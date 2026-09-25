"""Regression tests for the J-STAGE route check and the free PC/EC corroboration.

Two claims are re-derived here rather than only narrated: that the Hagiyama 2008
premise (a free J-STAGE full text) is falsified at identifier level, and that the
two restricted-catalog targets PC and EC are corroborated by an open-access
literal whose stored values still match the canonical dataset.
"""

from __future__ import annotations

import csv
import hashlib
import json

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT

EVIDENCE = REPOSITORY_ROOT / "probes" / "jstage_corroboration_evidence.json"
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"


def _rows() -> dict[str, dict[str, str]]:
    with DATASET.open(encoding="utf-8", newline="") as handle:
        return {row["name"]: row for row in csv.DictReader(handle)}


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_the_probe_changed_no_canonical_cell(evidence) -> None:
    impact = evidence["dataset_impact"]
    live = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert impact["changed_fields"] == []
    assert impact["canonical_sha256"] == live
    assert impact["rows"] == len(_rows())


def test_the_jstage_premise_is_recorded_as_falsified(evidence) -> None:
    gate = evidence["access_gate"]
    assert gate["doi"] == "10.1246/cl.2008.210"
    assert gate["verdict"] == "falsified"
    sources = " ".join(item["source"] for item in gate["evidence"])
    for required in ("OpenAlex", "Crossref", "DOI resolver", "J-STAGE"):
        assert required in sources, sources


def test_every_recorded_jstage_probe_is_a_404(evidence) -> None:
    probe = next(
        item for item in evidence["access_gate"]["evidence"]
        if item["source"] == "direct J-STAGE probes"
    )
    assert len(probe["observed"]) == 4
    assert all("HTTP 404" in line for line in probe["observed"]), probe["observed"]
    # The journal root is probed as well as the article, so the negative is not
    # an artefact of one wrong article identifier.
    assert any("browse/cl" in line for line in probe["observed"])


def test_openalex_recorded_this_work_as_closed_with_no_repository_copy(evidence) -> None:
    item = next(
        entry for entry in evidence["access_gate"]["evidence"]
        if entry["source"] == "OpenAlex REST"
    )
    observed = item["observed"]
    assert "is_oa=false" in observed
    assert "oa_status=closed" in observed
    assert "any_repository_has_fulltext=false" in observed


@pytest.mark.parametrize(
    ("name", "deposit", "temperature_c"),
    [
        ("propylene carbonate", 64.92, 25),
        ("ethylene carbonate", 89.78, 40),
    ],
)
def test_corroborated_values_agree_with_the_live_dataset(
    evidence, name, deposit, temperature_c
) -> None:
    target = next(t for t in evidence["corroboration_gate"]["targets"] if t["compound"] == name)
    row = _rows()[name]
    assert target["inchikey"] == row["inchikey"]
    # The stored side must still be the live canonical value, not a transcription.
    assert target["stored"]["value"] == float(row["dielectric"])
    assert target["stored"]["T_K"] == float(row["T_K"])
    assert target["corroborating"]["value"] == deposit
    assert target["corroborating"]["T_C"] == temperature_c
    assert target["temperature_aligned"] is True
    assert target["verdict"] == "corroborated"

    expected_abs = abs(float(row["dielectric"]) - deposit)
    assert target["absolute_deviation"] == round(expected_abs, 4)
    expected_rel = round(expected_abs / deposit * 100, 4)
    assert target["relative_deviation_percent"] == expected_rel


def test_the_corroboration_chain_names_riddick_as_its_own_source(evidence) -> None:
    chain = evidence["corroboration_gate"]["chain"]
    assert "10.5796/electrochemistry.75.607" == chain["open_literal"]["doi"]
    assert "Riddick" in chain["upstream"]["verbatim"]
    assert "1986" in chain["upstream"]["verbatim"]
    # Both figures are attributed to the same upstream reference in the literal.
    literal = chain["open_literal"]["verbatim"]
    assert "64.92 at 25 C" in literal
    assert "89.78 at 40 C" in literal


def test_the_two_uncorroborated_restricted_targets_are_still_named(evidence) -> None:
    named = {item["target"] for item in evidence["corroboration_gate"]["not_corroborated"]}
    assert named == {"GVL", "DME"}


def test_the_fec_leg_is_recorded_as_still_open(evidence) -> None:
    status = evidence["fec_107_leg_status_after_this_probe"]
    assert "still open" in status.lower()
    assert "model_ready=false" in status
