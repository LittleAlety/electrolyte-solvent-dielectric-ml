"""Build public candidate metadata without promoting restricted dielectric values."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path

PUBLIC_FIELDS = (
    "candidate_id",
    "name",
    "family",
    "restricted_evidence_status",
    "restricted_system_id",
    "primary_reference",
    "compilation_reference",
    "decision_status",
    "notes",
)
RESTRICTED_FIELDS = (
    "candidate_id",
    "name",
    "system_id",
    "T_K",
    "dielectric",
    "primary_reference",
    "compilation_reference",
    "source_url",
    "status",
)
FAMILIES = {
    "carbonate": "linear_or_fluorinated_carbonate",
    "dioxolane": "cyclic_ether",
    "nitrile": "nitrile",
    "sulfone": "sulfone_or_sulfoxide",
    "fluoroether": "fluorinated_ether",
}
UNMATCHED_TARGETS = (
    ("fluoroethylene carbonate", "cyclic_carbonate"),
    ("vinylene carbonate", "cyclic_carbonate"),
    ("difluoroethylene carbonate", "cyclic_carbonate"),
    ("2,2,2-trifluoroethyl acetate", "fluorinated_ester"),
    ("2,2,2-trifluoroethyl formate", "fluorinated_ester"),
    (
        "1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether",
        "fluorinated_ether",
    ),
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


def family_for_title(title: str) -> str:
    lowered = title.lower()
    for term, family in FAMILIES.items():
        if term in lowered:
            return family
    return "other"


def choose_nearest_row(
    rows: Sequence[Mapping[str, object]],
    *,
    target_temperature: float = 298.15,
    max_delta: float = 10.0,
) -> Mapping[str, object] | None:
    candidates = [
        row
        for row in rows
        if row.get("T_K") is not None
        and abs(float(row["T_K"]) - target_temperature) <= max_delta
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: abs(float(row["T_K"]) - target_temperature),
    )


def primary_reference_for_row(
    record: Mapping[str, object],
    row: Mapping[str, object],
) -> tuple[str, str]:
    target_values = (float(row["dielectric"]), float(row["T_K"]))
    for line in str(record.get("page_text", "")).splitlines():
        fields = line.split("\t")
        numeric = []
        for field in fields[:2]:
            try:
                numeric.append(float(field))
            except ValueError:
                numeric = []
                break
        if len(numeric) != 2:
            continue
        if all(
            abs(actual - expected) <= 1e-8
            for actual, expected in zip(numeric, target_values, strict=True)
        ):
            padded = [*fields, "", "", ""]
            return padded[2], padded[3]
    return "", ""


def build_queue(
    *,
    restricted_path: Path,
    public_output: Path,
    restricted_output: Path,
    summary_output: Path,
) -> dict[str, object]:
    catalog = json.loads(restricted_path.read_text(encoding="utf-8"))
    public_rows: list[dict[str, object]] = []
    restricted_rows: list[dict[str, object]] = []
    for record in catalog["records"]:
        selected = choose_nearest_row(record.get("rows", []))
        name = str(record["name"])
        candidate_id = f"modern:{len(public_rows) + 1:03d}"
        family = family_for_title(name)
        if selected is None:
            public_rows.append(
                {
                    "candidate_id": candidate_id,
                    "name": name,
                    "family": family,
                    "restricted_evidence_status": "no_near_298_value",
                    "restricted_system_id": str(record["systemId"]),
                    "primary_reference": "",
                    "compilation_reference": "",
                    "decision_status": "primary_source_search_required",
                    "notes": "Restricted page exists but no near-room value was parsed.",
                }
            )
            continue
        primary, compilation = primary_reference_for_row(record, selected)
        public_rows.append(
            {
                "candidate_id": candidate_id,
                "name": name,
                "family": family,
                "restricted_evidence_status": "near_298_value_available_restricted",
                "restricted_system_id": str(record["systemId"]),
                "primary_reference": primary,
                "compilation_reference": compilation,
                "decision_status": "primary_source_and_rights_review_required",
                "notes": "Numeric value remains only in restricted storage.",
            }
        )
        restricted_rows.append(
            {
                "candidate_id": candidate_id,
                "name": name,
                "system_id": record["systemId"],
                "T_K": selected["T_K"],
                "dielectric": selected["dielectric"],
                "primary_reference": primary,
                "compilation_reference": compilation,
                "source_url": record["url"],
                "status": "restricted_crosscheck_only",
            }
        )
    for name, family in UNMATCHED_TARGETS:
        candidate_id = f"modern:{len(public_rows) + 1:03d}"
        public_rows.append(
            {
                "candidate_id": candidate_id,
                "name": name,
                "family": family,
                "restricted_evidence_status": "not_found",
                "restricted_system_id": "",
                "primary_reference": "",
                "compilation_reference": "",
                "decision_status": "primary_source_search_required",
                "notes": "No matching restricted interactive dielectric record.",
            }
        )
    write_csv_rows(public_output, PUBLIC_FIELDS, public_rows)
    write_csv_rows(restricted_output, RESTRICTED_FIELDS, restricted_rows)
    summary = {
        "schema_version": 1,
        "candidate_count": len(public_rows),
        "restricted_near_room_value_count": len(restricted_rows),
        "public_trainable_value_count": 0,
        "decision": (
            "Candidate queue only: restricted values are not promoted into a "
            "public dielectric_v03 table."
        ),
        "public_queue": portable_relative_path(public_output, root=REPOSITORY_ROOT),
        "restricted_values": portable_relative_path(
            restricted_output,
            root=REPOSITORY_ROOT,
        ),
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restricted-input",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "restricted"
        / "springer_materials"
        / "modern_battery_solvent_candidates.json",
    )
    parser.add_argument(
        "--public-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "modern_battery_solvent_candidate_queue.csv",
    )
    parser.add_argument(
        "--restricted-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "restricted"
        / "springer_materials"
        / "modern_battery_solvent_values.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "modern_battery_solvent_queue_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = build_queue(
        restricted_path=args.restricted_input,
        public_output=args.public_output,
        restricted_output=args.restricted_output,
        summary_output=args.summary_output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
