from __future__ import annotations

import numpy as np
import pytest

from probes.dielectric_split_conformal_probe import (
    ALPHA,
    MIN_CALIBRATION_N,
    _conditional_coverage,
    build_summary,
    conformal_quantile,
    global_calibration_mask,
)


def test_conformal_quantile_returns_inf_when_rank_exceeds_sample() -> None:
    # m = 3, alpha = 0.10 -> k = ceil(4 * 0.9) = 4 > 3, so no finite quantile.
    assert conformal_quantile([1.0, 2.0, 3.0], ALPHA) == float("inf")


@pytest.mark.parametrize("size", [9, 10, 11, 12])
def test_conformal_quantile_is_maximum_at_the_minimum_calibration_size(size: int) -> None:
    scores = [float(value) for value in range(size)]

    assert conformal_quantile(scores, ALPHA) == pytest.approx(float(size - 1))


def test_conformal_quantile_is_the_expected_order_statistic() -> None:
    scores = [float(value) for value in range(20)]
    # m = 20 -> k = ceil(21 * 0.9) = 19 -> the 19th smallest value is 18.
    assert conformal_quantile(scores, ALPHA) == pytest.approx(18.0)


def test_conformal_quantile_rejects_empty_and_bad_alpha() -> None:
    with pytest.raises(ValueError):
        conformal_quantile([], ALPHA)
    with pytest.raises(ValueError):
        conformal_quantile([1.0], 1.5)


def test_min_calibration_n_is_consistent_with_the_order_statistic() -> None:
    # A finite 90% quantile needs m >= 9; m = 8 must fall back to +inf.
    assert conformal_quantile([float(v) for v in range(MIN_CALIBRATION_N)], ALPHA) < float(
        "inf"
    )
    assert conformal_quantile(
        [float(v) for v in range(MIN_CALIBRATION_N - 1)], ALPHA
    ) == float("inf")


def test_global_calibration_mask_is_deterministic_and_a_partition() -> None:
    first = global_calibration_mask(234, rng=np.random.default_rng(1234))
    second = global_calibration_mask(234, rng=np.random.default_rng(1234))

    assert first.shape == (234,)
    assert first.tolist() == second.tolist()
    assert int(first.sum()) == int(np.ceil(234 * 0.5))

    # Re-derive the mask from the documented rule so the check is not circular.
    expected = np.zeros(234, dtype=bool)
    expected[
        np.random.default_rng(1234).permutation(234)[: int(np.ceil(234 * 0.5))]
    ] = True
    assert np.array_equal(first, expected)

    # Calibration and test roles are complementary: no compound lands in both
    # and every compound lands in exactly one of the two.
    complement = ~first
    assert not np.any(first & complement)
    assert np.array_equal(first | complement, np.ones(234, dtype=bool))
    assert int(complement.sum()) == 234 - int(first.sum())


def test_global_calibration_mask_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        global_calibration_mask(0, rng=np.random.default_rng(0))
    with pytest.raises(ValueError):
        global_calibration_mask(10, rng=np.random.default_rng(0), calibration_fraction=1.0)


def test_conditional_coverage_subsets_by_target_range() -> None:
    target = np.asarray([5.0, 10.0, 30.0, 80.0])
    errors = np.asarray([1.0, 1.0, 1.0, 50.0])
    threshold = np.full(4, 2.0)

    assert _conditional_coverage(target, errors, threshold, high=20.0) == pytest.approx(1.0)
    assert _conditional_coverage(
        target, errors, threshold, low=20.0, high=60.0
    ) == pytest.approx(1.0)
    assert _conditional_coverage(target, errors, threshold, low=60.0) == pytest.approx(0.0)
    assert _conditional_coverage(target, errors, threshold, low=1000.0) is None


def test_real_run_keeps_marginal_coverage_and_the_high_epsilon_collapse(tmp_path) -> None:
    payload = build_summary(
        summary_path=tmp_path / "summary.json",
        splits_path=tmp_path / "splits.csv",
        plot_path=tmp_path / "plot.png",
    )

    assert payload["counts"]["compounds"] == 234
    assert payload["counts"]["split_rows"] == 12_000
    assert payload["exchangeability"]["repeat_treated_as_independent"] is False
    assert payload["exchangeability"]["conditional_target_coverage_claimed"] is False
    assert payload["exchangeability"]["target_strata_sizes"] == {
        "lt20": 182,
        "20_60": 47,
        "gt60": 5,
    }

    for summary in payload["series"].values():
        # The finite-sample per-fold quantile is conservative on the margin.
        assert summary["coverage"]["mean"] >= 1.0 - ALPHA
        assert summary["infinite_interval_rate"]["mean"] == pytest.approx(0.0)
        # The honest negative result: conditional coverage collapses above 60.
        assert summary["coverage_gt60"]["mean"] < 1.0 - ALPHA


def test_split_rows_never_pool_calibration_across_folds(tmp_path) -> None:
    import csv

    splits_path = tmp_path / "splits.csv"
    build_summary(
        summary_path=tmp_path / "summary.json",
        splits_path=splits_path,
        plot_path=tmp_path / "plot.png",
    )
    with splits_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    row = rows[0]
    fold_quanta = [row[f"fold{fold}_quantile"] for fold in range(5)]
    # Each fold carries its own finite-sample order statistic.
    assert len(set(fold_quanta)) > 1
    assert int(row["calibration_count"]) == 117
    assert int(row["test_count"]) == 117
