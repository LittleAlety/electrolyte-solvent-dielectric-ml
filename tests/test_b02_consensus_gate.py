"""B02 regression guards: the four-reviewer consensus gate must not be gameable.

The whole point of replacing per-row human sign-off with four AI reviewers is
that the substitution is *stricter* in the ways that matter. These tests pin the
properties that would silently break that promise:

  1. no majority vote        -- 3 PASS + 1 HOLD must NOT become ACCEPTED
  2. any FAIL blocks         -- 3 PASS + 1 FAIL must NOT become ACCEPTED
  3. missing reviewer blocks -- an absent reviewer must NOT be treated as PASS
  4. AI consensus is not a human signature -- the provenance column must say so
  5. the status machine declares HUMAN_SIGNED unreachable from this pipeline
  6. the queue's critical evidence columns are not silently empty
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADM = REPO_ROOT / "outputs" / "admission_v2"
SCRIPTS = REPO_ROOT / "scripts" / "b02"

REVIEWER_FILES = [f"reviewer_{i}_decisions.csv" for i in range(1, 5)]


def _load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _consensus() -> dict[str, dict]:
    return {r["queue_id"]: r for r in _load_csv(ADM / "consensus_decisions.csv")}


pytestmark = pytest.mark.skipif(
    not (ADM / "consensus_decisions.csv").is_file(),
    reason="B02 consensus not built yet",
)


def test_all_four_reviewer_files_present_and_cover_same_ids() -> None:
    ids = []
    for fname in REVIEWER_FILES:
        p = ADM / fname
        assert p.is_file(), f"missing reviewer file {fname}"
        rows = _load_csv(p)
        assert rows, f"{fname} is empty"
        ids.append({r["queue_id"] for r in rows})

    assert all(s == ids[0] for s in ids), "reviewers did not cover the same record set"


def test_no_majority_vote_three_pass_one_hold_is_not_accepted() -> None:
    for qid, row in _consensus().items():
        votes = [row[f"r{i}_decision"] for i in range(1, 5)]
        n_pass = votes.count("PASS")
        n_hold = votes.count("HOLD")
        n_fail = votes.count("FAIL")

        if n_fail > 0:
            assert row["consensus_status"] == "AI_CONSENSUS_REJECTED", (
                f"{qid}: {votes} has a FAIL but was not REJECTED"
            )
        elif n_hold > 0:
            # This is the exact case a majority vote would wrongly pass.
            assert row["consensus_status"] == "AI_CONSENSUS_HOLD", (
                f"{qid}: {votes} has a HOLD but was not HOLD"
            )
        elif n_pass == 4:
            assert row["consensus_status"] == "AI_CONSENSUS_ACCEPTED", (
                f"{qid}: {votes} is unanimous but was not ACCEPTED"
            )
        elif "MISSING" in votes:
            # Not yet reviewed: must never be counted as a pass.
            assert row["consensus_status"] == "AI_CONSENSUS_INCOMPLETE", (
                f"{qid}: {votes} has missing reviewers but was not INCOMPLETE"
            )
        else:
            pytest.fail(f"{qid}: unexpected vote combination {votes}")


def test_accepted_records_are_exactly_the_unanimous_ones() -> None:
    accepted = {q for q, r in _consensus().items()
                if r["consensus_status"] == "AI_CONSENSUS_ACCEPTED"}
    unanimous = {
        q for q, r in _consensus().items()
        if all(r[f"r{i}_decision"] == "PASS" for i in range(1, 5))
    }
    assert accepted == unanimous, "ACCEPTED set differs from the 4/4 PASS set"


def test_ai_consensus_is_never_labelled_as_human_signed() -> None:
    for qid, row in _consensus().items():
        assert row["provenance_class"] == "AI_CONSENSUS_NOT_HUMAN_SIGNED", (
            f"{qid} carries provenance {row['provenance_class']!r}"
        )
        # No field may assert a bare HUMAN_SIGNED status. The negation token
        # "AI_CONSENSUS_NOT_HUMAN_SIGNED" legitimately contains the substring, so
        # check for the status appearing outside that token.
        for col, val in row.items():
            text = str(val)
            if col == "provenance_class":
                continue
            residual = text.replace("AI_CONSENSUS_NOT_HUMAN_SIGNED", "")
            assert "HUMAN_SIGNED" not in residual, (
                f"{qid}/{col} asserts HUMAN_SIGNED: AI consensus must not "
                f"impersonate a signature"
            )


def test_status_machine_declares_human_signed_unreachable() -> None:
    sm = json.loads((ADM / "admission_status_machine.json").read_text(encoding="utf-8"))
    assert sm["human_signed_reachable_from_ai_pipeline"] is False
    assert "HUMAN_SIGNED" in sm["states"]
    # No transition may lead into HUMAN_SIGNED from this pipeline.
    for t in sm["transitions"]:
        assert t["to"] != "HUMAN_SIGNED", (
            f"a pipeline transition leads to HUMAN_SIGNED: {t}"
        )
    for constraint in sm["hard_constraints"]:
        assert isinstance(constraint, str) and constraint


def test_queue_critical_columns_are_not_all_empty() -> None:
    """Guards the exact defect three reviewers found: a total join failure
    that produced a plausible-looking blank column."""
    rows = _load_csv(ADM / "admission_review_queue.csv")
    assert rows
    for col in ("j04_condition_pair_valid", "j03_verdict",
                "j03_pair_in_single_observation", "temperature_raw_K",
                "dielectric_raw"):
        nonempty = sum(1 for r in rows if (r.get(col) or "").strip())
        assert nonempty > 0, (
            f"queue column {col} is empty on every row — broken join, not a data property"
        )


def test_queue_manifest_records_column_coverage() -> None:
    man = json.loads(
        (ADM / "admission_review_queue_manifest.json").read_text(encoding="utf-8")
    )
    cov = man["column_coverage_pct"]
    assert cov, "manifest must publish per-column coverage"
    # The columns that carry review-critical evidence must be substantially filled.
    assert cov["j04_condition_pair_valid"] > 90.0
    assert cov["j03_pair_in_single_observation"] > 90.0


def test_unreviewed_queue_records_are_not_silently_dropped() -> None:
    """A queue record nobody reviewed must appear as INCOMPLETE, not vanish.

    Regression: the gate used to iterate only the union of the reviewers' record
    sets, so a record added to the queue after review simply disappeared from the
    consensus output -- it escaped the gate by never being looked at.
    """
    queue_ids = {r["queue_id"] for r in _load_csv(ADM / "admission_review_queue.csv")}
    consensus_ids = set(_consensus())
    missing = queue_ids - consensus_ids
    assert not missing, (
        f"{len(missing)} queue records never reached the consensus output: "
        f"{sorted(missing)[:5]}"
    )

    # And each such record must be INCOMPLETE rather than ACCEPTED.
    for qid in queue_ids:
        row = _consensus()[qid]
        if any(row[f"r{i}_decision"] == "MISSING" for i in range(1, 5)):
            assert row["consensus_status"] == "AI_CONSENSUS_INCOMPLETE", (
                f"{qid} has a missing reviewer but status {row['consensus_status']}"
            )


def test_unresolved_source_conflicts_enter_the_review_queue() -> None:
    """Reviewer 4 found gamma-valerolactone was excluded from review, not adjudicated."""
    rows = _load_csv(ADM / "admission_review_queue.csv")
    conflict_rows = [r for r in rows if r["track"] == "UNRESOLVED_SOURCE_CONFLICT"]
    assert conflict_rows, "no unresolved-conflict track in the queue"
    ids = {r["measurement_id"] for r in conflict_rows}
    # Both sides of the 36.1 vs 36.9 conflict must be present.
    assert "EPSV04-R227" in ids and "EPSV04-R248" in ids, (
        f"gamma-valerolactone conflict not fully queued: {sorted(ids)}"
    )
    """Re-running the gate on unchanged inputs must not change the verdicts."""
    before = (ADM / "consensus_decisions.csv").read_bytes()
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_consensus_gate.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    after = (ADM / "consensus_decisions.csv").read_bytes()
    assert before == after, "consensus output is not byte-stable across runs"
