#!/usr/bin/env python
"""Build v7.0 descriptors that merge fixed-geometry SP layer with optimized-geometry opt layer.

Inputs:
  outputs/b700/B701_DFT/production_239/parsed_sp.csv
  outputs/b700/B701_DFT/production_239/parsed_opt.csv
  outputs/b700/orca_r2scan3c_descriptors.csv

Output:
  outputs/b700/orca_r2scan3c_opt_descriptors.csv
  outputs/b700/orca_r2scan3c_opt_descriptors.json

The opt layer provides geometry-consistent descriptors (energy, dipole, polarizability)
from the r2SCAN-3c optimized geometry. The SP layer provides the same descriptors
on the xTB geometry. This script merges them.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B701 = OUT / "B701_DFT" / "production_239"
GEN = "build_b705_opt_descriptors/1.0.0"


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


def main() -> None:
    sp_path = B701 / "parsed_sp.csv"
    opt_path = B701 / "parsed_opt.csv"
    base_path = OUT / "orca_r2scan3c_descriptors.csv"

    for p in [sp_path, opt_path, base_path]:
        if not p.exists():
            print(f"FATAL: missing {p}")
            return

    sp = {r["inchikey"]: r for r in load_csv(sp_path)}
    opt = {r["inchikey"]: r for r in load_csv(opt_path)}
    base = {r["inchikey"]: r for r in load_csv(base_path)}

    records = []
    for ik in sorted(base):
        b = base[ik]
        o = opt.get(ik, {})
        s = sp.get(ik, {})

        record = dict(b)  # Start with SP-layer descriptor
        # Override with opt-layer where available
        for key in ["dipole_D", "polarizability_au", "total_energy_hartree",
                    "scf_cycles", "optimization_converged", "n_dipole_blocks"]:
            opt_val = o.get(key)
            if opt_val and opt_val.strip():
                record[f"{key}_opt"] = opt_val
            else:
                record[f"{key}_opt"] = ""

        record["has_opt"] = "true" if o.get("terminated_normally") == "True" else "false"
        records.append(record)

    out_csv = OUT / "orca_r2scan3c_opt_descriptors.csv"
    if records:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)

    manifest = {
        "schema": "b700.b705_opt_descriptors/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(records),
        "n_with_opt": sum(1 for r in records if r.get("has_opt") == "true"),
        "input_hashes": {
            "parsed_sp_csv": hashlib.sha256(sp_path.read_bytes()).hexdigest(),
            "parsed_opt_csv": hashlib.sha256(opt_path.read_bytes()).hexdigest(),
            "base_descriptors_csv": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        },
    }
    out_json = OUT / "orca_r2scan3c_opt_descriptors.json"
    out_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    print(f"Total: {len(records)}, with opt: {manifest['n_with_opt']}")


if __name__ == "__main__":
    main()
