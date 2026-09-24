"""Regression tests for the FEC 78.4 temperature-attribution finding (v0.3.13).

The dataset stores FEC dielectric 78.4 at 296.15 K (23 C) on the authority of the
Kobayashi 2003 primary table, whose FEC row carries footnote e "At 23 C.".
Nanbu et al. 2007 restates the same value - and the same viscosity - as 40 C
while citing that same Kobayashi paper. These tests keep the downstream 40 C
restatement from ever being mistaken for a primary measurement, and keep the
competing 107 leg pinned to the near-room temperature at which it is quoted, so
that the 78.4-vs-107 split cannot be silently re-read as a temperature pair.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT

EVIDENCE = (
    REPOSITORY_ROOT
    / "probes"
    / "g1plus_fec_temperature_attribution_evidence.json"
)
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FEC_INCHIKEY = "SBLRHMKNNHXPHG-UHFFFAOYSA-N"
NEW_STATUS = (
    "primary_78.4_landed_107_leg_read_in_ue2014_compilation_plus_40C_temp_conflict"
)

def _local_cache_path(local_copy: str) -> Path:
    return REPOSITORY_ROOT / local_copy.split(" ")[0]


def _assert_local_cache_matches(entry) -> None:
    """Re-hash the git-ignored local copy when it is present.

    The cached PDFs are deliberately not tracked, so CI has nothing to check;
    on a workstation that holds them this pins the bytes behind the recorded
    hash instead of trusting the JSON string.
    """
    path = _local_cache_path(str(entry["local_copy"]))
    if not path.exists():
        pytest.skip(f"git-ignored cache absent: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == entry["pdf_sha256"], f"{path} sha256 {digest}"
    assert path.stat().st_size == entry["pdf_bytes"], f"{path} size"


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _fec_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(
            row for row in csv.DictReader(handle) if row["inchikey"] == FEC_INCHIKEY
        )


def test_the_primary_footnote_says_23c(evidence) -> None:
    primary = evidence["primary_source"]

    assert primary["doi"] == "10.1016/S0022-1139(02)00317-2"
    assert primary["printed_page"] == 108
    assert primary["pdf_page"] == 4
    assert primary["pdf_page_index"] == 3
    assert primary["pdf_bytes"] == 184370
    assert primary["pdf_sha256"] == (
        "729ee9240fd31f166207102d865048a6207600fd1f46f849f8a67554435ce91d"
    )
    assert primary["fec_row_extract"].endswith("4.1e 78.4e 1.04e Our data")
    assert primary["footnotes_verbatim"]["e"] == "At 23 C."
    assert primary["footnotes_verbatim"]["c"] == "At 40 C."
    assert primary["temperature_of_the_stored_value"].startswith("23 C")
    assert "600 dpi" in primary["verification_method"]


def test_the_40c_version_is_a_downstream_restatement_not_a_measurement(evidence) -> None:
    conflict = evidence["declared_conflict"]

    assert conflict["doi"] == "10.5796/electrochemistry.75.607"
    assert conflict["printed_page"] == 608
    assert "(78.4 at 40 C)" in conflict["verbatim"]
    assert "(4.1 mPa s at 40 C)" in conflict["verbatim"]
    assert "Kobayashi" in conflict["its_reference_4"]
    assert conflict["is_an_independent_measurement"].startswith("no -")
    assert conflict["scope_of_the_shift"].startswith("the restatement moves both")


def test_the_competing_107_leg_is_also_near_room_temperature(evidence) -> None:
    block = evidence["competing_leg_temperature"]
    sources = block["sources"]

    assert len(sources) == 2
    for item in sources:
        assert "(about 107 at 25 C)" in item["verbatim"]
    # each 2013 communication numbers the Hagiyama item differently
    assert "Hagiyama" in sources[0]["its_reference_5"]
    assert "Chem. Lett., 37, 210" in sources[0]["its_reference_5"]
    assert "Hagiyama" in sources[1]["its_reference_4"]
    assert "Chem. Lett., 37, 210" in sources[1]["its_reference_4"]
    assert block["claim"] == "about 107 at 25 C for FEC"
    assert evidence["temperature_pairing"]["gap_K"] == 2.0
    assert evidence["temperature_pairing"]["stored_leg"].startswith("78.4 at 23 C")


def test_the_dataset_row_declares_the_conflict_and_moves_no_value(evidence) -> None:
    row = _fec_row(DATASET)
    decision = evidence["decision"]

    assert row["dielectric"] == "78.4"
    assert row["T_K"] == "296.15"
    assert row["model_ready"] == "false"
    assert row["conflict_status"] == NEW_STATUS
    assert "downstream" in row["notes"]
    assert "40 C" in row["notes"]
    assert "about 107 at 25 C" in row["notes"]
    assert "no average" in row["notes"]

    assert decision["value_verdict"].startswith("retain 78.4")
    assert decision["stored_value_unchanged"].startswith("dielectric stays 78.4")
    assert "model_ready stays false" in decision["stored_value_unchanged"]


def test_the_cached_copies_stay_out_of_the_public_tree(evidence) -> None:
    primary = evidence["primary_source"]["local_copy"]
    conflict = evidence["declared_conflict"]["local_copy"]
    competing = evidence["competing_leg_temperature"]["sources"]

    assert primary.startswith("data/restricted/")
    assert "git-ignored" in primary
    assert conflict.startswith("data/external/g1plus/")
    assert "git-ignored" in conflict
    for item in competing:
        assert item["local_copy"].startswith("data/external/g1plus/")
        assert "git-ignored" in item["local_copy"]


def test_cached_local_copies_match_their_recorded_hashes(evidence) -> None:
    _assert_local_cache_matches(evidence["primary_source"])
    _assert_local_cache_matches(evidence["declared_conflict"])
    for item in evidence["competing_leg_temperature"]["sources"]:
        _assert_local_cache_matches(item)
