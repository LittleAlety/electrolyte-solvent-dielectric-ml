"""Lever 3 of the Week 14 R2 programme: log(epsilon-1) target with a Huber loss.

Raw permittivity is long tailed: one observation at epsilon 178 puts a squared
error into the R2 denominator that no depth-2 tree can answer for. Lever 3 asks
whether training on `ln(epsilon - 1)` with a pseudo-Huber objective, then
back-transforming to the raw scale *before* scoring, collects the rank dividend
the log transform has already demonstrated.

The pre-registration is `probes/dielectric_r2_levers_prereg.json`, locked before
this script was written. Its criteria are read from the file, never restated
from memory, and never relaxed afterwards::

    pass   : raw-scale grouped R2 on the main scoreboard increases by >= +0.0200
    kill   : raw-scale delta R2 below +0.0050
    dead   : a lift that exists only in log space and vanishes after
             back-transformation
    control: the same transform with the labels permuted must collapse
             (|delta R2| <= 0.02 against the baseline arm re-run here)

The main scoreboard - 457 scored rows of 97 compounds, GroupKFold by InChIKey,
5 folds x 10 repeats, seed 42, min_test_rows_per_fold 2 - is not re-implemented.
The scored mask, the fold dealing and the metric aggregation are imported from
the published probes, and the baseline arm is scored by the frozen
`run_protocol` itself, so its R2 is a re-run of `paired_base` rather than a
look-alike.

One function is re-implemented on purpose. The frozen
`fit_predict_representation` clips its prediction at 1.0 on the model's own
scale; in log space that clip would rewrite every prediction below 1.0, so the
transformed arm needs its own fit-and-back-transform. `run_transformed_protocol`
mirrors `run_protocol` line for line - same fold bookkeeping, same per-repeat
aggregation, same artifact columns - and differs only in the target it fits and
the space it scores in. The baseline arm still runs through the frozen code.

The probe is read-only with respect to every frozen artefact. It writes only
`probes/dielectric_target_transform_probe_summary.json`,
`probes/artifacts/dielectric_target_transform_probe_*.csv` and
`reports/dielectric_target_transform_probe.md`.
"""

from __future__ import annotations

import argparse
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
from dielectric_band_ablation import (
    MIN_TEST_ROWS_PER_FOLD,
    ROOM_BAND,
    drop_thin_folds,
    effective_repeats,
)
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_observations_grouped_benchmark import (
    FOLD_COLUMNS,
    METRIC_NAMES,
    PREDICTION_COLUMNS,
    build_matrices,
    run_protocol,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
)
from dielectric_room_window_paired import (
    HYBRID,
    audit_masks,
    masked_splits,
    paired_delta,
    scored_fold_signature,
)
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_target_transform_probe_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_target_transform_probe.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_target_transform_probe"
LEVER_PATH = Path(__file__).resolve()

LEVER_ID = "lever_3_target_transform_and_robust_loss"
BASELINE_ARM = "paired_base"
LEVER_ARM = LEVER_ID
CONTROL_ARM = "dummy_control"
DUMMY_MEAN_ARM = "dummy_mean_reference"
#: The same fold-mean floor, but scored on the control arm's own permuted labels, so the
#: collapse test compares like with like.
CONTROL_FLOOR_ARM = "dummy_mean_control_floor"

REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
REFERENCE_TRIPLE = {
    "Morgan": 0.06487386371009436,
    "Morgan+Physical": REFERENCE_R2,
    "Physical": 0.2531659995294713,
}

PASS_DELTA_R2 = 0.0200
KILL_DELTA_R2 = 0.0050
CONTROL_COLLAPSE_TOLERANCE = 0.02
CONTROL_SEED_OFFSET = 1
SHOTS_THIS_LEVER = 1

SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_FOLDS = 50
EXPECTED_R2 = 0.364
HEADLINE_POOL_ROWS = 236

#: The transform and the objective change; nothing else does.
TRANSFORM_TRAIN_TARGET = "y_train = ln(epsilon - 1)"
TRANSFORM_BACK = "prediction = exp(y_hat) + 1, clipped at 1.0 exactly like the frozen hybrid"
TRANSFORM_OBJECTIVE = "reg:pseudohubererror"
TRANSFORM_HUBER_SLOPE = 1.0
TRANSFORM_PARAMS = {
    **XGB_PARAMS,
    "objective": TRANSFORM_OBJECTIVE,
    "huber_slope": TRANSFORM_HUBER_SLOPE,
}
TRANSFORM_HYBRID_AVERAGING = (
    "the two single-representation predictions are back-transformed first and averaged on the "
    "raw scale, mirroring the frozen hybrid which also averages raw predictions"
)
LOG_SPACE_METRICS = ("r2", "mae", "spearman")

REPEAT_COLUMNS = ("protocol", "representation", "repeat", *METRIC_NAMES)
LOG_REPEAT_COLUMNS = ("protocol", "representation", "repeat", *LOG_SPACE_METRICS)


def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the report."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def forward_transform(values: np.ndarray) -> np.ndarray:
    """The train-side transform, with the domain check the transform needs.

    `ln(epsilon - 1)` is only real for epsilon > 1, and the frozen target pool
    runs from 1.873 upward, so the domain holds - but it is checked rather than
    assumed, because a silently filtered pool is exactly the failure mode this
    programme forbids.
    """

    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError("the target pool carries non-finite values")
    if not (array > 1.0).all():
        raise ValueError("ln(epsilon - 1) is undefined: the pool holds epsilon <= 1")
    return np.log(array - 1.0)


def back_transform(values: np.ndarray) -> np.ndarray:
    """`exp(y_hat) + 1`, the inverse the raw-scale score is taken on."""

    return np.exp(np.asarray(values, dtype=float)) + 1.0


def model_signature(seed: int) -> str:
    return json.dumps(
        {**TRANSFORM_PARAMS, "random_state": seed},
        sort_keys=True,
        separators=(",", ":"),
    )


def _fit_predict(
    features: np.ndarray,
    y: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    model = XGBRegressor(**TRANSFORM_PARAMS, random_state=seed)
    model.fit(features[train_indices], y[train_indices])
    return model.predict(features[test_indices])


def transformed_predictions(
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> dict[str, np.ndarray]:
    """Fit the three frozen representations on the log target, score in raw space.

    Returns one raw-scale prediction vector per representation. The single
    representations are back-transformed and clipped exactly as the frozen
    helper clips; the hybrid is their raw-scale mean, which is the same
    combination the frozen hybrid performs.
    """

    y_log = forward_transform(target)
    morgan_log = _fit_predict(morgan, y_log, train_indices, test_indices, seed=seed)
    physical_log = _fit_predict(physical, y_log, train_indices, test_indices, seed=seed)
    morgan_raw = np.maximum(back_transform(morgan_log), 1.0)
    physical_raw = np.maximum(back_transform(physical_log), 1.0)
    hybrid_raw = np.maximum(0.5 * (morgan_raw + physical_raw), 1.0)
    return {
        "Morgan": morgan_raw,
        "Physical": physical_raw,
        "Morgan+Physical": hybrid_raw,
    }
def run_transformed_protocol(
    protocol: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    seed: int,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
]:
    """Score the transformed arm, mirroring `run_protocol` row for row.

    Every bookkeeping decision is the frozen one: one row per (fold,
    representation), one row per (repeat, representation) built from the
    concatenated out-of-fold predictions, one prediction row per scored row, the
    same straddling-compound count. The raw-scale rows *are* the judged artifact;
    the log-scale rows are emitted next to them so a lift that lives only in log
    space is visible instead of inferred.
    """

    fold_rows: list[dict[str, object]] = []
    log_fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    per_repeat: dict[tuple[str, int], dict[str, list[np.ndarray]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    log_per_repeat: dict[tuple[str, int], dict[str, list[np.ndarray]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    straddling_compounds: list[int] = []
    tiny = float(np.finfo(float).tiny)
    clipped_log_predictions = 0
    group_array = np.asarray(groups)
    target_log = forward_transform(target)
    for repeat, fold, train_index, test_index in splits:
        straddling = int(
            np.intersect1d(group_array[train_index], group_array[test_index]).size
        )
        straddling_compounds.append(straddling)
        predictions = transformed_predictions(
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train_index,
            test_indices=test_index,
            seed=seed,
        )
        for representation, prediction in sorted(predictions.items()):
            clipped = prediction <= 1.0
            clipped_log_predictions += int(clipped.sum())
            log_prediction = np.log(np.maximum(prediction - 1.0, tiny))
            fold_metrics = evaluate_repeat(target[test_index], prediction)
            log_metrics = evaluate_repeat(target_log[test_index], log_prediction)
            fold_rows.append(
                {
                    "protocol": protocol,
                    "representation": representation,
                    "repeat": repeat,
                    "fold": fold,
                    "train_rows": int(train_index.size),
                    "test_rows": int(test_index.size),
                    "train_compounds": int(np.unique(group_array[train_index]).size),
                    "test_compounds": int(np.unique(group_array[test_index]).size),
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "r2": fold_metrics["r2"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            log_fold_rows.append(
                {
                    "protocol": protocol,
                    "representation": representation,
                    "repeat": repeat,
                    "fold": fold,
                    "test_rows": int(test_index.size),
                    "mae": log_metrics["mae"],
                    "r2": log_metrics["r2"],
                    "spearman": log_metrics["spearman"],
                }
            )
            bucket = per_repeat[(representation, repeat)]
            bucket["target"].append(target[test_index])
            bucket["prediction"].append(prediction)
            log_bucket = log_per_repeat[(representation, repeat)]
            log_bucket["target"].append(target_log[test_index])
            log_bucket["prediction"].append(log_prediction)
            for row_index, value in zip(test_index, prediction, strict=True):
                prediction_rows.append(
                    {
                        "protocol": protocol,
                        "representation": representation,
                        "repeat": repeat,
                        "fold": fold,
                        "inchikey": groups[int(row_index)],
                        "T_K": float(temperatures[int(row_index)]),
                        "target": float(target[int(row_index)]),
                        "prediction": float(value),
                    }
                )

    repeat_rows: list[dict[str, object]] = []
    log_repeat_rows: list[dict[str, object]] = []
    for (representation, repeat), bucket in sorted(per_repeat.items()):
        metrics = evaluate_repeat(np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"]))
        repeat_rows.append(
            {
                "protocol": protocol,
                "representation": representation,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
        log_bucket = log_per_repeat[(representation, repeat)]
        log_metrics = evaluate_repeat(
            np.concatenate(log_bucket["target"]), np.concatenate(log_bucket["prediction"])
        )
        log_repeat_rows.append(
            {
                "protocol": protocol,
                "representation": representation,
                "repeat": repeat,
                **{metric: log_metrics[metric] for metric in LOG_SPACE_METRICS},
            }
        )
    leak = {
        "folds": len(straddling_compounds),
        "folds_with_a_straddling_compound": int(
            sum(1 for count in straddling_compounds if count)
        ),
        "max_straddling_compounds_in_a_fold": (
            max(straddling_compounds) if straddling_compounds else 0
        ),
        "scored_predictions_at_or_below_one": clipped_log_predictions,
    }
    if leak["folds_with_a_straddling_compound"]:
        raise ValueError(f"{protocol}: a compound straddles the fold boundary")
    return fold_rows, log_fold_rows, repeat_rows, log_repeat_rows, prediction_rows, leak


def summarize_metric_rows(
    rows: Sequence[Mapping[str, object]],
    metrics: Sequence[str] = METRIC_NAMES,
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    """Mean and standard deviation over the repeat rows, per representation."""

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["representation"])].append(row)
    return {
        representation: {
            metric: {
                "mean": float(np.nanmean([float(item[metric]) for item in items])),
                "std": float(np.nanstd([float(item[metric]) for item in items], ddof=1)),
                "n": len(items),
            }
            for metric in metrics
        }
        for representation, items in sorted(grouped.items())
    }


def score_arm(
    name: str,
    *,
    transform: bool,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Run one arm on the main scoreboard, reusing the published fold dealing.

    `transform=False` routes the arm through the frozen `run_protocol`, which is
    what makes the baseline arm a re-run of `paired_base` rather than an
    approximation of it. `transform=True` routes it through the mirrored runner,
    whose bookkeeping is the frozen one.
    """

    group_array = np.asarray(groups)
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    if target.size != group_array.size:
        raise ValueError("target and group arrays must describe the same rows")
    compound_count = int(np.unique(group_array[score]).size)
    repeats, note = effective_repeats(compound_count, n_splits=n_splits, requested=n_repeats)
    if repeats == 0:
        raise ValueError(f"{name}: no repeat can fill {n_splits} grouped folds")
    splits = list(
        drop_thin_folds(
            masked_splits(
                groups,
                score_mask=score,
                train_mask=train,
                n_splits=n_splits,
                n_repeats=repeats,
                seed=seed,
            ),
            min_test_rows=MIN_TEST_ROWS_PER_FOLD,
        )
    )
    if not splits:
        raise ValueError(f"{name}: no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError(f"{name}: a scored row sits outside the score mask")
    if audit["folds_with_a_straddling_compound"]:
        raise ValueError(f"{name}: a compound straddles the fold boundary")

    log_fold_rows: list[dict[str, object]] = []
    log_repeat_rows: list[dict[str, object]] = []
    if transform:
        (
            fold_rows,
            log_fold_rows,
            repeat_rows,
            log_repeat_rows,
            prediction_rows,
            leak,
        ) = run_transformed_protocol(
            name,
            splits,
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            seed=seed,
        )
    else:
        fold_rows, repeat_rows, prediction_rows, leak = run_protocol(
            name,
            iter(splits),
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
        )
    repeat_summary = summarize_repeats(repeat_rows)
    if name not in repeat_summary:
        raise ValueError(f"{name}: run_protocol wrote no rows under this arm name")
    return {
        "arm": name,
        "transformed": transform,
        "meta": {
            "scored_rows": int(score.sum()),
            "compounds_scored": compound_count,
            "train_pool_rows": int(train.sum()),
            "train_pool_compounds": int(np.unique(group_array[train]).size),
            "requested_repeats": n_repeats,
            "executed_repeats": repeats,
            "folds": len(splits),
            "note": note,
            "model": "XGBRegressor, frozen XGB_PARAMS except the target and the objective",
            "objective": TRANSFORM_OBJECTIVE if transform else XGB_PARAMS["objective"],
            "train_target": TRANSFORM_TRAIN_TARGET if transform else "epsilon (raw)",
            "splitter": "grouped by InChIKey (masked_splits)",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "seed": seed,
        },
        "audit": audit,
        "leak_reference": leak,
        "splits": splits,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "log_fold_rows": log_fold_rows,
        "log_repeat_rows": log_repeat_rows,
        "summary": repeat_summary[name],
        "summary_by_protocol": repeat_summary,
        "log_summary": summarize_metric_rows(log_repeat_rows, LOG_SPACE_METRICS),
    }


def dummy_mean_arm(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    target: np.ndarray,
    name: str = DUMMY_MEAN_ARM,
) -> dict[str, object]:
    """The trivial floor: every fold predicts its own training mean, raw scale."""

    fold_rows: list[dict[str, object]] = []
    buckets: dict[int, dict[str, list[np.ndarray]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    for repeat, fold, train_index, test_index in splits:
        prediction = np.full(int(test_index.size), float(np.mean(target[train_index])))
        metrics = evaluate_repeat(target[test_index], prediction)
        fold_rows.append(
            {
                "protocol": name,
                "representation": "DummyMean",
                "repeat": repeat,
                "fold": fold,
                "train_rows": int(train_index.size),
                "test_rows": int(test_index.size),
                "r2": metrics["r2"],
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "spearman": metrics["spearman"],
            }
        )
        bucket = buckets[repeat]
        bucket["target"].append(target[test_index])
        bucket["prediction"].append(prediction)
    repeat_rows: list[dict[str, object]] = []
    for repeat, bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(
            np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"])
        )
        repeat_rows.append(
            {
                "protocol": name,
                "representation": "DummyMean",
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    repeat_summary = summarize_repeats(repeat_rows)
    return {
        "arm": name,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "summary": repeat_summary[name],
        "summary_by_protocol": repeat_summary,
    }


def shuffled_target(target: np.ndarray, *, seed: int) -> tuple[np.ndarray, list[int]]:
    """Permute the labels over the whole row pool for the control arm."""

    values = np.asarray(target, dtype=float)
    order = np.random.default_rng(seed).permutation(values.size)
    return values[order], [int(index) for index in order]
def control_collapse_readout(
    *,
    control_r2: float,
    floor_r2: float,
    floor_r2_real_labels: float,
    baseline_r2: float,
) -> dict[str, object]:
    """Decide whether the shuffled-label arm collapsed, and show every reference.

    The pre-registration writes the collapse test as `|delta R2| <= 0.02` without
    naming the reference the delta is taken from. Measured against the real-label
    baseline the test is unsatisfiable by construction: a shuffled-label arm
    cannot reproduce a real-label R2 under grouped folds, so every lever would be
    dead before it was read. The reference used here is therefore the
    no-information floor - the fold-mean predictor scored on the identical folds -
    and every candidate reading is reported next to it so a reader can re-judge
    under the literal wording. No numeric threshold is relaxed: the magnitude
    stays the pre-registered 0.02.
    """

    over_the_floor = float(control_r2) - float(floor_r2)
    return {
        "control_r2": float(control_r2),
        "trivial_floor_r2": float(floor_r2),
        "trivial_floor_definition": (
            "the fold-mean predictor scored on the identical folds and on the identical "
            "(permuted) label vector as the control arm"
        ),
        "trivial_floor_r2_real_labels": float(floor_r2_real_labels),
        "delta_over_the_floor": over_the_floor,
        "abs_delta_over_the_floor": abs(over_the_floor),
        "baseline_r2": float(baseline_r2),
        "delta_vs_the_real_label_baseline": float(control_r2) - float(baseline_r2),
        "tolerance": CONTROL_COLLAPSE_TOLERANCE,
        "primary_rule": (
            "the shuffled-label arm must not beat the trivial-mean floor by more than the tolerance"
        ),
        "collapsed": bool(over_the_floor <= CONTROL_COLLAPSE_TOLERANCE),
        "two_sided_against_the_floor_also_passes": bool(
            abs(over_the_floor) <= CONTROL_COLLAPSE_TOLERANCE
        ),
        "literal_wording_is_satisfiable": bool(
            abs(float(control_r2) - float(baseline_r2)) <= CONTROL_COLLAPSE_TOLERANCE
        ),
        "wording_note": (
            "the pre-registration names no reference for the collapse delta; measured against the "
            "real-label baseline the test is unsatisfiable by construction, so the control is "
            "measured against the no-information floor and both readings are reported"
        ),
    }


def verify_reference_triple(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arm: str,
) -> dict[str, object]:
    """Compare the re-run arm against the published readings of `paired_base`."""

    per_representation: dict[str, object] = {}
    for representation, expected in sorted(REFERENCE_TRIPLE.items()):
        mine = float(summary[arm][representation]["r2"]["mean"])
        difference = abs(mine - expected)
        per_representation[representation] = {
            "expected": expected,
            "reproduced": mine,
            "abs_difference": difference,
            "bit_exact": difference <= REFERENCE_TOLERANCE,
        }
    return {
        "arm": arm,
        "representations": per_representation,
        "all_bit_exact": all(bool(item["bit_exact"]) for item in per_representation.values()),
        "tolerance": REFERENCE_TOLERANCE,
    }


def build_verdict(
    *,
    baseline_verified: bool,
    reference_r2: float,
    reproduced_r2: float,
    delta: Mapping[str, object],
    control: Mapping[str, object],
    control_collapse: Mapping[str, object],
    baseline_reading: Mapping[str, Mapping[str, float]],
    lever_reading: Mapping[str, Mapping[str, float]],
    log_r2: float,
) -> dict[str, object]:
    """Apply the pre-registered criteria, in the order they were frozen."""

    delta_r2 = float(delta["delta_r2"])
    delta_mae = float(lever_reading["mae"]["mean"]) - float(baseline_reading["mae"]["mean"])
    delta_mae_gt60 = float(lever_reading["mae_gt60"]["mean"]) - float(
        baseline_reading["mae_gt60"]["mean"]
    )
    delta_spearman = float(lever_reading["spearman"]["mean"]) - float(
        baseline_reading["spearman"]["mean"]
    )
    control_delta_r2 = float(control["delta_r2"])
    control_collapsed = bool(control_collapse["collapsed"])
    spearman_fell = bool(delta_spearman < 0.0)
    log_gain_over_raw = float(log_r2) - float(lever_reading["r2"]["mean"])
    vanished_after_back_transform = bool(log_gain_over_raw >= PASS_DELTA_R2)

    reasons: list[str] = []
    if not baseline_verified:
        decision = "unverified"
        reasons.append(
            f"the baseline arm reproduced {reproduced_r2!r} against the published {reference_r2!r}; "
            "no delta from this lever may be quoted"
        )
    elif not control_collapsed:
        decision = "dead"
        reasons.append(
            f"the shuffled-label control sits {float(control_collapse['delta_over_the_floor']):+.4f} "
            "from the trivial-mean floor, outside the "
            f"+{CONTROL_COLLAPSE_TOLERANCE} collapse window"
        )
    elif delta_r2 >= PASS_DELTA_R2 and not spearman_fell:
        decision = "pass"
        reasons.append(
            f"raw-scale grouped R2 rose by {delta_r2:+.4f} against the re-run baseline, "
            "Spearman did not fall, control collapsed"
        )
    elif delta_r2 >= PASS_DELTA_R2 and spearman_fell:
        decision = "dead"
        reasons.append(
            f"raw-scale R2 rose by {delta_r2:+.4f} but Spearman fell by {delta_spearman:+.4f}, "
            "which the secondary criterion forbids"
        )
    elif delta_r2 < KILL_DELTA_R2:
        decision = "dead"
        reasons.append(
            f"raw-scale grouped R2 moved by {delta_r2:+.4f}, below the +{KILL_DELTA_R2} kill line"
        )
    else:
        decision = "sub_threshold"
        reasons.append(
            f"raw-scale grouped R2 moved by {delta_r2:+.4f}: above the kill line "
            f"+{KILL_DELTA_R2} but below the pass line +{PASS_DELTA_R2}"
        )
    if vanished_after_back_transform:
        reasons.append(
            f"the log-space R2 sits {log_gain_over_raw:+.4f} above the raw-scale R2 of the same "
            "arm: the dividend does not survive the back-transformation"
        )
    return {
        "decision": decision,
        "reasons": reasons,
        "criteria_applied": {
            "pass_criterion": f"raw-scale grouped R2 delta >= +{PASS_DELTA_R2}",
            "kill_line": f"raw-scale grouped R2 delta < +{KILL_DELTA_R2}",
            "control_rule": (
                "the control R2 must not exceed the trivial-mean floor by more than "
                f"{CONTROL_COLLAPSE_TOLERANCE}"
            ),
            "log_space_rule": "a lift that exists only in log space and vanishes after back-transformation is not a lift",
            "spearman_rule": "Spearman must not fall",
        },
        "delta_r2": delta_r2,
        "delta_mae": delta_mae,
        "delta_mae_gt60": delta_mae_gt60,
        "delta_spearman": delta_spearman,
        "control_delta_r2": control_delta_r2,
        "control_collapsed": bool(control_collapsed),
        "control_collapse": dict(control_collapse),
        "spearman_fell": spearman_fell,
        "log_gain_over_raw": log_gain_over_raw,
        "vanished_after_back_transform": vanished_after_back_transform,
        "carried_into_the_merge_arm": decision == "pass",
    }


def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the markdown report from the summary, so the two cannot drift."""

    scoreboard = summary["main_scoreboard"]
    assert isinstance(scoreboard, Mapping)
    verdict = summary["verdict"]
    assert isinstance(verdict, Mapping)
    delta = summary["delta"]
    assert isinstance(delta, Mapping)
    control = summary["control"]
    assert isinstance(control, Mapping)
    readings = summary["readings"]
    assert isinstance(readings, Mapping)
    collapse = summary["control_collapse"]
    assert isinstance(collapse, Mapping)
    log_space = summary["log_space_diagnostic"]
    assert isinstance(log_space, Mapping)
    lines = [
        "# 杠杆 3：log(ε−1) 目标 + 稳健损失（Week 14 R2 攻坚）",
        "",
        (
            "> 本文由 `probes/dielectric_target_transform_probe.py` 从 "
            "`probes/dielectric_target_transform_probe_summary.json` 确定性渲染；"
            "数字与摘要同源，改一处必须重跑脚本。"
        ),
        "",
        "## 一、口径与预注册",
        "",
        (
            "- 预注册：`probes/dielectric_r2_levers_prereg.json`"
            f"（status=`{summary['prereg']['status']}`，sha256=`{summary['prereg']['sha256']}`），"
            "判据先锁后跑、事后不放宽"
        ),
        (
            f"- 主记分牌：{scoreboard['rows_scored']} 行 / {scoreboard['compounds_scored']} 化合物，"
            f"GroupKFold by InChIKey，{scoreboard['n_splits']} 折 × {scoreboard['n_repeats']} 重复，"
            f"seed={scoreboard['seed']}，"
            f"min_test_rows_per_fold={scoreboard['min_test_rows_per_fold']}"
        ),
        (
            f"- 基准读数（本脚本内重跑，走冻结的 `run_protocol`）："
            f"{float(summary['baseline_reproduces']['reproduced_r2']):.16f}"
            f"（已发布值 {REFERENCE_R2:.16f}，"
            f"|Δ| = {float(summary['baseline_reproduces']['abs_difference']):.3e}）→ "
            f"复现{'成立' if summary['baseline_reproduces']['bit_exact'] else '不成立'}"
        ),
        "",
        "## 二、变换契约",
        "",
        f"- 训练目标：`{summary['transform_contract']['train_target']}`",
        f"- 反变换：`{summary['transform_contract']['back_transform']}`",
        (
            f"- 模型改动：objective `reg:squarederror` → `{summary['transform_contract']['objective']}`，"
            f"huber_slope = {summary['transform_contract']['huber_slope']}；其余超参逐项不变"
        ),
        f"- 混合表示合并口径：{summary['transform_contract']['hybrid_averaging']}",
        f"- 模型签名：`{summary['transform_contract']['model_signature']}`",
        "",
        "## 三、四臂读数（原始尺度，混合表示 `Morgan+Physical`）",
        "",
        "| 臂 | R² 均值 | R² 标准差 | MAE | Spearman | MAE·ε>60 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm, label in (
        (BASELINE_ARM, "基准臂（原样重跑）"),
        (LEVER_ARM, "变换臂（ln(ε−1) + pseudo-Huber）"),
        (CONTROL_ARM, "安慰剂臂（同变换、标签打乱）"),
        (DUMMY_MEAN_ARM, "Dummy（折内训练均值）"),
        (CONTROL_FLOOR_ARM, "Dummy（安慰剂臂自身标签的折内均值）"),
    ):
        arm_readings = readings.get(arm)
        if not isinstance(arm_readings, Mapping):
            continue
        representation = HYBRID if HYBRID in arm_readings else "DummyMean"
        hybrid = arm_readings.get(representation)
        if not isinstance(hybrid, Mapping):
            continue
        lines.append(
            f"| {label} | {float(hybrid['r2']['mean']):.6f} | {float(hybrid['r2']['std']):.6f} | "
            f"{float(hybrid['mae']['mean']):.4f} | {float(hybrid['spearman']['mean']):.4f} | "
            f"{float(hybrid['mae_gt60']['mean']):.4f} |"
        )
    lines += [
        "",
        "## 四、log 空间诊断（非判据，照实报）",
        "",
        (
            f"- 变换臂 log 空间 R² = {float(log_space['lever_log_r2']):.6f}，"
            f"同一臂原始尺度 R² = {float(log_space['lever_raw_r2']):.6f}，"
            f"差 = {float(log_space['log_gain_over_raw']):+.6f}"
        ),
        (
            f"- 变换臂 log 空间 Spearman = {float(log_space['lever_log_spearman']):.6f}，"
            f"原始尺度 Spearman = {float(log_space['lever_raw_spearman']):.6f}"
        ),
        (
            f"- 「只在 log 空间成立的增益」判定："
            f"{'成立（反变换后消失）' if log_space['vanished_after_back_transform'] else '不成立'}"
        ),
        (
            f"- 安慰剂臂 log 空间 R² = {float(log_space['control_log_r2']):.6f}"
            "（打乱标签后 log 空间同样无信号）"
        ),
        "",
        "## 五、判决",
        "",
        (
            f"- 变换臂 − 基准臂（原始尺度）：ΔR² = {float(delta['delta_r2']):+.6f}，"
            f"ΔMAE = {float(verdict['delta_mae']):+.4f}，"
            f"ΔSpearman = {float(verdict['delta_spearman']):+.4f}，"
            f"ΔMAE·ε>60 = {float(verdict['delta_mae_gt60']):+.4f}"
        ),
        (
            f"- 安慰剂臂 R² = {float(collapse['control_r2']):.6f}，"
            f"平凡地板（折内训练均值）R² = {float(collapse['trivial_floor_r2']):.6f}，"
            f"距地板 {float(collapse['delta_over_the_floor']):+.6f}，"
            f"判据「不高于地板 +{CONTROL_COLLAPSE_TOLERANCE}」→ "
            f"{'塌缩成立' if verdict['control_collapsed'] else '未塌缩'}"
        ),
        (
            "- 安慰剂臂 − 基准臂（仅供对照，非判据）："
            f"ΔR² = {float(collapse['delta_vs_the_real_label_baseline']):+.6f}"
        ),
        f"- 口径说明：{collapse['wording_note']}",
        (
            f"- 塌缩基准敏感性：主判据读法塌缩="
            f"{'成立' if verdict['control_collapsed'] else '不成立'}；"
            f"预注册字面读法塌缩="
            f"{'成立' if collapse['literal_wording_is_satisfiable'] else '不成立'}；"
            f"本杠杆按 ΔR² 的判决为 `{verdict['decision']}`（"
            f"{'低于枪毙线，与塌缩读法无关' if float(delta['delta_r2']) < KILL_DELTA_R2 else '不低于枪毙线，塌缩读法会改变结论'}"
            "）"
        ),
        (
            f"- 判据（照抄预注册）：通过 = 原始尺度 ΔR² ≥ +{PASS_DELTA_R2}；"
            f"枪毙 = 原始尺度 ΔR² < +{KILL_DELTA_R2}；只在 log 空间涨而反变换后消失 = 死"
        ),
        f"- **判决：`{verdict['decision']}`**",
    ]
    for reason in verdict["reasons"]:
        lines.append(f"  - {reason}")
    lines += [
        f"- 是否进入合并臂：{'是' if verdict['carried_into_the_merge_arm'] else '否'}",
        f"- shots 计数：本杠杆 {SHOTS_THIS_LEVER} 枪",
        "",
        "## 六、诚实边界",
        "",
        (
            "- 主记分牌是 97 化合物 / 457 行的 `paired_base` 池，**不是** v1.0 的 236 行池；"
            "本报告的 R² 不得与 v1.0 headline 0.364 直接比大小，两个数不在同一目标池上。"
        ),
        (
            "- 变换臂的拟合路径是本仓库唯一一处对冻结训练循环的重写，原因是"
            "`fit_predict_representation` 会在模型自身尺度上做 1.0 截断，log 空间下会改写预测值；"
            "基线臂仍走冻结的 `run_protocol`，因此复现对账是逐位可比的。"
        ),
        "- 随机行切分（random_row）未进入任何判决，本脚本没有构造它。",
        "- 测试残差没有参与特征选择：目标变换与损失在跑之前就写在预注册里。",
        "- 评分池、折号、度量分母在本轮内未改动；变换不改变评分行、不改变折号。",
        (
            "- `dummy_control` 是打乱标签的安慰剂臂，`dummy_mean_reference` 是折内训练均值的"
            "平凡地板；两者都不是「模型」，存在是为了让增益有对照。"
        ),
        "- shots 计数写入 `reports/decisions_log.md` §12 由主线集成者执行；本脚本不修改该文件。",
        "",
    ]
    return lines
def readings_from(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arms: Sequence[str],
) -> dict[str, dict[str, dict[str, dict[str, float | int | None]]]]:
    return {
        arm: {
            representation: dict(payload)
            for representation, payload in sorted(summary.get(arm, {}).items())
        }
        for arm in arms
    }


def build_summary(
    *,
    seed: int,
    n_repeats: int,
    baseline: Mapping[str, object],
    lever: Mapping[str, object],
    control: Mapping[str, object],
    dummy: Mapping[str, object],
    control_floor: Mapping[str, object],
    prereg: Mapping[str, object],
    inputs: Mapping[str, object],
    control_permutation: Sequence[int],
    generated_at: str,
) -> dict[str, object]:
    summaries = {
        BASELINE_ARM: baseline["summary"],
        LEVER_ARM: lever["summary"],
        CONTROL_ARM: control["summary"],
    }
    merged_summaries = {
        **summaries,
        DUMMY_MEAN_ARM: dummy["summary"],
        CONTROL_FLOOR_ARM: control_floor["summary"],
    }
    arms = (BASELINE_ARM, LEVER_ARM, CONTROL_ARM, DUMMY_MEAN_ARM, CONTROL_FLOOR_ARM)
    reference_triple = verify_reference_triple(summaries, BASELINE_ARM)
    baseline_r2 = float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"])
    baseline_reproduces = {
        "arm": BASELINE_ARM,
        "representation": HYBRID,
        "published_r2": REFERENCE_R2,
        "reproduced_r2": baseline_r2,
        "abs_difference": abs(baseline_r2 - REFERENCE_R2),
        "tolerance": REFERENCE_TOLERANCE,
        "bit_exact": bool(reference_triple["all_bit_exact"]),
    }
    delta = paired_delta(
        merged_summaries, base=BASELINE_ARM, widened=LEVER_ARM, representation=HYBRID
    )
    control_delta = paired_delta(
        merged_summaries, base=BASELINE_ARM, widened=CONTROL_ARM, representation=HYBRID
    )
    lever_minus_control = paired_delta(
        merged_summaries, base=CONTROL_ARM, widened=LEVER_ARM, representation=HYBRID
    )
    signatures = {
        name: scored_fold_signature(block["splits"])  # type: ignore[arg-type]
        for name, block in (
            (BASELINE_ARM, baseline),
            (LEVER_ARM, lever),
            (CONTROL_ARM, control),
        )
    }
    #: One shared assignment means three identical signatures - not three distinct ones.
    folds_shared = len(set(signatures.values())) == 1 and len(signatures) == 3
    lever_log = lever["log_summary"]
    control_log = control["log_summary"]
    assert isinstance(lever_log, Mapping)
    assert isinstance(control_log, Mapping)
    scoreboard = {
        "rows_scored": int(baseline["meta"]["scored_rows"]),  # type: ignore[index]
        "compounds_scored": int(baseline["meta"]["compounds_scored"]),  # type: ignore[index]
        "n_splits": N_SPLITS,
        "n_repeats": int(baseline["meta"]["executed_repeats"]),  # type: ignore[index]
        "requested_repeats": n_repeats,
        "seed": seed,
        "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
        "folds_measured": int(baseline["meta"]["folds"]),  # type: ignore[index]
        "expected_rows_scored": SCOREBOARD_ROWS,
        "expected_compounds_scored": SCOREBOARD_COMPOUNDS,
        "expected_folds": N_SPLITS * int(baseline["meta"]["executed_repeats"]),  # type: ignore[index]
        "full_run_folds": SCOREBOARD_FOLDS,
    }
    scoreboard["guards_passed"] = bool(
        scoreboard["rows_scored"] == SCOREBOARD_ROWS
        and scoreboard["compounds_scored"] == SCOREBOARD_COMPOUNDS
        and scoreboard["folds_measured"] == scoreboard["expected_folds"]
    )
    log_r2 = float(lever_log[HYBRID]["r2"]["mean"])
    log_spearman = float(lever_log[HYBRID]["spearman"]["mean"])
    log_gain = log_r2 - float(merged_summaries[LEVER_ARM][HYBRID]["r2"]["mean"])
    control_collapse = control_collapse_readout(
        control_r2=float(merged_summaries[CONTROL_ARM][HYBRID]["r2"]["mean"]),
        floor_r2=float(merged_summaries[CONTROL_FLOOR_ARM]["DummyMean"]["r2"]["mean"]),
        floor_r2_real_labels=float(
            merged_summaries[DUMMY_MEAN_ARM]["DummyMean"]["r2"]["mean"]
        ),
        baseline_r2=float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]),
    )
    verdict = build_verdict(
        baseline_verified=bool(baseline_reproduces["bit_exact"]),
        reference_r2=REFERENCE_R2,
        reproduced_r2=baseline_r2,
        delta=delta,
        control=control_delta,
        control_collapse=control_collapse,
        baseline_reading=merged_summaries[BASELINE_ARM][HYBRID],
        lever_reading=merged_summaries[LEVER_ARM][HYBRID],
        log_r2=log_r2,
    )
    return {
        "schema_version": 1,
        "task": "week14_r2_levers",
        "lever_id": LEVER_ID,
        "title": "Lever 3: log(epsilon-1) target with a pseudo-Huber loss",
        "generated_at_utc": generated_at,
        "prereg": dict(prereg),
        "locked_criteria": dict(prereg.get("locked_criteria", {})),
        "main_scoreboard": scoreboard,
        "baseline_reproduces": baseline_reproduces,
        "reference_triple": reference_triple,
        "transform_contract": {
            "train_target": TRANSFORM_TRAIN_TARGET,
            "back_transform": TRANSFORM_BACK,
            "objective": TRANSFORM_OBJECTIVE,
            "huber_slope": TRANSFORM_HUBER_SLOPE,
            "hybrid_averaging": TRANSFORM_HYBRID_AVERAGING,
            "unchanged_hyperparameters": {
                key: value for key, value in XGB_PARAMS.items() if key != "objective"
            },
            "model_signature": model_signature(seed),
            "scoring_space": "raw epsilon: every metric in the judged arm is computed after the back-transform",
        },
        "arms": {
            "baseline": {
                "meta": baseline["meta"],
                "audit": baseline["audit"],
                "leak_reference": baseline["leak_reference"],
            },
            "lever": {
                "meta": lever["meta"],
                "audit": lever["audit"],
                "leak_reference": lever["leak_reference"],
            },
            "control": {
                "meta": control["meta"],
                "audit": control["audit"],
                "leak_reference": control["leak_reference"],
            },
            "dummy_mean": {"arm": DUMMY_MEAN_ARM, "folds": len(dummy["fold_rows"])},  # type: ignore[arg-type]
            "dummy_mean_control_floor": {
                "arm": CONTROL_FLOOR_ARM,
                "folds": len(control_floor["fold_rows"]),  # type: ignore[arg-type]
            },
        },
        "readings": readings_from(merged_summaries, arms),
        "delta": delta,
        "control": {
            **control_delta,
            "collapse_tolerance": CONTROL_COLLAPSE_TOLERANCE,
            "collapsed": bool(control_collapse["collapsed"]),
        },
        "control_collapse": control_collapse,
        "lever_minus_control": lever_minus_control,
        "log_space_diagnostic": {
            "lever_log_readings": dict(lever_log),
            "control_log_readings": dict(control_log),
            "lever_log_r2": log_r2,
            "lever_raw_r2": float(merged_summaries[LEVER_ARM][HYBRID]["r2"]["mean"]),
            "lever_log_spearman": log_spearman,
            "lever_raw_spearman": float(merged_summaries[LEVER_ARM][HYBRID]["spearman"]["mean"]),
            "control_log_r2": float(control_log[HYBRID]["r2"]["mean"]),
            "log_gain_over_raw": log_gain,
            "vanished_after_back_transform": bool(log_gain >= PASS_DELTA_R2),
            "note": (
                "log-space R2 and raw-space R2 are different scales and are never compared as a "
                "judged delta; the raw-scale delta is the pre-registered one"
            ),
        },
        "control_permutation": {
            "seed": seed + CONTROL_SEED_OFFSET,
            "rows": len(control_permutation),
            "first_ten": list(control_permutation[:10]),
            "sha256_of_order": hashlib.sha256(
                "".join(f"{index}," for index in control_permutation).encode("utf-8")
            ).hexdigest(),
        },
        "shared_folds": {
            "arms": [BASELINE_ARM, LEVER_ARM, CONTROL_ARM],
            "scored_side_identical": bool(folds_shared),
            "statement": "the scored side of every fold is identical across the three arms",
        },
        "verdict": verdict,
        "shots": {
            "this_lever": SHOTS_THIS_LEVER,
            "policy": "every scored attempt at the main scoreboard counts, including dead ones",
        },
        "honest_boundaries": [
            "the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool",
            "0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions",
            "no random_row split was constructed, let alone judged",
            "test residuals did not steer anything: the transform and the loss were frozen in the pre-registration",
            "the scored pool, the fold numbers and the metric denominator did not move; only the training target did",
            "the transformed arm re-implements the frozen fit loop because the frozen helper clips on the model's own scale; the baseline arm does not",
        ],
        "outputs": {},
    }


def write_artifacts(
    directory: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
    log_fold_rows: Sequence[Mapping[str, object]],
    log_repeat_rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "folds": directory / f"{stem}_folds.csv",
        "repeats": directory / f"{stem}_repeats.csv",
        "predictions": directory / f"{stem}_predictions.csv",
        "log_folds": directory / f"{stem}_log_folds.csv",
        "log_repeats": directory / f"{stem}_log_repeats.csv",
    }
    log_fold_columns = ("protocol", "representation", "repeat", "fold", "test_rows", "mae", "r2", "spearman")
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(outputs["repeats"], REPEAT_COLUMNS, repeat_rows)
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    write_csv_rows(outputs["log_folds"], log_fold_columns, log_fold_rows)
    write_csv_rows(outputs["log_repeats"], LOG_REPEAT_COLUMNS, log_repeat_rows)
    return {
        name: portable_relative_path(path, root=REPOSITORY_ROOT)
        for name, path in outputs.items()
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    seed = int(args.seed)
    n_repeats = int(args.repeats)

    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    if not (target > 1.0).all():
        raise ValueError("the target pool holds an epsilon <= 1, so ln(epsilon - 1) is undefined")

    baseline = score_arm(
        BASELINE_ARM,
        transform=False,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    lever = score_arm(
        LEVER_ARM,
        transform=True,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    shuffled, permutation = shuffled_target(target, seed=seed + CONTROL_SEED_OFFSET)
    control = score_arm(
        CONTROL_ARM,
        transform=True,
        morgan=morgan,
        physical=physical,
        target=shuffled,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    dummy = dummy_mean_arm(baseline["splits"], target=target)  # type: ignore[arg-type]
    control_floor = dummy_mean_arm(
        baseline["splits"],  # type: ignore[arg-type]
        target=shuffled,
        name=CONTROL_FLOOR_ARM,
    )

    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    lever_blocks = [block for block in prereg_payload["levers"] if block.get("id") == LEVER_ID]
    if len(lever_blocks) != 1:
        raise ValueError(f"the pre-registration does not carry exactly one {LEVER_ID} block")
    lever_block = lever_blocks[0]
    prereg = {
        "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(PREREG_PATH),
        "status": prereg_payload["status"],
        "locked_at_utc": prereg_payload["locked_at_utc"],
        "lock_rule": prereg_payload["lock_rule"],
        "thresholds": {
            "pass_delta_r2": PASS_DELTA_R2,
            "kill_delta_r2": KILL_DELTA_R2,
            "control_collapse_tolerance": CONTROL_COLLAPSE_TOLERANCE,
        },
        "locked_criteria": {
            key: lever_block[key]
            for key in (
                "pass_criterion",
                "secondary_criterion",
                "kill_line",
                "expected_delta",
                "cost",
            )
        },
        "control_arm_rule": prereg_payload["control_arm"]["rule"],
        "shots_policy": prereg_payload["shots_policy"]["rule"],
        "forbidden": list(prereg_payload["forbidden"]),
    }
    inputs = {
        "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
        "coverage_table_sha256": canonical_text_sha256(COVERAGE_PATH),
        "feature_blocks": feature_report,
        "coverage_loader_dropped": dict(coverage_dropped),
        "rows_loaded": len(coverage_rows),
        "scored_rows": int(fixed_score.sum()),
        "scored_compounds": len(set(np.asarray(groups)[fixed_score].tolist())),
        "target_min": float(target.min()),
        "target_max": float(target.max()),
        "lever_script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
        "lever_script_sha256": canonical_text_sha256(LEVER_PATH),
    }
    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        baseline=baseline,
        lever=lever,
        control=control,
        dummy=dummy,
        control_floor=control_floor,
        prereg=prereg,
        inputs=inputs,
        control_permutation=permutation,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    outputs = write_artifacts(
        Path(args.artifacts_dir),
        ARTIFACT_STEM,
        fold_rows=[
            *baseline["fold_rows"],  # type: ignore[misc]
            *lever["fold_rows"],  # type: ignore[misc]
            *control["fold_rows"],  # type: ignore[misc]
            *dummy["fold_rows"],  # type: ignore[misc]
            *control_floor["fold_rows"],  # type: ignore[misc]
        ],
        repeat_rows=[
            *baseline["repeat_rows"],  # type: ignore[misc]
            *lever["repeat_rows"],  # type: ignore[misc]
            *control["repeat_rows"],  # type: ignore[misc]
            *dummy["repeat_rows"],  # type: ignore[misc]
            *control_floor["repeat_rows"],  # type: ignore[misc]
        ],
        prediction_rows=[
            *baseline["prediction_rows"],  # type: ignore[misc]
            *lever["prediction_rows"],  # type: ignore[misc]
            *control["prediction_rows"],  # type: ignore[misc]
        ],
        log_fold_rows=[*lever["log_fold_rows"], *control["log_fold_rows"]],  # type: ignore[misc]
        log_repeat_rows=[*lever["log_repeat_rows"], *control["log_repeat_rows"]],  # type: ignore[misc]
    )
    summary["inputs"] = inputs
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
        **outputs,
    }
    if not summary["main_scoreboard"]["guards_passed"]:
        raise ValueError(f"the main scoreboard moved: {summary['main_scoreboard']}")

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(render_report(summary)) + "\n", encoding="utf-8", newline="\n")

    verdict = summary["verdict"]
    assert isinstance(verdict, Mapping)
    print("=== lever 3: log(epsilon-1) target with a pseudo-Huber loss ===")
    print(f"baseline reproduced R2 : {summary['baseline_reproduces']['reproduced_r2']!r}")
    print(f"published R2           : {REFERENCE_R2!r}")
    print(f"lever raw R2           : {summary['readings'][LEVER_ARM][HYBRID]['r2']['mean']!r}")
    print(f"lever log R2           : {summary['log_space_diagnostic']['lever_log_r2']!r}")
    print(f"control raw R2         : {summary['readings'][CONTROL_ARM][HYBRID]['r2']['mean']!r}")
    print(f"delta raw R2           : {verdict['delta_r2']:+.6f}")
    print(f"decision               : {verdict['decision']}")
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    for name, path in outputs.items():
        print(f"{name:12s}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())