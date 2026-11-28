#!/usr/bin/env python
"""Parse fetched ORCA production opt outputs and build parsed_opt.csv.

Reuses the parse_one regex from scripts/b700/parse_b701_orca.py.

Output:
  outputs/b700/B701_DFT/production_239/parsed_opt.csv
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
B701 = REPO_ROOT / "outputs" / "b700" / "B701_DFT"
PROD = B701 / "production_239"
RES = PROD / "results_opt"
JOBS = RES

RE_TERM = re.compile(r"ORCA TERMINATED NORMALLY")
RE_DIPOLE = re.compile(r"Magnitude \(Debye\)\s*:\s*([-+]?\d+\.\d+)")
RE_ALPHA = re.compile(r"Isotropic polarizability\s*:\s*([-+]?\d+\.\d+)")
RE_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)")
RE_CYCLE = re.compile(r"Cycle\s+(\d+)\s+RMSD\s+[-+]?\d+\.\d+")
RE_OPT = re.compile(r"THE OPTIMIZATION HAS CONVERGED|OPTIMIZATION CONVERGED")


def parse_one(text: str) -> dict:
    dipoles = RE_DIPOLE.findall(text)
    alphas = RE_ALPHA.findall(text)
    energies = RE_ENERGY.findall(text)
    cycles = RE_CYCLE.findall(text)
    return {
        "terminated_normally": bool(RE_TERM.search(text)),
        "dipole_D": float(dipoles[-1]) if dipoles else None,
        "n_dipole_blocks": len(dipoles),
        "polarizability_au": float(alphas[-1]) if alphas else None,
        "total_energy_hartree": float(energies[-1]) if energies else None,
        "scf_cycles": int(cycles[-1]) if cycles else None,
        "optimization_converged": bool(RE_OPT.search(text)),
    }


def main() -> int:
    if not JOBS.is_dir():
        print(f"FATAL: no results at {JOBS}", file=sys.stderr)
        return 2

    # Load reference matrix for names/families/epsilon
    import io
    matrix = {}
    for name in ["model_matrix_b100.csv"]:
        p = REPO_ROOT / "outputs" / "b100" / name
        if not p.exists():
            continue
        raw = p.read_bytes()
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            continue
        hdr = text.splitlines()[0]
        delim = ";" if hdr.count(";") > hdr.count(",") else ","
        for r in csv.DictReader(io.StringIO(text, newline=""), delimiter=delim):
            ik = (r.get("inchikey") or "").strip()
            if ik:
                matrix[ik] = r

    rows = []
    for d in sorted(JOBS.iterdir()):
        f = d / "job.out"
        if not f.is_file():
            continue
        ik = d.name
        parsed = parse_one(f.read_text(encoding="utf-8", errors="replace"))
        m = matrix.get(ik, {})
        rows.append({
            "inchikey": ik,
            "name": m.get("name", ""),
            "family": m.get("family", ""),
            "epsilon": m.get("epsilon", ""),
            "status": "OK" if parsed["terminated_normally"] else "NOT_TERMINATED",
            **parsed,
        })

    out = PROD / "parsed_opt.csv"
    if rows:
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    ok = sum(1 for r in rows if r["status"] == "OK")
    conv = sum(1 for r in rows if r.get("optimization_converged"))
    print(f"Wrote {out}")
    print(f"Rows: {len(rows)}, OK: {ok}, converged: {conv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
