"""Deterministic SHA256 manifests for exported artifact directories."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

MANIFEST_NAME = "SHA256SUMS"
MANIFEST_LINE = re.compile(r"^(?P<sha256>[0-9a-f]{64})  (?P<path>.+)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exported_files(output_dir: Path) -> list[Path]:
    manifest_path = (output_dir / MANIFEST_NAME).resolve()
    files = [
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.resolve() != manifest_path
    ]
    return sorted(files, key=lambda path: path.relative_to(output_dir).as_posix())


def build_export_manifest(output_dir: Path) -> str:
    output_dir = Path(output_dir)
    lines = [
        f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in _exported_files(output_dir)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def write_export_manifest(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_NAME
    manifest_content = build_export_manifest(output_dir)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_dir,
        prefix=f".{MANIFEST_NAME}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(manifest_content)
        os.replace(temporary_path, manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return manifest_path


def verify_export_manifest(output_dir: Path) -> list[str]:
    output_dir = Path(output_dir)
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"missing manifest: {manifest_path}"]
    entries: dict[str, str] = {}
    errors: list[str] = []
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        match = MANIFEST_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed manifest line {line_number}")
            continue
        relative_path = match.group("path")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"unsafe manifest path: {relative_path}")
            continue
        if relative_path in entries:
            errors.append(f"duplicate manifest path: {relative_path}")
            continue
        entries[relative_path] = match.group("sha256")

    actual_paths = {
        path.relative_to(output_dir).as_posix() for path in _exported_files(output_dir)
    }
    for relative_path in sorted(set(entries) - actual_paths):
        errors.append(f"missing manifest entry target: {relative_path}")
    for relative_path in sorted(actual_paths - set(entries)):
        errors.append(f"unlisted file: {relative_path}")
    for relative_path, expected_hash in sorted(entries.items()):
        path = output_dir / relative_path
        if not path.is_file():
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            errors.append(
                f"hash mismatch: {relative_path}: {actual_hash} != {expected_hash}"
            )
    return errors
