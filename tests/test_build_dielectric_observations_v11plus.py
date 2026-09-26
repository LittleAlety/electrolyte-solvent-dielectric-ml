"""Tests for the merged v1.x observation table builder."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_dielectric_observations_v11plus import (
    ADMITTED_GATES,
    EXTRA_FIELDS,
    LOW_FREQUENCY_ORIGIN,
    SMILE_SOURCE_CANDIDATE,
    SMILE_SOURCE_STRUCTURES,
    SMILE_SOURCE_V11,
    ZERO_FREQUENCY_ORIGIN,
    build_merged_rows,
    load_resolved_smiles,
    read_csv_rows,
    run,
    summarise,
    write_csv_rows,
)

V11_FIELDS = [
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "epsilon",
    "frequency_mhz",
    "source_doi",
    "source_row_index",
    "temperature_band",
]


def _v11_row(key: str = "AAA-BBB-C", temperature: str = "298.15") -> dict[str, str]:
    return {
        "inchikey": key,
        "name": "known",
        "smiles": "CCO",
        "T_K": temperature,
        "epsilon": "24.5",
        "frequency_mhz": "0",
        "source_doi": "10.1/v11",
        "source_row_index": "7",
        "temperature_band": "room_temperature",
    }


def _candidate_row(
    key: str = "CCC-DDD-E",
    gate: str = ADMITTED_GATES[0],
    *,
    smiles: str = "",
    temperature: str = "298.15",
) -> dict[str, str]:
    return {
        "inchikey": key,
        "name": "new",
        "smiles": smiles,
        "T_K": temperature,
        "epsilon": "3.1",
        "frequency_mhz": "1",
        "source_doi": "10.1/lf",
        "source_row_index": "11",
        "temperature_band": "room_temperature",
        "gate": gate,
    }


def _structure_row(key: str = "CCC-DDD-E") -> dict[str, str]:
    return {"inchikey": key, "resolved_smiles": "CCCl", "name": "new"}


def test_zero_frequency_rows_keep_the_v11_payload() -> None:
    merged, counters = build_merged_rows(
        [_v11_row()], V11_FIELDS, [], {}
    )

    assert counters == {}
    assert len(merged) == 1
    row = merged[0]
    assert row["observation_origin"] == ZERO_FREQUENCY_ORIGIN
    assert row["frequency_gate"] == "zero_frequency"
    assert row["smiles_source"] == SMILE_SOURCE_V11
    assert row["epsilon"] == "24.5"


def test_only_admitted_gates_are_merged() -> None:
    candidates = [
        _candidate_row("CCC-DDD-E", ADMITTED_GATES[0]),
        _candidate_row("FFF-GGG-H", ADMITTED_GATES[1]),
        _candidate_row("III-JJJ-K", "rejected_highfreq"),
    ]

    merged, counters = build_merged_rows([], V11_FIELDS, candidates, {})

    assert len(merged) == 2
    assert counters["skipped_by_gate"] == 1
    assert {row["frequency_gate"] for row in merged} == set(ADMITTED_GATES)


def test_smiles_are_backfilled_from_the_structure_table() -> None:
    resolved = load_resolved_smiles([_structure_row()])

    merged, counters = build_merged_rows(
        [], V11_FIELDS, [_candidate_row()], resolved
    )

    assert counters["smiles_backfilled"] == 1
    assert merged[0]["smiles"] == "CCCl"
    assert merged[0]["smiles_source"] == SMILE_SOURCE_STRUCTURES


def test_candidate_smiles_win_over_the_structure_table() -> None:
    resolved = load_resolved_smiles([_structure_row()])

    merged, _ = build_merged_rows(
        [], V11_FIELDS, [_candidate_row(smiles="CCBr")], resolved
    )

    assert merged[0]["smiles"] == "CCBr"
    assert merged[0]["smiles_source"] == SMILE_SOURCE_CANDIDATE


def test_missing_smiles_is_counted_not_invented() -> None:
    merged, counters = build_merged_rows([], V11_FIELDS, [_candidate_row()], {})

    assert counters["smiles_missing"] == 1
    assert merged[0]["smiles"] == ""
    assert merged[0]["smiles_source"] == ""


def test_structure_rows_without_smiles_are_ignored() -> None:
    resolved = load_resolved_smiles([{"inchikey": "CCC-DDD-E", "resolved_smiles": "  "}])

    assert resolved == {}


def test_summarise_counts_compounds_and_original_overlap() -> None:
    v11 = [_v11_row(), _v11_row(temperature="303.15")]
    candidates = [_candidate_row("CCC-DDD-E"), _candidate_row("FFF-GGG-H", "rejected_highfreq")]
    merged, counters = build_merged_rows(v11, V11_FIELDS, candidates, {})

    summary = summarise(merged, v11, candidates, counters)

    assert summary["rows"] == 3
    assert summary["compounds"] == 2
    assert summary["compounds_added_over_v11"] == 1
    assert summary["rows_by_origin"] == {
        ZERO_FREQUENCY_ORIGIN: 2,
        LOW_FREQUENCY_ORIGIN: 1,
    }
    assert summary["rows_missing_source_doi"] == 0


def test_summarise_detects_cross_origin_overlap() -> None:
    v11 = [_v11_row("CCC-DDD-E")]
    candidates = [_candidate_row("CCC-DDD-E")]
    merged, counters = build_merged_rows(v11, V11_FIELDS, candidates, {})

    summary = summarise(merged, v11, candidates, counters)

    assert summary["origin_overlap_rows"] == 1


def test_write_csv_rows_emits_lf_only(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    write_csv_rows(path, V11_FIELDS + list(EXTRA_FIELDS), [_v11_row()])

    raw = path.read_bytes()

    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_main_writes_the_table_and_the_summary(tmp_path: Path) -> None:
    v11_path = tmp_path / "v11.csv"
    candidate_path = tmp_path / "candidates.csv"
    structure_path = tmp_path / "structures.csv"
    output = tmp_path / "merged.csv"
    summary_path = tmp_path / "summary.json"

    write_csv_rows(v11_path, V11_FIELDS, [_v11_row()])
    write_csv_rows(
        candidate_path,
        V11_FIELDS + ["gate"],
        [_candidate_row(), _candidate_row("III-JJJ-K", "rejected_highfreq")],
    )
    write_csv_rows(structure_path, ["inchikey", "resolved_smiles"], [_structure_row()])

    summary = run(
        v11_path=v11_path,
        candidates_path=candidate_path,
        structures_path=structure_path,
        output_path=output,
        summary_path=summary_path,
    )

    merged_rows, merged_fields = read_csv_rows(output)
    assert summary["rows"] == 2
    assert summary["compounds"] == 2
    assert summary["rows_by_origin"] == {
        ZERO_FREQUENCY_ORIGIN: 1,
        LOW_FREQUENCY_ORIGIN: 1,
    }
    assert merged_fields == V11_FIELDS + list(EXTRA_FIELDS)
    assert merged_rows[1]["smiles"] == "CCCl"
    assert bytes([13, 10]) not in output.read_bytes()
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written["rows"] == 2
