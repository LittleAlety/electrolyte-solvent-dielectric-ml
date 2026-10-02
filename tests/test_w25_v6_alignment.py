# Guards for the Week 25 alignment probe.
#
# Week 25 maps the six development directions of the parent manuscript (v6) onto
# this repository's frozen W21-W24 artefacts without spending a single
# electronic-structure cycle.  The guards below pin the three readings that only
# exist at this repository's scale, plus the discipline that makes them citable:
#
#   * the displacement-dispersion criterion reproduces at N=246 and collapses at
#     N=28, so it is a large-pool property and not a law about molecules;
#   * f_robust_inversion is nonzero on every rung here -- the opposite of v6's
#     branch C -- and it is a re-expression of f_unresolved, not a new quantity;
#   * the label budget is right-censored, so two of the three budget criteria are
#     vacuous and only H3b carries information;
#   * the probe is read-only and opens no shot on the frozen main scoreboard.

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w25_v6_alignment as w25

ARTIFACTS = ROOT / "probes" / "artifacts"
DISP_CSV = ARTIFACTS / "w25_dispersion_criterion.csv"
ROBUST_CSV = ARTIFACTS / "w25_robust_inversion_attribution.csv"
AL_CSV = ARTIFACTS / "w25_al_budget.csv"
BRANCH_CSV = ARTIFACTS / "w25_branch_claims.csv"
FIG_A = ARTIFACTS / "w25_dispersion_criterion.png"
FIG_B = ARTIFACTS / "w25_robust_inversion.png"
FIG_C = ARTIFACTS / "w25_al_budget.png"
SUMMARY = ROOT / "probes" / "w25_v6_alignment_summary.json"
REPORT = ROOT / "reports" / "w25_v6_alignment.md"
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _block_rows() -> list:
    return w25.read_rows(DISP_CSV)


def _label_containing(fragment: str) -> str:
    labels = {row["block"] for row in _block_rows()}
    matches = [label for label in labels if fragment in label]
    assert len(matches) == 1, matches
    return matches[0]


def _quantity(label: str, quantity: str) -> dict:
    rows = [
        row
        for row in _block_rows()
        if row["block"] == label and row["quantity"] == quantity
    ]
    assert len(rows) == 1, (label, quantity)
    return rows[0]


def test_the_probe_is_read_only_and_opens_no_shot():
    source = Path(w25.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source, "the probe must not shell out"
    assert "requests" not in source and "urllib" not in source
    assert w25.SCOREBOARD_SHOTS_THIS_WEEK == 0
    assert w25.CUMULATIVE_SCOREBOARD_ATTEMPTS == 12
    payload = _summary()
    assert payload["scoreboard_shots"] == 0
    assert payload["cumulative_scoreboard_attempts"] == 12


def test_the_preregistration_is_locked_and_the_summary_is_stamped_to_it():
    prereg = json.loads(w25.PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["arms"]["W25-1"]["bootstrap_draws"] == 20000
    assert prereg["arms"]["W25-1"]["seed"] == 20261002
    assert _summary()["prereg_sha256"] == _digest(w25.PREREG)


def test_every_delivered_artefact_matches_the_stamp_in_the_summary():
    stamped = _summary()["artifacts_sha256"]
    assert len(stamped) == 8
    for relative, digest in stamped.items():
        path = ROOT / relative.replace(chr(92), "/")
        assert path.is_file(), relative
        assert _digest(path) == digest, relative


def test_the_dispersion_criterion_reproduces_at_n246_and_collapses_at_n28():
    rungs = w25.load_rungs()
    assert len(rungs) == 38
    wide_pool = [rung for rung in rungs if rung["pool"].startswith("N=246")]
    narrow_pool = [rung for rung in rungs if rung["pool"].startswith("N=28")]
    assert (len(wide_pool), len(narrow_pool)) == (28, 10)
    merged = w25.dispersion_block(rungs, 2000, 20261002, "merged", "guard")
    wide = w25.dispersion_block(wide_pool, 2000, 20261013, "wide", "guard")
    narrow = w25.dispersion_block(narrow_pool, 2000, 20261024, "narrow", "guard")
    assert abs(merged["rho_std_tau"] + 0.7878) < 0.002
    assert abs(merged["rho_absmean_tau"] + 0.6569) < 0.002
    assert abs(merged["rho_std_funres"] - 0.8346) < 0.002
    for block in (merged, wide):
        assert block["rho_std_tau"] <= -0.70, block["label"]
        assert abs(block["rho_std_tau"]) >= abs(block["rho_absmean_tau"])
        assert block["ci_std_tau"][1] < 0.0, block["label"]
        assert block["rho_std_funres"] >= 0.70, block["label"]
    assert merged["lvr_direction_hits"] / merged["lvr_direction_total"] >= 8.0 / 38.0
    # The reading only this repository can buy: at N=28 the very same criterion
    # is flat and its bootstrap interval spans zero.
    assert narrow["rho_std_tau"] > -0.40
    assert narrow["ci_std_tau"][0] < 0.0 < narrow["ci_std_tau"][1]
    stored = _quantity(_label_containing("N=28"), "rho(std, tau_b)")
    assert float(stored["ci_lo"]) < 0.0 < float(stored["ci_hi"])


def test_robust_inversion_is_nonzero_on_every_rung_and_re_expresses_unresolved():
    rungs = w25.load_rungs()
    robust = w25.robust_block(rungs, 2000, 20261035)
    assert robust["n_rungs"] == 38
    assert robust["n_nonzero"] == 38
    assert robust["frobust_max"] > 0.20
    assert len(robust["strata"]) == 4
    assert robust["rho_frobust_funres"] >= 0.90
    assert robust["ci_frobust_funres"][0] > 0.0
    stored = _summary()["robust"]
    assert stored["n_nonzero"] == 38
    assert abs(stored["frobust_max"] - robust["frobust_max"]) < 0.04
    rows = w25.read_rows(ROBUST_CSV)
    assert len(rows) == 38
    nonzero = [row for row in rows if float(row["f_robust_inversion"]) > 0.0]
    assert len(nonzero) == 38


def test_the_label_budget_is_right_censored_for_every_acquisition():
    payload = _summary()["al"]
    assert payload["n_pool"] == 237
    assert set(payload["n_T_median"]) == {
        "random",
        "diversity",
        "uncertainty",
        "ranking_aware",
    }
    assert set(payload["n_T_median"].values()) == {121.0}
    rows = w25.read_rows(AL_CSV)
    assert len(rows) == 4 * 10 * 120
    assert {row["acquisition"] for row in rows} == set(payload["n_T_median"])
    for acquisition in payload["n_T_median"]:
        labels = sorted(
            int(row["labels"]) for row in rows if row["acquisition"] == acquisition
        )
        assert labels[0] == 4 and labels[-1] == 123 and len(labels) == 1200
    reachable = max(float(row["tau_b"]) for row in rows if row["tau_b"])
    assert 0.60 < reachable < 0.80, reachable


def test_the_branch_claims_record_the_departures_from_v6():
    rows = {row["branch"]: row for row in w25.read_rows(BRANCH_CSV)}
    assert sorted(rows) == list("ABCDEFG")
    assert rows["A"]["in_repo_verdict"] == rows["A"]["v6_verdict"]
    assert rows["C"]["v6_verdict"] == "NOT OBSERVED"
    assert rows["C"]["in_repo_verdict"].startswith("OBSERVED")
    assert rows["E"]["in_repo_verdict"] == "NOT TESTED"
    assert rows["F"]["in_repo_verdict"].startswith("NOT SUPPORTED")
    assert rows["G"]["in_repo_verdict"] == "SUPPORTED"
    assert _summary()["branches_differing"] == ["B", "C", "D", "E", "G"]


def test_the_verdicts_are_complete_and_match_the_stored_readings():
    verdicts = {entry["id"]: entry for entry in _summary()["verdicts"]}
    assert list(verdicts) == [
        "H1a",
        "H1b",
        "H1c",
        "H2",
        "H2a",
        "H2b",
        "H3a",
        "H3b",
        "H3c",
        "H4",
    ]
    for key in ("H1a", "H1b", "H1c", "H2a", "H3a", "H3c", "H4"):
        assert verdicts[key]["verdict"] == "\u6210\u7acb", key
    # The pre-registered H2 is the one that carries the mechanism claim: the
    # nonzero robust inversions are NOT confined to the conditional-state rungs,
    # so the "conditional-state artefact" explanation of the v6/v25 gap fails.
    for key in ("H2", "H2b", "H3b"):
        assert verdicts[key]["verdict"] == "\u5224\u5426", key
    assert verdicts["H2"]["reading"].startswith("28/38")
    assert verdicts["H2"]["reading"].endswith("0.262)")
    assert _summary()["robust"]["prereg_h2_violators"] == 10
    assert verdicts["H2b"]["reading"].startswith("0.3931")
    assert "n_T = 121" in verdicts["H3b"]["reading"]


def test_the_learnability_reading_is_reproducible():
    pool_x, pool_y, keys = w25.load_al_pool()
    assert pool_y.size == 237 and len(keys) == 237
    fresh = w25.learnability(pool_x, pool_y)
    stored = _summary()["al"]["learnability"]
    assert fresh["n"] == stored["n"] == 237
    assert abs(fresh["r2_loo"] - stored["r2_loo"]) < 1e-9
    assert abs(fresh["tau_b_loo"] - stored["tau_b_loo"]) < 1e-9
    assert 0.20 < fresh["r2_loo"] < 0.50
    assert fresh["alpha"] in w25.AL_ALPHAS


def test_outputs_are_utf8_without_a_bom_and_lf_only():
    for path in (DISP_CSV, ROBUST_CSV, AL_CSV, BRANCH_CSV, SUMMARY, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(BOM), path.name
        raw.decode("utf-8")
        assert CRLF not in raw, path.name


def test_figures_are_non_trivial_and_the_report_states_the_censoring_caveat():
    for figure in (FIG_A, FIG_B, FIG_C):
        assert figure.stat().st_size > 50_000, figure.name
    report = REPORT.read_text(encoding="utf-8")
    assert "budget_censored_at = 121" in report
    assert "N=28" in report and "\u540c\u540d\u4e0d\u540c\u9608" in report
    for token in ("H1a", "H2", "H2b", "H3b", "H4", "W25-1", "W25-4"):
        assert token in report, token
