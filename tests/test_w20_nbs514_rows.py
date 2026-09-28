"""Literal pins for the Week 20 W20-6b NBS-514 same-source temperature rows.

The candidate rule, the gate outcomes, the row counts and the discipline
fields are pinned here so a silent edit to the rule, to a gate flag or to the
frozen summary turns this file red.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_nbs514_rows as nbs

PREREG = REPOSITORY_ROOT / "probes" / "w20_nbs514_rows_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_nbs514_rows_summary.json"
ROWS = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_nbs514_rows.csv"

COUNTS = {
    "transcript_rows": 636,
    "roster_matched_rows_all": 121,
    "candidate_rows": 28,
    "non_static_frequency_rows_dropped": 2,
    "usable_rows": 26,
    "usable_rows_in_accepted_window": 26,
    "distinct_compound_temperature_pairs": 25,
    "distinct_full_inchikey_temperature_pairs": 26,
}

DROPPED_SOURCE_IDS = ("nbs514:p20:008", "nbs514:p23:010")


def test_prereg_is_locked_before_run_and_pins_the_rule() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["produces_reading"] is False
    assert prereg["promoted"] is False
    assert prereg["promotes_no_reading"] is True
    assert prereg["shot_number_taken"] is None
    assert prereg["scoreboard_attempts_delta"] == 0
    assert prereg["reaxys_values_used"] == 0
    assert prereg["models_fitted"] == 0
    assert prereg["main_scoreboard_untouched"] is True
    assert prereg["licence_verdict"] == "open"
    assert prereg["roster"] == "data/dielectric_v03.csv"
    assert prereg["source_doi"] == "10.6028/nbs.circ.514"
    assert prereg["first_hand_roster_qualities"] == list(nbs.FIRST_HAND_ROSTER_QUALITIES)
    assert prereg["expected_counts_from_handoff"]["candidate_rows"] == 28
    assert prereg["expected_counts_from_handoff"]["usable_rows"] == 26


def test_licence_is_public_domain_and_the_three_gates_clear() -> None:
    assert nbs.LICENCE_VERDICT == "open"
    assert nbs.LICENCE_KIND == "public_domain"
    gates = nbs.three_gate_result()
    assert list(gates) == ["gate_1_licence", "gate_2_locator", "gate_3_first_hand"]
    for block in gates.values():
        assert block["cleared"] is True
    assert nbs.FIRST_HAND_ROSTER_QUALITIES == (
        "four_figures",
        "primary_experimental_public_pdf",
        "public_domain_critical_compilation",
    )
    assert nbs.ACCEPTED_WINDOW_K == (283.15, 303.15)


def test_summary_records_the_counts_and_promotes_nothing() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["verdict"] == "same_source_rows_admissible_not_promoted"
    assert summary["status"] == "executed"
    assert summary["ceiling_break"] is False
    assert summary["produces_reading"] is False
    assert summary["promoted"] is False
    assert summary["shot_number_taken"] is None
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["reaxys_values_used"] == 0
    assert summary["models_fitted"] == 0
    assert summary["main_scoreboard_untouched"] is True
    assert summary["counts"] == COUNTS
    assert summary["roster_sha256"] == nbs.sha256_file(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")


def test_admissibility_clears_all_three_gates() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    admissibility = summary["admissibility"]
    assert admissibility["licence_cleared"] is True
    assert admissibility["locator_cleared"] is True
    assert admissibility["first_hand_cleared"] is True
    assert admissibility["admissible"] is True
    assert summary["licence_verdict"] == "open"


def test_only_frequency_noted_rows_are_dropped() -> None:
    payload = nbs.build()
    rows = payload["row_artifact_rows"]
    dropped = [row for row in rows if row["usable"] == "false"]
    assert [row["source_id"] for row in dropped] == list(DROPPED_SOURCE_IDS)
    for row in dropped:
        assert "cycles/sec" in row["frequency_note"]
    for row in rows:
        assert row["usable"] == ("true" if nbs.is_static(row) else "false")


def test_rows_artifact_matches_a_fresh_build() -> None:
    assert ROWS.is_file()
    with ROWS.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == nbs.ROWS_COLUMNS
        on_disk = [dict(row) for row in reader]
    fresh = nbs.build()["row_artifact_rows"]
    assert on_disk == fresh
    assert len(on_disk) == 28
    assert sum(1 for row in on_disk if row["usable"] == "true") == 26
    for row in on_disk:
        assert row["licence_verdict"] == "open"
        assert row["first_hand_verdict"] == "first_hand_checked"
        assert row["locator"].startswith(row["source_id"] + " | 10.6028/nbs.circ.514 | ")


def test_candidate_rows_never_leave_the_roster() -> None:
    payload = nbs.build()
    roster = {
        row["inchikey"]
        for row in nbs.read_csv_rows(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")
        if row["inchikey"]
    }
    for row in payload["row_artifact_rows"]:
        assert row["inchikey"] in roster
        assert row["roster_source_quality"] in nbs.FIRST_HAND_ROSTER_QUALITIES

