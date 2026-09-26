"""Unit tests for the KPI 15+14 shortlist vs our-funnel cross-run probe.

The pinned values below are the ones the frozen pre-registration
(probes/kpi_funnel_cross_run_prereg.json) committed to before the run, plus what
the run then produced. They are written out literally rather than recomputed, so
a silent edit to the identity table, the summary or the report shows up as a
failure instead of quietly re-baselining.

Batt-P30K is not in version control (data/raw/* is ignored), so the tests that
re-derive the funnel are skipped when that file is absent. No test touches the
network: the offline path is exercised exclusively.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.kpi_funnel_cross_run import (
    BATT_P30K_H5,
    DEFAULT_IDENTITY_CSV,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    IDENTITY_COLUMNS,
    _stable_view,
    read_csv_rows,
    render_report,
    resolve_identities,
    run,
    sha256_file,
)

SHORTLIST_PATH = REPOSITORY_ROOT / "data" / "reference" / "kpi_15_14_shortlists.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "kpi_funnel_cross_run_prereg.json"

EXPECTED_PREREG_SHA256 = "42e3fa658d903623fefefc9da6733619008ff1d1b1af109342626330886a12ee"
EXPECTED_PREREG_LOCKED_AT_UTC = "2026-09-26T09:11:42Z"
EXPECTED_IDENTITY_SHA256 = "29d7ebab031826b09b8a28c5fa2cf1576d5e4ba6c3f97ecce9afe5989e3dc976"

# The funnel replay on Batt-P30K.  S1 removes nothing: the battery pool carries
# no -OH/-COOH and stays under both size gates.
EXPECTED_FUNNEL = {"S0": 29519, "S1": 29519, "S2": 22249, "S3": 11709}
EXPECTED_INTERSECTIONS = {
    "vs_batt_p30k": 13,
    "vs_roster_314": 2,
    "vs_epsilon_v03": 2,
    "vs_epsilon_v11plus": 1,
}
EXPECTED_ELEMENT_WHITELIST = ["C", "N", "O"]

# The 13 shortlist rows that Batt-P30K also holds.  Pinned as identities, not as
# names, so a row that resolves to a different structure cannot slip through.
EXPECTED_BATT_HITS = (
    "YEJRWHAVMIAJKC-UHFFFAOYSA-N",  # 15-1  gamma-butyrolactone (96-48-0)
    "RUOJZAUFBMNUDX-UHFFFAOYSA-N",  # 15-2  propylene carbonate
    "PUEFXLJYTSRTGI-UHFFFAOYSA-N",  # 15-3
    "LWLOKSXSAUHTJO-UHFFFAOYSA-N",  # 15-4
    "ZZXUZKXVROWEIF-UHFFFAOYSA-N",  # 15-5
    "OYEXEQFKIPJKJK-UHFFFAOYSA-N",  # 15-6
    "GDCJAPJJFZWILF-UHFFFAOYSA-N",  # 15-8
    "WTQMTUQXPWPJIT-UHFFFAOYSA-N",  # 15-10
    "FPPLREPCQJZDAQ-UHFFFAOYSA-N",  # 15-12
    "AWVNJBFNHGQUQU-UHFFFAOYSA-N",  # 15-14
    "ZAGOKQGYDCMNPT-UHFFFAOYSA-N",  # 15-15
    "ADQZRFNEMNNSEH-UHFFFAOYSA-N",  # 14-3
    "IDLWDEPIHMNMIO-UHFFFAOYSA-N",  # 14-11
)


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    return json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report() -> str:
    return DEFAULT_REPORT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def offline_rerun() -> tuple[str, str, dict[str, Any], str]:
    if not BATT_P30K_H5.is_file():
        pytest.skip("Batt-P30K.h5 is not in version control (data/raw/* is ignored)")
    return run(online=False, refresh=False)


def test_prereg_is_byte_frozen_and_locked_before_the_run() -> None:
    assert sha256_file(PREREG_PATH) == EXPECTED_PREREG_SHA256
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    assert prereg["locked_at_utc"] == EXPECTED_PREREG_LOCKED_AT_UTC
    assert prereg["status"] == "locked_before_run"


def test_prereg_pins_three_criteria_and_the_forbidden_list() -> None:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    criteria = prereg["pre_registered_criteria"]
    assert set(criteria) == {"A_self_consistency", "B_identity", "C_intersection"}
    assert criteria["A_self_consistency"]["statement"].endswith("允许违反数 = 0。")
    assert len(prereg["forbidden"]) == 7
    by_id = {stage["id"]: stage for stage in prereg["stages"]}
    assert [stage["id"] for stage in prereg["stages"]] == ["S0", "S1", "S2", "S3", "S4"]
    assert by_id["S4"]["registered_as"] == "gap"
    assert by_id["S4"]["runnable"] is False
    assert by_id["S3"]["caveat"]


def test_summary_carries_the_same_prereg_digest_it_was_run_against(summary) -> None:
    assert summary["prereg"]["sha256"] == EXPECTED_PREREG_SHA256
    assert summary["prereg"]["locked_at_utc"] == EXPECTED_PREREG_LOCKED_AT_UTC


def test_identity_table_is_utf8_lf_without_bom() -> None:
    raw = DEFAULT_IDENTITY_CSV.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert sha256_file(DEFAULT_IDENTITY_CSV) == EXPECTED_IDENTITY_SHA256


def test_identity_table_header_is_the_declared_schema() -> None:
    with DEFAULT_IDENTITY_CSV.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == IDENTITY_COLUMNS


def test_identity_table_has_29_rows_with_29_distinct_inchikeys() -> None:
    rows = read_csv_rows(DEFAULT_IDENTITY_CSV)
    assert len(rows) == 29
    keys = [row["inchikey"] for row in rows]
    assert all(keys)
    assert len(set(keys)) == 29


def test_identity_routes_are_14_smiles_and_15_cas(summary) -> None:
    routes = summary["identity_resolution"]["by_route"]
    assert routes == {"smiles_rdkit": 14, "cas_pubchem": 15}
    assert summary["identity_resolution"]["resolved"] == 29
    assert summary["identity_resolution"]["unresolved"] == []


def test_every_shortlist_row_carries_exactly_one_identifier() -> None:
    for row in read_csv_rows(SHORTLIST_PATH):
        filled = [bool(row["cas"]), bool(row["smiles"])]
        assert sum(filled) == 1, row


def test_offline_resolution_reproduces_all_29_rows_without_network() -> None:
    records, meta = resolve_identities(read_csv_rows(SHORTLIST_PATH), online=False, refresh=False)
    assert meta["resolved"] == 29
    assert meta["unresolved"] == []
    assert meta["drift_vs_committed_table"] == []
    assert all(record["resolved_from"] for record in records)
    assert {record["resolved_from"] for record in records} == {
        "rdkit_from_shortlist_smiles",
        "pubchem_pug_rest",
    }


def test_summary_declares_no_model_was_fitted_and_no_r2_exists(summary) -> None:
    assert summary["model_fitting"]["fitted_any_model"] is False
    assert summary["model_fitting"]["r2_reported"] is False
    assert "r2" not in json.dumps(summary["funnel_ours"], ensure_ascii=False).lower()


def test_summary_forbidden_compliance_is_false_on_every_line(summary) -> None:
    compliance = summary["forbidden_compliance"]
    assert compliance
    assert set(compliance.values()) == {False}


def test_summary_registers_s4_as_a_gap_rather_than_a_result(summary) -> None:
    s4 = [stage for stage in summary["funnel_ours"] if stage["id"] == "S4"]
    assert len(s4) == 1
    assert s4[0]["registered_as"] == "gap"
    assert s4[0]["survivors"] is None
    assert s4[0]["survival_rate"] is None


def test_summary_states_that_the_kpi_cascade_was_not_recomputed(summary) -> None:
    assert summary["funnel_kpi_declared"]["recomputed_by_this_project"] is False
    assert summary["pools"]["kpi"]["available_locally"] is False
    assert "pool_different" in summary["pools"]["comparability"]


def test_declared_funnel_counts_are_the_pinned_ones(summary) -> None:
    observed = {
        stage["id"]: stage["survivors"]
        for stage in summary["funnel_ours"]
        if stage.get("survivors") is not None
    }
    assert observed == EXPECTED_FUNNEL
    assert summary["pools"]["ours"]["n_measured_this_round"] == EXPECTED_FUNNEL["S0"]
    assert summary["pools"]["ours"]["n_declared"] == 29519


def test_declared_intersections_are_the_pinned_ones(summary) -> None:
    block = summary["criterion_c_intersection"]
    observed = {key: block[key]["n"] for key in EXPECTED_INTERSECTIONS}
    assert observed == EXPECTED_INTERSECTIONS


def test_the_batt_hits_are_the_pinned_identities(summary) -> None:
    members = summary["criterion_c_intersection"]["vs_batt_p30k"]["members"]
    keys = tuple(sorted(member["inchikey"] for member in members))
    assert keys == tuple(sorted(EXPECTED_BATT_HITS))
    assert len(keys) == EXPECTED_INTERSECTIONS["vs_batt_p30k"]


def test_hits_carry_batt_p30k_dft_labels_including_the_dipole(summary) -> None:
    members = summary["criterion_c_intersection"]["vs_batt_p30k"]["members"]
    for member in members:
        labels = member["batt_p30k_labels"]
        for field in ("dipole_norm", "homo", "lumo", "gap", "ip", "ea"):
            assert isinstance(labels[field], float), (member["row_key"], field)


def test_element_whitelist_is_declared_as_derived_not_declared(summary) -> None:
    block = summary["element_whitelist"]
    assert block["status"] == "derived_not_declared"
    assert block["elements"] == EXPECTED_ELEMENT_WHITELIST
    assert block["derived_from_rows"] == 29
    assert block["caveat"]


def test_property_crosscheck_is_pinned_and_labelled_as_model_versus_experiment(summary, report) -> None:
    crosscheck = summary["property_crosscheck"]
    assert crosscheck["n_compared"] == 6
    assert crosscheck["median_abs_delta_k"] == 0.05
    assert crosscheck["max_abs_delta_k"] == 1.42
    assert {item["property"] for item in crosscheck["comparisons"]} == {
        "melting_point",
        "boiling_point",
        "flash_point",
    }
    assert "论文模型的预测值" in report


def test_report_is_exactly_render_report_of_the_summary(summary, report) -> None:
    assert report == render_report(summary)


def test_summary_and_report_are_utf8_lf_without_bom() -> None:
    for path in (DEFAULT_SUMMARY, DEFAULT_REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        assert b"\r" not in raw, path


def test_report_refuses_absolute_counts_between_the_two_pools(report) -> None:
    assert "不允许比绝对计数" in report
    assert "不允许把比例差异单方面归因于漏斗" in report


def test_report_states_the_usage_boundary(report) -> None:
    assert "redistributable=false" in report
    assert "永进不了 data/ 冻结表" in report


def test_offline_rerun_reproduces_the_committed_artefacts(offline_rerun, summary, report) -> None:
    identity_text, summary_text, recomputed, report_text = offline_rerun
    assert identity_text == DEFAULT_IDENTITY_CSV.read_text(encoding="utf-8")
    assert report_text == report
    assert _stable_view(recomputed) == _stable_view(summary)
    assert json.loads(summary_text)["task"] == "kpi_funnel_cross_run"


def test_offline_rerun_makes_no_network_call(offline_rerun) -> None:
    telemetry = offline_rerun[2]["run_telemetry"]
    assert telemetry["run_mode"] == "offline"
    assert telemetry["network_calls"] == 0
    assert telemetry["cache_hits"] == 0


def test_stable_view_drops_the_volatile_fields(summary) -> None:
    stable = _stable_view(summary)
    assert "generated_at_utc" not in stable
    assert "run_telemetry" not in stable
    assert "generated_at_utc" in summary
    assert "run_telemetry" in summary
