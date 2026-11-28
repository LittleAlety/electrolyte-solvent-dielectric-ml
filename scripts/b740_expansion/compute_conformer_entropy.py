#!/usr/bin/env python
"""B743-01: conformer entropy, effective conformer number and intramolecular H-bonds.

v7.3 computed C_mu (dipole cancellation). That answers "do the conformers point
differently" but not "how much conformational freedom is there". Two molecules can
have the same C_mu with 2 or 20 thermally accessible conformers, which are very
different physical situations for a liquid.

Definitions (Boltzmann over electronic energies, T = 298.15 K):

    S_conf = -R sum_i w_i ln w_i
    N_eff  = exp(S_conf / R)
    N_PR   = 1 / sum_i w_i^2                 (inverse participation ratio)

N_eff and N_PR are both "how many conformers count", but they differ: N_eff is
exponential in the entropy and is dominated by many small weights; N_PR is
dominated by the largest weight. Reporting both, plus their ratio, exposes whether
a molecule is "a few strong conformers" or "a continuum of weak ones".

Also computed: intramolecular hydrogen-bond count per conformer (donor-H...acceptor
distance + angle criteria, explicitly stated), and how often the H-bond survives
across the ensemble.

CAVEAT carried into every output: weights come from ELECTRONIC energies of gas-phase
conformers. No thermal correction, no solvation, no liquid-phase population. S_conf
here is a STRUCTURAL flexibility index, not a thermodynamic entropy of the liquid.

Outputs (outputs/b740_expansion/conformer_analysis/):
  conformer_entropy.csv
  conformer_entropy_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "conformer_analysis"
GEN = "compute_conformer_entropy/1.0.0"

RES = REPO_ROOT / "outputs" / "b700" / "B704_conformers" / "results"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"
CRAFT_RAW = REPO_ROOT / "data" / "external_raw" / "craft_epsilon" / "craft_model_ref.py"

R_KCAL = 0.0019872041
HARTREE_TO_KCAL = 627.5094740631
R_J = 8.314462618
T_K = 298.15
AU_TO_DEBYE = 2.541746473

RE_VEC = re.compile(r"Total Dipole Moment\s*:\s*([-+]?\d+\.\d+)\s+"
                    r"([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)")
RE_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)")

# Intramolecular H-bond criteria, stated explicitly so they can be challenged.
HB_DONOR = (7, 8, 16)          # N, O, S
HB_ACCEPT = (7, 8, 9, 16)      # N, O, F, S
HB_DIST_MIN = 1.4              # A, donor-H ... acceptor
HB_DIST_MAX = 2.5
HB_ANGLE_MIN = 120.0           # degrees, D-H...A


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
        # BUG FIXED: this read `math.isfinite(v)` on the RAW STRING. On Python 3.10
        # isfinite(str) raises TypeError, which the except swallowed, so fnum()
        # returned None for every input and every downstream correlation silently
        # became "n_used: 0". It must test the parsed float.
        return f if math.isfinite(f) else None
    except Exception:
        return None


def read_xyz(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    n = int(lines[0])
    atoms = []
    for line in lines[2:2 + n]:
        p = line.split()
        atoms.append((p[0], float(p[1]), float(p[2]), float(p[3])))
    return atoms


def count_intramolecular_hbonds(atoms) -> int:
    """Count donor-H...acceptor contacts satisfying distance and angle criteria.

    Only heavy atoms that are covalently bonded (nearest-neighbour heuristic is not
    used: we require the H to be within 1.3 A of a donor, which is a bond) count.
    """
    heavy = [(i, a) for i, a in enumerate(atoms) if a[0] != "H"]
    hyd = [(i, a) for i, a in enumerate(atoms) if a[0] == "H"]

    def dist(a, b):
        return math.sqrt(sum((a[k] - b[k]) ** 2 for k in (1, 2, 3)))

    total = 0
    for hi, h in hyd:
        # which heavy atom is this H bonded to?
        best = min(heavy, key=lambda t: dist(t[1], h))
        if dist(best[1], h) > 1.3:
            continue
        d_el = best[1][0]
        if d_el not in ("N", "O", "S"):
            continue
        for ai, a in heavy:
            if ai == best[0] or a[0] not in ("N", "O", "F", "S"):
                continue
            r = dist(h[1], a)
            if not (HB_DIST_MIN <= r <= HB_DIST_MAX):
                continue
            # angle D-H...A at H
            v1 = [best[1][k] - h[1][k] for k in (1, 2, 3)]
            v2 = [a[k] - h[1][k] for k in (1, 2, 3)]
            n1 = math.sqrt(sum(x * x for x in v1))
            n2 = math.sqrt(sum(x * x for x in v2))
            if n1 == 0 or n2 == 0:
                continue
            cosang = sum(v1[i] * v2[i] for i in range(3)) / (n1 * n2)
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            if ang >= HB_ANGLE_MIN:
                total += 1
    return total


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    lofo = {r["inchikey"]: r for r in load_csv(LOFO)}

    per_mol = defaultdict(list)
    for d in sorted(p for p in RES.iterdir() if p.is_dir()):
        for c in sorted(p for p in d.iterdir() if p.is_dir()):
            f = c / "job.out"
            if not f.exists():
                continue
            txt = f.read_text(encoding="utf-8", errors="replace")
            v = RE_VEC.findall(txt)
            e = RE_ENERGY.findall(txt)
            if not v or not e:
                continue
            # Geometry for H-bond counting: the conformer result dirs only hold
            # job.out, so fall back to the xTB conformer source geometry that B704
            # was built from. Both describe the same starting structure; the ORCA
            # single point did not move atoms.
            hb = None
            for xyz in (c / "geom.xyz",
                        REPO_ROOT / "data" / "interim" / "xtb_conformers_b100"
                        / d.name / c.name / "xtbopt.xyz",
                        REPO_ROOT / "data" / "interim" / "xtb_conformers_b100"
                        / d.name / c.name / "input.xyz"):
                if xyz.exists():
                    try:
                        hb = count_intramolecular_hbonds(read_xyz(xyz))
                    except Exception:                   # noqa: BLE001
                        hb = None
                    break
            per_mol[d.name].append({
                "conf": c.name,
                "energy": float(e[-1]),
                "vec_au": tuple(float(t) for t in v[-1]),
                "hbonds": hb,
            })

    rows = []
    for ik, confs in sorted(per_mol.items()):
        if len(confs) < 2:
            continue
        energies = [c["energy"] for c in confs]
        rel = [(x - min(energies)) * HARTREE_TO_KCAL for x in energies]
        w = [math.exp(-r / (R_KCAL * T_K)) for r in rel]
        s = sum(w)
        w = [x / s for x in w]

        from math import log
        s_conf = -R_J * sum(wi * log(wi) for wi in w if wi > 0)   # J/mol/K
        n_eff = math.exp(s_conf / R_J)
        n_pr = 1.0 / sum(wi * wi for wi in w)

        vecs = [tuple(c * AU_TO_DEBYE for c in conf["vec_au"]) for conf in confs]
        mags = [math.sqrt(sum(x * x for x in v)) for v in vecs]
        mean_vec = [sum(w[i] * vecs[i][k] for i in range(len(vecs))) for k in range(3)]
        mu_mean_sq = sum(x * x for x in mean_vec)
        mu_sq_mean = sum(w[i] * mags[i] ** 2 for i in range(len(mags)))
        c_mu = 1 - mu_mean_sq / mu_sq_mean if mu_sq_mean > 1e-12 else None

        hbs = [c["hbonds"] for c in confs if c["hbonds"] is not None]
        hb_mean = (sum(w[i] * hbs[i] for i in range(len(hbs))) if hbs else None)
        hb_occ = (sum(w[i] * (1.0 if hbs[i] > 0 else 0.0) for i in range(len(hbs)))
                  if hbs else None)

        rows.append({
            "inchikey": ik,
            "name": desc.get(ik, {}).get("name", ""),
            "family": desc.get(ik, {}).get("family", ""),
            "epsilon": desc.get(ik, {}).get("epsilon", ""),
            "lofo_resid": fnum(lofo.get(ik, {}).get("resid")) or "",
            "n_conformers": len(confs),
            "n_rotatable": fnum(desc.get(ik, {}).get("n_rotatable")) or "",
            "S_conf_J_mol_K": round(s_conf, 4),
            "N_eff": round(n_eff, 4),
            "N_PR": round(n_pr, 4),
            "N_eff_over_N_PR": round(n_eff / n_pr, 4) if n_pr else "",
            "energy_range_kcal": round(max(rel), 4),
            "max_weight": round(max(w), 4),
            "C_mu": round(c_mu, 4) if c_mu is not None else "",
            "hbond_mean_count": round(hb_mean, 4) if hb_mean is not None else "",
            "hbond_occupancy": round(hb_occ, 4) if hb_occ is not None else "",
            "hbd": fnum(desc.get(ik, {}).get("hbd")) or 0,
            "hba": fnum(desc.get(ik, {}).get("hba")) or 0,
        })

    out_csv = OUT / "conformer_entropy.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def corr(a, b):
        n = len(a)
        if n < 5:
            return None
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((v - ma) ** 2 for v in a))
        db = math.sqrt(sum((v - mb) ** 2 for v in b))
        return num / (da * db) if da and db else None

    with_res = [r for r in rows if r["lofo_resid"] not in ("", None)]
    s_conf = [fnum(r["S_conf_J_mol_K"]) for r in with_res]
    abs_res = [abs(fnum(r["lofo_resid"])) for r in with_res]

    by_fam = defaultdict(list)
    for r in rows:
        by_fam[r["family"]].append(fnum(r["N_eff"]))

    doc = {
        "schema": "b740.conformer_entropy/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(rows),
        "definitions": {
            "S_conf": "-R sum w ln w with R = 8.314462618 J/mol/K",
            "N_eff": "exp(S_conf/R)",
            "N_PR": "1/sum(w^2)",
            "N_eff_over_N_PR": ">1 means many small weights; ~1 means one dominant conformer",
        },
        "weight_provenance": {
            "energies": "GFN2-xTB total energies of r2SCAN-3c-optimised conformers",
            "is_gibbs": False,
            "note": ("ELECTRONIC energies only: no thermal correction, no solvation, no "
                     "liquid-phase population. S_conf is a STRUCTURAL flexibility index, "
                     "not a thermodynamic entropy of the liquid."),
            "temperature_K": T_K,
        },
        "hbond_criteria": {
            "donor_elements": list(HB_DONOR),
            "acceptor_elements": list(HB_ACCEPT),
            "H_to_acceptor_distance_A": [HB_DIST_MIN, HB_DIST_MAX],
            "D-H...A_angle_min_deg": HB_ANGLE_MIN,
            "note": ("geometric criteria on gas-phase conformers; an intramolecular "
                     "H-bond here is a structural feature, not a measured population"),
        },
        "S_conf": {
            "median": round(statistics.median([fnum(r["S_conf_J_mol_K"]) for r in rows]), 4),
            "min": round(min(fnum(r["S_conf_J_mol_K"]) for r in rows), 4),
            "max": round(max(fnum(r["S_conf_J_mol_K"]) for r in rows), 4),
        },
        "N_eff_by_family": {
            k: {"n": len(v), "median": round(statistics.median(v), 3)}
            for k, v in sorted(by_fam.items()) if len(v) >= 2},
        "association_with_error": {
            "pearson_Sconf_vs_abs_resid": (round(corr(s_conf, abs_res), 4)
                                           if len(with_res) >= 5 else None),
            "pearson_N_eff_vs_abs_resid": (
                round(corr([fnum(r["N_eff"]) for r in with_res], abs_res), 4)
                if len(with_res) >= 5 else None),
            "pearson_N_eff_vs_n_rotatable": (
                round(corr([fnum(r["N_eff"]) for r in rows],
                           [fnum(r["n_rotatable"]) or 0.0 for r in rows]), 4)
                if corr([fnum(r["N_eff"]) for r in rows],
                        [fnum(r["n_rotatable"]) or 0.0 for r in rows]) is not None
                else None),
            "n_used": len(with_res),
            "caveat": "n=39; descriptive only, no p-value claimed",
        },
        "hbond_summary": {
            "n_with_hbond_data": sum(1 for r in rows if r["hbond_mean_count"] != ""),
            "median_hbond_occupancy": (
                round(statistics.median([fnum(r["hbond_occupancy"]) for r in rows
                                         if r["hbond_occupancy"] != ""]), 4)
                if any(r["hbond_occupancy"] != "" for r in rows) else None),
        },
    }
    (OUT / "conformer_entropy_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'conformer_entropy_summary.json'}")
    print(f"molecules: {len(rows)}")
    print(f"S_conf J/mol/K: {doc['S_conf']}")
    print(f"hbond data on {doc['hbond_summary']['n_with_hbond_data']} molecules")
    print()
    print("association with error:")
    for k, v in doc["association_with_error"].items():
        print(f"  {k}: {v}")
    print()
    print(f"{'family':24s} {'n':>3s} {'median N_eff':>13s}")
    for k, v in sorted(doc["N_eff_by_family"].items(), key=lambda kv: -kv[1]["median"]):
        print(f"  {k:22s} {v['n']:3d} {v['median']:13.3f}")


if __name__ == "__main__":
    main()
