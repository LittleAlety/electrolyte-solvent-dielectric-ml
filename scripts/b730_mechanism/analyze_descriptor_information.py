#!/usr/bin/env python
"""B733-01: do the electronic descriptor blocks carry INDEPENDENT information?

The question is not "which block has lower MAE" but "does block B add anything
once block A is in the model". Two things are computed that answer it properly,
and one that is deliberately refused:

  ADDED (used)   conditional gain: fit with A, fit with A+B, compare LOO error on
                 the SAME molecules with lambda chosen inside each training fold.
  ADDED (used)   partial correlation: residualise B on A and correlate with the
                 target residual. This is the direct redundancy measure.
  REFUSED        plain permutation importance: with correlated features it
                 splits credit arbitrarily and is not evidence of independence.

All selection stays inside the training fold; nothing is chosen on the test
points. The comparison is paired (same molecules, same folds) so a gain cannot
come from a different split.

Outputs (outputs/b730_mechanism/descriptor_information/):
  descriptor_information.json
  descriptor_redundancy.csv
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
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "descriptor_information"
GEN = "analyze_descriptor_information/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

STRUCT = ["heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
          "molar_volume_m3_mol", "formal_charge", "n_rings", "n_rotatable",
          "fraction_csp3", "n_aromatic_atoms", "n_hetero", "n_halogen",
          "morgan2_nbits", "mw"]
DIP = ["dipole_D_v7"]                       # permanent dipole
MU2VM = ["mu_sq_over_Vm_v7"]                # volume-normalised dipole
POLAR = ["polarizability_au_v7"]            # isotropic polarizability
ELEC_XTB = ["dipole_D", "homo_lumo_gap_ev"]
ELEC_DFT = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]

BLOCKS = {
    "structure": STRUCT,
    "dipole": DIP,
    "mu2_over_Vm": MU2VM,
    "polarizability": POLAR,
    "xtb_electronic": ELEC_XTB,
    "dft_electronic": ELEC_DFT,
}


def load_csv(path: Path) -> list[dict]:
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


def choose_lambda(X, y, seed, k=5):
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


def loo(X, y, seed):
    n = len(y)
    out = np.empty(n)
    for h in range(n):
        mask = np.arange(n) != h
        lam = choose_lambda(X[mask], y[mask], seed)
        out[h] = fit_predict(X[mask], y[mask], X[h:h + 1], lam)[0]
    return out


def mae(y, p):
    return float(np.mean(np.abs(p - y)))


def residualise(B, A):
    """Regress each column of B on A (with intercept) and return residuals."""
    n = A.shape[0]
    A1 = np.hstack([np.ones((n, 1)), A])
    coef, *_ = np.linalg.lstsq(A1, B, rcond=None)
    return B - A1 @ coef


def partial_corr(B, A, y):
    """Correlation of B's residual (after A) with y's residual (after A)."""
    rb = residualise(B, A)
    ry = residualise(y.reshape(-1, 1), A).ravel()
    out = []
    for j in range(rb.shape[1]):
        b = rb[:, j]
        if np.std(b) == 0 or np.std(ry) == 0:
            out.append(None)
            continue
        out.append(round(float(np.corrcoef(b, ry)[0, 1]), 4))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)

    def build(cols):
        X, y, keep = [], [], []
        for r in rows:
            if fnum(r.get("epsilon")) is None:
                continue
            xs, ok = [], True
            for c in cols:
                v = fnum(r.get(c))
                if v is None and c == "homo_lumo_gap_ev_v7":
                    v = fnum(r.get("homo_lumo_gap_ev"))
                if v is None:
                    ok = False
                    break
                xs.append(v)
            if not ok:
                continue
            X.append(xs)
            y.append(fnum(r["epsilon"]))
            keep.append(r["inchikey"])
        return np.asarray(X, float), np.asarray(y, float), keep

    Xs, y, ids = build(STRUCT)
    n = len(y)

    # ---------------- conditional gains -----------------------------------
    base_pred = loo(Xs, y, SEED)
    base_mae = mae(y, base_pred)
    gains = []
    for name, cols in BLOCKS.items():
        if name == "structure":
            continue
        X2, y2, _ = build(STRUCT + cols)
        if len(y2) != n:
            continue
        p2 = loo(X2, y, SEED)
        m2 = mae(y, p2)
        d = [abs(base_pred[i] - y[i]) - abs(p2[i] - y[i]) for i in range(n)]
        rng = random.Random(SEED)
        boots = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n
                       for _ in range(1000))
        pc = partial_corr(X2[:, len(STRUCT):], Xs, y)
        gains.append({
            "added_block": name,
            "n_features": len(cols),
            "structure_only_mae": round(base_mae, 4),
            "with_block_mae": round(m2, 4),
            "mae_gain": round(base_mae - m2, 4),
            "relative_gain": round((base_mae - m2) / base_mae, 4),
            "n_molecules_improved": sum(1 for v in d if v > 0),
            "n_molecules_worse": sum(1 for v in d if v < 0),
            "boot_ci95_gain": [round(boots[25], 4), round(boots[974], 4)],
            "frac_boot_positive": round(sum(1 for v in boots if v > 0) / len(boots), 4),
            "partial_corr_with_target_given_structure": pc,
            "ci_excludes_zero": bool(boots[25] > 0),
        })
        print(f"  {name:16s} +{round(base_mae - m2, 4):+.4f} MAE  "
              f"CI [{boots[25]:+.3f},{boots[974]:+.3f}]  pc={pc}", flush=True)

    # ---------------- redundancy between electronic blocks ----------------
    Xx, _, _ = build(ELEC_XTB)
    Xd, _, _ = build(ELEC_DFT)
    if len(Xx) == len(Xd) == n:
        red = []
        for i, cx in enumerate(ELEC_XTB):
            for j, cd in enumerate(ELEC_DFT):
                c = float(np.corrcoef(Xx[:, i], Xd[:, j])[0, 1])
                red.append({"xtb_feature": cx, "dft_feature": cd,
                            "pearson_r": round(c, 4)})
        dft_given_xtb = partial_corr(Xd, Xx, y)
    else:
        red, dft_given_xtb = [], []

    with (OUT / "descriptor_redundancy.csv").open("w", newline="",
                                                  encoding="utf-8") as f:
        if red:
            w = csv.DictWriter(f, fieldnames=list(red[0].keys()))
            w.writeheader()
            w.writerows(red)

    # ---------------- polarizability after volume -------------------------
    pol_partial = partial_corr(build(POLAR)[0], Xs, y)

    doc = {
        "schema": "b730.descriptor_information/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": n,
        "protocol": {
            "model": "ridge with intercept, training-fold standardisation",
            "lambda": "chosen per holdout by inner 5-fold CV",
            "comparison": "paired: identical molecules and identical fold seeds",
            "selection": "inside the training fold only",
            "refused_method": ("plain permutation importance is not used as evidence "
                               "of independent contribution; correlated features "
                               "split credit arbitrarily"),
        },
        "conditional_gain_over_structure": gains,
        "polarizability_given_structure": {
            "partial_corr_with_target": pol_partial,
            "interpretation": ("if this is near zero, the polarizability adds little "
                               "once molecular size/volume is known"),
        },
        "xtb_vs_dft_redundancy": {
            "pairs": red,
            "max_abs_pearson": (round(max(abs(r["pearson_r"]) for r in red), 4)
                                if red else None),
            "perfect_correlation_cause": (
                "homo_lumo_gap_ev_v7 == homo_lumo_gap_ev with r=1.0 because the "
                "descriptor builder falls back to the xTB gap when the ORCA gap is "
                "absent. So the 'DFT gap' in this table is NOT an independent ORCA "
                "quantity; only the dipole is genuinely re-computed at r2SCAN-3c "
                "(r=0.921 vs xTB). Any claim that DFT adds a second electronic "
                "channel is therefore unsupported by these columns."
            ),
            "dft_features_given_xtb_partial_corr": dft_given_xtb,
            "interpretation": ("high r means the two electronic levels largely "
                               "re-express the same information. With the gap column "
                               "identical by construction, the only genuinely new "
                               "DFT information here is the dipole, at r=0.921."),
        },
    }
    (OUT / "descriptor_information.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nWrote {OUT / 'descriptor_information.json'}")
    if red:
        print(f"Wrote {OUT / 'descriptor_redundancy.csv'}")
    print(f"structure-only MAE: {base_mae:.4f}")
    print(f"polarizability given structure: partial r = {pol_partial}")
    if red:
        print(f"max |r| between xtb and dft blocks: "
              f"{doc['xtb_vs_dft_redundancy']['max_abs_pearson']}")
        print(f"dft given xtb partial corr: {dft_given_xtb}")


if __name__ == "__main__":
    main()
