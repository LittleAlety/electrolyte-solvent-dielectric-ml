from __future__ import annotations

import pytest

from probes.dielectric_density_feature_comparison import (
    density_adjusted_mu_sq_over_vm,
)


def test_density_adjusted_feature_uses_experimental_value() -> None:
    rows = [
        {
            "mu_sq_over_Vm": "10.0",
            "mu_sq_over_Vm_experimental": "12.5",
        }
    ]

    values = density_adjusted_mu_sq_over_vm(
        rows,
        use_experimental=True,
    )

    assert values.tolist() == [12.5]


def test_density_adjusted_feature_falls_back_to_xtb_value() -> None:
    rows = [
        {
            "mu_sq_over_Vm": "10.0",
            "mu_sq_over_Vm_experimental": "",
        }
    ]

    values = density_adjusted_mu_sq_over_vm(
        rows,
        use_experimental=True,
    )

    assert values.tolist() == [10.0]


def test_density_adjusted_feature_rejects_unknown_source() -> None:
    with pytest.raises(TypeError, match="source"):
        density_adjusted_mu_sq_over_vm([], use_experimental="maybe")
