"""P2: fingerprint-to-XGBoost baseline for Batt-P30K dipole moments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import matplotlib
import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import rdFingerprintGenerator
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FEATURE_SCHEMA_VERSION = 1
FEATURE_CONFIG: dict[str, Any] = {
    "fingerprint": "morgan_count",
    "radius": 2,
    "fp_size": 2048,
    "target": "Euclidean norm of the three-component dipole vector",
}


class CacheMismatchError(RuntimeError):
    """Raised when a feature cache does not match its source or configuration."""


class DatasetSchemaError(ValueError):
    """Raised when the Batt-P30K HDF5 schema is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class FeatureBundle:
    X: np.ndarray
    y: np.ndarray
    smiles: np.ndarray
    molecule_ids: np.ndarray
    source_sha256: str
    source_group_count: int
    invalid_smiles_count: int
    cache_status: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_smiles(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def dipole_magnitude(vector: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(vector, dtype=float)))


def regression_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def train_test_indices(
    sample_count: int,
    *,
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    indices = np.random.default_rng(seed).permutation(sample_count)
    test_count = max(1, round(sample_count * test_size))
    return indices[test_count:], indices[:test_count]


def _feature_config_json() -> str:
    return json.dumps(FEATURE_CONFIG, sort_keys=True, separators=(",", ":"))


def _load_valid_cache(
    cache_path: Path,
    *,
    source_sha256: str,
) -> FeatureBundle | None:
    if not cache_path.exists():
        return None
    with np.load(cache_path, allow_pickle=False) as cached:
        required = {
            "schema_version",
            "feature_config_json",
            "source_sha256",
            "source_group_count",
            "invalid_smiles_count",
            "X",
            "y",
            "smiles",
            "molecule_ids",
        }
        missing = sorted(required.difference(cached.files))
        if missing:
            raise CacheMismatchError(
                f"feature cache is missing metadata arrays: {', '.join(missing)}"
            )
        if int(cached["schema_version"]) != FEATURE_SCHEMA_VERSION:
            raise CacheMismatchError(
                "feature cache schema version mismatch: "
                f"{int(cached['schema_version'])} != {FEATURE_SCHEMA_VERSION}"
            )
        if str(cached["feature_config_json"].item()) != _feature_config_json():
            raise CacheMismatchError("feature cache configuration mismatch")
        if str(cached["source_sha256"].item()) != source_sha256:
            raise CacheMismatchError(
                "feature cache source SHA256 mismatch: "
                f"{cached['source_sha256'].item()} != {source_sha256}"
            )
        X = cached["X"]
        y = cached["y"]
        smiles = cached["smiles"]
        molecule_ids = cached["molecule_ids"]
        if X.ndim != 2 or X.shape[1] != FEATURE_CONFIG["fp_size"]:
            raise CacheMismatchError(
                f"feature cache has invalid X shape {X.shape}"
            )
        if not (X.shape[0] == len(y) == len(smiles) == len(molecule_ids)):
            raise CacheMismatchError("feature cache arrays have inconsistent row counts")
        return FeatureBundle(
            X=X,
            y=y,
            smiles=smiles,
            molecule_ids=molecule_ids,
            source_sha256=source_sha256,
            source_group_count=int(cached["source_group_count"]),
            invalid_smiles_count=int(cached["invalid_smiles_count"]),
            cache_status="cache_hit",
        )


def _group_sort_key(key: str) -> tuple[int, str]:
    if key.startswith("CompMol") and key.removeprefix("CompMol").isdigit():
        return int(key.removeprefix("CompMol")), key
    return 2**31 - 1, key


def build_features(
    h5_path: Path,
    cache_path: Path,
    *,
    rebuild_cache: bool = False,
) -> FeatureBundle:
    source_sha256 = sha256_file(h5_path)
    if not rebuild_cache:
        cached = _load_valid_cache(cache_path, source_sha256=source_sha256)
        if cached is not None:
            return cached

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprints: list[np.ndarray] = []
    targets: list[float] = []
    smiles_values: list[str] = []
    molecule_ids: list[str] = []
    invalid_smiles = 0

    RDLogger.DisableLog("rdApp.*")
    with h5py.File(h5_path, "r") as handle:
        keys = sorted(handle.keys(), key=_group_sort_key)
        if not keys:
            raise DatasetSchemaError("Batt-P30K HDF5 file contains no molecule groups")
        for index, key in enumerate(keys, start=1):
            group = handle[key]
            if not isinstance(group, h5py.Group):
                raise DatasetSchemaError(f"{key} is not an HDF5 group")
            if "smiles" not in group:
                raise DatasetSchemaError(f"{key} is missing the smiles dataset")
            if "dipole" not in group:
                raise DatasetSchemaError(f"{key} is missing the dipole dataset")
            dipole = np.asarray(group["dipole"][...], dtype=float)
            if dipole.shape != (3,):
                raise DatasetSchemaError(
                    f"{key}/dipole has shape {dipole.shape}, expected (3,)"
                )
            if not np.isfinite(dipole).all():
                raise DatasetSchemaError(f"{key}/dipole contains non-finite values")
            smiles = decode_smiles(group["smiles"][0])
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None:
                invalid_smiles += 1
                continue
            fingerprints.append(generator.GetCountFingerprintAsNumPy(molecule))
            targets.append(dipole_magnitude(dipole))
            smiles_values.append(Chem.MolToSmiles(molecule))
            molecule_ids.append(key)
            if index % 5000 == 0:
                print(f"featurized {index}/{len(keys)}")

    if not fingerprints:
        raise DatasetSchemaError("no valid molecules remain after SMILES parsing")
    X = np.vstack(fingerprints).astype(np.float32, copy=False)
    y = np.asarray(targets, dtype=np.float32)
    smiles_array = np.asarray(smiles_values, dtype=str)
    molecule_id_array = np.asarray(molecule_ids, dtype=str)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        X=X,
        y=y,
        smiles=smiles_array,
        molecule_ids=molecule_id_array,
        schema_version=np.asarray(FEATURE_SCHEMA_VERSION, dtype=np.int32),
        feature_config_json=np.asarray(_feature_config_json()),
        source_sha256=np.asarray(source_sha256),
        source_group_count=np.asarray(len(keys), dtype=np.int32),
        invalid_smiles_count=np.asarray(invalid_smiles, dtype=np.int32),
    )
    print(f"invalid SMILES: {invalid_smiles}")
    return FeatureBundle(
        X=X,
        y=y,
        smiles=smiles_array,
        molecule_ids=molecule_id_array,
        source_sha256=source_sha256,
        source_group_count=len(keys),
        invalid_smiles_count=invalid_smiles,
        cache_status="rebuilt",
    )


def _model(seed: int = 42) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=800,
        max_depth=10,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.6,
        reg_lambda=1.0,
        tree_method="hist",
        n_jobs=max(1, min(os.cpu_count() or 1, 8)),
        random_state=seed,
    )


def fit_learning_curve(
    X: np.ndarray,
    y: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    train_sizes: Sequence[int] = (1000, 5000, 10000, 25000),
    seed: int = 42,
) -> list[dict[str, float | int]]:
    rng = np.random.default_rng(seed)
    curve: list[dict[str, float | int]] = []
    for requested_size in train_sizes:
        size = min(requested_size, len(train_indices))
        selected = rng.choice(train_indices, size=size, replace=False)
        model = _model(seed)
        model.fit(X[selected], y[selected])
        prediction = model.predict(X[test_indices])
        metrics = regression_metrics(y[test_indices], prediction)
        curve.append({"train_size": size, **metrics})
        print(f"train_size={size}: {metrics}")
    return curve


def write_learning_curve(curve: Sequence[dict[str, float | int]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("train_size", "mae", "rmse", "r2"))
        writer.writeheader()
        writer.writerows(curve)


def write_plots(
    target: np.ndarray,
    prediction: np.ndarray,
    curve: Sequence[dict[str, float | int]],
    plot_dir: Path,
) -> tuple[Path, Path]:
    plot_dir.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(6, 6))
    axis.scatter(target, prediction, s=7, alpha=0.25, color="#2563eb", edgecolors="none")
    limit = float(max(np.max(target), np.max(prediction)))
    axis.plot([0, limit], [0, limit], color="#dc2626", linewidth=1.5)
    axis.set_xlabel("DFT dipole magnitude")
    axis.set_ylabel("Predicted dipole magnitude")
    axis.set_title("Batt-P30K parity")
    figure.tight_layout()
    parity_path = plot_dir / "p2_dipole_parity.png"
    figure.savefig(parity_path, dpi=180)
    plt.close(figure)

    sizes = [int(item["train_size"]) for item in curve]
    r2_values = [float(item["r2"]) for item in curve]
    mae_values = [float(item["mae"]) for item in curve]
    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.plot(sizes, r2_values, marker="o", color="#16a34a", label="R2")
    axis.plot(sizes, mae_values, marker="s", color="#f59e0b", label="MAE")
    axis.set_xscale("log")
    axis.set_xlabel("Training molecules")
    axis.set_ylabel("Test metric")
    axis.set_title("Batt-P30K learning curve")
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    curve_path = plot_dir / "p2_dipole_learning_curve.png"
    figure.savefig(curve_path, dpi=180)
    plt.close(figure)
    return parity_path, curve_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h5",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "p2_battp30k_count_features.npz",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p2_summary.json",
    )
    parser.add_argument(
        "--learning-curve",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "p2_learning_curve.csv",
    )
    parser.add_argument(
        "--plot-dir",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Rebuild the feature cache even when its metadata matches.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bundle = build_features(
        args.h5,
        args.cache,
        rebuild_cache=args.rebuild_cache,
    )
    X, y, smiles, molecule_ids = (
        bundle.X,
        bundle.y,
        bundle.smiles,
        bundle.molecule_ids,
    )
    train_indices, test_indices = train_test_indices(len(y), seed=42)
    curve = fit_learning_curve(X, y, train_indices, test_indices, seed=42)

    final_model = _model(seed=42)
    final_model.fit(X[train_indices], y[train_indices])
    prediction = final_model.predict(X[test_indices])
    metrics = regression_metrics(y[test_indices], prediction)
    parity_path, curve_path = write_plots(y[test_indices], prediction, curve, args.plot_dir)
    write_learning_curve(curve, args.learning_curve)

    model_path = args.plot_dir / "p2_dipole_model.json"
    final_model.save_model(model_path)
    prediction_path = REPOSITORY_ROOT / "data" / "processed" / "p2_test_predictions.csv"
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("molecule_id", "smiles", "target", "prediction"),
        )
        writer.writeheader()
        for index, predicted in zip(test_indices, prediction, strict=True):
            writer.writerow(
                {
                    "molecule_id": molecule_ids[index],
                    "smiles": smiles[index],
                    "target": f"{y[index]:.8g}",
                    "prediction": f"{predicted:.8g}",
                }
            )

    summary = {
        "dataset": str(args.h5),
        "dataset_sha256": bundle.source_sha256,
        "source_group_count": bundle.source_group_count,
        "molecule_count": len(y),
        "invalid_smiles_count": bundle.invalid_smiles_count,
        "feature_cache_status": bundle.cache_status,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_config": FEATURE_CONFIG,
        "feature": "Morgan count fingerprint, radius=2, 2048 bits",
        "target": "Euclidean norm of the three-component Batt-P30K dipole vector",
        "target_units": "not stated in the source README",
        "train_count": len(train_indices),
        "test_count": len(test_indices),
        "final_metrics": metrics,
        "pass_r2_gt_0_8": metrics["r2"] > 0.8,
        "learning_curve": curve,
        "outputs": {
            "parity_plot": str(parity_path),
            "learning_curve_plot": str(curve_path),
            "learning_curve_csv": str(args.learning_curve),
            "test_predictions_csv": str(prediction_path),
            "model_json": str(model_path),
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
