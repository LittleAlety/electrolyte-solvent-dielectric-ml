from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import probes.dielectric_representation_ablation as ablation
from probes.dielectric_representation_ablation import (
    evaluate_repeat,
    fit_predict_representation,
    physical_feature_matrix,
    read_modelling_rows,
    summarize_repeats,
)


def _feature_row(status: str = "ok") -> dict[str, str]:
    return {
        "status": status,
        "T_K": "298.15",
        "formal_charge": "0",
        "heavy_atom_count": "6",
        "hbd": "1",
        "hba": "1",
        "tpsa_A2": "20.23",
        "molecular_volume_A3": "103.816",
        "dipole_D": "1.692",
        "polarizability_A3": "10.1009",
        "mu_sq_over_Vm": "45791.569",
        "alpha_over_Vm": "0.097296",
        "total_energy_hartree": "-20.88",
        "homo_lumo_gap_ev": "12.11",
        "name": "example",
    }


def test_read_modelling_rows_separates_failed_features(tmp_path: Path) -> None:
    path = tmp_path / "features.csv"
    columns = tuple(_feature_row())
    rows = [_feature_row(), _feature_row("error")]
    path.write_text(
        ",".join(columns)
        + "\n"
        + ",".join(rows[0][column] for column in columns)
        + "\n"
        + ",".join(rows[1][column] for column in columns)
        + "\n",
        encoding="utf-8",
    )

    successful, failed = read_modelling_rows(path)

    assert len(successful) == 1
    assert len(failed) == 1
    assert physical_feature_matrix(successful).shape == (1, 13)


def test_fit_predict_representation_returns_one_prediction_per_test_row() -> None:
    morgan = np.arange(60, dtype=float).reshape(6, 10)
    physical = np.arange(12, dtype=float).reshape(6, 2)
    target = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    train = np.asarray([0, 1, 2, 3])
    test = np.asarray([4, 5])

    prediction, kernel = fit_predict_representation(
        "Morgan+Physical",
        morgan=morgan,
        physical=physical,
        target=target,
        train_indices=train,
        test_indices=test,
        seed=42,
    )

    assert prediction.shape == (2,)
    assert np.isfinite(prediction).all()
    assert kernel


def test_evaluate_repeat_and_summary_include_filter_and_ranking_metrics() -> None:
    target = np.asarray([3.0, 10.0, 20.0, 35.0, 50.0, 65.0])
    prediction = target + np.asarray([-1.0, 1.0, -2.0, 2.0, -3.0, 3.0])
    metrics = evaluate_repeat(target, prediction)
    rows = [{"representation": name, **metrics} for name in (
        "Morgan",
        "Physical",
        "Morgan+Physical",
    )]

    summary = summarize_repeats(rows)

    assert metrics["spearman"] == 1.0
    assert 0.0 <= metrics["auc_gt15"] <= 1.0
    assert 0.0 <= metrics["auc_gt30"] <= 1.0
    assert set(summary) == {"Morgan", "Physical", "Morgan+Physical"}
    assert summary["Physical"]["mae"]["mean"] > 0.0


def test_hybrid_prediction_is_true_equal_weight_ensemble(monkeypatch) -> None:
    def fake_fit_predict(
        train_features,
        test_features,
        target,
        train_indices,
        test_indices,
        seed,
    ):
        assert target.shape == (2,)
        assert train_indices.tolist() == [0]
        assert test_indices.tolist() == [1]
        assert seed == 42
        return (
            np.asarray([1.0, 5.0])
            if train_features.shape[1] == 2
            else np.asarray([3.0, 9.0])
        )

    monkeypatch.setattr(ablation, "_fit_predict_model", fake_fit_predict)
    prediction, _ = ablation.fit_predict_representation(
        "Morgan+Physical",
        morgan=np.zeros((2, 2)),
        physical=np.zeros((2, 1)),
        target=np.asarray([2.0, 6.0]),
        train_indices=np.asarray([0]),
        test_indices=np.asarray([1]),
        seed=42,
    )

    assert prediction.tolist() == [2.0, 7.0]


def test_summary_json_round_trips_mapping() -> None:
    payload = {"summary": {"Morgan": {"r2": {"mean": 0.1, "std": 0.0, "n": 1}}}}
    assert json.loads(json.dumps(payload)) == payload
