"""Guards for the lever-3 target-transform probe.

These tests pin what makes the transform arm auditable rather than self-serving:

* the transform and its inverse are checked numerically, and the domain guard
  refuses a pool that `ln(epsilon - 1)` cannot describe;
* the only model change is the objective, checked against the frozen
  `XGB_PARAMS` dictionary key by key;
* the judged thresholds are the literals frozen in the pre-registration;
* the main scoreboard is re-derived from the frozen tables - 457 scored rows of
  97 compounds - instead of being trusted to the summary;
* every reported reading is recomputed from the per-repeat artifact, in both the
  raw scale and the log scale;
* the verdict is the raws-scale one the pre-registration names, and a lift that
  vanished after the back-transformation is reported as such;
* the report file is byte-identical to what the summary renders;
* every artifact is LF-only.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_target_transform_probe as probe
import numpy as np
from dielectric_band_ablation import ROOM_BAND
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_representation_ablation import XGB_PARAMS

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_target_transform_probe_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_target_transform_probe.md"
COVERAGE_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_coverage_paired_benchmark_summary.json"
)
HYBRID = "Morgan+Physical"


def read_csv_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
    assert SUMMARY_PATH.is_file(), "run probes/dielectric_target_transform_probe.py first"
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_forward_and_back_transform_are_inverses() -> None:
    values = np.asarray([2.0, 10.0, 178.47])
    transformed = probe.forward_transform(values)
    assert transformed[0] == pytest.approx(0.0, abs=1e-15)
    assert transformed[1] == pytest.approx(np.log(9.0), abs=1e-15)
    assert probe.back_transform(transformed) == pytest.approx(values, rel=1e-12)
    assert probe.back_transform(np.asarray([0.0]))[0] == pytest.approx(2.0, abs=1e-15)


def test_forward_transform_refuses_a_pool_it_cannot_describe() -> None:
    with pytest.raises(ValueError, match=r"epsilon <= 1"):
        probe.forward_transform(np.asarray([1.0, 5.0]))
    with pytest.raises(ValueError, match=r"epsilon <= 1"):
        probe.forward_transform(np.asarray([0.5]))
    with pytest.raises(ValueError, match="non-finite"):
        probe.forward_transform(np.asarray([2.0, float("nan")]))


def test_the_only_model_change_is_the_objective() -> None:
    assert probe.TRANSFORM_PARAMS["objective"] == "reg:pseudohubererror"
    assert probe.TRANSFORM_PARAMS["huber_slope"] == 1.0
    for key, value in XGB_PARAMS.items():
        if key == "objective":
            continue
        assert probe.TRANSFORM_PARAMS[key] == value, key
    extra = set(probe.TRANSFORM_PARAMS) - set(XGB_PARAMS)
    assert extra == {"huber_slope"}


def test_thresholds_are_the_preregistered_literals(prereg_lever: dict, prereg: dict) -> None:
    assert probe.PASS_DELTA_R2 == 0.0200
    assert probe.KILL_DELTA_R2 == 0.0050
    assert probe.CONTROL_COLLAPSE_TOLERANCE == 0.02
    assert "+0.0200" in prereg_lever["pass_criterion"]
    assert "+0.0050" in prereg_lever["kill_line"]
    assert "0.02" in prereg["control_arm"]["rule"]
    assert probe.TRANSFORM_TRAIN_TARGET in prereg_lever["transform"]
    assert probe.TRANSFORM_OBJECTIVE in prereg_lever["model_change"]


def test_reference_r2_is_the_published_paired_base_reading() -> None:
    published = json.loads(COVERAGE_SUMMARY_PATH.read_text(encoding="utf-8"))
    value = published["fixed_pool_family"]["summary"]["paired_base"][HYBRID]["r2"]["mean"]
    assert probe.REFERENCE_R2 == pytest.approx(float(value), abs=1e-15)


def test_main_scoreboard_is_re_derived_from_the_frozen_tables() -> None:
    merged, _report = merge_feature_blocks()
    rows, _dropped = load_coverage_table(COVERAGE_PATH, merged)
    origin = np.asarray([str(row["observation_origin"]) for row in rows])
    band = np.asarray([str(row["temperature_band"]) for row in rows])
    score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    keys = np.asarray([str(row["inchikey"]) for row in rows])
    assert int(score.sum()) == probe.SCOREBOARD_ROWS == 457
    assert len(set(keys[score].tolist())) == probe.SCOREBOARD_COMPOUNDS == 97


def test_summary_declares_the_frozen_scoreboard(summary: dict, prereg: dict) -> None:
    scoreboard = summary["main_scoreboard"]
    declared = prereg["main_scoreboard"]
    assert scoreboard["rows_scored"] == declared["rows_scored"] == 457
    assert scoreboard["compounds_scored"] == declared["compounds_scored"] == 97
    assert scoreboard["n_splits"] == declared["n_splits"] == 5
    assert scoreboard["n_repeats"] == declared["n_repeats"] == 10
    assert scoreboard["seed"] == declared["seed"] == 42
    assert scoreboard["min_test_rows_per_fold"] == declared["min_test_rows_per_fold"] == 2
    assert scoreboard["folds_measured"] == scoreboard["full_run_folds"] == 50
    assert scoreboard["guards_passed"] is True


def test_baseline_arm_reproduced_the_published_r2(summary: dict) -> None:
    reproduced = summary["baseline_reproduces"]
    assert reproduced["abs_difference"] <= probe.REFERENCE_TOLERANCE
    assert reproduced["bit_exact"] is True
    assert summary["reference_triple"]["all_bit_exact"] is True
    assert summary["arms"]["baseline"]["meta"]["objective"] == XGB_PARAMS["objective"]


def test_all_arms_share_the_same_scored_folds(summary: dict) -> None:
    assert summary["shared_folds"]["scored_side_identical"] is True
    for arm in ("baseline", "lever", "control"):
        assert summary["arms"][arm]["audit"]["folds_with_a_straddling_compound"] == 0
        assert summary["arms"][arm]["audit"]["scored_rows_outside_the_score_mask"] == 0
        assert summary["arms"][arm]["meta"]["folds"] == 50


def scored_rows_by_fold(summary: dict, arm: str) -> dict[tuple[int, int], list[tuple[str, float]]]:
    """Every (compound, temperature) a fold scored, read from the artifact itself."""

    rows = read_csv_rows(REPOSITORY_ROOT / summary["outputs"]["predictions"])
    grouped: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for row in rows:
        if row["protocol"] != arm or row["representation"] != HYBRID:
            continue
        key = (int(row["repeat"]), int(row["fold"]))
        grouped.setdefault(key, []).append((row["inchikey"], float(row["T_K"])))
    return {key: sorted(value) for key, value in grouped.items()}


def test_the_three_arms_score_the_identical_rows(summary: dict) -> None:
    """The shared-fold claim, checked row by row instead of taken on trust.

    A shared assignment means the scored side of every fold is the *same* set of
    rows in all three arms, so the signatures must be identical - not distinct.
    The claim is re-derived here from the prediction artifact rather than read
    off the summary flag.
    """

    arms = summary["shared_folds"]["arms"]
    baseline = scored_rows_by_fold(summary, arms[0])
    assert baseline and len(baseline) == 50
    for arm in arms[1:]:
        other = scored_rows_by_fold(summary, arm)
        assert set(other) == set(baseline)
        for key, rows in baseline.items():
            assert other[key] == rows, key



def test_readings_recompute_from_the_per_repeat_artifact(summary: dict) -> None:
    rows = read_csv_rows(REPOSITORY_ROOT / summary["outputs"]["repeats"])
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        grouped.setdefault((row["protocol"], row["representation"]), []).append(float(row["r2"]))
    for arm, block in summary["readings"].items():
        for representation, metrics in block.items():
            key = (arm, representation)
            assert key in grouped, key
            assert float(metrics["r2"]["mean"]) == pytest.approx(
                float(np.mean(grouped[key])), abs=1e-15
            )


def test_log_readings_recompute_from_the_log_repeat_artifact(summary: dict) -> None:
    rows = read_csv_rows(REPOSITORY_ROOT / summary["outputs"]["log_repeats"])
    values = [
        float(row["r2"])
        for row in rows
        if row["protocol"] == probe.LEVER_ARM and row["representation"] == HYBRID
    ]
    assert values
    diagnostic = summary["log_space_diagnostic"]
    assert diagnostic["lever_log_r2"] == pytest.approx(float(np.mean(values)), abs=1e-15)
    assert diagnostic["vanished_after_back_transform"] == (
        diagnostic["log_gain_over_raw"] >= probe.PASS_DELTA_R2
    )
    assert diagnostic["log_gain_over_raw"] == pytest.approx(
        diagnostic["lever_log_r2"] - diagnostic["lever_raw_r2"], abs=1e-15
    )


def test_control_arm_is_reported_with_every_reference(summary: dict) -> None:
    collapse = summary["control_collapse"]
    assert collapse["trivial_floor_r2"] == pytest.approx(
        summary["readings"][probe.CONTROL_FLOOR_ARM]["DummyMean"]["r2"]["mean"], abs=1e-15
    )
    assert collapse["collapsed"] == (
        collapse["delta_over_the_floor"] <= probe.CONTROL_COLLAPSE_TOLERANCE
    )
    assert collapse["literal_wording_is_satisfiable"] == (
        abs(collapse["delta_vs_the_real_label_baseline"]) <= probe.CONTROL_COLLAPSE_TOLERANCE
    )


def test_verdict_never_claims_more_than_the_criterion_grants(summary: dict) -> None:
    verdict = summary["verdict"]
    delta = verdict["delta_r2"]
    assert verdict["decision"] in {"pass", "dead", "sub_threshold", "unverified"}
    if verdict["decision"] == "pass":
        assert delta >= probe.PASS_DELTA_R2
        assert verdict["spearman_fell"] is False
        assert verdict["control_collapsed"] is True
        assert verdict["carried_into_the_merge_arm"] is True
    if delta < probe.KILL_DELTA_R2:
        assert verdict["decision"] != "pass"
        assert verdict["carried_into_the_merge_arm"] is False
    assert verdict["delta_r2"] == pytest.approx(
        summary["readings"][probe.LEVER_ARM][HYBRID]["r2"]["mean"]
        - summary["readings"][probe.BASELINE_ARM][HYBRID]["r2"]["mean"],
        abs=1e-15,
    )


def test_report_is_the_rendered_summary(summary: dict) -> None:
    rendered = "\n".join(probe.render_report(summary)) + "\n"
    assert REPORT_PATH.read_text(encoding="utf-8") == rendered


def test_shots_and_locked_criteria(summary: dict, prereg_lever: dict) -> None:
    assert summary["shots"]["this_lever"] == probe.SHOTS_THIS_LEVER == 1
    for key in ("pass_criterion", "secondary_criterion", "kill_line"):
        assert summary["locked_criteria"][key] == prereg_lever[key]
    assert summary["prereg"]["sha256"] == probe.canonical_text_sha256(PREREG_PATH)


def test_every_artifact_is_lf_only(summary: dict) -> None:
    for key, relative in summary["outputs"].items():
        if not str(relative).endswith(".csv"):
            continue
        assert b"\r\n" not in (REPOSITORY_ROOT / relative).read_bytes(), key