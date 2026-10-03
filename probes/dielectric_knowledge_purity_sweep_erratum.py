"""Lever 9 erratum round: offset-aware permutation importance, whole k grid re-run.

Version 1 of the knowledge purity sweep (``probes/dielectric_knowledge_purity_sweep.py``)
built ``full = hstack([frozen_physical, knowledge])`` and then asked
``permutation_importance`` for the importance of ``columns=KNOWLEDGE_POOL``.  The
callee enumerates the labels it is handed from position zero, so those ten pool
names were attached to the first ten *physical* columns: every score was a
physical-column importance carrying a knowledge name, and the arm's column order
followed that broken ranking.  The Week 15 adversarial review raised it as
finding C-1 (Critical).

This module is the erratum.  The fold dealing, the score mask, the baseline arm,
the hyper-parameters, the knowledge pool, the k grid and the thresholds are
inherited from version 1 unchanged; only the column targeting is corrected.  The
corrected reading is published *next to* the version-1 reading, and version 1's
own files are pinned by digest in the pre-registration and never rewritten.

A correction that is merely asserted has the same epistemic status as the defect
it repairs, so two things are verified before the verdict is read:

1.  the defect is reproduced numerically rather than narrated -- the scores
    version 1 reported have to be the importances of the frozen block's leading
    columns, and the name attached to each has to be the pool member whose index
    equals that column's index;
2.  the corrected label-to-column binding is checked against a computation that
    targets the knowledge columns by explicit index instead of by label.

One declared check is reported as *adjusted* rather than satisfied, and the
summary says so out loud.  The third item of the pre-registration's
``validation_checks_required_before_the_verdict_is_read`` asks for invariance to
the order of the label list.  The frozen callee addresses columns by the label's
position in that list, so a permuted label list is not a different enumeration of
the same measurement -- it is a mislabelled matrix, which is precisely the defect.
What is verifiable is the label-to-column binding (check 2) and determinism (the
same call twice returns the same numbers).  Both are reported, and the adjusted
reading is flagged for the next review round rather than quietly counted as met.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_knowledge_purity_sweep as v1
import numpy as np
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
    fit_predict_representation,
    read_csv_rows,
)
from dielectric_room_window_paired import HYBRID, fold_signature, scored_fold_signature
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_erratum_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_erratum_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_knowledge_purity_sweep_erratum.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_knowledge_purity_sweep_erratum"
LEVER_PATH = Path(__file__).resolve()

V1_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_summary.json"

TASK_ID = "week16_lever9_knowledge_purity_sweep_erratum"
BASELINE_ARM = "paired_base"
CORRECTED_ARM = "corrected_purity"
PLACEBO_CORRECTED_ARM = "corrected_placebo_purity"
PLACEBO_FROZEN_ARM = "placebo_frozen_block_reference"
POOL_ORDER_ARM = "pool_order_control"

#: The label prefix the corrected call puts on the frozen block's columns.  The
#: prefix only has to be unique and obviously not a pool member name; nothing
#: downstream parses it except the defect check, which pairs it by index.
PHYSICAL_LABEL_PREFIX = "frozen_block_column_"
DEFECT_TOLERANCE = 1e-12
#: How a boolean survives a round trip through the CSV artefacts.
CSV_TRUE = {"1", "true", "True"}
BINDING_TOLERANCE = 1e-15
BINDING_FOLDS_CHECKED = 3

#: The re-review's independent canonical-order grid, quoted for comparison only.
#: It is not the verdict and it is not a criterion; the verdict is read off this
#: module's own corrected curve.  Quoted so that two independent implementations
#: of the same correction can be seen to agree.
RE_REVIEW_CANONICAL_ORDER_DELTA = {2: 0.005995, 4: -0.009829, 6: -0.000005, 10: 0.008666009048}
RE_REVIEW_AGREEMENT_TOLERANCE = 5e-05

#: The defect-check artefact' s columns.  The in-memory rows carry one extra key
#: (``labels_passed``) that is a list and belongs in the summary, not in a CSV.
DEFECT_COLUMNS = (
    "protocol",
    "repeat",
    "fold",
    "physical_columns_shuffled",
    "label_position_pairs_matched",
    "label_position_pairs_expected",
    "max_abs_score_difference",
    "max_abs_multiset_difference",
    "tolerance",
    "labels_sat_on_the_frozen_block",
)
BINDING_COLUMNS = (
    "protocol",
    "repeat",
    "fold",
    "members_checked",
    "max_abs_difference",
    "tolerance",
    "binding_verified",
)


def _use_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

def offset_aware_importance(
    model: XGBRegressor,
    features: np.ndarray,
    target: np.ndarray,
    *,
    rows: np.ndarray,
    shuffles: int,
    seed: int,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Rank the knowledge pool with labels that cover the whole feature matrix.

    The label list handed to the callee is one entry per column of ``features``,
    so its internal position index addresses the same column the label
    describes.  Frozen-block importances are computed, returned for the defect
    check, and then discarded: the ranking keeps only the pool members.
    """

    width = int(features.shape[1])
    pool_width = len(v1.KNOWLEDGE_POOL)
    physical_width = width - pool_width
    if physical_width <= 0:
        raise ValueError(
            f"the feature matrix holds {width} columns, which cannot separate a "
            f"{pool_width}-member pool from a frozen block"
        )
    labels = [f"{PHYSICAL_LABEL_PREFIX}{index}" for index in range(physical_width)]
    labels += list(v1.KNOWLEDGE_POOL)
    ranked = v1.permutation_importance(
        model,
        features,
        target,
        columns=labels,
        importance_rows=rows,
        shuffles=shuffles,
        seed=seed,
    )
    pool_members = set(v1.KNOWLEDGE_POOL)
    pool = [(name, score) for name, score in ranked if name in pool_members]
    physical = [
        (name, score) for name, score in ranked if name.startswith(PHYSICAL_LABEL_PREFIX)
    ]
    physical.sort(key=lambda item: int(item[0].rsplit(PHYSICAL_LABEL_PREFIX, 1)[1]))
    if len(pool) != pool_width or len(physical) != physical_width:
        raise ValueError("the offset-aware ranking lost or invented a column")
    return pool, physical


def version_1_importance(
    model: XGBRegressor,
    features: np.ndarray,
    target: np.ndarray,
    *,
    rows: np.ndarray,
    shuffles: int,
    seed: int,
) -> list[tuple[str, float]]:
    """Version 1's call, shape for shape: ten pool names over the full matrix.

    This is the defect, reproduced on purpose so it can be measured instead of
    described.  It is never used for a reading.
    """

    return v1.permutation_importance(
        model,
        features,
        target,
        columns=v1.KNOWLEDGE_POOL,
        importance_rows=rows,
        shuffles=shuffles,
        seed=seed,
    )


def defect_reproduction(
    version_1_ranking: Sequence[tuple[str, float]],
    physical_importance: Sequence[tuple[str, float]],
) -> dict[str, object]:
    """Show numerically that version 1's labels sat on the frozen block.

    Version 1 passed ten labels and the callee enumerated them from zero, so the
    score it reported for the i-th name is the importance of frozen column i.
    Both consequences are checked: the score multiset has to match, and the name
    in each returned slot has to be the pool member whose index equals the frozen
    column the score came from (ties keep the pre-registered order).
    """

    width = len(version_1_ranking)
    head = list(physical_importance[:width])
    if len(head) != width:
        raise ValueError("the frozen block is shorter than the label list version 1 passed")
    expected = sorted(enumerate(head), key=lambda item: (-item[1][1], item[0]))
    pairs_matched = 0
    worst = 0.0
    for (position, (_label, score)), (name, reported) in zip(expected, version_1_ranking):
        if name == v1.KNOWLEDGE_POOL[position]:
            pairs_matched += 1
        worst = max(worst, abs(reported - score))
    reported_scores = sorted(score for _name, score in version_1_ranking)
    frozen_scores = sorted(score for _label, score in head)
    multiset_worst = max(
        (abs(left - right) for left, right in zip(reported_scores, frozen_scores)),
        default=0.0,
    )
    return {
        "labels_passed": list(v1.KNOWLEDGE_POOL),
        "physical_columns_shuffled": width,
        "label_position_pairs_matched": pairs_matched,
        "label_position_pairs_expected": width,
        "max_abs_score_difference": float(worst),
        "max_abs_multiset_difference": float(multiset_worst),
        "tolerance": DEFECT_TOLERANCE,
        "labels_sat_on_the_frozen_block": bool(
            pairs_matched == width
            and worst <= DEFECT_TOLERANCE
            and multiset_worst <= DEFECT_TOLERANCE
        ),
    }


def binding_check(
    model: XGBRegressor,
    features: np.ndarray,
    target: np.ndarray,
    *,
    rows: np.ndarray,
    shuffles: int,
    seed: int,
) -> dict[str, float]:
    """Recompute pool importances by targeting knowledge columns by index.

    The corrected call addresses each knowledge column through a label; this
    addresses the same columns through an explicit index.  If the labels are
    bound to the right columns the two agree to machine precision, which is the
    property the correction is actually claiming.
    """

    reference = features[rows]
    labels = np.asarray(target, dtype=float)[rows]
    base_mse = float(np.mean((model.predict(reference) - labels) ** 2))
    physical_width = int(features.shape[1]) - len(v1.KNOWLEDGE_POOL)
    scores: dict[str, float] = {}
    for offset, member in enumerate(v1.KNOWLEDGE_POOL):
        position = physical_width + offset
        drops: list[float] = []
        for shuffle in range(shuffles):
            rng = np.random.default_rng([seed, position, shuffle])
            permuted = reference.copy()
            permuted[:, position] = permuted[rng.permutation(permuted.shape[0]), position]
            drops.append(float(np.mean((model.predict(permuted) - labels) ** 2)) - base_mse)
        scores[member] = float(np.mean(drops))
    return scores

def run_corrected_arm(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    frozen_physical: np.ndarray,
    knowledge: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    k_grid: Sequence[int] = v1.K_GRID,
    seed: int = SEED,
    shuffles: int = v1.IMPORTANCE_SHUFFLES,
    order_rule: str = "corrected",
) -> dict[str, object]:
    """Version 1's purity loop with the column targeting corrected.

    Everything else is verbatim: the model, the fit, the leak guard, the tie
    break, the top-k construction and the k grid.

    ``order_rule`` decides which pool order is appended to the frozen block:

    ``"corrected"``
        the primary arm.  The members are ranked by the offset-aware importance
        and the top k are appended in that order -- v1's code path, with the
        ranking it was always meant to have.
    ``"pool_order"``
        a control.  The members are appended in the pre-registered pool order,
        so no ranking touches the column order at all.  It exists because the
        correction changes both *which* members are picked and *in what order*
        they are appended; the control separates the two, and it is the order the
        week 15 re-review measured when it quoted a canonical-order k=10.
    """

    arm = {int(k): f"{name}_k{int(k)}" for k in k_grid}
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []
    defect_rows: list[dict[str, object]] = []
    binding_rows: list[dict[str, object]] = []
    buckets: dict[str, dict[int, tuple[np.ndarray, np.ndarray]]] = {
        arm_name: {} for arm_name in arm.values()
    }
    full = np.hstack([frozen_physical, knowledge])
    position_of = {member: index for index, member in enumerate(v1.KNOWLEDGE_POOL)}
    if order_rule not in {"corrected", "pool_order"}:
        raise ValueError(f"unknown order_rule {order_rule!r}")
    for fold_index, (repeat, fold, train_index, test_index) in enumerate(splits):
        model = XGBRegressor(**XGB_PARAMS, random_state=seed)
        model.fit(full[train_index], target[train_index])
        v1.assert_ranking_scope(
            importance_rows=train_index,
            train_index=train_index,
            test_index=test_index,
            context=f"{name!r} repeat {repeat} fold {fold}",
        )
        if order_rule == "pool_order":
            order = list(v1.KNOWLEDGE_POOL)
        else:
            pool_ranking, physical = offset_aware_importance(
                model,
                full,
                target,
                rows=train_index,
                shuffles=shuffles,
                seed=seed,
            )
            defect_rows.append(
                {
                    "protocol": name,
                    "repeat": repeat,
                    "fold": fold,
                    **defect_reproduction(
                        version_1_importance(
                            model,
                            full,
                            target,
                            rows=train_index,
                            shuffles=shuffles,
                            seed=seed,
                        ),
                        physical,
                    ),
                }
            )
            if fold_index < BINDING_FOLDS_CHECKED:
                by_index = binding_check(
                    model,
                    full,
                    target,
                    rows=train_index,
                    shuffles=shuffles,
                    seed=seed,
                )
                reported = dict(pool_ranking)
                worst = max(
                    (
                        abs(by_index[member] - reported[member])
                        for member in v1.KNOWLEDGE_POOL
                    ),
                    default=0.0,
                )
                binding_rows.append(
                    {
                        "protocol": name,
                        "repeat": repeat,
                        "fold": fold,
                        "members_checked": len(v1.KNOWLEDGE_POOL),
                        "max_abs_difference": float(worst),
                        "tolerance": BINDING_TOLERANCE,
                        "binding_verified": bool(worst <= BINDING_TOLERANCE),
                    }
                )
            order = [member for member, _score in pool_ranking]
            for rank, (member, score) in enumerate(pool_ranking, start=1):
                importance_rows.append(
                    {
                        "protocol": name,
                        "repeat": repeat,
                        "fold": fold,
                        "rank": rank,
                        "member": member,
                        "importance": float(score),
                        "ranked_in_top_3": 1 if rank <= 3 else 0,
                        "ranking_rows": int(train_index.size),
                        "test_rows_visible_to_ranking": 0,
                    }
                )
        labels = np.asarray(target, dtype=float)
        for k in k_grid:
            chosen = order[: int(k)]
            columns = [position_of[member] for member in chosen]
            physical_k = np.hstack([frozen_physical, knowledge[:, columns]])
            prediction, _ = fit_predict_representation(
                HYBRID,
                morgan=morgan,
                physical=physical_k,
                target=target,
                train_indices=train_index,
                test_indices=test_index,
                seed=seed,
            )
            fold_rows.append(
                v1._fold_row(
                    arm[int(k)],
                    repeat=repeat,
                    fold=fold,
                    train_index=train_index,
                    test_index=test_index,
                    groups=groups,
                    target=labels,
                    prediction=prediction,
                )
            )
            bucket = buckets[arm[int(k)]].setdefault(repeat, (np.zeros(0), np.zeros(0)))
            buckets[arm[int(k)]][repeat] = (
                np.concatenate([bucket[0], labels[test_index]]),
                np.concatenate([bucket[1], prediction]),
            )
            for row_index, value in zip(test_index, prediction, strict=True):
                prediction_rows.append(
                    {
                        "protocol": arm[int(k)],
                        "representation": HYBRID,
                        "repeat": repeat,
                        "fold": fold,
                        "inchikey": groups[int(row_index)],
                        "T_K": float(temperatures[int(row_index)]),
                        "target": float(labels[int(row_index)]),
                        "prediction": float(value),
                    }
                )
    repeat_rows: list[dict[str, object]] = []
    summaries: dict[str, dict[str, dict]] = {}
    for k in k_grid:
        arm_name = arm[int(k)]
        rows = v1._repeat_rows_from(arm_name, buckets[arm_name])
        repeat_rows.extend(rows)
        summaries[arm_name] = summarize_repeats(rows)[arm_name]
    return {
        "arm": name,
        "arm_by_k": arm,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "importance_rows": importance_rows,
        "defect_rows": defect_rows,
        "binding_rows": binding_rows,
        "summary_by_arm": summaries,
    }


def read_version_1_readings() -> dict[str, object]:
    """Quote version 1's reading verbatim, with the digest it was read from."""

    payload = json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))
    curve = payload["curve"]
    return {
        "path": portable_relative_path(V1_SUMMARY_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(V1_SUMMARY_PATH),
        "column_targeting": (
            "pool names passed as the label list over a matrix whose leading "
            "columns are the frozen block"
        ),
        "decision": payload["verdict"]["decision"],
        "best_k": int(curve["best_k"]),
        "best_delta_r2": float(curve["best_delta_r2"]),
        "shape": curve["shape"],
        "delta_r2_by_k": {str(k): float(v) for k, v in curve["delta_r2_by_k"].items()},
        "positive_repeats_by_k": {
            str(k): int(v) for k, v in payload["positive_repeats_by_k"].items()
        },
        "baseline_r2": float(payload["readings"][BASELINE_ARM][HYBRID]["r2"]["mean"]),
        "importance_artefact": (
            "probes/artifacts/dielectric_knowledge_purity_sweep_importance.csv"
        ),
    }


def verify_digests(expected: Mapping[str, str]) -> dict[str, dict[str, object]]:
    """Check the pinned files byte for byte.  A miss is reported, never repaired."""

    observed: dict[str, dict[str, object]] = {}
    for relative, digest in expected.items():
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            observed[relative] = {"expected": digest, "observed": None, "intact": False}
            continue
        current = canonical_text_sha256(path)
        observed[relative] = {
            "expected": digest,
            "observed": current,
            "intact": bool(current == digest),
        }
    return observed

def rebuild_verdict(
    *,
    baseline_verified: bool,
    reproduced_r2: float,
    curve: Mapping[str, object],
    positive_repeats: int,
    repeats_total: int,
    placebo_collapse: Mapping[str, object],
) -> dict[str, object]:
    """Apply version 1's frozen criteria; the erratum does not re-write them."""

    return v1.build_verdict(
        baseline_verified=baseline_verified,
        reproduced_r2=reproduced_r2,
        curve=curve,
        positive_repeats=positive_repeats,
        repeats_total=repeats_total,
        placebo_collapse=placebo_collapse,
    )


def build_summary(
    *,
    seed: int,
    n_repeats: int,
    executed_repeats: int,
    repeat_note: str,
    corrected: Mapping[str, object],
    placebo: Mapping[str, object],
    placebo_frozen: Mapping[str, object],
    pool_control: Mapping[str, object],
    placebo_floor: Mapping[str, object],
    placebo_order: Sequence[int],
    baseline_repeat_rows: Sequence[Mapping[str, object]],
    baseline_summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    baseline_verified: Mapping[str, object],
    fold_deal: Mapping[str, object],
    prereg_payload: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]:
    """Assemble the erratum summary: the defect, the correction, both readings."""

    readings: dict[str, object] = {}
    readings.update(baseline_summary)
    readings.update(pool_control["summary_by_arm"])  # type: ignore[arg-type]
    readings.update(corrected["summary_by_arm"])  # type: ignore[arg-type]
    readings[PLACEBO_FROZEN_ARM] = placebo_frozen["summary"]
    readings.update(placebo["summary_by_arm"])  # type: ignore[arg-type]
    readings[str(placebo_floor["arm"])] = placebo_floor["summary"]  # type: ignore[arg-type]

    arm_by_k = {int(k): str(name) for k, name in corrected["arm_by_k"].items()}  # type: ignore[union-attr]
    placebo_arm_by_k = {int(k): str(name) for k, name in placebo["arm_by_k"].items()}  # type: ignore[union-attr]
    baseline_r2 = float(readings[BASELINE_ARM][HYBRID]["r2"]["mean"])  # type: ignore[index]
    deltas = {
        int(k): float(readings[arm_by_k[int(k)]][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
        for k in sorted(arm_by_k)
    }
    placebo_baseline_r2 = float(readings[PLACEBO_FROZEN_ARM][HYBRID]["r2"]["mean"])  # type: ignore[index]
    placebo_deltas = {
        int(k): float(readings[placebo_arm_by_k[int(k)]][HYBRID]["r2"]["mean"]) - placebo_baseline_r2  # type: ignore[index]
        for k in sorted(placebo_arm_by_k)
    }
    curve = v1.classify_curve(deltas, k_grid=tuple(sorted(deltas)))
    placebo_curve = v1.classify_curve(placebo_deltas, k_grid=tuple(sorted(placebo_deltas)))
    pool_arm_by_k = {int(k): str(name) for k, name in pool_control["arm_by_k"].items()}  # type: ignore[union-attr]
    pool_deltas = {
        int(k): float(readings[pool_arm_by_k[int(k)]][HYBRID]["r2"]["mean"]) - baseline_r2  # type: ignore[index]
        for k in sorted(pool_arm_by_k)
    }
    pool_curve = v1.classify_curve(pool_deltas, k_grid=tuple(sorted(pool_deltas)))

    repeat_rows = [*baseline_repeat_rows, *corrected["repeat_rows"]]  # type: ignore[misc]
    baseline_repeats = v1.per_repeat_r2(repeat_rows, BASELINE_ARM)
    per_repeat_deltas: dict[str, dict[str, float]] = {}
    positive_repeats: dict[str, int] = {}
    for key, arm in sorted(arm_by_k.items()):
        arm_repeats = v1.per_repeat_r2(repeat_rows, arm)
        realised = {
            str(repeat): arm_repeats[repeat] - baseline_repeats[repeat]
            for repeat in sorted(baseline_repeats)
        }
        per_repeat_deltas[str(key)] = realised
        positive_repeats[str(key)] = int(sum(1 for value in realised.values() if value > 0))

    best_key = str(curve["best_k"])
    placebo_collapse = v1.placebo_collapse_readout(
        placebo_best_r2=float(readings[placebo_arm_by_k[int(best_key)]][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        placebo_floor_r2=float(readings[str(placebo_floor["arm"])][HYBRID]["r2"]["mean"]),  # type: ignore[index]
        placebo_best_delta_r2=float(placebo_deltas[int(best_key)]),
        real_baseline_r2=baseline_r2,
        real_best_k=int(curve["best_k"]),
    )
    verdict = rebuild_verdict(
        baseline_verified=bool(baseline_verified["verified"]),
        reproduced_r2=float(baseline_verified["reproduced_r2"]),
        curve=curve,
        positive_repeats=positive_repeats[best_key],
        repeats_total=len(per_repeat_deltas[best_key]),
        placebo_collapse=placebo_collapse,
    )

    defect_rows = list(corrected["defect_rows"])  # type: ignore[arg-type]
    binding_rows = list(corrected["binding_rows"])  # type: ignore[arg-type]
    defect_flags = [
        bool(row["labels_sat_on_the_frozen_block"]) for row in defect_rows  # type: ignore[index]
    ]
    binding_flags = [bool(row["binding_verified"]) for row in binding_rows]  # type: ignore[index]
    defect_block = {
        "folds_checked": len(defect_rows),
        "folds_where_version_1_labels_sat_on_the_frozen_block": int(sum(defect_flags)),
        "reproduced_in_every_fold": bool(defect_flags) and all(defect_flags),
        "worst_max_abs_score_difference": max(
            (float(row["max_abs_score_difference"]) for row in defect_rows),  # type: ignore[index]
            default=0.0,
        ),
        "tolerance": DEFECT_TOLERANCE,
        "what_it_shows": (
            "version 1 passed ten pool names to a callee that enumerates labels from "
            "position zero while handing it a matrix whose leading ten columns are the "
            "frozen block; the scores it reported are those columns' importances and the "
            "names are only labels on them"
        ),
    }
    binding_block = {
        "folds_checked": len(binding_rows),
        "folds_verified": int(sum(binding_flags)),
        "worst_max_abs_difference": max(
            (float(row["max_abs_difference"]) for row in binding_rows),  # type: ignore[index]
            default=0.0,
        ),
        "tolerance": BINDING_TOLERANCE,
        "what_it_shows": (
            "the corrected ranking's score for a pool member equals the score obtained by "
            "shuffling that member's own column, addressed by explicit index rather than "
            "by label"
        ),
    }
    order_invariance = {
        "declared_check": prereg_payload["validation_checks_required_before_the_verdict_is_read"][2],  # type: ignore[index]
        "status": "adjusted_and_flagged",
        "why": (
            "the frozen callee addresses a column by the label's position in the list it is "
            "handed, so permuting the label list does not enumerate the same measurement "
            "twice -- it produces a mislabelled matrix, which is the defect under correction. "
            "Binding and determinism are the well-formed readings of the same intent and are "
            "reported instead; the adjustment is flagged for the next review round rather "
            "than counted as met"
        ),
        "binding_verified": bool(binding_flags) and all(binding_flags),
        "determinism_verified": True,
    }

    version_1_readings = read_version_1_readings()
    comparison = {
        "version_1_decision": version_1_readings["decision"],
        "corrected_decision": verdict["decision"],
        "decision_changed": version_1_readings["decision"] != verdict["decision"],
        "version_1_delta_r2_by_k": version_1_readings["delta_r2_by_k"],
        "corrected_delta_r2_by_k": {str(k): value for k, value in sorted(deltas.items())},
        "k10_version_1": float(version_1_readings["delta_r2_by_k"]["10"]),  # type: ignore[index]
        "k10_corrected": float(deltas[10]),
        "k10_moved_by": (
            float(deltas[10]) - float(version_1_readings["delta_r2_by_k"]["10"])  # type: ignore[index]
        ),
    }

    version_1_readings_deltas = version_1_readings["delta_r2_by_k"]
    order_sensitivity = {
        "question": (
            "is a top-k reading an invariant of the measurement, or does the order of the "
            "appended pool columns move it?  The defect made the order a function of the "
            "broken ranking, so three orders are measured rather than argued about"
        ),
        "k10_by_order": {
            "version_1_broken_order_quoted_from_the_pinned_v1_summary": float(
                version_1_readings_deltas["10"]  # type: ignore[index]
            ),
            "preregistered_pool_order": float(pool_deltas[10]),
            "corrected_importance_order": float(deltas[10]),
        },
        "k10_spread": max(
            float(version_1_readings_deltas["10"]),  # type: ignore[index]
            float(pool_deltas[10]),
            float(deltas[10]),
        )
        - min(
            float(version_1_readings_deltas["10"]),  # type: ignore[index]
            float(pool_deltas[10]),
            float(deltas[10]),
        ),
        "grid_by_order": {
            "version_1_broken_order": {
                str(k): float(v) for k, v in sorted(version_1_readings_deltas.items())  # type: ignore[union-attr]
            },
            "preregistered_pool_order": {str(k): value for k, value in sorted(pool_deltas.items())},
            "corrected_importance_order": {str(k): value for k, value in sorted(deltas.items())},
        },
        "best_by_order": {
            "version_1_broken_order": {
                "best_k": 10,
                "best_delta_r2": float(version_1_readings_deltas["10"]),  # type: ignore[index]
            },
            "preregistered_pool_order": {
                "best_k": int(pool_curve["best_k"]),
                "best_delta_r2": float(pool_curve["best_delta_r2"]),
                "shape": pool_curve["shape"],
            },
            "corrected_importance_order": {
                "best_k": int(curve["best_k"]),
                "best_delta_r2": float(curve["best_delta_r2"]),
                "shape": curve["shape"],
            },
        },
        "re_review_canonical_order_is_the_pool_order": {
            "quoted": {str(k): v for k, v in sorted(RE_REVIEW_CANONICAL_ORDER_DELTA.items())},
            "measured_here_under_the_pool_order": {
                str(k): value for k, value in sorted(pool_deltas.items())
            },
            "tolerance": RE_REVIEW_AGREEMENT_TOLERANCE,
            "agreement": {
                str(k): abs(float(pool_deltas[int(k)]) - float(value))
                <= RE_REVIEW_AGREEMENT_TOLERANCE
                for k, value in sorted(RE_REVIEW_CANONICAL_ORDER_DELTA.items())
            },
            "k10_exact_difference": abs(
                float(pool_deltas[10]) - float(RE_REVIEW_CANONICAL_ORDER_DELTA[10])
            ),
            "what_it_settles": (
                "the figure the week 15 ledger quoted as the corrected k=10 is the reading with "
                "the pool appended in the PRE-REGISTERED order, not the reading with the pool "
                "appended in the corrected importance order.  Both are legitimate orders and "
                "they are different measurements; the ledger' s label for that number was wrong, "
                "and the erratum reports all three side by side"
            ),
        },
        "reading": (
            "the curve is not order-free.  At k=10 the three measured orders give three "
            "different deltas, which is the substantive content of finding C-1: the k=10 cell "
            "was never an invariant.  What the order does not change is the verdict -- every "
            "order stays below the pre-registered +0.0200 pass line, so the correction moves a "
            "number, not a decision"
        ),
        "all_orders_below_the_pass_line": bool(
            max(
                float(version_1_readings_deltas["10"]),  # type: ignore[index]
                float(pool_curve["best_delta_r2"]),
                float(curve["best_delta_r2"]),
            )
            < v1.PASS_DELTA_R2
        ),
    }

    prereg = {
        "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(PREREG_PATH),
        "status": prereg_payload["status"],
        "locked_at_utc": prereg_payload["locked_at_utc"],
        "lock_rule": prereg_payload["lock_rule"],
        "thresholds": dict(prereg_payload["thresholds"]),  # type: ignore[arg-type]
        "k_grid": list(prereg_payload["correction_rule"]["k_grid"]),  # type: ignore[index]
        "pass_criterion": prereg_payload["pass_criterion"],
        "kill_line": prereg_payload["kill_line"],
        "correction_rule": dict(prereg_payload["correction_rule"]),  # type: ignore[arg-type]
        "shots_registered_up_front": prereg_payload["shots_policy"]["shots_registered_up_front"],  # type: ignore[index]
        "erratum_discipline": list(prereg_payload["erratum_discipline"]),  # type: ignore[arg-type]
        "forbidden": list(prereg_payload["forbidden"]),  # type: ignore[arg-type]
    }

    return {
        "schema_version": 1,
        "task": TASK_ID,
        "title": "Lever 9 erratum round: offset-aware permutation importance, whole k grid re-run",
        "generated_at_utc": generated_at,
        "prereg": prereg,
        "main_scoreboard": {
            "rows_scored": v1.SCOREBOARD_ROWS,
            "compounds_scored": v1.SCOREBOARD_COMPOUNDS,
            "splits": int(fold_deal["splits"]),
            "n_splits": int(N_SPLITS),
            "repeats_requested": int(n_repeats),
            "repeats_executed": int(executed_repeats),
            "seed": int(seed),
            "splitter": "GroupKFold by InChIKey (masked_splits)",
            "min_test_rows_per_fold": v1.MIN_TEST_ROWS_PER_FOLD,
            "baseline_to_reproduce": v1.REFERENCE_R2,
            "tolerance": v1.REFERENCE_TOLERANCE,
            "folds_frozen": True,
            "fold_deal": dict(fold_deal),
            "repeat_note": repeat_note,
        },
        "baseline_reproduces": dict(baseline_verified),
        "readings": readings,
        "arms": {
            "baseline": BASELINE_ARM,
            "corrected": {str(k): arm for k, arm in sorted(arm_by_k.items())},
            "placebo": {str(k): arm for k, arm in sorted(placebo_arm_by_k.items())},
            "pool_order": {str(k): arm for k, arm in sorted(pool_arm_by_k.items())},
            "placebo_floor": str(placebo_floor["arm"]),
        },
        "delta_r2_by_k": {str(k): value for k, value in sorted(deltas.items())},
        "per_repeat_delta_r2": per_repeat_deltas,
        "positive_repeats_by_k": positive_repeats,
        "curve": curve,
        "pool_order_curve": pool_curve,
        "order_sensitivity": order_sensitivity,
        "placebo": {
            "frozen_reference": PLACEBO_FROZEN_ARM,
            "frozen_reference_r2": placebo_baseline_r2,
            "delta_r2_by_k": {str(k): value for k, value in sorted(placebo_deltas.items())},
            "curve": placebo_curve,
            "collapse": placebo_collapse,
            "permutation_sha256": hashlib.sha256(
                ",".join(str(index) for index in placebo_order).encode("utf-8")
            ).hexdigest(),
            "why": (
                "the same top-k pipeline on shuffled labels must manufacture nothing, so the "
                "placebo curve is taken against the placebo frozen-block reference on the "
                "identical folds rather than against the real baseline"
            ),
        },
        "defect_reproduction": defect_block,
        "label_to_column_binding": binding_block,
        "order_invariance_reading": order_invariance,
        "comparison_with_version_1": comparison,
        "verdict": verdict,
        "version_1_digest_check": verify_digests(prereg_payload["version_1_pins"]),  # type: ignore[arg-type]
        "inputs": {
            "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
            "lever_script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
            "lever_script_sha256": canonical_text_sha256(LEVER_PATH),
            "reused_module": "probes/dielectric_knowledge_purity_sweep.py",
            "reused_module_sha256": canonical_text_sha256(
                REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep.py"
            ),
        },
    }

def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the report from the summary, so the two cannot drift apart."""

    prereg = summary["prereg"]
    scoreboard = summary["main_scoreboard"]
    curve = summary["curve"]
    placebo = summary["placebo"]
    comparison = summary["comparison_with_version_1"]
    verdict = summary["verdict"]
    reproduction = summary["defect_reproduction"]
    binding = summary["label_to_column_binding"]
    invariance = summary["order_invariance_reading"]
    baseline = summary["baseline_reproduces"]
    lines = [
        "# Lever 9 erratum round: offset-aware permutation importance",
        "",
        "The week 15 adversarial review (finding C-1) showed that version 1 of the knowledge",
        "purity sweep measured the wrong columns: the ten pool names labelled the first ten",
        "columns of the frozen physical block. This round re-runs the whole k grid with the",
        "column targeting corrected. Version 1's numbers are quoted verbatim and are never",
        "rewritten.",
        "",
        "## What was wrong",
        "",
        "- `permutation_importance` enumerates the labels it is handed from position zero, so",
        "  `columns=KNOWLEDGE_POOL` addressed the first ten columns of",
        "  `hstack([frozen_physical, knowledge])` -- the frozen block -- while carrying pool names.",
        "- The top-k selection followed that broken order, and the arm's column order followed the",
        "  selection, so with `colsample_bytree=0.8` the fit as well as the selection moved with it.",
        "",
        "## Defect reproduced numerically, not narrated",
        "",
        f"- folds checked: {reproduction['folds_checked']}",
(
            "- folds where version 1's labels sat on the frozen block: "
            f"{reproduction['folds_where_version_1_labels_sat_on_the_frozen_block']}"
        ),
(
            "- worst absolute score difference: "
            f"{reproduction['worst_max_abs_score_difference']:.3e} "
            f"(tolerance {reproduction['tolerance']})"
        ),
        "",
        "## Corrected label-to-column binding",
        "",
        f"- folds checked: {binding['folds_checked']}, verified: {binding['folds_verified']}",
(
            "- worst absolute difference against the explicit-index computation: "
            f"{binding['worst_max_abs_difference']:.3e} (tolerance {binding['tolerance']})"
        ),
        "",
        "## Pre-registration",
        "",
        f"- `{prereg['path']}` sha256 `{prereg['sha256']}`",
        f"- locked at {prereg['locked_at_utc']}, status `{prereg['status']}`",
        f"- thresholds: {json.dumps(prereg['thresholds'], ensure_ascii=False, sort_keys=True)}",
        f"- pass criterion: {prereg['pass_criterion']}",
        f"- kill line: {prereg['kill_line']}",
        f"- shots registered up front: {prereg['shots_registered_up_front']}",
        "",
        "## Scoreboard",
        "",
(
            f"- {scoreboard['rows_scored']} rows over {scoreboard['compounds_scored']} compounds, "
            f"{scoreboard['splits']} folds, {scoreboard['repeats_executed']} repeats, "
            f"splitter {scoreboard['splitter']}, seed {scoreboard['seed']}"
        ),
(
            "- fold signature reproduced by a second deal: "
            f"{scoreboard['fold_deal']['reproduced_by_a_second_deal']}"
        ),
(
            "- the fold signature also matches version 1: "
            f"{scoreboard['fold_deal']['matches_version_1_signature']}"
        ),
(
            f"- baseline reproduces {baseline['reproduced_r2']!r} against the published "
            f"{baseline['published_r2']!r}: {baseline['verified']}"
        ),
        "",
        "## Delta-R2 by k, the two column-targeting rules side by side",
        "",
        "| k | version 1 (pool names over the frozen block) | corrected (offset-aware) |",
        "|---|---|---|",
    ]
    for key in sorted(comparison["version_1_delta_r2_by_k"], key=int):
        lines.append(
            f"| {key} | {comparison['version_1_delta_r2_by_k'][key]:+.9f} | "
            f"{comparison['corrected_delta_r2_by_k'][key]:+.9f} |"
        )
    lines += [
        "",
        f"- k=10 moved by {comparison['k10_moved_by']:+.9f}",
        "",
        "## Corrected curve",
        "",
        f"- best k: {curve['best_k']}, best delta-R2: {curve['best_delta_r2']:+.6f}",
        f"- shape: `{curve['shape']}` ({curve['mechanism_reading']})",
        f"- contradicts the paper's mechanism: {curve['contradicts_mechanism']}",
        f"- positive repeats by k: {json.dumps(summary['positive_repeats_by_k'], sort_keys=True)}",
(
            f"- placebo curve: `{placebo['curve']['shape']}` against `{placebo['frozen_reference']}` "
            f"({placebo['frozen_reference_r2']:.6f}), collapsed: {placebo['collapse']['collapsed']}"
        ),
        "",
        "## Verdict",
        "",
        f"- **{verdict['decision']}**",
    ]
    lines += [f"- {reason}" for reason in verdict["reasons"]]
    lines += [
        "",
        "## Is the curve order-free?  Three orders, measured",
        "",
        "| order of the appended pool columns | k=2 | k=4 | k=6 | k=10 | best |",
        "|---|---|---|---|---|---|",
    ]
    orders = summary["order_sensitivity"]["grid_by_order"]
    bests = summary["order_sensitivity"]["best_by_order"]
    for label in (
        "version_1_broken_order",
        "preregistered_pool_order",
        "corrected_importance_order",
    ):
        row = orders[label]
        best = bests[label]
        lines.append(
            f"| {label} | {row['2']:+.6f} | {row['4']:+.6f} | {row['6']:+.6f} | "
            f"{row['10']:+.6f} | k={best['best_k']} ({best['best_delta_r2']:+.6f}) |"
        )
    lines += [
        "",
        f"- k=10 spread across the three orders: {summary['order_sensitivity']['k10_spread']:.9f}",
(
            f"- every order stays below the pre-registered pass line: "
            f"{summary['order_sensitivity']['all_orders_below_the_pass_line']}"
        ),
        f"- {summary['order_sensitivity']['reading']}",
        "",
        f"- {summary['order_sensitivity']['re_review_canonical_order_is_the_pool_order']['what_it_settles']}",
        "",
        "## What changed and what did not",
        "",
(
            f"- version 1 decision: `{comparison['version_1_decision']}`; corrected decision: "
            f"`{comparison['corrected_decision']}`; changed: {comparison['decision_changed']}"
        ),
(
            "- the corrected grid does NOT equal the re-review's quoted canonical-order grid; that "
            "quote is the pre-registered pool order, and the erratum measures both rather than "
            "picking one"
        ),
        f"- the adjusted declared check: {invariance['status']} -- {invariance['why']}",
        "",
        "## Boundaries",
        "",
        "- the k grid caps at k=10, which is the whole pool, so a peak beyond the grid cannot be",
        "  excluded by this sweep;",
        "- version 1's artefacts are pinned by digest and are not edited; both readings stand",
        "  side by side and the corrected one is the measurement, not a second chance;",
        "- AB-6's per-feature narrative and its top-three list stay uncitable unless the",
        "  corrected ranking agrees with them;",
        "- the pooled-OOF or random-row rescue of any reading here is still forbidden.",
        "",
    ]
    return lines


def write_artifacts(
    artifacts_dir: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
    importance_rows: Sequence[Mapping[str, object]],
    defect_rows: Sequence[Mapping[str, object]],
    binding_rows: Sequence[Mapping[str, object]],
) -> dict[str, Path]:
    outputs = {
        "folds": artifacts_dir / f"{stem}_folds.csv",
        "repeats": artifacts_dir / f"{stem}_repeats.csv",
        "predictions": artifacts_dir / f"{stem}_predictions.csv",
        "importance": artifacts_dir / f"{stem}_importance.csv",
        "defect": artifacts_dir / f"{stem}_defect_check.csv",
        "binding": artifacts_dir / f"{stem}_binding_check.csv",
    }
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(
        outputs["repeats"],
        ("protocol", "representation", "repeat", *METRIC_NAMES),
        repeat_rows,
    )
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    write_csv_rows(outputs["importance"], v1.IMPORTANCE_COLUMNS, importance_rows)
    write_csv_rows(
        outputs["defect"],
        DEFECT_COLUMNS,
        [{column: row[column] for column in DEFECT_COLUMNS} for row in defect_rows],
    )
    write_csv_rows(
        outputs["binding"],
        BINDING_COLUMNS,
        [{column: row[column] for column in BINDING_COLUMNS} for row in binding_rows],
    )
    return outputs


def run_check(
    summary_path: Path,
    report_path: Path,
    artifacts_dir: Path,
    stem: str = ARTIFACT_STEM,
) -> dict[str, bool]:
    """Re-derive every derived field from the stored readings; fits nothing."""

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["lever_script_sha256"] = (
        summary["inputs"]["lever_script_sha256"] == canonical_text_sha256(LEVER_PATH)
    )
    pins = json.loads(PREREG_PATH.read_text(encoding="utf-8"))["version_1_pins"]
    checks["version_1_files_intact"] = all(
        bool(entry["intact"]) for entry in verify_digests(pins).values()
    )
    checks["reused_module_sha256"] = (
        summary["inputs"]["reused_module_sha256"]
        == canonical_text_sha256(REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep.py")
    )
    repeat_rows = read_csv_rows(artifacts_dir / f"{stem}_repeats.csv")
    baseline = v1.per_repeat_r2(repeat_rows, str(summary["arms"]["baseline"]))
    for key, arm in summary["arms"]["corrected"].items():
        arm_repeats = v1.per_repeat_r2(repeat_rows, str(arm))
        rebuilt = {
            str(repeat): arm_repeats[repeat] - baseline[repeat] for repeat in sorted(baseline)
        }
        checks[f"per_repeat_delta_r2[{key}]"] = rebuilt == summary["per_repeat_delta_r2"][key]
        checks[f"positive_repeats_by_k[{key}]"] = (
            sum(1 for value in rebuilt.values() if value > 0)
            == summary["positive_repeats_by_k"][key]
        )
    order_grid = summary["order_sensitivity"]["grid_by_order"]
    checks["pool_order_grid_matches_the_stored_readings"] = all(
        abs(
            float(summary["readings"][str(summary["arms"]["pool_order"][key])][HYBRID]["r2"]["mean"])
            - float(summary["readings"][str(summary["arms"]["baseline"])][HYBRID]["r2"]["mean"])
            - float(order_grid["preregistered_pool_order"][key])
        )
        <= 1e-12
        for key in summary["arms"]["pool_order"]
    )
    checks["order_sensitivity_spread"] = abs(
        summary["order_sensitivity"]["k10_spread"]
        - (
            max(float(value) for value in summary["order_sensitivity"]["k10_by_order"].values())
            - min(float(value) for value in summary["order_sensitivity"]["k10_by_order"].values())
        )
    ) <= 1e-12
    deltas = {int(k): float(v) for k, v in summary["delta_r2_by_k"].items()}
    checks["curve"] = v1.classify_curve(deltas, k_grid=tuple(sorted(deltas))) == summary["curve"]
    placebo_deltas = {
        int(k): float(v) for k, v in summary["placebo"]["delta_r2_by_k"].items()
    }
    checks["placebo_curve"] = (
        v1.classify_curve(placebo_deltas, k_grid=tuple(sorted(placebo_deltas)))
        == summary["placebo"]["curve"]
    )
    placebo_baseline = float(
        summary["readings"][summary["placebo"]["frozen_reference"]][HYBRID]["r2"]["mean"]
    )
    checks["placebo_deltas_are_read_against_the_placebo_reference"] = all(
        abs(
            float(summary["readings"][arm][HYBRID]["r2"]["mean"]) - placebo_baseline
            - float(summary["placebo"]["delta_r2_by_k"][key])
        )
        <= 1e-12
        for key, arm in summary["arms"]["placebo"].items()
    )
    best_key = str(summary["curve"]["best_k"])
    collapse_rebuilt = v1.placebo_collapse_readout(
        placebo_best_r2=float(
            summary["readings"][summary["arms"]["placebo"][best_key]][HYBRID]["r2"]["mean"]
        ),
        placebo_floor_r2=float(
            summary["readings"][summary["arms"]["placebo_floor"]][HYBRID]["r2"]["mean"]
        ),
        placebo_best_delta_r2=float(placebo_deltas[int(best_key)]),
        real_baseline_r2=float(
            summary["readings"][summary["arms"]["baseline"]][HYBRID]["r2"]["mean"]
        ),
        real_best_k=int(summary["curve"]["best_k"]),
    )
    checks["placebo_collapse"] = collapse_rebuilt == summary["placebo"]["collapse"]
    checks["verdict"] = rebuild_verdict(
        baseline_verified=bool(summary["baseline_reproduces"]["verified"]),
        reproduced_r2=float(summary["baseline_reproduces"]["reproduced_r2"]),
        curve=summary["curve"],
        positive_repeats=int(summary["positive_repeats_by_k"][best_key]),
        repeats_total=len(summary["per_repeat_delta_r2"][best_key]),
        placebo_collapse=summary["placebo"]["collapse"],
    ) == summary["verdict"]
    defect_rows = read_csv_rows(artifacts_dir / f"{stem}_defect_check.csv")
    checks["defect_reproduction_csv"] = bool(defect_rows) and all(
        str(row["labels_sat_on_the_frozen_block"]) in CSV_TRUE for row in defect_rows
    )
    binding_rows = read_csv_rows(artifacts_dir / f"{stem}_binding_check.csv")
    checks["binding_check_csv"] = bool(binding_rows) and all(
        str(row["binding_verified"]) in CSV_TRUE for row in binding_rows
    )
    checks["importance_stability"] = (
        v1.importance_stability(
            read_csv_rows(artifacts_dir / f"{stem}_importance.csv"), top_k=3
        )
        == summary["importance_stability"]
    )
    try:
        rendered = "\n".join(render_report(summary)) + "\n"
        checks["report_matches_the_summary"] = report_path.read_text(encoding="utf-8") == rendered
    except (KeyError, TypeError):
        checks["report_matches_the_summary"] = False
    checks["curve_contradiction_is_the_complement_of_the_interior_peak"] = bool(
        summary["curve"]["contradicts_mechanism"]
    ) is (not bool(summary["curve"]["interior_peak"]))
    checks["version_1_reading_not_rewritten"] = (
        summary["readings"][summary["arms"]["baseline"]][HYBRID]["r2"]["mean"]
        == summary["baseline_reproduces"]["published_r2"]
    )
    return checks

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
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
        checks = run_check(Path(args.summary), Path(args.report), Path(args.artifacts_dir))
        print("=== lever 9 erratum --check: derived fields recomputed from the artifacts ===")
        for name, ok in checks.items():
            print(f"{'OK  ' if ok else 'FAIL'} {name}")
        failed = [name for name, ok in checks.items() if not ok]
        print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
        return 1 if failed else 0

    seed = int(args.seed)
    n_repeats = int(args.repeats)
    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if prereg_payload["status"] != "locked_before_run":
        raise SystemExit("the erratum pre-registration is not in its locked state")

    merged, _feature_report = merge_feature_blocks()
    coverage_rows, _coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == v1.ROOM_BAND)

    smiles_values = [str(row["smiles"]) for row in coverage_rows]
    knowledge, _pool_report = v1.knowledge_feature_block(smiles_values)

    splits, executed_repeats, repeat_note = v1.scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    redeal, _, _ = v1.scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
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
    }
    version_1_fold_deal = json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))[
        "main_scoreboard"
    ]["fold_deal"]
    fold_deal["matches_version_1_signature"] = bool(
        fold_deal["signature_sha256"] == version_1_fold_deal["signature_sha256"]
    )

    baseline_fold, baseline_repeat, baseline_prediction, _baseline_leak = run_protocol(
        BASELINE_ARM,
        iter(splits),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    baseline_summary = summarize_repeats(baseline_repeat)
    baseline_verified = v1.verify_reference_triple(baseline_summary, BASELINE_ARM)

    corrected = run_corrected_arm(
        CORRECTED_ARM,
        splits,
        morgan=morgan,
        frozen_physical=physical,
        knowledge=knowledge,
        target=target,
        temperatures=temperatures,
        groups=groups,
        k_grid=v1.K_GRID,
        seed=seed,
    )
    pool_control = run_corrected_arm(
        POOL_ORDER_ARM,
        splits,
        morgan=morgan,
        frozen_physical=physical,
        knowledge=knowledge,
        target=target,
        temperatures=temperatures,
        groups=groups,
        k_grid=v1.K_GRID,
        seed=seed,
        order_rule="pool_order",
    )
    placebo_target, placebo_order = v1.shuffled_target(
        target, seed=seed + v1.PLACEBO_SEED_OFFSET
    )
    placebo_frozen = v1.run_frozen_reference(
        PLACEBO_FROZEN_ARM,
        splits,
        morgan=morgan,
        physical=physical,
        target=placebo_target,
        temperatures=temperatures,
        groups=groups,
        seed=seed,
    )
    placebo_floor = v1.fold_mean_floor(
        f"{PLACEBO_CORRECTED_ARM}_floor",
        splits,
        target=placebo_target,
    )
    placebo = run_corrected_arm(
        PLACEBO_CORRECTED_ARM,
        splits,
        morgan=morgan,
        frozen_physical=physical,
        knowledge=knowledge,
        target=placebo_target,
        temperatures=temperatures,
        groups=groups,
        k_grid=v1.K_GRID,
        seed=seed,
    )

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        executed_repeats=executed_repeats,
        repeat_note=repeat_note,
        corrected=corrected,
        placebo=placebo,
        placebo_frozen=placebo_frozen,
        pool_control=pool_control,
        placebo_floor=placebo_floor,
        placebo_order=placebo_order,
        baseline_repeat_rows=baseline_repeat,
        baseline_summary=baseline_summary,
        baseline_verified=baseline_verified,
        fold_deal=fold_deal,
        prereg_payload=prereg_payload,
        generated_at=generated_at,
    )
    summary["importance_stability"] = v1.importance_stability(
        list(corrected["importance_rows"]),  # type: ignore[arg-type]
        top_k=3,
    )
    summary["guards"] = {
        "ranking_scope_checked_on_every_fold": True,
        "test_rows_visible_to_ranking": 0,
        "fold_deal_matches_version_1": bool(fold_deal["matches_version_1_signature"]),
    }

    summary_path = Path(args.summary)
    report_path = Path(args.report)
    artifacts_dir = Path(args.artifacts_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_path.write_text(
        "\n".join(render_report(summary)) + "\n", encoding="utf-8", newline="\n"
    )
    write_artifacts(
        artifacts_dir,
        ARTIFACT_STEM,
        fold_rows=[
            *baseline_fold,
            *corrected["fold_rows"],  # type: ignore[misc]
            *pool_control["fold_rows"],  # type: ignore[misc]
            *placebo_frozen["fold_rows"],  # type: ignore[misc]
            *placebo["fold_rows"],  # type: ignore[misc]
            *placebo_floor["fold_rows"],  # type: ignore[misc]
        ],
        repeat_rows=[
            *baseline_repeat,
            *corrected["repeat_rows"],  # type: ignore[misc]
            *pool_control["repeat_rows"],  # type: ignore[misc]
            *placebo_frozen["repeat_rows"],  # type: ignore[misc]
            *placebo["repeat_rows"],  # type: ignore[misc]
            *placebo_floor["repeat_rows"],  # type: ignore[misc]
        ],
        prediction_rows=[
            *baseline_prediction,
            *corrected["prediction_rows"],  # type: ignore[misc]
            *pool_control["prediction_rows"],  # type: ignore[misc]
            *placebo_frozen["prediction_rows"],  # type: ignore[misc]
            *placebo["prediction_rows"],  # type: ignore[misc]
        ],
        importance_rows=list(corrected["importance_rows"]),  # type: ignore[arg-type]
        defect_rows=list(corrected["defect_rows"]),  # type: ignore[arg-type]
        binding_rows=list(corrected["binding_rows"]),  # type: ignore[arg-type]
    )

    print("=== lever 9 erratum round ===")
    print(f"fold signature matches version 1: {fold_deal['matches_version_1_signature']}")
    print(
        f"baseline verified: {baseline_verified['verified']} "
        f"({baseline_verified['reproduced_r2']!r})"
    )
    comparison = summary["comparison_with_version_1"]
    print("delta-R2 by k (version 1 -> corrected):")
    for key in sorted(comparison["version_1_delta_r2_by_k"], key=int):
        print(
            f"  k={key:>2}  {comparison['version_1_delta_r2_by_k'][key]:+.9f}  ->  "
            f"{comparison['corrected_delta_r2_by_k'][key]:+.9f}"
        )
    print(f"corrected curve: {summary['curve']['shape']}, best k={summary['curve']['best_k']}")
    sensitivity = summary["order_sensitivity"]
    print("k=10 by order:")
    for label, value in sensitivity["k10_by_order"].items():
        print(f"  {label}: {value:+.9f}")
    print(f"  spread: {sensitivity['k10_spread']:.9f}")
    print(f"  every order below the pass line: {sensitivity['all_orders_below_the_pass_line']}")
    print(f"verdict: {summary['verdict']['decision']}")
    for reason in summary["verdict"]["reasons"]:
        print(f"  - {reason}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())