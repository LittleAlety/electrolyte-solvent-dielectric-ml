"""Offline unit tests for the DDBST free-layer probe.

Everything here runs without network: the HTTP layer is injected as ``http_get_fn``
and every parser is exercised against canned payloads that reproduce the *real*
markup quirks observed on the live site:

- the first ``<td>`` of every table row is never closed, so splitting on ``</td>``
  silently mis-aligns columns;
- free-search result rows are monospace columns padded with ``&nbsp;`` runs, so a
  CAS-less multi-word name ("Tap water") is mis-filed as formula ``Tap`` / name
  ``water`` if you split on single spaces -- which then makes several distinct
  components collide on the name "water" and kills the exact match;
- the ``Statistics`` page carries a legend table that repeats every bank code, so a
  naive row scan returns each bank twice and the first copies have no numbers;
- larger systems list one DDB# per component, ``<br />``-joined, so an
  ``str.isdigit()`` check drops every binary and ternary row.

The failure-mode group pins that a dead network, an exhausted budget or an offline
run yields *no invented numbers* and no asserted verdicts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from probes.ddb_free_search_probe import (
    APP_URL,
    DDB_SEARCH_URL,
    ONLINE_URL,
    ROBOTS_URL,
    SITEMAP_INDEX_URL,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    ResponseCache,
    classify_url,
    clean,
    count_permittivity_mentions,
    extract_free_calculator_properties,
    extract_property_keywords,
    extract_supported_banks,
    find_export_links,
    find_no_data_statement,
    find_online_app_link,
    find_property,
    has_login_marker,
    join_names,
    load_roster_names,
    name_signature,
    normalise_name,
    parse_component_count,
    parse_component_options,
    parse_details_identity,
    parse_pure_property_table,
    parse_search_hits,
    parse_search_total,
    parse_sitemap_locs,
    parse_statistics_table,
    parse_systems_page,
    pick_exact_component,
    run_probe,
    sitemap_family,
    split_option_label,
    strip_tags,
    write_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

DDB_SEARCH_HTML = """
<html><body>
<h1>Information about the Online DDB Search</h1>
<p>The online DDB search now allows everybody world-wide to search the content of the
Dortmund Data Bank online for suitable information. This DDB online search does not
reveal any data but allows to send a mail to DDBST for requesting further information.</p>
<h3><a href="http://ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe">Start Online DDB Search</a></h3>
<h2>Supported Data Banks</h2>
<ul>
<li>Vapor-liquid equilibria</li>
<li>Thermal conductivities</li>
<li>Dielectric constants</li>
<li>Gas hydrate data</li>
</ul>
<p>Terms and Conditions of Use</p>
<p>The content information is freely available and no copyright is reserved for the search results.</p>
</body></html>
"""

ONLINE_HTML = """
<html><body>
<h2>DDB Online Search</h2>
<p>The online DDB search now allows everybody world-wide to search the content of the
Dortmund Data Bank online for suitable information. This DDB online search does not
present any data but allows sending a mail to DDBST for requesting further information.</p>
<h2>Online Calculation</h2>
</body></html>
"""

CALCULATION_HTML = """
<html><body>
<p>The current implementation of the online-calculation presents separate pages for each
of the following properties in a new window:</p>
<ul>
<li>Vapor pressure calculation by the Antoine equation</li>
<li>Liquid density calculation by the DIPPR 105 equation</li>
<li>Liquid dynamic viscosity calculation by the Vogel equation</li>
<li>Surface tension calculation by the DIPPR 106 equation</li>
<li>Heat of vaporization calculation by the PPDS12 equation</li>
</ul>
<p>The parameters for the equations have been fitted to experimental data.</p>
</body></html>
"""

MIXTURE_DIELECTRIC_HTML = """
<html><body>
<h1>Mixture Dielectric Constants</h1>
<p>Pure component dielectric constants have been part of the PCP data bank from its start
in 1994 but the mixture dielectric constants haven not been collected systematically.</p>
<p>A list of systems is available in our DDB Online Search system.</p>
</body></html>
"""

ROBOTS_TXT = "User-agent: *\nDisallow: /contao/\nSitemap: http://www.ddbst.com/DDBonlinesitemapindex.xml\n"

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset><url><loc>http://www.ddbst.com/sitemaps/DDBonlinesitemaps/cassitemap0.xml.gz</loc></url>
<url><loc>http://www.ddbst.com/sitemaps/DDBonlinesitemaps/pcpsitemap0.xml.gz</loc></url></urlset>
"""

APP_ENTRY_HTML = """
<html><body>
<h2>DDB Component Search</h2>
<form method="post" action="http://ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe">
<input type="text" name="ddbnumber">
<input type="text" name="name">
<input type="text" name="casn">
<input type="text" name="formula">
<input type="text" name="smiles">
<input name="submit" value="Search" type="submit">
</form>
<a href="http://ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe?submit=Statistics">
Overall Statistics on Systems, Sets, and Points</a>
</body></html>
"""

STATISTICS_HTML = """
<html><body><table class="tableformat"><tbody>
<tr><td class="cellformat">LLE</td><td class="cellformat">16360 sets<br />103280 points<br />6345 systems</td>
<td class="cellformat">24155 sets<br />262966 points<br />8851 systems</td>
<td class="cellformat">3131 sets<br />36791 points<br />1458 systems</td>
<td class="cellformat">273 sets<br />3177 points<br />156 systems</td>
<td class="cellformat">43919 sets<br />406214 points<br />16810 systems</td></tr>
<tr><td class="cellformat"><a href="/ddb-mdec.html">MDEC</a></td>
<td class="cellformat">263 sets<br /> 2244 points<br /> 50 components</td>
<td class="cellformat">10544 sets<br /> 90598 points<br /> 3881 systems</td>
<td class="cellformat">735 sets<br /> 6145 points<br /> 341 systems</td>
<td class="cellformat">6 sets<br /> 46 points<br /> 4 systems</td>
<td class="cellformat">27 sets<br /> 138 points<br /> 21 systems</td></tr>
<tr><td class="cellformat">PCP</td><td class="cellformat">468090 sets<br />2604876 points<br />91273 components</td>
<td class="cellformat">468090 sets<br />2604876 points<br />91273 systems</td><td></td><td></td><td></td></tr>
</tbody></table>
<table><tbody>
<tr><td class="cellformat">LLE</td><td class="cellformat">Liquid-Liquid Equilibria (Miscibility Gaps)</td></tr>
<tr><td class="cellformat">MDEC</td><td class="cellformat">Mixture Dielectric Constants</td></tr>
</tbody></table>
</body></html>
"""

SYSTEMS_HTML = """
<html><body>
<p>List of Systems for Mixture Dielectric Constants</p>
<p>4297 systems with 11575 data set/s and 99171 data point/s found</p>
<h3 id="Pure@Components">Pure Components</h3>
<div><table class="tableformat"><tbody>
<tr class="thformat"><th>No.</th><th>DDB#s</th><th>Components</th><th>Data Sets</th>
<th>Data Points</th><th>Details?</th></tr>
<tr><td class="cellformat">1<td class="cellformat">4</td>
<td class="cellformat"><a href="x?systemcomplist=4">Acetone</a></td>
<td class="cellformat">2</td><td class="cellformat">12</td>
<td class="cellformat"><a href="x?submit=Details&amp;systemcomplist=4">Details</a></td></tr>
<tr><td class="cellformat">2<td class="cellformat">8</td>
<td class="cellformat"><a href="x?systemcomplist=8">1,2-Ethanediol</a></td>
<td class="cellformat">26</td><td class="cellformat">277</td>
<td class="cellformat">Details</td></tr>
<tr><td class="cellformat">3<td class="cellformat">174</td>
<td class="cellformat"><a href="x?systemcomplist=174">Water</a></td>
<td class="cellformat">8</td><td class="cellformat">45</td>
<td class="cellformat">Details</td></tr>
</tbody></table></div>
<h3 id="Binary@Mixtures">Binary Mixtures</h3>
<div><table class="tableformat"><tbody>
<tr><td class="cellformat">1<td class="cellformat">1<br />31</td>
<td class="cellformat"><a href="x">Acetaldehyde</a><br /><a href="y">Benzene</a></td>
<td class="cellformat">1</td><td class="cellformat">7</td>
<td class="cellformat">Details</td></tr>
</tbody></table></div>
<h3 id="Ternary@Mixtures">Ternary Mixtures</h3><div></div>
<h3 id="Quaternary@Mixtures">Quaternary Mixtures</h3><div></div>
<h3 id="Quinary@Mixtures">Quinary Mixtures</h3><div></div>
<h3 id="Other@Mixtures">Other Mixtures</h3><div></div>
</body></html>
"""

COMPOUND_SEARCH_HTML = """
<html><body>
<h2>Component Search Result</h2>
<p><strong>24 Components found:</strong></p>
<form method="post" name="AddCompForm"><select name="complist" size="12">
<option selected value= "174 1">&nbsp;&nbsp;[174]&nbsp;&nbsp;&nbsp;7732-18-5&nbsp;&nbsp;H2O&nbsp;&nbsp;Water</option>
<option value= "2868 1">&nbsp;[2868]&nbsp;&nbsp;14940-63-7&nbsp;&nbsp;HDO&nbsp;&nbsp;Water-D1</option>
<option value= "94498 1">[94498]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Tap water</option>
<option value= "48834 1">[48834]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Mineral water</option>
<option value= "20174 1">[20174]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Seawater</option>
</select></form>
</body></html>
"""

DETAILS_HTML = """
<html><head>
<meta name="keywords" content="Dortmund Data Bank,Density,Dielectric Constant,Molar Polarization,Water" />
<title>Water | Details | Dortmund Data Bank (DDB)</title></head>
<body>
<h2>Query</h2>
<p>A quote for experimental literature data about the component can be obtained via email.</p>
<table><tbody><tr><th>DDB#</th><th>Name</th><th>CAS-RN</th><th>Formula</th></tr>
<tr><td class="cellformat">174</td><td class="cellformat">Water</td>
<td class="cellformat">7732-18-5</td><td class="cellformat">H2O</td></tr></tbody></table>
<h2>Pure Component Data</h2>
<table class="tableformat"><tbody>
<tr class="thformat"><th>Property</td><th>Points</td><th>Sets</td><th>Temperature Range</td>
<th>States</td><th>Sets</td></tr>
<tr><td class="cellformat">Density</td><td class="cellformattextright">23764</td>
<td class="cellformattextright">2495</td><td class="cellformattextright">20-1273 K</td>
<td class="cellformat">Liquid</td><td class="cellformattextright">2068</td></tr>
<tr><td></td><td></td><td></td><td></td><td class="cellformat">Gas/Vapor</td>
<td class="cellformattextright">173</td></tr>
<tr><td class="cellformat">Dielectric Constant</td><td class="cellformattextright">1569</td>
<td class="cellformattextright">273</td><td class="cellformattextright">67-823 K</td>
<td class="cellformat">Liquid</td><td class="cellformattextright">250</td></tr>
<tr><td></td><td></td><td></td><td></td><td class="cellformat">Further States</td>
<td class="cellformattextright">23</td></tr>
</tbody></table>
</body></html>
"""


def url_key(url: str, params: dict[str, str] | None = None) -> str:
    if not params:
        return url
    return url + "?" + "&".join(f"{key}={value}" for key, value in params.items())


class FakeHttp:
    """Injected HTTP layer: canned bodies keyed by URL plus query."""

    def __init__(self, pages: dict[str, str], *, failing: set[str] | None = None,
                 default_status: int = 200) -> None:
        self.pages = pages
        self.failing = failing or set()
        self.default_status = default_status
        self.calls: list[str] = []

    def __call__(self, url, *, session=None, budget=None, params=None, note="", **kwargs):
        if budget is not None:
            budget.consume(url)
        key = url_key(url, params)
        self.calls.append(key)
        if any(target in key for target in self.failing):
            return HttpResponse(
                url=key, status=None, body="", bytes_received=0, seconds=0.0,
                error="ConnectTimeout: injected", note=note,
            )
        status = self.default_status
        body = self.pages.get(key, self.pages.get(url, ""))
        if body == "":
            status = 404
        return HttpResponse(
            url=key, status=status, body=body, bytes_received=len(body), seconds=0.0, note=note
        )


def standard_pages() -> dict[str, str]:
    return {
        ROBOTS_URL: ROBOTS_TXT,
        DDB_SEARCH_URL: DDB_SEARCH_HTML,
        ONLINE_URL: ONLINE_HTML,
        "https://www.ddbst.com/calculation.html": CALCULATION_HTML,
        "https://www.ddbst.com/ddb-mdec.html": MIXTURE_DIELECTRIC_HTML,
        SITEMAP_INDEX_URL: SITEMAP_INDEX_XML,
        APP_URL: APP_ENTRY_HTML,
        url_key(APP_URL, {"submit": "Statistics"}): STATISTICS_HTML,
        url_key(APP_URL, {"submit": "DDBSystems", "databank": "MDEC"}): SYSTEMS_HTML,
        url_key(APP_URL, {"submit": "Search", "name": "water"}): COMPOUND_SEARCH_HTML,
        url_key(APP_URL, {"submit": "Details", "systemcomplist": "174"}): DETAILS_HTML,
    }


# --------------------------------------------------------------------------- helpers


def test_strip_tags_and_clean_collapse_markup():
    assert strip_tags("<td>a&nbsp;b</td>") == " a b "
    assert clean("  a \n b  ") == "a b"


def test_classify_url_sorts_marketing_from_record_pages():
    assert classify_url("https://www.ddbst.com/ddb-search.html") == "marketing_page"
    assert classify_url("https://www.ddbst.com/en/EED/PCP/DEC_C4.php") == "record_like"
    assert classify_url("https://www.ddbst.com/") == "root"


def test_sitemap_family_strips_the_index_number():
    assert sitemap_family("http://x/sitemaps/DDBonlinesitemaps/pcpsitemap12.xml.gz") == "pcpsitemap"


def test_parse_sitemap_locs_reads_every_loc():
    assert len(parse_sitemap_locs(SITEMAP_INDEX_XML)) == 2


# ------------------------------------------------------------------- marketing side


def test_find_no_data_statement_matches_both_vendor_phrasings():
    for html, verb in ((DDB_SEARCH_HTML, "reveal"), (ONLINE_HTML, "present")):
        statement = find_no_data_statement(html)
        assert statement is not None
        assert f"does not {verb} any data" in statement
        assert "a mail to DDBST" in statement


def test_find_no_data_statement_returns_none_when_the_claim_is_absent():
    assert find_no_data_statement("<html><body>Dielectric constants</body></html>") is None


def test_extract_supported_banks_stops_at_the_terms_line():
    banks = extract_supported_banks(DDB_SEARCH_HTML)
    assert "Dielectric constants" in banks
    assert "Gas hydrate data" in banks
    assert not any("Terms and Conditions" in bank for bank in banks)


def test_extract_free_calculator_properties_lists_five_and_none_is_permittivity():
    properties = extract_free_calculator_properties(CALCULATION_HTML)
    assert len(properties) == 5
    assert not any("dielectric" in prop.lower() for prop in properties)


def test_extract_free_calculator_properties_survives_a_wrapped_anchor_sentence():
    """The source may wrap the long intro sentence; the <li> fallback must catch it."""
    wrapped = CALCULATION_HTML.replace(
        "presents separate pages for each\nof the following properties",
        "presents separate pages for each\nof the following properties",
    ).replace(
        "<p>The current implementation of the online-calculation presents separate pages for each\nof the following properties in a new window:</p>",
        "<p>The current implementation of the online-calculation presents separate pages\nfor each of the following\nproperties in a new window:</p>",
    )
    assert "for each of the following\nproperties" in wrapped
    properties = extract_free_calculator_properties(wrapped)
    assert len(properties) == 5
    assert properties[0].startswith("Vapor pressure calculation")


def test_extract_free_calculator_properties_returns_empty_when_no_calculator_page():
    assert extract_free_calculator_properties("<html><p>nothing here</p></html>") == []


def test_count_permittivity_mentions_and_login_marker():
    assert count_permittivity_mentions(MIXTURE_DIELECTRIC_HTML) >= 2
    assert count_permittivity_mentions(CALCULATION_HTML) == 0
    assert has_login_marker(APP_ENTRY_HTML) is False
    assert has_login_marker("<form>Password: <input name='p'></form>") is True


def test_find_export_links_ignores_the_export_compliance_navigation_entry():
    html = '<a href="https://www.ddbst.com/export-compliance.html">Export Compliance</a>'
    assert find_export_links(html) == []
    html_ok = '<a href="/download/ddb.csv">data</a>'
    assert find_export_links(html_ok) == ["/download/ddb.csv"]


def test_find_online_app_link_extracts_the_entry_point():
    assert find_online_app_link(DDB_SEARCH_HTML) == APP_URL
    assert find_online_app_link("<html></html>") is None


def test_parse_search_hits_and_total():
    html = ('<p class="header">Results 1 - 11 of 11 for <strong>dielectric</strong></p>'
            '<h3><a href="http://www.ddbst.de/ddb-mdec.html" title="Mixture Dielectric Constants">x</a></h3>')
    assert parse_search_total(html) == 11
    hits = parse_search_hits(html)
    assert hits == [{"url": "http://www.ddbst.de/ddb-mdec.html", "title": "Mixture Dielectric Constants"}]


# ------------------------------------------------------------------------ app side


def test_parse_component_count_and_options():
    assert parse_component_count(COMPOUND_SEARCH_HTML) == 24
    options = parse_component_options(COMPOUND_SEARCH_HTML)
    assert len(options) == 5
    assert options[0]["ddb_number"] == 174
    assert options[0]["cas"] == "7732-18-5"
    assert options[0]["formula"] == "H2O"
    assert options[0]["name"] == "Water"


def test_split_option_label_keeps_cas_less_multiword_names_intact():
    """The trap: splitting on single spaces turns "Tap water" into formula "Tap"."""
    parsed = split_option_label("[94498]                    Tap water")
    assert parsed["formula"] == ""
    assert parsed["name"] == "Tap water"
    assert parsed["cas"] == ""


def test_pick_exact_component_requires_a_unique_exact_hit():
    options = parse_component_options(COMPOUND_SEARCH_HTML)
    picked = pick_exact_component(options, "water")
    assert picked is not None and picked["ddb_number"] == 174
    assert pick_exact_component(options, "aqua") is None
    duplicated = [{"name": "Water", "ddb_number": 1}, {"name": "water", "ddb_number": 2}]
    assert pick_exact_component(duplicated, "water") is None


def test_parse_details_identity_and_keywords():
    identity = parse_details_identity(DETAILS_HTML)
    assert identity["ddb_number"] == "174"
    assert identity["cas"] == "7732-18-5"
    keywords = extract_property_keywords(DETAILS_HTML)
    assert "Dielectric Constant" in keywords


def test_parse_pure_property_table_handles_unclosed_cells_and_continuations():
    properties = parse_pure_property_table(DETAILS_HTML)
    density = find_property(properties, "Density")
    assert density["points"] == 23764 and density["sets"] == 2495
    assert density["temperature_range"] == "20-1273 K"
    assert {"state": "Gas/Vapor", "sets": 173} in density["states"]
    dielectric = find_property(properties, "Dielectric Constant")
    assert dielectric["points"] == 1569 and dielectric["sets"] == 273
    assert dielectric["temperature_range"] == "67-823 K"
    assert dielectric["states"] == [
        {"state": "Liquid", "sets": 250},
        {"state": "Further States", "sets": 23},
    ]
    assert find_property(properties, "Not A Property") is None


def test_parse_statistics_table_dedupes_the_legend_and_reads_the_units():
    banks = parse_statistics_table(STATISTICS_HTML)
    codes = [row["code"] for row in banks]
    assert codes == ["LLE", "MDEC", "PCP"]
    mdec = next(row for row in banks if row["code"] == "MDEC")
    assert mdec["columns"][0]["sets"] == 263
    assert mdec["columns"][0]["points"] == 2244
    assert mdec["columns"][0]["unit"] == "components"
    assert mdec["columns"][0]["unit_count"] == 50
    assert mdec["columns"][1]["unit"] == "systems"


def test_parse_systems_page_reads_pure_and_multi_component_rows():
    parsed = parse_systems_page(SYSTEMS_HTML)
    assert parsed["title"] == "Mixture Dielectric Constants"
    assert (parsed["system_count"], parsed["data_sets"], parsed["data_points"]) == (4297, 11575, 99171)
    pure = parsed["sections"]["Pure Components"]
    assert [row["components"] for row in pure] == ["Acetone", "1,2-Ethanediol", "Water"]
    assert sum(row["data_sets"] for row in pure) == 36
    binary = parsed["sections"]["Binary Mixtures"]
    assert len(binary) == 1
    assert binary[0]["ddb_numbers"] == "1,31"


# ----------------------------------------------------------------------- name join


def test_name_signature_is_locant_order_insensitive_but_keeps_isomers_apart():
    assert name_signature("2-Butanol") == name_signature("butan-2-ol")
    assert name_signature("1-butanol") != name_signature("2-butanol")


def test_join_names_reports_tier1_tier2_and_residual_candidates():
    roster = ["water", "butan-2-ol", "ethanol"]
    joined = join_names(["Water", "2-Butanol", "Nitromethane"], roster)
    assert joined["matched_count"] == 1
    assert joined["matched"][0]["roster_name"] == "water"
    assert joined["signature_matched_count"] == 1
    assert joined["signature_matched"][0]["roster_name"] == "butan-2-ol"
    assert joined["unmatched"] == ["Nitromethane"]


def test_join_names_never_grows_the_matched_set_without_a_roster():
    assert join_names(["whatever"], [])["matched_count"] == 0


def test_normalise_name_strips_case_and_punctuation():
    assert normalise_name("1,2-Ethanediol") == "12ethanediol"


# ------------------------------------------------------------------- infrastructure


def test_request_budget_raises_once_spent():
    budget = RequestBudget(limit=1)
    budget.consume("a")
    with pytest.raises(BudgetExhausted):
        budget.consume("b")
    assert budget.exhausted and budget.remaining == 0


def test_response_cache_round_trips_and_skips_failures(tmp_path: Path):
    cache = ResponseCache(tmp_path)
    good = HttpResponse(url="u", status=200, body="body", bytes_received=4, seconds=0.0)
    cache.store("u", {"a": "b"}, good)
    loaded = cache.load("u", {"a": "b"})
    assert loaded is not None and loaded.body == "body" and loaded.status == 200
    assert cache.load("u", {"a": "c"}) is None
    cache.store("u", {"a": "d"}, HttpResponse("u", 404, "", 0, 0.0))
    assert cache.load("u", {"a": "d"}) is None


def test_write_summary_uses_lf_and_round_trips(tmp_path: Path):
    target = tmp_path / "summary.json"
    write_summary({"probe": "x", "中文": "ok"}, target)
    raw = target.read_bytes()
    assert b"\r\n" not in raw
    assert json.loads(raw.decode("utf-8"))["中文"] == "ok"


def test_roster_names_loads_the_frozen_roster():
    names = load_roster_names()
    assert len(names) == 246
    assert "water" in names


# ------------------------------------------------------------------- live pipeline


def test_run_probe_offline_makes_no_requests_and_claims_nothing():
    summary = run_probe(offline=True, sleep_seconds=0.0, roster_names=["water"])
    assert summary["mode"] == "offline"
    assert summary["budget"]["used"] == 0
    assert summary["counts"]["http_requests"] == 0
    assert summary["requests"] == []
    for key in ("q1_free_layer_exists", "q2_contains_permittivity_temperature",
                "q3_machine_readable", "q4_net_new_compounds"):
        assert summary["answers"][key]["verdict"] == "unknown_no_requests_made"
    assert summary["answers"]["q2_contains_permittivity_temperature"]["permittivity_values_read"] == 0


def test_run_probe_live_pipeline_produces_evidence_backed_verdicts():
    fake = FakeHttp(standard_pages())
    summary = run_probe(
        http_get_fn=fake, sleep_seconds=0.0, roster_names=["water", "Acetone"],
        connect_probe_fn=lambda host, port, timeout: {"host": host, "port": port,
                                                      "dns_ips": ["1.2.3.4"], "connect": "ok"},
    )
    answers = summary["answers"]
    assert answers["q1_free_layer_exists"]["verdict"] == "exists_free_of_charge_anonymous_and_usable_with_retries"
    assert answers["q1_free_layer_exists"]["app_search_axes"] == [
        "ddbnumber", "name", "casn", "formula", "smiles"
    ]
    q2 = answers["q2_contains_permittivity_temperature"]
    assert q2["verdict"] == "temperature_resolved_coverage_visible_but_no_values_returned"
    assert q2["permittivity_values_read"] == 0
    assert q2["temperature_values_read"] == 0
    assert q2["dielectric_property_rows"] == [{
        "compound": "water", "ddb_number": "174", "property": "Dielectric Constant",
        "points": 1569, "sets": 273, "temperature_range": "67-823 K",
        "states": [{"state": "Liquid", "sets": 250}, {"state": "Further States", "sets": 23}],
    }]
    assert q2["dielectric_bank_statistics"]["columns"][0]["unit_count"] == 50
    assert q2["dielectric_bank_system_list"]["pure_component_count"] == 3
    assert answers["q3_machine_readable"]["verdict"] == "html_tables_only_no_export_endpoint"
    q4 = answers["q4_net_new_compounds"]
    assert q4["net_new_compounds"] == 0
    assert q4["verdict"] == "coverage_metadata_only_name_level_candidates"
    phases = answers["phases_completed"]
    assert phases["app_entry_answered"] and phases["statistics_answered"]
    assert phases["compound_details_answered"] == 1


def test_run_probe_records_the_dead_sub_sitemap_family_without_crashing():
    fake = FakeHttp(standard_pages())
    summary = run_probe(http_get_fn=fake, sleep_seconds=0.0, roster_names=[],
                        connect_probe_fn=lambda host, port, timeout: {"host": host, "port": port,
                                                                     "dns_ips": [], "connect": "timeout"})
    assert summary["answers"]["sitemap_sub_families_advertised"] == 2
    assert summary["answers"]["sub_sitemap_reachable_samples"] == 0
    assert all(item["status"] == 404 for item in summary["sub_sitemap_sample"])


def test_run_probe_with_every_app_call_failing_claims_nothing():
    fake = FakeHttp(standard_pages(), failing={APP_URL})
    summary = run_probe(http_get_fn=fake, sleep_seconds=0.0, roster_names=["water"],
                        connect_probe_fn=lambda host, port, timeout: {"host": host, "port": port,
                                                                     "dns_ips": [], "connect": "timeout"})
    answers = summary["answers"]
    assert answers["q1_free_layer_exists"]["verdict"] == (
        "exists_and_free_of_charge_but_unreachable_from_this_environment"
    )
    assert answers["q2_contains_permittivity_temperature"]["permittivity_values_read"] == 0
    assert answers["q2_contains_permittivity_temperature"]["dielectric_property_rows"] == []
    assert answers["q4_net_new_compounds"]["net_new_compounds"] == 0
    assert summary["failed_attempts"]


def test_run_probe_stops_at_the_budget_and_says_so():
    fake = FakeHttp(standard_pages())
    summary = run_probe(http_get_fn=fake, sleep_seconds=0.0, roster_names=[],
                        budget=RequestBudget(limit=3),
                        connect_probe_fn=lambda host, port, timeout: {"host": host, "port": port,
                                                                     "dns_ips": [], "connect": "timeout"})
    assert summary["budget"]["exhausted"] is True
    assert summary["budget"]["stopped_early"]
    assert summary["budget"]["used"] == 3
    assert len(fake.calls) == 3


def test_run_probe_replays_from_cache_without_spending_budget(tmp_path: Path):
    cache = tmp_path / "cache"
    first = run_probe(http_get_fn=FakeHttp(standard_pages()), sleep_seconds=0.0,
                      roster_names=["water"], cache_dir=cache)
    assert first["cache"]["hits"] == 0
    budget = RequestBudget(limit=60)
    second = run_probe(http_get_fn=FakeHttp({}), sleep_seconds=0.0, roster_names=["water"],
                       cache_dir=cache, budget=budget)
    assert second["cache"]["hits"] > 0
    assert second["answers"]["q2_contains_permittivity_temperature"]["permittivity_values_read"] == 0
    assert second["answers"]["q2_contains_permittivity_temperature"]["dielectric_property_rows"]


def test_importing_the_module_performs_no_network_io():
    code = (
        # requests pulls in ssl, which subclasses socket.socket at import time, so the
        # heavy dependency is loaded first and only then is the socket module blocked.
        "import requests, socket\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise RuntimeError('network access during import')\n"
        "socket.socket = _blocked\n"
        "socket.getaddrinfo = _blocked\n"
        "socket.create_connection = _blocked\n"
        "import probes.ddb_free_search_probe as probe\n"
        "print(probe.APP_URL)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().endswith("onlineddboverview.exe")