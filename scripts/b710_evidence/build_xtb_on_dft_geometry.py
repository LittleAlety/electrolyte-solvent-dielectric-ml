#!/usr/bin/env python
"""B710-07: prepare xTB-on-DFT-geometry single points (the missing 2x2 cell).

Only ONE cell of the method x geometry matrix is missing:

            xTB geom          DFT geom
  xTB       have (v6.0)       MISSING
  DFT       have (B702 SP)    have (B702 Opt)

This stage runs the PLAN's phase 1: 12 representative molecules, GFN2-xTB single
point on the r2SCAN-3c optimised geometry. No re-optimisation -- a single point at
fixed coordinates, so the only variable is the electronic-structure method.

It extracts the final DFT geometry from the ORCA output (last CARTESIAN COORDINATES
block), verifies the atom count and element order against the input geometry, and
writes xTB inputs. The actual xTB run is launched separately on the cluster.

Outputs (outputs/b710_evidence/xtb_on_dft_geometry/):
  xtb_dft_geom_inputs/<inchikey>/xtb.xyz
  xtb_dft_geom_inputs/<inchikey>/run.sh
  xtb_on_dft_geometry_preflight.json
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "xtb_on_dft_geometry"
GEN = "build_xtb_on_dft_geometry/1.0.0"

PROD = REPO_ROOT / "outputs" / "b700" / "B701_DFT" / "production_239"
OPT_RES = PROD / "results_opt"
SP_INPUTS = PROD / "package_sp" / "jobs"

RE_XYZBLOCK = re.compile(
    r"CARTESIAN COORDINATES \(ANGSTROEM\)\s*\n-+\s*\n(.*?)\n\s*\n", re.S)

# 12 molecules covering the families named in the plan (small, high-eps, low-eps,
# halocarbon, strongly polar, flexible, O-heterocycle, S-containing). Chosen from
# the 239 by inchikey so the selection is auditable and not name-based.
PREFLIGHT_SAMPLE = [
    "WEVYAHXRMPXWCK-UHFFFAOYSA-N",  # acetonitrile (small, polar, fixture)
    "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",  # ethanol (protic, high eps)
    "QPFMBZIOSGYJDE-UHFFFAOYSA-N",  # 1,1,2,2-tetrachloroethane (halocarbon)
    "CXWXQJXEFPUFDZ-UHFFFAOYSA-N",  # tetralin (aromatic, low eps)
    "DHKHKXVYLBGOIT-UHFFFAOYSA-N",  # 1,1-diethoxyethane (ether, flexible)
    "BMRWNKZVCUKKSR-UHFFFAOYSA-N",  # 1,2-butanediol (polyol, high eps)
    "ZWEHNKRNPOVVGH-UHFFFAOYSA-N",  # 2-butanone (ketone)
    "PIICEJLVQHRZGT-UHFFFAOYSA-N",  # ethylenediamine (amine, very polar)
    "PGMYKACGEOXYJE-UHFFFAOYSA-N",  # amyl acetate (ester, flexible)
    "PSXCGTLGGVDWFU-UHFFFAOYSA-N",  # propylene glycol dinitrate (nitro)
    "PMJHHCWVYXUKFD-SNAWJCMRSA-N",  # 1,3-pentadiene (diene, low eps)
    "OIFBSDVPJOWBCH-UHFFFAOYSA-N",  # diethyl carbonate (carbonate)
]


def load_csv(path: Path) -> list[dict]:
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def last_geometry(text: str) -> list[tuple[str, float, float, float]] | None:
    blocks = RE_XYZBLOCK.findall(text)
    if not blocks:
        return None
    block = blocks[-1]
    atoms = []
    for line in block.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
        except ValueError:
            continue
    return atoms or None


def read_xyz(path: Path) -> list[tuple[str, float, float, float]]:
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    n = int(lines[0])
    atoms = []
    for line in lines[2:2 + n]:
        p = line.split()
        atoms.append((p[0], float(p[1]), float(p[2]), float(p[3])))
    return atoms


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inp_dir = OUT / "xtb_dft_geom_inputs"
    inp_dir.mkdir(exist_ok=True)

    opt = {r["inchikey"]: r for r in load_csv(PROD / "parsed_opt.csv")}
    sp = {r["inchikey"]: r for r in load_csv(PROD / "parsed_sp.csv")}

    records = []
    ok = 0
    for ik in PREFLIGHT_SAMPLE:
        job = OPT_RES / ik / "job.out"
        sp_geom = SP_INPUTS / ik / "geom.xyz"
        rec = {
            "inchikey": ik,
            "name": sp.get(ik, {}).get("name", ""),
            "family": sp.get(ik, {}).get("family", ""),
            "opt_status": opt.get(ik, {}).get("status"),
            "opt_converged": opt.get(ik, {}).get("optimization_converged"),
            "has_sp_input_geometry": sp_geom.exists(),
            "has_opt_output": job.exists(),
            "atom_count": None,
            "atom_order_matches_input": None,
            "status": "PENDING",
        }
        if not (job.exists() and sp_geom.exists()):
            rec["status"] = "MISSING_INPUT"
            records.append(rec)
            continue

        dft_atoms = last_geometry(job.read_text(encoding="utf-8", errors="replace"))
        inp_atoms = read_xyz(sp_geom)
        if dft_atoms is None:
            rec["status"] = "NO_GEOMETRY_IN_OUTPUT"
            records.append(rec)
            continue

        rec["atom_count"] = len(dft_atoms)
        # atom order must match the input geometry's element sequence
        same_n = len(dft_atoms) == len(inp_atoms)
        same_elem = same_n and all(dft_atoms[i][0] == inp_atoms[i][0]
                                   for i in range(len(inp_atoms)))
        rec["atom_order_matches_input"] = bool(same_elem)
        if not same_n:
            rec["status"] = "ATOM_COUNT_MISMATCH"
            records.append(rec)
            continue

        rec["max_coordinate_drift_A"] = round(max(
            max(abs(dft_atoms[i][1] - inp_atoms[i][1]),
                abs(dft_atoms[i][2] - inp_atoms[i][2]),
                abs(dft_atoms[i][3] - inp_atoms[i][3]))
            for i in range(len(inp_atoms))), 4)

        d = inp_dir / ik
        d.mkdir(exist_ok=True)
        xyz_text = f"{len(dft_atoms)}\nDFT(r2SCAN-3c) optimised geometry, GFN2-xTB single point\n"
        xyz_text += "\n".join(f"{a[0]:2s} {a[1]:14.8f} {a[2]:14.8f} {a[3]:14.8f}"
                              for a in dft_atoms) + "\n"
        (d / "xtb.xyz").write_text(xyz_text, encoding="utf-8")
        (d / "run.sh").write_text(
            "#!/bin/bash\n"
            "# GFN2-xTB single point at fixed r2SCAN-3c geometry (no optimisation)\n"
            "set -u\n"
            "xtb xtb.xyz --sp --chrg 0 --uhf 0 --namespace sp > xtb_sp.out 2>&1\n"
            "echo exit=$?\n",
            encoding="utf-8")
        rec["status"] = "INPUT_READY"
        rec["xyz_sha256"] = sha256(d / "xtb.xyz")
        ok += 1
        records.append(rec)

    doc = {
        "schema": "b710.xtb_on_dft_geom_preflight/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "stage": "phase1_preflight_12",
        "method": "GFN2-xTB single point at fixed r2SCAN-3c geometry",
        "no_reoptimisation": True,
        "charge": 0,
        "multiplicity": 1,
        "n_requested": len(PREFLIGHT_SAMPLE),
        "n_input_ready": ok,
        "atom_order_verified_against_input": all(
            r["atom_order_matches_input"] is True for r in records
            if r["status"] == "INPUT_READY"),
        "records": records,
        "next_step": "run run.sh on a compute node; do NOT submit to a login node",
    }
    (OUT / "xtb_on_dft_geometry_preflight.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'xtb_on_dft_geometry_preflight.json'}")
    print(f"input-ready: {ok}/{len(PREFLIGHT_SAMPLE)}")
    print(f"{'inchikey':30s} {'atoms':>5s} {'order_ok':>8s} {'drift_A':>8s} status")
    for r in records:
        print(f"{r['inchikey']:30s} {str(r['atom_count']):>5s} "
              f"{str(r['atom_order_matches_input']):>8s} "
              f"{str(r.get('max_coordinate_drift_A', '')):>8s} {r['status']}")


if __name__ == "__main__":
    main()
