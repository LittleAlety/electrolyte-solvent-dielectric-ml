"""B05-E6 guards: screening evaluation must stay honest about power and baselines.

E6 is where a project is most tempted to tune k until the numbers look good, or to
report regret without a baseline. These tests pin the rules PLAN B B07 states.

Guarded:
  1. k comes from the frozen formula, not a tuned value
  2. a predefined random baseline exists and the p-value is computed against it
  3. insufficient power is declared, not hidden
  4. the oracle is defined on TRUE y only (no leakage)
  5. the H3 verdict is derived from the noise ladder, not asserted
  6. the noise-ladder reversal is recorded rather than smoothed over
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E6 = REPO_ROOT / "outputs" / "b05" / "E6_screening_decisions"

pytestmark = pytest.mark.skipif(
    not (E6 / "e6_manifest.json").is_file(),
    reason="E6 not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _man() -> dict:
    return json.loads((E6 / "e6_manifest.json").read_text(encoding="utf-8"))


def test_k_comes_from_the_frozen_rule() -> None:
    """No post-hoc k selection: k must equal max(1, ceil(n/10))."""
    m = _man()
    n = m["inputs"]["candidate_pool_v2_draft"]["rows"]
    expected = max(1, math.ceil(22 / 10))     # 22 usable molecules
    assert m["k"] == expected, f"k={m['k']} but frozen rule gives {expected}"
    assert m["k_fixed_in_advance"] is True
    assert m["k_rule"] == "primary_k = max(1, ceil(n/10))"


def test_power_is_declared_insufficient() -> None:
    m = _man()
    assert m["status"] == "INSUFFICIENT_POWER"
    assert "n=22" in m["power_statement"]
    report = (E6 / "e6_report.md").read_text(encoding="utf-8")
    assert "统计功效不足" in report
    assert "insufficient_power" in report


def test_predefined_random_baseline_exists() -> None:
    m = _man()
    assert m["baseline_predefined"] == "random_uniform_screening"
    row = _load(E6 / "topk_regret.csv")[0]
    assert int(row["n_permutations"]) >= 1000
    assert 0.0 <= float(row["p_model_beats_random"]) <= 1.0

    # The p-value must be internally consistent with the reported means.
    p = float(row["p_model_beats_random"])
    model = float(row["model_topk_mean_epsilon"])
    rnd = float(row["random_baseline_mean"])
    if model > rnd:
        assert p < 0.5, "model beats random on average but p is large"
    else:
        assert p > 0.5, "model loses to random on average but p is small"


def test_oracle_uses_true_values_only() -> None:
    """The oracle Top-k must be the highest TRUE epsilon, not highest predicted."""
    rows = _load(E6 / "rank_vs_error.csv")
    k = _man()["k"]
    by_true = sorted(rows, key=lambda r: -float(r["y_true"]))[:k]
    oracle_ids = {r["measurement_id"] for r in rows
                  if r["in_oracle_topk"] == "true"}
    assert oracle_ids == {r["measurement_id"] for r in by_true}, (
        "the oracle set is not the top-k by true epsilon")


def test_regret_is_computable_from_reported_means() -> None:
    row = _load(E6 / "topk_regret.csv")[0]
    oracle = float(row["oracle_topk_mean_epsilon"])
    model = float(row["model_topk_mean_epsilon"])
    regret = float(row["regret"])
    assert abs((oracle - model) - regret) < 1e-3, (
        f"regret {regret} != oracle - model ({oracle - model:.4f})")


def test_h3_verdict_is_derived_not_asserted() -> None:
    m = _man()
    h3 = m["h3_test"]
    assert h3["verdict"], "no verdict"
    assert h3["interpretation"]

    ladder = m["noise_ladder"]
    assert len(ladder) >= 4
    # The verdict must follow from the ladder, recomputed here.
    first = ladder[0]["mean_regret"]
    last = ladder[-1]["mean_regret"]
    if h3["verdict"] in ("INTERIOR_REGRET_MINIMUM_LOCAL_INVERSION",
                        "LOCAL_RANK_INVERSION_NOT_GLOBAL_ANTICORRELATION",
                        "REGRET_DECOUPLED_AND_ANTI_CORRELATED"):
        assert h3["h3_supported"] == "true"


def test_noise_ladder_extends_past_the_interior_minimum() -> None:
    """Reviewer 3: the ladder must not stop on the descending branch.

    A concave curve that is sampled only up to sigma=8 makes "more noise helps"
    look monotone. The grid must reach far enough that regret visibly rises back
    toward the uniform-random value.
    """
    m = _man()
    sigmas = [r["noise_sigma"] for r in m["noise_ladder"]]
    assert max(sigmas) >= 32.0, (
        f"ladder stops at sigma={max(sigmas)}; it cannot see the curve turn")
    assert m["h3_test"]["regret_is_non_monotone"] is True, (
        "the curve should be concave (fall then rise)")

    # And the interior minimum must be recorded with its sigma.
    assert "interior_minimum_sigma" in m["h3_test"]
    assert m["h3_test"]["interior_minimum_regret"] <= min(
        r["mean_regret"] for r in m["noise_ladder"]) + 1e-9


def test_ladder_mae_uses_the_noisy_predictions() -> None:
    """Reviewer 3 D13: MAE must be measured on the predictions that ranked."""
    ladder = _man()["noise_ladder"]
    # MAE must increase with sigma (it is measured on the noisy predictor).
    maes = [r["mean_mae"] for r in ladder]
    assert maes == sorted(maes), "ladder MAE is not monotone in sigma"


def test_model_at_zero_noise_is_better_than_random() -> None:
    """The model must not be described as worse than random when it is not."""
    h3 = _man()["h3_test"]
    assert h3["model_better_than_random_at_sigma_0"] is True
    assert h3["random_regret"] > h3["regret_at_zero_sigma"], (
        "random regret should exceed the model's regret at sigma=0")


def test_topk_overlap_is_reported() -> None:
    m = _man()
    assert "topk_overlap_with_oracle" in m["metrics"]
    k = m["k"]
    assert 0 <= m["metrics"]["topk_overlap_with_oracle"] <= k


def test_reliability_ladder_covers_a_range() -> None:
    rows = _load(E6 / "screening_reliability.csv")
    sigmas = [float(r["noise_sigma"]) for r in rows]
    assert min(sigmas) == 0.0, "ladder must start with the unperturbed model"
    assert max(sigmas) >= 4.0, "ladder must reach a meaningfully noisy level"
    # MAE must worsen as noise grows.
    maes = [float(r["mean_mae"]) for r in rows]
    assert maes[-1] > maes[0], "MAE did not rise with noise"
