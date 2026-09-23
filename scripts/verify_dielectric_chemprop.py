"""Independently verify the Chemprop 10x5 outer-fold predictions."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

FLOAT_FIELDS = (
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
        "spearman": float(
            np.corrcoef(rankdata(target), rankdata(prediction))[0, 1]
        ),
        "auc_gt15": float(roc_auc_score(target > 15.0, prediction)),
        "auc_gt30": float(roc_auc_score(target > 30.0, prediction)),
        "mae_lt20": float(
            np.mean(np.abs(target[target < 20.0] - prediction[target < 20.0]))
        ),
        "mae_20_60": float(
            np.mean(
                np.abs(
                    target[(target >= 20.0) & (target <= 60.0)]
                    - prediction[(target >= 20.0) & (target <= 60.0)]
                )
            )
        ),
        "mae_gt60": float(
            np.mean(np.abs(target[target > 60.0] - prediction[target > 60.0]))
        ),
    }


def _compare(
    actual: Mapping[str, str],
    expected: Mapping[str, float],
) -> list[str]:
    errors: list[str] = []
    for field in FLOAT_FIELDS:
        if not np.isclose(float(actual[field]), expected[field], rtol=1e-10, atol=1e-10):
            errors.append(
                f"{actual['repeat']}:{field}: {actual[field]} != {expected[field]}"
            )
    return errors


def verify(source_root: Path) -> dict[str, object]:
    predictions = read_csv_rows(
        source_root / "data" / "processed" / "dielectric_chemprop_predictions.csv"
    )
    repeats = read_csv_rows(
        source_root / "data" / "processed" / "dielectric_chemprop_repeats.csv"
    )
    summary = json.loads(
        (
            source_root / "probes" / "dielectric_chemprop_summary.json"
        ).read_text(encoding="utf-8")
    )
    grouped: dict[int, list[Mapping[str, str]]] = defaultdict(list)
    for row in predictions:
        grouped[int(row["repeat"])].append(row)

    errors: list[str] = []
    recomputed: dict[int, dict[str, float]] = {}
    for repeat, rows in sorted(grouped.items()):
        if len(rows) != len({row["inchikey"] for row in rows}):
            errors.append(f"repeat {repeat} contains duplicate InChIKeys")
        target = np.asarray([float(row["target"]) for row in rows], dtype=np.float64)
        prediction = np.asarray(
            [float(row["prediction"]) for row in rows],
            dtype=np.float64,
        )
        recomputed[repeat] = _metrics(target, prediction)

    for row in repeats:
        repeat = int(row["repeat"])
        if repeat not in recomputed:
            errors.append(f"missing predictions for repeat {repeat}")
            continue
        errors.extend(_compare(row, recomputed[repeat]))

    expected_summary: dict[str, dict[str, float]] = {}
    for field in FLOAT_FIELDS:
        values = np.asarray(
            [recomputed[repeat][field] for repeat in sorted(recomputed)],
            dtype=np.float64,
        )
        expected_summary[field] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)),
        }
        recorded = summary["summary"]["Chemprop_DMPNN_raw"][field]
        if not np.isclose(recorded["mean"], expected_summary[field]["mean"], rtol=1e-10):
            errors.append(f"summary mean mismatch: {field}")
        if not np.isclose(recorded["std"], expected_summary[field]["std"], rtol=1e-10):
            errors.append(f"summary std mismatch: {field}")
    return {
        "passed": not errors,
        "check_count": 4,
        "passed_count": 4 if not errors else 0,
        "errors": errors,
        "repeat_count": len(recomputed),
        "prediction_count": len(predictions),
    }


def main() -> int:
    report = verify(REPOSITORY_ROOT)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
