"""KPI SI Fig. S20 / S21 shortlist extraction: 15 + 14 compounds, 29 rows.

Source
------
Y.-C. Gao, Y.-H. Yuan, S. Huang, N. Yao, L. Yu, Y.-P. Chen, Q. Zhang, X. Chen,
"A Knowledge-Data Dual-Driven Framework for Predicting the Molecular Properties
of Rechargeable Battery Electrolytes", Angew. Chem. Int. Ed. 2025, 64,
e202416506, DOI 10.1002/anie.202416506 -- the 12-page main text and the 64-page
Supporting Information, both read from local copies of the publication.

What is extracted
-----------------
Section 11 of the SI screens the QM9 pool down to two shortlists this project
wants to cross-check: 15 molecules that carry a CAS registry number (SI Fig.
S20) and 14 that do not (SI Fig. S21). This probe turns both figures into one
machine-readable table holding, per row, the shortlist, the rank inside the
figure, the CAS ID, the SMILES, the molecular weight, the melting, boiling and
flash points, and the figure and page the row was read from.

Why the compound blocks are transcribed by hand
-----------------------------------------------
The SI does have a text layer (64 pages, 43,929 characters) but it carries the
captions only. Each figure page holds a single full-page raster image and no
text objects at all for the molecular blocks, and a regex over the whole SI
finds no CAS-number-shaped string anywhere: the CAS IDs exist only as pixels on
SI page SI31 and the SMILES only as pixels on SI32. A coordinate-aware text
extractor has nothing to read there, so the 29 rows below are transcribed by
eye from the embedded page images. The transcription is therefore pinned as
module data instead of parsed, and a swapped SI is caught by EXPECTED_SI_SHA256
rather than silently changing the table.

What the SI does not print, and what is therefore left empty
------------------------------------------------------------
* molwt: neither figure prints a molecular weight. The section 11 prose quotes
  the screening gate (Molwt < 600) but no per-molecule value, so this column is
  empty for all 29 rows and is not back-filled from RDKit. RDKit-derived masses
  are reported separately, under derived_not_from_si, precisely so that they
  cannot be mistaken for SI values.
* smiles: Fig. S20 prints a skeletal formula and a CAS ID and never a SMILES,
  so the 15 rows of that shortlist carry an empty smiles.
* cas: Fig. S21 prints a skeletal formula and a SMILES and never a CAS ID, so
  the 14 rows of that shortlist carry an empty cas. This is not an extraction
  failure. The SI's own section 11 screening paragraph, the main-text abstract
  and the main-text results section all say the second shortlist is the one
  *without* CAS ID (the 20 CAS-less survivors were scored for retrosynthetic
  accessibility and 14 were kept). Fig. S21's caption, which reads "Fourteen
  molecules with CAS ID ... SMILES ... are listed", contradicts all three and
  is treated here as an SI typesetting error.

Discipline
----------
* Compilation, not data. source_kind is compilation_from_published_si,
  redistributable is false and usage is cross_check_only, and those three
  fields ride on every CSV row as well as on the summary. This table must never
  enter the frozen pipeline, and it is not a redistributable dataset.
* Paper-claimed numbers stay claimed. The cascade 133,885 -> 51,001 -> 13,155
  -> 3,619 -> 35 -> 15 + 14 is recorded as paper_declared_cascade with
  recomputed_by_this_project = false. This repository rebuilds neither the QM9
  pool nor the SOTA MP/BP/FP predictions, so not one level of the funnel is
  verified here. Where the SI and the main text disagree -- the main text's
  Figure 5 caption quotes 250/450/380 K instead of the SI's 230/430/360 K --
  the SI text wins and the difference is logged.
* No PDF text dump leaves this probe. Only the CSV, the summary and the report
  are written; the page rasters behind the manual transcription live in the
  temp directory and are not an artefact of this script.
* Offline. The probe reads local files only and makes no network call.

Usage
-----
    python probes/kpi_shortlist_extraction.py            # write CSV + summary + report
    python probes/kpi_shortlist_extraction.py --check     # re-derive and compare to disk
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CSV = REPOSITORY_ROOT / "data" / "reference" / "kpi_15_14_shortlists.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "kpi_shortlist_extraction_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "kpi_shortlist_extraction.md"

# Both source PDFs are local copies of the publication.  .gitignore drops every
# *.pdf, so neither is committed: they are looked up by name under the user's
# Downloads directory, with an environment override for other machines.
DOWNLOAD_DIR = Path.home() / "Downloads"
SI_PDF_NAME = "anie202416506-sup-0001-misc_information.pdf"
MAIN_TEXT_PDF_GLOB = "Angew Chem Int Ed - 2024 - Gao*.pdf"
SI_PDF_ENV = "KPI_SI_PDF"
MAIN_TEXT_PDF_ENV = "KPI_MAIN_TEXT_PDF"

# Pinned so a re-downloaded or re-typeset SI cannot silently change the table.
EXPECTED_SI_SHA256 = "5609c5edb51928296359311c02049a6c4a2538c1312b851886c99812acba51c8"
EXPECTED_SI_PAGES = 64

CSV_COLUMNS: tuple[str, ...] = (
    "shortlist",
    "rank",
    "cas",
    "smiles",
    "molwt",
    "mp_k",
    "bp_k",
    "fp_k",
    "source_figure",
    "source_page",
    "source_page_label",
    "source_kind",
    "redistributable",
    "usage",
    "notes",
)

SOURCE_KIND = "compilation_from_published_si"
REDISTRIBUTABLE = "false"
USAGE = "cross_check_only"
DISCIPLINE_STATEMENT = (
    "本表逐字转录自已发表的 Angew. Chem. Int. Ed. 补充材料图 S20 / S21，属汇编级证据，"
    "只用于交叉核对（usage=cross_check_only）。本表不得当作可再分发的数据集"
    "（redistributable=false），也不得作为本仓数据集的来源注入冻结管线。"
)

# The screening gates quoted by SI section 11.  They are used here only to check
# that the 29 transcribed rows are internally consistent with the published
# funnel; they are not recomputed.
SCREENING_GATES: dict[str, float] = {
    "mp_below_k": 230.0,
    "bp_above_k": 430.0,
    "fp_above_k": 360.0,
}

# (shortlist, rank) pairs whose printed flash point is not strictly below the
# printed boiling point.  Pinned as a set so a second such row cannot slip in
# unnoticed: the exception is the finding, not the rule.
ALLOWED_FP_NOT_BELOW_BP: frozenset[tuple[int, int]] = frozenset({(15, 5)})

TICK = "\u0060"


def code(text: str) -> str:
    """Wrap a token in a Markdown inline-code span."""

    return TICK + text + TICK


@dataclass(frozen=True)
class FigureSource:
    """Where one shortlist was printed and what its blocks carry."""

    shortlist: int
    figure: str
    page: int
    page_label: str
    caption_regex: str
    printed_fields: tuple[str, ...]
    extraction: str


FIGURE_SOURCES: tuple[FigureSource, ...] = (
    FigureSource(
        shortlist=15,
        figure="Figure S20",
        page=32,
        page_label="SI31",
        caption_regex=r"Figure\s*S\s*20\.",
        printed_fields=("skeletal formula", "CAS ID", "MP", "BP", "FP"),
        extraction="目视转录自 PDF 第 32 页的整页栅格图（该页文字层只有图注）",
    ),
    FigureSource(
        shortlist=14,
        figure="Figure S21",
        page=33,
        page_label="SI32",
        caption_regex=r"Figure\s*S\s*21\.",
        printed_fields=("skeletal formula", "SMILES", "MP", "BP", "FP"),
        extraction="目视转录自 PDF 第 33 页的整页栅格图（该页文字层只有图注）",
    ),
)


@dataclass(frozen=True)
class ShortlistEntry:
    """One transcribed shortlist row.  Numeric fields keep the printed form."""

    shortlist: int
    rank: int
    cas: str
    smiles: str
    mp_k: str
    bp_k: str
    fp_k: str
    note: str


# Fig. S20, SI page SI31 (PDF page 32): 15 molecules, printed five per row in
# reading order, each block a skeletal formula over "CAS: / MP / BP / FP".
# Transcribed from the embedded page image; see the module docstring for why
# there is no parser behind this literal.
S20_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("96-48-0", "228.2", "477.2", "371.5"),
    ("108-32-7", "224.4", "514.8", "389.2"),
    ("4437-69-8", "222.6", "504.3", "369.8"),
    ("4437-70-1", "217.3", "513.9", "367.4"),
    ("4437-85-8", "216.9", "514.2", "514.2"),
    ("6975-71-9", "227.8", "491.8", "365.0"),
    ("623-35-8", "220.9", "493.2", "384.9"),
    ("17611-82-4", "220.8", "499.5", "381.0"),
    ("4172-97-8", "228.9", "503.3", "372.8"),
    ("32091-48-8", "211.0", "508.8", "383.3"),
    ("15074-49-4", "221.2", "509.7", "374.7"),
    ("4553-62-2", "220.8", "508.6", "380.6"),
    ("16525-39-6", "228.7", "519.4", "383.2"),
    ("6959-71-3", "202.6", "467.2", "361.4"),
    ("35633-50-2", "221.6", "490.1", "368.1"),
)

S20_NOTES: dict[int, str] = {
    5: "SI 把这一块的 FP 印成 514.2 K，与同一块的 BP 514.2 K 完全相等；照实转录，未改写。",
}

# Fig. S21, SI page SI32 (PDF page 33): 14 molecules, printed five per row in
# reading order, each block a skeletal formula over "SMILES / MP / BP / FP".
S21_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("O=COCC1COCO1", "229.2", "458.3", "360.6"),
    ("N#CCCCC1CCC1", "225.4", "489.3", "362.0"),
    ("N#CCCC1=CCCC1", "223.9", "492.6", "363.2"),
    ("N#CCCC1(CC1)C#N", "228.0", "525.0", "387.0"),
    ("CCC(CC#N)CC#N", "222.3", "513.8", "381.3"),
    ("CC(CCC#N)CC#N", "219.3", "519.2", "382.0"),
    ("CCC(CCC#N)C#N", "223.3", "514.2", "381.8"),
    ("C#CCCOCCCC#N", "224.7", "477.2", "361.9"),
    ("CC(COCC#N)C#N", "226.4", "497.7", "378.4"),
    ("CC(CCOC=O)C#N", "227.7", "474.8", "361.7"),
    ("CC(COC=O)CC#N", "221.4", "476.7", "363.8"),
    ("CC(CCC#N)C1CO1", "226.1", "499.2", "360.7"),
    ("N#CCCOC1CCC1", "226.4", "476.5", "365.8"),
    ("CC1COCC1CC#N", "228.7", "492.9", "361.0"),
)

S21_NOTES: dict[int, str] = {}

NOTE_NO_SMILES = "SI 图 S20 只画骨架式、不印 SMILES，故此格留空，未由本仓回填。"
NOTE_NO_CAS = "SI 图 S21 不印 CAS ID，故此格留空（论文正文与 SI 均称这一组 14 个不带 CAS）。"

# The paper's own funnel, quoted in SI section 11.  Pinned verbatim as claimed
# numbers: see paper_declared_cascade_provenance for the not-recomputed flag.
PAPER_DECLARED_CASCADE: dict[str, Any] = {
    "qm9_molecules_collected": 133885,
    "after_structural_screening": 51001,
    "mp_below_230k": 13155,
    "bp_above_430k": 3619,
    "fp_above_360k": 35,
    "with_cas_id": 15,
    "without_cas_id": 20,
    "after_retrosynthetic_accessibility_gt_0.9": 14,
    "final_shortlists": "15 + 14",
    "structural_screening_rules": (
        "剔除含活泼氢官能团的分子（-OH、-COOH）；Molwt < 600；#Heavy < 30",
    ),
    "staged_thresholds_k": {"mp_below": 230, "bp_above": 430, "fp_above": 360},
}

SI_CASCADE_PAGE_MARKER = "High-throughput screening"

CASCADE_PATTERNS: dict[str, str] = {
    "qm9_molecules_collected": r"A total of\s+([\d,]+)\s+molecules from the QM9",
    "after_structural_screening": r"resulting in\s+([\d,]+)\s+molecules\s+remaining",
    "staged_counts": r"leaving\s+([\d,]+),\s*([\d,]+),\s*and\s+([\d,]+)\s+molecules",
    "staged_thresholds": r"MPs below\s+(\d+)\s*K,\s*BPs above\s+(\d+)\s*K,\s*and FPs above\s+(\d+)\s*K",
    "cas_split": r"which include\s+(\d+)\s+and\s+(\d+)\s+molecules with\s+and without CAS ID",
    "after_sa_score": r"ultimately\s+(\d+)\s+molecules were identified",
    "molwt_gate": r"Molwt to less than\s+(\d+)",
    "heavy_gate": r"#Heavy to less than\s+(\d+)",
}

CAS_PATTERN = re.compile(r"^(?P<body>\d{2,7})-(?P<group>\d{2})-(?P<check>\d)$")
PAGE_LABEL_PATTERN = re.compile(r"^\s*(SI\d+)")


# ---------------------------------------------------------------------------
# Transcribed table.
# ---------------------------------------------------------------------------


def shortlist_entries() -> tuple[ShortlistEntry, ...]:
    """Return the 29 transcribed rows, shortlist 15 first, rank order inside."""

    entries: list[ShortlistEntry] = []
    for rank, (cas, mp_k, bp_k, fp_k) in enumerate(S20_ROWS, start=1):
        entries.append(
            ShortlistEntry(
                shortlist=15,
                rank=rank,
                cas=cas,
                smiles="",
                mp_k=mp_k,
                bp_k=bp_k,
                fp_k=fp_k,
                note=S20_NOTES.get(rank, NOTE_NO_SMILES),
            )
        )
    for rank, (smiles, mp_k, bp_k, fp_k) in enumerate(S21_ROWS, start=1):
        entries.append(
            ShortlistEntry(
                shortlist=14,
                rank=rank,
                cas="",
                smiles=smiles,
                mp_k=mp_k,
                bp_k=bp_k,
                fp_k=fp_k,
                note=S21_NOTES.get(rank, NOTE_NO_CAS),
            )
        )
    return tuple(entries)


def csv_rows(entries: Sequence[ShortlistEntry]) -> list[dict[str, str]]:
    """Flatten the entries into CSV rows, one dict per row."""

    sources = {source.shortlist: source for source in FIGURE_SOURCES}
    rows: list[dict[str, str]] = []
    for entry in entries:
        source = sources[entry.shortlist]
        rows.append(
            {
                "shortlist": str(entry.shortlist),
                "rank": str(entry.rank),
                "cas": entry.cas,
                "smiles": entry.smiles,
                "molwt": "",
                "mp_k": entry.mp_k,
                "bp_k": entry.bp_k,
                "fp_k": entry.fp_k,
                "source_figure": source.figure,
                "source_page": str(source.page),
                "source_page_label": source.page_label,
                "source_kind": SOURCE_KIND,
                "redistributable": REDISTRIBUTABLE,
                "usage": USAGE,
                "notes": entry.note,
            }
        )
    return rows


def build_csv_text(entries: Sequence[ShortlistEntry]) -> str:
    """Render the table as CSV text with LF endings and no trailing blank line."""

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(CSV_COLUMNS),
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in csv_rows(entries):
        writer.writerow(row)
    return buffer.getvalue()


def cas_checksum_ok(cas: str) -> bool:
    """Validate a CAS registry number with the standard check-digit rule."""

    match = CAS_PATTERN.match(cas)
    if not match:
        return False
    digits = (match["body"] + match["group"])[::-1]
    total = sum(int(digit) * (position + 1) for position, digit in enumerate(digits))
    return total % 10 == int(match["check"])


# ---------------------------------------------------------------------------
# SI text layer.
# ---------------------------------------------------------------------------


def read_pdf_pages(pdf_path: Path) -> list[str]:
    """Return the extracted text of every page of a PDF, one string per page."""

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def file_sha256(pdf_path: Path) -> str:
    digest = hashlib.sha256()
    with open(pdf_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_si_pdf(override: str | None) -> Path | None:
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    from_env = os.environ.get(SI_PDF_ENV)
    if from_env and Path(from_env).is_file():
        return Path(from_env)
    candidate = DOWNLOAD_DIR / SI_PDF_NAME
    return candidate if candidate.is_file() else None


def resolve_main_text_pdf(override: str | None) -> Path | None:
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    from_env = os.environ.get(MAIN_TEXT_PDF_ENV)
    if from_env and Path(from_env).is_file():
        return Path(from_env)
    matches = sorted(DOWNLOAD_DIR.glob(MAIN_TEXT_PDF_GLOB))
    return matches[0] if matches else None


def find_page(pages: Sequence[str], marker: str) -> int:
    for index, text in enumerate(pages):
        if marker in text:
            return index
    return -1


def page_label(page_text: str) -> str:
    match = PAGE_LABEL_PATTERN.match(page_text)
    return match.group(1) if match else ""


def parse_caption(pages: Sequence[str], source: FigureSource) -> dict[str, Any]:
    """Return the printed caption of one figure, taken from the text layer."""

    pattern = re.compile(source.caption_regex)
    for index, text in enumerate(pages, start=1):
        match = pattern.search(text)
        if not match:
            continue
        label = page_label(text)
        caption = re.sub(r"\s+", " ", text[match.start() :]).strip()
        if label and caption.endswith(label):
            caption = caption[: -len(label)].strip()
        return {
            "found": True,
            "pdf_page": index,
            "page_label_found": label,
            "caption": caption,
        }
    return {"found": False, "pdf_page": None, "page_label_found": "", "caption": ""}


def parse_si_cascade(pages: Sequence[str]) -> dict[str, Any]:
    """Read the section 11 funnel out of the SI text layer.

    Returns the numbers exactly as the SI prints them, plus the verbatim
    paragraph they were read from.  Nothing here is a recomputation.
    """

    index = find_page(pages, SI_CASCADE_PAGE_MARKER)
    if index < 0:
        return {"found": False}
    text = pages[index]
    body = re.sub(r"\s+", " ", text)
    found: dict[str, Any] = {
        "found": True,
        "pdf_page": index + 1,
        "page_label": page_label(text),
        "verbatim_paragraph": body.strip(),
    }
    for key, pattern in CASCADE_PATTERNS.items():
        match = re.search(pattern, text)
        if match is None:
            found[key] = None
            continue
        groups = match.groups()
        if len(groups) == 1:
            found[key] = int(groups[0].replace(",", ""))
        else:
            found[key] = tuple(int(value.replace(",", "")) for value in groups)
    return found


def parse_main_text_gates(pages: Sequence[str]) -> dict[str, Any]:
    """Read the two threshold triples the main text prints for the screening."""

    body = re.sub(r"\s+", " ", "\n".join(pages))
    result: dict[str, Any] = {}
    figure_caption = re.search(
        r"an MP below\s+(\d+)\s*K,?\s*a BP above\s+(\d+)\s*K,?\s*and an FP above\s+(\d+)\s*K",
        body,
    )
    result["figure5_caption_k"] = (
        tuple(int(value) for value in figure_caption.groups()) if figure_caption else None
    )
    results_section = re.search(
        r"MP smaller than\s*(\d+)\s*K,\s*BP larger than\s*(\d+)\s*K,"
        r"\s*and FP larger than\s*(\d+)\s*K",
        body,
    )
    result["results_section_k"] = (
        tuple(int(value) for value in results_section.groups()) if results_section else None
    )
    abstract = re.search(r"Fifteen and fourteen molecules, with and without", body)
    result["abstract_states_second_shortlist_has_no_cas"] = abstract is not None
    return result


# ---------------------------------------------------------------------------
# Cross-checks.
# ---------------------------------------------------------------------------


def cascade_cross_checks(
    si_cascade: Mapping[str, Any],
    main_text: Mapping[str, Any],
    entries: Sequence[ShortlistEntry],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(check_id: str, status: str, detail: str) -> None:
        checks.append({"id": check_id, "status": status, "detail": detail})

    if not si_cascade.get("found"):
        add(
            "si_vs_handoff_expectation",
            "skipped",
            "SI 文本层不可用，无法与派单给的级联数字对表；paper_declared_cascade 仍按 SI 印刷值登记。",
        )
    else:
        staged = si_cascade.get("staged_counts") or (None, None, None)
        thresholds = si_cascade.get("staged_thresholds") or (None, None, None)
        si_tuple = (
            si_cascade.get("qm9_molecules_collected"),
            si_cascade.get("after_structural_screening"),
            staged[0],
            staged[1],
            staged[2],
        )
        expected_tuple = (
            PAPER_DECLARED_CASCADE["qm9_molecules_collected"],
            PAPER_DECLARED_CASCADE["after_structural_screening"],
            PAPER_DECLARED_CASCADE["mp_below_230k"],
            PAPER_DECLARED_CASCADE["bp_above_430k"],
            PAPER_DECLARED_CASCADE["fp_above_360k"],
        )
        add(
            "si_vs_handoff_expectation",
            "match" if si_tuple == expected_tuple else "mismatch",
            "SI 印刷值 " + " -> ".join(str(value) for value in si_tuple),
        )
        add(
            "si_vs_handoff_thresholds",
            "match" if thresholds == (230, 430, 360) else "mismatch",
            "SI 印刷阈值 MP<{} K / BP>{} K / FP>{} K，与派单给的同一组阈值".format(*thresholds),
        )
        add(
            "si_cas_split_recorded",
            "match" if si_cascade.get("cas_split") == (15, 20) else "mismatch",
            "SI 明写 35 个再拆成 15（带 CAS）与 20（不带 CAS），这 20 个再过 SAscore>0.9 得 "
            + str(si_cascade.get("after_sa_score"))
            + " 个；派单只写了 15+14，未写 20 这一中间层。",
        )

    figure_gates = main_text.get("figure5_caption_k")
    results_gates = main_text.get("results_section_k")
    if figure_gates is None and results_gates is None:
        add("main_text_vs_si_thresholds", "skipped", "正文 PDF 不可用，未做正文对表。")
    else:
        agree = results_gates == (230, 430, 360) and figure_gates == (250, 450, 380)
        add(
            "main_text_vs_si_thresholds",
            "documented_difference" if agree else "unexpected",
            "正文结果段印 MP<230 K / BP>430 K / FP>360 K（与 SI 一致），"
            "但正文 Figure 5 图注印 MP<250 K / BP>450 K / FP>380 K；"
            "本报告以 SI 实际文字 230/430/360 为准。",
        )

    gates = SCREENING_GATES
    offenders = [
        f"{entry.shortlist}/{entry.rank}"
        for entry in entries
        if not (
            float(entry.mp_k) < gates["mp_below_k"]
            and float(entry.bp_k) > gates["bp_above_k"]
            and float(entry.fp_k) > gates["fp_above_k"]
        )
    ]
    add(
        "shortlists_satisfy_the_published_gates",
        "pass" if not offenders else "fail",
        "29 行全部满足 MP<230 K、BP>430 K、FP>360 K；不满足的行："
        + (", ".join(offenders) if offenders else "无"),
    )
    add(
        "main_text_abstract_cas_split",
        "match" if main_text.get("abstract_states_second_shortlist_has_no_cas") else "unavailable",
        "正文摘要写 Fifteen and fourteen molecules, with and without CAS ID, respectively："
        "15 个带 CAS、14 个不带，与 SI 图 S21 只印 SMILES 一致，与其图注自称 with CAS ID 矛盾。",
    )
    return checks


def derived_smiles_block(entries: Sequence[ShortlistEntry]) -> dict[str, Any]:
    """RDKit is used only to sanity-check the transcribed SMILES.

    The resulting masses are this repository's numbers, not the SI's; they live
    here so that nobody is tempted to put them in the molwt column.
    """

    smiles = [entry.smiles for entry in entries if entry.smiles]
    block: dict[str, Any] = {
        "label": "本仓派生值，不是 SI 印刷值，绝不写进 CSV 的 molwt 列",
        "checked": len(smiles),
    }
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors
    except ImportError as exc:  # pragma: no cover - rdkit is a declared dependency
        block["available"] = False
        block["reason"] = f"rdkit unavailable: {exc}"
        return block

    masses: list[float] = []
    unparsed: list[str] = []
    for value in smiles:
        molecule = Chem.MolFromSmiles(value)
        if molecule is None:
            unparsed.append(value)
            continue
        masses.append(round(Descriptors.MolWt(molecule), 3))
    block["available"] = True
    block["parsed"] = len(masses)
    block["unparsed"] = unparsed
    block["molwt_min"] = min(masses) if masses else None
    block["molwt_max"] = max(masses) if masses else None
    block["all_below_the_600_gate"] = bool(masses) and max(masses) < 600.0
    return block


def validate_entries(entries: Sequence[ShortlistEntry]) -> dict[str, Any]:
    """Machine-check the transcription.  No PDF and no network are needed."""

    checks: list[dict[str, str]] = []
    problems: list[str] = []

    def record(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            problems.append(f"{check_id}: {detail}")

    record("row_count_is_29", len(entries) == 29, f"行数 = {len(entries)}")

    counts = Counter(entry.shortlist for entry in entries)
    record(
        "shortlist_split_is_15_14",
        counts.get(15) == 15 and counts.get(14) == 14,
        f"shortlist 计数 = {dict(sorted(counts.items()))}",
    )

    ranks_ok = all(
        sorted(entry.rank for entry in entries if entry.shortlist == size)
        == list(range(1, size + 1))
        for size in (15, 14)
    )
    record("ranks_run_1_to_n_per_shortlist", ranks_ok, "每个 shortlist 的 rank 为 1..n 连号")

    sources = {source.shortlist: source for source in FIGURE_SOURCES}
    bad_source = [
        f"{entry.shortlist}/{entry.rank}"
        for entry in entries
        if not sources[entry.shortlist].figure or sources[entry.shortlist].page <= 0
    ]
    record(
        "every_row_carries_figure_and_page",
        not bad_source,
        "source_figure / source_page / source_page_label 全部非空；缺项行："
        + (", ".join(bad_source) if bad_source else "无"),
    )

    def numeric_ok(field: str) -> list[str]:
        broken: list[str] = []
        for entry in entries:
            try:
                float(getattr(entry, field))
            except ValueError:
                broken.append(f"{entry.shortlist}/{entry.rank}={getattr(entry, field)}")
        return broken

    for field in ("mp_k", "bp_k", "fp_k"):
        broken = numeric_ok(field)
        record(f"{field}_is_numeric_on_every_row", not broken, "异常值：" + str(broken))

    offenders = [
        f"{entry.shortlist}/{entry.rank}"
        for entry in entries
        if float(entry.fp_k) >= float(entry.bp_k)
        and (entry.shortlist, entry.rank) not in ALLOWED_FP_NOT_BELOW_BP
    ]
    record(
        "fp_below_bp_except_the_pinned_exception",
        not offenders,
        "除已登记异常外每行 FP < BP；越界行：" + (", ".join(offenders) if offenders else "无"),
    )

    exceptions_seen = [
        (entry.shortlist, entry.rank)
        for entry in entries
        if float(entry.fp_k) >= float(entry.bp_k)
    ]
    record(
        "the_pinned_exception_is_still_present",
        set(exceptions_seen) == set(ALLOWED_FP_NOT_BELOW_BP),
        f"实际 FP>=BP 的行 = {sorted(exceptions_seen)}",
    )

    wrong_cas = [entry.cas for entry in entries if entry.shortlist == 15 and not entry.cas]
    wrong_cas += [entry.cas for entry in entries if entry.shortlist == 14 and entry.cas]
    record(
        "cas_filled_exactly_on_shortlist_15",
        not wrong_cas,
        "短名单 15 的 15 行全部有 CAS；短名单 14 的 14 行全部为空（SI 未印）。",
    )

    bad_checksum = [entry.cas for entry in entries if entry.cas and not cas_checksum_ok(entry.cas)]
    record(
        "cas_check_digits_all_valid",
        not bad_checksum,
        "15 个 CAS 全部通过标准校验位算法；未通过："
        + (", ".join(bad_checksum) if bad_checksum else "无"),
    )

    wrong_smiles = [entry.smiles for entry in entries if entry.shortlist == 14 and not entry.smiles]
    wrong_smiles += [entry.smiles for entry in entries if entry.shortlist == 15 and entry.smiles]
    record(
        "smiles_filled_exactly_on_shortlist_14",
        not wrong_smiles,
        "短名单 14 的 14 行全部有 SMILES；短名单 15 的 15 行全部为空（SI 只印骨架式）。",
    )

    cas_duplicates = [
        value for value, seen in Counter(entry.cas for entry in entries if entry.cas).items() if seen > 1
    ]
    smiles_duplicates = [
        value
        for value, seen in Counter(entry.smiles for entry in entries if entry.smiles).items()
        if seen > 1
    ]
    record(
        "no_duplicate_cas_or_smiles",
        not cas_duplicates and not smiles_duplicates,
        f"重复 CAS = {cas_duplicates}；重复 SMILES = {smiles_duplicates}",
    )

    derived = derived_smiles_block(entries)
    if derived.get("available"):
        record(
            "transcribed_smiles_parse_with_rdkit",
            not derived["unparsed"] and derived["parsed"] == 14,
            "RDKit 解析 {} / 14 条 SMILES；失败：{}".format(derived["parsed"], derived["unparsed"]),
        )
        record(
            "derived_masses_respect_the_600_gate",
            derived["all_below_the_600_gate"],
            "RDKit 派生的分子量区间 {} - {}（非 SI 印刷值）".format(
                derived["molwt_min"], derived["molwt_max"]
            ),
        )
    else:
        record("transcribed_smiles_parse_with_rdkit", True, "RDKit 不可用，跳过（不算失败）")

    return {"checks": checks, "problems": problems, "derived": derived}


# ---------------------------------------------------------------------------
# Summary and report.
# ---------------------------------------------------------------------------


def _field_coverage(entries: Sequence[ShortlistEntry]) -> dict[str, Any]:
    total = len(entries)

    def block(values: Sequence[str], printed_in_si: str, note: str) -> dict[str, Any]:
        filled = sum(1 for value in values if value.strip())
        return {
            "non_empty": filled,
            "rows": total,
            "non_empty_rate": round(filled / total, 4) if total else 0.0,
            "printed_in_si": printed_in_si,
            "note": note,
        }

    cas_filled = sum(1 for entry in entries if entry.cas)
    smiles_filled = sum(1 for entry in entries if entry.smiles)
    figure_values = [
        source.figure for source in FIGURE_SOURCES for _ in range(15 if source.shortlist == 15 else 14)
    ]
    page_values = [
        str(source.page) for source in FIGURE_SOURCES for _ in range(15 if source.shortlist == 15 else 14)
    ]
    return {
        "cas": block(
            [entry.cas for entry in entries],
            "Fig. S20 每块印 CAS ID；Fig. S21 一块都不印",
            f"非空 {cas_filled}/29；100% 只成立于短名单 15 这一半，短名单 14 的 CAS 在 SI 里不存在。",
        ),
        "smiles": block(
            [entry.smiles for entry in entries],
            "Fig. S21 每块印 SMILES；Fig. S20 只画骨架式",
            f"非空 {smiles_filled}/29；S20 的 15 行没有印刷 SMILES，本表不用结构感知回填。",
        ),
        "molwt": block(
            [""] * total,
            "两图都不印",
            "0/29；SI 只印了 Molwt < 600 这道闸门，没有逐分子数值。",
        ),
        "mp_k": block(
            [entry.mp_k for entry in entries], "两图都印", "29/29，按图上的印刷形式整字转录。"
        ),
        "bp_k": block(
            [entry.bp_k for entry in entries], "两图都印", "29/29，按图上的印刷形式整字转录。"
        ),
        "fp_k": block(
            [entry.fp_k for entry in entries], "两图都印", "29/29，按图上的印刷形式整字转录。"
        ),
        "source_figure": block(figure_values, "两图都印", "29/29。"),
        "source_page": block(
            page_values,
            "两图都印",
            "29/29；数值是 PDF 页码（1 基），SI 自己印的页签另存一列。",
        ),
    }


def build_summary(
    entries: Sequence[ShortlistEntry],
    *,
    si_pages: Sequence[str] | None,
    si_pdf: Path | None,
    main_pages: Sequence[str] | None,
    main_pdf: Path | None,
    csv_text: str,
) -> dict[str, Any]:
    si_cascade = parse_si_cascade(si_pages) if si_pages else {"found": False}
    main_text = parse_main_text_gates(main_pages) if main_pages else {}
    validation = validate_entries(entries)
    si_hash = file_sha256(si_pdf) if si_pdf else ""
    si_chars = sum(len(page) for page in si_pages) if si_pages else 0

    captions: dict[str, Any] = {}
    for source in FIGURE_SOURCES:
        captions[str(source.shortlist)] = (
            parse_caption(si_pages, source) if si_pages else {"found": False, "caption": ""}
        )

    cascade_provenance = {
        "source_page": si_cascade.get("pdf_page"),
        "source_page_label": si_cascade.get("page_label", ""),
        "verbatim_paragraph": si_cascade.get("verbatim_paragraph", ""),
        "recomputed_by_this_project": False,
        "note": (
            "以上全部是论文声称值，未经我方复算：本仓不复现 QM9 的 133,885 分子池，"
            "也不复现 SOTA 模型的 MP/BP/FP 预测，因此漏斗的任何一级都无法验证。"
            "本探针只把它们登记下来，供与 SI 印刷文字对表。"
        ),
    }

    anomalies: list[dict[str, Any]] = [
        {
            "id": "fp_equals_bp_on_shortlist_15_rank_5",
            "rows": ["15/5"],
            "detail": (
                "CAS 4437-85-8 那一块把 FP 印成 514.2 K，与同一块的 BP 514.2 K 相等；"
                "其余 28 行都满足 FP < BP。本表照实转录该印刷值、未做修正，"
                "并把这一对 (15, 5) 钉成唯一允许的例外。"
            ),
        },
        {
            "id": "figure_s21_caption_contradicts_the_screening_text",
            "rows": ["14/*"],
            "detail": (
                "Fig. S21 图注自称 Fourteen molecules with CAS ID，但同页每块印的是 SMILES 而不是 "
                "CAS ID；SI §11、正文摘要与正文结果段都写这 14 个 without CAS ID。"
                "本表以 SI §11 与正文的叙述为准，Fig. S21 的图注记为 SI 自相矛盾。"
            ),
        },
        {
            "id": "figure_s21_caption_spacing",
            "rows": ["14/*"],
            "detail": "SI 把该图注排版成 Figure S 21.（S 与 21 之间带空格），本表统一写作 Figure S21。",
        },
        {
            "id": "main_text_figure5_caption_quotes_other_thresholds",
            "rows": [],
            "detail": (
                "正文 Figure 5 图注写 MP<250 K / BP>450 K / FP>380 K，"
                "而 SI §11 与正文结果段写 230/430/360 K。本报告以 SI 实际文字为准。"
            ),
        },
        {
            "id": "cross_figure_identity_not_judged",
            "rows": [],
            "detail": (
                "Fig. S20 只有骨架式、没有 SMILES，所以本表没有对两个短名单做跨图去重或同一性判定。"
                "任何跨图去重都必须先有结构感知流程把 S20 的 SMILES 补出来，那一步不在本次范围内。"
            ),
        },
        {
            "id": "molwt_never_printed",
            "rows": [],
            "detail": "两图都不印分子量，molwt 列 29 行全空；本表不用 RDKit 回填。",
        },
    ]

    return {
        "schema_version": 1,
        "probe": "kpi_shortlist_extraction",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "paper": (
                "Gao, Yuan, Huang, Yao, Yu, Chen, Zhang, Chen, Angew. Chem. Int. Ed. 2025, 64, "
                "e202416506, DOI 10.1002/anie.202416506"
            ),
            "si_pdf": {
                "path": str(si_pdf) if si_pdf else None,
                "sha256": si_hash,
                "sha256_matches_pin": si_hash == EXPECTED_SI_SHA256,
                "pages": len(si_pages) if si_pages else None,
                "text_layer_chars": si_chars,
            },
            "main_text_pdf": {
                "path": str(main_pdf) if main_pdf else None,
                "pages": len(main_pages) if main_pages else None,
                "text_layer_chars": sum(len(page) for page in main_pages) if main_pages else 0,
            },
            "shortlist_csv_path": "data/reference/kpi_15_14_shortlists.csv",
            "shortlist_csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        },
        "discipline": {
            "source_kind": SOURCE_KIND,
            "redistributable": REDISTRIBUTABLE == "true",
            "usage": USAGE,
            "statement": DISCIPLINE_STATEMENT,
        },
        "extraction_method": {
            "text_layer": "pypdf 提取 SI 与正文的文字层；SI {} 页 / {} 字符。".format(
                len(si_pages) if si_pages else "?",
                si_chars,
            ),
            "figure_blocks": (
                "图 S20 / S21 的化合物块只存在于栅格图里：两页文字层只有图注，每页只有 1 张整页 "
                "<image>，没有可定位的文字对象，整个 SI 文字层里也没有任何 CAS 号形状的字符串。"
                "因此 29 行由图块目视转录（非 OCR 自动识别）。"
            ),
            "transcription_risk": (
                "人工误读单个数字是主要的残余风险。本探针用五道机检把误读压到可发现："
                "① 29 行且 15/14 分片；② 每行满足 MP<230 K、BP>430 K、FP>360 K；"
                "③ 除已登记的 1 行外每行 FP<BP；④ 15 个 CAS 全过标准校验位算法；"
                "⑤ 14 条 SMILES 全部能被 RDKit 解析。机检能证伪，不能证明与图逐字一致。"
            ),
            "hash_pin": "SI 的 sha256 与 {} 不符会在校验里报出（本次 {}）。".format(
                EXPECTED_SI_SHA256[:16] + "...",
                "一致" if si_hash == EXPECTED_SI_SHA256 else "不一致或不可用",
            ),
            "pdf_text_dump": "本探针不向仓库写任何 PDF 全文或页面转储；只写 CSV、摘要与本报告。",
        },
        "paper_declared_cascade": PAPER_DECLARED_CASCADE,
        "paper_declared_cascade_provenance": cascade_provenance,
        "si_cascade_text_layer": si_cascade,
        "main_text_thresholds": main_text,
        "cascade_cross_checks": cascade_cross_checks(si_cascade, main_text, entries),
        "figure_sources": {
            str(source.shortlist): {
                "figure": source.figure,
                "pdf_page": source.page,
                "page_label": source.page_label,
                "printed_fields": list(source.printed_fields),
                "extraction": source.extraction,
                "caption": captions[str(source.shortlist)].get("caption", ""),
                "caption_found_in_text_layer": captions[str(source.shortlist)].get("found", False),
            }
            for source in FIGURE_SOURCES
        },
        "coverage": {
            "rows": len(entries),
            "by_shortlist": {
                str(size): sum(1 for entry in entries if entry.shortlist == size) for size in (15, 14)
            },
            "fields": _field_coverage(entries),
            "per_shortlist": {
                str(source.shortlist): {
                    "rows": sum(1 for entry in entries if entry.shortlist == source.shortlist),
                    "cas_non_empty": sum(
                        1 for entry in entries if entry.shortlist == source.shortlist and entry.cas
                    ),
                    "smiles_non_empty": sum(
                        1 for entry in entries if entry.shortlist == source.shortlist and entry.smiles
                    ),
                    "molwt_non_empty": 0,
                    "mp_k_non_empty": sum(
                        1 for entry in entries if entry.shortlist == source.shortlist and entry.mp_k
                    ),
                }
                for source in FIGURE_SOURCES
            },
        },
        "derived_not_from_si": validation["derived"],
        "validation": {"checks": validation["checks"], "problems": validation["problems"]},
        "anomalies": anomalies,
        "entries": csv_rows(entries),
    }


def render_report(summary: Mapping[str, Any]) -> str:
    """Render the Markdown report.  The report is a pure function of summary."""

    source = summary["source"]
    discipline = summary["discipline"]
    cascade = summary["paper_declared_cascade"]
    provenance = summary["paper_declared_cascade_provenance"]
    coverage = summary["coverage"]
    figures = summary["figure_sources"]
    lines: list[str] = []
    add = lines.append

    add("# KPI 论文 SI 图 S20 / S21 短名单抠取（15 + 14 = 29 行）")
    add("")
    add(
        "**产物**："
        + code("data/reference/kpi_15_14_shortlists.csv")
        + "（机读表，29 行）、"
        + code("probes/kpi_shortlist_extraction_summary.json")
        + "（摘要）、"
        + code("probes/kpi_shortlist_extraction.py")
        + "（探针）、"
        + code("tests/test_kpi_shortlist_extraction.py")
        + "（单测）。"
    )
    add("")
    add("**论文**：" + source["paper"] + "。")
    add("")
    add(
        "**来源物料**：SI "
        + code("anie202416506-sup-0001-misc_information.pdf")
        + "（"
        + str(source["si_pdf"]["pages"])
        + " 页 / "
        + str(source["si_pdf"]["text_layer_chars"])
        + " 字符，sha256 "
        + (source["si_pdf"]["sha256"][:16] + "..." if source["si_pdf"]["sha256"] else "不可用")
        + "）；正文 12 页，只用于口径对表。两份 PDF 都不入仓（"
        + code(".gitignore")
        + " 排除所有 "
        + code("*.pdf")
        + "）。"
    )
    add("")
    add(
        "**纪律**："
        + code("source_kind=" + discipline["source_kind"])
        + "、"
        + code("redistributable=false")
        + "、"
        + code("usage=" + discipline["usage"])
        + "。"
    )
    add("")
    add("---")
    add("")
    add("## 1 抠取口径")
    add("")
    add(summary["extraction_method"]["text_layer"])
    add("")
    add(summary["extraction_method"]["figure_blocks"])
    add("")
    add("**残余风险**：" + summary["extraction_method"]["transcription_risk"])
    add("")
    add(summary["extraction_method"]["pdf_text_dump"])
    add("")
    add("| 短名单 | 图 | PDF 页 | SI 页签 | 图上印刷的字段 |")
    add("| --- | --- | --- | --- | --- |")
    for size in ("15", "14"):
        block = figures[size]
        add(
            "| {} | {} | {} | {} | {} |".format(
                size,
                block["figure"],
                block["pdf_page"],
                block["page_label"],
                "、".join(block["printed_fields"]),
            )
        )
    add("")
    add("图注（逐字取自 SI 文字层）：")
    add("")
    add("- 短名单 15（" + figures["15"]["figure"] + "）：" + figures["15"]["caption"])
    add("- 短名单 14（" + figures["14"]["figure"] + "）：" + figures["14"]["caption"])
    add("")
    add("---")
    add("")
    add("## 2 逐行清单（29 行）")
    add("")
    add("rank 是图内阅读顺序：先左右、再上下。数值一律保持图上的印刷形式。")
    add("")
    add("### 2.1 短名单 15 —— 带 CAS ID（Fig. S20）")
    add("")
    add("| rank | cas | mp_k | bp_k | fp_k |")
    add("| --- | --- | --- | --- | --- |")
    for row in summary["entries"]:
        if row["shortlist"] != "15":
            continue
        add(
            "| {} | {} | {} | {} | {} |".format(
                row["rank"], row["cas"], row["mp_k"], row["bp_k"], row["fp_k"]
            )
        )
    add("")
    add("### 2.2 短名单 14 —— 不带 CAS ID（Fig. S21）")
    add("")
    add("| rank | smiles | mp_k | bp_k | fp_k |")
    add("| --- | --- | --- | --- | --- |")
    for row in summary["entries"]:
        if row["shortlist"] != "14":
            continue
        add(
            "| {} | {} | {} | {} | {} |".format(
                row["rank"], row["smiles"], row["mp_k"], row["bp_k"], row["fp_k"]
            )
        )
    add("")
    add("---")
    add("")
    add("## 3 级联漏斗（论文声称值，未经复算）")
    add("")
    add("| 级 | 论文声称 | 出处 |")
    add("| --- | --- | --- |")
    add("| QM9 起始分子数 | {:,} | SI §11 |".format(cascade["qm9_molecules_collected"]))
    add(
        "| 结构过滤后（去掉 -OH / -COOH，Molwt < 600，#Heavy < 30） | {:,} | SI §11 |".format(
            cascade["after_structural_screening"]
        )
    )
    add("| MP < 230 K | {:,} | SI §11 |".format(cascade["mp_below_230k"]))
    add("| BP > 430 K | {:,} | SI §11 |".format(cascade["bp_above_430k"]))
    add("| FP > 360 K | {:,} | SI §11 |".format(cascade["fp_above_360k"]))
    add("| 分拆：带 CAS ID | {} | SI §11 |".format(cascade["with_cas_id"]))
    add("| 分拆：不带 CAS ID | {} | SI §11 |".format(cascade["without_cas_id"]))
    add(
        "| 不带 CAS 的 {} 个再过 SAscore > 0.9 | {} | SI §11 |".format(
            cascade["without_cas_id"], cascade["after_retrosynthetic_accessibility_gt_0.9"]
        )
    )
    add("")
    add("**未复算声明**：" + provenance["note"])
    add("")
    add("SI §11 原文（逐字，空白已折叠）：")
    add("")
    add("> " + provenance["verbatim_paragraph"])
    add("")
    add("---")
    add("")
    add("## 4 字段覆盖率")
    add("")
    add("| 字段 | 非空行数 | 覆盖率 | SI 里有吗 | 说明 |")
    add("| --- | --- | --- | --- | --- |")
    for field, block in coverage["fields"].items():
        add(
            "| {} | {} / {} | {:.2%} | {} | {} |".format(
                code(field),
                block["non_empty"],
                block["rows"],
                block["non_empty_rate"],
                block["printed_in_si"],
                block["note"],
            )
        )
    add("")
    add("---")
    add("")
    add("## 5 与派单预期 / 正文的口径差异")
    add("")
    add("| 检查 | 结果 | 说明 |")
    add("| --- | --- | --- |")
    for check in summary["cascade_cross_checks"]:
        add("| {} | {} | {} |".format(check["id"], check["status"], check["detail"]))
    add("")
    add(
        "**与派单的差异**：派单写的级联「133,885 → 51,001 → 13,155 → 3,619 → 35 → 15+14」"
        "与 SI §11 完全一致，SI 的实际文字里没有任何一个数字与它不同。"
        "唯一要补的是：SI 在 15 与 14 之间还印了一层「20」——35 拆成 15（带 CAS）与 20（不带 CAS），"
        "20 个再过 SAscore > 0.9 得 14；派单把这一步压缩成了「CAS 分拆 + SAscore>0.9」。"
    )
    add("")
    add("---")
    add("")
    add("## 6 异常与未解事项")
    add("")
    for index, item in enumerate(summary["anomalies"], start=1):
        rows = "、".join(item["rows"]) if item["rows"] else "不针对具体行"
        add("{}. {}（{}）：{}".format(index, code(item["id"]), rows, item["detail"]))
    add("")
    add("---")
    add("")
    add("## 7 机检清单")
    add("")
    add("| 检查 | 结果 | 说明 |")
    add("| --- | --- | --- |")
    for check in summary["validation"]["checks"]:
        add("| {} | {} | {} |".format(check["id"], check["status"], check["detail"]))
    add("")
    derived = summary["derived_not_from_si"]
    if derived.get("available"):
        add(
            "附："
            + derived["label"]
            + "——RDKit 解析 "
            + str(derived["parsed"])
            + " / "
            + str(derived["checked"])
            + " 条 SMILES，派生分子量区间 "
            + str(derived["molwt_min"])
            + " - "
            + str(derived["molwt_max"])
            + " g/mol，全部低于 600 这道闸门。"
        )
        add("")
    add("---")
    add("")
    add("## 8 使用边界")
    add("")
    add("- " + DISCIPLINE_STATEMENT)
    add(
        "- 本表不进冻结管线：它只被 "
        + code("tests/test_kpi_shortlist_extraction.py")
        + " 与交叉核对用途读取，不参与任何特征构造、训练或评分。"
    )
    add("- 本表不是本仓数据集的证据来源：29 个分子的 MP/BP/FP 是论文模型给出的预测值，不是实验观测值。")
    add("- 零网络：探针与单测都只读本地文件。")
    add(
        "- 图注里 "
        + code("Figure S 21")
        + " 的空格、以及 FP 与 BP 相等的那一行，都属于「照实登记、不做修正」。"
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def _stable_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the volatile fields so a re-derivation can be compared to disk."""

    clone = json.loads(json.dumps(summary, ensure_ascii=False))
    clone.pop("generated_at_utc", None)
    clone.get("source", {}).pop("shortlist_csv_sha256", None)
    return clone


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def run(
    *,
    si_pdf_override: str | None = None,
    main_text_override: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    """Derive the table, the summary and the report without touching disk."""

    entries = shortlist_entries()
    csv_text = build_csv_text(entries)
    si_pdf = resolve_si_pdf(si_pdf_override)
    main_pdf = resolve_main_text_pdf(main_text_override)
    si_pages = read_pdf_pages(si_pdf) if si_pdf else None
    main_pages = read_pdf_pages(main_pdf) if main_pdf else None
    summary = build_summary(
        entries,
        si_pages=si_pages,
        si_pdf=si_pdf,
        main_pages=main_pages,
        main_pdf=main_pdf,
        csv_text=csv_text,
    )
    return csv_text, summary, render_report(summary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract the KPI SI Fig. S20/S21 shortlists.")
    parser.add_argument("--si-pdf", default=None, help="override the SI PDF path")
    parser.add_argument("--main-text-pdf", default=None, help="override the main text PDF path")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="output CSV path")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="output summary path")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="output report path")
    parser.add_argument("--check", action="store_true", help="re-derive and compare to disk")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    summary_path = Path(args.summary)
    report_path = Path(args.report)
    csv_text, summary, report_text = run(
        si_pdf_override=args.si_pdf,
        main_text_override=args.main_text_pdf,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    problems: list[str] = list(summary["validation"]["problems"])

    if args.check:
        if not csv_path.is_file() or csv_path.read_bytes() != csv_text.encode("utf-8"):
            problems.append(f"CSV on disk differs from the re-derived table: {csv_path}")
        if not summary_path.is_file():
            problems.append(f"summary missing: {summary_path}")
        else:
            on_disk = json.loads(summary_path.read_text(encoding="utf-8"))
            if _stable_view(on_disk) != _stable_view(summary):
                problems.append("summary on disk differs from the re-derived summary")
        if not report_path.is_file():
            problems.append(f"report missing: {report_path}")
        elif report_path.read_text(encoding="utf-8") != report_text:
            problems.append(f"report on disk is not render_report(summary): {report_path}")
        if problems:
            for problem in problems:
                print("FAIL " + problem)
            return 1
        print("OK 29 rows, 15 + 14, table/summary/report reproduce")
        return 0

    _write_text(csv_path, csv_text)
    _write_text(summary_path, summary_text)
    _write_text(report_path, report_text)
    for problem in problems:
        print("FAIL " + problem)
    print(
        "wrote {} rows ({} + {}) to {}".format(
            summary["coverage"]["rows"],
            summary["coverage"]["by_shortlist"]["15"],
            summary["coverage"]["by_shortlist"]["14"],
            csv_path,
        )
    )
    print("si_hash_matches_pin={}".format(summary["source"]["si_pdf"]["sha256_matches_pin"]))
    for check in summary["validation"]["checks"]:
        print("  [{}] {}: {}".format(check["status"], check["id"], check["detail"]))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
