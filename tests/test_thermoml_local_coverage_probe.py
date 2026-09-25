from __future__ import annotations

import glob

import pytest

from probes.thermoml_local_coverage_probe import (
    REPOSITORY_ROOT,
    TARGETS,
    THERMOML_GLOB,
    build_summary,
    classify,
    component_indices,
    parse_components,
    scan_corpus,
)


def test_parse_components_handles_empty_and_bad_json() -> None:
    assert parse_components({}) == []
    assert parse_components({"components_json": ""}) == []
    assert parse_components({"components_json": "{not json"}) == []


def test_parse_components_reads_the_standard_inchi_key_field() -> None:
    row = {
        "components_json": (
            '[{"name": "water", "standard_inchi_key": "XLYOFNOQVPJJNP-UHFFFAOYSA-N"}]'
        )
    }

    parsed = parse_components(row)

    assert len(parsed) == 1
    assert parsed[0]["standard_inchi_key"] == "XLYOFNOQVPJJNP-UHFFFAOYSA-N"


def test_component_indices_splits_pure_from_mixture() -> None:
    rows = [
        {
            "components_json": (
                '[{"standard_inchi_key": "AAAA"}, {"standard_inchi_key": "BBBB"}]'
            ),
            "is_pure": "False",
            "property_family": "zero_frequency",
        },
        {
            "components_json": '[{"standard_inchi_key": "AAAA"}]',
            "is_pure": "True",
            "property_family": "zero_frequency",
        },
    ]

    counts = component_indices(rows)

    assert counts["AAAA"]["extracted_observations"] == 2
    assert counts["AAAA"]["extracted_pure_observations"] == 1
    assert counts["BBBB"].get("extracted_pure_observations", 0) == 0
    assert counts["BBBB"]["extracted_observations"] == 1


def test_classify_reports_the_three_negative_verdicts() -> None:
    present = {"extracted_observations": 3}
    assert classify({}, present) == (True, "locally_supported")

    absent = {
        "xml_files_mentioning_inchikey": 0,
        "xml_files_mentioning_cas": 0,
        "xml_files_mentioning_alias": 0,
        "xml_files_with_permittivity_text": 0,
    }
    assert classify(absent, {}) == (False, "absent_from_local_corpus")

    non_dielectric = {
        "xml_files_mentioning_inchikey": 26,
        "xml_files_mentioning_cas": 0,
        "xml_files_mentioning_alias": 0,
        "xml_files_with_permittivity_text": 0,
    }
    assert classify(non_dielectric, {}) == (
        False,
        "mentioned_only_in_non_dielectric_studies",
    )

    wording_only = dict(non_dielectric, xml_files_with_permittivity_text=2)
    assert classify(wording_only, {}) == (
        False,
        "permittivity_wording_present_but_no_extracted_observation",
    )


def test_scan_corpus_detects_inchikey_cas_and_alias(tmp_path) -> None:
    xml = tmp_path / "sample.xml"
    xml.write_text(
        "study of propylene carbonate CAS 108-32-7 key "
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N relative permittivity",
        encoding="utf-8",
    )
    target = {
        "label": "propylene carbonate",
        "aliases": ("propylene carbonate",),
        "cas": ("108-32-7",),
        "inchikey": "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    }

    hits = scan_corpus([xml], [target])

    counters = hits["propylene carbonate"]
    assert counters["xml_files_mentioning_inchikey"] == 1
    assert counters["xml_files_mentioning_cas"] == 1
    assert counters["xml_files_with_permittivity_text"] == 1


CORPUS_AVAILABLE = bool(
    glob.glob(str(REPOSITORY_ROOT / THERMOML_GLOB), recursive=True)
)


@pytest.mark.skipif(
    not CORPUS_AVAILABLE,
    reason="the git-ignored local ThermoML XML corpus is unavailable",
)
def test_real_corpus_reproduces_the_tier0_split(tmp_path) -> None:
    payload = build_summary(
        summary_path=tmp_path / "summary.json", rows_path=tmp_path / "rows.csv"
    )

    assert payload["inputs"]["xml_files_scanned"] == 242
    assert payload["inputs"]["extraction_rows"] == 11_646
    assert payload["summary"]["n_targets"] == len(TARGETS) == 10
    assert payload["summary"]["n_locally_supported"] == 5
    assert payload["summary"]["unsupported_labels"] == [
        "propylene carbonate",
        "ethylene carbonate",
        "vinylene carbonate",
        "fluoroethylene carbonate",
        "3-methoxypropionitrile",
    ]
    by_label = {row["label"]: row for row in payload["targets"]}
    # PC is named in many mixture studies but never measured dielectrically.
    assert by_label["propylene carbonate"]["xml_files_mentioning_inchikey"] == 26
    assert by_label["propylene carbonate"]["xml_files_with_permittivity_text"] == 0
    assert by_label["propylene carbonate"]["extracted_observations"] == 0
    # The glymes and the two dinitriles really do carry local pure observations.
    assert by_label["triglyme"]["extracted_pure_observations"] == 15
    assert by_label["adiponitrile"]["extracted_pure_observations"] == 31
