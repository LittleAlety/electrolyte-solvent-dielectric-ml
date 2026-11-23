#!/usr/bin/env python
"""Reviewer-3 independent re-computation of B05-E1 statistics.

Reads predictions_loo.csv, recomputes MAE/RMSE/bias/R2/constant-baseline MAE
with no reference to the project's own functions, then re-implements the ridge
model to test whether the missing intercept in scripts/b05/run_e1_*.py explains
the reported failure.
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


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def stats(y, p):
    n = len(y)
    e = [p[i] - y[i] for i in range(n)]
    mae = sum(abs(v) for v in e) / n
    rmse = math.sqrt(sum(v * v for v in e) / n)
    bias = sum(e) / n
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y)
    ssr = sum(v * v for v in e)
    return dict(n=n, mae=mae, rmse=rmse, bias=bias,
                r2=1 - ssr / sst if sst else float("nan"))


def _std(X):
    n, p = len(X), len(X[0])
    m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


def _solve(A, rhs):
    """Gaussian elimination, partial pivoting."""
    p = len(A)
    A = [row[:] for row in A]
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


def ridge_loo_noint(X, y, lam=1.0):
    """Replica of the project's ridge_loo: standardised, NO intercept."""
    n = len(X)
    out = []
    for h in range(n):
        Xtr = [X[i] for i in range(n) if i != h]
        ytr = [y[i] for i in range(n) if i != h]
        Z, m, s = _std(Xtr)
        p = len(m)
        A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
              for b in range(p)] for a in range(p)]
        rhs = [sum(Z[i][a] * ytr[i] for i in range(len(Z))) for a in range(p)]
        b = _solve(A, rhs)
        x = [(X[h][j] - m[j]) / s[j] for j in range(p)]
        out.append(sum(x[j] * b[j] for j in range(p)))
    return out


def ridge_loo_intercept(X, y, lam=1.0):
    """Same ridge but WITH an intercept (y centred on the training mean)."""
    n = len(X)
    out = []
    for h in range(n):
        Xtr = [X[i] for i in range(n) if i != h]
        ytr = [y[i] for i in range(n) if i != h]
        ybar = sum(ytr) / len(ytr)
        Z, m, s = _std(Xtr)
        p = len(m)
        A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
              for b in range(p)] for a in range(p)]
        rhs = [sum(Z[i][a] * (ytr[i] - ybar) for i in range(len(Z))) for a in range(p)]
        b = _solve(A, rhs)
        x = [(X[h][j] - m[j]) / s[j] for j in range(p)]
        out.append(ybar + sum(x[j] * b[j] for j in range(p)))
    return out


X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}

    # ---------- 1. recompute the published numbers from predictions_loo.csv ----
    pub = load(E1 / "predictions_loo.csv")
    man = json.loads((E1 / "e1_manifest.json").read_text(encoding="utf-8"))
    rec = {}
    for model in ("X0_structure_only", "X0_plus_X1_electronic"):
        rows = [r for r in pub if r["model"] == model]
        y = [float(r["y_true"]) for r in rows]
        p = [float(r["y_pred"]) for r in rows]
        st = stats(y, p)
        ybar = sum(y) / len(y)
        const_mae = sum(abs(v - ybar) for v in y) / len(y)
        const_rmse = math.sqrt(sum((v - ybar) ** 2 for v in y) / len(y))
        declared = next(m for m in man["metrics"] if m["model"] == model)
        rec[model] = dict(
            recomputed=st, const_mae=const_mae, const_rmse=const_rmse,
            declared_mae=declared["mae"], declared_rmse=declared["rmse"],
            declared_bias=declared["bias"], declared_r2=declared["r2"],
            declared_const_mae=declared["constant_baseline_mae"],
            match_mae=abs(st["mae"] - declared["mae"]) < 5e-6,
            match_rmse=abs(st["rmse"] - declared["rmse"]) < 5e-6,
            match_bias=abs(st["bias"] - declared["bias"]) < 5e-6,
            match_r2=abs(st["r2"] - declared["r2"]) < 5e-6,
            match_const=abs(const_mae - declared["constant_baseline_mae"]) < 5e-6,
            mean_pred=sum(p) / len(p), mean_true=ybar,
            min_pred=min(p), max_pred=max(p),
        )
    report["recompute_vs_manifest"] = rec

    # ---------- 2. rebuild X and rerun the model with / without intercept -----
    pool = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    feats = {r["inchikey"]: r
             for r in load(ROOT / "data" / "processed" / "dielectric_physical_features.csv")}
    PH = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}

    def get(ik, cols):
        f = feats.get(ik, {})
        v = []
        for c in cols:
            s = (f.get(c) or "").strip()
            if s.lower() in PH:
                return None
            v.append(float(s))
        return v

    y, A0, A1 = [], [], []
    for r in pool:
        a = get(r["inchikey"], X0)
        b = get(r["inchikey"], X0 + X1)
        if a is None or b is None:
            continue
        y.append(float(r["dielectric"]))
        A0.append(a)
        A1.append(b)
    report["n_used"] = len(y)

    variants = {}
    for lam in (1.0,):
        for name, X in (("X0", A0), ("X0X1", A1)):
            for kind, fn in (("no_intercept", ridge_loo_noint),
                             ("with_intercept", ridge_loo_intercept)):
                p = fn(X, y, lam)
                st = stats(y, p)
                ybar = sum(y) / len(y)
                cm = sum(abs(v - ybar) for v in y) / len(y)
                variants[f"{name}|{kind}|lam={lam}"] = dict(
                    mae=round(st["mae"], 6), rmse=round(st["rmse"], 6),
                    bias=round(st["bias"], 6), r2=round(st["r2"], 6),
                    mean_pred=round(sum(p) / len(p), 4),
                    beats_const=st["mae"] < cm,
                    mean_abs_pred=round(sum(abs(v) for v in p) / len(p), 4),
                )
    report["model_variants"] = variants
    report["constant_baseline_mae"] = round(
        sum(abs(v - sum(y) / len(y)) for v in y) / len(y), 6)

    # ---------- 3. permutation null: what does it actually test? -------------
    # (a) replicate the project's null (shuffle y, no intercept)
    # (b) same null but WITH intercept -> the null the report implicitly claims
    # (c) feature-permutation null (shuffle each column independently, keep y)
    SEED = 20261123
    NPERM = 500
    null = {}
    for tag, X in (("X0", A0), ("X0X1", A1)):
        for kind, fn in (("no_intercept", ridge_loo_noint),
                         ("with_intercept", ridge_loo_intercept)):
            rng = random.Random(SEED)
            maes = []
            for _ in range(NPERM):
                yp = y[:]
                rng.shuffle(yp)
                maes.append(stats(yp, fn(X, yp, 1.0))["mae"])
            maes.sort()
            obs = stats(y, fn(X, y, 1.0))["mae"]
            null[f"{tag}|{kind}|y_shuffle"] = dict(
                observed=round(obs, 4),
                q05=round(maes[int(0.05 * len(maes))], 4),
                median=round(maes[len(maes) // 2], 4),
                min=round(maes[0], 4),
                p_le=round(sum(1 for v in maes if v <= obs) / len(maes), 4),
                const_mae=report["constant_baseline_mae"],
            )

    # feature permutation (column-wise shuffle), with intercept
    def feat_perm_null(X, y, nperm=NPERM):
        n, p = len(X), len(X[0])
        rng = random.Random(SEED)
        maes = []
        for _ in range(nperm):
            cols = list(zip(*X))
            new = []
            for c in cols:
                cc = list(c)
                rng.shuffle(cc)
                new.append(cc)
            Xp = [list(row) for row in zip(*new)]
            maes.append(stats(y, ridge_loo_intercept(Xp, y, 1.0))["mae"])
        maes.sort()
        obs = stats(y, ridge_loo_intercept(X, y, 1.0))["mae"]
        return dict(observed=round(obs, 4),
                    q05=round(maes[int(0.05 * len(maes))], 4),
                    median=round(maes[len(maes) // 2], 4),
                    p_le=round(sum(1 for v in maes if v <= obs) / len(maes), 4),
                    null_uniform_ok=True)

    null["X0|with_intercept|feature_perm"] = feat_perm_null(A0, y)
    null["X0X1|with_intercept|feature_perm"] = feat_perm_null(A1, y)
    report["null_distributions"] = null

    # ---------- 4. lambda sensitivity: was lam=1.0 defensible? ---------------
    lam_scan = {}
    for lam in (0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0, 100.0):
        d = {}
        for name, X in (("X0", A0), ("X0X1", A1)):
            for kind, fn in (("no_intercept", ridge_loo_noint),
                             ("with_intercept", ridge_loo_intercept)):
                st = stats(y, fn(X, y, lam))
                d[f"{name}|{kind}"] = (round(st["mae"], 4), round(st["r2"], 4))
        lam_scan[str(lam)] = d
    report["lambda_scan"] = lam_scan

    (OUT / "v3_stats_recompute.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 1. recompute from predictions_loo.csv vs manifest ===")
    for m, r in rec.items():
        print(f"{m}: MAE {r['recomputed']['mae']:.6f} (decl {r['declared_mae']}) "
              f"match={r['match_mae']} | RMSE {r['recomputed']['rmse']:.6f} "
              f"match={r['match_rmse']} | bias {r['recomputed']['bias']:.6f} "
              f"match={r['match_bias']} | R2 {r['recomputed']['r2']:.6f} "
              f"match={r['match_r2']} | const MAE {r['const_mae']:.6f} "
              f"match={r['match_const']}")
        print(f"   mean_pred={r['mean_pred']:.4f} mean_true={r['mean_true']:.4f} "
              f"pred range [{r['min_pred']:.2f}, {r['max_pred']:.2f}]")
    print(f"\n=== 2. model variants (const baseline MAE "
          f"{report['constant_baseline_mae']}) ===")
    for k, v in variants.items():
        print(f"{k:32s} MAE={v['mae']:8.4f} RMSE={v['rmse']:8.4f} "
              f"bias={v['bias']:8.4f} R2={v['r2']:8.4f} mean_pred={v['mean_pred']:7.3f} "
              f"beats_const={v['beats_const']}")
    print("\n=== 3. null distributions ===")
    for k, v in null.items():
        print(f"{k:40s} obs={v['observed']:8.4f} q05={v['q05']:8.4f} "
              f"med={v['median']:8.4f} p={v['p_le']}")
    print("\n=== 4. lambda scan (MAE, R2) ===")
    for lam, d in lam_scan.items():
        print(f"lam={lam:>6s} " + " ".join(f"{k}={v}" for k, v in d.items()))


if __name__ == "__main__":
    main()
