from __future__ import annotations

import json

import pytest

from probes.schrodinger_si_reconciliation import (
    DEFAULT_SUMMARY,
    NUMERIC_LEFT_COLUMNS,
    OPEN_DOI,
    REPOSITORY_ROOT,
    ROW_COLUMN_PAIRS,
    SUPP3_PREDICTION_COLUMN,
    TOLERANCE,
    build_summary,
    compare_row_aligned,
    numbers_equal,
)


def _stored_row(**overrides: str) -> dict[str, str]:
    row = {
        "T_K": "298.15",
        "viscosity_cP": "1.217",
        "name": "water",
        "smiles": "O",
    }
    row.update(overrides)
    return row


def _supplement_row(**overrides: str) -> dict[str, str]:
    row = {
        "Temperature (K)": "298.15",
        "Viscosity (cP)": "1.217",
        "Name": "water",
        "CANON_SMILES": "O",
    }
    row.update(overrides)
    return row


def test_column_pairs_cover_the_four_compared_fields() -> None:
    assert ROW_COLUMN_PAIRS == (
        ("T_K", "Temperature (K)"),
        ("viscosity_cP", "Viscosity (cP)"),
        ("name", "Name"),
        ("smiles", "CANON_SMILES"),
    )
    assert NUMERIC_LEFT_COLUMNS == {"T_K", "viscosity_cP"}
    assert TOLERANCE == 1e-9


def test_numbers_equal_uses_a_symmetric_absolute_tolerance() -> None:
    assert numbers_equal("298.15", "298.15", TOLERANCE) is True
    assert numbers_equal("298.15", "298.1500000001", TOLERANCE) is True
    assert numbers_equal("298.1500000001", "298.15", TOLERANCE) is True
    assert numbers_equal("298.15", "298.15001", TOLERANCE) is False
    assert numbers_equal("", "", TOLERANCE) is True
    assert numbers_equal("", "1.0", TOLERANCE) is False
    assert numbers_equal("n/a", "n/a", TOLERANCE) is True


def test_compare_row_aligned_accepts_identical_tables() -> None:
    result = compare_row_aligned([_stored_row()], [_supplement_row()])

    assert result["rows_compared"] == 1
    assert result["row_aligned_matches"] == 1
    assert result["mismatches"] == 0
    assert result["mismatch_examples"] == []
    assert result["row_count_delta_left_minus_right"] == 0


def test_compare_row_aligned_flags_a_numeric_drift() -> None:
    result = compare_row_aligned(
        [_stored_row()], [_supplement_row(**{"Viscosity (cP)": "1.2171"})]
    )

    assert result["row_aligned_matches"] == 0
    assert result["mismatches"] == 1
    assert result["per_column_mismatches"] == {
        "T_K": 0,
        "viscosity_cP": 1,
        "name": 0,
        "smiles": 0,
    }
    assert result["mismatch_examples"] == [
        {
            "row_index": 0,
            "left_column": "viscosity_cP",
            "right_column": "Viscosity (cP)",
            "left_value": "1.217",
            "right_value": "1.2171",
        }
    ]


def test_compare_row_aligned_flags_a_name_mismatch() -> None:
    result = compare_row_aligned(
        [_stored_row()], [_supplement_row(Name="heavy water")]
    )

    assert result["mismatches"] == 1
    assert result["per_column_mismatches"]["name"] == 1
    assert result["per_column_mismatches"]["T_K"] == 0


def test_compare_row_aligned_reports_a_row_count_delta() -> None:
    result = compare_row_aligned([_stored_row()], [_supplement_row(), _supplement_row()])

    assert result["rows_compared"] == 1
    assert result["row_aligned_matches"] == 1
    assert result["row_count_delta_left_minus_right"] == -1


def test_compare_row_aligned_caps_the_recorded_examples() -> None:
    stored = [_stored_row(T_K=str(300 + index)) for index in range(15)]
    supplement = [
        _supplement_row(**{"Temperature (K)": str(250 + index)}) for index in range(15)
    ]

    result = compare_row_aligned(stored, supplement)

    assert result["mismatches"] == 15
    assert result["per_column_mismatches"]["T_K"] == 15
    assert len(result["mismatch_examples"]) == 10


@pytest.fixture(scope="module")
def fresh_summary(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output = tmp_path_factory.mktemp("schrodinger_si")
    return build_summary(summary_path=output / "summary.json")


def test_stored_table_is_the_open_subset_row_by_row(
    fresh_summary: dict[str, object],
) -> None:
    payload = fresh_summary

    assert payload["expectation_mismatches"] == []
    assert payload["row_aligned_matches"] == 3582
    assert payload["mismatches"] == 0
    assert payload["unique_keys"] == 957
    assert payload["source_doi_set"] == [OPEN_DOI]
    assert payload["source_doi_set_matches_expected"] is True

    comparison = payload["row_aligned_comparison"]
    assert comparison["rows_compared"] == 3582
    assert comparison["mismatch_examples"] == []
    assert comparison["row_count_delta_left_minus_right"] == 0
    assert comparison["per_column_mismatches"] == {
        "T_K": 0,
        "viscosity_cP": 0,
        "name": 0,
        "smiles": 0,
    }
    assert payload["inputs"]["viscosity_v01"]["rows"] == 3582
    assert payload["inputs"]["supp_2"]["rows"] == 3582
    assert payload["inputs"]["supp_3"]["rows"] == 650
    assert payload["stored_table"] == {
        "rows": 3582,
        "unique_keys": 957,
        "record_id_is_sequential": True,
        "data_status_counts": {"experimental": 3582},
        "pascal_second_consistent_rows": 3582,
        "pascal_second_inconsistent_rows": 0,
    }
    assert payload["open_subset"]["open_rows"] == 3582
    assert payload["open_subset"]["unique_smiles"] == 957
    assert payload["open_subset"]["index_is_sequential"] is True
    assert payload["open_subset"]["claimed_total_points"] == 4440
    assert payload["open_subset"]["withheld_points"] == 858


def test_supp_3_stays_out_of_the_experimental_table(
    fresh_summary: dict[str, object],
) -> None:
    supp_3 = fresh_summary["supp_3"]

    assert supp_3["rows"] == 650
    assert supp_3["unique_smiles"] == 50
    assert supp_3["overlap_smiles_with_supp_2"] == 19
    assert supp_3["data_status"] == "predicted"
    assert supp_3["prediction_column"] == SUPP3_PREDICTION_COLUMN
    assert supp_3["prediction_column_present_in_every_row"] is True
    assert supp_3["is_within_training_counts"] == {"False": 403, "True": 247}
    assert supp_3["rows_merged_into_experimental_table"] == 0
    assert supp_3["merge_forbidden"] is True
    assert "data_status=predicted" in supp_3["assertion"]


def _comparable(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "outputs"}
    }


def test_committed_summary_matches_a_fresh_build(
    fresh_summary: dict[str, object],
) -> None:
    committed = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))

    assert _comparable(committed) == _comparable(fresh_summary)
    assert committed["outputs"] == {
        "summary_path": "probes/schrodinger_si_reconciliation_summary.json"
    }


def test_build_summary_is_idempotent(fresh_summary: dict[str, object], tmp_path) -> None:
    second = build_summary(summary_path=tmp_path / "summary.json")

    assert _comparable(fresh_summary) == _comparable(second)


REPORT_PATH = REPOSITORY_ROOT / "reports" / "schrodinger_si_reconciliation.md"


def test_report_carries_the_four_sections_and_the_pinned_readings() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")

    for heading in ("## 数据来源", "## 方法", "## 读数", "## 边界（不许省略）"):
        assert heading in text
    for reading in (
        "3,582",
        "957",
        "650",
        "858",
        "4,440",
        "10.1186/s13321-024-00820-5",
        "EdgePool_log(Viscosity)_pred",
        "is_within_training",
    ):
        assert reading in text
    assert "不得绕版权获取" in text
