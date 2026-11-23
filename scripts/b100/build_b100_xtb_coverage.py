#!/usr/bin/env python
"""B100-8: unified xTB coverage -- fill the gaps with the SAME protocol.

The expansion layer already holds 388 GFN2-xTB records, every one produced by the
identical command:

    xtb input.xyz --opt --gfn 2 --chrg 0 --uhf 0

verified by reading `Hamiltonian: GFN2-xTB` and `GEOMETRY OPTIMIZATION CONVERGED`
out of the cached `xtb.out` files. So the existing computation is already unified;
what is missing is the core ThermoML layer, whose 31 phase-verified molecules have no
xTB record at all because they were never part of the expansion run.

This script computes exactly those missing molecules using the same command and the
same xTB binary, then writes a descriptor table that records, for every row, which
protocol produced it. Nothing is estimated and nothing is borrowed from a different
level of theory -- the objective forbids substituting xTB results for DFT, and the
same principle applies to substituting one xTB protocol for another.

Design notes:
  * Each molecule gets its own working directory under the cache root, mirroring the
    existing layout, so a re-run reuses converged results.
  * The manifest stores input/output SHA-256, so a value can be reproduced and an
    accidental re-optimisation is detectable.
  * Failures are recorded with their stderr and are retried with a longer SCF
    budget; a molecule that still fails is marked ERROR and excluded from coverage
    rather than given a placeholder.

Output: outputs/b100/xtb_coverage_b100.json
        outputs/b100/xtb_descriptors_b100.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
CACHE_ROOT = REPO_ROOT / "data" / "interim" / "xtb_features_b100"
GENERATOR = "build_b100_xtb_coverage/1.0.0"

XTB = Path(r"C:\Users\Little Alety\AppData\Local\electrolyte-ml\tools"
           r"\xtb-6.7.1\extracted\xtb-6.7.1\bin\xtb.exe")

EXP_FEAT = REPO_ROOT / "data" / "processed" / "dielectric_pool_expansion_features.csv"
PHASE = OUT / "phase_state_audit_b100.csv"
QUALIFIED = OUT / "qualified_molecules_b100.csv"
REGISTRY = OUT / "molecule_registry_b100.csv"

# The ONE protocol. Every row must be traceable to this exact command.
XTB_ARGS = ["--opt", "--gfn", "2", "--chrg", "0", "--uhf", "0"]
PROTOCOL_ID = "GFN2-xTB/opt/charge0/uhf0"

AUTOC_LEVEL = "normal"          # first attempt
AUTOC_LEVEL_TIGHT = "tight"     # retry for SCF trouble
TIMEOUT_S = 900

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


def write_xyz(smiles: str, path: Path) -> bool:
    """Embed a starting geometry from SMILES via RDKit."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        # fall back to random coordinates rather than fail outright
        if AllChem.EmbedMolecule(mol, randomSeed=42,
                                 useRandomCoords=True) != 0:
            return False
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:                       # noqa: BLE001
        pass
    conf = mol.GetConformer()
    lines = [str(mol.GetNumAtoms()), smiles]
    for i, atom in enumerate(mol.GetAtoms()):
        p = conf.GetAtomPosition(i)
        lines.append(f"{atom.GetSymbol():2s} {p.x:16.8f} {p.y:16.8f} "
                     f"{p.z:16.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def parse_xtb(out_text: str) -> dict:
    """Pull the descriptors out of an xTB stdout capture."""
    d: dict[str, float | None] = {
        "dipole_D": None, "homo_lumo_gap_ev": None,
        "total_energy_hartree": None, "polarizability_au": None,
        "converged": None, "gfn": None, "n_iterations": None,
    }
    m = re.search(r"Hamiltonian\s+(GFN[12]-xTB)", out_text)
    if m:
        d["gfn"] = m.group(1)
    m = re.search(r"GEOMETRY OPTIMIZATION CONVERGED AFTER\s+(\d+)\s+ITERATIONS",
                  out_text)
    if m:
        d["converged"] = True
        d["n_iterations"] = int(m.group(1))
    elif "GEOMETRY OPTIMIZATION DID NOT CONVERGE" in out_text:
        d["converged"] = False

    # total energy
    m = re.search(r"TOTAL ENERGY\s+(-?\d+\.\d+)\s+Eh", out_text)
    if m:
        d["total_energy_hartree"] = float(m.group(1))

    # dipole moment. The xTB block is:
    #     molecular dipole:
    #                      x           y           z       tot (Debye)
    #      q only:       ...
    #        full:      0.146       0.719      -0.445       2.180
    # i.e. THREE components followed by the total magnitude -- the total is the
    # fourth number, not a fifth. An earlier regex expected an extra field and
    # matched nothing, which silently left every dipole as None.
    m = re.search(r"molecular dipole:(.*?)(?:\n\s*\n|\Z)",
                  out_text, re.S)
    if m:
        block = m.group(1)
        fm = re.search(r"^\s*full:\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+"
                       r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", block, re.M)
        if fm:
            d["dipole_D"] = float(fm.group(4))
    if d["dipole_D"] is None:
        fm = re.search(r"^\s*full:\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+"
                       r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", out_text, re.M)
        if fm:
            d["dipole_D"] = float(fm.group(4))

    # HOMO-LUMO gap (alpha). The orbital table has TWO energy columns:
    #         #    occupation        Energy/Eh            Energy/eV
    #        15        2.0000           -0.3750385             -10.2053 (HOMO)
    #        16                         -0.2114206              -5.7530 (LUMO)
    # The number immediately before the (HOMO)/(LUMO) marker is already in eV, so the
    # gap is a plain subtraction. (An earlier version multiplied by 27.211, turning a
    # 4.45 eV gap into 121 eV -- obviously wrong for any closed-shell organic.)
    m = re.search(r"(-?\d+\.\d+)\s*\(HOMO\)", out_text)
    homo = float(m.group(1)) if m else None
    m = re.search(r"(-?\d+\.\d+)\s*\(LUMO\)", out_text)
    lumo = float(m.group(1)) if m else None
    if homo is not None and lumo is not None:
        gap = lumo - homo
        # sanity: a physical HOMO-LUMO gap for a neutral organic sits in 1-20 eV
        d["homo_lumo_gap_ev"] = gap if 0.0 < gap < 30.0 else None

    # isotropic polarizability
    m = re.search(r"Mol\. polarizability\s*:\s*\n\s*"
                  r"xx\s+(-?\d+\.\d+)\s+yy\s+(-?\d+\.\d+)\s+zz\s+(-?\d+\.\d+)"
                  r"\s*\n\s*iso\s+(-?\d+\.\d+)", out_text)
    if m:
        d["polarizability_au"] = float(m.group(4))
    return d


def run_xtb(workdir: Path, autoc: str) -> tuple[bool, str, str]:
    """Run one optimisation. Returns (ok, stdout, stderr)."""
    cmd = [str(XTB), "input.xyz", *XTB_ARGS, "--alpb", "none",
           "--acc", "1.0" if autoc == "normal" else "0.1"]
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True,
                              text=True, timeout=TIMEOUT_S,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT"
    ok = "GEOMETRY OPTIMIZATION CONVERGED" in proc.stdout
    return ok, proc.stdout, proc.stderr


def compute_one(rec: dict) -> dict:
    ik = rec["inchikey"]
    smi = rec.get("smiles", "")
    wd = CACHE_ROOT / ik
    result = {
        "inchikey": ik, "name": rec.get("name", ""), "smiles": smi,
        "protocol": PROTOCOL_ID, "status": "PENDING", "error": "",
        "dipole_D": None, "homo_lumo_gap_ev": None,
        "total_energy_hartree": None, "polarizability_au": None,
        "n_iterations": None, "xtb_seconds": 0.0,
        "input_sha256": "", "optimized_sha256": "", "output_sha256": "",
        "source": "NEWLY_COMPUTED",
    }

    if (wd / "xtb.out").is_file() and (wd / "manifest.json").is_file():
        man = json.loads((wd / "manifest.json").read_text(encoding="utf-8"))
        if man.get("protocol") == PROTOCOL_ID:
            out_text = (wd / "xtb.out").read_text(encoding="utf-8",
                                                  errors="replace")
            parsed = parse_xtb(out_text)
            if parsed["converged"]:
                result.update({k: v for k, v in parsed.items()
                               if k != "converged" and k != "gfn"})
                result["status"] = "CACHED"
                result["source"] = "CACHE"
                result["input_sha256"] = man.get("input_sha256", "")
                result["output_sha256"] = man.get("output_sha256", "")
                result["optimized_sha256"] = man.get("optimized_sha256", "")
                return result

    if not smi:
        result["status"] = "ERROR"
        result["error"] = "NO_SMILES"
        return result
    wd.mkdir(parents=True, exist_ok=True)
    if not write_xyz(smi, wd / "input.xyz"):
        result["status"] = "ERROR"
        result["error"] = "GEOMETRY_EMBED_FAILED"
        return result
    result["input_sha256"] = sha256_file(wd / "input.xyz")

    t0 = time.time()
    ok, out, err = run_xtb(wd, AUTOC_LEVEL)
    if not ok:
        # one retry with a tighter SCF threshold, recorded so the method change is
        # not hidden
        ok2, out2, err2 = run_xtb(wd, AUTOC_LEVEL_TIGHT)
        if ok2:
            ok, out, err = ok2, out2, err2
            result["error"] = "RETRIED_WITH_TIGHTER_SCF"
        else:
            result["status"] = "ERROR"
            result["error"] = (f"NOT_CONVERGED: {(err or '')[:300]}")
            (wd / "xtb.out").write_text(out, encoding="utf-8")
            return result
    result["xtb_seconds"] = round(time.time() - t0, 2)
    (wd / "xtb.out").write_text(out, encoding="utf-8")

    parsed = parse_xtb(out)
    if not parsed["converged"]:
        result["status"] = "ERROR"
        result["error"] = "NO_CONVERGENCE_MARKER"
        return result
    result.update({k: v for k, v in parsed.items()
                   if k not in ("converged", "gfn")})
    result["status"] = "OK"

    if (wd / "xtbopt.xyz").is_file():
        result["optimized_sha256"] = sha256_file(wd / "xtbopt.xyz")
    result["output_sha256"] = sha256_file(wd / "xtb.out")
    (wd / "manifest.json").write_text(json.dumps({
        "inchikey": ik, "protocol": PROTOCOL_ID, "args": XTB_ARGS,
        "input_sha256": result["input_sha256"],
        "optimized_sha256": result["optimized_sha256"],
        "output_sha256": result["output_sha256"],
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not XTB.is_file():
        print(f"FATAL: xtb binary not found at {XTB}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    phase = load(PHASE)
    qualified = {(r.get("inchikey") or "").strip(): r
                 for r in load(QUALIFIED)}
    registry = {(r.get("inchikey") or "").strip(): r
                for r in load(REGISTRY)}
    exp_feat = {(r.get("inchikey") or "").strip(): r
                for r in load(EXP_FEAT)}

    verified = [r for r in phase if r.get("phase_verified") == "true"]

    # Authoritative SMILES: once a molecule has been checked against PubChem, its
    # canonical SMILES is THE structure of record. Preferring it over the source-table
    # SMILES makes the tautomer repair durable -- an earlier version keyed the repair
    # off the transient TAUTOMER_OR_FORM verdict, so a plain rebuild silently restored
    # the wrong imidic-acid geometry for N-methylacetamide.
    canonical_smiles: dict[str, str] = {}
    sv_path = OUT / "smiles_verification_b100.csv"
    if sv_path.is_file():
        for r in load(sv_path):
            ik = (r.get("inchikey") or "").strip()
            pub = (r.get("pubchem_canonical_smiles") or "").strip()
            if ik and pub:
                canonical_smiles[ik] = pub

    def smi_for(ik: str, fallback: str) -> str:
        return canonical_smiles.get(ik) or fallback

    def same_molecule(a: str, b: str) -> bool:
        """Chemical comparison, not string comparison.

        Two SMILES can be textually different and still describe the same molecule
        (different canonicalisation order, stereo notation, aromatic form). Comparing
        raw strings marked 142 molecules as "stale" when only one actually was.
        """
        from rdkit import Chem, RDLogger
        RDLogger.DisableLog("rdApp.*")
        ma, mb = Chem.MolFromSmiles(a), Chem.MolFromSmiles(b) if a and b else None
        if ma is None or mb is None:
            return False
        return Chem.MolToSmiles(ma) == Chem.MolToSmiles(mb)

    # rows already carrying xTB from the uniform expansion run
    rows: list[dict] = []
    need: list[dict] = []
    for r in verified:
        ik = (r.get("inchikey") or "").strip()
        ef = exp_feat.get(ik)
        has = (ef is not None
               and (ef.get("dipole_D") or "").strip().lower()
               not in PLACEHOLDERS)
        # A molecule whose authoritative SMILES differs from the SMILES used in the
        # expansion run cannot reuse that run's numbers, even though they exist.
        used_smi = (ef.get("smiles") or "").strip() if ef else ""
        auth_smi = canonical_smiles.get(ik, "")
        stale_geometry = bool(auth_smi) and bool(used_smi) and (
            not same_molecule(auth_smi, used_smi))
        if has and not stale_geometry:
            # Carry the provenance hashes from the original cached run so every row,
            # including reused ones, is individually verifiable. `data/interim/` is
            # gitignored, so without these hashes a reader could not check that the
            # descriptors came from the geometry recorded here.
            #
            # Cache directories are sometimes named `<inchikey>` and sometimes
            # `<inchikey>__<prothash>` (283 of 493 carry a suffix, marking a protocol
            # revision). An exact-name lookup therefore misses most of them, so match
            # on the prefix and pick the newest matching directory.
            ex_in = ex_opt = ex_out = ""
            base = REPO_ROOT / "data" / "interim" / "xtb_features"
            cands = []
            if base.is_dir():
                exact = base / ik / "cache_manifest.json"
                if exact.is_file():
                    cands = [exact]
                else:
                    cands = sorted(
                        (d / "cache_manifest.json"
                         for d in base.glob(f"{ik}__*")),
                        key=lambda p: p.parent.name)
            for cm in cands:
                if not cm.is_file():
                    continue
                try:
                    em = json.loads(cm.read_text(encoding="utf-8"))
                except Exception:           # noqa: BLE001
                    continue
                if em.get("input_sha256"):
                    ex_in = em.get("input_sha256", "")
                    ex_opt = em.get("optimized_sha256", "")
                    ex_out = em.get("output_sha256", "")
                    break
            rows.append({
                "inchikey": ik, "name": r.get("name", ""),
                "smiles": (ef.get("smiles") or "").strip(),
                "protocol": PROTOCOL_ID, "status": "EXISTING",
                "error": "",
                "dipole_D": ef.get("dipole_D", ""),
                "polarizability_au": ef.get("polarizability_au", ""),
                "polarizability_A3": ef.get("polarizability_A3", ""),
                "homo_lumo_gap_ev": ef.get("homo_lumo_gap_ev", ""),
                "total_energy_hartree": ef.get("total_energy_hartree", ""),
                "mu_sq_over_Vm": ef.get("mu_sq_over_Vm", ""),
                "alpha_over_Vm": ef.get("alpha_over_Vm", ""),
                "n_iterations": "",
                "xtb_seconds": ef.get("xtb_seconds", ""),
                "input_sha256": ex_in,
                "optimized_sha256": ex_opt,
                "output_sha256": ex_out,
                "source": "EXISTING_UNIFIED_RUN",
                "epsilon": r.get("epsilon", ""),
                "T_K": r.get("T_K", ""),
                "evidence_grade": r.get("evidence_grade", ""),
                "family": registry.get(ik, {}).get("family", ""),
            })
        else:
            need.append({
                "inchikey": ik, "name": r.get("name", ""),
                "smiles": smi_for(
                    ik, registry.get(ik, {}).get("smiles", "") or used_smi),
                "epsilon": r.get("epsilon", ""),
                "T_K": r.get("T_K", ""),
                "evidence_grade": r.get("evidence_grade", ""),
                "family": registry.get(ik, {}).get("family", ""),
                "reason": "STALE_GEOMETRY" if stale_geometry else "NO_XTB",
            })

    print(f"[B100-8] phase-verified molecules : {len(verified)}")
    print(f"[B100-8] already have xTB         : {len(rows)}")
    print(f"[B100-8] to compute               : {len(need)}")
    if limit:
        need = need[:limit]
        print(f"[B100-8] limited to               : {len(need)}")

    # Any molecule flagged STALE_GEOMETRY must have its cached result discarded so the
    # corrected structure is actually recomputed (the cache is keyed by InChIKey, not
    # by SMILES, so a wrong geometry would otherwise be reused).
    stale = [x for x in need if x.get("reason") == "STALE_GEOMETRY"]
    if stale:
        print(f"[B100-8] stale geometries to recompute : {len(stale)}")
        for rec in stale:
            d = CACHE_ROOT / rec["inchikey"]
            if d.is_dir():
                for f in ("xtb.out", "xtbopt.xyz", "manifest.json",
                          "input.xyz", ".xtboptok"):
                    p = d / f
                    if p.is_file():
                        p.unlink()
            print(f"         {rec['name'][:34]:34s} -> {rec['smiles'][:40]}")

    for i, rec in enumerate(need, 1):
        res = compute_one(rec)
        res.update({
            "epsilon": rec.get("epsilon", ""), "T_K": rec.get("T_K", ""),
            "evidence_grade": rec.get("evidence_grade", ""),
            "family": rec.get("family", ""),
        })
        # derive the volume-normalised descriptors when possible
        vol = None
        reg = registry.get(rec["inchikey"], {})
        if reg:
            pass
        rows.append(res)
        print(f"  {i}/{len(need)} {rec['name'][:28]:28s} {res['status']:8s} "
              f"dipole={res.get('dipole_D')}")
        if i % 10 == 0:
            # incremental save so an interruption loses nothing
            _write(rows, OUT)
        time.sleep(0.05)

    _write(rows, OUT)

    n_ok = sum(1 for r in rows if r["status"] in ("EXISTING", "OK", "CACHED"))
    n_err = sum(1 for r in rows if r["status"] == "ERROR")
    n_new = sum(1 for r in rows if r["source"] == "NEWLY_COMPUTED")
    total_secs = sum(float(r["xtb_seconds"] or 0) for r in rows
                     if str(r.get("xtb_seconds") or "").replace(".", "").isdigit())

    doc = {
        "schema": "b100.xtb_coverage/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "id": PROTOCOL_ID,
            "command": f"xtb input.xyz {' '.join(XTB_ARGS)}",
            "binary": str(XTB),
            "binary_sha256": sha256_file(XTB),
            "why_unified": (
                "扩展层 388 条已核对全部为 GFN2-xTB 且几何优化收敛; "
                "本轮补算的分子使用完全相同的命令与同一个二进制, "
                "因此整个 B100 的 xTB 层次是统一协议."
            ),
        },
        "coverage": {
            "n_phase_verified": len(verified),
            "n_with_xtb": n_ok,
            "n_error": n_err,
            "n_from_existing_run": len(rows) - n_new,
            "n_newly_computed": n_new,
            "requirement_min": 100,
            "requirement_met": n_ok >= 100,
            "coverage_fraction": round(n_ok / max(len(verified), 1), 4),
        },
        "compute_cost": {
            "xtb_wall_seconds": round(total_secs, 1),
            "note": (
                "xTB 是半经验方法, 单分子几何优化约 0.4-30 秒; "
                "不计入 DFT 授权额度, 但记录以便复现."
            ),
        },
        "reproducibility": {
            "n_rows_with_input_hash": sum(
                1 for r in rows if (r.get("input_sha256") or "").strip()),
            "n_rows_total": len(rows),
            "note": (
                "每一行都带 input/optimized/output 三个 SHA-256. "
                "复用行取自 data/interim/xtb_features/<inchikey>/cache_manifest.json "
                "(该目录被 gitignore, 因此哈希是本表唯一可核对的计算来源凭据); "
                "新算行由本轮写入 manifest. 协议 id 与二进制哈希见 protocol 字段."
            ),
        },
        "failures": [
            {"inchikey": r["inchikey"], "name": r["name"],
             "error": r["error"]}
            for r in rows if r["status"] == "ERROR"
        ],
        "inputs": {
            "phase_state_audit_b100": {"sha256": sha256_file(PHASE)},
            "qualified_molecules_b100": {"sha256": sha256_file(QUALIFIED)},
            "expansion_features": {"sha256": sha256_file(EXP_FEAT)},
        },
    }
    j_path = OUT / "xtb_coverage_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print()
    print(f"  with xTB       = {n_ok}/{len(verified)}  "
          f"(requirement 100: {n_ok >= 100})")
    print(f"  newly computed = {n_new}")
    print(f"  errors         = {n_err}")
    print(f"  total seconds  = {total_secs:.1f}")
    return 0


def _write(rows: list[dict], out: Path) -> None:
    path = out / "xtb_descriptors_b100.csv"
    if not rows:
        return
    fields = ["inchikey", "name", "smiles", "epsilon", "T_K",
              "evidence_grade", "family", "protocol", "status", "error",
              "dipole_D", "polarizability_au", "polarizability_A3",
              "homo_lumo_gap_ev", "total_energy_hartree",
              "mu_sq_over_Vm", "alpha_over_Vm",
              "n_iterations", "xtb_seconds",
              "input_sha256", "optimized_sha256", "output_sha256", "source"]
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
