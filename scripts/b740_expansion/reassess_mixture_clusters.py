"""Correct CM mixing and reassess dependent points by pair and DOI clusters."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ("APROTIC_PAIR", "PROTIC_PRESENT")


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def cm_prediction(e1, e2, phi1):
    if any(finite(v) is None for v in (e1, e2, phi1)):
        return None
    e1, e2, phi1 = map(float, (e1, e2, phi1))
    if min(e1, e2) < 1 or not 0 <= phi1 <= 1:
        return None
    g = phi1 * (e1 - 1) / (e1 + 2) + (1 - phi1) * (e2 - 1) / (e2 + 2)
    return (1 + 2 * g) / (1 - g) if 0 <= g < 1 else None


def pair_key(row):
    a, b = sorted((row.get("ik1", "").strip(), row.get("ik2", "").strip()))
    return a + "|" + b if a and b else None


def cluster_bootstrap(rows, unit, seed=20261126, repetitions=4000):
    groups = defaultdict(list)
    omitted = 0
    for row in rows:
        key = pair_key(row) if unit == "pair" else row.get("doi", "").strip()
        value = finite(row.get("resid_vs_lichtenecker"))
        cls = row.get("association_class")
        if not key or value is None or cls not in CLASSES:
            omitted += 1
            continue
        groups[key].append((cls, value))
    keys = sorted(groups)
    observed = {c: [v for key in keys for cls, v in groups[key] if cls == c] for c in CLASSES}
    draws = {c: [] for c in CLASSES}
    differences = []
    rng = np.random.default_rng(seed)
    if len(keys) >= 2:
        for _ in range(repetitions):
            values = {c: [] for c in CLASSES}
            for index in rng.integers(0, len(keys), size=len(keys)):
                for cls, value in groups[keys[int(index)]]:
                    values[cls].append(value)
            medians = {c: float(np.median(values[c])) for c in CLASSES if values[c]}
            for cls, value in medians.items():
                draws[cls].append(value)
            if len(medians) == 2:
                differences.append(medians[CLASSES[1]] - medians[CLASSES[0]])

    def interval(values):
        return np.quantile(values, [0.025, 0.975]).tolist() if values else None

    by_class = {}
    for cls in CLASSES:
        n_clusters = sum(any(c == cls for c, _ in g) for g in groups.values())
        by_class[cls] = {
            "n_points": len(observed[cls]),
            "n_clusters": n_clusters,
            "median": float(np.median(observed[cls])) if observed[cls] else None,
            "ci95": interval(draws[cls]),
            "valid_replicates": len(draws[cls]),
            "inference_status": "DESCRIPTIVE_LIMITED_CLUSTERS"
            if n_clusters < 10
            else "CLUSTER_BOOTSTRAP",
        }
    ci = interval(differences)
    return {
        "unit": unit,
        "n_clusters": len(keys),
        "n_omitted_rows": omitted,
        "seed": seed,
        "n_requested_replicates": repetitions,
        "estimand": "point-weighted median residual; protic minus aprotic",
        "resampling": "global whole clusters with replacement, both classes share each draw",
        "by_class": by_class,
        "difference": {
            "point_estimate": float(
                np.median(observed[CLASSES[1]]) - np.median(observed[CLASSES[0]])
            )
            if all(observed.values())
            else None,
            "ci95": ci,
            "valid_replicates": len(differences),
            "undefined_replicates": repetitions - len(differences),
            "ci_excludes_zero": bool(ci is not None and (ci[0] > 0 or ci[1] < 0)),
        },
        "warning": "Conditional on available mixtures and pure references; missing-class draws omitted and counted; shared reference uncertainty and laboratories are not independently resolved.",
    }


def reassess(input_path, output_dir, repetitions=4000, seed=20261126):
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    raw = input_path.read_bytes()
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("empty mixture input")
    required = {
        "doi",
        "ik1",
        "ik2",
        "phi1",
        "epsilon_1_pure",
        "epsilon_2_pure",
        "epsilon_meas",
        "resid_vs_lichtenecker",
        "association_class",
    }
    if not required <= rows[0].keys():
        raise ValueError("missing mixture columns")
    corrected = []
    errors = []
    for row in rows:
        prediction = cm_prediction(row["epsilon_1_pure"], row["epsilon_2_pure"], row["phi1"])
        measured = finite(row["epsilon_meas"])
        residual = (
            measured - prediction if measured is not None and prediction is not None else None
        )
        if residual is not None:
            errors.append(abs(residual))
        corrected.append(
            {
                **row,
                "epsilon_cm_corrected": prediction,
                "resid_vs_cm_corrected": residual,
                "cm_corrected_status": "DEFINED"
                if residual is not None
                else "REFUSED_INVALID_INPUT",
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "mixture_cm_corrected.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(corrected[0]))
        writer.writeheader()
        writer.writerows(corrected)
    result = {
        "schema": "b750.mixture_cluster_reassessment/v1",
        "generator": "reassess_mixture_clusters/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "n_rows": len(rows),
        "cm_correction": {
            "forward": "g=(epsilon-1)/(epsilon+2)",
            "inverse": "epsilon=(1+2*g)/(1-g)",
            "domain": "0<=g<1; pole at g=1",
            "n_defined": len(errors),
            "n_refused": len(rows) - len(errors),
            "mae": float(np.mean(errors)) if errors else None,
            "historical_error": "g<0.49 was an artificial truncation; old 318/2278 coverage superseded",
        },
        "by_pair": cluster_bootstrap(rows, "pair", seed, repetitions),
        "by_doi": cluster_bootstrap(rows, "doi", seed, repetitions),
        "claim_guard": "Positive group medians do not imply every residual is positive; use a clustered group-contrast interval.",
    }
    if input_path.read_bytes() != raw:
        raise RuntimeError("historical input changed")
    (output_dir / "mixture_cluster_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cm": result["cm_correction"],
                "pair_difference": result["by_pair"]["difference"],
                "doi_difference": result["by_doi"]["difference"],
            }
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "outputs/b740_expansion/mixtures/mixture_dielectric_excess.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/b750_completion/mixtures"
    )
    parser.add_argument("--replicates", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261126)
    args = parser.parse_args()
    reassess(args.input, args.output_dir, args.replicates, args.seed)


if __name__ == "__main__":
    main()
