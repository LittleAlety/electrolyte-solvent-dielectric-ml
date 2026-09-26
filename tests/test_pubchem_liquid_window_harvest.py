"""Offline unit tests for the L1 PubChem liquid-window harvest.

Nothing here touches the network. The HTTP layer is made deterministic by
pre-seeding a throw-away cache directory and, where a missing cache must be
exercised, by running the client in ``offline`` mode so a stray request raises
instead of silently succeeding.

The parsing tests pin the cases the pilot actually surfaced: a Fahrenheit value
with a Celsius counterpart, a Kelvin value with no degree sign, a range that must
not become a negative temperature, a narrative line inside the boiling-point
section, and the vapour / relative / coefficient entries that share the Density
heading with real liquid densities.

The last tests read the committed summary and, when the (git-ignored) cache is
present, re-derive the coverage counts from the value table so a hand-edited row
cannot survive without the summary disagreeing with it.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.pubchem_liquid_window_harvest import (
    CACHE_SUFFIX,
    DENSITY_SELECTION_RULE,
    EXPERIMENTAL_HEADING,
    HARVEST_STATUSES,
    LIQUID_WINDOW_PROPERTIES,
    PUG_VIEW,
    REQUIRED_RUN_RECORD_KEYS,
    SELECTED_COLUMNS,
    TEMPERATURE_PROPERTIES,
    TEMPERATURE_SELECTION_RULE,
    VALUE_COLUMNS,
    ClientStats,
    OfflineError,
    PubChemClient,
    Target,
    _heading_url,
    append_run_log,
    build_run_record,
    build_value_rows,
    extract_condition,
    find_property_sections,
    flatten_temperature_value,
    harvest_compound,
    harvest_targets,
    is_narrative_temperature,
    load_targets,
    normalize_density,
    normalize_pressure,
    normalize_temperature,
    recorded_harvest_cost,
    select_values,
    summarize,
    value_text,
)

COMMITTED_SUMMARY = REPOSITORY_ROOT / "probes" / "pubchem_liquid_window_harvest_summary.json"
CACHE_DIR = (
    REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "liquid_window"
)
COMMITTED_VALUES = CACHE_DIR / "liquid_window_values.csv"
COMMITTED_SELECTED = CACHE_DIR / "liquid_window_selected.csv"
COMMITTED_LOG = CACHE_DIR / "_harvest_runs.jsonl"

ACETONITRILE = "WEVYAHXRMPXWCK-UHFFFAOYSA-N"
ACETONITRILE_CID = "6342"

REQUIRED_SUMMARY_KEYS = (
    "generated_at_utc",
    "coverage_set",
    "cache_hits",
    "network_calls",
    "retries",
    "throttle_seconds",
    "throttled_requests",
    "cache_entries_for_coverage_set",
    "throttle_seconds_per_request",
    "run_idempotent",
    "harvest_status_counts",
    "property_coverage",
    "value_rows",
    "selected_rows",
    "peer_reviewed_rows",
    "unparsed_value_rows",
    "density_subtype_counts",
    "depositor_counts_by_property",
    "numeric_ranges_by_property",
    "missing_temperature_keys",
    "unresolved",
    "source_kind",
    "quality_layer",
    "quality_layer_note",
    "recorded_harvest_cost_from_log",
)


def _string_info(
    reference_number: int,
    text: str,
    *,
    description: str | None = None,
    citation: str | None = None,
) -> dict:
    info: dict = {
        "ReferenceNumber": reference_number,
        "Value": {"StringWithMarkup": [{"String": text}]},
    }
    if description is not None:
        info["Description"] = description
    if citation is not None:
        info["Reference"] = [citation]
    return info


def _payload(entries: dict[str, list[dict]], *, cid: int = 6342, title: str = "Acetonitrile") -> dict:
    return {
        "Record": {
            "RecordType": "CID",
            "RecordNumber": cid,
            "RecordTitle": title,
            "Section": [
                {
                    "TOCHeading": "Chemical and Physical Properties",
                    "Section": [
                        {
                            "TOCHeading": "Experimental Properties",
                            "Section": [
                                {"TOCHeading": heading, "Information": infos}
                                for heading, infos in entries.items()
                            ],
                        }
                    ],
                }
            ],
            "Reference": [
                {"ReferenceNumber": 11, "SourceName": "CAMEO Chemicals"},
                {
                    "ReferenceNumber": 45,
                    "SourceName": "Hazardous Substances Data Bank (HSDB)",
                },
            ],
        }
    }


def _seed_cache(
    cache_dir: Path, inchikey: str, payload: object, *, cid: str = ACETONITRILE_CID
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{urllib.parse.quote(inchikey, safe="")}{CACHE_SUFFIX}"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.with_suffix(path.suffix + ".url").write_text(_heading_url(cid) + "\n", encoding="utf-8")


def _client(cache_dir: Path, *, offline: bool = True) -> PubChemClient:
    return PubChemClient(
        cache_dir=cache_dir,
        offline=offline,
        throttle_seconds=0.0,
        sleep_fn=lambda _seconds: None,
    )


def _target(inchikey: str = ACETONITRILE, cid: str = ACETONITRILE_CID) -> Target:
    return Target(inchikey=inchikey, name="probe", cid=cid, identity_check="roundtrip_match")


def _value_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in VALUE_COLUMNS}
    row.update(
        {
            "inchikey": ACETONITRILE,
            "name": "probe",
            "pubchem_cid": ACETONITRILE_CID,
            "property": "melting_point",
            "value_raw": "-44 degC",
            "value_numeric": "-44",
            "unit": "degC",
            "peer_reviewed": "false",
            "depositor": "probe depositor",
            "reference_number": "45",
            "source_kind": "compilation",
            "quality_layer": "filter_only",
        }
    )
    row.update(overrides)
    return row

# --------------------------------------------------------------------------
# Coverage set and cache behaviour.
# --------------------------------------------------------------------------


def test_targets_come_from_the_identity_map_with_a_cid_each() -> None:
    targets = load_targets()
    keys = [target.inchikey for target in targets]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)) == 314
    for target in targets:
        assert target.cid.isdigit()
        assert target.identity_check == "roundtrip_match"


def test_cache_hit_is_served_without_any_network_call(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _payload(
            {
                "Melting Point": [
                    _string_info(45, "-44 \u00b0C", description="PEER REVIEWED", citation="CRC")
                ],
                "Boiling Point": [_string_info(11, "81.6 \u00b0C at 760 mm Hg")],
            }
        ),
    )
    client = _client(cache_dir, offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert status == "harvested"
    assert client.stats.cache_hits == 1
    assert client.stats.network_calls == 0
    properties = {row["property"] for row in rows}
    assert properties == {"melting_point", "boiling_point"}


def test_missing_cache_while_offline_is_unresolved_not_absent(tmp_path: Path) -> None:
    client = _client(tmp_path / "empty", offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert status == "unresolved_offline"
    assert rows == []


def test_offline_client_raises_rather_than_silently_returning_nothing(tmp_path: Path) -> None:
    client = _client(tmp_path / "empty", offline=True)
    with pytest.raises(OfflineError):
        client.fetch(ACETONITRILE, ACETONITRILE_CID)


def test_a_cache_file_whose_url_marker_disagrees_is_not_trusted(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(cache_dir, ACETONITRILE, _payload({"Density": [_string_info(11, "0.787")]}))
    (cache_dir / f"{ACETONITRILE}{CACHE_SUFFIX}.url").write_text(
        _heading_url("9999") + "\n", encoding="utf-8"
    )
    client = _client(cache_dir, offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert client.stats.cache_hits == 0
    assert status == "unresolved_offline"
    assert rows == []


def test_a_scoped_404_is_recorded_as_no_experimental_properties_section(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        {"not_found": True, "http_status": 404, "fault_code": "PUGVIEW.NotFound"},
    )
    client = _client(cache_dir, offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert status == "no_experimental_properties_section"
    assert rows == []
    assert client.stats.network_calls == 0


def test_a_record_without_the_target_sections_is_reported_as_such(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _payload({"Odor": [_string_info(11, "pungent")]}),
    )
    client = _client(cache_dir, offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert status == "harvested_without_target_properties"
    assert rows == []


def test_find_property_sections_keeps_only_the_liquid_window_headings(tmp_path: Path) -> None:
    payload = _payload(
        {
            "Odor": [_string_info(11, "pungent")],
            "Vapor Density": [_string_info(11, "2.1 (Air = 1)")],
            "Flash Point": [_string_info(11, "12.8 \u00b0C")],
        }
    )
    found = find_property_sections(payload["Record"])
    assert [name for name, _, _ in found] == ["flash_point"]


# --------------------------------------------------------------------------
# Value parsing.
# --------------------------------------------------------------------------


def test_temperature_prefers_celsius_over_fahrenheit() -> None:
    normalized = normalize_temperature("42 \u00b0F (6 \u00b0C) (Open Cup)")
    assert normalized["celsius"] == 6.0
    assert normalized["reported_unit"] == "C"
    assert normalized["converted"] is False


def test_fahrenheit_is_converted_when_it_is_the_only_scale() -> None:
    normalized = normalize_temperature("-49 \u00b0F (NTP, 1992)")
    assert normalized["celsius"] == pytest.approx(-45.0)
    assert normalized["converted"] is True


def test_kelvin_without_a_degree_sign_is_understood() -> None:
    assert normalize_temperature("300 K")["celsius"] == pytest.approx(26.85)


def test_a_range_is_not_read_as_a_negative_temperature() -> None:
    # "0-94 degC" is a range (the en dash folds to "-"), not minus 94.
    assert normalize_temperature("0-94 \u00b0C")["celsius"] == pytest.approx(94.0)


def test_a_value_without_a_number_is_not_invented() -> None:
    assert normalize_temperature("not reported")["celsius"] is None


def test_pressure_conditions_are_normalised_to_mmhg() -> None:
    assert normalize_pressure("760 mm Hg")["mmhg"] == pytest.approx(760.0)
    assert normalize_pressure("at 1 atm")["mmhg"] == pytest.approx(760.0)
    assert normalize_pressure("at 101.3 kPa")["mmhg"] == pytest.approx(759.8, abs=0.1)
    assert normalize_pressure("no pressure here")["mmhg"] is None


def test_condition_temperature_and_raw_clause_are_kept() -> None:
    condition = extract_condition("0.9950 g/cu cm at 25 \u00b0C")
    assert condition["condition_raw"] == "25 \u00b0C"
    assert condition["temperature_c"] == pytest.approx(25.0)
    boiling = extract_condition("81.6 \u00b0C at 760 mm Hg")
    assert boiling["pressure_mmhg"] == pytest.approx(760.0)


def test_narrative_temperature_is_not_recorded_as_a_property() -> None:
    text = "Burns with luminous flame; dielectric constant: 38.8 at 20 \u00b0C"
    normalized = normalize_temperature(text)
    assert normalized["celsius"] is not None
    assert is_narrative_temperature(text, normalized["span"]) is True
    flat = flatten_temperature_value(text)
    assert flat["value_numeric"] is None
    assert flat["notes"] == "narrative_entry_not_parsed"


def test_decomposition_clause_is_not_recorded_as_a_property() -> None:
    flat = flatten_temperature_value("Decomposes at 200 \u00b0C")
    assert flat["value_numeric"] is None
    assert "narrative_entry_not_parsed" in flat["notes"]


def test_a_plain_temperature_is_recorded_with_its_condition() -> None:
    flat = flatten_temperature_value("81.6 \u00b0C at 760 mm Hg")
    assert flat["value_numeric"] == pytest.approx(81.6)
    assert flat["unit"] == "degC"
    assert flat["temperature_c"] == pytest.approx(81.6)
    assert flat["pressure_mmhg"] == pytest.approx(760.0)


def test_density_distinguishes_absolute_relative_unspecified_and_vapour() -> None:
    absolute = normalize_density("0.9950 g/cu cm at 25 \u00b0C")
    assert (absolute["subtype"], absolute["unit"]) == ("absolute", "g/cm3")
    assert absolute["value_numeric"] == pytest.approx(0.995)
    assert absolute["temperature_c"] == pytest.approx(25.0)

    superscript = normalize_density("0.82 g/cm\u00b3")
    assert (superscript["subtype"], superscript["value_numeric"]) == ("absolute", 0.82)

    relative = normalize_density("Relative density (water = 1): 0.8")
    assert (relative["subtype"], relative["unit"]) == ("relative", "relative")
    assert relative["value_numeric"] == pytest.approx(0.8)

    unspecified = normalize_density("0.787 at 68 \u00b0F (USCG, 1999) - Less dense than water")
    assert (unspecified["subtype"], unspecified["unit"]) == ("unspecified", "unspecified")
    assert unspecified["value_numeric"] == pytest.approx(0.787)
    assert unspecified["temperature_c"] == pytest.approx(20.0)

    vapour = normalize_density("Density of saturated air: 1.04 (Air = 1)")
    assert vapour["subtype"] == "excluded_vapour"
    assert vapour["value_numeric"] is None


def test_density_label_guard_rejects_a_coefficient_line() -> None:
    text = (
        "Coefficient of cubical expansion: 9.56X10-7 at 0-94 \u00b0C; critical density: 0.2734; "
        "specific heat: 0.586 cal/g/deg C at 25 \u00b0C"
    )
    result = normalize_density(text)
    assert result["value_numeric"] is None
    assert result["subtype"] == "unparsed"
    assert result["notes"] == "no_numeric_density_found"


def test_bulk_density_is_excluded() -> None:
    result = normalize_density("Bulk density: 8.0 lb/gal; readily polymerized")
    assert result["subtype"] == "excluded_bulk"
    assert result["value_numeric"] is None


def test_a_table_reference_alone_is_not_a_density() -> None:
    result = normalize_density("Chemical and physical properties[Table#8152]")
    assert result["value_numeric"] is None


def test_value_text_flags_structured_and_table_values() -> None:
    assert value_text({"Value": {"StringWithMarkup": [{"String": "-44 \u00b0C"}]}}) == (
        "-44 \u00b0C",
        "string",
    )
    assert value_text({"Value": {"Number": [0]}}) == ("0", "number")
    assert value_text({"Value": {"Binary": ["abc"]}}) == ("", "inline_table")
    assert value_text({}) == ("", "missing")


# --------------------------------------------------------------------------
# Row building and selection.
# --------------------------------------------------------------------------


def test_rows_carry_depositor_reference_and_quality_flags(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _payload(
            {
                "Melting Point": [
                    _string_info(
                        45,
                        "-44 \u00b0C",
                        description="PEER REVIEWED",
                        citation="Haynes, W.M. (ed.). CRC Handbook of Chemistry and Physics.",
                    ),
                    _string_info(11, "-49 \u00b0F (NTP, 1992)", citation="NTP Chemical Repository"),
                ]
            }
        ),
    )
    client = _client(cache_dir, offline=True)
    rows, status = harvest_compound(_target(), client, retrieved_at="2026-01-01T00:00:00Z")
    assert status == "harvested"
    reviewed = [row for row in rows if row["peer_reviewed"] == "true"]
    assert len(reviewed) == 1
    row = reviewed[0]
    assert row["depositor"] == "Hazardous Substances Data Bank (HSDB)"
    assert row["reference"].startswith("Haynes")
    assert row["source_kind"] == "compilation"
    assert row["quality_layer"] == "filter_only"
    assert row["source_url"] == _heading_url(ACETONITRILE_CID)
    assert row["retrieved_at"] == "2026-01-01T00:00:00Z"
    assert row["value_numeric"] == "-44"

    cameo = next(row for row in rows if row["depositor"] == "CAMEO Chemicals")
    assert cameo["value_numeric"] == "-45"
    assert "converted_from_degF" in cameo["notes"]


def test_an_unparseable_value_keeps_its_raw_text() -> None:
    payload = _payload({"Melting Point": [_string_info(11, "no numeric value here")]})
    rows = build_value_rows(
        _target(), payload["Record"], source_url="u", retrieved_at="t"
    )
    assert rows[0]["value_raw"] == "no numeric value here"
    assert rows[0]["value_numeric"] == ""
    assert rows[0]["notes"] == "no_parseable_temperature"


def test_selection_prefers_the_absolute_density_and_peer_reviewed_rows() -> None:
    rows = [
        _value_row(property="density", subtype="relative", unit="relative", value_numeric="0.79"),
        _value_row(
            property="density",
            subtype="absolute",
            unit="g/cm3",
            value_numeric="0.7822",
            depositor="Hazardous Substances Data Bank (HSDB)",
        ),
        _value_row(property="density", subtype="unspecified", unit="unspecified", value_numeric="0.78"),
        _value_row(property="melting_point", value_numeric="-44", peer_reviewed="false"),
        _value_row(
            property="melting_point",
            value_numeric="-45",
            peer_reviewed="true",
            depositor="Hazardous Substances Data Bank (HSDB)",
        ),
    ]
    selected = {entry["property"]: entry for entry in select_values(rows)}
    assert selected["density"]["value_numeric"] == "0.7822"
    assert selected["density"]["selection_rule"] == DENSITY_SELECTION_RULE
    assert selected["melting_point"]["value_numeric"] == "-45"
    assert selected["melting_point"]["peer_reviewed"] == "true"
    assert selected["melting_point"]["selection_rule"] == TEMPERATURE_SELECTION_RULE
    assert selected["melting_point"]["n_values_seen"] == "2"


def test_selection_takes_the_lower_median_and_keeps_provenance() -> None:
    rows = [
        _value_row(value_numeric="-40", depositor="a", reference_number="1"),
        _value_row(value_numeric="-44", depositor="b", reference_number="2"),
        _value_row(value_numeric="-50", depositor="c", reference_number="3"),
    ]
    entry = select_values(rows)[0]
    assert entry["value_numeric"] == "-44"
    assert entry["depositor"] == "b"
    assert entry["n_parsed_values"] == "3"


def test_selection_skips_a_property_with_no_parsed_value() -> None:
    rows = [_value_row(value_numeric="", notes="no_parseable_temperature")]
    assert select_values(rows) == []


# --------------------------------------------------------------------------
# Run log.
# --------------------------------------------------------------------------


class _FailingClient(PubChemClient):
    def fetch(self, inchikey: str, cid: str, *, refresh: bool = False) -> dict[str, object]:
        raise RuntimeError(f"boom for {inchikey}")


def test_harvest_targets_records_a_failed_request_without_aborting(tmp_path: Path) -> None:
    client = _FailingClient(cache_dir=tmp_path / "cache", offline=True)
    failures: dict[str, str] = {}
    rows, statuses = harvest_targets(
        [_target()], client, retrieved_at="t", failures=failures
    )
    assert statuses[ACETONITRILE] == "request_failed"
    assert rows == []
    assert "boom" in failures[ACETONITRILE]
    assert "request_failed" in HARVEST_STATUSES


def test_run_record_has_every_required_key_and_appends_one_line(tmp_path: Path) -> None:
    client = _client(tmp_path / "empty", offline=True)
    rows, statuses = harvest_targets([_target()], client, retrieved_at="2026-01-01T00:00:00Z")
    selected = select_values(rows)
    summary = summarize(
        rows,
        selected,
        statuses,
        client.stats,
        targets=[_target()],
        run_idempotent=True,
    )
    record = build_run_record(summary, offline=False)
    assert set(REQUIRED_RUN_RECORD_KEYS) <= set(record)
    assert record["requests"] == record["network_calls"] == 0
    assert record["offline"] is False
    assert record["coverage_set"] == 1

    log = tmp_path / "runs.jsonl"
    append_run_log(log, record)
    append_run_log(log, record)
    raw = log.read_bytes()
    assert b"\r" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["coverage_set"] == 1


def test_recorded_harvest_cost_recovers_the_most_expensive_run(tmp_path: Path) -> None:
    log = tmp_path / "runs.jsonl"
    assert recorded_harvest_cost(log)["logged_runs"] == 0
    append_run_log(log, {"network_calls": 0, "retries": 0, "throttle_seconds": 0.0})
    append_run_log(log, {"network_calls": 304, "retries": 2, "throttle_seconds": 74.9})
    cost = recorded_harvest_cost(log)
    assert cost["logged_runs"] == 2
    assert cost["max_network_calls"] == 304
    assert cost["retries_at_max"] == 2
    assert cost["throttle_seconds_at_max"] == pytest.approx(74.9)
    log.write_text("not json\n", encoding="utf-8")
    assert recorded_harvest_cost(log)["logged_runs"] == 0


def test_summarize_reports_the_fields_the_report_reads() -> None:
    client = _client(Path("does-not-matter"), offline=True)
    targets = [_target()]
    rows, statuses = harvest_targets(targets, client, retrieved_at="2026-01-01T00:00:00Z")
    summary = summarize(
        rows,
        select_values(rows),
        statuses,
        ClientStats(),
        targets=targets,
        run_idempotent=True,
    )
    for key in REQUIRED_SUMMARY_KEYS:
        assert key in summary, key
    assert summary["coverage_set"] == 1
    assert summary["harvest_status_counts"] == {"unresolved_offline": 1}
    assert set(summary["harvest_status_counts"]) <= set(HARVEST_STATUSES)
    assert summary["source_kind"] == "compilation"
    assert summary["quality_layer"] == "filter_only"

# --------------------------------------------------------------------------
# Committed artefacts (the cache directory is git-ignored, so skip when absent).
# --------------------------------------------------------------------------


def _read_committed_table(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        pytest.skip(f"{path} is absent; run probes/pubchem_liquid_window_harvest.py first")
    raw = path.read_bytes()
    assert b"\r" not in raw, "the artefact must be written with LF line endings"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == columns
        return list(reader)


def test_committed_summary_has_the_required_fields() -> None:
    assert COMMITTED_SUMMARY.is_file(), "run probes/pubchem_liquid_window_harvest.py first"
    summary = json.loads(COMMITTED_SUMMARY.read_text(encoding="utf-8"))
    for key in REQUIRED_SUMMARY_KEYS:
        assert key in summary, key
    assert summary["coverage_set"] == 314
    assert summary["targets_with_cid"] == 314
    assert summary["source_kind"] == "compilation"
    assert summary["quality_layer"] == "filter_only"
    assert "filter" in summary["quality_layer_note"]
    cost = summary["recorded_harvest_cost_from_log"]
    assert cost["logged_runs"] >= 1
    assert cost["max_network_calls"] > 0, "the harvesting run must be in the log"
    assert isinstance(summary["network_calls"], int)
    assert isinstance(summary["retries"], int)
    assert isinstance(summary["throttle_seconds"], float)
    assert summary["throttle_seconds_per_request"] == 0.25
    assert summary["run_idempotent"] is True
    assert set(summary["harvest_status_counts"]) <= set(HARVEST_STATUSES)
    for name in LIQUID_WINDOW_PROPERTIES:
        coverage = summary["property_coverage"][name]
        assert set(coverage) == {
            "keys_with_value",
            "keys_with_parsed_value",
            "value_rows",
            "peer_reviewed_rows",
            "unparsed_rows",
        }
        assert coverage["keys_with_value"] >= coverage["keys_with_parsed_value"]


def test_committed_summary_agrees_with_the_committed_values_table() -> None:
    assert COMMITTED_SUMMARY.is_file(), "run probes/pubchem_liquid_window_harvest.py first"
    summary = json.loads(COMMITTED_SUMMARY.read_text(encoding="utf-8"))
    rows = _read_committed_table(COMMITTED_VALUES, VALUE_COLUMNS)
    assert summary["value_rows"] == len(rows)
    for name in LIQUID_WINDOW_PROPERTIES:
        subset = [row for row in rows if row["property"] == name]
        coverage = summary["property_coverage"][name]
        assert coverage["value_rows"] == len(subset)
        assert coverage["keys_with_value"] == len({row["inchikey"] for row in subset})
        assert coverage["keys_with_parsed_value"] == len(
            {row["inchikey"] for row in subset if row["value_numeric"]}
        )
        assert coverage["unparsed_rows"] == sum(1 for row in subset if not row["value_numeric"])
        assert coverage["peer_reviewed_rows"] == sum(
            1 for row in subset if row["peer_reviewed"] == "true"
        )
    assert summary["unparsed_value_rows"] == sum(1 for row in rows if not row["value_numeric"])
    assert summary["peer_reviewed_rows"] == sum(
        1 for row in rows if row["peer_reviewed"] == "true"
    )
    for name in TEMPERATURE_PROPERTIES:
        expected = {
            row["inchikey"]
            for row in rows
            if row["property"] == name and row["value_numeric"]
        }
        assert summary["keys_with_mp_bp_fp"][name] == len(expected)


def test_committed_values_are_flagged_as_compilation_filter_only() -> None:
    rows = _read_committed_table(COMMITTED_VALUES, VALUE_COLUMNS)
    assert rows, "the committed run harvested nothing"
    for row in rows:
        assert row["source_kind"] == "compilation"
        assert row["quality_layer"] == "filter_only"
        assert row["peer_reviewed"] in {"true", "false"}
        assert row["retrieved_at"].endswith("Z")
        assert row["source_url"].startswith(PUG_VIEW + "/")
        assert row["source_url"].endswith("heading=" + urllib.parse.quote_plus(EXPERIMENTAL_HEADING))
        if row["value_numeric"]:
            assert row["depositor"] or row["reference"], "a value needs a provenance hook"
    temperatures = [row for row in rows if row["property"] in TEMPERATURE_PROPERTIES]
    for row in temperatures:
        if row["value_numeric"]:
            assert row["unit"] == "degC"
            assert -250.0 <= float(row["value_numeric"]) <= 600.0


def test_committed_selected_table_has_one_row_per_key_and_property() -> None:
    rows = _read_committed_table(COMMITTED_SELECTED, SELECTED_COLUMNS)
    pairs = [(row["inchikey"], row["property"]) for row in rows]
    assert len(pairs) == len(set(pairs))
    assert {row["property"] for row in rows} <= set(LIQUID_WINDOW_PROPERTIES)
    for row in rows:
        assert row["value_numeric"], "a selected row must carry a parsed value"
        assert row["selection_rule"] in {TEMPERATURE_SELECTION_RULE, DENSITY_SELECTION_RULE}
        assert row["source_kind"] == "compilation"
        assert row["quality_layer"] == "filter_only"
        assert int(row["n_values_seen"]) >= int(row["n_parsed_values"]) >= 1


def test_committed_harvest_log_records_the_harvesting_run() -> None:
    if not COMMITTED_LOG.is_file():
        pytest.skip(f"{COMMITTED_LOG} is absent; run probes/pubchem_liquid_window_harvest.py first")
    raw = COMMITTED_LOG.read_bytes()
    assert b"\r" not in raw
    lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert lines, "the run log must receive one line per run"
    for line in lines:
        assert set(REQUIRED_RUN_RECORD_KEYS) <= set(line)
        assert line["requests"] == line["network_calls"]
    # The lesson this probe was written to fix: the harvesting run itself is
    # logged, so the request cost is recoverable from the log alone.
    assert max(line["network_calls"] for line in lines) > 0


def test_acetonitrile_melting_point_is_harvested_from_the_committed_table() -> None:
    rows = _read_committed_table(COMMITTED_VALUES, VALUE_COLUMNS)
    melting = [
        float(row["value_numeric"])
        for row in rows
        if row["inchikey"] == ACETONITRILE
        and row["property"] == "melting_point"
        and row["value_numeric"]
    ]
    # Published acetonitrile melting points cluster near -45 degC; the anchor
    # fails loudly if the parser starts reading Fahrenheit as if it were Celsius.
    assert melting, "acetonitrile carries no parsed melting point"
    assert any(-50.0 <= value <= -40.0 for value in melting)
