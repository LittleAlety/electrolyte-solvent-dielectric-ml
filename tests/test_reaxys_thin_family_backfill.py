"""Guards for the W17-2 thin-family backfill queue."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from probes.reaxys_thin_family_backfill import (
    MIN_COMPOUNDS,
    MIN_SOURCES,
    TARGET_FAMILIES,
    family_coverage,
    read_rows,
)

OBSERVATIONS = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
GAPS = REPOSITORY_ROOT / "probes" / "artifacts" / "al_round4_local_coverage_gaps.csv"
QUEUE = REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_queue.csv"
SUMMARY = REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_summary.json"
PREREG = REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_prereg.json"


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_coverage_matches_the_al_round4_gap_table() -> None:
    coverage = family_coverage(read_rows(OBSERVATIONS))
    shipped = {
        row["family"]: row
        for row in read_rows(GAPS)
        if row.get("row_kind") == "family"
    }
    for family in TARGET_FAMILIES:
        assert coverage[family]["compounds"] == int(shipped[family]["compounds_in_scope"])
        assert coverage[family]["rows"] == int(shipped[family]["observation_rows"])
        assert coverage[family]["distinct_sources"] == int(shipped[family]["distinct_source_doi"])


def test_every_thin_family_is_still_below_the_lower_bound() -> None:
    summary = _summary()
    assert summary["lower_bound"] == {
        "min_compounds": MIN_COMPOUNDS,
        "min_distinct_sources": MIN_SOURCES,
    }
    for family in TARGET_FAMILIES:
        report = summary["family_report"][family]
        assert report["meets_lower_bound"] is False, family
        assert report["compounds_needed"] == max(0, MIN_COMPOUNDS - report["current"]["compounds"])
        assert report["sources_needed"] == max(
            0, MIN_SOURCES - report["current"]["distinct_sources"]
        )


def test_queue_is_names_and_keys_only_and_lf() -> None:
    raw = QUEUE.read_bytes()
    assert b"\r\n" not in raw
    with QUEUE.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    assert "value" not in fields
    assert "dielectric" not in fields
    assert "access" in fields
    assert {row["access"] for row in rows} == {"restricted_crosscheck_only"}
    assert len(rows) == _summary()["queue_rows"]
    by_source = Counter(row["candidate_source"] for row in rows)
    assert dict(sorted(by_source.items())) == _summary()["queue_by_source"]


def test_the_arm_executes_no_reaxys_query() -> None:
    summary = _summary()
    assert summary["reaxys_queries_executed"] == 0
    assert summary["run_telemetry"]["network_calls"] == 0
    assert summary["run_telemetry"]["models_fitted"] == 0
    assert summary["run_telemetry"]["r2_reported"] is False
    assert summary["run_telemetry"]["writes_under_data"] == 0


def test_restricted_contract_is_explicit() -> None:
    contract = _summary()["restricted_contract"]
    assert contract["values_enter_data"] is False
    assert contract["values_enter_any_pool"] is False
    assert contract["access_labels"] == ["restricted_crosscheck_only"]


def test_prereg_is_locked_and_pinned_by_the_summary() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert _summary()["prereg"]["sha256"] == canonical_text_sha256(PREREG)
    assert _summary()["prereg"]["status"] == "locked_before_run"


def test_probe_check_style_run_is_deterministic() -> None:
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill.py")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["queue_rows"] == _summary()["queue_rows"]
