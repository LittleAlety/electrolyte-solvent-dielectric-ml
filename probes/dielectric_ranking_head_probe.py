"""Compare an XGBoost pairwise ranking head with the frozen regression head.

C2 is evaluated on the 234-compound modelling roster from the v0.3 dielectric
benchmark. The primary query grouping is the repository's Murcko/Butina
scaffold_group_keys rule; a qid = InChIKey run is retained as a negative
control because that construction produces 234 singleton queries and removes
all pairwise training signal.

All outer and inner folds are qid-grouped. Both heads see exactly the same
row indices in every fit. The primary ranking metrics are global Spearman and
macro query-level pairwise accuracy; MAE/RMSE are reported only after the same
nested isotonic calibration is applied to both heads.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
from scipy.stats import rankdata, ttest_rel, wilcoxon
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, RepeatedKFold
from xgboost import XGBRanker, XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path
from probes.dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    SEED,
    XGB_PARAMS,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
    write_csv_rows,
)
from probes.dielectric_target_and_scaffold import scaffold_group_keys

FEATURES_PATH = REPOSITORY_ROOT / "data" / "interim" / "v03_features_original.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_ranking_head_summary.json"
PREDICTIONS_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "dielectric_ranking_head_predictions.csv"
)
METRICS_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "dielectric_ranking_head_metrics.csv"
)
QID_AUDIT_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "dielectric_ranking_head_qid_audit.csv"
)

PRIMARY_SCENARIO = "scaffold_butina_qid"
NEGATIVE_SCENARIO = "inchikey_singleton_negative_control"
SCENARIOS = (PRIMARY_SCENARIO, NEGATIVE_SCENARIO)
ARMS = ("rank_pairwise", "regression_head")
REPRESENTATION = "Morgan_count_r2_2048 + physical_13"
N_INNER_SPLITS = 5
BOOTSTRAP_ITERATIONS = 500
BOOTSTRAP_SEED = 20260924

RANK_PARAMS = {
    **XGB_PARAMS,
    "objective": "rank:pairwise",
    "lambdarank_pair_method": "mean",
}

METRIC_COLUMNS = (
    "scenario",
    "arm",
    "split_id",
    "repeat",
    "fold",
    "train_rows",
    "test_rows",
    "train_qids",
    "test_qids",
    "train_pair_capacity",
    "test_pair_capacity",
    "n_comparable_pairs",
    "global_spearman",
    "macro_query_spearman",
    "micro_pairwise_accuracy",
    "macro_pairwise_accuracy",
    "auc_gt15",
    "auc_gt30",
    "calibrated_mae",
    "calibrated_rmse",
    "calibrated_r2",
)
PREDICTION_COLUMNS = (
    "scenario",
    "arm",
    "split_id",
    "repeat",
    "fold",
    "inchikey",
    "qid",
    "target",
    "raw_score",
    "calibrated_epsilon",
    "target_stratum",
)
QID_AUDIT_COLUMNS = (
    "scenario",
    "qid",
    "size",
    "singleton",
    "n_ring",
    "n_acyclic",
    "unique_inchikeys",
    "pair_capacity",
    "smiles_examples",
)
SUMMARY_METRICS = (
    "global_spearman",
    "macro_query_spearman",
    "micro_pairwise_accuracy",
    "macro_pairwise_accuracy",
    "auc_gt15",
    "auc_gt30",
    "calibrated_mae",
    "calibrated_rmse",
    "calibrated_r2",
)


@dataclass(frozen=True)
class SplitSpec:
    """One outer or inner qid-grouped split."""

    split_id: int
    repeat: int
    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_qids: frozenset[str]
    test_qids: frozenset[str]


def _json_default(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return portable_relative_path(value, root=REPOSITORY_ROOT)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


def write_json_lf(path: Path, payload: object) -> None:
    """Write JSON with explicit LF endings and no non-finite literals.

    Path.write_text translates the newline to os.linesep on Windows, which would
    make the artifact bytes depend on the host platform. Non-finite floats are
    converted to null first because bare NaN and Infinity are not valid JSON.
    """

    text = (
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        if not np.isfinite(numeric):
            return "nan"
        return f"{numeric:.12g}"
    return str(value)


def _finite_mean(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    return float(np.mean(array)) if array.size else float("nan")


def _safe_spearman(target: np.ndarray, score: np.ndarray) -> float:
    target = np.asarray(target, dtype=float)
    score = np.asarray(score, dtype=float)
    if target.size < 2 or np.unique(target).size < 2 or np.unique(score).size < 2:
        return float("nan")
    target_rank = rankdata(target, method="average")
    score_rank = rankdata(score, method="average")
    return float(np.corrcoef(target_rank, score_rank)[0, 1])


def _safe_auc(target: np.ndarray, score: np.ndarray, threshold: float) -> float:
    labels = np.asarray(target, dtype=float) > threshold
    if np.unique(labels).size < 2:
        return float("nan")
    return float(roc_auc_score(labels, score))


def _pairwise_accuracy(
    target: np.ndarray,
    score: np.ndarray,
) -> tuple[int, float]:
    """Return comparable-pair count and pairwise accuracy.

    Target ties are excluded. A predicted tie contributes 0.5 rather than
    silently favouring either direction.
    """

    target = np.asarray(target, dtype=float)
    score = np.asarray(score, dtype=float)
    pair_count = 0
    credit = 0.0
    for right in range(1, target.size):
        for left in range(right):
            delta_target = target[right] - target[left]
            if delta_target == 0.0:
                continue
            pair_count += 1
            margin = (score[right] - score[left]) * delta_target
            if margin > 0.0:
                credit += 1.0
            elif margin == 0.0:
                credit += 0.5
    if pair_count == 0:
        return 0, float("nan")
    return pair_count, float(credit / pair_count)


def _pairwise_metrics(
    target: np.ndarray,
    score: np.ndarray,
    group_values: Sequence[str],
) -> tuple[int, float, float]:
    groups = np.asarray(group_values, dtype=object)
    if groups.shape[0] != target.shape[0]:
        raise ValueError("group_values must align with target")
    total_pairs = 0
    total_credit = 0.0
    per_query: list[float] = []
    for qid in sorted(set(groups.tolist())):
        mask = groups == qid
        pair_count, accuracy = _pairwise_accuracy(target[mask], score[mask])
        if pair_count == 0:
            continue
        total_pairs += pair_count
        total_credit += accuracy * pair_count
        per_query.append(accuracy)
    micro = total_credit / total_pairs if total_pairs else float("nan")
    macro = float(np.mean(per_query)) if per_query else float("nan")
    return total_pairs, micro, macro


def ranking_metrics(
    target: Sequence[float],
    raw_score: Sequence[float],
    group_values: Sequence[str],
    calibrated_epsilon: Sequence[float],
) -> dict[str, float | int]:
    """Compute scale-free ranking metrics plus calibrated regression metrics."""

    target_array = np.asarray(target, dtype=float)
    score_array = np.asarray(raw_score, dtype=float)
    calibrated = np.asarray(calibrated_epsilon, dtype=float)
    groups = np.asarray(group_values, dtype=object)
    if not (
        target_array.shape == score_array.shape == calibrated.shape == groups.shape
    ):
        raise ValueError("metric inputs must have identical shapes")
    if not np.isfinite(target_array).all() or not np.isfinite(score_array).all():
        raise ValueError("target and raw scores must be finite")
    if not np.isfinite(calibrated).all():
        raise ValueError("calibrated predictions must be finite")

    query_spearman: list[float] = []
    for qid in sorted(set(groups.tolist())):
        mask = groups == qid
        value = _safe_spearman(target_array[mask], score_array[mask])
        if np.isfinite(value):
            query_spearman.append(value)
    pair_count, micro_pairwise, macro_pairwise = _pairwise_metrics(
        target_array,
        score_array,
        groups,
    )
    return {
        "n_comparable_pairs": pair_count,
        "global_spearman": _safe_spearman(target_array, score_array),
        "macro_query_spearman": (
            float(np.mean(query_spearman)) if query_spearman else float("nan")
        ),
        "micro_pairwise_accuracy": micro_pairwise,
        "macro_pairwise_accuracy": macro_pairwise,
        "auc_gt15": _safe_auc(target_array, score_array, 15.0),
        "auc_gt30": _safe_auc(target_array, score_array, 30.0),
        "calibrated_mae": float(
            mean_absolute_error(target_array, calibrated)
        ),
        "calibrated_rmse": float(
            np.sqrt(mean_squared_error(target_array, calibrated))
        ),
        "calibrated_r2": (
            float(r2_score(target_array, calibrated))
            if target_array.size >= 2 and np.unique(target_array).size >= 2
            else float("nan")
        ),
    }


def _indices_for_qids(
    qid_values: Sequence[str],
    selected_qids: set[str] | frozenset[str],
) -> np.ndarray:
    return np.asarray(
        [
            index
            for index, qid in enumerate(qid_values)
            if qid in selected_qids
        ],
        dtype=int,
    )


def build_group_splits(
    qid_values: Sequence[str],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> list[SplitSpec]:
    """Run RepeatedKFold over qids, then expand qids back to row indices."""

    qids = sorted(set(qid_values))
    if len(qids) < n_splits:
        raise ValueError("not enough qids for the requested split count")
    splitter = RepeatedKFold(
        n_splits=n_splits,
        n_repeats=n_repeats,
        random_state=seed,
    )
    result: list[SplitSpec] = []
    for split_id, (train_positions, test_positions) in enumerate(
        splitter.split(np.zeros(len(qids)))
    ):
        train_qids = frozenset(qids[int(index)] for index in train_positions)
        test_qids = frozenset(qids[int(index)] for index in test_positions)
        if train_qids & test_qids:
            raise AssertionError("train and test qids overlap")
        train_indices = _indices_for_qids(qid_values, train_qids)
        test_indices = _indices_for_qids(qid_values, test_qids)
        if not np.array_equal(
            np.sort(np.concatenate((train_indices, test_indices))),
            np.arange(len(qid_values)),
        ):
            raise AssertionError("split does not cover every row exactly once")
        result.append(
            SplitSpec(
                split_id=split_id,
                repeat=split_id // n_splits,
                fold=split_id % n_splits,
                train_indices=train_indices,
                test_indices=test_indices,
                train_qids=train_qids,
                test_qids=test_qids,
            )
        )
    for repeat in range(n_repeats):
        repeat_splits = [split for split in result if split.repeat == repeat]
        if set().union(*(split.test_qids for split in repeat_splits)) != set(qids):
            raise AssertionError("one repeat does not test every qid exactly once")
    return result


def pair_capacity(qid_values: Sequence[str], indices: Sequence[int]) -> int:
    counts = Counter(qid_values[int(index)] for index in indices)
    return int(sum(size * (size - 1) // 2 for size in counts.values()))


def qid_summary(qid_values: Sequence[str]) -> dict[str, int]:
    counts = Counter(qid_values)
    return {
        "qid_count": len(counts),
        "singleton_count": sum(size == 1 for size in counts.values()),
        "total_pair_capacity": int(
            sum(size * (size - 1) // 2 for size in counts.values())
        ),
    }


def qid_audit_rows(
    scenario: str,
    qid_values: Sequence[str],
    inchikeys: Sequence[str],
    smiles_values: Sequence[str],
) -> list[dict[str, object]]:
    indices_by_qid: dict[str, list[int]] = defaultdict(list)
    for index, qid in enumerate(qid_values):
        indices_by_qid[qid].append(index)
    rows: list[dict[str, object]] = []
    for qid, indices in sorted(indices_by_qid.items()):
        size = len(indices)
        rows.append(
            {
                "scenario": scenario,
                "qid": qid,
                "size": size,
                "singleton": size == 1,
                "n_ring": sum(qid.startswith("ring:") for _ in indices),
                "n_acyclic": sum(qid.startswith("acyclic_cluster:") for _ in indices),
                "unique_inchikeys": len(
                    {inchikeys[index] for index in indices}
                ),
                "pair_capacity": size * (size - 1) // 2,
                "smiles_examples": ";".join(
                    smiles_values[index] for index in indices[:3]
                ),
            }
        )
    return rows


def fit_regression_head(
    features: np.ndarray,
    target: np.ndarray,
    *,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> np.ndarray:
    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(features[train_indices], target[train_indices])
    return np.asarray(model.predict(features[test_indices]), dtype=float)


def fit_rank_pairwise_head(
    features: np.ndarray,
    target: np.ndarray,
    qid_codes: np.ndarray,
    inchikeys: np.ndarray,
    *,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> np.ndarray:
    sort_order = np.lexsort(
        (
            np.asarray(inchikeys)[train_indices],
            np.asarray(qid_codes)[train_indices],
        )
    )
    ordered_train = train_indices[sort_order]
    ordered_qids = np.asarray(qid_codes)[ordered_train]
    group_sizes = np.unique(ordered_qids, return_counts=True)[1]
    params = {**RANK_PARAMS, "random_state": seed}
    model = XGBRanker(**params)
    model.fit(
        features[ordered_train],
        target[ordered_train],
        group=group_sizes,
    )
    return np.asarray(model.predict(features[test_indices]), dtype=float)


def fit_outer_heads(
    features: np.ndarray,
    target: np.ndarray,
    qid_codes: np.ndarray,
    inchikeys: np.ndarray,
    *,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit both heads on exactly the same outer train/test row indices."""

    regression_score = fit_regression_head(
        features,
        target,
        train_indices=train_indices,
        test_indices=test_indices,
        seed=seed,
    )
    rank_score = fit_rank_pairwise_head(
        features,
        target,
        qid_codes,
        inchikeys,
        train_indices=train_indices,
        test_indices=test_indices,
        seed=seed,
    )
    return regression_score, rank_score


def _inner_splits(
    train_indices: np.ndarray,
    qid_values: Sequence[str],
    *,
    split_id: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    train_qids = sorted({qid_values[int(index)] for index in train_indices})
    n_splits = min(N_INNER_SPLITS, len(train_qids))
    splitter = KFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=SEED + split_id,
    )
    result: list[tuple[np.ndarray, np.ndarray]] = []
    for train_positions, test_positions in splitter.split(np.zeros(len(train_qids))):
        inner_train_qids = {
            train_qids[int(index)] for index in train_positions
        }
        inner_test_qids = {
            train_qids[int(index)] for index in test_positions
        }
        result.append(
            (
                _indices_for_qids(qid_values, inner_train_qids),
                _indices_for_qids(qid_values, inner_test_qids),
            )
        )
    return result


def nested_isotonic_calibration(
    features: np.ndarray,
    target: np.ndarray,
    qid_values: Sequence[str],
    qid_codes: np.ndarray,
    inchikeys: np.ndarray,
    outer_test_scores: Mapping[str, np.ndarray],
    *,
    outer_train_indices: np.ndarray,
    outer_test_indices: np.ndarray,
    outer_split_id: int,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Create inner OOF scores, then calibrate the supplied outer test scores.

    The outer test targets never enter the isotonic fit.
    """

    raw_oof = {
        arm: np.full(len(target), np.nan, dtype=float) for arm in ARMS
    }
    inner_splits = _inner_splits(
        outer_train_indices,
        qid_values,
        split_id=outer_split_id,
    )
    for inner_fold, (inner_train, inner_test) in enumerate(inner_splits):
        inner_seed = SEED + outer_split_id * (N_INNER_SPLITS + 1) + inner_fold
        regression_score, rank_score = fit_outer_heads(
            features,
            target,
            qid_codes,
            inchikeys,
            train_indices=inner_train,
            test_indices=inner_test,
            seed=inner_seed,
        )
        raw_oof["regression_head"][inner_test] = regression_score
        raw_oof["rank_pairwise"][inner_test] = rank_score

    calibrated: dict[str, np.ndarray] = {}
    diagnostics: dict[str, object] = {}
    for arm in ARMS:
        train_scores = raw_oof[arm][outer_train_indices]
        if not np.isfinite(train_scores).all():
            raise AssertionError(f"{arm} inner OOF scores are incomplete")
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(train_scores, target[outer_train_indices])
        fitted = calibrator.predict(train_scores)
        outer_score = np.asarray(outer_test_scores[arm], dtype=float)
        if outer_score.shape != outer_test_indices.shape:
            raise ValueError("outer scores do not align with outer test indices")
        calibrated[arm] = np.maximum(calibrator.predict(outer_score), 1.0)
        diagnostics[arm] = {
            "oof_score_count": int(np.isfinite(train_scores).sum()),
            "fitted_value_count": int(np.unique(fitted).size),
            "outer_score_count": int(outer_score.size),
        }
    return calibrated, {
        "inner_n_splits": len(inner_splits),
        "inner_grouping": "qid",
        "outer_test_target_used_for_calibration": False,
        "calibrator": "IsotonicRegression(out_of_bounds=clip)",
        "diagnostics_by_arm": diagnostics,
    }


def _target_stratum(value: float) -> str:
    if value < 20.0:
        return "lt20"
    if value <= 60.0:
        return "20_60"
    return "gt60"


def _metrics_from_records(
    records: Sequence[Mapping[str, object]],
    *,
    group_labels: Sequence[str] | None = None,
) -> dict[str, float | int]:
    if not records:
        raise ValueError("cannot compute metrics for an empty record set")
    target = np.asarray([record["target"] for record in records], dtype=float)
    raw_score = np.asarray([record["raw_score"] for record in records], dtype=float)
    calibrated = np.asarray(
        [record["calibrated_epsilon"] for record in records],
        dtype=float,
    )
    groups = (
        list(group_labels)
        if group_labels is not None
        else [str(record["qid"]) for record in records]
    )
    return ranking_metrics(target, raw_score, groups, calibrated)


def _summarize_metric(
    values: Sequence[float],
) -> dict[str, float | int | None]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0,
        "n": int(finite.size),
    }


def _paired_stats(
    baseline: Sequence[float],
    challenger: Sequence[float],
) -> dict[str, object]:
    base = np.asarray(baseline, dtype=float)
    challenger_array = np.asarray(challenger, dtype=float)
    if base.shape != challenger_array.shape:
        raise ValueError("paired arrays must have the same shape")
    mask = np.isfinite(base) & np.isfinite(challenger_array)
    base = base[mask]
    challenger_array = challenger_array[mask]
    delta = challenger_array - base
    if delta.size == 0:
        return {
            "n_pairs": 0,
            "delta_mean": None,
            "delta_ci95": [None, None],
            "paired_t_pvalue": None,
            "wilcoxon_pvalue": None,
            "per_repeat_delta": [],
        }
    mean = float(np.mean(delta))
    if delta.size > 1:
        std = float(np.std(delta, ddof=1))
        half_width = float(1.96 * std / np.sqrt(delta.size))
        t_pvalue = float(ttest_rel(challenger_array, base).pvalue)
        wilcoxon_pvalue = (
            float(wilcoxon(challenger_array, base).pvalue)
            if np.any(delta != 0.0)
            else float("nan")
        )
    else:
        half_width = 0.0
        t_pvalue = float("nan")
        wilcoxon_pvalue = float("nan")
    return {
        "n_pairs": int(delta.size),
        "delta_mean": mean,
        "delta_ci95": [mean - half_width, mean + half_width],
        "paired_t_pvalue": t_pvalue,
        "wilcoxon_pvalue": wilcoxon_pvalue,
        "per_repeat_delta": [float(value) for value in delta],
    }


def _repeat_metrics(
    predictions: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, float | int]]]:
    by_arm: dict[str, list[dict[str, float | int]]] = {
        arm: [] for arm in ARMS
    }
    for repeat in range(N_REPEATS):
        for arm in ARMS:
            records = [
                record
                for record in predictions
                if record["arm"] == arm and record["repeat"] == repeat
            ]
            if len(records) != 234:
                raise AssertionError(
                    f"{arm} repeat {repeat} does not hold 234 test rows"
                )
            by_arm[arm].append(_metrics_from_records(records))
    return by_arm


def _bootstrap_records(
    predictions: Sequence[Mapping[str, object]],
    *,
    metric: str,
    iterations: int,
    seed: int,
) -> dict[str, object]:
    """Cluster-bootstrap the paired delta, resampling whole qids."""

    qids = sorted({str(record["qid"]) for record in predictions})
    if not qids:
        raise ValueError("no qids available for bootstrap")
    cells: dict[tuple[str, int, str], list[Mapping[str, object]]] = defaultdict(list)
    for record in predictions:
        cells[
            (
                str(record["arm"]),
                int(record["repeat"]),
                str(record["qid"]),
            )
        ].append(record)

    def metric_for_arm(
        arm: str,
        repeat: int,
        sampled_positions: np.ndarray,
    ) -> float:
        records: list[Mapping[str, object]] = []
        labels: list[str] = []
        for occurrence, qid_position in enumerate(sampled_positions):
            qid = qids[int(qid_position)]
            cell = cells.get((arm, repeat, qid), [])
            records.extend(cell)
            labels.extend([f"{occurrence}:{qid}"] * len(cell))
        if not records:
            return float("nan")
        return float(_metrics_from_records(records, group_labels=labels)[metric])

    rng = np.random.default_rng(seed)
    bootstrap_values = np.full(iterations, np.nan, dtype=float)
    for iteration in range(iterations):
        sampled = rng.integers(0, len(qids), size=len(qids))
        repeat_deltas: list[float] = []
        for repeat in range(N_REPEATS):
            regression_value = metric_for_arm(
                "regression_head",
                repeat,
                sampled,
            )
            rank_value = metric_for_arm(
                "rank_pairwise",
                repeat,
                sampled,
            )
            if np.isfinite(regression_value) and np.isfinite(rank_value):
                repeat_deltas.append(rank_value - regression_value)
        if repeat_deltas:
            bootstrap_values[iteration] = float(np.mean(repeat_deltas))
    finite = bootstrap_values[np.isfinite(bootstrap_values)]
    if finite.size == 0:
        ci95 = [None, None]
    else:
        ci95 = [
            float(np.quantile(finite, 0.025)),
            float(np.quantile(finite, 0.975)),
        ]
    identity = np.arange(len(qids))
    regression_point = _finite_mean(
        [
            metric_for_arm("regression_head", repeat, identity)
            for repeat in range(N_REPEATS)
        ]
    )
    rank_point = _finite_mean(
        [
            metric_for_arm("rank_pairwise", repeat, identity)
            for repeat in range(N_REPEATS)
        ]
    )
    return {
        "metric": metric,
        "baseline_arm": "regression_head",
        "challenger_arm": "rank_pairwise",
        "point_delta_challenger_minus_baseline": (
            rank_point - regression_point
            if np.isfinite(rank_point) and np.isfinite(regression_point)
            else None
        ),
        "cluster_bootstrap_ci95": ci95,
        "n_bootstrap": int(finite.size),
        "cluster_unit": "qid",
        "seed": seed,
    }


def run_scenario(
    scenario: str,
    *,
    features: np.ndarray,
    target: np.ndarray,
    qid_values: Sequence[str],
    qid_codes: np.ndarray,
    inchikeys: np.ndarray,
    smiles_values: Sequence[str],
    bootstrap_iterations: int,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    splits = build_group_splits(qid_values)
    prediction_records: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    constant_score_splits = {arm: 0 for arm in ARMS}

    for split in splits:
        if split.train_qids & split.test_qids:
            raise AssertionError("outer split leaks qids")
        regression_score, rank_score = fit_outer_heads(
            features,
            target,
            qid_codes,
            inchikeys,
            train_indices=split.train_indices,
            test_indices=split.test_indices,
            seed=SEED + split.split_id,
        )
        score_by_arm = {
            "rank_pairwise": rank_score,
            "regression_head": regression_score,
        }
        calibrated, calibration_diagnostics = nested_isotonic_calibration(
            features,
            target,
            qid_values,
            qid_codes,
            inchikeys,
            score_by_arm,
            outer_train_indices=split.train_indices,
            outer_test_indices=split.test_indices,
            outer_split_id=split.split_id,
        )
        for arm in ARMS:
            scores = score_by_arm[arm]
            if np.unique(scores).size == 1:
                constant_score_splits[arm] += 1
            metrics = ranking_metrics(
                target[split.test_indices],
                scores,
                [qid_values[index] for index in split.test_indices],
                calibrated[arm],
            )
            metric_rows.append(
                {
                    "scenario": scenario,
                    "arm": arm,
                    "split_id": split.split_id,
                    "repeat": split.repeat,
                    "fold": split.fold,
                    "train_rows": int(split.train_indices.size),
                    "test_rows": int(split.test_indices.size),
                    "train_qids": len(split.train_qids),
                    "test_qids": len(split.test_qids),
                    "train_pair_capacity": pair_capacity(
                        qid_values,
                        split.train_indices,
                    ),
                    "test_pair_capacity": pair_capacity(
                        qid_values,
                        split.test_indices,
                    ),
                    **metrics,
                }
            )
            for local_index, row_index in enumerate(split.test_indices):
                prediction_records.append(
                    {
                        "scenario": scenario,
                        "arm": arm,
                        "split_id": split.split_id,
                        "repeat": split.repeat,
                        "fold": split.fold,
                        "inchikey": str(inchikeys[row_index]),
                        "qid": str(qid_values[row_index]),
                        "target": float(target[row_index]),
                        "raw_score": float(scores[local_index]),
                        "calibrated_epsilon": float(calibrated[arm][local_index]),
                        "target_stratum": _target_stratum(float(target[row_index])),
                    }
                )

    repeat_metrics = _repeat_metrics(prediction_records)
    summary_by_arm: dict[str, object] = {}
    for arm in ARMS:
        metric_summary = {
            metric: _summarize_metric(
                [float(row[metric]) for row in repeat_metrics[arm]]
            )
            for metric in SUMMARY_METRICS
        }
        pooled = _metrics_from_records(
            [record for record in prediction_records if record["arm"] == arm]
        )
        summary_by_arm[arm] = {
            "per_repeat_metric_summary": metric_summary,
            "pooled_across_all_50_test_folds": pooled,
            "constant_score_split_count": constant_score_splits[arm],
            "n_splits": len(splits),
        }

    paired_diagnostics = {}
    for metric in (
        "global_spearman",
        "macro_pairwise_accuracy",
        "calibrated_mae",
    ):
        paired_diagnostics[metric] = _paired_stats(
            [float(row[metric]) for row in repeat_metrics["regression_head"]],
            [float(row[metric]) for row in repeat_metrics["rank_pairwise"]],
        )

    bootstrap = {
        metric: _bootstrap_records(
            prediction_records,
            metric=metric,
            iterations=bootstrap_iterations,
            seed=BOOTSTRAP_SEED + split_index,
        )
        for split_index, metric in enumerate(
            (
                "global_spearman",
                "macro_pairwise_accuracy",
                "calibrated_mae",
            )
        )
    }

    train_capacities = [
        int(row["train_pair_capacity"]) for row in metric_rows
    ]
    test_capacities = [int(row["test_pair_capacity"]) for row in metric_rows]
    qid_stats = qid_summary(qid_values)
    summary = {
        "scenario": scenario,
        "qid_rule": (
            "Murcko scaffold for cyclic molecules; ECFP4 Morgan radius=2, "
            "Tanimoto distance <= 0.5 Butina clusters for acyclic molecules"
            if scenario == PRIMARY_SCENARIO
            else "qid = InChIKey negative control"
        ),
        **qid_stats,
        "train_pair_capacity_min": min(train_capacities),
        "train_pair_capacity_median": float(np.median(train_capacities)),
        "train_pair_capacity_max": max(train_capacities),
        "test_pair_capacity_min": min(test_capacities),
        "test_pair_capacity_max": max(test_capacities),
        "results": summary_by_arm,
        "paired_repeat_diagnostics_rank_minus_regression": paired_diagnostics,
        "qid_cluster_bootstrap_rank_minus_regression": bootstrap,
        "calibration_example_diagnostics": calibration_diagnostics,
        "negative_results": [
            (
                f"{qid_stats['singleton_count']} of "
                f"{qid_stats['qid_count']} qids are singletons and contribute "
                "no pairwise training gradient"
            ),
            (
                f"the minimum train-fold pair capacity over all 50 splits is "
                f"{min(train_capacities)}; the earlier audit shorthand of "
                "approximately 277 was the repeat-0 minimum and is not the "
                "global minimum across all repeats"
            ),
            (
                "all 234 InChIKey queries are singleton in the negative "
                "control, so rank:pairwise has no comparable training pair"
            ),
        ],
        "split_manifest_assertions": {
            "train_test_qid_disjoint": True,
            "each_repeat_tests_every_qid_once": True,
            "both_heads_use_identical_outer_and_inner_row_indices": True,
            "outer_and_inner_grouping": "qid",
        },
    }
    if scenario == NEGATIVE_SCENARIO:
        summary["rank_degeneracy"] = {
            "rank_constant_score_split_count": constant_score_splits[
                "rank_pairwise"
            ],
            "rank_constant_score_split_fraction": (
                constant_score_splits["rank_pairwise"] / len(splits)
            ),
        }
    return summary, prediction_records, metric_rows


def _serialize_prediction_rows(
    predictions: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {column: _format_value(record[column]) for column in PREDICTION_COLUMNS}
        for record in predictions
    ]


def _serialize_metric_rows(
    metric_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {column: _format_value(row[column]) for column in METRIC_COLUMNS}
        for row in metric_rows
    ]


def _decision(scenario_summary: Mapping[str, object]) -> dict[str, object]:
    bootstrap = scenario_summary["qid_cluster_bootstrap_rank_minus_regression"]
    if not isinstance(bootstrap, Mapping):
        raise TypeError("bootstrap summary must be a mapping")
    macro_ci = bootstrap["macro_pairwise_accuracy"]["cluster_bootstrap_ci95"]
    spearman_ci = bootstrap["global_spearman"]["cluster_bootstrap_ci95"]
    mae_ci = bootstrap["calibrated_mae"]["cluster_bootstrap_ci95"]
    ranking_established = (
        macro_ci[0] is not None
        and macro_ci[1] is not None
        and float(macro_ci[0]) > 0.0
        and spearman_ci[0] is not None
        and spearman_ci[1] is not None
        and float(spearman_ci[0]) > 0.0
    )
    calibration_established = (
        mae_ci[0] is not None
        and mae_ci[1] is not None
        and float(mae_ci[1]) < 0.0
    )
    if ranking_established and calibration_established:
        label = "rank_pairwise_superior_by_pre_registered_criteria"
    elif ranking_established:
        label = "rank_pairwise_ranking_gain_without_calibrated_mae_gain"
    else:
        label = "no_established_rank_pairwise_advantage"
    return {
        "label": label,
        "pre_registered_rule": (
            "rank head is declared superior only when the 95% qid-cluster "
            "bootstrap CI for both macro pairwise accuracy and global Spearman "
            "is strictly above zero, and the corresponding calibrated-MAE CI "
            "is strictly below zero; otherwise the advantage is not established"
        ),
        "macro_pairwise_accuracy_ci95": macro_ci,
        "global_spearman_ci95": spearman_ci,
        "calibrated_mae_ci95": mae_ci,
        "ranking_gain_established": ranking_established,
        "calibration_gain_established": calibration_established,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument("--metrics", type=Path, default=METRICS_PATH)
    parser.add_argument("--qid-audit", type=Path, default=QID_AUDIT_PATH)
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=BOOTSTRAP_ITERATIONS,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    modelling_rows, failed_rows, withheld_rows = read_modelling_rows(args.features)
    if len(modelling_rows) != 234:
        raise ValueError(
            f"frozen C2 benchmark must contain 234 rows, found {len(modelling_rows)}"
        )
    target = np.asarray(
        [float(row["dielectric"]) for row in modelling_rows],
        dtype=float,
    )
    smiles_values = [row["smiles"] for row in modelling_rows]
    inchikeys = np.asarray(
        [row["inchikey"] for row in modelling_rows],
        dtype=object,
    )
    morgan = morgan_count_features(smiles_values)
    physical = physical_feature_matrix(modelling_rows)
    features = np.hstack((morgan, physical))
    scaffold_qid_values = scaffold_group_keys(smiles_values)
    negative_qid_values = [str(value) for value in inchikeys]
    qid_values_by_scenario = {
        PRIMARY_SCENARIO: scaffold_qid_values,
        NEGATIVE_SCENARIO: negative_qid_values,
    }

    audit_rows: list[dict[str, object]] = []
    scenario_summaries: dict[str, object] = {}
    all_predictions: list[dict[str, object]] = []
    all_metrics: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        qid_values = qid_values_by_scenario[scenario]
        qids = sorted(set(qid_values))
        qid_codes = np.asarray(
            [qids.index(qid) for qid in qid_values],
            dtype=int,
        )
        audit_rows.extend(
            qid_audit_rows(
                scenario,
                qid_values,
                [str(value) for value in inchikeys],
                smiles_values,
            )
        )
        scenario_summary, prediction_records, metric_rows = run_scenario(
            scenario,
            features=features,
            target=target,
            qid_values=qid_values,
            qid_codes=qid_codes,
            inchikeys=inchikeys,
            smiles_values=smiles_values,
            bootstrap_iterations=args.bootstrap_iterations,
        )
        scenario_summaries[scenario] = scenario_summary
        all_predictions.extend(prediction_records)
        all_metrics.extend(metric_rows)

    primary_summary = scenario_summaries[PRIMARY_SCENARIO]
    decision = _decision(primary_summary)
    primary_qid_stats = {
        key: primary_summary[key]
        for key in ("qid_count", "singleton_count", "total_pair_capacity")
    }
    if primary_qid_stats != {
        "qid_count": 111,
        "singleton_count": 76,
        "total_pair_capacity": 799,
    }:
        raise AssertionError(
            "primary qid audit differs from the frozen expected counts"
        )

    payload = {
        "schema_version": 1,
        "probe": "C2 XGBoost rank:pairwise versus regression head",
        "input_sha256": canonical_text_sha256(args.features),
        "source_code_sha256": canonical_text_sha256(Path(__file__).resolve()),
        "source_code_path": portable_relative_path(
            Path(__file__).resolve(),
            root=REPOSITORY_ROOT,
        ),
        "counts": {
            "modelling_rows": len(modelling_rows),
            "failed_feature_rows": len(failed_rows),
            "withheld_not_model_ready_rows": len(withheld_rows),
            "feature_count": int(features.shape[1]),
        },
        "representation": REPRESENTATION,
        "splitter": {
            "outer": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
            "split_level": "qid",
            "inner": "KFold(n_splits=5, shuffle=True, random_state=42+split_id)",
            "methodology_note": (
                "C2 的 5x10x42 在 qid 层运行，不是 v0.3 行级 fold 表的逐行复用。"
            ),
        },
        "qid_rule": {
            "primary": (
                "ring molecules use ring:{MurckoScaffoldSmiles}; acyclic "
                "molecules use acyclic_cluster:{Butina cluster id} from "
                "ECFP4 Morgan radius=2 and Tanimoto distance threshold 0.5"
            ),
            "negative_control": "qid = InChIKey",
            "source": "probes.dielectric_target_and_scaffold.scaffold_group_keys",
        },
        **primary_qid_stats,
        "rank_objective": "rank:pairwise",
        "rank_params": {
            **{key: value for key, value in RANK_PARAMS.items() if key != "random_state"},
            "random_state": "SEED + split_id",
        },
        "regression_params": {
            **XGB_PARAMS,
            "random_state": "SEED + split_id",
        },
        "metric_definition": {
            "primary": [
                "global Spearman rank correlation",
                "macro query-level pairwise accuracy; target ties excluded; predicted ties score 0.5",
            ],
            "secondary": [
                "micro pairwise accuracy",
                "AUC(epsilon > 15)",
                "AUC(epsilon > 30)",
                "calibrated MAE/RMSE/R2",
            ],
            "calibrated_metrics_warning": (
                "rank scores are not epsilon values; MAE/RMSE/R2 are computed "
                "only after identical nested isotonic calibration"
            ),
        },
        "calibration_spec": {
            "algorithm": "IsotonicRegression(out_of_bounds='clip')",
            "fit_data": "inner qid-grouped OOF predictions from outer-train rows only",
            "outer_test_targets_used": False,
            "same_link_family_for_both_heads": True,
            "clip": "max(calibrated_prediction, 1.0)",
        },
        "fold_qid_overlap_assertions": {
            "outer_train_test_qid_disjoint": True,
            "each_repeat_tests_every_qid_once": True,
            "both_heads_share_exact_row_indices": True,
            "inner_calibration_grouping": "qid",
        },
        "scenarios": scenario_summaries,
        "results": {
            "primary_arm_results": scenario_summaries[PRIMARY_SCENARIO]["results"],
            "negative_control_arm_results": scenario_summaries[
                NEGATIVE_SCENARIO
            ]["results"],
        },
        "decision": {
            **decision,
            "negative_control": {
                "qid_count": scenario_summaries[NEGATIVE_SCENARIO]["qid_count"],
                "singleton_count": scenario_summaries[NEGATIVE_SCENARIO][
                    "singleton_count"
                ],
                "total_pair_capacity": scenario_summaries[NEGATIVE_SCENARIO][
                    "total_pair_capacity"
                ],
                "rank_degeneracy": scenario_summaries[NEGATIVE_SCENARIO][
                    "rank_degeneracy"
                ],
            },
            "honesty_note": (
                "The decision follows the pre-registered ranking criteria. "
                "It is not changed after inspecting the metrics."
            ),
        },
        "limitations": [
            "76 of 111 primary qids are singletons and provide no pairwise training gradient.",
            (
                "The actual 50-split minimum train pair capacity is 173; the "
                "audit shorthand of approximately 277 was the repeat-0 minimum. "
                "The difference occurs when the large benzene-like qid and "
                "another large qid co-occur in the test fold."
            ),
            "The 10 RepeatedKFold repeats are correlated and are not 10 independent datasets; repeat-level t-tests are diagnostics only.",
            "Primary confidence intervals use a qid-cluster bootstrap; stable inference is limited by small non-singleton query counts.",
            "The qid-level split does not reproduce the v0.3 row-level fold table and must not be compared as if fold indices were identical.",
            "Isotonic calibration is applied separately to each head but with the same algorithm and inner splits; it can remove score-scale information by construction.",
            "The negative control is intentionally degenerate: every InChIKey is a singleton, so no comparable pairwise training or evaluation pairs exist.",
            "No claim is made about compounds outside the frozen 234-row v0.3 benchmark or about arbitrary chemical extrapolation.",
        ],
        "outputs": {
            "summary": portable_relative_path(args.summary, root=REPOSITORY_ROOT),
            "predictions": portable_relative_path(
                args.predictions,
                root=REPOSITORY_ROOT,
            ),
            "metrics": portable_relative_path(args.metrics, root=REPOSITORY_ROOT),
            "qid_audit": portable_relative_path(
                args.qid_audit,
                root=REPOSITORY_ROOT,
            ),
        },
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    write_json_lf(args.summary, payload)
    write_csv_rows(
        args.predictions,
        PREDICTION_COLUMNS,
        _serialize_prediction_rows(all_predictions),
    )
    write_csv_rows(
        args.metrics,
        METRIC_COLUMNS,
        _serialize_metric_rows(all_metrics),
    )
    write_csv_rows(args.qid_audit, QID_AUDIT_COLUMNS, audit_rows)

    primary_results = scenario_summaries[PRIMARY_SCENARIO]["results"]
    print(
        json.dumps(
            {
                "decision": decision["label"],
                "primary_metrics_mean": {
                    arm: {
                        metric: primary_results[arm][
                            "per_repeat_metric_summary"
                        ][metric]["mean"]
                        for metric in (
                            "macro_pairwise_accuracy",
                            "global_spearman",
                            "calibrated_mae",
                        )
                    }
                    for arm in ARMS
                },
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
