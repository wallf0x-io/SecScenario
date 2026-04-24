"""Extracts plain text from uploaded reports (PDF/MD/HTML/TXT/ZIP)."""
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
import markdown as md_lib


MAX_CHARS_PER_FILE = 200_000


def extract_text(file_path: Path) -> str:
    ext = file_path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _extract_pdf(file_path)
    if ext in {"md", "markdown", "rst"}:
        return _extract_markdown(file_path)
    if ext in {"html", "htm"}:
        return _extract_html(file_path)
    if ext == "zip":
        return _extract_zip(file_path)
    if ext in {"txt", "log", "json"}:
        return _read_text(file_path)
    return _read_text(file_path)


def _read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = path.read_text(encoding="latin-1", errors="ignore")
    return text[:MAX_CHARS_PER_FILE]


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(chunks)[:MAX_CHARS_PER_FILE]


def _extract_markdown(path: Path) -> str:
    raw = _read_text(path)
    html = md_lib.markdown(raw)
    return BeautifulSoup(html, "html.parser").get_text("\n")[:MAX_CHARS_PER_FILE]


def _extract_html(path: Path) -> str:
    raw = _read_text(path)
    return BeautifulSoup(raw, "html.parser").get_text("\n")[:MAX_CHARS_PER_FILE]


def _extract_zip(path: Path) -> str:
    pieces = []
    extract_root = path.parent / f"{path.stem}_extracted"
    extract_root.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            if member.endswith("/") or ".." in member:
                continue
            try:
                zf.extract(member, extract_root)
            except Exception:
                continue
            inner = extract_root / member
            if not inner.is_file():
                continue
            if inner.suffix.lower().lstrip(".") in {
                "pdf", "md", "markdown", "html", "htm", "txt", "log", "json", "rst"
            }:
                pieces.append(f"\n\n===== {member} =====\n")
                pieces.append(extract_text(inner))
    combined = "".join(pieces)
    return combined[: MAX_CHARS_PER_FILE * 2]
