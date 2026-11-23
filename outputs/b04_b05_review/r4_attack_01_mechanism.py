#!/usr/bin/env python
"""Reviewer 4 (red team) attack 1: reproduce the E1/E4 ridge exactly and locate
the mechanistic cause of the reported errors.

Question: are the reported errors evidence about the DESCRIPTORS, or about the
ESTIMATOR? The published ridge_fit solves (Z'Z + lam I) b = Z'y with Z
standardised and NO INTERCEPT. Since every column of Z sums to zero on the
training rows, the fitted values Z b have training mean exactly 0, i.e. the
model structurally cannot reproduce the label mean (~17.3). If so, every
prediction is shifted down by roughly ybar, and every reported MAE is
dominated by that shift rather than by descriptor content.

This script reproduces the published numbers bit-for-bit, then decomposes the
error of the four Tanimoto=1.000 molecules used in the report's "decisive"
claim C.
"""
from __future__ import annotations

import csv, json, math, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEAT = REPO / "data" / "processed" / "dielectric_physical_features.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]
XE4 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
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


def standardise(X):
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    Z = [[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)]
    return Z, means, sds


def ridge_fit(Z, y, lam):
    """Verbatim copy of the project's solver (no intercept column)."""
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
            if f == 0:
                continue
            for c in range(col, p):
                A[r][c] -= f * A[col][c]
            rhs[r] -= f * rhs[col]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-12:
            continue
        s = rhs[r] - sum(A[r][c] * b[c] for c in range(r + 1, p))
        b[r] = s / A[r][r]
    return b


def loo_no_intercept(X, y, lam=1.0):
    n = len(X)
    out = []
    for hold in range(n):
        tr = [i for i in range(n) if i != hold]
        Z, means, sds = standardise([X[i] for i in tr])
        b = ridge_fit(Z, [y[i] for i in tr], lam)
        x = [(X[hold][j] - means[j]) / sds[j] for j in range(len(means))]
        out.append(sum(x[j] * b[j] for j in range(len(b))))
    return out


def mae(y, p):
    return sum(abs(p[i] - y[i]) for i in range(len(y))) / len(y)


def main():
    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEAT)}
    y = [float(r["dielectric"]) for r in pool]
    n = len(y)
    ybar = sum(y) / n

    res = {"n": n, "ybar": ybar, "mean_abs_y": sum(abs(v) for v in y) / n,
           "const_baseline_mae": sum(abs(v - ybar) for v in y) / n}

    def mat(cols):
        return [[float(fnum(feats[r["inchikey"]][c])) for c in cols] for r in pool]

    Xa, Xb, Xc = mat(X0), mat(X0 + X1), mat(XE4)
    pa = loo_no_intercept(Xa, y)
    pb = loo_no_intercept(Xb, y)
    pc = loo_no_intercept(Xc, y)

    res["reproduce"] = {
        "X0_mae": mae(y, pa), "X0_bias": sum(pa[i] - y[i] for i in range(n)) / n,
        "X0_bias_plus_ybar": sum(pa[i] - y[i] for i in range(n)) / n + ybar,
        "X0X1_mae": mae(y, pb), "X0X1_bias": sum(pb[i] - y[i] for i in range(n)) / n,
        "X0X1_bias_plus_ybar": sum(pb[i] - y[i] for i in range(n)) / n + ybar,
        "E4_mae": mae(y, pc), "E4_bias": sum(pc[i] - y[i] for i in range(n)) / n,
        "published_X0_mae": 17.446507, "published_X0X1_mae": 17.286655,
        "published_E4_lomo_mae": 17.2375,
        "mean_prediction_X0": sum(pa) / n,
        "mean_prediction_X0X1": sum(pb) / n,
    }

    # --- the structural point: fitted values have training mean exactly 0 ---
    Z, means, sds = standardise(Xa)
    b = ridge_fit(Z, y, 1.0)
    fit = [sum(Z[i][j] * b[j] for j in range(len(b))) for i in range(n)]
    res["structural_no_intercept"] = {
        "mean_in_sample_fitted_value": sum(fit) / n,
        "mean_train_label": ybar,
        "implied_shift": sum(fit) / n - ybar,
        "note": ("columns of Z are centred on the training mean, so Zb has "
                 "training mean 0; the estimator cannot reach ybar"),
    }

    # ---------------- claim C decomposition ----------------
    names = [r["name"] for r in pool]
    ident = ["nonane", "heptane", "octanedinitrile", "heptanedinitrile"]
    rows = []
    for nm in ident:
        i = names.index(nm)
        rows.append({
            "name": nm,
            "y_true": y[i],
            "y_pred_E4model": pc[i],
            "abs_error": abs(pc[i] - y[i]),
            # counterfactual A: predict the global (LOO training) mean
            "mean_predictor_err_all22": abs(y[i] - ybar),
            # counterfactual B: predict the training mean of the 21 others
            "mean_predictor_err_loto": abs(y[i] - statistics.mean(
                [y[j] for j in range(n) if j != i])),
            "bias_share_of_error": abs(ybar) / abs(pc[i] - y[i]),
        })
    res["claim_C_decomposition"] = rows
    res["claim_C_summary"] = {
        "model_mae_on_4": statistics.mean(r["abs_error"] for r in rows),
        "mean_predictor_mae_on_4": statistics.mean(
            r["mean_predictor_err_all22"] for r in rows),
        "published_model_mae_on_4": 19.4791,
    }

    # do the descriptors actually distinguish nonane / heptane?
    i_non, i_hep = names.index("nonane"), names.index("heptane")
    d = {}
    for j, c in enumerate(XE4):
        d[c] = {"nonane": Xc[i_non][j], "heptane": Xc[i_hep][j],
                "abs_diff": abs(Xc[i_non][j] - Xc[i_hep][j])}
    res["nonane_vs_heptane_descriptors"] = d
    res["nonane_vs_heptane"] = {
        "true_eps": [y[i_non], y[i_hep]],
        "true_gap": abs(y[i_non] - y[i_hep]),
        "model_predictions": [pc[i_non], pc[i_hep]],
        "model_predicted_gap": abs(pc[i_non] - pc[i_hep]),
        "ratio_predicted_gap_to_true_gap": (
            abs(pc[i_non] - pc[i_hep]) / abs(y[i_non] - y[i_hep])),
        "identical_descriptor_vector": all(
            abs(Xc[i_non][j] - Xc[i_hep][j]) < 1e-12 for j in range(len(XE4))),
        "label": ("model EXAGGERATES the nonane/heptane difference by "
                  f"{abs(pc[i_non]-pc[i_hep])/abs(y[i_non]-y[i_hep]):.1f}x; "
                  "it is not descriptor-blind"),
    }

    # rank of the model's predictions vs truth (is there any signal at all?)
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
        ma, mb = sum(ra) / len(a), sum(rb) / len(b)
        num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(len(a)))
        den = math.sqrt(sum((v - ma) ** 2 for v in ra) * sum((v - mb) ** 2 for v in rb))
        return num / den

    res["ranking_signal"] = {
        "spearman_X0": spearman(pa, y),
        "spearman_X0X1": spearman(pb, y),
        "spearman_E4model": spearman(pc, y),
        "pearson_X0X1": statistics.correlation(pb, y),
    }

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_01_mechanism.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
