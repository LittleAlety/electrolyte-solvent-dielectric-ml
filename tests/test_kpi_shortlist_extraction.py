"""Unit tests for the KPI SI Fig. S20 / S21 shortlist extraction.

The expected values in this file are the ones printed in the Supporting
Information of Gao et al. (Angew. Chem. Int. Ed. 2025, 64, e202416506), Fig. S20
(SI page SI31) and Fig. S21 (SI page SI32), transcribed by hand. They are
written out literally rather than recomputed, so a silent edit to the table
shows up as a failure.

One deliberate deviation from the task brief is documented here. The brief asks
for a 100% non-empty cas rate. The SI does not support that: Fig. S20 prints a
CAS ID for each of its 15 molecules, while Fig. S21 prints a SMILES instead and
no CAS ID at all for any of its 14. That is exactly what the paper says -- the
SI section 11 screening paragraph, the main-text abstract and the main-text
results section all describe the second shortlist as the one *without* CAS ID --
so the 100% assertion is pinned to the 15-row shortlist and a second test pins
the 14-row shortlist to "no CAS ID". Inventing 14 CAS IDs to satisfy the brief
would have been the dishonest alternative. See section 5 of
reports/kpi_shortlist_extraction.md for the full comparison.

Nothing here touches the network or the source PDFs: the tests read the three
committed artefacts and the probe module only.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from kpi_shortlist_extraction import (
    ALLOWED_FP_NOT_BELOW_BP,
    CSV_COLUMNS,
    EXPECTED_SI_SHA256,
    REDISTRIBUTABLE,
    SCREENING_GATES,
    SOURCE_KIND,
    USAGE,
    build_csv_text,
    cas_checksum_ok,
    shortlist_entries,
    validate_entries,
)

CSV_PATH = REPOSITORY_ROOT / "data" / "reference" / "kpi_15_14_shortlists.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "kpi_shortlist_extraction_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "kpi_shortlist_extraction.md"

EXPECTED_COLUMNS: tuple[str, ...] = (
    "shortlist",
    "rank",
    "cas",
    "smiles",
    "molwt",
    "mp_k",
    "bp_k",
    "fp_k",
    "source_figure",
    "source_page",
    "source_page_label",
    "source_kind",
    "redistributable",
    "usage",
    "notes",
)

# Fig. S20 (SI31): (cas, mp_k, bp_k, fp_k) in figure reading order.
EXPECTED_S20: tuple[tuple[str, str, str, str], ...] = (
    ("96-48-0", "228.2", "477.2", "371.5"),
    ("108-32-7", "224.4", "514.8", "389.2"),
    ("4437-69-8", "222.6", "504.3", "369.8"),
    ("4437-70-1", "217.3", "513.9", "367.4"),
    ("4437-85-8", "216.9", "514.2", "514.2"),
    ("6975-71-9", "227.8", "491.8", "365.0"),
    ("623-35-8", "220.9", "493.2", "384.9"),
    ("17611-82-4", "220.8", "499.5", "381.0"),
    ("4172-97-8", "228.9", "503.3", "372.8"),
    ("32091-48-8", "211.0", "508.8", "383.3"),
    ("15074-49-4", "221.2", "509.7", "374.7"),
    ("4553-62-2", "220.8", "508.6", "380.6"),
    ("16525-39-6", "228.7", "519.4", "383.2"),
    ("6959-71-3", "202.6", "467.2", "361.4"),
    ("35633-50-2", "221.6", "490.1", "368.1"),
)

# Fig. S21 (SI32): (smiles, mp_k, bp_k, fp_k) in figure reading order.
EXPECTED_S21: tuple[tuple[str, str, str, str], ...] = (
    ("O=COCC1COCO1", "229.2", "458.3", "360.6"),
    ("N#CCCCC1CCC1", "225.4", "489.3", "362.0"),
    ("N#CCCC1=CCCC1", "223.9", "492.6", "363.2"),
    ("N#CCCC1(CC1)C#N", "228.0", "525.0", "387.0"),
    ("CCC(CC#N)CC#N", "222.3", "513.8", "381.3"),
    ("CC(CCC#N)CC#N", "219.3", "519.2", "382.0"),
    ("CCC(CCC#N)C#N", "223.3", "514.2", "381.8"),
    ("C#CCCOCCCC#N", "224.7", "477.2", "361.9"),
    ("CC(COCC#N)C#N", "226.4", "497.7", "378.4"),
    ("CC(CCOC=O)C#N", "227.7", "474.8", "361.7"),
    ("CC(COC=O)CC#N", "221.4", "476.7", "363.8"),
    ("CC(CCC#N)C1CO1", "226.1", "499.2", "360.7"),
    ("N#CCCOC1CCC1", "226.4", "476.5", "365.8"),
    ("CC1COCC1CC#N", "228.7", "492.9", "361.0"),
)

# SI section 11, verbatim: 133,885 -> 51,001 -> (13,155 / 3,619 / 35) ->
# 15 with CAS ID + 20 without -> 14 after the retrosynthetic accessibility gate.
EXPECTED_CASCADE: dict[str, int] = {
    "qm9_molecules_collected": 133885,
    "after_structural_screening": 51001,
    "mp_below_230k": 13155,
    "bp_above_430k": 3619,
    "fp_above_360k": 35,
    "with_cas_id": 15,
    "without_cas_id": 20,
    "after_retrosynthetic_accessibility_gt_0.9": 14,
}

CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")


def _read_csv_rows() -> list[dict[str, str]]:
    with open(CSV_PATH, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_summary() -> dict:
    with open(SUMMARY_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _rows_for(shortlist: str) -> list[dict[str, str]]:
    return [row for row in _read_csv_rows() if row["shortlist"] == shortlist]


def test_csv_header_is_exactly_the_declared_schema() -> None:
    rows = _read_csv_rows()
    assert tuple(rows[0].keys()) == EXPECTED_COLUMNS
    assert CSV_COLUMNS == EXPECTED_COLUMNS


def test_csv_has_29_rows() -> None:
    assert len(_read_csv_rows()) == 29


def test_shortlist_distribution_is_15_and_14() -> None:
    counts: dict[str, int] = {}
    for row in _read_csv_rows():
        counts[row["shortlist"]] = counts.get(row["shortlist"], 0) + 1
    assert counts == {"15": 15, "14": 14}


def test_rank_runs_one_to_n_inside_each_shortlist() -> None:
    assert [row["rank"] for row in _rows_for("15")] == [str(i) for i in range(1, 16)]
    assert [row["rank"] for row in _rows_for("14")] == [str(i) for i in range(1, 15)]


def test_every_row_carries_a_figure_and_a_page() -> None:
    for row in _read_csv_rows():
        assert row["source_figure"].strip(), row
        assert row["source_page"].strip(), row
        assert int(row["source_page"]) > 0, row
        assert row["source_page_label"].strip(), row


def test_every_row_points_at_the_figure_its_shortlist_came_from() -> None:
    expected = {"15": ("Figure S20", "32", "SI31"), "14": ("Figure S21", "33", "SI32")}
    for row in _read_csv_rows():
        assert (
            row["source_figure"],
            row["source_page"],
            row["source_page_label"],
        ) == expected[row["shortlist"]], row


def test_shortlist_15_has_cas_on_every_row() -> None:
    """100% cas coverage, which the SI grants to exactly one of the two lists."""

    rows = _rows_for("15")
    assert len(rows) == 15
    assert [row for row in rows if row["cas"].strip()] == rows


def test_shortlist_14_has_no_cas_because_the_si_does_not_print_one() -> None:
    """The honest reading of Fig. S21, which prints a SMILES and no CAS ID.

    This is the deviation from the brief noted in the module docstring: the
    paper's own text (SI section 11, main-text abstract, main-text results)
    describes these 14 as the shortlist *without* CAS ID.
    """

    rows = _rows_for("14")
    assert len(rows) == 14
    assert [row for row in rows if row["cas"].strip()] == []


def test_cas_non_empty_rate_overall_is_15_of_29_not_100_percent() -> None:
    rows = _read_csv_rows()
    filled = [row for row in rows if row["cas"].strip()]
    assert len(filled) == 15
    assert round(len(filled) / len(rows), 4) == 0.5172


def test_every_printed_cas_matches_the_registry_format_for_the_check_digit_rule() -> None:
    for row in _rows_for("15"):
        assert CAS_PATTERN.match(row["cas"]), row
        assert cas_checksum_ok(row["cas"]), row


def test_cas_check_digit_rule_rejects_a_mutated_number() -> None:
    """The check-digit rule is only useful if it can fail."""

    assert cas_checksum_ok("96-48-0") is True
    assert cas_checksum_ok("96-48-1") is False
    assert cas_checksum_ok("not-a-cas") is False


def test_shortlist_14_has_smiles_on_every_row() -> None:
    rows = _rows_for("14")
    assert [row for row in rows if row["smiles"].strip()] == rows


def test_shortlist_15_has_no_smiles_because_the_si_draws_only_a_skeleton() -> None:
    assert [row for row in _rows_for("15") if row["smiles"].strip()] == []


def test_molwt_is_empty_on_every_row() -> None:
    """Neither figure prints a molecular weight, so nothing is back-filled."""

    assert [row["molwt"] for row in _read_csv_rows()] == [""] * 29


def test_mp_bp_fp_are_numeric_on_every_row() -> None:
    for row in _read_csv_rows():
        for field in ("mp_k", "bp_k", "fp_k"):
            value = float(row[field])
            assert 100.0 < value < 600.0, row


def test_every_row_satisfies_the_published_screening_gates() -> None:
    for row in _read_csv_rows():
        assert float(row["mp_k"]) < SCREENING_GATES["mp_below_k"], row
        assert float(row["bp_k"]) > SCREENING_GATES["bp_above_k"], row
        assert float(row["fp_k"]) > SCREENING_GATES["fp_above_k"], row


def test_only_one_row_has_fp_not_below_bp_and_it_is_the_pinned_one() -> None:
    """CAS 4437-85-8 prints FP = BP = 514.2 K; the row is kept verbatim."""

    offenders = [
        (int(row["shortlist"]), int(row["rank"]))
        for row in _read_csv_rows()
        if float(row["fp_k"]) >= float(row["bp_k"])
    ]
    assert offenders == sorted(ALLOWED_FP_NOT_BELOW_BP)


def test_table_matches_the_hand_transcribed_figures() -> None:
    assert [(r["cas"], r["mp_k"], r["bp_k"], r["fp_k"]) for r in _rows_for("15")] == list(
        EXPECTED_S20
    )
    assert [(r["smiles"], r["mp_k"], r["bp_k"], r["fp_k"]) for r in _rows_for("14")] == list(
        EXPECTED_S21
    )


def test_discipline_fields_ride_on_every_row() -> None:
    for row in _read_csv_rows():
        assert row["source_kind"] == SOURCE_KIND == "compilation_from_published_si"
        assert row["redistributable"] == REDISTRIBUTABLE == "false"
        assert row["usage"] == USAGE == "cross_check_only"
        assert row["notes"].strip(), row


def test_csv_is_utf8_without_bom_and_lf_only() -> None:
    payload = CSV_PATH.read_bytes()
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in payload
    assert payload.decode("utf-8").count("\n") == 30


def test_summary_and_report_are_utf8_without_bom_and_lf_only() -> None:
    for path in (SUMMARY_PATH, REPORT_PATH):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf"), path
        assert b"\r\n" not in payload, path


def test_summary_has_the_key_fields() -> None:
    summary = _read_summary()
    for key in (
        "schema_version",
        "probe",
        "source",
        "discipline",
        "extraction_method",
        "paper_declared_cascade",
        "paper_declared_cascade_provenance",
        "figure_sources",
        "coverage",
        "validation",
        "anomalies",
        "entries",
    ):
        assert key in summary, key
    assert summary["probe"] == "kpi_shortlist_extraction"
    assert summary["source"]["si_pdf"]["pages"] == 64
    assert summary["source"]["si_pdf"]["sha256"] == EXPECTED_SI_SHA256


def test_summary_records_the_paper_declared_cascade_verbatim() -> None:
    cascade = _read_summary()["paper_declared_cascade"]
    for key, value in EXPECTED_CASCADE.items():
        assert cascade[key] == value, key
    assert cascade["final_shortlists"] == "15 + 14"
    assert cascade["staged_thresholds_k"] == {"mp_below": 230, "bp_above": 430, "fp_above": 360}


def test_summary_marks_the_cascade_as_not_recomputed() -> None:
    provenance = _read_summary()["paper_declared_cascade_provenance"]
    assert provenance["recomputed_by_this_project"] is False
    assert "未经我方复算" in provenance["note"]
    assert "133,885" in provenance["note"]


def test_summary_quotes_the_si_section_11_paragraph() -> None:
    """When the SI text layer was readable, it must carry the printed funnel."""

    text_layer = _read_summary()["si_cascade_text_layer"]
    if not text_layer.get("found"):
        pytest.skip("SI text layer was not available when the summary was written")
    assert text_layer["page_label"] == "SI11"
    assert text_layer["qm9_molecules_collected"] == 133885
    assert text_layer["after_structural_screening"] == 51001
    assert tuple(text_layer["staged_counts"]) == (13155, 3619, 35)
    assert tuple(text_layer["staged_thresholds"]) == (230, 430, 360)
    assert tuple(text_layer["cas_split"]) == (15, 20)
    assert text_layer["after_sa_score"] == 14


def test_summary_discipline_block_forbids_redistribution() -> None:
    discipline = _read_summary()["discipline"]
    assert discipline["source_kind"] == "compilation_from_published_si"
    assert discipline["redistributable"] is False
    assert discipline["usage"] == "cross_check_only"
    assert "不得当作可再分发的数据集" in discipline["statement"]


def test_summary_coverage_agrees_with_the_csv() -> None:
    summary = _read_summary()
    rows = _read_csv_rows()
    assert summary["coverage"]["rows"] == len(rows) == 29
    assert summary["coverage"]["by_shortlist"] == {"15": 15, "14": 14}
    fields = summary["coverage"]["fields"]
    for field in ("cas", "smiles", "molwt", "mp_k", "bp_k", "fp_k", "source_figure"):
        expected = sum(1 for row in rows if row[field].strip())
        assert fields[field]["non_empty"] == expected, field
        assert fields[field]["rows"] == 29
    assert summary["coverage"]["per_shortlist"]["15"]["cas_non_empty"] == 15
    assert summary["coverage"]["per_shortlist"]["14"]["cas_non_empty"] == 0
    assert summary["coverage"]["per_shortlist"]["15"]["smiles_non_empty"] == 0
    assert summary["coverage"]["per_shortlist"]["14"]["smiles_non_empty"] == 14


def test_summary_carries_the_same_29_rows_as_the_csv() -> None:
    summary = _read_summary()
    assert summary["entries"] == _read_csv_rows()


def test_summary_validation_has_no_problems() -> None:
    summary = _read_summary()
    assert summary["validation"]["problems"] == []
    assert summary["validation"]["checks"], "the machine checks should not be empty"
    assert all(check["status"] == "pass" for check in summary["validation"]["checks"])


def test_probe_revalidates_the_table_as_clean() -> None:
    report = validate_entries(shortlist_entries())
    assert report["problems"] == []
    assert all(check["status"] == "pass" for check in report["checks"])


def test_probe_rerender_matches_the_csv_on_disk() -> None:
    assert build_csv_text(shortlist_entries()) == CSV_PATH.read_text(encoding="utf-8")


def test_probe_pins_the_si_digest_it_was_built_from() -> None:
    assert len(EXPECTED_SI_SHA256) == 64
    assert set(EXPECTED_SI_SHA256) <= set("0123456789abcdef")


def test_summary_lists_the_anomalies_the_report_must_carry() -> None:
    ids = {item["id"] for item in _read_summary()["anomalies"]}
    assert "fp_equals_bp_on_shortlist_15_rank_5" in ids
    assert "figure_s21_caption_contradicts_the_screening_text" in ids
    assert "molwt_never_printed" in ids


def test_report_exists_and_forbids_redistribution() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "本表不得当作可再分发的数据集" in text
    assert "cross_check_only" in text


def test_report_carries_all_29_rows_and_the_cascade() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    for row in _read_csv_rows():
        key = row["cas"] if row["shortlist"] == "15" else row["smiles"]
        assert key in text, key
    for value in ("133,885", "51,001", "13,155", "3,619"):
        assert value in text, value


def test_report_states_that_the_cascade_was_not_recomputed() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "未经复算" in text
    assert "以 SI 实际文字" in text
