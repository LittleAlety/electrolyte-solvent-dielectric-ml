"""Unit tests for the v1.x frequency-gate probe.

Everything here runs offline against canned rows written into tmp_path: the probe
takes raw rows and a roster as plain sequences, so no test needs the real corpus.

Three groups carry most of the weight:

- the *gate* group pins the boundary behaviour (1.0 vs 1.000001 MHz, 3.0 vs
  3.000001 MHz) and the phase filter, because a silent boundary slip would move
  compounds between tiers without changing any headline count.
- the *control* group pins the statistics the frequency ceiling rests on: the
  cross-source consensus, the noise floor, the cumulative bucket edges, the
  same-source counter and the exact-match rate.
- the *honest-failure* group pins that a missing reference yields an empty value
  rather than a number, and that an empty corpus produces zero counts instead of
  an exception.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from probes.dielectric_lowfreq_gate_probe import (
    CANDIDATE_FIELDS,
    EXACT_MATCH_TOLERANCE,
    GATE_EXTENDED,
    GATE_PRIMARY,
    GATE_REJECTED,
    PRIMARY_FREQUENCY_CAP_MHZ,
    analyze,
    build_candidate_rows,
    classify_gate,
    compute_bias_check,
    compute_noise_floor,
    compute_roster_check,
    frequency_bucket,
    frequency_inventory,
    frequency_value,
    group_by_compound,
    is_liquid,
    is_pure,
    is_zero_frequency,
    lowest_frequency_rows,
    main,
    quantile,
    relative_deviation,
    static_consensus,
    summarize_values,
    temperature_band,
    write_csv_rows,
    write_json,
)

RAW_COLUMNS = (
    "source_file",
    "source_sha256",
    "doi",
    "title",
    "dataset_number",
    "property_name",
    "property_family",
    "value",
    "unit",
    "expanded_uncertainty",
    "standard_uncertainty",
    "uncertainty_kind",
    "confidence_level",
    "temperature_k",
    "pressure_kpa",
    "frequency_mhz",
    "phase",
    "method",
    "component_count",
    "is_pure",
    "primary_name",
    "primary_formula",
    "primary_inchi",
    "primary_inchi_key",
    "components_json",
)

ROSTER_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "model_ready",
)

STATIC_KEY = "AAAAAAA-UHFFFAOYSA-N"
BOTH_KEY = "BBBBBBB-UHFFFAOYSA-N"
FREQ_ONLY_KEY = "CCCCCCC-UHFFFAOYSA-N"
GAS_ONLY_KEY = "DDDDDDD-UHFFFAOYSA-N"


def raw_row(**overrides: str) -> dict[str, str]:
    row = dict.fromkeys(RAW_COLUMNS, "")
    row.update(
        {
            "source_file": "data/raw/thermoml/10.1000__synthetic.xml",
            "source_sha256": "deadbeef",
            "doi": "10.1000/synthetic",
            "title": "synthetic",
            "dataset_number": "1",
            "property_name": "Relative permittivity",
            "property_family": "zero_frequency",
            "value": "10.0",
            "temperature_k": "298.15",
            "pressure_kpa": "101.325",
            "frequency_mhz": "0",
            "phase": "Liquid",
            "method": "capacitor",
            "component_count": "1",
            "is_pure": "true",
            "primary_name": "synthetic",
            "primary_formula": "C2H6O",
            "primary_inchi": "InChI=1S/C2H6O",
            "primary_inchi_key": STATIC_KEY,
            "components_json": "[]",
        }
    )
    row.update(overrides)
    return row


def freq_row(**overrides: str) -> dict[str, str]:
    defaults = {
        "property_family": "frequency_dependent",
        "property_name": "Relative permittivity at various frequencies",
        "frequency_mhz": "1",
        "value": "10.0",
        "doi": "10.1000/synthetic-freq",
        "source_file": "data/raw/thermoml/10.1000__synthetic-freq.xml",
    }
    defaults.update(overrides)
    return raw_row(**defaults)


def roster_row(**overrides: str) -> dict[str, str]:
    row = dict.fromkeys(ROSTER_COLUMNS, "")
    row.update(
        {
            "inchikey": STATIC_KEY,
            "smiles": "CCO",
            "name": "synthetic",
            "T_K": "298.15",
            "dielectric": "10.0",
            "model_ready": "true",
        }
    )
    row.update(overrides)
    return row


def write_table(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def corpus() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """A four-compound corpus exercising every branch the probe cares about."""

    rows = [
        raw_row(value="10.0", temperature_k="298.15"),
        raw_row(
            doi="10.1000/two",
            value="12.0",
            temperature_k="298.15",
            source_file="data/raw/thermoml/10.1000__two.xml",
        ),
        raw_row(value="9.0", temperature_k="308.15"),
        freq_row(
            primary_inchi_key=BOTH_KEY,
            primary_name="both",
            value="20.0",
            frequency_mhz="1",
            temperature_k="298.15",
        ),
        freq_row(
            primary_inchi_key=BOTH_KEY,
            primary_name="both",
            value="19.0",
            frequency_mhz="0.01",
            temperature_k="298.15",
        ),
        freq_row(
            primary_inchi_key=BOTH_KEY,
            primary_name="both",
            value="18.0",
            frequency_mhz="30",
            temperature_k="298.15",
        ),
        raw_row(
            primary_inchi_key=BOTH_KEY,
            primary_name="both",
            value="20.4",
            temperature_k="298.15",
        ),
        freq_row(
            primary_inchi_key=FREQ_ONLY_KEY,
            primary_name="freq-only",
            value="5.0",
            frequency_mhz="0.05",
            temperature_k="283.15",
        ),
        freq_row(
            primary_inchi_key=FREQ_ONLY_KEY,
            primary_name="freq-only",
            value="4.9",
            frequency_mhz="0.1",
            temperature_k="283.15",
        ),
        freq_row(
            primary_inchi_key=FREQ_ONLY_KEY,
            primary_name="freq-only",
            value="4.5",
            frequency_mhz="2",
            temperature_k="293.15",
        ),
        freq_row(
            primary_inchi_key=FREQ_ONLY_KEY,
            primary_name="freq-only",
            value="4.4",
            frequency_mhz="340",
            temperature_k="303.15",
        ),
        freq_row(
            primary_inchi_key=GAS_ONLY_KEY,
            primary_name="gas-only",
            phase="Gas",
            value="1.0",
            frequency_mhz="200",
            temperature_k="250.0",
        ),
        freq_row(
            primary_inchi_key=GAS_ONLY_KEY,
            primary_name="gas-only",
            phase="Fluid (supercritical or subcritical phases)",
            value="1.1",
            frequency_mhz="270",
            temperature_k="260.0",
        ),
    ]
    return rows, [roster_row()]


# --------------------------------------------------------------------------- #
# Gates and buckets
# --------------------------------------------------------------------------- #


def test_frequency_bucket_edges_are_cumulative() -> None:
    assert frequency_bucket(0.001) == "<=0.01"
    assert frequency_bucket(0.01) == "<=0.01"
    assert frequency_bucket(0.011) == "<=0.1"
    assert frequency_bucket(0.1) == "<=0.1"
    assert frequency_bucket(0.101) == "<=1"
    assert frequency_bucket(1.0) == "<=1"
    assert frequency_bucket(1.5) == "<=10"
    assert frequency_bucket(10.0) == "<=10"
    assert frequency_bucket(10.001) == ">10"
    assert frequency_bucket(340.0) == ">10"


def test_classify_gate_primary_tier() -> None:
    assert classify_gate(0.001) == GATE_PRIMARY
    assert classify_gate(0.06) == GATE_PRIMARY
    assert classify_gate(PRIMARY_FREQUENCY_CAP_MHZ) == GATE_PRIMARY


def test_classify_gate_boundaries_are_exclusive_at_the_top_tier() -> None:
    assert classify_gate(1.000001) == GATE_EXTENDED
    assert classify_gate(3.0) == GATE_EXTENDED
    assert classify_gate(3.000001) == GATE_REJECTED
    assert classify_gate(340.0) == GATE_REJECTED


def test_phase_and_purity_filters() -> None:
    assert is_pure({"is_pure": "TRUE"})
    assert is_pure({"is_pure": " true "})
    assert not is_pure({"is_pure": "false"})
    assert not is_pure({})
    assert is_liquid({"phase": "Liquid"})
    assert not is_liquid({"phase": "Gas"})
    assert not is_liquid({"phase": "Crystal"})
    assert not is_liquid({"phase": "Fluid (supercritical or subcritical phases)"})


def test_is_zero_frequency_requires_the_exact_family() -> None:
    assert is_zero_frequency({"property_family": "zero_frequency"})
    assert not is_zero_frequency({"property_family": "frequency_dependent"})
    assert not is_zero_frequency({"property_family": "zero frequency"})


def test_temperature_band_labels() -> None:
    assert temperature_band(293.15) == "room_temperature"
    assert temperature_band(303.15) == "room_temperature"
    assert temperature_band(313.15) == "extended_temperature"
    assert temperature_band(323.15) == "extended_temperature"
    assert temperature_band(323.16) == "outside_declared_window"
    assert temperature_band(218.12) == "outside_declared_window"


def test_frequency_value_parses_blank_as_none() -> None:
    assert frequency_value({"frequency_mhz": "1"}) == 1.0
    assert frequency_value({"frequency_mhz": ""}) is None
    assert frequency_value({"frequency_mhz": "abc"}) is None


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_group_by_compound_splits_by_inchikey() -> None:
    rows, _ = corpus()
    grouped = group_by_compound(rows)
    assert set(grouped) == {STATIC_KEY, BOTH_KEY, FREQ_ONLY_KEY, GAS_ONLY_KEY}
    assert len(grouped[FREQ_ONLY_KEY]) == 4


def test_lowest_frequency_rows_keeps_the_lowest_per_temperature() -> None:
    rows, _ = corpus()
    freq_only = [
        row for row in rows if row["primary_inchi_key"] == FREQ_ONLY_KEY
    ]
    selected = lowest_frequency_rows(freq_only)
    kept = {row["temperature_k"]: row["frequency_mhz"] for _, row in selected}
    assert kept == {"283.15": "0.05", "293.15": "2", "303.15": "340"}


def test_lowest_frequency_rows_keeps_distinct_temperatures() -> None:
    rows = [
        freq_row(temperature_k="298.15", frequency_mhz="1", value="1.0"),
        freq_row(temperature_k="308.15", frequency_mhz="1", value="2.0"),
    ]
    selected = lowest_frequency_rows(rows)
    assert len(selected) == 2


def test_lowest_frequency_rows_tie_break_is_deterministic() -> None:
    rows = [
        freq_row(frequency_mhz="1", value="1.0", dataset_number="1"),
        freq_row(frequency_mhz="1", value="2.0", dataset_number="2"),
    ]
    selected = lowest_frequency_rows(rows)
    assert len(selected) == 1
    assert selected[0][0] == 0
    assert selected[0][1]["dataset_number"] == "1"


def test_lowest_frequency_rows_drops_unusable_rows() -> None:
    rows = [
        freq_row(value="0", frequency_mhz="1"),
        freq_row(value="-3", frequency_mhz="1"),
        freq_row(value="9", frequency_mhz="1", temperature_k=""),
    ]
    assert lowest_frequency_rows(rows) == []


# --------------------------------------------------------------------------- #
# The control: consensus, noise floor, bias curve
# --------------------------------------------------------------------------- #


def test_static_consensus_is_the_median_with_its_source_count() -> None:
    rows, _ = corpus()
    grouped = group_by_compound(
        [
            row
            for row in rows
            if is_zero_frequency(row) and is_liquid(row)
        ]
    )
    consensus, sources = static_consensus(grouped, STATIC_KEY, 298.15)
    assert sources == 2
    assert consensus == 11.0


def test_static_consensus_excludes_rows_outside_the_temperature_tolerance() -> None:
    rows = [
        raw_row(value="10.0", temperature_k="298.15"),
        raw_row(value="40.0", temperature_k="302.15"),
    ]
    grouped = group_by_compound(rows)
    consensus, sources = static_consensus(grouped, STATIC_KEY, 298.15)
    assert sources == 1
    assert consensus == 10.0


def test_static_consensus_returns_none_without_a_match() -> None:
    rows = [raw_row(value="10.0", temperature_k="298.15")]
    grouped = group_by_compound(rows)
    consensus, sources = static_consensus(grouped, "ZZZZZZZ-UHFFFAOYSA-N", 298.15)
    assert consensus is None
    assert sources == 0


def test_static_consensus_ignores_non_positive_values() -> None:
    rows = [
        raw_row(value="0.0", temperature_k="298.15"),
        raw_row(value="8.0", temperature_k="298.15"),
    ]
    grouped = group_by_compound(rows)
    consensus, sources = static_consensus(grouped, STATIC_KEY, 298.15)
    assert sources == 1
    assert consensus == 8.0


def test_relative_deviation_sign_and_missing_reference() -> None:
    assert relative_deviation(11.0, 10.0) == 0.1
    assert relative_deviation(9.0, 10.0) == -0.1
    assert relative_deviation(None, 10.0) is None
    assert relative_deviation(10.0, None) is None
    assert relative_deviation(10.0, 0.0) is None


def test_quantile_is_upper_nearest_rank() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 0.5) == 3.0
    assert quantile(values, 0.99) == 4.0
    assert quantile([], 0.5) is None


def test_summarize_values_reports_quantiles() -> None:
    stats = summarize_values([1.0, 2.0, 3.0, 4.0])
    assert stats["n"] == 4
    assert stats["median"] == 2.5
    assert stats["max"] == 4.0
    assert stats["p75"] == 4.0


def test_summarize_values_of_nothing_is_empty() -> None:
    assert summarize_values([]) == {"n": 0}


def test_noise_floor_measures_cross_source_spread() -> None:
    rows = [
        raw_row(value="10.0", temperature_k="298.15"),
        raw_row(value="12.0", temperature_k="298.15", doi="10.1000/two"),
    ]
    floor = compute_noise_floor(group_by_compound(rows))
    assert floor["comparisons"] == 2
    assert floor["absolute"]["max_percent"] == 100.0 * (1.0 / 11.0)


def test_noise_floor_skips_groups_with_a_single_source() -> None:
    rows = [raw_row(value="10.0", temperature_k="298.15")]
    floor = compute_noise_floor(group_by_compound(rows))
    assert floor["comparisons"] == 0


def test_bias_check_counts_one_pair_per_frequency_row() -> None:
    rows, _ = corpus()
    zero_by_compound = group_by_compound(
        [row for row in rows if is_zero_frequency(row) and is_liquid(row)]
    )
    freq_rows = [
        row
        for row in rows
        if row["property_family"] == "frequency_dependent"
        and is_liquid(row)
    ]
    check = compute_bias_check(freq_rows, zero_by_compound)
    assert check["matched_pairs"] == 3
    assert check["distinct_compounds"] == 1
    assert check["same_source_pairs"] == 0


def test_bias_check_records_a_same_source_pair() -> None:
    rows = [
        raw_row(value="10.0", temperature_k="298.15"),
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="10.0",
            frequency_mhz="1",
            temperature_k="298.15",
            doi="10.1000/synthetic",
            source_file="data/raw/thermoml/10.1000__synthetic.xml",
        ),
    ]
    zero_by_compound = group_by_compound([rows[0]])
    check = compute_bias_check([rows[1]], zero_by_compound)
    assert check["matched_pairs"] == 1
    assert check["same_source_pairs"] == 1


def test_bias_check_drops_pairs_beyond_the_temperature_tolerance() -> None:
    rows = [
        raw_row(value="10.0", temperature_k="298.15"),
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="10.0",
            temperature_mhz="1",
            temperature_k="305.0",
        ),
    ]
    check = compute_bias_check([rows[1]], group_by_compound([rows[0]]))
    assert check["matched_pairs"] == 0


def test_bias_check_buckets_are_cumulative() -> None:
    zero = raw_row(value="10.0", temperature_k="298.15")
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="10.0",
            frequency_mhz=str(f),
            temperature_k="298.15",
        )
        for f in (0.001, 0.01, 0.1, 1, 2, 3, 30, 340)
    ]
    check = compute_bias_check(freq_rows, group_by_compound([zero]))
    by_label = {entry["bucket"]: entry for entry in check["buckets"]}
    # Every row lands in exactly one bucket; the labels are the upper edges.
    assert by_label["<=0.01"]["pairs"] == 2
    assert by_label["<=0.1"]["pairs"] == 1
    assert by_label["<=1"]["pairs"] == 1
    assert by_label["<=10"]["pairs"] == 2
    assert by_label[">10"]["pairs"] == 2
    assert sum(entry["pairs"] for entry in check["buckets"]) == len(freq_rows)


def test_bias_check_counts_exact_matches() -> None:
    zero = raw_row(value="10.0", temperature_k="298.15")
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value=str(value),
            frequency_mhz="1",
            temperature_k="298.15",
        )
        for value in (10.0, 10.0 + 100.0 * EXACT_MATCH_TOLERANCE, 11.0)
    ]
    check = compute_bias_check(freq_rows, group_by_compound([zero]))
    entry = check["per_frequency"][0]
    assert entry["exact_matches"] == 1
    assert entry["exact_match_rate"] is not None
    assert abs(entry["exact_match_rate"] - 1.0 / 3.0) < 1e-12


def test_bias_check_worst_offenders_are_sorted_by_magnitude() -> None:
    zero = raw_row(value="10.0", temperature_k="298.15")
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value=str(value),
            frequency_mhz="1",
            temperature_k="298.15",
        )
        for value in (9.0, 20.0, 10.5)
    ]
    check = compute_bias_check(freq_rows, group_by_compound([zero]))
    magnitudes = [
        item["absolute_deviation_percent"] for item in check["worst_offenders"]
    ]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert round(magnitudes[0], 6) == 100.0
    assert round(magnitudes[-1], 6) == 5.0


def test_bias_check_signed_and_absolute_are_both_reported() -> None:
    zero = raw_row(value="10.0", temperature_k="298.15")
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="9.0",
            frequency_mhz="1",
            temperature_k="298.15",
        )
    ]
    check = compute_bias_check(freq_rows, group_by_compound([zero]))
    entry = check["per_frequency"][0]
    assert entry["signed"]["median_percent"] == -10.0
    assert entry["absolute"]["median_percent"] == 10.0
    assert entry["positive_deviations"] == 0


def test_roster_check_splits_temperature_matched_from_all() -> None:
    rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="9.0",
            frequency_mhz="1",
            temperature_k="298.15",
        ),
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="8.0",
            frequency_mhz="1",
            temperature_k="320.0",
        ),
    ]
    check = compute_roster_check(rows, {STATIC_KEY: roster_row()})
    assert check["comparisons"] == 2
    assert check["temperature_matched_comparisons"] == 1
    assert check["temperature_matched_compounds"] == 1
    entry = check["per_frequency"][0]
    assert entry["comparisons"] == 2
    assert entry["temperature_matched"] == 1
    assert entry["absolute_temperature_matched"]["median_percent"] == 10.0


# --------------------------------------------------------------------------- #
# Candidate rows
# --------------------------------------------------------------------------- #


def test_candidate_rows_exclude_compounds_that_have_static_rows() -> None:
    rows, roster = corpus()
    liquid_freq = [
        row
        for row in rows
        if row["property_family"] == "frequency_dependent" and is_liquid(row)
    ]
    candidates, dropped = build_candidate_rows(
        liquid_freq, {STATIC_KEY, BOTH_KEY}, {row["inchikey"]: row for row in roster}
    )
    assert {row["inchikey"] for row in candidates} == {FREQ_ONLY_KEY}
    assert dropped["compound_has_zero_frequency_row"] == 3


def test_candidate_rows_pick_the_lowest_frequency_per_temperature() -> None:
    rows, roster = corpus()
    liquid_freq = [
        row
        for row in rows
        if row["property_family"] == "frequency_dependent" and is_liquid(row)
    ]
    candidates, _ = build_candidate_rows(
        liquid_freq, {STATIC_KEY, BOTH_KEY}, {row["inchikey"]: row for row in roster}
    )
    assert [(row["T_K"], row["frequency_mhz"]) for row in candidates] == [
        ("283.15", "0.05"),
        ("293.15", "2"),
        ("303.15", "340"),
    ]


def test_candidate_rows_carry_gate_labels() -> None:
    rows, roster = corpus()
    liquid_freq = [
        row
        for row in rows
        if row["property_family"] == "frequency_dependent" and is_liquid(row)
    ]
    candidates, _ = build_candidate_rows(
        liquid_freq, {STATIC_KEY, BOTH_KEY}, {row["inchikey"]: row for row in roster}
    )
    gates = {row["frequency_mhz"]: row["gate"] for row in candidates}
    assert gates == {
        "0.05": GATE_PRIMARY,
        "2": GATE_EXTENDED,
        "340": GATE_REJECTED,
    }


def test_candidate_rows_record_the_frequencies_offered_at_that_temperature() -> None:
    rows, roster = corpus()
    liquid_freq = [
        row
        for row in rows
        if row["property_family"] == "frequency_dependent" and is_liquid(row)
    ]
    candidates, _ = build_candidate_rows(
        liquid_freq, {STATIC_KEY, BOTH_KEY}, {row["inchikey"]: row for row in roster}
    )
    first = candidates[0]
    assert first["frequencies_at_temperature"] == "0.05;0.1"
    assert first["n_values_at_same_temperature"] == "2"


def test_candidate_rows_fill_roster_fields_when_the_compound_is_known() -> None:
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="9.0",
            frequency_mhz="1",
            temperature_k="298.15",
        )
    ]
    candidates, _ = build_candidate_rows(
        freq_rows, set(), {STATIC_KEY: roster_row()}
    )
    row = candidates[0]
    assert row["in_roster"] == "true"
    assert row["roster_dielectric"] == "10.0"
    assert row["roster_temperature_delta_K"] == "0"
    assert row["deviation_vs_roster_static_percent"] == "-10.0000"


def test_candidate_rows_leave_the_deviation_blank_when_temperatures_do_not_match() -> None:
    freq_rows = [
        freq_row(
            primary_inchi_key=STATIC_KEY,
            value="9.0",
            frequency_mhz="1",
            temperature_k="330.0",
        )
    ]
    candidates, _ = build_candidate_rows(
        freq_rows, set(), {STATIC_KEY: roster_row()}
    )
    row = candidates[0]
    assert row["deviation_vs_roster_static_percent"] == ""
    assert row["roster_temperature_delta_K"] == "31.85"


def test_candidate_rows_leave_roster_fields_blank_for_unknown_compounds() -> None:
    freq_rows = [
        freq_row(
            primary_inchi_key=FREQ_ONLY_KEY,
            primary_name="freq-only",
            value="5.0",
            frequency_mhz="1",
            temperature_k="298.15",
        )
    ]
    candidates, _ = build_candidate_rows(freq_rows, set(), {})
    row = candidates[0]
    assert row["in_roster"] == "false"
    assert row["roster_dielectric"] == ""
    assert row["roster_temperature_delta_K"] == ""
    assert row["deviation_vs_roster_static_percent"] == ""
    assert row["name"] == "freq-only"


def test_candidate_rows_flag_pressure_relative_to_one_atmosphere() -> None:
    freq_rows = [
        freq_row(pressure_kpa="101.325", frequency_mhz="1"),
        freq_row(pressure_kpa="1121.52", frequency_mhz="1", temperature_k="303.15"),
        freq_row(pressure_kpa="", frequency_mhz="1", temperature_k="313.15"),
    ]
    candidates, _ = build_candidate_rows(freq_rows, set(), {})
    flags = [row["near_atmospheric_pressure"] for row in candidates]
    assert flags == ["true", "false", "unknown"]


def test_candidate_rows_expose_exactly_the_declared_fields() -> None:
    rows, roster = corpus()
    candidates, _ = build_candidate_rows(
        [row for row in rows if is_liquid(row) and not is_zero_frequency(row)],
        {STATIC_KEY, BOTH_KEY},
        {row["inchikey"]: row for row in roster},
    )
    assert candidates
    for row in candidates:
        assert tuple(row) == CANDIDATE_FIELDS


# --------------------------------------------------------------------------- #
# Inventory and summary
# --------------------------------------------------------------------------- #


def test_frequency_inventory_counts_every_family() -> None:
    rows, _ = corpus()
    inventory = frequency_inventory([row for row in rows if is_pure(row)])
    assert inventory["liquid_zero_frequency_compounds"] == 2
    assert inventory["liquid_frequency_dependent_compounds"] == 2
    assert inventory["both_compounds"] == 1
    assert inventory["frequency_only_compounds"] == 1
    assert inventory["non_liquid_frequency_only_compounds"] == [GAS_ONLY_KEY]
    assert inventory["non_liquid_frequency_only_rows"] == 2
    assert inventory["frequency_value_histogram"]["0.05"] == 1


def test_analyze_reports_the_dropped_row_tally_and_the_not_verified_list() -> None:
    rows, roster = corpus()
    _, summary = analyze(rows, roster)
    assert summary["dropped_frequency_rows"] == {"compound_has_zero_frequency_row": 3}
    assert summary["gate_decision"]["primary_cap_mhz"] == PRIMARY_FREQUENCY_CAP_MHZ
    assert len(summary["not_verified"]) == 3


def test_analyze_accepts_the_extended_tier_but_not_the_high_one() -> None:
    rows, roster = corpus()
    candidates, summary = analyze(rows, roster)
    totals = summary["candidates"]
    assert totals["rows"] == len(candidates) == 3
    assert totals["rows_by_gate"] == {
        GATE_EXTENDED: 1,
        GATE_PRIMARY: 1,
        GATE_REJECTED: 1,
    }
    assert totals["accepted_rows"] == 2
    assert totals["accepted_compounds"] == 1
    assert totals["accepted_new_compounds"] == 1
    assert totals["temperature_k"] == {"min": 283.15, "max": 303.15}
    assert totals["accepted_temperature_k"] == {"min": 283.15, "max": 293.15}


def test_analyze_on_an_empty_corpus_returns_zero_counts() -> None:
    candidates, summary = analyze([], [])
    assert candidates == []
    assert summary["candidates"]["rows"] == 0
    assert summary["candidates"]["rows_by_gate"] == {}
    assert summary["candidates"]["accepted_new_compounds"] == 0
    assert summary["bias_check"]["matched_pairs"] == 0
    assert summary["bias_check"]["buckets"][0]["pairs"] == 0
    assert summary["roster_check"]["comparisons"] == 0


# --------------------------------------------------------------------------- #
# Writers and the command line
# --------------------------------------------------------------------------- #


def test_write_csv_rows_uses_lf_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    write_csv_rows(path, ("a", "b"), [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])
    payload = path.read_bytes()
    assert b"\r\n" not in payload
    assert payload == b"a,b\n1,2\n3,4\n"


def test_write_json_ends_with_a_single_newline(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json(path, {"b": 1, "a": [1, 2]})
    payload = path.read_bytes()
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert json.loads(payload.decode("utf-8")) == {"b": 1, "a": [1, 2]}


def test_write_csv_rows_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "out.csv"
    write_csv_rows(path, ("a",), [{"a": "1"}])
    assert path.read_text(encoding="utf-8") == "a\n1\n"


def _run_main(tmp_path: Path, rows, roster) -> tuple[Path, Path]:
    raw = write_table(tmp_path / "raw.csv", RAW_COLUMNS, rows)
    roster_path = write_table(tmp_path / "roster.csv", ROSTER_COLUMNS, roster)
    out = tmp_path / "candidates.csv"
    summary = tmp_path / "summary.json"
    exit_code = main(
        [
            "--raw",
            str(raw),
            "--roster",
            str(roster_path),
            "--output",
            str(out),
            "--summary",
            str(summary),
        ]
    )
    assert exit_code == 0
    return out, summary


def test_main_writes_the_candidate_table_and_summary(tmp_path: Path) -> None:
    rows, roster = corpus()
    out, summary_path = _run_main(tmp_path, rows, roster)
    written = list(csv.DictReader(out.open(encoding="utf-8", newline="")))
    assert len(written) == 3
    assert tuple(written[0]) == CANDIDATE_FIELDS
    document = json.loads(summary_path.read_text(encoding="utf-8"))
    assert document["frequency_inventory"]["frequency_only_compounds"] == 1
    assert document["candidates"]["rows"] == 3
    assert document["inputs"]["raw_rows"] == len(rows)
    assert document["inputs"]["roster_rows"] == len(roster)
    assert document["frozen_roster_digest_unchanged"] is False


def test_main_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    rows, roster = corpus()
    out, summary_path = _run_main(tmp_path, rows, roster)
    first_csv = out.read_bytes()
    first_json = summary_path.read_bytes()
    _run_main(tmp_path, rows, roster)
    assert out.read_bytes() == first_csv
    assert summary_path.read_bytes() == first_json


def test_main_does_not_touch_the_roster(tmp_path: Path) -> None:
    rows, roster = corpus()
    raw = write_table(tmp_path / "raw.csv", RAW_COLUMNS, rows)
    roster_path = write_table(tmp_path / "roster.csv", ROSTER_COLUMNS, roster)
    before = roster_path.read_bytes()
    main(
        [
            "--raw",
            str(raw),
            "--roster",
            str(roster_path),
            "--output",
            str(tmp_path / "c.csv"),
            "--summary",
            str(tmp_path / "s.json"),
        ]
    )
    assert roster_path.read_bytes() == before


def test_main_handles_a_header_only_corpus(tmp_path: Path) -> None:
    out, summary_path = _run_main(tmp_path, [], [])
    assert out.read_text(encoding="utf-8") == ",".join(CANDIDATE_FIELDS) + "\n"
    document = json.loads(summary_path.read_text(encoding="utf-8"))
    assert document["candidates"]["rows"] == 0
    assert document["inputs"]["raw_rows"] == 0
