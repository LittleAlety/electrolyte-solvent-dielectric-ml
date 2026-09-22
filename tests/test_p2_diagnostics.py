from __future__ import annotations

import json

import numpy as np
import pytest

import probes.p2_diagnostics as diagnostics_module
from probes.p2_diagnostics import (
    ATOMIC_TO_DEBYE,
    TARGET_UNIT_EVIDENCE,
    MorganMetricMismatchError,
    atomic_to_debye,
    audit_morgan_metrics,
    distribution_diagnostics,
    evaluate_model_baselines,
    size_features,
    stratified_diagnostics,
    update_p2_summary_units,
)


def test_atomic_to_debye_uses_declared_conversion() -> None:
    converted = atomic_to_debye(np.array([1.0, 2.0]))

    np.testing.assert_allclose(converted, np.array([2.5418, 5.0836]))
    assert ATOMIC_TO_DEBYE == 2.5418


def test_distribution_diagnostics_uses_debye_thresholds() -> None:
    target_debye = np.array([0.25, 0.75, 2.0, 4.0])
    target_au = target_debye / ATOMIC_TO_DEBYE

    diagnostics = distribution_diagnostics(target_au)

    assert diagnostics["count"] == 4
    assert diagnostics["fractions"] == {
        "lt_0_5D": 0.25,
        "0_5D_to_1D": 0.25,
        "1D_to_3D": 0.25,
        "gt_3D": 0.25,
    }
    assert diagnostics["quantiles_debye"]["p50"] == pytest.approx(1.375)


def test_stratified_diagnostics_flags_small_strata_insufficient() -> None:
    target_debye = np.array([0.25, 0.75, 2.0, 4.0])
    target_au = target_debye / ATOMIC_TO_DEBYE

    diagnostics = stratified_diagnostics(target_au, target_au)

    assert diagnostics["overall"]["metrics_au"]["r2"] == 1.0
    assert diagnostics["strata"]["lt_0_5D"]["n"] == 1
    assert diagnostics["strata"]["lt_0_5D"]["status"] == "insufficient"


def test_model_baselines_use_same_split_and_report_both_units() -> None:
    y = np.linspace(0.1, 1.0, 100)
    size_x = np.column_stack([y, np.ones_like(y)])
    morgan_x = np.zeros((100, 2048))
    morgan_x[:, 0] = y
    train_indices = np.arange(80)
    test_indices = np.arange(80, 100)

    diagnostics = evaluate_model_baselines(
        y,
        morgan_x,
        size_x,
        train_indices,
        test_indices,
        metric_tolerance=1e-8,
    )

    assert diagnostics["dummy"]["n_test"] == 20
    assert diagnostics["size_only_ridge"]["n_test"] == 20
    assert diagnostics["morgan_xgboost"]["n_test"] == 20
    assert "r2" in diagnostics["size_only_ridge"]["metrics_au"]


def test_model_baselines_fit_morgan_model(monkeypatch) -> None:
    fitted_models: list[object] = []

    class FakeModel:
        def fit(self, features, target) -> None:
            self.mean = float(np.mean(target))
            fitted_models.append(self)

        def predict(self, features) -> np.ndarray:
            return np.full(len(features), self.mean)

    monkeypatch.setattr(diagnostics_module, "_model", lambda seed: FakeModel())
    y = np.linspace(0.1, 1.0, 30)
    morgan_x = np.zeros((30, 2048))
    size_x = np.column_stack([y, np.ones_like(y)])

    evaluate_model_baselines(
        y,
        morgan_x,
        size_x,
        np.arange(24),
        np.arange(24, 30),
        metric_tolerance=1e-8,
    )

    assert len(fitted_models) == 1


def test_missing_formal_metrics_is_allowed_for_retrained_morgan() -> None:
    audit = audit_morgan_metrics(
        {"mae": 0.36, "rmse": 0.49, "r2": 0.56},
        None,
        tolerance=1e-8,
    )

    assert audit["formal_metrics_available"] is False
    assert audit["passed"] is None


def test_recomputed_morgan_metric_mismatch_raises() -> None:
    with pytest.raises(MorganMetricMismatchError, match="r2"):
        audit_morgan_metrics(
            {"mae": 0.36, "rmse": 0.49, "r2": 0.56},
            {"mae": 0.36, "rmse": 0.49, "r2": 0.50},
            tolerance=1e-8,
        )


def test_unit_evidence_urls_are_commit_pinned() -> None:
    urls = {item["url"] for item in TARGET_UNIT_EVIDENCE}

    assert any(
        "b166b8635a3ace9497ff34a80928a3a8d2b8eb01" in url for url in urls
    )
    assert any(
        "a5101e30c6975552d97e34f1e93461126715c862" in url for url in urls
    )


def test_size_features_are_molecular_weight_and_heavy_atoms() -> None:
    features = size_features("CCO")

    assert features.shape == (2,)
    assert features[0] == pytest.approx(46.069, abs=1e-3)
    assert features[1] == 3.0


def test_update_p2_summary_units_preserves_existing_fields(tmp_path) -> None:
    summary_path = tmp_path / "p2_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "target_units": "not stated",
                "final_metrics": {"mae": 1.0, "rmse": 2.0, "r2": 0.5},
                "pass_r2_gt_0_8": False,
            }
        ),
        encoding="utf-8",
    )

    update_p2_summary_units(summary_path)
    updated = json.loads(summary_path.read_text(encoding="utf-8"))

    assert updated["target_units"] == "atomic_units (e*bohr)"
    assert updated["final_metrics_units"] == "atomic_units (e*bohr)"
    assert updated["final_metrics_debye"]["mae"] == pytest.approx(2.5418)
    assert updated["pass_r2_gt_0_8"] is False
