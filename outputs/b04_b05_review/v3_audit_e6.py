#!/usr/bin/env python
"""Reviewer-3 audit of the B05-E6 noise ladder.

Questions:
  (a) Is the RNG seeded consistently across sigma levels? (common random numbers
      vs re-drawing -> is the decrease an RNG artefact?)
  (b) Is the regret decrease statistically real, or inside Monte-Carlo error?
  (c) What does the ladder converge to as sigma -> infinity? If the limit is
      WORSE than the observed minimum, the "noise undoes the bias" mechanism
      cannot be right.
  (d) Recompute top-k regret, p_model_beats_random and Spearman independently.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "b04_b05_review"
E6 = ROOT / "outputs" / "b05" / "E6_screening_decisions"
SEED = 20261123

X_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
          "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
          "dipole_D", "polarizability_au", "polarizability_A3",
          "homo_lumo_gap_ev"]
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


def spearman(a, b):
    n = len(a)

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n))
                    * sum((rb[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    pool = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    feats = {r["inchikey"]: r
             for r in load(ROOT / "data" / "processed" / "dielectric_physical_features.csv")}
    mols = []
    for r in pool:
        f = feats.get(r["inchikey"], {})
        x = [fnum(f.get(c)) for c in X_COLS]
        if any(v is None for v in x):
            continue
        mols.append(dict(name=r["name"], y=float(r["dielectric"]),
                         x=[float(v) for v in x]))
    n = len(mols)
    y = [m["y"] for m in mols]
    X = [m["x"] for m in mols]
    k = max(1, math.ceil(n / 10))

    pred = loo(X, y)
    mae = sum(abs(pred[i] - y[i]) for i in range(n)) / n
    order_true = sorted(range(n), key=lambda i: -y[i])
    oracle = order_true[:k]
    oracle_mean = statistics.mean(y[i] for i in oracle)
    pool_mean = statistics.mean(y)
    order_pred = sorted(range(n), key=lambda i: -pred[i])
    model_topk = order_pred[:k]
    model_mean = statistics.mean(y[i] for i in model_topk)
    regret = oracle_mean - model_mean
    rho = spearman(pred, y)

    res["recomputed"] = dict(
        n=n, k=k, mae=round(mae, 4), spearman=round(rho, 4),
        oracle_mean=round(oracle_mean, 4), model_mean=round(model_mean, 4),
        pool_mean=round(pool_mean, 4), regret=round(regret, 4),
        regret_frac=round(regret / (oracle_mean - pool_mean), 4),
        overlap=len(set(oracle) & set(model_topk)),
        pool_mean_as_regret_limit=round(oracle_mean - pool_mean, 4),
    )
    pub = load(E6 / "topk_regret.csv")[0]
    res["published"] = dict(
        mae=pub["model_topk_mean_epsilon"], regret=pub["regret"],
        p_random=pub["p_model_beats_random"], oracle=pub["oracle_topk_mean_epsilon"],
        model=pub["model_topk_mean_epsilon"], pool=pub["pool_mean_epsilon"],
        k=pub["k"], spearman_manifest=None)
    man = json.loads((E6 / "e6_manifest.json").read_text(encoding="utf-8"))
    res["manifest_metrics"] = man["metrics"]

    # random baseline p, independently (theirs: 2000 samples from SEED)
    rng = random.Random(SEED)
    rnd = [statistics.mean(y[i] for i in rng.sample(range(n), k)) for _ in range(2000)]
    res["random_baseline"] = dict(
        mean=round(statistics.mean(rnd), 4),
        q95=round(sorted(rnd)[int(0.95 * 2000)], 4),
        p_random_ge_model=round(sum(1 for v in rnd if v >= model_mean) / 2000, 4),
    )

    # ---------- (a) RNG consistency across sigma -----------------------------
    # Replay exactly: fresh Random(SEED) per sigma, 200 trials of n draws.
    def ladder(trials, sigmas, rebuild_rng_per_sigma=True, seed=SEED):
        out = []
        for sigma in sigmas:
            rr = random.Random(seed) if rebuild_rng_per_sigma else rr
            means, maes = [], []
            for _ in range(trials):
                noisy = [pred[i] + rr.gauss(0, sigma) for i in range(n)]
                om = sorted(range(n), key=lambda i: -noisy[i])[:k]
                means.append(statistics.mean(y[i] for i in om))
                maes.append(sum(abs(noisy[i] - y[i]) for i in range(n)) / n)
            out.append(dict(sigma=sigma, mean_mae=round(statistics.mean(maes), 4),
                            mean_topk=round(statistics.mean(means), 4),
                            mean_regret=round(oracle_mean - statistics.mean(means), 4),
                            sd_topk=round(statistics.stdev(means), 4),
                            se_regret=round(statistics.stdev(means) / math.sqrt(trials), 4)))
        return out

    sigmas = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
    res["ladder_replayed_200"] = ladder(200, sigmas)
    res["ladder_replayed_20000"] = ladder(20000, sigmas)
    # alternative seeds -> is the monotone decrease robust?
    res["ladder_seed_sweep"] = {
        str(s): [r["mean_regret"] for r in ladder(2000, sigmas, seed=s)]
        for s in (1, 42, 7, 12345, 999)}

    # ---------- (c) limit behaviour ------------------------------------------
    res["ladder_extended"] = ladder(20000, [0.0, 2, 4, 8, 16, 32, 64, 128, 1e6])
    res["theoretical_limits"] = dict(
        sigma0_regret=round(regret, 4),
        sigma_inf_regret=round(oracle_mean - pool_mean, 4),
        note="sigma->inf => uniform random top-k => mean -> pool_mean",
    )

    # ---------- per-molecule check: which molecules are in model top-k --------
    res["model_topk"] = [dict(name=mols[i]["name"], y=y[i], pred=round(pred[i], 4),
                              true_rank=order_true.index(i) + 1,
                              in_oracle=i in set(oracle))
                         for i in order_pred[:k]]
    res["oracle_topk"] = [dict(name=mols[i]["name"], y=y[i], pred=round(pred[i], 4),
                               pred_rank=order_pred.index(i) + 1) for i in oracle]

    (OUT / "v3_e6_audit.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=== recomputed vs published ===")
    print(json.dumps(res["recomputed"], indent=2))
    print("published:", json.dumps(res["published"], indent=2))
    print("random baseline:", res["random_baseline"])
    print("\n=== ladder replayed, 200 trials (their setting) ===")
    for r in res["ladder_replayed_200"]:
        print(f"  sigma={r['sigma']:5} MAE={r['mean_mae']:8.4f} "
              f"topk={r['mean_topk']:8.4f} regret={r['mean_regret']:8.4f} "
              f"sd={r['sd_topk']:6.3f} se={r['se_regret']:.4f}")
    print("\n=== ladder, 20000 trials ===")
    for r in res["ladder_replayed_20000"]:
        print(f"  sigma={r['sigma']:5} regret={r['mean_regret']:8.4f} se={r['se_regret']:.4f}")
    print("\n=== seed sweep, regret by sigma ===")
    for s, v in res["ladder_seed_sweep"].items():
        print(f"  seed={s:>6s} {v}")
    print("\n=== extended ladder (limit behaviour) ===")
    for r in res["ladder_extended"]:
        print(f"  sigma={r['sigma']:<10} MAE={r['mean_mae']:9.4f} "
              f"topk={r['mean_topk']:8.4f} regret={r['mean_regret']:9.4f}")
    print("\ntheoretical limits:", res["theoretical_limits"])
    print("\nmodel top-k:", res["model_topk"])
    print("oracle top-k:", res["oracle_topk"])


if __name__ == "__main__":
    main()
