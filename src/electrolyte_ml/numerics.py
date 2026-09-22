"""Shared numerical comparison policies for reproducible verifiers."""

from __future__ import annotations

import math

MODEL_TOLERANCES: dict[str, tuple[float, float]] = {
    "gpr": (1e-5, 1e-5),
    "morgan_gpr": (1e-5, 1e-8),
    "descriptor_gpr": (1e-5, 1e-5),
    "xgboost": (1e-7, 1e-8),
    "strict": (0.0, 1e-12),
}


def numerical_values_close(
    actual: float,
    expected: float,
    *,
    model_family: str,
) -> bool:
    """Compare values using an explicit model-aware platform tolerance."""

    try:
        rtol, atol = MODEL_TOLERANCES[model_family]
    except KeyError as error:
        raise ValueError(f"unknown numerical model family: {model_family}") from error
    return math.isclose(
        float(actual),
        float(expected),
        rel_tol=rtol,
        abs_tol=atol,
    )
