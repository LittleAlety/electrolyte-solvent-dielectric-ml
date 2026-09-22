"""Fetch ThermoML XML files from the public NIST archive."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.thermoml import (
    THERMOML_USER_AGENT,
    DownloadError,
    download_url,
)

NIST_THERMOML_BASE_URL = "https://trc.nist.gov/ThermoML"
THERMOML_API_URL = "https://trc.nist.gov/ThermoML-API/objects"
DEFAULT_QUERY = "type:TRCTml4 AND dielectric"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover and download ThermoML XML files from NIST."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/thermoml"),
        help="Directory for unchanged XML files and .meta.json sidecars.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="NIST Lucene query used when no DOI/URL is given.",
    )
    parser.add_argument(
        "--doi",
        action="append",
        default=[],
        help="DOI to download; can be supplied more than once.",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Exact ThermoML XML URL to download; can be supplied more than once.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum API results to download.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="NIST API page size while discovering results.",
    )
    parser.add_argument(
        "--api-url",
        default=THERMOML_API_URL,
        help="ThermoML metadata API endpoint.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve candidates and print actions without writing files.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Discard any .part file instead of resuming it.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing raw file and sidecar.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="Network timeout in seconds.",
    )
    return parser.parse_args()


def _fetch_api_ids(
    query: str,
    *,
    api_url: str,
    limit: int,
    page_size: int,
    timeout: float,
) -> list[str]:
    ids: list[str] = []
    page_number = 0
    while len(ids) < limit:
        request_size = min(page_size, limit - len(ids))
        parameters = urllib.parse.urlencode(
            {
                "query": query,
                "pageNum": page_number,
                "pageSize": request_size,
                "ids": "",
            }
        )
        request = urllib.request.Request(
            f"{api_url}?{parameters}",
            headers={
                "Accept": "application/json",
                "User-Agent": THERMOML_USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise DownloadError(f"ThermoML API query failed: {exc}") from exc

        page_ids = payload.get("results", [])
        if not isinstance(page_ids, list):
            raise DownloadError("ThermoML API response has no results list")
        ids.extend(str(identifier) for identifier in page_ids)
        if len(page_ids) < request_size:
            break
        page_number += 1
    return ids[:limit]


def _doi_from_api_id(identifier: str) -> str:
    marker = ".thermoml/"
    if marker not in identifier:
        raise DownloadError(f"unexpected ThermoML API id: {identifier!r}")
    return identifier.split(marker, 1)[1]


def _url_from_doi(doi: str) -> str:
    encoded_doi = urllib.parse.quote(doi, safe="/")
    return f"{NIST_THERMOML_BASE_URL}/{encoded_doi}.xml"


def _destination_for_url(url: str, index: int) -> Path:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    filename = Path(path).name
    if not filename.endswith(".xml"):
        filename = f"thermoml-{index:04d}.xml"
    return Path(filename)


def main() -> int:
    args = _parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    urls = list(args.url)
    urls.extend(_url_from_doi(doi) for doi in args.doi)
    if not urls:
        identifiers = _fetch_api_ids(
            args.query,
            api_url=args.api_url,
            limit=args.limit,
            page_size=args.page_size,
            timeout=args.timeout,
        )
        urls.extend(_url_from_doi(_doi_from_api_id(identifier)) for identifier in identifiers)
    urls = urls[: args.limit]

    failures = 0
    for index, url in enumerate(urls):
        destination = args.output_dir / _destination_for_url(url, index)
        try:
            result = download_url(
                url,
                destination,
                resume=not args.no_resume,
                dry_run=args.dry_run,
                force=args.force,
                timeout=args.timeout,
            )
        except DownloadError as exc:
            failures += 1
            print(f"ERROR {url}: {exc}", file=sys.stderr)
            continue
        print(f"{result.status:9s} {result.url} -> {result.destination}")

    if not urls:
        print("No ThermoML files matched the request.", file=sys.stderr)
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
