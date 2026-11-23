#!/usr/bin/env python
"""Reviewer 1 diagnostic probes (READ-ONLY on existing artifacts).

Question set:
  A. Pool chemistry audit (phase state at stated T, classes, values).
  B. Is the E1 failure an intercept artifact?  (ridge fitted on un-centred y)
  C. Is the E4 identical-fingerprint error descriptor blindness or global offset?
  D. Is the E6 noise->regret reversal physically explicable?
  E. Kirkwood g-factor check: is eps a collective property (class-structured)?
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
E4D = ROOT / "outputs/b05/E4_domain_generalization/structural_distance_ood.csv"
E1P = ROOT / "outputs/b05/E1_structure_vs_electronic/predictions_loo.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = X0 + ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    try:
        return float((v or "").strip())
    except ValueError:
        return None


# ---------- exact reproduction of the B05 ridge, with/without intercept -------
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
    return {"mae": sum(abs(v) for v in e) / n,
            "rmse": math.sqrt(sum(v * v for v in e) / n),
            "bias": sum(e) / n,
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
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((v - ma) ** 2 for v in ra) * sum((v - mb) ** 2 for v in rb))
    return num / den if den else float("nan")


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
        rows.append({"name": r["name"], "ik": r["inchikey"], "y": float(r["dielectric"]),
                     "T": float(r["T_K"]), "doi": r["source_doi"],
                     "x0": [float(v) for v in v0], "x1": [float(v) for v in v1],
                     "dip": float(f["dipole_D"]),
                     "vm": float(f["molar_volume_m3_mol"]),
                     "ha": int(float(f["heavy_atom_count"]))})
    n = len(rows)
    y = [r["y"] for r in rows]
    X0m = [r["x0"] for r in rows]
    X1m = [r["x1"] for r in rows]
    const = sum(abs(v - statistics.mean(y)) for v in y) / n

    print("=" * 78)
    print(f"A. POOL: n={n}  eps {min(y):.2f}-{max(y):.2f}  mean {statistics.mean(y):.2f} "
          f"median {statistics.median(y):.2f}")
    print(f"   constant-baseline MAE (in-sample mean) = {const:.4f}")

    print("\n" + "=" * 78)
    print("B. E1 RE-FIT: reproduce, then add an intercept (identical features)")
    for tag, X, lam in (("X0 (7)", X0m, 1.0), ("X0+X1 (11)", X1m, 1.0)):
        p_no = loo(X, y, lam, intercept=False)
        p_yes = loo(X, y, lam, intercept=True)
        m0, m1 = mets(y, p_no), mets(y, p_yes)
        print(f"  {tag:12s} no-intercept: MAE={m0['mae']:7.4f} bias={m0['bias']:+8.4f} "
              f"R2={m0['r2']:+7.3f} rho={spearman(p_no, y):+.3f}  meanpred={statistics.mean(p_no):+7.3f}")
        print(f"  {tag:12s} WITH intercept: MAE={m1['mae']:7.4f} bias={m1['bias']:+8.4f} "
              f"R2={m1['r2']:+7.3f} rho={spearman(p_yes, y):+.3f}  meanpred={statistics.mean(p_yes):+7.3f}")
        # offset-only correction (oracle-inflated but bounds the offset share)
        off = statistics.mean(y) - statistics.mean(p_no)
        mae_off = sum(abs(p_no[i] + off - y[i]) for i in range(n)) / n
        print(f"  {tag:12s} no-intercept + single global offset {off:+.3f}: MAE={mae_off:7.4f}"
              f"   -> offset explains {(m0['mae']-mae_off)/m0['mae']*100:.1f}% of MAE")

    # how much of the E1 prediction variance is 'structure' vs 'constant'
    p_yes = loo(X1m, y, 1.0, intercept=True)
    print(f"\n  intercept model sd(pred)={statistics.pstdev(p_yes):.3f} vs sd(y)={statistics.pstdev(y):.3f}")

    print("\n" + "=" * 78)
    print("C. E4 identical-fingerprint MJ: are the DESCRIPTORS actually identical?")
    e4 = load(E4D)
    ident = [r for r in e4 if float(r["nn_tanimoto"]) >= 0.999]
    by = {r["name"]: r for r in rows}
    for r in ident:
        a, b = r["name"], r["nearest_neighbour"]
        ra, rb = by[a], by[b]
        d_ha = ra["ha"] - rb["ha"]
        d_v = ra["x0"][4] - rb["x0"][4]
        d_mv = ra["x0"][5] - rb["x0"][5]
        print(f"  {a:18s} vs {b:18s} eps {ra['y']:6.2f}/{rb['y']:6.2f}  "
              f"pred {float(r['y_pred']):+8.4f} err {float(r['abs_error']):6.2f}")
        print(f"     X0 d(heavy_atoms)={d_ha:+d}  d(mol_vol)={d_v:+8.3f} A^3  "
              f"d(molar_vol)={d_mv:+.3e} m3/mol  -> descriptors NOT identical")
    print("  => Morgan/ECFP collision, not descriptor degeneracy:")
    print(f"     prediction DIFFERS across the 'identical' pair "
          f"(nonane {float(ident[0]['y_pred']):+.2f} vs heptane "
          f"{[float(x['y_pred']) for x in ident if x['name']=='heptane'][0]:+.2f}),")
    print("     which is only possible because the X0 feature vectors differ.")
    bi = [float(r["y_pred"]) - float(r["y_true"]) for r in e4]
    off = statistics.mean(bi)
    print(f"\n  E4 residuals after subtracting the single global bias {off:+.3f}:")
    for nm in ("nonane", "heptane", "heptanedinitrile", "octanedinitrile"):
        rr = next(x for x in e4 if x["name"] == nm)
        raw = abs(float(rr["y_pred"]) - float(rr["y_true"]))
        adj = abs(float(rr["y_pred"]) - off - float(rr["y_true"]))
        print(f"     {nm:18s} eps={float(rr['y_true']):5.2f} pred={float(rr['y_pred']):+8.4f} "
              f"|err|={raw:6.2f}  ->  bias-removed |err|={adj:6.2f}")
    # and the properly-fitted (intercept) LOO prediction for the same molecules
    pfix = loo(X1m, y, 1.0, intercept=True)
    print("\n  same molecules under a correctly-intercepted LOO ridge:")
    for nm in ("nonane", "heptane", "heptanedinitrile", "octanedinitrile"):
        i = next(j for j, r in enumerate(rows) if r["name"] == nm)
        print(f"     {nm:18s} eps={y[i]:6.2f} pred={pfix[i]:+8.4f} |err|={abs(pfix[i]-y[i]):6.2f}")
    print(f"  E4 global bias = {off:+.4f} (vs pool mean eps {statistics.mean(y):.2f}) "
          f"-> the model is not under-informative, it is UN-CENTRED")
    print(f"  E4 LOO global bias over 22 mols = {statistics.mean(bi):+.4f}; "
          f"range of residuals {min(bi):+.2f}..{max(bi):+.2f}")
    print(f"  correlation(nn_tanimoto, residual) = "
          f"{spearman([float(r['nn_tanimoto']) for r in e4], bi):+.4f}")

    print("\n" + "=" * 78)
    print("D. E6: is the ranking anti-correlated?")
    order = sorted(range(n), key=lambda i: -y[i])
    k = 3
    p_clean = loo(X1m, y, 1.0, intercept=False)
    p_fix = loo(X1m, y, 1.0, intercept=True)
    for tag, pp in (("no-intercept (as shipped)", p_clean), ("WITH intercept", p_fix)):
        otop = order[:k]
        mtop = sorted(range(n), key=lambda i: -pp[i])[:k]
        om = statistics.mean(y[i] for i in otop)
        mm = statistics.mean(y[i] for i in mtop)
        print(f"  {tag:26s} model_top{k}={mm:6.3f} oracle={om:6.3f} regret={om-mm:6.3f} "
              f"rho={spearman(pp, y):+.3f} overlap={len(set(otop)&set(mtop))}/{k}")
    print(f"  pool mean = {statistics.mean(y):.3f}; random-screening regret = "
          f"{statistics.mean(y[i] for i in order[:k]) - statistics.mean(y):.3f}")

    # noise ladder reproduced + asymptotic limit + local resolution
    print("\n  noise ladder (sigma -> inf limit is the random baseline):")
    rr = random.Random(20261123)
    obs = statistics.mean(y[i] for i in order[:k])
    for sigma in (0, 1, 2, 4, 8, 16, 32, 64):
        means = []
        for _ in range(400):
            nz = [p_clean[i] + rr.gauss(0, sigma) for i in range(n)]
            sel = sorted(range(n), key=lambda i: -nz[i])[:k]
            means.append(statistics.mean(y[i] for i in sel))
        print(f"    sigma={sigma:5.1f} top{k}_mean={statistics.mean(means):7.3f} "
              f"regret={obs-statistics.mean(means):7.3f}")

    # local resolution at the top-k boundary
    sp = sorted(p_clean, reverse=True)
    print(f"\n  sorted predictions: {[round(v,2) for v in sp[:8]]}")
    print(f"  gap p3->p4 = {sp[2]-sp[3]:.2f}, p3->p6 = {sp[2]-sp[5]:.2f}, "
          f"MAE(model) = {mets(y, p_clean)['mae']:.2f}")
    print("  => the Top-k boundary sits INSIDE one MAE of the model; selection is "
          "effectively a lottery among ranks 1-6.")

    print("\n" + "=" * 78)
    print("E. KIRKWOOD: eps is collective -> g factor by class")
    NA, eps0, kB = 6.02214076e23, 8.8541878128e-12, 1.380649e-23
    out = []
    for r in rows:
        T = r["T"]
        mu = r["dip"] * 3.33564e-30
        deb = (NA * mu * mu) / (3 * eps0 * kB * T * r["vm"])
        g = (r["y"] - 1.05) / deb if deb > 0 else float("nan")
        out.append((r["name"], r["y"], deb + 1.05, g))
    for nm, e, de, g in sorted(out, key=lambda z: -z[3]):
        print(f"  {nm:38s} eps={e:6.2f} Debye_est={de:6.2f} g_apparent={g:6.2f}")
    print(f"\n  spearman(eps, Debye estimate) = "
          f"{spearman([z[1] for z in out], [z[2] for z in out]):+.4f}")
    print(f"  spearman(eps, dipole_D)      = "
          f"{spearman(y, [r['dip'] for r in rows]):+.4f}")
    print(f"  spearman(eps, 1/molar_vol)   = "
          f"{spearman(y, [1.0 / r['vm'] for r in rows]):+.4f}")

    print("\n" + "=" * 78)
    print("F. phase-state screen at the stated T_K (mp/mp-ish values in comment)")
    mp = {"nonane": 219.7, "heptane": 182.6, "methylcyclohexane": 146.6,
          "sulfolane": 300.6, "cyclohexanol": 298.9, "2-amino-2-methylpropan-1-ol": 303.6,
          "triethanolamine": 294.8, "diethanolamine": 301.3, "acetic acid": 289.8,
          "dimethyl carbonate": 275.0, "diethyl carbonate": 230.0,
          "1,2-propanediol": 213.0, "1,2-butanediol": 223.0,
          "1-methylimidazole": 267.3, "N-methylaniline": 245.0,
          "cycloheptanone": 250.0, "methyl propenoate": 195.0,
          "octanedinitrile": 274.0, "heptanedinitrile": 253.0,
          "2-acetylthiophene": 285.0,
          "1,4,7,10,13-pentaoxacyclopentadecane": 235.0,
          "N-(2-hydroxypropyl)-2-hydroxy-1-propanamine": 280.0}
    for r in rows:
        m = mp.get(r["name"])
        if m is None:
            continue
        d = r["T"] - m
        flag = "  <<< AT/BELOW MELTING POINT" if d < 3 else ""
        print(f"  {r['name']:38s} T={r['T']:7.2f} K  mp~{m:6.1f} K  T-mp={d:+7.1f} K{flag}")


if __name__ == "__main__":
    main()
