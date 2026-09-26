"""Paired room-window protocols for the v1.x dielectric observation table.

`probes/dielectric_band_ablation.py` scored five band protocols and left two
questions explicitly open.

* Section 7.4: `train_core_test_room` (train on room+extended, score on room)
  and `train_all_test_room` (train on every band, score on room) were never run.
  The ablation could therefore only show that widening the *scored* rows hurts;
  it could not say what widening the *training* rows does when the scored rows
  stay pinned to the declared window.
* Section 6: `band_room_only` (R2 0.4091) cannot be claimed as a win over v1.0
  (R2 0.3636) because the two numbers sit on different target pools (variance
  335.64 vs 580.30).

This probe closes both gaps with strictly paired protocols. "Paired" means one
fold assignment, one compound pool and one scored row set per chain, so a delta
reads as the effect of the single thing that changed.

Family 1 - the window family. Four protocols, the first three sharing one fold
assignment and one scored row set (the 457 room-band rows of the 97 compounds
that have any)::

    protocol               training rows     scored rows
    band_room_only         room              room
    train_core_test_room   room + extended   room
    train_all_test_room    every band        room
    band_all               every band        every band

`band_room_only` and `band_all` are the band-ablation protocols, re-run here so
that a reproduction failure is caught before any new number is reported.
`band_room_only` -> `train_core_test_room` -> `train_all_test_room` varies only
the training material, so the two deltas read directly as the value of the
out-of-window rows *as training data*.

Family 2 - the v1.0 cohort. v1.0's modelling pool is the 236 rows of
`data/processed/dielectric_physical_features_v03.csv` that pass both the
`model_ready` gate and xTB. All 98 v1.1 modelling compounds sit inside it and 97
of them have a room row, so the cohort locks the compound pool, the folds and
the row provenance::

    protocol                          rows per compound            targets
    cohort_v10_frozen                 1 (the v1.0 table itself)    v1.0 curated dielectric
    cohort_single_row                 1 (nearest 298.15 K room)    v1.1 observation
    cohort_room_train_single_test     train all room rows,         v1.1 observation
                                      score the single row
    cohort_room_rows                  all room rows                v1.1 observation

`cohort_single_row` -> `cohort_room_train_single_test` holds the scored rows
byte-identical (same folds, same compounds, same temperatures, same targets) and
widens only the training material. `cohort_room_train_single_test` ->
`cohort_room_rows` holds the training rows fixed and widens the scored set.
`cohort_v10_frozen` -> `cohort_single_row` is the label-provenance step.

Every protocol is grouped by InChIKey (whole compounds held out, shuffled
compound order, 10x5) with the frozen XGBoost hybrid representation. A
row-level `random_row` splitter is never used here.

The probe is read-only with respect to the released v1.0 artefacts. It writes
only `probes/artifacts/dielectric_room_window_paired_*.csv` and
`probes/dielectric_room_window_paired_summary.json`, and re-runs the frozen
236-compound endpoint replay from `dielectric_band_ablation` to prove the
pipeline it inherits is intact.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_band_ablation import (
    CORE_BANDS,
    INERT_TOLERANCE,
    MIN_TEST_ROWS_PER_FOLD,
    ROOM_BAND,
    classify,
    drop_thin_folds,
    effective_repeats,
    verify_frozen_endpoint,
)
from dielectric_band_ablation import SUMMARY_PATH as BAND_ABLATION_SUMMARY_PATH
from dielectric_observations_grouped_benchmark import (
    FEATURES_PATH,
    FOLD_COLUMNS,
    METRIC_NAMES,
    OBSERVATIONS_PATH,
    PREDICTION_COLUMNS,
    build_matrices,
    grouped_folds,
    load_table,
    run_protocol,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    DATASET_PATH,
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_room_window_paired_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"

HYBRID = "Morgan+Physical"
#: v1.0 shipped one value per compound at the declared reference temperature, so
#: the one-row control picks each compound's room observation nearest to this.
TARGET_TEMPERATURE_K = 298.15
#: Metrics the paired chains are read on. MAE alone can improve while the model
#: only shrinks towards the mean, so R2 and Spearman are always reported with it.
PAIRED_METRICS = ("r2", "mae", "spearman")

WINDOW_PROTOCOLS = (
    "band_room_only",
    "train_core_test_room",
    "train_all_test_room",
    "band_all",
)
COHORT_PROTOCOLS = (
    "cohort_v10_frozen",
    "cohort_single_row",
    "cohort_room_train_single_test",
    "cohort_room_rows",
)
#: Protocols that also exist in the band ablation, and must reproduce it exactly.
REFERENCE_PROTOCOLS = ("band_room_only", "band_all")
#: The three window protocols that share one fold assignment and one scored set.
WINDOW_SHARED_PROTOCOLS = (
    "band_room_only",
    "train_core_test_room",
    "train_all_test_room",
)

#: The paired chains, as (base, widened) protocol pairs.
WINDOW_CHAIN = (
    ("band_room_only", "train_core_test_room"),
    ("train_core_test_room", "train_all_test_room"),
    ("band_room_only", "train_all_test_room"),
)
COHORT_CHAIN = (
    ("cohort_v10_frozen", "cohort_single_row"),
    ("cohort_single_row", "cohort_room_train_single_test"),
    ("cohort_room_train_single_test", "cohort_room_rows"),
    ("cohort_single_row", "cohort_room_rows"),
)

TRAIN_MASK_DESCRIPTIONS = {
    "band_room_only": "room_temperature",
    "train_core_test_room": "room_temperature + extended_temperature",
    "train_all_test_room": "every band",
    "band_all": "every band",
    "cohort_v10_frozen": "the single frozen v1.0 cohort rows",
    "cohort_single_row": "the single room rows of the cohort",
    "cohort_room_train_single_test": "every room row of the cohort",
    "cohort_room_rows": "every room row of the cohort",
}

PROTOCOL_DESCRIPTIONS = {
    "band_room_only": (
        "train and score on room_temperature rows, grouped 10x5 (band-ablation reference)"
    ),
    "train_core_test_room": (
        "train on room+extended rows, score on room rows only; same folds and same scored rows "
        "as band_room_only"
    ),
    "train_all_test_room": (
        "train on every band, score on room rows only; same folds and same scored rows as "
        "band_room_only"
    ),
    "band_all": "train and score on every band, grouped 10x5 (band-ablation reference)",
    "cohort_v10_frozen": (
        "v1.0 cohort, one frozen v1.0 row per compound: v1.0 features and the curated dielectric label"
    ),
    "cohort_single_row": (
        "v1.0 cohort, one room row per compound (nearest 298.15 K), v1.1 observation label"
    ),
    "cohort_room_train_single_test": (
        "v1.0 cohort, train on every room row, score the single nearest-298.15 K room row; same "
        "scored rows as cohort_single_row"
    ),
    "cohort_room_rows": "v1.0 cohort, train and score on every room row, grouped 10x5",
}


def band_of(row: Mapping[str, object]) -> str:
    return str(row["temperature_band"])


def inchikey_of(row: Mapping[str, object]) -> str:
    return str(row["inchikey"])


def fold_of_by_repeat(
    keys: Sequence[str],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> list[dict[str, int]]:
    """Deal whole compounds into folds, repeat by repeat.

    Byte-for-byte the dealing rule of
    `dielectric_observations_grouped_benchmark.grouped_folds`: a fresh
    permutation of the sorted compound keys per repeat, dealt round-robin. It is
    re-derived rather than imported so that one assignment can be shared by
    protocols whose row pools differ but whose compound pool does not.
    """

    unique = np.asarray(sorted({str(key) for key in keys}))
    if unique.size == 0:
        raise ValueError("no compounds to deal into folds")
    assignments: list[dict[str, int]] = []
    for repeat in range(n_repeats):
        rng = np.random.default_rng(seed + repeat)
        shuffled = rng.permutation(unique)
        assignments.append(
            {str(key): index % n_splits for index, key in enumerate(shuffled)}
        )
    return assignments


def masked_splits(
    row_groups: Sequence[str],
    *,
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """Yield global row indices for a paired protocol.

    Folds are dealt over the compounds of `score_mask` alone, which is what
    makes two protocols with the same scored compounds share one fold assignment
    even when one of them trains on a wider row pool. `train_mask` then decides
    which rows of the *other* folds may enter the fit: a row is eligible only
    when its fold differs from the scored fold, so a held-out compound can never
    reach the training side. A compound that never appears in `score_mask` has no
    fold and is therefore training-only material in every fold, which is
    reported rather than silently dropped.
    """

    group_array = np.asarray([str(key) for key in row_groups])
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    if score.shape != group_array.shape or train.shape != group_array.shape:
        raise ValueError("masks must provide exactly one boolean per row")
    if not score.any():
        raise ValueError("the scored mask selects no rows")
    if not train.any():
        raise ValueError("the training mask selects no rows")
    for repeat, fold_of in enumerate(
        fold_of_by_repeat(
            group_array[score], n_splits=n_splits, n_repeats=n_repeats, seed=seed
        )
    ):
        row_fold = np.asarray([fold_of.get(str(key), -1) for key in group_array])
        for fold in range(n_splits):
            test_index = np.flatnonzero(score & (row_fold == fold))
            train_index = np.flatnonzero(train & (row_fold != fold))
            yield repeat, fold, train_index, test_index


def own_mode_equivalence(
    row_groups: Sequence[str],
    *,
    mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Check `masked_splits` against `grouped_folds` when score == train.

    `band_room_only` and `band_all` are `own`-mode protocols: they fit and score
    on the same row pool, so the paired splitter has to reproduce the
    band-ablation splitter exactly. The comparison is recomputed here from the
    index arrays rather than assumed.
    """

    index_mask = np.asarray(mask, dtype=bool)
    local = np.flatnonzero(index_mask)
    sub_groups = [str(row_groups[int(index)]) for index in local]
    reference = [
        (repeat, fold, local[train], local[test])
        for repeat, fold, train, test in grouped_folds(
            sub_groups, n_splits=n_splits, n_repeats=n_repeats, seed=seed
        )
    ]
    mine = list(
        masked_splits(
            row_groups,
            score_mask=index_mask,
            train_mask=index_mask,
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=seed,
        )
    )
    if len(mine) != len(reference):
        return {
            "available": True,
            "identical": False,
            "reason": f"fold count {len(mine)} != grouped_folds {len(reference)}",
        }
    identical = all(
        left[0] == right[0]
        and left[1] == right[1]
        and np.array_equal(left[2], right[2])
        and np.array_equal(left[3], right[3])
        for left, right in zip(mine, reference, strict=True)
    )
    return {
        "available": True,
        "identical": bool(identical),
        "folds": len(mine),
        "scored_rows": int(index_mask.sum()),
    }


def fold_signature(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> tuple:
    """A hashable fingerprint of a fold assignment, for the shared-fold check."""

    return tuple(
        (repeat, fold, tuple(int(index) for index in train), tuple(int(index) for index in test))
        for repeat, fold, train, test in splits
    )


def scored_fold_signature(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> tuple:
    """Fingerprint only the *scored* side of a fold assignment.

    Two protocols can share a fold assignment while training on different row
    pools, so the paired claim is that the scored rows of every fold coincide;
    the training side is exactly the thing that is allowed to differ.
    """

    return tuple(
        (repeat, fold, tuple(int(index) for index in np.sort(test)))
        for repeat, fold, _train, test in splits
    )


def audit_masks(
    row_groups: Sequence[str],
    *,
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> dict[str, object]:
    """Re-derive the paired contract from the fold indices that were run."""

    group_array = np.asarray([str(key) for key in row_groups])
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    straddling: list[int] = []
    test_rows = 0
    test_rows_outside_score_mask = 0
    train_rows_used = 0
    train_rows_unused = 0
    for _repeat, _fold, train_index, test_index in splits:
        test_groups = np.unique(group_array[test_index])
        straddling.append(int(np.intersect1d(group_array[train_index], test_groups).size))
        test_rows += int(test_index.size)
        test_rows_outside_score_mask += int((~score[test_index]).sum())
        eligible = np.flatnonzero(train & ~np.isin(group_array, test_groups))
        train_rows_used += int(train_index.size)
        train_rows_unused += int(eligible.size - np.intersect1d(eligible, train_index).size)
    return {
        "folds": len(splits),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
        "scored_rows_total": test_rows,
        "scored_rows_outside_the_score_mask": test_rows_outside_score_mask,
        "train_rows_used": train_rows_used,
        "train_rows_offered_but_unused": train_rows_unused,
        "compounds_scored": int(np.unique(group_array[score]).size),
        "compounds_available_for_training": int(np.unique(group_array[train]).size),
        "training_only_compounds": sorted(set(group_array[train]) - set(group_array[score])),
    }


def target_pool_stats(target: np.ndarray) -> dict[str, float | int]:
    values = np.asarray(target, dtype=float)
    return {
        "rows": int(values.size),
        "mean": float(values.mean()),
        "var": float(values.var()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
    }


def read_band_ablation_reference(
    path: Path = BAND_ABLATION_SUMMARY_PATH,
) -> dict[str, object]:
    """Load the band-ablation numbers the two shared protocols must reproduce."""

    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    if not summary:
        return {}
    return {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "protocols": {
            name: summary[name] for name in REFERENCE_PROTOCOLS if name in summary
        },
        "inputs": payload.get("inputs", {}),
        "frozen_endpoint": payload.get("reference", {}).get("frozen_endpoint", {}),
    }


def compare_protocol_reference(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    reference: Mapping[str, object],
) -> dict[str, object]:
    """Diff re-runs of the two shared protocols against their published numbers."""

    theirs = reference.get("protocols") or {}
    comparisons: dict[str, object] = {}
    for name in REFERENCE_PROTOCOLS:
        mine = summary.get(name)
        other = theirs.get(name)  # type: ignore[union-attr]
        if not mine or not other:
            comparisons[name] = {
                "available": False,
                "bit_exact": None,
                "reason": "protocol missing from one side",
            }
            continue
        per_representation: dict[str, object] = {}
        for representation in REPRESENTATIONS:
            if representation not in mine or representation not in other:
                continue
            deltas = {
                metric: float(mine[representation][metric]["mean"])
                - float(other[representation][metric]["mean"])
                for metric in METRIC_NAMES
                if other[representation].get(metric, {}).get("mean") is not None
            }
            per_representation[representation] = {
                "deltas": deltas,
                "max_abs_delta": max((abs(value) for value in deltas.values()), default=0.0),
                # An empty `deltas` means the two sides share no metric name, which
                # is not a pass: it is an unverifiable comparison.
                "bit_exact": bool(deltas) and all(value == 0.0 for value in deltas.values()),
            }
        comparisons[name] = {
            "available": True,
            "representations": per_representation,
            "max_abs_delta": max(
                (float(item["max_abs_delta"]) for item in per_representation.values()),
                default=0.0,
            ),
            "bit_exact": bool(per_representation)
            and all(bool(item["bit_exact"]) for item in per_representation.values()),
        }
    return comparisons


def paired_delta(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    *,
    base: str,
    widened: str,
    representation: str = HYBRID,
    tolerance: float = INERT_TOLERANCE,
) -> dict[str, object]:
    """Read one paired step on R2, MAE and Spearman at once."""

    if base not in summary or widened not in summary:
        return {"available": False, "base": base, "widened": widened}
    metrics: dict[str, dict[str, float]] = {}
    for metric in PAIRED_METRICS:
        before = float(summary[base][representation][metric]["mean"])
        after = float(summary[widened][representation][metric]["mean"])
        metrics[metric] = {"base": before, "widened": after, "delta": after - before}
    delta_r2 = metrics["r2"]["delta"]
    return {
        "available": True,
        "base": base,
        "widened": widened,
        "representation": representation,
        "metrics": metrics,
        "delta_r2": delta_r2,
        "verdict": classify(delta_r2, tolerance=tolerance),
        "tolerance": tolerance,
    }


def scored_row_fingerprints(
    prediction_rows: Sequence[Mapping[str, object]],
    protocol: str,
    *,
    representation: str = HYBRID,
) -> list[tuple[int, int, str, float, float]]:
    keys = [
        (
            int(row["repeat"]),  # type: ignore[arg-type]
            int(row["fold"]),  # type: ignore[arg-type]
            str(row["inchikey"]),
            round(float(row["T_K"]), 9),  # type: ignore[arg-type]
            round(float(row["target"]), 9),  # type: ignore[arg-type]
        )
        for row in prediction_rows
        if str(row["protocol"]) == protocol and str(row["representation"]) == representation
    ]
    return sorted(keys)


def paired_contract(
    prediction_rows: Sequence[Mapping[str, object]],
    chain: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Prove from the artifacts which chains really scored the same rows."""

    report: dict[str, object] = {}
    for base, widened in chain:
        before = scored_row_fingerprints(prediction_rows, base)
        after = scored_row_fingerprints(prediction_rows, widened)
        report[f"{base} -> {widened}"] = {
            "base_rows": len(before),
            "widened_rows": len(after),
            "identical_scored_rows": before == after,
            "widened_is_a_superset": not (Counter(before) - Counter(after)),
        }
    return report


def v10_modelling_pool(
    features_path: Path = FEATURES_PATH,
    dataset_path: Path = DATASET_PATH,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """The exact rows v1.0 fitted on: model_ready and xTB both passed."""

    rows, failed_rows, withheld_rows = read_modelling_rows(
        features_path, dataset_path=dataset_path
    )
    return rows, {
        "rows": len(rows),
        "failed_rows": len(failed_rows),
        "withheld_rows": len(withheld_rows),
    }


def cohort_membership(
    v10_rows: Sequence[Mapping[str, str]],
    v11_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Lock the compound pool to v1.0's modelling roster intersected with v1.1."""

    v10_keys = {inchikey_of(row) for row in v10_rows}
    v11_keys = {inchikey_of(row) for row in v11_rows}
    room_keys = {inchikey_of(row) for row in v11_rows if band_of(row) == ROOM_BAND}
    shared = v10_keys & v11_keys
    return {
        "v1_0_modelling_compounds": len(v10_keys),
        "v1_1_modelling_compounds": len(v11_keys),
        "shared_compounds": sorted(shared),
        "v1_1_compounds_outside_the_v1_0_pool": sorted(v11_keys - v10_keys),
        "shared_compounds_without_a_room_row": sorted(shared - room_keys),
        "cohort": sorted(shared & room_keys),
    }


def room_single_row_indices(
    rows: Sequence[Mapping[str, object]],
    *,
    target_temperature_k: float = TARGET_TEMPERATURE_K,
) -> dict[str, int]:
    """Map each compound to its room row nearest `target_temperature_k`."""

    best: dict[str, int] = {}
    best_distance: dict[str, float] = {}
    for index, row in enumerate(rows):
        key = inchikey_of(row)
        distance = abs(float(str(row["T_K"])) - target_temperature_k)
        if key not in best or distance < best_distance[key]:
            best[key] = index
            best_distance[key] = distance
    return best


def frozen_cohort_matrices(
    v10_rows: Sequence[Mapping[str, str]],
    cohort: Sequence[str],
) -> tuple[list[Mapping[str, str]], np.ndarray, np.ndarray, np.ndarray]:
    """v1.0's own features and labels for the cohort, in a deterministic order."""

    by_key = {str(row["inchikey"]): row for row in v10_rows}
    missing = [key for key in cohort if key not in by_key]
    if missing:
        raise ValueError(
            "cohort compounds absent from the v1.0 modelling pool: " + ", ".join(missing)
        )
    rows = [by_key[key] for key in cohort]
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([str(row["smiles"]) for row in rows])
    physical = physical_feature_matrix(rows)
    return rows, morgan, physical, target


def frozen_vs_observation_alignment(
    observation_rows: Sequence[Mapping[str, object]],
    v10_rows: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    """Quantify what else moves when the frozen label is swapped for the observation."""

    by_key = {str(row["inchikey"]): row for row in v10_rows}
    deltas_t: list[float] = []
    deltas_e: list[float] = []
    for row in observation_rows:
        frozen = by_key[inchikey_of(row)]
        deltas_t.append(abs(float(str(row["T_K"])) - float(frozen["T_K"])))
        deltas_e.append(abs(float(str(row["epsilon"])) - float(frozen["dielectric"])))
    return {
        "rows": len(observation_rows),
        "abs_delta_T_K": {
            "median": float(np.median(deltas_t)),
            "max": float(max(deltas_t)),
            "rows_above_1e-9": int(sum(1 for value in deltas_t if value > 1e-9)),
        },
        "abs_delta_epsilon": {
            "median": float(np.median(deltas_e)),
            "max": float(max(deltas_e)),
            "rows_above_0.01": int(sum(1 for value in deltas_e if value > 0.01)),
        },
    }

def _run_one(
    protocol: str,
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """Run one paired protocol and return its rows, its audit and its splits."""

    group_array = np.asarray(groups)
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    if target.size != group_array.size:
        raise ValueError("target and group arrays must describe the same rows")
    compound_count = int(np.unique(group_array[score]).size)
    repeats, note = effective_repeats(
        compound_count, n_splits=n_splits, requested=n_repeats
    )
    meta: dict[str, object] = {
        "description": PROTOCOL_DESCRIPTIONS[protocol],
        "score_mask": "every band" if protocol == "band_all" else "room_temperature",
        "train_mask": TRAIN_MASK_DESCRIPTIONS[protocol],
        "scored_rows": int(score.sum()),
        "compounds_scored": compound_count,
        "train_pool_rows": int(train.sum()),
        "requested_repeats": n_repeats,
        "executed_repeats": repeats,
        "note": note,
    }
    if repeats == 0:
        meta.update(
            {
                "folds": 0,
                "train_rows_mean": None,
                "train_compounds_mean": None,
                "test_rows_mean": None,
                "test_compounds_mean": None,
            }
        )
        return {
            "meta": meta,
            "audit": {"note": note, "folds": 0},
            "fold_rows": [],
            "repeat_rows": [],
            "prediction_rows": [],
            "splits": [],
        }

    splits = list(
        drop_thin_folds(
            masked_splits(
                groups,
                score_mask=score,
                train_mask=train,
                n_splits=n_splits,
                n_repeats=repeats,
                seed=seed,
            )
        )
    )
    if not splits:
        raise ValueError(f"{protocol}: no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["folds_with_a_straddling_compound"]:
        raise ValueError(f"{protocol}: a compound straddles the fold boundary")
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError(f"{protocol}: a scored row sits outside the score mask")

    meta.update(
        {
            "folds": len(splits),
            "train_rows_mean": float(np.mean([item[2].size for item in splits])),
            "train_compounds_mean": float(
                np.mean([np.unique(group_array[item[2]]).size for item in splits])
            ),
            "test_rows_mean": float(np.mean([item[3].size for item in splits])),
            "test_compounds_mean": float(
                np.mean([np.unique(group_array[item[3]]).size for item in splits])
            ),
        }
    )
    fold_rows, repeat_rows, prediction_rows, _leak = run_protocol(
        protocol,
        iter(splits),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    return {
        "meta": meta,
        "audit": audit,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "splits": splits,
    }


def run_window_family(
    rows: Sequence[Mapping[str, object]],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Protocols 1-4: hold the scored rows on the declared window, widen training."""

    morgan, physical, target, temperatures, groups = build_matrices(rows)
    band_array = np.asarray([band_of(row) for row in rows])
    every = np.ones(len(rows), dtype=bool)
    score_room = band_array == ROOM_BAND
    masks = {
        "band_room_only": (score_room, score_room),
        "train_core_test_room": (score_room, np.isin(band_array, list(CORE_BANDS))),
        "train_all_test_room": (score_room, every),
        "band_all": (every, every),
    }

    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    meta: dict[str, object] = {}
    audits: dict[str, object] = {}
    splits_by_protocol: dict[str, list[tuple[int, int, np.ndarray, np.ndarray]]] = {}
    for protocol in WINDOW_PROTOCOLS:
        score_mask, train_mask = masks[protocol]
        result = _run_one(
            protocol,
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            score_mask=score_mask,
            train_mask=train_mask,
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=seed,
        )
        meta[protocol] = result["meta"]
        audits[protocol] = result["audit"]
        splits_by_protocol[protocol] = result["splits"]  # type: ignore[assignment]
        fold_rows.extend(result["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(result["repeat_rows"])  # type: ignore[arg-type]
        prediction_rows.extend(result["prediction_rows"])  # type: ignore[arg-type]

    shared_signatures = {
        protocol: scored_fold_signature(splits_by_protocol[protocol])
        for protocol in WINDOW_SHARED_PROTOCOLS
        if splits_by_protocol.get(protocol)
    }
    return {
        "protocols": meta,
        "audits": audits,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summarize_repeats(repeat_rows),
        "target_pools": {
            protocol: target_pool_stats(target[np.asarray(masks[protocol][0], dtype=bool)])
            for protocol in WINDOW_PROTOCOLS
        },
        "folds_shared_by": list(WINDOW_SHARED_PROTOCOLS),
        "shared_fold_basis": "the scored room-band rows of every fold, per repeat",
        "folds_are_shared": len(set(shared_signatures.values())) == 1
        and len(shared_signatures) == len(WINDOW_SHARED_PROTOCOLS),
        "own_mode_equivalence": {
            name: own_mode_equivalence(
                groups,
                mask=masks[name][0],
                n_splits=n_splits,
                n_repeats=n_repeats,
                seed=seed,
            )
            for name in REFERENCE_PROTOCOLS
        },
    }


def run_cohort_family(
    rows: Sequence[Mapping[str, object]],
    v10_rows: Sequence[Mapping[str, str]],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Protocols 5-8: the paired v1.0 reconciliation on the locked cohort."""

    membership = cohort_membership(v10_rows, rows)
    cohort = [str(key) for key in membership["cohort"]]  # type: ignore[union-attr]
    cohort_set = set(cohort)

    room_rows = [
        row for row in rows if band_of(row) == ROOM_BAND and inchikey_of(row) in cohort_set
    ]
    if {inchikey_of(row) for row in room_rows} != cohort_set:
        raise ValueError("the cohort definition and its room rows disagree")
    room_morgan, room_physical, room_target, room_temperatures, room_groups = (
        build_matrices(room_rows)
    )
    single_index = room_single_row_indices(room_rows)
    if sorted(single_index) != cohort:
        raise ValueError("the one-row control does not cover the cohort exactly")
    single_positions = np.asarray(sorted(single_index.values()))
    single_mask = np.zeros(len(room_rows), dtype=bool)
    single_mask[single_positions] = True
    single_rows = [room_rows[int(index)] for index in single_positions]
    if len(single_rows) != len(cohort):
        raise ValueError("one row per compound was expected for the single-row control")

    frozen_rows, frozen_morgan, frozen_physical, frozen_target = frozen_cohort_matrices(
        v10_rows, cohort
    )
    single_morgan, single_physical, single_target, single_temperatures, single_groups = (
        build_matrices(single_rows)
    )
    every_room = np.ones(len(room_rows), dtype=bool)
    every_single = np.ones(len(single_rows), dtype=bool)
    every_frozen = np.ones(len(frozen_rows), dtype=bool)

    spaces = {
        "cohort_v10_frozen": (
            frozen_morgan,
            frozen_physical,
            frozen_target,
            [float(str(row["T_K"])) for row in frozen_rows],
            [str(row["inchikey"]) for row in frozen_rows],
            every_frozen,
            every_frozen,
        ),
        "cohort_single_row": (
            single_morgan,
            single_physical,
            single_target,
            single_temperatures,
            single_groups,
            every_single,
            every_single,
        ),
        "cohort_room_train_single_test": (
            room_morgan,
            room_physical,
            room_target,
            room_temperatures,
            room_groups,
            single_mask,
            every_room,
        ),
        "cohort_room_rows": (
            room_morgan,
            room_physical,
            room_target,
            room_temperatures,
            room_groups,
            every_room,
            every_room,
        ),
    }

    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    meta: dict[str, object] = {}
    audits: dict[str, object] = {}
    splits_by_protocol: dict[str, list[tuple[int, int, np.ndarray, np.ndarray]]] = {}
    for protocol in COHORT_PROTOCOLS:
        (
            protocol_morgan,
            protocol_physical,
            protocol_target,
            protocol_temperatures,
            protocol_groups,
            score_mask,
            train_mask,
        ) = spaces[protocol]
        result = _run_one(
            protocol,
            morgan=protocol_morgan,
            physical=protocol_physical,
            target=protocol_target,
            temperatures=protocol_temperatures,
            groups=protocol_groups,
            score_mask=score_mask,
            train_mask=train_mask,
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=seed,
        )
        meta[protocol] = result["meta"]
        audits[protocol] = result["audit"]
        splits_by_protocol[protocol] = result["splits"]  # type: ignore[assignment]
        fold_rows.extend(result["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(result["repeat_rows"])  # type: ignore[arg-type]
        prediction_rows.extend(result["prediction_rows"])  # type: ignore[arg-type]

    assignments = {
        protocol: fold_of_by_repeat(
            groups, n_splits=n_splits, n_repeats=n_repeats, seed=seed
        )
        for protocol, groups in (
            ("cohort_v10_frozen", [str(row["inchikey"]) for row in frozen_rows]),
            ("cohort_single_row", single_groups),
            (
                "cohort_room_train_single_test",
                [room_groups[int(index)] for index in single_positions],
            ),
            ("cohort_room_rows", room_groups),
        )
    }
    delivered_assignments = {
        (protocol, repeat): tuple(sorted(assignment.items()))
        for protocol, assignment_per_repeat in assignments.items()
        for repeat, assignment in enumerate(assignment_per_repeat)
    }
    # Repeats are *supposed* to differ from one another (each redraws the
    # compound permutation), so the invariant is per repeat: within a single
    # repeat every protocol must use the same fold assignment.
    signatures_by_repeat: dict[int, set[tuple]] = defaultdict(set)
    for (_protocol, repeat), signature in delivered_assignments.items():
        signatures_by_repeat[repeat].add(signature)
    folds_shared = (
        len(delivered_assignments) == len(COHORT_PROTOCOLS) * n_repeats
        and set(signatures_by_repeat) == set(range(n_repeats))
        and all(len(signatures) == 1 for signatures in signatures_by_repeat.values())
    )
    target_pools = {
        "cohort_v10_frozen": target_pool_stats(frozen_target),
        "cohort_single_row": target_pool_stats(single_target),
        "cohort_room_train_single_test": target_pool_stats(single_target),
        "cohort_room_rows": target_pool_stats(room_target),
    }
    return {
        "membership": membership,
        "cohort_rows": {
            "room_rows": len(room_rows),
            "single_rows": len(single_rows),
            "frozen_rows": len(frozen_rows),
        },
        "protocols": meta,
        "audits": audits,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summarize_repeats(repeat_rows),
        "target_pools": target_pools,
        "shared_fold_basis": "the cohort compounds, dealt once and reused by all four protocols",
        "folds_are_shared": folds_shared,
        "single_row_alignment": frozen_vs_observation_alignment(single_rows, v10_rows),
        "splits_by_protocol": splits_by_protocol,
    }

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paired room-window protocols (see module docstring).")
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument(
        "--reference", type=Path, default=BAND_ABLATION_SUMMARY_PATH,
        help="band-ablation summary the shared protocols must reproduce",
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--splits", type=int, default=N_SPLITS)
    parser.add_argument("--repeats", type=int, default=N_REPEATS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--skip-frozen-endpoint",
        action="store_true",
        help="skip the 236-compound v1.0 replay that re-verifies the inherited pipeline",
    )
    return parser.parse_args(argv)


def _format_protocol(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    protocol: str,
    *,
    representation: str = HYBRID,
) -> str:
    entry = summary.get(protocol, {}).get(representation)
    if not entry:
        return "not run"
    return (
        f"R2={entry['r2']['mean']:.4f} MAE={entry['mae']['mean']:.4f} "
        f"Spearman={entry['spearman']['mean']:.4f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rows, _feature_rows, dropped = load_table(args.observations, args.features)
    v10_rows, v10_meta = v10_modelling_pool(args.features, args.dataset)

    window = run_window_family(
        rows, n_splits=args.splits, n_repeats=args.repeats, seed=args.seed
    )
    cohort = run_cohort_family(
        rows, v10_rows, n_splits=args.splits, n_repeats=args.repeats, seed=args.seed
    )
    cohort.pop("splits_by_protocol", None)

    reference = read_band_ablation_reference(args.reference)
    reproduction = compare_protocol_reference(window["summary"], reference)
    window_chain = [
        paired_delta(window["summary"], base=base, widened=widened)
        for base, widened in WINDOW_CHAIN
    ]
    cohort_chain = [
        paired_delta(cohort["summary"], base=base, widened=widened)
        for base, widened in COHORT_CHAIN
    ]
    contract = {
        "window": paired_contract(window["prediction_rows"], WINDOW_CHAIN),
        "cohort": paired_contract(cohort["prediction_rows"], COHORT_CHAIN),
    }
    frozen_endpoint = (
        {}
        if args.skip_frozen_endpoint
        else verify_frozen_endpoint(n_repeats=args.repeats)
    )

    args.artifacts.mkdir(parents=True, exist_ok=True)
    folds_path = args.artifacts / "dielectric_room_window_paired_folds.csv"
    repeats_path = args.artifacts / "dielectric_room_window_paired_repeats.csv"
    predictions_path = args.artifacts / "dielectric_room_window_paired_predictions.csv"
    fold_rows = list(window["fold_rows"]) + list(cohort["fold_rows"])  # type: ignore[arg-type]
    repeat_rows = list(window["repeat_rows"]) + list(cohort["repeat_rows"])  # type: ignore[arg-type]
    prediction_rows = list(window["prediction_rows"]) + list(cohort["prediction_rows"])  # type: ignore[arg-type]
    write_csv_rows(folds_path, FOLD_COLUMNS, fold_rows)
    write_csv_rows(
        repeats_path, ("protocol", "representation", "repeat", *METRIC_NAMES), repeat_rows
    )
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, prediction_rows)

    payload = {
        "schema_version": 1,
        "seed": args.seed,
        "protocol": {
            "validation": "group K-fold by InChIKey, shuffled compound order, round robin",
            "n_splits": args.splits,
            "n_repeats": args.repeats,
            "random_state": args.seed,
            "model": "XGBRegressor with the frozen v1.0 hyper-parameters",
            "representations": list(REPRESENTATIONS),
            "physical_block": "frozen xTB vector with T_K replaced by the observation's T_K",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "paired_rule": (
                "folds are dealt over the compounds of the scored mask only, so protocols that "
                "score the same rows share one fold assignment even when their training pools differ"
            ),
        },
        "inputs": {
            "observations": portable_relative_path(args.observations, root=REPOSITORY_ROOT),
            "observations_sha256": canonical_text_sha256(args.observations),
            "features": portable_relative_path(args.features, root=REPOSITORY_ROOT),
            "features_sha256": canonical_text_sha256(args.features),
        },
        "dropped": dropped,
        "v1_0_pool": v10_meta,
        "window_family": {
            "protocols": window["protocols"],
            "audits": window["audits"],
            "summary": window["summary"],
            "target_pools": window["target_pools"],
            "folds_shared_by": window["folds_shared_by"],
            "shared_fold_basis": window["shared_fold_basis"],
            "folds_are_shared": window["folds_are_shared"],
            "own_mode_equivalence": window["own_mode_equivalence"],
            "chain": window_chain,
            "scored_row_contract": contract["window"],
        },
        "cohort_family": {
            "membership": cohort["membership"],
            "cohort_rows": cohort["cohort_rows"],
            "protocols": cohort["protocols"],
            "audits": cohort["audits"],
            "summary": cohort["summary"],
            "target_pools": cohort["target_pools"],
            "shared_fold_basis": cohort["shared_fold_basis"],
            "folds_are_shared": cohort["folds_are_shared"],
            "single_row_alignment": cohort["single_row_alignment"],
            "chain": cohort_chain,
            "scored_row_contract": contract["cohort"],
        },
        "reference": {
            "band_ablation": reference,
            "reproduction": reproduction,
            "frozen_endpoint": frozen_endpoint,
        },
        "outputs": {
            "folds": portable_relative_path(folds_path, root=REPOSITORY_ROOT),
            "repeats": portable_relative_path(repeats_path, root=REPOSITORY_ROOT),
            "predictions": portable_relative_path(predictions_path, root=REPOSITORY_ROOT),
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"rows {len(rows)} across {len({inchikey_of(row) for row in rows})} compounds; dropped {dropped}")
    print(f"window family (shared folds={window['folds_are_shared']}, scored set = room rows):")
    for protocol in WINDOW_PROTOCOLS:
        meta = window["protocols"][protocol]  # type: ignore[index]
        print(
            f"  {protocol:32s} scored={meta['scored_rows']:5d} compounds={meta['compounds_scored']:4d} "
            f"train/fold={meta['train_rows_mean']:.1f} test/fold={meta['test_rows_mean']:.1f} | "
            f"{_format_protocol(window['summary'], protocol)}"
        )
    print("window chain (hybrid):")
    for step in window_chain:
        print(
            f"  {step['base']:28s} -> {step['widened']:28s} "
            f"R2 {step['metrics']['r2']['base']:.4f} -> {step['metrics']['r2']['widened']:.4f} "
            f"({step['verdict']}, {step['delta_r2']:+.4f})"
        )
    membership = cohort["membership"]  # type: ignore[index]
    print(
        f"cohort: v1.0 pool {membership['v1_0_modelling_compounds']} x v1.1 pool "
        f"{membership['v1_1_modelling_compounds']} -> shared {len(membership['shared_compounds'])}, "
        f"cohort {len(membership['cohort'])}, excluded {membership['shared_compounds_without_a_room_row']}"
    )
    print(f"cohort family (shared folds={cohort['folds_are_shared']}):")
    for protocol in COHORT_PROTOCOLS:
        meta = cohort["protocols"][protocol]  # type: ignore[index]
        print(
            f"  {protocol:32s} scored={meta['scored_rows']:5d} compounds={meta['compounds_scored']:4d} "
            f"train/fold={meta['train_rows_mean']:.1f} test/fold={meta['test_rows_mean']:.1f} | "
            f"{_format_protocol(cohort['summary'], protocol)}"
        )
    print("cohort chain (hybrid):")
    for step in cohort_chain:
        print(
            f"  {step['base']:32s} -> {step['widened']:32s} "
            f"R2 {step['metrics']['r2']['base']:.4f} -> {step['metrics']['r2']['widened']:.4f} "
            f"({step['verdict']}, {step['delta_r2']:+.4f})"
        )
    for chain_name, report in contract.items():
        for pair, entry in report.items():  # type: ignore[union-attr]
            print(
                f"  contract[{chain_name}] {pair}: identical_scored_rows="
                f"{entry['identical_scored_rows']} superset={entry['widened_is_a_superset']}"
            )
    for name, comparison in reproduction.items():
        print(
            f"reproduce {name} vs band ablation: bit_exact={comparison.get('bit_exact')} "
            f"max_abs_delta={comparison.get('max_abs_delta')}"
        )
    for name, entry in window["own_mode_equivalence"].items():  # type: ignore[union-attr]
        print(f"splitter equivalence {name} vs grouped_folds: identical={entry.get('identical')}")
    if frozen_endpoint:
        print(
            f"frozen v1.0 endpoint replay: rows={frozen_endpoint['rows']} "
            f"bit_exact={frozen_endpoint['bit_exact']} "
            f"max_abs_delta={frozen_endpoint['max_abs_delta']:.3e}"
        )
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())