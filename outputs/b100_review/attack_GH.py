"""Attack G (conformer reliability threshold) and H (hard gates, temperature, frequency, label noise)."""
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

# ============================================================ G: conformers
cf = pd.read_csv(ROOT / "outputs" / "b100" / "deliverables" / "conformer_ensemble_b100.csv")
print(cf.verdict.value_counts().to_dict(), len(cf))
cf["polar"] = cf.boltzmann_dipole >= 0.30
print(cf.groupby("polar").size())

# the published rule: polar AND (rel_dev > thr OR rel_spread > thr)
def counts(thr):
    pol = cf[cf.polar]
    both = pol[(pol.single_vs_boltzmann_rel_dev > thr) | (pol.dipole_relative_spread > thr)]
    only_dev = pol[pol.single_vs_boltzmann_rel_dev > thr]
    only_spread = pol[pol.dipole_relative_spread > thr]
    and_ = pol[(pol.single_vs_boltzmann_rel_dev > thr) & (pol.dipole_relative_spread > thr)]
    return {"n_polar": int(len(pol)), "unreliable_OR": int(len(both)),
            "unreliable_only_rel_dev": int(len(only_dev)),
            "unreliable_only_rel_spread": int(len(only_spread)),
            "unreliable_AND": int(len(and_)),
            "frac_OR": round(len(both) / len(pol), 3)}

res["G_threshold_sweep"] = {f"{t:.2f}": counts(t) for t in [0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]}
print("\nthreshold sweep")
for k, v in res["G_threshold_sweep"].items():
    print(f"  thr={k}: {v['unreliable_OR']:2d}/{v['n_polar']} OR ({v['frac_OR']:.3f})  "
          f"dev-only={v['unreliable_only_rel_dev']:2d} spread-only={v['unreliable_only_rel_spread']:2d} "
          f"both={v['unreliable_AND']:2d}")

res["G_published_verdict_check"] = {
    "n_rows": int(len(cf)),
    "n_verdict_unreliable": int((cf.verdict == "SINGLE_CONFORMER_UNRELIABLE").sum()),
    "n_verdict_reliable": int((cf.verdict == "SINGLE_CONFORMER_RELIABLE").sum()),
    "reproduced_30_of_36": counts(0.10),
    "median_rel_spread": round(float(cf.dipole_relative_spread.median()), 4),
    "median_rel_dev": round(float(cf.single_vs_boltzmann_rel_dev.median()), 4),
    "max_rel_spread": round(float(cf.dipole_relative_spread.max()), 4),
}
print("\npublished-check:", res["G_published_verdict_check"])

# scope: the sample is the 40 most flexible molecules -> how much of the modelling set?
m = pd.read_csv(ROOT / "outputs" / "b100" / "model_matrix_b100.csv")
common = m.dropna(subset=L.X0_COLS + L.X1_COLS + L.XN_COLS)
rot_min = int(cf.n_rotatable.min())
rot_med = float(cf.n_rotatable.median())
res["G_scope"] = {
    "sample_rot_min": rot_min, "sample_rot_median": rot_med,
    "dataset_n": int(len(m)),
    "dataset_n_rot_ge_sample_min": int((m.n_rotatable >= rot_min).sum()),
    "dataset_frac_rot_ge_sample_min": round(float((m.n_rotatable >= rot_min).mean()), 3),
    "common_set_n_rot_ge_sample_min": int((common.n_rotatable >= rot_min).sum()),
    "common_set_frac_rot_ge_sample_min": round(float((common.n_rotatable >= rot_min).mean()), 3),
    "dataset_n_rot_ge_6": int((m.n_rotatable >= 6).sum()),
    "dataset_frac_rot_ge_6": round(float((m.n_rotatable >= 6).mean()), 3),
    "sample_frac_of_rot_ge_min": round(40 / max((m.n_rotatable >= rot_min).sum(), 1), 3),
}
print("\nscope:", res["G_scope"])

# consequence: translate dipole uncertainty into epsilon error via the mu2/Vm model
sub = common.dropna(subset=["mu_sq_over_Vm"]).copy()
x = sub.mu_sq_over_Vm.to_numpy(float)
y = sub.epsilon.to_numpy(float)
b, a = np.polyfit(x, y, 1)
rel_spread_med = float(cf.dipole_relative_spread.median())
# mu^2 has ~2x relative spread; a molecule at the median mu^2/Vm
x_med = float(np.median(x))
eps_shift = abs(b) * x_med * (2 * rel_spread_med)
res["G_consequence"] = {
    "slope_eps_per_mu2_over_Vm": float(b * 1e35),
    "median_mu2_over_Vm": x_med,
    "median_dipole_rel_spread": rel_spread_med,
    "implied_eps_shift_at_median": round(float(eps_shift), 3),
    "r2_of_linear_mu2_model": round(float(np.corrcoef(x, y)[0, 1] ** 2), 4),
    "note": ("conformer dipole spread -> mu^2 spread ~2x rel_spread -> epsilon shift at the "
             "median mu^2/Vm; compare with the model MAE 3.30"),
}
print("\nconsequence:", res["G_consequence"])

# ============================================================ H: hard gates
freeze = json.loads((ROOT / "outputs" / "b100" / "deliverables" / "b100_freeze_manifest.json")
                    .read_text(encoding="utf-8"))
gate = json.loads((ROOT / "outputs" / "b100" / "b100_admission_gate.json").read_text(encoding="utf-8"))
lab = pd.read_csv(ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv")
led = pd.read_csv(ROOT / "outputs" / "b100" / "deliverables" / "measurement_ledger_b100.csv")

res["H_gate_numbers"] = {
    "gate_n_qualified": gate["result"]["n_qualified_molecules"],
    "gate_n_qualified_with_xtb": gate["result"]["n_qualified_with_xtb"],
    "freeze_achieved_qualified": freeze["hard_gates"]["achieved_qualified"],
    "freeze_achieved_xtb": freeze["hard_gates"]["achieved_xtb"],
    "modelling_set": freeze["dataset"]["modelling_set"],
    "common_evaluation_set": freeze["dataset"]["common_evaluation_set"],
    "n_unique_inchikey_labels": int(lab.inchikey.nunique()),
    "n_labels": int(len(lab)),
    "n_measurements_in_ledger": int(len(led)),
    "n_molecules_multiple_measurements": int((led.groupby("inchikey").size() > 1).sum()),
    "evidence_grade": lab.evidence_grade.value_counts().to_dict(),
    "corroborated": freeze["source_independence"]["independently_corroborated"],
}

# temperature
res["H_temperature"] = {
    "T_min": float(lab.T_K.min()), "T_max": float(lab.T_K.max()),
    "n_at_298.15": int((lab.T_K == 298.15).sum()),
    "n_within_2K_of_298.15": int((abs(lab.T_K - 298.15) <= 2).sum()),
    "n_within_5K_of_298.15": int((abs(lab.T_K - 298.15) <= 5).sum()),
    "max_abs_dev_K": float(abs(lab.T_K - 298.15).max()),
}
# empirical d(eps)/dT from the ledger (same molecule, multiple temperatures)
slopes = []
for k, g in led.groupby("inchikey"):
    if len(g) < 2:
        continue
    g = g.dropna(subset=["epsilon", "T_K"])
    if len(g) < 2 or g.T_K.max() - g.T_K.min() < 5:
        continue
    T = g.T_K.to_numpy(float)
    e = g.epsilon.to_numpy(float)
    sl = np.polyfit(T, e, 1)[0]
    slopes.append(sl / e.mean())          # fractional change per K
slopes = np.asarray(slopes)
res["H_temperature"]["n_molecules_with_T_series"] = int(len(slopes))
res["H_temperature"]["median_frac_slope_per_K"] = round(float(np.median(slopes)), 5)
res["H_temperature"]["implied_frac_error_at_5K"] = round(float(abs(np.median(slopes)) * 5), 4)
res["H_temperature"]["implied_abs_error_at_5K_on_pool_mean"] = round(
    float(abs(np.median(slopes)) * 5 * lab.epsilon.mean()), 3)
print("\ntemperature:", res["H_temperature"])

# frequency
lab_f = led.dropna(subset=["frequency_mhz"])
res["H_frequency"] = {
    "n_ledger_rows_with_freq": int(len(lab_f)),
    "n_freq_zero": int((lab_f.frequency_mhz == 0).sum()),
    "n_freq_positive": int((lab_f.frequency_mhz > 0).sum()),
    "freq_positive_range_mhz": [float(lab_f.loc[lab_f.frequency_mhz > 0, "frequency_mhz"].min()),
                                float(lab_f.loc[lab_f.frequency_mhz > 0, "frequency_mhz"].max())],
    "n_ledger_rows_no_freq_nbs514": int(led.frequency_mhz.isna().sum()),
    "n_labels_per_measurement_reported": int((lab.frequency_basis.str.contains("per-measurement")).sum()),
    "n_labels_source_level_static": int((lab.frequency_basis.str.contains("source-level")).sum()),
}
# which label molecule uses a >0 frequency measurement? (approximate: molecule appears in a positive-freq row)
pos_keys = set(lab_f.loc[lab_f.frequency_mhz > 0, "inchikey"])
res["H_frequency"]["n_label_molecules_with_any_positive_freq_measurement"] = int(
    lab.inchikey.isin(pos_keys).sum())
print("frequency:", res["H_frequency"])

# ---- attrition bias: 257 -> 221 (polarizability missing)
missing36 = m[m.polarizability_au.isna()]
res["H_attrition"] = {
    "n_dropped_from_common_set": int(len(missing36)),
    "dropped_eps_mean": round(float(missing36.epsilon.mean()), 3),
    "kept_eps_mean": round(float(common.epsilon.mean()), 3),
    "dropped_eps_median": round(float(missing36.epsilon.median()), 3),
    "kept_eps_median": round(float(common.epsilon.median()), 3),
    "dropped_eps_max": round(float(missing36.epsilon.max()), 3),
    "kept_eps_max": round(float(common.epsilon.max()), 3),
    "dropped_family_counts": missing36.family.value_counts().to_dict(),
    "dropped_frac_high_eps": round(float((missing36.epsilon >= 20).mean()), 3),
    "kept_frac_high_eps": round(float((common.epsilon >= 20).mean()), 3),
    "mwu_p_eps": float(__import__("scipy.stats", fromlist=["mannwhitneyu"])
                       .mannwhitneyu(missing36.epsilon, common.epsilon).pvalue),
}
print("\nattrition:", res["H_attrition"])

# ---- label noise from repeated measurements of the same molecule near the same T
spread = []
for k, g in led.groupby("inchikey"):
    g = g.dropna(subset=["epsilon", "T_K"])
    if len(g) < 2:
        continue
    g = g[abs(g.T_K - 298.15) <= 10]
    if len(g) < 2:
        continue
    e = g.epsilon.to_numpy(float)
    spread.append((e.max() - e.min()) / e.mean())
spread = np.asarray(spread)
res["H_label_noise"] = {
    "n_molecules_repeat_measurements_near_298": int(len(spread)),
    "median_rel_range": round(float(np.median(spread)), 4),
    "p90_rel_range": round(float(np.percentile(spread, 90)), 4),
    "frac_gt_5pct": round(float((spread > 0.05).mean()), 3),
    "frac_gt_10pct": round(float((spread > 0.10).mean()), 3),
    "note": "same molecule, >=2 ledger measurements within 10 K of 298.15 K",
}
print("\nlabel noise:", res["H_label_noise"])

# ---- family balance of the modelling set
res["H_family_balance"] = {
    "n_families": int(m.family.nunique()),
    "n_families_ge_10": int((m.family.value_counts() >= 10).sum()),
    "families_lt_10": m.family.value_counts().loc[lambda s: s < 10].to_dict(),
    "n_high_eps_ge_20": int((m.epsilon >= 20).sum()),
}
print("\nfamily balance:", res["H_family_balance"])

(OUT / "attack_GH.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
print("\nwrote attack_GH.json")
