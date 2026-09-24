from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import probes.dielectric_representation_ablation as ablation
from probes.dielectric_representation_ablation import (
    DATASET_PATH,
    evaluate_repeat,
    fit_predict_representation,
    physical_feature_matrix,
    read_model_ready_map,
    read_modelling_rows,
    summarize_repeats,
)

REPOSITORY_ROOT = DATASET_PATH.parents[1]


def _feature_row(status: str = "ok", inchikey: str = "KEY-A") -> dict[str, str]:
    return {
        "status": status,
        "inchikey": inchikey,
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


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.write_text(
        ",".join(columns)
        + "\n"
        + "\n".join(",".join(row[column] for column in columns) for row in rows)
        + "\n",
        encoding="utf-8",
    )


def _roster(path: Path, ready: dict[str, str]) -> None:
    _write_csv(
        path,
        ("inchikey", "model_ready"),
        [{"inchikey": key, "model_ready": value} for key, value in ready.items()],
    )


def test_read_modelling_rows_separates_failed_and_withheld_rows(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    roster_path = tmp_path / "dataset.csv"
    _write_csv(
        features_path,
        tuple(_feature_row()),
        [
            _feature_row("ok", "KEY-A"),
            _feature_row("error", "KEY-B"),
            _feature_row("ok", "KEY-C"),
        ],
    )
    _roster(roster_path, {"KEY-A": "true", "KEY-B": "true", "KEY-C": "false"})

    successful, failed, withheld = read_modelling_rows(
        features_path,
        dataset_path=roster_path,
    )

    assert [row["inchikey"] for row in successful] == ["KEY-A"]
    assert [row["inchikey"] for row in failed] == ["KEY-B"]
    assert [row["inchikey"] for row in withheld] == ["KEY-C"]
    assert physical_feature_matrix(successful).shape == (1, 13)


def test_a_withheld_row_is_never_treated_as_a_feature_failure(tmp_path: Path) -> None:
    # A contested value is withheld for provenance reasons, not because its
    # xTB/descriptor computation failed. Conflating the two would hide it.
    features_path = tmp_path / "features.csv"
    roster_path = tmp_path / "dataset.csv"
    _write_csv(
        features_path,
        tuple(_feature_row()),
        [_feature_row("ok", "KEY-A"), _feature_row("ok", "KEY-C")],
    )
    _roster(roster_path, {"KEY-A": "true", "KEY-C": "false"})

    successful, failed, withheld = read_modelling_rows(
        features_path,
        dataset_path=roster_path,
    )

    assert failed == []
    assert [row["inchikey"] for row in successful] == ["KEY-A"]
    assert len(withheld) == 1


def test_a_feature_row_outside_the_dataset_roster_is_an_error(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    roster_path = tmp_path / "dataset.csv"
    _write_csv(
        features_path,
        tuple(_feature_row()),
        [_feature_row("ok", "KEY-A"), _feature_row("ok", "KEY-UNKNOWN")],
    )
    _roster(roster_path, {"KEY-A": "true"})

    with pytest.raises(ValueError, match="unknown"):
        read_modelling_rows(features_path, dataset_path=roster_path)


def test_shipped_feature_tables_only_hold_known_rows() -> None:
    """Every shipped feature row must resolve to a model_ready status."""

    ready = read_model_ready_map()
    assert len(ready) == 246
    assert sum(1 for value in ready.values() if not value) == 6
    for name in (
        "dielectric_physical_features.csv",
        "dielectric_physical_features_density.csv",
        "dielectric_physical_features_v03.csv",
    ):
        path = REPOSITORY_ROOT / "data" / "processed" / name
        rows, _, withheld = read_modelling_rows(path)
        expected = 1 if name.endswith("v03.csv") else 0
        assert len(withheld) == expected, name
        assert {row["name"] for row in withheld} == (
            {"vinylene carbonate"} if expected else set()
        ), name
        assert rows, name

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
