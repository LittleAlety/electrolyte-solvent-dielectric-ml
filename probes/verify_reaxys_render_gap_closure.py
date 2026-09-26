"""Verifier for the Reaxys render-gap closure artifacts.

The CSV mirrors a manual, logged-in Reaxys session, so it cannot be re-derived
offline. It is therefore pinned three ways: the CSV against the machine-readable
summary, the summary against the prior round's open items (quoted verbatim), and
the report against both. The load-bearing claims are the two closed open items
and the falsified "39.99 C" guess for the missing tetraglyme row.

The last block is the independence guard: this artifact family must not have
touched anything under data/. That is checked by recomputing the four frozen
red-line digests and by refusing any artifact path that lives under data/.
"""

import csv
import hashlib
import io
import json
import pathlib
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "probes" / "reaxys_render_gap_closure.csv"
JSON_PATH = REPO_ROOT / "probes" / "reaxys_render_gap_closure_summary.json"
MD_PATH = REPO_ROOT / "reports" / "reaxys_render_gap_closure.md"
PRIOR_PATH = REPO_ROOT / "probes" / "reaxys_v1x_stocking_scan_summary.json"
OBS_PATH = REPO_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"

ARTIFACT_PATHS = [CSV_PATH, JSON_PATH, MD_PATH, pathlib.Path(__file__).resolve()]

EXPECTED_FIELDS = [
    "query_id", "compound", "short", "cas", "reaxys_registry_number",
    "reaxys_property_category", "reaxys_declared_entries", "rendered_without_show_all",
    "rendered_with_show_all", "row_index", "value", "frequency_Hz", "temperature_C",
    "location", "comment", "reference", "provenance_tag", "access", "note",
]

QUERIES = {
    "query_1_pc": {"short": "PC", "cas": "108-32-7", "declared": "10", "pre": "7", "post": "10"},
    "query_2_tetraglyme": {"short": "tetraglyme", "cas": "143-24-8", "declared": "8", "pre": "7", "post": "8"},
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

MD_NEEDLES = [
    "Show all", "Dielectric Constant", "108-32-7", "143-24-8", "39.99",
    "证伪", "Ritzoulis", "Laurence", "restricted_values_contract",
    "禁止再分发", "不得并入数据集或候选池", "Maquestian", "Ugelstad", "Rivas",
    "64.4", "2 MHz", PC_KEY, TG_KEY, "reaxys_render_gap_closure.csv", "上一轮登记",
]


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _observation_rows():
    return _rows(OBS_PATH)


def main() -> int:
    checks = []
    problems = []

    def ck(name, value):
        value = bool(value)
        checks.append({"check": name, "passed": value})
        if not value:
            problems.append(name)
        return value

    raw = CSV_PATH.read_bytes()
    ck("csv exists with no CRLF and no BOM",
       CSV_PATH.exists() and b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf"))

    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    ck("csv header matches the declared contract", fields == EXPECTED_FIELDS)
    ck("csv carries 18 rows (PC 10 + tetraglyme 8)", len(rows) == 18)
    ck("csv covers exactly the two queried compounds",
       {r["query_id"] for r in rows} == set(QUERIES))

    for qid, want in QUERIES.items():
        block = [r for r in rows if r["query_id"] == qid]
        ck(f"{qid}: row count equals the Show-all rendering",
           len(block) == int(want["post"]))
        ck(f"{qid}: declared / pre / post are constant across the block",
           {r["reaxys_declared_entries"] for r in block} == {want["declared"]}
           and {r["rendered_without_show_all"] for r in block} == {want["pre"]}
           and {r["rendered_with_show_all"] for r in block} == {want["post"]})
        ck(f"{qid}: declared >= rendered-with-show-all > rendered-without-show-all",
           int(want["declared"]) >= int(want["post"]) > int(want["pre"]))
        ck(f"{qid}: row_index is dense 1..N",
           [int(r["row_index"]) for r in block] == list(range(1, len(block) + 1)))
        ck(f"{qid}: short and cas are stable",
           {r["short"] for r in block} == {want["short"]}
           and {r["cas"] for r in block} == {want["cas"]})
        ck(f"{qid}: property category is Dielectric Constant",
           {r["reaxys_property_category"] for r in block} == {"Dielectric Constant"})

    ck("every row routes through the restricted contract",
       all(r["provenance_tag"] == "reaxys_crosscheck_only"
           and r["access"] == "restricted_crosscheck_only" for r in rows))
    ck("every row carries a reference", all(r["reference"].strip() for r in rows))
    ck("every row names its Show-all state",
       all(("Show all 前已渲染" in r["note"]) or (SHOW_ALL_AFTER in r["note"]) for r in rows))

    newly_read_rows = [r for r in rows if SHOW_ALL_AFTER in r["note"]]
    ck("exactly four rows appear only after Show all", len(newly_read_rows) == 4)
    ck("every Show-all row is tied to a previously open item (note says 上一轮未闭合)",
       all("上一轮未闭合" in r["note"] for r in newly_read_rows))

    pc_block = {int(r["row_index"]): r for r in rows if r["query_id"] == "query_1_pc"}
    ck("PC rows 8 / 9 / 10 carry the newly read values",
       all(pc_block[i]["value"] == v for i, v in PC_NEW_ROWS.items()))
    ck("PC row 8 and 9 are the 2 MHz Ritzoulis legs",
       "Ritzoulis" in pc_block[8]["reference"] and pc_block[8]["frequency_Hz"] == "2E+06"
       and "Ritzoulis" in pc_block[9]["reference"] and pc_block[9]["frequency_Hz"] == "2E+06")
    ck("PC row 10 is a value-less citation stub",
       pc_block[10]["value"] == "" and pc_block[10]["temperature_C"] == ""
       and pc_block[10]["frequency_Hz"] == "" and "Maquestian" in pc_block[10]["reference"])

    tg_block = {int(r["row_index"]): r for r in rows if r["query_id"] == "query_2_tetraglyme"}
    ck("tetraglyme row 8 is a value-less citation stub, not a temperature point",
       tg_block[8]["value"] == "" and tg_block[8]["temperature_C"] == ""
       and tg_block[8]["frequency_Hz"] == "" and "Ugelstad" in tg_block[8]["reference"])
    ck("tetraglyme row 8 explicitly records the falsified 39.99 hypothesis",
       "39.99" in tg_block[8]["note"] and "证伪" in tg_block[8]["note"])
    ck("tetraglyme rows 1-7 are the Rivas series at 1 MHz",
       all("Rivas" in tg_block[i]["reference"] and tg_block[i]["frequency_Hz"] == "1E+06"
           for i in range(1, 8)))

    summary = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR_PATH.read_text(encoding="utf-8"))

    readings = {r["query_id"]: r for r in summary["readings"]}
    ck("summary readings cover exactly the two queries", set(readings) == set(QUERIES))
    for qid, want in QUERIES.items():
        reading = readings.get(qid, {})
        ck(f"{qid}: summary counts agree with the CSV",
           reading.get("declared_entries") == int(want["declared"])
           and reading.get("rendered_without_show_all") == int(want["pre"])
           and reading.get("rendered_with_show_all") == int(want["post"])
           and reading.get("cas") == want["cas"])
        csv_new = sorted(int(r["row_index"]) for r in rows
                         if r["query_id"] == qid and SHOW_ALL_AFTER in r["note"])
        ck(f"{qid}: summary newly_read_rows equals the CSV Show-all rows",
           list(reading.get("newly_read_rows", [])) == csv_new)
        ck(f"{qid}: summary mirrors each newly read value",
           [v["value"] for v in reading.get("newly_read_values", [])]
           == [r["value"] for r in sorted(
               (r for r in rows if r["query_id"] == qid and SHOW_ALL_AFTER in r["note"]),
               key=lambda r: int(r["row_index"]))])

    closed = summary.get("open_items_closed", [])
    ck("summary closes exactly the two render-gap open items", len(closed) == 2)
    prior_items = [str(x) for x in prior["open_items"]]
    ck("every closed item is quoted verbatim from the prior round",
       all(item.get("quote") in prior_items for item in closed))
    closed_quotes = {item.get("quote") for item in closed}
    ck("the tetraglyme render gap is the one closed first",
       prior_items[0] in closed_quotes)
    ck("the PC render gap is closed too", prior_items[3] in closed_quotes)
    still_open = [str(x) for x in summary.get("open_items_still_open", [])]
    ck("still-open items are exactly the prior items minus the closed two",
       sorted(still_open) == sorted(q for q in prior_items if q not in closed_quotes))
    ck("still-open items are non-trivial (4 remain)", len(still_open) == 4)

    falsified = summary.get("falsified_hypotheses", [])
    ck("the 39.99 C guess is recorded as falsified, with its prior quote",
       bool(falsified) and "39.99" in falsified[0].get("hypothesis", "")
       and falsified[0].get("quote_from_prior_round") in prior_items
       and "证伪" in falsified[0].get("verdict", ""))

    finding = summary.get("ui_finding", {})
    ck("ui_finding names the Show all control",
       finding.get("control") == "Show all" and "折叠" in finding.get("statement", ""))
    method = summary.get("method", {})
    ck("method is the manual logged-in Edge route with zero network calls",
       method.get("route") == "reaxys_ui_manual_query_in_logged_in_edge_session"
       and method.get("bulk_export_used") is False
       and method.get("automated_traversal_used") is False
       and method.get("network_calls_made_by_this_artifact") == 0)
    ck("the artifact declares itself offline", summary.get("method", {}).get("offline_artifact") is True)

    contract = summary.get("restricted_values_contract", {})
    ck("contract route is the manual logged-in Edge session",
       contract.get("route") == "reaxys_ui_manual_query_in_logged_in_edge_session")
    ck("contract provenance stops at the bibliographic citation",
       contract.get("provenance") == "reaxys<-bibliographic_citation")
    ck("contract declares the mirror is present",
       contract.get("machine_readable_mirror_present") is True)
    ck("contract names the mirror fields",
       isinstance(contract.get("mirror_fields"), list) and len(contract["mirror_fields"]) >= 2)
    ck("contract forbids redistribution", contract.get("redistribution") == "not_permitted")
    ck("contract forbids joining the data or the candidate pool",
       contract.get("may_join_into_data_or_pool") is False)
    ck("contract declares no channel availability",
       contract.get("declares_channel_availability") is False)
    ck("summary states what this does not prove",
       len(summary.get("what_this_does_not_prove", [])) >= 4)

    obs = _observation_rows()
    pc_local = [o for o in obs
                if "propylene carbonate" in (o.get("name") or "").lower()
                or o.get("inchikey") == PC_KEY]
    tg_local = [o for o in obs
                if "tetraethylene glycol dimethyl ether" in (o.get("name") or "").lower()
                or o.get("inchikey") == TG_KEY]
    ck("local observation table has 0 propylene carbonate rows (re-measured)",
       len(pc_local) == 0)
    ck("summary reports the same 0 local PC rows",
       readings["query_1_pc"].get("local_observation_rows") == 0)
    ck("local observation table has 6 tetraglyme rows (re-measured)", len(tg_local) == 6)
    ck("those tetraglyme rows cover 5 distinct temperatures",
       len({o["T_K"] for o in tg_local}) == 5)
    ck("summary reports the same 6 local tetraglyme rows",
       readings["query_2_tetraglyme"].get("local_observation_rows") == 6)

    md = MD_PATH.read_text(encoding="utf-8")
    for needle in MD_NEEDLES:
        ck(f"report mentions {needle!r}", needle in md)
    ck("report records the 39.99 C hypothesis as falsified",
       "39.99" in md and "证伪" in md)
    ck("report states the PC 2 MHz series is a lead, not data",
       "线索不是数据" in md or "只是线索，不是数据" in md)
    ck("report points back to the primary papers",
       "Laurence" in md and "Ritzoulis" in md and "一手核实" in md)

    ck("no artifact path lives under data/",
       not any("data" in path.parts for path in ARTIFACT_PATHS))
    for rel, want in FROZEN_DIGESTS.items():
        digest = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
        ck(f"frozen red line intact: {rel}", digest == want)

    passed = all(c["passed"] for c in checks)
    report = {
        "task": "verify_reaxys_render_gap_closure",
        "verification_passed": passed,
        "checks_total": len(checks),
        "checks_failed": len([c for c in checks if not c["passed"]]),
        "problems": problems,
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
