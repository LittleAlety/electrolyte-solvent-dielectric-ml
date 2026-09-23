"""Small-data MLP probes using the fixed dielectric CV splits."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import RepeatedKFold
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PREDICTION_COLUMNS,
    REPEAT_COLUMNS,
    SEED,
    evaluate_repeat,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
    write_csv_rows,
)

REPRESENTATIONS = (
    "MLP_Morgan",
    "MLP_Physical",
    "MLP_Hybrid",
)
XGBOOST_R2 = 0.32009889379719636
XGBOOST_SPEARMAN = 0.8299874869382549


def log_dielectric(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if np.any(values < 1.0):
        raise ValueError("dielectric values must be >= 1")
    return np.log(values - 1.0)


def inverse_log_dielectric(values: np.ndarray) -> np.ndarray:
    return np.maximum(np.exp(np.asarray(values, dtype=np.float64)) + 1.0, 1.0)


def _fit_predict(
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    scaler = StandardScaler()
    train = scaler.fit_transform(features[train_indices])
    test = scaler.transform(features[test_indices])
    model = MLPRegressor(
        hidden_layer_sizes=(64,),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        batch_size=32,
        learning_rate_init=1e-3,
        max_iter=2000,
        early_stopping=True,
        validation_fraction=0.2,
        n_iter_no_change=30,
        random_state=seed,
    )
    model.fit(train, log_dielectric(target[train_indices]))
    return inverse_log_dielectric(model.predict(test))


def _summarize(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["representation"])].append(row)
    metric_names = (
        "mae",
        "rmse",
        "r2",
        "spearman",
        "auc_gt15",
        "auc_gt30",
        "mae_lt20",
        "mae_20_60",
        "mae_gt60",
    )
    result: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for representation in REPRESENTATIONS:
        result[representation] = {}
        for metric in metric_names:
            values = np.asarray(
                [float(row[metric]) for row in grouped[representation]],
                dtype=np.float64,
            )
            finite = values[np.isfinite(values)]
            result[representation][metric] = {
                "mean": float(np.mean(finite)) if finite.size else None,
                "std": (
                    float(np.std(finite, ddof=1))
                    if finite.size > 1
                    else 0.0
                ),
                "n": int(finite.size),
            }
    return result


def _write_plot(
    summary: Mapping[str, Mapping[str, Mapping[str, object]]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    labels = list(REPRESENTATIONS)
    colors = ("#2563eb", "#dc2626", "#059669")
    for axis, metric in zip(axes, ("r2", "mae"), strict=True):
        means = [float(summary[name][metric]["mean"]) for name in labels]
        errors = [float(summary[name][metric]["std"]) for name in labels]
        axis.bar(labels, means, yerr=errors, color=colors, capsize=3)
        axis.set_title(f"{metric.upper()} across repeats")
        axis.tick_params(axis="x", rotation=15)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Small-data MLP probes")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features.csv",
    )
    parser.add_argument(
        "--repeat-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_mlp_probe_repeats.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_mlp_probe_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_mlp_probe_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_mlp_probe.png",
    )
    return parser.parse_args()


def run(
    *,
    input_path: Path,
    repeat_path: Path,
    predictions_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict[str, object]:
    rows, failed = read_modelling_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=np.float64)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    physical = physical_feature_matrix(rows)
    features = {
        "MLP_Morgan": morgan,
        "MLP_Physical": physical,
        "MLP_Hybrid": np.hstack((morgan, physical)),
    }
    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )
    repeat_predictions = {
        (representation, repeat): np.full(len(rows), np.nan)
        for representation in REPRESENTATIONS
        for repeat in range(N_REPEATS)
    }
    prediction_rows: list[dict[str, object]] = []
    for repeat, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(rows)))
    ):
        fold = repeat % N_SPLITS
        repeat_number = repeat // N_SPLITS
        for representation in REPRESENTATIONS:
            prediction = _fit_predict(
                features[representation],
                target,
                train_indices,
                test_indices,
                seed=SEED + repeat,
            )
            repeat_predictions[(representation, repeat_number)][test_indices] = prediction
            for row_index, predicted in zip(test_indices, prediction, strict=True):
                row = rows[int(row_index)]
                prediction_rows.append(
                    {
                        "representation": representation,
                        "repeat": repeat_number,
                        "fold": fold,
                        "inchikey": row["inchikey"],
                        "name": row["name"],
                        "smiles": row["smiles"],
                        "T_K": row["T_K"],
                        "target": f"{target[row_index]:.12g}",
                        "prediction": f"{predicted:.12g}",
                        "abs_error": f"{abs(target[row_index] - predicted):.12g}",
                        "target_stratum": (
                            "lt20"
                            if target[row_index] < 20
                            else "20_60"
                            if target[row_index] <= 60
                            else "gt60"
                        ),
                    }
                )

    repeat_rows: list[dict[str, object]] = []
    for representation in REPRESENTATIONS:
        for repeat in range(N_REPEATS):
            prediction = repeat_predictions[(representation, repeat)]
            if not np.isfinite(prediction).all():
                raise ValueError(
                    f"incomplete OOF predictions for {representation}/{repeat}"
                )
            repeat_rows.append(
                {
                    "representation": representation,
                    "repeat": repeat,
                    **evaluate_repeat(target, prediction),
                }
            )
    summary = _summarize(repeat_rows)
    best = max(
        REPRESENTATIONS,
        key=lambda name: float(summary[name]["r2"]["mean"]),
    )
    best_r2 = float(summary[best]["r2"]["mean"])
    best_spearman = float(summary[best]["spearman"]["mean"])
    payload: dict[str, object] = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "compound_count": len(rows),
        "failed_physical_feature_count": len(failed),
        "representations": list(REPRESENTATIONS),
        "model": {
            "type": "scikit-learn MLPRegressor",
            "hidden_layer_sizes": [64],
            "alpha": 1e-4,
            "batch_size": 32,
            "learning_rate_init": 1e-3,
            "early_stopping": True,
            "target_transform": "log(epsilon - 1)",
        },
        "validation": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
        },
        "summary": summary,
        "comparison": {
            "xgboost_hybrid_r2": XGBOOST_R2,
            "xgboost_hybrid_spearman": XGBOOST_SPEARMAN,
            "best_mlp": best,
            "best_mlp_r2": best_r2,
            "best_mlp_spearman": best_spearman,
            "go_kill": (
                "go"
                if best_r2 > XGBOOST_R2 and best_spearman > XGBOOST_SPEARMAN
                else "no_go"
            ),
        },
        "outputs": {
            "repeat_csv": repeat_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(
                REPOSITORY_ROOT
            ).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    write_csv_rows(repeat_path, REPEAT_COLUMNS, repeat_rows)
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(summary, plot_path)
    return payload


def main() -> int:
    args = _parse_args()
    payload = run(
        input_path=args.input,
        repeat_path=args.repeat_output,
        predictions_path=args.predictions_output,
        summary_path=args.summary_output,
        plot_path=args.plot,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
