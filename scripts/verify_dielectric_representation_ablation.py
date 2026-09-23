"""Independently verify the dielectric representation-ablation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
METRICS = (
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


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = target - prediction
    target_rank = rankdata(target, method="average")
    prediction_rank = rankdata(prediction, method="average")
    metrics = {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "r2": float(
            1.0
            - np.sum(error**2)
            / np.sum((target - np.mean(target)) ** 2)
        ),
        "spearman": float(np.corrcoef(target_rank, prediction_rank)[0, 1]),
        "auc_gt15": float(roc_auc_score(target > 15.0, prediction)),
        "auc_gt30": float(roc_auc_score(target > 30.0, prediction)),
    }
    for name, mask in (
        ("mae_lt20", target < 20.0),
        ("mae_20_60", (target >= 20.0) & (target <= 60.0)),
        ("mae_gt60", target > 60.0),
    ):
        metrics[name] = float(np.mean(np.abs(error[mask]))) if np.any(mask) else math.nan
    return metrics


def _compare_metrics(
    *,
    label: str,
    expected: Mapping[str, object],
    actual: Mapping[str, float],
) -> Check:
    mismatches = []
    for metric in METRICS:
        expected_value = float(expected[metric])
        actual_value = float(actual[metric])
        if math.isnan(expected_value) and math.isnan(actual_value):
            continue
        if not _close(actual_value, expected_value):
            mismatches.append(
                f"{metric}: artifact={expected_value:.12g}, recomputed={actual_value:.12g}"
            )
    if mismatches:
        return Check(label, False, "; ".join(mismatches))
    return Check(label, True, f"{len(METRICS)} metrics reproduced")


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    return float(np.mean(array)), float(np.std(array, ddof=1))


def verify(root: Path) -> dict[str, object]:
    paths = {
        "source": root / "data" / "dielectric_v02.csv",
        "features": root / "data" / "processed" / "dielectric_physical_features.csv",
        "exclusions": root / "data" / "processed" / "dielectric_v02_exclusions.csv",
        "cv": root
        / "data"
        / "processed"
        / "dielectric_representation_ablation_cv.csv",
        "repeats": root
        / "data"
        / "processed"
        / "dielectric_representation_ablation_repeats.csv",
        "predictions": root
        / "data"
        / "processed"
        / "dielectric_representation_ablation_predictions.csv",
        "summary": root / "probes" / "dielectric_representation_ablation_summary.json",
    }
    source_rows = read_csv_rows(paths["source"])
    feature_rows = read_csv_rows(paths["features"])
    exclusion_rows = read_csv_rows(paths["exclusions"])
    cv_rows = read_csv_rows(paths["cv"])
    repeat_rows = read_csv_rows(paths["repeats"])
    prediction_rows = read_csv_rows(paths["predictions"])
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    checks: list[Check] = []

    successful = [row for row in feature_rows if row["status"] != "error"]
    failed = [row for row in feature_rows if row["status"] == "error"]
    checks.append(
        Check(
            "accounting",
            len(successful) + len(failed) + len(exclusion_rows) == len(source_rows),
            (
                f"source={len(source_rows)}, successful={len(successful)}, "
                f"failed={len(failed)}, excluded={len(exclusion_rows)}"
            ),
        )
    )
    checks.append(
        Check(
            "summary counts",
            summary.get("source_count") == len(source_rows)
            and summary.get("compound_count") == len(successful)
            and summary.get("excluded_count") == len(exclusion_rows)
            and summary.get("failed_physical_feature_count") == len(failed),
            "summary counts match source/feature/exclusion artifacts",
        )
    )
    feature_sha = canonical_text_sha256(paths["features"])
    checks.append(
        Check(
            "feature hash",
            summary.get("input_sha256") == feature_sha,
            f"recorded={summary.get('input_sha256')} actual={feature_sha}",
        )
    )
    exclusion_sha = canonical_text_sha256(paths["exclusions"])
    checks.append(
        Check(
            "exclusion hash",
            summary.get("exclusions_sha256") == exclusion_sha,
            f"recorded={summary.get('exclusions_sha256')} actual={exclusion_sha}",
        )
    )

    expected_cv_keys = {
        (representation, repeat, fold)
        for representation in REPRESENTATIONS
        for repeat in range(10)
        for fold in range(5)
    }
    actual_cv_keys = {
        (row["representation"], int(row["repeat"]), int(row["fold"]))
        for row in cv_rows
    }
    checks.append(
        Check(
            "CV grid",
            actual_cv_keys == expected_cv_keys and len(cv_rows) == len(expected_cv_keys),
            f"{len(cv_rows)} unique representation/repeat/fold rows",
        )
    )
    seed_mismatches = [
        row
        for row in cv_rows
        if int(row["seed"]) != 42 + int(row["repeat"]) * 5 + int(row["fold"])
    ]
    checks.append(
        Check(
            "CV seed mapping",
            not seed_mismatches,
            f"{len(seed_mismatches)} mismatches from 42 + 5*repeat + fold",
        )
    )

    predictions_by_fold: dict[tuple[str, int, int], list[tuple[float, float]]] = defaultdict(list)
    predictions_by_repeat: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    for row in prediction_rows:
        key_fold = (row["representation"], int(row["repeat"]), int(row["fold"]))
        prediction = float(row["prediction"])
        target = float(row["target"])
        predictions_by_fold[key_fold].append((target, prediction))
        predictions_by_repeat[(row["representation"], int(row["repeat"]))].append(
            (target, prediction)
        )

    checks.append(
        Check(
            "prediction constraints",
            all(float(row["prediction"]) >= 1.0 for row in prediction_rows),
            "all OOF predictions satisfy dielectric >= 1",
        )
    )
    coverage_ok = True
    coverage_detail = "each representation/repeat covers each compound once"
    inchikeys = {row["inchikey"] for row in successful}
    for representation in REPRESENTATIONS:
        for repeat in range(10):
            prediction_keys = {
                row["inchikey"]
                for row in prediction_rows
                if row["representation"] == representation and int(row["repeat"]) == repeat
            }
            if prediction_keys != inchikeys:
                coverage_ok = False
                coverage_detail = f"coverage mismatch for {representation}/{repeat}"
                break
    checks.append(Check("OOF coverage", coverage_ok, coverage_detail))

    cv_lookup = {
        (row["representation"], int(row["repeat"]), int(row["fold"])): row
        for row in cv_rows
    }
    cv_mismatches: list[str] = []
    for key, values in predictions_by_fold.items():
        target = np.asarray([value[0] for value in values], dtype=float)
        prediction = np.asarray([value[1] for value in values], dtype=float)
        mismatch = _compare_metrics(
            label="CV metrics",
            expected=cv_lookup[key],
            actual=_metrics(target, prediction),
        )
        if not mismatch.passed:
            cv_mismatches.append(f"{key}: {mismatch.detail}")
    checks.append(
        Check(
            "CV metric recomputation",
            not cv_mismatches,
            cv_mismatches[0] if cv_mismatches else "all 150 fold metrics reproduced",
        )
    )

    repeat_lookup = {
        (row["representation"], int(row["repeat"])): row for row in repeat_rows
    }
    repeat_metrics: dict[tuple[str, int], dict[str, float]] = {}
    repeat_mismatches: list[str] = []
    for key, values in predictions_by_repeat.items():
        target = np.asarray([value[0] for value in values], dtype=float)
        prediction = np.asarray([value[1] for value in values], dtype=float)
        actual = _metrics(target, prediction)
        repeat_metrics[key] = actual
        mismatch = _compare_metrics(
            label="repeat metrics",
            expected=repeat_lookup[key],
            actual=actual,
        )
        if not mismatch.passed:
            repeat_mismatches.append(f"{key}: {mismatch.detail}")
    checks.append(
        Check(
            "repeat metric recomputation",
            not repeat_mismatches,
            repeat_mismatches[0] if repeat_mismatches else "all 30 repeat metrics reproduced",
        )
    )

    summary_mismatches: list[str] = []
    for representation in REPRESENTATIONS:
        for metric in METRICS:
            values = [
                repeat_metrics[(representation, repeat)][metric]
                for repeat in range(10)
            ]
            mean, std = _mean_std(values)
            expected = summary["summary"][representation][metric]
            if not _close(mean, float(expected["mean"])) or not _close(
                std,
                float(expected["std"]),
            ):
                summary_mismatches.append(f"{representation}/{metric}")
    checks.append(
        Check(
            "summary recomputation",
            not summary_mismatches,
            (
                summary_mismatches[0]
                if summary_mismatches
                else "all repeat-level means and standard deviations reproduced"
            ),
        )
    )
    checks.append(
        Check(
            "aggregation disclosure",
            "complete OOF vector" in str(summary.get("aggregation", "")),
            "summary states repeat-level OOF aggregation",
        )
    )

    check_rows = [asdict(check) for check in checks]
    return {
        "passed": all(check.passed for check in checks),
        "check_count": len(checks),
        "passed_count": sum(check.passed for check in checks),
        "checks": check_rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
