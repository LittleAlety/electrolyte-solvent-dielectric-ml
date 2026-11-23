"""B04 phase-state guards.

Reviewer 1 (B04+B05) found that the pool contains molecules measured below their
melting point. The existing `liquid_window_gate` cannot catch this because it
compares melting point to the *window's lower bound*, not to the measured
temperature -- so it both misses real solids and blocks real liquids.

Guarded:
  1. the audit exists and uses the correct criterion (mp_C < T_C)
  2. known-solid molecules are flagged, not silently treated as liquids
  3. the old gate's false blocks are identified
  4. the pool carries the phase status per row
  5. the finding is propagated to the manifest and the final package
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B04 = REPO_ROOT / "outputs" / "b04"

pytestmark = pytest.mark.skipif(
    not (B04 / "phase_state_audit.json").is_file(),
    reason="phase audit not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _audit() -> dict:
    return json.loads((B04 / "phase_state_audit.json").read_text(encoding="utf-8"))


def test_audit_covers_every_pool_molecule() -> None:
    a = _audit()
    rows = _load(B04 / "phase_state_audit.csv")
    assert len(rows) == a["counts"]["n_pool"] == 22
    assert sum(a["counts"]["by_phase_status"].values()) == 22


def test_criterion_is_mp_vs_measured_temperature() -> None:
    """The whole point: mp_C must be compared to T_C, not to a window bound."""
    a = _audit()
    assert "mp_C < (T_K - 273.15)" in a["question"]
    # And the audit must explain why the existing gate cannot answer it.
    assert "mp_above_T_low" in a["why_the_existing_gate_cannot_answer_this"]

    for r in _load(B04 / "phase_state_audit.csv"):
        if r["mp_C"] == "" or r["T_C"] == "":
            assert r["phase_status"] == "UNKNOWN_NO_MP"
            continue
        mp, t = float(r["mp_C"]), float(r["T_C"])
        expected = ("LIQUID_AT_STATED_T" if mp < t
                    else "SOLID_OR_SUPERCOOLED_AT_STATED_T")
        assert r["phase_status"] == expected, (
            f"{r['name']}: mp={mp} T={t} but status={r['phase_status']}")


def test_known_solids_are_flagged() -> None:
    """Sulfolane (mp 27.8 C) measured at 25 C is a solid/supercooled sample."""
    rows = {r["name"]: r for r in _load(B04 / "phase_state_audit.csv")}
    for name, min_margin in (("sulfolane", 2.0),
                             ("cyclohexanol", 0.5),
                             ("N-(2-hydroxypropyl)-2-hydroxy-1-propanamine", 10.0)):
        match = next((r for k, r in rows.items() if name.lower() in k.lower()), None)
        assert match is not None, f"{name} not in audit"
        assert match["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T", (
            f"{name} should be flagged as solid at its stated T")
        assert float(match["mp_margin_K"]) <= -min_margin


def test_old_gate_false_blocks_are_identified() -> None:
    """DMC (mp 0.5 C) at 25 C is liquid, yet the old gate blocked it."""
    rows = _load(B04 / "phase_state_audit.csv")
    false_blocks = [r for r in rows
                    if r["gate_agreement"] == "GATE_BLOCKED_BUT_ACTUALLY_LIQUID"]
    assert false_blocks, "the old gate's false blocks were not identified"
    names = {r["name"] for r in false_blocks}
    assert any("carbonate" in n.lower() for n in names), (
        "dimethyl carbonate should be a documented false block")
    for r in false_blocks:
        assert float(r["mp_margin_K"]) > 0


def test_pool_carries_phase_status_per_row() -> None:
    pool = _load(B04 / "candidate_pool_v2_draft.csv")
    for r in pool:
        assert r["phase_status"], f"{r['measurement_id']} lacks phase_status"
        assert r["phase_status"] in (
            "LIQUID_AT_STATED_T", "SOLID_OR_SUPERCOOLED_AT_STATED_T",
            "UNKNOWN_NO_MP", "NOT_AUDITED")


def test_manifest_records_the_phase_finding() -> None:
    man = json.loads(
        (B04 / "pool_lineage_manifest.json").read_text(encoding="utf-8"))
    ps = man["pool_character"]["phase_state"]
    assert ps["n_solid_or_supercooled"] >= 1
    assert "液相" in ps["finding"]
    assert ps["rule"], "must state the downstream rule"


def test_final_package_propagates_the_finding() -> None:
    final = REPO_ROOT / "outputs" / "final"
    if not (final / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv").is_file():
        pytest.skip("final package not built")
    claims = _load(final / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv")
    phase_claims = [c for c in claims if "phase_state_audit" in c["evidence_file"]]
    assert phase_claims, "phase finding not propagated to the claim ledger"
    assert any("熔点" in c["claim"] for c in phase_claims)
