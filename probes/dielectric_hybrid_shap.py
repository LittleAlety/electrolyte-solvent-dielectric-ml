"""Week 15 modelling line: per-fold training-side SHAP ranking of the epsilon hybrid.

Why this probe exists
=====================
The knowledge-data dual-driven framework of Gao et al. (Angew. Chem. Int. Ed.,
DOI 10.1002/anie.202416506) ranks its 64 knowledge dimensions with SHAP on the
whole dataset and then trains. That ordering is a leak: the ranking has already
seen the held-out rows. Lever 9 of the Week 14 programme answered it with a
column-shuffle permutation ranking recomputed inside every training fold, and
that reading is what appendix AB-6 of the working manual quotes. This probe asks
the same question through a *different importance implementation* - the exact
TreeSHAP contributions that the fitted booster already carries - so the AB-6
reading stops resting on a single implementation.

What is measured
================
Two arms, one fold dealing.

``hybrid``
    The frozen v1.x scoring model. It is **not** a concatenated
    Morgan+Physical matrix: ``fit_predict_representation`` fits one XGBoost
    model on the 2048 Morgan count bits and a second one on the 13 physical
    columns, then scores ``0.5 * (morgan_pred + physical_pred)`` clipped below
    at 1.0. That is the model whose grouped R2 is ``0.4091179943351143``. SHAP
    is additive under a linear combination of models with disjoint feature
    sets, so a hybrid feature's contribution is exactly ``0.5`` times its
    contribution inside its own model; the two halves are computed separately
    and concatenated into one 2061-column ranking. The clip is a boundary and
    is recorded as one (see ``honest_boundaries``).

``knowledge_block_crosscheck``
    The lever 9 model - the frozen physical block plus the ten knowledge
    members - read with the same TreeSHAP reader over the ten knowledge columns
    only. Same folds, same model specification, same columns as AB-6; the only
    thing that changes is the importance implementation. It exists because the
    AB-6 top three are knowledge-pool members and are *not* columns of the
    hybrid, so this arm is the only feature-for-feature comparison available.

The leak guard
==============
``assert_shap_ranking_scope`` is the lever 9 guard plus two clauses: the rows
that feed the ranking must be *exactly* the training fold (no silent scope
shrinkage), and no compound that appears in the test fold may appear among the
ranked rows. It runs inside every fold of the production loop, not only in the
tests, and every artifact row records ``test_rows_visible_to_ranking == 0``.

Boundaries
==========
Feature importance is not causation. This probe discovers nothing new; it
re-reads an existing result with an independent implementation. A rank that
moves between folds is reported as ``unstable`` rather than smoothed. Ranks of
columns that no tree ever split on are decided by column order, so they are
positions in a tie, not measurements. The full list is in ``honest_boundaries``
and in the report.

Outputs (all new; every frozen artefact is read-only here)::

    probes/dielectric_hybrid_shap_summary.json
    probes/artifacts/dielectric_hybrid_shap_importance.csv
    probes/artifacts/dielectric_hybrid_shap_rank_stability.csv
    reports/dielectric_hybrid_shap.md
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_band_ablation import ROOM_BAND
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_knowledge_purity_sweep import (
    IMPORTANCE_SHUFFLES,
    KNOWLEDGE_POOL,
    RankingLeakError,
    assert_ranking_scope,
    knowledge_feature_block,
    permutation_importance,
    scoreboard_splits,
)
from dielectric_observations_grouped_benchmark import (
    METRIC_NAMES,
    build_matrices,
    read_csv_rows,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    FP_SIZE,
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
    fit_predict_representation,
)
from dielectric_room_window_paired import HYBRID, fold_signature, scored_fold_signature
from xgboost import DMatrix, XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from electrolyte_ml.pathing import portable_relative_path

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_hybrid_shap_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_hybrid_shap.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
IMPORTANCE_PATH = ARTIFACTS_DIR / "dielectric_hybrid_shap_importance.csv"
STABILITY_PATH = ARTIFACTS_DIR / "dielectric_hybrid_shap_rank_stability.csv"
LEVER9_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_summary.json"
LEVER9_IMPORTANCE_PATH = ARTIFACTS_DIR / "dielectric_knowledge_purity_sweep_importance.csv"
LEVER_PATH = Path(__file__).resolve()

TASK_ID = "week15_modelling_hybrid_shap"
TITLE = "Week 15 建模线：ε hybrid 的逐折训练侧 SHAP 特征重要度排序"
IMPORTANCE_IMPL = "xgboost_pred_contribs"
PROTOCOL = (
    "冻结的 ε hybrid（Morgan+Physical，即 v1.x 主记分模型）在冻结主记分牌的每一折训练侧内部，"
    "重算精确 TreeSHAP 贡献后按列排序"
)
ARM_HYBRID = "hybrid"
ARM_KNOWLEDGE = "knowledge_block_crosscheck"
ARM_PERMUTATION = "knowledge_permutation_corrected"
ARM_ORDER = (ARM_HYBRID, ARM_KNOWLEDGE, ARM_PERMUTATION)

REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
#: Additivity is checked on a *relative* scale: xgboost accumulates TreeSHAP
#: contributions in single precision, so on margins of order 10^2 the
#: reconstruction error lands near 1e-4 absolute, i.e. a few 1e-7 relative. A
#: double-precision tolerance here would be a false claim about the tool.
SHAP_RELATIVE_TOLERANCE = 1e-5
SHAP_ABSOLUTE_FLOOR = 1.0
PREDICTION_FLOOR = 1.0
HYBRID_MIXING_WEIGHT = 0.5

STABILITY_TOP_K = 10
STABILITY_SIGN_MIN = 0.8
AGREEMENT_CONSISTENT = 0.8
AGREEMENT_PARTIAL = 0.2
TOP_K_LEVELS = (3, 10, 20)

COVERAGE_TABLE_SHA256 = "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
FROZEN_V03_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FROZEN_V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"

AB6_TOP_THREE = (
    "heteroatom_over_carbon",
    "donor_acceptor_pair_density",
    "ring_count",
)
AB6_REFERENCE = {
    "heteroatom_over_carbon": {"top_3_folds": 49, "mean_rank": 1.36},
    "donor_acceptor_pair_density": {"top_3_folds": 37, "mean_rank": 2.84},
    "ring_count": {"top_3_folds": 35, "mean_rank": 3.08},
    "donor_count": {"top_3_folds": 0, "mean_rank": 8.58},
    "acceptor_count": {"top_3_folds": 0, "mean_rank": 9.88, "mean_importance": 0.0},
}
AB6_RANK_TOLERANCE = 0.005

IMPORTANCE_COLUMNS = (
    "arm",
    "repeat",
    "fold",
    "rank",
    "feature",
    "feature_kind",
    "importance_mean_abs",
    "importance_mean_signed",
    "importance_share",
    "ranked_in_top_3",
    "ranked_in_top_10",
    "ranking_rows",
    "ranking_compounds",
    "test_rows_visible_to_ranking",
    "fold_feature_count",
    "shap_additivity_rel_residual",
)

STABILITY_COLUMNS = (
    "arm",
    "feature",
    "feature_kind",
    "repeats",
    "folds_ranked",
    "top_3_folds",
    "top_3_hit_rate",
    "top_10_folds",
    "top_10_hit_rate",
    "top_20_folds",
    "top_20_hit_rate",
    "mean_rank",
    "median_rank",
    "rank_std",
    "min_rank",
    "max_rank",
    "mean_importance",
    "std_importance",
    "mean_signed_importance",
    "zero_importance_folds",
    "repeats_resolved",
    "repeats_positive_sign",
    "repeats_negative_sign",
    "repeats_zero_sign",
    "sign_consistency",
    "majority_sign",
    "stability_label",
)

class ShapAdditivityError(RuntimeError):
    """Raised when TreeSHAP contributions do not rebuild the fitted margin."""


def _use_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _as_index(values: Sequence[object]) -> np.ndarray:
    return np.asarray([int(value) for value in values], dtype=int)


def morgan_feature_names() -> tuple[str, ...]:
    return tuple(f"morgan_bit_{index:04d}" for index in range(FP_SIZE))


def hybrid_feature_names() -> tuple[str, ...]:
    """The hybrid column order: the Morgan bits first, then the physical block."""

    return morgan_feature_names() + tuple(PHYSICAL_COLUMNS)


def knowledge_feature_names() -> tuple[str, ...]:
    return tuple(KNOWLEDGE_POOL)


def feature_kind(name: str) -> str:
    if name.startswith("morgan_bit_"):
        return "morgan_bit"
    if name in PHYSICAL_COLUMNS:
        return "physical"
    if name in KNOWLEDGE_POOL:
        return "knowledge"
    raise ValueError(f"unknown feature: {name!r}")


def feature_column_order_sha256(names: Sequence[str]) -> str:
    return hashlib.sha256(",".join(str(name) for name in names).encode("utf-8")).hexdigest()


def shap_contributions(
    model: XGBRegressor,
    features: np.ndarray,
    rows: Sequence[object],
    *,
    tolerance: float = SHAP_RELATIVE_TOLERANCE,
) -> tuple[np.ndarray, dict[str, float]]:
    """Exact TreeSHAP contributions for `rows`, with the bias column removed.

    `XGBRegressor.predict` does not accept `pred_contribs` in xgboost 3.4.1 (it
    raises TypeError), so the booster is asked directly. The raw matrix is
    `(n_rows, n_features + 1)`: the last column is the model bias and must be
    dropped. Dropping it is *checked*, not assumed - the contributions plus the
    bias have to rebuild the fitted margin.

    The check is relative rather than absolute: the booster accumulates its
    contributions in single precision, so the reconstruction error is a few 1e-7
    of the margin instead of machine epsilon of a float64. Quoting 1e-9 here would
    be a false statement about the tool, so the residual is normalised by
    `max(|margin|, 1.0)` and the raw absolute maximum is returned beside it.
    """

    matrix_rows = _as_index(rows)
    if matrix_rows.size == 0:
        raise ValueError("shap_contributions needs at least one row")
    block = np.asarray(features, dtype=float)[matrix_rows]
    matrix = DMatrix(block)
    booster = model.get_booster()
    raw = np.asarray(booster.predict(matrix, pred_contribs=True), dtype=float)
    expected = (block.shape[0], block.shape[1] + 1)
    if raw.ndim != 2 or raw.shape != expected:
        raise ShapAdditivityError(
            f"pred_contribs returned {raw.shape}, expected {expected}; the last column is the "
            "bias and must be dropped"
        )
    margin = np.asarray(booster.predict(matrix), dtype=float)
    bias_column = raw[:, -1]
    if not np.allclose(bias_column, bias_column[0], rtol=0.0, atol=1e-6):
        raise ShapAdditivityError("the pred_contribs bias column is not constant across rows")
    absolute = np.abs(raw[:, :-1].sum(axis=1) + bias_column - margin)
    scale = np.maximum(np.abs(margin), SHAP_ABSOLUTE_FLOOR)
    relative = float(np.max(absolute / scale))
    if not relative <= tolerance:
        raise ShapAdditivityError(
            "the contributions do not rebuild the margin: max relative residual "
            f"{relative!r} exceeds {tolerance!r}"
        )
    return raw[:, :-1], {
        "bias": float(bias_column[0]),
        "max_relative_residual": relative,
        "max_absolute_residual": float(np.max(absolute)),
        "tolerance": float(tolerance),
    }


def assert_shap_ranking_scope(
    *,
    importance_rows: Sequence[object],
    train_index: Sequence[object],
    test_index: Sequence[object],
    groups: Sequence[object] | None = None,
    context: str = "",
) -> dict[str, int]:
    """Fail if a SHAP ranking left the training fold or silently shrank it.

    Three clauses, in order of increasing strength:

    1. the lever 9 guard - no ranked row may be a test-fold row, and every
       ranked row has to sit inside the training fold;
    2. the scope must be *exactly* the training fold: a ranking that quietly
       dropped training rows would be a silent narrowing of the scope;
    3. no compound may be shared between the ranked rows and the test fold,
       which is the group-level clause the row-level check cannot see.
    """

    rows = _as_index(importance_rows)
    train = _as_index(train_index)
    test = _as_index(test_index)
    assert_ranking_scope(
        importance_rows=rows,
        train_index=train,
        test_index=test,
        context=context,
    )
    missing = train[~np.isin(train, rows)]
    if missing.size:
        raise RankingLeakError(
            f"{context}: the ranking covers {rows.size} row(s) but the training fold has "
            f"{train.size}; {missing.size} training row(s) would be silently dropped"
        )
    record = {
        "ranking_rows": int(rows.size),
        "ranking_compounds": 0,
        "test_rows_visible_to_ranking": 0,
    }
    if groups is not None:
        group_array = np.asarray(groups)
        shared = sorted(set(group_array[test].tolist()).intersection(group_array[rows].tolist()))
        if shared:
            raise RankingLeakError(
                f"{context}: the ranking touched {len(shared)} compound(s) that also sit in the "
                f"test fold: {shared[:5]}"
            )
        record["ranking_compounds"] = int(np.unique(group_array[rows]).size)
    return record


def leaky_shap_scope(train_index: Sequence[object], test_index: Sequence[object]) -> np.ndarray:
    """The forbidden scope, built only so the guard can be shown to fire."""

    return np.concatenate([_as_index(train_index), _as_index(test_index)])


def fit_hybrid_fold(
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    train_index: np.ndarray,
    test_index: np.ndarray,
    seed: int = SEED,
) -> tuple[XGBRegressor, XGBRegressor, np.ndarray, np.ndarray]:
    """Fit the frozen hybrid exactly as `fit_predict_representation` does.

    Returns both the raw two-model average and the clipped score, so the caller
    can record how often the 1.0 floor actually bites.
    """

    morgan_model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    morgan_model.fit(morgan[train_index], target[train_index])
    physical_model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    physical_model.fit(physical[train_index], target[train_index])
    raw = HYBRID_MIXING_WEIGHT * (
        morgan_model.predict(morgan[test_index]) + physical_model.predict(physical[test_index])
    )
    return morgan_model, physical_model, raw, np.maximum(raw, PREDICTION_FLOOR)


def fit_knowledge_fold(
    *,
    physical: np.ndarray,
    knowledge: np.ndarray,
    target: np.ndarray,
    train_index: np.ndarray,
    seed: int = SEED,
) -> tuple[XGBRegressor, np.ndarray]:
    """Fit the lever 9 ranking model: the frozen physical block plus the pool."""

    features = np.hstack([physical, knowledge])
    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(features[train_index], target[train_index])
    return model, features


def _rank_rows(
    *,
    arm: str,
    repeat: int,
    fold: int,
    feature_names: Sequence[str],
    contributions: np.ndarray,
    ranking_rows: int,
    ranking_compounds: int,
    residual: float,
) -> list[dict[str, object]]:
    """One fold's mean-absolute contributions turned into a ranked table.

    Ties keep the feature column order, so the ranking is a pure function of the
    inputs and cannot move with a set iteration order.
    """

    mean_abs = np.mean(np.abs(contributions), axis=0)
    mean_signed = np.mean(contributions, axis=0)
    total = float(np.sum(mean_abs))
    order = sorted(
        range(len(feature_names)),
        key=lambda position: (-float(mean_abs[position]), position),
    )
    rows: list[dict[str, object]] = []
    for rank, position in enumerate(order, start=1):
        name = str(feature_names[position])
        rows.append(
            {
                "arm": arm,
                "repeat": int(repeat),
                "fold": int(fold),
                "rank": int(rank),
                "feature": name,
                "feature_kind": feature_kind(name),
                "importance_mean_abs": float(mean_abs[position]),
                "importance_mean_signed": float(mean_signed[position]),
                "importance_share": (float(mean_abs[position]) / total) if total > 0.0 else 0.0,
                "ranked_in_top_3": 1 if rank <= 3 else 0,
                "ranked_in_top_10": 1 if rank <= 10 else 0,
                "ranking_rows": int(ranking_rows),
                "ranking_compounds": int(ranking_compounds),
                "test_rows_visible_to_ranking": 0,
                "fold_feature_count": len(feature_names),
                "shap_additivity_rel_residual": float(residual),
            }
        )
    return rows


def run_hybrid_arm(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    groups: Sequence[object],
    seed: int = SEED,
) -> dict[str, object]:
    """Score the frozen hybrid per fold and rank its columns on the training side."""

    names = hybrid_feature_names()
    group_array = np.asarray(groups)
    labels = np.asarray(target, dtype=float)
    importance_rows: list[dict[str, object]] = []
    guard_records: list[dict[str, object]] = []
    fold_records: list[dict[str, object]] = []
    residuals: list[float] = []
    absolute_residuals: list[float] = []
    predictions_by_fold: dict[tuple[int, int], np.ndarray] = {}
    buckets: dict[int, tuple[list[np.ndarray], list[np.ndarray]]] = {}
    clipped = 0
    for repeat, fold, train_index, test_index in splits:
        train_rows = _as_index(train_index)
        test_rows = _as_index(test_index)
        context = f"{ARM_HYBRID!r} repeat {int(repeat)} fold {int(fold)}"
        scope = assert_shap_ranking_scope(
            importance_rows=train_rows,
            train_index=train_rows,
            test_index=test_rows,
            groups=group_array,
            context=context,
        )
        morgan_model, physical_model, raw, prediction = fit_hybrid_fold(
            morgan=morgan,
            physical=physical,
            target=labels,
            train_index=train_rows,
            test_index=test_rows,
            seed=seed,
        )
        clipped += int(np.sum(raw < PREDICTION_FLOOR))
        morgan_contributions, morgan_diagnostics = shap_contributions(
            morgan_model, morgan, train_rows
        )
        physical_contributions, physical_diagnostics = shap_contributions(
            physical_model, physical, train_rows
        )
        residual = max(
            morgan_diagnostics["max_relative_residual"],
            physical_diagnostics["max_relative_residual"],
        )
        residuals.append(residual)
        absolute_residuals.append(
            max(
                morgan_diagnostics["max_absolute_residual"],
                physical_diagnostics["max_absolute_residual"],
            )
        )
        contributions = np.hstack(
            [
                HYBRID_MIXING_WEIGHT * morgan_contributions,
                HYBRID_MIXING_WEIGHT * physical_contributions,
            ]
        )
        importance_rows.extend(
            _rank_rows(
                arm=ARM_HYBRID,
                repeat=int(repeat),
                fold=int(fold),
                feature_names=names,
                contributions=contributions,
                ranking_rows=int(scope["ranking_rows"]),
                ranking_compounds=int(scope["ranking_compounds"]),
                residual=residual,
            )
        )
        guard_records.append({"repeat": int(repeat), "fold": int(fold), **scope})
        fold_records.append(
            {
                "repeat": int(repeat),
                "fold": int(fold),
                "train_rows": int(train_rows.size),
                "test_rows": int(test_rows.size),
                "train_compounds": int(np.unique(group_array[train_rows]).size),
                "test_compounds": int(np.unique(group_array[test_rows]).size),
                "train_groups_sha256": hashlib.sha256(
                    ",".join(sorted(set(group_array[train_rows].tolist()))).encode("utf-8")
                ).hexdigest(),
                "test_groups_sha256": hashlib.sha256(
                    ",".join(sorted(set(group_array[test_rows].tolist()))).encode("utf-8")
                ).hexdigest(),
            }
        )
        predictions_by_fold[(int(repeat), int(fold))] = prediction
        bucket = buckets.setdefault(int(repeat), ([], []))
        bucket[0].append(labels[test_rows])
        bucket[1].append(prediction)
    repeat_rows = []
    for repeat, (fold_labels, fold_predictions) in sorted(buckets.items()):
        metrics = evaluate_repeat(np.concatenate(fold_labels), np.concatenate(fold_predictions))
        repeat_rows.append(
            {
                "protocol": ARM_HYBRID,
                "representation": HYBRID,
                "repeat": int(repeat),
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    return {
        "importance_rows": importance_rows,
        "guard_records": guard_records,
        "fold_records": fold_records,
        "predictions_by_fold": predictions_by_fold,
        "repeat_rows": repeat_rows,
        "readings": summarize_repeats(repeat_rows)[ARM_HYBRID],
        "max_additivity_rel_residual": max(residuals) if residuals else 0.0,
        "max_additivity_abs_residual": (
            max(absolute_residuals) if absolute_residuals else 0.0
        ),
        "clipped_predictions": clipped,
        "fits": 2 * len(guard_records),
    }


def run_knowledge_arm(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    physical: np.ndarray,
    knowledge: np.ndarray,
    target: np.ndarray,
    groups: Sequence[object],
    seed: int = SEED,
) -> dict[str, object]:
    """Rank the ten knowledge members with TreeSHAP, for the AB-6 comparison."""

    names = knowledge_feature_names()
    group_array = np.asarray(groups)
    labels = np.asarray(target, dtype=float)
    importance_rows: list[dict[str, object]] = []
    guard_records: list[dict[str, object]] = []
    residuals: list[float] = []
    absolute_residuals: list[float] = []
    for repeat, fold, train_index, test_index in splits:
        train_rows = _as_index(train_index)
        test_rows = _as_index(test_index)
        context = f"{ARM_KNOWLEDGE!r} repeat {int(repeat)} fold {int(fold)}"
        scope = assert_shap_ranking_scope(
            importance_rows=train_rows,
            train_index=train_rows,
            test_index=test_rows,
            groups=group_array,
            context=context,
        )
        model, features = fit_knowledge_fold(
            physical=physical,
            knowledge=knowledge,
            target=labels,
            train_index=train_rows,
            seed=seed,
        )
        contributions, diagnostics = shap_contributions(model, features, train_rows)
        residual = diagnostics["max_relative_residual"]
        residuals.append(residual)
        absolute_residuals.append(diagnostics["max_absolute_residual"])
        knowledge_contributions = contributions[:, len(PHYSICAL_COLUMNS) :]
        importance_rows.extend(
            _rank_rows(
                arm=ARM_KNOWLEDGE,
                repeat=int(repeat),
                fold=int(fold),
                feature_names=names,
                contributions=knowledge_contributions,
                ranking_rows=int(scope["ranking_rows"]),
                ranking_compounds=int(scope["ranking_compounds"]),
                residual=residual,
            )
        )
        guard_records.append({"repeat": int(repeat), "fold": int(fold), **scope})
    return {
        "importance_rows": importance_rows,
        "guard_records": guard_records,
        "max_additivity_rel_residual": max(residuals) if residuals else 0.0,
        "max_additivity_abs_residual": (
            max(absolute_residuals) if absolute_residuals else 0.0
        ),
        "fits": len(guard_records),
    }


def permutation_aggregates(
    fold_order: Sequence[Sequence[int]],
    scores_by_member: Mapping[str, Sequence[float]],
) -> tuple[dict[str, dict[str, object]], dict[tuple[int, int], frozenset[str]]]:
    """Per-member aggregates and per-fold top-3 sets for a permutation reading.

    The ranking inside a fold is the lever 9 order: descending score, ties broken
    by the pre-registered pool order, so a reading can be rebuilt from the raw
    per-fold scores without refitting anything.
    """

    top_3_sets: dict[tuple[int, int], frozenset[str]] = {}
    ranks_by_member: dict[str, list[int]] = {member: [] for member in KNOWLEDGE_POOL}
    for index, (repeat, fold) in enumerate(fold_order):
        ordered = sorted(
            KNOWLEDGE_POOL,
            key=lambda member: (
                -float(scores_by_member[member][index]),
                KNOWLEDGE_POOL.index(member),
            ),
        )
        top_3_sets[(int(repeat), int(fold))] = frozenset(ordered[:3])
        for rank, member in enumerate(ordered, start=1):
            ranks_by_member[member].append(rank)
    per_member: dict[str, dict[str, object]] = {}
    for member in KNOWLEDGE_POOL:
        values = np.asarray(scores_by_member[member], dtype=float)
        ranks = np.asarray(ranks_by_member[member], dtype=float)
        per_member[member] = {
            "mean_importance": float(values.mean()) if values.size else 0.0,
            "mean_rank": float(ranks.mean()) if ranks.size else 0.0,
            "median_rank": float(np.median(ranks)) if ranks.size else 0.0,
            "min_rank": int(ranks.min()) if ranks.size else 0,
            "max_rank": int(ranks.max()) if ranks.size else 0,
            "top_1_folds": int(np.sum(ranks <= 1)),
            "top_3_folds": int(np.sum(ranks <= 3)),
        }
    return per_member, top_3_sets


def run_permutation_reference(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    physical: np.ndarray,
    knowledge: np.ndarray,
    target: np.ndarray,
    groups: Sequence[object],
    stored_rows: Sequence[Mapping[str, str]],
    seed: int = SEED,
) -> dict[str, object]:
    """Re-run the lever 9 ranking call and record which columns it shuffles.

    Lever 9 calls ``permutation_importance(model, full, target,
    columns=KNOWLEDGE_POOL, ...)`` where ``full`` has 23 columns (13 physical plus
    the ten knowledge members) and only the ten pool names are passed as
    ``columns``. That helper shuffles ``permuted[:, position]`` with ``position``
    taken from ``enumerate(columns)``, so the columns it actually permutes are
    positions 0..9 of the matrix - the first ten *physical* columns - and the ten
    pool names only label them.

    Three readings are taken off one fit per fold and stored beside each other:
    the lever 9 call as written, the same call with the ten first physical column
    names, and the call with all 23 columns named. The first two have to return
    identical numbers and the first has to reproduce the stored artifact to the
    last decimal; the third is the corrected measurement. That turns the claim
    into an arithmetic fact rather than a code review comment.
    """

    names = knowledge_feature_names()
    all_names = tuple(PHYSICAL_COLUMNS) + tuple(KNOWLEDGE_POOL)
    positional_names = tuple(PHYSICAL_COLUMNS[: len(names)])
    full = np.hstack([physical, knowledge])
    labels = np.asarray(target, dtype=float)
    group_array = np.asarray(groups)
    stored = {
        (int(row["repeat"]), int(row["fold"]), str(row["member"])): (
            float(row["importance"]),
            int(row["rank"]),
        )
        for row in stored_rows
    }
    fold_order: list[list[int]] = []
    stored_scores: dict[str, list[float]] = {member: [] for member in names}
    corrected_scores: dict[str, list[float]] = {member: [] for member in names}
    guard_records: list[dict[str, object]] = []
    replicated_ranks = 0
    replication_worst = 0.0
    positional_worst = 0.0
    corrected_worst = 0.0
    for repeat, fold, train_index, test_index in splits:
        train_rows = _as_index(train_index)
        test_rows = _as_index(test_index)
        context = f"{ARM_PERMUTATION!r} repeat {int(repeat)} fold {int(fold)}"
        scope = assert_shap_ranking_scope(
            importance_rows=train_rows,
            train_index=train_rows,
            test_index=test_rows,
            groups=group_array,
            context=context,
        )
        model = XGBRegressor(**XGB_PARAMS, random_state=seed)
        model.fit(full[train_rows], labels[train_rows])
        as_lever_9_ranked = permutation_importance(
            model,
            full,
            labels,
            columns=names,
            importance_rows=train_rows,
            shuffles=IMPORTANCE_SHUFFLES,
            seed=seed,
        )
        positional_ranked = permutation_importance(
            model,
            full,
            labels,
            columns=positional_names,
            importance_rows=train_rows,
            shuffles=IMPORTANCE_SHUFFLES,
            seed=seed,
        )
        named_ranked = dict(
            permutation_importance(
                model,
                full,
                labels,
                columns=all_names,
                importance_rows=train_rows,
                shuffles=IMPORTANCE_SHUFFLES,
                seed=seed,
            )
        )
        as_lever_9 = dict(as_lever_9_ranked)
        as_lever_9_ranks = {
            name: index for index, (name, _score) in enumerate(as_lever_9_ranked, start=1)
        }
        positional = dict(positional_ranked)
        for member in names:
            stored_scores[member].append(float(as_lever_9[member]))
            corrected_scores[member].append(float(named_ranked[member]))
            expected_score, expected_rank = stored[(int(repeat), int(fold), member)]
            replication_worst = max(
                replication_worst, abs(float(as_lever_9[member]) - expected_score)
            )
            replicated_ranks += int(as_lever_9_ranks[member] == expected_rank)
        for position, physical_name in enumerate(positional_names):
            positional_worst = max(
                positional_worst,
                abs(float(positional[physical_name]) - float(as_lever_9[names[position]])),
            )
        corrected_worst = max(
            corrected_worst,
            max(
                abs(float(named_ranked[member]) - float(as_lever_9[member])) for member in names
            ),
        )
        fold_order.append([int(repeat), int(fold)])
        guard_records.append({"repeat": int(repeat), "fold": int(fold), **scope})
    cells = len(fold_order) * len(names)
    replicated_sets = permutation_aggregates(fold_order, stored_scores)[1]
    return {
        "arm": ARM_PERMUTATION,
        "protocol": (
            "lever 9's column-shuffle permutation importance, re-run on the identical folds "
            "twice: once with the call as written, once with every column named"
        ),
        "shuffles": IMPORTANCE_SHUFFLES,
        "fold_order": fold_order,
        "stored_lever9_scores": stored_scores,
        "corrected_scores": corrected_scores,
        "labels_shuffled_by_the_lever9_call": {
            member: positional_names[position] for position, member in enumerate(names)
        },
        "replication": {
            "cells_compared": int(cells),
            "max_abs_difference_vs_stored_lever9": float(replication_worst),
            "ranks_identical": int(replicated_ranks),
            "verified": bool(replication_worst == 0.0 and replicated_ranks == cells),
            "method": (
                "the stored per-member importances are reproduced by re-running lever 9's own "
                "call signature on the identical folds: "
                "permutation_importance(model, full_23_columns, target, columns=KNOWLEDGE_POOL, "
                "importance_rows=train_rows, shuffles=3, seed=42)"
            ),
        },
        "positional_identity": {
            "max_abs_difference": float(positional_worst),
            "verified": bool(positional_worst == 0.0),
            "why": (
                "the same call with the ten first physical column names returns identical "
                "numbers, which is what pins the permuted columns to positions 0..9 of the "
                "23-column matrix"
            ),
        },
        "corrected_call_differs": {
            "max_abs_difference": float(corrected_worst),
            "verified": bool(corrected_worst > 0.0),
            "why": (
                "naming all 23 columns moves the ten knowledge members to positions 13..22, so "
                "both the shuffle seeds and the shuffled columns change and the corrected call "
                "is a different measurement"
            ),
        },
        "replicated_top_3_sets": {
            f"{key[0]}|{key[1]}": sorted(value) for key, value in sorted(replicated_sets.items())
        },
        "guard_records": guard_records,
    }


def verify_fold_faithfulness(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    predictions_by_fold: Mapping[tuple[int, int], np.ndarray],
    seed: int = SEED,
) -> dict[str, object]:
    """Prove the hand-rolled fold fitter is the frozen scoring function.

    The scoring contract of the main scoreboard is whatever
    `fit_predict_representation(HYBRID, ...)` returns. This probe fits the two
    halves itself (it needs the fitted boosters to read SHAP out of), so the two
    paths are compared prediction by prediction before any reading is believed.
    """

    labels = np.asarray(target, dtype=float)
    worst = 0.0
    compared = 0
    for repeat, fold, train_index, test_index in splits:
        reference, _signature = fit_predict_representation(
            HYBRID,
            morgan=morgan,
            physical=physical,
            target=labels,
            train_indices=_as_index(train_index),
            test_indices=_as_index(test_index),
            seed=seed,
        )
        mine = predictions_by_fold[(int(repeat), int(fold))]
        worst = max(worst, float(np.max(np.abs(reference - mine))))
        compared += 1
    return {
        "folds_compared": int(compared),
        "max_abs_difference": float(worst),
        "identical": bool(worst == 0.0),
        "reference_function": "dielectric_representation_ablation.fit_predict_representation",
        "why": (
            "the hybrid this probe ranks has to be the hybrid the main scoreboard scores; the "
            "two-model average is re-implemented here only because TreeSHAP needs the fitted "
            "boosters, so the re-implementation is checked against the frozen function instead "
            "of being trusted"
        ),
    }


def rank_stability(
    rows: Sequence[Mapping[str, object]],
    *,
    arm: str,
    feature_names: Sequence[str],
    repeats: int,
) -> list[dict[str, object]]:
    """Per-column rank and sign stability across the 50 folds."""

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["feature"])].append(row)
    entries: list[dict[str, object]] = []
    for name in feature_names:
        items = grouped.get(str(name), [])
        ranks = np.asarray([int(str(row["rank"])) for row in items], dtype=float)
        absolutes = np.asarray(
            [float(str(row["importance_mean_abs"])) for row in items], dtype=float
        )
        signed = np.asarray(
            [float(str(row["importance_mean_signed"])) for row in items], dtype=float
        )
        per_repeat: dict[int, list[float]] = defaultdict(list)
        for row in items:
            per_repeat[int(str(row["repeat"]))].append(float(str(row["importance_mean_signed"])))
        repeat_means = np.asarray(
            [float(np.mean(per_repeat[key])) for key in sorted(per_repeat)], dtype=float
        )
        positive = int(np.sum(repeat_means > 0.0))
        negative = int(np.sum(repeat_means < 0.0))
        zero = int(np.sum(repeat_means == 0.0))
        resolved = positive + negative
        consistency = float(max(positive, negative) / resolved) if resolved else 0.0
        top_3 = int(np.sum(ranks <= 3)) if ranks.size else 0
        top_10 = int(np.sum(ranks <= 10)) if ranks.size else 0
        top_20 = int(np.sum(ranks <= 20)) if ranks.size else 0
        folds = int(ranks.size)
        entries.append(
            {
                "arm": arm,
                "feature": str(name),
                "feature_kind": feature_kind(str(name)),
                "repeats": int(repeats),
                "folds_ranked": folds,
                "top_3_folds": top_3,
                "top_3_hit_rate": (top_3 / folds) if folds else 0.0,
                "top_10_folds": top_10,
                "top_10_hit_rate": (top_10 / folds) if folds else 0.0,
                "top_20_folds": top_20,
                "top_20_hit_rate": (top_20 / folds) if folds else 0.0,
                "mean_rank": float(ranks.mean()) if folds else 0.0,
                "median_rank": float(np.median(ranks)) if folds else 0.0,
                "rank_std": float(ranks.std(ddof=1)) if folds > 1 else 0.0,
                "min_rank": int(ranks.min()) if folds else 0,
                "max_rank": int(ranks.max()) if folds else 0,
                "mean_importance": float(absolutes.mean()) if folds else 0.0,
                "std_importance": float(absolutes.std(ddof=1)) if folds > 1 else 0.0,
                "mean_signed_importance": float(signed.mean()) if folds else 0.0,
                "zero_importance_folds": int(np.sum(absolutes == 0.0)),
                "repeats_resolved": resolved,
                "repeats_positive_sign": positive,
                "repeats_negative_sign": negative,
                "repeats_zero_sign": zero,
                "sign_consistency": consistency,
                "majority_sign": (
                    "positive" if positive > negative else ("negative" if negative > positive else "zero")
                ),
                "stability_label": (
                    "stable"
                    if ((top_10 / folds if folds else 0.0) >= STABILITY_SIGN_MIN
                        and consistency >= STABILITY_SIGN_MIN)
                    else "unstable"
                ),
            }
        )
    return entries


def stability_overview(
    entries: Sequence[Mapping[str, object]],
    *,
    repeats: int,
    top_k: int = STABILITY_TOP_K,
) -> dict[str, object]:
    stable = [entry for entry in entries if str(entry["stability_label"]) == "stable"]
    never = [
        entry
        for entry in entries
        if int(str(entry["zero_importance_folds"])) == int(str(entry["folds_ranked"]))
    ]
    return {
        "features": len(entries),
        "repeats": int(repeats),
        "folds_per_feature": int(entries[0]["folds_ranked"]) if entries else 0,
        "top_k": int(top_k),
        "stable_features": len(stable),
        "unstable_features": len(entries) - len(stable),
        "features_never_used_by_any_tree": len(never),
        "rule": (
            f"stable := top_{top_k}_hit_rate >= {STABILITY_SIGN_MIN} and sign_consistency >= "
            f"{STABILITY_SIGN_MIN}; sign_consistency is the share of repeats whose mean signed "
            "SHAP agrees with the majority sign, and it is 0 when every repeat resolves to zero"
        ),
        "tie_note": (
            "a column that no tree ever splits on carries exactly zero contribution in every "
            "fold; its rank is decided by the fixed column order and is a position inside a tie, "
            "not a measurement"
        ),
    }


def top_features(
    entries: Sequence[Mapping[str, object]],
    *,
    count: int = 10,
) -> list[dict[str, object]]:
    ordered = sorted(
        entries,
        key=lambda entry: (-float(str(entry["mean_importance"])), str(entry["feature"])),
    )
    return [
        {
            "rank": index,
            "feature": str(entry["feature"]),
            "feature_kind": str(entry["feature_kind"]),
            "mean_importance": float(str(entry["mean_importance"])),
            "mean_rank": float(str(entry["mean_rank"])),
            "rank_std": float(str(entry["rank_std"])),
            "top_3_folds": int(str(entry["top_3_folds"])),
            "top_10_folds": int(str(entry["top_10_folds"])),
            "top_10_hit_rate": float(str(entry["top_10_hit_rate"])),
            "sign_consistency": float(str(entry["sign_consistency"])),
            "stability_label": str(entry["stability_label"]),
        }
        for index, entry in enumerate(ordered[:count], start=1)
    ]


def kind_totals(entries: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """How much of the hybrid's importance each feature family carries."""

    total = sum(float(str(entry["mean_importance"])) for entry in entries)
    totals: dict[str, dict[str, object]] = {}
    for name in ("morgan_bit", "physical", "knowledge"):
        block = [entry for entry in entries if str(entry["feature_kind"]) == name]
        if not block:
            continue
        importance = sum(float(str(entry["mean_importance"])) for entry in block)
        totals[name] = {
            "features": len(block),
            "mean_importance_total": float(importance),
            "mean_importance_share": (float(importance) / total) if total > 0.0 else 0.0,
            "in_top_10": sum(1 for entry in block if int(str(entry["top_10_folds"])) > 0),
            "stable_features": sum(
                1 for entry in block if str(entry["stability_label"]) == "stable"
            ),
        }
    return totals

def _top_k_by_fold(
    rows: Sequence[Mapping[str, object]],
    *,
    name_key: str,
    top_k: int = 3,
) -> dict[tuple[int, int], frozenset[str]]:
    grouped: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    for row in rows:
        key = (int(str(row["repeat"])), int(str(row["fold"])))
        grouped[key].append((int(str(row["rank"])), str(row[name_key])))
    return {
        key: frozenset(name for _rank, name in sorted(items)[:top_k])
        for key, items in grouped.items()
    }


def read_lever9_reference() -> dict[str, object]:
    """The lever 9 reading the AB-6 comparison is drawn against."""

    payload = json.loads(LEVER9_SUMMARY_PATH.read_text(encoding="utf-8"))
    rows = read_csv_rows(LEVER9_IMPORTANCE_PATH)
    per_member = {
        member: {
            "top_3_folds": int(payload["importance_stability"]["per_member"][member]["top_3_folds"]),
            "mean_rank": float(payload["importance_stability"]["per_member"][member]["mean_rank"]),
            "mean_importance": float(
                payload["importance_stability"]["per_member"][member]["mean_importance"]
            ),
        }
        for member in KNOWLEDGE_POOL
    }
    fold_top_3 = _top_k_by_fold(rows, name_key="member", top_k=3)
    counts: dict[frozenset[str], int] = {}
    for value in fold_top_3.values():
        counts[value] = counts.get(value, 0) + 1
    modal = max(counts.items(), key=lambda item: (item[1], sorted(item[0])))
    controller = payload.get("purity_controller", {})
    return {
        "summary_path": portable_relative_path(LEVER9_SUMMARY_PATH, root=REPOSITORY_ROOT),
        "summary_sha256": canonical_text_sha256(LEVER9_SUMMARY_PATH),
        "importance_path": portable_relative_path(LEVER9_IMPORTANCE_PATH, root=REPOSITORY_ROOT),
        "importance_sha256": sha256_file(LEVER9_IMPORTANCE_PATH),
        "fold_deal_signature_sha256": str(
            payload["main_scoreboard"]["fold_deal"]["signature_sha256"]
        ),
        "importance_implementation": str(controller.get("importance_definition", "permutation")),
        "per_member": per_member,
        "fold_top_3": fold_top_3,
        "modal_top_3": sorted(modal[0]),
        "modal_top_3_count": int(modal[1]),
        "manual_appendix": "AB-6",
    }


def ab6_manual_check(reference: Mapping[str, object]) -> dict[str, object]:
    """Re-derive the five AB-6 numbers the manual quotes.

    The manual's rounded values are typed here as constants; the artifact is the
    authority. Comparing the two means a comparison table can never be built on
    a misreading of the manual.
    """

    per_member = reference["per_member"]
    checks: dict[str, dict[str, object]] = {}
    for member, expected in AB6_REFERENCE.items():
        actual = per_member[member]  # type: ignore[index]
        matches = int(actual["top_3_folds"]) == int(expected["top_3_folds"])
        if "mean_rank" in expected:
            matches = matches and (
                abs(float(actual["mean_rank"]) - float(expected["mean_rank"])) <= AB6_RANK_TOLERANCE
            )
        if "mean_importance" in expected:
            matches = matches and (
                abs(float(actual["mean_importance"]) - float(expected["mean_importance"]))
                <= AB6_RANK_TOLERANCE
            )
        checks[member] = {
            "matches_manual": bool(matches),
            "manual_top_3_folds": expected.get("top_3_folds"),
            "reference_top_3_folds": int(actual["top_3_folds"]),
            "manual_mean_rank": expected.get("mean_rank"),
            "reference_mean_rank": float(actual["mean_rank"]),
            "manual_mean_importance": expected.get("mean_importance"),
            "reference_mean_importance": float(actual["mean_importance"]),
        }
    return {
        "members": checks,
        "all_match": all(bool(entry["matches_manual"]) for entry in checks.values()),
        "tolerance": AB6_RANK_TOLERANCE,
        "why": (
            "the AB-6 numbers are quoted from the working manual; they are re-derived from the "
            "lever 9 artifact here so the comparison table cannot rest on a misread"
        ),
    }


def _verdict(match_rate: float) -> str:
    if match_rate >= AGREEMENT_CONSISTENT:
        return "consistent"
    if match_rate >= AGREEMENT_PARTIAL:
        return "partially_consistent"
    return "inconsistent"


def _agreement(
    left: Mapping[tuple[int, int], frozenset[str]],
    right: Mapping[tuple[int, int], frozenset[str]],
) -> dict[str, object]:
    """Per-fold exact top-3 set agreement between two rankings of the same ten members."""

    shared = sorted(set(left) & set(right))
    matches = sum(1 for key in shared if left[key] == right[key])
    jaccards = [
        len(left[key] & right[key]) / len(left[key] | right[key])
        for key in shared
        if (left[key] | right[key])
    ]
    rate = (matches / len(shared)) if shared else 0.0
    return {
        "folds": len(shared),
        "exact_top_3_set_matches": int(matches),
        "exact_match_rate": float(rate),
        "mean_jaccard": float(np.mean(jaccards)) if jaccards else 0.0,
        "verdict": _verdict(rate),
    }


def _modal_top_k(
    sets: Mapping[tuple[int, int], frozenset[str]],
) -> tuple[list[str], int]:
    """The most common top-k set and how many folds it covers."""

    counts: dict[frozenset[str], int] = {}
    for value in sets.values():
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return [], 0
    best = max(counts.items(), key=lambda item: (item[1], sorted(item[0])))
    return sorted(best[0]), int(best[1])


def _member_status(shap_folds: int, corrected_folds: int, folds: int) -> str:
    """Does an AB-6 top-three member keep its place under both honest readings?"""

    strong = min(shap_folds, corrected_folds) >= AGREEMENT_CONSISTENT * folds
    weak = max(shap_folds, corrected_folds) < AGREEMENT_PARTIAL * folds
    if strong:
        return "reproduced"
    if weak:
        return "lost"
    return "weakened"


def build_ab6_comparison(
    *,
    knowledge_rows: Sequence[Mapping[str, object]],
    knowledge_stability: Sequence[Mapping[str, object]],
    hybrid_stability: Sequence[Mapping[str, object]],
    reference: Mapping[str, object],
    permutation: Mapping[str, object],
) -> dict[str, object]:
    """The three-way table against AB-6.

    Three rankings of the same ten members on the same fifty folds:

    * ``shap`` - this probe's TreeSHAP arm, the independent implementation;
    * ``quoted_lever9`` - what AB-6 actually quotes, which the defect block shows
      is the ten first *physical* columns under the pool's names;
    * ``corrected_permutation`` - the lever 9 implementation with all 23 columns
      named, i.e. the reading lever 9 was trying to take.
    """

    shap_sets = _top_k_by_fold(knowledge_rows, name_key="feature", top_k=3)
    quoted_sets = reference["fold_top_3"]
    fold_order = permutation["fold_order"]
    folds = len(fold_order)
    quoted_members, quoted_rebuilt_sets = permutation_aggregates(
        fold_order, permutation["stored_lever9_scores"]
    )
    corrected_members, corrected_sets = permutation_aggregates(
        fold_order, permutation["corrected_scores"]
    )
    sets_reproduced = sum(
        1
        for key, value in quoted_rebuilt_sets.items()
        if key in quoted_sets and value == quoted_sets[key]  # type: ignore[index]
    )
    shap_vs_quoted = _agreement(shap_sets, quoted_sets)  # type: ignore[arg-type]
    shap_vs_corrected = _agreement(shap_sets, corrected_sets)
    quoted_vs_corrected = _agreement(quoted_rebuilt_sets, corrected_sets)
    by_member = {str(entry["feature"]): entry for entry in knowledge_stability}
    shuffled_behind = permutation["labels_shuffled_by_the_lever9_call"]
    per_member: dict[str, dict[str, object]] = {}
    for member in KNOWLEDGE_POOL:
        shap_entry = by_member[member]
        per_member[member] = {
            "shap_mean_importance": float(shap_entry["mean_importance"]),
            "shap_mean_rank": float(shap_entry["mean_rank"]),
            "shap_top_3_folds": int(shap_entry["top_3_folds"]),
            "shap_stability_label": str(shap_entry["stability_label"]),
            "quoted_lever9_mean_importance": float(quoted_members[member]["mean_importance"]),
            "quoted_lever9_mean_rank": float(quoted_members[member]["mean_rank"]),
            "quoted_lever9_top_3_folds": int(quoted_members[member]["top_3_folds"]),
            "corrected_permutation_mean_importance": float(
                corrected_members[member]["mean_importance"]
            ),
            "corrected_permutation_mean_rank": float(corrected_members[member]["mean_rank"]),
            "corrected_permutation_top_3_folds": int(corrected_members[member]["top_3_folds"]),
            "column_actually_shuffled_behind_the_quoted_label": str(shuffled_behind[member]),
        }
    top_three_status = {
        member: {
            "status": _member_status(
                int(per_member[member]["shap_top_3_folds"]),
                int(per_member[member]["corrected_permutation_top_3_folds"]),
                folds,
            ),
            "shap_top_3_folds": int(per_member[member]["shap_top_3_folds"]),
            "corrected_permutation_top_3_folds": int(
                per_member[member]["corrected_permutation_top_3_folds"]
            ),
            "quoted_lever9_top_3_folds": int(per_member[member]["quoted_lever9_top_3_folds"]),
        }
        for member in AB6_TOP_THREE
    }
    counts_last: dict[str, dict[str, object]] = {}
    for member in ("donor_count", "acceptor_count"):
        counts_last[member] = {
            "shap_mean_rank": float(per_member[member]["shap_mean_rank"]),
            "corrected_permutation_mean_rank": float(
                per_member[member]["corrected_permutation_mean_rank"]
            ),
            "quoted_lever9_mean_rank": float(per_member[member]["quoted_lever9_mean_rank"]),
        }
    counts_last_rule = "在某种读数下，那两个线性计数排在十名中的倒数三名"
    counts_last_holds = {
        name: bool(float(block["shap_mean_rank"]) >= 8.0)
        and bool(float(block["corrected_permutation_mean_rank"]) >= 8.0)
        for name, block in counts_last.items()
    }
    shap_modal, shap_modal_count = _modal_top_k(shap_sets)
    quoted_modal, quoted_modal_count = _modal_top_k(quoted_sets)  # type: ignore[arg-type]
    corrected_modal, corrected_modal_count = _modal_top_k(corrected_sets)
    hybrid_top = top_features(hybrid_stability, count=10)
    return {
        "reference": {
            "arm": "杠杆 9 知识纯度扫描，列随机置换重要度",
            "summary_path": reference["summary_path"],
            "summary_sha256": reference["summary_sha256"],
            "importance_path": reference["importance_path"],
            "importance_sha256": reference["importance_sha256"],
            "importance_definition": reference["importance_implementation"],
            "fold_deal_signature_sha256": reference["fold_deal_signature_sha256"],
            "manual_appendix": reference["manual_appendix"],
        },
        "manual_numbers_reproduced": ab6_manual_check(reference),
        "feature_level_comparability": {
            "ab6_top_three_is_inside_the_hybrid_feature_space": False,
            "ab6_top_three": list(AB6_TOP_THREE),
            "note": (
                "AB-6 的三强是十列知识池的成员；hybrid 的 2061 列是 2048 个 Morgan 位加 13 列"
                "物理特征，所以那三个名字根本不在 hybrid 的特征空间里。唯一可做的「特征对特征」"
                "对照是下面的知识臂：它在同样的折上排序的正是这十列。"
            ),
        },
        "crosscheck_arm": ARM_KNOWLEDGE,
        "reference_defect": {
            "id": "lever9_permutation_importance_shuffled_the_first_ten_columns",
            "claim": (
                "引用表里挂在十个知识池成员名下的那些重要度，其实是那张 23 列矩阵前 10 列（物理块）"
                "的置换重要度；因为 `permutation_importance` 洗的是 `permuted[:, position]`，"
                "而 `position` 来自 `enumerate(columns)`，但 `features` 实际带 23 列"
            ),
            "label_to_column_actually_shuffled": dict(shuffled_behind),  # type: ignore[arg-type]
            "evidence": {
                "replication": dict(permutation["replication"]),  # type: ignore[arg-type]
                "positional_identity": dict(permutation["positional_identity"]),  # type: ignore[arg-type]
                "corrected_call_differs": dict(permutation["corrected_call_differs"]),  # type: ignore[arg-type]
                "top_3_sets_reproduced_folds": int(sets_reproduced),
                "top_3_sets_compared_folds": int(folds),
                "quoted_vs_corrected": quoted_vs_corrected,
            },
            "consequence": (
                "手册 AB-6 那段描述的其实是物理块在知识池名字下的排序；修正后的置换排序与本探针的"
                " SHAP 排序，才是真正关于那十个知识池成员的读数"
            ),
            "not_claimed": [
                "不评判杠杆 9 那次调用的动机，只陈述代码做了什么、数值是什么",
                (
                    "本探针不改写杠杆 9：它的文件在本探针写集之外，只读打开；缺陷是**报告**出来的，"
                    "不是就地修掉的"
                ),
            ],
            "action_required_outside_this_write_set": (
                "需要在本探针写集之外做一次 Week 15 勘误决定：涉及杠杆 9 的产物，以及引用它的手册"
                "段落；本探针只能报告测量结果"
            ),
        },
        "readings": {
            "shap_vs_quoted_lever9": shap_vs_quoted,
            "shap_vs_corrected_permutation": shap_vs_corrected,
            "quoted_lever9_vs_corrected_permutation": quoted_vs_corrected,
        },
        "fold_top_3_exact_match": {
            "folds": int(shap_vs_quoted["folds"]),
            "matches": int(shap_vs_quoted["exact_top_3_set_matches"]),
            "match_rate": float(shap_vs_quoted["exact_match_rate"]),
            "mean_jaccard": float(shap_vs_quoted["mean_jaccard"]),
            "modal_top_3_shap": shap_modal,
            "modal_top_3_shap_count": int(shap_modal_count),
            "modal_top_3_quoted_lever9": quoted_modal,
            "modal_top_3_quoted_lever9_count": int(quoted_modal_count),
            "modal_top_3_corrected_permutation": corrected_modal,
            "modal_top_3_corrected_permutation_count": int(corrected_modal_count),
            "modal_top_3_permutation": list(reference["modal_top_3"]),  # type: ignore[arg-type]
            "modal_top_3_permutation_count": int(reference["modal_top_3_count"]),  # type: ignore[arg-type]
        },
        "top_three_status": top_three_status,
        "counts_rank_last": {
            "rule": counts_last_rule,
            "holds": counts_last_holds,
            "members": counts_last,
        },
        "per_member": per_member,
        "hybrid_side": {
            "top_10": [str(entry["feature"]) for entry in hybrid_top],
            "top_10_kinds": [str(entry["feature_kind"]) for entry in hybrid_top],
            "physical_columns_in_top_10": [
                str(entry["feature"])
                for entry in hybrid_top
                if str(entry["feature_kind"]) == "physical"
            ],
        },
        "verdict": str(shap_vs_quoted["verdict"]),
        "verdict_rule": (
            f"逐折 top-3 集合完全一致率：>= {AGREEMENT_CONSISTENT} 判 consistent，"
            f">= {AGREEMENT_PARTIAL} 判 partially_consistent，否则 inconsistent"
        ),
        "not_claimed": [
            (
                "不声称两种重要度实现哪一个是错的；两者对行的加权方式不同（平均 |贡献| vs 训练 MSE "
                "下降量），所以出现不一致只是关于这两个实现的事实"
            ),
            "不声称某个特征是物理机制",
            "不声称知识纯度控制器有效；那条读数归杠杆 9",
            (
                "不声称 AB-6 的结论是错的；把修正后的置换读数与引用读数并列，是为了让结论能对着"
                "「真正关于知识池成员的数字」重新核对"
            ),
        ],
    }

HONEST_BOUNDARIES_HEAD = (
    "特征重要度不是因果：平均 |SHAP| 大，只说明模型倚重该列，与该介电响应背后的物理无关。"
)

HONEST_BOUNDARIES_TAIL = (
    "名次不能跨臂比较：hybrid 臂排的是 2061 列，知识臂排的是 10 列，同一个名次 4 在两张表里"
    "含义不同。"
)

HONEST_BOUNDARIES = (
    HONEST_BOUNDARIES_HEAD,
    (
        "本探针没有发现任何新东西。它只是用一套独立的重要度实现，在完全相同的折上重读了杠杆 9 / "
        "AB-6 的排序；若不一致，那是关于两个实现的事实，不是关于化学的新发现。"
    ),
    (
        "对照目标本身被查出有缺陷，这一点是**报告**出来的，不是绕过去的。杠杆 9 的 "
        "`permutation_importance` 洗的是 `permuted[:, position]`，`position` 来自 "
        "`enumerate(columns)`；杠杆 9 给一张 23 列矩阵只传了十个池成员名，于是真正被洗的是第 "
        "0..9 列——前十个物理列——而那十个名字只是标签。缺陷已复现到 0.0，修正后的读数与它并列"
        "给出。本探针写集之外的文件一个都没有动。"
    ),
    (
        "hybrid 是「只看 Morgan 的模型」与「只看物理列的模型」的 0.5 加权平均，不是拼接起来的特征"
        "矩阵，所以把它说成「Morgan+Physical 拼接」是错的。对特征集不相交的两个模型的线性组合，"
        "SHAP 精确可加——这正是两半能拼成一张 2061 列排序的原因。"
    ),
    (
        "SHAP 读的是模型原始 margin。计分路径在 1.0 处把平均预测向下截断；真正触到该下限的测试"
        "预测行数被记录了下来，而截断没有被求导穿过。要对它做归因，需要另立一套处理。"
    ),
    (
        "加性校验用的是相对量级。booster 以**单精度**累加 TreeSHAP 贡献，所以重建误差是 margin 的"
        "几个 1e-7——在量级 100 的 margin 上约 1e-4 绝对值——而不是 float64 的机器 epsilon。"
        "写死一个 1e-9 的绝对容差不是更严的检验，而是关于这个工具的一个假陈述。"
    ),
    (
        "任何一棵树都没分裂过的列，在每一折里的贡献都恰好为零。它的名次是并列位次里由固定列序"
        "决定的位置，不是测量值；`zero_importance_folds` 已记录，读者可据此排除这类列。"
    ),
    HONEST_BOUNDARIES_TAIL,
    (
        "符号一致性是 10 次 repeat 的折级统计量。取值 0.8 意味着有 1 次 repeat 不一致；这是披露，"
        "不是显著性检验。"
    ),
    (
        "本轮没有触碰任何新数据源。457 行 / 97 化合物的固定池、折的派发、模型规格与指标都是冻结"
        "的，冻结输入在这里是被重新摘要校验过的，而不是被断言的。"
    ),
)

NOT_CLAIMED = (
    "不声称任何被排序的特征是物理机制。",
    (
        "不声称这份 hybrid SHAP 排序证明或否证了 AB-6 的读数；报告的只是两个实现在相同折上的"
        "一致率。"
    ),
    "不声称知识纯度控制器有效，也不声称换一个 k 更优。那条读数留在杠杆 9。",
)


def build_summary(run: Mapping[str, object]) -> dict[str, object]:
    """Assemble the machine-readable summary. Every field is a reading or a digest."""

    hybrid_arm = run["hybrid_arm"]  # type: ignore[assignment]
    knowledge_arm = run["knowledge_arm"]  # type: ignore[assignment]
    hybrid_stability = run["hybrid_stability"]  # type: ignore[assignment]
    knowledge_stability = run["knowledge_stability"]  # type: ignore[assignment]
    inputs = run["inputs"]  # type: ignore[assignment]
    baseline = run["baseline"]  # type: ignore[assignment]
    permutation = run["permutation"]  # type: ignore[assignment]
    guard_records = [
        *hybrid_arm["guard_records"],
        *knowledge_arm["guard_records"],
        *permutation["guard_records"],  # type: ignore[index]
    ]
    test_rows_visible = max(
        (int(record["test_rows_visible_to_ranking"]) for record in guard_records),
        default=0,
    )
    readings = hybrid_arm["readings"]
    top10 = top_features(hybrid_stability, count=10)
    comparison = run["comparison"]  # type: ignore[assignment]
    shap_vs_quoted = comparison["readings"]["shap_vs_quoted_lever9"]
    shap_vs_corrected = comparison["readings"]["shap_vs_corrected_permutation"]
    quoted_vs_corrected = comparison["readings"]["quoted_lever9_vs_corrected_permutation"]
    headline = (
        f"冻结 hybrid 的 grouped R2 逐位复现 {REFERENCE_R2!r}，泄漏守卫 "
        f"{len(guard_records)} 次排序全部干净（`test_rows_visible_to_ranking=0`）；hybrid 侧平均"
        f"重要度最高的是 `{top10[0]['feature']}`。与 AB-6 实际引用的那张表逐折 top-3 集合一致率 "
        f"{shap_vs_quoted['exact_match_rate']:.3f}（判决 `{shap_vs_quoted['verdict']}`），"
        f"但与**修正后**的置换排序一致率 {shap_vs_corrected['exact_match_rate']:.3f}"
        f"（判决 `{shap_vs_corrected['verdict']}`）；被引用表与修正置换自身的一致率只有 "
        f"{quoted_vs_corrected['exact_match_rate']:.3f}。原因是杠杆 9 的 "
        f"`permutation_importance` 洗的是 23 列矩阵的前 10 列（物理块），却贴着知识池的十个名字，"
        f"该缺陷已复现到 `0.0`。".replace("`/`", "")
    )
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "title": TITLE,
        "generated_at_utc": str(run["generated_at_utc"]),
        "protocol": PROTOCOL,
        "importance_impl": IMPORTANCE_IMPL,
        "implementation_note": (
            "xgboost 3.4.1 的 `XGBModel.predict` 拒绝 `pred_contribs`（抛 TypeError），所以直接问"
            "拟合好的 booster：`Booster.predict(DMatrix(X), pred_contribs=True)` 返回 "
            "(n_rows, n_features + 1)，末列是 bias，必须剔除。加性残差（贡献之和 + bias - margin）"
            "在每次拟合上都检查并逐折记录；因为 booster 以单精度累加贡献，残差按 "
            "`max(|margin|, 1)` 的相对量级测量。本探针没有安装任何包；环境里没有 `shap`。"
        ),
        "seed": int(run["seed"]),
        "repeats": int(run["executed_repeats"]),
        "repeats_requested": int(run["n_repeats"]),
        "folds": int(N_SPLITS),
        "repeats_x_folds": len(hybrid_arm["guard_records"]),
        "feature_count": len(hybrid_feature_names()),
        "knowledge_feature_count": len(knowledge_feature_names()),
        "feature_columns": {
            "hybrid": list(hybrid_feature_names()),
            "knowledge": list(knowledge_feature_names()),
        },
        "feature_column_order_sha256": feature_column_order_sha256(hybrid_feature_names()),
        "knowledge_column_order_sha256": feature_column_order_sha256(knowledge_feature_names()),
        "test_rows_visible_to_ranking": int(test_rows_visible),
        "leak_guard": {
            "name": "assert_shap_ranking_scope",
            "inherits": "probes.dielectric_knowledge_purity_sweep.assert_ranking_scope",
            "error_type": RankingLeakError.__name__,
            "clauses": [
                "排序行不得是测试折的任何一行",
                "排序行必须落在训练折内部",
                "排序行必须**恰好**等于训练折（不允许静默缩域）",
                "排序行与测试折不得共享任何化合物",
            ],
            "runs_in_every_fold": True,
            "folds_checked": len(guard_records),
            "test_rows_visible_to_ranking": int(test_rows_visible),
            "max_test_rows_visible_to_ranking": int(test_rows_visible),
            "records": guard_records,
        },
        "shap_additivity": {
            "residual_definition": (
                "逐行取 |sum(phi) + bias - margin| / max(|margin|, 1) 之后取最大值"
            ),
            "tolerance": SHAP_RELATIVE_TOLERANCE,
            "fits_checked": int(hybrid_arm["fits"]) + int(knowledge_arm["fits"]),
            "max_relative_residual_hybrid_arm": float(
                hybrid_arm["max_additivity_rel_residual"]
            ),
            "max_relative_residual_knowledge_arm": float(
                knowledge_arm["max_additivity_rel_residual"]
            ),
            "max_absolute_residual_hybrid_arm": float(
                hybrid_arm["max_additivity_abs_residual"]
            ),
            "max_absolute_residual_knowledge_arm": float(
                knowledge_arm["max_additivity_abs_residual"]
            ),
            "verified": bool(
                max(
                    float(hybrid_arm["max_additivity_rel_residual"]),
                    float(knowledge_arm["max_additivity_rel_residual"]),
                )
                <= SHAP_RELATIVE_TOLERANCE
            ),
            "why": (
                "`pred_contribs` 末尾的 bias 列是被**剔除**的，而不是默认忽略的；贡献加上该 bias "
                "必须能重建拟合 margin。残差按相对量级报告，因为该工具以单精度累加"
            ),
        },
        "fold_deal": dict(run["fold_deal"]),  # type: ignore[arg-type]
        "baseline_reproduces": dict(baseline),  # type: ignore[arg-type]
        "fold_fit_matches_the_frozen_function": dict(run["faithfulness"]),  # type: ignore[arg-type]
        "readings": {HYBRID: dict(readings[HYBRID])},
        "clipped_test_predictions": int(hybrid_arm["clipped_predictions"]),
        "clipping_note": (
            "测试折预测中「两模型原始平均低于 1.0、被 np.maximum 抬到下限」的行数；SHAP 读的是"
            "截断**之前**的 margin，也就是截断实际作用的那一层"
        ),
        "arms": {
            ARM_PERMUTATION: {
                "role": (
                    "杠杆 9 的置换实现，在每折一次拟合上跑两遍：一遍按它自己的调用签名，一遍把 23 "
                    "列全部命名。它是参照臂而不是 SHAP 臂，正是它把「引用缺陷」变成一个算术事实"
                ),
                "feature_columns": len(knowledge_feature_names()),
                "fits": len(permutation["fold_order"]),  # type: ignore[index]
                "importance_implementation": "column-shuffle permutation importance",
            },
            ARM_HYBRID: {
                "role": (
                    "冻结的 v1.x 计分模型；排序是「0.5 × Morgan 位贡献」与「0.5 × 物理列贡献」"
                    "的拼接"
                ),
                "feature_columns": len(hybrid_feature_names()),
                "fits": int(hybrid_arm["fits"]),
                "max_additivity_rel_residual": float(
                    hybrid_arm["max_additivity_rel_residual"]
                ),
                "max_additivity_abs_residual": float(
                    hybrid_arm["max_additivity_abs_residual"]
                ),
            },
            ARM_KNOWLEDGE: {
                "role": (
                    "杠杆 9 的模型（冻结物理块加十个知识池成员），只对那十列做 TreeSHAP 排序；"
                    "它存在的意义是让 AB-6 的对照是特征对特征的"
                ),
                "feature_columns": len(knowledge_feature_names()),
                "fits": int(knowledge_arm["fits"]),
                "max_additivity_rel_residual": float(
                    knowledge_arm["max_additivity_rel_residual"]
                ),
                "max_additivity_abs_residual": float(
                    knowledge_arm["max_additivity_abs_residual"]
                ),
            },
        },
        "permutation_reference": dict(permutation),  # type: ignore[arg-type]
        "top10_features": top10,
        "knowledge_top10": top_features(knowledge_stability, count=10),
        "kind_totals": run["kind_totals"],
        "rank_stability": {
            ARM_HYBRID: stability_overview(
                hybrid_stability, repeats=int(run["executed_repeats"])
            ),
            ARM_KNOWLEDGE: stability_overview(
                knowledge_stability, repeats=int(run["executed_repeats"])
            ),
        },
        "comparison_to_ab6": comparison,
        "outputs": {str(key): str(value) for key, value in dict(run["outputs"]).items()},
        "honest_boundaries": list(HONEST_BOUNDARIES),
        "not_claimed": list(NOT_CLAIMED),
        "verdict": {
            "leak_guard": "clean" if int(test_rows_visible) == 0 else "leaked",
            "baseline_reproduced": bool(baseline["verified"]),
            "fold_fit_matches_the_frozen_function": bool(
                run["faithfulness"]["identical"]  # type: ignore[index]
            ),
            "ab6_agreement_vs_quoted_lever9": str(
                comparison["readings"]["shap_vs_quoted_lever9"]["verdict"]
            ),
            "ab6_agreement_vs_corrected_permutation": str(
                comparison["readings"]["shap_vs_corrected_permutation"]["verdict"]
            ),
            "reference_defect_verified": bool(
                comparison["reference_defect"]["evidence"]["replication"]["verified"]
            ),
            "headline": headline,
        },
        "inputs": dict(inputs),  # type: ignore[arg-type]
    }


def _fmt(value: object, digits: int = 6) -> str:
    number = float(str(value))
    if np.isnan(number):
        return "nan"
    if number == 0.0:
        return "0"
    if abs(number) < 1e-3 or abs(number) >= 1e6:
        return f"{number:.{digits}e}"
    return f"{number:.{digits}f}"


def _pct(value: object, digits: int = 1) -> str:
    return f"{100.0 * float(str(value)):.{digits}f}%"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the Chinese markdown report straight from the summary."""

    inputs = summary["inputs"]  # type: ignore[assignment]
    baseline = summary["baseline_reproduces"]  # type: ignore[assignment]
    comparison = summary["comparison_to_ab6"]  # type: ignore[assignment]
    match = comparison["fold_top_3_exact_match"]  # type: ignore[assignment]
    additivity = summary["shap_additivity"]  # type: ignore[assignment]
    fold_deal = summary["fold_deal"]  # type: ignore[assignment]
    stability = summary["rank_stability"]  # type: ignore[assignment]
    kind_totals = summary["kind_totals"]  # type: ignore[assignment]
    lines: list[str] = []
    lines.append(f"# {summary['title']}")
    lines.append("")
    lines.append(f"- 任务：`{summary['task']}`")
    lines.append(f"- 生成时间（UTC）：`{summary['generated_at_utc']}`")
    lines.append(
        f"- 脚本：`{inputs['script']}`（`sha256` = `{str(inputs['script_sha256'])[:16]}…`）"
    )
    lines.append(f"- 重要度实现：`{summary['importance_impl']}`")
    lines.append("")
    lines.append("## 一句话结论")
    lines.append("")
    lines.append(str(summary["verdict"]["headline"]))  # type: ignore[index]
    lines.append("")
    lines.append("## 一、协议")
    lines.append("")
    lines.append(f"- 协议原文：{summary['protocol']}")
    lines.append(
        f"- 折划分来源：`{fold_deal['source']}`；分割器 {fold_deal['splitter']}；seed "
        f"`{fold_deal['seed']}`；{fold_deal['splits']} 折（{summary['folds']} folds × "
        f"{summary['repeats']} repeats）"
    )
    lines.append(
        f"- 折划分指纹 `signature_sha256` = `{fold_deal['signature_sha256']}`；与杠杆 9 记录"
        f"的主记分牌指纹{'一致' if fold_deal['signature_sha256'] == comparison['reference']['fold_deal_signature_sha256'] else '不一致'}；"
        f"二次发牌一致：{fold_deal['reproduced_by_a_second_deal']}"
    )
    lines.append(
        f"- 特征列序：{summary['feature_count']} 列（2048 Morgan count bits + 13 physical），"
        f"`feature_column_order_sha256` = `{summary['feature_column_order_sha256']}`"
    )
    lines.append(
        f"- 池：457 行 / 97 化合物（`thermoml_zero_frequency` AND `room_temperature`），"
        f"载入 {inputs['rows_loaded']} 行，`model_ready` 门与冻结口径未改"
    )
    lines.append(
        f"- 冻结 hybrid 的 grouped R2：参照 `{baseline['reference_r2']!r}`，本轮复现 "
        f"`{baseline['reproduced_r2']!r}`，差 `{baseline['abs_difference']!r}`（容差 "
        f"`{baseline['tolerance']!r}`）→ {'复现' if baseline['verified'] else '未复现'}"
    )
    lines.append(
        f"- 手写 fold 拟合 vs 冻结评分函数：比较 {summary['fold_fit_matches_the_frozen_function']['folds_compared']} 折，"
        f"最大逐点差 `{summary['fold_fit_matches_the_frozen_function']['max_abs_difference']!r}`"
        f"（{'逐位相同' if summary['fold_fit_matches_the_frozen_function']['identical'] else '有差'}）"
    )
    lines.append("")
    lines.append("### 1.1 hybrid 不是拼接矩阵（口径澄清，不许省略）")
    lines.append("")
    lines.append(
        "冻结的 `Morgan+Physical` 不是把 2048 位 Morgan 与 13 列物理特征拼成一张 2061 列矩阵，"
        "而是**分别**拟合两个 XGBoost（一个只看 Morgan 位、一个只看物理列），再取 "
        "`0.5 * (morgan_pred + physical_pred)` 并在 1.0 处截断。SHAP 对「特征集不相交的两个模型"
        "的线性组合」是**精确可加**的，所以某一列的 hybrid 贡献恰为 `0.5 ×` 它在自己模型内的贡献；"
        "本探针就是这么拼出这 2061 列排序的，`0.5` 这个系数写在 `HYBRID_MIXING_WEIGHT` 里。"
    )
    lines.append(
        f"- 截断影响：测试折预测中被 1.0 抬起的行数 = `{summary['clipped_test_predictions']}`"
        f"（SHAP 读的是截断**之前**的 margin，这条是边界不是成就）"
    )
    lines.append("")
    lines.append("## 二、泄漏守卫")
    lines.append("")
    lines.append(
        "`assert_shap_ranking_scope` 继承杠杆 9 的 `assert_ranking_scope`（`RankingLeakError`），"
        "并加两条更强的条款：①排序所用的行必须**恰好**等于训练折（防静默缩域）；②排序所用行里"
        "不许出现任何**同时出现在测试折的化合物**（行级检查看不见的组级泄漏）。守卫在生产循环的"
        "**每一折**内运行，不是只在测试里跑。"
    )
    lines.append("")
    lines.append(
        f"- 排序次数 = `{summary['leak_guard']['folds_checked']}`"
        f"（hybrid 臂 50 + 知识臂 50 + 置换参照臂 50）"
    )
    lines.append(f"- 实测 `test_rows_visible_to_ranking` = `{summary['test_rows_visible_to_ranking']}`（逐行记录，最大值为 `{summary['leak_guard']['max_test_rows_visible_to_ranking']}`）")
    lines.append(
        f"- SHAP 加性校验：检查 {additivity['fits_checked']} 次拟合，口径 "
        f"`{additivity['residual_definition']}`，容差 `{additivity['tolerance']}`；"
        f"hybrid 臂最大**相对**残差 `{additivity['max_relative_residual_hybrid_arm']!r}`"
        f"（绝对 `{additivity['max_absolute_residual_hybrid_arm']!r}`）、知识臂最大相对残差 "
        f"`{additivity['max_relative_residual_knowledge_arm']!r}` → "
        f"{'通过' if additivity['verified'] else '不通过'}。残差之所以不是 1e-9 而是 ~1e-7 相对量级，"
        f"是因为 boosters 以单精度累加贡献——这是关于工具的事实，已在边界里写明"
    )
    lines.append("")
    lines.append("## 三、读数")
    lines.append("")
    hybrid_overview = stability[ARM_HYBRID]
    lines.append(
        f"hybrid 臂共 {hybrid_overview['features']} 列（每列 {hybrid_overview['folds_per_feature']} 折），"
        f"其中 `stable` {hybrid_overview['stable_features']} 列、`unstable` "
        f"{hybrid_overview['unstable_features']} 列；任何一棵树都没用过的列 "
        f"{hybrid_overview['features_never_used_by_any_tree']} 列。"
    )
    lines.append("")
    lines.append("### 3.1 hybrid 臂 top-10（按跨折平均重要度）")
    lines.append("")
    lines.extend(
        _table(
            ("名次", "特征", "类型", "平均重要度", "平均名次", "名次标准差", "进 top-10 折数", "符号一致率", "稳定性"),
            [
                (
                    str(entry["rank"]),
                    f"`{entry['feature']}`",
                    str(entry["feature_kind"]),
                    _fmt(entry["mean_importance"], 6),
                    _fmt(entry["mean_rank"], 2),
                    _fmt(entry["rank_std"], 2),
                    f"{entry['top_10_folds']}/50",
                    _pct(entry["sign_consistency"]),
                    str(entry["stability_label"]),
                )
                for entry in summary["top10_features"]  # type: ignore[union-attr]
            ],
        )
    )
    lines.append("")
    lines.append("### 3.2 特征家族占比（hybrid 臂）")
    lines.append("")
    lines.extend(
        _table(
            ("家族", "列数", "平均重要度合计", "重要度份额", "曾进过 top-10 的列数", "stable 列数"),
            [
                (
                    f"`{name}`",
                    str(block["features"]),
                    _fmt(block["mean_importance_total"], 4),
                    _pct(block["mean_importance_share"]),
                    str(block["in_top_10"]),
                    str(block["stable_features"]),
                )
                for name, block in sorted(kind_totals.items())
            ],
        )
    )
    lines.append("")
    lines.append("### 3.3 知识池交叉臂 top-10（同折、同模型规格、换重要度实现）")
    lines.append("")
    knowledge_rows = [
        (
            str(entry["rank"]),
            f"`{entry['feature']}`",
            _fmt(entry["mean_importance"], 6),
            _fmt(entry["mean_rank"], 2),
            _fmt(entry["rank_std"], 2),
            f"{entry['top_3_folds']}/50",
            str(entry["stability_label"]),
        )
        for entry in summary["knowledge_top10"]
    ]
    lines.extend(_table(("名次", "成员", "平均重要度", "平均名次", "名次标准差", "进 top-3 折数", "稳定性"), knowledge_rows))
    lines.append("")
    lines.append("## 四、与 AB-6 对照")
    lines.append("")
    three = "`、`".join(AB6_TOP_THREE)
    lines.append(
        f"AB-6 的三强是**知识池**成员（`{three}`），它们**不在** hybrid 的 2061 维特征空间里"
        "（那是 2048 个 Morgan 位 + 13 列物理特征）。唯一「特征对特征」的对照只能走知识臂："
        "同样的 50 折、同样的模型规格、同样的 10 列，只换重要度实现。"
    )
    lines.append("")
    readings = comparison["readings"]
    lines.append("### 4.1 三张排序并列")
    lines.append("")
    lines.extend(
        _table(
            ("对照", "逐折 top-3 集合完全一致", "一致率", "平均 Jaccard", "判决"),
            [
                (
                    name,
                    f"{block['exact_top_3_set_matches']}/{block['folds']}",
                    f"{float(block['exact_match_rate']):.3f}",
                    f"{float(block['mean_jaccard']):.3f}",
                    f"`{block['verdict']}`",
                )
                for name, block in (
                    ("SHAP（本探针） vs AB-6 实际引用的表", readings["shap_vs_quoted_lever9"]),
                    ("SHAP（本探针） vs 修正后的置换", readings["shap_vs_corrected_permutation"]),
                    ("引用表 vs 修正后的置换", readings["quoted_lever9_vs_corrected_permutation"]),
                )
            ],
        )
    )
    lines.append("")
    lines.append(
        f"- 众数 top-3：SHAP = `{'`、`'.join(match['modal_top_3_shap'])}`"
        f"（{match['modal_top_3_shap_count']}/50）；引用表 = "
        f"`{'`、`'.join(match['modal_top_3_quoted_lever9'])}`"
        f"（{match['modal_top_3_quoted_lever9_count']}/50）；修正置换 = "
        f"`{'`、`'.join(match['modal_top_3_corrected_permutation'])}`"
        f"（{match['modal_top_3_corrected_permutation_count']}/50）"
    )
    lines.append(
        f"- 手册 AB-6 五个数字与杠杆 9 机读产物复核："
        f"{'全部对上' if comparison['manual_numbers_reproduced']['all_match'] else '有对不上的'}"
        f"（容差 `{comparison['manual_numbers_reproduced']['tolerance']}`）——**复核通过不等于口径正确**："
        "它对上的是那张带标签缺陷的表。"
    )
    lines.append("")
    defect = comparison["reference_defect"]
    evidence = defect["evidence"]
    lines.append("### 4.2 引用表的缺陷（已复现到 0.0，不是代码评注）")
    lines.append("")
    lines.append(str(defect["claim"]))
    lines.append("")
    lines.append(
        f"- **复现**：{evidence['replication']['cells_compared']} 个「折 × 成员」单元，与 lever 9 存储值的"
        f"最大差 = `{evidence['replication']['max_abs_difference_vs_stored_lever9']!r}`，名次逐格相同 "
        f"`{evidence['replication']['ranks_identical']}/{evidence['replication']['cells_compared']}`"
    )
    lines.append(
        "- **位置同一性**：把 `columns` 换成「前十个物理列名」，数值最大差 = "
        f"`{evidence['positional_identity']['max_abs_difference']!r}` → 被洗的确实是矩阵第 0..9 列"
    )
    lines.append(
        "- **修正调用确有区别**：命名全部 23 列后与引用读数的最大差 = "
        f"`{evidence['corrected_call_differs']['max_abs_difference']!r}`（>0，两次测量确实不同）"
    )
    lines.append(
        f"- **名次集合也复现**：由复现分数重建的逐折 top-3 集合与 lever 9 存储名次得到的集合相同 "
        f"`{evidence['top_3_sets_reproduced_folds']}/{evidence['top_3_sets_compared_folds']}` 折"
    )
    lines.append("")
    lines.append("引用表里「成员名」与实际被洗矩阵列的对应：")
    lines.append("")
    lines.extend(
        _table(
            ("引用表里的成员名", "实际被洗的矩阵列"),
            [
                (f"`{member}`", f"`{column}`")
                for member, column in defect["label_to_column_actually_shuffled"].items()
            ],
        )
    )
    lines.append("")
    lines.append("### 4.3 十个成员的三方逐项对照")
    lines.append("")
    lines.extend(
        _table(
            (
                "成员",
                "SHAP 平均重要度",
                "SHAP 平均名次",
                "SHAP 进 top-3",
                "引用表平均重要度",
                "引用表平均名次",
                "引用表进 top-3",
                "修正置换平均重要度",
                "修正置换平均名次",
                "修正置换进 top-3",
                "引用标签背后实际被洗的列",
            ),
            [
                (
                    f"`{member}`",
                    _fmt(block["shap_mean_importance"], 4),
                    _fmt(block["shap_mean_rank"], 2),
                    f"{block['shap_top_3_folds']}/50",
                    _fmt(block["quoted_lever9_mean_importance"], 3),
                    _fmt(block["quoted_lever9_mean_rank"], 2),
                    f"{block['quoted_lever9_top_3_folds']}/50",
                    _fmt(block["corrected_permutation_mean_importance"], 3),
                    _fmt(block["corrected_permutation_mean_rank"], 2),
                    f"{block['corrected_permutation_top_3_folds']}/50",
                    f"`{block['column_actually_shuffled_behind_the_quoted_label']}`",
                )
                for member, block in sorted(
                    comparison["per_member"].items(),
                    key=lambda item: float(item[1]["shap_mean_rank"]),
                )
            ],
        )
    )
    lines.append("")
    lines.append("### 4.4 AB-6 三强与副判据在诚实口径下是否还成立")
    lines.append("")
    lines.extend(
        _table(
            ("AB-6 三强", "SHAP 进 top-3 折数", "修正置换进 top-3 折数", "引用表进 top-3 折数", "状态"),
            [
                (
                    f"`{member}`",
                    f"{block['shap_top_3_folds']}/50",
                    f"{block['corrected_permutation_top_3_folds']}/50",
                    f"{block['quoted_lever9_top_3_folds']}/50",
                    str(block["status"]),
                )
                for member, block in comparison["top_three_status"].items()
            ],
        )
    )
    lines.append("")
    statuses = [str(block["status"]) for block in comparison["top_three_status"].values()]
    lines.append(
        f"- 三强状态统计：`reproduced` {statuses.count('reproduced')}/3、"
        f"`weakened` {statuses.count('weakened')}/3、`lost` {statuses.count('lost')}/3"
    )
    counts = comparison["counts_rank_last"]
    counts_ok = all(bool(value) for value in counts["holds"].values())
    donor = counts["members"]["donor_count"]
    acceptor = counts["members"]["acceptor_count"]
    lines.append(
        f"- AB-6 副判据「线性计数垫底」（规则：{counts['rule']}）：**{'成立' if counts_ok else '不成立'}**。"
        f"`donor_count` 平均名次 SHAP `{_fmt(donor['shap_mean_rank'], 2)}` / 修正置换 "
        f"`{_fmt(donor['corrected_permutation_mean_rank'], 2)}`；`acceptor_count` "
        f"`{_fmt(acceptor['shap_mean_rank'], 2)}` / "
        f"`{_fmt(acceptor['corrected_permutation_mean_rank'], 2)}`"
    )
    lines.append("")
    lines.append("这一节**不成立**或**不许外推**的部分，逐条列出：")
    lines.append("")
    lines.extend(f"- {item}" for item in comparison["not_claimed"])
    lines.extend(f"- {item}" for item in defect["not_claimed"])
    lines.append(
        f"- 需要本探针写集之外的动作：{defect['action_required_outside_this_write_set']}"
    )
    lines.append("")
    lines.append("## 五、边界（不许省略）")
    lines.append("")
    lines.extend(f"- {item}" for item in summary["honest_boundaries"])  # type: ignore[union-attr]
    lines.append("")
    lines.append("## 六、输出物")
    lines.append("")
    lines.extend(f"- `{path}`" for path in sorted(str(item) for item in summary["outputs"].values()))  # type: ignore[union-attr]
    lines.append("")
    return lines


def write_artifacts(
    *,
    importance_rows: Sequence[Mapping[str, object]],
    stability_rows: Sequence[Mapping[str, object]],
) -> dict[str, Path]:
    outputs = {"importance": IMPORTANCE_PATH, "stability": STABILITY_PATH}
    write_csv_rows(IMPORTANCE_PATH, IMPORTANCE_COLUMNS, importance_rows)
    write_csv_rows(STABILITY_PATH, STABILITY_COLUMNS, stability_rows)
    return outputs


def _csv_text(fieldnames: Sequence[str], rows: Sequence[Mapping[str, object]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()

def run_check(
    *,
    summary_path: Path = SUMMARY_PATH,
    report_path: Path = REPORT_PATH,
    importance_path: Path = IMPORTANCE_PATH,
    stability_path: Path = STABILITY_PATH,
) -> dict[str, bool]:
    """Recompute every derived field from the stored artifacts. Nothing is refitted."""

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["importance_impl_is_the_zero_dependency_reader"] = (
        str(summary["importance_impl"]) == IMPORTANCE_IMPL
    )
    checks["script_sha256"] = (
        str(summary["inputs"]["script_sha256"]) == canonical_text_sha256(LEVER_PATH)
    )
    importance_rows = read_csv_rows(importance_path)
    per_arm_expected = {
        ARM_HYBRID: (int(summary["repeats_x_folds"]), int(summary["feature_count"])),
        ARM_KNOWLEDGE: (
            int(summary["repeats_x_folds"]),
            int(summary["knowledge_feature_count"]),
        ),
    }
    checks["importance_csv_row_count"] = len(importance_rows) == sum(
        folds * columns for folds, columns in per_arm_expected.values()
    )
    fold_lookup = {
        (int(entry["repeat"]), int(entry["fold"])): entry
        for entry in summary["fold_deal"]["per_fold"]
    }
    checks["every_fold_ranks_every_column_exactly_once"] = True
    checks["top_flags_match_rank"] = True
    checks["no_test_row_ever_entered_a_ranking"] = True
    checks["ranking_scope_matches_the_recorded_folds"] = True
    for arm, (folds_expected, columns_expected) in per_arm_expected.items():
        grouped: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
        for row in importance_rows:
            if row["arm"] == arm:
                grouped[(int(row["repeat"]), int(row["fold"]))].append(row)
        if len(grouped) != folds_expected:
            checks["every_fold_ranks_every_column_exactly_once"] = False
            continue
        for key, items in grouped.items():
            if len(items) != columns_expected:
                checks["every_fold_ranks_every_column_exactly_once"] = False
            if sorted(int(row["rank"]) for row in items) != list(range(1, len(items) + 1)):
                checks["every_fold_ranks_every_column_exactly_once"] = False
            for row in items:
                rank = int(row["rank"])
                if int(row["ranked_in_top_3"]) != (1 if rank <= 3 else 0):
                    checks["top_flags_match_rank"] = False
                if int(row["ranked_in_top_10"]) != (1 if rank <= 10 else 0):
                    checks["top_flags_match_rank"] = False
                if int(row["test_rows_visible_to_ranking"]) != 0:
                    checks["no_test_row_ever_entered_a_ranking"] = False
            record = fold_lookup.get(key)
            if record is None:
                checks["ranking_scope_matches_the_recorded_folds"] = False
                continue
            if int(items[0]["ranking_rows"]) != int(record["train_rows"]):
                checks["ranking_scope_matches_the_recorded_folds"] = False
            if int(items[0]["ranking_compounds"]) != int(record["train_compounds"]):
                checks["ranking_scope_matches_the_recorded_folds"] = False
    checks["summary_field_test_rows_visible_is_zero"] = (
        int(summary["test_rows_visible_to_ranking"]) == 0
    )
    reference = read_lever9_reference()
    checks["fold_deal_signature_agrees_with_lever_9"] = str(
        summary["fold_deal"]["signature_sha256"]
    ) == str(reference["fold_deal_signature_sha256"])
    recomputed: list[dict[str, object]] = []
    for arm, names in (
        (ARM_HYBRID, hybrid_feature_names()),
        (ARM_KNOWLEDGE, knowledge_feature_names()),
    ):
        arm_rows = [row for row in importance_rows if row["arm"] == arm]
        recomputed.extend(
            rank_stability(
                arm_rows,
                arm=arm,
                feature_names=names,
                repeats=int(summary["repeats"]),
            )
        )
    checks["stability_csv_is_the_recomputation_of_the_importance_csv"] = _csv_text(
        STABILITY_COLUMNS, recomputed
    ) == stability_path.read_bytes().decode("utf-8")
    hybrid_entries = [entry for entry in recomputed if entry["arm"] == ARM_HYBRID]
    knowledge_entries = [entry for entry in recomputed if entry["arm"] == ARM_KNOWLEDGE]
    checks["top10_features_are_the_top_rows_of_the_stability_csv"] = (
        top_features(hybrid_entries, count=10) == summary["top10_features"]
    )
    checks["knowledge_top10_matches"] = (
        top_features(knowledge_entries, count=10) == summary["knowledge_top10"]
    )
    for arm, entries in ((ARM_HYBRID, hybrid_entries), (ARM_KNOWLEDGE, knowledge_entries)):
        checks[f"rank_stability_overview[{arm}]"] = (
            stability_overview(entries, repeats=int(summary["repeats"]))
            == summary["rank_stability"][arm]
        )
    baseline = summary["baseline_reproduces"]
    recomputed_difference = abs(
        float(baseline["reproduced_r2"]) - float(baseline["reference_r2"])
    )
    checks["baseline_reproduces_arithmetic"] = (
        abs(recomputed_difference - float(baseline["abs_difference"])) <= 1e-18
        and float(baseline["reference_r2"]) == REFERENCE_R2
        and bool(baseline["verified"])
        == (recomputed_difference <= float(baseline["tolerance"]))
    )
    faithfulness = summary["fold_fit_matches_the_frozen_function"]
    checks["fold_fit_matches_the_frozen_scoring_function"] = (
        int(faithfulness["folds_compared"]) == int(summary["repeats_x_folds"])
        and float(faithfulness["max_abs_difference"]) == 0.0
        and bool(faithfulness["identical"]) is True
    )
    additivity = summary["shap_additivity"]
    checks["shap_additivity_within_tolerance"] = (
        float(additivity["max_relative_residual_hybrid_arm"])
        <= float(additivity["tolerance"])
        and float(additivity["max_relative_residual_knowledge_arm"])
        <= float(additivity["tolerance"])
        and int(additivity["fits_checked"]) == 3 * int(summary["repeats_x_folds"])
        and bool(additivity["verified"]) is True
    )
    residuals = [float(row["shap_additivity_rel_residual"]) for row in importance_rows]
    checks["artifact_residuals_are_within_tolerance"] = bool(residuals) and (
        max(residuals) <= float(additivity["tolerance"])
    )
    checks["comparison_to_ab6_is_recomputed"] = build_ab6_comparison(
        knowledge_rows=[row for row in importance_rows if row["arm"] == ARM_KNOWLEDGE],
        knowledge_stability=knowledge_entries,
        hybrid_stability=hybrid_entries,
        reference=reference,
        permutation=summary["permutation_reference"],
    ) == summary["comparison_to_ab6"]
    defect = summary["comparison_to_ab6"]["reference_defect"]["evidence"]
    checks["reference_defect_replication_is_zero"] = (
        float(defect["replication"]["max_abs_difference_vs_stored_lever9"]) == 0.0
        and int(defect["replication"]["ranks_identical"])
        == int(defect["replication"]["cells_compared"])
        and bool(defect["replication"]["verified"]) is True
    )
    checks["reference_defect_positional_identity"] = (
        float(defect["positional_identity"]["max_abs_difference"]) == 0.0
        and bool(defect["positional_identity"]["verified"]) is True
        and float(defect["corrected_call_differs"]["max_abs_difference"]) > 0.0
    )
    checks["honest_boundaries_present"] = (
        list(summary["honest_boundaries"]) == list(HONEST_BOUNDARIES)
        and list(summary["not_claimed"]) == list(NOT_CLAIMED)
    )
    try:
        rendered = "\n".join(render_report(summary)) + "\n"
        checks["report_matches_the_summary"] = (
            report_path.read_text(encoding="utf-8") == rendered
        )
    except (KeyError, TypeError):
        checks["report_matches_the_summary"] = False
    return checks


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing and model seed")
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive every field from the stored artifacts and compare; fits nothing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    if args.check:
        checks = run_check()
        print("=== week 15 hybrid SHAP --check: derived fields recomputed from the artifacts ===")
        for name, ok in checks.items():
            print(f"{'OK  ' if ok else 'FAIL'} {name}")
        failed = [name for name, ok in checks.items() if not ok]
        print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
        return 1 if failed else 0

    seed = int(args.seed)
    n_repeats = int(args.repeats)
    full_run = seed == SEED and n_repeats == N_REPEATS

    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, _temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    smiles_values = [str(row["smiles"]) for row in coverage_rows]
    knowledge, pool_report = knowledge_feature_block(smiles_values)

    splits, executed_repeats, repeat_note = scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    redeal, _, _ = scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    hybrid_arm = run_hybrid_arm(
        splits,
        morgan=morgan,
        physical=physical,
        target=target,
        groups=groups,
        seed=seed,
    )
    knowledge_arm = run_knowledge_arm(
        splits,
        physical=physical,
        knowledge=knowledge,
        target=target,
        groups=groups,
        seed=seed,
    )
    faithfulness = verify_fold_faithfulness(
        splits,
        morgan=morgan,
        physical=physical,
        target=target,
        predictions_by_fold=hybrid_arm["predictions_by_fold"],  # type: ignore[arg-type]
        seed=seed,
    )
    hybrid_stability = rank_stability(
        hybrid_arm["importance_rows"],  # type: ignore[arg-type]
        arm=ARM_HYBRID,
        feature_names=hybrid_feature_names(),
        repeats=int(executed_repeats),
    )
    knowledge_stability = rank_stability(
        knowledge_arm["importance_rows"],  # type: ignore[arg-type]
        arm=ARM_KNOWLEDGE,
        feature_names=knowledge_feature_names(),
        repeats=int(executed_repeats),
    )
    reference = read_lever9_reference()
    permutation = run_permutation_reference(
        splits,
        physical=physical,
        knowledge=knowledge,
        target=target,
        groups=groups,
        stored_rows=read_csv_rows(LEVER9_IMPORTANCE_PATH),
        seed=seed,
    )
    comparison = build_ab6_comparison(
        knowledge_rows=knowledge_arm["importance_rows"],  # type: ignore[arg-type]
        knowledge_stability=knowledge_stability,
        hybrid_stability=hybrid_stability,
        reference=reference,
        permutation=permutation,
    )
    readings = hybrid_arm["readings"]  # type: ignore[assignment]
    baseline_r2 = float(readings[HYBRID]["r2"]["mean"])
    fold_deal = {
        "splits": len(splits),
        "signature_sha256": hashlib.sha256(
            repr(fold_signature(splits)).encode("utf-8")
        ).hexdigest(),
        "scored_signature_sha256": hashlib.sha256(
            repr(scored_fold_signature(splits)).encode("utf-8")
        ).hexdigest(),
        "reproduced_by_a_second_deal": bool(fold_signature(redeal) == fold_signature(splits)),
        "executed_repeats": int(executed_repeats),
        "note": repeat_note,
        "seed": int(seed),
        "source": (
            "dielectric_knowledge_purity_sweep.scoreboard_splits（冻结主记分牌）"
        ),
        "splitter": "按 InChIKey 分组的 GroupKFold（masked_splits），测试折至少 2 行",
        "per_fold": hybrid_arm["fold_records"],
    }
    run = {
        "seed": seed,
        "n_repeats": n_repeats,
        "executed_repeats": int(executed_repeats),
        "hybrid_arm": hybrid_arm,
        "knowledge_arm": knowledge_arm,
        "faithfulness": faithfulness,
        "hybrid_stability": hybrid_stability,
        "knowledge_stability": knowledge_stability,
        "comparison": comparison,
        "permutation": permutation,
        "fold_deal": fold_deal,
        "kind_totals": kind_totals(hybrid_stability),
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline": {
            "reference_r2": REFERENCE_R2,
            "reproduced_r2": baseline_r2,
            "abs_difference": abs(baseline_r2 - REFERENCE_R2),
            "tolerance": REFERENCE_TOLERANCE,
            "verified": abs(baseline_r2 - REFERENCE_R2) <= REFERENCE_TOLERANCE,
            "full_run_configuration": bool(full_run),
            "pool": (
                f"{int(fixed_score.sum())} 行参与计分 / "
                f"{int(np.unique(np.asarray(groups)[fixed_score]).size)} 个化合物，"
                "GroupKFold by InChIKey，5 折 x 10 repeats，seed 42"
            ),
            "why": (
                "折的派发与特征块都是冻结主记分牌；这里一旦漂移，下面每一张排序描述的就不再是同一个"
                "实验"
            ),
        },
        "outputs": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "importance_csv": portable_relative_path(IMPORTANCE_PATH, root=REPOSITORY_ROOT),
            "rank_stability_csv": portable_relative_path(STABILITY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
        },
        "inputs": {
            "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
            "coverage_table_sha256": sha256_file(COVERAGE_PATH),
            "coverage_table_verified": sha256_file(COVERAGE_PATH) == COVERAGE_TABLE_SHA256,
            "frozen_dataset": portable_relative_path(FROZEN_V03_PATH, root=REPOSITORY_ROOT),
            "frozen_dataset_sha256": sha256_file(FROZEN_V03_PATH),
            "frozen_dataset_verified": sha256_file(FROZEN_V03_PATH) == FROZEN_V03_SHA256,
            "rows_loaded": len(coverage_rows),
            "scored_rows": int(fixed_score.sum()),
            "scored_compounds": int(np.unique(np.asarray(groups)[fixed_score]).size),
            "seed": int(seed),
            "repeats_requested": int(n_repeats),
            "repeats_executed": int(executed_repeats),
            "repeat_note": repeat_note,
            "script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
            "script_sha256": canonical_text_sha256(LEVER_PATH),
            "lever9_reference_summary": reference["summary_path"],
            "lever9_reference_summary_sha256": reference["summary_sha256"],
            "lever9_reference_importance": reference["importance_path"],
            "lever9_reference_importance_sha256": reference["importance_sha256"],
            "coverage_loader_dropped": dict(coverage_dropped),
            "feature_blocks": dict(feature_report),
            "knowledge_pool_report": dict(pool_report),
        },
    }
    summary = build_summary(run)
    write_artifacts(
        importance_rows=hybrid_arm["importance_rows"] + knowledge_arm["importance_rows"],  # type: ignore[operator]
        stability_rows=hybrid_stability + knowledge_stability,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(render_report(summary)) + "\n", encoding="utf-8", newline="\n")
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"task            : {TASK_ID}")
    print(f"importance impl : {IMPORTANCE_IMPL}")
    print(f"folds           : {len(splits)} (5 x {executed_repeats})")
    print(f"features        : {len(hybrid_feature_names())} hybrid / {len(knowledge_feature_names())} knowledge")
    print(f"leak guard      : test_rows_visible_to_ranking = {summary['test_rows_visible_to_ranking']}")
    print(f"baseline R2     : {baseline_r2!r} (reference {REFERENCE_R2!r})")
    print(f"AB-6 verdict    : {comparison['verdict']}")
    for name, path in summary["outputs"].items():  # type: ignore[union-attr]
        print(f"{name:16s}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())