"""Tests for the manuscript figure-section guard.

These tests read the committed manuscript instead of running the two figure
probes, so they stay fast while still failing if a figure is renumbered,
dropped, or left citing a path that is not in the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from paper_figure_dataset_growth import _flag_counts, _missing_evidence_rows
from verify_paper_figures import (
    EXPECTED_FIGURE_ARTIFACTS,
    EXPECTED_FIGURE_COUNT,
    FIGURE_SECTION,
    parse_figure_section,
    validate_figures,
)


def _figures() -> list[dict]:
    text = FIGURE_SECTION.read_text(encoding="utf-8-sig")
    return parse_figure_section(text)


def test_figure_section_lists_six_consecutive_figures() -> None:
    figures = _figures()
    assert len(figures) == EXPECTED_FIGURE_COUNT
    assert [figure["number"] for figure in figures] == list(
        range(1, EXPECTED_FIGURE_COUNT + 1)
    )


def test_every_figure_cites_an_artifact_that_exists() -> None:
    for figure in _figures():
        assert figure["artifacts"], f"Figure {figure['number']} cites no artifact"
        for relative in figure["artifacts"] + figure["scripts"]:
            assert (REPOSITORY_ROOT / relative).is_file(), (
                f"Figure {figure['number']} cites a missing path: {relative}"
            )


def test_the_two_dedicated_figure_probes_are_cited() -> None:
    cited = {script for figure in _figures() for script in figure["scripts"]}
    assert "probes/paper_figure_dataset_growth.py" in cited
    assert "probes/paper_figure_conformal_strata.py" in cited


def test_every_figure_cites_a_generating_script() -> None:
    """Four of the six used to cite only an artifact, which is not reproducible."""

    for figure in _figures():
        assert figure["scripts"], f"Figure {figure['number']} cites no generating script"


def test_a_figure_pointed_at_an_unrelated_existing_file_is_rejected() -> None:
    """Existence alone must not be enough: the artifact is pinned per figure."""

    figures = _figures()
    figures[2]["artifacts"] = ["data/dielectric_v03.csv"]
    errors = validate_figures(figures)
    assert any("registered artifact" in error for error in errors), errors
    assert any("must be a rendered file" in error for error in errors), errors


def test_a_figure_without_a_script_is_rejected() -> None:
    figures = _figures()
    figures[0]["scripts"] = []
    errors = validate_figures(figures)
    assert any("no generating Script command" in error for error in errors), errors


def test_the_registered_artifact_map_covers_every_figure() -> None:
    assert sorted(EXPECTED_FIGURE_ARTIFACTS) == list(range(1, EXPECTED_FIGURE_COUNT + 1))
    cited = {figure["number"]: figure["artifacts"] for figure in _figures()}
    for number, expected in EXPECTED_FIGURE_ARTIFACTS.items():
        assert expected in cited[number]


def test_missing_evidence_level_is_detected() -> None:
    """The old check summed the counter and could never fire."""

    rows = [
        {"evidence_level": "primary"},
        {"evidence_level": ""},
        {"evidence_level": "open_access_review_table"},
    ]
    counts = _flag_counts(rows, "evidence_level")
    assert sum(counts.values()) == len(rows)
    assert _missing_evidence_rows(counts) == 1
    assert _missing_evidence_rows({"primary": 2}) == 0
