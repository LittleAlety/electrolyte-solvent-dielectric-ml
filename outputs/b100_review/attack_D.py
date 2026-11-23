"""Attack D: cross-family generalisation, haloarbon failure, narrow-eps baseline artefact."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib as L

ROOT = Path(r"E:\Claude Code\电解质ML\电解质ML")
MATRIX = ROOT / "outputs" / "b100" / "model_matrix_b100.csv"
OUT = ROOT / "outputs" / "b100_review"

m = pd.read_csv(MATRIX)
ALL18 = L.X0_COLS + L.X1_COLS
common = m.dropna(subset=L.X0_COLS + L.X1_COLS + L.XN_COLS).reset_index(drop=True)
res = {}

fam_stats = {}
for fam, g in common.groupby("family"):
    eps = g.epsilon.to_numpy(float)
    fam_stats[fam] = {
        "n_common": int(len(g)),
        "eps_mean": float(eps.mean()), "eps_sd": float(eps.std(ddof=1)),
        "eps_min": float(eps.min()), "eps_max": float(eps.max()),
        "eps_cv": float(eps.std(ddof=1) / eps.mean()),
        "eps_iqr": float(np.percentile(eps, 75) - np.percentile(eps, 25)),
        "n_lt5": int((eps < 5).sum()),
    }
res["family_epsilon_stats"] = fam_stats
print(pd.DataFrame(fam_stats).T[["n_common", "eps_mean", "eps_sd", "eps_min", "eps_max", "eps_cv"]]
      .sort_values("eps_mean").to_string())

# ---------------------------------------------------------------- reproduce E4 (LOFO)
e4 = json.loads((ROOT / "outputs" / "b100" / "e4_manifest_b100.json").read_text(encoding="utf-8"))
published = {f["family"]: f for f in e4["families"]}

rows = []
fam_detail = {}
for fam, g in common.groupby("family"):
    if len(g) < 3:
        continue
    test_keys = set(g.inchikey)
    train = m[~m.inchikey.isin(test_keys)].dropna(subset=ALL18).reset_index(drop=True)
    if len(train) < 20:
        continue
    Xtr, ytr = train[ALL18].to_numpy(float), train.epsilon.to_numpy(float)
    Xte, yte = g[ALL18].to_numpy(float), g.epsilon.to_numpy(float)
    lam = L.choose_lambda(Xtr, ytr)
    pred = L._fit_predict(Xtr, ytr, Xte, lam)
    mm = L.metrics(yte, pred)
    tr_mean = ytr.mean()
    base = L.mae(yte, np.full(len(yte), tr_mean))
    pub = published.get(fam, {})
    # --- alternative baselines -------------------------------------------------
    own_mean = L.mae(yte, np.full(len(yte), yte.mean()))           # oracle family constant
    loo_const = []                                                  # nested in-family constant
    for i in range(len(yte)):
        loo_const.append(abs(yte[i] - np.delete(yte, i).mean()))
    loo_const = float(np.mean(loo_const))
    # in-family ridge LOO with the same 18 features (is the family intrinsically learnable?)
    in_fam = L.metrics(yte, L.nested_loo(Xte, yte)) if len(yte) >= 8 else None
    # best single feature, in-family LOO
    best_uni, best_uni_feat = None, None
    for c in ALL18:
        p = L.nested_loo(g[[c]].to_numpy(float), yte)
        v = L.mae(yte, p)
        if best_uni is None or v < best_uni:
            best_uni, best_uni_feat = v, c
    # oracle mean-shift correction of the transfer model
    shift = pred + (yte.mean() - pred.mean())
    shift_mae = L.mae(yte, shift)
    # linear recalibration (slope+intercept fitted on the test family, oracle, 2 params)
    A = np.vstack([np.ones_like(pred), pred]).T
    coef, *_ = np.linalg.lstsq(A, yte, rcond=None)
    recal_mae = L.mae(yte, A @ coef)
    rec = {
        "family": fam, "n_test": int(len(yte)), "n_train": int(len(ytr)),
        "published_mae": pub.get("mae"), "repro_mae": round(mm["mae"], 4),
        "published_baseline": pub.get("train_mean_baseline_mae"),
        "repro_train_mean_baseline": round(base, 4),
        "published_r2": pub.get("r2"), "repro_r2": round(mm["r2"], 4),
        "spearman": round(L.spearman(pred, yte), 4),
        "bias": round(float((pred - yte).mean()), 4),
        "family_mean": round(float(yte.mean()), 4),
        "family_sd": round(float(yte.std(ddof=1)), 4),
        "family_cv": round(float(yte.std(ddof=1) / yte.mean()), 4),
        "baseline_oracle_family_mean_mae": round(own_mean, 4),
        "baseline_nested_family_mean_mae": round(loo_const, 4),
        "in_family_ridge_loo_mae": round(in_fam["mae"], 4) if in_fam else None,
        "in_family_ridge_loo_r2": round(in_fam["r2"], 4) if in_fam else None,
        "in_family_best_single_feature": best_uni_feat,
        "in_family_best_single_feature_mae": round(best_uni, 4) if best_uni else None,
        "model_after_oracle_mean_shift_mae": round(shift_mae, 4),
        "model_after_oracle_linear_recal_mae": round(recal_mae, 4),
        "mae_over_family_sd": round(mm["mae"] / yte.std(ddof=1), 4),
    }
    rows.append(rec)
    fam_detail[fam] = rec

res["lofo"] = rows
print("\nLOFO reproduction + alternative baselines")
for r in sorted(rows, key=lambda z: -z["n_test"]):
    print(f"  {r['family']:22s} n={r['n_test']:3d} MAE={r['repro_mae']:7.3f} "
          f"(pub {r['published_mae']}) base={r['repro_train_mean_baseline']:6.3f} "
          f"famMean={r['baseline_oracle_family_mean_mae']:6.3f} "
          f"inFamLOO={r['in_family_ridge_loo_mae']} R2={r['repro_r2']:+.2f} "
          f"sd={r['family_sd']:.2f} bias={r['bias']:+.2f}")

# ---------------------------------------------------------------- halocarbon deep dive
hal = common[common.family == "halocarbon"].copy()
ytest = hal.epsilon.to_numpy(float)
train = m[~m.inchikey.isin(set(hal.inchikey))].dropna(subset=ALL18)
tr_mean = train.epsilon.mean()
Xtr_all, ytr_all = train[ALL18].to_numpy(float), train.epsilon.to_numpy(float)
lam = L.choose_lambda(Xtr_all, ytr_all)
pred = L._fit_predict(Xtr_all, ytr_all, hal[ALL18].to_numpy(float), lam)

hd = {
    "n_test": int(len(hal)), "train_mean": round(float(tr_mean), 4),
    "test_mean": round(float(ytest.mean()), 4),
    "test_sd": round(float(ytest.std(ddof=1)), 4),
    "test_min": round(float(ytest.min()), 4), "test_max": round(float(ytest.max()), 4),
    "test_iqr": round(float(np.percentile(ytest, 75) - np.percentile(ytest, 25)), 4),
    "test_cv": round(float(ytest.std(ddof=1) / ytest.mean()), 4),
    "model_mae": round(L.mae(ytest, pred), 4),
    "model_bias": round(float((pred - ytest).mean()), 4),
    "model_spearman": round(L.spearman(pred, ytest), 4),
    "baseline_global_train_mean_mae": round(L.mae(ytest, np.full(len(ytest), tr_mean)), 4),
    "baseline_family_mean_in_sample_mae": round(L.mae(ytest, np.full(len(ytest), ytest.mean())), 4),
    "baseline_family_mean_nested_mae": round(float(np.mean(
        [abs(ytest[i] - np.delete(ytest, i).mean()) for i in range(len(ytest))])), 4),
    "model_after_mean_shift_mae": round(L.mae(ytest, pred + (ytest.mean() - pred.mean())), 4),
    "pred_mean": round(float(pred.mean()), 4),
    "pred_sd": round(float(pred.std(ddof=1)), 4),
}
# in-family predictability
in_fam_pred = L.nested_loo(hal[ALL18].to_numpy(float), ytest)
hd["in_family_18feat_loo_mae"] = round(L.mae(ytest, in_fam_pred), 4)
hd["in_family_18feat_loo_r2"] = round(L.r2(ytest, in_fam_pred), 4)
uni = {}
for c in ALL18 + L.XN_COLS:
    p = L.nested_loo(hal[[c]].to_numpy(float), ytest)
    uni[c] = {"mae": round(L.mae(ytest, p), 4), "r2": round(L.r2(ytest, p), 4),
              "spearman": round(L.spearman(p, ytest), 4)}
hd["in_family_univariate"] = dict(sorted(uni.items(), key=lambda kv: kv[1]["mae"])[:6])
# 2-feature in-family
best2 = []
for a, b in [(a, b) for i, a in enumerate(ALL18) for b in ALL18[i + 1:]]:
    p = L.nested_loo(hal[[a, b]].to_numpy(float), ytest)
    best2.append((L.mae(ytest, p), a, b))
best2.sort()
hd["in_family_best_pair"] = [{"mae": round(v, 4), "cols": [a, b]} for v, a, b in best2[:3]]
# analytic halocarbon character of the family
hd["family_mix"] = {
    "n_with_halogen": int((hal.n_halogen > 0).sum()),
    "mean_halogen_count": round(float(hal.n_halogen.mean()), 2),
    "mean_polarizability": round(float(hal.polarizability_au.mean()), 2),
    "mean_dipole": round(float(hal.dipole_D.mean()), 3),
    "mean_molar_volume": round(float(hal.molar_volume_m3_mol.mean() * 1e6), 2),
}
res["halocarbon"] = hd
print("\nHALOCARBON:", json.dumps(hd, indent=1, default=float)[:1800])

# ---------------------------------------------------------------- is epsilon-mean the explanation?
xs = np.array([fam_detail[f]["family_mean"] for f in fam_detail])
ys = np.array([fam_detail[f]["mae_over_family_sd"] for f in fam_detail])
ss = np.array([fam_detail[f]["in_family_ridge_loo_mae"] for f in fam_detail])
res["cross_family_relationship"] = {
    "families": list(fam_detail),
    "spearman_MAE_vs_family_mean_eps": round(L.spearman(xs, ys), 4),
    "spearman_MAE_vs_family_sd": round(L.spearman(
        np.array([fam_detail[f]["family_sd"] for f in fam_detail]), ys), 4),
    "spearman_MAE_vs_in_family_learnability": round(L.spearman(ss, ys), 4),
}
print("\ncross-family:", res["cross_family_relationship"])

# how many families would beat a FAIR baseline (family's own nested mean)?
fair = sum(1 for r in rows if r["repro_mae"] < r["baseline_nested_family_mean_mae"])
fair_oracle = sum(1 for r in rows if r["repro_mae"] < r["baseline_oracle_family_mean_mae"])
res["fair_baseline_summary"] = {
    "n_families": len(rows),
    "beats_published_train_mean_baseline": int(e4["summary"]["n_beating_baseline"]),
    "beats_nested_family_mean": fair,
    "beats_oracle_family_mean": fair_oracle,
    "n_negative_r2": int(sum(1 for r in rows if r["repro_r2"] < 0)),
}
print("fair-baseline summary:", res["fair_baseline_summary"])

(OUT / "attack_D.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
print("\nwrote attack_D.json")
