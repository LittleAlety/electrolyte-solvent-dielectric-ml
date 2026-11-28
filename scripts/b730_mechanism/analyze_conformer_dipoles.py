#!/usr/bin/env python
"""B732-01: conformer dipole vectors, Boltzmann statistics and cancellation C_mu.

The v7.1 E3 analysis compared single-conformer and Boltzmann-averaged dipole
MAGNITUDES. That cannot detect the thing that actually matters for a permittivity:
whether the conformers' dipoles point in DIFFERENT directions, so the ensemble
average vector is smaller than the average magnitude.

Three distinct quantities, kept apart:

    <mu>   = sum_i w_i * mu_i          (vector; the one Onsager uses)
    <mu^2> = sum_i w_i * |mu_i|^2      (scalar mean square)
    |<mu>|^2  <=  <mu^2>               always, with equality iff all vectors parallel

Cancellation index:

    C_mu = 1 - |<mu>|^2 / <mu^2>       in [0, 1)

C_mu = 0 means all conformers point the same way; C_mu -> 1 means the vector
average nearly vanishes. It is undefined if <mu^2> ~ 0, so a guard is applied and
flagged.

Weights: Boltzmann over GFN2-xTB total energies of the r2SCAN-3c optimised
conformers. These are ELECTRONIC energies, not Gibbs free energies -- no thermal
correction, no solvation. That is stated in every output; the same approximation
the project already uses, and it is the reason C_mu is reported as a structural
diagnostic rather than a liquid-phase population statement.

Dipole vectors are read from ORCA's 'Total Dipole Moment' line (components in
atomic units) and converted with AU_TO_DEBYE = 2.541746473, the constant
CRAFT-epsilon uses, so the two analyses are on the same footing.

Outputs (outputs/b730_mechanism/conformer_mechanism/):
  conformer_dipole_statistics.csv
  conformer_cancellation_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "conformer_mechanism"
GEN = "analyze_conformer_dipoles/1.0.0"

RES = REPO_ROOT / "outputs" / "b700" / "B704_conformers" / "results"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"

R_KCAL = 0.0019872041
HARTREE_TO_KCAL = 627.5094740631
T_K = 298.15
AU_TO_DEBYE = 2.541746473
MU2_MIN = 0.05 ** 2      # D^2; below this C_mu is numerically meaningless

RE_VEC = re.compile(r"Total Dipole Moment\s*:\s*([-+]?\d+\.\d+)\s+"
                    r"([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)")
RE_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)")
RE_ALPHA = re.compile(r"Isotropic polarizability\s*:\s*([-+]?\d+\.\d+)")


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
    except Exception:
        return None


def boltzmann(energies_hartree):
    rel = [(e - min(energies_hartree)) * HARTREE_TO_KCAL for e in energies_hartree]
    w = [math.exp(-r / (R_KCAL * T_K)) for r in rel]
    s = sum(w)
    return [x / s for x in w], s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    lofo = {r["inchikey"]: r for r in load_csv(LOFO)}

    # ---------------- collect conformer dipoles and energies --------------
    per_mol = defaultdict(list)
    for d in sorted(p for p in RES.iterdir() if p.is_dir()):
        ik = d.name
        for c in sorted(p for p in d.iterdir() if p.is_dir()):
            f = c / "job.out"
            if not f.exists():
                continue
            txt = f.read_text(encoding="utf-8", errors="replace")
            v = RE_VEC.findall(txt)
            e = RE_ENERGY.findall(txt)
            a = RE_ALPHA.findall(txt)
            if not v or not e:
                continue
            x, y, z = (float(t) for t in v[-1])
            per_mol[ik].append({
                "conformer": c.name,
                "vec_au": (x, y, z),
                "energy": float(e[-1]),
                "alpha_au": float(a[-1]) if a else None,
            })

    rows = []
    for ik, confs in sorted(per_mol.items()):
        if len(confs) < 2:
            continue
        energies = [c["energy"] for c in confs]
        weights, wsum = boltzmann(energies)
        # vectors in Debye
        vecs = [tuple(comp * AU_TO_DEBYE for comp in c["vec_au"]) for c in confs]
        mags = [math.sqrt(sum(v * v for v in vv)) for vv in vecs]

        mean_vec = [sum(weights[i] * vecs[i][k] for i in range(len(vecs)))
                    for k in range(3)]
        mu_mean_sq = sum(v * v for v in mean_vec)          # |<mu>|^2
        mu_sq_mean = sum(weights[i] * mags[i] ** 2 for i in range(len(mags)))
        rms = math.sqrt(mu_sq_mean) if mu_sq_mean > 0 else 0.0
        canc = (1 - mu_mean_sq / mu_sq_mean) if mu_sq_mean > MU2_MIN else None

        single = mags[weights.index(max(weights))]          # highest-weight conformer
        alphas = [c["alpha_au"] for c in confs if c["alpha_au"] is not None]
        alpha_mean = (sum(weights[i] * alphas[i] for i in range(len(alphas)))
                      if alphas else None)
        alpha_spread = (max(alphas) - min(alphas)) if len(alphas) > 1 else None

        eps = fnum(desc.get(ik, {}).get("epsilon"))
        resid = fnum(lofo.get(ik, {}).get("resid"))
        sp_dip = fnum(desc.get(ik, {}).get("dipole_D_v7"))

        rows.append({
            "inchikey": ik,
            "name": desc.get(ik, {}).get("name", ""),
            "family": desc.get(ik, {}).get("family", ""),
            "epsilon": eps if eps is not None else "",
            "lofo_resid": resid if resid is not None else "",
            "n_conformers": len(confs),
            "mu_max_weight_D": round(single, 4),
            "mu_boltzmann_mean_magnitude_D": round(math.sqrt(mu_mean_sq), 4),
            "mu_rms_D": round(rms, 4),
            "mu_mean_sq_D2": round(mu_mean_sq, 6),
            "mu_sq_mean_D2": round(mu_sq_mean, 6),
            "C_mu": round(canc, 4) if canc is not None else "",
            "C_mu_valid": "true" if canc is not None else "false",
            "vector_vs_scalar_ratio": (round(math.sqrt(mu_mean_sq) / rms, 4)
                                       if rms > 0 else ""),
            "mu_spread_D": round(max(mags) - min(mags), 4),
            "energy_range_kcal": round((max(energies) - min(energies)) * HARTREE_TO_KCAL, 4),
            "boltzmann_sum_before_norm": round(wsum, 6),
            "alpha_boltzmann_au": round(alpha_mean, 4) if alpha_mean is not None else "",
            "alpha_spread_au": round(alpha_spread, 4) if alpha_spread is not None else "",
            "sp_dipole_D": sp_dip if sp_dip is not None else "",
            "single_vs_ensemble_dipole_diff_D": (round(single - math.sqrt(mu_mean_sq), 4)
                                                 if sp_dip is not None else ""),
        })

    out_csv = OUT / "conformer_dipole_statistics.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---------------- summaries -------------------------------------------
    valid = [r for r in rows if r["C_mu_valid"] == "true"]

    def stats(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return {"n": 0}
        s = sorted(vals)
        return {"n": len(vals), "median": round(statistics.median(s), 4),
                "mean": round(statistics.mean(s), 4),
                "min": round(s[0], 4), "max": round(s[-1], 4)}

    def corr(a, b):
        n = len(a)
        if n < 5:
            return None
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((v - ma) ** 2 for v in a))
        db = math.sqrt(sum((v - mb) ** 2 for v in b))
        return num / (da * db) if da and db else None

    by_fam = defaultdict(list)
    for r in valid:
        by_fam[r["family"]].append(fnum(r["C_mu"]))

    c_mu = [fnum(r["C_mu"]) for r in valid]
    with_resid = [r for r in valid if r["lofo_resid"] not in ("", None)]
    rho_cmu_resid = None
    if len(with_resid) >= 5:
        rho_cmu_resid = corr([fnum(r["C_mu"]) for r in with_resid],
                             [abs(fnum(r["lofo_resid"])) for r in with_resid])

    doc = {
        "schema": "b730.conformer_cancellation/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(rows),
        "n_with_valid_C_mu": len(valid),
        "definitions": {
            "mu_mean": "sum_i w_i mu_i (vector)",
            "mu_sq_mean": "sum_i w_i |mu_i|^2 (scalar)",
            "C_mu": "1 - |<mu>|^2 / <mu^2>; 0 = parallel conformers, ->1 = cancelling",
            "identity": "|<mu>|^2 <= <mu^2> always; a violation means a bug",
        },
        "weights": {
            "scheme": "Boltzmann over GFN2-xTB total energies of r2SCAN-3c conformers",
            "is_gibbs": False,
            "note": ("ELECTRONIC energies only: no thermal correction, no solvation, no "
                     "liquid-phase population. C_mu is a structural diagnostic, not a "
                     "statement about the liquid ensemble."),
            "temperature_K": T_K,
            "guard": f"C_mu reported only when <mu^2> > {MU2_MIN} D^2",
        },
        "C_mu_all": stats(c_mu),
        "C_mu_by_family": {k: stats(v) for k, v in sorted(by_fam.items()) if len(v) >= 2},
        "energy_range_kcal": stats([fnum(r["energy_range_kcal"]) for r in rows]),
        "mu_spread_D": stats([fnum(r["mu_spread_D"]) for r in rows]),
        "alpha_spread_au": stats([fnum(r["alpha_spread_au"]) for r in rows]),
        "association_with_error": {
            "pearson_Cmu_vs_abs_lofo_resid": (round(rho_cmu_resid, 4)
                                              if rho_cmu_resid is not None else None),
            "n_used": len(with_resid),
            "caveat": ("n is 39; a correlation of this size at this n is descriptive. "
                       "No p-value is claimed."),
        },
        "sanity": {
            "all_vectors_at_most_rms": all(
                math.sqrt(fnum(r["mu_mean_sq_D2"])) <= math.sqrt(fnum(r["mu_sq_mean_D2"])) + 1e-9
                for r in valid),
            "all_C_mu_in_range": all(0 <= fnum(r["C_mu"]) < 1 for r in valid),
        },
    }
    (OUT / "conformer_cancellation_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'conformer_cancellation_summary.json'}")
    print()
    print(f"molecules: {len(rows)}, valid C_mu: {len(valid)}")
    print(f"C_mu: {doc['C_mu_all']}")
    print(f"sanity: {doc['sanity']}")
    print()
    print(f"{'family':24s} {'n':>3s} {'median C_mu':>12s}")
    for k, v in sorted(doc["C_mu_by_family"].items(), key=lambda kv: -kv[1]["median"]):
        print(f"  {k:22s} {v['n']:3d} {v['median']:12.3f}")
    print()
    print(f"pearson C_mu vs |resid|: {doc['association_with_error']['pearson_Cmu_vs_abs_lofo_resid']}")


if __name__ == "__main__":
    main()
