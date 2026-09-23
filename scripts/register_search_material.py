"""Register locally captured search material with explicit licensing provenance.

The ``搜索资料`` tree sits *outside* the git repository on purpose: it holds
publisher screenshots, exported tables and PDFs that must never be committed.
This script walks that tree, hashes every artifact, and keeps a registry row
per file carrying the licensing vocabulary already defined in
``docs/week3/manual_dielectric_entry_schema.md``.

Defaults are deliberately conservative:

* ``closed_source`` defaults to true and ``non_redistributable`` to true, so a
  new artifact is treated as restricted until a human says otherwise.
* ``redistribution_status`` defaults to ``unclear``, which the schema treats as
  non-redistributable.
* ``usable_as_data`` is false for screenshots. Search-result pages and preview
  thumbnails show record counts, not values; they are never a data source.
* Files at the archive root are authored scaffolding (the README and the
  acquisition worklist), not captured material, so they do not inherit the
  restricted defaults that a freshly captured artifact gets.

Hand-edited provenance columns survive a re-run. Only the derived columns
(``sha256``, ``size_bytes``, ``artifact_type``, ``source_family``) are
refreshed, so filling in ``source_url`` or ``retrieved_at`` by hand is safe.

This script never writes inside the git repository and never copies artifact
content anywhere.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import (
    MANIFEST_NAME as SHA256SUMS_NAME,
)
from electrolyte_ml.exporting import (
    sha256_file,
    verify_export_manifest,
    write_export_manifest,
)

DEFAULT_ROOT = Path(r"E:\Claude Code\电解质ML\搜索资料")
REGISTRY_NAME = "search_material_registry.csv"
MANIFEST_DIR_NAME = "manifest"

REGISTRY_COLUMNS = (
    "artifact_id",
    "relative_path",
    "sha256",
    "size_bytes",
    "added_at",
    "artifact_type",
    "source_family",
    "source_url",
    "retrieved_at",
    "access_authorization",
    "closed_source",
    "non_redistributable",
    "redistribution_status",
    "usable_as_data",
    "notes",
)

# Columns a human may edit; preserved verbatim across re-runs.
PRESERVED_COLUMNS = (
    "added_at",
    "source_url",
    "retrieved_at",
    "access_authorization",
    "closed_source",
    "non_redistributable",
    "redistribution_status",
    "usable_as_data",
    "notes",
)

SOURCE_FAMILIES = ("nbs514", "springermaterials", "anchors", "authored", "other")

EXTENSION_ARTIFACT_TYPES = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".webp": "screenshot",
    ".gif": "screenshot",
    ".pdf": "pdf",
    ".csv": "csv_export",
    ".tsv": "csv_export",
    ".xlsx": "xlsx_export",
    ".xls": "xlsx_export",
    ".html": "html_snapshot",
    ".htm": "html_snapshot",
    ".mhtml": "html_snapshot",
    ".md": "manual_note",
    ".txt": "manual_note",
}

# A path containing any of these markers names a page that shows record counts
# or thumbnails rather than values, so it can never be consumed as data.
NON_DATA_PATH_MARKERS = ("public_metadata", "preview", "thumbnail", "search_result")


class RegistrationError(RuntimeError):
    """Raised when the requested root cannot be registered safely."""


@dataclass(frozen=True, slots=True)
class Artifact:
    relative_path: str
    absolute_path: Path
    sha256: str
    size_bytes: int


def is_inside(parent: Path, child: Path) -> bool:
    """Return whether ``child`` resolves to ``parent`` or somewhere beneath it."""

    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def ensure_root_is_external(root: Path) -> None:
    """Refuse a root inside the git repository."""

    if is_inside(REPOSITORY_ROOT, root):
        raise RegistrationError(
            f"refusing to register a root inside the repository: {root} "
            f"(repository root is {REPOSITORY_ROOT})"
        )


def artifact_id_for(relative_path: str) -> str:
    """Return a stable identifier derived from the artifact's path."""

    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()
    return f"sm:{digest[:12]}"


def source_family_for(relative_path: str) -> str:
    """Classify an artifact by its path.

    A file sitting at the archive root is authored scaffolding -- the README and
    the acquisition worklist.  Captured material always lands in a
    source-family subdirectory, so a root-level file is not third-party content
    and must not inherit the restricted defaults.
    """

    normalised = relative_path.replace("\\", "/")
    if "/" not in normalised:
        return "authored"
    head = normalised.split("/", 1)[0]
    return head if head in SOURCE_FAMILIES else "other"


def artifact_type_for(relative_path: str) -> str:
    return EXTENSION_ARTIFACT_TYPES.get(Path(relative_path).suffix.casefold(), "other")


def classify_usable_as_data(relative_path: str, artifact_type: str) -> bool:
    """Return whether this artifact may be read as numeric data.

    Only full-value exports can be data.  Screenshots, PDFs, snapshots and
    anything filed under a record-count-only path are metadata evidence.
    """

    if artifact_type not in {"csv_export", "xlsx_export"}:
        return False
    lowered = relative_path.replace("\\", "/").casefold()
    return not any(marker in lowered for marker in NON_DATA_PATH_MARKERS)


def collect_artifacts(root: Path) -> list[Artifact]:
    """Return every registrable file under ``root``, sorted by relative path.

    Derived outputs are skipped: the manifest directory holds this script's own
    registry, and a root-level ``SHA256SUMS`` is regenerated on every run, so
    registering either would make the registry hash itself.
    """

    artifacts: list[Artifact] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == MANIFEST_DIR_NAME:
            continue
        if relative.as_posix() == SHA256SUMS_NAME:
            continue
        artifacts.append(
            Artifact(
                relative_path=relative.as_posix(),
                absolute_path=path,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    return artifacts


def read_existing_registry(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {
            row["relative_path"]: row
            for row in reader
            if row.get("relative_path")
        }


def build_row(
    artifact: Artifact,
    *,
    previous: dict[str, str] | None,
    now: str,
) -> dict[str, str]:
    artifact_type = artifact_type_for(artifact.relative_path)
    source_family = source_family_for(artifact.relative_path)
    # A public US Government publication is not closed, but its redistribution
    # status still needs a copyright determination, so it stays `unclear`.
    if source_family == "nbs514":
        access, closed, non_redistributable, status = (
            "public",
            "false",
            "true",
            "unclear",
        )
    # Authored scaffolding holds no measurements and no third-party rights.
    elif source_family == "authored":
        access, closed, non_redistributable, status = (
            "n/a",
            "false",
            "false",
            "allowed",
        )
    else:
        access, closed, non_redistributable, status = (
            "unknown",
            "true",
            "true",
            "unclear",
        )
    usable = (
        False
        if source_family == "authored"
        else classify_usable_as_data(artifact.relative_path, artifact_type)
    )
    row = {
        "artifact_id": artifact_id_for(artifact.relative_path),
        "relative_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": str(artifact.size_bytes),
        "added_at": now,
        "artifact_type": artifact_type,
        "source_family": source_family,
        "source_url": "",
        "retrieved_at": "",
        "access_authorization": access,
        "closed_source": closed,
        "non_redistributable": non_redistributable,
        "redistribution_status": status,
        "usable_as_data": str(usable).lower(),
        "notes": "",
    }
    if previous is not None:
        for column in PRESERVED_COLUMNS:
            value = previous.get(column)
            if value not in (None, ""):
                row[column] = value
    return row


def write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{REGISTRY_NAME}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def verify_registry(
    root: Path,
    rows: list[dict[str, str]],
    artifacts: list[Artifact],
) -> list[str]:
    """Return a list of problems; empty means the registry matches the tree."""

    errors: list[str] = []
    registered = {row["relative_path"] for row in rows}
    on_disk = {artifact.relative_path for artifact in artifacts}

    for relative_path in sorted(registered - on_disk):
        errors.append(f"registry row has no file on disk: {relative_path}")
    for relative_path in sorted(on_disk - registered):
        errors.append(f"unregistered file on disk: {relative_path}")

    by_path = {row["relative_path"]: row for row in rows}
    for artifact in artifacts:
        row = by_path.get(artifact.relative_path)
        if row is None:
            continue
        if row["sha256"] != artifact.sha256:
            errors.append(
                f"hash mismatch: {artifact.relative_path}: "
                f"{artifact.sha256} != {row['sha256']}"
            )
        if row["size_bytes"] != str(artifact.size_bytes):
            errors.append(
                f"size mismatch: {artifact.relative_path}: "
                f"{artifact.size_bytes} != {row['size_bytes']}"
            )

    # A row that is closed-source must never also claim it is redistributable.
    for row in rows:
        if row["closed_source"] == "true" and row["redistribution_status"] == "allowed":
            errors.append(
                f"contradictory provenance: {row['relative_path']} is closed_source "
                "but redistribution_status=allowed"
            )
    errors.extend(verify_export_manifest(root))
    return errors


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root

    try:
        ensure_root_is_external(root)
    except RegistrationError as error:
        print(f"error: {error}")
        return 1

    if not root.is_dir():
        # Absent on CI and on any machine that has not captured material yet.
        message = {
            "root": str(root),
            "exists": False,
            "registered": 0,
            "note": "root does not exist; nothing to register",
        }
        print(json.dumps(message, indent=2) if args.json else message["note"])
        return 0

    registry_path = root / MANIFEST_DIR_NAME / REGISTRY_NAME
    previous_rows = read_existing_registry(registry_path)
    artifacts = collect_artifacts(root)

    if args.verify:
        errors = verify_registry(root, list(previous_rows.values()), artifacts)
        result = {
            "root": str(root),
            "verify": True,
            "registry": str(registry_path),
            "registered": len(previous_rows),
            "on_disk": len(artifacts),
            "errors": errors,
        }
        print(json.dumps(result, indent=2) if args.json else _render_verify(result))
        return 1 if errors else 0

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        build_row(
            artifact,
            previous=previous_rows.get(artifact.relative_path),
            now=now,
        )
        for artifact in artifacts
    ]
    write_registry(registry_path, rows)
    write_export_manifest(root)

    result = {
        "root": str(root),
        "verify": False,
        "registry": str(registry_path),
        "registered": len(rows),
        "usable_as_data": sum(row["usable_as_data"] == "true" for row in rows),
        "closed_source": sum(row["closed_source"] == "true" for row in rows),
        "errors": [],
    }
    print(json.dumps(result, indent=2) if args.json else _render_register(result))
    return 0


def _render_register(result: dict[str, object]) -> str:
    return (
        f"registered {result['registered']} artifact(s) under {result['root']}\n"
        f"  closed_source: {result['closed_source']}\n"
        f"  usable_as_data: {result['usable_as_data']}\n"
        f"  registry: {result['registry']}"
    )


def _render_verify(result: dict[str, object]) -> str:
    errors = result["errors"]
    lines = [
        f"root: {result['root']}",
        f"registered rows: {result['registered']}",
        f"files on disk: {result['on_disk']}",
    ]
    if errors:
        lines.append(f"FAIL ({len(errors)} problem(s)):")
        lines.extend(f"  - {error}" for error in errors)
    else:
        lines.append("OK: registry, hashes and manifest agree")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
