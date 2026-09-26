"""Guards for the Reaxys render-gap closure artifacts.

The CSV is a transcription of a manual, logged-in Reaxys session, so it cannot
be re-derived offline. It is pinned by its own declarations instead: the
declared-vs-rendered counts, the rows that only appeared after "Show all", and
the two open items the prior round left behind. The load-bearing claim is a
falsification -- the missing tetraglyme row was guessed to be a 39.99 C point
and turned out to be a value-less citation stub -- so that must survive in both
the CSV note and the report.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "probes"
CSV_PATH = ARTIFACT_DIR / "reaxys_render_gap_closure.csv"
JSON_PATH = ARTIFACT_DIR / "reaxys_render_gap_closure_summary.json"
MD_PATH = REPO_ROOT / "reports" / "reaxys_render_gap_closure.md"
VERIFIER = ARTIFACT_DIR / "verify_reaxys_render_gap_closure.py"
PRIOR_PATH = ARTIFACT_DIR / "reaxys_v1x_stocking_scan_summary.json"
OBS_PATH = REPO_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"

EXPECTED_FIELDS = [
    "query_id", "compound", "short", "cas", "reaxys_registry_number",
    "reaxys_property_category", "reaxys_declared_entries", "rendered_without_show_all",
    "rendered_with_show_all", "row_index", "value", "frequency_Hz", "temperature_C",
    "location", "comment", "reference", "provenance_tag", "access", "note",
]

# query_id -> (declared, rendered_before_show_all, rendered_after_show_all)
QUERY_COUNTS = {
    "query_1_pc": (10, 7, 10),
    "query_2_tetraglyme": (8, 7, 8),
}
PC_NEW_ROWS = {8: "64", 9: "64.4", 10: ""}
SHOW_ALL_AFTER = "Show all 后新读到"

PC_KEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
TG_KEY = "ZUHZGEOKBKGPSW-UHFFFAOYSA-N"

FROZEN_DIGESTS = {
    "data/dielectric_v03.csv":
        "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv":
        "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json":
        "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv":
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    return _rows(CSV_PATH)


@pytest.fixture(scope="module")
def summary() -> dict[str, object]:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prior() -> dict[str, object]:
    return json.loads(PRIOR_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_query(rows: list[dict[str, str]]) -> dict[str, dict[int, dict[str, str]]]:
    out: dict[str, dict[int, dict[str, str]]] = {}
    for row in rows:
        out.setdefault(row["query_id"], {})[int(row["row_index"])] = row
    return out


def test_artifacts_are_lf_only_without_bom() -> None:
    for path in (CSV_PATH, JSON_PATH, MD_PATH):
        raw = path.read_bytes()
        assert b"\r\n" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path


def test_csv_header_is_the_declared_contract(rows: list[dict[str, str]]) -> None:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        assert csv.DictReader(handle).fieldnames == EXPECTED_FIELDS


def test_csv_row_count_is_eighteen(rows: list[dict[str, str]]) -> None:
    assert len(rows) == 18
    assert {r["query_id"] for r in rows} == set(QUERY_COUNTS)


def test_each_compound_declares_the_right_counts(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    for qid, (declared, pre, post) in QUERY_COUNTS.items():
        block = by_query[qid]
        assert len(block) == post
        assert {r["reaxys_declared_entries"] for r in block.values()} == {str(declared)}
        assert {r["rendered_without_show_all"] for r in block.values()} == {str(pre)}
        assert {r["rendered_with_show_all"] for r in block.values()} == {str(post)}
        assert declared >= post > pre


def test_the_show_all_gap_is_the_whole_story(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    """Exactly the rows past the pre-collapse render count are the new ones."""
    for qid, (_, pre, post) in QUERY_COUNTS.items():
        newly = sorted(i for i, r in by_query[qid].items() if SHOW_ALL_AFTER in r["note"])
        assert newly == list(range(pre + 1, post + 1))


def test_every_show_all_row_is_tied_to_a_prior_open_item(
    rows: list[dict[str, str]],
) -> None:
    """A newly read row must name the open item it closes, not just be new."""
    newly = [r for r in rows if SHOW_ALL_AFTER in r["note"]]
    assert len(newly) == 4
    assert all("上一轮未闭合" in r["note"] for r in newly)


def test_propylene_carbonate_new_rows_carry_the_recorded_values(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    block = by_query["query_1_pc"]
    for index, value in PC_NEW_ROWS.items():
        assert block[index]["value"] == value
    assert block[8]["frequency_Hz"] == "2E+06" and block[8]["temperature_C"] == "30"
    assert block[9]["frequency_Hz"] == "2E+06" and block[9]["temperature_C"] == "25"
    assert "Ritzoulis" in block[8]["reference"]
    assert "Ritzoulis" in block[9]["reference"]


def test_propylene_carbonate_row_ten_is_a_value_less_stub(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    row = by_query["query_1_pc"][10]
    assert row["value"] == "" and row["frequency_Hz"] == ""
    assert row["temperature_C"] == "" and row["location"] == ""
    assert row["comment"] == "" and "Maquestian" in row["reference"]


def test_tetraglyme_row_eight_is_a_value_less_stub_that_falsifies_the_guess(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    row = by_query["query_2_tetraglyme"][8]
    assert row["value"] == "" and row["frequency_Hz"] == ""
    assert row["temperature_C"] == "" and row["location"] == ""
    assert row["comment"] == "" and "Ugelstad" in row["reference"]
    assert "39.99" in row["note"] and "证伪" in row["note"]


def test_tetraglyme_series_legs_are_the_rivas_ones(
    by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    block = by_query["query_2_tetraglyme"]
    for index in range(1, 8):
        assert "Rivas" in block[index]["reference"]
        assert block[index]["frequency_Hz"] == "1E+06"
    assert [block[i]["value"] for i in range(1, 8)] == [
        "8.03", "7.9", "7.79", "7.67", "7.55", "7.31", "7.07"]


def test_every_row_is_restricted_and_carries_a_reference(rows: list[dict[str, str]]) -> None:
    for row in rows:
        assert row["provenance_tag"] == "reaxys_crosscheck_only"
        assert row["access"] == "restricted_crosscheck_only"
        assert row["reference"].strip()
        assert row["reaxys_property_category"] == "Dielectric Constant"


def test_summary_readings_mirror_the_csv(
    summary: dict[str, object], by_query: dict[str, dict[int, dict[str, str]]],
) -> None:
    readings = {r["query_id"]: r for r in summary["readings"]}  # type: ignore[index]
    assert set(readings) == set(QUERY_COUNTS)
    for qid, (declared, pre, post) in QUERY_COUNTS.items():
        reading = readings[qid]
        assert reading["declared_entries"] == declared
        assert reading["rendered_without_show_all"] == pre
        assert reading["rendered_with_show_all"] == post
        newly = sorted(i for i, r in by_query[qid].items() if SHOW_ALL_AFTER in r["note"])
        assert reading["newly_read_rows"] == newly
        assert [v["value"] for v in reading["newly_read_values"]] == [
            by_query[qid][i]["value"] for i in newly]


def test_summary_closes_the_two_render_gap_open_items(
    summary: dict[str, object], prior: dict[str, object],
) -> None:
    closed = summary["open_items_closed"]  # type: ignore[index]
    assert closed
    prior_items = [str(x) for x in prior["open_items"]]  # type: ignore[index]
    assert len(closed) == 2
    for item in closed:
        assert item["quote"] in prior_items
        assert item["from"].startswith("probes/reaxys_v1x_stocking_scan_summary.json")
        assert item["verdict"]
    quotes = {item["quote"] for item in closed}
    assert prior_items[0] in quotes, "the tetraglyme render gap must be closed"
    assert prior_items[3] in quotes, "the PC render gap must be closed"


def test_summary_leaves_the_other_four_items_open(
    summary: dict[str, object], prior: dict[str, object],
) -> None:
    prior_items = [str(x) for x in prior["open_items"]]  # type: ignore[index]
    closed = {item["quote"] for item in summary["open_items_closed"]}  # type: ignore[index]
    still_open = list(summary["open_items_still_open"])  # type: ignore[index]
    assert still_open == [q for q in prior_items if q not in closed]
    assert len(still_open) == 4


def test_summary_records_the_falsified_guess_verbatim(
    summary: dict[str, object], prior: dict[str, object],
) -> None:
    falsified = summary["falsified_hypotheses"]  # type: ignore[index]
    assert falsified
    entry = falsified[0]
    assert "39.99" in entry["hypothesis"]
    assert entry["quote_from_prior_round"] == prior["open_items"][0]  # type: ignore[index]
    assert "证伪" in entry["verdict"]


def test_summary_declares_the_restricted_contract(summary: dict[str, object]) -> None:
    contract = summary["restricted_values_contract"]  # type: ignore[index]
    assert contract["route"] == "reaxys_ui_manual_query_in_logged_in_edge_session"
    assert contract["provenance"] == "reaxys<-bibliographic_citation"
    assert contract["machine_readable_mirror_present"] is True
    assert len(contract["mirror_fields"]) >= 2
    assert contract["redistribution"] == "not_permitted"
    assert contract["may_join_into_data_or_pool"] is False
    assert contract["declares_channel_availability"] is False
    method = summary["method"]  # type: ignore[index]
    assert method["bulk_export_used"] is False
    assert method["automated_traversal_used"] is False
    assert method["network_calls_made_by_this_artifact"] == 0
    assert method["offline_artifact"] is True


def test_summary_records_the_show_all_ui_finding(summary: dict[str, object]) -> None:
    finding = summary["ui_finding"]  # type: ignore[index]
    assert finding["control"] == "Show all"
    assert "折叠" in finding["statement"]
    assert "> " in finding["effect"] or "声明数 > 渲染数" in finding["statement"]


def test_local_propylene_carbonate_rows_are_still_zero() -> None:
    """The report's PC-gap claim must hold against the observation table itself."""
    obs = _rows(OBS_PATH)
    assert not [o for o in obs
                if "propylene carbonate" in (o["name"] or "").lower()
                or o["inchikey"] == PC_KEY]


def test_local_tetraglyme_rows_are_still_six() -> None:
    obs = _rows(OBS_PATH)
    tg = [o for o in obs if o["inchikey"] == TG_KEY]
    assert len(tg) == 6
    assert len({o["T_K"] for o in tg}) == 5


def test_report_states_the_falsification_and_the_v1x_reading() -> None:
    md = MD_PATH.read_text(encoding="utf-8")
    assert "39.99" in md
    assert "证伪" in md
    assert "一手核实" in md
    assert "Laurence" in md and "Ritzoulis" in md
    assert "禁止再分发" in md and "不得并入数据集或候选池" in md


def test_verifier_passes_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFIER)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT), check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verification_passed"] is True
    assert payload["problems"] == []


def test_this_artifact_never_touched_the_frozen_inputs() -> None:
    for rel, want in FROZEN_DIGESTS.items():
        assert hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == want, rel
