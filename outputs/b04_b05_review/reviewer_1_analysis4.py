#!/usr/bin/env python
"""Reviewer 1 probe 4: exact reproduction of E1's 12-feature model and the
E1-vs-E6 feature-set discrepancy, plus the corrected specification."""
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
X1_12 = ["dipole_D", "polarizability_au", "polarizability_A3",
         "homo_lumo_gap_ev", "total_energy_hartree"]
X1_11 = ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]


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


def loo(X, y, lam=1.0, intercept=False):
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


def mets(y, p):
    n = len(y)
    e = [p[i] - y[i] for i in range(n)]
    ybar = sum(y) / n
    ss = sum((v - ybar) ** 2 for v in y)
    return {"mae": sum(abs(v) for v in e) / n, "bias": sum(e) / n,
            "r2": 1 - sum(v * v for v in e) / ss}


def rank(v):
    n = len(v)
    o = sorted(range(n), key=lambda i: v[i])
    rk = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[o[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return rk


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    return (sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
            / math.sqrt(sum((v - ma) ** 2 for v in ra) * sum((v - mb) ** 2 for v in rb)))


def main():
    pool = load(POOL)
    feat = {r["inchikey"]: r for r in load(FEAT)}
    rows, y = [], []
    for r in pool:
        f = feat.get(r["inchikey"], {})
        allc = X0 + X1_12
        vals = [fnum(f.get(c)) for c in allc]
        if any(v is None for v in vals):
            continue
        rows.append({c: float(f[c]) for c in allc})
        y.append(float(r["dielectric"]))
    n = len(rows)
    X0m = [[r[c] for c in X0] for r in rows]
    X11 = [[r[c] for c in X0 + X1_11] for r in rows]
    X12 = [[r[c] for c in X0 + X1_12] for r in rows]

    print("=" * 78)
    print("EXACT REPRODUCTION CHECK vs shipped metrics.csv")
    print(f"  constant baseline: recomputed "
          f"{sum(abs(v - statistics.mean(y)) for v in y)/n:.6f}  (shipped 10.806223)")
    for tag, X, shipped in (("X0 (7)", X0m, 17.446507),
                            ("X0+X1 11feat", X11, 17.237500),
                            ("X0+X1 12feat", X12, 17.286655)):
        p = loo(X, y, 1.0, intercept=False)
        m = mets(y, p)
        print(f"  {tag:14s} reproduced MAE={m['mae']:9.6f}  shipped={shipped:9.6f}  "
              f"match={abs(m['mae']-shipped)<0.002}   bias={m['bias']:+9.4f} "
              f"mean(pred)={statistics.mean(p):+8.4f}")

    print("\n  => E1 used 12 features (incl. total_energy_hartree);")
    print("     E6 used 11 (no total_energy_hartree). The two 'same model'")
    print("     numbers therefore differ (17.2867 vs 17.2375) despite both")
    print("     reporting the same feature description in model_input_manifest.")

    print("\n" + "=" * 78)
    print("SPECIFICATION REPAIR: add the intercept (SAME features, SAME LOO)")
    out = {}
    for tag, X, lam in (("X0 (7)", X0m, 1.0),
                        ("X0+X1 12feat", X12, 1.0)):
        p0 = loo(X, y, 1.0, intercept=False)
        p1 = loo(X, y, 1.0, intercept=True)
        m0, m1 = mets(y, p0), mets(y, p1)
        out[tag] = (p0, p1, m0, m1)
        print(f"\n  {tag}")
        print(f"    as shipped (no intercept): MAE={m0['mae']:7.4f} bias={m0['bias']:+8.3f} "
              f"R2={m0['r2']:+7.3f} rho={spearman(p0, y):+.3f} min={min(p0):+7.2f}")
        print(f"    with intercept          : MAE={m1['mae']:7.4f} bias={m1['bias']:+8.3f} "
              f"R2={m1['r2']:+7.3f} rho={spearman(p1, y):+.3f} min={min(p1):+7.2f}")
        print(f"    constant baseline       : MAE={sum(abs(v-statistics.mean(y)) for v in y)/n:7.4f}")
        print(f"    beats constant? shipped={m0['mae'] < 10.806223}  "
              f"repaired={m1['mae'] < 10.806223}")

    # lambda sensitivity: is the repair robust to the arbitrary lam=1.0?
    print("\n  LAMBDA SENSITIVITY of the repaired model (lam was hard-coded 1.0):")
    for lam in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0):
        p = loo(X12, y, lam, intercept=True)
        print(f"    lam={lam:6.1f}  MAE={mets(y, p)['mae']:7.4f}  rho={spearman(p, y):+.3f}")

    print("\n" + "=" * 78)
    print("PERMUTATION NULL of the repaired model (500 shuffles, paired)")
    random.seed(20261123)
    obs12 = mets(y, out["X0+X1 12feat"][1])["mae"]
    obs0 = mets(y, out["X0 (7)"][1])["mae"]
    nz12, nz0, dlt = [], [], []
    for _ in range(500):
        yp = y[:]
        random.shuffle(yp)
        a = mets(yp, loo(X0m, yp, 1.0, True))["mae"]
        b = mets(yp, loo(X12, yp, 1.0, True))["mae"]
        nz0.append(a)
        nz12.append(b)
        dlt.append(b - a)
    nz12.sort(); nz0.sort(); dlt.sort()
    print(f"  X0     obs MAE={obs0:7.4f}  null q05={nz0[25]:7.4f} "
          f"median={nz0[250]:7.4f}  p={sum(1 for v in nz0 if v<=obs0)/500:.3f}")
    print(f"  X0+X1  obs MAE={obs12:7.4f}  null q05={nz12[25]:7.4f} "
          f"median={nz12[250]:7.4f}  p={sum(1 for v in nz12 if v<=obs12)/500:.3f}")
    print(f"  paired dMAE obs={obs12-obs0:+.4f}  null q05={dlt[25]:+.4f} "
          f"median={dlt[250]:+.4f} q95={dlt[475]:+.4f}  "
          f"p={sum(1 for v in dlt if v<=obs12-obs0)/500:.3f}")

    print("\n" + "=" * 78)
    print("E6 SCREENING under the repaired model")
    pfix = out["X0+X1 12feat"][1]
    k = 3
    order = sorted(range(n), key=lambda i: -y[i])
    mtop = sorted(range(n), key=lambda i: -pfix[i])[:k]
    om = statistics.mean(y[i] for i in order[:k])
    mm = statistics.mean(y[i] for i in mtop)
    print(f"  oracle top{k}={om:.3f}  repaired-model top{k}={mm:.3f}  "
          f"regret={om-mm:.3f}  overlap={len(set(order[:k])&set(mtop))}/{k}")
    print(f"  shipped regret was 13.380 -> repaired regret {om-mm:.3f}")
    rnd = []
    rr = random.Random(20261123)
    for _ in range(2000):
        rnd.append(statistics.mean(y[i] for i in rr.sample(range(n), k)))
    rnd.sort()
    print(f"  random baseline mean={statistics.mean(rnd):.3f} q95={rnd[1900]:.3f}  "
          f"P(random>=repaired)={sum(1 for v in rnd if v>=mm)/len(rnd):.3f}")


if __name__ == "__main__":
    main()
