# -*- coding: utf-8 -*-
"""Render paper/paper_zh_draft_v3.md into the journal template layout.

Template: the file "template 20233020" fixes the page geometry and the type
scale: A4 (21.0 x 29.7 cm), 2.3 cm side margins, 3.4 cm top and 3.0 cm bottom
margins; Chinese title 16 pt bold, level-1 headings 12 pt bold, level-2/3
headings 10.5 pt bold, body Song / Times New Roman 10.5 pt on an exact 15 pt
line with a two-character first-line indent, figure captions 9 pt bold and
centred, three-line tables with 7.5 pt text and a centred 9 pt bold table
title, acknowledgements 9 pt FangSong, references 7.5 pt with a hanging
indent.

Two delivery rules from the standing brief are enforced here: every figure is
scaled to fit BOTH the usable page width and the usable page height, so a tall
multi-panel figure is never cropped; and the draft carries no appendix, so the
render adds none.

Run:

    python paper/make_paper_v3_template_docx.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

REPO = Path(__file__).resolve().parent.parent
MD = REPO / "paper" / "paper_zh_draft_v3.md"
OUT = (REPO.parent / "成果输出"
       / "论文_电解液溶剂筛选中的描述符决策稳定性_期刊模版.docx")

SONG = "宋体"
HEI = "黑体"
FANG = "仿宋"
TNR = "Times New Roman"
ARIAL = "Arial"
MONO = "Consolas"

BODY_SIZE = 10.5
SMALL_SIZE = 9.0
SIX_SIZE = 7.5
H1_SIZE = 12.0
TITLE_SIZE = 16.0
TITLE_EN_SIZE = 14.0
LINE_PT = 15.0
REF_LINE_PT = 11.0
TICK = chr(96)

PAGE_W_CM = 21.0
PAGE_H_CM = 29.7
MARGIN_SIDE_CM = 2.3
MARGIN_TOP_CM = 3.4
MARGIN_BOTTOM_CM = 3.0
USABLE_W_CM = PAGE_W_CM - 2 * MARGIN_SIDE_CM
USABLE_H_CM = PAGE_H_CM - MARGIN_TOP_CM - MARGIN_BOTTOM_CM
MAX_IMG_W_CM = 15.6
MAX_IMG_H_CM = 20.0

AUTHORS_ZH = "作者姓名1*，作者姓名2"
AFFILIATION_ZH = "单位名称，城市 邮编"
CLC = "O646；TP181"
TITLE_EN = ("Descriptor decision stability in electrolyte solvent screening: "
            "level artefacts, axis-locked disagreement and screening usability "
            "in an auditable five-channel funnel")
AUTHORS_EN = "Author A, Author B"
AFFILIATION_EN = "Affiliation, City Postcode, China"
KEYWORDS_EN = ("electrolyte solvent screening; descriptor decision stability; "
               "electronic-structure level; level artefact; ranking statistics; "
               "auditable machine learning; pre-registration; negative results")
ABSTRACT_EN = (
    "Electrolyte solvent screening rests on three computable properties: static permittivity, "
    "viscosity, and frontier-orbital energies with their derived oxidation and reduction windows. "
    "All three are heterogeneous in the public literature, and the orbital and redox channels are "
    "almost entirely computational, mixing functionals, basis sets and solvation models. More "
    "importantly, when the ordering induced by a descriptor is itself unstable, every screening "
    "conclusion built on it is unsound, and that risk is usually neither quantified nor audited. We "
    "release a 246-compound, 38-field static-permittivity dataset of near-room-temperature pure "
    "organic liquids, stratified by source, together with separately built orbital and redox "
    "channels drawn from openly redistributable sources. The method is a single-variable ladder: a "
    "free-molecule electronic-structure axis (P0 Koopmans, P1 delta-SCF, P2 implicit solvent) and a "
    "conditional-state axis (C0 bare molecule, C1 [Li(M)]+, C2 [Li(M)2]+), one factor per rung, "
    "with criteria frozen before the run, placebo permutation that must collapse the reading, "
    "grouped leakage audits, and every failure registered as part of the deliverable. Five results "
    "follow. First, decision stability is measurable: the resampling standard deviation of tau_b "
    "follows a finite-population correction, which puts a noise floor of 0.122 at the parent "
    "paper's sample size. Second, the cross-study disagreement on the reduction axis is a level "
    "artefact: all three oxidation-axis rungs sit within 0.04 sigma while all three reduction-axis "
    "rungs sit beyond 2.3 sigma, and holding the compounds fixed while changing only the level "
    "flips tau_b from +0.835 to -0.602. Third, ranking statistics and screening usability come "
    "apart: tau_b correlates with Top-10 overlap at only +0.793, while the unresolved fraction "
    "correlates with it at -0.862. Fourth, the discipline is engineered into artefacts that fail "
    "rather than drift: state legality became an on-disk registry enforced by a guard that refuses "
    "instead of returning None, citation flags are emitted by guards rather than typed by hand, and "
    "endpoint tolerances are frozen at 1e-12. Fifth, the missing dimension is intermolecular "
    "association: a structure-only 1-nearest-neighbour model reaches R2 of only 0.2503, "
    "fingerprint similarity correlates with the label gap at -0.0607, no very-similar-but-very-"
    "different pair exists, and the Kirkwood-Onsager orientational-correlation ratio is 2.5016 "
    "between donor and non-donor domains. Negative results, the ceiling and the audit trail are "
    "reported in full.")
ACK = ("本工作的全部数字由仓库内可执行产物生成并经一致性脚本校验；负结果与封顶读数一并登记，未作删减。"
       "感谢开源社区提供的 ThermoML、NBS Circular 514、Batt-SLM 与 THEMol 等公开数据与工具。")

IMAGE_RE = re.compile(r"^!\[(?P<cap>.*?)\]\((?P<path>.*?)\)\s*$")
TABLE_TITLE_RE = re.compile(r"^\*\*表\s*\d+\s*[　\s]*(?P<t>.+?)\*\*$")
INLINE_RE = re.compile(r"(\*\*.+?\*\*|\*[^*\n]+?\*|"
                       + TICK + r"[^" + TICK + r"\n]+?" + TICK + r")")
NUM_LIST_RE = re.compile(r"^(?P<n>\d+)\.\s+(?P<t>.*)$")


def letter_space(run, twentieths=0):
    if not twentieths:
        return
    rpr = run._element.get_or_add_rPr()
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:val"), str(twentieths))
    rpr.append(spacing)


def font(run, ascii_font, cjk, size, bold=None, italic=None):
    run.font.name = ascii_font
    run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic:
        run.font.italic = True
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), cjk)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)


# line_pt=None leaves the paragraph on the style line spacing, which is what
# an inline picture needs: exact line spacing clips inline images in Word.
def style_paragraph(par, *, line_pt=LINE_PT, before=0.0, after=0.0,
                    indent_chars=0.0, align=None, hanging=None,
                    keep_with_next=False):
    fmt = par.paragraph_format
    if line_pt:
        fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        fmt.line_spacing = Pt(line_pt)
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    if indent_chars:
        fmt.first_line_indent = Pt(indent_chars * BODY_SIZE)
    if hanging is not None:
        fmt.left_indent = Pt(hanging)
        fmt.first_line_indent = Pt(-hanging)
    if align is not None:
        par.alignment = align
    fmt.keep_with_next = keep_with_next
    return par


def add_text(par, text, size, ascii_font, cjk, bold_default=False):
    for piece in INLINE_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            font(par.add_run(piece[2:-2]), ascii_font, cjk, size, bold=True)
        elif piece.startswith(TICK) and piece.endswith(TICK) and len(piece) > 2:
            font(par.add_run(piece[1:-1]), ascii_font, cjk, size,
                 bold=True if bold_default else None)
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            font(par.add_run(piece[1:-1]), ascii_font, cjk, size, italic=True)
        else:
            font(par.add_run(piece), ascii_font, cjk, size,
                 bold=True if bold_default else None)
    return par


def add_paragraph(doc, text, *, size=BODY_SIZE, ascii_font=TNR, cjk=SONG,
                  indent=True, align=None, before=0.0, after=0.0,
                  bold_default=False, hanging=None, line_pt=LINE_PT,
                  keep_with_next=False):
    par = doc.add_paragraph()
    style_paragraph(par, line_pt=line_pt, before=before, after=after,
                    indent_chars=2.0 if indent else 0.0, align=align,
                    hanging=hanging, keep_with_next=keep_with_next)
    add_text(par, text, size, ascii_font, cjk, bold_default=bold_default)
    return par


def cell_border(cell, edge, size_eighths):
    tcpr = cell._tc.get_or_add_tcPr()
    borders = tcpr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcpr.append(borders)
    tag = "w:" + edge
    element = borders.find(qn(tag))
    if element is None:
        element = OxmlElement(tag)
        borders.append(element)
    element.set(qn("w:val"), "single")
    element.set(qn("w:sz"), str(size_eighths))
    element.set(qn("w:space"), "0")
    element.set(qn("w:color"), "000000")


def add_table_title(doc, text):
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, before=6.0, after=2.0,
                    keep_with_next=True)
    add_text(par, text, SMALL_SIZE, TNR, SONG, bold_default=True)
    return par


def add_three_line_table(doc, rows):
    width = max(len(row) for row in rows)
    table = doc.add_table(rows=0, cols=width)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for column in range(width):
            cell = cells[column]
            par = cell.paragraphs[0]
            style_paragraph(par, line_pt=10.0,
                            align=WD_ALIGN_PARAGRAPH.CENTER if row_index == 0 else None)
            add_text(par, row[column] if column < len(row) else "", SIX_SIZE,
                     TNR, SONG, bold_default=(row_index == 0))
    for cell in table.rows[0].cells:
        cell_border(cell, "top", 12)
        cell_border(cell, "bottom", 6)
    for cell in table.rows[-1].cells:
        cell_border(cell, "bottom", 12)
    style_paragraph(doc.add_paragraph(), line_pt=6.0)
    return table


def resolve_image(relative):
    for base in (MD.parent, REPO):
        candidate = (base / relative).resolve()
        if candidate.is_file():
            return candidate
    return None


def drawn_size_cm(path):
    from PIL import Image
    with Image.open(path) as im:
        px_w, px_h = im.size
    aspect = px_w / px_h if px_h else 1.0
    width = min(MAX_IMG_W_CM, MAX_IMG_H_CM * aspect)
    return width, width / aspect


CAPTION_NUM_RE = re.compile(r"^图\s*(\d+)\s*[　\s]*")


def journal_caption(caption):
    stripped = caption.strip()
    match = CAPTION_NUM_RE.match(stripped)
    if not match:
        return stripped
    return "图" + match.group(1) + "  " + stripped[match.end():].strip()


def add_figure(doc, relative_path, caption):
    target = resolve_image(relative_path)
    if target is None:
        add_paragraph(doc, "[缺图：" + relative_path + "]", size=SMALL_SIZE,
                      indent=False)
        return None
    width_cm, height_cm = drawn_size_cm(target)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, before=6.0, after=2.0,
                    keep_with_next=True, line_pt=None)
    par.add_run().add_picture(str(target), width=Cm(width_cm))
    cap = doc.add_paragraph()
    style_paragraph(cap, align=WD_ALIGN_PARAGRAPH.CENTER, before=0.0, after=8.0)
    add_text(cap, journal_caption(caption), SMALL_SIZE, ARIAL, HEI, bold_default=True)
    return width_cm, height_cm


def is_table_separator(line):
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= set("|-: ") and "-" in stripped


def split_table_row(line):
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def center_heading(doc, text, size=SMALL_SIZE):
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, before=10.0, after=4.0,
                    keep_with_next=True)
    add_text(par, text, size, ARIAL, HEI, bold_default=True)
    return par


def build_front_matter(doc, title_zh, subtitle_zh, abstract_zh, keywords_zh):
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, before=0.0, after=2.0)
    add_text(par, title_zh, TITLE_SIZE, ARIAL, SONG, bold_default=True)
    if subtitle_zh:
        par = doc.add_paragraph()
        style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, after=6.0)
        add_text(par, subtitle_zh, H1_SIZE, TNR, SONG, bold_default=True)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, after=0.0)
    add_text(par, AUTHORS_ZH, H1_SIZE, TNR, SONG)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, after=6.0)
    add_text(par, AFFILIATION_ZH, SMALL_SIZE, TNR, FANG)
    add_paragraph(doc, "**摘要：**" + abstract_zh, size=SMALL_SIZE,
                  indent=False, before=6.0)
    add_paragraph(doc, "**关键词：**" + keywords_zh, size=SMALL_SIZE,
                  indent=False, after=0.0)
    add_paragraph(doc, "**中图分类号：**" + CLC, size=SMALL_SIZE,
                  indent=False, after=8.0)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, before=6.0, after=2.0)
    add_text(par, TITLE_EN, TITLE_EN_SIZE, ARIAL, ARIAL, bold_default=True)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, after=0.0)
    add_text(par, AUTHORS_EN, H1_SIZE, TNR, TNR)
    par = doc.add_paragraph()
    style_paragraph(par, align=WD_ALIGN_PARAGRAPH.CENTER, after=6.0)
    add_text(par, AFFILIATION_EN, SMALL_SIZE, TNR, TNR)
    add_paragraph(doc, "**Abstract:**  " + ABSTRACT_EN, size=SMALL_SIZE,
                  indent=False, before=4.0)
    add_paragraph(doc, "**Key Words:**  " + KEYWORDS_EN, size=SMALL_SIZE,
                  indent=False, after=2.0)


def add_heading(doc, text, level):
    size = H1_SIZE if level == 1 else BODY_SIZE
    par = doc.add_paragraph()
    style_paragraph(par, before=10.0 if level == 1 else 8.0, after=4.0,
                    keep_with_next=True)
    add_text(par, text, size, ARIAL, HEI, bold_default=True)
    return par


def render_body(doc, lines, start, stop):
    fence = TICK * 3
    figures = []
    tables = 0
    index = start
    while index < stop:
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped == "---":
            index += 1
            continue
        if stripped.startswith(fence):
            index += 1
            block = []
            while index < stop and not lines[index].strip().startswith(fence):
                block.append(lines[index])
                index += 1
            index += 1
            for block_line in block:
                par = doc.add_paragraph()
                style_paragraph(par, line_pt=11.0, indent_chars=2.0)
                font(par.add_run(block_line if block_line else " "), MONO, MONO, 9.0)
            continue
        image = IMAGE_RE.match(stripped)
        if image:
            size = add_figure(doc, image.group("path"), image.group("cap"))
            if size is not None:
                figures.append((image.group("path"), size[0], size[1]))
            index += 1
            continue
        title_match = TABLE_TITLE_RE.match(stripped)
        if title_match:
            add_table_title(doc, stripped[2:-2].strip())
            index += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while index < stop and lines[index].strip().startswith("|"):
                if not is_table_separator(lines[index]):
                    rows.append(split_table_row(lines[index]))
                index += 1
            if rows:
                add_three_line_table(doc, rows)
                tables += 1
            continue
        if stripped.startswith("#### "):
            add_heading(doc, stripped[5:], 3)
        elif stripped.startswith("### "):
            add_heading(doc, stripped[4:], 2)
        elif stripped.startswith("## "):
            add_heading(doc, stripped[3:], 1)
        elif stripped.startswith("# "):
            add_heading(doc, stripped[2:], 1)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            add_paragraph(doc, "· " + stripped[2:], after=0.0)
        else:
            match = NUM_LIST_RE.match(stripped)
            if match:
                add_paragraph(doc, match.group("n") + ". " + match.group("t"), after=0.0)
            else:
                add_paragraph(doc, stripped, after=0.0)
        index += 1
    return figures, tables


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md", default=str(MD))
    parser.add_argument("--out", default=str(OUT))
    return parser.parse_args()


def scan_structure(lines):
    title_zh = ""
    subtitle_zh = ""
    abstract_index = None
    body_index = None
    reference_index = None
    keywords_zh = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not title_zh and stripped.startswith("# "):
            title_zh = stripped[2:].strip()
        elif not subtitle_zh and stripped.startswith("## ——"):
            subtitle_zh = stripped[3:].strip()
        elif stripped == "## 摘要" and abstract_index is None:
            abstract_index = index
        elif stripped.startswith("## 1 ") and body_index is None:
            body_index = index
        elif stripped == "## 参考文献" and reference_index is None:
            reference_index = index
        elif stripped.startswith("**关键词**") and not keywords_zh:
            keywords_zh = stripped.split("：", 1)[1].strip()
    return title_zh, subtitle_zh, abstract_index, body_index, reference_index, keywords_zh


def main():
    args = parse_args()
    lines = Path(args.md).read_text(encoding="utf-8").split("\n")
    title_zh, subtitle_zh, abstract_index, body_index, reference_index, keywords_zh = scan_structure(lines)
    if body_index is None or reference_index is None:
        raise SystemExit("the draft is missing its body or its reference section")
    abstract_parts = []
    if abstract_index is not None:
        for line in lines[abstract_index + 1:body_index]:
            stripped = line.strip()
            if not stripped or stripped == "---":
                continue
            if stripped.startswith("**关键词**"):
                continue
            abstract_parts.append(stripped)
    abstract_zh = "".join(abstract_parts)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = TNR
    normal.font.size = Pt(BODY_SIZE)
    section = doc.sections[0]
    section.page_width = Cm(PAGE_W_CM)
    section.page_height = Cm(PAGE_H_CM)
    section.left_margin = Cm(MARGIN_SIDE_CM)
    section.right_margin = Cm(MARGIN_SIDE_CM)
    section.top_margin = Cm(MARGIN_TOP_CM)
    section.bottom_margin = Cm(MARGIN_BOTTOM_CM)
    build_front_matter(doc, title_zh, subtitle_zh, abstract_zh, keywords_zh)
    figures, tables = render_body(doc, lines, body_index, reference_index)
    ack = doc.add_paragraph()
    style_paragraph(ack, before=10.0, after=10.0)
    add_text(ack, "**致谢：**" + ACK, SMALL_SIZE, TNR, FANG)
    center_heading(doc, "参  考  文  献")
    for line in lines[reference_index + 1:]:
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        if stripped.startswith("*") and not stripped.startswith("**"):
            continue
        if NUM_LIST_RE.match(stripped):
            add_paragraph(doc, stripped, size=SIX_SIZE, indent=False,
                          hanging=12.0, line_pt=REF_LINE_PT)
        else:
            add_paragraph(doc, stripped, size=SIX_SIZE, indent=False, after=2.0,
                          line_pt=REF_LINE_PT)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    heights = [f[2] for f in figures] or [0.0]
    widths = [f[1] for f in figures] or [0.0]
    print("saved " + str(out))
    print("paragraphs " + str(len(doc.paragraphs)) + " | tables " + str(tables)
          + " | figures " + str(len(figures)))
    print("usable page box " + str(round(USABLE_W_CM, 2)) + " x "
          + str(round(USABLE_H_CM, 2)) + " cm | largest figure "
          + str(round(max(widths), 2)) + " x " + str(round(max(heights), 2)) + " cm")


if __name__ == "__main__":
    main()
