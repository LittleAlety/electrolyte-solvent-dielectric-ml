"""Run a Chemprop D-MPNN baseline on the fixed dielectric CV folds."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import warnings
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_representation_ablation import read_model_ready_map

logging.getLogger("lightning.pytorch").setLevel(logging.ERROR)
warnings.filterwarnings(
    "ignore",
    message=".*train_dataloader.*many workers.*",
    category=UserWarning,
)

SEED = 42
N_SPLITS = 5
N_REPEATS = 10
MAX_EPOCHS = 50
BATCH_SIZE = 32
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


def read_rows(path: Path) -> list[dict[str, str]]:
    """Return the featurized rows that are eligible to be fitted.

    Two filters apply, in this order: physical-feature failures
    (`status == "error"`) and the dataset-level `model_ready` gate. The gate is
    what the v0.3.4 correction introduced; routing through it here keeps this
    probe consistent with every other fit, so a row the dataset flags as an
    unresolved conflict or as awaiting primary confirmation can never reach a
    Chemprop training fold. Every v0.2 row is `model_ready=true`, so this is a
    no-op on the frozen 205-row input and only bites if the input moves to the
    v0.3 table.
    """

    ready = read_model_ready_map()
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row["status"] != "error" and ready.get(row["inchikey"], False)
        ]


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def log_dielectric(values: np.ndarray) -> np.ndarray:
    return np.log(np.asarray(values, dtype=np.float64) - 1.0)


def inverse_log_dielectric(values: np.ndarray) -> np.ndarray:
    return np.maximum(np.exp(np.asarray(values, dtype=np.float64)) + 1.0, 1.0)


def evaluate(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.maximum(np.asarray(prediction, dtype=np.float64), 1.0)
    labels = target > 30.0
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
        "spearman": float(np.corrcoef(rankdata(target), rankdata(prediction))[0, 1]),
        "auc_gt15": (
            float(roc_auc_score(target > 15.0, prediction))
            if np.unique(target > 15.0).size == 2
            else float("nan")
        ),
        "auc_gt30": (
            float(roc_auc_score(labels, prediction))
            if np.unique(labels).size == 2
            else float("nan")
        ),
        "mae_lt20": float(np.mean(np.abs(target[target < 20.0] - prediction[target < 20.0]))),
        "mae_20_60": float(
            np.mean(
                np.abs(
                    target[(target >= 20.0) & (target <= 60.0)]
                    - prediction[(target >= 20.0) & (target <= 60.0)]
                )
            )
        ),
        "mae_gt60": float(np.mean(np.abs(target[target > 60.0] - prediction[target > 60.0]))),
    }


def summarize(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["representation"])].append(row)
    metric_names = REPEAT_COLUMNS[2:]
    result: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for representation, values in grouped.items():
        result[representation] = {}
        for metric in metric_names:
            numbers = np.asarray(
                [float(row[metric]) for row in values],
                dtype=np.float64,
            )
            finite = numbers[np.isfinite(numbers)]
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


def _predict_fold(
    train_rows: Sequence[Mapping[str, str]],
    test_rows: Sequence[Mapping[str, str]],
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    seed: int,
    use_log_target: bool,
) -> np.ndarray:
    import lightning as pl
    import torch
    from chemprop import data, featurizers, models, nn
    from lightning.pytorch import seed_everything

    seed_everything(seed, workers=True, verbose=False)
    torch.set_num_threads(1)
    fit_target = log_dielectric(target) if use_log_target else target
    train_datapoints = [
        data.MoleculeDatapoint.from_smi(row["smiles"], [float(fit_target[index])])
        for index, row in zip(train_indices, train_rows, strict=True)
    ]
    test_datapoints = [
        data.MoleculeDatapoint.from_smi(row["smiles"], [float(target[index])])
        for index, row in zip(test_indices, test_rows, strict=True)
    ]
    featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
    train_dataset = data.MoleculeDataset(train_datapoints, featurizer)
    test_dataset = data.MoleculeDataset(test_datapoints, featurizer)
    train_loader = data.build_dataloader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=0,
        seed=seed,
    )
    test_loader = data.build_dataloader(
        test_dataset,
        batch_size=64,
        shuffle=False,
        num_workers=0,
    )
    model = models.MPNN(
        nn.BondMessagePassing(),
        nn.MeanAggregation(),
        nn.RegressionFFN(),
    )
    trainer = pl.Trainer(
        max_epochs=MAX_EPOCHS,
        accelerator="cpu",
        devices=1,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        deterministic=True,
    )
    trainer.fit(model, train_loader)
    batches = trainer.predict(model, test_loader)
    prediction = torch.cat(batches).detach().cpu().numpy().reshape(-1)
    if use_log_target:
        prediction = inverse_log_dielectric(prediction)
    return np.maximum(prediction, 1.0)


def run(
    *,
    input_path: Path,
    repeat_path: Path,
    predictions_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    rows = read_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=np.float64)
    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )
    repeat_predictions = {
        ("Chemprop_DMPNN_raw", repeat): np.full(len(rows), np.nan)
        for repeat in range(N_REPEATS)
    }
    prediction_rows: list[dict[str, object]] = []
    for split_index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(rows)))
    ):
        repeat_number = split_index // N_SPLITS
        fold = split_index % N_SPLITS
        prediction = _predict_fold(
            [rows[int(index)] for index in train_indices],
            [rows[int(index)] for index in test_indices],
            target,
            train_indices,
            test_indices,
            seed=SEED + split_index,
            use_log_target=False,
        )
        repeat_predictions[("Chemprop_DMPNN_raw", repeat_number)][test_indices] = prediction
        for row_index, predicted in zip(test_indices, prediction, strict=True):
            row = rows[int(row_index)]
            prediction_rows.append(
                {
                    "representation": "Chemprop_DMPNN_raw",
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
    for repeat in range(N_REPEATS):
        prediction = repeat_predictions[("Chemprop_DMPNN_raw", repeat)]
        if not np.isfinite(prediction).all():
            raise ValueError(f"incomplete OOF predictions for repeat {repeat}")
        repeat_rows.append(
            {
                "representation": "Chemprop_DMPNN_raw",
                "repeat": repeat,
                **evaluate(target, prediction),
            }
        )
    summary = summarize(repeat_rows)
    payload: dict[str, object] = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "compound_count": len(rows),
        "representation": "Chemprop_DMPNN_raw",
        "model": {
            "name": "Chemprop D-MPNN",
            "version": "2.1.0",
            "message_passing": "BondMessagePassing",
            "aggregation": "MeanAggregation",
            "predictor": "RegressionFFN",
            "epochs": MAX_EPOCHS,
            "batch_size": BATCH_SIZE,
            "target": "raw dielectric",
        },
        "validation": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
        },
        "summary": summary,
        "outputs": {
            "repeat_csv": repeat_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(
                REPOSITORY_ROOT
            ).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    write_csv(repeat_path, REPEAT_COLUMNS, repeat_rows)
    write_csv(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
        "--repeat-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_chemprop_repeats.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_chemprop_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_chemprop_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run(
        input_path=args.input,
        repeat_path=args.repeat_output,
        predictions_path=args.predictions_output,
        summary_path=args.summary_output,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
