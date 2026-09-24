"""Regression tests for the G1+ crawl round 2 adjudications."""

from __future__ import annotations

import json

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT
from probes.nbs514_frequency_gate_audit import read_csv_rows

EVIDENCE = REPOSITORY_ROOT / "probes" / "g1plus_crawl_round2_evidence.json"
V03 = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
NBS_PART1 = REPOSITORY_ROOT / "data" / "interim" / "nbs514_organic_part1.csv"
QUEUE = REPOSITORY_ROOT / "data" / "processed" / "modern_battery_solvent_candidate_queue.csv"
THERMOML_XML = REPOSITORY_ROOT / "data" / "raw" / "thermoml" / "10.1021__je7000446-d4038df0df10.xml"


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_round_recorded_no_new_static_values(evidence: dict[str, object]) -> None:
    assert evidence["outcome"]["new_ingestable_static_values"] == 0
    assert evidence["outcome"]["claims_rejected_after_local_adjudication"] == 3
    assert evidence["dataset_impact"]["rows_before"] == evidence["dataset_impact"]["rows_after"]


def test_every_agent_claim_has_a_verdict(evidence: dict[str, object]) -> None:
    findings = evidence["findings"]
    assert len(findings) == 8
    verdicts = {finding["verdict"] for finding in findings}
    assert "rejected_frequency_gated" in verdicts
    assert "rejected_identity_and_pressure" in verdicts
    assert "blocked_on_publisher_access" in verdicts


def test_isobutyronitrile_request_has_a_frequency_note() -> None:
    rows = {row["source_id"]: row for row in read_csv_rows(NBS_PART1)}
    request = rows["nbs514:p20:009"]
    assert request["compound_name"] == "Isobutyronitrile"
    assert request["dielectric"] == "20.4"
    assert request["frequency_note"] == "f=3.6x10^8 cycles/sec"


def test_the_gated_candidate_is_still_absent_from_the_dataset() -> None:
    dataset_ids = {
        row["source_record_id"]
        for row in read_csv_rows(V03)
        if row["source_record_id"]
    }
    assert "nbs514:p20:009" not in dataset_ids
    assert "nbs514:p20:008" not in dataset_ids


def test_propanenitrile_corroboration_matches_the_stored_row() -> None:
    row = next(
        row
        for row in read_csv_rows(V03)
        if row["inchikey"] == "FVSKHRXBFJPNKK-UHFFFAOYSA-N"
    )
    assert row["source_record_id"] == "nbs514:p17:014"
    assert row["T_K"] == "293.15"
    assert row["dielectric"] == "27.2"
    assert "zero_frequency" in row["gate_flags"]


def test_methyl_trifluoromethyl_ether_still_has_no_open_primary_reference() -> None:
    queue = {row["name"]: row for row in read_csv_rows(QUEUE)}
    candidate = queue["methyl trifluoromethyl ether"]
    assert candidate["primary_reference"] == ""
    assert candidate["decision_status"] == "primary_source_and_rights_review_required"


def test_je7000446_extraction_binds_9_28_to_compound_1_at_1600_kpa() -> None:
    """The tracked extraction, not the git-ignored XML, must carry the binding."""

    raw = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"
    rows = [
        row
        for row in read_csv_rows(raw)
        if "je7000446" in (row["doi"] or "")
        and row["temperature_k"] == "302.8"
    ]
    assert rows, "the tracked extraction has no 302.8 K rows for this DOI"
    hit = next(row for row in rows if row["value"] == "9.28")
    assert hit["pressure_kpa"] == "1600"
    assert hit["frequency_mhz"] == "0.06"
    assert hit["primary_name"] == "1,1,1-trifluoroethane"
    assert hit["primary_inchi_key"] == "UJPMYEOUBPIPHQ-UHFFFAOYSA-N"
    # No ambient-pressure observation exists anywhere in the record.
    pressures = [int(row["pressure_kpa"]) for row in rows]
    assert min(pressures) == 1600
    assert len(rows) == 14
    assert max(pressures) == 30700


def test_machine_readable_evidence_does_not_reintroduce_the_zero_frequency_contract(
    evidence: dict[str, object],
) -> None:
    """Keep the adjudicated NBS-specific rule consistent with the reports."""

    payload = json.dumps(evidence, ensure_ascii=False)
    assert "static dataset admits zero-frequency permittivities only" not in payload
    assert "zero-frequency convention" not in payload
    assert "not a project-wide zero-frequency-only contract" in payload


@pytest.mark.skipif(
    not THERMOML_XML.exists(),
    reason="the raw ThermoML cache is git-ignored and absent in this checkout",
)
def test_deposited_compound_disagrees_with_the_citation_title(
    evidence: dict[str, object],
) -> None:
    import hashlib

    raw = THERMOML_XML.read_bytes()
    pinned = next(
        finding["local_evidence"]["raw_sha256"]
        for finding in evidence["findings"]
        if finding["finding_id"] == "crawl2_methyl_trifluoromethyl_ether_identity_conflict"
    )
    assert hashlib.sha256(raw).hexdigest() == pinned
    xml = raw.decode("utf-8", errors="replace")
    assert "trifluoromethyl methyl ether" in xml
    assert "UJPMYEOUBPIPHQ-UHFFFAOYSA-N" in xml
    assert "<sFormulaMolec>C2H3F3</sFormulaMolec>" in xml
    assert "<sFormulaMolec>C3H3F5O</sFormulaMolec>" in xml
    assert "R-143a" in xml
