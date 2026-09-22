"""Build a reproducible Chodera/P1 dielectric cross-check table."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

CROSSCHECK_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "p1_n",
    "chodera_n",
    "p1_median",
    "chodera_median",
    "median_difference",
    "nearest_p1_T_K",
    "nearest_chodera_T_K",
    "pair_delta_T_K",
    "pair_p1_value",
    "pair_chodera_value",
    "pair_value_delta",
    "relative_delta_percent",
    "p1_temps_K",
    "chodera_temps_K",
    "p1_source_doi",
    "chodera_source_doi",
    "driver_note",
)


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


def build_crosscheck(
    observations: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    p1 = [row for row in observations if row.get("dataset_source") == "P1 ThermoML"]
    chodera = [
        row for row in observations if row.get("dataset_source") == "Chodera 2015"
    ]
    p1_by_key: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    chodera_by_key: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in p1:
        p1_by_key[str(row["inchikey"])].append(row)
    for row in chodera:
        chodera_by_key[str(row["inchikey"])].append(row)
    common_keys = sorted(set(p1_by_key).intersection(chodera_by_key))
    rows: list[dict[str, object]] = []
    for inchikey in common_keys:
        p1_rows = p1_by_key[inchikey]
        chodera_rows = chodera_by_key[inchikey]
        p1_median = _median([Decimal(str(row["dielectric"])) for row in p1_rows])
        chodera_median = _median(
            [Decimal(str(row["dielectric"])) for row in chodera_rows]
        )
        median_difference = chodera_median - p1_median
        pairs = [
            (
                abs(Decimal(str(ch["T_K"])) - Decimal(str(p["T_K"]))),
                abs(
                    (Decimal(str(ch["dielectric"])) - Decimal(str(p["dielectric"])))
                    / Decimal(str(p["dielectric"]))
                )
                if Decimal(str(p["dielectric"]))
                else Decimal(0),
                p1_index,
                ch_index,
            )
            for p1_index, p in enumerate(p1_rows)
            for ch_index, ch in enumerate(chodera_rows)
        ]
        _, _, p1_index, ch_index = min(pairs)
        p1_pair = p1_rows[p1_index]
        chodera_pair = chodera_rows[ch_index]
        p1_temperature = Decimal(str(p1_pair["T_K"]))
        chodera_temperature = Decimal(str(chodera_pair["T_K"]))
        p1_value = Decimal(str(p1_pair["dielectric"]))
        chodera_value = Decimal(str(chodera_pair["dielectric"]))
        pair_delta = chodera_value - p1_value
        relative_delta = (
            pair_delta / p1_value * Decimal(100) if p1_value else Decimal(0)
        )
        rows.append(
            {
                "inchikey": inchikey,
                "smiles": p1_rows[0]["smiles"],
                "name": p1_rows[0]["name"],
                "p1_n": len(p1_rows),
                "chodera_n": len(chodera_rows),
                "p1_median": _text(p1_median),
                "chodera_median": _text(chodera_median),
                "median_difference": _text(median_difference),
                "nearest_p1_T_K": _text(p1_temperature),
                "nearest_chodera_T_K": _text(chodera_temperature),
                "pair_delta_T_K": _text(chodera_temperature - p1_temperature),
                "pair_p1_value": _text(p1_value),
                "pair_chodera_value": _text(chodera_value),
                "pair_value_delta": _text(pair_delta),
                "relative_delta_percent": _text(relative_delta),
                "p1_temps_K": "|".join(
                    _text(Decimal(str(row["T_K"]))) for row in p1_rows
                ),
                "chodera_temps_K": "|".join(
                    _text(Decimal(str(row["T_K"]))) for row in chodera_rows
                ),
                "p1_source_doi": ";".join(
                    sorted({str(row["source_doi"]) for row in p1_rows})
                ),
                "chodera_source_doi": ";".join(
                    sorted({str(row["source_doi"]) for row in chodera_rows})
                ),
                "driver_note": _driver_note(
                    chodera_temperature - p1_temperature
                ),
            }
        )
    differences = [abs(float(row["median_difference"])) for row in rows]
    temperature_gaps = [abs(float(row["pair_delta_T_K"])) for row in rows]
    sorted_rows = sorted(
        rows,
        key=lambda row: abs(float(row["median_difference"])),
        reverse=True,
    )
    near_isothermal = sum(
        abs(float(row["pair_delta_T_K"])) <= 0.05 for row in rows
    )
    temperature_gap_ge_1k = sum(
        abs(float(row["pair_delta_T_K"])) >= 1.0 for row in rows
    )
    summary = {
        "schema_version": 1,
        "common_key_count": len(rows),
        "median_abs_delta": float(np.median(differences)) if differences else None,
        "max_abs_delta": max(differences) if differences else None,
        "temperature_gap_stats_K": {
            "min": min(temperature_gaps) if temperature_gaps else None,
            "median": float(np.median(temperature_gaps)) if temperature_gaps else None,
            "max": max(temperature_gaps) if temperature_gaps else None,
        },
        "temperature_explanation_assessment": {
            "near_isothermal_keys_not_temperature_explained": near_isothermal,
            "temperature_gap_ge_1K_keys_temperature_may_contribute_but_not_proven": (
                temperature_gap_ge_1k
            ),
            "remaining_keys_insufficient_evidence": (
                len(rows) - near_isothermal - temperature_gap_ge_1k
            ),
            "method_attribution": (
                "No measurement-method attribution is made without direct evidence."
            ),
        },
        "top10_abs_median_difference": [
            {
                "inchikey": row["inchikey"],
                "name": row["name"],
                "median_difference": row["median_difference"],
                "pair_delta_T_K": row["pair_delta_T_K"],
                "driver_note": row["driver_note"],
            }
            for row in sorted_rows[:10]
        ],
        "limitations": [
            "Nearest-temperature pairing does not interpolate or model temperature dependence.",
            "A temperature gap permits but does not prove temperature as the driver.",
            "No method-level cause is assigned without source evidence.",
        ],
    }
    return rows, summary


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CROSSCHECK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_plot(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    median_delta = np.asarray([float(row["median_difference"]) for row in rows])
    pair_delta_t = np.asarray([abs(float(row["pair_delta_T_K"])) for row in rows])
    abs_value_delta = np.asarray([abs(float(row["pair_value_delta"])) for row in rows])
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].hist(median_delta, bins=15, color="#2563eb", alpha=0.85)
    axes[0].set_xlabel("Chodera median - P1 median")
    axes[0].set_ylabel("Compound count")
    axes[0].set_title("Median dielectric difference")
    axes[1].scatter(pair_delta_t, abs_value_delta, color="#dc2626", alpha=0.8)
    axes[1].set_xlabel("|Nearest-pair temperature difference| (K)")
    axes[1].set_ylabel("|Nearest-pair dielectric delta|")
    axes[1].set_title("Pair delta versus temperature gap")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observations",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_v01_observations.csv"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "chodera_crosscheck.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "chodera_crosscheck_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=(
            REPOSITORY_ROOT / "probes" / "artifacts" / "chodera_crosscheck.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows, summary = build_crosscheck(read_csv_rows(args.observations))
    write_csv(args.output, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_plot(rows, args.plot)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
