from __future__ import annotations

import glob
import json

import pytest

from probes.thermoml_viscosity_coverage_probe import (
    DEFAULT_ROWS,
    DEFAULT_SUMMARY,
    REPOSITORY_ROOT,
    ROW_COLUMNS,
    THERMOML_GLOB,
    build_summary,
    doi_from_source_file,
    is_viscosity_property,
    observation_rows,
    read_csv_rows,
    to_float,
)

CORPUS_AVAILABLE = bool(glob.glob(str(REPOSITORY_ROOT / THERMOML_GLOB)))


def _parsed_viscosity_row(**overrides: str) -> dict[str, str]:
    row = {
        "source_file": "10.1016__j.jct.2014.09.015-804145a54a38.xml",
        "doi": "10.1016/j.jct.2014.09.015",
        "component_count": "1",
        "primary_compound_name": "water",
        "primary_compound_inchi_key": "XLYOFNOQVPJJNP-UHFFFAOYSA-N",
        "property_name": "Viscosity, Pa*s",
        "property_value": "0.001217",
        "property_unit": "Pa*s",
        "property_uncertainty": "4.15e-05",
        "property_uncertainty_kind": "expanded",
        "temperature_value": "303.15",
        "temperature_unit": "K",
        "phase": "Liquid",
        "method_name": "CAPTUB:UFactor:8",
        "source_row_index": "0",
    }
    row.update(overrides)
    return row


def test_to_float_rejects_non_numeric_text() -> None:
    assert to_float("0.001217") == 0.001217
    assert to_float("") is None
    assert to_float("n/a") is None
    assert to_float("nan") is None


def test_is_viscosity_property_matches_both_families() -> None:
    assert is_viscosity_property("Viscosity, Pa*s")
    assert is_viscosity_property("Kinematic viscosity, m2/s")
    assert not is_viscosity_property("Mass density, kg/m3")


def test_doi_from_source_file_recovers_the_doi() -> None:
    assert (
        doi_from_source_file("10.1016__j.jct.2014.09.015-804145a54a38.xml")
        == "10.1016/j.jct.2014.09.015"
    )
    assert doi_from_source_file("hand_written.xml") == ""


def test_observation_rows_converts_pascal_second_to_centipoise() -> None:
    rows = observation_rows([_parsed_viscosity_row()])

    assert len(rows) == 1
    assert set(rows[0]) == set(ROW_COLUMNS)
    assert rows[0]["viscosity_Pa_s"] == "0.001217"
    assert rows[0]["viscosity_cP"] == "1.217"
    assert rows[0]["viscosity_kinematic_m2_s"] == ""
    assert rows[0]["property_value"] == "0.001217"
    assert rows[0]["T_K"] == "303.15"
    assert rows[0]["n_components"] == "1"
    assert rows[0]["pure_or_mixture"] == "pure"
    assert rows[0]["source_doi"] == "10.1016/j.jct.2014.09.015"
    assert rows[0]["thermoml_file"] == "10.1016__j.jct.2014.09.015-804145a54a38.xml"
    # ThermoML has no SMILES, so the column carries the name fallback.
    assert rows[0]["smiles_or_name"] == rows[0]["name"] == "water"


def test_observation_rows_keeps_kinematic_separate_and_never_converts_it() -> None:
    rows = observation_rows(
        [
            _parsed_viscosity_row(
                property_name="Kinematic viscosity, m2/s",
                property_value="3.069e-07",
                property_unit="m2/s",
                component_count="2",
            )
        ]
    )

    assert rows[0]["viscosity_kinematic_m2_s"] == "3.069e-07"
    assert rows[0]["viscosity_Pa_s"] == ""
    assert rows[0]["viscosity_cP"] == ""
    assert rows[0]["pure_or_mixture"] == "mixture"


def test_observation_rows_drops_non_numeric_values() -> None:
    rows = observation_rows([_parsed_viscosity_row(property_value="")])

    assert rows[0]["viscosity_Pa_s"] == ""
    assert rows[0]["viscosity_cP"] == ""
    assert rows[0]["property_value"] == ""


def test_observation_rows_falls_back_to_the_filename_doi() -> None:
    rows = observation_rows([_parsed_viscosity_row(doi="")])

    assert rows[0]["source_doi"] == "10.1016/j.jct.2014.09.015"


def test_observation_rows_sorts_by_file_then_source_row_index() -> None:
    rows = observation_rows(
        [
            _parsed_viscosity_row(source_file="b.xml", source_row_index="1"),
            _parsed_viscosity_row(source_file="a.xml", source_row_index="5"),
            _parsed_viscosity_row(source_file="b.xml", source_row_index="0"),
        ]
    )

    assert [(row["thermoml_file"], row["source_row_index"]) for row in rows] == [
        ("a.xml", "5"),
        ("b.xml", "0"),
        ("b.xml", "1"),
    ]


@pytest.fixture(scope="module")
def corpus_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    if not CORPUS_AVAILABLE:
        pytest.skip("the git-ignored local ThermoML XML corpus is unavailable")
    output = tmp_path_factory.mktemp("thermoml_viscosity")
    summary_path = output / "summary.json"
    rows_path = output / "rows.csv"
    payload = build_summary(summary_path=summary_path, rows_path=rows_path)
    return {"payload": payload, "summary_path": summary_path, "rows_path": rows_path}


def test_real_corpus_reproduces_the_recon_expectations(corpus_run: dict[str, object]) -> None:
    payload = corpus_run["payload"]

    assert payload["expectation_mismatches"] == []
    assert payload["xml_files_scanned"] == 242
    assert payload["viscosity_files"] == 29
    assert payload["viscosity_rows"] == 2725
    assert payload["viscosity_rows_pa_s"] == 2549
    assert payload["viscosity_rows_kinematic"] == 176
    assert payload["viscosity_rows_pa_s"] + payload["viscosity_rows_kinematic"] == 2725
    assert payload["viscosity_rows_by_property"] == {
        "Kinematic viscosity, m2/s": 176,
        "Viscosity, Pa*s": 2549,
    }
    assert payload["pure_rows"] == 569
    assert payload["mixture_rows"] == 2156
    assert payload["pure_rows"] + payload["mixture_rows"] == payload["viscosity_rows"]
    assert payload["pure_plus_mixture"] == 2725
    assert payload["component_count_distribution"] == {"1": 569, "2": 1524, "3": 632}
    assert payload["pure_keys"] == 47
    assert payload["overlap_eps_obs"] == 37
    assert payload["overlap_viscosity_v01"] == 28
    assert payload["new_vs_eps_and_v01"] == 3
    assert payload["pure_key_overlap_detail"] == {
        "pure_keys": 47,
        "in_eps_observation_table": 37,
        "in_stored_viscosity_table": 28,
        "in_both": 21,
        "in_neither": 3,
        "new_keys": [
            "INDFXCHYORWHLQ-UHFFFAOYSA-N",
            "SEGLCEQVOFDUPX-UHFFFAOYSA-N",
            "ZTWVDFVGJLMQNA-UHFFFAOYSA-O",
        ],
    }
    assert payload["temperature_units"] == {"K": 2725}
    assert payload["phase_distribution"] == {"Liquid": 2725}
    assert payload["source_doi"] == {"distinct_dois": 29, "rows_without_doi": 0}
    assert len(payload["files_with_viscosity"]) == 29
    assert (
        sum(entry["viscosity_rows"] for entry in payload["files_with_viscosity"]) == 2725
    )


def test_real_corpus_confirms_the_extraction_gap(corpus_run: dict[str, object]) -> None:
    payload = corpus_run["payload"]

    assert payload["inputs"]["normalized_rows"] == 625
    assert set(payload["inputs"]["normalized_property_names"]) == {
        "Relative permittivity at zero frequency",
        "Relative permittivity at various frequencies",
    }
    assert payload["inputs"]["dielectric_observations_keys"] == 153
    assert payload["inputs"]["viscosity_v01_keys"] == 957
    assert payload["inputs"]["dielectric_observations_sha256"] == (
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
    )


def test_stored_extractions_hold_zero_viscosity_rows(corpus_run: dict[str, object]) -> None:
    payload = corpus_run["payload"]
    stored = payload["stored_extraction"]

    assert payload["extraction_gap"] == {
        "viscosity_rows_in_local_xml": 2725,
        "viscosity_rows_in_stored_thermoml_extractions": 0,
        "verdict": (
            "viscosity fields are present in the raw XML but absent from every "
            "table this project built out of that same ThermoML corpus"
        ),
    }
    assert stored["data/processed/thermoml_normalized.csv"]["rows"] == 625
    assert stored["data/processed/thermoml_normalized.csv"]["viscosity_rows"] == 0
    assert stored["data/processed/dielectric_raw.csv"]["rows"] == 11646
    assert stored["data/processed/dielectric_raw.csv"]["viscosity_rows"] == 0
    assert stored["data/processed/thermoml_source_manifest.csv"]["viscosity_rows"] == 0
    assert (
        stored["data/processed/thermoml_source_manifest.csv"][
            "viscosity_labelled_columns"
        ]
        == []
    )


def test_identity_layer_needs_no_name_to_structure_resolution(
    corpus_run: dict[str, object],
) -> None:
    payload = corpus_run["payload"]

    assert "sStandardInChIKey" in payload["design"]["identity_layer"]
    rows = read_csv_rows(DEFAULT_ROWS)
    assert len(rows) == 2725
    assert all(row["inchikey"] for row in rows)
    assert all(row["T_K"] for row in rows)
    assert all(row["source_doi"] for row in rows)
    assert sum(1 for row in rows if row["pure_or_mixture"] == "pure") == 569


def _comparable(payload: dict) -> dict:
    """Drop the run-dependent timestamp and the informational write targets."""

    return {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "outputs"}
    }


def test_committed_summary_and_rows_match_a_fresh_build(
    corpus_run: dict[str, object],
) -> None:
    fresh = corpus_run["payload"]
    committed = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))

    assert _comparable(committed) == _comparable(fresh)
    # The committed artifact must also record the canonical write targets.
    assert committed["outputs"] == {
        "summary_path": "probes/thermoml_viscosity_coverage_summary.json",
        "rows_path": "data/processed/viscosity_observations_thermoml.csv",
        "rows": 2725,
        "rows_pure": 569,
    }
    assert fresh["outputs"]["rows"] == committed["outputs"]["rows"]
    assert fresh["outputs"]["rows_pure"] == committed["outputs"]["rows_pure"]

    committed_rows = DEFAULT_ROWS.read_bytes()
    assert committed_rows == corpus_run["rows_path"].read_bytes()
    assert b"\r\n" not in committed_rows
    assert committed_rows.count(b"\n") == 2726


def test_build_summary_is_idempotent(
    corpus_run: dict[str, object], tmp_path
) -> None:
    second = build_summary(
        summary_path=tmp_path / "summary.json", rows_path=tmp_path / "rows.csv"
    )
    first = corpus_run["payload"]

    assert _comparable(first) == _comparable(second)
    assert first["outputs"]["rows"] == second["outputs"]["rows"]
    assert first["outputs"]["rows_pure"] == second["outputs"]["rows_pure"]
    assert (tmp_path / "rows.csv").read_bytes() == corpus_run["rows_path"].read_bytes()


REPORT_PATH = REPOSITORY_ROOT / "reports" / "thermoml_viscosity_coverage.md"


def test_report_carries_the_four_sections_and_the_pinned_readings() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")

    for heading in ("## 数据来源", "## 方法", "## 读数", "## 边界（不许省略）"):
        assert heading in text
    for reading in (
        "2,725",
        "2,549",
        "2,156",
        "569",
        "47 个 key 中",
        "37",
        "28",
        "净新增",
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    ):
        assert reading in text
