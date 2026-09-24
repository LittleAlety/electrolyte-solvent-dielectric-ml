from __future__ import annotations

import json
from pathlib import Path

import pytest

from probes.g1plus_nist_webbook_probe import (
    INCHIKEY_IN_PAGE,
    probe_compound,
    property_hits,
)
from probes.g1plus_pubchem_probe import _dielectric_mentions

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _section(heading: str, text: str) -> dict[str, object]:
    return {
        "TOCHeading": heading,
        "Information": [{"Value": {"String": text}}],
    }


# --- PubChem: a value is only a value when a number is attached ---------------


def test_pubchem_keeps_temperatures_out_of_the_dielectric_values() -> None:
    mentions = _dielectric_mentions(
        _section(
            "Other Experimental Properties",
            "dielectric constant = 42.0 at 0 \u00b0C, 38.8 at 20 \u00b0C, "
            "26.2 at 81.6 \u00b0C.",
        )
    )

    assert len(mentions) == 1
    assert mentions[0]["values"] == pytest.approx([42.0, 38.8, 26.2])
    assert [m["temperature_C"] for m in mentions[0]["measurements"]] == pytest.approx(
        [0.0, 20.0, 81.6]
    )


def test_pubchem_bare_value_without_temperature_is_kept() -> None:
    mentions = _dielectric_mentions(
        _section("Other Experimental Properties", "Heat of fusion: 11.44 kJ/kg; dielectric constant: 43.3")
    )

    assert mentions[0]["values"] == pytest.approx([43.3])
    assert mentions[0]["measurements"][0]["temperature_C"] is None


def test_pubchem_kelvin_temperature_is_not_a_second_value() -> None:
    mentions = _dielectric_mentions(
        _section("Other Experimental Properties", "dielectric constant: 32.2 at 298 K")
    )

    assert mentions[0]["values"] == pytest.approx([32.2])
    assert mentions[0]["measurements"][0]["temperature"] == pytest.approx(298.0)
    assert mentions[0]["measurements"][0]["temperature_unit"] == "K"
    assert mentions[0]["measurements"][0]["temperature_C"] is None
    assert mentions[0]["unparsed_segments"] == []


def test_pubchem_frequency_note_is_not_a_second_value() -> None:
    mentions = _dielectric_mentions(
        _section("Other Experimental Properties", "dielectric constant: 78.4 at 25 C (1 kHz)")
    )

    assert mentions[0]["values"] == pytest.approx([78.4])
    assert mentions[0]["measurements"][0]["temperature_C"] == pytest.approx(25.0)
    assert mentions[0]["measurements"][0]["note"] == "1 kHz"


def test_pubchem_frequency_only_clause_keeps_one_value() -> None:
    mentions = _dielectric_mentions(
        _section("Other Experimental Properties", "dielectric constant: 10.2 (at 1 MHz)")
    )

    assert mentions[0]["values"] == pytest.approx([10.2])
    assert mentions[0]["measurements"][0]["note"] == "at 1 MHz"


def test_pubchem_unparseable_numeric_clause_is_flagged_not_filed() -> None:
    mentions = _dielectric_mentions(
        _section("Other Experimental Properties", "dielectric constant: ca. 43.3 +- 0.2")
    )

    assert mentions[0]["values"] == []
    assert mentions[0]["unparsed_segments"] == ["ca. 43.3 +- 0.2"]


def test_pubchem_committed_evidence_has_no_unparsed_numeric_clause() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "probes" / "g1plus_pubchem_evidence.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["summary"]["with_unparsed_numeric_clause"] == []
    assert payload["summary"]["with_standard_dielectric_value"] == ["sulfolane", "acetonitrile"]


def test_pubchem_sentence_final_period_does_not_break_parsing() -> None:
    mentions = _dielectric_mentions(
        _section(
            "Other Experimental Properties",
            "dielectric constant = 42.0 at 0 \u00b0C, 38.8 at 20 \u00b0C, "
            "26.2 at 81.6 \u00b0C.",
        )
    )

    assert mentions[0]["unparsed_segments"] == []
    assert mentions[0]["values"] == pytest.approx([42.0, 38.8, 26.2])


def test_pubchem_prose_mention_is_not_a_value() -> None:
    mentions = _dielectric_mentions(
        _section(
            "Formulations/Preparations",
            "...purified ethylene carbonate for dielectric constant and dipole moment "
            "studies by fractional distillation at reduced pressure and fractional "
            "crystallizations from dry ethyl ether.",
        )
    )

    assert mentions[0]["values"] == []
    assert mentions[0]["clause"] == ""


def test_pubchem_springer_heading_is_not_a_value() -> None:
    mentions = _dielectric_mentions(_section("SpringerMaterials Properties", "Dielectric constant"))

    assert mentions[0]["values"] == []


def test_committed_pubchem_evidence_counts_riddick_citations_once() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "probes" / "g1plus_pubchem_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    by_name = {record["name"]: record for record in payload["records"]}
    ethylene_carbonate = by_name["ethylene carbonate"]

    # The cached PUG-View record carries 20 Riddick citation strings: ten at
    # p. 989 and ten at p. 990. Walking nested sections would multiply this.
    assert ethylene_carbonate["riddick_reference_occurrences"] == 20
    assert len(ethylene_carbonate["riddick_distinct_references"]) == 2
    assert [reference[-6:] for reference in ethylene_carbonate["riddick_distinct_references"]] == [
        "p. 989",
        "p. 990",
    ]


def test_committed_pubchem_evidence_splits_values_from_links() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "probes" / "g1plus_pubchem_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    summary = payload["summary"]

    assert summary["with_standard_dielectric_value"] == ["sulfolane", "acetonitrile"]
    assert summary["with_narrative_mention_only"] == ["ethylene carbonate"]
    assert len(summary["with_springer_materials_dielectric_link"]) == 9
    assert summary["without_any_dielectric_evidence"] == [
        "propylene carbonate",
        "vinylene carbonate",
        "fluoroethylene carbonate",
        "gamma-valerolactone",
        "3-methoxypropionitrile",
    ]

    by_name = {record["name"]: record for record in payload["records"]}
    assert [m["value"] for m in by_name["sulfolane"]["standard_values"][0]["measurements"]] == [
        43.3
    ]
    acetonitrile = [
        m for hit in by_name["acetonitrile"]["standard_values"] for m in hit["measurements"]
    ]
    assert [m["value"] for m in acetonitrile] == pytest.approx([38.8, 42.0, 38.8, 26.2])
    assert [m["temperature_C"] for m in acetonitrile] == pytest.approx([20.0, 0.0, 20.0, 81.6])


def test_every_pubchem_standard_value_really_carries_a_number() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "probes" / "g1plus_pubchem_evidence.json").read_text(
            encoding="utf-8"
        )
    )

    for record in payload["records"]:
        for hit in record.get("standard_values", []):
            assert hit["values"], record["name"]
            for measurement in hit["measurements"]:
                assert 0 < measurement["value"] < 200
        for hit in record.get("narrative_hits", []):
            assert hit["values"] == [], record["name"]
        for link in record.get("springer_dielectric_links", []):
            assert link["substance_id"].startswith("smsid_")


# --- NIST WebBook: identity gate and structural negative ---------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_webbook_identity_gate_skips_a_name_collision(tmp_path: Path) -> None:
    key = "XLYOFNOQVPJJNP-UHFFFAOYSA-N"
    _write(tmp_path / "search_water.html", "cbook.cgi?ID=C1111111 cbook.cgi?ID=C7732185")
    _write(
        tmp_path / "compound_C1111111.html",
        '{"inChIKey" : "AAAAAAAAAAAAAA-UHFFFAOYSA-N"}',
    )
    _write(tmp_path / "compound_C7732185.html", '{"inChIKey" : "' + key + '"}')

    record = probe_compound("water", key, "positive control", tmp_path)

    assert record["status"] == "resolved"
    assert record["webbook_id"] == "C7732185"
    assert record["identity_checked"] == [
        {"id": "C1111111", "page_inchikey": "AAAAAAAAAAAAAA-UHFFFAOYSA-N"},
        {"id": "C7732185", "page_inchikey": key},
    ]


def test_webbook_identity_gate_rejects_when_nothing_matches(tmp_path: Path) -> None:
    _write(tmp_path / "search_water.html", "cbook.cgi?ID=C1111111")
    _write(
        tmp_path / "compound_C1111111.html",
        '{"inChIKey" : "AAAAAAAAAAAAAA-UHFFFAOYSA-N"}',
    )

    record = probe_compound("water", "XLYOFNOQVPJJNP-UHFFFAOYSA-N", "control", tmp_path)

    assert record["status"] == "name_unresolved_or_identity_mismatch"
    assert record["page_inchikey"] == ""
    assert sum(record["property_hits"].values()) == 0


def test_webbook_property_test_counts_body_text_not_only_headings() -> None:
    html = (
        "<h2>Notes</h2><p>Dielectric constant 78.4, permittivity, "
        "epsilon, and the symbol \u03b5</p>"
    )

    assert property_hits(html) == {
        "dielectric": 1,
        "permittivity": 1,
        "epsilon": 1,
        "\u03b5": 1,
    }


def test_webbook_page_inchikey_regex_requires_a_full_key() -> None:
    assert INCHIKEY_IN_PAGE.search('"inChIKey" : "XLYOFNOQVPJJNP-UHFFFAOYSA-N"')
    assert not INCHIKEY_IN_PAGE.search('"inChIKey" : "XLYOFNOQVPJJNP"')
    assert not INCHIKEY_IN_PAGE.search('"inchi" : "1S/H2O/h1H2"')


def test_committed_webbook_evidence_is_a_structural_negative() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "probes" / "g1plus_nist_webbook_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    summary = payload["summary"]

    assert summary["targets_with_dielectric_facet"] == []
    assert summary["controls_with_dielectric_facet"] == []
    assert summary["targets_unresolved"] == ["fluoroethylene carbonate"]
    assert len(summary["targets_resolved"]) == 13
    assert len(summary["targets_resolved"]) + len(summary["targets_unresolved"]) == summary[
        "target_count"
    ] == len(payload["summary"]["targets_resolved"]) + 1

    for record in payload["records"]:
        if record["status"] == "resolved":
            assert record["page_inchikey"] == record["expected_inchikey"]
        assert sum(record["property_hits"].values()) == 0

    assert payload["method"]["unsupported_query_form"]["http_status"] == 400
    assert payload["method"]["unsupported_query_form"]["accepted"] is False
