"""Guards for the W17-6 merge shot (`probes/dielectric_coordination_block_v3.py`).

The merge shot scores lever 4 and lever 8 together on the frozen main scoreboard, for
the first time, under the v2 amended placebo clause reused verbatim. These tests pin
five things: the v1 and v2 records are byte-identical and quoted verbatim, the baseline
reproduces the published R2, the two single-lever arms reproduce their own published
readings, the merge delta is measured rather than summed from the singles, and the
verdict is recomputable from the released artefacts alone.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes import dielectric_coordination_block_v2 as v2
from probes import dielectric_coordination_block_v3 as v3

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(v3.SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(v3.PREREG_PATH.read_text(encoding="utf-8"))


def _r2(summary: dict, arm: str, representation: str = v3.HYBRID) -> float:
    return float(summary["arms"][arm][representation]["r2"]["mean"])


# --------------------------------------------------------------------------- #
# the v1 and v2 records are untouched and quoted verbatim
# --------------------------------------------------------------------------- #


def test_v1_and_v2_files_still_carry_the_digests_recorded_at_lock_time(prereg: dict) -> None:
    recorded = prereg["v1_and_v2_are_not_edited"]["v1_and_v2_artefact_digests_observed_at_lock_time"]
    assert recorded, "the pre-registration must record what v1 and v2 looked like"
    for relative, digest in recorded.items():
        assert sha256_of(REPOSITORY_ROOT / relative) == digest, relative


def test_the_frozen_red_lines_are_intact(prereg: dict) -> None:
    entries = prereg["frozen_red_lines_untouched"]
    assert len(entries) == 6
    for entry in entries:
        relative, _, digest = entry.partition(" digest ")
        assert digest, entry
        assert sha256_of(REPOSITORY_ROOT / relative) == digest, relative


def test_v1_dead_and_v2_pass_are_kept_verbatim(summary: dict) -> None:
    quoted = summary["quoted_prior_verdicts"]
    assert quoted["v1"]["decision_verbatim"] == "dead"
    assert quoted["v2"]["decision_verbatim"] == "pass_under_amended_placebo_clause"
    on_disk_v1 = json.loads(
        (REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_summary.json").read_text(
            encoding="utf-8"
        )
    )
    on_disk_v2 = json.loads(v3.V2_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert on_disk_v1["verdict"]["decision"] == "dead"
    assert on_disk_v2["verdict"]["decision"] == "pass_under_amended_placebo_clause"
    assert summary["verdict"]["v1_decision_is_still_in_force"] == "dead"
    assert (
        summary["verdict"]["v2_decision_is_still_in_force"]
        == "pass_under_amended_placebo_clause"
    )


def test_the_pre_registration_locked_before_the_run(summary: dict, prereg: dict) -> None:
    assert prereg["status"] == "locked_before_run"
    assert sha256_of(v3.PREREG_PATH) == summary["preregistration"]["sha256"]


def test_v3_does_not_rewrite_any_earlier_output(summary: dict) -> None:
    for path in summary["outputs"].values():
        name = Path(str(path)).name
        assert "coordination_block_v3" in str(path) or "_v3" in name, path


# --------------------------------------------------------------------------- #
# release format
# --------------------------------------------------------------------------- #


def test_v3_csvs_are_lf_only_without_bom() -> None:
    for name in ("folds", "repeats", "predictions"):
        blob = (v3.ARTIFACTS_DIR / (v3.ARTIFACT_STEM + "_" + name + ".csv")).read_bytes()
        assert b"\r\n" not in blob
        assert not blob.startswith(b"\xef\xbb\xbf")


def test_v3_report_is_lf_only_without_bom() -> None:
    blob = v3.REPORT_PATH.read_bytes()
    assert b"\r\n" not in blob
    assert not blob.startswith(b"\xef\xbb\xbf")


def test_report_on_disk_is_the_render_of_the_summary(summary: dict) -> None:
    assert v3.REPORT_PATH.read_text(encoding="utf-8").splitlines() == v3.format_report(summary)


# --------------------------------------------------------------------------- #
# the frozen contract and the reproduction guards
# --------------------------------------------------------------------------- #


def test_baseline_reproduces_the_published_r2(summary: dict) -> None:
    baseline = _r2(summary, v3.ARM_BASELINE)
    assert abs(baseline - v3.BASELINE_R2) <= v3.REPRODUCTION_TOLERANCE
    assert summary["verdict"]["baseline_reproduced"] is True
    assert summary["verdict"]["baseline_abs_delta"] <= v3.REPRODUCTION_TOLERANCE


def test_the_scoreboard_is_the_frozen_457_and_97(summary: dict) -> None:
    scoreboard = summary["scoreboard"]
    assert scoreboard["scored_rows"] == 457
    assert scoreboard["compounds_scored"] == 97
    assert scoreboard["folds"] == 50
    assert scoreboard["executed_repeats"] == 10
    assert scoreboard["folds_with_a_straddling_compound"] == 0


def test_the_single_lever_arms_reproduce_their_own_publications(summary: dict) -> None:
    repro = summary["reproduction_checks"]
    assert abs(_r2(summary, v3.ARM_PLUS_LEVER4) - v3.LEVER4_PUBLISHED_R2) <= 1e-09
    assert abs(_r2(summary, v3.ARM_PLUS_LEVER8) - v3.LEVER8_PUBLISHED_R2) <= 1e-09
    assert repro["plus_lever4_vs_migration_publication"]["abs_delta"] <= 1e-09
    assert repro["plus_lever8_vs_v2_publication"]["abs_delta"] <= 1e-09


# --------------------------------------------------------------------------- #
# the merge really carries BOTH blocks, and is measured rather than summed
# --------------------------------------------------------------------------- #


def test_both_blocks_change_the_model(summary: dict) -> None:
    both = _r2(summary, v3.ARM_PLUS_BOTH)
    assert abs(both - _r2(summary, v3.ARM_PLUS_LEVER4)) > 1e-09
    assert abs(both - _r2(summary, v3.ARM_PLUS_LEVER8)) > 1e-09


def test_the_merge_delta_is_measured_not_added(summary: dict) -> None:
    merge = summary["merge_readings"]
    baseline = _r2(summary, v3.ARM_BASELINE)
    lever4 = _r2(summary, v3.ARM_PLUS_LEVER4) - baseline
    lever8 = _r2(summary, v3.ARM_PLUS_LEVER8) - baseline
    both = _r2(summary, v3.ARM_PLUS_BOTH) - baseline
    assert abs(merge["delta_vs_baseline"] - both) <= 1e-12
    assert abs(merge["single_arm_deltas"][v3.ARM_PLUS_LEVER4] - lever4) <= 1e-12
    assert abs(merge["single_arm_deltas"][v3.ARM_PLUS_LEVER8] - lever8) <= 1e-12
    assert abs(merge["naive_sum_of_singles"] - (lever4 + lever8)) <= 1e-12
    assert abs(merge["naive_sum_of_singles"] - 0.09989726876293720) <= 1e-12
    # the measured merge could equal the sum only by coincidence, never by construction
    assert merge["best_single_arm"] in {v3.ARM_PLUS_LEVER4, v3.ARM_PLUS_LEVER8}
    assert abs(merge["delta_vs_best_single"] - (both - merge["best_single_delta"])) <= 1e-12


# --------------------------------------------------------------------------- #
# the reused amended placebo clause and the verdict
# --------------------------------------------------------------------------- #


def test_the_amended_clause_is_evaluated_on_all_three_readings(summary: dict) -> None:
    collapse = summary["collapse"]
    assert collapse["tolerance"] == v3.PLACEBO_TOLERANCE
    floor_delta = collapse["placebo_r2"] - collapse["placebo_floor_r2"]
    assert abs(collapse["over_the_floor"] - floor_delta) <= 1e-12
    assert collapse["floor_rule_holds"] is (floor_delta <= v3.PLACEBO_TOLERANCE)
    real_arm_delta = collapse["placebo_r2"] - _r2(summary, v3.ARM_PLUS_BOTH)
    assert abs(collapse["delta_vs_the_same_pipeline_real_arm"] - real_arm_delta) <= 1e-12
    assert collapse["real_arm_rule_holds"] is (real_arm_delta <= v3.PLACEBO_TOLERANCE)
    inside = collapse["placebo_r2"] - _r2(summary, v3.ARM_CONTRAST_BASELINE)
    assert abs(collapse["within_pipeline_delta_r2"] - inside) <= 1e-12
    assert collapse["within_pipeline_rule_holds"] is (inside <= v3.PLACEBO_TOLERANCE)
    assert collapse["collapsed"] is (
        collapse["floor_rule_holds"]
        and collapse["real_arm_rule_holds"]
        and collapse["within_pipeline_rule_holds"]
    )


def test_the_decision_follows_from_the_artefacts(summary: dict) -> None:
    verdict = summary["verdict"]
    delta = _r2(summary, v3.ARM_PLUS_BOTH) - _r2(summary, v3.ARM_BASELINE)
    assert abs(verdict["delta_r2"] - delta) <= 1e-12
    collapsed = bool(summary["collapse"]["collapsed"])
    if not verdict["baseline_reproduced"]:
        expected = "unverified"
    elif not collapsed:
        expected = "dead"
    elif delta >= v3.PASS_DELTA:
        expected = "pass_merged_blocks"
    elif delta < v3.KILL_DELTA:
        expected = "dead"
    else:
        expected = "sub_threshold"
    assert verdict["decision"] == expected
    assert verdict["decision"] in set(v3.DECISION_VOCABULARY)
    assert verdict["passed"] is (verdict["decision"] == "pass_merged_blocks")


def test_the_report_carries_both_prior_verdicts_and_the_refusal(summary: dict) -> None:
    report = v3.REPORT_PATH.read_text(encoding="utf-8")
    assert "dead" in report
    assert "pass_under_amended_placebo_clause" in report
    assert "禁止外推" in report
    assert summary["verdict"]["decision"] in report


def test_placebo_and_floor_still_sit_on_the_identical_shuffled_vector(summary: dict) -> None:
    assert (
        summary["arms"][v3.ARM_PLACEBO][v3.HYBRID]["r2"]["mean"]
        == summary["collapse"]["placebo_r2"]
    )
    assert summary["collapse_arms"]["floor_r2"] == _r2(summary, v3.ARM_FLOOR)
    # the floor is the training-fold mean and so can never explain the target
    assert float(summary["floors"][v3.ARM_FLOOR_REAL][v3.HYBRID]["r2"]["mean"]) < 0.05


def test_check_artifacts_reports_no_problem() -> None:
    assert v3.check_artifacts() == 0


def test_the_reused_clause_is_v2_s(summary: dict) -> None:
    assert v3.v2.placebo_collapse_readout is not None
    # v3 must not silently widen the sibling tolerance
    assert v2.PLACEBO_TOLERANCE == v3.PLACEBO_TOLERANCE == 0.02
