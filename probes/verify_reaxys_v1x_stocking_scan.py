"""Verifier for the Reaxys v1.x stocking scan artifacts.

The load-bearing check is the queue one: the CSV must be exactly the set of
pool members that carry fewer than two distinct temperatures in the local
observation table, recomputed here from scratch so a stale or hand-edited CSV
cannot pass. The second load-bearing check is the freeze: this probe is
read-only with respect to the frozen table and the pool.

Every non-derived column is re-derived too. The first version of this verifier
only re-derived ``local_distinct_T``, so forging ``target_dielectric``,
``target_T_K``, ``local_rows`` or ``family_tag`` by hand still produced a clean
36/36. Those columns now come from the pool, from the observation table, or from
``classify()`` itself.
"""

import csv
import hashlib
import io
import json
import pathlib
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
QUEUE_PATH = REPO_ROOT / "probes" / "reaxys_v1x_stocking_queue.csv"
SUMMARY_PATH = REPO_ROOT / "probes" / "reaxys_v1x_stocking_scan_summary.json"
REPORT_PATH = REPO_ROOT / "reports" / "reaxys_v1x_stocking_scan.md"
POOL_PATH = REPO_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
OBS_PATH = REPO_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
FROZEN_PATH = REPO_ROOT / "data" / "dielectric_v03.csv"

POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
OBS_SHA256 = "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
FROZEN_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"

sys.path.insert(0, str(REPO_ROOT))
from probes.reaxys_v1x_stocking_scan import (
    FAMILY_RULES,
    PROBED_INCHIKEY,
    classify,
)

FAMILY_TAGS = {tag for tag, _ in FAMILY_RULES} | {"other"}
P2_FAMILIES = {"carbonate", "lactone", "glyme_ether", "fluorinated"}
EXPECTED_FIELDS = [
    "queue_rank", "inchikey", "name", "smiles", "target_dielectric", "target_T_K",
    "local_rows", "local_distinct_T", "family_tag", "is_champion", "champion_short",
    "model_ready", "probed_in_this_round", "stocking_priority", "access",
]
PRIORITIES = {"P1", "P2", "P3"}


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recompute_queue() -> tuple[set[str], dict[str, int], dict[str, dict], dict[str, int]]:
    with POOL_PATH.open(encoding="utf-8", newline="") as fh:
        pool = list(csv.DictReader(fh))
    with OBS_PATH.open(encoding="utf-8", newline="") as fh:
        obs = list(csv.DictReader(fh))
    temps: dict[str, set[float]] = {}
    obs_rows: dict[str, int] = {}
    for r in obs:
        obs_rows[r["inchikey"]] = obs_rows.get(r["inchikey"], 0) + 1
        try:
            temps.setdefault(r["inchikey"], set()).add(round(float(r["T_K"]), 2))
        except (TypeError, ValueError):
            pass
    expect = {r["inchikey"] for r in pool if len(temps.get(r["inchikey"], set())) < 2}
    counts = {k: len(v) for k, v in temps.items()}
    pool_by_key = {r["inchikey"]: r for r in pool}
    return expect, counts, pool_by_key, obs_rows


def main() -> int:
    problems: list[str] = []
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            problems.append(name)

    check("queue csv exists", QUEUE_PATH.exists())
    check("summary json exists", SUMMARY_PATH.exists())
    check("report md exists", REPORT_PATH.exists())
    if problems:
        for c in checks:
            print(f"  [{'PASS' if c[1] else 'FAIL'}] {c[0]}")
        return 1

    raw = QUEUE_PATH.read_bytes()
    check("queue csv is LF only", b"\r\n" not in raw)
    check("queue csv has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
    with QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields, rows = reader.fieldnames, list(reader)
    check("queue header matches expected", fields == EXPECTED_FIELDS)
    check("queue is non-empty", len(rows) > 0)
    check("queue_rank is 1..n in order",
          [int(r["queue_rank"]) for r in rows] == list(range(1, len(rows) + 1)))
    check("queue keys are unique", len({r["inchikey"] for r in rows}) == len(rows))
    check("every priority is known", {r["stocking_priority"] for r in rows} <= PRIORITIES)

    expect, counts, pool_by_key, obs_rows = recompute_queue()
    actual = {r["inchikey"] for r in rows}
    check("queue equals the recomputed set of pool members with <2 distinct T", actual == expect)
    if actual != expect:
        problems.append(f"missing={sorted(expect - actual)[:5]} extra={sorted(actual - expect)[:5]}")

    bad = [r["inchikey"] for r in rows if int(r["local_distinct_T"]) >= 2]
    check("no row claims a local temperature series", not bad)
    mismatch = [r["inchikey"] for r in rows
                if counts.get(r["inchikey"], 0) != int(r["local_distinct_T"])]
    check("local_distinct_T recomputes", not mismatch)
    champions_in_queue = {r["champion_short"] for r in rows if r["champion_short"]}
    check("the two champions appear as ordinary members", {"EC", "PC"} <= champions_in_queue)

    # ---- every non-derived column is re-derived, not trusted ----
    forged_target = [r["inchikey"] for r in rows
                     if r["target_dielectric"] != pool_by_key[r["inchikey"]]["target_dielectric"]
                     or r["target_T_K"] != pool_by_key[r["inchikey"]]["T_K"]]
    check("target_dielectric / target_T_K come from the pool verbatim", not forged_target)
    forged_flags = [r["inchikey"] for r in rows
                    if r["is_champion"] != pool_by_key[r["inchikey"]]["is_champion"]
                    or r["champion_short"] != pool_by_key[r["inchikey"]]["champion_short"]
                    or r["model_ready"] != pool_by_key[r["inchikey"]]["model_ready"]
                    or r["name"] != pool_by_key[r["inchikey"]]["name"]
                    or r["smiles"] != pool_by_key[r["inchikey"]]["smiles"]]
    check("name / smiles / is_champion / champion_short / model_ready come from the pool",
          not forged_flags)
    forged_family = [r["inchikey"] for r in rows if r["family_tag"] != classify(r["name"])]
    check("family_tag recomputes from classify()", not forged_family)
    check("every family_tag is a declared tag", {r["family_tag"] for r in rows} <= FAMILY_TAGS)
    forged_rows = [r["inchikey"] for r in rows
                   if int(r["local_rows"]) != obs_rows.get(r["inchikey"], 0)]
    check("local_rows recomputes from the observation table", not forged_rows)
    probed_keys = set(PROBED_INCHIKEY.values())
    forged_probe = [r["inchikey"] for r in rows
                    if r["probed_in_this_round"]
                    != ("yes" if r["inchikey"] in probed_keys else "no")]
    check("probed_in_this_round recomputes from the probed-compound list", not forged_probe)
    forged_access = [r["inchikey"] for r in rows
                     if r["access"] != (
                         "public_local_metadata_plus_manual_reaxys_probe"
                         if r["probed_in_this_round"] == "yes"
                         else "public_local_metadata_only_not_yet_probed")]
    check("access is derived per row, not asserted for the whole file", not forged_access)
    check("only the rows actually probed claim the manual probe",
          sum(1 for r in rows if r["probed_in_this_round"] == "yes")
          == len(probed_keys & {r["inchikey"] for r in rows}))
    check("P1 is exactly the champion rows",
          {r["inchikey"] for r in rows if r["stocking_priority"] == "P1"}
          == {r["inchikey"] for r in rows if r["is_champion"].strip().lower() == "true"})
    check("P2 rows are in the declared families",
          all(r["family_tag"] in P2_FAMILIES for r in rows if r["stocking_priority"] == "P2"))

    by_rank = sorted(rows, key=lambda r: int(r["queue_rank"]))
    order_key = [({"P1": 0, "P2": 1, "P3": 2}[r["stocking_priority"]], r["family_tag"], r["inchikey"])
                 for r in by_rank]
    check("queue is sorted by (priority, family, inchikey)", order_key == sorted(order_key))

    check("pool digest unchanged", sha256_of(POOL_PATH) == POOL_SHA256)
    check("observation table digest unchanged", sha256_of(OBS_PATH) == OBS_SHA256)
    check("frozen dielectric table digest unchanged", sha256_of(FROZEN_PATH) == FROZEN_SHA256)

    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    check("summary task id", summary.get("task") == "reaxys_v1x_stocking_scan")
    check("summary records the compliance line",
          "restricted_crosscheck_only" in json.dumps(summary, ensure_ascii=False))
    check("summary records the browser", "Edge" in str(summary.get("browser", "")))
    check("summary queue size matches the csv", summary["queue_stats"]["queue_size"] == len(rows))
    readings = summary.get("readings", [])
    check("summary carries every reading", len(readings) >= 7)
    check("every reading names a verdict",
          all(r.get("verdict") for r in readings))
    check("every reading keeps its local count",
          all(isinstance(r.get("local_registered_distinct_T"), int) for r in readings))
    check("every reading carries the observation-derived count",
          all(isinstance(r.get("observation_table_distinct_T"), int) for r in readings))
    check("every reading declares which local table its count came from",
          all(r.get("local_registered_scope") for r in readings))
    check("observation_table_distinct_T agrees with the observation table",
          all(r["observation_table_distinct_T"]
              == counts.get(PROBED_INCHIKEY[r["compound"]], 0) for r in readings))
    check("entries_rendered equals the number of transcribed rows",
          all(r["entries_rendered"] == len(r["rendered_rows"]) for r in readings))
    declared_gaps = {r["short"] for r in readings
                     if r["entries_rendered"] < r["reaxys_dielectric_entries"]}
    open_text = " ".join(str(i) for i in summary.get("open_items", []))
    check("every declared-vs-rendered gap is disclosed in the open items",
          all(short in open_text for short in declared_gaps))
    check("the machine-readable mirror of restricted values is admitted, not denied",
          "机器可读镜像" in str(summary.get("compliance", ""))
          and summary.get("restricted_values_contract", {}).get(
              "machine_readable_mirror_present") is True)
    check("the restricted-values contract forbids redistribution",
          summary.get("restricted_values_contract", {}).get("redistribution") == "not_permitted")
    check("the restricted-values contract declares no channel availability",
          summary.get("restricted_values_contract", {}).get(
              "declares_channel_availability") is False)
    check("observation digest is pinned in the summary",
          summary.get("observation_sha256") == OBS_SHA256)
    net_new_total = sum(int(r.get("net_new_temperature_points", 0)) for r in readings)
    listed_total = sum(int(n["n_points"]) for n in summary["net_new_temperature_points"])
    check("net-new points agree between readings and the headline list", net_new_total == listed_total)
    check("net-new headline names its sources",
          all(n.get("sources") for n in summary["net_new_temperature_points"]))
    check("the tetraglyme net-new source is named",
          any(any("Rivas" in str(src) for src in n["sources"])
              for n in summary["net_new_temperature_points"]))
    check("every net-new point carries a frequency qualifier",
          all(n.get("frequency_Hz") and n.get("qualifier")
              for n in summary["net_new_temperature_points"]))
    pc = next((c for c in summary.get("cross_checks", []) if c.get("champion") == "PC"), {})
    check("PC is recorded as a compilation restatement, not an independent measurement",
          pc.get("verdict") == "compilation_restatement_agrees")
    check("PC evidence chain names the shared compilation provenance",
          "Riddick" in pc.get("evidence_chain", {}).get("shared_provenance", ""))
    ec = next((c for c in summary.get("cross_checks", []) if c.get("champion") == "EC"), {})
    check("EC records the Reaxys temperature-label conflict",
          ec.get("verdict") == "value_matches_but_reaxys_temperature_label_conflicts")
    for c in summary.get("cross_checks", []):
        chain = c.get("evidence_chain", {})
        ref = REPO_ROOT / str(chain.get("cross_reference", ""))
        check(f"{c.get('champion')} evidence-chain cross-reference exists", ref.exists())
        if ref.exists():
            check(f"{c.get('champion')} evidence-chain quote is verbatim in the cross-referenced file",
                  chain.get("cross_reference_quote", "\u0000") in ref.read_text(encoding="utf-8"))
    check("the queue temperature-series counts partition the pool",
          summary["queue_stats"]["queue_size"]
          + summary["queue_stats"]["pool_members_with_two_or_more_distinct_T"]
          == summary["queue_stats"]["pool_distinct_keys"])
    check("P1-equals-champions is asserted in the stats",
          summary["queue_stats"].get("p1_equals_champion_rows") is True)
    check("the observation-table scope count is labelled separately from the pool scope count",
          "observation_table_compounds_with_two_or_more_distinct_T" in summary["queue_stats"]
          and "pool_members_with_two_or_more_distinct_T" in summary["queue_stats"])
    check("open items are declared", len(summary.get("open_items", [])) >= 3)
    check("summary pool sha matches the frozen pool",
          summary.get("pool_sha256") == POOL_SHA256)

    md = REPORT_PATH.read_bytes()
    check("report is LF only", b"\r\n" not in md)
    md_text = md.decode("utf-8")
    check("report states the compliance rule", "restricted_crosscheck_only" in md_text)
    check("report carries the pool digest prefix", POOL_SHA256[:16] in md_text)
    check("report states the net-new count", "净新增带温度的介电条目 4 条" in md_text)
    check("report is explicit that the expansion conclusion is unchanged", "不改结论" in md_text)
    check("report separates the pool-scope count from the observation-table-scope count",
          "池内**有**温度序列的是" in md_text and "**全表**" in md_text)
    check("report admits the restricted-value mirror", "机器可读镜像" in md_text)
    check("report states the no-usability-claim disclaimer",
          "不产生任何通道可用性声明" in md_text and "不是可用性判断" in md_text)
    check("report does not call the PC agreement an independent corroboration",
          "两个互相独立的一手来源复现" not in md_text)
    check("report pins the observation digest prefix", OBS_SHA256[:16] in md_text)

    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{sum(1 for _, ok in checks if ok)}/{len(checks)} checks passed")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())