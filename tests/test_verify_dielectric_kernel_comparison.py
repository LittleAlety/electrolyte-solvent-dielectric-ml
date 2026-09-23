from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import numpy as np

from scripts.verify_dielectric_kernel_comparison import (
    _xgboost_model,
    check_derived_summary,
    check_grid,
    check_metric_values,
    check_tanimoto_kernel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_kernel_verifier_rejects_missing_grid_combination() -> None:
    rows = [
        {"model": "Tanimoto_GPR", "repeat": "0", "fold": "0"},
    ]

    result = check_grid(rows)

    assert result.passed is False
    assert "missing" in result.detail


def test_kernel_verifier_xgboost_is_single_threaded() -> None:
    model = _xgboost_model()

    assert model.n_jobs == 1
    assert model.tree_method == "exact"


def test_kernel_summary_records_single_threaded_xgboost() -> None:
    summary = json.loads(
        (
            REPOSITORY_ROOT
            / "probes"
            / "dielectric_kernel_comparison_summary.json"
        ).read_text(encoding="utf-8")
    )

    assert "n_jobs=1" in summary["models"]["XGBoost"]["config"]
    assert "tree_method=exact" in summary["models"]["XGBoost"]["config"]


def test_kernel_verifier_rejects_metric_tampering() -> None:
    rows = [
        {
            "model": "Tanimoto_GPR",
            "repeat": "0",
            "fold": "0",
            "mae": "99",
            "rmse": "1",
            "r2": "0",
        }
    ]
    expected = {
        ("Tanimoto_GPR", 0, 0): {"mae": 1.0, "rmse": 1.0, "r2": 0.0}
    }

    result = check_metric_values(rows, expected)

    assert result.passed is False
    assert "mae" in result.detail


def test_kernel_verifier_accepts_small_gpr_metric_drift() -> None:
    rows = [
        {
            "model": "Tanimoto_GPR",
            "repeat": "0",
            "fold": "0",
            "mae": str(1.0 + 5e-6),
            "rmse": str(1.0 + 5e-6),
            "r2": str(0.5 + 5e-6),
        }
    ]
    expected = {
        ("Tanimoto_GPR", 0, 0): {"mae": 1.0, "rmse": 1.0, "r2": 0.5}
    }

    assert check_metric_values(rows, expected).passed is True


def test_kernel_verifier_rejects_large_gpr_metric_drift() -> None:
    rows = [
        {
            "model": "RBF_GPR",
            "repeat": "0",
            "fold": "0",
            "mae": str(1.0 + 1e-4),
            "rmse": "1.0",
            "r2": "0.5",
        }
    ]
    expected = {
        ("RBF_GPR", 0, 0): {"mae": 1.0, "rmse": 1.0, "r2": 0.5}
    }

    result = check_metric_values(rows, expected)

    assert result.passed is False
    assert "mae" in result.detail


def test_kernel_verifier_accepts_small_xgboost_metric_drift() -> None:
    rows = [
        {
            "model": "XGBoost",
            "repeat": "0",
            "fold": "0",
            "mae": str(1.0 + 5e-6),
            "rmse": str(1.0 + 5e-6),
            "r2": str(0.5 + 5e-6),
        }
    ]
    expected = {
        ("XGBoost", 0, 0): {"mae": 1.0, "rmse": 1.0, "r2": 0.5}
    }

    assert check_metric_values(rows, expected).passed is True


def test_kernel_verifier_rejects_large_xgboost_metric_drift() -> None:
    rows = [
        {
                "model": "XGBoost",
                "repeat": "0",
                "fold": "0",
                "mae": str(1.0 + 1e-2),
            "rmse": "1.0",
            "r2": "0.5",
        }
    ]
    expected = {
        ("XGBoost", 0, 0): {"mae": 1.0, "rmse": 1.0, "r2": 0.5}
    }

    result = check_metric_values(rows, expected)

    assert result.passed is False
    assert "mae" in result.detail


def test_kernel_verifier_rejects_tanimoto_kernel_tampering() -> None:
    fingerprints = np.asarray([[1, 1, 0], [1, 0, 1]], dtype=np.uint8)
    tampered = np.asarray([[1.0, 0.0], [0.0, 1.0]])

    result = check_tanimoto_kernel(fingerprints, tampered)

    assert result.passed is False
    assert "Tanimoto" in result.detail


def _load_derived_artifacts():
    with (
        REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_kernel_comparison.csv"
    ).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(
        (
            REPOSITORY_ROOT
            / "probes"
            / "dielectric_kernel_comparison_summary.json"
        ).read_text(encoding="utf-8")
    )
    return rows, summary


def test_kernel_verifier_rejects_gate_passed_tampering() -> None:
    rows, summary = _load_derived_artifacts()
    summary["gate"]["passed"] = not summary["gate"]["passed"]

    result = check_derived_summary(rows, summary)

    assert result.passed is False
    assert "gate.passed" in result.detail


def test_kernel_verifier_rejects_difference_tampering() -> None:
    rows, summary = _load_derived_artifacts()
    summary["tanimoto_vs_rbf_r2_mean_difference"] += 1.0

    result = check_derived_summary(rows, summary)

    assert result.passed is False
    assert "difference" in result.detail


def test_kernel_verifier_rejects_best_model_tampering() -> None:
    rows, summary = _load_derived_artifacts()
    summary["gate"]["best_model"] = "NotAModel"

    result = check_derived_summary(rows, summary)

    assert result.passed is False
    assert "best_model" in result.detail


def test_kernel_verifier_rejects_conclusion_tampering() -> None:
    rows, summary = _load_derived_artifacts()
    tampered_flag = copy.deepcopy(summary)
    tampered_flag["conclusion"]["tanimoto_improves_over_rbf"] = (
        not tampered_flag["conclusion"]["tanimoto_improves_over_rbf"]
    )
    flag_result = check_derived_summary(rows, tampered_flag)
    tampered_margin = copy.deepcopy(summary)
    tampered_margin["conclusion"]["improvement_margin"] += 1.0
    margin_result = check_derived_summary(rows, tampered_margin)

    assert flag_result.passed is False
    assert margin_result.passed is False
