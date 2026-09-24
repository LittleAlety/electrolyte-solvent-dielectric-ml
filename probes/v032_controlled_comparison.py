"""Controlled benchmark for the v0.3.2 PC/EC contribution.

The v0.3.2 ablation refits ``RepeatedKFold`` on the enlarged table.  That
reshuffles about half of the fold assignments relative to v0.3 and changes the
target variance of the evaluation set, so the raw version-to-version
R^2 jump cannot be attributed to the two new compounds.

This probe removes both confounds:

* the evaluated set is the frozen v0.3 table (234 eligible compounds) and the fold
  assignment is generated once, from the v0.3 row order, so both arms and
  all ten repeats score exactly the same compounds in exactly the same
  folds;
* propylene carbonate (PC) and ethylene carbonate (EC) are appended to the
  training folds only and never enter an evaluation fold.

All reported improvements are paired per-repeat deltas with a confidence
interval, a paired t-test and a Wilcoxon signed-rank test, and are
accompanied by MAE/RMSE/Spearman so that no single metric is cherry-picked.
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
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    _safe_spearman,
    evaluate_repeat,
    fit_predict_representation,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
    regression_metrics,
    write_csv_rows,
)
from scipy.stats import t as student_t
from scipy.stats import ttest_rel, wilcoxon
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PC_INCHIKEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"

METRIC_NAMES = ("r2", "mae", "rmse", "spearman")
REPEAT_COLUMNS = (
    "repeat",
    "representation",
    "arm",
    "fold",
    "mae",
    "rmse",
    "r2",
    "spearman",
    "train_count",
    "test_count",
)


def _fold_assignment(
    keys: Sequence[str],
    *,
    n_repeats: int = N_REPEATS,
    n_splits: int = N_SPLITS,
    seed: int = SEED,
) -> dict[tuple[str, int], int]:
    """Return {(inchikey, repeat): fold_id} for a fixed row order."""
    splitter = RepeatedKFold(
        n_splits=n_splits,
        n_repeats=n_repeats,
        random_state=seed,
    )
    assignment: dict[tuple[str, int], int] = {}
    for split_index, (_, test_indices) in enumerate(
        splitter.split(np.zeros(len(keys)))
    ):
        fold = split_index % n_splits
        repeat = split_index // n_splits
        for row_index in test_indices:
            assignment[(keys[int(row_index)], repeat)] = fold
    return assignment


def _paired_stats(baseline: Sequence[float], augmented: Sequence[float]) -> dict:
    """Paired delta statistics for augmented - baseline."""
    base = np.asarray(baseline, dtype=float)
    aug = np.asarray(augmented, dtype=float)
    if base.shape != aug.shape:
        raise ValueError("paired arrays must have the same length")
    delta = aug - base
    count = delta.size
    mean = float(np.mean(delta))
    std = float(np.std(delta, ddof=1)) if count > 1 else 0.0
    stderr = std / float(np.sqrt(count)) if count > 1 else 0.0
    half_width = (
        float(student_t.ppf(0.975, count - 1) * stderr) if count > 1 else 0.0
    )
    t_pvalue = float(ttest_rel(aug, base).pvalue) if count > 1 else float("nan")
    if count > 1 and np.any(delta != 0.0):
        wilcoxon_pvalue = float(wilcoxon(aug, base).pvalue)
    else:
        wilcoxon_pvalue = float("nan")
    return {
        "n_pairs": int(count),
        "baseline_mean": float(np.mean(base)),
        "augmented_mean": float(np.mean(aug)),
        "delta_mean": mean,
        "delta_std": std,
        "delta_ci95": [mean - half_width, mean + half_width],
        "paired_t_pvalue": t_pvalue,
        "wilcoxon_pvalue": wilcoxon_pvalue,
        "per_repeat_delta": [float(value) for value in delta],
    }


def _external_holdout(
    *,
    base: Sequence[Mapping[str, str]],
    extra: Sequence[Mapping[str, str]],
    representation: str,
    morgan_base: np.ndarray,
    physical_base: np.ndarray,
    target_base: np.ndarray,
    morgan_extra: np.ndarray,
    physical_extra: np.ndarray,
    target_extra: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Train on every v0.3 compound and predict the unseen PC/EC rows."""
    all_indices = np.arange(len(base))
    extra_indices = np.arange(len(extra))
    predictions: list[np.ndarray] = []
    for repeat in range(N_REPEATS):
        extra_prediction, _ = fit_predict_representation(
            representation,
            morgan=np.vstack([morgan_base, morgan_extra]),
            physical=np.vstack([physical_base, physical_extra]),
            target=np.concatenate([target_base, target_extra]),
            train_indices=all_indices,
            test_indices=len(base) + extra_indices,
            seed=SEED + repeat,
        )
        predictions.append(extra_prediction)
    stacked = np.vstack(predictions)
    return {
        row["inchikey"]: {
            "name": row["name"],
            "target": float(row["dielectric"]),
            "prediction_mean": float(np.mean(stacked[:, index])),
            "prediction_std": float(np.std(stacked[:, index], ddof=1)),
            "abs_error_mean": float(
                np.mean(np.abs(stacked[:, index] - float(row["dielectric"])))
            ),
        }
        for index, row in enumerate(extra)
    }


def run_comparison(
    *,
    base_features_path: Path,
    v032_features_path: Path,
    repeats_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict:
    base_rows, base_failed, base_withheld = read_modelling_rows(base_features_path)
    v032_rows, v032_failed, v032_withheld = read_modelling_rows(v032_features_path)
    base_keys = [row["inchikey"] for row in base_rows]
    v032_keys = [row["inchikey"] for row in v032_rows]
    if len(set(base_keys)) != len(base_keys):
        raise ValueError("duplicate inchikeys in the baseline feature table")
    if len(set(v032_keys)) != len(v032_keys):
        raise ValueError("duplicate inchikeys in the v0.3.2 feature table")

    extra_keys = [key for key in v032_keys if key not in set(base_keys)]
    if set(extra_keys) != {PC_INCHIKEY, EC_INCHIKEY}:
        raise ValueError(f"unexpected added compounds: {extra_keys}")
    extra_by_key = {row["inchikey"]: row for row in v032_rows}
    extra_rows = [extra_by_key[key] for key in extra_keys]

    target = np.asarray(
        [float(row["dielectric"]) for row in base_rows],
        dtype=float,
    )
    extra_target = np.asarray(
        [float(row["dielectric"]) for row in extra_rows],
        dtype=float,
    )
    morgan = morgan_count_features([row["smiles"] for row in base_rows])
    physical = physical_feature_matrix(base_rows)
    morgan_extra = morgan_count_features([row["smiles"] for row in extra_rows])
    physical_extra = physical_feature_matrix(extra_rows)

    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )
    splits = list(splitter.split(np.zeros(len(base_rows))))
    if len(splits) != N_SPLITS * N_REPEATS:
        raise ValueError("unexpected RepeatedKFold split count")

    extra_train_indices = np.arange(len(base_rows), len(base_rows) + len(extra_rows))

    repeat_rows: list[dict[str, object]] = []
    oof: dict[tuple[str, str, int], np.ndarray] = {}
    representatives = [*REPRESENTATIONS]
    for representation in representatives:
        for arm in ("baseline_v0.3", "augmented_pc_ec_train_only"):
            for repeat in range(N_REPEATS):
                oof[(representation, arm, repeat)] = np.full(len(base_rows), np.nan)

    for split_index, (train_indices, test_indices) in enumerate(splits):
        fold = split_index % N_SPLITS
        repeat = split_index // N_SPLITS
        for representation in representatives:
            baseline_prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_indices,
                test_indices=test_indices,
                seed=SEED + split_index,
            )
            augmented_prediction, _ = fit_predict_representation(
                representation,
                morgan=np.vstack([morgan, morgan_extra]),
                physical=np.vstack([physical, physical_extra]),
                target=np.concatenate([target, extra_target]),
                train_indices=np.concatenate([train_indices, extra_train_indices]),
                test_indices=test_indices,
                seed=SEED + split_index,
            )
            oof[(representation, "baseline_v0.3", repeat)][test_indices] = (
                baseline_prediction
            )
            oof[(representation, "augmented_pc_ec_train_only", repeat)][
                test_indices
            ] = augmented_prediction
            for arm, prediction, arm_train_count in (
                ("baseline_v0.3", baseline_prediction, len(train_indices)),
                (
                    "augmented_pc_ec_train_only",
                    augmented_prediction,
                    len(train_indices) + len(extra_rows),
                ),
            ):
                metrics = regression_metrics(target[test_indices], prediction)
                metrics["spearman"] = _safe_spearman(
                    target[test_indices], prediction
                )
                repeat_rows.append(
                    {
                        "repeat": repeat,
                        "representation": representation,
                        "arm": arm,
                        "fold": fold,
                        "mae": f"{metrics['mae']:.12g}",
                        "rmse": f"{metrics['rmse']:.12g}",
                        "r2": f"{metrics['r2']:.12g}",
                        "spearman": f"{metrics['spearman']:.12g}",
                        "train_count": arm_train_count,
                        "test_count": len(test_indices),
                    }
                )
        print(
            json.dumps(
                {"split": split_index, "repeat": repeat, "fold": fold},
                sort_keys=True,
            ),
            flush=True,
        )

    repeat_metrics: dict[str, dict[str, dict[str, list[float]]]] = {
        representation: {
            arm: {metric: [] for metric in METRIC_NAMES}
            for arm in ("baseline_v0.3", "augmented_pc_ec_train_only")
        }
        for representation in representatives
    }
    oof_rows: list[dict[str, object]] = []
    for representation in representatives:
        for repeat in range(N_REPEATS):
            for arm in ("baseline_v0.3", "augmented_pc_ec_train_only"):
                prediction = oof[(representation, arm, repeat)]
                if not np.isfinite(prediction).all():
                    raise ValueError(
                        f"incomplete OOF predictions for {representation}/{arm}/{repeat}"
                    )
                metrics = evaluate_repeat(target, prediction)
                for metric in METRIC_NAMES:
                    repeat_metrics[representation][arm][metric].append(
                        float(metrics[metric])
                    )
                for row_index, value in enumerate(prediction):
                    oof_rows.append(
                        {
                            "representation": representation,
                            "arm": arm,
                            "repeat": repeat,
                            "inchikey": base_rows[row_index]["inchikey"],
                            "name": base_rows[row_index]["name"],
                            "target": f"{target[row_index]:.12g}",
                            "prediction": f"{value:.12g}",
                        }
                    )

    paired: dict[str, dict[str, dict]] = {}
    for representation in representatives:
        paired[representation] = {
            metric: _paired_stats(
                repeat_metrics[representation]["baseline_v0.3"][metric],
                repeat_metrics[representation]["augmented_pc_ec_train_only"][metric],
            )
            for metric in METRIC_NAMES
        }

    base_assignment = _fold_assignment(base_keys)
    v032_assignment = _fold_assignment(v032_keys)
    shared = [key for key in v032_keys if key in set(base_keys)]
    total = len(shared) * N_REPEATS
    churned = sum(
        1
        for key in shared
        for repeat in range(N_REPEATS)
        if base_assignment.get((key, repeat)) != v032_assignment.get((key, repeat))
    )

    external: dict[str, dict] = {}
    for representation in representatives:
        external[representation] = _external_holdout(
            base=base_rows,
            extra=extra_rows,
            representation=representation,
            morgan_base=morgan,
            physical_base=physical,
            target_base=target,
            morgan_extra=morgan_extra,
            physical_extra=physical_extra,
            target_extra=extra_target,
        )

    payload = {
        "schema_version": 1,
        "design": {
            "question": "does adding PC/EC improve generalisation on v0.3 compounds?",
            "frozen_test_set": (
                f"the {len(base_rows)} v0.3 compounds that are model_ready=true "
                "and have usable physical features"
            ),
            "frozen_fold_source": "RepeatedKFold(5, 10, random_state=42) over the v0.3 row order",
            "added_to_training_only": sorted(extra_keys),
            "arms": ["baseline_v0.3", "augmented_pc_ec_train_only"],
            "pairing": "identical test compounds and identical folds in every repeat",
        },
        "inputs": {
            "baseline_features_path": portable_relative_path(
                base_features_path, root=REPOSITORY_ROOT
            ),
            "baseline_features_sha256": canonical_text_sha256(base_features_path),
            "v032_features_path": portable_relative_path(
                v032_features_path, root=REPOSITORY_ROOT
            ),
            "v032_features_sha256": canonical_text_sha256(v032_features_path),
        },
        "counts": {
            "baseline_compound_count": len(base_rows),
            "augmented_compound_count": len(base_rows) + len(extra_rows),
            "baseline_failed_feature_count": len(base_failed),
            "v032_failed_feature_count": len(v032_failed),
            "baseline_withheld_not_model_ready_count": len(base_withheld),
            "v032_withheld_not_model_ready_count": len(v032_withheld),
            "withheld_not_model_ready_names": sorted(
                {row["name"] for row in (*base_withheld, *v032_withheld)}
            ),
            "added_compound_keys": extra_keys,
        },
        "paired_deltas": paired,
        "fold_churn_diagnostic": {
            "note": (
                f"fold ids that differ between the {len(base_rows)}-row v0.3 split "
                f"and the {len(v032_rows)}-row v0.3.2 split, for shared compounds; "
                "this is why the raw version-to-version comparison is not "
                "controlled"
            ),
            "shared_compounds": len(shared),
            "shared_compound_repeat_pairs": total,
            "changed_fold_count": churned,
            "changed_fold_fraction": churned / total if total else None,
        },
        "pc_ec_external_holdout": external,
        "outputs": {
            "repeats_csv": portable_relative_path(repeats_path, root=REPOSITORY_ROOT),
            "summary_json": portable_relative_path(summary_path, root=REPOSITORY_ROOT),
            "oof_csv": portable_relative_path(
                repeats_path.with_name(f"{repeats_path.stem}_oof.csv"),
                root=REPOSITORY_ROOT,
            ),
            "plot": portable_relative_path(plot_path, root=REPOSITORY_ROOT),
        },
    }

    write_csv_rows(repeats_path, REPEAT_COLUMNS, repeat_rows)
    write_csv_rows(
        repeats_path.with_name(f"{repeats_path.stem}_oof.csv"),
        ("representation", "arm", "repeat", "inchikey", "name", "target", "prediction"),
        oof_rows,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(paired, plot_path)
    return payload


def _write_plot(paired: Mapping[str, Mapping[str, Mapping]], path: Path) -> None:
    metrics = ("r2", "mae", "rmse", "spearman")
    labels = list(paired.keys())
    colours = ("#2563eb", "#dc2626", "#059669")
    figure, axes = plt.subplots(1, len(metrics), figsize=(16.0, 4.2))
    for axis, metric in zip(axes, metrics, strict=True):
        means = [float(paired[name][metric]["delta_mean"]) for name in labels]
        errors = [
            float(paired[name][metric]["delta_ci95"][1])
            - float(paired[name][metric]["delta_mean"])
            for name in labels
        ]
        axis.bar(labels, means, yerr=errors, color=colours, capsize=3)
        axis.axhline(0.0, color="#111827", linewidth=0.9)
        axis.set_title(f"paired delta {metric}")
        axis.tick_params(axis="x", rotation=12)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("PC/EC added to training folds only (frozen v0.3 test set)")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-features",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "interim" / "v03_features_original.csv",
    )
    parser.add_argument(
        "--v032-features",
        type=Path,
        default=(
            REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
        ),
    )
    parser.add_argument(
        "--repeats-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "v032_controlled_comparison_repeats.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "v032_controlled_comparison_summary.json",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "v032_controlled_comparison.png",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_comparison(
        base_features_path=args.base_features,
        v032_features_path=args.v032_features,
        repeats_path=args.repeats_output,
        summary_path=args.summary_output,
        plot_path=args.plot_output,
    )
    compact = {
        representation: {
            metric: {
                "delta_mean": round(values["delta_mean"], 4),
                "ci95": [round(bound, 4) for bound in values["delta_ci95"]],
                "p": round(values["paired_t_pvalue"], 5),
            }
            for metric, values in metrics.items()
        }
        for representation, metrics in payload["paired_deltas"].items()
    }
    print(json.dumps(compact, indent=2))
    print(
        json.dumps(payload["fold_churn_diagnostic"], indent=2),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
