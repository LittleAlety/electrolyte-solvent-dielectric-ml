"""Diagnose the Batt-P30K dipole baseline without retraining the formal model."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.p2_battp30k_baseline import _model, train_test_indices

ATOMIC_TO_DEBYE = 2.5418
TARGET_UNIT = "atomic_units (e*bohr)"
MIN_STRATUM_SIZE = 100
MORGAN_METRIC_TOLERANCE = 1e-7
TARGET_UNIT_EVIDENCE = (
    {
        "source": "PiNN dipole documentation",
        "url": (
            "https://github.com/Teoroo-CMC/PiNN/blob/"
            "b166b8635a3ace9497ff34a80928a3a8d2b8eb01/docs/usage/dipole.md"
        ),
        "evidence": "PiNN dipole properties are documented in atomic units.",
    },
    {
        "source": "PiNN dipole model",
        "url": (
            "https://github.com/Teoroo-CMC/PiNN/blob/"
            "b166b8635a3ace9497ff34a80928a3a8d2b8eb01/pinn/models/dipole.py"
        ),
        "evidence": "The dipole model code operates on atomic-unit property tensors.",
    },
    {
        "source": "Batt-SLM dipole parameters",
        "url": (
            "https://github.com/Teoroo-CMC/Batt-SLM/blob/"
            "a5101e30c6975552d97e34f1e93461126715c862/Batt-P30K/params.yml"
        ),
        "evidence": (
            "d_scale=2.5412 and d_unit=2.5412 convert between atomic-unit and "
            "Debye scale during training. The standard physical conversion used "
            "for reporting is 2.5418; 2.5412 is upstream training rounding."
        ),
    },
)
UPSTREAM_TRAINING_SCALE = 2.5412


class MorganMetricMismatchError(RuntimeError):
    """Raised when an independently retrained Morgan model differs from formal metrics."""


def atomic_to_debye(values: np.ndarray) -> np.ndarray:
    """Convert dipoles from atomic units (e*bohr) to Debye."""

    return np.asarray(values, dtype=float) * ATOMIC_TO_DEBYE


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float | None]:
    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if target.shape != prediction.shape or target.ndim != 1:
        raise ValueError("target and prediction must be one-dimensional and aligned")
    if not len(target):
        raise ValueError("metrics require at least one observation")
    residual = target - prediction
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual**2)))
    if len(target) < 2 or float(np.var(target)) == 0.0:
        r2: float | None = None
    else:
        r2 = float(1.0 - np.sum(residual**2) / np.sum((target - np.mean(target)) ** 2))
    return {"mae": mae, "rmse": rmse, "r2": r2}


def metrics_both_units(
    target_au: np.ndarray,
    prediction_au: np.ndarray,
) -> dict[str, dict[str, float | None]]:
    return {
        "metrics_au": regression_metrics(target_au, prediction_au),
        "metrics_debye": regression_metrics(
            atomic_to_debye(target_au),
            atomic_to_debye(prediction_au),
        ),
    }


def distribution_diagnostics(target_au: np.ndarray) -> dict[str, object]:
    """Summarize the full target distribution in Debye units."""

    target_debye = atomic_to_debye(target_au)
    if target_debye.ndim != 1 or not len(target_debye):
        raise ValueError("target distribution requires a non-empty 1D array")
    quantile_probabilities = {
        "p01": 0.01,
        "p05": 0.05,
        "p10": 0.10,
        "p25": 0.25,
        "p50": 0.50,
        "p75": 0.75,
        "p90": 0.90,
        "p95": 0.95,
        "p99": 0.99,
        "p100": 1.0,
    }
    return {
        "count": len(target_debye),
        "min_debye": float(np.min(target_debye)),
        "max_debye": float(np.max(target_debye)),
        "mean_debye": float(np.mean(target_debye)),
        "std_debye": float(np.std(target_debye)),
        "quantiles_debye": {
            name: float(np.quantile(target_debye, probability))
            for name, probability in quantile_probabilities.items()
        },
        "counts": {
            "lt_0_5D": int(np.sum(target_debye < 0.5)),
            "0_5D_to_1D": int(np.sum((target_debye >= 0.5) & (target_debye < 1.0))),
            "1D_to_3D": int(np.sum((target_debye >= 1.0) & (target_debye <= 3.0))),
            "gt_3D": int(np.sum(target_debye > 3.0)),
        },
        "fractions": {
            "lt_0_5D": float(np.mean(target_debye < 0.5)),
            "0_5D_to_1D": float(
                np.mean((target_debye >= 0.5) & (target_debye < 1.0))
            ),
            "1D_to_3D": float(
                np.mean((target_debye >= 1.0) & (target_debye <= 3.0))
            ),
            "gt_3D": float(np.mean(target_debye > 3.0)),
        },
    }


def _stratum_masks(target_debye: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "lt_0_5D": target_debye < 0.5,
        "0_5D_to_1D": (target_debye >= 0.5) & (target_debye < 1.0),
        "1D_to_3D": (target_debye >= 1.0) & (target_debye <= 3.0),
        "gt_3D": target_debye > 3.0,
    }


def stratified_diagnostics(
    target_au: np.ndarray,
    prediction_au: np.ndarray,
) -> dict[str, object]:
    target_au = np.asarray(target_au, dtype=float)
    prediction_au = np.asarray(prediction_au, dtype=float)
    target_debye = atomic_to_debye(target_au)
    strata: dict[str, object] = {}
    for name, mask in _stratum_masks(target_debye).items():
        count = int(np.sum(mask))
        metrics = (
            metrics_both_units(target_au[mask], prediction_au[mask]) if count else None
        )
        status = (
            "empty"
            if count == 0
            else "insufficient"
            if count < MIN_STRATUM_SIZE
            else "reported"
        )
        strata[name] = {
            "n": count,
            "fraction": float(count / len(target_debye)),
            "status": status,
            "metrics": metrics,
        }
    return {
        "minimum_reportable_n": MIN_STRATUM_SIZE,
        "overall": {
            "n": len(target_debye),
            **metrics_both_units(target_au, prediction_au),
        },
        "strata": strata,
    }


def size_features(smiles: str) -> np.ndarray:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES for size features: {smiles!r}")
    return np.asarray(
        [
            float(Descriptors.MolWt(molecule)),
            float(molecule.GetNumHeavyAtoms()),
        ],
        dtype=float,
    )


def build_size_feature_matrix(smiles_values: Sequence[str]) -> np.ndarray:
    return np.vstack([size_features(str(smiles)) for smiles in smiles_values])


def evaluate_model_baselines(
    target_au: np.ndarray,
    morgan_x: np.ndarray,
    size_x: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    metric_tolerance: float = MORGAN_METRIC_TOLERANCE,
) -> dict[str, object]:
    target_au = np.asarray(target_au, dtype=float)
    morgan_x = np.asarray(morgan_x, dtype=float)
    size_x = np.asarray(size_x, dtype=float)
    dummy = DummyRegressor(strategy="mean")
    size_model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    morgan_model = _model(seed=42)
    dummy.fit(np.zeros((len(train_indices), 1)), target_au[train_indices])
    size_model.fit(size_x[train_indices], target_au[train_indices])
    morgan_model.fit(morgan_x[train_indices], target_au[train_indices])
    dummy_prediction = dummy.predict(
        np.zeros((len(test_indices), 1), dtype=float)
    )
    size_prediction = size_model.predict(size_x[test_indices])
    morgan_prediction = morgan_model.predict(morgan_x[test_indices])
    return {
        "split": {
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "seed": 42,
        },
        "dummy": {
            "model": "DummyRegressor(strategy='mean')",
            "n_test": len(test_indices),
            **metrics_both_units(target_au[test_indices], dummy_prediction),
        },
        "size_only_ridge": {
            "model": "StandardScaler + Ridge(alpha=1.0), features=MW+heavy_atoms",
            "n_test": len(test_indices),
            **metrics_both_units(target_au[test_indices], size_prediction),
        },
        "morgan_xgboost": {
            "model": "Morgan count fingerprint radius=2, 2048 bits + XGBoost",
            "n_test": len(test_indices),
            "numeric_tolerance": metric_tolerance,
            **metrics_both_units(target_au[test_indices], morgan_prediction),
        },
    }


def audit_morgan_metrics(
    recomputed_metrics_au: Mapping[str, float],
    formal_metrics_au: Mapping[str, object] | None,
    *,
    tolerance: float,
) -> dict[str, object]:
    """Compare an independent Morgan retrain with the formal summary metrics."""

    if formal_metrics_au is None:
        return {
            "formal_metrics_available": False,
            "recomputed_metrics_au": dict(recomputed_metrics_au),
            "absolute_differences": {},
            "tolerance": tolerance,
            "passed": None,
        }
    missing = {
        metric
        for metric in ("mae", "rmse", "r2")
        if metric not in formal_metrics_au
    }
    if missing:
        raise MorganMetricMismatchError(
            f"formal metrics missing required fields: {sorted(missing)}"
        )
    differences = {
        metric: abs(
            float(recomputed_metrics_au[metric]) - float(formal_metrics_au[metric])
        )
        for metric in ("mae", "rmse", "r2")
    }
    failures = {
        metric: difference
        for metric, difference in differences.items()
        if difference > tolerance
    }
    if failures:
        detail = ", ".join(
            f"{metric}={difference:.12g}" for metric, difference in failures.items()
        )
        raise MorganMetricMismatchError(
            f"recomputed Morgan metrics exceed tolerance {tolerance}: {detail}"
        )
    return {
        "formal_metrics_available": True,
        "formal_metrics_au": {
            metric: float(formal_metrics_au[metric])
            for metric in ("mae", "rmse", "r2")
        },
        "recomputed_metrics_au": dict(recomputed_metrics_au),
        "absolute_differences": differences,
        "tolerance": tolerance,
        "passed": True,
    }


def update_p2_summary_units(summary_path: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = summary.get("final_metrics")
    summary["target_units"] = TARGET_UNIT
    summary["target_unit_evidence"] = list(TARGET_UNIT_EVIDENCE)
    summary["atomic_to_debye"] = ATOMIC_TO_DEBYE
    summary["upstream_training_scale"] = UPSTREAM_TRAINING_SCALE
    summary["unit_conversion_note"] = (
        "2.5418 is the standard physical a.u.-to-Debye conversion; 2.5412 is "
        "the rounded scale in the upstream training configuration."
    )
    if isinstance(metrics, Mapping):
        summary["final_metrics_units"] = TARGET_UNIT
        summary["final_metrics_debye"] = {
            "mae": float(metrics["mae"]) * ATOMIC_TO_DEBYE,
            "rmse": float(metrics["rmse"]) * ATOMIC_TO_DEBYE,
            "r2": float(metrics["r2"]),
        }
    summary["unit_resolution"] = (
        "High-confidence source-code inference: Batt-SLM is built on PiNN, whose "
        "dipole properties use atomic units and whose parameters define the "
        "a.u.-to-Debye scale."
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_predictions(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return (
        np.asarray([float(row["target"]) for row in rows], dtype=float),
        np.asarray([float(row["prediction"]) for row in rows], dtype=float),
    )


def _csv_rows(summary: dict[str, object]) -> list[dict[str, object]]:
    distribution = summary["target_distribution"]
    model_comparison = summary["model_comparison"]
    stratified = summary["stratified_test_metrics"]
    assert isinstance(distribution, Mapping)
    assert isinstance(model_comparison, Mapping)
    assert isinstance(stratified, Mapping)
    rows: list[dict[str, object]] = []
    counts = distribution["counts"]
    fractions = distribution["fractions"]
    assert isinstance(counts, Mapping)
    assert isinstance(fractions, Mapping)
    for name in ("lt_0_5D", "0_5D_to_1D", "1D_to_3D", "gt_3D"):
        rows.append(
            {
                "analysis": "target_distribution",
                "subset": name,
                "n": counts[name],
                "fraction": fractions[name],
                "status": "observed",
            }
        )
    for name, value in distribution["quantiles_debye"].items():
        rows.append(
            {
                "analysis": "target_quantile_debye",
                "subset": name,
                "value_debye": value,
                "status": "observed",
            }
        )
    for name in ("dummy", "size_only_ridge", "morgan_xgboost"):
        model = model_comparison[name]
        assert isinstance(model, Mapping)
        metrics_au = model["metrics_au"]
        metrics_debye = model["metrics_debye"]
        assert isinstance(metrics_au, Mapping)
        assert isinstance(metrics_debye, Mapping)
        rows.append(
            {
                "analysis": "model_comparison",
                "subset": name,
                "n": model["n_test"],
                "mae_au": metrics_au["mae"],
                "rmse_au": metrics_au["rmse"],
                "r2": metrics_au["r2"],
                "mae_debye": metrics_debye["mae"],
                "rmse_debye": metrics_debye["rmse"],
                "status": "reported",
            }
        )
    strata = stratified["strata"]
    assert isinstance(strata, Mapping)
    for name, item in strata.items():
        assert isinstance(item, Mapping)
        metrics = item["metrics"]
        metrics_au = metrics["metrics_au"] if metrics else {}
        metrics_debye = metrics["metrics_debye"] if metrics else {}
        rows.append(
            {
                "analysis": "test_stratum",
                "subset": name,
                "n": item["n"],
                "fraction": item["fraction"],
                "mae_au": metrics_au.get("mae", ""),
                "rmse_au": metrics_au.get("rmse", ""),
                "r2": metrics_au.get("r2", ""),
                "mae_debye": metrics_debye.get("mae", ""),
                "rmse_debye": metrics_debye.get("rmse", ""),
                "status": item["status"],
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "analysis",
        "subset",
        "n",
        "fraction",
        "value_au",
        "value_debye",
        "mae_au",
        "rmse_au",
        "r2",
        "mae_debye",
        "rmse_debye",
        "status",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_target_distribution_plot(target_au: np.ndarray, path: Path) -> None:
    target_debye = atomic_to_debye(target_au)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(8, 4.8))
    upper = 10.0
    axis.hist(
        target_debye,
        bins=80,
        range=(0.0, upper),
        color="#2563eb",
        alpha=0.85,
        edgecolor="white",
        linewidth=0.2,
    )
    for threshold, color in ((0.5, "#f59e0b"), (1.0, "#16a34a"), (3.0, "#dc2626")):
        axis.axvline(threshold, color=color, linewidth=1.4)
    above = int(np.sum(target_debye > upper))
    axis.set_xlabel(f"Dipole magnitude (Debye); {above} values above {upper:g} D clipped")
    axis.set_ylabel("Molecule count")
    axis.set_title("Batt-P30K target distribution")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def write_model_comparison_plot(
    model_comparison: Mapping[str, object],
    path: Path,
) -> None:
    names = ("dummy", "size_only_ridge", "morgan_xgboost")
    labels = ("Dummy", "Size + Ridge", "Morgan + XGBoost")
    colors = ("#64748b", "#0f766e", "#2563eb")
    metrics: dict[str, list[float]] = {"r2": [], "mae_debye": [], "rmse_debye": []}
    for name in names:
        model = model_comparison[name]
        assert isinstance(model, Mapping)
        metrics_au = model["metrics_au"]
        metrics_debye = model["metrics_debye"]
        assert isinstance(metrics_au, Mapping)
        assert isinstance(metrics_debye, Mapping)
        metrics["r2"].append(float(metrics_au["r2"]))
        metrics["mae_debye"].append(float(metrics_debye["mae"]))
        metrics["rmse_debye"].append(float(metrics_debye["rmse"]))
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, metric, title in zip(
        axes,
        ("r2", "mae_debye", "rmse_debye"),
        ("R2", "MAE (Debye)", "RMSE (Debye)"),
        strict=True,
    ):
        axis.bar(labels, metrics[metric], color=colors)
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_diagnostics(
    *,
    cache_path: Path,
    predictions_path: Path,
    p2_summary_path: Path,
    csv_path: Path,
    summary_path: Path,
    distribution_plot_path: Path,
    comparison_plot_path: Path,
) -> dict[str, object]:
    cached = np.load(cache_path, allow_pickle=False)
    target_au = cached["y"].astype(float)
    smiles = cached["smiles"]
    size_x = build_size_feature_matrix(smiles)
    train_indices, test_indices = train_test_indices(len(target_au), seed=42)
    p2_summary = json.loads(p2_summary_path.read_text(encoding="utf-8"))
    morgan_x = cached["X"]
    model_comparison = evaluate_model_baselines(
        target_au,
        morgan_x,
        size_x,
        train_indices,
        test_indices,
        metric_tolerance=MORGAN_METRIC_TOLERANCE,
    )
    recomputed_morgan_metrics = model_comparison["morgan_xgboost"]["metrics_au"]
    formal_metrics = p2_summary.get("final_metrics")
    morgan_audit = audit_morgan_metrics(
        recomputed_morgan_metrics,
        formal_metrics if isinstance(formal_metrics, Mapping) else None,
        tolerance=MORGAN_METRIC_TOLERANCE,
    )
    prediction_target_au, prediction_au = _read_predictions(predictions_path)
    distribution = distribution_diagnostics(target_au)
    stratified = stratified_diagnostics(prediction_target_au, prediction_au)
    fractions = distribution["fractions"]
    assert isinstance(fractions, Mapping)
    dummy_r2 = float(model_comparison["dummy"]["metrics_au"]["r2"])
    size_only_r2 = float(model_comparison["size_only_ridge"]["metrics_au"]["r2"])
    morgan_r2 = float(model_comparison["morgan_xgboost"]["metrics_au"]["r2"])
    diagnosed = {
        "schema_version": 1,
        "cache_schema_version": int(cached["schema_version"]),
        "source_sha256": str(cached["source_sha256"].item()),
        "target_unit": {
            "unit": TARGET_UNIT,
            "atomic_to_debye": ATOMIC_TO_DEBYE,
            "evidence": list(TARGET_UNIT_EVIDENCE),
            "confidence": "high_source_code_inference",
            "hdf5_metadata_declares_unit": False,
        },
        "target_distribution": distribution,
        "stratified_test_metrics": stratified,
        "model_comparison": model_comparison,
        "morgan_retraining_audit": morgan_audit,
        "diagnosis": {
            "pipeline_green": True,
            "formal_r2": float(recomputed_morgan_metrics["r2"]),
            "dummy_r2": dummy_r2,
            "size_only_r2": size_only_r2,
            "morgan_xgboost_r2": morgan_r2,
            "pass_r2_gt_0_8": bool(float(recomputed_morgan_metrics["r2"]) > 0.8),
            "near_zero_lt_1D_fraction": float(
                fractions["lt_0_5D"] + fractions["0_5D_to_1D"]
            ),
            "near_zero_compression_primary_explanation": (
                float(fractions["lt_0_5D"] + fractions["0_5D_to_1D"]) >= 0.25
            ),
            "root_cause": (
                "The Morgan count fingerprint captures 2D connectivity but not "
                "3D geometry or conformational dipole orientation. Dummy and "
                "size-only provide near-zero explanatory power, while Morgan+XGBoost "
                "captures a real but insufficient signal."
            ),
            "next_step": "Chemprop/D-MPNN or a 3D/GNN representation.",
        },
        "outputs": {
            "diagnostics_csv": csv_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "target_distribution_plot": (
                distribution_plot_path.relative_to(REPOSITORY_ROOT).as_posix()
            ),
            "model_comparison_plot": (
                comparison_plot_path.relative_to(REPOSITORY_ROOT).as_posix()
            ),
        },
    }
    _write_csv(csv_path, _csv_rows(diagnosed))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(diagnosed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_target_distribution_plot(target_au, distribution_plot_path)
    write_model_comparison_plot(model_comparison, comparison_plot_path)
    update_p2_summary_units(p2_summary_path)
    return diagnosed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "p2_battp30k_count_features.npz"
        ),
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "p2_test_predictions.csv",
    )
    parser.add_argument(
        "--p2-summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p2_summary.json",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "p2_diagnostics.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p2_diagnostics_summary.json",
    )
    parser.add_argument(
        "--distribution-plot",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "probes"
            / "artifacts"
            / "p2_target_distribution_debye.png"
        ),
    )
    parser.add_argument(
        "--comparison-plot",
        type=Path,
        default=(
            REPOSITORY_ROOT / "probes" / "artifacts" / "p2_model_comparison.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_diagnostics(
        cache_path=args.cache,
        predictions_path=args.predictions,
        p2_summary_path=args.p2_summary,
        csv_path=args.csv,
        summary_path=args.summary,
        distribution_plot_path=args.distribution_plot,
        comparison_plot_path=args.comparison_plot,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
