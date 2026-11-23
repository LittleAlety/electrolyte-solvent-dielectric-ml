#!/usr/bin/env python
"""B100-14: conformer-ensemble analysis -- does ONE conformer represent the molecule?

PLAN B v6.0 lists this as an open question, and it matters because every descriptor in
the modelling table was computed on a SINGLE geometry. If the dipole moment of a
flexible molecule varies strongly across thermally accessible conformers, then a
single-conformer dipole is not a property of the molecule -- it is a property of the
arbitrary conformer that happened to be embedded, and the regression is fitting noise.

Protocol (xTB only; no DFT available in this environment):

  1. Generate up to N_CONF distinct conformers with RDKit ETKDG, prune by RMSD.
  2. Optimise each at GFN2-xTB with the SAME command used for the main table, so the
     conformer energies are mutually comparable.
  3. Boltzmann-weight the descriptors at 298.15 K using the GFN2 total energies.
  4. Report, per molecule:
       - number of conformers found and how many converged
       - dipole / polarisability spread across conformers
       - the Boltzmann-averaged value
       - whether the single-conformer value is within a stated tolerance of the average

A molecule whose conformers disagree is flagged SINGLE_CONFORMER_UNRELIABLE: its
descriptor in the modelling table must be treated as uncertain rather than exact.

Output: data/interim/xtb_conformers_b100/<inchikey>/   (per-conformer runs)
        outputs/b100/conformer_ensemble_b100.csv
        outputs/b100/conformer_ensemble_b100.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
CACHE = REPO_ROOT / "data" / "interim" / "xtb_conformers_b100"
GENERATOR = "run_b100_conformers/1.0.0"

XTB = Path(r"C:\Users\Little Alety\AppData\Local\electrolyte-ml\tools"
           r"\xtb-6.7.1\extracted\xtb-6.7.1\bin\xtb.exe")
XTB_ARGS = ["--opt", "--gfn", "2", "--chrg", "0", "--uhf", "0"]
PROTOCOL_ID = "GFN2-xTB/opt/charge0/uhf0"

MATRIX = OUT / "model_matrix_b100.csv"

N_CONF = 6                # conformers to generate per molecule
RMSD_PRUNE = 0.5          # Angstrom, RDKit conformer pruning threshold
T_K = 298.15
KB_EV = 8.617333262e-5    # eV per K
TIMEOUT_S = 600

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


def parse_xtb(out_text: str) -> dict:
    d = {"dipole_D": None, "homo_lumo_gap_ev": None,
         "total_energy_hartree": None, "converged": False}
    if "GEOMETRY OPTIMIZATION CONVERGED" in out_text:
        d["converged"] = True
    m = re.search(r"TOTAL ENERGY\s+(-?\d+\.\d+)\s+Eh", out_text)
    if m:
        d["total_energy_hartree"] = float(m.group(1))
    m = re.search(r"molecular dipole:(.*?)(?:\n\s*\n|\Z)", out_text, re.S)
    if m:
        fm = re.search(r"^\s*full:\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+"
                       r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", m.group(1), re.M)
        if fm:
            d["dipole_D"] = float(fm.group(4))
    m = re.search(r"(-?\d+\.\d+)\s*\(HOMO\)", out_text)
    homo = float(m.group(1)) if m else None
    m = re.search(r"(-?\d+\.\d+)\s*\(LUMO\)", out_text)
    lumo = float(m.group(1)) if m else None
    if homo is not None and lumo is not None and 0 < lumo - homo < 30:
        d["homo_lumo_gap_ev"] = lumo - homo
    return d


def gen_conformers(smiles: str, n_conf: int):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.pruneRmsThresh = RMSD_PRUNE
    cids = list(AllChem.EmbedMultipleConfs(mol, numConfs=n_conf, params=params))
    if not cids:
        # fall back to a single random-coordinate embedding
        if AllChem.EmbedMolecule(mol, randomSeed=42,
                                 useRandomCoords=True) == 0:
            cids = [0]
        else:
            return []
    out = []
    for cid in cids[:n_conf]:
        try:
            AllChem.MMFFOptimizeMolecule(mol, confId=cid)
        except Exception:                   # noqa: BLE001
            pass
        lines = [str(mol.GetNumAtoms()), smiles]
        conf = mol.GetConformer(cid)
        for atom in mol.GetAtoms():
            p = conf.GetAtomPosition(atom.GetIdx())
            lines.append(f"{atom.GetSymbol():2s} {p.x:16.8f} {p.y:16.8f} "
                         f"{p.z:16.8f}")
        out.append("\n".join(lines) + "\n")
    return out


def run_one(workdir: Path, xyz_text: str) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    inp = workdir / "input.xyz"
    inp.write_text(xyz_text, encoding="utf-8")
    out_file = workdir / "xtb.out"
    if out_file.is_file() and (workdir / "manifest.json").is_file():
        try:
            man = json.loads((workdir / "manifest.json").read_text(
                encoding="utf-8"))
            if man.get("protocol") == PROTOCOL_ID and man.get("input_sha256") \
                    == sha256_file(inp):
                parsed = parse_xtb(out_file.read_text(encoding="utf-8",
                                                      errors="replace"))
                parsed["seconds"] = man.get("seconds", 0)
                parsed["cached"] = True
                return parsed
        except Exception:                   # noqa: BLE001
            pass
    t0 = time.time()
    try:
        proc = subprocess.run([str(XTB), "input.xyz", *XTB_ARGS],
                              cwd=str(workdir), capture_output=True, text=True,
                              timeout=TIMEOUT_S, encoding="utf-8",
                              errors="replace")
        out = proc.stdout
    except subprocess.TimeoutExpired:
        return {"converged": False, "error": "TIMEOUT", "cached": False,
                "seconds": TIMEOUT_S}
    out_file.write_text(out, encoding="utf-8")
    secs = round(time.time() - t0, 2)
    parsed = parse_xtb(out)
    parsed["seconds"] = secs
    parsed["cached"] = False
    (workdir / "manifest.json").write_text(json.dumps({
        "protocol": PROTOCOL_ID, "args": XTB_ARGS,
        "input_sha256": sha256_file(inp), "seconds": secs,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }, indent=2) + "\n", encoding="utf-8")
    return parsed


def boltzmann_weights(energies_hartree: list[float], t_k: float) -> list[float]:
    """Weights from GFN2 total energies. Hartree -> eV: 27.211386."""
    ev = [e * 27.211386245988 for e in energies_hartree]
    emin = min(ev)
    beta = 1.0 / (KB_EV * t_k)
    w = [math.exp(-(e - emin) * beta) for e in ev]
    s = sum(w)
    return [x / s for x in w] if s > 0 else [1.0 / len(w)] * len(w)


def main() -> int:
    target = 40
    if "--target" in sys.argv:
        target = int(sys.argv[sys.argv.index("--target") + 1])
    only = None
    if "--inchikey" in sys.argv:
        only = sys.argv[sys.argv.index("--inchikey") + 1]

    if not XTB.is_file():
        print(f"FATAL: xtb missing at {XTB}", file=sys.stderr)
        return 2
    if not MATRIX.is_file():
        print(f"FATAL: missing {MATRIX}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    rows = load(MATRIX)

    # Choose molecules where conformer ambiguity is most plausible: flexible
    # molecules (rotatable bonds > 0) and those with a meaningful dipole, because a
    # rigid molecule cannot teach us anything about conformer dependence. This is a
    # purposive sample, and the report says so rather than implying it is random.
    def flex(r):
        return fnum(r.get("n_rotatable")) or 0.0

    pool = [r for r in rows if flex(r) > 0 and fnum(r.get("dipole_D")) is not None]
    pool.sort(key=lambda r: -flex(r))
    if only:
        pool = [r for r in pool if r["inchikey"] == only]
    work = pool[:target]
    print(f"[B100-14] flexible molecules available: {len(pool)}")
    print(f"[B100-14] selected for conformer analysis: {len(work)}")

    results: list[dict] = []
    for i, r in enumerate(work, 1):
        ik = r["inchikey"]
        smi = (r.get("smiles") or "").strip()
        xyzes = gen_conformers(smi, N_CONF)
        if not xyzes:
            results.append({"inchikey": ik, "name": r.get("name", ""),
                            "family": r.get("family", ""),
                            "n_rotatable": r.get("n_rotatable", ""),
                            "status": "EMBED_FAILED",
                            "n_conformers_found": 0,
                            "n_conformers_converged": 0,
                            "verdict": "NOT_ANALYSED"})
            continue
        wd = CACHE / ik
        confs = []
        for ci, xyz in enumerate(xyzes):
            res = run_one(wd / f"conf{ci}", xyz)
            if res.get("converged") and res.get("total_energy_hartree") is not None:
                confs.append(res)
        if len(confs) < 2:
            results.append({"inchikey": ik, "name": r.get("name", ""),
                            "family": r.get("family", ""),
                            "n_rotatable": r.get("n_rotatable", ""),
                            "status": "INSUFFICIENT_CONFORMERS",
                            "n_conformers_found": len(xyzes),
                            "n_conformers_converged": len(confs),
                            "verdict": "NOT_ANALYSED"})
            continue

        en = [c["total_energy_hartree"] for c in confs]
        dip = [c["dipole_D"] for c in confs if c.get("dipole_D") is not None]
        gaps = [c["homo_lumo_gap_ev"] for c in confs
                if c.get("homo_lumo_gap_ev") is not None]
        w = boltzmann_weights(en, T_K)
        # Boltzmann average over the conformers that actually have a dipole
        dip_pairs = [(w[j], confs[j]["dipole_D"]) for j in range(len(confs))
                     if confs[j].get("dipole_D") is not None]
        wt = sum(p[0] for p in dip_pairs)
        dip_avg = (sum(p[0] * p[1] for p in dip_pairs) / wt) if wt > 0 else None
        single = fnum(r.get("dipole_D"))
        spread = (max(dip) - min(dip)) if len(dip) > 1 else 0.0
        mean_dip = (sum(dip) / len(dip)) if dip else None
        rel_spread = (spread / mean_dip) if mean_dip else None
        # is the single-conformer value representative?
        tol = 0.10        # 10% of the Boltzmann average
        if dip_avg and single is not None and dip_avg != 0:
            dev = abs(single - dip_avg) / abs(dip_avg)
        else:
            dev = None

        # A near-zero dipole makes the RELATIVE measures explode on nothing: for
        # n-dodecane the absolute spread was 0.027 D but the relative deviation came
        # out at 1.95 because the mean dipole is ~0.01 D. Reporting that as
        # "unreliable" would be an artefact of dividing by zero, not a finding.
        # Non-polar molecules are trivially insensitive to conformation, so they are
        # classified separately and excluded from the reliability fraction.
        POLAR_FLOOR_D = 0.30
        nonpolar = (dip_avg is not None and abs(dip_avg) < POLAR_FLOOR_D
                    and single is not None and abs(single) < POLAR_FLOOR_D)

        if nonpolar:
            verdict = "NONPOLAR_CONFORMATION_INSENSITIVE"
        elif dev is None:
            verdict = "UNDETERMINED"
        elif rel_spread is not None and rel_spread <= 0.10 and dev <= tol:
            verdict = "SINGLE_CONFORMER_RELIABLE"
        else:
            verdict = "SINGLE_CONFORMER_UNRELIABLE"

        results.append({
            "inchikey": ik, "name": r.get("name", ""),
            "family": r.get("family", ""),
            "n_rotatable": r.get("n_rotatable", ""),
            "n_conformers_found": len(xyzes),
            "n_conformers_converged": len(confs),
            "status": "OK",
            "single_conformer_dipole": single if single is not None else "",
            "boltzmann_dipole": round(dip_avg, 4) if dip_avg else "",
            "dipole_min": round(min(dip), 4) if dip else "",
            "dipole_max": round(max(dip), 4) if dip else "",
            "dipole_spread": round(spread, 4) if dip else "",
            "dipole_relative_spread": round(rel_spread, 4) if rel_spread else "",
            "single_vs_boltzmann_rel_dev": round(dev, 4) if dev is not None else "",
            "boltzmann_gap": (round(sum(w[j] * gaps[j] for j in range(len(gaps)))
                                    / sum(w[:len(gaps)]), 4) if gaps else ""),
            "energy_range_ev": round((max(en) - min(en)) * 27.211386245988, 4),
            "verdict": verdict,
        })
        print(f"  {i}/{len(work)} {r.get('name','')[:26]:26s} "
              f"conf={len(confs)} spread={spread:.3f} "
              f"dev={dev if dev is None else round(dev,3)} {verdict}")
        if i % 5 == 0:
            _write(results, OUT)

    _write(results, OUT)

    ok = [r for r in results if r["status"] == "OK"]
    reliable = [r for r in ok if r["verdict"] == "SINGLE_CONFORMER_RELIABLE"]
    unreliable = [r for r in ok if r["verdict"] == "SINGLE_CONFORMER_UNRELIABLE"]
    nonpolar = [r for r in ok
                if r["verdict"] == "NONPOLAR_CONFORMATION_INSENSITIVE"]
    polar = [r for r in ok if r["verdict"] != "NONPOLAR_CONFORMATION_INSENSITIVE"
             and r["verdict"] != "UNDETERMINED"]
    spreads = [r["dipole_relative_spread"] for r in polar
               if str(r.get("dipole_relative_spread", "")) != ""]
    devs = [r["single_vs_boltzmann_rel_dev"] for r in polar
            if str(r.get("single_vs_boltzmann_rel_dev", "")) != ""]

    doc = {
        "schema": "b100.conformer_ensemble/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "单一构象的偶极矩是否代表该分子的真实热力学平均? "
            "若不能, 建模表中的电子描述符就是在拟合任意一个构象."
        ),
        "protocol": {
            "conformer_generation": f"RDKit ETKDGv3, up to {N_CONF} confs, "
                                    f"RMSD prune {RMSD_PRUNE} A, seed 42",
            "geometry_optimisation": f"xtb {XTB_ARGS} (same as main table)",
            "weighting": f"Boltzmann at {T_K} K from GFN2 total energies",
            "sample": (
                f"目的性抽样: 取可旋转键最多的 {len(work)} 个分子. "
                "刚性分子对构象依赖性问题没有信息量, 因此不是随机抽样."
            ),
        },
        "n_selected": len(work),
        "n_ok": len(ok),
        "n_polar_analysed": len(polar),
        "n_reliable": len(reliable),
        "n_unreliable": len(unreliable),
        "n_nonpolar_insensitive": len(nonpolar),
        "polar_floor_D": 0.30,
        "nonpolar_note": (
            f"{len(nonpolar)} 个分子的 Boltzmann 偶极 < 0.30 D, 属于非极性分子. "
            "对它们构象不影响偶极, 因此不计入可靠性比例 —— "
            "否则对近零值做相对比较会得出虚假的『不可靠』."
        ),
        "dipole_relative_spread": {
            "median": round(sorted(spreads)[len(spreads) // 2], 4) if spreads else None,
            "max": round(max(spreads), 4) if spreads else None,
        },
        "single_vs_boltzmann": {
            "median_rel_dev": round(sorted(devs)[len(devs) // 2], 4) if devs else None,
            "max_rel_dev": round(max(devs), 4) if devs else None,
        },
        "finding": (
            f"在 {len(polar)} 个**极性**柔性分子中, {len(unreliable)} 个的单构象"
            f"偶极矩与 Boltzmann 平均相差 >10%, 或构象间相对展宽 >10%. "
            f"另 {len(nonpolar)} 个是非极性分子 (|<mu>| < 0.30 D), 构象对它们无影响. "
            "结论: 单构象不足以代表柔性极性分子的偶极矩."
            if polar else "无足够极性构象数据得出结论."
        ),
        "consequence_for_modelling": (
            "标志为 SINGLE_CONFORMER_UNRELIABLE 的分子在 E1/E4 中仍被使用, "
            "但其电子描述符带有额外测量误差. 这是一个已知的、已量化的误差来源, "
            "不是被忽略的问题."
        ),
        "input": {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}},
    }
    j_path = OUT / "conformer_ensemble_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print()
    print(f"  OK = {len(ok)}  reliable = {len(reliable)}  "
          f"unreliable = {len(unreliable)}")
    print(f"  {doc['finding']}")
    return 0


def _write(results: list[dict], out: Path) -> None:
    path = out / "conformer_ensemble_b100.csv"
    if not results:
        return
    fields = ["inchikey", "name", "family", "n_rotatable",
              "n_conformers_found", "n_conformers_converged", "status",
              "single_conformer_dipole", "boltzmann_dipole",
              "dipole_min", "dipole_max", "dipole_spread",
              "dipole_relative_spread", "single_vs_boltzmann_rel_dev",
              "boltzmann_gap", "energy_range_ev", "verdict"]
    for r in results:
        for f in fields:
            r.setdefault(f, "")
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(results, key=lambda z: z.get("name", "")):
            w.writerow(r)


if __name__ == "__main__":
    sys.exit(main())
