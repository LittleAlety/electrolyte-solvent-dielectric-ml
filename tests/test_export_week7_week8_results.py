"""Delivery-package regression tests for the Week 7 and Week 8 exports."""

from __future__ import annotations

import json
from pathlib import Path

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week7_results import (
    README_TEXT as WEEK7_README_TEXT,
)
from probes.export_week7_results import (
    export_results as export_week7_results,
)
from probes.export_week8_results import (
    README_TEXT as WEEK8_README_TEXT,
)
from probes.export_week8_results import (
    export_results as export_week8_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_week7_export_ships_a_readme_and_current_fec_narrative(tmp_path: Path) -> None:
    export_week7_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    week7 = tmp_path / "week7"
    readme = (week7 / "README.md").read_text(encoding="utf-8")
    assert readme == WEEK7_README_TEXT
    assert "SHA256SUMS" in readme
    assert verify_export_manifest(week7) == []

    summary = json.loads((week7 / "week7_summary.json").read_text(encoding="utf-8"))
    note = summary["dataset_version_note"]
    assert (
        "v0.3.12 then landed the two field-level revisions it enabled, "
        "again without moving a dielectric value"
    ) not in note
    assert "moved the stored FEC dielectric from 102 to 78.4" in note
    open_items = "\n".join(summary["open_items"])
    assert "the stored 102 is recorded" not in open_items
    assert "the previously stored 102" in open_items


def test_week8_export_ships_a_readme_and_manifest(tmp_path: Path) -> None:
    export_week8_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    week8 = tmp_path / "week8"
    readme = (week8 / "README.md").read_text(encoding="utf-8")
    assert readme == WEEK8_README_TEXT
    assert "SHA256SUMS" in readme
    assert verify_export_manifest(week8) == []
