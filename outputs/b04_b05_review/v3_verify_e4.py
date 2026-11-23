#!/usr/bin/env python
"""Reviewer-3 independent verification of B05-E4 claims.

1. Recompute Morgan (radius 2, 2048 bit) Tanimoto for every pair of the 22 pool
   molecules -> confirm/refute nn_tanimoto == 1.000 for the 4 claimed molecules.
2. Test the E4 claim "the descriptors cannot distinguish them": compare the
   actual feature vectors of the identical-fingerprint pairs.
3. Recompute E4 abs_error with and without an intercept, to see whether the
   identical-fingerprint errors are descriptor blindness or a model bug.
4. Check FAMILY_RULES ordering claim ("most specific wins").
5. Check that abs_error never uses a model trained on the held-out molecule.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, DataStructs

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "b04_b05_review"
E4 = ROOT / "outputs" / "b05" / "E4_domain_generalization"

FAMILY_RULES = [
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"),
    ("dinitrile", "N#C.*C#N"),
    ("nitrile", "N#C"),
    ("carbonate", "[OX2][CX3](=O)[OX2]"),
    ("ester", "[CX3](=O)[OX2][#6]"),
    ("ketone", "[#6][CX3](=O)[#6]"),
    ("primary_secondary_amine", "[NX3;H2,H1;!$(NC=O)]"),
    ("tertiary_amine", "[NX3;H0;!$(NC=O)]"),
    ("alcohol", "[OX2H]"),
    ("ether", "[OD2]([#6])[#6]"),
    ("thiophene", "c1ccsc1"),
    ("imidazole", "c1cncn1"),
    ("aromatic", "a"),
]
X_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
          "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
          "dipole_D", "polarizability_au", "polarizability_A3",
          "homo_lumo_gap_ev"]
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


def _std(X):
    n, p = len(X), len(X[0])
    m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


def _solve(A, rhs):
    p = len(A)
    A = [r[:] for r in A]
    rhs = rhs[:]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12:
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
        if abs(A[r][r]) < 1e-12:
            continue
        b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
    return b


def fit_predict(Xtr, ytr, Xte, lam=1.0, intercept=False):
    Z, m, s = _std(Xtr)
    p = len(m)
    ybar = sum(ytr) / len(ytr) if intercept else 0.0
    A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * (ytr[i] - ybar) for i in range(len(Z))) for a in range(p)]
    b = _solve(A, rhs)
    out = []
    for row in Xte:
        x = [(row[j] - m[j]) / s[j] for j in range(p)]
        out.append(ybar + sum(x[j] * b[j] for j in range(p)))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}

    pool = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    v04 = {r["inchikey"]: r for r in load(ROOT / "data" / "dielectric_v04.csv")}
    feats = {r["inchikey"]: r
             for r in load(ROOT / "data" / "processed" / "dielectric_physical_features.csv")}

    mols = []
    for r in pool:
        ik = r["inchikey"]
        smi = (v04.get(ik, {}).get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        f = feats.get(ik, {})
        xv = [fnum(f.get(c)) for c in X_COLS]
        if mol is None or any(v is None for v in xv):
            continue
        mols.append(dict(measurement_id=r["measurement_id"], name=r["name"],
                         smiles=smi, mol=mol, y=float(r["dielectric"]),
                         x=[float(v) for v in xv],
                         raw={c: float(f[c]) for c in X_COLS if fnum(f.get(c)) is not None}))
    res["n_mols"] = len(mols)

    # ---------- 1. independent Morgan fingerprints, all 506 pairs -------------
    fps = [AllChem.GetMorganFingerprintAsBitVect(m["mol"], 2, nBits=2048) for m in mols]
    pairs = []
    for i, j in itertools.combinations(range(len(mols)), 2):
        sim = DataStructs.TanimotoSimilarity(fps[i], fps[j])
        pairs.append((sim, i, j))
    pairs.sort(reverse=True)
    res["top10_pairs"] = [
        dict(sim=round(s, 6), a=mols[i]["name"], b=mols[j]["name"],
             ya=mols[i]["y"], yb=mols[j]["y"],
             heavy_a=mols[i]["raw"]["heavy_atom_count"],
             heavy_b=mols[j]["raw"]["heavy_atom_count"])
        for s, i, j in pairs[:10]]
    ident = [(s, i, j) for s, i, j in pairs if s >= 0.999]
    res["n_pairs_tanimoto_1"] = len(ident)
    res["identical_pairs"] = [
        dict(sim=round(s, 9), a=mols[i]["name"], b=mols[j]["name"],
             y_a=mols[i]["y"], y_b=mols[j]["y"], d_y=round(abs(mols[i]["y"] - mols[j]["y"]), 4),
             heavy_a=mols[i]["raw"]["heavy_atom_count"],
             heavy_b=mols[j]["raw"]["heavy_atom_count"],
             vol_a=mols[i]["raw"]["molecular_volume_A3"],
             vol_b=mols[j]["raw"]["molecular_volume_A3"],
             tpsa_a=mols[i]["raw"]["tpsa_A2"], tpsa_b=mols[j]["raw"]["tpsa_A2"],
             dipole_a=mols[i]["raw"]["dipole_D"], dipole_b=mols[j]["raw"]["dipole_D"],
             polar_a=mols[i]["raw"]["polarizability_A3"],
             polar_b=mols[j]["raw"]["polarizability_A3"],
             feature_vector_identical=mols[i]["x"] == mols[j]["x"])
        for s, i, j in ident]
    res["n_molecules_with_identical_nn"] = len({x for _, i, j in ident for x in (i, j)})
    # which molecules are involved
    names = sorted({mols[i]["name"] for _, i, j in ident} | {mols[j]["name"] for _, i, j in ident})
    res["identical_group_names"] = names

    # ---------- 2. recompute E4 abs_error, no-intercept vs intercept ----------
    for label, use_icpt in (("no_intercept", False), ("with_intercept", True)):
        rows = []
        for i, m in enumerate(mols):
            tr = [j for j in range(len(mols)) if j != i]
            pred = fit_predict([mols[j]["x"] for j in tr], [mols[j]["y"] for j in tr],
                               [m["x"]], intercept=use_icpt)[0]
            sims = sorted(((DataStructs.TanimotoSimilarity(fps[i], fps[j]), j) for j in tr),
                          reverse=True)
            rows.append(dict(name=m["name"], y=m["y"], pred=pred,
                             nn_sim=sims[0][0], nn=mols[sims[0][1]]["name"],
                             abs_error=abs(pred - m["y"])))
        idr = [r for r in rows if r["nn_sim"] >= 0.999]
        res[f"ident_analysis_{label}"] = dict(
            mae_all=round(sum(r["abs_error"] for r in rows) / len(rows), 4),
            n_identical=len(idr),
            mae_identical=round(sum(r["abs_error"] for r in idr) / len(idr), 4)
            if idr else None,
            details=[dict(name=r["name"], nn=r["nn"], y=r["y"],
                          pred=round(r["pred"], 4),
                          abs_error=round(r["abs_error"], 4),
                          d_y_vs_nn=round(abs(r["y"] - next(x["y"] for x in rows if x["name"] == r["nn"])), 4))
                     for r in sorted(idr, key=lambda z: -z["abs_error"])])
        # leakage check: prediction for i must not use i
        res[f"leakage_check_{label}"] = "tr excludes i by construction (j != i)"

    # ---------- 3. compare to the project's published structural_distance_ood --
    pub = load(E4 / "structural_distance_ood.csv")
    mine = {r["name"]: r for r in res["ident_analysis_no_intercept"]["details"]}
    diffs = []
    for r in pub:
        if r["nn_tanimoto"] and float(r["nn_tanimoto"]) >= 0.999:
            m = mine.get(r["name"])
            if m:
                diffs.append(dict(name=r["name"],
                                  pub_abs_error=float(r["abs_error"]),
                                  mine_abs_error=m["abs_error"],
                                  pub_nn=r["nearest_neighbour"], mine_nn=m["nn"],
                                  match=abs(float(r["abs_error"]) - m["abs_error"]) < 5e-4))
    res["published_vs_recomputed_identical"] = diffs

    # also full-table match of published abs_error (no-intercept replica)
    full = {r["name"]: float(r["abs_error"]) for r in rows_all(pub)}
    res["published_abs_error_all"] = full

    # ---------- 4. FAMILY_RULES ordering claim -------------------------------
    def classify_first(mol):
        for label, sm in FAMILY_RULES:
            patt = Chem.MolFromSmarts(sm)
            if patt is not None and mol.HasSubstructMatch(patt):
                return label
        return "unclassified"

    def all_matches(mol):
        return [lab for lab, sm in FAMILY_RULES
                if (p := Chem.MolFromSmarts(sm)) is not None and mol.HasSubstructMatch(p)]

    fam = []
    for m in mols:
        first = classify_first(m["mol"])
        allm = all_matches(m["mol"])
        shadowed = [a for a in allm if a != first]
        fam.append(dict(name=m["name"], assigned=first, all_matching_rules=allm,
                        more_specific_rules_shadowed=shadowed))
    res["family_rules"] = fam
    res["n_shadowed"] = sum(1 for f in fam if f["more_specific_rules_shadowed"])

    (OUT / "v3_e4_verify.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=== 1. Morgan r=2 2048-bit, top pairs (independent) ===")
    for p in res["top10_pairs"]:
        print(f"  {p['sim']:.4f}  {p['a']:42s} / {p['b']:42s} "
              f"y={p['ya']:6.2f}/{p['yb']:6.2f} heavy={p['heavy_a']}/{p['heavy_b']}")
    print(f"\npairs with Tanimoto==1.0: {res['n_pairs_tanimoto_1']}")
    for p in res["identical_pairs"]:
        print(f"  {p['a']} / {p['b']}  y={p['y_a']}/{p['y_b']} (d={p['d_y']}) "
              f"heavy={p['heavy_a']}/{p['heavy_b']} vol={p['vol_a']}/{p['vol_b']} "
              f"feature_vector_identical={p['feature_vector_identical']}")
    print(f"molecules involved: {res['n_molecules_with_identical_nn']} -> {names}")

    print("\n=== 2. E4 abs_error: no-intercept vs with-intercept ===")
    for label in ("no_intercept", "with_intercept"):
        a = res[f"ident_analysis_{label}"]
        print(f"[{label}] MAE all={a['mae_all']}  n_ident={a['n_identical']} "
              f"MAE_ident={a['mae_identical']}")
        for d in a["details"]:
            print(f"    {d['name']:16s} nn={d['nn']:16s} y={d['y']:6.2f} "
                  f"pred={d['pred']:8.3f} |err|={d['abs_error']:7.3f} "
                  f"|y-y_nn|={d['d_y_vs_nn']}")

    print("\n=== 3. published vs recomputed (identical-fingerprint rows) ===")
    for d in diffs:
        print(f"  {d['name']:16s} pub={d['pub_abs_error']:8.4f} "
              f"mine={d['mine_abs_error']:8.4f} match={d['match']}")

    print("\n=== 4. FAMILY_RULES: shadowed specific rules ===")
    for f in fam:
        if f["more_specific_rules_shadowed"]:
            print(f"  {f['name']:45s} assigned={f['assigned']:24s} "
                  f"also matches={f['more_specific_rules_shadowed']}")


def rows_all(pub):
    return pub


if __name__ == "__main__":
    main()
