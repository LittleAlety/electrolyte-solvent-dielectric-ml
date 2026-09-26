"""Independently verify data/processed/dielectric_observations_v11plus.csv.

This verifier deliberately re-derives the expected table from the three inputs
with set/multiset logic instead of re-running the builder, so a bug in the
builder cannot hide behind a matching bug here.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

V11_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv"
CANDIDATES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_lowfreq_candidates.csv"
)
TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"

ADMITTED_GATES = ("accepted_primary_lowfreq", "accepted_extended_lowfreq")
EXTRA_FIELDS = ("observation_origin", "frequency_gate", "smiles_source")
ZERO_ORIGIN = "thermoml_zero_frequency"
LOW_ORIGIN = "thermoml_low_frequency"
OBSERVATION_COLUMNS = ("inchikey", "T_K", "epsilon", "source_doi", "source_row_index")
CHECK_COUNT = 10


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or ())


def fingerprint(row: dict[str, str]) -> tuple[str, ...]:
    key = (row.get("inchikey") or "").strip().upper()
    return (key,) + tuple((row.get(name) or "").strip() for name in OBSERVATION_COLUMNS[1:])


def check(conditions: list[tuple[str, bool, str]]) -> None:
    for name, ok, detail in conditions:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def run_checks() -> list[tuple[str, bool, str]]:
    v11, v11_fields = read_rows(V11_PATH)
    candidates, _ = read_rows(CANDIDATES_PATH)
    table, table_fields = read_rows(TABLE_PATH)

    admitted = [row for row in candidates if (row.get("gate") or "").strip() in ADMITTED_GATES]
    rejected = [row for row in candidates if (row.get("gate") or "").strip() not in ADMITTED_GATES]

    results: list[tuple[str, bool, str]] = []

    expected_fields = list(v11_fields) + list(EXTRA_FIELDS)
    results.append(
        (
            "header",
            table_fields == expected_fields,
            f"{len(table_fields)} columns, matches v11+extras={table_fields == expected_fields}",
        )
    )

    expected_rows = len(v11) + len(admitted)
    results.append(
        ("row_count", len(table) == expected_rows, f"{len(table)} == {len(v11)} + {len(admitted)}")
    )

    v11_multiset = Counter(fingerprint(row) for row in v11)
    table_zero = Counter(fingerprint(row) for row in table if row["observation_origin"] == ZERO_ORIGIN)
    results.append(
        (
            "v11_rows_preserved",
            table_zero == v11_multiset,
            f"{sum(table_zero.values())} zero-origin rows vs {sum(v11_multiset.values())} v11 rows",
        )
    )

    admitted_multiset = Counter(
        fingerprint({**row, "source_row_index": row.get("source_row_index", "")})
        for row in admitted
    )
    table_low = Counter(
        fingerprint(row) for row in table if row["observation_origin"] == LOW_ORIGIN
    )
    results.append(
        (
            "admitted_rows_present",
            table_low == admitted_multiset,
            f"{sum(table_low.values())} low-origin rows vs {sum(admitted_multiset.values())} admitted",
        )
    )

    admitted_set = set(admitted_multiset)
    rejected_present = [row for row in rejected if fingerprint(row) in admitted_set]
    results.append(
        (
            "rejected_rows_absent",
            sum(1 for row in rejected if fingerprint(row) in set(table_low)) == 0,
            f"{len(rejected)} rejected rows, {len(rejected_present)} leaked",
        )
    )

    seen: dict[tuple[str, str], set[str]] = {}
    for row in table:
        pair = ((row.get("inchikey") or "").strip().upper(), (row.get("T_K") or "").strip())
        seen.setdefault(pair, set()).add(row["observation_origin"])
    overlap = sum(1 for origins in seen.values() if len(origins) > 1)
    results.append(("origin_overlap", overlap == 0, f"{overlap} (compound, T_K) pairs in both origins"))

    missing_doi = sum(1 for row in table if not (row.get("source_doi") or "").strip())
    results.append(("source_doi_complete", missing_doi == 0, f"{missing_doi} rows without a DOI"))

    keys = {(row.get("inchikey") or "").strip().upper() for row in table}
    keys.discard("")
    low_keys = {(row.get("inchikey") or "").strip().upper() for row in table if row["observation_origin"] == LOW_ORIGIN}
    low_missing_smiles = sum(
        1
        for row in table
        if row["observation_origin"] == LOW_ORIGIN and not (row.get("smiles") or "").strip()
    )
    results.append(
        (
            "low_frequency_rows_modellable",
            low_missing_smiles == 0 and len(low_keys) == 50,
            f"{len(low_keys)} low-frequency compounds, {low_missing_smiles} rows without SMILES",
        )
    )

    frequencies = []
    for row in table:
        try:
            frequencies.append(float(row.get("T_K") or ""))
        except ValueError:
            pass
    in_range = all(218.0 <= value <= 407.0 for value in frequencies) and len(frequencies) == len(table)
    results.append(
        (
            "temperature_bounds",
            in_range,
            f"{len(frequencies)}/{len(table)} parseable, range {min(frequencies):.2f}-{max(frequencies):.2f} K",
        )
    )

    duplicates = Counter(
        (
            (row.get("inchikey") or "").strip().upper(),
            (row.get("T_K") or "").strip(),
            (row.get("epsilon") or "").strip(),
            (row.get("frequency_mhz") or "").strip(),
            (row.get("source_doi") or "").strip(),
            (row.get("source_row_index") or "").strip(),
        )
        for row in table
    )
    duplicate_rows = sum(count - 1 for count in duplicates.values() if count > 1)
    results.append(("row_uniqueness", duplicate_rows == 0, f"{duplicate_rows} duplicate rows"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    results = run_checks()
    check(results)
    failures = [name for name, ok, _ in results if not ok]
    passed = not failures
    if args.json:
        print(json.dumps({"passed": passed, "checks": len(results), "failures": failures}))
    else:
        print(f"{len(results) - len(failures)}/{len(results)} checks passed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())