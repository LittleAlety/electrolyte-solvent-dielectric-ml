from __future__ import annotations

import pytest

from scripts.verify_al_round1 import (
    _compare_rows,
    check_family_quota,
    check_filter_funnel,
    check_selection_no_v01_leak,
    check_source_integrity,
    classify_hazards,
)


def test_al_verifier_rejects_source_hash(tmp_path) -> None:
    path = tmp_path / "Batt-SLM.smi"
    path.write_text("CCO\n", encoding="utf-8")

    result = check_source_integrity(
        path,
        expected_sha256="0" * 64,
        expected_size=None,
    )

    assert result.passed is False
    assert "SHA256" in result.detail


def test_al_verifier_rejects_filter_count_mismatch() -> None:
    result = check_filter_funnel(
        {"parsed": 10, "deduplicated": 9},
        {"parsed": 11, "deduplicated": 9},
    )

    assert result.passed is False
    assert "parsed" in result.detail


def test_al_verifier_rejects_selection_v01_leak() -> None:
    result = check_selection_no_v01_leak(
        ["AAAA-BBBB-C"],
        {"AAAA-BBBB-C": "input molecule"},
    )

    assert result.passed is False
    assert "leak" in result.detail


def test_al_verifier_detects_alpha_halo_ether() -> None:
    assert "alpha_halo_ether" in classify_hazards("ClCOC")


def test_al_verifier_detects_halogen_oxygen_and_cumulated_thiocarbonyl() -> None:
    assert "halogen_oxygen" in classify_hazards("FOC")
    assert "halogen_oxygen" in classify_hazards("ClOC")
    assert "halogen_oxygen" in classify_hazards("BrOC")
    assert "halogen_oxygen" in classify_hazards("IOC")
    assert "thiocarbonyl" in classify_hazards("C=S=C")
    assert "thiocarbonyl" in classify_hazards("C1=S=C=C2OCCOC=12")


def test_al_verifier_rejects_family_quota_violation() -> None:
    rows = [
        {"candidate_id": str(index), "family": "OnlyFamily"} for index in range(7)
    ]

    result = check_family_quota(rows, max_per_family=6)

    assert result.passed is False
    assert "OnlyFamily" in result.detail


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("hazard_flags", "tampered"),
        ("manual_review_warnings", "tampered"),
        ("availability_status", "available"),
        ("decision_status", "selected"),
        ("selection_order", "99"),
        ("selection_step_score", "0.123456"),
        ("source_commit", "0" * 40),
        ("model_input_sha256", "0" * 64),
        ("acquisition_score", "0.0"),
        ("predicted_dielectric", "0.0"),
    ],
)
def test_al_verifier_rejects_top30_field_tamper(field, tampered) -> None:
    expected = [
        {
            "candidate_id": "candidate",
            "smiles": "CCO",
            "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "family": "Alcohols",
            "nearest_solvfunc_name": "ethanol",
            "nearest_solvfunc_category": "Alcohols",
            "max_tanimoto_solvfunc": "0.5",
            "max_tanimoto_v01": "0.5",
            "novelty": "0.5",
            "tier": "A",
            "predicted_dielectric": "20.0",
            "posterior_std": "1.0",
            "std_percentile": "0.9",
            "acquisition_score": "0.45",
            "cluster": "Alcohols",
            "hazard_flags": "",
            "manual_review_warnings": "",
            "mp_c": "",
            "bp_c": "",
            "literature_doi": "",
            "availability_status": "unknown",
            "decision_status": "awaiting_manual_review",
            "source_commit": "a" * 40,
            "model_input_sha256": "b" * 64,
            "selection_order": "1",
            "selection_step_score": "0.45",
        }
    ]
    actual = [dict(expected[0])]
    actual[0][field] = tampered

    result = _compare_rows(actual, expected, key="candidate_id")

    assert result.passed is False
    assert field in result.detail
