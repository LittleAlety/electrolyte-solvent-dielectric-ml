"""W20-4 (SS28.60): the second-stage P0 fine-tune -- can the epsilon 0.60 gun clear the gate?

W18-P0 (probes/dielectric_hyperparameter_grid.py, shot 18) swept six XGBoost axes on the
frozen Physical(lever4) protocol and its best arm, hp_d4_n200 (200 trees / max_depth 4 at the
frozen regularisation), reached 0.5998203128630835 cross-seed -- 0.00018 short of 0.60.  That
first-stage grid is seven arms x five seeds = 35 readings, and picking its maximum is nearly
certain to "clear 0.60" (the two seed-42 and seed-7 readings are already above it): that is not
a threshold pass, it is a multiple comparison.  W20-4 is the second stage: hold max_depth = 4
and n_estimators in 200-400 and probe min_child_weight / colsample_bytree / max_bin around
W18's winning arm.

Discipline, all fixed before the run in probes/w20_epsilon_second_stage_prereg.json:

* a SINGLE pre-registered arm (REGISTERED_ARM) decides everything;
* the gate is cross-seed mean R2 >= 0.60 AND the five-seed lower bound (the minimum of the five
  per-seed repeat means) > 0.55;
* every other arm of the grid is side information and may not revise the verdict;
* inner-fold tuning (a GroupKFold inside every training fold) is reported as a side arm, so the
  mechanism is on the record without handing the verdict to a per-fold argmax;
* a placebo run permutes the scored targets before fitting.

Nothing on the frozen side moves.  xgb_reference has to reproduce 0.6080587938801277 bit for bit
on seed 42 and the fold assignment has to keep the frozen signature, otherwise the probe refuses
to report anything else.  The frozen headline stays 0.4766400383507876 and the frozen baseline
stays 0.4091179943351143; a promotion is entered on the main-scoreboard ledger but never rewrites
them.

Five seeds run as five processes (one per seed); inside each seed the folds run on a nested
process pool, because the frozen XGBoost head is single-threaded (n_jobs = 1) and threads would
just sit on the GIL.

Run:
    .venv/Scripts/python.exe probes/w20_epsilon_second_stage.py
    .venv/Scripts/python.exe probes/w20_epsilon_second_stage.py --placebo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
)
from dielectric_representation_seed_robustness import build_context, splits_for
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_epsilon_second_stage_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_epsilon_second_stage_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_epsilon_second_stage.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "w20_epsilon_second_stage"
PLACEBO_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "w20_epsilon_second_stage_placebo_summary.json"
)
PLACEBO_REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_epsilon_second_stage_placebo.md"
PLACEBO_ARTIFACT_STEM = "w20_epsilon_second_stage_placebo"

REPRESENTATION = "Physical(lever4)"
SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
PLACEBO_SEED = 2026
INNER_FOLDS = 3
INNER_SEED = 2026
MAX_GRID_ARMS = 24

ARM_REFERENCE = "xgb_reference"
ARM_INNER_CV = "hp2_inner_cv"
REGISTERED_ARM = "hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128"

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
FROZEN_CROSS_SEED_ENDPOINT = 0.5861142332208197
W18_BEST_ARM = "hp_d4_n200_lr0.05_mcw1_ss0.8_cs0.8"
W18_BEST_CROSS_SEED = 0.5998203128630835

PASS_TARGET_R2 = 0.60
FIVE_SEED_LOWER_BOUND_MIN = 0.55
HONEST_EXPECTATION_LOW = 0.01
HONEST_EXPECTATION_HIGH = 0.05
HONEST_EXPECTATION_BASIS = "judgement, not a measurement"

# (name, n_estimators, max_depth, learning_rate, min_child_weight, subsample,
#  colsample_bytree, max_bin, block).  The reference row is the frozen head and must not move.
# Every other arm keeps max_depth = 4 and n_estimators in 200-400 and moves exactly the axes the
# W20-4 charter names (min_child_weight / colsample_bytree / max_bin); one arm is the bridge back
# to W18s winning point so the pipeline can be checked against 0.5998203128630835.
GRID_ARMS = (
    (ARM_REFERENCE, 200, 2, 0.05, 1, 0.8, 0.8, 64, "anchor"),
    ("hp2_d4_n200_lr0.05_mcw1_ss0.8_cs0.8_bin64", 200, 4, 0.05, 1, 0.8, 0.8, 64, "bridge"),
    ("hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin64", 200, 4, 0.05, 5, 0.8, 0.8, 64, "min_child_weight"),
    ("hp2_d4_n200_lr0.05_mcw1_ss0.8_cs0.8_bin128", 200, 4, 0.05, 1, 0.8, 0.8, 128, "max_bin"),
    ("hp2_d4_n200_lr0.05_mcw1_ss0.8_cs1.0_bin64", 200, 4, 0.05, 1, 0.8, 1.0, 64, "colsample"),
    ("hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128", 200, 4, 0.05, 5, 0.8, 0.8, 128, "registered"),
    ("hp2_d4_n300_lr0.05_mcw5_ss0.8_cs0.8_bin128", 300, 4, 0.05, 5, 0.8, 0.8, 128, "capacity_ladder"),
    ("hp2_d4_n400_lr0.05_mcw5_ss0.8_cs0.8_bin128", 400, 4, 0.05, 5, 0.8, 0.8, 128, "capacity_ladder"),
)

FIXED_ARMS = tuple(row[0] for row in GRID_ARMS)
ARM_ORDER = FIXED_ARMS + (ARM_INNER_CV,)
ARM_BLOCKS = {row[0]: str(row[8]) for row in GRID_ARMS}
ARM_BLOCKS[ARM_INNER_CV] = "inner_fold"
ARM_PARAMS = {
    row[0]: {
        **XGB_PARAMS,
        "n_estimators": int(row[1]),
        "max_depth": int(row[2]),
        "learning_rate": float(row[3]),
        "min_child_weight": int(row[4]),
        "subsample": float(row[5]),
        "colsample_bytree": float(row[6]),
        "max_bin": int(row[7]),
    }
    for row in GRID_ARMS
}
INNER_CANDIDATES = tuple(arm for arm in FIXED_ARMS if arm != ARM_REFERENCE)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=0, help="seed processes; 0 = one per seed")
    parser.add_argument("--fold-jobs", type=int, default=3, help="fold processes inside a seed")
    parser.add_argument("--seeds", type=str, default=",".join(str(seed) for seed in SEEDS))
    parser.add_argument("--arms", type=str, default="")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--placebo", action="store_true")
    return parser.parse_args(argv)


def parse_arms(raw: str) -> tuple[str, ...]:
    """Canonical arm order; the frozen reference is always present."""

    requested = [token.strip() for token in str(raw).split(",") if token.strip()]
    if not requested:
        return ARM_ORDER
    unknown = [token for token in requested if token not in ARM_ORDER]
    if unknown:
        raise SystemExit("unknown arm: " + ", ".join(unknown))
    return tuple(arm for arm in ARM_ORDER if arm in requested or arm == ARM_REFERENCE)


def select_arm(
    features: np.ndarray,
    target: np.ndarray,
    groups: np.ndarray,
    seed: int,
) -> str:
    """Best grid arm by a GroupKFold inside the training fold only.

    Nothing here sees the held-out fold, so the arm is honest but still inside the training
    data.  Ties break on the arm name so the choice is deterministic.
    """

    splitter = GroupKFold(n_splits=INNER_FOLDS)
    scores: dict[str, list[float]] = {arm: [] for arm in INNER_CANDIDATES}
    for inner_train, inner_test in splitter.split(features, target, groups=groups):
        if np.asarray(inner_test).size < 2:
            continue
        for arm in INNER_CANDIDATES:
            model = XGBRegressor(**ARM_PARAMS[arm], random_state=seed)
            model.fit(features[inner_train], target[inner_train])
            prediction = np.maximum(
                np.asarray(model.predict(features[inner_test]), dtype=float), 1.0
            )
            scores[arm].append(
                float(evaluate_repeat(target[inner_test], prediction)["r2"])
            )
    ranked = sorted(
        INNER_CANDIDATES,
        key=lambda arm: (-(float(np.mean(scores[arm])) if scores[arm] else 0.0), arm),
    )
    return ranked[0]


_GRID_STATE: dict[str, object] = {}


def _init_grid_worker(
    features: np.ndarray,
    target: np.ndarray,
    arms: Sequence[str],
    groups: np.ndarray,
) -> None:
    _GRID_STATE["features"] = features
    _GRID_STATE["target"] = target
    _GRID_STATE["arms"] = tuple(arms)
    _GRID_STATE["groups"] = groups


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]], str]:
    """One fold: every requested arm, in one worker process."""

    repeat, fold, train_index, test_index = task
    features = _GRID_STATE["features"]
    target = _GRID_STATE["target"]
    arms = _GRID_STATE["arms"]
    groups = _GRID_STATE["groups"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(arms, tuple)
    assert isinstance(groups, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    train_features = features[train]
    test_features = features[test]
    train_target = target[train]
    predictions: dict[str, list[float]] = {}
    for arm in arms:
        if arm == ARM_INNER_CV:
            continue
        model = XGBRegressor(**ARM_PARAMS[arm], random_state=SEED)
        model.fit(train_features, train_target)
        raw = np.asarray(model.predict(test_features), dtype=float)
        predictions[arm] = [float(value) for value in np.maximum(raw, 1.0)]
    chosen = ""
    if ARM_INNER_CV in arms:
        chosen = select_arm(train_features, train_target, groups[train], INNER_SEED)
        model = XGBRegressor(**ARM_PARAMS[chosen], random_state=SEED)
        model.fit(train_features, train_target)
        raw = np.asarray(model.predict(test_features), dtype=float)
        predictions[ARM_INNER_CV] = [float(value) for value in np.maximum(raw, 1.0)]
    return (
        repeat,
        fold,
        [int(index) for index in train],
        [int(index) for index in test],
        predictions,
        chosen,
    )


def trimmed_context(context: Mapping[str, object]) -> dict[str, object]:
    """Only what a seed worker needs; the 2048-column Morgan block is left behind."""

    return {
        "groups": [str(group) for group in context["groups"]],
        "scored": np.asarray(context["scored"], dtype=bool),
        "full_base": np.asarray(context["full_base"], dtype=bool),
        "physical_lever4": np.asarray(context["physical_lever4"], dtype=float),
        "target": np.asarray(context["target"], dtype=float),
        "frozen_splits": list(context["frozen_splits"]),
        "n_base": int(context["n_base"]),
        "n_expansion": int(context["n_expansion"]),
        "expansion_report": context["expansion_report"],
        "lever4_report": context["lever4_report"],
        "contract": context["contract"],
    }


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    fold_jobs: int,
    arms: Sequence[str],
    placebo: bool,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, int],
    bool,
    dict[str, int],
]:
    """One seed: the whole grid, on the frozen splits."""

    groups = np.asarray([str(item) for item in context["groups"]])
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    features = np.asarray(context["physical_lever4"], dtype=float)
    target = np.asarray(context["target"], dtype=float)
    splits = splits_for(seed, groups, scored, full_base)
    signature_ok = True
    if seed == ANCHOR_SEED:
        frozen = bn.fold_signature(list(context["frozen_splits"]))
        if bn.fold_signature(splits) != frozen:
            signature_ok = False
    fit_target = target
    if placebo:
        generator = np.random.default_rng(PLACEBO_SEED)
        permuted = target.copy()
        permuted[scored] = target[scored][generator.permutation(int(scored.sum()))]
        fit_target = permuted
    tasks = [
        (int(repeat), int(fold), [int(i) for i in train], [int(i) for i in test])
        for repeat, fold, train, test in splits
    ]
    if fold_jobs <= 1 or len(tasks) <= 1:
        _init_grid_worker(features, fit_target, tuple(arms), groups)
        results = [_fold_task(task) for task in tasks]
    else:
        with ProcessPoolExecutor(
            max_workers=min(fold_jobs, len(tasks)),
            initializer=_init_grid_worker,
            initargs=(features, fit_target, tuple(arms), groups),
        ) as pool:
            results = list(pool.map(_fold_task, tasks))
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    fold_rows: list[dict[str, object]] = []
    choices: dict[str, int] = defaultdict(int)
    for repeat, fold, train_index, test_index, predictions, chosen in results:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(groups[train], groups[test]).size))
        if chosen:
            choices[chosen] += 1
        for arm in arms:
            prediction = np.asarray(predictions[arm], dtype=float)
            fold_metrics = evaluate_repeat(target[test], prediction)
            fold_rows.append(
                {
                    "seed": int(seed),
                    "arm": str(arm),
                    "representation": REPRESENTATION,
                    "repeat": int(repeat),
                    "fold": int(fold),
                    "train_rows": int(train.size),
                    "test_rows": int(test.size),
                    "r2": fold_metrics["r2"],
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            bucket = buckets.setdefault(
                (str(arm), int(repeat)), {"target": [], "prediction": []}
            )
            bucket["target"].append(target[test])
            bucket["prediction"].append(prediction)
    repeat_rows: list[dict[str, object]] = []
    for (arm, repeat), bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(
            np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"])
        )
        repeat_rows.append(
            {
                "arm": arm,
                "representation": REPRESENTATION,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    leak = {
        "folds": len(straddling),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
    }
    return repeat_rows, fold_rows, leak, signature_ok, dict(choices)


def _seed_entry(
    payload: tuple[int, Mapping[str, object], int, Sequence[str], bool],
) -> tuple[int, list[dict[str, object]], list[dict[str, object]], dict[str, int], bool, dict[str, int]]:
    seed, context, fold_jobs, arms, placebo = payload
    repeat_rows, fold_rows, leak, signature_ok, choices = evaluate_seed(
        int(seed), context, int(fold_jobs), tuple(arms), bool(placebo)
    )
    return int(seed), repeat_rows, fold_rows, leak, signature_ok, choices


def arm_summary(
    repeat_rows: Sequence[Mapping[str, object]],
    arms: Sequence[str],
) -> dict[str, dict[str, object]]:
    by_arm: dict[str, list[float]] = defaultdict(list)
    for row in repeat_rows:
        by_arm[str(row["arm"])].append(float(row["r2"]))
    summary: dict[str, dict[str, object]] = {}
    for arm in arms:
        values = by_arm[arm]
        summary[arm] = {
            "block": ARM_BLOCKS[arm],
            "repeats": len(values),
            "r2_mean": float(np.mean(values)),
            "r2_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "r2_min": float(np.min(values)),
            "r2_max": float(np.max(values)),
            "repeats_above_060": int(sum(1 for value in values if value > PASS_TARGET_R2)),
        }
    return summary


def _arm_params_view(arm: str) -> dict[str, object]:
    if arm == ARM_INNER_CV:
        return {
            "selection": "inner_fold_mean_r2_argmax",
            "inner_folds": INNER_FOLDS,
            "inner_seed": INNER_SEED,
            "candidates": list(INNER_CANDIDATES),
        }
    return dict(ARM_PARAMS[arm])


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()
    arms = parse_arms(args.arms)
    seeds = tuple(int(token) for token in str(args.seeds).split(",") if token.strip())
    if not seeds:
        print("no seeds requested")
        return 1
    placebo = bool(args.placebo)
    summary_path = PLACEBO_SUMMARY_PATH if placebo else SUMMARY_PATH
    report_path = PLACEBO_REPORT_PATH if placebo else REPORT_PATH
    artifact_stem = PLACEBO_ARTIFACT_STEM if placebo else ARTIFACT_STEM

    if bool(args.report_only):
        if not summary_path.is_file():
            print("MISSING " + str(summary_path))
            return 1
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        report_path.write_text(format_report(existing), encoding="utf-8", newline=chr(10))
        print("wrote " + str(report_path))
        return 0

    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1
    if tuple(str(name) for name in prereg.get("arms", ())) != ARM_ORDER:
        print("the locked arm list does not match the script; refusing to continue")
        return 1
    if int((prereg.get("grid") or {}).get("arm_count", -1)) != len(ARM_ORDER):
        print("the locked arm count does not match the script; refusing to continue")
        return 1
    if len(ARM_ORDER) > MAX_GRID_ARMS:
        print("the grid is over the pre-registered arm cap; refusing to continue")
        return 1
    locked_params = {
        str(key): value for key, value in dict(prereg.get("arm_params", {})).items()
    }
    for arm in FIXED_ARMS:
        if dict(locked_params.get(arm, {})) != dict(ARM_PARAMS[arm]):
            print("locked parameters for " + arm + " do not match the script; refusing")
            return 1
    if str(prereg.get("registered_arm")) != REGISTERED_ARM:
        print("the locked registered arm does not match the script; refusing to continue")
        return 1
    if tuple(int(seed) for seed in prereg.get("seeds", ())) != tuple(int(seed) for seed in SEEDS):
        print("the locked seed set does not match the script; refusing to continue")
        return 1

    context = build_context()
    scored_total = int(np.asarray(context["scored"]).sum())
    payload = trimmed_context(context)
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
        flush=True,
    )
    print(
        "arms: " + str(len(arms)) + " of " + str(len(ARM_ORDER)) + " (" + ", ".join(arms) + ")",
        flush=True,
    )
    print("seeds: " + ", ".join(str(seed) for seed in seeds), flush=True)

    fold_jobs = max(1, int(args.fold_jobs))
    jobs = int(args.jobs) if int(args.jobs) > 0 else len(seeds)
    jobs = max(1, min(jobs, len(seeds)))
    tasks = [(int(seed), payload, fold_jobs, tuple(arms), placebo) for seed in seeds]
    if jobs <= 1 or len(tasks) <= 1:
        raw_results = [_seed_entry(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            raw_results = list(pool.map(_seed_entry, tasks))

    per_seed: dict[int, list[dict[str, object]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    fold_counts: dict[str, int] = {}
    inner_choices: dict[str, dict[str, int]] = {}
    for seed, repeat_rows, fold_rows, leak, signature_ok, choices in raw_results:
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        per_seed[seed] = repeat_rows
        spreadsheet.extend({"seed": int(seed), **row} for row in repeat_rows)
        leakage[str(seed)] = leak
        fold_counts[str(seed)] = len(fold_rows)
        inner_choices[str(seed)] = choices
        block = arm_summary(repeat_rows, arms)
        for arm in arms:
            print(
                "  seed " + str(seed) + " | " + arm + " | "
                + format(float(block[arm]["r2_mean"]), ".6f"),
                flush=True,
            )

    summaries = {seed: arm_summary(rows, arms) for seed, rows in per_seed.items()}
    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    if ANCHOR_SEED in summaries and ARM_REFERENCE in arms and not placebo:
        measured = float(summaries[ANCHOR_SEED][ARM_REFERENCE]["r2_mean"])
        gap = abs(measured - FROZEN_SINGLE_REPRESENTATION)
        anchors_reproduced = gap <= ANCHOR_TOLERANCE
        anchor_rows.append(
            {
                "arm": ARM_REFERENCE,
                "seed": ANCHOR_SEED,
                "expected": FROZEN_SINGLE_REPRESENTATION,
                "measured": measured,
                "abs_gap": gap,
                "ok": anchors_reproduced,
            }
        )
        if not anchors_reproduced:
            print("the seed-42 anchor did not reproduce; refusing to report anything else")
            return 1

    leak_clean = all(
        block["folds_with_a_straddling_compound"] == 0
        and block["max_straddling_compounds_in_a_fold"] == 0
        for block in leakage.values()
    )
    if not leak_clean:
        print("a scored compound straddled a fold; refusing to continue")
        return 1

    seed_rows: list[dict[str, object]] = []
    for seed in seeds:
        for arm in arms:
            seed_rows.append({"seed": int(seed), "arm": arm, **summaries[seed][arm]})

    cross_rows: list[dict[str, object]] = []
    cross_means: dict[str, float] = {}
    for arm in arms:
        values = [float(summaries[seed][arm]["r2_mean"]) for seed in seeds]
        cross_means[arm] = float(np.mean(values))
        cross_rows.append(
            {
                "arm": arm,
                "block": ARM_BLOCKS[arm],
                "params": _arm_params_view(arm),
                "r2_seed_mean": float(np.mean(values)),
                "r2_seed_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "r2_seed_min": float(np.min(values)),
                "r2_seed_max": float(np.max(values)),
                "seed_means": [float(value) for value in values],
                "seeds_above_060": int(sum(1 for value in values if value > PASS_TARGET_R2)),
            }
        )

    registered_cross = float(cross_means[REGISTERED_ARM])
    registered_row = next(row for row in cross_rows if row["arm"] == REGISTERED_ARM)
    registered_seed_means = [float(value) for value in registered_row["seed_means"]]
    five_seed_lower_bound = float(np.min(registered_seed_means))
    pass_cross_seed_mean = registered_cross >= PASS_TARGET_R2
    pass_five_seed_lower_bound = five_seed_lower_bound > FIVE_SEED_LOWER_BOUND_MIN
    gate_met = bool(pass_cross_seed_mean and pass_five_seed_lower_bound)

    fixed_arms = [arm for arm in arms if arm in FIXED_ARMS and arm != ARM_REFERENCE]
    best_side_arm = max(fixed_arms, key=lambda arm: (cross_means[arm], arm)) if fixed_arms else None
    best_side_cross = float(cross_means[best_side_arm]) if best_side_arm else None
    reference_cross = float(cross_means[ARM_REFERENCE])

    placebo_check: dict[str, object] | None = None
    if placebo:
        real_cross: float | None = None
        if SUMMARY_PATH.is_file():
            real_summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
            real_value = (real_summary.get("answers") or {}).get("registered_arm_cross_seed_mean")
            real_cross = float(real_value) if real_value is not None else None
        collapsed = (
            real_cross is not None
            and registered_cross < PASS_TARGET_R2
            and registered_cross < float(real_cross)
        )
        placebo_check = {
            "registered_arm_cross_seed_mean": registered_cross,
            "registered_arm_five_seed_lower_bound": five_seed_lower_bound,
            "real_registered_arm_cross_seed_mean": real_cross,
            "pass_cross_seed_mean": bool(pass_cross_seed_mean),
            "collapse_rule": "(placebo mean < 0.60) AND (placebo mean < the real mean of the same arm)",
            "collapsed": bool(collapsed),
        }

    if placebo:
        verdict = "placebo"
        promoted = False
    elif gate_met:
        verdict = "promoted"
        promoted = True
    else:
        verdict = "not_promoted"
        promoted = False

    promotion: dict[str, object] = {
        "promoted": bool(promoted),
        "frozen_headline": FROZEN_HEADLINE,
        "frozen_baseline": FROZEN_BASELINE,
        "frozen_single_representation_cross_seed": FROZEN_CROSS_SEED_ENDPOINT,
        "registered_arm": REGISTERED_ARM,
        "gate": {
            "cross_seed_mean_min": PASS_TARGET_R2,
            "five_seed_lower_bound_min": FIVE_SEED_LOWER_BOUND_MIN,
        },
        "single_arm_discipline": (
            "only " + REGISTERED_ARM + " decides the verdict; every other arm of the "
            + str(len(arms) * len(seeds)) + "-reading grid is side information"
        ),
    }
    if promoted:
        promotion["main_scoreboard_ledger"] = {
            "week": "week20",
            "lane": "W20-4",
            "section": "28.60",
            "attempts_this_week": 1,
            "attempts_cumulative": 12,
            "attempt_index": 12,
            "attempt_kind": "epsilon_0.60_bounded_pass_gun",
            "registered_arm": REGISTERED_ARM,
            "cross_seed_mean_r2": registered_cross,
            "five_seed_lower_bound_r2": five_seed_lower_bound,
            "seed_means": registered_seed_means,
            "gate": {
                "cross_seed_mean_min": PASS_TARGET_R2,
                "five_seed_lower_bound_min": FIVE_SEED_LOWER_BOUND_MIN,
            },
            "declaration": "this is the 12th main-scoreboard attempt in this repository",
        }
    else:
        promotion["main_scoreboard_ledger"] = {
            "week": "week20",
            "lane": "W20-4",
            "section": "28.60",
            "attempts_this_week": 0,
            "attempts_cumulative": 11,
            "reason": "the registered single arm did not clear the pre-registered gate",
        }

    summary: dict[str, object] = {
        "schema": "w20_epsilon_second_stage/summary@1",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "fold_jobs": fold_jobs,
        "placebo": placebo,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "status": str(prereg.get("status")),
            "arm_count": int((prereg.get("grid") or {}).get("arm_count", len(ARM_ORDER))),
            "max_arms_cap": MAX_GRID_ARMS,
            "registered_arm": str(prereg.get("registered_arm")),
        },
        "pool": {
            "base_rows": payload["n_base"],
            "scored_rows": scored_total,
            "expansion_rows": payload["n_expansion"],
            "expansion_report": payload["expansion_report"],
            "lever4_report": payload["lever4_report"],
        },
        "honest_expectation": {
            "delta_low": HONEST_EXPECTATION_LOW,
            "delta_high": HONEST_EXPECTATION_HIGH,
            "basis": HONEST_EXPECTATION_BASIS,
            "note": "a reasoned expectation fixed before the run, not a measurement",
        },
        "caliber_anchors": {
            "frozen_baseline": FROZEN_BASELINE,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_single_representation_cross_seed": FROZEN_CROSS_SEED_ENDPOINT,
            "w18_best_arm": W18_BEST_ARM,
            "w18_best_cross_seed": W18_BEST_CROSS_SEED,
            "rule": "these are five different calibers; they may not be mixed with one another",
        },
        "placebo_check": placebo_check,
        "contract": {
            "representation": REPRESENTATION,
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "seeds": [int(seed) for seed in seeds],
            "anchor_seed": ANCHOR_SEED,
            "arms": list(arms),
            "arm_count": len(arms),
            "arm_cap": MAX_GRID_ARMS,
            "registered_arm": REGISTERED_ARM,
            "endpoint": "cross_seed_mean",
            "five_seed_lower_bound": "min over the five per-seed repeat-mean R2",
            "model_random_state": SEED,
            "frozen_hyperparameters": dict(XGB_PARAMS),
            "inner_fold": {
                "arm": ARM_INNER_CV,
                "inner_folds": INNER_FOLDS,
                "inner_seed": INNER_SEED,
                "candidates": list(INNER_CANDIDATES),
                "role": "side information; never decides the verdict",
            },
        },
        "arm_blocks": ARM_BLOCKS,
        "anchors": {
            "reproduced": anchors_reproduced,
            "rows": anchor_rows,
            "tolerance": ANCHOR_TOLERANCE,
        },
        "seed_rows": seed_rows,
        "cross_seed": cross_rows,
        "inner_cv_choices": inner_choices,
        "leakage": {
            "by_seed": leakage,
            "clean": leak_clean,
            "folds_by_seed": fold_counts,
        },
        "answers": {
            "target_r2": PASS_TARGET_R2,
            "five_seed_lower_bound_min": FIVE_SEED_LOWER_BOUND_MIN,
            "endpoint": "cross_seed_mean",
            "registered_arm": REGISTERED_ARM,
            "registered_arm_cross_seed_mean": registered_cross,
            "registered_arm_five_seed_lower_bound": five_seed_lower_bound,
            "registered_arm_seed_means": registered_seed_means,
            "registered_arm_above_060_seeds": int(registered_row["seeds_above_060"]),
            "pass_cross_seed_mean": bool(pass_cross_seed_mean),
            "pass_five_seed_lower_bound": bool(pass_five_seed_lower_bound),
            "gate_met": gate_met,
            "reference_arm": ARM_REFERENCE,
            "reference_cross_seed_mean": reference_cross,
            "best_side_arm": best_side_arm,
            "best_side_cross_seed_mean": best_side_cross,
            "side_grid_arm_count": len(fixed_arms),
            "seeds_run": [int(seed) for seed in seeds],
        },
        "verdict": verdict,
        "promotion": promotion,
        "outputs": {
            "summary": portable_relative_path(summary_path, root=REPOSITORY_ROOT),
            "report": portable_relative_path(report_path, root=REPOSITORY_ROOT),
            "repeats": portable_relative_path(
                ARTIFACTS_DIR / (artifact_stem + "_repeats.csv"), root=REPOSITORY_ROOT
            ),
        },
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (artifact_stem + "_repeats.csv"),
        ("seed", "arm", "representation", "repeat", *METRIC_NAMES),
        spreadsheet,
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    report_path.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("wrote " + str(summary_path))
    print("wrote " + str(report_path))
    print(
        "verdict: " + verdict
        + " | registered arm " + REGISTERED_ARM
        + " | cross-seed mean R2 " + format(registered_cross, ".6f")
        + " | five-seed lower bound " + format(five_seed_lower_bound, ".6f")
    )
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    answers = summary["answers"]
    contract = summary["contract"]
    anchors = summary["anchors"]
    leakage = summary["leakage"]
    prereg = summary["prereg"]
    pool = summary["pool"]
    cross_rows = summary["cross_seed"]
    lines: list[str] = []
    lines.append("# W20-4 (28.60)：P0 二段精调 —— 0.60 有界达标枪")
    lines.append("")
    lines.append("**结论（verdict）**：`" + str(summary["verdict"]) + "`。")
    lines.append("")
    lines.append(
        "- 判据（跑前钉死）：跨种子均值 **>= 0.60** 且 5 种子下界 **> 0.55**；"
        "单臂预注册，不许事后择优选报。"
    )
    lines.append(
        "- 预注册臂 `" + str(answers["registered_arm"]) + "`：跨种子均值 **"
        + format(float(answers["registered_arm_cross_seed_mean"]), ".6f")
        + "**，5 种子下界（五个种子重复均值的 min）**"
        + format(float(answers["registered_arm_five_seed_lower_bound"]), ".6f") + "**。"
    )
    lines.append(
        "- 判据达成：跨种子均值门 **" + str(bool(answers["pass_cross_seed_mean"]))
        + "**；5 种子下界门 **" + str(bool(answers["pass_five_seed_lower_bound"]))
        + "**；总门 **" + str(bool(answers["gate_met"])) + "**。"
    )
    lines.append("")
    lines.append("## 一、口径（冻结侧一律不动）")
    lines.append("")
    lines.append(
        "- 表示 `" + str(contract["representation"]) + "`；训练掩码 full_base（"
        + str(pool["base_rows"]) + " 行）；计分掩码 scored（" + str(pool["scored_rows"])
        + " 行 / 97 化合物）。"
    )
    lines.append(
        "- 协议：" + str(contract["n_splits"]) + " 折 × " + str(contract["n_repeats"])
        + " 重复，GroupKFold by InChIKey；模型 random_state 固定为 "
        + str(contract["model_random_state"]) + "，折种子只改折分配。"
    )
    lines.append(
        "- 机制：围绕 W18 最优臂 `" + W18_BEST_ARM + "`（跨种子 "
        + format(W18_BEST_CROSS_SEED, ".6f") + "）做二段精调，depth 固定 4、"
        "n_estimators 在 200–400，探 min_child_weight / colsample_bytree / max_bin。"
    )
    lines.append("")
    lines.append("## 二、锚点复现（不通过就不许报别的数）")
    lines.append("")
    if anchors["rows"]:
        for row in anchors["rows"]:
            lines.append(
                "- seed " + str(row["seed"]) + " / `" + str(row["arm"])
                + "`：实测 **" + format(float(row["measured"]), ".16f")
                + "**，冻结值 **" + format(float(row["expected"]), ".16f")
                + "**，|gap| = " + format(float(row["abs_gap"]), ".3e")
                + "（容差 " + str(anchors["tolerance"]) + "）。"
            )
    else:
        lines.append("- 本次运行是 placebo 或未含冻结头，未做锚点复现。")
    lines.append("- 折签名与冻结 scoreboard 的签名一致，否则脚本拒绝输出其它任何数。")
    lines.append("")
    lines.append("## 三、预注册臂（唯一决定判词）")
    lines.append("")
    lines.append(
        "首段 7 臂 × 5 种子 = 35 个读数，挑最大几乎必然「过 0.60」，那不是达标。"
        "因此本枪只认单臂预注册的 `" + str(answers["registered_arm"]) + "`，"
        "其余臂只作附带信息、不得用来改判。"
    )
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("| --- | --- |")
    lines.append(
        "| 预注册臂 | `" + str(answers["registered_arm"]) + "` |"
    )
    lines.append(
        "| 跨种子均值 R² | " + format(float(answers["registered_arm_cross_seed_mean"]), ".6f")
        + " |"
    )
    lines.append(
        "| 5 种子下界（min of seed means） | "
        + format(float(answers["registered_arm_five_seed_lower_bound"]), ".6f") + " |"
    )
    lines.append(
        "| 过 0.60 种子数 | " + str(int(answers["registered_arm_above_060_seeds"])) + " / 5 |"
    )
    lines.append("")
    lines.append("逐种子读数：")
    lines.append("")
    for row in cross_rows:
        if str(row["arm"]) != str(answers["registered_arm"]):
            continue
        for seed, value in zip(answers["seeds_run"], row["seed_means"], strict=True):
            lines.append(
                "- seed " + str(seed) + "：**" + format(float(value), ".6f") + "**"
            )
    lines.append("")
    lines.append("## 四、附带信息（不参与判词）")
    lines.append("")
    lines.append("| 臂 | 块 | 跨种子均值 R² | sd | min | max | 过 0.60 种子数 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in cross_rows:
        lines.append(
            "| " + str(row["arm"]) + " | " + str(row["block"]) + " | "
            + format(float(row["r2_seed_mean"]), ".6f") + " | "
            + format(float(row["r2_seed_sd"]), ".6f") + " | "
            + format(float(row["r2_seed_min"]), ".6f") + " | "
            + format(float(row["r2_seed_max"]), ".6f") + " | "
            + str(int(row["seeds_above_060"])) + " |"
        )
    lines.append("")
    lines.append(
        "- 附带网格里最高的非参考臂 = `" + str(answers["best_side_arm"])
        + "`，跨种子均值 " + format(float(answers["best_side_cross_seed_mean"]), ".6f")
        + "；它**不**决定判词。"
    )
    lines.append("")
    lines.append("## 五、泄漏审计")
    lines.append("")
    lines.append(
        "- 干净：" + str(bool(leakage["clean"])) + "；每个种子 "
        + str(sorted({int(value) for value in leakage["folds_by_seed"].values()}))
        + " 折行数（折 × 臂）。"
    )
    lines.append("- 计分化合物跨折计数全 0，最大值全 0，否则脚本拒绝继续。")
    lines.append("")
    lines.append("## 六、冻结口径与提升声明")
    lines.append("")
    lines.append(
        "- 诚实预期 **+0.01 ~ +0.05**（**判断，非实测**）：这是写预注册时按机制给出的期望"
        "区间，不是任何一次实测读数；本枪的实测见上文。"
    )
    lines.append(
        "- 口径锚点（**不得混比**，各是各的口径）：冻结基线 **0.4091179943351143**、"
        "冻结头条 **0.4766400383507876**、诚实五种子端点 **0.5861142332208197**、"
        "W18 最优臂 **0.5998203128630835**（离 0.60 差 0.00018）。"
    )
    ledger = summary["promotion"].get("main_scoreboard_ledger", {})
    lines.append(
        "- 冻结基线 **0.4091179943351143**、冻结头条 **0.4766400383507876** 原位保留；"
        "提升判词 promoted = " + str(bool(summary["promotion"]["promoted"])) + "；"
        "本周主记分牌尝试数 = " + str(int(ledger.get("attempts_this_week", 0)))
        + "、累计 = " + str(int(ledger.get("attempts_cumulative", 11))) + "。"
    )
    if bool(summary["promotion"]["promoted"]):
        lines.append(
            "- **显式声明：这是本仓第 12 次主记分牌尝试**（本周尝试数 = 1、累计 = 12）。"
        )
    lines.append(
        "- 预注册臂**非盲**：seed 42 的 `0.6080587938801277` 与 W18 首段 7 臂网格在写预注册前"
        "已知；本枪是同族二段精调，端点是跨种子均值而非单种子读数。"
    )
    lines.append("- Reaxys 数值不进入本探针的任何池、特征或产物（红线）。")
    if summary.get("placebo"):
        check = summary.get("placebo_check") or {}
        lines.append("")
        lines.append("## 六·补、placebo 塌缩核对")
        lines.append("")
        lines.append(
            "- 塌缩规则（预注册）：（placebo 均值 < 0.60）且（placebo 均值 < 同臂真实均值）。"
        )
        lines.append(
            "- placebo 预注册臂跨种子均值 = "
            + format(float(check.get("registered_arm_cross_seed_mean", float("nan"))), ".6f")
            + "；真实跨种子均值 = " + str(check.get("real_registered_arm_cross_seed_mean"))
            + "；塌缩 = " + str(bool(check.get("collapsed"))) + "。"
        )
    lines.append("")
    lines.append("## 七、预注册 digest")
    lines.append("")
    lines.append(
        "- " + str(prereg["path"]) + " | sha256 = " + str(prereg["sha256"])
        + " | status = " + str(prereg["status"]) + " | arm_count = " + str(prereg["arm_count"])
        + " / cap " + str(prereg["max_arms_cap"]) + "。"
    )
    lines.append("")
    return chr(10).join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
