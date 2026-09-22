from __future__ import annotations

import numpy as np

from probes.viscosity_baseline import (
    build_feature_matrix,
    regression_metrics,
)


def test_viscosity_features_include_morgan_temperature_and_inverse_temperature() -> None:
    features, names = build_feature_matrix(["CCO", "CO"], [298.15, 310.0])

    assert features.shape == (2, 2050)
    assert names[-2:] == ("T_K", "1000_over_T_K")
    assert features[0, -2] == 298.15
    assert features[0, -1] == 1000.0 / 298.15


def test_viscosity_regression_metrics_are_reproducible() -> None:
    target = np.array([0.0, 1.0, 2.0])

    metrics = regression_metrics(target, target)

    assert metrics == {"mae": 0.0, "rmse": 0.0, "r2": 1.0}
