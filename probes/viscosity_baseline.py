"""Strong viscosity baseline with random-row and molecule-group evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from probes.p2_battp30k_baseline import _model

MODEL_NAMES = ("DummyMean", "TOnlyRidge", "MorganTemperatureXGBoost")
FEATURE_NAMES = ("T_K", "1000_over_T_K")
SEED = 42
TEST_FRACTION = 0.2
MAE_GATE = 0.15


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_feature_matrix(
    smiles_values: Sequence[str],
    temperatures_k: Sequence[float],
) -> tuple[np.ndarray, tuple[str, ...]]:
    if len(smiles_values) != len(temperatures_k):
        raise ValueError("SMILES and temperature counts differ")
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprints: list[np.ndarray] = []
    temperature_features: list[list[float]] = []
    for smiles, temperature in zip(smiles_values, temperatures_k, strict=True):
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        fingerprints.append(generator.GetCountFingerprintAsNumPy(molecule))
        temperature_features.append([temperature, 1000.0 / temperature])
    matrix = np.column_stack(
        [np.vstack(fingerprints), np.asarray(temperature_features, dtype=float)]
    ).astype(np.float32, copy=False)
    return matrix, FEATURE_NAMES


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def transformed_metrics(
    target_log10_cp: np.ndarray,
    prediction_log10_cp: np.ndarray,
) -> dict[str, dict[str, float]]:
    target_cp = np.power(10.0, target_log10_cp)
    prediction_cp = np.power(10.0, prediction_log10_cp)
    return {
        "log10_cP": regression_metrics(target_log10_cp, prediction_log10_cp),
        "log10_Pa_s": regression_metrics(
            target_log10_cp - 3.0,
            prediction_log10_cp - 3.0,
        ),
        "cP": regression_metrics(target_cp, prediction_cp),
        "Pa_s": regression_metrics(target_cp / 1000.0, prediction_cp / 1000.0),
    }


def _random_row_split(
    sample_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.random.default_rng(SEED).permutation(sample_count)
    test_count = max(1, round(sample_count * TEST_FRACTION))
    return indices[test_count:], indices[:test_count]


def _group_key_split(
    groups: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=TEST_FRACTION,
        random_state=SEED,
    )
    train_indices, test_indices = next(
        splitter.split(np.zeros(len(groups)), groups=groups)
    )
    return train_indices, test_indices


def _fit_predict(
    model_name: str,
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
) -> np.ndarray:
    if model_name == "DummyMean":
        model = DummyRegressor(strategy="mean")
        model.fit(np.zeros((len(train_indices), 1)), target[train_indices])
        return model.predict(np.zeros((len(test_indices), 1)))
    if model_name == "TOnlyRidge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        model.fit(features[train_indices, -2:], target[train_indices])
        return model.predict(features[test_indices, -2:])
    if model_name == "MorganTemperatureXGBoost":
        model = _model(seed=SEED)
        model.fit(features[train_indices], target[train_indices])
        return model.predict(features[test_indices])
    raise ValueError(f"unknown viscosity model: {model_name}")


def _model_config(model_name: str) -> str:
    if model_name == "DummyMean":
        return "DummyRegressor(strategy='mean')"
    if model_name == "TOnlyRidge":
        return "StandardScaler + Ridge(alpha=1.0), features=T_K+1000/T_K"
    return (
        "XGBoost n_estimators=800, max_depth=10, learning_rate=0.05, "
        "subsample=0.8, colsample_bytree=0.6, reg_lambda=1.0, seed=42; "
        "features=Morgan_count_2048+T_K+1000/T_K"
    )


def _split_hash(molecule_ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(molecule_ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_plot(
    predictions: Sequence[dict[str, object]],
    summary: dict[str, object],
    path: Path,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11, 10))
    for axis, split_type in zip(
        axes[:, 0],
        ("random_row", "group_key"),
        strict=True,
    ):
        rows = [
            row
            for row in predictions
            if row["split_type"] == split_type
            and row["model"] == "MorganTemperatureXGBoost"
        ]
        target = np.asarray([float(row["target_log10_cP"]) for row in rows])
        prediction = np.asarray([float(row["prediction_log10_cP"]) for row in rows])
        axis.scatter(target, prediction, s=8, alpha=0.3)
        axis.plot(
            [target.min(), target.max()],
            [target.min(), target.max()],
            color="#dc2626",
        )
        axis.set_title(f"Morgan+Temperature XGBoost: {split_type}")
        axis.set_xlabel("Target log10(cP)")
        axis.set_ylabel("Predicted log10(cP)")
    for axis, metric in zip(axes[:, 1], ("mae", "r2"), strict=True):
        for split_type in ("random_row", "group_key"):
            models = summary["splits"][split_type]["models"]
            axis.bar(
                [f"{name}\n{split_type}" for name in MODEL_NAMES],
                [models[name]["log10_cP"][metric] for name in MODEL_NAMES],
            )
        axis.set_title(metric.upper())
        axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_baseline(
    *,
    input_path: Path,
    predictions_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict[str, object]:
    rows = read_csv_rows(input_path)
    if len(rows) != 3582 or len({row["inchikey"] for row in rows}) != 957:
        raise ValueError("viscosity_v01 must contain 3582 rows and 957 keys")
    molecule_ids = [row["inchikey"] for row in rows]
    temperatures = np.asarray([float(row["T_K"]) for row in rows], dtype=float)
    target = np.log10(
        np.asarray([float(row["viscosity_cP"]) for row in rows], dtype=float)
    )
    features, feature_names = build_feature_matrix(
        [row["smiles"] for row in rows],
        temperatures,
    )
    split_indices = {
        "random_row": _random_row_split(len(rows)),
        "group_key": _group_key_split(molecule_ids),
    }
    prediction_rows: list[dict[str, object]] = []
    split_summaries: dict[str, object] = {}
    for split_type, (train_indices, test_indices) in split_indices.items():
        if split_type == "group_key":
            train_keys = {molecule_ids[index] for index in train_indices}
            test_keys = {molecule_ids[index] for index in test_indices}
            if train_keys.intersection(test_keys):
                raise RuntimeError("group split leaked molecule keys")
        model_summaries: dict[str, object] = {}
        for model_name in MODEL_NAMES:
            prediction = _fit_predict(
                model_name,
                features,
                target,
                train_indices,
                test_indices,
            )
            metrics = transformed_metrics(target[test_indices], prediction)
            model_summaries[model_name] = {
                "config": _model_config(model_name),
                **metrics,
                "gate_log10_cP_mae_lt_0_15": metrics["log10_cP"]["mae"] < MAE_GATE,
            }
            for index, predicted in zip(test_indices, prediction, strict=True):
                row = rows[int(index)]
                target_log = float(target[int(index)])
                prediction_log = float(predicted)
                target_cp = float(10.0**target_log)
                prediction_cp = float(10.0**prediction_log)
                prediction_rows.append(
                    {
                        "row_id": str(index),
                        "inchikey": row["inchikey"],
                        "smiles": row["smiles"],
                        "name": row["name"],
                        "T_K": row["T_K"],
                        "split_type": split_type,
                        "model": model_name,
                        "used_for_metrics": "true",
                        "target_log10_cP": target_log,
                        "prediction_log10_cP": prediction_log,
                        "target_cP": target_cp,
                        "prediction_cP": prediction_cp,
                        "target_Pa_s": target_cp / 1000.0,
                        "prediction_Pa_s": prediction_cp / 1000.0,
                        "abs_error_log10_cP": abs(target_log - prediction_log),
                        "abs_error_cP": abs(target_cp - prediction_cp),
                        "abs_error_Pa_s": abs(target_cp - prediction_cp) / 1000.0,
                    }
                )
        split_summaries[split_type] = {
            "train_rows": len(train_indices),
            "test_rows": len(test_indices),
            "train_unique_keys": len(
                {molecule_ids[int(index)] for index in train_indices}
            ),
            "test_unique_keys": len(
                {molecule_ids[int(index)] for index in test_indices}
            ),
            "group_overlap": len(
                {molecule_ids[int(index)] for index in train_indices}.intersection(
                    {molecule_ids[int(index)] for index in test_indices}
                )
            ),
            "train_id_hash": _split_hash(molecule_ids, train_indices),
            "test_id_hash": _split_hash(molecule_ids, test_indices),
            "models": model_summaries,
        }
    random_gate = split_summaries["random_row"]["models"][
        "MorganTemperatureXGBoost"
    ]["gate_log10_cP_mae_lt_0_15"]
    group_gate = split_summaries["group_key"]["models"][
        "MorganTemperatureXGBoost"
    ]["gate_log10_cP_mae_lt_0_15"]
    summary = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "input_hash_mode": "canonical_text_lf_utf8",
        "row_count": len(rows),
        "unique_key_count": len(set(molecule_ids)),
        "target": "log10(viscosity_cP)",
        "feature_config": {
            "fingerprint": "Morgan count, radius=2, fpSize=2048",
            "temperature_features": list(feature_names),
        },
        "prediction_rows": len(prediction_rows),
        "splits": split_summaries,
        "primary_gate": {
            "metric": "log10_cP_mae",
            "threshold": MAE_GATE,
            "random_row_passed": random_gate,
            "group_key_passed": group_gate,
        },
        "interpretation": {
            "random_row_tests_temperature_interpolation_and_row_memorization": True,
            "group_key_tests_new_molecule_generalization": True,
            "random_pass_group_fail": bool(random_gate and not group_gate),
        },
        "limitations": [
            "MD density fields are excluded because experimental density is unavailable.",
            "Group holdout measures new-molecule extrapolation but does not remove scaffold similarity.",
            "No test-driven hyperparameter tuning is performed.",
        ],
        "outputs": {
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "parity_plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    with predictions_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "row_id",
                "inchikey",
                "smiles",
                "name",
                "T_K",
                "split_type",
                "model",
                "used_for_metrics",
                "target_log10_cP",
                "prediction_log10_cP",
                "target_cP",
                "prediction_cP",
                "target_Pa_s",
                "prediction_Pa_s",
                "abs_error_log10_cP",
                "abs_error_cP",
                "abs_error_Pa_s",
            ),
        )
        writer.writeheader()
        writer.writerows(prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(prediction_rows, summary, plot_path)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "viscosity_v01.csv",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "viscosity_baseline_predictions.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=(
            REPOSITORY_ROOT / "probes" / "artifacts" / "viscosity_baseline_parity.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_baseline(
        input_path=args.input,
        predictions_path=args.predictions,
        summary_path=args.summary,
        plot_path=args.plot,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
