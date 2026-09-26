"""Week 17 arm W17-6: lever 4 and lever 8 carried into the model together.

Lever 4 (``probes/dielectric_xtb_full_table_migration.py``) replaced the dipole-derived
columns of the frozen physical block with v0.4 conformer means and moved the main
scoreboard by +0.0558. Lever 8 (``probes/dielectric_coordination_block_v2.py``) appended
the five Li+ coordination columns and moved the same scoreboard by +0.0441 under an
amended placebo clause. The two were never scored together; that is the two-shot merge
discipline AB-3.

This module is that merge, and it does three things only:

* it re-runs the frozen baseline inside this script and refuses to quote any delta unless
  the baseline reproduces 0.4091179943351143 to within 1e-9;
* it adds no new chemistry: lever 4 is read byte identical from the v0.4 conformer
  artefact and lever 8 byte identical from the v1 coordination artefact, so no xTB runs;
* it scores the merge arm once and reports its delta against the re-run baseline AND
  against the best single arm, so a merge that adds nothing is visible.

The individual readings may NOT be added. +0.0558 + 0.0441 = +0.0999 is recorded in the
pre-registration only to be refused; the merge delta is measured, never predicted.

Discipline restated from the code that defines it, never from memory:

    scoreboard : 457 rows / 97 compounds, GroupKFold by InChIKey, 5 folds x 10 repeats,
                 seed 42, XGBRegressor with the frozen hyper-parameters
    baseline   : must reproduce 0.4091179943351143 to within 1e-9, or the whole shot is
                 stamped `unverified` and no delta may be quoted
    pass       : delta R2 >= +0.0200 against the re-run baseline AND the reused amended
                 placebo clause collapsed -> pass_merged_blocks
    kill       : delta R2 < +0.0050, or a failed baseline, or a clause that does not hold
                 -> dead, reported as dead

The v1 decision ``dead`` and the v2 decision ``pass_under_amended_placebo_clause`` are
quoted verbatim in the summary and are never rewritten by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coordination_block as v1
import dielectric_coordination_block_v2 as v2
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_representation_ablation import SEED
from dielectric_room_window_paired import HYBRID

from electrolyte_ml.pathing import portable_relative_path

TASK_ID = "week17_lever4_lever8_merge_main_scoreboard"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_prereg_v3.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v3_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_coordination_block_v3.md"

ARTIFACT_STEM = "dielectric_coordination_block_v3"
COORDINATION_FEATURES = ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
CONFORMER_FEATURES = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
MIGRATION_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_xtb_full_table_migration_summary.json"
)
V1_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_summary.json"
V2_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v2_summary.json"
V2_PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_prereg_v2.json"

ARM_BASELINE = "baseline"
ARM_PLUS_LEVER4 = "plus_lever4"
ARM_PLUS_LEVER8 = "plus_lever8"
ARM_PLUS_BOTH = "plus_both"
ARM_PLACEBO = "placebo_shuffled_target"
ARM_CONTRAST_BASELINE = "baseline_features_shuffled_target"
ARM_CONTRAST_LEVER4 = "lever4_features_shuffled_target"
ARM_FLOOR = "no_information_floor"
ARM_FLOOR_REAL = "no_information_floor_real_labels"

#: Arms that fit the frozen model. The baseline is the reference, not a shot; the two
#: shuffled-label contrast arms are required by the amended clause, not extra shots.
FITTED_ARMS = (
    ARM_BASELINE,
    ARM_PLUS_LEVER4,
    ARM_PLUS_LEVER8,
    ARM_PLUS_BOTH,
    ARM_PLACEBO,
    ARM_CONTRAST_BASELINE,
    ARM_CONTRAST_LEVER4,
)
#: Arms that fit nothing at all: the training-fold mean on the same folds.
FLOOR_ARMS = (ARM_FLOOR, ARM_FLOOR_REAL)
ARM_ORDER = (*FITTED_ARMS, *FLOOR_ARMS)

ROLE = {
    ARM_BASELINE: "reference (real labels, frozen v03 physical + Morgan)",
    ARM_PLUS_LEVER4: "lever 4 alone (v0.4 conformer-averaged dipole, real labels)",
    ARM_PLUS_LEVER8: "lever 8 alone (the five coordination columns, real labels)",
    ARM_PLUS_BOTH: "THE SHOT (lever 4 and lever 8 together, real labels)",
    ARM_PLACEBO: "placebo (the merged pipeline, shuffled labels)",
    ARM_CONTRAST_BASELINE: "contrast (frozen feature set, the SAME shuffled labels)",
    ARM_CONTRAST_LEVER4: "contrast (lever-4 pipeline, the SAME shuffled labels)",
    ARM_FLOOR: "no-information floor (training-fold mean, the SAME shuffled labels)",
    ARM_FLOOR_REAL: "no-information floor on the real labels (context)",
}

BASELINE_R2 = 0.4091179943351143
REPRODUCTION_TOLERANCE = 1e-09
PASS_DELTA = 0.0200
KILL_DELTA = 0.0050
PLACEBO_TOLERANCE = 0.0200

SHOTS_THIS_RUN = 1
SHOTS_LEVER4_BEFORE = 1
SHOTS_LEVER8_BEFORE = 2

#: Published single-lever readings this shot has to reproduce, quoted from the artefacts.
LEVER4_PUBLISHED_R2 = 0.4649564468823552
LEVER4_PUBLISHED_DELTA = 0.0558384525472409
LEVER8_PUBLISHED_R2 = 0.4531768105508106
LEVER8_PUBLISHED_DELTA = 0.044058816215696295
#: Recorded only to be refused: the deltas are never added to predict the merge.
NAIVE_SUM_DELTA = LEVER4_PUBLISHED_DELTA + LEVER8_PUBLISHED_DELTA

DECISION_VOCABULARY = ("pass_merged_blocks", "sub_threshold", "dead", "unverified")

FOLD_COLUMNS = v1.FOLD_COLUMNS_OUT
REPEAT_COLUMNS = v1.REPEAT_COLUMNS_OUT
PREDICTION_COLUMNS = v1.PREDICTION_COLUMNS_OUT

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    return v1.read_csv_rows(path)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# the reused amended placebo clause (identical in form to v2, lever 2, lever 9)
# --------------------------------------------------------------------------- #


def fold_mean_floor(
    name: str,
    *,
    target: np.ndarray,
    temperatures: np.ndarray,
    groups: Sequence[str],
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> dict[str, object]:
    """The no-information floor, reused verbatim from the v2 second shot."""

    return v2.fold_mean_floor(
        name,
        target=target,
        temperatures=temperatures,
        groups=groups,
        splits=splits,
    )


def placebo_collapse_readout(
    *,
    placebo_r2: float,
    placebo_floor_r2: float,
    same_block_real_r2: float,
    placebo_baseline_features_r2: float,
    real_baseline_r2: float,
) -> dict[str, object]:
    """The v2 amended clause, reused verbatim.

    The placebo arm carries the MERGED pipeline on the shuffled labels, so rule 2 reads
    it against ``plus_both`` and rule 3 reads it against the frozen feature set on the
    identical shuffled vector. Nothing about the three rules is widened here.
    """

    return v2.placebo_collapse_readout(
        placebo_r2=placebo_r2,
        placebo_floor_r2=placebo_floor_r2,
        same_block_real_r2=same_block_real_r2,
        placebo_baseline_features_r2=placebo_baseline_features_r2,
        real_baseline_r2=real_baseline_r2,
    )


# --------------------------------------------------------------------------- #
# the merge account and the verdict
# --------------------------------------------------------------------------- #


def merge_readings(*, arms: Mapping[str, object], baseline_r2: float) -> dict[str, object]:
    """The merge arm against the baseline, each single arm, and the refused sum.

    The deltas are measured here, on this run's folds. The naive sum is carried beside
    them and labelled forbidden: the point of the merge shot is that the combined effect
    is measured, not predicted, because the two blocks touch the same physical axis.
    """

    lever4_delta = float(arms[ARM_PLUS_LEVER4][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
    lever8_delta = float(arms[ARM_PLUS_LEVER8][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
    both_delta = float(arms[ARM_PLUS_BOTH][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
    best_arm = ARM_PLUS_LEVER4 if lever4_delta >= lever8_delta else ARM_PLUS_LEVER8
    best_delta = max(lever4_delta, lever8_delta)
    return {
        "delta_vs_baseline": both_delta,
        "single_arm_deltas": {ARM_PLUS_LEVER4: lever4_delta, ARM_PLUS_LEVER8: lever8_delta},
        "best_single_arm": best_arm,
        "best_single_delta": best_delta,
        "delta_vs_best_single": both_delta - best_delta,
        "increment_over_lever4": both_delta - lever4_delta,
        "increment_over_lever8": both_delta - lever8_delta,
        "naive_sum_of_singles": NAIVE_SUM_DELTA,
        "merge_over_naive_sum": both_delta - NAIVE_SUM_DELTA,
        "forbidden_extrapolation": (
            "the single-lever deltas are never added. The merge delta is measured, not "
            "predicted; a reader who wants the combined effect reads this run, not a sum."
        ),
    }


def build_verdict(
    *,
    baseline_r2: float,
    delta_r2: float,
    collapse: Mapping[str, object],
    mae_gt60_delta: float,
    positive_repeats: int,
    repeats_total: int,
    criteria: Mapping[str, object],
) -> dict[str, object]:
    """Apply the v3 criteria in the order the pre-registration froze them."""

    reproduced = abs(float(baseline_r2) - BASELINE_R2) <= REPRODUCTION_TOLERANCE
    collapsed = bool(collapse["collapsed"])
    reasons: list[str] = []
    if not reproduced:
        decision = "unverified"
        reasons.append(
            f"the baseline arm reproduced {float(baseline_r2)!r} against the published "
            f"{BASELINE_R2!r}; no delta from this shot may be quoted"
        )
    elif not collapsed:
        decision = "dead"
        reasons.append(
            "the reused amended placebo clause did not hold "
            f"(over the floor {float(collapse['over_the_floor']):+.4f}, against the same merged "
            f"pipeline on real labels {float(collapse['delta_vs_the_same_pipeline_real_arm']):+.4f}, "
            f"within the pipeline {float(collapse['within_pipeline_delta_r2']):+.4f})"
        )
    elif float(delta_r2) >= PASS_DELTA:
        decision = "pass_merged_blocks"
        reasons.append(
            f"lever 4 and lever 8 together moved grouped {HYBRID} R2 by {float(delta_r2):+.4f} "
            f"against the re-run baseline and the reused amended placebo clause collapsed; the "
            f"merge arm beat the baseline in {positive_repeats} of {repeats_total} repeats. The v1 "
            "decision remains `dead`, the v2 decision remains `pass_under_amended_placebo_clause`, "
            "and this is a third, separately counted shot."
        )
    elif float(delta_r2) < KILL_DELTA:
        decision = "dead"
        reasons.append(f"delta R2 {float(delta_r2):+.4f} is below the +{KILL_DELTA:.4f} kill line")
    else:
        decision = "sub_threshold"
        reasons.append(
            f"delta R2 {float(delta_r2):+.4f} is above the kill line +{KILL_DELTA:.4f} but below "
            f"the pass line +{PASS_DELTA:.4f}"
        )
    return {
        "decision": decision,
        "reasons": reasons,
        "passed": bool(decision == "pass_merged_blocks"),
        "baseline_reproduced": bool(reproduced),
        "baseline_r2": float(baseline_r2),
        "baseline_r2_published": BASELINE_R2,
        "baseline_abs_delta": abs(float(baseline_r2) - BASELINE_R2),
        "delta_r2": float(delta_r2),
        "pass_bar": PASS_DELTA,
        "kill_line": KILL_DELTA,
        "primary_met": bool(float(delta_r2) >= PASS_DELTA),
        "placebo_collapsed": collapsed,
        "mae_gt60_not_worse": bool(float(mae_gt60_delta) <= 0.0),
        "mae_gt60_delta": float(mae_gt60_delta),
        "positive_repeats": int(positive_repeats),
        "repeats_total": int(repeats_total),
        "criteria_applied": {
            "pass_criterion": criteria["pass_criterion"],
            "kill_line": criteria["kill_line"],
            "placebo_rule": (
                "rule 1 floor upper bound AND rule 2 same-merged-pipeline real-label arm AND "
                "rule 3 within-pipeline shuffled contrast, all at +0.0200"
            ),
        },
        "v1_decision_is_still_in_force": "dead",
        "v2_decision_is_still_in_force": "pass_under_amended_placebo_clause",
        "not_a_gate_but_reported": "mae_gt60, MAE, RMSE, Spearman and the merge-over-single deltas",
    }
# --------------------------------------------------------------------------- #
# report (Chinese, per the W17-6 deliverable spec)
# --------------------------------------------------------------------------- #

ROLE_ZH = {
    ARM_BASELINE: "参考臂（真标签，冻结 v03 physical + Morgan，本脚本内重跑）",
    ARM_PLUS_LEVER4: "杠杆 4 单臂（v0.4 构象平均偶极，真标签）",
    ARM_PLUS_LEVER8: "杠杆 8 单臂（五列配位块，真标签）",
    ARM_PLUS_BOTH: "本轮 shot（杠杆 4 与杠杆 8 同时入模，真标签）",
    ARM_PLACEBO: "placebo（合并后管线，标签打乱）",
    ARM_CONTRAST_BASELINE: "对照（冻结特征集，同一打乱标签）",
    ARM_CONTRAST_LEVER4: "对照（杠杆 4 管线，同一打乱标签）",
    ARM_FLOOR: "无信息下限（训练折均值，同一打乱标签）",
    ARM_FLOOR_REAL: "无信息下限（真标签，语境）",
}

_DECISION_ZH = {
    "pass_merged_blocks": "过门",
    "sub_threshold": "未过门（介于杀线与过门线之间）",
    "dead": "未过门（dead）",
    "unverified": "未过门（unverified，基线未复现）",
}


def _arm_metric(arms: Mapping[str, object], arm: str, metric: str) -> float:
    return float(arms[arm][HYBRID][metric]["mean"])  # type: ignore[index]


def format_report(summary: Mapping[str, object]) -> list[str]:
    """Render the report from the summary; the md on disk is this text."""

    verdict = summary["verdict"]  # type: ignore[index]
    arms = summary["arms"]  # type: ignore[index]
    collapse = summary["collapse"]  # type: ignore[index]
    deltas = summary["paired_deltas"]  # type: ignore[index]
    scoreboard = summary["scoreboard"]  # type: ignore[index]
    shuffled = summary["shuffled_vector"]  # type: ignore[index]
    shots = summary["shots"]  # type: ignore[index]
    merge = summary["merge_readings"]  # type: ignore[index]
    repro = summary["reproduction_checks"]  # type: ignore[index]
    quoted = summary["quoted_prior_verdicts"]  # type: ignore[index]
    lever4 = summary["lever4_block"]  # type: ignore[index]
    block = summary["coordination_block"]  # type: ignore[index]
    telemetry = summary["run_telemetry"]  # type: ignore[index]
    lines: list[str] = []
    lines.append("# W17-6 杠杆 4 与杠杆 8 同时入模 —— 冻结主记分牌合并臂")
    lines.append("")
    lines.append(f"- 生成时间: `{summary['generated_at_utc']}`")
    lines.append(
        f"- 预注册 (v3): `{summary['preregistration']['path']}`"  # type: ignore[index]
        f" (sha256 `{summary['preregistration']['sha256']}`,"  # type: ignore[index]
        f" 锁定 {summary['preregistration']['locked_at_utc']})"  # type: ignore[index]
    )
    lines.append(f"- 判决: **{verdict['decision']}** —— {_DECISION_ZH[verdict['decision']]}")  # type: ignore[index]
    lines.append("")
    for reason in verdict["reasons"]:  # type: ignore[index]
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## 与 v1 / v2 并列阅读，绝不覆盖")
    lines.append("")
    lines.append(
        "- v1 (`probes/dielectric_coordination_block_summary.json`) 记录 **dead**，且仍然记录"
        " **dead**；其预注册与全部产物逐字节未动。"
    )
    lines.append(
        f"- v2 (`probes/dielectric_coordination_block_v2_summary.json`) 记录"
        f" **{quoted['v2']['decision_verbatim']}**，且仍然逐字如此（delta R2"
        f" {float(quoted['v2']['delta_r2_verbatim']):+.4f}）。"
    )
    lines.append(
        "- 本轮合并是单独计数的第三次 shot：它既不推翻 v1 的 `dead`，也不等同于 v2 的"
        " `pass_under_amended_placebo_clause`。"
    )
    lines.append(
        "- 两块从未合并复测（戒律 AB-3）；本轮是第一次合并，且**不把单臂 delta 相加外推**。"
    )
    lines.append("")
    lines.append("## 记分牌")
    lines.append("")
    lines.append(
        f"- 计分行 {scoreboard['scored_rows']}，化合物 {scoreboard['compounds_scored']}，"
        f"折数 {scoreboard['folds']}，repeats {scoreboard['executed_repeats']}"
    )
    lines.append(f"- 跨折化合物: {scoreboard['folds_with_a_straddling_compound']}")
    lines.append(
        f"- 打乱标签向量: seed {shuffled['seed']}，sha256 `{shuffled['permutation_sha256']}`"
        " —— 沿用 v1/v2，不重抽"
    )
    lines.append("- 本 shot 执行的 xTB: **否**（两块都逐字节复用冻结产物，成本为 0）")
    lines.append("")
    lines.append("## 两块")
    lines.append("")
    lines.append(
        f"- 杠杆 4（构象平均偶极）: 迁移 {lever4['migrated_rows']} 行 /"
        f" {lever4['migrated_compounds']} 化合物，计分池覆盖"
        f" {lever4['scored_compounds_migrated']}/{lever4['scored_compounds_total']}；"
        f"列 {list(lever4['migrated_columns'])}"
    )
    lines.append(
        f"- 杠杆 8（Li⁺ 配位块）: {block['compounds_ok']} 化合物可用块，五列"
        f" {list(block['columns'])}，逐字节读自 v1 特征产物"
    )
    lines.append("")
    lines.append("## 各臂读数")
    lines.append("")
    lines.append("| 臂 | 角色 | R2 | MAE | Spearman | MAE>60 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for arm in ARM_ORDER:
        lines.append(
            f"| `{arm}` | {ROLE_ZH[arm]} | {_arm_metric(arms, arm, 'r2'):.4f}"
            f" | {_arm_metric(arms, arm, 'mae'):.4f} | {_arm_metric(arms, arm, 'spearman'):.4f}"
            f" | {_arm_metric(arms, arm, 'mae_gt60'):.4f} |"
        )
    lines.append("")
    lines.append("## 合并读数（`plus_both` 对基线与各单臂）")
    lines.append("")
    lines.append(f"- 合并臂 delta R2 对基线: {merge['delta_vs_baseline']:+.6f}")
    lines.append(
        f"- 单臂 delta: `plus_lever4` {merge['single_arm_deltas'][ARM_PLUS_LEVER4]:+.6f},"
        f" `plus_lever8` {merge['single_arm_deltas'][ARM_PLUS_LEVER8]:+.6f}"
    )
    lines.append(
        f"- 最佳单臂: `{merge['best_single_arm']}` ({merge['best_single_delta']:+.6f})；"
        f"合并臂相对最佳单臂 {merge['delta_vs_best_single']:+.6f}"
    )
    lines.append(
        f"- 合并臂相对 `plus_lever4` 的增量 {merge['increment_over_lever4']:+.6f}；"
        f"相对 `plus_lever8` 的增量 {merge['increment_over_lever8']:+.6f}"
    )
    lines.append(
        f"- **禁止外推**: 单臂 +0.0558384525472409 (杠杆 4) 与 +0.044058816215696295 (杠杆 8)"
        f" 相加 = {merge['naive_sum_of_singles']:+.6f}，这个数**不是读数**，只登记以便拒绝；"
        f"实测合并 delta 与该和的差 {merge['merge_over_naive_sum']:+.6f}"
    )
    lines.append("")
    lines.append("## 复用的修订 placebo 条款（三读需同时成立）")
    lines.append("")
    lines.append(
        f"- 规则 1，下限上界: placebo {collapse['placebo_r2']:+.4f} 减下限"
        f" {collapse['placebo_floor_r2']:+.4f} = {collapse['over_the_floor']:+.4f}"
        f" -> 成立: {collapse['floor_rule_holds']}"
    )
    lines.append(
        f"- 规则 2，同一合并管线真标签臂: placebo 减 `plus_both`"
        f" = {collapse['delta_vs_the_same_pipeline_real_arm']:+.4f}"
        f" -> 成立: {collapse['real_arm_rule_holds']}"
    )
    lines.append(
        f"- 规则 3，同管线打乱对照: placebo 减同一打乱标签下的冻结特征集"
        f" = {collapse['within_pipeline_delta_r2']:+.4f}"
        f" -> 成立: {collapse['within_pipeline_rule_holds']}"
    )
    lines.append(
        f"- 每条规则容差: {collapse['tolerance']}；**塌缩: {collapse['collapsed']}**"
    )
    lines.append(f"- 下限定义: {collapse['placebo_floor_definition']}")
    lines.append(
        f"- 另一读数（仅报告，非门）: placebo 低于真标签基线"
        f" {collapse['delta_vs_the_real_label_baseline']:+.4f}"
    )
    lines.append("")
    lines.append("## 配对 delta (`plus_both` - `baseline`)")
    lines.append("")
    lines.append("| 指标 | delta |")
    lines.append("| --- | --- |")
    for metric in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60"):
        lines.append(f"| {metric} | {deltas[metric]:+.4f} |")
    lines.append("")
    lines.append("## 复现检查")
    lines.append("")
    lines.append(
        f"- `baseline`: {repro['baseline']['observed']:.16f} vs 已发布"
        f" {repro['baseline']['published']:.16f}（绝对差 {repro['baseline']['abs_delta']:.2e}，"
        f"容差 {repro['tolerance']:.0e}）"
    )
    lines.append(
        f"- `plus_lever4` vs 迁移发布值: {repro['plus_lever4_vs_migration_publication']['observed']:.16f}"
        f" vs {repro['plus_lever4_vs_migration_publication']['published']:.16f}"
        f"（绝对差 {repro['plus_lever4_vs_migration_publication']['abs_delta']:.2e}）"
    )
    lines.append(
        f"- `plus_lever8` vs v2 发布值: {repro['plus_lever8_vs_v2_publication']['observed']:.16f}"
        f" vs {repro['plus_lever8_vs_v2_publication']['published']:.16f}"
        f"（绝对差 {repro['plus_lever8_vs_v2_publication']['abs_delta']:.2e}）"
    )
    lines.append("")
    lines.append("## 运行遥测")
    lines.append("")
    lines.append(
        f"- 墙钟 {telemetry['wall_seconds']:.1f} s，jobs {telemetry['jobs']}，"
        f"Python {telemetry['python']}，平台 {telemetry['platform']}"
    )
    lines.append(
        "- 各臂耗时 (s): "
        + ", ".join(f"{arm} {seconds:.1f}" for arm, seconds in telemetry["arm_seconds"].items())
    )
    lines.append("")
    lines.append("## shots 记账")
    lines.append("")
    lines.append(f"- 本轮 shot: {shots['this_shot']}")
    lines.append(f"- 杠杆 4 此前 shot: {shots['lever_4_shots_before']}")
    lines.append(f"- 杠杆 8 此前 shot: {shots['lever_8_shots_before']}")
    lines.append(f"- 本轮之后杠杆 4 + 杠杆 8 项目累计 shot: {shots['programme_total_after_this_run']}")
    lines.append(f"- 规则: {shots['policy']}")
    lines.append(f"- {shots['this_probe_does_not_edit_it']}")
    lines.append("")
    lines.append("## 诚实边界")
    lines.append("")
    for boundary in summary["honest_boundaries"]:  # type: ignore[index]
        lines.append(f"- {boundary}")
    lines.append("")
    lines.append("## 文件")
    lines.append("")
    for name, path in sorted(summary["outputs"].items()):  # type: ignore[index]
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return lines
# --------------------------------------------------------------------------- #
# self-check
# --------------------------------------------------------------------------- #


def check_artifacts() -> int:
    """Re-derive the released v3 numbers from the artefacts on disk."""

    problems: list[str] = []
    for name in ("folds", "repeats", "predictions"):
        path = ARTIFACTS_DIR / (ARTIFACT_STEM + "_" + name + ".csv")
        if not path.is_file():
            problems.append(f"missing artefact {path.name}")
            continue
        blob = path.read_bytes()
        if b"\r\n" in blob:
            problems.append(f"{path.name} is not LF-only")
        if blob.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{path.name} carries a BOM")
    if not SUMMARY_PATH.is_file():
        print("MISSING " + str(SUMMARY_PATH))
        return 1
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    prereg = load_prereg()
    if sha256_of(PREREG_PATH) != summary["preregistration"]["sha256"]:
        problems.append("the v3 pre-registration is not the one recorded in the summary")
    for relative, digest in prereg["v1_and_v2_are_not_edited"][
        "v1_and_v2_artefact_digests_observed_at_lock_time"
    ].items():
        if sha256_of(REPOSITORY_ROOT / relative) != digest:
            problems.append(f"a v1/v2 artefact moved: {relative}")
    for entry in prereg["frozen_red_lines_untouched"]:
        relative, _, digest = entry.partition(" digest ")
        if not digest or sha256_of(REPOSITORY_ROOT / relative) != digest:
            problems.append(f"a frozen red line moved: {relative}")
    arms = summary["arms"]
    baseline = float(arms[ARM_BASELINE][HYBRID]["r2"]["mean"])
    if abs(baseline - BASELINE_R2) > REPRODUCTION_TOLERANCE:
        problems.append("the recorded baseline is not the published R2")
    delta = float(arms[ARM_PLUS_BOTH][HYBRID]["r2"]["mean"]) - baseline
    if abs(delta - float(summary["verdict"]["delta_r2"])) > 1e-12:
        problems.append("the recorded verdict delta disagrees with the arm table")
    if abs(float(summary["merge_readings"]["delta_vs_baseline"]) - delta) > 1e-12:
        problems.append("the merge reading disagrees with the arm table")
    collapse = summary["collapse"]
    reading = summary["collapse_arms"]
    if abs((reading["placebo_r2"] - reading["floor_r2"]) - collapse["over_the_floor"]) > 1e-12:
        problems.append("the floor reading disagrees with the arm table")
    if bool(collapse["floor_rule_holds"]) != (
        reading["placebo_r2"] - reading["floor_r2"] <= PLACEBO_TOLERANCE
    ):
        problems.append("the floor rule disagrees with the arm table")
    if bool(collapse["collapsed"]) != (
        bool(collapse["floor_rule_holds"])
        and bool(collapse["real_arm_rule_holds"])
        and bool(collapse["within_pipeline_rule_holds"])
    ):
        problems.append("the collapse flag disagrees with its three rules")
    if summary["verdict"]["v1_decision_is_still_in_force"] != "dead":
        problems.append("the v1 decision was dropped")
    if summary["verdict"]["v2_decision_is_still_in_force"] != "pass_under_amended_placebo_clause":
        problems.append("the v2 decision was dropped")
    report = REPORT_PATH.read_text(encoding="utf-8").splitlines()
    if report != format_report(summary):
        problems.append("reports/dielectric_coordination_block_v3.md is not format_report(summary)")
    for problem in problems:
        print("PROBLEM " + problem)
    printed = ", ".join(f"{arm}={float(arms[arm][HYBRID]['r2']['mean']):.4f}" for arm in FITTED_ARMS)
    print(
        printed
        + f", floor={float(arms[ARM_FLOOR][HYBRID]['r2']['mean']):.4f}"
        + f", problems={len(problems)}"
    )
    return 1 if problems else 0


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #


def _honest_boundaries(*, collapse: Mapping[str, object]) -> list[str]:
    return [
        (
            "v1 的 `dead` 仍然有效，v2 的 `pass_under_amended_placebo_clause` 仍然逐字有效；本轮合并"
            "既不推翻 v1，也不等同于 v2，是单独计数的第三次 shot。"
        ),
        (
            "本次两块都逐字节读自冻结产物（v1 配位块特征、v0.4 构象偶极），因此本 shot 不跑 xTB，"
            "特征侧按构造冻结，不引入新化学。"
        ),
        (
            "两块触及同一物理轴（极性 / Li⁺ 配位），单臂 delta 极可能重叠；禁止把杠杆 4 的 +0.0558 与"
            "杠杆 8 的 +0.0441 相加外推，合并 delta 只认本轮实测。"
        ),
        (
            "合并臂相对最佳单臂的增量仅旁列报告、不入门：冻结判据只认对基线的 delta R2 与复用的"
            "修订 placebo 条款。"
        ),
        (
            "杠杆 4 只覆盖计分池 95/97 化合物，缺 2 个（无 xTB 特征块的离子液体）；冻结模型原生处理"
            "缺失值。"
        ),
        (
            "杠杆 8 有 9 个化合物无 O 也无 N，按预注册的位点规则把块留空为 NaN，而不是填值。"
        ),
        (
            "GFN2-xTB 对 Li⁺ 过度成键；只使用结合能在化合物间的分布，绝不把其绝对值当作热化学。"
        ),
        (
            "Li⁺ 络合物为气相单分子：无阴离子、无溶剂-溶剂竞争——正是综述自己指出的结合能描述符弱点。"
        ),
        (
            "mae_gt60、MAE、RMSE、Spearman 以及合并-单臂增量仅旁列报告，不构成 v3 判据。"
        ),
        (
            f"placebo 臂低于真标签基线 {float(collapse['delta_vs_the_real_label_baseline']):+.4f}；"
            "这是打乱标签的预期符号，仅作完整性报告——把该距离当真门的 v1 条款在本轮被沿用其修订形式，"
            "而非删除。"
        ),
    ]


def build_summary(
    *,
    scoreboard: Mapping[str, object],
    block_report: Mapping[str, object],
    lever4_report: Mapping[str, object],
    fitted: Mapping[str, Mapping[str, object]],
    floors: Mapping[str, Mapping[str, object]],
    shuffled: np.ndarray,
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    if v2.PLACEBO_TOLERANCE != PLACEBO_TOLERANCE:
        raise ValueError("the reused v2 placebo tolerance drifted from the v3 pre-registration")
    arms: dict[str, object] = {arm: fitted[arm]["summary"] for arm in FITTED_ARMS}
    for arm in FLOOR_ARMS:
        arms[arm] = floors[arm]["summary"]
    prereg = load_prereg()
    baseline_r2 = float(arms[ARM_BASELINE][HYBRID]["r2"]["mean"])  # type: ignore[index]
    both_r2 = float(arms[ARM_PLUS_BOTH][HYBRID]["r2"]["mean"])  # type: ignore[index]
    delta_r2 = both_r2 - baseline_r2
    deltas = {
        metric: float(arms[ARM_PLUS_BOTH][HYBRID][metric]["mean"])  # type: ignore[index]
        - float(arms[ARM_BASELINE][HYBRID][metric]["mean"])  # type: ignore[index]
        for metric in METRIC_NAMES
    }
    collapse = placebo_collapse_readout(
        placebo_r2=float(arms[ARM_PLACEBO][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        placebo_floor_r2=float(arms[ARM_FLOOR][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        same_block_real_r2=both_r2,
        placebo_baseline_features_r2=float(
            arms[ARM_CONTRAST_BASELINE][HYBRID]["r2"]["mean"]  # type: ignore[index]
        ),
        real_baseline_r2=baseline_r2,
    )
    merge = merge_readings(arms=arms, baseline_r2=baseline_r2)
    hybrid_rows = [
        row for row in fitted[ARM_PLUS_BOTH]["repeat_rows"] if str(row["representation"]) == HYBRID
    ]
    baseline_by_repeat = {
        int(row["repeat"]): float(row["r2"])
        for row in fitted[ARM_BASELINE]["repeat_rows"]
        if str(row["representation"]) == HYBRID
    }
    positive = sum(
        1 for row in hybrid_rows if float(row["r2"]) > baseline_by_repeat[int(row["repeat"])]
    )
    verdict = build_verdict(
        baseline_r2=baseline_r2,
        delta_r2=delta_r2,
        collapse=collapse,
        mae_gt60_delta=deltas["mae_gt60"],
        positive_repeats=positive,
        repeats_total=len(hybrid_rows),
        criteria=prereg,
    )
    lever4_r2 = float(arms[ARM_PLUS_LEVER4][HYBRID]["r2"]["mean"])  # type: ignore[index]
    lever8_r2 = float(arms[ARM_PLUS_LEVER8][HYBRID]["r2"]["mean"])  # type: ignore[index]
    v1_summary = json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))
    v2_summary = json.loads(V2_SUMMARY_PATH.read_text(encoding="utf-8"))
    if str(v1_summary["verdict"]["decision"]) != "dead":
        raise ValueError("the v1 decision on disk is no longer `dead`")
    if str(v2_summary["verdict"]["decision"]) != "pass_under_amended_placebo_clause":
        raise ValueError("the v2 decision on disk is no longer the amended-clause pass")
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "generated_at_utc": _utc_now(),
        "seed": SEED,
        "run_telemetry": dict(telemetry),
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_of(PREREG_PATH),
            "locked_at_utc": prereg["locked_at_utc"],
        },
        "quoted_prior_verdicts": {
            "v1": {
                "source": portable_relative_path(V1_SUMMARY_PATH, root=REPOSITORY_ROOT),
                "decision_verbatim": str(v1_summary["verdict"]["decision"]),
                "delta_r2_verbatim": float(v1_summary["verdict"]["delta_r2"]),
                "placebo_verbatim": v1_summary["placebo"],
                "note": "kept verbatim; never rewritten by v3",
            },
            "v2": {
                "source": portable_relative_path(V2_SUMMARY_PATH, root=REPOSITORY_ROOT),
                "decision_verbatim": str(v2_summary["verdict"]["decision"]),
                "delta_r2_verbatim": float(v2_summary["verdict"]["delta_r2"]),
                "collapse_verbatim": v2_summary["collapse"],
                "note": "kept verbatim; never rewritten by v3",
            },
        },
        "protocol": {
            "scoreboard": "the frozen main scoreboard, 457 rows / 97 compounds",
            "splitter": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            "model": "XGBRegressor with the frozen v1.0 hyper-parameters, n_jobs=1",
            "hybrid": f"{HYBRID} = 0.5 * (Morgan + Physical), the frozen blend",
            "arms": list(ARM_ORDER),
            "fitted_arms": list(FITTED_ARMS),
            "floor_arms": list(FLOOR_ARMS),
            "shots": SHOTS_THIS_RUN,
            "placebo_clause": "reused verbatim from v2, on the MERGED pipeline",
        },
        "inputs": {
            "coordination_features": portable_relative_path(
                COORDINATION_FEATURES, root=REPOSITORY_ROOT
            ),
            "coordination_features_sha256": sha256_of(COORDINATION_FEATURES),
            "conformer_dipole_features": portable_relative_path(
                CONFORMER_FEATURES, root=REPOSITORY_ROOT
            ),
            "conformer_dipole_features_sha256": sha256_of(CONFORMER_FEATURES),
            "migration_summary": portable_relative_path(
                MIGRATION_SUMMARY_PATH, root=REPOSITORY_ROOT
            ),
            "migration_summary_sha256": sha256_of(MIGRATION_SUMMARY_PATH),
            "v1_summary_sha256": sha256_of(V1_SUMMARY_PATH),
            "v2_summary_sha256": sha256_of(V2_SUMMARY_PATH),
            "v2_prereg_sha256": sha256_of(V2_PREREG_PATH),
            "scoreboard_code": portable_relative_path(
                REPOSITORY_ROOT / "probes" / "dielectric_coordination_block.py", root=REPOSITORY_ROOT
            ),
            "rule": "both blocks are read byte identical from their frozen artefacts; no xTB runs here",
            "frozen_red_lines_untouched": prereg["frozen_red_lines_untouched"],
            "v1_and_v2_artefact_digests_observed_at_lock_time": prereg["v1_and_v2_are_not_edited"][
                "v1_and_v2_artefact_digests_observed_at_lock_time"
            ],
        },
        "scoreboard": scoreboard["contract"],
        "coordination_block": dict(block_report) | {
            "columns": list(v1.COORDINATION_COLUMNS),
            "feature_table": portable_relative_path(COORDINATION_FEATURES, root=REPOSITORY_ROOT),
            "published_delta_r2": LEVER8_PUBLISHED_DELTA,
            "published_r2": LEVER8_PUBLISHED_R2,
            "xtb_executed_here": False,
        },
        "lever4_block": dict(lever4_report) | {
            "columns": list(migration.MIGRATED_COLUMNS),
            "feature_table": portable_relative_path(CONFORMER_FEATURES, root=REPOSITORY_ROOT),
            "scored_compounds_migrated": int(lever4_report["scored_compounds_migrated"]),
            "scored_compounds_total": int(lever4_report["scored_compounds_total"]),
            "published_delta_r2": LEVER4_PUBLISHED_DELTA,
            "published_r2": LEVER4_PUBLISHED_R2,
            "xtb_executed_here": False,
        },
        "shuffled_vector": {
            "seed": SEED,
            "permutation_sha256": hashlib.sha256(
                ",".join(
                    f"{float(value):.12g}" for value in np.asarray(shuffled, dtype=float)
                ).encode("utf-8")
            ).hexdigest(),
            "reuse_note": (
                "the identical vector carries the placebo and both contrast arms and the floor; "
                "none of them gets its own draw"
            ),
            "real_baseline_r2": baseline_r2,
        },
        "arms": arms,
        "floors": {arm: floors[arm]["summary"] for arm in FLOOR_ARMS},
        "collapse": collapse,
        "collapse_arms": {
            "placebo_r2": float(arms[ARM_PLACEBO][HYBRID]["r2"]["mean"]),  # type: ignore[index]
            "floor_r2": float(arms[ARM_FLOOR][HYBRID]["r2"]["mean"]),  # type: ignore[index]
            "placebo_baseline_features_r2": float(
                arms[ARM_CONTRAST_BASELINE][HYBRID]["r2"]["mean"]  # type: ignore[index]
            ),
            "merged_real_r2": both_r2,
        },
        "merge_readings": merge,
        "reproduction_checks": {
            "tolerance": REPRODUCTION_TOLERANCE,
            "baseline": {
                "published": BASELINE_R2,
                "observed": baseline_r2,
                "abs_delta": abs(baseline_r2 - BASELINE_R2),
            },
            "plus_lever4_vs_migration_publication": {
                "published": LEVER4_PUBLISHED_R2,
                "observed": lever4_r2,
                "abs_delta": abs(lever4_r2 - LEVER4_PUBLISHED_R2),
                "source": portable_relative_path(MIGRATION_SUMMARY_PATH, root=REPOSITORY_ROOT),
            },
            "plus_lever8_vs_v2_publication": {
                "published": LEVER8_PUBLISHED_R2,
                "observed": lever8_r2,
                "abs_delta": abs(lever8_r2 - LEVER8_PUBLISHED_R2),
                "source": portable_relative_path(V2_SUMMARY_PATH, root=REPOSITORY_ROOT),
            },
            "note": (
                "only the baseline reproduction is a gate; the single-lever checks are cross-checks "
                "against their own published runs"
            ),
        },
        "paired_deltas": deltas,
        "verdict": verdict,
        "shots": {
            "this_shot": SHOTS_THIS_RUN,
            "lever_4_shots_before": SHOTS_LEVER4_BEFORE,
            "lever_8_shots_before": SHOTS_LEVER8_BEFORE,
            "programme_total_after_this_run": (
                SHOTS_THIS_RUN + SHOTS_LEVER4_BEFORE + SHOTS_LEVER8_BEFORE
            ),
            "policy": "every scored attempt at the main scoreboard is counted, including failed ones",
            "must_be_registered_in": "reports/decisions_log.md section 12, by the integrator",
            "this_probe_does_not_edit_it": (
                "this probe may not edit decisions_log.md, so the count is carried here for the "
                "integrator to register"
            ),
        },
        "honest_boundaries": _honest_boundaries(collapse=collapse),
    }
# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="W17-6: lever 4 and lever 8 merged.")
    parser.add_argument("--jobs", type=int, default=v1.default_jobs())
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def dipole_map_from_conformer_rows(
    conformer_rows: Sequence[Mapping[str, object]],
) -> dict[str, float]:
    """The v0.4 conformer-averaged dipole per compound, read from the frozen artefact."""

    dipole_map: dict[str, float] = {}
    for row in conformer_rows:
        if str(row.get("status")) != "ok":
            continue
        text = str(row.get("dipole_D_conformer_mean", "")).strip()
        if not text:
            continue
        dipole_map[str(row["inchikey"])] = float(text)
    return dipole_map


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        return check_artifacts()
    for path in (PREREG_PATH, COORDINATION_FEATURES, CONFORMER_FEATURES, MIGRATION_SUMMARY_PATH):
        if not path.is_file():
            print("MISSING " + str(path))
            return 1
    jobs = max(1, int(args.jobs))
    started = time.perf_counter()
    started_utc = _utc_now()

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the rebuilt scoreboard does not match the pre-registration")
        return 1
    print(
        "scoreboard: rows={scored_rows} compounds={compounds_scored} folds={folds}".format(**contract)
    )

    coordination_rows = read_csv_rows(COORDINATION_FEATURES)
    matrix, block_report = v1.coordination_matrix(scoreboard["rows"], coordination_rows)
    block_ok = len([row for row in coordination_rows if str(row.get("status")) == "ok"])
    block_report = dict(block_report) | {
        "compounds_requested": len(coordination_rows),
        "compounds_ok": block_ok,
        "compounds_failed": len(coordination_rows) - block_ok,
    }
    print(f"coordination block: ok={block_ok}/{len(coordination_rows)} xtb=not run")

    conformer_rows = read_csv_rows(CONFORMER_FEATURES)
    dipole_map = dipole_map_from_conformer_rows(conformer_rows)
    physical_v04, lever4_raw = migration.build_physical_matrix_v04(
        scoreboard["rows"], dipole_map=dipole_map
    )
    scored_keys = {
        str(key)
        for key, flag in zip(scoreboard["groups"], scoreboard["scored"], strict=True)
        if flag
    }
    lever4_report = dict(lever4_raw) | {
        "scored_compounds_migrated": len(scored_keys & set(dipole_map)),
        "scored_compounds_total": len(scored_keys),
    }
    print(
        "lever 4 block: migrated_rows={migrated_rows} migrated_compounds={migrated_compounds}"
        " scored={scored_compounds_migrated}/{scored_compounds_total} xtb=not run".format(
            **lever4_report
        )
    )

    morgan = scoreboard["morgan"]
    physical = scoreboard["physical"]
    target = scoreboard["target"]
    temperatures = scoreboard["temperatures"]
    groups = scoreboard["groups"]
    scored = scoreboard["scored"]
    splits = scoreboard["splits"]
    assert isinstance(morgan, np.ndarray)
    assert isinstance(physical, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(temperatures, np.ndarray)
    assert isinstance(scored, np.ndarray)

    with_lever8 = np.hstack([physical, matrix])
    with_both = np.hstack([physical_v04, matrix])
    shuffled = v1.shuffled_target(target, scored)
    features_by_arm = {
        ARM_BASELINE: physical,
        ARM_PLUS_LEVER4: physical_v04,
        ARM_PLUS_LEVER8: with_lever8,
        ARM_PLUS_BOTH: with_both,
        ARM_PLACEBO: with_both,
        ARM_CONTRAST_BASELINE: physical,
        ARM_CONTRAST_LEVER4: physical_v04,
    }
    targets = {
        ARM_BASELINE: target,
        ARM_PLUS_LEVER4: target,
        ARM_PLUS_LEVER8: target,
        ARM_PLUS_BOTH: target,
        ARM_PLACEBO: shuffled,
        ARM_CONTRAST_BASELINE: shuffled,
        ARM_CONTRAST_LEVER4: shuffled,
    }
    fitted: dict[str, Mapping[str, object]] = {}
    arm_seconds: dict[str, float] = {}
    for arm in FITTED_ARMS:
        print("arm: " + arm, flush=True)
        clock = time.perf_counter()
        fitted[arm] = v1.evaluate_arm(
            arm,
            morgan=morgan,
            physical=features_by_arm[arm],
            target=targets[arm],
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        arm_seconds[arm] = time.perf_counter() - clock
    floors: dict[str, Mapping[str, object]] = {}
    for arm, labels in ((ARM_FLOOR, shuffled), (ARM_FLOOR_REAL, target)):
        print("arm: " + arm, flush=True)
        clock = time.perf_counter()
        floors[arm] = fold_mean_floor(
            arm,
            target=labels,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
        )
        arm_seconds[arm] = time.perf_counter() - clock

    telemetry = {
        "started_at_utc": started_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "fitted_arms": len(FITTED_ARMS),
        "folds_per_arm": int(contract["folds"]),
        "arm_seconds": arm_seconds,
        "python": platform.python_version(),
        "platform": sys.platform,
        "xtb_executed_here": False,
    }
    summary = build_summary(
        scoreboard=scoreboard,
        block_report=block_report,
        lever4_report=lever4_report,
        fitted=fitted,
        floors=floors,
        shuffled=shuffled,
        telemetry=telemetry,
    )
    summary["outputs"] = {
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        "folds": portable_relative_path(
            ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), root=REPOSITORY_ROOT
        ),
        "repeats": portable_relative_path(
            ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), root=REPOSITORY_ROOT
        ),
        "predictions": portable_relative_path(
            ARTIFACTS_DIR / (ARTIFACT_STEM + "_predictions.csv"), root=REPOSITORY_ROOT
        ),
    }
    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    for arm in ARM_ORDER:
        source = fitted[arm] if arm in fitted else floors[arm]
        fold_rows.extend(source["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(source["repeat_rows"])  # type: ignore[arg-type]
        prediction_rows.extend(source["prediction_rows"])  # type: ignore[arg-type]
    v1.write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), FOLD_COLUMNS, fold_rows)
    v1.write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), REPEAT_COLUMNS, repeat_rows)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_predictions.csv"), PREDICTION_COLUMNS, prediction_rows
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    REPORT_PATH.write_text("\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n")

    verdict = summary["verdict"]
    collapse = summary["collapse"]
    merge = summary["merge_readings"]
    print()
    print(
        f"baseline {verdict['baseline_r2']:.16f} vs published {verdict['baseline_r2_published']:.16f}"
        f" (abs delta {verdict['baseline_abs_delta']:.2e})"
    )
    for arm in ARM_ORDER:
        block_arm = summary["arms"][arm]
        hybrid = block_arm[HYBRID] if HYBRID in block_arm else next(iter(block_arm.values()))
        print(f"{arm:<34s} R2 {hybrid['r2']['mean']:+.4f}")
    print(f"delta R2 (plus_both - baseline) : {verdict['delta_r2']:+.6f}  bar +{verdict['pass_bar']:.4f}")
    print(f"delta (plus_lever4 - baseline)  : {merge['single_arm_deltas'][ARM_PLUS_LEVER4]:+.6f}")
    print(f"delta (plus_lever8 - baseline)  : {merge['single_arm_deltas'][ARM_PLUS_LEVER8]:+.6f}")
    print(f"merge vs best single arm        : {merge['delta_vs_best_single']:+.6f}")
    print(f"refused naive sum of singles    : {merge['naive_sum_of_singles']:+.6f}")
    print(f"floor on the shuffled labels    : {collapse['placebo_floor_r2']:+.6f}")
    print(f"placebo over the floor          : {collapse['over_the_floor']:+.6f}")
    print(f"placebo within the pipeline     : {collapse['within_pipeline_delta_r2']:+.6f}")
    print(f"placebo collapsed               : {verdict['placebo_collapsed']}")
    print(f"decision                        : {verdict['decision']}")
    print(f"wall seconds                    : {telemetry['wall_seconds']:.1f}")
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())