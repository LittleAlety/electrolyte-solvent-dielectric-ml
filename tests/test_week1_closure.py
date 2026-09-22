from __future__ import annotations

import hashlib
import json
import math

import pytest

from electrolyte_ml.standardize import (
    GATE_FLAGS,
    MoleculeStandardizationError,
    canonicalize_smiles,
    centipoise_to_pascal_second,
    standardize_molecule,
)
from scripts.build_week1_closure import (
    build_spot_check_rows,
    build_thermoml_manifest,
    choose_spot_check_observation,
)
from scripts.verify_week1 import check_gate_flags


def test_standardize_molecule_returns_canonical_smiles_and_inchikey() -> None:
    standardized = standardize_molecule("C(C)O")

    assert standardized.smiles == "CCO"
    assert standardized.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def test_standardize_molecule_rejects_invalid_smiles() -> None:
    with pytest.raises(MoleculeStandardizationError):
        canonicalize_smiles("not-a-smiles")


def test_centipoise_to_pascal_second_uses_exact_scale() -> None:
    assert str(centipoise_to_pascal_second("1.234")) == "0.001234"


def _observation(
    *,
    name: str,
    value: str,
    temperature: str,
    frequency: str,
    is_pure: bool,
    property_family: str = "zero_frequency",
    source_file: str = "source.xml",
) -> dict[str, str]:
    return {
        "components_json": json.dumps([{"name": name}]),
        "property_family": property_family,
        "value": value,
        "temperature_k": temperature,
        "frequency_mhz": frequency,
        "is_pure": str(is_pure),
        "source_file": source_file,
        "source_sha256": "0" * 64,
        "doi": "10.0000/example",
    }


def test_spot_check_prefers_pure_component_over_same_value_mixture() -> None:
    mixture = _observation(
        name="water",
        value="78.42",
        temperature="297.15",
        frequency="0",
        is_pure=False,
    )
    pure = _observation(
        name="water",
        value="78.42",
        temperature="297.15",
        frequency="0",
        is_pure=True,
    )

    selected = choose_spot_check_observation(
        [mixture, pure],
        aliases=("water",),
        property_family="zero_frequency",
        expected_temperature=297.15,
        expected_frequency=0.0,
    )

    assert selected is pure


def test_spot_check_returns_none_when_name_is_absent() -> None:
    selected = choose_spot_check_observation(
        [_observation(name="water", value="78.4", temperature="298.15", frequency="0", is_pure=True)],
        aliases=("propylene carbonate",),
        property_family="zero_frequency",
        expected_temperature=298.15,
        expected_frequency=0.0,
    )

    assert selected is None


def test_spot_check_selection_does_not_read_observed_value() -> None:
    first_in_stable_order = _observation(
        name="water",
        value="999",
        temperature="297.15",
        frequency="0",
        is_pure=True,
        source_file="a.xml",
    )
    closer_to_reference = _observation(
        name="water",
        value="78.4",
        temperature="297.15",
        frequency="0",
        is_pure=True,
        source_file="z.xml",
    )

    selected = choose_spot_check_observation(
        [closer_to_reference, first_in_stable_order],
        aliases=("water",),
        property_family="zero_frequency",
        expected_temperature=297.15,
        expected_frequency=0.0,
    )

    assert selected is first_in_stable_order


def test_manifest_recomputes_hash_and_sidecar_metadata(tmp_path) -> None:
    xml_path = tmp_path / "10.1000__example-abc.xml"
    xml_path.write_bytes(b"<ThermoML />")
    digest = hashlib.sha256(xml_path.read_bytes()).hexdigest()
    xml_path.with_name(xml_path.name + ".meta.json").write_text(
        json.dumps(
            {
                "url": "https://trc.nist.gov/ThermoML/10.1000/example.xml",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "sha256": digest,
                "size_bytes": xml_path.stat().st_size,
                "http_status": 200,
                "etag": "etag",
                "last_modified": "Thu, 01 Jan 2026 00:00:00 GMT",
            }
        ),
        encoding="utf-8",
    )

    rows = build_thermoml_manifest(tmp_path, {"unused": 2})

    assert len(rows) == 1
    assert rows[0]["sha256"] == digest
    assert rows[0]["doi"] == "10.1000/example"
    assert rows[0]["size_bytes"] == str(xml_path.stat().st_size)


def test_manifest_rejects_sidecar_hash_mismatch(tmp_path) -> None:
    xml_path = tmp_path / "10.1000__example-abc.xml"
    xml_path.write_bytes(b"<ThermoML />")
    xml_path.with_name(xml_path.name + ".meta.json").write_text(
        json.dumps(
            {
                "url": "https://trc.nist.gov/ThermoML/10.1000/example.xml",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "sha256": "0" * 64,
                "size_bytes": xml_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sidecar SHA256 mismatch"):
        build_thermoml_manifest(tmp_path, {})


def test_spot_check_uses_manual_reference_and_dmc_tolerance() -> None:
    rows = build_spot_check_rows(
        [
            _observation(
                name="dimethyl carbonate",
                value="3.134",
                temperature="298.15",
                frequency="0",
                is_pure=True,
            )
        ]
    )
    dmc = next(row for row in rows if row["anchor_id"] == "dmc_298K")

    assert dmc["expected_value"] == 3.09
    assert dmc["reference_value"] == 3.09
    assert dmc["observed_value"] == 3.134
    assert math.isclose(float(dmc["delta"]), 0.044, abs_tol=1e-12)
    assert dmc["tolerance"] == 0.05
    assert dmc["status"] == "pass"


def test_ec_guard_does_not_fabricate_reference_value() -> None:
    guard = next(
        row
        for row in build_spot_check_rows([])
        if row["anchor_id"] == "ethylene_carbonate_temperature_guard"
    )

    assert guard["expected_value"] == ""
    assert guard["reference_value"] == ""
    assert guard["status"] == "blocked_temperature_gate"


def test_gate_flags_enum_contains_all_generated_labels() -> None:
    assert {
        "not_found",
        "missing_viscosity",
        "not_training_ready",
    }.issubset(GATE_FLAGS)


def test_gate_flag_fixture_has_nonempty_schema() -> None:
    result = check_gate_flags(
        "fixture.csv",
        [{"gate_flags": "experimental|pure_component"}],
    )

    assert result.passed is True
