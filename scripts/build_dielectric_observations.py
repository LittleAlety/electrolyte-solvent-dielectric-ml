"""Build the v1.x temperature-resolved dielectric observation table.

v1.0 ships one near-room-temperature value per compound. The local ThermoML
cache already holds the full permittivity series for the compounds it covers:
the v0.3 ingest kept only the 293.15-303.15 K window, so every other point in
those series was parsed and then dropped. This builder opens that gate and emits
one row per pure-component, zero-frequency, liquid observation, carrying the
provenance fields the dataset already requires.

The released artifacts are untouched. `data/dielectric_v03.csv`, its digest and
the frozen 236-row benchmark are read-only inputs here; the observation table is
a new artifact derived from `data/processed/dielectric_raw.csv` plus the roster
(joined for SMILES, names and the `model_ready` gate).
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
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

ROOM_TEMPERATURE_RANGE_K = (293.15, 303.15)
EXTENDED_TEMPERATURE_RANGE_K = (313.15, 323.15)

#: The observation table is deliberately unfiltered in temperature: the whole
#: point is to stop discarding the series. Rows outside the declared schema
#: windows are labelled rather than dropped, so a downstream fit can choose.
OUTSIDE_WINDOW_BAND = "outside_declared_window"

OBSERVATION_FIELDS = (
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "epsilon",
    "epsilon_unit",
    "uncertainty_expanded",
    "uncertainty_standard",
    "uncertainty_kind",
    "confidence_level",
    "phase",
    "method",
    "property_family",
    "property_name",
    "frequency_mhz",
    "pressure_kpa",
    "source_doi",
    "source_file",
    "source_file_sha256",
    "source_row_index",
    "dataset_number",
    "component_count",
    "in_roster",
    "model_ready",
    "temperature_band",
    "roster_T_K",
    "roster_dielectric",
    "duplicate_observation_count",
    "distinct_values_at_temperature",
    "multiple_values_at_temperature",
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
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def temperature_band(temperature_k: float) -> str:
    """Label an observation with the schema band it falls into, if any."""

    room_min, room_max = ROOM_TEMPERATURE_RANGE_K
    if room_min <= temperature_k <= room_max:
        return "room_temperature"
    extended_min, extended_max = EXTENDED_TEMPERATURE_RANGE_K
    if extended_min <= temperature_k <= extended_max:
        return "extended_temperature"
    return OUTSIDE_WINDOW_BAND


def _float(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def roster_index(
    roster_rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    return {row["inchikey"]: row for row in roster_rows}


def select_observations(
    raw_rows: Sequence[Mapping[str, str]],
) -> tuple[list[tuple[int, Mapping[str, str]]], Counter]:
    """Return the liquid/pure/zero-frequency rows plus a drop tally.

    Every rejected row is counted by reason; nothing is discarded silently.
    """

    dropped: Counter = Counter()
    selected: list[tuple[int, Mapping[str, str]]] = []
    for index, row in enumerate(raw_rows):
        if row.get("is_pure", "").strip().lower() != "true":
            dropped["not_pure_component"] += 1
            continue
        if row.get("property_family", "") != "zero_frequency":
            dropped["frequency_dependent"] += 1
            continue
        if row.get("phase", "") != "Liquid":
            dropped["non_liquid_phase"] += 1
            continue
        value = _float(row.get("value", ""))
        temperature = _float(row.get("temperature_k", ""))
        if value is None or value <= 0.0:
            dropped["non_positive_or_missing_value"] += 1
            continue
        if temperature is None:
            dropped["missing_temperature"] += 1
            continue
        if not row.get("doi", "").strip():
            dropped["missing_source_doi"] += 1
            continue
        selected.append((index, row))
    return selected, dropped


def build_observation_rows(
    raw_rows: Sequence[Mapping[str, str]],
    roster_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], Counter, dict[str, int]]:
    selected, dropped = select_observations(raw_rows)
    roster = roster_index(roster_rows)

    duplicate_tally: Counter = Counter()
    temperature_tally: dict[tuple[str, float], set[float]] = {}
    for _, row in selected:
        key = row["primary_inchi_key"]
        temperature = round(_float(row["temperature_k"]) or 0.0, 6)
        value = round(_float(row["value"]) or 0.0, 6)
        duplicate_tally[(key, temperature, value, row.get("source_file", ""))] += 1
        temperature_tally.setdefault((key, temperature), set()).add(value)

    rows: list[dict[str, str]] = []
    for index, row in selected:
        key = row["primary_inchi_key"]
        temperature = float(row["temperature_k"])
        value = float(row["value"])
        rounded_temperature = round(temperature, 6)
        rounded_value = round(value, 6)
        member = roster.get(key)
        distinct = len(temperature_tally[(key, rounded_temperature)])
        rows.append(
            {
                "inchikey": key,
                "name": (member or {}).get("name", row.get("primary_name", "")),
                "smiles": (member or {}).get("smiles", ""),
                "T_K": _format(temperature),
                "epsilon": _format(value),
                "epsilon_unit": row.get("unit", ""),
                "uncertainty_expanded": row.get("expanded_uncertainty", ""),
                "uncertainty_standard": row.get("standard_uncertainty", ""),
                "uncertainty_kind": row.get("uncertainty_kind", ""),
                "confidence_level": row.get("confidence_level", ""),
                "phase": row.get("phase", ""),
                "method": row.get("method", ""),
                "property_family": row.get("property_family", ""),
                "property_name": row.get("property_name", ""),
                "frequency_mhz": row.get("frequency_mhz", ""),
                "pressure_kpa": row.get("pressure_kpa", ""),
                "source_doi": row.get("doi", ""),
                "source_file": portable_relative_path(
                    row.get("source_file", ""), root=REPOSITORY_ROOT
                ),
                "source_file_sha256": row.get("source_sha256", ""),
                "source_row_index": str(index),
                "dataset_number": row.get("dataset_number", ""),
                "component_count": row.get("component_count", ""),
                "in_roster": "true" if member else "false",
                "model_ready": (member or {}).get("model_ready", ""),
                "temperature_band": temperature_band(temperature),
                "roster_T_K": (member or {}).get("T_K", ""),
                "roster_dielectric": (member or {}).get("dielectric", ""),
                "duplicate_observation_count": str(
                    duplicate_tally[
                        (key, rounded_temperature, rounded_value, row.get("source_file", ""))
                    ]
                ),
                "distinct_values_at_temperature": str(distinct),
                "multiple_values_at_temperature": "true" if distinct > 1 else "false",
            }
        )

    pairs = len(temperature_tally)
    conflicting = sum(1 for values in temperature_tally.values() if len(values) > 1)
    structure = {
        "temperature_pairs": pairs,
        "temperature_pairs_with_multiple_values": conflicting,
        "duplicate_observations": sum(
            count - 1 for count in duplicate_tally.values() if count > 1
        ),
    }
    rows.sort(key=lambda item: (item["inchikey"], float(item["T_K"]), float(item["epsilon"])))
    return rows, dropped, structure


def summarize(
    rows: Sequence[Mapping[str, str]],
    dropped: Counter,
    structure: Mapping[str, int],
    *,
    raw_path: Path,
    roster_path: Path,
) -> dict[str, object]:
    bands = Counter(row["temperature_band"] for row in rows)
    compounds = {row["inchikey"] for row in rows}
    dois = {row["source_doi"] for row in rows}
    temperatures = [float(row["T_K"]) for row in rows]
    roster_members = {row["inchikey"] for row in rows if row["in_roster"] == "true"}
    ready = {
        row["inchikey"]
        for row in rows
        if row["model_ready"].strip().lower() == "true"
    }
    return {
        "inputs": {
            "raw": portable_relative_path(raw_path, root=REPOSITORY_ROOT),
            "raw_sha256": canonical_text_sha256(raw_path) if raw_path.is_file() else "",
            "roster": portable_relative_path(roster_path, root=REPOSITORY_ROOT),
            "roster_sha256": (
                canonical_text_sha256(roster_path) if roster_path.is_file() else ""
            ),
        },
        "rows": len(rows),
        "compounds": len(compounds),
        "source_dois": len(dois),
        "rows_missing_source_doi": sum(1 for row in rows if not row["source_doi"].strip()),
        "rows_missing_smiles": sum(1 for row in rows if not row["smiles"].strip()),
        "roster_members": len(roster_members),
        "roster_model_ready_compounds": len(ready),
        "temperature_k": {
            "min": min(temperatures) if temperatures else None,
            "max": max(temperatures) if temperatures else None,
        },
        "band_counts": dict(sorted(bands.items())),
        "dropped": dict(sorted(dropped.items())),
        "structure": dict(structure),
    }


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", type=Path, default=data_dir / "processed" / "dielectric_raw.csv"
    )
    parser.add_argument("--roster", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=data_dir / "processed" / "dielectric_observations_v11.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_observations_v11_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _, raw_rows = read_csv_rows(args.raw)
    _, roster_rows = read_csv_rows(args.roster)
    rows, dropped, structure = build_observation_rows(raw_rows, roster_rows)
    write_csv_rows(args.output, OBSERVATION_FIELDS, rows)
    summary = summarize(
        rows, dropped, structure, raw_path=args.raw, roster_path=args.roster
    )
    write_json(args.summary, summary)

    print(f"wrote {portable_relative_path(args.output, root=REPOSITORY_ROOT)}")
    print(f"  rows      : {summary['rows']}")
    print(f"  compounds : {summary['compounds']}")
    print(f"  source DOIs: {summary['source_dois']}")
    print(f"  bands     : {summary['band_counts']}")
    print(f"  dropped   : {summary['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
