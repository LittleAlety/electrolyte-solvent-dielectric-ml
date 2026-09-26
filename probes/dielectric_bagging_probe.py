"""Lever 7 of the Week 14 R2 programme: a bagged XGBoost ensemble.

Appendix X of the execution handbook names seven levers. Lever 7 is the one
whose hypothesis is about *variance*, not bias: the standing complaint against
the frozen hybrid is that its repeat-level R2 readings are scattered, so
bagging the frozen model over independent seeds on the identical folds should
leave the mean roughly where it is while narrowing that spread.

The pre-registration is `probes/dielectric_r2_levers_prereg.json`, locked before
this script was written. Its criteria are read from the file rather than
restated from memory, and they are never relaxed after the fact::

    pass   : mean grouped R2 must not fall by more than 0.0050 AND the standard
             deviation of the repeat-level R2 readings must shrink by at least
             20 percent relative to the baseline arm
    kill   : mean R2 falls by more than 0.0050, or the standard deviation
             shrinks by less than 20 percent -> dead
    control: the same model with the labels permuted must collapse

The real deliverable is the interval, not the mean: a variance claim without a
narrowed interval is not a result.

The main scoreboard - 457 scored rows of 97 compounds, GroupKFold by InChIKey,
5 folds x 10 repeats, seed 42, min_test_rows_per_fold 2 - is not re-implemented
here. The scored mask, the fold dealing, the model specification and the metric
aggregation are all imported from the published probes, so the baseline arm is
a re-run of `paired_base` rather than a look-alike:

* `dielectric_coverage_paired_benchmark` - feature blocks, the coverage loader,
  the scored mask recipe (`thermoml_zero_frequency` AND `room_temperature`);
* `dielectric_room_window_paired.masked_splits` - the paired fold dealing;
* `dielectric_band_ablation.drop_thin_folds` / `effective_repeats`;
* `dielectric_observations_grouped_benchmark.run_protocol` - the frozen
  baseline arm: the hybrid (`Morgan+Physical`), `XGB_PARAMS`, the per-fold
  metrics, the repeat aggregation.

The bagged arm cannot go through `run_protocol`, because that helper fits one
model per representation and scores it. It therefore re-implements the frozen
fit loop with the ensemble inserted, exactly as lever 3 re-implemented it with
the target transform inserted. The fold dealing is not re-implemented: the
bagged arm is handed the *same* `splits` object the baseline arm consumed, and
`scored_fold_signature` is compared across the arms to prove it.

The probe is read-only with respect to every frozen artefact. It writes only
`probes/dielectric_bagging_probe_summary.json`,
`probes/artifacts/dielectric_bagging_*.csv` and
`reports/dielectric_bagging_probe.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
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
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_bagging_probe_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_bagging_probe.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_bagging"
PROBE_PATH = Path(__file__).resolve()

LEVER_ID = "lever_7_bagging"
BASELINE_ARM = "paired_base"
LEVER_ARM = LEVER_ID
CONTROL_ARM = "dummy_control"
DUMMY_MEAN_ARM = "dummy_mean_reference"
#: The same fold-mean floor, but scored on the control arm's own permuted
#: labels, so the collapse test compares like with like.
CONTROL_FLOOR_ARM = "dummy_mean_control_floor"
DUMMY_REPRESENTATION = "DummyMean"

#: The published `paired_base` hybrid R2 every report has to reproduce first.
REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
#: The same three readings for the two single representations, pinned so a
#: drift in the fold dealing cannot hide behind the hybrid alone.
REFERENCE_TRIPLE = {
    "Morgan": 0.06487386371009436,
    "Morgan+Physical": REFERENCE_R2,
    "Physical": 0.2531659995294713,
}

#: Pre-registered constants. These are the values frozen in the JSON before the
#: run; a test asserts they still equal the literals in the pre-registration.
N_BAGS = 10
BAG_SEED_MULTIPLIER = 1000
MEAN_TOLERANCE = 0.0050
STD_SHRINK_REQUIRED = 0.20
CONTROL_COLLAPSE_TOLERANCE = 0.02
CONTROL_SEED_OFFSET = 1
SHOTS_THIS_LEVER = 1
#: Declared, not pre-registered: the band inside which a MAE move is called
#: noise rather than a regression. Spelled out here so the reading is auditable.
SECONDARY_NOISE_BAND = 0.02
#: The bagged arm is scored on the main scoreboard's representation only. The
#: single representations exist to police the fold dealing in the baseline arm,
#: and bagging them would double the run for no judged quantity.
BAGGED_REPRESENTATIONS = (HYBRID,)

#: The main scoreboard this probe may not move.
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_FOLDS = 50

#: Fold-level parallelism. Each fit is independent and seeded, so the number of
#: workers cannot change a single number; it only changes the wall clock.
DEFAULT_WORKERS = 6

SCORED_ARM_META = "XGBRegressor with XGB_PARAMS, frozen hyper-parameters, bagged over independent seeds"

def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the report."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def build_shared_splits(
    groups: Sequence[str],
    *,
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> tuple[list[tuple[int, int, np.ndarray, np.ndarray]], dict[str, object], int, str]:
    """Deal the folds once, so every arm of this probe consumes the same object.

    The baseline arm handed to `run_protocol` and the bagged arm running through
    the re-implemented fit loop must be scored on identical folds; handing them
    one shared list is the strongest form of that guarantee, and the audit below
    refuses to return a dealing that lets a compound straddle a boundary.
    """

    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    compound_count = int(np.unique(np.asarray(groups)[score]).size)
    repeats, note = effective_repeats(compound_count, n_splits=n_splits, requested=n_repeats)
    if repeats == 0:
        raise ValueError(f"no repeat can fill {n_splits} grouped folds")
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
        raise ValueError("no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError("a scored row sits outside the score mask")
    if audit["folds_with_a_straddling_compound"]:
        raise ValueError("a compound straddles the fold boundary")
    return splits, audit, repeats, note


def _fit_member(
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> np.ndarray:
    """One bag: the frozen model, the frozen hyper-parameters, its own seed."""

    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(features[train_indices], target[train_indices])
    return model.predict(features[test_indices])


def bagged_fold_predictions(
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    n_bags: int = N_BAGS,
    seed: int = SEED,
) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    """The bagged hybrid for one fold, plus the two member stacks.

    The frozen hybrid combines the two representations *before* any averaging
    (``0.5 * (morgan + physical)``), so the ensemble is built the same way: one
    complete hybrid prediction per bag, then the bags averaged, then the frozen
    non-negativity clip. Averaging the two representations afterwards would give
    the same number algebraically and is not what "the same model, averaged"
    means, so it is not what is computed.
    """

    hybrid_members: list[np.ndarray] = []
    morgan_members: list[np.ndarray] = []
    physical_members: list[np.ndarray] = []
    for bag_index in range(n_bags):
        bag_seed = seed * BAG_SEED_MULTIPLIER + bag_index
        morgan_prediction = _fit_member(morgan, target, train_indices, test_indices, bag_seed)
        physical_prediction = _fit_member(
            physical, target, train_indices, test_indices, bag_seed
        )
        morgan_members.append(morgan_prediction)
        physical_members.append(physical_prediction)
        hybrid_members.append(0.5 * (morgan_prediction + physical_prediction))
    average = np.mean(np.vstack(hybrid_members), axis=0)
    return np.maximum(average, 1.0), morgan_members, physical_members


_WORKER_STATE: dict[str, object] = {}


def _initialise_worker(payload: Mapping[str, object]) -> None:
    _WORKER_STATE.clear()
    _WORKER_STATE.update(payload)


def bagged_fold_task(task: Mapping[str, object]) -> dict[str, object]:
    """Score one fold of the bagged arm inside a worker process.

    The state is loaded once per worker by `_initialise_worker`; the task carries
    only what differs between folds - the fold identity, its indices and the
    target vector, which is the real one for the bagged arm and the permuted one
    for the control arm.
    """

    morgan = _WORKER_STATE["morgan"]
    physical = _WORKER_STATE["physical"]
    groups = _WORKER_STATE["groups"]
    temperatures = _WORKER_STATE["temperatures"]
    n_bags = int(_WORKER_STATE["n_bags"])
    seed = int(_WORKER_STATE["seed"])

    repeat = int(task["repeat"])
    fold = int(task["fold"])
    train_indices = np.asarray(task["train_indices"], dtype=int)
    test_indices = np.asarray(task["test_indices"], dtype=int)
    target = np.asarray(task["target"], dtype=float)

    prediction, _morgan_members, _physical_members = bagged_fold_predictions(
        morgan=morgan,
        physical=physical,
        target=target,
        train_indices=train_indices,
        test_indices=test_indices,
        n_bags=n_bags,
        seed=seed,
    )
    group_array = np.asarray(groups)
    return {
        "repeat": repeat,
        "fold": fold,
        "train_rows": int(train_indices.size),
        "test_rows": int(test_indices.size),
        "train_compounds": int(np.unique(group_array[train_indices]).size),
        "test_compounds": int(np.unique(group_array[test_indices]).size),
        "straddling": int(
            np.intersect1d(group_array[train_indices], group_array[test_indices]).size
        ),
        "inchikeys": [str(groups[int(index)]) for index in test_indices],
        "T_K": [float(temperatures[int(index)]) for index in test_indices],
        "target": [float(value) for value in target[test_indices]],
        "prediction": [float(value) for value in prediction],
        "metrics": evaluate_repeat(target[test_indices], prediction),
    }


def run_bagged_arm(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    n_bags: int = N_BAGS,
    seed: int = SEED,
    workers: int = DEFAULT_WORKERS,
    train_pool_rows: int,
    train_pool_compounds: int,
) -> dict[str, object]:
    """Score the bagged arm over the shared folds, in parallel across folds.

    Averaging happens before scoring: every fold hands back one prediction per
    scored row, already the mean of its bags, and `evaluate_repeat` sees exactly
    the vector the baseline arm's single model would have produced.
    """

    tasks = [
        {
            "repeat": int(repeat),
            "fold": int(fold),
            "train_indices": np.asarray(train_index, dtype=int),
            "test_indices": np.asarray(test_index, dtype=int),
            "target": np.asarray(target, dtype=float),
        }
        for repeat, fold, train_index, test_index in splits
    ]
    payload = {
        "morgan": morgan,
        "physical": physical,
        "groups": np.asarray(groups),
        "temperatures": np.asarray(temperatures, dtype=float),
        "n_bags": int(n_bags),
        "seed": int(seed),
    }
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(
            max_workers=int(workers), initializer=_initialise_worker, initargs=(payload,)
        ) as executor:
            results = list(executor.map(bagged_fold_task, tasks))
    else:
        _initialise_worker(payload)
        results = [bagged_fold_task(task) for task in tasks]

    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    buckets: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    straddling: list[int] = []
    for result in results:
        repeat = int(result["repeat"])
        fold = int(result["fold"])
        metrics = result["metrics"]
        straddling.append(int(result["straddling"]))
        fold_rows.append(
            {
                "protocol": name,
                "representation": HYBRID,
                "repeat": repeat,
                "fold": fold,
                "train_rows": int(result["train_rows"]),
                "test_rows": int(result["test_rows"]),
                "train_compounds": int(result["train_compounds"]),
                "test_compounds": int(result["test_compounds"]),
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "r2": metrics["r2"],
                "spearman": metrics["spearman"],
            }
        )
        bucket = buckets[repeat]
        bucket["target"].extend(result["target"])
        bucket["prediction"].extend(result["prediction"])
        for inchikey, temperature, observed, predicted in zip(
            result["inchikeys"],
            result["T_K"],
            result["target"],
            result["prediction"],
            strict=True,
        ):
            prediction_rows.append(
                {
                    "protocol": name,
                    "representation": HYBRID,
                    "repeat": repeat,
                    "fold": fold,
                    "inchikey": inchikey,
                    "T_K": temperature,
                    "target": observed,
                    "prediction": predicted,
                }
            )

    repeat_rows: list[dict[str, object]] = []
    for repeat in sorted(buckets):
        bucket = buckets[repeat]
        metrics = evaluate_repeat(
            np.asarray(bucket["target"], dtype=float),
            np.asarray(bucket["prediction"], dtype=float),
        )
        repeat_rows.append(
            {
                "protocol": name,
                "representation": HYBRID,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    leak = {
        "folds": len(straddling),
        "folds_with_a_straddling_compound": sum(1 for count in straddling if count),
        "max_straddling_compounds_in_a_fold": max(straddling) if straddling else 0,
    }
    summary = summarize_repeats(repeat_rows)
    if name not in summary:
        raise ValueError(f"{name}: the bagged arm produced no repeat rows")
    return {
        "arm": name,
        "meta": {
            "scored_rows": int(sum(int(result["test_rows"]) for result in results)),
            "compounds_scored": len(
                {
                    inchikey
                    for result in results
                    for inchikey in result["inchikeys"]
                }
            ),
            "train_pool_rows": int(train_pool_rows),
            "train_pool_compounds": int(train_pool_compounds),
            "requested_repeats": len({int(result["repeat"]) for result in results}),
            "executed_repeats": len({int(result["repeat"]) for result in results}),
            "folds": len(results),
            "model": SCORED_ARM_META,
            "objective": XGB_PARAMS["objective"],
            "splitter": "grouped by InChIKey (masked_splits)",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "seed": seed,
            "n_bags": int(n_bags),
            "bag_seeds": [int(seed) * BAG_SEED_MULTIPLIER + bag for bag in range(n_bags)],
            "representations_scored": list(BAGGED_REPRESENTATIONS),
        },
        "leak_reference": leak,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summary[name],
        "summary_by_protocol": summary,
    }

def run_dummy_mean_arm(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    target: np.ndarray,
    groups: Sequence[str],
) -> dict[str, object]:
    """The no-information floor: the fold-mean of the training side.

    This is what a model that has learned nothing scores on these exact folds,
    so the control arm can be measured against a floor rather than against the
    real-label baseline - a comparison the pre-registration's literal wording
    makes unsatisfiable by construction.
    """

    values = np.asarray(target, dtype=float)
    group_array = np.asarray(groups)
    fold_rows: list[dict[str, object]] = []
    buckets: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    for repeat, fold, train_index, test_index in splits:
        prediction = np.full(test_index.size, float(np.mean(values[train_index])))
        metrics = evaluate_repeat(values[test_index], prediction)
        fold_rows.append(
            {
                "protocol": name,
                "representation": DUMMY_REPRESENTATION,
                "repeat": int(repeat),
                "fold": int(fold),
                "train_rows": int(train_index.size),
                "test_rows": int(test_index.size),
                "train_compounds": int(np.unique(group_array[train_index]).size),
                "test_compounds": int(np.unique(group_array[test_index]).size),
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "r2": metrics["r2"],
                "spearman": metrics["spearman"],
            }
        )
        bucket = buckets[int(repeat)]
        bucket["target"].extend(float(value) for value in values[test_index])
        bucket["prediction"].extend(float(value) for value in prediction)
    repeat_rows: list[dict[str, object]] = []
    for repeat in sorted(buckets):
        bucket = buckets[repeat]
        metrics = evaluate_repeat(
            np.asarray(bucket["target"], dtype=float),
            np.asarray(bucket["prediction"], dtype=float),
        )
        repeat_rows.append(
            {
                "protocol": name,
                "representation": DUMMY_REPRESENTATION,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    return {
        "arm": name,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "summary": summarize_repeats(repeat_rows),
    }


def shuffled_target(target: np.ndarray, *, seed: int) -> tuple[np.ndarray, list[int]]:
    """Permute the labels over the whole row pool for the control arm.

    The permutation is drawn once from a seed that is *not* the fold seed, so the
    control cannot accidentally inherit a fold assignment, and it is applied to
    the full table rather than to the scored mask, so the training side is
    shuffled too.
    """

    values = np.asarray(target, dtype=float)
    order = np.random.default_rng(seed).permutation(values.size)
    return values[order], [int(index) for index in order]


def _reading(summary: Mapping[str, Mapping[str, Mapping[str, float]]], metric: str) -> dict[str, float]:
    block = summary[metric]
    return {
        "mean": float(block["mean"]),
        "std": float(block["std"]),
        "n": int(block["n"]),
    }


def readings_from(
    summaries: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arms: Sequence[str],
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    return {
        arm: {
            representation: {
                metric: _reading(summaries[arm][representation], metric)
                for metric in METRIC_NAMES
            }
            for representation in summaries[arm]
        }
        for arm in arms
        if arm in summaries
    }


def control_collapse_readout(
    *,
    control_r2: float,
    floor_r2: float,
    floor_r2_real_labels: float,
    baseline_r2: float,
) -> dict[str, object]:
    """Judge the shuffled-label arm against the no-information floor.

    The pre-registration says the control must collapse to ``|delta R2| <= 0.02``
    without naming a reference. Measured against the real-label baseline the test
    is unsatisfiable by construction - a permuted label vector cannot score
    anywhere near a fitted model - so both readings are reported and the primary
    rule is the one the sentence is actually about: the shuffled-label arm must
    not *beat* the no-information floor by more than the tolerance.
    """

    delta_over_the_floor = control_r2 - floor_r2
    over_the_floor = abs(delta_over_the_floor)
    return {
        "control_r2": control_r2,
        "trivial_floor_r2": floor_r2,
        "trivial_floor_definition": (
            "the fold-mean predictor scored on the identical folds and on the "
            "identical (permuted) label vector as the control arm"
        ),
        "trivial_floor_r2_real_labels": floor_r2_real_labels,
        "delta_over_the_floor": delta_over_the_floor,
        "abs_delta_over_the_floor": over_the_floor,
        "baseline_r2": baseline_r2,
        "delta_vs_the_real_label_baseline": control_r2 - baseline_r2,
        "tolerance": CONTROL_COLLAPSE_TOLERANCE,
        "primary_rule": (
            "the shuffled-label arm must not beat the trivial-mean floor by more "
            "than the tolerance"
        ),
        "collapsed": bool(delta_over_the_floor <= CONTROL_COLLAPSE_TOLERANCE),
        "two_sided_against_the_floor_also_passes": bool(
            over_the_floor <= CONTROL_COLLAPSE_TOLERANCE
        ),
        "literal_wording_is_satisfiable": False,
        "wording_note": (
            "the pre-registration names no reference for the collapse delta; "
            "measured against the real-label baseline the test is unsatisfiable "
            "by construction, so the control is measured against the "
            "no-information floor and both readings are reported"
        ),
    }


def verify_reference_triple(
    summaries: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arm: str,
) -> dict[str, object]:
    representations = {
        name: {
            "expected": REFERENCE_TRIPLE[name],
            "reproduced": float(summaries[arm][name]["r2"]["mean"]),
            "abs_difference": abs(float(summaries[arm][name]["r2"]["mean"]) - REFERENCE_TRIPLE[name]),
            "bit_exact": float(summaries[arm][name]["r2"]["mean"]) == REFERENCE_TRIPLE[name],
        }
        for name in REFERENCE_TRIPLE
    }
    return {
        "arm": arm,
        "representations": representations,
        "all_bit_exact": all(block["bit_exact"] for block in representations.values()),
        "tolerance": REFERENCE_TOLERANCE,
    }


def build_verdict(
    *,
    baseline_verified: bool,
    baseline_reading: Mapping[str, Mapping[str, float]],
    lever_reading: Mapping[str, Mapping[str, float]],
    control: Mapping[str, object],
    control_collapse: Mapping[str, object],
) -> dict[str, object]:
    """Apply the pre-registered pass criterion and its kill line, verbatim.

    The lever passes only when *both* halves of the sentence hold: the mean has
    not fallen by more than 0.0050 **and** the repeat-level standard deviation
    has shrunk by at least 20 percent. The real deliverable is the interval, so a
    flat mean with a narrowed interval is a pass and a lifted mean with a wide
    interval is not.
    """

    baseline_mean = float(baseline_reading["r2"]["mean"])
    baseline_std = float(baseline_reading["r2"]["std"])
    lever_mean = float(lever_reading["r2"]["mean"])
    lever_std = float(lever_reading["r2"]["std"])
    delta_mean = lever_mean - baseline_mean
    shrink = (baseline_std - lever_std) / baseline_std if baseline_std > 0 else float("nan")
    mean_ok = bool(delta_mean >= -MEAN_TOLERANCE)
    shrink_ok = bool(np.isfinite(shrink) and shrink >= STD_SHRINK_REQUIRED)
    control_ok = bool(control_collapse["collapsed"])

    baseline_mae = float(baseline_reading["mae"]["mean"])
    delta_mae = float(lever_reading["mae"]["mean"]) - baseline_mae
    delta_mae_gt60 = float(lever_reading["mae_gt60"]["mean"]) - float(
        baseline_reading["mae_gt60"]["mean"]
    )
    delta_spearman = float(lever_reading["spearman"]["mean"]) - float(
        baseline_reading["spearman"]["mean"]
    )
    secondary = {
        "delta_mae": delta_mae,
        "delta_mae_gt60": delta_mae_gt60,
        "delta_spearman": delta_spearman,
        "noise_band": SECONDARY_NOISE_BAND,
        "noise_band_definition": "a MAE move inside 2 percent of the baseline MAE is called noise",
        "mae_ok": bool(abs(delta_mae) <= baseline_mae * SECONDARY_NOISE_BAND),
        "mae_gt60_ok": bool(
            abs(delta_mae_gt60)
            <= abs(float(baseline_reading["mae_gt60"]["mean"])) * SECONDARY_NOISE_BAND
        ),
    }

    if not baseline_verified:
        decision = "unverified"
    elif mean_ok and shrink_ok and control_ok:
        decision = "pass"
    else:
        decision = "dead"

    reasons = [
        (
            f"mean grouped R2 moved by {delta_mean:+.6f}, against a pre-registered "
            f"floor of -{MEAN_TOLERANCE:.4f}"
        ),
        (
            f"repeat-level R2 std moved from {baseline_std:.6f} to {lever_std:.6f} "
            f"({shrink * 100:+.2f} percent), against a required shrink of "
            f"{STD_SHRINK_REQUIRED * 100:.0f} percent"
        ),
    ]
    if not mean_ok:
        reasons.append("the mean fell by more than the pre-registered 0.0050")
    if not shrink_ok:
        reasons.append("the interval did not narrow by the pre-registered 20 percent")
    if not control_ok:
        reasons.append("the shuffled-label control did not collapse")
    if not baseline_verified:
        reasons.append("the baseline arm did not reproduce, so no delta from this run may be quoted")

    return {
        "decision": decision,
        "reasons": reasons,
        "criteria_applied": {
            "pass_criterion": (
                "mean grouped R2 must not fall by more than 0.0050 AND the standard "
                "deviation of the repeat-level R2 readings must shrink by at least "
                "20 percent relative to the baseline arm"
            ),
            "kill_line": (
                "mean R2 falls by more than 0.0050, or the standard deviation shrinks "
                "by less than 20 percent -> dead"
            ),
            "control_rule": (
                "each lever carries a shuffled-label control: a lever may only be "
                "called real if its control collapses"
            ),
        },
        "delta_mean_r2": delta_mean,
        "baseline_mean_r2": baseline_mean,
        "lever_mean_r2": lever_mean,
        "baseline_std_r2": baseline_std,
        "lever_std_r2": lever_std,
        "std_shrink_percent": float(shrink * 100.0),
        "mean_ok": mean_ok,
        "std_shrink_ok": shrink_ok,
        "control_collapsed": control_ok,
        "secondary": secondary,
        "control_delta_r2": float(control.get("delta_r2", float("nan"))),
        "carried_into_the_merge_arm": bool(decision == "pass"),
    }

def build_summary(
    *,
    seed: int,
    n_repeats: int,
    workers: int,
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
    arms = (BASELINE_ARM, LEVER_ARM, CONTROL_ARM, DUMMY_MEAN_ARM, CONTROL_FLOOR_ARM)
    merged_summaries = {
        **summaries,
        DUMMY_MEAN_ARM: dummy["summary"][DUMMY_MEAN_ARM],  # type: ignore[index]
        CONTROL_FLOOR_ARM: control_floor["summary"][CONTROL_FLOOR_ARM],  # type: ignore[index]
    }
    reference_triple = verify_reference_triple(summaries, BASELINE_ARM)  # type: ignore[arg-type]
    baseline_reproduces = {
        "arm": BASELINE_ARM,
        "representation": HYBRID,
        "published_r2": REFERENCE_R2,
        "reproduced_r2": float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]),
        "abs_difference": abs(
            float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]) - REFERENCE_R2
        ),
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
        name: scored_fold_signature(block)  # type: ignore[arg-type]
        for name, block in ((BASELINE_ARM, baseline["splits"]), (LEVER_ARM, lever["splits"]))
    }
    folds_shared = len(set(signatures.values())) == 1 and len(signatures) == 2
    control_collapse = control_collapse_readout(
        control_r2=float(merged_summaries[CONTROL_ARM][HYBRID]["r2"]["mean"]),
        floor_r2=float(merged_summaries[CONTROL_FLOOR_ARM][DUMMY_REPRESENTATION]["r2"]["mean"]),
        floor_r2_real_labels=float(
            merged_summaries[DUMMY_MEAN_ARM][DUMMY_REPRESENTATION]["r2"]["mean"]
        ),
        baseline_r2=float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]),
    )
    verdict = build_verdict(
        baseline_verified=bool(baseline_reproduces["bit_exact"]),
        baseline_reading=merged_summaries[BASELINE_ARM][HYBRID],
        lever_reading=merged_summaries[LEVER_ARM][HYBRID],
        control=control_delta,
        control_collapse=control_collapse,
    )
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
        "shifted_or_resized": False,
    }
    scoreboard["guards_passed"] = bool(
        scoreboard["rows_scored"] == SCOREBOARD_ROWS
        and scoreboard["compounds_scored"] == SCOREBOARD_COMPOUNDS
        and scoreboard["folds_measured"] == scoreboard["expected_folds"]
    )
    return {
        "schema_version": 1,
        "task": "week14_r2_levers",
        "lever_id": LEVER_ID,
        "title": "Lever 7: bagged XGBoost ensemble",
        "generated_at_utc": generated_at,
        "prereg": dict(prereg),
        "locked_criteria": dict(prereg.get("locked_criteria", {})),
        "main_scoreboard": scoreboard,
        "baseline_reproduces": baseline_reproduces,
        "reference_triple": reference_triple,
        "ensemble": {
            "n_bags": N_BAGS,
            "bag_seeds": [seed * BAG_SEED_MULTIPLIER + bag for bag in range(N_BAGS)],
            "bag_seed_rule": "random_state = seed * 1000 + bag index",
            "averaging": "one complete hybrid prediction per bag, then the bags averaged, then the frozen non-negativity clip",
            "representations_scored": list(BAGGED_REPRESENTATIONS),
            "hyper_parameters": dict(XGB_PARAMS),
            "hyper_parameters_changed": [],
        },
        "arms": {
            "baseline": {
                "meta": baseline["meta"],
                "audit": baseline["audit"],
                "leak_reference": baseline["leak_reference"],
            },
            "lever": {"meta": lever["meta"], "leak_reference": lever["leak_reference"]},
            "control": {"meta": control["meta"], "leak_reference": control["leak_reference"]},
            "dummy_mean": {"arm": DUMMY_MEAN_ARM, "folds": len(dummy["fold_rows"])},  # type: ignore[arg-type]
            "dummy_mean_control_floor": {
                "arm": CONTROL_FLOOR_ARM,
                "folds": len(control_floor["fold_rows"]),  # type: ignore[arg-type]
            },
        },
        "readings": readings_from(merged_summaries, arms),
        "delta": delta,
        "control": control_delta,
        "control_collapse": control_collapse,
        "lever_minus_control": lever_minus_control,
        "control_permutation": {
            "seed": seed + CONTROL_SEED_OFFSET,
            "rows": len(control_permutation),
            "first_ten": list(control_permutation[:10]),
            "sha256_of_order": hashlib.sha256(
                "".join(f"{index}," for index in control_permutation).encode("utf-8")
            ).hexdigest(),
        },
        "shared_folds": {
            "arms": [BASELINE_ARM, LEVER_ARM],
            "scored_side_identical": bool(folds_shared),
            "statement": "the bagged arm was handed the same fold assignment the baseline arm consumed",
        },
        "verdict": verdict,
        "shots": {
            "this_lever": SHOTS_THIS_LEVER,
            "control_arm_shots": 1,
            "policy": "every scored attempt at the main scoreboard counts, including dead ones",
        },
        "honest_boundaries": [
            "the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool",
            "0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions",
            "no random_row split was constructed, let alone judged",
            "test residuals did not steer anything: n_bags and the bag-seed rule were frozen in the pre-registration",
            "the scored pool, the fold numbers and the metric denominator did not move; only the fitted model did",
            "every frozen hyper-parameter is untouched; bagging changes how many models are fitted, not what one model is",
            "the bagged arm is scored on the main scoreboard's representation only; the single representations are not re-bagged",
            "the bagged arm re-implements the frozen fit loop because the frozen helper fits exactly one model per representation; the baseline arm does not",
            "the number of worker processes cannot move a number: every fit is independent and seeded",
        ],
        "outputs": {},
    }


def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the markdown report from the summary, so the two cannot drift."""

    scoreboard = summary["main_scoreboard"]
    verdict = summary["verdict"]
    collapse = summary["control_collapse"]
    readings = summary["readings"]
    baseline = readings[BASELINE_ARM][HYBRID]
    control = readings[CONTROL_ARM][HYBRID]
    secondary = verdict["secondary"]
    ensemble = summary["ensemble"]
    lines = [
        "# 杠杆 7：XGBoost bagging 集成（Week 14 R2 攻坚）",
        "",
        (
            "> 本文由 `probes/dielectric_bagging_probe.py` 从 "
            "`probes/dielectric_bagging_probe_summary.json` 确定性渲染；"
            "数字与摘要同源，改一处必须重跑脚本。"
        ),
        "",
        "## 一、口径与预注册",
        "",
        (
            f"- 预注册：`probes/dielectric_r2_levers_prereg.json`"
            f"（status=`{summary['prereg']['status']}`，"
            f"sha256=`{summary['prereg']['sha256']}`），判据先锁后跑、事后不放宽"
        ),
        (
            f"- 主记分牌：{scoreboard['rows_scored']} 行 / "
            f"{scoreboard['compounds_scored']} 化合物，GroupKFold by InChIKey，"
            f"{scoreboard['n_splits']} 折 × {scoreboard['n_repeats']} 重复，"
            f"seed={scoreboard['seed']}，"
            f"min_test_rows_per_fold={scoreboard['min_test_rows_per_fold']}"
        ),
        (
            f"- 折划分：bagging 臂直接复用基准臂消费的同一份 `splits`，"
            f"实测折数 = {scoreboard['folds_measured']}，"
            f"评分侧签名一致 = {summary['shared_folds']['scored_side_identical']}"
            f"（{summary['shared_folds']['statement']}）"
        ),
        (
            f"- 基准读数（本脚本内原地重跑）`paired_base` 混合表示 R² = "
            f"{float(summary['baseline_reproduces']['reproduced_r2']):.16f}"
            f"（已发布值 {REFERENCE_R2:.16f}，"
            f"|Δ| = {float(summary['baseline_reproduces']['abs_difference']):.3e}，"
            f"容差 {REFERENCE_TOLERANCE:g}）→ "
            f"复现{'成立' if summary['baseline_reproduces']['bit_exact'] else '不成立'}"
        ),
        "",
        "## 二、集成规格（预注册原文）",
        "",
        f"- 成员数 n_bags = {ensemble['n_bags']}；种子规则 `{ensemble['bag_seed_rule']}`",
        f"- 实际成员种子：{ensemble['bag_seeds']}",
        (
            f"- 冻结超参：`{ensemble['hyper_parameters']}`；"
            f"改动过的超参：{ensemble['hyper_parameters_changed'] or '无'}"
        ),
        f"- 平均口径：{ensemble['averaging']}",
        (
            f"- 本臂评分的表示：{ensemble['representations_scored']}"
            f"（单表示不重复 bagging，只用于基准臂的折号对账）"
        ),
        "",
        "## 三、三臂读数（混合表示 `Morgan+Physical`）",
        "",
        "| 臂 | R² 均值 | R² 标准差 | MAE | MAE·ε>60 | Spearman |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm, label in (
        (BASELINE_ARM, "基准臂（原样重跑）"),
        (LEVER_ARM, "bagging 臂（10 成员平均）"),
        (CONTROL_ARM, "安慰剂臂（同模型、标签打乱）"),
    ):
        block = readings[arm][HYBRID]
        lines.append(
            f"| {label} | {float(block['r2']['mean']):.6f} | "
            f"{float(block['r2']['std']):.6f} | {float(block['mae']['mean']):.6f} | "
            f"{float(block['mae_gt60']['mean']):.6f} | "
            f"{float(block['spearman']['mean']):.6f} |"
        )
    lines += [
        "",
        (
            f"- 均值位移：**{float(verdict['delta_mean_r2']):+.6f}**"
            f"（下限 -{MEAN_TOLERANCE:.4f}，{'达标' if verdict['mean_ok'] else '越界'}）"
        ),
        (
            f"- 重复级 R² 标准差：{float(verdict['baseline_std_r2']):.6f} → "
            f"{float(verdict['lever_std_r2']):.6f} = "
            f"**{float(verdict['std_shrink_percent']):+.2f}%**"
            f"（要求收窄 ≥ {STD_SHRINK_REQUIRED * 100:.0f}%，"
            f"{'达标' if verdict['std_shrink_ok'] else '未达标'}）"
        ),
        (
            "- 本杠杆真正交付的是**区间**而不是均值：均值不掉不等于结论，"
            "只有区间被压窄才算数。"
        ),
        "",
        "## 四、判决",
        "",
        f"**{str(verdict['decision']).upper()}**",
        "",
    ]
    lines += [f"- {reason}" for reason in verdict["reasons"]]
    lines += [
        "",
        (
            f"- 次要判据：ΔMAE = {float(secondary['delta_mae']):+.6f}"
            f"（声明噪声带 {float(secondary['noise_band']):.0%} 内："
            f"{secondary['mae_ok']}）；ΔMAE·ε>60 = "
            f"{float(secondary['delta_mae_gt60']):+.6f}"
            f"（带内：{secondary['mae_gt60_ok']}）；ΔSpearman = "
            f"{float(secondary['delta_spearman']):+.6f}"
        ),
        f"- 噪声带定义：{secondary['noise_band_definition']}（声明值，非预注册值）",
        "",
        "## 五、安慰剂对照",
        "",
        (
            f"- 打乱标签臂 R² = {float(control['r2']['mean']):.6f}"
            f"（基准臂重跑 {float(baseline['r2']['mean']):.6f}）"
        ),
        (
            f"- **同一套打乱标签**上的无信息地板（折内训练均值）= "
            f"{float(collapse['trivial_floor_r2']):.6f}"
        ),
        (
            f"- 相对地板：{float(collapse['delta_over_the_floor']):+.6f}"
            f"（|Δ| = {float(collapse['abs_delta_over_the_floor']):.6f}，"
            f"容差 {collapse['tolerance']}）"
        ),
        (
            f"- 塌缩：**{collapse['collapsed']}**；严格双侧口径是否也达标："
            f"{collapse['two_sided_against_the_floor_also_passes']}"
        ),
        f"- 口径说明：{collapse['wording_note']}",
        "",
        "## 六、共享折号",
        "",
        (
            f"- {summary['shared_folds']['statement']}"
            f"（评分侧一致：{summary['shared_folds']['scored_side_identical']}）"
        ),
        "",
        "## 七、合并臂状态",
        "",
        (
            "- 本探针只回答「杠杆 7 自身是否过门」"
            f"（是否进入合并臂：{verdict['carried_into_the_merge_arm']}）；"
            "合并臂是否开跑由预注册 `merge_rule` 与集群收口决定。"
        ),
        "",
        "## 八、shots 计数",
        "",
        (
            f"- 本杠杆：**{summary['shots']['this_lever']}** 次主记分牌实测；"
            f"安慰剂臂 {summary['shots']['control_arm_shots']} 次"
        ),
        f"- 口径：{summary['shots']['policy']}",
        "",
        "## 九、诚实边界",
        "",
    ]
    lines += [f"- {item}" for item in summary["honest_boundaries"]]
    lines += [
        "",
        "## 十、产物",
        "",
    ]
    lines += [f"- `{name}`：`{path}`" for name, path in sorted(summary["outputs"].items())]
    lines.append("")
    return lines


def write_artifacts(
    directory: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "folds": directory / f"{stem}_folds.csv",
        "repeats": directory / f"{stem}_repeats.csv",
        "predictions": directory / f"{stem}_predictions.csv",
    }
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(outputs["repeats"], ("protocol", "representation", "repeat", *METRIC_NAMES), repeat_rows)
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    return {
        name: portable_relative_path(path, root=REPOSITORY_ROOT)
        for name, path in outputs.items()
    }


def check_summary(summary: Mapping[str, object]) -> list[str]:
    """Re-derive the verdict from the stored readings without refitting anything."""

    problems: list[str] = []
    readings = summary["readings"]
    verdict = summary["verdict"]

    def look(arm: str, metric: str) -> float:
        return float(readings[arm][HYBRID][metric]["mean"])  # type: ignore[index]

    recomputed = build_verdict(
        baseline_verified=bool(summary["baseline_reproduces"]["bit_exact"]),  # type: ignore[index]
        baseline_reading=readings[BASELINE_ARM][HYBRID],  # type: ignore[index]
        lever_reading=readings[LEVER_ARM][HYBRID],  # type: ignore[index]
        control=summary["control"],  # type: ignore[arg-type]
        control_collapse=summary["control_collapse"],  # type: ignore[arg-type]
    )
    if recomputed["decision"] != verdict["decision"]:  # type: ignore[index]
        problems.append("the stored verdict does not survive a re-derivation from the stored readings")
    if round(float(verdict["delta_mean_r2"]), 12) != round(look(LEVER_ARM, "r2") - look(BASELINE_ARM, "r2"), 12):  # type: ignore[index]
        problems.append("the stored mean delta is not the difference of the stored means")
    baseline_std = float(readings[BASELINE_ARM][HYBRID]["r2"]["std"])  # type: ignore[index]
    lever_std = float(readings[LEVER_ARM][HYBRID]["r2"]["std"])  # type: ignore[index]
    shrink = (baseline_std - lever_std) / baseline_std
    if abs(shrink * 100.0 - float(verdict["std_shrink_percent"])) > 1e-9:  # type: ignore[index]
        problems.append("the stored std shrink does not survive a re-derivation")
    if abs(look(BASELINE_ARM, "r2") - REFERENCE_R2) > REFERENCE_TOLERANCE:
        problems.append("the baseline hybrid R2 no longer equals the published reference")
    reference = summary["reference_triple"]
    for name, block in reference["representations"].items():  # type: ignore[union-attr]
        if abs(float(block["reproduced"]) - float(block["expected"])) > REFERENCE_TOLERANCE:
            problems.append(f"the reference triple drifted for {name}")
    scoreboard = summary["main_scoreboard"]
    if int(scoreboard["rows_scored"]) != SCOREBOARD_ROWS:  # type: ignore[index]
        problems.append("the scored row count is not the frozen 457")
    if int(scoreboard["compounds_scored"]) != SCOREBOARD_COMPOUNDS:  # type: ignore[index]
        problems.append("the scored compound count is not the frozen 97")
    if int(scoreboard["folds_measured"]) != SCOREBOARD_FOLDS:  # type: ignore[index]
        problems.append("the fold count is not the frozen 50")
    if not bool(summary["shared_folds"]["scored_side_identical"]):  # type: ignore[index]
        problems.append("the bagged arm was not scored on the baseline arm's folds")
    return problems

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="fold-level worker processes; cannot move a number, only the wall clock",
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive the verdict from the stored summary instead of refitting",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    seed = int(args.seed)
    n_repeats = int(args.repeats)
    workers = int(args.workers)

    if args.check:
        payload = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        problems = check_summary(payload)
        if problems:
            print(f"CHECK FAILED: {args.summary}")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print(f"CHECK OK: {args.summary} verdict={payload['verdict']['decision']}")
        return 0

    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)

    splits, audit, repeats, note = build_shared_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    train_pool_rows = int(fixed_score.sum())
    train_pool_compounds = int(np.unique(np.asarray(groups)[fixed_score]).size)

    baseline_fold_rows, baseline_repeat_rows, baseline_prediction_rows, baseline_leak = (
        run_protocol(
            BASELINE_ARM,
            iter(splits),
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
        )
    )
    baseline_summary = summarize_repeats(baseline_repeat_rows)
    if BASELINE_ARM not in baseline_summary:
        raise ValueError(f"{BASELINE_ARM}: run_protocol wrote no rows under this arm name")
    baseline = {
        "arm": BASELINE_ARM,
        "meta": {
            "scored_rows": train_pool_rows,
            "compounds_scored": train_pool_compounds,
            "train_pool_rows": train_pool_rows,
            "train_pool_compounds": train_pool_compounds,
            "requested_repeats": n_repeats,
            "executed_repeats": repeats,
            "folds": len(splits),
            "note": note,
            "model": "XGBRegressor with XGB_PARAMS, frozen hyper-parameters",
            "objective": XGB_PARAMS["objective"],
            "splitter": "grouped by InChIKey (masked_splits)",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "seed": seed,
        },
        "audit": audit,
        "leak_reference": baseline_leak,
        "splits": splits,
        "fold_rows": baseline_fold_rows,
        "repeat_rows": baseline_repeat_rows,
        "prediction_rows": baseline_prediction_rows,
        "summary": baseline_summary[BASELINE_ARM],
    }

    lever = run_bagged_arm(
        LEVER_ARM,
        splits,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        n_bags=N_BAGS,
        seed=seed,
        workers=workers,
        train_pool_rows=train_pool_rows,
        train_pool_compounds=train_pool_compounds,
    )
    lever["splits"] = splits

    shuffled, permutation = shuffled_target(target, seed=seed + CONTROL_SEED_OFFSET)
    control = run_bagged_arm(
        CONTROL_ARM,
        splits,
        morgan=morgan,
        physical=physical,
        target=shuffled,
        temperatures=temperatures,
        groups=groups,
        n_bags=N_BAGS,
        seed=seed,
        workers=workers,
        train_pool_rows=train_pool_rows,
        train_pool_compounds=train_pool_compounds,
    )
    control["splits"] = splits

    dummy = run_dummy_mean_arm(DUMMY_MEAN_ARM, splits, target=target, groups=groups)
    control_floor = run_dummy_mean_arm(
        CONTROL_FLOOR_ARM, splits, target=shuffled, groups=groups
    )

    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    lever_blocks = [block for block in prereg_payload["levers"] if block.get("id") == LEVER_ID]
    if len(lever_blocks) != 1:
        raise ValueError(f"the pre-registration does not carry exactly one {LEVER_ID} block")
    lever_block = lever_blocks[0]
    if f"n_bags = {N_BAGS}" not in str(lever_block["model_change"]):
        raise ValueError("N_BAGS no longer matches the frozen model_change text")
    if f"seed * {BAG_SEED_MULTIPLIER}" not in str(lever_block["model_change"]):
        raise ValueError("the bag-seed rule no longer matches the frozen model_change text")
    prereg = {
        "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(PREREG_PATH),
        "status": prereg_payload["status"],
        "locked_at_utc": prereg_payload["locked_at_utc"],
        "lock_rule": prereg_payload["lock_rule"],
        "thresholds": {
            "mean_tolerance": MEAN_TOLERANCE,
            "std_shrink_required": STD_SHRINK_REQUIRED,
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
        "merge_rule": prereg_payload["merge_rule"],
        "forbidden": list(prereg_payload["forbidden"]),
    }

    inputs = {
        "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
        "coverage_table_sha256": canonical_text_sha256(COVERAGE_PATH),
        "feature_blocks": feature_report,
        "coverage_loader_dropped": dict(coverage_dropped),
        "rows_loaded": len(coverage_rows),
        "scored_rows": train_pool_rows,
        "scored_compounds": train_pool_compounds,
        "probe_script": portable_relative_path(PROBE_PATH, root=REPOSITORY_ROOT),
        "probe_script_sha256": canonical_text_sha256(PROBE_PATH),
        "workers": workers,
    }

    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        workers=workers,
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
            *baseline["fold_rows"],
            *lever["fold_rows"],
            *control["fold_rows"],
            *dummy["fold_rows"],
            *control_floor["fold_rows"],
        ],
        repeat_rows=[
            *baseline["repeat_rows"],
            *lever["repeat_rows"],
            *control["repeat_rows"],
            *dummy["repeat_rows"],
            *control_floor["repeat_rows"],
        ],
        prediction_rows=[
            *baseline["prediction_rows"],
            *lever["prediction_rows"],
            *control["prediction_rows"],
        ],
    )
    summary["inputs"] = inputs
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
        **outputs,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_lines = render_report(summary)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8", newline="\n")
    print("\n".join(report_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())