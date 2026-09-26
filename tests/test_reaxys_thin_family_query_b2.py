"""Offline tests for the W17-15 Reaxys thin-family second batch.

The pinned digest is written out literally so a silent edit to the facts table
or its generator shows up as a failure instead of quietly re-baselining.

Nothing here touches the network or a browser.  The raw Reaxys evidence under
``data/raw/reaxys_w17c/`` is git-ignored, so the tests that need it are skipped
in CI, which is the normal state.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

FACTS = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_b2_facts.csv"
SUMMARY = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_b2_summary.json"
GENERATOR = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_b2.py"
QUEUE = REPOSITORY_ROOT / "probes/reaxys_thin_family_backfill_queue.csv"
BATCH_ONE_FACTS = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_facts.csv"
RAW_OBSERVATIONS = REPOSITORY_ROOT / "data/raw/reaxys_w17c/observations.csv"

RAW_PRESENT = RAW_OBSERVATIONS.exists()

FACTS_SHA256 = "8c87bd6cc3941ce7951f93f82ac92dfc8fc72bfd5b2c285cbd4edd00d28484a5"
QUEUE_SHA256 = "350b40f3b81de4d40b96f79557056711a69cebf593e99b2c4fa92516e3e5a426"

EXPECTED_COLUMNS = [
    "substance", "inchikey", "in_backfill_queue", "reaxys_rn", "cas",
    "eps_rows", "eps_valued", "eps_point",
    "eta_rows", "eta_valued", "eta_point",
    "hp_rows", "hp_valued", "hp_point",
    "redox_rows", "redox_valued", "redox_point",
    "redox_point_from_comment", "hp_point_property",
]

SUBSTANCES = 4
QUERIES_EXECUTED = 4
QUERY_BUDGET = 30
EPSILON_ROWS, EPSILON_VALUED, EPSILON_POINT = 19, 17, 16
ETA_ROWS, ETA_VALUED, ETA_POINT = 22, 21, 21
ETA_POINTS_FROM_COMMENT = 11
ORBITAL_ROWS = 12
ORBITAL_POINTS = 0
REDOX_ROWS = 1
REDOX_POINTS = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_facts() -> list[dict[str, str]]:
    with FACTS.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_facts_digest_and_schema() -> None:
    assert sha256_file(FACTS) == FACTS_SHA256
    assert sha256_file(QUEUE) == QUEUE_SHA256
    rows = load_facts()
    assert list(rows[0].keys()) == EXPECTED_COLUMNS
    assert len(rows) == SUBSTANCES
    assert len({row["inchikey"] for row in rows}) == SUBSTANCES


def test_summary_pins_the_same_digest_it_reports() -> None:
    summary = load_summary()
    assert summary["arm"] == "W17-15"
    assert summary["week"] == "week17"
    assert summary["facts_path"] == "probes/reaxys_thin_family_query_b2_facts.csv"
    assert summary["facts_sha256"] == FACTS_SHA256
    assert summary["schema_version"] == "reaxys_thin_family_query/v1"
    assert summary["substances_queried"] == SUBSTANCES


def test_every_key_comes_verbatim_from_the_queue() -> None:
    """The generator's hard assertion, re-checked without importing the generator."""

    with QUEUE.open(newline="", encoding="utf-8") as handle:
        queue_keys = {row["candidate_inchikey"] for row in csv.DictReader(handle)}
    queue_keys.discard("")
    for row in load_facts():
        assert row["inchikey"] in queue_keys, row["inchikey"]
        assert row["in_backfill_queue"] == "true"


def test_the_batch_does_not_repeat_the_first_batch() -> None:
    with BATCH_ONE_FACTS.open(newline="", encoding="utf-8") as handle:
        first = {row["inchikey"] for row in csv.DictReader(handle)}
    second = {row["inchikey"] for row in load_facts()}
    assert first and second
    assert not (first & second)


def test_the_requested_range_could_not_be_keyed() -> None:
    """The headline of this arm is a scope narrowing, and it must stay recorded."""

    scope = load_summary()["scope"]
    assert scope["requested_rows_total"] == 15
    assert scope["requested_rows_carry_a_key"] == 0
    assert scope["requested"] == (
        "queue rows 11-25 of probes/reaxys_thin_family_backfill_queue.csv"
    )
    assert scope["queue_rows_with_a_key"] == 14
    assert scope["queue_rows_walked_by_w17_13"] == 10
    assert scope["queue_rows_with_a_key_left"] == 4
    assert scope["executed_queue_rows"] == [59, 60, 62, 67]

    with QUEUE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows[10:25]:
        assert row["candidate_inchikey"] == "", row["candidate_name"]
    keyed = [index for index, row in enumerate(rows) if row["candidate_inchikey"]]
    assert [index + 1 for index in keyed] == sorted([index + 1 for index in keyed])
    assert len(keyed) == 14


def test_channel_tally_matches_the_facts_table() -> None:
    tally = load_summary()["channel_tally"]
    assert (tally["epsilon"]["rows"], tally["epsilon"]["valued_rows"],
            tally["epsilon"]["point_values"]) == (EPSILON_ROWS, EPSILON_VALUED, EPSILON_POINT)
    assert (tally["eta"]["rows"], tally["eta"]["valued_rows"],
            tally["eta"]["point_values"]) == (ETA_ROWS, ETA_VALUED, ETA_POINT)
    assert tally["eta"]["point_values_from_the_comment_column"] == ETA_POINTS_FROM_COMMENT
    assert tally["homo_lumo"]["rows"] == ORBITAL_ROWS
    assert tally["homo_lumo"]["point_values"] == ORBITAL_POINTS
    assert tally["homo_lumo"]["reference_only_rows"] == ORBITAL_ROWS
    assert tally["redox"]["rows"] == REDOX_ROWS
    assert tally["redox"]["point_values"] == REDOX_POINTS
    assert tally["redox"]["valued_rows"] == 0

    rows = load_facts()
    assert sum(int(row["eps_rows"]) for row in rows) == EPSILON_ROWS
    assert sum(int(row["eps_point"]) for row in rows) == EPSILON_POINT
    assert sum(int(row["eta_rows"]) for row in rows) == ETA_ROWS
    assert sum(int(row["eta_point"]) for row in rows) == ETA_POINT
    assert sum(int(row["hp_rows"]) for row in rows) == ORBITAL_ROWS
    assert sum(int(row["hp_point"]) for row in rows) == ORBITAL_POINTS
    assert sum(int(row["redox_rows"]) for row in rows) == REDOX_ROWS


def test_valued_and_point_are_never_conflated() -> None:
    semantics = load_summary()["value_semantics"]
    assert "valued" in semantics and "point" in semantics
    for row in load_facts():
        assert int(row["eps_point"]) <= int(row["eps_valued"]) <= int(row["eps_rows"])
        assert int(row["eta_point"]) <= int(row["eta_valued"]) <= int(row["eta_rows"])
        assert int(row["hp_point"]) <= int(row["hp_valued"]) <= int(row["hp_rows"])
        assert int(row["redox_point"]) <= int(row["redox_valued"]) <= int(row["redox_rows"])


def test_the_orbital_channel_still_has_no_homo_or_lumo() -> None:
    tally = load_summary()["channel_tally"]["homo_lumo"]
    assert "Ionization Potential" in tally["definition"]
    assert "neither is a HOMO" in tally["definition"]
    correction = load_summary()["correction_to_the_w17_rx_claim"]
    assert correction["verdict"] == "unchanged by this batch"
    assert "no HOMO, LUMO or gap column" in correction["what_still_holds"]
    assert "bottleneck is not relieved" in correction["why_it_matters"]


def test_the_comment_column_finding_is_recorded_as_a_conflict() -> None:
    """Batch 1 hit comment values only in redox; batch 2 hits them in eta."""

    findings = " ".join(load_summary()["findings"])
    limitations = " ".join(load_summary()["limitations"])
    assert "Comment column rather than the value column" in findings
    assert "will see 10 of 21 eta values" in limitations


def test_session_and_query_budget_are_honest() -> None:
    session = load_summary()["session"]
    assert session["queries_executed"] == QUERIES_EXECUTED
    assert session["query_budget"] == QUERY_BUDGET
    assert session["queries_executed"] < session["query_budget"]
    assert "no headless scraping" in session["channel"]


def test_non_interference_block() -> None:
    block = load_summary()["non_interference"]
    assert block["models_fitted"] == 0
    assert block["r2_reported"] is False
    assert block["main_scoreboard_touched"] is False
    assert block["data_tracked_files_modified"] == []


def test_generator_declares_the_check_mode() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    assert "--check" in source
    assert "candidate_inchikey" in source


@pytest.mark.skipif(not RAW_PRESENT, reason="raw Reaxys evidence is not present")
def test_raw_observations_digest_matches_the_summary() -> None:
    evidence = load_summary()["evidence"]
    assert sha256_file(RAW_OBSERVATIONS) == evidence["observations_csv"]["sha256"]
    with RAW_OBSERVATIONS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == evidence["observations_csv"]["rows"]
    facts_keys = {row["inchikey"] for row in load_facts()}
    assert {row["inchikey"] for row in rows} <= facts_keys