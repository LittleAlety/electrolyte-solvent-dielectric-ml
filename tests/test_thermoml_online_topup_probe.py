"""Offline unit tests for the online ThermoML top-up probe.

Everything here runs with zero network access: every HTTP interaction goes through a
locally defined fake ``http_get``, and all file work happens under ``tmp_path`` so the
real 189 MB archive in ``data/raw/thermoml_archive`` is never opened. The tests pin the
honest-failure behaviour of the probe: a zero-filled preallocated download must be
reported as corrupt, never silently accepted as a usable archive.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from probes.thermoml_online_topup_probe import (
    API_BASE,
    API_OBJECT_PREFIX,
    API_PHRASE_QUERIES,
    API_QUERIES,
    ARCHIVE_DIR,
    ARCHIVE_PATH,
    DEFAULT_SUMMARY,
    DOWNLOAD_BUDGET_LIMIT,
    GZIP_MAGIC,
    HTTP_TIMEOUT_SECONDS,
    KNOWN_KEY_SOURCES,
    LEGACY_ARCHIVE_URLS,
    MIN_ARCHIVE_BYTES,
    PERMITTIVITY_WORDING,
    REPOSITORY_ROOT,
    SITE_BASE,
    TAR_MAGIC,
    TAR_MAGIC_OFFSET,
    TOTAL_RECORDS_QUERY,
    USER_AGENT,
    BudgetExhausted,
    HttpResponse,
    RequestBudget,
    ThermoMLSearchError,
    api_search,
    build_summary,
    classify_archive_payload,
    classify_online_property,
    coverage_delta,
    default_http_get,
    diagnose_local_archive,
    discover_endpoints,
    expected_size_from_manifest,
    extract_inchikeys,
    is_inchikey,
    is_salvageable,
    iter_records,
    load_known_inchikeys,
    log_entry,
    mentions_permittivity,
    property_names,
    pure_zero_frequency_liquid_epsilon_rows,
    record_dois,
    request,
    scan_file_zones,
    sha256_file,
    zone_scan,
)

WATER_KEY = "XLYOFNOQVPJJNP-UHFFFAOYSA-N"
EC_KEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
# Synthetic-but-well-formed keys: guaranteed absent from the local dielectric data.
FRESH_KEY = "ZZZZZZZZZZZZZZ-ZZZZZZZZZZ-Z"
KNOWN_KEY = "YYYYYYYYYYYYYY-YYYYYYYYYY-Y"

ZERO_FREQ_PROPERTY = "Relative permittivity at zero frequency"
VARIOUS_FREQ_PROPERTY = "Relative permittivity at various frequencies"


# --- helpers --------------------------------------------------------------


def _resp(status: int, body: bytes = b"", headers: Mapping[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status_code=status, headers=headers or {}, body=body)


def _json_response(payload: Any, status: int = 200) -> HttpResponse:
    return _resp(
        status,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )


def _fake_get(response: HttpResponse, calls: list[dict[str, Any]] | None = None):
    def fake(
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        timeout: int = HTTP_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        if calls is not None:
            calls.append({"url": url, "method": method, "params": dict(params or {})})
        return response

    return fake


def _api_payload(results: list[dict[str, Any]], size: int | None = None) -> dict[str, Any]:
    return {
        "pageNum": 0,
        "pageSize": -1,
        "size": len(results) if size is None else size,
        "results": results,
    }


def _api_record(doi: str, content: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": API_OBJECT_PREFIX + doi, "type": "TRCTml4", "content": dict(content)}


def _component(inchikey: str, name: str = "Water", formula: str = "H2O") -> dict[str, Any]:
    return {
        "sStandardInChIKey": inchikey,
        "sCommonName": name,
        "sFormula": formula,
    }


def _themol_property(name: str) -> dict[str, Any]:
    return {
        "Property-MethodID": {
            "PropertyGroup": {"Prop": {"ePropName": name, "eMethodName": "Test method"}}
        },
        "PropPhaseID": {"ePropPhase": "Liquid"},
        "nPropNumber": 1,
    }


def _frequency_constraint(value: str) -> dict[str, Any]:
    return {
        "ConstraintID": {
            "ConstraintType": {"eMiscellaneous": "Frequency, Hz"},
            "ConstraintPhaseID": {"eConstraintPhase": "Liquid"},
        },
        "nConstraintValue": value,
    }


def _block(
    components: list[dict[str, Any]],
    property_name: str,
    *,
    frequency_value: str | None = None,
    phase: str = "Liquid",
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "Component": components,
        "PhaseID": [{"ePhase": phase}],
        "Property": [_themol_property(property_name)],
        "Variable": [
            {
                "VariableID": {"VariableType": {"eTemperature": "Temperature, K"}},
                "nVarValue": "298.15",
            }
        ],
    }
    if frequency_value is not None:
        block["Constraint"] = [_frequency_constraint(frequency_value)]
    return block


def _content(
    blocks: list[dict[str, Any]],
    compounds: list[dict[str, Any]],
    doi: str,
    *,
    title: str = "A thermophysical study of model electrolytes",
) -> dict[str, Any]:
    return {
        "Citation": {"sTitle": title, "sDOI": doi},
        "Compound": compounds,
        "PureOrMixtureData": blocks,
        "id": doi,
    }


# --- 1. a non-archive payload must never be reported as usable ------------


def test_classify_rejects_a_zero_filled_preallocated_download() -> None:
    result = classify_archive_payload(b"\x00" * 64, 189_433_115)

    assert set(result) == {"gzip_magic", "tar_magic", "zero_prefixed", "verdict"}
    assert result["verdict"] == "zero_filled"
    assert result["gzip_magic"] is False
    assert result["tar_magic"] is False
    assert result["zero_prefixed"] is True
    assert is_salvageable(result["verdict"]) is False


def test_classify_rejects_plain_text_that_is_not_an_archive() -> None:
    payload = b"hello world, definitely not an archive" * 32

    result = classify_archive_payload(payload, 2048)

    assert result["verdict"] == "not_an_archive"
    assert result["gzip_magic"] is False
    assert result["zero_prefixed"] is False
    assert is_salvageable(result["verdict"]) is False


def test_classify_accepts_a_real_gzip_signature() -> None:
    first_bytes = b"\x1f\x8b\x08\x00" + b"\x00" * 60

    result = classify_archive_payload(first_bytes, len(first_bytes))

    assert first_bytes.startswith(GZIP_MAGIC)
    assert result["verdict"] == "ok_gzip"
    assert result["gzip_magic"] is True
    assert is_salvageable(result["verdict"]) is True


def test_classify_accepts_a_gzip_member_even_when_it_is_shorter_than_the_minimum() -> None:
    first_bytes = GZIP_MAGIC + b"\x00" * 8

    result = classify_archive_payload(first_bytes, len(first_bytes))

    assert len(first_bytes) < MIN_ARCHIVE_BYTES
    assert result["verdict"] == "ok_gzip"
    assert is_salvageable(result["verdict"]) is True


def test_classify_reports_empty_and_too_small() -> None:
    empty = classify_archive_payload(b"", 0)
    assert empty["verdict"] == "empty"
    assert is_salvageable(empty["verdict"]) is False

    tiny = classify_archive_payload(b"abcdefgh", 8)
    assert tiny["verdict"] == "too_small"
    assert tiny["gzip_magic"] is False
    assert is_salvageable(tiny["verdict"]) is False


def test_classify_recognises_a_tar_magic_at_offset_257() -> None:
    first_bytes = b"\x00" * TAR_MAGIC_OFFSET + TAR_MAGIC + b"\x00" * 64

    result = classify_archive_payload(first_bytes, 2048)

    assert first_bytes[TAR_MAGIC_OFFSET : TAR_MAGIC_OFFSET + len(TAR_MAGIC)] == TAR_MAGIC
    assert result["tar_magic"] is True
    assert result["verdict"] == "ok_tar"
    assert is_salvageable(result["verdict"]) is True


# --- 2. zone scanning -----------------------------------------------------


def test_zone_scan_reports_all_zero_and_empty_buffers() -> None:
    zeros = zone_scan(b"\x00" * 128)

    assert set(zeros) == {
        "size",
        "zero_bytes",
        "nonzero_bytes",
        "first_nonzero_offset",
        "last_nonzero_offset",
        "zero_filled",
        "zero_fraction",
    }
    assert zeros["size"] == 128
    assert zeros["nonzero_bytes"] == 0
    assert zeros["zero_bytes"] == 128
    assert zeros["first_nonzero_offset"] is None
    assert zeros["last_nonzero_offset"] is None
    assert zeros["zero_filled"] is True
    assert zeros["zero_fraction"] == pytest.approx(1.0)

    empty = zone_scan(b"")
    assert empty["size"] == 0
    assert empty["nonzero_bytes"] == 0
    assert empty["zero_filled"] is False


def test_zone_scan_locates_a_single_nonzero_byte() -> None:
    data = b"\x00" * 10 + b"\x01" + b"\x00" * 5

    result = zone_scan(data)

    assert result["size"] == 16
    assert result["nonzero_bytes"] == 1
    assert result["zero_bytes"] == 15
    assert result["first_nonzero_offset"] == 10
    assert result["last_nonzero_offset"] == 10
    assert result["zero_filled"] is False
    assert result["zero_fraction"] == pytest.approx(15 / 16)


def test_scan_file_zones_streams_a_sparse_file(tmp_path: Path) -> None:
    path = tmp_path / "sparse.tgz"
    path.write_bytes(b"\x00" * 4096 + b"\x07" + b"\x00" * 2048)

    zones = scan_file_zones(path, chunk_size=1024)

    assert zones["size"] == 4096 + 1 + 2048
    assert zones["nonzero_bytes"] == 1
    assert zones["first_nonzero_offset"] == 4096
    assert zones["last_nonzero_offset"] == 4096
    assert zones["zero_filled"] is False

    head_only = scan_file_zones(path, chunk_size=512, max_bytes=1000)
    assert head_only["nonzero_bytes"] == 0
    assert head_only["first_nonzero_offset"] is None


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    payload = b"thermoml-online-topup" * 97
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)

    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


# --- 3. local archive diagnosis -------------------------------------------


def test_diagnose_local_archive_missing_file_is_not_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.tgz"

    result = diagnose_local_archive(missing)

    assert set(result) == {
        "path",
        "exists",
        "size",
        "sha256",
        "head_hex",
        "tail_hex",
        "zones",
        "classification",
        "manifest_expected_size",
        "salvageable",
        "diagnosis",
    }
    assert result["exists"] is False
    assert result["size"] == 0
    assert result["salvageable"] is False
    assert result["manifest_expected_size"] is None
    assert isinstance(result["diagnosis"], str)
    assert result["diagnosis"]


def test_diagnose_local_archive_flags_a_zero_filled_payload(tmp_path: Path) -> None:
    path = tmp_path / "ThermoML.v2020-09-30.tgz"
    path.write_bytes(b"\x00" * 4096)

    result = diagnose_local_archive(path)

    assert result["exists"] is True
    assert result["size"] == 4096
    assert result["salvageable"] is False
    assert result["classification"]["verdict"] == "zero_filled"
    assert result["zones"]["zero_filled"] is True
    assert set(result["head_hex"]) == {"0"}
    assert set(result["tail_hex"]) == {"0"}


def test_expected_size_from_manifest_reads_a_sidecar(tmp_path: Path) -> None:
    archive = tmp_path / ARCHIVE_PATH.name
    archive.write_bytes(b"\x00" * 16)

    assert expected_size_from_manifest(archive) is None

    archive.with_name(archive.name + ".meta.json").write_text(
        json.dumps({"expected_size": 189_433_115}), encoding="utf-8"
    )
    assert expected_size_from_manifest(archive) == 189_433_115


def test_expected_size_from_manifest_falls_back_to_other_keys(tmp_path: Path) -> None:
    archive = tmp_path / "a.tgz"
    archive.write_bytes(b"x")
    (tmp_path / "download.json").write_text(
        json.dumps({"content_length": 4096}), encoding="utf-8"
    )

    assert expected_size_from_manifest(archive) == 4096


# --- 4. injectable HTTP layer ---------------------------------------------


def test_log_entry_has_exactly_the_documented_keys() -> None:
    entry = log_entry("https://example.org/x", "GET", _resp(200, b"abc"))

    assert set(entry) == {"url", "method", "status", "bytes", "ok"}
    assert entry["url"] == "https://example.org/x"
    assert entry["method"] == "GET"
    assert entry["status"] == 200
    assert entry["bytes"] == 3
    assert entry["ok"] is True
    assert log_entry("https://example.org/x", "GET", _resp(404))["ok"] is False
    assert log_entry("https://example.org/x", "GET", _resp(301))["ok"] is True
    assert log_entry("https://example.org/x", "GET", _resp(0))["ok"] is False


def test_request_budget_spend_raises_once_the_limit_is_exhausted() -> None:
    budget = RequestBudget(limit=2)

    assert budget.limit == 2
    assert budget.used == 0
    assert budget.bytes_transferred == 0
    assert budget.remaining() == 2

    budget.spend()
    budget.spend()
    assert budget.used == 2
    assert budget.remaining() == 0

    with pytest.raises(BudgetExhausted):
        budget.spend()

    budget.record(200, 1234)
    budget.record(404, 0)
    assert budget.bytes_transferred == 1234


def test_api_search_spends_exactly_one_budget_unit_and_logs_the_call() -> None:
    calls: list[dict[str, Any]] = []
    response = _json_response(_api_payload([_api_record("10.1021/je3001427", {})]))
    budget = RequestBudget(limit=8)

    payload, entry = api_search(
        _fake_get(response, calls), "permittivity", budget=budget, page_size=1
    )

    assert payload["size"] == 1
    assert budget.used == 1
    assert entry["url"] == API_BASE
    assert entry["method"] == "GET"
    assert entry["status"] == 200
    assert entry["bytes"] == len(response.body)
    assert entry["ok"] is True
    assert calls[0]["url"] == API_BASE
    assert calls[0]["method"] == "GET"
    assert calls[0]["params"]["query"] == "permittivity"
    assert calls[0]["params"]["pageSize"] == 1


def test_api_search_omits_paging_when_no_page_size_is_given() -> None:
    calls: list[dict[str, Any]] = []
    budget = RequestBudget(limit=8)

    api_search(_fake_get(_json_response(_api_payload([])), calls), "*", budget=budget)

    assert "pageSize" not in calls[0]["params"]
    assert budget.used == 1


def test_api_search_raises_on_error_status_and_on_non_json() -> None:
    budget = RequestBudget(limit=8)

    with pytest.raises(ThermoMLSearchError):
        api_search(_fake_get(_resp(503, b"")), "permittivity", budget=budget)

    with pytest.raises(ThermoMLSearchError):
        api_search(_fake_get(_resp(200, b"<html>not json</html>")), "permittivity", budget=budget)

    assert budget.used == 2


def test_request_accumulates_bytes_transferred() -> None:
    body = b'{"size": 0, "results": []}'
    budget = RequestBudget(limit=8)
    fake = _fake_get(_resp(200, body))

    _, first = request(fake, API_BASE, budget=budget, params={"query": "a"})
    _, second = request(fake, SITE_BASE, budget=budget, method="HEAD")

    assert budget.used == 2
    assert budget.bytes_transferred == 2 * len(body)
    assert first["bytes"] == len(body)
    assert second["method"] == "HEAD"
    assert second["url"] == SITE_BASE


def test_default_http_get_swallows_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = pytest.importorskip("requests")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise requests.ConnectionError("offline test")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests, "request", boom)
    monkeypatch.setattr(requests, "head", boom)
    monkeypatch.setattr(requests.Session, "request", boom)

    response = default_http_get("https://example.invalid/objects", {"query": "x"})

    assert response.status_code == 0
    assert response.body == b""
    assert response.text == ""
    assert dict(response.headers) == {}


def test_discover_endpoints_logs_the_dead_archive_and_the_live_api() -> None:
    seen: list[tuple[str, str]] = []

    def fake(
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        timeout: int = HTTP_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        seen.append((method, url))
        status = 404 if url in LEGACY_ARCHIVE_URLS else 200
        return _resp(status, b"" if method == "HEAD" else b"{}")

    budget = RequestBudget(limit=64)
    entries = discover_endpoints(fake, budget)

    statuses = {entry["url"]: entry["status"] for entry in entries}
    for url in LEGACY_ARCHIVE_URLS:
        assert statuses[url] == 404
    assert statuses[SITE_BASE] == 200
    assert statuses[API_BASE] == 200
    assert budget.used == len(entries)
    # Every endpoint entry must carry the full log_entry contract (Agent A may add
    # extra metadata such as "kind", which the summary schema also needs).
    assert all(
        {"url", "method", "status", "bytes", "ok"} <= set(entry) for entry in entries
    )
    assert all(isinstance(entry["bytes"], int) for entry in entries)
    assert all(entry["method"] == "HEAD" for entry in entries)
    assert LEGACY_ARCHIVE_URLS


def test_discover_endpoints_survives_server_errors() -> None:
    def fake(
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        timeout: int = HTTP_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        return _resp(500, b"")

    entries = discover_endpoints(fake, RequestBudget(limit=64))

    assert entries
    assert all(entry["ok"] is False for entry in entries)


# --- 5. payload parsing ---------------------------------------------------


def test_iter_records_strips_the_object_prefix_and_skips_malformed_entries() -> None:
    content = _content([], [_component(WATER_KEY)], "10.1021/je3001427")
    payload = {
        "pageNum": 0,
        "pageSize": -1,
        "size": 4,
        "results": [
            _api_record("10.1021/je3001427", content),
            "not-a-dict",
            {"type": "TRCTml4"},
            {"id": None, "content": {}},
        ],
    }

    records = list(iter_records(payload))

    assert len(records) == 1
    assert records[0]["object_id"] == API_OBJECT_PREFIX + "10.1021/je3001427"
    assert records[0]["doi"] == "10.1021/je3001427"
    assert records[0]["content"]["id"] == "10.1021/je3001427"
    assert record_dois(payload) == ["10.1021/je3001427"]


def test_iter_records_tolerates_a_payload_without_results() -> None:
    assert list(iter_records({})) == []
    assert record_dois({}) == []


def test_extract_inchikeys_handles_a_single_compound_and_a_list() -> None:
    single = {"Compound": {"sStandardInChIKey": "xlyofnoqvpjjnp-uhfffaoysa-n"}}
    listed = {
        "Compound": [
            {"sInChIKey": "kmtrudsvknlomy-uhfffaoysa-n"},
            {"sStandardInChIKey": ""},
            {"sStandardInChIKey": None},
            {},
        ]
    }

    assert extract_inchikeys(single) == {WATER_KEY}
    assert extract_inchikeys(listed) == {EC_KEY}
    assert extract_inchikeys({}) == set()


def test_is_inchikey_accepts_real_keys_and_rejects_junk() -> None:
    assert is_inchikey(WATER_KEY) is True
    assert is_inchikey(EC_KEY) is True
    assert is_inchikey(FRESH_KEY) is True
    assert is_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA") is False
    assert is_inchikey("xlyofnoqvpjjnp-uhfffaoysa-n") is False
    assert is_inchikey("") is False
    assert is_inchikey("not a key") is False
    assert is_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-NN") is False


def test_coverage_delta_reports_new_keys_as_a_sorted_list() -> None:
    delta = coverage_delta([WATER_KEY, EC_KEY, FRESH_KEY], [EC_KEY, KNOWN_KEY, WATER_KEY])

    assert set(delta) == {"online_total", "known_total", "overlap", "new_keys", "new_count"}
    assert delta["online_total"] == 3
    assert delta["known_total"] == 3
    assert delta["overlap"] == 2
    assert delta["new_keys"] == [FRESH_KEY]
    assert delta["new_count"] == 1

    empty = coverage_delta([], [])
    assert empty["new_keys"] == []
    assert empty["new_count"] == 0
    assert empty["overlap"] == 0


def test_property_names_and_permittivity_wording() -> None:
    permittivity = _content(
        [_block([_component(WATER_KEY)], VARIOUS_FREQ_PROPERTY)], [_component(WATER_KEY)], "d1"
    )
    conductivity = _content(
        [_block([_component(WATER_KEY)], "Electrical conductivity, S/m")],
        [_component(WATER_KEY)],
        "d2",
    )

    assert property_names(permittivity) == [VARIOUS_FREQ_PROPERTY]
    assert property_names(conductivity) == ["Electrical conductivity, S/m"]
    assert property_names({}) == []
    assert mentions_permittivity(permittivity) is True
    assert mentions_permittivity(conductivity) is False
    assert isinstance(PERMITTIVITY_WORDING, re.Pattern)
    assert PERMITTIVITY_WORDING.search("Relative Permittivity at zero frequency")


def test_classify_online_property_delegates_to_the_shared_rule() -> None:
    assert classify_online_property(ZERO_FREQ_PROPERTY) == "static_or_zero_frequency"
    assert classify_online_property(VARIOUS_FREQ_PROPERTY) == "frequency_dependent"
    assert classify_online_property("Relative permittivity, imaginary part") == "loss"
    assert classify_online_property("Relative permittivity", "0") == "static_or_zero_frequency"


# --- 6. the tight zero-frequency gate -------------------------------------


def test_pure_zero_frequency_epsilon_row_is_emitted_for_a_pure_liquid() -> None:
    content = _content(
        [_block([_component(WATER_KEY, "Water")], ZERO_FREQ_PROPERTY)],
        [_component(WATER_KEY, "Water")],
        "10.1021/je3001427",
    )

    rows = pure_zero_frequency_liquid_epsilon_rows(content, "10.1021/je3001427")

    assert len(rows) == 1
    row = rows[0]
    assert row["inchikey"] == WATER_KEY
    assert row["doi"] == "10.1021/je3001427"
    assert row["property_name"] == ZERO_FREQ_PROPERTY
    assert row["phase"].lower() == "liquid"
    assert isinstance(row["compound_name"], str)
    assert isinstance(row["frequency_value"], str)


def test_pure_zero_frequency_gate_rejects_a_mixture() -> None:
    components = [_component(WATER_KEY, "Water"), _component(EC_KEY, "Ethylene carbonate")]
    content = _content(
        [_block(components, ZERO_FREQ_PROPERTY)],
        components,
        "10.1021/je400001a",
    )

    assert pure_zero_frequency_liquid_epsilon_rows(content, "10.1021/je400001a") == []


def test_pure_zero_frequency_gate_rejects_a_frequency_dependent_property() -> None:
    content = _content(
        [_block([_component(WATER_KEY)], VARIOUS_FREQ_PROPERTY, frequency_value="1")],
        [_component(WATER_KEY)],
        "10.1021/je500001b",
    )

    assert pure_zero_frequency_liquid_epsilon_rows(content, "10.1021/je500001b") == []


def test_pure_zero_frequency_gate_rejects_a_non_liquid_phase() -> None:
    content = _content(
        [_block([_component(WATER_KEY)], ZERO_FREQ_PROPERTY, phase="Gas")],
        [_component(WATER_KEY)],
        "10.1021/je600001c",
    )

    assert pure_zero_frequency_liquid_epsilon_rows(content, "10.1021/je600001c") == []


def test_pure_zero_frequency_gate_never_raises_on_junk() -> None:
    assert pure_zero_frequency_liquid_epsilon_rows({}, "d") == []
    assert pure_zero_frequency_liquid_epsilon_rows({"PureOrMixtureData": "junk"}, "d") == []
    assert pure_zero_frequency_liquid_epsilon_rows({"PureOrMixtureData": [{}]}, "d") == []


# --- 7. local known-key loading -------------------------------------------


def test_load_known_inchikeys_reads_the_column_and_skips_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "dielectric_v03.csv"
    path.write_text(
        "inchikey,smiles,name\n"
        f'"{WATER_KEY}","O","water"\n'
        f'"{EC_KEY.lower()}","C1COC(=O)O1","ethylene carbonate"\n',
        encoding="utf-8",
    )

    keys = load_known_inchikeys([path])

    assert len(keys) == 2
    assert {key.upper() for key in keys} == {WATER_KEY, EC_KEY}
    assert load_known_inchikeys([tmp_path / "missing.csv"]) == set()


def test_known_key_sources_point_at_the_local_dielectric_exports() -> None:
    assert KNOWN_KEY_SOURCES
    names = {source.name for source in KNOWN_KEY_SOURCES}
    assert "dielectric_v03.csv" in names
    assert "dielectric_raw.csv" in names
    for source in KNOWN_KEY_SOURCES:
        assert isinstance(source, Path)


# --- constants ------------------------------------------------------------


def test_constants_match_the_frozen_spec() -> None:
    assert REPOSITORY_ROOT == Path(__file__).resolve().parents[1]
    assert ARCHIVE_DIR == REPOSITORY_ROOT / "data" / "raw" / "thermoml_archive"
    assert ARCHIVE_PATH == ARCHIVE_DIR / "ThermoML.v2020-09-30.tgz"
    assert DEFAULT_SUMMARY == REPOSITORY_ROOT / "probes" / "thermoml_online_topup_summary.json"
    assert API_BASE == "https://trc.nist.gov/ThermoML-API/objects"
    assert SITE_BASE == "https://trc.nist.gov/ThermoML/"
    assert API_OBJECT_PREFIX == "20.5000.trc.thermoml/"
    assert TOTAL_RECORDS_QUERY == "*"
    assert GZIP_MAGIC == b"\x1f\x8b"
    assert TAR_MAGIC_OFFSET == 257
    assert TAR_MAGIC == b"ustar"
    assert MIN_ARCHIVE_BYTES == 512
    assert isinstance(USER_AGENT, str) and USER_AGENT
    assert HTTP_TIMEOUT_SECONDS > 0
    assert DOWNLOAD_BUDGET_LIMIT > 0
    assert set(API_QUERIES) == {"permittivity", "dielectric"}
    assert any("zero frequency" in query for query in API_PHRASE_QUERIES)
    assert any("various frequencies" in query for query in API_PHRASE_QUERIES)
    assert len({url for url in LEGACY_ARCHIVE_URLS if url.startswith("https://trc.nist.gov")}) == len(
        LEGACY_ARCHIVE_URLS
    )


# --- importing the module must not touch the network ----------------------


_NO_NETWORK_IMPORT_SNIPPET = """
import socket
import ssl

def _blocked(*args, **kwargs):
    raise RuntimeError("network access attempted while importing the probe module")

ssl.SSLContext  # touch ssl so its hierarchy is fully built before patching
socket.socket.connect = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

import probes.thermoml_online_topup_probe as probe

assert callable(probe.main)
print("IMPORT_OK")
"""


def test_importing_the_module_performs_no_network_io() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPOSITORY_ROOT), str(REPOSITORY_ROOT / "src")]
    )

    result = subprocess.run(
        [sys.executable, "-c", _NO_NETWORK_IMPORT_SNIPPET],
        cwd=str(REPOSITORY_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


# --- 8. end-to-end build_summary over a canned transport ------------------


def _phrase_payload(query: str) -> dict[str, Any]:
    fresh = _api_record(
        "10.1021/je3001427",
        _content(
            [_block([_component(FRESH_KEY, "Model solvent A")], ZERO_FREQ_PROPERTY)],
            [_component(FRESH_KEY, "Model solvent A")],
            "10.1021/je3001427",
        ),
    )
    already_known = _api_record(
        "10.1021/je3001428",
        _content(
            [_block([_component(KNOWN_KEY, "Model solvent B")], ZERO_FREQ_PROPERTY)],
            [_component(KNOWN_KEY, "Model solvent B")],
            "10.1021/je3001428",
        ),
    )
    mixture = _api_record(
        "10.1021/je3001429",
        _content(
            [
                _block(
                    [_component(FRESH_KEY, "A"), _component(EC_KEY, "B")],
                    ZERO_FREQ_PROPERTY,
                )
            ],
            [_component(FRESH_KEY, "A"), _component(EC_KEY, "B")],
            "10.1021/je3001429",
        ),
    )
    frequency_dependent = _api_record(
        "10.1021/je3001430",
        _content(
            [_block([_component(EC_KEY, "EC")], VARIOUS_FREQ_PROPERTY, frequency_value="1")],
            [_component(EC_KEY, "EC")],
            "10.1021/je3001430",
        ),
    )
    if "zero frequency" in query:
        return _api_payload([fresh, already_known, mixture])
    if "various frequencies" in query:
        return _api_payload([frequency_dependent])
    return _api_payload([])


def test_build_summary_uses_the_phrase_queries_for_the_headline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake(
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        timeout: int = HTTP_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        params = dict(params or {})
        calls.append({"url": url, "method": method, "params": params})
        if method == "HEAD":
            return _resp(404 if url in LEGACY_ARCHIVE_URLS else 200, b"")
        query = params.get("query", "")
        if query == TOTAL_RECORDS_QUERY:
            return _json_response(_api_payload([], size=11923))
        if query in API_QUERIES:
            return _json_response(_api_payload([], size={"permittivity": 117, "dielectric": 93}[query]))
        return _json_response(_phrase_payload(query))

    known_csv = tmp_path / "known.csv"
    known_csv.write_text(f"inchikey\n{KNOWN_KEY}\n", encoding="utf-8")

    monkeypatch.setattr(
        "probes.thermoml_online_topup_probe.DEFAULT_SUMMARY", tmp_path / "summary.json"
    )

    summary = build_summary(
        archive_path=tmp_path / "missing" / ARCHIVE_PATH.name,
        http_get=fake,
        known_key_sources=[known_csv],
    )

    assert summary["schema_version"] == 1
    assert summary["probe"] == "thermoml_online_topup_probe"
    assert summary["local_archive"]["exists"] is False
    assert summary["local_archive"]["salvageable"] is False

    online = summary["online"]
    assert online["api_base"] == API_BASE
    assert online["total_records_online"] == 11923
    assert isinstance(online["endpoints"], list)
    assert online["request_budget"]["limit"] == DOWNLOAD_BUDGET_LIMIT
    assert online["request_budget"]["used"] > 0
    assert isinstance(online["bytes_transferred"], int)

    kinds = {entry["kind"] for entry in online["queries"]}
    assert {"total", "bare", "phrase"} <= kinds
    sizes = {entry["query"]: entry["size"] for entry in online["queries"]}
    assert sizes.get("permittivity") == 117
    assert sizes.get("dielectric") == 93

    coverage = summary["coverage"]
    assert coverage["known_keys"] >= 1
    assert FRESH_KEY in coverage["new_keys_list"]
    assert KNOWN_KEY not in coverage["new_keys_list"]
    assert coverage["new_keys_with_zero_frequency_epsilon"] == 1
    assert coverage["new_keys_list"] == sorted(coverage["new_keys_list"])
    assert coverage["tight_online_keys"] >= 2
    assert coverage["loose_online_keys"] >= 2

    tight_keys = {row["inchikey"] for row in coverage["tight_rows"]}
    assert tight_keys == {FRESH_KEY, KNOWN_KEY}

    assert summary["headline"]["new_inchikeys"] == coverage["new_keys_with_zero_frequency_epsilon"]
    assert isinstance(summary["headline"]["statement"], str)
    assert summary["headline"]["statement"]
    assert isinstance(summary["failures"], list)

    # The bare single-word queries must never be the headline source: they returned
    # empty result sets here, so no key can have come from them.
    assert not (tmp_path / "summary.json").exists()

# --- regression: a multi-compound record must not collapse onto Compound[0] ---


def test_component_keys_resolve_through_the_compound_table_not_the_inline_copy() -> None:
    """The NIST JSON collapses every component's inline key onto the first compound.

    A real record (10.1021/je101184s) holds 27 distinct compounds, yet every data-set
    Component repeats the FIRST compound's sStandardInChIKey. Trusting that copy turns a
    27-molecule study into a single molecule and silently under-counts coverage, so the
    resolver has to follow the RegNum counter and the /Compound/<n> path instead.
    """

    first = "AAAAAAAAAAAAAA-AAAAAAAAAA-A"
    second = "BBBBBBBBBBBBBB-BBBBBBBBBB-B"

    def compound(inchikey: str, org: int) -> dict[str, Any]:
        return {
            "RegNum": {"nOrgNum": org},
            "sStandardInChIKey": inchikey,
            "sCommonName": f"compound-{org}",
        }

    def collapsed_component(org: int) -> dict[str, Any]:
        # both blocks carry the SAME inline key, exactly as the real payload does
        return {
            "RegNum": {"nOrgNum": org},
            "path": f"/Compound/{org - 1}",
            "sStandardInChIKey": first,
        }

    content = _content(
        [
            _block([collapsed_component(1)], ZERO_FREQ_PROPERTY),
            _block([collapsed_component(2)], ZERO_FREQ_PROPERTY),
        ],
        [compound(first, 1), compound(second, 2)],
        "10.1000/collapsed",
    )

    rows = pure_zero_frequency_liquid_epsilon_rows(content, "10.1000/collapsed")

    assert [row["inchikey"] for row in rows] == [first, second]
    assert {row["inchikey"] for row in rows} != {first}


def test_component_key_resolves_by_path_when_the_regnum_counter_is_absent() -> None:
    key_a = "DDDDDDDDDDDDDD-DDDDDDDDDD-D"
    key_b = "EEEEEEEEEEEEEE-EEEEEEEEEE-E"

    content = _content(
        [_block([{"path": "/Compound/1", "sStandardInChIKey": key_a}], ZERO_FREQ_PROPERTY)],
        [
            {"RegNum": {"nOrgNum": 1}, "sStandardInChIKey": key_a},
            {"RegNum": {"nOrgNum": 2}, "sStandardInChIKey": key_b},
        ],
        "10.1000/path-only",
    )

    rows = pure_zero_frequency_liquid_epsilon_rows(content, "10.1000/path-only")

    assert [row["inchikey"] for row in rows] == [key_b]


def test_component_key_falls_back_to_the_inline_copy_without_a_registry() -> None:
    """A single-compound record has a trustworthy inline key; that path must keep working."""

    key = "CCCCCCCCCCCCCC-CCCCCCCCCC-C"
    block = _block([_component(key)], ZERO_FREQ_PROPERTY)
    content = _content([block], [], "10.1000/single-compound")

    rows = pure_zero_frequency_liquid_epsilon_rows(content, "10.1000/single-compound")

    assert [row["inchikey"] for row in rows] == [key]
