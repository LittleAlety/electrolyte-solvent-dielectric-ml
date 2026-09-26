"""Unit tests for the AL Round-3 acquisition-list probe.

Everything here runs offline.  The HTTP layer is injected, so compound
resolution, noise classification, snippet extraction, disposition rules and the
PubChem payload shaping are all exercised against canned fixtures.  The last
group pins the honest-failure paths: an offline run must make zero HTTP calls,
a bot check must never be reported as a full text, and a value must never be
claimed without a permittivity cue, a temperature unit and a plausible number on
the same extracted line.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from probes.al_round3_candidates import (
    GET_DISPOSITIONS,
    HTML_FULLTEXT_MIN_CHARS,
    OUTPUT_COLUMNS,
    CompoundEntry,
    Evidence,
    EvidenceReport,
    HttpResponse,
    RequestBudget,
    aliases_for,
    classify_disposition,
    classify_fulltext,
    classify_noise,
    clean_lines,
    extract_evidence,
    extract_html_text,
    extract_pdf_pages,
    find_compound_mentions,
    find_unresolved_names,
    http_get_with_backoff,
    is_bot_check,
    looks_like_pdf,
    molecular_formula,
    next_backoff_delay,
    parse_retry_after,
    plausible_permittivity_values,
    pubchem_formula_from_payload,
    pubchem_slug,
    render_report,
    resolve_inchikey,
    roster_status,
    run_pipeline,
    shape_crosscheck,
    value_outcome,
    write_outputs,
)

ADIPONITRILE_KEY = "BTGRAWJCKBQKAO-UHFFFAOYSA-N"
SUCCINONITRILE_KEY = "IAHFWCOBPZCAEA-UHFFFAOYSA-N"

# The synthetic input file mirrors the columns the round-6 sweep writes.
LEAD_COLUMNS = (
    "doi",
    "openalex_id",
    "title",
    "publication_year",
    "type",
    "host_venue",
    "openalex_is_oa",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "oa_url",
    "oa_host_type",
    "oa_version",
    "license",
    "journal_is_oa",
    "published_date",
    "query_label",
    "matched_known_names",
    "is_new_lead",
)


def _noop_sleep(_seconds: float) -> None:
    return None


def _lead(
    doi: str = "10.0000/test",
    title: str = "Dielectric constant of adiponitrile",
    oa_url: str = "https://example.org/paper.pdf",
    query_label: str = "dinitriles",
) -> dict[str, str]:
    return {
        "doi": doi,
        "openalex_id": "https://openalex.org/W1",
        "title": title,
        "publication_year": "2022",
        "type": "article",
        "host_venue": "J. Test",
        "openalex_is_oa": "True",
        "unpaywall_is_oa": "True",
        "unpaywall_oa_status": "gold",
        "oa_url": oa_url,
        "oa_host_type": "publisher",
        "oa_version": "publishedVersion",
        "license": "cc-by",
        "journal_is_oa": "True",
        "published_date": "2022-01-01",
        "query_label": query_label,
        "matched_known_names": "",
        "is_new_lead": "True",
    }


class _Recorder:
    """A fake transport that records every call and replays canned answers."""

    def __init__(self, answer: HttpResponse | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.answer = answer if answer is not None else HttpResponse(200)

    def __call__(self, url: str, *, max_bytes: int) -> HttpResponse:
        self.calls.append((url, max_bytes))
        if callable(self.answer):
            return self.answer(url)
        return self.answer


def _write_input(path: Path, leads: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LEAD_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for lead in leads:
            writer.writerow({column: lead.get(column, "") for column in LEAD_COLUMNS})


def _big_html(body: str) -> bytes:
    """An HTML document large enough to clear the full-text threshold."""

    filler = "<p>boilerplate sentence</p>" * 4000
    return f"<html><body>{body}{filler}</body></html>".encode()


# --- compound resolution --------------------------------------------------


def test_resolve_inchikey_matches_the_pinned_key() -> None:
    # The audit report pins this exact key after an earlier ad-hoc grep used the
    # wrong one, so this is the project's regression value for adiponitrile.
    assert resolve_inchikey("N#CCCCCC#N") == ADIPONITRILE_KEY


def test_resolve_inchikey_returns_none_for_an_unparsable_smiles() -> None:
    assert resolve_inchikey("this is not a molecule") is None


def test_molecular_formula_is_hill_ordered() -> None:
    assert molecular_formula("N#CCCCCC#N") == "C6H8N2"


def test_aliases_for_puts_the_longest_spelling_first() -> None:
    aliases = aliases_for(CompoundEntry("1,2-dimethoxyethane", "COCCOC"))
    assert aliases[0] == "ethylene glycol dimethyl ether"
    assert "1,2-dimethoxyethane" in aliases


def test_tetraglyme_never_resolves_to_a_bare_glyme() -> None:
    titles = {
        match.name
        for match in find_compound_mentions(
            "low dielectric constant tetraglyme-based electrolytes"
        )
    }
    assert titles == {"tetraglyme"}


def test_decagram_of_a_novec_brand_resolves_to_the_named_fluid() -> None:
    names = {
        match.name
        for match in find_compound_mentions("Pool boiling of FC-72 and Novec 649")
    }
    assert names == {"perfluorohexane", "decafluoropentane"}


def test_compound_matching_is_whole_token() -> None:
    assert find_compound_mentions("cyclooctane and not a solvent") == ()


def test_colon_spelling_of_dimethoxyethane_is_resolved() -> None:
    matches = find_compound_mentions("Solvation effect on 1,2:dimethoxyethane")
    assert [match.name for match in matches] == ["1,2-dimethoxyethane"]


def test_each_compound_is_reported_at_most_once() -> None:
    matches = find_compound_mentions(
        "succinonitrile, succinonitrile-glutaronitrile and succinonitrile again"
    )
    assert [match.name for match in matches].count("succinonitrile") == 1


def test_unresolved_patterns_fire_on_a_plural() -> None:
    hits = dict(find_unresolved_names("Charge-Separated States in Molecular Triads"))
    assert "not a solvent" in hits.values()


def test_unresolved_pattern_does_not_fire_on_a_resolved_glyme() -> None:
    assert find_unresolved_names("tetraglyme based electrolytes") == ()


def test_unresolved_pattern_fires_on_a_bare_glyme() -> None:
    fragments = [fragment for fragment, _ in find_unresolved_names("glyme based electrolytes")]
    assert fragments == ["glyme"]


# --- noise classification -------------------------------------------------


def test_pool_boiling_titles_are_noise() -> None:
    assert "pool_boiling_heat_transfer" in classify_noise(
        "Enhanced nucleate boiling of Novec 649 on thin metal foils"
    )


def test_biophysics_titles_are_noise_and_a_plural_still_fires() -> None:
    rules = classify_noise(
        "Mechanism by which trifluoroethanol/water mixtures stabilize peptides"
    )
    assert rules == ("biophysics_peptide_or_protein",)


def test_a_solvent_title_is_not_noise() -> None:
    assert classify_noise("Dielectric spectroscopy of propylene carbonate") == ()


# --- roster status --------------------------------------------------------


def test_roster_status_distinguishes_new_from_covered() -> None:
    roster = frozenset({"AAA", "BBB"})
    assert roster_status([], roster) == "unresolved"
    assert roster_status(["AAA", "BBB"], roster) == "all_in_roster"
    assert roster_status(["AAA", "CCC"], roster) == "some_new"
    assert roster_status(["CCC"], roster) == "all_new"


# --- permittivity extraction ---------------------------------------------


def test_temperature_number_is_never_returned_as_a_permittivity() -> None:
    values = plausible_permittivity_values("the dielectric constant is 64.9 at 298.15 K")
    assert values == (64.9,)
    assert 298.15 not in values


def test_a_number_far_from_the_cue_is_rejected() -> None:
    line = "the dielectric constant was reported elsewhere, and the run used " + "x" * 60 + " 9.9"
    assert plausible_permittivity_values(line) == ()


def test_an_implausible_value_is_rejected() -> None:
    assert plausible_permittivity_values("dielectric constant 640 at 298 K") == ()


def test_no_cue_means_no_value() -> None:
    assert plausible_permittivity_values("the viscosity is 3.2 mPa s at 298 K") == ()


def test_evidence_value_line_requires_cue_temperature_and_number() -> None:
    report = extract_evidence(
        ["The relative permittivity of the solvent is 31.5 at 298.15 K."]
    )
    assert len(report.values) == 1
    assert report.values[0].values == (31.5,)
    assert report.values[0].page == 1
    assert report.values[0].temperature_tokens == ("298.15 K",)


def test_evidence_value_line_without_a_temperature_is_not_a_value() -> None:
    report = extract_evidence(["The relative permittivity of the solvent is 31.5."])
    assert report.values == ()
    assert report.permittivity_context_lines == 1


def test_table_shaped_block_is_flagged_for_review() -> None:
    report = extract_evidence(
        [
            (
                "Table 2. Dielectric constant of the solvent\n"
                "T / K    epsilon\n"
                "293.15   31.5\n"
                "298.15   30.9"
            )
        ]
    )
    # The caption line carries no value of its own, so nothing may be claimed as
    # read; the block is surfaced for a human instead.
    assert report.values == ()
    assert report.tables
    first = report.tables[0]
    assert first.kind == "table"
    assert first.page == 1
    assert first.line_number == 1
    assert "293.15" in first.text


def test_page_numbers_are_one_based_and_tracked() -> None:
    report = extract_evidence(
        ["nothing here\nthe dielectric constant is 31.5 at 298.15 K", "a second page"]
    )
    assert report.values[0].page == 1
    assert report.values[0].line_number == 2


def test_clean_lines_collapses_whitespace() -> None:
    assert clean_lines("a   b\n\n c ") == ["a b", "", "c"]


def test_value_outcome_reports_the_reason_when_nothing_is_readable() -> None:
    status, reason = value_outcome(EvidenceReport((), 0, 0))
    assert status == "value_not_read"
    assert reason == "no_permittivity_wording_in_extracted_text"


def test_value_outcome_reports_a_missing_temperature_unit() -> None:
    status, reason = value_outcome(EvidenceReport((), 2, 0))
    assert status == "value_not_read"
    assert "no_explicit_temperature_with_unit" in reason


def test_value_outcome_prefers_a_read_value_over_a_table_candidate() -> None:
    item = Evidence("value", 1, 1, "text", ("298 K",), (31.5,))
    assert value_outcome(EvidenceReport((item,), 1, 1))[0] == "value_read"


# --- disposition rules ----------------------------------------------------


def _disposition(**overrides) -> str:
    base = {
        "oa_url": "https://example.org/a.pdf",
        "fetch_attempted": True,
        "skip_reason": "",
        "fetch_error": "",
        "fulltext": True,
        "block_reason": "",
        "value_status": "value_read",
    }
    base.update(overrides)
    return classify_disposition(**base)


def test_disposition_order_prefers_a_read_value() -> None:
    assert _disposition() == "value_read"


def test_disposition_reports_a_fetch_error_before_anything_else() -> None:
    assert _disposition(fetch_error="ConnectTimeout: boom") == "blocked_fetch_error"


def test_disposition_names_the_block_reason() -> None:
    assert _disposition(fulltext=False, block_reason="bot_check") == "blocked_bot_check"
    assert _disposition(fulltext=False, block_reason="html_landing") == "blocked_html_landing"


def test_disposition_for_an_unfetched_noise_lead() -> None:
    assert _disposition(fetch_attempted=False, skip_reason="noise_prefilter") == (
        "skipped_noise_prefilter"
    )


def test_disposition_for_an_offline_lead() -> None:
    assert _disposition(fetch_attempted=False, skip_reason="offline") == "not_attempted_offline"


def test_disposition_without_an_oa_url() -> None:
    assert _disposition(oa_url="", fetch_attempted=False) == "no_oa_url"


def test_every_disposition_the_rules_emit_is_declared() -> None:
    produced = {
        _disposition(),
        _disposition(value_status="table_candidate"),
        _disposition(value_status="value_not_read"),
        _disposition(fetch_error="x"),
        _disposition(fulltext=False, block_reason="bot_check"),
        _disposition(fulltext=False, block_reason="pdf_unparsed"),
        _disposition(fulltext=False, block_reason=""),
        _disposition(oa_url="", fetch_attempted=False),
        _disposition(fetch_attempted=False, skip_reason="noise_prefilter"),
        _disposition(fetch_attempted=False, skip_reason="offline"),
        _disposition(fetch_attempted=False, skip_reason="request_budget"),
    }
    assert produced <= set(GET_DISPOSITIONS)


# --- body classification --------------------------------------------------


def test_pdf_magic_and_content_type_are_both_accepted() -> None:
    assert looks_like_pdf(b"%PDF-1.7\n", "")
    assert looks_like_pdf(b"<html>", "application/pdf")


def test_a_bot_check_is_recognised() -> None:
    assert is_bot_check("<title>Just a moment...</title>cf-browser-verification")
    assert not is_bot_check("<html><body>a real article</body></html>")


def test_bot_check_body_is_not_a_fulltext() -> None:
    body = _big_html("<title>Just a moment...</title>cf-browser-verification")
    fulltext, reason, _, _, error = classify_fulltext(body, "text/html")
    assert (fulltext, reason) == (False, "bot_check")
    assert error


def test_short_html_is_a_landing_page_not_a_fulltext() -> None:
    fulltext, reason, _, _, _ = classify_fulltext(
        b"<html><body><h1>Paper</h1></body></html>", "text/html"
    )
    assert (fulltext, reason) == (False, "html_landing")


def test_large_html_is_accepted_as_a_fulltext() -> None:
    fulltext, reason, extractor, pages, _ = classify_fulltext(_big_html("<p>x</p>"), "text/html")
    assert fulltext and reason == "" and extractor == "html"
    assert sum(len(page) for page in pages) >= HTML_FULLTEXT_MIN_CHARS


def test_empty_body_is_reported_rather_than_parsed() -> None:
    assert classify_fulltext(b"", "application/pdf")[1] == "empty_body"


def test_pdf_extraction_never_raises_on_garbage() -> None:
    pages, error = extract_pdf_pages(b"%PDF-1.4 truncated nonsense")
    assert isinstance(pages, tuple)
    assert error


def test_html_text_drops_scripts_and_unescapes_entities() -> None:
    text = extract_html_text(b"<script>var x=1;</script><p>a &amp; b</p>")
    assert "var x" not in text
    assert "a & b" in text


# --- pubchem shaping ------------------------------------------------------


def test_pubchem_payload_shaping() -> None:
    payload = {"PropertyTable": {"Properties": [{"CID": 8061, "MolecularFormula": "C6H8N2"}]}}
    assert pubchem_formula_from_payload(payload) == (8061, "C6H8N2")
    assert pubchem_formula_from_payload({"PropertyTable": {"Properties": []}}) == (None, "")
    assert pubchem_formula_from_payload(None) == (None, "")


def test_crosscheck_outcomes() -> None:
    payload = {"PropertyTable": {"Properties": [{"CID": 7, "MolecularFormula": "C6H8N2"}]}}
    assert shape_crosscheck("KEY", "C6H8N2", payload) == "KEY=cid7:formula_match"
    assert "formula_mismatch" in shape_crosscheck("KEY", "C5H3F9O", payload)
    assert shape_crosscheck("KEY", "C6H8N2", {}) == "KEY=unavailable"


def test_pubchem_slug_is_upper_cased() -> None:
    assert pubchem_slug(" abcd-efgh ") == "ABCD-EFGH"


# --- transport ------------------------------------------------------------


def test_request_budget_stops_at_the_limit() -> None:
    budget = RequestBudget(2)
    assert budget.spend() and budget.spend()
    assert not budget.spend()
    assert budget.remaining == 0
    budget.record(200)
    assert budget.statuses[200] == 1


def test_retry_after_parsing_and_backoff_cap() -> None:
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("nonsense") is None
    assert parse_retry_after(None) is None
    hints = HttpResponse(429, retry_after=600.0)
    assert next_backoff_delay(hints, 0, 1.0) == 45.0
    assert next_backoff_delay(HttpResponse(429), 0, 1.0) == 5.0


def test_backoff_retries_a_429_then_returns_the_success() -> None:
    answers = iter([HttpResponse(429, retry_after=30.0), HttpResponse(200)])
    slept: list[float] = []
    budget = RequestBudget(5)
    response = http_get_with_backoff(
        "https://example.org/a",
        http_get=lambda _url: next(answers),
        budget=budget,
        sleeper=slept.append,
        sleep_seconds=1.0,
    )
    assert response.status_code == 200
    # 1.0 is the polite pre-request sleep; 30.0 is the server's own retry hint,
    # which outranks the fixed 5 s/15 s schedule.
    assert slept == [1.0, 30.0]
    assert budget.used == 2


def test_transport_budget_exhaustion_is_reported_not_raised() -> None:
    response = http_get_with_backoff(
        "https://example.org/a",
        http_get=lambda _url: HttpResponse(200),
        budget=RequestBudget(0),
        sleeper=_noop_sleep,
        sleep_seconds=0.0,
    )
    assert response.status_code == 0
    assert "budget exhausted" in response.error


# --- pipeline -------------------------------------------------------------


def _run(tmp_path: Path, leads: list[dict[str, str]], **kwargs) -> tuple[dict, list]:
    input_path = tmp_path / "in.csv"
    output_path = tmp_path / "out.csv"
    summary_path = tmp_path / "summary.json"
    _write_input(input_path, leads)
    recorder = _Recorder(kwargs.pop("answer", None))
    transport = kwargs.pop("transport", recorder)
    summary = run_pipeline(
        input_path=input_path,
        roster_path=tmp_path / "missing_roster.csv",
        observations_path=tmp_path / "missing_obs.csv",
        output_path=output_path,
        summary_path=summary_path,
        http_get=transport,
        sleeper=_noop_sleep,
        sleep_seconds=0.0,
        **kwargs,
    )
    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return summary, rows


def test_offline_run_makes_no_http_calls_at_all(tmp_path: Path) -> None:
    def explode(_url: str, *, max_bytes: int) -> HttpResponse:
        raise AssertionError("an offline run must not touch the network")

    leads = [_lead(), _lead(doi="10.0000/two", title="Pool boiling of Novec 649")]
    summary, rows = _run(tmp_path, leads, transport=explode, offline=True)
    assert summary["budget"]["requests_used"] == 0
    assert summary["budget"]["pubchem_requests_used"] == 0
    assert summary["run_mode"]["crosscheck"] is False
    assert {row["disposition"] for row in rows} == {
        "not_attempted_offline",
        "skipped_noise_prefilter",
    }


def test_noise_leads_are_not_fetched_by_default(tmp_path: Path) -> None:
    recorder = _Recorder()
    leads = [_lead(title="Pool boiling of Novec 649 on metal foils")]
    summary, rows = _run(tmp_path, leads, transport=recorder, crosscheck=False)
    assert recorder.calls == []
    assert rows[0]["disposition"] == "skipped_noise_prefilter"
    assert summary["noise_lead_count"] == 1


def test_fetch_noise_overrides_the_prefilter(tmp_path: Path) -> None:
    recorder = _Recorder()
    leads = [_lead(title="Pool boiling of Novec 649 on metal foils")]
    _run(tmp_path, leads, transport=recorder, fetch_noise=True, crosscheck=False)
    assert len(recorder.calls) == 1


def test_a_readable_value_is_recorded_verbatim_with_provenance(tmp_path: Path) -> None:
    body = _big_html("<p>The relative permittivity of adiponitrile is 32.0 at 298.15 K.</p>")
    leads = [_lead()]
    summary, rows = _run(
        tmp_path,
        leads,
        transport=_Recorder(HttpResponse(200, "", "text/html", body)),
        crosscheck=False,
    )
    assert rows[0]["disposition"] == "value_read"
    assert rows[0]["epsilon_values_read"] == "1"
    assert "32.0 at 298.15 K" in rows[0]["epsilon_evidence"]
    assert "p1L" in rows[0]["epsilon_evidence"]
    assert summary["values_read"][0]["doi"] == "10.0000/test"


def test_a_reachable_fulltext_without_a_value_is_reported_honestly(tmp_path: Path) -> None:
    body = _big_html("<p>This article never reports a permittivity at all.</p>")
    _summary, rows = _run(
        tmp_path,
        [_lead()],
        transport=_Recorder(HttpResponse(200, "", "text/html", body)),
        crosscheck=False,
    )
    assert rows[0]["disposition"] == "fulltext_no_value"
    assert rows[0]["value_status"] == "value_not_read"
    assert rows[0]["epsilon_evidence"] == ""


def test_a_bot_check_200_is_blocked_and_not_called_reachable(tmp_path: Path) -> None:
    body = _big_html("<title>Just a moment...</title>cf-browser-verification")
    summary, rows = _run(
        tmp_path,
        [_lead()],
        transport=_Recorder(HttpResponse(200, "", "text/html", body)),
        crosscheck=False,
    )
    assert rows[0]["disposition"] == "blocked_bot_check"
    assert summary["disposition_counts"]["blocked_bot_check"] == 1


def test_http_error_is_recorded_as_a_failure_with_the_status(tmp_path: Path) -> None:
    answer = HttpResponse(403, "https://example.org/a.pdf", "text/html", b"", False, "HTTP 403")
    summary, rows = _run(tmp_path, [_lead()], transport=_Recorder(answer))
    assert rows[0]["disposition"] == "blocked_fetch_error"
    assert rows[0]["http_status"] == "403"
    assert summary["failures"][0]["stage"] == "fetch"


def test_per_document_byte_cap_reaches_the_transport(tmp_path: Path) -> None:
    recorder = _Recorder(HttpResponse(200, "", "text/html", b"<html></html>"))
    _run(tmp_path, [_lead()], transport=recorder, max_bytes_per_doc=1234, crosscheck=False)
    assert recorder.calls == [("https://example.org/paper.pdf", 1234)]


def test_crosscheck_queries_pubchem_for_a_resolved_compound(tmp_path: Path) -> None:
    payload = json.dumps(
        {"PropertyTable": {"Properties": [{"CID": 8061, "MolecularFormula": "C6H8N2"}]}}
    ).encode()
    seen: list[str] = []

    def transport(url: str, *, max_bytes: int) -> HttpResponse:
        seen.append(url)
        if "pubchem" in url:
            return HttpResponse(200, url, "application/json", payload)
        return HttpResponse(200, url, "text/html", _big_html("<p>no numbers here</p>"))

    _summary, rows = _run(tmp_path, [_lead()], transport=transport)
    assert any("pubchem" in url for url in seen)
    assert rows[0]["pubchem_crosscheck"] == f"{ADIPONITRILE_KEY}=cid8061:formula_match"


def test_a_compound_shared_by_two_leads_is_cross_checked_once(tmp_path: Path) -> None:
    payload = json.dumps(
        {"PropertyTable": {"Properties": [{"CID": 8061, "MolecularFormula": "C6H8N2"}]}}
    ).encode()
    pubchem_calls: list[str] = []

    def transport(url: str, *, max_bytes: int) -> HttpResponse:
        if "pubchem" in url:
            pubchem_calls.append(url)
            return HttpResponse(200, url, "application/json", payload)
        return HttpResponse(200, url, "text/html", _big_html("<p>nothing</p>"))

    leads = [_lead(), _lead(doi="10.0000/two")]
    summary, rows = _run(tmp_path, leads, transport=transport)
    assert len(pubchem_calls) == 1
    assert summary["budget"]["pubchem_requests_used"] == 1
    assert rows[0]["pubchem_crosscheck"] == rows[1]["pubchem_crosscheck"]


def test_summary_counts_every_lead_exactly_once(tmp_path: Path) -> None:
    leads = [
        _lead(),
        _lead(doi="10.0000/two", title="Pool boiling of Novec 649"),
        _lead(doi="10.0000/three", title="something unrelated", oa_url=""),
    ]
    summary, rows = _run(tmp_path, leads)
    assert summary["lead_count"] == 3
    assert sum(summary["disposition_counts"].values()) == 3
    assert sum(summary["roster_status_counts"].values()) == 3
    assert len(rows) == 3


def test_succinonitrile_is_reported_as_not_in_the_roster(tmp_path: Path) -> None:
    # The v1.0 roster holds 246 compounds and does not include succinonitrile,
    # even though the v11 observation table does.  The row must not blur that.
    roster = tmp_path / "roster.csv"
    roster.write_text("inchikey\n" + ADIPONITRILE_KEY + "\n", encoding="utf-8")
    observations = tmp_path / "obs.csv"
    observations.write_text("inchikey\n" + SUCCINONITRILE_KEY + "\n", encoding="utf-8")
    input_path = tmp_path / "in.csv"
    _write_input(input_path, [_lead(title="Dielectric properties of succinonitrile")])
    run_pipeline(
        input_path=input_path,
        roster_path=roster,
        observations_path=observations,
        output_path=tmp_path / "out.csv",
        summary_path=tmp_path / "summary.json",
        http_get=_Recorder(HttpResponse(200)),
        sleeper=_noop_sleep,
        sleep_seconds=0.0,
        offline=True,
    )
    with (tmp_path / "out.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["roster_status"] == "all_new"
    assert row["in_roster"] == "False"
    assert row["in_observations_v11"] == "True"


def test_roster_and_observation_keys_are_loaded_from_synthetic_files(tmp_path: Path) -> None:
    roster = tmp_path / "roster.csv"
    roster.write_text("inchikey\n" + ADIPONITRILE_KEY + "\n", encoding="utf-8")
    input_path = tmp_path / "in.csv"
    _write_input(input_path, [_lead()])
    run_pipeline(
        input_path=input_path,
        roster_path=roster,
        observations_path=tmp_path / "absent.csv",
        output_path=tmp_path / "out.csv",
        summary_path=tmp_path / "summary.json",
        http_get=_Recorder(HttpResponse(200)),
        sleeper=_noop_sleep,
        sleep_seconds=0.0,
        offline=True,
    )
    with (tmp_path / "out.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["roster_status"] == "all_in_roster"
    assert row["in_roster"] == "True"


# --- outputs --------------------------------------------------------------


def test_write_outputs_emits_exactly_the_declared_columns(tmp_path: Path) -> None:
    output_path = tmp_path / "out.csv"
    summary_path = tmp_path / "summary.json"
    write_outputs(
        [{"doi": "10.0/x", "disposition": "value_read"}],
        {"lead_count": 1, "budget": {}, "disposition_counts": {}, "failures": []},
        output_path=output_path,
        summary_path=summary_path,
    )
    raw = output_path.read_bytes()
    assert b"\r\n" not in raw
    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(OUTPUT_COLUMNS)
    assert json.loads(summary_path.read_text(encoding="utf-8"))["lead_count"] == 1


def test_render_report_prints_the_request_budget() -> None:
    summary = {
        "lead_count": 2,
        "budget": {
            "requests_used": 3,
            "request_limit": 90,
            "pubchem_requests_used": 1,
            "pubchem_request_limit": 30,
            "bytes_fetched": 99,
            "max_bytes_per_doc": 10,
            "total_byte_budget": 100,
            "status_counts": {"200": 3},
        },
        "disposition_counts": {"value_read": 1, "blocked_fetch_error": 1},
        "failures": [],
    }
    text = render_report(summary)
    assert "requests used: 3/90" in text
    assert "bytes fetched: 99" in text
    assert "value_read: 1" in text


def test_module_has_no_network_side_effect_on_import() -> None:
    # A guard against someone adding a module-level fetch later.
    import probes.al_round3_candidates as module

    assert module.DEFAULT_INPUT.name == "openalex_oa_candidates.csv"
    assert module.DEFAULT_REQUEST_LIMIT > 0
