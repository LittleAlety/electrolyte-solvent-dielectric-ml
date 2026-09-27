"""Guards for the Week 18 P2 Onsager/Kirkwood delta-learning lane.

The lane lives in `probes/dielectric_onsager_delta_w18.py`.  The repository already
shipped `tests/test_dielectric_onsager_delta_probe.py`, but that module imports the
Week 8 probe (`probes.dielectric_onsager_delta_probe`) and never touches a byte of the
W18 file -- so the exporter recorded P2 as "verified" while nothing exercised it.  This
module closes that gap and pins the W18 promises:

* the pre-registration is locked before the run and is pinned by digest;
* the seed-42 reference arm reproduces the frozen single-representation reading
  0.6080587938801277 bit for bit, and its cross-seed endpoint is 0.5861142332208197;
* the endpoint is the arithmetic mean of the per-seed 10-repeat means, recomputed here;
* the verdict follows the registered ladder and can be rebuilt from the summary alone;
* the leakage audit is clean and covers every locked seed;
* the frozen headline 0.4766400383507876 and baseline 0.4091179943351143 do not move,
  and nothing this lane produces is ever promoted.

Everything here is offline: the probe is never re-run and no model is fitted.  Every
reading is read back from the landed summary and compared against the pinned literals,
so moving a number in the probe requires moving a line of this file.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes/dielectric_onsager_delta_w18.py"
PREREG = ROOT / "probes/dielectric_onsager_delta_w18_prereg.json"
SUMMARY = ROOT / "probes/dielectric_onsager_delta_w18_summary.json"
REPORT = ROOT / "reports/dielectric_onsager_delta_w18.md"
REPEATS = ROOT / "probes/artifacts/dielectric_onsager_delta_w18_repeats.csv"
PLACEBO_SUMMARY = ROOT / "probes/dielectric_onsager_delta_w18_placebo_summary.json"

# The digest of probes/dielectric_onsager_delta_w18_prereg.json at lock time.
# A mutant that edits a locked preregistration has to edit this literal too.
PREREG_SHA256 = "7c936b53e99182ab7f4bbe03aa13620f11095f2fc6a85eed882ef36759a08c8b"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ARMS = (
    "reference_direct",
    "onsager_analytic_only",
    "onsager_delta_xgb",
    "onsager_delta_recomputed",
)
REFERENCE = "reference_direct"
JUDGED = ("onsager_delta_xgb", "onsager_delta_recomputed")
VERDICTS = ("confirmed", "partial", "refuted", "placebo")

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED = 0.5861142332208197
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
ANCHOR_TOLERANCE = 1e-09
CONFIRMED_BAR_R2 = 0.02
PARTIAL_BAR_R2 = 0.005
MIN_CONFIRMING_SEEDS = 5

FROZEN_PER_SEED = {
    42: 0.6080587938801277,
    1234: 0.5653494903237062,
    2026: 0.5848044432962747,
    31337: 0.5985324927011,
    7: 0.5738259459028902,
}

REPEATS_PER_CELL = 10
FOLDS_PER_SEED = 50
BASE_ROWS = 2029
SCORED_ROWS = 457
REPEAT_COLUMNS = (
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
)


def _summary() -> dict:
    if not SUMMARY.is_file():
        pytest.skip("probes/dielectric_onsager_delta_w18_summary.json has not landed yet")
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _placebo_summary() -> dict:
    if not PLACEBO_SUMMARY.is_file():
        pytest.skip(
            "probes/dielectric_onsager_delta_w18_placebo_summary.json has not landed yet"
        )
    return json.loads(PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def _prereg() -> dict:
    return json.loads(PREREG.read_text(encoding="utf-8"))


def _seed_rows(summary: dict) -> list[dict]:
    rows = summary["seed_rows"]
    assert isinstance(rows, list) and rows
    return rows


def _cross_by_arm(summary: dict) -> dict[str, dict]:
    rows = summary["cross_seed"]
    assert isinstance(rows, list), "cross_seed must be a per-arm list in this lane"
    return {str(row["arm"]): row for row in rows}


def _leakage_blocks(summary: dict) -> tuple[dict[str, dict], dict]:
    raw = summary["leakage"]
    assert isinstance(raw, dict)
    if "by_seed" in raw:
        blocks = {str(key): value for key, value in raw["by_seed"].items()}
    else:
        blocks = {
            str(key): value
            for key, value in raw.items()
            if str(key).lstrip("-").isdigit()
        }
    return blocks, raw


# --------------------------------------------------------------------------- #
# the pre-registration
# --------------------------------------------------------------------------- #


def test_the_prereg_is_locked_before_the_run_and_pinned_by_digest() -> None:
    raw = PREREG.read_bytes()
    assert raw.count(b"\r\n") == 0
    assert raw[:3] != b"\xef\xbb\xbf"
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    prereg = _prereg()
    assert prereg["status"] == "locked_before_run"
    assert prereg["task"] == "w18_p2_onsager_delta"
    assert set(prereg["anchors"]["per_seed_reference_direct"]) == {
        str(seed) for seed in SEEDS
    }
    assert prereg["representation"] == "Physical(lever4)"
    assert set(prereg["arms"]) == set(ARMS)
    assert len(prereg["arms"]) == len(ARMS)
    assert prereg["reference_arm"] == REFERENCE
    assert set(prereg["judged_arms"]) == set(JUDGED)
    assert prereg["frozen_protocol"]["n_splits"] == 5
    assert prereg["frozen_protocol"]["n_repeats"] == REPEATS_PER_CELL
    assert prereg["frozen_protocol"]["train_mask"] == "full_base (2029 base rows)"
    assert prereg["anchors"]["per_seed_reference_direct"][str(ANCHOR_SEED)] == FROZEN_SINGLE_REPRESENTATION
    assert prereg["anchors"]["cross_seed_reference_direct"] == FROZEN_CROSS_SEED
    rule = prereg["decision_rule"]
    assert rule["confirmed"].startswith("cross-seed mean of the arm")
    assert rule["min_confirming_seeds"] == MIN_CONFIRMING_SEEDS
    assert "0.02" in rule["confirmed"]
    assert "0.005" in rule["partial"]
    assert "no reading from this probe is promoted" in prereg["promotion_rule"]
    assert "0.4766400383507876" in prereg["promotion_rule"]
    assert "0.4091179943351143" in prereg["promotion_rule"]


def test_the_summary_records_the_same_locked_prereg_digest() -> None:
    summary = _summary()
    recorded = summary["prereg"]
    assert recorded["sha256"] == PREREG_SHA256
    assert recorded["status"] == "locked_before_run"
    assert recorded["schema"] == _prereg()["schema"]


# --------------------------------------------------------------------------- #
# the frozen side
# --------------------------------------------------------------------------- #


def test_nothing_is_promoted_and_the_frozen_side_did_not_move() -> None:
    summary = _summary()
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert promotion["frozen_headline"] == FROZEN_HEADLINE
    assert promotion["frozen_baseline"] == FROZEN_BASELINE
    assert summary["decisions"]["promotable"] is False


def test_the_frozen_side_is_still_written_into_the_script() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "FROZEN_HEADLINE = 0.4766400383507876",
        "FROZEN_BASELINE = 0.4091179943351143",
        "FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277",
        "FROZEN_CROSS_SEED = 0.5861142332208197",
        '"promoted": False',
        '"promotable": False',
    ):
        assert needle in text, needle
    assert "0.4766400383507876" in text
    assert "0.4091179943351143" in text


def test_the_pool_is_the_frozen_one() -> None:
    pool = _summary()["pool"]
    assert pool["base_rows"] == BASE_ROWS
    assert pool["scored_rows"] == SCORED_ROWS
    assert pool["representation"] == "Physical(lever4)"
    assert pool["folds_per_seed"] == {str(seed): FOLDS_PER_SEED for seed in SEEDS}


# --------------------------------------------------------------------------- #
# the anchor and the endpoint
# --------------------------------------------------------------------------- #


def test_the_anchor_reproduces_the_frozen_single_representation_reading() -> None:
    summary = _summary()
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["fold_signature_ok"] is True
    assert anchors["tolerance"] == ANCHOR_TOLERANCE
    rows = {int(row["seed"]): row for row in anchors["rows"]}
    assert set(rows) == set(SEEDS)
    for seed, expected in FROZEN_PER_SEED.items():
        row = rows[seed]
        assert row["expected"] == expected
        assert abs(float(row["measured"]) - expected) <= ANCHOR_TOLERANCE
        assert float(row["abs_gap"]) <= ANCHOR_TOLERANCE
        assert row["ok"] is True
    seed_42 = rows[ANCHOR_SEED]
    assert seed_42["expected"] == FROZEN_SINGLE_REPRESENTATION
    assert abs(float(seed_42["measured"]) - FROZEN_SINGLE_REPRESENTATION) <= ANCHOR_TOLERANCE


def test_the_cross_seed_reference_endpoint_matches_the_frozen_mean() -> None:
    summary = _summary()
    cross = summary["anchors"]["cross_seed"]
    assert cross["expected"] == FROZEN_CROSS_SEED
    assert cross["comparable"] is True
    assert {int(seed) for seed in cross["seeds_compared"]} == set(SEEDS)
    assert abs(float(cross["measured"]) - FROZEN_CROSS_SEED) <= ANCHOR_TOLERANCE
    assert abs(float(cross["abs_gap"])) <= ANCHOR_TOLERANCE
    decisions = summary["decisions"]
    assert abs(float(decisions["endpoint_reference_direct"]) - FROZEN_CROSS_SEED) <= ANCHOR_TOLERANCE
    rows = _cross_by_arm(summary)
    assert abs(float(rows[REFERENCE]["r2_seed_mean"]) - FROZEN_CROSS_SEED) <= ANCHOR_TOLERANCE


def test_every_seed_carries_every_arm_with_ten_repeats() -> None:
    rows = _seed_rows(_summary())
    seen = {(int(row["seed"]), str(row["arm"])) for row in rows}
    assert seen == {(seed, arm) for seed in SEEDS for arm in ARMS}
    for row in rows:
        assert row["repeats"] == REPEATS_PER_CELL
        assert row["representation"] == "Physical(lever4)"
        assert float(row["r2_sd"]) >= 0.0


def test_the_endpoint_is_the_mean_of_the_per_seed_readings() -> None:
    summary = _summary()
    rows = _seed_rows(summary)
    cross = _cross_by_arm(summary)
    decisions = summary["decisions"]
    reference = decisions["endpoint_reference_direct"]
    for arm in ARMS:
        values = [float(row["r2_mean"]) for row in rows if str(row["arm"]) == arm]
        assert len(values) == len(SEEDS)
        mean = sum(values) / len(values)
        assert abs(float(cross[arm]["r2_seed_mean"]) - mean) <= 1e-12
        assert abs(float(decisions["endpoint_" + arm]) - mean) <= 1e-12
        assert abs(float(cross[arm]["improvement_vs_reference"]) - (mean - reference)) <= 1e-12
    for seed, expected in FROZEN_PER_SEED.items():
        measured = [
            float(row["r2_mean"])
            for row in rows
            if int(row["seed"]) == seed and str(row["arm"]) == REFERENCE
        ]
        assert len(measured) == 1
        assert abs(measured[0] - expected) <= ANCHOR_TOLERANCE


# --------------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------------- #


def test_the_verdict_is_recomputed_from_the_cross_seed_ladder() -> None:
    summary = _summary()
    decisions = summary["decisions"]
    verdict = str(decisions["verdict"])
    assert verdict in VERDICTS
    reference = float(decisions["endpoint_reference_direct"])
    improvements = {arm: float(decisions["endpoint_" + arm]) - reference for arm in ARMS if arm != REFERENCE}
    best = max(JUDGED, key=lambda arm: (improvements[arm], arm))
    best_improvement = improvements[best]
    assert str(decisions["best_arm"]) == best
    assert abs(float(decisions["best_improvement"]) - best_improvement) <= 1e-12
    assert decisions["confirmed_bar_r2"] == CONFIRMED_BAR_R2
    assert decisions["partial_bar_r2"] == PARTIAL_BAR_R2
    assert decisions["min_confirming_seeds"] == MIN_CONFIRMING_SEEDS
    assert set(decisions["judged_arms"]) == set(JUDGED)
    placebo = bool(summary["placebo"])
    if placebo:
        expected = "placebo"
    elif best_improvement >= CONFIRMED_BAR_R2 and len(SEEDS) >= MIN_CONFIRMING_SEEDS:
        expected = "confirmed"
    elif best_improvement >= PARTIAL_BAR_R2:
        expected = "partial"
    else:
        expected = "refuted"
    assert verdict == expected, (verdict, expected, best_improvement)


# --------------------------------------------------------------------------- #
# the leakage audit
# --------------------------------------------------------------------------- #


def test_the_leakage_audit_is_clean_and_covers_every_seed() -> None:
    summary = _summary()
    blocks, raw = _leakage_blocks(summary)
    assert set(blocks) == {str(seed) for seed in SEEDS}
    for seed, block in blocks.items():
        assert block["folds"] == FOLDS_PER_SEED, seed
        assert block["folds_with_a_straddling_compound"] == 0, seed
        assert block["max_straddling_compounds_in_a_fold"] == 0, seed
    if "clean" in raw:
        assert raw["clean"] is True


# --------------------------------------------------------------------------- #
# the artifact and the report
# --------------------------------------------------------------------------- #


def test_the_placebo_board_exists_and_its_verdict_is_placebo() -> None:
    placebo = _placebo_summary()
    assert placebo["placebo"] is True
    assert placebo["decisions"]["verdict"] == "placebo"
    assert placebo["decisions"]["promotable"] is False
    assert placebo["promotion"]["promoted"] is False
    assert placebo["task"] == "w18_p2_onsager_delta"


def test_the_placebo_board_never_feeds_the_main_board() -> None:
    summary = _summary()
    placebo = _placebo_summary()
    assert PLACEBO_SUMMARY != SUMMARY
    # the main board keeps the ladder verdict it earned on the real target;
    # the placebo verdict lives only in the separate file.
    assert summary["placebo"] is False
    assert summary["decisions"]["verdict"] in ("confirmed", "partial", "refuted")
    assert placebo["decisions"]["verdict"] == "placebo"
    assert placebo["outputs"]["summary"] != summary["outputs"]["summary"]
    assert placebo["outputs"]["report"] != summary["outputs"]["report"]
    assert placebo["outputs"]["repeats"] != summary["outputs"]["repeats"]
    assert [int(seed) for seed in placebo["seeds"]] == [int(seed) for seed in summary["seeds"]]
    # two sets of readings: the permuted target moves the reference endpoint.
    main_reference = float(summary["decisions"]["endpoint_reference_direct"])
    placebo_reference = float(placebo["decisions"]["endpoint_reference_direct"])
    assert abs(main_reference - FROZEN_CROSS_SEED) <= ANCHOR_TOLERANCE
    assert abs(placebo_reference - main_reference) > ANCHOR_TOLERANCE


def test_the_repeats_artifact_keeps_the_frozen_schema() -> None:
    _summary()
    assert REPEATS.is_file(), REPEATS
    raw = REPEATS.read_bytes()
    assert raw.count(b"\r\n") == 0
    assert raw[:3] != b"\xef\xbb\xbf"
    with REPEATS.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == list(REPEAT_COLUMNS)
    assert len(rows) == len(SEEDS) * len(ARMS) * REPEATS_PER_CELL
    for seed in SEEDS:
        present = {row["arm"] for row in rows if int(row["seed"]) == seed}
        assert present == set(ARMS)
    assert all(row["representation"] == "Physical(lever4)" for row in rows)


def test_the_report_states_the_verdict_and_the_frozen_numbers() -> None:
    _summary()
    assert REPORT.is_file(), REPORT
    text = REPORT.read_text(encoding="utf-8")
    assert "W18-P2" in text
    assert str(_summary()["decisions"]["verdict"]) in text
    assert "0.6080587938801277" in text
    assert "0.4766400383507876" in text
    assert "0.4091179943351143" in text


def test_the_new_files_are_lf_and_bom_free() -> None:
    paths = [SCRIPT, PREREG]
    for path in (SUMMARY, REPORT, REPEATS, PLACEBO_SUMMARY):
        if path.is_file():
            paths.append(path)
    for path in paths:
        payload = path.read_bytes()
        assert payload.count(b"\r\n") == 0, path
        assert payload[:3] != b"\xef\xbb\xbf", path

