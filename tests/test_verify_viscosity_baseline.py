from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from scripts.verify_viscosity_baseline import (
    check_derived_columns,
    check_gate_and_interpretation,
    check_group_key_leakage,
    check_metrics_from_predictions,
    check_prediction_binding,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load():
    with (
        REPOSITORY_ROOT / "data" / "processed" / "viscosity_baseline_predictions.csv"
    ).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(
        (REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json").read_text(
            encoding="utf-8"
        )
    )
    return rows, summary


def test_viscosity_verifier_rejects_group_key_leakage() -> None:
    rows = [
        {"split_type": "group_key", "inchikey": "SAME", "row_id": "1"},
        {"split_type": "group_key", "inchikey": "SAME", "row_id": "2"},
    ]
    split_assignment = {"1": "train", "2": "test"}

    result = check_group_key_leakage(rows, split_assignment)

    assert result.passed is False
    assert "overlap" in result.detail or "leak" in result.detail


def test_viscosity_verifier_rejects_metric_mismatch() -> None:
    rows, summary = _load()
    tampered = copy.deepcopy(summary)
    model = next(iter(tampered["splits"]["random_row"]["models"]))
    tampered["splits"]["random_row"]["models"][model]["log10_cP"]["mae"] += 1.0

    result = check_metrics_from_predictions(rows, tampered)

    assert result.passed is False
    assert "mae" in result.detail


def test_viscosity_verifier_rejects_target_tampering() -> None:
    rows, _ = _load()
    input_rows = list(
        csv.DictReader(
            (REPOSITORY_ROOT / "data" / "viscosity_v01.csv").open(
                encoding="utf-8",
                newline="",
            )
        )
    )
    tampered = copy.deepcopy(rows)
    tampered[0]["target_log10_cP"] = str(float(tampered[0]["target_log10_cP"]) + 0.1)

    result = check_derived_columns(tampered, input_rows)

    assert result.passed is False
    assert "target" in result.detail


def test_viscosity_verifier_rejects_unit_column_tampering() -> None:
    rows, _ = _load()
    input_rows = list(
        csv.DictReader(
            (REPOSITORY_ROOT / "data" / "viscosity_v01.csv").open(
                encoding="utf-8",
                newline="",
            )
        )
    )
    tampered = copy.deepcopy(rows)
    tampered[0]["prediction_Pa_s"] = "999"

    result = check_derived_columns(tampered, input_rows)

    assert result.passed is False
    assert "prediction_Pa_s" in result.detail


def test_viscosity_verifier_rejects_gate_tampering() -> None:
    rows, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["primary_gate"]["group_key_passed"] = (
        not tampered["primary_gate"]["group_key_passed"]
    )

    result = check_gate_and_interpretation(rows, tampered)

    assert result.passed is False
    assert "gate" in result.detail


def test_viscosity_verifier_rejects_interpretation_tampering() -> None:
    rows, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["interpretation"]["random_pass_group_fail"] = (
        not tampered["interpretation"]["random_pass_group_fail"]
    )

    result = check_gate_and_interpretation(rows, tampered)

    assert result.passed is False
    assert "interpretation" in result.detail


def test_viscosity_verifier_rejects_row_binding_tampering() -> None:
    rows, _ = _load()
    input_rows = list(
        csv.DictReader(
            (REPOSITORY_ROOT / "data" / "viscosity_v01.csv").open(
                encoding="utf-8",
                newline="",
            )
        )
    )
    tampered = copy.deepcopy(rows)
    tampered[0]["T_K"] = str(float(tampered[0]["T_K"]) + 1)
    assignment = {row["row_id"]: row["split_type"] for row in tampered}

    result = check_prediction_binding(tampered, input_rows, assignment)

    assert result.passed is False
    assert "T_K" in result.detail
