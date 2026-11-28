"""Paired X0 / unified opt-electronic transfer with the full 67 denominator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/b740_expansion"
spec = importlib.util.spec_from_file_location(
    "baseline_transfer", Path(__file__).with_name("run_new_molecule_transfer.py")
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
ELECTRONIC = ["dipole_D_opt", "polarizability_au_opt"]


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def electronic_values(row, core=False):
    columns = ("dipole_D_v7", "polarizability_au_v7") if core else ("dipole_D", "polarizability_au")
    values = [finite(row.get(c)) for c in columns]
    return None if any(v is None for v in values) or values[0] < 0 or values[1] <= 0 else values


def unique_by_identity(rows, source):
    result = {}
    for row in rows:
        key = row.get("inchikey", "")
        if not key or key in result:
            raise ValueError(source + ": missing or duplicate identity " + key)
        result[key] = row
    return result


def score(observed, prediction, training_mean):
    observed, prediction = np.asarray(observed), np.asarray(prediction)
    if not len(observed):
        return {"n": 0}
    error = prediction - observed
    total = float(np.square(observed - observed.mean()).sum())
    return {
        "n": len(observed),
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
        "bias": float(error.mean()),
        "r2": 1 - float(np.square(error).sum()) / total if total > 0 else None,
        "training_mean_baseline_mae": float(np.abs(observed - training_mean).mean()),
    }


def run(new_descriptors, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    opt = ROOT / "outputs/b700/orca_r2scan3c_opt_model.csv"
    ledger = BASE / "molecule_expansion/cohort_ledger.csv"
    structures_path = BASE / "molecule_expansion/new_molecule_structures.csv"
    scan = BASE / "thermoml/thermoml_local_scan.csv"
    core = unique_by_identity(baseline.load_csv(opt), "CORE opt")
    requested = unique_by_identity(
        [r for r in baseline.load_csv(ledger) if r["cohort"] == "NEW_MOLECULE_VALIDATED"],
        "requested",
    )
    if len(core) != 239 or len(requested) != 67 or set(core) & set(requested):
        raise ValueError("Frozen cohort drift")
    incoming = unique_by_identity(baseline.load_csv(new_descriptors), "new descriptors")
    if set(incoming) - set(requested):
        raise ValueError("Unregistered descriptor identity")
    structures = unique_by_identity(baseline.load_csv(structures_path), "structures")
    labels = baseline.eps_near_298(baseline.load_csv(scan))
    summary = {
        "schema": "b750.electronic_transfer/v1",
        "generator": "run_electronic_transfer/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_requested": 67,
        "electronic_features": ELECTRONIC,
        "units": {"dipole_D_opt": "Debye", "polarizability_au_opt": "bohr^3"},
        "excluded_features": [
            "homo_lumo_gap_ev_v7",
            "lippert_mataga_delta_f",
            "apparent_gk",
            "d_eps_dT_per_K",
        ],
        "gap_exclusion_reason": "Archived gap_v7 is inherited xTB, not ORCA opt.",
        "protocol": "CORE239-only fit; fixed ridge alpha=1; training-only scaling; identical test molecules and labels in both arms.",
        "selection_warning": "Completion-order subset is not representative; all gains are descriptive, not confirmed.",
        "source_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
            for p in (opt, ledger, structures_path, scan, new_descriptors)
        },
    }
    eligibility = []
    eligible = []
    for key, item in requested.items():
        row = incoming.get(key)
        reason = None
        if row is None:
            reason = "RESULT_NOT_COLLECTED_OR_REJECTED"
        elif row.get("status") != "ACCEPTED":
            reason = "RESULT_NOT_ACCEPTED"
        elif not all(
            str(row.get(c, "")).lower() == "true"
            for c in ("method_verified", "opt_converged", "terminated_normally", "scf_converged")
        ) or not row.get("output_sha256"):
            reason = "UNVERIFIED_ACCEPTANCE_PROVENANCE"
        elif electronic_values(row) is None:
            reason = "INVALID_ELECTRONIC_VALUES"
        elif key not in labels:
            reason = "NO_NEAR_AMBIENT_STATIC_LABEL"
        elif key not in structures:
            reason = "NO_VERIFIED_STRUCTURE"
        else:
            structure = structures[key]
            if (
                structure.get("identity_verified", "").lower() != "true"
                or structure.get("inchikey_roundtrip") != key
            ):
                reason = "STRUCTURE_IDENTITY_NOT_VERIFIED"
            else:
                features = baseline.rdkit_features(structure["smiles"])
                if features is None:
                    reason = "STRUCTURE_FEATURE_FAILURE"
        eligibility.append({"inchikey": key, "status": reason or "ELIGIBLE"})
        if reason is None:
            eligible.append((key, item, features, electronic_values(row), labels[key]))
    summary.update(
        n_accepted_descriptors=sum(
            r.get("status") == "ACCEPTED" and electronic_values(r) is not None
            for r in incoming.values()
        ),
        n_evaluable=len(eligible),
        eligibility=eligibility,
        status="BLOCKED_NO_EVALUABLE_RESULTS"
        if not eligible
        else "PARTIAL_RESULTS"
        if len(eligible) < 67
        else "COMPLETE_RESULTS",
    )
    if eligible:
        train_x0, train_x1, train_y = [], [], []
        for key, row in core.items():
            values = electronic_values(row, core=True)
            label = finite(row.get("epsilon"))
            features = baseline.rdkit_features(row.get("smiles", ""))
            if values is None or label is None or features is None:
                raise ValueError("CORE239 unusable row; refusing silent denominator loss: " + key)
            structural = [features[c] for c in baseline.FEATURES]
            train_x0.append(structural)
            train_x1.append(structural + values)
            train_y.append(label)
        x0 = np.asarray([[item[2][c] for c in baseline.FEATURES] for item in eligible])
        x1 = np.asarray([list(x0[i]) + item[3] for i, item in enumerate(eligible)])
        y = np.asarray([item[4][1] for item in eligible])
        p0 = baseline.fit_predict(np.asarray(train_x0), np.asarray(train_y), x0)
        p1 = baseline.fit_predict(np.asarray(train_x1), np.asarray(train_y), x1)
        records = []
        for i, (key, item, features, _, label) in enumerate(eligible):
            records.append(
                {
                    "inchikey": key,
                    "name": item.get("name", ""),
                    "epsilon_label": y[i],
                    "label_T_K": label[2],
                    "label_doi": label[3],
                    "is_ionic": features["n_fragments"] > 1,
                    "prediction_X0": p0[i],
                    "prediction_X0_X1": p1[i],
                    "paired_abs_error_gain": abs(p0[i] - y[i]) - abs(p1[i] - y[i]),
                }
            )
        summary["training_n"] = len(train_y)
        summary["results"] = {}
        for group, indices in [
            ("all", list(range(len(y)))),
            ("neutral", [i for i, r in enumerate(records) if not r["is_ionic"]]),
            ("ionic", [i for i, r in enumerate(records) if r["is_ionic"]]),
        ]:
            idx = np.asarray(indices, dtype=int)
            summary["results"][group] = {
                "X0": score(y[idx], p0[idx], np.mean(train_y)),
                "X0_X1": score(y[idx], p1[idx], np.mean(train_y)),
                "paired_mae_gain": float(
                    np.mean(np.abs(p0[idx] - y[idx]) - np.abs(p1[idx] - y[idx]))
                )
                if len(idx)
                else None,
                "evidence_level": "DESCRIPTIVE_ONLY",
            }
        with (output_dir / "paired_predictions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    elif (output_dir / "paired_predictions.csv").exists():
        raise ValueError("Stale predictions in blocked directory; choose a fresh output directory")
    (output_dir / "electronic_transfer_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "n_evaluable": len(eligible),
                "results": summary.get("results"),
            }
        )
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-descriptors",
        type=Path,
        default=BASE / "dft_expansion/results_opt/validation/new_molecule_descriptors.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/b750_completion/electronic_transfer"
    )
    args = parser.parse_args()
    run(args.new_descriptors, args.output_dir)


if __name__ == "__main__":
    main()
