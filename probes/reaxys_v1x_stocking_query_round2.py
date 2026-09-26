"""W17-20 - the Reaxys v1.x stocking queue, P3 layer, second walk (round two).

Round one (W17-16) walked the queue's P2 layer and found that every redox potential on a
card sits inside the Comment cell while the value cell of the same row stays empty.  This
lane keeps walking the same queue, drops to the P3 layer, and spends its query slots on the
P3 rows most likely to feed the channel the four-channel board is reddest on - redox
(oxidation MAE 0.2905 eV, reduction MAE 0.4096 eV, gate 0.15 eV, the whole channel flagged as
a 392-label bottleneck rather than a model-capacity one).  Aromatics and heteroaromatics
carry by far the most electrochemical rows per card of anything the earlier lanes read, so
seven of them were walked: acetone, benzonitrile, pyridine, chlorobenzene, bromobenzene,
o-dichlorobenzene and iodobenzene.

The lane keeps round one's restricted contract and its counting axes:

* the restricted contract (reports/decisions_log.md section 28.2, ruling B): Reaxys-derived
  values never enter data/, any pool or any feature table.  Everything this lane writes lives
  under probes/; the raw page evidence stays in the git-ignored data/raw/reaxys_w17e/.
* the key audit: every substance key must come from the queue's inchikey column verbatim, and
  no key may already sit in an earlier lane's fact table.
* the value/number distinction: rows (every row of the category table), valued (the value
  cell is populated, a range included) and point (the value cell parses as one float) are
  counted on three separate axes and never conflated.
* the Comment column: a number can hide in the Comment cell while the value cell of the same
  row stays empty, so those rows are counted on their own axis and never merged into the
  value-column counts.  For Electrochemical Characteristics this is not an edge case: the
  category has no numeric column at all, so every redox number in this batch is a Comment
  number.

Usage::

    python probes/reaxys_v1x_stocking_query_round2.py --overwrite
    python probes/reaxys_v1x_stocking_query_round2.py --check
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
RAW_DIR = ROOT / "data" / "raw" / "reaxys_w17e"
FACTS = ROOT / "probes" / "reaxys_v1x_stocking_query_round2_facts.csv"
SUMMARY = ROOT / "probes" / "reaxys_v1x_stocking_query_round2_summary.json"

PRIOR_LANES = (
    ("W17-13", ROOT / "probes" / "reaxys_thin_family_query_facts.csv"),
    ("W17-15", ROOT / "probes" / "reaxys_thin_family_query_b2_facts.csv"),
    ("W17-16", ROOT / "probes" / "reaxys_v1x_stocking_query_facts.csv"),
)

ARM = "W17-20"
WEEK = "week17"
TITLE = (
    "Reaxys v1.x stocking queue, P3 layer round two: seven redox-rich aromatics and a nitrile, "
    "where the redox channel at last has rows to give (121 of them, 71 carrying a Comment "
    "number) but still not one numeric value column, epsilon and eta add 224 and 177 rows, and "
    "the orbital channel stays ionization potentials only"
)

QUEUE_PRIORITY = "P3"
POINT = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
NUMBER_IN_TEXT = re.compile(r"[-+]?\d+(?:\.\d+)?")
VOLT_IN_TEXT = re.compile(r"[-+]?\d+(?:\.\d+)?\s*V\b")

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
    "Bulk Viscosity": "Bulk Viscosity, P",
    "Quantum Chemical Calculations": None,
    "Calculated Properties": None,
    "Electrochemical Characteristics": None,
}

CHANNEL_DEFINITIONS = {
    "eps": "Dielectric Constant + Static Dielectric Constant",
    "eta": "Dynamic Viscosity + Kinematic Viscosity (Bulk Viscosity deliberately excluded)",
    "hp": (
        "Ionization Potential + Quantum Chemical Calculations (labelled Calculated Properties "
        "on the card). Both are orbital-adjacent; neither is a HOMO, a LUMO or a gap"
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
    "substances_in_result_list",
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

CATEGORY_CHANNEL = {name: key for key, names in CHANNELS for name in names}


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
    """Rows, valued rows, point values and Comment-only numbers of one category table."""
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


def harvest_for(key):
    slug = key.split("-")[0]
    path = RAW_DIR / ("harvest_" + slug + ".json")
    if not path.exists():
        raise SystemExit("missing raw harvest " + path.name)
    return path, read_json(path)


def walk_keys():
    """The walked set is whatever raw evidence this lane actually saved."""
    keys = []
    for path in sorted(RAW_DIR.glob("harvest_*.json")):
        keys.append(read_json(path)["inchikey_searched"])
    return keys


def resolve_targets(queue_rows, queue_keys, prior):
    walked = set(walk_keys())
    walked_before = set().union(*prior.values()) if prior else set()
    overlap = walked & walked_before
    if overlap:
        raise SystemExit(
            "these keys were already read by an earlier lane: " + ", ".join(sorted(overlap))
        )
    targets = [row for row in queue_rows if row.get("inchikey") in walked]
    missing = walked - {row["inchikey"] for row in targets}
    if missing:
        raise SystemExit("walked keys absent from the queue: " + ", ".join(sorted(missing)))
    return targets, walked


def compose():
    queue_rows = read_csv(QUEUE)
    queue_keys = {row["inchikey"] for row in queue_rows if row.get("inchikey")}
    prior = {}
    for lane, path in PRIOR_LANES:
        prior[lane] = {row["inchikey"] for row in read_csv(path) if row.get("inchikey")}
    targets, walked = resolve_targets(queue_rows, queue_keys, prior)
    if len(targets) != len(walked):
        raise SystemExit("target resolution dropped a walked key")

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
    comment_rows = 0
    comment_volt_rows = 0

    for target in targets:
        key = target["inchikey"]
        if key not in queue_keys:
            raise SystemExit(
                key + " is not an inchikey in the v1.x stocking queue; hand-typed keys are "
                "not allowed here"
            )
        path, harvest = harvest_for(key)
        if harvest.get("inchikey_searched") != key:
            raise SystemExit(key + ": harvest searched another key")
        on_card = (harvest.get("identification") or {}).get("InChIKey")
        if on_card != key:
            raise SystemExit(key + ": card InChIKey " + repr(on_card) + " != queue key")

        per_channel = {
            name: {"rows": 0, "valued": 0, "point": 0, "point_from_comment": 0}
            for name in ("eps", "eta", "hp", "redox")
        }
        captured_categories = 0
        captured_rows = 0
        for table in harvest["tables"]:
            category = table["category"]
            read_rows = len(table["rows"])
            if read_rows != table["reported"]:
                raise SystemExit(
                    key + "/" + str(category) + ": " + str(read_rows) + " rows read but Reaxys "
                    "reports " + str(table["reported"])
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
            if channel == "redox":
                comment_at = comment_index(table["headers"])
                for row in table["rows"]:
                    comment = cell(row, comment_at)
                    if comment and NUMBER_IN_TEXT.search(comment):
                        comment_rows += 1
                        if VOLT_IN_TEXT.search(comment):
                            comment_volt_rows += 1

        ident = harvest.get("identification") or {}
        row = {
            "inchikey": key,
            "name": target["name"],
            "family_tag": target["family_tag"],
            "queue_rank": target["queue_rank"],
            "stocking_priority": target["stocking_priority"],
            "card_inchikey": on_card,
            "reaxys_rn": ident.get("Reaxys Registry Number") or "",
            "cas": ident.get("CAS Registry Number(s)") or "",
            "substances_in_result_list": harvest.get("n_substances_in_result_list", ""),
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
            "file": "data/raw/reaxys_w17e/" + path.name,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "tables_captured": captured_categories,
            "rows_captured": captured_rows,
        }

    for key, names in CHANNELS:
        tally[key]["tables"] = sum(
            1
            for target in targets
            for table in harvest_for(target["inchikey"])[1]["tables"]
            if table["category"] in names
        )
    audit = {
        "redox_rows_with_a_number_in_the_comment_cell": comment_rows,
        "redox_comment_rows_stating_a_volt_value": comment_volt_rows,
        "redox_comment_rows_with_a_number_but_no_volt_value": comment_rows - comment_volt_rows,
        "note": (
            "a Comment number that is a concentration (0.1 M nBu4PF6) is not a potential; only "
            "the volt-stating rows are counted separately, and neither set becomes a value"
        ),
    }
    return queue_rows, queue_keys, prior, targets, rows_out, evidence, tally, audit


def build_summary(queue_rows, queue_keys, prior, targets, rows_out, evidence, tally, audit):
    p3 = [row for row in queue_rows if row.get("stocking_priority") == QUEUE_PRIORITY]
    return {
        "schema_version": "reaxys_v1x_stocking_query_round2/v1",
        "arm": ARM,
        "week": WEEK,
        "title": TITLE,
        "extends": (
            "W17-16 (the round-one P2 stocking walk whose Comment-column finding this lane "
            "confirms on seven more cards); W17-13 and W17-15 (the thin-family lanes whose fact "
            "tables define already read)"
        ),
        "session": {
            "channel": (
                "the author's already signed-in Reaxys tab in Edge, taken over through the Codex "
                "browser channel; no profile copy, no fresh login, no headless scraping"
            ),
            "signed_in_marker": (
                "Reaxys Access avatar QP present, quick search reachable, no login wall"
            ),
            "queries_executed": 9,
            "substance_walks": 7,
            "query_budget": 30,
            "prior_round_queries": 21,
            "cumulative_queries": 30,
            "extra_submissions": 2,
            "extra_submissions_note": (
                "two search submissions beyond the seven distinct substances, both on "
                "chlorobenzene: the first quick search was made by hand while learning the card "
                "layout on this round's first substance, and the first full card walk was "
                "submitted again after a script error stopped that run between the search and "
                "the table read. Both were re-submissions of a substance already in the set, so "
                "the walk still covers seven distinct substances and no card was read twice."
            ),
            "blocked_by_session_modal": 0,
            "interaction": (
                "one substance card at a time; Physical Data expanded, its category list walked "
                "to the end with its own Load More control, and every channel category expanded "
                "with its own Show all control to the row count Reaxys reports on the category "
                "button"
            ),
        },
        "scope": {
            "queue": "probes/reaxys_v1x_stocking_queue.csv",
            "layer": QUEUE_PRIORITY,
            "p3_rows_in_queue": len(p3),
            "already_read_by_an_earlier_lane": {
                lane: sorted(keys & {row["inchikey"] for row in p3})
                for lane, keys in prior.items()
            },
            "walked_this_round": sorted(row["inchikey"] for row in targets),
            "never_read_assertion": (
                "no walked key appears in any earlier lane's fact table; the generator raises "
                "rather than silently overlapping"
            ),
        },
        "selection": {
            "strategy": (
                "spend the whole budget on the P3 rows most likely to carry redox rows, because "
                "redox is the channel the four-channel board is reddest on, then read epsilon "
                "and eta off the same cards for free"
            ),
            "channels_targeted": ["redox", "eps", "eta", "hp"],
            "why_these_seven": (
                "aromatics and heteroaromatics carry the most Electrochemical Characteristics "
                "rows per card of anything the earlier lanes read; a nitrile (benzonitrile) and "
                "a ketone (acetone) were added as electrolyte-solvent-relevant probes of the "
                "same channel"
            ),
            "queue_priority": QUEUE_PRIORITY,
        },
        "channel_tally": tally,
        "redox_comment_audit": audit,
        "substances_queried": len(targets),
        "evidence": {
            "dir": "data/raw/reaxys_w17e (git-ignored, kept verbatim in the repository)",
            "harvest_files": len(evidence),
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
        },
        "non_interference": {
            "models_fitted": 0,
            "r2_reported": False,
            "main_scoreboard_touched": False,
            "data_tracked_files_modified": [],
        },
        "restricted_contract": {
            "decision": "reports/decisions_log.md section 28.2 (the author's ruling B)",
            "raw_evidence_dir": "data/raw/reaxys_w17e (git-ignored)",
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
        "comment_column": (
            "the column whose header starts with Comment (; a number in it is counted only on "
            "the comment axis"
        ),
        "value_semantics": (
            "Reaxys writes ranges and points into the same value column, so rows, valued rows "
            "and point values are counted on three separate axes and never conflated. A row "
            "whose value cell is empty but whose Comment cell states a number is counted only "
            "on the comment axis. Ionization Potential, Dynamic Viscosity, Kinematic Viscosity, "
            "Bulk Viscosity and both dielectric categories carry a numeric value column; "
            "Electrochemical Characteristics and Quantum Chemical Calculations do not, which is "
            "why their valued and point counts are zero by construction rather than by absence "
            "of data."
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

    queue_rows, queue_keys, prior, targets, rows_out, evidence, tally, audit = compose()
    summary = build_summary(
        queue_rows, queue_keys, prior, targets, rows_out, evidence, tally, audit
    )
    facts_text = render_facts(rows_out)
    summary["facts_path"] = "probes/reaxys_v1x_stocking_query_round2_facts.csv"
    summary["facts_sha256"] = hashlib.sha256(facts_text.encode("utf-8")).hexdigest()
    summary_text = render_summary(summary)

    if args.check:
        if FACTS.read_text(encoding="utf-8") != facts_text:
            raise SystemExit("facts table on disk differs from a fresh build")
        if SUMMARY.read_text(encoding="utf-8") != summary_text:
            raise SystemExit("summary on disk differs from a fresh build")
        digest = summary["facts_sha256"]
        print("check ok: " + str(len(rows_out)) + " substances, facts " + digest)
        return
    with FACTS.open("w", encoding="utf-8", newline="") as handle:
        handle.write(facts_text)
    with SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        handle.write(summary_text)
    digest = summary["facts_sha256"]
    print("wrote " + str(len(rows_out)) + " substances")
    print("facts sha256 " + digest)


if __name__ == "__main__":
    main()
