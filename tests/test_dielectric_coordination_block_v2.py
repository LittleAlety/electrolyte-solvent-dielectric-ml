"""Guards for the lever-8 second shot (`probes/dielectric_coordination_block_v2.py`).

The second shot re-runs the same frozen scoreboard with the same frozen
coordination block and the same shuffled label vector, but reads the placebo
clause against a no-information floor as lever 2 and lever 9 already do. These
tests pin three things: the v1 record is byte-identical, the v2 verdict is
recomputable from the v2 artefacts alone, and the amended clause really is
evaluated on all three readings.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes import dielectric_coordination_block_v2 as v2

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(v2.SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(v2.PREREG_PATH.read_text(encoding="utf-8"))


def _r2(summary: dict, arm: str, representation: str = v2.HYBRID) -> float:
    return float(summary["arms"][arm][representation]["r2"]["mean"])


# --------------------------------------------------------------------------- #
# the v1 record is untouched
# --------------------------------------------------------------------------- #


def test_v1_files_still_carry_the_digests_recorded_at_lock_time(prereg: dict) -> None:
    recorded = prereg["v1_is_not_edited"]["v1_artefact_digests_observed_at_lock_time"]
    assert recorded, "the pre-registration must record what v1 looked like"
    for relative, digest in recorded.items():
        assert sha256_of(REPOSITORY_ROOT / relative) == digest, relative


def test_the_frozen_red_lines_are_intact(prereg: dict) -> None:
    for entry in prereg["frozen_red_lines_untouched"]:
        relative, _, digest = entry.partition(" digest ")
        assert digest, entry
        assert sha256_of(REPOSITORY_ROOT / relative) == digest, relative


def test_v2_does_not_rewrite_any_v1_output(summary: dict) -> None:
    for path in summary["outputs"].values():
        assert "_v2" in Path(str(path)).name or "coordination_block_v2" in str(path), path


def test_v1_decision_is_still_recorded_as_dead(prereg: dict) -> None:
    assert prereg["v1_is_not_edited"]["v1_decision_is_still_in_force"] == "dead"
    v1_summary = json.loads(
        (REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert v1_summary["verdict"]["decision"] == "dead"


def test_the_superseded_clause_is_kept_verbatim(prereg: dict) -> None:
    untouched = json.loads(
        (REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_prereg.json").read_text(
            encoding="utf-8"
        )
    )
    kept = prereg["superseded_placebo_clause"]["fields_verbatim"]
    assert kept["secondary_criterion"] == untouched["secondary_criterion"]
    assert kept["kill_line"] == untouched["kill_line"]
    assert kept["arms_entry"] == untouched["arms"][2]


# --------------------------------------------------------------------------- #
# release format
# --------------------------------------------------------------------------- #


def test_v2_csvs_are_lf_only_without_bom() -> None:
    for name in ("folds", "repeats", "predictions"):
        blob = (v2.ARTIFACTS_DIR / (v2.ARTIFACT_STEM + "_" + name + ".csv")).read_bytes()
        assert b"\r\n" not in blob
        assert not blob.startswith(b"\xef\xbb\xbf")


def test_v2_report_is_lf_only_without_bom() -> None:
    blob = v2.REPORT_PATH.read_bytes()
    assert b"\r\n" not in blob
    assert not blob.startswith(b"\xef\xbb\xbf")


def test_report_on_disk_is_the_render_of_the_summary(summary: dict) -> None:
    assert v2.REPORT_PATH.read_text(encoding="utf-8").splitlines() == v2.format_report(summary)


# --------------------------------------------------------------------------- #
# the frozen contract and the reproduction guard
# --------------------------------------------------------------------------- #


def test_baseline_reproduces_the_published_r2(summary: dict) -> None:
    baseline = _r2(summary, v2.ARM_BASELINE)
    assert abs(baseline - v2.BASELINE_R2) <= v2.REPRODUCTION_TOLERANCE
    assert summary["verdict"]["baseline_reproduced"] is True
    assert summary["verdict"]["baseline_abs_delta"] <= v2.REPRODUCTION_TOLERANCE


def test_the_scoreboard_is_the_frozen_457_and_97(summary: dict) -> None:
    scoreboard = summary["scoreboard"]
    assert scoreboard["scored_rows"] == 457
    assert scoreboard["compounds_scored"] == 97
    assert scoreboard["folds"] == 50
    assert scoreboard["executed_repeats"] == 10
    assert scoreboard["folds_with_a_straddling_compound"] == 0


def test_the_folds_are_the_v1_folds_not_new_ones(summary: dict) -> None:
    rows = read_rows(v2.ARTIFACTS_DIR / (v2.ARTIFACT_STEM + "_folds.csv"))
    assert rows
    for row in rows:
        assert 0 <= int(row["fold"]) < 5
        assert int(row["train_rows"]) + int(row["test_rows"]) == 457
    sizes = {
        (row["repeat"], row["fold"], row["train_rows"], row["test_rows"])
        for row in rows
        if row["arm"] == v2.ARM_BASELINE
    }
    assert len(sizes) == 50


# --------------------------------------------------------------------------- #
# the amended placebo clause
# --------------------------------------------------------------------------- #


def test_the_floor_is_the_training_fold_mean(summary: dict) -> None:
    floor = summary["floors"][v2.ARM_FLOOR][v2.HYBRID]
    rows = read_rows(v2.ARTIFACTS_DIR / (v2.ARTIFACT_STEM + "_predictions.csv"))
    floor_rows = [row for row in rows if row["arm"] == v2.ARM_FLOOR]
    assert floor_rows
    by_fold: dict[tuple[str, str], list[float]] = {}
    for row in floor_rows:
        by_fold.setdefault((row["repeat"], row["fold"]), []).append(float(row["prediction"]))
    # a fold-mean predictor is constant inside a fold
    for values in by_fold.values():
        assert max(values) - min(values) < 1e-12
    assert float(floor["r2"]["mean"]) < 0.05


def test_the_placebo_and_the_floor_sit_on_the_identical_label_vector(summary: dict) -> None:
    readings = summary["arms"]
    real_baseline = _r2(summary, v2.ARM_BASELINE)
    floor_real = float(summary["floors"][v2.ARM_FLOOR_REAL][v2.HYBRID]["r2"]["mean"])
    # the real-label floor is the mean-only reference for the real baseline
    assert floor_real < 0.05
    assert abs(summary["shuffled_vector"]["real_baseline_r2"] - real_baseline) <= 1e-12
    assert readings[v2.ARM_PLACEBO][v2.HYBRID]["r2"]["mean"] == summary["collapse"]["placebo_r2"]


def test_the_amended_clause_is_evaluated_on_all_three_readings(summary: dict) -> None:
    collapse = summary["collapse"]
    assert collapse["tolerance"] == v2.PLACEBO_TOLERANCE
    floor_delta = collapse["placebo_r2"] - collapse["placebo_floor_r2"]
    assert abs(collapse["over_the_floor"] - floor_delta) <= 1e-12
    assert collapse["floor_rule_holds"] is (floor_delta <= v2.PLACEBO_TOLERANCE)
    real_arm_delta = collapse["placebo_r2"] - _r2(summary, v2.ARM_PLUS)
    assert abs(collapse["delta_vs_the_same_pipeline_real_arm"] - real_arm_delta) <= 1e-12
    assert collapse["real_arm_rule_holds"] is (real_arm_delta <= v2.PLACEBO_TOLERANCE)
    inside = collapse["placebo_r2"] - _r2(summary, v2.ARM_PLACEBO_BASELINE)
    assert abs(collapse["within_pipeline_delta_r2"] - inside) <= 1e-12
    assert collapse["within_pipeline_rule_holds"] is (inside <= v2.PLACEBO_TOLERANCE)
    assert collapse["collapsed"] is (
        collapse["floor_rule_holds"]
        and collapse["real_arm_rule_holds"]
        and collapse["within_pipeline_rule_holds"]
    )


# --------------------------------------------------------------------------- #
# the verdict is recomputable from the artefacts alone
# --------------------------------------------------------------------------- #


def test_the_decision_follows_from_the_artefacts(summary: dict) -> None:
    verdict = summary["verdict"]
    delta = _r2(summary, v2.ARM_PLUS) - _r2(summary, v2.ARM_BASELINE)
    assert abs(verdict["delta_r2"] - delta) <= 1e-12
    collapsed = bool(summary["collapse"]["collapsed"])
    if not verdict["baseline_reproduced"]:
        expected = "unverified"
    elif not collapsed:
        expected = "dead"
    elif delta >= v2.PASS_DELTA:
        expected = "pass_under_amended_placebo_clause"
    elif delta < v2.KILL_DELTA:
        expected = "dead"
    else:
        expected = "sub_threshold"
    assert verdict["decision"] == expected
    assert verdict["decision"] in set(v2.DECISION_VOCABULARY)


def test_a_pass_carries_its_qualifier_in_the_report(summary: dict) -> None:
    report = v2.REPORT_PATH.read_text(encoding="utf-8")
    assert "v1" in report
    assert "dead" in report
    assert summary["merge_arm"] is not None
    if summary["verdict"]["decision"] == "pass_under_amended_placebo_clause":
        assert "pass_under_amended_placebo_clause" in report
        assert "dead" in report, "the v1 verdict must be reported beside a v2 pass"


def test_check_artifacts_reports_no_problem() -> None:
    assert v2.check_artifacts() == 0
