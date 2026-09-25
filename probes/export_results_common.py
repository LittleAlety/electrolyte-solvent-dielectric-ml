"""Shared helpers for the week-by-week result exports."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT.parent / "成果输出"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_sha256s(directory: Path) -> None:
    files = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(directory).as_posix()}" for path in files]
    # Pin the newline so the manifest itself is byte-stable across platforms.
    with (directory / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def copy_artifacts(
    source_root: Path,
    week_root: Path,
    artifacts: Sequence[tuple[str, str]],
) -> list[str]:
    written: list[str] = []
    for source, destination in artifacts:
        source_path = source_root / source
        if not source_path.is_file():
            raise FileNotFoundError(f"missing artifact: {source_path}")
        destination_path = week_root / destination
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        written.append(destination_path.relative_to(week_root).as_posix())
    return written


def run_verifiers(source_root: Path, verifiers: Sequence[str]) -> dict[str, object]:
    """Run each verifier script and record its exit status and JSON body.

    The entry may carry arguments (for example ``build_paper_full_draft.py
    --check``), so it is split the way a shell would split it.
    """

    checks: list[dict[str, object]] = []
    for relative in verifiers:
        completed = subprocess.run(
            [sys.executable, *shlex.split(relative)],
            cwd=source_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        payload: object | None = None
        stdout = (completed.stdout or "").strip()
        if stdout.startswith("{"):
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None
        checks.append(
            {
                "command": f"{relative}",
                "exit_code": completed.returncode,
                "passed": completed.returncode == 0,
                "report": payload,
            }
        )
    return {"passed": all(check["passed"] for check in checks), "checks": checks}
