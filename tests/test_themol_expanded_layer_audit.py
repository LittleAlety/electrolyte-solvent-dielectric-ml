"""Offline tests pinning the independent re-audit of the W17-17 THEMol expansion arm.

They re-run probes/audit_themol_expanded_layer.py and hold the post-fix findings
to closed / open / partially_closed, plus one behavioural probe that proves the
calibration status gate is now decided by the out-of-sample r rather than the
in-sample r.  No network, no xTB.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import audit_themol_expanded_layer as audit
from probes.build_themol_orbital_layer_expanded import (
    apply_out_of_sample_gate,
    out_of_sample_r,
)

ROSTER = REPOSITORY_ROOT / "probes/themol_registry_expansion_roster.csv"
AUDIT_JSON = REPOSITORY_ROOT / "probes/themol_expanded_layer_audit.json"
LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
ROSTER_SHA256 = "71277d2c2607dfc5efb31654e2bb668a2618ef6e830073c4aea7fcb48d0136d6"
ROSTER_ROWS = 5117
LAYER_SHA256 = "8b10b23f3da60c48cafc96cf783605180869b890ff0c5a4df7d0dd9c2036703b"
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80
EXPECTED_VERDICTS = {
    "F1": "closed",
    "F2": "closed",
    "F3": "closed",
    "F4": "closed",
    "F5": "open",
    "F6": "partially_closed",
    "F7": "closed",
    "F8": "closed",
    "F9": "closed",
}
ROUND1_VERDICTS = {
    "F1": "fail",
    "F2": "fail",
    "F3": "pass",
    "F4": "pass",
    "F5": "partial",
    "F6": "fail",
    "F7": "fail",
    "F8": "fail",
    "F9": "not_reproducible",
}


@pytest.fixture(scope="module")
def audit_result() -> dict[str, object]:
    return audit.build_audit()


def test_layer_is_the_frozen_final_snapshot() -> None:
    assert hashlib.sha256(LAYER.read_bytes()).hexdigest() == LAYER_SHA256
    assert len(audit.read_rows(LAYER)) == ROSTER_ROWS


def test_roster_bytes_and_digest_are_the_frozen_ones() -> None:
    assert hashlib.sha256(ROSTER.read_bytes()).hexdigest() == ROSTER_SHA256
    assert len(audit.read_rows(ROSTER)) == ROSTER_ROWS


def test_roster_counters_reproduce_from_the_raw_inputs(audit_result: dict[str, object]) -> None:
    roster = audit_result["s2_roster_5117"]
    assert roster["counters_agree"] is True
    assert roster["tiers_agree"] is True
    assert roster["digest_matches_file"] is True
    assert roster["recomputed"]["rows_by_tier"] == {
        "no_reference_orbital": 421,
        "flagship_dielectric": 54,
        "named_core_channel": 68,
        "calibration_bulk": 4574,
    }


def test_layer_is_complete(audit_result: dict[str, object]) -> None:
    complete = audit_result["s2b_layer_completeness"]
    assert complete["complete"] is True
    assert complete["run_status"] == "complete"
    assert complete["delivered_rows"] == ROSTER_ROWS


def test_calibration_status_is_decided_out_of_sample(audit_result: dict[str, object]) -> None:
    cal = audit_result["s1_calibration_leakage"]
    for channel in ("homo", "lumo", "gap"):
        entry = cal[channel]
        assert entry["slope_matches_summary"] is True
        assert entry["recorded_status_equals_out_of_sample_gate"] is True
        assert entry["summary_status_basis"] == "out_of_sample_mae_and_out_of_sample_r"
        assert entry["r_out_of_sample"] is not None
        assert abs(entry["r_out_of_sample"] - entry["summary_r_out_of_sample"]) <= 1e-9


def test_calibration_numbers_reproduce_the_summary(audit_result: dict[str, object]) -> None:
    cal = audit_result["s1_calibration_leakage"]
    for channel in ("homo", "lumo", "gap"):
        entry = cal[channel]
        assert abs(entry["r_in_sample"] - entry["summary_r_in_sample"]) <= 1e-9
        assert abs(entry["mae_out_of_sample_eV"] - entry["summary_mae_out_of_sample_eV"]) <= 1e-9


def test_builder_gate_is_governed_by_out_of_sample_r() -> None:
    pairs = [
        {"inchikey": "k0", "x": 0.0, "y": 0.0},
        {"inchikey": "k1", "x": 0.0, "y": 10.0},
        {"inchikey": "k2", "x": 1.0, "y": 1.0},
        {"inchikey": "k3", "x": 1.0, "y": 11.0},
        {"inchikey": "k4", "x": 2.0, "y": 2.0},
    ]
    good_fits = [
        {"held_out_fold": 0, "slope": 1.0, "intercept": 0.0},
        {"held_out_fold": 1, "slope": 1.0, "intercept": 10.0},
    ]
    bad_fits = [
        {"held_out_fold": 0, "slope": 1.0, "intercept": 10.0},
        {"held_out_fold": 1, "slope": 1.0, "intercept": 0.0},
    ]
    low_r_in = {
        "slope": 1.0,
        "intercept": 0.0,
        "mae_out_of_sample_eV": 0.1,
        "pearson_r_in_sample": 0.0,
        "fold_fits": good_fits,
    }
    high_r_in = {
        "slope": 1.0,
        "intercept": 0.0,
        "mae_out_of_sample_eV": 0.1,
        "pearson_r_in_sample": 0.99,
        "fold_fits": bad_fits,
    }
    assert out_of_sample_r(pairs, low_r_in) >= R_LIMIT
    assert out_of_sample_r(pairs, high_r_in) < R_LIMIT
    assert apply_out_of_sample_gate(low_r_in, pairs)["status"] == "usable_with_flag"
    assert apply_out_of_sample_gate(high_r_in, pairs)["status"] == "reference_only"


def test_merge_counters_are_reachable_and_match_the_summary(
    audit_result: dict[str, object],
) -> None:
    merge = audit_result["s3_merge_dedup"]
    assert merge["off_roster_branch_reachable"] is True
    assert merge["ok_ok_collision_counted"] is True
    assert merge["bad_ok_upgrade_counted"] is True
    assert merge["duplicate_collisions_replicated"] == 302
    assert merge["duplicate_upgrades_replicated"] == 117
    assert merge["counters_match"] is True


def test_verifier_is_independent_and_gates_out_of_sample(
    audit_result: dict[str, object],
) -> None:
    verifier = audit_result["s4_verifier_independence"]
    assert verifier["verifier_imports_project_module"] is False
    assert verifier["verifier_mentions_builder_module"] is False
    assert verifier["verifier_gates_on_out_of_sample_r"] is True
    assert verifier["verifier_gates_on_in_sample_r"] is False
    assert verifier["builder_imports_shared_module"] is True


def test_structure_check_is_recomputed_per_row(audit_result: dict[str, object]) -> None:
    structure = audit_result["s5_structure_check"]
    assert structure["recomputed_inchikey_mismatch"] == 0
    assert structure["recomputed_smiles_unparsable"] == 0
    assert structure["stored_column_disagrees_with_recompute"] == 0
    assert structure["compares_only_first_inchikey_block"] is True


def test_unit_evidence_is_now_from_this_layer_but_sampled(
    audit_result: dict[str, object],
) -> None:
    unit = audit_result["s6_unit_scale"]
    assert unit["this_layer_n_sampled"] == 24
    assert unit["this_layer_all_passed"] is True
    assert unit["this_layer_layer_sha256_matches_current"] is True
    assert unit["this_layer_geometry_digest_matches"] == 24
    assert unit["coverage_note_present"] is True
    assert unit["judgement_C_letter_satisfied"] is False
    assert unit["this_layer_sample_share"] < 0.01


def test_models_fitted_note_is_present(audit_result: dict[str, object]) -> None:
    models = audit_result["s7_models_fitted"]
    assert models["models_fitted_field"] == 0
    assert models["models_fitted_note_present"] is True


def test_report_exists_with_section7(audit_result: dict[str, object]) -> None:
    report = audit_result["s8_report"]
    assert report["exists"] is True
    assert report["section7"] is True


def test_round1_history_is_preserved(audit_result: dict[str, object]) -> None:
    history = audit_result["history"]["round1"]
    assert history["layer_sha256"].startswith("44f900b1")
    assert history["verdicts"] == ROUND1_VERDICTS


def test_recorded_audit_json_holds_the_same_round2_verdicts() -> None:
    recorded = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    verdicts = {item["id"]: item["verdict"] for item in recorded["findings"]}
    assert verdicts == EXPECTED_VERDICTS
    assert recorded["history"]["round1"]["verdicts"] == ROUND1_VERDICTS
