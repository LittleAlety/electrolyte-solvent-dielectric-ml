"""Unit tests for the ILThermo (NIST SRD 147) probe.

Everything here runs offline: the HTTP layer is injected via ``http_get``, so every
parser, ranking rule and verdict is exercised against canned payloads that mirror
the real response shapes observed on the live site.

Two groups carry most of the weight:

- the "traps" group pins the failure modes that would silently produce wrong
  numbers (reading ``data`` instead of ``res``; guessing the opaque ``prp`` key;
  treating a shared molecular formula as a compound match even though
  constitutional isomers share one).
- the honest-failure group pins that a dead network or an exhausted budget yields
  no invented numbers at all: failures are recorded, verdicts go False.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.ilthermo_probe import (
    DATASET_PATH,
    DISCOVERY_TARGETS,
    PROPERTY_LIST_PATH,
    SEARCH_PATH,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    choose_sample,
    classify_compound,
    extract_observations,
    find_property_keys,
    formula_signature,
    http_get_with_backoff,
    is_ionic_liquid_name,
    load_roster,
    next_backoff_delay,
    normalize_name,
    parse_dataset_payload,
    parse_formula_counts,
    parse_html_formula,
    parse_property_list,
    parse_retry_after,
    parse_search_payload,
    permittivity_column_index,
    property_key_names,
    run_probe,
    spread,
    summarize_set,
    temperature_column_index,
    write_summary,
)

BASE = "https://ilthermo.boulder.nist.gov"


# --------------------------------------------------------------------------- #
# Canned payloads mirroring the real response shapes
# --------------------------------------------------------------------------- #


def _ilprpls() -> dict:
    """Property list where key/name are index-paired, exactly as the server sends it.

    The pairing is the whole trap: TGKW is 'Relative permittivity' because it sits at
    the same index, not because of anything in the key itself.
    """
    return {
        "cprmsg": "&copy; test",
        "plist": [
            {"cls": "Transport properties", "key": ["tplC"], "name": ["Viscosity"]},
            {
                "cls": "Refraction, surface tension, and speed of sound",
                "key": ["IzOV", "TGKW", "JYHK"],
                "name": ["Interfacial tension", "Relative permittivity", "Speed of sound"],
            },
        ],
    }


SEARCH_HEADER = [
    "setid",
    "ref",
    "prp",
    "phases",
    "cmp1",
    "cmp2",
    "cmp3",
    "np",
    "nm1",
    "nm2",
    "nm3",
]


def _search_row(
    setid: str,
    name: str,
    datapoints: int,
    *,
    reference: str = "Bennett et al. (2019)",
    property_name: str = "Relative permittivity",
    second: str = "0",
) -> list:
    return [
        setid,
        reference,
        property_name,
        "Liquid",
        "AAheIp",
        "0",
        "0",
        datapoints,
        name,
        second,
        "0",
    ]


def _search_payload(rows: list) -> dict:
    return {"cnt": len(rows), "errors": [], "header": SEARCH_HEADER, "res": rows}


def _dataset_payload(
    name: str,
    formula: str,
    data: list,
    dhead: list | None = None,
    *,
    setid: str = "s1",
    reference: str = "Bennett, E. L.; Song, C.; Huang, Y.; Xiao, J. (2019) J. Mol. Liq. 294, 111571.",
    extra_components: list | None = None,
) -> dict:
    return {
        "title": f"Refraction, surface tension, and speed of sound: Relative permittivity ({setid})",
        "ref": {"title": "Measured relative complex permittivities", "full": reference},
        "dhead": dhead
        or [
            ["Temperature, K", None],
            ["Pressure, kPa", None],
            ["Frequency, MHz", "Liquid"],
            ["Relative permittivity at zero frequency", "Liquid"],
        ],
        "components": [{"name": name, "mw": "1.00", "idout": "AAheIp", "formula": formula}]
        + list(extra_components or []),
        "data": data,
        "expmeth": "Coaxial cylinder capacitor",
    }


def _json(payload: dict) -> HttpResponse:
    return HttpResponse(
        url="https://ilthermo.boulder.nist.gov/canned",
        status=200,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _key(path: str, params: dict | None = None) -> tuple:
    return (BASE + path, tuple(sorted((params or {}).items())))


def _transport(routes: dict, log: list | None = None):
    """Return an injectable http_get backed by a route table."""

    def http_get(url, params=None):
        if log is not None:
            log.append((url, dict(params or {})))
        key = (url, tuple(sorted((params or {}).items())))
        if key not in routes:
            return HttpResponse(
                url=url,
                status=404,
                body=b"<html>not found</html>",
                headers={"content-type": "text/html"},
            )
        value = routes[key]
        return value() if callable(value) else value

    return http_get


def _noop_sleep(_seconds: float) -> None:
    return None

def _standard_routes(datasets: dict) -> dict:
    """Route table for a full probe run: discovery, census, sample, series check."""
    routes = {}
    for _label, path, params in DISCOVERY_TARGETS:
        routes[_key(path, params)] = _json({"ok": True})
    routes[_key(PROPERTY_LIST_PATH)] = _json(_ilprpls())
    routes[_key(SEARCH_PATH, {"prp": "TGKW"})] = _json(_search_payload(_ALL_ROWS))
    routes[_key(SEARCH_PATH, {"prp": "TGKW", "ncmp": "1"})] = _json(_search_payload(_PURE_ROWS))
    routes[_key(SEARCH_PATH, {"prp": "IzOV"})] = _json(
        _search_payload([_search_row("c1", "IL one", 5, property_name="Interfacial tension")])
    )
    for setid, payload in datasets.items():
        routes[_key(DATASET_PATH, {"set": setid})] = _json(payload)
    return routes


# Three pure compounds of differing size plus one binary mixture, so the sample
# spreading and the pure-vs-mixture distinction are both exercised.
_PURE_ROWS = [
    _search_row("s1", "imidazolium one", 18),
    _search_row("s4", "imidazolium three", 5),
    _search_row("s2", "imidazolium two", 1),
]
_ALL_ROWS = _PURE_ROWS + [
    _search_row("s3", "imidazolium one", 30, second="methanol"),
]

_TWO_TEMPERATURE_DATA = [
    [["0"], ["293.15"], ["101.325"], ["33.9", "1.6"]],
    [["0.006"], ["303.15"], ["101.325"], ["33.2", "1.5"]],
    [["0.012"], ["313.15"], ["101.325"], ["32.2", "1.5"]],
]
_SINGLE_TEMPERATURE_DATA = [
    [["298.15"], ["101.325"], ["1000"], ["6.8", "0.6"]],
    [["298.15"], ["101.325"], ["2000"], ["6.3", "0.6"]],
]

_DATASETS = {
    "s1": _dataset_payload(
        "imidazolium one",
        "C<SUB>8</SUB>H<SUB>15</SUB>F<SUB>6</SUB>N<SUB>2</SUB>P",
        _SINGLE_TEMPERATURE_DATA,
    ),
    "s2": _dataset_payload(
        "imidazolium two",
        "C8H15F6N2P",
        [[["298.15"], ["101.325"], ["3.15", "0.1"]]],
        dhead=[["Temperature, K", None], ["Pressure, kPa", None], ["Relative permittivity", "Liquid"]],
    ),
    "s3": _dataset_payload(
        "imidazolium one",
        "C8H15ClN2",
        _TWO_TEMPERATURE_DATA,
        dhead=[
            ["Weight fraction of imidazolium one", "Liquid"],
            ["Temperature, K", None],
            ["Pressure, kPa", None],
            ["Relative permittivity at zero frequency", "Liquid"],
        ],
        extra_components=[{"name": "methanol", "mw": "32.04", "idout": "AAGIgg", "formula": "CH<SUB>4</SUB>O"}],
    ),
    "s4": _dataset_payload(
        "imidazolium three",
        "C6H11BF4N2",
        [[["296.0"], ["101.325"], ["2.87"]]],
        dhead=[["Temperature, K", None], ["Pressure, kPa", None], ["Relative permittivity", "Liquid"]],
    ),
}


@pytest.fixture()
def roster_csv(tmp_path: Path) -> Path:
    """A miniature roster: one name match, plus a formula that collides with s2."""
    path = tmp_path / "roster.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["inchikey", "smiles", "name", "gate_flags"])
        writer.writerow(
            ["KEYONE-UHFFFAOYSA-N", "Nc1ccccc1", "imidazolium one", "zero_frequency|pure_component"]
        )
        writer.writerow(
            [
                "KEYTWO-UHFFFAOYSA-N",
                "CCCC",
                "isomer partner",
                "zero_frequency|pure_component|out_of_scope_ionic_or_organometallic",
            ]
        )
        writer.writerow(["KEYTHREE-UHFFFAOYSA-N", "O", "plain solvent", "zero_frequency"])
    return path


def _fake_formula_of_smiles(smiles: str) -> str | None:
    return {"Nc1ccccc1": "C6H7N", "CCCC": "C8H15F6N2P", "O": "H2O"}.get(smiles)


def _run(roster_csv: Path, **overrides):
    datasets = overrides.pop("datasets", _DATASETS)
    routes = _standard_routes(datasets)
    routes.update(overrides.pop("routes", {}))
    return run_probe(
        http_get=_transport(routes),
        sleep=_noop_sleep,
        roster_path=roster_csv,
        formula_of_smiles=_fake_formula_of_smiles,
        now="2026-01-01T00:00:00Z",
        **overrides,
    )

# --------------------------------------------------------------------------- #
# Politeness primitives
# --------------------------------------------------------------------------- #


def test_parse_retry_after_reads_header_case_insensitively():
    assert parse_retry_after({"Retry-After": "39"}) == 39.0
    assert parse_retry_after({"retry-after": "2.5"}) == 2.5


def test_parse_retry_after_rejects_absent_invalid_and_negative():
    assert parse_retry_after({}) is None
    assert parse_retry_after({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
    assert parse_retry_after({"retry-after": "-4"}) is None


def test_next_backoff_delay_prefers_server_hint_over_local_ramp():
    assert next_backoff_delay(0, {"retry-after": "12"}) == 12.0
    assert next_backoff_delay(0, {}) == 5.0
    assert next_backoff_delay(9, {}) == 15.0


def test_next_backoff_delay_honours_a_hint_above_the_local_ramp():
    assert next_backoff_delay(0, {"retry-after": "39"}) == 39.0


def test_next_backoff_delay_caps_a_huge_server_hint():
    assert next_backoff_delay(0, {"retry-after": "9999"}) == 60.0


def test_request_budget_refuses_to_overrun():
    budget = RequestBudget(limit=2)
    budget.consume()
    budget.consume()
    assert budget.remaining == 0
    with pytest.raises(BudgetExhausted):
        budget.consume()


def test_backoff_retries_a_429_then_returns_the_good_response():
    calls = []
    sleeps = []

    def http_get(url, params=None):
        calls.append(url)
        if len(calls) == 1:
            return HttpResponse(url=url, status=429, body=b"", headers={"retry-after": "7"})
        return HttpResponse(url=url, status=200, body=b"{}", headers={})

    response = http_get_with_backoff(
        http_get, "https://x", budget=RequestBudget(limit=5), sleep=sleeps.append
    )
    assert response.status == 200
    assert sleeps == [7.0]
    assert len(calls) == 2


def test_backoff_gives_up_after_the_ramp_and_returns_the_last_failure():
    def http_get(url, params=None):
        return HttpResponse(url=url, status=503, body=b"", headers={})

    budget = RequestBudget(limit=10)
    response = http_get_with_backoff(http_get, "https://x", budget=budget, sleep=_noop_sleep)
    assert response.status == 503
    assert budget.used == 3


def test_backoff_does_not_retry_a_404():
    calls = []

    def http_get(url, params=None):
        calls.append(url)
        return HttpResponse(url=url, status=404, body=b"", headers={})

    response = http_get_with_backoff(
        http_get, "https://x", budget=RequestBudget(limit=5), sleep=_noop_sleep
    )
    assert response.status == 404
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# The traps
# --------------------------------------------------------------------------- #


def test_property_list_pairs_key_and_name_by_index():
    entries = parse_property_list(_ilprpls())
    assert [entry.key for entry in entries] == ["tplC", "IzOV", "TGKW", "JYHK"]
    assert find_property_keys(entries, "Relative permittivity")[0].key == "TGKW"
    assert property_key_names(entries, "TGKW") == ["Relative permittivity"]


def test_property_list_key_is_not_self_describing():
    """A guessed key returns a different property: JYHK is not relative permittivity."""
    entries = parse_property_list(_ilprpls())
    assert property_key_names(entries, "JYHK") == ["Speed of sound"]
    assert find_property_keys(entries, "Speed of sound")[0].key == "JYHK"


def test_property_list_tolerates_missing_blocks():
    assert parse_property_list({}) == []
    assert parse_property_list({"plist": None}) == []
    assert parse_property_list({"plist": [{"cls": "X", "key": ["a"], "name": []}]}) == []


def test_search_payload_reads_rows_from_res_not_data():
    """A payload with populated res and empty data must not read as 'no results'."""
    payload = _search_payload([_search_row("s1", "IL one", 18)])
    payload["data"] = []
    page = parse_search_payload(payload)
    assert page.count == 1
    assert len(page.hits) == 1
    assert page.hits[0].setid == "s1"
    assert page.hits[0].datapoints == 18


def test_search_payload_skips_placeholder_component_names():
    page = parse_search_payload(_search_payload(_ALL_ROWS))
    mixture = next(hit for hit in page.hits if hit.setid == "s3")
    assert mixture.component_names == ("imidazolium one", "methanol")
    assert page.hits[0].component_names == ("imidazolium one",)


def test_search_payload_reports_errors_verbatim():
    payload = _search_payload([])
    payload["errors"] = ["no search parameters provided"]
    assert parse_search_payload(payload).errors == ("no search parameters provided",)


def test_search_payload_survives_an_unparseable_datapoint_count():
    row = _search_row("s1", "IL one", 0)
    row[7] = "n/a"
    assert parse_search_payload(_search_payload([row])).hits[0].datapoints == 0


# --------------------------------------------------------------------------- #
# Chemistry-ish helpers
# --------------------------------------------------------------------------- #


def test_parse_html_formula_strips_sub_tags_and_entities():
    assert parse_html_formula("C<SUB>8</SUB>H<SUB>15</SUB>ClN<SUB>2</SUB>") == "C8H15ClN2"
    assert parse_html_formula("C<SUB>10</SUB>H<SUB>21</SUB>N<SUB>2</SUB>O<SUB>4</SUB>P") == "C10H21N2O4P"
    assert parse_html_formula("") == ""


def test_formula_signature_is_order_insensitive():
    assert formula_signature("C8H15F6N2P") == formula_signature("N2PC8H15F6")
    assert parse_formula_counts("C8H15F6N2P") == {"C": 8, "H": 15, "F": 6, "N": 2, "P": 1}


def test_normalize_name_ignores_case_punctuation_and_unicode_dashes():
    assert normalize_name("1-Butyl-3-methylimidazolium hexafluorophosphate") == normalize_name(
        "1-butyl-3-methylimidazolium hexafluorophosphate"
    )
    assert normalize_name("1,3-dimethylimidazolium dimethyl phosphate") == normalize_name(
        "1,3-dimethylimidazolium dimethylphosphate"
    )
    assert normalize_name("a\u2013b") == normalize_name("a-b")


def test_is_ionic_liquid_name_spots_salts_but_not_plain_solvents():
    assert is_ionic_liquid_name("1-butyl-3-methylimidazolium tetrafluoroborate")
    assert is_ionic_liquid_name("triethylsulfonium bis(trifluoromethylsulfonyl)imide")
    assert is_ionic_liquid_name("choline L-alaninate")
    assert not is_ionic_liquid_name("methanol")
    assert not is_ionic_liquid_name("water")

# --------------------------------------------------------------------------- #
# Dataset parsing and observation extraction
# --------------------------------------------------------------------------- #


def test_dataset_payload_parses_headers_components_and_cells():
    dataset = parse_dataset_payload(_DATASETS["s1"], setid="s1")
    assert dataset.setid == "s1"
    assert dataset.components[0].name == "imidazolium one"
    assert dataset.components[0].formula == "C8H15F6N2P"
    assert dataset.method == "Coaxial cylinder capacitor"
    assert dataset.rows[0][3] == ("6.8", "0.6")


def test_column_locators_find_temperature_permittivity_and_frequency():
    dataset = parse_dataset_payload(_DATASETS["s1"], setid="s1")
    assert temperature_column_index(dataset.column_headers) == 0
    assert permittivity_column_index(dataset.column_headers) == 3
    assert permittivity_column_index(parse_dataset_payload(_DATASETS["s2"], "s2").column_headers) == 2


def test_extract_observations_pulls_temperature_permittivity_and_uncertainty():
    observations = extract_observations(parse_dataset_payload(_DATASETS["s1"], setid="s1"))
    assert observations[0].temperature_k == 298.15
    assert observations[0].relative_permittivity == 6.8
    assert observations[0].uncertainty == 0.6
    assert observations[0].frequency_mhz == 1000.0


def test_extract_observations_returns_nothing_when_permittivity_is_absent():
    payload = _dataset_payload(
        "imidazolium one",
        "C6H7N",
        [[["298.15"], ["1.0"]]],
        dhead=[["Temperature, K", None], ["Viscosity", "Liquid"]],
    )
    assert extract_observations(parse_dataset_payload(payload, setid="x")) == []


def test_extract_observations_handles_a_cell_without_uncertainty():
    payload = _dataset_payload(
        "imidazolium one",
        "C6H7N",
        [[["296.0"], ["2.87"]]],
        dhead=[["Temperature, K", None], ["Relative permittivity", "Liquid"]],
    )
    observations = extract_observations(parse_dataset_payload(payload, setid="x"))
    assert observations[0].relative_permittivity == 2.87
    assert observations[0].uncertainty is None


def test_summarize_set_separates_temperature_and_frequency_behaviour():
    dataset = parse_dataset_payload(_DATASETS["s1"], setid="s1")
    summary = summarize_set(dataset, extract_observations(dataset))
    assert summary["n_rows"] == 2
    assert summary["has_temperature_column"] is True
    assert summary["has_frequency_column"] is True
    assert summary["n_distinct_temperatures"] == 1

    mixture = parse_dataset_payload(_DATASETS["s3"], setid="s3")
    mixture_summary = summarize_set(mixture, extract_observations(mixture))
    assert mixture_summary["n_distinct_temperatures"] == 3
    assert mixture_summary["temperature_k_min"] == 293.15
    assert mixture_summary["temperature_k_max"] == 313.15
    assert mixture_summary["has_frequency_column"] is False


def test_summarize_set_reports_nothing_rather_than_zero_for_missing_data():
    payload = _dataset_payload(
        "imidazolium one",
        "C6H7N",
        [[["298.15"], ["1.0"]]],
        dhead=[["Temperature, K", None], ["Viscosity", "Liquid"]],
    )
    dataset = parse_dataset_payload(payload, setid="x")
    summary = summarize_set(dataset, extract_observations(dataset))
    assert summary["relative_permittivity_min"] is None
    assert summary["n_observations"] == 0


# --------------------------------------------------------------------------- #
# Roster join
# --------------------------------------------------------------------------- #


def test_load_roster_indexes_names_formulas_and_inchikeys(roster_csv: Path):
    roster = load_roster(roster_csv, _fake_formula_of_smiles)
    assert roster.by_name[normalize_name("imidazolium one")] == "imidazolium one"
    assert roster.inchikey_by_name[normalize_name("imidazolium one")] == "KEYONE-UHFFFAOYSA-N"
    assert roster.by_formula[formula_signature("C6H7N")] == "imidazolium one"
    assert roster.out_of_scope_names == ("isomer partner",)


def test_load_roster_works_without_any_formula_resolver(roster_csv: Path):
    roster = load_roster(roster_csv, None)
    assert len(roster.by_name) == 3
    assert roster.by_formula == {}


def test_classify_compound_matches_by_normalised_name_and_carries_the_inchikey(roster_csv: Path):
    roster = load_roster(roster_csv, _fake_formula_of_smiles)
    outcome = classify_compound("Imidazolium ONE", "C6H7N", roster)
    assert outcome.verdict == "matched_name"
    assert outcome.inchikey == "KEYONE-UHFFFAOYSA-N"


def test_classify_compound_flags_an_isomer_collision_instead_of_claiming_a_match(
    roster_csv: Path,
):
    """Constitutional isomers share a formula but are different compounds.

    'imidazolium two' is absent from the roster by name yet shares C8H15F6N2P with
    'isomer partner'. Counting that as a match would silently delete a genuinely new
    compound from the yield, so it must stay 'not_in_roster' with a collision flag.
    """
    roster = load_roster(roster_csv, _fake_formula_of_smiles)
    outcome = classify_compound("imidazolium two", "C8H15F6N2P", roster)
    assert outcome.verdict == "not_in_roster"
    assert outcome.matched_roster_name is None
    assert outcome.formula_collision_with_roster == "isomer partner"
    assert outcome.structure_resolved is True


def test_classify_compound_without_a_formula_makes_no_structural_claim(roster_csv: Path):
    roster = load_roster(roster_csv, _fake_formula_of_smiles)
    outcome = classify_compound("imidazolium three", None, roster)
    assert outcome.verdict == "not_in_roster"
    assert outcome.structure_resolved is False
    assert outcome.formula_collision_with_roster is None


# --------------------------------------------------------------------------- #
# Sample selection
# --------------------------------------------------------------------------- #


def test_spread_covers_both_ends_of_an_ordered_list():
    names = [chr(ord("a") + index) for index in range(10)]
    picked = spread(names, 3)
    assert picked[0] == "a"
    assert picked[-1] == "j"


def test_spread_returns_everything_when_asked_for_more_than_exists():
    assert spread(["a", "b"], 8) == ["a", "b"]
    assert spread([], 4) == []
    assert spread(["a", "b"], 0) == []


def test_choose_sample_prefers_the_larger_family_and_reserves_a_solvent_slot():
    components = {
        "imidazolium one": 18,
        "imidazolium two": 12,
        "imidazolium three": 6,
        "methanol": 4,
        "acetone": 2,
    }
    chosen = choose_sample(components, 4)
    assert "methanol" in chosen or "acetone" in chosen
    assert len(chosen) <= 4


def test_choose_sample_respects_the_cap():
    components = {f"imidazolium {index}": index for index in range(1, 40)}
    assert len(choose_sample(components, 8)) <= 8

# --------------------------------------------------------------------------- #
# End-to-end probe against canned payloads
# --------------------------------------------------------------------------- #


def test_run_probe_verdict_a_is_evidence_backed(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    verdict = record["verdicts"]["a_exposes_relative_permittivity"]
    assert verdict["verdict"] is True
    assert verdict["keys"] == ["TGKW"]
    assert verdict["property_class"] == "Refraction, surface tension, and speed of sound"
    assert verdict["pairing_verified_by_live_query"] is True
    assert verdict["control_key_discriminates"] is True


def test_run_probe_control_query_returns_a_different_property(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    verification = record["property_census"]["verification"]
    assert verification["TGKW"]["returned_property_names"] == {"Relative permittivity": 4}
    assert verification["TGKW"]["all_rows_are_target"] is True
    control = verification["control:IzOV"]
    assert control["returned_property_names"] == {"Interfacial tension": 1}
    assert control["all_rows_are_target"] is False


def test_run_probe_verdict_b_separates_schema_from_real_variation(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    verdict = record["verdicts"]["b_carries_temperature"]
    assert verdict["temperature_column_present_in_all_sampled_sets"] is True
    assert verdict["n_sampled_sets"] == 2
    assert verdict["temperature_variation_observed_for_pure_compounds"] is False
    assert verdict["n_targeted_series_checks_with_multiple_temperatures"] == 1
    assert verdict["n_targeted_series_checks_pure_and_multitemperature"] == 0
    assert verdict["verdict"] is True


def test_run_probe_verdict_c_reports_json_api_but_no_bulk_export(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    verdict = record["verdicts"]["c_machine_readable_export"]
    assert verdict["json_api_found"] is True
    assert verdict["bulk_csv_or_txt_export_found"] is False


def test_run_probe_records_export_guess_statuses_from_the_wire(roster_csv: Path):
    routes = {
        _key("/ILT2/ilset.csv"): HttpResponse(url=BASE + "/ILT2/ilset.csv", status=404, body=b"", headers={}),
        _key("/ILT2/ilsearch.txt"): HttpResponse(
            url=BASE + "/ILT2/ilsearch.txt", status=404, body=b"", headers={}
        ),
    }
    record = _run(roster_csv, sample_sets=2, routes=routes)
    statuses = record["verdicts"]["c_machine_readable_export"]["export_guess_statuses"]
    assert statuses == {"csv_export_guess": 404, "txt_export_guess": 404}


def test_run_probe_verdict_d_counts_new_compounds_honestly(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    verdict = record["verdicts"]["d_compounds_carrying_it"]
    assert verdict["sets_total"] == 4
    assert verdict["distinct_pure_compounds"] == 3
    assert verdict["already_in_roster"] == 1
    assert verdict["new_to_roster"] == 2
    assert verdict["formula_collisions_needing_manual_review"] == 1


def test_run_probe_crosscheck_reports_the_collision_for_manual_review(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    crosscheck = record["roster_crosscheck"]
    collisions = crosscheck["formula_collisions_needing_manual_review"]
    assert len(collisions) == 1
    assert collisions[0]["compound"] == "imidazolium two"
    assert collisions[0]["same_formula_as_roster_compound"] == "isomer partner"
    assert crosscheck["n_with_formula_evidence"] == 2


def test_run_probe_only_fetches_the_datasets_it_needs(roster_csv: Path):
    log: list = []
    routes = _standard_routes(_DATASETS)
    record = run_probe(
        http_get=_transport(routes, log),
        sleep=_noop_sleep,
        roster_path=roster_csv,
        formula_of_smiles=_fake_formula_of_smiles,
        sample_sets=2,
    )
    requested_sets = [params["set"] for url, params in log if url == BASE + DATASET_PATH and "set" in params]
    assert requested_sets == ["s1", "s2", "s3", "s4"]
    assert record["request_budget"]["used"] == len(record["request_log"])
    assert record["request_budget"]["used"] <= record["request_budget"]["limit"]


def test_run_probe_respects_the_sample_cap(roster_csv: Path):
    record = _run(roster_csv, sample_sets=1)
    assert len(record["sample"]["sets"]) == 1


def test_run_probe_records_the_pure_population_histogram(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    census = record["dataset_census"]["by_key"]["pure_component"]
    assert census["datapoint_count_histogram"] == {1: 1, 5: 1, 18: 1}
    assert census["count"] == 3


def test_run_probe_totals_bytes_and_has_no_failures_on_a_healthy_route_table(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    assert record["failures"] == []
    assert record["total_bytes_transferred"] > 0


# --------------------------------------------------------------------------- #
# Honest failure: no numbers may be invented when the network is not there
# --------------------------------------------------------------------------- #


def test_run_probe_records_every_failure_when_the_transport_always_raises(roster_csv: Path):
    def http_get(url, params=None):
        raise OSError("network is unreachable")

    record = run_probe(
        http_get=http_get,
        sleep=_noop_sleep,
        roster_path=roster_csv,
        formula_of_smiles=_fake_formula_of_smiles,
        sample_sets=2,
    )
    assert record["failures"]
    assert all("network is unreachable" in failure["error"] for failure in record["failures"])
    assert record["verdicts"]["a_exposes_relative_permittivity"]["verdict"] is False
    assert record["verdicts"]["b_carries_temperature"]["verdict"] is False
    assert record["verdicts"]["d_compounds_carrying_it"]["new_to_roster"] == 0
    assert record["verdicts"]["d_compounds_carrying_it"]["sets_total"] is None
    assert record["discovery"] == []


def test_run_probe_stops_at_the_budget_and_says_so(roster_csv: Path):
    record = _run(roster_csv, sample_sets=2, budget_limit=3)
    assert record["request_budget"]["used"] == 3
    assert any("BudgetExhausted" in failure["error"] for failure in record["failures"])
    assert record["verdicts"]["a_exposes_relative_permittivity"]["verdict"] is False


def test_run_probe_reports_broken_json_instead_of_guessing(roster_csv: Path):
    routes = {
        _key(SEARCH_PATH, {"prp": "TGKW"}): HttpResponse(
            url=BASE + SEARCH_PATH, status=200, body=b"<html>not json</html>", headers={}
        )
    }
    record = _run(roster_csv, sample_sets=2, routes=routes)
    assert any(failure["error"].startswith("json:") for failure in record["failures"])
    # The broken call is the whole-population census, so its entry is absent and the
    # headline total is explicitly unknown -- while the still-working pure census is
    # kept, because discarding a response that did arrive would be its own dishonesty.
    assert record["dataset_census"]["by_key"].get("all") is None
    assert record["verdicts"]["d_compounds_carrying_it"]["sets_total"] is None
    assert record["verdicts"]["d_compounds_carrying_it"]["distinct_pure_compounds"] == 3


def test_run_probe_without_a_permittivity_property_says_so(roster_csv: Path):
    routes = {
        _key(PROPERTY_LIST_PATH): _json(
            {"plist": [{"cls": "Transport properties", "key": ["tplC"], "name": ["Viscosity"]}]}
        )
    }
    record = _run(roster_csv, sample_sets=2, routes=routes)
    assert record["property_census"]["permittivity_keys"] == []
    assert record["verdicts"]["a_exposes_relative_permittivity"]["verdict"] is False
    assert record["verdicts"]["d_compounds_carrying_it"]["sets_total"] is None


def test_write_summary_round_trips_utf8(tmp_path: Path, roster_csv: Path):
    record = _run(roster_csv, sample_sets=2)
    target = write_summary(tmp_path / "nested" / "summary.json", record)
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    as_written = json.loads(json.dumps(record["verdicts"]))
    assert reloaded["verdicts"] == as_written
    assert reloaded["verdicts"]["a_exposes_relative_permittivity"]["verdict"] is True
    assert reloaded["probe"] == "ilthermo"