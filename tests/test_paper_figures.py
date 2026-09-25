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

from verify_paper_figures import (
    EXPECTED_FIGURE_COUNT,
    FIGURE_SECTION,
    parse_figure_section,
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
