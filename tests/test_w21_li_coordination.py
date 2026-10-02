"""Guards for the Week 21 Tier 3 C_1 Li+ coordination arm (framework Axis B / X2).

The reading this file protects is uncomfortable in two directions at once:

* the Li+ step keeps the HOMO ordering (rho > 0.6, the top decile overlaps 10/11)
  but *destroys* the LUMO ordering (the top decile overlaps 0/22);
* the pre-registered structural QC criterion (Li-X distance + Mulliken charge)
  labels the no-donor alkanes "intact", even though the post-hoc binding-energy
  check shows those C_1 structures are not bound states at all.

If a later change silently turns either of those into a comfortable story, the
report has changed its meaning.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes/w21_li_coordination_summary.json"
PREREG = ROOT / "probes/w21_li_coordination_prereg.json"
LAYER = ROOT / "data/processed/w21_li_coordination_layer.csv"
DELTA = ROOT / "probes/artifacts/w21_li_coordination_delta_stats.csv"
TOPK = ROOT / "probes/artifacts/w21_li_coordination_topk.csv"
BATT = ROOT / "probes/artifacts/w21_li_coordination_batt_step.csv"
QC = ROOT / "probes/artifacts/w21_li_coordination_qc.csv"
BINDING = ROOT / "probes/artifacts/w21_li_coordination_binding_posthoc.csv"
RETRY = ROOT / "probes/artifacts/w21_li_coordination_scf_retry_posthoc.csv"
REPORT = ROOT / "reports/w21_li_coordination.md"
FROZEN = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)
ARTIFACTS = (LAYER, DELTA, TOPK, BATT, QC, BINDING, RETRY)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_and_the_pool_reproduces_it() -> None:
    prereg = _json(PREREG)
    assert prereg["status"] == "locked_before_run"
    summary = _json(SUMMARY)
    assert summary["preregistration"]["status"] == "locked_before_run"
    import hashlib

    assert summary["preregistration"]["sha256"] == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    assert summary["pool"]["n_compounds"] == 246
    assert summary["pool"]["runs"] == 492
    assert summary["pool"]["matches_prereg"] is True
    for motif_class, expected in prereg["pool"]["motif_class_counts"].items():
        assert summary["pool"]["motif_counts"][motif_class] == expected, motif_class


def test_nothing_is_promoted_and_no_shot_is_taken() -> None:
    summary = _json(SUMMARY)
    assert summary["promotion"]["promoted"] is False
    assert summary["promotion"]["main_scoreboard_attempts"] == 0
    assert summary["promotion"]["cumulative_main_scoreboard_attempts"] == 12
    assert [float(value) for value in summary["promotion"]["frozen_untouched"]] == list(FROZEN)


def test_the_w21_1_regression_row_reproduces_the_frozen_reading() -> None:
    """The P0 row must re-derive w21_1 bit for bit, or the new arm is not comparable."""

    row = {entry["arm"]: entry for entry in _rows(BATT)}["P0_themol_geometry_w21_1"]
    assert row["resolved_in_both"] == "451"
    assert row["robust_inversions"] == "0"
    # the artifact stores eight decimals, so compare at that resolution
    assert abs(float(row["f_naive_inversion"]) - 0.1556122448979592) < 1e-7
    assert abs(float(row["kendall_tau_b"]) - 0.6887755102040816) < 1e-7
    assert abs(float(row["spearman_rho"]) - 0.8639795918367346) < 1e-7


def test_the_li_step_keeps_zero_robust_inversions_on_the_batt_subset() -> None:
    row = {entry["arm"]: entry for entry in _rows(BATT)}["C1_this_arm_li"]
    assert row["robust_inversions"] == "0"
    assert int(row["resolved_in_both"]) > 0
    assert float(row["spearman_rho"]) > 0.7


def test_the_homo_ordering_survives_the_coordination_step() -> None:
    homo = _json(SUMMARY)["channels"]["homo"]
    assert homo["n"] == 217
    assert homo["spearman_rho"] > 0.6
    assert homo["kendall_tau_b"] > 0.45
    assert abs(homo["topk"]["k/N=10%"]["overlap"] - 10.0 / 11.0) < 1e-12
    assert homo["topk"]["k/N=10%"]["k"] == 22


def test_the_lumo_ordering_collapses_under_coordination() -> None:
    channels = _json(SUMMARY)["channels"]
    assert channels["lumo"]["n"] == 217
    assert channels["lumo"]["topk"]["k/N=10%"]["overlap"] == 0.0
    assert channels["lumo"]["spearman_rho"] < 0.4
    assert channels["lumo"]["spearman_rho"] < channels["homo"]["spearman_rho"]
    assert channels["lumo"]["f_naive_inversion"] > channels["homo"]["f_naive_inversion"]


def test_the_registered_qc_thresholds_are_applied_as_written() -> None:
    rows = [row for row in _rows(LAYER) if row["c1_status"] == "ok"]
    checked = 0
    for row in rows:
        if not row["li_min_dist_A"] or not row["li_mulliken_q"]:
            continue
        distance = float(row["li_min_dist_A"])
        charge = float(row["li_mulliken_q"])
        checked += 1
        if row["qc_status"] == "intact":
            assert distance <= 2.60 and charge >= 0.30, row["name"]
        elif row["qc_status"] == "dissociated":
            assert distance > 3.50 or charge < 0.10, row["name"]
    assert checked == 239


def test_the_post_hoc_binding_check_flags_the_unbound_reference_rows() -> None:
    summary = _json(SUMMARY)
    binding = summary["post_hoc"]["li_binding_energy"]
    assert binding["registration"] == "post_hoc_not_preregistered"
    rows = _rows(BINDING)
    assert rows and "binding_verdict" in rows[0]
    for row in rows:
        if row["motif_class"] == "no_motif":
            assert row["binding_verdict"] == "not_a_bound_state", row["name"]
    assert binding["n_not_a_bound_state"] == sum(
        1 for row in rows if row["binding_verdict"] != "bound"
    )
    assert binding["by_motif_class_eV"]["lone_pair"]["median_eV"] < 0


def test_the_scf_retry_is_labelled_post_hoc_and_does_not_rewrite_the_layer() -> None:
    summary = _json(SUMMARY)
    retry = summary["post_hoc"]["scf_retry"]
    assert retry["registration"] == "post_hoc_not_preregistered"
    assert retry["attempted"] == len(_rows(RETRY))
    assert retry["recovered"] + retry["still_failed"] == retry["attempted"]
    failures = summary["qc"]["failed_arms"]
    failed_arms = sum(
        (entry["c0_status"] != "ok") + (entry["c1_status"] != "ok") for entry in failures
    )
    assert failed_arms == retry["attempted"]
    for entry in failures:
        assert entry["c0_status"] != "ok" or entry["c1_status"] != "ok"
        assert "returncode" in entry["error"]


def test_no_artifact_carries_crlf_or_a_bom() -> None:
    for path in ARTIFACTS:
        raw = path.read_bytes()
        assert b"\r\n" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path


def test_the_layer_columns_are_the_ones_the_summary_declares() -> None:
    summary = _json(SUMMARY)
    with LAYER.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == list(summary["layer"]["fields"])


def test_the_report_states_the_boundary_and_the_two_directions() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for needle in (
        "X2",
        "Gate 1",
        "未闭合",
        "GFN2-xTB",
        "no_motif",
        "not_a_bound_state",
        "事后",
        "246",
    ):
        assert needle in text, needle
