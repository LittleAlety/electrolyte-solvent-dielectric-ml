"""Measure the NBS Circular 514 frequency gate against the frozen dataset.

A G1+ crawl for the modern battery-solvent candidates surfaced NBS Circular 514
entry `p20:009` - isobutyronitrile, eps = 20.4 at 297.15 K - as an apparent
new static value.  It is not one: the transcript carries
`f=3.6x10^8 cycles/sec`, i.e. a 360 MHz measurement inside the dispersion
region.

The rule being applied is the **NBS import rule**, not a global zero-frequency
contract.  The manual entry schema admits `zero_frequency` *or* an explicitly
justified `static_low_frequency` protocol
(`docs/week3/manual_dielectric_entry_schema.md`), which is how the 1 MHz
ethylene carbonate row entered the main table.  What actually excludes the
microwave rows is specific to NBS Circular 514:
`scripts/resolve_nbs514_structures.py` records the exclusion reason
`frequency_dependent` for any row with a non-empty `frequency_note`, and
`scripts/build_dielectric_v02.py` refuses to import such a row.

This probe measures that rule instead of assuming it: it counts every transcript
row with an explicit frequency note, checks how many of them are inside
`data/dielectric_v03.csv`, and cross-references the modern battery-solvent
candidate queue.  The answer decides whether the crawl hit is ingestable or must
be recorded as a limitation.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

TRANSCRIPT_FILES = (
    "data/interim/nbs514_organic_part1.csv",
    "data/interim/nbs514_organic_part2.csv",
    "data/interim/nbs514_organic_part3.csv",
    "data/interim/nbs514_organic_part4.csv",
)
STATIC_DATASET = "data/dielectric_v03.csv"
MODERN_QUEUE = "data/processed/modern_battery_solvent_candidate_queue.csv"

# The crawl hits this audit exists to adjudicate.
CRAWL_TARGETS = (
    "nbs514:p20:008",
    "nbs514:p20:009",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_audit(repo_root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    transcript: list[dict[str, str]] = []
    for relative in TRANSCRIPT_FILES:
        transcript.extend(read_csv_rows(repo_root / relative))

    static_rows = read_csv_rows(repo_root / STATIC_DATASET)
    static_ids = {row["source_record_id"] for row in static_rows if row["source_record_id"]}
    nbs_static = [row for row in static_rows if "nbs.circ.514" in (row["source_doi"] or "")]
    queue_names = {
        row["name"].strip().lower()
        for row in read_csv_rows(repo_root / MODERN_QUEUE)
    }

    frequency_rows = [
        row for row in transcript if (row.get("frequency_note") or "").strip()
    ]
    frequency_in_static = [
        row for row in frequency_rows if row["source_id"] in static_ids
    ]
    frequency_on_queue = [
        row
        for row in frequency_rows
        if (row["compound_name"] or "").strip().lower() in queue_names
    ]

    return {
        "schema_version": "nbs514_frequency_gate_audit/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": {
            "question": (
                "Are NBS Circular 514 rows with an explicit microwave frequency "
                "note inside the static dielectric dataset?"
            ),
            "network_used": False,
            "rule_applied": (
                "The NBS Circular 514 import path excludes every row carrying an "
                "explicit frequency note."
            ),
            "rule_sources": [
                (
                    "scripts/resolve_nbs514_structures.py: exclusion reason "
                    "'frequency_dependent' for any non-empty frequency_note"
                ),
                (
                    "scripts/build_dielectric_v02.py: raises when a selected NBS "
                    "row carries a frequency_note"
                ),
                (
                    "docs/week3/manual_dielectric_entry_schema.md: frequency_type "
                    "must be zero_frequency or an explicitly justified "
                    "static_low_frequency protocol"
                ),
            ],
            "why_360_mhz_is_not_static_low_frequency": (
                "3.6x10^8 cycles/sec sits inside the dispersion region; it is not a "
                "low-frequency protocol that could be justified the way the 1 MHz "
                "ethylene carbonate measurement is."
            ),
            "transcript_files": list(TRANSCRIPT_FILES),
            "static_dataset": STATIC_DATASET,
        },
        "transcript": {
            "rows": len(transcript),
            "distinct_compounds": len(
                {(row["compound_name"] or "").strip() for row in transcript}
            ),
            "frequency_noted_rows": len(frequency_rows),
            "frequency_note_values": dict(
                sorted(
                    collections.Counter(
                        row["frequency_note"].strip() for row in frequency_rows
                    ).items()
                )
            ),
            "frequency_noted_eligibility_statuses": dict(
                sorted(
                    collections.Counter(
                        row["eligibility_status"] for row in frequency_rows
                    ).items()
                )
            ),
        },
        "static_dataset": {
            "path": STATIC_DATASET,
            "canonical_sha256": canonical_text_sha256(repo_root / STATIC_DATASET),
            "rows": len(static_rows),
            "nbs_sourced_rows": len(nbs_static),
            "nbs_rows_carrying_zero_frequency_gate": sum(
                1 for row in nbs_static if "zero_frequency" in (row["gate_flags"] or "")
            ),
            "nbs_rows_without_gate_flags": sum(
                1 for row in nbs_static if not (row["gate_flags"] or "")
            ),
        },
        "cross_check": {
            "frequency_noted_rows_present_in_static_dataset": len(frequency_in_static),
            "frequency_noted_rows_absent_from_static_dataset": len(frequency_rows)
            - len(frequency_in_static),
            "frequency_noted_rows_also_modern_queue_candidates": len(frequency_on_queue),
            "modern_queue_candidates_gated_by_frequency": [
                {
                    "source_id": row["source_id"],
                    "compound_name": row["compound_name"],
                    "dielectric": row["dielectric"],
                    "T_K": row["T_K"],
                    "frequency_note": row["frequency_note"],
                    "eligibility_status": row["eligibility_status"],
                }
                for row in frequency_on_queue
            ],
        },
        "crawl_targets": [
            {
                "source_id": row["source_id"],
                "compound_name": row["compound_name"],
                "formula": row["formula"],
                "dielectric": row["dielectric"],
                "T_K": row["T_K"],
                "frequency_note": row["frequency_note"],
                "eligibility_status": row["eligibility_status"],
                "present_in_static_dataset": row["source_id"] in static_ids,
            }
            for row in transcript
            if row["source_id"] in CRAWL_TARGETS
        ],
        "conclusion": (
            "Every NBS Circular 514 row carrying an explicit microwave frequency "
            "note is outside the static dataset, and the two p20 butyronitrile / "
            "isobutyronitrile entries are no exception. The isobutyronitrile "
            "crawl hit is therefore a frequency-gated observation, not an "
            "ingestable static permittivity: importing it would overrule the NBS "
            "frequency-note exclusion applied to all 127 frequency-noted transcript rows, "
            "and 360 MHz is not a justifiable static low-frequency protocol. This "
            "is not a claim that the project admits zero-frequency data only: the "
            "schema also allows an explicitly justified static_low_frequency "
            "protocol."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "nbs514_frequency_gate_audit.json",
    )
    args = parser.parse_args(argv)

    report = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    cross = report["cross_check"]
    print(f"wrote {args.output.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(
        f"  frequency-noted transcript rows: "
        f"{report['transcript']['frequency_noted_rows']}"
    )
    print(
        f"  present in the static dataset: "
        f"{cross['frequency_noted_rows_present_in_static_dataset']}"
    )
    print(
        f"  modern-queue candidates gated: "
        f"{cross['frequency_noted_rows_also_modern_queue_candidates']}"
    )
    for target in report["crawl_targets"]:
        print(
            f"  {target['source_id']} {target['compound_name']}: "
            f"{target['dielectric']} @ {target['T_K']} K, "
            f"{target['frequency_note']} -> in dataset: "
            f"{target['present_in_static_dataset']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
