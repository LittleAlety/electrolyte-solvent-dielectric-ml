from __future__ import annotations

import json
from pathlib import Path

from probes.export_week1_results import (
    REPOSITORY_ROOT,
    export_week1_results,
)


def _resolved_output_path(output_dir: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (output_dir / path).resolve()


def test_week1_export_summary_is_self_contained_without_mutating_repo_summary(
    tmp_path,
) -> None:
    source_summary_path = REPOSITORY_ROOT / "probes" / "p1_summary.json"
    before = source_summary_path.read_bytes()

    export_week1_results(tmp_path)

    exported_summary_path = tmp_path / "p1_summary.json"
    exported_summary = json.loads(exported_summary_path.read_text(encoding="utf-8"))
    output_root = tmp_path.resolve()

    for value in exported_summary["outputs"].values():
        destination = _resolved_output_path(tmp_path, value)
        assert destination.is_relative_to(output_root)
        assert destination.is_file()

    assert source_summary_path.read_bytes() == before
