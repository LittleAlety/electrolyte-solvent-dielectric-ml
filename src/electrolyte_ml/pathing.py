"""Cross-platform path helpers for string-valued provenance fields."""

from __future__ import annotations

from pathlib import Path


def portable_basename(path: str | Path) -> str:
    """Return a basename after normalizing both Windows and POSIX separators."""

    return str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def portable_relative_path(path: str | Path, *, root: str | Path) -> str:
    """Return a POSIX path relative to root, or an absolute fallback outside it."""

    resolved_path = Path(path).resolve()
    resolved_root = Path(root).resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()
