"""Build a metadata-only queue from the Landolt-Boernstein 2015 book."""

from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

BOOK_DOI = "10.1007/978-3-662-48168-4"
BOOK_TITLE = "Static Dielectric Constants of Pure Liquids and Binary Liquid Mixtures"
CROSSREF_URL = "https://api.crossref.org/works"
USER_AGENT = "electrolyte-ml/0.0.0 (+https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml)"


def _title(item: Mapping[str, Any]) -> str:
    values = item.get("title", [])
    return " ".join(str(value) for value in values).strip()


def _container_title(item: Mapping[str, Any]) -> str:
    values = item.get("container-title", [])
    return " ".join(str(value) for value in values).strip()


def is_pure_substance_chapter(item: Mapping[str, Any]) -> bool:
    """Return whether Crossref metadata denotes a pure-substance chapter."""

    title = _title(item)
    return (
        _container_title(item) == BOOK_TITLE
        and title.startswith("Static dielectric constant of ")
        and "binary liquid mixture" not in title.casefold()
    )


def candidate_name(title: str) -> str:
    prefix = "Static dielectric constant of "
    return title.removeprefix(prefix).strip()


def fetch_crossref_items(*, timeout: float) -> list[dict[str, Any]]:
    parameters = urllib.parse.urlencode(
        {
            "query.container-title": BOOK_TITLE,
            "filter": (
                "type:book-chapter,"
                "from-pub-date:2015-01-01,until-pub-date:2015-12-31"
            ),
            "rows": "1000",
            "select": "DOI,title,container-title,published",
        }
    )
    request = urllib.request.Request(
        f"{CROSSREF_URL}?{parameters}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    items = payload.get("message", {}).get("items", [])
    if not isinstance(items, list):
        raise TypeError("Crossref response has no message.items list")
    return [item for item in items if isinstance(item, dict)]


def build_queue(items: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        if not is_pure_substance_chapter(item):
            continue
        title = _title(item)
        rows.append(
            {
                "queue_id": "",
                "candidate_name": candidate_name(title),
                "book_doi": BOOK_DOI,
                "chapter_doi": str(item.get("DOI", "")),
                "chapter_title": title,
                "source_title": BOOK_TITLE,
                "source_access": "closed_subscription",
                "manual_value_status": "not_reviewed",
                "required_fields_missing": (
                    "smiles;inchikey;T_K;phase;frequency_MHz;dielectric;"
                    "uncertainty;source_page_or_table;redistribution_status"
                ),
                "decision_status": "awaiting_manual_review",
            }
        )
    rows.sort(key=lambda row: row["chapter_doi"])
    for index, row in enumerate(rows, start=1):
        row["queue_id"] = f"lb2015:{index:04d}"
    return rows


def write_queue(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "queue_id",
        "candidate_name",
        "book_doi",
        "chapter_doi",
        "chapter_title",
        "source_title",
        "source_access",
        "manual_value_status",
        "required_fields_missing",
        "decision_status",
    )
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "data"
            / "processed"
            / "landolt_boernstein_2015_pure_liquid_queue.csv"
        ),
    )
    parser.add_argument("--timeout", type=float, default=30)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = build_queue(fetch_crossref_items(timeout=args.timeout))
    if not rows:
        raise SystemExit("Crossref returned no matching pure-substance chapters")
    write_queue(rows, args.output)
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
