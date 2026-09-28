"""Literal pins for the Week 20 W20-8 funnel KPI board and capped-ladder revision.

The forbidden R2 KPI, the literature-framework disclaimer, the measured ranking
KPIs and the capping revision are pinned here so a silent edit to the board or
to a frozen input turns this file red.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_funnel_kpi as funnel

PREREG = REPOSITORY_ROOT / "probes" / "w20_funnel_kpi_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_funnel_kpi_summary.json"
FIGURE = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_funnel_kpi_ranking.png"

POOLED_PINS = {
    "auc_gt15": 0.8947205768486257,
    "auc_gt30": 0.9392420870425322,
    "spearman": 0.7737616891926036,
    "n_rows": 4570,
}

TOP_K_PINS = {
    "base_rate": 0.26258205689277897,
    "top10_precision": 0.9,
    "top20_precision": 0.95,
    "top50_precision": 0.66,
    "top20_enrichment": 3.617916666666667,
    "top20_hits_gt30": 19,
}


def test_plan_registers_without_readings() -> None:
    plan = funnel.plan()
    assert plan["produces_reading"] is False
    assert plan["promoted"] is False
    assert plan["main_scoreboard_untouched"] is True
    assert plan["scoreboard_attempts_delta"] == 0
    assert plan["shot_number_taken"] is None
    assert plan["status"] == "registered_no_model"
    assert plan["arm"]["baseline_r2"] == 0.4091179943351143


def test_r2_is_a_forbidden_funnel_kpi() -> None:
    assert funnel.FORBIDDEN_KPIS == ("r2",)
    assert "magnitude" in funnel.FORBIDDEN_KPI_REASON
    for group in funnel.KPI_GROUPS:
        assert "r2" not in group["items"], group["group"]


def test_kpi_groups_are_the_three_registered_groups() -> None:
    names = [group["group"] for group in funnel.KPI_GROUPS]
    assert names == ["ranking", "coverage_cost", "discipline"]
    ranking = funnel.KPI_GROUPS[0]["items"]
    assert ranking == ("auc_gt15", "auc_gt30", "spearman", "top_k_enrichment")


def test_literature_kpi_framework_is_a_different_thing() -> None:
    framework = funnel.LITERATURE_KPI_FRAMEWORK
    assert framework["acronym"] == "KPI"
    assert framework["expansion"] == (
        "Knowledge-based electrolyte Property prediction Integration"
    )
    assert framework["kind"] == "literature framework name"
    assert framework["doi"] == "10.1002/anie.202416506"


def test_pooled_ranking_kpis_are_literal() -> None:
    pooled = funnel.run()["ranking"]["pooled"]
    for key, value in POOLED_PINS.items():
        assert pooled[key] == value, key


def test_top_k_enrichment_is_literal() -> None:
    top_k = funnel.run()["ranking"]["top_k"]
    assert top_k["repeat"] == "0"
    assert top_k["n_rows"] == 457
    for key, value in TOP_K_PINS.items():
        assert top_k[key] == value, key


def test_coverage_and_discipline_kpis_are_literal() -> None:
    coverage = funnel.coverage_kpis()
    assert coverage["scorable_compounds"] == 97.0
    assert coverage["in_domain_compounds"] == 57.0
    assert coverage["in_domain_coverage"] == 0.5876288659793815
    assert coverage["cost_status"] == "defined_not_measured"
    assert coverage["compute_cost_per_candidate"] is None
    assert coverage["experiment_cost_per_candidate"] is None

    discipline = funnel.discipline_kpis()
    assert discipline["promoted_false_count"] == 8
    assert discipline["w20_lanes"] == 8
    assert discipline["main_scoreboard_attempts"] == 0
    assert discipline["cumulative_main_scoreboard_attempts"] == 11
    assert discipline["redline_violations"] == 0


def test_capping_revision_flips_the_rung_to_capped() -> None:
    revision = funnel.capping_revision()
    assert revision["status_after"] == "capped"
    assert revision["cap_chain"] == [161, 157, 153]
    assert revision["net_new_upper_bound"] == 4
    assert revision["row"]["rung"] == "0.58\u20130.65"
    assert revision["row"]["status_before"] == "next_rung"
    assert revision["row"]["premise"] == "\u5316\u5408\u7269\u8986\u76d6\u518d\u7ffb\u500d"
    assert "28.36" in revision["refuted_by"]
    assert "28.37" in revision["refuted_by"]


def test_summary_and_prereg_register_the_same_board() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["produces_reading"] is False
    assert prereg["promoted"] is False
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["models_fitted"] == 0
    assert prereg["forbidden_kpis"] == ["r2"]
    assert prereg["capping_revision"]["status_after"] == "capped"
    assert prereg["capping_revision"]["cap_chain"] == [161, 157, 153]

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["produces_reading"] is False
    assert summary["promoted"] is False
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["shot_number_taken"] is None
    assert summary["forbidden_kpis"] == ["r2"]
    assert summary["capping_revision"]["status_after"] == "capped"
    assert summary["literature_kpi_framework"]["expansion"] == (
        "Knowledge-based electrolyte Property prediction Integration"
    )


def test_ranking_figure_is_present() -> None:
    assert FIGURE.is_file()
    with FIGURE.open("rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"


def test_write_figure_reproduces_a_png(tmp_path: Path) -> None:
    target = tmp_path / "ranking.png"
    returned = funnel.write_figure(path=target)
    assert returned == target
    assert target.is_file()
    with target.open("rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"


def test_pooled_rows_are_read_from_the_frozen_table() -> None:
    with funnel.PREDICTIONS_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["protocol"] == funnel.ARM_PROTOCOL
            and row["representation"] == funnel.ARM_REPRESENTATION
        ]
    assert len(rows) == 4570

