from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from probes import walden_dn_channel as builder
from scripts import verify_walden_dn_channel as verifier

HEADINGS = (
    "## 方法",
    "## 读数",
    "## 运动黏度解冻状态",
    "## 与预注册的冲突与不确定处",
    "## 边界（不许省略）",
    "## 校验",
)

def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    return verifier.read_csv_rows(path)

@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    return builder.read_prereg()

@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    _, joint = _read(builder.JOINT_TABLE_PATH)
    pair_header, pairs = _read(builder.DEFAULT_PAIRS_PATH)
    audit_header, audit = _read(builder.DEFAULT_DN_AUDIT_PATH)
    summary = json.loads(builder.DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8"))
    return {
        "joint": joint,
        "pair_header": pair_header,
        "pairs": pairs,
        "audit_header": audit_header,
        "audit": audit,
        "summary": summary,
    }

@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    output = tmp_path_factory.mktemp("walden_dn_channel")
    pairs_path = output / "walden_coupling_pairs.csv"
    audit_path = output / "dn_coverage_audit.csv"
    summary_path = output / "walden_dn_channel_summary.json"
    report_path = output / "walden_dn_channel.md"
    summary = builder.build_artifacts(
        pairs_path=pairs_path,
        dn_audit_path=audit_path,
        summary_path=summary_path,
        report_path=report_path,
    )
    pair_header, pairs = _read(pairs_path)
    audit_header, audit = _read(audit_path)
    return {
        "pairs_path": pairs_path,
        "audit_path": audit_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "pair_header": pair_header,
        "pairs": pairs,
        "audit_header": audit_header,
        "audit": audit,
        "summary": summary,
    }

def test_prereg_is_locked_and_registers_the_rules(prereg: dict[str, Any]) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["walden_pairs"]["t_tolerance_k"] == 1e-06
    assert prereg["walden_pairs"]["t_alignment_sensitivity_ladder_k"] == [0.5, 1.0, 2.0]
    assert prereg["walden_pairs"]["primary_coupling"]["name"] == (
        "walden_coupling_epsilon_times_eta"
    )
    assert prereg["dn_channel"]["coverage_threshold"] == 0.30
    assert prereg["kinematic_thaw"]["frozen_count"] == 176
    assert "experimental" in prereg["dn_channel"]["admissibility_rule"]
    assert len(prereg["frozen_red_lines"]) == 6

def test_the_joint_table_recount_matches_the_prereg(
    committed: dict[str, Any], prereg: dict[str, Any]
) -> None:
    joint = committed["joint"]

    assert len(joint) == prereg["input"]["expected_rows"] == 8359
    assert len({row["inchikey"] for row in joint}) == prereg["input"]["expected_distinct_keys"]
    assert Counter(row["dataset_id"] for row in joint) == Counter(
        prereg["input"]["expected_source_split"]
    )
    assert Counter(row["property"] for row in joint) == Counter(
        {"epsilon": 2065, "viscosity": 6294}
    )
    recount = committed["summary"]["joint_table_recount"]
    assert recount["recount_matches_prereg"] is True

def test_the_committed_pair_table_has_the_registered_shape(
    committed: dict[str, Any],
) -> None:
    assert committed["pair_header"] == list(builder.PAIR_COLUMNS)
    assert len(committed["pairs"]) == 1219
    assert len({row["inchikey"] for row in committed["pairs"]}) == 76
    assert len({row["pair_id"] for row in committed["pairs"]}) == 1219

def test_every_pair_row_carries_both_provenances(committed: dict[str, Any]) -> None:
    for row in committed["pairs"]:
        for column in verifier.PROVENANCE_COLUMNS:
            assert (row[column] or "").strip(), row["pair_id"]
        assert row["averaging_applied"] == "false", row["pair_id"]
        if row["pair_quality_layer"] == "publishable_core":
            for column in verifier.DOI_COLUMNS:
                assert (row[column] or "").strip(), row["pair_id"]

def test_the_temperature_alignment_rule_holds_on_every_row(
    committed: dict[str, Any],
) -> None:
    tolerance = builder.read_prereg()["walden_pairs"]["t_tolerance_k"]

    for row in committed["pairs"]:
        epsilon_t = float(row["epsilon_T_K_source"])
        viscosity_t = float(row["viscosity_T_K_source"])
        assert abs(epsilon_t - viscosity_t) <= tolerance, row["pair_id"]
        assert float(row["T_alignment_delta_K"]) == 0.0, row["pair_id"]
        assert row["T_alignment_rule"] == builder.alignment_token(tolerance)
        assert float(row["T_K"]) == epsilon_t

def test_the_coupling_columns_recompute_from_the_stored_values(
    committed: dict[str, Any],
) -> None:
    couplings = []
    for row in committed["pairs"]:
        epsilon = float(row["epsilon"])
        viscosity = float(row["viscosity_Pa_s"])
        assert float(row["walden_coupling_epsilon_times_eta"]) == pytest.approx(
            epsilon * viscosity, rel=1e-12
        )
        assert float(row["walden_ratio_eta_over_epsilon"]) == pytest.approx(
            viscosity / epsilon, rel=1e-12
        )
        couplings.append(epsilon * viscosity)
    assert min(couplings) < 0.001
    assert max(couplings) > 9.0

def test_the_pair_quality_layer_follows_the_both_sides_rule(
    committed: dict[str, Any],
) -> None:
    counts = Counter()
    for row in committed["pairs"]:
        expected = (
            "publishable_core"
            if row["epsilon_quality_layer"] == "publishable_core"
            and row["viscosity_quality_layer"] == "publishable_core"
            else "filter_only"
        )
        assert row["pair_quality_layer"] == expected, row["pair_id"]
        counts[expected] += 1
        if row["pair_quality_layer"] == "filter_only":
            assert row["viscosity_dataset_id"] == "pubchem_liquid_window_harvest"
            assert row["pair_redistributable"] == "false"
    assert counts == Counter({"publishable_core": 1129, "filter_only": 90})

def test_the_source_quadrant_and_layer_counts(committed: dict[str, Any]) -> None:
    quadrant = Counter(row["pair_source_quadrant"] for row in committed["pairs"])

    assert quadrant == Counter(
        {
            "epsilon_observations_v11plus x thermoml_viscosity": 1055,
            "epsilon_observations_v11plus x pubchem_liquid_window_harvest": 90,
            "epsilon_observations_v11plus x schrodinger_viscosity_v01_open_subset": 74,
        }
    )
    purity = Counter(
        "pure"
        if row["epsilon_pure_or_mixture"] == "pure" and row["viscosity_pure_or_mixture"] == "pure"
        else "mixture"
        for row in committed["pairs"]
    )
    assert purity == Counter({"mixture": 694, "pure": 525})
    walden = committed["summary"]["walden_pairs"]
    assert walden["by_source_quadrant"] == dict(sorted(quadrant.items()))
    assert walden["averaging_applied"] is False

def test_keys_with_both_channels_but_no_shared_temperature_are_not_paired(
    committed: dict[str, Any],
) -> None:
    walden = committed["summary"]["walden_pairs"]

    assert walden["epsilon_keys"] == 153
    assert walden["viscosity_keys"] == 993
    assert walden["keys_with_both_channels"] == 103
    assert walden["keys_with_both_channels_without_a_shared_temperature"] == 27
    assert walden["matched_temperature_cells"] == 394
    assert walden["cells_with_more_than_one_value_on_a_side"] == 69
    assert 103 - 76 == walden["keys_with_both_channels_without_a_shared_temperature"]

def test_the_sensitivity_ladder_is_a_reading_only(committed: dict[str, Any]) -> None:
    ladder = committed["summary"]["walden_pairs"]["sensitivity_ladder"]

    assert [(rung["t_tolerance_k"], rung["pair_rows"], rung["distinct_keys"]) for rung in ladder] == [
        (0.5, 1529, 84),
        (1.0, 1572, 84),
        (2.0, 1750, 86),
    ]
    assert "reading only" in committed["summary"]["walden_pairs"]["sensitivity_ladder_role"]
    assert len(committed["pairs"]) == 1219
def test_the_dn_coverage_fails_the_registered_threshold(committed: dict[str, Any]) -> None:
    dn = committed["summary"]["dn_channel"]

    assert dn["target_keys"] == 1043
    assert dn["coverage_threshold"] == 0.30
    assert dn["admissible"]["covered_keys"] == 0
    assert dn["admissible"]["coverage_fraction"] == 0.0
    assert dn["admissible"]["passes_threshold"] is False
    assert dn["verdict"] == "channel_does_not_enter_the_feature_table"
    assert committed["summary"]["decision"]["dn_channel_fails_criterion"] is True
    assert dn["predicted_sub_channel"]["covered_keys"] == 32
    assert dn["predicted_sub_channel"]["merges_into_admissible_coverage"] is False
    assert dn["predicted_sub_channel"]["values_keyed_locally"] == 87

def test_the_dn_audit_covers_every_target_key(committed: dict[str, Any]) -> None:
    audit = committed["audit"]
    joint_keys = sorted({row["inchikey"] for row in committed["joint"]})

    assert committed["audit_header"] == list(builder.DN_AUDIT_COLUMNS)
    assert [row["inchikey"] for row in audit] == joint_keys
    assert len(audit) == 1043
    statuses = Counter(row["dn_channel_status"] for row in audit)
    assert statuses["admissible_dn"] == 0
    assert statuses["predicted_dn_only"] == 32
    for row in audit:
        assert row["key_carries_admissible_dn"] == "false"
        assert (row["dn_channel_status"] == "predicted_dn_only") == (
            row["key_carries_predicted_dn"] == "true"
        )

def test_the_dn_source_registry_admits_only_experimental_values(
    committed: dict[str, Any],
) -> None:
    sources = committed["summary"]["dn_channel"]["source_readings"]

    assert [source["source_id"] for source in sources] == [
        "dn218_acs_nano_experimental",
        "solvfunc87_predicted_dn",
        "perricone2011_secondary_mopn",
        "gsds_zenodo_donornum",
    ]
    admissible = [source for source in sources if source["admissible"]]
    assert [source["source_id"] for source in admissible] == ["dn218_acs_nano_experimental"]
    assert admissible[0]["values_present_locally"] == 0
    reasons = {source["source_id"]: source["inadmissible_reason"] for source in sources}
    assert reasons["solvfunc87_predicted_dn"] == "predicted_not_experimental"
    assert reasons["gsds_zenodo_donornum"] == "generated_molecule_scoring_task_not_an_experimental_corpus"
    assert reasons["perricone2011_secondary_mopn"] == (
        "secondary_compilation_without_a_readable_primary"
    )
    gsds = committed["summary"]["dn_channel"]["gsds_audit"]
    assert gsds["donornum_entry_count"] > 0
    assert gsds["donornum_standalone_dataset_entry_count"] == 0

def test_the_kinematic_viscosity_is_family_level_only(committed: dict[str, Any]) -> None:
    kinematic = committed["summary"]["kinematic_thaw"]

    assert kinematic["thermoml_kinematic_rows_excluded"] == 176
    assert kinematic["all_kinematic_rows_excluded"] == 214
    assert kinematic["thaw_dependency"] == "data/density_v01.csv"
    # The frozen W17-4 density table is on disk and committed, so the sibling-arm
    # dependency the pre-registration named has been met since that arm landed.
    assert kinematic["thaw_dependency_present"] is True
    assert kinematic["thawed"] is True
    assert "已解冻" in kinematic["statement"]
    assert committed["summary"]["decision"]["kinematic_viscosity"] == (
        "family level only in this arm; the density table is on disk so nu can fold to eta"
    )

def test_no_model_is_fitted_and_no_r2_is_reported(committed: dict[str, Any]) -> None:
    telemetry = committed["summary"]["run_telemetry"]

    assert telemetry["network_calls"] == 0
    assert telemetry["models_fitted"] == 0
    assert telemetry["r2_reported"] is False
    assert telemetry["run_mode"] == "offline"
    assert telemetry["writes_under_data"] == 2
    decision = committed["summary"]["decision"]
    assert decision["model_fitted"] is False
    assert decision["r2_reported"] is False
    assert decision["frozen_baseline_touched"] is False

def test_the_frozen_red_lines_are_intact(committed: dict[str, Any]) -> None:
    frozen = committed["summary"]["manifest"]["frozen_red_lines"]

    assert len(frozen) == 6
    assert committed["summary"]["manifest"]["frozen_red_lines_intact"] is True
    for relative, item in frozen.items():
        assert item["intact"] is True, relative
        assert item["measured"] == item["expected"]

def test_the_committed_summary_matches_a_fresh_build(fresh: dict[str, Any]) -> None:
    committed_summary = json.loads(builder.DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8"))
    fresh_summary = fresh["summary"]

    def comparable(payload: dict[str, Any]) -> dict[str, Any]:
        clone = {
            key: value
            for key, value in payload.items()
            if key not in {"generated_at_utc", "manifest"}
        }
        telemetry = dict(clone.get("run_telemetry", {}))
        telemetry.pop("generated_at_utc", None)
        clone["run_telemetry"] = telemetry
        return clone

    assert comparable(committed_summary) == comparable(fresh_summary)
    assert (
        committed_summary["manifest"]["pairs"]["sha256"]
        == fresh_summary["manifest"]["pairs"]["sha256"]
    )
    assert (
        committed_summary["manifest"]["dn_coverage_audit"]["sha256"]
        == fresh_summary["manifest"]["dn_coverage_audit"]["sha256"]
    )

def test_the_manifest_digests_match_the_bytes_on_disk(committed: dict[str, Any]) -> None:
    manifest = committed["summary"]["manifest"]

    assert manifest["pairs"]["sha256"] == verifier.sha256_of(builder.DEFAULT_PAIRS_PATH)
    assert manifest["dn_coverage_audit"]["sha256"] == verifier.sha256_of(
        builder.DEFAULT_DN_AUDIT_PATH
    )
    assert manifest["builder"]["sha256"] == verifier.sha256_of(builder.BUILDER_PATH)
    assert manifest["prereg"]["sha256"] == verifier.sha256_of(builder.PREREG_PATH)
    assert manifest["prereg"]["status"] == "locked_before_run"
    assert manifest["pairs"]["columns"] == list(builder.PAIR_COLUMNS)

def test_the_week16_products_are_never_written(committed: dict[str, Any], fresh: dict[str, Any]) -> None:
    assert fresh["pairs_path"].resolve() != builder.JOINT_TABLE_PATH.resolve()
    assert fresh["audit_path"].resolve() != builder.JOINT_EXCLUSIONS_PATH.resolve()
    _, exclusions = _read(builder.JOINT_EXCLUSIONS_PATH)
    assert len(exclusions) == 11977
    for row in committed["pairs"]:
        assert row["epsilon_dataset_id"] == "epsilon_observations_v11plus"
        assert row["epsilon_quality_layer"] == "publishable_core"

def test_the_check_mode_passes_on_the_committed_artifacts() -> None:
    assert verifier.main(["--check"]) == 0

def test_the_check_mode_fails_on_a_tampered_pair_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    header, rows = _read(builder.DEFAULT_PAIRS_PATH)
    rows[0]["walden_coupling_epsilon_times_eta"] = "999.0"
    rows[1]["T_alignment_delta_K"] = "5.0"
    rows[2]["averaging_applied"] = "true"
    rows[3]["pair_quality_layer"] = (
        "filter_only"
        if rows[3]["epsilon_quality_layer"] == "publishable_core"
        and rows[3]["viscosity_quality_layer"] == "publishable_core"
        else "publishable_core"
    )
    rows[4]["epsilon_source_row_index"] = ""
    tampered = tmp_path / "walden_coupling_pairs.csv"
    with tampered.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    monkeypatch.setattr(verifier, "PAIRS_PATH", tampered)

    checks = {name: ok for name, ok, _ in verifier.run_checks()}
    supplementary = {name: ok for name, ok, _ in verifier.run_supplementary()}
    assert checks["pair_provenance_present"] is False
    assert checks["pairs_temperature_alignment"] is False
    assert checks["coupling_columns_recompute"] is False
    assert checks["pair_quality_layer_rule"] is False
    assert supplementary["pairs_table_matches_reconstruction"] is False
    assert verifier.main(["--check"]) == 1

def test_the_report_states_the_boundaries_and_the_verdict() -> None:
    text = builder.DEFAULT_REPORT_PATH.read_text(encoding="utf-8")

    for heading in HEADINGS:
        assert heading in text
    for reading in (
        "8,359",
        "1,043",
        "1,219",
        "locked_before_run",
        "channel_does_not_enter_the_feature_table",
        "不过线",
        "已解冻",
        "density_v01.csv",
        "predicted_not_experimental",
        "DN-218",
        "SolvFunc-87",
        "filter_only",
        "6/6 INTACT",
        "0.4091179943351143",
        "averaging_applied=false",
    ):
        assert reading in text

def test_the_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    builder.build_artifacts(
        pairs_path=first,
        dn_audit_path=tmp_path / "first_audit.csv",
        summary_path=tmp_path / "first_summary.json",
        report_path=tmp_path / "first.md",
    )
    builder.build_artifacts(
        pairs_path=second,
        dn_audit_path=tmp_path / "second_audit.csv",
        summary_path=tmp_path / "second_summary.json",
        report_path=tmp_path / "second.md",
    )

    assert first.read_bytes() == second.read_bytes()
    assert (tmp_path / "first_audit.csv").read_bytes() == (tmp_path / "second_audit.csv").read_bytes()
    assert (tmp_path / "first.md").read_bytes() == (tmp_path / "second.md").read_bytes()