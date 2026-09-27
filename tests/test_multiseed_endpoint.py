"""Regression tests for the Week 18 P1 multi-seed endpoint probe.

The endpoint definition is the whole point of this lane, so the pinned literals
are the four registered Week 13/14 merge readings.  The pool assertions are a
regression guard for a defect found while this lane was first run: the probe
originally trained on the 2029-row full table (the shot-13 configuration, whose
hybrid reads 0.530028742596643) while claiming to reproduce the four scored-pool
anchors, so seed 42 printed 0.530029 for `baseline` and the whole sweep would have
been thrown away after hours of fitting.  `pool.training_rows == 457` is what makes
that mistake impossible to reintroduce silently.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from probes.dielectric_multiseed_endpoint import (
    ANCHOR_SEED,
    ANCHOR_TOLERANCE,
    ARMS,
    FROZEN_BASELINE,
    FROZEN_HEADLINE,
    PREREG_PATH,
    SEED_42_ANCHORS,
    SEEDS,
    SUMMARY_PATH,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

REGISTERED_ANCHORS = {
    "baseline": 0.4091179943351143,
    "plus_lever4": 0.4649564468823552,
    "plus_lever8": 0.4531768105508106,
    "plus_both": 0.4766400383507876,
}


PREREG_SHA256 = "3516befd25cf6ff9258f1d1d678786915504ac5a6c0fbd5529b75514a2313083"


def test_the_endpoint_is_the_pre_locked_five_seed_mean() -> None:
    assert SEEDS == (42, 1234, 2026, 31337, 7)
    assert ANCHOR_SEED == 42
    assert ARMS == ("baseline", "plus_lever4", "plus_lever8", "plus_both")


def test_the_pinned_anchors_are_the_registered_merge_readings() -> None:
    assert SEED_42_ANCHORS == REGISTERED_ANCHORS
    assert FROZEN_BASELINE == 0.4091179943351143
    assert FROZEN_HEADLINE == 0.4766400383507876


def test_the_preregistration_is_locked_before_the_run() -> None:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    assert tuple(int(seed) for seed in payload["seeds"]) == SEEDS
    assert tuple(str(arm) for arm in payload["arms"]) == ARMS
    frozen_side = payload["frozen_side"]
    assert float(frozen_side["baseline_unchanged"]) == FROZEN_BASELINE
    assert float(frozen_side["headline_unchanged"]) == FROZEN_HEADLINE
    assert {str(k): float(v) for k, v in payload["seed_42_anchors"].items()} == SEED_42_ANCHORS


@pytest.fixture(scope="module")
def summary() -> dict:
    if not SUMMARY_PATH.is_file():
        pytest.skip("the lane has not been run yet; no summary to audit")
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_the_pool_is_the_scored_one_and_not_the_full_table(summary: dict) -> None:
    assert int(summary["pool"]["scored_rows"]) == 457
    assert int(summary["pool"]["scored_compounds"]) == 97
    assert int(summary["pool"]["training_rows"]) == 457
    assert int(summary["pool"]["training_rows"]) != 2029


def test_the_seed_42_anchors_reproduce_bit_for_bit(summary: dict) -> None:
    anchors = summary["anchors"]
    assert bool(anchors["reproduced"]) is True
    assert float(anchors["tolerance"]) == ANCHOR_TOLERANCE
    for row in anchors["rows"]:
        assert bool(row["ok"]), row
        assert float(row["abs_gap"]) <= ANCHOR_TOLERANCE
        assert float(row["measured"]) == pytest.approx(REGISTERED_ANCHORS[str(row["arm"])], abs=0.0)


def test_no_scored_compound_straddles_a_fold(summary: dict) -> None:
    leakage = summary["leakage"]
    assert bool(leakage["clean"]) is True
    for block in leakage["by_seed_arm"].values():
        assert int(block["folds_with_a_straddling_compound"]) == 0
        assert int(block["max_straddling_compounds_in_a_fold"]) == 0


def test_every_arm_reports_a_five_seed_endpoint(summary: dict) -> None:
    endpoints = {str(row["arm"]): row for row in summary["endpoints"]}
    assert sorted(endpoints) == sorted(ARMS)
    for arm, row in endpoints.items():
        assert sorted(row["seed_values"]) == sorted(str(seed) for seed in SEEDS)
        values = np.asarray([float(row["seed_values"][str(seed)]) for seed in SEEDS])
        assert float(row["cross_seed_mean"]) == pytest.approx(float(values.mean()), abs=1e-12)
        assert float(row["cross_seed_min"]) == pytest.approx(float(values.min()), abs=1e-12)
        assert float(row["cross_seed_max"]) == pytest.approx(float(values.max()), abs=1e-12)
        assert float(row["seed_42"]) == pytest.approx(REGISTERED_ANCHORS[arm], abs=0.0)


def test_the_lane_promotes_nothing(summary: dict) -> None:
    assert bool(summary["promotion"]["promoted"]) is False
    assert float(summary["frozen_headline_unchanged_r2"]) == FROZEN_HEADLINE
    assert float(summary["frozen_baseline_unchanged_r2"]) == FROZEN_BASELINE
    assert float(summary["target_r2"]) == 0.6


def test_the_endpoint_is_reported_as_above_or_below_the_target(summary: dict) -> None:
    best = summary["best_arm"]
    assert str(best["arm"]) in ARMS
    flag = bool(summary["target_met_cross_seed"])
    assert flag == (float(best["cross_seed_mean"]) > 0.60)


def test_the_preregistration_bytes_are_pinned_by_sha256() -> None:
    # Gate B: a later edit to any pre-registration field, registered or not,
    # moves the digest and turns this test red.  The sample file for the
    # pattern is tests/test_unimol_embedding.py.
    raw = PREREG_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "the pre-registration carries a BOM"
    assert raw.count(b"\r\n") == 0, "the pre-registration is not LF-only"
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert payload["status"] == "locked_before_run"


def test_every_seed_arm_pair_covers_all_fifty_folds(summary: dict) -> None:
    # Gate A: the fold count is recorded per (seed, arm) inside the leakage
    # block (v1.evaluate_arm -> "leak" -> "folds"), so the gate is per
    # (seed, arm) and not per seed.  drop_thin_folds can silently drop a fold;
    # that would shrink `folds` below 50 and is caught here, whereas the
    # existing straddling gate cannot see a fold that never ran.
    by_seed_arm = summary["leakage"]["by_seed_arm"]
    assert set(by_seed_arm) == {
        str(seed) + "/" + arm for seed in SEEDS for arm in ARMS
    }
    for key, block in by_seed_arm.items():
        assert int(block["folds"]) == 50, key
