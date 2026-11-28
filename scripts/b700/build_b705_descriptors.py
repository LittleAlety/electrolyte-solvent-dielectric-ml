#!/usr/bin/env python
"""B705: Build v7.0 unified ORCA-r2SCAN-3c descriptor table from the SP layer.

Inputs:
  outputs/b700/B701_DFT/production_239/parsed_sp.csv
  outputs/b100/deliverables/model_matrix_b100.csv
  outputs/b100/deliverables/epsilon_labels_b100.csv

Output:
  outputs/b700/orca_r2scan3c_descriptors.csv
  outputs/b700/orca_r2scan3c_descriptors.json

The v6.0 model matrix provides structure descriptors (X0) plus xTB electronic
descriptors.  The v7.0 matrix replaces the xTB electronic layer with the ORCA
r2SCAN-3c single-point descriptors, while keeping the same structure descriptors,
same molecule set, and same epsilon labels.

Volume-normalised terms are recomputed from the ORCA values:
  mu_sq_over_Vm      = (dipole_D * 3.33564e-30)^2 / molar_volume_m3_mol
  alpha_over_Vm      = (polarizability_au * 1.648777e-41) / molar_volume_m3_mol

For reference the v6.0 values are preserved in *_v6 columns.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"
B100_DIR = REPO_ROOT / "outputs" / "b100"
GEN = "build_b705_descriptors/1.0.0"

SP = OUT / "B701_DFT" / "production_239" / "parsed_sp.csv"
MATRIX = B100_DIR / "model_matrix_b100.csv"
EPS = B100 / "epsilon_labels_b100.csv"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


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
    import math

    if not SP.exists():
        raise SystemExit(f"SP layer not found: {SP}")
    if not MATRIX.exists():
        raise SystemExit(f"Model matrix not found: {MATRIX}")
    if not EPS.exists():
        raise SystemExit(f"Epsilon labels not found: {EPS}")

    sp_rows = load_csv(SP)
    matrix_rows = load_csv(MATRIX)
    eps_rows = load_csv(EPS)

    sp_map = {r["inchikey"]: r for r in sp_rows}
    matrix_map = {r["inchikey"]: r for r in matrix_rows}
    eps_map = {r["inchikey"]: r for r in eps_rows}

    missing_in_sp = [r for r in matrix_rows if r["inchikey"] not in sp_map]
    missing_in_matrix = [r for r in sp_rows if r["inchikey"] not in matrix_map]
    missing_in_eps = [r for r in sp_rows if r["inchikey"] not in eps_map]

    # Columns we carry from the v6 model matrix (structure + xTB for reference)
    KEEP_V6 = [
        "heavy_atom_count", "n_rings", "n_rotatable", "hbd", "hba", "tpsa_A2",
        "formal_charge", "mw", "fraction_csp3", "n_aromatic_atoms", "n_hetero",
        "n_halogen", "n_N", "n_O", "n_S", "morgan2_nbits",
        "molecular_volume_A3", "molar_volume_m3_mol",
        "dipole_D", "polarizability_au", "homo_lumo_gap_ev", "total_energy_hartree",
        "mu_sq_over_Vm", "alpha_over_Vm",
        "is_protic", "has_strong_donor", "epsilon_band", "association_class",
        "family", "evidence_grade", "smiles",
    ]

    # Epsilon
    eps_cols = ["epsilon", "T_K", "evidence_grade", "frequency_basis"]

    records = []
    for ik, sp in sp_map.items():
        m = matrix_map.get(ik, {})
        e = eps_map.get(ik, {})
        dipole = fnum(sp.get("dipole_D"))
        polar = fnum(sp.get("polarizability_au"))
        mv = fnum(m.get("molar_volume_m3_mol"))
        gap = fnum(sp.get("xtb_gap_ev")) or fnum(m.get("homo_lumo_gap_ev"))
        xtb_dipole = fnum(sp.get("xtb_dipole_D"))
        b3lyp_dipole = fnum(sp.get("b3lyp_dipole_D"))

        mu2_over_vm = None
        alpha_over_vm = None
        if dipole is not None and mv is not None and mv > 0:
            mu_cm = dipole * 3.33564e-30
            mu2_over_vm = (mu_cm ** 2) / mv
        if polar is not None and mv is not None and mv > 0:
            alpha_over_vm = (polar * 1.648777e-41) / mv

        record = {
            "inchikey": ik,
            "name": sp.get("name", m.get("name", "")),
            "smiles": m.get("smiles", ""),
            "family": sp.get("family", m.get("family", "")),
            "evidence_grade": e.get("evidence_grade", m.get("evidence_grade", "")),
            "epsilon": e.get("epsilon", ""),
            "T_K": e.get("T_K", ""),
            "frequency_basis": e.get("frequency_basis", ""),
            "epsilon_unit": e.get("epsilon_unit", "static_relative"),
            # v6 X0 structure (reference)
            **{k: m.get(k, "") for k in KEEP_V6},
            # v7.0 electronic descriptors (primary)
            "dipole_D_v7": dipole if dipole is not None else "",
            "polarizability_au_v7": polar if polar is not None else "",
            "homo_lumo_gap_ev_v7": gap if gap is not None else "",
            "total_energy_hartree_v7": sp.get("total_energy_hartree", ""),
            "scf_cycles_v7": sp.get("scf_cycles", ""),
            # v7 volume-normalised terms
            "mu_sq_over_Vm_v7": mu2_over_vm if mu2_over_vm is not None else "",
            "alpha_over_Vm_v7": alpha_over_vm if alpha_over_vm is not None else "",
            # reference electronic values for cross-checks
            "dipole_D_xtb_ref": xtb_dipole if xtb_dipole is not None else "",
            "dipole_D_b3lyp_ref": b3lyp_dipole if b3lyp_dipole is not None else "",
            "polarizability_au_xtb_ref": fnum(sp.get("polarizability_au")) if False else "",  # parsed_sp has no xtb polar
            "orca_status_v7": sp.get("status", ""),
            "orca_terminated_normally_v7": sp.get("terminated_normally", ""),
            "orca_scf_cycles_v7": sp.get("scf_cycles", ""),
            "orca_optimization_converged_v7": sp.get("optimization_converged", ""),
        }
        records.append(record)

    # Write CSV
    csv_path = OUT / "orca_r2scan3c_descriptors.csv"
    if records:
        fieldnames = list(records[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    # JSON manifest
    manifest = {
        "schema": "b700.orca_r2scan3c_descriptors/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "method": "r2SCAN-3c",
        "program": "ORCA",
        "orca_version_expected": "6.1.1",
        "layer": "fixed_geometry_single_point",
        "geometry_source": "GFN2-xTB optimised (v6.0)",
        "n_molecules": len(records),
        "coverage": {
            "with_dipole": sum(1 for r in records if fnum(r.get("dipole_D_v7")) is not None),
            "with_polarizability": sum(1 for r in records if fnum(r.get("polarizability_au_v7")) is not None),
            "with_molar_volume": sum(1 for r in records if fnum(r.get("molar_volume_m3_mol")) is not None),
            "with_mu2_over_Vm": sum(1 for r in records if fnum(r.get("mu_sq_over_Vm_v7")) is not None),
            "with_alpha_over_Vm": sum(1 for r in records if fnum(r.get("alpha_over_Vm_v7")) is not None),
        },
        "input_hashes": {
            "parsed_sp_csv": sha256_file(SP),
            "model_matrix_csv": sha256_file(MATRIX),
            "epsilon_labels_csv": sha256_file(EPS),
        },
        "family_counts": dict(Counter(r["family"] for r in records)),
        "missing_from_matrix": [r["inchikey"] for r in sp_rows if r["inchikey"] not in matrix_map][:20],
        "missing_from_eps": [r["inchikey"] for r in sp_rows if r["inchikey"] not in eps_map][:20],
    }

    json_path = OUT / "orca_r2scan3c_descriptors.json"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Records: {len(records)}")
    print(f"Coverage: {manifest['coverage']}")
    print(f"Missing from matrix: {len(missing_in_matrix)}")
    print(f"Missing from epsilon: {len(missing_in_eps)}")
    print("Families:", manifest["family_counts"])


if __name__ == "__main__":
    main()
