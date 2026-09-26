"""Offline tests for the coverage paired benchmark audit.

Nothing here touches the network and nothing here refits a model. The suite pins
three things:

1. the audit's own arithmetic (average ranks with ties, R2, KS statistic, bitwise
   float comparison) against hand-computed values;
2. the audit's *falsification* paths -- a synthetic prediction table whose widened
   arm equals the base arm must come back as "refuted", and a tampered real
   prediction must break the bit-exact cross-artifact check;
3. the audit's conclusions on the released artifacts, plus byte-level
   reproducibility of the written report and summary through the CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from probes.dielectric_coverage_paired_benchmark_audit import (
    AUDIT_SUMMARY_PATH,
    BASE_PROTOCOL,
    HYBRID,
    LEAK_MARKER,
    LEAK_REFERENCE_PROTOCOL,
    PREDICTIONS_PATH,
    REPEATS_PATH,
    REPORT_PATH,
    SUMMARY_PATH,
    WIDENED_PROTOCOL,
    average_ranks,
    bitwise_equal,
    build_summary,
    check_fold_identity_and_metrics,
    check_leak_reference_framing,
    check_prediction_shift,
    check_prior_shift_alternative,
    check_training_expansion_composition,
    format_report,
    ks_statistic,
    read_predictions,
    regression_metrics,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SOURCE = REPOSITORY_ROOT / "probes" / "dielectric_coverage_paired_benchmark_audit.py"
REPRESENTATIONS = ("Morgan", "Physical", HYBRID)


@pytest.fixture(scope="module")
def audit_summary() -> dict[str, object]:
    return build_summary()


@pytest.fixture(scope="module")
def real_predictions() -> dict:
    return read_predictions(PREDICTIONS_PATH)


@pytest.fixture(scope="module")
def checks_by_name(audit_summary: dict) -> dict:
    return {check["name"]: check for check in audit_summary["checks"]}


@pytest.fixture(scope="module")
def benchmark_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def synthetic_predictions(
    *,
    base_prediction: float,
    widened_prediction: float,
    target: float = 12.0,
    unpaired: bool = False,
) -> dict:
    """A tiny stand-in prediction table with the real column semantics."""

    table: dict = {}
    for protocol, value in (
        (BASE_PROTOCOL, base_prediction),
        (WIDENED_PROTOCOL, widened_prediction),
    ):
        for representation in REPRESENTATIONS:
            folds = {}
            for repeat in range(2):
                for fold in range(2):
                    rows = []
                    for index in range(2):
                        key = "KEY-" + str(fold) + "-" + str(index)
                        if unpaired and protocol == WIDENED_PROTOCOL:
                            key = "OTHER-" + str(fold) + "-" + str(index)
                        rows.append(
                            {
                                "inchikey": key,
                                "T_K": 298.15,
                                "target": target,
                                "prediction": value,
                            }
                        )
                    folds[(repeat, fold)] = rows
            table[protocol + "|" + representation] = folds
    return table


def test_average_ranks_averages_ties() -> None:
    ranks = average_ranks(np.asarray([10.0, 10.0, 20.0]))
    assert list(ranks) == [1.5, 1.5, 3.0]


def test_average_ranks_is_order_independent() -> None:
    values = np.asarray([3.0, 1.0, 3.0, 2.0])
    ranks = average_ranks(values)
    assert ranks[np.argsort(values, kind="mergesort")].tolist() == sorted(ranks.tolist())


def test_regression_metrics_matches_hand_computation() -> None:
    target = np.asarray([1.0, 2.0, 4.0])
    prediction = np.asarray([2.0, 2.0, 2.0])
    metrics = regression_metrics(target, prediction)
    assert metrics["mae"] == pytest.approx(1.0)
    assert metrics["rmse"] == pytest.approx(np.sqrt(5.0 / 3.0))
    ss_tot = float(np.sum((target - target.mean()) ** 2))
    assert metrics["r2"] == pytest.approx(1.0 - 5.0 / ss_tot)


def test_regression_metrics_perfect_prediction() -> None:
    target = np.asarray([1.0, 5.0, 9.0])
    metrics = regression_metrics(target, target.copy())
    assert metrics["r2"] == pytest.approx(1.0)
    assert metrics["mae"] == pytest.approx(0.0)
    assert metrics["spearman"] == pytest.approx(1.0)


def test_spearman_ignores_any_positive_level_or_scale_change() -> None:
    target = np.asarray([1.0, 4.0, 9.0, 16.0])
    prediction = np.asarray([1.5, 3.0, 10.0, 15.0])
    base = regression_metrics(target, prediction)
    shifted = regression_metrics(target, prediction + 25.0)
    scaled = regression_metrics(target, 0.5 * prediction)
    assert shifted["spearman"] == base["spearman"]
    assert scaled["spearman"] == base["spearman"]
    assert shifted["r2"] != base["r2"]
    assert scaled["mae"] != base["mae"]


def test_ks_statistic_extremes() -> None:
    sample = np.asarray([1.0, 2.0, 3.0, 4.0])
    assert ks_statistic(sample, sample.copy()) == pytest.approx(0.0)
    assert ks_statistic(np.asarray([0.0, 0.0]), np.asarray([5.0, 5.0])) == pytest.approx(1.0)


def test_bitwise_equal_separates_neighbouring_floats() -> None:
    assert bitwise_equal(1.0, 1.0)
    assert not bitwise_equal(1.0, 1.0 + 1e-15)
    assert not bitwise_equal(0.1, 0.2)


def test_prediction_shift_is_refuted_when_the_two_arms_are_identical() -> None:
    result = check_prediction_shift(
        synthetic_predictions(base_prediction=10.0, widened_prediction=10.0)
    )
    assert result["verdict"] == "refuted"
    assert result["evidence"]["per_representation"][HYBRID]["changed_cells"] == 0


def test_prediction_shift_is_confirmed_when_every_cell_moves() -> None:
    result = check_prediction_shift(
        synthetic_predictions(base_prediction=10.0, widened_prediction=11.0)
    )
    assert result["verdict"] == "confirmed"
    evidence = result["evidence"]["per_representation"][HYBRID]
    assert evidence["changed_cells"] == evidence["scored_cells_compared"]
    assert evidence["mean_delta"] == pytest.approx(1.0)


def test_prediction_shift_is_refuted_when_the_scored_rows_are_not_paired() -> None:
    result = check_prediction_shift(
        synthetic_predictions(base_prediction=10.0, widened_prediction=11.0, unpaired=True)
    )
    assert result["verdict"] == "refuted"
    assert result["evidence"]["per_representation"][HYBRID]["scored_cells_compared"] == 0


def test_prediction_shift_partial_movement_is_unresolved() -> None:
    table = synthetic_predictions(base_prediction=10.0, widened_prediction=10.0)
    lifted = table[WIDENED_PROTOCOL + "|" + HYBRID]
    rows = lifted[(0, 0)]
    rows[0] = {**rows[0], "prediction": 11.0}
    result = check_prediction_shift(table)
    assert result["verdict"] == "unresolved"


def test_real_shift_is_complete_on_the_hybrid_arm(checks_by_name: dict) -> None:
    evidence = checks_by_name["prediction_shift"]["evidence"]
    hybrid = evidence["per_representation"][HYBRID]
    assert hybrid["scored_cells_compared"] == 4570
    assert hybrid["identity_mismatches"] == 0
    assert hybrid["changed_cells"] == 4570
    assert hybrid["bitwise_identical_cells"] == 0
    assert hybrid["changed_fraction"] == pytest.approx(1.0)
    assert hybrid["repeat_mean_delta_min"] < 0.0 or hybrid["repeat_mean_delta_max"] > 0.0


def test_real_shift_moves_the_morgan_arm_too(checks_by_name: dict) -> None:
    evidence = checks_by_name["prediction_shift"]["evidence"]["per_representation"]
    assert evidence["Morgan"]["changed_cells"] == 4570
    assert evidence["Physical"]["changed_cells"] > 4000


def test_training_expansion_is_exactly_the_new_room_rows(checks_by_name: dict) -> None:
    evidence = checks_by_name["training_expansion_composition"]["evidence"]
    assert evidence["room_rows_after_gate"]["thermoml_zero_frequency"]["rows"] == 457
    assert evidence["room_rows_after_gate"]["thermoml_zero_frequency"]["compounds"] == 97
    assert evidence["room_rows_after_gate"]["thermoml_low_frequency"]["rows"] == 127
    assert evidence["room_rows_after_gate"]["thermoml_low_frequency"]["compounds"] == 50
    assert evidence["room_rows_before_gate"]["thermoml_zero_frequency"]["rows"] == 460
    assert evidence["added_compounds_overlap_scored_compounds"] == []
    assert evidence["added_compounds_with_a_v11_observation"] == []
    assert evidence["added_row_overlap_scored_rows"] == 0


def test_training_expansion_per_fold_is_127_in_all_fifty_folds(checks_by_name: dict) -> None:
    extra = checks_by_name["training_expansion_composition"]["evidence"][
        "extra_train_rows_per_fold"
    ]
    assert extra["folds_compared"] == 50
    assert extra["ambiguous_folds"] == 0
    assert extra["mean"] == pytest.approx(127.0)
    assert extra["min"] == 127
    assert extra["max"] == 127
    assert extra["total"] == 6350


def test_training_expansion_reads_the_same_pool_as_the_check_itself() -> None:
    result = check_training_expansion_composition()
    assert result["verdict"] == "confirmed"
    assert result["evidence"]["room_rows_after_gate"]["rows_total"] == 584


def test_prior_shift_verdict_and_distribution_gap(checks_by_name: dict) -> None:
    evidence = checks_by_name["prior_shift_alternative"]["evidence"]
    assert evidence["added_block_looks_same_distribution"] is False
    assert evidence["permutation_tests"]["ks_statistic"] > 0.25
    assert evidence["permutation_tests"]["ks_p_value"] < 0.01
    assert evidence["permutation_tests"]["mean_gap_added_minus_scored"] < -8.0
    assert evidence["scored_pool_targets"]["rows"] == 457
    assert evidence["added_train_targets"]["rows"] == 127
    assert evidence["added_train_targets"]["rows_above_60"] < evidence["scored_pool_targets"]["rows_above_60"]


def test_prior_shift_rank_invariance_holds_on_the_real_predictions(checks_by_name: dict) -> None:
    demonstration = checks_by_name["prior_shift_alternative"]["evidence"][
        "rank_invariance_demonstration"
    ]
    assert demonstration["spearman_after_adding_25"] == demonstration["spearman_base"]
    assert demonstration["spearman_after_scaling_by_0_5"] == demonstration["spearman_base"]
    assert demonstration["r2_after_adding_25"] < demonstration["r2_base"]


def test_prior_shift_movement_is_not_a_shrink_towards_the_pool_mean(checks_by_name: dict) -> None:
    correlations = checks_by_name["prior_shift_alternative"]["evidence"][
        "delta_attribution_correlations"
    ]
    assert abs(correlations["corr_delta_with_shrinkage_direction"]) < 0.05
    assert (
        correlations["partial_corr_delta_with_target_deviation_controlling_shrinkage"] > 0.4
    )


def test_prior_shift_improvement_is_broad_not_single_compound(checks_by_name: dict) -> None:
    breadth = checks_by_name["prior_shift_alternative"]["evidence"]["improvement_breadth"]
    assert breadth["scored_compounds"] == 97
    assert breadth["compounds_with_lower_mean_abs_error"] > 50
    assert breadth["share_of_scored_rows_with_lower_abs_error"] > 0.5


def test_prior_shift_spearman_gain_is_the_per_repeat_one(checks_by_name: dict) -> None:
    change = checks_by_name["prior_shift_alternative"]["evidence"]["observed_metric_change"]
    assert change["spearman"] == pytest.approx(0.1080996482295582, abs=1e-12)
    assert change["spearman_pooled_4570"] == pytest.approx(0.10637476931160739, abs=1e-12)
    assert change["r2"] == pytest.approx(0.1240864496977292, abs=1e-12)


def test_prior_shift_check_reruns_to_the_same_verdict(real_predictions: dict) -> None:
    result = check_prior_shift_alternative(real_predictions)
    assert result["verdict"] == "confirmed"


def test_fold_identity_is_bit_exact_on_the_real_artifacts(checks_by_name: dict) -> None:
    evidence = checks_by_name["fold_identity_and_metrics"]["evidence"]
    assert evidence["identity_mismatch_cells"] == 0
    assert evidence["shared_repeat_fold_cells"] == 50
    assert evidence["scored_rows_total_over_repeats"] == 4570
    assert evidence["max_metric_abs_delta"] == 0.0
    assert evidence["cross_artifact_band_room_only"]["bitwise_prediction_differences"] == 0
    assert evidence["cross_artifact_band_room_only"]["cells_compared"] == 4570
    assert evidence["merged_v11_block"]["order_identical"] is True
    assert evidence["merged_v11_block"]["set_identical"] is True
    assert evidence["declared_sha256_matches"] is True


def test_fold_identity_detects_a_tampered_prediction(
    real_predictions: dict, benchmark_summary: dict
) -> None:
    import copy

    tampered = copy.deepcopy(real_predictions)
    folds = tampered[BASE_PROTOCOL + "|" + HYBRID]
    first_key = min(folds)
    rows = folds[first_key]
    rows[0] = {**rows[0], "prediction": float(rows[0]["prediction"]) + 1.0}
    result = check_fold_identity_and_metrics(tampered, benchmark_summary)
    assert result["verdict"] == "refuted"


def test_fold_identity_detects_a_moved_scored_row(
    real_predictions: dict, benchmark_summary: dict
) -> None:
    import copy

    tampered = copy.deepcopy(real_predictions)
    folds = tampered[WIDENED_PROTOCOL + "|" + HYBRID]
    first_key = min(folds)
    rows = folds[first_key]
    rows[0] = {**rows[0], "inchikey": "ZZZZZZZZZZZZZZ-ZZZZZZZZZZ-Z"}
    result = check_fold_identity_and_metrics(tampered, benchmark_summary)
    assert result["verdict"] == "refuted"
    assert result["evidence"]["identity_mismatch_cells"] >= 1


def test_leak_reference_is_contained(checks_by_name: dict) -> None:
    check = checks_by_name["leak_reference_framing"]
    assert check["verdict"] == "confirmed"
    evidence = check["evidence"]
    assert "LEAK REFERENCE ONLY" in evidence["leak_protocol_description"]
    assert "same rows as extended_pool_room" in evidence["leak_protocol_description"]
    assert "never a conclusion number" in evidence["leak_block_note"]
    assert evidence["chain_mentions_the_leak_protocol"] is False
    assert evidence["verdict_mentions_the_leak_protocol"] is False
    assert evidence["report_unlabelled_lines_with_0_6748"] == 0
    assert evidence["report_unlabelled_lines_strict_rule"] == 1


def test_leak_reference_check_reruns_clean() -> None:
    result = check_leak_reference_framing()
    assert result["verdict"] == "confirmed"
    assert result["evidence"]["leak_reference_r2"] > result["evidence"]["grouped_comparison_r2"]


def test_leak_protocol_never_appears_in_the_fixed_pool_chain(benchmark_summary: dict) -> None:
    chain = json.dumps(benchmark_summary["fixed_pool_family"]["chain"], ensure_ascii=False)
    assert LEAK_MARKER not in chain
    assert LEAK_REFERENCE_PROTOCOL not in chain
    assert len(benchmark_summary["fixed_pool_family"]["chain"]) == 3


def test_every_check_is_confirmed_and_none_is_refuted(audit_summary: dict) -> None:
    assert audit_summary["tally"] == {"confirmed": 5, "refuted": 0, "unresolved": 0}
    assert audit_summary["verdict"] == {
        "headline_reproduces": True,
        "training_really_widened": True,
        "prior_shift_alternative": "confirmed",
        "leak_reference_contained": True,
    }


def test_check_names_and_contract(audit_summary: dict) -> None:
    names = [check["name"] for check in audit_summary["checks"]]
    assert names == [
        "prediction_shift",
        "training_expansion_composition",
        "prior_shift_alternative",
        "fold_identity_and_metrics",
        "leak_reference_framing",
    ]
    for check in audit_summary["checks"]:
        assert check["verdict"] in {"confirmed", "refuted", "unresolved"}
        assert check["claim"]
        assert check["note"]
        assert isinstance(check["evidence"], dict)
        assert json.dumps(check["evidence"], ensure_ascii=False)


def test_summary_declares_its_read_only_offline_nature(audit_summary: dict) -> None:
    assert audit_summary["no_network"] is True
    assert audit_summary["read_only"] is True
    assert audit_summary["schema_version"] == 1
    assert audit_summary["seed"] == 42


def test_report_has_the_three_required_lists(audit_summary: dict) -> None:
    text = "\n".join(format_report(audit_summary))
    assert "### 被证伪" in text
    assert "### 被确认" in text
    assert "### 仍存疑" in text
    assert "## 1. 预测真的变了吗" in text
    assert "## 5. 行级随机折有没有被当成结论" in text
    assert "4570/4570" in text


def test_report_and_summary_files_are_lf_only(audit_summary: dict) -> None:
    report = REPORT_PATH.read_bytes()
    payload = AUDIT_SUMMARY_PATH.read_bytes()
    assert b"\r\n" not in report
    assert b"\r\n" not in payload
    assert json.loads(payload.decode("utf-8"))["tally"]["refuted"] == 0


def test_repeats_csv_is_only_read_for_metrics() -> None:
    assert REPEATS_PATH.is_file()
    header = REPEATS_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("protocol,representation,repeat,r2,mae,rmse,spearman")


def test_cli_run_is_byte_reproducible(tmp_path: Path) -> None:
    report = tmp_path / "audit.md"
    summary = tmp_path / "audit.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(AUDIT_SOURCE),
            "--quiet",
            "--report",
            str(report),
            "--summary-out",
            str(summary),
        ],
        cwd=str(REPOSITORY_ROOT),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert report.read_text(encoding="utf-8") == REPORT_PATH.read_text(encoding="utf-8")
    assert summary.read_text(encoding="utf-8") == AUDIT_SUMMARY_PATH.read_text(encoding="utf-8")


def test_audit_never_imports_the_module_it_audits() -> None:
    source = AUDIT_SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "import dielectric_coverage_paired_benchmark\n",
        "from dielectric_coverage_paired_benchmark import",
        "from probes.dielectric_coverage_paired_benchmark import",
        "import requests",
        "import urllib",
        "import socket",
        "import sklearn",
        "import xgboost",
    )
    for needle in forbidden:
        assert needle not in source, needle


def test_audit_has_no_network_or_model_fit_calls() -> None:
    source = AUDIT_SOURCE.read_text(encoding="utf-8")
    for needle in ("urlopen", "requests.get", "http://", "https://", ".fit(", "XGBRegressor"):
        assert needle not in source, needle
