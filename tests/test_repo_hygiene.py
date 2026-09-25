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
from pathlib import Path, PurePosixPath

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

LINT_ROOTS = frozenset({"notebooks", "probes", "scripts", "src", "tests"})
LINT_SUFFIXES = frozenset({".ipynb", ".py", ".pyi"})


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


def _index_modes() -> dict[str, str]:
    """Map every tracked path to the file mode git would check out."""

    completed = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    modes: dict[str, str] = {}
    for entry in completed.stdout.split(b"\x00"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        modes[raw_path.decode("utf-8")] = meta.split()[0].decode("ascii")
    return modes


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


def test_executable_shebang_guard_uses_lint_scope_and_index_blobs() -> None:
    """The guard must mirror ruff's lint scope and trust index blobs.

    Ruff checks only Python-ish files under the five project roots.  A shell
    hook elsewhere may legitimately have a shebang and mode 100644.  The guard
    must also read the blob that git would check out, not the worktree, or a
    dirty local edit can hide a clean-checkout EXE001.
    """

    entries = {
        "scripts/demo_hook.sh": ("100644", "a" * 40),
        "scripts/demo.py": ("100644", "b" * 40),
        "scripts/verify_week0.py": ("100755", "c" * 40),
    }
    blob_heads = {
        "a" * 40: b"#!/bin/sh\n",
        "b" * 40: b"#!/usr/bin/env python\n",
        "c" * 40: b"print('ok')\n",
    }
    assert _executable_bit_findings(entries, blob_heads) == (
        ["scripts/demo.py"],
        ["scripts/verify_week0.py"],
    )


def _is_lint_path(relative: str) -> bool:
    """Return whether CI's ruff invocation covers this repository path."""

    path = PurePosixPath(relative)
    return (
        bool(path.parts)
        and path.parts[0] in LINT_ROOTS
        and path.suffix.lower() in LINT_SUFFIXES
    )


def _index_entries() -> dict[str, tuple[str, str]]:
    """Map each tracked path to ``(mode, object-id)`` from the git index."""

    completed = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    entries: dict[str, tuple[str, str]] = {}
    for entry in completed.stdout.split(b"\x00"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, oid = meta.split()[:2]
        entries[raw_path.decode("utf-8")] = (
            mode.decode("ascii"),
            oid.decode("ascii"),
        )
    return entries


def _blob_heads(entries: dict[str, tuple[str, str]]) -> dict[str, bytes]:
    """Read the first 256 bytes of each distinct lint-scope index blob."""

    oids = sorted(
        oid
        for relative, (_, oid) in entries.items()
        if _is_lint_path(relative)
    )
    if not oids:
        return {}
    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPOSITORY_ROOT,
        check=True,
        input=b"".join(oid.encode("ascii") + b"\n" for oid in oids),
        capture_output=True,
    )
    data = completed.stdout
    heads: dict[str, bytes] = {}
    offset = 0
    for oid in oids:
        header_end = data.index(b"\n", offset)
        header = data[offset:header_end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise AssertionError(f"unexpected cat-file header for {oid}: {header!r}")
        size = int(header[2])
        content_start = header_end + 1
        content_end = content_start + size
        if content_end > len(data):
            raise AssertionError(f"truncated cat-file blob for {oid}")
        heads[oid] = data[content_start:content_start + 256]
        offset = content_end + 1
    return heads


def _executable_bit_findings(
    entries: dict[str, tuple[str, str]],
    blob_heads: dict[str, bytes],
) -> tuple[list[str], list[str]]:
    """Return EXE001-like and EXE002-like findings for the CI lint scope."""

    not_executable = []
    executable_without_shebang = []
    for relative, (mode, oid) in sorted(entries.items()):
        if not _is_lint_path(relative):
            continue
        has_shebang = blob_heads.get(oid, b"").startswith(b"#!")
        is_executable = mode == "100755"
        if has_shebang and not is_executable:
            not_executable.append(relative)
        if is_executable and not has_shebang:
            executable_without_shebang.append(relative)
    return not_executable, executable_without_shebang


@pytest.mark.skipif(not GIT_METADATA_PRESENT, reason="no git metadata to query")
def test_executable_bit_agrees_with_the_shebang() -> None:
    """Critical: ruff EXE001/EXE002 only fire on a posix checkout.

    EXE001 is "shebang present but the file is not executable" and EXE002 is
    the mirror image.  Both read the filesystem mode bit, which Windows cannot
    express, so the same tree lints clean here and fails on the Linux runner.
    The git index mode is the portable source of truth for what CI checks out.
    """

    entries = _index_entries()
    not_executable, executable_without_shebang = _executable_bit_findings(
        entries,
        _blob_heads(entries),
    )

    assert not_executable == [], (
        "ruff EXE001 on a posix runner: these files carry a shebang but the "
        f"index mode is 100644: {not_executable}"
    )
    assert executable_without_shebang == [], (
        "ruff EXE002 on a posix runner: these files are executable but carry "
        f"no shebang: {executable_without_shebang}"
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
