"""Offline unit tests for the W17-3 viscosity_v02 table builder.

Everything here runs with zero network access. The pinned values are what the frozen
pre-registration (probes/build_viscosity_v02_prereg.json) committed to before the run plus
what the run then produced. They are written out literally rather than recomputed, so a
silent edit to the pre-registration, the summary, the report or the two new CSVs shows up
as a failure instead of quietly re-baselining.

The end-to-end test drives the real compose()/main() with a synthetic two-slice catalog and
synthetic ThermoML XML placed in a temporary cache, so the pagination, the value layer,
the unfreeze pairing and --check are all exercised without touching NIST.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.build_viscosity_v02 import (
    DEFAULT_DENSITY,
    DEFAULT_LOCAL_COVERAGE,
    DEFAULT_LOCAL_OBS,
    DEFAULT_PREREG,
    DEFAULT_RAW,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    DEFAULT_TABLE,
    FIRST_PAGE_NUM,
    KINEMATIC_PROPERTY,
    KINEMATIC_QUERY,
    KINEMATIC_SLUG,
    PA_S_PROPERTY,
    PA_S_QUERY,
    PA_S_SLUG,
    PA_S_UNIT_TO_PA_S,
    PAGE_SIZE,
    RAW_COLUMNS,
    TABLE_COLUMNS,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    api_url,
    catalog_page_descriptor,
    guard_violations,
    ledger_from_raw,
    load_local_doi_source,
    main_rows_from_raw,
    main_rows_from_unfreeze,
    pair_kinematic_rows,
    pressure_kpa,
    project_row,
    read_csv_rows,
    reconcile_local_pa_s,
    render_report,
    stable_view,
    temperature_distribution,
    xml_cache_paths,
    xml_url,
)

EXPECTED_PREREG_SHA256 = "0934dcf0e48e27dee57baaf667cb8d679f7a4b03ec67e2df53ab25b4a81aa6ed"
EXPECTED_MANIFEST_SHA256 = "c54e4df744565d72c7fc793dd308d0f32d1472dcadf83cd949cb8af004d53f50"
EXPECTED_TABLE_SHA256 = "907f5368ff6d4d6c15fa26c8c2b57e8bbc8c7ac7a7b3db06ec2c689b283bf3a5"
EXPECTED_RAW_SHA256 = "848153226153487bf1c6c09e3310867ea22916cd373e19139a882fa118fac901"
EXPECTED_V01_SHA256 = "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"

EXPECTED_TOTAL_RECORDS = 11923
EXPECTED_PA_S_RECORDS = 1690
EXPECTED_PA_S_PAGES = 17
EXPECTED_KINEMATIC_RECORDS = 70
EXPECTED_KINEMATIC_PAGES = 1
EXPECTED_DOI_UNION = 1743
EXPECTED_DOI_INTERSECTION = 17
EXPECTED_TABLE_ROWS = 42941
EXPECTED_TABLE_KEYS = 1228
EXPECTED_PA_S_MEASURED_ROWS = 42855
EXPECTED_KINEMATIC_CONVERTED_ROWS = 86
EXPECTED_RAW_ROWS = 268247
EXPECTED_MULTI_COMPONENT_DEFERRED = 223605
EXPECTED_LOCAL_PA_S_ROWS = 2549
EXPECTED_LOCAL_KINEMATIC_ROWS = 176
EXPECTED_KINEMATIC_POOLED_ROWS = 86
EXPECTED_LOCAL_DOIS = 29

# data/processed/viscosity_v02_raw.csv is git-ignored on purpose (see .gitignore: it is
# offline-recomputable from data/raw/thermoml_viscosity_pa_s/, which is not committed
# either).  The contracts below can only be re-derived where that layer is on disk, so
# they skip on a clean clone instead of failing there.
RAW_LAYER_PRESENT = DEFAULT_RAW.is_file()
requires_raw_layer = pytest.mark.skipif(
    not RAW_LAYER_PRESENT,
    reason="data/processed/viscosity_v02_raw.csv is git-ignored and absent from this checkout",
)

METHANOL_KEY = "OKKJLVBELUTLKV-UHFFFAOYSA-N"
METHANOL_INCHI = "InChI=1S/CH4O/c1-2/h2H,1H3"
PA_S_DOI = "10.1000/alpha"
KINEMATIC_DOI = "10.1000/beta"

FAKE_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version><nVersionMajor>1</nVersionMajor><nVersionMinor>0</nVersionMinor></Version>
  <Citation><sDOI>{doi}</sDOI><sTitle>synthetic viscosity report</sTitle></Citation>
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
          <TransportProp>
            <ePropName>{property_name}</ePropName>
            <eMethodName>Ubbelohde viscometer</eMethodName>
          </TransportProp>
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
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>{value_a}</nPropValue><nPropDigits>4</nPropDigits></PropertyValue>
    </NumValues>
    <NumValues>
      <VariableValue><nVarNumber>1</nVarNumber><nVarValue>308.15</nVarValue><nVarDigits>5</nVarDigits></VariableValue>
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>{value_b}</nPropValue><nPropDigits>4</nPropDigits></PropertyValue>
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
        "A_online_slice_reproduction_and_pagination",
        "B_local_subset_of_online",
        "C_unit_honesty",
        "D_basis_honesty",
    }
    for entry in criteria.values():
        assert entry["allowed_violations"] == 0
        assert entry["statement"] and entry["threshold"] and entry["machine_readable"]


def test_prereg_and_summary_agree_on_the_lock(summary, prereg) -> None:
    assert summary["prereg"]["sha256"] == EXPECTED_PREREG_SHA256
    assert summary["prereg"]["locked_at_utc"] == prereg["locked_at_utc"]
    assert summary["prereg"]["status"] == "locked_before_run"


def test_prereg_unit_table_is_explicit_and_forbids_silent_drop(prereg) -> None:
    table = prereg["unit_table"]
    assert table["Viscosity, Pa*s"]["cP"] == 0.001
    assert table["Viscosity, Pa*s"]["Pa*s"] == 1.0
    assert table["Kinematic viscosity, m2/s"]["mm2/s"] == 1e-06
    assert table["Kinematic viscosity, m2/s"]["m2/s"] == 1.0
    assert prereg["pre_registered_criteria"]["C_unit_honesty"]["machine_readable"][
        "silent_drop_allowed"
    ] is False
    assert prereg["frozen_expectations"]["local_kinematic_rows"] == EXPECTED_LOCAL_KINEMATIC_ROWS


def test_prereg_pins_the_frozen_expectations(prereg) -> None:
    expected = prereg["frozen_expectations"]
    assert expected["total_records_size"] == EXPECTED_TOTAL_RECORDS
    assert expected["pa_s_slice_size"] == EXPECTED_PA_S_RECORDS
    assert expected["pa_s_slice_pages"] == EXPECTED_PA_S_PAGES
    assert expected["kinematic_slice_size"] == EXPECTED_KINEMATIC_RECORDS
    assert expected["kinematic_slice_pages"] == EXPECTED_KINEMATIC_PAGES
    assert expected["local_pa_s_rows"] == EXPECTED_LOCAL_PA_S_ROWS


def test_prereg_never_permits_extrapolation_for_the_unfreeze(prereg) -> None:
    unfreeze = prereg["unfreeze"]
    assert "不插值" in unfreeze["no_interpolation"]
    assert unfreeze["exact_tolerance_k"] == 0.001
    assert unfreeze["nearest_tolerance_k"] == 1.0


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


def test_summary_literal_counts_match_the_catalog() -> None:
    summary = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))
    slices = summary["dataset"]["slices"]
    assert slices[PA_S_SLUG]["size_records"] == EXPECTED_PA_S_RECORDS
    assert slices[PA_S_SLUG]["records_collected"] == EXPECTED_PA_S_RECORDS
    assert slices[PA_S_SLUG]["pages_fetched"] == EXPECTED_PA_S_PAGES
    assert slices[PA_S_SLUG]["unique_dois"] == EXPECTED_PA_S_RECORDS
    assert slices[KINEMATIC_SLUG]["size_records"] == EXPECTED_KINEMATIC_RECORDS
    assert slices[KINEMATIC_SLUG]["records_collected"] == EXPECTED_KINEMATIC_RECORDS
    assert slices[KINEMATIC_SLUG]["pages_fetched"] == EXPECTED_KINEMATIC_PAGES
    assert summary["dataset"]["total_records"]["size_records"] == EXPECTED_TOTAL_RECORDS
    assert len(summary["dataset"]["doi_union"]) == EXPECTED_DOI_UNION
    assert len(summary["dataset"]["doi_intersection"]) == EXPECTED_DOI_INTERSECTION
    assert slices[PA_S_SLUG]["failed_pages"] == []
    assert slices[KINEMATIC_SLUG]["failed_pages"] == []
    assert summary["criterion_a_online_slice"]["passed"] is True
    assert summary["dataset"]["manifest_sha256"] == EXPECTED_MANIFEST_SHA256


def test_summary_dual_basis_counts_are_the_pinned_numbers(summary) -> None:
    dual = summary["criterion_d_basis_honesty"]["dual_basis_counts"]
    assert dual["online_pa_s_slice_records"] == EXPECTED_PA_S_RECORDS
    assert dual["online_kinematic_slice_records"] == EXPECTED_KINEMATIC_RECORDS
    assert dual["online_union_records"] == EXPECTED_DOI_UNION
    assert dual["raw_named_rows"] == EXPECTED_RAW_ROWS
    assert dual["viscosity_v02_rows"] == EXPECTED_TABLE_ROWS
    assert dual["viscosity_v02_inchikeys"] == EXPECTED_TABLE_KEYS
    assert dual["pa_s_measured_rows"] == EXPECTED_PA_S_MEASURED_ROWS
    assert dual["kinematic_converted_rows"] == EXPECTED_KINEMATIC_CONVERTED_ROWS
    assert dual["multi_component_deferred_rows"] == EXPECTED_MULTI_COMPONENT_DEFERRED
    assert summary["criterion_d_basis_honesty"]["row_comparison_allowed"] is False


def test_summary_records_the_required_run_telemetry(summary) -> None:
    telemetry = summary["run_provenance"]["run_telemetry"]
    for key in ("network_calls", "models_fitted", "r2_reported", "writes_under_data", "run_mode"):
        assert key in telemetry
    assert telemetry["models_fitted"] == 0
    assert telemetry["r2_reported"] == 0
    assert telemetry["writes_under_data"] == 2


def test_summary_pins_input_sha256s(summary) -> None:
    for key in ("density_v01", "local_observations", "local_coverage_summary"):
        digest = summary["inputs"][key]["sha256"]
        assert isinstance(digest, str) and len(digest) == 64


def test_summary_output_digests_match_the_committed_files(summary) -> None:
    import hashlib

    table_digest = hashlib.sha256(DEFAULT_TABLE.read_bytes()).hexdigest()
    assert summary["outputs"]["table"]["sha256"] == table_digest == EXPECTED_TABLE_SHA256
    assert summary["outputs"]["table"]["rows"] == EXPECTED_TABLE_ROWS
    if RAW_LAYER_PRESENT:
        raw_digest = hashlib.sha256(DEFAULT_RAW.read_bytes()).hexdigest()
        assert summary["outputs"]["raw"]["sha256"] == raw_digest == EXPECTED_RAW_SHA256
        assert summary["outputs"]["raw"]["rows"] == EXPECTED_RAW_ROWS


def test_frozen_viscosity_v01_is_untouched() -> None:
    import hashlib

    digest = hashlib.sha256((REPOSITORY_ROOT / "data" / "viscosity_v01.csv").read_bytes()).hexdigest()
    assert digest == EXPECTED_V01_SHA256


# --- criteria recomputed from the committed artifacts ----------------------------------


@requires_raw_layer
def test_criteria_recompute_and_match_the_summary(summary) -> None:
    table_rows = read_csv_rows(DEFAULT_TABLE)
    raw_rows = read_csv_rows(DEFAULT_RAW)
    ledger = ledger_from_raw(raw_rows)
    assert ledger == summary["value_layer"]["ledger"]
    assert len(raw_rows) == summary["value_layer"]["total_named_viscosity_rows"]

    local_rows = [
        row
        for row in read_csv_rows(DEFAULT_LOCAL_OBS)
        if (row.get("property_name") or "").strip() == PA_S_PROPERTY
    ]
    reconciler = reconcile_local_pa_s(raw_rows, local_rows)
    rebuilt = main_rows_from_raw(raw_rows, matched_row_keys=reconciler["matched_row_keys"])
    rebuilt += main_rows_from_unfreeze(summary["criterion_c_unfreeze"])
    rebuilt = sorted(
        rebuilt,
        key=lambda item: (
            item["source_doi"],
            item["thermoml_file"],
            int(item["source_row_index"] or "0"),
            item["value_origin"],
        ),
    )
    assert len(rebuilt) == len(table_rows)
    for index, (rebuilt_row, committed_row) in enumerate(zip(rebuilt, table_rows)):
        expected = {column: rebuilt_row.get(column, "") for column in TABLE_COLUMNS}
        expected["record_id"] = str(index)
        assert expected == committed_row


@requires_raw_layer
def test_row_reconciliation_recomputes_to_all_matched(summary) -> None:
    raw_rows = read_csv_rows(DEFAULT_RAW)
    local_rows = [
        row
        for row in read_csv_rows(DEFAULT_LOCAL_OBS)
        if (row.get("property_name") or "").strip() == PA_S_PROPERTY
    ]
    assert len(local_rows) == EXPECTED_LOCAL_PA_S_ROWS
    recomputed = reconcile_local_pa_s(raw_rows, local_rows)
    assert recomputed["local_rows"] == EXPECTED_LOCAL_PA_S_ROWS
    assert recomputed["matched_local_rows"] == EXPECTED_LOCAL_PA_S_ROWS
    assert recomputed["unmatched_local_rows"] == 0
    assert summary["criterion_e_row_reconciliation"]["averaging_applied"] is False


def test_local_coverage_dois_are_all_inside_the_online_union(summary) -> None:
    source = load_local_doi_source(DEFAULT_LOCAL_COVERAGE)
    assert len(source["dois"]) == EXPECTED_LOCAL_DOIS
    online = set(summary["dataset"]["doi_union"])
    assert set(source["dois"]) <= online
    assert summary["criterion_b_local_subset"]["hit_count"] == EXPECTED_LOCAL_DOIS


def test_unfreeze_metric_recomputes_from_the_committed_artifacts(summary) -> None:
    kinematic_rows = [
        row
        for row in read_csv_rows(DEFAULT_LOCAL_OBS)
        if (row.get("property_name") or "").strip() == KINEMATIC_PROPERTY
    ]
    assert len(kinematic_rows) == EXPECTED_LOCAL_KINEMATIC_ROWS
    recomputed = pair_kinematic_rows(kinematic_rows, read_csv_rows(DEFAULT_DENSITY))
    assert recomputed["exact_rows"] == EXPECTED_LOCAL_KINEMATIC_ROWS
    assert recomputed["nearest_rows"] == EXPECTED_LOCAL_KINEMATIC_ROWS
    assert recomputed["converted_rows"] == EXPECTED_LOCAL_KINEMATIC_ROWS
    assert recomputed["pooled_rows"] == EXPECTED_KINEMATIC_POOLED_ROWS
    assert summary["criterion_c_unfreeze"]["nearest_rows"] == EXPECTED_LOCAL_KINEMATIC_ROWS
    assert summary["criterion_c_unfreeze"]["pooled_rows"] == EXPECTED_KINEMATIC_POOLED_ROWS


def test_every_pooled_kinematic_row_carries_the_conversion_provenance(summary) -> None:
    pooled = [
        entry
        for entry in summary["criterion_c_unfreeze"]["per_row"]
        if entry["pooled_into_main_table"]
    ]
    assert len(pooled) == EXPECTED_KINEMATIC_POOLED_ROWS
    for entry in pooled:
        assert entry["density_kg_m3"]
        assert entry["density_source_doi"]
        assert entry["density_thermoml_file"]
        assert entry["density_T_K"]
        assert float(entry["delta_t_k"]) <= summary["criterion_c_unfreeze"]["nearest_tolerance_k"]


def test_main_table_marks_duplicates_without_averaging() -> None:
    rows = read_csv_rows(DEFAULT_TABLE)
    duplicated = [row for row in rows if row["duplicate_of_local"] == "true"]
    assert len(duplicated) == 483
    assert all(row["source_priority"] == "online_duplicate_of_local" for row in duplicated)
    converted = [row for row in rows if row["value_origin"] == "kinematic_converted"]
    assert len(converted) == EXPECTED_KINEMATIC_CONVERTED_ROWS
    assert all(row["source_priority"] == "local_kinematic_unfrozen" for row in converted)


def test_report_is_the_byte_exact_render_of_the_summary(summary, report_text) -> None:
    assert report_text == render_report(summary)


def test_wording_guard_passes_on_the_committed_report(prereg, summary, report_text) -> None:
    assert guard_violations(prereg, report_text, summary) == []


# --- unit-level contracts --------------------------------------------------------------


def test_api_url_zero_bases_the_page_number() -> None:
    url = api_url(PA_S_QUERY, PAGE_SIZE, FIRST_PAGE_NUM)
    assert "pageNum=0" in url and "pageSize=100" in url
    assert "%22Viscosity%2C+Pa%2As%22" in url
    kinematic_url = api_url(KINEMATIC_QUERY, PAGE_SIZE, FIRST_PAGE_NUM)
    assert "pageNum=0" in kinematic_url
    assert "%22Kinematic+viscosity%2C+m2%2Fs%22" in kinematic_url


def test_xml_cache_paths_keep_the_doi_slashes_out_of_the_filename(tmp_path) -> None:
    payload, marker = xml_cache_paths(tmp_path, "10.1000/alpha")
    assert payload.name == "10.1000__alpha.xml"
    assert marker.name == "10.1000__alpha.xml.url"
    assert xml_url("10.1000/alpha") == "https://trc.nist.gov/ThermoML/10.1000/alpha.xml"


def _base_row(**overrides: str) -> dict[str, str]:
    row = {
        "primary_compound_inchi_key": METHANOL_KEY,
        "primary_compound_inchi": METHANOL_INCHI,
        "primary_compound_name": "methanol",
        "temperature_value": "298.15",
        "property_name": PA_S_PROPERTY,
        "property_value": "0.00059",
        "property_unit": "Pa*s",
        "property_uncertainty": "",
        "property_uncertainty_kind": "",
        "phase": "Liquid",
        "method_name": "",
        "constraints_json": '[{"name": "Pressure", "unit": "kPa", "value": "101.325"}]',
        "doi": PA_S_DOI,
        "source_file": "x.xml",
        "source_row_index": "0",
        "component_count": "1",
    }
    row.update(overrides)
    return row


def test_unit_table_normalizes_centipoise_and_millimetre_squared_per_second() -> None:
    assert PA_S_UNIT_TO_PA_S["cP"] == 0.001
    projected = project_row(_base_row(property_value="0.59", property_unit="cP"), inchi_cache={})
    assert projected["property_value_si"] == "0.00059"
    assert projected["quality_flag"] == "accepted"
    assert projected["pressure_kPa"] == "101.325"

    kinematic = project_row(
        _base_row(
            property_name=KINEMATIC_PROPERTY,
            property_value="0.59",
            property_unit="mm2/s",
        ),
        inchi_cache={},
    )
    assert kinematic["property_value_si"] == "5.9e-07"
    assert kinematic["si_unit"] == "m2/s"
    assert kinematic["quality_flag"] == "accepted"


def test_unit_outside_the_table_is_rejected_not_converted() -> None:
    projected = project_row(_base_row(property_unit="lbm/(ft*s)"), inchi_cache={})
    assert projected["quality_flag"] == "unit_rejected"
    assert projected["property_value_si"] == ""
    assert projected["unit_conversion_factor"] == ""


def test_temperature_and_value_guards() -> None:
    hot = project_row(_base_row(temperature_value="1200"), inchi_cache={})
    assert hot["quality_flag"] == "temperature_rejected"
    cold = project_row(_base_row(temperature_value="50"), inchi_cache={})
    assert cold["quality_flag"] == "temperature_rejected"
    negative = project_row(_base_row(property_value="-1e-5"), inchi_cache={})
    assert negative["quality_flag"] == "value_rejected"
    absurd = project_row(_base_row(property_value="99999"), inchi_cache={})
    assert absurd["quality_flag"] == "value_rejected"


def test_multi_component_rows_are_deferred_not_pooled() -> None:
    projected = project_row(_base_row(component_count="2"), inchi_cache={})
    assert projected["quality_flag"] == "accepted"
    assert projected["role"] == "multi_component_deferred"
    ledger = ledger_from_raw([projected])
    assert ledger["accepted_pure_rows"] == 0
    assert ledger["multi_component_deferred_rows"] == 1
    assert sum(ledger.values()) == 1


def test_pairing_never_extrapolates_beyond_the_tolerance() -> None:
    kinematic = [
        {
            "inchikey": METHANOL_KEY,
            "name": "methanol",
            "T_K": "298.15",
            "viscosity_kinematic_m2_s": "1e-6",
            "property_name": KINEMATIC_PROPERTY,
            "n_components": "1",
            "source_doi": "d",
            "thermoml_file": "f",
            "source_row_index": "0",
        },
        {
            "inchikey": METHANOL_KEY,
            "name": "methanol",
            "T_K": "400.0",
            "viscosity_kinematic_m2_s": "1e-6",
            "property_name": KINEMATIC_PROPERTY,
            "n_components": "1",
            "source_doi": "d",
            "thermoml_file": "f",
            "source_row_index": "1",
        },
    ]
    density = [
        {"inchikey": METHANOL_KEY, "T_K": "298.15", "density_kg_m3": "786.6", "source_doi": "d2", "thermoml_file": "d.xml", "source_row_index": "0"},
        {"inchikey": METHANOL_KEY, "T_K": "308.15", "density_kg_m3": "780.1", "source_doi": "d2", "thermoml_file": "d.xml", "source_row_index": "1"},
    ]
    pairing = pair_kinematic_rows(kinematic, density)
    assert pairing["exact_rows"] == 1
    assert pairing["nearest_rows"] == 1
    assert pairing["converted_rows"] == 1
    assert pairing["per_row"][0]["converted_pa_s"] == "0.0007866"
    assert pairing["per_row"][1]["nearest"] is False


def test_request_budget_refuses_to_overspend() -> None:
    budget = RequestBudget(limit=1)
    budget.spend()
    with pytest.raises(BudgetExhausted):
        budget.spend()


def test_temperature_distribution_counts_every_named_row() -> None:
    rows = [{"T_K": "298.15"}, {"T_K": "250"}, {"T_K": "400"}]
    bins = temperature_distribution(rows)
    assert sum(entry["count"] for entry in bins) == len(rows)


def test_stable_view_drops_only_the_timestamp_and_provenance(summary) -> None:
    stable = stable_view(summary)
    assert "generated_at_utc" not in stable
    assert "run_provenance" not in stable
    assert set(stable) == set(summary) - {"generated_at_utc", "run_provenance"}


def test_pressure_only_reads_pressure_constraints() -> None:
    assert pressure_kpa('[{"name": "Temperature", "unit": "K", "value": "298.15"}]') == ""
    assert pressure_kpa('[{"name": "Pressure", "unit": "MPa", "value": "1"}]') == "1000"
    assert pressure_kpa("not json") == ""


def test_catalog_page_descriptor_flags_pure_property() -> None:
    payload = {
        "size": 1,
        "results": [
            {
                "id": "20.5000.trc.thermoml/" + PA_S_DOI,
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
                                            "TransportProp": {"ePropName": PA_S_PROPERTY}
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
    descriptor = catalog_page_descriptor(payload, PA_S_PROPERTY)
    assert descriptor["dois"] == [PA_S_DOI]
    assert descriptor["pure_property_dois"] == [PA_S_DOI]
    assert descriptor["structured_hit_dois"] == [PA_S_DOI]
    assert descriptor["keys"] == {METHANOL_KEY}
    kinematic_descriptor = catalog_page_descriptor(payload, KINEMATIC_PROPERTY)
    assert kinematic_descriptor["pure_property_dois"] == []
    assert kinematic_descriptor["structured_hit_dois"] == []


# --- synthetic end-to-end: compose + --check without any network ----------------------


def _synthetic_record(doi: str, property_name: str) -> dict[str, Any]:
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
                                    "TransportProp": {"ePropName": property_name}
                                }
                            },
                        }
                    ],
                }
            ],
            "data_summary": {"pure": {"TransportProp": {property_name: {"data_points": 2}}}},
        },
    }


def _synthetic_http_get(calls: list[str]):
    def http_get(url: str, *, timeout: int = 120) -> HttpResponse:
        calls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        asked = query["query"][0]
        if asked == "*":
            body = json.dumps({"pageNum": 0, "pageSize": 1, "size": 5, "results": []}).encode("utf-8")
            return HttpResponse(200, body, url)
        if asked == PA_S_QUERY:
            payload = {
                "pageNum": 0,
                "pageSize": PAGE_SIZE,
                "size": 1,
                "results": [_synthetic_record(PA_S_DOI, PA_S_PROPERTY)],
            }
            return HttpResponse(200, json.dumps(payload).encode("utf-8"), url)
        payload = {
            "pageNum": 0,
            "pageSize": PAGE_SIZE,
            "size": 1,
            "results": [_synthetic_record(KINEMATIC_DOI, KINEMATIC_PROPERTY)],
        }
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
        root / "local_obs.csv",
        [
            "inchikey",
            "name",
            "T_K",
            "viscosity_Pa_s",
            "viscosity_kinematic_m2_s",
            "property_name",
            "n_components",
            "source_doi",
            "thermoml_file",
            "source_row_index",
        ],
        [
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "298.15",
                "viscosity_Pa_s": "0.00059",
                "viscosity_kinematic_m2_s": "",
                "property_name": PA_S_PROPERTY,
                "n_components": "1",
                "source_doi": PA_S_DOI,
                "thermoml_file": "a.xml",
                "source_row_index": "0",
            },
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "308.15",
                "viscosity_Pa_s": "0.00055",
                "viscosity_kinematic_m2_s": "",
                "property_name": PA_S_PROPERTY,
                "n_components": "1",
                "source_doi": PA_S_DOI,
                "thermoml_file": "a.xml",
                "source_row_index": "1",
            },
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "298.15",
                "viscosity_Pa_s": "",
                "viscosity_kinematic_m2_s": "1.0e-6",
                "property_name": KINEMATIC_PROPERTY,
                "n_components": "1",
                "source_doi": KINEMATIC_DOI,
                "thermoml_file": "b.xml",
                "source_row_index": "0",
            },
            {
                "inchikey": METHANOL_KEY,
                "name": "methanol",
                "T_K": "308.15",
                "viscosity_Pa_s": "",
                "viscosity_kinematic_m2_s": "0.9e-6",
                "property_name": KINEMATIC_PROPERTY,
                "n_components": "1",
                "source_doi": KINEMATIC_DOI,
                "thermoml_file": "b.xml",
                "source_row_index": "1",
            },
        ],
    )
    write_rows(
        root / "density.csv",
        ["inchikey", "T_K", "density_kg_m3", "source_doi", "thermoml_file", "source_row_index"],
        [
            {
                "inchikey": METHANOL_KEY,
                "T_K": "298.15",
                "density_kg_m3": "786.6",
                "source_doi": "10.1000/d",
                "thermoml_file": "d.xml",
                "source_row_index": "0",
            },
            {
                "inchikey": METHANOL_KEY,
                "T_K": "308.15",
                "density_kg_m3": "780.1",
                "source_doi": "10.1000/d",
                "thermoml_file": "d.xml",
                "source_row_index": "1",
            },
        ],
    )
    coverage = {
        "viscosity_files": 2,
        "files_with_viscosity": [
            {"thermoml_file": "a.xml", "viscosity_rows": 2, "source_doi": PA_S_DOI},
            {"thermoml_file": "b.xml", "viscosity_rows": 2, "source_doi": KINEMATIC_DOI},
        ],
    }
    (root / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    prereg["frozen_expectations"].update(
        {
            "total_records_size": 5,
            "pa_s_slice_size": 1,
            "pa_s_slice_pages": 1,
            "kinematic_slice_size": 1,
            "kinematic_slice_pages": 1,
            "local_viscosity_dois": 2,
            "local_pa_s_rows": 2,
            "local_kinematic_rows": 2,
            "local_kinematic_keys": 1,
        }
    )
    prereg_path = root / "prereg.json"
    prereg_path.write_text(
        json.dumps(prereg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    xml_cache = root / "xml"
    xml_cache.mkdir(parents=True, exist_ok=True)
    for doi, property_name, value_a, value_b in (
        (PA_S_DOI, PA_S_PROPERTY, "0.00059", "0.00055"),
        (KINEMATIC_DOI, KINEMATIC_PROPERTY, "1.0e-6", "0.9e-6"),
    ):
        payload, marker = xml_cache_paths(xml_cache, doi)
        payload.write_text(
            FAKE_XML_TEMPLATE.format(
                doi=doi,
                inchi=METHANOL_INCHI,
                key=METHANOL_KEY,
                property_name=property_name,
                value_a=value_a,
                value_b=value_b,
            ),
            encoding="utf-8",
            newline="\n",
        )
        marker.write_text(xml_url(doi) + "\n", encoding="utf-8", newline="\n")
    return {
        "prereg": prereg_path,
        "local_obs": root / "local_obs.csv",
        "local_coverage": root / "coverage.json",
        "density": root / "density.csv",
        "catalog_cache": root / "catalog",
        "xml_cache": xml_cache,
        "summary": root / "summary.json",
        "report": root / "report.md",
        "table": root / "viscosity_v02.csv",
        "raw": root / "viscosity_v02_raw.csv",
    }


def test_synthetic_end_to_end_then_offline_check(tmp_path) -> None:
    paths = _write_synthetic_workspace(tmp_path)
    calls: list[str] = []
    http_get = _synthetic_http_get(calls)

    import probes.build_viscosity_v02 as module

    original = module.default_http_get
    module.default_http_get = http_get
    argv = [
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
        "--density",
        str(paths["density"]),
        "--local-obs",
        str(paths["local_obs"]),
        "--local-coverage",
        str(paths["local_coverage"]),
    ]
    try:
        assert module.main(argv) == 0
        # the XMLs were already cached, so the only network calls are catalog pages
        assert all("ThermoML-API" in url for url in calls)
        summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
        assert summary["criterion_a_online_slice"]["passed"] is True
        assert summary["criterion_b_local_subset"]["passed"] is True
        assert summary["criterion_c_unit_honesty"]["passed"] is True
        assert summary["criterion_d_basis_honesty"]["passed"] is True
        assert summary["run_provenance"]["value_layer_source"] == "thermoml_xml"
        assert summary["criterion_c_unfreeze"]["local_rows"] == 2
        assert summary["criterion_c_unfreeze"]["nearest_rows"] == 2
        assert summary["criterion_c_unfreeze"]["pooled_rows"] == 2
        assert summary["criterion_e_row_reconciliation"]["matched_local_rows"] == 2
        assert "group_overlap == 0" in summary["group_overlap_audit"]["assertion"]
        # only one compound in the synthetic corpus, so the split degrades instead of leaking
        assert summary["group_overlap_audit"]["assertion_passed"] is False
        # main table = 2 measured Pa*s rows + 2 rho-converted kinematic rows
        assert summary["criterion_d_basis_honesty"]["dual_basis_counts"]["viscosity_v02_rows"] == 4
        # offline --check must reproduce the just-written artifacts byte for byte
        assert module.main(["--check", *argv[1:]]) == 0
    finally:
        module.default_http_get = original
