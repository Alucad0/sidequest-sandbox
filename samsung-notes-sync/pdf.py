import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

# a PDF page can be at most 200 inches, so very long notes are tried again at a smaller print size
DPIS = (96, 200, 400, 1000, 2500)
# "Page 2: 1752 x 2479, background #fcfcfc, template custom PDF page 3, ..." in the converter's output
PDF_TEMPLATE = re.compile(r"Page (\d+):.*template custom PDF page (\d+)")
# the plain fill the converter paints first on every page, which would hide an imported PDF
BACKGROUND = re.compile(rb"q [\d.]+ 0 0 -[\d.]+ 0 [\d.]+ cm [\d. ]+ (?:g|rg) 0 0 m [\d.]+ 0 l [\d.]+ [\d.]+ l 0 [\d.]+ l\s+h\s+f\s+Q")


def convert(sdocx, source, target):
    # returns None, or why the PDF couldn't be made
    try:
        import pymupdf
    except ImportError:
        return "PDFs need: pip install -r requirements.txt"

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        source, background = prepare(pymupdf, source, temp)
        output = temp / "note.pdf"
        for dpi in DPIS:
            try:
                result = subprocess.run([sdocx, str(source), "-f", "pdf", "--pdf-dpi", str(dpi), "-o", str(output)],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            except subprocess.TimeoutExpired:
                return "timed out"
            if result.returncode == 0 and output.exists():
                break
            error = ((result.stderr or result.stdout).strip().splitlines() or ["failed"])[-1]
            if "dimensions" not in error:
                return error
        else:
            return error

        templates = {int(page): int(pdf_page) for page, pdf_page in PDF_TEMPLATE.findall(result.stdout + result.stderr)}
        if background and templates:
            add_backgrounds(pymupdf, output, background, templates)
        finished = target.with_name(target.stem + ".tmp.pdf")
        shutil.copyfile(output, finished)
        os.replace(finished, target)
    return None


def prepare(pymupdf, source, temp):
    # Samsung saves some cut-out images as BMP named .png, which the converter refuses, so those become real PNGs
    # returns the .sdocx to convert, and the imported PDF if the note has one
    background = None
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        bmps = [n for n in names if n.lower().endswith(".png") and archive.open(n).read(2) == b"BM"]
        for name in names:
            if name.startswith("media/") and name.lower().endswith(".pdf"):
                background = temp / "background.pdf"
                background.write_bytes(archive.read(name))
        if not bmps:
            return source, background
        fixed = temp / "fixed.sdocx"
        with zipfile.ZipFile(fixed, "w", zipfile.ZIP_DEFLATED) as copy:
            for name in names:
                data = archive.read(name)
                if name in bmps:
                    data = pymupdf.Pixmap(data).tobytes("png")
                copy.writestr(name, data)
    return fixed, background


def add_backgrounds(pymupdf, output, background, templates):
    # draws each imported PDF page under the handwriting, full width at the top, like Samsung Notes does
    note, pdf = pymupdf.open(output), pymupdf.open(background)
    for number, pdf_page in templates.items():
        if number >= len(note) or not 1 <= pdf_page <= len(pdf):
            continue
        page = note[number]
        for xref in page.get_contents():
            stream = note.xref_stream(xref)
            if BACKGROUND.search(stream):
                note.update_stream(xref, BACKGROUND.sub(b"", stream, count=1))
                break
        # an imported PDF can also be one long page with all its pages under each other
        width, top, index = page.rect.width, 0, pdf_page - 1
        while index < len(pdf):
            height = width * pdf[index].rect.height / pdf[index].rect.width
            if top + height / 2 > page.rect.height:
                break
            page.show_pdf_page(pymupdf.Rect(0, top, width, top + height), pdf, index, overlay=False)
            top += height
            index += 1
    note.save(output.with_name("with-background.pdf"), garbage=3, deflate=True)
    note.close()
    pdf.close()
    os.replace(output.with_name("with-background.pdf"), output)
