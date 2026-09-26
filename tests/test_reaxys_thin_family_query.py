"""Offline tests for the W17-13 Reaxys thin-family query.

The pinned literals are what the session produced.  They are written out
literally rather than recomputed so that a silent edit to the fact table, the
summary or the queue shows up as a failure instead of quietly re-baselining.

The raw page evidence lives in the git-ignored ``data/raw/reaxys_w17b/``; the
checks that need it are skipped when it is absent, which is the normal state in
CI.  Nothing here touches the network.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

FACTS = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_facts.csv"
SUMMARY = REPOSITORY_ROOT / "probes/reaxys_thin_family_query_summary.json"
PROBE = REPOSITORY_ROOT / "probes/reaxys_thin_family_query.py"
QUEUE = REPOSITORY_ROOT / "probes/reaxys_thin_family_backfill_queue.csv"
REPORT = REPOSITORY_ROOT / "reports/reaxys_thin_family_query.md"
RAW_EVIDENCE = REPOSITORY_ROOT / "data/raw/reaxys_w17b/observations.csv"

GIT_METADATA_PRESENT = (REPOSITORY_ROOT / ".git").exists()
RAW_PRESENT = RAW_EVIDENCE.exists()

FACTS_SHA256 = "f57e865fc1f63ff69c566c6335ac667fbd106a1192c7677f6b65ab61cc33f847"
SUMMARY_SHA256 = "2a8b44cf78262b8ddda49020e3f442ad1b6a676e58b4c4e07a1bc4f0e37daa40"
QUEUE_SHA256 = "350b40f3b81de4d40b96f79557056711a69cebf593e99b2c4fa92516e3e5a426"
OBSERVATIONS_SHA256 = "601c78e910c0f041a6d22ad9822a266a88748b2301efa589ee1dc9671fdf5907"

FACT_COLUMNS = [
    "substance",
    "inchikey",
    "in_backfill_queue",
    "reaxys_rn",
    "cas",
    "eps_rows",
    "eps_valued",
    "eps_point",
    "eta_rows",
    "eta_valued",
    "eta_point",
    "hp_rows",
    "hp_valued",
    "hp_point",
    "redox_rows",
    "redox_valued",
    "redox_point",
    "redox_point_from_comment",
    "hp_point_property",
]

SUBSTANCES = 10
CHANNEL_TALLY = {
    "epsilon": (78, 66, 59),
    "eta": (169, 162, 143),
    "homo_lumo": (24, 13, 10),
    "redox": (19, 5, 5),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_facts():
    with open(FACTS, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


@pytest.fixture(scope="module")
def summary():
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def facts():
    return load_facts()


def test_facts_table_is_pinned(facts):
    header, rows = facts
    assert header == FACT_COLUMNS
    assert len(rows) == SUBSTANCES
    assert sha256(FACTS) == FACTS_SHA256


def test_facts_keys_are_unique_sorted_and_non_empty(facts):
    _, rows = facts
    keys = [row["inchikey"] for row in rows]
    assert keys == sorted(set(keys))
    assert all(len(key.split("-")) == 3 for key in keys)


def test_summary_is_pinned_and_self_consistent(summary):
    assert sha256(SUMMARY) == SUMMARY_SHA256
    assert summary["schema_version"] == "reaxys_thin_family_query/v1"
    assert summary["arm"] == "W17-13"
    assert summary["substances_queried"] == SUBSTANCES
    assert summary["facts_path"] == "probes/reaxys_thin_family_query_facts.csv"
    assert summary["facts_sha256"] == sha256(FACTS) == FACTS_SHA256


def test_channel_tally_is_pinned(summary):
    tally = summary["channel_tally"]
    assert set(tally) == set(CHANNEL_TALLY)
    for channel, (rows, valued, points) in CHANNEL_TALLY.items():
        block = tally[channel]
        assert block["rows"] == rows
        assert block["valued_rows"] == valued
        assert block["point_values"] == points
        assert block["reference_only_rows"] == rows - valued
        assert block["valued_rows"] + block["reference_only_rows"] == rows


def test_every_key_comes_from_the_w17_2_queue(facts, summary):
    assert sha256(QUEUE) == QUEUE_SHA256
    with open(QUEUE, newline="", encoding="utf-8") as handle:
        queue_keys = {
            row["candidate_inchikey"]
            for row in csv.DictReader(handle)
            if row.get("candidate_inchikey")
        }
    _, rows = facts
    assert {row["inchikey"] for row in rows} <= queue_keys
    audit = summary["queue_key_audit"]
    assert audit["keys_from_the_w17_2_queue"] == SUBSTANCES
    assert audit["keys_not_from_the_queue"] == 0
    assert audit["queue_sha256"] == QUEUE_SHA256
    assert all(row["in_backfill_queue"] == "true" for row in rows)


def test_orbit_and_redox_channels_do_not_claim_more_than_they_hold(facts):
    """The two channels the P4 bottleneck depends on must stay honestly small."""
    _, rows = facts
    by_substance = {row["substance"]: row for row in rows}
    assert sum(int(row["hp_point"]) for row in rows) == 10
    assert sum(int(row["redox_point"]) for row in rows) == 5
    # every redox point in this set was read out of the Comment column
    assert sum(int(row["redox_point_from_comment"]) for row in rows) == 5
    for row in rows:
        assert int(row["redox_point_from_comment"]) <= int(row["redox_point"])
        # an ionization potential is not an orbital energy: only the two
        # carboxylic acids carry any, and the column names the quantity
        if int(row["hp_point"]) > 0:
            assert row["hp_point_property"] == "Ionization Potential"
        else:
            assert row["hp_point_property"] == ""
    assert "Ionization Potential" not in [
        row["hp_point_property"] for row in rows if row["hp_point"] == "0"
    ]
    assert by_substance["acetic acid"]["redox_point"] == "0"
    assert by_substance["valeric acid"]["redox_point"] == "4"


def test_the_four_protic_ionic_liquids_have_no_epsilon_category(facts):
    _, rows = facts
    by_substance = {row["substance"]: row for row in rows}
    for name in (
        "2-hydroxyethylammonium acetate",
        "2-hydroxyethylammonium lactate",
        "triethanolamine lactate",
        "triethanolammonium acetate",
    ):
        assert by_substance[name]["eps_rows"] == "0"
        assert int(by_substance[name]["eta_point"]) >= 1
    # the three that show "Retrieve CAS RN" on the card carry no CAS here either
    for name in (
        "2-hydroxyethylammonium lactate",
        "triethanolamine lactate",
        "triethanolammonium acetate",
    ):
        assert by_substance[name]["cas"] == ""
    assert by_substance["2-hydroxyethylammonium acetate"]["cas"] == "54300-24-2"


def test_report_quotes_the_pinned_digests():
    text = REPORT.read_text(encoding="utf-8")
    assert FACTS_SHA256 in text
    assert SUMMARY_SHA256 in text
    assert "W17-13" in text


def test_restricted_contract_blocks_every_value_route(summary):
    contract = summary["restricted_contract"]
    assert contract["values_enter_data"] is False
    assert contract["values_enter_any_pool"] is False
    assert contract["values_enter_any_feature_table"] is False
    assert contract["values_ship_in_this_bundle"] is False
    assert summary["non_interference"]["models_fitted"] == 0
    assert summary["non_interference"]["r2_reported"] is False
    assert summary["non_interference"]["main_scoreboard_touched"] is False
    assert summary["non_interference"]["data_tracked_files_modified"] == []


@pytest.mark.skipif(not GIT_METADATA_PRESENT, reason="no git metadata to query")
def test_raw_evidence_is_ignored_and_the_deliverables_are_not():
    def ignored(relative):
        return (
            subprocess.run(
                ["git", "check-ignore", "-q", relative],
                cwd=str(REPOSITORY_ROOT),
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )

    assert ignored("data/raw/reaxys_w17b/observations.csv")
    assert not ignored("probes/reaxys_thin_family_query.py")
    assert not ignored("probes/reaxys_thin_family_query_facts.csv")
    assert not ignored("probes/reaxys_thin_family_query_summary.json")


@pytest.mark.skipif(not RAW_PRESENT, reason="raw Reaxys evidence is not committed")
def test_raw_evidence_digest_matches_the_summary(summary):
    assert sha256(RAW_EVIDENCE) == OBSERVATIONS_SHA256
    assert summary["evidence"]["observations_csv"]["sha256"] == OBSERVATIONS_SHA256


@pytest.mark.skipif(not RAW_PRESENT, reason="raw Reaxys evidence is not committed")
def test_probe_reproduces_byte_identically_from_the_raw_layer():
    result = subprocess.run(
        [sys.executable, str(PROBE), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=str(REPOSITORY_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CHECK OK" in result.stdout
