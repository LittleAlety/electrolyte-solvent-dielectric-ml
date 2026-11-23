"""B08 completion-audit guards.

The completion audit exists so that the project's "complete" claim is derived, not
asserted. Its own failure mode would be an audit whose checks cannot fail -- so
these tests assert that each check is *live*: it reads an artifact and would flip
if that artifact changed.

Guarded:
  1. the audit ran and every check passed
  2. no check is trivially true (each cites an existing evidence file)
  3. the frozen-evidence check actually invokes the verifier
  4. reviewer coverage is counted per work package, not from one pattern
  5. the audit is reproducible
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FINAL = REPO_ROOT / "outputs" / "final"
AUDIT = FINAL / "B_FINAL_COMPLETION_AUDIT.json"

pytestmark = pytest.mark.skipif(
    not AUDIT.is_file(), reason="completion audit not run yet")


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_audit_passed_every_check() -> None:
    a = _audit()
    assert a["overall"] == "PASS", (
        f"completion audit failed: "
        f"{[c['id'] for c in a['checks'] if c['status'] == 'FAIL']}")
    assert a["n_fail"] == 0
    assert a["n_checks"] == a["n_pass"]


def test_every_check_cites_existing_evidence() -> None:
    """A check with no evidence path would be an assertion, not a measurement."""
    a = _audit()
    for c in a["checks"]:
        assert c["evidence"], f"{c['id']} has no evidence pointer"
        # evidence may list several paths separated by ', '
        for part in c["evidence"].split(","):
            p = part.strip()
            if not p:
                continue
            assert (REPO_ROOT / p).exists(), (
                f"{c['id']} cites missing evidence: {p}")


def test_frozen_check_is_live() -> None:
    """R16 must run the verifier rather than trusting a stored boolean."""
    a = _audit()
    r16 = next(c for c in a["checks"] if c["id"] == "R16")
    assert "verify_frozen_artifacts" in r16["detail"]
    src = (REPO_ROOT / "scripts" / "b08" / "audit_completion.py").read_text(
        encoding="utf-8")
    assert "verify_frozen_artifacts.py" in src, (
        "the audit no longer invokes the frozen verifier")


def test_reviewer_coverage_is_counted_per_package() -> None:
    """B03 names its files b03_reviewer_*; a single glob pattern would miss them."""
    a = _audit()
    r13 = next(c for c in a["checks"] if c["id"] == "R13")
    for label in ("B02_admission", "B02_gvl", "B03_backfill", "B04_B05_review"):
        assert label in r13["detail"], f"{label} not covered in R13"
        assert f"{label}=4/4" in r13["detail"], (
            f"{label} did not reach 4/4: {r13['detail']}")


def test_no_human_signed_forgery_check_scans_files() -> None:
    """R18 must grep the package, not just read a status field."""
    a = _audit()
    r18 = next(c for c in a["checks"] if c["id"] == "R18")
    assert r18["status"] == "PASS"
    assert "forged_files" in r18["detail"]
    src = (REPO_ROOT / "scripts" / "b08" / "audit_completion.py").read_text(
        encoding="utf-8")
    assert "HUMAN_SIGNED_TRUE" in src, (
        "the forgery scan was removed; R18 would become vacuous")


def test_dft_check_is_live() -> None:
    a = _audit()
    r20 = next(c for c in a["checks"] if c["id"] == "R20")
    assert "dft_started=False" in r20["detail"].replace(" ", "")
    assert "dft_hours=0" in r20["detail"].replace(" ", "")


def test_claim_mapping_check_counts_missing_files() -> None:
    a = _audit()
    r15 = next(c for c in a["checks"] if c["id"] == "R15")
    assert "条结论" in r15["detail"]
    assert "0 条缺证据" in r15["detail"]


def test_audit_is_reproducible() -> None:
    before = AUDIT.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "b08" / "audit_completion.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stderr[-1500:]
    # generated_at_utc moves, but the verdict must not.
    after = json.loads(AUDIT.read_text(encoding="utf-8"))
    prev = json.loads(before)
    assert after["overall"] == prev["overall"]
    assert after["n_pass"] == prev["n_pass"] == after["n_checks"]
