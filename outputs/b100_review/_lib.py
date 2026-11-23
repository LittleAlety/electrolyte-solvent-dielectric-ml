"""Reviewer-4 adversarial audit: shared recomputation library.

Independent re-implementation of the B100 ridge/nested-LOO protocol so that the
published numbers can be reproduced (or broken) without touching any frozen file.
Nothing here writes outside outputs/b100_review/.
"""
from __future__ import annotations

import math
import random

import numpy as np

SEED = 20261123
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X1_COLS = ["dipole_D", "polarizability_au", "homo_lumo_gap_ev"]
XN_COLS = ["mu_sq_over_Vm", "alpha_over_Vm"]


def kfold_idx(n, k, seed=SEED):
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    folds = [[] for _ in range(k)]
    for i, idx in enumerate(order):
        folds[i % k].append(idx)
    return [np.asarray(f, int) for f in folds]


def _fit_predict(Xtr, ytr, Xte, lam):
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0, ddof=1)
    sd = np.where(sd == 0, 1.0, sd)
    Z = (Xtr - mu) / sd
    Zt = (Xte - mu) / sd
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    b = np.linalg.solve(A, Z.T @ (ytr - ytr.mean()))
    return ytr.mean() + Zt @ b


def choose_lambda(Xtr, ytr, k=5, seed=SEED):
    n = len(ytr)
    if n < k * 3:
        return 1.0
    folds = kfold_idx(n, k, seed)
    best_lam, best_mae = LAMBDA_GRID[0], float("inf")
    allidx = np.arange(n)
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = np.setdiff1d(allidx, te, assume_unique=True)
            if len(te) == 0 or len(tr) < 5:
                continue
            p = _fit_predict(Xtr[tr], ytr[tr], Xtr[te], lam)
            errs.append(np.abs(p - ytr[te]))
        if errs:
            m = float(np.concatenate(errs).mean())
            if m < best_mae:
                best_mae, best_lam = m, lam
    return best_lam


def nested_loo(X, y, return_lambda=False):
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n = len(y)
    pred = np.empty(n)
    lams = []
    allidx = np.arange(n)
    for hold in range(n):
        tr = np.setdiff1d(allidx, [hold], assume_unique=True)
        lam = choose_lambda(X[tr], y[tr])
        lams.append(lam)
        pred[hold] = _fit_predict(X[tr], y[tr], X[hold:hold + 1], lam)[0]
    if return_lambda:
        return pred, lams
    return pred


def loo_fixed(X, y, lam):
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n = len(y)
    pred = np.empty(n)
    allidx = np.arange(n)
    for hold in range(n):
        tr = np.setdiff1d(allidx, [hold], assume_unique=True)
        pred[hold] = _fit_predict(X[tr], y[tr], X[hold:hold + 1], lam)[0]
    return pred


def metrics(y, pred):
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    e = pred - y
    sst = float(((y - y.mean()) ** 2).sum())
    ssr = float((e ** 2).sum())
    return {
        "n": int(len(y)),
        "mae": float(np.abs(e).mean()),
        "rmse": float(math.sqrt((e ** 2).mean())),
        "r2": float(1 - ssr / sst) if sst > 0 else float("nan"),
        "bias": float(e.mean()),
        "spearman": spearman(pred, y),
    }


def _rank(v):
    order = np.argsort(v, kind="mergesort")
    rk = np.empty(len(v), float)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        rk[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return rk


def spearman(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ra, rb = _rank(a), _rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    den = math.sqrt(float((ra ** 2).sum() * (rb ** 2).sum()))
    return float((ra * rb).sum() / den) if den else float("nan")


def r2(y, pred):
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    sst = ((y - y.mean()) ** 2).sum()
    return float(1 - ((pred - y) ** 2).sum() / sst) if sst > 0 else float("nan")


def mae(y, pred):
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    return float(np.abs(pred - y).mean())


def boot_ci(values, n_boot=5000, seed=SEED):
    rng = np.random.default_rng(seed)
    values = np.asarray(values, float)
    n = len(values)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = values[idx].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def paired_boot(per_mol_a, per_mol_b, n_boot=5000, seed=SEED):
    """per-molecule absolute errors; delta = a - b, positive => b better."""
    d = np.asarray(per_mol_a, float) - np.asarray(per_mol_b, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    m = d[idx].mean(axis=1)
    return {
        "mean_delta_mae": float(d.mean()),
        "ci95": [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))],
        "frac_bootstrap_negative": float((m < 0).mean()),
        "n_a_worse_than_b": int((d > 0).sum()),
        "n": int(len(d)),
    }
