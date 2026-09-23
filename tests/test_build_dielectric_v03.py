from __future__ import annotations

import pytest

from scripts.build_dielectric_v03 import build_v03_rows
from scripts.verify_dielectric_v03 import verify_v03_rows


def _addition(**overrides: str) -> dict[str, str]:
    row = {
        "inchikey": "ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
        "smiles": "CC#N",
        "name": "example nitrile",
        "T_K": "298.15",
        "dielectric": "20.0",
        "uncertainty_value": "0.2",
        "uncertainty_kind": "standard",
        "confidence_level": "68",
        "source_doi": "10.1000/example",
        "source_url": "https://example.org/article",
        "source_citation": "Example (2000)",
        "source_table": "Table 1",
        "source_quality": "primary_experimental",
        "redistribution_status": "allowed",
    }
    row.update(overrides)
    return row


def test_build_v03_appends_public_observation() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)

    assert len(rows) == 1
    assert rows[0]["name"] == "example nitrile"
    assert rows[0]["dataset_origin"] == "v0.3_addition"
    assert rows[0]["temperature_band"] == "room_temperature"


def test_build_v03_rejects_restricted_observation() -> None:
    with pytest.raises(ValueError, match="restricted"):
        build_v03_rows(
            [],
            [_addition(redistribution_status="restricted")],
            minimum_additions=1,
        )


def test_build_v03_rejects_duplicate_inchikey() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_v03_rows([], [_addition(), _addition()], minimum_additions=1)


def test_build_v03_requires_minimum_additions() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        build_v03_rows([], [_addition()], minimum_additions=2)


def test_verify_v03_accepts_complete_public_addition() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert errors == []


def test_verify_v03_rejects_restricted_output_row() -> None:
    rows = build_v03_rows([], [_addition()], minimum_additions=1)
    rows[0]["redistribution_status"] = "restricted"

    errors = verify_v03_rows(rows, minimum_additions=1)

    assert any("restricted" in error for error in errors)


def test_build_v03_marks_conflicted_v02_row_not_model_ready() -> None:
    rows = build_v03_rows(
        [
            {
                "inchikey": "HBNYJWAFDZLWRS-UHFFFAOYSA-N",
                "T_K": "294.15",
            }
        ],
        [],
        minimum_additions=0,
        excluded_model_keys={"HBNYJWAFDZLWRS-UHFFFAOYSA-N"},
    )

    assert rows[0]["model_ready"] == "false"
    assert rows[0]["conflict_status"] == "excluded_model_conflict"
