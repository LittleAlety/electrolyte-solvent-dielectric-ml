"""Delivery-package regression tests for the Week 10 export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from electrolyte_ml.exporting import verify_export_manifest
from probes import export_week10_results as week10_module
from probes.export_week10_results import README_TEXT as WEEK10_README_TEXT
from probes.export_week10_results import export_results as export_week10_results

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_week10_export_ships_a_readme_and_manifest(tmp_path: Path) -> None:
    export_week10_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    week10 = tmp_path / "week10"
    readme = (week10 / "README.md").read_text(encoding="utf-8")
    assert readme == WEEK10_README_TEXT
    assert "SHA256SUMS" in readme
    assert verify_export_manifest(week10) == []


def test_week10_summary_records_the_m1_outcome(tmp_path: Path) -> None:
    export_week10_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    summary = json.loads(
        (tmp_path / "week10" / "week10_summary.json").read_text(encoding="utf-8")
    )
    assert summary["verification"] is True
    assert summary["review_baseline_commit"] == "795b52c"
    assert summary["dielectric_v03_sha256"] == (
        "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
    )

    review = summary["review"]
    assert any("0.802" in entry for entry in review["critical_fixed"])
    assert any("Tier-3/Tier-4" in entry for entry in review["important_fixed"])
    assert any("817-819" in entry for entry in review["minor_fixed"])
    assert any("0.757" in entry for entry in review["minor_fixed"])
    assert review["rejected"] and "labels" in review["rejected"][0]

    assert summary["guard"]["function"] == "check_abstract_ceiling_numbers"
    assert summary["gates"]["pytest"] == "847 passed"
    assert [figure["number"] for figure in summary["figures"]] == [1, 2, 3, 4, 5, 6]
    for figure in summary["figures"]:
        assert (tmp_path / "week10" / figure["artifact"]).is_file()


def test_week10_paper_snapshot_matches_the_repository(tmp_path: Path) -> None:
    """A stale paper snapshot is the failure mode this package must not have."""

    export_week10_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    for relative in (
        "paper/abstract_and_intro.md",
        "paper/full_draft.md",
        "paper/benchmark_and_figures.md",
    ):
        shipped = (tmp_path / "week10" / relative).read_bytes()
        current = (REPOSITORY_ROOT / relative).read_bytes()
        assert shipped == current, f"{relative} in the package is stale"


def test_week10_main_returns_non_zero_when_verification_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """A delivery package must not report success through its exit code alone."""

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_week10_results.py",
            "--output-root",
            str(tmp_path),
            "--overwrite",
        ],
    )

    monkeypatch.setattr(
        week10_module,
        "export_results",
        lambda **_: {"week": "week10", "output": str(tmp_path), "verification_passed": False},
    )
    assert week10_module.main() == 1

    monkeypatch.setattr(
        week10_module,
        "export_results",
        lambda **_: {"week": "week10", "output": str(tmp_path), "verification_passed": True},
    )
    assert week10_module.main() == 0
