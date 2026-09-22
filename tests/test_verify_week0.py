from __future__ import annotations

from pathlib import Path

from scripts import verify_week0


def test_batch_check_reports_missing_dielectric_marker(tmp_path: Path, monkeypatch) -> None:
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    output = processed_dir / "thermoml_normalized.csv"
    output.write_text(
        "\n".join(
            [
                (
                    "doi,primary_compound_inchi_key,property_name,property_value,"
                    "temperature_value,dielectric_kind,source_sha256"
                ),
                *[
                    f"10.0000/test,ABC,Relative permittivity,20,298,"
                    f"static_or_zero_frequency,hash-{index}"
                    for index in range(100)
                ],
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_week0, "ROOT", tmp_path)

    result = verify_week0._check_thermoml_batch()

    assert result.passed is False
    assert "is_dielectric" in result.detail
