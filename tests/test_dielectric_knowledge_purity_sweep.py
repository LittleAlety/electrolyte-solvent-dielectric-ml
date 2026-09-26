"""Guards for the Week 14 lever 9 knowledge purity sweep.

The sweep exists because lever 2 appended six association descriptors in one
block and lost 0.0119 grouped R2, while the KPI paper (Angew. Chem. Int. Ed.
2025, 64, e202416506) reports the same shape of failure from the other side:
embedding all 64 knowledge dimensions is worse than embedding the top 20 / 20 /
10. These tests pin the four things that could quietly go wrong -- the baseline
not reproducing, the fold dealing drifting, the importance ranking seeing a
test-fold row, and the placebo arm not collapsing -- plus the literal shot count
and the LF-only artifacts.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from probes.dielectric_knowledge_purity_sweep import (
    K_GRID,
    KILL_DELTA_R2,
    KNOWLEDGE_POOL,
    MIN_POSITIVE_REPEATS,
    N_SPLITS,
    PASS_DELTA_R2,
    PLACEBO_COLLAPSE_TOLERANCE,
    PREREG_PATH,
    REFERENCE_R2,
    REFERENCE_TOLERANCE,
    REPORT_PATH,
    SCOREBOARD_COMPOUNDS,
    SCOREBOARD_ROWS,
    SHOTS_THIS_LEVER,
    SUMMARY_PATH,
    RankingLeakError,
    assert_ranking_scope,
    classify_curve,
    knowledge_features_for_smiles,
    leaky_ranking_scope,
    permutation_importance,
    placebo_collapse_readout,
    render_report,
)
from probes.dielectric_representation_ablation import XGB_PARAMS

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep.py"
ARTIFACT_STEM = "dielectric_knowledge_purity_sweep"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
FROZEN_V03 = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FROZEN_V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
SHAPE_VOCABULARY = {
    "monotone_decreasing",
    "monotone_increasing",
    "interior_peak",
    "edge_peak_low_k",
    "edge_peak_high_k",
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _raw(path: Path) -> bytes:
    return path.read_bytes()


def summary_digest_matches() -> bool:
    """The artifact set must have been written by the script that is on disk.

    A probe whose summary records an older script digest is the exact failure
    this guards: the readings look fine and the artifact set is not the one the
    file produces.
    """

    payload = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    return payload["inputs"]["lever_script_sha256"] == canonical_text_sha256(SCRIPT_PATH)


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def importance_rows() -> list[dict[str, str]]:
    return _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_importance.csv")


@pytest.fixture(scope="module")
def fold_rows() -> list[dict[str, str]]:
    return _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_folds.csv")


# --------------------------------------------------------------------------- #
# frozen inputs
# --------------------------------------------------------------------------- #


def test_prereg_is_locked_and_the_script_agrees_with_it(prereg):
    assert prereg["status"] == "locked_before_run"
    assert prereg["lock_rule"]
    assert tuple(prereg["purity_controller"]["k_grid"]) == K_GRID
    assert tuple(prereg["knowledge_pool"]["members"]) == KNOWLEDGE_POOL
    assert prereg["shots_policy"]["shots_registered_up_front"] == SHOTS_THIS_LEVER
    assert "test-fold row" in prereg["purity_controller"]["leak_rule"]
    assert prereg["main_scoreboard"]["baseline_to_reproduce"] == REFERENCE_R2
    assert prereg["main_scoreboard"]["tolerance"] == REFERENCE_TOLERANCE
    assert prereg["main_scoreboard"]["folds_frozen"] is True


def test_thresholds_are_the_frozen_ones(summary):
    thresholds = summary["prereg"]["thresholds"]
    assert thresholds["pass_delta_r2"] == PASS_DELTA_R2 == 0.02
    assert thresholds["kill_delta_r2"] == KILL_DELTA_R2 == 0.005
    assert thresholds["min_positive_repeats"] == MIN_POSITIVE_REPEATS == 8
    assert thresholds["placebo_collapse_tolerance"] == PLACEBO_COLLAPSE_TOLERANCE == 0.02
    assert summary["prereg"]["sha256"] == canonical_text_sha256(PREREG_PATH)


def test_the_frozen_roster_was_not_touched():
    assert sha256_file(FROZEN_V03) == FROZEN_V03_SHA256


def test_shots_are_four_and_every_k_is_reported(summary):
    assert SHOTS_THIS_LEVER == 4
    assert len(K_GRID) == 4
    assert summary["shots"]["count"] == 4
    assert summary["shots"]["all_k_reported"] is True
    assert set(summary["delta_r2_by_k"]) == {str(k) for k in K_GRID}
    assert set(summary["per_repeat_delta_r2"]) == {str(k) for k in K_GRID}
    assert set(summary["positive_repeats_by_k"]) == {str(k) for k in K_GRID}


# --------------------------------------------------------------------------- #
# the main scoreboard
# --------------------------------------------------------------------------- #


def test_guards_pass_and_the_scoreboard_is_the_frozen_one(summary):
    block = summary["main_scoreboard"]
    assert block["rows_scored"] == SCOREBOARD_ROWS == 457
    assert block["compounds_scored"] == SCOREBOARD_COMPOUNDS == 97
    assert block["n_splits"] == N_SPLITS == 5
    assert block["repeats_executed"] == 10
    assert block["seed"] == 42
    assert block["splits"] == N_SPLITS * 10
    assert block["min_test_rows_per_fold"] == 2
    assert block["baseline_to_reproduce"] == REFERENCE_R2
    assert block["tolerance"] == REFERENCE_TOLERANCE
    assert block["guards_passed"] is True
    assert all(block["guards"].values())


def test_baseline_reproduces_to_the_published_tolerance(summary):
    baseline = summary["baseline_reproduces"]
    assert baseline["published_r2"] == REFERENCE_R2
    assert baseline["abs_difference"] <= REFERENCE_TOLERANCE
    assert baseline["verified"] is True
    for representation, block in baseline["representations"].items():
        assert block["bit_exact"] is True, representation


def test_the_purity_loop_is_faithful_to_run_protocol(summary):
    loop = summary["loop_faithfulness"]
    assert loop["abs_difference"] <= 1e-12
    assert loop["agrees"] is True
    assert loop["frozen_block_reference_r2"] == pytest.approx(
        summary["baseline_reproduces"]["reproduced_r2"], abs=1e-12
    )


def test_k_grid_deltas_are_the_readings_minus_the_baseline(summary):
    baseline = summary["readings"]["paired_base"]["Morgan+Physical"]["r2"]["mean"]
    for key, arm in summary["arms"]["purity"].items():
        reading = summary["readings"][arm]["Morgan+Physical"]["r2"]["mean"]
        assert summary["delta_r2_by_k"][key] == pytest.approx(reading - baseline, abs=1e-12)


def test_per_repeat_signs_agree_with_the_positive_counts(summary):
    baseline = {
        row["repeat"]: float(row["r2"])
        for row in _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_repeats.csv")
        if row["protocol"] == "paired_base" and row["representation"] == "Morgan+Physical"
    }
    assert len(baseline) == 10
    for key, block in summary["per_repeat_delta_r2"].items():
        assert len(block) == 10
        positives = sum(1 for value in block.values() if float(value) > 0)
        assert positives == summary["positive_repeats_by_k"][key]
        for repeat, value in block.items():
            arm = summary["arms"]["purity"][key]
            reading = {
                row["repeat"]: float(row["r2"])
                for row in _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_repeats.csv")
                if row["protocol"] == arm and row["representation"] == "Morgan+Physical"
            }
            assert float(value) == pytest.approx(reading[repeat] - baseline[repeat], abs=1e-12)


def test_verdict_is_consistent_with_the_frozen_criteria(summary):
    verdict = summary["verdict"]
    curve = summary["curve"]
    assert verdict["decision"] in {"pass", "dead", "sub_threshold", "unverified"}
    assert verdict["best_k"] == curve["best_k"]
    assert verdict["best_delta_r2"] == pytest.approx(curve["best_delta_r2"], abs=1e-12)
    if verdict["decision"] == "pass":
        assert curve["best_delta_r2"] >= PASS_DELTA_R2
        assert verdict["positive_repeats"] >= MIN_POSITIVE_REPEATS
        assert summary["placebo"]["collapse"]["collapsed"] is True
    if verdict["decision"] == "dead" and all(
        float(value) < KILL_DELTA_R2 for value in curve["delta_r2_by_k"].values()
    ):
        assert any("kill line" in reason for reason in verdict["reasons"])


def test_curve_shape_matches_the_delta_series(summary):
    curve = summary["curve"]
    assert curve["shape"] in SHAPE_VOCABULARY
    values = [float(curve["delta_r2_by_k"][str(k)]) for k in K_GRID]
    expected = all(values[i] >= values[i + 1] for i in range(len(values) - 1))
    assert curve["monotone_decreasing"] is expected
    assert curve["best_k"] == K_GRID[int(np.argmax(values))]
    assert curve["contradicts_mechanism"] is (not curve["interior_peak"])
    placebo_curve = summary["placebo"]["curve"]
    assert placebo_curve["contradicts_mechanism"] is (not placebo_curve["interior_peak"])
    if curve["monotone_decreasing"]:
        assert curve["mechanism_reading"] == "no_interior_peak_monotone_decrease"
    if curve["monotone_increasing"]:
        assert curve["mechanism_reading"] == "no_interior_peak_monotone_increase"

# --------------------------------------------------------------------------- #
# the leak guard
# --------------------------------------------------------------------------- #


def _synthetic_split() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A train fold whose labels depend on m0, and a test fold on m1."""

    rng = np.random.default_rng(7)
    train_x = rng.normal(size=(60, 4))
    test_x = rng.normal(size=(30, 4))
    features = np.vstack([train_x, test_x])
    target = np.concatenate([3.0 * train_x[:, 0], -9.0 * test_x[:, 1]])
    train_index = np.arange(0, 60)
    test_index = np.arange(60, 90)
    return features, target, train_index, test_index


def test_no_leak_guard_accepts_the_training_fold_and_rejects_a_test_row():
    _features, _target, train_index, test_index = _synthetic_split()
    assert_ranking_scope(
        importance_rows=train_index,
        train_index=train_index,
        test_index=test_index,
        context="clean",
    )
    with pytest.raises(RankingLeakError, match="test-fold row"):
        assert_ranking_scope(
            importance_rows=leaky_ranking_scope(train_index, test_index),
            train_index=train_index,
            test_index=test_index,
            context="mutant",
        )
    with pytest.raises(RankingLeakError):
        assert_ranking_scope(
            importance_rows=np.asarray([0, 999]),
            train_index=train_index,
            test_index=test_index,
        )


def test_a_ranking_that_saw_the_test_fold_picks_a_different_member():
    features, target, train_index, test_index = _synthetic_split()
    columns = ("m0", "m1", "m2", "m3")
    clean_model = XGBRegressor(**XGB_PARAMS, random_state=42)
    clean_model.fit(features[train_index], target[train_index])
    clean = permutation_importance(
        clean_model,
        features,
        target,
        columns=columns,
        importance_rows=train_index,
        shuffles=3,
        seed=42,
    )
    leaky_rows = leaky_ranking_scope(train_index, test_index)
    leaky_model = XGBRegressor(**XGB_PARAMS, random_state=42)
    leaky_model.fit(features[leaky_rows], target[leaky_rows])
    leaky = permutation_importance(
        leaky_model,
        features,
        target,
        columns=columns,
        importance_rows=leaky_rows,
        shuffles=3,
        seed=42,
    )
    assert clean[0][0] == "m0"
    assert leaky[0][0] == "m1"
    assert [name for name, _score in clean] != [name for name, _score in leaky]


def test_permutation_importance_is_deterministic_and_breaks_ties_by_pool_order():
    rng = np.random.default_rng(11)
    features = rng.normal(size=(40, 3))
    target = 2.0 * features[:, 2]
    model = XGBRegressor(**XGB_PARAMS, random_state=42)
    model.fit(features, target)
    columns = ("a", "b", "c")
    first = permutation_importance(
        model, features, target, columns=columns, importance_rows=np.arange(40), seed=42
    )
    second = permutation_importance(
        model, features, target, columns=columns, importance_rows=np.arange(40), seed=42
    )
    assert first == second
    assert first[0][0] == "c"
    assert [score for _name, score in first] == sorted(
        (score for _name, score in first), reverse=True
    )


def test_the_importance_artifact_proves_the_ranking_stayed_in_the_training_fold(
    importance_rows, fold_rows
):
    assert len(importance_rows) == N_SPLITS * 10 * len(KNOWLEDGE_POOL)
    assert all(int(row["test_rows_visible_to_ranking"]) == 0 for row in importance_rows)
    train_rows_by_fold: dict[tuple[str, str], int] = {}
    for row in fold_rows:
        if row["protocol"] == "purity_k2" and row["representation"] == "Morgan+Physical":
            train_rows_by_fold[(row["repeat"], row["fold"])] = int(row["train_rows"])
    assert len(train_rows_by_fold) == N_SPLITS * 10
    for row in importance_rows:
        key = (row["repeat"], row["fold"])
        assert int(row["ranking_rows"]) == train_rows_by_fold[key]


def test_each_fold_ranks_every_member_exactly_once(importance_rows):
    per_fold: dict[tuple[str, str], list[str]] = {}
    for row in importance_rows:
        per_fold.setdefault((row["repeat"], row["fold"]), []).append(row["member"])
    assert len(per_fold) == N_SPLITS * 10
    for key, members in per_fold.items():
        assert sorted(members) == sorted(KNOWLEDGE_POOL), key
        assert sorted(int(row["rank"]) for row in importance_rows if (row["repeat"], row["fold"]) == key) == list(
            range(1, len(KNOWLEDGE_POOL) + 1)
        )


def test_stability_reports_the_moves_of_the_top_three(summary):
    stability = summary["importance_stability"]
    assert stability["folds"] == N_SPLITS * 10
    assert stability["top_k"] == 3
    assert stability["distinct_top_k_sets"] >= 1
    assert 0 <= stability["changes_between_consecutive_folds"] <= stability["folds"] - 1
    assert len(stability["modal_top_k_set"]) == 3
    assert set(stability["per_member"]) == set(KNOWLEDGE_POOL)
    for member, block in stability["per_member"].items():
        assert block["folds"] == stability["folds"], member
        assert 1 <= block["min_rank"] <= block["max_rank"] <= len(KNOWLEDGE_POOL)
        assert 0 <= block["top_3_folds"] <= stability["folds"]


# --------------------------------------------------------------------------- #
# placebo, curve and knowledge pool units
# --------------------------------------------------------------------------- #


def test_placebo_collapse_readout_holds_both_rules():
    collapsed = placebo_collapse_readout(
        placebo_best_r2=-0.30,
        placebo_floor_r2=-0.31,
        placebo_best_delta_r2=0.004,
        real_baseline_r2=0.4091179943351143,
        real_best_k=4,
    )
    assert collapsed["collapsed"] is True
    assert collapsed["best_real_k"] == 4
    assert collapsed["placebo_within_pipeline_delta_r2"] == 0.004
    shattered = placebo_collapse_readout(
        placebo_best_r2=0.10,
        placebo_floor_r2=-0.31,
        placebo_best_delta_r2=0.25,
        real_baseline_r2=0.4091179943351143,
        real_best_k=4,
    )
    assert shattered["collapsed"] is False
    assert shattered["floor_rule_holds"] is False
    assert shattered["within_pipeline_rule_holds"] is False


def test_placebo_arm_in_the_summary_matches_its_readings(summary):
    placebo = summary["placebo"]
    floor_name = placebo["arms"]["floor"]
    floor = summary["readings"][floor_name]["Morgan+Physical"]["r2"]["mean"]
    best_k = summary["curve"]["best_k"]
    arm = placebo["arms"]["purity"][str(best_k)]
    reading = summary["readings"][arm]["Morgan+Physical"]["r2"]["mean"]
    collapse = placebo["collapse"]
    assert collapse["placebo_r2_at_best_real_k"] == pytest.approx(reading, abs=1e-12)
    assert collapse["placebo_floor_r2"] == pytest.approx(floor, abs=1e-12)
    assert collapse["delta_over_the_floor"] == pytest.approx(reading - floor, abs=1e-12)
    assert collapse["collapsed"] == (
        collapse["floor_rule_holds"] and collapse["within_pipeline_rule_holds"]
    )


def test_classify_curve_names_the_shapes():
    decreasing = classify_curve({2: 0.01, 4: 0.005, 6: 0.001, 10: -0.002})
    assert decreasing["shape"] == "monotone_decreasing"
    assert decreasing["contradicts_mechanism"] is True
    interior = classify_curve({2: 0.005, 4: 0.030, 6: 0.010, 10: -0.001})
    assert interior["shape"] == "interior_peak"
    assert interior["interior_peak_is_strict"] is True
    assert interior["best_k"] == 4
    assert interior["contradicts_mechanism"] is False
    low = classify_curve({2: 0.05, 4: 0.01, 6: 0.03, 10: 0.001})
    assert low["shape"] == "edge_peak_low_k"
    high = classify_curve({2: 0.001, 4: 0.002, 6: 0.005, 10: 0.020})
    assert high["shape"] == "monotone_increasing"
    assert high["contradicts_mechanism"] is True
    assert high["mechanism_reading"] == "no_interior_peak_monotone_increase"
    assert interior["mechanism_reading"] == "interior_peak"
    assert low["contradicts_mechanism"] is True
    assert low["mechanism_reading"] == "no_interior_peak_edge_peak"
    for curve in (decreasing, interior, low, high):
        assert curve["contradicts_mechanism"] is (not curve["interior_peak"])


def test_knowledge_members_are_computable_from_smiles():
    water = knowledge_features_for_smiles("O")
    assert water["donor_count"] == 1
    assert water["has_1_donor"] == 1.0
    assert water["has_2_donors"] == 0.0
    glycerol = knowledge_features_for_smiles("OCC(O)CO")
    assert glycerol["donor_count"] == 3
    assert glycerol["has_3plus_donors"] == 1.0
    ether = knowledge_features_for_smiles("COC")
    assert ether["donor_count"] == 0
    assert ether["has_1_donor"] == 0.0
    assert ether["donor_acceptor_pair_density"] == 0.0
    assert knowledge_features_for_smiles("not-a-molecule") is None
    for member in KNOWLEDGE_POOL:
        assert member in glycerol


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "suffix", ["folds", "repeats", "predictions", "importance"]
)
def test_new_csvs_are_lf_only(suffix):
    raw = _raw(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_{suffix}.csv")
    assert b"\r\n" not in raw
    assert raw.count(b"\n") > 1


def test_repo_root_exports_are_left_alone():
    assert sha256_file(FROZEN_V03) == FROZEN_V03_SHA256


def test_report_is_rendered_from_the_summary_byte_for_byte(summary):
    rendered = "\n".join(render_report(summary)) + "\n"
    on_disk = REPORT_PATH.read_text(encoding="utf-8")
    assert on_disk == rendered


def test_check_mode_recomputes_every_derived_field_from_the_artifacts():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout
    assert "checks passed" in result.stdout


def test_summary_records_the_script_digest_it_was_written_by():
    assert summary_digest_matches() is True


def test_summary_records_the_flow_controller_boundary(summary):
    assert summary["purity_controller"]["flow_controller_implemented"] is False
    assert "boundary" in summary["purity_controller"]["flow_controller_boundary"]
    joined = " ".join(summary["honest_boundaries"])
    assert "flow controller is not implemented" in joined
    assert "melting, boiling and flash" in joined
    assert "147-compound" in joined
    assert "not the existence of an optimum k" in joined
    assert "hard ceiling" in joined
    assert "never 'the optimum is the full pool'" in joined
    assert summary["prereg"]["shots_registered_up_front"] == SHOTS_THIS_LEVER
    forbidden = " ".join(summary["prereg"]["forbidden"])
    assert "test-fold row" in forbidden
    assert "0.97-0.99" in forbidden
    assert not PREREG_PATH.read_text(encoding="utf-8").startswith("\ufeff")