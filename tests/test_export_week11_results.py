from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week11_results import ARTIFACTS, VERIFIERS, WEEK, export_results

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIGEST = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week11")
    return root, export_results(output_root=root)


def test_every_declared_artifact_exists_in_the_repository() -> None:
    missing = [
        source for source, _ in ARTIFACTS if not (REPOSITORY_ROOT / source).is_file()
    ]

    assert missing == []


def test_export_ships_every_artifact_readme_manifest_and_verification(
    exported: tuple[Path, dict],
) -> None:
    root, result = exported
    week_root = root / WEEK

    assert result["verification_passed"] is True
    for _, destination in ARTIFACTS:
        assert (week_root / destination).is_file()
    for name in ("README.md", "week11_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file()
    assert verify_export_manifest(week_root) == []


def test_summary_records_the_frozen_digest_and_the_negative_verdict(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))

    assert summary["frozen_dataset"]["changed"] is False
    assert summary["frozen_dataset"]["sha256"] == FROZEN_DIGEST
    verdict = summary["verdict"]
    assert verdict["criterion_met"] is False
    assert verdict["grouped_hybrid_r2"] < 0.364
    assert verdict["random_row_hybrid_r2"] > 0.9
    assert verdict["group_leak"]["grouped"]["folds_with_a_straddling_compound"] == 0
    assert verdict["group_leak"]["random_row"]["folds_with_a_straddling_compound"] > 0


def test_summary_records_the_observation_table_shape(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    table = summary["observation_table"]

    assert table["rows"] >= 1200
    assert table["rows_missing_source_doi"] == 0
    assert table["band_counts"]["outside_declared_window"] >= 900


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    export_results(output_root=tmp_path)
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path)

    assert export_results(output_root=tmp_path, overwrite=True)["verification_passed"] is True


def test_declared_verifiers_are_real_scripts() -> None:
    for command in VERIFIERS:
        parts = shlex.split(command)
        assert (REPOSITORY_ROOT / parts[0]).is_file(), command

def test_summary_records_the_temperature_band_ablation(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    ablation = summary["band_ablation"]
    r2 = ablation["hybrid_r2"]

    assert r2["band_all"] == pytest.approx(0.1601650045731296)
    assert r2["single_row_298"] == pytest.approx(0.1860769950728934)
    assert r2["band_room_only"] == pytest.approx(0.4091179943351143)
    assert r2["band_room_only"] > r2["band_room_extended"] > r2["train_all_test_core"]
    assert ablation["mechanism"]["training_side_verdict"] == "hurts"
    assert ablation["mechanism"]["scoring_side_verdict"] == "hurts"


def test_summary_records_the_frequency_gate_and_the_closed_external_doors(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))

    gate = summary["frequency_gate"]
    assert gate["primary_cap_mhz"] == 1.0
    assert gate["accepted_rows"] == 435
    assert gate["accepted_compounds"] == 50
    assert gate["accepted_new_compounds"] == 39
    assert gate["same_source_pairs"] == 0

    topup = summary["thermoml_online_topup"]
    assert topup["archive_verdict"] == "zero_filled"
    assert topup["records_online"] == 11923
    assert topup["new_keys_with_zero_frequency_epsilon"] == 0

    ilthermo = summary["ilthermo"]
    assert ilthermo["resolved_new_compounds"] == 29
    assert ilthermo["compounds_with_temperature_series"] == 1

    al_round3 = summary["al_round3"]
    assert al_round3["leads"] == 37
    assert al_round3["value_status"]["not_attempted"] == 33

def test_summary_records_the_frequency_gate_structures(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    structures = summary["frequency_gate_structures"]

    assert structures["structurally_complete"] == 50
    assert structures["inchikey_roundtrip_match"] == 50
    assert structures["needs_xtb"] == 39
    assert structures["with_frozen_features"] == 11
    absence = structures["v11_absence_reasons"]
    roster_absence = sum(
        count
        for reason, count in absence.items()
        if reason.startswith("roster_value_source_absent_from_thermoml_raw:")
    )
    assert roster_absence == 11

def test_summary_records_the_paired_window_and_cohort_answers(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    paired = summary["room_window_paired"]

    window = paired["window_family_hybrid_r2"]
    assert window["band_room_only"] == pytest.approx(0.4091179943351143)
    assert window["train_core_test_room"] == pytest.approx(0.36252298932101024)
    assert window["train_all_test_room"] == pytest.approx(0.3230413291579051)
    assert window["train_all_test_room"] < 0.364

    cohort = paired["cohort_family_hybrid_r2"]
    assert cohort["cohort_v10_frozen"] == pytest.approx(0.2157795633748551)
    assert cohort["cohort_single_row"] == pytest.approx(0.21980963043803006)
    assert cohort["cohort_room_train_single_test"] == pytest.approx(0.22991644044192502)
    assert paired["cohort_intersection_compounds"] == 98
    assert paired["cohort_scored_compounds"] == 97

def test_summary_records_the_coverage_extension(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    extension = summary["coverage_extension"]

    assert extension["rows"] == 2065
    assert extension["compounds"] == 153
    assert extension["compounds_added_over_v11"] == 50
    assert extension["origin_overlap_rows"] == 0
    assert extension["rows_missing_source_doi"] == 0
    assert extension["rows_by_origin"] == {
        "thermoml_zero_frequency": 1630,
        "thermoml_low_frequency": 435,
    }


def test_summary_records_the_coverage_paired_benchmark_and_its_audit(
    exported: tuple[Path, dict],
) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    block = summary["coverage_paired_benchmark"]

    assert block["scored_rows"] == 457
    assert block["scored_compounds"] == 97
    assert block["folds_are_shared"] is True
    assert block["hybrid_r2"]["paired_base"] == pytest.approx(0.4091179943351143)
    assert block["hybrid_r2"]["paired_plus_coverage"] == pytest.approx(0.5332044440328436)
    assert block["delta_r2"] == pytest.approx(0.1240864496977293)
    assert block["delta_mae"] == pytest.approx(-1.5361827492386713)
    assert block["delta_spearman"] == pytest.approx(0.1080996482295582)
    assert block["decision"] == "helps"
    assert block["train_pool_compounds_widened"] == 147
    assert block["extra_train_rows_per_fold"] == 127.0
    assert block["leak_reference_hybrid_r2"] > block["extended_pool_room_hybrid_r2"]
    assert block["audit_tally"] == {"confirmed": 5, "refuted": 0, "unresolved": 0}
    assert block["audit_verdict"]["headline_reproduces"] is True
    assert block["audit_verdict"]["training_really_widened"] is True
    assert block["audit_verdict"]["leak_reference_contained"] is True


def test_summary_records_the_alpha_prior_dead_end(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    alpha = summary["alpha_prior"]

    assert alpha["coefficient_coverage_v11_room_band"] == 0.0
    assert alpha["coefficient_coverage_v10_pool"] == pytest.approx(0.1864406779661017)
    assert alpha["nbs_alpha_delta_r2_versus_the_placebo"] == 0.0
    assert alpha["leaky_slope_delta_r2_versus_the_placebo"] > 0.0
    assert alpha["honest_train_only_slope_delta_r2_versus_the_placebo"] < 0.0
    assert alpha["honest_train_only_slope_classification"] == "hurts"


def test_summary_records_the_ddb_free_search_closure(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = json.loads((root / WEEK / "week11_summary.json").read_text(encoding="utf-8"))
    ddb = summary["ddb_free_search"]

    assert ddb["app_has_no_property_query"] is True
    assert ddb["permittivity_values_read"] == 0
    assert ddb["csv_or_json_export_endpoint_found"] is False
    assert ddb["net_new_compounds"] == 0
    assert ddb["net_new_compounds_at_coverage_metadata_level"] == 33
    assert ddb["dielectric_bank_pure_components"] == 50
    assert ddb["verdict"] == "coverage_metadata_only_name_level_candidates"


def test_shipped_readme_carries_the_corrected_source_numbers(
    exported: tuple[Path, dict],
) -> None:
    """The README prose is part of the deliverable, so its key numbers are pinned.

    The ``test_summary_records_*`` tests read the exported JSON; on their own they
    cannot notice a wrong number written into the README text itself, which is the
    copy a reviewer actually reads.
    """

    root, _ = exported
    readme = (root / WEEK / "README.md").read_text(encoding="utf-8")

    # I1: 12 was the repository-wide 403 count; the publisher side has 10.
    assert "出版商侧 10x403 + 6 落地页" in readme
    assert "12x403" not in readme
    # I2: 175 counts every row, 160 is the pure-component denominator of the 57.
    assert "纯组分 160 个" in readme
    assert "57 个纯组分在零频行里完全不存在" in readme
    # I3: the span really is 1 kHz-340 MHz, and only 1/3 MHz are let through.
    assert "频率跨 1 kHz-340 MHz" in readme
    assert "主闸 ≤1 MHz 共 136 行" in readme
    assert "扩展闸 1-3 MHz 共 299 行" in readme
    # I5: the merged table and its verifier are in the entry/verification lists.
    assert "dielectric_observations_v11plus.csv" in readme
    assert "python scripts/verify_dielectric_observations_v11plus.py" in readme
    # The paired-coverage headline keeps its measured per-fold expansion.
    assert "每折真实多训练 **127 行**" in readme


def test_hybrid_raises_for_a_declared_protocol_that_is_missing() -> None:
    """Regression: a renamed/absent protocol used to publish a silent ``null``."""

    from probes.export_week11_results import _hybrid

    summary = {"summary": {"grouped": {"Morgan+Physical": {"r2": {"mean": 0.25}}}}}

    assert _hybrid(summary, "grouped") == 0.25
    with pytest.raises(KeyError):
        _hybrid(summary, "grouped_v2")
    with pytest.raises(KeyError):
        _hybrid(summary, "grouped", "spearman")
