"""Unit tests for the identity-layer drawing-difference decision probe.

The probe decides nothing: it records the mechanical facts a rewrite decision
needs.  These tests pin those facts literally, so a silent edit to a local
SMILES string, to the identity layer or to the report shows up as a failure
instead of quietly re-baselining.  No test touches the network.
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.identity_smiles_drawing_decision import (
    FROZEN_RED_LINES,
    IDENTITY_MAP_PATH,
    REPORT_PATH,
    REWRITE_DECISION_STATUS,
    SUMMARY_PATH,
    build_full_summary,
    check,
    render_report,
    sha256_file,
)

EXPECTED_IDENTITY_MAP_SHA256 = (
    "2db76cd728090f4cfa2acc633b0582fae235cae0203acdedf4d36e7a9d68f91f"
)

PINNED_LOCAL_SMILES = {
    "FSXANJBLYFVXEU-UHFFFAOYSA-N": "CCCCCCCCN1CN(C=C1)C.Br",
    "LBHLGZNUPKUZJC-UHFFFAOYSA-N": "CCCC[N+]1(C)CCCC1.N#C[N-]C#N",
    "OHLUUHNLEMFGTQ-UHFFFAOYSA-N": "CN=C(C)O",
    "OOKUTCYPKPJYFV-UHFFFAOYSA-N": "Br.Cn1ccnc1",
    "ZHNUHDYFZUAESO-UHFFFAOYSA-N": "N=CO",
}

PINNED_FROZEN_CARRIERS = 4


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    assert SUMMARY_PATH.exists(), "the probe summary is not on disk"
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_probe_is_offline_and_trains_nothing(summary: dict[str, Any]) -> None:
    telemetry = summary["run_telemetry"]
    assert telemetry["network_calls"] == 0
    assert telemetry["models_fitted"] == 0
    assert telemetry["r2_reported"] is False
    assert telemetry["writes_under_data"] == 0


def test_counts_match_the_pinned_identity_layer(summary: dict[str, Any]) -> None:
    counts = summary["counts"]
    assert counts["identity_rows"] == 314
    assert counts["smiles_match"] == 299
    assert counts["differing_keys_total"] == 15
    assert counts["stereo_only"] == 10
    assert counts["structural"] == 5
    assert counts["structural_in_frozen_red_line_source"] == PINNED_FROZEN_CARRIERS
    assert counts["structural_in_derived_table"] == 1
    assert counts["structural_authored_in_identity_layer"] == 0


def test_the_five_local_smiles_are_pinned(summary: dict[str, Any]) -> None:
    observed = {
        item["inchikey"]: item["local_smiles"]
        for item in summary["structural_differences"]
    }
    assert observed == PINNED_LOCAL_SMILES


def test_every_pair_is_identity_identical(summary: dict[str, Any]) -> None:
    for item in summary["structural_differences"]:
        assert item["identity_check"] == "roundtrip_match", item["inchikey"]
        assert item["pubchem_inchikey"] == item["inchikey"]
        assert item["identity_identical"] is True
        assert item["copied_verbatim_into_the_identity_layer"] is True


def test_the_local_strings_are_copies_from_declared_sources(summary: dict[str, Any]) -> None:
    for item in summary["structural_differences"]:
        assert item["carrier_files"], item["inchikey"]
        if item["frozen_carrier_files"]:
            assert item["source_authority"] == "frozen_red_line"
            for rel in item["frozen_carrier_files"]:
                assert rel in FROZEN_RED_LINES
        else:
            assert item["source_authority"] == "derived_table"
        assert item["difference_family"] != "unclassified", item["inchikey"]


def test_the_frozen_roster_still_carries_four_of_the_five(summary: dict[str, Any]) -> None:
    carriers = [
        item for item in summary["structural_differences"] if item["frozen_carrier_files"]
    ]
    assert len(carriers) == PINNED_FROZEN_CARRIERS
    assert all(
        "data/dielectric_v03.csv" in item["frozen_carrier_files"] for item in carriers
    )


def test_all_five_gates_pass(summary: dict[str, Any]) -> None:
    gates = summary["gates"]
    assert sorted(gates) == [
        "A_identity_identical",
        "B_copied_never_authored",
        "C_frozen_sources_still_carry_the_string",
        "D_nothing_rewritten",
        "E_drawing_form_feeds_geometry",
    ]
    for name, gate in gates.items():
        assert gate["passed"] is True, name


def test_the_decision_is_registered_as_a_recommendation(summary: dict[str, Any]) -> None:
    decision = summary["decision"]
    assert decision["status"] == REWRITE_DECISION_STATUS
    assert decision["status"] == "recommended_no_rewrite_awaiting_human_confirmation"
    assert decision["no_data_change_made"] is True
    assert len(decision["reasons"]) == 4
    assert "作者" in decision["decision_owner"]


def test_geometry_derived_features_pin_four_keys(summary: dict[str, Any]) -> None:
    census = summary["geometry_derived_feature_census"]
    assert census["n_keys_with_geometry_derived_features"] == 4
    assert sorted(census["keys_with_geometry_derived_features"]) == [
        "LBHLGZNUPKUZJC-UHFFFAOYSA-N",
        "OHLUUHNLEMFGTQ-UHFFFAOYSA-N",
        "OOKUTCYPKPJYFV-UHFFFAOYSA-N",
        "ZHNUHDYFZUAESO-UHFFFAOYSA-N",
    ]


def test_the_report_is_render_of_the_summary(summary: dict[str, Any]) -> None:
    assert REPORT_PATH.read_text(encoding="utf-8") == render_report(summary)


def test_pinned_inputs_still_match_the_disk(summary: dict[str, Any]) -> None:
    for rel, meta in summary["inputs"].items():
        assert sha256_file(REPOSITORY_ROOT / rel) == meta["sha256"], rel
    assert sha256_file(IDENTITY_MAP_PATH) == EXPECTED_IDENTITY_MAP_SHA256


def test_check_reproduces_with_the_socket_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_socket(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the decision probe must never open a socket")

    monkeypatch.setattr(socket, "socket", _no_socket)
    monkeypatch.setattr(urllib.request, "urlopen", _no_socket)
    assert check() == []


def test_the_summary_recomputes_to_itself() -> None:
    on_disk = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    fresh = build_full_summary()
    left = {key: value for key, value in on_disk.items() if key != "run_telemetry"}
    right = {key: value for key, value in fresh.items() if key != "run_telemetry"}
    assert left == right
