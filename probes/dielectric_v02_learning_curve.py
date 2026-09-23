"""Measure whether the v0.2 additions improve the fixed v0.1 test split."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

SEED = 42
TRAIN_SIZES = {
    "v0.1": (20, 40, 60, 80),
    "v0.2": (20, 40, 60, 80, 120, 160, 180),
}
REPEATS = 10


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


def _indices_hash(ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def _fit_predict(
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
) -> np.ndarray:
    scaler = StandardScaler()
    train_features = scaler.fit_transform(features[train_indices])
    test_features = scaler.transform(features[test_indices])
    kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
        noise_level=1.0
    )
    model = GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=2,
        random_state=SEED,
    )
    model.fit(train_features, target[train_indices])
    return model.predict(test_features)


def run_comparison(
    v01_rows: Sequence[dict[str, str]],
    v02_rows: Sequence[dict[str, str]],
    *,
    train_sizes: Mapping[str, Sequence[int]] = TRAIN_SIZES,
    repeats: int = REPEATS,
) -> list[dict[str, object]]:
    from dielectric_gpr_baseline import deterministic_split, morgan_count_features

    _, v01_test = deterministic_split(len(v01_rows), seed=SEED)
    test_keys = [v01_rows[index]["inchikey"] for index in v01_test]
    test_key_set = set(test_keys)
    v01_training_indices = np.asarray(
        [
            index
            for index, row in enumerate(v01_rows)
            if row["inchikey"] not in test_key_set
        ],
        dtype=int,
    )
    v02_test_indices = np.asarray(
        [
            index
            for index, row in enumerate(v02_rows)
            if row["inchikey"] in test_key_set
        ],
        dtype=int,
    )
    if len(v02_test_indices) != len(v01_test):
        raise ValueError("fixed v0.1 test compounds were not preserved in v0.2")
    v02_training_indices = np.asarray(
        [
            index
            for index, row in enumerate(v02_rows)
            if row["inchikey"] not in test_key_set
        ],
        dtype=int,
    )
    all_features = morgan_count_features([row["smiles"] for row in v02_rows])
    all_target = np.asarray([float(row["dielectric"]) for row in v02_rows])
    all_ids = [row["inchikey"] for row in v02_rows]

    pools = {
        "v0.1": v01_training_indices,
        "v0.2": v02_training_indices,
    }
    rows: list[dict[str, object]] = []
    for dataset_name, pool in pools.items():
        for train_size in train_sizes[dataset_name]:
            if train_size > len(pool):
                raise ValueError(f"{dataset_name} training pool is too small")
            for run in range(repeats):
                rng = np.random.default_rng(SEED + 1000 * train_size + run)
                selected = rng.choice(pool, size=train_size, replace=False)
                prediction = _fit_predict(
                    all_features,
                    all_target,
                    selected,
                    v02_test_indices,
                )
                rows.append(
                    {
                        "dataset": dataset_name,
                        "train_size": train_size,
                        "run": run,
                        "n_train_pool": len(pool),
                        "n_test": len(v02_test_indices),
                        "train_id_hash": _indices_hash(all_ids, selected),
                        "test_id_hash": _indices_hash(all_ids, v02_test_indices),
                        **_metrics(all_target[v02_test_indices], prediction),
                    }
                )
    return rows


def summarize(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for dataset_name in ("v0.1", "v0.2"):
        dataset_summary: dict[str, object] = {}
        for train_size in TRAIN_SIZES[dataset_name]:
            selected = [
                row
                for row in rows
                if row["dataset"] == dataset_name
                and int(row["train_size"]) == train_size
            ]
            dataset_summary[str(train_size)] = {
                metric: {
                    "mean": float(np.mean([float(row[metric]) for row in selected])),
                    "std": float(np.std([float(row[metric]) for row in selected])),
                }
                for metric in ("r2", "mae", "rmse")
            }
        summary[dataset_name] = dataset_summary
    return summary


def _write_plot(
    rows: Sequence[dict[str, object]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    colors = {"v0.1": "#2563eb", "v0.2": "#dc2626"}
    for axis, metric, title in zip(
        axes,
        ("r2", "mae", "rmse"),
        ("R2", "MAE", "RMSE"),
        strict=True,
    ):
        for dataset_name in ("v0.1", "v0.2"):
            means = []
            stds = []
            for train_size in TRAIN_SIZES[dataset_name]:
                values = [
                    float(row[metric])
                    for row in rows
                    if row["dataset"] == dataset_name
                    and int(row["train_size"]) == train_size
                ]
                means.append(float(np.mean(values)))
                stds.append(float(np.std(values)))
            axis.errorbar(
                TRAIN_SIZES[dataset_name],
                means,
                yerr=stds,
                marker="o",
                capsize=3,
                color=colors[dataset_name],
                label=dataset_name,
            )
        axis.set_xlabel("Training compounds")
        axis.set_title(title)
        axis.grid(alpha=0.2)
    axes[0].legend()
    figure.suptitle("Fixed v0.1 test set: data expansion effect")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--v01",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--v02",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v02.csv",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_v02_learning_curve.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v02_learning_curve_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_v02_learning_curve.png",
    )
    return parser.parse_args()


def main() -> int:
    from dielectric_gpr_baseline import deterministic_split

    args = _parse_args()
    v01_rows = read_csv_rows(args.v01)
    v02_rows = read_csv_rows(args.v02)
    rows = run_comparison(v01_rows, v02_rows)
    summary = summarize(rows)
    test_indices = deterministic_split(len(v01_rows), seed=SEED)[1]
    payload = {
        "schema_version": 1,
        "seed": SEED,
        "train_sizes": {
            dataset_name: list(train_sizes)
            for dataset_name, train_sizes in TRAIN_SIZES.items()
        },
        "repeats": REPEATS,
        "fixed_test_compounds": len(test_indices),
        "test_id_hash": _indices_hash(
            [row["inchikey"] for row in v01_rows],
            test_indices,
        ),
        "v01_sha256": canonical_text_sha256(args.v01),
        "v02_sha256": canonical_text_sha256(args.v02),
        "summary": summary,
        "rows": rows,
    }
    write_csv_rows(
        args.csv,
        (
            "dataset",
            "train_size",
            "run",
            "n_train_pool",
            "n_test",
            "train_id_hash",
            "test_id_hash",
            "mae",
            "rmse",
            "r2",
        ),
        rows,
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(rows, args.plot)
    print(json.dumps({"summary": summary, "rows": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
