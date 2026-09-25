"""Repository hygiene guards for the two defects that made a clean clone red.

Both failure modes are invisible locally.  ``.gitattributes`` normalises line
endings on commit (``* text=auto eol=lf`` plus an explicit ``*.csv`` rule), so a
worktree holding CRLF bytes and a sha256 pin taken over those very bytes agree
with each other while disagreeing with every fresh checkout.  These tests move
the detection from CI to the moment the drift is introduced.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Committed text is LF by policy.  Binaries are excluded on purpose: they are
# never line-ending-normalised by git, so the rule does not apply to them.
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".csv",
        ".ini",
        ".ipynb",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)

# ``git ls-files`` is the only reliable way to see exactly what a clean clone
# would receive, but the repository metadata has to exist to ask the question.
GIT_METADATA_PRESENT = (REPOSITORY_ROOT / ".git").exists()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        REPOSITORY_ROOT / raw.decode("utf-8")
        for raw in completed.stdout.split(b"\x00")
        if raw
    ]


def _looks_binary(payload: bytes) -> bool:
    return b"\x00" in payload[:8192]


@pytest.mark.skipif(not GIT_METADATA_PRESENT, reason="no git metadata to query")
def test_tracked_text_files_are_checked_out_with_lf_endings() -> None:
    """Critical: a CRLF worktree silently diverges from every clean clone."""

    offenders = []
    checked = 0
    for path in _tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        payload = path.read_bytes()
        if _looks_binary(payload):
            continue
        checked += 1
        if b"\r\n" in payload:
            offenders.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert checked > 0, "the tracked-file scan found nothing to check"
    assert offenders == [], (
        "these tracked text files hold CRLF in the worktree while .gitattributes "
        f"commits them as LF: {offenders}"
    )


def _pinned_pairs(node: object):
    """Yield ``(stem, path_string, digest)`` for ``<stem>_path``/``<stem>_sha256``."""

    if isinstance(node, dict):
        for key, value in node.items():
            if (
                isinstance(value, str)
                and len(value) == 64
                and key.endswith("_sha256")
                and all(character in "0123456789abcdef" for character in value)
            ):
                target = node.get(key[: -len("_sha256")] + "_path")
                if isinstance(target, str):
                    yield key, target, value
            yield from _pinned_pairs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _pinned_pairs(item)


def test_no_sha256_pin_is_satisfied_only_by_crlf_bytes() -> None:
    """Critical: a pin that only matches the CRLF form cannot survive a clone.

    A pin that matches neither form is left alone here: several v0.2-era
    summaries record digests of artefacts whose generating scripts no longer
    exist, and those historical pins are out of scope for this guard.
    """

    summaries = sorted((REPOSITORY_ROOT / "probes").glob("*.json"))
    assert summaries, "no probe summaries found to audit"

    resolved = 0
    offenders = []
    for summary in summaries:
        try:
            payload = json.loads(summary.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        for key, target, digest in _pinned_pairs(payload):
            path = REPOSITORY_ROOT / target
            if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
                continue
            raw = path.read_bytes()
            if _looks_binary(raw):
                continue
            canonical = raw.replace(b"\r\n", b"\n")
            if raw == canonical:
                # LF already: the raw and canonical digests are identical, so
                # no pin can distinguish the two forms.
                resolved += 1
                continue
            resolved += 1
            if _sha256(raw) == digest and _sha256(canonical) != digest:
                offenders.append((summary.name, key, target))

    assert resolved > 0, "no pinned path/digest pairs were resolved"
    assert offenders == [], f"pins that only match the CRLF form: {offenders}"
