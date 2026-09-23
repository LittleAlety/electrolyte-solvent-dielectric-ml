"""Applicability-domain rules for dielectric-solvent predictions."""

from __future__ import annotations


def applicability_domain(
    predicted_dielectric: float,
    *,
    hbd_count: int,
    onsager_epsilon: float | None = None,
) -> str:
    """Return a conservative domain label for one prediction.
    
    Uses Onsager-estimated epsilon as a model-independent high-dielectric
    threshold when available. Falls back to predicted dielectric when
    Onsager estimate is not available (legacy path).
    
    The Onsager estimate is computed independently of any ML model,
    so the threshold check is not a circular dependency on model outputs.
    """
    if predicted_dielectric < 1.0:
        return "outside_nonphysical"
    
    threshold_eps = onsager_epsilon if onsager_epsilon is not None else predicted_dielectric
    
    if hbd_count >= 1 and threshold_eps > 60.0:
        return "outside_associated_liquid"
    return "inside_domain"
