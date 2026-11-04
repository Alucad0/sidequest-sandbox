import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pdf
from samsung_notes import find_storage, read_notes, write_sdocx

STATE = ".sync-state.json"  # in the mirror: which version of each note it holds
PDF_VERSION = 2  # raise when PDFs come out differently, so they're made again
GITHUB_LIMIT = 100 * 1024 * 1024  # GitHub rejects files bigger than this
PUSH_LIMIT = 1024 * 1024 * 1024  # and pushes over 2 GB, so big syncs go in parts of about this size
EXCLUDE_START, EXCLUDE_END = "# notes_sync: too big for GitHub", "# notes_sync end"


def find_sdocx(given):
    if given:
        return given
    # cargo install sdocx-cli names it sdocx-cli.exe, other builds call it sdocx
    for name in ("sdocx-cli", "sdocx"):
        found = shutil.which(name) or Path.home() / ".cargo" / "bin" / f"{name}.exe"
        if Path(found).exists():
            return str(found)
    return None


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_json(path, data):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def pdf_outdated(note, old, pdf_path):
    if old.get("pdf") == PDF_VERSION:
        # a PDF that failed is only tried again when the note changes
        return not pdf_path.exists() and not old.get("pdf_error")
    # made by an older version: only failed PDFs and notes with an imported PDF come out different now
    return old.get("pdf") is not True or not pdf_path.exists() or any(note.folder.glob("media/*.pdf"))


def sync_mirror(notes, out, sdocx, full=False, dry_run=False):
    state = {} if full else load_json(out / STATE).get("notes", {})
    current = {note.uuid: note for note in notes}
    removed = changed = 0

    # deleted or moved notes: remove the old copy first, a moved one is written again below
    for uuid, old in list(state.items()):
        if uuid in current and current[uuid].path == old["path"]:
            continue
        print(f"  {'moved  ' if uuid in current else 'removed'}  {old['path']}")
        removed += 1
        if not dry_run:
            for ext in (".sdocx", ".pdf"):
                (out / (old["path"] + ext)).unlink(missing_ok=True)
        del state[uuid]

    todo = []
    for note in notes:
        old = state.get(note.uuid)
        if (old and old["modified"] == note.modified and (out / (note.path + ".sdocx")).exists()
                and not (sdocx and pdf_outdated(note, old, out / (note.path + ".pdf")))):
            continue
        todo.append(note)

    try:
        for number, note in enumerate(todo, 1):
            print(f"  [{number}/{len(todo)}] {'updated' if note.uuid in state else 'new    '}  {note.path}")
            changed += 1
            if dry_run:
                continue
            target = out / (note.path + ".sdocx")
            target.parent.mkdir(parents=True, exist_ok=True)
            write_sdocx(note, target)
            state[note.uuid] = {"path": note.path, "modified": note.modified}
            if sdocx:
                error = pdf.convert(sdocx, target, target.with_suffix(".pdf"))
                if error:
                    # keeps the .sdocx, and an older PDF if there is one
                    print(f"      couldn't make the PDF: {error}")
                state[note.uuid].update(pdf=PDF_VERSION, **({"pdf_error": error} if error else {}))
            if number % 20 == 0:
                save_json(out / STATE, {"notes": state})
    finally:
        if not dry_run:
            save_json(out / STATE, {"notes": state})
            remove_empty_folders(out)
    failed = sorted((old["path"], old["pdf_error"]) for old in state.values() if old.get("pdf_error"))
    if failed and sdocx:
        print(f"No PDF for {len(failed)} notes, the converter can't handle them yet:")
        for path, error in failed:
            print(f"  {path}  ({error})")
    return changed, removed


def remove_empty_folders(out):
    for folder in sorted((p for p in out.rglob("*") if p.is_dir() and ".git" not in p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def git(out, *args, check=True, input=None):
    return subprocess.run(["git", "-C", str(out), *args], check=check, capture_output=True, text=True, encoding="utf-8",
                          input=input)


def push_github(out):
    if not (out / ".git").exists():
        raise RuntimeError(f"{out} isn't a git repository, see 'GitHub setup' in the README")

    # files over GitHub's limit stay local, listed in .git/info/exclude so they're never committed
    too_big = sorted(p.relative_to(out).as_posix() for p in out.rglob("*")
                     if p.is_file() and ".git" not in p.parts and p.stat().st_size > GITHUB_LIMIT)
    exclude = out / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    if EXCLUDE_START in lines:
        lines = lines[:lines.index(EXCLUDE_START)] + lines[lines.index(EXCLUDE_END) + 1:]
    if too_big:
        lines += [EXCLUDE_START, *("/" + glob_escape(path) for path in too_big), EXCLUDE_END]
        print(f"  over 100 MB, not pushed to GitHub: {', '.join(too_big)}")
        for path in too_big:
            git(out, "rm", "--cached", "--quiet", "--ignore-unmatch", "--", path)
    exclude.write_text("\n".join(lines) + "\n", encoding="utf-8")

    git(out, "add", "-A")
    changed = [path for path in git(out, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if path]
    # GitHub refuses pushes over 2 GB, so a big sync (like the first one) is committed and pushed in parts
    batches, size = [[]], 0
    for path in changed:
        file = out / path
        file_size = file.stat().st_size if file.exists() else 0
        if batches[-1] and size + file_size > PUSH_LIMIT:
            batches.append([])
            size = 0
        batches[-1].append(path)
        size += file_size
    if len(batches) > 1:
        git(out, "reset", "-q")

    message = f"Sync Samsung Notes {datetime.now():%Y-%m-%d %H:%M}"
    for number, batch in enumerate(b for b in batches if b):
        if len(batches) > 1:
            # literal so brackets and stars in note titles aren't patterns
            git(out, "--literal-pathspecs", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul",
                input="\0".join(batch))
        part = f", part {number + 1} of {len(batches)}" if len(batches) > 1 else ""
        git(out, "commit", "-m", f"{message} ({len(batch)} files{part})")
        push(out)
        print(f"GitHub: pushed {len(batch)} changed files{part}")
    if not changed:
        # pushes what an earlier run committed but couldn't push
        push(out)
        print("GitHub: up to date")


def push(out):
    # -u so the first push of a new repository works too
    pushed = git(out, "push", "-u", "origin", "HEAD", check=False)
    if pushed.returncode != 0:
        raise RuntimeError(f"Committed, but git push failed:\n{pushed.stderr.strip()}")


def glob_escape(path):
    # exclude lines are patterns, so brackets, stars etc. in note titles must not count as wildcards
    return "".join("\\" + c if c in "[]*?!#\\" else c for c in path)


def main():
    parser = argparse.ArgumentParser(description="Copy Samsung Notes as .sdocx and PDF to a folder, GitHub and Google Drive, "
                                                 "updating only the notes changed since last time.")
    parser.add_argument("--out", type=Path, default=Path.home() / "Documents" / "Samsung Notes",
                        help="local copy of the notes (default Documents/Samsung Notes)")
    parser.add_argument("--github", action="store_true", help="commit and push the local copy, which must be a git clone")
    parser.add_argument("--drive", nargs="?", const="Samsung Notes", metavar="FOLDER",
                        help="upload to this Google Drive folder (default 'Samsung Notes')")
    parser.add_argument("--no-pdf", action="store_true", help="only copy the .sdocx files")
    parser.add_argument("--sdocx", metavar="PATH", help="the sdocx converter, if it isn't on PATH")
    parser.add_argument("--full", action="store_true", help="write every note again, even unchanged ones")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without changing anything")
    args = parser.parse_args()

    sdocx = None
    if not args.no_pdf:
        sdocx = find_sdocx(args.sdocx)
        if not sdocx:
            sys.exit("Couldn't find the sdocx converter. Install it with: cargo install sdocx-cli\n(or use --no-pdf)")

    try:
        notes = read_notes(find_storage())
    except RuntimeError as error:
        sys.exit(str(error))
    print(f"{len(notes)} notes in Samsung Notes, copying to {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)
    changed, removed = sync_mirror(notes, args.out, sdocx, full=args.full, dry_run=args.dry_run)
    print(f"{'Would write' if args.dry_run else 'Wrote'} {changed} notes, {removed} removed or moved")

    if args.dry_run:
        return
    try:
        if args.github:
            push_github(args.out)
        if args.drive:
            import drive
            drive.sync(drive.connect(), args.out, args.drive)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(getattr(error, "stderr", None) or str(error))


if __name__ == "__main__":
    main()
