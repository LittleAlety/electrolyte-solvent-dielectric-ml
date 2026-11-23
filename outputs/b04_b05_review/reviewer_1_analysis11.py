#!/usr/bin/env python
"""Reviewer 1 probe 11: robustness of the E6 noise-ladder reversal.

The shipped ladder used the 11-feature model (no total_energy_hartree).
Question: is 'regret monotone decreasing with noise' robust to
  (a) the seed, and (b) the presence of total_energy_hartree?
If it flips sign across either, the H3 ANTI_CORRELATED verdict is not a
finding, it is sampling noise on a 22-point pool.
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
X11 = ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]
X12 = X11 + ["total_energy_hartree"]


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def standardise(Xm):
    n, p = len(Xm), len(Xm[0])
    m = [sum(Xm[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((Xm[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(Xm[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


def ridge_fit(Z, yy, lam=1.0):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * yy[i] for i in range(n)) for a in range(p)]
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


def loo(Xm, y, intercept):
    n = len(Xm)
    out = []
    for h in range(n):
        Xtr = [Xm[i] for i in range(n) if i != h]
        ytr = [y[i] for i in range(n) if i != h]
        ybar = sum(ytr) / len(ytr)
        yy = [v - ybar for v in ytr] if intercept else list(ytr)
        Z, m, s = standardise(Xtr)
        b = ridge_fit(Z, yy)
        x = [(Xm[h][j] - m[j]) / s[j] for j in range(len(m))]
        out.append(sum(x[j] * b[j] for j in range(len(b))) + (ybar if intercept else 0.0))
    return out


def main():
    pool = load(POOL)
    feat = {r["inchikey"]: r for r in load(FEAT)}
    y = [float(r["dielectric"]) for r in pool]
    n = len(y)
    k = 3
    order = sorted(range(n), key=lambda i: -y[i])
    oracle = statistics.mean(y[i] for i in order[:k])
    rnd_mean = statistics.mean(y)

    print("=" * 78)
    print("AB. NOISE-LADDER REVERSAL: seed robustness, both feature sets")
    for tag, cols in (("11 feat (as shipped in E6)", X0 + X11),
                      ("12 feat (as used in E1/E4)", X0 + X12)):
        Xm = [[float(feat[r["inchikey"]][c]) for c in cols] for r in pool]
        pred = loo(Xm, y, False)
        print(f"\n  {tag}   MAE={statistics.mean([abs(pred[i]-y[i]) for i in range(n)]):.4f}"
              f"  regret(sigma=0)={oracle - statistics.mean(y[i] for i in sorted(range(n), key=lambda i: -pred[i])[:k]):.4f}")
        # for each seed: is regret at sigma=8 < regret at sigma=0 ?
        dec = 0
        deltas = []
        for seed in range(200):
            rr = random.Random(seed)
            def reg(sig):
                ms = []
                for _ in range(100):
                    nz = [pred[i] + rr.gauss(0, sig) for i in range(n)]
                    ms.append(statistics.mean(y[i] for i in sorted(range(n), key=lambda i: -nz[i])[:k]))
                return oracle - statistics.mean(ms)
            r0, r8 = reg(0.0), reg(8.0)
            deltas.append(r8 - r0)
            if r8 < r0 - 0.5:
                dec += 1
        deltas.sort()
        print(f"    over 200 seeds: regret(sigma=8) < regret(sigma=0) in "
              f"{dec}/200 = {dec/200:.0%} of seeds")
        print(f"    delta(regret) median={statistics.median(deltas):+.3f} "
              f"q05={deltas[10]:+.3f} q95={deltas[190]:+.3f}")
        print(f"    -> the effect is {'CONSISTENT' if dec/200 > 0.9 else 'SEED-DEPENDENT'}")

    print("\n" + "=" * 78)
    print("AC. DOES 'REGRET DECREASES' SURVIVE A PHYSICALLY-CLIPPED MODEL?")
    Xm = [[float(feat[r["inchikey"]][c]) for c in X0 + X11] for r in pool]
    pred = [max(v, 1.0) for v in loo(Xm, y, False)]
    print(f"  clip predictions at eps=1 (passivity), 11-feature model:")
    print(f"    MAE={statistics.mean([abs(pred[i]-y[i]) for i in range(n)]):.4f}")
    print(f"    regret(sigma=0)="
          f"{oracle - statistics.mean(y[i] for i in sorted(range(n), key=lambda i: -pred[i])[:k]):.4f}")
    for sigma in (0.0, 4.0, 8.0):
        rr = random.Random(20261123)
        ms = []
        for _ in range(400):
            nz = [pred[i] + rr.gauss(0, sigma) for i in range(n)]
            ms.append(statistics.mean(y[i] for i in sorted(range(n), key=lambda i: -nz[i])[:k]))
        print(f"    sigma={sigma:4.1f} top3={statistics.mean(ms):7.3f} "
              f"regret={oracle-statistics.mean(ms):7.3f}")

    print("\n" + "=" * 78)
    print("AD. THE SHIPPED LADDER IS A ~1-MOLECULE EFFECT")
    print("  With k=3, the Top-3 mean can only change in steps of ~")
    ordered_hi = [y[i] for i in order[:8]]
    print(f"    {[round(v,1) for v in ordered_hi]}")
    print("  Moving ONE slot from rank-3 (15.48) to rank-6 (39.78) changes the")
    print(f"  Top-3 mean by {(39.78-15.48)/3:.2f} eps units.")
    print("  The reported total regret change across the whole ladder is")
    print("  2.82 units -- LESS THAN ONE SLOT SWAP. So the entire 'noise")
    print("  improves screening' effect is a single molecule changing place.")
    print("  That is inside the Monte-Carlo / seed noise of any n=22 experiment.")


if __name__ == "__main__":
    main()
