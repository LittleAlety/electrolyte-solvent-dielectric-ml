"""W17 shot 17: can the frozen protocol be beaten by changing the head?

The frozen W17 record contains exactly one reading above 0.60: the
single-representation Physical arm on full_table_lever4 at 0.6080587938801277.
Shot 16 showed that value carries a favourable fold draw (seed mean 0.586114
over five seeds, 1/5 above 0.60).  This probe asks the next, separate question:
with the pool, the splitter, the scorer and the representation all frozen, does
swapping the *model head* clear 0.70?

Seven arms are pre-registered, all on Physical(lever4):

* xgb_reference      the frozen head (200 trees, depth 2, lr 0.05).
* xgb_deep           depth 8, 1200 trees, lr 0.03.
* extra_trees        500 fully randomised trees.
* kernel_ridge       RBF kernel ridge on standardised features, z-scored target.
* mlp                a (64, 32) network on the same standardised pair.
* blend_uniform      the arithmetic mean of the five single families, weights
  pinned in advance at 1/5 each.
* selected_inner_cv  pick the best single family by a 3-fold GroupKFold inside
  the training fold only, then refit it on the whole training fold.

Nothing on the frozen side moves.  xgb_reference has to reproduce
0.6080587938801277 bit for bit and the fold assignment has to keep the frozen
signature, otherwise the probe refuses to report anything else.

This probe is diagnostic: no reading it produces may be promoted.  The frozen
headline stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv/Scripts/python.exe probes/dielectric_head_sweep.py --jobs 8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
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
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.kernel_ridge import KernelRidge
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_head_sweep_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_head_sweep_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_head_sweep.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_head_sweep"

REPRESENTATION = "Physical(lever4)"
DEFAULT_SEEDS = "42"
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09

ARM_REFERENCE = "xgb_reference"
ARM_DEEP = "xgb_deep"
ARM_EXTRA_TREES = "extra_trees"
ARM_KERNEL_RIDGE = "kernel_ridge"
ARM_MLP = "mlp"
ARM_BLEND = "blend_uniform"
ARM_INNER_CV = "selected_inner_cv"
SINGLE_ARMS = (ARM_REFERENCE, ARM_DEEP, ARM_EXTRA_TREES, ARM_KERNEL_RIDGE, ARM_MLP)
ARMS = (*SINGLE_ARMS, ARM_BLEND, ARM_INNER_CV)

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
PASS_TARGET_R2 = 0.70
PARTIAL_TARGET_R2 = 0.60
IMPROVEMENT_BAR_R2 = 0.02
KILL_BAR_R2 = 0.005
MIN_CONFIRMING_SEEDS = 3
INNER_FOLDS = 3
INNER_SEED = 2026

DEEP_XGB_PARAMS = {
    **XGB_PARAMS,
    "max_depth": 8,
    "n_estimators": 1200,
    "learning_rate": 0.03,
}
EXTRA_TREES_ESTIMATORS = 500
KERNEL_RIDGE_PARAMS = {"kernel": "rbf", "alpha": 1.0}
MLP_PARAMS = {"hidden_layer_sizes": (64, 32), "max_iter": 1500}

HEAD_DESCRIPTIONS = {
    ARM_REFERENCE: "冻结头：200 棵树 / 深度 2 / 学习率 0.05（锚点，必须逐位复现）",
    ARM_DEEP: "深树：1200 棵树 / 深度 8 / 学习率 0.03",
    ARM_EXTRA_TREES: "500 棵完全随机化树（ExtraTrees）",
    ARM_KERNEL_RIDGE: "RBF 核岭回归（特征标准化、目标 z 标准化）",
    ARM_MLP: "(64, 32) 前馈网络（同样的标准化）",
    ARM_BLEND: "五个单族的等权算术平均（权重事前固定为 1/5）",
    ARM_INNER_CV: "训练折内部 3 折 GroupKFold 选族后再全折重拟合",
}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--seeds", type=str, default=DEFAULT_SEEDS)
    parser.add_argument("--arms", type=str, default="")
    parser.add_argument("--placebo", action="store_true")
    return parser.parse_args(argv)


def parse_arms(raw: str) -> tuple[str, ...]:
    """Canonical arm order; the frozen reference is always present."""

    requested = [token.strip() for token in str(raw).split(",") if token.strip()]
    if not requested:
        return ARMS
    unknown = [token for token in requested if token not in ARMS]
    if unknown:
        raise SystemExit("unknown head: " + ", ".join(unknown))
    return tuple(arm for arm in ARMS if arm in requested or arm == ARM_REFERENCE)


def heads_to_fit(arms: Sequence[str]) -> tuple[str, ...]:
    """Single families that have to be fitted for the requested arms."""

    if ARM_BLEND in arms or ARM_INNER_CV in arms:
        return SINGLE_ARMS
    return tuple(arm for arm in arms if arm in SINGLE_ARMS)


def standardise(
    train_features: np.ndarray,
    test_features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Feature scaling fitted on the training fold only."""

    centre = train_features.mean(axis=0)
    spread = train_features.std(axis=0)
    spread = np.where(spread == 0.0, 1.0, spread)
    return (train_features - centre) / spread, (test_features - centre) / spread


def fit_predict_head(
    head: str,
    train_features: np.ndarray,
    test_features: np.ndarray,
    train_target: np.ndarray,
    seed: int,
) -> np.ndarray:
    """One family, trained on the training fold, returning raw predictions."""

    if head == ARM_REFERENCE:
        model = XGBRegressor(**XGB_PARAMS, random_state=seed)
        model.fit(train_features, train_target)
        return np.asarray(model.predict(test_features), dtype=float)
    if head == ARM_DEEP:
        model = XGBRegressor(**DEEP_XGB_PARAMS, random_state=seed)
        model.fit(train_features, train_target)
        return np.asarray(model.predict(test_features), dtype=float)
    if head == ARM_EXTRA_TREES:
        model = ExtraTreesRegressor(
            n_estimators=EXTRA_TREES_ESTIMATORS, random_state=seed, n_jobs=1
        )
        model.fit(train_features, train_target)
        return np.asarray(model.predict(test_features), dtype=float)
    if head in (ARM_KERNEL_RIDGE, ARM_MLP):
        standard_train, standard_test = standardise(train_features, test_features)
        centre = float(train_target.mean())
        spread = float(train_target.std())
        if spread == 0.0:
            spread = 1.0
        scaled_target = (train_target - centre) / spread
        if head == ARM_KERNEL_RIDGE:
            model = KernelRidge(gamma=1.0 / train_features.shape[1], **KERNEL_RIDGE_PARAMS)
        else:
            model = MLPRegressor(random_state=seed, **MLP_PARAMS)
        model.fit(standard_train, scaled_target)
        return np.asarray(model.predict(standard_test), dtype=float) * spread + centre
    raise ValueError("unknown head: " + str(head))


def select_head(
    train_features: np.ndarray,
    train_target: np.ndarray,
    train_groups: np.ndarray,
    seed: int,
) -> str:
    """Best single family by a GroupKFold inside the training fold only.

    Nothing here sees the held-out fold, so the arm is honest but still inside
    the training data.  Ties break on the arm name so the choice is deterministic.
    """

    splitter = GroupKFold(n_splits=INNER_FOLDS)
    scores: dict[str, list[float]] = {head: [] for head in SINGLE_ARMS}
    for inner_train, inner_test in splitter.split(
        train_features, train_target, groups=train_groups
    ):
        if np.asarray(inner_test).size < 2:
            continue
        for head in SINGLE_ARMS:
            prediction = fit_predict_head(
                head,
                train_features[inner_train],
                train_features[inner_test],
                train_target[inner_train],
                seed,
            )
            prediction = np.maximum(prediction, 1.0)
            scores[head].append(
                float(evaluate_repeat(train_target[inner_test], prediction)["r2"])
            )
    ranked = sorted(
        SINGLE_ARMS,
        key=lambda head: (-(float(np.mean(scores[head])) if scores[head] else 0.0), head),
    )
    return ranked[0]


_HEAD_STATE: dict[str, object] = {}


def _init_head_worker(
    features: np.ndarray,
    groups: np.ndarray,
    target: np.ndarray,
    arms: Sequence[str],
) -> None:
    _HEAD_STATE["features"] = features
    _HEAD_STATE["groups"] = groups
    _HEAD_STATE["target"] = target
    _HEAD_STATE["arms"] = tuple(arms)


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]], str]:
    """One fold: every requested head, in one worker process."""

    repeat, fold, train_index, test_index = task
    features = _HEAD_STATE["features"]
    groups = _HEAD_STATE["groups"]
    target = _HEAD_STATE["target"]
    arms = _HEAD_STATE["arms"]
    assert isinstance(features, np.ndarray)
    assert isinstance(groups, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(arms, tuple)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    train_features = features[train]
    test_features = features[test]
    train_target = target[train]
    raw: dict[str, np.ndarray] = {}
    for head in heads_to_fit(arms):
        raw[head] = fit_predict_head(head, train_features, test_features, train_target, SEED)
    if ARM_BLEND in arms:
        raw[ARM_BLEND] = np.mean([raw[head] for head in SINGLE_ARMS], axis=0)
    chosen = ""
    if ARM_INNER_CV in arms:
        chosen = select_head(train_features, train_target, groups[train], SEED)
        raw[ARM_INNER_CV] = fit_predict_head(
            chosen, train_features, test_features, train_target, SEED
        )
    predictions = {
        head: [float(value) for value in np.maximum(raw[head], 1.0)] for head in arms
    }
    return (
        repeat,
        fold,
        [int(index) for index in train],
        [int(index) for index in test],
        predictions,
        chosen,
    )


def _parallel_map(
    function: Callable[[object], object],
    tasks: Sequence[object],
    jobs: int,
    *,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[object, ...] = (),
) -> list[object]:
    if jobs <= 1 or len(tasks) <= 1:
        if initializer is not None:
            initializer(*initargs)
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(
        max_workers=jobs, initializer=initializer, initargs=initargs
    ) as pool:
        return list(pool.map(function, tasks))


def arm_summary(repeat_rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    by_arm: dict[str, list[float]] = defaultdict(list)
    for row in repeat_rows:
        by_arm[str(row["arm"])].append(float(row["r2"]))
    summary: dict[str, dict[str, object]] = {}
    for arm, values in by_arm.items():
        summary[arm] = {
            "repeats": len(values),
            "r2_mean": float(np.mean(values)),
            "r2_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "r2_min": float(np.min(values)),
            "r2_max": float(np.max(values)),
            "repeats_above_060": int(sum(1 for value in values if value > PARTIAL_TARGET_R2)),
            "repeats_above_070": int(sum(1 for value in values if value > PASS_TARGET_R2)),
        }
    return summary


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    jobs: int,
    arms: Sequence[str],
    placebo: bool,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, int],
    dict[str, int],
    bool,
]:
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
        generator = np.random.default_rng(INNER_SEED)
        permuted = target.copy()
        permuted[scored] = target[scored][generator.permutation(int(scored.sum()))]
        fit_target = permuted
    tasks = [
        (
            int(repeat),
            int(fold),
            [int(index) for index in train],
            [int(index) for index in test],
        )
        for repeat, fold, train, test in splits
    ]
    results = _parallel_map(
        _fold_task,
        tasks,
        jobs,
        initializer=_init_head_worker,
        initargs=(features, groups, fit_target, tuple(arms)),
    )
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    chosen_tally: dict[str, int] = defaultdict(int)
    fold_rows: list[dict[str, object]] = []
    for repeat, fold, train_index, test_index, predictions, chosen in results:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(groups[train], groups[test]).size))
        if chosen:
            chosen_tally[str(chosen)] += 1
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
                    "train_compounds": int(np.unique(groups[train]).size),
                    "test_compounds": int(np.unique(groups[test]).size),
                    "r2": fold_metrics["r2"],
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            bucket = buckets.setdefault((str(arm), int(repeat)), {"target": [], "prediction": []})
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
    return repeat_rows, fold_rows, dict(chosen_tally), leak, signature_ok


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()
    jobs = max(1, int(args.jobs))
    arms = parse_arms(args.arms)
    seeds = tuple(int(token) for token in str(args.seeds).split(",") if token.strip())
    if not seeds:
        print("no seeds requested")
        return 1
    placebo = bool(args.placebo)

    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    context = build_context()
    scored_total = int(np.asarray(context["scored"]).sum())
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
        flush=True,
    )
    print("heads: " + ", ".join(arms), flush=True)
    print("seeds: " + ", ".join(str(seed) for seed in seeds), flush=True)

    per_seed: dict[int, list[dict[str, object]]] = {}
    spreadsheet: list[dict[str, object]] = []
    chosen_by_seed: dict[str, dict[str, int]] = {}
    leakage: dict[str, dict[str, int]] = {}
    fold_counts: dict[str, int] = {}
    for seed in seeds:
        clock = time.perf_counter()
        repeat_rows, fold_rows, chosen, leak, signature_ok = evaluate_seed(
            seed, context, jobs, arms, placebo
        )
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        per_seed[seed] = repeat_rows
        spreadsheet.extend({"seed": int(seed), **row} for row in repeat_rows)
        chosen_by_seed[str(seed)] = chosen
        leakage[str(seed)] = leak
        fold_counts[str(seed)] = len(fold_rows)
        block = arm_summary(repeat_rows)
        for arm in arms:
            print(
                "  seed " + str(seed) + " | " + arm + " | "
                + format(float(block[arm]["r2_mean"]), ".6f")
                + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
                flush=True,
            )

    summaries = {seed: arm_summary(rows) for seed, rows in per_seed.items()}
    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    if ANCHOR_SEED in summaries and not placebo:
        measured = float(summaries[ANCHOR_SEED][ARM_REFERENCE]["r2_mean"])
        gap = abs(measured - FROZEN_SINGLE_REPRESENTATION)
        anchors_reproduced = gap <= ANCHOR_TOLERANCE
        anchor_rows.append(
            {
                "head": ARM_REFERENCE,
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

    reference_seed = ANCHOR_SEED if ANCHOR_SEED in summaries else seeds[0]
    reference_mean = float(summaries[reference_seed][ARM_REFERENCE]["r2_mean"])
    comparison = [arm for arm in arms if arm != ARM_REFERENCE]
    improvements = {
        arm: float(summaries[reference_seed][arm]["r2_mean"]) - reference_mean
        for arm in comparison
    }
    if comparison:
        best_arm = max(comparison, key=lambda arm: (improvements[arm], arm))
    else:
        best_arm = ARM_REFERENCE
    best_r2 = float(summaries[reference_seed][best_arm]["r2_mean"])
    best_improvement = float(improvements.get(best_arm, 0.0))
    cross_seed_best = float(
        np.mean([float(summaries[seed][best_arm]["r2_mean"]) for seed in seeds])
    )

    if placebo:
        verdict = "placebo"
    elif (
        best_r2 >= PASS_TARGET_R2
        and best_improvement >= IMPROVEMENT_BAR_R2
        and cross_seed_best >= PASS_TARGET_R2
        and len(seeds) >= MIN_CONFIRMING_SEEDS
    ):
        verdict = "confirmed"
    elif best_improvement >= KILL_BAR_R2:
        verdict = "partial"
    else:
        verdict = "refuted"

    seed_rows: list[dict[str, object]] = []
    for seed in seeds:
        for arm in arms:
            seed_rows.append({"seed": int(seed), "head": arm, **summaries[seed][arm]})

    cross_seed_reference = float(
        np.mean([float(summaries[seed][ARM_REFERENCE]["r2_mean"]) for seed in seeds])
    )
    cross_rows: list[dict[str, object]] = []
    per_head_seed_means: dict[str, list[float]] = {}
    for arm in arms:
        values = [float(summaries[seed][arm]["r2_mean"]) for seed in seeds]
        per_head_seed_means[arm] = values
        cross_rows.append(
            {
                "head": arm,
                "description": HEAD_DESCRIPTIONS[arm],
                "r2_seed_mean": float(np.mean(values)),
                "r2_seed_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "r2_seed_min": float(np.min(values)),
                "r2_seed_max": float(np.max(values)),
                "improvement_vs_reference": float(np.mean(values)) - cross_seed_reference,
            }
        )

    summary: dict[str, object] = {
        "schema": "dielectric_head_sweep/summary@1",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "placebo": placebo,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "status": str(prereg.get("status")),
        },
        "pool": {
            "base_rows": context["n_base"],
            "scored_rows": scored_total,
            "expansion_rows": context["n_expansion"],
            "expansion_report": context["expansion_report"],
            "lever4_report": context["lever4_report"],
        },
        "contract": {
            "representation": REPRESENTATION,
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "seeds": list(seeds),
            "anchor_seed": ANCHOR_SEED,
            "heads": list(arms),
            "inner_folds": INNER_FOLDS,
            "inner_seed": INNER_SEED,
            "frozen_head_params": XGB_PARAMS,
            "deep_head_params": DEEP_XGB_PARAMS,
            "extra_trees_estimators": EXTRA_TREES_ESTIMATORS,
            "kernel_ridge_params": KERNEL_RIDGE_PARAMS,
            "mlp_hidden_layer_sizes": [64, 32],
            "mlp_max_iter": 1500,
        },
        "anchors": {
            "reproduced": anchors_reproduced,
            "rows": anchor_rows,
            "tolerance": ANCHOR_TOLERANCE,
        },
        "head_descriptions": HEAD_DESCRIPTIONS,
        "seed_rows": seed_rows,
        "cross_seed": cross_rows,
        "inner_cv_choices": chosen_by_seed,
        "leakage": {
            "by_seed": leakage,
            "clean": leak_clean,
            "folds_by_seed": fold_counts,
        },
        "answers": {
            "target_r2": PASS_TARGET_R2,
            "partial_target_r2": PARTIAL_TARGET_R2,
            "improvement_bar_r2": IMPROVEMENT_BAR_R2,
            "kill_bar_r2": KILL_BAR_R2,
            "reference_head": ARM_REFERENCE,
            "reference_r2": reference_mean,
            "reference_seed": reference_seed,
            "cross_seed_reference_r2": cross_seed_reference,
            "best_head": best_arm,
            "best_r2": best_r2,
            "best_improvement": best_improvement,
            "cross_seed_mean_of_best_head": cross_seed_best,
            "target_met_at_anchor_seed": bool(best_r2 >= PASS_TARGET_R2),
            "target_met_cross_seed": bool(cross_seed_best >= PASS_TARGET_R2),
            "partial_target_met": bool(best_r2 >= PARTIAL_TARGET_R2),
            "seeds_run": [int(seed) for seed in seeds],
            "single_seed_run": bool(len(seeds) < MIN_CONFIRMING_SEEDS),
        },
        "verdict": verdict,
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "diagnostic head sweep on the frozen protocol; the frozen headline is a "
                "co-primary hybrid arm and this probe is non-blind with respect to seed 42"
            ),
        },
        "outputs": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "repeats": portable_relative_path(
                ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), root=REPOSITORY_ROOT
            ),
        },
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"),
        ("seed", "arm", "representation", "repeat", *METRIC_NAMES),
        spreadsheet,
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("wrote " + str(SUMMARY_PATH))
    print("wrote " + str(REPORT_PATH))
    print(
        "verdict: " + verdict
        + " | best head " + best_arm
        + " | R2 " + format(best_r2, ".6f")
        + " (frozen head " + format(reference_mean, ".6f")
        + ", improvement " + format(best_improvement, "+.6f") + ")"
    )
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    contract = summary["contract"]
    answers = summary["answers"]
    pool = summary["pool"]
    anchors = summary["anchors"]
    cross_rows = summary["cross_seed"]
    seed_rows = summary["seed_rows"]
    choices = summary["inner_cv_choices"]
    assert isinstance(contract, Mapping)
    assert isinstance(answers, Mapping)
    assert isinstance(pool, Mapping)
    assert isinstance(anchors, Mapping)
    assert isinstance(cross_rows, Sequence)
    assert isinstance(seed_rows, Sequence)
    assert isinstance(choices, Mapping)
    target = float(answers["target_r2"])
    best_r2 = float(answers["best_r2"])
    best_head = str(answers["best_head"])
    reference_mean = float(answers["reference_r2"])
    best_improvement = float(answers["best_improvement"])
    cross_best = float(answers["cross_seed_mean_of_best_head"])
    seed_list = [int(seed) for seed in answers["seeds_run"]]
    lines: list[str] = []
    lines.append("# 介电常数 ε：换「模型头」能否突破 0.70（W17 第 17 枪，诊断性）")
    lines.append("")
    lines.append("**这不是提升，也不是新发现。** 池、分折、计分、表示（`Physical(lever4)`）全部冻结，")
    lines.append("只换模型族，问一个可证伪的问题：**头部替换能不能把单表示 R² 推过 0.70。**")
    lines.append("")
    lines.append("## 结论先行")
    lines.append("")
    lines.append(
        "- 目标 R² ≥ **" + format(target, ".2f") + "**："
        + ("**达到**" if answers["target_met_at_anchor_seed"] else "**未达到**")
        + "。最佳头 `" + best_head + "` 在锚种子 " + str(answers["reference_seed"])
        + " 上 R² = **" + format(best_r2, ".6f") + "**。"
    )
    lines.append(
        "- 相对冻结头 `" + str(answers["reference_head"]) + "`（" + format(reference_mean, ".6f")
        + "）的增益 = **" + format(best_improvement, "+.6f") + "**；提升门槛 +"
        + format(float(answers["improvement_bar_r2"]), ".2f") + "，淘汰门槛 +"
        + format(float(answers["kill_bar_r2"]), ".3f") + "。"
    )
    lines.append(
        "- 旧目标 R² ≥ **" + format(float(answers["partial_target_r2"]), ".2f") + "**："
        + ("**达到**" if answers["partial_target_met"] else "**未达到**") + "。"
    )
    lines.append(
        "- 最佳头的跨种子均值 = **" + format(cross_best, ".6f") + "**"
        + ("（≥ " if answers["target_met_cross_seed"] else "（< ")
        + format(target, ".2f") + "）。"
    )
    lines.append(
        "- **判定**：`" + str(summary["verdict"]) + "`；运行种子 = "
        + ", ".join(str(seed) for seed in seed_list) + "。"
    )
    lines.append("")
    lines.append("## 冻结侧（一个都不动）")
    lines.append("")
    lines.append(
        "- 池：" + str(pool["base_rows"]) + " 行基表训练行；计分 " + str(pool["scored_rows"])
        + " 行 / 97 化合物 / 276 个 (化合物, T) 对；外源行 " + str(pool["expansion_rows"]) + " 行"
    )
    lines.append(
        "- 分折：GroupKFold by InChIKey，" + str(contract["n_splits"]) + " 折 x "
        + str(contract["n_repeats"]) + " 重复"
    )
    lines.append("- 表示：`" + str(contract["representation"]) + "`（单一表示，不含 Morgan 指纹）")
    lines.append("- 预测统一裁剪到 ≥ 1.0（与冻结拟合器一致）")
    lines.append("")
    lines.append("## 锚点：冻结头必须逐位复现 " + repr(FROZEN_SINGLE_REPRESENTATION))
    lines.append("")
    lines.append("| 头 | 种子 | 登记值 | 本次实测 | abs_gap | ok |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    anchor_list = anchors["rows"]
    assert isinstance(anchor_list, Sequence)
    for row in anchor_list:
        assert isinstance(row, Mapping)
        lines.append(
            "| `" + str(row["head"]) + "` | " + str(row["seed"]) + " | " + repr(row["expected"])
            + " | " + repr(row["measured"]) + " | " + format(float(row["abs_gap"]), ".2e")
            + " | " + ("OK" if row["ok"] else "MISS") + " |"
        )
    if not anchor_list:
        lines.append("| （安慰剂模式，锚点不适用） | - | - | - | - | - |")
    lines.append("")
    lines.append("## 各头的跨种子表现")
    lines.append("")
    lines.append("| 头 | 说明 | R2（种子均值） | 种子间 sd | min | max | 相对冻结头 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    heads: list[str] = []
    for row in cross_rows:
        assert isinstance(row, Mapping)
        heads.append(str(row["head"]))
        lines.append(
            "| `" + str(row["head"]) + "` | " + str(row["description"]) + " | "
            + format(float(row["r2_seed_mean"]), ".6f") + " | "
            + format(float(row["r2_seed_sd"]), ".4f") + " | "
            + format(float(row["r2_seed_min"]), ".6f") + " | "
            + format(float(row["r2_seed_max"]), ".6f") + " | "
            + format(float(row["improvement_vs_reference"]), "+.6f") + " |"
        )
    lines.append("")
    lines.append("## 逐种子明细（每格为该头在该种子上的 repeat 均值 R2）")
    lines.append("")
    lines.append("| 头 | " + " | ".join(str(seed) for seed in seed_list) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in seed_list) + " |")
    by_key: dict[tuple[int, str], Mapping[str, object]] = {}
    for row in seed_rows:
        assert isinstance(row, Mapping)
        by_key[(int(row["seed"]), str(row["head"]))] = row
    for head in heads:
        cells = [format(float(by_key[(seed, head)]["r2_mean"]), ".6f") for seed in seed_list]
        lines.append("| `" + head + "` | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 内层选族（`selected_inner_cv` 只看训练折内部）")
    lines.append("")
    for seed, tally in sorted(choices.items()):
        if not tally:
            continue
        rendered = ", ".join(
            str(head) + " x" + str(count) for head, count in sorted(tally.items())
        )
        lines.append(
            "- 种子 " + str(seed) + "：共 " + str(sum(int(v) for v in tally.values()))
            + " 折，选中的族 " + rendered
        )
    lines.append("")
    lines.append("## 判定规则（预先注册）")
    lines.append("")
    lines.append(
        "1. `confirmed`：最佳头在锚种子 R² ≥ " + format(target, ".2f")
        + " **且**增益 ≥ +" + format(float(answers["improvement_bar_r2"]), ".2f")
        + " **且**跨种子均值 ≥ " + format(target, ".2f")
        + " **且**至少跑了 " + str(MIN_CONFIRMING_SEEDS) + " 个种子。"
    )
    lines.append(
        "2. `partial`：最佳头相对冻结头的增益 ≥ +"
        + format(float(answers["kill_bar_r2"]), ".3f") + "，但未满足 `confirmed` 的全部条件。"
    )
    lines.append(
        "3. `refuted`：所有头的增益 < +" + format(float(answers["kill_bar_r2"]), ".3f") + "。"
    )
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append("1. 本探针**非盲**：0.6081 这个锚点在预注册之前就已经知道。")
    lines.append("2. 最佳头是在若干**预先注册**候选里事后挑最大值，存在多重比较红利；单种子结果只能读作上界探测。")
    lines.append(
        "3. **任何读数一律不提升**：冻结头条保持 " + repr(FROZEN_HEADLINE)
        + "，冻结基线保持 " + repr(FROZEN_BASELINE) + "。"
    )
    lines.append("4. 单表示（`Physical`）与冻结头条的混合口径不同，不得跨口径相减用于达标宣称。")
    if answers["single_seed_run"]:
        lines.append(
            "5. 本枪只跑了 " + str(len(seed_list)) + " 个种子，按预注册最多只能判到 `partial`；"
            "`confirmed` 需要 ≥ " + str(MIN_CONFIRMING_SEEDS) + " 个种子的稳健性复验。"
        )
    else:
        lines.append(
            "5. 本枪跑了 " + str(len(seed_list)) + " 个种子；跨种子均值已计入判定。"
        )
    lines.append("")
    return chr(10).join(lines) + chr(10)


if __name__ == "__main__":
    raise SystemExit(main())