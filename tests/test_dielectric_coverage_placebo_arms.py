"""Offline tests for the S-5 placebo three-arm probe.

Everything the probe decides without fitting a model is pinned here against
synthetic tables: the compound-level dose curve, the between-compound label
permutation, the mean-row reduction, the pass/fail readings and the refusal to
clobber an existing output. No XGBoost fit is paid for. The real repository
tables are read only by the integration tests at the end, and those need no
network either.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coverage_placebo_arms.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("placebo_arms_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

T_INDEX = list(probe.PHYSICAL_COLUMNS).index("T_K")


def _point(percent: int, delta: float) -> dict[str, object]:
    return {"percent": percent, "delta_r2": delta}


def _curve(*deltas: float) -> dict[str, object]:
    return probe.dose_curve_report(
        [_point(percent, delta) for percent, delta in zip(probe.DOSE_CURVE_PERCENTS, deltas)]
    )


# --------------------------------------------------------------------------- #
# arm B: the dose curve reading
# --------------------------------------------------------------------------- #


def test_dose_curve_report_reads_a_rising_curve_as_monotone() -> None:
    report = _curve(0.01, 0.04, 0.09, 0.12)
    assert report["percents"] == [25, 50, 75, 100]
    assert report["delta_r2"] == [0.01, 0.04, 0.09, 0.12]
    assert report["step_between"] == [[25, 50], [50, 75], [75, 100]]
    assert report["steps"] == pytest.approx([0.03, 0.05, 0.03])
    assert report["monotone"] is True
    assert report["non_decreasing"] is True
    assert report["span"] == pytest.approx(0.11)


def test_dose_curve_report_flags_a_reversal() -> None:
    report = _curve(0.01, 0.05, 0.04, 0.12)
    assert report["monotone"] is False
    assert report["non_decreasing"] is False


def test_dose_curve_report_separates_a_tie_from_a_reversal() -> None:
    tied = _curve(0.01, 0.01, 0.02)
    assert tied["monotone"] is False
    assert tied["non_decreasing"] is True
    assert tied["steps"][0] == 0.0


def test_dose_curve_report_tolerance_is_exclusive_for_monotone() -> None:
    report = probe.dose_curve_report(
        [_point(25, 0.0), _point(50, 1e-12)], tolerance=1e-12
    )
    assert report["steps"] == [1e-12]
    assert report["monotone"] is False
    assert report["non_decreasing"] is True


@pytest.mark.parametrize("points", [[], [_point(25, 0.01)]])
def test_dose_curve_report_needs_at_least_two_doses(points: list[dict[str, object]]) -> None:
    report = probe.dose_curve_report(points)
    assert report["monotone"] is False
    assert report["non_decreasing"] is False
    assert report["steps"] == []
    assert report["span"] is None
    assert "at least two" in str(report["reason"])


def test_dose_curve_report_is_ordered_by_the_caller() -> None:
    forward = _curve(0.01, 0.04, 0.09, 0.12)
    backward = _curve(0.12, 0.09, 0.04, 0.01)
    assert forward["monotone"] is True
    assert backward["monotone"] is False


# --------------------------------------------------------------------------- #
# arm B: the compound-level subsample
# --------------------------------------------------------------------------- #


def test_dose_compound_order_is_a_deterministic_permutation() -> None:
    keys = [f"c{index:02d}" for index in range(12)]
    first = probe.dose_compound_order(keys, seed=probe.DOSE_SEED)
    second = probe.dose_compound_order(keys, seed=probe.DOSE_SEED)
    assert first == second
    assert sorted(first) == keys
    assert probe.dose_compound_order(keys, seed=probe.DOSE_SEED + 1) != first


def test_dose_compound_order_deduplicates_and_rejects_an_empty_pool() -> None:
    order = probe.dose_compound_order(["b", "a", "b", "a"], seed=1)
    assert sorted(order) == ["a", "b"]
    with pytest.raises(ValueError, match="no compounds"):
        probe.dose_compound_order([], seed=1)


def test_dose_compounds_nest_and_hit_the_ceiling_count() -> None:
    order = probe.dose_compound_order([f"c{index:02d}" for index in range(50)], seed=7)
    level_25 = set(probe.dose_compounds(order, 25))
    level_50 = set(probe.dose_compounds(order, 50))
    level_75 = set(probe.dose_compounds(order, 75))
    level_100 = set(probe.dose_compounds(order, 100))
    assert level_25 < level_50 < level_75 < level_100
    assert [len(level) for level in (level_25, level_50, level_75, level_100)] == [13, 25, 38, 50]
    assert probe.dose_compounds(order, 100) == sorted(order)
    assert probe.dose_compounds(order, 25) == sorted(probe.dose_compounds(order, 25))


def test_dose_compounds_takes_at_least_one_compound() -> None:
    order = probe.dose_compound_order(["solo"], seed=1)
    assert probe.dose_compounds(order, 25) == ["solo"]


@pytest.mark.parametrize("percent", [0, -1, 101])
def test_dose_compounds_rejects_an_out_of_range_percent(percent: int) -> None:
    with pytest.raises(ValueError, match="out of range"):
        probe.dose_compounds(["a", "b"], percent)


# --------------------------------------------------------------------------- #
# arm A: the between-compound label placebo
# --------------------------------------------------------------------------- #


def _added_layout() -> tuple[list[str], np.ndarray, np.ndarray]:
    """Six added compounds with unequal blocks, plus two rows outside the block."""

    keys = ["a", "a", "a", "b", "c", "c", "d", "e", "f", "f", "z0", "z1"]
    added = np.zeros(len(keys), dtype=bool)
    added[:10] = True
    target = np.arange(len(keys), dtype=float)
    return keys, target, added


def test_permute_added_compound_labels_moves_labels_between_compounds() -> None:
    keys, target, added = _added_layout()
    added_keys = sorted({key for key, flag in zip(keys, added) if flag})
    assert len(added_keys) == 6

    reports = []
    for seed in range(6):
        permuted, report = probe.permute_added_compound_labels(
            keys, target, added_mask=added, seed=seed
        )
        # the compound set and the row layout of the added block are untouched
        assert report["added_compounds"] == len(added_keys)
        assert sorted(report["donor_compounds_per_destination"]) == added_keys
        assert report["added_rows"] == int(added.sum())
        assert permuted.shape == target.shape
        assert report["label_multiset_preserved"] is True
        assert report["labels_untouched_outside_the_added_block"] is True
        assert np.array_equal(permuted[~added], target[~added])
        assert sorted(permuted[added].tolist()) == sorted(target[added].tolist())
        expects_change = report["labels_changed"] > 0
        assert expects_change == (report["label_change_fraction"] > 0.0)
        assert report["label_change_fraction"] == pytest.approx(
            report["labels_changed"] / int(added.sum())
        )
        reports.append(report)

    assert any(report["labels_changed"] > 0 for report in reports)
    assert any(report["compounds_receiving_a_foreign_label"] > 0 for report in reports)


def test_permute_added_compound_labels_is_reproducible() -> None:
    keys, target, added = _added_layout()
    first, first_report = probe.permute_added_compound_labels(
        keys, target, added_mask=added, seed=probe.PLACEBO_SEED
    )
    second, second_report = probe.permute_added_compound_labels(
        keys, target, added_mask=added, seed=probe.PLACEBO_SEED
    )
    assert np.array_equal(first, second)
    assert first_report == second_report


def test_permute_added_compound_labels_spills_between_unequal_blocks() -> None:
    # a donor block larger than its destination has to spill onto the next compound
    keys = ["big", "big", "big", "small"]
    target = np.asarray([1.0, 2.0, 3.0, 9.0])
    added = np.asarray([True, True, True, True])
    permuted, report = probe.permute_added_compound_labels(
        keys, target, added_mask=added, seed=probe.PLACEBO_SEED
    )
    assert report["label_multiset_preserved"] is True
    assert sorted(permuted.tolist()) == sorted(target.tolist())


def test_permute_added_compound_labels_is_the_identity_without_added_rows() -> None:
    keys = ["a", "a", "b"]
    target = np.asarray([1.0, 2.0, 3.0])
    added = np.zeros(3, dtype=bool)
    permuted, report = probe.permute_added_compound_labels(keys, target, added_mask=added, seed=5)
    assert np.array_equal(permuted, target)
    assert report["added_compounds"] == 0
    assert report["added_rows"] == 0
    assert report["note"] == "no added rows: the placebo is the identity"


def test_permute_added_compound_labels_cannot_permute_one_compound() -> None:
    keys = ["only", "only", "z"]
    target = np.asarray([1.0, 2.0, 3.0])
    added = np.asarray([True, True, False])
    permuted, report = probe.permute_added_compound_labels(
        keys, target, added_mask=added, seed=5
    )
    assert report["added_compounds"] == 1
    assert np.array_equal(permuted, target)
    assert "cannot be permuted" in str(report["note"])


# --------------------------------------------------------------------------- #
# arm C: the mean row
# --------------------------------------------------------------------------- #


def test_mean_row_selection_keeps_the_row_nearest_the_compound_mean() -> None:
    keys = ["a", "a", "a", "b"]
    target = np.asarray([10.0, 20.0, 30.0, 99.0])
    temperatures = [300.0, 310.0, 320.0, 330.0]
    keep, report = probe.mean_row_selection(
        keys, target, temperatures, candidate_mask=[True, True, True, True]
    )
    assert report["compounds"] == 2
    assert report["kept_rows"] == 2
    assert report["rows_dropped"] == 2
    assert report["per_compound"]["a"]["kept_row"] == 1
    assert report["per_compound"]["a"]["kept_epsilon"] == 20.0
    assert report["per_compound"]["a"]["mean_epsilon"] == 20.0
    assert report["per_compound"]["b"]["kept_row"] == 3
    assert keep.tolist() == [False, True, False, True]


def test_mean_row_selection_breaks_a_tie_towards_the_smallest_index() -> None:
    keys = ["a", "a"]
    target = np.asarray([10.0, 30.0])
    keep, report = probe.mean_row_selection(
        keys, target, [300.0, 400.0], candidate_mask=[True, True]
    )
    assert report["per_compound"]["a"]["kept_row"] == 0
    assert report["per_compound"]["a"]["kept_epsilon"] == 10.0
    assert keep.tolist() == [True, False]


def test_mean_row_selection_honours_the_candidate_mask() -> None:
    keys = ["a", "a", "a"]
    target = np.asarray([10.0, 20.0, 30.0])
    keep, report = probe.mean_row_selection(
        keys, target, [300.0, 310.0, 320.0], candidate_mask=[True, False, True]
    )
    assert report["candidate_rows"] == 2
    assert report["per_compound"]["a"]["candidate_rows"] == 2
    assert report["per_compound"]["a"]["mean_epsilon"] == 20.0
    assert report["per_compound"]["a"]["kept_row"] == 0
    assert keep.tolist() == [True, False, False]


def _augmentation_fixture(*, constant_block: bool = True):
    keys = ["c0", "c0", "c1", "c1", "z0"]
    columns = len(probe.PHYSICAL_COLUMNS)
    physical = np.zeros((len(keys), columns), dtype=float)
    for row in range(len(keys)):
        physical[row] = float(row + 1)
    # a compound's physical block is constant apart from T_K
    physical[0, T_INDEX] = 300.0
    physical[1, T_INDEX] = 400.0
    physical[2, T_INDEX] = 310.0
    physical[3, T_INDEX] = 330.0
    other = [index for index in range(columns) if index != T_INDEX]
    physical[1, other] = physical[0, other]
    physical[3, other] = physical[2, other]
    if not constant_block:
        physical[1, other[0]] = physical[0, other[0]] + 1.0
    morgan = np.arange(len(keys) * 3, dtype=float).reshape(len(keys), 3)
    target = np.asarray([10.0, 20.0, 30.0, 40.0, 50.0])
    temperatures = physical[:, T_INDEX].tolist()
    added = np.asarray([True, True, True, True, False])
    room = np.asarray([True, True, True, True, True])
    return keys, morgan, physical, target, temperatures, added, room


def test_mean_row_augmentation_appends_one_mean_row_per_compound() -> None:
    keys, morgan, physical, target, temperatures, added, room = _augmentation_fixture()
    morgan_ext, physical_ext, target_ext, temperature_ext, keys_ext, report = (
        probe.mean_row_augmentation(
            keys,
            morgan,
            physical,
            target,
            temperatures,
            added_mask=added,
            room_mask=room,
        )
    )
    assert report["synthetic_rows"] == 2
    assert report["row_index_start"] == len(keys)
    assert report["row_index_stop"] == len(keys) + 2
    assert report["physical_block_constant_within_every_compound"] is True
    assert report["per_compound"]["c0"]["mean_T_K"] == 350.0
    assert report["per_compound"]["c0"]["mean_epsilon"] == 15.0
    assert report["per_compound"]["c1"]["mean_T_K"] == 320.0
    assert report["per_compound"]["c1"]["mean_epsilon"] == 35.0
    # the synthetic rows land after the observation rows, so no index moves
    assert keys_ext[: len(keys)] == keys
    assert keys_ext[len(keys) :] == ["c0", "c1"]
    assert np.array_equal(target_ext[: len(keys)], target)
    assert target_ext[len(keys) :].tolist() == [15.0, 35.0]
    assert temperature_ext[len(keys) :].tolist() == [350.0, 320.0]
    assert physical_ext[len(keys), T_INDEX] == 350.0
    assert physical_ext[len(keys) + 1, T_INDEX] == 320.0
    other = [index for index in range(physical.shape[1]) if index != T_INDEX]
    assert np.array_equal(physical_ext[len(keys), other], physical[0, other])
    assert np.array_equal(physical_ext[len(keys) + 1, other], physical[2, other])
    assert morgan_ext.shape == (len(keys) + 2, morgan.shape[1])
    assert np.array_equal(morgan_ext[len(keys)], morgan[0])
    assert np.array_equal(morgan_ext[: len(keys)], morgan)
    assert np.array_equal(physical_ext[: len(keys)], physical)


def test_mean_row_augmentation_flags_a_block_that_is_not_constant() -> None:
    fixture = _augmentation_fixture(constant_block=False)
    keys, morgan, physical, target, temperatures, added, room = fixture
    _morgan, _physical, _target, _temperature, _keys, report = probe.mean_row_augmentation(
        keys, morgan, physical, target, temperatures, added_mask=added, room_mask=room
    )
    assert report["physical_block_constant_within_every_compound"] is False
    assert report["per_compound"]["c0"]["physical_block_constant_within_the_compound"] is False
    assert report["per_compound"]["c1"]["physical_block_constant_within_the_compound"] is True


def test_mean_row_augmentation_needs_both_the_added_and_the_room_mask() -> None:
    keys, morgan, physical, target, temperatures, added, room = _augmentation_fixture()
    room = np.asarray([True, True, True, True, True])
    room[2] = False
    room[3] = False
    _morgan, _physical, _target, _temperature, keys_ext, report = probe.mean_row_augmentation(
        keys, morgan, physical, target, temperatures, added_mask=added, room_mask=room
    )
    assert report["synthetic_rows"] == 1
    assert keys_ext[len(keys) :] == ["c0"]


def test_mean_row_augmentation_is_the_identity_without_added_room_rows() -> None:
    keys, morgan, physical, target, temperatures, added, room = _augmentation_fixture()
    room = np.zeros(len(keys), dtype=bool)
    morgan_ext, physical_ext, target_ext, temperature_ext, keys_ext, report = (
        probe.mean_row_augmentation(
            keys,
            morgan,
            physical,
            target,
            temperatures,
            added_mask=added,
            room_mask=room,
        )
    )
    assert report["synthetic_rows"] == 0
    assert np.array_equal(morgan_ext, morgan)
    assert np.array_equal(physical_ext, physical)
    assert np.array_equal(target_ext, target)
    assert np.array_equal(temperature_ext, np.asarray(temperatures, dtype=float))
    assert keys_ext == keys


# --------------------------------------------------------------------------- #
# the training expansion and the fold contract
# --------------------------------------------------------------------------- #


def _protocols(names, *, scored_rows=457, compounds=97, folds=50):
    return {
        name: {"scored_rows": scored_rows, "compounds_scored": compounds, "folds": folds}
        for name in names
    }


def _split(repeat, fold, train, test):
    return (repeat, fold, np.asarray(train, dtype=int), np.asarray(test, dtype=int))


def test_fold_contract_requires_one_shared_scored_signature() -> None:
    names = [*probe.week_eleven.FIXED_POOL_PROTOCOLS, probe.ARM_A_PROTOCOL]
    protocols = _protocols(names)
    shared = [_split(0, 0, [0, 1, 2], [3, 4]), _split(0, 1, [3, 4], [0, 1, 2])]
    splits = {name: list(shared) for name in names}
    contract = probe.fold_contract(protocols, splits)
    assert contract["scored_fold_signatures_identical"] is True
    assert contract["protocols_with_a_signature"] == len(names)
    assert contract["arms_scored_rows"] == [457]
    assert contract["arms_compounds_scored"] == [97]
    assert contract["arms_fold_counts"] == [50]
    assert contract["arms_scored_rows_identical"] is True

    drifted = _protocols(names)
    splits[probe.ARM_A_PROTOCOL] = [_split(0, 0, [0, 1, 2], [3, 5])]
    contract = probe.fold_contract(drifted, splits)
    assert contract["scored_fold_signatures_identical"] is False


def test_arm_training_expansion_counts_the_rows_a_fold_really_fits() -> None:
    names = [probe.BASE_PROTOCOL, probe.FULL_ARM_PROTOCOL]
    masks = {
        probe.BASE_PROTOCOL: (np.zeros(12, dtype=bool), np.asarray([True] * 8 + [False] * 4)),
        probe.FULL_ARM_PROTOCOL: (np.zeros(12, dtype=bool), np.asarray([True] * 10 + [False] * 2)),
    }
    base = [_split(0, 0, [0, 1, 2, 3], [8, 9]), _split(0, 1, [4, 5, 6, 7], [10, 11])]
    wide = [_split(0, 0, [0, 1, 2, 3, 8, 9], [8, 9]), _split(0, 1, [4, 5, 6, 7, 10, 11], [10, 11])]
    splits = {probe.BASE_PROTOCOL: base, probe.FULL_ARM_PROTOCOL: wide}
    table = probe.arm_training_expansion(names, masks, splits_by_protocol=splits)
    assert table[probe.FULL_ARM_PROTOCOL]["rows_added_over_base"] == 2
    assert table[probe.FULL_ARM_PROTOCOL]["extra_rows_fitted_per_fold_mean"] == 2.0
    assert table[probe.FULL_ARM_PROTOCOL]["folds_compared"] == 2
    assert table[probe.FULL_ARM_PROTOCOL]["extra_rows_fitted_total"] == 4
    assert table[probe.BASE_PROTOCOL]["extra_rows_fitted_per_fold_mean"] == 0.0


def test_arm_training_expansion_refuses_mismatched_fold_order() -> None:
    names = [probe.BASE_PROTOCOL, probe.FULL_ARM_PROTOCOL]
    masks = {
        probe.BASE_PROTOCOL: (np.zeros(6, dtype=bool), np.zeros(6, dtype=bool)),
        probe.FULL_ARM_PROTOCOL: (np.zeros(6, dtype=bool), np.zeros(6, dtype=bool)),
    }
    splits = {
        probe.BASE_PROTOCOL: [_split(0, 0, [0], [1])],
        probe.FULL_ARM_PROTOCOL: [_split(0, 1, [0], [1])],
    }
    with pytest.raises(ValueError, match="fold order"):
        probe.arm_training_expansion(names, masks, splits_by_protocol=splits)


def test_arm_training_expansion_needs_a_base_with_folds() -> None:
    masks = {probe.BASE_PROTOCOL: (np.zeros(3, dtype=bool), np.zeros(3, dtype=bool))}
    with pytest.raises(ValueError, match="no folds"):
        probe.arm_training_expansion(
            [probe.BASE_PROTOCOL], masks, splits_by_protocol={probe.BASE_PROTOCOL: []}
        )


# --------------------------------------------------------------------------- #
# the S-5 criteria and the verdict
# --------------------------------------------------------------------------- #


def _criteria(**overrides):
    values = {
        "integrity_ok": True,
        "arm_a_delta_r2": 0.0,
        "dose_curve": {"monotone": True, "non_decreasing": True},
        "arm_c_delta_r2": 0.10,
        "full_arm_delta_r2": 0.1240864496977293,
    }
    values.update(overrides)
    return probe.build_criteria(**values)


def test_build_criteria_implements_the_threshold_literally() -> None:
    assert probe.ARM_A_TOLERANCE == 0.02
    at_the_threshold = _criteria(arm_a_delta_r2=0.02)
    assert at_the_threshold["arm_a_placebo_collapse"] is True
    above_the_threshold = _criteria(arm_a_delta_r2=0.0200001)
    assert above_the_threshold["arm_a_placebo_collapse"] is False
    assert at_the_threshold["arm_a_threshold"] == 0.02


def test_build_criteria_marks_arm_a_not_read_when_the_delta_is_missing() -> None:
    criteria = _criteria(arm_a_delta_r2=None)
    assert criteria["arm_a_placebo_collapse"] is None
    assert criteria["arm_c_below_the_full_arm"] is True


def test_verification_requires_every_criterion() -> None:
    assert probe.verification_passed(_criteria()) is True
    assert probe.verification_passed(_criteria(integrity_ok=False)) is False
    assert probe.verification_passed(_criteria(arm_a_delta_r2=0.05)) is False
    assert probe.verification_passed(
        _criteria(dose_curve={"monotone": False, "non_decreasing": True})
    ) is False
    assert probe.verification_passed(_criteria(arm_c_delta_r2=0.2)) is False


def test_build_verdict_names_the_information_reading_when_both_arms_pass() -> None:
    criteria = _criteria(arm_a_delta_r2=0.0001)
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=0.0001, full_arm_delta_r2=0.1240864496977293
    )
    assert verdict["observation_level_information_driven"] is True
    assert verdict["decision"] == "observation_level_information_driven"
    assert verdict["headline"] == "观测级信息驱动"
    assert "+0.1241" in str(verdict["statement"])


def test_build_verdict_reads_a_label_placebo_that_does_not_collapse_as_data_volume() -> None:
    criteria = _criteria(arm_a_delta_r2=0.09)
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=0.09, full_arm_delta_r2=0.1240864496977293
    )
    assert verdict["decision"] == "data_volume_effect"
    assert verdict["observation_level_information_driven"] is False
    assert "不得对外引用" in verdict["headline"]
    assert "Arm A 未塌缩" in str(verdict["statement"])
    assert "+0.1241" in str(verdict["statement"])


def test_build_verdict_reads_a_non_monotone_dose_curve_as_data_volume() -> None:
    criteria = _criteria(dose_curve={"monotone": False, "non_decreasing": False})
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=0.0, full_arm_delta_r2=0.1240864496977293
    )
    assert verdict["decision"] == "data_volume_effect"
    assert "Arm B 剂量曲线不是单调递增" in str(verdict["statement"])


def test_build_verdict_leaves_a_failed_integrity_gate_unverified() -> None:
    criteria = _criteria(integrity_ok=False, arm_a_delta_r2=0.0)
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=0.0, full_arm_delta_r2=0.1240864496977293
    )
    assert verdict["decision"] == "unverified"
    assert verdict["observation_level_information_driven"] is None
    assert "未通过完整性自检" in str(verdict["headline"])


def test_build_verdict_keeps_the_headline_when_only_arm_c_disagrees() -> None:
    criteria = _criteria(arm_c_delta_r2=0.2, arm_a_delta_r2=0.0)
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=0.0, full_arm_delta_r2=0.1240864496977293
    )
    assert criteria["arm_c_below_the_full_arm"] is False
    assert verdict["decision"] == "observation_level_information_driven"
    assert probe.verification_passed(criteria) is False


def test_build_verdict_writes_not_read_when_the_placebo_was_not_run() -> None:
    criteria = _criteria(arm_a_delta_r2=None)
    verdict = probe.build_verdict(
        criteria, arm_a_delta_r2=None, full_arm_delta_r2=0.1240864496977293
    )
    assert verdict["decision"] == "data_volume_effect"
    assert "not read" in str(verdict["statement"])


# --------------------------------------------------------------------------- #
# the plumbing: outputs, the digest and the json encoder
# --------------------------------------------------------------------------- #


def test_planned_outputs_names_every_table() -> None:
    outputs = probe.planned_outputs(Path("s.json"), Path("r.md"), Path("art"))
    assert set(outputs) == {"summary", "report", "folds", "repeats", "predictions"}
    assert outputs["folds"].name == probe.ARTIFACT_STEM + "_folds.csv"
    assert outputs["repeats"].name == probe.ARTIFACT_STEM + "_repeats.csv"
    assert outputs["predictions"].name == probe.ARTIFACT_STEM + "_predictions.csv"


def test_refuse_existing_lists_only_what_is_there_without_overwrite(tmp_path: Path) -> None:
    present = tmp_path / "summary.json"
    present.write_text("{}\n", encoding="utf-8", newline="\n")
    outputs = {"summary": present, "report": tmp_path / "absent.md"}
    assert probe.refuse_existing(outputs, overwrite=False) == [present]
    assert probe.refuse_existing(outputs, overwrite=True) == []


def test_jsonable_converts_the_numpy_scalars_the_run_produces() -> None:
    payload = probe.jsonable(
        {"a": np.float64(1.5), "b": [np.int64(2)], "c": np.asarray([np.float32(3.0)])}
    )
    assert payload == {"a": 1.5, "b": [2], "c": [3.0]}
    assert json.loads(json.dumps(payload)) == payload


def test_frozen_table_digest_reports_not_read_when_the_file_is_absent(tmp_path: Path) -> None:
    entry = probe.frozen_table_digest(tmp_path / "missing.csv", expected=probe.FROZEN_TABLE_SHA256)
    assert entry["status"] == "not read"
    assert entry["matches_literal"] is None
    assert entry["expected"] == probe.FROZEN_TABLE_SHA256


def test_pinned_reproduction_is_not_read_under_a_reduced_repeat_count() -> None:
    entry = probe.pinned_reproduction(
        paired_base_r2=probe.PAIRED_BASE_R2,
        paired_plus_coverage_r2=probe.PAIRED_PLUS_COVERAGE_R2,
        repeats=1,
    )
    assert entry["applicable"] is False
    assert entry["bit_exact"] is None
    assert "not read" in str(entry["reason"])


def test_pinned_reproduction_is_bit_exact_on_the_pinned_literals() -> None:
    entry = probe.pinned_reproduction(
        paired_base_r2=probe.PAIRED_BASE_R2,
        paired_plus_coverage_r2=probe.PAIRED_PLUS_COVERAGE_R2,
        repeats=probe.N_REPEATS,
    )
    assert entry["applicable"] is True
    assert entry["bit_exact"] is True
    assert entry["delta_r2"] == probe.PAIRED_DELTA_R2


def test_parse_args_defaults_and_the_overwrite_flag() -> None:
    defaults = probe._parse_args([])
    assert defaults.repeats == probe.N_REPEATS
    assert defaults.seed == probe.FOLD_SEED
    assert defaults.placebo_seed == probe.PLACEBO_SEED
    assert defaults.dose_seed == probe.DOSE_SEED
    assert defaults.overwrite is False
    assert probe._parse_args(["--overwrite"]).overwrite is True


def test_arm_descriptions_registers_and_restores_the_week_eleven_table() -> None:
    before = dict(probe.week_eleven.PROTOCOL_DESCRIPTIONS)
    with probe.arm_descriptions():
        for name in probe.ARM_DESCRIPTIONS:
            assert probe.week_eleven.PROTOCOL_DESCRIPTIONS[name] == probe.ARM_DESCRIPTIONS[name]
    assert dict(probe.week_eleven.PROTOCOL_DESCRIPTIONS) == before


def test_protocol_description_falls_back_to_week_eleven() -> None:
    assert probe.protocol_description(probe.ARM_A_PROTOCOL) == probe.ARM_DESCRIPTIONS[
        probe.ARM_A_PROTOCOL
    ]
    assert probe.protocol_description(probe.BASE_PROTOCOL)


# --------------------------------------------------------------------------- #
# the real repository tables (still offline: no network is touched)
# --------------------------------------------------------------------------- #


requires_real_tables = pytest.mark.skipif(
    not probe.week_eleven.COVERAGE_PATH.exists()
    or not probe.week_eleven.NEW_FEATURES_PATH.exists(),
    reason="the v11plus tables are not present in this checkout",
)


@requires_real_tables
def test_real_frozen_v03_table_keeps_its_pinned_digest() -> None:
    entry = probe.frozen_table_digest()
    assert entry["status"] == "read"
    assert entry["sha256"] == probe.FROZEN_TABLE_SHA256
    assert entry["matches_literal"] is True


@requires_real_tables
def test_real_scored_pool_still_has_the_shape_the_arms_assume() -> None:
    merged, _report = probe.week_eleven.merge_feature_blocks()
    coverage_rows, _dropped = probe.week_eleven.load_coverage_table(
        probe.week_eleven.COVERAGE_PATH, merged
    )
    v11_rows, _frozen, _dropped = probe.week_eleven.load_table(
        probe.week_eleven.OBSERVATIONS_PATH, probe.week_eleven.FEATURES_PATH
    )
    inventory = probe.week_eleven.new_compound_inventory(
        coverage_rows, {str(row["inchikey"]) for row in v11_rows}
    )
    assert inventory["compounds"] == probe.ADDED_COMPOUNDS
    assert inventory["room_rows_total"] == probe.ADDED_ROOM_ROWS
    assert len(coverage_rows) == 2029

    room = [
        row
        for row in coverage_rows
        if str(row["temperature_band"]) == probe.week_eleven.ROOM_BAND
        and str(row["observation_origin"]) == probe.week_eleven.ZERO_FREQUENCY_ORIGIN
    ]
    assert len(room) == probe.PAIRED_SCORED_ROWS
    assert len({str(row["inchikey"]) for row in room}) == probe.PAIRED_SCORED_COMPOUNDS


@requires_real_tables
def test_real_arm_table_rows_are_the_protocols_the_probe_runs() -> None:
    labels = [label for label, _protocol in probe.ARM_TABLE_ROWS]
    protocols = [protocol for _label, protocol in probe.ARM_TABLE_ROWS]
    assert len(set(protocols)) == len(protocols)
    assert probe.BASE_PROTOCOL in protocols
    assert probe.FULL_ARM_PROTOCOL in protocols
    assert probe.ARM_A_PROTOCOL in protocols
    assert probe.ARM_C_PROTOCOL in protocols
    assert "A label placebo" in labels
    for percent in probe.DOSE_CURVE_PERCENTS[:3]:
        assert probe.dose_protocol(percent) in protocols


@pytest.mark.skipif(not probe.SUMMARY_PATH.exists(), reason="the placebo summary has not been run")
def test_real_summary_renders_both_the_console_and_the_markdown_report() -> None:
    summary = json.loads(probe.SUMMARY_PATH.read_text(encoding="utf-8"))
    lines = probe.format_report(summary)
    assert lines[0] == "S-5 placebo arms for the Week 11 coverage gain"
    assert any(line.startswith("verdict") for line in lines)
    assert summary["verification_passed"] == probe.verification_passed(summary["criteria"])
    markdown = probe.render_markdown(summary)
    assert str(summary["verdict"]["headline"]) in markdown
    assert "\r" not in markdown
    assert summary["criteria"]["arm_a_threshold"] == probe.ARM_A_TOLERANCE
