"""Offline unit tests for the W17-4 density rho(T) table builder.

Everything here runs with zero network access. The pinned values are what the frozen
pre-registration (probes/build_density_v01_prereg.json) committed to before the run plus
what the run then produced. They are written out literally rather than recomputed, so a
silent edit to the pre-registration, the summary, the report or the two new CSVs shows up
as a failure instead of quietly re-baselining.

The end-to-end test drives the real compose()/main() with a synthetic one-page catalog and
a synthetic ThermoML XML placed in a temporary cache, so the pagination, the value layer,
the pairing and --check are all exercised without touching NIST.
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.build_density_v01 import (
    DEFAULT_PREREG,
    DEFAULT_RAW,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    DEFAULT_TABLE,
    FIRST_PAGE_NUM,
    KINEMATIC_PROPERTY,
    PAGE_SIZE,
    RAW_COLUMNS,
    TABLE_COLUMNS,
    UNIT_TO_KG_M3,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    api_url,
    catalog_page_descriptor,
    coverage_block,
    guard_violations,
    ledger_from_raw,
    main,
    pair_kinematic_rows,
    pressure_kpa,
    project_pure_row,
    read_csv_rows,
    render_report,
    stable_view,
    table_rows_from_raw,
    temperature_distribution,
    xml_cache_paths,
    xml_url,
)

EXPECTED_PREREG_SHA256 = "4eb1a255402ca1211fef4544c1c6addd5300b1b0fbae7f98031ebdea2b84110e"
EXPECTED_MANIFEST_SHA256 = "2950d5dbc3187f7d546551f1d96e17bfb2e07dcd0ccd834a3ede0e9ec803e448"

EXPECTED_TOTAL_RECORDS = 11923
EXPECTED_DENSITY_RECORDS = 4697
EXPECTED_DENSITY_PAGES = 47
EXPECTED_FREEZE_ROWS = 176

# The 54 MB value layer (data/processed/density_raw.csv) is git-ignored on purpose
# (see .gitignore: it is offline-recomputable from data/raw/thermoml_density/, which is
# not committed either).  The contracts below can only be re-derived where that layer is
# on disk, so they skip on a clean clone instead of failing there.
RAW_LAYER_PRESENT = DEFAULT_RAW.is_file()
requires_raw_layer = pytest.mark.skipif(
    not RAW_LAYER_PRESENT,
    reason="data/processed/density_raw.csv is git-ignored and absent from this checkout",
)

KINEMATIC_PATH = REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
DIELECTRIC_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
IDENTITY_MAP_PATH = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"

METHANOL_KEY = "OKKJLVBELUTLKV-UHFFFAOYSA-N"
METHANOL_INCHI = "InChI=1S/CH4O/c1-2/h2H,1H3"
FAKE_DOI = "10.1000/alpha"

FAKE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version><nVersionMajor>1</nVersionMajor><nVersionMinor>0</nVersionMinor></Version>
  <Citation><sDOI>{doi}</sDOI><sTitle>synthetic density report</sTitle></Citation>
  <Compound>
    <RegNum><nOrgNum>1</nOrgNum></RegNum>
    <sCommonName>methanol</sCommonName>
    <sFormulaMolec>CH4O</sFormulaMolec>
    <sStandardInChI>{inchi}</sStandardInChI>
    <sStandardInChIKey>{key}</sStandardInChIKey>
  </Compound>
  <PureOrMixtureData>
    <nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber>
    <Component><RegNum><nOrgNum>1</nOrgNum></RegNum><nSampleNm>1</nSampleNm></Component>
    <Property>
      <nPropNumber>1</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <VolumetricProp>
            <ePropName>Mass density, kg/m3</ePropName>
            <eMethodName>Vibrating tube method</eMethodName>
          </VolumetricProp>
        </PropertyGroup>
      </Property-MethodID>
      <PropPhaseID><ePropPhase>Liquid</ePropPhase></PropPhaseID>
    </Property>
    <Variable>
      <nVarNumber>1</nVarNumber>
      <VariableID><VariableType><eTemperature>Temperature, K</eTemperature></VariableType></VariableID>
      <VarPhaseID><eVarPhase>Liquid</eVarPhase></VarPhaseID>
    </Variable>
    <Constraint>
      <nConstraintNumber>1</nConstraintNumber>
      <ConstraintID><ConstraintType><ePressure>Pressure, kPa</ePressure></ConstraintType></ConstraintID>
      <ConstraintPhaseID><eConstraintPhase>Liquid</eConstraintPhase></ConstraintPhaseID>
      <nConstraintValue>101.325</nConstraintValue>
      <nConstrDigits>6</nConstrDigits>
    </Constraint>
    <PhaseID><ePhase>Liquid</ePhase></PhaseID>
    <NumValues>
      <VariableValue><nVarNumber>1</nVarNumber><nVarValue>298.15</nVarValue><nVarDigits>5</nVarDigits></VariableValue>
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>786.6</nPropValue><nPropDigits>4</nPropDigits></PropertyValue>
    </NumValues>
    <NumValues>
      <VariableValue><nVarNumber>1</nVarNumber><nVarValue>308.15</nVarValue><nVarDigits>5</nVarDigits></VariableValue>
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>780.1</nPropValue><nPropDigits>4</nPropDigits></PropertyValue>
    </NumValues>
  </PureOrMixtureData>
</DataReport>
"""


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    return json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    return json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report_text() -> str:
    return DEFAULT_REPORT.read_text(encoding="utf-8")


# --- pre-registration is byte-frozen and locked before the run ------------------------


def test_prereg_is_byte_frozen_and_locked_before_the_run() -> None:
    import hashlib

    digest = hashlib.sha256(DEFAULT_PREREG.read_bytes()).hexdigest()
    assert digest == EXPECTED_PREREG_SHA256


def test_prereg_declares_locked_before_run_and_four_criteria(prereg) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["locked_at_utc"].endswith("Z")
    criteria = prereg["pre_registered_criteria"]
    assert set(criteria) == {
        "A_catalog_integrity_and_pagination",
        "B_value_extraction_integrity",
        "C_unfreeze_metric",
        "D_basis_honesty",
    }
    for entry in criteria.values():
        assert entry["allowed_violations"] == 0
        assert entry["statement"] and entry["threshold"] and entry["machine_readable"]


def test_prereg_records_the_no_values_in_api_finding(prereg) -> None:
    evidence = prereg["recon_evidence"]
    assert "nValue" in evidence["api_carries_no_measured_values"]
    assert prereg["value_source"]["url_template"].startswith("https://trc.nist.gov/ThermoML/")
    assert prereg["extraction_rules"]["accepted_property_names"] == [
        "Mass density, kg/m3",
        "Density, kg/m3",
    ]


def test_prereg_and_summary_agree_on_the_lock(summary, prereg) -> None:
    assert summary["prereg"]["sha256"] == EXPECTED_PREREG_SHA256
    assert summary["prereg"]["locked_at_utc"] == prereg["locked_at_utc"]
    assert summary["prereg"]["status"] == "locked_before_run"


def test_prereg_never_permits_extrapolation_for_the_unfreeze_metric(prereg) -> None:
    rules = prereg["pairing_rules"]
    assert "外推" in rules["secondary_nearest"]
    assert "1.0 K" in rules["secondary_nearest"]
    machine = prereg["pre_registered_criteria"]["C_unfreeze_metric"]["machine_readable"]
    assert machine["no_extrapolation"] is True
    assert machine["temperature_tolerance_k"] == 1.0
    assert machine["exact_tolerance_k"] == 0.001


# --- committed artifacts: contracts, newlines, counts ---------------------------------


def test_committed_table_has_exactly_the_contracted_columns() -> None:
    rows = read_csv_rows(DEFAULT_TABLE)
    assert rows
    assert list(rows[0].keys()) == list(TABLE_COLUMNS)


@requires_raw_layer
def test_committed_raw_layer_has_exactly_the_contracted_columns() -> None:
    rows = read_csv_rows(DEFAULT_RAW)
    assert rows
    assert list(rows[0].keys()) == list(RAW_COLUMNS)


def test_new_csv_and_text_artifacts_are_lf_only() -> None:
    paths = [DEFAULT_TABLE, DEFAULT_SUMMARY, DEFAULT_REPORT, DEFAULT_PREREG]
    if RAW_LAYER_PRESENT:
        paths.append(DEFAULT_RAW)
    for path in paths:
        payload = path.read_bytes()
        assert b"\r" not in payload, f"{path.name} 含 CR"


def test_summary_literal_counts_match_the_catalog(tmp_path) -> None:
    summary = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))
    slice_dataset = summary["dataset"]["slice"]
    assert slice_dataset["size_records"] == EXPECTED_DENSITY_RECORDS
    assert slice_dataset["records_collected"] == EXPECTED_DENSITY_RECORDS
    assert slice_dataset["pages_fetched"] == EXPECTED_DENSITY_PAGES
    assert slice_dataset["unique_dois"] == EXPECTED_DENSITY_RECORDS
    assert summary["dataset"]["total_records"]["size_records"] == EXPECTED_TOTAL_RECORDS
    assert slice_dataset["failed_pages"] == []
    assert (
        summary["dataset"]["manifest_sha256"] == EXPECTED_MANIFEST_SHA256
    )
    assert summary["criterion_a_catalog"]["passed"] is True


def test_summary_records_the_required_run_telemetry(summary) -> None:
    telemetry = summary["run_provenance"]["run_telemetry"]
    for key in ("network_calls", "models_fitted", "r2_reported", "writes_under_data", "run_mode"):
        assert key in telemetry
    assert telemetry["models_fitted"] == 0
    assert telemetry["r2_reported"] == 0
    assert telemetry["writes_under_data"] == 2


def test_summary_pins_input_sha256s(summary) -> None:
    for key in ("kinematic", "dielectric_v03", "identity_map"):
        digest = summary["inputs"][key]["sha256"]
        assert isinstance(digest, str) and len(digest) == 64


def test_summary_output_digest_matches_the_committed_table(summary) -> None:
    import hashlib

    digest = hashlib.sha256(DEFAULT_TABLE.read_bytes()).hexdigest()
    assert summary["outputs"]["table"]["sha256"] == digest
    assert summary["outputs"]["table"]["rows"] == len(read_csv_rows(DEFAULT_TABLE))


# --- criteria recomputed from the committed artifacts ----------------------------------


@requires_raw_layer
def test_criteria_recompute_and_match_the_summary(summary) -> None:
    table_rows = read_csv_rows(DEFAULT_TABLE)
    raw_rows = read_csv_rows(DEFAULT_RAW)
    ledger = ledger_from_raw(raw_rows)
    assert ledger == summary["criterion_b_values"]["ledger"]
    assert len(table_rows) == summary["criterion_b_values"]["table_rows"]

    expected_table = table_rows_from_raw(raw_rows)
    assert expected_table == table_rows


def test_coverage_numbers_equal_the_summary_literals(summary) -> None:
    table_keys = {row["inchikey"] for row in read_csv_rows(DEFAULT_TABLE) if row["inchikey"]}
    targets = {
        "vs_dielectric_v03": DIELECTRIC_PATH,
        "vs_identity_map": IDENTITY_MAP_PATH,
        "vs_local_kinematic": KINEMATIC_PATH,
    }
    for block_id, path in targets.items():
        rows = read_csv_rows(path)
        if block_id == "vs_local_kinematic":
            keys = {
                row["inchikey"]
                for row in rows
                if row.get("property_name") == KINEMATIC_PROPERTY and row.get("inchikey")
            }
        else:
            keys = {row["inchikey"] for row in rows if row.get("inchikey")}
        recomputed = coverage_block(block_id, path, keys, table_keys)
        assert recomputed["target_size"] == summary["coverage"][block_id]["target_size"]
        assert recomputed["intersection_size"] == summary["coverage"][block_id]["intersection_size"]
        assert recomputed["intersection"] == summary["coverage"][block_id]["intersection"]


def test_unfreeze_metric_recomputes_from_the_committed_table(summary) -> None:
    kinematic_rows = [
        row
        for row in read_csv_rows(KINEMATIC_PATH)
        if row.get("property_name") == KINEMATIC_PROPERTY
    ]
    assert len(kinematic_rows) == EXPECTED_FREEZE_ROWS
    recomputed = pair_kinematic_rows(kinematic_rows, read_csv_rows(DEFAULT_TABLE))
    assert recomputed["exact_rows"] == summary["criterion_c_unfreeze"]["exact_rows"]
    assert recomputed["nearest_rows"] == summary["criterion_c_unfreeze"]["unfreeze_rows"]


def test_every_paired_row_carries_a_source_triple(summary) -> None:
    for entry in summary["criterion_c_unfreeze"]["by_key"]:
        assert entry
    for row in summary["criterion_c_unfreeze"]["per_row"]:
        if row["nearest"]:
            assert row["nearest_source_doi"]
            assert row["nearest_thermoml_file"]
            assert row["nearest_source_row_index"] != ""


def test_report_is_the_byte_exact_render_of_the_summary(summary, report_text) -> None:
    assert report_text == render_report(summary)


def test_wording_guard_passes_on_the_committed_report(prereg, summary, report_text) -> None:
    assert guard_violations(prereg, report_text, summary) == []


# --- unit-level contracts --------------------------------------------------------------


def test_api_url_zero_bases_the_page_number() -> None:
    url = api_url('"Density, kg/m3"', PAGE_SIZE, FIRST_PAGE_NUM)
    assert "pageNum=0" in url and "pageSize=100" in url
    assert "%22Density%2C+kg%2Fm3%22" in url


def test_xml_cache_paths_keep_the_doi_dots(tmp_path) -> None:
    payload, marker = xml_cache_paths(tmp_path, FAKE_DOI)
    assert payload.name == "10.1000__alpha.xml"
    assert marker.name == "10.1000__alpha.xml.url"
    assert xml_url(FAKE_DOI) == "https://trc.nist.gov/ThermoML/10.1000/alpha.xml"


def test_unit_table_normalizes_grams_per_cm3() -> None:
    assert UNIT_TO_KG_M3["g/cm3"] == 1000.0
    assert UNIT_TO_KG_M3["kg/m3"] == 1.0
    row = {
        "primary_compound_inchi_key": METHANOL_KEY,
        "primary_compound_inchi": METHANOL_INCHI,
        "primary_compound_name": "methanol",
        "temperature_value": "298.15",
        "property_name": "Mass density, kg/m3",
        "property_value": "0.7866",
        "property_unit": "g/cm3",
        "property_uncertainty": "",
        "property_uncertainty_kind": "",
        "phase": "Liquid",
        "method_name": "",
        "constraints_json": '[{"name": "Pressure", "unit": "kPa", "value": "101.325"}]',
        "doi": FAKE_DOI,
        "source_file": "x.xml",
        "source_row_index": "0",
    }
    projected = project_pure_row(row, inchi_cache={})
    assert projected["density_kg_m3"] == "786.6"
    assert projected["unit_conversion_factor"] == "1000"
    assert projected["quality_flag"] == "accepted"
    assert projected["pressure_kPa"] == "101.325"


def test_unit_outside_the_table_is_rejected_not_converted() -> None:
    row = {
        "primary_compound_inchi_key": METHANOL_KEY,
        "primary_compound_inchi": "",
        "primary_compound_name": "methanol",
        "temperature_value": "298.15",
        "property_name": "Mass density, kg/m3",
        "property_value": "786.6",
        "property_unit": "lbm/ft3",
        "property_uncertainty": "",
        "property_uncertainty_kind": "",
        "phase": "Liquid",
        "method_name": "",
        "constraints_json": "[]",
        "doi": FAKE_DOI,
        "source_file": "x.xml",
        "source_row_index": "0",
    }
    projected = project_pure_row(row, inchi_cache={})
    assert projected["quality_flag"] == "unit_rejected"
    assert projected["density_kg_m3"] == ""


def test_temperature_and_density_guards() -> None:
    base = {
        "primary_compound_inchi_key": METHANOL_KEY,
        "primary_compound_inchi": "",
        "primary_compound_name": "methanol",
        "property_name": "Mass density, kg/m3",
        "property_value": "786.6",
        "property_unit": "kg/m3",
        "property_uncertainty": "",
        "property_uncertainty_kind": "",
        "phase": "Liquid",
        "method_name": "",
        "constraints_json": "[]",
        "doi": FAKE_DOI,
        "source_file": "x.xml",
        "source_row_index": "0",
    }
    hot = dict(base, temperature_value="1200")
    assert project_pure_row(hot, inchi_cache={})["quality_flag"] == "temperature_rejected"
    dense = dict(base, temperature_value="298.15", property_value="99999")
    assert project_pure_row(dense, inchi_cache={})["quality_flag"] == "value_rejected"


def test_pressure_only_reads_pressure_constraints() -> None:
    assert pressure_kpa('[{"name": "Temperature", "unit": "K", "value": "298.15"}]') == ""
    assert pressure_kpa('[{"name": "Pressure", "unit": "MPa", "value": "1"}]') == "1000"
    assert pressure_kpa("not json") == ""


def test_catalog_page_descriptor_flags_pure_mass_density() -> None:
    payload = {
        "size": 1,
        "results": [
            {
                "id": "20.5000.trc.thermoml/" + FAKE_DOI,
                "content": {
                    "Compound": [{"sStandardInChIKey": METHANOL_KEY}],
                    "PureOrMixtureData": [
                        {
                            "Component": [{"sStandardInChIKey": METHANOL_KEY}],
                            "Property": [
                                {
                                    "nPropNumber": 1,
                                    "Property-MethodID": {
                                        "PropertyGroup": {
                                            "VolumetricProp": {"ePropName": "Mass density, kg/m3"}
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    }
    descriptor = catalog_page_descriptor(payload)
    assert descriptor["dois"] == [FAKE_DOI]
    assert descriptor["pure_mass_dois"] == [FAKE_DOI]
    assert descriptor["keys"] == {METHANOL_KEY}
    assert descriptor["records_with_mass_name"] == 1
    assert descriptor["records_with_critical_name"] == 0


def test_pairing_never_extrapolates_beyond_the_tolerance() -> None:
    kinematic = [
        {"inchikey": METHANOL_KEY, "name": "methanol", "T_K": "298.15", "viscosity_kinematic_m2_s": "1e-6", "source_doi": "d", "thermoml_file": "f", "source_row_index": "0"},
        {"inchikey": METHANOL_KEY, "name": "methanol", "T_K": "400.0", "viscosity_kinematic_m2_s": "1e-6", "source_doi": "d", "thermoml_file": "f", "source_row_index": "1"},
    ]
    density = [
        {"inchikey": METHANOL_KEY, "T_K": "298.15", "density_kg_m3": "786.6", "source_doi": "d2", "thermoml_file": "d.xml", "source_row_index": "0"},
        {"inchikey": METHANOL_KEY, "T_K": "308.15", "density_kg_m3": "780.1", "source_doi": "d2", "thermoml_file": "d.xml", "source_row_index": "1"},
    ]
    pairing = pair_kinematic_rows(kinematic, density)
    assert pairing["exact_rows"] == 1
    assert pairing["nearest_rows"] == 1
    assert pairing["per_row"][1]["nearest"] is False


def test_request_budget_refuses_to_overspend() -> None:
    budget = RequestBudget(limit=1)
    budget.spend()
    with pytest.raises(BudgetExhausted):
        budget.spend()


def test_temperature_distribution_counts_every_accepted_row() -> None:
    rows = [{"T_K": "298.15"}, {"T_K": "250"}, {"T_K": "400"}]
    bins = temperature_distribution(rows)
    assert sum(entry["count"] for entry in bins) == len(rows)


def test_stable_view_drops_only_the_timestamp_and_provenance(summary) -> None:
    stable = stable_view(summary)
    assert "generated_at_utc" not in stable
    assert "run_provenance" not in stable
    assert set(stable) == set(summary) - {"generated_at_utc", "run_provenance"}


# --- synthetic end-to-end: compose + --check without any network ----------------------


def _synthetic_record(doi: str) -> dict[str, Any]:
    return {
        "id": "20.5000.trc.thermoml/" + doi,
        "type": "TRCTml4",
        "content": {
            "Citation": {"sDOI": doi},
            "Compound": [
                {
                    "RegNum": {"nOrgNum": 1},
                    "sStandardInChIKey": METHANOL_KEY,
                    "sStandardInChI": METHANOL_INCHI,
                    "sCommonName": ["methanol"],
                }
            ],
            "PureOrMixtureData": [
                {
                    "Component": [{"RegNum": {"nOrgNum": 1}, "sStandardInChIKey": METHANOL_KEY}],
                    "Property": [
                        {
                            "nPropNumber": 1,
                            "Property-MethodID": {
                                "PropertyGroup": {
                                    "VolumetricProp": {"ePropName": "Mass density, kg/m3"}
                                }
                            },
                        }
                    ],
                }
            ],
            "data_summary": {
                "pure": {"VolumetricProp": {"Mass density, kg/m3": {"data_points": 2}}}
            },
        },
    }


def _synthetic_http_get(calls: list[str]):
    def http_get(url: str, *, timeout: int = 120) -> HttpResponse:
        calls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if query["query"][0] == "*":
            body = json.dumps({"pageNum": 0, "pageSize": 1, "size": 5, "results": []}).encode(
                "utf-8"
            )
            return HttpResponse(200, body, url)
        payload = {"pageNum": 0, "pageSize": PAGE_SIZE, "size": 1, "results": [_synthetic_record(FAKE_DOI)]}
        return HttpResponse(200, json.dumps(payload).encode("utf-8"), url)

    return http_get


def _write_synthetic_workspace(root: Path) -> dict[str, Path]:
    import csv as _csv

    def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = _csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    write_rows(
        root / "kinematic.csv",
        [
            "inchikey",
            "name",
            "T_K",
            "viscosity_kinematic_m2_s",
            "property_name",
            "source_doi",
            "thermoml_file",
            "source_row_index",
        ],
        [
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "298.15",
                "viscosity_kinematic_m2_s": "1.0e-6",
                "property_name": KINEMATIC_PROPERTY,
                "source_doi": "10.1000/k",
                "thermoml_file": "k.xml",
                "source_row_index": "0",
            },
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "308.15",
                "viscosity_kinematic_m2_s": "0.9e-6",
                "property_name": KINEMATIC_PROPERTY,
                "source_doi": "10.1000/k",
                "thermoml_file": "k.xml",
                "source_row_index": "1",
            },
        ],
    )
    write_rows(
        root / "dielectric.csv",
        ["inchikey", "name"],
        [
            {"inchikey": METHANOL_KEY, "name": "methanol"},
            {"inchikey": "OTHER-KEY-AAAAAAAAAA-N", "name": "other"},
        ],
    )
    write_rows(
        root / "identity.csv",
        ["inchikey", "smiles"],
        [
            {"inchikey": METHANOL_KEY, "smiles": "CO"},
            {"inchikey": "ZZZZZZZZZZZZZZ-ZZZZZZZZSA-N", "smiles": "zz"},
        ],
    )
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    prereg["frozen_expectations"].update(
        {
            "total_records_size": 5,
            "density_slice_size": 1,
            "density_slice_pages": 1,
            "local_kinematic_rows": 2,
            "local_kinematic_keys": 1,
            "dielectric_v03_keys": 2,
            "identity_map_keys": 2,
        }
    )
    prereg_path = root / "prereg.json"
    prereg_path.write_text(json.dumps(prereg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    xml_cache = root / "xml"
    xml_cache.mkdir(parents=True, exist_ok=True)
    payload, marker = xml_cache_paths(xml_cache, FAKE_DOI)
    payload.write_text(
        FAKE_XML.format(doi=FAKE_DOI, inchi=METHANOL_INCHI, key=METHANOL_KEY),
        encoding="utf-8",
        newline="\n",
    )
    marker.write_text(xml_url(FAKE_DOI) + "\n", encoding="utf-8", newline="\n")
    return {
        "prereg": prereg_path,
        "kinematic": root / "kinematic.csv",
        "dielectric": root / "dielectric.csv",
        "identity": root / "identity.csv",
        "catalog_cache": root / "catalog",
        "xml_cache": xml_cache,
        "summary": root / "summary.json",
        "report": root / "report.md",
        "table": root / "density_v01.csv",
        "raw": root / "density_raw.csv",
    }


def test_synthetic_end_to_end_then_offline_check(tmp_path) -> None:
    paths = _write_synthetic_workspace(tmp_path)
    calls: list[str] = []
    http_get = _synthetic_http_get(calls)

    import probes.build_density_v01 as module

    original = module.default_http_get
    module.default_http_get = http_get
    try:
        status = module.main(
            [
                "--resolve-online",
                "--prereg",
                str(paths["prereg"]),
                "--summary",
                str(paths["summary"]),
                "--report",
                str(paths["report"]),
                "--catalog-cache",
                str(paths["catalog_cache"]),
                "--xml-cache",
                str(paths["xml_cache"]),
                "--table",
                str(paths["table"]),
                "--raw",
                str(paths["raw"]),
                "--dielectric",
                str(paths["dielectric"]),
                "--identity-map",
                str(paths["identity"]),
                "--kinematic",
                str(paths["kinematic"]),
            ]
        )
    finally:
        module.default_http_get = original
    assert status == 0
    # the XML was already cached, so the only network calls are catalog pages
    assert all("ThermoML-API" in url for url in calls)

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["criterion_a_catalog"]["passed"] is True
    assert summary["criterion_b_values"]["passed"] is True
    assert summary["criterion_c_unfreeze"]["passed"] is True
    assert summary["criterion_d_honesty"]["passed"] is True
    assert summary["criterion_c_unfreeze"]["unfreeze_rows"] == 2
    assert summary["coverage"]["vs_dielectric_v03"]["intersection_size"] == 1
    assert summary["run_provenance"]["value_layer_source"] == "thermoml_xml"

    # offline --check with the same caches must reproduce the artifacts byte-for-byte
    status = module.main(
        [
            "--check",
            "--prereg",
            str(paths["prereg"]),
            "--summary",
            str(paths["summary"]),
            "--report",
            str(paths["report"]),
            "--catalog-cache",
            str(paths["catalog_cache"]),
            "--xml-cache",
            str(paths["xml_cache"]),
            "--table",
            str(paths["table"]),
            "--raw",
            str(paths["raw"]),
            "--dielectric",
            str(paths["dielectric"]),
            "--identity-map",
            str(paths["identity"]),
            "--kinematic",
            str(paths["kinematic"]),
        ]
    )
    assert status == 0


@requires_raw_layer
def test_check_falls_back_to_the_committed_manifest_without_raw_cache(tmp_path) -> None:
    """无在线缓存（data/external、data/raw 都不在）时，--check 靠已提交 summary 的目录层清单
    与已提交的数值层 CSV 零网络复现；数值层本身按 .gitignore 的裁决不入库，故此处按需跳过。"""

    empty_catalog = tmp_path / "no_catalog"
    empty_xml = tmp_path / "no_xml"
    assert (
        main(
            [
                "--check",
                "--catalog-cache",
                str(empty_catalog),
                "--xml-cache",
                str(empty_xml),
            ]
        )
        == 0
    )


def test_check_refuses_to_pass_without_a_summary(tmp_path) -> None:
    paths = _write_synthetic_workspace(tmp_path)
    assert (
        main(
            [
                "--check",
                "--prereg",
                str(paths["prereg"]),
                "--summary",
                str(tmp_path / "missing.json"),
                "--report",
                str(paths["report"]),
                "--catalog-cache",
                str(paths["catalog_cache"]),
                "--xml-cache",
                str(paths["xml_cache"]),
                "--table",
                str(paths["table"]),
                "--raw",
                str(paths["raw"]),
                "--dielectric",
                str(paths["dielectric"]),
                "--identity-map",
                str(paths["identity"]),
                "--kinematic",
                str(paths["kinematic"]),
            ]
        )
        == 1
    )


def test_check_fails_when_the_report_drifts_from_the_summary(tmp_path) -> None:
    paths = _write_synthetic_workspace(tmp_path)
    calls: list[str] = []
    import probes.build_density_v01 as module

    original = module.default_http_get
    module.default_http_get = _synthetic_http_get(calls)
    try:
        assert (
            module.main(
                [
                    "--resolve-online",
                    "--prereg",
                    str(paths["prereg"]),
                    "--summary",
                    str(paths["summary"]),
                    "--report",
                    str(paths["report"]),
                    "--catalog-cache",
                    str(paths["catalog_cache"]),
                    "--xml-cache",
                    str(paths["xml_cache"]),
                    "--table",
                    str(paths["table"]),
                    "--raw",
                    str(paths["raw"]),
                    "--dielectric",
                    str(paths["dielectric"]),
                    "--identity-map",
                    str(paths["identity"]),
                    "--kinematic",
                    str(paths["kinematic"]),
                ]
            )
            == 0
        )
    finally:
        module.default_http_get = original

    paths["report"].write_text(
        paths["report"].read_text(encoding="utf-8") + "\n额外一行：未登记的措辞。\n",
        encoding="utf-8",
        newline="\n",
    )
    assert (
        main(
            [
                "--check",
                "--prereg",
                str(paths["prereg"]),
                "--summary",
                str(paths["summary"]),
                "--report",
                str(paths["report"]),
                "--catalog-cache",
                str(paths["catalog_cache"]),
                "--xml-cache",
                str(paths["xml_cache"]),
                "--table",
                str(paths["table"]),
                "--raw",
                str(paths["raw"]),
                "--dielectric",
                str(paths["dielectric"]),
                "--identity-map",
                str(paths["identity"]),
                "--kinematic",
                str(paths["kinematic"]),
            ]
        )
        == 1
    )


def test_no_test_touches_the_network(monkeypatch) -> None:
    def guard(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("test attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", guard)
    assert socket.create_connection is guard
