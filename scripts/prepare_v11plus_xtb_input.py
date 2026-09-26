"""Select the compounds of the merged table that still need an xTB feature block.

Reads the merged observation table and the frozen v0.3 feature table, and writes
the subset whose compounds have no usable xTB features yet.  The output is shaped
for ``scripts/run_xtb_physical_features.py``.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

MERGED_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_v11plus_xtb_input.csv"
)
DEFAULT_SUMMARY = (
    REPOSITORY_ROOT / "probes" / "dielectric_v11plus_xtb_input_summary.json"
)

INPUT_FIELDS = ("inchikey", "name", "smiles", "T_K", "dielectric")
USABLE_STATUSES = ("ok", "cached")


def key(value: str | None) -> str:
    return (value or "").strip().upper()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(
    path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def select_missing(
    merged: Sequence[Mapping[str, str]],
    features: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    covered: set[str] = set()
    for row in features:
        if (row.get("status") or "").strip() not in USABLE_STATUSES:
            continue
        if not (row.get("dipole_D") or "").strip():
            continue
        covered.add(key(row.get("inchikey")))

    stats = {"merged_compounds_with_smiles": 0, "already_covered": 0, "missing": 0,
             "skipped_without_smiles": 0}
    selected: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for row in merged:
        compound = key(row.get("inchikey"))
        smiles = (row.get("smiles") or "").strip()
        if not compound or compound in seen:
            continue
        seen.add(compound)
        if not smiles:
            stats["skipped_without_smiles"] += 1
            continue
        stats["merged_compounds_with_smiles"] += 1
        if compound in covered:
            stats["already_covered"] += 1
            continue
        selected[compound] = {
            "inchikey": compound,
            "name": row.get("name", ""),
            "smiles": smiles,
            "T_K": row.get("T_K", ""),
            "dielectric": row.get("epsilon", ""),
        }
    stats["missing"] = len(selected)
    ordered = [selected[k] for k in sorted(selected)]
    return ordered, stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", type=Path, default=MERGED_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = _parse_args()
    rows, stats = select_missing(read_rows(args.merged), read_rows(args.features))
    write_rows(args.output, INPUT_FIELDS, rows)
    summary = dict(stats)
    summary["compounds"] = [row["name"] for row in rows]
    summary["inputs"] = {
        "merged": str(args.merged.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
        "features": str(args.features.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())