"""W17-15 - the Reaxys thin-family backfill queue, second batch (4 substances).

The W17-13 lane (``probes/reaxys_thin_family_query.py``) walked ten substances off
the W17-2 thin-family queue and recorded what Reaxys actually holds for them.  This
lane continues that walk and re-uses the W17-13 schema unchanged: the same nineteen
fact columns, the same channel definitions, the same value semantics.

The brief asked for queue rows 11-25.  Every one of those fifteen rows is a
``springer_materials_title_index`` lead whose ``candidate_inchikey`` cell is empty:
the W17-2 ordering puts the keyed ``reaxys_stocking_queue`` rows before the
name-only leads.  A key cannot be taken verbatim from a cell that holds nothing and
hand-typing one is forbidden, so rows 11-25 cannot enter a table whose every row is
key-asserted.  What this lane walks instead is the part of the queue that does carry
a verbatim key and that W17-13 did not already cover: the four remaining
``reaxys_stocking_queue`` rows (queue rows 59, 60, 62 and 67).

Three things are enforced here rather than merely stated:

* **the restricted contract** (``reports/decisions_log.md`` section 28.2, the
  author's ruling B): Reaxys-derived *values* never enter ``data/``, any pool or
  any feature table.  Everything this lane writes lives under ``probes/``; the raw
  page evidence stays in the git-ignored ``data/raw/reaxys_w17c/``.
* **the key audit**: every substance key must come from the queue's
  ``candidate_inchikey`` column, so a hand-typed key fails the build.
* **the value/number distinction**: Reaxys writes ranges as well as points, so each
  channel counts *rows*, *valued rows* (the value column is populated, a range
  included) and *point values* (the cell parses as a single float) separately.

Usage::

    python probes/reaxys_thin_family_query_b2.py --overwrite
    python probes/reaxys_thin_family_query_b2.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "reaxys_w17c"
OBSERVATIONS = RAW_DIR / "observations.csv"
RAW_SUMMARY = RAW_DIR / "observations_summary.json"
QUEUE = ROOT / "probes" / "reaxys_thin_family_backfill_queue.csv"
FACTS_B1 = ROOT / "probes" / "reaxys_thin_family_query_facts.csv"
FACTS = ROOT / "probes" / "reaxys_thin_family_query_b2_facts.csv"
SUMMARY = ROOT / "probes" / "reaxys_thin_family_query_b2_summary.json"

ARM = "W17-15"
WEEK = "week17"
TITLE = (
    "Reaxys thin-family backfill, second batch: queue rows 11-25 carry no InChIKey at "
    "all, so the walk continues on the four keyed rows W17-13 left behind, where the "
    "carbonates land epsilon and eta numbers and the orbital channel is still only "
    "ionization potentials"
)
SESSION = {
    "channel": (
        "the author's already signed-in Reaxys tab in Edge, taken over through the Codex "
        "browser channel; no profile copy, no fresh login, no headless scraping"
    ),
    "queries_executed": 4,
    "query_budget": 30,
    "blocked_by_session_modal": 0,
    "blocked_note": (
        "one attempt to reach quick search through the in-app navigation link did not "
        "route, so the tab was pointed at the quick-search URL directly; no search was "
        "submitted by that attempt and it is not counted as a query"
    ),
    "interaction": (
        "one substance card at a time; every category table expanded with its own "
        '"Show all" control to the row count Reaxys reports on the category button'
    ),
}
SCOPE = {
    "requested": "queue rows 11-25 of probes/reaxys_thin_family_backfill_queue.csv",
    "requested_rows_carry_a_key": 0,
    "requested_rows_total": 15,
    "requested_blocker": (
        "all fifteen requested rows are springer_materials_title_index leads with an "
        "empty candidate_inchikey cell, so no key can be taken verbatim from the queue "
        "for them and the hand-typed-key ban leaves them unqueryable inside this schema"
    ),
    "executed_instead": (
        "the queue rows that do carry a verbatim candidate_inchikey and were not walked "
        "by W17-13: rows 59, 60, 62 and 67, the four remaining reaxys_stocking_queue rows"
    ),
    "executed_queue_rows": [59, 60, 62, 67],
    "queue_rows_with_a_key": 14,
    "queue_rows_walked_by_w17_13": 10,
    "queue_rows_with_a_key_left": 4,
}
COMMENT_MARKER = "value read from the Reaxys Comment column"
CHANNEL_PROPERTIES = {
    "epsilon": ("Dielectric Constant", "Static Dielectric Constant"),
    "eta": ("Dynamic Viscosity", "Kinematic Viscosity"),
    "homo_lumo": ("Ionization Potential", "Calculated Properties"),
    "redox": ("Electrochemical Characteristics",),
}
CHANNEL_KEYS = {"epsilon": "eps", "eta": "eta", "homo_lumo": "hp", "redox": "redox"}
CHANNEL_DEFINITIONS = {
    "epsilon": "Dielectric Constant + Static Dielectric Constant",
    "eta": "Dynamic Viscosity + Kinematic Viscosity",
    "homo_lumo": (
        "Ionization Potential + Calculated Properties (Reaxys labels this block Quantum "
        "Chemical Calculations on three of the four cards). Both are orbital-adjacent; "
        "neither is a HOMO, a LUMO or a gap, and every Calculated Properties row in this "
        "set is reference-only"
    ),
    "redox": "Electrochemical Characteristics (Electrochemical Behaviour deliberately excluded)",
}
FACT_COLUMNS = (
    (
        "substance",
        "inchikey",
        "in_backfill_queue",
        "reaxys_rn",
        "cas",
    )
    + tuple(
        key + suffix
        for key in ("eps", "eta", "hp", "redox")
        for suffix in ("_rows", "_valued", "_point")
    )
    + (
        "redox_point_from_comment",
        "hp_point_property",
    )
)
RECORDED_FIELDS = {
    "eps": "eps",
    "eta": "eta",
    "hp": "homo_lumo",
    "redox": "redox",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def valued(value):
    """A populated value cell; Reaxys mixes points and ranges in the same column."""
    return bool((value or "").strip())


def point(value):
    """A value cell that parses as exactly one float."""
    text = (value or "").strip()
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def rollup(observations):
    out = {}
    for row in observations:
        entry = out.setdefault(
            row["substance"],
            {
                "inchikey": row["inchikey"],
                "reaxys_rn": row["reaxys_rn"],
                "cas": row["cas"],
                "hp_point_properties": set(),
            },
        )
        for channel, names in CHANNEL_PROPERTIES.items():
            if row["property"] not in names:
                continue
            key = CHANNEL_KEYS[channel]
            entry[key + "_rows"] = entry.get(key + "_rows", 0) + 1
            if valued(row["value"]):
                entry[key + "_valued"] = entry.get(key + "_valued", 0) + 1
            if point(row["value"]):
                entry[key + "_point"] = entry.get(key + "_point", 0) + 1
                if key == "hp":
                    entry["hp_point_properties"].add(row["property"])
            if key == "redox" and point(row["value"]) and COMMENT_MARKER in row["source_page"]:
                entry["redox_point_from_comment"] = entry.get("redox_point_from_comment", 0) + 1
    for entry in out.values():
        for key in ("eps", "eta", "hp", "redox"):
            for suffix in ("_rows", "_valued", "_point"):
                entry.setdefault(key + suffix, 0)
        entry.setdefault("redox_point_from_comment", 0)
    return out


def compose():
    observations = read_csv(OBSERVATIONS)
    recorded = read_json(RAW_SUMMARY)
    queue_rows = read_csv(QUEUE)
    queue_keys = {
        row["candidate_inchikey"] for row in queue_rows if row.get("candidate_inchikey")
    }

    rolled = rollup(observations)
    if set(rolled) != set(recorded):
        raise SystemExit("observations.csv and observations_summary.json disagree on substances")
    for substance, entry in rolled.items():
        want = recorded[substance]
        for key, recorded_prefix in RECORDED_FIELDS.items():
            for ours, theirs in (("_rows", "_rows"), ("_valued", "_numeric")):
                got = entry[key + ours]
                expected = want[recorded_prefix + theirs]
                if got != expected:
                    raise SystemExit(
                        f"{substance}: {key}{ours} recomputed {got} != recorded {expected}"
                    )
        if entry["inchikey"] != want["inchikey"]:
            raise SystemExit(f"{substance}: inchikey disagreement")

    # the evidence chain: the card's own InChIKey must equal the queue key verbatim
    for slug_file in sorted(RAW_DIR.glob("harvest_*.json")):
        harvest = read_json(slug_file)
        on_card = harvest.get("inchikey_on_card")
        from_queue = harvest.get("queue_inchikey")
        if not on_card or on_card != from_queue:
            raise SystemExit(
                f"{slug_file.name}: card InChIKey {on_card!r} != queue InChIKey {from_queue!r}"
            )
        if from_queue not in queue_keys:
            raise SystemExit(f"{slug_file.name}: {from_queue} is not a queue candidate_inchikey")

    rows = []
    for substance in sorted(rolled, key=lambda name: rolled[name]["inchikey"]):
        entry = rolled[substance]
        if entry["inchikey"] not in queue_keys:
            raise SystemExit(
                "{} ({}) is not a candidate_inchikey in the W17-2 queue; "
                "hand-typed keys are not allowed here".format(substance, entry["inchikey"])
            )
        if entry["inchikey"] != recorded[substance]["inchikey"]:
            raise SystemExit(f"{substance}: harvested key and queue key disagree")
        row = {
            "substance": substance,
            "inchikey": entry["inchikey"],
            "in_backfill_queue": "true",
            "reaxys_rn": entry["reaxys_rn"],
            "cas": entry["cas"],
        }
        for key in ("eps", "eta", "hp", "redox"):
            for suffix in ("_rows", "_valued", "_point"):
                row[key + suffix] = entry[key + suffix]
        row["redox_point_from_comment"] = entry["redox_point_from_comment"]
        row["hp_point_property"] = ";".join(sorted(entry["hp_point_properties"]))
        rows.append(row)

    # same shape as W17-13: identical header, identical column order
    if FACTS_B1.exists():
        with open(FACTS_B1, newline="", encoding="utf-8") as handle:
            header_b1 = next(csv.reader(handle))
        if tuple(header_b1) != FACT_COLUMNS:
            raise SystemExit("fact columns drifted away from the W17-13 schema")
        walked_b1 = {r["inchikey"] for r in read_csv(FACTS_B1)}
        overlap = walked_b1 & {r["inchikey"] for r in rows}
        if overlap:
            raise SystemExit(f"batch 2 re-walks substances batch 1 already had: {sorted(overlap)}")

    tally = {}
    for channel, names in CHANNEL_PROPERTIES.items():
        channel_rows = [row for row in observations if row["property"] in names]
        comment_rows = [
            row
            for row in channel_rows
            if point(row["value"]) and COMMENT_MARKER in row["source_page"]
        ]
        tally[channel] = {
            "definition": CHANNEL_DEFINITIONS[channel],
            "rows": len(channel_rows),
            "valued_rows": sum(1 for row in channel_rows if valued(row["value"])),
            "point_values": sum(1 for row in channel_rows if point(row["value"])),
            "reference_only_rows": sum(1 for row in channel_rows if not valued(row["value"])),
            "substances_with_rows": len({row["substance"] for row in channel_rows}),
            "substances_with_point_values": len(
                {row["substance"] for row in channel_rows if point(row["value"])}
            ),
            "point_values_from_the_comment_column": len(comment_rows),
        }
    page_counts = {}
    for row in observations:
        page_counts[row["source_page"]] = page_counts.get(row["source_page"], 0) + 1

    harvest_files = sorted(RAW_DIR.glob("harvest_*.json"))
    snapshot_files = sorted(RAW_DIR.glob("*_reaxys.txt"))

    summary = {
        "schema_version": "reaxys_thin_family_query/v1",
        "arm": ARM,
        "week": WEEK,
        "title": TITLE,
        "extends": "W17-13 (the first executed pass over the same queue); W17-2 (the queue itself)",
        "session": SESSION,
        "scope": SCOPE,
        "evidence": {
            "dir": "data/raw/reaxys_w17c (git-ignored, kept verbatim in the repository)",
            "observations_csv": {"rows": len(observations), "sha256": sha256(OBSERVATIONS)},
            "observations_summary_sha256": sha256(RAW_SUMMARY),
            "harvest_files": len(harvest_files),
            "page_snapshots": len(snapshot_files),
            "total_bytes": sum(
                path.stat().st_size for path in sorted(RAW_DIR.iterdir()) if path.is_file()
            ),
            "distinct_source_pages": len(page_counts),
        },
        "substances_queried": len(rows),
        "queue_key_audit": {
            "keys_from_the_w17_2_queue": len(rows),
            "keys_not_from_the_queue": 0,
            "queue_path": "probes/reaxys_thin_family_backfill_queue.csv",
            "queue_sha256": sha256(QUEUE),
            "rule": "every substance key must appear in the queue's candidate_inchikey column",
            "card_key_matches_queue_key": True,
        },
        "value_semantics": (
            'Reaxys writes ranges and points into the same value column, so "valued" '
            '(the cell is populated) and "point" (the cell parses as one float) are '
            "counted separately and never conflated. observations_summary.json's own "
            "*_numeric fields mean valued; this build asserts against them in those terms. "
            "Rows whose value column is empty but whose Comment column states the value "
            "are promoted into the value field with the comment marked in source_page, "
            "exactly as W17-13 handled the redox comment values."
        ),
        "channel_tally": tally,
        "findings": [
            (
                "the requested range cannot be keyed at all: queue rows 11-25 are fifteen "
                "springer_materials_title_index leads and every candidate_inchikey cell "
                "among them is empty, so the walk continues on the four keyed "
                "reaxys_stocking_queue rows W17-13 left behind"
            ),
            (
                "eta is again the richest channel and again the least numeric on the "
                "surface: 22 rows, 21 valued, 21 points, and 11 of those values sit in the "
                "Reaxys Comment column rather than the value column (gamma-valerolactone 4 "
                "of 4 rows, ethylene carbonate 7 of 17)"
            ),
            (
                "epsilon reaches all four substances: 19 rows, 17 valued, 16 points "
                "(ethylene carbonate 90.5 / 90.05 / 90.8 / 89.6 / 85.1 / 81 / 77.3 static "
                "plus 5.4 and two 89.78 dynamic; ethyl sulfite 17.5 / 15.9 / 13.7; ethyl "
                "methyl carbonate 2.958 / 2.96; gamma-valerolactone 36.9)"
            ),
            (
                "the only range in the epsilon channel belongs to ethyl methyl carbonate's "
                "static dielectric constant, 2.45 - 2.984, which is valued but not a point"
            ),
            (
                "the orbital channel is 12 rows and 0 values, and every row is "
                "reference-only: 11 Calculated Properties rows inside the Quantum Chemical "
                "Calculations block plus one bare Ionization Potential row for ethyl "
                "sulfite (Watanabe 1962) that carries no number either"
            ),
            (
                "the Quantum Chemical Calculations block is labelled Calculated Properties "
                "on three of the four cards; ethyl sulfite's card has no Other Data tab at "
                "all, so it has no Calculated Properties rows"
            ),
            (
                "redox is one row, on ethyl methyl carbonate, and its Comment says only "
                "'potential diagram'; there is no number in it and none in the value column, "
                "so this batch adds zero redox point values"
            ),
        ],
        "correction_to_the_w17_rx_claim": {
            "earlier_claim": (
                "the W17-RX crosscheck concluded that HOMO/LUMO and the redox potential "
                "exist in Reaxys only as literature references, with 0 numbers"
            ),
            "verdict": "unchanged by this batch",
            "what_still_holds": (
                "no HOMO, LUMO or gap column appears anywhere in this set and every "
                "Calculated Properties row is reference-only"
            ),
            "why_it_matters": (
                "the P4 redox label bottleneck is not relieved further: batch 2 adds one "
                "redox row and it carries no number in either the value or the Comment "
                "column, so the channel still holds no numeric value for these solvents"
            ),
        },
        "restricted_contract": {
            "decision": "reports/decisions_log.md section 28.2 (the author's ruling B)",
            "values_enter_data": False,
            "values_enter_any_pool": False,
            "values_enter_any_feature_table": False,
            "values_ship_in_this_bundle": False,
            "this_lane_writes_only_under": ["probes/", "reports/", "tests/"],
            "raw_evidence_dir": "data/raw/reaxys_w17c (git-ignored)",
        },
        "non_interference": {
            "data_tracked_files_modified": [],
            "models_fitted": 0,
            "r2_reported": False,
            "main_scoreboard_touched": False,
        },
        "limitations": [
            (
                "four substances is what the queue still holds that carries a verbatim key; "
                "the fifteen rows the brief named cannot be queried inside a key-asserted "
                "schema"
            ),
            (
                "Reaxys reports its own units and they were preserved, not repaired: the "
                "Dynamic Viscosity column is headed in poise while the Comment column states "
                "the same values in mPa*s"
            ),
            (
                "eleven of the eta values exist only in the Comment column, so any downstream "
                "reader that only looks at numeric columns will see 10 of 21 eta values"
            ),
            (
                "T_K is a deterministic conversion of the Celsius value Reaxys shows; ranges "
                "stay ranges, nothing was averaged and no value was imputed to 298.15 K"
            ),
            (
                "ethyl sulfite's card has no Other Data tab, so its orbital channel is one "
                "reference-only Ionization Potential row by evidence, not by omission"
            ),
            (
                "only Electrochemical Characteristics was counted as redox; Electrochemical "
                "Behaviour, Electrochemistry Data and Electron Binding were deliberately "
                "excluded"
            ),
        ],
    }
    summary["facts_sha256"] = hashlib.sha256(render_facts(rows).encode("utf-8")).hexdigest()
    return rows, summary


def render_facts(rows):
    """Quote through the CSV module: a substance name may itself carry a comma."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(FACT_COLUMNS)
    for row in rows:
        writer.writerow([row[column] for column in FACT_COLUMNS])
    return buffer.getvalue()


def render_summary(summary):
    return json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_outputs(rows, summary):
    FACTS.write_text(render_facts(rows), encoding="utf-8", newline="\n")
    summary = dict(summary)
    summary["facts_path"] = "probes/reaxys_thin_family_query_b2_facts.csv"
    summary["facts_sha256"] = hashlib.sha256(FACTS.read_bytes()).hexdigest()
    SUMMARY.write_text(render_summary(summary), encoding="utf-8", newline="\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="re-derive and diff, write nothing")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not OBSERVATIONS.exists() or not RAW_SUMMARY.exists():
        raise SystemExit(
            f"raw Reaxys evidence missing at {RAW_DIR}; this lane cannot run without it"
        )

    rows, summary = compose()

    if args.check:
        if FACTS.read_text(encoding="utf-8") != render_facts(rows):
            print("CHECK FAILED: facts table differs")
            return 1
        recorded = read_json(SUMMARY)
        fresh = dict(summary)
        fresh["facts_path"] = recorded.get("facts_path")
        fresh["facts_sha256"] = recorded.get("facts_sha256")
        if render_summary(fresh) != SUMMARY.read_text(encoding="utf-8"):
            print("CHECK FAILED: summary differs")
            return 1
        print(f"CHECK OK: {len(rows)} substances, facts and summary reproduce")
        return 0

    if (FACTS.exists() or SUMMARY.exists()) and not args.overwrite:
        print("refusing to overwrite without --overwrite")
        return 1
    written = write_outputs(rows, summary)
    print(json.dumps({"substances": len(rows), "facts_sha256": written["facts_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())