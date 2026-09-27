"""Guards for the Week 17 shot-17 model-head sweep.

Shot 16 left the single-representation reading at 0.6080587938801277 explained but
not beaten: it is a seed-42 high draw whose cross-seed mean is 0.586114, and the
frozen headline stays the hybrid 0.4766400383507876.  The probe
probes/dielectric_head_sweep.py asks the next, separate question -- with the pool,
the splitter, the scorer and the representation all frozen, does swapping the model
head clear 0.70? -- and this module keeps its promises honest: the frozen head
reproduces bit for bit, the fold signature is checked against the frozen one, the
leakage audit stays clean, and no reading is ever promoted, least of all on a
single seed.

Everything here is offline: no network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.dielectric_observations_grouped_benchmark import METRIC_NAMES

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_head_sweep_prereg.json"
SUMMARY = ROOT / "probes/dielectric_head_sweep_summary.json"
REPORT = ROOT / "reports/dielectric_head_sweep.md"
SCRIPT = ROOT / "probes/dielectric_head_sweep.py"
ARTIFACT = ROOT / "probes/artifacts/dielectric_head_sweep_repeats.csv"

EXPECTED_COLUMNS = ("seed", "arm", "representation", "repeat", *METRIC_NAMES)
SEED_42_REFERENCE = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
ANCHOR_TOLERANCE = 1e-09
HEADS = (
    "xgb_reference",
    "xgb_deep",
    "extra_trees",
    "kernel_ridge",
    "mlp",
    "blend_uniform",
    "selected_inner_cv",
)
VERDICTS = ("confirmed", "partial", "refuted", "placebo")


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def test_prereg_is_locked_and_pins_the_ladder_before_the_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["non_blind"] is True
    assert "0.6080587938801277" in prereg["non_blind_reason"]
    rule = prereg["decision_rule"]
    assert rule["pass_threshold_r2"] == 0.70
    assert rule["partial_target_r2"] == 0.60
    assert rule["improvement_bar_r2"] == 0.02
    assert rule["kill_bar_r2"] == 0.005
    assert rule["min_confirming_seeds"] == 3
    for key in ("confirmed", "partial", "refuted"):
        assert key in rule
    assert "is promoted" in prereg["promotion_rule"]
    assert prereg["reference_arm"] == "xgb_reference"
    assert prereg["anchors"]["xgb_reference_physical_lever4"] == SEED_42_REFERENCE
    assert prereg["anchors"]["tolerance"] == ANCHOR_TOLERANCE
    assert set(HEADS) == set(prereg["arms"])


def test_the_frozen_head_reproduces_bit_for_bit_or_the_probe_is_silent() -> None:
    summary = _summary()
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["tolerance"] == ANCHOR_TOLERANCE
    rows = anchors["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["head"] == "xgb_reference"
    assert row["seed"] == 42
    assert row["ok"] is True
    assert row["expected"] == SEED_42_REFERENCE
    assert abs(row["measured"] - SEED_42_REFERENCE) <= ANCHOR_TOLERANCE
    assert summary["contract"]["anchor_seed"] == 42
    text = SCRIPT.read_text(encoding="utf-8")
    assert "the seed-42 anchor did not reproduce; refusing to report anything else" in text
    assert "the fold assignment moved; refusing to continue" in text


def test_the_sweep_never_promotes_and_the_frozen_numbers_do_not_move() -> None:
    summary = _summary()
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert promotion["frozen_headline"] == FROZEN_HEADLINE
    assert promotion["frozen_baseline"] == FROZEN_BASELINE
    assert "non-blind" in promotion["reason"]


def test_the_verdict_is_recomputed_from_the_pre_registered_ladder() -> None:
    summary = _summary()
    answers = summary["answers"]
    assert answers["reference_head"] == "xgb_reference"
    assert answers["reference_r2"] == pytest.approx(SEED_42_REFERENCE, abs=ANCHOR_TOLERANCE)
    seed_rows = {
        (int(row["seed"]), str(row["head"])): float(row["r2_mean"])
        for row in summary["seed_rows"]
    }
    seeds = [int(seed) for seed in answers["seeds_run"]]
    anchor = int(answers["reference_seed"])
    comparison = [head for head in HEADS if head != "xgb_reference"]
    improvements = {
        head: seed_rows[(anchor, head)] - answers["reference_r2"] for head in comparison
    }
    best_head = max(comparison, key=lambda head: (improvements[head], head))
    assert best_head == answers["best_head"]
    assert answers["best_r2"] == pytest.approx(seed_rows[(anchor, best_head)], abs=1e-12)
    assert answers["best_improvement"] == pytest.approx(improvements[best_head], abs=1e-12)
    cross = [seed_rows[(seed, best_head)] for seed in seeds]
    assert answers["cross_seed_mean_of_best_head"] == pytest.approx(
        sum(cross) / len(cross), abs=1e-12
    )
    assert answers["target_met_at_anchor_seed"] == (answers["best_r2"] >= 0.70)
    assert answers["target_met_cross_seed"] == (
        answers["cross_seed_mean_of_best_head"] >= 0.70
    )
    if summary["placebo"]:
        assert summary["verdict"] == "placebo"
    elif (
        answers["best_r2"] >= 0.70
        and answers["best_improvement"] >= 0.02
        and answers["cross_seed_mean_of_best_head"] >= 0.70
        and len(seeds) >= 3
    ):
        assert summary["verdict"] == "confirmed"
    elif answers["best_improvement"] >= 0.005:
        assert summary["verdict"] == "partial"
    else:
        assert summary["verdict"] == "refuted"
    assert summary["verdict"] in VERDICTS


def test_a_single_seed_run_can_never_reach_confirmed() -> None:
    summary = _summary()
    answers = summary["answers"]
    if not summary["placebo"] and len(answers["seeds_run"]) < 3:
        assert answers["single_seed_run"] is True
        assert summary["verdict"] != "confirmed"


def test_the_report_answers_the_target_question_out_loud() -> None:
    text = _report_text()
    for needle in (
        "目标 R² ≥ **0.70**",
        "旧目标 R² ≥ **0.60**",
        "0.6080587938801277",
        "0.4766400383507876",
        "0.4091179943351143",
        "本探针**非盲**",
        "任何读数一律不提升",
        "多重比较红利",
        "诊断性",
    ):
        assert needle in text, needle


def test_the_summary_carries_a_clean_leakage_audit() -> None:
    summary = _summary()
    leakage = summary["leakage"]
    assert leakage["clean"] is True
    for block in leakage["by_seed"].values():
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0
    # one fold row per (fold, head): 50 folds x 7 heads x seeds
    assert sum(leakage["folds_by_seed"].values()) == 50 * len(HEADS) * len(
        summary["answers"]["seeds_run"]
    )


def test_the_frozen_side_did_not_move() -> None:
    summary = _summary()
    contract = summary["contract"]
    assert contract["representation"] == "Physical(lever4)"
    assert contract["n_splits"] == 5
    assert contract["n_repeats"] == 10
    assert contract["inner_folds"] == 3
    assert contract["frozen_head_params"]["max_depth"] == 2
    assert contract["frozen_head_params"]["n_estimators"] == 200
    assert summary["pool"]["base_rows"] == 2029
    assert summary["pool"]["scored_rows"] == 457
    for row in summary["seed_rows"]:
        assert row["repeats"] == 10


def test_the_artifact_keeps_the_frozen_repeat_schema() -> None:
    with ARTIFACT.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == list(EXPECTED_COLUMNS)
    seeds = [int(seed) for seed in _summary()["answers"]["seeds_run"]]
    assert len(rows) == len(seeds) * len(HEADS) * 10
    assert bytes([13, 10]) not in ARTIFACT.read_bytes()
    for seed in seeds:
        present = {row["arm"] for row in rows if int(row["seed"]) == seed}
        assert present == set(HEADS)


def test_the_script_states_the_frozen_head_and_the_ladder() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277",
        "FROZEN_HEADLINE = 0.4766400383507876",
        "FROZEN_BASELINE = 0.4091179943351143",
        "PASS_TARGET_R2 = 0.70",
        "IMPROVEMENT_BAR_R2 = 0.02",
        "MIN_CONFIRMING_SEEDS = 3",
        '"promoted": False',
    ):
        assert needle in text, needle
