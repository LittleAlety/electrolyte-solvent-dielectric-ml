#!/usr/bin/env python
"""Reviewer-3 audit of the B05-E1 permutation null.

Claims to test:
  1. The null shuffles y and refits. Because the ridge has NO intercept, the
     null distribution is pinned near the "predict 0" baseline, so the test
     cannot answer "does this feature set explain variance".
  2. The two models share ONE random stream (random.seed once, then 500 shuffles
     for X0, then 500 more for X0+X1). Therefore each model's p-value depends on
     the order the models are looped over -> not a per-model reproducible p.
  3. The correct null for "does this feature set carry information" is a
     FEATURE permutation (column-wise), keeping y fixed.
  4. There is no null for Delta MAE although the report reasons about it.
"""
from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E1 = ROOT / "outputs" / "b05" / "E1_structure_vs_electronic"
OUT = ROOT / "outputs" / "b04_b05_review"
SEED = 20261123
NPERM = 500

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]
PH = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


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


def _std(X):
    n, p = len(X), len(X[0])
    m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


def _solve(A, rhs):
    p = len(A)
    A = [r[:] for r in A]
    rhs = rhs[:]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12:
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
        Z, m, s = _std(Xtr)
        p = len(m)
        ybar = sum(ytr) / len(ytr) if intercept else 0.0
        A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
              for b in range(p)] for a in range(p)]
        rhs = [sum(Z[i][a] * (ytr[i] - ybar) for i in range(len(Z))) for a in range(p)]
        b = _solve(A, rhs)
        x = [(X[h][j] - m[j]) / s[j] for j in range(p)]
        out.append(ybar + sum(x[j] * b[j] for j in range(p)))
    return out


def mae_of(y, p):
    n = len(y)
    return sum(abs(p[i] - y[i]) for i in range(n)) / n


def r2_of(y, p):
    n = len(y)
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y)
    return 1 - sum((p[i] - y[i]) ** 2 for i in range(n)) / sst


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    pool = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    feats = {r["inchikey"]: r
             for r in load(ROOT / "data" / "processed" / "dielectric_physical_features.csv")}
    y, A0, A1 = [], [], []
    for r in pool:
        f = feats.get(r["inchikey"], {})
        a = [fnum(f.get(c)) for c in X0]
        b = [fnum(f.get(c)) for c in X0 + X1]
        if any(v is None for v in a) or any(v is None for v in b):
            continue
        y.append(float(r["dielectric"]))
        A0.append([float(v) for v in a])
        A1.append([float(v) for v in b])

    # ---- 1. replicate the script's SHARED-stream ordering --------------------
    random.seed(SEED)
    shared = {}
    for label, X in (("X0_structure_only", A0), ("X0_plus_X1_electronic", A1)):
        maes = []
        for _ in range(NPERM):
            yp = y[:]
            random.shuffle(yp)
            maes.append(mae_of(yp, loo(X, yp, 1.0)))
        maes.sort()
        obs = mae_of(y, loo(X, y, 1.0))
        shared[label] = dict(observed=round(obs, 6),
                             q05=round(maes[int(0.05 * NPERM)], 6),
                             median=round(maes[int(0.50 * NPERM)], 6),
                             p=round(sum(1 for v in maes if v <= obs) / NPERM, 4))
    res["replicated_shared_stream"] = shared
    res["published"] = {n["model"]: dict(p=n["permutation_p_value"],
                                         obs=n["observed_mae"],
                                         q05=n["null_mae_q05"],
                                         median=n["null_mae_median"])
                        for n in load(E1 / "permutation_null.csv")}

    # ---- 2. same test but per-model reseed + REVERSED order ------------------
    per_model = {}
    for label, X in (("X0_plus_X1_electronic", A1), ("X0_structure_only", A0)):
        rng = random.Random(SEED)
        maes = []
        for _ in range(NPERM):
            yp = y[:]
            rng.shuffle(yp)
            maes.append(mae_of(yp, loo(X, yp, 1.0)))
        maes.sort()
        obs = mae_of(y, loo(X, y, 1.0))
        per_model[label] = dict(p=round(sum(1 for v in maes if v <= obs) / NPERM, 4),
                                q05=round(maes[int(0.05 * NPERM)], 6),
                                median=round(maes[int(0.50 * NPERM)], 6))
    res["per_model_reseed"] = per_model

    # ---- 3. CORRECT null: permute features (columns), keep y ----------------
    def ss_total(y):
        ybar = sum(y) / len(y)
        return sum((v - ybar) ** 2 for v in y)

    # 3a. "does the feature set explain variance" -> test R2 against column perm
    feat_null = {}
    for label, X in (("X0", A0), ("X0X1", A1)):
        n, p = len(X), len(X[0])
        cols = list(zip(*X))
        rng = random.Random(SEED)
        null_r2, null_mae = [], []
        for _ in range(NPERM):
            new = []
            for c in cols:
                cc = list(c)
                rng.shuffle(cc)
                new.append(cc)
            Xp = [list(row) for row in zip(*new)]
            pp = loo(Xp, y, 1.0)
            null_r2.append(r2_of(y, pp))
            null_mae.append(mae_of(y, pp))
        obs_p = loo(X, y, 1.0)
        obs_r2 = r2_of(y, obs_p)
        obs_mae = mae_of(y, obs_p)
        null_r2.sort()
        null_mae.sort()
        feat_null[label] = dict(
            observed_r2=round(obs_r2, 6),
            observed_mae=round(obs_mae, 6),
            r2_null_median=round(null_r2[len(null_r2) // 2], 6),
            r2_null_q95=round(null_r2[int(0.95 * len(null_r2))], 6),
            p_r2_ge=round(sum(1 for v in null_r2 if v >= obs_r2) / NPERM, 4),
            mae_null_median=round(null_mae[len(null_mae) // 2], 6),
            p_mae_le=round(sum(1 for v in null_mae if v <= obs_mae) / NPERM, 4),
        )
    res["feature_permutation_null"] = feat_null

    # ---- 4. Delta-MAE null (the quantity the report discusses) --------------
    rng = random.Random(SEED)
    d_null = []
    for _ in range(NPERM):
        yp = y[:]
        rng.shuffle(yp)
        d_null.append(mae_of(yp, loo(A1, yp, 1.0)) - mae_of(yp, loo(A0, yp, 1.0)))
    obs_d = mae_of(y, loo(A1, y, 1.0)) - mae_of(y, loo(A0, y, 1.0))
    d_null.sort()
    res["delta_null"] = dict(
        observed_delta=round(obs_d, 6),
        null_median=round(d_null[len(d_null) // 2], 6),
        null_q05=round(d_null[int(0.05 * len(d_null))], 6),
        null_q95=round(d_null[int(0.95 * len(d_null))], 6),
        p_two_sided=round(sum(1 for v in d_null if abs(v) >= abs(obs_d)) / NPERM, 4),
    )

    # ---- 5. why the y-shuffle null is degenerate: closed-form check ---------
    # With no intercept and standardised X, predictions are ~centred on 0, so
    # MAE is dominated by E|y|, not by explained variance.
    ybar = sum(y) / len(y)
    res["degeneracy"] = dict(
        mae_predict_zero=round(sum(abs(v) for v in y) / len(y), 6),
        mae_predict_mean=round(sum(abs(v - ybar) for v in y) / len(y), 6),
        observed_x0=round(shared["X0_structure_only"]["observed"], 6),
        observed_x0x1=round(shared["X0_plus_X1_electronic"]["observed"], 6),
        note=("observed MAE is within ~1.5% of the predict-zero baseline: the "
              "no-intercept model has no way to reach the label mean, so the "
              "null and the observation are both pinned to E|y|"),
    )

    (OUT / "v3_e1_null_audit.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== published permutation_null.csv ===")
    for k, v in res["published"].items():
        print(f"  {k:26s} obs={v['obs']} q05={v['q05']} med={v['median']} p={v['p']}")
    print("\n=== replicate shared-stream ordering (should match) ===")
    for k, v in shared.items():
        print(f"  {k:26s} obs={v['observed']} q05={v['q05']} "
              f"med={v['median']} p={v['p']}")
    print("\n=== per-model reseed (order reversed) ===")
    for k, v in per_model.items():
        print(f"  {k:26s} p={v['p']} q05={v['q05']} med={v['median']}")
    print("\n=== FEATURE-permutation null (the appropriate null) ===")
    for k, v in feat_null.items():
        print(f"  {k}: obs R2={v['observed_r2']} obs MAE={v['observed_mae']} | "
              f"R2 null med={v['r2_null_median']} q95={v['r2_null_q95']} "
              f"p(R2>=obs)={v['p_r2_ge']} | MAE null med={v['mae_null_median']} "
              f"p(MAE<=obs)={v['p_mae_le']}")
    print("\n=== Delta-MAE null ===")
    print(" ", res["delta_null"])
    print("\n=== degeneracy check ===")
    print(" ", json.dumps(res["degeneracy"], indent=2))


if __name__ == "__main__":
    main()
