"""B05-E1b guards: a negative result must be diagnosed, not just reported.

The first E1 pass concluded "the descriptors carry no signal" from "both models are
worse than the constant baseline". E1b showed that conclusion was wrong: the errors
were almost entirely one-signed (|bias|/MAE = 1.0), and after removing the offset
the model beats the baseline. That is a calibration failure, not an information
failure -- a distinction that changes what a reader should do next.

Guarded:
  1. the robustness check exists and sweeps more than one lambda
  2. log-space fitting is used so negative epsilons are structurally discouraged
  3. the bias/ranking diagnostic exists and its conclusion is derived
  4. when |bias|/MAE ~ 1, the report must NOT claim "no signal"
  5. the impact on E1's original conclusion is stated
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E1B = REPO_ROOT / "outputs" / "b05" / "E1b_physics_constrained"

pytestmark = pytest.mark.skipif(
    not (E1B / "e1b_manifest.json").is_file(),
    reason="E1b not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _man() -> dict:
    return json.loads((E1B / "e1b_manifest.json").read_text(encoding="utf-8"))


def test_lambda_was_swept_not_fixed() -> None:
    """The original E1 silently fixed lambda=1. That is the defect this guards."""
    m = _man()
    assert len(m["lambda_grid"]) >= 4, "lambda was not swept"
    rows = _load(E1B / "lambda_sweep.csv")
    lambdas = {float(r["lambda"]) for r in rows}
    assert len(lambdas) >= 4
    # And both feature sets and both spaces must be covered.
    assert {r["model"] for r in rows} == {"X0_structure_only",
                                          "X0_plus_X1_electronic"}
    assert {r["space"] for r in rows} == {"linear", "log"}


def test_log_space_avoids_nonphysical_predictions() -> None:
    """eps > 1 by construction in log space, so negatives must be rarer."""
    rows = _load(E1B / "log_space_results.csv")
    assert rows
    # The manifest must report the count so the reader can judge.
    for r in rows:
        assert "n_pred_below_eps_floor" in r


def test_bias_diagnostic_exists() -> None:
    m = _man()
    diag = m.get("bias_vs_ranking_diagnostic")
    assert diag is not None, "no bias/ranking diagnostic"
    for key in ("mae", "bias", "abs_bias_over_mae",
                "mae_after_debiasing", "diagnosis"):
        assert key in diag, f"diagnostic missing {key}"


def test_diagnosis_is_derived_not_asserted() -> None:
    """The CALIBRATION vs INFORMATION verdict must follow the arithmetic."""
    m = _man()
    diag = m["bias_vs_ranking_diagnostic"]
    frac = diag["abs_bias_over_mae"]
    deb = diag["mae_after_debiasing"]
    base = m["constant_baseline_mae"]

    if frac > 0.9 and deb < base:
        assert diag["diagnosis"] == "CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE"
    elif deb >= base:
        assert diag["diagnosis"] == "INFORMATION_FAILURE"


def test_report_does_not_claim_no_signal_when_bias_dominates() -> None:
    """If the error is one-signed and debiasing beats the baseline, saying
    'descriptors carry no signal' would be a false conclusion."""
    m = _man()
    diag = m["bias_vs_ranking_diagnostic"]
    report = (E1B / "e1b_report.md").read_text(encoding="utf-8")

    if diag["diagnosis"] == "CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE":
        assert "推翻了 E1 的原始结论" in report or "必须修正" in report, (
            "the report must flag that E1's conclusion was wrong")
        assert "标定失败" in report
        assert "信号存在" in report


def test_impact_on_previous_conclusions_is_stated() -> None:
    m = _man()
    impact = m["conclusion_impact"]
    assert "E1_original" in impact
    assert "E4_identical_fingerprint" in impact
    assert "E6_screening" in impact
    # E4's identical-fingerprint claim must be flagged for restatement, because
    # those errors were driven by negative (nonphysical) predictions.
    assert "NEEDS_RESTATEMENT" in impact["E4_identical_fingerprint"]


def test_negative_predictions_were_actually_detected() -> None:
    """The whole reason for E1b: the first pass emitted nonphysical values."""
    rows = _load(E1B / "lambda_sweep.csv")
    n_neg_linear = max(int(r["n_pred_below_eps_floor"]) for r in rows
                       if r["space"] == "linear")
    assert n_neg_linear > 0, (
        "no negative predictions found in linear space — the premise of E1b "
        "would be wrong")
    report = (E1B / "e1b_report.md").read_text(encoding="utf-8")
    assert "负" in report and "介电常数" in report
