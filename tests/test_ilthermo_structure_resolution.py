"""Offline unit tests for the ILThermo -> PubChem structure resolution probe.

The probe exists to close a join between two systems that share no identifier, so
the tests concentrate on the places where a sloppy join would silently claim more
than the data supports:

- a shared molecular formula must never become a compound match (constitutional
  isomers share one formula);
- an unresolved name must stay unresolved with its reason attached instead of
  inheriting a plausible-looking InChIKey;
- the temperature columns must stay empty when no ilset payload was read.

Everything runs offline: the HTTP layer is injected and every roster/summary is a
tmp_path fixture.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from probes.ilthermo_probe import DATASET_PATH, ORIGIN, HttpResponse, RequestBudget, load_roster
from probes.ilthermo_structure_resolution import (
    AMBIGUOUS,
    CSV_FIELDS,
    NOT_QUERIED,
    RESOLVED,
    UNRESOLVED,
    PubChemCandidate,
    Resolution,
    build_pubchem_url,
    classify_candidates,
    compound_formula,
    compound_temperature,
    facts_from_set_payload,
    format_number,
    formula_check,
    load_roster_smiles,
    lookup_pubchem,
    lookup_variants,
    main,
    parse_probe_pure_compounds,
    parse_pubchem_payload,
    read_facts_replay,
    reconcile_roster,
    repair_lookup_name,
    review_reasons,
    roster_indexes,
    run_resolution,
    sample_formulas,
    set_facts_from_dict,
    set_facts_to_dict,
    span_class,
    write_csv,
)

# --------------------------------------------------------------------------- #
# Canned payloads mirroring the real response shapes
# --------------------------------------------------------------------------- #

DEFAULT_DHEAD = [
    ["Temperature, K", None],
    ["Pressure, kPa", None],
    ["Frequency, MHz", "Liquid"],
    ["Relative permittivity at zero frequency", "Liquid"],
]

# The isomer pair: the roster's 1-ethyl-2,3-dimethylimidazolium NTf2 and ILThermo's
# 1-methyl-3-propylimidazolium NTf2 really do share the formula C9H13F6N3O4S2.
ISOMER_B_SMILES = "CCC[N+]1=CN(C)C=C1.C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F"
ROSTER_NTF2_SMILES = "CC[N+]1=C(C)N(C=C1)C.C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F"
ROSTER_NTF2_FORMULA = "C9H13F6N3O4S2"
ROSTER_NTF2_INCHIKEY = "XDJYSDBSJWNTQT-UHFFFAOYSA-N"

ROSTER_ROWS = [
    {
        "inchikey": ROSTER_NTF2_INCHIKEY,
        "smiles": ROSTER_NTF2_SMILES,
        "name": "1-ethyl-2,3-dimethylimidazolium bis(trifluoromethylsulfonyl)imide",
        "gate_flags": "zero_frequency|pure_component",
    },
    {
        "inchikey": "XLYOFNOQVPJJNP-UHFFFAOYSA-N",
        "smiles": "O",
        "name": "water",
        "gate_flags": "zero_frequency|pure_component",
    },
    {
        "inchikey": "IXQYBUDWDLYNMA-UHFFFAOYSA-N",
        "smiles": "CCCC[N+]1=CN(C)C=C1.F[P-](F)(F)(F)(F)F",
        "name": "1-butyl-3-methylimidazolium hexafluorophosphate",
        "gate_flags": "pure_component|out_of_scope_ionic_or_organometallic",
    },
    {
        # Same compound as ILThermo's "1-hexylpyridinium tetrafluoroborate" under a
        # spelling that does not survive normalisation, so only the InChIKey join
        # can recover it.
        "inchikey": "ABCDEFGHIJKLMN-UHFFFAOYSA-N",
        "smiles": "CCCCCC[n+]1ccccc1.F[B-](F)(F)F",
        "name": "hexylpyridinium tetrafluoroborate",
        "gate_flags": "zero_frequency|pure_component",
    },
]

ISOMER_NAME = "1-methyl-3-propylimidazolium bis[(trifluoromethyl)sulfonyl]imide"
RECOVERABLE_NAME = "1-hexylpyridinium tetrafluoroborate"
NOT_FOUND_NAME = "1-methyl-3-octylimidazolium chloride"
AMBIGUOUS_NAME = "acetylcholine bis(trifluoromethylsulfonyl)imide"
BROKEN_NAME = "2-hydroxy-N,N,N-trimethylethan-1-aminium L-prolinate"
HEXAHYDRO_NAME = "1-ethyl-3-methylimidazolium tetrafluoroborate"

CENSUS_SETS = [
    {"setid": "s1", "datapoints": 18, "components": [ROSTER_ROWS[0]["name"]],
     "reference": "Bennett et al. (2019)"},
    {"setid": "s2", "datapoints": 18, "components": [ISOMER_NAME],
     "reference": "Bennett et al. (2019)"},
    {"setid": "s3", "datapoints": 6, "components": ["water"],
     "reference": "Huang et al. (2011b)"},
    {"setid": "s4", "datapoints": 1, "components": [ROSTER_ROWS[2]["name"]],
     "reference": "Nakamura and Shikata (2010)"},
    {"setid": "s5", "datapoints": 18, "components": [RECOVERABLE_NAME],
     "reference": "Bennett et al. (2019)"},
    {"setid": "s6", "datapoints": 18, "components": [NOT_FOUND_NAME],
     "reference": "Musale et al. (2019)"},
    {"setid": "s7", "datapoints": 1, "components": [AMBIGUOUS_NAME],
     "reference": "Wakai et al. (2005)"},
    {"setid": "s8", "datapoints": 3, "components": [BROKEN_NAME],
     "reference": "Ma et al. (2016b)"},
    # A binary mixture: it must never be counted as a pure compound.
    {"setid": "s9", "datapoints": 30,
     "components": ["1-butyl-3-methylimidazolium chloride", "methanol"],
     "reference": "Rana et al. (2019)"},
]


def _json(payload: dict, status: int = 200) -> HttpResponse:
    return HttpResponse(
        url="canned",
        status=status,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _ilset_payload(
    name: str,
    formula: str,
    data: list,
    *,
    dhead: list | None = None,
    reference: str = "Bennett, E. L. (2019) J. Mol. Liq. 294, 111571.",
) -> dict:
    return {
        "title": "Refraction, surface tension, and speed of sound: Relative permittivity",
        "ref": {"title": "Measured relative complex permittivities", "full": reference},
        "dhead": DEFAULT_DHEAD if dhead is None else dhead,
        "components": [{"name": name, "mw": "1.00", "idout": "AAheIp", "formula": formula}],
        "data": data,
        "expmeth": "Coaxial cylinder capacitor",
    }


def _data_row(temperature: float, epsilon: float, *, frequency: float = 1000.0,
              uncertainty: float = 0.1) -> list:
    return [[str(temperature)], ["101.325"], [str(frequency)], [str(epsilon), str(uncertainty)]]


def _probe_summary(sets: list | None = None, *, sample: list | None = None) -> dict:
    return {
        "probe": "ilthermo",
        "dataset_census": {
            "by_key": {"pure_component": {"count": len(sets or []), "sets": sets or []}}
        },
        "sample": {"sets": sample or []},
    }


def _pubchem_payload(*candidates: dict) -> dict:
    return {"PropertyTable": {"Properties": list(candidates)}}


def _candidate(cid: int, smiles: str, inchikey: str, formula: str) -> dict:
    return {"CID": cid, "SMILES": smiles, "InChIKey": inchikey, "MolecularFormula": formula}


def _key(url: str, params: dict | None = None) -> tuple:
    return (url, tuple(sorted((params or {}).items())))


def _set_key(setid: str) -> tuple:
    return _key(f"{ORIGIN}{DATASET_PATH}", {"set": setid})


def _transport(routes: dict, log: list | None = None):
    def http_get(url, params=None):
        if log is not None:
            log.append((url, dict(params or {})))
        entry = routes.get(_key(url, params))
        if entry is None:
            entry = routes.get(url)
        if entry is None:
            return _json({"Fault": {"Message": "no route"}}, status=404)
        return entry() if callable(entry) else entry

    return http_get


def _forbidden_transport():
    def http_get(url, params=None):
        raise AssertionError(f"an offline run attempted a network call: {url}")

    return http_get


def _noop_sleep(_seconds: float) -> None:
    return None


def _no_set_transport(routes: dict):
    """A transport for replayed runs: any ilset request is a bug."""

    def http_get(url, params=None):
        if (params or {}).get("set"):
            raise AssertionError("a replayed run attempted to re-read an ilset payload")
        entry = routes.get(_key(url, params))
        if entry is None:
            entry = routes.get(url)
        if entry is None:
            return _json({"Fault": {"Message": "no route"}}, status=404)
        return entry() if callable(entry) else entry

    return http_get


def _write_roster(tmp_path: Path, rows: list | None = None) -> Path:
    path = tmp_path / "roster.csv"
    fields = ["inchikey", "smiles", "name", "gate_flags"]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ROSTER_ROWS if rows is None else rows)
    return path


def _write_summary(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "ilthermo_probe_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _dataset_routes(*, varying: bool = False) -> dict:
    routes = {
        _set_key("s1"): _json(_ilset_payload(ROSTER_ROWS[0]["name"], ROSTER_NTF2_FORMULA,
                                             [_data_row(298.15, 9.4)])),
        _set_key("s2"): _json(_ilset_payload(ISOMER_NAME, ROSTER_NTF2_FORMULA,
                                             [_data_row(298.15, 8.7)])),
        _set_key("s3"): _json(_ilset_payload("water", "H2O",
                                             [_data_row(298.15, 78.4, frequency=0.0)])),
        _set_key("s4"): _json(_ilset_payload(ROSTER_ROWS[2]["name"], "C8H15F6N2P",
                                             [_data_row(298.15, 12.1)])),
        _set_key("s5"): _json(_ilset_payload(RECOVERABLE_NAME, "C11H18BF4N",
                                             [_data_row(298.15, 11.6, frequency=1000.0)])),
        _set_key("s6"): _json(_ilset_payload(NOT_FOUND_NAME, "C12H23ClN2",
                                             [_data_row(298.15, 6.8)])),
        _set_key("s7"): _json(_ilset_payload(AMBIGUOUS_NAME, "C8H12F6N2O5S2",
                                             [_data_row(298.15, 22.0)])),
        _set_key("s8"): _json(_ilset_payload(BROKEN_NAME, "C8H18N2O3",
                                             [_data_row(298.15, 30.0)])),
    }
    if varying:
        routes[_set_key("s8")] = _json(
            _ilset_payload(BROKEN_NAME, "C8H18N2O3", [_data_row(293.15, 31.0),
                                                      _data_row(303.15, 29.0)])
        )
    return routes


def _pubchem_routes(*, recover: bool = True, ambiguous: bool = True,
                    broken: bool = True, missing: bool = True) -> dict:
    routes = {
        build_pubchem_url(ISOMER_NAME): _json(
            _pubchem_payload(
                _candidate(12345, ISOMER_B_SMILES, "PROPYLIMIDAZOLIUM-KEY-UHFFFAOYSA-N",
                           ROSTER_NTF2_FORMULA)
            )
        ),
        build_pubchem_url(HEXAHYDRO_NAME): _json(
            _pubchem_payload(_candidate(9, "CC[n+]1cn(C)c1.F[B-](F)(F)F",
                                        "EMIM-BF4-KEY-UHFFFAOYSA-N", "C6H11BF4N2"))
        ),
    }
    if recover:
        routes[build_pubchem_url(RECOVERABLE_NAME)] = _json(
            _pubchem_payload(
                _candidate(778, "CCCCCC[n+]1ccccc1", "PYRIDINIUM-CATION-ONLY-KEY", "C11H18N+"),
                _candidate(777, "CCCCCC[n+]1ccccc1.F[B-](F)(F)F",
                           ROSTER_ROWS[3]["inchikey"], "C11H18BF4N"),
            )
        )
    if ambiguous:
        routes[build_pubchem_url(AMBIGUOUS_NAME)] = _json(
            _pubchem_payload(
                _candidate(1, "CC(=O)OCC[N+](C)(C)C.C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
                           "AMBIG-ONE-KEY-UHFFFAOYSA-N", "C9H14F6N2O5S2"),
                _candidate(2, "CC(=O)OCC[N+](C)(C)C.C(F)(F)(F)S(=O)(=O)NS(=O)(=O)C(F)(F)F",
                           "AMBIG-TWO-KEY-UHFFFAOYSA-N", "C9H15F6NO5S2"),
            )
        )
    if broken:
        def boom():
            raise ConnectionError("DNS lookup failed")

        routes[build_pubchem_url(BROKEN_NAME)] = boom
    if missing:
        routes[build_pubchem_url(NOT_FOUND_NAME)] = _json(
            {"Fault": {"Message": "PUGREST.NotFound"}}, status=404
        )
    return routes


def _full_routes(**kwargs) -> dict:
    routes = _dataset_routes()
    routes.update(_pubchem_routes(**kwargs))
    return routes


def _run(tmp_path: Path, routes: dict, *, offline: bool = False, **overrides):
    payload = overrides.pop("summary_payload", _probe_summary(CENSUS_SETS))
    summary_path = _write_summary(tmp_path, payload)
    roster_path = _write_roster(tmp_path)
    kwargs = {
        "http_get": _transport(routes),
        "probe_summary_path": summary_path,
        "roster_path": roster_path,
        "offline": offline,
        "sleep": _noop_sleep,
        "delay_seconds": 0.0,
    }
    kwargs.update(overrides)
    return run_resolution(**kwargs)


def _row(record: dict, name: str) -> dict:
    for row in record["rows"]:
        if row["ilthermo_name"] == name:
            return row
    raise AssertionError(f"no row for {name!r}")


# --------------------------------------------------------------------------- #
# Census parsing
# --------------------------------------------------------------------------- #


def test_pure_compounds_are_aggregated_from_the_census() -> None:
    compounds = parse_probe_pure_compounds(_probe_summary(CENSUS_SETS))
    names = [compound.name for compound in compounds]
    assert len(compounds) == 8
    assert "methanol" not in names
    isomer = next(c for c in compounds if c.name == ISOMER_NAME)
    assert isomer.setids == ("s2",)
    assert isomer.n_epsilon_sets == 1
    assert isomer.n_datapoints == 18
    assert isomer.references == ("Bennett et al. (2019)",)
    assert isomer.is_ionic_liquid is True


def test_multi_component_sets_are_not_pure_compounds() -> None:
    compounds = parse_probe_pure_compounds(_probe_summary(CENSUS_SETS))
    assert all(compound.name != "1-butyl-3-methylimidazolium chloride" for compound in compounds)


def test_census_sets_are_merged_per_compound() -> None:
    sets = [
        {"setid": "a", "datapoints": 18, "components": ["water"], "reference": "R1"},
        {"setid": "b", "datapoints": 6, "components": ["water"], "reference": "R2"},
    ]
    compounds = parse_probe_pure_compounds(_probe_summary(sets))
    assert len(compounds) == 1
    assert compounds[0].n_epsilon_sets == 2
    assert compounds[0].n_datapoints == 24
    assert compounds[0].setids == ("a", "b")
    assert compounds[0].references == ("R1", "R2")


def test_compounds_are_sorted_by_set_count_then_name() -> None:
    sets = [
        {"setid": "a", "datapoints": 1, "components": ["zzz"], "reference": "R"},
        {"setid": "b", "datapoints": 1, "components": ["aaa"], "reference": "R"},
        {"setid": "c", "datapoints": 1, "components": ["aaa"], "reference": "R"},
    ]
    compounds = parse_probe_pure_compounds(_probe_summary(sets))
    assert [compound.name for compound in compounds] == ["aaa", "zzz"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"dataset_census": {}},
        {"dataset_census": {"by_key": {}}},
        {"dataset_census": {"by_key": {"pure_component": {"sets": "nope"}}}},
    ],
)
def test_missing_census_blocks_raise(payload: dict) -> None:
    with pytest.raises(TypeError):
        parse_probe_pure_compounds(payload)


def test_sample_formulas_reads_the_probe_sample() -> None:
    summary = _probe_summary(
        CENSUS_SETS,
        sample=[{"setid": "s1", "components": [{"name": "water", "formula": "H2O"}]}],
    )
    assert sample_formulas(summary) == {"water": "H2O"}


def test_sample_formulas_tolerates_a_missing_sample_block() -> None:
    assert sample_formulas({"probe": "ilthermo"}) == {}


# --------------------------------------------------------------------------- #
# Name variants
# --------------------------------------------------------------------------- #


def test_lookup_variants_keeps_the_published_name_first() -> None:
    assert lookup_variants("1-methyl-3-octylimidazolium chloride") == (
        "1-methyl-3-octylimidazolium chloride",
    )


def test_lookup_variants_repairs_the_published_typo() -> None:
    name = "1-hexylpyridinium bis(trifluromethylsulfonyl)imide"
    variants = lookup_variants(name)
    assert len(variants) == 2
    assert variants[0] == name
    assert "trifluromethyl" not in variants[1]
    assert "trifluoromethyl" in variants[1]


def test_repair_lookup_name_leaves_correct_spellings_alone() -> None:
    name = "triethylsulfonium bis((trifluoromethyl)sulfonyl)imide"
    assert repair_lookup_name(name) == name


def test_build_pubchem_url_encodes_the_published_name() -> None:
    url = build_pubchem_url("1-methyl-3-propylimidazolium bis[(trifluoromethyl)sulfonyl]imide")
    assert url.startswith("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/")
    assert url.endswith("/property/SMILES,InChIKey,MolecularFormula/JSON")
    assert "%5B" in url and "%5D" in url and "(" not in url.split("/name/")[1]


# --------------------------------------------------------------------------- #
# PubChem payload parsing
# --------------------------------------------------------------------------- #


def test_parse_pubchem_payload_reads_the_property_table() -> None:
    payload = _pubchem_payload(_candidate(1, "O", "XLYOFNOQVPJJNP-UHFFFAOYSA-N", "H2O"))
    assert parse_pubchem_payload(payload) == [
        PubChemCandidate(cid=1, smiles="O", inchikey="XLYOFNOQVPJJNP-UHFFFAOYSA-N", formula="H2O")
    ]


def test_parse_pubchem_payload_accepts_a_string_cid() -> None:
    payload = _pubchem_payload({"CID": "962", "SMILES": "O", "InChIKey": "K", "MolecularFormula": "H2O"})
    assert parse_pubchem_payload(payload)[0].cid == 962


def test_parse_pubchem_payload_skips_entries_without_identity() -> None:
    payload = _pubchem_payload({"CID": 1}, {"CID": 2, "SMILES": "", "InChIKey": ""})
    assert parse_pubchem_payload(payload) == []


def test_parse_pubchem_payload_tolerates_a_boolean_cid() -> None:
    payload = _pubchem_payload({"CID": True, "SMILES": "O", "InChIKey": "K", "MolecularFormula": ""})
    assert parse_pubchem_payload(payload)[0].cid is None


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"PropertyTable": {}}, {"PropertyTable": {"Properties": "nope"}}, "text"],
)
def test_parse_pubchem_payload_tolerates_broken_shapes(payload: object) -> None:
    assert parse_pubchem_payload(payload) == []


# --------------------------------------------------------------------------- #
# Candidate classification
# --------------------------------------------------------------------------- #


def test_one_inchikey_resolves_and_prefers_the_shortest_smiles() -> None:
    candidates = [
        PubChemCandidate(cid=1, smiles="C(C)(C)C", inchikey="KEY-A", formula="C4H10"),
        PubChemCandidate(cid=1, smiles="CC(C)C", inchikey="KEY-A", formula="C4H10"),
    ]
    resolution = classify_candidates(candidates, "C4H10")
    assert resolution.status == RESOLVED
    assert resolution.inchikey == "KEY-A"
    assert resolution.smiles == "CC(C)C"
    assert resolution.n_candidates == 2


def test_several_cids_under_one_inchikey_still_resolve() -> None:
    candidates = [
        PubChemCandidate(cid=1, smiles="O", inchikey="KEY-A", formula="H2O"),
        PubChemCandidate(cid=2, smiles="O", inchikey="KEY-A", formula="H2O"),
    ]
    assert classify_candidates(candidates, "H2O").status == RESOLVED


def test_no_inchikey_is_unresolved_not_a_guess() -> None:
    candidates = [PubChemCandidate(cid=1, smiles="O", inchikey="", formula="H2O")]
    resolution = classify_candidates(candidates, "H2O")
    assert resolution.status == UNRESOLVED
    assert resolution.inchikey == ""


def test_empty_candidates_are_unresolved() -> None:
    assert classify_candidates([], "H2O").status == UNRESOLVED


def test_two_inchikeys_one_formula_match_is_a_recorded_disambiguation() -> None:
    candidates = [
        PubChemCandidate(cid=1, smiles="CC(=O)OCC[N+](C)(C)C.C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
                         inchikey="AMBIG-ONE", formula="C9H14F6N2O5S2"),
        PubChemCandidate(cid=2, smiles="CC(=O)OCC[N+](C)(C)C.C(F)(F)(F)S(=O)(=O)NS(=O)(=O)C(F)(F)F",
                         inchikey="AMBIG-TWO", formula="C9H17F6N2O6S2+"),
    ]
    resolution = classify_candidates(candidates, "C9H17F6N2O6S2")
    assert resolution.status == RESOLVED
    assert resolution.inchikey == "AMBIG-TWO"
    assert "disambiguated by the ILThermo molecular formula" in resolution.note
    assert "AMBIG-ONE" in resolution.note


def test_two_inchikeys_that_both_match_the_formula_are_ambiguous() -> None:
    candidates = [
        PubChemCandidate(cid=1, smiles="O", inchikey="KEY-A", formula="H2O"),
        PubChemCandidate(cid=2, smiles="[OH2]", inchikey="KEY-B", formula="H2O"),
    ]
    resolution = classify_candidates(candidates, "H2O")
    assert resolution.status == AMBIGUOUS
    assert resolution.inchikey == ""
    assert "KEY-A" in resolution.note and "KEY-B" in resolution.note


def test_ambiguity_without_an_expected_formula_stays_ambiguous() -> None:
    candidates = [
        PubChemCandidate(cid=1, smiles="O", inchikey="KEY-A", formula="H2O"),
        PubChemCandidate(cid=2, smiles="S", inchikey="KEY-B", formula="H2S"),
    ]
    assert classify_candidates(candidates, "").status == AMBIGUOUS


# --------------------------------------------------------------------------- #
# Formula check
# --------------------------------------------------------------------------- #


def test_formula_check_matches_order_insensitively() -> None:
    assert formula_check("C8H15BF4N2", "B1C8F4H15N2") == "match"


def test_formula_check_flags_a_mismatch() -> None:
    assert formula_check("C8H15BF4N2", "C8H15F6N2P") == "mismatch"


@pytest.mark.parametrize(
    ("ilthermo_formula", "computed"),
    [("", "H2O"), ("H2O", None), ("", None)],
)
def test_formula_check_is_not_checked_without_both_sides(
    ilthermo_formula: str, computed: str | None
) -> None:
    assert formula_check(ilthermo_formula, computed) == "not_checked"


def test_format_number_renders_blanks_for_unknown_values() -> None:
    assert format_number(None) == ""
    assert format_number(298.15) == "298.15"
    assert format_number(0.0, digits=3) == "0.000"


# --------------------------------------------------------------------------- #
# Roster reconciliation
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def roster_bundle(tmp_path_factory: pytest.TempPathFactory):
    directory = tmp_path_factory.mktemp("roster")
    path = _write_roster(directory)
    roster = load_roster(path, formula_of_smiles=lambda smiles: {
        ROSTER_NTF2_SMILES: ROSTER_NTF2_FORMULA,
        "O": "H2O",
        "CCCC[N+]1=CN(C)C=C1.F[P-](F)(F)(F)(F)F": "C8H15F6N2P",
        "CCCCCC[n+]1ccccc1.F[B-](F)(F)F": "C11H16BF4N",
    }.get(smiles))
    return roster, roster_indexes(roster)


def test_name_join_marks_the_roster_hit(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=UNRESOLVED)
    verdict = reconcile_roster(ROSTER_ROWS[0]["name"], resolution, roster, indexes)
    assert verdict.in_roster is True
    assert verdict.basis == "name"
    assert verdict.roster_name == ROSTER_ROWS[0]["name"]
    assert verdict.out_of_scope is False


def test_out_of_scope_flag_travels_with_the_roster_hit(roster_bundle) -> None:
    roster, indexes = roster_bundle
    verdict = reconcile_roster(ROSTER_ROWS[2]["name"], Resolution(status=UNRESOLVED), roster, indexes)
    assert verdict.in_roster is True
    assert verdict.out_of_scope is True


def test_inchikey_join_recovers_a_differently_spelled_name(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey=ROSTER_ROWS[3]["inchikey"], smiles="x")
    verdict = reconcile_roster(RECOVERABLE_NAME, resolution, roster, indexes)
    assert verdict.in_roster is True
    assert verdict.basis == "inchikey"
    assert verdict.roster_name == ROSTER_ROWS[3]["name"]


def test_unknown_compound_stays_out_of_the_roster(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey="NOT-IN-ROSTER-KEY", smiles="x")
    verdict = reconcile_roster(ISOMER_NAME, resolution, roster, indexes)
    assert verdict.in_roster is False
    assert verdict.basis == "none"
    assert verdict.roster_name == ""


def test_roster_smiles_are_read_from_the_file(tmp_path: Path) -> None:
    path = _write_roster(tmp_path)
    smiles = load_roster_smiles(path)
    assert smiles["water"] == "O"
    assert len(smiles) == len(ROSTER_ROWS)


def test_isomer_formula_collision_needs_manual_review(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey="PROPYLIMIDAZOLIUM-KEY-UHFFFAOYSA-N",
                            smiles=ISOMER_B_SMILES)
    verdict = reconcile_roster(ISOMER_NAME, resolution, roster, indexes)
    reasons = review_reasons(resolution, verdict, "match", ROSTER_NTF2_FORMULA, roster, indexes)
    assert verdict.in_roster is False
    assert any(reason.startswith("isomer_formula_collision_with_roster:") for reason in reasons)


def test_shared_skeleton_is_flagged_even_without_a_formula(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey="XDJYSDBSJWNTQT-UHFFFAOYSA-M", smiles="x")
    verdict = reconcile_roster("some new NTf2 salt", resolution, roster, indexes)
    reasons = review_reasons(resolution, verdict, "not_checked", "", roster, indexes)
    assert any(reason.startswith("shared_skeleton_with_roster:") for reason in reasons)


def test_formula_mismatch_is_a_review_reason(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey="SOMETHING-ELSE-UHFFFAOYSA-N", smiles="x")
    verdict = reconcile_roster("unrelated compound", resolution, roster, indexes)
    reasons = review_reasons(resolution, verdict, "mismatch", "C99H99", roster, indexes)
    assert "formula_mismatch_vs_ilthermo" in reasons


def test_ambiguity_is_a_review_reason(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=AMBIGUOUS, note="two keys")
    verdict = reconcile_roster("unrelated compound", resolution, roster, indexes)
    assert "ambiguous_pubchem_name" in review_reasons(
        resolution, verdict, "not_checked", "", roster, indexes
    )


def test_roster_members_are_never_sent_to_manual_review(roster_bundle) -> None:
    roster, indexes = roster_bundle
    resolution = Resolution(status=RESOLVED, inchikey=ROSTER_NTF2_INCHIKEY, smiles=ROSTER_NTF2_SMILES)
    verdict = reconcile_roster(ROSTER_ROWS[0]["name"], resolution, roster, indexes)
    assert review_reasons(resolution, verdict, "match", ROSTER_NTF2_FORMULA, roster, indexes) == []


# --------------------------------------------------------------------------- #
# Temperature facts
# --------------------------------------------------------------------------- #


def test_set_facts_read_the_temperature_column() -> None:
    payload = _ilset_payload("water", "H2O", [_data_row(298.15, 78.4), _data_row(298.15, 78.3)])
    facts = facts_from_set_payload(payload, "s3", url="u", http_status=200)
    assert facts.temperatures == (298.15,)
    assert facts.has_temperature_column is True
    assert facts.formula == "H2O"
    assert facts.epsilon_min == 78.3
    assert facts.epsilon_max == 78.4
    assert facts.n_rows == 2
    assert facts.http_status == 200


def test_set_facts_deduplicate_and_sort_temperatures() -> None:
    payload = _ilset_payload(
        "water", "H2O", [_data_row(303.15, 1.0), _data_row(293.15, 2.0), _data_row(303.15, 3.0)]
    )
    facts = facts_from_set_payload(payload, "s3", url="u", http_status=200)
    assert facts.temperatures == (293.15, 303.15)


def test_set_facts_count_zero_frequency_rows() -> None:
    payload = _ilset_payload(
        "water", "H2O", [_data_row(298.15, 1.0, frequency=0.0), _data_row(298.15, 2.0)]
    )
    facts = facts_from_set_payload(payload, "s3", url="u", http_status=200)
    assert (facts.n_zero_frequency_rows, facts.n_frequency_rows_above_zero) == (1, 1)


def test_set_facts_report_a_missing_temperature_column() -> None:
    payload = _ilset_payload(
        "water", "H2O", [_data_row(298.15, 1.0)],
        dhead=[["Pressure, kPa", None], ["Relative permittivity at zero frequency", "Liquid"]],
    )
    facts = facts_from_set_payload(payload, "s3", url="u", http_status=200)
    assert facts.has_temperature_column is False
    assert facts.temperatures == ()


def test_compound_temperature_unions_the_fetched_sets() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([
            {"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"},
            {"setid": "b", "datapoints": 1, "components": ["water"], "reference": "R"},
        ])
    )[0]
    facts = {
        "a": facts_from_set_payload(
            _ilset_payload("water", "H2O", [_data_row(293.15, 1.0)]), "a", url="u", http_status=200
        ),
        "b": facts_from_set_payload(
            _ilset_payload("water", "H2O", [_data_row(313.15, 2.0)]), "b", url="u", http_status=200
        ),
    }
    summary = compound_temperature(compound, facts)
    assert summary["n_sets_temperature_read"] == 2
    assert summary["n_distinct_temperatures"] == 2
    assert summary["temperature_span_K"] == pytest.approx(20.0)
    assert summary["temperature_span_class"] == "temperature_series"


def test_compound_temperature_is_empty_when_nothing_was_read() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([{"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"}])
    )[0]
    summary = compound_temperature(compound, {})
    assert summary == {
        "n_sets_temperature_read": 0,
        "n_distinct_temperatures": 0,
        "temperature_min_K": None,
        "temperature_max_K": None,
        "temperature_span_K": None,
        "temperature_span_class": "single_temperature",
    }


def test_compound_formula_prefers_the_ilset_payload() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([{"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"}])
    )[0]
    facts = {
        "a": facts_from_set_payload(
            _ilset_payload("water", "H2O", [_data_row(298.15, 1.0)]), "a", url="u", http_status=200
        )
    }
    assert compound_formula(compound, facts, {"water": "WRONG"}) == ("H2O", "ilset")


def test_compound_formula_falls_back_to_the_probe_sample() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([{"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"}])
    )[0]
    assert compound_formula(compound, {}, {"water": "H2O"}) == ("H2O", "probe_summary_sample")


def test_compound_formula_says_not_read_when_nothing_is_known() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([{"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"}])
    )[0]
    assert compound_formula(compound, {}, {}) == ("", "not_read")


# --------------------------------------------------------------------------- #
# lookup_pubchem failure paths
# --------------------------------------------------------------------------- #


def _lookup(name: str, routes: dict, *, limit: int = 10):
    return lookup_pubchem(
        name,
        http_get=_transport(routes),
        budget=RequestBudget(limit=limit),
        sleep=_noop_sleep,
        delay_seconds=0.0,
        expected_formula="",
        formula_of_smiles=lambda _smiles: None,
        status_counts=Counter(),
    )


def test_lookup_records_http_404_as_unresolved() -> None:
    routes = {build_pubchem_url(NOT_FOUND_NAME): _json({}, status=404)}
    resolution = _lookup(NOT_FOUND_NAME, routes)
    assert resolution.status == UNRESOLVED
    assert "HTTP 404" in resolution.note
    assert resolution.inchikey == ""


def test_lookup_records_a_transport_failure_as_unresolved() -> None:
    def boom():
        raise ConnectionError("DNS lookup failed")

    routes = {build_pubchem_url(BROKEN_NAME): boom}
    resolution = _lookup(BROKEN_NAME, routes)
    assert resolution.status == UNRESOLVED
    assert resolution.note.startswith("network_error:ConnectionError")
    assert resolution.inchikey == ""


def test_lookup_stops_when_the_budget_is_exhausted() -> None:
    routes = {build_pubchem_url(NOT_FOUND_NAME): _json({}, status=404)}
    resolution = _lookup(NOT_FOUND_NAME, routes, limit=0)
    assert resolution.status == NOT_QUERIED
    assert "budget exhausted" in resolution.note


def test_lookup_retries_a_transient_status_then_resolves() -> None:
    state = {"calls": 0}

    def flaky():
        state["calls"] += 1
        if state["calls"] == 1:
            return _json({}, status=503)
        return _json(_pubchem_payload(_candidate(9, "O", "KEY-A", "H2O")))

    routes = {build_pubchem_url("water"): flaky}
    resolution = _lookup("water", routes)
    assert state["calls"] == 2
    assert resolution.status == RESOLVED
    assert resolution.inchikey == "KEY-A"


def test_lookup_tries_the_repaired_spelling_after_a_404() -> None:
    typo = "1-hexylpyridinium bis(trifluromethylsulfonyl)imide"
    fixed = "1-hexylpyridinium bis(trifluoromethylsulfonyl)imide"
    routes = {
        build_pubchem_url(typo): _json({}, status=404),
        build_pubchem_url(fixed): _json(_pubchem_payload(_candidate(5, "O", "KEY-FIXED", "H2O"))),
    }
    resolution = _lookup(typo, routes)
    assert resolution.status == RESOLVED
    assert resolution.inchikey == "KEY-FIXED"


def test_lookup_marks_an_unparsable_payload_unresolved() -> None:
    routes = {build_pubchem_url("water"): HttpResponse(url="u", status=200, body=b"not json")}
    resolution = _lookup("water", routes)
    assert resolution.status == UNRESOLVED
    assert resolution.note.startswith("unparsable JSON payload")


# --------------------------------------------------------------------------- #
# run_resolution
# --------------------------------------------------------------------------- #


def test_offline_run_makes_no_requests_and_invents_nothing(tmp_path: Path) -> None:
    record = _run(tmp_path, {}, offline=True)
    assert record["requests"]["pubchem"]["used"] == 0
    assert record["requests"]["ilthermo_sets"]["used"] == 0
    assert record["offline"] is True
    assert record["temperature"]["verdict"].startswith("not read")
    for row in record["rows"]:
        if row["resolution_status"] != RESOLVED:
            assert row["resolved_inchikey"] == ""
        assert row["temperature_span_K"] == ""
        assert row["n_sets_temperature_read"] == "0"


def test_offline_run_still_uses_the_roster_identifiers(tmp_path: Path) -> None:
    record = _run(tmp_path, {}, offline=True)
    row = _row(record, ROSTER_ROWS[0]["name"])
    assert row["resolution_status"] == RESOLVED
    assert row["resolution_source"] == "roster_name_join"
    assert row["resolved_inchikey"] == ROSTER_NTF2_INCHIKEY
    assert row["resolved_smiles"] == ROSTER_NTF2_SMILES


def test_offline_roster_rows_are_not_queried(tmp_path: Path) -> None:
    record = _run(tmp_path, {}, offline=True)
    assert record["resolution"]["n_names_queried"] == 5
    assert record["resolution"]["status_counts"] == {NOT_QUERIED: 5}


def test_live_run_resolves_names_and_reports_the_split(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    assert record["population"]["n_pure_compounds"] == 8
    assert record["population"]["n_in_roster_by_name"] == 3
    assert record["population"]["n_new_to_roster_by_name"] == 5
    assert record["population"]["n_in_roster_total"] == 4
    assert record["population"]["n_new_compound_total"] == 4
    assert record["resolution"]["n_names_queried"] == 5
    assert record["resolution"]["status_counts"][RESOLVED] == 2
    assert record["resolution"]["status_counts"][UNRESOLVED] == 2
    assert record["resolution"]["status_counts"][AMBIGUOUS] == 1


def test_live_run_recovers_a_roster_compound_by_inchikey(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    row = _row(record, RECOVERABLE_NAME)
    assert row["in_roster"] == "true"
    assert row["roster_join_basis"] == "inchikey"
    assert row["roster_match_name"] == ROSTER_ROWS[3]["name"]
    assert record["resolution"]["recovered_into_roster_by_inchikey"] == [RECOVERABLE_NAME]
    assert row["needs_manual_review"] == "false"
    assert row["formula_check"] == "match"
    assert "disambiguated by the ILThermo molecular formula" in row["notes"]
    assert "PYRIDINIUM-CATION-ONLY-KEY" in row["notes"]


def test_live_run_flags_the_isomer_collision(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    row = _row(record, ISOMER_NAME)
    assert row["in_roster"] == "false"
    assert row["formula_check"] == "match"
    assert row["roster_formula_collisions"] == ROSTER_ROWS[0]["name"]
    assert row["needs_manual_review"] == "true"
    assert row["needs_manual_review_reason"].startswith("isomer_formula_collision_with_roster:")


def test_live_run_records_failures_without_inventing_identifiers(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    broken = _row(record, BROKEN_NAME)
    missing = _row(record, NOT_FOUND_NAME)
    ambiguous = _row(record, AMBIGUOUS_NAME)
    assert broken["resolution_status"] == UNRESOLVED
    assert broken["notes"].startswith("network_error:ConnectionError")
    assert broken["resolved_inchikey"] == ""
    assert missing["resolution_status"] == UNRESOLVED
    assert missing["resolved_inchikey"] == ""
    assert ambiguous["resolution_status"] == AMBIGUOUS
    assert ambiguous["resolved_inchikey"] == ""
    assert ambiguous["needs_manual_review"] == "true"


def test_live_run_reads_the_temperature_span(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes(), summary_payload=_probe_summary(CENSUS_SETS))
    row = _row(record, ISOMER_NAME)
    assert row["ilthermo_formula"] == ROSTER_NTF2_FORMULA
    assert row["formula_source"] == "ilset"
    assert row["temperature_min_K"] == "298.15"
    assert row["temperature_span_K"] == "0.00"
    assert row["n_distinct_temperatures"] == "1"
    assert row["temperature_span_class"] == "single_temperature"
    assert record["temperature"]["n_sets_read"] == 8
    assert record["temperature"]["facts_source"] == "live"
    assert record["temperature"]["n_compounds_with_temperature_read"] == 8
    assert record["temperature"]["n_compounds_with_multiple_set_temperatures"] == 0
    assert record["temperature"]["n_compounds_with_temperature_series"] == 0
    assert record["temperature"]["verdict"].startswith("0 of 8 pure compounds")


def test_live_run_notices_a_compound_that_does_vary_temperature(tmp_path: Path) -> None:
    routes = _dataset_routes(varying=True)
    routes.update(_pubchem_routes())
    record = _run(tmp_path, routes)
    row = _row(record, BROKEN_NAME)
    assert row["n_distinct_temperatures"] == "2"
    assert row["temperature_span_K"] == "10.00"
    assert row["temperature_span_class"] == "temperature_series"
    assert record["temperature"]["n_compounds_with_temperature_series"] == 1
    assert record["temperature"]["verdict"].startswith("1 of 8 pure compounds")


def test_set_failures_are_recorded_and_leave_the_temperature_blank(tmp_path: Path) -> None:
    routes = _pubchem_routes()
    routes[_set_key("s2")] = _json({}, status=403)
    record = _run(tmp_path, routes)
    row = _row(record, ISOMER_NAME)
    assert row["temperature_span_K"] == ""
    assert row["n_sets_temperature_read"] == "0"
    assert row["formula_source"] == "not_read"
    assert "ILThermo formula not read" in row["notes"]
    assert any(
        failure["setid"] == "s2" and failure["detail"] == "HTTP 403"
        for failure in record["failures"]
    )


def test_a_set_budget_cut_is_reported_once(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes(), set_budget_limit=2)
    budget_failures = [
        failure for failure in record["failures"] if "budget exhausted" in failure["detail"]
    ]
    assert len(budget_failures) == 1
    assert len(budget_failures[0]["setids_skipped"]) == 6
    assert record["requests"]["ilthermo_sets"]["used"] == 2


def test_max_names_trims_the_lookup_list(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes(), max_names=1)
    statuses = {row["ilthermo_name"]: row["resolution_status"] for row in record["rows"]}
    assert list(statuses.values()).count(NOT_QUERIED) == 4
    assert record["resolution"]["n_names_queried"] == 1


def test_a_pubchem_budget_cut_marks_the_rest_not_queried(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes(), request_budget_limit=1)
    cut = [
        row for row in record["rows"]
        if row["resolution_status"] == NOT_QUERIED and row["resolution_source"] == ""
    ]
    assert len(cut) == 4
    assert all("budget exhausted" in row["notes"] for row in cut)


def test_no_row_carries_an_identifier_it_did_not_earn(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    for row in record["rows"]:
        if row["resolution_status"] in {UNRESOLVED, AMBIGUOUS, NOT_QUERIED}:
            assert row["resolved_inchikey"] == ""
            assert row["resolved_smiles"] == ""
        if row["in_roster"] == "true":
            assert row["needs_manual_review"] == "false"


def test_out_of_scope_roster_rows_are_listed(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    assert record["roster_reconciliation"]["out_of_scope_rows"] == [ROSTER_ROWS[2]["name"]]


def test_every_request_is_logged(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    phases = {entry["phase"] for entry in record["request_log"]}
    assert phases == {"ilthermo_set", "pubchem_name"}
    assert record["requests"]["total_bytes_transferred"] > 0


def test_new_compounds_block_lists_the_unmatched_rows(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    names = [entry["ilthermo_name"] for entry in record["new_compounds"]]
    assert ISOMER_NAME in names
    assert ROSTER_ROWS[0]["name"] not in names
    # A compound the InChIKey join proves is already in the roster is not new:
    # it belongs to the normalisation catch, not to the coverage list.
    assert RECOVERABLE_NAME not in names
    assert len(names) == record["population"]["n_new_compound_total"] == 4


def test_generated_at_is_honoured(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    stamp = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)
    record = _run(tmp_path, _full_routes(), generated_at=stamp)
    assert record["generated_utc"] == "2026-09-25T12:00:00Z"


def test_span_class_splits_set_scatter_from_a_real_series() -> None:
    assert span_class(0, None) == "single_temperature"
    assert span_class(1, 0.0) == "single_temperature"
    assert span_class(2, 0.05) == "near_single"
    assert span_class(3, 2.0) == "near_single"
    assert span_class(15, 75.0) == "temperature_series"


def test_compound_temperature_keeps_a_two_kelvin_spread_out_of_the_series_bucket() -> None:
    compound = parse_probe_pure_compounds(
        _probe_summary([
            {"setid": "a", "datapoints": 1, "components": ["water"], "reference": "R"},
            {"setid": "b", "datapoints": 1, "components": ["water"], "reference": "R"},
        ])
    )[0]
    facts = {
        "a": facts_from_set_payload(
            _ilset_payload("water", "H2O", [_data_row(296.15, 1.0)]), "a", url="u", http_status=200
        ),
        "b": facts_from_set_payload(
            _ilset_payload("water", "H2O", [_data_row(298.15, 2.0)]), "b", url="u", http_status=200
        ),
    }
    summary = compound_temperature(compound, facts)
    assert summary["n_distinct_temperatures"] == 2
    assert summary["temperature_span_class"] == "near_single"


def test_set_facts_survive_a_dictionary_round_trip() -> None:
    payload = _ilset_payload("water", "H2O", [_data_row(298.15, 78.4, frequency=0.0)])
    fact = facts_from_set_payload(payload, "s3", url="u", http_status=200)
    assert set_facts_from_dict(set_facts_to_dict(fact)) == fact


def test_set_facts_from_dict_tolerates_missing_numbers() -> None:
    fact = set_facts_from_dict({"setid": "x"})
    assert fact.formula == ""
    assert fact.temperatures == ()
    assert fact.epsilon_min is None
    assert fact.http_status == 0


def test_read_facts_replay_requires_a_set_facts_block(tmp_path: Path) -> None:
    path = _write_summary(tmp_path, _probe_summary(CENSUS_SETS))
    with pytest.raises(ValueError):
        read_facts_replay(path)


def test_the_summary_stores_the_set_facts_for_later_replay(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    assert {entry["setid"] for entry in record["set_facts"]} == {f"s{i}" for i in range(1, 9)}
    assert record["temperature"]["facts_source"] == "live"


def test_a_stored_run_replays_without_touching_ilthermo(tmp_path: Path) -> None:
    first = _run(tmp_path, _full_routes())
    stored = tmp_path / "first_summary.json"
    stored.write_text(
        json.dumps({key: value for key, value in first.items() if key != "rows"}),
        encoding="utf-8",
    )
    second = run_resolution(
        http_get=_no_set_transport(_pubchem_routes()),
        probe_summary_path=_write_summary(tmp_path, _probe_summary(CENSUS_SETS)),
        roster_path=_write_roster(tmp_path),
        sleep=_noop_sleep,
        delay_seconds=0.0,
        facts_replay=read_facts_replay(stored),
    )
    assert second["requests"]["ilthermo_sets"]["used"] == 0
    assert second["temperature"]["facts_source"] == "replay"
    assert second["temperature"]["n_sets_read"] == 8
    for name in (ISOMER_NAME, BROKEN_NAME):
        assert _row(second, name)["temperature_span_K"] == _row(first, name)["temperature_span_K"]
        assert _row(second, name)["ilthermo_formula"] == _row(first, name)["ilthermo_formula"]


# --------------------------------------------------------------------------- #
# CSV output
# --------------------------------------------------------------------------- #


def test_write_csv_writes_lf_only(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "rows.csv"
    write_csv(path, [{"ilthermo_name": "x"}])
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8").splitlines()[0] == ",".join(CSV_FIELDS)


def test_write_csv_keeps_every_field_in_order(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    path = write_csv(tmp_path / "rows.csv", record["rows"])
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert list(rows[0]) == list(CSV_FIELDS)


def test_booleans_are_written_lowercase(tmp_path: Path) -> None:
    record = _run(tmp_path, _full_routes())
    values = {row["in_roster"] for row in record["rows"]}
    assert values <= {"true", "false"}


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #


def test_main_offline_writes_both_artifacts(tmp_path: Path) -> None:
    summary_path = _write_summary(tmp_path, _probe_summary(CENSUS_SETS))
    roster_path = _write_roster(tmp_path)
    csv_path = tmp_path / "out" / "ilthermo_new_compounds.csv"
    json_path = tmp_path / "out" / "summary.json"
    assert main([
        "--offline",
        "--probe-summary", str(summary_path),
        "--roster", str(roster_path),
        "--output", str(csv_path),
        "--summary", str(json_path),
    ]) == 0
    assert csv_path.is_file() and json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "rows" not in payload
    assert payload["population"]["n_pure_compounds"] == 8
    assert payload["offline"] is True
