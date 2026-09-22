from __future__ import annotations

from scripts.verify_week1 import (
    check_gate_flags,
    check_intersection_rows,
    check_p2_diagnostics,
)


def test_verify_week1_rejects_unknown_gate_flag() -> None:
    result = check_gate_flags(
        "fixture.csv",
        [{"gate_flags": "experimental|unknown_flag"}],
    )

    assert result.passed is False
    assert "unknown_flag" in result.detail


def test_verify_week1_rejects_intersection_count_mismatch() -> None:
    result = check_intersection_rows(
        [
            {
                "inchikey": "AAAA-BBBB-C",
                "temperature_delta_K": "0",
                "model_ready": "false",
                "pair_type": "loose_join",
                "gate_flags": "experimental|not_training_ready",
            }
        ]
    )

    assert result.passed is False
    assert "456" in result.detail


def test_verify_week1_rejects_wrong_p2_diagnostic_unit() -> None:
    result = check_p2_diagnostics(
        {
            "target_unit": "unknown",
            "target_distribution": {},
            "stratified_test_metrics": {},
            "model_comparison": {},
        }
    )

    assert result.passed is False
    assert "atomic_units" in result.detail
