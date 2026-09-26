"""Verifier for the Reaxys dielectric queue first-cut artifacts.

Checks the CSV/JSON/Markdown triple against each other, against the frozen
v1.0 row metadata, and against the local observation table. The sulfolane
check is the load-bearing one: Reaxys and our local extraction must agree
point by point on the Vahidi & Moshtari 2013 series.
"""

import csv
import io
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "probes" / "reaxys_dielectric_queue_first_cut.csv"
JSON_PATH = REPO_ROOT / "probes" / "reaxys_dielectric_queue_first_cut_summary.json"
MD_PATH = REPO_ROOT / "reports" / "reaxys_dielectric_queue_first_cut.md"
OBS_PATH = REPO_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"

EXPECTED_FIELDS = [
    "queue_rank", "compound", "short", "cas", "inchikey", "reaxys_property_category",
    "reaxys_n_entries_in_category", "value", "frequency_Hz", "temperature_C", "location",
    "comment", "reference", "local_observations_v11plus", "net_new_vs_local",
    "provenance_tag", "access", "note",
]
NUMERIC_OR_RANGE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?(\s*-\s*[+-]?\d+(\.\d+)?)?$")
SULFOLANE_SERIES = {
    "44.5": 19.99, "44": 24.99, "43.4": 29.99, "42.8": 34.99,
    "42.2": 39.99, "41.6": 44.99, "41.1": 49.99, "40.4": 54.99,
}


def main() -> int:
    problems: list[str] = []
    checks: list[tuple[str, bool]] = []

    raw = CSV_PATH.read_bytes()
    checks.append(("csv exists", CSV_PATH.exists()))
    checks.append(("csv has no CRLF", b"\r\n" not in raw))
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields, rows = reader.fieldnames, list(reader)
    checks.append(("header matches expected", fields == EXPECTED_FIELDS))
    if fields != EXPECTED_FIELDS:
        problems.append(f"header mismatch: {fields}")
    checks.append(("row count is 19", len(rows) == 19))
    checks.append(("six compounds covered",
                   {r["short"] for r in rows} == {"FEC", "VC", "GVL", "DME", "SFL", "MOPN"}))

    for r in rows:
        tag = f"{r['short']}@{r['reference'][:24]}"
        if r["provenance_tag"] != "reaxys_crosscheck_only":
            problems.append(f"{tag}: provenance_tag={r['provenance_tag']!r}")
        if r["access"] != "restricted_crosscheck_only":
            problems.append(f"{tag}: access={r['access']!r}")
        if not r["reference"].strip():
            problems.append(f"{tag}: empty reference")
        for col in ("value", "frequency_Hz", "temperature_C"):
            v = r[col].strip()
            if v and not NUMERIC_OR_RANGE.match(v):
                problems.append(f"{tag}: {col}={v!r} not numeric-or-range")
    checks.append(("compliance + numeric-or-range on every row", not problems))

    summary = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    nn = summary["net_new_numbers"]
    checks.append(("net_new: FEC 0 / VC 0 / SFL 0",
                   nn["FEC"] == 0 and nn["VC"] == 0 and nn["SFL"] == 0))
    checks.append(("net_new: GVL 1 / DME 1", nn["GVL"] == 1 and nn["DME"] == 1))
    checks.append(("Reaxys method field declared absent",
                   "不存在" in summary["reaxys_data_model"]["method_field"]))

    with OBS_PATH.open(encoding="utf-8", newline="") as fh:
        obs = list(csv.DictReader(fh))

    def local_rows(name_needle: str) -> list[dict[str, str]]:
        return [o for o in obs if name_needle in (o["name"] or "").lower()]

    sfl_local = local_rows("sulfolane")
    checks.append(("local table has 8 sulfolane observations", len(sfl_local) == 8))

    series = [r for r in rows if r["short"] == "SFL" and "Vahidi" in r["reference"]]
    wu = [r for r in rows if r["short"] == "SFL" and "Wu, Di" in r["reference"]]
    checks.append(("Reaxys carries the 8-point Vahidi series", len(series) == 8))
    matched = 0
    for r in series:
        want_t = float(r["temperature_C"]) + 273.15
        want_e = float(r["value"])
        for o in sfl_local:
            if abs(float(o["T_K"]) - want_t) <= 0.02 and abs(float(o["epsilon"]) - want_e) <= 1e-9:
                matched += 1
                break
        else:
            problems.append(f"sulfolane {r['value']} @ {r['temperature_C']} C has no local match")
    checks.append(("sulfolane Reaxys series matches local point by point", matched == 8))
    checks.append(("Wu 2024 cross-agrees at 30 C", bool(wu) and wu[0]["value"] == "43.4"))

    gvl_local = local_rows("valerolactone")
    checks.append(("GVL is a real local gap (0 observations)", len(gvl_local) == 0))
    checks.append(("DME already has >= 9 local observations", len(local_rows("dimethoxyethane")) >= 9))
    mopn = [r for r in rows if r["short"] == "MOPN"]
    checks.append(("MOPN recorded as a negative row", len(mopn) == 1))
    checks.append(("MOPN category count is 0",
                   bool(mopn) and mopn[0]["reaxys_n_entries_in_category"] == "0"))
    checks.append(("MOPN row carries no dielectric value",
                   bool(mopn) and mopn[0]["value"] == "" and mopn[0]["temperature_C"] == ""
                   and mopn[0]["frequency_Hz"] == ""))
    checks.append(("MOPN negative note states all three levels",
                   bool(mopn) and all(k in mopn[0]["note"] for k in
                                      ("Physical Data", "0 Substances", "112"))))
    checks.append(("MOPN dipole anchor is Strobykina 1987",
                   bool(mopn) and "Strobykina" in mopn[0]["reference"]))
    checks.append(("MOPN has 0 local observations",
                   len(local_rows("methoxypropionitrile")) == 0))
    ticket = summary["mopn_ticket"]
    checks.append(("MOPN category list sums to the 103 recorded entries",
                   sum(ticket["category_list"].values()) == ticket["physical_data_entries"] == 103))
    checks.append(("MOPN declares no dielectric category", ticket["dielectric_categories"] == []))
    checks.append(("MOPN dipole is not usable as a dielectric value",
                   ticket["only_electrical_quantity"]["usable_as_dielectric_value"] is False))
    checks.append(("MOPN net_new is 0", nn["MOPN"] == 0))

    md = MD_PATH.read_text(encoding="utf-8")
    for needle in ("Static Dielectric Constant", "Frequency (Hz)", "10.1039/j29660000005",
                   "Hagiyama", "支持材料" if False else "supporting information",
                   "Werblan", "Vahidi", "永不进可分发数据集", "净新增", "110-67-8", "Strobykina", "4.04", "SummaryAI"):
        checks.append((f"report mentions {needle!r}", needle in md))

    ok = all(v for _, v in checks) and not problems
    for name, value in checks:
        print(("PASS  " if value else "FAIL  ") + name)
    for p in problems:
        print("PROBLEM  " + p)
    print("verification_passed = " + ("true" if ok else "false"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())