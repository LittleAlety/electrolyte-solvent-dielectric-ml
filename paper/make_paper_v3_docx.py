# -*- coding: utf-8 -*-
"""Render paper/paper_zh_draft_v3.md into a Word document.

Fixes two problems of the v2 renderer:

*   Image paths in the rewritten draft are relative to the markdown file
    (``../probes/artifacts/...``) so that they also resolve on GitHub.  The
    renderer tries the markdown directory first, then the repository root.
*   Every figure is scaled to fit BOTH the usable page width and the usable
    page height, so a tall multi-panel figure is never cropped.

Run::

    python paper/make_paper_v3_docx.py
"""
from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

REPO = Path(__file__).resolve().parent.parent
MD = REPO / "paper" / "paper_zh_draft_v3.md"
DEFAULT_OUT = (REPO.parent / "成果输出"
               / "论文_电解液溶剂筛选中的描述符决策稳定性_v3.docx")

IMAGE_RE = re.compile(r"^!\[(?P<cap>.*?)\]\((?P<path>.*?)\)\s*$")
BOLD_RE = re.compile(r"(\*\*.+?\*\*|\x60[^\x60]+\x60)")

# A4 portrait, 2.3 cm side margins, 2.5 cm top/bottom.
PAGE_W_CM = 21.0
PAGE_H_CM = 29.7
MARGIN_SIDE_CM = 2.3
MARGIN_TB_CM = 2.5
USABLE_W_CM = PAGE_W_CM - 2 * MARGIN_SIDE_CM          # 16.4
USABLE_H_CM = PAGE_H_CM - 2 * MARGIN_TB_CM            # 24.7
MAX_IMG_W_CM = 15.6                                   # leave a little slack
MAX_IMG_H_CM = 19.5                                   # room for caption


def resolve_image(relative: str) -> Path | None:
    """Resolve a markdown image path against the draft dir, then the repo root."""
    for base in (MD.parent, REPO):
        candidate = (base / relative).resolve()
        if candidate.is_file():
            return candidate
    return None


def image_size_cm(path: Path) -> tuple[float, float]:
    """Return the drawn (width, height) in cm, fitted inside the page box."""
    from PIL import Image
    with Image.open(path) as im:
        px_w, px_h = im.size
    aspect = px_w / px_h if px_h else 1.0
    width = min(MAX_IMG_W_CM, MAX_IMG_H_CM * aspect)
    return width, width / aspect


def set_cjk(style_name, doc, ascii_font, cjk_font, size=None, bold=None):
    st = doc.styles[style_name]
    st.font.name = ascii_font
    if size is not None:
        st.font.size = Pt(size)
    if bold is not None:
        st.font.bold = bold
    rpr = st.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rf)
    rf.set(qn("w:eastAsia"), cjk_font)
    rf.set(qn("w:ascii"), ascii_font)
    rf.set(qn("w:hAnsi"), ascii_font)


def add_runs(par, text):
    for piece in BOLD_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            par.add_run(piece[2:-2]).bold = True
        elif piece.startswith("\x60") and piece.endswith("\x60") and len(piece) > 2:
            r = par.add_run(piece[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0x1F, 0x3B, 0x63)
        else:
            par.add_run(piece)


def add_image(doc, rel_path, caption):
    img = resolve_image(rel_path)
    if img is None:
        par = doc.add_paragraph()
        par.add_run("[缺图：" + rel_path + "]").italic = True
        return False
    width_cm, _height_cm = image_size_cm(img)
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(6)
    par.paragraph_format.space_after = Pt(2)
    par.add_run().add_picture(str(img), width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(10)
    r = cap.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    return True


def add_table(doc, rows):
    ncol = max(len(r) for r in rows)
    tbl = doc.add_table(rows=0, cols=ncol)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        cells = tbl.add_row().cells
        for j in range(ncol):
            txt = row[j] if j < len(row) else ""
            cells[j].text = ""
            par = cells[j].paragraphs[0]
            add_runs(par, txt)
            for r in par.runs:
                r.font.size = Pt(9)
                if i == 0:
                    r.bold = True
    doc.add_paragraph()


def is_sep(line):
    s = line.strip()
    return bool(s) and set(s) <= set("|-: ") and "-" in s


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(MD))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    lines = io.open(args.md, encoding="utf-8").read().split("\n")

    doc = Document()
    set_cjk("Normal", doc, "Times New Roman", "宋体", size=10.5)
    for name, sz in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5), ("Title", 20)):
        try:
            set_cjk(name, doc, "Times New Roman", "黑体", size=sz)
        except KeyError:
            pass
    sec = doc.sections[0]
    sec.page_width = Cm(PAGE_W_CM)
    sec.page_height = Cm(PAGE_H_CM)
    sec.left_margin = Cm(MARGIN_SIDE_CM)
    sec.right_margin = Cm(MARGIN_SIDE_CM)
    sec.top_margin = Cm(MARGIN_TB_CM)
    sec.bottom_margin = Cm(MARGIN_TB_CM)

    n_fig = n_tab = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s == "" or s == "---":
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            for bl in block:
                par = doc.add_paragraph()
                r = par.add_run(bl if bl else " ")
                r.font.name = "Consolas"
                r.font.size = Pt(9)
                par.paragraph_format.space_after = Pt(0)
            continue
        m = IMAGE_RE.match(s)
        if m:
            if add_image(doc, m.group("path"), m.group("cap")):
                n_fig += 1
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not is_sep(lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            if rows:
                add_table(doc, rows)
                n_tab += 1
            continue
        if s.startswith("### "):
            doc.add_heading(s[4:].strip(), level=2)
        elif s.startswith("## "):
            doc.add_heading(s[3:].strip(), level=1)
        elif s.startswith("# "):
            doc.add_heading(s[2:].strip(), level=0)
        else:
            par = doc.add_paragraph()
            par.paragraph_format.first_line_indent = Cm(0.74)
            par.paragraph_format.space_after = Pt(4)
            add_runs(par, s)
        i += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print("saved", out)
    print("paragraphs", len(doc.paragraphs), "tables", n_tab, "figures", n_fig)


if __name__ == "__main__":
    main()