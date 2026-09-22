"""Diagnostic evidence for the dielectric v0.1 Morgan+GPR baseline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import warnings
from collections import defaultdict
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
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from sklearn.dummy import DummyRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_gpr_baseline import (
    ALPHA,
    N_RESTARTS_OPTIMIZER,
    SEED,
    _initial_kernel,
    deterministic_split,
    morgan_count_features,
    read_csv_rows,
    regression_metrics,
)

MODEL_NAMES = ("DummyMean", "SizeOnlyRidge", "MorganRBFGPR")
DESCRIPTOR_NAMES = (
    "TPSA",
    "MolLogP",
    "NumHDonors",
    "NumHAcceptors",
    "FractionCSP3",
    "NumRotatableBonds",
    "MolWt",
    "HeavyAtomCount",
    "RingCount",
    "Gasteiger_charge_min",
    "Gasteiger_charge_max",
    "Gasteiger_charge_mean_abs",
    "Gasteiger_charge_std",
    "Gasteiger_charge_sum_abs",
)
TRAIN_SIZES = (20, 40, 60, 80)
LEARNING_CURVE_REPEATS = 5
CV_SPLITS = 5
CV_REPEATS = 10


def _indices_hash(molecule_ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(str(molecule_ids[int(index)]) for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def size_features(smiles: str) -> np.ndarray:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES for size features: {smiles!r}")
    return np.asarray(
        [float(Descriptors.MolWt(molecule)), float(molecule.GetNumHeavyAtoms())],
        dtype=float,
    )


def build_size_matrix(smiles_values: Sequence[str]) -> np.ndarray:
    return np.vstack([size_features(smiles) for smiles in smiles_values])


def _gasteiger_statistics(molecule: Chem.Mol) -> tuple[float, float, float, float, float]:
    AllChem.ComputeGasteigerCharges(molecule)
    charges = np.asarray(
        [float(atom.GetDoubleProp("_GasteigerCharge")) for atom in molecule.GetAtoms()],
        dtype=float,
    )
    finite_charges = charges[np.isfinite(charges)]
    if not len(finite_charges):
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return (
        float(np.min(finite_charges)),
        float(np.max(finite_charges)),
        float(np.mean(np.abs(finite_charges))),
        float(np.std(finite_charges)),
        float(np.sum(np.abs(finite_charges))),
    )


def gasteiger_nonfinite_count(smiles_values: Sequence[str]) -> int:
    count = 0
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES for Gasteiger audit: {smiles!r}")
        AllChem.ComputeGasteigerCharges(molecule)
        charges = np.asarray(
            [
                float(atom.GetDoubleProp("_GasteigerCharge"))
                for atom in molecule.GetAtoms()
            ],
            dtype=float,
        )
        count += int(np.sum(~np.isfinite(charges)))
    return count


def descriptor_features(smiles_values: Sequence[str]) -> tuple[np.ndarray, tuple[str, ...]]:
    rows: list[list[float]] = []
    morgan_rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES for descriptor features: {smiles!r}")
        charge_statistics = _gasteiger_statistics(molecule)
        rows.append(
            [
                float(rdMolDescriptors.CalcTPSA(molecule)),
                float(Descriptors.MolLogP(molecule)),
                float(rdMolDescriptors.CalcNumHBD(molecule)),
                float(rdMolDescriptors.CalcNumHBA(molecule)),
                float(rdMolDescriptors.CalcFractionCSP3(molecule)),
                float(rdMolDescriptors.CalcNumRotatableBonds(molecule)),
                float(Descriptors.MolWt(molecule)),
                float(molecule.GetNumHeavyAtoms()),
                float(rdMolDescriptors.CalcNumRings(molecule)),
                *charge_statistics,
            ]
        )
    morgan_rows = morgan_count_features(list(smiles_values))
    return (
        np.column_stack([morgan_rows, np.asarray(rows, dtype=float)]).astype(
            np.float32,
            copy=False,
        ),
        DESCRIPTOR_NAMES,
    )


def _gpr_model() -> GaussianProcessRegressor:
    return GaussianProcessRegressor(
        kernel=_initial_kernel(),
        alpha=ALPHA,
        normalize_y=True,
        n_restarts_optimizer=N_RESTARTS_OPTIMIZER,
        random_state=SEED,
    )


def _fit_predict(
    model_name: str,
    train_features: np.ndarray,
    train_target: np.ndarray,
    test_features: np.ndarray,
) -> np.ndarray:
    if model_name == "DummyMean":
        model = DummyRegressor(strategy="mean")
        model.fit(np.zeros((len(train_target), 1)), train_target)
        return model.predict(np.zeros((len(test_features), 1)))
    if model_name == "SizeOnlyRidge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    elif model_name in {"MorganRBFGPR", "MorganRDKitGasteigerGPR"}:
        model = make_pipeline(StandardScaler(), _gpr_model())
    else:
        raise ValueError(f"unknown diagnostic model: {model_name}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model.fit(train_features, train_target)
        return model.predict(test_features)


def run_single_split_models(
    target: np.ndarray,
    morgan: np.ndarray,
    size: np.ndarray,
    *,
    model_names: Sequence[str] = MODEL_NAMES,
) -> dict[str, dict[str, float]]:
    train_indices, test_indices = deterministic_split(len(target), seed=SEED)
    feature_sets = {
        "DummyMean": np.zeros((len(target), 1), dtype=float),
        "SizeOnlyRidge": size,
        "MorganRBFGPR": morgan,
    }
    results: dict[str, dict[str, float]] = {}
    for model_name in model_names:
        features = feature_sets[model_name]
        prediction = _fit_predict(
            model_name,
            features[train_indices],
            np.asarray(target)[train_indices],
            features[test_indices],
        )
        results[model_name] = regression_metrics(
            np.asarray(target)[test_indices],
            prediction,
        )
    return results


def summarize_metric_rows(
    rows: Sequence[dict[str, object]],
) -> dict[str, dict[str, dict[str, float]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["model"])].append(row)
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for model_name, model_rows in grouped.items():
        summary[model_name] = {}
        for metric in ("mae", "rmse", "r2"):
            values = [float(row[metric]) for row in model_rows]
            summary[model_name][metric] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            }
    return summary


def run_repeated_cv(
    target: np.ndarray,
    morgan: np.ndarray,
    size: np.ndarray,
    *,
    molecule_ids: Sequence[str] | None = None,
    model_names: Sequence[str] = MODEL_NAMES,
) -> list[dict[str, object]]:
    target = np.asarray(target, dtype=float)
    if molecule_ids is None:
        molecule_ids = [str(index) for index in range(len(target))]
    if len(molecule_ids) != len(target):
        raise ValueError("molecule_ids must align with target")
    rows: list[dict[str, object]] = []
    splitter = RepeatedKFold(
        n_splits=CV_SPLITS,
        n_repeats=CV_REPEATS,
        random_state=SEED,
    )
    for fold_index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(target)))
    ):
        repeat = fold_index // CV_SPLITS
        fold = fold_index % CV_SPLITS
        for model_name in model_names:
            features = {
                "DummyMean": np.zeros((len(target), 1), dtype=float),
                "SizeOnlyRidge": size,
                "MorganRBFGPR": morgan,
            }[model_name]
            prediction = _fit_predict(
                model_name,
                features[train_indices],
                target[train_indices],
                features[test_indices],
            )
            rows.append(
                {
                    "model": model_name,
                    "seed": SEED,
                    "repeat": repeat,
                    "fold": fold,
                    "n_train": len(train_indices),
                    "n_test": len(test_indices),
                    "train_id_hash": _indices_hash(molecule_ids, train_indices),
                    "test_id_hash": _indices_hash(molecule_ids, test_indices),
                    **regression_metrics(target[test_indices], prediction),
                }
            )
    return rows


def run_learning_curve(
    target: np.ndarray,
    morgan: np.ndarray,
    size: np.ndarray,
    *,
    molecule_ids: Sequence[str] | None = None,
    train_sizes: Sequence[int] = TRAIN_SIZES,
    repeats: int = LEARNING_CURVE_REPEATS,
    model_names: Sequence[str] = MODEL_NAMES,
) -> list[dict[str, object]]:
    target = np.asarray(target, dtype=float)
    if molecule_ids is None:
        molecule_ids = [str(index) for index in range(len(target))]
    if len(molecule_ids) != len(target):
        raise ValueError("molecule_ids must align with target")
    original_train, original_test = deterministic_split(len(target), seed=SEED)
    rows: list[dict[str, object]] = []
    for train_size in train_sizes:
        if train_size > len(original_train):
            raise ValueError("train size exceeds original training partition")
        for run in range(repeats):
            rng = np.random.default_rng(SEED + 1000 * train_size + run)
            selected = rng.choice(original_train, size=train_size, replace=False)
            if set(selected).intersection(original_test):
                raise RuntimeError("learning-curve sample overlaps held-out test")
            for model_name in model_names:
                features = {
                    "DummyMean": np.zeros((len(target), 1), dtype=float),
                    "SizeOnlyRidge": size,
                    "MorganRBFGPR": morgan,
                }[model_name]
                prediction = _fit_predict(
                    model_name,
                    features[selected],
                    target[selected],
                    features[original_test],
                )
                rows.append(
                    {
                        "model": model_name,
                        "train_size": train_size,
                        "run": run,
                        "n_train": train_size,
                        "n_test": len(original_test),
                        "train_id_hash": _indices_hash(molecule_ids, selected),
                        "test_id_hash": _indices_hash(molecule_ids, original_test),
                        **regression_metrics(target[original_test], prediction),
                    }
                )
    return rows


def run_descriptor_enhancement(
    target: np.ndarray,
    descriptor_x: np.ndarray,
) -> dict[str, float]:
    train_indices, test_indices = deterministic_split(len(target), seed=SEED)
    prediction = _fit_predict(
        "MorganRDKitGasteigerGPR",
        descriptor_x[train_indices],
        np.asarray(target)[train_indices],
        descriptor_x[test_indices],
    )
    return regression_metrics(np.asarray(target)[test_indices], prediction)


def _write_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_comparison_plot(
    comparison: dict[str, dict[str, float]],
    path: Path,
) -> None:
    names = list(comparison)
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, metric, title in zip(
        axes,
        ("r2", "mae", "rmse"),
        ("R2", "MAE", "RMSE"),
        strict=True,
    ):
        axis.bar(names, [comparison[name][metric] for name in names])
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _write_learning_curve_plot(
    rows: Sequence[dict[str, object]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, metric in zip(axes, ("r2", "mae", "rmse"), strict=True):
        for model_name in MODEL_NAMES:
            model_rows = [row for row in rows if row["model"] == model_name]
            sizes = sorted({int(row["train_size"]) for row in model_rows})
            means = [
                float(
                    np.mean(
                        [
                            float(row[metric])
                            for row in model_rows
                            if int(row["train_size"]) == size
                        ]
                    )
                )
                for size in sizes
            ]
            stds = [
                float(
                    np.std(
                        [
                            float(row[metric])
                            for row in model_rows
                            if int(row["train_size"]) == size
                        ],
                        ddof=1,
                    )
                )
                for size in sizes
            ]
            axis.errorbar(sizes, means, yerr=stds, marker="o", capsize=2, label=model_name)
        axis.set_xlabel("Training compounds")
        axis.set_title(metric.upper())
        axis.grid(alpha=0.2)
    axes[0].legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _update_gpr_summary(
    path: Path,
    *,
    comparison: dict[str, dict[str, float]],
    cv_summary: dict[str, object],
    learning_summary: dict[str, object],
    descriptor_metrics: dict[str, float],
) -> None:
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["baseline_diagnostics"] = {
        "single_split_comparison": comparison,
        "cv": cv_summary,
        "learning_curve": learning_summary,
        "descriptor_enhancement": descriptor_metrics,
        "original_gpr_metrics_preserved": summary["metrics"],
    }
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_diagnostics(
    *,
    input_path: Path,
    comparison_path: Path,
    cv_path: Path,
    learning_path: Path,
    summary_path: Path,
    comparison_plot_path: Path,
    learning_plot_path: Path,
    gpr_summary_path: Path,
) -> dict[str, object]:
    rows = read_csv_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    size = build_size_matrix([row["smiles"] for row in rows])
    descriptor_x, descriptor_names = descriptor_features(
        [row["smiles"] for row in rows]
    )
    gasteiger_nonfinite = gasteiger_nonfinite_count(
        [row["smiles"] for row in rows]
    )
    train_indices, test_indices = deterministic_split(len(rows), seed=SEED)
    split_hash = "|".join(rows[int(index)]["inchikey"] for index in sorted(test_indices))
    comparison = run_single_split_models(target, morgan, size)
    molecule_ids = [row["inchikey"] for row in rows]
    cv_rows = run_repeated_cv(
        target,
        morgan,
        size,
        molecule_ids=molecule_ids,
    )
    learning_rows = run_learning_curve(
        target,
        morgan,
        size,
        molecule_ids=molecule_ids,
    )
    descriptor_metrics = run_descriptor_enhancement(target, descriptor_x)
    cv_summary = summarize_metric_rows(cv_rows)
    learning_summary: dict[str, object] = {}
    for model_name in MODEL_NAMES:
        learning_summary[model_name] = {}
        for train_size in TRAIN_SIZES:
            selected = [
                row
                for row in learning_rows
                if row["model"] == model_name and row["train_size"] == train_size
            ]
            learning_summary[model_name][str(train_size)] = {
                metric: {
                    "mean": float(np.mean([float(row[metric]) for row in selected])),
                    "std": float(np.std([float(row[metric]) for row in selected], ddof=1)),
                }
                for metric in ("mae", "rmse", "r2")
            }
    comparison_rows = [
        {
            "model": model_name,
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "r2": metrics["r2"],
            "n_train": len(train_indices),
            "n_test": len(test_indices),
            "seed": SEED,
            "split_id_hash": hashlib.sha256(split_hash.encode("utf-8")).hexdigest(),
        }
        for model_name, metrics in comparison.items()
    ]
    _write_rows(
        comparison_path,
        (
            "model",
            "mae",
            "rmse",
            "r2",
            "n_train",
            "n_test",
            "seed",
            "split_id_hash",
        ),
        comparison_rows,
    )
    _write_rows(
        cv_path,
        (
            "model",
            "seed",
            "repeat",
            "fold",
            "n_train",
            "n_test",
            "train_id_hash",
            "test_id_hash",
            "mae",
            "rmse",
            "r2",
        ),
        cv_rows,
    )
    _write_rows(
        learning_path,
        (
            "model",
            "train_size",
            "run",
            "n_train",
            "n_test",
            "train_id_hash",
            "test_id_hash",
            "mae",
            "rmse",
            "r2",
        ),
        learning_rows,
    )
    _write_comparison_plot(comparison, comparison_plot_path)
    _write_learning_curve_plot(learning_rows, learning_plot_path)
    summary = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "input_hash_mode": "canonical_text_lf_utf8",
        "compound_count": len(rows),
        "split": {
            "seed": SEED,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "split_id_hash": hashlib.sha256(split_hash.encode("utf-8")).hexdigest(),
        },
        "model_config": {
            "DummyMean": "DummyRegressor(strategy='mean')",
            "SizeOnlyRidge": "StandardScaler + Ridge(alpha=1.0), features=MW+HeavyAtoms",
            "MorganRBFGPR": (
                "StandardScaler + GaussianProcessRegressor; "
                "C(1)*RBF(length_scale=10)+WhiteKernel(noise_level=1); "
                "alpha=1e-6; normalize_y=True; n_restarts_optimizer=2"
            ),
            "descriptor_enhancement": (
                "Morgan count + 14 RDKit/Gasteiger descriptors; same StandardScaler+GPR"
            ),
            "cv_splitter": (
                "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)"
            ),
            "learning_curve_sampling": (
                "rng=default_rng(SEED + 1000*train_size + run); sample from "
                "the original deterministic 80-row train partition without replacement"
            ),
        },
        "single_split": comparison,
        "cv": {
            "n_splits": CV_SPLITS,
            "n_repeats": CV_REPEATS,
            "fold_rows": len(cv_rows),
            "models": cv_summary,
        },
        "learning_curve": {
            "train_sizes": list(TRAIN_SIZES),
            "repeats": LEARNING_CURVE_REPEATS,
            "fixed_test_count": len(test_indices),
            "rows": len(learning_rows),
            "summary": learning_summary,
        },
        "descriptor_enhancement": {
            "feature_names": list(descriptor_names),
            "gasteiger_nonfinite_atom_count": gasteiger_nonfinite,
            "gasteiger_nonfinite_policy": (
                "finite charges only; all-zero statistics if none are finite"
            ),
            "metrics": descriptor_metrics,
            "r2_gain_over_morgan": (
                descriptor_metrics["r2"] - comparison["MorganRBFGPR"]["r2"]
            ),
            "reached_r2_0_35": descriptor_metrics["r2"] >= 0.35,
        },
        "limitations": [
            "Only 100 compounds are available.",
            "CV and learning-curve estimates are sensitive to high-dielectric outliers.",
            "The descriptor enhancement is a single fixed quick test, not hyperparameter tuning.",
        ],
        "outputs": {
            "comparison_csv": comparison_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "cv_csv": cv_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "learning_curve_csv": learning_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "comparison_plot": comparison_plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "learning_curve_plot": learning_plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _update_gpr_summary(
        gpr_summary_path,
        comparison=comparison,
        cv_summary=cv_summary,
        learning_summary=learning_summary,
        descriptor_metrics=descriptor_metrics,
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--comparison-csv",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_baseline_comparison.csv"
        ),
    )
    parser.add_argument(
        "--cv-csv",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_gpr_repeated_cv.csv"
        ),
    )
    parser.add_argument(
        "--learning-csv",
        type=Path,
        default=(
            REPOSITORY_ROOT / "data" / "processed" / "dielectric_learning_curve.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "probes"
            / "dielectric_baseline_diagnostics_summary.json"
        ),
    )
    parser.add_argument(
        "--comparison-plot",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "probes"
            / "artifacts"
            / "dielectric_baseline_comparison.png"
        ),
    )
    parser.add_argument(
        "--learning-plot",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "probes"
            / "artifacts"
            / "dielectric_learning_curve.png"
        ),
    )
    parser.add_argument(
        "--gpr-summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_gpr_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_diagnostics(
        input_path=args.input,
        comparison_path=args.comparison_csv,
        cv_path=args.cv_csv,
        learning_path=args.learning_csv,
        summary_path=args.summary,
        comparison_plot_path=args.comparison_plot,
        learning_plot_path=args.learning_plot,
        gpr_summary_path=args.gpr_summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
