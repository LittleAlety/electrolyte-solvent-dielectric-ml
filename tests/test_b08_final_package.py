"""B08 final-package guards: the deliverables must be complete and traceable.

The final package is what a reader will judge the whole project by. Its failure
modes are (a) a claim with no evidence behind it, (b) a completion declaration
that hides what was not done, and (c) a hash manifest that no longer matches.

Guarded:
  1. all six required files exist
  2. every claim points at a file that exists
  3. claims are graded, and exploratory work is never graded as confirmed
  4. the status file records what was NOT done (B06/DFT, E2/E3/E5)
  5. no HUMAN_SIGNED field was written
  6. the hash manifest matches the files on disk
  7. J01/J02/J03 are still frozen
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FINAL = REPO_ROOT / "outputs" / "final"

REQUIRED = [
    "B_FINAL_STATUS.json",
    "B_FINAL_MEASUREMENT_LEDGER.csv",
    "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv",
    "B_FINAL_HASH_MANIFEST.json",
    "B_FINAL_REVIEW.json",
    "B_FINAL_REPORT.md",
]

VALID_GRADES = {
    "CONFIRMED_FROZEN", "FOUR_AGENT_PASS", "FOUR_AGENT_REJECT",
    "EXPLORATORY", "INSUFFICIENT_POWER",
}

pytestmark = pytest.mark.skipif(
    not (FINAL / "B_FINAL_STATUS.json").is_file(),
    reason="final package not built yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _status() -> dict:
    return json.loads((FINAL / "B_FINAL_STATUS.json").read_text(encoding="utf-8"))


def test_all_six_deliverables_exist() -> None:
    for f in REQUIRED:
        p = FINAL / f
        assert p.is_file(), f"missing {f}"
        assert p.stat().st_size > 0, f"{f} is empty"


def test_every_claim_has_existing_evidence() -> None:
    """PLAN B chapter 7: every paper conclusion must map to evidence."""
    claims = _load(FINAL / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv")
    assert claims, "claim ledger is empty"
    for c in claims:
        ev = (c["evidence_file"] or "").strip()
        assert ev, f"{c['claim_id']} has no evidence file"
        assert (REPO_ROOT / ev).is_file(), (
            f"{c['claim_id']} points at a missing file: {ev}")
        assert c["claim"], f"{c['claim_id']} has no claim text"


def test_every_claim_is_graded() -> None:
    claims = _load(FINAL / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv")
    grades = set()
    for c in claims:
        g = c["evidence_grade"]
        assert g in VALID_GRADES, f"{c['claim_id']} has invalid grade {g!r}"
        grades.add(g)
    # A complete package must distinguish confirmed from exploratory.
    assert "CONFIRMED_FROZEN" in grades
    assert "EXPLORATORY" in grades, (
        "no exploratory claims recorded — either none exist or the grading is wrong")


def test_exploratory_claims_are_not_dressed_as_confirmed() -> None:
    """A modelling result on n=22 must never be graded CONFIRMED."""
    claims = _load(FINAL / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv")
    for c in claims:
        ev = c["evidence_file"]
        if "b05" in ev or "b07" in ev:
            assert c["evidence_grade"] in ("EXPLORATORY", "INSUFFICIENT_POWER"), (
                f"{c['claim_id']} comes from a modelling experiment but is graded "
                f"{c['evidence_grade']}")


def test_status_records_what_was_not_done() -> None:
    s = _status()
    b06 = s["work_packages"]["B06"]
    assert b06["gate_open"] is False
    assert b06["status"] == "NOT_STARTED"
    assert b06["dft_compute_hours_used"] == 0
    assert s["compute"]["dft_started"] is False

    b05 = s["work_packages"]["B05"]
    assert set(b05["conditional_not_run"]) == {"E2", "E3", "E5"}


def test_no_human_signed_field_was_written() -> None:
    s = _status()
    assert s["human_signed_fields_written"] == 0
    assert s["ai_consensus_provenance"] == "AI_CONSENSUS_NOT_HUMAN_SIGNED"

    review = json.loads((FINAL / "B_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    assert review["policy"]["human_signed_reachable_from_ai_pipeline"] is False

    # And no artifact in the final package may claim a signature.
    for f in REQUIRED:
        text = (FINAL / f).read_text(encoding="utf-8", errors="replace")
        assert "HUMAN_SIGNED_TRUE" not in text


def test_no_git_actions_were_performed() -> None:
    s = _status()
    assert "none" in s["git_actions_performed"]


def test_hash_manifest_matches_disk() -> None:
    """The manifest is the reproducibility anchor; it must not drift.

    Some tracked artifacts embed `generated_at_utc`, so *any* re-run of a builder
    legitimately changes them. The manifest is therefore only valid at the moment
    of emission. What this test actually guards is the narrower, checkable claim:
    no file may have *disappeared*, and content-bearing CSV files must still
    match, because those do not carry timestamps.
    """
    man = json.loads(
        (FINAL / "B_FINAL_HASH_MANIFEST.json").read_text(encoding="utf-8"))
    files = man["files"]
    assert len(files) > 50, "manifest tracks too few files"

    missing = []
    csv_drift = []
    for rel, meta in files.items():
        p = REPO_ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        # CSV artifacts carry data, not timestamps: they must be byte-stable.
        if rel.endswith(".csv"):
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != meta["sha256"]:
                csv_drift.append(rel)

    missing = [m for m in missing if "B_FINAL_HASH_MANIFEST" not in m]
    assert not missing, f"{len(missing)} tracked files disappeared: {missing[:5]}"
    assert not csv_drift, (
        f"{len(csv_drift)} CSV artifacts drifted (data changed, not just a "
        f"timestamp): {csv_drift[:5]}")


def test_frozen_artifacts_still_verified() -> None:
    man = json.loads(
        (FINAL / "B_FINAL_HASH_MANIFEST.json").read_text(encoding="utf-8"))
    assert man["frozen_evidence_verified_before_emit"] is True
    for name in ("J01", "J02A", "J02B", "J03"):
        assert name in man["j01_j02_j03"]
        assert man["j01_j02_j03"][name]["status"] == "PASS"


def test_measurement_ledger_covers_every_measurement() -> None:
    rows = _load(FINAL / "B_FINAL_MEASUREMENT_LEDGER.csv")
    assert len(rows) == 2065, f"expected 2065 measurements, got {len(rows)}"
    ids = [r["measurement_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate measurement_id"
    for r in rows:
        assert r["source_file_sha256"], (
            f"{r['measurement_id']} lacks a source hash")
        assert r["final_status"], "every row must carry a final status"


def test_report_states_limits() -> None:
    report = (FINAL / "B_FINAL_REPORT.md").read_text(encoding="utf-8")
    assert "不能支持的宣称" in report
    assert "未完成与需人工批准" in report
    assert "有效性边界" in report
    for h in ("H1", "H2", "H3"):
        assert h in report
