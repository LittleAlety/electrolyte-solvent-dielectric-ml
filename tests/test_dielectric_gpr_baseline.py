from __future__ import annotations

import numpy as np

from probes.dielectric_gpr_baseline import (
    coverage_95,
    deterministic_split,
    morgan_count_features,
    regression_metrics,
)


def test_deterministic_split_is_reproducible_and_80_20() -> None:
    first_train, first_test = deterministic_split(100, seed=42)
    second_train, second_test = deterministic_split(100, seed=42)

    np.testing.assert_array_equal(first_train, second_train)
    np.testing.assert_array_equal(first_test, second_test)
    assert len(first_train) == 80
    assert len(first_test) == 20
    assert set(first_train).isdisjoint(first_test)


def test_regression_metrics_for_perfect_prediction() -> None:
    target = np.array([1.0, 2.0, 3.0])

    metrics = regression_metrics(target, target)

    assert metrics == {"mae": 0.0, "rmse": 0.0, "r2": 1.0}


def test_coverage_95_uses_posterior_std() -> None:
    target = np.array([0.0, 0.0, 0.0, 0.0])
    prediction = np.array([0.0, 1.0, 2.0, 3.0])
    std = np.array([1.0, 1.0, 1.0, 1.0])

    coverage = coverage_95(target, prediction, std)

    assert coverage["covered"] == 2
    assert coverage["total"] == 4
    assert coverage["coverage"] == 0.5
    assert coverage["z"] == 1.96


def test_morgan_count_features_have_fixed_dimension() -> None:
    features = morgan_count_features(["CCO", "CO"])

    assert features.shape == (2, 2048)
