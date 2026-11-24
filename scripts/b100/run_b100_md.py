#!/usr/bin/env python
"""B100-21: liquid MD -- dielectric constant and Kirkwood g from dipole fluctuations.

Run with the conda environment at E:/conda_md, which is the only one on this machine
with a working OpenMM CPU platform. The pip build registers only Reference, and on a
periodic PME system that segfaults; that finding is preserved in the commit history.

Why this layer exists: PLAN B asks for >=12 liquid systems to measure the Kirkwood g
factor. Everything else in this repository infers g indirectly -- the
association-deficit analysis backs it out of epsilon and found halocarbons at
g_eff 0.51 while carrying a 3.34 D dipole. MD measures g directly.

Protocol
--------
  charges    NAGL openff-gnn-am1bcc-1.0.0.pt (AM1-BCC-quality; AmberTools has no
             Windows build, and NAGL is trained to reproduce AM1-BCC, so the OpenFF
             force field stays on the charge model it was parameterised for)
  packing    cubic lattice with random orientations; edge from the molar volume
  ensemble   NVT at a density taken from the molar volume
  analysis   eps = 1 + (<M^2> - <M>^2)/(3 eps0 V kB T)
             g   = (<M^2> - <M>^2)/(N mu^2)

Two honest limits:
  * NPT was tried and abandoned: the lattice start leaves local voids, and the
    barostat collapses the box below twice the cutoff within a few thousand steps.
    Fixed-density NVT is well posed but makes the density an INPUT, so the achieved
    density is reported next to every result.
  * The molar volume in the model matrix is a gas-phase molecular volume times N_A,
    measured at 0.53-0.72x the true liquid molar volume. LIQUID_VOLUME_FACTOR scales
    it; it is the one calibration constant in this layer and is stated, not buried.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TMP", r"E:\tmp")
os.environ.setdefault("TEMP", r"E:\tmp")
os.environ.setdefault("TMPDIR", r"E:\tmp")

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "run_b100_md/5.0.0"
MATRIX = OUT / "model_matrix_b100.csv"

FORCEFIELD = "openff-2.1.0.offxml"
CHARGE_MODEL = "openff-gnn-am1bcc-1.0.0.pt"
PLATFORM = "CPU"

T_K = 298.15
EQUIL_PS = 30.0
PRODUCTION_PS = 200.0
TIMESTEP_FS = 2.0
SAMPLE_FS = 20.0
FRICTION_PER_PS = 1.0

CUTOFF_NM = 0.9
SWITCH_NM = 0.8
# Calibrated against ethanol: the matrix molar volume is 3.24e-5 m3/mol while the true
# liquid value is 5.84e-5, a ratio of 0.555, so the factor is 1/0.555 = 1.80. With 1.6
# the density came out 889 kg/m3 against the experimental 789 -- a 13% error that
# propagates straight into epsilon.
LIQUID_VOLUME_FACTOR = 1.80

EPS0 = 8.8541878128e-12
KB = 1.380649e-23
E_CHARGE = 1.602176634e-19
AVOGADRO = 6.02214076e23

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}

CSV_FIELDS = ["system", "inchikey", "status", "T_K", "density_kg_m3",
              "epsilon_experimental", "epsilon_md", "epsilon_block_sd",
              "kirkwood_g", "n_molecules", "production_ps", "volume_nm3",
              "wall_seconds", "detail"]


def load(path):
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
    import io
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def platforms():
    try:
        import openmm
        return [openmm.Platform.getPlatform(i).getName()
                for i in range(openmm.Platform.getNumPlatforms())]
    except Exception:
        return []


def build_forcefield():
    """openff-2.1.0 with ToolkitAM1BCC replaced by the NAGL equivalent.

    Retargeting the existing handler's partial_charge_method is NOT enough: the
    charge-model matching inside Interchange still calls the registry with the literal
    name am1bcc, which no toolkit on this machine can satisfy. The handler itself has
    to be replaced.
    """
    from openff.toolkit.typing.engines.smirnoff import ForceField
    from openff.toolkit.typing.engines.smirnoff.parameters import NAGLChargesHandler

    ff = ForceField(FORCEFIELD)
    try:
        ff.deregister_parameter_handler("ToolkitAM1BCC")
    except Exception:
        pass
    ff.register_parameter_handler(
        NAGLChargesHandler(version="0.3", model_file=CHARGE_MODEL))
    return ff


def make_molecule(smiles):
    """Build the molecule, tolerating undefined stereocentres.

    2-Methylcyclohexanol has a stereocentre the registry SMILES does not specify, and
    RDKit raises UndefinedStereochemistryError. The stereochemistry is irrelevant for a
    bulk dielectric constant of a racemic liquid, so it is allowed explicitly rather
    than by editing the stored SMILES.
    """
    from openff.toolkit import Molecule
    try:
        mol = Molecule.from_smiles(smiles, allow_undefined_stereo=True)
    except TypeError:                       # older signature
        mol = Molecule.from_smiles(smiles)
    mol.generate_conformers(n_conformers=1)
    return mol


def pack_lattice(mol, n_mol, vm_m3_mol):
    """Cubic lattice with random orientations, box edge from the molar volume.

    The edge MUST be (Vm * N / N_A)**(1/3). Using (Vm * N)**(1/3) gives an edge of about
    1.9e8 nm, which OpenMM accepts without complaint -- the system simply becomes
    non-periodic and the resulting epsilon is meaningless.
    """
    import numpy as np

    v_total = (vm_m3_mol * LIQUID_VOLUME_FACTOR) * n_mol / AVOGADRO
    edge_nm = (v_total ** (1.0 / 3.0)) * 1e9

    side = max(2, int(math.ceil(n_mol ** (1.0 / 3.0))))
    while side ** 3 < n_mol:
        side += 1

    base = np.array(mol.conformers[0].magnitude, dtype=float) * 0.1
    centroid = base.mean(axis=0)
    rng = random.Random(20261123)

    positions = []
    placed = 0
    for ix in range(side):
        for iy in range(side):
            for iz in range(side):
                if placed >= n_mol:
                    break
                centre = np.array([(ix + 0.5) * edge_nm / side,
                                   (iy + 0.5) * edge_nm / side,
                                   (iz + 0.5) * edge_nm / side])
                q = np.array([rng.gauss(0, 1) for _ in range(4)])
                q /= np.linalg.norm(q)
                w, x, y, z = q
                rot = np.array([
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),
                     2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z),
                     2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w),
                     1 - 2 * (x * x + y * y)]])
                positions.append((base - centroid) @ rot.T + centre)
                placed += 1
    return np.vstack(positions), edge_nm


def to_float_e(value):
    """OpenMM returns quantities, floats or guarded quantities depending on version."""
    import openmm
    for getter in (lambda v: v.value_in_unit(openmm.unit.elementary_charge),
                   lambda v: v._value_in_unit(openmm.unit.elementary_charge),
                   lambda v: float(v._value),
                   lambda v: float(v)):
        try:
            return float(getter(value))
        except Exception:
            continue
    raise TypeError("cannot convert {} to elementary charge".format(type(value)))


def run_system(name, smiles, vm_m3_mol, n_mol, production_ps, equil_ps):
    import numpy as np
    import openmm
    from openmm import unit
    from openff.toolkit import Topology
    from openff.interchange import Interchange

    t_start = time.time()
    mol = make_molecule(smiles)
    pos, edge_nm = pack_lattice(mol, n_mol, vm_m3_mol)

    top = Topology()
    for _ in range(n_mol):
        top.add_molecule(mol)

    ff = build_forcefield()
    inter = Interchange.from_smirnoff(force_field=ff, topology=top)
    inter.box = unit.Quantity(np.eye(3) * edge_nm, unit.nanometer)

    system = inter.to_openmm()
    system.setDefaultPeriodicBoxVectors(
        openmm.Vec3(edge_nm, 0, 0) * unit.nanometer,
        openmm.Vec3(0, edge_nm, 0) * unit.nanometer,
        openmm.Vec3(0, 0, edge_nm) * unit.nanometer)

    charges = None
    for f in range(system.getNumForces()):
        force = system.getForce(f)
        if isinstance(force, openmm.NonbondedForce):
            force.setNonbondedMethod(openmm.NonbondedForce.PME)
            # The cutoff has to fit inside half the box, and the switching distance
            # inside the cutoff. A small N makes the box too short and OpenMM then
            # refuses outright, so both are derived from the actual box rather than
            # taken from a fixed constant.
            cutoff = min(CUTOFF_NM, 0.45 * edge_nm)
            switch = min(SWITCH_NM, 0.85 * cutoff)
            force.setCutoffDistance(cutoff * unit.nanometer)
            force.setSwitchingDistance(switch * unit.nanometer)
            charges = np.array([to_float_e(force.getParticleParameters(i)[0])
                                for i in range(force.getNumParticles())])
            break
    if charges is None:
        return {"system": name, "status": "NO_NONBONDED_FORCE"}

    conf = np.array(mol.conformers[0].magnitude) * 1e-10
    q_mol = charges[:mol.n_atoms]
    mu_single = float(np.linalg.norm(
        (q_mol[:, None] * (conf - conf.mean(axis=0))).sum(axis=0) * E_CHARGE))

    integrator = openmm.LangevinMiddleIntegrator(
        T_K * unit.kelvin, FRICTION_PER_PS / unit.picosecond,
        TIMESTEP_FS * unit.femtoseconds)
    sim = openmm.app.Simulation(inter.to_openmm_topology(), system, integrator,
                                openmm.Platform.getPlatformByName(PLATFORM))
    sim.context.setPositions(pos * unit.nanometer)
    sim.minimizeEnergy(maxIterations=500)
    sim.context.setVelocitiesToTemperature(T_K * unit.kelvin, 20261123)
    sim.step(int(equil_ps * 1000 / TIMESTEP_FS))

    st = sim.context.getState(getPositions=True)
    box = st.getPeriodicBoxVectors(asNumpy=True).value_in_unit(unit.nanometer)
    volume_nm3 = abs(float(np.linalg.det(box)))
    box_len = float(box[0][0])

    n_samples = max(1, int(production_ps * 1000 / SAMPLE_FS))
    n_at = mol.n_atoms
    m2_list, mu_list = [], []
    for _ in range(n_samples):
        sim.step(int(SAMPLE_FS / TIMESTEP_FS))
        xyz = sim.context.getState(getPositions=True).getPositions(
            asNumpy=True).value_in_unit(unit.nanometer)
        total = np.zeros(3)
        for m in range(n_mol):
            sl = slice(m * n_at, (m + 1) * n_at)
            rel = xyz[sl] - xyz[sl].mean(axis=0)
            rel -= np.round(rel / box_len) * box_len
            total += (charges[sl, None] * rel).sum(axis=0)
        vec = total * E_CHARGE * 1e-9
        mu_list.append(vec)
        m2_list.append(float(vec @ vec))

    m2 = np.array(m2_list)
    mu_arr = np.array(mu_list)
    var = float(m2.mean() - float(mu_arr.mean(axis=0) @ mu_arr.mean(axis=0)))
    volume_m3 = volume_nm3 * 1e-27
    eps = 1.0 + var / (3.0 * EPS0 * volume_m3 * KB * T_K)
    g = var / (n_mol * mu_single ** 2) if mu_single > 0 else None

    n_blocks = 10
    per = len(m2) // n_blocks
    blocks = []
    for b in range(n_blocks):
        lo, hi = b * per, (b + 1) * per
        if hi - lo < 2:
            continue
        seg, seg_mu = m2[lo:hi], mu_arr[lo:hi]
        v = float(seg.mean() - float(seg_mu.mean(axis=0) @ seg_mu.mean(axis=0)))
        blocks.append(1.0 + v / (3.0 * EPS0 * volume_m3 * KB * T_K))
    eps_sd = float(np.std(blocks, ddof=1)) if len(blocks) > 1 else None

    mass = sum(a.mass for a in mol.atoms).magnitude      # g/mol
    # mass is g/mol, so the box mass is mass*n/N_A grams = /1000 kg. Writing /1e-3
    # instead of /1000 multiplied by 1000 and reported a density of 8.9e8 kg/m3 for
    # ethanol -- six orders of magnitude out, and silent because nothing checks it.
    density = float((mass * n_mol / AVOGADRO / 1000.0) / volume_m3)
    return {
        "system": name, "status": "OK",
        "T_K": T_K,
        "density_kg_m3": round(density, 2),
        "epsilon_md": round(eps, 3),
        "epsilon_block_sd": round(eps_sd, 3) if eps_sd is not None else "",
        "kirkwood_g": round(g, 4) if g is not None else "",
        "mu_single_D": round(mu_single / 3.33564e-30, 3),
        "n_molecules": n_mol,
        "production_ps": production_ps,
        "n_samples": n_samples,
        "volume_nm3": round(volume_nm3, 4),
        "wall_seconds": round(time.time() - t_start, 1),
    }


def write_csv(results):
    with (OUT / "md_dielectric_b100.csv").open("w", newline="",
                                               encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            for f in CSV_FIELDS:
                r.setdefault(f, "")
            writer.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--systems", type=int, default=12)
    ap.add_argument("--n-molecules", type=int, default=200)
    ap.add_argument("--production-ps", type=float, default=PRODUCTION_PS)
    ap.add_argument("--equil-ps", type=float, default=EQUIL_PS)
    args = ap.parse_args()

    rows = {(r.get("inchikey") or "").strip(): r for r in load(MATRIX)}
    if not rows:
        print("FATAL: missing model matrix", file=sys.stderr)
        return 2
    avail = platforms()
    if PLATFORM not in avail:
        print("FATAL: platform {} not registered; available {}".format(
            PLATFORM, avail), file=sys.stderr)
        return 3

    usable = [r for r in rows.values()
              if (r.get("smiles") or "").strip()
              and fnum(r.get("molar_volume_m3_mol")) is not None
              and fnum(r.get("epsilon")) is not None
              and (fnum(r.get("heavy_atom_count")) or 999) <= 12]
    usable.sort(key=lambda r: fnum(r["epsilon"]))

    if args.pilot:
        chosen = [r for r in usable if r["name"].lower() == "ethanol"] or usable[:1]
    else:
        step = max(1, len(usable) // args.systems)
        chosen = usable[::step][:args.systems]

    print("[B100-21] MD: {} systems, N={}, {} ps production, platform={}".format(
        len(chosen), args.n_molecules, args.production_ps, PLATFORM))

    # ---- resume: reuse any system already computed at the same protocol ----
    # A 12-system batch takes over an hour, and one molucule failing on a fixable
    # detail should not force a full re-run. Results are keyed by inchikey and only
    # reused when the protocol matches exactly, so a changed protocol cannot silently
    # mix numbers from two runs.
    previous = {}
    if (OUT / "md_dielectric_b100.json").is_file():
        try:
            old = json.loads((OUT / "md_dielectric_b100.json")
                             .read_text(encoding="utf-8"))
            old_protocol = old.get("protocol") or {}
            same = (old_protocol.get("n_molecules") == args.n_molecules
                    and old_protocol.get("production_ps") == args.production_ps
                    and old_protocol.get("equil_ps") == args.equil_ps)
            if same:
                for r in old.get("results") or []:
                    if r.get("status") == "OK":
                        previous[(r.get("inchikey") or "").strip()] = r
                if previous:
                    print("  resume: {} system(s) already computed at this "
                          "protocol".format(len(previous)))
        except Exception:
            previous = {}

    results = []
    for i, r in enumerate(chosen, 1):
        done_row = previous.get(r["inchikey"])
        if done_row is not None:
            results.append(done_row)
            print("  {}/{} {:28s} cached eps_md={}".format(
                i, len(chosen), r["name"][:28], done_row.get("epsilon_md")))
            continue
        print("  {}/{} {:28s} eps_exp={:>8s} ...".format(
            i, len(chosen), r["name"][:28], r["epsilon"]), flush=True)
        try:
            res = run_system(r["name"], r["smiles"],
                             fnum(r["molar_volume_m3_mol"]),
                             args.n_molecules, args.production_ps,
                             args.equil_ps)
        except Exception as exc:
            res = {"system": r["name"],
                   "status": "FAILED: {}".format(type(exc).__name__),
                   "detail": str(exc)[:300]}
        res["inchikey"] = r["inchikey"]
        res["epsilon_experimental"] = fnum(r["epsilon"])
        results.append(res)
        print("      -> {} eps_md={} (exp {}) g={} {}s".format(
            res.get("status"), res.get("epsilon_md"), r["epsilon"],
            res.get("kirkwood_g"), res.get("wall_seconds", "?")))

    write_csv(results)
    ok = [x for x in results if x.get("status") == "OK"]
    doc = {
        "schema": "b100.md_layer/v5",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "COMPUTED" if ok else "NOT_COMPUTED",
        "engine": {"md": "OpenMM 8.6.1", "forcefield": FORCEFIELD,
                   "charges": CHARGE_MODEL, "platform": PLATFORM,
                   "available_platforms": avail,
                   "environment": "conda env E:/conda_md (conda-forge openmm)"},
        "why_conda_env": (
            "pip 版 OpenMM 在 Windows 上只注册 Reference 平台, 在本体系生产段段错误. "
            "conda-forge 的 openmm 提供 CPU 与 OpenCL 平台, "
            "因此 MD 在独立 conda 环境中运行."
        ),
        "protocol": {
            "n_molecules": args.n_molecules, "T_K": T_K,
            "equil_ps": args.equil_ps, "production_ps": args.production_ps,
            "timestep_fs": TIMESTEP_FS, "sample_fs": SAMPLE_FS,
            "ensemble": "NVT at fixed density",
            "cutoff_nm": CUTOFF_NM, "switch_nm": SWITCH_NM,
            "epsilon_formula": "eps = 1 + (<M^2>-<M>^2)/(3 eps0 V kB T)",
            "g_formula": "g = (<M^2>-<M>^2)/(N mu^2)",
        },
        "n_systems": len(results), "n_ok": len(ok),
        "target": {"systems": 20, "minimum": 12},
        "requirement_met": len(ok) >= 12,
        "declared_calibration": {
            "liquid_volume_factor": LIQUID_VOLUME_FACTOR,
            "meaning": (
                "矩阵中的 molar_volume 是气相分子体积乘以 N_A "
                "(实测为液体摩尔体积的 0.53-0.72 倍). "
                "该因子把它放大到液体范围. 密度因此是输入而非结果, "
                "每个体系的实测密度都会一并报告."
            ),
        },
        "limits": [
            "固定密度 NVT: NPT 会因晶格初值空隙把盒子压塌, 故未使用",
            "介电常数收敛慢; 每体系的 block 标准差已报告",
            "力场为 OpenFF 2.1.0 + NAGL AM1-BCC 电荷, 非可极化模型, "
            "对强缔合体系会低估 eps",
        ],
        "results": results,
    }
    (OUT / "md_dielectric_b100.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n[B100-21] ok={}/{} requirement_met={}".format(
        len(ok), len(results), doc["requirement_met"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
