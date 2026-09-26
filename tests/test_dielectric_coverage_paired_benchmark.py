"""Offline tests for the strict coverage-paired benchmark probe.

Every network-free path is pinned here with synthetic tables and a stub
predictor, so the probe's arithmetic (fold sharing, the mask audit, the room-row
gate account and the paired deltas) is verified without paying for a single
XGBoost fit. Three integration tests read the real repository tables; they need
no network either.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coverage_paired_benchmark.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("coverage_paired_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()
PHYSICAL_COLUMNS = probe.PHYSICAL_COLUMNS

ROOM = probe.ROOM_BAND
OUTSIDE = "outside_declared_window"
EXTENDED = "extended_temperature"
ZERO = probe.ZERO_FREQUENCY_ORIGIN
LOW = probe.LOW_FREQUENCY_ORIGIN

OBSERVATION_COLUMNS = (
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "epsilon",
    "source_doi",
    "source_row_index",
    "observation_origin",
    "temperature_band",
)


def _observation(
    key: str,
    *,
    name: str = "compound",
    smiles: str = "CCO",
    t_k: str = "298.15",
    epsilon: str = "10.0",
    doi: str = "10.0000/test",
    origin: str = ZERO,
    band: str = ROOM,
    row_index: str = "0",
) -> dict[str, str]:
    return {
        "inchikey": key,
        "name": name,
        "smiles": smiles,
        "T_K": t_k,
        "epsilon": epsilon,
        "source_doi": doi,
        "source_row_index": row_index,
        "observation_origin": origin,
        "temperature_band": band,
    }


def _feature(key: str, *, status: str = "cached", blank: str | None = None) -> dict[str, str]:
    row = {"inchikey": key, "name": "compound", "status": status}
    for index, column in enumerate(PHYSICAL_COLUMNS):
        row[column] = "" if column == blank else str(index + 1)
    return row


def _write_csv(path: Path, rows: list[dict[str, str]], columns: tuple[str, ...]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return path


def _observation_file(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    return _write_csv(tmp_path / "observations.csv", rows, OBSERVATION_COLUMNS)


def _feature_file(
    tmp_path: Path,
    name: str,
    rows: list[dict[str, str]],
) -> Path:
    columns = ("inchikey", "name", "status", *PHYSICAL_COLUMNS)
    return _write_csv(tmp_path / name, rows, columns)


# --------------------------------------------------------------------------- #
# feature blocks
# --------------------------------------------------------------------------- #


def test_read_feature_block_excludes_error_rows(tmp_path: Path) -> None:
    path = _feature_file(tmp_path, "f.csv", [_feature("A"), _feature("B", status="error")])
    usable, report = probe.read_feature_block(path, source=probe.FROZEN_SOURCE)
    assert sorted(usable) == ["A"]
    assert report["usable"] == 1
    assert report["errored_keys"] == ["B"]
    assert usable["A"]["_feature_source"] == probe.FROZEN_SOURCE


def test_read_feature_block_flags_incomplete_physical_columns(tmp_path: Path) -> None:
    path = _feature_file(tmp_path, "f.csv", [_feature("A", blank="dipole_D")])
    usable, report = probe.read_feature_block(path, source=probe.NEW_XTB_SOURCE)
    assert usable == {}
    assert report["incomplete_keys"] == ["A"]


def test_read_feature_block_records_duplicate_keys(tmp_path: Path) -> None:
    path = _feature_file(tmp_path, "f.csv", [_feature("A"), _feature("A")])
    usable, report = probe.read_feature_block(path, source=probe.FROZEN_SOURCE)
    assert list(usable) == ["A"]
    assert report["duplicate_keys"] == ["A"]


def test_merge_feature_blocks_lets_the_frozen_block_win(tmp_path: Path) -> None:
    frozen_rows = [_feature("A")]
    frozen_rows[0]["dipole_D"] = "99"
    new_rows = [_feature("A"), _feature("B")]
    frozen = _feature_file(tmp_path, "frozen.csv", frozen_rows)
    new = _feature_file(tmp_path, "new.csv", new_rows)
    merged, report = probe.merge_feature_blocks(frozen, new)
    assert sorted(merged) == ["A", "B"]
    assert merged["A"]["_feature_source"] == probe.FROZEN_SOURCE
    assert merged["B"]["_feature_source"] == probe.NEW_XTB_SOURCE
    assert report["overlap_keys"] == ["A"]
    assert report["overlap_physical_column_disagreements"] == {"A": ["dipole_D"]}
    assert report["usable_from_frozen"] == 0
    assert report["usable_from_new"] == 1


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

# --------------------------------------------------------------------------- #
# the coverage table, the inventory and the gate account
# --------------------------------------------------------------------------- #


def test_load_coverage_table_mirrors_the_frozen_loader_gates(tmp_path: Path) -> None:
    rows = [
        _observation("A", row_index="0"),
        _observation("B", row_index="1"),
        _observation("C", row_index="2", smiles=""),
    ]
    path = _observation_file(tmp_path, rows)
    features = {
        "A": {"_feature_source": probe.FROZEN_SOURCE},
        "C": {"_feature_source": probe.FROZEN_SOURCE},
    }
    kept, dropped = probe.load_coverage_table(path, features)
    assert [row["inchikey"] for row in kept] == ["A"]
    assert dropped == {"no_xtb_features": 1, "no_smiles": 1}
    assert kept[0]["_feature_source"] == probe.FROZEN_SOURCE


def test_frozen_table_agreement_needs_the_same_rows_in_the_same_order() -> None:
    frozen = [_observation("A", row_index="0"), _observation("B", row_index="1")]
    same = [dict(row) for row in frozen]
    assert probe.frozen_table_agreement(frozen, same)["order_identical"] is True
    swapped = [dict(frozen[1]), dict(frozen[0])]
    agreement = probe.frozen_table_agreement(frozen, swapped)
    assert agreement["order_identical"] is False
    assert agreement["set_identical"] is True


def test_new_compound_inventory_counts_room_rows_per_compound() -> None:
    rows = [
        _observation("A", band=ROOM),
        _observation("N1", band=ROOM, row_index="1"),
        _observation("N1", band=ROOM, row_index="2", t_k="300.15"),
        _observation("N1", band=OUTSIDE, row_index="3"),
        _observation("N2", band=ROOM, origin=LOW, row_index="4"),
    ]
    for row in rows:
        row["_feature_source"] = probe.FROZEN_SOURCE
    inventory = probe.new_compound_inventory(rows, {"A"})
    assert inventory["compounds"] == 2
    assert inventory["rows_total"] == 4
    assert inventory["room_rows_total"] == 3
    assert inventory["compounds_with_a_room_row"] == 2
    assert inventory["room_row_histogram"] == {"1": 1, "2": 1}
    assert inventory["per_compound"]["N1"]["room_rows"] == 2
    assert inventory["per_compound"]["N1"]["rows_by_band"] == {OUTSIDE: 1, ROOM: 2}


def test_new_compound_inventory_splits_by_feature_source() -> None:
    rows = [
        _observation("N1", band=ROOM),
        _observation("N2", band=ROOM, row_index="1"),
    ]
    for row in rows:
        row["_feature_source"] = (
            probe.NEW_XTB_SOURCE if row["inchikey"] == "N1" else probe.FROZEN_SOURCE
        )
    inventory = probe.new_compound_inventory(rows, set())
    assert inventory["compounds_by_feature_source"] == {
        probe.FROZEN_SOURCE: 1,
        probe.NEW_XTB_SOURCE: 1,
    }


def test_featureless_compound_report_groups_by_compound_and_band(tmp_path: Path) -> None:
    rows = [
        _observation("A", name="no-xTB", row_index="0"),
        _observation("A", name="no-xTB", row_index="1", band=OUTSIDE),
        _observation("B", name="has-xTB", row_index="2"),
    ]
    path = _observation_file(tmp_path, rows)
    report = probe.featureless_compound_report(path, {"B": {}})
    assert report["compounds"] == 1
    assert report["rows_total"] == 2
    assert report["per_compound"]["A"]["rows_by_band"] == {OUTSIDE: 1, ROOM: 1}
    assert report["per_compound"]["A"]["origins"] == [ZERO]


def test_room_gate_audit_counts_rows_lost_to_the_feature_gate(tmp_path: Path) -> None:
    rows = [
        _observation("A", band=ROOM, row_index="0"),
        _observation("A", band=OUTSIDE, row_index="1"),
        _observation("IL", band=ROOM, row_index="2", origin=ZERO),
        _observation("N1", band=ROOM, origin=LOW, row_index="3"),
    ]
    path = _observation_file(tmp_path, rows)
    report = probe.room_gate_audit(path, {"A": {}, "N1": {}})
    assert report["before_total"] == 3
    assert report["after_total"] == 2
    assert report["before_the_feature_gate"] == {ZERO: 2, LOW: 1}
    assert report["after_the_feature_gate"] == {ZERO: 1, LOW: 1}
    assert report["compounds_losing_room_rows"] == {
        "IL": {"name": "compound", "origin": ZERO, "room_rows": 1}
    }


# --------------------------------------------------------------------------- #
# target statistics
# --------------------------------------------------------------------------- #


def test_value_stats_handles_an_empty_block() -> None:
    assert probe.value_stats(np.zeros(0)) == {"rows": 0}


def test_value_stats_reports_the_moments_it_promises() -> None:
    stats = probe.value_stats(np.asarray([1.0, 2.0, 3.0, 4.0]))
    assert stats["rows"] == 4
    assert stats["mean"] == pytest.approx(2.5)
    assert stats["median"] == pytest.approx(2.5)
    assert stats["min"] == 1.0
    assert stats["max"] == 4.0
    assert stats["rows_above_60"] == 0


def test_added_row_targets_separate_the_widened_rows() -> None:
    target = np.asarray([1.0, 2.0, 3.0, 4.0])
    keys = np.asarray(["A", "A", "N1", "N2"])
    base = np.asarray([True, True, False, False])
    widened = np.asarray([True, True, True, True])
    masks = {
        "paired_base": (base, base),
        "paired_plus_coverage": (base, widened),
        "paired_plus_new_xtb": (base, widened),
        "paired_plus_v03_block": (base, base),
    }
    out = probe.added_row_targets(masks, target, keys)
    assert out["paired_base_pool"]["rows"] == 2
    assert out["paired_plus_coverage"]["rows_added"] == 2
    assert out["paired_plus_coverage"]["compounds_added"] == 2
    assert out["paired_plus_coverage"]["added"]["mean"] == pytest.approx(3.5)
    assert out["paired_plus_v03_block"]["rows_added"] == 0

# --------------------------------------------------------------------------- #
# the splitter, the paired contract and the widening arithmetic
# --------------------------------------------------------------------------- #


def _synthetic_matrices(rows: list[dict[str, str]]):
    keys = [row["inchikey"] for row in rows]
    target = np.asarray([float(row["epsilon"]) for row in rows], dtype=float)
    temperatures = np.asarray([float(row["T_K"]) for row in rows], dtype=float)
    morgan = np.zeros((len(rows), 4), dtype=float)
    physical = np.column_stack([temperatures, np.ones(len(rows))])
    return morgan, physical, target, temperatures, keys


def _stub_run_protocol(record: list[dict[str, object]]):
    """A stand-in for the XGBoost runner: it records the folds and predicts nothing."""

    def stub(protocol, splits, *, morgan, physical, target, temperatures, groups):
        fold_rows: list[dict[str, object]] = []
        for repeat, fold, train_index, test_index in splits:
            record.append(
                {
                    "protocol": protocol,
                    "repeat": repeat,
                    "fold": fold,
                    "train": tuple(int(index) for index in train_index),
                    "test": tuple(int(index) for index in test_index),
                }
            )
            fold_rows.append(
                {
                    "protocol": protocol,
                    "representation": probe.HYBRID,
                    "repeat": repeat,
                    "fold": fold,
                    "train_rows": int(train_index.size),
                    "test_rows": int(test_index.size),
                    "train_compounds": 0,
                    "test_compounds": 0,
                    "mae": 0.0,
                    "rmse": 0.0,
                    "r2": 0.0,
                    "spearman": 0.0,
                }
            )
        return fold_rows, [], [], {"folds": len(fold_rows)}

    return stub


def _run_protocol_with_stub(monkeypatch, protocol, *, rows, score_mask, train_mask, n_splits=3):
    record: list[dict[str, object]] = []
    monkeypatch.setattr(probe, "run_protocol", _stub_run_protocol(record))
    morgan, physical, target, temperatures, groups = _synthetic_matrices(rows)
    result = probe.run_coverage_protocol(
        protocol,
        splitter="grouped",
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=score_mask,
        train_mask=train_mask,
        n_splits=n_splits,
        n_repeats=2,
        seed=42,
    )
    return result, record


def test_own_mode_random_row_splits_cover_every_scored_row_once_per_repeat() -> None:
    mask = np.asarray([True, True, True, True, True, False])
    splits = list(probe.own_mode_random_row_splits(mask, n_splits=5, n_repeats=2, seed=42))
    assert len(splits) == 10
    for repeat in range(2):
        seen: list[int] = []
        for item_repeat, _fold, _train, test in splits:
            if item_repeat == repeat:
                seen.extend(int(index) for index in test)
        assert sorted(seen) == [0, 1, 2, 3, 4]


def test_paired_protocols_share_one_scored_fold_assignment(monkeypatch) -> None:
    rows = [
        _observation("A", row_index="0", epsilon="1"),
        _observation("A", row_index="1", epsilon="2", t_k="310.15"),
        _observation("B", row_index="2", epsilon="3"),
        _observation("B", row_index="3", epsilon="4", t_k="310.15"),
        _observation("C", row_index="4", epsilon="5"),
        _observation("C", row_index="5", epsilon="6", t_k="310.15"),
        _observation("D", row_index="6", epsilon="7"),
        _observation("D", row_index="7", epsilon="8", t_k="310.15"),
    ]
    score = np.asarray([True] * 6 + [False] * 2)
    widened = np.ones(8, dtype=bool)
    base, _ = _run_protocol_with_stub(
        monkeypatch, "paired_base", rows=rows, score_mask=score, train_mask=score
    )
    plus, _ = _run_protocol_with_stub(
        monkeypatch, "paired_plus_coverage", rows=rows, score_mask=score, train_mask=widened
    )
    assert probe.scored_fold_signature(base["splits"]) == probe.scored_fold_signature(plus["splits"])
    assert base["audit"]["folds_with_a_straddling_compound"] == 0
    assert plus["audit"]["training_only_compounds"] == ["D"]
    assert plus["meta"]["train_pool_rows"] == 8
    for _repeat, _fold, train_index, _test in plus["splits"]:
        assert {6, 7}.issubset({int(index) for index in train_index})


def test_training_expansion_is_counted_from_the_folds_that_ran(monkeypatch) -> None:
    rows = [
        _observation("A", row_index="0"),
        _observation("A", row_index="1", t_k="310.15"),
        _observation("B", row_index="2"),
        _observation("B", row_index="3", t_k="310.15"),
        _observation("C", row_index="4"),
        _observation("C", row_index="5", t_k="310.15"),
        _observation("D", row_index="6"),
        _observation("D", row_index="7", t_k="310.15"),
    ]
    score = np.asarray([True] * 6 + [False] * 2)
    widened = np.ones(8, dtype=bool)
    base, _ = _run_protocol_with_stub(
        monkeypatch, "paired_base", rows=rows, score_mask=score, train_mask=score
    )
    plus, _ = _run_protocol_with_stub(
        monkeypatch, "paired_plus_coverage", rows=rows, score_mask=score, train_mask=widened
    )
    masks = {
        "paired_base": (score, score),
        "paired_plus_coverage": (score, widened),
        "paired_plus_new_xtb": (score, widened),
        "paired_plus_v03_block": (score, score),
    }
    table = probe.training_expansion(
        masks,
        splits_by_protocol={
            "paired_base": base["splits"],
            "paired_plus_coverage": plus["splits"],
            "paired_plus_new_xtb": plus["splits"],
            "paired_plus_v03_block": base["splits"],
        },
    )
    assert table["paired_base"]["rows_added_over_base"] == 0
    assert table["paired_plus_coverage"]["rows_added_over_base"] == 2
    assert table["paired_plus_coverage"]["folds_compared"] == len(plus["splits"])
    # D has no fold, so every fold may fit both of its rows.
    assert table["paired_plus_coverage"]["extra_rows_fitted_per_fold_mean"] == 2.0
    assert table["paired_plus_coverage"]["extra_rows_fitted_total"] == 2 * len(plus["splits"])


def test_training_expansion_rejects_a_fold_order_mismatch(monkeypatch) -> None:
    rows = [
        _observation("A", row_index="0"),
        _observation("A", row_index="1", t_k="310.15"),
        _observation("B", row_index="2"),
        _observation("B", row_index="3", t_k="310.15"),
        _observation("C", row_index="4"),
        _observation("C", row_index="5", t_k="310.15"),
    ]
    score = np.ones(6, dtype=bool)
    base, _ = _run_protocol_with_stub(
        monkeypatch, "paired_base", rows=rows, score_mask=score, train_mask=score
    )
    shuffled = [
        (repeat + 1, fold, train, test) for repeat, fold, train, test in base["splits"]
    ]
    masks = {name: (score, score) for name in probe.FIXED_POOL_PROTOCOLS}
    with pytest.raises(ValueError, match="fold order does not match"):
        probe.training_expansion(
            masks,
            splits_by_protocol={
                "paired_base": base["splits"],
                **{
                    name: shuffled
                    for name in probe.FIXED_POOL_PROTOCOLS
                    if name != "paired_base"
                },
            },
        )


def test_random_row_reference_straddles_while_grouped_never_does(monkeypatch) -> None:
    rows = [
        _observation(key, row_index=str(index), t_k=str(298.15 + 5 * index))
        for index, key in enumerate(["A", "A", "A", "B", "B", "B", "C", "C", "C", "D", "D", "D"])
    ]
    mask = np.ones(12, dtype=bool)
    record: list[dict[str, object]] = []
    monkeypatch.setattr(probe, "run_protocol", _stub_run_protocol(record))
    morgan, physical, target, temperatures, groups = _synthetic_matrices(rows)
    common = {
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "temperatures": temperatures,
        "groups": groups,
        "score_mask": mask,
        "train_mask": mask,
        "n_splits": 3,
        "n_repeats": 2,
        "seed": 42,
    }
    grouped = probe.run_coverage_protocol("extended_pool_room", splitter="grouped", **common)
    leak = probe.run_coverage_protocol(
        "extended_pool_room_random_row", splitter="random_row", **common
    )
    assert grouped["audit"]["folds_with_a_straddling_compound"] == 0
    assert leak["audit"]["folds_with_a_straddling_compound"] == len(leak["splits"])
    assert leak["audit"]["max_straddling_compounds_in_a_fold"] > 0
    assert grouped["meta"]["splitter"] == "grouped"
    assert leak["meta"]["splitter"] == "random_row"


def test_run_coverage_protocol_rejects_an_unknown_splitter() -> None:
    with pytest.raises(ValueError, match="unknown splitter"):
        probe.run_coverage_protocol(
            "paired_base",
            splitter="magic",
            morgan=np.zeros((1, 1)),
            physical=np.zeros((1, 1)),
            target=np.zeros(1),
            temperatures=[298.15],
            groups=["A"],
            score_mask=[True],
            train_mask=[True],
            n_splits=5,
            n_repeats=1,
            seed=42,
        )


def test_run_coverage_protocol_records_a_pool_too_thin_for_the_folds(monkeypatch) -> None:
    rows = [_observation("A"), _observation("B", row_index="1")]
    mask = np.ones(2, dtype=bool)
    monkeypatch.setattr(probe, "run_protocol", _stub_run_protocol([]))
    morgan, physical, target, temperatures, groups = _synthetic_matrices(rows)
    result = probe.run_coverage_protocol(
        "paired_base",
        splitter="grouped",
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=mask,
        train_mask=mask,
        n_splits=5,
        n_repeats=2,
        seed=42,
    )
    assert result["meta"]["executed_repeats"] == 0
    assert result["meta"]["folds"] == 0
    assert "not run" in result["meta"]["note"]
    assert result["fold_rows"] == []


def test_splitter_contract_detects_a_mismatched_scored_pool() -> None:
    block = {
        "protocols": {
            "paired_base": {"scored_rows": 457, "compounds_scored": 97, "folds": 50},
            "paired_plus_coverage": {"scored_rows": 457, "compounds_scored": 97, "folds": 50},
            "paired_plus_new_xtb": {"scored_rows": 457, "compounds_scored": 97, "folds": 50},
            "paired_plus_v03_block": {"scored_rows": 458, "compounds_scored": 97, "folds": 50},
        },
        "folds_are_shared": True,
    }
    contract = probe.splitter_contract(block)
    assert contract["scored_rows_identical"] is False
    assert contract["compounds_scored_identical"] is True
    assert contract["fold_counts_identical"] is True
    assert contract["folds_are_shared"] is True

# --------------------------------------------------------------------------- #
# summaries, verdicts and artefacts
# --------------------------------------------------------------------------- #


def _metric_block(**metrics: float) -> dict[str, dict[str, float]]:
    return {name: {"mean": value} for name, value in metrics.items()}


def _fake_summary(
    grouped_r2: float,
    leak_r2: float,
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    return {
        "extended_pool_room": {
            probe.HYBRID: _metric_block(r2=grouped_r2, mae=7.0, spearman=0.85)
        },
        probe.LEAK_REFERENCE_PROTOCOL: {
            probe.HYBRID: _metric_block(r2=leak_r2, mae=4.0, spearman=0.93)
        },
    }


def _fake_audits(straddling: int, max_straddling: int) -> dict[str, dict[str, object]]:
    return {
        "extended_pool_room": {
            "folds": 50,
            "scored_rows_total": 5840,
            "folds_with_a_straddling_compound": 0,
            "max_straddling_compounds_in_a_fold": 0,
        },
        probe.LEAK_REFERENCE_PROTOCOL: {
            "folds": 50,
            "scored_rows_total": 5840,
            "folds_with_a_straddling_compound": straddling,
            "max_straddling_compounds_in_a_fold": max_straddling,
        },
    }


def test_leak_comparison_sizes_the_inflation_and_nothing_else() -> None:
    block = probe.leak_comparison(_fake_summary(0.4783, 0.6748), _fake_audits(50, 56))
    assert block["available"] is True
    assert block["scored_rows_per_fold"] == 116
    assert block["inflation"]["r2"] == pytest.approx(0.1965, abs=1e-4)
    assert block["random_row_folds_with_a_straddling_compound"] == 50
    assert "never a conclusion number" in block["note"]


def test_leak_comparison_is_unavailable_without_the_reference_protocol() -> None:
    assert probe.leak_comparison({"extended_pool_room": {}}, _fake_audits(50, 56)) == {
        "available": False
    }


def _chain(delta_r2: float) -> list[dict[str, object]]:
    return [
        {
            "available": True,
            "base": "paired_base",
            "widened": "paired_plus_coverage",
            "delta_r2": delta_r2,
            "metrics": {
                "r2": {"base": 0.4, "widened": 0.4 + delta_r2, "delta": delta_r2},
                "mae": {"base": 8.0, "widened": 7.0, "delta": -1.0},
                "spearman": {"base": 0.7, "widened": 0.8, "delta": 0.1},
            },
        }
    ]


def test_build_verdict_reads_the_paired_delta() -> None:
    verdict = probe.build_verdict(
        _chain(0.1241), integrity={"ok": True}, added_compounds=50
    )
    assert verdict["decision"] == "helps"
    assert verdict["delta_r2"] == pytest.approx(0.1241)
    assert verdict["delta_mae"] == -1.0
    assert "50 compounds" in verdict["statement"]


def test_build_verdict_stamps_an_integrity_failure_as_unverified() -> None:
    verdict = probe.build_verdict(
        _chain(0.1241), integrity={"ok": False}, added_compounds=50
    )
    assert verdict["decision"] == "unverified"
    assert verdict["integrity_ok"] is False


def test_build_verdict_reports_a_negative_delta_as_hurting() -> None:
    verdict = probe.build_verdict(_chain(-0.05), integrity={"ok": True}, added_compounds=50)
    assert verdict["decision"] == "hurts"


def test_build_verdict_handles_a_missing_primary_step() -> None:
    verdict = probe.build_verdict([], integrity={"ok": True}, added_compounds=50)
    assert verdict["available"] is False
    assert verdict["decision"] == "not run"


def _published(hybrid_r2: float) -> dict[str, object]:
    published = {
        representation: _metric_block(r2=0.1, mae=1.0, rmse=1.0, spearman=0.1)
        for representation in probe.REPRESENTATIONS
    }
    published[probe.HYBRID] = _metric_block(r2=hybrid_r2, mae=8.0, rmse=14.0, spearman=0.7)
    return {
        "published": published,
        "published_hybrid_r2": hybrid_r2,
    }


def test_compare_room_band_reference_is_bit_exact_on_identical_numbers() -> None:
    reference = _published(0.4091179943351143)
    mine = {probe.ROOM_BAND_REFERENCE_PROTOCOL: reference["published"]}
    comparison = probe.compare_room_band_reference(mine, reference)
    assert comparison["bit_exact"] is True
    assert comparison["max_abs_delta"] == 0.0
    assert comparison["hybrid_r2"] == 0.4091179943351143


def test_compare_room_band_reference_catches_a_drifted_pipeline() -> None:
    reference = _published(0.4091179943351143)
    drifted = {
        representation: dict(metrics)
        for representation, metrics in reference["published"].items()  # type: ignore[union-attr]
    }
    drifted[probe.HYBRID] = _metric_block(
        r2=0.4091179943351143 + 1e-12, mae=8.0, rmse=14.0, spearman=0.7
    )
    comparison = probe.compare_room_band_reference(
        {probe.ROOM_BAND_REFERENCE_PROTOCOL: drifted}, reference
    )
    assert comparison["bit_exact"] is False
    assert comparison["max_abs_delta"] > 0.0


def test_compare_room_band_reference_reports_a_missing_side() -> None:
    comparison = probe.compare_room_band_reference({}, _published(0.4))
    assert comparison["available"] is False
    assert comparison["bit_exact"] is None


def test_row_fingerprint_is_column_ordered() -> None:
    row = {column: column for column in probe.FINGERPRINT_COLUMNS}
    row["source_row_index"] = "7"
    assert probe.row_fingerprint(row) == (
        "inchikey",
        "T_K",
        "epsilon",
        "smiles",
        "source_doi",
        "7",
    )


def test_write_artifacts_emits_lf_only_tables(tmp_path: Path) -> None:
    fold_row = dict.fromkeys(probe.FOLD_COLUMNS, 0)
    fold_row.update({"protocol": "paired_base", "representation": probe.HYBRID})
    repeat_row = {name: 0.0 for name in probe.METRIC_NAMES}
    repeat_row.update({"protocol": "paired_base", "representation": probe.HYBRID, "repeat": 0})
    prediction_row = dict.fromkeys(probe.PREDICTION_COLUMNS, 0)
    prediction_row.update({"protocol": "paired_base", "representation": probe.HYBRID})
    outputs = probe.write_artifacts(
        tmp_path,
        "stem",
        fold_rows=[fold_row],
        repeat_rows=[repeat_row],
        prediction_rows=[prediction_row],
    )
    assert set(outputs) == {"folds", "repeats", "predictions"}
    for relative in outputs.values():
        candidate = Path(relative)
        path = candidate if candidate.is_absolute() else REPOSITORY_ROOT / candidate
        raw = path.read_bytes()
        assert b"\r" not in raw, relative
        header = raw.decode("utf-8").splitlines()[0]
        assert header.startswith("protocol,representation,repeat")


# --------------------------------------------------------------------------- #
# the real repository tables (still offline: no network is touched)
# --------------------------------------------------------------------------- #


requires_real_tables = pytest.mark.skipif(
    not probe.COVERAGE_PATH.exists() or not probe.NEW_FEATURES_PATH.exists(),
    reason="the v11plus tables are not present in this checkout",
)


@requires_real_tables
def test_real_reference_json_still_holds_the_pinned_literal() -> None:
    reference = probe.read_room_band_reference()
    assert reference["published_hybrid_r2"] == probe.ROOM_BAND_HYBRID_R2_REFERENCE
    assert reference["matches_literal"] is True


@requires_real_tables
def test_real_new_compounds_all_carry_usable_features() -> None:
    merged, report = probe.merge_feature_blocks()
    coverage_rows, dropped = probe.load_coverage_table(probe.COVERAGE_PATH, merged)
    v11_rows, _frozen, _v11_dropped = probe.load_table(probe.OBSERVATIONS_PATH, probe.FEATURES_PATH)
    v11_keys = {str(row["inchikey"]) for row in v11_rows}
    inventory = probe.new_compound_inventory(coverage_rows, v11_keys)
    assert inventory["compounds"] == 50
    assert inventory["compounds_with_a_room_row"] == 50
    assert inventory["room_rows_total"] == 127
    assert inventory["room_row_histogram"] == {"1": 19, "2": 7, "3": 13, "5": 11}
    assert set(inventory["per_compound"]) == set(
        json.loads(probe.COVERAGE_SUMMARY_PATH.read_text(encoding="utf-8"))[
            "compounds_added_list"
        ]
    )
    assert report["merged_usable"] == 276
    assert dropped == {"no_xtb_features": 36}


@requires_real_tables
def test_real_pools_have_the_shape_the_benchmark_assumes() -> None:
    merged, _report = probe.merge_feature_blocks()
    coverage_rows, _dropped = probe.load_coverage_table(probe.COVERAGE_PATH, merged)
    v11_rows, _frozen, _v11_dropped = probe.load_table(probe.OBSERVATIONS_PATH, probe.FEATURES_PATH)
    agreement = probe.frozen_table_agreement(v11_rows, coverage_rows)
    assert agreement["order_identical"] is True

    room = [
        row
        for row in coverage_rows
        if str(row["temperature_band"]) == ROOM
        and str(row["observation_origin"]) == ZERO
    ]
    assert len(room) == 457
    assert len({str(row["inchikey"]) for row in room}) == 97

    every_room = [row for row in coverage_rows if str(row["temperature_band"]) == ROOM]
    assert len(every_room) == 584
    assert len({str(row["inchikey"]) for row in every_room}) == 147

    gate = probe.room_gate_audit(probe.COVERAGE_PATH, merged)
    assert gate["before_total"] == 587
    assert gate["after_total"] == 584
    assert len(gate["compounds_losing_room_rows"]) == 3
    assert {item["origin"] for item in gate["compounds_losing_room_rows"].values()} == {ZERO}