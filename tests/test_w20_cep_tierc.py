"""Literal pins for the Week 20 W20-6c CEP 88k DFPT Tier C screen.

The verdict, the tier ceiling, the identifiability statement and the physics
reason are pinned here so a silent edit to the screen turns this file red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_cep_tierc as cep

PREREG = REPOSITORY_ROOT / "probes" / "w20_cep_tierc_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_cep_tierc_summary.json"


def test_prereg_is_locked_before_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["expected_verdict"] == "not_verifiable"
    assert prereg["expected_tier"] == "C"
    assert prereg["licence_verdict"] == "not_verifiable"
    assert prereg["produces_reading"] is False
    assert prereg["promoted"] is False
    assert prereg["shot_number_taken"] is None
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["reaxys_values_used"] == 0
    assert prereg["main_scoreboard_untouched"] is True
    assert all(value is None for value in prereg["screen_inputs"].values())


def test_screen_verdict_is_not_verifiable_and_tier_c() -> None:
    summary = cep.screen()
    assert summary["verdict"] == "not_verifiable"
    assert summary["tier"] == "C"
    assert summary["tier_ceiling"] == "features_and_predictions_only"
    assert summary["ceiling_break"] is False
    assert summary["licence_verdict"] == "not_verifiable"
    assert summary["licence_verdict"] in cep.LICENCE_VERDICTS


def test_handle_is_not_identifiable_and_no_row_is_classified() -> None:
    summary = cep.screen()
    ident = summary["identifiability"]
    assert ident["handle"] == "CEP 88k DFPT"
    assert ident["status"] == "not_identifiable"
    assert ident["handle_identifiable"] is False
    assert ident["open_licence_readable"] is False
    assert all(value is None for value in ident["screen_inputs"].values())
    row_level = summary["row_level_classification"]
    assert row_level["status"] == "source_not_verifiable"
    assert row_level["admissible"] == 0
    assert row_level["needs_lead"] == 0
    assert row_level["inadmissible"] == 0
    assert summary["row_count"] == 0
    assert summary["rows_artifact"] is None


def test_physics_reason_is_the_orientational_correlation() -> None:
    reason = cep.screen()["physics_reason"]
    assert "different quantities" in reason["statement"]
    assert "orientational correlation" in reason["missing_term"]
    assert "g factor" in reason["missing_term"]
    assert "g = 1" in reason["why_g_is_one_in_gas"]
    assert "Tier C" in reason["consequence"]
    assert "mu^2 g" in reason["kirkwood_relation"]


def test_summary_file_matches_the_screen_and_promotes_nothing() -> None:
    on_disk = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert on_disk == cep.screen()
    assert on_disk["produces_reading"] is False
    assert on_disk["promoted"] is False
    assert on_disk["shot_number_taken"] is None
    assert on_disk["scoreboard_attempts_delta"] == 0
    assert on_disk["reaxys_values_used"] == 0
    assert on_disk["models_fitted"] == 0
    assert on_disk["main_scoreboard_untouched"] is True


def test_plan_carries_the_decidable_rule_and_no_reading() -> None:
    plan = cep.plan()
    assert plan["tier"] == "C"
    assert "per-row table/figure locator" in plan["decidable_rule"]
    assert "not_verifiable" in plan["decidable_rule"]
    assert "Tier C" in plan["tier_rule"]
    assert plan["produces_reading"] is False
    assert plan["promoted"] is False
    assert plan["reaxys_values_used"] == 0

