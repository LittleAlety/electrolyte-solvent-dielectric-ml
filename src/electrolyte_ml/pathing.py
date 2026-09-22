"""Cross-platform path helpers for string-valued provenance fields."""

from __future__ import annotations

from pathlib import Path


def portable_basename(path: str | Path) -> str:
    """Return a basename after normalizing both Windows and POSIX separators."""

    return str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
