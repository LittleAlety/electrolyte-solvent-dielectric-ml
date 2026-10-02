# Guards for the Week 25-7 post-hoc arm: direct learning versus shift learning.
#
# The arm is deliberately built with two feature sets, and the guards pin the
# distinction that makes it readable at all:
#
#   * the x0 pair is a CONTROL -- that feature set already contains the free level,
#     so the two parameterisations carry nearly the same information and the effect
#     must be ~0.  If this pair ever moves, the arm is broken, not "improved".
#   * the off_free pair is the EVIDENCE -- the free level enters only through the
#     shift target, so the paired difference is a real change of parameterisation.
#
# It also pins the magnitude caveat: on the reduction axis the ranking improves
# while the original-scale R2 collapses, which is the repository's recurring
# "rank learned, magnitude not" pattern rather than a clean win.

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w25_7_delta_learning as w257

CSV_OUT = ROOT / "probes" / "artifacts" / "w25_7_delta_learning.csv"
FIG = ROOT / "probes" / "artifacts" / "w25_7_delta_learning.png"
REPORT = ROOT / "reports" / "w25_7_delta_learning.md"
SUMMARY = ROOT / "probes" / "w25_7_delta_learning_summary.json"
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _columns(name: str):
    return dict((key, value) for key, value, _ in w257.FEATURE_SETS)[name]


def test_the_arm_is_post_hoc_and_declares_zero_scoreboard_shots():
    source = Path(w257.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "requests" not in source and "urllib" not in source
    assert w257.POST_HOC is True
    assert w257.NEW_SHOT is False
    assert w257.SCOREBOARD_SHOTS == 0
    payload = _summary()
    assert payload["post_hoc"] is True
    assert payload["new_shot"] is False
    assert payload["scoreboard_shots"] == 0


def test_the_frozen_week25_pre_registration_is_not_touched_by_this_arm():
    prereg = ROOT / "probes" / "w25_v6_alignment_prereg.json"
    payload = json.loads(prereg.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    assert "W25-7" not in json.dumps(payload), "the post-hoc arm must not appear in the prereg"
    assert _summary()["task"] == "w25_7_delta_learning"


def test_the_pool_and_the_two_feature_sets_are_what_the_report_claims():
    payload = _summary()
    assert payload["n_pool"] == 237
    assert set(payload["feature_sets"]) == {"x0", "off_free"}
    assert payload["feature_sets"]["off_free"] == ["formal_charge", "total_energy_free_hartree"]
    assert set(payload["readings"]) == {"ox", "red"}
    for axis in ("ox", "red"):
        assert set(payload["readings"][axis]) == {"x0", "off_free"}


def test_the_x0_pair_is_the_degenerate_control():
    readings = _summary()["readings"]
    for axis in ("ox", "red"):
        entry = readings[axis]["x0"]["random"]
        assert abs(entry["delta_tau_b_mean"]) < 0.02, axis
        width = entry["delta_tau_b_ci"][1] - entry["delta_tau_b_ci"][0]
        assert width < 0.03, axis
        assert entry["delta_tau_b_max"] - entry["delta_tau_b_min"] < 0.06, axis
        assert abs(entry["delta_r2_mean"]) < 0.10, axis
    control = readings["ox"]["x0"]["random"]
    assert control["delta_tau_b_ci"][0] < 0.0 < control["delta_tau_b_ci"][1]


def test_the_off_free_pair_is_the_informative_evidence():
    readings = _summary()["readings"]
    oxidation = readings["ox"]["off_free"]["random"]
    assert oxidation["delta_tau_b_mean"] >= 0.20
    assert oxidation["delta_tau_b_ci"][0] > 0.0
    assert oxidation["positive_repeats"] == oxidation["repeats"] == 10
    assert oxidation["delta_r2_mean"] > 0.50
    reduction = readings["red"]["off_free"]["random"]
    assert reduction["delta_tau_b_mean"] > 0.05
    assert reduction["delta_tau_b_ci"][0] > 0.0
    assert reduction["positive_repeats"] == reduction["repeats"] == 10
    # The caveat that must travel with the win: on the reduction axis the ranking
    # improves while the original-scale R2 gets worse, not better.
    assert reduction["delta_r2_mean"] < 0.0


def test_the_leave_one_family_out_reading_is_mixed_not_universal():
    readings = _summary()["readings"]
    for axis in ("ox", "red"):
        for name in ("x0", "off_free"):
            entry = readings[axis][name]["lofo"]
            # anion_halide holds 2 compounds, so tau_b (undefined below n = 3) drops
            # out of the mean while still being listed with a null reading.
            assert entry["families_total"] == 5
            assert entry["families"] == 4
            assert 0 <= entry["positive_families"] <= entry["families"]
            assert entry["per_family"]["anion_halide"] is None
            assert set(entry["per_family"]) == {
                "alkene_pi",
                "anion_halide",
                "aromatic_pi",
                "lone_pair",
                "no_motif",
            }
    oxidation = readings["ox"]["off_free"]["lofo"]
    assert oxidation["delta_tau_b_mean"] > 0.30
    assert oxidation["positive_families"] == oxidation["families"] == 4
    reduction = readings["red"]["off_free"]["lofo"]
    assert 0 < reduction["positive_families"] < reduction["families"]


def test_a_stored_row_recomputes_exactly():
    pool = w257.load_pool()
    rows = w257.w25.read_rows(CSV_OUT)
    seed = 3
    row = next(
        item
        for item in rows
        if item["mode"] == "random"
        and item["axis"] == "ox"
        and item["feature_set"] == "off_free"
        and item["seed"] == str(seed)
    )
    folds = w257.kfold_indices(len(pool), w257.N_FOLDS, random.Random(20261000 + seed))
    for shape, key in (("direct", "direct_tau_b"), ("shift", "shift_tau_b")):
        result = w257.cross_validate(pool, "ox", folds, shape, _columns("off_free"))
        assert abs(result["tau_b"] - float(row[key])) < 1e-9, shape
    stored = w257.w25.read_rows(CSV_OUT)
    assert len(stored) == 2 * 2 * (10 + 5)


def test_a_lofo_row_recomputes_on_the_held_out_family_only():
    # This is the guard for the instrument defect this arm was built through: an
    # earlier version scored tau_b over the whole prediction vector (np.empty, so
    # undefined entries) instead of the held-out family alone.
    pool = w257.load_pool()
    rows = w257.w25.read_rows(CSV_OUT)
    row = next(
        item
        for item in rows
        if item["mode"] == "lofo"
        and item["axis"] == "ox"
        and item["feature_set"] == "off_free"
        and item["family"] == "aromatic_pi"
    )
    test_idx = [i for i, record in enumerate(pool) if record["family"] == "aromatic_pi"]
    assert len(test_idx) == 21
    result = w257.cross_validate(pool, "ox", [test_idx], "direct", _columns("off_free"))
    assert result["n_scored"] == 21
    assert abs(result["tau_b"] - float(row["direct_tau_b"])) < 1e-9
    assert abs(result["mae"] - float(row["direct_mae"])) < 1e-9


def test_every_delivered_file_matches_the_stamp_and_is_lf_utf8():
    stamped = _summary()["artifacts_sha256"]
    assert len(stamped) == 3
    for relative, digest in stamped.items():
        path = ROOT / relative.replace(chr(92), "/")
        assert path.is_file(), relative
        assert _digest(path) == digest, relative
    for path in (CSV_OUT, SUMMARY, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(BOM), path.name
        raw.decode("utf-8")
        assert CRLF not in raw, path.name


def test_figure_is_non_trivial_and_the_report_separates_control_from_evidence():
    assert FIG.stat().st_size > 40_000
    report = REPORT.read_text(encoding="utf-8")
    assert "控制组" in report
    assert "未预注册" in report
    assert "off_free" in report and "x0" in report
