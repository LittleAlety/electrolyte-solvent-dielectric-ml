"""Regression tests for the G1+ crawl round-4 evidence.

The round's headline claims are all re-derivable from the working tree, so they
are asserted here rather than only narrated: the ThermoML normalisation gap, the
identity gate on the ten targets, the DC-200 "unknown, not zero" verdict, the
Saadi identifier correction, and the no-cell-changed statement.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT

EVIDENCE = REPOSITORY_ROOT / "probes" / "g1plus_crawl_round4_evidence.json"
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
ALIASES = REPOSITORY_ROOT / "data" / "reference" / "dielectric_molecule_aliases.csv"
NORMALIZED_PROVENANCE = (
    REPOSITORY_ROOT / "data" / "processed" / "thermoml_normalized.provenance.json"
)
NORMALIZED = REPOSITORY_ROOT / "data" / "processed" / "thermoml_normalized.csv"
ARCHIVE = REPOSITORY_ROOT / "data" / "raw" / "thermoml_archive" / "ThermoML.v2020-09-30.tgz"
SI_PDF = (
    REPOSITORY_ROOT
    / "data"
    / "external"
    / "g1plus"
    / "compilations"
    / "nn6c06255_si_001.pdf"
)


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _gate(evidence: dict[str, object], gate_id: str) -> dict[str, object]:
    return next(
        gate for gate in evidence["gate_results"] if gate["gate_id"] == gate_id
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_round_changed_no_canonical_cell(evidence: dict[str, object]) -> None:
    impact = evidence["dataset_impact"]
    assert impact["changed_fields"] == []
    assert impact["rows"] == 246
    live = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert impact["canonical_sha256"] == live


def test_every_reported_target_is_identity_gated_against_the_dataset(
    evidence: dict[str, object],
) -> None:
    """A transcribed InChIKey only counts if it names a shipped row and alias."""

    shipped = {row["inchikey"] for row in _rows(DATASET)}
    registry: dict[str, set[str]] = {}
    for row in _rows(ALIASES):
        registry.setdefault(row["inchikey"], set()).add(row["alias"].lower())
    targets = _gate(evidence, "thermoml_local_corpus_completeness")["per_target_10"]
    assert len(targets) == 10
    assert len({target["inchikey"] for target in targets}) == 10
    for target in targets:
        assert target["inchikey"] in shipped, (
            f"{target['name']} carries an InChIKey the dataset does not ship"
        )
        assert target["name"].lower() in registry.get(target["inchikey"], set()), (
            f"{target['name']} is not a registered alias of its InChIKey"
        )


def test_the_normalisation_gap_matches_its_own_premise(
    evidence: dict[str, object],
) -> None:
    """The gap only holds because the helper file is a five-file subset."""

    provenance = json.loads(NORMALIZED_PROVENANCE.read_text(encoding="utf-8"))
    gap = _gate(evidence, "thermoml_local_corpus_completeness")["normalized_gap"]
    assert provenance["raw_file_count"] == 5
    assert provenance["row_count"] == 625
    assert provenance["filter"] == "dielectric_only"
    assert gap["normalized_rows_matched"] == provenance["row_count"]
    assert len(_rows(NORMALIZED)) == provenance["row_count"]
    assert (
        gap["normalized_missing_rows"]
        == gap["raw_xml_rows"] - gap["normalized_rows_matched"]
    )
    assert gap["reverse_difference_rows"] == 0


def test_the_dc200_verdict_stays_unknown_rather_than_zero(
    evidence: dict[str, object],
) -> None:
    """Members not released must never be laundered into "no overlap"."""

    overlap = _gate(evidence, "dc200_availability")["overlap_with_local_246_rows"]
    assert overlap["verdict"] == "UNKNOWN"
    assert overlap["not_zero"] is True


def test_the_saadi_identifier_correction_is_recorded(
    evidence: dict[str, object],
) -> None:
    sources = _gate(evidence, "unclosed_primary_sources")["per_source"]
    saadi = next(item for item in sources if "j29660000005" in item["citation"])
    correction = saadi["identifier_correction"]
    assert "vinylene carbonate" in correction
    assert "not an adiponitrile or glutaronitrile paper" in correction


def test_request_accounting_is_consistent(evidence: dict[str, object]) -> None:
    scope = evidence["scope"]
    reported = [agent["reported_external_requests"] for agent in scope["agents"]]
    assert scope["external_http_calls_reported_total"] == sum(reported)
    assert all(
        not agent["sub_cap_breached"] for agent in scope["agents"]
    )
    assert scope["hourly_ceiling_approached"] is False


@pytest.mark.skipif(
    not ARCHIVE.exists(), reason="the ThermoML archive is git-ignored and absent"
)
def test_the_local_archive_is_not_a_usable_gzip(evidence: dict[str, object]) -> None:
    head = ARCHIVE.read_bytes()[:2]
    assert head != b"\x1f\x8b"
    archive = _gate(evidence, "thermoml_local_corpus_completeness")["archive_integrity"]
    assert archive["bytes"] == ARCHIVE.stat().st_size


@pytest.mark.skipif(not SI_PDF.exists(), reason="the SI cache is git-ignored and absent")
def test_the_dc200_si_pin_matches_the_cached_copy(
    evidence: dict[str, object],
) -> None:
    carrier = _gate(evidence, "dc200_availability")["carrier"]
    assert carrier["sha256"].lower() == hashlib.sha256(SI_PDF.read_bytes()).hexdigest()
    assert carrier["bytes"] == SI_PDF.stat().st_size
