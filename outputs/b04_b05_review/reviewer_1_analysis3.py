#!/usr/bin/env python
"""Reviewer 1 probe 3: the decisive mechanism checks.

K. Feature collinearity / effective rank of X0 and X1.
L. Physical admissibility: eps >= 1 is a hard bound (Kramers-Kronig / stability).
M. Clausius-Mossotti with REAL molar volumes for the nonpolar subset.
N. E6 noise ladder: selection probabilities -> what actually changes.
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
                     "T": float(r["T_K"]), "f": {c: float(f[c]) for c in X0 + X1}})
    n = len(rows)
    y = [r["y"] for r in rows]

    print("=" * 78)
    print("K. FEATURE COLLINEARITY  (n=22, so effective rank is what matters)")
    NA = 6.02214076e23
    print("\n  exact linear relationships found:")
    r1 = [r["f"]["molar_volume_m3_mol"] / r["f"]["molecular_volume_A3"] for r in rows]
    print(f"    molar_volume_m3_mol / molecular_volume_A3 = {min(r1):.6e}..{max(r1):.6e}")
    print(f"    N_A                                                = {NA:.6e}")
    print(f"    -> ratio is constant = N_A to {abs(statistics.mean(r1)-NA)/NA*1e6:.3f} ppm")
    print("    => molar_volume_m3_mol is EXACTLY molecular_volume_A3 * N_A")
    print("       i.e. a van der Waals cavity volume, NOT the bulk molar volume")
    print("       that enters Clausius-Mossotti / Kirkwood. Two of the seven X0")
    print("       columns carry ONE piece of information.")
    r2 = [r["f"]["polarizability_A3"] / r["f"]["polarizability_au"] for r in rows]
    print(f"\n    polarizability_A3 / polarizability_au = {min(r2):.6f}..{max(r2):.6f}")
    print("    -> constant 0.148184 = 1 bohr^3 in A^3; again the SAME number twice")
    print("       (and the E1 manifest lists X1 as 5 cols; X0+X1 nominal 12 = "
          "effective 9)")

    # packing fraction check: vdW molar volume vs real liquid molar volume
    Vm_lit_cm3 = {"heptane": 146.6, "nonane": 179.0, "methylcyclohexane": 128.0,
                  "cyclohexanol": 106.0, "1,2-propanediol": 73.2,
                  "dimethyl carbonate": 84.7, "diethyl carbonate": 121.0,
                  "sulfolane": 95.4, "acetic acid": 57.5,
                  "1-methylimidazole": 79.0, "triethanolamine": 133.0}
    print("\n  vdW-molar volume vs literature liquid molar volume (packing):")
    for nm, vm in Vm_lit_cm3.items():
        rr = next((r for r in rows if r["name"] == nm), None)
        if rr is None:
            continue
        v_vdw = rr["f"]["molar_volume_m3_mol"] * 1e6
        print(f"    {nm:24s} vdW={v_vdw:7.1f} cm3/mol  lit Vm={vm:7.1f}  "
              f"packing={v_vdw/vm:.2f}")

    print("\n" + "=" * 78)
    print("L. PHYSICAL ADMISSIBILITY: eps >= 1 is a hard bound")
    e1 = load(ROOT / "outputs/b05/E1_structure_vs_electronic/predictions_loo.csv")
    for model in ("X0_structure_only", "X0_plus_X1_electronic"):
        pr = [float(r["y_pred"]) for r in e1 if r["model"] == model]
        n_neg = sum(1 for v in pr if v < 0)
        n_b1 = sum(1 for v in pr if v < 1.0)
        print(f"  {model:24s}: {n_neg}/22 predictions < 0 ; {n_b1}/22 < 1.0")
        print(f"      min={min(pr):+8.3f}  max={max(pr):+8.3f}")
    e4 = load(ROOT / "outputs/b05/E4_domain_generalization/structural_distance_ood.csv")
    pr4 = [float(r["y_pred"]) for r in e4]
    print(f"  E4 (same model)          : {sum(1 for v in pr4 if v<0)}/22 < 0 ; "
          f"{sum(1 for v in pr4 if v<1.0)}/22 < 1.0")
    print("  eps < 1 violates passivity/causality (Kramers-Kronig) for a")
    print("  non-magnetic liquid. A model emitting eps = -20.6 is not making a")
    print("  scientific prediction about a liquid; it is emitting an unphysical")
    print("  number because the regression has NO INTERCEPT (fit through the")
    print("  origin of standardised features) and no output constraint.")

    print("\n" + "=" * 78)
    print("M. CLAUSIUS-MOSSOTTI with REAL liquid molar volumes")
    eps0 = 8.8541878128e-12
    print("   (e_inf-1)/(e_inf+2) = N_A*alpha_SI/(3*eps0*V_m);  alpha_SI=4*pi*eps0*alpha_A3*1e-30")
    print(f"\n   {'name':24s} {'eps_meas':>8s} {'eps_inf':>8s} {'dip':>6s} {'err':>7s}")
    nonp = []
    for nm, vm_cm3 in Vm_lit_cm3.items():
        rr = next((r for r in rows if r["name"] == nm), None)
        if rr is None:
            continue
        a_vol = rr["f"]["polarizability_A3"]
        a_si = 4 * math.pi * eps0 * a_vol * 1e-30
        vm = vm_cm3 * 1e-6
        yll = NA * a_si / (3 * eps0 * vm)
        e_inf = (1 + 2 * yll) / (1 - yll)
        d = rr["f"]["dipole_D"]
        print(f"   {nm:24s} {rr['y']:8.2f} {e_inf:8.2f} {d:6.2f} {e_inf-rr['y']:+7.2f}")
        if d < 0.5:
            nonp.append(abs(e_inf - rr["y"]))
    if nonp:
        print(f"\n   nonpolar (dipole<0.5 D) MAE of eps_inf from polarizability alone "
              f"= {statistics.mean(nonp):.3f}")
    print("   => for the alkanes eps IS the electronic term and X1 contains it.")
    print("      The 3 alkanes (eps 1.93-2.01) are PREDICTED at -20.6/-14.9/-20.6.")
    print("      Any model that maps polarizability to eps monotonically cannot")
    print("      produce that; the failure is specification, not information.")

    print("\n" + "=" * 78)
    print("N. E6 NOISE LADDER: what actually changes is the top-of-ranking lottery")
    # rebuild the shipped LOO predictor exactly
    def standardise(X):
        n_, p = len(X), len(X[0])
        m = [sum(X[i][j] for i in range(n_)) / n_ for j in range(p)]
        s = []
        for j in range(p):
            v = sum((X[i][j] - m[j]) ** 2 for i in range(n_)) / max(n_ - 1, 1)
            s.append(math.sqrt(v) if v > 0 else 1.0)
        return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n_)], m, s

    def ridge_fit(Z, yy, lam=1.0):
        n_, p = len(Z), len(Z[0])
        A = [[sum(Z[i][a] * Z[i][b] for i in range(n_)) + (lam if a == b else 0.0)
              for b in range(p)] for a in range(p)]
        rhs = [sum(Z[i][a] * yy[i] for i in range(n_)) for a in range(p)]
        for c in range(p):
            piv = max(range(c, p), key=lambda r: abs(A[r][c]))
            if abs(A[piv][c]) < 1e-12:
                continue
            A[c], A[piv] = A[piv], A[c]
            rhs[c], rhs[piv] = rhs[piv], rhs[c]
            pv = A[c][c]
            for r in range(c + 1, p):
                f_ = A[r][c] / pv
                for k in range(c, p):
                    A[r][k] -= f_ * A[c][k]
                rhs[r] -= f_ * rhs[c]
        b = [0.0] * p
        for r in range(p - 1, -1, -1):
            if abs(A[r][r]) < 1e-12:
                continue
            b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
        return b

    cols = X0 + X1
    Xm = [[r["f"][c] for c in cols] for r in rows]
    pred = []
    for h in range(n):
        Xtr = [Xm[i] for i in range(n) if i != h]
        ytr = [y[i] for i in range(n) if i != h]
        Z, m, s = standardise(Xtr)
        b = ridge_fit(Z, ytr, 1.0)
        x = [(Xm[h][j] - m[j]) / s[j] for j in range(len(m))]
        pred.append(sum(x[j] * b[j] for j in range(len(b))))
    k = 3
    order = sorted(range(n), key=lambda i: -y[i])
    obs = statistics.mean(y[i] for i in order[:k])
    print(f"  oracle top{k} mean = {obs:.3f}; pool mean = {statistics.mean(y):.3f}")
    names = [r["name"] for r in rows]
    sr = sorted(range(n), key=lambda i: -pred[i])
    print("\n  rank-by-prediction, true eps, and selection probability at each sigma:")
    rr = random.Random(20261123)
    sigmas = (0, 4, 8, 16)
    selprob = {s: [0] * n for s in sigmas}
    T = 3000
    for s in sigmas:
        for _ in range(T):
            nz = [pred[i] + rr.gauss(0, s) for i in range(n)]
            for i in sorted(range(n), key=lambda z: -nz[z])[:k]:
                selprob[s][i] += 1
    hdr = "  ".join(f"P(s={s})" for s in sigmas)
    print(f"  {'rank':>4s} {'name':30s} {'eps':>6s}  {hdr}")
    for rk, i in enumerate(sr, 1):
        ps = "  ".join(f"{selprob[s][i]/T:6.2f}" for s in sigmas)
        print(f"  {rk:4d} {names[i][:30]:30s} {y[i]:6.2f}  {ps}")
    print("\n  reading:")
    print("   - sulfolane (eps 44, the oracle #1) is predicted #1 and is picked")
    print("     almost always at every sigma -> the model DOES find the best one.")
    print("   - ranks 2-3 have true eps BELOW the pool mean (13.87, 15.48), while")
    print("     ranks 4-6 have true eps 25.94/39.78/29.71. The top-3 set is")
    print("     internally INVERTED at ranks 2-6.")
    print("   - moderate noise shuffles ranks 2-6, so 2 of 3 slots are drawn from a")
    print("     group whose median eps is much higher -> regret falls.")
    print("   - large noise (sigma>=16) eventually destroys the sulfolane pick and")
    print("     regret climbs back to the random baseline (~20.6).")
    print("   => non-monotone, interior optimum. This is a LOTTERY among near-tied")
    print("      candidates, NOT global anti-correlation (rho = +0.755).")


if __name__ == "__main__":
    main()
