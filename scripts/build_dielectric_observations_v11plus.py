"""Merge the verified v1.x observation table with the admission-gated low-frequency rows.

The v0.3 ingest gate admitted only pure-component, liquid, zero-frequency
relative-permittivity rows.  ``probes/dielectric_lowfreq_gate_probe.py`` showed
that 53 pure liquid compounds in the local ThermoML extract carry only
frequency-dependent rows, and that below its 1 MHz primary cap (3 MHz extended)
those rows agree with the zero-frequency static value within the corpus noise
floor.  This script merges the rows that probe admitted onto
``data/processed/dielectric_observations_v11.csv``.

Neither input is modified: the v11 table, the candidate table and the structure
table are read-only here, and the merged table is a new artifact.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

V11_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv"
CANDIDATES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_lowfreq_candidates.csv"
)
STRUCTURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_lowfreq_structures.csv"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
)
DEFAULT_SUMMARY = (
    REPOSITORY_ROOT / "probes" / "dielectric_observations_v11plus_summary.json"
)

ZERO_FREQUENCY_ORIGIN = "thermoml_zero_frequency"
LOW_FREQUENCY_ORIGIN = "thermoml_low_frequency"
ZERO_FREQUENCY_GATE = "zero_frequency"
ADMITTED_GATES = ("accepted_primary_lowfreq", "accepted_extended_lowfreq")
EXTRA_FIELDS = ("observation_origin", "frequency_gate", "smiles_source")

SMILE_SOURCE_V11 = "v11_table"
SMILE_SOURCE_CANDIDATE = "dielectric_lowfreq_candidates"
SMILE_SOURCE_STRUCTURES = "dielectric_lowfreq_structures"


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or ())


def write_csv_rows(
    path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def normalise_key(value: str | None) -> str:
    return (value or "").strip().upper()


def load_resolved_smiles(structures: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Return InChIKey -> resolved SMILES for structurally complete compounds."""

    resolved: dict[str, str] = {}
    for row in structures:
        key = normalise_key(row.get("inchikey"))
        smiles = (row.get("resolved_smiles") or "").strip()
        if key and smiles:
            resolved[key] = smiles
    return resolved


def build_merged_rows(
    v11_rows: Sequence[Mapping[str, str]],
    v11_fields: Sequence[str],
    candidate_rows: Sequence[Mapping[str, str]],
    resolved_smiles: Mapping[str, str],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Concatenate the zero-frequency table with the admitted low-frequency rows."""

    merged: list[dict[str, str]] = []
    for row in v11_rows:
        out = {field: (row.get(field) or "") for field in v11_fields}
        out["observation_origin"] = ZERO_FREQUENCY_ORIGIN
        out["frequency_gate"] = ZERO_FREQUENCY_GATE
        out["smiles_source"] = SMILE_SOURCE_V11
        merged.append(out)

    counters = Counter()
    for row in candidate_rows:
        gate = (row.get("gate") or "").strip()
        if gate not in ADMITTED_GATES:
            counters["skipped_by_gate"] += 1
            continue
        out = {field: (row.get(field) or "") for field in v11_fields}
        key = normalise_key(row.get("inchikey"))
        if (out.get("smiles") or "").strip():
            out["smiles_source"] = SMILE_SOURCE_CANDIDATE
        elif key in resolved_smiles:
            out["smiles"] = resolved_smiles[key]
            out["smiles_source"] = SMILE_SOURCE_STRUCTURES
            counters["smiles_backfilled"] += 1
        else:
            out["smiles_source"] = ""
            counters["smiles_missing"] += 1
        out["observation_origin"] = LOW_FREQUENCY_ORIGIN
        out["frequency_gate"] = gate
        merged.append(out)
        counters[f"admitted_{gate}"] += 1

    return merged, dict(counters)


def summarise(
    merged: Sequence[Mapping[str, str]],
    v11_rows: Sequence[Mapping[str, str]],
    candidate_rows: Sequence[Mapping[str, str]],
    counters: Mapping[str, int],
) -> dict[str, Any]:
    by_origin: Counter[str] = Counter()
    origin_keys: dict[str, set[str]] = {}
    bands_by_origin: dict[str, Counter[str]] = {}
    temperatures: list[float] = []
    for row in merged:
        origin = row["observation_origin"]
        by_origin[origin] += 1
        key = normalise_key(row.get("inchikey"))
        origin_keys.setdefault(origin, set()).add(key)
        bands_by_origin.setdefault(origin, Counter())[row.get("temperature_band", "")] += 1
        try:
            temperatures.append(float(row.get("T_K") or ""))
        except ValueError:
            pass

    keys = {normalise_key(row.get("inchikey")) for row in merged}
    keys.discard("")
    v11_keys = {normalise_key(row.get("inchikey")) for row in v11_rows}
    v11_keys.discard("")
    admitted_keys = set(origin_keys.get(LOW_FREQUENCY_ORIGIN, set()))
    admitted_keys.discard("")

    smiles_present = sum(1 for row in merged if (row.get("smiles") or "").strip())
    return {
        "rows": len(merged),
        "compounds": len(keys),
        "rows_by_origin": dict(by_origin),
        "compounds_by_origin": {
            origin: len(value) for origin, value in sorted(origin_keys.items())
        },
        "band_counts_by_origin": {
            origin: dict(sorted(counter.items()))
            for origin, counter in sorted(bands_by_origin.items())
        },
        "band_counts_total": dict(
            sorted(Counter(row.get("temperature_band", "") for row in merged).items())
        ),
        "temperature_k": {
            "min": round(min(temperatures), 2) if temperatures else None,
            "max": round(max(temperatures), 2) if temperatures else None,
        },
        "compounds_added_over_v11": len(keys - v11_keys),
        "compounds_added_list": sorted(keys - v11_keys),
        "compounds_only_in_v11": len(v11_keys - keys),
        "admitted_compounds_already_in_v11": len(admitted_keys & v11_keys),
        "origin_overlap_rows": _origin_overlap(merged),
        "rows_with_smiles": smiles_present,
        "rows_missing_smiles": len(merged) - smiles_present,
        "rows_missing_source_doi": sum(
            1 for row in merged if not (row.get("source_doi") or "").strip()
        ),
        "source_dois": len(
            {
                (row.get("source_doi") or "").strip()
                for row in merged
                if (row.get("source_doi") or "").strip()
            }
        ),
        "inputs": {
            "v11_rows": len(v11_rows),
            "candidate_rows": len(candidate_rows),
        },
        "gate_counters": dict(sorted(counters.items())),
    }


def _origin_overlap(merged: Sequence[Mapping[str, str]]) -> int:
    """Rows whose (compound, temperature) pair appears in both origins."""

    seen: dict[tuple[str, str], set[str]] = {}
    for row in merged:
        key = (normalise_key(row.get("inchikey")), (row.get("T_K") or "").strip())
        seen.setdefault(key, set()).add(row["observation_origin"])
    return sum(1 for origins in seen.values() if len(origins) > 1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v11", type=Path, default=V11_PATH)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_PATH)
    parser.add_argument("--structures", type=Path, default=STRUCTURES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def run(
    *,
    v11_path: Path,
    candidates_path: Path,
    structures_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    """Build the merged table and its summary, returning the summary."""

    v11_rows, v11_fields = read_csv_rows(v11_path)
    candidate_rows, _ = read_csv_rows(candidates_path)
    structure_rows, _ = read_csv_rows(structures_path)

    resolved_smiles = load_resolved_smiles(structure_rows)
    merged, counters = build_merged_rows(
        v11_rows, v11_fields, candidate_rows, resolved_smiles
    )
    fieldnames = list(v11_fields) + list(EXTRA_FIELDS)
    write_csv_rows(output_path, fieldnames, merged)

    summary = summarise(merged, v11_rows, candidate_rows, counters)
    summary["outputs"] = {
        "table": _relative(output_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return summary


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = _parse_args()
    summary = run(
        v11_path=args.v11,
        candidates_path=args.candidates,
        structures_path=args.structures,
        output_path=args.output,
        summary_path=args.summary,
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "rows",
                    "compounds",
                    "compounds_added_over_v11",
                    "rows_missing_smiles",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())