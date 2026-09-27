"""Guards for the Week 17 pool-expansion shots 12-15.

The audit of shot 12 and shot 13 (reports/dielectric_pool_expansion_audit.md) filed one
remediation item these tests close: the pool-expansion scripts had no regression
guard, so the defects it found (a mislabelled start timestamp and a stale dict key
behind a print) could come back unnoticed.  Everything here is offline: no
network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import pytest

from probes.dielectric_pool_expansion_benchmark import (
    PHYSICAL_COLUMNS,
    build_splits,
    fold_signature,
    label_placebo_target,
    load_expansion,
)

ROOT = Path(__file__).resolve().parents[1]
V3_SUMMARY = ROOT / "probes/dielectric_pool_expansion_v3_summary.json"
V3_PREREG = ROOT / "probes/dielectric_pool_expansion_prereg_v3.json"
ANCHOR_PREREG = ROOT / "probes/dielectric_anchor_prereg.json"
ANCHOR_SUMMARY = ROOT / "probes/dielectric_anchor_summary.json"
ANCHOR_SUMMARY_LITERALS = {
    "baseline_hybrid": 0.4091179943351143,
    "full_table_lever4": 0.5433111678100043,
}


def _write_csv(path: Path, rows, columns) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")


def _feature_row(key: str) -> dict[str, str]:
    row = {"inchikey": key, "name": key, "smiles": "CCO", "status": "ok"}
    row.update({column: "1.0" for column in PHYSICAL_COLUMNS})
    return row


def _observation_row(key: str, **overrides) -> dict[str, str]:
    row = {
        "inchikey": key,
        "name": key,
        "smiles": "CCO",
        "T_K": "298.15",
        "epsilon": "20.0",
        "frequency_mhz": "",
        "phase": "liquid",
        "component_count": "1",
        "source_url": "https://example.invalid",
        "license": "CC0",
        "source_file_sha256": "0" * 64,
        "expansion_track": "test",
    }
    row.update(overrides)
    return row


def test_load_expansion_admits_a_clean_row_and_drops_each_bad_one(tmp_path: Path) -> None:
    keys = ("AAAA-BBBB-CCCC-D", "DDDD-EEEE-FFFF-G", "GGGG-HHHH-IIII-J", "JJJJ-KKKK-LLLL-M")
    features = tmp_path / "features.csv"
    _write_csv(features, [_feature_row(key) for key in keys], ("inchikey", "name", "smiles", "status", *PHYSICAL_COLUMNS))
    observations = tmp_path / "observations.csv"
    rows = [
        _observation_row(keys[0]),
        _observation_row(keys[1], T_K="350.00"),
        _observation_row(keys[2], epsilon="0.5"),
        _observation_row(keys[3], phase="gas"),
    ]
    _write_csv(observations, rows, tuple(rows[0]))

    kept, report = load_expansion(
        observations_path=observations,
        features_path=features,
        blocked_keys=set(),
        scoring_compounds=set(),
    )
    assert [str(row["inchikey"]) for row in kept] == [keys[0]]
    assert report["rows_admitted"] == 1
    assert report["dropout"]["temperature_out_of_the_room_band"] == 1
    assert report["dropout"]["epsilon_out_of_range"] == 1
    assert report["dropout"]["phase_is_not_liquid"] == 1


def test_load_expansion_drops_a_row_already_in_the_scored_pool(tmp_path: Path) -> None:
    key = "AAAA-BBBB-CCCC-D"
    features = tmp_path / "features.csv"
    _write_csv(features, [_feature_row(key)], ("inchikey", "name", "smiles", "status", *PHYSICAL_COLUMNS))
    observations = tmp_path / "observations.csv"
    _write_csv(observations, [_observation_row(key)], tuple(_observation_row(key)))

    kept, report = load_expansion(
        observations_path=observations,
        features_path=features,
        blocked_keys={(key, 298.15)},
        scoring_compounds={key},
    )
    assert kept == []
    assert report["dropout"]["duplicate_of_a_coverage_row"] == 1


def test_load_expansion_drops_a_compound_without_xtb_features(tmp_path: Path) -> None:
    key = "AAAA-BBBB-CCCC-D"
    features = tmp_path / "features.csv"
    _write_csv(features, [], ("inchikey", "name", "smiles", "status", *PHYSICAL_COLUMNS))
    observations = tmp_path / "observations.csv"
    _write_csv(observations, [_observation_row(key)], tuple(_observation_row(key)))

    kept, report = load_expansion(
        observations_path=observations,
        features_path=features,
        blocked_keys=set(),
        scoring_compounds=set(),
    )
    assert kept == []
    assert report["dropout"]["no_xtb_features"] == 1


def test_label_placebo_preserves_the_multiset_and_the_per_compound_counts() -> None:
    target = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    groups = ["A", "A", "B", "C", "C", "C"]
    mask = np.array([True, True, True, True, True, True])
    shuffled = label_placebo_target(target, groups, mask)

    assert sorted(shuffled.tolist()) == sorted(target.tolist())
    counts = {key: int((np.asarray(groups) == key).sum()) for key in set(groups)}
    assert counts == {"A": 2, "B": 1, "C": 3}
    assert label_placebo_target(target, groups, mask).tolist() == shuffled.tolist()


def test_label_placebo_leaves_rows_outside_the_mask_alone() -> None:
    target = np.array([1.0, 2.0, 3.0, 4.0])
    groups = ["A", "A", "B", "B"]
    mask = np.array([True, True, False, False])
    shuffled = label_placebo_target(target, groups, mask)
    assert shuffled[2] == 3.0
    assert shuffled[3] == 4.0
    assert sorted(shuffled[:2].tolist()) == [1.0, 2.0]


def test_build_splits_never_puts_a_compound_on_both_sides_of_a_fold() -> None:
    groups = [f"c{index}" for index in range(20) for _ in range(3)]
    scored = np.ones(len(groups), dtype=bool)
    splits = build_splits(groups, score_mask=scored, train_mask=scored)
    assert splits
    array = np.asarray(groups)
    for _repeat, _fold, train, test in splits:
        shared = set(array[np.asarray(train)].tolist()) & set(array[np.asarray(test)].tolist())
        assert shared == set()
    assert fold_signature(splits) == fold_signature(list(splits))


def test_shot14_summary_reproduces_every_anchor_and_reports_the_miss() -> None:
    summary = json.loads(V3_SUMMARY.read_text(encoding="utf-8"))
    verdict = summary["verdict"]
    assert verdict["anchors_reproduced"] is True
    assert verdict["baseline_abs_gap"] <= 1e-09
    for name, item in verdict["reproduction_anchors"].items():
        assert item["reproduced"] is True, name
    assert verdict["co_primary_arms"] == [
        "full_table_lever4_lever8full",
        "static_lever4_lever8full",
    ]
    assert verdict["co_primaries_met"] is False
    assert verdict["decision"] == "co_primaries_missed"
    assert verdict["arm_a_pass"] is True
    assert verdict["arm_b_pass"] is True
    pool = summary["pool"]
    assert pool["base_rows"] == 2029
    assert pool["static_training_rows"] + pool["finite_frequency_training_rows"] == 2029
    assert pool["coordination_full_rows_with_the_block"] > pool["coordination_released_rows_with_the_block"]


def test_every_prereg_is_locked_before_the_summary_it_governs() -> None:
    """The audit's blocking finding, turned into a guard."""

    pairs = (
        (V3_PREREG, V3_SUMMARY),
        (ANCHOR_PREREG, ANCHOR_SUMMARY),
    )
    for prereg_path, summary_path in pairs:
        if not summary_path.is_file():
            continue
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        locked = str(prereg["locked_at_utc"])
        generated = str(summary["generated_at_utc"])
        assert locked <= generated, (str(prereg_path), locked, generated)
        assert str(summary["prereg"]["status"]) == "locked_before_run"


def test_shot15_anchor_arms_reproduce_the_shared_references() -> None:
    if not ANCHOR_SUMMARY.is_file():
        return
    summary = json.loads(ANCHOR_SUMMARY.read_text(encoding="utf-8"))
    arms = summary["arms"]
    for name, expected in ANCHOR_SUMMARY_LITERALS.items():
        assert abs(float(arms[name]["r2"]) - expected) <= 1e-09, name


def test_the_new_artifacts_are_lf_only_and_carry_no_bom() -> None:
    paths = [
        V3_SUMMARY,
        V3_PREREG,
        ROOT / "probes/dielectric_pool_expansion_prereg_v3.json",
        ROOT / "data/processed/dielectric_anchor_observations.csv",
        ROOT / "data/processed/dielectric_anchor_features.csv",
    ]
    for path in paths:
        if not path.is_file():
            continue
        blob = path.read_bytes()
        assert not blob.startswith(b"\xef\xbb\xbf"), str(path)
        assert b"\r\n" not in blob, str(path)


def test_the_anchor_block_holds_only_compounds_the_pool_never_had() -> None:
    from probes.build_dielectric_anchor_blocks import SOURCE_PATH, pool_keys, select_rows

    if not SOURCE_PATH.is_file():
        pytest.skip("the open_data_eps2 harvest is not present in this checkout")
    kept, _dropout = select_rows()
    blocked = pool_keys()
    assert kept
    for row in kept:
        assert row["inchikey"] not in blocked
        assert row["phase"] == "liquid"
        assert row["component_count"] == "1"
        assert 273.15 <= float(row["T_K"]) <= 353.15
        assert 1.0 < float(row["epsilon"]) <= 200.0


def test_the_reaxys_red_line_breach_stays_disclosed() -> None:
    """Section 28.33: one arm trained on Reaxys-restricted values.

    The reading is void, and the disclosure must not be silently dropped from either
    the report or the script that carries the path.
    """

    report = (ROOT / "reports/dielectric_pool_expansion_v3.md").read_text(encoding="utf-8")
    assert "红线登记" in report
    assert "禁止任何受限值进入池或特征" in report
    assert "widened_lever4_lever8full" in report
    assert "0.5151538934971656" in report
    assert "作废" in report

    script = (ROOT / "probes/dielectric_pool_expansion_v3.py").read_text(encoding="utf-8")
    assert "RED LINE" in script
    assert "reaxys_w17f" in script
