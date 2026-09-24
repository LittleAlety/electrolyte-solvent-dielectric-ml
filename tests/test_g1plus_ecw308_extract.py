from __future__ import annotations

import json
from pathlib import Path

import pytest

from probes.g1plus_ecw308_extract import (
    AGREEMENT_BANDS,
    DEFAULT_CROSSCHECK,
    DEFAULT_DATASET,
    DEFAULT_OUTPUT,
    DEFAULT_PDF,
    FALLBACK_BAND,
    TABLE_ROWS,
    Token,
    _cell_status,
    _formula_for,
    _name_for,
    _references_for,
    band_cells,
    canonical_name,
    classify,
    crosscheck,
    dielectric_band,
    parse_references,
    row_starts,
    write_json,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The eleven values the v0.3.6 tier-2 pass read by hand from this SI. They are
# the extractor's ground truth: if a refactor moves any of them, the automated
# reading of the other 297 rows is not trustworthy either.
HAND_READ_ANCHORS = {
    38: "37.00",
    52: "37.00",
    53: "30.00",
    96: "7.40",
    104: "7.53",
    158: "89.00",
    159: "64.90",
    163: "126.00",
    166: "78.40",
    209: "43.00",
}

# Row 51 (MOPN) prints two stacked values, so it is asserted separately: the
# cell must keep both numbers and must not be collapsed into a value.
STACKED_ANCHOR = (51, ("36.00", "25.00"))

# Rows whose identity the extractor previously got wrong: rows 1, 3, 4 and 9
# had their labels taken over by the header word and by formula subscripts.
ROW_IDENTITY = {
    1: ("formamide", "CH3NO"),
    3: ("dimethyl acetamide", "C4H9NO"),
    4: ("methylacetamide", "C3H7NO"),
    9: ("urea", "CH4N2O"),
    38: ("acetonitrile", "C2H3N"),
    96: ("diglyme", "C6H14O3"),
    163: ("vinylene carbonate", "C3H2O3"),
}


def _evidence() -> dict:
    return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))


def _crosscheck() -> dict:
    return json.loads(DEFAULT_CROSSCHECK.read_text(encoding="utf-8"))


def test_band_is_derived_from_the_printed_header_positions() -> None:
    tokens = [
        Token(1, 452.0, 500.0, "Viscosity"),
        Token(1, 521.0, 500.0, "Dielectric"),
        Token(1, 599.0, 500.0, "Ionic"),
    ]
    assert dielectric_band(tokens) == (486.5, 560.0)


def test_band_falls_back_when_the_header_is_absent() -> None:
    assert dielectric_band([Token(1, 300.0, 500.0, "Solvent")]) == FALLBACK_BAND


def test_row_numbers_must_arrive_in_order() -> None:
    tokens = [
        Token(1, 100.0, 500.0, "1. Formamide"),
        Token(1, 100.0, 475.0, "2. Dimethyl formamide"),
        Token(1, 100.0, 450.0, "4. N-methylacetamide"),
    ]
    starts, reached = row_starts(tokens, (1, 2))
    assert [start.text for start in starts] == ["1. Formamide", "2. Dimethyl formamide"]
    assert reached == 2


def test_row_279_without_a_full_stop_is_still_numbered() -> None:
    # Row 279 of the SI prints its number without the trailing period.
    tokens = [Token(9, 100.0, 500.0 - 24.0 * (index - 1), f"{index}.") for index in range(1, 279)]
    tokens.append(Token(9, 88.0, 500.0 - 24.0 * 279, "279"))
    starts, reached = row_starts(tokens, (1, 10))
    assert reached == 279
    assert starts[-1].text == "279"


def test_a_stray_bare_integer_never_opens_a_row() -> None:
    # The header prints "Category 1" and formulas print subscripts such as the
    # "3" of C3H7NO. Neither may be mistaken for a row label.
    tokens = [Token(1, 100.0, 500.0, "1."), Token(1, 188.0, 474.0, "2")]
    starts, reached = row_starts(tokens, (1, 2))
    assert reached == 1
    assert [start.text for start in starts] == ["1."]


def test_formula_window_is_bounded_by_the_next_row_label() -> None:
    start = Token(2, 120.3, 230.3, "38.")
    follower = Token(2, 147.3, 204.4, "39. Propanenitrile")
    scoped = [
        start,
        Token(2, 154.5, 218.3, "C"),
        Token(2, 161.5, 217.4, "2"),
        Token(2, 165.0, 218.3, "H"),
        Token(2, 172.7, 217.4, "3"),
        Token(2, 176.1, 218.3, "N"),
        follower,
    ]
    formula, line = _formula_for(start, scoped, follower)
    assert formula == "C2H3N"
    assert {token.text for token in scoped if id(token) in line} == {"C", "2", "H", "3", "N"}


def test_formula_window_reaches_a_wrapped_row_without_taking_its_neighbour() -> None:
    # Rows whose names wrap sit on a 48.7 pt pitch and push the formula 36.3 pt
    # below the label, past the old fixed 35 pt cap. The next row's formula sits
    # one whole pitch further down and must stay unclaimed.
    start = Token(2, 122.5, 495.0, "88.")
    follower = Token(2, 101.4, 446.3, "89.")
    scoped = [
        start,
        Token(2, 146.3, 458.7, "C"),
        Token(2, 153.4, 457.8, "5"),
        Token(2, 156.9, 458.7, "H"),
        Token(2, 164.5, 457.8, "10"),
        Token(2, 171.5, 458.7, "F"),
        Token(2, 177.4, 457.8, "2"),
        Token(2, 180.7, 458.7, "O"),
        Token(2, 188.4, 457.8, "2"),
        follower,
        Token(2, 148.1, 410.0, "C"),
        Token(2, 158.7, 410.0, "H"),
        Token(2, 169.8, 410.0, "F"),
        Token(2, 179.1, 410.0, "O"),
    ]
    assert _formula_for(start, scoped, follower)[0] == "C5H10F2O2"
    # The follower's own window stops before the row below it, so it reads the
    # reduced formula and never inherits its predecessor's.
    assert _formula_for(follower, scoped, None)[0] == "CHFO"


def test_a_formula_that_crosses_a_page_break_is_still_read() -> None:
    # Entries 43 and 116 print their formula at the very top of the *following*
    # page, above the label of that page's first row.
    start = Token(70, 115.9, 104.1, "43.")
    follower = Token(71, 118.3, 479.7, "44.")
    scoped = [
        start,
        Token(70, 131.8, 104.1, "Methoxypropionitrile"),
        follower,
        Token(71, 150.7, 495.0, "C"),
        Token(71, 157.8, 494.0, "4"),
        Token(71, 161.3, 495.0, "H"),
        Token(71, 169.0, 494.0, "7"),
        Token(71, 172.3, 495.0, "NO"),
    ]
    assert _formula_for(start, scoped, follower)[0] == "C4H7NO"
    # The same tokens must not leak into the next row's window.
    assert _formula_for(follower, scoped, None)[0] is None


def test_a_number_far_to_the_right_never_opens_a_row() -> None:
    tokens = [Token(1, 290.0, 500.0, "1.")]
    starts, reached = row_starts(tokens, (1, 2))
    assert starts == []
    assert reached == 0


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["89.00"], "value"),
        (["/"], "blank"),
        ([], "missing"),
        (["36.00", "25.00"], "stacked"),
    ],
)
def test_cell_status(texts: list[str], expected: str) -> None:
    status, _cell, _value = _cell_status(texts)
    assert status == expected


def test_stacked_cell_is_never_collapsed_to_a_value() -> None:
    status, cell, value = _cell_status(["36.00", "25.00"])
    assert (status, cell, value) == ("stacked", "36.00 25.00", None)


def test_cell_ownership_uses_the_row_block_not_the_nearest_row() -> None:
    starts = [Token(1, 100.0, 500.0, "1."), Token(1, 100.0, 470.0, "2.")]
    in_block = Token(1, 529.6, 483.0, "44.00")
    above_block = Token(1, 529.6, 481.0, "1.00")
    cells, unclaimed = band_cells(starts, [in_block, above_block], (486.3, 559.7))
    assert [token.text for token in cells[(1, 500.0)]] == ["44.00", "1.00"]
    assert unclaimed == []


def test_a_cell_below_every_row_block_is_reported_unclaimed() -> None:
    starts = [Token(1, 100.0, 500.0, "1.")]
    far = Token(1, 529.6, 470.0, "44.00")
    cells, unclaimed = band_cells(starts, [far], (486.3, 559.7))
    assert cells == {}
    assert unclaimed and unclaimed[0]["text"] == "44.00"


def test_reference_cells_are_read_line_by_line() -> None:
    start = Token(1, 100.0, 416.6, "158.")
    scoped = [
        start,
        Token(1, 732.7, 420.1, "["),
        Token(1, 735.0, 420.1, "16"),
        Token(1, 741.9, 420.1, ","),
        Token(1, 745.5, 420.1, "34"),
        Token(1, 752.5, 420.1, ","),
        Token(1, 738.8, 407.9, "36"),
        Token(1, 745.8, 407.9, "]"),
    ]
    assert _references_for(start, scoped) == [16, 34, 36]


def test_formula_is_assembled_left_to_right_across_baselines() -> None:
    start = Token(1, 106.7, 416.6, "158.")
    scoped = [
        start,
        Token(1, 152.8, 404.5, "C"),
        Token(1, 163.3, 404.5, "H"),
        Token(1, 174.4, 404.5, "O"),
        Token(1, 159.9, 403.5, "3"),
        Token(1, 171.0, 403.5, "4"),
        Token(1, 182.1, 403.5, "3"),
    ]
    formula, line = _formula_for(start, scoped)
    assert formula == "C3H4O3"
    assert [token.text for token in scoped if id(token) in line] == [
        "C",
        "H",
        "O",
        "3",
        "4",
        "3",
    ]


def test_name_does_not_repeat_an_overlapping_chunk() -> None:
    start = Token(1, 117.0, 271.2, "52. Glutaronitrile (GLN)")
    scoped = [start, Token(1, 117.0, 271.2, "Glutaronitrile (GLN)")]
    assert _name_for(start, scoped) == "Glutaronitrile (GLN)"


def test_locants_survive_the_duplicate_guard() -> None:
    # The previous guard dropped a token whenever its text appeared inside an
    # earlier one, so "1" already present in "91." vanished and the ester lost
    # both of its locants. Locants and repeated hyphens must both survive.
    start = Token(5, 86.5, 372.8, "91.")
    scoped = [
        start,
        *(Token(5, x, 372.8, text) for x, text in [
            (102.4, "1"),
            (107.7, "-"),
            (111.1, "(2"),
            (119.9, "-"),
            (123.4, "Fluoroethoxy)"),
            (183.5, "-"),
            (187.0, "2"),
            (192.3, "-"),
            (195.7, "ethoxyethane"),
        ]),
    ]
    assert _name_for(start, scoped) == "1 - (2 - Fluoroethoxy) - 2 - ethoxyethane"


def test_row_279_drops_its_bare_label() -> None:
    start = Token(9, 88.2, 369.2, "279")
    scoped = [
        start,
        *(Token(9, x, 369.2, text) for x, text in [
            (104.1, "."),
            (109.3, "1"),
            (114.6, "-"),
            (118.1, "Methyl"),
            (148.3, "-"),
            (151.8, "2"),
            (157.1, "-"),
            (160.6, "pyrrolidinone"),
            (220.3, "(NMP)"),
        ]),
    ]
    assert _name_for(start, scoped) == "1 - Methyl - 2 - pyrrolidinone (NMP)"


def test_locants_on_a_continuation_line_survive() -> None:
    # The first version of the continuation rule refused every numeric token,
    # which deleted the "3" of "3-Methoxysulfolane". Real PDF tokens for row 235
    # are reproduced here, plus the neighbouring value cell of the row above.
    start = Token(9, 159.9, 203.0, "235.")
    scoped = [
        start,
        Token(9, 277.1, 196.0, "127.00"),
        Token(9, 126.5, 190.8, "3"),
        Token(9, 131.8, 190.8, "-"),
        Token(9, 135.3, 190.8, "Methoxysulfolane"),
        Token(9, 151.6, 178.7, "(MESL)"),
    ]
    assert _name_for(start, scoped) == "3 - Methoxysulfolane (MESL)"


def test_a_decimal_value_cell_in_the_name_column_is_refused() -> None:
    # Only the decimal form is a value cell; a single digit in the same place is
    # a locant and must be kept (see the test above).
    start = Token(2, 133.5, 369.2, "7.")
    scoped = [
        start,
        Token(2, 144.0, 369.2, "Isobutyramide"),
        Token(2, 150.0, 363.2, "127.00"),
    ]
    assert _name_for(start, scoped) == "Isobutyramide"


def test_reference_list_parser_keeps_the_full_citation() -> None:
    pages = ["References\n[1] A. Author, J. Journal 2020, 1, 1.\n[2] B. Writer, X 2021.\n"]
    parsed = parse_references(pages)
    assert parsed["1"].startswith("A. Author")
    assert parsed["2"].startswith("B. Writer")


def test_canonical_name_drops_parentheticals() -> None:
    assert canonical_name("Ethylene carbonate (EC)") == "ethylene carbonate"
    assert canonical_name("1,2-Dimethoxyethane (DME)") == "1 2 dimethoxyethane"


@pytest.mark.parametrize(
    ("relative_delta", "expected"),
    [
        (0.004, "agree_within_1pct"),
        (-0.03, "agree_within_5pct"),
        (0.07, "divergent"),
    ],
)
def test_classify(relative_delta: float, expected: str) -> None:
    assert classify(relative_delta) == expected
    assert expected in {"divergent", *(label for _, label in AGREEMENT_BANDS)}


def _tiny_evidence(rows: list[dict]) -> dict:
    return {"rows": rows, "summary": {}}


def _row(index: int, name: str, formula: str | None, value: float | None, status: str) -> dict:
    return {
        "index": index,
        "name": name,
        "formula": formula,
        "dielectric_value": value,
        "dielectric_status": status,
        "dielectric_cell": None if value is None else f"{value:.2f}",
        "references": [],
    }


def test_crosscheck_refuses_a_formula_only_pair(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_text(
        "inchikey,smiles,name,dielectric,T_K\n"
        "QTBSBXVTEAMEQO-UHFFFAOYSA-N,CC(=O)O,acetic acid,6.15,293.15\n",
        encoding="utf-8",
        newline="\n",
    )
    evidence = _tiny_evidence([_row(112, "Methyl formate", "C2H4O2", 8.5, "value")])
    report = crosscheck(evidence, dataset)
    entry = report["entries"][0]
    assert entry["status"] == "formula_only_candidate"
    assert entry["formula_candidates"] == ["acetic acid"]
    assert report["summary"]["divergent"] == 0


def test_crosscheck_matches_when_the_identity_claim_agrees(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_text(
        "inchikey,smiles,name,dielectric,T_K\n"
        "RUOJZAUFBMNUDX-UHFFFAOYSA-N,CC1COC(=O)O1,propylene carbonate,64.9,298.15\n",
        encoding="utf-8",
        newline="\n",
    )
    evidence = _tiny_evidence([_row(159, "Propylene carbonate (PC)", "C4H6O3", 64.9, "value")])
    report = crosscheck(evidence, dataset)
    entry = report["entries"][0]
    assert entry["status"] == "agree_within_1pct"
    assert entry["relative_delta"] == 0.0


def test_crosscheck_reports_a_stacked_cell_without_matching_it(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_text(
        "inchikey,smiles,name,dielectric,T_K\n"
        "OOWFYDWAMOKVSF-UHFFFAOYSA-N,COCCC#N,3-methoxypropionitrile,36.0,298.15\n",
        encoding="utf-8",
        newline="\n",
    )
    row = _row(51, "3-Methoxypropionitrile", "C4H7NO", None, "stacked")
    row["dielectric_cell"] = "36.00 25.00"
    report = crosscheck(_tiny_evidence([row]), dataset)
    entry = report["entries"][0]
    assert entry["status"] == "ecw_stacked"
    assert entry["stacked_values"] == [36.0, 25.0]
    assert entry["dataset_value_in_cell"] is True
    assert report["summary"]["matched"] == 0


def test_committed_evidence_reproduces_the_hand_read_anchors() -> None:
    rows = {row["index"]: row for row in _evidence()["rows"]}
    for index, expected in HAND_READ_ANCHORS.items():
        row = rows[index]
        assert row["dielectric_cell"] == expected, f"row {index} cell drifted"
        assert row["dielectric_value"] == pytest.approx(float(expected))
        assert row["dielectric_status"] == "value"
    index, values = STACKED_ANCHOR
    stacked = rows[index]
    assert stacked["dielectric_status"] == "stacked"
    assert stacked["dielectric_value"] is None
    for value in values:
        assert value in (stacked["dielectric_cell"] or "")


def test_committed_evidence_keeps_row_identity() -> None:
    rows = {row["index"]: row for row in _evidence()["rows"]}
    for index, (name, formula) in ROW_IDENTITY.items():
        row = rows[index]
        assert name in row["name"].lower(), f"row {index} name drifted: {row['name']!r}"
        assert row["formula"] == formula, f"row {index} formula drifted"


def test_committed_evidence_covers_every_row_of_table_s3() -> None:
    evidence = _evidence()
    assert evidence["summary"]["row_index_sequence_complete"] is True
    assert evidence["summary"]["row_index_sequence_reached"] == TABLE_ROWS
    assert len(evidence["rows"]) == TABLE_ROWS


def test_committed_evidence_reads_the_wrapped_and_cross_page_entries() -> None:
    rows = {row["index"]: row for row in _evidence()["rows"]}
    # Row 88 and 89 wrap their name over three printed lines; the continuation
    # carries the abbreviation that the identity gate needs to see.
    assert rows[88]["name"].endswith("methoxyethoxy)ethane (DFEME)")
    assert rows[88]["formula"] == "C5H10F2O2"
    assert rows[89]["formula"] == "C5H9F3O3"
    # Rows 43 (MOPN) and 116 print their formula after a page break.
    assert rows[43]["formula"] == "C4H7NO"
    assert rows[116]["formula"] == "C5H10O2"
    # Row 279's label is a bare "279" followed by a separate "." token.
    assert rows[279]["name"] == "1 - Methyl - 2 - pyrrolidinone (NMP)"
    assert "279" not in rows[279]["name"]


def test_every_valued_row_of_the_table_carries_a_formula() -> None:
    report = _crosscheck()
    # The two earlier hold-outs (43 and 116) are read across their page break,
    # so no valued row is left without the identity gate's input.
    assert report["summary"]["ecw_no_formula"] == 0
    assert report["summary"]["matched"] == 27
    assert report["summary"]["agree_within_1pct"] == 11
    assert report["summary"]["agree_within_5pct"] == 10
    assert report["summary"]["divergent"] == 6
    assert report["summary"]["formula_only_candidate"] == 19


@pytest.mark.parametrize(
    ("index", "dataset_name", "dataset_value"),
    [
        (109, "Butyl acetate", 5.01),
        (280, "Acetone", 20.7),
        (283, "N-methylpyrrolidone", 32.2),
    ],
)
def test_same_cid_synonyms_are_gated_on_identity(
    index: int, dataset_name: str, dataset_value: float
) -> None:
    # Each pair was confirmed to be one structure by PubChem PUG-REST (same
    # CID), so the row may be matched on identity rather than on formula alone.
    entry = next(e for e in _crosscheck()["entries"] if e["ecw_index"] == index)
    assert entry["status"] == "agree_within_1pct"
    assert entry["dataset_name"] == dataset_name
    assert entry["dataset_dielectric"] == pytest.approx(dataset_value)


def test_a_candidate_without_a_name_claim_stays_a_candidate() -> None:
    # ECW prints "Methoxypropionitrile" with no locant; the dataset entry is
    # "3-methoxypropionitrile". Without a locant the two names do not establish
    # identity (2-methoxypropionitrile is a different molecule), so the row must
    # stay a candidate instead of becoming a match or a conflict.
    entry = next(e for e in _crosscheck()["entries"] if e["ecw_index"] == 43)
    assert entry["status"] == "formula_only_candidate"
    assert entry["formula_candidates"] == ["3-methoxypropionitrile"]


def test_committed_evidence_resolves_the_ecw_citation_numbers() -> None:
    references = _evidence()["references"]
    assert references["3"].startswith("D. S. Hall")
    assert references["16"].startswith("B. Flamme")
    assert references["34"].startswith("H. Duncan")
    assert references["36"].startswith("E. Perricone")


def test_committed_crosscheck_never_claims_a_formula_only_conflict() -> None:
    report = _crosscheck()
    for entry in report["entries"]:
        if entry["status"] == "divergent":
            assert entry["dataset_name"]
            assert entry["relative_delta"] != 0
            assert abs(entry["relative_delta"]) > 0.05
        assert entry["status"] != "ambiguous_formula"


def test_committed_crosscheck_handles_the_known_fluorine_conflict() -> None:
    entry = next(e for e in _crosscheck()["entries"] if e["ecw_index"] == 166)
    assert entry["status"] == "divergent"
    assert entry["ecw_dielectric"] == 78.4
    assert entry["dataset_dielectric"] == 102


def test_evidence_file_is_lf_only_and_endswith_newline() -> None:
    for path in (DEFAULT_OUTPUT, DEFAULT_CROSSCHECK):
        raw = path.read_bytes()
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")


def test_write_json_is_lf_only(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"probe": "x"})
    raw = target.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_extraction_writes_the_expected_shapes() -> None:
    evidence = _evidence()
    assert set(evidence) >= {"schema_version", "probe", "source", "method", "summary", "rows"}
    assert evidence["source"]["sha256"]
    assert len(evidence["references"]) == evidence["summary"]["references_parsed"]


@pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="SI PDF is not present locally")
def test_committed_evidence_reproduces_from_the_pinned_pdf() -> None:
    from probes.g1plus_ecw308_extract import build_evidence

    assert build_evidence(DEFAULT_PDF) == _evidence()


@pytest.mark.skipif(not DEFAULT_DATASET.exists(), reason="dataset is not present")
def test_dataset_still_carries_the_rows_the_crosscheck_reads() -> None:
    text = DEFAULT_DATASET.read_text(encoding="utf-8")
    assert "fluoroethylene carbonate" in text
    assert REPOSITORY_ROOT / "data" / "dielectric_v03.csv" == DEFAULT_DATASET
