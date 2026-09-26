"""Delivery-package regression tests for the Week 15 export."""

from __future__ import annotations

import csv
import json
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week15_results import (
    ARTIFACTS,
    BASELINE_R2,
    FROZEN_DIGEST,
    OBSERVATIONS_SHA256,
    ORDER_LABEL_ERRATUM_NOTE,
    PILOT_POOL_SHA256,
    PREREG_V1_SHA256,
    R2_LEVERS_PREREG_SHA256,
    README_TEXT,
    VERIFIERS,
    VISCOSITY_V01_SHA256,
    WEEK,
    _parse_args,
    distinct_local_trace_files,
    export_results,
    kpi_block_sizes,
    kpi_fidelity_counts,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

RED_LINE_EXPECTATIONS = (
    ("data/dielectric_v03.csv", FROZEN_DIGEST),
    ("probes/l3_stage1_pilot_pool.csv", PILOT_POOL_SHA256),
    ("probes/l3_backvalidation_prereg.json", PREREG_V1_SHA256),
    ("data/processed/dielectric_observations_v11plus.csv", OBSERVATIONS_SHA256),
    ("probes/dielectric_r2_levers_prereg.json", R2_LEVERS_PREREG_SHA256),
    ("data/viscosity_v01.csv", VISCOSITY_V01_SHA256),
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week15")
    return root, export_results(output_root=root, overwrite=False)


def _summary(root: Path) -> dict:
    return json.loads((root / WEEK / "week15_summary.json").read_text(encoding="utf-8"))


def _json(relative: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def test_every_declared_artifact_exists_in_the_repository() -> None:
    missing = [s for s, _ in ARTIFACTS if not (REPOSITORY_ROOT / s).is_file()]
    assert missing == []


def test_export_ships_every_artifact_readme_manifest_and_verification(
    exported: tuple[Path, dict],
) -> None:
    root, result = exported
    week_root = root / WEEK

    assert result["verification_passed"] is True
    for _, destination in ARTIFACTS:
        assert (week_root / destination).is_file(), destination
    for name in ("README.md", "week15_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file(), name
    assert verify_export_manifest(week_root) == []


def test_the_summary_records_the_artifact_list_it_shipped(
    exported: tuple[Path, dict],
) -> None:
    _, result = exported
    assert result["artifacts"] == [destination for _, destination in ARTIFACTS]


def test_the_shipped_readme_is_the_module_constant(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    assert (root / WEEK / "README.md").read_text(encoding="utf-8") == README_TEXT
    assert _summary(root)["week"] == WEEK == "week15"


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / WEEK).mkdir()
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)


def test_the_overwrite_flag_is_wired_through_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_week15_results.py", "--overwrite"])
    assert _parse_args().overwrite is True
    monkeypatch.setattr(sys, "argv", ["export_week15_results.py"])
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


def test_summary_pins_every_frozen_red_line(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    red_lines = _summary(root)["frozen_red_lines"]

    assert set(red_lines) == {name for name, _ in RED_LINE_EXPECTATIONS}
    for name, expected in RED_LINE_EXPECTATIONS:
        entry = red_lines[name]
        assert entry["sha256"] == expected, name
        assert entry["expected_sha256"] == expected, name
        assert entry["intact"] is True, name


def test_summary_records_the_scoreboard_and_the_276_pair_caveat(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    scoreboard = _summary(root)["main_scoreboard"]

    assert scoreboard["rows_scored"] == 457
    assert scoreboard["compounds_scored"] == 97
    assert scoreboard["distinct_compound_temperature_pairs"] == 276
    assert scoreboard["distinct_compound_temperature_pairs"] < scoreboard["rows_scored"]
    assert scoreboard["baseline_r2"] == BASELINE_R2
    note = scoreboard["note"]
    assert "276" in note
    assert "never 457" in note


def test_the_scoreboard_is_touched_once_and_buys_no_r2(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = _summary(root)

    shots = summary["shots"]
    assert shots["main_scoreboard_attempts"] == 0
    assert shots["calibration_reproductions"] == 1
    assert "buys no R2" in shots["calibration_reproduction_is_not_a_gain_attempt"]
    assert summary["buys_no_new_r2"].strip()
    assert "buys no R2" in summary["buys_no_new_r2"]


def test_the_ranked_hybrid_is_the_hybrid_the_scoreboard_scores(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    reproduction = _summary(root)["baseline_reproduction"]
    t5 = _json("probes/dielectric_hybrid_shap_summary.json")

    assert reproduction["reference_r2"] == BASELINE_R2 == 0.4091179943351143
    assert reproduction["bit_exact"] is True
    assert reproduction["abs_difference"] == 0.0
    assert reproduction["reproduced_r2"] == reproduction["reference_r2"]
    assert reproduction["folds_compared"] == (
        t5["fold_fit_matches_the_frozen_function"]["folds_compared"]
    )
    assert t5["fold_fit_matches_the_frozen_function"]["identical"] is True
    assert t5["baseline_reproduces"]["verified"] is True


def test_the_thermoml_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    """T1's readout is re-read from the probe summary, never restated."""

    root, _ = exported
    lane = _summary(root)["lanes"]["t1_thermoml_viscosity_reparse"]
    t1 = _json("probes/thermoml_viscosity_coverage_summary.json")

    assert lane["probe"] == "probes/thermoml_viscosity_coverage_probe.py"
    assert lane["xml_files_scanned"] == t1["xml_files_scanned"]
    assert lane["viscosity_files"] == t1["viscosity_files"]
    assert lane["viscosity_rows"] == t1["viscosity_rows"]
    assert lane["viscosity_rows_pa_s"] == t1["viscosity_rows_pa_s"]
    assert lane["viscosity_rows_kinematic"] == t1["viscosity_rows_kinematic"]
    assert lane["pure_rows"] == t1["pure_rows"]
    assert lane["mixture_rows"] == t1["mixture_rows"]
    assert lane["pure_keys"] == t1["pure_keys"]
    assert lane["new_keys_vs_epsilon_and_stored_viscosity"] == t1["new_vs_eps_and_v01"]
    assert lane["distinct_source_dois"] == t1["source_doi"]["distinct_dois"]
    assert lane["rows_without_doi"] == t1["source_doi"]["rows_without_doi"]
    assert lane["acceptance_values_reconciled"] == len(t1["expectation_vs_remeasured"])
    assert lane["expectation_mismatches"] == t1["expectation_mismatches"] == []

    # The viscosity totals are three views of one corpus and have to close.
    assert lane["viscosity_rows"] == lane["pure_rows"] + lane["mixture_rows"]
    assert lane["viscosity_rows"] == (
        lane["viscosity_rows_pa_s"] + lane["viscosity_rows_kinematic"]
    )
    assert t1["pure_plus_mixture"] == lane["viscosity_rows"]

    # The hypothesis T1 set out to test: the stored ThermoML extractions built
    # out of this same corpus harvested no viscosity row at all.
    gap = t1["extraction_gap"]
    assert lane["stored_thermoml_extraction_viscosity_rows"] == (
        gap["viscosity_rows_in_stored_thermoml_extractions"]
    )
    assert lane["stored_thermoml_extraction_viscosity_rows"] == 0
    assert gap["viscosity_rows_in_local_xml"] == lane["viscosity_rows"]
    assert "NIST" in lane["boundary"] and "upper bound" in lane["boundary"]


def test_the_schrodinger_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _summary(root)["lanes"]["t2_schrodinger_si_reconciliation"]
    t2 = _json("probes/schrodinger_si_reconciliation_summary.json")

    assert lane["probe"] == "probes/schrodinger_si_reconciliation.py"
    assert lane["stored_rows"] == t2["stored_table"]["rows"]
    assert lane["row_aligned_matches"] == t2["row_aligned_matches"]
    assert lane["mismatches"] == t2["mismatches"]
    assert lane["multiset_matches"] == t2["row_multiset_comparison"]["multiset_matches"]
    assert lane["unique_keys"] == t2["unique_keys"]
    assert lane["source_doi"] == t2["source_doi_set"][0]
    assert lane["claimed_total_points"] == t2["open_subset"]["claimed_total_points"]
    assert lane["withheld_points"] == t2["open_subset"]["withheld_points"]
    assert lane["supp_3_rows"] == t2["supp_3"]["rows"]
    assert lane["supp_3_rows_merged_into_experimental_table"] == (
        t2["supp_3"]["rows_merged_into_experimental_table"]
    )

    # Row-aligned identity is the whole claim; the withheld remainder is the
    # arithmetic gap between the paper's stated total and the open subset.
    assert lane["row_aligned_matches"] == lane["stored_rows"]
    assert lane["mismatches"] == 0
    assert lane["multiset_matches"] is True
    assert lane["claimed_total_points"] - lane["withheld_points"] == lane["stored_rows"]
    assert lane["supp_3_rows_merged_into_experimental_table"] == 0
    assert t2["supp_3"]["data_status"] == "predicted"
    assert t2["source_doi_set_matches_expected"] is True
    assert "858" in lane["boundary"]


def test_the_pubchem_identity_lane_matches_its_own_summary(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _summary(root)["lanes"]["t3_pubchem_identity_layer"]
    t3 = _json("probes/pubchem_identity_layer_summary.json")

    assert lane["probe"] == "probes/pubchem_identity_layer.py"
    assert lane["coverage_set"] == t3["coverage_set"]
    assert lane["roster_keys"] == t3["roster_keys"]
    assert lane["roster_resolved_with_cid"] == t3["roster_resolved_with_cid"]
    assert lane["resolved_with_cid"] == t3["resolved_with_cid"]
    assert lane["unresolved"] == t3["unresolved_count"]
    assert lane["identity_check_counts"] == t3["identity_check_counts"]
    assert lane["network_calls_at_export"] == t3["network_calls"]
    assert lane["cache_hits"] == t3["cache_hits"]
    assert lane["cache_entries"] == t3["cache_entries_for_coverage_set"]
    assert lane["cid_conflicts"] == t3["cid_conflicts"]

    # Every key of the coverage set closes, and the roster closes inside it.
    assert lane["resolved_with_cid"] == lane["coverage_set"]
    assert lane["roster_resolved_with_cid"] == lane["roster_keys"]
    assert lane["roster_keys"] < lane["coverage_set"]
    assert lane["unresolved"] == 0
    assert lane["identity_check_counts"] == {"roundtrip_match": lane["coverage_set"]}
    assert lane["cache_entries"] == lane["cache_hits"] // 2

    kinds = Counter(entry["difference_kind"] for entry in t3["smiles_differing_keys"])
    assert lane["smiles_differing_keys_by_kind"] == dict(sorted(kinds.items()))
    assert sum(kinds.values()) == len(t3["smiles_differing_keys"])
    assert "drawing differences" in lane["boundary"]


def test_the_kpi_lane_matches_its_report_and_its_module(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _summary(root)["lanes"]["t4_kpi_64_feature_module"]

    assert lane["module"] == "src/electrolyte_ml/kpi_descriptors.py"
    assert lane["columns"] == 64
    assert lane["block_sizes"] == kpi_block_sizes()
    assert sum(lane["block_sizes"].values()) == lane["columns"]

    # The fidelity ledger is parsed back off the shipped report, so the summary
    # cannot advertise a tier the prose no longer states.
    assert lane["fidelity_counts"] == kpi_fidelity_counts(
        REPOSITORY_ROOT / "reports" / "kpi_64_feature_module.md"
    )
    assert sum(lane["fidelity_counts"].values()) == lane["columns"]

    with (REPOSITORY_ROOT / "data" / "dielectric_v03.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        roster = len(list(csv.DictReader(handle)))
    assert lane["roster"]["roster_smiles"] == roster
    assert lane["roster"]["descriptor_cells"] == roster * lane["columns"]
    assert lane["roster"]["non_finite_cells"] == 0
    assert "0.0" in lane["charge_fallback"]


def test_the_hybrid_shap_lane_matches_its_own_summary(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lane = _summary(root)["lanes"]["t5_hybrid_shap"]
    t5 = _json("probes/dielectric_hybrid_shap_summary.json")

    assert lane["probe"] == "probes/dielectric_hybrid_shap.py"
    assert lane["feature_columns"] == t5["feature_count"]
    assert lane["knowledge_feature_columns"] == t5["knowledge_feature_count"]
    assert lane["folds"] == t5["repeats_x_folds"]
    assert lane["repeats"] == t5["repeats"]
    assert lane["importance_implementation"] == t5["importance_impl"]
    assert lane["test_rows_visible_to_ranking"] == t5["test_rows_visible_to_ranking"]
    assert lane["additivity_verified"] == t5["shap_additivity"]["verified"]
    assert lane["max_relative_residual_hybrid_arm"] == (
        t5["shap_additivity"]["max_relative_residual_hybrid_arm"]
    )
    assert lane["max_relative_residual_knowledge_arm"] == (
        t5["shap_additivity"]["max_relative_residual_knowledge_arm"]
    )
    assert lane["additivity_tolerance"] == t5["shap_additivity"]["tolerance"]
    assert lane["clipped_test_predictions"] == t5["clipped_test_predictions"]
    assert lane["boundaries"] == t5["honest_boundaries"]

    hybrid_top = (t5["top10_features"] or [{}])[0]
    assert lane["top_feature_hybrid"] == {
        key: hybrid_top[key]
        for key in ("feature", "mean_importance", "mean_rank", "top_3_folds")
    }
    knowledge_top = (t5["knowledge_top10"] or [{}])[0]
    assert lane["top_feature_knowledge"] == {
        key: knowledge_top[key]
        for key in ("feature", "mean_importance", "mean_rank", "top_3_folds")
    }

    stability = t5["rank_stability"]["hybrid"]
    assert lane["rank_stability"] == {
        "stable_features": stability["stable_features"],
        "unstable_features": stability["unstable_features"],
        "features_never_used_by_any_tree": stability["features_never_used_by_any_tree"],
        "rule": stability["rule"],
    }
    assert lane["rank_stability"]["stable_features"] + (
        lane["rank_stability"]["unstable_features"]
    ) == lane["feature_columns"]

    # The ranking may only look at training folds, and it has to do so every fold.
    leak = t5["leak_guard"]
    assert lane["leak_guard_folds_checked"] == leak["folds_checked"]
    assert lane["leak_guard_folds_checked"] >= lane["folds"]
    assert lane["test_rows_visible_to_ranking"] == 0
    assert leak["test_rows_visible_to_ranking"] == 0
    assert leak["max_test_rows_visible_to_ranking"] == 0


def test_the_ab6_cross_reading_matches_the_source_summary(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    lane = _summary(root)["lanes"]["t5_hybrid_shap"]
    t5 = _json("probes/dielectric_hybrid_shap_summary.json")

    comparison = lane["comparison_to_ab6"]
    source = t5["comparison_to_ab6"]

    assert comparison["verdict"] == source["verdict"]
    assert comparison["verdict"] == t5["verdict"]["ab6_agreement_vs_quoted_lever9"]
    assert comparison["verdict"] == "inconsistent"
    assert comparison["verdict_rule"] == source["verdict_rule"]
    for key in (
        "shap_vs_quoted_lever9",
        "shap_vs_corrected_permutation",
        "quoted_lever9_vs_corrected_permutation",
    ):
        assert comparison[key] == source["readings"][key], key
    assert comparison["top_three_status"] == source["top_three_status"]
    assert comparison["counts_rank_last_holds"] == source["counts_rank_last"]["holds"]

    # The two arms are different importance implementations, so the readout may
    # only report that they disagree; a consistent verdict would contradict the
    # match rates it is derived from.
    assert comparison["shap_vs_quoted_lever9"]["exact_match_rate"] < 0.2
    assert comparison["shap_vs_corrected_permutation"]["exact_match_rate"] >= 0.2


def test_al_round_4_recompute_matches_its_generator_and_its_list(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    recompute = _summary(root)["al_round_4_recompute"]
    al4 = _json("probes/al_round4_new_compound_backfill_summary.json")

    assert recompute["list"] == "probes/al_round4_backfill_list_v0.csv"
    assert recompute["summary"] == "probes/al_round4_new_compound_backfill_summary.json"
    assert recompute["recomputed_at_export"] is True
    assert recompute["rows"] == al4["list_stats"]["rows"]
    assert recompute["by_row_kind"] == al4["list_stats"]["by_row_kind"]
    assert recompute["new_compound_rows"] == al4["list_stats"]["new_compound_rows"]
    assert recompute["new_compound_rows"] == recompute["by_row_kind"]["new_compound"]
    assert sum(recompute["by_row_kind"].values()) == recompute["rows"]

    # The trace count is recomputed off the list at export time, so the shipped
    # list and the shipped count have to agree with each other.
    list_path = REPOSITORY_ROOT / "probes" / "al_round4_backfill_list_v0.csv"
    assert recompute["distinct_local_trace_files"] == distinct_local_trace_files(list_path)
    assert recompute["distinct_local_trace_files"] == distinct_local_trace_files(
        root / WEEK / "al_round4_backfill_list_v0.csv"
    )
    assert "git ls-files" in recompute["known_fragility"]
    assert "disk" in recompute["known_fragility"]


def test_the_pool_definition_caveat_forbids_the_headline_comparison(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    caveat = _summary(root)["pool_definition_caveat"]

    assert "147" in caveat
    assert "97" in caveat
    assert "0.364" in caveat
    assert "never be compared" in caveat


def test_readme_ships_the_boundaries_the_summary_claims() -> None:
    assert ORDER_LABEL_ERRATUM_NOTE in README_TEXT
    for phrase in (
        "+0.015746812",
        "预注册池序",
        "三序全部低于",
        "sub_threshold",
        "0.007080803",
    ):
        assert phrase in ORDER_LABEL_ERRATUM_NOTE, phrase
    for phrase in (
        "这是补给线，不是新矿脉",
        "不许把「有 2,725 行」讲成「多出 2,725 行新化合物」",
        "不得**与 v1.0",
        "受限的 858 条",
        "本地 XML 是 NIST 全库",
        "重要度不是因果",
        "不声称任何特征是物理机制",
    ):
        assert phrase in README_TEXT, phrase


def test_the_open_erratum_note_is_carried_by_the_machine_summary(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    corrections = _summary(root)["open_corrections"]

    assert corrections["lever_9_k10_column_order_label"] == ORDER_LABEL_ERRATUM_NOTE
    assert "标签是错的" in corrections["lever_9_k10_column_order_label"]


def test_summary_separates_the_artifacts_commit_from_the_export_time_head(
    exported: tuple[Path, dict],
) -> None:
    """The export-time HEAD alone cannot say whether the shipped files came from a commit."""

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
    assert "only when worktree_dirty is false" in note


def test_every_exported_csv_is_lf_only(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    offenders = [
        path.name for path in (root / WEEK).rglob("*.csv") if b"\r\n" in path.read_bytes()
    ]
    assert offenders == []
