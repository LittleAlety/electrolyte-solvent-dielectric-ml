from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.verify_dielectric_gpr_baseline import (
    check_input_hash,
    check_metrics_from_predictions,
    check_model_contract,
    check_split_alignment,
    check_std_summary,
    check_uncertainty,
    run_checks,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_valid_artifacts() -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    input_rows = [
        row
        for row in __import__("csv")
        .DictReader(
            (REPOSITORY_ROOT / "data" / "dielectric_v01.csv").open(
                encoding="utf-8",
                newline="",
            )
        )
    ]
    prediction_rows = [
        row
        for row in __import__("csv")
        .DictReader(
            (
                REPOSITORY_ROOT
                / "data"
                / "processed"
                / "dielectric_gpr_test_predictions.csv"
            ).open(encoding="utf-8", newline="")
        )
    ]
    summary = json.loads(
        (
            REPOSITORY_ROOT / "probes" / "dielectric_gpr_summary.json"
        ).read_text(encoding="utf-8")
    )
    return input_rows, prediction_rows, summary


def test_gpr_verifier_accepts_valid_artifacts() -> None:
    checks = run_checks(REPOSITORY_ROOT)

    assert all(check.passed for check in checks), [
        (check.name, check.detail) for check in checks if not check.passed
    ]


def test_gpr_verifier_rejects_split_assignment_tampering() -> None:
    input_rows, prediction_rows, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(prediction_rows)
    test_index = next(
        index for index, row in enumerate(tampered) if row["split"] == "test"
    )
    tampered[test_index]["split"] = "train"
    tampered[test_index]["used_for_metrics"] = "false"

    result = check_split_alignment(input_rows, tampered, summary)

    assert result.passed is False
    assert "split" in result.detail


@pytest.mark.parametrize("column", ["target", "smiles"])
def test_gpr_verifier_rejects_row_misalignment(column: str) -> None:
    input_rows, prediction_rows, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(prediction_rows)
    tampered[10][column] = "tampered"

    result = check_split_alignment(input_rows, tampered, summary)

    assert result.passed is False
    assert column in result.detail


def test_gpr_verifier_rejects_std_summary_mismatch() -> None:
    _, prediction_rows, summary = _load_valid_artifacts()
    tampered_summary = copy.deepcopy(summary)
    tampered_summary["posterior_std"]["mean"] += 1.0

    result = check_std_summary(prediction_rows, tampered_summary)

    assert result.passed is False
    assert "mean" in result.detail


def test_gpr_verifier_rejects_input_hash_mismatch() -> None:
    _, _, summary = _load_valid_artifacts()
    tampered_summary = copy.deepcopy(summary)
    tampered_summary["input_sha256"] = "0" * 64

    result = check_input_hash(tampered_summary, root=REPOSITORY_ROOT)

    assert result.passed is False
    assert "SHA256" in result.detail


def test_gpr_verifier_rejects_metric_mismatch() -> None:
    rows = [
        {
            "split": "test",
            "target": "1.0",
            "prediction": "2.0",
            "std": "1.0",
            "abs_error": "1.0",
        },
        {
            "split": "test",
            "target": "2.0",
            "prediction": "2.0",
            "std": "1.0",
            "abs_error": "0.0",
        },
    ]
    summary = {"metrics": {"mae": 0.0, "rmse": 0.0, "r2": 1.0}}

    result = check_metrics_from_predictions(rows, summary)

    assert result.passed is False
    assert "MAE" in result.detail


def test_gpr_verifier_rejects_negative_std() -> None:
    rows = [
        {
            "inchikey": "AAAA-BBBB-C",
            "split": "test",
            "target": "1.0",
            "prediction": "1.0",
            "std": "-0.1",
            "abs_error": "0.0",
            "inside_95": "true",
        }
    ]

    result = check_uncertainty(rows)

    assert result.passed is False
    assert "negative" in result.detail


def test_gpr_verifier_rejects_final_kernel_tampering() -> None:
    _, _, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(summary)
    tampered["model"]["final_kernel"] = (
        "2.16**2 * RBF(length_scale=99) + WhiteKernel(noise_level=0.278)"
    )

    result = check_model_contract(tampered)

    assert result.passed is False
    assert "final kernel" in result.detail


def test_gpr_verifier_rejects_random_state_tampering() -> None:
    _, _, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(summary)
    tampered["model"]["random_state"] = 7

    result = check_model_contract(tampered)

    assert result.passed is False
    assert "random_state" in result.detail


def test_gpr_verifier_rejects_gate_passed_tampering() -> None:
    _, _, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(summary)
    tampered["gate"]["passed"] = True

    result = check_model_contract(tampered)

    assert result.passed is False
    assert "gate" in result.detail


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("model", "name"), "NotAGPR"),
        (("feature", "type"), "not-morgan"),
    ],
)
def test_gpr_verifier_rejects_model_or_feature_type_tampering(
    path: tuple[str, str],
    value: str,
) -> None:
    _, _, summary = _load_valid_artifacts()
    tampered = copy.deepcopy(summary)
    tampered[path[0]][path[1]] = value

    result = check_model_contract(tampered)

    assert result.passed is False
    assert "model" in result.detail or "feature" in result.detail
