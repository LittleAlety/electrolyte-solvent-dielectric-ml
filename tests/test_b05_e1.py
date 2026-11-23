"""B05-E1 guards: an exploratory model must not masquerade as a finding.

With n=22 the failure mode is not a wrong MAE -- it is a *presentational* one:
reporting "electronic descriptors improve MAE by X%" when the improvement is
inside permutation noise, or when the model is worse than predicting the mean.

Guarded:
  1. the result is labelled exploratory, not confirmatory
  2. a permutation null exists for every model
  3. the constant baseline is reported so a useless model cannot look useful
  4. the delta is not claimed to be significant when it is inside the null
  5. LOO is used (molecule-level grouping), not a random split
  6. coverage is reported
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E1 = REPO_ROOT / "outputs" / "b05" / "E1_structure_vs_electronic"

pytestmark = pytest.mark.skipif(
    not (E1 / "e1_manifest.json").is_file(),
    reason="E1 not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_result_is_labelled_exploratory() -> None:
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    assert man["status"] == "EXPLORATORY_NOT_CONFIRMATORY"
    assert "n=" in man["exploratory_reason"]

    report = (E1 / "e1_report.md").read_text(encoding="utf-8")
    assert "探索性" in report
    assert "不构成" in report and "确认性" in report


def test_every_model_has_a_permutation_null() -> None:
    nulls = _load(E1 / "permutation_null.csv")
    metrics = _load(E1 / "metrics.csv")
    assert len(nulls) == len(metrics), "a model lacks a permutation null"
    for n in nulls:
        assert int(n["n_permutations"]) >= 100, (
            f"{n['model']} used only {n['n_permutations']} permutations")
        assert 0.0 <= float(n["permutation_p_value"]) <= 1.0
        # The null must actually span a range, otherwise it is not a distribution.
        assert float(n["null_mae_q05"]) < float(n["null_mae_median"])


def test_constant_baseline_is_reported() -> None:
    """A model worse than 'predict the mean' must not be presented as a gain."""
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    base = man["constant_baseline"]
    assert base["mae"] > 0
    for m in man["metrics"]:
        assert "beats_constant_baseline" in m
        # Consistency: the flag must agree with the arithmetic.
        expected = "true" if float(m["mae"]) < base["mae"] else "false"
        assert m["beats_constant_baseline"] == expected, (
            f"{m['model']}: flag contradicts MAE {m['mae']} vs baseline {base['mae']}")


def test_delta_is_not_overclaimed() -> None:
    """If |ΔMAE| is inside the null spread, the report must not call it a gain."""
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    delta = abs(man["delta_mae_x1_minus_x0"])
    nulls = {n["model"]: n for n in _load(E1 / "permutation_null.csv")}
    spread = abs(float(nulls["X0_structure_only"]["null_mae_median"])
                 - float(nulls["X0_structure_only"]["null_mae_q05"]))

    report = (E1 / "e1_report.md").read_text(encoding="utf-8")
    if delta < spread:
        assert "不能" in report and "增量价值" in report, (
            "a delta inside the null spread is presented as a gain")


def test_validation_is_leave_one_out() -> None:
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    assert man["validation"]["scheme"] == "leave_one_out"
    # Each model must have exactly one prediction per molecule.
    preds = _load(E1 / "predictions_loo.csv")
    by_model: dict[str, list[str]] = {}
    for p in preds:
        by_model.setdefault(p["model"], []).append(p["measurement_id"])
    for model, ids in by_model.items():
        assert len(ids) == len(set(ids)), f"{model} predicted a molecule twice"


def test_coverage_is_reported_not_assumed() -> None:
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    cov = man["coverage"]
    assert cov["n_pool"] == 22
    assert cov["n_comparable"] <= cov["n_pool"]
    assert "missing_x0" in cov and "missing_x1" in cov


def test_predictions_are_self_consistent() -> None:
    """residual must equal y_pred - y_true for every row."""
    for p in _load(E1 / "predictions_loo.csv"):
        expected = float(p["y_pred"]) - float(p["y_true"])
        assert abs(float(p["residual"]) - expected) < 1e-6, (
            f"{p['model']}/{p['measurement_id']} residual inconsistent")


def test_metrics_are_recomputable_from_predictions() -> None:
    """MAE reported must equal MAE recomputed from the prediction file."""
    metrics = {m["model"]: m for m in _load(E1 / "metrics.csv")}
    preds = _load(E1 / "predictions_loo.csv")
    for model, m in metrics.items():
        rows = [p for p in preds if p["model"] == model]
        mae = sum(abs(float(p["residual"])) for p in rows) / len(rows)
        assert abs(mae - float(m["mae"])) < 1e-5, (
            f"{model}: reported MAE {m['mae']} != recomputed {mae:.6f}")
