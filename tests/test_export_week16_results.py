"""Delivery-package regression tests for the Week 16 export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week16_results import (
    ARTIFACTS,
    EXEC_BIT_REPAIR_NOTE,
    FROZEN_RED_LINES,
    MAIN_SCOREBOARD,
    PRE_REPAIR_LIST_COMMIT,
    PRE_REPAIR_RECORDED_FILES,
    RANDOM_ROW_LEAK_REFERENCE_R2,
    README_TEXT,
    VERIFIERS,
    WEEK,
    _parse_args,
    export_results,
    trace_file_census,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The expectations are written out as literals on purpose.  Reading them back
# out of the module would let a mutated constant keep its own test green: the
# assertion below therefore pins the literals *and* the module constants.
RED_LINE_EXPECTATIONS = (
    ("data/dielectric_v03.csv", "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"),
    ("probes/l3_stage1_pilot_pool.csv", "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"),
    (
        "probes/l3_backvalidation_prereg.json",
        "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    ),
    (
        "data/processed/dielectric_observations_v11plus.csv",
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    ),
    (
        "probes/dielectric_r2_levers_prereg.json",
        "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    ),
    ("data/viscosity_v01.csv", "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"),
)
FROZEN_BASELINE_R2 = 0.4091179943351143
FROZEN_LEAK_REFERENCE_R2 = 0.7385332681453336

# The narrative numbers live in prose, so a mutant can change one of them and keep
# every machine-lane assertion green (measured: rewriting 1,690 -> 1,691 left all
# 21 tests passing).  The README bytes are therefore pinned by a literal digest --
# a deliberate edit has to move this line -- and the numbers the prose must carry
# are asserted as literals of their own.
README_SHA256 = "dd221baa0de3df4a0e24e5ed86aaf32cede1751843bcd45017fd7d8fd5f59823"
README_NARRATIVE_NUMBERS = (
    "11,923",
    "**1,690**",
    "**70**",
    "**1,743**",
    "1.72%",
    "34/34",
    "10 ＋ 结构层 5",
    "4 条携带几何派生特征",
    "**119**",
    "tracked_candidates = 98",
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week16")
    return root, export_results(output_root=root, overwrite=False)


def _summary(root: Path) -> dict:
    return json.loads((root / WEEK / "week16_summary.json").read_text(encoding="utf-8"))


def _json(relative: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def _lane(root: Path, name: str) -> dict:
    return _summary(root)["lanes"][name]


def _cited_trace_files(text: str) -> set[str]:
    """The distinct files a shipped backfill list cites, with the path:tier suffix stripped."""

    return {
        entry.split(":")[0]
        for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        for entry in (row.get("local_trace_files") or "").split(";")
        if entry.strip()
    }


def _local_trace_tally(text: str) -> dict[str, int]:
    """How many shipped rows fall under each local_trace value."""

    tally = dict.fromkeys(("yes", "no", "na"), 0)
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        value = row.get("local_trace")
        if value in tally:
            tally[value] += 1
    return tally


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
        assert (week_root / destination).is_file(), destination
    for name in ("README.md", "week16_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file(), name
    assert verify_export_manifest(week_root) == []


def test_the_summary_records_the_artifact_list_it_shipped(exported: tuple[Path, dict]) -> None:
    _, result = exported
    assert result["artifacts"] == [destination for _, destination in ARTIFACTS]


def test_the_shipped_readme_is_the_module_constant(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    assert (root / WEEK / "README.md").read_text(encoding="utf-8") == README_TEXT
    assert _summary(root)["week"] == WEEK == "week16"


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / WEEK).mkdir()
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)


def test_the_overwrite_flag_is_wired_through_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_week16_results.py", "--overwrite"])
    assert _parse_args().overwrite is True
    monkeypatch.setattr(sys, "argv", ["export_week16_results.py"])
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


def test_the_verifier_block_actually_ran_and_passed(exported: tuple[Path, dict]) -> None:
    _, result = exported
    checks = result["verification"]["checks"]

    assert [check["command"] for check in checks] == list(VERIFIERS)
    assert all(check["passed"] and check["exit_code"] == 0 for check in checks)
    assert result["verification"]["passed"] is True


def test_summary_pins_every_frozen_red_line(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = _summary(root)
    red_lines = summary["frozen_red_lines"]

    assert dict(RED_LINE_EXPECTATIONS) == FROZEN_RED_LINES
    assert set(red_lines) == {name for name, _ in RED_LINE_EXPECTATIONS}
    for relative, expected in RED_LINE_EXPECTATIONS:
        entry = red_lines[relative]
        assert entry["sha256"] == expected, relative
        assert entry["expected_sha256"] == expected, relative
        assert entry["intact"] is True, relative
    assert summary["frozen_red_lines_all_intact"] is True


def test_the_round_fits_no_model_and_touches_no_scoreboard(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = _summary(root)

    assert MAIN_SCOREBOARD == FROZEN_BASELINE_R2
    assert RANDOM_ROW_LEAK_REFERENCE_R2 == FROZEN_LEAK_REFERENCE_R2
    assert summary["main_scoreboard"]["touched"] is False
    assert summary["main_scoreboard"]["value"] == FROZEN_BASELINE_R2
    assert summary["shots"]["main_scoreboard_attempts"] == 0
    assert summary["shots"]["models_fitted"] == 0
    assert summary["shots"]["r2_reported_anywhere"] is False
    assert summary["random_row_leak_reference_r2"] == FROZEN_LEAK_REFERENCE_R2
    assert summary["buys_no_new_r2"]

    fitted = summary["lanes"]["d8_kpi_funnel_cross_run"]["model_fitting"]
    assert fitted["fitted_any_model"] is False
    assert fitted["r2_reported"] is False


def test_the_d8_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "d8_kpi_funnel_cross_run")
    source = _json("probes/kpi_funnel_cross_run_summary.json")
    first = source["criterion_a_self_consistency"]
    second = source["criterion_b_identity"]
    third = source["criterion_c_intersection"]

    assert lane["shortlist_rows"] == source["source"]["shortlist_rows"] == 29
    assert lane["shortlist_by_shortlist"] == source["source"]["shortlist_by_shortlist"]
    assert lane["identity_resolution"]["resolved"] == lane["identity_resolution"]["rows"] == 29

    assert lane["criterion_a_self_consistency"]["rows_checked"] == first["rows_checked"] == 29
    assert lane["criterion_a_self_consistency"]["rows_with_violations"] == 0
    assert lane["criterion_a_self_consistency"]["passed"] is True
    assert lane["criterion_b_identity"]["resolved"] == second["resolved"] == 29
    assert lane["criterion_b_identity"]["required"] == 29
    assert lane["criterion_c_intersection"] == {
        "distinct_inchikeys": third["distinct_inchikeys"],
        "vs_batt_p30k": third["vs_batt_p30k"]["n"],
        "vs_roster_314": third["vs_roster_314"]["n"],
        "vs_epsilon_v03": third["vs_epsilon_v03"]["n"],
        "vs_epsilon_v11plus": third["vs_epsilon_v11plus"]["n"],
    }

    stages = {stage["id"]: stage for stage in lane["funnel_ours"]}
    source_stages = {stage["id"]: stage for stage in source["funnel_ours"]}
    assert list(stages) == ["S0", "S1", "S2", "S3", "S4"]
    assert stages["S0"]["survivors"] == stages["S1"]["survivors"] == 29519
    assert stages["S1"]["excluded_here"] == 0
    assert stages["S2"]["survivors"] == 22249
    assert stages["S3"]["survivors"] == 11709
    assert stages["S4"]["survivors"] is None
    for key in ("S0", "S1", "S2", "S3", "S4"):
        assert stages[key]["survivors"] == source_stages[key]["survivors"], key

    assert lane["element_whitelist"]["status"] == "derived_not_declared"
    assert "pool_different" in lane["pools"]["comparability"]
    assert lane["forbidden_compliance"]["s4_claimed_as_run"] is False
    assert lane["forbidden_compliance"]["random_row_leakage_used"] is False
    assert lane["forbidden_compliance"]["guessed_structures_filled_in"] is False


def test_the_unimol_lane_matches_its_preregistration(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "u_unimol_probe_spec")
    spec = _json("probes/unimol_probe_spec_prereg.json")

    assert lane["status"] == spec["status"] == "locked_before_run"
    assert lane["locked_at_utc"] == spec["locked_at_utc"]
    assert lane["title"] == spec["title"]
    assert lane["scope_of_this_round"]["this_round_runs_no_model"] is True
    assert lane["scope_of_this_round"]["this_round_writes_only_the_spec"] is True
    assert lane["scope_of_this_round"]["r2_claimed_this_round"] is False
    assert lane["scope_of_this_round"]["shots_this_round"] == 0
    assert lane["kill_line_verbatim_zh"] == spec["kill_line"]["verbatim_zh"]
    assert lane["frozen_red_lines_declared"] == spec["frozen_red_lines"]["count"] == 6
    assert lane["evaluation_protocol"]["splitter"] == spec["evaluation_protocol"]["splitter"]
    assert lane["registered_uncertainties"] == len(spec["registered_uncertainties"])
    assert lane["forbidden_rules"] == len(spec["forbidden"])
    assert lane["conformer_count_conflict"]["no_silent_resolution"] is True


def test_the_online_slice_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "f1_online_viscosity_slice")
    source = _json("probes/thermoml_viscosity_online_slice_summary.json")

    assert lane["prereg_sha256"] == source["prereg"]["sha256"]
    assert lane["total_records_query_star"] == 11923
    assert lane["slice_records"] == {"viscosity_pa_s": 1690, "kinematic_viscosity": 70}
    assert lane["slice_records_collected"] == lane["slice_records"]
    assert lane["page_num_base"] == 0
    assert lane["criterion_a_online_slice"]["passed"] is True
    assert lane["criterion_a_online_slice"]["n_violations"] == 0

    subset = lane["criterion_b_local_subset"]
    assert subset["local_doi_count"] == subset["n_present"] == 29
    assert subset["n_misses"] == 0
    assert subset["online_union_dois"] == 1743
    assert subset["passed"] is True

    honesty = lane["criterion_c_unit_honesty"]
    assert honesty["size_unit"] == "record"
    assert honesty["online_row_count"] == "unknown"
    assert honesty["coverage"]["record_basis"]["ratio"] == pytest.approx(29 / 1690)
    assert honesty["coverage"]["row_basis"]["comparable"] is False
    assert honesty["coverage"]["row_basis"]["online_rows"] == "unknown"
    assert honesty["passed"] is True

    assert lane["requests_spent"] <= lane["request_budget"]
    assert lane["run_mode"] == source["run_provenance"]["run_mode"]


def test_the_trace_repair_lane_is_recomputed_from_git_and_matches(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _lane(root, "f2_trace_source_repair")
    generator = _json("probes/al_round4_new_compound_backfill_summary.json")

    assert lane["trace_scan_census"] == generator["trace_scan_census"]
    census = lane["trace_file_census"]
    assert census == trace_file_census(REPOSITORY_ROOT)
    assert census["distinct_local_trace_files"] == 77
    assert census["local_trace"] == {"yes": 18, "no": 2, "na": 1}

    comparison = census["repair_comparison"]
    if comparison["available"] is not True:
        pytest.skip(
            "the pre-repair list is read out of git by commit id; on a clone that "
            "cannot reach that commit the comparison degrades to available=false "
            "with the recorded file count instead, and there is nothing to compare"
        )
    assert comparison["pre_repair_commit"] == PRE_REPAIR_LIST_COMMIT
    assert comparison["pre_repair_distinct_files"] == PRE_REPAIR_RECORDED_FILES == 148
    assert comparison["post_repair_distinct_files"] == 77
    assert comparison["disappeared"] == 148 - 77 == 71
    assert comparison["added"] == 0
    assert comparison["disappeared_by_root"] == {"external": 69, "processed": 2}
    assert sum(comparison["disappeared_by_root"].values()) == comparison["disappeared"]
    assert comparison["local_trace_flipped"] is False
    assert comparison["local_trace_after"] == census["local_trace"]

    counts = generator["trace_scan_census"]
    assert counts["tracked_candidates"] == 98
    assert counts["restricted_local_only_candidates"] == 21
    assert counts["tracked_candidates"] + counts["restricted_local_only_candidates"] == 119
    assert counts["total_candidates"] == 119
    assert generator["list_stats"]["rows"] == 21


def test_the_repair_comparison_recomputes_both_states_from_git() -> None:
    """Neither side of the before/after census is remembered; both are re-read from git.

    The parse is re-implemented here instead of calling the exporter's own helper, so
    the shipped comparison is checked against an independent reading of the working
    tree and of the pre-repair blob at PRE_REPAIR_LIST_COMMIT.
    """

    list_path = "probes/al_round4_backfill_list_v0.csv"
    now_text = (REPOSITORY_ROOT / list_path).read_text(encoding="utf-8-sig")
    completed = subprocess.run(
        ["git", "show", f"{PRE_REPAIR_LIST_COMMIT}:{list_path}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("the pre-repair commit is not reachable in this clone")
    before_text = completed.stdout
    before = _cited_trace_files(before_text)
    now = _cited_trace_files(now_text)

    disappeared_by_root: dict[str, int] = {}
    for path in sorted(before - now):
        parts = path.split("/")
        if parts[0] == "data" and len(parts) > 2:
            disappeared_by_root[parts[1]] = disappeared_by_root.get(parts[1], 0) + 1

    comparison = trace_file_census(REPOSITORY_ROOT)["repair_comparison"]
    assert comparison["available"] is True
    assert comparison["pre_repair_commit"] == PRE_REPAIR_LIST_COMMIT
    assert comparison["pre_repair_distinct_files"] == len(before)
    assert len(before) == PRE_REPAIR_RECORDED_FILES
    assert comparison["post_repair_distinct_files"] == len(now)
    assert comparison["disappeared"] == len(before - now)
    assert comparison["added"] == len(now - before) == 0
    assert comparison["disappeared_by_root"] == dict(sorted(disappeared_by_root.items()))
    assert sum(comparison["disappeared_by_root"].values()) == comparison["disappeared"]

    before_tally = _local_trace_tally(before_text)
    after_tally = _local_trace_tally(now_text)
    assert comparison["local_trace_before"] == before_tally
    assert comparison["local_trace_after"] == after_tally
    assert before_tally == after_tally
    assert comparison["local_trace_flipped"] is False

    # The token the defect was found through is gone from the working-tree list.
    assert not any(path.endswith("kpi_shortlist_identity/108-32-7.json") for path in now)




def test_the_identity_decision_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "f3_identity_drawing_decision")
    source = _json("probes/identity_smiles_drawing_decision_summary.json")

    assert lane["counts"] == source["counts"]
    assert lane["counts"]["differing_keys_total"] == 15
    assert lane["counts"]["stereo_only"] + lane["counts"]["structural"] == 15
    assert lane["counts"]["structural"] == 5
    assert lane["counts"]["structural_authored_in_identity_layer"] == 0
    assert lane["gates"] == {
        name: bool(gate.get("passed")) for name, gate in sorted(source["gates"].items())
    }
    assert all(lane["gates"].values())
    geometry = lane["geometry_derived_feature_census"]
    assert geometry["n_keys_with_geometry_derived_features"] == 4
    assert len(geometry["keys"]) == 4

    decision = lane["decision"]
    assert decision["status"] == "recommended_no_rewrite_awaiting_human_confirmation"
    assert decision["no_data_change_made"] is True
    assert source["run_telemetry"]["writes_under_data"] == 0


def test_the_exec_bit_repair_is_what_the_index_records(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _summary(root)["exec_bit_repair"]

    assert lane["path"] == "probes/kpi_funnel_cross_run.py"
    assert lane["index_mode_before"] == "100644"
    assert lane["index_mode_after"] == "100755"
    assert lane["content_changed"] is False
    assert lane["note"] == EXEC_BIT_REPAIR_NOTE

    completed = subprocess.run(
        ["git", "ls-files", "--stage", "--", lane["path"]],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        pytest.skip("the git index is not readable in this environment")
    assert completed.stdout.split()[0] == "100755"


def test_the_shipped_list_is_the_one_the_census_reads(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    with (root / WEEK / "al_round4_backfill_list_v0.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 21


def test_the_readme_explains_the_week15_drift_it_ships(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    text = (root / WEEK / "README.md").read_text(encoding="utf-8")

    assert "114 → 128" in text
    assert "146" in text
    assert "148 → 77" in text
    assert "消失 **71**" in text
    assert "Week 15 包**不回改**" in text
    assert "lanes.f2_trace_source_repair.trace_file_census.repair_comparison" in text


def test_the_readme_ships_the_boundaries_the_summary_claims(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    text = (root / WEEK / "README.md").read_text(encoding="utf-8")

    for needle in (
        "在线行数 = `unknown`",
        "data/restricted/",
        "0.7385332681453336",
        "0.4091179943351143",
        "858",
        "data/external/thermoml_api/",
    ):
        assert needle in text, needle


def test_every_exported_csv_is_lf_only(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    for path in (root / WEEK).rglob("*.csv"):
        assert b"\r\n" not in path.read_bytes(), path

def test_the_readme_text_is_pinned_by_a_literal_digest() -> None:
    assert hashlib.sha256(README_TEXT.encode("utf-8")).hexdigest() == README_SHA256


def test_the_readme_carries_the_numbers_the_lanes_measured(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    text = (root / WEEK / "README.md").read_text(encoding="utf-8")
    for needle in README_NARRATIVE_NUMBERS:
        assert needle in text, needle
