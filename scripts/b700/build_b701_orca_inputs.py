#!/usr/bin/env python
"""B701-01: build the ORCA r2SCAN-3c job package for the WHU cluster.

Two layers are produced for every molecule, because they answer different questions
and mixing them is how a method difference gets mistaken for a geometry difference:

  FIXED-GEOMETRY (sp)   r2SCAN-3c single point on the SAME geometry v6.0 used
                        (the GFN2-xTB optimised structure). Only the electronic
                        structure method changes, so a descriptor shift here is
                        attributable to the method.
  OPTIMISED (opt)       r2SCAN-3c geometry optimisation, then properties on the
                        optimised structure. This is the production feature layer:
                        it is internally consistent (geometry and properties from
                        one method) but cannot be compared one-to-one with v6.0.

The v6.0 layer remains untouched; the B3LYP numbers stay as a third, historical
reference so that method and geometry effects can be separated three ways.

Cluster facts this package depends on (verified 2026-11-24 against the cluster):
  * login  pengqihang@202.114.96.180, login node swarm02, Slurm 25.05.1
  * ORCA   6.1.1 at /home/pengqihang/project/soft/orca  (use its env.sh)
  * parallel protocol: ORCA calls mpirun itself, so Slurm must hand it
    --ntasks=N --cpus-per-task=1; the 1-task + N-cpus form fails to start.

Output: a package directory ready for rsync
        outputs/b700/B701_DFT/package_{sp,opt}/  with jobs/, manifest.json
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
B100 = REPO_ROOT / "outputs" / "b100"
OUT = REPO_ROOT / "outputs" / "b700" / "B701_DFT"

MATRIX = B100 / "model_matrix_b100.csv"
XTB_CACHE = REPO_ROOT / "data" / "interim" / "xtb_features_b100"
XTB_CACHE_ALT = REPO_ROOT / "data" / "interim" / "xtb_features"

CHARGES = {"charge": 0, "multiplicity": 1}
MAXCORE = 2000
NPROCS = 4   # must equal --ntasks in run_batch.sbatch
CHUNKS = 16  # array tasks; each walks a slice of joblist.txt in series
METHOD = "r2SCAN-3c"


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text or "", newline=""), delimiter=delim))


def fnum(v):
    s = (str(v) if v is not None else "").strip()
    if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def geometry_for(inchikey: str, smiles: str):
    """Return (atoms, source). Prefers the xTB-optimised geometry v6.0 actually used."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")

    candidates = [XTB_CACHE / inchikey / "xtbopt.xyz"]
    if XTB_CACHE_ALT.is_dir():
        candidates.append(XTB_CACHE_ALT / inchikey / "xtbopt.xyz")
        candidates.extend(sorted(XTB_CACHE_ALT.glob(f"{inchikey}__*"))
                          and [d / "xtbopt.xyz"
                               for d in sorted(XTB_CACHE_ALT.glob(f"{inchikey}__*"))])
    for c in candidates:
        if c.is_file():
            lines = c.read_text(encoding="utf-8", errors="replace").splitlines()
            try:
                n = int(lines[0].strip())
            except (ValueError, IndexError):
                continue
            atoms = []
            for ln in lines[2:2 + n]:
                parts = ln.split()
                if len(parts) >= 4:
                    atoms.append((parts[0], float(parts[1]), float(parts[2]),
                                  float(parts[3])))
            if len(atoms) == n:
                return atoms, "XTB_OPTIMISED_GEOMETRY"

    if not smiles:
        return None, "NO_GEOMETRY"
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        if AllChem.EmbedMolecule(mol, randomSeed=42, useRandomCoords=True) != 0:
            return None, "EMBED_FAILED"
    pos = mol.GetConformer().GetPositions()
    atoms = [(a.GetSymbol(), float(pos[i][0]), float(pos[i][1]), float(pos[i][2]))
             for i, a in enumerate(mol.GetAtoms())]
    return atoms, "RDKIT_EMBED_FALLBACK"


def write_xyz(path: Path, atoms) -> None:
    lines = [str(len(atoms)), ""]
    for sym, x, y, z in atoms:
        lines.append(f"{sym:2s} {x:16.8f} {y:16.8f} {z:16.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inp(path: Path, job_type: str, xyz_name: str) -> None:
    lines = [f"! {METHOD}"]
    if job_type == "opt":
        lines[0] = f"! {METHOD} Opt"
    lines += [
        "",
        "%pal",
        f"  nprocs {NPROCS}",
        "end",
        "",
        f"%maxcore {MAXCORE}",
        "",
        "%elprop",
        "  Polar 1",
        "end",
        "",
        "%scf",
        "  MaxIter 300",
        "  TolX 1e-7",
        "  TolE 1e-8",
        "end",
        "",
        f"* xyzfile {CHARGES['charge']} {CHARGES['multiplicity']} {xyz_name}",
        "",
    ]
    # %pal nprocs is injected per-job by the submit script so it matches --ntasks
    path.write_text("\n".join(lines), encoding="utf-8")


def build(package: Path, job_type: str, rows: list[dict]) -> dict:
    jobs = package / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    records = []
    for r in rows:
        ik = (r.get("inchikey") or "").strip()
        name = r.get("name", "")
        atoms, src = geometry_for(ik, r.get("smiles", ""))
        jobdir = jobs / ik
        jobdir.mkdir(parents=True, exist_ok=True)
        if atoms is None:
            records.append({"inchikey": ik, "name": name, "status": src,
                            "geometry_source": src})
            continue
        write_xyz(jobdir / "geom.xyz", atoms)
        write_inp(jobdir / "job.inp", job_type, "geom.xyz")
        records.append({
            "inchikey": ik, "name": name, "status": "READY",
            "geometry_source": src,
            "n_atoms": len(atoms),
            "epsilon": r.get("epsilon", ""),
            "family": r.get("family", ""),
            "job_dir": f"jobs/{ik}",
        })

    manifest = {
        "schema": "b700.b701_orca_package/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "job_type": job_type,
        "method": METHOD,
        "orca_version_expected": "6.1.1",
        "orca_path_on_cluster": "/home/pengqihang/project/soft/orca",
        "charge": CHARGES["charge"],
        "multiplicity": CHARGES["multiplicity"],
        "maxcore_mb": MAXCORE,
        "n_jobs": sum(1 for r in records if r["status"] == "READY"),
        "n_geometry_missing": sum(1 for r in records if r["status"] != "READY"),
        "geometry_sources": {},
        "records": records,
    }
    from collections import Counter
    manifest["geometry_sources"] = dict(Counter(r["geometry_source"]
                                                for r in records))
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # one sbatch array job over all ready job directories
    ready = [r for r in records if r["status"] == "READY"]
    order = "\n".join(r["job_dir"] for r in ready)
    (package / "joblist.txt").write_text(order + "\n", encoding="utf-8")

    # The cluster QOS caps how many jobs one user may have SUBMITTED (~20), so a
    # 239-element array is rejected outright. The array is therefore over CHUNKS:
    # a small number of tasks, each walking a contiguous slice of joblist.txt in
    # series. That keeps the submission count legal and still finishes in one pass.
    chunk = max(1, math.ceil(len(ready) / CHUNKS)) if ready else 1
    sbatch = f"""#!/bin/bash
#-------------------------------------------------------------------------------
# ORCA {METHOD} {job_type.upper()} batch on WHU hpxg (chunked).
# ORCA invokes mpirun itself, so Slurm must give it N TASK slots, not 1 task with
# N cpus: the latter fails at startup with "not enough slots".
# Usage: sbatch --array=1-{CHUNKS} run_batch.sbatch
#-------------------------------------------------------------------------------
#SBATCH --job-name=b701_{job_type}
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks={NPROCS}
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%A_%a.out

set -u
# ORCA shells out to mpirun itself, so the MPI runtime must be on PATH.
# Without this the job dies at startup with 'mpirun: command not found'.
module load openmpi/5.0
source $HOME/project/soft/orca/env.sh

PKG_DIR="${{SLURM_SUBMIT_DIR}}"
CHUNK={chunk}
FIRST=$(( (SLURM_ARRAY_TASK_ID - 1) * CHUNK + 1 ))
LAST=$(( SLURM_ARRAY_TASK_ID * CHUNK ))

for IDX in $(seq $FIRST $LAST); do
  JOB_DIR=$(sed -n "${{IDX}}p" "$PKG_DIR/joblist.txt")
  [ -z "$JOB_DIR" ] && continue
  WORK="$PKG_DIR/$JOB_DIR"
  [ -f "$WORK/job.out" ] && grep -q "ORCA TERMINATED NORMALLY" "$WORK/job.out" && continue
  cd "$WORK" || continue
  $ORCA_DIR/orca job.inp > job.out 2>&1
  RC=$?
  OK=$(grep -c "ORCA TERMINATED NORMALLY" job.out || true)
  echo "task=${{SLURM_ARRAY_TASK_ID}} idx=$IDX dir=$JOB_DIR exit=$RC ok=$OK"
  cd "$PKG_DIR" || exit 1
done
echo "chunk ${{SLURM_ARRAY_TASK_ID}} finished"
"""
    (package / "run_batch.sbatch").write_text(sbatch, encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "preflight"
    rows = load(MATRIX)
    if not rows:
        print("FATAL: missing model matrix", file=sys.stderr)
        return 2

    if stage == "preflight":
        # 12 molecules spanning the chemistry, chosen the same way v6.0 chose its
        # method-validation set, so the two are comparable
        by_fam: dict[str, list[dict]] = {}
        for r in rows:
            if (fnum(r.get("heavy_atom_count")) or 999) <= 12:
                by_fam.setdefault(r.get("family") or "unclassified", []).append(r)
        chosen: list[dict] = []
        for _fam, items in sorted(by_fam.items(), key=lambda kv: -len(kv[1])):
            chosen.append(items[0])
            if len(chosen) >= 12:
                break
        rest = sorted(rows, key=lambda r: -(fnum(r.get("dipole_D")) or 0))
        seen = {c["inchikey"] for c in chosen}
        for r in rest:
            if len(chosen) >= 12:
                break
            if r["inchikey"] not in seen:
                chosen.append(r)
                seen.add(r["inchikey"])
        chosen = chosen[:12]
        base = OUT / "preflight_12"
    elif stage == "production":
        chosen = rows
        base = OUT / "production_239"
    else:
        print(f"FATAL: unknown stage {stage}", file=sys.stderr)
        return 2

    for job_type in ("sp", "opt"):
        pkg = base / f"package_{job_type}"
        man = build(pkg, job_type, chosen)
        print(f"[B701-01] {stage}/{job_type}: {man['n_jobs']} jobs -> {pkg}")
        print(f"           geometry sources: {man['geometry_sources']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
