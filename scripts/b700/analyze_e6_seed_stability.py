#!/usr/bin/env python
"""E6 stability: how much does Top-k regret move across fold partitions?

Top-10 regret over a 239-molecule pool depends on which molecules happen to land
in the predicted top-10. A single seed can therefore produce a number that is not
representative. This script repeats the full nested-LOO + Top-k computation over
several seeds and reports the distribution.

This is a METHODOLOGICAL result, not a new model: its purpose is to tell the
report how many digits of a regret number are meaningful.

Output: outputs/b700/B706_E6_seed_stability.json
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

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
GEN = "analyze_e6_seed_stability/1.0.0"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
ARMS = {
    "X0_plus_mu2_Vm_v7": X0_COLS + ["mu_sq_over_Vm_v7"],
    "X0_plus_v7_electronic": X0_COLS + ["dipole_D_v7", "homo_lumo_gap_ev_v7"],
    "X0_plus_xtb_electronic": X0_COLS + ["dipole_D", "homo_lumo_gap_ev"],
    "X0_structure": X0_COLS,
}
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
SEEDS = [20261123, 20261124, 20261125, 20261126, 20261127]
TOPK = 10


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
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    return ([[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)],
            means, sds)


def ridge_fit(Z, y, lam):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    for col in range(p):
        piv = max(range(col, p), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            continue
        A[col], A[piv] = A[piv], A[col]
        rhs[col], rhs[piv] = rhs[piv], rhs[col]
        pv = A[col][col]
        for r in range(col + 1, p):
            f = A[r][col] / pv
            for c in range(col, p):
                A[r][c] -= f * A[col][c]
            rhs[r] -= f * rhs[col]
    x = [0.0] * p
    for r in range(p - 1, -1, -1):
        s = rhs[r] - sum(A[r][c] * x[c] for c in range(r + 1, p))
        if abs(A[r][r]) > 1e-12:
            x[r] = s / A[r][r]
    return x


def fit_predict(Xtr, ytr, Xte, lam):
    Z, means, sds = standardise(Xtr)
    b = ridge_fit(Z, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    return [ybar + sum(((row[j] - means[j]) / sds[j]) * b[j]
                       for j in range(len(means))) for row in Xte]


def choose_lambda(X, y, seed, k=5):
    n = len(X)
    if n < k * 3:
        return 1.0
    idx = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(idx)
    folds = [[] for _ in range(k)]
    for i, v in enumerate(idx):
        folds[i % k].append(v)
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [i for j in range(k) if j != f for i in folds[j]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict([X[i] for i in tr], [y[i] for i in tr],
                            [X[i] for i in te], lam)
            errs.extend(abs(p[t] - y[te[t]]) for t in range(len(te)))
        if errs:
            m = sum(errs) / len(errs)
            if m < best:
                best, bl = m, lam
    return bl


def nested_loo(X, y, seed):
    n = len(X)
    pred = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        lam = choose_lambda([X[i] for i in tr], [y[i] for i in tr], seed)
        pred.append(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                                [X[h]], lam)[0])
    return pred


def main() -> None:
    rows = load_csv(OUT / "orca_r2scan3c_descriptors.csv")
    results = {}
    for arm, cols in ARMS.items():
        X, y = [], []
        for r in rows:
            if fnum(r.get("epsilon")) is None:
                continue
            xs = []
            for c in cols:
                v = fnum(r.get(c))
                if v is None and c == "homo_lumo_gap_ev_v7":
                    v = fnum(r.get("homo_lumo_gap_ev"))
                xs.append(v)
            if any(v is None for v in xs):
                continue
            X.append(xs)
            y.append(fnum(r["epsilon"]))

        n = len(y)
        oracle = statistics.mean(sorted(y, reverse=True)[:TOPK])
        per_seed = []
        for seed in SEEDS:
            p = nested_loo(X, y, seed)
            order = sorted(range(n), key=lambda i: -p[i])
            model_top = statistics.mean(y[i] for i in order[:TOPK])
            mae = sum(abs(p[i] - y[i]) for i in range(n)) / n
            per_seed.append({
                "seed": seed,
                "mae": round(mae, 4),
                "topk_model_mean": round(model_top, 4),
                "regret": round(oracle - model_top, 4),
            })
            print(f"  {arm:26s} seed={seed} MAE={mae:.4f} regret={oracle-model_top:.3f}",
                  flush=True)

        regrets = [s["regret"] for s in per_seed]
        maes = [s["mae"] for s in per_seed]
        results[arm] = {
            "n": n,
            "topk_oracle_mean": round(oracle, 4),
            "per_seed": per_seed,
            "regret_mean": round(statistics.mean(regrets), 4),
            "regret_sd": round(statistics.pstdev(regrets), 4),
            "regret_min": min(regrets),
            "regret_max": max(regrets),
            "mae_mean": round(statistics.mean(maes), 4),
            "mae_sd": round(statistics.pstdev(maes), 4),
        }

    doc = {
        "schema": "b700.e6_seed_stability/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "k": TOPK,
        "seeds": SEEDS,
        "protocol": "nested LOO (per-fold lambda by inner 5-fold CV), identical to v6.0",
        "arms": results,
        "headline": (
            "Top-k regret at n=239, k=10 is a high-variance statistic: it moves by "
            "several epsilon units across fold partitions. Rank-order the arms by median "
            "regret, not by a single seed, and quote the spread."
        ),
    }
    path = OUT / "B706_E6_seed_stability.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {path}")
    print(f"{'arm':28s} {'regret mean':>11s} {'sd':>7s} {'min':>7s} {'max':>7s}")
    for arm, r in results.items():
        print(f"{arm:28s} {r['regret_mean']:11.3f} {r['regret_sd']:7.3f} "
              f"{r['regret_min']:7.3f} {r['regret_max']:7.3f}")


if __name__ == "__main__":
    main()
