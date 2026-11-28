#!/usr/bin/env python
"""B748-01: multiscale feature ablation X0 -> X1 -> X2 -> X3 on a COMMON molecule set.

The plan's central model question is whether each new layer of physical information
buys anything once the previous layer is present. That is only answerable if every
configuration is scored on the SAME molecules with the SAME folds, so this script
first intersects the feature layers, reports the coverage loss, and only then fits.

Layers
  X0  structure (RDKit/topology)
  X1  single-molecule electronic (r2SCAN-3c dipole, gap, polarizability, anisotropy)
  X2  conformer statistics (C_mu, S_conf, N_eff) -- only for the 39 B704 molecules
  X3  experimental liquid properties (n_D, V_m, rho_HBD/HBA, Lippert-Mataga)

COVERAGE HONESTY: X3 exists for only a few dozen molecules and X2 for 39, so the
full X0+X1+X2+X3 model would be scored on a handful. This script therefore reports
TWO comparisons and never mixes them:

  (a) FULL COHORT  : X0 vs X0+X1, on all molecules that have X1           (n=239)
  (b) COMMON SUBSET: X0 vs X0+X1 vs X0+X1+X2 vs X0+X1+X2+X3, on the
                     intersection                                     (n = small)

Quoting (b)'s improvement against (a)'s baseline would be a selection-bias error,
and the output says so explicitly.

Outputs (outputs/b740_expansion/multiscale_models/):
  multiscale_ablation.csv
  multiscale_model_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "multiscale_models"
GEN = "run_feature_ablation/1.0.0"
SEED = 20261126
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
POLAR = (REPO_ROOT / "outputs" / "b740_expansion" / "molecular_descriptors"
         / "polarizability_tensor.csv")
CONF = (REPO_ROOT / "outputs" / "b740_expansion" / "conformer_analysis"
        / "conformer_entropy.csv")
THERMO = (REPO_ROOT / "outputs" / "b740_expansion" / "thermodynamic_properties"
          / "liquid_thermodynamic_indices.csv")

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
      "formal_charge", "n_rings", "n_rotatable", "fraction_csp3",
      "n_aromatic_atoms", "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X1 = ["dipole_D_v7", "homo_lumo_gap_ev_v7", "polarizability_au_v7",
      "alpha_anisotropy_ratio"]
X2 = ["C_mu", "S_conf_J_mol_K", "N_eff"]
X3 = ["n_D", "molar_volume_cm3_mol", "rho_HBD_per_cm3", "rho_HBA_per_cm3",
      "lippert_mataga_delta_f"]


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def standardise(X):
    m = X.mean(axis=0)
    s = X.std(axis=0, ddof=1)
    s[s == 0] = 1.0
    return (X - m) / s, m, s


def ridge(Z, y, lam):
    p = Z.shape[1]
    return np.linalg.solve(Z.T @ Z + lam * np.eye(p), Z.T @ y)


def fit_predict(Xtr, ytr, Xte, lam):
    Z, m, s = standardise(Xtr)
    b = ridge(Z, ytr, lam)
    return float(np.mean(ytr)) + ((Xte - m) / s) @ b


def choose_lambda(X, y, seed=SEED, k=5):
    n = len(y)
    if n < k * 3:
        return 1.0
    idx = np.arange(n).tolist()
    random.Random(seed).shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [j for g in range(k) if g != f for j in folds[g]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict(X[tr], y[tr], X[te], lam)
            errs.extend(np.abs(p - y[te]).tolist())
        if errs:
            m = sum(errs) / len(errs)
            if m < best:
                best, bl = m, lam
    return bl


def loo(X, y, seed=SEED):
    n = len(y)
    out = np.empty(n)
    for h in range(n):
        mask = np.arange(n) != h
        lam = choose_lambda(X[mask], y[mask], seed)
        out[h] = fit_predict(X[mask], y[mask], X[h:h + 1], lam)[0]
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    polar = {}
    for r in load_csv(POLAR):
        if r["layer"] == "opt" or not polar:
            polar.setdefault(r["inchikey"], r)
    conf = {r["inchikey"]: r for r in load_csv(CONF)}
    thermo = {r["inchikey"]: r for r in load_csv(THERMO)}

    # assemble a merged record per molecule
    merged = {}
    for ik, d in desc.items():
        eps = fnum(d.get("epsilon"))
        if eps is None:
            continue
        rec = {"inchikey": ik, "epsilon": eps,
               "family": d.get("family", ""), "name": d.get("name", "")}
        ok = True
        for c in X0:
            v = fnum(d.get(c))
            if v is None:
                ok = False
                break
            rec[c] = v
        if not ok:
            continue
        for c in X1[:3]:
            v = fnum(d.get(c))
            if v is None and c == "homo_lumo_gap_ev_v7":
                v = fnum(d.get("homo_lumo_gap_ev"))
            rec[c] = v if v is not None else None
        # X1 anisotropy from the tensor table
        p = polar.get(ik, {})
        rec["alpha_anisotropy_ratio"] = fnum(p.get("anisotropy_ratio"))
        # X2 from conformer entropy
        cf = conf.get(ik, {})
        rec["C_mu"] = fnum(cf.get("C_mu"))
        rec["S_conf_J_mol_K"] = fnum(cf.get("S_conf_J_mol_K"))
        rec["N_eff"] = fnum(cf.get("N_eff"))
        # X3 from thermodynamic indices
        th = thermo.get(ik, {})
        rec["n_D"] = fnum(th.get("n_D"))
        rec["molar_volume_cm3_mol"] = fnum(th.get("molar_volume_cm3_mol"))
        rec["rho_HBD_per_cm3"] = fnum(th.get("rho_HBD_per_cm3"))
        rec["rho_HBA_per_cm3"] = fnum(th.get("rho_HBA_per_cm3"))
        rec["lippert_mataga_delta_f"] = fnum(th.get("lippert_mataga_delta_f"))
        merged[ik] = rec

    def subset(cols):
        kept = []
        for ik, r in merged.items():
            if all(r.get(c) is not None for c in cols):
                kept.append(r)
        return kept

    def run(rows, cols, label, min_n=10):
        """Fit and LOO-evaluate one configuration.

        min_n is 10 rather than 20: a panel with 10-19 molecules can still support a
        PAIRED within-panel comparison (same molecules, same folds on both arms), and
        dropping those panels would hide the only evidence available for X2/X3.
        Every such row is labelled with its n so the reader sees the power.
        """
        if len(rows) < min_n:
            return {"config": label, "n": len(rows), "status": "TOO_FEW"}
        X = np.asarray([[r[c] for c in cols] for r in rows], float)
        y = np.asarray([r["epsilon"] for r in rows], float)
        p = loo(X, y)
        err = np.abs(p - y)
        mae = float(np.mean(err))
        yb = float(np.mean(y))
        sst = float(np.sum((y - yb) ** 2))
        r2 = 1.0 - float(np.sum((p - y) ** 2)) / sst if sst else float("nan")
        return {"config": label, "n": len(rows), "n_features": len(cols),
                "mae": round(mae, 4), "r2": round(r2, 4),
                "constant_baseline_mae": round(float(np.mean(np.abs(y - yb))), 4),
                "status": "OK",
                "power": "INADEQUATE" if len(rows) < 30 else
                         "LIMITED" if len(rows) < 100 else "ADEQUATE"}

    # (a) full cohort: X0 vs X0+X1
    rows_a = subset(X0 + X1[:3])
    full = [run(rows_a, X0, "X0_structure"),
            run(rows_a, X0 + X1[:3], "X0+X1_single_molecule_electronic")]

    # (b) strict common subset across ALL layers -- usually tiny, reported as such
    all_cols = X0 + X1[:3] + X2 + X3
    rows_b = subset(all_cols)
    common = []
    if len(rows_b) >= 20:
        common = [
            run(rows_b, X0, "X0_structure"),
            run(rows_b, X0 + X1[:3], "X0+X1"),
            run(rows_b, X0 + X1[:3] + X2, "X0+X1+X2_conformer"),
            run(rows_b, all_cols, "X0+X1+X2+X3_liquid"),
        ]

    # (c) PAIRED STAIRCASE: each layer is added on the largest set that HAS it,
    #     and every row carries its own n. This is the informative comparison when
    #     layers do not coexist on many molecules: within each panel the molecule
    #     set and folds are identical, so the delta is a clean paired estimate.
    staircase = []
    # X2 panel: conformer molecules that also have X0+X1 and epsilon
    rows_x2 = subset(X0 + X1[:3] + X2)
    if len(rows_x2) >= 10:
        staircase += [
            {**run(rows_x2, X0 + X1[:3], "X0+X1"), "panel": "X2_PANEL"},
            {**run(rows_x2, X0 + X1[:3] + X2, "X0+X1+X2"), "panel": "X2_PANEL"},
        ]
    # X3 panel: molecules with the liquid-property block
    rows_x3 = subset(X0 + X1[:3] + X3)
    if len(rows_x3) >= 10:
        staircase += [
            {**run(rows_x3, X0 + X1[:3], "X0+X1"), "panel": "X3_PANEL"},
            {**run(rows_x3, X0 + X1[:3] + X3, "X0+X1+X3"), "panel": "X3_PANEL"},
        ]

    with (OUT / "multiscale_ablation.csv").open("w", newline="",
                                                encoding="utf-8") as f:
        rows = [{"set": "FULL_COHORT", **r} for r in full] + \
               [{"set": "COMMON_SUBSET", **r} for r in common]
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def gain(a, b):
        if a.get("status") != "OK" or b.get("status") != "OK":
            return None
        return round(a["mae"] - b["mae"], 4)

    def _gain_pair(lst, i, j):
        if len(lst) <= j:
            return None
        a, b = lst[i], lst[j]
        if a.get("status") != "OK" or b.get("status") != "OK":
            return None
        return round(a["mae"] - b["mae"], 4)

    doc = {
        "schema": "b740.multiscale_models/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "layers": {
            "X0": X0, "X1": X1, "X2": X2, "X3": X3,
        },
        "coverage": {
            "total_with_epsilon": len(merged),
            "with_X0_X1": len(rows_a),
            "with_all_layers": len(rows_b),
            "X2_available": sum(1 for r in merged.values()
                                if r.get("N_eff") is not None),
            "X3_available": sum(1 for r in merged.values()
                                if r.get("lippert_mataga_delta_f") is not None),
        },
        "full_cohort": full,
        "common_subset": common,
        "paired_staircase": staircase,
        "ablation_gains": {
            "FULL_X0_to_X0X1": gain(full[0], full[1]) if len(full) == 2 else None,
            "COMMON_X0_to_X0X1": gain(common[0], common[1]) if len(common) > 1 else None,
            "COMMON_X0X1_to_X0X1X2": gain(common[1], common[2]) if len(common) > 2 else None,
            "COMMON_X0X1X2_to_all": gain(common[2], common[3]) if len(common) > 3 else None,
        },
        "paired_staircase_gains": {
            "X2_panel_n": len(rows_x2),
            "X2_panel_gain": _gain_pair(staircase, 0, 1),
            "X3_panel_n": len(rows_x3),
            "X3_panel_gain": _gain_pair(staircase, 2, 3),
        },
        "selection_bias_warning": (
            "the COMMON_SUBSET has far fewer molecules than the FULL_COHORT. Its MAE "
            "is NOT comparable to the full-cohort MAE, and its apparent improvement "
            "must not be quoted as a gain for the whole dataset. Only the WITHIN-set "
            "differences are meaningful."
        ),
        "verdict": {},
    }

    g = doc["ablation_gains"]
    doc["verdict"] = {
        "single_molecule_electronic_helps": (g["FULL_X0_to_X0X1"] is not None
                                             and g["FULL_X0_to_X0X1"] > 0),
        "conformer_layer_helps_on_subset": (
            doc["paired_staircase_gains"]["X2_panel_gain"] is not None
            and doc["paired_staircase_gains"]["X2_panel_gain"] > 0),
        "liquid_property_layer_helps_on_subset": (
            doc["paired_staircase_gains"]["X3_panel_gain"] is not None
            and doc["paired_staircase_gains"]["X3_panel_gain"] > 0),
        "n_common_subset": len(rows_b),
        "statistical_power": ("INADEQUATE" if len(rows_b) < 50 else "LIMITED"
                              if len(rows_b) < 150 else "ADEQUATE"),
    }
    (OUT / "multiscale_model_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'multiscale_ablation.csv'}")
    print(f"Wrote {OUT / 'multiscale_model_summary.json'}")
    print(f"coverage: {doc['coverage']}")
    print()
    print("FULL COHORT:")
    for r in full:
        if r.get("status") == "OK":
            print(f"  {r['config']:34s} n={r['n']:4d} MAE={r['mae']:7.4f} R2={r['r2']:+.3f}")
    print("COMMON SUBSET (all layers):")
    for r in common:
        if r.get("status") == "OK":
            print(f"  {r['config']:34s} n={r['n']:4d} MAE={r['mae']:7.4f} R2={r['r2']:+.3f}")
    print("PAIRED STAIRCASE:")
    for r in staircase:
        if r.get("status") == "OK":
            print(f"  [{r.get('panel',''):9s}] {r['config']:20s} n={r['n']:4d} "
                  f"MAE={r['mae']:7.4f} R2={r['r2']:+.3f}")
    print("staircase gains:", json.dumps(doc["paired_staircase_gains"], indent=2))
    print()
    print("gains:", json.dumps(doc["ablation_gains"], indent=2))
    print("verdict:", json.dumps(doc["verdict"], indent=2))


if __name__ == "__main__":
    main()
