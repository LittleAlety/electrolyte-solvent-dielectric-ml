"""Regression tests for the paper <-> artifact consistency checker."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.build_paper_full_draft import SECTION_ORDER, render_full_draft
from scripts.check_paper_artifact_consistency import (
    PAPER_DIR,
    constant_baseline_metrics,
    verify_paper,
)


@pytest.fixture()
def paper_copy(tmp_path: Path) -> Path:
    """A writable copy of paper/ so drift can be injected without touching git."""
    target = tmp_path / "paper"
    target.mkdir()
    for name in (*SECTION_ORDER, "full_draft.md", "outline.md"):
        shutil.copy2(PAPER_DIR / name, target / name)
    return target


def test_paper_drafts_agree_with_frozen_artifacts(paper_copy: Path) -> None:
    assert verify_paper(paper_copy) == []


def test_full_draft_is_generated_from_the_section_files(paper_copy: Path) -> None:
    actual = (paper_copy / "full_draft.md").read_text(encoding="utf-8")
    assert actual == render_full_draft(paper_copy)


def test_a_stale_benchmark_number_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "benchmark_and_figures.md"
    text = path.read_text(encoding="utf-8")
    assert "**0.364**" in text
    path.write_text(text.replace("**0.364**", "**0.377**"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("0.377" in error for error in errors), errors


def test_a_stale_row_count_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "methods_data_records.md"
    text = path.read_text(encoding="utf-8")
    assert "(246 compounds)" in text
    path.write_text(text.replace("(246 compounds)", "(245 compounds)"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("245 compounds" in error for error in errors), errors


def test_conflict_count_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "methods_data_records.md"
    text = path.read_text(encoding="utf-8")
    assert "Nine rows" in text
    path.write_text(text.replace("Nine rows", "Five rows"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("conflict rows" in error for error in errors), errors


def test_a_stale_full_draft_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "full_draft.md"
    path.write_text(path.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("full_draft.md is stale" in error for error in errors), errors


def test_an_immutable_release_claim_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "outline.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nList the immutable release commit.\n",
        encoding="utf-8",
    )
    errors = verify_paper(paper_copy)
    assert any("immutable release commit" in error for error in errors), errors


def test_constant_baseline_is_deterministic_and_matches_the_paper() -> None:
    first = constant_baseline_metrics()
    assert first == constant_baseline_metrics()
    assert first["mae"] == pytest.approx(11.9670, abs=5e-4)
    assert first["r2"] == pytest.approx(-0.0126, abs=5e-4)
    assert first["mae_lt20"] == pytest.approx(8.3003, abs=5e-4)

def test_applicability_trigger_rate_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "benchmark_and_figures.md"
    text = path.read_text(encoding="utf-8")
    assert "33.66%" in text
    path.write_text(text.replace("33.66%", "31.66%"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("applicability trigger rate" in error for error in errors), errors


def test_applicability_flagged_row_count_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "methods_data_records.md"
    text = path.read_text(encoding="utf-8")
    # the claim wraps across a line, so drift is injected on the number alone
    assert "2,070" in text
    path.write_text(text.replace("2,070", "2,000"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("rows outside the domain" in error for error in errors), errors


def test_the_retired_circular_rule_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "outline.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nThe rule is HBD >= 1 and predicted dielectric `> 60`.\n",
        encoding="utf-8",
    )
    errors = verify_paper(paper_copy)
    assert any("predicted dielectric" in error for error in errors), errors


def test_the_rejected_onsager_wording_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "technical_validation.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nOnsager-estimated static dielectric above 60 are flagged.\n",
        encoding="utf-8",
    )
    errors = verify_paper(paper_copy)
    assert any(
        "Onsager variant was measured and rejected" in error for error in errors
    ), errors


def test_fitted_row_count_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "benchmark_and_figures.md"
    text = path.read_text(encoding="utf-8")
    assert "236 fitted rows" in text
    path.write_text(text.replace("236 fitted rows", "237 fitted rows"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("fitted rows" in error for error in errors), errors


def test_controlled_delta_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "abstract_and_intro.md"
    text = path.read_text(encoding="utf-8")
    assert "+0.0059 R2" in text
    path.write_text(text.replace("+0.0059 R2", "+0.0265 R2"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("controlled R2 gain" in error for error in errors), errors

def test_coverage_table_fitted_row_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "technical_validation.md"
    text = path.read_text(encoding="utf-8")
    assert "| **236** |" in text
    path.write_text(text.replace("| **236** |", "| **237** |"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("fitted rows" in error for error in errors), errors


def test_coverage_table_metric_drift_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "technical_validation.md"
    text = path.read_text(encoding="utf-8")
    assert "**0.3636**" in text
    path.write_text(text.replace("**0.3636**", "**0.3777**"), encoding="utf-8")
    errors = verify_paper(paper_copy)
    assert any("Morgan+Physical" in error for error in errors), errors


def test_a_superseded_row_count_phrase_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "technical_validation.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nThe v0.3.2 237-row benchmark is the current one.\n",
        encoding="utf-8",
    )
    errors = verify_paper(paper_copy)
    assert any("237-row" in error for error in errors), errors


def test_a_duplicate_ablation_table_is_rejected(paper_copy: Path) -> None:
    path = paper_copy / "technical_validation.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n| Morgan (ECFP4 count) | 0.223 |\n",
        encoding="utf-8",
    )
    errors = verify_paper(paper_copy)
    assert any("ECFP4 count" in error for error in errors), errors
