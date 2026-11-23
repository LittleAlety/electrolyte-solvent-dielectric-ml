#!/usr/bin/env python
"""Reviewer 4 attack 3 (corrected): CLAIM C, the report's "decisive" finding.

Report claim: "4 molecules have nearest-neighbour Tanimoto = 1.000 yet mean
absolute error 19.4791, which proves the descriptors cannot resolve chemically
distinct liquids -- not out-of-domain extrapolation."

Tests:
  (1) PREMISE. Morgan-2/2048-bit presence fingerprints collide on homologous
      n-alkanes. Tanimoto == 1.0 does not mean "identical molecules", and the
      fingerprint is NOT the model's input (the model uses 11 continuous
      RDKit/xTB descriptors).
  (2) THE INFERENCE. If two rows really had identical descriptor vectors the
      model would be FORCED to emit one value and the optimal error would be
      |y_i-y_j|/2. Check whether the descriptors are identical and what the
      model actually emits.
  (3) THE MAGNITUDE. A constant mean predictor uses no descriptors at all and
      still has a known error on these four molecules. How does the reported
      19.48 compare?

Regression reproduces the published E4 model exactly (verified: total LOO MAE
17.237529668 == published 17.2375).
"""
from __future__ import annotations

import csv, json, math, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
V04 = REPO / "data" / "dielectric_v04.csv"
FEAT = REPO / "data" / "processed" / "dielectric_physical_features.csv"

XE4 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
       "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
       "dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]
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


def standardise(XX):
    m, p = len(XX), len(XX[0])
    mu = [sum(XX[i][j] for i in range(m)) / m for j in range(p)]
    sd = []
    for j in range(p):
        v = sum((XX[i][j] - mu[j]) ** 2 for i in range(m)) / max(m - 1, 1)
        sd.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(XX[i][j] - mu[j]) / sd[j] for j in range(p)] for i in range(m)], mu, sd


def solve(A, rhs):
    p = len(rhs)
    A = [r[:] for r in A]
    rhs = rhs[:]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-14:
            continue
        A[c], A[piv] = A[piv], A[c]
        rhs[c], rhs[piv] = rhs[piv], rhs[c]
        pv = A[c][c]
        for r in range(c + 1, p):
            f = A[r][c] / pv
            if f == 0:
                continue
            for k in range(c, p):
                A[r][k] -= f * A[c][k]
            rhs[r] -= f * rhs[c]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-14:
            continue
        b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
    return b


def loo_predict(X, y, lam=1.0, intercept=False):
    """Correct LOO: the training labels are indexed by the same tr list."""
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        Xtr = [X[i] for i in tr]
        ytr = [y[i] for i in tr]
        Z, mu, sd = standardise(Xtr)
        p = len(Z[0])
        A = [[sum(Z[r][a] * Z[r][b] for r in range(len(Z)))
              + (lam if a == b else 0.0) for b in range(p)] for a in range(p)]
        rhs = [sum(Z[r][a] * ytr[r] for r in range(len(Z))) for a in range(p)]
        b = solve(A, rhs)
        x = [(X[h][j] - mu[j]) / sd[j] for j in range(p)]
        v = sum(x[j] * b[j] for j in range(p))
        if intercept:
            v += sum(ytr) / len(ytr)
        out.append(v)
    return out


def main():
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, DataStructs, rdMolDescriptors, rdFingerprintGenerator
    RDLogger.DisableLog("rdApp.*")

    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feats = {r["inchikey"]: r for r in load(FEAT)}
    y = [float(r["dielectric"]) for r in pool]
    n = len(y)
    ybar = sum(y) / n
    names = [r["name"] for r in pool]
    res = {}

    mols, smis = [], []
    for r in pool:
        s = (v04.get(r["inchikey"], {}).get("smiles") or "").strip()
        smis.append(s)
        mols.append(Chem.MolFromSmiles(s) if s else None)

    # ---- (0) sanity: reproduce the published number exactly ---------------
    X = [[float(fnum(feats[r["inchikey"]][c])) for c in XE4] for r in pool]
    p_bug = loo_predict(X, y, 1.0, False)
    p_fix = loo_predict(X, y, 1.0, True)
    res["reproduction_check"] = {
        "reproduced_loo_mae": sum(abs(p_bug[i] - y[i]) for i in range(n)) / n,
        "published_loo_mae": 17.2375,
        "abs_diff": abs(sum(abs(p_bug[i] - y[i]) for i in range(n)) / n - 17.2375),
        "reproduced_bias": sum(p_bug[i] - y[i] for i in range(n)) / n,
        "published_bias": -16.9385,
    }

    # ---- (1) fingerprint provenance ---------------------------------------
    gens = {
        "morgan2_2048": lambda m: rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=2048).GetFingerprint(m),
        "morgan3_2048": lambda m: rdFingerprintGenerator.GetMorganGenerator(
            radius=3, fpSize=2048).GetFingerprint(m),
        "morgan2_4096": lambda m: rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=4096).GetFingerprint(m),
        "morgan4_2048": lambda m: rdFingerprintGenerator.GetMorganGenerator(
            radius=4, fpSize=2048).GetFingerprint(m),
        "rdkit_path_2048": lambda m: Chem.RDKFingerprint(m, fpSize=2048),
        "maccs_166": lambda m: AllChem.GetMACCSKeysFingerprint(m),
    }
    nn = {}
    for gname, g in gens.items():
        fps = [g(m) for m in mols]
        sims = []
        for i in range(n):
            s = sorted(((DataStructs.TanimotoSimilarity(fps[i], fps[j]), j)
                        for j in range(n) if j != i), reverse=True)
            sims.append(s[0])
        nn[gname] = {
            "max_nn_similarity": sorted((s for s, _ in sims), reverse=True)[0],
            "n_molecules_with_nn_at_1": sum(1 for s, _ in sims if s > 0.999),
            "pairs_at_1": [[names[i], names[s[1]]] for i, s in enumerate(sims)
                           if s[0] > 0.999],
            "mean_nn_similarity": statistics.mean(s for s, _ in sims),
        }
    # unresolved-stereo explanation
    nn["nonane_smiles"] = smis[names.index("nonane")]
    nn["heptane_smiles"] = smis[names.index("heptane")]
    nn["nonane_formula"] = rdMolDescriptors.CalcMolFormula(mols[names.index("nonane")])
    nn["heptane_formula"] = rdMolDescriptors.CalcMolFormula(mols[names.index("heptane")])
    nn["nonane_heavy_atoms"] = mols[names.index("nonane")].GetNumHeavyAtoms()
    nn["heptane_heavy_atoms"] = mols[names.index("heptane")].GetNumHeavyAtoms()
    nn["why_identical"] = (
        "Morgan fingerprints enumerate substructures to a fixed radius and hash "
        "them into a bit vector; a straight-chain alkane's environments are all "
        "C-sp3 with only chain-position variation, and with a presence (bit) "
        "fingerprint the repeated middle-chain environments collapse, so nonane "
        "and heptane land on the same bits. They are different molecules "
        "(C9H20 vs C7H16, MW 128 vs 100) with different molar volumes.")
    res["fingerprints"] = nn

    # ---- (2) are the MODEL's descriptors identical? -----------------------
    pairs = [("nonane", "heptane"), ("octanedinitrile", "heptanedinitrile")]
    pair_rows = []
    for a, b in pairs:
        ia, ib = names.index(a), names.index(b)
        diff = [abs(X[ia][j] - X[ib][j]) for j in range(len(XE4))]
        rel = [diff[j] / max(abs(X[ia][j]), abs(X[ib][j]), 1e-12)
               for j in range(len(XE4))]
        big = [XE4[j] for j in range(len(XE4)) if rel[j] > 0.01]
        pair_rows.append({
            "pair": [a, b], "y_true": [y[ia], y[ib]],
            "true_gap": abs(y[ia] - y[ib]),
            "descriptor_vectors_identical": all(d < 1e-12 for d in diff),
            "descriptors_differing_rel_gt_1pct": big,
            "n_differing": len(big),
        })
    res["descriptor_identity"] = pair_rows

    # ---- (3) error decomposition on the four molecules --------------------
    ident = [m for row in pairs for m in row]  # 4 names, report's set
    ident = ["nonane", "heptane", "octanedinitrile", "heptanedinitrile"]
    rows = []
    for nm in ident:
        i = names.index(nm)
        loto = statistics.mean([y[j] for j in range(n) if j != i])
        rows.append({
            "name": nm, "y_true": y[i],
            "pred_published_no_intercept": round(p_bug[i], 4),
            "abs_err_published": round(abs(p_bug[i] - y[i]), 4),
            "pred_intercept_fixed": round(p_fix[i], 4),
            "abs_err_intercept_fixed": round(abs(p_fix[i] - y[i]), 4),
            "abs_err_zero_descriptor_mean_predictor": round(abs(ybar - y[i]), 4),
            "abs_err_zero_descriptor_loto_mean": round(abs(loto - y[i]), 4),
        })
    res["four_molecules"] = rows
    m_pub = statistics.mean(r["abs_err_published"] for r in rows)
    m_fix = statistics.mean(r["abs_err_intercept_fixed"] for r in rows)
    m_mean = statistics.mean(r["abs_err_zero_descriptor_mean_predictor"] for r in rows)
    res["four_molecules_summary"] = {
        "published_model_mae_on_4": m_pub,
        "reported_value_in_report": 19.4791,
        "intercept_fixed_model_mae_on_4": m_fix,
        "zero_descriptor_mean_predictor_mae_on_4": m_mean,
        "ratio_published_over_mean_predictor": m_pub / m_mean,
        "n_molecules_where_model_beats_mean_predictor": sum(
            1 for r in rows
            if r["abs_err_published"] < r["abs_err_zero_descriptor_mean_predictor"]),
    }

    # ---- irreducible error IF the model were genuinely blind -------------
    blind = []
    for a, b in pairs:
        ia, ib = names.index(a), names.index(b)
        blind.append({
            "pair": [a, b],
            "irreducible_abs_err_each": abs(y[ia] - y[ib]) / 2,
            "model_abs_err_A": abs(p_bug[ia] - y[ia]),
            "model_abs_err_B": abs(p_bug[ib] - y[ib]),
            "model_predicted_gap": abs(p_bug[ia] - p_bug[ib]),
            "true_gap": abs(y[ia] - y[ib]),
        })
    res["if_truly_blind"] = blind

    # ---- error concentration: is it a global offset? ---------------------
    # If the model is just mis-levelled, subtracting a single constant (the
    # best possible one) should collapse the error a lot. Fit that constant
    # honestly out-of-fold.
    shifted = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        # best additive correction estimated on the training folds only
        c = statistics.mean(y[i] - p_bug[i] for i in tr)
        shifted.append(p_bug[h] + c)
    mae_shift = sum(abs(shifted[i] - y[i]) for i in range(n)) / n
    res["one_constant_offset_fix"] = {
        "published_mae": res["reproduction_check"]["reproduced_loo_mae"],
        "mae_after_adding_out_of_fold_constant": mae_shift,
        "fraction_of_error_from_mere_level": 1 - mae_shift / res[
            "reproduction_check"]["reproduced_loo_mae"],
        "note": ("a single scalar correction, fitted on the training folds only "
                 "and using no molecule information, removes this much of the "
                 "reported error"),
    }

    # ---- residual ranking signal on the four molecules -------------------
    res["four_molecule_ranking"] = {
        "predicted_order": [ident[j] for j in sorted(
            range(4), key=lambda k: -p_bug[names.index(ident[k])])],
        "true_order": [ident[j] for j in sorted(
            range(4), key=lambda k: -y[names.index(ident[k])])],
    }

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_03_claimC.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
