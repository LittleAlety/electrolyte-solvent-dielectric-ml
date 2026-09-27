"""Guards for the Week 18 lane A / P3 conformer-flexibility probe.

Lever 4 carried the conformer MEAN dipole into the dense block and stopped there.
The probe probes/dielectric_conformer_flexibility.py asks whether the conformer
SPREAD (std / range) and the conformer count add anything on top, with the pool, the
splitter, the scorer, the protocol and the frozen head all frozen.  These guards keep
its promises honest: the seed-42 anchor reproduces bit for bit or nothing is
reported, the fold audit stays clean, the pre-registered bar decides the verdict,
the coverage of the source table is published (including the fact that the conformer
count is a zero-variance column), the placebo is run and its scope defect is stated
instead of being glossed over, and no reading is promoted.

Everything here is offline: no network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_conformer_flexibility_prereg.json"
SUMMARY = ROOT / "probes/dielectric_conformer_flexibility_summary.json"
PLACEBO_SUMMARY = ROOT / "probes/dielectric_conformer_flexibility_placebo_summary.json"
REPORT = ROOT / "reports/dielectric_conformer_flexibility.md"
SCRIPT = ROOT / "probes/dielectric_conformer_flexibility.py"
ARTIFACT = ROOT / "probes/artifacts/dielectric_conformer_flexibility_repeats.csv"
PLACEBO_ARTIFACT = ROOT / "probes/artifacts/dielectric_conformer_flexibility_placebo_repeats.csv"

SEED_42_REFERENCE = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
TOLERANCE = 1e-09
SEEDS = (42, 1234, 2026, 31337, 7)
ARMS = ("reference_lever4", "plus_flexibility", "flexibility_only")
FLEXIBILITY_COLUMNS = ("dipole_D_conformer_std", "dipole_D_conformer_range", "n_conformers")
CONFIRM_BAR = 0.02
PARTIAL_BAR = 0.005
EXPECTED_COLUMNS = (
    "seed",
    "arm",
    "representation",
    "repeat",
    "r2",
    "mae",
    "rmse",
    "spearman",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
    "auc_gt15",
    "auc_gt30",
)
VERDICTS = ("confirmed", "partial", "refuted", "placebo")


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _placebo_summary() -> dict:
    return json.loads(PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def _report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_and_pins_the_bar_before_the_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["non_blind"] is True
    assert "0.6080587938801277" in prereg["non_blind_reason"]
    assert set(ARMS) == set(prereg["arms"])
    assert tuple(prereg["flexibility_columns"]) == FLEXIBILITY_COLUMNS
    frozen = prereg["frozen"]
    assert frozen["single_representation_anchor"] == SEED_42_REFERENCE
    assert frozen["headline"] == FROZEN_HEADLINE
    assert frozen["baseline"] == FROZEN_BASELINE
    assert frozen["anchor_tolerance"] == TOLERANCE
    assert frozen["random_state"] == 42
    assert tuple(frozen["seeds"]) == SEEDS
    rule = prereg["decision_rule"]
    assert rule["confirmed"] == "delta >= 0.02"
    assert "0.005" in rule["partial"]
    assert "cross_seed_mean_r2(plus_flexibility)" in rule["delta_definition"]
    assert "0.0" in prereg["missing_fill"]


def test_the_frozen_anchor_reproduces_bit_for_bit_or_the_probe_is_silent() -> None:
    summary = _summary()
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["tolerance"] == TOLERANCE
    rows = anchors["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["arm"] == "reference_lever4"
    assert row["seed"] == 42
    assert row["ok"] is True
    assert row["expected"] == SEED_42_REFERENCE
    assert abs(row["measured"] - SEED_42_REFERENCE) <= TOLERANCE
    assert row["abs_gap"] == 0.0


def test_the_seed_42_reference_reading_is_the_frozen_one() -> None:
    seeds = {int(row["seed"]): row for row in _summary()["seed_rows"] if row["arm"] == "reference_lever4"}
    assert seeds[42]["r2_mean"] == SEED_42_REFERENCE


def test_the_leakage_audit_is_clean_and_covers_every_seed() -> None:
    leakage = _summary()["leakage"]
    assert leakage["clean"] is True
    assert sorted(leakage["by_seed"], key=int) == [str(seed) for seed in sorted(SEEDS)]
    for block in leakage["by_seed"].values():
        assert block["folds"] == 50
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0


def test_the_artifact_carries_every_seed_and_arm_with_the_auc_columns() -> None:
    rows = _csv_rows(ARTIFACT)
    assert tuple(rows[0].keys()) == EXPECTED_COLUMNS
    assert len(rows) == len(SEEDS) * len(ARMS) * 10
    seen = defaultdict(set)
    for row in rows:
        seen[(int(row["seed"]), row["arm"])].add(int(row["repeat"]))
        assert row["representation"] == "Physical(lever4+flex)"
    for seed in SEEDS:
        for arm in ARMS:
            assert seen[(seed, arm)] == set(range(10))


def test_the_verdict_follows_the_registered_bar_and_is_not_promotable() -> None:
    summary = _summary()
    decision = summary["decision"]
    assert decision["verdict"] in VERDICTS
    assert decision["promotable"] is False
    assert decision["confirm_bar"] == CONFIRM_BAR
    assert decision["partial_bar"] == PARTIAL_BAR
    cross = summary["cross_seed"]
    delta = cross["plus_flexibility"] - cross["reference_lever4"]
    assert summary["delta_plus_minus_reference"] == delta
    if decision["verdict"] == "confirmed":
        expected = delta >= CONFIRM_BAR
    elif decision["verdict"] == "partial":
        expected = PARTIAL_BAR <= delta < CONFIRM_BAR
    else:
        expected = delta < PARTIAL_BAR
    assert expected is True
    per_seed = summary["per_seed_delta_plus_minus_reference"]
    assert sorted(per_seed, key=int) == [str(seed) for seed in sorted(SEEDS)]
    assert summary["seeds_with_a_positive_delta"] == sum(
        1 for value in per_seed.values() if value > 0.0
    )


def test_the_flexibility_coverage_is_published_with_the_constant_column_flagged() -> None:
    coverage = _summary()["flexibility"]["coverage"]
    assert coverage["source_rows"] == 276
    assert coverage["usable_rows"] == 274
    assert coverage["n_conformers_values"] == [8]
    assert coverage["n_conformers_is_constant"] is True
    assert 0 < coverage["rows_with_nonzero_std"] < coverage["usable_rows"]
    assert coverage["rows_with_nonzero_std"] == coverage["rows_with_nonzero_range"]
    alignment = _summary()["flexibility"]["alignment"]
    assert alignment["rows_with_a_conformer_row"] + alignment["rows_filled_with_zero"] == alignment["rows"]
    assert alignment["rows_filled_with_zero"] > 0
    text = _report_text()
    assert "零方差列" in text
    assert "不是柔性信息" in text


def test_the_placebo_was_run_and_its_scope_defect_is_stated() -> None:
    placebo = _summary()["placebo"]
    assert placebo["status"] == "ran"
    assert sorted(placebo["cross_seed"]) == sorted(ARMS)
    standalone = _placebo_summary()
    assert standalone["placebo"]["status"] == "this_run"
    assert standalone["placebo"]["cross_seed"] == placebo["cross_seed"]
    assert len(_csv_rows(PLACEBO_ARTIFACT)) == len(SEEDS) * len(ARMS) * 10
    text = _report_text()
    assert "只置换 457 个 scored 行" in text
    assert "不是" in text


def test_no_reading_is_promoted_and_the_frozen_numbers_are_quoted_unchanged() -> None:
    summary = _summary()
    assert summary["frozen_control"]["headline"] == FROZEN_HEADLINE
    assert summary["frozen_control"]["baseline"] == FROZEN_BASELINE
    assert summary["frozen_control"]["single_representation_anchor"] == SEED_42_REFERENCE
    assert summary["decision"]["promotable"] is False
    text = _report_text()
    assert "任何读数都不 promote" in text
    assert "0.4766400383507876" in text
    assert "0.4091179943351143" in text


def test_the_probe_keeps_the_frozen_head_and_the_source_table_pinned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277" in source
    assert "FROZEN_HEADLINE = 0.4766400383507876" in source
    assert "FROZEN_BASELINE = 0.4091179943351143" in source
    assert "XGB_PARAMS" in source
    assert "dielectric_xtb_full_table_migration_conformers.csv" in source
