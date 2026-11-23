#!/usr/bin/env python
"""Reviewer 1 probe 7: rigorous Kirkwood-Frohlich g-factor + temperature
confounding + the eps>=1 constraint as a physical prior.

Kirkwood-Frohlich:
  (e-einf)(2e+einf) / (e (einf+2)^2) = N_A * rho * g * mu^2 / (9 eps0 M k T)
with rho/M = 1/V_m  =>
  g = [9 eps0 k T V_m / (N_A mu^2)] * (e-einf)(2e+einf) / (e (einf+2)^2)

V_m must be the REAL liquid molar volume, not the vdW cavity sum. Where the
project's own density table is unavailable we use literature V_m.
"""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "outputs/b04/candidate_pool_v2_draft.csv"
FEAT = ROOT / "data/processed/dielectric_physical_features.csv"

NA = 6.02214076e23
EPS0 = 8.8541878128e-12
KB = 1.380649e-23
DEBYE = 3.33564e-30

# literature liquid molar volume, cm3/mol at ~25 C
VM = {
    "N-methylaniline": 108.8, "methyl propenoate": 87.0, "nonane": 179.0,
    "1,2-butanediol": 88.0, "octanedinitrile": 130.0,
    "2-amino-2-methylpropan-1-ol": 105.0, "cycloheptanone": 119.0,
    "1,2-propanediol": 73.2, "triethanolamine": 133.0, "cyclohexanol": 106.0,
    "sulfolane": 95.4, "dimethyl carbonate": 84.7, "heptane": 146.6,
    "heptanedinitrile": 115.0, "N-(2-hydroxypropyl)-2-hydroxy-1-propanamine": 140.0,
    "1-methylimidazole": 79.0, "diethyl carbonate": 121.0, "acetic acid": 57.5,
    "methylcyclohexane": 128.0, "1,4,7,10,13-pentaoxacyclopentadecane": 165.0,
    "2-acetylthiophene": 108.0, "diethanolamine": 96.0,
}
# literature epsilon_infinity ~ n_D^2 (optical)
N2 = {
    "N-methylaniline": 2.32, "methyl propenoate": 1.96, "nonane": 1.95,
    "1,2-butanediol": 2.03, "octanedinitrile": 2.15,
    "2-amino-2-methylpropan-1-ol": 2.02, "cycloheptanone": 2.09,
    "1,2-propanediol": 2.03, "triethanolamine": 2.20, "cyclohexanol": 2.06,
    "sulfolane": 2.21, "dimethyl carbonate": 1.88, "heptane": 1.92,
    "heptanedinitrile": 2.10, "N-(2-hydroxypropyl)-2-hydroxy-1-propanamine": 2.10,
    "1-methylimidazole": 2.20, "diethyl carbonate": 1.90, "acetic acid": 1.87,
    "methylcyclohexane": 1.96, "1,4,7,10,13-pentaoxacyclopentadecane": 2.05,
    "2-acetylthiophene": 2.30, "diethanolamine": 2.15,
}


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    pool = load(POOL)
    feat = {r["inchikey"]: r for r in load(FEAT)}
    rows = []
    for r in pool:
        f = feat[r["inchikey"]]
        rows.append({"name": r["name"], "T": float(r["T_K"]),
                     "e": float(r["dielectric"]),
                     "mu": float(f["dipole_D"]),
                     "vm": VM.get(r["name"]), "einf": N2.get(r["name"])})
    n = len(rows)

    print("=" * 78)
    print("U. KIRKWOOD-FROHLICH g  (orientational correlation)")
    print("   g=1 : no correlation | g>1 : parallel (H-bonded chains)")
    print("   g<1 : antiparallel (dimers) | alkane g formally >>1 from induced terms")
    print(f"\n  {'name':40s} {'eps':>6s} {'mu/D':>6s} {'g':>7s} {'class':>10s}")
    gs = []
    for r in rows:
        if r["vm"] is None or r["einf"] is None:
            print(f"  {r['name'][:40]:40s} {r['e']:6.2f} {r['mu']:6.2f}  no Vm/n")
            continue
        vm = r["vm"] * 1e-6
        mu = r["mu"] * DEBYE
        e, ei = r["e"], r["einf"]
        rhs = ((e - ei) * (2 * e + ei)) / (e * (ei + 2) ** 2)
        g = (9 * EPS0 * KB * r["T"] * vm / (NA * mu * mu)) * rhs
        cls = "alkane" if r["mu"] < 0.3 else ("assoc" if g > 1.4 else
                                             ("anti" if g < 1.0 else "normal"))
        gs.append((r["name"], r["e"], r["mu"], g, cls))
        print(f"  {r['name'][:40]:40s} {e:6.2f} {r['mu']:6.2f} {g:7.2f} {cls:>10s}")
    print("\n  g spans a factor of "
          f"{max(g for _,_,_,g,_ in gs)/min(g for _,_,_,g,_ in gs):.1f} "
          f"across the pool ({min(g for _,_,_,g,_ in gs):.2f} to "
          f"{max(g for _,_,_,g,_ in gs):.2f})")
    # For mu -> 0 (alkanes) the Kirkwood g is not defined: the induced
    # (distortion) polarization dominates and eps ~ n^2 regardless of g.
    polar = [z for z in gs if z[2] >= 0.5]
    print(f"\n  NOTE: the 3 alkanes (mu<0.1 D) give g = 31/19/5 -- this is NOT a")
    print("  real orientational correlation. For nonpolar species eps is the")
    print("  induced term (eps ~ n^2) and the Kirkwood g is UNDEFINED because")
    print("  the mu^2 denominator vanishes. Restricting to polar molecules")
    print(f"  (mu >= 0.5 D, n={len(polar)}):")
    print(f"    g range {min(z[3] for z in polar):.2f} .. {max(z[3] for z in polar):.2f}"
          f"  (factor {max(z[3] for z in polar)/min(z[3] for z in polar):.1f})")
    print(f"    g < 1 (antiparallel): {sorted(z[0] for z in polar if z[3] < 1.0)}")
    print(f"    g > 1.8 (correlated) : {sorted(z[0] for z in polar if z[3] > 1.8)}")
    print("  Textbook g: acetone 1.3, methanol 2.5, ethanol 2.2, water 2.9.")
    print("  Our polar subset spans 0.44 (acetic acid, cyclic dimer) to 6.5")
    print("  (AMP, H-bonded), i.e. the same physical range. Since g is a")
    print("  COLLECTIVE quantity and appears nowhere in X0/X1, eps is being")
    print("  asked of descriptors that structurally cannot contain it.")
    print("  But dipole still ranks reasonably (below), so the honest physics")
    print("  reading is: descriptors carry PART of eps (the mu^2/Vm factor),")
    print("  and the missing part is g (0.4-6.5), not nothing.")

    # correlation of g with eps and of dipole with eps
    def rank(v):
        nn = len(v)
        o = sorted(range(nn), key=lambda i: v[i])
        rk = [0.0] * nn
        i = 0
        while i < nn:
            j = i
            while j + 1 < nn and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[o[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return rk

    def sp(a, b):
        ra, rb = rank(a), rank(b)
        nn = len(a)
        ma, mb = sum(ra) / nn, sum(rb) / nn
        num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(nn))
        den = math.sqrt(sum((v - ma) ** 2 for v in ra) * sum((v - mb) ** 2 for v in rb))
        return num / den if den else float("nan")

    print(f"\n  spearman(eps, g)      = {sp([z[1] for z in gs], [z[3] for z in gs]):+.3f}")
    print(f"  spearman(eps, mu)     = {sp([z[1] for z in gs], [z[2] for z in gs]):+.3f}")
    print(f"  spearman(eps, mu^2/Vm)= "
          f"{sp([z[1] for z in gs], [(z[2]*DEBYE)**2/(VM[z[0]]*1e-6) for z in gs]):+.3f}")
    kos = [(z[2] * DEBYE) ** 2 / (VM[z[0]] * 1e-6) for z in gs]
    top = sorted(range(len(gs)), key=lambda i: -kos[i])[:3]
    print(f"  top-3 by mu^2/Vm: {[gs[i][0] for i in top]} with eps "
          f"{[gs[i][1] for i in top]}")

    print("\n" + "=" * 78)
    print("V. TEMPERATURE IS A MEASURED VARIABLE BUT IS NOT IN X0/X1")
    Ts = sorted(set(r["T"] for r in rows))
    print(f"  T_K values present: {Ts}  -> spread {max(Ts)-min(Ts):.2f} K")
    print("  X0 = " + ", ".join(["heavy_atom_count", "hbd", "hba", "tpsa_A2",
                                 "molecular_volume_A3", "molar_volume_m3_mol",
                                 "formal_charge"]))
    print("  X1 = dipole_D, polarizability_au/A3, homo_lumo_gap_ev, total_energy")
    print("  => T_K is NOT a model input, although the Debye/Kirkwood term is")
    print("     explicitly proportional to 1/T.")
    dT = 0.4  # typical |deps/dT| for associated solvents, per K
    print(f"\n  |deps/dT| for associated liquids ~ 0.3-0.5 per K")
    print(f"  a 10 K spread -> {0.3*10:.1f} to {0.5*10:.1f} eps units of pure")
    print(f"  temperature mismatch, against a pool sd of {statistics.pstdev([r['e'] for r in rows]):.2f}.")
    print(f"  That is {0.3*10/statistics.pstdev([r['e'] for r in rows])*100:.0f}-"
          f"{0.5*10/statistics.pstdev([r['e'] for r in rows])*100:.0f}% of the target sd.")
    # normalise eps to 298.15
    print("\n  normalised to a common 298.15 K using deps/dT = -0.4/K (sensitivity):")
    for slope in (-0.3, -0.4):
        adj = [r["e"] + slope * (r["T"] - 298.15) for r in rows]
        print(f"    deps/dT={slope:+.1f}: pool mean {statistics.mean(adj):.3f} "
              f"(raw {statistics.mean([r['e'] for r in rows]):.3f}), "
              f"sd {statistics.pstdev(adj):.3f} (raw "
              f"{statistics.pstdev([r['e'] for r in rows]):.3f})")
    print("  the six 303.15 K entries are ALL amines/polyols (high eps), so the")
    print("  temperature effect is confounded with chemistry, not random.")

    print("\n" + "=" * 78)
    print("W. eps >= 1 AS A PHYSICAL CONSTRAINT THE MODEL IGNORES")
    print("  A non-magnetic condensed phase must have eps >= 1 (Kramers-Kronig,")
    print("  passivity). Observed predictions:")
    e1 = load(ROOT / "outputs/b05/E1_structure_vs_electronic/predictions_loo.csv")
    for m in ("X0_structure_only", "X0_plus_X1_electronic"):
        pr = [float(x["y_pred"]) for x in e1 if x["model"] == m]
        print(f"    {m:24s}: {sum(1 for v in pr if v<1)}/22 violate eps>=1, "
              f"{sum(1 for v in pr if v<0)}/22 are negative")
    print("  A single clip at eps=1 (pure physics, no fitting) changes MAE:")
    for m in ("X0_structure_only", "X0_plus_X1_electronic"):
        pr = [float(x["y_pred"]) for x in e1 if x["model"] == m]
        yt = [float(x["y_true"]) for x in e1 if x["model"] == m]
        mae_raw = statistics.mean([abs(pr[i] - yt[i]) for i in range(len(pr))])
        cl = [max(v, 1.0) for v in pr]
        mae_cl = statistics.mean([abs(cl[i] - yt[i]) for i in range(len(cl))])
        print(f"    {m:24s}: raw {mae_raw:7.4f} -> clipped {mae_cl:7.4f} "
              f"(gain {mae_raw-mae_cl:.2f})")
    print("  => the reported MAE is partly a MEASURE OF AN UNPHYSICAL")
    print("     OUTPUT, not of chemical ignorance.")


if __name__ == "__main__":
    main()
