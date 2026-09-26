from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from probes import build_eta_epsilon_joint_table as builder
from probes import verify_eta_epsilon_joint_table as verifier


def _write_rows(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    header, rows = verifier.read_table(builder.DEFAULT_TABLE_PATH)
    exclusion_header, exclusions = verifier.read_table(builder.DEFAULT_EXCLUSIONS_PATH)
    summary = json.loads(builder.DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8"))
    return {
        "header": header,
        "rows": rows,
        "exclusion_header": exclusion_header,
        "exclusions": exclusions,
        "summary": summary,
    }

@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    output = tmp_path_factory.mktemp("eta_epsilon_joint")
    table_path = output / "eta_epsilon_joint_observations.csv"
    exclusions_path = output / "eta_epsilon_joint_exclusions.csv"
    summary_path = output / "eta_epsilon_joint_summary.json"
    report_path = output / "eta_epsilon_joint_table.md"
    summary = builder.build_artifacts(
        table_path=table_path,
        exclusions_path=exclusions_path,
        summary_path=summary_path,
        report_path=report_path,
    )
    header, rows = verifier.read_table(table_path)
    exclusion_header, exclusions = verifier.read_table(exclusions_path)
    return {
        "table_path": table_path,
        "exclusions_path": exclusions_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "header": header,
        "rows": rows,
        "exclusion_header": exclusion_header,
        "exclusions": exclusions,
        "summary": summary,
    }

def test_the_table_has_exactly_the_locked_27_columns(committed: dict[str, Any]) -> None:
    prereg = builder.read_prereg()
    locked = [column["name"] for column in prereg["observation_schema"]["columns"]]

    assert len(locked) == 27
    assert committed["header"] == locked
    assert list(builder.OBSERVATION_COLUMNS) == locked
    assert builder.prereg_primary_key(prereg) == builder.PRIMARY_KEY

def test_every_required_column_is_filled(committed: dict[str, Any]) -> None:
    prereg = builder.read_prereg()
    required = [column["name"] for column in prereg["observation_schema"]["columns"] if column["required"]]

    for column in required:
        empty = [row["row_id"] for row in committed["rows"] if not row[column].strip()]
        assert empty == [], f"{column} empty on {empty[:3]}"

def test_the_primary_key_has_no_duplicates(committed: dict[str, Any]) -> None:
    keys = [
        tuple(row[column] for column in builder.PRIMARY_KEY) for row in committed["rows"]
    ]

    assert len(keys) == len(set(keys))

def test_unit_is_consistent_with_property_on_every_row(committed: dict[str, Any]) -> None:
    for row in committed["rows"]:
        assert row["property"] in builder.PROPERTY_UNIT, row
        assert row["unit"] == builder.PROPERTY_UNIT[row["property"]], row
        assert row["property_family"] == builder.PROPERTY_FAMILY[row["property"]], row
    assert Counter(row["unit"] for row in committed["rows"]) == Counter(
        {"1": 2065, "Pa*s": 6294}
    )

def test_cp_is_not_stored_as_a_second_column(committed: dict[str, Any]) -> None:
    assert "viscosity_cP" not in committed["header"]
    assert "cP" not in {row["unit"] for row in committed["rows"]}

def test_publishable_core_rows_carry_a_doi_and_a_measurement_kind(
    committed: dict[str, Any],
) -> None:
    core = [row for row in committed["rows"] if row["quality_layer"] == "publishable_core"]

    assert len(core) == 8196
    for row in core:
        assert row["source_doi"].strip() != "", row["row_id"]
        assert row["source_kind"] in builder.MEASUREMENT_SOURCE_KINDS, row["row_id"]

def test_pubchem_values_are_filter_only_compilations(committed: dict[str, Any]) -> None:
    harvest = [
        row for row in committed["rows"] if row["dataset_id"] == builder.DATASET_PUBCHEM
    ]

    assert harvest, "the harvest contributed no row at all"
    for row in harvest:
        assert row["quality_layer"] == "filter_only"
        assert row["source_kind"] == "compilation"
        assert row["licence"] == "publisher_terms_see_source"
        assert row["redistributable"] == "false"
    filter_only = [row for row in committed["rows"] if row["quality_layer"] == "filter_only"]
    assert {row["dataset_id"] for row in filter_only} == {builder.DATASET_PUBCHEM}

def test_the_headline_never_counts_a_filter_only_row(committed: dict[str, Any]) -> None:
    summary = committed["summary"]
    headline = summary["publishable_headline"]

    assert headline["rows"] == summary["row_counts"]["observations"] - headline[
        "filter_only_rows_excluded_from_this_headline"
    ]
    assert set(headline["by_dataset_id"]) == {
        builder.DATASET_EPSILON,
        builder.DATASET_THERMOML,
        builder.DATASET_SCHRODINGER,
    }

def test_conflicting_values_are_all_kept(committed: dict[str, Any]) -> None:
    summary = committed["summary"]
    conflicts = summary["conflicts"]["all_rows"]
    examples = conflicts["examples"]

    assert conflicts["conflicting_keys"] > 0
    assert conflicts["averaging_applied"] is False
    by_key: dict[tuple[str, str, str], set[str]] = {}
    for row in committed["rows"]:
        key = (row["inchikey"], row["property"], row["T_K"])
        by_key.setdefault(key, set()).add(row["value"])
    recomputed = {key: values for key, values in by_key.items() if len(values) > 1}
    assert len(recomputed) == conflicts["conflicting_keys"]
    for example in examples:
        observed = {
            row["value"]
            for row in committed["rows"]
            if row["inchikey"] == example["inchikey"]
            and row["property"] == example["property"]
            and float(row["T_K"]) == float(example["T_K"])
        }
        assert observed == set(example["values"])

def _verify(
    built: dict[str, Any],
    *,
    table_path: Path | None = None,
    exclusions_path: Path | None = None,
) -> dict[str, Any]:
    return verifier.verify(
        table_path=table_path or built["table_path"],
        exclusions_path=exclusions_path or built["exclusions_path"],
        summary_path=built["summary_path"],
    )

def test_the_verifier_passes_on_a_fresh_build(fresh: dict[str, Any]) -> None:
    report = _verify(fresh)

    assert report["status"] == "PASS", report["failures"]
    assert report["failures"] == []
    assert [item["id"] for item in report["checks"]] == ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    assert report["manifest_check"]["passed"] is True

def test_the_verifier_passes_on_the_committed_artefacts() -> None:
    report = verifier.verify()

    assert report["status"] == "PASS", report["failures"]
    assert report["table"]["rows"] == 8359
    assert report["exclusions"]["rows"] == 11977

def test_the_verifier_fails_when_a_unit_no_longer_matches_the_property(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    rows = [dict(row) for row in fresh["rows"]]
    target = next(row for row in rows if row["property"] == "viscosity")
    target["unit"] = "cP"
    path = tmp_path / "corrupt_unit.csv"
    _write_rows(path, fresh["header"], rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "C2" in report["failures"]

def test_the_verifier_fails_when_a_required_cell_is_blank(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    rows = [dict(row) for row in fresh["rows"]]
    rows[0]["source_kind"] = ""
    path = tmp_path / "corrupt_blank.csv"
    _write_rows(path, fresh["header"], rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "C1" in report["failures"]

def test_the_verifier_fails_on_a_duplicated_primary_key(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    rows = [dict(row) for row in fresh["rows"]]
    rows.append(dict(rows[0]))
    path = tmp_path / "corrupt_duplicate.csv"
    _write_rows(path, fresh["header"], rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "C6" in report["failures"]

def test_the_verifier_fails_when_a_dropped_row_has_no_exclusion_record(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    rows = [dict(row) for row in fresh["rows"]]
    victim = next(row for row in rows if row["dataset_id"] == builder.DATASET_EPSILON)
    rows = [row for row in rows if row["row_id"] != victim["row_id"]]
    path = tmp_path / "corrupt_dropped.csv"
    _write_rows(path, fresh["header"], rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "C7" in report["failures"]

def test_the_verifier_fails_on_a_tampered_row_digest(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    rows = [dict(row) for row in fresh["rows"]]
    rows[0]["source_file_sha256"] = "0" * 64
    path = tmp_path / "corrupt_digest.csv"
    _write_rows(path, fresh["header"], rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "S1" in report["failures"]

def test_the_verifier_fails_on_a_dropped_column(
    fresh: dict[str, Any], tmp_path: Path
) -> None:
    header = [column for column in fresh["header"] if column != "pressure_kpa"]
    rows = [{key: value for key, value in row.items() if key != "pressure_kpa"} for row in fresh["rows"]]
    path = tmp_path / "corrupt_header.csv"
    _write_rows(path, header, rows)

    report = _verify(fresh, table_path=path)

    assert report["status"] == "FAIL"
    assert "C1" in report["failures"]

def test_the_verifier_main_returns_the_exit_code(tmp_path: Path) -> None:
    assert verifier.main([]) == 0
    missing = tmp_path / "absent.csv"
    assert verifier.main(["--table", str(missing)]) == 1

def test_exclusion_records_name_their_source_and_reason(fresh: dict[str, Any]) -> None:
    exclusions = fresh["exclusions"]

    assert exclusions
    for row in exclusions:
        assert row["source_file"].strip()
        assert row["reason_code"].strip()
        assert row["reason"].strip()
    reasons = Counter(row["reason_code"] for row in exclusions)
    assert reasons["kinematic_viscosity_not_dynamic"] == 214
    assert reasons["property_not_in_joint_enum"] == 11735

def test_no_source_row_shrinks_without_a_record(committed: dict[str, Any]) -> None:
    counts = committed["summary"]["row_counts"]

    assert counts["source_rows_uncovered"] == 0
    for source in committed["summary"]["sources"]:
        assert source["source_rows_uncovered"] == 0
        assert source["source_rows_covered"] == source["rows_in_source"]

def test_denylisted_sources_never_reach_the_table(committed: dict[str, Any]) -> None:
    for row in committed["rows"]:
        lowered = row["source_file"].lower()
        for marker in builder.DENYLIST_MARKERS:
            assert marker not in lowered, row["source_file"]
    contract = committed["summary"]["exclusions_contract"]
    assert contract["schrodinger_restricted_858"]["fetched_here"] is False
    assert contract["schrodinger_restricted_858"]["reconstructed_here"] is False
    assert contract["chew_2024_supp_3_predicted"]["rows_in_table"] == 0
    assert contract["reaxys_values"]["rows_in_table"] == 0
    assert contract["table_rows_from_denylisted_sources"] == 0

def test_groupkfold_by_inchikey_keeps_every_group_on_one_side(
    committed: dict[str, Any],
) -> None:
    contract = committed["summary"]["evaluation_contract"]

    assert contract["splitter"] == "GroupKFold by InChIKey"
    assert contract["group_key"] == "inchikey"
    assert contract["assertion_passed"] is True
    assert contract["max_group_overlap"] == 0
    assert all(fold["group_overlap"] == 0 for fold in contract["folds"])
    assert contract["subset_rows"] == 6130
    assert "never enters a verdict" in contract["random_row"]["role"]
    assert contract["random_row"]["leaked_fraction"] > 0

def test_publishable_core_covers_pure_and_mixture_rows_but_the_target_is_pure(
    committed: dict[str, Any],
) -> None:
    summary = committed["summary"]

    assert summary["publishable_headline"]["rows"] == 8196
    assert summary["publishable_headline"]["distinct_inchikeys"] == 1037
    assert summary["filter_only_layer"]["rows"] == 163
    assert summary["pure_subset"]["rows"] == 6293
    assert summary["pure_subset"]["mixture_rows_stored_but_not_a_modelling_target"] == 2066

def test_the_committed_summary_matches_a_fresh_build(fresh: dict[str, Any]) -> None:
    committed_summary = json.loads(builder.DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8"))
    fresh_summary = fresh["summary"]

    def comparable(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in {"generated_at_utc", "manifest"}}

    assert comparable(committed_summary) == comparable(fresh_summary)
    assert (
        committed_summary["manifest"]["table"]["sha256"]
        == fresh_summary["manifest"]["table"]["sha256"]
    )
    assert (
        committed_summary["manifest"]["exclusions"]["sha256"]
        == fresh_summary["manifest"]["exclusions"]["sha256"]
    )
    assert (
        committed_summary["manifest"]["builder"]["sha256"]
        == fresh_summary["manifest"]["builder"]["sha256"]
    )

def test_the_report_states_the_boundaries_and_the_conflict() -> None:
    text = builder.DEFAULT_REPORT_PATH.read_text(encoding="utf-8")

    for heading in (
        "## 数据来源",
        "## 方法",
        "## 读数",
        "## 评估契约",
        "## 与预注册的冲突与不确定处",
        "## 边界（不许省略）",
        "## 校验",
    ):
        assert heading in text
    for reading in (
        "858",
        "650",
        "Reaxys",
        "未获取",
        "未进入",
        "GroupKFold by InChIKey",
        "group_overlap == 0",
        "random_row",
        "property_not_in_joint_enum",
        "filter_only",
    ):
        assert reading in text

def test_the_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    builder.build_artifacts(
        table_path=first,
        exclusions_path=tmp_path / "first_exc.csv",
        summary_path=tmp_path / "first_summary.json",
        report_path=tmp_path / "first.md",
    )
    builder.build_artifacts(
        table_path=second,
        exclusions_path=tmp_path / "second_exc.csv",
        summary_path=tmp_path / "second_summary.json",
        report_path=tmp_path / "second.md",
    )

    assert first.read_bytes() == second.read_bytes()
