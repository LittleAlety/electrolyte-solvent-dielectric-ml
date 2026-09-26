"""Delivery-package regression tests for the Week 14 export."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week14_results import (
    ARTIFACTS,
    BASELINE_R2,
    BLOCK_V2_AMENDMENT_NOTE,
    COORDINATION_BLOCK_FEATURES,
    FROZEN_DIGEST,
    OBSERVATIONS_SHA256,
    PILOT_POOL_SHA256,
    PREREG_V1_SHA256,
    R2_LEVERS_PREREG_SHA256,
    README_TEXT,
    VERIFIERS,
    WEEK,
    _parse_args,
    blockless_status_counts,
    export_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week14")
    return root, export_results(output_root=root, overwrite=False)


def _summary(root: Path) -> dict:
    return json.loads((root / WEEK / "week14_summary.json").read_text(encoding="utf-8"))


def _json(relative: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def test_every_declared_artifact_exists_in_the_repository() -> None:
    missing = [source for source, _ in ARTIFACTS if not (REPOSITORY_ROOT / source).is_file()]
    assert missing == []


def test_export_ships_every_artifact_readme_manifest_and_verification(
    exported: tuple[Path, dict],
) -> None:
    root, result = exported
    week_root = root / WEEK

    assert result["verification_passed"] is True
    for _, destination in ARTIFACTS:
        assert (week_root / destination).is_file()
    for name in ("README.md", "week14_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file()
    assert verify_export_manifest(week_root) == []


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / WEEK).mkdir()
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)


def test_the_overwrite_flag_is_wired_through_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_week14_results.py", "--overwrite"])
    assert _parse_args().overwrite is True
    monkeypatch.setattr(sys, "argv", ["export_week14_results.py"])
    assert _parse_args().overwrite is False


def test_declared_verifiers_are_real_scripts() -> None:
    for command in VERIFIERS:
        parts = shlex.split(command)
        if parts[0] == "-m":
            assert len(parts) >= 3 and parts[1] == "pytest", command
            for target in parts[2:]:
                if target.endswith(".py"):
                    assert (REPOSITORY_ROOT / target).is_file(), command
            continue
        assert (REPOSITORY_ROOT / parts[0]).is_file(), command


def test_summary_pins_every_frozen_red_line(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    red_lines = _summary(root)["frozen_red_lines"]

    for name, expected in (
        ("data/dielectric_v03.csv", FROZEN_DIGEST),
        ("probes/l3_stage1_pilot_pool.csv", PILOT_POOL_SHA256),
        ("probes/l3_backvalidation_prereg.json", PREREG_V1_SHA256),
        ("data/processed/dielectric_observations_v11plus.csv", OBSERVATIONS_SHA256),
        ("probes/dielectric_r2_levers_prereg.json", R2_LEVERS_PREREG_SHA256),
    ):
        entry = red_lines[name]
        assert entry["sha256"] == expected, name
        assert entry["intact"] is True, name


def test_summary_records_the_scoreboard_and_the_276_pair_caveat(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    scoreboard = _summary(root)["main_scoreboard"]

    assert scoreboard["rows_scored"] == 457
    assert scoreboard["compounds_scored"] == 97
    assert scoreboard["distinct_compound_temperature_pairs"] == 276
    assert scoreboard["baseline_r2"] == BASELINE_R2
    assert "never 457" in scoreboard["note"]
    assert _summary(root)["baseline_reproduction"]["bit_exact"] is True
    assert len(_summary(root)["baseline_reproduction"]["scripts"]) == 7


def test_every_lever_readout_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    """The package must re-read the levers, never restate them from memory."""

    root, _ = exported
    levers = _summary(root)["levers"]

    lever2 = _json("probes/dielectric_association_features_summary.json")["verdict"]
    lever3 = _json("probes/dielectric_target_transform_probe_summary.json")["verdict"]
    lever4 = _json("probes/dielectric_xtb_full_table_migration_summary.json")
    lever7 = _json("probes/dielectric_bagging_probe_summary.json")["verdict"]
    lever9 = _json("probes/dielectric_knowledge_purity_sweep_summary.json")

    assert levers["lever_2_association_features"]["delta_r2"] == lever2["delta_r2"]
    assert levers["lever_2_association_features"]["decision"] == lever2["decision"] == "dead"
    assert levers["lever_3_target_transform"]["delta_r2"] == lever3["delta_r2"]
    assert levers["lever_3_target_transform"]["decision"] == lever3["decision"] == "dead"
    assert levers["lever_4_xtb_migration"]["delta_r2"] == lever4["verdict"]["delta_r2"]
    assert levers["lever_4_xtb_migration"]["decision"] == lever4["verdict"]["state"] == "pass"
    assert levers["lever_7_bagging"]["decision"] == lever7["decision"] == "dead"
    assert levers["lever_9_knowledge_purity"]["decision"] == lever9["verdict"]["decision"]
    assert levers["lever_9_knowledge_purity"]["decision"] == "sub_threshold"


def test_lever_3_records_that_the_log_dividend_did_not_survive(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    diagnostic = _summary(root)["levers"]["lever_3_target_transform"]["log_space_diagnostic"]

    assert diagnostic["vanished_after_back_transform"] is True
    assert diagnostic["log_gain_over_raw"] > 0.2
    assert diagnostic["note"].startswith("log-space R2 and raw-space R2")


def test_lever_8_keeps_the_v1_dead_verdict_and_ships_the_amendment_separately(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lever8 = _summary(root)["levers"]["lever_8_coordination_block"]

    v1 = _json("probes/dielectric_coordination_block_summary.json")["verdict"]
    v2 = _json("probes/dielectric_coordination_block_v2_summary.json")["verdict"]

    assert v1["decision"] == "dead"
    assert lever8["v1_decision"] == "dead"
    assert lever8["v1_kill_reasons"] == v1["kill_reasons"]
    assert v2["decision"] == "pass_under_amended_placebo_clause"
    assert lever8["v2_decision"] == "pass_under_amended_placebo_clause"
    assert v2["v1_decision_is_still_in_force"] == "dead"
    assert lever8["v1_decision_is_still_in_force"] == "dead"
    assert "v2_note" not in lever8
    # same block, same folds, same shuffled vector: the readout is bit-identical
    assert v1["delta_r2"] == v2["delta_r2"]


def test_lever_4_coverage_gap_is_recorded(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lever4 = _summary(root)["levers"]["lever_4_xtb_migration"]

    assert lever4["coverage"]["scored_compounds_migrated"] == 95
    assert lever4["coverage"]["scored_compounds_total"] == 97
    assert _json("probes/dielectric_xtb_full_table_migration_summary.json")["readings"][
        "completeness"
    ] == "partial_coverage"


def test_shots_are_counted_per_channel_and_the_merge_arm_never_ran(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    shots = _summary(root)["shots"]

    assert shots["by_channel"] == {
        "lever_2": 1,
        "lever_3": 1,
        "lever_4": 1,
        "lever_7": 1,
        "lever_8": 2,
        "lever_9": 4,
    }
    assert shots["total_main_scoreboard_attempts"] == 10
    assert shots["total_main_scoreboard_attempts"] == sum(shots["by_channel"].values())
    assert shots["calibration_gate_attempts"] == {"feature_envelope_gate": 1}
    assert "not inside them" in shots["calibration_gate_is_not_a_gain_attempt"]
    assert shots["merge_arm_attempts"] == 0
    assert "not a discovery" in shots["rule"]
    assert _json("probes/dielectric_merge_arm_summary.json")["merge_arm_run"] is False


def test_the_three_preregistration_defects_are_recorded(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    defects = _summary(root)["preregistration_defects"]

    assert "unsatisfiable by" in defects["placebo_collapse_clause"]
    assert "never names its reference" in defects["placebo_collapse_clause"]
    assert "authoritative" in defects["locked_at_utc_vs_mtime"]
    assert "backfilled" in defects["locked_at_utc_vs_mtime"]
    assert "never serve as the gate" in defects["boolean_collapse_fields"]


def test_the_envelope_gate_is_not_claimed_as_a_usable_filter(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    gate = _summary(root)["feature_envelope_gate"]

    assert gate["verdict"] == "primary_met_secondary_not_met"
    assert gate["criteria"]["primary_met"] is True
    assert gate["criteria"]["secondary_met"] is False
    assert gate["secondary_check"]["flag_rate_combined"] > gate["secondary_check"]["threshold"]
    assert "must not be described as a usable filter" in gate["discipline"]


def test_al_round_4_is_offline_and_keeps_its_two_tables_distinct(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    al4 = _summary(root)["al_round_4"]

    assert al4["run_mode"] == "offline_local_only"
    assert al4["network_calls"] == 0
    assert al4["runs"] == 1
    assert "shots" not in al4
    assert _json("probes/al_round4_new_compound_backfill_summary.json")["shots"] == 1
    assert al4["list_stats"]["rows"] == 21
    assert al4["new_compound_stats"]["count"] == 7
    boundaries = "\n".join(al4["honesty_boundaries"])
    assert boundaries


def test_readme_refuses_to_present_the_two_crossings_as_a_discovery() -> None:
    assert "本身不构成发现" in README_TEXT
    assert "不得**与 v1.0" in README_TEXT
    assert "包络闸门不得宣称为可用过滤器" in README_TEXT
    assert "三份" in README_TEXT and "mtime" in README_TEXT
    assert "不计入" in README_TEXT


def test_every_exported_csv_is_lf_only(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    offenders = []
    for path in (root / WEEK).rglob("*.csv"):
        if b"\r\n" in path.read_bytes():
            offenders.append(path.name)
    assert offenders == []


def test_summary_separates_the_artifacts_commit_from_the_export_time_head(
    exported: tuple[Path, dict],
) -> None:
    """``head_commit`` alone cannot say whether the shipped files came from a commit.

    The v1.0 package recorded ``head_commit = f5663a0`` while shipping week-14
    files that commit does not contain, so the package now records the
    export-time HEAD *and* the dirty state that decides whether that HEAD is a
    usable coordinate for the shipped artefacts.
    """

    root, _ = exported
    summary = _summary(root)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout.strip()

    assert isinstance(summary["artifacts_commit"], str)
    assert summary["artifacts_commit"] == head
    assert isinstance(summary["head_commit"], str)
    assert summary["head_commit"] == head
    assert isinstance(summary["worktree_dirty"], bool)
    assert isinstance(summary["worktree_dirty_paths"], int)
    assert summary["worktree_dirty_paths"] >= 0
    assert summary["worktree_dirty"] is (summary["worktree_dirty_paths"] > 0)
    note = summary["provenance_note"]
    assert "artifacts_commit" in note
    assert "head_commit" in note
    assert "worktree_dirty" in note
    # An unconditional "artifacts_commit is the coordinate" sentence would
    # contradict a dirty export, which is exactly the v1.0 failure mode.
    assert "only when worktree_dirty is false" in note


def test_the_v2_block_clause_ships_as_a_post_reading_amendment(
    exported: tuple[Path, dict],
) -> None:
    """v2 was locked after the v1 readout, so it is not a blind pre-registration."""

    root, _ = exported
    defects = _summary(root)["preregistration_defects"]

    assert defects["block_v2_post_reading_amendment"] == BLOCK_V2_AMENDMENT_NOTE
    assert BLOCK_V2_AMENDMENT_NOTE in README_TEXT
    for phrase in (
        "非盲锁",
        "03:57:03Z",
        "04:02:50Z",
        "5 分 47 秒",
        "pass_under_amended_placebo_clause",
        "v1 的 dead 逐字保留",
    ):
        assert phrase in BLOCK_V2_AMENDMENT_NOTE, phrase
    assert "仅预注册、本轮未跑" in README_TEXT


def test_the_blockless_compounds_are_counted_from_the_feature_table(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lever8 = _summary(root)["levers"]["lever_8_coordination_block"]

    blockless = blockless_status_counts(COORDINATION_BLOCK_FEATURES)
    assert blockless == {"undefined_no_hetero_site": 9}
    assert lever8["scored_compounds_without_the_block"] == sum(blockless.values()) == 9
    note = lever8["coverage_note"]
    assert "compounds_without_the_block=60" in note
    assert "scored_compounds_without_the_block=9" in note
    assert "+ 51 compounds" in note
    block = _json("probes/dielectric_coordination_block_summary.json")["coordination_block"]
    assert len(block["compounds_without_the_block"]) == 60


def test_the_blockless_counter_reads_the_status_column(tmp_path: Path) -> None:
    path = tmp_path / "features.csv"
    path.write_text(
        "inchikey,name,status\n"
        "AAAAAA-AAAAA-AAAAA,a,ok\n"
        "BBBBBB-BBBBB-BBBBB,b,undefined_no_hetero_site\n"
        "CCCCCC-CCCCC-CCCCC,c,ok\n"
        "DDDDDD-DDDDD-DDDDD,d,undefined_no_hetero_site\n",
        encoding="utf-8",
        newline="\n",
    )
    assert blockless_status_counts(path) == {"undefined_no_hetero_site": 2}
