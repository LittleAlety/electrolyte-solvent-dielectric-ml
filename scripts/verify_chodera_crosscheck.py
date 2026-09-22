"""Independently verify Chodera cross-check evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _driver_note(delta_t: Decimal) -> str:
    absolute = abs(delta_t)
    if absolute <= Decimal("0.05"):
        return "near_isothermal_pair_not_temperature_explained"
    if absolute >= Decimal(1):
        return "temperature_gap_ge_1K_possible_but_not_proven"
    return "small_temperature_gap_insufficient_to_assign_driver"


def _rebuild_crosscheck(
    observations: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    p1_by_key: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    chodera_by_key: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in observations:
        if row.get("dataset_source") == "P1 ThermoML":
            p1_by_key[str(row["inchikey"])].append(row)
        elif row.get("dataset_source") == "Chodera 2015":
            chodera_by_key[str(row["inchikey"])].append(row)
    rows: list[dict[str, str]] = []
    for inchikey in sorted(set(p1_by_key).intersection(chodera_by_key)):
        p1_rows = p1_by_key[inchikey]
        chodera_rows = chodera_by_key[inchikey]
        p1_median = _median([Decimal(row["dielectric"]) for row in p1_rows])
        chodera_median = _median(
            [Decimal(row["dielectric"]) for row in chodera_rows]
        )
        pairs = []
        for p1_index, p1_row in enumerate(p1_rows):
            for chodera_index, chodera_row in enumerate(chodera_rows):
                p1_temperature = Decimal(p1_row["T_K"])
                chodera_temperature = Decimal(chodera_row["T_K"])
                p1_value = Decimal(p1_row["dielectric"])
                chodera_value = Decimal(chodera_row["dielectric"])
                delta_t = abs(chodera_temperature - p1_temperature)
                relative_delta = (
                    abs((chodera_value - p1_value) / p1_value)
                    if p1_value
                    else Decimal(0)
                )
                pairs.append(
                    (
                        delta_t,
                        relative_delta,
                        p1_index,
                        chodera_index,
                    )
                )
        _, _, p1_index, chodera_index = min(pairs)
        p1_pair = p1_rows[p1_index]
        chodera_pair = chodera_rows[chodera_index]
        p1_temperature = Decimal(p1_pair["T_K"])
        chodera_temperature = Decimal(chodera_pair["T_K"])
        p1_value = Decimal(p1_pair["dielectric"])
        chodera_value = Decimal(chodera_pair["dielectric"])
        pair_delta = chodera_value - p1_value
        relative_delta_percent = (
            pair_delta / p1_value * Decimal(100) if p1_value else Decimal(0)
        )
        rows.append(
            {
                "inchikey": inchikey,
                "smiles": p1_rows[0]["smiles"],
                "name": p1_rows[0]["name"],
                "p1_n": str(len(p1_rows)),
                "chodera_n": str(len(chodera_rows)),
                "p1_median": _text(p1_median),
                "chodera_median": _text(chodera_median),
                "median_difference": _text(chodera_median - p1_median),
                "nearest_p1_T_K": _text(p1_temperature),
                "nearest_chodera_T_K": _text(chodera_temperature),
                "pair_delta_T_K": _text(chodera_temperature - p1_temperature),
                "pair_p1_value": _text(p1_value),
                "pair_chodera_value": _text(chodera_value),
                "pair_value_delta": _text(pair_delta),
                "relative_delta_percent": _text(relative_delta_percent),
                "p1_temps_K": "|".join(
                    _text(Decimal(row["T_K"])) for row in p1_rows
                ),
                "chodera_temps_K": "|".join(
                    _text(Decimal(row["T_K"])) for row in chodera_rows
                ),
                "p1_source_doi": ";".join(
                    sorted({row["source_doi"] for row in p1_rows})
                ),
                "chodera_source_doi": ";".join(
                    sorted({row["source_doi"] for row in chodera_rows})
                ),
                "driver_note": _driver_note(
                    chodera_temperature - p1_temperature
                ),
            }
        )
    return rows


def check_crosscheck_rows(rows: Sequence[Mapping[str, str]]) -> Check:
    for row in rows:
        try:
            p1_median = Decimal(row["p1_median"])
            chodera_median = Decimal(row["chodera_median"])
            difference = Decimal(row["median_difference"])
            p1_value = Decimal(row["pair_p1_value"])
            chodera_value = Decimal(row["pair_chodera_value"])
            pair_delta = Decimal(row["pair_value_delta"])
            relative_delta = Decimal(row["relative_delta_percent"])
        except (KeyError, ArithmeticError) as exc:
            return Check("Chodera crosscheck rows", False, f"invalid row: {exc}")
        if difference != chodera_median - p1_median:
            return Check(
                "Chodera crosscheck rows",
                False,
                f"median_difference mismatch for {row.get('inchikey')}",
            )
        if pair_delta != chodera_value - p1_value:
            return Check(
                "Chodera crosscheck rows",
                False,
                f"pair_value_delta mismatch for {row.get('inchikey')}",
            )
        expected_relative = (
            pair_delta / p1_value * Decimal(100) if p1_value else Decimal(0)
        )
        if relative_delta != expected_relative:
            return Check(
                "Chodera crosscheck rows",
                False,
                f"relative_delta_percent mismatch for {row.get('inchikey')}",
            )
    return Check("Chodera crosscheck rows", True, "per-row arithmetic is consistent")


def check_crosscheck_summary(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    differences = [abs(Decimal(row["median_difference"])) for row in rows]
    gaps = [abs(Decimal(row["pair_delta_T_K"])) for row in rows]
    expected_median = _median(differences)
    expected_max_delta = max(differences)
    expected_gap_min = min(gaps)
    expected_gap_median = _median(gaps)
    expected_gap_max = max(gaps)
    gap_stats = summary.get("temperature_gap_stats_K")
    if not isinstance(gap_stats, Mapping):
        return Check("Chodera crosscheck summary", False, "temperature gap stats missing")
    if Decimal(str(summary["median_abs_delta"])) != expected_median:
        return Check("Chodera crosscheck summary", False, "median_abs_delta mismatch")
    if Decimal(str(summary["max_abs_delta"])) != expected_max_delta:
        return Check("Chodera crosscheck summary", False, "max_abs_delta mismatch")
    if (
        Decimal(str(gap_stats["min"])) != expected_gap_min
        or Decimal(str(gap_stats["median"])) != expected_gap_median
        or Decimal(str(gap_stats["max"])) != expected_gap_max
    ):
        return Check("Chodera crosscheck summary", False, "max/min/median gap mismatch")
    near_isothermal = sum(abs(Decimal(row["pair_delta_T_K"])) <= Decimal("0.05") for row in rows)
    gap_ge_1k = sum(abs(Decimal(row["pair_delta_T_K"])) >= Decimal(1) for row in rows)
    assessment = summary.get("temperature_explanation_assessment")
    if not isinstance(assessment, Mapping):
        return Check("Chodera crosscheck summary", False, "assessment missing")
    if (
        assessment.get("near_isothermal_keys_not_temperature_explained")
        != near_isothermal
        or assessment.get(
            "temperature_gap_ge_1K_keys_temperature_may_contribute_but_not_proven"
        )
        != gap_ge_1k
        or assessment.get("remaining_keys_insufficient_evidence")
        != len(rows) - near_isothermal - gap_ge_1k
    ):
        return Check("Chodera crosscheck summary", False, "assessment mismatch")
    expected_top10 = [
        {
            "inchikey": row["inchikey"],
            "name": row["name"],
            "median_difference": row["median_difference"],
            "pair_delta_T_K": row["pair_delta_T_K"],
            "driver_note": row["driver_note"],
        }
        for row in sorted(
            rows,
            key=lambda row: abs(Decimal(row["median_difference"])),
            reverse=True,
        )[:10]
    ]
    if summary.get("top10_abs_median_difference") != expected_top10:
        return Check("Chodera crosscheck summary", False, "Top10 mismatch")
    return Check("Chodera crosscheck summary", True, "summary and Top10 reproduced")


def run_checks(root: Path = ROOT) -> list[Check]:
    observations_path = root / "data" / "processed" / "dielectric_v01_observations.csv"
    crosscheck_path = root / "data" / "processed" / "chodera_crosscheck.csv"
    summary_path = root / "probes" / "chodera_crosscheck_summary.json"
    plot_path = root / "probes" / "artifacts" / "chodera_crosscheck.png"
    missing = [
        str(path)
        for path in (observations_path, crosscheck_path, summary_path, plot_path)
        if not path.is_file()
    ]
    if missing:
        return [Check("Chodera crosscheck artifacts", False, f"missing: {missing}")]
    actual_rows = read_csv_rows(crosscheck_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_rows = _rebuild_crosscheck(read_csv_rows(observations_path))
    checks = [
        Check(
            "Chodera crosscheck count",
            len(actual_rows) == 45 and len(expected_rows) == 45,
            f"actual={len(actual_rows)}, independently rebuilt={len(expected_rows)}",
        ),
        check_crosscheck_rows(actual_rows),
    ]
    if len(actual_rows) != len(expected_rows):
        return checks
    expected_by_key = {row["inchikey"]: row for row in expected_rows}
    for actual in actual_rows:
        expected = expected_by_key.get(actual["inchikey"])
        if expected is None:
            checks.append(
                Check(
                    "Chodera crosscheck rows",
                    False,
                    f"unexpected key {actual['inchikey']}",
                )
            )
            return checks
        for column in expected:
            if actual.get(column) != expected[column]:
                checks.append(
                    Check(
                        "Chodera crosscheck rows",
                        False,
                        f"{column} mismatch for {actual['inchikey']}",
                    )
                )
                return checks
    checks.append(check_crosscheck_summary(actual_rows, summary))
    return checks


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    output = stdout if stdout is not None else sys.stdout
    if args.json:
        print(
            json.dumps(
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
                ensure_ascii=False,
                indent=2,
            ),
            file=output,
        )
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=output)
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed", file=output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
