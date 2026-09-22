from __future__ import annotations

from electrolyte_ml.standardize import GATE_FLAGS
from scripts.build_dielectric_v01_ext import (
    EC_INCHIKEY,
    build_extension,
)


def test_extension_gate_flags_are_registered() -> None:
    assert {
        "high_temperature_extension",
        "literature_manual_entry",
        "single_source",
        "frequency_1mhz",
    }.issubset(GATE_FLAGS)


def test_extension_adds_exact_ec_row_and_keeps_frequency_dependent() -> None:
    rows, observations, summary = build_extension([])
    ec = next(row for row in rows if row["inchikey"] == EC_INCHIKEY)

    assert len(rows) == 1
    assert len(observations) == 1
    assert ec["T_K"] == "313.15"
    assert ec["dielectric"] == "90.5"
    assert ec["frequency_MHz"] == "1"
    assert ec["property_family"] == "frequency_dependent"
    assert ec["uncertainty_text"] == "<1.5% relative"
    assert ec["source_doi"] == "10.1021/je050341y"
    assert ec["source_type"] == "literature_manual_entry"
    assert ec["gate_flags"] == (
        "high_temperature_extension|literature_manual_entry|"
        "single_source|frequency_1mhz"
    )
    assert summary["row_counts"]["total_keys"] == 1
    assert summary["row_counts"]["observation_rows"] == 1


def test_extension_counts_real_fixture_observations() -> None:
    observations = [
        {
            "property_family": "zero_frequency",
            "is_pure": "True",
            "temperature_k": "313.15",
            "primary_inchi_key": "AAAA-BBBB-C",
            "primary_inchi": "InChI=1S/CH4/h1H4",
            "primary_name": "methane",
            "value": "1.8",
            "source_file": r"C:\data\raw\thermoml\x.xml",
            "source_sha256": "0" * 64,
            "expanded_uncertainty": "",
            "standard_uncertainty": "",
            "uncertainty_kind": "",
            "confidence_level": "",
            "doi": "10.1000/example",
        }
    ]

    rows, expanded, summary = build_extension(observations)

    assert len(expanded) == 2
    assert len(rows) == 2
    assert expanded[0]["source_file"] == "data/raw/thermoml/x.xml"
    assert summary["row_counts"]["nist_keys"] == 1
    assert summary["row_counts"]["total_keys"] == 2
