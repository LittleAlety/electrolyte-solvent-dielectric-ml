"""B02-CONFLICT regression guards: the GVL adjudication must stay honest.

The gamma-valerolactone conflict is the project's worked example of an unresolved
source conflict. These tests pin the properties that make the adjudication
trustworthy, and they guard against the two failure modes that would make it
worthless:

  1. inventing a winner (averaging, or silently picking one value)
  2. losing the record (dropping it from review instead of adjudicating it)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADM = REPO_ROOT / "outputs" / "admission_v2"
B01 = REPO_ROOT / "outputs" / "b01"

pytestmark = pytest.mark.skipif(
    not (ADM / "gvl_conflict_consensus.csv").is_file(),
    reason="GVL adjudication not built yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_all_four_reviewers_answered() -> None:
    doc = json.loads((ADM / "gvl_conflict_consensus.json").read_text(encoding="utf-8"))
    for label in ("R1", "R2", "R3", "R4"):
        meta = doc["reviewers"][label]
        assert meta["present"], f"{label} did not produce a decision file"
        assert meta["rows"] == 2, f"{label} covered {meta['rows']} rows, expected 2"
    assert doc["structural_problems"] == [], doc["structural_problems"]


def test_no_record_was_accepted() -> None:
    """Neither leg reached 4/4 PASS, so neither may be ACCEPTED."""
    for row in _load(ADM / "gvl_conflict_consensus.csv"):
        assert row["consensus_status"] != "AI_CONSENSUS_ACCEPTED", (
            f"{row['measurement_id']} was accepted despite not being unanimous"
        )
        votes = [row[f"r{i}_decision"] for i in range(1, 5)]
        assert votes.count("PASS") < 4, (
            f"{row['measurement_id']} has 4 PASS but was not accepted")


def test_no_averaging_occurred() -> None:
    """Averaging two non-independent compilations would carry zero provenance."""
    for row in _load(ADM / "gvl_conflict_consensus.csv"):
        resolutions = row["resolution_votes"].lower()
        assert "average" not in resolutions, (
            f"{row['measurement_id']} considered AVERAGE: {row['resolution_votes']}")
        # Each leg must retain its own value, never a blended one.
        authoritative = (row.get("r3_authoritative_value") or "").strip()
        if row["measurement_id"] == "EPSV04-R227":
            assert authoritative == "36.1", (
                f"R227 authoritative value drifted to {authoritative!r}")
        if row["measurement_id"] == "EPSV04-R248":
            assert authoritative == "36.9", (
                f"R248 authoritative value drifted to {authoritative!r}")


def test_both_legs_are_recorded_separately() -> None:
    rows = _load(ADM / "gvl_conflict_consensus.csv")
    ids = {r["measurement_id"] for r in rows}
    assert ids == {"EPSV04-R227", "EPSV04-R248"}, (
        f"expected both legs of the conflict, got {sorted(ids)}")


def test_conflict_premise_is_documented_as_unsound() -> None:
    """Both temperatures are imputed, so 'same T' is an assumption, not a fact."""
    reg = json.loads(
        (B01 / "source_conflict_register.json").read_text(encoding="utf-8"))
    caveat = reg.get("critical_caveat_on_this_conflict")
    assert caveat, "the imputed-temperature caveat is missing from the register"
    assert "not_reported" in caveat["finding"]
    assert "review_table_standard_room_temperature" in caveat["finding"]

    # And the temperature audit must quantify the wider defect.
    timp = json.loads(
        (B01 / "temperature_imputation_audit.json").read_text(encoding="utf-8"))
    assert timp["counts"]["n_imputed"] > 0
    # Imputed rows must not be silently presented as measured.
    assert timp["counts"]["n_imputed_model_ready"] > 0, (
        "expected some imputed rows flagged model_ready; if this is now zero the "
        "upstream v04 may have been corrected -- update the audit")


def test_gvl_rows_are_not_in_any_accepted_pool() -> None:
    """Neither GVL leg may appear in an accepted set while unresolved."""
    consensus = _load(ADM / "consensus_decisions.csv")
    gvl_meas = {"EPSV04-R227", "EPSV04-R248"}
    for row in consensus:
        if row["measurement_id"] in gvl_meas:
            assert row["consensus_status"] != "AI_CONSENSUS_ACCEPTED", (
                f"{row['measurement_id']} accepted in the main consensus while "
                f"its conflict is unresolved")


def test_gvl_consensus_is_deterministic() -> None:
    import subprocess
    import sys

    target = ADM / "gvl_conflict_consensus.csv"
    before = target.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "b02"
                             / "build_gvl_conflict_consensus.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert target.read_bytes() == before, "GVL consensus is not byte-stable"
