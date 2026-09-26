"""Offline tests for the temperature-band ablation probe.

Everything here runs against synthetic tables in a temporary directory. The
probe's band inventory, fold construction, leak audit and reporting logic are
exercised without reading data/processed, touching the network, or re-fitting
the frozen 236-compound endpoint.

Imports are deliberately bare (`import dielectric_band_ablation`) rather than
namespaced (`import probes.dielectric_band_ablation`): the probe itself imports
its collaborators by bare name, so the two spellings would otherwise resolve to
two distinct module objects and a monkeypatch applied to one would silently miss
the other.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_band_ablation as band_probe
import dielectric_observations_grouped_benchmark as grouped_benchmark
from dielectric_band_ablation import (
    BAND_ORDER,
    BAND_PROTOCOLS,
    CORE_BANDS,
    EXTENDED_BAND,
    HYBRID,
    OUTSIDE_BAND,
    ROOM_BAND,
    audit_folds,
    band_inventory,
    classify,
    compare_frozen_endpoint,
    compare_grouped_reference,
    core_test_splits,
    drop_thin_folds,
    effective_repeats,
    mechanism_decomposition,
    pooled_metrics,
    read_frozen_endpoint,
    read_grouped_reference,
    run_band_ablation,
    scoring_side_decomposition,
)
from dielectric_observations_grouped_benchmark import grouped_folds, random_row_folds
from dielectric_representation_ablation import PHYSICAL_COLUMNS

SMILES = ("CCO", "CCCO", "CCCCO", "CCCCC", "c1ccccc1", "CC(=O)C", "CO", "CC#N")

#: Band mix per synthetic compound. Compound 5 exists only outside the declared
#: window, which is exactly the training-only case the paired protocol handles.
BAND_PLAN: dict[int, tuple[str, ...]] = {
    0: (ROOM_BAND, ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    1: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    2: (ROOM_BAND, ROOM_BAND),
    3: (EXTENDED_BAND, OUTSIDE_BAND),
    4: (ROOM_BAND,),
    5: (OUTSIDE_BAND, OUTSIDE_BAND),
    6: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    7: (ROOM_BAND,),
}
#: Same shape, but every compound has at least one room row. That is what makes
#: the core compound set equal the full compound set, which is the condition the
#: probe relies on for `band_all` and `train_all_test_core` to be the same models.
PAIRED_BAND_PLAN: dict[int, tuple[str, ...]] = {
    0: (ROOM_BAND, ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    1: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    2: (ROOM_BAND, ROOM_BAND, OUTSIDE_BAND),
    3: (ROOM_BAND, EXTENDED_BAND),
    4: (ROOM_BAND, OUTSIDE_BAND),
    5: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    6: (ROOM_BAND, ROOM_BAND),
    7: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
}
EXPECTED_BAND_ROWS = {ROOM_BAND: 8, EXTENDED_BAND: 4, OUTSIDE_BAND: 6}
#: Row total of PAIRED_BAND_PLAN, which has a different band mix on purpose.
PAIRED_TOTAL_ROWS = 22
EXPECTED_BAND_COMPOUNDS = {ROOM_BAND: 6, EXTENDED_BAND: 4, OUTSIDE_BAND: 5}
ARTIFACT_FILENAMES = {
    "folds": "dielectric_band_ablation_folds.csv",
    "repeats": "dielectric_band_ablation_repeats.csv",
    "predictions": "dielectric_band_ablation_predictions.csv",
}


def _key(index: int) -> str:
    return f"SYNTH{index:04d}-UHFFFAOYSA-N"


def _write_lf_csv(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _tables(
    root: Path,
    plan: dict[int, tuple[str, ...]] | None = None,
) -> tuple[Path, Path]:
    """Write a synthetic observation + feature pair and return their paths."""

    plan = BAND_PLAN if plan is None else plan
    observations = root / "observations.csv"
    features = root / "features.csv"
    _write_lf_csv(
        observations,
        ("inchikey", "name", "smiles", "T_K", "epsilon", "temperature_band", "source_doi"),
        [
            [
                _key(index),
                f"mol{index}",
                SMILES[index % len(SMILES)],
                round(240.0 + 9.0 * (index + step), 2),
                round(2.5 + index + 0.4 * step, 3),
                band,
                "10.1000/synthetic",
            ]
            for index, bands in sorted(plan.items())
            for step, band in enumerate(bands)
        ],
    )
    _write_lf_csv(
        features,
        ("inchikey", "status", *PHYSICAL_COLUMNS),
        [
            [
                _key(index),
                "ok",
                *[
                    298.15 if column == "T_K" else float(index + 1)
                    for column in PHYSICAL_COLUMNS
                ],
            ]
            for index in sorted(plan)
        ],
    )
    return observations, features


def _rows(root: Path, plan: dict[int, tuple[str, ...]] | None = None) -> list[dict]:
    observations, features = _tables(root, plan)
    rows, _, dropped = band_probe.load_table(observations, features)
    assert dropped == {}
    return rows


def _core_rows(rows: Sequence[dict]) -> list[dict]:
    return [row for row in rows if row["temperature_band"] in CORE_BANDS]


def _split_signature(splits: Sequence[tuple]) -> list[tuple[int, int, tuple, tuple]]:
    return [
        (repeat, fold, tuple(sorted(train.tolist())), tuple(sorted(test.tolist())))
        for repeat, fold, train, test in splits
    ]


def _summary_stub(
    values: dict[str, dict[str, float]],
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    return {
        protocol: {
            representation: {"r2": {"mean": value}, "mae": {"mean": 1.0}}
            for representation, value in representations.items()
        }
        for protocol, representations in values.items()
    }


@pytest.fixture
def stub_predictor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the frozen XGBoost fit with a cheap deterministic stand-in.

    The structural tests below assert band routing, fold membership and the leak
    audit - properties of the split bookkeeping, not of model quality. Fitting
    200 boosted trees for each of them would cost minutes of wall clock and buy
    no extra evidence, so the predictor is stubbed to the training mean. The
    end-to-end test at the bottom keeps the real model, so the frozen pipeline
    is still exercised for real.
    """

    def predict(
        representation: str,
        *,
        morgan: np.ndarray,
        physical: np.ndarray,
        target: np.ndarray,
        train_indices: np.ndarray,
        test_indices: np.ndarray,
        seed: int,
    ) -> tuple[np.ndarray, str]:
        return np.full(int(test_indices.size), float(np.mean(target[train_indices]))), "stub"

    monkeypatch.setattr(grouped_benchmark, "fit_predict_representation", predict)


def test_band_constants_describe_the_observation_table() -> None:
    assert CORE_BANDS == (ROOM_BAND, EXTENDED_BAND)
    assert OUTSIDE_BAND not in CORE_BANDS
    assert set(BAND_ORDER) == {ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND}
    assert BAND_ORDER[0] == ROOM_BAND


def test_band_protocol_order_matches_the_reported_table() -> None:
    assert BAND_PROTOCOLS == (
        "band_room_only",
        "band_room_extended",
        "band_all",
        "single_row_298",
        "train_all_test_core",
    )


def test_band_inventory_counts_rows_and_compounds_per_band(tmp_path: Path) -> None:
    inventory = band_inventory(_rows(tmp_path))
    assert inventory["rows"] == EXPECTED_BAND_ROWS
    assert inventory["compounds"] == EXPECTED_BAND_COMPOUNDS
    assert inventory["total_rows"] == sum(EXPECTED_BAND_ROWS.values())
    assert inventory["total_compounds"] == len(BAND_PLAN)
    assert inventory["unknown_band_rows"] == {}
    assert inventory["core_bands"] == list(CORE_BANDS)


def test_band_inventory_separates_outside_only_compounds(tmp_path: Path) -> None:
    inventory = band_inventory(_rows(tmp_path))
    assert inventory["compounds_outside_only"] == [_key(5)]
    assert inventory["compounds_with_core_rows"] == len(BAND_PLAN) - 1


def test_band_inventory_flags_an_unexpected_band_label(tmp_path: Path) -> None:
    plan = {0: (ROOM_BAND, "not_a_band"), 1: (ROOM_BAND,)}
    inventory = band_inventory(_rows(tmp_path, plan))
    assert inventory["unknown_band_rows"] == {"not_a_band": 1}
    assert inventory["rows"][ROOM_BAND] == 2
    assert inventory["total_compounds"] == 2


def test_effective_repeats_refuses_a_pool_thinner_than_the_folds() -> None:
    repeats, note = effective_repeats(4, n_splits=5, requested=10)
    assert repeats == 0
    assert "not run" in note
    assert "4 compounds" in note


def test_effective_repeats_caps_at_what_the_pool_can_support() -> None:
    repeats, note = effective_repeats(12, n_splits=5, requested=10)
    assert repeats == 2
    assert "reduced from 10 to 2" in note


def test_effective_repeats_keeps_the_request_when_supported() -> None:
    repeats, note = effective_repeats(98, n_splits=5, requested=10)
    assert repeats == 10
    assert note == ""


def test_effective_repeats_always_runs_one_repeat_when_it_can() -> None:
    repeats, _note = effective_repeats(5, n_splits=5, requested=10)
    assert repeats == 1


def test_drop_thin_folds_removes_a_single_row_test_set() -> None:
    splits = [
        (0, 0, np.array([0, 1, 2]), np.array([3])),
        (0, 1, np.array([0, 1, 3]), np.array([2, 3])),
    ]
    kept = list(drop_thin_folds(splits))
    assert [fold for _repeat, fold, _train, _test in kept] == [1]


def test_drop_thin_folds_honours_a_custom_threshold() -> None:
    splits = [(0, 0, np.array([0, 1, 2, 3]), np.array([4, 5]))]
    assert list(drop_thin_folds(splits, min_test_rows=3)) == []


def test_core_test_splits_scores_only_rows_inside_the_core_bands(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    splits = list(core_test_splits(rows, _core_rows(rows), n_splits=2, n_repeats=1, seed=0))
    bands = [row["temperature_band"] for row in rows]
    assert splits
    for _repeat, _fold, _train, test in splits:
        assert {bands[int(index)] for index in test} <= set(CORE_BANDS)


def test_core_test_splits_never_puts_a_held_out_compound_in_train(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    splits = list(core_test_splits(rows, _core_rows(rows), n_splits=2, n_repeats=1, seed=0))
    for _repeat, _fold, train, test in splits:
        held_out = {groups[int(index)] for index in test}
        assert not held_out & {groups[int(index)] for index in train}


def test_core_test_splits_reuses_the_core_protocol_fold_membership(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    core = _core_rows(rows)
    core_groups = [row["inchikey"] for row in core]
    expected = list(grouped_folds(core_groups, n_splits=2, n_repeats=1, seed=0))
    actual = list(core_test_splits(rows, core, n_splits=2, n_repeats=1, seed=0))
    groups = [row["inchikey"] for row in rows]
    assert len(actual) == len(expected)
    for (repeat, fold, _train, test), (ref_repeat, ref_fold, _rtrain, ref_test) in zip(
        actual, expected, strict=True
    ):
        assert (repeat, fold) == (ref_repeat, ref_fold)
        assert {groups[int(index)] for index in test} == {
            core_groups[int(index)] for index in ref_test
        }


def test_core_test_splits_trains_on_every_out_of_core_row_it_can(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    splits = list(core_test_splits(rows, _core_rows(rows), n_splits=2, n_repeats=1, seed=0))
    audit = audit_folds(
        splits,
        groups=[row["inchikey"] for row in rows],
        bands=[row["temperature_band"] for row in rows],
    )
    assert audit["out_of_core_train_rows_available"] > 0
    assert audit["out_of_core_train_rows_not_used"] == 0


def test_core_test_splits_keeps_an_outside_only_compound_in_every_train_side(
    tmp_path: Path,
) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    splits = list(core_test_splits(rows, _core_rows(rows), n_splits=2, n_repeats=1, seed=0))
    for _repeat, _fold, train, test in splits:
        train_groups = {groups[int(index)] for index in train}
        test_groups = {groups[int(index)] for index in test}
        assert _key(5) in train_groups
        assert _key(5) not in test_groups


def test_core_test_splits_is_deterministic_for_a_fixed_seed(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    core = _core_rows(rows)
    first = _split_signature(core_test_splits(rows, core, n_splits=2, n_repeats=1, seed=3))
    second = _split_signature(core_test_splits(rows, core, n_splits=2, n_repeats=1, seed=3))
    assert first == second


def test_core_test_splits_moves_the_folds_when_the_seed_changes(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    core = _core_rows(rows)
    signatures = {
        tuple(
            _split_signature(core_test_splits(rows, core, n_splits=2, n_repeats=1, seed=seed))
        )
        for seed in range(6)
    }
    assert len(signatures) > 1


def test_core_test_splits_rejects_a_core_pool_that_is_not_the_core_band_rows(
    tmp_path: Path,
) -> None:
    rows = _rows(tmp_path)
    with pytest.raises(ValueError, match="core-band rows"):
        list(core_test_splits(rows, rows, n_splits=2, n_repeats=1, seed=0))


def test_core_test_splits_rejects_a_reordered_core_pool(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    core = list(reversed(_core_rows(rows)))
    with pytest.raises(ValueError, match="order"):
        list(core_test_splits(rows, core, n_splits=2, n_repeats=1, seed=0))


def test_audit_folds_accepts_a_grouped_split(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = [row["temperature_band"] for row in rows]
    splits = list(grouped_folds(groups, n_splits=2, n_repeats=1, seed=0))
    audit = audit_folds(splits, groups=groups, bands=bands)
    assert audit["folds_with_a_straddling_compound"] == 0
    assert audit["max_straddling_compounds_in_a_fold"] == 0
    assert audit["test_rows_outside_core_bands"] > 0


def test_audit_folds_flags_a_leaking_split() -> None:
    groups = ["A", "A", "B", "B", "C", "C"]
    bands = [ROOM_BAND] * 6
    leaking = [(0, 0, np.array([0, 1, 2]), np.array([2, 3]))]
    audit = audit_folds(leaking, groups=groups, bands=bands)
    assert audit["folds_with_a_straddling_compound"] == 1
    assert audit["max_straddling_compounds_in_a_fold"] == 1


def test_audit_folds_flags_the_reference_row_splitter(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = [row["temperature_band"] for row in rows]
    splits = list(random_row_folds(len(rows), n_splits=2, n_repeats=1, seed=0))
    audit = audit_folds(splits, groups=groups, bands=bands)
    assert audit["folds_with_a_straddling_compound"] == audit["folds"]


def test_audit_folds_counts_out_of_core_rows_that_were_used() -> None:
    groups = ["A", "A", "A", "B", "B", "B"]
    bands = [ROOM_BAND, ROOM_BAND, OUTSIDE_BAND, ROOM_BAND, ROOM_BAND, OUTSIDE_BAND]
    splits = [(0, 0, np.array([0, 1, 2]), np.array([3, 4]))]
    audit = audit_folds(splits, groups=groups, bands=bands)
    assert audit["out_of_core_train_rows_available"] == 1
    assert audit["out_of_core_train_rows_not_used"] == 0


def test_audit_folds_reports_an_empty_split_list() -> None:
    audit = audit_folds((), groups=["A"], bands=[ROOM_BAND])
    assert audit["folds"] == 0
    assert audit["folds_with_a_straddling_compound"] == 0
    assert audit["test_rows"] == 0


def test_run_band_ablation_covers_every_protocol(tmp_path: Path, stub_predictor: None) -> None:
    result = run_band_ablation(_rows(tmp_path), n_splits=2, n_repeats=1, seed=0)
    assert set(result["protocols"]) == set(BAND_PROTOCOLS)
    assert set(result["summary"]) == set(BAND_PROTOCOLS)
    for protocol in BAND_PROTOCOLS:
        assert result["audits"][protocol]["folds_with_a_straddling_compound"] == 0


def test_run_band_ablation_scores_only_core_rows_in_the_paired_protocol(
    tmp_path: Path, stub_predictor: None
) -> None:
    result = run_band_ablation(_rows(tmp_path), n_splits=2, n_repeats=1, seed=0)
    core = result["audits"]["band_room_extended"]
    paired = result["audits"]["train_all_test_core"]
    assert paired["test_rows"] == core["test_rows"]
    assert core["test_rows_outside_core_bands"] == 0
    assert paired["test_rows_outside_core_bands"] == 0
    assert paired["out_of_core_train_rows_available"] > core["out_of_core_train_rows_available"]


def test_run_band_ablation_gives_the_paired_protocol_more_training_rows(
    tmp_path: Path, stub_predictor: None
) -> None:
    result = run_band_ablation(_rows(tmp_path), n_splits=2, n_repeats=1, seed=0)
    core = result["protocols"]["band_room_extended"]
    paired = result["protocols"]["train_all_test_core"]
    assert paired["train_rows_mean"] > core["train_rows_mean"]
    assert paired["test_rows_mean"] == core["test_rows_mean"]


def test_run_band_ablation_keeps_the_single_row_control_at_one_row_per_compound(
    tmp_path: Path, stub_predictor: None
) -> None:
    result = run_band_ablation(_rows(tmp_path), n_splits=2, n_repeats=1, seed=0)
    meta = result["protocols"]["single_row_298"]
    assert meta["rows"] == len(BAND_PLAN)
    assert meta["compounds"] == len(BAND_PLAN)


def test_run_band_ablation_is_reproducible(tmp_path: Path, stub_predictor: None) -> None:
    rows = _rows(tmp_path)
    first = run_band_ablation(rows, n_splits=2, n_repeats=1, seed=0)
    second = run_band_ablation(rows, n_splits=2, n_repeats=1, seed=0)
    # NaN never equals NaN, so the tables are compared through their JSON form.
    assert json.dumps(first["summary"], sort_keys=True) == json.dumps(
        second["summary"], sort_keys=True
    )
    assert first["audits"] == second["audits"]
    assert first["protocols"] == second["protocols"]


def test_run_band_ablation_raises_when_a_compound_straddles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _rows(tmp_path)

    def leaking_splits(groups, *, n_splits, n_repeats, seed):
        every = np.arange(len(groups))
        yield 0, 0, every, every

    monkeypatch.setattr(band_probe, "grouped_folds", leaking_splits)
    with pytest.raises(ValueError, match="straddles"):
        run_band_ablation(rows, n_splits=2, n_repeats=1, seed=0)


def test_run_band_ablation_marks_a_thin_pool_as_not_run(tmp_path: Path) -> None:
    plan = {0: (ROOM_BAND, EXTENDED_BAND), 1: (ROOM_BAND,)}
    result = run_band_ablation(_rows(tmp_path, plan), n_splits=5, n_repeats=1, seed=0)
    for protocol in BAND_PROTOCOLS:
        meta = result["protocols"][protocol]
        assert meta["executed_repeats"] == 0
        assert "not run" in meta["note"]
        assert result["audits"][protocol]["folds"] == 0
        assert result["audits"][protocol]["folds_with_a_straddling_compound"] == 0
    assert result["fold_rows"] == []
    assert result["summary"] == {}


def test_classify_buckets_a_delta_against_the_tolerance() -> None:
    assert classify(0.05) == "helps"
    assert classify(-0.05) == "hurts"
    assert classify(0.0) == "inert"
    assert classify(0.004, tolerance=0.005) == "inert"
    assert classify(0.006, tolerance=0.005) == "helps"


def test_mechanism_decomposition_splits_the_gap_into_two_paired_deltas() -> None:
    summary = _summary_stub(
        {
            "band_room_extended": {HYBRID: 0.1861},
            "train_all_test_core": {HYBRID: 0.2061},
            "band_all": {HYBRID: 0.1602},
        }
    )
    mechanism = mechanism_decomposition(summary)
    assert mechanism["available"] is True
    assert mechanism["training_side_delta_r2"] == pytest.approx(0.02)
    assert mechanism["training_side_verdict"] == "helps"
    assert mechanism["scoring_side_delta_r2"] == pytest.approx(-0.0459)
    assert mechanism["scoring_side_verdict"] == "hurts"
    assert mechanism["total_delta_r2"] == pytest.approx(-0.0259)
    assert (
        mechanism["training_side_delta_r2"] + mechanism["scoring_side_delta_r2"]
        == pytest.approx(mechanism["total_delta_r2"])
    )


def test_mechanism_decomposition_reports_a_flat_training_side_as_inert() -> None:
    summary = _summary_stub(
        {
            "band_room_extended": {HYBRID: 0.2},
            "train_all_test_core": {HYBRID: 0.201},
            "band_all": {HYBRID: 0.1},
        }
    )
    mechanism = mechanism_decomposition(summary)
    assert mechanism["training_side_verdict"] == "inert"
    assert mechanism["scoring_side_verdict"] == "hurts"


def test_mechanism_decomposition_is_unavailable_without_the_protocols() -> None:
    mechanism = mechanism_decomposition(_summary_stub({"band_all": {HYBRID: 0.1}}))
    assert mechanism["available"] is False
    assert "band_room_extended" in mechanism["missing"]


def test_compare_grouped_reference_reports_bit_exact_reproduction() -> None:
    summary = {
        "band_all": {"Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.0}}},
        "single_row_298": {"Morgan": {"r2": {"mean": 0.3}, "mae": {"mean": 3.0}}},
    }
    reference = {
        "summary": {
            "grouped": {"Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.0}}},
            "grouped_single_row": {"Morgan": {"r2": {"mean": 0.3}, "mae": {"mean": 3.0}}},
        }
    }
    comparison = compare_grouped_reference(summary, reference)
    assert comparison["band_all"]["bit_exact"] is True
    assert comparison["single_row_298"]["bit_exact"] is True
    assert comparison["band_all"]["representations"]["Morgan"]["max_abs_delta"] == 0.0


def test_compare_grouped_reference_surfaces_a_numeric_drift() -> None:
    summary = {"band_all": {"Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.5}}}}
    reference = {"summary": {"grouped": {"Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.0}}}}}
    entry = compare_grouped_reference(summary, reference)["band_all"]
    assert entry["bit_exact"] is False
    assert entry["representations"]["Morgan"]["deltas"]["mae"] == pytest.approx(0.5)
    assert entry["representations"]["Morgan"]["bit_exact"] is False


def test_compare_grouped_reference_skips_representations_absent_from_either_side() -> None:
    summary = {
        "band_all": {
            "Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.0}},
            "Physical": {"r2": {"mean": 0.4}, "mae": {"mean": 3.0}},
            HYBRID: {"r2": {"mean": 0.6}, "mae": {"mean": 1.0}},
        }
    }
    reference = {
        "summary": {"grouped": {"Morgan": {"r2": {"mean": 0.5}, "mae": {"mean": 2.0}}}}
    }
    comparison = compare_grouped_reference(summary, reference)["band_all"]
    assert set(comparison["representations"]) == {"Morgan"}
    assert comparison["bit_exact"] is True
    # With nothing comparable on both sides the flag must not default to a pass.
    assert compare_grouped_reference({"band_all": {}}, {"summary": {"grouped": {}}})[
        "band_all"
    ]["bit_exact"] is False


def test_compare_grouped_reference_handles_a_missing_reference() -> None:
    comparison = compare_grouped_reference({}, {})
    assert comparison["band_all"]["available"] is False
    assert comparison["band_all"]["bit_exact"] is None


def test_compare_frozen_endpoint_flags_an_exact_replay() -> None:
    observed = {"Morgan": {"r2": 0.24019751230960526, "mae": 7.612385933454966}}
    reported = {
        "reported": {
            "Morgan": {
                "r2": {"mean": 0.24019751230960526},
                "mae": {"mean": 7.612385933454966},
            }
        }
    }
    comparison = compare_frozen_endpoint(observed, reported)
    assert comparison["bit_exact"] is True
    assert comparison["max_abs_delta"] == 0.0
    assert set(comparison["representations"]) == {"Morgan"}


def test_compare_frozen_endpoint_measures_the_drift() -> None:
    observed = {"Physical": {"r2": 0.3422, "mae": 7.1}}
    reported = {"reported": {"Physical": {"r2": {"mean": 0.3423}, "mae": {"mean": 7.0}}}}
    comparison = compare_frozen_endpoint(observed, reported)
    assert comparison["bit_exact"] is False
    assert comparison["max_abs_delta"] == pytest.approx(0.1)
    assert comparison["representations"]["Physical"]["deltas"]["r2"] == pytest.approx(-0.0001)


def test_compare_frozen_endpoint_is_empty_without_a_reference() -> None:
    comparison = compare_frozen_endpoint({"Morgan": {"r2": 0.0, "mae": 0.0}}, {})
    assert comparison["representations"] == {}
    assert comparison["bit_exact"] is False
    assert comparison["max_abs_delta"] == 0.0


def test_read_grouped_reference_points_at_the_w12_summary() -> None:
    reference = read_grouped_reference()
    if not reference:
        pytest.skip("the W12 grouped-benchmark summary is not present")
    assert reference["path"].endswith("dielectric_observations_grouped_benchmark_summary.json")
    assert set(reference["summary"]) >= {"grouped", "grouped_single_row"}


def test_read_frozen_endpoint_covers_the_three_representations() -> None:
    endpoint = read_frozen_endpoint()
    if not endpoint:
        pytest.skip("the frozen v1.0 ablation summary is not present")
    assert set(endpoint["reported"]) == {"Morgan", "Physical", HYBRID}
    for metrics in endpoint["reported"].values():
        assert set(metrics) == {"r2", "mae"}


def test_main_writes_lf_only_artifacts_and_a_complete_summary(tmp_path: Path) -> None:
    observations, features = _tables(tmp_path)
    summary_path = tmp_path / "out" / "summary.json"
    artifacts = tmp_path / "out" / "artifacts"
    exit_code = band_probe.main(
        [
            "--observations",
            str(observations),
            "--features",
            str(features),
            "--summary",
            str(summary_path),
            "--artifacts",
            str(artifacts),
            "--splits",
            "2",
            "--repeats",
            "1",
            "--skip-frozen-endpoint",
        ]
    )
    assert exit_code == 0
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert set(payload["protocols"]) == set(BAND_PROTOCOLS)
    assert set(payload["summary"]) == set(BAND_PROTOCOLS)
    assert payload["band_inventory"]["rows"] == EXPECTED_BAND_ROWS
    assert payload["protocols"]["band_all"]["rows"] == sum(EXPECTED_BAND_ROWS.values())
    assert payload["reference"]["frozen_endpoint"] == {}
    assert payload["mechanism"]["available"] is True
    assert set(payload["mechanism"]["pooled_metrics"]) == set(BAND_PROTOCOLS)
    assert payload["mechanism"]["scoring_side_decomposition"]["available"] is True
    for protocol in BAND_PROTOCOLS:
        assert payload["audits"][protocol]["folds_with_a_straddling_compound"] == 0
        assert payload["protocols"][protocol]["executed_repeats"] == 1
    for name, filename in ARTIFACT_FILENAMES.items():
        assert Path(payload["outputs"][name]).name == filename
        written = artifacts / filename
        assert written.is_file()
        assert b"\r\n" not in written.read_bytes()
    folds = list(
        csv.DictReader(
            (artifacts / ARTIFACT_FILENAMES["folds"]).read_text(encoding="utf-8").splitlines()
        )
    )
    assert {row["protocol"] for row in folds} == set(BAND_PROTOCOLS)


def _prediction_rows(
    protocol: str,
    repeat: int,
    targets: Sequence[float],
    predictions: Sequence[float],
    representation: str = HYBRID,
) -> list[dict]:
    return [
        {
            "protocol": protocol,
            "representation": representation,
            "repeat": repeat,
            "fold": 0,
            "inchikey": _key(index),
            "T_K": 300.0,
            "target": float(target),
            "prediction": float(prediction),
        }
        for index, (target, prediction) in enumerate(
            zip(targets, predictions, strict=True)
        )
    ]


def test_pooled_metrics_recover_r2_from_mse_and_pool_variance() -> None:
    rows = _prediction_rows("probe", 0, (0.0, 10.0, 20.0, 30.0), (1.0, 9.0, 21.0, 29.0))
    aggregate, per_repeat = pooled_metrics(rows)
    entry = aggregate["probe"]
    assert entry["rows"] == 4
    assert entry["repeats"] == 1
    assert entry["mse"] == pytest.approx(1.0)
    assert entry["mae"] == pytest.approx(1.0)
    assert entry["rmse"] == pytest.approx(1.0)
    assert entry["pool_variance"] == pytest.approx(125.0)
    assert entry["r2"] == pytest.approx(1.0 - 1.0 / 125.0)
    assert per_repeat["probe"][0]["rows"] == 4.0


def test_pooled_metrics_only_use_the_named_representation() -> None:
    rows = _prediction_rows("probe", 0, (0.0, 4.0), (0.0, 4.0), representation=HYBRID)
    rows += _prediction_rows("probe", 0, (0.0, 4.0), (99.0, 99.0), representation="Morgan")
    aggregate, _per_repeat = pooled_metrics(rows)
    assert aggregate["probe"]["mse"] == pytest.approx(0.0)


def test_pooled_metrics_average_over_repeats() -> None:
    rows = _prediction_rows("probe", 0, (0.0, 4.0), (0.0, 4.0))
    rows += _prediction_rows("probe", 1, (0.0, 4.0), (2.0, 6.0))
    aggregate, per_repeat = pooled_metrics(rows)
    assert aggregate["probe"]["repeats"] == 2
    assert aggregate["probe"]["mse"] == pytest.approx(2.0)
    assert per_repeat["probe"][0]["mse"] == pytest.approx(0.0)
    assert per_repeat["probe"][1]["mse"] == pytest.approx(4.0)


def test_pooled_metrics_are_empty_without_predictions() -> None:
    aggregate, per_repeat = pooled_metrics([])
    assert aggregate == {}
    assert per_repeat == {}


def test_scoring_side_decomposition_identity_holds() -> None:
    per_repeat = {
        "core": [
            {"repeat": 0.0, "rows": 4.0, "mse": 4.0, "mae": 2.0, "rmse": 2.0,
             "pool_variance": 125.0, "r2": 1.0 - 4.0 / 125.0}
        ],
        "wide": [
            {"repeat": 0.0, "rows": 6.0, "mse": 1.0, "mae": 1.0, "rmse": 1.0,
             "pool_variance": 35.0 / 3.0, "r2": 1.0 - 1.0 / (35.0 / 3.0)}
        ],
    }
    decomposition = scoring_side_decomposition(per_repeat, core="core", scored="wide")
    assert decomposition["available"] is True
    assert decomposition["identity_residual"] == pytest.approx(0.0, abs=1e-12)
    assert decomposition["delta_r2"] == pytest.approx(
        decomposition["squared_error_effect"] + decomposition["denominator_effect"]
    )


def test_scoring_side_decomposition_exposes_a_denominator_driven_drop() -> None:
    # The wider pool is predicted *better* in squared error, yet R2 still falls
    # because the scored pool variance shrank. This is the real-data pattern.
    per_repeat = {
        "core": [
            {"repeat": 0.0, "rows": 4.0, "mse": 4.0, "mae": 2.0, "rmse": 2.0,
             "pool_variance": 125.0, "r2": 1.0 - 4.0 / 125.0}
        ],
        "wide": [
            {"repeat": 0.0, "rows": 6.0, "mse": 1.0, "mae": 1.0, "rmse": 1.0,
             "pool_variance": 35.0 / 3.0, "r2": 1.0 - 1.0 / (35.0 / 3.0)}
        ],
    }
    decomposition = scoring_side_decomposition(per_repeat, core="core", scored="wide")
    assert decomposition["squared_error_effect"] > 0.0
    assert decomposition["denominator_effect"] < 0.0
    assert decomposition["delta_r2"] < 0.0
    assert decomposition["mse_scored"] < decomposition["mse_core"]


def test_scoring_side_decomposition_exposes_a_genuine_error_regression() -> None:
    per_repeat = {
        "core": [
            {"repeat": 0.0, "rows": 4.0, "mse": 1.0, "mae": 1.0, "rmse": 1.0,
             "pool_variance": 125.0, "r2": 1.0 - 1.0 / 125.0}
        ],
        "wide": [
            {"repeat": 0.0, "rows": 4.0, "mse": 16.0, "mae": 4.0, "rmse": 4.0,
             "pool_variance": 125.0, "r2": 1.0 - 16.0 / 125.0}
        ],
    }
    decomposition = scoring_side_decomposition(per_repeat, core="core", scored="wide")
    assert decomposition["squared_error_effect"] == pytest.approx(-0.12)
    assert decomposition["denominator_effect"] == pytest.approx(0.0)
    assert decomposition["delta_r2"] == pytest.approx(-0.12)


def test_scoring_side_decomposition_is_unavailable_without_both_protocols() -> None:
    decomposition = scoring_side_decomposition(
        {"train_all_test_core": [{"repeat": 0.0}]}, core="other", scored="band_all"
    )
    assert decomposition["available"] is False
    assert decomposition["core"] == "other"


def test_run_band_ablation_reports_pooled_metrics_and_the_decomposition(
    tmp_path: Path, stub_predictor: None
) -> None:
    result = run_band_ablation(
        _rows(tmp_path, PAIRED_BAND_PLAN), n_splits=2, n_repeats=1, seed=0
    )
    assert set(result["pooled"]) == set(BAND_PROTOCOLS)
    assert result["pooled"]["band_all"]["rows"] == PAIRED_TOTAL_ROWS
    decomposition = result["scoring_side_decomposition"]
    assert decomposition["available"] is True
    assert decomposition["identity_residual"] == pytest.approx(0.0, abs=1e-9)


def test_band_all_and_train_all_test_core_are_the_same_models(
    tmp_path: Path, stub_predictor: None
) -> None:
    """The paired protocols must differ only in which rows they score.

    Every compound in this plan has a room row, so the core compound set is the
    full compound set, the fold dealing is identical, and the training rows per
    fold coincide. Without that condition the scoring-side decomposition would be
    comparing two different models.
    """

    result = run_band_ablation(
        _rows(tmp_path, PAIRED_BAND_PLAN), n_splits=2, n_repeats=1, seed=0
    )
    rows = _rows(tmp_path, PAIRED_BAND_PLAN)
    assert band_inventory(rows)["compounds_outside_only"] == []

    train_rows = {}
    for row in result["fold_rows"]:
        if row["protocol"] in ("band_all", "train_all_test_core"):
            key = (row["representation"], row["repeat"], row["fold"])
            train_rows.setdefault(key, {})[row["protocol"]] = row["train_rows"]
    assert train_rows
    for key, per_protocol in train_rows.items():
        assert per_protocol["band_all"] == per_protocol["train_all_test_core"], key

    shared: dict[tuple, dict[str, float]] = {}
    for row in result["prediction_rows"]:
        key = (
            row["representation"],
            row["repeat"],
            row["inchikey"],
            row["T_K"],
            row["target"],
        )
        shared.setdefault(key, {})[row["protocol"]] = row["prediction"]
    # Every protocol here scores a subset of the rows `band_all` scores, and the
    # paired protocol must agree with it cell by cell.
    assert all("band_all" in value for value in shared.values())
    paired = [
        value
        for value in shared.values()
        if "band_all" in value and "train_all_test_core" in value
    ]
    assert paired
    assert all(value["band_all"] == value["train_all_test_core"] for value in paired)


def test_main_defaults_name_the_real_inputs_and_run_the_frozen_endpoint() -> None:
    args = band_probe._parse_args([])
    assert args.splits == band_probe.N_SPLITS
    assert args.repeats == band_probe.N_REPEATS
    assert args.skip_frozen_endpoint is False
    assert args.observations.name == "dielectric_observations_v11.csv"
    assert args.features.name == "dielectric_physical_features_v03.csv"
