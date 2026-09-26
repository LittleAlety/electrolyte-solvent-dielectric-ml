"""Week 17 / W17-2 -- thin-family backfill queue (attack the 0.276 scaffold ceiling).

The five thin families named by the Week 17 chapter are re-derived here from the
shipped observation table with the repository's own ``classify_family`` (the same
first-match-wins structural rule that built
``probes/artifacts/al_round4_local_coverage_gaps.csv``), so the arithmetic below
cannot drift away from that table.  For each family the script reports the current
lower-bound gap (>= 5 compounds AND >= 2 independent source DOIs) and a **manual
query queue** ordered by pre-registered rules.

Channel and compliance (inherited verbatim from the Week 12/16 discipline):

* the Reaxys stock queue ``probes/reaxys_v1x_stocking_queue.csv`` is the primary
  channel; rows are queried **one at a time by hand**, batch crawling is banned;
* restricted values are cross-check only -- they never enter ``data/``, never enter
  a pool, and the queue file itself carries only names, keys and coverage facts;
* ``data/restricted/springer_materials/interactive_pure_dielectric_catalog.json``
  contributes **name-level leads only** (it stores titles, not values); on a clean
  clone it is absent and the name index degrades to ``available = false``.

This arm executes **no Reaxys query and fits no model**: the deliverables are the
pre-registered queue and the coverage arithmetic.  ``reaxys_queries_executed`` is
reported as 0 rather than being implied.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path
from probes.al_round4_new_compound_backfill import classify_family

TARGET_FAMILIES = ("acid", "lactone", "carbonate", "sulfone", "protic_ionic_pair")
MIN_COMPOUNDS = 5
MIN_SOURCES = 2
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}

# Name-level keyword leads over the restricted SpringerMaterials title index.  They
# are candidates for a manual query, never values.
# include patterns, then exclude patterns.  The acid exclusion is what keeps the
# title index from offering esters ("...acid methyl ester") as carboxylic acids.
NAME_LEADS = {
    "sulfone": ((r"sulfon",), ()),
    "acid": (
        (r"\bacid\b",),
        (r"\bester\b", r"\bamide\b", r"amino", r"\bsalt\b", r"anhydride"),
    ),
    "lactone": ((r"lactone",), ()),
    "carbonate": ((r"carbonate",), ()),
    "protic_ionic_pair": ((r"onium", r"ammonium", r"imidazolium", r"pyrrolidinium"), ()),
}

UNSTABLE_KEYS = ("generated_at_utc",)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json_lf(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def family_coverage(observation_rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, object]]:
    """Per-family compound / row / distinct-source counts from the observation table."""

    compounds: dict[str, set[str]] = defaultdict(set)
    rows = Counter()
    sources: dict[str, set[str]] = defaultdict(set)
    for row in observation_rows:
        family = classify_family(row.get("smiles", ""))
        rows[family] += 1
        key = row.get("inchikey", "")
        if key:
            compounds[family].add(key)
        doi = (row.get("source_doi") or "").strip()
        if doi:
            sources[family].add(doi)
    coverage: dict[str, dict[str, object]] = {}
    for family in sorted(set(rows) | set(TARGET_FAMILIES)):
        coverage[family] = {
            "compounds": len(compounds.get(family, ())),
            "rows": rows.get(family, 0),
            "distinct_sources": len(sources.get(family, ())),
        }
    return coverage


def gap_for(coverage: Mapping[str, object]) -> tuple[int, int]:
    compounds = int(coverage.get("compounds", 0))
    sources = int(coverage.get("distinct_sources", 0))
    return max(0, MIN_COMPOUNDS - compounds), max(0, MIN_SOURCES - sources)


def stock_queue_candidates(
    stock_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    by_family: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in stock_rows:
        family = classify_family(row.get("smiles", ""))
        if family not in TARGET_FAMILIES:
            continue
        by_family[family].append(
            {
                "candidate_name": row.get("name", ""),
                "candidate_inchikey": row.get("inchikey", ""),
                "candidate_source": "reaxys_stocking_queue",
                "candidate_family_confidence": "structural_smarts",
                "local_rows": row.get("local_rows", ""),
                "stocking_priority": row.get("stocking_priority", ""),
                "evidence_needed": "manual single-compound Reaxys property query",
            }
        )
    return by_family


def name_leads(catalog_path: Path) -> tuple[bool, dict[str, list[dict[str, str]]]]:
    if not catalog_path.is_file():
        return False, {}
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    titles = [str(record.get("title", "")) for record in payload.get("records", [])]
    leads: dict[str, list[dict[str, str]]] = defaultdict(list)
    for family, (include, exclude) in NAME_LEADS.items():
        for title in titles:
            if not any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in include):
                continue
            if any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in exclude):
                continue
            name = title
            if name.lower().startswith("dielectric constant for "):
                name = name[len("dielectric constant for ") :]
            name = name.removesuffix(" (pure)")
            leads[family].append(
                {
                    "candidate_name": name,
                    "candidate_inchikey": "",
                    "candidate_source": "springer_materials_title_index",
                    "candidate_family_confidence": "name_keyword_only",
                    "local_rows": "",
                    "stocking_priority": "",
                    "evidence_needed": "manual single-compound query; restricted value stays a crosscheck",
                }
            )
    return True, leads


def sort_key(row: Mapping[str, str]) -> tuple:
    return (
        PRIORITY_ORDER.get(str(row.get("stocking_priority", "")), 9),
        0 if row.get("candidate_inchikey") else 1,
        str(row.get("candidate_name", "")),
    )


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observations",
        type=Path,
        default=data_dir / "processed" / "dielectric_observations_v11plus.csv",
    )
    parser.add_argument(
        "--stock-queue",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_queue.csv",
    )
    parser.add_argument(
        "--restricted-catalog",
        type=Path,
        default=data_dir
        / "restricted"
        / "springer_materials"
        / "interactive_pure_dielectric_catalog.json",
    )
    parser.add_argument(
        "--queue-out",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_queue.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "reaxys_thin_family_backfill_summary.json",
    )
    parser.add_argument(
        "--prereg",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "reaxys_thin_family_backfill_prereg.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    observation_rows = read_rows(args.observations)
    stock_rows = read_rows(args.stock_queue)
    coverage = family_coverage(observation_rows)
    stock_by_family = stock_queue_candidates(stock_rows)
    catalog_available, leads_by_family = name_leads(args.restricted_catalog)

    queue_rows: list[dict[str, str]] = []
    family_report: dict[str, dict[str, object]] = {}
    for family in TARGET_FAMILIES:
        current = coverage.get(family, {"compounds": 0, "rows": 0, "distinct_sources": 0})
        compounds_needed, sources_needed = gap_for(current)
        candidates = [
            *stock_by_family.get(family, []),
            *leads_by_family.get(family, []),
        ]
        candidates.sort(key=sort_key)
        for rank, candidate in enumerate(candidates, start=1):
            queue_rows.append(
                {
                    "family": family,
                    "current_compounds": str(current["compounds"]),
                    "current_rows": str(current["rows"]),
                    "current_distinct_sources": str(current["distinct_sources"]),
                    "compounds_needed": str(compounds_needed),
                    "sources_needed": str(sources_needed),
                    "candidate_rank": str(rank),
                    **candidate,
                    "action": "manual_reaxys_query"
                    if candidate["candidate_source"] == "reaxys_stocking_queue"
                    else "manual_lead_triage",
                    "access": "restricted_crosscheck_only",
                }
            )
        family_report[family] = {
            "current": current,
            "compounds_needed": compounds_needed,
            "sources_needed": sources_needed,
            "queue_candidates": len(candidates),
            "queue_candidates_from_stock_queue": len(stock_by_family.get(family, [])),
            "queue_candidates_from_title_index": len(leads_by_family.get(family, [])),
            "meets_lower_bound": compounds_needed == 0 and sources_needed == 0,
        }

    fields = [
        "family",
        "current_compounds",
        "current_rows",
        "current_distinct_sources",
        "compounds_needed",
        "sources_needed",
        "candidate_rank",
        "candidate_name",
        "candidate_inchikey",
        "candidate_source",
        "candidate_family_confidence",
        "local_rows",
        "stocking_priority",
        "evidence_needed",
        "action",
        "access",
    ]
    write_csv(args.queue_out, fields, queue_rows)

    summary = {
        "schema_version": 1,
        "task": "reaxys_thin_family_backfill",
        "week": "week17",
        "arm": "W17-2",
        "prereg": {
            "path": portable_relative_path(args.prereg, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(args.prereg),
            "status": "locked_before_run",
        },
        "target_families": list(TARGET_FAMILIES),
        "lower_bound": {"min_compounds": MIN_COMPOUNDS, "min_distinct_sources": MIN_SOURCES},
        "family_report": family_report,
        "family_coverage_full": coverage,
        "queue_rows": len(queue_rows),
        "queue_by_source": dict(
            sorted(Counter(row["candidate_source"] for row in queue_rows).items())
        ),
        "restricted_title_index_available": catalog_available,
        "reaxys_queries_executed": 0,
        "restricted_contract": {
            "values_enter_data": False,
            "values_enter_any_pool": False,
            "queue_carries": "names, InChIKeys and coverage facts only",
            "access_labels": ["restricted_crosscheck_only"],
            "disclosure_rule": "queue file is excluded from outward-facing bundles (decision 28.2)",
        },
        "inputs": {
            "observations": {
                "path": portable_relative_path(args.observations, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(args.observations),
            },
            "stock_queue": {
                "path": portable_relative_path(args.stock_queue, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(args.stock_queue),
            },
        },
        "outputs": {
            "queue": {
                "path": portable_relative_path(args.queue_out, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(args.queue_out),
                "row_count": len(queue_rows),
            }
        },
        "run_telemetry": {
            "network_calls": 0,
            "models_fitted": 0,
            "r2_reported": False,
            "writes_under_data": 0,
            "run_mode": "offline_local_only",
        },
        "honesty_boundaries": [
            "The queue is a plan, not a measurement: no Reaxys query was executed by this arm.",
            "Candidate family labels are structural (the repository's classify_family) for stock-queue rows and name-keyword-only for title-index leads.",
            "Row counts are not comparable between the observation table and the online ThermoML slices; only the local table is used here.",
        ],
    }
    write_json_lf(args.summary, summary)
    print(
        json.dumps(
            {
                "status": "built",
                "queue_rows": len(queue_rows),
                "families": {
                    family: {
                        "compounds": family_report[family]["current"]["compounds"],
                        "rows": family_report[family]["current"]["rows"],
                        "sources": family_report[family]["current"]["distinct_sources"],
                        "need": [
                            family_report[family]["compounds_needed"],
                            family_report[family]["sources_needed"],
                        ],
                        "candidates": family_report[family]["queue_candidates"],
                    }
                    for family in TARGET_FAMILIES
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
