"""Offline tests for the paired room-window probe.

Everything runs against synthetic tables in a temporary directory and a stubbed
predictor, so no test reads `data/processed`, touches the network, or fits the
frozen XGBoost model. The structural properties under test are fold routing, the
paired contract, the cohort lock and the artifact layout - not model quality.
The end-to-end test at the bottom keeps the real model so the inherited pipeline
is exercised for real.

Imports are bare (`import dielectric_room_window_paired`) rather than namespaced:
the probe imports its collaborators by bare name, so `probes.` spellings would
resolve to different module objects and a monkeypatch would silently miss.
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

import dielectric_observations_grouped_benchmark as grouped_benchmark
import dielectric_room_window_paired as room_probe
from dielectric_band_ablation import CORE_BANDS, EXTENDED_BAND, ROOM_BAND
from dielectric_observations_grouped_benchmark import grouped_folds
from dielectric_representation_ablation import PHYSICAL_COLUMNS

OUTSIDE_BAND = "outside_declared_window"
SMILES = (
    "CCO",
    "CCCO",
    "CCCCO",
    "CCCCC",
    "c1ccccc1",
    "CC(=O)C",
    "CO",
    "CC#N",
    "CCCl",
    "CCBr",
)
#: Compound 6 has no room row at all: it is the training-only case.
BAND_PLAN: dict[int, tuple[str, ...]] = {
    0: (ROOM_BAND, ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    1: (ROOM_BAND, EXTENDED_BAND, OUTSIDE_BAND),
    2: (ROOM_BAND, ROOM_BAND, EXTENDED_BAND),
    3: (ROOM_BAND,),
    4: (ROOM_BAND, OUTSIDE_BAND),
    5: (ROOM_BAND, ROOM_BAND, ROOM_BAND),
    6: (EXTENDED_BAND, OUTSIDE_BAND),
    7: (ROOM_BAND,),
    8: (ROOM_BAND, EXTENDED_BAND),
    9: (ROOM_BAND,),
}
#: Room-band rows in BAND_PLAN, used to check the scored pool size.
ROOM_ROWS = sum(1 for bands in BAND_PLAN.values() for band in bands if band == ROOM_BAND)
ARTIFACT_FILENAMES = {
    "folds": "dielectric_room_window_paired_folds.csv",
    "repeats": "dielectric_room_window_paired_repeats.csv",
    "predictions": "dielectric_room_window_paired_predictions.csv",
}


def _key(index: int) -> str:
    return f"SYNTH{index:04d}-UHFFFAOYSA-N"


def _write_lf_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _temperature(band: str, step: int) -> float:
    if band == ROOM_BAND:
        return round(293.15 + 2.5 * step, 2)
    if band == EXTENDED_BAND:
        return round(313.15 + 5.0 * step, 2)
    return round(240.0 + 7.0 * step, 2)


def _tables(
    root: Path,
    plan: dict[int, tuple[str, ...]] | None = None,
    *,
    not_model_ready: Sequence[int] = (),
) -> tuple[Path, Path, Path]:
    """Write a synthetic observation table, feature table and v1.0 roster.

    One feature table plays both parts, exactly as
    `data/processed/dielectric_physical_features_v03.csv` does for the real run:
    it carries the v1.0 curated label plus the frozen physical block, and it is
    also the xTB source the observation rows are joined against. The roster is
    the `model_ready` gate.
    """

    plan = BAND_PLAN if plan is None else plan
    observations = root / "observations.csv"
    features = root / "features.csv"
    dataset = root / "dataset.csv"
    _write_lf_csv(
        observations,
        ("inchikey", "name", "smiles", "T_K", "epsilon", "temperature_band", "source_doi"),
        [
            [
                _key(index),
                f"mol{index}",
                SMILES[index % len(SMILES)],
                _temperature(band, step),
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
        ("inchikey", "name", "smiles", "T_K", "dielectric", *PHYSICAL_COLUMNS[1:], "status"),
        [
            [
                _key(index),
                f"mol{index}",
                SMILES[index % len(SMILES)],
                298.15,
                round(3.5 + index, 3),
                *[float(index + 1) for _column in PHYSICAL_COLUMNS[1:]],
                "ok",
            ]
            for index in sorted(plan)
        ],
    )
    _write_lf_csv(
        dataset,
        ("inchikey", "model_ready"),
        [
            [_key(index), "false" if index in set(not_model_ready) else "true"]
            for index in sorted(plan)
        ],
    )
    return observations, features, dataset


def _rows(root: Path, plan: dict[int, tuple[str, ...]] | None = None) -> list[dict]:
    observations, features, _dataset = _tables(root, plan)
    rows, _, dropped = room_probe.load_table(observations, features)
    assert dropped == {}
    return rows


def _v10_rows(
    root: Path,
    plan: dict[int, tuple[str, ...]] | None = None,
    *,
    not_model_ready: Sequence[int] = (),
) -> tuple[list[dict[str, str]], dict[str, int], Path]:
    """The v1.0 pool exactly as `main` sees it: same feature file, its roster."""

    _observations, features, dataset = _tables(root, plan, not_model_ready=not_model_ready)
    rows, meta = room_probe.v10_modelling_pool(features, dataset)
    return rows, meta, dataset

def _summary_stub(
    values: dict[str, dict[str, dict[str, float]]],
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    return {
        protocol: {
            representation: {
                metric: {"mean": value, "std": 0.0, "n": 1}
                for metric, value in metrics.items()
            }
            for representation, metrics in representations.items()
        }
        for protocol, representations in values.items()
    }


def _band_ablation_stub(
    values: dict[str, dict[str, dict[str, float]]],
) -> dict[str, object]:
    return {"protocols": _summary_stub(values)}


def _full_metrics(r2: float, mae: float, spearman: float) -> dict[str, float]:
    metrics = {name: 0.0 for name in grouped_benchmark.METRIC_NAMES}
    metrics.update({"r2": r2, "mae": mae, "spearman": spearman})
    return metrics


@pytest.fixture
def stub_predictor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the frozen XGBoost fit with the training mean."""

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


def _split_map(
    rows: Sequence[dict],
    *,
    score_bands: Sequence[str],
    train_bands: Sequence[str],
    n_splits: int = 3,
    n_repeats: int = 1,
    seed: int = 42,
) -> dict[tuple[int, int], tuple[int, ...]]:
    bands = np.asarray([row["temperature_band"] for row in rows])
    groups = [row["inchikey"] for row in rows]
    splits = room_probe.drop_thin_folds(
        room_probe.masked_splits(
            groups,
            score_mask=np.isin(bands, list(score_bands)),
            train_mask=np.isin(bands, list(train_bands)),
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=seed,
        )
    )
    return {
        (repeat, fold): (int(test.size), int(train.size))
        for repeat, fold, train, test in splits
    }


def test_protocol_orders_match_the_reported_tables() -> None:
    assert room_probe.WINDOW_PROTOCOLS == (
        "band_room_only",
        "train_core_test_room",
        "train_all_test_room",
        "band_all",
    )
    assert room_probe.COHORT_PROTOCOLS == (
        "cohort_v10_frozen",
        "cohort_single_row",
        "cohort_room_train_single_test",
        "cohort_room_rows",
    )
    assert room_probe.REFERENCE_PROTOCOLS == ("band_room_only", "band_all")


def test_every_protocol_has_a_description_and_a_train_mask_label() -> None:
    every = set(room_probe.WINDOW_PROTOCOLS) | set(room_probe.COHORT_PROTOCOLS)
    assert set(room_probe.PROTOCOL_DESCRIPTIONS) == every
    assert set(room_probe.TRAIN_MASK_DESCRIPTIONS) == every
    assert all(room_probe.PROTOCOL_DESCRIPTIONS[name].strip() for name in every)


def test_chains_reference_real_protocols() -> None:
    for base, widened in room_probe.WINDOW_CHAIN:
        assert base in room_probe.WINDOW_PROTOCOLS
        assert widened in room_probe.WINDOW_PROTOCOLS
    for base, widened in room_probe.COHORT_CHAIN:
        assert base in room_probe.COHORT_PROTOCOLS
        assert widened in room_probe.COHORT_PROTOCOLS
    assert room_probe.WINDOW_SHARED_PROTOCOLS == (
        "band_room_only",
        "train_core_test_room",
        "train_all_test_room",
    )


def test_frozen_choices_are_the_v1_0_ones() -> None:
    assert room_probe.HYBRID == "Morgan+Physical"
    assert room_probe.TARGET_TEMPERATURE_K == 298.15
    assert set(room_probe.PAIRED_METRICS) == {"r2", "mae", "spearman"}


def test_fold_of_by_repeat_matches_the_grouped_dealing() -> None:
    keys = [_key(index) for index in range(7)]
    mine = room_probe.fold_of_by_repeat(keys, n_splits=3, n_repeats=2, seed=11)
    reference: list[dict[str, int]] = [{}, {}]
    for repeat, fold, _train, test in grouped_folds(
        keys, n_splits=3, n_repeats=2, seed=11
    ):
        for index in test:
            reference[repeat].setdefault(keys[int(index)], fold)
    assert mine == reference


def test_fold_of_by_repeat_is_deterministic_and_covers_every_compound() -> None:
    keys = [_key(index) for index in range(9)]
    first = room_probe.fold_of_by_repeat(keys, n_splits=3, n_repeats=2, seed=5)
    second = room_probe.fold_of_by_repeat(keys, n_splits=3, n_repeats=2, seed=5)
    assert first == second
    for assignment in first:
        assert sorted(assignment) == sorted(keys)
        assert sorted(assignment.values()) == sorted([index % 3 for index in range(9)])


def test_fold_of_by_repeat_moves_with_the_seed() -> None:
    keys = [_key(index) for index in range(12)]
    assert room_probe.fold_of_by_repeat(keys, n_splits=3, n_repeats=1, seed=1) != (
        room_probe.fold_of_by_repeat(keys, n_splits=3, n_repeats=1, seed=2)
    )


def test_fold_of_by_repeat_rejects_an_empty_pool() -> None:
    with pytest.raises(ValueError, match="no compounds"):
        room_probe.fold_of_by_repeat([])


def test_masked_splits_keeps_a_compound_whole(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    for _repeat, _fold, train, test in room_probe.masked_splits(
        groups,
        score_mask=bands == ROOM_BAND,
        train_mask=np.ones(len(rows), dtype=bool),
        n_splits=3,
        n_repeats=1,
    ):
        assert not set(np.asarray(groups)[train]) & set(np.asarray(groups)[test])


def test_masked_splits_scores_every_masked_row_exactly_once_per_repeat(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    score = bands == ROOM_BAND
    seen: list[int] = []
    for _repeat, _fold, _train, test in room_probe.masked_splits(
        groups, score_mask=score, train_mask=score, n_splits=3, n_repeats=1
    ):
        seen.extend(int(index) for index in test)
    assert sorted(seen) == sorted(np.flatnonzero(score).tolist())


def test_masked_splits_never_scores_a_row_outside_the_score_mask(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    score = bands == ROOM_BAND
    for _repeat, _fold, _train, test in room_probe.masked_splits(
        groups,
        score_mask=score,
        train_mask=np.ones(len(rows), dtype=bool),
        n_splits=3,
        n_repeats=1,
    ):
        assert score[test].all()


def test_masked_splits_widens_only_the_training_side(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    narrow = _split_map(rows, score_bands=(ROOM_BAND,), train_bands=(ROOM_BAND,))
    wide = _split_map(rows, score_bands=(ROOM_BAND,), train_bands=CORE_BANDS)
    assert narrow.keys() == wide.keys()
    for key, (test_rows, train_rows) in narrow.items():
        assert wide[key][0] == test_rows
        assert wide[key][1] > train_rows


def test_masked_splits_trains_on_a_compound_that_is_never_scored(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    band_array = np.asarray([row["temperature_band"] for row in rows])
    train_only = _key(6)
    assert train_only not in set(np.asarray(groups)[band_array == ROOM_BAND])
    for _repeat, _fold, train, _test in room_probe.masked_splits(
        groups,
        score_mask=band_array == ROOM_BAND,
        train_mask=np.isin(band_array, list(CORE_BANDS)),
        n_splits=3,
        n_repeats=1,
    ):
        assert train_only in set(np.asarray(groups)[train])


def test_masked_splits_rejects_a_mask_size_mismatch() -> None:
    with pytest.raises(ValueError, match="one boolean per row"):
        list(room_probe.masked_splits(["a", "b"], score_mask=[True], train_mask=[True, True]))


def test_masked_splits_rejects_an_empty_score_or_train_mask() -> None:
    with pytest.raises(ValueError, match="scored mask"):
        list(
            room_probe.masked_splits(
                ["a", "b"], score_mask=[False, False], train_mask=[True, True]
            )
        )
    with pytest.raises(ValueError, match="training mask"):
        list(
            room_probe.masked_splits(
                ["a", "b"], score_mask=[True, True], train_mask=[False, False]
            )
        )


def test_masked_splits_is_deterministic(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    kwargs = {"score_mask": bands == ROOM_BAND, "train_mask": np.ones(len(rows), dtype=bool)}
    first = room_probe.fold_signature(
        list(room_probe.masked_splits(groups, n_splits=3, n_repeats=1, **kwargs))
    )
    second = room_probe.fold_signature(
        list(room_probe.masked_splits(groups, n_splits=3, n_repeats=1, **kwargs))
    )
    assert first == second

def test_own_mode_equivalence_confirms_the_grouped_rule(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    report = room_probe.own_mode_equivalence(
        groups, mask=bands == ROOM_BAND, n_splits=3, n_repeats=1
    )
    assert report["available"] is True
    assert report["identical"] is True
    assert report["folds"] == 3


def test_own_mode_equivalence_detects_a_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    original = room_probe.masked_splits

    def shifted(row_groups, **kwargs):
        for repeat, fold, train, test in original(row_groups, **kwargs):
            yield repeat, fold, train, np.flip(test)

    monkeypatch.setattr(room_probe, "masked_splits", shifted)
    report = room_probe.own_mode_equivalence(
        groups, mask=bands == ROOM_BAND, n_splits=3, n_repeats=1
    )
    assert report["identical"] is False


def test_audit_masks_accepts_a_paired_split(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    score = bands == ROOM_BAND
    train = np.isin(bands, list(CORE_BANDS))
    splits = list(
        room_probe.drop_thin_folds(
            room_probe.masked_splits(
                groups, score_mask=score, train_mask=train, n_splits=3, n_repeats=1
            )
        )
    )
    audit = room_probe.audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    assert audit["folds_with_a_straddling_compound"] == 0
    assert audit["max_straddling_compounds_in_a_fold"] == 0
    assert audit["scored_rows_outside_the_score_mask"] == 0
    assert audit["train_rows_offered_but_unused"] == 0
    assert audit["compounds_scored"] == len(
        {row["inchikey"] for row in rows if row["temperature_band"] == ROOM_BAND}
    )
    assert audit["training_only_compounds"] == [_key(6)]


def test_audit_masks_flags_a_straddling_compound(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    score = np.ones(len(rows), dtype=bool)
    splits = [(0, 0, np.asarray([0, 1]), np.asarray([1, 2]))]
    audit = room_probe.audit_masks(groups, score_mask=score, train_mask=score, splits=splits)
    assert audit["folds_with_a_straddling_compound"] == 1
    assert audit["max_straddling_compounds_in_a_fold"] == 1


def test_audit_masks_flags_scored_rows_outside_the_mask(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    bands = np.asarray([row["temperature_band"] for row in rows])
    score = bands == ROOM_BAND
    outside = int(np.flatnonzero(~score)[0])
    splits = [(0, 0, np.asarray([0]), np.asarray([outside, outside + 1]))]
    audit = room_probe.audit_masks(
        groups, score_mask=score, train_mask=np.ones(len(rows), dtype=bool), splits=splits
    )
    assert audit["scored_rows_outside_the_score_mask"] == 2


def test_audit_masks_counts_rows_that_were_offered_but_not_used(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = np.asarray([row["inchikey"] for row in rows])
    bands = np.asarray([row["temperature_band"] for row in rows])
    score = bands == ROOM_BAND
    train = np.ones(len(rows), dtype=bool)
    held_out = {str(groups[0])}
    eligible = np.flatnonzero(train & ~np.isin(groups, sorted(held_out)))
    splits = [(0, 0, eligible[1:], np.asarray([int(np.flatnonzero(score)[0])]))]
    audit = room_probe.audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    assert audit["train_rows_offered_but_unused"] == 1


def test_audit_masks_handles_an_empty_split_list(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    groups = [row["inchikey"] for row in rows]
    audit = room_probe.audit_masks(
        groups, score_mask=np.ones(len(rows), dtype=bool), train_mask=np.ones(len(rows), dtype=bool), splits=[]
    )
    assert audit["folds"] == 0
    assert audit["max_straddling_compounds_in_a_fold"] == 0
    assert audit["scored_rows_total"] == 0


def test_target_pool_stats_uses_the_population_variance() -> None:
    stats = room_probe.target_pool_stats(np.asarray([1.0, 2.0, 3.0, 4.0]))
    assert stats["rows"] == 4
    assert stats["mean"] == pytest.approx(2.5)
    assert stats["var"] == pytest.approx(1.25)
    assert stats["std"] == pytest.approx(np.sqrt(1.25))
    assert stats["min"] == 1.0
    assert stats["max"] == 4.0


def test_fold_signature_is_stable_and_sensitive() -> None:
    first = [(0, 0, np.asarray([1, 2]), np.asarray([3]))]
    same = [(0, 0, np.asarray([1, 2]), np.asarray([3]))]
    other = [(0, 0, np.asarray([1, 2]), np.asarray([4]))]
    assert room_probe.fold_signature(first) == room_probe.fold_signature(same)
    assert room_probe.fold_signature(first) != room_probe.fold_signature(other)


def test_read_band_ablation_reference_keeps_only_the_two_shared_protocols(
    tmp_path: Path,
) -> None:
    path = tmp_path / "band.json"
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "band_room_only": {"Morgan+Physical": {"r2": {"mean": 0.4}}},
                    "band_all": {"Morgan+Physical": {"r2": {"mean": 0.16}}},
                    "single_row_298": {"Morgan+Physical": {"r2": {"mean": 0.18}}},
                },
                "inputs": {"observations_sha256": "abc"},
                "reference": {"frozen_endpoint": {"bit_exact": True}},
            }
        ),
        encoding="utf-8",
    )
    reference = room_probe.read_band_ablation_reference(path)
    assert set(reference["protocols"]) == {"band_room_only", "band_all"}
    assert reference["frozen_endpoint"] == {"bit_exact": True}


def test_read_band_ablation_reference_is_empty_without_a_summary(tmp_path: Path) -> None:
    assert room_probe.read_band_ablation_reference(tmp_path / "missing.json") == {}
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"summary": {}}), encoding="utf-8")
    assert room_probe.read_band_ablation_reference(empty) == {}


def test_compare_protocol_reference_reports_bit_exact() -> None:
    values = {
        "band_room_only": {"Morgan+Physical": _full_metrics(0.4091, 8.041, 0.7)},
        "band_all": {"Morgan+Physical": _full_metrics(0.1602, 10.292, 0.6)},
    }
    summary = _summary_stub(values)
    comparison = room_probe.compare_protocol_reference(summary, _band_ablation_stub(values))
    assert comparison["band_room_only"]["bit_exact"] is True
    assert comparison["band_all"]["max_abs_delta"] == 0.0
    assert set(comparison["band_room_only"]["representations"]["Morgan+Physical"]["deltas"]) == set(
        grouped_benchmark.METRIC_NAMES
    )


def test_compare_protocol_reference_surfaces_a_drift() -> None:
    mine = {
        "band_room_only": {"Morgan+Physical": _full_metrics(0.4091, 8.041, 0.7)},
        "band_all": {"Morgan+Physical": _full_metrics(0.1602, 10.292, 0.6)},
    }
    theirs = {
        "band_room_only": {"Morgan+Physical": _full_metrics(0.4091, 8.041, 0.7)},
        "band_all": {"Morgan+Physical": _full_metrics(0.1603, 10.292, 0.6)},
    }
    comparison = room_probe.compare_protocol_reference(
        _summary_stub(mine), _band_ablation_stub(theirs)
    )
    assert comparison["band_room_only"]["bit_exact"] is True
    assert comparison["band_all"]["bit_exact"] is False
    assert comparison["band_all"]["max_abs_delta"] == pytest.approx(1e-4)


def test_compare_protocol_reference_skips_a_missing_side() -> None:
    values = {"band_room_only": {"Morgan+Physical": _full_metrics(0.4, 8.0, 0.7)}}
    comparison = room_probe.compare_protocol_reference(
        _summary_stub(values), _band_ablation_stub(values)
    )
    assert comparison["band_all"]["available"] is False
    assert comparison["band_all"]["bit_exact"] is None


def test_compare_protocol_reference_without_a_reference() -> None:
    values = {"band_room_only": {"Morgan+Physical": _full_metrics(0.4, 8.0, 0.7)}}
    comparison = room_probe.compare_protocol_reference(_summary_stub(values), {})
    assert all(entry["available"] is False for entry in comparison.values())


def test_paired_delta_reads_r2_mae_and_spearman() -> None:
    summary = _summary_stub(
        {
            "a": {"Morgan+Physical": _full_metrics(0.40, 8.0, 0.70)},
            "b": {"Morgan+Physical": _full_metrics(0.36, 9.0, 0.60)},
        }
    )
    step = room_probe.paired_delta(summary, base="a", widened="b")
    assert step["available"] is True
    assert set(step["metrics"]) == {"r2", "mae", "spearman"}
    assert step["delta_r2"] == pytest.approx(-0.04)
    assert step["verdict"] == "hurts"
    assert step["metrics"]["mae"]["delta"] == pytest.approx(1.0)


def test_paired_delta_buckets_a_small_move_as_inert() -> None:
    summary = _summary_stub(
        {
            "a": {"Morgan+Physical": _full_metrics(0.4000, 8.0, 0.70)},
            "b": {"Morgan+Physical": _full_metrics(0.4030, 8.0, 0.70)},
        }
    )
    assert room_probe.paired_delta(summary, base="a", widened="b")["verdict"] == "inert"


def test_paired_delta_is_unavailable_without_a_protocol() -> None:
    summary = _summary_stub({"a": {"Morgan+Physical": _full_metrics(0.4, 8.0, 0.7)}})
    step = room_probe.paired_delta(summary, base="a", widened="b")
    assert step["available"] is False
    assert step["base"] == "a"


def _prediction_rows(protocol: str, keys: Sequence[tuple[int, int, str, float, float]]) -> list[dict]:
    return [
        {
            "protocol": protocol,
            "representation": "Morgan+Physical",
            "repeat": repeat,
            "fold": fold,
            "inchikey": inchikey,
            "T_K": temperature,
            "target": target,
            "prediction": 0.0,
        }
        for repeat, fold, inchikey, temperature, target in keys
    ]


def test_scored_row_fingerprints_filters_by_protocol_and_representation() -> None:
    rows = _prediction_rows("a", [(0, 0, _key(1), 298.15, 3.5)])
    rows.append({**rows[0], "protocol": "b"})
    rows.append({**rows[0], "representation": "Morgan"})
    assert len(room_probe.scored_row_fingerprints(rows, "a")) == 1


def test_scored_row_fingerprints_rounds_floats() -> None:
    rows = _prediction_rows("a", [(0, 0, _key(1), 298.15000000000003, 3.5000000000000004)])
    other = _prediction_rows("b", [(0, 0, _key(1), 298.15, 3.5)])
    assert room_probe.scored_row_fingerprints(rows, "a") == room_probe.scored_row_fingerprints(
        other, "b"
    )


def test_paired_contract_proves_identical_scored_rows() -> None:
    keys = [(0, 0, _key(1), 298.15, 3.5), (0, 0, _key(2), 300.65, 4.5)]
    rows = _prediction_rows("a", keys) + _prediction_rows("b", keys)
    report = room_probe.paired_contract(rows, (("a", "b"),))
    entry = report["a -> b"]
    assert entry["identical_scored_rows"] is True
    assert entry["widened_is_a_superset"] is True


def test_paired_contract_sees_a_widened_superset() -> None:
    base = [(0, 0, _key(1), 298.15, 3.5)]
    wide = base + [(0, 0, _key(1), 300.65, 4.5)]
    rows = _prediction_rows("a", base) + _prediction_rows("b", wide)
    entry = room_probe.paired_contract(rows, (("a", "b"),))["a -> b"]
    assert entry["identical_scored_rows"] is False
    assert entry["widened_is_a_superset"] is True
    assert entry["base_rows"] == 1
    assert entry["widened_rows"] == 2


def test_paired_contract_reports_a_shrunk_widened_set() -> None:
    base = [(0, 0, _key(1), 298.15, 3.5), (0, 0, _key(2), 300.65, 4.5)]
    narrow = base[:1]
    rows = _prediction_rows("a", base) + _prediction_rows("b", narrow)
    entry = room_probe.paired_contract(rows, (("a", "b"),))["a -> b"]
    assert entry["widened_is_a_superset"] is False


def test_scored_row_fingerprints_counts_duplicates(tmp_path: Path) -> None:
    rows = _prediction_rows("a", [(0, 0, _key(1), 298.15, 3.5)] * 2)
    assert len(room_probe.scored_row_fingerprints(rows, "a")) == 2

def _obs(
    inchikey: str,
    temperature: float,
    *,
    epsilon: float = 3.0,
    band: str = ROOM_BAND,
) -> dict:
    return {
        "inchikey": inchikey,
        "name": inchikey,
        "smiles": "CCO",
        "T_K": temperature,
        "epsilon": epsilon,
        "temperature_band": band,
    }


def test_v10_modelling_pool_honours_the_model_ready_gate(tmp_path: Path) -> None:
    plan = {index: (ROOM_BAND,) for index in range(6)}
    rows, meta, _dataset = _v10_rows(tmp_path, plan, not_model_ready=(4,))
    assert [row["inchikey"] for row in rows] == [_key(index) for index in (0, 1, 2, 3, 5)]
    assert meta == {"rows": 5, "failed_rows": 0, "withheld_rows": 1}


def test_cohort_membership_locks_the_intersection(tmp_path: Path) -> None:
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, not_model_ready=(5,))
    rows = _rows(tmp_path)
    membership = room_probe.cohort_membership(v10_rows, rows)
    assert membership["v1_0_modelling_compounds"] == 9
    assert membership["v1_1_modelling_compounds"] == 10
    assert membership["cohort"] == [_key(index) for index in (0, 1, 2, 3, 4, 7, 8, 9)]
    assert membership["shared_compounds_without_a_room_row"] == [_key(6)]
    assert membership["v1_1_compounds_outside_the_v1_0_pool"] == [_key(5)]


def test_cohort_membership_reports_a_fully_covered_pool(tmp_path: Path) -> None:
    plan = {index: (ROOM_BAND, ROOM_BAND) for index in range(4)}
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, plan)
    rows = _rows(tmp_path, plan)
    membership = room_probe.cohort_membership(v10_rows, rows)
    assert membership["cohort"] == [_key(index) for index in range(4)]
    assert membership["shared_compounds_without_a_room_row"] == []
    assert membership["v1_1_compounds_outside_the_v1_0_pool"] == []


def test_room_single_row_indices_picks_the_nearest_reference_temperature() -> None:
    rows = [
        _obs(_key(0), 293.15),
        _obs(_key(0), 298.15),
        _obs(_key(0), 303.15),
        _obs(_key(1), 293.15),
        _obs(_key(1), 300.65),
    ]
    picked = room_probe.room_single_row_indices(rows)
    assert picked == {_key(0): 1, _key(1): 4}


def test_room_single_row_indices_keeps_the_first_row_on_a_tie() -> None:
    rows = [_obs(_key(0), 297.15), _obs(_key(0), 299.15)]
    assert room_probe.room_single_row_indices(rows) == {_key(0): 0}


def test_room_single_row_indices_honours_a_custom_target() -> None:
    rows = [_obs(_key(0), 293.15), _obs(_key(0), 303.15)]
    assert room_probe.room_single_row_indices(rows, target_temperature_k=303.0) == {_key(0): 1}


def test_frozen_cohort_matrices_is_ordered_by_the_cohort(tmp_path: Path) -> None:
    plan = {index: (ROOM_BAND,) for index in range(5)}
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, plan)
    cohort = [_key(3), _key(0), _key(4)]
    rows, morgan, physical, target = room_probe.frozen_cohort_matrices(v10_rows, cohort)
    assert [row["inchikey"] for row in rows] == cohort
    assert target.tolist() == [3.5 + 3, 3.5 + 0, 3.5 + 4]
    assert physical.shape == (3, len(PHYSICAL_COLUMNS))
    assert morgan.shape[0] == 3


def test_frozen_cohort_matrices_rejects_a_compound_outside_the_pool(tmp_path: Path) -> None:
    plan = {index: (ROOM_BAND,) for index in range(3)}
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, plan)
    with pytest.raises(ValueError, match="absent from the v1.0 modelling pool"):
        room_probe.frozen_cohort_matrices(v10_rows, [_key(0), _key(9)])


def test_frozen_vs_observation_alignment_measures_both_deltas(tmp_path: Path) -> None:
    plan = {index: (ROOM_BAND,) for index in (0, 1)}
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, plan)
    observations = [
        _obs(_key(0), 298.15, epsilon=3.5),
        _obs(_key(1), 300.15, epsilon=5.0),
    ]
    alignment = room_probe.frozen_vs_observation_alignment(observations, v10_rows)
    assert alignment["rows"] == 2
    assert alignment["abs_delta_T_K"]["rows_above_1e-9"] == 1
    assert alignment["abs_delta_T_K"]["max"] == pytest.approx(2.0)
    assert alignment["abs_delta_epsilon"]["rows_above_0.01"] == 1
    assert alignment["abs_delta_epsilon"]["max"] == pytest.approx(0.5)


def test_run_window_family_covers_every_protocol(tmp_path: Path, stub_predictor: None) -> None:
    rows = _rows(tmp_path)
    result = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    assert set(result["protocols"]) == set(room_probe.WINDOW_PROTOCOLS)
    assert set(result["summary"]) == set(room_probe.WINDOW_PROTOCOLS)
    for protocol in room_probe.WINDOW_PROTOCOLS:
        assert result["audits"][protocol]["folds_with_a_straddling_compound"] == 0
        assert result["protocols"][protocol]["executed_repeats"] == 1


def test_run_window_family_shares_the_folds_and_the_scored_rows(
    tmp_path: Path, stub_predictor: None
) -> None:
    rows = _rows(tmp_path)
    result = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    assert result["folds_are_shared"] is True
    for name in room_probe.REFERENCE_PROTOCOLS:
        assert result["own_mode_equivalence"][name]["identical"] is True
    contract = room_probe.paired_contract(result["prediction_rows"], room_probe.WINDOW_CHAIN)
    for entry in contract.values():
        assert entry["identical_scored_rows"] is True
        assert entry["widened_is_a_superset"] is True


def test_run_window_family_widens_only_the_training_pool(
    tmp_path: Path, stub_predictor: None
) -> None:
    rows = _rows(tmp_path)
    result = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    protocols = result["protocols"]
    scored = {name: protocols[name]["scored_rows"] for name in room_probe.WINDOW_SHARED_PROTOCOLS}
    assert len(set(scored.values())) == 1
    assert protocols["band_room_only"]["train_pool_rows"] < (
        protocols["train_core_test_room"]["train_pool_rows"]
    )
    assert protocols["train_core_test_room"]["train_pool_rows"] < (
        protocols["train_all_test_room"]["train_pool_rows"]
    )
    assert protocols["band_all"]["scored_rows"] == len(rows)


def test_run_window_family_reports_the_target_pool_per_protocol(
    tmp_path: Path, stub_predictor: None
) -> None:
    rows = _rows(tmp_path)
    result = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    pools = result["target_pools"]
    assert pools["band_all"]["rows"] == len(rows)
    assert pools["band_room_only"]["rows"] == ROOM_ROWS
    assert pools["band_all"]["var"] != pools["band_room_only"]["var"]


def test_run_window_family_is_reproducible(tmp_path: Path, stub_predictor: None) -> None:
    rows = _rows(tmp_path)
    first = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    second = room_probe.run_window_family(rows, n_splits=3, n_repeats=1)
    # `json.dumps` rather than `==`: an empty MAE stratum is NaN, and NaN != NaN.
    assert json.dumps(first["repeat_rows"], sort_keys=True) == json.dumps(
        second["repeat_rows"], sort_keys=True
    )


def test_run_window_family_marks_a_thin_pool_as_not_run(tmp_path: Path) -> None:
    plan = {
        0: (ROOM_BAND,),
        1: (ROOM_BAND,),
        2: (ROOM_BAND,),
        3: (ROOM_BAND,),
        4: (ROOM_BAND,),
        5: (ROOM_BAND,),
        6: (ROOM_BAND,),
    }
    rows = _rows(tmp_path, plan)
    result = room_probe.run_window_family(rows, n_splits=9, n_repeats=1)
    assert result["protocols"]["band_room_only"]["executed_repeats"] == 0
    assert "not run" in result["protocols"]["band_room_only"]["note"]
    assert result["summary"] == {}


def test_run_cohort_family_locks_the_cohort_and_the_folds(
    tmp_path: Path, stub_predictor: None
) -> None:
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, not_model_ready=(5,))
    rows = _rows(tmp_path)
    result = room_probe.run_cohort_family(rows, v10_rows, n_splits=3, n_repeats=1)
    assert set(result["protocols"]) == set(room_probe.COHORT_PROTOCOLS)
    assert result["folds_are_shared"] is True
    assert result["cohort_rows"] == {"room_rows": 10, "single_rows": 8, "frozen_rows": 8}
    for protocol in room_probe.COHORT_PROTOCOLS:
        assert result["audits"][protocol]["folds_with_a_straddling_compound"] == 0
        assert result["protocols"][protocol]["compounds_scored"] == 8
        assert result["protocols"][protocol]["executed_repeats"] == 1


def test_run_cohort_family_shares_the_folds_across_repeats(
    tmp_path: Path, stub_predictor: None
) -> None:
    """The shared-fold invariant is per repeat, not across repeats.

    Each repeat redraws the compound permutation, so a check that demanded one
    single assignment for every repeat would be wrong - and a one-repeat test
    could never catch that. This one runs two repeats.
    """

    v10_rows, _meta, _dataset = _v10_rows(tmp_path, not_model_ready=(5,))
    rows = _rows(tmp_path)
    result = room_probe.run_cohort_family(rows, v10_rows, n_splits=3, n_repeats=2)
    assert result["folds_are_shared"] is True
    assert all(
        meta["executed_repeats"] == 2 for meta in result["protocols"].values()
    )
    window = room_probe.run_window_family(rows, n_splits=3, n_repeats=2)
    assert window["folds_are_shared"] is True


def test_run_cohort_family_holds_the_scored_rows_fixed_through_the_widening_step(
    tmp_path: Path, stub_predictor: None
) -> None:
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, not_model_ready=(5,))
    rows = _rows(tmp_path)
    result = room_probe.run_cohort_family(rows, v10_rows, n_splits=3, n_repeats=1)
    contract = room_probe.paired_contract(result["prediction_rows"], room_probe.COHORT_CHAIN)
    widening = contract["cohort_single_row -> cohort_room_train_single_test"]
    assert widening["identical_scored_rows"] is True
    assert result["target_pools"]["cohort_single_row"] == result["target_pools"][
        "cohort_room_train_single_test"
    ]
    scored = contract["cohort_room_train_single_test -> cohort_room_rows"]
    assert scored["identical_scored_rows"] is False
    assert scored["widened_is_a_superset"] is True
    assert result["target_pools"]["cohort_room_rows"]["rows"] == 10
    train_pools = {
        name: result["protocols"][name]["train_pool_rows"]
        for name in room_probe.COHORT_PROTOCOLS
    }
    assert train_pools["cohort_single_row"] < train_pools["cohort_room_train_single_test"]
    assert train_pools["cohort_room_train_single_test"] == train_pools["cohort_room_rows"]


def test_run_cohort_family_keeps_the_label_step_visible(
    tmp_path: Path, stub_predictor: None
) -> None:
    v10_rows, _meta, _dataset = _v10_rows(tmp_path, not_model_ready=(5,))
    rows = _rows(tmp_path)
    result = room_probe.run_cohort_family(rows, v10_rows, n_splits=3, n_repeats=1)
    contract = room_probe.paired_contract(result["prediction_rows"], room_probe.COHORT_CHAIN)
    label_step = contract["cohort_v10_frozen -> cohort_single_row"]
    assert label_step["identical_scored_rows"] is False
    alignment = result["single_row_alignment"]
    assert alignment["rows"] == 8
    assert alignment["abs_delta_epsilon"]["max"] > 0


def test_main_writes_lf_only_artifacts_and_a_complete_summary(
    tmp_path: Path, stub_predictor: None
) -> None:
    observations, features, dataset = _tables(tmp_path, not_model_ready=(5,))
    reference = tmp_path / "band.json"
    reference.write_text(json.dumps({"summary": {}}), encoding="utf-8")
    summary_path = tmp_path / "out" / "summary.json"
    artifacts = tmp_path / "out" / "artifacts"
    exit_code = room_probe.main(
        [
            "--observations",
            str(observations),
            "--features",
            str(features),
            "--dataset",
            str(dataset),
            "--reference",
            str(reference),
            "--summary",
            str(summary_path),
            "--artifacts",
            str(artifacts),
            "--splits",
            "3",
            "--repeats",
            "1",
            "--skip-frozen-endpoint",
        ]
    )
    assert exit_code == 0
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert set(payload["window_family"]["protocols"]) == set(room_probe.WINDOW_PROTOCOLS)
    assert set(payload["cohort_family"]["protocols"]) == set(room_probe.COHORT_PROTOCOLS)
    assert payload["window_family"]["folds_are_shared"] is True
    assert payload["cohort_family"]["folds_are_shared"] is True
    assert payload["reference"]["frozen_endpoint"] == {}
    assert payload["v1_0_pool"]["withheld_rows"] == 1
    assert payload["cohort_family"]["membership"]["shared_compounds_without_a_room_row"] == [
        _key(6)
    ]
    for name, filename in ARTIFACT_FILENAMES.items():
        written = artifacts / filename
        assert written.is_file()
        assert Path(payload["outputs"][name]).name == filename
        assert b"\r\n" not in written.read_bytes()
    folds = list(
        csv.DictReader(
            (artifacts / ARTIFACT_FILENAMES["folds"]).read_text(encoding="utf-8").splitlines()
        )
    )
    assert {row["protocol"] for row in folds} == set(room_probe.WINDOW_PROTOCOLS) | set(
        room_probe.COHORT_PROTOCOLS
    )
    predictions = list(
        csv.DictReader(
            (artifacts / ARTIFACT_FILENAMES["predictions"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
    )
    assert set(predictions[0]) == set(grouped_benchmark.PREDICTION_COLUMNS)
    assert payload["outputs"]["folds"].endswith(ARTIFACT_FILENAMES["folds"])


def test_main_defaults_name_the_real_inputs_and_run_the_frozen_endpoint() -> None:
    args = room_probe._parse_args([])
    assert args.splits == room_probe.N_SPLITS
    assert args.repeats == room_probe.N_REPEATS
    assert args.skip_frozen_endpoint is False
    assert args.observations.name == "dielectric_observations_v11.csv"
    assert args.features.name == "dielectric_physical_features_v03.csv"
    assert args.reference.name == "dielectric_band_ablation_summary.json"


def test_format_protocol_renders_the_three_paired_metrics() -> None:
    summary = _summary_stub(
        {"a": {"Morgan+Physical": _full_metrics(0.4091, 8.041, 0.7012)}}
    )
    line = room_probe._format_protocol(summary, "a")
    assert "R2=0.4091" in line
    assert "MAE=8.0410" in line
    assert "Spearman=0.7012" in line
    assert room_probe._format_protocol(summary, "missing") == "not run"