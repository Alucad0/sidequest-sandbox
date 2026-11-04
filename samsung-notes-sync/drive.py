import json
import os
import warnings
from pathlib import Path

HERE = Path(__file__).parent
CREDENTIALS = HERE / "credentials.json"
TOKEN = HERE / "token.json"
STATE = HERE / "drive_state.json"  # Drive ids of what's uploaded, and which local version each one is
# only files and folders this program made, it can't see the rest of your Drive
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER = "application/vnd.google-apps.folder"
MIME_TYPES = {".pdf": "application/pdf"}


def connect():
    # Google's libraries warn on every run that Python 3.10 won't get their future updates; it still works
    warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Google Drive support needs: pip install -r requirements.txt")
    if not CREDENTIALS.exists():
        raise RuntimeError(f"Missing {CREDENTIALS.name}, see 'Google Drive setup' in the README")

    from google.auth.exceptions import RefreshError

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Google expires the sign-in about once a week while the app is in testing mode
            creds = None
    if not creds or not creds.valid:
        print("Signing in to Google, a browser window will open (or use the link below).")
        creds = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def load_state(root_name):
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    if state.get("root_name") != root_name:
        # a different Drive folder starts over
        state = {"root_name": root_name, "root": None}
    state.setdefault("folders", {})
    state.setdefault("files", {})
    return state


def save_state(state):
    temp = STATE.with_name(STATE.name + ".tmp")
    temp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, STATE)


def exists(service, file_id):
    from googleapiclient.errors import HttpError

    try:
        return not service.files().get(fileId=file_id, fields="trashed").execute()["trashed"]
    except HttpError as error:
        if error.resp.status == 404:
            return False
        raise


def create_folder(service, name, parent=None):
    body = {"name": name, "mimeType": FOLDER, "parents": [parent] if parent else []}
    return service.files().create(body=body, fields="id").execute()["id"]


def folder_id(service, state, folder):
    # Drive id of a folder like "SF1624 - Linear algebra/Tentor", made if needed
    if not folder:
        return state["root"]
    if folder not in state["folders"]:
        parent, _, name = folder.rpartition("/")
        state["folders"][folder] = create_folder(service, name, folder_id(service, state, parent))
    return state["folders"][folder]


def trash(service, file_id):
    from googleapiclient.errors import HttpError

    try:
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
    except HttpError as error:
        if error.resp.status != 404:
            raise


def upload(service, state, path, file, known_id):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(file), mimetype=MIME_TYPES.get(file.suffix, "application/octet-stream"), resumable=True)
    if known_id:
        try:
            return service.files().update(fileId=known_id, media_body=media, fields="id").execute()["id"]
        except HttpError as error:
            if error.resp.status != 404:
                raise
            # deleted on Drive, upload it again
    folder, _, name = path.rpartition("/")
    body = {"name": name, "parents": [folder_id(service, state, folder)]}
    try:
        return service.files().create(body=body, media_body=media, fields="id").execute()["id"]
    except HttpError as error:
        if error.resp.status != 404:
            raise
        # a folder was deleted on Drive, make the folders again
        state["folders"] = {}
        body["parents"] = [folder_id(service, state, folder)]
        return service.files().create(body=body, media_body=media, fields="id").execute()["id"]


def sync(service, out, root_name):
    state = load_state(root_name)
    if not state["root"] or not exists(service, state["root"]):
        print(f"Drive: making the folder '{root_name}'")
        state.update(root=create_folder(service, root_name), folders={}, files={})

    # files starting with a dot (the sync state, .git) stay local
    local = {p.relative_to(out).as_posix(): p for p in sorted(out.rglob("*"))
             if p.is_file() and not any(part.startswith(".") for part in p.relative_to(out).parts)}
    uploaded = removed = 0
    try:
        for path, file in local.items():
            stat = file.stat()
            known = state["files"].get(path)
            version = [stat.st_size, stat.st_mtime_ns]
            if known and known["version"] == version:
                continue
            print(f"  Drive: uploading {path}")
            file_id = upload(service, state, path, file, known and known["id"])
            state["files"][path] = {"id": file_id, "version": version}
            uploaded += 1
            save_state(state)

        for path in [p for p in state["files"] if p not in local]:
            print(f"  Drive: removing {path}")
            trash(service, state["files"].pop(path)["id"])
            removed += 1

        # folders with nothing left in them, trashing the top one takes its subfolders along
        used = {"/".join(path.split("/")[:depth]) for path in local for depth in range(1, path.count("/") + 1)}
        for folder in sorted(state["folders"]):
            if folder not in used and folder in state["folders"]:
                trash(service, state["folders"][folder])
                state["folders"] = {f: i for f, i in state["folders"].items() if f != folder and not f.startswith(folder + "/")}
    finally:
        save_state(state)
    print(f"Drive: uploaded {uploaded} files, removed {removed}")
