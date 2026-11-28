#!/usr/bin/env python
"""B748-02: does the CORE239 model transfer to the 67 NEW molecules?

Everything in v7.0-v7.3 was evaluated on CORE239 itself (cross-validation,
leave-one-family-out, bootstrap). That measures interpolation, not transfer.
v7.4 recovered static permittivity for 67 molecules that are NOT in CORE239 and
for which an independent supply of data exists, so the model can finally be
asked an out-of-sample question:

    fit on CORE239, predict the 67 new molecules, and look at the error.

Two things are deliberately controlled:

  * the feature layer is recomputed for BOTH cohorts by ONE code path (RDKit),
    so a feature-definition difference cannot masquerade as a transfer effect.
    The stored CORE239 'molecular_volume_A3' is reproduced by the RDKit volume
    to ~0.6% median, which is the validation that the re-implementation is the
    same descriptor and not a look-alike.
  * ionic liquids are reported SEPARATELY. 25 of the 67 new molecules are salts
    while CORE239 has no ionic liquid, so pooling them would report a chemistry
    effect as a model failure.

The label definition is declared rather than hidden: CORE239 uses the v6.0
consensus epsilon (near-ambient); the new molecules use the nearest static
epsilon to 298.15 K in the local ThermoML corpus, and the per-row temperature
offset is recorded.

Outputs (outputs/b740_expansion/transfer/):
  new_molecule_predictions.csv
  transfer_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "transfer"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
STRUCT = (REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion"
          / "new_molecule_structures.csv")
LEDGER = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion" / "cohort_ledger.csv"
SCAN = REPO_ROOT / "outputs" / "b740_expansion" / "thermoml" / "thermoml_local_scan.csv"
GEN = "run_new_molecule_transfer/1.0.0"
TARGET_T = 298.15
T_TOL_LABEL = 10.0
SEED = 20261125
N_FOLDS = 10

# RDKit-reproducible X0 layer. 'morgan2_nbits' is EXCLUDED on purpose: the stored
# column is an integer whose fingerprint parameters are not recorded in the v7.0
# artefact, so it cannot be recomputed for a new molecule without guessing.
FEATURES = ["heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
            "formal_charge", "n_rings", "n_rotatable", "fraction_csp3",
            "n_aromatic_atoms", "n_hetero", "n_halogen", "mw"]


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def rdkit_features(smiles: str) -> dict | None:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mh = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mh, randomSeed=42) != 0:
        if AllChem.EmbedMolecule(mh, randomSeed=7, useRandomCoords=True) != 0:
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mh, maxIters=500)
    except Exception:                                         # noqa: BLE001
        pass
    try:
        vol = AllChem.ComputeMolVolume(mh, gridSpacing=0.3)
    except Exception:                                         # noqa: BLE001
        return None
    return {
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "tpsa_A2": rdMolDescriptors.CalcTPSA(mol),
        "molecular_volume_A3": vol,
        "formal_charge": Chem.GetFormalCharge(mol),
        "n_rings": rdMolDescriptors.CalcNumRings(mol),
        "n_rotatable": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
        "n_aromatic_atoms": sum(1 for a in mol.GetAtoms() if a.GetIsAromatic()),
        "n_hetero": sum(1 for a in mol.GetAtoms() if a.GetSymbol() not in ("C", "H")),
        "n_halogen": sum(1 for a in mol.GetAtoms()
                         if a.GetSymbol() in ("F", "Cl", "Br", "I")),
        "mw": Descriptors.MolWt(mol),
        # BUG-FIX: a salt such as 1-butyl-3-methylimidazolium triflate is written as
        # TWO disconnected fragments with zero NET charge, so Chem.GetFormalCharge()
        # returns 0 and every ionic liquid looked "neutral". The fragment count is
        # the objective flag. It is NOT a model feature -- smoking it would change
        # the feature layer relative to CORE239 -- only a grouping key.
        "n_fragments": len(Chem.GetMolFrags(mol)),
    }


def eps_near_298(scan_rows: list[dict]) -> dict:
    """Nearest static epsilon to TARGET_T per InChIKey, with its T offset."""
    best = {}
    for r in scan_rows:
        if r["property"] != "dielectric_constant_static" or r["is_mixture"] != "false":
            continue
        ik = r["inchikey"]
        T, v = fnum(r["temperature_K"]), fnum(r["value"])
        if not ik or T is None or v is None or not (1.0 < v < 200.0):
            continue
        d = abs(T - TARGET_T)
        if d > T_TOL_LABEL:
            continue
        if ik not in best or d < best[ik][0]:
            best[ik] = (d, v, T, r["doi"])
    return best


def fit_predict(Xtr, ytr, Xte, alpha=1.0):
    """Ridge with intercept and training-fold-only standardisation."""
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    Ztr = (Xtr - mu) / sd
    Zte = (Xte - mu) / sd
    A = np.hstack([np.ones((Ztr.shape[0], 1)), Ztr])
    B = np.hstack([np.ones((Zte.shape[0], 1)), Zte])
    reg = alpha * np.eye(A.shape[1])
    reg[0, 0] = 0.0
    w = np.linalg.solve(A.T @ A + reg, A.T @ ytr)
    return B @ w


def metrics(y_obs, y_pred) -> dict:
    y_obs = np.asarray(y_obs, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_obs) == 0:
        return {"n": 0}
    err = y_pred - y_obs
    ss_res = float(((y_obs - y_pred) ** 2).sum())
    ss_tot = float(((y_obs - y_obs.mean()) ** 2).sum())
    return {
        "n": int(len(y_obs)),
        "mae": round(float(np.abs(err).mean()), 4),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
        "bias": round(float(err.mean()), 4),
        "mae_rel_pct": round(float((np.abs(err) / y_obs).mean() * 100), 3),
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "constant_baseline_mae": round(float(np.abs(y_obs - np.mean(Y_TRAIN_MEAN)).mean()), 4)
        if Y_TRAIN_MEAN is not None else None,
    }


Y_TRAIN_MEAN = None   # set in main(); used only for the constant baseline


def main() -> None:
    global Y_TRAIN_MEAN
    OUT.mkdir(parents=True, exist_ok=True)

    desc = load_csv(DESC)
    struct = {r["inchikey"]: r for r in load_csv(STRUCT)}
    ledger = {r["inchikey"]: r for r in load_csv(LEDGER)}
    scan = load_csv(SCAN)
    eps298 = eps_near_298(scan)

    # ---------------- training cohort: CORE239, features recomputed ---------
    Xtr, ytr, names_tr = [], [], []
    volume_repro = []
    for r in desc:
        smi = r.get("smiles")
        eps = fnum(r.get("epsilon"))
        if not smi or eps is None:
            continue
        feat = rdkit_features(smi)
        if feat is None:
            continue
        stored = fnum(r.get("molecular_volume_A3"))
        if stored:
            volume_repro.append(abs(feat["molecular_volume_A3"] - stored) / stored)
        Xtr.append([feat[k] for k in FEATURES])
        ytr.append(eps)
        names_tr.append(r["inchikey"])

    Xtr = np.asarray(Xtr, dtype=float)
    ytr = np.asarray(ytr, dtype=float)
    Y_TRAIN_MEAN = float(ytr.mean())

    # ---------------- transfer cohort: the 67 validated new molecules -------
    Xte, yte, meta_te = [], [], []
    missing = []
    for ik, led in ledger.items():
        if led["cohort"] != "NEW_MOLECULE_VALIDATED":
            continue
        st = struct.get(ik)
        if not st:
            missing.append((led.get("name", ik), "no resolved structure"))
            continue
        lab = eps298.get(ik)
        if not lab:
            missing.append((led.get("name", ik), "no static epsilon within 10 K of 298.15"))
            continue
        feat = rdkit_features(st["smiles"])
        if feat is None:
            missing.append((led.get("name", ik), "RDKit feature extraction failed"))
            continue
        Xte.append([feat[k] for k in FEATURES])
        yte.append(lab[1])
        meta_te.append({
            "inchikey": ik,
            "name": led.get("name", ""),
            "label_T_K": lab[2],
            "label_T_offset_K": round(lab[0], 2),
            "label_doi": lab[3],
            "formal_charge": feat["formal_charge"],
            "n_fragments": feat["n_fragments"],
            "is_ionic": feat["n_fragments"] > 1,
            "mw": round(feat["mw"], 2),
            "n_heavy": feat["heavy_atom_count"],
            "n_distinct_dois": led.get("n_distinct_eps_dois", ""),
        })

    Xte = np.asarray(Xte, dtype=float) if Xte else np.zeros((0, len(FEATURES)))
    yte = np.asarray(yte, dtype=float)

    # ---------------- CORE239 cross-validation (interpolation reference) ---
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(ytr))
    folds = np.array_split(order, N_FOLDS)
    cv_pred = np.full(len(ytr), np.nan)
    for k in range(N_FOLDS):
        va = folds[k]
        tr = np.concatenate([folds[j] for j in range(N_FOLDS) if j != k])
        cv_pred[va] = fit_predict(Xtr[tr], ytr[tr], Xtr[va])
    cv_metrics = metrics(ytr, cv_pred)

    # ---------------- transfer: fit on ALL CORE239, predict new ------------
    pred_all = fit_predict(Xtr, ytr, Xte) if len(yte) else np.zeros(0)
    transfer_all = metrics(yte, pred_all) if len(yte) else {"n": 0}

    rows = []
    for i, m in enumerate(meta_te):
        rows.append({**m,
                     "epsilon_label": round(float(yte[i]), 4),
                     "epsilon_pred": round(float(pred_all[i]), 4),
                     "resid": round(float(pred_all[i] - yte[i]), 4)})

    # split neutral vs ionic (an ionic liquid is a different physical object)
    neutral = [i for i, m in enumerate(meta_te) if not m["is_ionic"]]
    ionic = [i for i, m in enumerate(meta_te) if m["is_ionic"]]

    def subset_metrics(idx):
        if not idx:
            return {"n": 0}
        return metrics(yte[idx], pred_all[idx])

    # where does the error live? a regression-to-the-mean signature (bias growing
    # with the observed value) means the feature layer carries no polarity
    # information, not that the new molecules are "hard".
    resid_all = np.asarray([r["resid"] for r in rows], dtype=float) if rows else np.zeros(0)
    obs_all = np.asarray(yte, dtype=float)
    diag = {"n": int(len(obs_all))}
    if len(obs_all) >= 10:
        diag["pearson_resid_vs_observed"] = round(
            float(np.corrcoef(resid_all, obs_all)[0, 1]), 4)
        med_obs = float(np.median(obs_all))
        lo = [i for i in range(len(obs_all)) if obs_all[i] <= med_obs]
        hi = [i for i in range(len(obs_all)) if obs_all[i] > med_obs]
        diag["split_at_observed_median"] = {
            "median": round(med_obs, 3),
            "low_epsilon": metrics(obs_all[lo], pred_all[lo]),
            "high_epsilon": metrics(obs_all[hi], pred_all[hi]),
        }
        # a polarity-blind model cannot do better on the high-epsilon half
        diag["high_epsilon_ge_15"] = metrics(
            obs_all[obs_all >= 15], pred_all[obs_all >= 15])
        diag["low_epsilon_lt_15"] = metrics(
            obs_all[obs_all < 15], pred_all[obs_all < 15])

    # leave-one-ionic-liquid-out is impossible with zero ILs in training; say so
    doc = {
        "schema": "b740.new_molecule_transfer/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "question": ("does a model fitted on CORE239 predict the 67 molecules that "
                     "v7.4 recovered outside CORE239?"),
        "feature_layer": {
            "name": "X0_RDKIT",
            "features": FEATURES,
            "why_recomputed": ("one code path for both cohorts, so a feature-definition "
                               "difference cannot look like a transfer effect"),
            "excluded": {
                "morgan2_nbits": ("the stored column is an integer whose fingerprint "
                                  "parameters are not recorded in the v7.0 artefact"),
                "X1_X2_X3": ("dipole/polarizability/conformer/liquid indices do not exist "
                             "for the new molecules (no DFT layer, no conformer search)"),
            },
            "volume_reproduction_check": {
                "n": len(volume_repro),
                "median_rel_diff_vs_stored": (round(statistics.median(volume_repro), 5)
                                              if volume_repro else None),
                "max_rel_diff_vs_stored": (round(max(volume_repro), 5)
                                           if volume_repro else None),
            },
        },
        "label_definition": {
            "core239": "v6.0 consensus epsilon (near-ambient, 293-303 K)",
            "new_molecules": (f"nearest static epsilon to {TARGET_T} K in the local "
                              f"ThermoML corpus, |dT| <= {T_TOL_LABEL} K; per-row "
                              "offset recorded in the prediction table"),
            "known_noise": ("the two cohorts therefore differ by a few K of measurement "
                            "temperature; this is label noise, not a model effect"),
        },
        "model": {
            "type": "ridge regression, intercept not penalised, alpha=%.1f" % 1.0,
            "standardisation": "training-fold only",
        },
        "training_cohort": {"n": int(len(ytr)), "mean_epsilon": round(Y_TRAIN_MEAN, 4)},
        "core239_10fold_cv": cv_metrics,
        "transfer": {
            "all_new": transfer_all,
            "neutral_organic": subset_metrics(neutral),
            "ionic_liquid": subset_metrics(ionic),
            "n_missing_excluded": len(missing),
            "missing": missing[:20],
        },
        "distribution_shift": {
            "core239_epsilon_quantiles": [round(float(np.quantile(ytr, q)), 3)
                                          for q in (0.05, 0.25, 0.5, 0.75, 0.95)],
            "new_epsilon_quantiles": ([round(float(np.quantile(yte, q)), 3)
                                       for q in (0.05, 0.25, 0.5, 0.75, 0.95)]
                                      if len(yte) else None),
            "note": "quantiles are 5/25/50/75/95 percent",
        },
        "worst_errors": sorted(rows, key=lambda r: -abs(r["resid"]))[:10],
        "error_structure": diag,
        "interpretation_guard": (
            "the transfer error is NOT a cross-validation score and must not be compared "
            "with the v7.0 CV MAE as if the two were the same quantity; it mixes domain "
            "shift, label-definition noise and (for the ionic liquids) a chemistry class "
            "that CORE239 does not contain at all"),
    }

    if rows:
        out_csv = OUT / "new_molecule_predictions.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    (OUT / "transfer_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"training n={len(ytr)}  transfer n={len(yte)}  missing={len(missing)}")
    print(f"volume reproduction: median rel diff "
          f"{doc['feature_layer']['volume_reproduction_check']['median_rel_diff_vs_stored']}")
    print("\nCORE239 10-fold CV:", cv_metrics)
    print("\ntransfer (all):", transfer_all)
    print("  neutral:", doc["transfer"]["neutral_organic"])
    print("  ionic  :", doc["transfer"]["ionic_liquid"])
    print("\nworst errors:")
    for r in doc["worst_errors"][:6]:
        print(f"  {r['name'][:40]:42s} obs={r['epsilon_label']:8.2f} "
              f"pred={r['epsilon_pred']:8.2f} resid={r['resid']:8.2f} "
              f"{'IONIC' if r['is_ionic'] else ''}")


if __name__ == "__main__":
    main()
