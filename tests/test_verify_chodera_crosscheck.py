from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from scripts.verify_chodera_crosscheck import (
    check_crosscheck_rows,
    check_crosscheck_summary,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load():
    rows = list(
        csv.DictReader(
            (
                REPOSITORY_ROOT / "data" / "processed" / "chodera_crosscheck.csv"
            ).open(encoding="utf-8", newline="")
        )
    )
    summary = json.loads(
        (
            REPOSITORY_ROOT / "probes" / "chodera_crosscheck_summary.json"
        ).read_text(encoding="utf-8")
    )
    return rows, summary


def test_crosscheck_verifier_rejects_tampered_median_difference() -> None:
    rows, _ = _load()
    tampered = copy.deepcopy(rows)
    tampered[0]["median_difference"] = "999"

    result = check_crosscheck_rows(tampered)

    assert result.passed is False
    assert "median_difference" in result.detail


def test_crosscheck_verifier_rejects_tampered_pair_value() -> None:
    rows, _ = _load()
    tampered = copy.deepcopy(rows)
    tampered[0]["pair_chodera_value"] = "999"

    result = check_crosscheck_rows(tampered)

    assert result.passed is False
    assert "pair" in result.detail


def test_crosscheck_verifier_rejects_relative_delta_tampering() -> None:
    rows, _ = _load()
    tampered = copy.deepcopy(rows)
    tampered[0]["relative_delta_percent"] = "999"

    result = check_crosscheck_rows(tampered)

    assert result.passed is False
    assert "relative_delta_percent" in result.detail


def test_crosscheck_verifier_rejects_max_temperature_gap_tampering() -> None:
    rows, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["temperature_gap_stats_K"]["max"] += 1.0

    result = check_crosscheck_summary(rows, tampered)

    assert result.passed is False
    assert "max" in result.detail


def test_crosscheck_verifier_rejects_assessment_tampering() -> None:
    rows, summary = _load()
    tampered = copy.deepcopy(summary)
    tampered["temperature_explanation_assessment"][
        "near_isothermal_keys_not_temperature_explained"
    ] += 1

    result = check_crosscheck_summary(rows, tampered)

    assert result.passed is False
    assert "assessment" in result.detail
