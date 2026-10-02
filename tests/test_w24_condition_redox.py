# Guards for the Week 24 Axis B conditional-state arm (C_1 redox + C_2 microsolvation).
#
# These tests exist because two defects were caught only by running the arm:
#
# 1. the shared numeric formatter raised ValueError for every non-None value, so the
#    arm would have died the first time it tried to write a layer row;
# 2. the first scheduler used an ordered map, so the slowest molecule (a 107-atom
#    C_2 dimer of an ionic liquid) blocked the progress stream and no partial evidence
#    reached disk for over half an hour.
#
# Both are pinned here, together with the discipline invariants: the pre-registration
# is locked, and the frozen readings are untouched.

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w24_condition_redox as w24
import w23_redox_dscf as w23
import w21_li_coordination as w21

PREREG = ROOT / "probes/w24_condition_redox_prereg.json"
SUMMARY = ROOT / "probes/w24_condition_redox_summary.json"
LAYER = ROOT / "data/processed/w24_condition_redox_layer.csv"
CHECKPOINT = ROOT / "probes/artifacts/w24_condition_redox_records.jsonl"

FROZEN_FORMATTER_CASES = ((1.2345, 4, "1.2345"), (0.0, 6, "0.000000"),
                          (-2.5, 2, "-2.50"), (1234, 0, "1234"))

LIVE = LAYER.is_file() and SUMMARY.is_file()


def test_formatter_regression():
    # The pre-run version of this function used the format string "%.%df", which
    # raises "unsupported format character" for every input.  It must never come back.
    for value, digits, expected in FROZEN_FORMATTER_CASES:
        assert w24.fmt(value, digits) == expected
    assert w24.fmt(None) == ""
    assert w24.fmt("text") == "text"
    source = (ROOT / "probes/w24_condition_redox.py").read_text(encoding="utf-8")
    assert "%.%df" not in source


def test_preregistration_is_locked_and_hashed():
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    assert digest == "cb090950b55f1da1fdfcaa17037c804df358bdc15cb1a4a57b43ab122abb8b0d"
    assert payload["amendment_before_run"]["reason"]


def test_arm_grid_is_the_preregistered_one():
    assert len(w24.MEDIA) == 4
    assert len(w24.STATES) == 3
    assert len(w24.COMPLEXES) == 2
    assert len(w24.ARM_KEYS) == 24
    charges = {arm: None for arm in w24.ARM_KEYS}
    for complex_key, _ligands in w24.COMPLEXES:
        for medium, _solvent, _eps in w24.MEDIA:
            for state, delta_q, _unpaired in w24.STATES:
                charges[complex_key + "_" + medium + "_" + state] = delta_q
    assert set(charges) == set(w24.ARM_KEYS)
    assert sorted(set(charges.values())) == [-1, 0, 1]


def test_dispatch_puts_the_long_poles_first():
    rows = [{"canonical_smiles": "CCO"},
            {"canonical_smiles": "CCCCCCCCCCCCCCCCCC(=O)O"}]
    assert w24.dispatch_order(rows) == [1, 0]
    assert w24.estimated_cost("COC(=O)OC") == 6
    assert w24.estimated_cost("not-a-smiles") == 0


def test_checkpoint_round_trip():
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "records.jsonl"
        record = {"row_index": 7, "name": "x", "arms": {"a": {"status": "ok"}}}
        w24.append_checkpoint(path, record)
        w24.append_checkpoint(path, {"row_index": 8, "name": "y", "arms": {}})
        loaded = w24.load_checkpoint(path)
        assert sorted(loaded) == [7, 8]
        assert loaded[7]["arms"]["a"]["status"] == "ok"
        assert w24.load_checkpoint(Path(scratch) / "missing.jsonl") == {}


def test_open_shell_states_are_not_optimised_by_the_closed_shell_builder():
    from electrolyte_ml.xtb_runner import xtb_open_shell_arguments
    arguments = xtb_open_shell_arguments("x.xyz", formal_charge=1, unpaired_electrons=1)
    assert "--uhf" in arguments
    assert "--chrg" in arguments


def test_frozen_readings_are_not_restated_here():
    # The arm must never touch the epsilon scoreboard.  This is a cheap tripwire:
    # the probe must not contain any of the frozen readings as a literal.
    source = (ROOT / "probes/w24_condition_redox.py").read_text(encoding="utf-8")
    for frozen in ("0.4091179943351143", "0.4766400383507876",
                   "0.5861142332208197", "0.6216672295270079"):
        assert frozen not in source


def test_the_probe_writes_only_its_own_artifacts():
    # Read-only access to the Week 21 C_1 layer is expected; writing to a frozen
    # red line is not.  None of these filenames may appear in the probe at all.
    source = (ROOT / "probes/w24_condition_redox.py").read_text(encoding="utf-8")
    for frozen in ("dielectric_v03.csv", "viscosity_v01.csv",
                   "dielectric_observations_v11plus.csv",
                   "l3_backvalidation_prereg.json",
                   "l3_stage1_pilot_pool.csv",
                   "dielectric_r2_levers_prereg.json"):
        assert frozen not in source, frozen


def test_live_layer_matches_the_pre_registered_grid():
    if not LIVE:
        return
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    pool = summary["pool"]
    assert pool["n_compounds"] == 246
    assert pool["matches_prereg"] is True
    # Every planned cell is accounted for exactly once: executed, or registered as a
    # failure with a reason.  The first version of this test demanded failed_arms == 0,
    # which the pre-registration never promised -- the 528 no_motif cells and the SCF
    # failures are declared limits of the arm, not silent drops.
    assert pool["actual_runs"] + pool["failed_arms"] == 246 * 24
    rows = w21.read_rows(LAYER)
    statuses = {row[arm + "_status"] for row in rows for arm in w24.ARM_KEYS}
    assert statuses <= {"ok", "no_motif", "xtb_failed", "exception", "not_computed"}


def test_live_h7_regression_anchor():
    if not LIVE:
        return
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    anchor = summary["anchors"]
    assert anchor["max_abs_delta_hartree"] <= 1e-9
    assert anchor["verdict"] == "成立"


def test_live_negative_results_are_recorded_not_hidden():
    if not LIVE:
        return
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    verdicts = summary["hypotheses"]
    assert set(verdicts) == {"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"}
    for key, entry in verdicts.items():
        assert entry["verdict"] in ("成立", "判否"), key


# --------------------------------------------------------------------------- #
# Lithium population plumbing
#
# The first pass emptied all 24 Li columns and scored H2 on zero pairs, because the
# w23 wrapper rebuilt its payload without the diagnostics that w21 had just computed.
# These pin the wiring; test_live_lithium_columns_are_populated pins the result.
# --------------------------------------------------------------------------- #

def test_the_w23_wrapper_exposes_the_lithium_diagnostics(monkeypatch):
    monkeypatch.setattr(w23.w21, "parse_arm", lambda result: {
        "status": "ok", "homo_eV": -1.0, "lumo_eV": 0.0, "gap_eV": 1.0,
        "total_energy_hartree": -10.0, "xtb_version": "test", "error": "",
        "li_mulliken_q": 0.3456, "li_min_dist_A": 2.0, "li_nearest_atom": "O"})
    parsed = w23.parse_arm({"returncode": 0, "stdout": "", "seconds": 0.0})
    assert parsed["li_mulliken_q"] == 0.3456
    assert parsed["li_min_dist_A"] == 2.0
    assert parsed["li_nearest_atom"] == "O"


def test_live_lithium_columns_are_populated():
    if not LIVE:
        return
    rows = w21.read_rows(LAYER)
    if len(rows) < 5:
        return
    cells = 0
    filled = 0
    for row in rows:
        for arm in w24.ARM_KEYS:
            if row[arm + "_status"] != "ok":
                continue
            cells += 1
            if (row[arm + "_li_q"] or "").strip() not in ("", "None", "nan"):
                filled += 1
    assert cells, "no finished arm in the live layer"
    assert filled == cells
