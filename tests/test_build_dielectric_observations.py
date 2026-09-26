from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_dielectric_observations import (
    OBSERVATION_FIELDS,
    build_observation_rows,
    select_observations,
    temperature_band,
)
from scripts.verify_dielectric_observations import check_observations

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv"
RAW_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"
ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_observations_v11_summary.json"


def raw_row(**overrides: str) -> dict[str, str]:
    row = {
        "source_file": "E:/repo/data/raw/thermoml/example.xml",
        "source_sha256": "a" * 64,
        "doi": "10.1000/example",
        "dataset_number": "1",
        "property_name": "Relative permittivity at zero frequency",
        "property_family": "zero_frequency",
        "value": "12.5",
        "unit": "",
        "expanded_uncertainty": "0.1",
        "standard_uncertainty": "",
        "uncertainty_kind": "expanded",
        "confidence_level": "0.95",
        "temperature_k": "298.15",
        "pressure_kpa": "101.325",
        "frequency_mhz": "",
        "phase": "Liquid",
        "method": "",
        "component_count": "1",
        "is_pure": "True",
        "primary_name": "example",
        "primary_formula": "C2H6O",
        "primary_inchi": "",
        "primary_inchi_key": "AAAA-BBBB-CCCC",
        "components_json": "[]",
    }
    row.update(overrides)
    return row


def roster_row(**overrides: str) -> dict[str, str]:
    row = {
        "inchikey": "AAAA-BBBB-CCCC",
        "name": "example",
        "smiles": "CCO",
        "T_K": "298.15",
        "dielectric": "12.5",
        "model_ready": "true",
    }
    row.update(overrides)
    return row


def test_temperature_band_covers_the_declared_windows() -> None:
    assert temperature_band(293.15) == "room_temperature"
    assert temperature_band(303.15) == "room_temperature"
    assert temperature_band(313.15) == "extended_temperature"
    assert temperature_band(323.15) == "extended_temperature"


def test_temperature_band_labels_anything_else_rather_than_dropping_it() -> None:
    assert temperature_band(303.16) == "outside_declared_window"
    assert temperature_band(313.14) == "outside_declared_window"
    assert temperature_band(223.02) == "outside_declared_window"
    assert temperature_band(406.64) == "outside_declared_window"


def test_select_observations_counts_every_drop_reason() -> None:
    rows = [
        raw_row(is_pure="False"),
        raw_row(property_family="frequency_dependent"),
        raw_row(phase="Gas"),
        raw_row(value="0.0"),
        raw_row(temperature_k=""),
        raw_row(doi=""),
        raw_row(),
    ]

    selected, dropped = select_observations(rows)

    assert [index for index, _ in selected] == [6]
    assert dropped == {
        "not_pure_component": 1,
        "frequency_dependent": 1,
        "non_liquid_phase": 1,
        "non_positive_or_missing_value": 1,
        "missing_temperature": 1,
        "missing_source_doi": 1,
    }


def test_build_observation_rows_flags_duplicates_and_same_temperature_conflicts() -> None:
    rows = [raw_row(), raw_row(), raw_row(value="13.0")]

    built, dropped, structure = build_observation_rows(rows, [roster_row()])

    assert dropped == {}
    assert len(built) == 3
    assert set(built[0]) == set(OBSERVATION_FIELDS)
    assert {row["name"] for row in built} == {"example"}
    assert {row["smiles"] for row in built} == {"CCO"}
    assert {row["in_roster"] for row in built} == {"true"}
    assert {row["model_ready"] for row in built} == {"true"}
    assert [row["duplicate_observation_count"] for row in built] == ["2", "2", "1"]
    assert {row["distinct_values_at_temperature"] for row in built} == {"2"}
    assert {row["multiple_values_at_temperature"] for row in built} == {"true"}
    assert structure == {
        "temperature_pairs": 1,
        "temperature_pairs_with_multiple_values": 1,
        "duplicate_observations": 1,
    }


def test_build_observation_rows_keeps_compounds_outside_the_roster() -> None:
    rows = [raw_row(primary_inchi_key="ZZZZ-ZZZZ-ZZZZ")]

    built, _, _ = build_observation_rows(rows, [roster_row()])

    assert built[0]["in_roster"] == "false"
    assert built[0]["model_ready"] == ""
    assert built[0]["smiles"] == ""
    assert built[0]["name"] == "example"


@pytest.mark.skipif(
    not (OBSERVATIONS_PATH.is_file() and RAW_PATH.is_file()),
    reason="the v1.x observation table has not been built in this tree",
)
def test_committed_observation_table_passes_its_verifier() -> None:
    failures = check_observations(
        OBSERVATIONS_PATH, RAW_PATH, ROSTER_PATH, SUMMARY_PATH
    )

    assert failures == []


@pytest.mark.skipif(
    not OBSERVATIONS_PATH.is_file(),
    reason="the v1.x observation table has not been built in this tree",
)
def test_observation_table_actually_opens_the_temperature_gate() -> None:
    import csv

    with OBSERVATIONS_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    outside = [row for row in rows if row["temperature_band"] == "outside_declared_window"]
    assert len(rows) >= 1200
    assert len(outside) >= 900
    assert {row["source_doi"] for row in rows} and all(
        row["source_doi"].strip() for row in rows
    )