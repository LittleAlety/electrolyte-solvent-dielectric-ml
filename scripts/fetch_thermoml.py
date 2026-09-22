"""Fetch ThermoML XML files from the public NIST archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.thermoml import (
    THERMOML_USER_AGENT,
    DownloadError,
    destination_lock,
    download_url,
)

NIST_THERMOML_BASE_URL = "https://trc.nist.gov/ThermoML"
THERMOML_API_URL = "https://trc.nist.gov/ThermoML-API/objects"
DEFAULT_QUERY = "type:TRCTml4 AND dielectric"


def _positive_page_size(value: str) -> int:
    try:
        page_size = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--page-size must be a positive integer"
        ) from exc
    if page_size < 1:
        raise argparse.ArgumentTypeError("--page-size must be a positive integer")
    return page_size


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
        type=_positive_page_size,
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


def _safe_filename_component(value: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in value
    )
    return sanitized.strip("._-") or "thermoml"


def _destination_for_url(url: str) -> Path:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    segments = [
        urllib.parse.unquote(segment)
        for segment in path.split("/")
        if segment
    ]
    filename = segments[-1] if segments else "thermoml.xml"
    stem = filename.removesuffix(".xml") or "thermoml"
    doi_prefix = next(
        (
            segment
            for segment in segments[:-1]
            if segment.startswith("10.")
            and 4 <= len(segment.removeprefix("10.")) <= 9
            and segment.removeprefix("10.").isdigit()
        ),
        "",
    )
    readable_name = f"{doi_prefix}__{stem}" if doi_prefix else stem
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return Path(f"{_safe_filename_component(readable_name)}-{digest}.xml")


def _destinations_for_urls(urls: list[str]) -> list[Path]:
    """Return stable collision-safe destination names independent of the batch."""

    return [_destination_for_url(url) for url in urls]


def _legacy_destination_for_url(url: str) -> Path | None:
    filename = Path(urllib.parse.urlparse(url).path).name
    if not filename.endswith(".xml"):
        return None
    return Path(filename)


def _legacy_download_candidates(
    url: str,
    output_dir: Path,
    destination: Path,
) -> list[Path]:
    candidates: list[Path] = []
    for candidate in sorted(output_dir.glob("*.xml")):
        if candidate == destination:
            continue
        metadata_path = candidate.with_name(candidate.name + ".meta.json")
        if not candidate.is_file() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict) and metadata.get("url") == url:
            candidates.append(candidate)
    return candidates


def _move_download_pair(
    source_xml: Path,
    source_metadata: Path,
    destination_xml: Path,
    destination_metadata: Path,
) -> None:
    if destination_xml.exists() or destination_metadata.exists():
        raise DownloadError(
            f"refusing to overwrite migration target {destination_xml}"
        )
    metadata_moved = False
    xml_moved = False
    try:
        os.replace(source_metadata, destination_metadata)
        metadata_moved = True
        os.replace(source_xml, destination_xml)
        xml_moved = True
    except OSError as exc:
        rollback_errors: list[str] = []
        if xml_moved:
            try:
                os.replace(destination_xml, source_xml)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if metadata_moved:
            try:
                os.replace(destination_metadata, source_metadata)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        rollback_detail = (
            f"; rollback errors: {'; '.join(rollback_errors)}"
            if rollback_errors
            else "; rollback completed"
        )
        raise DownloadError(
            f"migration failed for {source_xml.name}: {exc}{rollback_detail}"
        ) from exc


def _quarantine_legacy_download(legacy_path: Path, output_dir: Path) -> Path:
    destination = output_dir / f"{legacy_path.name}.migrated"
    suffix = 1
    while destination.exists() or destination.with_name(
        destination.name + ".meta.json"
    ).exists():
        destination = output_dir / f"{legacy_path.name}.migrated.{suffix}"
        suffix += 1
    _move_download_pair(
        legacy_path,
        legacy_path.with_name(legacy_path.name + ".meta.json"),
        destination,
        destination.with_name(destination.name + ".meta.json"),
    )
    return destination


def _migrate_legacy_download_locked(
    url: str,
    output_dir: Path,
    destination: Path,
) -> Path:
    """Migrate or quarantine legacy candidates while the caller holds the lock."""

    candidates = _legacy_download_candidates(url, output_dir, destination)
    if not candidates:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_metadata = destination.with_name(destination.name + ".meta.json")
    candidate_hashes = [(candidate, hashlib.sha256(candidate.read_bytes()).hexdigest()) for candidate in candidates]

    if destination.exists():
        if not destination_metadata.is_file():
            raise DownloadError(
                f"stable destination {destination.name} has no metadata sidecar"
            )
        stable_metadata = json.loads(destination_metadata.read_text(encoding="utf-8"))
        if stable_metadata.get("url") != url:
            raise DownloadError(
                f"stable destination {destination.name} belongs to another URL"
            )
        stable_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        conflicting = [
            candidate.name
            for candidate, candidate_hash in candidate_hashes
            if candidate_hash != stable_hash
        ]
        if conflicting:
            raise DownloadError(
                "legacy candidates conflict with stable hashes: "
                + ", ".join(conflicting)
            )
        for candidate, _ in candidate_hashes:
            _quarantine_legacy_download(candidate, output_dir)
        return destination

    distinct_hashes = {candidate_hash for _, candidate_hash in candidate_hashes}
    if len(distinct_hashes) != 1:
        raise DownloadError(
            "legacy candidates for one URL have conflicting hashes: "
            + ", ".join(candidate.name for candidate, _ in candidate_hashes)
        )

    preferred = _legacy_destination_for_url(url)
    selected = next(
        (
            candidate
            for candidate, _ in candidate_hashes
            if preferred is not None and candidate.name == preferred.name
        ),
        candidate_hashes[0][0],
    )
    _move_download_pair(
        selected,
        selected.with_name(selected.name + ".meta.json"),
        destination,
        destination_metadata,
    )
    for candidate, _ in candidate_hashes:
        if candidate == selected:
            continue
        _quarantine_legacy_download(candidate, output_dir)
    return destination


def _migrate_legacy_download(
    url: str,
    output_dir: Path,
    destination: Path,
) -> Path:
    """Move URL-matched legacy files into one stable, non-duplicated name."""

    lock_path = destination.with_name(destination.name + ".lock")
    with destination_lock(lock_path, timeout=60):
        return _migrate_legacy_download_locked(url, output_dir, destination)


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
    destinations = _destinations_for_urls(urls)

    failures = 0
    for url, destination_name in zip(urls, destinations, strict=True):
        destination = args.output_dir / destination_name
        try:
            result = download_url(
                url,
                destination,
                resume=not args.no_resume,
                dry_run=args.dry_run,
                force=args.force,
                timeout=args.timeout,
                prepare_destination=(
                    None
                    if args.dry_run
                    else partial(
                        _migrate_legacy_download_locked,
                        url,
                        args.output_dir,
                    )
                ),
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
