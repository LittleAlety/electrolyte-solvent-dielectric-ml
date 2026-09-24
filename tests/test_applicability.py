from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from electrolyte_ml.applicability import (
    INSIDE_DOMAIN,
    OUTSIDE_ASSOCIATED_LIQUID,
    OUTSIDE_NONPHYSICAL,
    applicability_domain,
    count_hbond_donors,
)
from electrolyte_ml.xtb_features import onsager_dielectric_estimate
from probes.build_applicability_flags import run


def test_associated_liquid_is_outside_domain() -> None:
    assert applicability_domain(20.0, donor_count=1) == OUTSIDE_ASSOCIATED_LIQUID


def test_non_donor_liquid_stays_in_domain() -> None:
    assert applicability_domain(70.0, donor_count=0) == INSIDE_DOMAIN


def test_nonphysical_prediction_is_outside_domain() -> None:
    assert applicability_domain(0.5, donor_count=1) == OUTSIDE_NONPHYSICAL


def test_boundary_does_not_read_the_prediction() -> None:
    # The adopted trigger is structural, so it must not move with the
    # model output the boundary is meant to qualify.
    assert applicability_domain(20.0, donor_count=1) == applicability_domain(
        400.0,
        donor_count=1,
    )
    assert applicability_domain(20.0, donor_count=0) == applicability_domain(
        400.0,
        donor_count=0,
    )


def test_water_counts_as_a_hydrogen_bond_donor() -> None:
    # RDKit NumHDonors is a drug-likeness heuristic and returns 0 here,
    # which is chemically wrong for a solvent permittivity boundary.
    assert count_hbond_donors("O") == 1


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("CO", 1),  # methanol
        ("NC=O", 1),  # formamide
        ("CC#N", 0),  # acetonitrile
        ("C1COC(=O)O1", 0),  # ethylene carbonate
        ("CS(C)=O", 0),  # dimethyl sulfoxide
        ("CC(=O)OC", 0),  # methyl acetate
    ],
)
def test_textbook_donor_examples(smiles: str, expected: int) -> None:
    assert count_hbond_donors(smiles) == expected


def test_count_hbond_donors_rejects_unparsable_smiles() -> None:
    with pytest.raises(ValueError):
        count_hbond_donors("this-is-not-a-smiles")


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


def test_run_records_trigger_rate_and_rejected_variants(tmp_path: Path) -> None:
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

    def prediction(inchikey: str, name: str, target: str, value: str):
        return {
            "representation": "test",
            "repeat": "0",
            "fold": "0",
            "inchikey": inchikey,
            "name": name,
            "T_K": "298.15",
            "target": target,
            "prediction": value,
        }

    predictions = [
        prediction("DONOR", "water", "20", "20"),
        prediction("DONOR_LOW", "methanol", "80", "20"),
        prediction("APROTIC", "acetonitrile", "80", "80"),
        prediction("LEGACY", "legacy-flag", "70", "70"),
        prediction("NONPHYS", "nonphysical", "20", "0.5"),
        prediction("FALLBACK", "no-physics", "20", "20"),
    ]
    _write_rows(predictions_path, prediction_fields, predictions)

    feature_fields = [
        "inchikey",
        "name",
        "T_K",
        "smiles",
        "hbd",
        "dipole_D",
        "molar_volume_m3_mol",
        "polarizability_A3",
        "status",
    ]

    def feature(
        inchikey: str,
        name: str,
        smiles: str,
        hbd: str,
        dipole: str,
        volume: str,
        alpha: str,
        status: str = "ok",
    ):
        return {
            "inchikey": inchikey,
            "name": name,
            "T_K": "298.15",
            "smiles": smiles,
            "hbd": hbd,
            "dipole_D": dipole,
            "molar_volume_m3_mol": volume,
            "polarizability_A3": alpha,
            "status": status,
        }

    features = [
        # donor SMILES, but the drug-likeness counter says hbd == 0
        feature("DONOR", "water", "O", "0", "5.0", "4e-5", "8.0"),
        feature("DONOR_LOW", "methanol", "CO", "0", "1.0", "1e-4", "8.0"),
        feature("APROTIC", "acetonitrile", "CC#N", "0", "3.9", "5.2e-5", "6.5"),
        # non-donor SMILES with hbd == 1: only the legacy rule reacts
        feature("LEGACY", "legacy-flag", "CC#N", "1", "3.9", "5.2e-5", "6.5"),
        feature("NONPHYS", "nonphysical", "CC#N", "0", "3.9", "5.2e-5", "6.5"),
        feature("FALLBACK", "no-physics", "CC#N", "0", "", "", "", "error"),
    ]
    _write_rows(features_path, feature_fields, features)

    summary = run(
        predictions_path=predictions_path,
        features_path=features_path,
        output_path=output_path,
        summary_path=summary_path,
    )

    assert summary["row_count"] == 6
    assert summary["onsager_available"] == 5
    assert summary["onsager_fallback"] == 1
    assert summary["domain_counts"] == {
        INSIDE_DOMAIN: 3,
        OUTSIDE_ASSOCIATED_LIQUID: 2,
        OUTSIDE_NONPHYSICAL: 1,
    }
    assert summary["trigger_rate"] == pytest.approx(3 / 6)
    assert summary["rule_smarts"] == "[O,S,N;!H0]"
    assert "predicted dielectric > 60" not in str(summary["rule"])

    high_zone = summary["high_permittivity_zone"]
    assert high_zone["row_count"] == 3
    assert high_zone["covered_by_adopted_rule"] == 1
    assert high_zone["coverage"] == pytest.approx(1 / 3)

    rejected = summary["rejected_variants"]
    assert set(rejected) == {"legacy_prediction_threshold", "onsager_threshold"}
    assert rejected["legacy_prediction_threshold"]["row_count"] == 1
    assert rejected["onsager_threshold"]["row_count"] == 1
    assert rejected["onsager_threshold"]["high_permittivity_zone_covered"] == 0
    assert rejected["onsager_threshold"]["flagged_compounds"] == ["water"]

    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary

    with output_path.open(encoding="utf-8", newline="") as handle:
        output_rows = {row["inchikey"]: row for row in csv.DictReader(handle)}

    assert output_rows["DONOR"]["applicability_domain"] == OUTSIDE_ASSOCIATED_LIQUID
    assert output_rows["DONOR"]["hbond_donor_count"] == "1"
    assert output_rows["APROTIC"]["applicability_domain"] == INSIDE_DOMAIN
    assert output_rows["LEGACY"]["applicability_domain"] == INSIDE_DOMAIN
    assert output_rows["NONPHYS"]["applicability_domain"] == OUTSIDE_NONPHYSICAL
    assert output_rows["FALLBACK"]["onsager_epsilon"] == ""
    assert float(output_rows["DONOR"]["onsager_epsilon"]) > 60.0
