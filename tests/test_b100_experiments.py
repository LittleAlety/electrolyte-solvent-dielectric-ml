"""B100 experiment guards: comparability, power, and honest verdicts.

Scaling from 22 to 221 molecules changes conclusions, which is exactly why the
methodology has to be pinned down. The most dangerous failure at this scale is
comparing models fitted on different molecule sets: the first run had X0 evaluated on
257 molecules and X1 on 221, with constant baselines of 6.91 vs 5.09 -- a 36% gap that
had nothing to do with the descriptors.

Guarded:
  1. every E1 block is evaluated on the SAME molecule set
  2. the constant baseline is identical across blocks (proof of (1))
  3. the ridge has an intercept (the bug that once inverted the 22-molecule result)
  4. permutation p-values use the same scoring protocol as the observed value
  5. H4 reports INSUFFICIENT_POWER when a group is too small
  6. a family that fails LOFO transfer is reported as failing, not omitted
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"

E1 = OUT / "e1_manifest_b100.json"
E4 = OUT / "e4_manifest_b100.json"
E6 = OUT / "e6_manifest_b100.json"
H4 = OUT / "h4_manifest_b100.json"

pytestmark = pytest.mark.skipif(not E1.is_file(), reason="B100 experiments not run")


def _j(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------ comparability

def test_all_blocks_share_one_evaluation_set() -> None:
    e1 = _j(E1)
    ns = {b["n_used"] for b in e1["blocks"]}
    assert len(ns) == 1, (
        f"blocks were evaluated on different molecule counts {ns}; the comparison "
        f"is not paired and MAE differences cannot be attributed to features")
    assert e1["n_common_evaluation_set"] == list(ns)[0]


def test_constant_baseline_is_identical_across_blocks() -> None:
    """The strongest evidence of (1): a shared sample has a shared mean."""
    e1 = _j(E1)
    bases = {b["constant_baseline_mae"] for b in e1["blocks"]}
    assert len(bases) == 1, (
        f"constant baselines differ across blocks {bases}, which means the "
        f"underlying sample differs")


def test_comparability_rationale_is_recorded() -> None:
    e1 = _j(E1)
    assert "same" in e1["comparability_note"].lower() or "同一" in e1["comparability_note"]


# ------------------------------------------------ intercept / protocol

def test_every_block_beats_or_is_honest_about_the_baseline() -> None:
    e1 = _j(E1)
    for b in e1["blocks"]:
        expected = b["nested_loo_mae"] < b["constant_baseline_mae"]
        assert (b["beats_constant"] == "true") == expected, (
            f"{b['block']}: beats_constant flag disagrees with the numbers")


def test_negative_bias_would_signal_a_missing_intercept() -> None:
    """|bias| ~ MAE with a negative sign was the signature of the old defect."""
    e1 = _j(E1)
    for b in e1["blocks"]:
        mae = b["nested_loo_mae"]
        bias = abs(b["bias"])
        if mae > 0:
            assert bias / mae < 0.5, (
                f"{b['block']} has |bias|/MAE = {bias/mae:.3f}: the errors are "
                f"one-signed, which suggests the fit lost its intercept")


def test_permutation_p_uses_a_matching_protocol() -> None:
    e1 = _j(E1)
    for b in e1["blocks"]:
        assert "cv_mae_for_pvalue" in b, (
            "the p-value must be accompanied by the CV error it was compared "
            "against, so the null and the observation use the same protocol")
        assert 0.0 <= b["p_feature_permutation"] <= 1.0
        assert 0.0 <= b["p_label_permutation"] <= 1.0


# ------------------------------------------------ E6

def test_screening_verdict_matches_its_p_value() -> None:
    e6 = _j(E6)
    p = e6["p_random_at_least_as_good"]
    if p <= 0.05:
        assert e6["verdict"] == "SIGNIFICANTLY_BETTER_THAN_RANDOM"
    else:
        assert e6["verdict"] == "NOT_DEMONSTRATED_SUPERIOR_AT_THIS_POWER"


def test_topk_was_frozen_and_sensitivity_reported() -> None:
    e6 = _j(E6)
    assert e6["k"] == 10, "primary k must be the pre-registered Top-10"
    assert set(e6["topk_sensitivity"]) == {"k=5", "k=15"}, (
        "the two pre-registered sensitivity values must both be reported")


def test_regret_is_not_smaller_than_zero() -> None:
    """The oracle is by construction the best possible Top-k."""
    e6 = _j(E6)
    assert e6["regret"] >= 0
    assert e6["oracle_topk_mean"] >= e6["model_topk_mean"]


def test_screening_variants_are_reported_with_the_primary_block() -> None:
    """The primary block understates screening; the variant must be visible."""
    e6 = _j(E6)
    variants = e6.get("screening_variants") or []
    assert variants, "no screening variants reported"
    labels = {v["block"] for v in variants}
    assert "X0_plus_mu2_over_Vm" in labels, (
        "the mu^2/Vm screening variant is missing, so the deliverable would "
        "report only the weaker block")
    for v in variants:
        assert v["regret"] >= 0
        assert v["p_random_at_least_as_good"] > 0, "p must respect the +1 floor"
        assert 0.0 <= v["fraction_of_headroom_captured"] <= 1.0


def test_primary_block_understatement_is_flagged() -> None:
    """If a variant is far better, the manifest must say the primary understates."""
    e6 = _j(E6)
    cmp_ = e6.get("screening_comparison")
    assert cmp_ is not None, "screening comparison block missing"
    best = min((v["regret"] for v in e6.get("screening_variants") or []),
               default=None)
    if best is None:
        pytest.skip("no variants")
    if best < e6["regret"] * 0.5:
        assert cmp_["verdict"] == "PRIMARY_BLOCK_UNDERSTATES_SCREENING", (
            f"a variant achieves regret {best} against the primary "
            f"{e6['regret']}, but the manifest does not flag the understatement")


def test_regret_decomposition_is_present() -> None:
    """Regret concentrated in one outlier must be visible, not averaged away."""
    e6 = _j(E6)
    dec = e6.get("regret_decomposition")
    assert dec is not None, "regret decomposition missing"
    assert dec["contributors"], "no per-molecule contributions listed"
    assert dec.get("mechanism") in (
        "RANGE_COMPRESSION_AT_HIGH_EPSILON", "MIXED_RANKING_ERROR"), (
        f"unrecognised mechanism {dec.get('mechanism')}")
    assert "drop_largest_epsilon" in dec


# ------------------------------------------------ E4

def test_lofo_reports_failing_families() -> None:
    """A family the model cannot transfer to must appear as a failure."""
    e4 = _j(E4)
    assert e4["families"], "no per-family results"
    n_fail = sum(1 for f in e4["families"] if f["beats_baseline"] == "false")
    n_beat = sum(1 for f in e4["families"] if f["beats_baseline"] == "true")
    assert n_fail + n_beat == len(e4["families"])
    # the summary must agree with the per-family rows
    assert e4["summary"]["n_beating_baseline"] == n_beat


def test_applicability_domain_separation_is_computed() -> None:
    e4 = _j(E4)
    so = e4["structural_ood"]
    assert so["n_in_domain"] + so["n_out_domain"] > 0
    if so["mae_in_domain"] and so["mae_out_domain"]:
        expected = so["mae_out_domain"] / so["mae_in_domain"]
        assert abs(so["out_over_in_ratio"] - expected) < 1e-3


# ------------------------------------------------ H4

def test_h4_refuses_to_claim_with_insufficient_power() -> None:
    h4 = _j(H4)
    pw = h4["power"]
    if not pw["sufficient"]:
        assert h4["status"] == "INSUFFICIENT_POWER", (
            "H4 has an undersized group but is not labelled INSUFFICIENT_POWER")
        # and the direction may be mentioned, but must not be a confirmed finding
        assert h4["status"] != "CONFIRMED"


def test_h4_uses_relative_error_not_raw_mae() -> None:
    """Groups differ in epsilon scale; raw MAE would read scale as skill."""
    h4 = _j(H4)
    if "comparison" in h4:
        c = h4["comparison"]
        assert "weak_relative_mae" in c and "strong_relative_mae" in c
        assert "why_relative" in c
