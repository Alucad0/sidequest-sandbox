import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Samsung Notes for Windows (Microsoft Store app)
APP_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
APP_PATTERN = "SAMSUNGELECTRONICSCoLtd.SamsungNotes_*"
# the top level, shown as "Folders" in the app (UUID_UNCATEGORIZED is from older versions)
ROOT_FOLDERS = {"", "uncategorized:///", "UUID_UNCATEGORIZED"}
LIVE = 0  # NoteDB.DeletedStatus: 0 live, 2 in the trash


@dataclass
class Note:
    uuid: str
    path: str  # where it goes in the mirror, without extension, e.g. "SF1624 - Linear algebra/M1 Vektorer"
    modified: int  # milliseconds since 1970
    folder: Path  # the note's files, the same as an unzipped .sdocx


def find_storage():
    for package in sorted(APP_DATA.glob(APP_PATTERN)):
        state = package / "LocalState"
        if (state / "Storage.sqlite").exists():
            return state
    raise RuntimeError("Couldn't find Samsung Notes, is the Windows app installed and opened at least once?")


def safe_name(name):
    # Windows doesn't allow these characters, and drops trailing dots and spaces
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    return name or "_"


def read_notes(state):
    # the app keeps the database open, so read a copy instead of risking a lock
    with tempfile.TemporaryDirectory() as temp:
        for file in state.glob("Storage.sqlite*"):
            shutil.copy2(file, temp)
        db = sqlite3.connect(Path(temp) / "Storage.sqlite")
        try:
            folders = {uuid: (parent, name, deleted) for uuid, parent, name, deleted in db.execute(
                "SELECT UUID, ParentUUID, DisplayName, IsDeleted FROM CategoryTreeDB")}
            rows = db.execute(
                "SELECT UUID, CategoryUUID, Title, RecommendedTitle, LastModifiedAt, FilePath, CreatedAt "
                "FROM NoteDB WHERE DeletedStatus = ? ORDER BY CreatedAt, UUID", (LIVE,)).fetchall()
        finally:
            db.close()

    notes, taken = [], set()
    for uuid, category, title, recommended, modified, file_path, _ in rows:
        folder_path = folder_names(folders, category or "")
        files = Path(file_path) if file_path else state / "wdoc" / uuid
        if folder_path is None or not files.is_dir():
            continue
        name = safe_name((title or "").strip() or recommended or "Untitled")
        path = "/".join(folder_path + [name])
        # two notes with the same title in one folder: the newer one gets a number
        number = 2
        while path.lower() in taken:
            path = "/".join(folder_path + [f"{name} ({number})"])
            number += 1
        taken.add(path.lower())
        notes.append(Note(uuid, path, modified or 0, files))
    return notes


def folder_names(folders, category):
    # "SF1624 - Linear algebra/Tentor" as a list, or None if the folder is in the trash
    names, seen = [], set()
    while category not in ROOT_FOLDERS:
        if category not in folders or category in seen:
            return None if category.endswith(":///") else names[::-1]
        seen.add(category)
        parent, name, deleted = folders[category]
        if deleted:
            return None
        names.append(safe_name(name or ""))
        category = parent or ""
    return names[::-1]


def write_sdocx(note, target):
    # a .sdocx is the note's folder zipped, which Samsung Notes on any device can import
    temp = target.with_name(target.name + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(note.folder.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(note.folder).as_posix())
    os.replace(temp, target)
