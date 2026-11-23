"""B03 regression guards: the A18 gap register must stay faithful to PLAN B.

The register is a *planning* artifact, so its failure mode is not a wrong number
-- it is a wrong story. If it silently reclassified a molecule into a softer tier,
or claimed a room-temperature observation that does not exist, every downstream
backfill decision would be built on a fiction.

Guarded properties:
  1. the 18 molecules and their PLAN B tiers are exactly as the plan states
  2. zero-observation molecules are reported as zero, not omitted
  3. SN (P2) has no room-band observation -- the plan's key constraint
  4. AN (P3) is flagged for non-static frequency
  5. the register adds no measurements (it reads frozen evidence only)
  6. output is byte-reproducible
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EB = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"

# PLAN B B03's tier grouping, restated independently of the implementation.
EXPECTED_TIERS = {
    "P0": {"DMC", "DEC", "SL"},
    "P1": {"DME", "TEGDME", "GBL", "DMSO"},
    "P2": {"SN"},
    "P3": {"AN"},
    "P4": {"EMC", "EC", "PC", "FEC", "VC", "DOL", "EA", "MA", "TMP"},
}


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


pytestmark = pytest.mark.skipif(
    not (EB / "A18_gap_register.csv").is_file(),
    reason="A18 gap register not built yet",
)


def test_all_eighteen_molecules_present() -> None:
    rows = _load(EB / "A18_gap_register.csv")
    assert len(rows) == 18, f"expected 18 molecules, got {len(rows)}"
    ids = {r["a_mol_id"] for r in rows}
    assert len(ids) == 18, "duplicate a_mol_id in register"


def test_plan_b03_tiers_match_the_plan_exactly() -> None:
    rows = _load(EB / "A18_gap_register.csv")
    actual: dict[str, set[str]] = {}
    for r in rows:
        actual.setdefault(r["plan_b03_tier"], set()).add(r["a_name"].upper())
    for tier, names in EXPECTED_TIERS.items():
        assert actual.get(tier) == names, (
            f"tier {tier}: expected {sorted(names)}, got {sorted(actual.get(tier, []))}")


def test_zero_observation_molecules_are_reported_as_zero() -> None:
    """A missing molecule must not be silently dropped or given a fake count.

    Reviewer 4 (B03) found the earlier labelling misleading: "ZERO_OBSERVATION"
    read as "no data exists", when in fact all nine have curated v04 values --
    they simply never passed through the ThermoML observation layer. The label
    must now distinguish the two layers.
    """
    rows = _load(EB / "A18_gap_register.csv")
    zero = {r["a_name"].upper() for r in rows if r["n_observations"] == "0"}
    assert zero == EXPECTED_TIERS["P4"], (
        f"zero-observation set drifted: {sorted(zero)}")
    for r in rows:
        if r["n_observations"] != "0":
            continue
        # Every P4 molecule has a curated v04 value, so the status must say so.
        assert r["evidence_status"] == "NO_THERMOML_OBSERVATION_BUT_V04_VALUE", (
            f"{r['a_name']}: status {r['evidence_status']!r} hides the curated value")
        assert r["v04_curated_value_present"] == "true", (
            f"{r['a_name']}: v04 value not detected")
        assert r["v04_dielectric"], f"{r['a_name']}: missing v04 epsilon"
        assert "ZERO_THERMOML_OBSERVATIONS" in r["blockers"]
        assert "CURATED_VALUE_NOT_IN_OBSERVATION_LAYER" in r["blockers"]


def test_sn_has_no_room_band_observation() -> None:
    """PLAN B P2: SN's 333.15 K data must not be folded into room temperature."""
    rows = _load(EB / "A18_gap_register.csv")
    sn = next(r for r in rows if r["a_name"].upper() == "SN")
    assert sn["n_observations"] != "0", "SN should have high-temperature observations"
    assert sn["n_room_band_observations"] == "0", (
        "SN unexpectedly has a room-band observation; verify before trusting")
    assert "NO_ROOM_BAND_OBSERVATION" in sn["blockers"]
    assert sn["evidence_status"] == "OBSERVED_NOT_ROOM_BAND"


def test_an_is_flagged_for_non_static_frequency() -> None:
    """PLAN B P3: AN's 0.01/1 MHz evidence cannot substitute for static 0 Hz."""
    rows = _load(EB / "A18_gap_register.csv")
    an = next(r for r in rows if r["a_name"].upper() == "AN")
    assert an["frequency_status"] == "RF_ONLY", (
        f"AN frequency_status drifted to {an['frequency_status']!r}")
    assert "NON_STATIC_FREQUENCY_PRESENT" in an["blockers"]


def test_register_adds_no_measurements() -> None:
    """The register is a gap analysis, not an evidence source."""
    doc = json.loads((EB / "A18_gap_register.json").read_text(encoding="utf-8"))
    assert "不新增任何测量" in doc["declaration"]
    # Every row's counts must be derivable from the frozen ledger.
    ledger = _load(REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
                   / "measurement_ledger_v1.csv")
    by_mol: dict[str, int] = {}
    for m in ledger:
        aid = (m.get("a_mol_id") or "").strip()
        if aid and aid.lower() != "not_evaluated":
            by_mol[aid] = by_mol.get(aid, 0) + 1
    for r in _load(EB / "A18_gap_register.csv"):
        expected = by_mol.get(r["a_mol_id"], 0)
        assert int(r["n_observations"]) == expected, (
            f"{r['a_mol_id']}: register says {r['n_observations']} observations, "
            f"ledger has {expected}")


def test_register_is_byte_reproducible() -> None:
    target = EB / "A18_gap_register.csv"
    before = target.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "b03"
                             / "build_a18_gap_register.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert target.read_bytes() == before, "A18 register is not byte-stable"
