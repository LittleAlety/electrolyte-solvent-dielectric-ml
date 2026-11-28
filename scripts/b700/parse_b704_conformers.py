#!/usr/bin/env python
"""Parse B704 conformer ORCA outputs and build the conformer descriptor table.

Inputs:
  outputs/b700/B704_conformers/results/<inchikey>/conf<N>/job.out

Output:
  outputs/b700/B704_conformers/parsed_conformers.csv
  outputs/b700/B704_conformers/parsed_conformers.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B704 = OUT / "B704_conformers"
RESULTS = B704 / "results"
GEN = "parse_b704_conformers/1.0.0"

RE_TERM = re.compile(r"ORCA TERMINATED NORMALLY")
RE_DIPOLE = re.compile(r"Magnitude \(Debye\)\s*:\s*([-+]?\d+\.\d+)")
RE_ALPHA = re.compile(r"Isotropic polarizability\s*:\s*([-+]?\d+\.\d+)")
RE_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)")
RE_CYCLE = re.compile(r"SCF CONVERGED AFTER\s+(\d+)\s+CYCLES")
RE_OPT = re.compile(r"THE OPTIMIZATION HAS CONVERGED|OPTIMIZATION CONVERGED")


def parse_one(text: str) -> dict:
    dipoles = RE_DIPOLE.findall(text)
    alphas = RE_ALPHA.findall(text)
    energies = RE_ENERGY.findall(text)
    cycles = RE_CYCLE.findall(text)
    return {
        "terminated_normally": bool(RE_TERM.search(text)),
        "dipole_D": float(dipoles[-1]) if dipoles else None,
        "polarizability_au": float(alphas[-1]) if alphas else None,
        "total_energy_hartree": float(energies[-1]) if energies else None,
        "scf_cycles": int(cycles[-1]) if cycles else None,
    }


def main() -> int:
    if not RESULTS.exists():
        print(f"FATAL: no results at {RESULTS}", file=sys.stderr)
        return 2

    # Load reference data
    sp = {}
    sp_path = OUT / "B701_DFT" / "production_239" / "parsed_sp.csv"
    if sp_path.exists():
        raw = sp_path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = None
        if text:
            import io
            header = text.splitlines()[0]
            delim = ";" if header.count(";") > header.count(",") else ","
            for r in csv.DictReader(io.StringIO(text, newline=""), delimiter=delim):
                ik = r.get("inchikey", "").strip()
                if ik:
                    sp[ik] = r

    rows = []
    for job_dir in sorted(RESULTS.iterdir()):
        if not job_dir.is_dir():
            continue
        ik = job_dir.name
        for conf_dir in sorted(job_dir.iterdir()):
            if not conf_dir.is_dir():
                continue
            conf_id = conf_dir.name
            out_file = conf_dir / "job.out"
            if not out_file.is_file():
                continue
            text = out_file.read_text(encoding="utf-8", errors="replace")
            parsed = parse_one(text)
            sp_row = sp.get(ik, {})
            rows.append({
                "inchikey": ik,
                "name": sp_row.get("name", ""),
                "family": sp_row.get("family", ""),
                "conformer_id": conf_id,
                "status": "OK" if parsed["terminated_normally"] else "FAILED",
                "dipole_D": parsed["dipole_D"] if parsed["dipole_D"] is not None else "",
                "polarizability_au": parsed["polarizability_au"] if parsed["polarizability_au"] is not None else "",
                "total_energy_hartree": parsed["total_energy_hartree"] if parsed["total_energy_hartree"] is not None else "",
                "scf_cycles": parsed["scf_cycles"] if parsed["scf_cycles"] is not None else "",
                "sp_dipole_D": sp_row.get("dipole_D", ""),
                "sp_energy_hartree": sp_row.get("total_energy_hartree", ""),
            })

    if not rows:
        print("No conformer results found")
        return 0

    out_csv = B704 / "parsed_conformers.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    ok = [r for r in rows if r["status"] == "OK"]
    by_mol = defaultdict(list)
    for r in ok:
        by_mol[r["inchikey"]].append(r)

    summary = {
        "n_conformers_total": len(rows),
        "n_conformers_ok": len(ok),
        "n_molecules": len(by_mol),
        "families": dict(Counter(r["family"] for r in ok)),
    }

    # Boltzmann-weighted averages
    boltzmann = []
    for ik, confs in by_mol.items():
        if len(confs) < 2:
            continue
        energies = [r["total_energy_hartree"] for r in confs if r["total_energy_hartree"]]
        if not energies:
            continue
        e_min = min(energies)
        weights = [math.exp(-(e - e_min) * 627.509) for e in energies]  # Hartree to kcal/mol
        w_sum = sum(weights)
        if w_sum <= 0:
            continue
        dipoles = [r["dipole_D"] for r in confs if r["dipole_D"] is not None]
        polars = [r["polarizability_au"] for r in confs if r["polarizability_au"] is not None]
        boltzmann.append({
            "inchikey": ik,
            "name": confs[0]["name"],
            "n_conformers": len(confs),
            "boltzmann_dipole_D": sum(w * d for w, d in zip(weights, dipoles)) / w_sum if dipoles else None,
            "boltzmann_polarizability_au": sum(w * p for w, p in zip(weights, polars)) / w_sum if polars else None,
            "single_conformer_dipole_D": dipoles[0] if dipoles else None,
            "dipole_spread_D": max(dipoles) - min(dipoles) if len(dipoles) > 1 else 0,
        })

    summary["boltzmann_weighted"] = boltzmann

    out_json = B704 / "parsed_conformers.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    print(f"Conformers: {len(rows)}, OK: {len(ok)}, Molecules: {len(by_mol)}")
    print(f"Boltzmann averages: {len(boltzmann)} molecules")
    return 0


if __name__ == "__main__":
    import math
    import sys
    sys.exit(main())
