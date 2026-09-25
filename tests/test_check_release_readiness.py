"""Regression tests for the phased v1.0 release gate.

The gate exists because Zenodo archives a GitHub *release*: the release is what
mints the DOI, so the pre-release state legitimately carries a pending DOI
while the released state must carry the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_readiness import MANUSCRIPT_FILES, check_release_readiness

RELEASED_CODE_AND_DATA = """# Code and Data Availability

**Repository:** https://github.com/example-org/dielectric-ml
**Release:** v1.0 (GitHub release 2026-09-25; dataset v0.3.3)
**DOI:** https://doi.org/10.5281/zenodo.1234567
"""

PENDING_CODE_AND_DATA = RELEASED_CODE_AND_DATA.replace(
    "**DOI:** https://doi.org/10.5281/zenodo.1234567",
    "**DOI:** pending (Zenodo mints the DOI from the v1.0 GitHub release)",
)

CANDIDATE_CODE_AND_DATA = """# Code and Data Availability

**Repository:** https://github.com/[repository-name]
**Release:** v0.3.3 (candidate; v1.0 tag will be applied only after the freeze)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]
"""


@pytest.fixture()
def paper_dir(tmp_path: Path) -> Path:
    """A resolved pre-release tree, so each test injects exactly one defect."""
    target = tmp_path / "paper"
    target.mkdir()
    for name in MANUSCRIPT_FILES:
        text = PENDING_CODE_AND_DATA if name == "code_and_data.md" else "# Section\n"
        (target / name).write_text(text, encoding="utf-8")
    (target / "cover_letter.md").write_text("# Cover letter\n", encoding="utf-8")
    return target


def test_the_pre_release_state_passes_with_a_pending_doi(paper_dir: Path) -> None:
    assert check_release_readiness(paper_dir, "pre-release") == []


def test_the_released_state_requires_the_real_doi(paper_dir: Path) -> None:
    errors = check_release_readiness(paper_dir, "released")
    assert any("not a real Zenodo DOI" in error for error in errors), errors
    (paper_dir / "code_and_data.md").write_text(RELEASED_CODE_AND_DATA, encoding="utf-8")
    assert check_release_readiness(paper_dir, "released") == []


def test_the_candidate_release_block_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "code_and_data.md").write_text(CANDIDATE_CODE_AND_DATA, encoding="utf-8")
    errors = check_release_readiness(paper_dir, "pre-release")
    assert any("candidate" in error for error in errors), errors
    assert any("Zenodo DOI placeholder" in error for error in errors), errors
    assert any("not a real GitHub URL" in error for error in errors), errors


def test_a_placeholder_in_the_methods_section_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "methods_data_records.md").write_text(
        "Available at https://github.com/[repository].\n", encoding="utf-8"
    )
    errors = check_release_readiness(paper_dir, "pre-release")
    assert any("methods_data_records.md" in error for error in errors), errors


def test_a_version_that_is_not_v1_0_is_rejected(paper_dir: Path) -> None:
    (paper_dir / "code_and_data.md").write_text(
        RELEASED_CODE_AND_DATA.replace("v1.0 (GitHub", "v0.3.3 (GitHub"),
        encoding="utf-8",
    )
    errors = check_release_readiness(paper_dir, "pre-release")
    assert any("does not start with v1.0" in error for error in errors), errors


def test_a_free_form_doi_line_is_not_accepted_as_pending(paper_dir: Path) -> None:
    (paper_dir / "code_and_data.md").write_text(
        RELEASED_CODE_AND_DATA.replace(
            "**DOI:** https://doi.org/10.5281/zenodo.1234567", "**DOI:** coming soon"
        ),
        encoding="utf-8",
    )
    errors = check_release_readiness(paper_dir, "pre-release")
    assert any("explicit 'pending' marker" in error for error in errors), errors


def test_the_cover_letter_only_matters_in_the_submission_phase(paper_dir: Path) -> None:
    (paper_dir / "cover_letter.md").write_text(
        "# Cover letter\n\n[TODO: email]\n", encoding="utf-8"
    )
    assert check_release_readiness(paper_dir, "pre-release") == []
    errors = check_release_readiness(paper_dir, "submission")
    assert any("cover_letter.md" in error and "TODO" in error for error in errors), errors


def test_documentation_placeholders_in_inline_code_are_ignored(paper_dir: Path) -> None:
    """The cover letter documents the convention; that must not fail the gate."""
    (paper_dir / "code_and_data.md").write_text(RELEASED_CODE_AND_DATA, encoding="utf-8")
    (paper_dir / "cover_letter.md").write_text(
        "# Cover letter\n\nEvery `[TODO: ...]` must be resolved before sending.\n",
        encoding="utf-8",
    )
    assert check_release_readiness(paper_dir, "submission") == []


def test_smarts_and_metric_intervals_are_not_placeholders(paper_dir: Path) -> None:
    (paper_dir / "benchmark_and_figures.md").write_text(
        "SMARTS [O,S,N;!H0] with interval [-0.002, +0.013].\n", encoding="utf-8"
    )
    assert check_release_readiness(paper_dir, "pre-release") == []


def test_a_missing_manuscript_file_is_reported(paper_dir: Path) -> None:
    (paper_dir / "outline.md").unlink()
    errors = check_release_readiness(paper_dir, "pre-release")
    assert any("outline.md: missing" in error for error in errors), errors


def test_an_unknown_phase_is_refused(paper_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown phase"):
        check_release_readiness(paper_dir, "whenever")
