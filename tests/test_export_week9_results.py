"""Delivery-package regression tests for the Week 9 export."""

from __future__ import annotations

import json
from pathlib import Path

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week9_results import README_TEXT as WEEK9_README_TEXT
from probes.export_week9_results import export_results as export_week9_results

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_week9_export_ships_a_readme_and_manifest(tmp_path: Path) -> None:
    export_week9_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    week9 = tmp_path / "week9"
    readme = (week9 / "README.md").read_text(encoding="utf-8")
    assert readme == WEEK9_README_TEXT
    assert "SHA256SUMS" in readme
    assert verify_export_manifest(week9) == []


def test_week9_summary_carries_the_six_figures_and_the_gate_numbers(tmp_path: Path) -> None:
    export_week9_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    summary = json.loads((tmp_path / "week9" / "week9_summary.json").read_text(encoding="utf-8"))
    assert summary["verification"] is True
    assert [figure["number"] for figure in summary["figures"]] == [1, 2, 3, 4, 5, 6]
    for figure in summary["figures"]:
        assert (tmp_path / "week9" / figure["artifact"]).is_file()

    leave_ec_out = summary["d1_leave_ec_out"]
    assert leave_ec_out["ec_in_training_folds"] == 0
    assert leave_ec_out["baseline_matches_frozen_predictions"] is True
    assert leave_ec_out["frozen_prediction_rows_checked"] == 7080
    assert leave_ec_out["family_ranking_changed"] is False
    assert leave_ec_out["hybrid_r2"]["baseline_full_236"] > leave_ec_out["hybrid_r2"][
        "leave_ec_out_235"
    ]

    coverage = summary["conformal_conditional_coverage"]
    assert 0.9 <= coverage["nominal_coverage"] <= 0.91
    for representation in coverage["representations"].values():
        assert 0.9 <= representation["marginal"] <= 0.94
        assert representation["coverage_gt60"] < 0.3
        assert representation["normalized_coverage_gt60"] < 0.6


def test_week9_paper_snapshot_matches_the_repository(tmp_path: Path) -> None:
    """A stale paper snapshot is the failure mode this package must not have."""

    export_week9_results(
        source_root=REPOSITORY_ROOT,
        output_root=tmp_path,
        overwrite=True,
    )

    for relative in (
        "paper/benchmark_and_figures.md",
        "paper/full_draft.md",
        "paper/methods_data_records.md",
    ):
        shipped = (tmp_path / "week9" / relative).read_bytes()
        current = (REPOSITORY_ROOT / relative).read_bytes()
        assert shipped == current, f"{relative} in the package is stale"
