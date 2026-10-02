"""Guards for the Week 21 decision-metric pilot (framework sections 9, 10, 13).

The reading this file protects is an uncomfortable one: at the pre-registered
95% separation rule the cheap proxy and the reference layer share *zero*
resolvable sign flips, even though 15.6% of pairs flip order.  If a later change
turns those flips into "robust inversions" without touching the tolerance, the
report has silently changed its meaning.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes/w21_rank_stability_summary.json"
PREREG = ROOT / "probes/w21_rank_stability_prereg.json"
PAIRS = ROOT / "probes/artifacts/w21_rank_pairs.csv"
TOPK = ROOT / "probes/artifacts/w21_topk_overlap.csv"
SPLITS = ROOT / "probes/artifacts/w21_split_metrics.csv"
SENSITIVITY = ROOT / "probes/artifacts/w21_tolerance_sensitivity.csv"
REPORT = ROOT / "reports/w21_rank_stability.md"
W19 = ROOT / "probes/w19_batt_gap_crosscheck_summary.json"
FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_and_the_pool_reproduces_the_w19_arm() -> None:
    prereg = _json(PREREG)
    assert prereg["status"] == "locked_before_run"
    summary = _json(SUMMARY)
    assert summary["preregistration"]["status"] == "locked_before_run"
    assert summary["pool"]["n_compounds"] == 49
    assert summary["pool"]["pairs"] == 1176
    assert summary["promotion"]["main_scoreboard_attempts"] == 0
    assert summary["promotion"]["promoted"] is False
    assert [float(value) for value in summary["promotion"]["frozen_untouched"]] == list(FROZEN)
    w19 = _json(W19)
    pairs = _rows(PAIRS)
    assert len(pairs) == 1176
    keys = {row["key_i"] for row in pairs} | {row["key_j"] for row in pairs}
    assert keys == set(w19["primary"]["keys"])


def test_zero_robust_inversions_at_the_registered_tolerance() -> None:
    homo = _json(SUMMARY)["channels"]["homo"]["scalars"]
    assert homo["robust_inversions"] == 0
    assert homo["f_robust_inversion"] == 0.0
    assert homo["resolved_in_both"] == 451
    assert homo["pairs"] == 1176
    assert abs(homo["f_naive_inversion"] - 0.1556122448979592) < 1e-09
    assert abs(homo["f_unresolved_at_least_one"] - 0.6164965986394557) < 1e-09
    assert abs(homo["kendall_tau_b"] - 0.6887755102040816) < 1e-09
    assert abs(homo["spearman_rho"] - 0.8639795918367346) < 1e-09
    summary = _json(SUMMARY)["channels"]["homo"]
    assert summary["f_robust_inversion_ci95"]["draws_used"] == 5000
    assert summary["permutation"]["p_value"] == 1.0


def test_the_denominator_patch_is_reported() -> None:
    """Framework 9.2 divides by pairs resolved in both; that drops most pairs."""

    homo = _json(SUMMARY)["channels"]["homo"]["scalars"]
    assert abs(homo["f_resolved_in_exactly_one"] - 0.5654761904761905) < 1e-09
    assert homo["f_resolved_in_exactly_one"] > homo["f_robust_inversion"]


def test_the_tolerance_scan_is_labelled_and_monotone() -> None:
    rows = _rows(SENSITIVITY)
    # every channel carries exactly one pre-registered row, and it is always z = 1.96
    for channel in ("homo", "lumo", "gap"):
        registered = [row for row in rows if row["registration"] == "pre_registered" and row["channel"] == channel]
        assert len(registered) == 1, channel
        assert float(registered[0]["z"]) == 1.96
    homo = [row for row in rows if row["channel"] == "homo"]
    assert [row for row in homo if row["registration"] == "pre_registered"][0]["robust_inversions"] == "0"
    ordered = sorted(homo, key=lambda row: float(row["z"]))
    counts = [int(row["robust_inversions"]) for row in ordered]
    # z ascending -> robust inversions descend: a looser band can only add flips
    assert counts == sorted(counts, reverse=True), ordered
    assert counts[0] > counts[-1]
    assert counts[-1] == 0
    assert [float(row["z"]) for row in ordered] == [0.0, 0.674, 1.0, 1.96]


def test_topk_overlap_and_regret_are_what_the_report_says() -> None:
    rows = {row["k_rule"]: row for row in _rows(TOPK) if row["channel"] == "homo"}
    assert rows["k/N=10%"]["overlap"] == "0.400000"
    assert rows["k/N=20%"]["overlap"] == "0.900000"
    assert float(rows["k/N=10%"]["selection_regret_eV"]) > 0.5
    assert float(rows["k/N=20%"]["selection_regret_eV"]) < 0.2


def test_no_csv_carries_crlf_and_the_report_states_the_boundary() -> None:
    for path in (PAIRS, TOPK, SPLITS, SENSITIVITY):
        assert bytes([13, 10]) not in path.read_bytes(), path
    text = REPORT.read_text(encoding="utf-8")
    for needle in ("robust inversion", "machinery pilot", "threshold-based decision error", "n = 49"):
        assert needle in text, needle


def test_splits_keep_the_honest_cuts_negative() -> None:
    rows = [row for row in _rows(SPLITS) if row["metric"] == "r2" and row["mean"]]
    by = {(row["split"], row["model"]): float(row["mean"]) for row in rows}
    assert by[("random_repeated_kfold_5x10", "random_forest")] > 0.5
    assert by[("group_kfold_scaffold_5", "random_forest")] < 0.0
    for model in (
        "ridge",
        "krr_tuned",
        "gpr",
        "random_forest",
        "gradient_boosting",
        "single_feature_baseline",
    ):
        assert by[("lofo_family_min5", model)] < 0.0, model
    assert "mean_baseline" in {row["model"] for row in rows}