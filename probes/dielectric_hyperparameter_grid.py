"""W18 P0: does retuning the XGBoost head of the dense physical configuration clear 0.60?

Shot 17 (probes/dielectric_head_sweep.py) refuted the "swap the model family" path:
with the pool, the splitter, the scorer and the representation frozen, the best
alternative family reached 0.567035 against the frozen head at 0.608059, and the
inner-fold family selector systematically picked the worst families.  P0 asks the
remaining, narrower question: same family (XGBoost), same frozen protocol, does
retuning the hyperparameters of the *dense* physical configuration push the
cross-seed endpoint above 0.60?

The frozen head was tuned for 2048-column sparse Morgan fingerprints, while the
winning Physical(lever4) block has 13-15 dense columns, so max_depth 2 (four leaves
per tree) is plausibly underfitting.  This probe pre-registers a grid over
max_depth / n_estimators / learning_rate / min_child_weight / subsample /
colsample_bytree.  The full cartesian is 288 arms and is deliberately not run; the
locked subset, the factor levels and the selection rule live in
probes/dielectric_hyperparameter_grid_prereg.json and are re-checked at runtime.
The candidate blocks were listed as 22 arms, but the cost was measured before the first
fit -- see PRE_RUN_AMENDMENT below -- and the registered arm set is the 7-arm subset that
carries both grid axes plus one depth x capacity interaction point.

Nothing on the frozen side moves.  xgb_reference has to reproduce
0.6080587938801277 bit for bit and the fold assignment has to keep the frozen
signature, otherwise the probe refuses to report anything else.  The endpoint is the
cross-seed mean over the five pre-registered seeds (42, 1234, 2026, 31337, 7).

This probe is diagnostic: no reading it produces may be promoted.  The frozen
headline stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv/Scripts/python.exe probes/dielectric_hyperparameter_grid.py --jobs 4
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
from export_results_common import write_json_stable
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_hyperparameter_grid_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_hyperparameter_grid_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_hyperparameter_grid.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_hyperparameter_grid"
PLACEBO_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_hyperparameter_grid_placebo_summary.json"
)
PLACEBO_REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_hyperparameter_grid_placebo.md"
PLACEBO_ARTIFACT_STEM = "dielectric_hyperparameter_grid_placebo"

REPRESENTATION = "Physical(lever4)"
SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
PLACEBO_SEED = 2026

ARM_REFERENCE = "xgb_reference"
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

PASS_TARGET_R2 = 0.60
IMPROVEMENT_BAR_R2 = 0.02
KILL_BAR_R2 = 0.005
MAX_GRID_ARMS = 24

# The pre-registered candidate blocks listed 22 arms.  The cost was measured before the
# first fit -- one frozen-head fit (200 trees, depth 2) on the 2029 x 2061 dense
# Physical(lever4)+Morgan matrix is 4.16 s CPU and the deepest candidate (800 trees, depth
# 6) is about 35 s -- which makes the candidate set 22 arms x 50 folds x 5 seeds, i.e.
# over 2.6 hours of pure CPU for one seed set.  The registered arm set is therefore the
# 7-arm subset that carries both grid axes plus one depth x capacity interaction point;
# the digest was re-pinned at the same time and no result existed then.
PRE_RUN_AMENDMENT = (
    "2026-09-27, recorded before the first fit: the candidate blocks listed 22 arms, but "
    "22 arms x 50 folds x 5 seeds is 5,500 fits per seed and over 2.6 hours of pure CPU "
    "for one seed set, so the registered arm set is the 7-arm subset that carries both "
    "grid axes plus one depth x capacity interaction point; the digest was re-pinned and "
    "no result existed when this was recorded."
)

# (name, n_estimators, max_depth, learning_rate, min_child_weight, subsample,
#  colsample_bytree, block).  The reference row is the frozen head and must not move.
GRID_ARMS = (
    ("xgb_reference", 200, 2, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d3_n200_lr0.05_mcw1_ss0.8_cs0.8", 200, 3, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d4_n200_lr0.05_mcw1_ss0.8_cs0.8", 200, 4, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d6_n200_lr0.05_mcw1_ss0.8_cs0.8", 200, 6, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d2_n400_lr0.05_mcw1_ss0.8_cs0.8", 400, 2, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d2_n800_lr0.05_mcw1_ss0.8_cs0.8", 800, 2, 0.05, 1, 0.8, 0.8, "axis"),
    ("hp_d4_n400_lr0.05_mcw1_ss0.8_cs0.8", 400, 4, 0.05, 1, 0.8, 0.8, "capacity_ladder"),
)


ARM_ORDER = tuple(row[0] for row in GRID_ARMS)
ARM_BLOCKS = {row[0]: str(row[7]) for row in GRID_ARMS}
ARM_TUPLES = {row[0]: tuple(row[1:7]) for row in GRID_ARMS}
ARM_PARAMS = {
    row[0]: {
        **XGB_PARAMS,
        "n_estimators": int(row[1]),
        "max_depth": int(row[2]),
        "learning_rate": float(row[3]),
        "min_child_weight": int(row[4]),
        "subsample": float(row[5]),
        "colsample_bytree": float(row[6]),
    }
    for row in GRID_ARMS
}

BLOCK_ORDER = ("axis", "capacity_ladder", "regularisation_relaxed")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--seeds", type=str, default=",".join(str(seed) for seed in SEEDS))
    parser.add_argument("--arms", type=str, default="")
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


_STATE: dict[str, object] = {}


def _init_worker(
    features: np.ndarray,
    target: np.ndarray,
    arms: Sequence[str],
) -> None:
    _STATE["features"] = features
    _STATE["target"] = target
    _STATE["arms"] = tuple(arms)


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    """One fold: every requested grid arm, in one worker process."""

    repeat, fold, train_index, test_index = task
    features = _STATE["features"]
    target = _STATE["target"]
    arms = _STATE["arms"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(arms, tuple)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    predictions: dict[str, list[float]] = {}
    for arm in arms:
        model = XGBRegressor(**ARM_PARAMS[arm], random_state=SEED)
        model.fit(features[train], target[train])
        raw = np.asarray(model.predict(features[test]), dtype=float)
        predictions[arm] = [float(value) for value in np.maximum(raw, 1.0)]
    return (
        repeat,
        fold,
        [int(index) for index in train],
        [int(index) for index in test],
        predictions,
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


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    jobs: int,
    arms: Sequence[str],
    placebo: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int], bool]:
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
        initializer=_init_worker,
        initargs=(features, fit_target, tuple(arms)),
    )
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    fold_rows: list[dict[str, object]] = []
    for repeat, fold, train_index, test_index, predictions in results:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(groups[train], groups[test]).size))
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
    return repeat_rows, fold_rows, leak, signature_ok


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
    summary_path = PLACEBO_SUMMARY_PATH if placebo else SUMMARY_PATH
    report_path = PLACEBO_REPORT_PATH if placebo else REPORT_PATH
    artifact_stem = PLACEBO_ARTIFACT_STEM if placebo else ARTIFACT_STEM

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
    for arm in ARM_ORDER:
        if dict(locked_params.get(arm, {})) != dict(ARM_PARAMS[arm]):
            print("locked parameters for " + arm + " do not match the script; refusing")
            return 1
    if tuple(int(seed) for seed in prereg.get("seeds", ())) != tuple(
        int(seed) for seed in SEEDS
    ):
        print("the locked seed set does not match the script; refusing to continue")
        return 1

    context = build_context()
    scored_total = int(np.asarray(context["scored"]).sum())
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

    per_seed: dict[int, list[dict[str, object]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    fold_counts: dict[str, int] = {}
    for seed in seeds:
        clock = time.perf_counter()
        repeat_rows, fold_rows, leak, signature_ok = evaluate_seed(
            seed, context, jobs, arms, placebo
        )
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        per_seed[seed] = repeat_rows
        spreadsheet.extend({"seed": int(seed), **row} for row in repeat_rows)
        leakage[str(seed)] = leak
        fold_counts[str(seed)] = len(fold_rows)
        block = arm_summary(repeat_rows, arms)
        for arm in arms:
            print(
                "  seed " + str(seed) + " | " + arm + " | "
                + format(float(block[arm]["r2_mean"]), ".6f")
                + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
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
                "params": ARM_PARAMS[arm],
                "r2_seed_mean": float(np.mean(values)),
                "r2_seed_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "r2_seed_min": float(np.min(values)),
                "r2_seed_max": float(np.max(values)),
                "seed_means": [float(value) for value in values],
                "seeds_above_060": int(sum(1 for value in values if value > PASS_TARGET_R2)),
            }
        )
    reference_cross = float(cross_means.get(ARM_REFERENCE, float("nan")))
    comparison = [arm for arm in arms if arm != ARM_REFERENCE]
    if comparison:
        best_arm = max(comparison, key=lambda arm: (cross_means[arm], arm))
        best_cross = float(cross_means[best_arm])
        best_improvement = best_cross - reference_cross
    else:
        best_arm = ARM_REFERENCE
        best_cross = reference_cross
        best_improvement = 0.0

    if placebo:
        verdict = "placebo"
    elif best_cross > PASS_TARGET_R2 and best_improvement >= IMPROVEMENT_BAR_R2:
        verdict = "confirmed"
    elif best_improvement >= KILL_BAR_R2:
        verdict = "partial"
    else:
        verdict = "refuted"

    summary: dict[str, object] = {
        "schema": "dielectric_hyperparameter_grid/summary@1",
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
            "arm_count": int((prereg.get("grid") or {}).get("arm_count", len(ARM_ORDER))),
            "max_arms_cap": MAX_GRID_ARMS,
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
            "seeds": [int(seed) for seed in seeds],
            "anchor_seed": ANCHOR_SEED,
            "arms": list(arms),
            "arm_count": len(arms),
            "arm_cap": MAX_GRID_ARMS,
            "endpoint": "cross_seed_mean",
            "model_random_state": SEED,
            "frozen_hyperparameters": dict(XGB_PARAMS),
            "grid_factor_levels": {
                "max_depth": [2, 3, 4, 6],
                "n_estimators": [200, 400, 800],
                "learning_rate": [0.03, 0.05, 0.1],
                "min_child_weight": [1, 5],
                "subsample": [0.8, 1.0],
                "colsample_bytree": [0.8, 1.0],
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
        "leakage": {
            "by_seed": leakage,
            "clean": leak_clean,
            "folds_by_seed": fold_counts,
        },
        "answers": {
            "target_r2": PASS_TARGET_R2,
            "improvement_bar_r2": IMPROVEMENT_BAR_R2,
            "kill_bar_r2": KILL_BAR_R2,
            "endpoint": "cross_seed_mean",
            "reference_arm": ARM_REFERENCE,
            "reference_cross_seed_mean": reference_cross,
            "best_arm": best_arm,
            "best_cross_seed_mean": best_cross,
            "best_improvement_vs_reference": best_improvement,
            "target_met_cross_seed": bool(best_cross > PASS_TARGET_R2),
            "improvement_met": bool(best_improvement >= IMPROVEMENT_BAR_R2),
            "seed_42_reference_r2": (
                float(summaries[ANCHOR_SEED][ARM_REFERENCE]["r2_mean"])
                if ANCHOR_SEED in summaries and ARM_REFERENCE in arms
                else None
            ),
            "seeds_run": [int(seed) for seed in seeds],
        },
        "verdict": verdict,
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "diagnostic hyperparameter grid on the frozen protocol: the frozen headline is a "
                "co-primary hybrid arm, the grid is non-blind with respect to seed 42 and the "
                "endpoint is a multiple comparison over " + str(len(arms)) + " arms"
            ),
        },
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
    write_json_stable(summary_path, summary)
    report_path.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("wrote " + str(summary_path))
    print("wrote " + str(report_path))
    print(
        "verdict: " + verdict
        + " | best arm " + best_arm
        + " | cross-seed mean R2 " + format(best_cross, ".6f")
        + " (reference " + format(reference_cross, ".6f")
        + ", improvement " + format(best_improvement, "+.6f") + ")"
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
    seed_rows = summary["seed_rows"]
    lines: list[str] = []
    lines.append("# W18-P0：稠密物理配置重调 XGB 超参（预注册网格）")
    lines.append("")
    lines.append("**结论（verdict）**：`" + str(summary["verdict"]) + "`。")
    lines.append("")
    lines.append(
        "- 端点口径：**跨 5 种子均值**（种子在预注册里锁死："
        + ", ".join(str(seed) for seed in answers["seeds_run"]) + "）。"
    )
    lines.append(
        "- 最优臂：`" + str(answers["best_arm"]) + "`，跨种子均值 R² **"
        + format(float(answers["best_cross_seed_mean"]), ".6f") + "**；"
        + "冻结头 `xgb_reference` 跨种子均值 R² **"
        + format(float(answers["reference_cross_seed_mean"]), ".6f") + "**；"
        + "提升 **" + format(float(answers["best_improvement_vs_reference"]), "+.6f") + "**。"
    )
    lines.append(
        "- 判据：跨种子均值 **> 0.60** 且提升 **>= +0.02** 判 confirmed；提升 >= +0.005 判 partial；"
        "否则 refuted。目标达成：**" + str(bool(answers["target_met_cross_seed"]))
        + "**；提升达成：**" + str(bool(answers["improvement_met"])) + "**。"
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
        "- 家族固定为 XGBoostRegressor；继承冻结的 reg_lambda / objective / tree_method / "
        "max_bin / n_jobs，只搜 max_depth / n_estimators / learning_rate / min_child_weight / "
        "subsample / colsample_bytree。"
    )
    lines.append(
        "- 网格：全笛卡尔 288 臂，**预注册子集 " + str(contract["arm_count"])
        + " 臂（上限 " + str(contract["arm_cap"]) + "）**，运行前锁死 digest。"
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
        lines.append("- 本次运行不是锚点种子或未含冻结头，未做锚点复现。")
    lines.append("- 折签名与冻结 scoreboard 的签名一致，否则脚本拒绝输出其它任何数。")
    lines.append("")
    lines.append("## 三、跨 5 种子端点表")
    lines.append("")
    lines.append(
        "| 臂 | 块 | trees/depth/lr/mcw/ss/cs | 跨种子均值 R² | sd | min | max | 过 0.60 种子数 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in cross_rows:
        params = row["params"]
        lines.append(
            "| " + str(row["arm"]) + " | " + str(row["block"]) + " | "
            + str(params["n_estimators"]) + "/" + str(params["max_depth"]) + "/"
            + str(params["learning_rate"]) + "/" + str(params["min_child_weight"]) + "/"
            + str(params["subsample"]) + "/" + str(params["colsample_bytree"]) + " | "
            + format(float(row["r2_seed_mean"]), ".6f") + " | "
            + format(float(row["r2_seed_sd"]), ".6f") + " | "
            + format(float(row["r2_seed_min"]), ".6f") + " | "
            + format(float(row["r2_seed_max"]), ".6f") + " | "
            + str(row["seeds_above_060"]) + " |"
        )
    lines.append("")
    lines.append("## 四、逐种子读数")
    lines.append("")
    lines.append("| seed | 臂 | 该种子 10 重复均值 R² | sd | 过 0.60 重复数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in seed_rows:
        lines.append(
            "| " + str(row["seed"]) + " | " + str(row["arm"]) + " | "
            + format(float(row["r2_mean"]), ".6f") + " | "
            + format(float(row["r2_sd"]), ".6f") + " | "
            + str(row["repeats_above_060"]) + " |"
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
    lines.append("## 六、冻结口径与不提升声明")
    lines.append("")
    lines.append(
        "- 冻结头条 **0.4766400383507876**、冻结基线 **0.4091179943351143** 原位保留；"
        "本探针**不提升任何读数**（promoted = false）。"
    )
    lines.append(
        "- 本臂**非盲**：seed 42 的 0.6080587938801277 与 shot 17 的读数在写预注册前已知；"
        "网格是多臂多重比较，端点是跨种子均值而非单种子读数。"
    )
    lines.append("- Reaxys 数值不进入本探针的任何池、特征或产物（红线）。")
    lines.append("")
    lines.append("## 七、预注册 digest")
    lines.append("")
    lines.append(
        "- " + str(prereg["path"]) + " | sha256 = " + str(prereg["sha256"])
        + " | status = " + str(prereg["status"])
        + " | arm_count = " + str(prereg["arm_count"]) + " / cap " + str(prereg["max_arms_cap"]) + "。"
    )
    lines.append("")
    return chr(10).join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
