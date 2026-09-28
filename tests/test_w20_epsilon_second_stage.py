"""Literal pins for the Week 20 W20-4 bounded epsilon 0.60 gun (section 28.60).

W20-4 is the only Week 20 lane permitted to touch the main scoreboard, and only when a
single pre-registered arm clears a gate that was fixed before the run.  This file pins that
contract: the locked pre-registration by digest, the 9-arm grid and its 24-arm cap, the
registered arm and its parameters, the five locked seeds, the 0.60 / 0.55 decision rule, the
seed-42 anchor, the clean leakage audit, the artifact schema, the report tokens, the placebo
collapse rule and the scoreboard accounting.  Nothing here fits a model: every test is a
literal pin read back from disk.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from probes import w20_epsilon_second_stage as stage
from probes.dielectric_observations_grouped_benchmark import METRIC_NAMES

SCRIPT = ROOT / "probes/w20_epsilon_second_stage.py"
PREREG = ROOT / "probes/w20_epsilon_second_stage_prereg.json"
SUMMARY = ROOT / "probes/w20_epsilon_second_stage_summary.json"
PLACEBO_SUMMARY = ROOT / "probes/w20_epsilon_second_stage_placebo_summary.json"
ARTIFACT = ROOT / "probes/artifacts/w20_epsilon_second_stage_repeats.csv"
FIGURE = ROOT / "probes/artifacts/w20_epsilon_second_stage_cross_seed.png"
REPORT = ROOT / "reports/w20_epsilon_second_stage.md"
SECTION = ROOT / "reports/_w20_section_w204.md"
TEST_PATH = Path(__file__)

PREREG_SHA256 = "2c60ed395d78ab97f90bf84c04c79efc192122b4d9c6d0e4d664456707b65fe0"

REGISTERED_ARM = "hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128"
REFERENCE_ARM = "xgb_reference"
INNER_ARM = "hp2_inner_cv"
SEEDS = (42, 1234, 2026, 31337, 7)
ARM_CAP = 24
TARGET_R2 = 0.60
LOWER_BOUND_MIN = 0.55
ANCHOR_TOLERANCE = 1e-09

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
FROZEN_CROSS_SEED_ENDPOINT = 0.5861142332208197
W18_BEST_CROSS_SEED = 0.5998203128630835

GRID_ARMS = (
    "xgb_reference",
    "hp2_d4_n200_lr0.05_mcw1_ss0.8_cs0.8_bin64",
    "hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin64",
    "hp2_d4_n200_lr0.05_mcw1_ss0.8_cs0.8_bin128",
    "hp2_d4_n200_lr0.05_mcw1_ss0.8_cs1.0_bin64",
    "hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128",
    "hp2_d4_n300_lr0.05_mcw5_ss0.8_cs0.8_bin128",
    "hp2_d4_n400_lr0.05_mcw5_ss0.8_cs0.8_bin128",
    "hp2_inner_cv",
)
SIDE_ARMS = tuple(arm for arm in GRID_ARMS if arm != REGISTERED_ARM)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _summary() -> dict:
    return json.loads(_text(SUMMARY))


def _placebo() -> dict:
    return json.loads(_text(PLACEBO_SUMMARY))


def test_all_deliverables_exist() -> None:
    for path in (
        SCRIPT, PREREG, SUMMARY, PLACEBO_SUMMARY, ARTIFACT, FIGURE, REPORT, SECTION,
        TEST_PATH,
    ):
        assert path.is_file(), "missing file: " + str(path)
    assert FIGURE.stat().st_size > 0


def test_new_files_are_lf_and_bom_free() -> None:
    for path in (SUMMARY, PLACEBO_SUMMARY, ARTIFACT, REPORT, SECTION, TEST_PATH):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "BOM in " + path.name
        assert b"\r\n" not in raw, "CRLF in " + path.name


def test_prereg_is_locked_and_pinned_by_digest() -> None:
    raw = PREREG.read_bytes()
    assert raw.count(b"\r\n") == 0
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    prereg = json.loads(raw.decode("utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["non_blind"] is True
    assert prereg["registered_arm"] == REGISTERED_ARM
    assert tuple(str(arm) for arm in prereg["arms"]) == GRID_ARMS
    assert tuple(int(seed) for seed in prereg["seeds"]) == SEEDS
    assert prereg["anchor_tolerance"] == ANCHOR_TOLERANCE
    assert prereg["anchors"]["xgb_reference_physical_lever4"] == FROZEN_SINGLE_REPRESENTATION


def test_prereg_grid_matches_the_module_and_the_cap() -> None:
    prereg = json.loads(_text(PREREG))
    assert prereg["grid"]["arm_count"] == len(GRID_ARMS) == len(stage.ARM_ORDER)
    assert prereg["grid"]["max_arms_cap"] == ARM_CAP
    assert len(stage.ARM_ORDER) <= ARM_CAP
    assert len(set(stage.ARM_ORDER)) == len(stage.ARM_ORDER)
    assert tuple(prereg["side_arms"]) == SIDE_ARMS
    for arm in stage.FIXED_ARMS:
        assert dict(prereg["arm_params"][arm]) == dict(stage.ARM_PARAMS[arm])


def test_the_registered_arm_is_the_d4_n200_mcw5_bin128_point() -> None:
    params = stage.ARM_PARAMS[REGISTERED_ARM]
    assert params["max_depth"] == 4
    assert params["n_estimators"] == 200
    assert params["learning_rate"] == 0.05
    assert params["min_child_weight"] == 5
    assert params["subsample"] == 0.8
    assert params["colsample_bytree"] == 0.8
    assert params["max_bin"] == 128
    assert stage.ARM_BLOCKS[REGISTERED_ARM] == "registered"
    reference = stage.ARM_PARAMS[REFERENCE_ARM]
    assert reference["max_depth"] == 2
    assert reference["n_estimators"] == 200
    assert reference["max_bin"] == 64
    assert stage.ARM_BLOCKS[REFERENCE_ARM] == "anchor"
    for arm in stage.FIXED_ARMS:
        assert stage.ARM_PARAMS[arm]["n_jobs"] == 1
        # The probe pins the model random_state itself, as
        # XGBRegressor(**ARM_PARAMS[arm], random_state=SEED) in _fold_task, so the locked
        # arm parameters must NOT carry one: a second random_state keyword would be a
        # TypeError, and a frozen value inside the dict would not even reach the model.
        assert "random_state" not in stage.ARM_PARAMS[arm]
        assert stage.SEED == 42
        assert stage.ARM_PARAMS[arm]["objective"] == "reg:squarederror"
        if arm != REFERENCE_ARM:
            assert stage.ARM_PARAMS[arm]["max_depth"] == 4
            assert 200 <= stage.ARM_PARAMS[arm]["n_estimators"] <= 400


def test_module_constants_match_the_registration() -> None:
    assert stage.REGISTERED_ARM == REGISTERED_ARM
    assert stage.ARM_REFERENCE == REFERENCE_ARM
    assert stage.ARM_INNER_CV == INNER_ARM
    assert stage.ARM_ORDER == GRID_ARMS
    assert stage.SEEDS == SEEDS
    assert stage.ANCHOR_SEED == 42
    assert stage.PLACEBO_SEED == 2026
    assert stage.MAX_GRID_ARMS == ARM_CAP
    assert stage.PASS_TARGET_R2 == TARGET_R2
    assert stage.FIVE_SEED_LOWER_BOUND_MIN == LOWER_BOUND_MIN
    assert stage.FROZEN_SINGLE_REPRESENTATION == FROZEN_SINGLE_REPRESENTATION
    assert stage.FROZEN_HEADLINE == FROZEN_HEADLINE
    assert stage.FROZEN_BASELINE == FROZEN_BASELINE
    assert stage.FROZEN_CROSS_SEED_ENDPOINT == FROZEN_CROSS_SEED_ENDPOINT
    assert stage.W18_BEST_ARM == "hp_d4_n200_lr0.05_mcw1_ss0.8_cs0.8"
    assert stage.W18_BEST_CROSS_SEED == W18_BEST_CROSS_SEED


def test_parse_arms_preserves_the_frozen_order() -> None:
    assert stage.parse_arms("") == stage.ARM_ORDER
    assert stage.parse_arms(REFERENCE_ARM) == (REFERENCE_ARM,)
    assert stage.parse_arms(INNER_ARM + "," + REFERENCE_ARM) == (
        REFERENCE_ARM, INNER_ARM,
    )
    assert stage.parse_arms(REGISTERED_ARM)[0] == REFERENCE_ARM
    with pytest.raises(SystemExit):
        stage.parse_arms("invented_arm")


def test_arm_summary_on_a_synthetic_block() -> None:
    rows = [
        {"arm": REGISTERED_ARM, "r2": 0.4},
        {"arm": REGISTERED_ARM, "r2": 0.5},
        {"arm": REGISTERED_ARM, "r2": 0.6},
        {"arm": REFERENCE_ARM, "r2": 0.6080587938801277},
    ]
    block = stage.arm_summary(rows, (REGISTERED_ARM, REFERENCE_ARM))
    registered = block[REGISTERED_ARM]
    assert registered["repeats"] == 3
    assert registered["r2_mean"] == pytest.approx(0.5, abs=1e-15)
    assert registered["r2_sd"] == pytest.approx(0.1, abs=1e-15)
    assert registered["r2_min"] == 0.4
    assert registered["r2_max"] == 0.6
    assert registered["repeats_above_060"] == 0
    assert registered["block"] == "registered"
    assert block[REFERENCE_ARM]["repeats_above_060"] == 1


def test_summary_verdict_comes_from_the_registered_arm_alone() -> None:
    summary = _summary()
    answers = summary["answers"]
    cross = {row["arm"]: float(row["r2_seed_mean"]) for row in summary["cross_seed"]}
    registered = next(
        row for row in summary["cross_seed"] if row["arm"] == REGISTERED_ARM
    )
    assert answers["registered_arm"] == REGISTERED_ARM
    assert answers["endpoint"] == "cross_seed_mean"
    assert answers["registered_arm_cross_seed_mean"] == pytest.approx(
        cross[REGISTERED_ARM], abs=1e-12,
    )
    assert answers["registered_arm_cross_seed_mean"] == pytest.approx(
        sum(registered["seed_means"]) / len(registered["seed_means"]), abs=1e-12,
    )
    lower = min(float(value) for value in registered["seed_means"])
    assert answers["registered_arm_five_seed_lower_bound"] == pytest.approx(lower, abs=1e-12)
    assert answers["pass_cross_seed_mean"] == (
        answers["registered_arm_cross_seed_mean"] >= TARGET_R2
    )
    assert answers["pass_five_seed_lower_bound"] == (lower > LOWER_BOUND_MIN)
    assert answers["gate_met"] == (
        answers["pass_cross_seed_mean"] and answers["pass_five_seed_lower_bound"]
    )
    side = [arm for arm in SIDE_ARMS if arm != REFERENCE_ARM]
    best = max(side, key=lambda arm: (cross[arm], arm))
    assert answers["best_side_arm"] == best
    assert answers["side_grid_arm_count"] == len(side)
    assert answers["seeds_run"] == list(SEEDS)
    if answers["gate_met"]:
        assert summary["verdict"] == "promoted"
        assert summary["promotion"]["promoted"] is True
    else:
        assert summary["verdict"] == "not_promoted"
        assert summary["promotion"]["promoted"] is False


def test_scoreboard_ledger_follows_the_gate() -> None:
    summary = _summary()
    ledger = summary["promotion"]["main_scoreboard_ledger"]
    assert ledger["week"] == "week20"
    assert ledger["lane"] == "W20-4"
    assert ledger["section"] == "28.60"
    if summary["answers"]["gate_met"]:
        assert ledger["attempts_this_week"] == 1
        assert ledger["attempts_cumulative"] == 12
        assert ledger["attempt_index"] == 12
    else:
        assert ledger["attempts_this_week"] == 0
        assert ledger["attempts_cumulative"] == 11
        assert "did not clear" in ledger["reason"]
    assert summary["promotion"]["frozen_headline"] == FROZEN_HEADLINE
    assert summary["promotion"]["frozen_baseline"] == FROZEN_BASELINE


def test_summary_anchor_and_frozen_side_did_not_move() -> None:
    summary = _summary()
    contract = summary["contract"]
    assert contract["representation"] == "Physical(lever4)"
    assert contract["n_splits"] == 5
    assert contract["n_repeats"] == 10
    assert contract["anchor_seed"] == 42
    assert contract["model_random_state"] == 42
    assert summary["pool"]["base_rows"] == 2029
    assert summary["pool"]["scored_rows"] == 457
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["tolerance"] == ANCHOR_TOLERANCE
    row = anchors["rows"][0]
    assert row["arm"] == REFERENCE_ARM
    assert row["seed"] == 42
    assert row["expected"] == FROZEN_SINGLE_REPRESENTATION
    assert row["measured"] == pytest.approx(FROZEN_SINGLE_REPRESENTATION, abs=ANCHOR_TOLERANCE)
    assert row["ok"] is True
    for seed_row in summary["seed_rows"]:
        assert seed_row["repeats"] == 10


def test_summary_leakage_is_clean() -> None:
    leakage = _summary()["leakage"]
    assert leakage["clean"] is True
    for block in leakage["by_seed"].values():
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0
    assert sum(leakage["folds_by_seed"].values()) == 50 * len(GRID_ARMS) * len(SEEDS)


def test_artifact_keeps_the_frozen_repeat_schema() -> None:
    with ARTIFACT.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == ["seed", "arm", "representation", "repeat", *METRIC_NAMES]
    assert len(rows) == len(SEEDS) * len(GRID_ARMS) * 10
    for seed in SEEDS:
        present = {row["arm"] for row in rows if int(row["seed"]) == seed}
        assert present == set(GRID_ARMS)
    assert all(row["representation"] == "Physical(lever4)" for row in rows)


def test_report_states_the_rule_anchors_and_figure() -> None:
    text = _text(REPORT)
    for needle in (
        "W20-4",
        "28.60",
        REGISTERED_ARM,
        "0.600000",
        "0.550000",
        "0.6080587938801277",
        "0.4766400383507876",
        "0.4091179943351143",
        "0.5861142332208197",
        "0.5998203128630835",
        "w20_epsilon_second_stage_cross_seed.png",
        "Reaxys",
    ):
        assert needle in text, "report is missing " + needle


def test_section_file_starts_with_the_pinned_heading() -> None:
    first = _text(SECTION).splitlines()[0]
    assert first.startswith("## 28.60 ")
    assert first.endswith("\uff08" + "2026-09-28" + "\uff09")


def test_placebo_summary_records_the_collapse_rule() -> None:
    summary = _placebo()
    assert summary["placebo"] is True
    assert summary["verdict"] == "placebo"
    assert summary["promotion"]["promoted"] is False
    check = summary["placebo_check"]
    assert check["real_registered_arm_cross_seed_mean"] == pytest.approx(
        _summary()["answers"]["registered_arm_cross_seed_mean"], abs=1e-12,
    )
    assert check["collapsed"] == (
        check["registered_arm_cross_seed_mean"] < TARGET_R2
        and check["registered_arm_cross_seed_mean"]
        < check["real_registered_arm_cross_seed_mean"]
    )
    assert check["collapsed"] is True

