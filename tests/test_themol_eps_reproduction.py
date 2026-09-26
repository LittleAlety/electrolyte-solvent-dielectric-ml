"""Recompute the chain A / chain B THEMol reproduction facts from the frozen inputs.

Both inputs are committed -- chain A is the delivery layer and chain B is the frozen
shard copy under probes/themol_eps_reproduction_inputs/ -- so no test here needs a
network skip marker.

The assertions recompute grouping, representative selection and the deltas from the
two source tables instead of only re-reading the artefacts, so a silent edit on either
side fails here rather than quietly re-baselining.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import themol_eps_reproduction as repro

FACTS = REPOSITORY_ROOT / "probes/themol_eps_reproduction_facts.csv"
SUMMARY = REPOSITORY_ROOT / "probes/themol_eps_reproduction_summary.json"
GENERATOR = REPOSITORY_ROOT / "probes/themol_eps_reproduction.py"
CHAIN_B_DIR = REPOSITORY_ROOT / "probes/themol_eps_reproduction_inputs"

INCHIKEY = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
LEVELS = (
    ("homo", "homo_gfn2_eV", "homo_eV"),
    ("lumo", "lumo_gfn2_eV", "lumo_eV"),
    ("gap", "gap_gfn2_eV", "gap_eV"),
)

# Both chains print the levels to four decimals, so one unit in the last printed digit
# is the expected noise floor.
PRINTED_TOLERANCE_EV = 1.0e-4
# The gap is printed as a difference of two printed levels, so its error can be the sum
# of both endpoint errors rather than one printed unit.
GAP_TOLERANCE_EV = 2.0 * PRINTED_TOLERANCE_EV


def read_facts() -> list[dict[str, str]]:
    """Read the facts CSV exactly as written."""
    with FACTS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_summary() -> dict:
    """Read the summary JSON exactly as written."""
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def layer_index() -> dict[str, dict[str, str]]:
    """Index chain A's layer by InChIKey."""
    return {row["inchikey"]: row for row in repro.read_layer()}


def chain_b_index() -> dict[str, list[dict[str, str]]]:
    """Group the frozen chain B shards by InChIKey, first-seen order preserved."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in repro.read_chain_b():
        grouped.setdefault(row["inchikey"], []).append(row)
    return grouped


def representative(rows: list[dict[str, str]]) -> dict[str, str]:
    """The value-bearing chain B row for one key, recomputed independently."""
    for row in rows:
        if row["homo_eV"].strip():
            return row
    return rows[-1]


def test_facts_row_set_is_the_chain_b_key_union() -> None:
    facts = read_facts()
    keys = [row["inchikey"] for row in facts]
    assert len(facts) == 51
    assert keys == sorted(set(keys))
    assert keys == sorted(chain_b_index())
    assert all(INCHIKEY.match(key) for key in keys)
    assert read_summary()["match"]["only_in_b"] == 0


def test_facts_columns_match_the_declared_contract() -> None:
    with FACTS.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == repro.FACTS_COLUMNS


def test_every_key_is_read_verbatim_from_both_inputs() -> None:
    layer_text = repro.LAYER.read_text(encoding="utf-8")
    shard_texts = [
        (CHAIN_B_DIR / shard).read_text(encoding="utf-8")
        for shard in repro.CHAIN_B_SHARDS
    ]
    for row in read_facts():
        key = row["inchikey"]
        assert key in layer_text
        assert any(key in text for text in shard_texts)


def test_deltas_are_recomputed_from_the_two_source_tables() -> None:
    layer = layer_index()
    grouped = chain_b_index()
    for fact in read_facts():
        key = fact["inchikey"]
        chain_a_row = layer[key]
        chain_b_row = representative(grouped[key])
        for level, chain_a_column, chain_b_column in LEVELS:
            chain_a_text = chain_a_row[chain_a_column]
            chain_b_text = chain_b_row[chain_b_column]
            assert fact[level + "_a_eV"] == chain_a_text
            assert fact[level + "_b_eV"] == chain_b_text
            reported = fact["delta_" + level + "_eV"]
            if not chain_a_text.strip() or not chain_b_text.strip():
                assert reported == ""
                continue
            expected = round(float(chain_a_text) - float(chain_b_text), 9)
            assert abs(float(reported) - expected) <= 5e-7


def test_absolute_deltas_stay_at_the_printed_precision() -> None:
    facts = read_facts()
    maxima = {}
    for level, _, _ in LEVELS:
        magnitudes = [
            abs(float(row["delta_" + level + "_eV"]))
            for row in facts
            if row["delta_" + level + "_eV"]
        ]
        assert len(magnitudes) == 47
        maxima[level] = max(magnitudes)
    assert maxima["homo"] <= PRINTED_TOLERANCE_EV
    assert maxima["lumo"] <= PRINTED_TOLERANCE_EV
    assert maxima["gap"] <= GAP_TOLERANCE_EV

    summary = read_summary()
    assert summary["max_abs_delta_eV"] == max(maxima.values()) == 0.0002
    for level, block in summary["deltas"].items():
        assert block["n"] == 47
        assert block["max_abs_eV"] == maxima[level]
        assert block["n_beyond_printed_tolerance"] == (1 if level == "gap" else 0)


def test_uuid_agreement_is_total() -> None:
    layer = layer_index()
    grouped = chain_b_index()
    agreements = 0
    for fact in read_facts():
        key = fact["inchikey"]
        chain_a_row = layer[key]
        chain_b_row = representative(grouped[key])
        assert fact["chain_a_uuid"] == chain_a_row["themol_uuid"]
        assert fact["chain_b_uuid"] == chain_b_row["uuid"]
        expected = chain_a_row["themol_uuid"] == chain_b_row["uuid"]
        assert fact["uuid_match"] == ("yes" if expected else "no")
        agreements += int(expected)

    summary = read_summary()
    assert agreements == summary["uuid"]["compared"] == 51
    assert summary["uuid"]["mismatch"] == 0
    assert summary["uuid"]["mismatch_list"] == []
    assert summary["uuid"]["match_rate"] == 1.0


def test_chain_b_shard_arithmetic_is_reported_not_hidden() -> None:
    counted: dict[str, int] = {}
    for row in repro.read_chain_b():
        counted[row["shard"]] = counted.get(row["shard"], 0) + 1

    integrity = read_summary()["chain_b_integrity"]
    assert sum(counted.values()) == integrity["rows_total"] == 145
    assert counted == integrity["rows_by_shard"]
    assert integrity["rows_by_shard"] == {
        "themol_eps142_shard0.csv": 47,
        "themol_eps142_shard1.csv": 51,
        "themol_eps142_shard2.csv": 47,
    }
    assert integrity["unique_keys"] == 51
    assert integrity["rows_minus_keys"] == 94
    assert integrity["keys_in_multiple_shards"] == 47
    assert integrity["identical_key_set_shard_pairs"] == [
        ["themol_eps142_shard0.csv", "themol_eps142_shard2.csv"]
    ]
    assert integrity["rows_total"] != integrity["unique_keys"]
    assert read_summary()["inputs"]["chain_b"]["claimed_rows_in_source_name"] == 142


def test_shard_rows_that_failed_to_open_are_kept_as_missing() -> None:
    facts = {row["inchikey"]: row for row in read_facts()}
    integrity = read_summary()["chain_b_integrity"]
    without = integrity["keys_without_any_level"]
    assert without == integrity["keys_only_in_one_shard"]
    assert len(without) == 4
    for key in without:
        row = facts[key]
        assert row["homo_b_eV"] == ""
        assert row["lumo_b_eV"] == ""
        assert row["gap_b_eV"] == ""
        assert row["delta_homo_eV"] == ""
        assert row["delta_lumo_eV"] == ""
        assert row["delta_gap_eV"] == ""
        assert row["chain_b_rc"].startswith("ERR:")
        assert row["homo_a_eV"].strip() != ""
    assert read_summary()["match"]["comparable_rows"] == 47
    assert integrity["shard_rows_without_levels"] == 13


def test_summary_pins_both_inputs_and_runs_no_queries() -> None:
    summary = read_summary()
    layer_digest = hashlib.sha256(repro.LAYER.read_bytes()).hexdigest()
    assert summary["input_chain_a_sha256"] == layer_digest
    assert summary["inputs"]["chain_a"]["sha256"] == layer_digest
    assert summary["input_chain_b_sha256"] == repro.bundle_digest(CHAIN_B_DIR)
    for entry in summary["inputs"]["chain_b"]["files"]:
        digest = hashlib.sha256((CHAIN_B_DIR / entry["name"]).read_bytes()).hexdigest()
        assert entry["sha256"] == digest
        assert entry["rows"] == summary["chain_b_integrity"]["rows_by_shard"][entry["name"]]
    assert summary["queries_executed"] == 0
    assert summary["is_a_plan_not_a_measurement"] is False


def test_reported_names_come_from_chain_a_and_agree_with_chain_b() -> None:
    layer = layer_index()
    for fact in read_facts():
        assert fact["name"] == layer[fact["inchikey"]]["name"]
    agreement = read_summary()["name_agreement"]
    assert agreement["compared"] == 51
    assert agreement["differ"] == 0
    assert agreement["differing_keys"] == []


def test_check_mode_regenerates_both_artefacts() -> None:
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "CHECK OK" in completed.stdout


def test_artefacts_and_frozen_inputs_are_lf_only() -> None:
    paths = [FACTS, SUMMARY, GENERATOR]
    paths.extend(CHAIN_B_DIR / shard for shard in repro.CHAIN_B_SHARDS)
    for path in paths:
        assert b"\r\n" not in path.read_bytes(), path.name
