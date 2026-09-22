from __future__ import annotations

import csv
import json
from pathlib import Path

from electrolyte_ml.thermoml import CSV_COLUMNS
from scripts import verify_week0


def _write_batch(
    tmp_path: Path,
    *,
    provenance_row_count: int = 100,
    provenance_columns: list[str] | None = None,
    writer_columns: list[str] | None = None,
    provenance_filter: str = "dielectric_only",
    provenance_schema_version: int = 2,
    provenance_errors: list[dict[str, str]] | None = None,
    provenance_deduplication: str = "none",
    provenance_unit_conversion: str = "none",
    provenance_sources: list[dict[str, object]] | None = None,
    raw_file_count: int | None = None,
    summary_missing_temperature: int = 0,
    summary_constraint_temperature: int = 0,
    is_dielectric: str = "true",
) -> None:
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    output = processed_dir / "thermoml_normalized.csv"
    columns = list(CSV_COLUMNS if writer_columns is None else writer_columns)
    rows = [
        {
            "doi": "10.0000/test",
            "primary_compound_inchi_key": "ABC",
            "property_name": "Relative permittivity",
            "property_value": "20",
            "temperature_value": "298",
            "temperature_unit": "K",
            "dielectric_kind": "static_or_zero_frequency",
            "is_dielectric": is_dielectric,
            "constraints_json": "[]",
            "source_file": "fixture.xml",
            "source_url": "https://example.test/fixture.xml",
            "source_sha256": "fixture-hash",
        }
        for index in range(100)
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    provenance_path = processed_dir / "thermoml_normalized.provenance.json"
    sources = (
        [
            {
                "file": "fixture.xml",
                "url": "https://example.test/fixture.xml",
                "sha256": "fixture-hash",
                "row_count": 100,
            }
        ]
        if provenance_sources is None
        else provenance_sources
    )
    provenance_path.write_text(
        json.dumps(
            {
                "row_count": provenance_row_count,
                "columns": columns if provenance_columns is None else provenance_columns,
                "filter": provenance_filter,
                "schema_version": provenance_schema_version,
                "errors": [] if provenance_errors is None else provenance_errors,
                "deduplication": provenance_deduplication,
                "unit_conversion": provenance_unit_conversion,
                "sources": sources,
                "raw_file_count": (
                    len(sources) if raw_file_count is None else raw_file_count
                ),
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "docs" / "week0" / "thermoml" / "data_summary.md"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        "\n".join(
            [
                "| Metric | Value |",
                "|---|---:|",
                f"| Rows missing temperature | {summary_missing_temperature} |",
                (
                    "| Rows with temperature from Constraint | "
                    f"{summary_constraint_temperature} |"
                ),
            ]
        ),
        encoding="utf-8",
    )


def test_batch_check_reports_missing_dielectric_marker(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, is_dielectric="false")
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "invalid dielectric rows" in result.detail


def test_batch_check_requires_provenance_row_count(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_row_count=99)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "row_count" in result.detail


def test_batch_check_requires_provenance_columns(tmp_path: Path, monkeypatch) -> None:
    _write_batch(
        tmp_path,
        provenance_columns=["doi", "property_value"],
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "columns" in result.detail


def test_batch_check_rejects_outdated_csv_schema(tmp_path: Path, monkeypatch) -> None:
    outdated_columns = [
        column
        for column in CSV_COLUMNS
        if column != "property_uncertainty_confidence_level"
    ]
    _write_batch(tmp_path, writer_columns=outdated_columns)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "CSV_COLUMNS" in result.detail


def test_batch_check_requires_schema_version_two(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_schema_version=1)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "schema_version" in result.detail


def test_batch_check_requires_no_provenance_errors(tmp_path: Path, monkeypatch) -> None:
    _write_batch(
        tmp_path,
        provenance_errors=[{"file": "broken.xml", "error": "invalid XML"}],
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "errors" in result.detail


def test_batch_check_requires_no_deduplication(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_deduplication="applied")
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "deduplication" in result.detail


def test_batch_check_requires_no_unit_conversion(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_unit_conversion="applied")
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "unit_conversion" in result.detail


def test_batch_check_requires_nonempty_sources(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_sources=[], raw_file_count=1)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "sources" in result.detail


def test_batch_check_requires_raw_file_count_to_match_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(tmp_path, raw_file_count=2)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "raw_file_count" in result.detail


def test_batch_check_requires_source_row_count_to_match_csv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(
        tmp_path,
        provenance_sources=[
            {
                "file": "fixture.xml",
                "url": "https://example.test/fixture.xml",
                "sha256": "fixture-hash",
                "row_count": 99,
            }
        ],
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "source row_count" in result.detail


def test_batch_check_rejects_duplicate_source_url_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(
        tmp_path,
        provenance_sources=[
            {
                "file": "first.xml",
                "url": "https://example.test/fixture.xml",
                "sha256": "first-hash",
                "row_count": 50,
            },
            {
                "file": "second.xml",
                "url": "https://example.test/fixture.xml",
                "sha256": "second-hash",
                "row_count": 50,
            },
        ],
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "duplicate source URL" in result.detail


def test_batch_check_rejects_csv_source_not_declared_in_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(
        tmp_path,
        provenance_sources=[
            {
                "file": "other.xml",
                "url": "https://example.test/other.xml",
                "sha256": "other-hash",
                "row_count": 100,
            }
        ],
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "not declared" in result.detail


def test_batch_check_requires_provenance_filter(tmp_path: Path, monkeypatch) -> None:
    _write_batch(tmp_path, provenance_filter="none")
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "filter" in result.detail


def test_batch_check_requires_summary_temperature_missing_count(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(tmp_path, summary_missing_temperature=1)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "temperature" in result.detail


def test_batch_check_requires_summary_constraint_temperature_count(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_batch(tmp_path, summary_constraint_temperature=1)
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "Constraint" in result.detail
