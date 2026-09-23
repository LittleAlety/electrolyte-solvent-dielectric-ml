from __future__ import annotations

from electrolyte_ml.applicability import applicability_domain


def test_associated_liquid_is_outside_domain() -> None:
    assert (
        applicability_domain(70.0, hbd_count=1)
        == "outside_associated_liquid"
    )


def test_non_hbd_liquid_stays_in_domain() -> None:
    assert applicability_domain(70.0, hbd_count=0) == "inside_domain"


def test_nonphysical_prediction_is_outside_domain() -> None:
    assert applicability_domain(0.5, hbd_count=0) == "outside_nonphysical"
