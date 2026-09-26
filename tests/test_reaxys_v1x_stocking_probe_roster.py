"""Guards for the W17-16 Reaxys stocking-queue probe roster.

Two things are pinned.  The *derived* half is pinned by re-derivation: the roster
must equal what the builder computes from the frozen queue and the prior probe
artefacts, and the probe_target / already_probed split must be recomputed from those
artefacts rather than copied from the queue's own stale flag.  The *plan* half is
pinned by boundary assertions: the roster runs no query, carries no Reaxys value, and
touches neither ``data/`` nor the main scoreboard.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from probes.build_reaxys_v1x_stocking_probe_roster import (
    build_roster,
    load_prereg,
    verify_invariants,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROSTER = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster.csv"
SUMMARY = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster_summary.json"
PREREG = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_prereg.json"
REPORT = REPOSITORY_ROOT / "reports" / "reaxys_v1x_stocking_probe_roster.md"
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_reaxys_v1x_stocking_probe_roster.py"

# The queue flags three rows as probed; the W17 thin-family lanes walked more, so the
# recomputed split must exceed the flag.  EMC was walked by W17-15 yet is unflagged.
EMC_KEY = "JBTWLSYIZRCDFO-UHFFFAOYSA-N"
QUEUE_FLAGGED_KEYS = {
    "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    "CWIFAKBLLXGZIC-UHFFFAOYSA-N",
}


def _rows() -> list[dict[str, str]]:
    with ROSTER.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_roster_is_exactly_the_p1_and_p2_tier() -> None:
    rows = _rows()
    assert len(rows) == 24
    assert {row["stocking_priority"] for row in rows} == {"P1", "P2"}


def test_every_key_is_taken_verbatim_from_the_queue() -> None:
    prereg = load_prereg()
    with (REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"]).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        queue_keys = {row["inchikey"].strip() for row in csv.DictReader(handle)}
    rows = _rows()
    assert all(row["inchikey"] in queue_keys for row in rows)
    assert len(rows) == len({row["inchikey"] for row in rows})


def test_the_split_is_recomputed_not_copied_from_the_queue_flag() -> None:
    rows = {row["inchikey"]: row for row in _rows()}
    # Every queue-flagged row is already_probed...
    for key in QUEUE_FLAGGED_KEYS:
        assert rows[key]["probe_status"] == "already_probed", key
    # ...and so is EMC, which the queue leaves unflagged but W17-15 walked.
    assert rows[EMC_KEY]["probe_status"] == "already_probed"
    assert "reaxys_thin_family_query_b2_facts.csv" in rows[EMC_KEY]["prior_evidence"]
    # A queue-flagged status is only one of the two rules and is named as such.
    assert all(
        "queue_flag:probed_in_this_round" in row["prior_evidence"]
        for row in _rows()
        if row["inchikey"] in QUEUE_FLAGGED_KEYS
    )


def test_counts_match_the_shipped_summary() -> None:
    rows = _rows()
    summary = _summary()
    targets = [row for row in rows if row["probe_status"] == "probe_target"]
    probed = [row for row in rows if row["probe_status"] == "already_probed"]
    assert summary["counts"]["probe_target"] == len(targets) == 18
    assert summary["counts"]["already_probed"] == len(probed) == 6
    assert summary["probe_target_keys_in_order"] == [row["inchikey"] for row in targets]


def test_probe_order_is_contiguous_and_targets_come_first() -> None:
    rows = _rows()
    assert [int(row["probe_order"]) for row in rows] == list(range(1, len(rows) + 1))
    statuses = [row["probe_status"] for row in rows]
    first_probed = statuses.index("already_probed")
    assert set(statuses[:first_probed]) == {"probe_target"}
    assert set(statuses[first_probed:]) == {"already_probed"}


def test_aromatic_suspects_are_flagged_and_sunk_to_the_tail() -> None:
    rows = _rows()
    suspects = [row for row in rows if row["aromatic_non_electrolyte_suspect"] == "yes"]
    assert suspects
    assert all(row["family_tag"] == "fluorinated" for row in suspects)
    assert all("c" in row["smiles"] for row in suspects)
    # The flagged rows are never dropped, only ordered last within their tier.
    targets = [row for row in rows if row["probe_status"] == "probe_target"]
    # Flagged rows are never dropped, only ordered last inside their own tier.
    assert {row["inchikey"] for row in suspects} <= {row["inchikey"] for row in targets}
    for tier in sorted({row["stocking_priority"] for row in targets}):
        in_tier = [row for row in targets if row["stocking_priority"] == tier]
        clean = [
            int(row["probe_order"])
            for row in in_tier
            if row["aromatic_non_electrolyte_suspect"] == "no"
        ]
        flagged = [
            int(row["probe_order"])
            for row in in_tier
            if row["aromatic_non_electrolyte_suspect"] == "yes"
        ]
        if clean and flagged:
            assert max(clean) < min(flagged), tier




def test_the_roster_is_a_plan_not_a_measurement() -> None:
    summary = _summary()
    assert summary["is_a_plan_not_a_measurement"] is True
    assert summary["queries_executed"] == 0
    assert summary["non_interference"]["models_fitted"] == 0
    assert summary["non_interference"]["r2_reported"] is False
    assert summary["non_interference"]["main_scoreboard_touched"] is False
    assert summary["non_interference"]["data_tracked_files_written"] == []
    assert summary["compliance"]["values_enter_data"] is False
    assert summary["compliance"]["values_enter_any_pool"] is False


def test_every_carried_field_is_a_queue_metadata_field() -> None:
    """No Reaxys rendered value can ride in: every column traces to the queue file."""

    prereg = load_prereg()
    with (REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"]).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        queue = list(csv.DictReader(handle))
    by_key = {row["inchikey"]: row for row in queue}
    for row in _rows():
        source = by_key[row["inchikey"]]
        assert row["name"] == (source.get("name") or "").strip()
        assert row["smiles"] == (source.get("smiles") or "").strip()
        assert row["target_dielectric"] == (source.get("target_dielectric") or "").strip()
        assert row["local_rows"] == (source.get("local_rows") or "").strip()


def test_builder_invariants_hold() -> None:
    prereg = load_prereg()
    with (REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"]).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        queue = list(csv.DictReader(handle))
    rows, _ = build_roster(prereg)
    assert verify_invariants(rows, queue) == []


def test_prereg_pins_the_queue_and_the_prior_artefacts() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    queue_path = REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"]
    digest = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    assert digest == prereg["inputs"]["queue"]["sha256"]
    for item in prereg["inputs"]["prior_probe_artefacts"]:
        measured = hashlib.sha256((REPOSITORY_ROOT / item["path"]).read_bytes()).hexdigest()
        assert measured == item["sha256"], item["path"]


def test_summary_records_the_roster_digest_and_the_key_audit() -> None:
    summary = _summary()
    assert summary["roster"]["sha256"] == hashlib.sha256(ROSTER.read_bytes()).hexdigest()
    assert summary["key_audit"]["keys_not_from_the_queue"] == 0
    assert "verbatim" in summary["key_audit"]["rule"]


def test_independent_verifier_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


def test_report_states_the_plan_scope() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "queries_executed = 0" in text
    assert "keys_not_from_the_queue = 0" in text
    assert "0.4091179943351143" in text

