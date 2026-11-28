#!/usr/bin/env python
"""B703-extended: separate electronic-structure effects from geometry effects.

Full method x geometry matrix available in v7.0:

                    xTB geometry            r2SCAN-3c geometry
  GFN2-xTB          v6.0 xtb_descriptors    (optional single points, if run)
  ORCA r2SCAN-3c    B702 SP layer           B702 Opt layer
  PySCF B3LYP       v6.0 dft_descriptors    -

This script quantifies:
  1. geometry effect  = descriptor(opt) - descriptor(sp)   [same method]
  2. method effect    = descriptor(sp)  - descriptor(xtb)  [same geometry]
  3. total effect     = descriptor(opt) - descriptor(xtb)

Output:
  outputs/b700/B703_full_matrix.csv
  outputs/b700/B703_full_matrix.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"
GEN = "analyze_b703_full_matrix/1.0.0"

SP = OUT / "B701_DFT" / "production_239" / "parsed_sp.csv"
OPT = OUT / "B701_DFT" / "production_239" / "parsed_opt.csv"
XTB = B100 / "xtb_descriptors_b100.csv"
B3LYP = B100 / "dft_descriptors_b100.csv"


def load_csv(path: Path) -> list[dict]:
    import io
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


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        "min": min(vals),
        "max": max(vals),
    }


def main() -> None:
    sp = {r["inchikey"]: r for r in load_csv(SP)}
    opt = {r["inchikey"]: r for r in load_csv(OPT)}
    xtb = {r["inchikey"]: r for r in load_csv(XTB)}

    rows = []
    for ik in sorted(sp):
        s = sp.get(ik, {})
        o = opt.get(ik, {})
        x = xtb.get(ik, {})

        sp_d = fnum(s.get("dipole_D"))
        sp_a = fnum(s.get("polarizability_au"))
        sp_e = fnum(s.get("total_energy_hartree"))
        opt_d = fnum(o.get("dipole_D"))
        opt_a = fnum(o.get("polarizability_au"))
        opt_e = fnum(o.get("total_energy_hartree"))
        xtb_d = fnum(x.get("dipole_D"))
        xtb_a = fnum(x.get("polarizability_au"))

        geom_d = (opt_d - sp_d) if (opt_d is not None and sp_d is not None) else None
        meth_d = (sp_d - xtb_d) if (sp_d is not None and xtb_d is not None) else None
        total_d = (opt_d - xtb_d) if (opt_d is not None and xtb_d is not None) else None
        geom_a = (opt_a - sp_a) if (opt_a is not None and sp_a is not None) else None
        meth_a = (sp_a - xtb_a) if (sp_a is not None and xtb_a is not None) else None

        rows.append({
            "inchikey": ik,
            "name": s.get("name", ""),
            "family": s.get("family", ""),
            "epsilon": s.get("epsilon", ""),
            "dipole_xtb_xTBgeom": xtb_d if xtb_d is not None else "",
            "dipole_r2sc3c_xTBgeom": sp_d if sp_d is not None else "",
            "dipole_r2sc3c_DFTgeom": opt_d if opt_d is not None else "",
            "dipole_geom_effect": geom_d if geom_d is not None else "",
            "dipole_method_effect": meth_d if meth_d is not None else "",
            "dipole_total_effect": total_d if total_d is not None else "",
            "polar_xtb_xTBgeom": xtb_a if xtb_a is not None else "",
            "polar_r2sc3c_xTBgeom": sp_a if sp_a is not None else "",
            "polar_r2sc3c_DFTgeom": opt_a if opt_a is not None else "",
            "polar_geom_effect": geom_a if geom_a is not None else "",
            "polar_method_effect": meth_a if meth_a is not None else "",
            "energy_sp_hartree": sp_e if sp_e is not None else "",
            "energy_opt_hartree": opt_e if opt_e is not None else "",
            "energy_relaxation_hartree": (opt_e - sp_e) if (opt_e is not None and sp_e is not None) else "",
        })

    out_csv = OUT / "B703_full_matrix.csv"
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Summary
    dipole_geom = [fnum(r["dipole_geom_effect"]) for r in rows]
    dipole_meth = [fnum(r["dipole_method_effect"]) for r in rows]
    dipole_total = [fnum(r["dipole_total_effect"]) for r in rows]
    polar_geom = [fnum(r["polar_geom_effect"]) for r in rows]
    polar_meth = [fnum(r["polar_method_effect"]) for r in rows]
    relax = [fnum(r["energy_relaxation_hartree"]) for r in rows]

    fam = {}
    for r in rows:
        fk = r["family"] or "unknown"
        fam.setdefault(fk, []).append(r)

    summary = {
        "n": len(rows),
        "dipole_geometry_effect": stats(dipole_geom),
        "dipole_method_effect": stats(dipole_meth),
        "dipole_total_effect": stats(dipole_total),
        "polarizability_geometry_effect": stats(polar_geom),
        "polarizability_method_effect": stats(polar_meth),
        "energy_relaxation_hartree": stats(relax),
        "family_geometry_effect_dipole": {
            k: stats([fnum(r["dipole_geom_effect"]) for r in v]) for k, v in sorted(fam.items())
        },
        "family_method_effect_dipole": {
            k: stats([fnum(r["dipole_method_effect"]) for r in v]) for k, v in sorted(fam.items())
        },
        "note": (
            "geometry effect = r2SCAN-3c(DFT geom) - r2SCAN-3c(xTB geom); "
            "method effect = r2SCAN-3c(xTB geom) - xTB(xTB geom). "
            "These separate geometry relaxation from level-of-theory change."
        ),
    }

    manifest = {
        "schema": "b700.b703_full_matrix/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "summary": summary,
        "input_hashes": {
            "parsed_sp": hashlib.sha256(SP.read_bytes()).hexdigest(),
            "parsed_opt": hashlib.sha256(OPT.read_bytes()).hexdigest(),
            "xtb_descriptors": hashlib.sha256(XTB.read_bytes()).hexdigest(),
        },
    }
    out_json = OUT / "B703_full_matrix.json"
    out_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    print(f"n = {len(rows)}")
    for k in ("dipole_geometry_effect", "dipole_method_effect", "dipole_total_effect",
              "polarizability_geometry_effect", "polarizability_method_effect"):
        s = summary[k]
        if s["n"]:
            print(f"{k:36s} mean={s['mean']:+9.4f} sd={s['sd']:8.4f} n={s['n']}")
    print(f"energy_relaxation (Hartree)          mean={summary['energy_relaxation_hartree']['mean']:+.6f}")


if __name__ == "__main__":
    main()
