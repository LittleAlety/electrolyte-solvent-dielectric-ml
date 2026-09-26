"""Offline tests for the W17-17 unit recheck probe.

Nothing here touches the network: the parser is exercised on a synthetic xTB
block, and the JSON is only inspected when a local run has produced it (the raw
directory is git-ignored, so CI skips that part).
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.themol_expand_unit_recheck import TOLERANCE_EV, parse_orbital_block

PROBE = REPOSITORY_ROOT / "probes/themol_expand_unit_recheck.py"
LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
OUTPUT = REPOSITORY_ROOT / "data/raw/themol/expand_unit_recheck.json"

SAMPLE_LOG = (
    "some banner\n"
    "    * Orbital Energies and Occupations\n"
    "\n"
    "         #    Occupation            Energy/Eh            Energy/eV\n"
    "      -------------------------------------------------------------\n"
    "         1        2.0000           -0.7228632             -19.6701\n"
    "       ...           ...                  ...                  ...\n"
    "        26        2.0000           -0.4006580             -10.9025 (HOMO)\n"
    "        27                         -0.2676358              -7.2827 (LUMO)\n"
    "        28                         -0.2000000              -5.4423\n"
    "          TOTAL ENERGY\n"
)


def test_probe_does_not_borrow_the_harvest_parser() -> None:
    source = PROBE.read_text(encoding="utf-8")
    assert "parse_orbitals(" not in source
    assert "occupation" in source
    assert "sample_share" in source
    assert "coverage_note" in source


def test_parser_reads_the_occupation_boundary_not_the_labels() -> None:
    parsed = parse_orbital_block(SAMPLE_LOG)
    assert parsed["mode"] == "occupation"
    # 2 occupied rows plus 3 virtual ones; xTB leaves the occupation cell of a
    # virtual orbital empty, which is why the pattern must accept 3 columns.
    assert parsed["n_levels"] == 4
    assert abs(parsed["homo_eV"] - (-10.9025)) < 1e-6
    assert abs(parsed["lumo_eV"] - (-7.2827)) < 1e-6
    assert abs(parsed["max_abs_hartree_residual_eV"]) < 1e-4
    assert parsed["label_agreement"] == {"HOMO": True, "LUMO": True}


def test_parser_refuses_a_log_without_the_orbital_section() -> None:
    parsed = parse_orbital_block("nothing to see here")
    assert parsed["mode"] == "no_section"
    assert parsed["homo_eV"] is None


@pytest.mark.skipif(not OUTPUT.exists(), reason="the recheck JSON is git-ignored and absent")
def test_local_recheck_json_is_consistent_with_the_layer() -> None:
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    digest = hashlib.sha256(LAYER.read_bytes()).hexdigest()
    assert payload["layer_sha256"] == digest, "the JSON describes a different layer build"
    with LAYER.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert payload["n_sampled"] <= len(rows)
    assert payload["n_sampled"] == len(payload["results"])
    assert payload["tolerance_eV"] == TOLERANCE_EV
    assert payload["all_passed"] is True
    assert all(row["passed"] for row in payload["results"])
    keys = {row["inchikey"] for row in rows}
    assert {row["inchikey"] for row in payload["results"]} <= keys
