"""Guards for the P4 redox v2 enriched-feature probe and its artifacts.

These tests do not re-run the 5x10 CV grid (that is minutes of compute); they
pin the frozen anchors, the gate contract, the fold-grid bookkeeping, the
label-leakage boundary and the honesty of the reported verdict against the
committed artifacts.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import pytest

from probes.p4_redox_baseline import GATE_MAE_THRESHOLD as V1_GATE_MAE_THRESHOLD
from probes.p4_redox_v2_enriched import (
    FOLD_COLUMNS,
    FORBIDDEN_FEATURE_NAMES,
    FORBIDDEN_FEATURE_SUBSTRING,
    GATE_CANDIDATE_MODELS,
    GATE_MAE_THRESHOLD,
    LABEL_COLUMNS,
    MODEL_NAMES,
    PREDICTION_COLUMNS,
    TARGETS,
    _index_hash,
    assert_no_label_leakage,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "p4_redox_v2_summary.json"
V1_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "p4_redox_summary.json"
FOLDS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_repeated_cv.csv"
PREDICTIONS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_predictions.csv"
LEARNING_CURVE_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_learning_curve.csv"
)
PROBE_PATH = REPOSITORY_ROOT / "probes" / "p4_redox_v2_enriched.py"

ARTIFACT_PATHS = (SUMMARY_PATH, FOLDS_PATH, PREDICTIONS_PATH, LEARNING_CURVE_PATH, PROBE_PATH)

EXPECTED_TEST_ID_HASH = "dba15cd8c3a99215cc3e1fd5b2a73b9a5c0275eb2ee41fba436bcf62f2d2daee"
EXPECTED_V1_OXIDATION_LINEAR_MAE = 0.2905180517963865
EXPECTED_V1_OXIDATION_LINEAR_R2 = 0.9443164629360373
PINNED_GATE_THRESHOLD = 0.15
REQUIRED_FOLD_COLUMNS = (
    "model",
    "target",
    "seed",
    "repeat",
    "fold",
    "n_train",
    "n_test",
    "train_id_hash",
    "test_id_hash",
    "mae",
    "rmse",
    "r2",
)
REQUIRED_PREDICTION_COLUMNS = (
    "row_id",
    "target",
    "model",
    "split",
    "repeat",
    "fold",
    "used_for_metrics",
    "target_value",
    "prediction",
    "abs_error",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v1_summary() -> dict:
    return json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fold_rows() -> list[dict[str, str]]:
    return _read_csv(FOLDS_PATH)


@pytest.fixture(scope="module")
def prediction_rows() -> list[dict[str, str]]:
    return _read_csv(PREDICTIONS_PATH)


@pytest.fixture(scope="module")
def learning_rows() -> list[dict[str, str]]:
    return _read_csv(LEARNING_CURVE_PATH)


def test_v1_anchor_summary_is_untouched(v1_summary: dict) -> None:
    """The frozen v1 artifacts must still read exactly as they did before v2."""

    assert v1_summary["gate"]["passed"] is False
    assert v1_summary["gate"]["threshold_mae"] == PINNED_GATE_THRESHOLD
    assert v1_summary["gate"]["best_model_mae"] == {
        "oxidation_free_energy": EXPECTED_V1_OXIDATION_LINEAR_MAE,
        "reduction_free_energy": 0.4096241620366996,
    }
    assert v1_summary["split"]["test_id_hash"] == EXPECTED_TEST_ID_HASH


def test_anchor_reproduces_v1_oxidation_linear(summary: dict, v1_summary: dict) -> None:
    anchors = summary["anchors"]
    assert anchors["matches"] is True
    assert anchors["tolerance"] <= 1e-9
    reproduced = anchors["reproduced_v1_oxidation_linear"]
    assert abs(reproduced["mae"] - EXPECTED_V1_OXIDATION_LINEAR_MAE) <= 1e-9
    assert abs(reproduced["r2"] - EXPECTED_V1_OXIDATION_LINEAR_R2) <= 1e-9
    v1_metrics = v1_summary["metrics"]["oxidation_free_energy"]["linear"]
    assert abs(reproduced["mae"] - v1_metrics["mae"]) <= 1e-9
    assert abs(reproduced["r2"] - v1_metrics["r2"]) <= 1e-9


def test_heldout_split_is_314_78_with_frozen_hash(summary: dict) -> None:
    split = summary["split"]
    assert split["seed"] == 42
    assert split["test_fraction"] == 0.2
    assert split["train_count"] == 314
    assert split["test_count"] == 78
    assert split["test_id_hash"] == EXPECTED_TEST_ID_HASH
    assert summary["anchors"]["reproduced_test_id_hash"] == EXPECTED_TEST_ID_HASH


def test_predictions_recompute_the_frozen_heldout_hash(prediction_rows: list[dict[str, str]]) -> None:
    """Re-derive the 78-row held-out id hash from the predictions CSV alone.

    ``_index_hash`` joins the ids in ascending *dataset index* order, and the
    predictions CSV emits each ``(target, model)`` block in that same order, so
    the collected ids must not be re-sorted.
    """

    for target in TARGETS:
        for model in MODEL_NAMES:
            row_ids = [
                row["row_id"]
                for row in prediction_rows
                if row["target"] == target and row["model"] == model and row["split"] == "heldout_test"
            ]
            assert len(row_ids) == 78
            assert _index_hash(row_ids, range(len(row_ids))) == EXPECTED_TEST_ID_HASH


def test_gate_threshold_is_still_015_and_matches_v1(summary: dict, v1_summary: dict) -> None:
    assert GATE_MAE_THRESHOLD == PINNED_GATE_THRESHOLD
    assert V1_GATE_MAE_THRESHOLD == PINNED_GATE_THRESHOLD
    assert summary["gate"]["threshold_mae"] == PINNED_GATE_THRESHOLD
    assert summary["gate"]["unit"] == "eV"
    assert summary["gate"]["threshold_mae"] == v1_summary["gate"]["threshold_mae"]
    assert summary["gate_repeated_cv"]["threshold_mae"] == PINNED_GATE_THRESHOLD


def test_gate_keeps_the_v1_key_contract(summary: dict, v1_summary: dict) -> None:
    for key in ("threshold_mae", "unit", "criterion", "best_model_mae", "passed"):
        assert key in summary["gate"]
    assert summary["gate"]["criterion"] == v1_summary["gate"]["criterion"]
    per_target = summary["gate"]["per_target"]
    assert set(per_target) == set(TARGETS)
    for target in TARGETS:
        assert set(per_target[target]) == {"mae", "passed"}
        assert per_target[target]["passed"] is (
            per_target[target]["mae"] < PINNED_GATE_THRESHOLD
        )


def test_gate_best_model_mae_is_the_heldout_minimum(summary: dict) -> None:
    heldout = summary["heldout"]["metrics"]
    for target in TARGETS:
        assert summary["gate"]["best_model"][target] in GATE_CANDIDATE_MODELS
        expected_best = min(GATE_CANDIDATE_MODELS, key=lambda name: heldout[target][name]["mae"])
        assert summary["gate"]["best_model"][target] == expected_best
        assert (
            abs(summary["gate"]["best_model_mae"][target] - heldout[target][expected_best]["mae"])
            <= 1e-12
        )


def test_gate_passed_is_the_conjunction_of_per_target(summary: dict) -> None:
    per_target = summary["gate"]["per_target"]
    assert summary["gate"]["passed"] is all(per_target[target]["passed"] for target in TARGETS)
    assert summary["verdict"]["gate_passed"] is summary["gate"]["passed"]
    cv_per_target = summary["gate_repeated_cv"]["per_target"]
    assert summary["gate_repeated_cv"]["passed"] is all(
        cv_per_target[target]["passed"] for target in TARGETS
    )

def test_fold_record_columns_match_the_project_standard(
    fold_rows: list[dict[str, str]],
) -> None:
    assert list(fold_rows[0]) == list(FOLD_COLUMNS)
    assert FOLD_COLUMNS == REQUIRED_FOLD_COLUMNS


def test_dummy_control_shares_every_fold(fold_rows: list[dict[str, str]]) -> None:
    grouped: dict[tuple[str, str, str], dict[str, tuple[str, str]]] = {}
    for row in fold_rows:
        key = (row["target"], row["repeat"], row["fold"])
        grouped.setdefault(key, {})[row["model"]] = (row["train_id_hash"], row["test_id_hash"])
    assert grouped, "fold records must not be empty"
    for key, per_model in grouped.items():
        assert set(per_model) == set(MODEL_NAMES), key
        assert len(set(per_model.values())) == 1, (key, per_model)


def test_dummy_is_never_a_gate_candidate(summary: dict) -> None:
    assert "dummy_mean" not in GATE_CANDIDATE_MODELS
    assert set(MODEL_NAMES) - set(GATE_CANDIDATE_MODELS) == {"dummy_mean"}
    assert "dummy_mean" not in set(summary["gate"]["best_model"].values())
    assert "dummy_mean" not in set(summary["gate_repeated_cv"]["best_model"].values())
    assert summary["dummy_control"]["shared_folds"] is True
    for target in TARGETS:
        dummy_mae = summary["dummy_control"]["repeated_cv_mae"][target]
        assert dummy_mae > summary["gate_repeated_cv"]["best_model_mae"][target]


def test_fold_grid_is_complete(fold_rows: list[dict[str, str]]) -> None:
    assert len(fold_rows) == len(MODEL_NAMES) * len(TARGETS) * 50
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in fold_rows:
        grouped.setdefault((row["model"], row["target"]), []).append(row)
    assert set(grouped) == {(model, target) for model in MODEL_NAMES for target in TARGETS}
    for key, rows in grouped.items():
        assert len(rows) == 50, key
        assert {(int(row["repeat"]), int(row["fold"])) for row in rows} == {
            (repeat, fold) for repeat in range(10) for fold in range(5)
        }
        for row in rows:
            assert int(row["n_train"]) + int(row["n_test"]) == 392
            assert 78 <= int(row["n_test"]) <= 79
            assert int(row["seed"]) == 42 + int(row["repeat"]) * 5 + int(row["fold"])


def test_cv_summary_matches_the_fold_records(summary: dict, fold_rows: list[dict[str, str]]) -> None:
    for target in TARGETS:
        for model in MODEL_NAMES:
            values = [
                float(row["mae"])
                for row in fold_rows
                if row["target"] == target and row["model"] == model
            ]
            assert len(values) == 50
            metrics = summary["repeated_cv"]["metrics"][target][model]
            assert abs(metrics["fold_mae_mean"] - statistics.fmean(values)) <= 1e-9
            assert abs(metrics["fold_mae_std"] - statistics.stdev(values)) <= 1e-9


def test_cv_repeat_means_match_the_pooled_predictions(
    summary: dict, prediction_rows: list[dict[str, str]]
) -> None:
    pooled: dict[tuple[str, str, int], list[float]] = {}
    for row in prediction_rows:
        if row["split"] != "cv_test":
            continue
        key = (row["target"], row["model"], int(row["repeat"]))
        pooled.setdefault(key, []).append(float(row["abs_error"]))
    for target in TARGETS:
        for model in MODEL_NAMES:
            repeat_means = [
                statistics.fmean(pooled[(target, model, repeat)]) for repeat in range(10)
            ]
            for repeat in range(10):
                assert len(pooled[(target, model, repeat)]) == 392
            metrics = summary["repeated_cv"]["metrics"][target][model]
            assert abs(metrics["mae_mean"] - statistics.fmean(repeat_means)) <= 1e-9
            assert abs(metrics["mae_std"] - statistics.stdev(repeat_means)) <= 1e-9

def test_feature_names_carry_no_label_derivative(summary: dict) -> None:
    features = summary["features"]
    assert features["leakage_guard"] == "passed"
    names = features["feature_names"]
    assert len(names) == len(set(names)), "feature names must be unique"
    assert features["views"]["enriched"]["count"] == len(names)
    for name in names:
        assert FORBIDDEN_FEATURE_SUBSTRING not in name, name
        assert name not in FORBIDDEN_FEATURE_NAMES, name
        assert name not in LABEL_COLUMNS, name


def test_feature_groups_only_use_allowed_sources(summary: dict) -> None:
    groups = summary["features"]["groups"]
    assert groups["pre_registered"] == ["IP", "EA"]
    assert groups["low_order_interactions"] == ["IP_times_EA", "IP_squared", "EA_squared"]
    assert groups["rdkit_2d"] == [
        "MolWt",
        "TPSA",
        "MolLogP",
        "RingCount",
        "NumHDonors",
        "NumHAcceptors",
        "NumRotatableBonds",
        "FractionCSP3",
    ]
    assert summary["inputs"]["label_columns"] == list(LABEL_COLUMNS)
    assert summary["inputs"]["source_filter"] == "RX-392"
    assert summary["inputs"]["rows"] == 392


def test_label_leakage_guard_rejects_derived_names() -> None:
    for bad in (
        "oxidation_free_energy",
        "reduction_free_energy",
        "ox_plus_red",
        "ox_minus_red",
        "sum_free_energy",
        "delta_free_energy",
        "oxidation_free_energy_minus_IP",
    ):
        with pytest.raises(ValueError):
            assert_no_label_leakage(["IP", bad])
    assert_no_label_leakage(["IP", "EA", "IP_times_EA", "MolWt", "morgan_17"])


def test_predictions_columns_and_split_counts(prediction_rows: list[dict[str, str]]) -> None:
    assert PREDICTION_COLUMNS == REQUIRED_PREDICTION_COLUMNS
    assert list(prediction_rows[0]) == list(PREDICTION_COLUMNS)
    assert "row_id" in REQUIRED_PREDICTION_COLUMNS
    assert "target_value" in REQUIRED_PREDICTION_COLUMNS
    expected = {
        "heldout_train": 314,
        "heldout_test": 78,
        "cv_test": 3920,
    }
    for target in TARGETS:
        for model in MODEL_NAMES:
            for split, count in expected.items():
                observed = sum(
                    1
                    for row in prediction_rows
                    if row["target"] == target and row["model"] == model and row["split"] == split
                )
                assert observed == count, (target, model, split, observed)


def test_predictions_rebuild_the_heldout_metrics(
    summary: dict, prediction_rows: list[dict[str, str]]
) -> None:
    for target in TARGETS:
        for model in MODEL_NAMES:
            errors = [
                abs(float(row["target_value"]) - float(row["prediction"]))
                for row in prediction_rows
                if row["target"] == target and row["model"] == model and row["split"] == "heldout_test"
            ]
            assert len(errors) == 78
            heldout_mae = summary["heldout"]["metrics"][target][model]["mae"]
            assert abs(statistics.fmean(errors) - heldout_mae) <= 1e-9, (target, model)


def test_prediction_abs_error_is_internally_consistent(
    prediction_rows: list[dict[str, str]],
) -> None:
    sampled = prediction_rows[::1501]
    assert len(sampled) > 20
    for row in sampled:
        recomputed = abs(float(row["target_value"]) - float(row["prediction"]))
        assert abs(recomputed - float(row["abs_error"])) <= 1e-6, row


def test_train_residual_proves_capacity_is_not_the_bottleneck(summary: dict) -> None:
    residuals = summary["heldout"]["train_residual_mae"]
    for target in TARGETS:
        assert set(residuals[target]) == {
            "linear_scalar",
            "ridge_enriched",
            "gpr_enriched",
            "xgb_enriched",
        }
        assert residuals[target]["xgb_enriched"] < PINNED_GATE_THRESHOLD
        assert min(residuals[target].values()) < PINNED_GATE_THRESHOLD
        best_heldout = summary["gate"]["best_model_mae"][target]
        assert best_heldout > 2.0 * residuals[target]["xgb_enriched"], target


def test_verdict_is_honest_about_the_red_gate(summary: dict) -> None:
    verdict = summary["verdict"]
    assert verdict["gate_passed"] is False
    assert verdict["gate_passed_repeated_cv"] is False
    assert "sample_size" in verdict["bottleneck"]
    for target in TARGETS:
        assert summary["gate"]["per_target"][target]["passed"] is False
        assert summary["gate"]["per_target"][target]["mae"] > PINNED_GATE_THRESHOLD
        assert summary["gate_repeated_cv"]["per_target"][target]["mae"] > PINNED_GATE_THRESHOLD


def test_enriched_beats_the_single_feature_baseline_in_cv(summary: dict) -> None:
    cv = summary["repeated_cv"]["metrics"]
    for target in TARGETS:
        single = cv[target]["linear_scalar"]["mae_mean"]
        best = min(GATE_CANDIDATE_MODELS, key=lambda name: cv[target][name]["mae_mean"])
        assert cv[target][best]["mae_mean"] < single, target
        assert cv[target][best]["mae_mean"] < 0.85 * single, target
        assert cv[target]["xgb_structure_only"]["mae_mean"] > cv[target]["xgb_enriched"]["mae_mean"]


def test_learning_curve_covers_the_declared_grid(
    summary: dict, learning_rows: list[dict[str, str]]
) -> None:
    curve = summary["learning_curve"]
    assert curve["sizes"] == [100, 200, 300, 392]
    assert set(curve["summary"]) == set(TARGETS)
    for target in TARGETS:
        entries = curve["summary"][target]
        assert {(entry["model"], entry["train_size"]) for entry in entries} == {
            (model, size) for model in ("linear_scalar", "xgb_enriched") for size in (100, 200, 300, 392)
        }
    grouped: dict[tuple[str, str, str], int] = {}
    for row in learning_rows:
        key = (row["model"], row["target"], row["train_size"])
        grouped[key] = grouped.get(key, 0) + 1
    assert set(grouped.values()) == {15}
    for target in TARGETS:
        xgb_curve = {
            entry["train_size"]: entry["mae_mean"]
            for entry in curve["summary"][target]
            if entry["model"] == "xgb_enriched"
        }
        assert xgb_curve[392] < xgb_curve[100], target


def test_artifacts_are_lf_terminated() -> None:
    for path in ARTIFACT_PATHS:
        payload = path.read_bytes()
        assert b"\r" not in payload, path.as_posix()