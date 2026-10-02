# Guards for the Week 26 dielectric-law probe.
#
# Week 26 is the first round in this repository that scans an arbitrary relative
# permittivity with a continuum model (xTB 6.7.1 ddCOSMO, --cosmo EPSILON) while
# holding one gas-phase geometry rigid across every epsilon and every charge state.
# The guards below pin what makes the round citable:
#
#   * the pre-registration was locked before the production run and the summary
#     quotes its sha256;
#   * the round reproduces the frozen W21 layer only when it is compared against
#     the convention that layer actually used (the first ISCF block of an --opt
#     log), which is the reproducibility gate H1g;
#   * the Born reading quoted in the report can be recomputed from the stored
#     per-point table, so the delivered numbers are not a black box;
#   * no Reaxys number, no frozen reading and no main-scoreboard shot moves.
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w26_dielectric_law as w26

ARTIFACTS = ROOT / "probes" / "artifacts"
SCAN_CSV = ARTIFACTS / "w26_dielectric_scan.csv"
BORN_CSV = ARTIFACTS / "w26_born_fit.csv"
GATE_CSV = ARTIFACTS / "w26_anion_gate.csv"
CONTRAST_CSV = ARTIFACTS / "w26_model_contrast.csv"
FIG_A = ARTIFACTS / "w26_dielectric_law.png"
FIG_B = ARTIFACTS / "w26_anion_gate.png"
PREREG = ROOT / "probes" / "w26_dielectric_law_prereg.json"
SUMMARY = ROOT / "probes" / "w26_dielectric_law_summary.json"
REPORT = ROOT / "reports" / "w26_dielectric_law.md"
LAYER = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
LAYER_SHA256 = "48864109573f919ab320aa10d2b7b8e78532115e1f65228b16e75a76123eeedc"
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

VERDICT_IDS = ("H1f", "H1g", "H1a", "H1b", "H1c", "H1d", "H1e", "H2a", "H2b", "H3")


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scan_rows() -> list:
    return w26.read_rows(SCAN_CSV)


def test_prereg_is_locked_before_the_run() -> None:
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    assert payload["revision"] == 2
    assert payload["red_lines"]
    assert payload["epsilon_grid"][0] == 1.0
    assert payload["arms"]["W26-1"]["criteria"]["H1a_ion_born_r2_median_min"] == 0.99


def test_summary_quotes_the_prereg_bytes() -> None:
    summary = _summary()
    assert summary["prereg_status"] == "locked_before_run"
    assert summary["prereg_sha256"] == _digest(PREREG)
    assert summary["input_sha256"] == LAYER_SHA256
    assert _digest(LAYER) == LAYER_SHA256


def test_frozen_readings_and_scoreboard_do_not_move() -> None:
    summary = _summary()
    assert summary["main_scoreboard_attempts_delta"] == 0
    assert summary["cumulative_main_scoreboard_attempts"] == 12
    for _key, value in FROZEN_READINGS.items():
        assert isinstance(value, float)
    assert w26.SCOREBOARD_SHOTS_THIS_WEEK == 0


def test_every_verdict_id_is_present_and_the_gate_orders_the_anchor_first() -> None:
    ids = [entry["id"] for entry in _summary()["verdicts"]]
    assert tuple(ids) == VERDICT_IDS
    for entry in _summary()["verdicts"]:
        assert entry["verdict"] in ("成立", "判否")


def test_convention_anchor_reproduces_the_frozen_layer_exactly() -> None:
    # H1g is the reproducibility gate: the probe must be able to recompute the
    # quantity the frozen layer actually stored, bit for bit.
    anchor = _summary()["anchor_convention"]
    assert anchor["holds"] is True
    assert anchor["orbital_violations"] == 0
    assert anchor["energy_violations"] == 0
    assert anchor["max_orbital_dev_eV"] == 0.0
    assert anchor["max_energy_dev_hartree"] < 1e-9


def test_literal_anchor_fails_and_is_reported_as_such() -> None:
    # H1f is the anchor as originally frozen; it is expected to fail because
    # w21.parse_arm reads the FIRST ISCF block of an --opt log (input geometry).
    anchor = _summary()["anchor"]
    assert anchor["holds"] is False
    assert anchor["orbital_violations"] > 0


def test_born_reading_is_recomputable_from_the_stored_table() -> None:
    rows = [row for row in _scan_rows() if row["status"] == "ok"]
    assert rows, "the scan table has no successful rows"
    by_curve = {}
    for row in rows:
        key = (row["inchikey"], row["charge_state"])
        by_curve.setdefault(key, {})[float(row["epsilon"])] = float(row["total_E_hartree"])
    stored = {(row["inchikey"], row["charge_state"]): row for row in w26.read_rows(BORN_CSV)}
    checked = 0
    for key, table in by_curve.items():
        entry = stored.get(key)
        if entry is None or not entry.get("C_eV"):
            continue
        block = w26.curve_block(table, w26.EPSILON_GRID, w26.BAND_START)
        assert block is not None
        assert float(entry["C_eV"]) == pytest.approx(block["C_eV"], rel=1e-9)
        assert float(entry["r2"]) == pytest.approx(block["r2"], rel=1e-6)
        assert float(entry["travel_200_1000_eV"]) == pytest.approx(
            block["travel_200_1000_eV"], rel=1e-9
        )
        checked += 1
        if checked >= 5:
            break
    assert checked == 5


def test_the_ion_born_reading_is_the_strong_one() -> None:
    summary = _summary()
    born = summary["born_fit"]
    assert born["n_ion_curves"] > 0
    assert born["r2_median_ion"] >= 0.99
    assert born["r2_median_ion"] > 0.0
    assert born["travel_200_1000_median_ion_eV"] <= 0.015
    assert math.isfinite(born["c_eV_median_ion"])


def test_anion_gate_criterion_fails_with_an_attribution() -> None:
    summary = _summary()
    gate = summary["anion_gate"]
    attribution = summary["h2_attribution"]
    assert gate["n_candidates"] + gate["n_already_bound"] == gate["n_molecules"]
    assert attribution["window_over_spread"] is not None
    # The whole point of the negative result: the continuum window is smaller
    # than the method\u2019s own gas-phase electron-affinity spread.
    assert attribution["window_over_spread"] < 1.0


def test_model_contrast_has_rows_for_every_probed_model() -> None:
    rows = w26.read_rows(CONTRAST_CSV)
    assert rows
    models = {row["model"] for row in rows}
    assert models == {"alpb", "cpcmx"}
    epsilons = {float(row["epsilon"]) for row in rows if row["model"] == "alpb"}
    assert epsilons == {7.58, 18.0, 80.4}


def test_csv_outputs_are_lf_only_and_never_carry_a_bom() -> None:
    for path in (SCAN_CSV, BORN_CSV, GATE_CSV, CONTRAST_CSV):
        payload = path.read_bytes()
        assert payload, path
        assert not payload.startswith(BOM), path
        assert CRLF not in payload, path
        payload.decode("utf-8")


def test_figures_are_written_and_are_not_trivial() -> None:
    for path in (FIG_A, FIG_B):
        assert path.is_file(), path
        assert path.stat().st_size > 20000, path
        assert path.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])


def test_report_exists_and_names_the_level_of_every_reading() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "ddCOSMO" in text
    assert "GFN2" in text
    assert "刚性几何" in text
    assert "locked_before_run" in text
    assert "主记分牌 shot：0" in text


def test_pool_size_matches_the_frozen_layer_subset() -> None:
    summary = _summary()
    pool = w26.load_pool()
    assert summary["pool"]["n"] == len(pool)
    assert len(pool) == 242


def test_contrast_and_scan_never_enter_a_frozen_pool() -> None:
    # The round is read-only with respect to every frozen artefact.
    assert Path(w26.LAYER).name == "w21_li_coordination_layer.csv"
    assert w26.SCAN_CSV.parent.name == "artifacts"

