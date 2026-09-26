"""Offline tests for the W17-E OMat24 feasibility audit.

These tests never touch the network and never import lmdb/rdkit: they only read the
frozen facts file and assert that the audit really did say what the report says it
said. The pins are literals on purpose -- if the facts file is silently re-baselined
the assertions fail instead of quietly agreeing with the new numbers.

The live re-run (which does need the network) is opt-in via OMAT24_AUDIT_ONLINE=1.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = REPOSITORY_ROOT / "probes/omat24_feasibility_facts.json"
AUDIT_SCRIPT = REPOSITORY_ROOT / "probes/omat24_feasibility_audit.py"
REPORT_PATH = REPOSITORY_ROOT / "reports/omat24_feasibility.md"

VERDICT_ENUM = ["adopt", "reference_only", "reject"]
TOP_LEVEL_KEYS = [
    "calculator",
    "calculator_parameters",
    "cell",
    "ctime",
    "data",
    "energy",
    "forces",
    "initial_magmoms",
    "mtime",
    "numbers",
    "pbc",
    "positions",
    "stress",
    "unique_id",
    "user",
]
ORBITAL_TOKENS = ("homo", "lumo", "gap", "eigen", "orbital", "mo_energy", "band", "fermi", "dos")


@pytest.fixture(scope="module")
def facts() -> dict:
    assert FACTS_PATH.exists(), f"facts file missing: {FACTS_PATH}"
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def test_schema_and_verdict_enum(facts):
    for key in (
        "audit_id",
        "audit_scope",
        "verdict",
        "verdict_reason",
        "verdict_enum",
        "q1_data_shape",
        "q1b_probe",
        "q2_molecules_or_crystals",
        "q3_orbital_quantities",
        "q4_structure_matching",
        "q5_license",
        "q6_verdict",
        "evidence_urls",
        "not_obtained",
    ):
        assert key in facts, f"missing top-level key {key}"
    assert facts["audit_id"] == "omat24_orbital_feasibility"
    assert facts["verdict"] in VERDICT_ENUM
    assert facts["verdict_enum"] == VERDICT_ENUM
    assert facts["q6_verdict"]["verdict"] == facts["verdict"]


def test_verdict_is_reject_with_a_reason(facts):
    assert facts["verdict"] == "reject"
    assert "inorganic" in facts["verdict_reason"]
    assert facts["q6_verdict"]["reason_one_sentence"].strip()


def test_evidence_urls_are_non_empty_and_well_formed(facts):
    urls = facts["evidence_urls"]
    assert urls, "evidence_urls must not be empty"
    for entry in urls:
        assert entry["url"].startswith("https://")
        assert entry["http_status"] != ""
        assert entry["what"]
    # the two hosts that actually had to be reachable
    blob = " ".join(entry["url"] for entry in urls)
    assert "hf-mirror.com" in blob
    assert "dl.fbaipublicfiles.com" in blob
    assert all(entry["http_status"] == 200 for entry in urls)


def test_no_orbital_quantity_exists(facts):
    orbital = facts["q3_orbital_quantities"]
    assert orbital["orbital_keys_present"] == []
    assert orbital["orbital_keys_present_count"] == 0
    assert len(orbital["orbital_key_candidates_sought"]) >= 20
    assert orbital["observed_label_fields"] == ["energy", "forces", "stress"]
    # defensive: no observed key may even look like an orbital field
    observed = facts["q1b_probe"]["top_level_key_union"] + facts["q1b_probe"]["data_key_union"]
    for name in observed:
        lowered = name.lower()
        assert not any(token in lowered for token in ORBITAL_TOKENS), name


def test_no_structure_identifier_exists(facts):
    matching = facts["q4_structure_matching"]
    assert matching["structure_keys_present"] == []
    assert matching["structure_keys_present_count"] == 0
    assert matching["records_with_inchikey_shaped_string"] == 0
    assert matching["join_index_available"] is False
    solvents = matching["solvents_probed"]
    assert len(solvents) == 5
    for row in solvents:
        assert re.fullmatch(r"[A-Z]{14}-[A-Z]{10}-[A-Z]", row["inchikey"]), row
        assert row["rdkit_formula"]
        assert matching["composition_reduced_exact_matches"][row["rdkit_formula_spaced"]] == 0


def test_dataset_is_periodic_inorganic_not_molecular(facts):
    shape = facts["q2_molecules_or_crystals"]
    assert shape["is_periodic_crystal_dataset"] is True
    assert shape["all_periodic_pbc_true"] is True
    assert shape["non_periodic_records"] == 0
    assert shape["natoms_min"] >= 10
    assert shape["distinct_elements"] >= 80
    # the electrolyte-relevant elements do occur, but inside periodic crystals
    for symbol in ("H", "C", "N", "O", "F", "S", "P", "Cl", "Br", "I", "B", "Si"):
        assert shape["element_histogram_selected"][symbol] > 0, symbol
    assert shape["organic_subset_only_examples"], "expected a few non-molecular formulas"


def test_probe_schema_is_exactly_the_pinned_key_union(facts):
    probe = facts["q1b_probe"]
    assert probe["records"] == 35579
    assert probe["top_level_key_union"] == sorted(TOP_LEVEL_KEYS)
    assert probe["non_record_entries"] == [{"key": "nextid", "value": 35580}]
    assert probe["metadata_npz_keys"] == ["natoms"]
    assert probe["archive_bytes"] == 71395159
    assert probe["members"]["data.aselmdb"]["bytes"] == 110694400
    sample = probe["sample_record"]
    for key in ("pbc", "cell", "energy", "forces", "stress", "numbers"):
        assert key in sample
    assert sample["pbc"] == [True, True, True]
    assert sample["data"]["composition_reduced"] == "Th1 Zr1 Ru1"


def test_license_is_redistributable_and_not_the_reason(facts):
    license_block = facts["q5_license"]
    assert license_block["card_license_field"] == "cc-by-4.0"
    assert license_block["readme_front_matter_license"] == "cc-by-4.0"
    assert license_block["redistribution_allowed"] is True
    assert "creativecommons.org/licenses/by/4.0" in license_block["readme_license_sentence"]
    assert "NOT the reason" in license_block["note_on_this_repo"]


def test_the_audit_records_what_it_did_not_get(facts):
    assert len(facts["not_obtained"]) >= 3
    blob = " ".join(facts["not_obtained"])
    assert "orbital" in blob


def test_deliverable_files_exist():
    assert AUDIT_SCRIPT.exists()
    assert REPORT_PATH.exists()
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "NETWORK_UNAVAILABLE" in source
    assert "return 2" in source
    assert "ProxyHandler({})" in source
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "reject" in report


@pytest.mark.skipif(
    os.environ.get("OMAT24_AUDIT_ONLINE") != "1",
    reason="live re-run hits hf-mirror.com + dl.fbaipublicfiles.com; set OMAT24_AUDIT_ONLINE=1",
)
def test_live_check_reproduces():
    proc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPOSITORY_ROOT),
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
