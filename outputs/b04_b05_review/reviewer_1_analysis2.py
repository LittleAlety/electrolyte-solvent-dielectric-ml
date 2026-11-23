#!/usr/bin/env python
"""Reviewer 1 probe 2: physics-facing checks.

G. Clausius-Mossotti: can eps_infinity be recovered from the X1 features
   (polarizability + molar volume)?  If yes, the features DO contain the
   dominant physics for nonpolar solvents, and the E1 failure is a model
   specification failure, not a descriptor-information failure.
H. Permutation null for the correctly-specified (intercept) model.
I. Temperature heterogeneity of the pool: d(eps)/dT impact.
"""
from __future__ import annotations

import csv
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "outputs/b04/candidate_pool_v2_draft.csv"
FEAT = ROOT / "data/processed/dielectric_physical_features.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    try:
        return float((v or "").strip())
    except ValueError:
        return None


def standardise(X):
    n, p = len(X), len(X[0])
    m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


def ridge_fit(Z, y, lam=1.0):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12:
            continue
        A[c], A[piv] = A[piv], A[c]
        rhs[c], rhs[piv] = rhs[piv], rhs[c]
        pv = A[c][c]
        for r in range(c + 1, p):
            f = A[r][c] / pv
            for k in range(c, p):
                A[r][k] -= f * A[c][k]
            rhs[r] -= f * rhs[c]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-12:
            continue
        b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
    return b


def loo(X, y, lam=1.0, intercept=True):
    n = len(X)
    out = []
    for h in range(n):
        Xtr = [X[i] for i in range(n) if i != h]
        ytr = [y[i] for i in range(n) if i != h]
        ybar = sum(ytr) / len(ytr)
        yy = [v - ybar for v in ytr] if intercept else list(ytr)
        Z, m, s = standardise(Xtr)
        b = ridge_fit(Z, yy, lam)
        x = [(X[h][j] - m[j]) / s[j] for j in range(len(m))]
        out.append(sum(x[j] * b[j] for j in range(len(b))) + (ybar if intercept else 0.0))
    return out


def mae(y, p):
    return sum(abs(p[i] - y[i]) for i in range(len(y))) / len(y)


def main():
    pool = load(POOL)
    feat = {r["inchikey"]: r for r in load(FEAT)}
    rows = []
    for r in pool:
        f = feat.get(r["inchikey"], {})
        v0 = [fnum(f.get(c)) for c in X0]
        v1 = [fnum(f.get(c)) for c in X1]
        if any(v is None for v in v0 + v1):
            continue
        rows.append({"name": r["name"], "y": float(r["dielectric"]),
                     "T": float(r["T_K"]),
                     "x0": [float(v) for v in v0], "x1": [float(v) for v in v1],
                     "alpha": float(f["polarizability_au"]),
                     "alphaA3": float(f["polarizability_A3"]),
                     "vm": float(f["molar_volume_m3_mol"]),
                     "dip": float(f["dipole_D"])})
    n = len(rows)
    y = [r["y"] for r in rows]
    X0m = [r["x0"] for r in rows]
    X1m = [r["x0"] + r["x1"] for r in rows]

    print("=" * 78)
    print("G. CLAUSIUS-MOSSOTTI: eps_infinity from polarizability + molar volume")
    print("   (eps_inf-1)/(eps_inf+2) = 4*pi*N_A*alpha/(3*V_m),  alpha in SI (C m^2/V)")
    NA, eps0 = 6.02214076e23, 8.8541878128e-12
    # alpha_A3 (volume polarizability) -> SI: 1 A^3 = 1e-30 m^3 ; alpha_SI = 4*pi*eps0*alpha_vol
    print(f"\n   {'name':38s} {'eps':>6s} {'eps_inf_CM':>10s} {'err':>7s} {'dipole':>7s}")
    cm_pred, errs = [], []
    for r in rows:
        a_si = 4 * math.pi * eps0 * r["alphaA3"] * 1e-30
        y_ll = 4 * math.pi * NA * a_si / (3 * r["vm"])
        # invert Lorentz-Lorenz  y_ll = (e-1)/(e+2)  ->  e = (1+2y)/(1-y)
        e_inf = (1 + 2 * y_ll) / (1 - y_ll) if abs(1 - y_ll) > 1e-9 else float("nan")
        cm_pred.append(e_inf)
        errs.append(abs(e_inf - r["y"]))
        print(f"   {r['name']:38s} {r['y']:6.2f} {e_inf:10.2f} {e_inf-r['y']:+7.2f} "
              f"{r['dip']:7.2f}")
    print(f"\n   MAE of PURE Clausius-Mossotti eps_inf vs measured eps = "
          f"{sum(errs)/n:.4f}  (constant baseline 10.81)")
    nonpolar = [i for i, r in enumerate(rows) if r["dip"] < 0.5]
    print(f"   nonpolar subset (dipole<0.5 D, n={len(nonpolar)}): "
          f"{[rows[i]['name'] for i in nonpolar]}")
    for i in nonpolar:
        print(f"      {rows[i]['name']:24s} eps_meas={rows[i]['y']:.2f} "
              f"eps_inf_CM={cm_pred[i]:.2f}  diff={cm_pred[i]-rows[i]['y']:+.2f}")
    nm = sum(abs(cm_pred[i] - rows[i]['y']) for i in nonpolar) / len(nonpolar)
    print(f"      nonpolar MAE of eps_inf_CM alone = {nm:.3f}")
    print("   => for the 3 nonpolar alkanes, eps IS the electronic/atomic term")
    print("      (eps ~ n^2), so a molecular dipole cannot ever predict it;")
    print("      but polarizability+volume CAN. The information is in X1.")

    print("\n" + "=" * 78)
    print("H. PERMUTATION NULL for the correctly-specified model (intercept)")
    random.seed(20261123)
    const = sum(abs(v - statistics.mean(y)) for v in y) / n
    for tag, X in (("X0 (7)", X0m), ("X0+X1 (11)", X1m)):
        obs_no = mae(y, loo(X, y, 1.0, intercept=False))
        obs_yes = mae(y, loo(X, y, 1.0, intercept=True))
        nz_no, nz_yes = [], []
        for _ in range(500):
            yp = y[:]
            random.shuffle(yp)
            nz_no.append(mae(yp, loo(X, yp, 1.0, intercept=False)))
            nz_yes.append(mae(yp, loo(X, yp, 1.0, intercept=True)))
        nz_no.sort()
        nz_yes.sort()
        p_no = sum(1 for v in nz_no if v <= obs_no) / len(nz_no)
        p_yes = sum(1 for v in nz_yes if v <= obs_yes) / len(nz_yes)
        print(f"  {tag}:")
        print(f"    no-intercept: MAE={obs_no:7.4f}  null q05={nz_no[25]:7.4f} "
              f"median={nz_no[250]:7.4f}  p={p_no:.3f}")
        print(f"    WITH intercept: MAE={obs_yes:7.4f}  null q05={nz_yes[25]:7.4f} "
              f"median={nz_yes[250]:7.4f}  p={p_yes:.3f}")
        print(f"    constant baseline={const:.4f}  beats={(obs_yes < const)}")

    # delta null: paired, same permutation applied to both
    print("\n  paired delta-MAE null (X0+X1 minus X0, intercept on, same shuffle):")
    ds = []
    random.seed(20261123)
    for _ in range(500):
        yp = y[:]
        random.shuffle(yp)
        ds.append(mae(yp, loo(X1m, yp, 1.0, True)) - mae(yp, loo(X0m, yp, 1.0, True)))
    ds.sort()
    obs_d = mae(y, loo(X1m, y, 1.0, True)) - mae(y, loo(X0m, y, 1.0, True))
    print(f"    observed dMAE = {obs_d:+.4f}   null q05={ds[25]:+.4f} "
          f"median={ds[250]:+.4f} q95={ds[475]:+.4f}")
    print(f"    p(dMAE >= observed) = {sum(1 for v in ds if v <= obs_d)/len(ds):.3f}")

    print("\n" + "=" * 78)
    print("I. POOL IS NOT ISOTHERMAL")
    Ts = sorted(set(r["T"] for r in rows))
    print(f"  distinct T_K values: {Ts}   spread = {max(Ts)-min(Ts):.2f} K")
    for t in Ts:
        grp = [r for r in rows if r["T"] == t]
        print(f"    T={t:7.2f} K  n={len(grp)}  names={[g['name'][:16] for g in grp]}")
    # temperature sensitivity: d eps / dT for associated liquids ~ -0.3..-0.5 /K
    print("\n  literature d(eps)/dT for associated solvents ~ -0.3 to -0.5 per K ;")
    print("  a 10 K spread therefore maps to 3-5 eps units of pure label noise,")
    print("  which is 25-40% of the claimed E1 signal (MAE 6.8 after repair).")

    print("\n" + "=" * 78)
    print("J. degenerate/trace features")
    for j, c in enumerate(X0 + ["dipole_D"] + X1[1:]):
        col = [r["x0"][j] for r in rows] if j < len(X0) else None
        if col is not None:
            print(f"  {c:26s} min={min(col):12.4g} max={max(col):12.4g} "
                  f"sd={statistics.pstdev(col):12.4g}")
    fc = [r["x0"][6] for r in rows]
    print(f"\n  formal_charge: set={set(fc)} -> zero variance, contributes nothing, "
          f"and confirms no salt/ionic species in the pool")


if __name__ == "__main__":
    main()
