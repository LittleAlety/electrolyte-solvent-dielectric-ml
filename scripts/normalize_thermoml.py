"""Normalize downloaded ThermoML XML files into CSV plus provenance JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.thermoml import (
    DownloadError,
    ThermoMLError,
    build_provenance,
    parse_thermoml_file,
    read_download_metadata,
    sha256_file,
    write_normalized_csv,
    write_provenance,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse raw ThermoML XML without converting units or removing duplicates."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw/thermoml"),
        help="Directory containing raw .xml files and optional .meta.json sidecars.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("data/processed/thermoml_normalized.csv"),
        help="Destination CSV path.",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("data/processed/thermoml_normalized.provenance.json"),
        help="Destination provenance JSON path.",
    )
    parser.add_argument(
        "--dielectric-only",
        action="store_true",
        help="Explicitly filter to dielectric-related rows; defaults to keeping all rows.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    xml_paths = sorted(
        path
        for path in args.raw_dir.rglob("*.xml")
        if path.is_file() and not path.name.endswith(".part")
    )
    rows: list[dict[str, str]] = []
    sources: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for xml_path in xml_paths:
        metadata_path = xml_path.with_name(xml_path.name + ".meta.json")
        metadata: dict[str, object] = {}
        if metadata_path.exists():
            try:
                metadata = read_download_metadata(metadata_path)
            except (DownloadError, OSError) as exc:
                errors.append({"file": xml_path.name, "error": str(exc)})

        digest = str(metadata.get("sha256") or sha256_file(xml_path))
        source_url = str(metadata.get("url", ""))
        retrieved_at = str(metadata.get("retrieved_at", ""))
        try:
            file_rows = parse_thermoml_file(
                xml_path,
                source_url=source_url,
                source_sha256=digest,
                retrieved_at=retrieved_at,
            )
        except (ThermoMLError, OSError) as exc:
            errors.append({"file": xml_path.name, "error": str(exc)})
            continue

        selected_rows = (
            [row for row in file_rows if row["is_dielectric"] == "true"]
            if args.dielectric_only
            else file_rows
        )
        rows.extend(selected_rows)
        sources.append(
            {
                "file": xml_path.name,
                "url": source_url,
                "retrieved_at": retrieved_at,
                "sha256": digest,
                "metadata_found": metadata_path.exists(),
                "row_count": len(selected_rows),
                "source_row_count": len(file_rows),
            }
        )

    provenance = build_provenance(rows, sources)
    provenance.update(
        {
            "filter": "dielectric_only" if args.dielectric_only else "none",
            "raw_file_count": len(xml_paths),
            "errors": errors,
            "deduplication": "none",
            "unit_conversion": "none",
        }
    )
    write_normalized_csv(rows, args.csv)
    write_provenance(args.provenance, provenance)

    print(
        f"Wrote {len(rows)} row(s) from {len(sources)} file(s) to {args.csv}; "
        f"provenance: {args.provenance}"
    )
    for error in errors:
        print(f"ERROR {error['file']}: {error['error']}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
