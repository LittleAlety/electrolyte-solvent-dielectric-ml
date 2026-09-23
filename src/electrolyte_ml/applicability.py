"""Applicability-domain rules for dielectric-solvent predictions."""

from __future__ import annotations


def applicability_domain(
    predicted_dielectric: float,
    *,
    hbd_count: int,
) -> str:
    """Return a conservative domain label for one prediction."""

    if predicted_dielectric < 1.0:
        return "outside_nonphysical"
    if hbd_count >= 1 and predicted_dielectric > 60.0:
        return "outside_associated_liquid"
    return "inside_domain"
