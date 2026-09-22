from __future__ import annotations

import numpy as np

from probes.dielectric_baseline_diagnostics import (
    descriptor_features,
    gasteiger_nonfinite_count,
    run_learning_curve,
    run_single_split_models,
    summarize_metric_rows,
)


def test_descriptor_features_have_morgan_plus_fixed_descriptor_block() -> None:
    features, names = descriptor_features(["CCO", "CO"])

    assert features.shape == (2, 2062)
    assert len(names) == 14
    assert names[:2] == ("TPSA", "MolLogP")
    assert names[-1] == "Gasteiger_charge_sum_abs"


def test_descriptor_features_handle_nonfinite_gasteiger_charges_deterministically() -> None:
    smiles = "CCCCn1cc[n+](C)c1.F[P-](F)(F)(F)(F)F"

    features, _ = descriptor_features([smiles])

    assert np.isfinite(features).all()
    assert gasteiger_nonfinite_count([smiles]) > 0


def test_summarize_metric_rows_reports_mean_and_std() -> None:
    rows = [
        {"model": "A", "mae": 1.0, "rmse": 2.0, "r2": 0.1},
        {"model": "A", "mae": 3.0, "rmse": 4.0, "r2": 0.3},
    ]

    summary = summarize_metric_rows(rows)

    assert summary["A"]["mae"]["mean"] == 2.0
    assert summary["A"]["mae"]["std"] == np.sqrt(2.0)
    assert summary["A"]["r2"]["mean"] == 0.2


def test_single_split_models_are_deterministic_for_dummy_and_ridge() -> None:
    target = np.linspace(1.0, 10.0, 100)
    morgan = np.zeros((100, 2048))
    size = np.column_stack([target, np.ones_like(target)])

    first = run_single_split_models(
        target,
        morgan,
        size,
        model_names=("DummyMean", "SizeOnlyRidge"),
    )
    second = run_single_split_models(
        target,
        morgan,
        size,
        model_names=("DummyMean", "SizeOnlyRidge"),
    )

    assert first == second
    assert set(first) == {"DummyMean", "SizeOnlyRidge"}


def test_learning_curve_repeats_do_not_overlap_fixed_test() -> None:
    target = np.linspace(1.0, 10.0, 100)
    morgan = np.zeros((100, 2048))
    size = np.column_stack([target, np.ones_like(target)])

    rows = run_learning_curve(
        target,
        morgan,
        size,
        train_sizes=(20,),
        repeats=2,
        model_names=("DummyMean", "SizeOnlyRidge"),
    )

    assert len(rows) == 4
    assert {row["train_size"] for row in rows} == {20}
    assert {row["run"] for row in rows} == {0, 1}
    assert all(row["n_test"] == 20 for row in rows)
