from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

import scripts.verify_dielectric_baseline_diagnostics as diagnostics_verifier
from scripts.verify_dielectric_baseline_diagnostics import (
    check_cv_grid,
    check_cv_summary,
    check_descriptor_enhancement,
    check_learning_rows,
    check_model_names,
    check_row_count,
    metric_within_tolerance,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load():
    cv_rows = _read_csv(
        REPOSITORY_ROOT / "data" / "processed" / "dielectric_gpr_repeated_cv.csv"
    )
    learning_rows = _read_csv(
        REPOSITORY_ROOT / "data" / "processed" / "dielectric_learning_curve.csv"
    )
    summary = json.loads(
        (
            REPOSITORY_ROOT
            / "probes"
            / "dielectric_baseline_diagnostics_summary.json"
        ).read_text(encoding="utf-8")
    )
    return cv_rows, learning_rows, summary


def test_diagnostics_verifier_rejects_count_mismatch() -> None:
    result = check_row_count("cv", [], expected=50)

    assert result.passed is False
    assert "50" in result.detail


def test_diagnostics_verifier_rejects_summary_mean_mismatch() -> None:
    rows = [
        {"model": "DummyMean", "mae": 1.0, "rmse": 1.0, "r2": 0.0},
        {"model": "DummyMean", "mae": 1.0, "rmse": 1.0, "r2": 0.0},
        {"model": "SizeOnlyRidge", "mae": 1.0, "rmse": 1.0, "r2": 0.0},
        {"model": "SizeOnlyRidge", "mae": 1.0, "rmse": 1.0, "r2": 0.0},
        {"model": "MorganRBFGPR", "mae": 1.0, "rmse": 1.0, "r2": 0.1},
        {"model": "MorganRBFGPR", "mae": 3.0, "rmse": 3.0, "r2": 0.3},
    ]
    summary = {
        "cv": {
            "n_splits": 5,
            "n_repeats": 10,
            "fold_rows": 150,
            "models": {
                "DummyMean": {
                    "mae": {"mean": 1.0, "std": 0.0},
                    "rmse": {"mean": 1.0, "std": 0.0},
                    "r2": {"mean": 0.0, "std": 0.0},
                },
                "SizeOnlyRidge": {
                    "mae": {"mean": 1.0, "std": 0.0},
                    "rmse": {"mean": 1.0, "std": 0.0},
                    "r2": {"mean": 0.0, "std": 0.0},
                },
                "MorganRBFGPR": {
                    "mae": {"mean": 9.0, "std": 1.0},
                    "rmse": {"mean": 2.0, "std": 1.0},
                    "r2": {"mean": 0.2, "std": 0.1},
                },
            },
        }
    }

    result = check_cv_summary(rows, summary)

    assert result.passed is False
    assert "mean" in result.detail


def test_diagnostics_verifier_rejects_null_model_name() -> None:
    result = check_model_names(
        [{"model": ""}, {"model": "MorganRBFGPR"}],
        expected={"MorganRBFGPR"},
    )

    assert result.passed is False
    assert "model" in result.detail


def test_diagnostics_verifier_rejects_missing_cv_fold() -> None:
    cv_rows, _, _ = _load()

    result = check_cv_grid(cv_rows[:-1])

    assert result.passed is False
    assert "missing" in result.detail


def test_diagnostics_verifier_rejects_duplicate_cv_fold() -> None:
    cv_rows, _, _ = _load()
    tampered = copy.deepcopy(cv_rows)
    tampered[-1] = copy.deepcopy(tampered[0])

    result = check_cv_grid(tampered)

    assert result.passed is False
    assert "duplicate" in result.detail


def test_diagnostics_verifier_rejects_wrong_cv_repeat() -> None:
    cv_rows, _, _ = _load()
    tampered = copy.deepcopy(cv_rows)
    tampered[0]["repeat"] = "99"

    result = check_cv_grid(tampered)

    assert result.passed is False
    assert "missing" in result.detail or "unexpected" in result.detail


def test_diagnostics_verifier_rejects_learning_test_overlap() -> None:
    _, learning_rows, _ = _load()
    tampered = copy.deepcopy(learning_rows)
    tampered[0]["train_id_hash"] = tampered[0]["test_id_hash"]

    result = check_learning_rows(tampered, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "train_id_hash" in result.detail


def test_diagnostics_verifier_rejects_learning_size_error() -> None:
    _, learning_rows, _ = _load()
    tampered = copy.deepcopy(learning_rows)
    tampered[0]["n_train"] = "19"

    result = check_learning_rows(tampered, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "n_train" in result.detail


def test_diagnostics_verifier_rejects_descriptor_metric_tampering() -> None:
    _, _, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["descriptor_enhancement"]["metrics"]["mae"] += 1.0

    result = check_descriptor_enhancement(tampered, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "metric" in result.detail


def test_diagnostics_verifier_rejects_descriptor_gain_or_flag_tampering() -> None:
    _, _, summary = _load()
    tampered_gain = copy.deepcopy(summary)
    tampered_gain["descriptor_enhancement"]["r2_gain_over_morgan"] += 0.5
    gain_result = check_descriptor_enhancement(
        tampered_gain,
        root=REPOSITORY_ROOT,
    )
    tampered_flag = copy.deepcopy(summary)
    tampered_flag["descriptor_enhancement"]["reached_r2_0_35"] = (
        not tampered_flag["descriptor_enhancement"]["reached_r2_0_35"]
    )
    flag_result = check_descriptor_enhancement(
        tampered_flag,
        root=REPOSITORY_ROOT,
    )

    assert gain_result.passed is False
    assert flag_result.passed is False


def test_gpr_metric_tolerance_accepts_small_platform_difference() -> None:
    assert metric_within_tolerance("MorganRBFGPR", 1.0000005, 1.0) is True


def test_gpr_metric_tolerance_rejects_large_difference() -> None:
    assert metric_within_tolerance("MorganRBFGPR", 1.0001, 1.0) is False


def test_non_gpr_metric_tolerance_remains_strict() -> None:
    assert metric_within_tolerance("DummyMean", 1.0 + 1e-13, 1.0) is True
    assert metric_within_tolerance("SizeOnlyRidge", 1.0 + 1e-9, 1.0) is False


def test_descriptor_gpr_metric_tolerance_accepts_small_drift() -> None:
    assert metric_within_tolerance("DescriptorGPR", 1.0 + 5e-6, 1.0) is True


def test_descriptor_gpr_metric_tolerance_rejects_large_drift() -> None:
    assert metric_within_tolerance("DescriptorGPR", 1.0 + 1e-4, 1.0) is False


def test_descriptor_gain_uses_same_gpr_tolerance() -> None:
    assert metric_within_tolerance("DescriptorGPR", 1.0 + 5e-6, 1.0) is True
    assert metric_within_tolerance("DescriptorGPR", 1.0 + 1e-4, 1.0) is False


@pytest.mark.parametrize(
    ("drift", "expected_passed"),
    [(5e-6, True), (2e-5, False), (1e-4, False)],
)
def test_descriptor_r2_real_scale_tolerance(
    monkeypatch,
    drift: float,
    expected_passed: bool,
) -> None:
    _, _, summary = _load()
    reported = dict(summary["descriptor_enhancement"]["metrics"])
    recomputed = dict(reported)
    recomputed["r2"] = float(reported["r2"]) + drift
    summary["descriptor_enhancement"]["r2_gain_over_morgan"] = (
        recomputed["r2"] - float(summary["single_split"]["MorganRBFGPR"]["r2"])
    )
    summary["descriptor_enhancement"]["reached_r2_0_35"] = (
        recomputed["r2"] >= 0.35
    )
    monkeypatch.setattr(
        diagnostics_verifier,
        "run_descriptor_enhancement",
        lambda target, features: recomputed,
    )

    result = check_descriptor_enhancement(summary, root=REPOSITORY_ROOT)

    assert result.passed is expected_passed


@pytest.mark.parametrize(
    ("drift", "expected_passed"),
    [(5e-6, True), (2e-5, False), (1e-4, False)],
)
def test_descriptor_gain_real_scale_tolerance(
    monkeypatch,
    drift: float,
    expected_passed: bool,
) -> None:
    _, _, summary = _load()
    reported = dict(summary["descriptor_enhancement"]["metrics"])
    recomputed = dict(reported)
    true_gain = recomputed["r2"] - float(
        summary["single_split"]["MorganRBFGPR"]["r2"]
    )
    summary["descriptor_enhancement"]["r2_gain_over_morgan"] = true_gain + drift
    monkeypatch.setattr(
        diagnostics_verifier,
        "run_descriptor_enhancement",
        lambda target, features: recomputed,
    )

    result = check_descriptor_enhancement(summary, root=REPOSITORY_ROOT)

    assert result.passed is expected_passed
