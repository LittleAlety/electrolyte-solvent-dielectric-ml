from __future__ import annotations

import hashlib

from scripts.verify_dataset_v01 import (
    check_compound_values_from_observations,
    check_dielectric_compound_rows,
    check_observation_provenance,
    check_viscosity_rows,
)


def test_dataset_v01_verifier_rejects_wrong_dielectric_row_count() -> None:
    result = check_dielectric_compound_rows(
        [
            {
                "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
                "smiles": "CCO",
                "T_K": "298.15",
                "dielectric": "24.5",
                "name": "ethanol",
                "uncertainty": "",
                "source_doi": "10.1000/example",
                "n_observations": "1",
                "source_scope": "p1",
                "gate_flags": "experimental|pure_component|zero_frequency",
            }
        ]
    )

    assert result.passed is False
    assert "100" in result.detail


def test_dataset_v01_verifier_rejects_predicted_viscosity() -> None:
    result = check_viscosity_rows(
        [
            {
                "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
                "smiles": "CCO",
                "T_K": "298.15",
                "viscosity_Pa_s": "0.0011",
                "name": "ethanol",
                "density": "",
                "data_status": "predicted",
                "source_scope": "chew_2024_supp3_prediction",
                "source_doi": "10.1000/example",
                "n_observations": "1",
                "gate_flags": "predicted",
            }
        ]
    )

    assert result.passed is False
    assert "predicted" in result.detail


def test_dataset_v01_verifier_rejects_unknown_viscosity_flag() -> None:
    result = check_viscosity_rows(
        [
            {
                "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
                "smiles": "CCO",
                "T_K": "298.15",
                "viscosity_Pa_s": "0.0011",
                "name": "ethanol",
                "density": "",
                "data_status": "experimental",
                "source_scope": "chew_2024_supp2_experimental_viscosity",
                "source_doi": "10.1000/example",
                "n_observations": "1",
                "gate_flags": "experimental|unknown_flag",
            }
        ]
    )

    assert result.passed is False
    assert "unknown_flag" in result.detail


def _p1_observation(value: str, temperature: str) -> dict[str, str]:
    return {
        "dataset_source": "P1 ThermoML",
        "selection_status": "primary",
        "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        "T_K": temperature,
        "dielectric": value,
        "source_file": "data/raw/thermoml/example.xml",
        "source_sha256": "0" * 64,
        "source_size_bytes": "1",
    }


def _compound_row(value: str, temperature: str = "298.15") -> dict[str, str]:
    return {
        "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        "name": "ethanol",
        "T_K": temperature,
        "dielectric": value,
        "n_observations": "2",
    }


def test_dataset_v01_verifier_recomputes_even_sample_median_exactly() -> None:
    result = check_compound_values_from_observations(
        [_compound_row("3")],
        [_p1_observation("2", "298.15"), _p1_observation("4", "298.15")],
    )

    assert result.passed is True


def test_dataset_v01_verifier_rejects_tampered_median() -> None:
    result = check_compound_values_from_observations(
        [_compound_row("3.1")],
        [_p1_observation("2", "298.15"), _p1_observation("4", "298.15")],
    )

    assert result.passed is False
    assert "median dielectric" in result.detail


def test_dataset_v01_verifier_rejects_provenance_hash_mismatch(tmp_path) -> None:
    raw_path = tmp_path / "data" / "raw" / "thermoml" / "example.xml"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"abc")
    row = _p1_observation("2", "298.15")
    row["source_sha256"] = "0" * 64
    row["source_size_bytes"] = "3"

    result = check_observation_provenance([row], root=tmp_path)

    assert result.passed is False
    assert "SHA256 mismatch" in result.detail


def test_dataset_v01_verifier_reports_raw_hash_skip_without_fake_pass(
    tmp_path,
) -> None:
    row = _p1_observation("2", "298.15")
    expected = hashlib.sha256(b"abc").hexdigest()
    row["source_sha256"] = expected
    row["source_size_bytes"] = "3"

    result = check_observation_provenance([row], root=tmp_path)

    assert result.passed is True
    assert "skipped" in result.detail
