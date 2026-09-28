"""Literal pins for the Week 20 W20-7 label rule and provenance sidecar.

The normative sentence, the closed role vocabulary and the sidecar counts are
pinned here so a silent edit to the rule, to a role spelling or to a frozen
layer table turns this file red.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_label_provenance as provenance

CHARTER = REPOSITORY_ROOT / "reports" / "week20_project_charter.md"
SIDECAR = REPOSITORY_ROOT / "data" / "processed" / "four_core_label_provenance_sidecar.csv"
PREREG = REPOSITORY_ROOT / "probes" / "w20_label_provenance_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_label_provenance_summary.json"

REGISTRY_COVERAGE = {
    "dielectric": 247,
    "viscosity": 1228,
    "orbitals": 29868,
    "redox_label": 392,
    "density": 2178,
    "liquid_window": 218,
}

ROLE_TALLY = {
    "primary_reference": 255254,
    "calibrated_estimate": 1250,
    "reference_only": 5259,
    "feature_only": 0,
}


def test_rule_sentence_is_verbatim_from_the_charter() -> None:
    charter = CHARTER.read_text(encoding="utf-8")
    assert provenance.LABEL_RULE_SENTENCE in charter
    assert "ML 预测值永不入池" in provenance.LABEL_RULE_SENTENCE
    assert "受限许可值永不入池" in provenance.LABEL_RULE_SENTENCE
    assert "同源同水平" in provenance.LABEL_RULE_SENTENCE


def test_dft_is_registered_as_the_label_not_as_a_computed_value() -> None:
    levels = provenance.DFT_IS_THE_LABEL
    assert levels["orbitals_primary"] == "Batt-P30K = wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)"
    assert levels["orbitals_second"] == "PubChemQC = B3LYP/6-31G*//PM6"
    assert "GFN2-xTB" in levels["orbitals_third"]
    assert "predicted_not_experimental" in levels["banned_1"]


def test_role_vocabulary_is_closed_and_aliases_are_mapped() -> None:
    assert provenance.ROLES == (
        "primary_reference",
        "calibrated_estimate",
        "reference_only",
        "feature_only",
    )
    assert provenance._mapped_role("paired_anchor") == "reference_only"
    assert provenance._mapped_role("uncalibrated_reference") == "reference_only"
    assert provenance._mapped_role("calibrated_estimate") == "calibrated_estimate"
    with pytest.raises(ValueError):
        provenance._mapped_role("something_new")
    for row in provenance.sidecar_rows():
        assert row["role"] in provenance.ROLES
        assert row["access_class"] in provenance.ACCESS_CLASSES


def test_restricted_and_never_pooled_values_are_not_primary() -> None:
    for row in provenance.sidecar_rows():
        if row["access_class"] == "noncommercial":
            assert row["role"] != "primary_reference", row
        assert "predicted" not in row["reference_level"].lower()


def test_registry_coverage_is_literal() -> None:
    coverage = provenance.registry_coverage()
    assert coverage == REGISTRY_COVERAGE
    assert sum(coverage.values()) == 34131


def test_scattered_provenance_survey_is_literal() -> None:
    scattered = provenance.scattered_provenance_columns()
    assert scattered["files"] == 8
    assert scattered["columns_total"] == 75
    assert len(scattered["per_file"]["data/dielectric_v04.csv"]) == 18


def test_sidecar_is_written_with_the_pinned_schema_and_counts() -> None:
    assert SIDECAR.is_file()
    with SIDECAR.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(provenance.SIDECAR_COLUMNS)
        rows = list(reader)
    assert len(rows) == 11
    numbers = {}
    for row in rows:
        key = (row["channel"], row["source_layer"], row["role"], row["calibration_id"])
        assert key not in numbers
        numbers[key] = int(row["n_rows"])
    assert numbers[("orbitals", "batt_p30k_primary", "primary_reference", "")] == 29519
    assert numbers[("orbitals", "pubchemqc_second_source", "calibrated_estimate", "linear_2fold_v1")] == 801
    assert numbers[("liquid_window", "liquid_window_features", "reference_only", "")] == 314
    assert numbers[("density", "density_v01", "primary_reference", "")] == 182154


def test_generated_sidecar_matches_a_fresh_build() -> None:
    fresh = provenance.sidecar_rows()
    with SIDECAR.open("r", encoding="utf-8", newline="") as handle:
        on_disk = [dict(row) for row in csv.DictReader(handle)]
    assert on_disk == fresh


def test_summary_and_prereg_register_without_readings() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["produces_reading"] is False
    assert prereg["promoted"] is False
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["models_fitted"] == 0
    assert prereg["sidecar"]["charter_fields"] == [
        "channel",
        "role",
        "reference_level",
        "calibration_id",
        "source_doi",
        "locator_table_figure",
        "access_class",
    ]

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["produces_reading"] is False
    assert summary["promoted"] is False
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["sidecar_rows"] == 11
    assert summary["after_columns"] == 9
    assert summary["registry_coverage"] == REGISTRY_COVERAGE
    assert summary["registry_coverage_total"] == 34131
    assert summary["role_tally"] == ROLE_TALLY
