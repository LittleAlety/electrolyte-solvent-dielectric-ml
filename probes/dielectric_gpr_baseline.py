"""Morgan-fingerprint Gaussian-process baseline for dielectric v0.1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SEED = 42
TEST_FRACTION = 0.2
FP_RADIUS = 2
FP_SIZE = 2048
ALPHA = 1e-6
N_RESTARTS_OPTIMIZER = 2
COVERAGE_Z = 1.96
INPUT_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
)
PREDICTION_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "split",
    "used_for_metrics",
    "target",
    "prediction",
    "std",
    "abs_error",
    "inside_95",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def deterministic_split(
    sample_count: int,
    *,
    test_fraction: float = TEST_FRACTION,
    seed: int = SEED,
) -> tuple[np.ndarray, np.ndarray]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    indices = np.random.default_rng(seed).permutation(sample_count)
    test_count = max(1, round(sample_count * test_fraction))
    return indices[test_count:], indices[:test_count]


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def coverage_95(
    target: np.ndarray,
    prediction: np.ndarray,
    std: np.ndarray,
) -> dict[str, float | int]:
    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    std = np.asarray(std, dtype=float)
    covered = np.abs(target - prediction) <= COVERAGE_Z * std
    return {
        "covered": int(np.sum(covered)),
        "total": len(target),
        "coverage": float(np.mean(covered)),
        "z": COVERAGE_Z,
    }


def morgan_count_features(
    smiles_values: Sequence[str],
    *,
    radius: int = FP_RADIUS,
    fp_size: int = FP_SIZE,
) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=fp_size)
    features: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES for GPR baseline: {smiles!r}")
        features.append(generator.GetCountFingerprintAsNumPy(molecule))
    return np.vstack(features).astype(np.float32, copy=False)


def _initial_kernel():
    return ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(noise_level=1.0)


def _write_plot(
    rows: Sequence[dict[str, object]],
    path: Path,
) -> None:
    test_rows = [row for row in rows if row["split"] == "test"]
    target = np.asarray([float(row["target"]) for row in test_rows])
    prediction = np.asarray([float(row["prediction"]) for row in test_rows])
    std = np.asarray([float(row["std"]) for row in test_rows])
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(6.4, 5.6))
    axis.errorbar(
        target,
        prediction,
        yerr=COVERAGE_Z * std,
        fmt="o",
        color="#2563eb",
        ecolor="#93c5fd",
        alpha=0.8,
        capsize=2,
    )
    lower = min(float(np.min(target)), float(np.min(prediction - COVERAGE_Z * std)))
    upper = max(float(np.max(target)), float(np.max(prediction + COVERAGE_Z * std)))
    axis.plot([lower, upper], [lower, upper], color="#dc2626", linewidth=1.4)
    axis.set_xlabel("Experimental relative permittivity")
    axis.set_ylabel("Predicted relative permittivity")
    axis.set_title("Dielectric v0.1: Morgan + GPR")
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
    if len(rows) != 100 or len({row["inchikey"] for row in rows}) != 100:
        raise ValueError("dielectric v0.1 must contain 100 unique InChIKeys")
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    features = morgan_count_features([row["smiles"] for row in rows])
    train_indices, test_indices = deterministic_split(len(rows), seed=SEED)
    scaler = StandardScaler()
    train_features = scaler.fit_transform(features[train_indices])
    test_features = scaler.transform(features[test_indices])
    initial_kernel = _initial_kernel()
    model = GaussianProcessRegressor(
        kernel=initial_kernel,
        alpha=ALPHA,
        normalize_y=True,
        n_restarts_optimizer=N_RESTARTS_OPTIMIZER,
        random_state=SEED,
    )
    model.fit(train_features, target[train_indices])
    train_prediction, train_std = model.predict(train_features, return_std=True)
    test_prediction, test_std = model.predict(test_features, return_std=True)
    predictions: dict[int, tuple[str, bool, float, float]] = {}
    for row_index, predicted, std in zip(
        train_indices,
        train_prediction,
        train_std,
        strict=True,
    ):
        predictions[int(row_index)] = ("train", False, float(predicted), float(std))
    for row_index, predicted, std in zip(
        test_indices,
        test_prediction,
        test_std,
        strict=True,
    ):
        predictions[int(row_index)] = ("test", True, float(predicted), float(std))

    prediction_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        split, used_for_metrics, predicted, std = predictions[row_index]
        observed = float(row["dielectric"])
        abs_error = abs(observed - predicted)
        prediction_rows.append(
            {
                "inchikey": row["inchikey"],
                "smiles": row["smiles"],
                "name": row["name"],
                "T_K": row["T_K"],
                "split": split,
                "used_for_metrics": str(used_for_metrics).lower(),
                "target": observed,
                "prediction": predicted,
                "std": std,
                "abs_error": abs_error,
                "inside_95": str(abs_error <= COVERAGE_Z * std).lower(),
            }
        )
    test_rows = [row for row in prediction_rows if row["used_for_metrics"] == "true"]
    test_target = np.asarray([float(row["target"]) for row in test_rows])
    test_prediction_values = np.asarray(
        [float(row["prediction"]) for row in test_rows]
    )
    test_std = np.asarray([float(row["std"]) for row in test_rows])
    metrics = regression_metrics(test_target, test_prediction_values)
    coverage = coverage_95(test_target, test_prediction_values, test_std)
    nonphysical = test_prediction_values[test_prediction_values < 0.0]
    split_payload = "|".join(
        rows[int(index)]["inchikey"] for index in sorted(test_indices)
    )
    summary = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": sha256_file(input_path),
        "compound_count": len(rows),
        "unique_inchikey_count": len({row["inchikey"] for row in rows}),
        "feature": {
            "type": "Morgan count fingerprint",
            "radius": FP_RADIUS,
            "fp_size": FP_SIZE,
        },
        "split": {
            "strategy": "deterministic permutation; 80/20",
            "seed": SEED,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "train_inchikeys": [
                rows[int(index)]["inchikey"] for index in train_indices
            ],
            "test_inchikeys": [
                rows[int(index)]["inchikey"] for index in test_indices
            ],
            "test_id_hash": hashlib.sha256(split_payload.encode("utf-8")).hexdigest(),
        },
        "model": {
            "name": "StandardScaler + GaussianProcessRegressor",
            "initial_kernel": repr(initial_kernel),
            "final_kernel": repr(model.kernel_),
            "alpha": ALPHA,
            "normalize_y": True,
            "n_restarts_optimizer": N_RESTARTS_OPTIMIZER,
            "random_state": SEED,
            "hyperparameters_tuned_on_test": False,
        },
        "prediction_rows": len(prediction_rows),
        "metrics": metrics,
        "posterior_std": {
            "finite": bool(np.isfinite(test_std).all()),
            "nonnegative": bool(np.all(test_std >= 0.0)),
            "min": float(np.min(test_std)),
            "max": float(np.max(test_std)),
            "mean": float(np.mean(test_std)),
        },
        "coverage_95": coverage,
        "predictions_clipped": False,
        "nonphysical_prediction_count": len(nonphysical),
        "nonphysical_prediction_min": (
            float(np.min(nonphysical)) if len(nonphysical) else None
        ),
        "gate": {
            "metric": "r2",
            "threshold": 0.8,
            "passed": bool(metrics["r2"] > 0.8),
        },
        "context": {
            "dataset_v01_compound_count": 100,
            "chodera_keys_all_overlap_p1": True,
            "p2_dipole_reference_r2": 0.5636486411094666,
            "note": "This is the active-learning starting baseline, not a final model.",
        },
        "outputs": {
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "parity_plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "model_comparison": "P2 dipole R2 is a different target and is context only.",
        },
    }
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(prediction_rows, plot_path)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_gpr_test_predictions.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_gpr_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_gpr_parity.png",
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
