"""Regression tests for the Appendix I/J roster reconciliation.

The failure these pin down is a false negative, not a wrong value: the dataset
has carried the three glymes and both dinitriles since v0.1 under IUPAC-type
names, and a common-name search reports them as absent.
"""

from __future__ import annotations

import json

import pytest

from probes.manual_appendix_reconciliation import (
    ALIAS_REGISTRY,
    CURRENT_VERSION,
    DATASET_VERSIONS,
    DEFAULT_MANUAL,
    REPOSITORY_ROOT,
    TARGET_GROUPS,
    _evaluate_claims,
    _probe_manual,
    build_reconciliation,
    name_search_safety,
    read_csv_rows,
)

ARTIFACT = REPOSITORY_ROOT / "probes" / "manual_appendix_reconciliation.json"
CURRENT_DATASET_SHA256 = (
    "765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60"
)

GLYME_KEYS = TARGET_GROUPS["glymes"]
DINITRILE_KEYS = TARGET_GROUPS["dinitriles"]
ALL_GROUP_KEYS = tuple(
    key for keys in TARGET_GROUPS.values() for key in keys
)
@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return build_reconciliation()


def _by_key(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {target["inchikey"]: target for target in report["targets"]}


def _manual_state(payload: dict[str, object]) -> dict[str, object]:
    """The manual facts that must stay fresh, ignoring line-number drift."""

    probe = payload.get("manual_probe") or {}
    return {
        "available": probe.get("available"),
        "stale_phrase_hit_count": probe.get("stale_phrase_hit_count"),
        "stale_phrases": sorted(
            hit["phrase"]
            for hit in probe.get("stale_phrase_hits", [])
            if hit["line_numbers"]
        ),
    }


def test_committed_artifact_matches_a_live_derivation(
    report: dict[str, object],
) -> None:
    committed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    live = json.loads(json.dumps(report))
    # The manual is an external file: when it is present, the stored probe result
    # must still describe it, otherwise a stale verdict would ship unnoticed.
    if DEFAULT_MANUAL.exists():
        assert _manual_state(committed) == _manual_state(live)
        assert _manual_state(committed)["stale_phrase_hit_count"] == 0
    for payload in (committed, live):
        payload.pop("generated_at_utc", None)
        payload.pop("manual_probe", None)
    assert committed == live


def test_every_registered_molecule_is_in_the_current_dataset(
    report: dict[str, object],
) -> None:
    registry_keys = {
        row["inchikey"] for row in read_csv_rows(REPOSITORY_ROOT / ALIAS_REGISTRY)
    }
    targets = _by_key(report)
    assert set(targets) == registry_keys
    assert all(
        target["current_row"] is not None for target in targets.values()
    ), "a molecule in the alias registry is missing from the current dataset"


def test_registry_stored_name_matches_the_dataset_row(
    report: dict[str, object],
) -> None:
    registry = read_csv_rows(REPOSITORY_ROOT / ALIAS_REGISTRY)
    for key, target in _by_key(report).items():
        stored = [
            row["alias"]
            for row in registry
            if row["inchikey"] == key and row["alias_type"] == "dataset_name"
        ]
        assert len(stored) == 1, f"{key} must declare exactly one dataset name"
        assert stored[0] == target["current_row"]["name"], (
            f"{key}: the registry says {stored[0]!r} but the dataset stores "
            f"{target['current_row']['name']!r}"
        )


@pytest.mark.parametrize("inchikey", GLYME_KEYS + DINITRILE_KEYS)
def test_glymes_and_dinitriles_are_in_every_dataset_version(
    report: dict[str, object], inchikey: str
) -> None:
    presence = _by_key(report)[inchikey]["presence"]
    assert set(presence) == {label for label, _ in DATASET_VERSIONS}
    assert all(presence.values()), (
        f"{inchikey} vanished from {[k for k, v in presence.items() if not v]}"
    )


def test_name_search_misses_are_exactly_the_token_disjoint_names(
    report: dict[str, object],
) -> None:
    assert tuple(report["summary"]["targets_missed_by_common_name_search"]) == (
        "2,5,8,11,14-pentaoxapentadecane",
        "2,5,8,11-tetraoxadodecane",
        "2,5,8-trioxanonane",
        "hexanedinitrile",
        "pentanedinitrile",
    )
    assert report["summary"]["targets_without_a_registered_common_name"] == []


def test_claim_verdicts_are_pinned(report: dict[str, object]) -> None:
    verdicts = {claim["claim_id"]: claim["verdict"] for claim in report["claims"]}
    assert verdicts == {
        "appendix_i_a1_pc": "confirmed_and_since_closed",
        "appendix_i_a1_ec": "confirmed_and_since_closed",
        "appendix_i_a1_ec_extended_band_empty": "confirmed_and_since_closed",
        "appendix_i_a1_glymes_absent": "false_negative",
        "appendix_i_a1_glutaronitrile_absent": "false_negative",
        "appendix_i_a1_mopn_absent": "confirmed_and_since_closed",
    }
    assert report["summary"]["verdict_counts"] == {
        "confirmed_and_since_closed": 4,
        "false_negative": 2,
    }


def test_current_dataset_hash_is_untouched(report: dict[str, object]) -> None:
    hashes = {row["label"]: row["canonical_sha256"] for row in report["datasets"]}
    assert hashes[CURRENT_VERSION] == CURRENT_DATASET_SHA256


def test_the_temperature_band_column_is_reported_as_absent_before_v031(
    report: dict[str, object],
) -> None:
    bands = {row["label"]: row for row in report["datasets"]}
    for label in ("v0.1", "v0.2"):
        assert bands[label]["temperature_band_column_present"] is False
        assert bands[label]["temperature_band_counts"] is None
    for label in ("v0.3.1", "v0.3.2", "v0.3"):
        assert bands[label]["temperature_band_column_present"] is True


# --- verdict logic: the claim must fail when any part of it fails -----------


def _synthetic(presence_by_key: dict[str, dict[str, bool]], ec_row: dict) -> list[dict]:
    current_rows = {key: None for key in ALL_GROUP_KEYS}
    current_rows[TARGET_GROUPS["ec"][0]] = ec_row
    targets = []
    for key in ALL_GROUP_KEYS:
        presence = presence_by_key.get(
            key, {label: False for label, _ in DATASET_VERSIONS}
        )
        targets.append(
            {
                "inchikey": key,
                "presence": presence,
                "first_present_version": next(
                    (label for label, _ in DATASET_VERSIONS if presence[label]), None
                ),
                "current_row": current_rows[key],
                "name_search": {"dataset_name": "synthetic"},
            }
        )
    return targets


def _synthetic_snapshots() -> dict[str, dict[str, object]]:
    return {
        label: {"temperature_band_counts": {"room_temperature": 1, "extended_temperature": 1}}
        for label, _ in DATASET_VERSIONS
    }


def test_pc_claim_fails_when_the_row_was_already_present_in_v031() -> None:
    key = TARGET_GROUPS["pc"][0]
    presence = {
        "v0.1": False,
        "v0.2": False,
        "v0.3.1": True,
        "v0.3.2": True,
        "v0.3": True,
    }
    claims = _evaluate_claims(
        _synthetic_snapshots(), _synthetic({key: presence}, {"temperature_band": "room_temperature", "T_K": "298.15"})
    )
    pc = next(claim for claim in claims if claim["claim_id"] == "appendix_i_a1_pc")
    assert pc["verdict"] == "not_reproduced"


def test_ec_claim_fails_without_the_extended_temperature_band() -> None:
    key = TARGET_GROUPS["ec"][0]
    presence = {
        "v0.1": False,
        "v0.2": False,
        "v0.3.1": False,
        "v0.3.2": True,
        "v0.3": True,
    }
    claims = _evaluate_claims(
        _synthetic_snapshots(),
        _synthetic({key: presence}, {"temperature_band": "room_temperature", "T_K": "298.15"}),
    )
    ec = next(claim for claim in claims if claim["claim_id"] == "appendix_i_a1_ec")
    assert ec["verdict"] == "not_reproduced"


def test_ec_claim_holds_in_the_extended_band() -> None:
    key = TARGET_GROUPS["ec"][0]
    presence = {
        "v0.1": False,
        "v0.2": False,
        "v0.3.1": False,
        "v0.3.2": True,
        "v0.3": True,
    }
    claims = _evaluate_claims(
        _synthetic_snapshots(),
        _synthetic({key: presence}, {"temperature_band": "extended_temperature", "T_K": "313.15"}),
    )
    ec = next(claim for claim in claims if claim["claim_id"] == "appendix_i_a1_ec")
    assert ec["verdict"] == "confirmed_and_since_closed"


def test_one_present_glyme_refutes_the_whole_roster_claim() -> None:
    key = TARGET_GROUPS["glymes"][0]
    presence = {"v0.1": True, "v0.2": False, "v0.3.1": False, "v0.3.2": False, "v0.3": False}
    claims = _evaluate_claims(
        _synthetic_snapshots(),
        _synthetic({key: presence}, {"temperature_band": "room_temperature", "T_K": "298.15"}),
    )
    glymes = next(
        claim for claim in claims if claim["claim_id"] == "appendix_i_a1_glymes_absent"
    )
    assert glymes["verdict"] == "false_negative"
    assert glymes["evidence"]["refuted_by"][0]["versions_present"] == ["v0.1"]


# --- name-search diagnostic: generic tokens must not count as evidence ------


def test_generic_token_overlap_does_not_count_as_findable() -> None:
    snapshot = {"rows_by_inchikey": {"X": {"name": "ethyl methyl carbonate"}}}
    aliases = [{"alias": "methyl formate", "alias_type": "common_name"}]
    result = name_search_safety("X", aliases, snapshot)
    assert result["common_name_matches_dataset_name"] is False
    assert result["name_search_would_miss"] is True


def test_distinctive_token_overlap_counts_as_findable() -> None:
    snapshot = {"rows_by_inchikey": {"X": {"name": "propylene carbonate"}}}
    aliases = [{"alias": "propylene glycol carbonate", "alias_type": "common_name"}]
    assert name_search_safety("X", aliases, snapshot)["name_search_would_miss"] is False


def test_missing_common_name_is_unjudged_not_findable() -> None:
    snapshot = {"rows_by_inchikey": {"X": {"name": "opaque systematic name"}}}
    aliases = [{"alias": "DGM", "alias_type": "abbreviation"}]
    result = name_search_safety("X", aliases, snapshot)
    assert result["common_name_registered"] is False
    assert result["name_search_would_miss"] is None


# --- the manual guard ------------------------------------------------------


def test_a_bare_correction_marker_does_not_excuse_the_claim(tmp_path) -> None:
    fake = tmp_path / "manual.md"
    fake.write_text(
        "diglyme/triglyme/tetraglyme 连带缺失 【已对账更正】\n", encoding="utf-8"
    )
    probe = _probe_manual(fake)
    assert probe["stale_phrase_hit_count"] == 1


def test_a_substantive_correction_excuses_the_claim(tmp_path) -> None:
    fake = tmp_path / "manual.md"
    fake.write_text(
        "diglyme/triglyme/tetraglyme 连带缺失 【已对账更正】属假阴性，库内名为 "
        "2,5,8-trioxanonane\n",
        encoding="utf-8",
    )
    probe = _probe_manual(fake)
    assert probe["stale_phrase_hit_count"] == 0
    assert probe["corrected_phrase_hit_count"] == 1


@pytest.mark.skipif(
    not DEFAULT_MANUAL.exists(), reason="the working manual is not on this machine"
)
def test_working_manual_no_longer_asserts_the_false_negative(
    report: dict[str, object],
) -> None:
    probe = report["manual_probe"]
    assert probe["available"] is True
    assert probe["stale_phrase_hit_count"] == 0, (
        "the working manual still carries a claim the datasets contradict: "
        + json.dumps(probe["stale_phrase_hits"], ensure_ascii=False)
    )
