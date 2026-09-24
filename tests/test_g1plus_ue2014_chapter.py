"""Regression tests for the Ue et al. 2014 FEC 107-leg evidence.

v0.3.13 records that the competing 107 leg of fluoroethylene carbonate is now
read from the Ue et al. 2014 book chapter, but only at compilation level: the
chapter's own Table 2.3 carries no per-row source, and its prose attributes the
FEC permittivity data to Hagiyama et al. 2008, which remains unread. These tests
keep that distinction from collapsing into a promotion.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT

EVIDENCE = REPOSITORY_ROOT / "probes" / "g1plus_ue2014_chapter_evidence.json"
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FEC_INCHIKEY = "SBLRHMKNNHXPHG-UHFFFAOYSA-N"
NEW_STATUS = "primary_78.4_landed_107_leg_read_in_ue2014_compilation_plus_40C_temp_conflict"


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _fec_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(
            row for row in csv.DictReader(handle) if row["inchikey"] == FEC_INCHIKEY
        )


def test_the_value_is_recorded_from_the_chapter_table(evidence) -> None:
    source = evidence["source"]
    row = evidence["evidence"]

    assert source["doi"] == "10.1007/978-1-4939-0302-3_2"
    assert source["chapter_pages"] == "93-165"
    assert source["pdf_bytes"] == 2721678
    assert source["pdf_sha256"] == (
        "88931e6a9151de50a3eddb1992d755b850928ebe0bdb262319a92ca410c0eefe"
    )
    assert row["table_number"] == "Table 2.3"
    assert row["printed_page"] == 101
    assert row["value"] == 107
    assert "eps_r" in row["column_headers"]
    assert row["fec_row_extract"].startswith("4-Fluoro-1,3-dioxolan-2-one (FEC)")
    assert row["fec_row_extract"].endswith("107 4.1 -13.30 1.45")


def test_the_hagiyama_attribution_is_recorded_but_not_promoted(evidence) -> None:
    row = evidence["evidence"]
    chain = evidence["attribution_chain"]
    decision = evidence["decision"]

    assert row["per_row_footnote"].startswith("none for the FEC row")
    assert "[4, 5]" in row["table_source_attribution"]
    assert "[25]" in row["body_text_attribution"]
    assert "Hagiyama" in row["reference_25"]
    assert "Chem. Lett. 2008, 37, 210-211" in row["reference_25"]

    assert chain["status"] == "compilation_read_primary_still_unread"
    assert chain["independent_of_hagiyama_2008"].startswith("no -")
    assert chain["primary_measurement_located"].startswith("no -")
    assert decision["stored_value_unchanged"].startswith("dielectric stays 78.4")
    assert "model_ready stays false" in decision["stored_value_unchanged"]


def test_the_rejected_mopn_lead_stays_rejected(evidence) -> None:
    rejected = evidence["evidence"]["unrelated_lead_rejected"]

    assert "fluoroacetonitrile" in rejected
    assert "not 3-methoxypropionitrile" in rejected


def test_the_restricted_pdf_stays_out_of_the_public_tree(evidence) -> None:
    source = evidence["source"]

    assert source["local_cache"].startswith("data/external/g1plus/")
    assert "git-ignored" in source["local_cache"]


def test_the_dataset_row_changes_provenance_text_only(evidence) -> None:
    row = _fec_row(DATASET)

    assert row["dielectric"] == "78.4"
    assert row["T_K"] == "296.15"
    assert row["model_ready"] == "false"
    assert row["conflict_status"] == NEW_STATUS
    assert "eps_r 107" in row["notes"]
    assert "Hagiyama" in row["notes"]
    assert "remains unread" in row["notes"]
    assert "no average is taken" in row["notes"]
