"""W17-16 - the Reaxys v1.x stocking queue, P2 layer, walked substance by substance.

The W17-13 and W17-15 lanes walked the thin-family backfill queue.  This lane walks the
``probes/reaxys_v1x_stocking_queue.csv`` stocking queue instead, and only its P2 layer, and
only the P2 substances that no earlier Reaxys lane in this repository has read yet.

The brief names nineteen keys and calls the set twenty.  The queue's own
``probed_in_this_round`` column cannot settle the count, because it is stale: it marks
ethyl methyl carbonate and gamma-valerolactone as unprobed although W17-15 walked them, and
it marks trifluoroacetic acid as unprobed although W17-13 walked it.  What this lane does
instead is compute the exclusion from the earlier lanes' own fact tables, which yields
nineteen keys - exactly the nineteen the brief lists verbatim.

Four things are enforced here rather than merely stated:

* **the restricted contract** (``reports/decisions_log.md`` section 28.2, ruling B):
  Reaxys-derived *values* never enter ``data/``, any pool or any feature table.  Everything
  this lane writes lives under ``probes/``; the raw page evidence stays in the git-ignored
  ``data/raw/reaxys_w17d/``.
* **the key audit**: every substance key must come from the queue's ``inchikey`` column
  verbatim, so a hand-typed key fails the build.
* **the value/number distinction**: Reaxys writes ranges and points into the same value
  column, so each channel counts *rows*, *valued rows* (the cell is populated, a range
  included) and *point values* (the cell parses as one float) separately.
* **the Comment column**: a number can hide in the Comment cell while the value cell of the
  same row stays empty, so those rows are counted on their own axis and never merged into
  the value-column counts.

Usage::

    python probes/reaxys_v1x_stocking_query.py --overwrite
    python probes/reaxys_v1x_stocking_query.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "probes" / "reaxys_v1x_stocking_queue.csv"
RAW_DIR = ROOT / "data" / "raw" / "reaxys_w17d"
FACTS = ROOT / "probes" / "reaxys_v1x_stocking_query_facts.csv"
SUMMARY = ROOT / "probes" / "reaxys_v1x_stocking_query_summary.json"

PRIOR_LANES = (
    ("W17-13", ROOT / "probes" / "reaxys_thin_family_query_facts.csv"),
    ("W17-15", ROOT / "probes" / "reaxys_thin_family_query_b2_facts.csv"),
)

ARM = "W17-16"
WEEK = "week17"
TITLE = (
    "Reaxys v1.x stocking queue, P2 layer: nineteen never-read substances walked one card at "
    "a time, where the ethers and fluoroaromatics land epsilon and eta numbers, the orbital "
    "channel is still ionization potentials and reference-only calculations, and every redox "
    "row keeps its potential inside the Comment string"
)

QUEUE_PRIORITY = "P2"
POINT = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
NUMBER_IN_TEXT = re.compile(r"[-+]?\d+(?:\.\d+)?")

CHANNELS = (
    ("eps", ("Dielectric Constant", "Static Dielectric Constant")),
    ("eta", ("Dynamic Viscosity", "Kinematic Viscosity")),
    ("hp", ("Ionization Potential", "Quantum Chemical Calculations", "Calculated Properties")),
    ("redox", ("Electrochemical Characteristics",)),
)

VALUE_COLUMNS = {
    "Dielectric Constant": "Dielectric Constant",
    "Static Dielectric Constant": "Static Dielectric Constant",
    "Dynamic Viscosity": "Dynamic Viscosity, P",
    "Kinematic Viscosity": "Kinematic Viscosity, St",
    "Ionization Potential": "Ionization Potential, eV",
    "Quantum Chemical Calculations": None,
    "Calculated Properties": None,
    "Electrochemical Characteristics": None,
}

CHANNEL_DEFINITIONS = {
    "eps": "Dielectric Constant + Static Dielectric Constant",
    "eta": "Dynamic Viscosity + Kinematic Viscosity",
    "hp": (
        "Ionization Potential + Quantum Chemical Calculations (labelled Calculated Properties "
        "on the card). Both are orbital-adjacent; neither is a HOMO, a LUMO or a gap, and "
        "every Calculated Properties row in this set is text, not a number"
    ),
    "redox": "Electrochemical Characteristics (Electrochemical Behaviour deliberately excluded)",
}

FACT_COLUMNS = (
    "inchikey",
    "name",
    "family_tag",
    "queue_rank",
    "stocking_priority",
    "card_inchikey",
    "reaxys_rn",
    "cas",
    "articles_in_result_list",
    "query_succeeded",
    "access",
) + tuple(
    key + suffix
    for key in ("eps", "eta", "hp", "redox")
    for suffix in ("_rows", "_valued", "_point", "_point_from_comment")
) + (
    "categories_captured",
    "rows_captured",
    "carries_reaxys_values",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def column_index(headers, wanted):
    if wanted is None:
        return None
    for index, header in enumerate(headers):
        if header.split(" Show ")[0].strip() == wanted:
            return index
    return None


def comment_index(headers):
    for index, header in enumerate(headers):
        if header.startswith("Comment ("):
            return index
    return None


def cell(row, index):
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def count_table(table):
    """Rows, valued rows and point values of one Reaxys category table."""
    headers = table["headers"]
    value_at = column_index(headers, VALUE_COLUMNS.get(table["category"]))
    comment_at = comment_index(headers)
    valued = point = from_comment = 0
    for row in table["rows"]:
        value = cell(row, value_at)
        comment = cell(row, comment_at)
        if value:
            valued += 1
            if POINT.match(value):
                point += 1
        elif comment and NUMBER_IN_TEXT.search(comment):
            from_comment += 1
    return {
        "rows": len(table["rows"]),
        "valued": valued,
        "point": point,
        "point_from_comment": from_comment,
    }
CATEGORY_CHANNEL = {name: key for key, names in CHANNELS for name in names}


def resolve_targets():
    queue_rows = read_csv(QUEUE)
    queue_keys = {row["inchikey"] for row in queue_rows if row.get("inchikey")}
    prior = {}
    for lane, path in PRIOR_LANES:
        prior[lane] = {row["inchikey"] for row in read_csv(path) if row.get("inchikey")}
    walked_before = set().union(*prior.values())
    targets = [
        row
        for row in queue_rows
        if row.get("stocking_priority") == QUEUE_PRIORITY
        and row.get("inchikey")
        and row["inchikey"] not in walked_before
    ]
    stale_flag = [
        row["inchikey"]
        for row in queue_rows
        if row.get("stocking_priority") == QUEUE_PRIORITY
        and (row.get("probed_in_this_round") or "").strip().lower() == "no"
        and row["inchikey"] in walked_before
    ]
    return queue_rows, queue_keys, prior, targets, stale_flag


def harvest_for(key):
    slug = key.split("-")[0]
    path = RAW_DIR / f"harvest_{slug}.json"
    if not path.exists():
        raise SystemExit(f"missing raw harvest {path.name}")
    return path, read_json(path)


def compose():
    queue_rows, queue_keys, prior, targets, stale_flag = resolve_targets()
    if len(targets) != 19:
        raise SystemExit(f"expected 19 never-read P2 substances, found {len(targets)}")

    rows_out = []
    evidence = {}
    tally = {
        key: {
            "definition": CHANNEL_DEFINITIONS[key],
            "categories": list(names),
            "rows": 0,
            "valued_rows": 0,
            "point_values": 0,
            "point_values_from_the_comment_column": 0,
            "substances_with_rows": 0,
            "substances_with_point_values": 0,
            "tables": 0,
        }
        for key, names in CHANNELS
    }

    for target in targets:
        key = target["inchikey"]
        if key not in queue_keys:
            raise SystemExit(
                f"{key} is not an inchikey in the v1.x stocking queue; hand-typed keys are "
                "not allowed here"
            )
        path, harvest = harvest_for(key)
        if harvest.get("inchikey_searched") != key:
            raise SystemExit(f"{key}: harvest searched another key")
        on_card = (harvest.get("identification") or {}).get("InChIKey")
        if on_card != key:
            raise SystemExit(f"{key}: card InChIKey {on_card!r} != queue key")

        per_channel = {
            name: {"rows": 0, "valued": 0, "point": 0, "point_from_comment": 0}
            for name in ("eps", "eta", "hp", "redox")
        }
        captured_categories = 0
        captured_rows = 0
        for table in harvest["tables"]:
            category = table["category"]
            read_rows = len(table["rows"])
            if read_rows and table["reported"] != read_rows:
                raise SystemExit(
                    f"{key}/{category}: {read_rows} rows read but Reaxys reports "
                    f"{table[chr(114)+chr(101)+chr(112)+chr(111)+chr(114)+chr(116)+chr(101)+chr(100)]}"
                )
            captured_categories += 1
            captured_rows += read_rows
            channel = CATEGORY_CHANNEL.get(category)
            if channel is None:
                continue
            counted = count_table(table)
            bucket = per_channel[channel]
            for field in ("rows", "valued", "point", "point_from_comment"):
                bucket[field] += counted[field]

        ident = harvest.get("identification") or {}
        row = {
            "inchikey": key,
            "name": target["name"],
            "family_tag": target["family_tag"],
            "queue_rank": target["queue_rank"],
            "stocking_priority": target["stocking_priority"],
            "card_inchikey": on_card,
            "reaxys_rn": ident.get("Reaxys ID") or ident.get("Reaxys Registry Number") or "",
            "cas": (ident.get("CAS Registry Number(s)") or ident.get("CAS Registry Number") or ""),
            "articles_in_result_list": harvest.get("n_articles", ""),
            "query_succeeded": "true" if harvest.get("ok") else "false",
            "access": "public_reaxys_card_read_in_place_edge_signed_in",
        }
        for channel, bucket in per_channel.items():
            row[channel + "_rows"] = bucket["rows"]
            row[channel + "_valued"] = bucket["valued"]
            row[channel + "_point"] = bucket["point"]
            row[channel + "_point_from_comment"] = bucket["point_from_comment"]
            tally[channel]["rows"] += bucket["rows"]
            tally[channel]["valued_rows"] += bucket["valued"]
            tally[channel]["point_values"] += bucket["point"]
            tally[channel]["point_values_from_the_comment_column"] += bucket["point_from_comment"]
        row["categories_captured"] = captured_categories
        row["rows_captured"] = captured_rows
        row["carries_reaxys_values"] = "false"
        rows_out.append(row)

        for channel, bucket in per_channel.items():
            if bucket["rows"]:
                tally[channel]["substances_with_rows"] += 1
            if bucket["point"]:
                tally[channel]["substances_with_point_values"] += 1

        evidence[key] = {
            "file": "data/raw/reaxys_w17d/" + path.name,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "tables_captured": captured_categories,
            "rows_captured": captured_rows,
        }

    for key, names in CHANNELS:
        tally[key]["tables"] = sum(
            1 for target in targets
            for table in harvest_for(target["inchikey"])[1]["tables"]
            if table["category"] in names
        )
    return queue_rows, queue_keys, prior, targets, stale_flag, rows_out, evidence, tally
def build_summary(queue_rows, queue_keys, prior, targets, stale_flag, rows_out, evidence, tally):
    p2 = [row for row in queue_rows if row.get("stocking_priority") == QUEUE_PRIORITY]
    return {
        "schema_version": "reaxys_v1x_stocking_query/v1",
        "arm": ARM,
        "week": WEEK,
        "title": TITLE,
        "extends": (
            "W17-13 and W17-15 (the thin-family lanes whose fact tables define already read); "
            "W17-2 (the v1.x stocking queue itself)"
        ),
        "session": {
            "channel": (
                "the author's already signed-in Reaxys tab in Edge, taken over through the Codex "
                "browser channel; no profile copy, no fresh login, no headless scraping"
            ),
            "signed_in_marker": "Reaxys Access avatar QP present, quick search reachable, no login wall",
            "queries_executed": 21,
            "substance_walks": 19,
            "query_budget": 30,
            "extra_submissions": 2,
            "extra_submissions_note": (
                "two search submissions beyond the nineteen distinct substances: the first "
                "fluorobenzene quick search was made by hand while learning the card layout, "
                "and the first m-fluorotoluene walk was submitted again after a sandbox error "
                "stopped that run mid-card. Both were re-submissions of a substance already in "
                "the set, so the walk still covers nineteen distinct substances and no card was "
                "read twice."
            ),
            "blocked_by_session_modal": 0,
            "recovery_note": (
                "the Reaxys session cookie from the previous day had expired and every route "
                "redirected to the institution sign-in screen; the institutional Shibboleth route "
                "was blocked in Edge by the machine's dead system proxy 127.0.0.1:10809, which "
                "handshakes with reaxys.com but times out on idp.whu.edu.cn; a scoped proxy bypass "
                "for whu.edu.cn restored the route, the Edge profile's existing Wuhan University "
                "session then authenticated on its own, and the bypass was reverted afterwards"
            ),
            "interaction": (
                "one substance card at a time; every category table expanded with its own "
                "Show all control to the row count Reaxys reports on the category button"
            ),
        },
        "scope": {
            "queue": "probes/reaxys_v1x_stocking_queue.csv",
            "layer": QUEUE_PRIORITY,
            "p2_rows_in_queue": len(p2),
            "already_read_by_an_earlier_lane": {
                lane: sorted(keys & {row["inchikey"] for row in p2}) for lane, keys in prior.items()
            },
            "never_read_p2_rows": len(targets),
            "brief_named_keys": 19,
            "brief_stated_count": 20,
            "count_resolution": (
                "the brief names nineteen keys and calls the set twenty; the queue holds 22 P2 rows, "
                "three of which earlier lanes had already read, so nineteen is the correct size of "
                "the never-read P2 set and the named list is exactly that set"
            ),
            "targets": sorted(row["inchikey"] for row in targets),
        },
        "channel_tally": tally,
        "substances_queried": len(targets),
        "evidence": {
            "dir": "data/raw/reaxys_w17d (git-ignored, kept verbatim in the repository)",
            "harvest_files": len(evidence),
            "blocked_session_screenshot": (
                "data/raw/reaxys_w17d/blocked_institution_signin.png"
            ),
            "total_bytes": sum(item["bytes"] for item in evidence.values()),
            "tables_captured": sum(item["tables_captured"] for item in evidence.values()),
            "rows_captured": sum(item["rows_captured"] for item in evidence.values()),
            "per_substance": evidence,
        },
        "queue_key_audit": {
            "queue_path": "probes/reaxys_v1x_stocking_queue.csv",
            "queue_sha256": sha256(QUEUE),
            "key_column": "inchikey",
            "keys_checked": len(targets),
            "keys_not_from_the_queue": 0,
            "card_key_matches_queue_key": True,
            "rule": "every substance key must appear verbatim in the queue inchikey column",
            "stale_flag_rows": sorted(stale_flag),
            "stale_flag_note": (
                "the queue probed_in_this_round column is stale: it still reads no for the three P2 "
                "rows W17-13 "
                "and W17-15 already walked, so the target set is computed from the earlier lanes' "
                "fact tables instead of from that flag"
            ),
        },
        "non_interference": {
            "models_fitted": 0,
            "r2_reported": False,
            "main_scoreboard_touched": False,
            "data_tracked_files_modified": [],
        },
        "restricted_contract": {
            "decision": "reports/decisions_log.md section 28.2 (the author's ruling B)",
            "raw_evidence_dir": "data/raw/reaxys_w17d (git-ignored)",
            "this_lane_writes_only_under": ["probes/", "reports/", "tests/"],
            "values_enter_data": False,
            "values_enter_any_pool": False,
            "values_enter_any_feature_table": False,
            "values_ship_in_this_bundle": False,
        },
        "value_columns": {
            category: (column if column else "none - this category has no numeric column")
            for category, column in VALUE_COLUMNS.items()
        },
        "comment_column": "the column whose header starts with Comment (; a number in it is counted only on the comment axis",
        "value_semantics": (
            "Reaxys writes ranges and points into the same value column, so rows (every row of the "
            "category table), valued rows (the value cell is populated, a range included) and point "
            "values (the cell parses as one float) are counted on three separate axes and never "
            "conflated. A row whose value cell is empty but whose Comment cell states a number is "
            "counted only on the comment axis. Ionization Potential, Dynamic Viscosity and Kinematic "
            "Viscosity carry a numeric value column; Dielectric Constant and Static Dielectric "
            "Constant do; Electrochemical Characteristics and Quantum Chemical Calculations do not, "
            "which is why their valued and point counts are zero by construction rather than by "
            "absence of data."
        ),
    }


def render_facts(rows_out):
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(FACT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows_out, key=lambda item: item["inchikey"]):
        writer.writerow(row)
    return buffer.getvalue()


def render_summary(summary):
    return json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="rewrite the facts and summary")
    parser.add_argument("--check", action="store_true", help="fail if the files on disk differ")
    args = parser.parse_args()
    if not (args.overwrite or args.check):
        parser.error("pass --overwrite or --check")

    queue_rows, queue_keys, prior, targets, stale_flag, rows_out, evidence, tally = compose()
    summary = build_summary(
        queue_rows, queue_keys, prior, targets, stale_flag, rows_out, evidence, tally
    )
    facts_text = render_facts(rows_out)
    summary["facts_path"] = "probes/reaxys_v1x_stocking_query_facts.csv"
    summary["facts_sha256"] = hashlib.sha256(facts_text.encode("utf-8")).hexdigest()
    summary_text = render_summary(summary)

    if args.check:
        if FACTS.read_text(encoding="utf-8") != facts_text:
            raise SystemExit("facts table on disk differs from a fresh build")
        if SUMMARY.read_text(encoding="utf-8") != summary_text:
            raise SystemExit("summary on disk differs from a fresh build")
        digest = summary["facts_sha256"]
        print(f"check ok: {len(rows_out)} substances, facts {digest}")
        return
    # newline="" keeps the artefacts LF on Windows; write_text would emit CRLF and
    # the digest pinned in the summary describes the LF bytes.
    with FACTS.open("w", encoding="utf-8", newline="") as handle:
        handle.write(facts_text)
    with SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        handle.write(summary_text)
    digest = summary["facts_sha256"]
    print(f"wrote {len(rows_out)} substances")
    print(f"facts sha256 {digest}")


if __name__ == "__main__":
    main()