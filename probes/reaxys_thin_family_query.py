"""W17-13 - the Reaxys thin-family backfill queue, actually executed (10 substances).

The W17-2 lane shipped a *queue* and explicitly executed zero Reaxys queries.
This lane walks the head of that queue on the author's signed-in Reaxys session
and records what Reaxys actually holds for each substance, so the W17-2 plan
stops being a plan and starts being measured evidence.

Three things are enforced here rather than merely stated:

* **the restricted contract** (``reports/decisions_log.md`` section 28.2, the
  author's ruling B): Reaxys-derived *values* never enter ``data/``, any pool or
  any feature table.  Everything this lane writes lives under ``probes/``; the
  raw page evidence stays in the git-ignored ``data/raw/reaxys_w17b/``.
* **the key audit**: every substance key must come from the queue's
  ``candidate_inchikey`` column, so a hand-typed key fails the build.
* **the value/number distinction**: Reaxys writes ranges as well as points, so
  each channel counts *rows*, *valued rows* (the value column is populated, a
  range included) and *point values* (the cell parses as a single float)
  separately.  The value layer's own ``*_numeric`` field means "valued", and the
  build asserts against it in those terms.

The per-substance rollup is recomputed from ``observations.csv`` and asserted
against ``observations_summary.json`` before anything is written.

Usage::

    python probes/reaxys_thin_family_query.py --overwrite
    python probes/reaxys_thin_family_query.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "reaxys_w17b"
OBSERVATIONS = RAW_DIR / "observations.csv"
RAW_SUMMARY = RAW_DIR / "observations_summary.json"
QUEUE = ROOT / "probes" / "reaxys_thin_family_backfill_queue.csv"
FACTS = ROOT / "probes" / "reaxys_thin_family_query_facts.csv"
SUMMARY = ROOT / "probes" / "reaxys_thin_family_query_summary.json"

ARM = "W17-13"
WEEK = "week17"
TITLE = (
    "Reaxys thin-family backfill, executed: 10 substances walked off the W17-2 "
    "queue, epsilon and eta carry numbers, the orbital channel only ever carries "
    "ionization potentials, and the five redox numbers that exist hide in a Comment"
)
SESSION = {
    "channel": (
        "the author's already signed-in Reaxys tab, taken over through the Codex "
        "browser channel; no profile copy, no fresh login, no headless scraping"
    ),
    "queries_executed": 21,
    "query_budget": 25,
    "blocked_by_session_modal": 1,
    "blocked_note": (
        'one click was swallowed by the "Search results ... no longer available in '
        'this session" modal, produced no result row and is not counted as a query'
    ),
    "interaction": (
        "one substance card at a time; category tables expanded to their reported "
        "row counts, never paged blindly"
    ),
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
        "Ionization Potential + Calculated Properties (the Quantum Chemical Calculations "
        "block). Both are orbital-adjacent; neither is a HOMO, a LUMO or a gap, and every "
        "Calculated Properties row in this set is reference-only"
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
    queue_keys = {
        row["candidate_inchikey"] for row in read_csv(QUEUE) if row.get("candidate_inchikey")
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

    rows = []
    for substance in sorted(rolled, key=lambda name: rolled[name]["inchikey"]):
        entry = rolled[substance]
        if entry["inchikey"] not in queue_keys:
            raise SystemExit(
                "{} ({}) is not a candidate_inchikey in the W17-2 queue; "
                "hand-typed keys are not allowed here".format(substance, entry["inchikey"])
            )
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
        "extends": "W17-2 (the queue this lane walks); W17-RX (the first Reaxys crosscheck)",
        "session": SESSION,
        "evidence": {
            "dir": "data/raw/reaxys_w17b (git-ignored, kept verbatim in the repository)",
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
        },
        "value_semantics": (
            'Reaxys writes ranges and points into the same value column, so "valued" '
            '(the cell is populated) and "point" (the cell parses as one float) are '
            "counted separately and never conflated. observations_summary.json's own "
            "*_numeric fields mean valued; this build asserts against them in those terms."
        ),
        "channel_tally": tally,
        "findings": [
            (
                "epsilon reaches 6 of the 10 substances and carries point values for 5 of them "
                "(59 point values out of 78 rows); the four protic ionic liquids have no epsilon "
                "category on their Reaxys card at all, which is a gap in Reaxys, not a gap in "
                "the query"
            ),
            (
                "dynamic viscosity is by far the richest channel: 169 rows, 143 point values, "
                "point values on all 10 substances"
            ),
            (
                "the orbital channel in Reaxys is *Ionization Potential* plus the reference-only "
                "Quantum Chemical Calculations block: 24 rows, 10 point values, and all 10 are "
                "ionization potentials (acetic acid 10.32-10.38 / 10.35 / 10.6-10.7 / 10.66 / "
                "10.7 / 10.72 / 11.15 eV; butyric acid 10.17 / 10.24 / 10.22 eV). An ionization "
                "potential is not an orbital energy and never enters the orbital channel"
            ),
            (
                "the redox channel has 19 Electrochemical Characteristics rows but only 5 point "
                "values, and all 5 sit in the Reaxys *Comment* column rather than the value "
                "column: trifluoroacetic acid -1.2 V and valeric acid -1.35 / -1.08 / -1.40 / "
                "-1.44 V"
            ),
            (
                "the Quantum Chemical Calculations block is reference-only everywhere it appears "
                "in this set: 6 rows, 0 values, including propylene carbonate's Electronic energy "
                "levels / Molecular orbitals / Density of states (DFT) entries"
            ),
        ],
        "correction_to_the_w17_rx_claim": {
            "earlier_claim": (
                "the W17-RX crosscheck concluded that HOMO/LUMO and the redox potential exist "
                "in Reaxys only as literature references, with 0 numbers"
            ),
            "verdict": "narrowed, not overturned",
            "what_still_holds": (
                "there is no HOMO, LUMO or gap column anywhere in this set, and the Quantum "
                "Chemical Calculations block stays reference-only"
            ),
            "what_has_to_be_narrowed": (
                "that conclusion was measured on five carbonate and nitrile solvents. Extended "
                "to ten thin-family substances it holds for the *orbital* channel only: the "
                "redox channel does carry 5 point values, on two carboxylic acids, all five of "
                "them written in the Comment column instead of the value column"
            ),
            "why_it_matters": (
                "the P4 redox label bottleneck (392 rows) is not relieved: 5 numbers on 2 "
                "substances, none in a numeric column, and still no numeric HOMO/LUMO at all"
            ),
        },
        "restricted_contract": {
            "decision": "reports/decisions_log.md section 28.2 (the author's ruling B)",
            "values_enter_data": False,
            "values_enter_any_pool": False,
            "values_enter_any_feature_table": False,
            "values_ship_in_this_bundle": False,
            "this_lane_writes_only_under": ["probes/", "reports/", "tests/"],
            "raw_evidence_dir": "data/raw/reaxys_w17b (git-ignored)",
        },
        "non_interference": {
            "data_tracked_files_modified": [],
            "models_fitted": 0,
            "r2_reported": False,
            "main_scoreboard_touched": False,
        },
        "limitations": [
            "ten substances is the head of a 124-row queue, not the queue",
            (
                "the propylene carbonate Use category tops out at 107 of 141 rows on the card "
                "surface; the remaining 34 rows have no further paging control there and were not "
                "reached through another surface"
            ),
            (
                "Reaxys carries its own unit noise and it was preserved, not repaired: propylene "
                "carbonate 24.997 P and 0.253 P, butyric acid 58 P and acetic acid 0.0001176 P all "
                "look like centipoise recorded in the poise column"
            ),
            (
                "T_K is a deterministic conversion of the Celsius value Reaxys shows; ranges stay "
                "ranges, nothing was averaged and no value was imputed to 298.15 K"
            ),
            (
                'three of the four protic ionic liquids (HEL / TEL / TEAA) show "Retrieve CAS '
                'RN" instead '
                "of a CAS number, so the cas column is empty for those three by evidence, "
                "not by omission; the fourth, HEAL, does carry CAS 54300-24-2"
            ),
            (
                "only Electrochemical Characteristics was counted as redox; Electrochemical "
                "Behaviour (acid dissociation, polarography) was deliberately excluded"
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
    summary["facts_path"] = "probes/reaxys_thin_family_query_facts.csv"
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
