#!/usr/bin/env python
"""Strict extraction of the ECW-308 Table S3 and its bibliography.

Source
------
D. Wang, T. He, A. Wang, K. Guo, M. Avdeev, C. Ouyang, L. Chen, S. Shi,
"A Thermodynamic Cycle-Based Electrochemical Windows Database of 308
Electrolyte Solvents for Rechargeable Batteries", Adv. Funct. Mater. 2023,
DOI 10.1002/adfm.202212342, Supporting Information, Table S3 ("The predicted
melting points, predicted boiling points, viscosities, dielectric constants,
ionic conductivities and predicted flash points of 308 electrolyte solvents
from literatures and ChemSpider/PubChem database").

Why a coordinate-aware extractor instead of the text dump
---------------------------------------------------------
The v0.3.6 tier-2 pass read this SI one target row at a time and left two loose
ends. First, the SI's own "Refs." column is a list of bracketed numbers, and
the mapping from those numbers to full citations lives in the bibliography of
the same file; reading only the target page turns "Hall et al.; Flamme et al."
into an unresolvable fragment. Second, a per-target read cannot support a
whole-table cross-check, and ECW-308 is the highest-overlap free compilation
for this dataset, so reconciling all 308 rows is the strongest cheap
cross-validation available.

A plain text dump cannot support that reconciliation. In the dump the rows run
together on shared lines ("... [16, 34, 36] 159. Propylene carbonate ..."), row
279 loses its full stop entirely, and some names are glued to the row number.
The PDF, by contrast, positions every cell at a stable x coordinate, so the
extractor reads the PDF through the pypdf text visitor and decides columns by
geometry:

- the dielectric column is the band strictly between the viscosity and
  ionic-conductivity header columns, both of which are printed on every Table
  S3 page that repeats the header,
- a row is only accepted when its row number equals the next expected index, so
  a stray number in a neighbouring column cannot open a row,
- a cell is only reported as a value when exactly one token falls inside the
  band and it parses as a number.

Honesty rules
-------------
- A cell rendered as "/" is "blank", a row whose band holds no token at all is
  "missing", and a row whose band holds two tokens is "ambiguous". None of
  these three states is ever converted into a number.
- The dielectric column is headed "Dielectric constant at 25 C" and the SI
  prints no per-row thermometer reading, so every accepted value carries
  temperature_c = 25.0 with temperature_source = "column_header" rather than a
  fabricated per-row temperature.
- The cross-check never edits the dataset. It writes a side-car table and
  refuses to match a row whose molecular formula maps to more than one dataset
  entry.

Usage
-----
    python probes/g1plus_ecw308_extract.py            # write evidence + crosscheck
    python probes/g1plus_ecw308_extract.py --check    # re-derive and compare to disk
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PDF = (
    REPOSITORY_ROOT
    / "data"
    / "external"
    / "g1plus"
    / "compilations"
    / "adfm202212342-sup-0001-SuppMat.pdf"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "probes" / "g1plus_ecw308_evidence.json"
DEFAULT_CROSSCHECK = REPOSITORY_ROOT / "probes" / "g1plus_ecw308_crosscheck.json"
DEFAULT_DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"

# Pinned so a swapped SI file cannot silently change the artefact. Set to None
# (or pass --no-hash-check) when deliberately re-baselining on a new download.
EXPECTED_PDF_SHA256 = "19f1166e2aba6834f0cccb1d751b618dded5c80f97ab5b9957b2d15046bdbc76"

TABLE_ROWS = 308
ROW_INDEX = re.compile(r"^(?P<index>\d{1,3})\.")
NUMERIC = re.compile(r"^[\u2212-]?\d+(?:\.\d+)?$")
FORMULA = re.compile(r"^(?:[A-Z][a-z]?\d*){2,}$")
FORMULA_TOKEN = re.compile(r"^[A-Za-z0-9]+$")
REFERENCE_ENTRY = re.compile(r"\[(?P<index>\d+)\]\s*(?P<body>.*?)(?=\[\d+\]|\Z)", re.DOTALL)

# Header x positions, measured on every Table S3 page that repeats the column
# header (SI pages 67, 70, 72, 79, 83, 84 and 90). They are stable to within a
# point, so the dielectric band is derived from them rather than fitted to the
# values it is meant to police.
HEADER_VISCOSITY = "Viscosity"
HEADER_DIELECTRIC = "Dielectric"
HEADER_CONDUCTIVITY = "Ionic"
HEADER_X = {HEADER_VISCOSITY: 452.0, HEADER_DIELECTRIC: 521.0, HEADER_CONDUCTIVITY: 599.0}
FALLBACK_BAND = (
    (HEADER_X[HEADER_VISCOSITY] + HEADER_X[HEADER_DIELECTRIC]) / 2.0,
    (HEADER_X[HEADER_DIELECTRIC] + HEADER_X[HEADER_CONDUCTIVITY]) / 2.0,
)

ROW_INDEX_MAX_X = 260.0
ROW_NAME_MAX_X = 285.0
FORMULA_MIN_X = 138.0
FORMULA_MAX_X = 220.0
FORMULA_MIN_DY = 10.5
FORMULA_MAX_DY = 35.0
REFERENCE_MIN_X = 700.0
# A row block occupies the ~20 pt of column space below its printed number, and
# the SI sometimes stacks a second, uncited value under the first. A cell is
# therefore claimed by the single row whose baseline sits 0-20 pt above it (up
# to 2 pt above the baseline is tolerated because a stacked first value can be
# printed fractionally above the row name).
CELL_BELOW_MAX_DY = 20.0
CELL_ABOVE_MAX_DY = 2.0
NAME_SAME_LINE_DY = 1.5
COLUMN_TEMPERATURE_C = 25.0
COLUMN_TEMPERATURE_SOURCE = "column_header"

# Trade and trivial names used by the SI that differ from the systematic name
# frozen in the dataset. The bridge is only ever consulted when the molecular
# formula is ambiguous or absent, never to override a formula match.
SYNONYM_NAMES = {
    # Traditional names in the SI mapped onto the systematic name frozen in the
    # dataset. Every entry is an identity claim, so the table stays small and
    # explicit instead of being inferred by string similarity.
    "diglyme": "2,5,8-trioxanonane",
    "triglyme": "2,5,8,11-tetraoxadodecane",
    "tetraglyme": "2,5,8,11,14-pentaoxapentadecane",
    "adiponitrile": "hexanedinitrile",
    "glutaronitrile": "pentanedinitrile",
    "pimelonitrile": "heptanedinitrile",
    "tetramethylene sulfone": "sulfolane",
    "suberonitrile": "octanedinitrile",
    "azelanitrile": "nonanedinitrile",
    "sebaconitrile": "decanedinitrile",
    # The SI prints a few names with the substituent spacing split across the
    # word ("1,2 - Dimethoxy ethane"); the key is the canonical form.
    "1 2 dimethoxy ethane": "1,2-dimethoxyethane",
}

AGREEMENT_BANDS = ((0.01, "agree_within_1pct"), (0.05, "agree_within_5pct"))
MATCHED_LABELS = tuple(label for _, label in AGREEMENT_BANDS)
# Every status the cross-check can emit. They are all reported, including the
# zeroes, so a downstream reader never has to distinguish "absent" from "none".
STATUS_LABELS = (
    *MATCHED_LABELS,
    "divergent",
    "formula_only_candidate",
    "dataset_miss",
    "ambiguous_formula",
    "ecw_no_formula",
    "ecw_blank",
    "ecw_missing",
    "ecw_stacked",
)


class Token(NamedTuple):
    page: int
    x: float
    y: float
    text: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_pdf(path: Path) -> tuple[list[Token], list[str]]:
    """Return coordinate-tagged text tokens plus plain text for every page."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    tokens: list[Token] = []
    page_texts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        raw: list[tuple[float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size, _raw=raw):
            collapsed = " ".join(text.split())
            if collapsed:
                _raw.append((round(tm[4], 1), round(tm[5], 1), collapsed))

        page.extract_text(visitor_text=visitor)
        tokens.extend(Token(page_number, x, y, text) for x, y, text in raw)
        page_texts.append(page.extract_text())
    return tokens, page_texts


def table_s3_page_range(page_texts: Sequence[str]) -> tuple[int, int]:
    """Half-open 1-based page range holding Table S3."""
    start = next(i for i, text in enumerate(page_texts) if "Table S3." in text)
    end = next(i for i, text in enumerate(page_texts) if i > start and "Table S4." in text)
    return start + 1, end + 1


def dielectric_band(tokens: Sequence[Token]) -> tuple[float, float]:
    positions = {
        token.text: token.x
        for token in tokens
        if token.text in (HEADER_VISCOSITY, HEADER_DIELECTRIC, HEADER_CONDUCTIVITY)
    }
    if len(positions) == 3:
        return (
            (positions[HEADER_VISCOSITY] + positions[HEADER_DIELECTRIC]) / 2.0,
            (positions[HEADER_DIELECTRIC] + positions[HEADER_CONDUCTIVITY]) / 2.0,
        )
    return FALLBACK_BAND


def row_starts(tokens: Sequence[Token], page_range: tuple[int, int]) -> tuple[list[Token], int]:
    """Sequentially pin rows 1..308; stop at the first index that never arrives."""
    scoped = [t for t in tokens if page_range[0] <= t.page < page_range[1]]
    stream = sorted(scoped, key=lambda t: (t.page, -t.y, t.x))
    starts: list[Token] = []
    expected = 1
    for token in stream:
        if token.x > ROW_INDEX_MAX_X:
            continue
        match = ROW_INDEX.match(token.text)
        if match:
            value = int(match.group("index"))
        elif token.text == str(expected):
            # Row 279 is printed without its full stop in the SI.
            value = expected
        else:
            continue
        if value != expected:
            continue
        starts.append(token)
        expected += 1
        if expected > TABLE_ROWS:
            break
    return starts, expected - 1


def _row_index(start: Token) -> int:
    match = ROW_INDEX.match(start.text)
    return int(match.group("index")) if match else int(start.text)


def _name_for(start: Token, scoped: Sequence[Token]) -> str:
    parts = [(start.x, start.text)]
    for token in scoped:
        if token.page != start.page:
            continue
        if abs(token.y - start.y) > NAME_SAME_LINE_DY:
            continue
        if token.x > ROW_NAME_MAX_X:
            continue
        parts.append((token.x, token.text))
    pieces: list[str] = []
    for _, text in sorted(parts):
        if pieces and text in " ".join(pieces):
            continue
        pieces.append(text)
    return ROW_INDEX.sub("", " ".join(pieces), count=1).strip()


def _formula_for(start: Token, scoped: Sequence[Token]) -> str | None:
    cells = [
        token
        for token in scoped
        if token.page == start.page
        and FORMULA_MIN_X <= token.x <= FORMULA_MAX_X
        and FORMULA_MIN_DY <= start.y - token.y <= FORMULA_MAX_DY
        and FORMULA_TOKEN.match(token.text)
    ]
    # Order by x, not by y: element symbols and their subscripts sit at slightly
    # different baselines, so a y-major sort would produce "CHO343".
    joined = "".join(text for _, text in sorted((cell.x, cell.text) for cell in cells))
    return joined if FORMULA.match(joined) else None


def _references_for(start: Token, scoped: Sequence[Token]) -> list[int]:
    cells = [
        token
        for token in scoped
        if token.page == start.page
        and token.x >= REFERENCE_MIN_X
        and -6.0 <= start.y - token.y <= 16.0
    ]
    # Reference cells wrap onto a second line, so read them top line first and
    # then left to right; an x-major sort would interleave the two lines and
    # turn "[16, 34, 36]" into "[1636, 34]".
    ordered = sorted(cells, key=lambda cell: (-cell.y, cell.x))
    joined = "".join(cell.text for cell in ordered)
    return [int(value) for value in re.findall(r"\d+", joined)]


def band_cells(
    starts: Sequence[Token], scoped: Sequence[Token], band: tuple[float, float]
) -> tuple[dict[tuple[int, float], list[Token]], list[dict]]:
    """Claim each in-band token for the one row whose block can contain it."""
    per_row: dict[tuple[int, float], list[Token]] = defaultdict(list)
    by_page: dict[int, list[Token]] = defaultdict(list)
    for start in starts:
        by_page[start.page].append(start)
    unclaimed: list[dict] = []
    for token in scoped:
        if not band[0] < token.x < band[1]:
            continue
        candidates = [
            start
            for start in by_page.get(token.page, [])
            if -CELL_ABOVE_MAX_DY <= start.y - token.y <= CELL_BELOW_MAX_DY
        ]
        if len(candidates) == 1:
            per_row[(candidates[0].page, candidates[0].y)].append(token)
        elif len(candidates) > 1:
            nearest = min(candidates, key=lambda start: abs(start.y - token.y))
            per_row[(nearest.page, nearest.y)].append(token)
            unclaimed.append(
                {
                    "page": token.page,
                    "x": token.x,
                    "y": token.y,
                    "text": token.text,
                    "reason": "more than one row baseline could own the cell",
                }
            )
        else:
            unclaimed.append(
                {
                    "page": token.page,
                    "x": token.x,
                    "y": token.y,
                    "text": token.text,
                    "reason": "no row baseline 0-20 pt above the cell",
                }
            )
    return per_row, unclaimed


def _cell_status(texts: list[str]) -> tuple[str, str | None, float | None]:
    numbers = [text for text in texts if NUMERIC.match(text)]
    if len(numbers) == 1:
        return "value", numbers[0], float(numbers[0].replace("\u2212", "-"))
    if len(numbers) > 1:
        return "stacked", " ".join(texts), None
    if texts:
        return "blank", " ".join(texts), None
    return "missing", None, None


def extract_rows(
    tokens: Sequence[Token], page_range: tuple[int, int]
) -> tuple[list[dict], dict, list[dict]]:
    scoped = [t for t in tokens if page_range[0] <= t.page < page_range[1]]
    starts, reached = row_starts(tokens, page_range)
    band = dielectric_band(scoped)
    cells, unclaimed = band_cells(starts, scoped, band)
    rows: list[dict] = []
    for start in starts:
        raw_cells = sorted(cells.get((start.page, start.y), []), key=lambda token: token.x)
        status, cell, value = _cell_status([token.text for token in raw_cells])
        found = status == "value"
        distance = (
            round(abs(start.y - raw_cells[0].y), 1) if status == "value" and raw_cells else None
        )
        rows.append(
            {
                "index": _row_index(start),
                "page": start.page,
                "name": _name_for(start, scoped),
                "formula": _formula_for(start, scoped),
                "dielectric_cell": cell,
                "dielectric_status": status,
                "dielectric_value": value,
                "temperature_c": COLUMN_TEMPERATURE_C if found else None,
                "temperature_source": COLUMN_TEMPERATURE_SOURCE if found else None,
                "cell_distance_pt": distance,
                "needs_review": bool(distance is not None and distance > 15.0),
                "references": _references_for(start, scoped),
                "row_y": start.y,
            }
        )
    meta = {
        "table_pages": [page_range[0], page_range[1] - 1],
        "dielectric_band_x": [round(band[0], 1), round(band[1], 1)],
        "row_index_sequence_reached": reached,
        "row_index_sequence_complete": reached == TABLE_ROWS,
    }
    return rows, meta, unclaimed


def parse_references(page_texts: Sequence[str]) -> dict[str, str]:
    tail = "\n".join(page_texts)
    marker = tail.find("References")
    if marker == -1:
        return {}
    references: dict[str, str] = {}
    for match in REFERENCE_ENTRY.finditer(tail[marker:]):
        body = " ".join(match.group("body").split())
        if body:
            references[match.group("index")] = body
    return references


def build_evidence(pdf_path: Path, *, check_hash: bool = True) -> dict[str, Any]:
    digest = sha256_file(pdf_path)
    if check_hash and EXPECTED_PDF_SHA256 and digest != EXPECTED_PDF_SHA256:
        raise SystemExit(
            f"SI PDF hash {digest} does not match the pinned {EXPECTED_PDF_SHA256}; "
            "re-baseline deliberately with --no-hash-check"
        )
    tokens, page_texts = read_pdf(pdf_path)
    page_range = table_s3_page_range(page_texts)
    rows, meta, unclaimed = extract_rows(tokens, page_range)
    references = parse_references(page_texts)
    statuses: dict[str, int] = defaultdict(int)
    for row in rows:
        statuses[row["dielectric_status"]] += 1
    summary = {
        "rows_extracted": len(rows),
        "rows_with_value": statuses["value"],
        "rows_blank": statuses["blank"],
        "rows_missing": statuses["missing"],
        "rows_stacked": statuses["stacked"],
        "cells_unclaimed": len(unclaimed),
        "rows_with_formula": sum(1 for row in rows if row["formula"]),
        "rows_needing_review": sum(1 for row in rows if row["needs_review"]),
        "references_parsed": len(references),
        **meta,
    }
    return {
        "schema_version": 1,
        "probe": "g1plus_ecw308_table_s3",
        "source": {
            "citation": (
                "D. Wang, T. He, A. Wang, K. Guo, M. Avdeev, C. Ouyang, L. Chen, "
                "S. Shi, Adv. Funct. Mater. 2023, 33, 2212342"
            ),
            "doi": "10.1002/adfm.202212342",
            "table": "Supporting Information, Table S3",
            "url": (
                "https://advanced.onlinelibrary.wiley.com/action/downloadSupplement"
                "?doi=10.1002%2Fadfm202212342&file=adfm202212342-sup-0001-SuppMat.pdf"
            ),
            "file": pdf_path.name,
            "sha256": digest,
            "license_note": (
                "Wiley article with no CC licence declared. Retained locally as "
                "research evidence only, not redistributed."
            ),
        },
        "method": {
            "extraction": "pypdf text visitor with x/y coordinates",
            "column_rule": (
                "dielectric band = midpoint(viscosity header x, dielectric header x) "
                "to midpoint(dielectric header x, conductivity header x)"
            ),
            "row_rule": "row numbers must arrive in order 1..308",
            "value_rule": "exactly one numeric token inside the band",
            "temperature_rule": (
                "the column header states 25 C and the SI prints no per-row "
                "temperature, so values carry the column temperature only"
            ),
        },
        "limitations": [
            (
                "ECW-308 is a secondary compilation: a cross-check and a source of "
                "citation leads, not a primary value that may overwrite the dataset."
            ),
            (
                "Every dielectric cell is rounded to two decimals, so agreement with a "
                "full-precision primary value is not expected to be exact."
            ),
            (
                "Rows are matched by molecular formula plus an explicit identity claim, "
                "so a formula shared by several isomers is never matched by guesswork."
            ),
            (
                "Table S3 mixes literature and ChemSpider/PubChem data, so a matched row "
                "still needs its Refs. column read before the value can be cited."
            ),
        ],
        "summary": summary,
        "rows": rows,
        "unclaimed_cells": unclaimed,
        "references": references,
    }


def rdkit_formula(smiles: str) -> str | None:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return rdMolDescriptors.CalcMolFormula(molecule)


def classify(relative_delta: float) -> str:
    for threshold, label in AGREEMENT_BANDS:
        if abs(relative_delta) <= threshold:
            return label
    return "divergent"


def normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def canonical_name(name: str) -> str:
    """Lower-case name with parenthetical qualifiers and punctuation removed."""
    stripped = re.sub(r"\([^)]*\)", " ", name)
    return normalise_name(stripped)


def _dataset_candidates(
    row: dict, by_formula: dict[str, list[dict]]
) -> tuple[list[dict], list[str]]:
    """Candidates that agree on both formula and an explicit identity claim."""
    formula_matches = by_formula.get(row["formula"], []) if row["formula"] else []
    names = [record["name"] for record in formula_matches]
    if not formula_matches:
        return [], names
    ecw_name = canonical_name(row["name"])
    synonym = normalise_name(SYNONYM_NAMES.get(ecw_name, ""))
    agreed = [
        record
        for record in formula_matches
        if canonical_name(record["name"]) in {ecw_name, synonym}
    ]
    return agreed, names


def crosscheck(evidence: dict[str, Any], dataset_path: Path) -> dict[str, Any]:
    with dataset_path.open(encoding="utf-8", newline="") as handle:
        dataset = list(csv.DictReader(handle))
    by_formula: dict[str, list[dict]] = defaultdict(list)
    for record in dataset:
        formula = rdkit_formula(record.get("smiles", ""))
        if formula:
            by_formula[formula].append(record)

    counts: dict[str, int] = defaultdict(int)
    entries: list[dict] = []
    for row in evidence["rows"]:
        entry: dict[str, Any] = {
            "ecw_index": row["index"],
            "ecw_name": row["name"],
            "ecw_formula": row["formula"],
            "ecw_dielectric": row["dielectric_value"],
            "ecw_references": row["references"],
        }
        status = row["dielectric_status"]
        if status != "value":
            agreed, _ = _dataset_candidates(row, by_formula) if row["formula"] else ([], [])
            entry["status"] = f"ecw_{status}"
            entry["dielectric_cell"] = row["dielectric_cell"]
            if status == "stacked" and agreed:
                numbers = [
                    float(value)
                    for value in re.findall(r"\d+(?:\.\d+)?", row["dielectric_cell"] or "")
                ]
                dataset_value = float(agreed[0]["dielectric"])
                entry.update(
                    {
                        "stacked_values": numbers,
                        "dataset_name": agreed[0]["name"],
                        "dataset_dielectric": dataset_value,
                        "dataset_value_in_cell": any(
                            abs(number - dataset_value) < 1e-9 for number in numbers
                        ),
                    }
                )
            counts[f"ecw_{status}"] += 1
            entries.append(entry)
            continue
        if not row["formula"]:
            entry["status"] = "ecw_no_formula"
            counts["ecw_no_formula"] += 1
            entries.append(entry)
            continue
        agreed, formula_matches = _dataset_candidates(row, by_formula)
        if len(agreed) > 1:
            entry["status"] = "ambiguous_formula"
            entry["formula_candidates"] = [c["name"] for c in agreed]
            counts["ambiguous_formula"] += 1
            entries.append(entry)
            continue
        if not agreed:
            entry["status"] = (
                "formula_only_candidate" if formula_matches else "dataset_miss"
            )
            if formula_matches:
                entry["formula_candidates"] = formula_matches
            counts[entry["status"]] += 1
            entries.append(entry)
            continue
        record = agreed[0]
        dataset_value = float(record["dielectric"])
        relative_delta = (row["dielectric_value"] - dataset_value) / dataset_value
        entry.update(
            {
                "status": classify(relative_delta),
                "inchikey": record["inchikey"],
                "dataset_name": record["name"],
                "dataset_dielectric": dataset_value,
                "dataset_temperature_k": float(record["T_K"]),
                "delta": round(row["dielectric_value"] - dataset_value, 4),
                "relative_delta": round(relative_delta, 4),
                "temperature_note": (
                    "same 298.15 K"
                    if abs(float(record["T_K"]) - 298.15) < 1e-6
                    else f"dataset value is at {record['T_K']} K"
                ),
            }
        )
        counts[entry["status"]] += 1
        entries.append(entry)

    return {
        "schema_version": 1,
        "probe": "g1plus_ecw308_crosscheck",
        "source": {"evidence": DEFAULT_OUTPUT.name, "dataset": dataset_path.name},
        "method": {
            "identity_bridge": (
                "molecular formula from the dataset SMILES via RDKit, confirmed by an "
                "explicit name identity claim (parenthesis-stripped full name or a "
                "documented synonym) rather than string similarity"
            ),
            "ambiguity_rule": (
                "an ECW row that agrees on formula but not on an identity claim is "
                "reported as formula_only_candidate, never as a conflict"
            ),
            "agreement_bands": {label: threshold for threshold, label in AGREEMENT_BANDS},
        },
        "summary": {
            "dataset_rows": len(dataset),
            "ecw_rows": len(evidence["rows"]),
            **{label: counts.get(label, 0) for label in STATUS_LABELS},
            "matched": sum(counts.get(label, 0) for label in MATCHED_LABELS)
            + counts.get("divergent", 0),
        },
        "entries": entries,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--crosscheck-out", type=Path, default=DEFAULT_CROSSCHECK)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--no-hash-check", action="store_true")
    parser.add_argument("--skip-crosscheck", action="store_true")
    parser.add_argument("--check", action="store_true", help="re-derive and compare to disk")
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"missing SI PDF: {args.pdf}", file=sys.stderr)
        return 2

    evidence = build_evidence(args.pdf, check_hash=not args.no_hash_check)
    if args.check:
        same = json.loads(args.out.read_text(encoding="utf-8")) == evidence
        print(f"evidence reproduces: {same}")
        return 0 if same else 1

    write_json(args.out, evidence)
    print(
        "rows={rows_extracted} values={rows_with_value} blank={rows_blank} "
        "missing={rows_missing} stacked={rows_stacked} unclaimed={cells_unclaimed} "
        "refs={references_parsed}".format(**evidence["summary"])
    )
    if not args.skip_crosscheck:
        report = crosscheck(evidence, args.dataset)
        write_json(args.crosscheck_out, report)
        summary = report["summary"]
        print(
            f"crosscheck: matched={summary.get('matched', 0)} "
            f"divergent={summary.get('divergent', 0)} "
            f"formula_only={summary.get('formula_only_candidate', 0)} "
            f"ambiguous={summary.get('ambiguous_formula', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

