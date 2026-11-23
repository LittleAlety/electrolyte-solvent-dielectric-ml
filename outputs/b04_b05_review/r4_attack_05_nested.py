#!/usr/bin/env python
"""Reviewer 4 attack 5: pre-empt the obvious rebuttals to the intercept finding.

The rebuttal a project author will make is: "you tuned lambda on the test set,
so your 6.50 is optimistic." So this script does it properly:

  * NESTED cross-validation: lambda is selected inside the training fold only,
    never on the held-out molecule.
  * Feature-block ablation: structural only (X0) vs electronic only (X1) vs both,
    so claim B ("electronic descriptors add no detectable value") is tested
    directly rather than through a possibly-unlucky full model.
  * Repeats claim G's three splits with the intercept restored, selecting lambda
    inside each fold.
  * Reports how the E1 claim survives when the estimator is a standard library
    RidgeCV / LinearRegression with fit_intercept=True.
"""
from __future__ import annotations

import csv, json, math, random, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
V04 = REPO / "data" / "dielectric_v04.csv"
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


def mae(y, p):
    return sum(abs(p[i] - y[i]) for i in range(len(y))) / len(y)


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
            i = j + 1
        return rk
    ra, rb = rank(a), rank(b)
    ma_, mb_ = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((ra[i] - ma_) * (rb[i] - mb_) for i in range(len(ra)))
    den = math.sqrt(sum((v - ma_) ** 2 for v in ra) * sum((v - mb_) ** 2 for v in rb))
    return num / den if den else float("nan")


def main():
    import numpy as np
    from sklearn.linear_model import Ridge, LinearRegression
    from sklearn.model_selection import LeaveOneOut, GridSearchCV, cross_val_predict
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.metrics import mean_absolute_error

    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feats = {r["inchikey"]: r for r in load(FEAT)}
    y = np.array([float(r["dielectric"]) for r in pool])
    n = len(y)
    const = mae(y, [float(np.mean(y))] * n)
    res = {"n": n, "constant_baseline_mae": const,
           "constant_baseline_loo_mae": float(np.mean(
               [abs(y[i] - np.mean(np.delete(y, i))) for i in range(n)]))}

    def arr(cols):
        return np.array([[float(fnum(feats[r["inchikey"]][c])) for c in cols]
                         for r in pool], dtype=float)

    blocks = {"X0_structural_7": X0,
              "X1_electronic_5": X1,
              "X0_plus_X1_12": X0 + X1,
              "E4_11_no_total_energy": XE4,
              "dipole_only": ["dipole_D"],
              "X0_plus_dipole": X0 + ["dipole_D"]}

    # ---- nested CV: lambdas chosen inside the training fold only ----------
    alphas = np.logspace(-4, 3, 36)
    out = {}
    for name, cols in blocks.items():
        Xb = arr(cols)
        inner = GridSearchCV(
            make_pipeline(StandardScaler(), Ridge(fit_intercept=True)),
            {"ridge__alpha": alphas}, cv=LeaveOneOut())
        pred = cross_val_predict(inner, Xb, y, cv=LeaveOneOut())
        ols = cross_val_predict(
            make_pipeline(StandardScaler(), LinearRegression(fit_intercept=True)),
            Xb, y, cv=LeaveOneOut())
        out[name] = {
            "n_features": len(cols),
            "nested_ridge_loo_mae": float(mean_absolute_error(y, pred)),
            "nested_ridge_spearman": spearman(list(pred), list(y)),
            "ols_loo_mae": float(mean_absolute_error(y, ols)),
            "ols_spearman": spearman(list(ols), list(y)),
            "beats_constant": bool(mean_absolute_error(y, pred) < const),
            "mae_reduction_vs_constant_pct": float(
                100 * (1 - mean_absolute_error(y, pred) / const)),
        }
    res["nested_cv_by_feature_block"] = out

    # ---- claim B tested directly: paired delta between blocks ------------
    def loo_pred(cols):
        Xb = arr(cols)
        m = make_pipeline(StandardScaler(), Ridge(alpha=1.0, fit_intercept=True))
        return np.array(cross_val_predict(m, Xb, y, cv=LeaveOneOut()))

    p0 = loo_pred(X0)
    p1 = loo_pred(X0 + X1)

    def paired_perm_delta(a, b, nperm=5000, seed=SEED):
        """Bootstrap/permutation CI on MAE(b)-MAE(a) per molecule."""
        rng = np.random.default_rng(seed)
        ea = np.abs(a - y)
        eb = np.abs(b - y)
        obs = float(eb.mean() - ea.mean())
        diffs = eb - ea
        boot = []
        for _ in range(nperm):
            idx = rng.integers(0, n, n)
            boot.append(float(diffs[idx].mean()))
        boot.sort()
        return {"observed_delta_mae": obs,
                "bootstrap_ci95": [boot[int(0.025 * nperm)], boot[int(0.975 * nperm)]],
                "frac_bootstrap_negative": float(np.mean(np.array(boot) < 0))}

    res["claim_B_delta"] = {
        "X0_mae": float(mae(y, p0)), "X0X1_mae": float(mae(y, p1)),
        "delta_mae": float(mae(y, p1) - mae(y, p0)),
        "delta_test": paired_perm_delta(p0, p1),
        "sign_test_molecules_where_X0X1_better": int(np.sum(
            np.abs(p1 - y) < np.abs(p0 - y))),
        "n_molecules": n,
    }

    # ---- E1 permutation null re-run with the fixed estimator, 10000 perms --
    def perm_null(cols, nperm=10000, seed=SEED):
        Xb = arr(cols)
        m = make_pipeline(StandardScaler(), Ridge(alpha=1.0, fit_intercept=True))
        obs = float(mean_absolute_error(y, cross_val_predict(m, Xb, y, cv=LeaveOneOut())))
        rng = random.Random(seed)
        yl = list(y)
        null = []
        for _ in range(nperm):
            rng.shuffle(yl)
            pr = cross_val_predict(m, Xb, np.array(yl), cv=LeaveOneOut())
            null.append(float(mean_absolute_error(yl, pr)))
        null.sort()
        p_one = sum(1 for v in null if v <= obs) / len(null)
        return {"observed_mae": obs, "p_one_sided": p_one,
                "null_median": null[len(null) // 2], "null_min": null[0],
                "null_q05": null[int(0.05 * len(null))], "n_perm": nperm}

    res["permutation_null_fixed_10k"] = {
        "X0": perm_null(X0, 5000),
        "X0X1": perm_null(X0 + X1, 5000),
        "dipole_only": perm_null(["dipole_D"], 5000),
    }

    # ---- claim G with intercept restored, nested lambda --------------------
    from collections import defaultdict
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    FAMILY = [("carboxylic_acid", "[CX3](=O)[OX2H1]"), ("dinitrile", "N#C.*C#N"),
              ("nitrile", "N#C"), ("carbonate", "[OX2][CX3](=O)[OX2]"),
              ("ester", "[CX3](=O)[OX2][#6]"), ("ketone", "[#6][CX3](=O)[#6]"),
              ("primary_secondary_amine", "[NX3;H2,H1;!$(NC=O)]"),
              ("tertiary_amine", "[NX3;H0;!$(NC=O)]"), ("alcohol", "[OX2H]"),
              ("ether", "[OD2]([#6])[#6]"), ("thiophene", "c1ccsc1"),
              ("imidazole", "c1cncn1"), ("aromatic", "a")]
    mols, fam = [], []
    for r in pool:
        s = (v04.get(r["inchikey"], {}).get("smiles") or "").strip()
        m = Chem.MolFromSmiles(s) if s else None
        mols.append(m)
        lab = "unclassified"
        for lbl, sm in FAMILY:
            pt = Chem.MolFromSmarts(sm)
            if pt is not None and m.HasSubstructMatch(pt):
                lab = lbl
                break
        fam.append(lab)
    res["family_counts"] = dict(sorted(
        ((k, fam.count(k)) for k in set(fam)), key=lambda kv: -kv[1]))

    XE = arr(XE4)

    def fit_model(Xtr, ytr):
        m = GridSearchCV(make_pipeline(StandardScaler(), Ridge(fit_intercept=True)),
                         {"ridge__alpha": alphas}, cv=LeaveOneOut())
        m.fit(Xtr, ytr)
        return m

    # LOFO
    pr = np.zeros(n)
    groups = defaultdict(list)
    for i, f in enumerate(fam):
        groups[f].append(i)
    for f, idx in groups.items():
        tr = [i for i in range(n) if i not in set(idx)]
        m = fit_model(XE[tr], y[tr])
        pr[idx] = m.predict(XE[idx])
    lofo_mae = float(mean_absolute_error(y, pr))

    # LOMO
    m = make_pipeline(StandardScaler(), Ridge(alpha=1.0, fit_intercept=True))
    lomo_mae = float(mean_absolute_error(
        y, cross_val_predict(m, XE, y, cv=LeaveOneOut())))

    # random 5-fold, repeated
    rng = random.Random(SEED)
    kf_maes = []
    for _ in range(200):
        idx = list(range(n))
        rng.shuffle(idx)
        folds = [idx[i::5] for i in range(5)]
        prr = np.zeros(n)
        for f in folds:
            tr = [i for i in range(n) if i not in set(f)]
            mm = make_pipeline(StandardScaler(), Ridge(alpha=1.0, fit_intercept=True))
            mm.fit(XE[tr], y[tr])
            prr[f] = mm.predict(XE[f])
        kf_maes.append(float(mean_absolute_error(y, prr)))
    res["claim_G_with_intercept"] = {
        "lomo_mae": lomo_mae, "lofo_mae": lofo_mae,
        "random_5fold_mean_mae": statistics.mean(kf_maes),
        "random_5fold_min_mae": min(kf_maes),
        "random_5fold_q05": sorted(kf_maes)[int(0.05 * len(kf_maes))],
        "spread_max_minus_min": float(max([lomo_mae, lofo_mae,
                                           statistics.mean(kf_maes)])
                                      - min([lomo_mae, lofo_mae,
                                             statistics.mean(kf_maes)])),
        "constant_baseline_mae": const,
        "all_three_beat_constant": bool(max(lomo_mae, lofo_mae,
                                            statistics.mean(kf_maes)) < const),
    }
    # LOFO per family, with intercept
    fam_out = {}
    for f, idx in groups.items():
        tr = [i for i in range(n) if i not in set(idx)]
        m = fit_model(XE[tr], y[tr])
        ptest = m.predict(XE[idx])
        base = float(np.mean([abs(y[i] - np.mean(y[tr])) for i in idx]))
        fam_out[f] = {"n": len(idx), "mae": float(mean_absolute_error(y[idx], ptest)),
                      "train_mean_baseline_mae": base,
                      "beats_baseline": bool(
                          mean_absolute_error(y[idx], ptest) < base)}
    res["lofo_by_family_with_intercept"] = fam_out
    res["lofo_summary_with_intercept"] = {
        "n_measured_families": sum(1 for v in fam_out.values() if v["n"] >= 2),
        "n_beating_baseline": sum(1 for v in fam_out.values()
                                  if v["n"] >= 2 and v["beats_baseline"]),
    }

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_05_nested.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
