"""Temperature-band ablation for the v1.x dielectric observation table.

The W12 grouped benchmark
(`probes/dielectric_observations_grouped_benchmark.py`) answered whether a
temperature-resolved table *can* hold the v1.0 score under an honest grouped
protocol, and the answer was no: R2 falls from 0.3636 (v1.0, one row per
compound) to 0.1602 (all bands) while a one-row-per-compound control built from
the same observations scores 0.1861.

That left a mechanism question open. The observation table is not homogeneous:
only the room band sits inside the 293.15-303.15 K window v1.0 was declared for,
the extended band is already a +10 to +30 K extrapolation above it, and the bulk
of the extra rows are `outside_declared_window`. The W12 comparison bundles both effects together,
because protocol "all bands" changes the training rows *and* the scored rows at
the same time.

This probe separates them. The frozen pipeline is reused bit-for-bit (Morgan /
Physical / Morgan+Physical, XGBoost with the frozen hyper-parameters, the
frozen physical vector with T_K replaced by each observation's own temperature)
and the only thing that varies is which bands may enter the fit and the score:

1. `band_room_only`      - room_temperature rows only
2. `band_room_extended`  - room_temperature + extended_temperature
3. `band_all`            - every row; the W12 `grouped` protocol, so it must
                            reproduce R2 = 0.1602
4. `single_row_298`      - one row per compound (nearest 298.15 K); the W12
                            `grouped_single_row` protocol, so it must
                            reproduce R2 = 0.1861
5. `train_all_test_core` - train on every band, score on room+extended only,
                            with the same fold membership and the same scored
                            rows as protocol 2

Protocol 5 is the mechanism probe, and it decomposes the W12 gap exactly:

* protocol 2 -> 5 changes only the training rows (test rows identical), so the
  delta is the value of the out-of-window rows as *training* material;
* protocol 5 -> 3 changes only the scored rows (training rows identical), so the
  delta is the damage done by *scoring* on out-of-window rows.

Both directions are paired: same folds, same compounds, same model.

The probe is read-only with respect to the released v1.0 artefacts. It writes
only `probes/artifacts/dielectric_band_ablation_*.csv` and
`probes/dielectric_band_ablation_summary.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_observations_grouped_benchmark import (
    FEATURES_PATH,
    FOLD_COLUMNS,
    METRIC_NAMES,
    OBSERVATIONS_PATH,
    PREDICTION_COLUMNS,
    REFERENCE_SUMMARY,
    build_matrices,
    grouped_folds,
    load_table,
    run_protocol,
    select_one_row_per_compound,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    DATASET_PATH,
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    evaluate_repeat,
    fit_predict_representation,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_band_ablation_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
GROUPED_BENCHMARK_SUMMARY = (
    REPOSITORY_ROOT / "probes" / "dielectric_observations_grouped_benchmark_summary.json"
)
FROZEN_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)

ROOM_BAND = "room_temperature"
EXTENDED_BAND = "extended_temperature"
OUTSIDE_BAND = "outside_declared_window"
#: The bands the v1.0 pipeline was actually declared for. Everything else is an
#: extrapolation and must not be allowed to define a scored row by default.
CORE_BANDS = (ROOM_BAND, EXTENDED_BAND)
BAND_ORDER = (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND)

HYBRID = "Morgan+Physical"
#: A paired delta smaller than this is reported as inert rather than as a win or
#: a loss. 0.005 is well under the repeat-to-repeat SD (0.11 for the grouped
#: protocol) so it cannot manufacture a trend out of seed noise.
INERT_TOLERANCE = 0.005
#: A fold with a single scored row has an undefined R2, so it is dropped and
#: counted instead of being silently turned into a NaN.
MIN_TEST_ROWS_PER_FOLD = 2

BAND_PROTOCOLS = (
    "band_room_only",
    "band_room_extended",
    "band_all",
    "single_row_298",
    "train_all_test_core",
)

PROTOCOL_DESCRIPTIONS = {
    "band_room_only": "room_temperature rows only, grouped 10x5",
    "band_room_extended": "room_temperature + extended_temperature rows, grouped 10x5",
    "band_all": "every row incl. outside_declared_window, grouped 10x5 (W12 reference)",
    "single_row_298": "one row per compound, nearest 298.15 K, grouped 10x5 (W12 control)",
    "train_all_test_core": (
        "train on every band, score on room+extended only; same folds and same "
        "scored rows as band_room_extended"
    ),
}

#: (protocol in this probe, protocol in the W12 grouped benchmark) pairs that must
#: reproduce exactly, because they are the same computation on the same rows.
GROUPED_REFERENCE_PAIRS = (
    ("band_all", "grouped"),
    ("single_row_298", "grouped_single_row"),
)

def band_of(row: Mapping[str, object]) -> str:
    return str(row["temperature_band"])


def read_grouped_reference() -> dict[str, object]:
    """Load the W12 grouped-benchmark summary this probe has to reproduce."""

    if not GROUPED_BENCHMARK_SUMMARY.is_file():
        return {}
    payload = json.loads(GROUPED_BENCHMARK_SUMMARY.read_text(encoding="utf-8"))
    if not payload.get("summary"):
        return {}
    return {
        "path": portable_relative_path(GROUPED_BENCHMARK_SUMMARY, root=REPOSITORY_ROOT),
        "rows": payload.get("rows"),
        "compounds": payload.get("compounds"),
        "protocols": payload.get("protocols"),
        "summary": payload["summary"],
    }


def read_frozen_endpoint() -> dict[str, object]:
    """Load the v1.0 frozen 236-compound endpoint this probe re-verifies."""

    if not REFERENCE_SUMMARY.is_file():
        return {}
    payload = json.loads(REFERENCE_SUMMARY.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    if not summary:
        return {}
    return {
        "path": portable_relative_path(REFERENCE_SUMMARY, root=REPOSITORY_ROOT),
        "reported": {
            representation: {
                metric: summary[representation][metric]
                for metric in ("r2", "mae")
                if metric in summary.get(representation, {})
            }
            for representation in REPRESENTATIONS
            if representation in summary
        },
    }


def band_inventory(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Count rows and compounds per band, plus the compound-level band mix."""

    row_counts = Counter(band_of(row) for row in rows)
    per_compound: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        per_compound[str(row["inchikey"])].add(band_of(row))
    unknown = {band: count for band, count in row_counts.items() if band not in BAND_ORDER}
    return {
        "rows": {band: int(row_counts.get(band, 0)) for band in BAND_ORDER},
        "unknown_band_rows": unknown,
        "compounds": {
            band: int(sum(1 for bands in per_compound.values() if band in bands))
            for band in BAND_ORDER
        },
        "total_rows": len(rows),
        "total_compounds": len(per_compound),
        "compounds_with_core_rows": int(
            sum(1 for bands in per_compound.values() if bands & set(CORE_BANDS))
        ),
        "compounds_outside_only": sorted(
            inchikey for inchikey, bands in per_compound.items() if bands == {OUTSIDE_BAND}
        ),
        "core_bands": list(CORE_BANDS),
    }


def effective_repeats(
    n_compounds: int,
    *,
    n_splits: int = N_SPLITS,
    requested: int = N_REPEATS,
) -> tuple[int, str]:
    """Cap the repeat count at what the compound pool can actually support.

    Grouped K-fold needs at least `n_splits` distinct compounds to fill every
    fold, and this probe refuses to pretend it ran a protocol it could not fill.
    A pool thinner than that returns 0 repeats and the caller records the
    protocol as not run instead of emitting an empty table.
    """

    if n_compounds < n_splits:
        return 0, (
            f"not run: {n_compounds} compounds cannot fill {n_splits} grouped folds"
        )
    supportable = max(1, n_compounds // n_splits)
    if supportable < requested:
        return supportable, (
            f"reduced from {requested} to {supportable} repeats: "
            f"{n_compounds} compounds / {n_splits} folds"
        )
    return requested, ""

def drop_thin_folds(
    splits: Iterable[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    min_test_rows: int = MIN_TEST_ROWS_PER_FOLD,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """Skip folds whose scored set is too small for the metrics to be defined."""

    for repeat, fold, train_index, test_index in splits:
        if test_index.size < min_test_rows:
            continue
        yield repeat, fold, train_index, test_index


def core_test_splits(
    all_rows: Sequence[Mapping[str, object]],
    core_rows: Sequence[Mapping[str, object]],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """Yield train/test indices into the *all-rows* matrix for protocol 5.

    Fold membership is dealt over the core-band compounds only, so the held-out
    compound set (and therefore the scored rows) is exactly the one protocol 2
    uses. Training is then widened to every row of every *other* compound, which
    is what makes protocol 2 -> 5 a one-variable comparison.

    Out-of-core rows of a held-out compound are removed together with its core
    rows, so the widening cannot leak a compound across the fold boundary.
    Compounds that only ever appear outside the window are training-only: they
    are in every fold's train side and in no fold's test side, and are reported
    as such rather than silently dropped.
    """

    all_groups = np.asarray([str(row["inchikey"]) for row in all_rows])
    all_bands = np.asarray([band_of(row) for row in all_rows])
    core_mask = np.isin(all_bands, list(CORE_BANDS))
    core_positions = np.flatnonzero(core_mask)
    if core_positions.size != len(core_rows):
        raise ValueError(
            "core_rows must be exactly the core-band rows of all_rows "
            f"({core_positions.size} core rows found, {len(core_rows)} given)"
        )
    for position, row in zip(core_positions, core_rows, strict=True):
        if str(row["inchikey"]) != str(all_rows[int(position)]["inchikey"]):
            raise ValueError("core_rows order does not match the all-rows order")

    core_group_array = np.asarray([str(row["inchikey"]) for row in core_rows])
    for repeat, fold, _core_train, core_test in grouped_folds(
        list(core_group_array),
        n_splits=n_splits,
        n_repeats=n_repeats,
        seed=seed,
    ):
        held_out = np.unique(core_group_array[core_test])
        test_index = core_positions[core_test]
        train_index = np.flatnonzero(~np.isin(all_groups, held_out))
        yield repeat, fold, train_index, test_index


def audit_folds(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    groups: Sequence[str],
    bands: Sequence[str],
    core_bands: Sequence[str] = CORE_BANDS,
) -> dict[str, object]:
    """Re-derive the grouped contract from the fold indices that were run.

    The counters are recomputed from the index arrays rather than trusted from
    the splitter, so a splitter that quietly split a compound would be caught.
    """

    group_array = np.asarray(groups)
    band_array = np.asarray(bands)
    core_mask = np.isin(band_array, list(core_bands))
    straddling: list[int] = []
    test_rows = 0
    test_rows_outside_core = 0
    held_out_compounds = 0
    out_of_core_train_rows = 0
    out_of_core_train_rows_dropped = 0
    for _repeat, _fold, train_index, test_index in splits:
        test_groups = np.unique(group_array[test_index])
        overlap = np.intersect1d(group_array[train_index], test_groups)
        straddling.append(int(overlap.size))
        test_rows += int(test_index.size)
        test_rows_outside_core += int((~core_mask[test_index]).sum())
        held_out_compounds += int(test_groups.size)
        eligible = np.flatnonzero(
            ~np.isin(group_array, test_groups) & ~core_mask
        )
        out_of_core_train_rows += int(eligible.size)
        out_of_core_train_rows_dropped += int((~np.isin(eligible, train_index)).sum())
    return {
        "folds": len(splits),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
        "test_rows": test_rows,
        "test_rows_outside_core_bands": test_rows_outside_core,
        "held_out_compound_instances": held_out_compounds,
        "out_of_core_train_rows_available": out_of_core_train_rows,
        "out_of_core_train_rows_not_used": out_of_core_train_rows_dropped,
    }

def _build_plan(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """Materialise each protocol's row pool and its role."""

    core_rows = [row for row in rows if band_of(row) in CORE_BANDS]
    return {
        "band_room_only": {
            "mode": "own",
            "rows": [row for row in rows if band_of(row) == ROOM_BAND],
        },
        "band_room_extended": {"mode": "own", "rows": core_rows},
        "band_all": {"mode": "own", "rows": list(rows)},
        "single_row_298": {"mode": "own", "rows": select_one_row_per_compound(rows)},
        "train_all_test_core": {
            "mode": "core_test",
            "rows": list(rows),
            "core_rows": core_rows,
        },
    }


def run_band_ablation(
    rows: Sequence[Mapping[str, object]],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Run all five band protocols and return everything needed to report them."""

    plan = _build_plan(rows)
    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    audits: dict[str, object] = {}
    protocol_meta: dict[str, dict[str, object]] = {}

    for protocol in BAND_PROTOCOLS:
        entry = plan[protocol]
        protocol_rows = entry["rows"]
        morgan, physical, target, temperatures, groups = build_matrices(protocol_rows)
        bands = [band_of(row) for row in protocol_rows]
        compounds = len(set(groups))
        repeats, note = effective_repeats(
            compounds, n_splits=n_splits, requested=n_repeats
        )
        if repeats == 0:
            protocol_meta[protocol] = {
                "description": PROTOCOL_DESCRIPTIONS[protocol],
                "mode": entry["mode"],
                "rows": len(protocol_rows),
                "compounds": compounds,
                "requested_repeats": n_repeats,
                "executed_repeats": 0,
                "folds": 0,
                "train_rows_mean": None,
                "train_compounds_mean": None,
                "test_rows_mean": None,
                "test_compounds_mean": None,
                "note": note,
            }
            audits[protocol] = {
                **audit_folds((), groups=groups, bands=bands),
                "note": note,
            }
            continue

        if entry["mode"] == "own":
            raw_splits = grouped_folds(
                groups, n_splits=n_splits, n_repeats=repeats, seed=seed
            )
        else:
            raw_splits = core_test_splits(
                protocol_rows,
                entry["core_rows"],
                n_splits=n_splits,
                n_repeats=repeats,
                seed=seed,
            )
        splits = list(drop_thin_folds(raw_splits))
        if not splits:
            raise ValueError(f"{protocol}: no fold survived the thin-fold filter")
        audit = audit_folds(splits, groups=groups, bands=bands)
        if audit["folds_with_a_straddling_compound"]:
            raise ValueError(f"{protocol}: a compound straddles the fold boundary")
        audits[protocol] = audit

        folds, repeat_items, predictions, _leak = run_protocol(
            protocol,
            iter(splits),
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
        )
        fold_rows.extend(folds)
        repeat_rows.extend(repeat_items)
        prediction_rows.extend(predictions)

        group_array = np.asarray(groups)
        protocol_meta[protocol] = {
            "description": PROTOCOL_DESCRIPTIONS[protocol],
            "mode": entry["mode"],
            "rows": len(protocol_rows),
            "compounds": compounds,
            "requested_repeats": n_repeats,
            "executed_repeats": repeats,
            "folds": len(splits),
            "train_rows_mean": float(np.mean([item[2].size for item in splits])),
            "train_compounds_mean": float(
                np.mean([np.unique(group_array[item[2]]).size for item in splits])
            ),
            "test_rows_mean": float(np.mean([item[3].size for item in splits])),
            "test_compounds_mean": float(
                np.mean([np.unique(group_array[item[3]]).size for item in splits])
            ),
            "note": note,
        }

    pooled, pooled_per_repeat = pooled_metrics(prediction_rows)
    return {
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summarize_repeats(repeat_rows),
        "audits": audits,
        "protocols": protocol_meta,
        "pooled": pooled,
        "pooled_per_repeat": pooled_per_repeat,
        "scoring_side_decomposition": scoring_side_decomposition(pooled_per_repeat),
    }

def classify(value: float, *, tolerance: float = INERT_TOLERANCE) -> str:
    if value > tolerance:
        return "helps"
    if value < -tolerance:
        return "hurts"
    return "inert"


def mechanism_decomposition(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    *,
    core: str = "band_room_extended",
    trained: str = "train_all_test_core",
    scored: str = "band_all",
    representation: str = HYBRID,
    tolerance: float = INERT_TOLERANCE,
) -> dict[str, object]:
    """Split the core -> all-bands R2 gap into a training and a scoring term.

    `core -> trained` varies only the training rows (the scored rows are
    identical), and `trained -> scored` varies only the scored rows (the
    training rows are identical), so the two deltas add up to the W12 gap.
    """

    missing = [name for name in (core, trained, scored) if name not in summary]
    if missing:
        return {"available": False, "missing": missing}
    values = {
        name: float(summary[name][representation]["r2"]["mean"])
        for name in (core, trained, scored)
    }
    mae = {
        name: float(summary[name][representation]["mae"]["mean"])
        for name in (core, trained, scored)
    }
    training_delta = values[trained] - values[core]
    scoring_delta = values[scored] - values[trained]
    return {
        "available": True,
        "representation": representation,
        "r2": values,
        "mae": mae,
        "training_side_delta_r2": training_delta,
        "training_side_verdict": classify(training_delta, tolerance=tolerance),
        "scoring_side_delta_r2": scoring_delta,
        "scoring_side_verdict": classify(scoring_delta, tolerance=tolerance),
        "total_delta_r2": values[scored] - values[core],
        "tolerance": tolerance,
    }


def compare_grouped_reference(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    reference: Mapping[str, object],
) -> dict[str, object]:
    """Check that the two shared protocols reproduce the W12 numbers exactly."""

    reference_summary = reference.get("summary") or {}
    comparisons: dict[str, object] = {}
    for mine, theirs in GROUPED_REFERENCE_PAIRS:
        if not reference_summary or theirs not in reference_summary or mine not in summary:
            comparisons[mine] = {
                "reference_protocol": theirs,
                "available": False,
                "bit_exact": None,
            }
            continue
        per_representation: dict[str, object] = {}
        for representation in REPRESENTATIONS:
            # A representation absent from either side is skipped rather than
            # guessed at, so a partial summary cannot masquerade as a match.
            if representation not in summary[mine]:
                continue
            reference_metrics = reference_summary[theirs].get(representation)
            if not reference_metrics:
                continue
            mine_metrics = summary[mine][representation]
            deltas = {
                metric: float(mine_metrics[metric]["mean"])
                - float(reference_metrics[metric]["mean"])
                for metric in METRIC_NAMES
                if reference_metrics.get(metric, {}).get("mean") is not None
            }
            per_representation[representation] = {
                "deltas": deltas,
                "max_abs_delta": max((abs(value) for value in deltas.values()), default=0.0),
                "bit_exact": all(value == 0.0 for value in deltas.values()),
            }
        comparisons[mine] = {
            "reference_protocol": theirs,
            "available": True,
            "representations": per_representation,
            "bit_exact": bool(per_representation)
            and all(bool(item["bit_exact"]) for item in per_representation.values()),
        }
    return comparisons


#: Metrics the frozen endpoint rewrite is diffed on.
FROZEN_ENDPOINT_METRICS = ("r2", "mae")

#: Metrics recomputed from pooled out-of-fold predictions. `pool_variance` is
#: the variance of the scored target pool, i.e. the denominator of R^2.
POOLED_METRIC_NAMES = ("r2", "mae", "rmse", "mse", "pool_variance")


def compare_frozen_endpoint(
    observed: Mapping[str, Mapping[str, float]],
    reported: Mapping[str, object],
) -> dict[str, object]:
    """Diff a frozen-endpoint replay against the numbers it has to reproduce.

    Keeping this pure means the comparison can be exercised offline with
    synthetic numbers instead of paying for a 236-compound replay in tests.
    """

    reported_values = reported.get("reported") or {}
    comparisons: dict[str, object] = {}
    max_abs_delta = 0.0
    for representation in REPRESENTATIONS:
        entry = reported_values.get(representation, {})
        if not entry:
            continue
        deltas = {
            metric: float(observed[representation][metric]) - float(entry[metric]["mean"])
            for metric in FROZEN_ENDPOINT_METRICS
            if entry.get(metric, {}).get("mean") is not None
        }
        max_abs_delta = max(
            max_abs_delta, max((abs(value) for value in deltas.values()), default=0.0)
        )
        comparisons[representation] = {
            "observed": {
                metric: float(observed[representation][metric])
                for metric in FROZEN_ENDPOINT_METRICS
            },
            "reported": {
                metric: float(entry[metric]["mean"])
                for metric in FROZEN_ENDPOINT_METRICS
                if entry.get(metric, {}).get("mean") is not None
            },
            "deltas": deltas,
        }
    return {
        "representations": comparisons,
        "max_abs_delta": max_abs_delta,
        "bit_exact": bool(comparisons) and max_abs_delta == 0.0,
    }


def pooled_metrics(
    prediction_rows: Sequence[Mapping[str, object]],
    *,
    representation: str = HYBRID,
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, float]]]]:
    """Recompute per-repeat metrics from the pooled OOF predictions.

    The headline numbers in `summary` are means of per-repeat metrics. Pooling
    the same predictions again puts `mse` and `pool_variance` side by side,
    which is what makes the R^2 denominator visible: `R2 = 1 - MSE / Var(target)`
    and the scored pool is not the same size between protocols.
    """

    grouped: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
    for row in prediction_rows:
        if str(row["representation"]) != representation:
            continue
        grouped[(str(row["protocol"]), int(row["repeat"]))].append(row)
    per_repeat: dict[str, list[dict[str, float]]] = defaultdict(list)
    for (protocol, repeat), items in sorted(grouped.items()):
        target = np.asarray([float(str(item["target"])) for item in items], dtype=float)
        prediction = np.asarray(
            [float(str(item["prediction"])) for item in items], dtype=float
        )
        residual = target - prediction
        mse = float(np.mean(residual**2))
        variance = float(np.var(target))
        per_repeat[protocol].append(
            {
                "repeat": float(repeat),
                "rows": float(target.size),
                "mse": mse,
                "mae": float(np.mean(np.abs(residual))),
                "rmse": float(np.sqrt(mse)),
                "pool_variance": variance,
                "r2": float(1.0 - mse / variance) if variance > 0.0 else float("nan"),
            }
        )
    aggregate: dict[str, dict[str, object]] = {}
    for protocol, items in sorted(per_repeat.items()):
        row_counts = sorted({int(item["rows"]) for item in items})
        aggregate[protocol] = {
            "rows": row_counts[0] if len(row_counts) == 1 else None,
            "repeats": len(items),
            **{
                metric: float(np.mean([item[metric] for item in items]))
                for metric in POOLED_METRIC_NAMES
            },
        }
    return aggregate, {key: list(value) for key, value in per_repeat.items()}


def scoring_side_decomposition(
    per_repeat: Mapping[str, Sequence[Mapping[str, float]]],
    *,
    core: str = "train_all_test_core",
    scored: str = "band_all",
) -> dict[str, object]:
    """Split a cross-pool R^2 gap into a squared-error and a denominator term.

    `core` and `scored` are the *same models* applied to two scored pools: the
    probe gives them identical folds and identical training rows, and the
    delivered predictions confirm it cell by cell. So the whole gap is pool
    composition, and with `R2 = 1 - MSE / Var` it decomposes exactly as

        R2_scored - R2_core = (MSE_core - MSE_scored) / Var_scored
                              + MSE_core * (1/Var_scored - 1/Var_core)

    The first term answers the honest denominator-free question - was the wider
    pool predicted better or worse? - and the second is pure R^2 arithmetic that
    fires whenever the scored pool gets narrower or wider.
    """

    core_records = {int(item["repeat"]): item for item in per_repeat.get(core, [])}
    scored_records = {int(item["repeat"]): item for item in per_repeat.get(scored, [])}
    repeats = sorted(set(core_records) & set(scored_records))
    if not repeats:
        return {"available": False, "core": core, "scored": scored}
    squared_error_effects: list[float] = []
    denominator_effects: list[float] = []
    for repeat in repeats:
        core_row = core_records[repeat]
        scored_row = scored_records[repeat]
        squared_error_effects.append(
            (float(core_row["mse"]) - float(scored_row["mse"]))
            / float(scored_row["pool_variance"])
        )
        denominator_effects.append(
            float(core_row["mse"]) / float(core_row["pool_variance"])
            - float(core_row["mse"]) / float(scored_row["pool_variance"])
        )
    r2_core = float(np.mean([core_records[repeat]["r2"] for repeat in repeats]))
    r2_scored = float(np.mean([scored_records[repeat]["r2"] for repeat in repeats]))
    squared_error_effect = float(np.mean(squared_error_effects))
    denominator_effect = float(np.mean(denominator_effects))
    return {
        "available": True,
        "core": core,
        "scored": scored,
        "repeats": len(repeats),
        "rows_core": core_records[repeats[0]]["rows"],
        "rows_scored": scored_records[repeats[0]]["rows"],
        "r2_core": r2_core,
        "r2_scored": r2_scored,
        "delta_r2": r2_scored - r2_core,
        "mse_core": float(np.mean([core_records[r]["mse"] for r in repeats])),
        "mse_scored": float(np.mean([scored_records[r]["mse"] for r in repeats])),
        "mae_core": float(np.mean([core_records[r]["mae"] for r in repeats])),
        "mae_scored": float(np.mean([scored_records[r]["mae"] for r in repeats])),
        "pool_variance_core": float(
            np.mean([core_records[r]["pool_variance"] for r in repeats])
        ),
        "pool_variance_scored": float(
            np.mean([scored_records[r]["pool_variance"] for r in repeats])
        ),
        "squared_error_effect": squared_error_effect,
        "denominator_effect": denominator_effect,
        "identity_residual": (r2_scored - r2_core)
        - (squared_error_effect + denominator_effect),
        "reading": (
            "squared_error_effect > 0 means the wider pool is predicted MORE "
            "accurately; a negative denominator_effect is pure R^2 arithmetic "
            "from the smaller scored-pool variance"
        ),
    }


def verify_frozen_endpoint(
    *,
    features_path: Path = FROZEN_FEATURES_PATH,
    dataset_path: Path = DATASET_PATH,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Replay the v1.0 236-compound RepeatedKFold endpoint on the frozen table.

    This is the coverage-curve probe's protocol, re-run here so this report can
    state its own reproduction result instead of quoting one.
    """

    rows, failed_rows, withheld_rows = read_modelling_rows(
        features_path, dataset_path=dataset_path
    )
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([str(row["smiles"]) for row in rows])
    physical = physical_feature_matrix(rows)
    splitter = RepeatedKFold(
        n_splits=N_SPLITS, n_repeats=n_repeats, random_state=seed
    )
    observed: dict[str, dict[str, float]] = {}
    for representation in REPRESENTATIONS:
        fold_winners = [np.full(len(rows), np.nan) for _ in range(n_repeats)]
        for index, (train_indices, test_indices) in enumerate(
            splitter.split(np.zeros(len(rows)))
        ):
            prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_indices,
                test_indices=test_indices,
                seed=seed + index,
            )
            fold_winners[index // N_SPLITS][test_indices] = prediction
        repeats = [evaluate_repeat(target, values) for values in fold_winners]
        observed[representation] = {
            "r2": float(np.mean([item["r2"] for item in repeats])),
            "mae": float(np.mean([item["mae"] for item in repeats])),
        }
    reported = read_frozen_endpoint()
    comparison = compare_frozen_endpoint(observed, reported)
    return {
        "rows": len(rows),
        "failed_rows": len(failed_rows),
        "withheld_rows": len(withheld_rows),
        "n_repeats": n_repeats,
        "protocol": "v1.0 RepeatedKFold(5x10, seed=42) over the frozen 236-compound table",
        "reference_path": reported.get("path"),
        **comparison,
    }

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--splits", type=int, default=N_SPLITS)
    parser.add_argument("--repeats", type=int, default=N_REPEATS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--skip-frozen-endpoint",
        action="store_true",
        help="skip the 236-compound v1.0 replay used to re-verify the frozen endpoint",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rows, _features, dropped = load_table(args.observations, args.features)
    result = run_band_ablation(
        rows, n_splits=args.splits, n_repeats=args.repeats, seed=args.seed
    )
    summary = result["summary"]

    grouped_reference = read_grouped_reference()
    reproduction = compare_grouped_reference(summary, grouped_reference)
    mechanism = {
        **mechanism_decomposition(summary),
        "pooled_metrics": result["pooled"],
        "scoring_side_decomposition": result["scoring_side_decomposition"],
    }
    frozen_endpoint = (
        {} if args.skip_frozen_endpoint else verify_frozen_endpoint(n_repeats=args.repeats)
    )

    args.artifacts.mkdir(parents=True, exist_ok=True)
    folds_path = args.artifacts / "dielectric_band_ablation_folds.csv"
    repeats_path = args.artifacts / "dielectric_band_ablation_repeats.csv"
    predictions_path = args.artifacts / "dielectric_band_ablation_predictions.csv"
    write_csv_rows(folds_path, FOLD_COLUMNS, result["fold_rows"])
    write_csv_rows(
        repeats_path, ("protocol", "representation", "repeat", *METRIC_NAMES), result["repeat_rows"]
    )
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, result["prediction_rows"])

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
        },
        "inputs": {
            "observations": portable_relative_path(args.observations, root=REPOSITORY_ROOT),
            "observations_sha256": canonical_text_sha256(args.observations),
            "features": portable_relative_path(args.features, root=REPOSITORY_ROOT),
            "features_sha256": canonical_text_sha256(args.features),
        },
        "dropped": dropped,
        "band_inventory": band_inventory(rows),
        "protocols": result["protocols"],
        "audits": result["audits"],
        "summary": summary,
        "mechanism": mechanism,
        "reference": {
            "grouped_benchmark": grouped_reference,
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

    print(f"rows {len(rows)} across {band_inventory(rows)['total_compounds']} compounds")
    for protocol in BAND_PROTOCOLS:
        meta = result["protocols"][protocol]
        if not meta["executed_repeats"]:
            print(f"  {protocol:20s}: NOT RUN ({meta['note']})")
            continue
        line = ", ".join(
            f"{name} R2={summary[protocol][name]['r2']['mean']:.4f}"
            f" MAE={summary[protocol][name]['mae']['mean']:.4f}"
            for name in REPRESENTATIONS
        )
        print(
            f"  {protocol:20s}: rows={meta['rows']:5d} compounds={meta['compounds']:4d} "
            f"test_rows/fold={meta['test_rows_mean']:.1f} | {line}"
        )
    if mechanism.get("available"):
        print(
            "mechanism (hybrid R2): "
            f"core={mechanism['r2']['band_room_extended']:.4f} -> "
            f"train_all={mechanism['r2']['train_all_test_core']:.4f} "
            f"({mechanism['training_side_verdict']}, "
            f"{mechanism['training_side_delta_r2']:+.4f}) -> "
            f"score_all={mechanism['r2']['band_all']:.4f} "
            f"({mechanism['scoring_side_verdict']}, "
            f"{mechanism['scoring_side_delta_r2']:+.4f})"
        )
    decomposition = mechanism["scoring_side_decomposition"]
    if decomposition.get("available"):
        print(
            "scoring-side split (hybrid): "
            f"dR2={decomposition['delta_r2']:+.4f} = "
            f"squared-error {decomposition['squared_error_effect']:+.4f} "
            f"+ denominator {decomposition['denominator_effect']:+.4f} "
            f"| MSE {decomposition['mse_core']:.2f} -> {decomposition['mse_scored']:.2f} "
            f"| pool var {decomposition['pool_variance_core']:.2f} -> "
            f"{decomposition['pool_variance_scored']:.2f}"
        )
    for mine, comparison in reproduction.items():
        if comparison.get("available"):
            print(
                f"reproduce {mine} vs W12 {comparison['reference_protocol']}: "
                f"bit_exact={comparison['bit_exact']}"
            )
    if frozen_endpoint:
        print(
            f"frozen v1.0 endpoint replay: rows={frozen_endpoint['rows']} "
            f"bit_exact={frozen_endpoint['bit_exact']} "
            f"max_abs_delta={frozen_endpoint['max_abs_delta']:.3e}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
