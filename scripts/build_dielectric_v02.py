"""Build dielectric v0.2 from v0.1 plus selected NBS Circular 514 additions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

NBS514_DOI = "10.6028/nbs.circ.514"
NBS514_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf"
NBS514_SHA256 = "cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683"
NBS514_SCOPE = "nbs514_manual_static_293.15_303.15K"
V01_SCOPE = "p1_thermoml_zero_frequency_pure_293.15_303.15K"
PROVENANCE_FIELDS = (
    "source_record_id",
    "source_page",
    "source_quality",
    "selection_rank",
    "structure_resolution_source",
    "al_round1_hit",
    "max_tanimoto_solvfunc",
)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _nbs_row(candidate: Mapping[str, str]) -> dict[str, str]:
    return {
        "inchikey": candidate["inchikey"],
        "smiles": candidate["smiles"],
        "name": candidate["compound_name"],
        "T_K": candidate["T_K"],
        "dielectric": candidate["dielectric"],
        "uncertainty": "",
        "uncertainty_value": "",
        "uncertainty_kind": "not_reported",
        "confidence_level": "",
        "uncertainty_json": "[]",
        "source_doi": NBS514_DOI,
        "source_dois_all": NBS514_DOI,
        "n_observations": "1",
        "n_historical_observations": "0",
        "source_scope": NBS514_SCOPE,
        "crosscheck_available": "false",
        "gate_flags": (
            "zero_frequency|pure_component|experimental|literature_manual_entry|"
            "single_source|nbs514_circular_514"
        ),
        "source_record_id": candidate["source_id"],
        "source_page": candidate["source_page"],
        "source_quality": candidate["source_quality"],
        "selection_rank": candidate["selection_rank"],
        "structure_resolution_source": candidate["resolution_source"],
        "al_round1_hit": candidate["al_round1_hit"],
        "max_tanimoto_solvfunc": candidate["max_tanimoto_solvfunc"],
    }


def build_rows(
    v01_rows: Sequence[Mapping[str, str]],
    candidates: Sequence[Mapping[str, str]],
    *,
    minimum_additions: int = 100,
) -> list[dict[str, str]]:
    selected = [
        dict(row)
        for row in candidates
        if row.get("selected_for_v02") == "true"
    ]
    selected.sort(key=lambda row: int(row["selection_rank"]))
    if len(selected) < minimum_additions:
        raise ValueError(
            f"v0.2 needs at least {minimum_additions} additions; found {len(selected)}"
        )

    v01_keys = {row["inchikey"] for row in v01_rows}
    v01_names = {row["name"].casefold() for row in v01_rows}
    additions = []
    for row in selected:
        if row["inchikey"] in v01_keys:
            raise ValueError(f"selected addition duplicates a v0.1 key: {row['inchikey']}")
        if row["compound_name"].casefold() in v01_names:
            raise ValueError(
                f"selected addition duplicates a v0.1 name: {row['compound_name']}"
            )
        if row.get("selection_eligible") != "true":
            raise ValueError(f"selected row is not eligible: {row['source_id']}")
        if row.get("formula_match") != "true":
            raise ValueError(f"selected row has a formula mismatch: {row['source_id']}")
        if any(row.get(field, "") for field in ("frequency_note", "hazard_flags", "stability_flags")):
            raise ValueError(f"selected row has a source or stability exclusion: {row['source_id']}")
        additions.append(_nbs_row(row))

    rows = [
        {
            **row,
            "source_record_id": "",
            "source_page": "",
            "source_quality": "",
            "selection_rank": "",
            "structure_resolution_source": "",
            "al_round1_hit": "",
            "max_tanimoto_solvfunc": "",
        }
        for row in v01_rows
    ]
    rows.extend(additions)
    keys = [row["inchikey"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("v0.2 contains duplicate InChIKeys")
    return rows


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v01", type=Path, default=data_dir / "dielectric_v01.csv")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=data_dir / "processed" / "nbs514_structure_candidates.csv",
    )
    parser.add_argument("--output", type=Path, default=data_dir / "dielectric_v02.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v02_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    v01_fields, v01_rows = read_csv_rows(args.v01)
    _, candidates = read_csv_rows(args.candidates)
    rows = build_rows(v01_rows, candidates)
    fields = list(v01_fields)
    extra_fields = [field for field in PROVENANCE_FIELDS if field not in fields]
    fields.extend(extra_fields)
    write_csv_rows(args.output, fields, rows)

    source_counts = Counter(row["source_scope"] for row in rows)
    temperatures = [float(row["T_K"]) for row in rows]
    summary = {
        "schema_version": 2,
        "dataset_version": "0.2",
        "compound_count": len(rows),
        "v01_compound_count": len(v01_rows),
        "new_compound_count": len(rows) - len(v01_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "temperature_window_K": {
            "minimum": min(temperatures),
            "maximum": max(temperatures),
        },
        "nbs514": {
            "doi": NBS514_DOI,
            "pdf_url": NBS514_URL,
            "pdf_sha256": NBS514_SHA256,
            "source_scope": NBS514_SCOPE,
            "selected_compounds": len(rows) - len(v01_rows),
            "source_pages": sorted(
                {
                    int(row["source_page"])
                    for row in rows
                    if row["source_scope"] == NBS514_SCOPE
                }
            ),
            "source_quality_counts": dict(
                sorted(
                    Counter(
                        row["source_quality"]
                        for row in rows
                        if row["source_scope"] == NBS514_SCOPE
                    ).items()
                )
            ),
        },
        "inputs": {
            "v01_sha256": canonical_text_sha256(args.v01),
            "candidate_sha256": canonical_text_sha256(args.candidates),
        },
        "output": {
            "path": args.output.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": canonical_text_sha256(args.output),
        },
        "status": "built; independent verification required",
    }
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
