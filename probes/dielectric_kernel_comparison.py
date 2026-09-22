"""Compare Tanimoto-GPR, RBF-GPR, and XGBoost on dielectric v0.1."""

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
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Kernel
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from probes.p2_battp30k_baseline import _model

MODEL_NAMES = ("Tanimoto_GPR", "RBF_GPR", "XGBoost")
CV_SPLITS = 5
CV_REPEATS = 10
SEED = 42
FP_RADIUS = 2
FP_SIZE = 2048
ALPHA = 1e-6


class PrecomputedKernel(Kernel):
    """Compatibility shim for the removed string precomputed-kernel mode."""

    def __init__(self) -> None:
        pass

    def __call__(self, X, Y=None, eval_gradient=False):
        kernel = np.asarray(X, dtype=float)
        if eval_gradient:
            return kernel, np.empty((kernel.shape[0], kernel.shape[1], 0))
        return kernel

    def diag(self, X):
        return np.diag(np.asarray(X, dtype=float))

    def is_stationary(self) -> bool:
        return False


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _morgan_features(smiles_values: Sequence[str], *, binary: bool) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=FP_RADIUS,
        fpSize=FP_SIZE,
    )
    rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        if binary:
            rows.append(generator.GetFingerprintAsNumPy(molecule))
        else:
            rows.append(generator.GetCountFingerprintAsNumPy(molecule))
    return np.vstack(rows).astype(np.float32, copy=False)


def tanimoto_kernel(
    left: np.ndarray,
    right: np.ndarray | None = None,
) -> np.ndarray:
    left = np.asarray(left, dtype=float)
    right = left if right is None else np.asarray(right, dtype=float)
    intersection = left @ right.T
    union = (
        np.sum(left, axis=1)[:, None]
        + np.sum(right, axis=1)[None, :]
        - intersection
    )
    return np.divide(
        intersection,
        union,
        out=np.zeros_like(intersection, dtype=float),
        where=union != 0,
    )


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def _tanimoto_gpr() -> GaussianProcessRegressor:
    return GaussianProcessRegressor(
        kernel=PrecomputedKernel(),
        alpha=ALPHA,
        normalize_y=True,
        optimizer=None,
        n_restarts_optimizer=0,
        random_state=SEED,
    )


def _rbf_gpr():
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
        noise_level=1.0
    )
    return make_pipeline(
        StandardScaler(),
        GaussianProcessRegressor(
            kernel=kernel,
            alpha=ALPHA,
            normalize_y=True,
            n_restarts_optimizer=2,
            random_state=SEED,
        ),
    )


def _predict_fold(
    model_name: str,
    *,
    binary: np.ndarray,
    count: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
) -> np.ndarray:
    if model_name == "Tanimoto_GPR":
        train_kernel = tanimoto_kernel(binary[train_indices])
        model = _tanimoto_gpr()
        model.fit(train_kernel, target[train_indices])
        cross_kernel = tanimoto_kernel(
            binary[test_indices],
            binary[train_indices],
        )
        return model.predict(cross_kernel)
    if model_name == "RBF_GPR":
        model = _rbf_gpr()
        model.fit(count[train_indices], target[train_indices])
        return model.predict(count[test_indices])
    if model_name == "XGBoost":
        model = _model(seed=SEED)
        model.fit(count[train_indices], target[train_indices])
        return model.predict(count[test_indices])
    raise ValueError(f"unknown model: {model_name}")


def _index_hash(molecule_ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(molecule_ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_metric_rows(
    rows: Sequence[dict[str, object]],
) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    for model_name in sorted({str(row["model"]) for row in rows}):
        model_rows = [row for row in rows if row["model"] == model_name]
        result[model_name] = {}
        for metric in ("mae", "rmse", "r2"):
            values = np.asarray([float(row[metric]) for row in model_rows])
            result[model_name][metric] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values, ddof=1)),
            }
    return result


def _model_config(model_name: str) -> str:
    if model_name == "Tanimoto_GPR":
        return (
            "binary Morgan r=2/2048; precomputed Tanimoto; "
            "GPR(alpha=1e-6, normalize_y=True, optimizer=None)"
        )
    if model_name == "RBF_GPR":
        return (
            "count Morgan r=2/2048; StandardScaler; "
            "C(1)*RBF(length_scale=10)+White(noise_level=1); alpha=1e-6; "
            "normalize_y=True; n_restarts=2; seed=42"
        )
    return (
        "count Morgan r=2/2048; XGBoost n_estimators=800, max_depth=10, "
        "learning_rate=0.05, subsample=0.8, colsample_bytree=0.6, seed=42"
    )


def run_comparison(
    *,
    input_path: Path,
    csv_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict[str, object]:
    rows = read_csv_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    molecule_ids = [row["inchikey"] for row in rows]
    binary = _morgan_features([row["smiles"] for row in rows], binary=True)
    count = _morgan_features([row["smiles"] for row in rows], binary=False)
    splitter = RepeatedKFold(
        n_splits=CV_SPLITS,
        n_repeats=CV_REPEATS,
        random_state=SEED,
    )
    output_rows: list[dict[str, object]] = []
    for index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(target)))
    ):
        repeat = index // CV_SPLITS
        fold = index % CV_SPLITS
        for model_name in MODEL_NAMES:
            prediction = _predict_fold(
                model_name,
                binary=binary,
                count=count,
                target=target,
                train_indices=train_indices,
                test_indices=test_indices,
            )
            output_rows.append(
                {
                    "model": model_name,
                    "repeat": repeat,
                    "fold": fold,
                    "seed": SEED,
                    "n_train": len(train_indices),
                    "n_test": len(test_indices),
                    "train_id_hash": _index_hash(molecule_ids, train_indices),
                    "test_id_hash": _index_hash(molecule_ids, test_indices),
                    "config": _model_config(model_name),
                    **regression_metrics(target[test_indices], prediction),
                }
            )
    summaries = summarize_metric_rows(output_rows)
    rbf_r2 = summaries["RBF_GPR"]["r2"]["mean"]
    tanimoto_r2 = summaries["Tanimoto_GPR"]["r2"]["mean"]
    summary = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "input_hash_mode": "canonical_text_lf_utf8",
        "compound_count": len(rows),
        "split": {
            "method": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
            "seed": SEED,
            "fold_count": CV_SPLITS * CV_REPEATS,
            "rows_per_model": CV_SPLITS * CV_REPEATS,
        },
        "models": {
            name: {
                "config": _model_config(name),
                "metrics": summaries[name],
            }
            for name in MODEL_NAMES
        },
        "tanimoto_vs_rbf_r2_mean_difference": tanimoto_r2 - rbf_r2,
        "gate": {
            "metric": "r2_mean",
            "threshold": 0.8,
            "best_model": max(summaries, key=lambda name: summaries[name]["r2"]["mean"]),
            "passed": max(summaries[name]["r2"]["mean"] for name in MODEL_NAMES)
            > 0.8,
        },
        "conclusion": {
            "tanimoto_improves_over_rbf": tanimoto_r2 > rbf_r2,
            "improvement_margin": tanimoto_r2 - rbf_r2,
            "recommended_next_step": (
                "Do not tune the kernels further; inspect fold-level failures and "
                "representation alternatives."
            ),
        },
        "outputs": {
            "comparison_csv": csv_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "comparison_plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "model",
                "repeat",
                "fold",
                "seed",
                "n_train",
                "n_test",
                "train_id_hash",
                "test_id_hash",
                "config",
                "mae",
                "rmse",
                "r2",
            ),
        )
        writer.writeheader()
        writer.writerows(output_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, metric in zip(axes, ("r2", "mae", "rmse"), strict=True):
        means = [summaries[name][metric]["mean"] for name in MODEL_NAMES]
        stds = [summaries[name][metric]["std"] for name in MODEL_NAMES]
        axis.bar(MODEL_NAMES, means, yerr=stds, capsize=3)
        axis.set_title(metric.upper())
        axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(plot_path, dpi=180)
    plt.close(figure)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_kernel_comparison.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_kernel_comparison_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "probes"
            / "artifacts"
            / "dielectric_kernel_comparison.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_comparison(
        input_path=args.input,
        csv_path=args.csv,
        summary_path=args.summary,
        plot_path=args.plot,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
