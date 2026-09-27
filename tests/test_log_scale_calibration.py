"""Guards for the Week 18 lane B / P6 log-space calibration probe.

Lever 3 trained in log space (R^2 0.551 there) and died on the way back (-0.105 on the
original scale).  The probe probes/dielectric_log_scale_calibration.py asks whether an
isotonic map fitted inside the training fold turns that into a positive original-scale
reading, with the pool, the splitter, the scorer, the protocol and the frozen head all
frozen.  These guards keep its promises honest: the seed-42 anchor reproduces bit for
bit or nothing is reported, the fold audit stays clean, the verdict follows the
pre-registered rule (original-scale R^2 first, secondary MAE / Spearman / AUC>30 only
as partial credit), the in-sample optimism of the calibration and the un-run variants
are stated, and no reading is promoted.

Everything here is offline: no network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_log_scale_calibration_prereg.json"
SUMMARY = ROOT / "probes/dielectric_log_scale_calibration_summary.json"
PLACEBO_SUMMARY = ROOT / "probes/dielectric_log_scale_calibration_placebo_summary.json"
REPORT = ROOT / "reports/dielectric_log_scale_calibration.md"
SCRIPT = ROOT / "probes/dielectric_log_scale_calibration.py"
ARTIFACT = ROOT / "probes/artifacts/dielectric_log_scale_calibration_repeats.csv"
PLACEBO_ARTIFACT = ROOT / "probes/artifacts/dielectric_log_scale_calibration_placebo_repeats.csv"

SEED_42_REFERENCE = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
TOLERANCE = 1e-09
SEEDS = (42, 1234, 2026, 31337, 7)
ARMS = ("reference_lever4", "log_space_raw", "log_space_isotonic")
MAE_MARGIN = 0.01
SPEARMAN_MARGIN = 0.01
AUC_MARGIN = 0.005
EXPECTED_COLUMNS = (
    "seed",
    "arm",
    "representation",
    "repeat",
    "r2",
    "mae",
    "rmse",
    "spearman",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
    "auc_gt15",
    "auc_gt30",
    "log_r2",
)
VERDICTS = ("improved", "partial", "refuted", "placebo")


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _placebo_summary() -> dict:
    return json.loads(PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def _report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_and_pins_the_rule_before_the_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["non_blind"] is True
    assert "0.6080587938801277" in prereg["non_blind_reason"]
    assert set(ARMS) == set(prereg["arms"])
    assert "log_space_isotonic_spearman" not in prereg["arms"]
    assert prereg["optional_arm_not_run"]["name"] == "log_space_isotonic_spearman"
    assert "恒等" in prereg["optional_arm_not_run"]["reason"]
    frozen = prereg["frozen"]
    assert frozen["single_representation_anchor"] == SEED_42_REFERENCE
    assert frozen["headline"] == FROZEN_HEADLINE
    assert frozen["baseline"] == FROZEN_BASELINE
    assert frozen["lever3_log_space_r2"] == 0.551
    assert frozen["anchor_tolerance"] == TOLERANCE
    assert tuple(frozen["seeds"]) == SEEDS
    rule = prereg["decision_rule"]
    assert "reference_lever4" in rule["primary"]
    assert "0.005" in rule["partial"]
    assert "不得宣称原尺度 R² 达标" in rule["reporting_duty"]
    assert "训练折" in prereg["calibration_rule"]


def test_the_frozen_anchor_reproduces_bit_for_bit_or_the_probe_is_silent() -> None:
    anchors = _summary()["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["tolerance"] == TOLERANCE
    rows = anchors["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["arm"] == "reference_lever4"
    assert row["seed"] == 42
    assert row["ok"] is True
    assert row["expected"] == SEED_42_REFERENCE
    assert abs(row["measured"] - SEED_42_REFERENCE) <= TOLERANCE
    assert row["abs_gap"] == 0.0


def test_the_seed_42_reference_reading_is_the_frozen_one() -> None:
    seeds = {int(row["seed"]): row for row in _summary()["seed_rows"] if row["arm"] == "reference_lever4"}
    assert seeds[42]["r2_mean"] == SEED_42_REFERENCE


def test_the_leakage_audit_is_clean_and_covers_every_seed() -> None:
    leakage = _summary()["leakage"]
    assert leakage["clean"] is True
    assert sorted(leakage["by_seed"], key=int) == [str(seed) for seed in sorted(SEEDS)]
    for block in leakage["by_seed"].values():
        assert block["folds"] == 50
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0


def test_the_artifact_carries_every_seed_and_arm_with_the_secondary_scales() -> None:
    rows = _csv_rows(ARTIFACT)
    assert tuple(rows[0].keys()) == EXPECTED_COLUMNS
    assert len(rows) == len(SEEDS) * len(ARMS) * 10
    seen = defaultdict(set)
    for row in rows:
        seen[(int(row["seed"]), row["arm"])].add(int(row["repeat"]))
        assert row["representation"] == "Physical(lever4)"
    for seed in SEEDS:
        for arm in ARMS:
            assert seen[(seed, arm)] == set(range(10))


def test_every_arm_reports_mae_spearman_and_auc_gt30_in_the_summary() -> None:
    for row in _summary()["seed_rows"]:
        for key in ("mae_mean", "spearman_mean", "auc_gt30_mean", "log_r2_mean"):
            assert key in row


def test_the_verdict_follows_the_registered_rule_and_is_not_promotable() -> None:
    summary = _summary()
    decision = summary["decision"]
    assert decision["verdict"] in VERDICTS
    assert decision["promotable"] is False
    assert decision["mae_partial_margin"] == MAE_MARGIN
    assert decision["spearman_partial_margin"] == SPEARMAN_MARGIN
    assert decision["auc_partial_margin"] == AUC_MARGIN
    cross = summary["cross_seed"]
    gains = summary["secondary_gains"]
    improved = cross["log_space_isotonic"] > cross["reference_lever4"]
    partial = (
        gains["mae_improvement"] >= MAE_MARGIN
        or gains["spearman_improvement"] >= SPEARMAN_MARGIN
        or gains["auc_gt30_improvement"] >= AUC_MARGIN
    )
    assert decision["secondary_partial_rule_satisfied"] is partial
    if improved:
        assert decision["verdict"] == "improved"
    elif partial:
        assert decision["verdict"] == "partial"
    else:
        assert decision["verdict"] == "refuted"


def test_the_placebo_was_run_and_its_scope_defect_is_stated() -> None:
    placebo = _summary()["placebo"]
    assert placebo["status"] == "ran"
    assert sorted(placebo["cross_seed"]) == sorted(ARMS)
    standalone = _placebo_summary()
    assert standalone["placebo"]["status"] == "this_run"
    assert standalone["placebo"]["cross_seed"] == placebo["cross_seed"]
    assert len(_csv_rows(PLACEBO_ARTIFACT)) == len(SEEDS) * len(ARMS) * 10
    text = _report_text()
    assert "只置换 457 个 scored 行" in text


def test_the_report_states_the_calibration_caveats_and_the_un_run_arm() -> None:
    text = _report_text()
    assert "in-sample" in text
    assert "交叉拟合" in text
    assert "log_space_isotonic_spearman" in text
    assert "不得" in text and "原尺度 R² 达标" in text
    for value in ("0.6080587938801277", "0.4766400383507876", "0.4091179943351143"):
        assert value in text


def test_no_reading_is_promoted_and_the_frozen_numbers_are_quoted_unchanged() -> None:
    summary = _summary()
    assert summary["frozen_control"]["headline"] == FROZEN_HEADLINE
    assert summary["frozen_control"]["baseline"] == FROZEN_BASELINE
    assert summary["frozen_control"]["single_representation_anchor"] == SEED_42_REFERENCE
    assert summary["decision"]["promotable"] is False
    text = _report_text()
    assert "任何读数都不 promote" in text


def test_the_probe_keeps_the_frozen_head_and_the_isotonic_scope_pinned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277" in source
    assert "FROZEN_HEADLINE = 0.4766400383507876" in source
    assert "FROZEN_BASELINE = 0.4091179943351143" in source
    assert "IsotonicRegression(out_of_bounds=" in source
    assert "XGB_PARAMS" in source
