from __future__ import annotations

from scripts.lookup_primary_dielectric_references import parse_reference


def test_parse_reference_extracts_author_and_year() -> None:
    assert parse_reference("Nakazawa (2001)") == ("Nakazawa", 2001)


def test_parse_reference_rejects_unstructured_text() -> None:
    assert parse_reference("compilation only") is None
