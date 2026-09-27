"""Guards for the Week 18 P0 dense-XGBoost hyperparameter grid.

Shot 17 (probes/dielectric_head_sweep.py) refuted swapping the model family: the best
alternative head reached 0.567035 against the frozen head at 0.608059.  P0 asks the
remaining question -- same family, frozen protocol, dense Physical(lever4) block -- and
this module keeps its promises honest: the locked pre-registration is pinned by digest,
the grid is capped at 24 arms and contains the frozen reference, the anchor has to
reproduce 0.6080587938801277 bit for bit, the endpoint is the cross-seed mean over the
five locked seeds, the leakage audit stays clean, and no reading is ever promoted.

Everything here is offline: no network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes.dielectric_observations_grouped_benchmark import METRIC_NAMES

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_hyperparameter_grid_prereg.json"
SUMMARY = ROOT / "probes/dielectric_hyperparameter_grid_summary.json"
REPORT = ROOT / "reports/dielectric_hyperparameter_grid.md"
SCRIPT = ROOT / "probes/dielectric_hyperparameter_grid.py"
ARTIFACT = ROOT / "probes/artifacts/dielectric_hyperparameter_grid_repeats.csv"

PREREG_SHA256 = "79834b717141dbbace6ae91bd259fa37289f81f7d310feaa8b2470d7743179bc"
SEED_42_REFERENCE = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
ANCHOR_TOLERANCE = 1e-09
LOCKED_SEEDS = (42, 1234, 2026, 31337, 7)
ARM_CAP = 24
TARGET_R2 = 0.60
IMPROVEMENT_BAR = 0.02
KILL_BAR = 0.005
REFERENCE = "xgb_reference"

ARMS = (
    "xgb_reference",
    "hp_d3_n200_lr0.05_mcw1_ss0.8_cs0.8",
    "hp_d4_n200_lr0.05_mcw1_ss0.8_cs0.8",
    "hp_d6_n200_lr0.05_mcw1_ss0.8_cs0.8",
    "hp_d2_n400_lr0.05_mcw1_ss0.8_cs0.8",
    "hp_d2_n800_lr0.05_mcw1_ss0.8_cs0.8",
    "hp_d4_n400_lr0.05_mcw1_ss0.8_cs0.8",
)
VERDICTS = ("confirmed", "partial", "refuted", "placebo")


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def test_prereg_is_locked_and_pins_the_grid_by_digest() -> None:
    raw = PREREG.read_bytes()
    assert raw.count(b"\r\n") == 0
    assert raw[:3] != b"\xef\xbb\xbf"
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    prereg = json.loads(raw.decode("utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["non_blind"] is True
    assert "0.6080587938801277" in prereg["non_blind_reason"]
    grid = prereg["grid"]
    assert grid["arm_count"] == len(ARMS)
    assert grid["max_arms_cap"] == ARM_CAP
    assert grid["full_cartesian_size"] == 288
    assert "not run" in grid["selection_rule"]
    assert set(prereg["arms"]) == set(ARMS)
    assert len(prereg["arms"]) == len(ARMS)
    assert prereg["reference_arm"] == REFERENCE
    assert tuple(int(seed) for seed in prereg["seeds"]) == LOCKED_SEEDS
    assert prereg["anchor_tolerance"] == ANCHOR_TOLERANCE
    assert prereg["anchors"]["xgb_reference_physical_lever4"] == SEED_42_REFERENCE
    rule = prereg["decision_rule"]
    assert rule["endpoint"] == "cross_seed_mean"
    assert rule["pass_threshold_r2"] == TARGET_R2
    assert rule["improvement_bar_r2"] == IMPROVEMENT_BAR
    assert rule["kill_bar_r2"] == KILL_BAR
    for key in ("confirmed", "partial", "refuted", "placebo"):
        assert key in rule
    assert "is promoted" in prereg["promotion_rule"]
    assert "rebuilt from the arm names" in prereg["pre_run_correction"]
    assert "No result existed" in prereg["pre_run_correction"]


def test_the_grid_is_capped_and_contains_the_frozen_head() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert len(ARMS) <= ARM_CAP
    assert len(set(ARMS)) == len(ARMS)
    assert REFERENCE in ARMS
    params = prereg["arm_params"]
    assert set(params) == set(ARMS)
    reference = params[REFERENCE]
    assert reference["n_estimators"] == 200
    assert reference["max_depth"] == 2
    assert reference["learning_rate"] == 0.05
    assert reference["subsample"] == 0.8
    assert reference["colsample_bytree"] == 0.8
    assert reference["reg_lambda"] == 1.0
    assert reference["objective"] == "reg:squarederror"
    assert reference["tree_method"] == "hist"
    assert reference["max_bin"] == 64
    assert reference["n_jobs"] == 1
    factors = prereg["grid"]["factors"]
    assert factors["max_depth"] == [2, 3, 4, 6]
    assert factors["n_estimators"] == [200, 400, 800]
    assert factors["learning_rate"] == [0.03, 0.05, 0.1]
    assert factors["min_child_weight"] == [1, 5]
    depths = {params[arm]["max_depth"] for arm in ARMS}
    assert depths == {2, 3, 4, 6}
    for arm in ARMS:
        assert params[arm]["reg_lambda"] == 1.0
        assert params[arm]["tree_method"] == "hist"


def test_the_frozen_head_reproduces_bit_for_bit_or_the_probe_is_silent() -> None:
    summary = _summary()
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["tolerance"] == ANCHOR_TOLERANCE
    rows = anchors["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["arm"] == REFERENCE
    assert row["seed"] == 42
    assert row["ok"] is True
    assert row["expected"] == SEED_42_REFERENCE
    assert abs(row["measured"] - SEED_42_REFERENCE) <= ANCHOR_TOLERANCE
    assert summary["contract"]["anchor_seed"] == 42
    text = SCRIPT.read_text(encoding="utf-8")
    assert "the seed-42 anchor did not reproduce; refusing to report anything else" in text
    assert "the fold assignment moved; refusing to continue" in text
    assert "the locked arm list does not match the script; refusing to continue" in text


def test_the_grid_never_promotes_and_the_frozen_numbers_do_not_move() -> None:
    summary = _summary()
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert promotion["frozen_headline"] == FROZEN_HEADLINE
    assert promotion["frozen_baseline"] == FROZEN_BASELINE
    assert "non-blind" in promotion["reason"]
    assert "multiple comparison" in promotion["reason"]


def test_the_endpoint_is_the_cross_seed_mean_over_the_locked_seeds() -> None:
    summary = _summary()
    answers = summary["answers"]
    assert answers["endpoint"] == "cross_seed_mean"
    assert tuple(int(seed) for seed in answers["seeds_run"]) == LOCKED_SEEDS
    assert summary["contract"]["seeds"] == list(LOCKED_SEEDS)
    cross = {str(row["arm"]): row for row in summary["cross_seed"]}
    assert set(cross) == set(summary["contract"]["arms"])
    for row in cross.values():
        seed_means = [float(value) for value in row["seed_means"]]
        assert len(seed_means) == len(LOCKED_SEEDS)
        assert float(row["r2_seed_mean"]) == pytest.approx(
            sum(seed_means) / len(seed_means), abs=1e-12
        )
        assert float(row["r2_seed_min"]) == pytest.approx(min(seed_means), abs=1e-12)
        assert float(row["r2_seed_max"]) == pytest.approx(max(seed_means), abs=1e-12)


def test_the_verdict_is_recomputed_from_the_cross_seed_ladder() -> None:
    summary = _summary()
    answers = summary["answers"]
    arms = [str(arm) for arm in summary["contract"]["arms"]]
    cross = {str(row["arm"]): float(row["r2_seed_mean"]) for row in summary["cross_seed"]}
    assert answers["reference_arm"] == REFERENCE
    assert float(answers["reference_cross_seed_mean"]) == pytest.approx(
        cross[REFERENCE], abs=1e-12
    )
    comparison = [arm for arm in arms if arm != REFERENCE]
    if comparison:
        best = max(comparison, key=lambda arm: (cross[arm], arm))
        improvement = cross[best] - cross[REFERENCE]
    else:
        best = REFERENCE
        improvement = 0.0
    assert str(answers["best_arm"]) == best
    assert float(answers["best_cross_seed_mean"]) == pytest.approx(cross[best], abs=1e-12)
    assert float(answers["best_improvement_vs_reference"]) == pytest.approx(
        improvement, abs=1e-12
    )
    assert bool(answers["target_met_cross_seed"]) == (cross[best] > TARGET_R2)
    assert bool(answers["improvement_met"]) == (improvement >= IMPROVEMENT_BAR)
    verdict = str(summary["verdict"])
    assert verdict in VERDICTS
    if summary["placebo"]:
        assert verdict == "placebo"
    elif cross[best] > TARGET_R2 and improvement >= IMPROVEMENT_BAR:
        assert verdict == "confirmed"
    elif improvement >= KILL_BAR:
        assert verdict == "partial"
    else:
        assert verdict == "refuted"


def test_the_summary_carries_a_clean_leakage_audit() -> None:
    summary = _summary()
    leakage = summary["leakage"]
    assert leakage["clean"] is True
    for block in leakage["by_seed"].values():
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0
    arms = len(summary["contract"]["arms"])
    assert sum(leakage["folds_by_seed"].values()) == 50 * arms * len(summary["answers"]["seeds_run"])


def test_the_frozen_side_did_not_move() -> None:
    summary = _summary()
    contract = summary["contract"]
    assert contract["representation"] == "Physical(lever4)"
    assert contract["n_splits"] == 5
    assert contract["n_repeats"] == 10
    assert contract["arm_count"] <= contract["arm_cap"] == ARM_CAP
    assert contract["model_random_state"] == 42
    frozen = contract["frozen_hyperparameters"]
    assert frozen["max_depth"] == 2
    assert frozen["n_estimators"] == 200
    assert frozen["learning_rate"] == 0.05
    assert frozen["reg_lambda"] == 1.0
    assert summary["pool"]["base_rows"] == 2029
    assert summary["pool"]["scored_rows"] == 457
    for row in summary["seed_rows"]:
        assert row["repeats"] == 10


def test_the_artifact_keeps_the_frozen_repeat_schema() -> None:
    with ARTIFACT.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == ["seed", "arm", "representation", "repeat", *METRIC_NAMES]
    summary = _summary()
    arms = [str(arm) for arm in summary["contract"]["arms"]]
    seeds = [int(seed) for seed in summary["answers"]["seeds_run"]]
    assert len(rows) == len(seeds) * len(arms) * 10
    assert bytes([13, 10]) not in ARTIFACT.read_bytes()
    for seed in seeds:
        present = {row["arm"] for row in rows if int(row["seed"]) == seed}
        assert present == set(arms)
    assert all(row["representation"] == "Physical(lever4)" for row in rows)


def test_the_script_states_the_frozen_head_and_the_ladder() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277",
        "FROZEN_HEADLINE = 0.4766400383507876",
        "FROZEN_BASELINE = 0.4091179943351143",
        "SEEDS = (42, 1234, 2026, 31337, 7)",
        "MAX_GRID_ARMS = 24",
        "PASS_TARGET_R2 = 0.60",
        "IMPROVEMENT_BAR_R2 = 0.02",
        "KILL_BAR_R2 = 0.005",
        '"promoted": False',
    ):
        assert needle in text, needle
    # The text gate used to read `text.count("hp_d") >= 21`, i.e. "the script states the
    # 22-arm candidate ladder".  That gate was written before the pre-run cost amendment and
    # now contradicts the registration: the registered run set is 7 arms.  The gate follows
    # the registration instead -- six non-reference arms plus the amendment record the script
    # has to state out loud -- and the stale 22-arm wording is banned outright.
    assert text.count("hp_d") >= 6
    assert "PRE_RUN_AMENDMENT" in text
    assert "5,500 fits per seed" in text
    assert "the registered arm set is the 7-arm subset" in text
    assert "no result existed" in text
    assert "pre-registers a 22-arm grid" not in text


def test_the_report_answers_the_target_question_out_loud() -> None:
    text = _report_text()
    for needle in (
        "W18-P0",
        "预注册",
        "跨 5 种子均值",
        "锚点复现",
        "0.6080587938801277",
        "0.4766400383507876",
        "0.4091179943351143",
        "不提升任何读数",
        "非盲",
        "Reaxys 数值不进入",
    ):
        assert needle in text, needle


def test_the_new_files_are_lf_and_bom_free() -> None:
    for path in (SCRIPT, PREREG, SUMMARY, REPORT, ARTIFACT):
        raw = path.read_bytes()
        assert raw.count(b"\r\n") == 0, path
        assert raw[:3] != b"\xef\xbb\xbf", path
