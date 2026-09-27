"""Guards for the Week 17 shot-16 representation seed-robustness probe.

The audit of shots 12-15 (reports/dielectric_pool_expansion_audit.md, Q7) left one
number on the books that nothing in the delivery package explained: the only reading
above 0.60 in the whole W17 record is ``full_table_lever4`` / ``Physical`` =
0.6080587938801277, and it is a *single-representation* reading that the pre-registered
primary criterion (the Morgan+Physical hybrid) does not cover, so it may never be
promoted.  ``probes/dielectric_representation_seed_robustness.py`` asks the separate,
answerable question -- does that ordering survive a fresh fold randomisation? -- and
this module keeps its three promises honest: the frozen side does not move, the
seed-42 anchors reproduce bit for bit, and nothing gets promoted.

Everything here is offline: no network, no xTB, no fitting.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.dielectric_coordination_block import REPEAT_COLUMNS_OUT

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_representation_seed_robustness_prereg.json"
SUMMARY = ROOT / "probes/dielectric_representation_seed_robustness_summary.json"
REPORT = ROOT / "reports/dielectric_representation_seed_robustness.md"
SCRIPT = ROOT / "probes/dielectric_representation_seed_robustness.py"
ARTIFACT = ROOT / "probes/artifacts/dielectric_representation_seed_robustness_repeats.csv"

SEED_42_PHYSICAL = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
ANCHORS = {
    "baseline_hybrid": 0.4091179943351143,
    "full_table_hybrid": 0.530028742596643,
    "full_table_lever4": 0.5433111678100043,
}
SEEDS = [42, 1234, 2026, 31337, 7]
REPRESENTATIONS = ["Morgan", "Physical", "Morgan+Physical"]
VERDICTS = ("confirmed_out_of_seed", "partially_confirmed", "refuted_seed_42_artifact")
ANCHOR_TOLERANCE = 1e-09


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def test_prereg_is_locked_and_pins_the_question_before_the_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["seeds"] == SEEDS
    assert prereg["decision_rule"]["primary_arm"] == "full_table_lever4"
    for key in ("confirmed", "partial", "refuted"):
        assert key in prereg["decision_rule"]
    assert "不提升" in prereg["promotion_rule"]
    # The disclosure has to say out loud that seed 42 was already known: the probe
    # is a robustness re-measurement, never a blind confirmation.
    assert "不是盲法确认" in prereg["disclosure"]
    assert any("0.6080587938801277" in item for item in prereg["known_before_locking"])


def test_the_summary_reproduces_the_seed_42_anchors_bit_for_bit() -> None:
    summary = _summary()
    assert summary["anchors"]["reproduced"] is True
    assert summary["anchors"]["tolerance"] == ANCHOR_TOLERANCE
    measured = {row["arm"]: row for row in summary["anchors"]["rows"]}
    assert set(measured) == set(ANCHORS)
    for arm, expected in ANCHORS.items():
        row = measured[arm]
        assert row["ok"] is True
        assert row["expected"] == expected
        assert abs(row["measured"] - expected) <= ANCHOR_TOLERANCE
    assert summary["contract"]["anchor_seed"] == 42


def test_the_probe_records_the_6081_reading_and_never_promotes() -> None:
    summary = _summary()
    assert summary["seed42_single_representation"] == SEED_42_PHYSICAL
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert promotion["frozen_headline"] == FROZEN_HEADLINE
    assert promotion["frozen_baseline"] == FROZEN_BASELINE
    assert "non-blind" in promotion["reason"]


def test_the_verdict_is_one_of_the_pre_registered_outcomes() -> None:
    hypothesis = _summary()["hypothesis"]
    assert hypothesis["arm"] == "full_table_lever4"
    assert hypothesis["total_seeds"] == len(SEEDS)
    per_seed = hypothesis["per_seed"]
    assert [row["seed"] for row in per_seed] == SEEDS
    positive = sum(1 for row in per_seed if row["delta"] > 0.0)
    assert positive == hypothesis["positive_seeds"]
    if positive == len(SEEDS):
        expected = "confirmed_out_of_seed"
    elif positive >= 3:
        expected = "partially_confirmed"
    else:
        expected = "refuted_seed_42_artifact"
    assert hypothesis["verdict"] == expected
    assert hypothesis["verdict"] in VERDICTS


def test_the_frozen_side_did_not_move_between_seeds() -> None:
    summary = _summary()
    assert summary["contract"]["n_splits"] == 5
    assert summary["contract"]["n_repeats"] == 10
    assert summary["contract"]["representations"] == REPRESENTATIONS
    assert summary["contract"]["seeds"] == SEEDS
    assert summary["pool"]["base_rows"] == 2029
    assert summary["pool"]["scored_rows"] == 457
    for row in summary["seed_rows"]:
        assert row["repeats"] == 10
    seed42 = {
        (row["arm"], row["representation"]): row["r2_mean"]
        for row in summary["seed_rows"]
        if row["seed"] == 42
    }
    for arm, expected in ANCHORS.items():
        assert seed42[(arm, "Morgan+Physical")] == pytest.approx(expected, abs=ANCHOR_TOLERANCE)
    assert seed42[("full_table_lever4", "Physical")] == pytest.approx(
        SEED_42_PHYSICAL, abs=ANCHOR_TOLERANCE
    )


def test_the_report_discloses_that_6081_stays_unpromoted() -> None:
    text = _report_text()
    for needle in (
        "0.6080587938801277",
        "本探针**非盲**",
        "任何读数一律不提升",
        "4766400383507876",
        "4091179943351143",
        "**不是**盲法确认",
    ):
        assert needle in text, needle
    assert "诊断性" in text


def test_the_summary_carries_a_clean_leakage_audit() -> None:
    """Shot 13 shipped a fold-leak block; this probe has to ship one too."""

    leakage = _summary()["leakage"]
    assert leakage["clean"] is True
    assert len(leakage["by_seed_arm"]) == len(SEEDS) * 3
    for block in leakage["by_seed_arm"].values():
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0


def test_the_report_answers_the_target_question_and_names_the_counterexample() -> None:
    """The audit asked for three disclosures; all three have to be in the prose.

    (a) the arm is shot 13 post-hoc best arm and not a co-primary, so the claim is
    scoped to that arm; (b) the same probe reverses on the hybrid arm; (c) the 0.60
    (and now 0.70) target is answered out loud, with the seed-42 bias stated.
    """

    text = _report_text()
    for needle in (
        "先回答那个问题",
        "**没有达到。**",
        "0.586114",
        "4/4",
        "事后最高臂",
        "**5/5 反向**",
        "0.523136",
        "0.486277",
        "R² > 0.70",
        "folds_with_a_straddling_compound",
    ):
        assert needle in text, needle


def test_the_script_asserts_the_6081_constant_against_the_refit() -> None:
    """The headline constant may not be decoration: the script re-checks it."""

    text = SCRIPT.read_text(encoding="utf-8")
    assert "the seed-42 single-representation reading moved" in text
    assert "a scored compound straddled a fold; refusing to continue" in text


def test_the_artifact_keeps_the_frozen_repeat_schema() -> None:
    with ARTIFACT.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == list(REPEAT_COLUMNS_OUT)
    # one row per (arm, representation, repeat): 5 seeds x 3 arms x 3 representations
    # x 10 repeats.
    assert len(rows) == len(SEEDS) * 3 * 3 * 10
    assert b"\r\n" not in ARTIFACT.read_bytes()
    arms = {row["arm"] for row in rows}
    assert len(arms) == len(SEEDS) * 3
    for seed in SEEDS:
        assert any(row["arm"].endswith("@seed" + str(seed)) for row in rows)


def test_the_script_locks_the_pool_and_the_anchors() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "ANCHOR_TOLERANCE = 1e-09",
        "the fold assignment moved; refusing to continue",
        "refusing to report anything else",
        "SEEDS = (42, 1234, 2026, 31337, 7)",
        "PRIMARY_ARM = ARM_FULL_L4",
    ):
        assert needle in text, needle

