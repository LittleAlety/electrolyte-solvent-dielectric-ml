"""Independently verify the public dielectric v0.3 table."""

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
from scripts.build_dielectric_v03 import (
    ADDITION_REQUIRED_FIELDS,
    PUBLIC_REDISTRIBUTION_STATUSES,
    apply_provenance_patches,
    build_v03_rows,
    temperature_band,
    v03_license_errors,
)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def verify_v03_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    minimum_additions: int,
    excluded_model_keys: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    excluded_model_keys = excluded_model_keys or set()
    additions = [
        row for row in rows if row.get("dataset_origin") == "v0.3_addition"
    ]
    if len(additions) < minimum_additions:
        errors.append(
            f"fewer than {minimum_additions} v0.3 additions: {len(additions)}"
        )

    keys = [str(row.get("inchikey", "")) for row in rows]
    duplicates = sorted(
        key for key, count in Counter(keys).items() if key and count > 1
    )
    if duplicates:
        errors.append(f"duplicate InChIKeys: {', '.join(duplicates)}")

    for index, row in enumerate(additions, start=1):
        missing = [
            field for field in ADDITION_REQUIRED_FIELDS if not row.get(field)
        ]
        if missing:
            errors.append(
                f"addition {index} missing fields: {', '.join(missing)}"
            )
        status = str(row.get("redistribution_status", ""))
        if status not in PUBLIC_REDISTRIBUTION_STATUSES:
            errors.append(f"restricted addition {index}: {status or 'missing status'}")
        try:
            expected_band = temperature_band(float(row["T_K"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"addition {index} has invalid T_K: {exc}")
        else:
            if row.get("temperature_band") != expected_band:
                errors.append(
                    f"addition {index} temperature band mismatch: "
                    f"{row.get('temperature_band')} != {expected_band}"
                )
    for row in rows:
        if (
            row.get("inchikey") in excluded_model_keys
            and row.get("model_ready") != "false"
        ):
            errors.append(
                f"excluded model row is marked ready: {row.get('inchikey')}"
            )
    errors.extend(v03_license_errors(rows))
    return errors


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
    parser.add_argument(
        "--review-additions",
        type=Path,
        default=data_dir
        / "processed"
        / "modern_solvent_public_review_observations.csv",
    )
    parser.add_argument(
        "--model-exclusions",
        type=Path,
        default=data_dir / "processed" / "dielectric_v03_exclusions.csv",
    )
    parser.add_argument(
        "--provenance-patches",
        type=Path,
        default=data_dir / "processed" / "dielectric_v03_provenance_patches.csv",
    )
    parser.add_argument("--output", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v03_summary.json",
    )
    parser.add_argument("--minimum-additions", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _, v02_rows = read_csv_rows(args.v02)
    _, addition_rows = read_csv_rows(args.additions)
    _, review_addition_rows = read_csv_rows(args.review_additions)
    all_addition_rows = [*addition_rows, *review_addition_rows]
    _, exclusion_rows = read_csv_rows(args.model_exclusions)
    excluded_model_keys = {row["inchikey"] for row in exclusion_rows}
    _, patch_rows = read_csv_rows(args.provenance_patches)
    _, output_rows = read_csv_rows(args.output)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    expected_rows = build_v03_rows(
        v02_rows,
        all_addition_rows,
        minimum_additions=args.minimum_additions,
        excluded_model_keys=excluded_model_keys,
    )
    expected_rows, applied_patches = apply_provenance_patches(
        expected_rows, patch_rows
    )

    errors = verify_v03_rows(
        output_rows,
        minimum_additions=args.minimum_additions,
        excluded_model_keys=excluded_model_keys,
    )
    fields = set(expected_rows[0]) | set(output_rows[0])
    for field in sorted(fields):
        if field not in output_rows[0]:
            errors.append(f"output is missing field: {field}")
    if len(output_rows) != len(expected_rows):
        errors.append(
            f"row count mismatch: {len(output_rows)} != {len(expected_rows)}"
        )
    else:
        for index, (actual, expected) in enumerate(
            zip(output_rows, expected_rows, strict=True),
            start=1,
        ):
            if any(
                actual.get(field, "") != expected.get(field, "")
                for field in fields
            ):
                errors.append(f"row {index} does not reproduce from pinned inputs")
                break

    expected_output_hash = canonical_text_sha256(args.output)
    recorded_output_hash = summary.get("output", {}).get("sha256")
    if recorded_output_hash != expected_output_hash:
        errors.append(
            "summary output hash mismatch: "
            f"{recorded_output_hash} != {expected_output_hash}"
        )
    expected_additions_hash = canonical_text_sha256(args.additions)
    recorded_additions_hash = summary.get("inputs", {}).get("additions_sha256")
    if recorded_additions_hash != expected_additions_hash:
        errors.append(
            "summary additions hash mismatch: "
            f"{recorded_additions_hash} != {expected_additions_hash}"
        )
    expected_review_additions_hash = canonical_text_sha256(args.review_additions)
    recorded_review_additions_hash = summary.get("inputs", {}).get(
        "review_additions_sha256"
    )
    if recorded_review_additions_hash != expected_review_additions_hash:
        errors.append(
            "summary review additions hash mismatch: "
            f"{recorded_review_additions_hash} != {expected_review_additions_hash}"
        )
    expected_exclusions_hash = canonical_text_sha256(args.model_exclusions)
    recorded_exclusions_hash = summary.get("inputs", {}).get(
        "model_exclusions_sha256"
    )
    if recorded_exclusions_hash != expected_exclusions_hash:
        errors.append(
            "summary model exclusions hash mismatch: "
            f"{recorded_exclusions_hash} != {expected_exclusions_hash}"
        )
    expected_patches_hash = canonical_text_sha256(args.provenance_patches)
    recorded_patches_hash = summary.get("inputs", {}).get(
        "provenance_patches_sha256"
    )
    if recorded_patches_hash != expected_patches_hash:
        errors.append(
            "summary provenance patches hash mismatch: "
            f"{recorded_patches_hash} != {expected_patches_hash}"
        )
    recorded_patch_count = summary.get("provenance_patches", {}).get("applied_count")
    if recorded_patch_count != len(applied_patches):
        errors.append(
            "summary provenance patch count mismatch: "
            f"{recorded_patch_count} != {len(applied_patches)}"
        )

    report = {
        "passed": not errors,
        "check_count": 7,
        "passed_count": 7 if not errors else 0,
        "errors": errors,
        "row_count": len(output_rows),
        "addition_count": len(all_addition_rows),
        "output": portable_relative_path(args.output, root=REPOSITORY_ROOT),
        "output_sha256": expected_output_hash,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
