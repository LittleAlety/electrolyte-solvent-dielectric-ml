"""Lever 8, second shot: the Li+ coordination block under an amended placebo clause.

The first shot (``probes/dielectric_coordination_block.py``) met its pass bar
(+0.0441 against a bar of +0.0200) and was then killed by its own placebo
clause, which reads ``|delta R2| <= 0.0200`` against the real-label baseline
arm. That inequality can only hold when the shuffled-label arm KEEPS the
baseline's signal, so it is unsatisfiable whenever the placebo behaves as a
placebo. The defect is constructive, not a reading of our numbers.

Lever 2 (``probes/dielectric_association_features_probe.py``) and lever 9
(``probes/dielectric_knowledge_purity_sweep.py``) already read the same clause
against a no-information floor: the training-fold mean on the identical
permuted labels. This module adopts that form verbatim, writes it down in
``probes/dielectric_coordination_block_prereg_v2.json`` BEFORE the run, and
re-scores the identical frozen scoreboard with the identical frozen block.

What this module does NOT do:

* it does not edit v1 or any v1 artefact. The v1 decision is ``dead`` and stays
  ``dead``; the v2 verdict is reported beside it, never on top of it;
* it does not relax anything. The amended clause is one-sided, uses the same
  +0.0200 as every sibling, and is gated on all three readings at once;
* it does not run xTB. The block is read byte identical from the v1 feature
  artefact, so no new chemistry enters and the feature side is frozen;
* it does not decide the merge arm. Whether the block is carried into a merge
  arm is the integrator's ruling.

The protocols below are the frozen ones, restated from the code that defines
them and never from memory:

    scoreboard : 457 rows / 97 compounds, GroupKFold by InChIKey, 5 folds x 10
                 repeats, seed 42, XGBRegressor with the frozen hyper-parameters
    baseline   : must reproduce 0.4091179943351143 to within 1e-9, or the whole
                 shot is stamped `unverified` and no delta may be quoted
    pass       : delta R2 >= +0.0200 against the re-run baseline AND the amended
                 placebo clause collapsed -> pass_under_amended_placebo_clause
    kill       : delta R2 < +0.0050, or a failed baseline, or a clause that does
                 not hold -> dead, reported as dead
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coordination_block as v1
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES, summarize_repeats
from dielectric_representation_ablation import SEED, evaluate_repeat
from dielectric_room_window_paired import HYBRID

from electrolyte_ml.pathing import portable_relative_path

TASK_ID = "week14_lever8_coordination_block_placebo_clause_v2"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_prereg_v2.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v2_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_coordination_block_v2.md"

ARTIFACT_STEM = "dielectric_coordination_block_v2"
V1_ARTIFACT_STEM = "dielectric_coordination_block"
V1_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / (V1_ARTIFACT_STEM + "_summary.json")
COORDINATION_FEATURES = ARTIFACTS_DIR / (V1_ARTIFACT_STEM + "_features.csv")

ARM_BASELINE = "baseline"
ARM_PLUS = "plus_coordination_block"
ARM_PLACEBO = "placebo_shuffled_target"
ARM_PLACEBO_BASELINE = "baseline_features_shuffled_target"
ARM_FLOOR = "no_information_floor"
ARM_FLOOR_REAL = "no_information_floor_real_labels"

#: Arms that fit the frozen model. The baseline is the reference, not a shot.
FITTED_ARMS = (ARM_BASELINE, ARM_PLUS, ARM_PLACEBO, ARM_PLACEBO_BASELINE)
#: Arms that fit nothing at all: the training-fold mean on the same folds.
FLOOR_ARMS = (ARM_FLOOR, ARM_FLOOR_REAL)
ARM_ORDER = (*FITTED_ARMS, *FLOOR_ARMS)

ROLE = {
    ARM_BASELINE: "reference (real labels, frozen v03 physical + Morgan)",
    ARM_PLUS: "the shot (the five coordination columns appended, real labels)",
    ARM_PLACEBO: "placebo (the same block pipeline, shuffled labels)",
    ARM_PLACEBO_BASELINE: "contrast (frozen feature set, the SAME shuffled labels)",
    ARM_FLOOR: "no-information floor (training-fold mean, the SAME shuffled labels)",
    ARM_FLOOR_REAL: "no-information floor on the real labels (context)",
}

BASELINE_R2 = 0.4091179943351143
REPRODUCTION_TOLERANCE = 1e-09
PASS_DELTA = 0.0200
KILL_DELTA = 0.0050
PLACEBO_TOLERANCE = 0.0200
SHOTS_THIS_RUN = 1
SHOTS_V1 = 1

FOLD_COLUMNS = v1.FOLD_COLUMNS_OUT
REPEAT_COLUMNS = v1.REPEAT_COLUMNS_OUT
PREDICTION_COLUMNS = v1.PREDICTION_COLUMNS_OUT

DECISION_VOCABULARY = ("pass_under_amended_placebo_clause", "sub_threshold", "dead", "unverified")


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
# the no-information floor
# --------------------------------------------------------------------------- #


def fold_mean_floor(
    name: str,
    *,
    target: np.ndarray,
    temperatures: np.ndarray,
    groups: Sequence[str],
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> dict[str, object]:
    """The no-information floor: the training-fold mean, on the identical folds.

    Lever 2 established that a shuffled-label arm cannot be measured against a
    real-label baseline - it is unsatisfiable by construction - so the collapse
    reading is taken against this floor. It is computed on whatever label vector
    the caller passes, so the floor for the placebo arm and the placebo arm
    itself sit on the identical permuted labels.
    """

    labels = np.asarray(target, dtype=float)
    group_array = np.asarray([str(item) for item in groups])
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    buckets: dict[int, dict[str, list[np.ndarray]]] = {}
    for repeat, fold, train_index, test_index in splits:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        prediction = np.full(test.size, float(np.mean(labels[train])))
        metrics = evaluate_repeat(labels[test], prediction)
        fold_rows.append(
            {
                "arm": name,
                "representation": HYBRID,
                "repeat": int(repeat),
                "fold": int(fold),
                "train_rows": int(train.size),
                "test_rows": int(test.size),
                "train_compounds": int(np.unique(group_array[train]).size),
                "test_compounds": int(np.unique(group_array[test]).size),
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "r2": metrics["r2"],
                "spearman": metrics["spearman"],
            }
        )
        bucket = buckets.setdefault(int(repeat), {"target": [], "prediction": []})
        bucket["target"].append(labels[test])
        bucket["prediction"].append(prediction)
        for row_index, value in zip(test_index, prediction.tolist(), strict=True):
            prediction_rows.append(
                {
                    "arm": name,
                    "representation": HYBRID,
                    "repeat": int(repeat),
                    "fold": int(fold),
                    "inchikey": str(groups[int(row_index)]),
                    "T_K": float(temperatures[int(row_index)]),
                    "target": float(labels[int(row_index)]),
                    "prediction": float(value),
                }
            )
    repeat_rows: list[dict[str, object]] = []
    for repeat, bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(
            np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"])
        )
        repeat_rows.append(
            {
                "arm": name,
                "representation": HYBRID,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    grouped = summarize_repeats([{**row, "protocol": name} for row in repeat_rows])
    summary = grouped.get(name)
    if summary is None or HYBRID not in summary:
        raise ValueError(f"{name}: the floor arm table is incomplete")
    return {
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# the amended placebo clause
# --------------------------------------------------------------------------- #


def placebo_collapse_readout(
    *,
    placebo_r2: float,
    placebo_floor_r2: float,
    same_block_real_r2: float,
    placebo_baseline_features_r2: float,
    real_baseline_r2: float,
) -> dict[str, object]:
    """The amended clause, evaluated on three readings at once.

    rule 1 (sibling precedent, lever 2 / lever 9): the shuffled-label arm must
    not beat its own no-information floor by more than +0.0200.
    rule 2 (the sentence as written): the block pipeline on shuffled labels must
    not manufacture a gain of more than +0.0200 against the same pipeline's
    real-label arm.
    rule 3 (the reading that catches leakage, lever 9): the block pipeline on
    shuffled labels must not beat the frozen feature set on the SAME shuffled
    labels by more than +0.0200.

    `collapsed` requires all three. Every rule uses the same +0.0200; nothing is
    widened, and the two readings that are easy to satisfy cannot be traded
    against the one that is not.
    """

    over_the_floor = float(placebo_r2) - float(placebo_floor_r2)
    against_the_real_arm = float(placebo_r2) - float(same_block_real_r2)
    within_pipeline = float(placebo_r2) - float(placebo_baseline_features_r2)
    floor_holds = over_the_floor <= PLACEBO_TOLERANCE
    real_arm_holds = against_the_real_arm <= PLACEBO_TOLERANCE
    within_holds = within_pipeline <= PLACEBO_TOLERANCE
    return {
        "tolerance": PLACEBO_TOLERANCE,
        "placebo_r2": float(placebo_r2),
        "placebo_floor_r2": float(placebo_floor_r2),
        "placebo_floor_definition": (
            "the training-fold-mean predictor scored on the identical folds and the identical "
            "permuted label vector as the shuffled-label arm"
        ),
        "over_the_floor": over_the_floor,
        "floor_rule_holds": bool(floor_holds),
        "same_pipeline_real_arm_r2": float(same_block_real_r2),
        "delta_vs_the_same_pipeline_real_arm": against_the_real_arm,
        "real_arm_rule_holds": bool(real_arm_holds),
        "placebo_baseline_features_r2": float(placebo_baseline_features_r2),
        "within_pipeline_delta_r2": within_pipeline,
        "within_pipeline_rule_holds": bool(within_holds),
        "collapsed": bool(floor_holds and real_arm_holds and within_holds),
        "delta_vs_the_real_label_baseline": float(placebo_r2) - float(real_baseline_r2),
        "real_label_baseline_r2": float(real_baseline_r2),
        "wording_note": (
            "the superseded v1 clause named no reference; measured against the real-label baseline "
            "it is unsatisfiable by construction. This clause names its reference explicitly, is "
            "one-sided, and gates on all three readings."
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
    """Apply the v2 criteria in the order the pre-registration froze them."""

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
            "the amended placebo clause did not hold "
            f"(over the floor {float(collapse['over_the_floor']):+.4f}, against the same pipeline on "
            f"real labels {float(collapse['delta_vs_the_same_pipeline_real_arm']):+.4f}, within the "
            f"pipeline {float(collapse['within_pipeline_delta_r2']):+.4f})"
        )
    elif float(delta_r2) >= PASS_DELTA:
        decision = "pass_under_amended_placebo_clause"
        reasons.append(
            f"the block moved grouped {HYBRID} R2 by {float(delta_r2):+.4f} against the re-run "
            f"baseline and the amended placebo clause collapsed; the block arm beat the baseline in "
            f"{positive_repeats} of {repeats_total} repeats. The v1 decision remains `dead` and this "
            "is a second, separately counted shot."
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
                "rule 1 floor upper bound AND rule 2 same-pipeline real-label arm AND rule 3 "
                "within-pipeline shuffled contrast, all at +0.0200"
            ),
        },
        "v1_decision_is_still_in_force": "dead",
        "not_a_gate_but_reported": "mae_gt60, MAE, RMSE and Spearman deltas",
    }

# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #


def _r2_of(summary: Mapping[str, object], arm: str) -> float:
    return float(summary["arms"][arm][HYBRID]["r2"]["mean"])  # type: ignore[index]


def format_report(summary: Mapping[str, object]) -> list[str]:
    """Render the report from the summary; the md on disk is this text."""

    verdict = summary["verdict"]  # type: ignore[index]
    arms = summary["arms"]  # type: ignore[index]
    collapse = summary["collapse"]  # type: ignore[index]
    deltas = summary["paired_deltas"]  # type: ignore[index]
    scoreboard = summary["scoreboard"]  # type: ignore[index]
    clause = summary["superseded_clause"]  # type: ignore[index]
    shuffled = summary["shuffled_vector"]  # type: ignore[index]
    shots = summary["shots"]  # type: ignore[index]
    lines: list[str] = []
    lines.append("# Lever 8, second shot - the Li+ coordination block under an amended placebo clause")
    lines.append("")
    lines.append(f"- generated: `{summary['generated_at_utc']}`")
    lines.append(
        f"- pre-registration (v2): `{summary['preregistration']['path']}`"  # type: ignore[index]
        f" (sha256 `{summary['preregistration']['sha256']}`,"  # type: ignore[index]
        f" locked {summary['preregistration']['locked_at_utc']})"  # type: ignore[index]
    )
    lines.append(f"- decision: **{verdict['decision']}**")  # type: ignore[index]
    lines.append("")
    for reason in verdict["reasons"]:  # type: ignore[index]
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## Read this beside v1, never on top of it")
    lines.append("")
    lines.append(
        "- v1 (`probes/dielectric_coordination_block_summary.json`) recorded **dead** and still "
        "records **dead**. Its pre-registration and every one of its artefacts are byte identical; "
        "the digests taken at lock time are in the v2 pre-registration."
    )
    lines.append(
        f"- the superseded clause `{clause['secondary_criterion']}` names no reference, and against "
        "the real-label baseline it is unsatisfiable whenever the placebo behaves as a placebo. "
        "That is a defect of the sentence, not a reading of our numbers."
    )
    lines.append(
        "- this shot is a **new, separately counted** attempt under an explicitly amended clause, "
        "written before the run and identical in form to lever 2 and lever 9."
    )
    lines.append(
        "- the amendment exists to repair a broken sentence, **not to rescue lever 8**. Gating on "
        "all three readings at once is at least as strict as either sibling."
    )
    lines.append(
        f"- whether the block is carried into a merge arm is **not decided here**: "
        f"{summary['merge_arm']}"
    )
    lines.append("")
    lines.append("## Scoreboard")
    lines.append("")
    lines.append(
        f"- scored rows {scoreboard['scored_rows']}, compounds {scoreboard['compounds_scored']},"
        f" folds {scoreboard['folds']}, repeats {scoreboard['executed_repeats']}"
    )
    lines.append(
        f"- straddling compounds across a fold boundary:"
        f" {scoreboard['folds_with_a_straddling_compound']}"
    )
    lines.append(
        f"- shuffled label vector: seed {shuffled['seed']}, sha256 `{shuffled['permutation_sha256']}`"
        " - reused from v1, not redrawn"
    )
    lines.append(
        f"- coordination block: {summary['coordination_block']['compounds_ok']} compounds with a"
        " usable block, read byte identical from the v1 feature artefact"
    )
    lines.append("- xTB executed by this shot: **no** (the block is frozen, so there is no cost)")
    lines.append("")
    lines.append("## Arms")
    lines.append("")
    lines.append("| arm | role | R2 | MAE | Spearman | MAE >60 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for arm in ARM_ORDER:
        block_arm = arms[arm]  # type: ignore[index]
        hybrid = block_arm[HYBRID] if HYBRID in block_arm else next(iter(block_arm.values()))
        lines.append(
            f"| `{arm}` | {ROLE[arm]} | {hybrid['r2']['mean']:.4f} | {hybrid['mae']['mean']:.4f}"
            f" | {hybrid['spearman']['mean']:.4f} | {hybrid['mae_gt60']['mean']:.4f} |"
        )
    lines.append("")
    lines.append("## Amended placebo clause (all three readings must hold)")
    lines.append("")
    lines.append(
        f"- rule 1, floor upper bound: placebo {collapse['placebo_r2']:+.4f} minus floor"
        f" {collapse['placebo_floor_r2']:+.4f} = {collapse['over_the_floor']:+.4f}"
        f" -> holds: {collapse['floor_rule_holds']}"
    )
    lines.append(
        f"- rule 2, the same pipeline on real labels: placebo minus the block arm"
        f" = {collapse['delta_vs_the_same_pipeline_real_arm']:+.4f}"
        f" -> holds: {collapse['real_arm_rule_holds']}"
    )
    lines.append(
        f"- rule 3, within-pipeline shuffled contrast: placebo minus the frozen feature set on the"
        f" SAME shuffled labels = {collapse['within_pipeline_delta_r2']:+.4f}"
        f" -> holds: {collapse['within_pipeline_rule_holds']}"
    )
    lines.append(
        f"- tolerance for every rule: {collapse['tolerance']}; **collapsed:"
        f" {collapse['collapsed']}**"
    )
    lines.append(f"- floor definition: {collapse['placebo_floor_definition']}")
    lines.append(f"- note: {collapse['wording_note']}")
    lines.append("")
    lines.append("## Paired deltas (plus_coordination_block - baseline)")
    lines.append("")
    lines.append("| metric | delta |")
    lines.append("| --- | --- |")
    for metric in ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60"):
        lines.append(f"| {metric} | {deltas[metric]:+.4f} |")
    lines.append("")
    lines.append(
        f"- baseline reproduction: {verdict['baseline_r2']:.16f} vs published"
        f" {verdict['baseline_r2_published']:.16f} (abs delta"
        f" {verdict['baseline_abs_delta']:.2e})"
    )
    lines.append(
        f"- mae_gt60 delta {verdict['mae_gt60_delta']:+.4f} (not a gate in v2, reported)"
    )
    lines.append("")
    lines.append("## v1 and v2 side by side")
    lines.append("")
    lines.append("| | v1 | v2 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| decision | `dead` (unchanged) | `{verdict['decision']}` |")
    lines.append(
        "| placebo reference | the real-label baseline, absolute distance | the no-information"
        " floor on the identical permuted labels |"
    )
    lines.append(
        f"| block delta R2 | {summary['v1_comparison']['v1_delta_r2']:+.4f}"
        f" | {verdict['delta_r2']:+.4f} |"
    )
    lines.append(
        f"| placebo R2 | {summary['v1_comparison']['v1_placebo_reading']['r2']:+.4f}"
        f" | {collapse['placebo_r2']:+.4f} |"
    )
    lines.append("| shots | 1 | 1 (lever 8 total 2) |")
    lines.append("")
    lines.append("## Honest boundaries")
    lines.append("")
    for boundary in summary["honest_boundaries"]:  # type: ignore[index]
        lines.append(f"- {boundary}")
    lines.append("")
    lines.append("## Shots")
    lines.append("")
    lines.append(f"- this shot: {shots['this_shot']}")
    lines.append(f"- v1 shot: {shots['v1_shot']}")
    lines.append(f"- lever 8 total after this run: {shots['lever8_total_after_this_run']}")
    lines.append(f"- policy: {shots['policy']}")
    lines.append(f"- {shots['this_probe_does_not_edit_it']}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for name, path in sorted(summary["outputs"].items()):  # type: ignore[index]
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return lines

# --------------------------------------------------------------------------- #
# self-check
# --------------------------------------------------------------------------- #


def check_artifacts() -> int:
    """Re-derive the released v2 numbers from the artefacts on disk."""

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
        problems.append("the v2 pre-registration is not the one recorded in the summary")
    for relative, digest in prereg["v1_is_not_edited"][
        "v1_artefact_digests_observed_at_lock_time"
    ].items():
        if sha256_of(REPOSITORY_ROOT / relative) != digest:
            problems.append(f"a v1 artefact moved: {relative}")
    for entry in prereg["frozen_red_lines_untouched"]:
        relative, _, digest = entry.partition(" digest ")
        if not digest or sha256_of(REPOSITORY_ROOT / relative) != digest:
            problems.append(f"a frozen red line moved: {relative}")
    arms = summary["arms"]
    baseline = float(arms[ARM_BASELINE][HYBRID]["r2"]["mean"])
    if abs(baseline - BASELINE_R2) > REPRODUCTION_TOLERANCE:
        problems.append("the recorded baseline is not the published R2")
    delta = float(arms[ARM_PLUS][HYBRID]["r2"]["mean"]) - baseline
    if abs(delta - float(summary["verdict"]["delta_r2"])) > 1e-12:
        problems.append("the recorded verdict delta disagrees with the arm table")
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
    report = REPORT_PATH.read_text(encoding="utf-8").splitlines()
    if report != format_report(summary):
        problems.append("reports/dielectric_coordination_block_v2.md is not format_report(summary)")
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


def _honest_boundaries(collapse: Mapping[str, object]) -> list[str]:
    return [
        (
            "the v1 decision is `dead` and remains `dead`. This shot is a second, separately "
            "counted attempt under an explicitly amended clause; it does not overturn v1 and must "
            "never be quoted as if it had."
        ),
        (
            "the amended clause exists because the v1 sentence named no reference and is "
            "unsatisfiable by construction against a real-label baseline. The amendment was written "
            "before this run and is identical in form to lever 2 and lever 9, not tuned to this "
            "lever's numbers."
        ),
        (
            "all three clause readings are gated at once at the same +0.0200. Two of them are easy "
            "to satisfy; the third, the within-pipeline contrast against the frozen feature set on "
            "the identical shuffled labels, is the one that would catch a block that still lifts on "
            "random labels."
        ),
        (
            "target mismatch: the source review describes solvating power inside an electrolyte, "
            "while this scoreboard predicts the static dielectric constant of a pure solvent. The "
            "block tests which of the review's axes transfers to a different target."
        ),
        (
            "no xTB ran in this shot. The coordination block is read byte identical from the v1 "
            "feature artefact, so the feature side is frozen by construction and no cost was "
            "incurred."
        ),
        (
            "GFN2-xTB overbinds Li+; only the spread of the binding energy across compounds is "
            "used, never its absolute value as thermochemistry."
        ),
        (
            "the Li+ complex is gas phase and single molecule: no anion, no solvent-solvent "
            "competition - the weakness the review itself states for the binding-energy descriptor."
        ),
        (
            "nine compounds have no O and no N, so the pre-registered site rule leaves their block "
            "undefined rather than filled; the frozen model handles the missing cells natively."
        ),
        (
            "the mae_gt60 stratum, MAE, RMSE and Spearman deltas are reported beside the decision, "
            "not gated by it: the v2 pass criterion names only the baseline reproduction, the R2 "
            "delta and the amended placebo clause."
        ),
        (
            f"the placebo arm sits {float(collapse['delta_vs_the_real_label_baseline']):+.4f} below "
            "the real-label baseline. That is the expected sign for shuffled labels and is reported "
            "for completeness only; the v1 clause that made that distance a gate is superseded here, "
            "not deleted."
        ),
    ]


def build_summary(
    *,
    scoreboard: Mapping[str, object],
    block_report: Mapping[str, object],
    fitted: Mapping[str, Mapping[str, object]],
    floors: Mapping[str, Mapping[str, object]],
    shuffled: np.ndarray,
) -> dict[str, object]:
    arms: dict[str, object] = {arm: fitted[arm]["summary"] for arm in FITTED_ARMS}
    for arm in FLOOR_ARMS:
        arms[arm] = floors[arm]["summary"]
    prereg = load_prereg()
    baseline_r2 = float(arms[ARM_BASELINE][HYBRID]["r2"]["mean"])  # type: ignore[index]
    delta_r2 = float(arms[ARM_PLUS][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
    deltas = {
        metric: float(arms[ARM_PLUS][HYBRID][metric]["mean"])  # type: ignore[index]
        - float(arms[ARM_BASELINE][HYBRID][metric]["mean"])  # type: ignore[index]
        for metric in METRIC_NAMES
    }
    collapse = placebo_collapse_readout(
        placebo_r2=float(arms[ARM_PLACEBO][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        placebo_floor_r2=float(arms[ARM_FLOOR][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        same_block_real_r2=float(arms[ARM_PLUS][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        placebo_baseline_features_r2=float(
            arms[ARM_PLACEBO_BASELINE][HYBRID]["r2"]["mean"]  # type: ignore[index]
        ),
        real_baseline_r2=baseline_r2,
    )
    hybrid_rows = [
        row for row in fitted[ARM_PLUS]["repeat_rows"] if str(row["representation"]) == HYBRID
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
    v1_summary = json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))
    feature_rows = read_csv_rows(COORDINATION_FEATURES)
    block_ok = len([row for row in feature_rows if str(row.get("status")) == "ok"])
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "generated_at_utc": _utc_now(),
        "seed": SEED,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_of(PREREG_PATH),
            "locked_at_utc": prereg["locked_at_utc"],
            "supersedes_for_this_shot_only": portable_relative_path(
                REPOSITORY_ROOT / "probes" / (V1_ARTIFACT_STEM + "_prereg.json"),
                root=REPOSITORY_ROOT,
            ),
        },
        "superseded_clause": {
            "secondary_criterion": prereg["superseded_placebo_clause"]["fields_verbatim"][
                "secondary_criterion"
            ],
            "kill_line": prereg["superseded_placebo_clause"]["fields_verbatim"]["kill_line"],
            "kept_verbatim_in": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "defect": prereg["superseded_placebo_clause"]["defect"],
        },
        "protocol": {
            "scoreboard": "the frozen main scoreboard, 457 rows / 97 compounds",
            "splitter": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            "folds": "re-derived by the same frozen call chain as v1; the fold numbers are unchanged",
            "model": "XGBRegressor with the frozen v1.0 hyper-parameters, n_jobs=1",
            "hybrid": f"{HYBRID} = 0.5 * (Morgan + Physical), the frozen blend",
            "arms": list(ARM_ORDER),
            "fitted_arms": list(FITTED_ARMS),
            "floor_arms": list(FLOOR_ARMS),
            "shots": SHOTS_THIS_RUN,
        },
        "inputs": {
            "coordination_features": portable_relative_path(
                COORDINATION_FEATURES, root=REPOSITORY_ROOT
            ),
            "coordination_features_sha256": sha256_of(COORDINATION_FEATURES),
            "coordination_rule": (
                "reused byte identical from the v1 xTB phase; this shot executes no xTB and adds no "
                "new chemistry"
            ),
            "scoreboard_code": portable_relative_path(
                REPOSITORY_ROOT / "probes" / (V1_ARTIFACT_STEM + ".py"), root=REPOSITORY_ROOT
            ),
            "v1_summary": portable_relative_path(V1_SUMMARY_PATH, root=REPOSITORY_ROOT),
            "v1_summary_sha256": sha256_of(V1_SUMMARY_PATH),
            "frozen_red_lines_untouched": prereg["frozen_red_lines_untouched"],
            "v1_artefact_digests_observed_at_lock_time": prereg["v1_is_not_edited"][
                "v1_artefact_digests_observed_at_lock_time"
            ],
        },
        "scoreboard": scoreboard["contract"],
        "coordination_block": dict(block_report) | {
            "columns": list(v1.COORDINATION_COLUMNS),
            "feature_table": portable_relative_path(COORDINATION_FEATURES, root=REPOSITORY_ROOT),
            "compounds_requested": len(feature_rows),
            "compounds_ok": block_ok,
            "compounds_failed": len(feature_rows) - block_ok,
            "xtb_executed_here": False,
        },
        "shuffled_vector": {
            "seed": SEED,
            "permutation_sha256": hashlib.sha256(
                ",".join(f"{float(value):.12g}" for value in np.asarray(shuffled, dtype=float)).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "reuse_note": (
                "the identical vector carries the placebo arm, the contrast arm and the floor; none "
                "of the three gets its own draw"
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
                arms[ARM_PLACEBO_BASELINE][HYBRID]["r2"]["mean"]  # type: ignore[index]
            ),
            "block_real_r2": float(arms[ARM_PLUS][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        },
        "paired_deltas": deltas,
        "verdict": verdict,
        "v1_comparison": {
            "v1_decision": v1_summary["verdict"]["decision"],
            "v1_decision_is_still_in_force": "dead",
            "v1_delta_r2": float(v1_summary["verdict"]["delta_r2"]),
            "v1_placebo_reading": v1_summary["placebo"],
            "difference": (
                "the same block, the same folds and the same shuffled vector; only the reference the "
                "placebo clause is measured against changes, from the real-label baseline to the "
                "no-information floor on the identical permuted labels"
            ),
        },
        "merge_arm": "left to the integrator: this shot neither requests nor pre-empts a merge arm",
        "shots": {
            "this_shot": SHOTS_THIS_RUN,
            "v1_shot": SHOTS_V1,
            "lever8_total_after_this_run": SHOTS_THIS_RUN + SHOTS_V1,
            "policy": (
                "attempts at the main scoreboard are counted in reports/decisions_log.md section 12"
            ),
            "must_be_registered_in": "reports/decisions_log.md section 12, by the integrator",
            "this_probe_does_not_edit_it": (
                "this probe may not edit decisions_log.md, so the count is carried here for the "
                "integrator to register"
            ),
        },
        "honest_boundaries": _honest_boundaries(collapse),
    }

# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lever 8 second shot (amended placebo clause).")
    parser.add_argument("--jobs", type=int, default=v1.default_jobs())
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        return check_artifacts()
    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    if not COORDINATION_FEATURES.is_file():
        print("MISSING " + str(COORDINATION_FEATURES))
        return 1
    jobs = max(1, int(args.jobs))

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the rebuilt scoreboard does not match the pre-registration")
        return 1
    print(
        "scoreboard: rows={scored_rows} compounds={compounds_scored} folds={folds}".format(**contract)
    )

    xtb_rows = read_csv_rows(COORDINATION_FEATURES)
    matrix, block_report = v1.coordination_matrix(scoreboard["rows"], xtb_rows)
    print(
        "coordination block: ok={ok}/{total} xtb=not run".format(
            ok=len([row for row in xtb_rows if row["status"] == "ok"]),
            total=len(xtb_rows),
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

    with_block = np.hstack([physical, matrix])
    shuffled = v1.shuffled_target(target, scored)
    features_by_arm = {
        ARM_BASELINE: physical,
        ARM_PLUS: with_block,
        ARM_PLACEBO: with_block,
        ARM_PLACEBO_BASELINE: physical,
    }
    targets = {
        ARM_BASELINE: target,
        ARM_PLUS: target,
        ARM_PLACEBO: shuffled,
        ARM_PLACEBO_BASELINE: shuffled,
    }
    fitted: dict[str, Mapping[str, object]] = {}
    for arm in FITTED_ARMS:
        print("arm: " + arm, flush=True)
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
    floors: dict[str, Mapping[str, object]] = {}
    for arm, labels in ((ARM_FLOOR, shuffled), (ARM_FLOOR_REAL, target)):
        print("arm: " + arm, flush=True)
        floors[arm] = fold_mean_floor(
            arm,
            target=labels,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
        )

    summary = build_summary(
        scoreboard=scoreboard,
        block_report=block_report,
        fitted=fitted,
        floors=floors,
        shuffled=shuffled,
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
    print()
    print(
        f"baseline {verdict['baseline_r2']:.16f} vs published {verdict['baseline_r2_published']:.16f}"
        f" (abs delta {verdict['baseline_abs_delta']:.2e})"
    )
    for arm in ARM_ORDER:
        block = summary["arms"][arm]
        hybrid = block[HYBRID] if HYBRID in block else next(iter(block.values()))
        print(f"{arm:<34s} R2 {hybrid['r2']['mean']:+.4f}")
    print(f"delta R2 (block - baseline)   : {verdict['delta_r2']:+.6f}  bar +{verdict['pass_bar']:.4f}")
    print(f"floor on the shuffled labels  : {collapse['placebo_floor_r2']:+.6f}")
    print(f"over the floor                : {collapse['over_the_floor']:+.6f}")
    print(f"within-pipeline contrast      : {collapse['within_pipeline_delta_r2']:+.6f}")
    print(f"placebo collapsed             : {verdict['placebo_collapsed']}")
    print(f"decision                      : {verdict['decision']}")
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())