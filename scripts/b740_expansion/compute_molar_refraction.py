#!/usr/bin/env python
"""B744-01: liquid thermodynamic indices from the recovered ThermoML data.

v7.4 recovered refractive index (86 molecules, 37 of them in CORE239), density at
many temperatures, and (for a few) enthalpy of vaporisation. That makes several
standard liquid-state indices computable for the first time in this project:

  Molar refraction      R_m = [(n_D^2 - 1)/(n_D^2 + 2)] * V_m
  Lorentz-Lorenz alpha  alpha_LL = (3/(4 pi N_A)) * (n_D^2-1)/(n_D^2+2) * V_m
  Cohesive energy dens. CED = (dH_vap - R T) / V_m
  Hildebrand parameter  delta_H = sqrt(CED)
  Lippert-Mataga        Delta f = (eps-1)/(2eps+1) - (n^2-1)/(2n^2+1)
  H-bond site density   rho_HBD = N_HBD / V_m , rho_HBA = N_HBA / V_m
  Dielectric T coeff.   (d eps / d T)_P by local slope where >=3 points exist

Units are checked explicitly because that is where these formulas usually break:
  V_m in cm^3/mol, R_m in cm^3/mol, CED in MPa = J/cm^3, alpha_LL in cm^3/mol
  which converts to A^3 by 1e24 / N_A.

Temperature matching: every index is computed from ONE (T, eps, n, rho) tuple, so
the inputs must share a temperature to within 2 K; otherwise the molecule is
skipped for that index and the skip is counted. No cross-temperature splicing.

Outputs (outputs/b740_expansion/thermodynamic_properties/):
  liquid_thermodynamic_indices.csv
  thermodynamic_summary.json
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
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "thermodynamic_properties"
GEN = "compute_molar_refraction/1.0.0"

SCAN = REPO_ROOT / "outputs" / "b740_expansion" / "thermoml" / "thermoml_local_scan.csv"
COHORT = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion" / "cohort_ledger.csv"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
POLAR = (REPO_ROOT / "outputs" / "b740_expansion" / "molecular_descriptors"
         / "polarizability_tensor.csv")

N_A = 6.02214076e23
R_GAS = 8.314462618        # J/mol/K
T_TOL = 2.0                # K, inputs of one index must share this window
AU_TO_A3 = 0.14818471

# IUPAC 2021 standard atomic weights (abridged to elements that appear in this
# corpus). Needed because V_m = M/rho, and M is only present in the CORE239
# descriptor table -- the 67 NEW_MOLECULE_VALIDATED molecules have no row there.
ATOMIC_WEIGHTS = {
    "H": 1.008, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078, "Ti": 47.867,
    "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693,
    "Cu": 63.546, "Zn": 65.38, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Mo": 95.95, "Ag": 107.868, "Cd": 112.414, "Sn": 118.710, "Sb": 121.760,
    "I": 126.904, "Ba": 137.327, "Pt": 195.084, "Au": 196.967, "Hg": 200.592,
    "Pb": 207.2,
}
FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def mw_from_formula(formula: str) -> float | None:
    """Molecular weight from a ThermoML formula string.

    Corrections applied after the first version silently returned None for every
    new molecule (V_m was then blank even though a measured density existed):

      * multi-component formulas (``;`` or a free ``.`` hydrate separator) are
        REFUSED rather than summed -- summing them would invent a V_m
      * charges / radicals (``+``, ``-``, ``^``) are refused: ThermoML keeps the
        neutral formula for these records but a charge suffix means the string
        was not what we assume
      * unknown element symbols are refused instead of being skipped (a skipped
        token would silently produce a too-small M and therefore a too-small V_m)
    """
    if not formula:
        return None
    f = formula.strip()
    if not f or ";" in f or "+" in f or "-" in f or "^" in f:
        return None
    # a hydrate separator only counts when it separates two formula fragments
    if "." in f:
        parts = [p for p in f.split(".") if p]
        if len(parts) != 1:
            return None
        f = parts[0]
    total = 0.0
    pos = 0
    n_tokens = 0
    while pos < len(f):
        m = FORMULA_TOKEN.match(f, pos)
        if not m:
            return None
        sym, cnt = m.group(1), m.group(2)
        if sym not in ATOMIC_WEIGHTS:
            return None
        total += ATOMIC_WEIGHTS[sym] * (int(cnt) if cnt else 1)
        n_tokens += 1
        pos = m.end()
    return total if n_tokens and total > 0 else None


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


def molar_refraction(nD, vm_cm3):
    """R_m = (n^2-1)/(n^2+2) * V_m  [cm^3/mol]."""
    if nD is None or vm_cm3 is None or vm_cm3 <= 0 or nD <= 1:
        return None
    return (nD * nD - 1) / (nD * nD + 2) * vm_cm3


def lorentz_lorenz_alpha_A3(nD, vm_cm3):
    """alpha = (3/(4 pi N_A)) * (n^2-1)/(n^2+2) * V_m, returned in A^3.

    V_m[cm^3/mol] * 1e-24 = m^3/mol ... conversion handled by the 1e24/N_A factor.
    """
    if nD is None or vm_cm3 is None or vm_cm3 <= 0 or nD <= 1:
        return None
    alpha_cm3 = 3.0 / (4.0 * math.pi * N_A) * (nD ** 2 - 1) / (nD ** 2 + 2) * vm_cm3
    return alpha_cm3 * 1e24


def lippert_mataga(eps, nD):
    if eps is None or nD is None or eps <= 1 or nD <= 1:
        return None
    return ((eps - 1) / (2 * eps + 1)) - ((nD ** 2 - 1) / (2 * nD ** 2 + 1))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scan = load_csv(SCAN)
    cohort = {r["inchikey"]: r for r in load_csv(COHORT)}
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    polar = {r["inchikey"]: r for r in load_csv(POLAR) if r["layer"] == "opt"}
    if not polar:                       # fall back to the SP layer if opt is absent
        polar = {r["inchikey"]: r for r in load_csv(POLAR) if r["layer"] == "sp"}

    pure = [r for r in scan if r["is_mixture"] == "false"]
    by_prop = defaultdict(lambda: defaultdict(list))   # ik -> prop -> [(T, val)]
    formula_votes = defaultdict(Counter)               # ik -> Counter(formula)
    for r in pure:
        p = r["property"]
        if p not in ("dielectric_constant_static", "density",
                     "refractive_index", "enthalpy_of_vaporization"):
            continue
        T = fnum(r["temperature_K"])
        v = fnum(r["value"])
        if T is None or v is None:
            continue
        by_prop[r["inchikey"]][p].append((T, v))
        f = (r.get("formula") or "").strip()
        if f:
            formula_votes[r["inchikey"]][f] += 1

    rows = []
    skip = Counter()
    mw_checks = []      # (descriptor mw, formula mw) for overlap validation
    for ik, props in sorted(by_prop.items()):
        eps_l = sorted(props.get("dielectric_constant_static", []))
        rho_l = sorted(props.get("density", []))
        ri_l = sorted(props.get("refractive_index", []))
        hv_l = sorted(props.get("enthalpy_of_vaporization", []))
        if not eps_l:
            continue

        mw = fnum(desc.get(ik, {}).get("mw"))
        mw_source = "CORE239_DESCRIPTOR" if mw else ""
        formula = formula_votes[ik].most_common(1)[0][0] if formula_votes.get(ik) else ""
        if mw is None:
            mw = mw_from_formula(formula)
            mw_source = "THERMOML_FORMULA" if mw else ""
        if mw is not None and formula:
            check_mw = mw_from_formula(formula)
            if check_mw is not None:
                mw_checks.append((mw, check_mw))
        hbd = fnum(desc.get(ik, {}).get("hbd"))
        hba = fnum(desc.get(ik, {}).get("hba"))
        alpha_au = fnum(polar.get(ik, {}).get("alpha_bar_au"))

        # ---- dielectric temperature coefficient (needs >=3 points) ----
        deps_dT = None
        if len(eps_l) >= 3:
            Ts = [t for t, _ in eps_l]
            Es = [v for _, v in eps_l]
            mt, me = statistics.mean(Ts), statistics.mean(Es)
            den = sum((t - mt) ** 2 for t in Ts)
            if den > 0:
                deps_dT = sum((Ts[i] - mt) * (Es[i] - me) for i in range(len(Ts))) / den

        # ---- matched (T, eps, n, rho) tuples for the composite indices ----
        matched_ri = 0
        matched_rho = 0
        candidates = []
        for T_e, eps in eps_l:
            # nearest refractive index within T_TOL
            cand = [(abs(T_r - T_e), v) for T_r, v in ri_l if abs(T_r - T_e) <= T_TOL]
            nD, dT_ri = (min(cand)[1], min(cand)[0]) if cand else (None, None)
            cand_rho = [(abs(T_r - T_e), v) for T_r, v in rho_l if abs(T_r - T_e) <= T_TOL]
            rho, dT_rho = (min(cand_rho)[1], min(cand_rho)[0]) if cand_rho else (None, None)
            if nD is not None:
                matched_ri += 1
            if rho is not None:
                matched_rho += 1
            if nD is None and rho is None:
                continue
            vm = None
            if rho and mw:
                vm = (mw / 1000.0) / rho * 1e6          # cm^3/mol from kg/m^3
            if nD is None and vm is None:
                continue
            # BUG-FIX: the first version kept the FIRST eps point that had either
            # nD or rho. That discarded temperatures where BOTH were present and
            # left molar_refraction blank for molecules whose first matched
            # temperature happened to be an n-only point. Prefer the most complete
            # tuple, then the smallest |dT|.
            completeness = int(nD is not None) + int(vm is not None)
            dT_sum = (dT_ri or 0.0) + (dT_rho or 0.0)
            candidates.append((completeness, -dT_sum, {
                "T": T_e, "eps": eps, "nD": nD, "rho": rho, "vm": vm}))
        row_best = max(candidates, key=lambda c: (c[0], c[1]))[2] if candidates else None

        if row_best is None:
            skip["no_matched_ri_or_rho"] += 1
            continue

        vm = row_best["vm"]
        nD = row_best["nD"]
        # if RI is missing but we have both eps and density, still record V_m-based terms
        Rm = molar_refraction(nD, vm) if nD is not None else None
        aLL = lorentz_lorenz_alpha_A3(nD, vm) if nD is not None else None
        df = lippert_mataga(row_best["eps"], nD) if nD is not None else None

        ced = None
        delta_h = None
        if hv_l and vm:
            # nearest enthalpy of vaporisation, and require temperature proximity
            cand = [(abs(T - row_best["T"]), v) for T, v in hv_l
                    if abs(T - row_best["T"]) <= 10.0]
            if cand:
                dh = min(cand)[1]                       # J/mol (ThermoML SI)
                ced = (dh - R_GAS * row_best["T"]) / (vm * 1e-6)   # J/m^3
                ced = ced / 1e6                          # MPa = J/cm^3
                delta_h = math.sqrt(max(ced, 0.0))

        rho_hbd = (hbd / vm) if (hbd is not None and vm) else None
        rho_hba = (hba / vm) if (hba is not None and vm) else None

        rows.append({
            "inchikey": ik,
            "name": cohort.get(ik, {}).get("name") or desc.get(ik, {}).get("name", ""),
            "cohort": cohort.get(ik, {}).get("cohort", ""),
            "in_core239": cohort.get(ik, {}).get("in_core239", ""),
            "formula": formula,
            "mw_g_mol": round(mw, 3) if mw else "",
            "mw_source": mw_source,
            "matched_T_K": round(row_best["T"], 2),
            "epsilon_at_matched_T": round(row_best["eps"], 4),
            "n_D": nD if nD is not None else "",
            "density_kg_m3": row_best["rho"] if row_best["rho"] is not None else "",
            "molar_volume_cm3_mol": round(vm, 4) if vm else "",
            "molar_refraction_cm3_mol": round(Rm, 4) if Rm is not None else "",
            "lorentz_lorenz_alpha_A3": round(aLL, 4) if aLL is not None else "",
            "dft_alpha_iso_A3": (round(alpha_au * AU_TO_A3, 4)
                                 if alpha_au is not None else ""),
            "alpha_LL_minus_dft_A3": (round(aLL - alpha_au * AU_TO_A3, 4)
                                      if (aLL is not None and alpha_au is not None) else ""),
            "lippert_mataga_delta_f": round(df, 5) if df is not None else "",
            "cohesive_energy_density_MPa": round(ced, 4) if ced is not None else "",
            "hildebrand_MPa_half": round(delta_h, 4) if delta_h is not None else "",
            "rho_HBD_per_cm3": round(rho_hbd, 6) if rho_hbd is not None else "",
            "rho_HBA_per_cm3": round(rho_hba, 6) if rho_hba is not None else "",
            "d_eps_dT_per_K": round(deps_dT, 6) if deps_dT is not None else "",
            "n_eps_points": len(eps_l),
            "n_ri_points": len(ri_l),
            "n_rho_points": len(rho_l),
            "n_hvap_points": len(hv_l),
            "n_matched_ri_pairs": matched_ri,
            "n_matched_rho_pairs": matched_rho,
        })

    out_csv = OUT / "liquid_thermodynamic_indices.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def stats(key):
        v = [fnum(r[key]) for r in rows if r[key] not in ("", None)]
        v = [x for x in v if x is not None]
        if not v:
            return {"n": 0}
        return {"n": len(v), "median": round(statistics.median(v), 4),
                "min": round(min(v), 4), "max": round(max(v), 4)}

    # alpha_LL vs DFT alpha: the key validation of the DFT polarizability
    pairs = [(fnum(r["lorentz_lorenz_alpha_A3"]), fnum(r["dft_alpha_iso_A3"]))
             for r in rows
             if r["lorentz_lorenz_alpha_A3"] not in ("", None)
             and r["dft_alpha_iso_A3"] not in ("", None)]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    corr = mae = None
    if len(pairs) >= 5:
        ma = statistics.mean([p[0] for p in pairs])
        mb = statistics.mean([p[1] for p in pairs])
        num = sum((p[0] - ma) * (p[1] - mb) for p in pairs)
        da = math.sqrt(sum((p[0] - ma) ** 2 for p in pairs))
        db = math.sqrt(sum((p[1] - mb) ** 2 for p in pairs))
        corr = round(num / (da * db), 4) if da and db else None
        mae = round(statistics.mean(abs(p[0] - p[1]) for p in pairs), 4)

    doc = {
        "schema": "b740.thermodynamic_indices/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(rows),
        "n_in_core239": sum(1 for r in rows if r["in_core239"] == "true"),
        "temperature_matching": {
            "tolerance_K": T_TOL,
            "rule": ("one index is computed from one (T, eps, n, rho) tuple; inputs "
                     "must share T within the tolerance, no cross-T splicing"),
            "n_molecules_skipped_no_match": skip.get("no_matched_ri_or_rho", 0),
        },
        "molar_volume": {
            "formula": "V_m = M / rho with M in g/mol and rho in kg/m^3 -> V_m in cm^3/mol",
            "n_from_descriptor_mw": sum(1 for r in rows
                                        if r["mw_source"] == "CORE239_DESCRIPTOR"),
            "n_from_thermoml_formula": sum(1 for r in rows
                                           if r["mw_source"] == "THERMOML_FORMULA"),
            "n_without_molar_mass": sum(1 for r in rows if not r["mw_source"]),
            "formula_mw_crosscheck": {
                "n_overlap": len(mw_checks),
                "max_abs_deviation_g_mol": (round(max(abs(a - b) for a, b in mw_checks), 3)
                                            if mw_checks else None),
                "note": ("where both a CORE239 descriptor mass and a ThermoML formula "
                         "mass exist they are compared; the formula mass is used only "
                         "when the descriptor mass is absent"),
            },
            "consequence": ("before this fallback the 67 NEW_MOLECULE_VALIDATED molecules "
                            "had a measured density but no M, so V_m -- and therefore "
                            "molar refraction, CED and H-bond site density -- was blank"),
        },
        "formulas": {
            "molar_refraction": "R_m = (n^2-1)/(n^2+2) * V_m   [cm^3/mol]",
            "lorentz_lorenz_alpha": "alpha = 3/(4 pi N_A) * (n^2-1)/(n^2+2) * V_m -> A^3",
            "cohesive_energy_density": "CED = (dH_vap - RT)/V_m   [MPa = J/cm^3]",
            "hildebrand": "delta_H = sqrt(CED)",
            "lippert_mataga": "df = (eps-1)/(2eps+1) - (n^2-1)/(2n^2+1)",
            "hbond_site_density": "rho_HBD = N_HBD/V_m ; rho_HBA = N_HBA/V_m",
            "dielectric_T_coefficient": "OLS slope of eps vs T (>=3 points)",
        },
        "coverage": {
            "with_molar_volume": sum(1 for r in rows
                                     if r["molar_volume_cm3_mol"] not in ("", None)),
            "with_molar_refraction": sum(1 for r in rows
                                         if r["molar_refraction_cm3_mol"] not in ("", None)),
            "with_lippert_mataga": sum(1 for r in rows
                                       if r["lippert_mataga_delta_f"] not in ("", None)),
            "with_CED": sum(1 for r in rows
                            if r["cohesive_energy_density_MPa"] not in ("", None)),
            "with_d_eps_dT": sum(1 for r in rows
                                 if r["d_eps_dT_per_K"] not in ("", None)),
        },
        "distributions": {
            "molar_refraction": stats("molar_refraction_cm3_mol"),
            "lippert_mataga_delta_f": stats("lippert_mataga_delta_f"),
            "d_eps_dT_per_K": stats("d_eps_dT_per_K"),
        },
        "dft_polarizability_validation": {
            "what": ("Lorentz-Lorenz polarizability from measured n_D and V_m, "
                     "compared with the r2SCAN-3c isotropic alpha"),
            "n_pairs": len(pairs),
            "pearson_r": corr,
            "mae_A3": mae,
            "interpretation": ("a high r means the DFT polarizability is consistent "
                               "with the optical response; a systematic offset means "
                               "the two definitions differ (gas-phase vs condensed)"),
        },
        "caveats": [
            "CORRECTION: the local ThermoML corpus contains ZERO enthalpy-of-vaporisation "
            "records (see thermoml_coverage.json, 'enthalpy_of_vaporization': 0). CED and "
            "the Hildebrand parameter are therefore NOT_TESTABLE from this data, not "
            "'computed on a small subset' -- an earlier wording of this caveat said "
            "'sparse', which understated the gap",
            "Lorentz-Lorenz uses n_D at the sodium D line; comparing it with a STATIC "
            "DFT polarizability assumes the optical and static electronic responses "
            "coincide, which is an approximation, not an identity",
            "3-4 pi N_A conversion is the SI form; the 1e24 factor converts cm^3 to A^3",
            "for the new molecules the molar mass comes from the ThermoML formula "
            "string, not from an optimised structure; multi-component or charged "
            "formulas are refused rather than summed, so a missing V_m here means "
            "'mass not established', not 'density absent'",
        ],
    }
    (OUT / "thermodynamic_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'thermodynamic_summary.json'}")
    print(f"molecules: {len(rows)} (CORE239: {doc['n_in_core239']})")
    print(f"coverage: {doc['coverage']}")
    print()
    print("distributions:")
    for k, v in doc["distributions"].items():
        print(f"  {k}: {v}")
    print()
    print(f"DFT alpha validation: n={len(pairs)} r={corr} MAE={mae} A^3")


if __name__ == "__main__":
    main()
