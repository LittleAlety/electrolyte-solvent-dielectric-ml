from __future__ import annotations

import math

import pytest

from probes.nbs514_alpha_harmonization_probe import (
    DIELECTRIC_V03,
    REPOSITORY_ROOT,
    find_internal_validations,
    harmonize_to_298_15,
    implied_dielectric_slope,
    parse_valid_range_c,
    target_in_valid_range,
)


def test_linear_branch_matches_nbs_benzene() -> None:
    # NBS Circular 514 lists benzene at 20 C as 2.284 with a = 200e-5.
    harmonized = harmonize_to_298_15(2.284, 293.15, 200.0, "a")

    assert harmonized == pytest.approx(2.274, abs=1e-9)


def test_logarithmic_branch_matches_nbs_chlorobenzene() -> None:
    # Chlorobenzene: 5.71 at 20 C with alpha = 130e-5 predicts 5.621 at 25 C,
    # which is the value NBS tabulates independently.
    harmonized = harmonize_to_298_15(5.71, 293.15, 130.0, "alpha")

    assert harmonized == pytest.approx(5.621, abs=5e-3)


def test_branches_move_in_the_same_direction_below_target() -> None:
    linear = harmonize_to_298_15(10.0, 293.15, 300.0, "a")
    logarithmic = harmonize_to_298_15(10.0, 293.15, 300.0, "alpha")

    assert linear < 10.0
    assert logarithmic < 10.0


def test_harmonization_is_identity_at_the_target_temperature() -> None:
    assert harmonize_to_298_15(7.5, 298.15, 1234.0, "a") == pytest.approx(7.5)
    assert harmonize_to_298_15(7.5, 298.15, 1234.0, "alpha") == pytest.approx(7.5)


def test_unsupported_coefficient_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        harmonize_to_298_15(5.0, 293.15, 100.0, "b")


def test_implied_slope_is_negative_for_normal_liquids() -> None:
    assert implied_dielectric_slope(20.0, 205.0, "alpha") < 0.0
    assert implied_dielectric_slope(8.03, 3000.0, "a") < 0.0
    assert implied_dielectric_slope(2.97, -230.0, "a") > 0.0


def test_implied_slope_alpha_matches_chain_rule() -> None:
    dielectric = 15.0
    alpha_1e5 = 250.0
    slope = implied_dielectric_slope(dielectric, alpha_1e5, "alpha")

    assert slope == pytest.approx(-alpha_1e5 * 1e-5 * dielectric * math.log(10.0))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,55", (1.0, 55.0)),
        ("0 to 50", (0.0, 50.0)),
        ("at20", (20.0, 20.0)),
        ("at 20", (20.0, 20.0)),
        ("20", (20.0, 20.0)),
        ("19", (19.0, 19.0)),
        ("-60,40", (-60.0, 40.0)),
        ("-40 to 80", (-40.0, 80.0)),
        ("30,35", (30.0, 35.0)),
        ("", (None, None)),
    ],
)
def test_parse_valid_range_c(text: str, expected: tuple[float | None, float | None]) -> None:
    assert parse_valid_range_c(text) == expected


def test_target_in_valid_range_handles_boundaries_and_unknown() -> None:
    assert target_in_valid_range(20.0, 30.0) is True
    assert target_in_valid_range(25.0, 25.0) is True
    assert target_in_valid_range(30.0, 35.0) is False
    assert target_in_valid_range(None, None) is None


def test_internal_validation_uses_the_other_tabulated_entry() -> None:
    transcript = [
        {
            "source_id": "nbs514:p01:001",
            "compound_name": "Widgetol",
            "formula": "C2H6O",
            "dielectric": "10.00",
            "T_K": "298.15",
            "alpha_1e5": "200.0",
            "alpha_kind": "alpha",
            "valid_range_C": "10,40",
        },
        {
            "source_id": "nbs514:p01:002",
            "compound_name": "Widgetol",
            "formula": "C2H6O",
            "dielectric": "10.24",
            "T_K": "293.15",
            "alpha_1e5": "",
            "alpha_kind": "",
            "valid_range_C": "",
        },
    ]

    pairs = find_internal_validations(transcript)

    assert len(pairs) == 1
    assert pairs[0]["observed_entry_has_coefficient"] is False
    assert pairs[0]["predicted_dielectric"] == pytest.approx(10.2329, abs=1e-3)
    assert pairs[0]["relative_error"] < 0.01


def test_frozen_dataset_is_not_modified_by_the_probe() -> None:
    from electrolyte_ml.exporting import canonical_text_sha256

    # The probe is analysis-only; the canonical dataset hash must stay frozen.
    digest = canonical_text_sha256(REPOSITORY_ROOT / DIELECTRIC_V03)
    assert digest == (
        "a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085"
    )
