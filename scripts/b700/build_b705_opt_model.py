#!/usr/bin/env python
"""Build the geometry-consistent v7.0 descriptor table (opt layer as primary).

Same column layout as orca_r2scan3c_descriptors.csv, but the `_v7` electronic
columns come from the r2SCAN-3c OPTIMISED geometry instead of the xTB geometry.
This lets B706 run identical experiments on both layers and isolates whether
matching the geometry to the electronic method improves prediction.

Output:
  outputs/b700/orca_r2scan3c_opt_model.csv
  outputs/b700/orca_r2scan3c_opt_model.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B701 = OUT / "B701_DFT" / "production_239"
GEN = "build_b705_opt_model/1.0.0"

BASE = OUT / "orca_r2scan3c_descriptors.csv"
OPT = B701 / "parsed_opt.csv"


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


def main() -> None:
    base = load_csv(BASE)
    opt = {r["inchikey"]: r for r in load_csv(OPT)}

    out = []
    n_replaced = 0
    for b in base:
        ik = b["inchikey"]
        o = opt.get(ik)
        row = dict(b)
        if o is not None:
            d = fnum(o.get("dipole_D"))
            a = fnum(o.get("polarizability_au"))
            e = fnum(o.get("total_energy_hartree"))
            if d is not None:
                row["dipole_D_v7"] = d
                n_replaced += 1
            if a is not None:
                row["polarizability_au_v7"] = a
            if e is not None:
                row["total_energy_hartree_v7"] = e
            mv = fnum(b.get("molar_volume_m3_mol"))
            if d is not None and mv and mv > 0:
                mu_cm = d * 3.33564e-30
                row["mu_sq_over_Vm_v7"] = (mu_cm ** 2) / mv
            elif d is not None:
                row["mu_sq_over_Vm_v7"] = ""
            if a is not None and mv and mv > 0:
                row["alpha_over_Vm_v7"] = (a * 1.648777e-41) / mv
            elif a is not None:
                row["alpha_over_Vm_v7"] = ""
            row["orca_scf_cycles_v7"] = o.get("scf_cycles", "")
            row["orca_optimization_converged_v7"] = o.get("optimization_converged", "")
            row["orca_status_v7"] = o.get("status", "")
        out.append(row)

    path = OUT / "orca_r2scan3c_opt_model.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    manifest = {
        "schema": "b700.orca_r2scan3c_opt_model/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "layer": "optimised_geometry",
        "geometry": "r2SCAN-3c optimised",
        "n_molecules": len(out),
        "n_dipole_from_opt": n_replaced,
        "input_hashes": {
            "base_descriptors": hashlib.sha256(BASE.read_bytes()).hexdigest(),
            "parsed_opt": hashlib.sha256(OPT.read_bytes()).hexdigest(),
        },
    }
    (OUT / "orca_r2scan3c_opt_model.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote {path}")
    print(f"molecules={len(out)} dipole_from_opt={n_replaced}")


if __name__ == "__main__":
    main()
