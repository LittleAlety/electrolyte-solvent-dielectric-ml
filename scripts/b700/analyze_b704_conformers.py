#!/usr/bin/env python
"""B704-E3: Single-conformer vs Boltzmann-weighted multi-conformer comparison.

Compare the prediction accuracy of:
  1. Single conformer (lowest energy)
  2. Boltzmann-weighted average
  3. SP layer (single point on xTB geometry, for reference)

This answers: does multi-conformer averaging improve dielectric prediction?

Inputs:
  outputs/b700/B704_conformers/parsed_conformers.csv
  outputs/b700/B704_conformers/parsed_conformers.json
  outputs/b700/orca_r2scan3c_descriptors.csv
  outputs/b100/deliverables/epsilon_labels_b100.csv

Output:
  outputs/b700/B704_conformer_analysis.csv
  outputs/b700/B704_conformer_analysis.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B704 = OUT / "B704_conformers"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"
GEN = "analyze_b704_conformers/1.0.0"


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
    conf_csv = B704 / "parsed_conformers.csv"
    conf_json = B704 / "parsed_conformers.json"
    sp_csv = OUT / "orca_r2scan3c_descriptors.csv"
    eps_csv = B100 / "epsilon_labels_b100.csv"

    if not conf_csv.exists():
        print(f"FATAL: missing {conf_csv}")
        return

    conf_rows = load_csv(conf_csv)
    sp_rows = {r["inchikey"]: r for r in load_csv(sp_csv)} if sp_csv.exists() else {}
    eps_rows = {r["inchikey"]: r for r in load_csv(eps_csv)} if eps_csv.exists() else {}

    # Group by molecule
    by_mol = defaultdict(list)
    for r in conf_rows:
        if r.get("status") == "OK":
            by_mol[r["inchikey"]].append(r)

    records = []
    for ik, confs in by_mol.items():
        if len(confs) < 2:
            continue

        # Sort by energy
        confs_sorted = sorted(confs, key=lambda r: fnum(r.get("total_energy_hartree")) or 0)
        energies = [fnum(r.get("total_energy_hartree")) for r in confs_sorted if fnum(r.get("total_energy_hartree")) is not None]
        dipoles = [fnum(r.get("dipole_D")) for r in confs_sorted if fnum(r.get("dipole_D")) is not None]
        polars = [fnum(r.get("polarizability_au")) for r in confs_sorted if fnum(r.get("polarizability_au")) is not None]

        if not energies or not dipoles:
            continue

        # Single conformer (lowest energy)
        single_dipole = dipoles[0]
        single_polar = polars[0] if polars else None

        # Boltzmann weights
        e_min = min(energies)
        weights = [math.exp(-(e - e_min) * 627.509) for e in energies]  # Hartree to kcal/mol
        w_sum = sum(weights)
        if w_sum <= 0:
            continue

        boltz_dipole = sum(w * d for w, d in zip(weights, dipoles)) / w_sum
        boltz_polar = (sum(w * p for w, p in zip(weights, polars)) / w_sum) if polars else None

        # SP reference
        sp_row = sp_rows.get(ik, {})
        sp_dipole = fnum(sp_row.get("dipole_D_v7"))
        sp_polar = fnum(sp_row.get("polarizability_au_v7"))

        # Epsilon
        eps = fnum(eps_rows.get(ik, {}).get("epsilon"))

        record = {
            "inchikey": ik,
            "name": confs[0].get("name", ""),
            "family": confs[0].get("family", ""),
            "n_conformers": len(confs),
            "epsilon": eps if eps is not None else "",
            "single_dipole_D": single_dipole,
            "boltzmann_dipole_D": boltz_dipole,
            "sp_dipole_D": sp_dipole if sp_dipole is not None else "",
            "single_polarizability_au": single_polar if single_polar is not None else "",
            "boltzmann_polarizability_au": boltz_polar if boltz_polar is not None else "",
            "sp_polarizability_au": sp_polar if sp_polar is not None else "",
            "dipole_spread_D": max(dipoles) - min(dipoles) if len(dipoles) > 1 else 0,
            "energy_range_hartree": max(energies) - min(energies) if len(energies) > 1 else 0,
            "energy_range_kcal_mol": (max(energies) - min(energies)) * 627.509 if len(energies) > 1 else 0,
        }
        records.append(record)

    # Write CSV
    out_csv = B704 / "B704_conformer_analysis.csv"
    if records:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    # Summary statistics
    with_eps = [r for r in records if fnum(r.get("epsilon")) is not None]
    summary = {
        "n_molecules": len(records),
        "n_with_epsilon": len(with_eps),
        "dipole_spread_stats": {
            "mean": statistics.mean([r["dipole_spread_D"] for r in records]) if records else 0,
            "max": max([r["dipole_spread_D"] for r in records]) if records else 0,
        },
        "energy_range_stats_kcal_mol": {
            "mean": statistics.mean([r["energy_range_kcal_mol"] for r in records]) if records else 0,
            "max": max([r["energy_range_kcal_mol"] for r in records]) if records else 0,
        },
    }

    out_json = B704 / "B704_conformer_analysis.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    print(f"Molecules: {len(records)}, with epsilon: {len(with_eps)}")
    print(f"Dipole spread: mean={summary['dipole_spread_stats']['mean']:.3f} D, max={summary['dipole_spread_stats']['max']:.3f} D")
    print(f"Energy range: mean={summary['energy_range_stats_kcal_mol']['mean']:.2f} kcal/mol, max={summary['energy_range_stats_kcal_mol']['max']:.2f} kcal/mol")


if __name__ == "__main__":
    main()
