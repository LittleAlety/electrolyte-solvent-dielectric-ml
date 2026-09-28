"""Literal pins for the Week 20 W20-5 high-epsilon refusal regime.

The refusal predicates, the second-scoreboard endpoints and the refused-region
counts are typed out here instead of being re-read from prose, so a silent edit
to the module or to the frozen registry turns this file red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w19_ranking_key as ranking
from probes import w20_refusal as refusal

REGISTRY = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
PREREG = REPOSITORY_ROOT / "probes" / "w20_refusal_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_refusal_summary.json"

REGISTRY_SHA256 = "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee"

# Measured from the frozen registry on 2026-09-28 by this module.
EXPECTED_SCALE = {
    "registry_rows": 31949,
    "unparsable_smiles": 2,
    "rows_with_dielectric": 247,
    "d1_in_domain_rows": 802,
    "d1_out_of_domain_rows": 31145,
    "eps_rows_d1_in_domain": 64,
    "eps_rows_d1_out_of_domain": 183,
    "eps_rows_refused_by_high_eps": 9,
    "eps_rows_refused_by_domain": 183,
    "eps_rows_refused_by_both": 5,
    "eps_rows_refused_total": 187,
    "eps_rows_ranked": 60,
}

SECOND_SCOREBOARD_PINS = {
    "global_endpoint_r2": 0.45401075998423623,
    "d1_in_domain_r2": 0.524012313223719,
    "d1_out_of_domain_r2": 0.3198024498133034,
    "d1_in_domain_compounds": 57.0,
    "d1_out_of_domain_compounds": 40.0,
    "scored_compounds": 97.0,
    "scored_rows": 457.0,
}


def test_threshold_has_a_single_owner() -> None:
    assert refusal.HIGH_PERMITTIVITY_EPS == 60.0
    assert refusal.HIGH_PERMITTIVITY_EPS is ranking.HIGH_PERMITTIVITY_EPS
    assert refusal.D1_MIN_HBD == 1
    assert refusal.D1_MIN_TPSA == 20.0


def test_second_scoreboard_pins_are_literal() -> None:
    for key, value in SECOND_SCOREBOARD_PINS.items():
        assert refusal.SECOND_SCOREBOARD[key] == value, key
    assert refusal.SECOND_SCOREBOARD["d1_definition"] == (
        "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0"
    )


def test_high_permittivity_boundary_is_strict() -> None:
    inside = refusal.refusal_decision(epsilon=60.0, donor_count=1, tpsa=30.0)
    outside = refusal.refusal_decision(epsilon=60.0000001, donor_count=1, tpsa=30.0)
    assert inside["refused"] is False
    assert inside["high_permittivity_excluded"] is False
    assert outside["refused"] is True
    assert outside["refusal_reasons"] == ["high_permittivity_region"]
    assert outside["score_produced"] is False
    assert outside["exit"] == "refused_experimental_queue"


def test_domain_rule_fires_and_is_executable() -> None:
    accepted = refusal.refusal_decision(epsilon=20.0, donor_count=1, tpsa=20.0)
    assert accepted["refused"] is False
    assert accepted["domain_label"] == "in_domain"
    assert accepted["exit"] == "ranked"
    assert accepted["score_produced"] is True

    refused = refusal.refusal_decision(epsilon=20.0, donor_count=0, tpsa=76.0)
    assert refused["refused"] is True
    assert refused["refusal_reasons"] == ["outside_applicability_domain"]
    assert refused["domain_label"] == "out_of_domain"
    assert refused["score_produced"] is False

    both = refusal.refusal_decision(epsilon=88.0, donor_count=0, tpsa=76.0)
    assert both["refusal_reasons"] == [
        "high_permittivity_region",
        "outside_applicability_domain",
    ]

    missing = refusal.refusal_decision(epsilon=None, donor_count=1, tpsa=30.0)
    assert missing["refused"] is False
    assert missing["high_permittivity_excluded"] is False


def test_rule_table_is_ordered_and_closed() -> None:
    assert refusal.REFUSAL_REASONS == (
        "high_permittivity_region",
        "outside_applicability_domain",
    )
    for rule in refusal.REFUSAL_RULES:
        assert rule.exit_code == "refused_experimental_queue"
        assert rule.rule_id.startswith("w20_refusal_")
        assert rule.evidence


@pytest.mark.skipif(not REGISTRY.is_file(), reason="frozen registry is absent")
def test_registry_scale_reproduces_literal_counts() -> None:
    import hashlib

    digest = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert digest == REGISTRY_SHA256
    scale = refusal.registry_refusal_scale()
    for key, value in EXPECTED_SCALE.items():
        assert scale[key] == value, key
    assert scale["eps_rows_refused_total"] + scale["eps_rows_ranked"] == (
        scale["rows_with_dielectric"]
    )
    assert scale["eps_rows_refused_by_high_eps"] + scale["eps_rows_refused_by_domain"] - (
        scale["eps_rows_refused_by_both"]
    ) == scale["eps_rows_refused_total"]
    assert scale["d1_in_domain_rows"] + scale["d1_out_of_domain_rows"] + (
        scale["unparsable_smiles"]
    ) == scale["registry_rows"]


def test_summary_and_prereg_are_registered_without_readings() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["produces_reading"] is False
    assert prereg["promoted"] is False
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["models_fitted"] == 0
    assert len(prereg["rules"]) == 2

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["produces_reading"] is False
    assert summary["promoted"] is False
    assert summary["main_scoreboard_untouched"] is True
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["shot_number_taken"] is None
    for key, value in EXPECTED_SCALE.items():
        assert summary["registry_scale"][key] == value, key
