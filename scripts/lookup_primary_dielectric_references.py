"""Find public DOI metadata for primary references in the modern-solvent queue."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path

USER_AGENT = "electrolyte-ml-reference-lookup/1.0"
OUTPUT_FIELDS = (
    "primary_reference",
    "author_query",
    "year",
    "status",
    "doi",
    "title",
    "container_title",
    "matched_query",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_reference(reference: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"\s*(.+?)\s*\((\d{4})\)\s*", reference)
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def lookup_reference(
    reference: str,
    *,
    session: requests.Session,
) -> dict[str, object]:
    parsed = parse_reference(reference)
    if parsed is None:
        return {
            "primary_reference": reference,
            "author_query": "",
            "year": "",
            "status": "unparsed",
            "doi": "",
            "title": "",
            "container_title": "",
            "matched_query": "",
        }
    author, year = parsed
    response = session.get(
        "https://api.crossref.org/works",
        params={
            "query.author": author,
            "query.bibliographic": "dielectric constant relative permittivity",
            "filter": (
                f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
            ),
            "rows": 5,
        },
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("message", {}).get("items", [])
    if not items:
        return {
            "primary_reference": reference,
            "author_query": author,
            "year": year,
            "status": "not_found",
            "doi": "",
            "title": "",
            "container_title": "",
            "matched_query": "",
        }
    item = items[0]
    return {
        "primary_reference": reference,
        "author_query": author,
        "year": year,
        "status": "candidate_requires_manual_verification",
        "doi": item.get("DOI", ""),
        "title": " ".join(item.get("title", [])),
        "container_title": " ".join(item.get("container-title", [])),
        "matched_query": "dielectric constant relative permittivity",
    }


def run(
    *,
    queue_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    references = sorted(
        {
            row["primary_reference"]
            for row in read_csv_rows(queue_path)
            if row.get("primary_reference")
        }
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    rows = [lookup_reference(reference, session=session) for reference in references]
    write_csv_rows(output_path, OUTPUT_FIELDS, rows)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "reference_count": len(rows),
        "candidate_doi_count": sum(bool(row["doi"]) for row in rows),
        "output": portable_relative_path(output_path, root=REPOSITORY_ROOT),
        "policy": "Crossref matches are candidates and require manual verification.",
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "modern_battery_solvent_candidate_queue.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "modern_battery_solvent_primary_references.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "modern_battery_solvent_reference_lookup_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run(
        queue_path=args.queue,
        output_path=args.output,
        summary_path=args.summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
