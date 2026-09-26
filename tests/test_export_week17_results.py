"""Delivery-package regression tests for the Week 17 export.

The expectations are literals on purpose.  Week 16's review found that the
machine lanes were pinned while the prose layer was free to rot (rewriting
1,690 -> 1,691 left all 21 tests green), so the README bytes are pinned by a
digest and every narrative number is asserted as a literal of its own.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week17_results import (
    ARTIFACTS,
    FROZEN_RED_LINES,
    INDEPENDENT_RECHECK_FACTS,
    LEVER_4_PLUS_LEVER_8_PROGRAMME_SHOTS_AFTER,
    MAIN_SCOREBOARD,
    MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
    RANDOM_ROW_LEAK_REFERENCE_R2,
    README_TEXT,
    RESTRICTED_EXCLUDED,
    VERIFIERS,
    W17_MAIN_SCOREBOARD_ATTEMPTS,
    WEEK,
    _parse_args,
    export_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

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
DIELECTRIC_V04_SHA256 = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"
DENSITY_V01_SHA256 = "47f920f773054ccd8789ac5679e3da5ca8ec732f8f6e79ba1f824cf68b2556ff"
WALDEN_PAIRS_SHA256 = "df2a0fe93b9d2f88009c4ded96b29378a10e0f4de5eca10ad84c41cea10c8cc3"
VISCOSITY_MAE_GATE = 0.15
DN_AUDIT_SHA256 = "3a80daa9f74c423bfcd6d2cbd3f6c54a6ffe2516daab0c3147e33d92adf7dab6"

# A mutant that rewrites one narrative number must move this line as well.
README_SHA256 = "3aeb9c45c3ea8be5ac021168647b676c8aa59306a857c22d6237801ecc3279c7"
README_NARRATIVE_NUMBERS = (
    "0.4091179943351143",
    "0.7481271437772365",
    "0.17477197208762",
    "0.19050925839013938",
    "0.13855083976437643",
    "0.2010970559642009",
    "0.23415453202842548",
    "0.2905180517963865",
    "0.4096241620366996",
    "182,154",
    "2,178",
    "73.17%",
    "176/176",
    "314",
    "0.24522292993630573",
    "0.5987261146496815",
    "36.4",
    "0.4766400383507876",
    "+0.0675220440156733",
    "+0.0200",
    "9/10",
    "+0.0998972687629372",
    "0.0323752247472639",
    "+0.011683591468432397",
    "8,359",
    "1,043",
    "1,219",
    "0.00%",
    "30%",
    "392",
    "42,941",
    "1,743",
    "268,247",
    "1,547",
    "1,228",
    "2,549",
    "2549/2549",
    "80 行观测",
    "0 Substances",
    "GAEKPEKOJKCEMS",
    "JYVATQXCHBTGRN",
    "89.78",
    "25 °C",  # non-breaking space before the unit, as the README writes it
    # W17-10 -- the four-core cross-channel registry.
    "31,949",
    "29,868",
    "0.6464482483155134",
    "n = **79**",
    "**51**",
    # W17-14 -- THEMol geometry + GFN2-xTB, the third orbital source.
    "6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80",
    "2,695,304",
    "5,117/31,949",
    "142/247",
    "242/1,228",
    "142,150,508",
    "166 行 / 34 列",
    "0.8557447540814086",
    "0.353095083458508 eV",
    "0.5295614175613801",
    "0.0903748834229043",
    "0.3072262053474138",
    "−1.0595 eV",
    "−7.0126 eV",
    "4.49e-05 eV",
    # W17-15 -- the second Reaxys thin-family batch.
    "19/17/16",
    "22/21/21",
    "12/0/0",
    "1/0/0",
    "11/21",
    "10/21",
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week17")
    return root, export_results(output_root=root, overwrite=False)


def _summary(root: Path) -> dict:
    return json.loads((root / WEEK / "week17_summary.json").read_text(encoding="utf-8"))


def _json(relative: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def _lane(root: Path, name: str) -> dict:
    return _summary(root)["lanes"][name]


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
    for name in ("README.md", "week17_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file(), name
    assert verify_export_manifest(week_root) == []


def test_the_summary_records_the_artifact_list_it_shipped(exported: tuple[Path, dict]) -> None:
    _, result = exported
    assert result["artifacts"] == [destination for _, destination in ARTIFACTS]


def test_the_shipped_readme_is_the_module_constant(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    assert (root / WEEK / "README.md").read_text(encoding="utf-8") == README_TEXT
    assert _summary(root)["week"] == WEEK == "week17"


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / WEEK).mkdir()
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)


def test_the_overwrite_flag_is_wired_through_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_week17_results.py", "--overwrite"])
    assert _parse_args().overwrite is True
    monkeypatch.setattr(sys, "argv", ["export_week17_results.py"])
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


def test_the_week_makes_exactly_one_scoreboard_attempt_and_counts_it(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = _summary(root)
    shots = summary["shots"]

    assert MAIN_SCOREBOARD == FROZEN_BASELINE_R2
    assert RANDOM_ROW_LEAK_REFERENCE_R2 == FROZEN_LEAK_REFERENCE_R2
    assert W17_MAIN_SCOREBOARD_ATTEMPTS == 1
    assert MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS == 11
    assert LEVER_4_PLUS_LEVER_8_PROGRAMME_SHOTS_AFTER == 4

    assert shots["main_scoreboard_attempts"] == 1
    assert shots["main_scoreboard_cumulative_attempts"] == 11
    assert shots["lever_4_plus_lever_8_programme_shots_after"] == 4
    assert shots["models_fitted"] == 1
    assert shots["r2_reported_anywhere"] is True

    scoreboard = summary["main_scoreboard"]
    assert scoreboard["value"] == FROZEN_BASELINE_R2
    assert scoreboard["touched"] is True
    assert scoreboard["baseline_reproduced"] is True
    assert scoreboard["baseline_abs_delta"] == 0.0
    assert summary["random_row_leak_reference_r2"] == FROZEN_LEAK_REFERENCE_R2


def test_the_v04_roster_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_1_dielectric_v04_roster")
    source = _json("probes/dielectric_v04_summary.json")

    # dataset_version is a string in every summary this repo has ever written
    # ("0.2", "0.3", "0.3.1"), so pin the string, not a float that would never
    # survive a patch-level version.
    assert lane["dataset_version"] == source["dataset_version"] == "0.4"
    assert lane["v03_row_count"] == source["v03_row_count"] == 246
    assert lane["row_count"] == source["row_count"] == 248
    assert lane["compound_count"] == source["compound_count"] == 247
    assert lane["addition_count"] == source["addition_count"] == 2
    assert lane["model_ready_addition_count"] == source["model_ready_addition_count"] == 0
    assert lane["conflict_addition_count"] == source["conflict_addition_count"] == 1

    table = lane["table"]
    assert table["path"] == "data/dielectric_v04.csv"
    assert table["rows"] == 248
    assert table["sha256"] == table["measured_sha256"] == DIELECTRIC_V04_SHA256
    assert table["digest_matches_summary"] is True
    assert table["expected_sha256"] == DIELECTRIC_V04_SHA256
    assert lane["frozen_v03_untouched"] is True
    # The frozen v0.3 bytes are the same digest the red-line block pins.
    assert dict(RED_LINE_EXPECTATIONS)["data/dielectric_v03.csv"] != DIELECTRIC_V04_SHA256


def test_the_thin_family_lane_is_a_plan_and_executes_no_query(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _lane(root, "w17_2_thin_family_backfill_queue")
    source = _json("probes/reaxys_thin_family_backfill_summary.json")

    assert lane["target_families"] == source["target_families"]
    assert lane["target_families"] == [
        "acid",
        "lactone",
        "carbonate",
        "sulfone",
        "protic_ionic_pair",
    ]
    assert lane["lower_bound"] == source["lower_bound"] == {
        "min_compounds": 5,
        "min_distinct_sources": 2,
    }
    assert lane["queue_rows"] == source["queue_rows"] == 124
    assert lane["queue_by_source"] == {
        "reaxys_stocking_queue": 14,
        "springer_materials_title_index": 110,
    }
    assert lane["reaxys_queries_executed"] == source["reaxys_queries_executed"] == 0
    assert all(
        report["meets_lower_bound"] is False for report in lane["family_report"].values()
    )


def test_the_density_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_4_density_v01")
    source = _json("probes/density_v01_summary.json")

    table = lane["table"]
    assert table["path"] == "data/density_v01.csv"
    assert table["rows"] == source["outputs"]["table"]["rows"] == 182154
    assert table["sha256"] == source["outputs"]["table"]["sha256"] == DENSITY_V01_SHA256
    assert table["unit"] == "kg/m3"
    assert len(table["columns"]) == 11

    catalog = lane["catalog"]
    assert catalog["slice_size_records"] == 4697
    assert catalog["pages_fetched"] == 47
    assert catalog["records_collected"] == 4697

    coverage = lane["coverage_vs_dielectric_v03"]
    assert coverage["target_size"] == 246
    assert coverage["density_size"] == 2178
    assert coverage["intersection_size"] == 180
    assert coverage["covered_fraction"] == pytest.approx(0.7317073170731707)
    assert coverage["covered_fraction"] == pytest.approx(180 / 246)

    unfreeze = lane["unfreeze"]
    assert unfreeze["local_rows"] == 176
    assert unfreeze["local_keys"] == 5
    assert unfreeze["exact_rows"] == 176 == unfreeze["unfreeze_rows"]
    assert unfreeze["exact_tolerance_k"] == 0.001

    assert lane["criteria"] == {
        "a_catalog": True,
        "b_values": True,
        "c_unfreeze": True,
        "d_honesty": True,
    }


def test_the_liquid_window_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_5_liquid_window_gate")
    source = _json("probes/liquid_window_gate_summary.json")

    assert lane["gate"] == source["gate"]
    gate = lane["gate"]
    assert gate["T_low_C"] == -20.0
    assert gate["T_high_C"] == 60.0
    assert gate["total"] == 314
    assert gate["blocked"] == 77
    assert gate["pass"] == 126
    assert gate["unknown"] == 111
    assert gate["blocked"] + gate["pass"] + gate["unknown"] == gate["total"]
    assert gate["blocked_reason_counts"] == {"mp_above_T_low": 56, "bp_below_T_high": 21}
    assert gate["trigger_rate_blocked_only"] == pytest.approx(0.24522292993630573)
    assert gate["trigger_rate_blocked_only"] == pytest.approx(77 / 314)
    assert gate["trigger_rate_blocked_plus_unknown"] == pytest.approx(0.5987261146496815)
    assert gate["trigger_rate_blocked_plus_unknown"] == pytest.approx(188 / 314)


def test_the_coordination_block_lane_matches_its_own_summary(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _lane(root, "w17_6_coordination_block_merge")
    source = _json("probes/dielectric_coordination_block_v3_summary.json")
    verdict = source["verdict"]

    assert lane["decision"] == verdict["decision"]
    assert lane["passed"] is True
    assert lane["baseline_r2"] == verdict["baseline_r2"] == FROZEN_BASELINE_R2
    assert lane["baseline_abs_delta"] == 0.0
    assert lane["delta_r2"] == verdict["delta_r2"] == 0.0675220440156733
    assert lane["pass_bar"] == 0.02
    assert lane["kill_line"] == 0.005
    assert lane["positive_repeats"] == 9
    assert lane["repeats_total"] == 10
    assert lane["placebo_collapsed"] is True

    arms = lane["arms"]
    assert arms["baseline"] == 0.4091179943351143
    assert arms["plus_lever4"] == 0.4649564468823552
    assert arms["plus_lever8"] == 0.4531768105508106
    assert arms["plus_both"] == 0.4766400383507876
    assert arms["plus_both"] - arms["baseline"] == pytest.approx(lane["delta_r2"])

    merge = lane["merge_readings"]
    assert merge["naive_sum_of_singles"] == 0.0998972687629372
    assert merge["merge_over_naive_sum"] == -0.0323752247472639
    assert merge["delta_vs_best_single"] == 0.011683591468432397
    assert merge["single_arm_deltas"] == {
        "plus_lever4": 0.0558384525472409,
        "plus_lever8": 0.044058816215696295,
    }
    # The merge is measured, never predicted: the singles are not added.
    assert merge["delta_vs_baseline"] < merge["naive_sum_of_singles"]
    assert lane["shots"]["this_shot"] == 1
    assert lane["shots"]["programme_total_after_this_run"] == 4


def test_the_walden_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_7_walden_and_dn")
    source = _json("probes/walden_dn_channel_summary.json")

    recount = lane["joint_table_recount"]
    assert recount["observations"] == source["joint_table_recount"]["observations"] == 8359
    assert recount["distinct_keys"] == 1043
    assert recount["by_dataset_id"] == {
        "epsilon_observations_v11plus": 2065,
        "thermoml_viscosity": 2549,
        "schrodinger_viscosity_v01_open_subset": 3582,
        "pubchem_liquid_window_harvest": 163,
    }
    assert sum(recount["by_dataset_id"].values()) == recount["observations"]
    assert recount["recount_matches_prereg"] is True

    pairs = lane["walden_pairs"]
    assert pairs["rows"] == source["walden_pairs"]["rows"] == 1219
    assert pairs["distinct_keys"] == 76
    assert pairs["averaging_applied"] is False
    assert pairs["by_source_quadrant"] == {
        "epsilon_observations_v11plus x pubchem_liquid_window_harvest": 90,
        "epsilon_observations_v11plus x schrodinger_viscosity_v01_open_subset": 74,
        "epsilon_observations_v11plus x thermoml_viscosity": 1055,
    }

    dn = lane["dn_channel"]
    assert dn["coverage_threshold"] == 0.3
    assert dn["audit_rows"] == 1043
    assert dn["admissible"] == {
        "coverage_fraction": 0.0,
        "covered_keys": 0,
        "passes_threshold": False,
    }
    assert dn["admissible"]["covered_keys"] / dn["audit_rows"] < dn["coverage_threshold"]
    assert dn["gsds_audit"]["donornum_standalone_dataset_entry_count"] == 0
    assert dn["acs_nano_audit"]["donor_number_mentions"] == 21
    assert dn["acs_nano_audit"]["values_read_here"] == 0

    thaw = lane["kinematic_thaw"]
    assert thaw["thermoml_kinematic_rows_excluded"] == 176
    assert thaw["all_kinematic_rows_excluded"] == 214
    assert lane["decision"]["walden_pairs"] == (
        "built; a derived pair table, not a measurement table"
    )
    assert lane["decision"]["dn_channel"] == (
        "channel_does_not_enter_the_feature_table"
    )
    assert lane["decision"]["dn_channel_fails_criterion"] is True
    assert lane["decision"]["model_fitted"] is False
    assert lane["decision"]["r2_reported"] is False


def test_the_walden_lane_records_the_thaw_state_it_read(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_7_walden_and_dn")
    thaw = lane["kinematic_thaw"]

    # The pre-registration defines thawed = data/density_v01.csv is present, and the
    # frozen W17-4 table is on disk, so the sibling-arm dependency is met.
    assert thaw["thaw_dependency"] == "data/density_v01.csv"
    assert thaw["thaw_dependency_present"] is True
    assert thaw["thawed"] is True
    assert "已解冻" in thaw["statement"]
    assert (REPOSITORY_ROOT / "data" / "density_v01.csv").is_file()
    assert lane["decision"]["kinematic_viscosity"] == (
        "family level only in this arm; the density table is on disk so nu can fold to eta"
    )


def test_the_four_channel_board_lane_matches_its_own_summary(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _lane(root, "w17_9_four_channel_board")
    source = _json("probes/four_channel_coverage_summary.json")
    pins = lane["pinned"]

    assert pins == source["pinned"]
    assert lane["board_rows"] == 29
    assert lane["channels"] == source["channels"] == [
        "dielectric",
        "viscosity",
        "homo_lumo",
        "redox",
    ]
    assert lane["main_scoreboard"] == FROZEN_BASELINE_R2
    assert lane["random_row_leak_reference_r2"] == FROZEN_LEAK_REFERENCE_R2

    assert pins["dielectric_main_scoreboard_r2"] == FROZEN_BASELINE_R2
    assert pins["dielectric_scoreboard_rows"] == 457
    assert pins["dielectric_scoreboard_compounds"] == 97
    assert pins["dielectric_scoreboard_pairs"] == 276

    # HOMO/LUMO are the two channels the user named as core data.
    assert pins["homo_lumo_threshold_ev"] == 0.2
    assert pins["homo_mae_ev"] == 0.19050925839013938 < pins["homo_lumo_threshold_ev"]
    assert pins["lumo_mae_ev"] == 0.13855083976437643 < pins["homo_lumo_threshold_ev"]
    assert pins["ip_mae_ev"] == 0.2010970559642009 > pins["homo_lumo_threshold_ev"]
    assert pins["ea_mae_ev"] == 0.23415453202842548 > pins["homo_lumo_threshold_ev"]

    assert pins["viscosity_group_key_r2"] == 0.7481271437772365
    assert pins["viscosity_group_key_mae"] == 0.17477197208762
    # The viscosity MAE gate is 0.15, so this channel stays red and family level only.
    assert pins["viscosity_group_key_mae"] > VISCOSITY_MAE_GATE
    assert pins["redox_oxidation_mae_ev"] == 0.2905180517963865 > pins["redox_threshold_ev"]
    assert pins["redox_reduction_mae_ev"] == 0.4096241620366996 > pins["redox_threshold_ev"]
    assert pins["redox_rx392_rows"] == 392

    assert pins["liquid_window_keys"] == 314
    assert pins["liquid_window_blocked"] == 77
    assert pins["walden_pair_rows"] == 1219
    assert pins["walden_pair_keys"] == 76
    assert pins["dn_covered_keys"] == 0
    assert pins["dn_target_keys"] == 1043


def test_the_pool_caveat_and_the_not_done_list_are_shipped(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = _summary(root)

    assert "0.5332" in summary["pool_definition_caveat"]
    assert "0.5454" in summary["pool_definition_caveat"]
    assert "0.364" in summary["pool_definition_caveat"]
    assert len(summary["not_done_this_week"]) == 3
    joined = " ".join(summary["not_done_this_week"])
    assert "P1" in joined and "P3" in joined
    assert "reaxys_queries_executed" not in joined


def test_the_viscosity_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _lane(root, "w17_3_viscosity_v02")
    source = _json("probes/viscosity_v02_summary.json")

    assert lane["prereg"]["sha256"] == (
        "0934dcf0e48e27dee57baaf667cb8d679f7a4b03ec67e2df53ab25b4a81aa6ed"
    )
    assert lane["prereg"]["status"] == "locked_before_run"

    table = lane["table"]
    assert table["path"] == "data/viscosity_v02.csv"
    assert table["rows"] == source["outputs"]["table"]["rows"] == 42941
    assert table["sha256"] == (
        "907f5368ff6d4d6c15fa26c8c2b57e8bbc8c7ac7a7b3db06ec2c689b283bf3a5"
    )

    slices = lane["catalog_slices"]
    assert slices["viscosity_pa_s"]["size_records"] == 1690
    assert slices["viscosity_pa_s"]["pages_fetched"] == 17
    assert slices["viscosity_pa_s"]["records_collected"] == 1690
    assert slices["viscosity_pa_s"]["unique_dois"] == 1690
    assert slices["kinematic_viscosity"]["size_records"] == 70
    assert slices["kinematic_viscosity"]["pages_fetched"] == 1
    assert slices["viscosity_pa_s"]["failed_pages"] == []
    assert slices["kinematic_viscosity"]["failed_pages"] == []
    # The slice sizes are record counts, never row counts.
    assert sum(item["size_records"] for item in slices.values()) != table["rows"]

    dual = lane["dual_basis_counts"]
    assert dual["online_union_records"] == 1743
    assert dual["raw_named_rows"] == 268247
    assert dual["raw_named_inchikeys"] == 1547
    assert dual["viscosity_v02_rows"] == 42941
    assert dual["viscosity_v02_inchikeys"] == 1228
    assert dual["pa_s_measured_rows"] == 42855
    assert dual["kinematic_converted_rows"] == 86
    assert dual["multi_component_deferred_rows"] == 223605
    assert dual["local_pa_s_rows_reconciled"] == 2549
    assert dual["local_pa_s_rows_matched"] == 2549
    assert (
        dual["pa_s_measured_rows"] + dual["kinematic_converted_rows"]
        == dual["viscosity_v02_rows"]
    )

    unfreeze = lane["unfreeze"]
    assert unfreeze["local_rows"] == 176
    assert unfreeze["exact_rows"] == 176
    assert unfreeze["converted_rows"] == 176
    assert unfreeze["pooled_rows"] == 86
    assert unfreeze["deferred_multi_component_rows"] == 90
    assert unfreeze["pooled_rows"] + unfreeze["deferred_multi_component_rows"] == 176
    assert unfreeze["exact_tolerance_k"] == 0.001

    recon = lane["row_reconciliation"]
    assert recon["local_rows"] == 2549 == recon["matched_local_rows"]
    assert recon["unmatched_local_rows"] == 0
    assert recon["averaging_applied"] is False

    overlap = lane["group_overlap"]
    assert overlap["assertion_passed"] is True
    assert overlap["max_group_overlap"] == 0
    assert overlap["random_row"]["leaked_fraction"] == pytest.approx(0.997904)

    assert lane["criteria"] == {
        "a_online_slice": True,
        "b_local_subset": True,
        "c_unit_honesty": True,
        "d_basis_honesty": True,
    }
    assert lane["run_telemetry"]["models_fitted"] == 0
    assert lane["run_telemetry"]["r2_reported"] == 0


def test_the_viscosity_raw_layer_is_declared_but_not_shipped(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    layer = _lane(root, "w17_3_viscosity_v02")["value_layer"]

    assert layer["path"] == "data/processed/viscosity_v02_raw.csv"
    assert layer["rows"] == 268247
    assert layer["sha256"] == (
        "848153226153487bf1c6c09e3310867ea22916cd373e19139a882fa118fac901"
    )
    assert layer["shipped_in_this_bundle"] is False
    assert not (root / WEEK / "data" / "processed" / "viscosity_v02_raw.csv").exists()


def test_the_restricted_contract_withholds_every_reaxys_list(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    contract = _summary(root)["restricted_contract"]

    assert contract["values_enter_data"] is False
    assert contract["values_enter_any_pool"] is False
    assert contract["values_ship_in_this_bundle"] is False
    assert contract["row_labels"] == [
        "reaxys_crosscheck_only",
        "restricted_crosscheck_only",
    ]
    assert "28.2" in contract["decision"]

    shipped = {destination for _, destination in ARTIFACTS}
    excluded = contract["repo_internal_only"]
    assert len(excluded) == len(RESTRICTED_EXCLUDED) == 15
    for entry in excluded:
        assert (REPOSITORY_ROOT / entry["path"]).is_file(), entry["path"]
        assert len(entry["sha256"]) == 64, entry["path"]
        assert entry["path"] not in shipped, entry["path"]
    by_value = {entry["path"]: entry["carries_reaxys_values"] for entry in excluded}
    assert by_value["probes/reaxys_core_four_crosscheck.csv"] is True
    assert by_value["probes/reaxys_thin_family_backfill_queue.csv"] is False
    # Nothing the repository keeps as a Reaxys list may reach the shipped set.
    assert "probes/reaxys_core_four_crosscheck.csv" not in shipped
    assert "probes/reaxys_thin_family_backfill_queue.csv" not in shipped


def test_the_reaxys_crosscheck_lane_carries_no_reaxys_value(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _lane(root, "w17_rx_reaxys_core_four_crosscheck")

    assert lane["session"]["queries_executed"] == 9
    assert lane["session"]["batch_crawling"] is False
    assert lane["observation_rows"] == 80
    assert lane["compliance"]["values_written_under_data"] is False
    assert lane["compliance"]["values_entered_any_pool"] is False
    assert lane["substances_queried"] == [
        "ethylene carbonate",
        "propylene carbonate",
        "gamma-valerolactone",
        "succinonitrile",
        "dimethyl carbonate",
    ]

    verdicts = {item["channel"]: item for item in lane["channel_verdicts"]}
    assert verdicts["dielectric_epsilon"]["verdict"] == "usable_numeric"
    assert verdicts["dielectric_epsilon"]["rows_observed"] == 31
    assert verdicts["dielectric_epsilon"]["numeric_rows"] == 24
    assert verdicts["viscosity_eta"]["verdict"] == "usable_numeric"
    assert verdicts["viscosity_eta"]["rows_observed"] == 32
    assert verdicts["viscosity_eta"]["numeric_rows"] == 25
    # The two channels the user named as core data are reference-only in Reaxys.
    assert verdicts["homo_lumo"]["verdict"] == "reference_only"
    assert verdicts["homo_lumo"]["numeric_rows"] == 0
    assert verdicts["redox_potential"]["verdict"] == "reference_only"
    assert verdicts["redox_potential"]["numeric_rows"] == 0

    assert lane["queue_key_audit_summary"] == {
        "audited": 14,
        "matched": 14,
        "mismatched": 0,
    }
    assert lane["lesson_findings"] == {
        "A_gvl_inchikey": "not_reproduced",
        "B_ec_temperature_label": "reproduced",
        "C_ec_8978_as_melting_point": "not_reproduced",
    }

    # The lane must not smuggle a Reaxys number in, whatever else it mirrors.
    payload = json.dumps(lane, ensure_ascii=False)
    for leaked in ("36.9", "89.78", "90.5", "0.0251", "100.117"):
        assert leaked not in payload, leaked


def test_the_independent_recheck_reproduced_the_crosscheck(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    recheck = _lane(root, "w17_rx_reaxys_core_four_crosscheck")["independent_recheck"]

    assert len(recheck["facts"]) == len(INDEPENDENT_RECHECK_FACTS) == 4
    facts = " ".join(item["observed"] for item in recheck["facts"])
    assert "0 Substances and 0 Documents" in facts
    assert "4 Substances" in facts
    assert "CAS 108-29-2" in facts
    assert "CAS 616-38-6" in facts
    assert "no numeric HOMO, LUMO or gap column exists" in facts


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


def test_the_readme_ships_the_boundaries_the_summary_claims(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    text = (root / WEEK / "README.md").read_text(encoding="utf-8")

    for needle in (
        "data/density_v01.csv",
        "data/dielectric_v04.csv",
        "6/6 INTACT",
        "随机行",
        "group_key",
        "HOMO",
        "LUMO",
        "DN",
    ):
        assert needle in text, needle
