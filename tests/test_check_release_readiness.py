"""Regression tests for the v1.0 release-readiness gate.

The gate exists because `paper/submission_checklist.md` forbids tagging before
the Zenodo DOI is known. It must stay red while the manuscript is still a
candidate, and it must go green only on a fully resolved release.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_readiness import SHIPPED_FILES, check_release_readiness

RELEASED_CODE_AND_DATA = """# Code and Data Availability

**Repository:** https://github.com/example-org/dielectric-ml
**Release:** v1.0 (tagged 2026-10-01)
**DOI:** https://doi.org/10.5281/zenodo.1234567
"""

CANDIDATE_CODE_AND_DATA = """# Code and Data Availability

**Repository:** https://github.com/[repository-name]
**Release:** v0.3.3 (candidate; v1.0 tag will be applied only after the freeze)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]
"""


@pytest.fixture()
def paper_dir(tmp_path: Path) -> Path:
    """A resolved release, so each test can inject exactly one defect."""
    target = tmp_path / "paper"
    target.mkdir()
    for name in SHIPPED_FILES:
        text = RELEASED_CODE_AND_DATA if name == "code_and_data.md" else "# Section\n"
        (target / name).write_text(text, encoding="utf-8")
    return target


def test_a_resolved_release_passes(paper_dir: Path) -> None:
    assert check_release_readiness(paper_dir) == []


def test_the_candidate_release_block_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "code_and_data.md").write_text(CANDIDATE_CODE_AND_DATA, encoding="utf-8")
    errors = check_release_readiness(paper_dir)
    assert any("candidate" in error for error in errors), errors
    assert any("Zenodo DOI placeholder" in error for error in errors), errors
    assert any("not a real Zenodo DOI" in error for error in errors), errors
    assert any("GitHub URL" in error for error in errors), errors


def test_a_todo_in_a_shipped_file_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "cover_letter.md").write_text(
        "# Cover letter\n\n[TODO: email]\n", encoding="utf-8"
    )
    errors = check_release_readiness(paper_dir)
    assert any("cover_letter.md" in error and "TODO" in error for error in errors), errors


def test_a_placeholder_in_the_methods_section_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "methods_data_records.md").write_text(
        "Available at https://github.com/[repository].\n", encoding="utf-8"
    )
    errors = check_release_readiness(paper_dir)
    assert any("methods_data_records.md" in error for error in errors), errors


def test_a_version_that_is_not_v1_0_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "code_and_data.md").write_text(
        RELEASED_CODE_AND_DATA.replace("v1.0 (tagged", "v0.3.3 (tagged"),
        encoding="utf-8",
    )
    errors = check_release_readiness(paper_dir)
    assert any("does not start with v1.0" in error for error in errors), errors


def test_documentation_placeholders_in_inline_code_are_ignored(paper_dir: Path) -> None:
    """The cover letter documents the convention; that must not fail the gate."""
    (paper_dir / "cover_letter.md").write_text(
        "# Cover letter\n\nEvery `[TODO: ...]` must be resolved before sending.\n",
        encoding="utf-8",
    )
    assert check_release_readiness(paper_dir) == []


def test_smarts_and_metric_intervals_are_not_placeholders(paper_dir: Path) -> None:
    (paper_dir / "benchmark_and_figures.md").write_text(
        "SMARTS [O,S,N;!H0] with interval [-0.002, +0.013].\n", encoding="utf-8"
    )
    assert check_release_readiness(paper_dir) == []


def test_a_missing_manuscript_file_is_reported(paper_dir: Path) -> None:
    (paper_dir / "outline.md").unlink()
    errors = check_release_readiness(paper_dir)
    assert any("outline.md: missing" in error for error in errors), errors
