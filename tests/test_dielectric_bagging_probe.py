"""Guards for the lever-7 bagging probe.

These tests pin what makes the lever auditable rather than self-serving:

* the ensemble width and the bag-seed rule are the literals frozen in the
  pre-registration, read from the file rather than restated from memory;
* the bagged prediction really is the mean of `n_bags` independently seeded
  members - re-derived here with `XGBRegressor` directly, not with the probe's
  own helper;
* bagging is not a no-op: the ensemble differs from a single member;
* the non-negativity clip is applied *after* the averaging, not per member;
* the main scoreboard is re-derived from the frozen tables - 457 scored rows of
  97 compounds - instead of being trusted to the summary;
* **the three arms are scored on one shared fold assignment**, and that guard is
  not vacuous: the same comparison is shown to *fail* when the fold-dealing seed
  moves, and the fold count and row coverage are asserted so an empty or
  single-fold comparison cannot pass;
* the baseline arm reproduced the published number, and the verdict never claims
  a pass the pre-registered criterion would not grant;
* the report file is byte-identical to what the summary renders;
* every artifact is LF-only.
"""

from __future__ import annotations

import copy
import csv
import json
import pathlib
import sys
from collections import defaultdict

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_bagging_probe as probe
import numpy as np
from dielectric_band_ablation import ROOM_BAND, drop_thin_folds, effective_repeats
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_observations_grouped_benchmark import build_matrices
from dielectric_representation_ablation import XGB_PARAMS
from dielectric_room_window_paired import masked_splits, scored_fold_signature
from xgboost import XGBRegressor

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_bagging_probe_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_bagging_probe.md"
PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_bagging_predictions.csv"
)

#: The frozen red lines this probe may never move.
FROZEN_DIGESTS = {
    REPOSITORY_ROOT / "data" / "dielectric_v03.csv": (
        "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
    ),
    REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv": (
        "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
    ),
    REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json": (
        "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
    ),
    REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json": (
        "212ec2493dcaf4b757ea6a25295890b7144694191f49aeee4b8bba8bfec272d7"
    ),
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv": (
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
    ),
}


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg_lever(prereg: dict) -> dict:
    blocks = [block for block in prereg["levers"] if block["id"] == probe.LEVER_ID]
    assert len(blocks) == 1
    return blocks[0]


@pytest.fixture(scope="module")
def summary() -> dict:
    assert SUMMARY_PATH.is_file(), "run probes/dielectric_bagging_probe.py first"
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scoreboard() -> dict:
    """The main scoreboard re-derived from the frozen tables, once per module."""

    merged, _report = merge_feature_blocks()
    rows, _dropped = load_coverage_table(COVERAGE_PATH, merged)
    _morgan, _physical, _target, _temperatures, groups = build_matrices(rows)
    origin = np.asarray([str(row["observation_origin"]) for row in rows])
    band = np.asarray([str(row["temperature_band"]) for row in rows])
    mask = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    return {"groups": list(groups), "mask": mask}


@pytest.fixture(scope="module")
def bagged_fixture() -> dict:
    """One small, cheap bagged fold shared by the ensemble tests."""

    rng = np.random.default_rng(0)
    morgan = rng.normal(size=(40, 6))
    physical = rng.normal(size=(40, 2))
    target = 1.0 + 30.0 * rng.random(40)
    train = np.arange(28)
    test = np.arange(28, 40)
    prediction, morgan_members, physical_members = probe.bagged_fold_predictions(
        morgan=morgan,
        physical=physical,
        target=target,
        train_indices=train,
        test_indices=test,
        n_bags=3,
        seed=42,
    )
    return {
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "train": train,
        "test": test,
        "prediction": prediction,
        "morgan_members": morgan_members,
        "physical_members": physical_members,
    }


def test_bagging_constants_are_the_preregistered_literals(prereg_lever: dict) -> None:
    assert probe.N_BAGS == 10
    assert probe.BAG_SEED_MULTIPLIER == 1000
    assert probe.MEAN_TOLERANCE == 0.0050
    assert probe.STD_SHRINK_REQUIRED == 0.20
    assert f"n_bags = {probe.N_BAGS}" in prereg_lever["model_change"]
    assert f"seed * {probe.BAG_SEED_MULTIPLIER}" in prereg_lever["model_change"]


def test_the_preregistered_thresholds_are_the_ones_applied(summary: dict) -> None:
    assert summary["prereg"]["thresholds"]["mean_tolerance"] == probe.MEAN_TOLERANCE
    assert summary["prereg"]["thresholds"]["std_shrink_required"] == probe.STD_SHRINK_REQUIRED
    assert isinstance(summary["verdict"]["std_shrink_ok"], bool)
    assert isinstance(summary["verdict"]["mean_ok"], bool)


def test_reference_r2_is_the_published_paired_base_reading() -> None:
    assert probe.REFERENCE_R2 == 0.4091179943351143
    assert probe.REFERENCE_TRIPLE["Morgan+Physical"] == probe.REFERENCE_R2
    assert probe.REFERENCE_TRIPLE["Morgan"] == 0.06487386371009436
    assert probe.REFERENCE_TRIPLE["Physical"] == 0.2531659995294713


def test_main_scoreboard_is_re_derived_from_the_frozen_tables(scoreboard: dict) -> None:
    mask = np.asarray(scoreboard["mask"], dtype=bool)
    assert int(mask.sum()) == probe.SCOREBOARD_ROWS == 457
    assert len(set(np.asarray(scoreboard["groups"])[mask].tolist())) == 97


def test_bagged_prediction_is_the_mean_of_independently_seeded_members(
    bagged_fixture: dict,
) -> None:
    """Re-derive the ensemble with `XGBRegressor` directly, not with the probe."""

    morgan = bagged_fixture["morgan"]
    physical = bagged_fixture["physical"]
    target = bagged_fixture["target"]
    train = bagged_fixture["train"]
    test = bagged_fixture["test"]

    members = []
    for bag_index in range(3):
        bag_seed = 42 * probe.BAG_SEED_MULTIPLIER + bag_index
        morgan_model = XGBRegressor(**XGB_PARAMS, random_state=bag_seed)
        morgan_model.fit(morgan[train], target[train])
        physical_model = XGBRegressor(**XGB_PARAMS, random_state=bag_seed)
        physical_model.fit(physical[train], target[train])
        members.append(
            0.5 * (morgan_model.predict(morgan[test]) + physical_model.predict(physical[test]))
        )
    expected = np.maximum(np.mean(np.vstack(members), axis=0), 1.0)
    assert np.array_equal(bagged_fixture["prediction"], expected)


def test_bagging_is_not_a_no_op(bagged_fixture: dict) -> None:
    """A single member must not already equal the ensemble."""

    single = 0.5 * (
        bagged_fixture["morgan_members"][0] + bagged_fixture["physical_members"][0]
    )
    assert not np.allclose(np.maximum(single, 1.0), bagged_fixture["prediction"])


def test_averaging_does_not_reorder_the_composition(bagged_fixture: dict) -> None:
    """Averaging the finished hybrids equals the mean of the two member means."""

    members = bagged_fixture["morgan_members"]
    other = bagged_fixture["physical_members"]
    algebraic = 0.5 * (
        np.mean(np.vstack(members), axis=0) + np.mean(np.vstack(other), axis=0)
    )
    assert np.allclose(np.maximum(algebraic, 1.0), bagged_fixture["prediction"])


def test_the_clip_is_applied_after_the_averaging() -> None:
    """A target below the clip has to come back clipped, not negative."""

    rng = np.random.default_rng(7)
    morgan = rng.normal(size=(24, 4))
    physical = rng.normal(size=(24, 2))
    target = np.full(24, 1.0)
    prediction, _m, _p = probe.bagged_fold_predictions(
        morgan=morgan,
        physical=physical,
        target=target,
        train_indices=np.arange(16),
        test_indices=np.arange(16, 24),
        n_bags=2,
        seed=42,
    )
    assert np.all(prediction >= 1.0)


def test_bagged_predictions_are_deterministic(bagged_fixture: dict) -> None:
    repeated, _m, _p = probe.bagged_fold_predictions(
        morgan=bagged_fixture["morgan"],
        physical=bagged_fixture["physical"],
        target=bagged_fixture["target"],
        train_indices=bagged_fixture["train"],
        test_indices=bagged_fixture["test"],
        n_bags=3,
        seed=42,
    )
    assert np.array_equal(repeated, bagged_fixture["prediction"])


def test_the_bag_seeds_are_the_frozen_rule(summary: dict) -> None:
    assert summary["ensemble"]["bag_seed_rule"] == "random_state = seed * 1000 + bag index"
    assert summary["ensemble"]["bag_seeds"] == [42000 + bag for bag in range(10)]
    assert summary["ensemble"]["hyper_parameters_changed"] == []
    assert summary["ensemble"]["hyper_parameters"] == XGB_PARAMS


def test_the_shared_splits_guard_is_not_vacuous(scoreboard: dict) -> None:
    """The arms must share one dealing - and the comparison must be able to fail.

    A guard that only ever sees one dealing cannot fail, so this test also shows
    that moving the seed produces a *different* signature, and it pins the fold
    count and the covered-row count so an empty or single-fold comparison cannot
    pass by accident.
    """

    groups = scoreboard["groups"]
    mask = np.asarray(scoreboard["mask"], dtype=bool)
    repeats, _note = effective_repeats(97, n_splits=5, requested=10)
    kwargs = {"score_mask": mask, "train_mask": mask, "n_splits": 5, "n_repeats": repeats}

    first = list(drop_thin_folds(masked_splits(groups, seed=42, **kwargs), min_test_rows=2))
    again = list(drop_thin_folds(masked_splits(groups, seed=42, **kwargs), min_test_rows=2))
    other = list(drop_thin_folds(masked_splits(groups, seed=43, **kwargs), min_test_rows=2))

    # The dealing is reproducible ...
    assert scored_fold_signature(first) == scored_fold_signature(again)
    # ... and the signature can actually tell two dealings apart, so claiming the
    # three arms share one assignment is a claim with content.
    assert scored_fold_signature(first) != scored_fold_signature(other)
    covered = {int(index) for _repeat, _fold, _train, test in first for index in test}
    assert len(first) == 50
    assert len(covered) == 457


def test_the_summary_declares_the_shared_folds(summary: dict) -> None:
    assert summary["shared_folds"]["scored_side_identical"] is True
    assert summary["shared_folds"]["arms"] == [probe.BASELINE_ARM, probe.LEVER_ARM]


def test_the_three_arms_scored_the_same_rows_in_every_fold() -> None:
    """Read the armed predictions back off disk and compare the scored side.

    Every `(arm, representation)` pair must have been scored on the same
    `(repeat, fold)` and the very same rows inside it, duplicates included. The
    baseline arm writes three representations and the bagged and control arms one,
    so the guard is applied to all five pairs rather than to the hybrid alone -
    and it is asserted to have real content: five pairs, 50 folds each, every
    repeat laying the 457 scored rows out exactly once, 4570 rows in total.
    """

    assert PREDICTIONS_PATH.is_file(), "run probes/dielectric_bagging_probe.py first"
    by_arm: dict[tuple[str, str], dict[tuple[int, int], list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    with PREDICTIONS_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (int(row["repeat"]), int(row["fold"]))
            by_arm[(row["protocol"], row["representation"])][key].append(
                (row["inchikey"], row["T_K"])
            )

    expected_pairs = {
        (probe.BASELINE_ARM, "Morgan"),
        (probe.BASELINE_ARM, "Morgan+Physical"),
        (probe.BASELINE_ARM, "Physical"),
        (probe.LEVER_ARM, probe.HYBRID),
        (probe.CONTROL_ARM, probe.HYBRID),
    }
    assert set(by_arm) == expected_pairs

    reference = by_arm[(probe.BASELINE_ARM, probe.HYBRID)]
    assert len(reference) == 50
    for pair, block in by_arm.items():
        assert set(block) == set(reference), pair
        for key, rows in reference.items():
            # A multiset comparison, so a dropped or doubled duplicate row cannot
            # hide behind set semantics.
            assert sorted(block[key]) == sorted(rows), (pair, key)

    per_repeat_rows: dict[int, int] = defaultdict(int)
    per_repeat_pairs: dict[int, set] = defaultdict(set)
    for (repeat, _fold), rows in reference.items():
        per_repeat_rows[repeat] += len(rows)
        per_repeat_pairs[repeat].update(rows)
    assert len(per_repeat_rows) == 10
    assert all(count == 457 for count in per_repeat_rows.values()), per_repeat_rows
    assert sum(per_repeat_rows.values()) == 4570
    # The 457 scored rows carry only 276 distinct (compound, T) pairs: the same
    # temperature of the same compound is reported by more than one source, so a
    # block of rows duplicates a pair already in the pool. GroupKFold keeps a whole
    # compound together, so those duplicates travel as a block - which is why the
    # row count is not the sample size here.
    assert all(len(pairs) == 276 for pairs in per_repeat_pairs.values()), {
        repeat: len(pairs) for repeat, pairs in per_repeat_pairs.items()
    }



def test_the_bagged_arm_is_scored_on_the_main_scoreboard_representation(summary: dict) -> None:
    assert summary["ensemble"]["representations_scored"] == [probe.HYBRID]
    for arm in (probe.LEVER_ARM, probe.CONTROL_ARM):
        assert list(summary["readings"][arm]) == [probe.HYBRID]
    assert set(summary["readings"][probe.BASELINE_ARM]) == {
        "Morgan",
        "Morgan+Physical",
        "Physical",
    }


def test_baseline_arm_reproduced_the_published_r2(summary: dict) -> None:
    assert summary["baseline_reproduces"]["bit_exact"] is True
    assert summary["baseline_reproduces"]["abs_difference"] == 0.0
    assert summary["reference_triple"]["all_bit_exact"] is True
    assert summary["baseline_reproduces"]["reproduced_r2"] == probe.REFERENCE_R2


def test_the_std_shrink_is_derived_from_the_two_std_readings(summary: dict) -> None:
    readings = summary["readings"]
    baseline_std = readings[probe.BASELINE_ARM][probe.HYBRID]["r2"]["std"]
    lever_std = readings[probe.LEVER_ARM][probe.HYBRID]["r2"]["std"]
    expected = (baseline_std - lever_std) / baseline_std * 100.0
    assert summary["verdict"]["std_shrink_percent"] == pytest.approx(expected, abs=1e-12)
    assert summary["verdict"]["lever_std_r2"] == lever_std
    assert summary["verdict"]["baseline_std_r2"] == baseline_std


def test_verdict_never_claims_more_than_the_criterion_grants(summary: dict) -> None:
    verdict = summary["verdict"]
    passed = (
        verdict["mean_ok"]
        and verdict["std_shrink_ok"]
        and verdict["control_collapsed"]
    )
    if verdict["decision"] == "pass":
        assert passed
        assert verdict["carried_into_the_merge_arm"] is True
    else:
        assert not passed or verdict["decision"] == "unverified"
        assert verdict["carried_into_the_merge_arm"] is False
    if verdict["std_shrink_ok"] is False:
        assert verdict["decision"] != "pass"


def test_the_control_arm_is_judged_against_a_floor(summary: dict) -> None:
    collapse = summary["control_collapse"]
    readings = summary["readings"]
    assert collapse["control_r2"] == readings[probe.CONTROL_ARM][probe.HYBRID]["r2"]["mean"]
    assert collapse["delta_over_the_floor"] == pytest.approx(
        collapse["control_r2"] - collapse["trivial_floor_r2"], abs=1e-12
    )
    assert collapse["trivial_floor_r2"] != collapse["baseline_r2"]


def test_lever_delta_equals_the_two_rereadings(summary: dict) -> None:
    readings = summary["readings"]
    expected = (
        readings[probe.LEVER_ARM][probe.HYBRID]["r2"]["mean"]
        - readings[probe.BASELINE_ARM][probe.HYBRID]["r2"]["mean"]
    )
    assert summary["verdict"]["delta_mean_r2"] == pytest.approx(expected, abs=1e-12)
    assert summary["delta"]["delta_r2"] == pytest.approx(expected, abs=1e-12)


def test_check_recomputes_the_stored_verdict(summary: dict) -> None:
    assert probe.check_summary(summary) == []


def test_check_catches_a_tampered_reading(summary: dict) -> None:
    """The check must be able to fail, so the reading is moved on purpose."""

    tampered = copy.deepcopy(summary)
    tampered["readings"][probe.LEVER_ARM][probe.HYBRID]["r2"]["mean"] += 0.5
    assert probe.check_summary(tampered) != []
    tampered_std = copy.deepcopy(summary)
    tampered_std["readings"][probe.LEVER_ARM][probe.HYBRID]["r2"]["std"] *= 0.5
    assert probe.check_summary(tampered_std) != []


def test_report_is_the_rendered_summary(summary: dict) -> None:
    rendered = "\n".join(probe.render_report(summary))
    assert REPORT_PATH.read_text(encoding="utf-8") == rendered


def test_shots_are_counted(summary: dict) -> None:
    assert summary["shots"]["this_lever"] == 1
    assert summary["shots"]["control_arm_shots"] == 1


def test_locked_criteria_come_from_the_preregistration(summary: dict, prereg_lever: dict) -> None:
    locked = summary["locked_criteria"]
    for key in ("pass_criterion", "secondary_criterion", "kill_line", "expected_delta", "cost"):
        assert locked[key] == prereg_lever[key], key


def test_every_artifact_is_lf_only(summary: dict) -> None:
    paths = [REPORT_PATH, SUMMARY_PATH]
    paths += [
        REPOSITORY_ROOT / path
        for name, path in summary["outputs"].items()
        if name in {"folds", "repeats", "predictions"}
    ]
    for path in paths:
        raw = path.read_bytes()
        assert b"\r" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path


def test_frozen_red_lines_are_untouched() -> None:
    from electrolyte_ml.exporting import canonical_text_sha256

    for path, expected in FROZEN_DIGESTS.items():
        assert canonical_text_sha256(path) == expected, path