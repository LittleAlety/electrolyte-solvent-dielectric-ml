"""Attack E (applicability domain) and F (top-k screening significance)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib as L

ROOT = Path(r"E:\Claude Code\电解质ML\电解质ML")
OUT = ROOT / "outputs" / "b100_review"
res = {}

# ============================================================ E: applicability domain
ood = pd.read_csv(ROOT / "outputs" / "b100" / "e4_structural_ood_b100.csv")
print(ood.head(3).to_string())
print(ood.shape, ood.family.value_counts().to_dict())

n = len(ood)
res["E_repro_0.5"] = {
    "n": n,
    "n_in": int((ood.nn_tanimoto >= 0.5).sum()),
    "n_out": int((ood.nn_tanimoto < 0.5).sum()),
    "mae_in": round(float(ood.loc[ood.nn_tanimoto >= 0.5, "abs_error"].mean()), 4),
    "mae_out": round(float(ood.loc[ood.nn_tanimoto < 0.5, "abs_error"].mean()), 4),
}
res["E_repro_0.5"]["ratio"] = round(res["E_repro_0.5"]["mae_out"] / res["E_repro_0.5"]["mae_in"], 4)

# threshold sweep
sweep = {}
for thr in [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
    ind = ood.nn_tanimoto >= thr
    if ind.sum() < 5 or (~ind).sum() < 5:
        continue
    mi = float(ood.loc[ind, "abs_error"].mean())
    mo = float(ood.loc[~ind, "abs_error"].mean())
    # bootstrap CI of the ratio
    rng = np.random.default_rng(L.SEED)
    a = ood.loc[ind, "abs_error"].to_numpy()
    b = ood.loc[~ind, "abs_error"].to_numpy()
    ratios = []
    for _ in range(2000):
        ratios.append(rng.choice(b, len(b)).mean() / rng.choice(a, len(a)).mean())
    sweep[f"{thr:.2f}"] = {
        "n_in": int(ind.sum()), "n_out": int((~ind).sum()),
        "mae_in": round(mi, 4), "mae_out": round(mo, 4), "ratio": round(mo / mi, 4),
        "ratio_ci95": [round(float(np.percentile(ratios, 2.5)), 3),
                       round(float(np.percentile(ratios, 97.5)), 3)],
        "median_in": round(float(ood.loc[ind, "abs_error"].median()), 3),
        "median_out": round(float(ood.loc[~ind, "abs_error"].median()), 3),
        "median_ratio": round(float(ood.loc[~ind, "abs_error"].median()
                                    / max(ood.loc[ind, "abs_error"].median(), 1e-9)), 3),
    }
res["E_threshold_sweep"] = sweep
print("\nthreshold sweep")
for k, v in sweep.items():
    print(f"  thr={k} in={v['n_in']:3d} out={v['n_out']:3d} MAE {v['mae_in']:6.3f}/{v['mae_out']:6.3f} "
          f"ratio={v['ratio']:5.2f} CI{v['ratio_ci95']} medratio={v['median_ratio']}")

# ---- confound: are "out of domain" molecules simply the high-eps, hard ones?
res["E_composition"] = {
    "out_domain_family_counts": ood.loc[ood.nn_tanimoto < 0.5, "family"].value_counts().to_dict(),
    "in_domain_family_counts": ood.loc[ood.nn_tanimoto >= 0.5, "family"].value_counts().to_dict(),
    "eps_mean_in": round(float(ood.loc[ood.nn_tanimoto >= 0.5, "y_true"].mean()), 3),
    "eps_mean_out": round(float(ood.loc[ood.nn_tanimoto < 0.5, "y_true"].mean()), 3),
    "eps_median_in": round(float(ood.loc[ood.nn_tanimoto >= 0.5, "y_true"].median()), 3),
    "eps_median_out": round(float(ood.loc[ood.nn_tanimoto < 0.5, "y_true"].median()), 3),
    "spearman_sim_vs_abs_error": round(L.spearman(ood.nn_tanimoto, ood.abs_error), 4),
    "spearman_eps_vs_abs_error": round(L.spearman(ood.y_true, ood.abs_error), 4),
    "spearman_sim_vs_eps": round(L.spearman(ood.nn_tanimoto, ood.y_true), 4),
}
print("\ncomposition:", res["E_composition"])

# partial spearman of similarity vs error controlling for eps (rank residualisation)
ra = L._rank(ood.nn_tanimoto.to_numpy())
rb = L._rank(ood.abs_error.to_numpy())
rc = L._rank(ood.y_true.to_numpy())
A = np.vstack([np.ones_like(rc), rc]).T
ra_r = ra - A @ np.linalg.lstsq(A, ra, rcond=None)[0]
rb_r = rb - A @ np.linalg.lstsq(A, rb, rcond=None)[0]
res["E_partial_spearman_sim_error_given_eps"] = round(float(np.corrcoef(ra_r, rb_r)[0, 1]), 4)

# ratio within eps strata (does the AD effect survive matching on eps?)
strata = {}
for lo, hi in [(-np.inf, 5), (5, 10), (10, 20), (20, np.inf)]:
    s = ood[(ood.y_true >= lo) & (ood.y_true < hi)]
    if len(s) < 10:
        continue
    ind = s.nn_tanimoto >= 0.5
    if ind.sum() < 3 or (~ind).sum() < 3:
        strata[f"[{lo},{hi})"] = {"n": int(len(s)), "n_in": int(ind.sum()),
                                  "n_out": int((~ind).sum()), "ratio": None}
        continue
    strata[f"[{lo},{hi})"] = {
        "n": int(len(s)), "n_in": int(ind.sum()), "n_out": int((~ind).sum()),
        "mae_in": round(float(s.loc[ind, "abs_error"].mean()), 3),
        "mae_out": round(float(s.loc[~ind, "abs_error"].mean()), 3),
        "ratio": round(float(s.loc[~ind, "abs_error"].mean() / s.loc[ind, "abs_error"].mean()), 3),
    }
res["E_eps_stratified"] = strata
print("eps-stratified:", strata)

# within-family ratio (halocarbon excluded / included)
famr = {}
for fam in ood.family.unique():
    s = ood[ood.family == fam]
    ind = s.nn_tanimoto >= 0.5
    if ind.sum() < 3 or (~ind).sum() < 3:
        continue
    famr[fam] = {"n": int(len(s)), "n_in": int(ind.sum()), "n_out": int((~ind).sum()),
                 "mae_in": round(float(s.loc[ind, "abs_error"].mean()), 3),
                 "mae_out": round(float(s.loc[~ind, "abs_error"].mean()), 3),
                 "ratio": round(float(s.loc[~ind, "abs_error"].mean()
                                      / s.loc[ind, "abs_error"].mean()), 3)}
res["E_within_family"] = famr

# excluding halocarbons altogether
nb = ood[ood.family != "halocarbon"]
ind = nb.nn_tanimoto >= 0.5
res["E_excluding_halocarbon"] = {
    "n": int(len(nb)), "n_in": int(ind.sum()), "n_out": int((~ind).sum()),
    "mae_in": round(float(nb.loc[ind, "abs_error"].mean()), 3),
    "mae_out": round(float(nb.loc[~ind, "abs_error"].mean()), 3),
    "ratio": round(float(nb.loc[~ind, "abs_error"].mean() / nb.loc[ind, "abs_error"].mean()), 3),
}
print("\nwithin-family ratios:", json.dumps(famr, indent=1))
print("excluding halocarbon:", res["E_excluding_halocarbon"])

# ============================================================ F: top-k screening
rk = pd.read_csv(ROOT / "outputs" / "b100" / "e6_ranking_b100.csv")
print("\ne6 ranking:", rk.shape)
rk = rk.sort_values("rank_by_prediction").reset_index(drop=True)
pool = rk.y_true.to_numpy(float)
model_pred = rk.y_pred.to_numpy(float)
K = 10
oracle_idx = np.argsort(-pool)[:K]
model_idx = np.arange(K)  # already ranked by prediction
oracle_mean = pool[oracle_idx].mean()
model_mean = pool[model_idx].mean()
pool_mean = pool.mean()
headroom = oracle_mean - pool_mean
captured = (model_mean - pool_mean) / headroom
res["F_core"] = {
    "n_pool": int(len(pool)), "oracle_top10_mean": round(float(oracle_mean), 4),
    "model_top10_mean": round(float(model_mean), 4), "pool_mean": round(float(pool_mean), 4),
    "regret": round(float(oracle_mean - model_mean), 4),
    "headroom_captured_frac": round(float(captured), 4),
    "overlap_model_vs_oracle_top10": int(len(set(model_idx) & set(oracle_idx))),
    "recall_top10pct": round(float(len(set(model_idx) & set(np.argsort(-pool)[:22])) / 22), 4),
    "recall_top20pct": round(float(len(set(model_idx) & set(np.argsort(-pool)[:44])) / 44), 4),
    "precision_of_model_top10_above_pool_90pct": round(float(
        (pool[model_idx] >= np.percentile(pool, 90)).mean()), 3),
    "n_model_top10_that_are_halocarbon": int((rk.family.to_numpy()[model_idx] == "halocarbon").sum()),
    "pool_sd": round(float(pool.std(ddof=1)), 3),
}
print("\nF core:", json.dumps(res["F_core"], indent=1))

# NDCG@10 (gain = eps, standard)
def ndcg(order_idx, k=10):
    gains = pool[order_idx][:k]
    disc = 1 / np.log2(np.arange(2, k + 2))
    dcg = (gains * disc).sum()
    ideal = (np.sort(pool)[::-1][:k] * disc).sum()
    return float(dcg / ideal)


res["F_core"]["ndcg10"] = round(ndcg(model_idx), 4)
res["F_core"]["ndcg10_mu2_only"] = None

# ---- exact-ish Monte Carlo null (1e6 draws), paired across scenarios
rng = np.random.default_rng(L.SEED)
N_MC = 400000
base_idx = np.argsort(rng.random((N_MC, len(pool))), axis=1)[:, :K]
mc_means = pool[base_idx].mean(axis=1)
res["F_core"]["mc_p_random_ge_model"] = round(float((mc_means >= model_mean).mean()), 6)
res["F_core"]["mc_p_resolution"] = round(1 / N_MC, 6)
res["F_core"]["mc_mean_of_random_mean"] = round(float(mc_means.mean()), 4)
res["F_core"]["z_score_vs_random"] = round(float((model_mean - mc_means.mean()) / mc_means.std()), 3)
res["F_core"]["random_mean_sd"] = round(float(mc_means.std()), 4)

# effective sample-size view: what n_top-k would a "rank-correlation-only" model get
# sensitivity: remove the highest-eps molecules from the pool (are a few easy molecules driving p?)
esc = {}
for n_drop in [0, 1, 2, 3, 5]:
    order = np.argsort(-pool)
    keep_mask = np.ones(len(pool), bool)
    keep_mask[order[:n_drop]] = False
    p_keep = pool[keep_mask]
    # model picks its best k among the kept molecules
    order_pred = np.argsort(-model_pred)
    sel = [i for i in order_pred if keep_mask[i]][:K]
    m_mean = pool[sel].mean()
    o_mean = np.sort(p_keep)[::-1][:K].mean()
    pm = p_keep.mean()
    idxs = np.argsort(rng.random((N_MC // 4, len(p_keep))), axis=1)[:, :K]
    mm = p_keep[idxs].mean(axis=1)
    esc[f"drop_top{n_drop}"] = {
        "n_pool": int(keep_mask.sum()),
        "oracle": round(float(o_mean), 3), "model": round(float(m_mean), 3),
        "pool_mean": round(float(pm), 3),
        "headroom_captured": round(float((m_mean - pm) / (o_mean - pm)), 3),
        "p_random_ge_model": round(float((mm >= m_mean).mean()), 6),
        "overlap_with_oracle": int(len(set(sel) & set(np.argsort(-p_keep)[:K]))),
    }
res["F_drop_extremes"] = esc
print("\ndrop-extremes:", json.dumps(esc, indent=1))

# ---- does a single trivial descriptor rank as well?
m = pd.read_csv(ROOT / "outputs" / "b100" / "model_matrix_b100.csv")
mm = m.set_index("inchikey")
single = {}
cands = {"mu_sq_over_Vm": "mu_sq_over_Vm", "dipole_D": "dipole_D",
         "alpha_over_Vm": "alpha_over_Vm", "tpsa_A2": "tpsa_A2",
         "hbd": "hbd", "n_halogen_negative": "n_halogen",
         "mw_negative": "mw", "molar_volume_negative": "molar_volume_m3_mol"}
for label, col in cands.items():
    vals = mm.loc[rk.inchikey, col].to_numpy(float)
    sign = -1 if label.endswith("_negative") else 1
    sel = np.argsort(-sign * vals)[:K]
    mean_sel = pool[sel].mean()
    p = float((mc_means >= mean_sel).mean())
    single[label] = {
        "top10_mean": round(float(mean_sel), 3),
        "p_random_ge": round(p, 6),
        "overlap_with_model_top10": int(len(set(sel) & set(model_idx))),
        "overlap_with_oracle": int(len(set(sel) & set(oracle_idx))),
        "ndcg10": round(ndcg(sel), 4),
    }
res["F_single_descriptor"] = single
print("\nsingle-descriptor top-10:", json.dumps(single, indent=1))

# ---- family-composition-matched null: random subsets drawn with the same family mix as the model top-10
fams = rk.family.to_numpy()
model_fams = fams[model_idx]
pool_by_fam = {f: np.where(fams == f)[0] for f in set(fams)}
mm2 = []
for _ in range(N_MC // 4):
    pick = []
    for f in model_fams:
        pick.append(rng.choice(pool_by_fam[f]))
    mm2.append(pool[np.asarray(pick)].mean())
mm2 = np.asarray(mm2)
res["F_family_matched_null"] = {
    "model_top10_families": sorted(pd.Series(model_fams).value_counts().to_dict().items()),
    "p_random_family_matched_ge_model": round(float((mm2 >= model_mean).mean()), 6),
    "family_matched_mean": round(float(mm2.mean()), 4),
}

# k sensitivity with the same MC
for k2 in [5, 15]:
    idxs = np.argsort(rng.random((N_MC // 4, len(pool))), axis=1)[:, :k2]
    mmk = pool[idxs].mean(axis=1)
    mk = pool[np.argsort(-model_pred)[:k2]].mean()
    ok = np.sort(pool)[::-1][:k2].mean()
    res[f"F_k{k2}"] = {"oracle": round(float(ok), 3), "model": round(float(mk), 3),
                       "pool_mean": round(float(pool_mean), 3),
                       "headroom_captured": round(float((mk - pool_mean) / (ok - pool_mean)), 3),
                       "p_random_ge_model": round(float((mmk >= mk).mean()), 6)}

(OUT / "attack_EF.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
print("\nwrote attack_EF.json")
