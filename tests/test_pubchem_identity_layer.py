"""Offline unit tests for the L0 PubChem identity layer.

Nothing here touches the network. The HTTP layer is made deterministic by
pre-seeding a throw-away cache directory and, where a missing cache must be
exercised, by running the client in ``offline`` mode so a stray request raises
instead of silently succeeding.

The last two tests read the committed artefacts under ``data/reference`` and
``probes`` and re-derive the summary counts from the CSV, so a hand-edited row
cannot survive without the summary disagreeing with it.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.pubchem_identity_layer import (
    IDENTITY_COLUMNS,
    OfflineError,
    PubChemClient,
    _difference_kind,
    _properties_url,
    _shared_smiles,
    build_targets,
    load_roster,
    parse_property_record,
    resolve_targets,
    summarize,
    write_rows,
)

COMMITTED_MAP = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
COMMITTED_SUMMARY = REPOSITORY_ROOT / "probes" / "pubchem_identity_layer_summary.json"

ACETONITRILE = "WEVYAHXRMPXWCK-UHFFFAOYSA-N"
WATER = "XLYOFNOQVPJJNP-UHFFFAOYSA-N"

RESOLUTION_STATUSES = {
    "resolved_pubchem",
    "unresolved_no_pubchem_record",
    "unresolved_offline",
    "unresolved_empty_response",
}


def _seed_cache(cache_dir: Path, inchikey: str, payload: object) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{inchikey}.properties.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.with_suffix(path.suffix + ".url").write_text(
        _properties_url(inchikey) + "\n", encoding="utf-8"
    )


def _property_payload(cid: int, formula: str, weight: str, smiles: str, inchikey: str) -> dict:
    return {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": cid,
                    "MolecularFormula": formula,
                    "MolecularWeight": weight,
                    "SMILES": smiles,
                    "InChIKey": inchikey,
                }
            ]
        }
    }


def _client(cache_dir: Path, *, offline: bool = True) -> PubChemClient:
    return PubChemClient(
        cache_dir=cache_dir,
        offline=offline,
        throttle_seconds=0.0,
        sleep_fn=lambda _seconds: None,
    )


def _target(inchikey: str, **overrides: object) -> dict[str, object]:
    target: dict[str, object] = {
        "inchikey": inchikey,
        "name": "probe",
        "smiles": "CC#N",
        "in_roster": True,
        "in_lowfreq_table": False,
        "in_ilthermo_table": False,
    }
    target.update(overrides)
    return target


# --------------------------------------------------------------------------
# Coverage set.
# --------------------------------------------------------------------------


def test_targets_are_the_sorted_union_of_the_roster_and_the_two_cid_tables() -> None:
    targets = build_targets()
    keys = [str(target["inchikey"]) for target in targets]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))
    assert sum(1 for target in targets if target["in_roster"]) == 246
    roster_keys = {row["inchikey"] for row in load_roster()}
    assert roster_keys <= set(keys)
    assert len(targets) == 314


def test_every_roster_key_is_flagged_and_no_key_is_flagged_twice() -> None:
    targets = build_targets()
    roster = [str(target["inchikey"]) for target in targets if target["in_roster"]]
    assert len(roster) == len(set(roster)) == 246


# --------------------------------------------------------------------------
# Cache and offline behaviour.
# --------------------------------------------------------------------------


def test_cache_hit_is_served_without_any_network_call(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    assert client.stats.cache_hits == 1
    assert client.stats.network_calls == 0
    row = rows[0]
    assert row["resolution_status"] == "resolved_pubchem"
    assert row["pubchem_cid"] == "6342"
    assert row["molecular_formula"] == "C2H3N"
    assert row["molecular_weight"] == "41.05"
    assert row["resolved_from"] == "pubchem_pug_rest"
    assert row["identity_check"] == "roundtrip_match"


def test_missing_cache_while_offline_is_unresolved_not_absent(tmp_path: Path) -> None:
    client = _client(tmp_path / "empty", offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    row = rows[0]
    assert row["resolution_status"] == "unresolved_offline"
    assert row["pubchem_cid"] == ""
    assert row["resolved_from"] == "none"
    assert "no cached PubChem response" in row["notes"]


def test_offline_client_raises_rather_than_silently_returning_nothing(tmp_path: Path) -> None:
    client = _client(tmp_path / "empty", offline=True)
    with pytest.raises(OfflineError):
        client.fetch(ACETONITRILE)


def test_a_cache_file_whose_url_marker_disagrees_is_not_trusted(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    (cache_dir / f"{ACETONITRILE}.properties.json.url").write_text(
        _properties_url(WATER) + "\n", encoding="utf-8"
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    assert client.stats.cache_hits == 0
    assert rows[0]["resolution_status"] == "unresolved_offline"


def test_a_404_payload_is_recorded_as_no_pubchem_record(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(cache_dir, ACETONITRILE, {"not_found": True, "http_status": 404})
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    row = rows[0]
    assert row["resolution_status"] == "unresolved_no_pubchem_record"
    assert row["pubchem_cid"] == ""
    assert row["retrieved_at"]


def test_local_table_cid_is_kept_when_pubchem_has_no_record(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(cache_dir, ACETONITRILE, {"not_found": True, "http_status": 404})
    client = _client(cache_dir, offline=True)
    rows = resolve_targets(
        [_target(ACETONITRILE)],
        client,
        known_cids={ACETONITRILE: ("6342", "lowfreq_structures_table")},
        aliases={},
    )
    row = rows[0]
    assert row["pubchem_cid"] == "6342"
    assert "not in PubChem" in row["notes"]


# --------------------------------------------------------------------------
# Conflict detection.
# --------------------------------------------------------------------------


def test_cid_conflict_between_a_local_table_and_pubchem_is_flagged(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets(
        [_target(ACETONITRILE)],
        client,
        known_cids={ACETONITRILE: ("9999", "ilthermo_new_compounds_table")},
        aliases={},
    )
    assert rows[0]["notes"].startswith("cid_conflict")
    assert "9999" in rows[0]["notes"]


def test_corroborated_cid_is_recorded_without_a_conflict(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets(
        [_target(ACETONITRILE)],
        client,
        known_cids={ACETONITRILE: ("6342", "lowfreq_structures_table")},
        aliases={},
    )
    assert rows[0]["notes"] == "cid_corroborated_by lowfreq_structures_table"


def test_a_roundtrip_mismatch_is_flagged_and_keeps_the_row_resolved(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", WATER),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    assert rows[0]["identity_check"] == "roundtrip_mismatch"


def test_smiles_comparison_ignores_atom_ordering_but_not_structure(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    # PubChem canonicalises differently, so a raw string comparison would call
    # this a mismatch even though "N#CC" and "CC#N" are the same molecule.
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "N#CC", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE, smiles="CC#N")], client, known_cids={}, aliases={})
    assert rows[0]["smiles_match"] == "match"
    assert rows[0]["smiles"] == "CC#N"
    assert rows[0]["pubchem_smiles"] == "N#CC"


def test_a_genuinely_different_structure_is_reported_as_differ(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    # Propionitrile on the PubChem side, acetonitrile locally.
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CCC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE, smiles="CC#N")], client, known_cids={}, aliases={})
    assert rows[0]["smiles_match"] == "differ"


def test_an_unparseable_smiles_on_either_side_is_not_comparable(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "not-a-molecule", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE, smiles="CC#N")], client, known_cids={}, aliases={})
    assert rows[0]["smiles_match"] == "not_comparable"


def test_aliases_are_joined_into_one_field(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets(
        [_target(ACETONITRILE)],
        client,
        known_cids={},
        aliases={ACETONITRILE: ["acetonitrile", "ethanenitrile"]},
    )
    assert rows[0]["alias_names"] == "acetonitrile;ethanenitrile"


# --------------------------------------------------------------------------
# Idempotence and artefacts.
# --------------------------------------------------------------------------


def test_resolution_is_idempotent_over_the_same_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    first = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={}, retrieved_at="T")
    second = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={}, retrieved_at="T")
    assert first == second
    assert client.stats.network_calls == 0


def test_written_csv_is_utf8_lf_with_the_declared_columns(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets([_target(ACETONITRILE)], client, known_cids={}, aliases={})
    output = tmp_path / "identity_map.csv"
    write_rows(output, rows)
    raw = output.read_bytes()
    assert b"\r" not in raw
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == IDENTITY_COLUMNS
        written = list(reader)
    assert len(written) == 1
    assert written[0]["inchikey"] == ACETONITRILE


def test_summary_exposes_every_required_field(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _seed_cache(
        cache_dir,
        ACETONITRILE,
        _property_payload(6342, "C2H3N", "41.05", "CC#N", ACETONITRILE),
    )
    client = _client(cache_dir, offline=True)
    rows = resolve_targets(
        [_target(ACETONITRILE), _target(WATER, in_roster=False)],
        client,
        known_cids={},
        aliases={},
    )
    summary = summarize(rows, client.stats, roster_keys=246, run_idempotent=True)
    for key in (
        "roster_keys",
        "resolved_with_cid",
        "unresolved",
        "cache_hits",
        "network_calls",
        "throttle_seconds",
        "run_idempotent",
    ):
        assert key in summary
    assert summary["roster_keys"] == 246
    assert summary["resolved_with_cid"] == 1
    assert summary["unresolved_count"] == 1
    assert summary["unresolved"][0]["inchikey"] == WATER
    assert summary["resolution_status_counts"]["unresolved_offline"] == 1


def test_parse_property_record_rejects_payloads_without_a_cid() -> None:
    assert parse_property_record({"not_found": True}) is None
    assert parse_property_record({}) is None
    assert parse_property_record({"PropertyTable": {"Properties": []}}) is None
    assert parse_property_record({"PropertyTable": {"Properties": [{"MolecularFormula": "C"}]}}) is None


# --------------------------------------------------------------------------
# Committed artefacts.
# --------------------------------------------------------------------------


def test_committed_identity_map_is_well_formed_and_covers_the_roster() -> None:
    assert COMMITTED_MAP.is_file(), "run probes/pubchem_identity_layer.py first"
    raw = COMMITTED_MAP.read_bytes()
    assert b"\r" not in raw
    with COMMITTED_MAP.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == IDENTITY_COLUMNS
        rows = list(reader)
    keys = [row["inchikey"] for row in rows]
    assert len(keys) == len(set(keys)) == 314
    roster_keys = {row["inchikey"] for row in load_roster()}
    assert roster_keys <= set(keys)
    assert {row["resolution_status"] for row in rows} <= RESOLUTION_STATUSES
    resolved = [row for row in rows if row["resolution_status"] == "resolved_pubchem"]
    assert resolved, "the committed run resolved nothing"
    for row in resolved:
        assert row["pubchem_cid"].isdigit()
        assert row["molecular_formula"]
        assert row["molecular_weight"]
        assert row["source_url"].startswith("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/")
        assert row["retrieved_at"].endswith("Z")
        assert row["identity_check"] in {"roundtrip_match", "roundtrip_mismatch", "not_reported"}


def test_difference_kind_separates_stereo_stripping_from_a_real_disagreement() -> None:
    # trans-1,2-dichloroethylene vs its stereo-free form.
    assert _difference_kind("Cl/C=C/Cl", "C(=CCl)Cl") == "stereo_only"
    # Propionitrile is not acetonitrile.
    assert _difference_kind("CC#N", "CCC#N") == "structural"
    assert _difference_kind("not-a-molecule", "CC#N") == "unclassified"


def test_shared_smiles_groups_two_keys_onto_one_string() -> None:
    rows = [
        {"inchikey": "A", "pubchem_smiles": "CCC"},
        {"inchikey": "B", "pubchem_smiles": "CCC"},
        {"inchikey": "C", "pubchem_smiles": "CCN"},
    ]
    shared = _shared_smiles(rows)
    assert shared == [{"pubchem_smiles": "CCC", "inchikeys": ["A", "B"]}]


def test_committed_summary_classifies_every_smiles_disagreement() -> None:
    summary = json.loads(COMMITTED_SUMMARY.read_text(encoding="utf-8"))
    differing = summary["smiles_differing_keys"]
    kinds: dict[str, list[str]] = {}
    for entry in differing:
        kinds.setdefault(entry["difference_kind"], []).append(entry["inchikey"])
    assert len(differing) == summary["smiles_match_counts"]["differ"] == 15
    assert len(kinds["stereo_only"]) == 10
    assert kinds.get("unclassified", []) == []
    # These five are real structural disagreements and are pinned by key so a
    # silent re-harvest cannot make them disappear from the record.
    assert sorted(kinds["structural"]) == [
        "FSXANJBLYFVXEU-UHFFFAOYSA-N",
        "LBHLGZNUPKUZJC-UHFFFAOYSA-N",
        "OHLUUHNLEMFGTQ-UHFFFAOYSA-N",
        "OOKUTCYPKPJYFV-UHFFFAOYSA-N",
        "ZHNUHDYFZUAESO-UHFFFAOYSA-N",
    ]


def test_committed_summary_flags_pubchem_smiles_shared_by_several_keys() -> None:
    summary = json.loads(COMMITTED_SUMMARY.read_text(encoding="utf-8"))
    shared = summary["pubchem_smiles_shared_by_several_keys"]
    pairs = sorted(tuple(entry["inchikeys"]) for entry in shared)
    # cis/trans-1,2-dichloroethylene and cis/trans-3-hexene each collapse to one
    # PubChem ConnectivitySMILES. A SMILES-keyed join would merge them.
    assert pairs == [
        ("KFUSEUYYWQURPO-OWOJBTEDSA-N", "KFUSEUYYWQURPO-UPHRSURJSA-N"),
        ("ZQDPJFUHLCOCRG-AATRIKPKSA-N", "ZQDPJFUHLCOCRG-WAYWQWQTSA-N"),
    ]


def test_committed_summary_agrees_with_the_committed_csv() -> None:
    assert COMMITTED_SUMMARY.is_file(), "run probes/pubchem_identity_layer.py first"
    summary = json.loads(COMMITTED_SUMMARY.read_text(encoding="utf-8"))
    with COMMITTED_MAP.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert summary["coverage_set"] == len(rows)
    assert summary["resolved_with_cid"] == sum(1 for row in rows if row["pubchem_cid"])
    assert summary["unresolved_count"] == sum(1 for row in rows if not row["pubchem_cid"])
    assert summary["roster_keys"] == 246
    assert summary["roster_resolved_with_cid"] == sum(
        1 for row in rows if row["in_roster"] == "true" and row["pubchem_cid"]
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["resolution_status"]] = counts.get(row["resolution_status"], 0) + 1
    assert summary["resolution_status_counts"] == dict(sorted(counts.items()))
    assert summary["run_idempotent"] is True
    assert summary["network_calls"] >= 0
