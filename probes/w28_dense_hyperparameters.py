"""W28 -- retuning the dense-block XGB hyperparameters, pre-registered before the run.

Week 27 gave the frozen scoreboard a clean negative and, more usefully, a measurement
of the capacity penalty: appending thirteen response columns to the 13-column dense
lever-4 physical block cost 0.096956 in R2, but a row-shuffled block of the same width
still cost 0.006099, i.e. more than the 0.005 inert line.  That residual cannot be
information loss; it is the fit reacting to width.  The frozen hyperparameters
(max_depth 2, 200 trees, lr 0.05, max_bin 64) were chosen for a 2048-column sparse
Morgan fingerprint, and two levels of depth is four leaves per tree.

This probe asks one pre-registered question on the frozen main scoreboard pool
(2029 base training rows / 457 scored rows over 97 compounds, GroupKFold by InChIKey):
does selecting the XGB hyperparameters inside each outer fold, on the training rows of
that fold only, lift the single-representation Physical endpoint that has sat at
0.5861142332208197 since Week 18?

Design, frozen before the production run:

* the pool, the score mask, the train mask, the group splitter and the five-seed set are
  the frozen ones; the fitter is the frozen XGBoost estimator with the frozen
  random_state (42) -- only the three hyperparameters in the grid move;
* selection is nested: inside every outer fold the training rows are split by compound
  into three inner folds, each grid point is scored by the R2 pooled over the three
  inner holdouts, and the winner is refit on the whole outer training set.  The outer
  test rows are never seen by the selection, so the outer reading stays honest;
* ties break to the earliest grid entry, so the procedure is deterministic;
* the four arms are paired on identical folds: frozen, retuned, and the Week 27 response
  block under both settings.  The response arm answers the question Week 27 could not:
  once width is priced correctly, is the response block still harmful?

Run:
    .venv/Scripts/python.exe probes/w28_dense_hyperparameters.py --jobs 12
    .venv/Scripts/python.exe probes/w28_dense_hyperparameters.py --stage smoke --jobs 8
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_pool_expansion_benchmark as bn
import dielectric_representation_seed_robustness as sr
import numpy as np
import w27_dielectric_response as w27
from dielectric_representation_ablation import SEED as FIT_SEED
from dielectric_representation_ablation import XGB_PARAMS, evaluate_repeat
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w28_dense_hyperparameters_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w28_dense_hyperparameters_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w28_dense_hyperparameters.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
SELECTION_CSV = ARTIFACTS_DIR / "w28_dense_hyperparameters_selection.csv"
REPEATS_CSV = ARTIFACTS_DIR / "w28_dense_hyperparameters_repeats.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w28_dense_hyperparameters.png"

SCHEMA = "w28_dense_hyperparameters/summary@1"
TASK = "week28_dense_hyperparameters"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED = 0.5861142332208197
REPRODUCTION_TOLERANCE = 1e-09
GATE_R2 = 0.60

INNER_SPLITS = 3
PLACEBO_RNG_SEED = 2026
PLACEBO_SEEDS = (ANCHOR_SEED,)
CONTROL_SEED = ANCHOR_SEED
CONTROL_REPEATS = (0,)

SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97

ARM_FROZEN = "lever4_physical_frozen"
ARM_RETUNED = "lever4_physical_retuned"
ARM_RESPONSE_FROZEN = "lever4_plus_response_frozen"
ARM_RESPONSE_RETUNED = "lever4_plus_response_retuned"
ARM_PLACEBO = "lever4_physical_retuned_shuffled_target"
ARM_MORGAN_CONTROL = "lever4_morgan_retuned"
ARM_MORGAN_FROZEN = "lever4_morgan_frozen"
LADDER_ARM_PREFIX = "grid_fixed_"
ARM_LADDER = "lever4_physical_grid_ladder"

SCOREBOARD_SHOTS_THIS_WEEK = 2
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 15

#: W27 shipped this reading on disk; the frozen response arm here has to reproduce it.
#: That is a second, independent check that this probe fold path equals the W27 one.
W27_PHYSICAL_BLOCK_MEAN = 0.5003081615487617

SELECTION_COLUMNS = ("arm", "seed", "repeat", "fold", "selected_index", "selected_label",
                     "selected_max_depth", "selected_n_estimators", "selected_learning_rate",
                     "inner_best_r2", "inner_frozen_r2", "train_rows", "test_rows")

CLAIM = ("给稠密 13 列物理块重调 XGB 超参（内层折选择、折不动），单表示 Physical 的"
         "五种子端点是否能从 0.5861142332208197 上升，并越过 0.60")

#: The frozen configuration is grid entry 0, so the anchor arm and the control live in
#: the same code path: the frozen arm is the retuned procedure with the search
#: switched off.  Entry labels are frozen; the guard test re-reads them.
GRID = (
    ("frozen_d2_n200_lr05", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05}),
    ("deep_d3_n200_lr05", {"max_depth": 3, "n_estimators": 200, "learning_rate": 0.05}),
    ("deep_d4_n200_lr05", {"max_depth": 4, "n_estimators": 200, "learning_rate": 0.05}),
    ("deep_d3_n400_lr05", {"max_depth": 3, "n_estimators": 400, "learning_rate": 0.05}),
    ("deep_d4_n400_lr05", {"max_depth": 4, "n_estimators": 400, "learning_rate": 0.05}),
    ("slow_d2_n400_lr02", {"max_depth": 2, "n_estimators": 400, "learning_rate": 0.02}),
)
FROZEN_INDEX = 0
DEPTHS_IN_GRID = tuple(int(entry[1]["max_depth"]) for entry in GRID)
PASS_DEPTH_BAR = 2
MIN_SEEDS_WITH_A_DEEP_MODE = 4


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(["" if value is None else value for value in row])


def dump_json(path: Path, payload: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def params_for(index: int) -> dict:
    """The frozen estimator with exactly the three grid keys overridden."""

    overrides = dict(GRID[index][1])
    return {**XGB_PARAMS, **overrides, "random_state": FIT_SEED}


def grid_label(index: int) -> str:
    return str(GRID[index][0])


def _fit_predict(features, target, train, test, params) -> np.ndarray:
    """The frozen fitter: same estimator, same clamp, same fixed random_state."""

    model = XGBRegressor(**params)
    model.fit(features[train], target[train])
    return np.maximum(model.predict(features[test]), 1.0)


def inner_folds(train: np.ndarray, groups: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Three compound-grouped inner folds over the training rows of one outer fold.

    GroupKFold is deterministic and needs no seed: the split is a function of the
    compound sizes alone, so the selection cannot drift between runs.
    """

    sub = np.asarray(groups)[train]
    if np.unique(sub).size < INNER_SPLITS:
        raise ValueError("an outer fold has fewer training compounds than inner folds")
    splitter = GroupKFold(n_splits=INNER_SPLITS)
    placeholder = np.zeros((train.size, 1))
    folds = []
    for inner_train, inner_test in splitter.split(placeholder, groups=sub):
        if inner_test.size == 0 or inner_train.size == 0:
            raise ValueError("GroupKFold produced an empty inner fold")
        folds.append((train[inner_train], train[inner_test]))
    return folds


_FOLD_STATE: dict[str, object] = {}


def _init_fold_worker(features, target, groups, mode) -> None:
    _FOLD_STATE["features"] = features
    _FOLD_STATE["target"] = target
    _FOLD_STATE["groups"] = np.asarray(groups)
    _FOLD_STATE["mode"] = str(mode)


def select_index(features, target, groups, train, shuffle_rng):
    """Nested selection: pooled inner-holdout R2 for every grid entry.

    Returns the winner, the vector of inner scores and the target vector the fit
    must use -- the shuffled one on the placebo arm, the real one everywhere else.
    Ties go to the earliest grid entry, which keeps the procedure deterministic.
    """

    folds = inner_folds(train, groups)
    y_used = target
    if shuffle_rng is not None:
        y_used = target.copy()
        y_used[train] = target[train][shuffle_rng.permutation(train.size)]
    scores = []
    for index in range(len(GRID)):
        params = params_for(index)
        stacked_target = []
        stacked_prediction = []
        for inner_train, inner_test in folds:
            prediction = _fit_predict(features, y_used, inner_train, inner_test, params)
            stacked_target.append(y_used[inner_test])
            stacked_prediction.append(prediction)
        scores.append(float(r2_score(np.concatenate(stacked_target),
                                    np.concatenate(stacked_prediction))))
    best = int(np.argmax(scores))
    return best, scores, y_used


def _fold_task(task):
    repeat, fold, train_index, test_index = task
    features = _FOLD_STATE["features"]
    target = _FOLD_STATE["target"]
    groups = _FOLD_STATE["groups"]
    mode = str(_FOLD_STATE["mode"])
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(groups, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    scores: list[float] = []
    if mode in ("retuned", "retuned_shuffled"):
        rng = None
        if mode == "retuned_shuffled":
            rng = np.random.default_rng([PLACEBO_RNG_SEED, int(repeat), int(fold)])
        best, scores, y_used = select_index(features, target, groups, train, rng)
    else:
        best, y_used = FROZEN_INDEX, target
    params = params_for(best)
    prediction = _fit_predict(features, y_used, train, test, params)
    return (int(repeat), int(fold), [int(index) for index in train],
            [int(index) for index in test], [float(value) for value in prediction],
            int(best), [float(value) for value in scores])


def parallel_map(function, tasks, jobs: int, *, initargs=()) -> list:
    if jobs <= 1 or len(tasks) <= 1:
        _init_fold_worker(*initargs)
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_fold_worker,
                             initargs=initargs) as pool:
        return list(pool.map(function, tasks))


def _ladder_task(task):
    """One fold, every grid entry fit once.

    The ladder is a fixed-configuration sweep, not a search: nothing in it looks
    at a test row to choose anything, so every entry is an honest reading and the
    ladder answers "is there a better fixed setting" separately from "can the
    inner selection find it".
    """

    repeat, fold, train_index, test_index = task
    features = _FOLD_STATE["features"]
    target = _FOLD_STATE["target"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    predictions: dict[str, list[float]] = {}
    for index in range(len(GRID)):
        prediction = _fit_predict(features, target, train, test, params_for(index))
        predictions[grid_label(index)] = [float(value) for value in prediction]
    return (int(repeat), int(fold), [int(index) for index in train],
            [int(index) for index in test], predictions)


def evaluate_ladder(features, splits, context, jobs) -> dict[str, object]:
    """Every fixed grid entry, scored on the frozen folds, in one pass."""

    groups = [str(item) for item in context["groups"]]
    group_array = np.asarray(groups)
    target = np.asarray(context["target"], dtype=float)
    tasks = [(repeat, fold, [int(index) for index in train], [int(index) for index in test])
             for repeat, fold, train, test in splits]
    clock = time.perf_counter()
    raw = parallel_map(_ladder_task, tasks, jobs,
                       initargs=(features, target, group_array, "ladder"))
    seconds = time.perf_counter() - clock
    entries = [grid_label(index) for index in range(len(GRID))]
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    for repeat, fold, train_index, test_index, predictions in raw:
        for entry in entries:
            bucket = buckets.setdefault((entry, int(repeat)), {"target": [], "prediction": []})
            bucket["target"].append(target[np.asarray(test_index)])
            bucket["prediction"].append(np.asarray(predictions[entry], dtype=float))
    repeat_rows: list[dict[str, object]] = []
    for (entry, repeat), bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(np.concatenate(bucket["target"]),
                                  np.concatenate(bucket["prediction"]))
        repeat_rows.append({"arm": LADDER_ARM_PREFIX + entry,
                            "seed": int(context["seed"]), "repeat": int(repeat),
                            **{metric: float(metrics[metric]) for metric in METRIC_COLUMNS}})
    per_entry: dict[str, object] = {}
    for entry in entries:
        rows = [row for row in repeat_rows if row["arm"] == LADDER_ARM_PREFIX + entry]
        per_entry[entry] = {"r2_mean": mean_metric(rows, "r2"),
                            "spearman_mean": mean_metric(rows, "spearman"),
                            "auc_gt30_mean": mean_metric(rows, "auc_gt30"),
                            "repeats": len(rows)}
    return {"repeat_rows": repeat_rows, "per_entry": per_entry, "seconds": seconds}


METRIC_COLUMNS = ("r2", "mae", "rmse", "spearman", "auc_gt15", "auc_gt30",
                  "mae_lt20", "mae_20_60", "mae_gt60")
REPEAT_COLUMNS = ("seed", "arm", "repeat", *METRIC_COLUMNS)

ARM_SPECS = (
    (ARM_FROZEN, "physical", "frozen"),
    (ARM_RETUNED, "physical", "retuned"),
    (ARM_RESPONSE_FROZEN, "response", "frozen"),
    (ARM_RESPONSE_RETUNED, "response", "retuned"),
)
PLACEBO_SPEC = (ARM_PLACEBO, "physical", "retuned_shuffled")
CONTROL_SPEC = (ARM_MORGAN_CONTROL, "morgan", "retuned")
def arm_features(arm: str, context: Mapping[str, object], response: np.ndarray) -> np.ndarray:
    physical = np.asarray(context["physical_lever4"], dtype=float)
    if arm in (ARM_FROZEN, ARM_RETUNED, ARM_PLACEBO, ARM_LADDER):
        return physical
    if arm in (ARM_RESPONSE_FROZEN, ARM_RESPONSE_RETUNED):
        return np.hstack([physical, response])
    if arm in (ARM_MORGAN_CONTROL, ARM_MORGAN_FROZEN):
        return np.asarray(context["morgan"], dtype=float)
    raise ValueError("unknown arm: " + str(arm))


def mean_metric(rows, key: str) -> float:
    values = [float(str(row[key])) for row in rows if row.get(key) is not None]
    return float(np.mean(values)) if values else float("nan")
def evaluate_arm(name, features, mode, splits, context, jobs) -> dict[str, object]:
    """One arm: every fold through the frozen fitter, pooled per repeat."""
    groups = [str(item) for item in context["groups"]]
    group_array = np.asarray(groups)
    target = np.asarray(context["target"], dtype=float)
    tasks = [(repeat, fold, [int(index) for index in train], [int(index) for index in test])
             for repeat, fold, train, test in splits]
    clock = time.perf_counter()
    raw = parallel_map(_fold_task, tasks, jobs,
                       initargs=(features, target, group_array, mode))
    seconds = time.perf_counter() - clock
    buckets: dict[int, dict[str, list[np.ndarray]]] = {}
    selection_rows: list[dict[str, object]] = []
    straddling: list[int] = []
    for repeat, fold, train_index, test_index, predictions, best, scores in raw:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(group_array[train], group_array[test]).size))
        bucket = buckets.setdefault(int(repeat), {"target": [], "prediction": []})
        bucket["target"].append(target[test])
        bucket["prediction"].append(np.asarray(predictions, dtype=float))
        if scores:
            overrides = dict(GRID[int(best)][1])
            selection_rows.append({
                "arm": name,
                "seed": int(context.get("seed", 0)),
                "repeat": int(repeat),
                "fold": int(fold),
                "selected_index": int(best),
                "selected_label": grid_label(int(best)),
                "selected_max_depth": int(overrides["max_depth"]),
                "selected_n_estimators": int(overrides["n_estimators"]),
                "selected_learning_rate": float(overrides["learning_rate"]),
                "inner_best_r2": float(max(scores)),
                "inner_frozen_r2": float(scores[FROZEN_INDEX]),
                "train_rows": int(train.size),
                "test_rows": int(test.size),
            })
    repeat_rows: list[dict[str, object]] = []
    for repeat, bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(np.concatenate(bucket["target"]),
                                  np.concatenate(bucket["prediction"]))
        repeat_rows.append({"arm": name, "repeat": repeat,
                            **{metric: float(metrics[metric]) for metric in METRIC_COLUMNS}})
    return {
        "repeat_rows": repeat_rows,
        "selection_rows": selection_rows,
        "r2_mean": mean_metric(repeat_rows, "r2"),
        "spearman_mean": mean_metric(repeat_rows, "spearman"),
        "auc_gt30_mean": mean_metric(repeat_rows, "auc_gt30"),
        "mae_mean": mean_metric(repeat_rows, "mae"),
        "repeats": len(repeat_rows),
        "seconds": seconds,
        "leak": {
            "folds": len(straddling),
            "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
            "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
        },
    }


def splits_for_seed(seed: int, context):
    groups = [str(item) for item in context["groups"]]
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    return sr.splits_for(seed, groups, scored, full_base)


def build_verdict(identifier, description, value, threshold, passed) -> dict[str, object]:
    return {
        "id": str(identifier),
        "description": str(description),
        "value": None if value is None else float(value),
        "threshold": None if threshold is None else float(threshold),
        "verdict": "成立" if bool(passed) else "判否",
    }
def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--stage", default="full", choices=("smoke", "anchor", "full"))
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in SEEDS))
    return parser.parse_args(argv)


def parse_seeds(text) -> tuple[int, ...]:
    values = []
    for part in str(text).split(","):
        if part.strip():
            values.append(int(part.strip()))
    if not values:
        raise ValueError("no seeds")
    return tuple(values)


def schedule(stage: str, seeds: Sequence[int]):
    """Which (arm, mode, feature key, seed, repeat filter) the stage runs."""

    plan = []
    if stage == "anchor":
        for seed in seeds:
            plan.append((ARM_FROZEN, "frozen", "physical", int(seed), None))
        return plan
    repeats = (0,) if stage == "smoke" else None
    for seed in seeds:
        for arm, key, mode in ARM_SPECS:
            plan.append((arm, mode, key, int(seed), repeats))
    for seed in seeds:
        plan.append((ARM_LADDER, "ladder", "physical", int(seed), repeats))
    for seed in PLACEBO_SEEDS:
        plan.append((ARM_PLACEBO, PLACEBO_SPEC[2], "physical", int(seed), repeats))
    plan.append((ARM_MORGAN_FROZEN, "frozen", "morgan", CONTROL_SEED, CONTROL_REPEATS))
    plan.append((ARM_MORGAN_CONTROL, CONTROL_SPEC[2], "morgan", CONTROL_SEED,
                 CONTROL_REPEATS))
    return plan


def selector_summary(selection_rows, seeds) -> dict[str, object]:
    """Per-seed modal selected depth and the depth histogram of the search."""

    per_seed: dict[str, object] = {}
    histogram: dict[str, int] = {}
    for row in selection_rows:
        depth = int(row["selected_max_depth"])
        histogram[str(depth)] = histogram.get(str(depth), 0) + 1
        per_seed.setdefault(str(row["seed"]), {})
    for seed in seeds:
        key = str(int(seed))
        depths = [int(row["selected_max_depth"]) for row in selection_rows
                  if int(row["seed"]) == int(seed)]
        counts: dict[int, int] = {}
        for depth in depths:
            counts[depth] = counts.get(depth, 0) + 1
        modal = None
        if counts:
            best_count = max(counts.values())
            modal = min(depth for depth, count in counts.items() if count == best_count)
        per_seed[key] = {
            "folds_judged": len(depths),
            "modal_depth": modal,
            "depth_counts": {str(depth): counts[depth] for depth in sorted(counts)},
            "share_deeper_than_two": (sum(count for depth, count in counts.items() if depth > 2)
                                      / float(len(depths))) if depths else None,
        }
    return {"per_seed": per_seed, "depth_histogram": histogram}


def cross_seed_mean(cache, arm: str, seeds: Sequence[int], key: str = "r2_mean") -> float:
    values = [float(cache[(arm, int(seed))][key]) for seed in seeds
              if (arm, int(seed)) in cache]
    return float(np.mean(values)) if values else float("nan")


def per_seed_table(cache, arm: str, seeds: Sequence[int]) -> dict[str, object]:
    table: dict[str, object] = {}
    for seed in seeds:
        entry = cache.get((arm, int(seed)))
        if entry is None:
            continue
        table[str(int(seed))] = {
            "r2": float(entry["r2_mean"]),
            "spearman": float(entry["spearman_mean"]),
            "auc_gt30": float(entry["auc_gt30_mean"]),
            "mae": float(entry["mae_mean"]),
            "repeats": int(entry["repeats"]),
            "seconds": float(entry["seconds"]),
            "leak": dict(entry["leak"]),
        }
    return table


def build_verdicts(readings) -> list[dict[str, object]]:
    """The eight verdicts, each against a bar frozen before the production run."""

    verdicts = [
        build_verdict("H28a", "复现锚：seed 42 的 Physical 单表示逐位复现冻结值",
                      readings["anchor_seed42_gap"], REPRODUCTION_TOLERANCE,
                      bool(readings["anchor_seed42_gap"] is not None
                           and readings["anchor_seed42_gap"] <= REPRODUCTION_TOLERANCE)),
        build_verdict("H28b", "复现锚：五种子端点逐位复现冻结值",
                      readings["anchor_cross_seed_gap"], REPRODUCTION_TOLERANCE,
                      bool(readings["anchor_cross_seed_gap"] is not None
                           and readings["anchor_cross_seed_gap"] <= REPRODUCTION_TOLERANCE)),
        build_verdict("H28c", "跨折泄漏：含跨界化合物的折数（全部臂与种子）",
                      float(readings["leak_folds"]), 0.0,
                      bool(readings["leak_folds"] == 0)),
        build_verdict("H28d", "端点升级：重调臂五种子均值减去冻结臂五种子均值 > 0",
                      readings["retune_delta"], 0.0,
                      bool(np.isfinite(readings["retune_delta"])
                           and readings["retune_delta"] > 0.0)),
        build_verdict("H28e", "过门：重调臂五种子均值 >= 0.60",
                      readings["retuned_mean"], GATE_R2,
                      bool(np.isfinite(readings["retuned_mean"])
                           and readings["retuned_mean"] >= GATE_R2)),
        build_verdict("H28f", "安慰剂塌缩：重调 + 打乱训练靶值的 seed 42 读数 <= 0.00",
                      readings["placebo_mean"], 0.0,
                      bool(readings["placebo_mean"] is not None
                           and readings["placebo_mean"] <= 0.0)),
        build_verdict("H28g", "机制预测：>= 4/5 种子上被选中次数最多的深度 > 2",
                      readings["seeds_with_a_deep_mode"], MIN_SEEDS_WITH_A_DEEP_MODE,
                      bool(readings["seeds_with_a_deep_mode"] >= MIN_SEEDS_WITH_A_DEEP_MODE)),
        build_verdict("H28h", "同容量响应块净效应：重调(物理+响应) 减 重调(物理) > 0",
                      readings["response_delta_retuned"], 0.0,
                      bool(np.isfinite(readings["response_delta_retuned"])
                           and readings["response_delta_retuned"] > 0.0)),
        build_verdict("H28i", "交叉验证：冻结(物理+响应) 复现 W27 的 Physical 读数",
                      readings["w27_gap"], 1e-06,
                      bool(readings["w27_gap"] is not None and readings["w27_gap"] <= 1e-06)),
        build_verdict("H28j", "固定档位阶梯：最佳档位的五种子均值高于冻结臂",
                      readings["ladder_delta"], 0.0,
                      bool(readings["ladder_delta"] is not None and readings["ladder_delta"] > 0.0)),
        build_verdict("H28k", "固定档位阶梯过门：最佳档位的五种子均值 >= 0.60",
                      readings["ladder_best_mean"], GATE_R2,
                      bool(readings["ladder_best_mean"] is not None
                           and readings["ladder_best_mean"] >= GATE_R2)),
    ]
    return verdicts


def build_notes(readings) -> list[str]:
    return [
        "池、评分掩码、训练掩码、分组切分器与五种子集合逐字复用冻结主记分牌；拟合器是冻结的 XGBoost 估计器（random_state 固定为 " + str(FIT_SEED) + "），本枪只移动网格里的三个超参。",
        "选择是嵌套的：每个外层折内部按化合物把训练行切成 " + str(INNER_SPLITS) + " 个内层折，网格每一档用三个内层留出的合并 R2 打分，赢家在全外层训练集上重拟合；外层测试行从未被选择过程看到。",
        "平局取网格里更早的一档（np.argmax 的语义），因此整个过程确定可复现；内层折用 GroupKFold，无随机性。",
        "安慰剂只打乱外层折内的训练靶值（生成器种子在预注册里冻结为 " + str(PLACEBO_RNG_SEED) + "），测试靶值保持真实，因此重调过程的读数是真靶值上的读数。",
        "本枪不新增量子化学、不装依赖、不联网；响应块由盘上已有的 W26 产物派生，与 W27 用的是同一块。",
        "主记分牌 shot = " + str(SCOREBOARD_SHOTS_THIS_WEEK) + "（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）；四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。",
        "重调只解决容量口径，不改变任务：本枪不外推到别的名册，也不宣称稠密块本身有上限。",
    ]


def tick(text) -> str:
    character = chr(96)
    return character + str(text) + character


def fmt(value, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    if not np.isfinite(number):
        return "n/a"
    return format(number, "." + str(int(digits)) + "f")


def configure_fonts():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def render_figure(summary) -> bool:
    try:
        plt = configure_fonts()
    except Exception as error:
        print("font setup failed: " + type(error).__name__, flush=True)
        return False
    try:
        seeds = [int(seed) for seed in summary["per_seed"]]
        frozen = [summary["per_seed"][str(seed)]["frozen"] for seed in seeds]
        retuned = [summary["per_seed"][str(seed)]["retuned"] for seed in seeds]
        response = [summary["per_seed"][str(seed)]["response_retuned"] for seed in seeds]
        figure, axes = plt.subplots(1, 2, figsize=(12.8, 4.8))
        positions = np.arange(len(seeds), dtype=float)
        width = 0.27
        axes[0].bar(positions - width, frozen, width, label="冻结超参", color="#1f3b63")
        axes[0].bar(positions, retuned, width, label="重调（Physical）", color="#c0392b")
        axes[0].bar(positions + width, response, width,
                    label="重调（Physical+响应块）", color="#e67e22")
        axes[0].axhline(GATE_R2, color="#7f8c8d", linestyle="--", linewidth=1.0,
                        label="0.60 门线")
        axes[0].axhline(FROZEN_CROSS_SEED, color="#16a085", linestyle=":", linewidth=1.0,
                        label="冻结端点 0.5861")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels([str(seed) for seed in seeds])
        axes[0].set_xlabel("折随机种子")
        axes[0].set_ylabel("Physical 单表示 R²（10 次重复均值）")
        axes[0].set_title("A 逐种子读数（配对同折）")
        axes[0].legend(fontsize=7)
        axes[0].grid(alpha=0.25, axis="y")
        depths = sorted(int(depth) for depth in summary["selection"]["depth_histogram"])
        for offset, seed in enumerate(seeds):
            counts = summary["selection"]["per_seed"][str(seed)]["depth_counts"]
            heights = [int(counts.get(str(depth), 0)) for depth in depths]
            axes[1].bar([position + offset * 0.16 for position in depths], heights, 0.16,
                        label="seed " + str(seed))
        axes[1].axvline(2.0, color="#7f8c8d", linestyle="--", linewidth=1.0,
                        label="冻结深度 2")
        axes[1].set_xticks(depths)
        axes[1].set_xlabel("内层选择选中的 max_depth")
        axes[1].set_ylabel("命中折数")
        axes[1].set_title("B 内层折选出的深度分布")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.25, axis="y")
        figure.suptitle("W28 稠密块超参重调：五种子配对读数（shot = 2，累计 15）",
                        fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:
        print("figure failure: " + type(error).__name__ + ": " + str(error), flush=True)
        plt.close("all")
        return False


def format_report(summary) -> str:
    lines: list[str] = []
    lines.append("# W28 结题报告：稠密块 XGB 超参的嵌套重调")
    lines.append("")
    lines.append("- 预注册 " + tick("probes/w28_dense_hyperparameters_prereg.json")
                 + "（status = locked_before_run）")
    lines.append("- 臂：" + tick(ARM_FROZEN) + " 对 " + tick(ARM_RETUNED)
                 + "，另有 " + tick(ARM_RESPONSE_FROZEN) + " / " + tick(ARM_RESPONSE_RETUNED))
    lines.append("- 池：冻结主记分牌池，评分 " + str(SCOREBOARD_ROWS) + " 行 / "
                 + str(SCOREBOARD_COMPOUNDS) + " 化合物；训练掩码 full_base")
    lines.append("- 主记分牌 shot：" + str(SCOREBOARD_SHOTS_THIS_WEEK) + "（累计 "
                 + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）")
    lines.append("")
    lines.append("## 1. 裁决表")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for entry in summary["verdicts"]:
        lines.append("| " + str(entry["id"]) + " " + str(entry["description"]) + " | "
                     + fmt(entry["value"]) + " | " + fmt(entry["threshold"]) + " | "
                     + str(entry["verdict"]) + " |")
    lines.append("")
    lines.append("## 2. 读数（Physical 单表示，10 次重复均值，五种子配对同折）")
    lines.append("")
    lines.append("| 种子 | 冻结 | 重调 | 重调-冻结 | 冻结(物理+响应) | 重调(物理+响应) |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for seed in sorted(summary["per_seed"], key=lambda item: int(item)):
        row = summary["per_seed"][seed]
        lines.append("| " + str(seed) + " | " + fmt(row["frozen"]) + " | "
                     + fmt(row["retuned"]) + " | " + fmt(row["retuned_delta"]) + " | "
                     + fmt(row["response_frozen"]) + " | " + fmt(row["response_retuned"]) + " |")
    lines.append("| 五种子均值 | " + fmt(summary["cross_seed"]["frozen"]) + " | "
                 + fmt(summary["cross_seed"]["retuned"]) + " | "
                 + fmt(summary["deltas"]["retune"]) + " | "
                 + fmt(summary["cross_seed"]["response_frozen"]) + " | "
                 + fmt(summary["cross_seed"]["response_retuned"]) + " |")
    lines.append("")
    lines.append("## 3. 内层选择读出了什么")
    lines.append("")
    lines.append("| 种子 | 判定折数 | 众数深度 | 深度分布 | 深度大于 2 的占比 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for seed in sorted(summary["selection"]["per_seed"], key=lambda item: int(item)):
        block = summary["selection"]["per_seed"][seed]
        lines.append("| " + str(seed) + " | " + str(block["folds_judged"]) + " | "
                     + str(block["modal_depth"]) + " | "
                     + str(block["depth_counts"]) + " | "
                     + fmt(block["share_deeper_than_two"]) + " |")
    lines.append("")
    lines.append("## 4. 固定档位阶梯（每档在同样的折上各拟合一次，没有任何选择）")
    lines.append("")
    lines.append("| 档位 | 五种子均值 | 与冻结臂之差 |")
    lines.append("| --- | --- | --- |")
    for entry in summary["ladder"]["entries"]:
        value = summary["ladder"]["entries"][entry]
        lines.append("| " + str(entry) + " | " + fmt(value) + " | "
                     + fmt(float(value) - summary["cross_seed"]["frozen"]) + " |")
    lines.append("")
    lines.append("阶梯最佳档位：" + str(summary["ladder"]["best_entry"]) + "（五种子均值 "
                 + fmt(summary["ladder"]["best_mean"]) + "）。")
    lines.append("")
    lines.append("## 5. 安慰剂与对照")
    lines.append("")
    lines.append("- 安慰剂（重调 + 打乱训练靶值，seed 42）：" + fmt(summary["readings"]["placebo_mean"])
                 + "；阈值 <= 0.00")
    lines.append("- Morgan 对照（同一重调过程，seed 42、仅 repeat 0）："
                 + fmt(summary["readings"]["control_mean"]) + "，其冻结同折读数 "
                 + fmt(summary["readings"]["control_frozen_mean"]) + "，增量 "
                 + fmt(summary["readings"]["control_delta"]))
    lines.append("")
    lines.append("## 6. 口径与边界")
    lines.append("")
    for note in summary["notes"]:
        lines.append("- " + str(note))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    jobs = max(1, int(args.jobs))
    stage = str(args.stage)
    seeds = parse_seeds(args.seeds)

    prereg: dict = {}
    if PREREG_PATH.is_file():
        prereg = read_json(PREREG_PATH)
    if stage == "full":
        if not prereg:
            print("MISSING " + str(PREREG_PATH))
            return 1
        if str(prereg.get("status")) != "locked_before_run":
            print("the pre-registration is not locked_before_run")
            return 1

    context = sr.build_context()
    groups = [str(item) for item in context["groups"]]
    scored = np.asarray(context["scored"], dtype=bool)
    print("pool: " + str(len(groups)) + " rows | scored " + str(int(scored.sum()))
          + " rows | physical block " + str(np.asarray(context["physical_lever4"]).shape),
          flush=True)

    block_rows, block_report = w27.build_block()
    pool_rows = [{"inchikey": group} for group in groups]
    response, coverage = w27.response_matrix(pool_rows, block_rows)
    print("response block: " + str(block_report["compounds_in_the_block"]) + " compounds, "
          + str(block_report["compounds_complete"]) + " complete | rows covered "
          + str(coverage["rows_with_the_block"]) + "/" + str(len(pool_rows)), flush=True)

    cache: dict[tuple[str, int], dict] = {}
    ladder_cache: dict[int, dict] = {}
    selection_rows: list[dict[str, object]] = []
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for arm, mode, key, seed, repeats in schedule(stage, seeds):
        splits = splits_for_seed(seed, context)
        if repeats is not None:
            splits = [item for item in splits if int(item[0]) in repeats]
        moved = bn.fold_signature(splits) != bn.fold_signature(context["frozen_splits"])
        if seed == ANCHOR_SEED and repeats is None and moved:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        features = arm_features(arm, context, response)
        scoped = dict(context)
        scoped["seed"] = int(seed)
        if arm == ARM_LADDER:
            ladder = evaluate_ladder(features, splits, scoped, jobs)
            ladder_cache[int(seed)] = ladder
            spreadsheet.extend(dict(row) for row in ladder["repeat_rows"])
            print("  seed " + str(int(seed)) + " | " + arm + " | "
                  + "  ".join(entry + " " + format(ladder["per_entry"][entry]["r2_mean"], ".6f")
                              for entry in [grid_label(index) for index in range(len(GRID))])
                  + "  (" + format(ladder["seconds"], ".1f") + "s)", flush=True)
            continue
        result = evaluate_arm(arm, features, mode, splits, scoped, jobs)
        cache[(arm, int(seed))] = result
        selection_rows.extend(dict(row) for row in result["selection_rows"])
        for row in result["repeat_rows"]:
            spreadsheet.append({"seed": int(seed), **dict(row)})
        leakage[str(int(seed)) + ":" + arm] = dict(result["leak"])
        print("  seed " + str(seed) + " | " + arm + " | " + format(result["r2_mean"], ".6f")
              + "  (" + format(result["seconds"], ".1f") + "s, "
              + str(result["repeats"]) + " repeats)", flush=True)

    if stage in ("smoke", "anchor"):
        print("stage " + stage + " finished in " + format(time.perf_counter() - started, ".1f")
              + "s; no artifact written", flush=True)
        return 0

    frozen_mean = cross_seed_mean(cache, ARM_FROZEN, seeds)
    retuned_mean = cross_seed_mean(cache, ARM_RETUNED, seeds)
    response_frozen_mean = cross_seed_mean(cache, ARM_RESPONSE_FROZEN, seeds)
    response_retuned_mean = cross_seed_mean(cache, ARM_RESPONSE_RETUNED, seeds)
    anchor_seed42 = cache[(ARM_FROZEN, ANCHOR_SEED)]["r2_mean"] if (ARM_FROZEN, ANCHOR_SEED) in cache else None
    anchor_seed42_gap = None if anchor_seed42 is None else abs(float(anchor_seed42) - FROZEN_SINGLE_REPRESENTATION)
    anchor_cross_seed_gap = None
    if all((ARM_FROZEN, int(seed)) in cache for seed in seeds):
        anchor_cross_seed_gap = abs(float(frozen_mean) - FROZEN_CROSS_SEED)
    placebo_mean = None
    if (ARM_PLACEBO, ANCHOR_SEED) in cache:
        placebo_mean = float(cache[(ARM_PLACEBO, ANCHOR_SEED)]["r2_mean"])
    control_mean = None
    if (ARM_MORGAN_CONTROL, CONTROL_SEED) in cache:
        control_mean = float(cache[(ARM_MORGAN_CONTROL, CONTROL_SEED)]["r2_mean"])
    control_frozen_mean = None
    if (ARM_MORGAN_FROZEN, CONTROL_SEED) in cache:
        control_frozen_mean = float(cache[(ARM_MORGAN_FROZEN, CONTROL_SEED)]["r2_mean"])
    control_delta = None
    if control_mean is not None and control_frozen_mean is not None:
        control_delta = control_mean - control_frozen_mean
    leak_folds = sum(int(block["folds_with_a_straddling_compound"]) for block in leakage.values())
    ladder_cross: dict[str, float] = {}
    for index in range(len(GRID)):
        entry = grid_label(index)
        values = [float(ladder_cache[int(seed)]["per_entry"][entry]["r2_mean"])
                  for seed in seeds if int(seed) in ladder_cache]
        ladder_cross[entry] = float(np.mean(values)) if values else float("nan")
    ladder_best_entry = None
    ladder_best_mean = float("nan")
    for entry, value in ladder_cross.items():
        if np.isfinite(value) and (ladder_best_entry is None or value > ladder_best_mean):
            ladder_best_entry, ladder_best_mean = entry, float(value)
    ladder_per_seed: dict[str, object] = {}
    for seed in seeds:
        if int(seed) not in ladder_cache:
            continue
        ladder_per_seed[str(int(seed))] = {
            entry: float(ladder_cache[int(seed)]["per_entry"][entry]["r2_mean"])
            for entry in ladder_cross}
    retune_rows = [row for row in selection_rows if str(row["arm"]) == ARM_RETUNED]
    selection = selector_summary(retune_rows, seeds)
    seeds_with_a_deep_mode = sum(
        1 for seed in seeds
        if int(selection["per_seed"].get(str(int(seed)), {}).get("modal_depth") or 0) > PASS_DEPTH_BAR
    )

    per_seed: dict[str, object] = {}
    for seed in seeds:
        frozen_entry = cache.get((ARM_FROZEN, int(seed)))
        retuned_entry = cache.get((ARM_RETUNED, int(seed)))
        if frozen_entry is None or retuned_entry is None:
            continue
        response_frozen_entry = cache.get((ARM_RESPONSE_FROZEN, int(seed)))
        response_retuned_entry = cache.get((ARM_RESPONSE_RETUNED, int(seed)))
        per_seed[str(int(seed))] = {
            "frozen": float(frozen_entry["r2_mean"]),
            "retuned": float(retuned_entry["r2_mean"]),
            "retuned_delta": float(retuned_entry["r2_mean"]) - float(frozen_entry["r2_mean"]),
            "response_frozen": (float(response_frozen_entry["r2_mean"])
                                if response_frozen_entry else float("nan")),
            "response_retuned": (float(response_retuned_entry["r2_mean"])
                                 if response_retuned_entry else float("nan")),
        }

    readings = {
        "anchor_seed42": None if anchor_seed42 is None else float(anchor_seed42),
        "anchor_seed42_gap": anchor_seed42_gap,
        "anchor_cross_seed_gap": anchor_cross_seed_gap,
        "frozen_mean": float(frozen_mean),
        "retuned_mean": float(retuned_mean),
        "retune_delta": float(retuned_mean) - float(frozen_mean),
        "response_frozen_mean": float(response_frozen_mean),
        "response_retuned_mean": float(response_retuned_mean),
        "response_delta_frozen": float(response_frozen_mean) - float(frozen_mean),
        "response_delta_retuned": float(response_retuned_mean) - float(retuned_mean),
        "placebo_mean": placebo_mean,
        "control_mean": control_mean,
        "control_frozen_mean": control_frozen_mean,
        "control_delta": control_delta,
        "leak_folds": int(leak_folds),
        "seeds_with_a_deep_mode": int(seeds_with_a_deep_mode),
        "w27_expected": W27_PHYSICAL_BLOCK_MEAN,
        "w27_gap": abs(float(response_frozen_mean) - W27_PHYSICAL_BLOCK_MEAN),
        "ladder_best_entry": ladder_best_entry,
        "ladder_best_mean": (None if not np.isfinite(ladder_best_mean)
                             else float(ladder_best_mean)),
        "ladder_delta": (None if not np.isfinite(ladder_best_mean)
                         else float(ladder_best_mean) - float(frozen_mean)),
    }
    verdicts = build_verdicts(readings)
    notes = build_notes(readings)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": time.perf_counter() - started,
        "stage": stage,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(PREREG_PATH),
            "status": str(prereg.get("status")),
            "revision": prereg.get("revision"),
        },
        "claim": CLAIM,
        "pool": {"rows": len(groups), "scored_rows": int(scored.sum()),
                 "scored_compounds": len({group for group, flag in zip(groups, scored) if flag}),
                 "matches_preregistration": bool(int(scored.sum()) == SCOREBOARD_ROWS)},
        "grid": [{"index": index, "label": grid_label(index), **dict(GRID[index][1])}
                 for index in range(len(GRID))],
        "frozen_params": dict(XGB_PARAMS),
        "fit_seed": int(FIT_SEED),
        "inner_splits": int(INNER_SPLITS),
        "seeds": [int(seed) for seed in seeds],
        "per_seed": per_seed,
        "cross_seed": {"frozen": float(frozen_mean), "retuned": float(retuned_mean),
                       "response_frozen": float(response_frozen_mean),
                       "response_retuned": float(response_retuned_mean)},
        "readings": readings,
        "deltas": {"retune": readings["retune_delta"],
                   "response_frozen": readings["response_delta_frozen"],
                   "response_retuned": readings["response_delta_retuned"],
                   "control": control_delta},
        "selection": selection,
        "ladder": {"entries": ladder_cross, "best_entry": ladder_best_entry,
                   "best_mean": readings["ladder_best_mean"], "per_seed": ladder_per_seed},
        "coverage": dict(coverage),
        "block": block_report,
        "leakage": leakage,
        "per_arm": {arm: per_seed_table(cache, arm, seeds) for arm, _key, _mode in ARM_SPECS},
        "verdicts": verdicts,
        "notes": notes,
        "artifacts": {"selection": SELECTION_CSV.name, "repeats": REPEATS_CSV.name},
        "figures": {"main": FIGURE_PATH.name},
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
    }

    write_csv(SELECTION_CSV, SELECTION_COLUMNS,
              [[row.get(column) for column in SELECTION_COLUMNS] for row in selection_rows])
    write_csv(REPEATS_CSV, REPEAT_COLUMNS,
              [[row.get(column) for column in REPEAT_COLUMNS] for row in spreadsheet])
    summary["figures"]["written"] = bool(render_figure(summary))
    report = format_report(summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    dump_json(SUMMARY_PATH, summary)

    for entry in verdicts:
        print("  " + str(entry["id"]) + " " + str(entry["verdict"]) + " "
              + fmt(entry["value"]) + " (阈值 " + fmt(entry["threshold"]) + ")", flush=True)
    print("frozen " + fmt(frozen_mean) + " | retuned " + fmt(retuned_mean)
          + " | delta " + fmt(readings["retune_delta"])
          + " | report " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())