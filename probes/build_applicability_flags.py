"""Annotate representation-ablation OOF predictions with applicability flags.

The flag is a disclosure boundary, so the summary this script writes must make
the boundary auditable: it records the adopted rule, its trigger rate, the
error stratification it is supposed to explain, how much of the measured
high-permittivity zone it covers, and the alternative rules that were measured
and rejected.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.applicability import (
    H_BOND_DONOR_SMARTS,
    INSIDE_DOMAIN,
    OUTSIDE_ASSOCIATED_LIQUID,
    applicability_domain,
    count_hbond_donors,
)
from electrolyte_ml.pathing import portable_relative_path
from electrolyte_ml.xtb_features import onsager_dielectric_estimate

HIGH_PERMITTIVITY_THRESHOLD = 60.0

OUTPUT_FIELDS = (
    "representation",
    "repeat",
    "fold",
    "inchikey",
    "name",
    "T_K",
    "hbd",
    "hbond_donor_count",
    "target",
    "prediction",
    "onsager_epsilon",
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


def _onsager_epsilon(feature: Mapping[str, str]) -> float | None:
    """Return a model-independent Onsager estimate, or None if unavailable.

    Kept as a recorded diagnostic.  It is no longer the trigger: the estimate
    is inverted for the compounds the boundary is meant to describe.
    """
    if feature.get("status") == "error":
        return None
    try:
        return onsager_dielectric_estimate(
            dipole_debye=float(feature["dipole_D"]),
            molar_volume_m3_mol=float(feature["molar_volume_m3_mol"]),
            polarizability_A3=float(feature["polarizability_A3"]),
            temperature_K=float(feature["T_K"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _mean(values: Sequence[float]) -> float | None:
    return statistics.mean(values) if values else None


def _stats_label(smiles: str, donor_count: int) -> str:
    return f"{smiles} donors={donor_count}"


def run(
    *,
    predictions_path: Path,
    features_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    features = {row["inchikey"]: row for row in read_csv_rows(features_path)}
    donors = {
        inchikey: count_hbond_donors(feature["smiles"])
        for inchikey, feature in features.items()
    }

    output_rows: list[dict[str, object]] = []
    onsager_available = 0
    onsager_fallback = 0
    adopted_errors: dict[str, list[float]] = collections.defaultdict(list)
    onsager_errors: dict[str, list[float]] = collections.defaultdict(list)
    high_zone_rows = 0
    high_zone_errors: list[float] = []
    high_zone_covered = 0
    high_zone_onsager_covered = 0
    onsager_flagged_names: dict[str, str] = {}

    for row in read_csv_rows(predictions_path):
        inchikey = row["inchikey"]
        feature = features[inchikey]
        donor_count = donors[inchikey]
        onsager_epsilon = _onsager_epsilon(feature)
        if onsager_epsilon is None:
            onsager_fallback += 1
        else:
            onsager_available += 1

        prediction = float(row["prediction"])
        target = float(row["target"])
        absolute_error = abs(prediction - target)

        domain = applicability_domain(prediction, donor_count=donor_count)
        output_rows.append(
            {
                "representation": row["representation"],
                "repeat": row["repeat"],
                "fold": row["fold"],
                "inchikey": inchikey,
                "name": row["name"],
                "T_K": row["T_K"],
                "hbd": feature["hbd"],
                "hbond_donor_count": donor_count,
                "target": row["target"],
                "prediction": row["prediction"],
                "onsager_epsilon": (
                    "" if onsager_epsilon is None else f"{onsager_epsilon:.12g}"
                ),
                "applicability_domain": domain,
            }
        )

        adopted_errors[domain].append(absolute_error)

        legacy_flagged = int(feature["hbd"]) >= 1 and prediction > HIGH_PERMITTIVITY_THRESHOLD
        onsager_flagged = (
            donor_count >= 1
            and onsager_epsilon is not None
            and onsager_epsilon > HIGH_PERMITTIVITY_THRESHOLD
        )
        if legacy_flagged:
            onsager_errors["legacy"].append(absolute_error)
        if onsager_flagged:
            onsager_errors["onsager"].append(absolute_error)
            onsager_flagged_names[inchikey] = str(feature.get("name", ""))

        if target > HIGH_PERMITTIVITY_THRESHOLD:
            high_zone_rows += 1
            high_zone_errors.append(absolute_error)
            if domain == OUTSIDE_ASSOCIATED_LIQUID:
                high_zone_covered += 1
            if onsager_flagged:
                high_zone_onsager_covered += 1

    counts = collections.Counter(
        str(row["applicability_domain"]) for row in output_rows
    )
    row_count = len(output_rows)
    write_csv_rows(output_path, OUTPUT_FIELDS, output_rows)

    summary: dict[str, object] = {
        "schema_version": 2,
        "predictions_path": portable_relative_path(
            predictions_path,
            root=REPOSITORY_ROOT,
        ),
        "features_path": portable_relative_path(features_path, root=REPOSITORY_ROOT),
        "output_path": portable_relative_path(output_path, root=REPOSITORY_ROOT),
        "row_count": row_count,
        "domain_counts": dict(sorted(counts.items())),
        "inside_domain_count": counts[INSIDE_DOMAIN],
        "outside_associated_liquid_count": counts[OUTSIDE_ASSOCIATED_LIQUID],
        "outside_count": row_count - counts[INSIDE_DOMAIN],
        "trigger_rate": (row_count - counts[INSIDE_DOMAIN]) / row_count,
        "rule": (
            "predicted_dielectric < 1.0 => outside_nonphysical; "
            "hbond_donor_count >= 1 => outside_associated_liquid"
        ),
        "rule_smarts": H_BOND_DONOR_SMARTS,
        "rule_basis": (
            "Textbook hydrogen-bond donor count computed from SMILES, so the "
            "boundary is independent of any model output."
        ),
        "mean_absolute_error_by_domain": {
            domain: _mean(errors) for domain, errors in sorted(adopted_errors.items())
        },
        "high_permittivity_zone": {
            "definition": "target dielectric > 60",
            "row_count": high_zone_rows,
            "mean_absolute_error": _mean(high_zone_errors),
            "covered_by_adopted_rule": high_zone_covered,
            "coverage": high_zone_covered / high_zone_rows if high_zone_rows else None,
        },
        "rejected_variants": {
            "legacy_prediction_threshold": {
                "rule": "hbd >= 1 and predicted dielectric > 60",
                "mean_absolute_error": _mean(onsager_errors.get("legacy", [])),
                "row_count": len(onsager_errors.get("legacy", [])),
                "reason": (
                    "Circular: the trigger reads the model output the boundary "
                    "is supposed to qualify, and the model cannot predict the "
                    "compounds the boundary exists to catch."
                ),
            },
            "onsager_threshold": {
                "rule": "hbond_donor_count >= 1 and onsager_epsilon > 60",
                "mean_absolute_error": _mean(onsager_errors.get("onsager", [])),
                "row_count": len(onsager_errors.get("onsager", [])),
                "flagged_compounds": sorted(onsager_flagged_names.values()),
                "high_permittivity_zone_covered": high_zone_onsager_covered,
                "reason": (
                    "Model-independent but physically inverted: the Onsager "
                    "reaction-field estimate is low for hydrogen-bonded "
                    "associated liquids (Kirkwood g much greater than 1) and "
                    "high for ionic liquids, so it misses the failure zone and "
                    "flags low-permittivity ionic liquids instead."
                ),
            },
        },
        "onsager_available": onsager_available,
        "onsager_fallback": onsager_fallback,
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
