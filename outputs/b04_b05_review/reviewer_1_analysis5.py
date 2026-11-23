#!/usr/bin/env python
"""Reviewer 1 probe 5: prove the ECFP-collision mechanism and retest the
applicability-domain claim under a correctly specified model."""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "outputs/b04/candidate_pool_v2_draft.csv"
V04 = ROOT / "data/dielectric_v04.csv"
FEAT = ROOT / "data/processed/dielectric_physical_features.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    try:
        return float((v or "").strip())
    except ValueError:
        return None


def main():
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, DataStructs
    RDLogger.DisableLog("rdApp.*")

    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feat = {r["inchikey"]: r for r in load(FEAT)}

    print("=" * 78)
    print("O. WHY MORGAN r=2 SAYS Tanimoto=1.0 FOR HEPTANE vs NONANE")
    for nm, smi in (("heptane", "CCCCCCC"), ("nonane", "CCCCCCCCC")):
        m = Chem.MolFromSmiles(smi)
        fp = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
        print(f"  {nm:8s} {smi:12s} nBits set={fp.GetNumOnBits()}  onbits={sorted(fp.GetOnBits())}")
    a = AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles("CCCCCCC"), 2, 2048)
    b = AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles("CCCCCCCCC"), 2, 2048)
    print(f"  Tanimoto(heptane,nonane) = {DataStructs.TanimotoSimilarity(a,b):.4f}")
    print("  => radius-2 Morgan environments in an unbranched alkane only encode")
    print("     'distance from chain terminus up to 2'. Heptane and nonane are")
    print("     therefore BIT-IDENTICAL in ECFP space, while being C7 vs C9.")
    print("     This is a well-known fingerprint resolution limit with NOTHING")
    print("     to do with the model's tabular descriptors:")
    for nm in ("heptane", "nonane"):
        rr = next(r for r in pool if r["name"] == nm)
        f = feat[rr["inchikey"]]
        print(f"     {nm:8s} heavy_atom_count={f['heavy_atom_count']:>3s} "
              f"molecular_volume={float(f['molecular_volume_A3']):7.2f} A^3 "
              f"dipole={float(f['dipole_D']):.3f} D")
    print("     -> the X0/X1 vectors the model actually sees are clearly DIFFERENT.")
    print("     The E4 text says '描述符无法区分二者' (descriptors cannot")
    print("     distinguish) -- that is FALSE for the model's descriptor set and")
    print("     TRUE only for the ECFP vector, which the model never used.")

    # identical-descriptor counterfactual: force one of the pair to use the
    # other's feature vector -> this is what "identical descriptors" would mean
    print("\n  counterfactual check: if the descriptors truly were identical, an")
    print("  LOO ridge would emit (near-)identical predictions. Observed:")
    e4 = load(ROOT / "outputs/b05/E4_domain_generalization/structural_distance_ood.csv")
    for nm in ("heptane", "nonane", "heptanedinitrile", "octanedinitrile"):
        r = next(x for x in e4 if x["name"] == nm)
        print(f"    {nm:18s} y_pred={float(r['y_pred']):+8.4f}")
    print("    difference nonane-heptane = "
          f"{float(next(x for x in e4 if x['name']=='nonane')['y_pred']) - float(next(x for x in e4 if x['name']=='heptane')['y_pred']):+.4f}")
    print("    A 5.7-unit spread is impossible under identical feature vectors")
    print("    (LOO folds differ by one molecule out of 21).")

    print("\n" + "=" * 78)
    print("P. DECOMPOSITION OF THE 'IDENTICAL-FINGERPRINT' ERROR")
    rows = []
    for r in e4:
        rows.append({"name": r["name"], "y": float(r["y_true"]),
                     "p": float(r["y_pred"]), "err": float(r["abs_error"]),
                     "res": float(r["y_pred"]) - float(r["y_true"]),
                     "nn": float(r["nn_tanimoto"])})
    bias = statistics.mean([q["res"] for q in rows])
    ident = [q for q in rows if q["nn"] >= 0.999]
    print(f"  E4 pooled mean residual (global bias) = {bias:+.4f}")
    print(f"  mean |err| over the 4 'identical' molecules = "
          f"{statistics.mean([q['err'] for q in ident]):.4f}   (reported 19.4791)")
    print(f"  mean |err - bias| over the same 4          = "
          f"{statistics.mean([abs(q['res']-bias) for q in ident]):.4f}")
    print(f"  -> the global offset accounts for "
          f"{(1-statistics.mean([abs(q['res']-bias) for q in ident])/statistics.mean([q['err'] for q in ident]))*100:.1f}% "
          f"of the 'descriptor blindness' error.")

    print("\n" + "=" * 78)
    print("Q. APPLICABILITY DOMAIN: does the claim survive a correct model?")
    # repaired LOO predictions with intercept
    def standardise(X):
        n, p = len(X), len(X[0])
        m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
        s = []
        for j in range(p):
            v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
            s.append(math.sqrt(v) if v > 0 else 1.0)
        return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s

    def ridge_fit(Z, yy, lam=1.0):
        n, p = len(Z), len(Z[0])
        A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
              for b in range(p)] for a in range(p)]
        rhs = [sum(Z[i][a] * yy[i] for i in range(n)) for a in range(p)]
        for c in range(p):
            piv = max(range(c, p), key=lambda r: abs(A[r][c]))
            if abs(A[piv][c]) < 1e-12:
                continue
            A[c], A[piv] = A[piv], A[c]
            rhs[c], rhs[piv] = rhs[piv], rhs[c]
            pv = A[c][c]
            for r in range(c + 1, p):
                f = A[r][c] / pv
                for k in range(c, p):
                    A[r][k] -= f * A[c][k]
                rhs[r] -= f * rhs[c]
        b = [0.0] * p
        for r in range(p - 1, -1, -1):
            if abs(A[r][r]) < 1e-12:
                continue
            b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
        return b

    order = [q["name"] for q in rows]
    byn = {r["name"]: r for r in pool}
    Xm, yv = [], []
    for nm in order:
        f = feat[byn[nm]["inchikey"]]
        Xm.append([float(f[c]) for c in X0 + X1])
        yv.append(float(byn[nm]["dielectric"]))
    n = len(Xm)
    pred = []
    for h in range(n):
        Xtr = [Xm[i] for i in range(n) if i != h]
        ytr = [yv[i] for i in range(n) if i != h]
        ybar = sum(ytr) / len(ytr)
        Z, m, s = standardise(Xtr)
        b = ridge_fit(Z, [v - ybar for v in ytr], 1.0)
        x = [(Xm[h][j] - m[j]) / s[j] for j in range(len(m))]
        pred.append(sum(x[j] * b[j] for j in range(len(b))) + ybar)

    ind = [i for i in range(n) if rows[i]["nn"] >= 0.3999]  # same >=0.4 threshold
    outd = [i for i in range(n) if rows[i]["nn"] < 0.3999]
    print(f"  AD threshold nn_tanimoto >= 0.40 : in={len(ind)} out={len(outd)}")
    for tag, pr in (("as shipped (no intercept)", [q["p"] for q in rows]),
                    ("repaired (with intercept)", pred)):
        mi = statistics.mean([abs(pr[i] - yv[i]) for i in ind])
        mo = statistics.mean([abs(pr[i] - yv[i]) for i in outd])
        print(f"    {tag:26s} MAE_in={mi:7.3f} MAE_out={mo:7.3f} ratio={mo/mi:.3f}")
    print("  -> with a physical model the out/in ratio is ", end="")
    mi = statistics.mean([abs(pred[i] - yv[i]) for i in ind])
    mo = statistics.mean([abs(pred[i] - yv[i]) for i in outd])
    print(f"{mo/mi:.3f}: still no useful separation,")
    print("     BUT that is now a genuine (if underpowered) statement rather than")
    print("     an artefact of a uniformly mis-centred predictor.")

    print("\n" + "=" * 78)
    print("R. FAMILY TAXONOMY DEFECTS")
    e4r = load(ROOT / "outputs/b05/E4_domain_generalization/structural_distance_ood.csv")
    fam = {}
    for r in e4r:
        fam.setdefault(r["family"], []).append((r["name"], float(r["y_true"])))
    for k in sorted(fam, key=lambda z: -len(fam[z])):
        eps = [v for _, v in fam[k]]
        print(f"  {k:26s} n={len(fam[k])} eps {min(eps):5.2f}-{max(eps):5.2f} "
              f"spread={max(eps)/max(min(eps),1e-9):6.1f}x")
    print("\n  'unclassified' mixes the alkanes (eps~2) with sulfolane (eps=44):")
    print("     a 22-fold internal spread. Leave-one-family-out on this bucket")
    print("     holds out both extremes simultaneously and cannot mean anything.")
    print("  diethanolamine -> primary_secondary_amine ; triethanolamine ->")
    print("     tertiary_amine, although they differ only by one N-CH2CH2OH.")
    print("     Chemically near-identical molecules are split across 'families',")
    print("     which makes the LOFO estimate unstable by construction.")


if __name__ == "__main__":
    main()
