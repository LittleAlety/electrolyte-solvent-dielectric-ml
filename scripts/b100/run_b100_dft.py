#!/usr/bin/env python
"""B100-20: DFT layer -- method validation, then single-point batch.

PLAN B v6.0 specifies the DFT layer as: single-point on the GFN2-xTB optimised
geometry, and requires a 12-molecule method validation BEFORE any batch run, with the
protocol frozen afterwards.

The A repository's r2SCAN-3c/ORCA protocol is not reproducible here: ORCA is
commercial and the A-repository runs were submitted to a cluster this session cannot
reach. So the DFT is done with PySCF instead -- a genuine DFT code -- and the choice is
declared rather than presented as the original protocol. What must NOT happen is
substituting xTB numbers and labelling them DFT.

Validation stage (12 molecules spanning polarity, H-bonding and halocarbons):
  * B3LYP/def2-SVP   (fast reference)
  * B3LYP/def2-TZVP  (basis-set sensitivity)
and for each, the correlation between the xTB and DFT dipole moments. If xTB dipoles
track DFT well, then the E1 result "electronic descriptors barely beat structure" is a
statement about the descriptor set, not about xTB being a bad proxy. If they do not,
that is itself the finding, and E2 (xTB vs DFT) becomes a real experiment rather than
a formality.

Output: outputs/b100/dft_validation_b100.json
        outputs/b100/dft_descriptors_b100.csv   (deliverable)
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
CACHE = REPO_ROOT / "data" / "interim" / "dft_b100"
GENERATOR = "run_b100_dft/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"

# The frozen protocol. Changing any of these must be a visible edit, not a silent
# default, because the batch numbers are only comparable within one protocol.
XC = "b3lyp"
BASIS_VALIDATION = ["def2-svp", "def2-tzvp"]
BASIS_PRODUCTION = "def2-svp"
MAX_CYCLE = 200
CONV_TOL = 1e-9
HARTREE_TO_EV = 27.211386245988

# A hard size cap, imposed by disk rather than by chemistry.
#
# Triolein (63 heavy atoms) with def2-TZVP and density fitting wrote a 49 GB auxiliary
# tensor and filled the drive; the run then died with ENOSPC, which is not a scientific
# result. 235 of the 239 molecules have <= 20 heavy atoms, so the cap costs almost
# nothing in coverage while keeping the largest auxiliary tensor around a few GB.
MAX_HEAVY_ATOMS = 20
# Validation uses both bases, so it must stay small enough that the TZVP tensor fits.
MAX_HEAVY_ATOMS_VALIDATION = 12
MIN_FREE_GB = 12.0
TEMP_DIR = r"E:\tmp"

VALIDATION_KEYS: list[str] = []     # filled at runtime from family diversity

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find_geometry(inchikey: str, smiles: str):
    """Return an atom list from the xTB-optimised geometry, else embed from SMILES.

    Using the xTB geometry is the protocol PLAN B specifies; falling back to an
    RDKit embedding is recorded in the row so a mixed-geometry set is visible.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")

    candidates = []
    for root in (REPO_ROOT / "data" / "interim" / "xtb_features_b100" / inchikey,
                 ):
        candidates.append(root / "xtbopt.xyz")
    # the expansion cache uses <inchikey> or <inchikey>__<suffix>
    base = REPO_ROOT / "data" / "interim" / "xtb_features"
    if base.is_dir():
        candidates.append(base / inchikey / "xtbopt.xyz")
        for d in sorted(base.glob(f"{inchikey}__*")):
            candidates.append(d / "xtbopt.xyz")

    for c in candidates:
        if c.is_file():
            lines = c.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) < 3:
                continue
            try:
                n = int(lines[0].strip())
            except ValueError:
                continue
            atoms = []
            for ln in lines[2:2 + n]:
                parts = ln.split()
                if len(parts) < 4:
                    continue
                atoms.append((parts[0], (float(parts[1]), float(parts[2]),
                                         float(parts[3]))))
            if len(atoms) == n:
                return atoms, "XTB_OPTIMISED_GEOMETRY"

    if not smiles:
        return None, "NO_GEOMETRY"
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        if AllChem.EmbedMolecule(mol, randomSeed=42, useRandomCoords=True) != 0:
            return None, "EMBED_FAILED"
    pos = mol.GetConformer().GetPositions()
    atoms = [(a.GetSymbol(), tuple(pos[i]))
             for i, a in enumerate(mol.GetAtoms())]
    return atoms, "RDKIT_EMBED_FALLBACK"


def free_gb(path: str = TEMP_DIR) -> float:
    import shutil
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except Exception:                       # noqa: BLE001
        return -1.0


def run_dft(atoms, basis: str) -> dict:
    """One RKS single point with density fitting. Returns dipole in Debye and gap in eV.

    Density fitting (RI-J) is required: the plain 4-index build tried to allocate a
    1.6 GB contiguous block and aborted with `malloc failed` on the larger molecules.
    RI-J replaces that array with 3-centre integrals and is the standard choice at this
    size. The approximation is recorded in the result, not silently absorbed.

    Disk is the binding constraint, not CPU: the auxiliary tensor is written to the
    scratch directory, so free space is checked before starting and the scratch is
    forced onto the drive with room (C: was completely full on first attempt).
    """
    import os
    os.environ.setdefault("TMP", TEMP_DIR)
    os.environ.setdefault("TEMP", TEMP_DIR)
    os.environ.setdefault("TMPDIR", TEMP_DIR)
    from pyscf import gto, dft

    if free_gb() < MIN_FREE_GB:
        return {"converged": False, "error": "INSUFFICIENT_DISK",
                "free_gb": round(free_gb(), 2), "seconds": 0.0}

    mol = gto.M(atom=atoms, basis=basis, charge=0, spin=0, verbose=0,
                max_memory=2000)
    mf = dft.RKS(mol)
    mf.xc = XC
    mf = mf.density_fit()
    mf.max_cycle = MAX_CYCLE
    mf.conv_tol = CONV_TOL
    t0 = time.time()
    try:
        energy = mf.kernel()
    except (OSError, MemoryError) as exc:
        return {"converged": False, "error": f"{type(exc).__name__}: {exc}",
                "free_gb": round(free_gb(), 2), "seconds": round(time.time() - t0, 2)}
    secs = round(time.time() - t0, 2)
    if not mf.converged:
        return {"converged": False, "error": "NOT_CONVERGED", "seconds": secs}

    dm = mf.make_rdm1()
    dip_au = mf.dip_moment(mol, dm, unit="AU", verbose=0)
    magnitude_au = math.sqrt(sum(float(x) ** 2 for x in dip_au))
    dipole_D = magnitude_au * 2.541746473

    mo_e = mf.mo_energy
    occ = mf.mo_occ
    homo = max((i for i in range(len(occ)) if occ[i] > 0.5), default=None)
    lumo = min((i for i in range(len(occ)) if occ[i] < 0.5), default=None)
    gap_ev = ((mo_e[lumo] - mo_e[homo]) * HARTREE_TO_EV
              if homo is not None and lumo is not None else None)
    return {
        "converged": True, "seconds": secs,
        "total_energy_hartree": float(energy),
        "dipole_D": round(dipole_D, 4),
        "homo_lumo_gap_ev": round(gap_ev, 4) if gap_ev is not None else None,
        "n_basis": int(mol.nao),
        "basis": basis, "xc": XC,
        "density_fitting": True,
    }


def cached(inchikey: str, basis: str) -> dict | None:
    p = CACHE / f"{inchikey}__{XC}__{basis}.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:                   # noqa: BLE001
            return None
    return None


def store(inchikey: str, basis: str, rec: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{inchikey}__{XC}__{basis}.json"
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


def spearman(a, b):
    n = len(a)
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n))
                    * sum((rb[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def main() -> int:
    mode = "validate"
    if "--production" in sys.argv:
        mode = "production"
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = load(MATRIX)
    if not rows:
        print(f"FATAL: missing {MATRIX}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- choose the validation set: 12 molecules spanning the chemistry ----
    # restricted to small molecules because both bases are run, and the TZVP auxiliary
    # tensor on a mid-size molecule is what filled the disk on the first attempt
    by_fam: dict[str, list[dict]] = {}
    for r in rows:
        h = fnum(r.get("heavy_atom_count")) or 0
        if h <= MAX_HEAVY_ATOMS_VALIDATION:
            by_fam.setdefault(r.get("family") or "unclassified", []).append(r)
    validation: list[dict] = []
    for fam, items in sorted(by_fam.items(), key=lambda kv: -len(kv[1])):
        if items:
            validation.append(items[0])
        if len(validation) >= 12:
            break
    rest = sorted(rows, key=lambda r: -(fnum(r.get("dipole_D")) or 0))
    for r in rest:
        if len(validation) >= 12:
            break
        if (fnum(r.get("heavy_atom_count")) or 0) > MAX_HEAVY_ATOMS_VALIDATION:
            continue
        if r["inchikey"] not in {v["inchikey"] for v in validation}:
            validation.append(r)
    validation = validation[:12]

    if mode == "validate":
        print(f"[B100-20] VALIDATION stage: {len(validation)} molecules, "
              f"bases {BASIS_VALIDATION}")
        results = []
        for i, r in enumerate(validation, 1):
            ik = r["inchikey"]
            atoms, geom_src = find_geometry(ik, r.get("smiles", ""))
            if atoms is None:
                print(f"  {i}/{len(validation)} {r['name'][:26]:26s} "
                      f"NO GEOMETRY")
                continue
            row = {"inchikey": ik, "name": r.get("name", ""),
                   "family": r.get("family", ""),
                   "xtb_dipole_D": fnum(r.get("dipole_D")),
                   "geometry": geom_src, "bases": {}}
            for basis in BASIS_VALIDATION:
                rec = cached(ik, basis)
                if rec is None:
                    rec = run_dft(atoms, basis)
                    store(ik, basis, rec)
                row["bases"][basis] = rec
            d_svp = row["bases"].get("def2-svp", {}).get("dipole_D")
            d_tzvp = row["bases"].get("def2-tzvp", {}).get("dipole_D")
            row["basis_sensitivity_D"] = (round(abs(d_svp - d_tzvp), 4)
                                          if (d_svp is not None
                                              and d_tzvp is not None) else None)
            results.append(row)
            print(f"  {i}/{len(validation)} {r['name'][:26]:26s} "
                  f"xTB={row['xtb_dipole_D']} SVP={d_svp} TZVP={d_tzvp} "
                  f"Δbasis={row['basis_sensitivity_D']}")

        xt = [x["xtb_dipole_D"] for x in results
              if x.get("xtb_dipole_D") is not None
              and x["bases"].get("def2-tzvp", {}).get("dipole_D") is not None]
        dt = [x["bases"]["def2-tzvp"]["dipole_D"] for x in results
              if x.get("xtb_dipole_D") is not None
              and x["bases"].get("def2-tzvp", {}).get("dipole_D") is not None]
        diffs = [abs(a - b) for a, b in zip(xt, dt)]

        doc = {
            "schema": "b100.dft_validation/v1",
            "generator": GENERATOR,
            "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "why": (
                "PLAN B v6.0 要求 DFT 前先做 12 分子方法验证并冻结协议。"
                "A 仓库的 ORCA r2SCAN-3c 协议在本环境不可用 "
                "(ORCA 商业、A 仓库跑在无法访问的集群上), 因此改用 PySCF 做真正的 "
                "DFT, 并**声明这一替换**, 而不是把 xTB 结果标成 DFT。"
            ),
            "protocol": {
                "xc": XC, "basis_validation": BASIS_VALIDATION,
                "basis_production": BASIS_PRODUCTION,
                "geometry": "GFN2-xTB optimised (falls back to RDKit embedding, "
                            "recorded per row)",
                "max_cycle": MAX_CYCLE, "conv_tol": CONV_TOL,
                "engine": "PySCF 2.15.1",
            },
            "n_validated": len(results),
            "molecules": results,
            "xtb_vs_dft_dipole": {
                "n": len(xt),
                "pearson_r": round(pearson(xt, dt), 4) if len(xt) > 2 else None,
                "spearman_rho": round(spearman(xt, dt), 4) if len(xt) > 2 else None,
                "mean_abs_difference_D": round(statistics.mean(diffs), 4) if diffs else None,
                "max_abs_difference_D": round(max(diffs), 4) if diffs else None,
            },
            "basis_sensitivity": {
                "mean_abs_D": round(statistics.mean(
                    [x["basis_sensitivity_D"] for x in results
                     if x["basis_sensitivity_D"] is not None]), 4)
                if any(x["basis_sensitivity_D"] is not None for x in results)
                else None,
                "note": (
                    "def2-SVP -> def2-TZVP 的偶极变化. 若该值远小于 xTB-DFT 差, "
                    "则用 SVP 做生产计算是可接受的."
                ),
            },
            "production_decision": (
                f"采用 {XC}/{BASIS_PRODUCTION} 做生产计算"
            ),
            "inputs": {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}},
        }
        j_path = OUT / "dft_validation_b100.json"
        j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"\n[B100-20] {j_path}")
        v = doc["xtb_vs_dft_dipole"]
        print(f"  xTB vs DFT (TZVP) dipole: r={v['pearson_r']} "
              f"rho={v['spearman_rho']} MAE={v['mean_abs_difference_D']} D")
        print(f"  basis sensitivity: {doc['basis_sensitivity']['mean_abs_D']} D")
        return 0

    # ---- production ----
    sized = [r for r in rows
             if (fnum(r.get("heavy_atom_count")) or 999) <= MAX_HEAVY_ATOMS]
    n_size_excluded = len(rows) - len(sized)
    work = sized if limit is None else sized[:limit]
    print(f"[B100-20] PRODUCTION: {len(work)} molecules, "
          f"{XC}/{BASIS_PRODUCTION}")
    print(f"[B100-20] excluded for size > {MAX_HEAVY_ATOMS} heavy atoms: "
          f"{n_size_excluded}")
    out_rows: list[dict] = []
    n_fail = 0
    total_s = 0.0
    for i, r in enumerate(work, 1):
        ik = r["inchikey"]
        atoms, geom_src = find_geometry(ik, r.get("smiles", ""))
        if atoms is None:
            out_rows.append({"inchikey": ik, "name": r.get("name", ""),
                             "status": "NO_GEOMETRY"})
            n_fail += 1
            continue
        rec = cached(ik, BASIS_PRODUCTION)
        if rec is None:
            rec = run_dft(atoms, BASIS_PRODUCTION)
            store(ik, BASIS_PRODUCTION, rec)
        total_s += rec.get("seconds", 0) or 0
        if not rec.get("converged"):
            out_rows.append({"inchikey": ik, "name": r.get("name", ""),
                             "status": "NOT_CONVERGED"})
            n_fail += 1
            continue
        out_rows.append({
            "inchikey": ik, "name": r.get("name", ""),
            "status": "OK", "geometry": geom_src,
            "dft_dipole_D": rec["dipole_D"],
            "dft_homo_lumo_gap_ev": rec.get("homo_lumo_gap_ev", ""),
            "dft_total_energy_hartree": rec["total_energy_hartree"],
            "xc": XC, "basis": BASIS_PRODUCTION,
            "n_basis": rec.get("n_basis", ""),
            "xtb_dipole_D": fnum(r.get("dipole_D")),
        })
        if i % 20 == 0 or i == len(work):
            print(f"  {i}/{len(work)}  ok={sum(1 for x in out_rows if x.get('status') == 'OK')}"
                  f"  failures={n_fail}  cpu_s={total_s:.0f}")
            _write(out_rows, OUT)

    _write(out_rows, OUT)
    n_ok = sum(1 for x in out_rows if x.get("status") == "OK")
    doc = {
        "schema": "b100.dft_production/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {"xc": XC, "basis": BASIS_PRODUCTION,
                     "engine": "PySCF 2.15.1",
                     "geometry": "GFN2-xTB optimised where available"},
        "coverage": {
            "n_input": len(work), "n_ok": n_ok, "n_failed": n_fail,
            "target": 100, "minimum": 60,
            "requirement_met": n_ok >= 60,
            "target_met": n_ok >= 100,
            "n_excluded_for_size": n_size_excluded,
            "max_heavy_atoms": MAX_HEAVY_ATOMS,
            "size_cap_reason": (
                "Triolein (63 重原子) 在 def2-TZVP + 密度拟合下写出 49 GB 辅助张量"
                "并写满磁盘, 导致 ENOSPC 而非科学失败. 上限取 20 重原子, "
                "保留 235/239 个分子, 覆盖率几乎不受影响."
            ),
        },
        "compute": {"dft_cpu_seconds": round(total_s, 1),
                    "dft_core_hours": round(total_s / 3600.0, 4)},
        "note": (
            "这是真正的 DFT (PySCF B3LYP), 不是 xTB 冒充. "
            "方法在 12 分子验证后冻结; 换基组或泛函必须作为显式变更."
        ),
        "inputs": {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}},
    }
    j_path = OUT / "dft_production_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"\n[B100-20] {j_path}")
    print(f"  ok={n_ok}/{len(work)}  failures={n_fail}  "
          f"cpu={doc['compute']['dft_core_hours']} core-hours")
    return 0


def _write(rows: list[dict], out: Path) -> None:
    path = out / "dft_descriptors_b100.csv"
    fields = ["inchikey", "name", "status", "geometry", "dft_dipole_D",
              "dft_homo_lumo_gap_ev", "dft_total_energy_hartree",
              "xc", "basis", "n_basis", "xtb_dipole_D"]
    for r in rows:
        for f in fields:
            r.setdefault(f, "")
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda z: z.get("name", "")):
            w.writerow(r)


if __name__ == "__main__":
    sys.exit(main())
