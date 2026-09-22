from __future__ import annotations

from electrolyte_ml.numerics import numerical_values_close


def test_gpr_tolerance_accepts_small_platform_drift() -> None:
    assert numerical_values_close(1.000005, 1.0, model_family="gpr") is True


def test_gpr_tolerance_rejects_large_drift() -> None:
    assert numerical_values_close(1.0001, 1.0, model_family="gpr") is False


def test_xgboost_and_strict_profiles_are_tighter() -> None:
    assert numerical_values_close(1.0 + 5e-8, 1.0, model_family="xgboost") is True
    assert numerical_values_close(1.0 + 1e-6, 1.0, model_family="xgboost") is False
    assert numerical_values_close(1.0 + 1e-13, 1.0, model_family="strict") is True
    assert numerical_values_close(1.0 + 1e-9, 1.0, model_family="strict") is False
