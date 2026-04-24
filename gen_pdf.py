"""One-shot: bundle all SecScenario source into a single PDF.

Excludes: .env, .env.example (real-format key), uploads/, challenges/,
instance/, __pycache__/, *.pyc, static/** binaries, this script itself.
"""
from __future__ import annotations
from pathlib import Path
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "SecScenario_source.pdf"

EXCLUDE_DIRS = {
    ".git", "__pycache__", "uploads", "challenges", "instance", ".venv", "venv",
    ".idea", ".vscode", ".claude",
}
EXCLUDE_FILES = {".env", ".env.example", "gen_pdf.py", "SecScenario_source.pdf"}
INCLUDE_EXTS = {
    ".py", ".html", ".css", ".js", ".md", ".txt", ".json", ".rst",
    ".cfg", ".toml", ".yaml", ".yml",
}
# files with no extension that we still want (README, etc. handled by name)
INCLUDE_NAMES = {"requirements.txt", ".gitignore", "README"}


def gather_files() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        if p.suffix.lower() in INCLUDE_EXTS or p.name in INCLUDE_NAMES:
            out.append(p)
    # stable grouping: Python first, then templates, static, then rest
    def sort_key(path: Path) -> tuple:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        group = (
            0 if rel == "README.md" else
            1 if rel == "requirements.txt" else
            2 if path.suffix == ".py" else
            3 if rel.startswith("templates/") else
            4 if rel.startswith("static/") else
            5
        )
        return (group, rel.lower())
    return sorted(out, key=sort_key)


def sanitize(text: str) -> str:
    # fpdf2 TTF path supports unicode, but normalize weird linebreaks.
    return text.replace("\r\n", "\n").replace("\r", "\n")


class SourcePDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Consolas", "B", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, f"SecScenario — source bundle", align="L")
        self.cell(0, 6, f"page {self.page_no()}", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Consolas", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "localhost tool — not for distribution", align="C")


def build():
    files = gather_files()
    pdf = SourcePDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_font("Consolas", "", "C:/Windows/Fonts/consola.ttf")
    pdf.add_font("Consolas", "B", "C:/Windows/Fonts/consolab.ttf")

    # ----- cover -----
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Consolas", "B", 26)
    pdf.ln(60)
    pdf.cell(0, 14, "SecScenario", align="C")
    pdf.ln(18)
    pdf.set_font("Consolas", "", 11)
    pdf.cell(0, 8, "Vulnerability Report -> CTF Challenge Pipeline", align="C")
    pdf.ln(12)
    pdf.set_font("Consolas", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, "Source code bundle", align="C")
    pdf.ln(6)
    pdf.cell(0, 6, f"{len(files)} files", align="C")
    pdf.ln(30)
    pdf.set_font("Consolas", "B", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, "Contents:", align="L")
    pdf.ln(8)
    pdf.set_font("Consolas", "", 8.5)
    pdf.set_text_color(40, 40, 40)
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        pdf.cell(0, 5, f"  - {rel}")
        pdf.ln(4.5)

    # ----- per-file pages -----
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raw = f"[could not read: {e}]"
        raw = sanitize(raw)

        pdf.add_page()
        # file header bar
        pdf.set_fill_color(15, 18, 30)
        pdf.set_text_color(0, 217, 255)
        pdf.set_font("Consolas", "B", 11)
        pdf.cell(0, 9, f"  {rel}", fill=True, align="L")
        pdf.ln(11)

        # line-numbered body
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("Consolas", "", 7.4)
        lines = raw.split("\n")
        line_w = pdf.w - 2 * pdf.l_margin
        for i, line in enumerate(lines, start=1):
            num = f"{i:>4}  "
            body = line.replace("\t", "    ")
            if not body:
                pdf.ln(3.2); continue
            # wrap long lines manually at a rough char budget
            budget = 110
            chunks = [body[j:j+budget] for j in range(0, len(body), budget)] or [""]
            for k, chunk in enumerate(chunks):
                pdf.set_text_color(140, 140, 140)
                pdf.cell(12, 3.4, num if k == 0 else "    ")
                pdf.set_text_color(20, 20, 20)
                # use write_html-less simple write
                pdf.cell(0, 3.4, chunk)
                pdf.ln(3.4)

    pdf.output(str(OUT))
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB, {len(files)} files)")


if __name__ == "__main__":
    build()
