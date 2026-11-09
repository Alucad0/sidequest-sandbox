# Samsung Notes sync

Copies your Samsung Notes to a folder, GitHub and Google Drive. Each note is saved twice:

- **`.sdocx`:** the note itself, which Samsung Notes on any device can import.
- **`.pdf`:** for reading anywhere.

Your Samsung Notes folders are kept as the folder structure. Only notes changed since the last run are written and uploaded again. Notes you delete or move are deleted or moved in the copies too. Notes in the trash are skipped.

## Usage

From this folder:

```bash
python notes_sync.py --github --drive
```

```output
495 notes in Samsung Notes, copying to C:\Users\you\Documents\Samsung Notes
  moved    SF1688 - Disk Matte/ex tenta
  [1/2] updated  SF1688 - Disk Matte/formelsamling
  [2/2] new      SF1688 - Disk Matte/Tentor/ex tenta
Wrote 2 notes, 1 removed or moved
GitHub: pushed 5 changed files
  Drive: uploading SF1688 - Disk Matte/formelsamling.pdf
  ...
Drive: uploaded 4 files, removed 2
```

The first run writes all notes, which takes a while (about 3 GB).

| Option | |
|---|---|
| `--out DIR` | local copy (default `Documents/Samsung Notes`) |
| `--github` | commit and push the local copy |
| `--drive [FOLDER]` | upload to this Google Drive folder (default `Samsung Notes`) |
| `--no-pdf` | only copy the `.sdocx` files |
| `--sdocx PATH` | the PDF converter, if it isn't on PATH |
| `--full` | write every note again, e.g. after updating the converter |
| `--dry-run` | show what would change without changing anything |

It reads the Samsung Notes app for Windows, so notes from your phone or tablet have to be synced there through Samsung Cloud first.

## PDF converter

Samsung's format isn't public. The PDFs are made by [sdocx](https://github.com/twangodev/sdocx), an open-source converter built by reverse engineering the format, so check the PDFs against Samsung Notes. Install it with Rust:

```bash
cargo install sdocx-cli
```

If it fails with `dlltool.exe: program not found`, Rust is using its GNU toolchain. Build with the Microsoft one instead, which needs Visual Studio Build Tools:

```bash
cargo +stable-x86_64-pc-windows-msvc install sdocx-cli
```

Then install the Python packages:

```bash
pip install -r requirements.txt
```

The converter only draws your handwriting, so for notes written on an imported PDF (slides, exams) the program adds the PDF pages underneath with [PyMuPDF](https://pymupdf.readthedocs.io/). It also fixes cut-out images that Samsung saved as BMP but named `.png`, which the converter refuses.

Converting takes a few seconds per note. Very long pages get a smaller print size in the PDF, but nothing is cut off.

Some notes still can't be converted, e.g. ones with over a million pen points. Their `.sdocx` is still copied, and every run lists them. The PDF is tried again only when the note changes. Until then you can export the PDF from Samsung Notes yourself and put it next to the `.sdocx`; it's kept and synced like the others.

## GitHub setup

`--github` doesn't create the repository, it commits to and pushes the local copy. Set that up once:

1. Make an empty **private** repository on GitHub (no README or license, so there's nothing to merge).
2. Connect the local copy to it:

   ```bash
   cd "$HOME\Documents\Samsung Notes"
   git init -b main
   git remote add origin https://github.com/YOU/samsung-notes.git
   ```

The first `--github` run commits everything and pushes it. If you haven't pushed to GitHub from this computer before, Git asks you to sign in.

GitHub refuses pushes over 2 GB, so a big sync like the first one is committed and pushed in parts of about 1 GB. GitHub also doesn't allow files over 100 MB. Those stay in the local copy and on Drive, and the run lists them. Every changed note adds a new copy to the repository's history, so it grows over time.

## Google Drive setup

In [Google Cloud Console](https://console.cloud.google.com/), use the same project as the schedule finder or set up a new one (see its README):
- Enable the **Google Drive API**.
- Save the **Desktop app** client JSON here as `credentials.json`.

On the first run, a browser window asks you to sign in. `--drive` then makes a folder called `Samsung Notes` at the top of your Drive (or the name you give with `--drive NAME`) and uploads into it. If you already have a folder with that name, you get a second one, because the program can only see the files and folders it made, not the rest of your Drive. Removed notes go to the Drive trash.

`credentials.json`, `token.json` and `drive_state.json` are gitignored. Never commit them.
