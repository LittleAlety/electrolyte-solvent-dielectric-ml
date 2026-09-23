"""Test whether experimental-density Onsager features improve dielectric CV."""

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
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    PREDICTION_COLUMNS,
    REPEAT_COLUMNS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
    write_csv_rows,
)

MU_SQ_COLUMN = "mu_sq_over_Vm"
EXPERIMENTAL_MU_SQ_COLUMN = "mu_sq_over_Vm_experimental"
VARIANTS = (
    "Physical_xtb_raw",
    "Physical_density_raw",
    "Physical_xtb_log",
    "Physical_density_log",
    "Hybrid_xtb_raw",
    "Hybrid_density_raw",
    "Hybrid_xtb_log",
    "Hybrid_density_log",
)


def density_adjusted_mu_sq_over_vm(
    rows: Sequence[Mapping[str, str]],
    *,
    use_experimental: bool,
) -> np.ndarray:
    if not isinstance(use_experimental, bool):
        raise TypeError("density feature source must be a boolean")
    values: list[float] = []
    for row in rows:
        experimental = row.get(EXPERIMENTAL_MU_SQ_COLUMN, "")
        if use_experimental and experimental:
            values.append(float(experimental))
        else:
            values.append(float(row[MU_SQ_COLUMN]))
    result = np.asarray(values, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError("density-adjusted feature contains non-finite values")
    return result


def _variant_physical(
    rows: Sequence[Mapping[str, str]],
    *,
    use_experimental: bool,
) -> np.ndarray:
    matrix = physical_feature_matrix(rows)
    column_index = list(PHYSICAL_COLUMNS).index(MU_SQ_COLUMN)
    matrix[:, column_index] = density_adjusted_mu_sq_over_vm(
        rows,
        use_experimental=use_experimental,
    )
    return matrix


def _fit_predict(
    train_features: np.ndarray,
    test_features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    seed: int,
    use_log_target: bool,
) -> np.ndarray:
    fit_target = np.log(target - 1.0) if use_log_target else target
    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(train_features[train_indices], fit_target[train_indices])
    prediction = model.predict(test_features[test_indices])
    if use_log_target:
        prediction = np.expm1(prediction) + 1.0
    return np.maximum(prediction, 1.0)


def _variant_parts(variant: str) -> tuple[str, bool, bool]:
    model_name, feature_source, target_name = variant.split("_", 2)
    return model_name, feature_source == "density", target_name == "log"


def _summarize(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["variant"])].append(row)
    metrics = (
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
    for variant in VARIANTS:
        values = grouped[variant]
        result[variant] = {}
        for metric in metrics:
            numbers = np.asarray(
                [float(row[metric]) for row in values],
                dtype=np.float64,
            )
            finite = numbers[np.isfinite(numbers)]
            result[variant][metric] = {
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
    labels = ("xtb", "density")
    colors = ("#2563eb", "#dc2626")
    for axis, metric in zip(axes, ("r2", "mae"), strict=True):
        for offset, family in enumerate(("Physical", "Hybrid")):
            values = [
                float(summary[f"{family}_{source}_raw"][metric]["mean"])
                for source in labels
            ]
            errors = [
                float(summary[f"{family}_{source}_raw"][metric]["std"])
                for source in labels
            ]
            positions = np.arange(2) + (offset - 0.5) * 0.25
            axis.bar(
                positions,
                values,
                yerr=errors,
                width=0.25,
                color=colors[offset],
                capsize=3,
                label=family,
            )
        axis.set_xticks(np.arange(2), labels)
        axis.set_title(f"{metric.upper()} across repeats")
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    figure.suptitle("Experimental-density Onsager feature comparison")
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
        / "dielectric_physical_features_density.csv",
    )
    parser.add_argument(
        "--repeat-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_density_feature_repeats.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_density_feature_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_density_feature_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_density_feature_comparison.png",
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
    physical_xtb = _variant_physical(rows, use_experimental=False)
    physical_density = _variant_physical(rows, use_experimental=True)
    matrices = {
        ("Physical", "xtb"): physical_xtb,
        ("Physical", "density"): physical_density,
        ("Hybrid", "xtb"): physical_xtb,
        ("Hybrid", "density"): physical_density,
    }
    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )

    repeat_predictions = {
        (variant, repeat): np.full(len(rows), np.nan)
        for variant in VARIANTS
        for repeat in range(N_REPEATS)
    }
    prediction_rows: list[dict[str, object]] = []
    for repeat, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(rows)))
    ):
        fold = repeat % N_SPLITS
        repeat_number = repeat // N_SPLITS
        for variant in VARIANTS:
            model_name, use_density, use_log = _variant_parts(variant)
            physical = matrices[(model_name, "density" if use_density else "xtb")]
            physical_prediction = _fit_predict(
                physical,
                physical,
                target,
                train_indices,
                test_indices,
                seed=SEED + repeat,
                use_log_target=use_log,
            )
            if model_name == "Hybrid":
                morgan_prediction = _fit_predict(
                    morgan,
                    morgan,
                    target,
                    train_indices,
                    test_indices,
                    seed=SEED + repeat,
                    use_log_target=use_log,
                )
                prediction = 0.5 * (morgan_prediction + physical_prediction)
            else:
                prediction = physical_prediction
            repeat_predictions[(variant, repeat_number)][test_indices] = prediction
            for row_index, predicted in zip(test_indices, prediction, strict=True):
                row = rows[int(row_index)]
                prediction_rows.append(
                    {
                        "representation": variant,
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
    for variant in VARIANTS:
        for repeat in range(N_REPEATS):
            prediction = repeat_predictions[(variant, repeat)]
            if not np.isfinite(prediction).all():
                raise ValueError(f"incomplete OOF predictions for {variant}/{repeat}")
            repeat_rows.append(
                {
                    "variant": variant,
                    "repeat": repeat,
                    **evaluate_repeat(target, prediction),
                }
            )

    summary = _summarize(repeat_rows)
    deltas = {
        f"{family}_{target_mode}": {
            metric: (
                float(
                    summary[f"{family}_density_{target_mode}"][metric]["mean"]
                )
                - float(summary[f"{family}_xtb_{target_mode}"][metric]["mean"])
            )
            for metric in ("mae", "rmse", "r2", "spearman", "auc_gt30")
        }
        for family in ("Physical", "Hybrid")
        for target_mode in ("raw", "log")
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "compound_count": len(rows),
        "failed_physical_feature_count": len(failed),
        "experimental_density_count": sum(
            bool(row[EXPERIMENTAL_MU_SQ_COLUMN]) for row in rows
        ),
        "fallback_xtb_volume_count": sum(
            not row[EXPERIMENTAL_MU_SQ_COLUMN] for row in rows
        ),
        "variants": list(VARIANTS),
        "validation": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
        },
        "summary": summary,
        "density_minus_xtb": deltas,
        "interpretation": (
            "Positive R2/Spearman/AUC deltas and negative MAE/RMSE deltas "
            "favor experimental-density Onsager features."
        ),
        "outputs": {
            "repeat_csv": repeat_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(
                REPOSITORY_ROOT
            ).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    write_csv_rows(
        repeat_path,
        ("variant", "repeat", *REPEAT_COLUMNS[2:]),
        repeat_rows,
    )
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
