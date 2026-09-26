"""Independently verify the public dielectric v0.4 roster."""

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
from scripts.build_dielectric_v04 import (
    ADDITION_EXTRA_FIELDS,
    PROTECTED_PATCH_FIELDS,
    V03_FROZEN_SHA256,
    build_v04_rows,
    load_additions,
    load_patches,
    temperature_band_v04,
)

PUBLIC_REDISTRIBUTION_STATUSES = frozenset({"allowed", "public_domain"})


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def verify_v04(
    *,
    v03_fields: Sequence[str],
    v03_rows: Sequence[Mapping[str, str]],
    output_rows: Sequence[Mapping[str, str]],
    addition_rows: Sequence[Mapping[str, str]],
    patches: Sequence[Mapping[str, str]],
) -> list[str]:
    """Return the list of policy violations (empty when the table is sound)."""

    errors: list[str] = []
    if len(output_rows) != len(v03_rows) + len(addition_rows):
        errors.append(
            "row count mismatch: "
            f"{len(output_rows)} != {len(v03_rows)} + {len(addition_rows)}"
        )
    patched_fields = {(patch["inchikey"], patch["field"]) for patch in patches}
    for index, (legacy, shipped) in enumerate(
        zip(v03_rows, output_rows, strict=False), start=1
    ):
        for field in v03_fields:
            before = legacy.get(field, "")
            after = shipped.get(field, "")
            if before == after:
                continue
            if field in PROTECTED_PATCH_FIELDS:
                errors.append(
                    f"row {index} altered a protected field: {field}"
                )
            elif (legacy.get("inchikey", ""), field) not in patched_fields:
                errors.append(
                    f"row {index} changed {field} without a declared patch"
                )
    for addition in addition_rows:
        missing = [
            field
            for field in ("inchikey", "smiles", "name", "T_K", "dielectric")
            if not addition.get(field)
        ]
        if missing:
            errors.append(f"addition missing fields: {', '.join(missing)}")
        status = str(addition.get("redistribution_status", ""))
        if status not in PUBLIC_REDISTRIBUTION_STATUSES:
            errors.append(
                f"restricted addition {addition.get('inchikey')}: {status or 'missing'}"
            )
        if addition.get("dataset_origin") != "v0.4_addition":
            errors.append(
                f"addition not stamped v0.4_addition: {addition.get('inchikey')}"
            )
        try:
            expected_band = temperature_band_v04(float(addition["T_K"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"addition has an invalid T_K: {exc}")
            continue
        if addition.get("temperature_band") != expected_band:
            errors.append(
                "addition temperature band mismatch: "
                f"{addition.get('temperature_band')} != {expected_band}"
            )
    keys = [row.get("inchikey", "") for row in output_rows]
    duplicated = sorted(key for key, count in Counter(keys).items() if key and count > 1)
    if duplicated != ["GAEKPEKOJKCEMS-UHFFFAOYSA-N"]:
        errors.append(f"unexpected duplicate InChIKeys: {duplicated}")
    return errors


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v03", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument("--v04", type=Path, default=data_dir / "dielectric_v04.csv")
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
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v04_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    errors: list[str] = []

    measured_v03 = canonical_text_sha256(args.v03)
    if measured_v03 != V03_FROZEN_SHA256:
        errors.append(
            f"frozen v0.3 digest moved: {measured_v03} != {V03_FROZEN_SHA256}"
        )

    v03_fields, v03_rows = read_rows(args.v03)
    output_fields, output_rows = read_rows(args.v04)
    addition_rows, _ = load_additions(args.additions, v03_fields)
    patches = load_patches(args.patches)

    if output_fields != v03_fields:
        errors.append("v0.4 header does not match the v0.3 field list")

    errors.extend(
        verify_v04(
            v03_fields=v03_fields,
            v03_rows=v03_rows,
            output_rows=output_rows,
            addition_rows=addition_rows,
            patches=patches,
        )
    )

    expected_rows, applied = build_v04_rows(v03_rows, addition_rows, patches, v03_fields)
    for index, (actual, expected) in enumerate(
        zip(output_rows, expected_rows, strict=False), start=1
    ):
        if any(actual.get(field, "") != expected.get(field, "") for field in v03_fields):
            errors.append(f"row {index} does not reproduce from pinned inputs")
            break

    if b"\r\n" in args.v04.read_bytes():
        errors.append("v0.4 is not LF-only in the worktree")

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    recorded_output = summary.get("output", {}).get("sha256")
    if recorded_output != canonical_text_sha256(args.v04):
        errors.append("summary output hash does not match the shipped table")
    if summary.get("provenance_patches", {}).get("applied_count") != len(applied):
        errors.append("summary provenance patch count mismatch")
    if summary.get("addition_count") != len(addition_rows):
        errors.append("summary addition count mismatch")
    if summary.get("inputs", {}).get("dielectric_v03", {}).get("sha256") != measured_v03:
        errors.append("summary v0.3 input digest mismatch")

    report = {
        "passed": not errors,
        "check_count": 8,
        "passed_count": 8 if not errors else 0,
        "errors": errors,
        "v03_row_count": len(v03_rows),
        "v04_row_count": len(output_rows),
        "addition_count": len(addition_rows),
        "patch_count": len(applied),
        "duplicate_keys": ["GAEKPEKOJKCEMS-UHFFFAOYSA-N"],
        "v04": portable_relative_path(args.v04, root=REPOSITORY_ROOT),
        "v04_sha256": canonical_text_sha256(args.v04),
        "v03_sha256": measured_v03,
        "addition_extra_fields": list(ADDITION_EXTRA_FIELDS),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
