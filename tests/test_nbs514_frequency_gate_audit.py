"""Regression tests for the NBS Circular 514 frequency gate."""

from __future__ import annotations

import json

from probes.nbs514_frequency_gate_audit import (
    CRAWL_TARGETS,
    REPOSITORY_ROOT,
    build_audit,
    read_csv_rows,
)

ARTIFACT = REPOSITORY_ROOT / "probes" / "nbs514_frequency_gate_audit.json"
CURRENT_DATASET_SHA256 = (
    "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
)


def test_committed_artifact_matches_a_live_derivation() -> None:
    committed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    live = json.loads(json.dumps(build_audit()))
    committed.pop("generated_at_utc", None)
    live.pop("generated_at_utc", None)
    assert committed == live


def test_frequency_noted_rows_are_all_outside_the_dataset() -> None:
    audit = build_audit()
    cross = audit["cross_check"]
    assert audit["transcript"]["frequency_noted_rows"] > 0
    assert cross["frequency_noted_rows_present_in_static_dataset"] == 0
    assert cross["frequency_noted_rows_absent_from_static_dataset"] == (
        audit["transcript"]["frequency_noted_rows"]
    )


def test_every_frequency_note_is_a_microwave_measurement() -> None:
    audit = build_audit()
    for note in audit["transcript"]["frequency_note_values"]:
        assert "x10^8 cycles/sec" in note


def test_isobutyronitrile_crawl_hit_is_frequency_gated() -> None:
    audit = build_audit()
    targets = {row["source_id"]: row for row in audit["crawl_targets"]}
    assert set(targets) == set(CRAWL_TARGETS)
    hit = targets["nbs514:p20:009"]
    assert hit["compound_name"] == "Isobutyronitrile"
    assert hit["dielectric"] == "20.4"
    assert hit["T_K"] == "297.15"
    assert hit["frequency_note"] == "f=3.6x10^8 cycles/sec"
    assert hit["present_in_static_dataset"] is False


def test_gated_neighbour_keeps_its_independent_primary_value() -> None:
    audit = build_audit()
    targets = {row["source_id"]: row for row in audit["crawl_targets"]}
    neighbour = targets["nbs514:p20:008"]
    assert neighbour["compound_name"] == "Butyronitrile"
    assert neighbour["present_in_static_dataset"] is False
    # ... and the row the dataset keeps instead is the independent primary one.
    row = next(
        row
        for row in read_csv_rows(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")
        if row["inchikey"] == "KVNRLNFWIYMESJ-UHFFFAOYSA-N"
    )
    assert row["name"] == "butanenitrile"
    assert row["dielectric"] == "22.0"
    assert row["T_K"] == "298.15"
    assert row["source_doi"] == "10.1007/BF02848094"
    assert row["source_record_id"] != "nbs514:p20:008"


def test_inherited_nbs_rows_all_carry_the_zero_frequency_gate() -> None:
    audit = build_audit()
    static = audit["static_dataset"]
    assert static["nbs_sourced_rows"] > static["nbs_rows_carrying_zero_frequency_gate"]
    assert static["nbs_rows_carrying_zero_frequency_gate"] >= 100


def test_current_dataset_hash_is_untouched() -> None:
    assert build_audit()["static_dataset"]["canonical_sha256"] == CURRENT_DATASET_SHA256
