"""Unit tests for the W13 OpenAlex + Unpaywall open-access sweep.

Everything here runs offline: the HTTP layer is injected, so query building, OA
filtering and candidate-row shaping are exercised against canned payloads. The
last group also pins the honest-failure path: when every call dies, the sweep must
emit no candidates and record the failure verbatim rather than guess.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.openalex_unpaywall_sweep import (
    CANDIDATE_COLUMNS,
    MAX_BACKOFF_SECONDS,
    HttpResponse,
    RequestBudget,
    build_openalex_filter,
    build_openalex_params,
    build_query_expression,
    extract_retry_after,
    http_get_with_backoff,
    is_new_lead,
    match_known_names,
    next_backoff_delay,
    normalize_doi,
    parse_retry_after,
    run_sweep,
    shape_candidate_row,
    shape_openalex_work,
    sweep_openalex,
    sweep_unpaywall,
    unpaywall_oa_fields,
    work_is_openalex_oa,
    write_outputs,
)


def _noop_sleep(_seconds: float) -> None:
    return None


def _work(work_id, doi, title, year=2015, is_oa=True, venue="J. Test Electrolytes"):
    return {
        "id": f"https://openalex.org/W{work_id}",
        "doi": None if doi is None else f"https://doi.org/{doi}",
        "title": title,
        "publication_year": year,
        "type": "article",
        "open_access": {"is_oa": is_oa, "oa_status": "gold" if is_oa else "closed"},
        "primary_location": {"source": {"display_name": venue, "type": "journal"}},
    }


def _openalex_payload(works):
    return {"meta": {"count": len(works)}, "results": works}


def _unpaywall(doi, is_oa, status="gold", url="https://example.org/a.pdf", host="repository"):
    best = None
    if is_oa:
        best = {
            "url_for_pdf": url,
            "url": url,
            "url_for_landing_page": url,
            "host_type": host,
            "version": "publishedVersion",
            "license": "cc-by",
        }
    return {
        "doi": doi,
        "is_oa": is_oa,
        "oa_status": status,
        "journal_is_oa": status == "gold",
        "published_date": "2015-01-01",
        "best_oa_location": best,
    }


# --- query building -------------------------------------------------------


def test_query_expression_pairs_dielectric_with_solvent_terms() -> None:
    query = build_query_expression(("glyme", "diglyme"))
    assert query == "(dielectric OR permittivity) AND (glyme OR diglyme)"


def test_query_expression_decommaes_and_quotes_multiword_terms() -> None:
    query = build_query_expression(("1,2-dimethoxyethane", "methyl nonafluorobutyl ether"))
    assert '"methyl nonafluorobutyl ether"' in query
    # A comma inside a filter value is rejected by OpenAlex, so none may survive.
    assert "," not in query.split("title_and_abstract.search:")[-1]
    assert "1 2-dimethoxyethane" in query


def test_query_expression_rejects_an_empty_term_list() -> None:
    with pytest.raises(ValueError):
        build_query_expression(("   ",))


def test_openalex_filter_has_no_comma_inside_the_search_value() -> None:
    query = build_query_expression(("1,2-dimethoxyethane", "sulfolane"))
    filt = build_openalex_filter(query, earliest_year=2001)
    head, _, search_value = filt.partition("title_and_abstract.search:")
    assert "," not in search_value
    assert head == "from_publication_date:2001-01-01,has_doi:true,"


def test_openalex_params_carry_a_polite_mailto_and_page_cap() -> None:
    params = build_openalex_params(
        "(dielectric OR permittivity) AND (glyme)", per_page=20, mailto="codex@local"
    )
    assert params["per-page"] == 20
    assert params["page"] == 1
    assert params["mailto"] == "codex@local"
    assert params["filter"].startswith("from_publication_date:2001-01-01,has_doi:true,")


# --- parsing --------------------------------------------------------------


def test_normalize_doi_strips_resolver_prefixes_and_lowercases() -> None:
    assert normalize_doi("https://doi.org/10.1021/ACS.JPCB.0C00000") == "10.1021/acs.jpcb.0c00000"
    assert normalize_doi("doi:10.1000/XYZ") == "10.1000/xyz"
    assert normalize_doi("  ") == ""
    assert normalize_doi(None) == ""


def test_shape_openalex_work_drops_records_without_a_doi() -> None:
    assert shape_openalex_work(_work(1, None, "No DOI here"), "glymes") is None


def test_shape_openalex_work_extracts_the_fields_the_sweep_needs() -> None:
    row = shape_openalex_work(
        _work(42, "10.1000/abc", "Dielectric study of glyme", year=2019, is_oa=False), "glymes"
    )
    assert row is not None
    assert row["doi"] == "10.1000/abc"
    assert row["openalex_id"] == "https://openalex.org/W42"
    assert row["publication_year"] == 2019
    assert row["host_venue"] == "J. Test Electrolytes"
    assert row["openalex_is_oa"] is False
    assert row["query_labels"] == ["glymes"]


def test_work_is_openalex_oa_reads_the_open_access_block() -> None:
    assert work_is_openalex_oa(_work(1, "10.1/x", "t", is_oa=True)) is True
    assert work_is_openalex_oa(_work(1, "10.1/x", "t", is_oa=False)) is False
    assert work_is_openalex_oa({}) is False


def test_unpaywall_fields_read_the_best_open_location() -> None:
    fields = unpaywall_oa_fields(_unpaywall("10.1/x", True, host="journal"))
    assert fields["unpaywall_is_oa"] is True
    assert fields["unpaywall_oa_status"] == "gold"
    assert fields["oa_url"] == "https://example.org/a.pdf"
    assert fields["oa_host_type"] == "journal"
    assert fields["oa_version"] == "publishedVersion"
    assert fields["license"] == "cc-by"
    assert fields["journal_is_oa"] is True


def test_unpaywall_fields_degrade_safely_on_closed_and_missing_locations() -> None:
    closed = unpaywall_oa_fields(_unpaywall("10.1/x", False, status="closed"))
    assert closed["unpaywall_is_oa"] is False
    assert closed["oa_url"] == ""
    assert closed["oa_host_type"] == ""
    assert unpaywall_oa_fields(None)["unpaywall_is_oa"] is False
    assert unpaywall_oa_fields({"is_oa": True})["oa_url"] == ""


def test_unpaywall_fields_read_the_real_v2_shape_without_a_source_block() -> None:
    # Unpaywall v2 carries `host_type` (and `version`) on the location itself; there
    # is no nested `source` object, so a source-only reader silently yields "".
    payload = {
        "is_oa": True,
        "oa_status": "green",
        "best_oa_location": {"host_type": "repository", "url": "https://example.org/x"},
    }
    fields = unpaywall_oa_fields(payload)
    assert fields["oa_host_type"] == "repository"
    assert fields["oa_url"] == "https://example.org/x"
    assert fields["oa_version"] == ""


# --- novelty triage -------------------------------------------------------


def test_match_known_names_is_whole_token() -> None:
    known = ("octane", "diglyme")
    assert match_known_names("Self-diffusion in cyclooctane", known) == ()
    assert match_known_names("Permittivity of diglyme at 298 K", known) == ("diglyme",)


def test_match_known_names_drops_short_generic_names() -> None:
    # "water" is five characters, below the default floor, so it cannot over-match.
    assert match_known_names("Dielectric relaxation of water", ("water",)) == ()


def test_is_new_lead_flags_titles_the_local_dataset_does_not_cover() -> None:
    known = ("sulfolane", "propylene carbonate")
    assert is_new_lead("Dielectric spectra of sulfolane", known) is False
    assert is_new_lead("Temperature dependence of epsilon in adiponitrile", known) is True


def test_shape_candidate_row_merges_openalex_and_unpaywall_fields() -> None:
    work = shape_openalex_work(_work(7, "10.1/x", "t", is_oa=True), "glymes")
    assert work is not None
    row = shape_candidate_row(work, unpaywall_oa_fields(_unpaywall("10.1/x", True)))
    assert row["doi"] == "10.1/x"
    assert row["unpaywall_is_oa"] is True
    assert row["openalex_is_oa"] is True

# --- budget and transport -------------------------------------------------


def test_request_budget_caps_spending_and_tallies_statuses() -> None:
    budget = RequestBudget(limit=2)
    assert budget.spend() is True
    assert budget.spend() is True
    assert budget.spend() is False
    assert budget.used == 2
    assert budget.remaining == 0
    budget.record(429)
    budget.record(429)
    budget.record(200)
    assert budget.statuses[429] == 2
    assert budget.statuses[200] == 1


def test_backoff_retries_a_429_then_returns_the_success() -> None:
    calls = []
    sleeps = []

    def http_get(url, params):
        calls.append(url)
        if len(calls) == 1:
            return HttpResponse(429, None, "rate limited")
        return HttpResponse(200, {"ok": 1}, None)

    budget = RequestBudget(limit=10)
    response = http_get_with_backoff(
        "https://api.openalex.org/works",
        {},
        http_get=http_get,
        budget=budget,
        sleeper=sleeps.append,
        sleep_seconds=1.0,
    )
    assert response.status_code == 200
    assert len(calls) == 2
    assert sleeps == [5.0]
    assert budget.statuses[429] == 1
    assert budget.statuses[200] == 1


def test_backoff_gives_up_after_the_retry_allowance() -> None:
    sleeps = []

    def http_get(url, params):
        return HttpResponse(429, None, "rate limited")

    budget = RequestBudget(limit=10)
    response = http_get_with_backoff(
        "https://api.openalex.org/works",
        {},
        http_get=http_get,
        budget=budget,
        sleeper=sleeps.append,
        sleep_seconds=1.0,
    )
    assert response.status_code == 429
    assert budget.used == 3  # one try plus two backoff retries
    assert sleeps == [5.0, 15.0, 1.0]


def test_backoff_stops_as_soon_as_the_budget_is_spent() -> None:
    calls = []

    def http_get(url, params):
        calls.append(url)
        return HttpResponse(429, None, "rate limited")

    budget = RequestBudget(limit=1)
    response = http_get_with_backoff(
        "https://api.openalex.org/works",
        {},
        http_get=http_get,
        budget=budget,
        sleeper=_noop_sleep,
        sleep_seconds=1.0,
    )
    assert response.status_code == 0
    assert "budget exhausted" in (response.error or "")
    assert len(calls) == 1
    assert budget.used == 1


# --- per-source sweeps ----------------------------------------------------


def test_sweep_openalex_shapes_works_and_records_the_total_count() -> None:
    payload = _openalex_payload(
        [
            _work(1, "10.1/a", "Dielectric study of glyme", year=2018, is_oa=True),
            _work(2, None, "A work with no DOI", is_oa=True),
        ]
    )
    calls = []

    def http_get(url, params):
        calls.append((url, dict(params)))
        return HttpResponse(200, payload, None)

    budget = RequestBudget(limit=5)
    record = sweep_openalex(
        "glymes",
        ("glyme",),
        http_get=http_get,
        budget=budget,
        mailto="codex@local",
        per_page=20,
        sleep_seconds=0.0,
        sleeper=_noop_sleep,
    )
    assert record["total_count"] == 2
    assert record["works_returned"] == 2
    assert [work["doi"] for work in record["works"]] == ["10.1/a"]
    assert record["status"] == 200
    assert record["error"] is None
    url, params = calls[0]
    assert url == "https://api.openalex.org/works"
    assert params["mailto"] == "codex@local"
    assert params["per-page"] == 20
    assert "title_and_abstract.search:" in params["filter"]


def test_sweep_openalex_records_a_transport_failure_verbatim() -> None:
    def http_get(url, params):
        return HttpResponse(0, None, "ConnectionError: DNS lookup failed")

    record = sweep_openalex(
        "glymes",
        ("glyme",),
        http_get=http_get,
        budget=RequestBudget(limit=5),
        mailto="codex@local",
        per_page=20,
        sleep_seconds=0.0,
        sleeper=_noop_sleep,
    )
    assert record["status"] == 0
    assert record["error"] == "ConnectionError: DNS lookup failed"
    assert record["works"] == []
    assert record["total_count"] is None


def test_sweep_openalex_skips_the_call_once_the_budget_is_gone() -> None:
    budget = RequestBudget(limit=0)
    record = sweep_openalex(
        "glymes",
        ("glyme",),
        http_get=lambda url, params: HttpResponse(200, {}, None),
        budget=budget,
        mailto="codex@local",
        per_page=20,
        sleep_seconds=0.0,
        sleeper=_noop_sleep,
    )
    assert record["status"] is None
    assert "budget exhausted" in record["error"]
    assert budget.used == 0


def test_sweep_unpaywall_resolves_open_access_and_records_failures() -> None:
    seen = []

    def http_get(url, params):
        seen.append((url, dict(params)))
        doi = url.split("/v2/", 1)[1]
        if doi == "10.1/dead":
            return HttpResponse(404, None, "not found")
        return HttpResponse(200, _unpaywall(doi, True), None)

    result = sweep_unpaywall(
        ("10.1/open", "10.1/dead"),
        http_get=http_get,
        budget=RequestBudget(limit=10),
        mailto="codex@local",
        sleep_seconds=0.0,
        sleeper=_noop_sleep,
    )
    assert set(result["resolved"]) == {"10.1/open"}
    assert result["resolved"]["10.1/open"]["unpaywall_is_oa"] is True
    assert result["unresolved"] == ["10.1/dead"]
    assert result["failures"] == [
        {"stage": "unpaywall", "doi": "10.1/dead", "status": 404, "error": "not found"}
    ]
    assert seen[0][0] == "https://api.unpaywall.org/v2/10.1/open"
    assert seen[0][1] == {"email": "codex@local"}


# --- end-to-end orchestration (still offline) -----------------------------


def _routed_http_get(openalex_payload, unpaywall_by_doi, calls=None):
    def http_get(url, params):
        if calls is not None:
            calls.append((url, dict(params)))
        if url.endswith("/works"):
            return HttpResponse(200, openalex_payload, None)
        # DOIs contain "/", so the Unpaywall path segment is the anchor, not the last "/".
        payload = unpaywall_by_doi.get(url.split("/v2/", 1)[1])
        if payload is None:
            return HttpResponse(404, None, "not found")
        return HttpResponse(200, payload, None)

    return http_get


def test_run_sweep_keeps_only_unpaywall_open_access(tmp_path: Path) -> None:
    works = [
        _work(1, "10.1/open", "Dielectric study of a glyme", is_oa=True),
        _work(2, "10.1/closed", "A closed access dielectric study", is_oa=False),
    ]
    http_get = _routed_http_get(
        _openalex_payload(works),
        {
            "10.1/open": _unpaywall("10.1/open", True),
            "10.1/closed": _unpaywall("10.1/closed", False, status="closed"),
        },
    )
    summary = run_sweep(
        output=tmp_path / "candidates.csv",
        summary_path=tmp_path / "summary.json",
        http_get=http_get,
        sleeper=_noop_sleep,
        known_names=("sulfolane",),
        queries=(("glymes", ("glyme",)),),
    )
    assert [row["doi"] for row in summary["candidates"]] == ["10.1/open"]
    assert summary["works_collected"] == 2
    assert summary["openalex_is_oa_works"] == 1
    assert summary["unpaywall_resolved"] == 2
    assert summary["oa_candidates"] == 1
    assert summary["new_leads"] == 1
    assert summary["candidates"][0]["is_new_lead"] is True
    assert summary["candidates"][0]["matched_known_names"] == ""


def test_run_sweep_marks_titles_the_local_dataset_already_covers(tmp_path: Path) -> None:
    works = [_work(1, "10.1/known", "Permittivity of sulfolane with temperature", is_oa=True)]
    http_get = _routed_http_get(
        _openalex_payload(works), {"10.1/known": _unpaywall("10.1/known", True)}
    )
    summary = run_sweep(
        output=tmp_path / "candidates.csv",
        summary_path=tmp_path / "summary.json",
        http_get=http_get,
        sleeper=_noop_sleep,
        known_names=("sulfolane",),
        queries=(("sulfones", ("sulfolane",)),),
    )
    row = summary["candidates"][0]
    assert row["is_new_lead"] is False
    assert row["matched_known_names"] == "sulfolane"
    assert summary["new_leads"] == 0


def test_run_sweep_merges_repeated_dois_across_queries(tmp_path: Path) -> None:
    payload = _openalex_payload([_work(1, "10.1/dup", "Dielectric study of glyme", is_oa=True)])
    http_get = _routed_http_get(payload, {"10.1/dup": _unpaywall("10.1/dup", True)})
    summary = run_sweep(
        output=tmp_path / "candidates.csv",
        summary_path=tmp_path / "summary.json",
        http_get=http_get,
        sleeper=_noop_sleep,
        known_names=(),
        queries=(("glymes", ("glyme",)), ("sulfones", ("sulfolane",))),
    )
    assert summary["works_collected"] == 1
    assert summary["candidates"][0]["query_label"] == "glymes;sulfones"


def test_run_sweep_writes_the_csv_and_summary_outputs(tmp_path: Path) -> None:
    works = [_work(1, "10.1/open", "Dielectric study of a glyme", year=2020, is_oa=True)]
    http_get = _routed_http_get(
        _openalex_payload(works), {"10.1/open": _unpaywall("10.1/open", True)}
    )
    csv_path = tmp_path / "candidates.csv"
    json_path = tmp_path / "summary.json"
    run_sweep(
        output=csv_path,
        summary_path=json_path,
        http_get=http_get,
        sleeper=_noop_sleep,
        known_names=(),
        queries=(("glymes", ("glyme",)),),
    )
    assert b"\r\n" not in csv_path.read_bytes()
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(CANDIDATE_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["doi"] == "10.1/open"
    assert rows[0]["is_new_lead"] == "True"
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["oa_candidates"] == 1
    assert on_disk["mailto"] == "codex@local"
    assert on_disk["queries"][0]["label"] == "glymes"
    assert "works" not in on_disk["queries"][0]
    assert on_disk["caveats"]


def test_run_sweep_records_a_total_outage_honestly(tmp_path: Path) -> None:
    def dead_get(url, params):
        return HttpResponse(0, None, "ConnectionError: DNS lookup failed for api.openalex.org")

    csv_path = tmp_path / "candidates.csv"
    json_path = tmp_path / "summary.json"
    summary = run_sweep(
        output=csv_path,
        summary_path=json_path,
        http_get=dead_get,
        sleeper=_noop_sleep,
        known_names=(),
        queries=(("glymes", ("glyme",)), ("sulfones", ("sulfolane",))),
    )
    assert summary["candidates"] == []
    assert summary["oa_candidates"] == 0
    assert summary["works_collected"] == 0
    assert summary["unpaywall_resolved"] == 0
    assert summary["http_status_counts"] == {"0": 2}
    assert len(summary["failures"]) == 2
    assert all(failure["stage"] == "openalex" for failure in summary["failures"])
    assert all("DNS lookup failed" in failure["error"] for failure in summary["failures"])
    # The ledger is still written, and it is empty rather than fabricated.
    assert csv_path.read_text(encoding="utf-8").strip() == ",".join(CANDIDATE_COLUMNS)
    assert json.loads(json_path.read_text(encoding="utf-8"))["oa_candidates"] == 0


def test_run_sweep_respects_the_hard_request_budget(tmp_path: Path) -> None:
    payload = _openalex_payload([_work(1, "10.1/one", "Dielectric study of glyme", is_oa=True)])
    calls = []
    http_get = _routed_http_get(payload, {"10.1/one": _unpaywall("10.1/one", True)}, calls=calls)
    summary = run_sweep(
        output=tmp_path / "candidates.csv",
        summary_path=tmp_path / "summary.json",
        http_get=http_get,
        sleeper=_noop_sleep,
        known_names=(),
        limit=1,
        queries=(("glymes", ("glyme",)), ("sulfones", ("sulfolane",))),
    )
    assert len(calls) == 1
    assert summary["requests_used"] == 1
    assert summary["request_budget"] == 1
    assert summary["oa_candidates"] == 0
    assert summary["unpaywall_unresolved"] == ["10.1/one"]


def test_write_outputs_can_be_called_on_a_hand_built_summary(tmp_path: Path) -> None:
    summary = {"candidates": [{column: "" for column in CANDIDATE_COLUMNS}]}
    csv_path = tmp_path / "nested" / "candidates.csv"
    json_path = tmp_path / "nested" / "summary.json"
    write_outputs(summary, output=csv_path, summary_path=json_path)
    assert csv_path.is_file()
    assert json_path.is_file()
    assert csv_path.read_text(encoding="utf-8").count("\n") == 2

# --- server-advertised retry hints ----------------------------------------


def test_parse_retry_after_accepts_numbers_and_rejects_junk() -> None:
    assert parse_retry_after("39") == 39.0
    assert parse_retry_after(39) == 39.0
    assert parse_retry_after(" 12.5 ") == 12.5
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") is None
    assert parse_retry_after(-1) is None


def test_extract_retry_after_prefers_the_header_then_the_body() -> None:
    body = '{"error":"Rate limit exceeded","retryAfter":39}'
    assert extract_retry_after("12", body) == 12.0
    assert extract_retry_after(None, body) == 39.0
    assert extract_retry_after(None, "not json") is None
    assert extract_retry_after(None, None) is None


def test_backoff_waits_for_the_server_retry_hint() -> None:
    # The hint (39s) is longer than the scheduled 5s, so it wins.
    response = HttpResponse(429, None, "rate limited", retry_after=39.0)
    assert next_backoff_delay(response, 0, 1.0) == 39.0
    assert next_backoff_delay(response, 1, 1.0) == 39.0


def test_backoff_caps_an_absurd_retry_hint_and_keeps_the_schedule_as_a_floor() -> None:
    absurd = HttpResponse(429, None, "rate limited", retry_after=99999.0)
    assert next_backoff_delay(absurd, 0, 1.0) == MAX_BACKOFF_SECONDS
    # A hint shorter than the schedule does not shorten the polite wait.
    tiny = HttpResponse(429, None, "rate limited", retry_after=0.5)
    assert next_backoff_delay(tiny, 0, 1.0) == 5.0
    assert next_backoff_delay(tiny, 1, 1.0) == 15.0


def test_backoff_retries_a_429_with_the_advertised_delay() -> None:
    calls = []
    sleeps = []

    def http_get(url, params):
        calls.append(url)
        if len(calls) == 1:
            return HttpResponse(429, None, "rate limited", retry_after=39.0)
        return HttpResponse(200, {"ok": 1}, None)

    budget = RequestBudget(limit=10)
    response = http_get_with_backoff(
        "https://api.openalex.org/works",
        {},
        http_get=http_get,
        budget=budget,
        sleeper=sleeps.append,
        sleep_seconds=1.0,
    )
    assert response.status_code == 200
    assert sleeps == [39.0]
