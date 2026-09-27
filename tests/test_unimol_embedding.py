"""Regression tests for the W18-P5 Uni-Mol embedding lane.

The lane has two legal shapes and this file pins the second one, because that is
the one this repository actually ran:

* blocked -- the pre-trained runtime was absent, so the lane claims no reading and
  only records the measured blockers;
* reading -- the lane ran, the anchor arm reproduced the frozen single-representation
  reading bit for bit, and every arm reading is reported against that anchor.

The literals below are pinned on purpose, in the style every earlier week used: the
frozen side and the registered bars are constants, and the seed-42 arm readings are
pinned once they exist.  A mutant that moves a number has to move a line of this file.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes/dielectric_unimol_embedding_prereg.json"
PROBE = ROOT / "probes/dielectric_unimol_embedding.py"
BUILDER = ROOT / "probes/build_unimol_embeddings.py"
SUMMARY = ROOT / "probes/dielectric_unimol_embedding_summary.json"
PLACEBO_SUMMARY = ROOT / "probes/dielectric_unimol_embedding_placebo_summary.json"
REPORT = ROOT / "reports/dielectric_unimol_embedding.md"
EMBEDDINGS = ROOT / "probes/artifacts/dielectric_unimol_embedding.csv"

SEEDS = (42, 1234, 2026, 31337, 7)
ARMS = ("reference_lever4", "plus_unimol", "unimol_only")
VERDICTS = ("confirmed", "partial", "refuted", "placebo")
CONFIRM_BAR = 0.02
PARTIAL_BAR = 0.005
ANCHOR_TOLERANCE = 1e-09

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_CROSS_SEED_ENDPOINT = 0.5861142332208197

EMBEDDING_ROWS = 276
EMBEDDING_DIMENSION = 512
SEED_42 = {
    "reference_lever4": 0.6080587938801277,
    "plus_unimol": 0.19880491733580088,
    "unimol_only": 0.13540969792681085,
}
SEED_42_DELTA = -0.4092538765443269
CROSS_SEED = {
    "reference_lever4": 0.5861142332208197,
    "plus_unimol": 0.1102020209457352,
    "unimol_only": 0.0305790659288033,
}
CROSS_SEED_DELTA = -0.4759122122750845


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _placebo_summary() -> dict:
    return json.loads(PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def test_the_lane_ships_its_probe_builder_prereg_and_artifacts() -> None:
    for path in (PROBE, BUILDER, PREREG, SUMMARY, REPORT, EMBEDDINGS):
        assert path.is_file(), path


def test_the_prereg_is_locked_before_the_run_and_pins_the_anchor() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["lane"] == "W18-P5"
    assert tuple(prereg["seeds"]) == SEEDS
    assert prereg["anchor_seed"] == 42
    assert prereg["decision_rule"]["confirm_bar"] == CONFIRM_BAR
    assert prereg["decision_rule"]["partial_bar"] == PARTIAL_BAR
    assert prereg["decision_rule"]["compared_against"] == FROZEN_CROSS_SEED_ENDPOINT
    assert "torch" in prereg["runtime_requirements"]
    assert "unimol_tools" in prereg["runtime_requirements"]
    recorded = _summary()["prereg"]
    assert recorded["sha256"] == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    assert recorded["status"] == "locked_before_run"


def test_the_embedding_table_has_the_registered_shape() -> None:
    with EMBEDDINGS.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    assert header[:2] == ["inchikey", "smiles"]
    assert len(header) - 2 == EMBEDDING_DIMENSION
    assert header[2] == "dim_000"
    assert header[-1] == "dim_" + format(EMBEDDING_DIMENSION - 1, "03d")
    body = rows[1:]
    assert len(body) == EMBEDDING_ROWS
    assert len({row[0] for row in body}) == EMBEDDING_ROWS
    assert all(len(row) == len(header) for row in body)


def test_the_lane_read_the_embedding_table_it_was_given() -> None:
    embedding = _summary()["embedding"]
    assert embedding["present"] is True
    assert embedding["dimension"] == EMBEDDING_DIMENSION
    assert embedding["table_rows"] == EMBEDDING_ROWS
    coverage = embedding["coverage"]
    assert coverage["rows"] == 2391
    assert coverage["rows_with_an_embedding"] == 2154
    assert coverage["zero_filled_rows"] == 237
    assert coverage["rows"] == coverage["rows_with_an_embedding"] + coverage["zero_filled_rows"]


def test_the_lane_only_reports_because_the_anchor_reproduced() -> None:
    summary = _summary()
    anchors = summary["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["fold_signature_matched"] is True
    assert anchors["arm"] == "reference_lever4"
    assert anchors["seed"] == 42
    assert anchors["expected"] == FROZEN_SINGLE_REPRESENTATION
    assert abs(anchors["value"] - FROZEN_SINGLE_REPRESENTATION) <= ANCHOR_TOLERANCE


def test_seed_42_is_pinned_arm_by_arm() -> None:
    rows = [row for row in _summary()["seed_rows"] if row["seed"] == 42]
    readings = {row["arm"]: row["r2_mean"] for row in rows}
    assert readings == SEED_42
    assert readings["reference_lever4"] == FROZEN_SINGLE_REPRESENTATION
    assert readings["plus_unimol"] - readings["reference_lever4"] == SEED_42_DELTA


def test_every_seed_carries_every_arm() -> None:
    rows = _summary()["seed_rows"]
    seen = {(row["seed"], row["arm"]) for row in rows}
    assert seen == {(seed, arm) for seed in SEEDS for arm in ARMS}
    for row in rows:
        assert row["repeats"] == 10
        assert 0.0 <= float(row["r2_sd"])


def test_the_cross_seed_endpoint_is_the_mean_of_the_seed_readings() -> None:
    summary = _summary()
    rows = summary["seed_rows"]
    for arm in ARMS:
        values = [row["r2_mean"] for row in rows if row["arm"] == arm]
        assert len(values) == len(SEEDS)
        mean = sum(values) / len(values)
        assert abs(summary["cross_seed"][arm] - mean) <= 1e-12
    reference = summary["cross_seed"]["reference_lever4"]
    assert abs(reference - FROZEN_CROSS_SEED_ENDPOINT) <= 1e-09

def test_the_cross_seed_endpoint_is_pinned_arm_by_arm() -> None:
    summary = _summary()
    assert summary["cross_seed"] == CROSS_SEED
    assert summary["cross_seed"]["reference_lever4"] == FROZEN_CROSS_SEED_ENDPOINT
    reference = summary["cross_seed"]["reference_lever4"]
    plus = summary["cross_seed"]["plus_unimol"]
    assert plus - reference == CROSS_SEED_DELTA
    assert summary["delta_plus_minus_reference"] == CROSS_SEED_DELTA
    assert summary["seeds_with_a_positive_delta"] == 0
    deltas = summary["per_seed_delta_plus_minus_reference"]
    assert sorted(deltas, key=int) == [str(seed) for seed in sorted(SEEDS)]
    assert all(value < 0 for value in deltas.values())
    assert all(value < -0.40 for value in deltas.values())


def test_the_verdict_follows_the_registered_ladder_and_promotes_nothing() -> None:
    summary = _summary()
    decision = summary["decision"]
    assert decision["verdict"] in VERDICTS
    assert decision["verdict"] == "refuted"
    assert decision["promotable"] is False
    assert decision["confirm_bar"] == CONFIRM_BAR
    assert decision["partial_bar"] == PARTIAL_BAR
    delta = summary["cross_seed"]["plus_unimol"] - summary["cross_seed"]["reference_lever4"]
    assert summary["delta_plus_minus_reference"] == delta
    if delta >= CONFIRM_BAR:
        expected = "confirmed" if summary["seeds_with_a_positive_delta"] >= 4 else "partial"
    elif delta >= PARTIAL_BAR:
        expected = "partial"
    else:
        expected = "refuted"
    assert decision["verdict"] == expected


def test_the_leakage_audit_is_clean_and_covers_every_seed() -> None:
    leakage = _summary()["leakage"]
    blocks = leakage if isinstance(leakage, list) else [leakage]
    assert len(blocks) == len(SEEDS)
    assert sorted((str(block["seed"]) for block in blocks), key=int) == [
        str(seed) for seed in sorted(SEEDS)
    ]
    for block in blocks:
        assert block["folds"] == 50
        assert block["folds_with_a_straddling_compound"] == 0
        assert block["max_straddling_compounds_in_a_fold"] == 0


def test_the_frozen_side_did_not_move() -> None:
    control = _summary()["frozen_control"]
    assert control["baseline_r2"] == FROZEN_BASELINE
    assert control["headline_r2"] == FROZEN_HEADLINE
    assert control["single_representation_r2"] == FROZEN_SINGLE_REPRESENTATION
    assert control["single_representation_cross_seed_mean"] == FROZEN_CROSS_SEED_ENDPOINT


def test_the_placebo_ran_and_is_kept_out_of_the_verdict() -> None:
    assert PLACEBO_SUMMARY.is_file()
    standalone = _placebo_summary()
    assert standalone["stage"] == "placebo"
    assert standalone["decision"]["promotable"] is False
    assert sorted(standalone["cross_seed"], key=str) == sorted(ARMS)


def test_the_report_states_the_verdict_out_loud() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "refuted" in text
    assert "blocked lane is not a negative result" in text


def test_the_new_files_are_lf_and_bom_free() -> None:
    for path in (PROBE, BUILDER, PREREG, SUMMARY, EMBEDDINGS, REPORT, PLACEBO_SUMMARY):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf"), path
        assert b"\r\n" not in payload, path
