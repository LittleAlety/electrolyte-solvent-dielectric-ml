#!/usr/bin/env python
"""Reviewer 4 attack 2: is the reported failure a descriptor failure or an
estimator defect?

The project's ridge_fit solves (Z'Z + lam I) b = Z'y on standardised Z with NO
intercept column. Because Z is column-centred on the TRAINING rows, the fitted
values Z b have training mean exactly 0 by construction. The estimator therefore
cannot represent the label mean (~17.3) and every prediction is shifted down by
roughly that amount. Every downstream number (MAE, bias, R2, the Tanimoto
applicability-domain ratio, the Top-k regret, the noise ladder, the three-split
agreement) is computed on those shifted predictions.

This script:
  (a) reproduces the published numbers exactly,
  (b) re-runs the SAME estimators with an intercept (a one-line fix),
  (c) does the lambda sensitivity check demanded in the review mandate,
  (d) compares against other learners,
  (e) recomputes the permutation nulls.
"""
from __future__ import annotations

import csv, json, math, random, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEAT = REPO / "data" / "processed" / "dielectric_physical_features.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]
XE4 = X0 + ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]
PH = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}
SEED = 20261123


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PH:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def standardise(X):
    n, p = len(X), len(X[0])
    mu = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sd = []
    for j in range(p):
        v = sum((X[i][j] - mu[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sd.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(X[i][j] - mu[j]) / sd[j] for j in range(p)] for i in range(n)], mu, sd


def solve(A, rhs):
    p = len(rhs)
    A = [row[:] for row in A]
    rhs = rhs[:]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-14:
            continue
        A[c], A[piv] = A[piv], A[c]
        rhs[c], rhs[piv] = rhs[piv], rhs[c]
        pv = A[c][c]
        for r in range(c + 1, p):
            f = A[r][c] / pv
            if f == 0:
                continue
            for k in range(c, p):
                A[r][k] -= f * A[c][k]
            rhs[r] -= f * rhs[c]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-14:
            continue
        b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
    return b


def fit_b(rows, y, lam):
    Z, mu, sd = standardise(rows)
    p = len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(len(Z))) for a in range(p)]
    return solve(A, rhs), mu, sd


def loo(X, y, lam=1.0, intercept=False):
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        b, mu, sd = fit_b([X[i] for i in tr], [y[i] for i in tr], lam)
        x = [(X[h][j] - mu[j]) / sd[j] for j in range(len(mu))]
        v = sum(x[j] * b[j] for j in range(len(b)))
        if intercept:
            v += sum(y[i] for i in tr) / len(tr)
        out.append(v)
    return out


def mae(y, p):
    return sum(abs(p[i] - y[i]) for i in range(len(y))) / len(y)


def rmse(y, p):
    return math.sqrt(sum((p[i] - y[i]) ** 2 for i in range(len(y))) / len(y))


def bias(y, p):
    return sum(p[i] - y[i] for i in range(len(y))) / len(y)


def r2(y, p):
    yb = sum(y) / len(y)
    sst = sum((v - yb) ** 2 for v in y)
    ssr = sum((p[i] - y[i]) ** 2 for i in range(len(y)))
    return 1 - ssr / sst


def spearman(a, b):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[o[j + 1]] == v[o[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[o[k]] = avg
            i = j + 1
        return rk
    ra, rb = rank(a), rank(b)
    ma_, mb_ = sum(ra) / len(a), sum(rb) / len(b)
    num = sum((ra[i] - ma_) * (rb[i] - mb_) for i in range(len(a)))
    den = math.sqrt(sum((v - ma_) ** 2 for v in ra) * sum((v - mb_) ** 2 for v in rb))
    return num / den if den else float("nan")


def main():
    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEAT)}
    y = [float(r["dielectric"]) for r in pool]
    n = len(y)
    ybar = sum(y) / n

    def mat(cols):
        return [[float(fnum(feats[r["inchikey"]][c])) for c in cols] for r in pool]

    X0m, X1m, XE4m = mat(X0), mat(X0 + X1), mat(XE4)
    res = {}

    # constant baselines
    const_all = mae(y, [ybar] * n)
    loo_const = []
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        loo_const.append(sum(y[j] for j in tr) / len(tr))
    res["baselines"] = {"const_mean_all22": const_all,
                        "const_mean_loo": mae(y, loo_const),
                        "pool_mean": ybar, "pool_sd": statistics.stdev(y),
                        "pool_min": min(y), "pool_max": max(y)}

    # (a) reproduce + (b) intercept-corrected
    grid = {}
    for lam in (0.0, 0.01, 0.1, 1.0, 10.0, 100.0):
        for ic in (False, True):
            key = f"lam{lam}_{'icpt' if ic else 'noicpt'}"
            p0 = loo(X0m, y, lam, ic)
            p1 = loo(X1m, y, lam, ic)
            grid[key] = {
                "X0_mae": mae(y, p0), "X0_bias": bias(y, p0), "X0_r2": r2(y, p0),
                "X0_spearman": spearman(p0, y),
                "X0X1_mae": mae(y, p1), "X0X1_bias": bias(y, p1),
                "X0X1_r2": r2(y, p1), "X0X1_spearman": spearman(p1, y),
                "delta_mae": mae(y, p1) - mae(y, p0),
                "beats_const": mae(y, p0) < const_all,
            }
    res["lambda_and_intercept_grid"] = grid

    # E4 model too (11 cols, no total_energy)
    grid_e4 = {}
    for lam in (0.0, 1.0):
        for ic in (False, True):
            p = loo(XE4m, y, lam, ic)
            grid_e4[f"lam{lam}_{'icpt' if ic else 'noicpt'}"] = {
                "mae": mae(y, p), "bias": bias(y, p), "r2": r2(y, p),
                "spearman": spearman(p, y)}
    res["e4_model_grid"] = grid_e4

    # (e) permutation nulls for the FIXED estimator
    def perm_null(cols, lam, ic, nperm=2000, seed=SEED):
        rng = random.Random(seed)
        obs = mae(y, loo(mat(cols), y, lam, ic))
        null = []
        for _ in range(nperm):
            yp = y[:]
            rng.shuffle(yp)
            null.append(mae(yp, loo(mat(cols), yp, lam, ic)))
        null.sort()
        p = sum(1 for v in null if v <= obs) / len(null)
        return {"observed_mae": obs, "p_one_sided": p,
                "null_q05": null[int(0.05 * len(null))],
                "null_median": null[len(null) // 2],
                "null_min": null[0], "n_perm": nperm}

    res["permutation_null"] = {
        "X0_buggy_lam1": perm_null(X0, 1.0, False, 500),
        "X0X1_buggy_lam1": perm_null(X0 + X1, 1.0, False, 500),
        "X0_fixed_lam1": perm_null(X0, 1.0, True, 2000),
        "X0X1_fixed_lam1": perm_null(X0 + X1, 1.0, True, 2000),
        "E4_fixed_lam1": perm_null(XE4, 1.0, True, 2000),
    }

    # (d) other learners, scikit-learn, LOO
    import numpy as np
    from sklearn.linear_model import RidgeCV, LinearRegression
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import LeaveOneOut, cross_val_predict
    from sklearn.metrics import mean_absolute_error

    learners = {}
    defs = {
        "OLS": make_pipeline(StandardScaler(), LinearRegression()),
        "RidgeCV_auto": make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 25))),
        "RF_500": RandomForestRegressor(n_estimators=500, random_state=SEED),
        "GBM": GradientBoostingRegressor(random_state=SEED),
        "kNN_3": make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=3)),
        "kNN_5": make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=5)),
    }
    Xnp = np.array(X1m, dtype=float)
    for name, mdl in defs.items():
        pr = cross_val_predict(mdl, Xnp, np.array(y), cv=LeaveOneOut())
        learners[name] = {"mae": float(mean_absolute_error(y, pr)),
                          "spearman": spearman(list(pr), y),
                          "r2": float(r2(y, list(pr))),
                          "bias": float(bias(y, list(pr)))}
    res["other_learners_loo"] = learners

    # best single descriptor (properly with intercept)
    singles = {}
    for j, c in enumerate(XE4):
        col = [[XE4m[i][j]] for i in range(n)]
        p = loo(col, y, 0.0, True)
        singles[c] = {"mae": mae(y, p), "spearman": spearman(p, y), "r2": r2(y, p)}
    res["single_descriptor_models"] = dict(
        sorted(singles.items(), key=lambda kv: kv[1]["mae"]))

    # 2-descriptor best pair
    best = None
    for a in range(len(XE4)):
        for b_ in range(a + 1, len(XE4)):
            col = [[XE4m[i][a], XE4m[i][b_]] for i in range(n)]
            p = loo(col, y, 0.0, True)
            m = mae(y, p)
            if best is None or m < best["mae"]:
                best = {"pair": [XE4[a], XE4[b_]], "mae": m,
                        "spearman": spearman(p, y), "r2": r2(y, p)}
    res["best_descriptor_pair"] = best

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_02_estimator.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
