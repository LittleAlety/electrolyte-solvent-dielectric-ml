# Guards for the Week 24-3 post-hoc re-analysis of the frozen W24 artefacts.
#
# The value of this file is that it pins the four readings that only exist because
# the census is N=246 rather than the paper N=12-18, and it pins them against the
# frozen tables rather than against a number typed by hand:
#
#   * the finite-population sampling law, not a bare 1/sqrt(N);
#   * the paper gap is axis-locked (oxidation reproduces, reduction does not);
#   * the ox/red asymmetry flips sign at the Li+ coordination rung;
#   * tau_b and the top-decile overlap decouple, so f_unresolved reads screening.
#
# It also pins the discipline: the probe is read-only, imports no subprocess, and
# declares itself post-hoc with zero scoreboard shots.

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w24_3_posthoc as w243

ARTIFACTS = ROOT / "probes" / "artifacts"
RUNG_TABLE = ARTIFACTS / "w24_rung_table.csv"
SUBSAMPLE = ARTIFACTS / "w24_subsample_tau.csv"
BORN = ARTIFACTS / "w24_born_curves.csv"
CONCLUSIONS = ARTIFACTS / "w24_3_conclusions.json"
FIGURE_ADEQUACY = ARTIFACTS / "w24_3_data_adequacy.png"
FIGURE_SCREENING = ARTIFACTS / "w24_3_screening_reading.png"

LIVE = CONCLUSIONS.is_file() and FIGURE_ADEQUACY.is_file() and FIGURE_SCREENING.is_file()


def _law():
    return w243.sampling_law(w243.read_rows(RUNG_TABLE), w243.read_rows(SUBSAMPLE))


def _sigma():
    return w243.paper_sigma(_law(), w243.read_rows(RUNG_TABLE))


def _flip():
    return w243.axis_flip(w243.read_rows(RUNG_TABLE))


def _decoupling():
    return w243.topk_decoupling(w243.read_rows(RUNG_TABLE))


def _born():
    return w243.born_regimes(w243.read_rows(BORN))


def test_the_probe_is_read_only_and_recomputes_nothing():
    source = Path(w243.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source, "the post-hoc probe must not shell out"
    assert "requests" not in source and "urllib" not in source
    for path in (w243.RUNG_TABLE, w243.SUBSAMPLE, w243.BORN):
        assert path.is_file(), str(path)
    # The three frozen inputs are opened read-only: only utf-8-sig read mode appears.
    assert source.count(chr(34) + "w" + chr(34)) == 1, "only the writer opens for write"


def test_sampling_law_is_the_finite_population_form():
    entries = _law()
    assert [entry["series"] for entry in entries] == list(w243.SERIES)
    for entry in entries:
        assert entry["fit_rmse"] <= 0.0100, entry["series"]
        assert entry["sd_at_n12"] > entry["sd_at_n18"] > entry["sd_at_n100"] > 0.0
        observed = [point["sd"] for point in entry["observed"]]
        assert observed == sorted(observed, reverse=True), entry["series"]
    # The closed form must actually beat a bare 1/sqrt(N): the fitted sd at the
    # population size is zero, so extrapolating must not blow up the way a power
    # law with a positive exponent does.
    # The correction is not cosmetic: measured against a bare power law the
    # implied exponent is steeper than 0.5 for every series, which is exactly
    # what the finite-population term predicts and a 1/sqrt(N) law forbids.
    import math
    for entry in entries:
        exponent = math.log(entry["sd_at_n12"] / entry["sd_at_n100"]) / math.log(100.0 / 12.0)
        assert exponent > 0.5, entry["series"]


def test_oxidation_reproduces_the_paper_and_reduction_does_not():
    entries = _sigma()
    oxidation = [entry for entry in entries if entry["axis"] == "ox"]
    reduction = [entry for entry in entries if entry["axis"] == "red"]
    assert len(oxidation) == 3 and len(reduction) == 3
    for entry in oxidation:
        assert abs(entry["sigma"]) <= 0.05, entry["series"]
    for entry in reduction:
        assert entry["sigma"] >= 2.0, entry["series"]
        assert entry["delta_tau_b"] > 0.0, entry["series"]
    worst = max(abs(entry["sigma"]) for entry in oxidation)
    best = min(entry["sigma"] for entry in reduction)
    assert worst < 0.05 < 2.0 <= best


def test_axis_asymmetry_flips_at_the_coordination_rung():
    entries = _flip()
    structural = [entry for entry in entries if entry["group"] == "P"]
    coordination = [entry for entry in entries if entry["group"] == "C"]
    assert len(structural) == 5 and len(coordination) == 9
    for entry in structural:
        assert entry["delta_ox_minus_red"] < 0.0, entry["rung"]
    for entry in coordination:
        assert entry["delta_ox_minus_red"] > 0.0, entry["rung"]
    # The mechanism is visible in the same table: the reduction shift falls below
    # the method resolution once Li+ binds.
    lookup = {entry["rung"]: entry for entry in entries}
    assert lookup["P0->P1"]["unresolved_red"] < 0.25
    for rung in ("C0->C1_dscf_gas", "C0->C1_dscf_thf",
                 "C0->C1_dscf_benzaldehyde", "C0->C1_dscf_water"):
        assert lookup[rung]["unresolved_red"] >= 0.75, rung


def test_topk_decoupling_prefers_the_unresolved_fraction_at_the_top():
    cuts, offenders = _decoupling()
    lookup = {entry["cut"]: entry for entry in cuts}
    for cut in ("top-10", "top-20"):
        entry = lookup[cut]
        assert abs(entry["rho_unresolved"]) > entry["rho_tau_b"], cut
    assert lookup["top-30"]["rho_tau_b"] > 0.94
    assert lookup["top-10"]["rho_tau_b"] < 0.85
    assert len(offenders) == 4
    for entry in offenders:
        assert entry["axis"] == "red", entry["rung"]
        assert entry["rung"].startswith("C0->C1"), entry["rung"]
        assert entry["topk10"] < 0.20 and entry["unresolved"] > 0.70


def test_born_failure_is_the_small_response_regime():
    entries, rho = _born()
    lookup = {entry["charge_state"]: entry for entry in entries}
    assert lookup["neutral"]["share_r2_ge_0.90"] < 0.10
    assert lookup["cation"]["share_r2_ge_0.90"] > 0.90
    assert lookup["anion"]["share_r2_ge_0.90"] > 0.90
    assert lookup["neutral"]["abs_C_mean_eV"] < 0.5 * lookup["cation"]["abs_C_mean_eV"]
    assert rho > 0.40


def test_the_committed_conclusions_match_a_fresh_recompute():
    payload = json.loads(CONCLUSIONS.read_text(encoding="utf-8"))
    assert payload["post_hoc"] is True
    assert payload["new_shot"] is False
    assert payload["scoreboard_shots"] == 0
    assert len(payload["readings"]) == 8
    fresh = {entry["series"]: round(entry["sigma"], 6) for entry in _sigma()}
    stored = {entry["series"]: round(entry["sigma"], 6) for entry in payload["paper_sigma"]}
    assert stored == fresh


def test_outputs_are_utf8_without_a_bom():
    raw = CONCLUSIONS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")


def test_figures_are_non_trivial():
    assert FIGURE_ADEQUACY.stat().st_size > 50_000
    assert FIGURE_SCREENING.stat().st_size > 50_000

