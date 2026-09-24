from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.verify_dielectric_v032 import (
    EC_INCHIKEY,
    METHYL_PROPIONATE_INCHIKEY,
    REQUIRED_COLUMNS,
    V031_PATH,
    V032_PATH,
    VC_INCHIKEY,
    check_counts,
    check_required_key_rows,
    check_smiles_inchikeys,
    check_source_metadata,
    check_unique_keys,
    compare_superset,
    read_csv_rows,
    validate_required_columns,
    verify_v032,
)


@pytest.fixture()
def rows() -> list[dict[str, str]]:
    _, values = read_csv_rows(V032_PATH)
    return deepcopy(values)


@pytest.fixture()
def baseline_rows() -> list[dict[str, str]]:
    _, values = read_csv_rows(V031_PATH)
    return deepcopy(values)


def test_v032_verifier_passes_all_audited_checks() -> None:
    report = verify_v032()

    assert report["passed"] is True, report["errors"]
    assert report["row_count"] == 245
    assert report["model_ready_count"] == 240
    assert report["conflict_count"] == 6
    assert report["superset_comparison"]["equal_common_rows"] == 243
    assert report["superset_comparison"]["common_key_count"] == 243
    assert report["superset_comparison"]["added_key_count"] == 2
    assert report["superset_comparison"]["added_keys"] == [
        EC_INCHIKEY,
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    ]
    assert [check["name"] for check in report["checks_run"]] == [
        "required_columns",
        "unique_inchikeys",
        "smiles_inchikey_consistency",
        "source_metadata",
        "required_key_rows",
        "dataset_counts",
        "v031_superset",
    ]


def test_superset_comparison_rejects_provenance_regression(rows, baseline_rows) -> None:
    ethoxybenzene = next(
        row for row in rows if row["inchikey"] == "DLRJIFUOBPOJNS-UHFFFAOYSA-N"
    )
    ethoxybenzene["notes"] = ""

    errors, report = compare_superset(
        rows,
        baseline_rows,
        baseline_source="data/dielectric_v031.csv",
    )

    assert report["equal_common_rows"] == 242
    assert report["mismatch_count"] == 1
    assert any("common-key field mismatches" in error for error in errors)


def test_duplicate_inchikeys_are_rejected(rows) -> None:
    rows.append(dict(rows[0]))

    errors, _ = check_unique_keys(rows)

    assert any("duplicate InChIKeys" in error for error in errors)


def test_smiles_inchikey_mismatch_is_rejected(rows) -> None:
    rows[0]["smiles"] = "C"

    errors = check_smiles_inchikeys(rows)

    assert any("SMILES InChIKey mismatch" in error for error in errors)


def test_source_metadata_fields_are_validated(rows) -> None:
    pc = next(row for row in rows if row["inchikey"] == "RUOJZAUFBMNUDX-UHFFFAOYSA-N")
    pc["source_url"] = "not-a-url"
    pc["source_citation"] = ""
    pc["source_table"] = ""
    pc["source_scope"] = "unsupported_scope"

    errors = check_source_metadata(rows)

    assert any("invalid source_url" in error for error in errors)
    assert any("missing source_citation" in error for error in errors)
    assert any("missing source_table" in error for error in errors)
    assert any("unsupported source_scope" in error for error in errors)


def test_pc_requires_source_dois_all_membership(rows) -> None:
    pc = next(row for row in rows if row["inchikey"] == "RUOJZAUFBMNUDX-UHFFFAOYSA-N")
    pc["source_dois_all"] = ""

    errors, _ = check_required_key_rows(rows)

    assert any("source_dois_all does not contain" in error for error in errors)


def test_ec_temperature_and_model_ready_are_required(rows) -> None:
    ec = next(row for row in rows if row["inchikey"] == EC_INCHIKEY)
    ec["T_K"] = "298.15"
    ec["model_ready"] = "false"

    errors, _ = check_required_key_rows(rows)

    assert any("EC: T_K" in error for error in errors)
    assert any("EC: model_ready" in error for error in errors)


def test_missing_vc_fails_instead_of_being_skipped(rows) -> None:
    rows = [row for row in rows if row["inchikey"] != VC_INCHIKEY]

    errors, _ = check_required_key_rows(rows)

    assert "vinylene carbonate (VC) missing" in errors


def test_methyl_propionate_conflict_status_is_required(rows) -> None:
    methyl_propionate = next(
        row for row in rows if row["inchikey"] == METHYL_PROPIONATE_INCHIKEY
    )
    methyl_propionate["conflict_status"] = ""

    errors, _ = check_required_key_rows(rows)

    assert any("methyl propionate: conflict_status" in error for error in errors)


def test_count_assertions_reject_regressions(rows) -> None:
    methyl_propionate = next(
        row for row in rows if row["inchikey"] == METHYL_PROPIONATE_INCHIKEY
    )
    methyl_propionate["model_ready"] = "false"
    methyl_propionate["conflict_status"] = ""

    errors, model_ready_count, conflict_count = check_counts(rows)

    assert model_ready_count == 239
    assert conflict_count == 5
    assert any("model_ready count" in error for error in errors)
    assert any("conflict count" in error for error in errors)


def test_missing_required_columns_are_reported_explicitly(rows) -> None:
    fieldnames = [field for field in REQUIRED_COLUMNS if field != "notes"]

    errors = validate_required_columns(fieldnames)

    assert errors == ["missing required columns: notes"]