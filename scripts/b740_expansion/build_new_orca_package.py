#!/usr/bin/env python
"""B742-01: build the r2SCAN-3c OPT package for the new molecules.

The 67 NEW_MOLECULE_VALIDATED molecules have measured epsilon but no electronic
descriptor layer, which is why the transfer test (B748-02) could only use the
structural X0 layer and had no skill. This script builds the ORCA package that
closes that gap.

Only the OPT layer is built, on purpose:

  * b700's FIXED-GEOMETRY (sp) layer means "r2SCAN-3c single point on the
    GFN2-xTB geometry v6.0 used". The new molecules have no xTB geometry, so a
    package labelled 'sp' here would silently change the meaning of the layer.
    Building nothing is more honest than building a same-named different thing.
  * the OPT layer is the one the project treats as the production feature layer,
    and it is internally consistent: geometry and properties from one method.

Starting geometries are RDKit ETKDG + MMFF, not GFN2-xTB. That is a real
difference from CORE239 and is recorded in the manifest; the optimised geometry
is r2SCAN-3c in both cases, so the produced layer stays comparable.

Cluster protocol is copied from outputs/b700/B701_DFT/production_239 (ORCA calls
mpirun itself, so Slurm must hand it N TASK slots, not 1 task with N cpus).

Outputs (outputs/b740_expansion/dft_expansion/):
  package_opt/jobs/<IK>/{geom.xyz,job.inp}
  package_opt/{joblist.txt,run_batch.sbatch,manifest.json}
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "outputs" / "b740_expansion" / "dft_expansion"
PKG = BASE / "package_opt"
STRUCT = (REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion"
          / "new_molecule_structures.csv")
LEDGER = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion" / "cohort_ledger.csv"
GEN = "build_new_orca_package/1.0.0"

NPROCS = 4
MAXCORE = 2000
METHOD = "r2SCAN-3c"
SEED = 42

SBATCH = """#!/bin/bash
#-------------------------------------------------------------------------------
# B742 ORCA {label} batch on WHU hpxg (chunked).
# ORCA invokes mpirun itself, so Slurm must give it N TASK slots, not 1 task with
# N cpus: the latter fails at startup with "not enough slots".
# Usage: sbatch --array=1-{n_chunks} run_batch.sbatch
#-------------------------------------------------------------------------------
#SBATCH --job-name=b742_{label}
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks={nprocs}
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%A_%a.out

set -u
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

JOB_INP = """! {method} Opt

%pal
  nprocs {nprocs}
end

%maxcore {maxcore}

%elprop
  Polar 1
end

%scf
  MaxIter 300
  TolX 1e-7
  TolE 1e-8
end

* xyzfile 0 1 geom.xyz
"""


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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def xyz_from_smiles(smiles: str):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mh = Chem.AddHs(mol)
    ok = AllChem.EmbedMolecule(mh, randomSeed=SEED)
    if ok != 0:
        ok = AllChem.EmbedMolecule(mh, randomSeed=SEED, useRandomCoords=True)
    if ok != 0:
        return None
    try:
        AllChem.MMFFOptimizeMolecule(mh, maxIters=2000)
    except Exception:                                         # noqa: BLE001
        pass
    conf = mh.GetConformer()
    lines = [f"{mh.GetNumAtoms()}", "rdkit etkdg+mmff"]
    for atom in mh.GetAtoms():
        p = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol():2s} {p.x:14.8f} {p.y:14.8f} {p.z:14.8f}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ledger = {r["inchikey"]: r for r in load_csv(LEDGER)}
    struct = load_csv(STRUCT)
    targets = [r for r in struct if ledger.get(r["inchikey"], {}).get("cohort")
               == "NEW_MOLECULE_VALIDATED"]
    print(f"structures available: {len(struct)}  targeted (VALIDATED): {len(targets)}")

    PKG.mkdir(parents=True, exist_ok=True)
    entries, failed = [], []
    for r in targets:
        ik = r["inchikey"]
        xyz = xyz_from_smiles(r["smiles"])
        if xyz is None:
            failed.append({"inchikey": ik, "name": r["name"], "reason": "3D embedding failed"})
            continue
        job = PKG / "jobs" / ik
        job.mkdir(parents=True, exist_ok=True)
        (job / "geom.xyz").write_text(xyz, encoding="utf-8")
        (job / "job.inp").write_text(
            JOB_INP.format(method=METHOD, nprocs=NPROCS, maxcore=MAXCORE), encoding="utf-8")
        entries.append({
            "inchikey": ik,
            "name": r["name"],
            "smiles": r["smiles"],
            "n_atoms": int(xyz.splitlines()[0]),
            "geom_sha256": sha256(job / "geom.xyz"),
            "inp_sha256": sha256(job / "job.inp"),
        })

    entries.sort(key=lambda e: e["inchikey"])
    # BUG-FIX: Python text mode on Windows writes CRLF, and the Slurm job then
    # fails with "cd: ...\r: No such file or directory" for every entry. The
    # joblist is consumed on Linux, so it must be written with LF explicitly.
    (PKG / "joblist.txt").write_bytes(
        ("\n".join(f"jobs/{e['inchikey']}" for e in entries) + "\n").encode("utf-8"))

    chunk = 8
    n_chunks = max(1, (len(entries) + chunk - 1) // chunk)
    (PKG / "run_batch.sbatch").write_text(
        SBATCH.format(label="opt", nprocs=NPROCS, n_chunks=n_chunks, chunk=chunk),
        encoding="utf-8", newline="\n")

    manifest = {
        "schema": "b740.orca_package/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "layer": "opt",
        "method": METHOD,
        "why_no_sp_layer": ("b700's 'sp' means single point on the GFN2-xTB geometry; the "
                            "new molecules have no xTB geometry, so a same-named layer "
                            "would change meaning"),
        "geometry_source": {
            "protocol": f"RDKit ETKDG (seed {SEED}) + MMFF optimisation",
            "difference_from_core239": ("CORE239 started from GFN2-xTB geometries; the "
                                        "optimised geometry is r2SCAN-3c in both cases"),
            "n_atoms_total": sum(e["n_atoms"] for e in entries),
        },
        "cluster": {
            "login": "pengqihang@202.114.96.180",
            "orca_expected": "6.1.1 via $HOME/project/soft/orca/env.sh",
            "slurm": "--ntasks=%d --cpus-per-task=1 (ORCA spawns its own mpirun)" % NPROCS,
            "chunk_size": chunk,
            "n_array_tasks": n_chunks,
        },
        "n_jobs": len(entries),
        "n_failed_embedding": len(failed),
        "failed": failed,
        "jobs": entries,
        "status": "BUILT_NOT_SUBMITTED",
        "note": ("this package is a computation to be run, not a result; no descriptor "
                 "value for the new molecules exists until job.out files come back"),
    }
    (PKG / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"built {len(entries)} jobs ({n_chunks} array tasks, chunk {chunk})")
    print(f"embedding failures: {len(failed)}")
    for f in failed:
        print("  FAILED", f["name"], f["reason"])


if __name__ == "__main__":
    main()
