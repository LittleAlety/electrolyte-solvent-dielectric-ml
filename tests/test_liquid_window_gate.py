"""Offline tests for the Week-17 liquid-window feature table and hard gate.

Nothing here touches the network.  Every test reads the committed artefacts the
builder wrote and re-derives the numbers from them, so a hand-edited row cannot
survive without a test disagreeing with it.  The gate rule is exercised through
``gate_verdict`` from the verifier, which re-implements the frozen prereg rule
independently of the builder.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.build_liquid_window_features import (
    BOILING,
    DENSITY,
    FEATURE_COLUMNS,
    FLASH,
    FROZEN_RED_LINES,
    GATE_COLUMNS,
    MELTING,
    PROPERTY_SPECS,
)
from scripts.verify_liquid_window_gate import (
    gate_verdict,
    run_checks,
    sha256_file,
)

PREREG = REPOSITORY_ROOT / "probes" / "liquid_window_gate_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json"
FEATURES = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_features.csv"
GATE = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_gate_report.csv"
UPSTREAM = REPOSITORY_ROOT / "probes" / "pubchem_liquid_window_harvest_summary.json"
IDENTITY = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_MELTING_POINT_C = 36.4
T_LOW_C, T_HIGH_C = -20.0, 60.0
COVERAGE_SET_SIZE = 314


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@pytest.fixture(scope="module")
def features() -> list[dict[str, str]]:
    return _rows(FEATURES)


@pytest.fixture(scope="module")
def gate_rows() -> list[dict[str, str]]:
    return _rows(GATE)


@pytest.fixture(scope="module")
def summary() -> dict:
    return _load(SUMMARY)


def test_prereg_is_locked_and_fixes_the_window() -> None:
    prereg = _load(PREREG)
    assert prereg["status"] == "locked_before_run"
    gate = prereg["gate"]
    assert gate["T_low_C"] == T_LOW_C
    assert gate["T_high_C"] == T_HIGH_C
    assert "mp_C > T_low_C" in gate["rule"]
    assert "bp_C < T_high_C" in gate["rule"]
    assert "unknown" in gate["unknown_policy"]


def test_reaxys_temperature_label_lesson_is_recorded() -> None:
    prereg = _load(PREREG)
    text = json.dumps(prereg["sanity_checks"], ensure_ascii=False)
    assert "Reaxys" in text
    assert "25 degC" in text
    # EC's melting point sits above 25 degC, which is exactly why a 25 degC
    # dielectric label for EC cannot be a liquid measurement.
    assert _float(_load(SUMMARY)["sanity_checks"]["EC_mp_C_in_features"]) == EC_MELTING_POINT_C
    assert EC_MELTING_POINT_C > 25.0


def test_features_schema_and_size(features: list[dict[str, str]]) -> None:
    assert tuple(features[0].keys()) == FEATURE_COLUMNS
    assert len(features) == COVERAGE_SET_SIZE


def test_features_cover_every_identity_key_once(features: list[dict[str, str]]) -> None:
    identity_keys = [row["inchikey"] for row in _rows(IDENTITY)]
    feature_keys = [row["inchikey"] for row in features]
    assert feature_keys == identity_keys
    assert len(set(feature_keys)) == COVERAGE_SET_SIZE


def test_coverage_matches_the_upstream_harvest(
    features: list[dict[str, str]], summary: dict
) -> None:
    upstream = _load(UPSTREAM)
    for spec in PROPERTY_SPECS:
        recomputed = sum(1 for row in features if row[spec.has_column] == "true")
        assert recomputed == upstream["property_coverage"][spec.name]["keys_with_parsed_value"]
    assert (
        summary["coverage"]["keys_with_melting_point"]
        == upstream["keys_with_mp_bp_fp"]["melting_point"]
    )
    assert (
        summary["coverage"]["keys_with_boiling_point"]
        == upstream["keys_with_mp_bp_fp"]["boiling_point"]
    )
    assert (
        summary["coverage"]["keys_with_flash_point"]
        == upstream["keys_with_mp_bp_fp"]["flash_point"]
    )
    all_three = sum(
        1
        for row in features
        if row["has_mp"] == "true" and row["has_bp"] == "true" and row["has_flash_point"] == "true"
    )
    assert all_three == upstream["keys_with_all_three_temperatures"] == 186


def test_primary_value_equals_the_upstream_selection(
    features: list[dict[str, str]],
) -> None:
    selected = {
        (row["inchikey"], row["property"]): row["value_numeric"]
        for row in _rows(
            REPOSITORY_ROOT
            / "data"
            / "external"
            / "g1plus"
            / "pubchem"
            / "liquid_window"
            / "liquid_window_selected.csv"
        )
    }
    index = {row["inchikey"]: row for row in features}
    for (inchikey, property_name), value_numeric in selected.items():
        spec = {s.name: s for s in PROPERTY_SPECS}[property_name]
        assert index[inchikey][spec.value_column] == value_numeric


def test_each_present_value_carries_provenance_and_a_basis(
    features: list[dict[str, str]],
) -> None:
    for row in features:
        for spec in PROPERTY_SPECS:
            if row[spec.has_column] != "true":
                continue
            assert row[f"{spec.prefix}_depositor"] or row[f"{spec.prefix}_reference_number"]
            assert row[f"{spec.prefix}_selection_rule"]
            assert row[f"{spec.prefix}_confidence"] in {"high", "medium", "low"}
            assert row["source_kind"] == "compilation"
            assert row["quality_layer"] == "filter_only"


def test_absent_values_are_empty_and_flagged(features: list[dict[str, str]]) -> None:
    for row in features:
        for spec in PROPERTY_SPECS:
            if row[spec.has_column] == "true":
                assert row[spec.value_column] != ""
                assert row[f"{spec.prefix}_confidence"] != "absent"
            else:
                assert row[spec.value_column] == ""
                assert row[f"{spec.prefix}_confidence"] == "absent"


def test_primary_sits_inside_the_alternative_range(features: list[dict[str, str]]) -> None:
    """Disagreeing depositor values are recorded, never averaged away."""

    for row in features:
        for spec in PROPERTY_SPECS:
            if row[spec.has_column] != "true":
                continue
            value = _float(row[spec.value_column])
            low = _float(row[f"{spec.prefix}_alt_min{spec.unit_suffix}"])
            high = _float(row[f"{spec.prefix}_alt_max{spec.unit_suffix}"])
            assert low is not None and high is not None
            assert low <= value <= high


def test_gate_report_recomputes_from_the_features(
    features: list[dict[str, str]], gate_rows: list[dict[str, str]]
) -> None:
    assert tuple(gate_rows[0].keys()) == GATE_COLUMNS
    assert len(gate_rows) == len(features)
    for feature_row, gate_row in zip(features, gate_rows):
        decision, reasons, unknown_reason = gate_verdict(
            _float(feature_row["mp_C"]),
            _float(feature_row["bp_C"]),
            t_low=T_LOW_C,
            t_high=T_HIGH_C,
        )
        assert gate_row["gate_decision"] == decision
        assert gate_row["trigger_reasons"] == ";".join(reasons)
        assert gate_row["unknown_reason"] == unknown_reason
        assert gate_row["T_low_C"] == "-20"
        assert gate_row["T_high_C"] == "60"


def test_gate_verdict_never_defaults_a_missing_boundary() -> None:
    # One-sided evidence still blocks: a compound that freezes at the cold end
    # is evicted whether or not its boiling point is known.
    assert gate_verdict(36.4, None, t_low=T_LOW_C, t_high=T_HIGH_C)[0] == "blocked"
    assert gate_verdict(None, 30.0, t_low=T_LOW_C, t_high=T_HIGH_C)[0] == "blocked"
    # A present value that does not fire, with the other boundary missing, is
    # unknown - neither a pass nor an evict.
    decision, reasons, unknown_reason = gate_verdict(-50.0, None, t_low=T_LOW_C, t_high=T_HIGH_C)
    assert (decision, reasons, unknown_reason) == ("unknown", [], "missing_bp")
    # Both present and neither firing is the only pass.
    assert gate_verdict(-50.0, 200.0, t_low=T_LOW_C, t_high=T_HIGH_C)[0] == "pass"


def test_unknown_is_never_defaulted_to_pass_or_evict(
    gate_rows: list[dict[str, str]],
) -> None:
    for row in gate_rows:
        if row["gate_decision"] == "pass":
            assert row["mp_C"] != "" and row["bp_C"] != ""
        if row["gate_decision"] == "unknown":
            assert row["mp_C"] == "" or row["bp_C"] == ""
            assert row["unknown_reason"] in {"missing_mp", "missing_bp", "missing_mp;missing_bp"}
        if row["gate_decision"] == "blocked":
            assert row["trigger_reasons"]


def test_trigger_rate_uses_both_readings(gate_rows: list[dict[str, str]], summary: dict) -> None:
    total = len(gate_rows)
    blocked = sum(1 for row in gate_rows if row["gate_decision"] == "blocked")
    unknown = sum(1 for row in gate_rows if row["gate_decision"] == "unknown")
    passed = sum(1 for row in gate_rows if row["gate_decision"] == "pass")
    assert blocked + unknown + passed == total == COVERAGE_SET_SIZE
    assert summary["gate"]["decision_counts"] == {
        "blocked": blocked,
        "pass": passed,
        "unknown": unknown,
    }
    assert summary["gate"]["trigger_rate_blocked_only"] == pytest.approx(blocked / total)
    assert summary["gate"]["trigger_rate_blocked_plus_unknown"] == pytest.approx(
        (blocked + unknown) / total
    )
    assert (
        summary["gate"]["trigger_rate_blocked_only"]
        <= summary["gate"]["trigger_rate_blocked_plus_unknown"]
    )
    assert summary["gate"]["trigger_rate_blocked_only"] == pytest.approx(
        summary["trigger_rate_comparison"]["liquid_window_blocked_only"]
    )


def test_ec_is_a_room_temperature_solid_and_is_blocked(
    features: list[dict[str, str]], gate_rows: list[dict[str, str]]
) -> None:
    feature_row = next(row for row in features if row["inchikey"] == EC_INCHIKEY)
    gate_row = next(row for row in gate_rows if row["inchikey"] == EC_INCHIKEY)
    assert _float(feature_row["mp_C"]) == EC_MELTING_POINT_C
    assert gate_row["gate_decision"] == "blocked"
    assert gate_row["trigger_reasons"] == "mp_above_T_low"


def test_frozen_red_lines_are_intact() -> None:
    for relative, expected in FROZEN_RED_LINES.items():
        assert sha256_file(REPOSITORY_ROOT / relative) == expected


def test_summary_telemetry_records_digests_and_stays_offline(summary: dict) -> None:
    assert summary["run_telemetry"]["network_calls"] == 0
    assert summary["run_telemetry"]["run_mode"] == "offline"
    assert summary["run_telemetry"]["models_fitted"] == 0
    assert summary["prereg"]["sha256"] == sha256_file(PREREG)
    assert summary["outputs"]["data/processed/liquid_window_features.csv"]["sha256"] == sha256_file(
        FEATURES
    )
    assert summary["outputs"]["data/processed/liquid_window_gate_report.csv"][
        "sha256"
    ] == sha256_file(GATE)


def test_offline_verifier_passes() -> None:
    payload = run_checks()
    assert payload["verification_passed"] is True
    assert payload["checks_failed"] == 0
    assert payload["failures"] == []


def test_outputs_are_lf_only() -> None:
    for path in (FEATURES, GATE, SUMMARY):
        assert b"\r" not in path.read_bytes(), path


def test_feature_column_names_include_the_required_four() -> None:
    assert {"mp_C", "bp_C", "flash_point_C", "density_g_cm3"} <= set(FEATURE_COLUMNS)
    assert {MELTING.has_column, BOILING.has_column, FLASH.has_column, DENSITY.has_column} <= set(
        FEATURE_COLUMNS
    )
