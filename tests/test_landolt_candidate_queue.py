from __future__ import annotations

from scripts.build_landolt_candidate_queue import (
    BOOK_TITLE,
    build_queue,
    candidate_name,
    is_pure_substance_chapter,
)


def _chapter(title: str, container: str = BOOK_TITLE) -> dict[str, object]:
    return {
        "DOI": "10.1007/example",
        "title": [title],
        "container-title": [container],
    }


def test_pure_substance_chapter_filter_excludes_binary_mixtures() -> None:
    pure = _chapter("Static dielectric constant of ethanol")
    mixture = _chapter(
        "Static dielectric constant of the binary liquid mixture of ethanol and water"
    )

    assert is_pure_substance_chapter(pure) is True
    assert is_pure_substance_chapter(mixture) is False


def test_candidate_name_strips_metadata_prefix() -> None:
    assert candidate_name("Static dielectric constant of ethylene carbonate") == (
        "ethylene carbonate"
    )


def test_build_queue_assigns_stable_ids_and_marks_manual_status() -> None:
    rows = build_queue(
        [
            _chapter("Static dielectric constant of ethanol"),
            _chapter(
                "Static dielectric constant of the binary liquid mixture of ethanol and water"
            ),
        ]
    )

    assert len(rows) == 1
    assert rows[0]["queue_id"] == "lb2015:0001"
    assert rows[0]["manual_value_status"] == "not_reviewed"
    assert rows[0]["decision_status"] == "awaiting_manual_review"
