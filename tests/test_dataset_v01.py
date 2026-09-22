from __future__ import annotations

import csv
import json
from decimal import Decimal

import pytest

from scripts.build_dataset_v01 import build_dataset_outputs

ETHANOL_INCHI = "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3"
ETHANOL_KEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
METHANOL_INCHI = "InChI=1S/CH4O/c1-2/h2H,1H3"
METHANOL_KEY = "OKKJLVBELUTLKV-UHFFFAOYSA-N"


def _write_csv(path, fieldnames, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture_paths(tmp_path):
    p1_path = tmp_path / "dielectric_raw.csv"
    chodera_path = tmp_path / "chodera.csv"
    viscosity_path = tmp_path / "chew-supp2.csv"
    predicted_path = tmp_path / "chew-supp3.csv"
    intersection_path = tmp_path / "p3_summary.json"

    p1_fields = [
        "source_file",
        "source_sha256",
        "doi",
        "property_family",
        "value",
        "expanded_uncertainty",
        "standard_uncertainty",
        "uncertainty_kind",
        "confidence_level",
        "temperature_k",
        "is_pure",
        "primary_name",
        "primary_inchi",
        "primary_inchi_key",
    ]
    p1_rows = [
        {
            "source_file": "ethanol-a.xml",
            "source_sha256": "a" * 64,
            "doi": "10.1000/p1",
            "property_family": "zero_frequency",
            "value": "2",
            "expanded_uncertainty": "0.1",
            "standard_uncertainty": "",
            "uncertainty_kind": "combined",
            "confidence_level": "95",
            "temperature_k": "293.15",
            "is_pure": "True",
            "primary_name": "ethanol",
            "primary_inchi": ETHANOL_INCHI,
            "primary_inchi_key": ETHANOL_KEY,
        },
        {
            "source_file": "ethanol-b.xml",
            "source_sha256": "b" * 64,
            "doi": "10.1000/p2",
            "property_family": "zero_frequency",
            "value": "4",
            "expanded_uncertainty": "0.2",
            "standard_uncertainty": "",
            "uncertainty_kind": "combined",
            "confidence_level": "95",
            "temperature_k": "298.15",
            "is_pure": "True",
            "primary_name": "ethanol",
            "primary_inchi": ETHANOL_INCHI,
            "primary_inchi_key": ETHANOL_KEY,
        },
        {
            "source_file": "ethanol-b.xml",
            "source_sha256": "b" * 64,
            "doi": "10.1000/p2",
            "property_family": "zero_frequency",
            "value": "6",
            "expanded_uncertainty": "0.3",
            "standard_uncertainty": "",
            "uncertainty_kind": "combined",
            "confidence_level": "95",
            "temperature_k": "303.15",
            "is_pure": "True",
            "primary_name": "ethanol",
            "primary_inchi": ETHANOL_INCHI,
            "primary_inchi_key": ETHANOL_KEY,
        },
        {
            "source_file": "mixture.xml",
            "source_sha256": "c" * 64,
            "doi": "10.1000/mix",
            "property_family": "zero_frequency",
            "value": "99",
            "expanded_uncertainty": "",
            "standard_uncertainty": "",
            "uncertainty_kind": "",
            "confidence_level": "",
            "temperature_k": "298.15",
            "is_pure": "False",
            "primary_name": "ethanol",
            "primary_inchi": ETHANOL_INCHI,
            "primary_inchi_key": ETHANOL_KEY,
        },
    ]
    _write_csv(p1_path, p1_fields, p1_rows)

    chodera_fields = [
        "components",
        "smiles",
        "cas",
        "Temperature, K",
        "Pressure, kPa",
        "Mass density, kg/m3",
        "Relative permittivity at zero frequency",
    ]
    _write_csv(
        chodera_path,
        chodera_fields,
        [
            {
                "components": "ethanol",
                "smiles": "CCO",
                "cas": "64-17-5",
                "Temperature, K": "308.2",
                "Pressure, kPa": "101.325",
                "Mass density, kg/m3": "776",
                "Relative permittivity at zero frequency": "22.87",
            }
        ],
    )

    viscosity_fields = [
        "Index",
        "Name",
        "CANON_SMILES",
        "Temperature (K)",
        "Inverse temperature (1/K)",
        "Viscosity (cP)",
        "log(Viscosity)",
        "MD_density",
        "MD_FV",
        "MD_Rg",
        "MD_SP_E",
        "MD_SP_V",
        "MD_SP",
        "MD_HV",
        "MD_RMSD",
        "Reference",
    ]
    viscosity_row = {field: "" for field in viscosity_fields}
    viscosity_row.update(
        {
            "Index": "0",
            "Name": "ethanol",
            "CANON_SMILES": "CCO",
            "Temperature (K)": "298.15",
            "Inverse temperature (1/K)": str(1 / 298.15),
            "Viscosity (cP)": "1.1",
            "log(Viscosity)": "0.0414",
            "MD_density": "0.8",
            "Reference": "fixture",
        }
    )
    _write_csv(viscosity_path, viscosity_fields, [viscosity_row])

    prediction_fields = [
        "Index",
        "Solvent Name",
        "CANON_SMILES",
        "Temperature (K)",
        "Inverse temperature (1/K)",
        "EdgePool_log(Viscosity)_pred",
        "is_within_training",
    ]
    _write_csv(
        predicted_path,
        prediction_fields,
        [
            {
                "Index": "1",
                "Solvent Name": "methanol",
                "CANON_SMILES": "CO",
                "Temperature (K)": "298.15",
                "Inverse temperature (1/K)": str(1 / 298.15),
                "EdgePool_log(Viscosity)_pred": "0.1",
                "is_within_training": "True",
            }
        ],
    )
    intersection_path.write_text(
        json.dumps({"paired_row_intersection_count": 456, "model_ready": False}),
        encoding="utf-8",
    )
    return p1_path, chodera_path, viscosity_path, predicted_path, intersection_path


def test_build_dataset_v01_uses_median_and_does_not_union_chodera(tmp_path) -> None:
    paths = _fixture_paths(tmp_path)

    result = build_dataset_outputs(
        p1_path=paths[0],
        chodera_path=paths[1],
        viscosity_path=paths[2],
        predicted_viscosity_path=paths[3],
        intersection_summary_path=paths[4],
    )

    dielectric = result["dielectric_compound_rows"]
    assert len(dielectric) == 1
    assert dielectric[0]["inchikey"] == ETHANOL_KEY
    assert Decimal(dielectric[0]["dielectric"]) == Decimal(4)
    assert dielectric[0]["n_observations"] == "3"
    assert "10.1000/p1;10.1000/p2" in dielectric[0]["source_doi"]
    assert "arXiv:1506.00262" in dielectric[0]["source_dois_all"]
    assert result["summary"]["overlap"]["union_key_count"] == 1
    assert result["summary"]["overlap"]["chodera_adds_unique_keys"] == 0
    assert result["summary"]["overlap"]["union_is_not_145"] is True


def test_build_dataset_v01_keeps_density_empty_and_excludes_predictions(tmp_path) -> None:
    paths = _fixture_paths(tmp_path)

    result = build_dataset_outputs(
        p1_path=paths[0],
        chodera_path=paths[1],
        viscosity_path=paths[2],
        predicted_viscosity_path=paths[3],
        intersection_summary_path=paths[4],
    )

    viscosity = result["viscosity_rows"]
    assert len(viscosity) == 1
    assert viscosity[0]["density"] == ""
    assert Decimal(viscosity[0]["viscosity_Pa_s"]) == Decimal("0.0011")
    assert viscosity[0]["data_status"] == "experimental"
    assert result["summary"]["viscosity"]["predicted_rows_excluded"] == 1


def test_build_dataset_v01_reports_unparseable_inchi(tmp_path) -> None:
    paths = _fixture_paths(tmp_path)
    rows = list(csv.DictReader(paths[0].open(encoding="utf-8", newline="")))
    rows[0]["primary_inchi"] = "not-an-inchi"
    rows[0]["primary_inchi_key"] = "INVALID"
    _write_csv(paths[0], rows[0].keys(), rows)

    with pytest.raises(ValueError, match="cannot parse InChI"):
        build_dataset_outputs(
            p1_path=paths[0],
            chodera_path=paths[1],
            viscosity_path=paths[2],
            predicted_viscosity_path=paths[3],
            intersection_summary_path=paths[4],
        )


def test_build_dataset_v01_uncertainty_does_not_mix_kinds(tmp_path) -> None:
    paths = _fixture_paths(tmp_path)
    rows = list(csv.DictReader(paths[0].open(encoding="utf-8", newline="")))
    rows[1]["expanded_uncertainty"] = ""
    rows[1]["standard_uncertainty"] = "0.2"
    rows[1]["uncertainty_kind"] = "standard"
    _write_csv(paths[0], rows[0].keys(), rows)

    result = build_dataset_outputs(
        p1_path=paths[0],
        chodera_path=paths[1],
        viscosity_path=paths[2],
        predicted_viscosity_path=paths[3],
        intersection_summary_path=paths[4],
    )
    row = result["dielectric_compound_rows"][0]

    assert row["uncertainty"] == ""
    assert row["uncertainty_kind"] == "mixed"
    uncertainty_signatures = json.loads(row["uncertainty_json"])
    assert {item["kind"] for item in uncertainty_signatures} == {
        "combined",
        "standard",
    }
