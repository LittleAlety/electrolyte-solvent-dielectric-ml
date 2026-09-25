"""G2 probe: frozen v0.2 model evaluated on new battery-relevant solvents."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from scipy.stats import spearmanr
from xgboost import XGBRegressor

sys.path.insert(0, ".")
sys.path.insert(0, "src")

from probes.dielectric_representation_ablation import (
    morgan_count_features,
    read_modelling_rows,
)

XGB_PARAMS = {"n_estimators":200,"max_depth":2,"learning_rate":0.05,"subsample":0.8,
              "colsample_bytree":0.8,"reg_lambda":1.0,"objective":"reg:squarederror",
              "tree_method":"hist","max_bin":64,"n_jobs":1}
def r2_score(y, p):
    ss_res = np.sum((y-p)**2); ss_tot = np.sum((y-np.mean(y))**2)
    return 1-ss_res/ss_tot if ss_tot>0 else float("nan")

# Load training data (v0.2 physical features)
train_rows, _, _ = read_modelling_rows(Path("data/processed/dielectric_physical_features.csv"))
train_morgan = morgan_count_features([r["smiles"] for r in train_rows])
train_y = np.array([float(r["dielectric"]) for r in train_rows])
print(f"Train: {len(train_rows)} compounds, Morgan={train_morgan.shape[1]}")

# Load external test compounds
v02_ik = set()
with open("data/dielectric_v02.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f): v02_ik.add(r["inchikey"])

test_compounds = []
with open("data/dielectric_v031.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["dataset_origin"]=="v0.3_addition" and r["model_ready"]=="true" and r["inchikey"] not in v02_ik:
            test_compounds.append(r)
print(f"Test candidates: {len(test_compounds)}")

# Compute Morgan for test compounds
def morgan_fp_vec(smiles_list):
    result = []
    valid = []
    for s in smiles_list:
        mol = Chem.MolFromSmiles(s)
        if mol is None: continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048)
        result.append(np.array(fp, dtype=np.float64))
        valid.append(True)
    return np.vstack(result) if result else np.array([])

test_smiles = [r["smiles"] for r in test_compounds]
test_morgan = morgan_fp_vec(test_smiles)
test_y = np.array([float(r["dielectric"]) for r in test_compounds])
test_names = [r["name"] for r in test_compounds]

# Also compute basic RDKit physical features for comparison
def rdkit_phys(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None: return None
    return np.array([
        Descriptors.MolWt(mol),
        rdMolDescriptors.CalcNumRotatableBonds(mol),
        rdMolDescriptors.CalcNumHBD(mol),
        rdMolDescriptors.CalcNumHBA(mol),
        rdMolDescriptors.CalcNumHeavyAtoms(mol),
        rdMolDescriptors.CalcNumRings(mol),
        rdMolDescriptors.CalcNumAromaticRings(mol),
        rdMolDescriptors.CalcFractionCSP3(mol),
        Descriptors.TPSA(mol),
    ], dtype=np.float64)

# Build RDKit physical feature matrix for ALL compounds (train + test)
train_smiles = [r["smiles"] for r in train_rows]
train_phys_rdkit = np.vstack([rdkit_phys(s) for s in train_smiles])
test_phys_rdkit = np.vstack([rdkit_phys(s) for s in test_smiles])

# Train frozen v0.2 models
m_morgan = XGBRegressor(**XGB_PARAMS, random_state=42).fit(train_morgan, train_y)
m_phys = XGBRegressor(**XGB_PARAMS, random_state=42).fit(train_phys_rdkit, train_y)

pm = m_morgan.predict(test_morgan)
pp = m_phys.predict(test_phys_rdkit)
ph = 0.5*pm + 0.5*pp

metrics = {"Morgan":{"R2":r2_score(test_y,pm),"Spearman":float(spearmanr(test_y,pm)[0])},
           "RDKit_Phys":{"R2":r2_score(test_y,pp),"Spearman":float(spearmanr(test_y,pp)[0])},
           "Hybrid":{"R2":r2_score(test_y,ph),"Spearman":float(spearmanr(test_y,ph)[0])}}
print(f"\n=== External Test Results (v0.2 model -> {len(test_y)} new compounds) ===")
print(f"{'Model':15s}  {'R2':>8s}  {'Spearman':>10s}")
for k,v in metrics.items():
    print(f"{k:15s}  {v['R2']:8.4f}  {v['Spearman']:10.4f}")
print("\n(v0.2 CRV hybrid R2 reference: 0.320)")

# Parity plot
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
for ax, title, pred, c in zip(axes, ["Morgan","RDKit Phys","Hybrid"], [pm,pp,ph], ["#2563eb","#dc2626","#059669"]):
    ax.scatter(test_y, pred, alpha=0.7, color=c, edgecolors="white", s=40)
    mx = max(test_y.max(), pred.max()) + 1; mn = min(test_y.min(), pred.min()) - 1
    ax.plot([mn,mx], [mn,mx], "k--", alpha=0.3, lw=0.8)
    ax.set_xlabel("Experimental eps"); ax.set_ylabel("Predicted eps")
    r2 = r2_score(test_y, pred); sp = float(spearmanr(test_y, pred)[0])
    ax.set_title(f"{title}\nR2={r2:.3f}, Spearman={sp:.3f}")
    for i, n in enumerate(test_names):
        if abs(test_y[i]-pred[i]) > 10:
            ax.annotate(n.split()[0][:8], (test_y[i], pred[i]), fontsize=6, alpha=0.6)
    ax.grid(alpha=0.2); ax.set_xlim(mn,mx); ax.set_ylim(mn,mx)
fig.suptitle(f"Domain-Gap: v0.2 frozen model -> {len(test_y)} new battery solvents", fontsize=11)
fig.tight_layout()
fig.savefig("probes/artifacts/domain_gap_parity.png", dpi=180)
print("\nPlot saved: probes/artifacts/domain_gap_parity.png")

# Detail table
detail = [{"name":n,"dielectric":float(test_y[i]),
           "pred_morgan":float(pm[i]),"pred_phys":float(pp[i]),"pred_hybrid":float(ph[i])}
          for i,n in enumerate(test_names)]
for d in detail:
    print(f"  {d['name']:30s} true={d['dielectric']:6.1f}  morgan={d['pred_morgan']:6.1f}  phys={d['pred_phys']:6.1f}  hybrid={d['pred_hybrid']:6.1f}")

with Path("probes/g2_domain_gap_summary.json").open("w", encoding="utf-8", newline="\n") as handle:
    json.dump(
        {
            "probe": "G2_domain_gap",
            "train_count": len(train_rows),
            "test_count": len(test_compounds),
            "metrics": metrics,
            "per_compound": detail,
            "v02_crv_hybrid_r2": 0.320,
            "note": (
                "Physical features use RDKit-only subset (no xTB); "
                "xTB-dependent features not available for new compounds"
            ),
        },
        handle,
        ensure_ascii=False,
        indent=2,
    )
print("\nDone")
