"""Leakage-free paired liquid ablation; historical results remain read-only."""

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
CORE = ROOT / "outputs/b700/orca_r2scan3c_opt_model.csv"
LIQUID = ROOT / "outputs/b740_expansion/thermodynamic_properties/liquid_thermodynamic_indices.csv"
OUT = ROOT / "outputs/b750_completion/leakage_audit"
spec = importlib.util.spec_from_file_location(
    "baseline_transfer", Path(__file__).with_name("run_new_molecule_transfer.py")
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
X0 = list(baseline.FEATURES)
X1 = ["dipole_D_v7", "polarizability_au_v7"]
X3 = ["n_D", "molar_volume_cm3_mol", "rho_HBD_per_cm3", "rho_HBA_per_cm3"]
ALLOWLIST = frozenset(X0 + X1 + X3)


def guard_features(features):
    tokens = (
        "epsilon",
        "permittivity",
        "lippert",
        "delta_f",
        "apparent_g",
        "d_eps",
        "kf_rhs",
        "target",
        "resid",
    )
    for name in features:
        if any(token in name.lower() for token in tokens):
            raise ValueError("Target-derived feature refused: " + name)
        if name not in ALLOWLIST:
            raise ValueError("Unreviewed feature refused: " + name)
    if len(features) != len(set(features)):
        raise ValueError("Duplicate feature columns")


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def ridge_predict(x_train, y_train, x_test):
    return baseline.fit_predict(x_train, y_train, x_test)


def paired_loo(rows, features):
    guard_features(features)
    if len(rows) < 3:
        return None, None
    x = np.asarray([[row[col] for col in features] for row in rows], dtype=float)
    y = np.asarray([row["epsilon"] for row in rows], dtype=float)
    predictions = np.empty(len(y))
    constants = np.empty(len(y))
    for i in range(len(y)):
        mask = np.arange(len(y)) != i
        predictions[i] = ridge_predict(x[mask], y[mask], x[i : i + 1])[0]
        constants[i] = y[mask].mean()
    denominator = float(np.square(y - y.mean()).sum())
    result = {
        "n": len(y),
        "features": features,
        "n_features": len(features),
        "mae": float(np.abs(predictions - y).mean()),
        "rmse": float(np.sqrt(np.square(predictions - y).mean())),
        "r2": 1 - float(np.square(predictions - y).sum()) / denominator
        if denominator > 0
        else None,
        "training_fold_mean_baseline_mae": float(np.abs(constants - y).mean()),
    }
    return result, predictions


def unique_index(rows, label):
    result = {}
    for row in rows:
        key = row.get("inchikey", "").strip()
        if not key or key in result:
            raise ValueError(label + ": missing or duplicate identity " + key)
        result[key] = row
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-new", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        ROOT / "outputs/b750_completion/leakage_audit_expanded" if args.include_new else OUT
    )
    guard_features(X0 + X1 + X3)
    core = unique_index(baseline.load_csv(CORE), "CORE opt")
    liquid = unique_index(baseline.load_csv(LIQUID), "liquid")
    if len(core) != 239:
        raise ValueError("CORE239 drift")
    n_expansion_requested = 0
    if args.include_new:
        # Same structural feature code for both cohorts; no stored/recomputed mix.
        for key, row in core.items():
            features = baseline.rdkit_features(row["smiles"])
            if features is None:
                raise ValueError("Cannot reproduce CORE239 structural row: " + key)
            row.update(features)
        expansion = ROOT / "outputs/b740_expansion/molecule_expansion"
        requested = [
            r
            for r in baseline.load_csv(expansion / "cohort_ledger.csv")
            if r["cohort"] == "NEW_MOLECULE_VALIDATED"
        ]
        if len(requested) != 67:
            raise ValueError("Expansion denominator drift")
        n_expansion_requested = len(requested)
        structures = unique_index(
            baseline.load_csv(expansion / "new_molecule_structures.csv"), "structures"
        )
        accepted = unique_index(
            baseline.load_csv(
                ROOT
                / "outputs/b740_expansion/dft_expansion/results_opt/validation/new_molecule_descriptors.csv"
            ),
            "new electronics",
        )
        labels = baseline.eps_near_298(
            baseline.load_csv(ROOT / "outputs/b740_expansion/thermoml/thermoml_local_scan.csv")
        )
        for item in requested:
            key = item["inchikey"]
            if key in core:
                raise ValueError("Expansion overlaps CORE239")
            row = {
                "inchikey": key,
                "name": item.get("name", ""),
                "epsilon": labels.get(key, (None, None))[1],
            }
            if key in accepted and key in structures and accepted[key]["status"] == "ACCEPTED":
                st = structures[key]
                if (
                    st.get("identity_verified", "").lower() != "true"
                    or st.get("inchikey_roundtrip") != key
                ):
                    raise ValueError("Unverified new structure")
                features = baseline.rdkit_features(st["smiles"])
                if features is not None:
                    row.update(features)
                row.update(
                    dipole_D_v7=accepted[key]["dipole_D"],
                    polarizability_au_v7=accepted[key]["polarizability_au"],
                )
            core[key] = row
    panel, excluded = [], []
    required = ["epsilon"] + X0 + X1
    for key, row in core.items():
        measured = liquid.get(key)
        if measured is None:
            excluded.append({"inchikey": key, "reason": "NO_LIQUID_RECORD"})
            continue
        merged = {
            "inchikey": key,
            "name": row.get("name", ""),
            **{c: number(row.get(c)) for c in required},
            **{c: number(measured.get(c)) for c in X3},
        }
        missing = [c for c in required + X3 if merged[c] is None]
        if missing:
            excluded.append({"inchikey": key, "reason": "MISSING_OR_NONFINITE", "columns": missing})
        else:
            panel.append(merged)
    panel.sort(key=lambda row: row["inchikey"])
    base, p0 = paired_loo(panel, X0 + X1)
    augmented, p1 = paired_loo(panel, X0 + X1 + X3)
    gain = base["mae"] - augmented["mae"] if base else None
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "b750.safe_liquid_ablation/v1",
        "generator": "run_safe_liquid_ablation/1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "DESCRIPTIVE_PAIRED_RESULT" if base else "INSUFFICIENT_DATA",
        "n_core": len(core),
        "n_core239": 239,
        "n_expansion_requested": n_expansion_requested,
        "expanded_panel_warning": "Completion-order-selected new rows; descriptive paired CV only. Expanded structure features recomputed for both cohorts."
        if args.include_new
        else None,
        "n_paired_panel": len(panel),
        "n_excluded": len(excluded),
        "actual_features": {"X0": X0, "X1": X1, "X3": X3},
        "base": base,
        "augmented": augmented,
        "paired_mae_gain": gain,
        "protocol": {
            "evaluation": "same-panel leave-one-molecule-out",
            "model": "ridge alpha=1, unpenalised intercept",
            "scaling": "training fold only",
            "electronic_geometry": "r2SCAN-3c opt dipole/polarizability only",
        },
        "scientific_corrections": [
            "delta_f contains the epsilon target and is forbidden",
            "historical X3 gain -0.0232 is not leakage-free predictive evidence",
            "gap_v7 originates from xTB and is excluded",
            "fingerprint protocol unrecorded; morgan2_nbits excluded",
            "model, geometry and feature definitions changed; score difference is not attributable only to removing delta_f",
            "small panel and dependent sources permit descriptive results, not a general claim",
        ],
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (CORE, LIQUID)
        },
        "excluded": excluded,
    }
    (output_dir / "safe_liquid_ablation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if base:
        with (output_dir / "paired_predictions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "inchikey",
                    "epsilon",
                    "prediction_base",
                    "prediction_augmented",
                    "absolute_error_improvement",
                ],
            )
            writer.writeheader()
            for i, row in enumerate(panel):
                y = row["epsilon"]
                writer.writerow(
                    {
                        "inchikey": row["inchikey"],
                        "epsilon": y,
                        "prediction_base": p0[i],
                        "prediction_augmented": p1[i],
                        "absolute_error_improvement": abs(p0[i] - y) - abs(p1[i] - y),
                    }
                )
    print(
        json.dumps(
            {
                "n_paired_panel": len(panel),
                "base": base,
                "augmented": augmented,
                "paired_mae_gain": gain,
            }
        )
    )


if __name__ == "__main__":
    main()
