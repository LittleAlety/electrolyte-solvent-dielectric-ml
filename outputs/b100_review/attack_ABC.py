"""Attacks A (aggregate R2 = low/high separation), B (2 vs 15 features), C (dipole sufficiency)."""
from __future__ import annotations

import itertools
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
OUT.mkdir(parents=True, exist_ok=True)

m = pd.read_csv(MATRIX)
ALL = L.X0_COLS + L.X1_COLS + L.XN_COLS
common = m.dropna(subset=ALL).reset_index(drop=True)
print(f"common set n={len(common)} of {len(m)}")

res = {"n_common": int(len(common))}

# ------------------------------------------------------------------ reproduce E1 headline
X20 = common[ALL].to_numpy(float)
y = common.epsilon.to_numpy(float)
pred20 = L.nested_loo(X20, y)
m20 = L.metrics(y, pred20)
res["repro_X0_X1_Xn"] = m20
print("repro best block:", {k: round(v, 4) if isinstance(v, float) else v for k, v in m20.items()})

for cols, name in [(L.X0_COLS, "X0_structure"), (L.X1_COLS, "X1_electronic"),
                   (L.XN_COLS, "Xn_volume_normalised"), (["dipole_D"], "dipole_only")]:
    p = L.nested_loo(common[cols].to_numpy(float), y)
    mm = L.metrics(y, p)
    res["repro_" + name] = mm
    print(f"  {name:22s} MAE={mm['mae']:.4f} R2={mm['r2']:+.4f}")

# ------------------------------------------------------------------ A: where does R2 come from
band = pd.cut(common.epsilon, [-np.inf, 5, 20, np.inf], labels=["LOW", "MID", "HIGH"])
res["band_counts"] = band.value_counts().to_dict()

# between / within band variance decomposition of the LABEL
gm = y.mean()
ss_tot = float(((y - gm) ** 2).sum())
ss_between = float(sum((band == b).sum() * (y[band == b].mean() - gm) ** 2
                       for b in ["LOW", "MID", "HIGH"]))
ss_within = ss_tot - ss_between
res["variance_decomposition"] = {
    "ss_total": ss_tot, "ss_between_bands": ss_between, "ss_within_bands": ss_within,
    "frac_variance_between_bands": ss_between / ss_tot,
    "frac_variance_within_bands": ss_within / ss_tot,
}

# what a "3-band classifier" (predict the band mean) already achieves
band_mean_pred = np.array([y[band == b].mean() for b in band])
res["band_mean_oracle_predictor"] = {
    "mae": L.mae(y, band_mean_pred),
    "r2": L.r2(y, band_mean_pred),
    "note": "oracle band membership, no molecular information beyond which of 3 bands",
}
print("band-mean oracle:", res["band_mean_oracle_predictor"])

# within-band skill of the actual model
wb = {}
for b in ["LOW", "MID", "HIGH"]:
    mask = (band == b).to_numpy()
    yy, pp = y[mask], pred20[mask]
    wb[b] = {
        "n": int(mask.sum()),
        "eps_mean": float(yy.mean()), "eps_sd": float(yy.std(ddof=1)),
        "mae_model": L.mae(yy, pp),
        "mae_band_constant": L.mae(yy, np.full(len(yy), yy.mean())),
        "r2_model_within": L.r2(yy, pp),
        "spearman_within": L.spearman(pp, yy),
        "bias": float((pp - yy).mean()),
    }
res["within_band"] = wb
for b, v in wb.items():
    print(f"  {b:5s} n={v['n']:3d} model MAE={v['mae_model']:6.3f} "
          f"band-const MAE={v['mae_band_constant']:6.3f} R2_within={v['r2_model_within']:+.3f}")

# subsets
subsets = {
    "halocarbon_only": common.family == "halocarbon",
    "non_halocarbon": common.family != "halocarbon",
    "eps_ge_10": common.epsilon >= 10,
    "eps_ge_20": common.epsilon >= 20,
    "eps_lt_5": common.epsilon < 5,
    "top25_eps": common.epsilon >= common.epsilon.nlargest(25).min(),
}
sub = {}
for name, mask in subsets.items():
    mask = mask.to_numpy()
    yy, pp = y[mask], pred20[mask]
    const = np.full(len(yy), (y[~mask].mean() if (~mask).sum() else yy.mean()))
    sub[name] = {
        "n": int(mask.sum()), "mae": L.mae(yy, pp), "r2": L.r2(yy, pp),
        "spearman": L.spearman(pp, yy), "bias": float((pp - yy).mean()),
        "mae_pool_const": L.mae(yy, const),
        "r2_loose": "n<10" if mask.sum() < 10 else None,
    }
    print(f"  subset {name:16s} n={mask.sum():3d} MAE={sub[name]['mae']:7.3f} "
          f"R2={sub[name]['r2']:+.3f} rho={sub[name]['spearman']:+.3f} bias={sub[name]['bias']:+.2f}")
res["subsets"] = sub

# log target
pl = L.nested_loo(X20, np.log(y))
res["log_target"] = {"mae_log": float(np.abs(pl - np.log(y)).mean()),
                     "r2_log": L.r2(np.log(y), pl),
                     "r2_of_expm1": L.r2(y, np.exp(pl))}
print("log target:", res["log_target"])

# influence of the single largest epsilon
drop = np.argmax(y)
keep = np.ones(len(y), bool)
keep[drop] = False
p2 = L.nested_loo(X20[keep], y[keep])
res["drop_max_eps"] = {"dropped_eps": float(y[drop]),
                       "r2_without": L.r2(y[keep], p2),
                       "mae_without": L.mae(y[keep], p2)}
print("drop max eps:", res["drop_max_eps"])

# winsorised target
yw = np.clip(y, None, np.quantile(y, 0.95))
pw = L.nested_loo(X20, yw)
res["winsor95"] = {"r2": L.r2(yw, pw), "mae": L.mae(yw, pw),
                   "cap": float(np.quantile(y, 0.95)), "n_capped": int((y > np.quantile(y, 0.95)).sum())}

# ------------------------------------------------------------------ B: 2 vs 15 features
x0 = common[L.X0_COLS].to_numpy(float)
# univariate LOO R2 (single feature, nested lambda)
uni = {}
for c in L.X0_COLS + L.X1_COLS + L.XN_COLS:
    p = L.nested_loo(common[[c]].to_numpy(float), y)
    uni[c] = {"r2": L.r2(y, p), "mae": L.mae(y, p), "spearman": L.spearman(p, y)}
res["univariate"] = uni
print("\nunivariate top:")
for c, v in sorted(uni.items(), key=lambda kv: -kv[1]["r2"])[:8]:
    print(f"  {c:24s} R2={v['r2']:+.4f} MAE={v['mae']:.3f} rho={v['spearman']:+.3f}")

# degenerate columns
res["column_diagnostics"] = {
    "formal_charge_nunique": int(common.formal_charge.nunique()),
    "corr_molar_vs_molecular_volume": float(np.corrcoef(common.molar_volume_m3_mol,
                                                        common.molecular_volume_A3)[0, 1]),
    "corr_mw_vs_heavy_atom": float(np.corrcoef(common.mw, common.heavy_atom_count)[0, 1]),
    "corr_morgan2_vs_heavy_atom": float(np.corrcoef(common.morgan2_nbits, common.heavy_atom_count)[0, 1]),
    "corr_mu2_Vm_vs_alpha_Vm": float(np.corrcoef(common.mu_sq_over_Vm, common.alpha_over_Vm)[0, 1]),
    "corr_mu2_Vm_vs_dipole2": float(np.corrcoef(common.mu_sq_over_Vm, common.dipole_D ** 2)[0, 1]),
    "spearman_1_over_Vm_vs_eps": L.spearman(1.0 / common.molar_volume_m3_mol, y),
}
print("\ncolumn diagnostics:", json.dumps(res["column_diagnostics"], indent=1))

CLEAN = [c for c in L.X0_COLS if c not in ("formal_charge", "molar_volume_m3_mol")]
res["X0_clean"] = L.metrics(y, L.nested_loo(common[CLEAN].to_numpy(float), y))
print("X0 clean (13):", {k: round(v, 4) for k, v in res["X0_clean"].items() if k != "n"})

# all pairs of the 15 structural columns
pair_best = []
cols15 = L.X0_COLS
for a, b in itertools.combinations(cols15, 2):
    p = L.nested_loo(common[[a, b]].to_numpy(float), y)
    pair_best.append((L.r2(y, p), L.mae(y, p), a, b))
pair_best.sort(reverse=True)
res["best_structural_pairs"] = [{"r2": round(r, 4), "mae": round(mm, 4), "cols": [a, b]}
                                for r, mm, a, b in pair_best[:6]]
print("\nbest 2-column structural subsets:")
for r, mm, a, b in pair_best[:5]:
    print(f"  R2={r:+.4f} MAE={mm:.3f}  {a} + {b}")

# --------------------------------------------------------------- C: dipole sufficiency
blocks = {
    "dipole_only": ["dipole_D"],
    "alpha_only": ["polarizability_au"],
    "gap_only": ["homo_lumo_gap_ev"],
    "dipole_alpha": ["dipole_D", "polarizability_au"],
    "dipole_gap": ["dipole_D", "homo_lumo_gap_ev"],
    "alpha_gap": ["polarizability_au", "homo_lumo_gap_ev"],
    "electronic_3": L.X1_COLS,
}
Cres = {}
preds = {}
for k, cols in blocks.items():
    p = L.nested_loo(common[cols].to_numpy(float), y)
    preds[k] = p
    Cres[k] = L.metrics(y, p)
    print(f"  {k:14s} MAE={Cres[k]['mae']:.4f} R2={Cres[k]['r2']:+.4f} rho={Cres[k]['spearman']:+.3f}")
res["C_blocks"] = Cres
res["C_paired_dipole_vs_electronic"] = L.paired_boot(np.abs(preds["dipole_only"] - y),
                                                     np.abs(preds["electronic_3"] - y))
res["C_paired_dipole_vs_alpha_gap"] = L.paired_boot(np.abs(preds["dipole_only"] - y),
                                                    np.abs(preds["dipole_alpha"] - y))
# incremental: dipole + mu2/Vm etc (does the electronic block add beyond dipole inside the full model?)
res["C_paired_dipole_vs_dipole_gap"] = L.paired_boot(np.abs(preds["dipole_only"] - y),
                                                    np.abs(preds["dipole_gap"] - y))

(OUT / "attack_ABC.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
print("\nwrote attack_ABC.json")
