"""Regression tests for the G1+ crawl round-5 evidence.

The round's headline claims are re-derivable from the working tree, so they are
asserted here rather than only narrated: the two primary-measurement closures
(FEC 78.4 at 23 C, vinylene carbonate 126 +/- 1.0 at 25 C), the round-4 Flamme
claim being extended rather than reversed, the same-source versus independent
split across the
restricted captures, the pressure window, the catalog coverage gap, and the
no-cell-changed statement.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT

EVIDENCE = REPOSITORY_ROOT / "probes" / "g1plus_crawl_round5_evidence.json"
CROSSCHECK = REPOSITORY_ROOT / "probes" / "g1plus_round5_crosscheck_summary.json"
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
RAW = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def crosscheck() -> dict[str, object]:
    return json.loads(CROSSCHECK.read_text(encoding="utf-8"))


def _gate(evidence: dict[str, object], gate_id: str) -> dict[str, object]:
    return next(
        gate for gate in evidence["gate_results"] if gate["gate_id"] == gate_id
    )


def _entry(crosscheck: dict[str, object], inchikey: str) -> dict[str, object]:
    return next(
        entry for entry in crosscheck["results"] if entry["inchikey"] == inchikey
    )


def test_the_round_changed_no_canonical_cell(evidence, crosscheck) -> None:
    impact = evidence["dataset_impact"]
    assert impact["changed_fields"] == []
    live = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert impact["canonical_sha256"] == live
    assert crosscheck["dataset_sha256"] == live
    assert crosscheck["raw_sha256"] == hashlib.sha256(RAW.read_bytes()).hexdigest()
    assert impact["rows"] == len(_rows(DATASET))


def test_the_fec_78_4_leg_is_closed_against_a_primary_measurement(evidence) -> None:
    gate = _gate(evidence, "fec_78_4_leg_primary_source")
    assert gate["verdict"] == "closed_at_primary_measurement_level"
    assert gate["value"] == 78.4
    assert gate["temperature_c"] == 23
    assert gate["table"] == "Table 2"
    assert gate["provenance_marker"] == "Our data"
    assert "10.1016/S0022-1139(02)00317-2" in gate["answer"]
    # The companion values are what tie the Kobayashi row to Flamme entry 21.
    assert gate["companion_values_in_same_row"] == {
        "bp_c": 210,
        "mp_c": 17.3,
        "density_kg_m3": 1497,
        "viscosity_mPa_s": 4.1,
        "conductivity_S_m": 1.04,
    }
    # The 2 K offset between the stored temperature and the measurement is
    # recorded rather than rounded away.
    assert "296.15" in gate["temperature_boundary"]


def test_the_round_four_flamme_claim_is_extended_not_reversed(evidence) -> None:
    gate = _gate(evidence, "fec_78_4_leg_primary_source")
    correction = gate["round4_correction"]
    # Round 4 is not retracted: it correctly said Flamme was not established as
    # the primary measurement. Round 5 only adds the next layer.
    assert "correctly" in correction
    assert "next layer rather than a reversal" in correction
    assert "not established" in correction
    assert "78.4" in correction
    # The compilation and the measurement must not be conflated.
    assert "still not the measurement" in correction


def test_the_vinylene_carbonate_leg_is_closed_with_an_uncertainty(evidence) -> None:
    gate = _gate(evidence, "vinylene_carbonate_dielectric_value")
    assert gate["verdict"] == "closed_at_primary_measurement_level"
    assert gate["value"] == 126
    assert gate["uncertainty"] == 1.0
    assert gate["temperature_c"] == 25
    assert gate["table"] == "Table 2"
    assert "10.1039/j29660000005" in gate["answer"]
    assert gate["cross_check_rows_in_the_same_table"]["propylene_carbonate"][
        "dielectric"
    ] == 61.0


def test_the_reaxys_index_carried_the_citation_but_no_number(evidence) -> None:
    gate = _gate(evidence, "reaxys_index_mapping_before_the_pdf_arrived")
    assert gate["verdict"] == "the_licensed_index_carried_the_citation_but_no_number"
    assert "Saadi" in gate["answer"]
    assert "no numeric value" in gate["answer"]


def test_the_fec_107_leg_is_still_recorded_as_blocked(evidence) -> None:
    gate = _gate(evidence, "fec_107_leg")
    assert gate["verdict"] == "still_blocked"
    assert gate["candidate_values_unresolved"] == [78.4, 107]


def test_same_source_confirmation_is_not_dressed_up_as_independent_agreement(
    evidence, crosscheck
) -> None:
    gate = _gate(evidence, "restricted_source_priority_crosscheck")
    live_counts: dict[str, int] = {}
    for entry in crosscheck["results"]:
        label = entry["source_relationship"]
        live_counts[label] = live_counts.get(label, 0) + 1
    assert gate["relationship_counts"] == live_counts
    assert crosscheck["relationship_counts"] == live_counts

    # The two dinitriles are the same-source pair, and the shared DOI is the
    # very one the dataset row rests on.
    dataset_dois = {
        row["inchikey"]: row["source_doi"] for row in _rows(DATASET)
    }
    same_source = {
        entry["inchikey"]
        for entry in crosscheck["results"]
        if entry["source_relationship"] == "same_source_confirmation"
    }
    assert same_source == {
        "BTGRAWJCKBQKAO-UHFFFAOYSA-N",
        "ZTOMUSMDRMJOTH-UHFFFAOYSA-N",
    }
    for inchikey in same_source:
        entry = _entry(crosscheck, inchikey)
        assert entry["smi_reference_labels"] == entry["dataset_source_labels"]
        assert dataset_dois[inchikey] == "10.1021/je300958c"

    independent = {
        entry["inchikey"]
        for entry in crosscheck["results"]
        if entry["source_relationship"] == "independent_sources_only"
    }
    assert independent == {
        "ZUHZGEOKBKGPSW-UHFFFAOYSA-N",  # 2,5,8,11,14-pentaoxapentadecane
        "WYURNTSHIVDZCO-UHFFFAOYSA-N",  # tetrahydrofuran
        "SECXISVLQFMRJM-UHFFFAOYSA-N",  # N-methylpyrrolidone
    }


def test_the_pressure_gate_keeps_pressurised_rows_out(crosscheck) -> None:
    assert crosscheck["ambient_pressure_window_kPa"] == [90.0, 110.0]
    excluded = {
        entry["inchikey"]: entry["smi_pressurised_rows_excluded"]
        for entry in crosscheck["results"]
        if entry["smi_pressurised_rows_excluded"]
    }
    assert excluded == {"SECXISVLQFMRJM-UHFFFAOYSA-N": 5}
    nmp = _entry(crosscheck, "SECXISVLQFMRJM-UHFFFAOYSA-N")
    assert nmp["smi_near_rows"] == 5


def test_the_reported_targets_are_identity_gated_against_the_dataset(
    evidence, crosscheck
) -> None:
    shipped = {row["inchikey"] for row in _rows(DATASET)}
    assert len(crosscheck["results"]) == 16
    for entry in crosscheck["results"]:
        assert entry["inchikey"] in shipped
        assert entry["dataset_present"] is True
    assert crosscheck["results"], "the target roster must not be empty"


def test_the_catalog_coverage_gap_is_recorded_not_papered_over(crosscheck) -> None:
    present_but_uncaptured = {
        entry["inchikey"]: entry["catalog_doc_ids"]
        for entry in crosscheck["results"]
        if entry["catalog_present"] and entry["smi_near_rows"] == 0
    }
    assert present_but_uncaptured == {
        "KMTRUDSVKNLOMY-UHFFFAOYSA-N": ["SMI_SC_31657"],  # ethylene carbonate
        "GAEKPEKOJKCEMS-UHFFFAOYSA-N": ["SMI_SC_31853"],  # gamma-valerolactone
        "XTHFKEDIFFGKHM-UHFFFAOYSA-N": ["SMI_SC_31827"],  # 1,2-dimethoxyethane
        "HXJUTPCZVOIRIF-UHFFFAOYSA-N": ["SMI_SC_31784"],  # sulfolane
    }
    missing_from_catalog = {
        entry["inchikey"]
        for entry in crosscheck["results"]
        if not entry["catalog_present"]
    }
    assert missing_from_catalog == {
        "OOWFYDWAMOKVSF-UHFFFAOYSA-N",  # 3-methoxypropionitrile
        "VAYTZRYEBVHVLE-UHFFFAOYSA-N",  # vinylene carbonate
        "SBLRHMKNNHXPHG-UHFFFAOYSA-N",  # fluoroethylene carbonate
        "YFNKIDBQEZZDLK-UHFFFAOYSA-N",  # 2,5,8,11-tetraoxadodecane
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N",  # propylene carbonate
        "WEVYAHXRMPXWCK-UHFFFAOYSA-N",  # acetonitrile
    }


def test_the_two_ready_patches_target_the_right_rows(evidence) -> None:
    backlog = " ".join(evidence["backlog"])
    assert "SBLRHMKNNHXPHG-UHFFFAOYSA-N" in backlog
    assert "VAYTZRYEBVHVLE-UHFFFAOYSA-N" in backlog
    assert "dielectric 102 -> 78.4" in backlog
    assert "10.1039/j29660000005" in backlog
    # Neither patch may touch model_ready, because that would move the frozen
    # fitting subset rather than fix a provenance field.
    assert "model_ready stays false" in backlog
    assert "modelling decision" in backlog


def test_the_tracked_crosscheck_is_reproducible_from_the_working_tree(
    crosscheck,
) -> None:
    from probes import g1plus_round5_crosscheck as probe

    # Shape checks on the committed artefact. These run unconditionally so the
    # tracked summary is still guarded in CI, where the restricted
    # SpringerMaterials capture is absent and the rebuild below is skipped.
    assert crosscheck["dataset_sha256"] == (
        "765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60"
    )
    assert crosscheck["max_delta_temperature_K"] == 5.0
    assert crosscheck["ambient_pressure_window_kPa"] == [90.0, 110.0]
    assert crosscheck["redistribution_status"] == "aggregates_only"
    assert len(crosscheck["results"]) == 16
    assert sum(crosscheck["relationship_counts"].values()) == 16
    known = {
        "same_source_confirmation",
        "independent_sources_only",
        "mixed_same_and_independent",
        "no_capture",
    }
    for entry in crosscheck["results"]:
        assert entry["source_relationship"] in known
        assert len(entry["inchikey"]) == 27

    if not probe.load_restricted_observations():
        pytest.skip("the restricted SpringerMaterials capture is not on this machine")

    rebuilt = probe.build_crosscheck(
        probe.load_dataset_rows(),
        probe._read_csv(probe.RAW),
        probe.load_restricted_observations(),
        probe.load_catalog(),
        max_delta_temperature=crosscheck["max_delta_temperature_K"],
    )
    tracked = {
        entry["inchikey"]: (
            entry["source_relationship"],
            entry["smi_near_rows"],
            entry["smi_pressurised_rows_excluded"],
            entry["dataset_present"],
        )
        for entry in crosscheck["results"]
    }
    live = {
        entry["inchikey"]: (
            entry["source_relationship"],
            entry["smi_near_rows"],
            entry["smi_pressurised_rows_excluded"],
            entry["dataset_present"],
        )
        for entry in rebuilt
    }
    assert live == tracked
