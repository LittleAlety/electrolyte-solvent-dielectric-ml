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
    MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
    MAIN_SCOREBOARD_HEADLINE_R2,
    MAIN_SCOREBOARD_VERSION,
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
FROZEN_PROMOTED_HEADLINE_R2 = 0.4766400383507876
FROZEN_PROMOTED_HEADLINE_DELTA_R2 = 0.0675220440156733
FROZEN_LEAK_REFERENCE_R2 = 0.7385332681453336
DIELECTRIC_V04_SHA256 = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"
DENSITY_V01_SHA256 = "47f920f773054ccd8789ac5679e3da5ca8ec732f8f6e79ba1f824cf68b2556ff"
WALDEN_PAIRS_SHA256 = "df2a0fe93b9d2f88009c4ded96b29378a10e0f4de5eca10ad84c41cea10c8cc3"
VISCOSITY_MAE_GATE = 0.15
DN_AUDIT_SHA256 = "3a80daa9f74c423bfcd6d2cbd3f6c54a6ffe2516daab0c3147e33d92adf7dab6"

# A mutant that rewrites one narrative number must move this line as well.
README_SHA256 = "ad33d867d32cdaf6294816069095f241a0b7ca6c2be437b90cac850364cbf986"
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
    # W17-26 -- the seed-robustness lane of the single-representation 0.6081.
    "0.6080587938801277",
    "+0.044489",
    "+0.015919",
    "0.000550",
    "0.586114",
    "0.565349–0.608059",
    "0.523136",
    "0.486277",
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
    # W17-16 .. W17-19 -- the late arms.
    "98/70/53",
    "144/130/90",
    "70/30/30",
    "27/0/0",
    "35,579/35,579",
    "15,388 B",
    "1×10⁻⁴ eV",
    "5,117",
    "4,668",
    "0.8549",
    "0.3036",
    "0.6141",
    "0.4343",
    # W17-21 .. W17-25 -- the dielectric pool-expansion shots 12-15, the audit
    # and the delivery-consistency close-out.
    "0.3809089252433510",
    "0.530028742596643",
    "0.49147018524319047",
    "0.5433111678100043",
    "0.48600023850174934",
    "0.4035089033119271",
    "0.510231505819011",
    "0.323041",
    "0.515154",
    "96 行 / 31 化合物",
    "246 → 493",
    "112 → 120",
    "133 → 141",
    "276 个 (化合物, T) 对",
    "457 行 / 97 化合物",
    "w17_pool_expansion_{arms,dose,ceiling}.png",
    # W17-22/W17-23 -- the Reaxys static-epsilon harvest and the red-line register.
    "读数作废",
    "§28.33",
    # W17-27 -- the shot-17 model-head sweep (refuted) and its inner-CV finding.
    "0.041024",
    "0.567035",
    "0.121422",
    # W18-F -- the AUC sidecar, the splitter table and the ordering-vs-magnitude story.
    "0.9579",
    "0.7011",
    "0.9337",
    "0.1602",
    "0.0860",
    "0.8412",
    "0.7358",
    "1594",
    "125.8 s",
    # W17-28 -- the open-licence epsilon frontier re-check.
    "153 + 4 = 157",
    "785 张 PNG",
    "58 个 raw 键",
    "403",
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
    assert MAIN_SCOREBOARD_VERSION == "v2"
    assert MAIN_SCOREBOARD_HEADLINE_R2 == FROZEN_PROMOTED_HEADLINE_R2
    assert MAIN_SCOREBOARD_HEADLINE_DELTA_R2 == FROZEN_PROMOTED_HEADLINE_DELTA_R2
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
    assert scoreboard["version"] == MAIN_SCOREBOARD_VERSION == "v2"
    assert scoreboard["value"] == FROZEN_BASELINE_R2
    assert scoreboard["baseline"]["value"] == FROZEN_BASELINE_R2
    assert scoreboard["baseline"]["status"] == "retained_unchanged"
    assert scoreboard["headline"]["value"] == FROZEN_PROMOTED_HEADLINE_R2
    assert scoreboard["headline"]["delta_vs_baseline"] == FROZEN_PROMOTED_HEADLINE_DELTA_R2
    assert scoreboard["promoted_r2"] == FROZEN_PROMOTED_HEADLINE_R2
    assert scoreboard["headline_minus_baseline_r2"] == FROZEN_PROMOTED_HEADLINE_DELTA_R2
    assert scoreboard["headline"]["value"] - scoreboard["baseline"]["value"] == pytest.approx(
        scoreboard["headline"]["delta_vs_baseline"]
    )
    assert "pass_merged_blocks" in scoreboard["headline"]["promotion_basis"]
    assert len(scoreboard["caveats"]) == 3
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


def test_the_pool_expansion_lane_is_frozen_and_not_promoted(
    exported: tuple[Path, dict],
) -> None:
    """The five-shot 0.60 chase, read off the lane rather than the prose.

    The scoring pool never moves across the shots, no shot reaches the target, and
    the best reading is not a co-primary, so it may not be promoted.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W17-21_dielectric_pool_expansion"]

    frozen_pool = lane["scoring_pool_frozen"]
    assert frozen_pool["rows_scored"] == 457
    assert frozen_pool["compounds_scored"] == 97
    assert frozen_pool["compound_temperature_pairs"] == 276
    assert frozen_pool["folds"] == 50
    assert frozen_pool["frozen_baseline_r2"] == FROZEN_BASELINE_R2
    assert frozen_pool["baseline_reproduced_in_every_shot"] is True

    assert lane["target_r2"] == 0.6
    assert lane["target_met"] is False
    assert lane["promoted_headline_unchanged_r2"] == FROZEN_PROMOTED_HEADLINE_R2

    best = lane["best_reading"]
    assert best["r2"] == 0.5433111678100043
    assert best["promotable"] is False
    assert "not a co-primary" in best["why_not"]

    shots = lane["shots"]
    shot12 = shots["shot_12_foreign_space"]
    assert shot12["primary_r2"] == 0.38090892524335096
    assert shot12["decision"] == "primary_missed"
    assert shot12["arm_a_pass"] is True
    assert shot12["arm_b_pass"] is False

    shot13 = shots["shot_13_same_source_full_table"]
    assert shot13["decision"] == "co_primaries_missed"
    assert shot13["co_primary_values"] == {
        "full_table_hybrid": 0.530028742596643,
        "full_table_lever4_lever8": 0.49147018524319047,
    }
    assert "not a blind confirmation" in shot13["not_blind"]

    shot14 = shots["shot_14_block_full_plus_reaxys_widening"]
    assert shot14["decision"] == "co_primaries_missed"
    assert shot14["co_primary_values"] == {
        "full_table_lever4_lever8full": 0.48600023850174934,
        "static_lever4_lever8full": 0.4035089033119271,
    }
    assert shot14["anchors_reproduced"] is True

    shot15 = shots["shot_15_high_epsilon_anchors"]
    assert shot15["decision"] == "primary_missed"
    assert shot15["co_primary_values"] == {"anchors_lever4": 0.510231505819011}

    counts = lane["open_access_sources"]["counts"]
    assert counts["usable_sources"] == 22
    assert counts["usable_rows"] == 96
    assert counts["usable_compounds"] == 31
    assert counts["reference_only_rows"] == 10

def test_the_seed_robustness_lane_never_promotes_the_6081(
    exported: tuple[Path, dict],
) -> None:
    """The one reading above 0.60 is explained, bounded, and never promoted.

    The lane has to ship the counterexample next to the finding: the ordering it
    confirms on the lever4 arm reverses on the hybrid arm, and the cross-seed mean
    of the single-representation reading stays below the 0.60 target.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W17-26_representation_seed_robustness"]

    assert lane["frozen_side_unchanged"] is True
    assert lane["frozen_baseline_r2"] == FROZEN_BASELINE_R2
    assert lane["frozen_headline_unchanged_r2"] == FROZEN_PROMOTED_HEADLINE_R2
    assert lane["seeds"] == [42, 1234, 2026, 31337, 7]
    assert lane["seed_42_anchors_reproduced"] is True
    assert lane["leakage_clean"] is True
    assert lane["seed_42_single_representation_r2"] == 0.6080587938801277
    assert lane["prereg"]["status"] == "locked_before_run"

    hypothesis = lane["hypothesis"]
    assert hypothesis["arm"] == "full_table_lever4"
    assert hypothesis["verdict"] == "confirmed_out_of_seed"
    assert hypothesis["positive_seeds"] == 5
    assert hypothesis["total_seeds"] == 5
    assert hypothesis["delta_min"] > 0.0

    means = lane["cross_seed_means"]
    assert means["full_table_lever4/Physical"] == pytest.approx(0.586114, abs=1e-6)
    assert means["full_table_lever4/Morgan+Physical"] == pytest.approx(0.541625, abs=1e-6)
    assert means["full_table_lever4/Physical"] < 0.60
    # the counterexample ships with the finding, not instead of it
    assert means["full_table_hybrid/Morgan+Physical"] > means["full_table_hybrid/Physical"]
    assert "Morgan+Physical 0.523136" in lane["counterexample"]

    assert lane["target_r2"] == 0.6
    assert lane["target_met"] is False
    assert lane["reading_never_promoted"] is True
    assert lane["non_blind"] is True
    assert lane["promotable"] is False


def test_the_head_sweep_lane_refutes_every_swap(exported: tuple[Path, dict]) -> None:
    """Shot 17 swaps the model head at the frozen pool and no head wins.

    The lane has to ship the anchor, the refutation of every alternative head and
    the inner-CV finding that makes a W18 grid pre-registered rather than selected.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W17-27_model_head_sweep"]

    assert lane["verdict"] == "refuted"
    assert lane["target_met"] is False
    assert lane["promotable"] is False
    assert lane["non_blind"] is True
    assert lane["prereg"]["status"] == "locked_before_run"

    anchors = lane["anchors"]
    assert anchors["reproduced"] is True
    assert anchors["rows"][0]["measured"] == 0.6080587938801277
    assert anchors["rows"][0]["abs_gap"] == 0.0

    assert lane["leakage_clean"] is True
    assert lane["leakage_folds"] == {"42": 350}

    heads = lane["head_r2"]
    assert lane["reference_head"] == "xgb_reference"
    assert lane["reference_r2"] == 0.6080587938801277
    assert heads["xgb_reference"] == 0.6080587938801277
    assert lane["best_head"] == "blend_uniform"
    assert lane["best_r2"] == pytest.approx(0.567034657421033)
    assert lane["best_improvement"] == pytest.approx(-0.04102413645909475)
    assert heads["xgb_deep"] == pytest.approx(0.5521211165030482)
    assert heads["extra_trees"] == pytest.approx(0.5162359988716283)
    assert heads["kernel_ridge"] == pytest.approx(0.4580443557748957)
    assert heads["mlp"] == pytest.approx(0.12142151511869281)
    # no swapped head reaches the frozen reference, let alone the target
    rivals = {name: r2 for name, r2 in heads.items() if name != lane["reference_head"]}
    assert max(rivals.values()) < lane["reference_r2"] < 0.70
    assert lane["best_head"] != lane["reference_head"]
    assert lane["best_improvement"] < 0.0

    assert lane["inner_cv_choices"] == {
        "42": {
            "mlp": 10,
            "kernel_ridge": 25,
            "xgb_reference": 3,
            "xgb_deep": 8,
            "extra_trees": 4,
        }
    }
    assert "frozen head only 3" in lane["inner_cv_finding"]


def test_the_auc_sidecar_lane_adds_ordering_without_moving_magnitude(
    exported: tuple[Path, dict],
) -> None:
    """The AUC columns are restored from shipped rows and no frozen byte moves.

    The sidecar reads the shipped prediction rows, so its R2 must match the shipped
    repeats bit-for-bit and the shipped metric name list must stay untouched.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W18-F1_auc_sidecar"]

    assert lane["promotable"] is False
    assert lane["worst_r2_abs_gap"] == 0
    assert lane["r2_tolerance"] == 1e-9
    assert "auc_gt15" not in lane["metric_names_shipped"]
    assert "auc_gt30" not in lane["metric_names_shipped"]
    assert lane["metric_names_extended"][-2:] == ["auc_gt15", "auc_gt30"]
    assert lane["metric_names_extended"][:7] == lane["metric_names_shipped"]

    sources = lane["sources"]
    assert len(sources) == 5
    assert all(block["max_r2_abs_gap"] == 0 for block in sources.values())
    assert sources["dielectric_coordination_block_v3"]["scored_groups"] == 230
    assert sources["dielectric_coordination_block_v3"]["auc_gt30_mean"] == pytest.approx(
        0.7010835698619533
    )
    assert sources["dielectric_coverage_paired_benchmark"]["scored_groups"] == 180
    assert sources["dielectric_band_ablation"]["scored_groups"] == 150
    assert lane["table"] == "probes/artifacts/dielectric_auc_sidecar.csv"


def test_the_splitter_lane_keeps_ordering_while_magnitude_collapses(
    exported: tuple[Path, dict],
) -> None:
    """R2 collapses under compound and scaffold holdout while AUC>30 largely holds.

    The lane has to ship the leak reference as a leak reference, keep the pool
    caveat, and never promote the leak reference row as a result.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W18-F2_splitters_auc"]

    assert lane["promotable"] is False
    assert lane["random_row_is_a_leak_reference"] is True
    assert lane["reused_max_r2_abs_gap"] == 0

    pool = lane["pool"]
    assert pool["rows"] == 1594
    assert pool["compounds"] == 98
    assert pool["scaffold_groups"] == 50
    assert pool["leak"]["folds_with_a_straddling_compound"] == 0
    assert "NOT the 457-row / 97-compound" in lane["pool_caveat"]

    by_protocol = lane["by_protocol"]
    assert lane["protocol_order"] == [
        "random_row",
        "grouped",
        "scaffold",
        "grouped_single_row",
    ]

    leak = by_protocol["random_row"]["Morgan+Physical"]
    honest = by_protocol["grouped"]["Morgan+Physical"]
    scaffold = by_protocol["scaffold"]["Morgan+Physical"]

    assert leak["r2"] == pytest.approx(0.9336667897786656)
    assert honest["r2"] == pytest.approx(0.1601650045731296, abs=1e-9)
    assert scaffold["r2"] == pytest.approx(-0.08604221437905275, abs=1e-9)

    # the ordering metric survives compound and scaffold holdout far better
    assert leak["auc_gt30"] == pytest.approx(0.993801699471083)
    assert honest["auc_gt30"] == pytest.approx(0.841177924217463, abs=1e-9)
    assert scaffold["auc_gt30"] == pytest.approx(0.735817111766236, abs=1e-9)
    assert leak["r2"] > honest["r2"] > scaffold["r2"]
    assert leak["auc_gt30"] > honest["auc_gt30"] > scaffold["auc_gt30"]
    assert honest["auc_gt30"] - scaffold["auc_gt30"] < honest["r2"] - scaffold["r2"] + 1.0


def test_the_source_recheck_lane_registers_a_re_check_not_a_crawl(
    exported: tuple[Path, dict],
) -> None:
    """The open-licence re-check adds no source and records its accounting gap.

    It must state that it did not run a new crawl, that the frontier is not
    overturned, and that the raw keys outside the roster were not re-judged.
    """

    root, _ = exported
    summary = _summary(root)
    lane = summary["late_arms"]["W17-28_open_licence_source_recheck"]

    assert lane["new_sources"] == 0
    assert lane["net_new_compounds"] == 0
    assert lane["net_new_rows"] == 0
    assert lane["roster_size"] == 153
    assert lane["upper_bound_compounds"] == 157
    assert lane["widest_bound_compounds"] == 161
    assert lane["frontier_exhausted_not_overturned"] is True
    assert lane["raw_keys_outside_the_roster"] == 58
    assert "already went through an admission ruling" in lane["raw_keys_note"]
    assert lane["models_fitted"] == 0
    assert lane["promotable"] is False
    assert lane["candidates"] == "probes/dielectric_source_sweep_v2_sources.csv"
    assert lane["blocking_reasons"]["figshare_api"].startswith("HTTP 403")
    assert "not a new crawl" in lane["nature"]


def test_the_coordination_block_lane_matches_its_own_summary(    exported: tuple[Path, dict],
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
    assert lane["board_rows"] == 30
    assert lane["channels"] == source["channels"] == [
        "dielectric",
        "viscosity",
        "homo_lumo",
        "redox",
    ]
    assert lane["main_scoreboard"] == FROZEN_BASELINE_R2
    assert lane["main_scoreboard_version"] == MAIN_SCOREBOARD_VERSION
    assert lane["main_scoreboard_headline"] == FROZEN_PROMOTED_HEADLINE_R2
    assert lane["main_scoreboard_headline_delta_r2"] == FROZEN_PROMOTED_HEADLINE_DELTA_R2
    assert lane["random_row_leak_reference_r2"] == FROZEN_LEAK_REFERENCE_R2

    assert pins["dielectric_main_scoreboard_r2"] == FROZEN_BASELINE_R2
    assert pins["dielectric_main_scoreboard_headline_r2"] == FROZEN_PROMOTED_HEADLINE_R2
    assert pins["dielectric_main_scoreboard_headline_delta_r2"] == FROZEN_PROMOTED_HEADLINE_DELTA_R2
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
    assert len(excluded) == len(RESTRICTED_EXCLUDED) == 25
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
