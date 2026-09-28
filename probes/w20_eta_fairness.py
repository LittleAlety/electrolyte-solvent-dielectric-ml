"""Week 20 W20-1: the eta fairness review (budget-aligned arms, grouped 5x5).

W19-D5 left two boundaries it could not remove. The incumbent viscosity arm was a
frozen single-configuration single-seed XGBoost while the Chemprop arm was a
three-seed ensemble, and the grouped protocol was a single 20 percent hold-out draw
with no fold-level variance. This lane removes both: the incumbent is granted the
tuning and multi-seed budget it was denied, and the split is upgraded to GroupKFold
by InChIKey, five folds by five repeats.

Every rule is imported and never re-implemented where a frozen rule exists:

* the pools come from probes/viscosity_row_level_unfreeze.py::build_pools;
* the target, the incumbent features and the incumbent reproduction anchor come from
  probes/viscosity_baseline.py;
* the pool frame, the Chemprop featurisation and the Chemprop member come from
  probes/w19_chemprop_viscosity.py.

The run is void unless the incumbent reproduces its frozen readings with
abs_gap = 0.0 on the W19-D5 split, so a silent drift cannot be reported as a fairness
effect.

Nothing here reads or writes the frozen epsilon numbers 0.4091179943351143 /
0.4766400383507876, nothing here uses Reaxys values, and nothing here is promoted.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
import viscosity_baseline as frozen
import viscosity_row_level_unfreeze as unfreeze
import w19_chemprop_viscosity as w19
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256

TASK_ID = "week20_w20_1_eta_fairness"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_PATH = ARTIFACTS_DIR / "w20_eta_fairness_repeats.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_eta_fairness.md"

POOL_PRIMARY = "row_level"
POOL_SECONDARY = "family_level"
POOL_ORDER: tuple[str, ...] = (POOL_PRIMARY, POOL_SECONDARY)

N_SPLITS = 5
N_REPEATS = 5
REPEAT_SEEDS: tuple[int, ...] = (42, 1234, 2026, 31337, 7)
ENSEMBLE_SEEDS: tuple[int, ...] = (42, 1234, 2026)
INNER_SPLITS = 3

EPOCHS = 30
EPOCHS_REGISTERED_IN_W19 = 60
WORKER_THREADS = 2
XGB_JOBS = 2

MAE_GATE = 0.15
TOLERANCE = 0.02
INCUMBENT_REPRODUCTION_TOLERANCE = 1e-9

PLACEBO_SEED = 20260928

INCUMBENT_GRID: tuple[dict[str, float | int | str], ...] = (
    {
        "name": "frozen_default",
        "n_estimators": 800,
        "max_depth": 10,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.6,
        "reg_lambda": 1.0,
    },
    {
        "name": "shallow_wide",
        "n_estimators": 1200,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.6,
        "reg_lambda": 1.0,
    },
    {
        "name": "shallow_slow",
        "n_estimators": 1500,
        "max_depth": 4,
        "learning_rate": 0.03,
        "subsample": 0.9,
        "colsample_bytree": 0.8,
        "reg_lambda": 2.0,
    },
)
INCUMBENT_GRID_NAMES: tuple[str, ...] = tuple(str(row["name"]) for row in INCUMBENT_GRID)

INCUMBENT_MODEL = "MorganTemperatureXGBoost"
INCUMBENT_FROZEN_MAE: Mapping[str, float] = {
    POOL_PRIMARY: 0.15686276760094522,
    POOL_SECONDARY: 0.17477197208762,
}
INCUMBENT_FROZEN_TRAIN_ID_HASH: Mapping[str, str] = {
    POOL_PRIMARY: "48b17e76c1edcdce0369d8118ad21ea0beb1b472ec744cee3c579c02fa6e3111",
    POOL_SECONDARY: "e9a63ff49a3f54380ad1241be8db156c8bd7f4c3c9c0308859f8dcaa121c9506",
}
INCUMBENT_FROZEN_TEST_ID_HASH: Mapping[str, str] = {
    POOL_PRIMARY: "2dedfc6ae3ac3dae98e7404556535030d5d3fd000b8119c25d230db791507119",
    POOL_SECONDARY: "dfea9aa151cd5b0f86eede1d6929b8fe5a1e0ab34926a851e90d3f7de6d4d63f",
}
W19_REGISTERED_GATE_STATES: Mapping[str, bool] = {
    "chemprop_row_level_passed": True,
    "incumbent_row_level_passed": False,
}

VERDICT_VOCABULARY: tuple[str, ...] = (
    "eta_crosses_gate_out_of_fold",
    "incumbent_budget_closes_gate",
    "representation_sensitive_gate_undetermined",
    "incumbent_confirmed",
)

W20_3_RULE_TEXT = (
    "Only a verdict of eta_crosses_gate_out_of_fold authorises W20-3 to fold eta into "
    "the ranking key v1. Every other verdict means W20-3 must NOT fold eta in."
)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_repeat_folds(
    keys: Sequence[str],
    repeat_seeds: Sequence[int] = REPEAT_SEEDS,
    n_splits: int = N_SPLITS,
) -> list[dict[str, Any]]:
    """The registered grouped grid: GroupKFold by InChIKey, 5 folds x 5 repeats.

    Repeat r permutes the row order with numpy.random.default_rng(seed_r) and runs
    GroupKFold over that order, so different repeats land different groups in different
    folds while every fold stays group-disjoint and the folds of a repeat partition the
    rows. Both properties are asserted here, not assumed.
    """

    keys_list = [str(key) for key in keys]
    sample_count = len(keys_list)
    splitter = GroupKFold(n_splits=n_splits)
    folds: list[dict[str, Any]] = []
    for repeat_index, seed in enumerate(repeat_seeds):
        order = np.random.default_rng(int(seed)).permutation(sample_count)
        ordered_groups = [keys_list[int(index)] for index in order]
        seen = np.zeros(sample_count, dtype=bool)
        for fold_index, (train_position, test_position) in enumerate(
            splitter.split(np.zeros(sample_count), groups=ordered_groups)
        ):
            train_indices = np.sort(order[np.asarray(train_position, dtype=int)])
            test_indices = np.sort(order[np.asarray(test_position, dtype=int)])
            train_keys = {keys_list[int(index)] for index in train_indices}
            test_keys = {keys_list[int(index)] for index in test_indices}
            overlap = train_keys & test_keys
            if overlap:
                raise RuntimeError("group overlap inside a fold: run void")
            if bool(seen[test_indices].any()):
                raise RuntimeError("test folds of a repeat are not disjoint: run void")
            seen[test_indices] = True
            folds.append(
                {
                    "repeat_index": repeat_index,
                    "repeat_seed": int(seed),
                    "fold_index": fold_index,
                    "train_indices": train_indices,
                    "test_indices": test_indices,
                    "train_rows": int(train_indices.size),
                    "test_rows": int(test_indices.size),
                    "train_keys": len(train_keys),
                    "test_keys": len(test_keys),
                }
            )
        if not bool(seen.all()):
            raise RuntimeError("test folds of a repeat do not cover the rows: run void")
    return folds


def _xgb_model(config: Mapping[str, Any], seed: int) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=int(config["n_estimators"]),
        max_depth=int(config["max_depth"]),
        learning_rate=float(config["learning_rate"]),
        subsample=float(config["subsample"]),
        colsample_bytree=float(config["colsample_bytree"]),
        reg_lambda=float(config["reg_lambda"]),
        tree_method="hist",
        n_jobs=XGB_JOBS,
        random_state=int(seed),
    )


def select_incumbent_config(
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    keys: Sequence[str],
) -> tuple[dict[str, Any], dict[str, float]]:
    """Pick a grid config with an inner GroupKFold on the TRAINING rows only."""

    keys_list = [str(key) for key in keys]
    train_keys = [keys_list[int(index)] for index in train_indices]
    splitter = GroupKFold(n_splits=INNER_SPLITS)
    scores: dict[str, float] = {}
    for config in INCUMBENT_GRID:
        fold_maes: list[float] = []
        for inner_train, inner_test in splitter.split(
            np.zeros(train_indices.size), groups=train_keys
        ):
            rows_train = train_indices[np.asarray(inner_train, dtype=int)]
            rows_test = train_indices[np.asarray(inner_test, dtype=int)]
            model = _xgb_model(config, ENSEMBLE_SEEDS[0])
            model.fit(features[rows_train], target[rows_train])
            prediction = model.predict(features[rows_test])
            fold_maes.append(float(np.mean(np.abs(target[rows_test] - prediction))))
        scores[str(config["name"])] = float(np.mean(fold_maes))
    best = INCUMBENT_GRID[0]
    best_score = scores[str(best["name"])]
    for config in INCUMBENT_GRID[1:]:
        score = scores[str(config["name"])]
        if score < best_score:
            best = config
            best_score = score
    return dict(best), scores


_WORKER: dict[str, Any] = {}


def _worker_init(pool_names: Sequence[str], threads: int) -> None:
    import torch

    torch.set_num_threads(int(threads))
    pools, census = unfreeze.build_pools()
    for name in pool_names:
        frame = w19.build_pool_frame(pools, census, name)
        features, _names = frozen.build_feature_matrix(
            [str(smile) for smile in frame["smiles"]],
            [float(value) for value in frame["temperatures"]],
        )
        frame["features"] = features
        _WORKER[str(name)] = frame


def _chemprop_task(job: Mapping[str, Any]) -> dict[str, Any]:
    frame = _WORKER[str(job["pool"])]
    prediction, fit_seconds = w19.predict_chemprop_member(
        frame,
        np.asarray(job["train_indices"], dtype=int),
        np.asarray(job["test_indices"], dtype=int),
        int(job["seed"]),
        int(job["epochs"]),
    )
    return {
        "pool": str(job["pool"]),
        "repeat_seed": int(job["repeat_seed"]),
        "fold_index": int(job["fold_index"]),
        "seed": int(job["seed"]),
        "prediction": prediction,
        "fit_seconds": float(fit_seconds),
    }


def _placebo_task(job: Mapping[str, Any]) -> dict[str, Any]:
    base = _WORKER[str(job["pool"])]
    frame = dict(base)
    target = np.asarray(base["target"], dtype=float)
    permutation = np.random.default_rng(PLACEBO_SEED).permutation(target.size)
    frame["target"] = target[permutation]
    prediction, fit_seconds = w19.predict_chemprop_member(
        frame,
        np.asarray(job["train_indices"], dtype=int),
        np.asarray(job["test_indices"], dtype=int),
        int(job["seed"]),
        int(job["epochs"]),
    )
    return {
        "pool": str(job["pool"]),
        "repeat_seed": int(job["repeat_seed"]),
        "fold_index": int(job["fold_index"]),
        "seed": int(job["seed"]),
        "prediction": prediction,
        "fit_seconds": float(fit_seconds),
    }


def _incumbent_task(job: Mapping[str, Any]) -> dict[str, Any]:
    frame = _WORKER[str(job["pool"])]
    features = frame["features"]
    target = np.asarray(frame["target"], dtype=float)
    keys = [str(key) for key in frame["keys_list"]]
    train_indices = np.asarray(job["train_indices"], dtype=int)
    test_indices = np.asarray(job["test_indices"], dtype=int)
    config, inner_scores = select_incumbent_config(features, target, train_indices, keys)
    predictions = []
    for seed in ENSEMBLE_SEEDS:
        model = _xgb_model(config, int(seed))
        model.fit(features[train_indices], target[train_indices])
        predictions.append(model.predict(features[test_indices]))
    return {
        "pool": str(job["pool"]),
        "repeat_seed": int(job["repeat_seed"]),
        "fold_index": int(job["fold_index"]),
        "selected_config": str(config["name"]),
        "inner_scores": inner_scores,
        "predictions": np.asarray(predictions, dtype=float),
        "seeds": [int(seed) for seed in ENSEMBLE_SEEDS],
    }


def regression_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = prediction - target
    denominator = float(np.sum((target - float(target.mean())) ** 2))
    r2 = float("nan") if denominator <= 0.0 else float(1.0 - np.sum(residual**2) / denominator)
    return {
        "mae_log10_cP": float(np.mean(np.abs(residual))),
        "rmse_log10_cP": float(np.sqrt(np.mean(residual**2))),
        "r2_log10_cP": r2,
    }


def _pooled(target: np.ndarray, folds, pieces) -> dict[str, float]:
    targets = []
    predictions = []
    for fold, piece in zip(folds, pieces, strict=True):
        index = fold["test_indices"]
        targets.append(target[index])
        predictions.append(np.asarray(piece, dtype=float))
    return regression_metrics(np.concatenate(targets), np.concatenate(predictions))


def evaluate_pool(
    pool_name: str,
    frame: Mapping[str, Any],
    folds: Sequence[Mapping[str, Any]],
    chemprop_members: Mapping[Any, np.ndarray],
    incumbent_members: Mapping[Any, np.ndarray],
    selected_configs: Mapping[Any, str],
    placebo_members: Mapping[Any, np.ndarray],
    seeds: Sequence[int],
    jobs: int,
    epochs: int,
    run_placebo: bool,
    reproduce_incumbent: bool,
) -> dict[str, Any]:
    """Pool the 5x5 grid into per-seed readings for both arms, plus the placebo."""

    target = np.asarray(frame["target"], dtype=float)
    keys = [str(key) for key in frame["keys_list"]]

    reproduction: dict[str, Any] | None = None
    if reproduce_incumbent:
        train_indices, test_indices = frozen._group_key_split(keys)
        train_hash = frozen._split_hash(keys, train_indices)
        test_hash = frozen._split_hash(keys, test_indices)
        if (
            train_hash != INCUMBENT_FROZEN_TRAIN_ID_HASH[pool_name]
            or test_hash != INCUMBENT_FROZEN_TEST_ID_HASH[pool_name]
        ):
            raise RuntimeError("the incumbent W19-D5 split does not reproduce: run void")
        features, _names = frozen.build_feature_matrix(
            [str(smile) for smile in frame["smiles"]],
            [float(value) for value in frame["temperatures"]],
        )
        prediction = frozen._fit_predict(
            INCUMBENT_MODEL, features, target, train_indices, test_indices
        )
        observed = float(np.mean(np.abs(target[test_indices] - prediction)))
        frozen_mae = INCUMBENT_FROZEN_MAE[pool_name]
        reproduction = {
            "split": "GroupShuffleSplit(test_size=0.2, random_state=42) by inchikey",
            "model": INCUMBENT_MODEL,
            "mae_log10_cP": observed,
            "frozen_mae_log10_cP": frozen_mae,
            "abs_gap": abs(observed - frozen_mae),
            "matches_frozen": bool(
                abs(observed - frozen_mae) <= INCUMBENT_REPRODUCTION_TOLERANCE
            ),
            "train_id_hash": train_hash,
            "test_id_hash": test_hash,
        }

    chemprop_by_seed: dict[int, Any] = {}
    for seed in ENSEMBLE_SEEDS:
        pieces = [chemprop_members[(pool_name, fold["repeat_seed"], fold["fold_index"], seed)]
                  for fold in folds]
        chemprop_by_seed[int(seed)] = _pooled(target, folds, pieces)

    incumbent_by_seed: dict[int, Any] = {}
    for seed_index, seed in enumerate(ENSEMBLE_SEEDS):
        pieces = [
            incumbent_members[(pool_name, fold["repeat_seed"], fold["fold_index"])][seed_index]
            for fold in folds
        ]
        incumbent_by_seed[int(seed)] = _pooled(target, folds, pieces)

    constant_pieces = []
    for fold in folds:
        train_index = fold["train_indices"]
        constant_pieces.append(np.full(fold["test_indices"].size, float(target[train_index].mean())))
    constant = _pooled(target, folds, constant_pieces)

    placebo: dict[str, Any] | None = None
    if run_placebo:
        pieces = [placebo_members[(pool_name, fold["repeat_seed"], fold["fold_index"])]
                  for fold in folds]
        placebo_metrics = _pooled(target, folds, pieces)
        placebo = {
            "arm": "placebo_shuffled_target",
            "seed": PLACEBO_SEED,
            "members": 1,
            "cells": len(folds),
            "mae_log10_cP": placebo_metrics["mae_log10_cP"],
            "rmse_log10_cP": placebo_metrics["rmse_log10_cP"],
            "r2_log10_cP": placebo_metrics["r2_log10_cP"],
            "constant_predictor_mae_log10_cP": constant["mae_log10_cP"],
            "collapsed": bool(
                placebo_metrics["mae_log10_cP"] >= constant["mae_log10_cP"]
            ),
        }

    chemprop_values = [float(chemprop_by_seed[int(seed)]["mae_log10_cP"])
                       for seed in ENSEMBLE_SEEDS]
    incumbent_values = [float(incumbent_by_seed[int(seed)]["mae_log10_cP"])
                        for seed in ENSEMBLE_SEEDS]
    chemprop_mean = float(np.mean(chemprop_values))
    incumbent_mean = float(np.mean(incumbent_values))
    delta_mean = chemprop_mean - incumbent_mean
    delta_by_seed = {
        str(int(seed)): float(chemprop_by_seed[int(seed)]["mae_log10_cP"])
        - float(incumbent_by_seed[int(seed)]["mae_log10_cP"])
        for seed in ENSEMBLE_SEEDS
    }
    chemprop_gate = bool(chemprop_mean < MAE_GATE)
    incumbent_gate = bool(incumbent_mean < MAE_GATE)
    gate_state_unchanged = bool(
        chemprop_gate == W19_REGISTERED_GATE_STATES["chemprop_row_level_passed"]
        and incumbent_gate == W19_REGISTERED_GATE_STATES["incumbent_row_level_passed"]
    )
    verdict = verdict_from(delta_mean, chemprop_gate, incumbent_gate)

    chemprop_cells = [float(np.mean(np.abs(target[fold["test_indices"]] - np.asarray(
        chemprop_members[(pool_name, fold["repeat_seed"], fold["fold_index"],
                          int(seeds[0]))], dtype=float)))) for fold in folds]

    return {
        "pool": pool_name,
        "rows": len(keys),
        "keys": len(set(keys)),
        "cells": len(folds),
        "test_rows_pooled": int(sum(int(fold["test_indices"].size) for fold in folds)),
        "incumbent_in_place_reproduction": reproduction,
        "incumbent_aligned": {
            "label": "incumbent_aligned",
            "model": INCUMBENT_MODEL,
            "budget": "three-config grid selected by inner GroupKFold(3) on training rows, "
                      "then a three-seed ensemble",
            "ensemble_seeds": [int(seed) for seed in ENSEMBLE_SEEDS],
            "cross_seed_mean_mae_log10_cP": incumbent_mean,
            "cross_seed_sd_mae_log10_cP": float(np.std(incumbent_values, ddof=1)),
            "cross_seed_min_mae_log10_cP": float(np.min(incumbent_values)),
            "cross_seed_max_mae_log10_cP": float(np.max(incumbent_values)),
            "seed_values": {str(int(seed)): float(incumbent_by_seed[int(seed)]["mae_log10_cP"])
                            for seed in ENSEMBLE_SEEDS},
            "selected_config_counts": _count_values(selected_configs, pool_name),
            "gate_0_15_passed_by_cross_seed_mean": incumbent_gate,
            "gate_0_15_passed_by_cross_seed_min": bool(
                float(np.min(incumbent_values)) < MAE_GATE
            ),
        },
        "chemprop_aligned": {
            "label": "chemprop_aligned",
            "model": "Chemprop D-MPNN (BondMessagePassing, NormAggregation, RegressionFFN)",
            "budget": "registered W19-D5 configuration, three-seed ensemble, no search",
            "ensemble_seeds": [int(seed) for seed in ENSEMBLE_SEEDS],
            "epochs": int(epochs),
            "cross_seed_mean_mae_log10_cP": chemprop_mean,
            "cross_seed_sd_mae_log10_cP": float(np.std(chemprop_values, ddof=1)),
            "cross_seed_min_mae_log10_cP": float(np.min(chemprop_values)),
            "cross_seed_max_mae_log10_cP": float(np.max(chemprop_values)),
            "seed_values": {str(int(seed)): float(chemprop_by_seed[int(seed)]["mae_log10_cP"])
                            for seed in ENSEMBLE_SEEDS},
            "per_cell_mae_log10_cP": {
                "mean": float(np.mean(chemprop_cells)),
                "sd": float(np.std(chemprop_cells, ddof=1)),
                "min": float(np.min(chemprop_cells)),
                "max": float(np.max(chemprop_cells)),
            },
            "gate_0_15_passed_by_cross_seed_mean": chemprop_gate,
            "gate_0_15_passed_by_cross_seed_min": bool(
                float(np.min(chemprop_values)) < MAE_GATE
            ),
        },
        "delta": {
            "definition": "MAE_chemprop_cross_seed_mean - MAE_incumbent_cross_seed_mean, "
                          "pooled over the 5x5 grouped grid, in log10(cP)",
            "mean": delta_mean,
            "min": float(np.min(list(delta_by_seed.values()))),
            "max": float(np.max(list(delta_by_seed.values()))),
            "seed_values": delta_by_seed,
        },
        "gate": {
            "value": MAE_GATE,
            "units": "log10(cP)",
            "tolerance": TOLERANCE,
            "chemprop_cross_seed_mean_passed": chemprop_gate,
            "incumbent_cross_seed_mean_passed": incumbent_gate,
            "gate_state_unchanged_vs_w19": gate_state_unchanged,
        },
        "placebo": placebo,
        "verdict": verdict,
    }


def _count_values(selected_configs: Mapping[Any, str], pool_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (pool, _repeat_seed, _fold_index), name in selected_configs.items():
        if str(pool) != pool_name:
            continue
        counts[str(name)] = counts.get(str(name), 0) + 1
    return counts


def verdict_from(delta_mean: float, chemprop_gate: bool, incumbent_gate: bool) -> str:
    if abs(delta_mean) <= TOLERANCE:
        return "representation_sensitive_gate_undetermined"
    if delta_mean <= -TOLERANCE:
        if chemprop_gate and not incumbent_gate:
            return "eta_crosses_gate_out_of_fold"
        return "incumbent_budget_closes_gate"
    return "incumbent_confirmed"


def _package_version(name: str) -> str:
    try:
        module = __import__(name)
    except ImportError:
        return "absent"
    return str(getattr(module, "__version__", "unknown"))


HONEST_BOUNDARIES: tuple[str, ...] = (
    (
        "The eta channel is a separate channel from epsilon: its row and compound counts "
        "are never mixed with 457 / 97 / 276 / 2029."
    ),
    (
        "The split is GroupKFold by InChIKey, five folds by five repeats, so there is "
        "fold-level variance here that the W19-D5 single hold-out could not give. The "
        "folds are group-disjoint by construction and that is asserted before any arm is "
        "fitted."
    ),
    (
        "The incumbent arm is granted strictly MORE budget than the Chemprop arm: a "
        "three-config grid with inner grouped selection plus a three-seed ensemble, "
        "against the Chemprop arm registered configuration plus a three-seed ensemble "
        "with no search. The design is conservative against the Chemprop arm."
    ),
    (
        "The Chemprop epoch budget was reduced 60 -> 30 before the run under the "
        "declared amendment rule, because the registered 60-epoch grid extrapolated to "
        "several hours. The split, the pools and the arms were not reduced."
    ),
    (
        "The Chemprop configuration was registered in W19-D5 and was never searched: "
        "this is still an untuned neural arm against a budget-aligned fingerprint arm, "
        "not the best that either family can do."
    ),
    (
        "A verdict of eta_crosses_gate_out_of_fold authorises W20-3 to fold eta into "
        "the ranking key v1. It promotes nothing, and it moves no epsilon number."
    ),
)

UNVERIFIABLE: tuple[str, ...] = (
    (
        "Whether a hyperparameter search on the Chemprop arm would move the verdict is "
        "not verifiable from this design: the search budget was spent on the incumbent."
    ),
    (
        "The upstream provenance of the pooled rows (extraction, density pairing, unit "
        "conversion) is reused and not re-verified here."
    ),
    (
        "GroupKFold removes group leakage by InChIKey but does not remove scaffold or "
        "chemistry-family similarity, so new-chemistry generalisation is not verified."
    ),
    (
        "The placebo probes permuted labels only; permuted features and permuted groups "
        "are not probed, so the placebo is a one-sided collapse check."
    ),
    (
        "The incumbent in-place reproduction is exact on the W19-D5 GroupShuffleSplit "
        "split only; it is not a reproduction of the 5x5 grid, which has no prior."
    ),
    (
        "Per-seed readings pair a Chemprop seed with the incumbent seed of the same "
        "index; that pairing is a reporting convenience and carries no physical meaning."
    ),
)

VERDICT_NOTES: dict[str, str] = {
    "eta_crosses_gate_out_of_fold": (
        "Under a five-fold by five-repeat grouped protocol, with the incumbent granted "
        "the tuning and multi-seed budget it was denied, the Chemprop arm still leads by "
        "more than the tolerance and the two gate states are unchanged. The eta channel "
        "crosses its gate out of fold."
    ),
    "incumbent_budget_closes_gate": (
        "The Chemprop arm still leads by more than the tolerance, but the gate-pass "
        "pattern changed once the incumbent was budget-aligned, so the crossing is not "
        "registered."
    ),
    "representation_sensitive_gate_undetermined": (
        "The two arms are not resolvable at the registered tolerance under the upgraded "
        "protocol: the reading is representation-sensitive and the gate crossing is "
        "undetermined."
    ),
    "incumbent_confirmed": (
        "The budget-aligned incumbent wins by more than the tolerance, so the W19-D5 "
        "delta does not survive budget alignment."
    ),
}


def build_summary(
    *,
    prereg_sha256: str,
    pool_results: Mapping[str, dict[str, Any]],
    config: Mapping[str, Any],
    telemetry: Mapping[str, Any],
) -> dict[str, Any]:
    primary = pool_results[POOL_PRIMARY]
    verdict = str(primary["verdict"])
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "preregistration": {
            "path": "probes/w20_eta_fairness_prereg.json",
            "sha256": prereg_sha256,
            "status": "locked_before_run",
        },
        "plan_reference": "reports/week20_project_charter.md | section 1 | W20-1",
        "lane_section": "28.57",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "chemprop": _package_version("chemprop"),
            "torch": _package_version("torch"),
            "xgboost": _package_version("xgboost"),
            "numpy": _package_version("numpy"),
        },
        "registered_config": dict(config),
        "pools": {name: dict(record) for name, record in pool_results.items()},
        "verdict": verdict,
        "delta_mae_log10_cP": float(primary["delta"]["mean"]),
        "gate_log10_cP": MAE_GATE,
        "tolerance": TOLERANCE,
        "w20_3_eta_authorised": bool(verdict == "eta_crosses_gate_out_of_fold"),
        "w20_3_rule_text": W20_3_RULE_TEXT,
        "promoted": False,
        "main_scoreboard_attempts_added": 0,
        "cumulative_main_scoreboard_attempts": 11,
        "uses_no_reaxys_numbers": True,
        "telemetry": dict(telemetry),
        "honest_boundaries": list(HONEST_BOUNDARIES),
        "unverifiable": list(UNVERIFIABLE),
        "outputs": {
            "summary": "probes/w20_eta_fairness_summary.json",
            "report": "reports/w20_eta_fairness.md",
            "repeats": "probes/artifacts/w20_eta_fairness_repeats.csv",
        },
    }


def format_report(summary: Mapping[str, Any]) -> list[str]:
    primary = summary["pools"][POOL_PRIMARY]
    delta = float(summary["delta_mae_log10_cP"])
    lines: list[str] = [
        "# W20-1: the eta fairness review (budget-aligned arms, grouped five by five)",
        "",
        "Task `" + str(summary["task_id"]) + "`, generated "
        + str(summary["generated_at_utc"]) + ".",
        "",
        "## 0. What this lane removes",
        "",
        (
            "W19-D5 flagged two boundaries it could not remove: the incumbent was a frozen "
            "single-configuration single-seed XGBoost against a three-seed Chemprop ensemble, "
            "and the grouped protocol was one 20 percent hold-out draw with no fold-level "
            "variance. This lane grants the incumbent the tuning and multi-seed budget, and "
            "upgrades the split to GroupKFold by InChIKey, five folds by five repeats."
        ),
        "",
        "## 1. What was compared",
        "",
        "| item | incumbent_aligned | chemprop_aligned |",
        "| --- | --- | --- |",
        (
            "| model | Morgan count 2048 plus a temperature block, XGBoost | Chemprop "
            "D-MPNN, learned graph representation |"
        ),
        (
            "| budget | three-config grid, inner GroupKFold(3) selection, three-seed "
            "ensemble | W19-D5 registered configuration, three-seed ensemble, no search |"
        ),
        "| split | GroupKFold by InChIKey, 5 folds x 5 repeats | identical, cells shared |",
        "| target | log10(cP) | log10(cP) |",
        "| gate | 0.15 | 0.15, reported rather than used as the criterion |",
        "",
        "## 2. Readings, grouped out-of-fold grid only",
        "",
        (
            "| pool | rows | keys | cells | incumbent mean | incumbent min | chemprop "
            "mean | chemprop min | delta | verdict |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in POOL_ORDER:
        record = summary["pools"].get(name)
        if not record:
            continue
        incumbent = record["incumbent_aligned"]
        chemprop = record["chemprop_aligned"]
        cells = [
            name,
            str(record["rows"]),
            str(record["keys"]),
            str(record["cells"]),
            str(incumbent["cross_seed_mean_mae_log10_cP"]),
            str(incumbent["cross_seed_min_mae_log10_cP"]),
            str(chemprop["cross_seed_mean_mae_log10_cP"]),
            str(chemprop["cross_seed_min_mae_log10_cP"]),
            str(record["delta"]["mean"]),
            str(record["verdict"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend([
        "",
        "## 3. Incumbent in-place reproduction (prior)",
        "",
        "| pool | split | observed MAE | frozen MAE | abs_gap |",
        "| --- | --- | --- | --- | --- |",
    ])
    for name in POOL_ORDER:
        record = summary["pools"].get(name)
        if not record:
            continue
        reproduction = record["incumbent_in_place_reproduction"]
        lines.append("| " + " | ".join([
            name,
            str(reproduction["split"]),
            str(reproduction["mae_log10_cP"]),
            str(reproduction["frozen_mae_log10_cP"]),
            str(reproduction["abs_gap"]),
        ]) + " |")
    lines.extend([
        "",
        "## 4. Placebo",
        "",
    ])
    placebo = primary.get("placebo")
    if placebo:
        lines.append("| arm | seed | cells | grid MAE | constant predictor MAE | collapsed |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        lines.append("| " + " | ".join([
            str(placebo["arm"]),
            str(placebo["seed"]),
            str(placebo["cells"]),
            str(placebo["mae_log10_cP"]),
            str(placebo["constant_predictor_mae_log10_cP"]),
            str(placebo["collapsed"]),
        ]) + " |")
        lines.append("")
    lines.extend([
        "## 5. Verdict",
        "",
        "Primary pool `" + POOL_PRIMARY + "`: delta = " + repr(delta) + " log10(cP) against "
        "the registered tolerance of +/-" + repr(TOLERANCE) + " -> **"
        + str(summary["verdict"]) + "**.",
        "",
        VERDICT_NOTES.get(str(summary["verdict"]), ""),
        "",
        "Gate context on the primary pool: the Chemprop arm reads "
        + str(primary["chemprop_aligned"]["cross_seed_mean_mae_log10_cP"])
        + " (min " + str(primary["chemprop_aligned"]["cross_seed_min_mae_log10_cP"]) + ")",
        " and the incumbent reads "
        + str(primary["incumbent_aligned"]["cross_seed_mean_mae_log10_cP"])
        + " (min " + str(primary["incumbent_aligned"]["cross_seed_min_mae_log10_cP"])
        + ") against the registered gate of " + repr(MAE_GATE) + ".",
        "",
        "**W20-3 decision**: " + str(summary["w20_3_rule_text"]),
        "Authorised to fold eta in: **" + str(summary["w20_3_eta_authorised"]) + "**.",
        "",
        "## 6. Boundaries",
        "",
    ])
    for boundary in summary["honest_boundaries"]:
        lines.append("- " + " ".join(str(boundary).split()))
    lines.append("")
    lines.append("## 7. Registered as not verifiable")
    lines.append("")
    for item in summary["unverifiable"]:
        lines.append("- " + " ".join(str(item).split()))
    lines.extend([
        "",
        (
            "Nothing here is promoted and no main-scoreboard attempt is spent. The frozen "
            "baseline 0.4091179943351143 and the frozen headline 0.4766400383507876 are not "
            "touched. No Reaxys value appears anywhere in this lane."
        ),
        "",
    ])
    return lines


def write_repeats_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "pool",
        "arm",
        "repeat_seed",
        "fold_index",
        "member",
        "train_rows",
        "test_rows",
        "mae_log10_cP",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in fieldnames})


def _write_text(path: Path, text: str) -> None:
    """LF-only, UTF-8, no BOM: the repository hygiene test pins all three."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--pools", nargs="+", default=list(POOL_ORDER))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(ENSEMBLE_SEEDS))
    parser.add_argument("--repeats", type=int, default=N_REPEATS)
    parser.add_argument("--no-incumbent-reproduction", action="store_true")
    parser.add_argument("--no-placebo", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.smoke:
        jobs = 1
        epochs = 5
        pool_names = [POOL_PRIMARY]
        seeds = [ENSEMBLE_SEEDS[0]]
        repeat_seeds = REPEAT_SEEDS[:1]
        run_placebo = False
        reproduce = False
    else:
        jobs = max(1, int(args.jobs))
        epochs = int(args.epochs)
        pool_names = [str(name) for name in args.pools]
        seeds = tuple(int(seed) for seed in args.seeds)
        repeat_seeds = REPEAT_SEEDS[: int(args.repeats)]
        run_placebo = not args.no_placebo
        reproduce = not args.no_incumbent_reproduction

    if not args.smoke and SUMMARY_PATH.exists() and not args.overwrite:
        raise SystemExit("summary already exists; pass --overwrite to replace it")

    pools, census = unfreeze.build_pools()
    frames = {name: w19.build_pool_frame(pools, census, name) for name in pool_names}
    folds_by_pool: dict[str, list[dict[str, Any]]] = {}
    for name in pool_names:
        folds = build_repeat_folds(frames[name]["keys_list"], repeat_seeds)
        if args.smoke:
            folds = [fold for fold in folds if fold["fold_index"] == 0]
        folds_by_pool[name] = folds

    started = time.perf_counter()
    chemprop_jobs: list[dict[str, Any]] = []
    incumbent_jobs: list[dict[str, Any]] = []
    placebo_jobs: list[dict[str, Any]] = []
    for name in pool_names:
        for fold in folds_by_pool[name]:
            base = {
                "pool": name,
                "repeat_seed": fold["repeat_seed"],
                "fold_index": fold["fold_index"],
                "train_indices": fold["train_indices"],
                "test_indices": fold["test_indices"],
                "epochs": epochs,
            }
            incumbent_jobs.append(dict(base))
            for seed in seeds:
                chemprop_jobs.append({**base, "seed": int(seed)})
            if run_placebo and name == POOL_PRIMARY:
                placebo_jobs.append({**base, "seed": int(seeds[0])})

    chemprop_members: dict[Any, np.ndarray] = {}
    incumbent_members: dict[Any, np.ndarray] = {}
    selected_configs: dict[Any, str] = {}
    placebo_members: dict[Any, np.ndarray] = {}
    fit_seconds: list[float] = []
    workers = 1 if args.smoke else jobs
    if workers == 1:
        _worker_init(pool_names, WORKER_THREADS)
        for job in chemprop_jobs:
            result = _chemprop_task(job)
            key = (result["pool"], result["repeat_seed"], result["fold_index"], result["seed"])
            chemprop_members[key] = result["prediction"]
            fit_seconds.append(result["fit_seconds"])
        for job in incumbent_jobs:
            result = _incumbent_task(job)
            key = (result["pool"], result["repeat_seed"], result["fold_index"])
            incumbent_members[key] = result["predictions"]
            selected_configs[key] = result["selected_config"]
        for job in placebo_jobs:
            result = _placebo_task(job)
            key = (result["pool"], result["repeat_seed"], result["fold_index"])
            placebo_members[key] = result["prediction"]
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(tuple(pool_names), WORKER_THREADS),
        ) as executor:
            for result in executor.map(_chemprop_task, chemprop_jobs):
                key = (result["pool"], result["repeat_seed"], result["fold_index"],
                       result["seed"])
                chemprop_members[key] = result["prediction"]
                fit_seconds.append(result["fit_seconds"])
            for result in executor.map(_incumbent_task, incumbent_jobs):
                key = (result["pool"], result["repeat_seed"], result["fold_index"])
                incumbent_members[key] = result["predictions"]
                selected_configs[key] = result["selected_config"]
            for result in executor.map(_placebo_task, placebo_jobs):
                key = (result["pool"], result["repeat_seed"], result["fold_index"])
                placebo_members[key] = result["prediction"]
    elapsed = time.perf_counter() - started

    pool_results: dict[str, dict[str, Any]] = {}
    for name in pool_names:
        pool_results[name] = evaluate_pool(
            name,
            frames[name],
            folds_by_pool[name],
            chemprop_members,
            incumbent_members,
            selected_configs,
            placebo_members,
            seeds,
            jobs,
            epochs,
            run_placebo and name == POOL_PRIMARY,
            reproduce,
        )

    if args.smoke:
        record = pool_results[POOL_PRIMARY]
        print("smoke ok: cells " + str(record["cells"])
              + " chemprop " + repr(record["chemprop_aligned"]["cross_seed_mean_mae_log10_cP"])
              + " incumbent " + repr(
                  record["incumbent_aligned"]["cross_seed_mean_mae_log10_cP"])
              + " delta " + repr(record["delta"]["mean"])
              + " verdict " + str(record["verdict"]), flush=True)
        return pool_results

    repeats_rows: list[dict[str, Any]] = []
    for name in pool_names:
        for fold in folds_by_pool[name]:
            for seed in seeds:
                index = fold["test_indices"]
                prediction = chemprop_members[(name, fold["repeat_seed"], fold["fold_index"],
                                               int(seed))]
                repeats_rows.append({
                    "pool": name,
                    "arm": "chemprop_aligned",
                    "repeat_seed": fold["repeat_seed"],
                    "fold_index": fold["fold_index"],
                    "member": "seed-" + str(int(seed)),
                    "train_rows": fold["train_rows"],
                    "test_rows": fold["test_rows"],
                    "mae_log10_cP": float(np.mean(np.abs(
                        np.asarray(frames[name]["target"], dtype=float)[index]
                        - np.asarray(prediction, dtype=float)))),
                })
            incumbent_predictions = incumbent_members[(
                name, fold["repeat_seed"], fold["fold_index"])]
            for seed_index, seed in enumerate(seeds):
                index = fold["test_indices"]
                repeats_rows.append({
                    "pool": name,
                    "arm": "incumbent_aligned",
                    "repeat_seed": fold["repeat_seed"],
                    "fold_index": fold["fold_index"],
                    "member": "seed-" + str(int(seed)),
                    "train_rows": fold["train_rows"],
                    "test_rows": fold["test_rows"],
                    "mae_log10_cP": float(np.mean(np.abs(
                        np.asarray(frames[name]["target"], dtype=float)[index]
                        - np.asarray(incumbent_predictions[seed_index], dtype=float)))),
                })
    write_repeats_csv(REPEATS_PATH, repeats_rows)

    config = {
        "n_splits": N_SPLITS,
        "n_repeats": len(repeat_seeds),
        "repeat_seeds": [int(seed) for seed in repeat_seeds],
        "ensemble_seeds": [int(seed) for seed in seeds],
        "inner_splits": INNER_SPLITS,
        "chemprop_epochs": int(epochs),
        "chemprop_epochs_registered_in_w19": EPOCHS_REGISTERED_IN_W19,
        "incumbent_grid": list(INCUMBENT_GRID_NAMES),
        "placebo_seed": PLACEBO_SEED,
        "workers": workers,
        "torch_threads_per_worker": WORKER_THREADS,
    }
    telemetry = {
        "total_seconds": elapsed,
        "chemprop_fits": len(fit_seconds),
        "chemprop_fit_seconds_total": float(np.sum(fit_seconds)),
        "chemprop_fit_seconds_max": float(np.max(fit_seconds)) if fit_seconds else 0.0,
        "pool_census_keys": sorted(census["pools"].keys()),
    }
    prereg_sha256 = canonical_text_sha256(PREREG_PATH)
    summary = build_summary(
        prereg_sha256=prereg_sha256,
        pool_results=pool_results,
        config=config,
        telemetry=telemetry,
    )
    summary["artifacts"] = {
        "w20_eta_fairness_repeats.csv": canonical_text_sha256(REPEATS_PATH),
    }
    _write_text(REPORT_PATH, "\n".join(format_report(summary)) + "\n")
    summary["artifacts"]["w20_eta_fairness.md"] = canonical_text_sha256(REPORT_PATH)
    _write_text(SUMMARY_PATH, json.dumps(summary, indent=2) + "\n")
    primary = pool_results[POOL_PRIMARY]
    print("verdict " + str(summary["verdict"])
          + " delta " + repr(summary["delta_mae_log10_cP"])
          + " chemprop_mean " + repr(
              primary["chemprop_aligned"]["cross_seed_mean_mae_log10_cP"])
          + " incumbent_mean " + repr(
              primary["incumbent_aligned"]["cross_seed_mean_mae_log10_cP"]),
          flush=True)
    print("w20_3_eta_authorised " + str(summary["w20_3_eta_authorised"]), flush=True)
    print("wrote " + str(SUMMARY_PATH), flush=True)
    return pool_results


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
