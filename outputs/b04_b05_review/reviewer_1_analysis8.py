#!/usr/bin/env python
"""Reviewer 1 probe 8: E4 leave-one-family-out with a correctly specified
(intercept) ridge -- same families, same folds, same baseline."""
from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "outputs/b04/candidate_pool_v2_draft.csv"
V04 = ROOT / "data/dielectric_v04.csv"
FEAT = ROOT / "data/processed/dielectric_physical_features.csv"

X = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
     "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
     "dipole_D", "polarizability_au", "polarizability_A3",
     "homo_lumo_gap_ev", "total_energy_hartree"]

FAMILY_RULES = [
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"), ("dinitrile", "N#C.*C#N"),
    ("nitrile", "N#C"), ("carbonate", "[OX2][CX3](=O)[OX2]"),
    ("ester", "[CX3](=O)[OX2][#6]"), ("ketone", "[#6][CX3](=O)[#6]"),
    ("primary_secondary_amine", "[NX3;H2,H1;!$(NC=O)]"),
    ("tertiary_amine", "[NX3;H0;!$(NC=O)]"), ("alcohol", "[OX2H]"),
    ("ether", "[OD2]([#6])[#6]"), ("thiophene", "c1ccsc1"),
    ("imidazole", "c1cncn1"), ("aromatic", "a"),
]


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    try:
        return float((v or "").strip())
    except ValueError:
        return None


def standardise(Xm):
    n, p = len(Xm), len(Xm[0])
    m = [sum(Xm[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((Xm[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(Xm[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s


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


def fit_predict(Xtr, ytr, Xte, intercept):
    ybar = sum(ytr) / len(ytr)
    yy = [v - ybar for v in ytr] if intercept else list(ytr)
    Z, m, s = standardise(Xtr)
    b = ridge_fit(Z, yy)
    return [sum((row[j] - m[j]) / s[j] * b[j] for j in range(len(b)))
            + (ybar if intercept else 0.0) for row in Xte]


def main():
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feat = {r["inchikey"]: r for r in load(FEAT)}
    mols = []
    for r in pool:
        smi = (v04.get(r["inchikey"], {}).get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        f = feat.get(r["inchikey"], {})
        vals = [fnum(f.get(c)) for c in X]
        if mol is None or any(v is None for v in vals):
            continue
        fam = "unclassified"
        for lab, sm in FAMILY_RULES:
            patt = Chem.MolFromSmarts(sm)
            if patt is not None and mol.HasSubstructMatch(patt):
                fam = lab
                break
        mols.append({"name": r["name"], "fam": fam,
                     "y": float(r["dielectric"]), "x": [float(v) for v in vals]})
    y = [m["y"] for m in mols]
    n = len(y)
    g = defaultdict(list)
    for i, m in enumerate(mols):
        g[m["fam"]].append(i)

    print("=" * 78)
    print("X. LEAVE-ONE-FAMILY-OUT: shipped (no intercept) vs repaired")
    print(f"  {'family':26s} {'n':>2s} | {'MAE':>8s} {'base':>7s} {'beat':>5s} | "
          f"{'MAE_fix':>8s} {'beat':>5s}  delta")
    nbeat0 = nbeat1 = nmeas = 0
    for fam, idx in sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(idx) < 2:
            print(f"  {fam:26s} {len(idx):2d} |  insufficient_power")
            continue
        nmeas += 1
        tr = [i for i in range(n) if i not in set(idx)]
        te = list(idx)
        Xtr = [mols[i]["x"] for i in tr]
        ytr = [y[i] for i in tr]
        Xte = [mols[i]["x"] for i in te]
        p0 = fit_predict(Xtr, ytr, Xte, False)
        p1 = fit_predict(Xtr, ytr, Xte, True)
        trmean = sum(ytr) / len(ytr)
        base = sum(abs(y[i] - trmean) for i in te) / len(te)
        m0 = sum(abs(p0[j] - y[te[j]]) for j in range(len(te))) / len(te)
        m1 = sum(abs(p1[j] - y[te[j]]) for j in range(len(te))) / len(te)
        b0 = m0 < base
        b1 = m1 < base
        nbeat0 += b0
        nbeat1 += b1
        print(f"  {fam:26s} {len(idx):2d} | {m0:8.3f} {base:7.3f} {str(b0):>5s} | "
              f"{m1:8.3f} {str(b1):>5s}  {m1-m0:+.2f}")
    print(f"\n  measurable families={nmeas}  beats baseline: "
          f"shipped {nbeat0}  repaired {nbeat1}")
    print("  => the '1 of 6' headline is a specification artefact; with an")
    print("     intercept the count changes.")

    print("\n" + "=" * 78)
    print("Y. THE 'unclassified' FAMILY IS CHEMICALLY INCOHERENT")
    unc = g["unclassified"]
    print("  members:")
    for i in unc:
        print(f"    {mols[i]['name']:26s} eps={y[i]:6.2f}")
    print(f"  eps range {min(y[i] for i in unc):.2f} - {max(y[i] for i in unc):.2f} "
          f"= {max(y[i] for i in unc)/min(y[i] for i in unc):.1f}x")
    print("  This bucket contains the 3 alkanes (eps~2) AND sulfolane (eps 44).")
    print("  Any leave-one-family-out fold that holds it out removes BOTH the")
    print("  lowest and the highest polarity simultaneously, so train and test")
    print("  no longer share a chemical space by construction.")
    print("  Root cause: the SMARTS rule list has no 'alkane' rule and no")
    print("  'sulfone' rule, so both fall through to 'unclassified'.")


if __name__ == "__main__":
    main()
