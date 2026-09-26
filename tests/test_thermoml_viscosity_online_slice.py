"""Offline unit tests for the T1 online ThermoML viscosity slice check.

Everything here runs with zero network access. The pinned values below are what the
frozen pre-registration (probes/thermoml_viscosity_online_slice_prereg.json) committed
to before the run, plus what the run then produced. They are written out literally
rather than recomputed, so a silent edit to the pre-registration, the summary or the
report shows up as a failure instead of quietly re-baselining.

The raw /ThermoML-API/objects responses live in data/external/thermoml_api/, which is
gitignored, so a clean clone has none of them. No test needs them: --check is asserted
to pass both with the raw cache present and with it absent (the committed summary then
carries the online manifest). No test touches the network.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.thermoml_viscosity_online_slice import (
    API_BASE,
    DEFAULT_CACHE_DIR,
    DEFAULT_PREREG,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    FIRST_PAGE_NUM,
    LOCAL_COVERAGE_SUMMARY,
    PAGE_SIZE,
    REQUEST_BUDGET_LIMIT,
    TOTAL_RECORDS_QUERY,
    USER_AGENT,
    BudgetExhausted,
    RequestBudget,
    api_url,
    cache_paths,
    compose,
    evaluate_criterion_a,
    evaluate_criterion_b,
    guard_violations,
    load_local_viscosity_dois,
    main,
    prose_guard_violations,
    record_doi,
    render_report,
    sha256_file,
    stable_view,
    structured_property_names,
    summarize_slice,
)

EXPECTED_PREREG_SHA256 = "f62ad8eca0bea4714cbfad63e7af028c7b3c202d3e899675981289970feb4389"
EXPECTED_LOCKED_AT_UTC = "2026-09-26T10:17:13Z"
EXPECTED_SLICES_SHA256 = "52aa8d68c69438b0d3a2727f7ba66dbe148083a648cdd2b1b88904409ae2a9be"

# Criterion A: the three online record counts, measured, never row counts.
EXPECTED_TOTAL_RECORDS = 11923
EXPECTED_PA_S_RECORDS = 1690
EXPECTED_KINEMATIC_RECORDS = 70
EXPECTED_PA_S_PAGES = 17
EXPECTED_KINEMATIC_PAGES = 1

# Criterion B: every local viscosity XML DOI is inside the online slice union.
EXPECTED_LOCAL_DOIS = 29
EXPECTED_LOCAL_MISSES = 0
EXPECTED_ONLINE_UNION_DOIS = 1743

# Criterion C: coverage is only ever stated on the record basis.
COVERAGE_NUMERATOR = 29
COVERAGE_DENOMINATOR = 1690

PA_S_SLICE = "viscosity_pa_s"
KINEMATIC_SLICE = "kinematic_viscosity"


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    return json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    return json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report_text() -> str:
    return DEFAULT_REPORT.read_text(encoding="utf-8")


def slice_by_id(summary: dict[str, Any], slice_id: str) -> dict[str, Any]:
    return next(item for item in summary["dataset"]["slices"] if item["id"] == slice_id)


def synthetic_dataset(*, pa_s_count: int, pa_s_collected: int, kinematic_count: int = 70) -> dict[str, Any]:
    def entry(slice_id: str, query: str, size: int, collected: int) -> dict[str, Any]:
        dois = [f"10.1000/synthetic-{index:05d}" for index in range(collected)]
        return {
            "id": slice_id,
            "query": query,
            "property_name": query.strip('"'),
            "page_size": PAGE_SIZE,
            "size_records": size,
            "pages_fetched": 1,
            "records_collected": collected,
            "records_without_doi": 0,
            "unique_dois": len(set(dois)),
            "structured_property_hit_records": collected,
            "phrase_only_records": 0,
            "structured_property_hit_dois": dois,
            "phrase_only_dois": [],
            "dois": dois,
        }

    return {
        "total_records": {"query": TOTAL_RECORDS_QUERY, "size_records": EXPECTED_TOTAL_RECORDS},
        "slices": [
            entry(PA_S_SLICE, '"Viscosity, Pa*s"', pa_s_count, pa_s_collected),
            entry(KINEMATIC_SLICE, '"Kinematic viscosity, m2/s"', kinematic_count, kinematic_count),
        ],
    }


# --- pre-registration is byte-frozen and locked before the run ------------------------


def test_prereg_is_byte_frozen_and_locked_before_the_run() -> None:
    assert sha256_file(DEFAULT_PREREG) == EXPECTED_PREREG_SHA256


def test_prereg_declares_locked_before_run_and_the_three_criteria(prereg) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["locked_at_utc"] == EXPECTED_LOCKED_AT_UTC
    criteria = prereg["pre_registered_criteria"]
    assert set(criteria) == {
        "A_online_slice_reproduction_and_pagination",
        "B_local_subset_of_online",
        "C_unit_and_index_honesty",
    }
    for entry in criteria.values():
        assert entry["allowed_violations"] == 0
        assert entry["statement"]
        assert entry["threshold"]
        assert entry["machine_readable"]


def test_prereg_freezes_the_five_forbidden_statements(prereg) -> None:
    forbidden = prereg["forbidden"]
    assert len(forbidden) >= 10
    joined = " ".join(forbidden)
    for token in ("冒充数据行数", "phrase", "ePropName", "在线 = 本地", "不许拟合任何模型", "不产任何 R2 或 MAE"):
        assert token in joined
    assert "整个 NIST 全库" in joined or "NIST 全库" in joined


def test_prereg_zero_bases_the_page_number_and_records_the_recon_evidence(prereg) -> None:
    assert prereg["api"]["page_num_base"] == 0
    assert prereg["api"]["first_page_num"] == 0
    assert FIRST_PAGE_NUM == 0
    probe = prereg["recon_evidence"]["page_num_offset_probe"]
    assert probe["results_per_page_num"] == {"0": 20, "1": 20, "2": 20, "3": 10, "4": 0}
    assert probe["union_over_page_num_0_to_3"] == probe["size"] == 70


def test_prereg_pins_the_wording_guard_spec(prereg) -> None:
    guard = prereg["wording_guard"]
    assert guard["bare_number_tokens"] == ["11923", "1690"]
    assert guard["required_qualifier_any_of"] == ["记录", "records"]
    assert guard["forbidden_row_units"] == ["行", "rows"]
    assert guard["adjacency_window_chars"] == 6


# --- criterion A: the online record counts -------------------------------------------


def test_summary_carries_the_prereg_digest_it_was_run_against(summary) -> None:
    assert summary["prereg"]["sha256"] == EXPECTED_PREREG_SHA256
    assert summary["prereg"]["locked_at_utc"] == EXPECTED_LOCKED_AT_UTC
    assert summary["prereg"]["status"] == "locked_before_run"


def test_criterion_a_reproduces_the_three_online_record_counts(summary) -> None:
    criterion = summary["criterion_a_online_slice"]
    assert criterion["measured_sizes"] == {
        TOTAL_RECORDS_QUERY: EXPECTED_TOTAL_RECORDS,
        '"Viscosity, Pa*s"': EXPECTED_PA_S_RECORDS,
        '"Kinematic viscosity, m2/s"': EXPECTED_KINEMATIC_RECORDS,
    }
    assert criterion["expected_sizes"] == criterion["measured_sizes"]
    assert criterion["n_violations"] == EXPECTED_LOCAL_MISSES
    assert criterion["passed"] is True


def test_criterion_a_paginated_both_slices_to_the_last_record(summary) -> None:
    pagination = summary["criterion_a_online_slice"]["pagination"]
    assert pagination[PA_S_SLICE] == {
        "size_records": EXPECTED_PA_S_RECORDS,
        "records_collected": EXPECTED_PA_S_RECORDS,
        "pages_fetched": EXPECTED_PA_S_PAGES,
        "pagination_complete": True,
        "dois_unique": True,
    }
    assert pagination[KINEMATIC_SLICE] == {
        "size_records": EXPECTED_KINEMATIC_RECORDS,
        "records_collected": EXPECTED_KINEMATIC_RECORDS,
        "pages_fetched": EXPECTED_KINEMATIC_PAGES,
        "pagination_complete": True,
        "dois_unique": True,
    }


def test_a_synthetic_incomplete_slice_fails_criterion_a(prereg) -> None:
    dataset = synthetic_dataset(pa_s_count=EXPECTED_PA_S_RECORDS, pa_s_collected=EXPECTED_PA_S_RECORDS - 100)
    criterion = evaluate_criterion_a(dataset, prereg)
    assert criterion["passed"] is False
    assert criterion["n_violations"] == 1
    assert "分页不全" in criterion["violations"][0]


def test_a_wrong_online_size_fails_criterion_a(prereg) -> None:
    dataset = synthetic_dataset(pa_s_count=EXPECTED_PA_S_RECORDS, pa_s_collected=EXPECTED_PA_S_RECORDS)
    dataset["total_records"]["size_records"] = EXPECTED_TOTAL_RECORDS + 1
    criterion = evaluate_criterion_a(dataset, prereg)
    assert criterion["passed"] is False
    assert f"与预注册 {EXPECTED_TOTAL_RECORDS} 不符" in criterion["violations"][0]


def test_slices_sha256_pins_the_measured_doi_lists(summary) -> None:
    assert summary["digests"]["slices_sha256"] == EXPECTED_SLICES_SHA256


# --- criterion B: local is a subset of online ----------------------------------------


def test_criterion_b_finds_every_local_doi_online(summary) -> None:
    criterion = summary["criterion_b_local_subset"]
    assert criterion["local_doi_count"] == EXPECTED_LOCAL_DOIS
    assert len(criterion["per_doi"]) == EXPECTED_LOCAL_DOIS
    assert criterion["n_present"] == EXPECTED_LOCAL_DOIS
    assert criterion["n_misses"] == EXPECTED_LOCAL_MISSES
    assert criterion["misses"] == []
    assert criterion["online_union_dois"] == EXPECTED_ONLINE_UNION_DOIS
    assert criterion["passed"] is True


def test_criterion_b_matches_through_the_structured_property_not_the_phrase(summary) -> None:
    criterion = summary["criterion_b_local_subset"]
    assert criterion["n_structured"] == EXPECTED_LOCAL_DOIS
    assert criterion["n_phrase_only"] == 0
    assert all(item["match_kind"] == "structured_property" for item in criterion["per_doi"])
    # Two local files are kinematic-only: they must be found in the kinematic slice.
    kinematic_only = [
        item["doi"]
        for item in criterion["per_doi"]
        if item["matched_slices"] == [KINEMATIC_SLICE]
    ]
    assert kinematic_only == ["10.1016/j.fluid.2016.10.026", "10.1016/j.tca.2015.08.013"]


def test_criterion_b_lists_every_miss_instead_of_only_a_ratio(prereg) -> None:
    local = {
        "path": "synthetic",
        "entry_count": 2,
        "dois": ["10.1000/present", "10.1000/absent"],
    }
    dataset = synthetic_dataset(pa_s_count=EXPECTED_PA_S_RECORDS, pa_s_collected=1)
    dataset["slices"][0]["dois"] = ["10.1000/present"]
    dataset["slices"][0]["structured_property_hit_dois"] = ["10.1000/present"]
    dataset["slices"][1]["dois"] = []
    dataset["slices"][1]["structured_property_hit_dois"] = []
    criterion = evaluate_criterion_b(dataset, local, prereg)
    assert criterion["passed"] is False
    assert criterion["misses"] == ["10.1000/absent"]
    assert criterion["n_misses"] == 1
    assert len(criterion["per_doi"]) == 2


def test_local_doi_list_comes_from_the_committed_coverage_summary() -> None:
    local = load_local_viscosity_dois(LOCAL_COVERAGE_SUMMARY)
    assert local["entry_count"] == EXPECTED_LOCAL_DOIS
    assert len(local["dois"]) == EXPECTED_LOCAL_DOIS
    assert local["viscosity_files"] == EXPECTED_LOCAL_DOIS
    assert "10.1021/je800664z" in local["dois"]
    assert local["viscosity_rows"] > local["entry_count"]


# --- criterion C: unit and index honesty ---------------------------------------------


def test_criterion_c_records_are_not_rows_and_online_rows_are_unknown(summary) -> None:
    criterion = summary["criterion_c_unit_honesty"]
    assert criterion["size_unit"] == "record"
    assert criterion["online_row_count"] == "unknown"
    assert criterion["online_row_count_reason"]
    assert "data_points" in criterion["online_row_count_reason"]
    assert criterion["passed"] is True
    assert criterion["n_violations"] == 0


def test_criterion_c_reports_phrase_hits_and_structured_hits_separately(summary) -> None:
    per_slice = summary["criterion_c_unit_honesty"]["phrase_index_vs_structured_property"]
    assert per_slice["per_slice"][PA_S_SLICE] == {
        "size_records": EXPECTED_PA_S_RECORDS,
        "structured_property_hit_records": EXPECTED_PA_S_RECORDS,
        "phrase_only_records": 0,
        "structured_property_hit_dois": EXPECTED_PA_S_RECORDS,
        "phrase_only_dois": 0,
    }
    assert "ePropName" in per_slice["structured_field_path"]


def test_criterion_c_states_coverage_on_records_and_calls_rows_incomparable(summary) -> None:
    coverage = summary["criterion_c_unit_honesty"]["coverage"]
    record_basis = coverage["record_basis"]
    assert record_basis["unit"] == "record"
    assert record_basis["local_viscosity_files"] == COVERAGE_NUMERATOR
    assert record_basis["online_pa_s_records"] == COVERAGE_DENOMINATOR
    assert record_basis["ratio"] == pytest.approx(COVERAGE_NUMERATOR / COVERAGE_DENOMINATOR)
    assert coverage["row_basis"]["comparable"] is False
    assert coverage["row_basis"]["online_rows"] == "unknown"


# --- the wording guard ----------------------------------------------------------------


def test_wording_guard_rejects_a_bare_number_and_a_row_unit() -> None:
    violations = prose_guard_violations(
        "在线 Viscosity Pa*s 切片 1690 行全部命中。",
        tokens=["11923", "1690"],
        qualifiers=["记录", "records"],
        row_units=["行", "rows"],
        window=6,
    )
    assert violations
    assert all("1690" in item for item in violations)


def test_wording_guard_accepts_a_qualified_record_count() -> None:
    violations = prose_guard_violations(
        "在线 Viscosity Pa*s 切片 1690 条记录已分页抓全。",
        tokens=["11923", "1690"],
        qualifiers=["记录", "records"],
        row_units=["行", "rows"],
        window=6,
    )
    assert violations == []


def test_the_committed_report_and_summary_pass_the_wording_guard(prereg, summary, report_text) -> None:
    assert guard_violations(prereg, report_text, summary) == []
    assert "11923 行" not in report_text
    assert "1690 行" not in report_text


# --- the report is exactly render_report(summary) ------------------------------------


def test_report_is_render_report_of_the_committed_summary(summary, report_text) -> None:
    assert report_text == render_report(summary)
    assert report_text.endswith("\n")


def test_report_never_prints_a_timestamp_so_it_can_be_byte_reproduced(report_text, summary) -> None:
    assert summary["generated_at_utc"] not in report_text


def test_report_text_has_no_bom_and_no_crlf(report_text) -> None:
    raw = DEFAULT_REPORT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert raw.decode("utf-8") == report_text


def test_summary_json_is_utf8_lf_without_bom() -> None:
    raw = DEFAULT_SUMMARY.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    json.loads(raw.decode("utf-8"))


# --- --check is offline, byte-exact, and tamper-evident -------------------------------


def test_check_passes_offline_with_the_network_blocked(monkeypatch, tmp_path) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("--check 不许联网")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(
        "probes.thermoml_viscosity_online_slice.default_http_get", boom
    )
    # with the raw cache present (this machine) and absent (clean clone) alike
    for cache_dir in (DEFAULT_CACHE_DIR, tmp_path / "absent"):
        assert main(["--check", "--cache-dir", str(cache_dir)]) == 0


def test_check_never_spends_a_request(tmp_path) -> None:
    args = argparse.Namespace(
        prereg=DEFAULT_PREREG,
        summary=DEFAULT_SUMMARY,
        report=DEFAULT_REPORT,
        cache_dir=tmp_path / "absent",
        local_coverage=LOCAL_COVERAGE_SUMMARY,
    )
    summary, _ = compose(args, online=False, refresh=False, generated_at="2026-01-01T00:00:00Z")
    provenance = summary["run_provenance"]
    assert provenance["requests"]["requests_spent"] == 0
    assert provenance["requests"]["bytes_transferred"] == 0
    assert all(entry["source"] != "network" for entry in provenance["requests"]["ledger"])
    assert provenance["cache"]["dataset_source"] == "committed_summary"
    assert provenance["cache"]["cache_complete"] is False


@pytest.mark.skipif(
    not DEFAULT_CACHE_DIR.is_dir(),
    reason="原始响应缓存在 data/external/thermoml_api/，被 .gitignore 忽略，干净克隆上没有",
)
def test_check_recomputes_the_manifest_from_the_raw_cache_when_it_is_present(summary) -> None:
    args = argparse.Namespace(
        prereg=DEFAULT_PREREG,
        summary=DEFAULT_SUMMARY,
        report=DEFAULT_REPORT,
        cache_dir=DEFAULT_CACHE_DIR,
        local_coverage=LOCAL_COVERAGE_SUMMARY,
    )
    recomputed, _ = compose(args, online=False, refresh=False, generated_at="2026-01-01T00:00:00Z")
    assert recomputed["run_provenance"]["cache"]["dataset_source"] == "raw_api_cache"
    assert recomputed["run_provenance"]["cache"]["pages_present"] == EXPECTED_PA_S_PAGES + 2
    assert recomputed["dataset"] == summary["dataset"]


def test_check_fails_loudly_when_the_online_manifest_was_edited(tmp_path, summary) -> None:
    tampered = json.loads(json.dumps(summary))
    target = next(item for item in tampered["dataset"]["slices"] if item["id"] == PA_S_SLICE)
    dropped = target["dois"][0]
    target["dois"] = [doi for doi in target["dois"] if doi != dropped]
    target["structured_property_hit_dois"] = [
        doi for doi in target["structured_property_hit_dois"] if doi != dropped
    ]
    bad_summary = tmp_path / "tampered_summary.json"
    bad_summary.write_text(json.dumps(tampered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    good_report = tmp_path / "report.md"
    good_report.write_text(render_report(summary), encoding="utf-8")

    # the raw cache catches it, and so does the clean-clone path (criteria are re-derived)
    for cache_dir in (DEFAULT_CACHE_DIR, tmp_path / "absent"):
        assert (
            main(
                [
                    "--check",
                    "--summary",
                    str(bad_summary),
                    "--report",
                    str(good_report),
                    "--cache-dir",
                    str(cache_dir),
                ]
            )
            == 1
        )


def test_check_fails_loudly_when_the_report_drifts_from_the_summary(tmp_path) -> None:
    good_summary = tmp_path / "summary.json"
    good_summary.write_text(
        json.dumps(json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8")), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    drifted = tmp_path / "report.md"
    drifted.write_text(
        DEFAULT_REPORT.read_text(encoding="utf-8") + "\n额外一行：未登记的措辞。\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--check",
                "--summary",
                str(good_summary),
                "--report",
                str(drifted),
                "--cache-dir",
                str(DEFAULT_CACHE_DIR),
            ]
        )
        == 1
    )


def test_check_refuses_to_pass_without_a_summary(tmp_path) -> None:
    assert (
        main(
            [
                "--check",
                "--summary",
                str(tmp_path / "missing.json"),
                "--report",
                str(DEFAULT_REPORT),
                "--cache-dir",
                str(tmp_path / "absent"),
            ]
        )
        == 1
    )


# --- plumbing -------------------------------------------------------------------------


def test_api_url_zero_bases_the_page_number_and_quotes_the_phrase() -> None:
    url = api_url('"Viscosity, Pa*s"', PAGE_SIZE, FIRST_PAGE_NUM)
    assert url.startswith(API_BASE + "?")
    assert "pageNum=0" in url
    assert "pageSize=100" in url
    assert "%22Viscosity%2C+Pa%2As%22" in url


def test_cache_paths_keep_the_page_number_zero_padded_from_zero(tmp_path) -> None:
    payload, marker = cache_paths(tmp_path, PA_S_SLICE, 0)
    assert payload.name == "page-0000.json"
    assert marker.name == "page-0000.json.url"
    assert payload.parent.name == PA_S_SLICE


def test_record_doi_prefers_the_object_id_and_falls_back_to_the_citation() -> None:
    assert (
        record_doi({"id": "20.5000.trc.thermoml/10.1021/je800664z"})
        == "10.1021/je800664z"
    )
    assert (
        record_doi({"id": "weird", "content": {"Citation": {"sDOI": "10.1000/x"}}})
        == "10.1000/x"
    )
    assert record_doi({}) == ""


def test_structured_property_names_reads_only_the_epropname_field() -> None:
    content = {
        "PureOrMixtureData": [
            {
                "Property": [
                    {
                        "Property-MethodID": {
                            "PropertyGroup": {
                                "TransportProp": {
                                    "ePropName": "Viscosity, Pa*s",
                                    "eMethodName": "Vibrating wire viscometry",
                                }
                            }
                        }
                    }
                ]
            }
        ],
        "Citation": {"sAbstract": "Kinematic viscosity, m2/s is not a structured field here"},
    }
    names = structured_property_names(content)
    assert names == {"Viscosity, Pa*s"}
    # the phrase in the abstract must not leak in as a structured hit
    assert "Kinematic viscosity, m2/s" not in names


def test_summarize_slice_counts_phrase_only_hits_separately_from_structured_hits() -> None:
    collected = {
        "id": PA_S_SLICE,
        "query": '"Viscosity, Pa*s"',
        "property_name": "Viscosity, Pa*s",
        "page_size": PAGE_SIZE,
        "size_records": 3,
        "pages_fetched": 1,
        "observations": [
            {"doi": "10.1000/a", "structured_property_hit": True},
            {"doi": "10.1000/b", "structured_property_hit": False},
            {"doi": "", "structured_property_hit": False},
            {"doi": "10.1000/b", "structured_property_hit": True},
        ],
    }
    entry = summarize_slice(collected)
    assert entry["records_collected"] == 4
    assert entry["records_without_doi"] == 1
    assert entry["unique_dois"] == 2
    assert entry["structured_property_hit_records"] == 2
    assert entry["phrase_only_records"] == 2
    # 10.1000/b is a structured hit somewhere, so it must not also be listed as phrase-only
    assert entry["phrase_only_dois"] == []
    assert entry["dois"] == ["10.1000/a", "10.1000/b"]


def test_request_budget_refuses_to_overspend() -> None:
    budget = RequestBudget(limit=1)
    budget.spend()
    with pytest.raises(BudgetExhausted):
        budget.spend()
    assert budget.used == 1


def test_summary_and_prereg_agree_on_the_api_contract(summary) -> None:
    assert summary["api"]["endpoint"] == API_BASE
    assert summary["api"]["user_agent"] == USER_AGENT
    assert summary["api"]["page_size"] == PAGE_SIZE
    assert summary["api"]["total_records_query"] == TOTAL_RECORDS_QUERY
    assert summary["api"]["page_num_base"] == 0
    assert summary["run_provenance"]["requests"]["budget_limit"] <= REQUEST_BUDGET_LIMIT
    assert summary["run_provenance"]["requests"]["requests_spent"] <= REQUEST_BUDGET_LIMIT


def test_stable_view_drops_only_the_run_provenance_and_the_timestamp(summary) -> None:
    stable = stable_view(summary)
    assert "generated_at_utc" not in stable
    assert "run_provenance" not in stable
    assert set(stable) == set(summary) - {"generated_at_utc", "run_provenance"}
