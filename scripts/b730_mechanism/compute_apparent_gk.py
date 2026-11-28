#!/usr/bin/env python
"""B731-01: physical decomposition of the liquid dielectric response.

The point of this script is to stop treating mu^2/V_m as just another feature and
instead put it inside the relation that actually governs the static permittivity,
then ask what is LEFT OVER after the single-molecule part is accounted for.

Framework (Kirkwood-Froehlich, the form CRAFT-epsilon also uses):

    (eps_s - eps_inf)(2 eps_s + eps_inf)     N_A mu^2 g
    ------------------------------------ = ------------
        eps_s (eps_inf + 2)^2              9 eps0 kB T V_m

Solving for the leftover term with a GAS-PHASE single-molecule mu gives what is
deliberately named `apparent_correlation_factor` (g_app), NOT the Kirkwood g:

  g_app = [9 eps0 kB T V_m / (N_A mu^2)] * X(eps_s, eps_inf)

Why "apparent": a gas-phase mu differs from the liquid-phase dipole (induced
polarisation, hydrogen bonding), and a single conformer differs from the liquid
ensemble. So g_app absorbs dipole enhancement + orientational correlation +
single-molecule approximation error + condition mismatch. It is a diagnostic,
never a measurement of intermolecular correlation strength.

eps_inf: the correct route is a measured refractive index (eps_inf ~= n_D^2).
This repository has NO refractive-index column, so:
  A. `eps_inf` from n_D^2 where n_D exists (ComBat `Refraction`, exploratory)
  B. else Clausius-Mossotti from the r2SCAN-3c isotropic polarizability
  C. else a documented fallback eps_inf = 2.0 (clearly flagged)
Route A is preferred where available; the script records which route each
molecule used, and every analysis is reported by route so a fallback cannot
silently drive a conclusion.

Data admission: molar volume from measured density at ~298 K where available
(Te 293-303 K), else the RDKit/Bouteloup-style estimate, again flagged.

Outputs (outputs/b730_mechanism/dielectric_physics/):
  dielectric_physics_decomposition.csv
  apparent_gk_summary.json
  eps_inf_route_audit.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "dielectric_physics"
GEN = "compute_apparent_gk/1.0.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
DENSITY = REPO_ROOT / "data" / "density_v01.csv"
CB = REPO_ROOT / "data" / "external_raw" / "combat" / "data.csv"

N_A = 6.02214076e23       # mol^-1
EPS0 = 8.8541878128e-12   # F m^-1
KB = 1.380649e-23         # J K^-1
DEBYE_C_M = 3.33564e-30   # C m per debye
AU_TO_A3 = 0.14818471     # bohr^3 -> A^3

# g_app divides by mu^2, so it is numerically undefined for non-polar molecules.
# 29 of 239 have mu < 0.15 D; for those the orientation term is ~0 and any g_app
# is an artefact of the division (values up to 1e14 were produced before this
# guard). They are reported but NOT summarised as physics.
MU_MIN_FOR_GAPP = 0.3     # D

T_REF = 298.15
T_TOL = 5.0               # density accepted within +-5 K of the epsilon temperature
EPS_INF_FALLBACK = 2.0    # documented fallback, flagged per row


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


def cm_eps_inf(alpha_au: float, vm_m3_mol: float) -> float | None:
    """Clausius-Mossotti eps_inf from isotropic polarizability (a.u.) and V_m.

    x = (4 pi / 3) * N_A * alpha[cm^3/mol] / V_m[cm^3/mol], capped below 1.
    alpha[A^3] = alpha_au * AU_TO_A3 ; V_m[cm^3/mol] = vm_m3_mol * 1e6
    """
    if alpha_au is None or not vm_m3_mol or vm_m3_mol <= 0:
        return None
    alpha_A3 = alpha_au * AU_TO_A3
    vm_cm3 = vm_m3_mol * 1e6
    x = (4.0 * math.pi / 3.0) * N_A * alpha_A3 * 1e-24 / vm_cm3
    if x >= 0.99:
        x = 0.99
    return (1 + 2 * x) / (1 - x)


def kf_rhs(eps_s: float, eps_inf: float) -> float | None:
    """(eps_s - eps_inf)(2 eps_s + eps_inf) / (eps_s (eps_inf + 2)^2)."""
    if eps_s <= 0 or eps_inf <= 0 or eps_s <= eps_inf:
        return None
    num = (eps_s - eps_inf) * (2 * eps_s + eps_inf)
    den = eps_s * (eps_inf + 2) ** 2
    return num / den if den else None


def g_apparent(eps_s: float, eps_inf: float, mu_D: float, vm_m3_mol: float,
               T: float) -> float | None:
    """g_app = [9 eps0 kB T V_m / (N_A mu^2)] * X(eps_s, eps_inf).

    Result is positive when the liquid's orientation term exceeds what the
    gas-phase single-molecule dipole can supply; <1 indicates the single-molecule
    dipole already over-explains the permittivity (dipole cancellation or
    overestimated mu).
    """
    X = kf_rhs(eps_s, eps_inf)
    if X is None or not mu_D or mu_D <= 1e-9 or not vm_m3_mol or vm_m3_mol <= 0:
        return None
    mu_cm = mu_D * DEBYE_C_M
    return (9 * EPS0 * KB * T * vm_m3_mol) / (N_A * mu_cm ** 2) * X


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)
    eps_map = {r["inchikey"]: r for r in rows}

    # ---------------- measured density near the target temperature --------
    dens = defaultdict(list)
    for r in load_csv(DENSITY):
        if (r.get("phase") or "") not in ("Liquid", "Metastable liquid"):
            continue
        ik = (r.get("inchikey") or "").strip()
        rho = fnum(r.get("density_kg_m3"))
        T = fnum(r.get("T_K"))
        if not ik or rho is None or T is None or rho <= 0:
            continue
        dens[ik].append((T, rho))

    # ---------------- refractive index (ComBat, exploratory only) ---------
    nD = {}
    for r in load_csv(CB):
        ik = (r.get("InChI Key") or "").strip()
        v = fnum(r.get("Refraction"))
        if ik and v is not None and 1.0 < v < 2.0:
            nD[ik] = v

    records = []
    route_counts = Counter()
    vm_source = Counter()
    for r in rows:
        ik = r["inchikey"]
        eps_s = fnum(r.get("epsilon"))
        mu = fnum(r.get("dipole_D_v7"))
        alpha = fnum(r.get("polarizability_au_v7"))
        T = fnum(r.get("T_K")) or T_REF
        mw = fnum(r.get("mw"))

        # molar volume: prefer measured density compatible with the label's T
        vm_used, vm_src = None, "UNAVAILABLE"
        if ik in dens:
            close = [(abs(t - T), rho) for t, rho in dens[ik] if abs(t - T) <= T_TOL]
            if close:
                close.sort()
                rho = statistics.median([c[1] for c in close])
                if mw and rho > 0:
                    # V_m [m3/mol] = (M [g/mol] / 1000 [g/kg]) / rho [kg/m3]
                    # A first version divided by an extra 1e6, making V_m 1000x too
                    # small; that both inflated g_app by 1000 and pushed the
                    # Clausius-Mossotti x above 0.99 so eps_inf fell back for
                    # every molecule with a measured density.
                    vm_used = (mw / 1000.0) / rho
                    vm_src = "MEASURED_DENSITY"
        if vm_used is None:
            est = fnum(r.get("molar_volume_m3_mol"))
            if est:
                # IMPORTANT: this column is NOT a liquid molar volume. It is the
                # RDKit vdW cavity volume times N_A, i.e. ~half the real liquid
                # V_m (bromoethane: 39.3 vs 74.6 cm^3/mol). Using it inflates both
                # the Clausius-Mossotti x and g_app. Kept as a last resort and
                # flagged as its own source so the analysis can be split by it.
                vm_used, vm_src = est, "RDKIT_VDW_VOLUME_NOT_LIQUID_VM"
        vm_source[vm_src] += 1

        # eps_inf by declared route priority
        eps_inf, route = None, "FALLBACK"
        if ik in nD:
            eps_inf, route = nD[ik] ** 2, "N_D_SQUARED"
        else:
            ci = cm_eps_inf(alpha, vm_used)
            if ci is not None and 1.0 < ci < 30:
                eps_inf, route = ci, "CLAUSIUS_MOSSOTTI"
            else:
                eps_inf, route, = EPS_INF_FALLBACK, "FALLBACK"
        route_counts[route] += 1

        # g_app is only meaningful when there IS a dipole to speak of.
        g = None
        g_valid = False
        if eps_s and eps_inf and mu and vm_used:
            g = g_apparent(eps_s, eps_inf, mu, vm_used, T)
            g_valid = bool(mu >= MU_MIN_FOR_GAPP)

        hbd = fnum(r.get("hbd"))
        hba = fnum(r.get("hba"))
        records.append({
            "inchikey": ik,
            "name": r.get("name", ""),
            "family": r.get("family", ""),
            "epsilon_s": eps_s if eps_s is not None else "",
            "epsilon_inf": round(eps_inf, 4) if eps_inf else "",
            "eps_inf_route": route,
            "n_D": nD.get(ik, ""),
            "dipole_D": mu if mu is not None else "",
            "polarizability_au": alpha if alpha is not None else "",
            "molar_volume_m3_mol": vm_used if vm_used else "",
            "molar_volume_source": vm_src,
            "temperature_K": T,
            "mw": mw if mw is not None else "",
            "mu_sq_over_Vm": (round((mu * DEBYE_C_M) ** 2 / vm_used, 30)
                              if (mu is not None and vm_used) else ""),
            "apparent_gk": round(g, 4) if g is not None else "",
            "apparent_gk_valid": "true" if g_valid else "false",
            "log10_apparent_gk": round(math.log10(g), 4) if g and g > 0 else "",
            "kf_rhs": (round(kf_rhs(eps_s, eps_inf), 6)
                       if (eps_s and eps_inf and kf_rhs(eps_s, eps_inf) is not None)
                       else ""),
            "hbd": hbd if hbd is not None else "",
            "hba": hba if hba is not None else "",
            "n_rotatable": fnum(r.get("n_rotatable")) or "",
            "fraction_csp3": fnum(r.get("fraction_csp3")) or "",
            "molecular_volume_A3": fnum(r.get("molecular_volume_A3")) or "",
        })

    out_csv = OUT / "dielectric_physics_decomposition.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    # ---------------- summaries ------------------------------------------
    # only dipole-bearing molecules can carry a g_app at all
    with_g = [r for r in records
              if r["apparent_gk_valid"] == "true"
              and fnum(r["apparent_gk"]) is not None]
    n_nonpolar_excluded = sum(1 for r in records
                              if r["apparent_gk_valid"] == "false"
                              and fnum(r["dipole_D"]) is not None)

    def stats(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return {"n": 0}
        s = sorted(vals)
        return {"n": len(vals), "median": round(statistics.median(s), 4),
                "mean": round(statistics.mean(s), 4),
                "p10": round(s[int(0.1 * (len(s) - 1))], 4),
                "p90": round(s[int(0.9 * (len(s) - 1))], 4),
                "min": round(s[0], 4), "max": round(s[-1], 4)}

    by_route = defaultdict(list)
    for r in with_g:
        by_route[r["eps_inf_route"]].append(fnum(r["apparent_gk"]))

    by_family = defaultdict(list)
    by_vm = defaultdict(list)
    for r in with_g:
        by_family[r["family"]].append(fnum(r["apparent_gk"]))
        by_vm[r["molar_volume_source"]].append(fnum(r["apparent_gk"]))

    def corr(a, b):
        n = len(a)
        if n < 4:
            return None
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((v - ma) ** 2 for v in a))
        db = math.sqrt(sum((v - mb) ** 2 for v in b))
        return num / (da * db) if da and db else None

    # PRIMARY subset: only molecules whose V_m came from a measured liquid density.
    # The vdW-volume group has V_m ~ half the true value, which biases eps_inf up
    # and g_app down by construction, so mixing them would manufacture a fake
    # family signal (the two groups differ 0.23 vs 1.10 in median g_app).
    primary = [r for r in with_g if r["molar_volume_source"] == "MEASURED_DENSITY"]
    by_fam_primary = defaultdict(list)
    for r in primary:
        by_fam_primary[r["family"]].append(fnum(r["apparent_gk"]))
    hbd_rho = hba_rho = rot_rho = None
    if len(primary) > 10:
        g = [fnum(r["apparent_gk"]) for r in primary]
        hbd_rho = corr(g, [fnum(r["hbd"]) or 0.0 for r in primary])
        hba_rho = corr(g, [fnum(r["hba"]) or 0.0 for r in primary])
        rot_rho = corr(g, [fnum(r["n_rotatable"]) or 0.0 for r in primary])

    doc = {
        "schema": "b730.apparent_gk/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "framework": "Kirkwood-Froehlich solved for the leftover correlation term",
        "naming": {
            "apparent_correlation_factor": (
                "g_app, computed from a GAS-PHASE single-molecule dipole. It is NOT the "
                "Kirkwood g. It mixes liquid-phase dipole enhancement, orientational "
                "correlation, single-molecule approximation error and condition mismatch."
            ),
            "forbidden_interpretation": (
                "do not report g_app as a pure intermolecular correlation strength"
            ),
        },
        "n_molecules": len(records),
        "coverage": {
            "with_apparent_gk": len(with_g),
            "fraction": round(len(with_g) / len(records), 4),
            "mu_min_for_gapp_D": MU_MIN_FOR_GAPP,
            "excluded_due_to_near_zero_dipole": n_nonpolar_excluded,
            "exclusion_reason": (
                "g_app ~ 1/mu^2 diverges as mu -> 0, so for non-polar liquids it is "
                "not a physical quantity. Values are still written to the CSV with "
                "apparent_gk_valid=false so the exclusion is auditable, but they are "
                "kept out of every summary statistic and every correlation."
            ),
            "eps_inf_routes": dict(route_counts),
            "molar_volume_sources": dict(vm_source),
            "molar_volume_warning": (
                "MEASURED_DENSITY is a real liquid V_m. RDKIT_VDW_VOLUME_NOT_LIQUID_VM "
                "is the vdW cavity volume x N_A, roughly half the liquid V_m "
                "(bromoethane 39.3 vs 74.6 cm^3/mol), so eps_inf and g_app for those "
                "molecules are biased. Conclusions are reported per source."
            ),
            "n_with_measured_nD": len(nD),
        },
        "eps_inf_route_audit": {
            "N_D_SQUARED": "measured refractive index squared (preferred)",
            "CLAUSIUS_MOSSOTTI": "from r2SCAN-3c polarizability and molar volume",
            "FALLBACK": f"eps_inf = {EPS_INF_FALLBACK}, flagged; conclusions that depend "
                        "on this route are not reported as physical results",
        },
        "PRIMARY_subset": {
            "definition": "molecules whose molar volume came from a measured liquid density",
            "n": len(primary),
            "g_app": stats([fnum(r["apparent_gk"]) for r in primary]),
            "g_app_by_family": {k: stats(v) for k, v in sorted(by_fam_primary.items())
                                if len(v) >= 3},
            "correlations": {
                "pearson_g_vs_hbd": round(hbd_rho, 4) if hbd_rho is not None else None,
                "pearson_g_vs_hba": round(hba_rho, 4) if hba_rho is not None else None,
                "pearson_g_vs_n_rotatable": round(rot_rho, 4) if rot_rho is not None else None,
                "caveat": "descriptive; no p-value claimed",
            },
        },
        "apparent_gk_all": stats([fnum(r["apparent_gk"]) for r in with_g]),
        "apparent_gk_by_route": {
            k: stats(v) for k, v in by_route.items()},
        "apparent_gk_by_molar_volume_source": {
            k: stats(v) for k, v in by_vm.items()},
        "apparent_gk_by_family": {
            k: stats(v) for k, v in sorted(by_family.items()) if len(v) >= 3},
        "association_descriptor_correlations": {
            "pearson_g_vs_hbd": round(hbd_rho, 4) if hbd_rho is not None else None,
            "pearson_g_vs_hba": round(hba_rho, 4) if hba_rho is not None else None,
            "pearson_g_vs_n_rotatable": round(rot_rho, 4) if rot_rho is not None else None,
            "caveat": ("descriptive only: no permuted p-value is claimed, and the "
                       "g_app definition contains the approximation error we are "
                       "trying to attribute"),
        },
        "limitations": [
            "no refractive index in the frozen 239 -> eps_inf comes from Clausius-Mossotti "
            "with a computed polarizability for most molecules; that is itself a model",
            "molar volume is measured density for a subset and an RDKit estimate otherwise",
            "gas-phase mu means g_app is not the Kirkwood g",
            "temperature matching is +-5 K on density and the label T is source-level",
        ],
    }
    (OUT / "apparent_gk_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "eps_inf_route_audit.json").write_text(
        json.dumps({"schema": "b730.eps_inf_route/v1",
                    "generated_at_utc": doc["generated_at_utc"],
                    "counts": dict(route_counts),
                    "per_molecule": [
                        {"inchikey": r["inchikey"], "route": r["eps_inf_route"],
                         "epsilon_inf": r["epsilon_inf"]} for r in records]},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'apparent_gk_summary.json'}")
    print(f"Wrote {OUT / 'eps_inf_route_audit.json'}")
    print()
    print(f"n = {len(records)}, with g_app = {len(with_g)} "
          f"({doc['coverage']['fraction']:.1%})")
    print(f"eps_inf routes: {dict(route_counts)}")
    print(f"molar volume sources: {dict(vm_source)}")
    print()
    print("g_app (all):", doc["apparent_gk_all"])
    print()
    print(f"{'family':24s} {'n':>4s} {'median g_app':>13s}")
    for k, v in sorted(doc["apparent_gk_by_family"].items(),
                       key=lambda kv: -kv[1]["median"]):
        print(f"  {k:22s} {v['n']:4d} {v['median']:13.3f}")
    print()
    pr = doc["PRIMARY_subset"]
    print()
    print(f"PRIMARY (measured density only): n={pr['n']}  {pr['g_app']}")
    for k, v in sorted(pr["g_app_by_family"].items(), key=lambda kv: -kv[1]["median"]):
        print(f"  {k:22s} {v['n']:3d} {v['median']:9.3f}")
    print(f"  correlations: {pr['correlations']}")


if __name__ == "__main__":
    main()
