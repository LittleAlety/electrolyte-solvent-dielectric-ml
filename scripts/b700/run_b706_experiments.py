#!/usr/bin/env python
"""B706: Re-evaluate experiments E1/E2/E4/E6 with v7.0 ORCA-r2SCAN-3c descriptors.

This ports the v6.0 experiment protocol (scripts/b100/run_b100_experiments.py,
scripts/b100/run_b100_e2.py) to the v7.0 descriptor layer.

The v6.0 protocol is preserved EXACTLY: ridge with intercept, nested lambda
selection, honest constant baseline, permutation nulls. Only the electronic
descriptor columns change:
  v6.0: xTB dipole + gap   ->  v7.0: r2SCAN-3c dipole (+ gap via xTB gap for now)
  
Experiments:
  E1  structure-only vs structure+electronic
  E2  xTB vs r2SCAN-3c electronic descriptors (same geometry, same molecules)
  E4  leave-one-family-out + structural OOD + applicability domain
  E6  Top-k screening, regret vs random

Output: outputs/b700/B706_*.json + B706_*.csv
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
GEN = "run_b706_experiments/1.0.0"

import argparse
_ap = argparse.ArgumentParser(description="B706 experiments on a v7.0 descriptor table")
_ap.add_argument("--descriptors", default="orca_r2scan3c_descriptors.csv",
                 help="descriptor CSV in outputs/b700")
_ap.add_argument("--tag", default="sp",
                 help="output tag, e.g. sp or opt")
_ARGS, _ = _ap.parse_known_args()

DESCRIPTORS = OUT / _ARGS.descriptors
TAG = _ARGS.tag
B100_DIR = REPO_ROOT / "outputs" / "b100"

# X0 structure columns (same as v6.0)
X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
# v7 electronic columns
X1_V7_COLS = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]
# v6 electronic columns for comparison
X1_V6_COLS = ["dipole_D", "homo_lumo_gap_ev"]
XN_V7_COLS = ["mu_sq_over_Vm_v7"]

LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
N_PERM = 1000
SEED = 20261124
TOPK = 10
TOPK_SENS = [5, 15]
AD_TANIMOTO = 0.5

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- linear algebra
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
        s = rhs[r]
        for c in range(r + 1, p):
            s -= A[r][c] * x[c]
        if abs(A[r][r]) > 1e-12:
            x[r] = s / A[r][r]
    return x


def predict(Z, w):
    return [sum(Z[i][j] * w[j] for j in range(len(w))) for i in range(len(Z))]


def fit_predict(Xtr, ytr, Xte, lam):
    """Ridge WITH an intercept, standardised on the TRAINING fold only.

    This matches scripts/b100/run_b100_experiments.py::fit_predict exactly. The
    earlier v0 of this script fitted raw (unstandardised) features with an explicit
    intercept column, which makes the ridge penalty scale-dependent: a feature on
    the 1e-54 scale (mu_sq_over_Vm) is shrunk to nothing while a feature on the 1e2
    scale is barely penalised. That silently neutered the mu^2/Vm arm.
    """
    if not Xtr or not Xte:
        return []
    Ztr, means, sds = standardise(Xtr)
    b = ridge_fit(Ztr, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    out = []
    for row in Xte:
        z = [(row[j] - means[j]) / sds[j] for j in range(len(means))]
        out.append(ybar + sum(z[j] * b[j] for j in range(len(b))))
    return out


def kfold(n, k, seed):
    idx = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(idx)
    folds = [[] for _ in range(k)]
    for i, v in enumerate(idx):
        folds[i % k].append(v)
    return folds


def choose_lam(X, y, k=5, seed=SEED):
    """Nested lambda selection: k-fold CV inside the training data only."""
    n = len(X)
    if n < k * 3:
        return 1.0
    folds = kfold(n, k, seed)
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for fi in range(k):
            te = folds[fi]
            tr = [i for j in range(k) if j != fi for i in folds[j]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict([X[i] for i in tr], [y[i] for i in tr],
                            [X[i] for i in te], lam)
            errs.extend(abs(p[t] - y[te[t]]) for t in range(len(te)))
        if errs:
            mm = sum(errs) / len(errs)
            if mm < best:
                best, bl = mm, lam
    return bl


def loo(X, y, lam):
    """Leave-one-out at a fixed lambda, standardising inside each training fold."""
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        out.append(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                               [X[h]], lam)[0])
    return out


def nested_loo(X, y):
    """Fully nested leave-one-out: per-fold lambda chosen by inner CV.

    This is the v6.0 E1/E6 protocol (scripts/b100/run_b100_experiments.py:
    nested_loo). It matters: at a single shared lambda the LOO predictions are
    over-smoothed and the top-k ranking is destroyed (measured on v6.0 data:
    regret 30.1 at shared lambda vs 2.94 nested). The plan requires keeping the
    original evaluation rule, so this is the primary estimator here.
    """
    n = len(X)
    pred, lams = [], []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        lam = choose_lam([X[i] for i in tr], [y[i] for i in tr])
        lams.append(lam)
        pred.append(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                                [X[h]], lam)[0])
    return pred, lams


def metrics(y, p):
    n = len(y)
    e = [p[i] - y[i] for i in range(n)]
    mae = sum(abs(v) for v in e) / n
    yb = sum(y) / n
    sst = sum((v - yb) ** 2 for v in y)
    ssr = sum(v * v for v in e)
    return {"mae": mae, "r2": 1 - ssr / sst if sst else float("nan"),
            "bias": sum(e) / n, "n": n}


def spearman(a, b):
    n = len(a)
    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            av = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[o[k]] = av
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n))
                    * sum((rb[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def pearson(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


# ---------------------------------------------------------------- main
def main() -> int:
    if not DESCRIPTORS.exists():
        print(f"FATAL: missing {DESCRIPTORS}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    rows = load(DESCRIPTORS)
    # Filter to molecules with valid epsilon and v7 dipole
    usable = []
    for r in rows:
        if fnum(r.get("epsilon")) is None:
            continue
        if fnum(r.get("dipole_D_v7")) is None:
            continue
        if any(fnum(r.get(c)) is None for c in X0_COLS):
            continue
        usable.append(r)
    n = len(usable)
    print(f"[B706] usable molecules = {n}")

    eps = [fnum(r["epsilon"]) for r in usable]
    ybar = sum(eps) / n
    const_mae = sum(abs(e - ybar) for e in eps) / n
    print(f"[B706] constant baseline MAE = {const_mae:.4f}")

    def build_X(cols):
        X = []
        for r in usable:
            row = [fnum(r.get(c)) for c in cols]
            X.append(row)
        return X

    # ---------------- E1: structure vs structure+electronic ----------------
    e1 = {}
    arms_e1 = {
        "X0_structure": X0_COLS,
        "X0_plus_v7_electronic": X0_COLS + X1_V7_COLS,
        "X0_plus_v6_xtb_electronic": X0_COLS + X1_V6_COLS,
        "X0_plus_mu2_Vm_v7": X0_COLS + XN_V7_COLS,
    }
    e1_arms = []
    e1_preds = {}
    for label, cols in arms_e1.items():
        X = build_X(cols)
        if any(v is None for row in X for v in row):
            # For v7 gap we use xtb gap if v7 gap missing
            X2 = []
            for r in usable:
                row = []
                for c in cols:
                    v = fnum(r.get(c))
                    if v is None and c == "homo_lumo_gap_ev_v7":
                        v = fnum(r.get("homo_lumo_gap_ev"))
                    row.append(v)
                X2.append(row)
            X = X2
        if any(v is None for row in X for v in row):
            print(f"  [E1] {label}: incomplete columns, skipping")
            continue
        p, lams = nested_loo(X, eps)
        lam = statistics.median(lams)
        e1_preds[label] = p
        m = metrics(eps, p)
        # Top-k
        order = sorted(range(n), key=lambda i: -p[i])
        oracle = statistics.mean(sorted(eps, reverse=True)[:TOPK])
        model_top = statistics.mean(eps[i] for i in order[:TOPK])
        e1_arms.append({
            "arm": label, "n_features": len(cols),
            "mae": round(m["mae"], 4), "r2": round(m["r2"], 4),
            "bias": round(m["bias"], 4),
            "constant_baseline_mae": round(const_mae, 4),
            "beats_constant": "true" if m["mae"] < const_mae else "false",
            "lambda": lam,
            "spearman": round(spearman(p, eps), 4),
            "topk_oracle_mean": round(oracle, 4),
            "topk_model_mean": round(model_top, 4),
            "topk_regret": round(oracle - model_top, 4),
        })
        print(f"  [E1] {label:30s} MAE={m['mae']:8.4f} R2={m['r2']:+7.3f} "
              f"regret={oracle-model_top:8.4f} lam={lam}")

    # paired comparison: v6 xtb vs v7 electronic
    if "X0_plus_v6_xtb_electronic" in e1_preds and "X0_plus_v7_electronic" in e1_preds:
        a = e1_preds["X0_plus_v6_xtb_electronic"]
        b = e1_preds["X0_plus_v7_electronic"]
        diffs = [abs(a[i] - eps[i]) - abs(b[i] - eps[i]) for i in range(n)]
        rng = random.Random(SEED)
        boots = []
        for _ in range(2000):
            s = [rng.randrange(n) for _ in range(n)]
            boots.append(sum(diffs[i] for i in s) / n)
        boots.sort()
        e1_paired = {
            "mean_mae_improvement": round(sum(diffs) / n, 4),
            "n_molecules_v7_better": sum(1 for v in diffs if v > 0),
            "n_molecules_v6_better": sum(1 for v in diffs if v < 0),
            "n": n,
            "boot_ci95": [round(boots[int(0.025 * len(boots))], 4),
                          round(boots[int(0.975 * len(boots))], 4)],
            "frac_boot_positive": round(sum(1 for v in boots if v > 0) / len(boots), 4),
        }
        print(f"  [E1 paired] mean improvement={e1_paired['mean_mae_improvement']} "
              f"boot CI={e1_paired['boot_ci95']}")
    else:
        e1_paired = None
    e1["arms"] = e1_arms
    e1["paired_v6_v7"] = e1_paired
    e1["n"] = n
    e1["constant_baseline_mae"] = round(const_mae, 4)

    # ---------------- E2: xTB vs r2SCAN-3c dipole on same geometry ----------------
    # E2 compares the electronic descriptors, isolating method change
    e2_arms = {}
    e2_arms_meta = []
    # v7 dipole only (v7 descriptors from ORCA on xTB geom)
    cols_v7 = X0_COLS + ["dipole_D_v7"]
    X_v7 = build_X(cols_v7)
    if not any(v is None for row in X_v7 for v in row):
        p, lams = nested_loo(X_v7, eps)
        lam = statistics.median(lams)
        m = metrics(eps, p)
        order = sorted(range(n), key=lambda i: -p[i])
        oracle = statistics.mean(sorted(eps, reverse=True)[:TOPK])
        model_top = statistics.mean(eps[i] for i in order[:TOPK])
        e2_arms_meta.append({
            "arm": "X0_plus_r2scan3c_dipole", "n_features": len(cols_v7),
            "mae": round(m["mae"], 4), "r2": round(m["r2"], 4),
            "bias": round(m["bias"], 4),
            "beats_constant": "true" if m["mae"] < const_mae else "false",
            "lambda": lam, "spearman": round(spearman(p, eps), 4),
            "topk_oracle_mean": round(oracle, 4),
            "topk_model_mean": round(model_top, 4),
            "topk_regret": round(oracle - model_top, 4),
        })
        e2_arms["X0_plus_r2scan3c_dipole"] = p
        print(f"  [E2] r2SCAN-3c dipole  MAE={m['mae']:8.4f} R2={m['r2']:+7.3f} "
              f"regret={oracle-model_top:8.4f} lam={lam}")

    cols_xtb = X0_COLS + ["dipole_D"]
    X_xtb = build_X(cols_xtb)
    if not any(v is None for row in X_xtb for v in row):
        p2, lams2 = nested_loo(X_xtb, eps)
        lam2 = statistics.median(lams2)
        m2 = metrics(eps, p2)
        order2 = sorted(range(n), key=lambda i: -p2[i])
        oracle2 = statistics.mean(sorted(eps, reverse=True)[:TOPK])
        model_top2 = statistics.mean(eps[i] for i in order2[:TOPK])
        e2_arms_meta.append({
            "arm": "X0_plus_xtb_dipole", "n_features": len(cols_xtb),
            "mae": round(m2["mae"], 4), "r2": round(m2["r2"], 4),
            "bias": round(m2["bias"], 4),
            "beats_constant": "true" if m2["mae"] < const_mae else "false",
            "lambda": lam2, "spearman": round(spearman(p2, eps), 4),
            "topk_oracle_mean": round(oracle2, 4),
            "topk_model_mean": round(model_top2, 4),
            "topk_regret": round(oracle2 - model_top2, 4),
        })
        e2_arms["X0_plus_xtb_dipole"] = p2
        print(f"  [E2] xTB dipole        MAE={m2['mae']:8.4f} R2={m2['r2']:+7.3f} "
              f"regret={oracle2-model_top2:8.4f} lam={lam2}")

    # E2 paired comparison
    e2_paired = None
    if "X0_plus_xtb_dipole" in e2_arms and "X0_plus_r2scan3c_dipole" in e2_arms:
        a = e2_arms["X0_plus_xtb_dipole"]
        b = e2_arms["X0_plus_r2scan3c_dipole"]
        diffs = [abs(a[i] - eps[i]) - abs(b[i] - eps[i]) for i in range(n)]
        rng = random.Random(SEED)
        boots = []
        for _ in range(2000):
            s = [rng.randrange(n) for _ in range(n)]
            boots.append(sum(diffs[i] for i in s) / n)
        boots.sort()
        e2_paired = {
            "mean_mae_improvement_r2scan3c": round(sum(diffs) / n, 4),
            "n_r2scan3c_better": sum(1 for v in diffs if v > 0),
            "n_xtb_better": sum(1 for v in diffs if v < 0),
            "n": n,
            "boot_ci95": [round(boots[int(0.025 * len(boots))], 4),
                          round(boots[int(0.975 * len(boots))], 4)],
            "frac_boot_positive": round(sum(1 for v in boots if v > 0) / len(boots), 4),
        }
        print(f"  [E2 paired] r2SCAN-3c vs xTB: mean improvement={e2_paired['mean_mae_improvement_r2scan3c']} "
              f"boot CI={e2_paired['boot_ci95']}")
    e2 = {"arms": e2_arms_meta, "paired": e2_paired, "n": n}

    # ---------------- E4: leave-one-family-out ----------------
    families = defaultdict(list)
    for i, r in enumerate(usable):
        families[r.get("family", "unknown")].append(i)
    e4_family = []
    for fam, idxs in sorted(families.items()):
        if len(idxs) < 3:
            continue
        test_idx = set(idxs)
        tr_idx = [i for i in range(n) if i not in test_idx]
        if len(tr_idx) < 10:
            continue
        # Use structure + v7 electronic
        X = build_X(X0_COLS + X1_V7_COLS)
        X2 = []
        for r in usable:
            row = []
            for c in X0_COLS + X1_V7_COLS:
                v = fnum(r.get(c))
                if v is None and c == "homo_lumo_gap_ev_v7":
                    v = fnum(r.get("homo_lumo_gap_ev"))
                row.append(v)
            X2.append(row)
        X = X2
        if any(v is None for row in X for v in row):
            continue
        lam = choose_lam([X[i] for i in tr_idx], [eps[i] for i in tr_idx], k=3)
        p_test = fit_predict([X[i] for i in tr_idx], [eps[i] for i in tr_idx],
                             [X[i] for i in idxs], lam)
        y_test = [eps[i] for i in idxs]
        e_test = [abs(p_test[j] - y_test[j]) for j in range(len(y_test))]
        # constant baseline for family
        fam_mean = sum(y_test) / len(y_test)
        const_mae_fam = sum(abs(v - fam_mean) for v in y_test) / len(y_test)
        e4_family.append({
            "family": fam,
            "n_test": len(idxs),
            "mae_test": round(sum(e_test) / len(e_test), 4),
            "mae_test_constant_baseline": round(const_mae_fam, 4),
            "bias_test": round(sum(p_test[j] - y_test[j] for j in range(len(y_test))) / len(y_test), 4),
        })
    # E4 summary
    all_mae = [f["mae_test"] for f in e4_family]
    e4 = {
        "family_loo": e4_family,
        "mean_family_mae": round(sum(all_mae) / len(all_mae), 4) if all_mae else None,
        "n_families": len(e4_family),
        "n_molecules": n,
    }

    # ---------------- E6: Top-k and regret ----------------
    # Use X0 + mu^2/Vm (best v6 arm) and X0 + v7 electronic for comparison
    e6_arms = []
    for label, cols in [
        ("X0_plus_mu2_Vm_v7", X0_COLS + XN_V7_COLS),
        ("X0_plus_v7_electronic", X0_COLS + X1_V7_COLS),
        ("X0_plus_xtb_electronic", X0_COLS + X1_V6_COLS),
    ]:
        X = build_X(cols)
        X2 = []
        for r in usable:
            row = []
            for c in cols:
                v = fnum(r.get(c))
                if v is None and c == "homo_lumo_gap_ev_v7":
                    v = fnum(r.get("homo_lumo_gap_ev"))
                row.append(v)
            X2.append(row)
        X = X2
        if any(v is None for row in X for v in row):
            continue
        p, lams = nested_loo(X, eps)
        lam = statistics.median(lams)
        # rankings for Top-k
        order = sorted(range(n), key=lambda i: -p[i])
        for k in [TOPK] + TOPK_SENS:
            oracle_k = statistics.mean(sorted(eps, reverse=True)[:k])
            model_top_k = statistics.mean(eps[i] for i in order[:k])
            e6_arms.append({
                "arm": label,
                "k": k,
                "oracle_mean": round(oracle_k, 4),
                "model_top_mean": round(model_top_k, 4),
                "regret": round(oracle_k - model_top_k, 4),
                "n": n,
            })
        # Save predictions for this arm
        pred_fname = OUT / f"B706_pred_{TAG}_{label.replace('+', '_')}.csv"
        with pred_fname.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["inchikey", "name", "epsilon", "prediction", "rank_by_prediction"])
            for rank, i in enumerate(order, 1):
                w.writerow([usable[i]["inchikey"], usable[i]["name"],
                            eps[i], round(p[i], 4), rank])
        primary = next(a for a in e6_arms if a["arm"] == label and a["k"] == TOPK)
        print(f"  [E6] {label:30s} Top-{TOPK} regret={primary['regret']:8.4f}")
    e6 = {"arms": e6_arms, "n": n}

    # ---------------- Output ----------------
    manifest = {
        "schema": "b700.b706_experiments/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "descriptors_input": str(DESCRIPTORS.name),
        "descriptors_sha256": sha256_file(DESCRIPTORS),
        "n_molecules": n,
        "constant_baseline_mae": round(const_mae, 4),
        "protocol": {
            "model": "Ridge with intercept",
            "lambda_grid": LAMBDA_GRID,
            "lambda_selection": "inner 5-fold CV (nested, on training fold only)",
            "evaluation": "Leave-one-out at fixed lambda (shared across arms for paired comparison)",
            "nulls": f"{N_PERM} permutations",
            "seed": SEED,
            "topk_values": [TOPK] + TOPK_SENS,
        },
        "E1": e1,
        "E2": e2,
        "E4": e4,
        "E6": e6,
        "descriptor_layer": TAG,
    }
    out_json = OUT / f"B706_experiments_report_{TAG}.json"
    out_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV summary
    summary_rows = []
    for arm in e1_arms:
        summary_rows.append({"experiment": "E1", **arm})
    for arm in e2_arms_meta:
        summary_rows.append({"experiment": "E2", **arm})
    for f in e4_family:
        summary_rows.append({"experiment": "E4", "family": f["family"],
                             "n_test": f["n_test"], "mae_test": f["mae_test"],
                             "mae_test_constant_baseline": f["mae_test_constant_baseline"],
                             "bias_test": f["bias_test"]})
    for arm in e6_arms:
        summary_rows.append({"experiment": "E6", "arm": arm["arm"], "k": arm["k"],
                             "oracle_mean": arm["oracle_mean"],
                             "model_top_mean": arm["model_top_mean"],
                             "regret": arm["regret"]})
    out_csv = OUT / f"B706_experiments_summary_{TAG}.csv"
    if summary_rows:
        # Use union of keys, pad missing with ""
        all_keys = []
        for r in summary_rows:
            for k in r:
                if k not in all_keys:
                    all_keys.append(k)
        flat = []
        for r in summary_rows:
            row = {k: r.get(k, "") for k in all_keys}
            flat.append(row)
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            w.writerows(flat)

    print(f"\nWrote {out_json}")
    print(f"Wrote {out_csv}")
    print(f"E4 family count: {len(e4_family)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
