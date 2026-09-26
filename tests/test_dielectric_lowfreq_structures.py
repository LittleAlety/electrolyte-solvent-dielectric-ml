"""Offline unit tests for the low-frequency-gate structure resolution probe.

The probe exists to turn "435 rows we can see but cannot model" into modelling
samples, so the tests concentrate on the places where a sloppy resolver would
claim more than the data supports:

- a PubChem lookup that 404s must not be dressed up as a structure, and a
  compound that only has its roster SMILES must not be claimed as "verified
  against PubChem";
- two different structures returned for one InChIKey must be recorded as
  ambiguous, not silently averaged into one;
- a formula mismatch must surface instead of being reported as a match;
- the claim "ThermoML has no zero-frequency row for this compound" must be
  derived from the raw rows, and the one shape that would mean the admission
  gate misfired must be flagged for review.

Everything runs offline: the HTTP layer is injected and every input table is a
tmp_path fixture. No test in this file opens a socket.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from probes.dielectric_lowfreq_structures import (
    AMBIGUOUS,
    CSV_FIELDS,
    NOT_QUERIED,
    RESOLVED,
    UNRESOLVED,
    PubChemRecord,
    build_absence_reason,
    build_pubchem_url,
    check_formula,
    check_inchikey_roundtrip,
    check_roster_smiles,
    derive_absence_suffix,
    distinct_structures,
    fault_message,
    format_number,
    load_accepted_compounds,
    load_feature_keys,
    load_observation_counts,
    load_raw_doi_set,
    load_roster_entries,
    main,
    parse_pubchem_payload,
    read_facts_replay,
    resolve_from_records,
    run_probe,
    scan_raw_evidence,
    write_csv,
)
from probes.ilthermo_probe import HttpResponse

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Authentic InChIKey/SMILES/formula triples, taken from the live run of this
# probe so the round-trip assertion below is a real check, not a tautology.
BENZENE = ("UHOVQNZJYSORNB-UHFFFAOYSA-N", "benzene", "c1ccccc1", "C6H6")
FURAN = ("YLQBMQCUIZJEEH-UHFFFAOYSA-N", "furan", "c1ccoc1", "C4H4O")
ACETONE = ("CSCPPACGZOOCGX-UHFFFAOYSA-N", "acetone", "CC(C)=O", "C3H6O")
BUTANEDIOL = ("WERYXYBDKMZEQL-UHFFFAOYSA-N", "1,4-butanediol", "OCCCCO", "C4H10O2")
BUTANONE = ("ZWEHNKRNPOVVGH-UHFFFAOYSA-N", "2-butanone", "CCC(C)=O", "C4H8O")
DODECANE = ("SNRUBQQJIBEYMU-UHFFFAOYSA-N", "dodecane", "CCCCCCCCCCCC", "C12H26")
HEXANAMINE = ("BMVXCPBXGZKUPN-UHFFFAOYSA-N", "1-hexanamine", "CCCCCCN", "C6H15N")
NITROBENZENE = (
    "LQNUZADURLCDLV-UHFFFAOYSA-N",
    "nitrobenzene",
    "C1=CC=C(C=C1)[N+](=O)[O-]",
    "C6H5NO2",
)
CHLOROBUTANE = ("BSPCSKHALVHRSR-UHFFFAOYSA-N", "2-chlorobutane", "CCC(C)Cl", "C4H9Cl")
FLUOROETHANE = ("UJPMYEOUBPIPHQ-UHFFFAOYSA-N", "1,1,1-trifluoroethane", "CC(F)(F)F", "C2H3F3")
METHYLFURAN = ("VQKFNUFAXTZWDK-UHFFFAOYSA-N", "2-methylfuran", "CC1=CC=CO1", "C5H6O")
PENTANOL = ("AQIXEPGDORPWBJ-UHFFFAOYSA-N", "3-pentanol", "CCC(CC)O", "C5H12O")

NBS_DOI = "10.6028/nbs.circ.514"
PRESENT_DOI = "10.1234/present"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def write_rows(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


CANDIDATE_FIELDS = ("inchikey", "name", "smiles", "T_K", "gate", "in_roster", "source_doi")
RAW_FIELDS = ("doi", "components_json", "is_pure", "property_family", "frequency_mhz")
ROSTER_FIELDS = (
    "inchikey",
    "name",
    "smiles",
    "source_doi",
    "source_scope",
    "model_ready",
    "T_K",
    "dielectric",
)


def candidate_row(
    entry: tuple[str, str, str, str],
    *,
    temperature: str,
    gate: str,
    in_roster: bool,
    smiles: str | None = None,
) -> dict[str, str]:
    key, name, default_smiles, _ = entry
    return {
        "inchikey": key,
        "name": name,
        "smiles": default_smiles if smiles is None else smiles,
        "T_K": temperature,
        "gate": gate,
        "in_roster": "true" if in_roster else "false",
        "source_doi": NBS_DOI if in_roster else "10.1234/thermoml",
    }


def raw_row(
    entry: tuple[str, str, str, str],
    *,
    family: str,
    is_pure: bool,
    frequency: str,
    doi: str = "10.1234/thermoml",
    components: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    key, name, _, formula = entry
    payload = components or [{"name": name, "formula": formula, "standard_inchi_key": key}]
    return {
        "doi": doi,
        "components_json": json.dumps(payload),
        "is_pure": "True" if is_pure else "False",
        "property_family": family,
        "frequency_mhz": frequency,
    }


@dataclass
class Fixture:
    candidates: Path
    raw: Path
    observations: Path
    features: Path
    roster: Path

    @property
    def compound_count(self) -> int:
        return 11


@pytest.fixture()
def fixture(tmp_path: Path) -> Fixture:
    candidates = tmp_path / "candidates.csv"
    primary = "accepted_primary_lowfreq"
    extended = "accepted_extended_lowfreq"
    rows = [
        candidate_row(BENZENE, temperature="293.15", gate=primary, in_roster=True),
        candidate_row(BENZENE, temperature="298.15", gate=extended, in_roster=True),
        candidate_row(FURAN, temperature="278.15", gate=extended, in_roster=True),
        candidate_row(ACETONE, temperature="298.15", gate=primary, in_roster=True),
        candidate_row(BUTANEDIOL, temperature="303.15", gate=primary, in_roster=True),
        candidate_row(BUTANONE, temperature="293.15", gate=primary, in_roster=True),
        candidate_row(DODECANE, temperature="300", gate=primary, in_roster=False, smiles=""),
        candidate_row(DODECANE, temperature="310", gate=primary, in_roster=False, smiles=""),
        candidate_row(DODECANE, temperature="320", gate=primary, in_roster=False, smiles=""),
        candidate_row(HEXANAMINE, temperature="293", gate=primary, in_roster=False, smiles=""),
        candidate_row(HEXANAMINE, temperature="298", gate=primary, in_roster=False, smiles=""),
        candidate_row(HEXANAMINE, temperature="303", gate=extended, in_roster=False, smiles=""),
        candidate_row(NITROBENZENE, temperature="293.15", gate=primary, in_roster=False, smiles=""),
        candidate_row(NITROBENZENE, temperature="313.15", gate=primary, in_roster=False, smiles=""),
        candidate_row(CHLOROBUTANE, temperature="283.15", gate=primary, in_roster=False, smiles=""),
        candidate_row(FLUOROETHANE, temperature="218.12", gate=primary, in_roster=False, smiles=""),
        candidate_row(METHYLFURAN, temperature="278.15", gate=primary, in_roster=False, smiles=""),
        # Rejected by the frequency gate: must never enter the population, and
        # must never consume a PubChem request.
        candidate_row(
            PENTANOL, temperature="298.15", gate="rejected_highfreq", in_roster=False, smiles=""
        ),
    ]
    write_rows(candidates, CANDIDATE_FIELDS, rows)

    raw = tmp_path / "raw.csv"
    # Benzene's only zero-frequency rows are binary mixtures, so the pure-only
    # admission gate correctly refuses them.
    benzene_mix = [
        {"name": "benzene", "formula": "C6H6", "standard_inchi_key": BENZENE[0]},
        {
            "name": "methanol",
            "formula": "CH4O",
            "standard_inchi_key": "OKKJLVBELUTLKV-UHFFFAOYSA-N",
        },
    ]
    raw_rows = [
        raw_row(
            BENZENE, family="zero_frequency", is_pure=False, frequency="0", components=benzene_mix
        ),
        raw_row(
            BENZENE, family="zero_frequency", is_pure=False, frequency="0", components=benzene_mix
        ),
        raw_row(BENZENE, family="frequency_dependent", is_pure=True, frequency="0.01"),
        raw_row(FURAN, family="frequency_dependent", is_pure=True, frequency="2"),
        raw_row(
            ACETONE, family="frequency_dependent", is_pure=True, frequency="0.01", doi=PRESENT_DOI
        ),
        raw_row(DODECANE, family="frequency_dependent", is_pure=True, frequency="1"),
        raw_row(HEXANAMINE, family="frequency_dependent", is_pure=True, frequency="2"),
        raw_row(NITROBENZENE, family="frequency_dependent", is_pure=True, frequency="0.1"),
        # A pure zero-frequency row that never reached the v11 table: the one
        # shape that means the gate itself misfired.
        raw_row(BUTANEDIOL, family="zero_frequency", is_pure=True, frequency="0"),
        raw_row(BUTANONE, family="zero_frequency", is_pure=True, frequency="0", doi=PRESENT_DOI),
    ]
    write_rows(raw, RAW_FIELDS, raw_rows)

    observations = tmp_path / "observations.csv"
    write_rows(
        observations, ("inchikey", "epsilon"), [{"inchikey": BUTANONE[0], "epsilon": "18.5"}]
    )

    features = tmp_path / "features.csv"
    write_rows(
        features,
        ("inchikey",),
        [
            {"inchikey": entry[0]}
            for entry in (BENZENE, FURAN, ACETONE, BUTANEDIOL, BUTANONE, NITROBENZENE)
        ],
    )

    roster = tmp_path / "roster.csv"
    write_rows(
        roster,
        ROSTER_FIELDS,
        [
            {
                "inchikey": entry[0],
                "name": entry[1],
                "smiles": entry[2],
                "source_doi": doi,
                "source_scope": "synthetic_fixture",
                "model_ready": "true",
                "T_K": temperature,
                "dielectric": value,
            }
            for entry, doi, temperature, value in (
                (BENZENE, NBS_DOI, "293.15", "2.284"),
                (FURAN, NBS_DOI, "298.15", "2.95"),
                (ACETONE, PRESENT_DOI, "298.15", "20.7"),
                (BUTANEDIOL, NBS_DOI, "303.15", "30.2"),
                (BUTANONE, NBS_DOI, "293.15", "18.51"),
            )
        ],
    )
    return Fixture(
        candidates=candidates,
        raw=raw,
        observations=observations,
        features=features,
        roster=roster,
    )


class FakeHTTP:
    """Injected HTTP layer: answers by the InChIKey embedded in the URL."""

    def __init__(
        self,
        records: dict[str, list[dict[str, str]]] | None = None,
        statuses: dict[str, int] | None = None,
    ) -> None:
        self.records = records or {}
        self.statuses = statuses or {}
        self.urls: list[str] = []

    def __call__(self, url: str, params=None) -> HttpResponse:
        self.urls.append(url)
        key = url.split("/compound/inchikey/")[1].split("/")[0]
        status = self.statuses.get(key, 200)
        if status != 200:
            body = json.dumps({"Fault": {"Message": "PUGREST.NotFound"}}).encode("utf-8")
            return HttpResponse(url=url, status=status, body=body)
        entries = self.records.get(key, [])
        payload = {"PropertyTable": {"Properties": entries}}
        return HttpResponse(url=url, status=200, body=json.dumps(payload).encode("utf-8"))


def pubchem_entry(
    entry: tuple[str, str, str, str], *, cid: str, formula: str | None = None
) -> dict[str, str]:
    _key, _, smiles, default_formula = entry
    return {
        "CID": cid,
        "SMILES": smiles,
        "ConnectivitySMILES": smiles,
        "MolecularFormula": formula or default_formula,
    }


def default_http() -> FakeHTTP:
    return FakeHTTP(
        records={
            BENZENE[0]: [pubchem_entry(BENZENE, cid="241")],
            FURAN[0]: [pubchem_entry(FURAN, cid="8029")],
            BUTANEDIOL[0]: [pubchem_entry(BUTANEDIOL, cid="8060")],
            BUTANONE[0]: [pubchem_entry(BUTANONE, cid="6569")],
            DODECANE[0]: [pubchem_entry(DODECANE, cid="8182")],
            HEXANAMINE[0]: [pubchem_entry(HEXANAMINE, cid="8102")],
            NITROBENZENE[0]: [pubchem_entry(NITROBENZENE, cid="7416")],
            # Two distinct structures for one InChIKey: must be ambiguous.
            CHLOROBUTANE[0]: [
                pubchem_entry(CHLOROBUTANE, cid="5442"),
                {
                    "CID": "999999",
                    "SMILES": "CCCCCl",
                    "ConnectivitySMILES": "CCCCCl",
                    "MolecularFormula": "C4H9Cl",
                },
            ],
            # A wrong MolecularFormula: must surface as a mismatch.
            METHYLFURAN[0]: [pubchem_entry(METHYLFURAN, cid="10797", formula="C5H7O")],
        },
        statuses={ACETONE[0]: 404, FLUOROETHANE[0]: 404},
    )


def run(fixture: Fixture, http_get: FakeHTTP, **overrides) -> dict:
    kwargs = {
        "http_get": http_get,
        "candidates_path": fixture.candidates,
        "raw_path": fixture.raw,
        "observations_path": fixture.observations,
        "features_path": fixture.features,
        "roster_path": fixture.roster,
        "sleep": lambda _seconds: None,
    }
    kwargs.update(overrides)
    return run_probe(**kwargs)


def row_of(record: dict, entry: tuple[str, str, str, str]) -> dict[str, str]:
    for row in record["rows"]:
        if row["inchikey"] == entry[0]:
            return row
    raise AssertionError(f"{entry[1]} missing from the result rows")


# --------------------------------------------------------------------------- #
# Payload parsing and identity checks
# --------------------------------------------------------------------------- #


def test_parse_pubchem_payload_reads_the_property_table() -> None:
    payload = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 241,
                    "SMILES": "c1ccccc1",
                    "ConnectivitySMILES": "C1=CC=CC=C1",
                    "MolecularFormula": "C6H6",
                }
            ]
        }
    }
    records = parse_pubchem_payload(payload)
    assert len(records) == 1
    assert records[0].cid == "241"
    assert records[0].smiles == "c1ccccc1"
    assert records[0].formula == "C6H6"


@pytest.mark.parametrize(
    "payload",
    [
        {"Fault": {"Message": "PUGREST.NotFound"}},
        {"PropertyTable": {}},
        {"PropertyTable": {"Properties": "nope"}},
        [],
        None,
    ],
)
def test_parse_pubchem_payload_refuses_anything_without_a_property_table(payload: object) -> None:
    assert parse_pubchem_payload(payload) == []


def test_fault_message_is_whitespace_normalised() -> None:
    payload = {"Fault": {"Message": "  PUGREST.NotFound\n  "}}
    assert fault_message(payload) == "PUGREST.NotFound"
    assert fault_message({"PropertyTable": {}}) == ""
    assert fault_message("not a mapping") == ""


def test_build_pubchem_url_encodes_the_key_and_names_the_properties() -> None:
    url = build_pubchem_url(BENZENE[0])
    assert url == (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/"
        "UHOVQNZJYSORNB-UHFFFAOYSA-N/property/SMILES,ConnectivitySMILES,MolecularFormula/JSON"
    )


def test_distinct_structures_collapses_canonical_duplicates() -> None:
    records = [
        PubChemRecord(cid="1", smiles="c1ccccc1", connectivity_smiles="", formula="C6H6"),
        PubChemRecord(cid="2", smiles="C1=CC=CC=C1", connectivity_smiles="", formula="C6H6"),
    ]
    assert distinct_structures(records) == ["c1ccccc1"]


def test_distinct_structures_keeps_genuinely_different_structures() -> None:
    records = [
        PubChemRecord(cid="1", smiles=BENZENE[2], connectivity_smiles="", formula="C6H6"),
        PubChemRecord(cid="2", smiles=DODECANE[2], connectivity_smiles="", formula="C12H26"),
    ]
    assert len(distinct_structures(records)) == 2


def test_resolve_from_records_without_records_is_unresolved() -> None:
    status, smiles, note = resolve_from_records([])
    assert (status, smiles, note) == (UNRESOLVED, "", "")


def test_resolve_from_records_marks_two_structures_ambiguous_and_records_both() -> None:
    records = [
        PubChemRecord(cid="1", smiles=BENZENE[2], connectivity_smiles="", formula="C6H6"),
        PubChemRecord(cid="2", smiles=DODECANE[2], connectivity_smiles="", formula="C12H26"),
    ]
    status, smiles, note = resolve_from_records(records)
    assert status == AMBIGUOUS
    assert smiles == ""
    assert "pubchem_returned_distinct_structures" in note
    assert BENZENE[2] in note and DODECANE[2] in note


def test_resolve_from_records_falls_back_to_connectivity_smiles() -> None:
    records = [PubChemRecord(cid="1", smiles="", connectivity_smiles="C1=CC=CC=C1", formula="C6H6")]
    status, smiles, _ = resolve_from_records(records)
    assert (status, smiles) == (RESOLVED, "C1=CC=CC=C1")


def test_resolve_from_records_keeps_the_fallback_when_the_record_is_empty() -> None:
    records = [PubChemRecord(cid="1", smiles="", connectivity_smiles="", formula="C6H6")]
    status, smiles, _ = resolve_from_records(records, fallback_smiles="c1ccccc1")
    assert (status, smiles) == (UNRESOLVED, "c1ccccc1")


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (BENZENE, "match"),
        (DODECANE, "match"),
        (HEXANAMINE, "match"),
        (NITROBENZENE, "match"),
    ],
)
def test_check_formula_matches_on_authentic_pairs(
    entry: tuple[str, str, str, str], expected: str
) -> None:
    verdict, computed = check_formula(entry[2], entry[3])
    assert verdict == expected
    assert computed


def test_check_formula_reports_the_disagreement_verbatim() -> None:
    verdict, computed = check_formula(BENZENE[2], "C12H26")
    assert verdict.startswith("mismatch:")
    assert "C6H6" in verdict and "C12H26" in verdict
    assert computed == "C6H6"


def test_check_formula_never_claims_a_match_without_both_sides() -> None:
    assert check_formula("", "C6H6")[0] == "not_checked_no_structure"
    assert check_formula(BENZENE[2], "")[0] == "not_checked_no_reference_formula"
    assert check_formula("not-a-smiles", "C6H6")[0] == "not_checked_rdkit_unparseable"


def test_check_roster_smiles_compares_canonical_forms() -> None:
    assert check_roster_smiles("C1=CC=CC=C1", "c1ccccc1") == "match"
    assert check_roster_smiles("c1ccccc1", DODECANE[2]) == "mismatch"
    assert check_roster_smiles("", "c1ccccc1") == "no_roster_smiles"
    assert check_roster_smiles("c1ccccc1", "") == "no_resolved_smiles"


@pytest.mark.parametrize("entry", [BENZENE, FURAN, ACETONE, DODECANE, HEXANAMINE, NITROBENZENE])
def test_check_inchikey_roundtrip_confirms_the_authentic_pairs(
    entry: tuple[str, str, str, str],
) -> None:
    """The strongest available identity check, and a guard on the fixtures."""
    assert check_inchikey_roundtrip(entry[0], entry[2]) == "match"


def test_check_inchikey_roundtrip_flags_a_different_structure() -> None:
    verdict = check_inchikey_roundtrip(DODECANE[0], BENZENE[2])
    assert verdict.startswith("mismatch:")
    assert BENZENE[0] in verdict


def test_check_inchikey_roundtrip_stays_unchecked_without_a_structure() -> None:
    assert check_inchikey_roundtrip(BENZENE[0], "") == "not_checked_no_structure"
    assert check_inchikey_roundtrip("", BENZENE[2]) == "not_checked_no_input_key"
    assert check_inchikey_roundtrip(BENZENE[0], "not-a-smiles") == "unparseable_smiles"


def test_format_number_trims_trailing_zeros() -> None:
    assert format_number(None) == ""
    assert format_number(10.0) == "10"
    assert format_number(10.5) == "10.5"
    assert format_number(20.0, digits=2) == "20"


# --------------------------------------------------------------------------- #
# Input tables
# --------------------------------------------------------------------------- #


def test_load_accepted_compounds_dedupes_and_ignores_rejected_rows(fixture: Fixture) -> None:
    compounds = load_accepted_compounds(fixture.candidates)
    assert len(compounds) == 11
    keys = {compound.inchikey for compound in compounds}
    assert PENTANOL[0] not in keys
    assert len(keys) == len(compounds)


def test_load_accepted_compounds_aggregates_the_rows(fixture: Fixture) -> None:
    by_key = {
        compound.inchikey: compound for compound in load_accepted_compounds(fixture.candidates)
    }
    benzene = by_key[BENZENE[0]]
    assert benzene.name == "benzene"
    assert benzene.candidate_smiles == BENZENE[2]
    assert benzene.in_roster is True
    assert benzene.n_accepted_rows == 2
    assert benzene.gates == ("accepted_extended_lowfreq", "accepted_primary_lowfreq")
    assert benzene.temperature_min_K == 293.15
    assert benzene.temperature_max_K == 298.15
    assert benzene.temperature_span_K == 5.0

    dodecane = by_key[DODECANE[0]]
    assert dodecane.candidate_smiles == ""
    assert dodecane.in_roster is False
    assert dodecane.temperature_span_K == 20.0

    furan = by_key[FURAN[0]]
    assert furan.temperature_span_K == 0.0


def test_scan_raw_evidence_counts_components_beyond_the_first_slot(fixture: Fixture) -> None:
    evidence = scan_raw_evidence(fixture.raw, keys={BENZENE[0], FURAN[0], BUTANEDIOL[0]})
    benzene = evidence[BENZENE[0]]
    assert benzene.n_rows == 3
    assert benzene.n_zero_frequency_total == 2
    assert benzene.n_zero_frequency_pure == 0
    assert benzene.n_zero_frequency_mixture == 2
    assert benzene.n_frequency_dependent_pure == 1
    assert benzene.pure_frequencies_mhz == ("0.01",)
    assert benzene.thermoml_formula == "C6H6"

    # The methanol component of benzene's mixture is not part of the wanted set.
    assert "OKKJLVBELUTLKV-UHFFFAOYSA-N" not in evidence

    furan = evidence[FURAN[0]]
    assert (furan.n_rows, furan.n_zero_frequency_total) == (1, 0)
    assert furan.pure_frequencies_mhz == ("2",)


def test_scan_raw_evidence_returns_nothing_for_an_unmentioned_compound(fixture: Fixture) -> None:
    evidence = scan_raw_evidence(fixture.raw, keys={CHLOROBUTANE[0]})
    assert CHLOROBUTANE[0] not in evidence


def test_load_raw_doi_set_lowercases_the_dois(fixture: Fixture) -> None:
    dois = load_raw_doi_set(fixture.raw)
    assert PRESENT_DOI in dois
    assert NBS_DOI not in dois


def test_load_observation_counts_filters_to_the_requested_keys(fixture: Fixture) -> None:
    counts = load_observation_counts(fixture.observations, keys={BUTANONE[0], BENZENE[0]})
    assert counts[BUTANONE[0]] == 1
    assert counts[BENZENE[0]] == 0
    assert len(counts) == 1


def test_load_roster_entries_reads_the_evidence_fields(fixture: Fixture) -> None:
    entries = load_roster_entries(fixture.roster, keys={BUTANONE[0]})
    entry = entries[BUTANONE[0]]
    assert entry.smiles == BUTANONE[2]
    assert entry.source_doi == NBS_DOI
    assert entry.model_ready is True
    assert entry.temperature_K == 293.15
    assert entry.dielectric == 18.51


def test_load_feature_keys_honours_the_key_filter(fixture: Fixture) -> None:
    assert load_feature_keys(fixture.features, keys={DODECANE[0]}) == set()
    assert load_feature_keys(fixture.features, keys={NITROBENZENE[0]}) == {NITROBENZENE[0]}


# --------------------------------------------------------------------------- #
# Why a compound is absent from the v11 table
# --------------------------------------------------------------------------- #


def test_derive_absence_suffix_names_each_thermoml_shape(fixture: Fixture) -> None:
    evidence = scan_raw_evidence(fixture.raw)
    assert derive_absence_suffix(None) == "thermoml_cache_does_not_mention_the_compound"
    assert derive_absence_suffix(evidence[FURAN[0]]) == "thermoml_has_no_zero_frequency_rows"
    assert (
        derive_absence_suffix(evidence[BENZENE[0]])
        == "thermoml_zero_frequency_rows_are_all_mixtures"
    )
    assert (
        derive_absence_suffix(evidence[BUTANEDIOL[0]])
        == "thermoml_has_zero_frequency_pure_rows_but_none_were_admitted"
    )


def test_build_absence_reason_separates_roster_source_from_gate_behaviour(
    fixture: Fixture,
) -> None:
    evidence = scan_raw_evidence(fixture.raw)
    raw_dois = load_raw_doi_set(fixture.raw)
    roster = load_roster_entries(fixture.roster, keys={BENZENE[0], ACETONE[0], FURAN[0]})

    assert (
        build_absence_reason(
            has_v11_rows=True,
            in_roster=True,
            roster_entry=roster[BENZENE[0]],
            raw_doi_set=raw_dois,
            evidence=evidence[BENZENE[0]],
        )
        == ""
    )
    absent = build_absence_reason(
        has_v11_rows=False,
        in_roster=True,
        roster_entry=roster[BENZENE[0]],
        raw_doi_set=raw_dois,
        evidence=evidence[BENZENE[0]],
    )
    assert absent == (
        f"roster_value_source_absent_from_thermoml_raw:{NBS_DOI}"
        "|thermoml_zero_frequency_rows_are_all_mixtures"
    )
    present = build_absence_reason(
        has_v11_rows=False,
        in_roster=True,
        roster_entry=roster[ACETONE[0]],
        raw_doi_set=raw_dois,
        evidence=evidence[ACETONE[0]],
    )
    assert present.startswith(f"roster_value_source_present_in_thermoml_raw:{PRESENT_DOI}|")
    unknown = build_absence_reason(
        has_v11_rows=False,
        in_roster=True,
        roster_entry=None,
        raw_doi_set=raw_dois,
        evidence=None,
    )
    assert unknown.startswith("roster_value_source_unknown|")
    new = build_absence_reason(
        has_v11_rows=False,
        in_roster=False,
        roster_entry=None,
        raw_doi_set=raw_dois,
        evidence=evidence[DODECANE[0]],
    )
    assert new == "not_in_roster|thermoml_has_no_zero_frequency_rows"


# --------------------------------------------------------------------------- #
# run_probe
# --------------------------------------------------------------------------- #


def test_run_probe_population_and_requests(fixture: Fixture) -> None:
    http = default_http()
    record = run(fixture, http)
    population = record["population"]
    assert population["n_accepted_compounds"] == 11
    assert population["n_new_to_roster"] == 6
    assert population["n_in_roster"] == 5
    assert population["n_accepted_lowfreq_rows"] == 17
    assert population["candidate_table_has_formula_column"] is False

    assert record["requests"]["used"] == 11
    assert record["requests"]["limit"] == 120
    assert record["requests"]["response_status_counts"] == {200: 9, 404: 2}
    assert len(record["failures"]) == 2
    assert {failure["inchikey"] for failure in record["failures"]} == {ACETONE[0], FLUOROETHANE[0]}

    # A rejected candidate must never reach the network.
    assert not any(PENTANOL[0] in url for url in http.urls)
    assert len(http.urls) == 11


def test_run_probe_resolution_statuses(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    assert record["resolution"]["status_counts"] == {RESOLVED: 9, AMBIGUOUS: 1, UNRESOLVED: 1}
    assert record["resolution"]["n_structurally_complete"] == 9

    chlorobutane = row_of(record, CHLOROBUTANE)
    assert chlorobutane["resolution_status"] == AMBIGUOUS
    assert chlorobutane["resolved_smiles"] == ""
    assert "pubchem_returned_distinct_structures" in chlorobutane["notes"]

    fluoroethane = row_of(record, FLUOROETHANE)
    assert fluoroethane["resolution_status"] == UNRESOLVED
    assert fluoroethane["resolved_smiles"] == ""
    assert "http_status_404" in fluoroethane["notes"]
    assert fluoroethane["resolution_source"] == ""


def test_run_probe_falls_back_to_the_candidate_smiles_on_404(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    acetone = row_of(record, ACETONE)
    assert acetone["resolution_status"] == RESOLVED
    assert acetone["resolved_smiles"] == ACETONE[2]
    assert acetone["resolution_source"] == "candidate_table"
    assert acetone["formula_check"] == "not_checked_no_reference_formula"
    assert acetone["thermoml_formula_match"] == "match"
    assert acetone["roster_smiles_match"] == "match"


def test_run_probe_takes_the_structure_from_pubchem_when_available(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    benzene = row_of(record, BENZENE)
    assert benzene["resolution_source"] == "pubchem"
    assert benzene["pubchem_cid"] == "241"
    assert benzene["pubchem_formula"] == "C6H6"
    assert benzene["rdkit_formula"] == "C6H6"
    assert benzene["formula_check"] == "match"
    assert benzene["inchikey_roundtrip"] == "match"


def test_run_probe_formula_checks(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    checks = record["formula_checks"]
    assert checks["match"] == 7
    assert checks["mismatch"] == 1
    assert checks["not_checked"] == 3
    assert checks["mismatch_detail"] == [
        {"inchikey": METHYLFURAN[0], "name": METHYLFURAN[1], "verdict": "mismatch:C5H6O!=C5H7O"}
    ]


def test_run_probe_identity_roundtrip_covers_exactly_the_resolved_rows(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    assert record["identity_checks"]["inchikey_roundtrip_match"] == 9
    assert record["identity_checks"]["inchikey_roundtrip_not_confirmed"] == [
        {
            "inchikey": CHLOROBUTANE[0],
            "name": CHLOROBUTANE[1],
            "verdict": "not_checked_no_structure",
        },
        {
            "inchikey": FLUOROETHANE[0],
            "name": FLUOROETHANE[1],
            "verdict": "not_checked_no_structure",
        },
    ]


def test_run_probe_absent_v11_rows_are_explained_per_compound(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    counts = record["v11_absence"]["reason_counts"]
    assert counts == {
        f"roster_value_source_absent_from_thermoml_raw:{NBS_DOI}"
        "|thermoml_zero_frequency_rows_are_all_mixtures": 1,
        f"roster_value_source_absent_from_thermoml_raw:{NBS_DOI}"
        "|thermoml_has_no_zero_frequency_rows": 1,
        f"roster_value_source_present_in_thermoml_raw:{PRESENT_DOI}"
        "|thermoml_has_no_zero_frequency_rows": 1,
        "not_in_roster|thermoml_has_no_zero_frequency_rows": 3,
        "not_in_roster|thermoml_cache_does_not_mention_the_compound": 3,
        f"roster_value_source_absent_from_thermoml_raw:{NBS_DOI}"
        "|thermoml_has_zero_frequency_pure_rows_but_none_were_admitted": 1,
    }
    butanone = row_of(record, BUTANONE)
    assert butanone["has_v11_rows"] == "true"
    assert butanone["n_v11_rows"] == "1"
    assert butanone["v11_absence_reason"] == ""


def test_run_probe_roster_absence_detail_carries_the_evidence(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    benzene = record["v11_absence"]["roster_compounds"][BENZENE[0]]
    assert benzene["roster_source_doi"] == NBS_DOI
    assert benzene["model_ready"] is True
    assert benzene["thermoml_rows"] == 3
    assert benzene["thermoml_zero_frequency_total"] == 2
    assert benzene["thermoml_zero_frequency_pure"] == 0
    assert benzene["thermoml_zero_frequency_mixture"] == 2
    assert benzene["n_v11_rows"] == 0


def test_run_probe_needs_xtb_tracks_missing_frozen_features(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    needs_xtb = {entry["inchikey"] for entry in record["coverage"]["needs_xtb"]}
    assert needs_xtb == {DODECANE[0], HEXANAMINE[0], METHYLFURAN[0]}
    assert record["coverage"]["n_with_frozen_features"] == 6
    assert record["coverage"]["n_with_any_v11_row"] == 1
    assert record["coverage"]["n_roster_smiles_match"] == 5
    assert record["coverage"]["n_roster_smiles_mismatch"] == 0


def test_run_probe_flags_manual_review_cases(fixture: Fixture) -> None:
    record = run(fixture, default_http())
    flagged = {entry["inchikey"] for entry in record["resolution"]["needs_manual_review"]}
    # ambiguous, unresolved, formula mismatch, and the gate anomaly
    assert flagged == {CHLOROBUTANE[0], FLUOROETHANE[0], METHYLFURAN[0], BUTANEDIOL[0]}
    assert record["resolution"]["n_still_needing_manual_work"] == 4


def test_run_probe_max_compounds_bounds_the_work(fixture: Fixture) -> None:
    http = default_http()
    record = run(fixture, http, max_compounds=2)
    assert record["population"]["n_accepted_compounds"] == 2
    assert record["requests"]["used"] == 2
    assert len(http.urls) == 2


def test_run_probe_offline_makes_no_request_and_keeps_smiles_from_disk(fixture: Fixture) -> None:
    http = default_http()
    record = run(fixture, http, offline=True)
    assert http.urls == []
    assert record["requests"]["used"] == 0
    assert record["mode"] == {"offline": True, "facts_replay": False}
    assert record["resolution"]["status_counts"] == {RESOLVED: 5, NOT_QUERIED: 6}
    benzene = row_of(record, BENZENE)
    assert benzene["resolved_smiles"] == BENZENE[2]
    assert benzene["resolution_source"] == "candidate_table"
    dodecane = row_of(record, DODECANE)
    assert dodecane["resolved_smiles"] == ""
    assert dodecane["needs_xtb"] == "false"
    assert dodecane["formula_check"] == "not_checked_no_structure"


def test_run_probe_respects_an_exhausted_budget(fixture: Fixture) -> None:
    http = default_http()
    record = run(fixture, http, request_budget_limit=3)
    assert record["requests"]["used"] == 3
    assert len(http.urls) == 3
    exhausted = [row for row in record["rows"] if "budget_exhausted" in row["notes"]]
    assert len(exhausted) == 8
    # A compound with no candidate SMILES cannot be rescued once the budget is
    # gone; one that already carries a roster SMILES still resolves from disk.
    unrescued = {row["inchikey"] for row in exhausted if row["resolved_smiles"] == ""}
    assert unrescued == {
        DODECANE[0],
        NITROBENZENE[0],
        FLUOROETHANE[0],
        METHYLFURAN[0],
    }
    assert record["resolution"]["status_counts"] == {RESOLVED: 6, AMBIGUOUS: 1, UNRESOLVED: 4}


def test_run_probe_replays_recorded_answers_without_asking_pubchem(fixture: Fixture) -> None:
    first = run(fixture, default_http())
    replay = {
        key: {
            "status": value["status"],
            "note": value["note"],
            "records": [PubChemRecord.from_dict(record) for record in value["records"]],
        }
        for key, value in first["pubchem_records"].items()
    }
    http = default_http()
    second = run(fixture, http, facts_replay=replay)
    assert http.urls == []
    assert second["requests"]["used"] == 0
    assert second["mode"] == {"offline": False, "facts_replay": True}
    assert second["resolution"]["status_counts"] == first["resolution"]["status_counts"]
    assert (
        second["requests"]["response_status_counts"] == first["requests"]["response_status_counts"]
    )
    assert [row["resolved_smiles"] for row in second["rows"]] == [
        row["resolved_smiles"] for row in first["rows"]
    ]


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #


def test_write_csv_is_lf_only_and_uses_the_declared_columns(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    write_csv(target, [{"inchikey": "X", "name": "n"}])
    payload = target.read_bytes()
    assert b"\r" not in payload
    assert payload.endswith(b"\n")
    header = payload.decode("utf-8").splitlines()[0].split(",")
    assert header == list(CSV_FIELDS)


def test_read_facts_replay_round_trips_a_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "pubchem_records": {
                    BENZENE[0]: {
                        "status": 200,
                        "note": "",
                        "records": [
                            PubChemRecord(
                                cid="241",
                                smiles=BENZENE[2],
                                connectivity_smiles=BENZENE[2],
                                formula=BENZENE[3],
                            ).as_dict()
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    replay = read_facts_replay(summary)
    assert replay[BENZENE[0]]["status"] == 200
    assert replay[BENZENE[0]]["records"][0].cid == "241"


def test_read_facts_replay_requires_the_block(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"population": {}}), encoding="utf-8")
    with pytest.raises(TypeError):
        read_facts_replay(summary)


def test_main_writes_the_csv_and_the_summary(fixture: Fixture, tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "lowfreq_structures.csv"
    summary = tmp_path / "lowfreq_structures.json"
    http = default_http()
    monkeypatch.setattr(
        "probes.dielectric_lowfreq_structures.default_http_get",
        lambda url, params=None: http(url, params),
    )
    exit_code = main(
        [
            "--candidates",
            str(fixture.candidates),
            "--raw",
            str(fixture.raw),
            "--observations",
            str(fixture.observations),
            "--features",
            str(fixture.features),
            "--roster",
            str(fixture.roster),
            "--output",
            str(output),
            "--summary",
            str(summary),
            "--sleep",
            "0",
        ]
    )
    assert exit_code == 0
    assert len(http.urls) == 11

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 11
    assert all(row["resolution_status"] for row in rows)

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["population"]["n_accepted_compounds"] == 11
    assert payload["resolution"]["n_structurally_complete"] == 9
    assert "rows" not in payload
    assert payload["pubchem_records"][BENZENE[0]]["records"][0]["cid"] == "241"


def test_import_performs_no_network_io() -> None:
    script = (
        "import socket\n"
        "class Blocked(socket.socket):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        raise AssertionError('network access during import')\n"
        "socket.socket = Blocked\n"
        "def _blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during import')\n"
        "socket.create_connection = _blocked\n"
        "import probes.dielectric_lowfreq_structures as module\n"
        "print('imported', module.CSV_FIELDS[0])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "imported inchikey" in result.stdout
