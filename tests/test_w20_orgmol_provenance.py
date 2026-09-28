"""Literal pins for the Week 20 W20-6a Org-Mol provenance probe.

The source-identity facts, the licence reading, the three-gate result, the
row-level "source not obtainable" statement and the frozen rows artifact are
pinned here so a silent edit to the verdict, to a gate flag or to the summary
turns this file red.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_orgmol_provenance as provenance

PREREG = REPOSITORY_ROOT / "probes" / "w20_orgmol_provenance_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_orgmol_provenance_summary.json"
ROWS = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_orgmol_provenance_rows.csv"

ROWS_COLUMNS = ("gate", "verdict", "cleared", "reason")
NOT_OBTAINABLE = "source_not_obtainable"


def _fresh_gate_rows() -> list[dict[str, str]]:
    """Rebuild the rows artifact from the module, not from the on-disk copy."""

    rows: list[dict[str, str]] = []
    for gate, block in provenance.THREE_GATE_RESULT.items():
        rows.append(
            {
                "gate": gate,
                "verdict": str(block["verdict"]),
                "cleared": "true" if block["cleared"] else "false",
                "reason": str(block["reason"]),
            }
        )
    return rows


def test_source_identity_is_literal() -> None:
    identity = provenance.SOURCE_IDENTITY
    assert identity["name"] == "Org-Mol"
    assert identity["journal"] == "npj Computational Materials 11, 224 (2025)"
    assert identity["doi"] == "10.1038/s41524-025-01720-4"
    assert identity["arxiv"] == "2501.09896"
    assert "Uni-Mol" in identity["upstream_framework"]
    assert "not a newly measured collection" in identity["composition_warning"]


def test_licence_reading_is_restricted_and_do_not_listed() -> None:
    reading = provenance.LICENCE_READING
    assert reading["verdict"] == "restricted"
    assert reading["compilation_released"] is False
    assert reading["article_licence"] == "CC BY-NC-ND 4.0"
    assert "upon reasonable request" in reading["data_availability_quote"]
    refs = {entry["ref"]: entry for entry in reading["epsilon_provenance_refs"]}
    assert refs["53"]["citation"].startswith("Haynes, W. CRC Handbook")
    assert "Springer Materials" in refs["54"]["citation"]
    for entry in reading["epsilon_provenance_refs"]:
        assert entry["access_class"] == "restricted"
        assert entry["on_week20_do_not_list"] is True


def test_three_gates_all_fail_in_order() -> None:
    gates = provenance.THREE_GATE_RESULT
    assert list(gates) == ["gate_1_licence", "gate_2_locator", "gate_3_first_hand"]
    assert gates["gate_1_licence"]["verdict"] == "restricted"
    assert gates["gate_2_locator"]["verdict"] == "unreachable"
    assert gates["gate_3_first_hand"]["verdict"] == "unreachable"
    for block in gates.values():
        assert block["cleared"] is False


def test_source_level_class_is_inadmissible_and_verdict_constants_hold() -> None:
    assert provenance.SOURCE_LEVEL_ACCESS_CLASS == "inadmissible"
    assert provenance.ACCESS_CLASSES == ("admissible", "needs_lead", "inadmissible")
    assert provenance.ACCEPTED_WINDOW_K == (283.15, 303.15)
    assert provenance.LICENCE_VERDICT is None
    assert "licence_not_cleared" in provenance.FATAL_REASONS
    assert provenance.REQUIRED_COLUMNS == ("inchikey", "smiles", "epsilon", "temperature_C")
    assert provenance.LOCATOR_COLUMNS == ("doi", "locator")


def test_summary_records_the_source_screen_without_readings() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "source_screened_not_obtainable"
    assert summary["ceiling_break"] is False
    assert summary["produces_reading"] is False
    assert summary["promotes_no_reading"] is True
    assert summary["shot_number_taken"] is None
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["main_scoreboard_untouched"] is True
    assert summary["source_level_access_class"] == "inadmissible"
    assert summary["three_gate_result"] == provenance.THREE_GATE_RESULT
    row_level = summary["row_level_classification"]
    assert row_level["status"] == NOT_OBTAINABLE
    assert row_level["admissible"] == 0
    assert row_level["needs_lead"] == 0
    assert row_level["inadmissible"] == 0


def test_prereg_is_locked_before_run_and_carries_no_readings() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["produces_reading"] is False
    assert prereg["shot_number_taken"] is None
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["main_scoreboard_untouched"] is True
    assert prereg["roster"] == "data/dielectric_v03.csv"
    assert prereg["licence_verdict"] is None


def test_rows_artifact_matches_the_frozen_gate_table() -> None:
    assert ROWS.is_file()
    with ROWS.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == ROWS_COLUMNS
        on_disk = [dict(row) for row in reader]
    assert on_disk == _fresh_gate_rows()
    assert len(on_disk) == 3
    assert all(row["cleared"] == "false" for row in on_disk)


def test_run_refuses_while_unarmed() -> None:
    blockers = provenance.blocking_conditions()
    assert blockers
    with pytest.raises(SystemExit):
        provenance.run()

