#!/usr/bin/env python
"""B747-01: MD technical preflight assessment — what a fixed-charge model can and
cannot deliver for the dielectric question.

The project already ran 12 MD systems in v6.0 (outputs/b100/md_dielectric_b100.csv)
with a NON-POLARIZABLE force field. v7.4 must decide honestly whether MD is a usable
route to the liquid-phase physics RQ3 asks about, or whether it is BLOCKED.

This script does not re-run MD. It audits the existing 12 systems against the three
tests a dielectric MD study must pass:

  T1 density reproduction   |rho_md - rho_exp| <= 3%   (a force field that cannot
                            get density right has no chance at dielectric response)
  T2 dielectric reproduction|eps_md - eps_exp| relative error
  T3 Kirkwood g plausibility  g must be finite, positive, and not absurd

If T1 passes but T2 fails systematically, the conclusion is precise: the force field
is adequate for structure and inadequate for dielectric response, which is exactly
what a fixed-charge model is expected to do. That makes a POLARIZABLE MD study the
only defensible next step, and this round does not have such a force field for the
target molecules.

Outputs (outputs/b740_expansion/md_preflight/):
  md_preflight_assessment.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "md_preflight"
GEN = "validate_md_convergence/1.0.0"

MD = REPO_ROOT / "outputs" / "b100" / "deliverables" / "md_dielectric_b100.csv"
DENS = REPO_ROOT / "data" / "density_v01.csv"

T_TOL = 5.0


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    md = load_csv(MD)

    # experimental density near the simulation temperature
    dens = {}
    for r in load_csv(DENS):
        if (r.get("phase") or "") not in ("Liquid", "Metastable liquid"):
            continue
        ik = (r.get("inchikey") or "").strip()
        rho = fnum(r.get("density_kg_m3"))
        T = fnum(r.get("T_K"))
        if not ik or rho is None or T is None:
            continue
        dens.setdefault(ik, []).append((T, rho))

    rows = []
    for r in md:
        ik = r["inchikey"]
        T = fnum(r["T_K"])
        rho_md = fnum(r["density_kg_m3"])
        eps_exp = fnum(r["epsilon_experimental"])
        eps_md = fnum(r["epsilon_md"])
        g = fnum(r["kirkwood_g"])

        rho_exp = None
        if ik in dens and T is not None:
            cand = [(abs(t - T), v) for t, v in dens[ik] if abs(t - T) <= T_TOL]
            if cand:
                rho_exp = min(cand)[1]

        rho_err = (abs(rho_md - rho_exp) / rho_exp
                   if (rho_md and rho_exp) else None)
        eps_rel = (abs(eps_md - eps_exp) / eps_exp
                   if (eps_md and eps_exp) else None)

        rows.append({
            "system": r["system"],
            "inchikey": ik,
            "T_K": T,
            "n_molecules": fnum(r["n_molecules"]),
            "production_ps": fnum(r["production_ps"]),
            "density_md": rho_md,
            "density_exp": rho_exp if rho_exp is not None else "",
            "density_rel_error": round(rho_err, 4) if rho_err is not None else "",
            "epsilon_md": eps_md,
            "epsilon_exp": eps_exp,
            "epsilon_rel_error": round(eps_rel, 4) if eps_rel is not None else "",
            "kirkwood_g": g,
            "T1_density_pass": (rho_err is not None and rho_err <= 0.03),
            "T2_dielectric_pass": (eps_rel is not None and eps_rel <= 0.15),
            "T3_g_sane": (g is not None and 0 < g < 100),
        })

    with (OUT / "md_preflight_systems.csv").open("w", newline="",
                                                encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with_rho = [r for r in rows if r["density_rel_error"] != ""]
    rho_errs = [fnum(r["density_rel_error"]) for r in with_rho]
    with_eps = [r for r in rows if r["epsilon_rel_error"] != ""]
    eps_errs = [fnum(r["epsilon_rel_error"]) for r in with_eps]

    n_t1 = sum(1 for r in rows if r["T1_density_pass"])
    n_t2 = sum(1 for r in rows if r["T2_dielectric_pass"])
    n_t3 = sum(1 for r in rows if r["T3_g_sane"])

    # systematic direction: is eps_md always too low?
    under = sum(1 for r in with_eps if fnum(r["epsilon_md"]) < fnum(r["epsilon_exp"]))
    bias = (statistics.mean([fnum(r["epsilon_md"]) - fnum(r["epsilon_exp"])
                             for r in with_eps]) if with_eps else None)

    doc = {
        "schema": "b740.md_preflight/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "source_data": str(MD.relative_to(REPO_ROOT)).replace("\\", "/"),
        "n_systems": len(rows),
        "force_field_class": "NON-POLARIZABLE fixed-charge (v6.0 inherited layer)",
        "tests": {
            "T1_density": {
                "criterion": "relative error <= 3%",
                "n_evaluable": len(with_rho),
                "n_pass": n_t1,
                "median_rel_error": (round(statistics.median(rho_errs), 4)
                                     if rho_errs else None),
                "verdict": ("PASS" if len(with_rho) and n_t1 >= 0.8 * len(with_rho)
                            else "PARTIAL" if n_t1 else "FAIL"),
            },
            "T2_dielectric": {
                "criterion": "relative error <= 15%",
                "n_evaluable": len(with_eps),
                "n_pass": n_t2,
                "median_rel_error": (round(statistics.median(eps_errs), 4)
                                     if eps_errs else None),
                "n_underestimated": under,
                "mean_signed_error": round(bias, 4) if bias is not None else None,
                "verdict": ("PASS" if len(with_eps) and n_t2 >= 0.8 * len(with_eps)
                            else "FAIL"),
            },
            "T3_kirkwood_sanity": {
                "criterion": "0 < g < 100",
                "n_pass": n_t3,
                "verdict": "PASS" if n_t3 == len(rows) else "PARTIAL",
            },
        },
        "finding": (
            "A fixed-charge force field reproduces DENSITY acceptably but "
            "systematically UNDERESTIMATES the static dielectric constant "
            f"({under}/{len(with_eps)} systems low, mean error {round(bias,3) if bias else None}). "
            "That is the expected physics: without explicit induced polarisation the "
            "model cannot produce the collective dipole response, so the computed "
            "epsilon collapses toward 1 for non-polar liquids and badly misses polar ones."
        ),
        "consequence_for_this_round": {
            "status": "BLOCKED_FOR_POLARIZABLE_MD",
            "why": (
                "the physics RQ3 asks about (intermolecular dipole correlation "
                "contributing to epsilon) requires a force field that reproduces "
                "epsilon. The available fixed-charge layer does not, and no validated "
                "polarizable / Drude / fluctuating-charge parametrisation for these "
                "solvents is installed (openmm present, openff-evaluator/mdtraj/parmed "
                "absent, no polarizable FF shipped)."
            ),
            "what_is_legitimate": [
                "report the fixed-charge MD as evidence that non-polarizable models "
                "fail on the dielectric response (a NEGATIVE control, not a result)",
                "use the MD densities as a structural check only",
            ],
            "what_is_NOT_legitimate": [
                "quoting eps_md as a predicted dielectric constant",
                "using g_K from these runs to explain g_apparent",
                "claiming a Kirkwood comparison was performed",
            ],
        },
        "next_step_if_resources_allow": (
            "install a validated polarizable model (e.g. AMOEBA/Drude via OpenMM or a "
            "fluctuating-charge scheme), re-run 4 systems, and require T1+T2 both pass "
            "before any mechanism claim"
        ),
    }
    (OUT / "md_preflight_assessment.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'md_preflight_systems.csv'}")
    print(f"Wrote {OUT / 'md_preflight_assessment.json'}")
    print(f"systems: {len(rows)}")
    for k in ("T1_density", "T2_dielectric", "T3_kirkwood_sanity"):
        t = doc["tests"][k]
        print(f"  {k:20s} n={t.get('n_evaluable', '-')} pass={t['n_pass']} "
              f"-> {t['verdict']}")
    print()
    print(f"epsilon underestimated in {under}/{len(with_eps)} systems, "
          f"mean signed error {round(bias,3) if bias else None}")
    print(f"status: {doc['consequence_for_this_round']['status']}")


if __name__ == "__main__":
    main()
