"""Pre-registered leave-EC-out sensitivity probe (D1, v0.3.14).

Why EC needs this probe
-----------------------
`data/dielectric_v03.csv` carries exactly one row outside the primary
near-room window (293.15-303.15 K): ethylene carbonate (EC), stored as
``epsilon = 90.5`` at 313.15 K and labelled ``temperature_band =
extended_temperature``.  EC melts at about 36.4 C, so no room-temperature
liquid measurement of the pure compound exists, and the row is kept rather
than dropped.  The open question a reviewer will ask is whether that single
out-of-window row is doing hidden work inside the frozen benchmark.

Pre-registered decision rule (written before the probe was first run)
--------------------------------------------------------------------
This is a robustness/disclosure probe, not a model-selection procedure.

* The v1.0 configuration stays what ``probes/v032_ablation_summary.json``
  freezes: Morgan / Physical / equal-weight Hybrid, XGBRegressor with the
  recorded parameters, ``RepeatedKFold(n_splits=5, n_repeats=10,
  random_state=42)``.
* Removing EC may be reported as a sensitivity limitation, but it cannot
  trigger a post-hoc model switch, a feature change or a dataset revision.
* Any actual change requires a separate pre-registered v1.1 revision.

Design
------
* Baseline arm: train on the full 236-row frozen training folds and predict
  the held-out fold, reproducing the frozen benchmark exactly.
* Treatment arm: identical folds, identical seeds, but EC is deleted from
  every training fold.  The other 235 compounds therefore keep byte-identical
  fold geometry, and every metric delta is attributable to EC alone.
* EC itself is scored out-of-fold in every repeat, because it is held out
  exactly once per repeat.

The probe writes only ``probes/dielectric_leave_ec_out_summary.json``,
``probes/artifacts/dielectric_leave_ec_out_predictions.csv`` and
``probes/artifacts/dielectric_leave_ec_out.png``.  No dataset cell is touched.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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
    read_csv_rows,
    read_modelling_rows,
    write_csv_rows,
)
from sklearn.model_selection import RepeatedKFold
from v032_controlled_comparison import _paired_stats

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_NAME = "ethylene carbonate"
EXPECTED_COMPOUND_COUNT = 236
EXPECTED_REMAINING_COUNT = 235

FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
EXCLUSIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_v03_exclusions.csv"
FROZEN_PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "v032_ablation_predictions.csv"
)
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_leave_ec_out_summary.json"
PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_leave_ec_out_predictions.csv"
)
PLOT_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_leave_ec_out.png"

PAIRED_METRICS = ("r2", "mae", "rmse", "spearman")
PREDICTION_COLUMNS = (
    "representation",
    "repeat",
    "fold",
    "arm",
    "inchikey",
    "name",
    "target",
    "prediction",
)


def _fold_index_map(rows: Sequence[Mapping[str, str]]) -> dict[tuple[str, int], int]:
    """Return {(inchikey, repeat): fold} for the frozen 236-row row order."""

    splitter = RepeatedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    assignment: dict[tuple[str, int], int] = {}
    for split_index, (_, test_indices) in enumerate(
        splitter.split(np.zeros(len(rows)))
    ):
        fold = split_index % N_SPLITS
        repeat = split_index // N_SPLITS
        for row_index in test_indices:
            assignment[(rows[int(row_index)]["inchikey"], repeat)] = fold
    return assignment


def _rank_percentile(values: np.ndarray, value: float) -> float:
    """Fraction of `values` at or below `value`, in percent."""

    return float(100.0 * np.mean(np.asarray(values, dtype=float) <= float(value)))


def run_probe(
    *,
    features_path: Path = FEATURES_PATH,
    dataset_path: Path = DATASET_PATH,
    exclusions_path: Path = EXCLUSIONS_PATH,
    frozen_predictions_path: Path = FROZEN_PREDICTIONS_PATH,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    rows, failed_rows, withheld_rows = read_modelling_rows(
        features_path,
        dataset_path=dataset_path,
    )
    source_rows = read_csv_rows(dataset_path)
    exclusions = read_csv_rows(exclusions_path) if exclusions_path.is_file() else []

    count = len(rows)
    if count != EXPECTED_COMPOUND_COUNT:
        raise ValueError(
            f"expected {EXPECTED_COMPOUND_COUNT} modelling rows, found {count}"
        )
    keys = [row["inchikey"] for row in rows]
    if keys.count(EC_INCHIKEY) != 1:
        raise ValueError("the frozen benchmark must contain exactly one EC row")
    ec_index = keys.index(EC_INCHIKEY)
    if rows[ec_index]["name"] != EC_NAME:
        raise ValueError(f"unexpected EC row name: {rows[ec_index]['name']!r}")

    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    physical = physical_feature_matrix(rows)

    keep = np.ones(count, dtype=bool)
    keep[ec_index] = False
    if int(keep.sum()) != EXPECTED_REMAINING_COUNT:
        raise ValueError("the leave-EC-out subset must hold 235 compounds")

    baseline: dict[tuple[int, str], np.ndarray] = {
        (repeat, representation): np.full(count, np.nan)
        for repeat in range(N_REPEATS)
        for representation in REPRESENTATIONS
    }
    treatment: dict[tuple[int, str], np.ndarray] = {
        (repeat, representation): np.full(count, np.nan)
        for repeat in range(N_REPEATS)
        for representation in REPRESENTATIONS
    }
    fold_of: dict[tuple[str, int], int] = {}
    prediction_rows: list[dict[str, object]] = []
    seed_of_split: dict[tuple[int, str], int] = {}
    ec_train_removals = 0

    splitter = RepeatedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    for split_index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(count))
    ):
        fold = split_index % N_SPLITS
        repeat = split_index // N_SPLITS
        seed = SEED + split_index
        for row_index in test_indices:
            fold_of[(rows[int(row_index)]["inchikey"], repeat)] = fold
        ec_in_test = bool(ec_index in set(test_indices.tolist()))
        train_without_ec = train_indices[train_indices != ec_index]
        expected_train = len(train_indices) - (0 if ec_in_test else 1)
        if len(train_without_ec) != expected_train:
            raise ValueError("EC removal changed the training set by the wrong amount")
        if ec_index in set(train_without_ec.tolist()):
            raise ValueError("EC survived into a treatment training fold")
        if not ec_in_test:
            ec_train_removals += 1
        for representation in REPRESENTATIONS:
            seed_of_split[(repeat, representation)] = seed
            base_prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_indices,
                test_indices=test_indices,
                seed=seed,
            )
            treat_prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_without_ec,
                test_indices=test_indices,
                seed=seed,
            )
            baseline[(repeat, representation)][test_indices] = base_prediction
            treatment[(repeat, representation)][test_indices] = treat_prediction
            for row_index, base_value, treat_value in zip(
                test_indices, base_prediction, treat_prediction, strict=True
            ):
                row = rows[int(row_index)]
                for arm, value in (("baseline", base_value), ("leave_ec_out", treat_value)):
                    prediction_rows.append(
                        {
                            "representation": representation,
                            "repeat": repeat,
                            "fold": fold,
                            "arm": arm,
                            "inchikey": row["inchikey"],
                            "name": row["name"],
                            "target": f"{target[row_index]:.12g}",
                            "prediction": f"{float(value):.12g}",
                        }
                    )
        print(
            json.dumps(
                {
                    "repeat": repeat,
                    "fold": fold,
                    "seed": seed,
                    "ec_held_out": ec_in_test,
                }
            ),
            flush=True,
        )

    for key, values in list(baseline.items()) + list(treatment.items()):
        if not np.isfinite(values).all():
            raise ValueError(f"incomplete out-of-fold predictions for {key}")

    # Invariant 1: the baseline arm must reproduce the frozen benchmark.
    frozen_rows = read_csv_rows(frozen_predictions_path)
    frozen = {
        (row["representation"], int(row["repeat"]), row["inchikey"]): row["prediction"]
        for row in frozen_rows
    }
    mismatches: list[str] = []
    for (repeat, representation), values in baseline.items():
        for row_index, row in enumerate(rows):
            expected = frozen.get((representation, repeat, row["inchikey"]))
            if expected is None:
                mismatches.append(f"missing {representation}/{repeat}/{row['inchikey']}")
                continue
            if expected != f"{values[row_index]:.12g}":
                mismatches.append(
                    f"{representation}/{repeat}/{row['inchikey']}: "
                    f"{expected} != {values[row_index]:.12g}"
                )
    if mismatches:
        raise ValueError(
            "the baseline arm does not reproduce the frozen benchmark: "
            + "; ".join(mismatches[:5])
        )

    # Invariant 2: the fold geometry of the 235 surviving compounds is frozen.
    for repeat in range(N_REPEATS):
        for row in rows:
            if row["inchikey"] == EC_INCHIKEY:
                continue
            if (row["inchikey"], repeat) not in fold_of:
                raise ValueError(f"{row['inchikey']} has no fold in repeat {repeat}")

    # Per-representation metrics and paired deltas on the 235 surviving rows.
    metrics: dict[str, object] = {}
    ec_report: dict[str, object] = {}
    for representation in REPRESENTATIONS:
        base_235: list[dict[str, float]] = []
        treat_235: list[dict[str, float]] = []
        base_236: list[dict[str, float]] = []
        for repeat in range(N_REPEATS):
            base_values = baseline[(repeat, representation)]
            treat_values = treatment[(repeat, representation)]
            base_235.append(evaluate_repeat(target[keep], base_values[keep]))
            treat_235.append(evaluate_repeat(target[keep], treat_values[keep]))
            base_236.append(evaluate_repeat(target, base_values))
        paired = {
            metric: _paired_stats(
                [row[metric] for row in base_235],
                [row[metric] for row in treat_235],
            )
            for metric in PAIRED_METRICS
        }
        baseline_ranking = sorted(
            PAIRED_METRICS,
            key=lambda metric: (
                paired[metric]["baseline_mean"]
                if metric in ("mae", "rmse")
                else -paired[metric]["baseline_mean"]
            ),
        )
        treatment_ranking = sorted(
            PAIRED_METRICS,
            key=lambda metric: (
                paired[metric]["augmented_mean"]
                if metric in ("mae", "rmse")
                else -paired[metric]["augmented_mean"]
            ),
        )
        metrics[representation] = {
            "baseline_full_236": {
                metric: {
                    "mean": float(np.mean([row[metric] for row in base_236])),
                    "std": float(np.std([row[metric] for row in base_236], ddof=1)),
                }
                for metric in PAIRED_METRICS
            },
            "baseline_surviving_235": {
                metric: {
                    "mean": float(np.mean([row[metric] for row in base_235])),
                    "std": float(np.std([row[metric] for row in base_235], ddof=1)),
                }
                for metric in PAIRED_METRICS
            },
            "leave_ec_out_235": {
                metric: {
                    "mean": float(np.mean([row[metric] for row in treat_235])),
                    "std": float(np.std([row[metric] for row in treat_235], ddof=1)),
                }
                for metric in PAIRED_METRICS
            },
            "paired_leave_ec_out_minus_baseline_235": paired,
            "metric_ranking_baseline": baseline_ranking,
            "metric_ranking_leave_ec_out": treatment_ranking,
            "ranking_changed": baseline_ranking != treatment_ranking,
        }

        ec_values = np.asarray(
            [treatment[(repeat, representation)][ec_index] for repeat in range(N_REPEATS)],
            dtype=float,
        )
        survivor_mean_prediction = np.asarray(
            [
                float(np.mean([treatment[(repeat, representation)][i] for repeat in range(N_REPEATS)]))
                for i in range(count)
                if i != ec_index
            ],
            dtype=float,
        )
        ec_report[representation] = {
            "target": float(target[ec_index]),
            "prediction_mean": float(np.mean(ec_values)),
            "prediction_std": float(np.std(ec_values, ddof=1)),
            "prediction_min": float(np.min(ec_values)),
            "prediction_max": float(np.max(ec_values)),
            "abs_error_mean": float(np.mean(np.abs(ec_values - target[ec_index]))),
            "signed_error_mean": float(np.mean(ec_values - target[ec_index])),
            "rank_percentile_among_235": _rank_percentile(
                survivor_mean_prediction, float(np.mean(ec_values))
            ),
        }

    family_ranking: dict[str, object] = {}
    for arm, mean_key in (("baseline", "baseline_mean"), ("leave_ec_out", "augmented_mean")):
        family_ranking[arm] = {
            metric: sorted(
                REPRESENTATIONS,
                key=lambda representation: metrics[representation][
                    "paired_leave_ec_out_minus_baseline_235"
                ][metric][mean_key],
                reverse=metric in ("r2", "spearman"),
            )
            for metric in PAIRED_METRICS
        }
    family_ranking["changed"] = family_ranking["baseline"] != family_ranking["leave_ec_out"]

    payload: dict[str, object] = {
        "schema_version": 1,
        "probe": "dielectric_leave_ec_out_sensitivity",
        "preregistration": (
            "Report-only robustness probe. It cannot trigger a post-hoc model "
            "switch, feature change or dataset revision; the v1.0 configuration "
            "stays exactly what probes/v032_ablation_summary.json freezes."
        ),
        "selection_effect": "none",
        "model_selection_impact": "none",
        "removed_inchikey": EC_INCHIKEY,
        "removed_name": EC_NAME,
        "removed_temperature_K": float(
            next(row["T_K"] for row in rows if row["inchikey"] == EC_INCHIKEY)
        ),
        "removed_temperature_band": next(
            row["temperature_band"]
            for row in source_rows
            if row["inchikey"] == EC_INCHIKEY
        ),
        "fold_source": portable_relative_path(
            frozen_predictions_path, root=REPOSITORY_ROOT
        ),
        "fold_scheme": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
        "seed_scheme": "42 + global RepeatedKFold split index",
        "same_fold_ids_for_235": True,
        "ec_in_training_folds": 0,
        "ec_training_removals": ec_train_removals,
        "ec_holdout_repeats": N_REPEATS,
        "baseline_fit_count": count,
        "leave_ec_out_fit_count": count - 1,
        "baseline_matches_frozen_predictions": True,
        "frozen_prediction_rows_checked": len(frozen_rows),
        "failed_physical_feature_count": len(failed_rows),
        "withheld_not_model_ready_count": len(withheld_rows),
        "excluded_count": len({row["inchikey"] for row in exclusions}),
        "metrics": metrics,
        "family_ranking": family_ranking,
        "ec_leave_one_out": ec_report,
        "inputs": {
            "features_path": portable_relative_path(
                features_path, root=REPOSITORY_ROOT
            ),
            "features_sha256": canonical_text_sha256(features_path),
            "dataset_path": portable_relative_path(dataset_path, root=REPOSITORY_ROOT),
            "dataset_sha256": canonical_text_sha256(dataset_path),
            "exclusions_sha256": (
                canonical_text_sha256(exclusions_path)
                if exclusions_path.is_file()
                else None
            ),
            "frozen_predictions_path": portable_relative_path(
                frozen_predictions_path, root=REPOSITORY_ROOT
            ),
            "frozen_predictions_sha256": canonical_text_sha256(
                frozen_predictions_path
            ),
        },
        "outputs": {},
    }
    return payload, prediction_rows


def _write_plot(payload: Mapping[str, object], path: Path) -> None:
    metrics = payload["metrics"]
    ec = payload["ec_leave_one_out"]
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.4))

    positions = np.arange(len(REPRESENTATIONS))
    target_value = float(next(iter(ec.values()))["target"])
    for offset, representation in enumerate(REPRESENTATIONS):
        values = [
            metrics[representation]["paired_leave_ec_out_minus_baseline_235"]["r2"][
                "per_repeat_delta"
            ]
        ]
        axes[0].scatter(
            np.full(len(values[0]), offset),
            values[0],
            s=26,
            alpha=0.75,
            label=representation if offset == 0 else None,
        )
        axes[1].scatter(
            np.full(1, offset),
            [ec[representation]["prediction_mean"]],
            s=60,
            marker="D",
        )
        axes[1].errorbar(
            offset,
            ec[representation]["prediction_mean"],
            yerr=ec[representation]["prediction_std"],
            fmt="none",
            capsize=4,
        )
    axes[0].axhline(0.0, color="black", linewidth=1.0, linestyle="--")
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(REPRESENTATIONS, rotation=15)
    axes[0].set_ylabel("delta R2 (leave-EC-out - baseline)")
    axes[0].set_title("Paired per-repeat delta on the 235 surviving rows")
    axes[1].axhline(target_value, color="black", linewidth=1.0, linestyle="--")
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels(REPRESENTATIONS, rotation=15)
    axes[1].set_ylabel("predicted epsilon for EC")
    axes[1].set_title(
        f"EC out-of-fold prediction (stored value {target_value:g})"
    )
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _normalise_lf(path: Path) -> None:
    """Keep the tracked prediction table byte-stable across platforms."""

    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8", newline="\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSIONS_PATH)
    parser.add_argument(
        "--frozen-predictions", type=Path, default=FROZEN_PREDICTIONS_PATH
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument("--plot", type=Path, default=PLOT_PATH)
    return parser.parse_args()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args() if argv is None else _parse_args_from(argv)
    payload, prediction_rows = run_probe(
        features_path=args.features,
        dataset_path=args.dataset,
        exclusions_path=args.exclusions,
        frozen_predictions_path=args.frozen_predictions,
    )
    payload["outputs"] = {
        "summary_json": portable_relative_path(args.summary, root=REPOSITORY_ROOT),
        "predictions_csv": portable_relative_path(args.predictions, root=REPOSITORY_ROOT),
        "plot": portable_relative_path(args.plot, root=REPOSITORY_ROOT),
    }
    write_csv_rows(args.predictions, PREDICTION_COLUMNS, prediction_rows)
    _normalise_lf(args.predictions)
    _write_plot(payload, args.plot)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"summary": str(args.summary), "status": "written"}))
    return 0


def _parse_args_from(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSIONS_PATH)
    parser.add_argument(
        "--frozen-predictions", type=Path, default=FROZEN_PREDICTIONS_PATH
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument("--plot", type=Path, default=PLOT_PATH)
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    raise SystemExit(main())