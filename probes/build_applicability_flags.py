"""Annotate representation-ablation OOF predictions with applicability flags."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.applicability import applicability_domain
from electrolyte_ml.pathing import portable_relative_path

OUTPUT_FIELDS = (
    "representation",
    "repeat",
    "fold",
    "inchikey",
    "name",
    "T_K",
    "hbd",
    "target",
    "prediction",
    "applicability_domain",
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


def run(
    *,
    predictions_path: Path,
    features_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    features = {
        row["inchikey"]: row
        for row in read_csv_rows(features_path)
        if row["status"] != "error"
    }
    output_rows: list[dict[str, object]] = []
    for row in read_csv_rows(predictions_path):
        feature = features[row["inchikey"]]
        domain = applicability_domain(
            float(row["prediction"]),
            hbd_count=int(feature["hbd"]),
        )
        output_rows.append(
            {
                "representation": row["representation"],
                "repeat": row["repeat"],
                "fold": row["fold"],
                "inchikey": row["inchikey"],
                "name": row["name"],
                "T_K": row["T_K"],
                "hbd": feature["hbd"],
                "target": row["target"],
                "prediction": row["prediction"],
                "applicability_domain": domain,
            }
        )
    counts = collections.Counter(
        str(row["applicability_domain"]) for row in output_rows
    )
    write_csv_rows(output_path, OUTPUT_FIELDS, output_rows)
    summary = {
        "schema_version": 1,
        "predictions_path": portable_relative_path(
            predictions_path,
            root=REPOSITORY_ROOT,
        ),
        "features_path": portable_relative_path(features_path, root=REPOSITORY_ROOT),
        "output_path": portable_relative_path(output_path, root=REPOSITORY_ROOT),
        "row_count": len(output_rows),
        "domain_counts": dict(sorted(counts.items())),
        "rule": "HBD >= 1 and predicted dielectric > 60 => outside_associated_liquid",
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_representation_ablation_predictions.csv",
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features_density.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_applicability_flags.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "applicability_domain_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run(
        predictions_path=args.predictions,
        features_path=args.features,
        output_path=args.output,
        summary_path=args.summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
