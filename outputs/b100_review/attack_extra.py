"""Extra probes: family-mean predictor (A), dipole transforms (B), alpha/Vm (C), within-family ranking (F)."""
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

m = pd.read_csv(ROOT / "outputs" / "b100" / "model_matrix_b100.csv")
ALL = L.X0_COLS + L.X1_COLS + L.XN_COLS
common = m.dropna(subset=ALL).reset_index(drop=True)
y = common.epsilon.to_numpy(float)
fams = common.family.to_numpy()
X20 = common[ALL].to_numpy(float)
pred20 = L.nested_loo(X20, y)

# ---- A: categorical family-mean predictor (learnable, no continuous features)
loo_fam = np.empty(len(y))
for i in range(len(y)):
    mask = np.ones(len(y), bool)
    mask[i] = False
    same = (fams == fams[i]) & mask
    loo_fam[i] = y[same].mean() if same.sum() else y[mask].mean()
res["A_family_mean_predictor"] = {
    "mae": round(L.mae(y, loo_fam), 4), "r2": round(L.r2(y, loo_fam), 4),
    "spearman": round(L.spearman(loo_fam, y), 4),
    "note": "LOO mean of the molecule's own family; family identity derivable from SMILES",
}
print("family-mean LOO:", res["A_family_mean_predictor"])

# and the published global constant baseline for reference
res["A_global_constant"] = {"mae": round(L.mae(y, np.full(len(y), y.mean())), 4)}

# ---- B: is mu2/Vm just dipole^2 and 1/Vm?
V = common.molar_volume_m3_mol.to_numpy(float)
d = common.dipole_D.to_numpy(float)
c1 = 1e-18 * (1 / 2.99792458e9) ** 2  # D -> C m (3.33564e-30)
d2 = (d * 3.33564e-30) ** 2
probes = {
    "dipole_squared": d2.reshape(-1, 1),
    "inverse_molar_volume": (1.0 / V).reshape(-1, 1),
    "dipole_sq_and_inv_V": np.column_stack([d2, 1.0 / V]),
    "mu2_over_Vm_only": common.mu_sq_over_Vm.to_numpy(float).reshape(-1, 1),
    "alpha_over_Vm_only": common.alpha_over_Vm.to_numpy(float).reshape(-1, 1),
    "mu2_Vm_plus_alpha_Vm": common[L.XN_COLS].to_numpy(float),
    "alpha_only": common.polarizability_au.to_numpy(float).reshape(-1, 1),
    "mu2_Vm_plus_alpha_only": np.column_stack([common.mu_sq_over_Vm, common.polarizability_au]),
}
Bp = {}
for k, X in probes.items():
    p = L.nested_loo(X, y)
    Bp[k] = {"mae": round(L.mae(y, p), 4), "r2": round(L.r2(y, p), 4),
             "spearman": round(L.spearman(p, y), 4)}
    print(f"  {k:26s} MAE={Bp[k]['mae']:.4f} R2={Bp[k]['r2']:+.4f}")
res["B_probes"] = Bp
res["B_paired_mu2_vs_Xn"] = L.paired_boot(
    np.abs(L.nested_loo(common[["mu_sq_over_Vm"]].to_numpy(float), y) - y),
    np.abs(L.nested_loo(common[L.XN_COLS].to_numpy(float), y) - y))

# X0 + nonlinear dipole terms (is the structure block's weakness a linearity artefact?)
X0 = common[L.X0_COLS].to_numpy(float)
for label, extra in {
    "X0_plus_dipole_sq": d2.reshape(-1, 1),
    "X0_plus_mu2_Vm": common.mu_sq_over_Vm.to_numpy(float).reshape(-1, 1),
    "X0_plus_Xn": common[L.XN_COLS].to_numpy(float),
}.items():
    p = L.nested_loo(np.column_stack([X0, extra]), y)
    res[label] = {"mae": round(L.mae(y, p), 4), "r2": round(L.r2(y, p), 4)}
    print(f"  {label:26s} MAE={res[label]['mae']:.4f} R2={res[label]['r2']:+.4f}")

# ---- C: marginal value of alpha and gap on top of dipole + mu2/Vm
combos = {
    "dipole_mu2Vm": ["dipole_D", "mu_sq_over_Vm"],
    "dipole_mu2Vm_alpha": ["dipole_D", "mu_sq_over_Vm", "polarizability_au"],
    "dipole_mu2Vm_alphaVm": ["dipole_D", "mu_sq_over_Vm", "alpha_over_Vm"],
    "dipole_mu2Vm_gap": ["dipole_D", "mu_sq_over_Vm", "homo_lumo_gap_ev"],
    "full20": ALL,
}
baseline_pred = None
for k, cols in combos.items():
    p = L.nested_loo(common[cols].to_numpy(float), y)
    res.setdefault("C_combos", {})[k] = {"mae": round(L.mae(y, p), 4),
                                         "r2": round(L.r2(y, p), 4),
                                         "k": len(cols)}
    print(f"  {k:24s} k={len(cols):2d} MAE={res['C_combos'][k]['mae']:.4f} R2={res['C_combos'][k]['r2']:+.4f}")
    if k == "dipole_mu2Vm":
        baseline_pred = p
for k in ["dipole_mu2Vm_alpha", "dipole_mu2Vm_alphaVm", "dipole_mu2Vm_gap"]:
    p = L.nested_loo(common[combos[k]].to_numpy(float), y)
    res.setdefault("C_paired_vs_twofeature", {})[k] = L.paired_boot(
        np.abs(baseline_pred - y), np.abs(p - y))

# ---- F: within-family ranking of the full LOO model
famrank = {}
for f in np.unique(fams):
    mask = fams == f
    if mask.sum() < 8:
        continue
    famrank[f] = {"n": int(mask.sum()),
                  "spearman_within_family": round(L.spearman(pred20[mask], y[mask]), 3),
                  "mae": round(L.mae(y[mask], pred20[mask]), 3),
                  "mae_constant": round(L.mae(y[mask], np.full(mask.sum(), y[mask].mean())), 3)}
res["F_within_family_ranking"] = famrank
print("\nwithin-family ranking:", json.dumps(famrank, indent=1))

# amine detail: the model's 9 amine picks vs the 9 best amines
am = fams == "amine"
ya, pa = y[am], pred20[am]
sel = np.argsort(-pa)[:9]
res["F_amine_detail"] = {
    "n_amine": int(am.sum()),
    "n_selected_amine_in_top10": int(len(sel)),
    "eps_of_selected_amines": sorted([round(float(v), 2) for v in ya[sel]], reverse=True),
    "top9_amine_eps": sorted([round(float(v), 2) for v in np.sort(ya)[::-1][:9]], reverse=True),
    "mean_selected": round(float(ya[sel].mean()), 3),
    "mean_top9_by_eps": round(float(np.sort(ya)[::-1][:9].mean()), 3),
    "mean_all_amines": round(float(ya.mean()), 3),
}
print("amine detail:", json.dumps(res["F_amine_detail"], indent=1))

(OUT / "attack_extra.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
print("wrote attack_extra.json")
