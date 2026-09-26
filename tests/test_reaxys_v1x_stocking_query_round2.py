"""Offline tests for the W17-20 Reaxys v1.x stocking-queue P3 second walk (round two).

The pinned digest is written out literally so a silent edit to the facts table or its
generator shows up as a failure instead of quietly re-baselining.

Nothing here touches the network or a browser.  The raw Reaxys evidence under
data/raw/reaxys_w17e/ is git-ignored, so the tests that re-derive the counts from it are
skipped in CI, which is the normal state.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

FACTS = REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_query_round2_facts.csv"
SUMMARY = REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_query_round2_summary.json"
GENERATOR = REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_query_round2.py"
QUEUE = REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_queue.csv"
LANE_W17_13_FACTS = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_facts.csv"
LANE_W17_15_FACTS = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_b2_facts.csv"
LANE_W17_16_FACTS = REPOSITORY_ROOT / "probes/reaxys_v1x_stocking_query_facts.csv"
RAW_DIR = REPOSITORY_ROOT / "data/raw/reaxys_w17e"

RAW_PRESENT = RAW_DIR.is_dir() and any(RAW_DIR.glob("harvest_*.json"))

FACTS_SHA256 = "a070262124c582e8097999e8d615d859da4dfc920ba2fe0b514f491bcb06bf7b"
QUEUE_SHA256 = "a4ecdab027187475b4d32aefc87dbce9e3821b656562013e6ec7e796c34e33d3"

EXPECTED_COLUMNS = [
    "inchikey", "name", "family_tag", "queue_rank", "stocking_priority",
    "card_inchikey", "reaxys_rn", "cas", "substances_in_result_list",
    "query_succeeded", "access",
    "eps_rows", "eps_valued", "eps_point", "eps_point_from_comment",
    "eta_rows", "eta_valued", "eta_point", "eta_point_from_comment",
    "hp_rows", "hp_valued", "hp_point", "hp_point_from_comment",
    "redox_rows", "redox_valued", "redox_point", "redox_point_from_comment",
    "categories_captured", "rows_captured", "carries_reaxys_values",
]

SUBSTANCES = 7
QUERIES_EXECUTED = 9
SUBSTANCE_WALKS = 7
QUERY_BUDGET = 30
PRIOR_ROUND_QUERIES = 21
CUMULATIVE_QUERIES = 30
P3_ROWS = 143

EPSILON = {"rows": 224, "valued": 176, "point": 140, "from_comment": 4}
ETA = {"rows": 177, "valued": 173, "point": 130, "from_comment": 3}
ORBITAL = {"rows": 85, "valued": 77, "point": 77, "from_comment": 0}
REDOX = {"rows": 121, "valued": 0, "point": 0, "from_comment": 71}
REDOX_COMMENT = {"numbered": 71, "volt": 58, "no_volt": 13}

CATEGORY_CHANNEL = {
    "Dielectric Constant": "eps",
    "Static Dielectric Constant": "eps",
    "Dynamic Viscosity": "eta",
    "Kinematic Viscosity": "eta",
    "Ionization Potential": "hp",
    "Quantum Chemical Calculations": "hp",
    "Electrochemical Characteristics": "redox",
}
NUMERIC_VALUE_COLUMN = {
    "Dielectric Constant": "Dielectric Constant",
    "Static Dielectric Constant": "Static Dielectric Constant",
    "Dynamic Viscosity": "Dynamic Viscosity, P",
    "Kinematic Viscosity": "Kinematic Viscosity, St",
    "Ionization Potential": "Ionization Potential, eV",
}
POINT = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
NUMBER_IN_TEXT = re.compile(r"[-+]?\d+(?:\.\d+)?")


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


def load_queue() -> list[dict[str, str]]:
    with QUEUE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def walked_before() -> set[str]:
    keys: set[str] = set()
    for path in (LANE_W17_13_FACTS, LANE_W17_15_FACTS, LANE_W17_16_FACTS):
        with path.open(newline="", encoding="utf-8") as handle:
            keys |= {row["inchikey"] for row in csv.DictReader(handle) if row.get("inchikey")}
    return keys


def test_facts_digest_and_schema() -> None:
    assert sha256_file(FACTS) == FACTS_SHA256
    assert sha256_file(QUEUE) == QUEUE_SHA256
    rows = load_facts()
    assert list(rows[0].keys()) == EXPECTED_COLUMNS
    assert len(rows) == SUBSTANCES
    assert len({row["inchikey"] for row in rows}) == SUBSTANCES


def test_summary_pins_the_same_digest_it_reports() -> None:
    summary = load_summary()
    assert summary["arm"] == "W17-20"
    assert summary["week"] == "week17"
    assert summary["facts_path"] == "probes/reaxys_v1x_stocking_query_round2_facts.csv"
    assert summary["facts_sha256"] == FACTS_SHA256
    assert summary["schema_version"] == "reaxys_v1x_stocking_query_round2/v1"
    assert summary["substances_queried"] == SUBSTANCES


def test_every_key_comes_verbatim_from_the_queue() -> None:
    queue_keys = {row["inchikey"] for row in load_queue() if row.get("inchikey")}
    facts = load_facts()
    assert {row["inchikey"] for row in facts} <= queue_keys
    for row in facts:
        assert row["inchikey"] == row["card_inchikey"]
        assert row["stocking_priority"] == "P3"
    summary = load_summary()
    assert summary["queue_key_audit"]["keys_not_from_the_queue"] == 0
    assert summary["queue_key_audit"]["card_key_matches_queue_key"] is True
    assert summary["queue_key_audit"]["queue_sha256"] == QUEUE_SHA256


def test_no_walked_key_was_read_by_an_earlier_lane() -> None:
    facts = load_facts()
    prior = walked_before()
    assert {row["inchikey"] for row in facts}.isdisjoint(prior)
    scope = load_summary()["scope"]
    assert scope["layer"] == "P3"
    assert scope["p3_rows_in_queue"] == P3_ROWS
    assert sorted(row["inchikey"] for row in facts) == scope["walked_this_round"]


def test_channel_counts_match_the_pinned_totals() -> None:
    rows = load_facts()
    tally = load_summary()["channel_tally"]

    def sums(name: str) -> dict[str, int]:
        return {
            "rows": sum(int(row[name + "_rows"]) for row in rows),
            "valued": sum(int(row[name + "_valued"]) for row in rows),
            "point": sum(int(row[name + "_point"]) for row in rows),
            "from_comment": sum(int(row[name + "_point_from_comment"]) for row in rows),
        }

    assert sums("eps") == EPSILON
    assert sums("eta") == ETA
    assert sums("hp") == ORBITAL
    assert sums("redox") == REDOX
    for key, expected in (("eps", EPSILON), ("eta", ETA), ("hp", ORBITAL), ("redox", REDOX)):
        assert tally[key]["rows"] == expected["rows"]
        assert tally[key]["valued_rows"] == expected["valued"]
        assert tally[key]["point_values"] == expected["point"]
        assert tally[key]["point_values_from_the_comment_column"] == expected["from_comment"]
    assert tally["redox"]["substances_with_rows"] == SUBSTANCES
    assert tally["redox"]["substances_with_point_values"] == 0


def test_the_redox_channel_still_has_no_numeric_column() -> None:
    rows = load_facts()
    assert sum(int(row["redox_valued"]) for row in rows) == 0
    assert sum(int(row["redox_point"]) for row in rows) == 0
    values = load_summary()["value_columns"]
    assert "no numeric column" in values["Electrochemical Characteristics"]
    assert "no numeric column" in values["Quantum Chemical Calculations"]
    assert values["Dynamic Viscosity"] == "Dynamic Viscosity, P"
    assert values["Kinematic Viscosity"] == "Kinematic Viscosity, St"
    assert "Comment" in load_summary()["comment_column"]


def test_the_redox_comment_audit_is_honest() -> None:
    audit = load_summary()["redox_comment_audit"]
    assert audit["redox_rows_with_a_number_in_the_comment_cell"] == REDOX_COMMENT["numbered"]
    assert audit["redox_comment_rows_stating_a_volt_value"] == REDOX_COMMENT["volt"]
    assert audit["redox_comment_rows_with_a_number_but_no_volt_value"] == REDOX_COMMENT["no_volt"]
    assert REDOX_COMMENT["volt"] + REDOX_COMMENT["no_volt"] == REDOX_COMMENT["numbered"]
    assert audit["redox_rows_with_a_number_in_the_comment_cell"] == REDOX["from_comment"]
    assert "concentration" in audit["note"]


def test_the_orbital_channel_still_has_no_homo_or_lumo() -> None:
    tally = load_summary()["channel_tally"]["hp"]
    assert "Ionization Potential" in tally["definition"]
    assert "neither is a HOMO" in tally["definition"]
    assert tally["substances_with_rows"] == SUBSTANCES
    assert tally["point_values"] == tally["valued_rows"]


def test_session_and_query_budget_are_honest() -> None:
    session = load_summary()["session"]
    assert session["queries_executed"] == QUERIES_EXECUTED
    assert session["substance_walks"] == SUBSTANCE_WALKS
    assert session["query_budget"] == QUERY_BUDGET
    assert session["prior_round_queries"] == PRIOR_ROUND_QUERIES
    assert session["cumulative_queries"] == CUMULATIVE_QUERIES
    assert session["cumulative_queries"] <= session["query_budget"]
    assert session["queries_executed"] == SUBSTANCE_WALKS + session["extra_submissions"]
    assert "no headless scraping" in session["channel"]
    assert "Load More" in session["interaction"]
    assert "Show all" in session["interaction"]
    assert "chlorobenzene" in session["extra_submissions_note"]
    assert "no card was read twice" in session["extra_submissions_note"]


def test_non_interference_and_restricted_contract() -> None:
    block = load_summary()["non_interference"]
    assert block["models_fitted"] == 0
    assert block["r2_reported"] is False
    assert block["main_scoreboard_touched"] is False
    assert block["data_tracked_files_modified"] == []
    contract = load_summary()["restricted_contract"]
    assert contract["raw_evidence_dir"] == "data/raw/reaxys_w17e (git-ignored)"
    assert contract["values_enter_data"] is False
    assert contract["values_enter_any_pool"] is False
    assert contract["values_enter_any_feature_table"] is False
    assert contract["values_ship_in_this_bundle"] is False
    for row in load_facts():
        assert row["carries_reaxys_values"] == "false"


def test_generator_declares_the_check_mode() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    assert "--check" in source
    assert "inchikey" in source


@pytest.mark.skipif(not RAW_PRESENT, reason="raw Reaxys evidence is not present")
def test_counts_re_derived_from_the_raw_harvest() -> None:
    """Recompute every per-channel count straight from the saved cards."""

    facts = {row["inchikey"]: row for row in load_facts()}
    assert len(list(RAW_DIR.glob("harvest_*.json"))) == SUBSTANCES
    seen = set()
    for path in sorted(RAW_DIR.glob("harvest_*.json")):
        harvest = json.loads(path.read_text(encoding="utf-8"))
        key = harvest["inchikey_searched"]
        assert key in facts, key
        seen.add(key)
        assert harvest["identification"]["InChIKey"] == key
        counts = {
            name: {"rows": 0, "valued": 0, "point": 0, "from_comment": 0}
            for name in ("eps", "eta", "hp", "redox")
        }
        for table in harvest["tables"]:
            channel = CATEGORY_CHANNEL.get(table["category"])
            headers = table["headers"]
            value_at = None
            wanted = NUMERIC_VALUE_COLUMN.get(table["category"])
            if wanted is not None:
                for index, header in enumerate(headers):
                    if header.split(" Show ")[0].strip() == wanted:
                        value_at = index
                        break
            comment_at = None
            for index, header in enumerate(headers):
                if header.startswith("Comment ("):
                    comment_at = index
                    break
            if channel is None:
                continue
            bucket = counts[channel]
            assert table["reported"] == len(table["rows"]), table["category"]
            for row in table["rows"]:
                value = row[value_at].strip() if value_at is not None else ""
                comment = row[comment_at].strip() if comment_at is not None else ""
                bucket["rows"] += 1
                if value:
                    bucket["valued"] += 1
                    if POINT.match(value):
                        bucket["point"] += 1
                elif comment and NUMBER_IN_TEXT.search(comment):
                    bucket["from_comment"] += 1
        for name, bucket in counts.items():
            assert int(facts[key][name + "_rows"]) == bucket["rows"], (key, name)
            assert int(facts[key][name + "_valued"]) == bucket["valued"], (key, name)
            assert int(facts[key][name + "_point"]) == bucket["point"], (key, name)
            assert int(facts[key][name + "_point_from_comment"]) == bucket["from_comment"], (key, name)
    assert seen == set(facts)
