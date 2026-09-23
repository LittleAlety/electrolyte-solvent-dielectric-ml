from __future__ import annotations

import pytest

from probes.build_density_physical_features import (
    experimental_molar_volume,
    select_density,
)


def test_select_density_prefers_closest_temperature() -> None:
    observations = [
        {"temperature_K": 293.15, "density_kg_m3": 1000.0, "property_value_digits": 4},
        {"temperature_K": 298.15, "density_kg_m3": 997.0, "property_value_digits": 4},
    ]

    selected = select_density(observations, 298.0)

    assert selected is not None
    assert selected["density_kg_m3"] == 997.0


def test_select_density_rejects_far_temperature() -> None:
    assert select_density([{"temperature_K": 350.0, "density_kg_m3": 900.0}], 298.0) is None


def test_experimental_molar_volume_uses_molecular_weight() -> None:
    assert experimental_molar_volume("CO", 1000.0) == pytest.approx(3.2042e-5, rel=1e-3)
