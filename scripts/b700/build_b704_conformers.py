#!/usr/bin/env python
"""B704: Build ORCA r2SCAN-3c single-point inputs for 40 multi-conformer molecules.

Input geometries: data/interim/xtb_conformers_b100/<inchikey>/conf<N>/xtbopt.xyz
ORCA method: r2SCAN-3c (same as B701 freeze)

Output:
  outputs/b700/B704_conformers/jobs/<inchikey>/conf<N>/job.inp + geom.xyz

Total conformers: 227 across 40 molecules.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"
DATA_CONF = REPO_ROOT / "data" / "interim" / "xtb_conformers_b100"
GEN = "build_b704_conformers/1.0.0"

ORCA_TEMPLATE = """! r2SCAN-3c

%pal
  nprocs 4
end

%maxcore 2000

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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    out_base = OUT / "B704_conformers"
    out_jobs = out_base / "jobs"
    if out_jobs.exists():
        shutil.rmtree(out_jobs)
    out_jobs.mkdir(parents=True)

    # Load conformer registry (40 molecules with conformer info)
    conf_reg = {}
    reg_path = B100 / "conformer_ensemble_b100.csv"
    if reg_path.exists():
        import io
        raw = reg_path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = None
        if text:
            header = text.splitlines()[0]
            delim = ";" if header.count(";") > header.count(",") else ","
            for r in csv.DictReader(io.StringIO(text, newline=""), delimiter=delim):
                ik = r.get("inchikey", "").strip()
                if ik:
                    conf_reg[ik] = r

    # Load SP layer for names/families
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
            header = text.splitlines()[0]
            delim = ";" if header.count(";") > header.count(",") else ","
            for r in csv.DictReader(io.StringIO(text, newline=""), delimiter=delim):
                ik = r.get("inchikey", "").strip()
                if ik:
                    sp[ik] = r

    records = []
    n_total = 0
    n_ok = 0
    for ik in sorted(conf_reg):
        if ik not in sp:
            continue
        conf_dir = DATA_CONF / ik
        if not conf_dir.is_dir():
            continue
        for conf in sorted(conf_dir.iterdir()):
            if not conf.is_dir():
                continue
            xyz = conf / "xtbopt.xyz"
            if not xyz.is_file():
                xyz = conf / "input.xyz"
            if not xyz.is_file():
                continue
            n_total += 1
            # Read geometry
            geom_text = xyz.read_text(encoding="utf-8", errors="replace")
            lines = geom_text.strip().splitlines()
            if not lines:
                continue
            try:
                n_atoms = int(lines[0].strip())
                geom_lines = lines[2:2 + n_atoms]
                if len(geom_lines) < n_atoms:
                    continue
            except Exception:
                continue

            job_dir = out_jobs / ik / conf.name
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "job.inp").write_text(ORCA_TEMPLATE, encoding="utf-8")
            (job_dir / "geom.xyz").write_text("\n".join([str(n_atoms)] + lines[1:2] + geom_lines) + "\n", encoding="utf-8")
            n_ok += 1
            records.append({
                "inchikey": ik,
                "name": sp[ik].get("name", ""),
                "family": sp[ik].get("family", ""),
                "conformer_id": conf.name,
                "conformer_dir": str(conf),
                "n_atoms": n_atoms,
                "geom_sha256": sha256_file(job_dir / "geom.xyz"),
                "inp_sha256": sha256_file(job_dir / "job.inp"),
            })

    # Write manifest
    manifest = {
        "schema": "b700.b704_conformers/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "orca_version_expected": "6.1.1",
        "method": "r2SCAN-3c",
        "geometry_source": "GFN2-xTB optimised conformers",
        "n_molecules": len(set(r["inchikey"] for r in records)),
        "n_conformers": len(records),
        "job_dir": str(out_jobs),
    }
    (out_base / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write job list
    with (out_base / "joblist.txt").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(f"{r['inchikey']}/{r['conformer_id']}\n")

    print(f"Wrote inputs for {n_ok} conformers across {len(set(r['inchikey'] for r in records))} molecules")
    print(f"Job dir: {out_jobs}")
    print(f"Manifest: {out_base / 'manifest.json'}")
    print(f"Families: {Counter(r['family'] for r in records)}")


if __name__ == "__main__":
    main()
