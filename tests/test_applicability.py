from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from electrolyte_ml.applicability import applicability_domain
from electrolyte_ml.xtb_features import onsager_dielectric_estimate
from probes.build_applicability_flags import run


def test_associated_liquid_is_outside_domain_on_legacy_fallback() -> None:
    assert (
        applicability_domain(70.0, hbd_count=1, onsager_epsilon=None)
        == "outside_associated_liquid"
    )


def test_non_hbd_liquid_stays_in_domain() -> None:
    assert applicability_domain(70.0, hbd_count=0) == "inside_domain"


def test_nonphysical_prediction_is_outside_domain() -> None:
    assert (
        applicability_domain(0.5, hbd_count=1, onsager_epsilon=80.0)
        == "outside_nonphysical"
    )


def test_high_onsager_estimate_overrides_low_prediction() -> None:
    assert (
        applicability_domain(20.0, hbd_count=1, onsager_epsilon=80.0)
        == "outside_associated_liquid"
    )


def test_low_onsager_estimate_keeps_high_prediction_in_domain() -> None:
    assert (
        applicability_domain(80.0, hbd_count=1, onsager_epsilon=40.0)
        == "inside_domain"
    )


def test_legacy_fallback_uses_predicted_dielectric() -> None:
    assert (
        applicability_domain(40.0, hbd_count=1, onsager_epsilon=None)
        == "inside_domain"
    )
    assert (
        applicability_domain(70.0, hbd_count=1, onsager_epsilon=None)
        == "outside_associated_liquid"
    )


def test_onsager_dielectric_estimate_uses_lorentz_lorenz_and_reaction_field() -> None:
    assert onsager_dielectric_estimate(
        dipole_debye=5.0,
        molar_volume_m3_mol=4.0e-5,
        polarizability_A3=8.0,
        temperature_K=298.15,
    ) == pytest.approx(62.9295998911, rel=1e-9)


def _write_rows(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_run_records_onsager_counts_and_non_circular_domains(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.csv"
    features_path = tmp_path / "features.csv"
    output_path = tmp_path / "applicability.csv"
    summary_path = tmp_path / "summary.json"

    prediction_fields = [
        "representation",
        "repeat",
        "fold",
        "inchikey",
        "name",
        "T_K",
        "target",
        "prediction",
    ]
    predictions = [
        {
            "representation": "test",
            "repeat": "0",
            "fold": "0",
            "inchikey": "HIGH",
            "name": "high-onsager",
            "T_K": "298.15",
            "target": "20",
            "prediction": "20",
        },
        {
            "representation": "test",
            "repeat": "0",
            "fold": "0",
            "inchikey": "LOW",
            "name": "low-onsager",
            "T_K": "298.15",
            "target": "80",
            "prediction": "80",
        },
        {
            "representation": "test",
            "repeat": "0",
            "fold": "0",
            "inchikey": "ERROR",
            "name": "feature-error",
            "T_K": "298.15",
            "target": "20",
            "prediction": "20",
        },
        {
            "representation": "test",
            "repeat": "0",
            "fold": "0",
            "inchikey": "MISSING",
            "name": "missing-physics",
            "T_K": "298.15",
            "target": "20",
            "prediction": "20",
        },
    ]
    _write_rows(predictions_path, prediction_fields, predictions)

    feature_fields = [
        "inchikey",
        "T_K",
        "hbd",
        "dipole_D",
        "molar_volume_m3_mol",
        "polarizability_A3",
        "status",
    ]
    features = [
        {
            "inchikey": "HIGH",
            "T_K": "298.15",
            "hbd": "1",
            "dipole_D": "5.0",
            "molar_volume_m3_mol": "4e-5",
            "polarizability_A3": "8.0",
            "status": "ok",
        },
        {
            "inchikey": "LOW",
            "T_K": "298.15",
            "hbd": "1",
            "dipole_D": "1.0",
            "molar_volume_m3_mol": "1e-4",
            "polarizability_A3": "8.0",
            "status": "ok",
        },
        {
            "inchikey": "ERROR",
            "T_K": "298.15",
            "hbd": "1",
            "dipole_D": "",
            "molar_volume_m3_mol": "",
            "polarizability_A3": "",
            "status": "error",
        },
        {
            "inchikey": "MISSING",
            "T_K": "298.15",
            "hbd": "1",
            "dipole_D": "5.0",
            "molar_volume_m3_mol": "4e-5",
            "polarizability_A3": "",
            "status": "ok",
        },
    ]
    _write_rows(features_path, feature_fields, features)

    summary = run(
        predictions_path=predictions_path,
        features_path=features_path,
        output_path=output_path,
        summary_path=summary_path,
    )

    assert summary["onsager_available"] == 2
    assert summary["onsager_fallback"] == 2
    assert summary["row_count"] == 4
    assert "predicted dielectric > 60" not in str(summary["rule"])
    assert "threshold_eps = onsager_epsilon when available" in str(summary["rule"])
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary

    with output_path.open(encoding="utf-8", newline="") as handle:
        output_rows = {row["inchikey"]: row for row in csv.DictReader(handle)}

    assert output_rows["HIGH"]["applicability_domain"] == "outside_associated_liquid"
    assert float(output_rows["HIGH"]["onsager_epsilon"]) > 60.0
    assert output_rows["LOW"]["applicability_domain"] == "inside_domain"
    assert float(output_rows["LOW"]["onsager_epsilon"]) < 60.0
    assert output_rows["ERROR"]["onsager_epsilon"] == ""
    assert output_rows["MISSING"]["onsager_epsilon"] == ""
