"""Build dielectric v0.3 from v0.2 plus audited public observations."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PUBLIC_REDISTRIBUTION_STATUSES = {"allowed", "public_domain"}
ROOM_TEMPERATURE_RANGE_K = (293.15, 303.15)
EXTENDED_TEMPERATURE_RANGE_K = (313.15, 323.15)
ADDITION_REQUIRED_FIELDS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "source_doi",
    "source_url",
    "source_citation",
    "source_table",
    "source_quality",
    "redistribution_status",
)
V03_FIELDS = (
    "dataset_origin",
    "temperature_band",
    "source_url",
    "source_citation",
    "source_table",
    "redistribution_status",
    "notes",
)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


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


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def temperature_band(temperature_k: float) -> str:
    room_min, room_max = ROOM_TEMPERATURE_RANGE_K
    if room_min <= temperature_k <= room_max:
        return "room_temperature"
    extended_min, extended_max = EXTENDED_TEMPERATURE_RANGE_K
    if extended_min <= temperature_k <= extended_max:
        return "extended_temperature"
    raise ValueError(f"unsupported v0.3 temperature: {temperature_k} K")


def _normalized_addition(row: Mapping[str, str]) -> dict[str, str]:
    missing = [field for field in ADDITION_REQUIRED_FIELDS if not row.get(field)]
    if missing:
        raise ValueError(f"addition is missing required fields: {', '.join(missing)}")
    redistribution_status = row["redistribution_status"]
    if redistribution_status not in PUBLIC_REDISTRIBUTION_STATUSES:
        raise ValueError(
            f"restricted observation cannot enter public v0.3: {row['name']}"
        )
    temperature_k = float(row["T_K"])
    dielectric = float(row["dielectric"])
    if temperature_k <= 0 or dielectric < 1:
        raise ValueError(f"nonphysical addition: {row['name']}")
    output = dict(row)
    output["dataset_origin"] = "v0.3_addition"
    output["temperature_band"] = temperature_band(temperature_k)
    return output


def build_v03_rows(
    v02_rows: Sequence[Mapping[str, str]],
    additions: Sequence[Mapping[str, str]],
    *,
    minimum_additions: int,
) -> list[dict[str, str]]:
    if len(additions) < minimum_additions:
        raise ValueError(
            f"v0.3 needs at least {minimum_additions} additions; found {len(additions)}"
        )

    rows = [
        {
            **row,
            "dataset_origin": "v0.2",
            "temperature_band": temperature_band(float(row["T_K"])),
        }
        for row in v02_rows
    ]
    keys = [row["inchikey"] for row in rows]
    for addition in additions:
        normalized = _normalized_addition(addition)
        if normalized["inchikey"] in keys:
            raise ValueError(f"duplicate InChIKey in v0.3: {normalized['inchikey']}")
        keys.append(normalized["inchikey"])
        rows.append(normalized)
    return rows


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02", type=Path, default=data_dir / "dielectric_v02.csv")
    parser.add_argument(
        "--additions",
        type=Path,
        default=data_dir
        / "processed"
        / "modern_solvent_public_observations.csv",
    )
    parser.add_argument("--output", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v03_summary.json",
    )
    parser.add_argument("--minimum-additions", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    v02_fields, v02_rows = read_csv_rows(args.v02)
    _, addition_rows = read_csv_rows(args.additions)
    rows = build_v03_rows(
        v02_rows,
        addition_rows,
        minimum_additions=args.minimum_additions,
    )
    fields = list(v02_fields)
    fields.extend(field for field in V03_FIELDS if field not in fields)
    write_csv_rows(args.output, fields, rows)

    source_counts = Counter(row["dataset_origin"] for row in rows)
    band_counts = Counter(row["temperature_band"] for row in rows)
    summary = {
        "schema_version": 3,
        "dataset_version": "0.3",
        "compound_count": len(rows),
        "v02_compound_count": len(v02_rows),
        "addition_count": len(addition_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "temperature_band_counts": dict(sorted(band_counts.items())),
        "temperature_ranges_K": {
            "room_temperature": list(ROOM_TEMPERATURE_RANGE_K),
            "extended_temperature": list(EXTENDED_TEMPERATURE_RANGE_K),
        },
        "inputs": {
            "v02_sha256": canonical_text_sha256(args.v02),
            "additions_sha256": canonical_text_sha256(args.additions),
        },
        "output": {
            "path": portable_relative_path(args.output, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(args.output),
        },
        "status": "built; independent verification required",
    }
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
