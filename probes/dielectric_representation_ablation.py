"""Compare Morgan, xTB-physical, and combined representations on dielectric v0.2."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from scipy.stats import rankdata
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import RepeatedKFold
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

DATASET_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"

SEED = 42
N_SPLITS = 5
N_REPEATS = 10
FP_RADIUS = 2
FP_SIZE = 2048
XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 2,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "max_bin": 64,
    "n_jobs": 1,
}
PHYSICAL_COLUMNS = (
    "T_K",
    "formal_charge",
    "heavy_atom_count",
    "hbd",
    "hba",
    "tpsa_A2",
    "molecular_volume_A3",
    "dipole_D",
    "polarizability_A3",
    "mu_sq_over_Vm",
    "alpha_over_Vm",
    "total_energy_hartree",
    "homo_lumo_gap_ev",
)
REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
CV_COLUMNS = (
    "representation",
    "repeat",
    "fold",
    "seed",
    "train_count",
    "test_count",
    "mae",
    "rmse",
    "r2",
    "spearman",
    "auc_gt15",
    "auc_gt30",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
    "model_params",
)
REPEAT_COLUMNS = (
    "representation",
    "repeat",
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
PREDICTION_COLUMNS = (
    "representation",
    "repeat",
    "fold",
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "target",
    "prediction",
    "abs_error",
    "target_stratum",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def morgan_count_features(smiles_values: Sequence[str]) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=FP_RADIUS,
        fpSize=FP_SIZE,
    )
    rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        rows.append(generator.GetCountFingerprintAsNumPy(molecule))
    return np.vstack(rows).astype(np.float32, copy=False)


def physical_feature_matrix(rows: Sequence[Mapping[str, str]]) -> np.ndarray:
    values = np.asarray(
        [[float(row[column]) for column in PHYSICAL_COLUMNS] for row in rows],
        dtype=np.float64,
    )
    if not np.isfinite(values).all():
        raise ValueError("physical feature matrix contains non-finite values")
    return values


def read_model_ready_map(dataset_path: Path = DATASET_PATH) -> dict[str, bool]:
    """Return `inchikey -> model_ready` for the authoritative dataset roster.

    `model_ready` is the dataset-level gate: a row is `false` when its value is
    an unresolved source conflict or is awaiting primary confirmation. Because
    every dielectric fit goes through `read_modelling_rows`, this map is what
    stops a contested label from reaching a training fold.
    """

    status = {
        row["inchikey"]: row.get("model_ready", "").strip().lower() == "true"
        for row in read_csv_rows(dataset_path)
    }
    if not status:
        raise ValueError(f"empty dataset roster: {dataset_path}")
    return status


def read_modelling_rows(
    path: Path,
    *,
    dataset_path: Path = DATASET_PATH,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Split a physical-feature table into (modelling, failed, withheld).

    `withheld` holds rows whose dataset record is `model_ready != true`. They
    are returned instead of dropped, so every caller has to account for them
    rather than quietly fitting a contested value.
    """

    records = read_csv_rows(path)
    ready = read_model_ready_map(dataset_path)
    unknown = sorted({row["inchikey"] for row in records} - set(ready))
    if unknown:
        raise ValueError(
            "physical-feature rows are absent from the dataset roster, so their "
            "model_ready status is unknown: " + ", ".join(unknown)
        )
    eligible = [row for row in records if ready[row["inchikey"]]]
    withheld = [row for row in records if not ready[row["inchikey"]]]
    successful = [row for row in eligible if row["status"] != "error"]
    failed = [row for row in eligible if row["status"] == "error"]
    for row in successful:
        missing = [column for column in PHYSICAL_COLUMNS if row[column] == ""]
        if missing:
            raise ValueError(
                f"{row['name']} is missing physical columns: {', '.join(missing)}"
            )
    return successful, failed, withheld


def _fit_predict_model(
    train_features: np.ndarray,
    test_features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> np.ndarray:
    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(train_features[train_indices], target[train_indices])
    return model.predict(test_features[test_indices])


def fit_predict_representation(
    representation: str,
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, str]:
    if representation == "Morgan":
        prediction = _fit_predict_model(
            morgan,
            morgan,
            target,
            train_indices,
            test_indices,
            seed,
        )
    elif representation == "Physical":
        prediction = _fit_predict_model(
            physical,
            physical,
            target,
            train_indices,
            test_indices,
            seed,
        )
    elif representation == "Morgan+Physical":
        morgan_prediction = _fit_predict_model(
            morgan,
            morgan,
            target,
            train_indices,
            test_indices,
            seed,
        )
        physical_prediction = _fit_predict_model(
            physical,
            physical,
            target,
            train_indices,
            test_indices,
            seed,
        )
        prediction = 0.5 * (morgan_prediction + physical_prediction)
    else:
        raise ValueError(f"unknown representation: {representation}")

    signature = json.dumps(
        {**XGB_PARAMS, "random_state": seed},
        sort_keys=True,
        separators=(",", ":"),
    )
    return np.maximum(prediction, 1.0), signature


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


def _safe_spearman(target: np.ndarray, prediction: np.ndarray) -> float:
    if np.unique(target).size < 2 or np.unique(prediction).size < 2:
        return float("nan")
    target_rank = rankdata(target, method="average")
    prediction_rank = rankdata(prediction, method="average")
    return float(np.corrcoef(target_rank, prediction_rank)[0, 1])


def _safe_auc(target: np.ndarray, prediction: np.ndarray, threshold: float) -> float:
    labels = target > threshold
    if np.unique(labels).size < 2:
        return float("nan")
    return float(roc_auc_score(labels, prediction))


def _stratum(target: float) -> str:
    if target < 20.0:
        return "lt20"
    if target <= 60.0:
        return "20_60"
    return "gt60"


def _stratified_mae(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    errors = np.abs(target - prediction)
    result: dict[str, float] = {}
    for name, mask in (
        ("lt20", target < 20.0),
        ("20_60", (target >= 20.0) & (target <= 60.0)),
        ("gt60", target > 60.0),
    ):
        result[name] = float(np.mean(errors[mask])) if np.any(mask) else float("nan")
    return result


def evaluate_repeat(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    metrics = regression_metrics(target, prediction)
    metrics["spearman"] = _safe_spearman(target, prediction)
    metrics["auc_gt15"] = _safe_auc(target, prediction, 15.0)
    metrics["auc_gt30"] = _safe_auc(target, prediction, 30.0)
    for stratum, value in _stratified_mae(target, prediction).items():
        metrics[f"mae_{stratum}"] = value
    return metrics


def _mean_std(values: Sequence[float]) -> dict[str, float | int | None]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0,
        "n": int(finite.size),
    }


def summarize_repeats(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["representation"])].append(row)
    result: dict[str, dict[str, dict[str, float | int | None]]] = {}
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
    for representation in REPRESENTATIONS:
        result[representation] = {
            metric: _mean_std([float(row[metric]) for row in grouped[representation]])
            for metric in metric_names
        }
    return result


def _write_plot(
    summary: Mapping[str, Mapping[str, Mapping[str, object]]],
    path: Path,
) -> None:
    labels = list(REPRESENTATIONS)
    colors = ("#2563eb", "#dc2626", "#059669")
    figure, axes = plt.subplots(2, 2, figsize=(11.0, 8.0))

    metric_specs = (
        ("r2", "R2"),
        ("spearman", "Spearman rho"),
        ("mae", "MAE"),
        ("rmse", "RMSE"),
    )
    for axis, (metric, title) in zip(axes.flat, metric_specs, strict=True):
        means = [float(summary[name][metric]["mean"]) for name in labels]
        errors = [float(summary[name][metric]["std"]) for name in labels]
        axis.bar(labels, means, yerr=errors, color=colors, capsize=3)
        axis.set_title(f"{title} across 10 repeats")
        axis.axhline(0.0, color="#111827", linewidth=0.8)
        axis.tick_params(axis="x", rotation=15)
        axis.grid(axis="y", alpha=0.25)

    figure.suptitle("Dielectric v0.2 representation ablation")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_experiment(
    *,
    input_path: Path,
    source_path: Path,
    exclusions_path: Path,
    dataset_path: Path = DATASET_PATH,
    cv_path: Path,
    repeat_path: Path,
    predictions_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict[str, object]:
    rows, failed_rows, withheld_rows = read_modelling_rows(
        input_path,
        dataset_path=dataset_path,
    )
    source_rows = read_csv_rows(source_path)
    exclusions = read_csv_rows(exclusions_path) if exclusions_path.is_file() else []
    source_keys = {row["inchikey"] for row in source_rows}
    # An exclusion only applies to a lineage that actually contains the row;
    # rows excluded from a different revision are reported, never ignored.
    all_excluded_keys = {row["inchikey"] for row in exclusions}
    excluded_keys = all_excluded_keys & source_keys
    excluded_not_in_source = sorted(all_excluded_keys - source_keys)
    if (
        len(rows)
        + len(failed_rows)
        + len(withheld_rows)
        + len(excluded_keys)
        != len(source_rows)
    ):
        raise ValueError(
            "accounting mismatch: successful + failed + withheld + excluded "
            "!= source rows"
        )
    if len(rows) < N_SPLITS:
        raise ValueError("not enough successful physical feature rows")
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    physical = physical_feature_matrix(rows)
    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )

    cv_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    repeat_predictions: dict[tuple[str, int], np.ndarray] = {}
    for representation in REPRESENTATIONS:
        for repeat in range(N_REPEATS):
            repeat_predictions[(representation, repeat)] = np.full(len(rows), np.nan)

    for repeat, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(rows)))
    ):
        fold = repeat % N_SPLITS
        repeat_number = repeat // N_SPLITS
        for representation in REPRESENTATIONS:
            prediction, model_params = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_indices,
                test_indices=test_indices,
                seed=SEED + repeat,
            )
            repeat_predictions[(representation, repeat_number)][test_indices] = prediction
            metrics = regression_metrics(target[test_indices], prediction)
            strata = _stratified_mae(target[test_indices], prediction)
            cv_rows.append(
                {
                    "representation": representation,
                    "repeat": repeat_number,
                    "fold": fold,
                    "seed": SEED + repeat,
                    "train_count": len(train_indices),
                    "test_count": len(test_indices),
                    **{key: f"{value:.12g}" for key, value in metrics.items()},
                    "spearman": f"{_safe_spearman(target[test_indices], prediction):.12g}",
                    "auc_gt15": f"{_safe_auc(target[test_indices], prediction, 15.0):.12g}",
                    "auc_gt30": f"{_safe_auc(target[test_indices], prediction, 30.0):.12g}",
                    "mae_lt20": f"{strata['lt20']:.12g}",
                    "mae_20_60": f"{strata['20_60']:.12g}",
                    "mae_gt60": f"{strata['gt60']:.12g}",
                    "model_params": model_params,
                }
            )
            for row_index, predicted in zip(
                test_indices,
                prediction,
                strict=True,
            ):
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
                        "target_stratum": _stratum(float(target[row_index])),
                    }
                )
            print(
                json.dumps(
                    {
                        "repeat": repeat_number,
                        "fold": fold,
                        "representation": representation,
                        "r2": f"{metrics['r2']:.6f}",
                    }
                ),
                flush=True,
            )

    repeat_rows: list[dict[str, object]] = []
    for representation in REPRESENTATIONS:
        for repeat in range(N_REPEATS):
            prediction = repeat_predictions[(representation, repeat)]
            if not np.isfinite(prediction).all():
                raise ValueError(f"incomplete OOF predictions for {representation}/{repeat}")
            metrics = evaluate_repeat(target, prediction)
            repeat_rows.append(
                {
                    "representation": representation,
                    "repeat": repeat,
                    **metrics,
                }
            )

    summary = summarize_repeats(repeat_rows)
    write_csv_rows(repeat_path, REPEAT_COLUMNS, repeat_rows)
    payload: dict[str, object] = {
        "schema_version": 1,
        "input_path": portable_relative_path(input_path, root=REPOSITORY_ROOT),
        "input_sha256": canonical_text_sha256(input_path),
        "source_path": portable_relative_path(source_path, root=REPOSITORY_ROOT),
        "source_sha256": canonical_text_sha256(source_path),
        "source_count": len(source_rows),
        "compound_count": len(rows),
        "excluded_count": len(excluded_keys),
        "excluded_inchikeys": sorted(excluded_keys),
        "exclusion_file_count": len(all_excluded_keys),
        "excluded_not_in_source": excluded_not_in_source,
        "exclusions_path": portable_relative_path(
            exclusions_path,
            root=REPOSITORY_ROOT,
        ),
        "exclusions_sha256": (
            canonical_text_sha256(exclusions_path)
            if exclusions_path.is_file()
            else None
        ),
        "dataset_path": portable_relative_path(dataset_path, root=REPOSITORY_ROOT),
        "dataset_sha256": canonical_text_sha256(dataset_path),
        "model_ready_gate": (
            "rows whose dataset record is model_ready != true are withheld "
            "from every fit and reported explicitly"
        ),
        "failed_physical_feature_count": len(failed_rows),
        "failed_physical_feature_names": [row["name"] for row in failed_rows],
        "withheld_not_model_ready_count": len(withheld_rows),
        "withheld_not_model_ready_names": [row["name"] for row in withheld_rows],
        "withheld_not_model_ready_inchikeys": [
            row["inchikey"] for row in withheld_rows
        ],
        "representations": {
            "Morgan": {
                "type": "Morgan count fingerprint",
                "radius": FP_RADIUS,
                "fp_size": FP_SIZE,
            },
            "Physical": {
                "type": "GFN2-xTB and RDKit physical descriptors",
                "columns": list(PHYSICAL_COLUMNS),
            },
            "Morgan+Physical": {
                "type": "equal-weight ensemble of separately trained Morgan and Physical models",
                "components": ["Morgan", "Physical"],
                "component_weight": 0.5,
            },
        },
        "model": {
            "name": "XGBRegressor",
            "parameters": XGB_PARAMS,
            "random_state_scheme": (
                "42 + global RepeatedKFold split index; consecutive folds use "
                "different seeds"
            ),
        },
        "validation": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
            "metrics": [
                "mae",
                "rmse",
                "r2",
                "spearman",
                "auc_gt15",
                "auc_gt30",
                "stratified_mae",
            ],
            "target_transform": "none",
            "prediction_constraint": "clip to dielectric >= 1",
        },
        "aggregation": (
            "Per repeat, concatenate the five fold-held-out predictions into a "
            "complete OOF vector; compute metrics on that vector; then average "
            "the ten repeat-level metrics. Per-fold metrics are diagnostic only."
        ),
        "predictions_clipped": True,
        "summary": summary,
        "outputs": {
            "cv_csv": portable_relative_path(cv_path, root=REPOSITORY_ROOT),
            "repeat_csv": portable_relative_path(
                repeat_path,
                root=REPOSITORY_ROOT,
            ),
            "predictions_csv": portable_relative_path(
                predictions_path,
                root=REPOSITORY_ROOT,
            ),
            "summary_json": portable_relative_path(
                summary_path,
                root=REPOSITORY_ROOT,
            ),
            "plot": portable_relative_path(plot_path, root=REPOSITORY_ROOT),
        },
    }
    write_csv_rows(cv_path, CV_COLUMNS, cv_rows)
    write_csv_rows(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(summary, plot_path)
    return payload


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
        "--source",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v02.csv",
    )
    parser.add_argument(
        "--exclusions",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_v02_exclusions.csv",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="dataset roster that supplies the model_ready gate",
    )
    parser.add_argument(
        "--repeat-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_representation_ablation_repeats.csv",
    )
    parser.add_argument(
        "--cv-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_representation_ablation_cv.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_representation_ablation_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "dielectric_representation_ablation_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_representation_ablation.png",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help=(
            "re-render --plot from the committed --summary-output instead of "
            "re-running the benchmark; use this to reproduce a figure whose "
            "rendered file has to be regenerated without refitting a model"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.plot_only:
        payload = json.loads(args.summary_output.read_text(encoding="utf-8"))
        _write_plot(payload["summary"], args.plot)
        print(json.dumps({"plot": args.plot.relative_to(REPOSITORY_ROOT).as_posix()}))
        return 0
    payload = run_experiment(
        input_path=args.input,
        source_path=args.source,
        exclusions_path=args.exclusions,
        dataset_path=args.dataset,
        cv_path=args.cv_output,
        repeat_path=args.repeat_output,
        predictions_path=args.predictions_output,
        summary_path=args.summary_output,
        plot_path=args.plot,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
