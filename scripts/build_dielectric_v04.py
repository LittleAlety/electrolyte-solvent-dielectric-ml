"""Build dielectric v0.4 from the frozen v0.3 roster plus the Week 17 roster patches.

Week 17 (W17-1) turns two long-standing loose ends into rows of a *new* version
table, leaving the frozen v0.3 file untouched:

* the **succinonitrile roster gap** -- the compound already carries 17 relative
  permittivity observations in the v1.x observation table (333.15 K to 373.15 K,
  ``10.1021/je300958c``) but has no row in the v0.3 roster;
* the **gamma-valerolactone value conflict** -- 36.9 (Segato, Baratta, Belanzoni,
  Belpassi, Del Zotto & Zuccaccia 2021, Inorganica Chimica Acta 522, 120372,
  supporting information) against the v0.3 review-table value 36.1 (iScience 2026
  Table 3).  The two legs are kept as two rows with provenance; nothing is
  averaged.

``data/dielectric_v04.csv`` therefore is: v0.3's 246 rows (every protected field
byte for byte; only two declared non-protected fields on the one contested row
are patched) followed by the two new addition rows.  v0.3's digest stays
``ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path
from scripts.build_dielectric_v03 import temperature_band as temperature_band_v03

V03_FROZEN_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"

# v0.3 refuses any temperature outside 293.15-303.15 K (room) or 313.15-323.15 K
# (extended).  succinonitrile's whole series sits above the extended window, so
# v0.4 declares one more band explicitly instead of silently widening v0.3's.
HIGH_TEMPERATURE_RANGE_K = (333.15, 373.15)
HIGHLY_TEMPERATURE_BAND = "high_temperature"

# Fields that a provenance patch may never touch: identity, target and the
# version stamp.  Mirrors scripts/build_dielectric_v03.py.
PROTECTED_PATCH_FIELDS = frozenset(
    {
        "inchikey",
        "name",
        "smiles",
        "dielectric",
        "T_K",
        "temperature_band",
        "model_ready",
        "dataset_origin",
    }
)

ADDITION_EXTRA_FIELDS = ("patch_kind", "rationale")
ADDITION_PATCH_KINDS = frozenset({"roster_gap_fill", "conflict_dual_row"})


def temperature_band_v04(temperature_k: float) -> str:
    """v0.3's bands plus one explicitly declared high-temperature band.

    v0.3's own helper is consulted first so the room and extended windows keep
    their exact v0.3 meaning; only a temperature it refuses can reach the new
    band, and that band is checked explicitly rather than by widening anything.
    """

    try:
        return temperature_band_v03(temperature_k)
    except ValueError:
        pass
    low, high = HIGH_TEMPERATURE_RANGE_K
    if low <= temperature_k <= high:
        return HIGHLY_TEMPERATURE_BAND
    raise ValueError(f"unsupported v0.4 temperature: {temperature_k} K")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def load_additions(
    path: Path, v03_fields: Sequence[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (rows, provenance_records) for the addition table."""

    header, raw_rows = read_rows(path)
    expected = [*v03_fields, *ADDITION_EXTRA_FIELDS]
    if header != expected:
        raise ValueError(
            "addition table header does not match the v0.3 field list plus "
            f"{ADDITION_EXTRA_FIELDS}: {header}"
        )
    rows: list[dict[str, str]] = []
    records: list[dict[str, str]] = []
    for raw in raw_rows:
        kind = raw["patch_kind"]
        if kind not in ADDITION_PATCH_KINDS:
            raise ValueError(f"unknown addition patch_kind: {kind}")
        row = {field: raw.get(field, "") for field in v03_fields}
        rows.append(row)
        records.append(
            {
                "patch_kind": kind,
                "inchikey": row["inchikey"],
                "name": row["name"],
                "dielectric": row["dielectric"],
                "rationale": raw["rationale"],
            }
        )
    return rows, records


def load_patches(path: Path) -> list[dict[str, str]]:
    header, raw_rows = read_rows(path)
    expected = ["inchikey", "field", "value", "rationale"]
    if header != expected:
        raise ValueError(f"patch table header mismatch: {header}")
    patches: list[dict[str, str]] = []
    for raw in raw_rows:
        field = raw["field"]
        if field in PROTECTED_PATCH_FIELDS:
            raise ValueError(f"patch touches a protected field: {field}")
        patches.append(
            {
                "inchikey": raw["inchikey"],
                "field": field,
                "value": raw["value"],
                "rationale": raw["rationale"],
            }
        )
    return patches


def apply_patches(
    rows: Sequence[Mapping[str, str]], patches: Sequence[Mapping[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Apply field-level patches to existing rows and report what was applied."""

    working = [dict(row) for row in rows]
    by_key: dict[str, dict[str, str]] = {}
    for row in working:
        by_key.setdefault(row.get("inchikey", ""), row)
    applied: list[dict[str, str]] = []
    for patch in patches:
        target = by_key.get(patch["inchikey"])
        if target is None:
            raise ValueError(f"patch targets an unknown row: {patch['inchikey']}")
        previous = target.get(patch["field"], "")
        target[patch["field"]] = patch["value"]
        applied.append(
            {
                "inchikey": patch["inchikey"],
                "name": target.get("name", ""),
                "field": patch["field"],
                "previous_value": previous,
                "value": patch["value"],
                "rationale": patch["rationale"],
            }
        )
    return working, applied


def build_v04_rows(
    v03_rows: Sequence[Mapping[str, str]],
    addition_rows: Sequence[Mapping[str, str]],
    patch_rows: Sequence[Mapping[str, str]],
    v03_fields: Sequence[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    patched, applied = apply_patches(v03_rows, patch_rows)
    rows: list[dict[str, str]] = [*patched]
    for addition in addition_rows:
        rows.append({field: addition.get(field, "") for field in v03_fields})
    return rows, applied


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


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v03", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--additions",
        type=Path,
        default=data_dir / "processed" / "dielectric_v04_roster_additions.csv",
    )
    parser.add_argument(
        "--patches",
        type=Path,
        default=data_dir / "processed" / "dielectric_v04_provenance_patches.csv",
    )
    parser.add_argument("--output", type=Path, default=data_dir / "dielectric_v04.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v04_summary.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    measured_v03 = canonical_text_sha256(args.v03)
    if measured_v03 != V03_FROZEN_SHA256:
        raise SystemExit(
            "frozen v0.3 digest moved: "
            f"{measured_v03} != {V03_FROZEN_SHA256} (refusing to build v0.4)"
        )
    v03_fields, v03_rows = read_rows(args.v03)
    addition_rows, addition_records = load_additions(args.additions, v03_fields)
    patch_rows = load_patches(args.patches)
    rows, applied = build_v04_rows(v03_rows, addition_rows, patch_rows, v03_fields)

    for addition in addition_rows:
        expected_band = temperature_band_v04(float(addition["T_K"]))
        if addition.get("temperature_band") != expected_band:
            raise SystemExit(
                "addition temperature band mismatch: "
                f"{addition.get('temperature_band')} != {expected_band}"
            )
        if addition.get("dataset_origin") != "v0.4_addition":
            raise SystemExit(
                f"addition is not stamped v0.4_addition: {addition.get('inchikey')}"
            )

    write_csv(args.output, v03_fields, rows)

    band_counts = Counter(row["temperature_band"] for row in rows)
    evidence_counts = Counter(row["evidence_level"] for row in rows)
    source_counts = Counter(row["dataset_origin"] for row in rows)
    summary = {
        "schema_version": 4,
        "dataset_version": "0.4",
        "week": "week17",
        "arm": "W17-1",
        "v03_row_count": len(v03_rows),
        "row_count": len(rows),
        "compound_count": len({row["inchikey"] for row in rows}),
        "addition_count": len(addition_rows),
        "additions": addition_records,
        "model_ready_addition_count": sum(
            1 for row in addition_rows if row.get("model_ready") == "true"
        ),
        "conflict_addition_count": sum(
            1 for row in addition_rows if row.get("conflict_status")
        ),
        "source_counts": dict(sorted(source_counts.items())),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "temperature_band_counts": dict(sorted(band_counts.items())),
        "temperature_ranges_K": {
            "room_temperature": [293.15, 303.15],
            "extended_temperature": [313.15, 323.15],
            HIGHLY_TEMPERATURE_BAND: list(HIGH_TEMPERATURE_RANGE_K),
        },
        "provenance_patches": {
            "path": portable_relative_path(args.patches, root=REPOSITORY_ROOT),
            "applied_count": len(applied),
            "applied": applied,
        },
        "inputs": {
            "dielectric_v03": {
                "path": portable_relative_path(args.v03, root=REPOSITORY_ROOT),
                "sha256": measured_v03,
                "frozen_digest_intact": True,
            },
            "roster_additions": {
                "path": portable_relative_path(args.additions, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(args.additions),
            },
            "provenance_patches": {
                "path": portable_relative_path(args.patches, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(args.patches),
            },
        },
        "output": {
            "path": portable_relative_path(args.output, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(args.output),
            "row_count": len(rows),
        },
        "status": "built",
    }
    write_json_lf(args.summary, summary)
    print(
        json.dumps(
            {
                "status": "built",
                "row_count": len(rows),
                "addition_count": len(addition_rows),
                "patch_count": len(applied),
                "output_sha256": summary["output"]["sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
