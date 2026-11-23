"""B03 consensus guards: the four-agent split must be recorded, not smoothed over.

The EA/MA review split 2-2: two reviewers passed the VALUES, two held on
PROVENANCE. That is a real scientific distinction, not a tie to be broken by
majority. These tests pin the honesty of the outcome.

Guarded properties:
  1. no record reached 4/4 PASS, so none may be ACCEPTED
  2. the split is explained by axis (values vs provenance), not hidden
  3. the circularity finding is recorded
  4. the shared-citation finding is recorded
  5. neither molecule may enter B04
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EB = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


pytestmark = pytest.mark.skipif(
    not (EB / "b03_consensus_decisions.csv").is_file(),
    reason="B03 consensus not built yet",
)


def test_no_record_was_accepted() -> None:
    for row in _load(EB / "b03_consensus_decisions.csv"):
        assert row["consensus_status"] != "AI_CONSENSUS_ACCEPTED", (
            f"{row['a_name']} accepted without 4/4 PASS")
        votes = [row[f"r{i}_decision"] for i in range(1, 5)]
        assert votes.count("PASS") < 4


def test_all_four_reviewers_answered() -> None:
    doc = json.loads((EB / "b03_consensus.json").read_text(encoding="utf-8"))
    for label in ("R1", "R2", "R3", "R4"):
        meta = doc["reviewers"][label]
        assert meta["present"], f"{label} missing"
        assert meta["per_molecule_rows"] == 2, (
            f"{label} covered {meta['per_molecule_rows']} molecules, expected 2")
    assert doc["structural_problems"] == [], doc["structural_problems"]


def test_split_is_explained_by_axis_not_hidden() -> None:
    """The 2-2 split must be described as values-vs-provenance."""
    doc = json.loads((EB / "b03_consensus.json").read_text(encoding="utf-8"))
    split = doc["split_analysis"]
    assert "溯源" in split["finding"] or "provenance" in split["finding"].lower()
    assert "4/4" in split["why_hold_not_pass"]
    assert "FAIL" in split["why_not_reject"]

    for row in _load(EB / "b03_consensus_decisions.csv"):
        # The value axis and the provenance axis must both be visible per record.
        assert row["value_reproducible"] in ("true", "false")
        assert row["source_is_primary"] in ("true", "false")


def test_circularity_is_recorded() -> None:
    """v04's value IS the NBS514 transcription; 'agrees' is not corroboration."""
    doc = json.loads((EB / "b03_consensus.json").read_text(encoding="utf-8"))
    agreed = " ".join(doc["agreed_facts"])
    assert "source_record_id" in agreed, (
        "the circularity fact is not recorded")
    assert "转录完整性" in agreed or "transcription" in agreed.lower()

    # And the verifier's own JSON must warn about it.
    ver = json.loads((EB / "nbs514_verification.json").read_text(encoding="utf-8"))
    assert "circularity_warning" in ver
    assert "SINGLE_SOURCE" in ver["circularity_warning"]["consequence"]


def test_shared_primary_citation_is_recorded() -> None:
    doc = json.loads((EB / "b03_consensus.json").read_text(encoding="utf-8"))
    agreed = " ".join(doc["agreed_facts"])
    assert "63" in agreed, "the shared reference 63 is not recorded"
    assert "Williams" in agreed or "Krchma" in agreed

    constraints = " ".join(doc["hard_constraints"])
    assert "独立来源" in constraints, (
        "must forbid treating EA/MA as two independent sources")


def test_neither_molecule_may_enter_b04() -> None:
    for row in _load(EB / "b03_consensus_decisions.csv"):
        assert row["may_enter_b04"] == "false", (
            f"{row['a_name']} is allowed into B04 despite not being accepted")
        assert row["b04_blocking_reason"]


def test_zero_new_observations_is_an_agreed_fact() -> None:
    doc = json.loads((EB / "b03_consensus.json").read_text(encoding="utf-8"))
    agreed = " ".join(doc["agreed_facts"])
    assert "未新增观测" in agreed or "0 new" in agreed.lower(), (
        "the 'no new observations' fact is missing from the consensus")
