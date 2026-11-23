"""B00 regression guards: repository forensics must stay read-only and reproducible.

These tests exist because B00 makes *claims about frozen state*. A forensics
script that silently rewrites bytes, or that reports PASS without actually
re-deriving a digest, would undermine every later gate that trusts it.

Guarded properties:
  1. determinism  -- re-running every B00 script leaves its outputs byte-identical
  2. read-only    -- no frozen J01/J02/J03 artifact changes as a side effect
  3. honesty      -- the hash lock contains no UNCLAIMED/MISSING frozen file that
                     was nevertheless counted as a pass
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B00_DIR = REPO_ROOT / "outputs" / "b00"
SCRIPTS = [
    "build_repo_snapshot.py",
    "verify_frozen_artifacts.py",
    "build_branch_reconciliation.py",
    "audit_paper_package.py",
]

B00_OUTPUTS = [
    "repo_snapshot.json",
    "branch_inventory.csv",
    "w49_commit_reconciliation.json",
    "w49_commit_reconciliation.md",
    "j01_j02_j03_hash_lock.json",
    "v56_r007_freeze_manifest.json",
    "paper_v13_inventory.csv",
    "paper_v13_inventory.json",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "b00" / script)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_b00_script_runs_clean(script: str) -> None:
    proc = _run(script)
    assert proc.returncode == 0, f"{script} failed:\n{proc.stderr[-2000:]}"


def test_b00_outputs_are_byte_reproducible() -> None:
    """A second run must not change a single byte of any B00 output."""
    for script in SCRIPTS:
        assert _run(script).returncode == 0
    first = {name: _sha(B00_DIR / name) for name in B00_OUTPUTS}

    for script in SCRIPTS:
        assert _run(script).returncode == 0
    second = {name: _sha(B00_DIR / name) for name in B00_OUTPUTS}

    drifted = [n for n in B00_OUTPUTS if first[n] != second[n]]
    assert not drifted, f"non-deterministic B00 outputs: {drifted}"


def test_hash_lock_covers_all_frozen_analyses_and_never_fakes_a_pass() -> None:
    """Every frozen file must be receipt-claimed and MATCH, or the lock must fail."""
    lock = json.loads((B00_DIR / "j01_j02_j03_hash_lock.json").read_text(encoding="utf-8"))

    assert set(lock["analyses"]) == {"J01", "J02A", "J02B", "J03"}

    for name, analysis in lock["analyses"].items():
        for check in analysis["checks"]:
            status = check["status"]
            # "UNCLAIMED_BY_RECEIPT" means no generator vouches for the bytes.
            # It must never be silently absorbed into a passing analysis.
            assert status != "UNCLAIMED_BY_RECEIPT", (
                f"{name}/{check['file']} is not covered by any rebuild receipt"
            )
            assert status in {"MATCH", "MISSING"}, (
                f"{name}/{check['file']} unexpected status {status}"
            )

        if analysis["n_fail"] or analysis["n_missing"]:
            assert analysis["status"].startswith("FAIL")
        else:
            assert analysis["status"] == "PASS"


def test_hash_lock_records_recomputed_digests_not_only_claims() -> None:
    """The lock must carry an actual_sha256 for every matched file."""
    lock = json.loads((B00_DIR / "j01_j02_j03_hash_lock.json").read_text(encoding="utf-8"))
    for name, analysis in lock["analyses"].items():
        for check in analysis["checks"]:
            if check["status"] != "MATCH":
                continue
            assert check.get("actual_sha256"), f"{name}/{check['file']} missing actual digest"
            assert check["actual_sha256"] == check["expected_sha256"], (
                f"{name}/{check['file']} MATCH but digests differ"
            )


def test_b00_scripts_have_no_write_paths_into_frozen_tree() -> None:
    """Static guard: B00 scripts must never open a confirm_2027 path for writing."""
    forbidden = ("confirm_2027", "v56_standalone", "candidate_pool_C")
    for script in SCRIPTS:
        src = (REPO_ROOT / "scripts" / "b00" / script).read_text(encoding="utf-8")
        for line in src.splitlines():
            if "write_text" not in line and "open(" not in line:
                continue
            if line.lstrip().startswith("#"):
                continue
            for token in forbidden:
                assert token not in line, (
                    f"{script} appears to write into a frozen path: {line.strip()}"
                )


def test_w49_reconciliation_states_ff_relationship_correctly() -> None:
    """The branch verdict must be derived, not asserted."""
    doc = json.loads(
        (B00_DIR / "w49_commit_reconciliation.json").read_text(encoding="utf-8")
    )
    assert doc["ahead"] >= 0 and doc["behind"] >= 0
    if doc["is_fast_forward_of_origin"]:
        # A fast-forward means nothing on origin is missing locally.
        assert doc["behind"] == 0
        assert doc["merge_base"] == doc["origin_main"]["sha"]


def test_paper_package_is_tag_bounded() -> None:
    """v1.3 is a tag; files added to paper/ afterwards must be marked post-tag."""
    doc = json.loads(
        (B00_DIR / "paper_v13_inventory.json").read_text(encoding="utf-8")
    )
    assert doc["package_identity"]["kind"] == "git_tag"
    for row in doc["tagged_paper_files"]:
        assert row["in_tag_v13"] is True
    for row in doc["worktree_only_paper_files"]:
        assert row["in_tag_v13"] is False
        assert row["package_role"] == "post_v13_worktree_only"
