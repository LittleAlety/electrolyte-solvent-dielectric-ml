"""Independently verify `data/processed/dielectric_observations_v11.csv`.

The builder and this verifier deliberately share no selection code: the checks
below re-derive the expected table straight from `data/processed/dielectric_raw.csv`
and then compare. That is the point of the layer - a builder bug that quietly
drops or mislabels rows has to survive an independent recomputation.

Checks:
1. the committed row count equals the independently selected row count;
2. every committed row carries a source DOI and a source file hash;
3. the (inchikey, T_K, epsilon) multiset matches the recomputation exactly;
4. no committed row is a mixture, a frequency-dependent value or a non-liquid;
5. the temperature band label matches the committed temperature;
6. `duplicate_observation_count` and the two conflict columns recompute;
7. the roster join (name, SMILES, model_ready) matches `data/dielectric_v03.csv`;
8. the summary JSON agrees with the table it describes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

ROOM_TEMPERATURE_RANGE_K = (293.15, 303.15)
EXTENDED_TEMPERATURE_RANGE_K = (313.15, 323.15)
OUTSIDE_WINDOW_BAND = "outside_declared_window"
TOLERANCE = 1e-5

#: Number of independent checks `check_observations` performs.
CHECK_COUNT = 8


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def label(temperature_k: float) -> str:
    room_min, room_max = ROOM_TEMPERATURE_RANGE_K
    if room_min <= temperature_k <= room_max:
        return "room_temperature"
    extended_min, extended_max = EXTENDED_TEMPERATURE_RANGE_K
    if extended_min <= temperature_k <= extended_max:
        return "extended_temperature"
    return OUTSIDE_WINDOW_BAND


def independent_selection(
    raw_rows: Sequence[Mapping[str, str]],
) -> list[tuple[str, float, float, str]]:
    selected: list[tuple[str, float, float, str]] = []
    for row in raw_rows:
        if row.get("is_pure", "").strip().lower() != "true":
            continue
        if row.get("property_family", "") != "zero_frequency":
            continue
        if row.get("phase", "") != "Liquid":
            continue
        if not row.get("doi", "").strip():
            continue
        value = number(row.get("value"))
        temperature = number(row.get("temperature_k"))
        if value is None or value <= 0.0 or temperature is None:
            continue
        selected.append(
            (row["primary_inchi_key"], temperature, value, row.get("source_file", ""))
        )
    return selected


def check_observations(
    table_path: Path,
    raw_path: Path,
    roster_path: Path,
    summary_path: Path,
) -> list[str]:
    failures: list[str] = []
    table = read_csv_rows(table_path)
    raw = read_csv_rows(raw_path)
    roster = {row["inchikey"]: row for row in read_csv_rows(roster_path)}
    expected = independent_selection(raw)

    if len(table) != len(expected):
        failures.append(f"row count: table has {len(table)}, recomputation has {len(expected)}")

    missing_doi = [row for row in table if not row.get("source_doi", "").strip()]
    if missing_doi:
        failures.append(f"{len(missing_doi)} rows carry no source DOI")
    missing_hash = [row for row in table if not row.get("source_file_sha256", "").strip()]
    if missing_hash:
        failures.append(f"{len(missing_hash)} rows carry no source file hash")

    expected_multiset = Counter(
        (key, round(temperature, 6), round(value, 6)) for key, temperature, value, _ in expected
    )
    actual_multiset = Counter(
        (
            row["inchikey"],
            round(number(row["T_K"]) or 0.0, 6),
            round(number(row["epsilon"]) or 0.0, 6),
        )
        for row in table
    )
    if actual_multiset != expected_multiset:
        only_table = sum((actual_multiset - expected_multiset).values())
        only_raw = sum((expected_multiset - actual_multiset).values())
        failures.append(
            f"observation multiset differs: {only_table} only in the table, "
            f"{only_raw} only in the recomputation"
        )

    bad_family = [row for row in table if row["property_family"] != "zero_frequency"]
    bad_phase = [row for row in table if row["phase"] != "Liquid"]
    if bad_family:
        failures.append(f"{len(bad_family)} rows are not zero-frequency observations")
    if bad_phase:
        failures.append(f"{len(bad_phase)} rows are not liquid-phase observations")

    wrong_band = [
        row
        for row in table
        if row["temperature_band"] != label(number(row["T_K"]) or float("nan"))
    ]
    if wrong_band:
        failures.append(f"{len(wrong_band)} rows carry the wrong temperature band")

    recomputed_duplicates = Counter(
        (key, round(temperature, 6), round(value, 6), source)
        for key, temperature, value, source in expected
    )
    distinct_at_temperature: dict[tuple[str, float], set[float]] = {}
    for key, temperature, value, _ in expected:
        distinct_at_temperature.setdefault((key, round(temperature, 6)), set()).add(
            round(value, 6)
        )
    # ThermoML XML basenames are unique, so they map a portable table path back
    # to the raw absolute path without re-resolving the repository root.
    raw_source_by_basename = {
        Path(item[3]).name: item[3] for item in expected
    }
    for row in table:
        key = row["inchikey"]
        temperature = round(number(row["T_K"]) or 0.0, 6)
        value = round(number(row["epsilon"]) or 0.0, 6)
        basename = row["source_file"].rsplit("/", 1)[-1]
        raw_source = raw_source_by_basename.get(basename)
        if raw_source is None:
            failures.append(f"{key}: source file {basename} is absent from the raw table")
            continue
        duplicate = recomputed_duplicates[(key, temperature, value, raw_source)]
        if int(row["duplicate_observation_count"]) != duplicate:
            failures.append(
                f"{key}@{row['T_K']}: duplicate_observation_count "
                f"{row['duplicate_observation_count']} != {duplicate}"
            )
        distinct = len(distinct_at_temperature[(key, temperature)])
        if int(row["distinct_values_at_temperature"]) != distinct:
            failures.append(
                f"{key}@{row['T_K']}: distinct_values_at_temperature "
                f"{row['distinct_values_at_temperature']} != {distinct}"
            )
        expected_flag = "true" if distinct > 1 else "false"
        if row["multiple_values_at_temperature"] != expected_flag:
            failures.append(
                f"{key}@{row['T_K']}: multiple_values_at_temperature is "
                f"{row['multiple_values_at_temperature']}, expected {expected_flag}"
            )

    for row in table:
        member = roster.get(row["inchikey"])
        expected_membership = "true" if member else "false"
        if row["in_roster"] != expected_membership:
            failures.append(
                f"{row['inchikey']}: in_roster is {row['in_roster']}, "
                f"expected {expected_membership}"
            )
            continue
        if member is None:
            continue
        if row["name"] != member["name"] or row["smiles"] != member["smiles"]:
            failures.append(f"{row['inchikey']}: roster identity fields disagree")
        if row["model_ready"] != member["model_ready"]:
            failures.append(f"{row['inchikey']}: model_ready disagrees with the roster")

    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for field, value in (
            ("rows", len(table)),
            ("compounds", len({row["inchikey"] for row in table})),
            ("source_dois", len({row["source_doi"] for row in table})),
        ):
            if summary.get(field) != value:
                failures.append(f"summary {field}: {summary.get(field)} != {value}")
        band_counts = Counter(row["temperature_band"] for row in table)
        if summary.get("band_counts") != dict(sorted(band_counts.items())):
            failures.append("summary band_counts disagree with the table")
    else:
        failures.append(f"summary file is missing: {summary_path}")

    return failures


def main(argv: list[str] | None = None) -> int:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        type=Path,
        default=data_dir / "processed" / "dielectric_observations_v11.csv",
    )
    parser.add_argument("--raw", type=Path, default=data_dir / "processed" / "dielectric_raw.csv")
    parser.add_argument("--roster", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_observations_v11_summary.json",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    failures = check_observations(args.table, args.raw, args.roster, args.summary)
    if args.json:
        print(
            json.dumps(
                {
                    "artifact": str(args.table),
                    "passed": not failures,
                    "checks": CHECK_COUNT,
                    "failures": failures,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failures else 0
    if failures:
        print("dielectric observation table: NOT verified", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"dielectric observation table: {CHECK_COUNT}/{CHECK_COUNT} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())