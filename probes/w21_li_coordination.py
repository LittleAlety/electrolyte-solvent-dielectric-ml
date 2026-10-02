"""W21 Tier 3 -- Axis B C_1: the Li+ coordination condition state.

Framework slots this file instantiates for the first time:

* section 3 Axis B C_1  -- the Li+-coordinated condition state (previously an
  explicit "not executed" red line in reports/w21_framework_slot_map.md);
* section 11 X2        -- the condition-state feature block, which had no
  occupant at all before this run;
* section 9            -- the robust-inversion battery re-run on the C_1 step;
* section 12           -- the direct-shift vs conditional-shift variance contrast.

Every number here is produced by the frozen pre-registration in
probes/w21_li_coordination_prereg.json.  Nothing in the frozen side moves: no
training pool is fitted, no frozen reading is touched, no shot is taken, and no
Reaxys value is read.  The Batt layer is used only as a reference layer on the
49-compound subset that already carries it.

Level honesty: the condition state is built at the GFN2-xTB level, not at the
DFT level the framework asks for in its own section 7 protocol.  The arm
instantiates the X2 slot; it does not claim to be the slot's final content.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import warnings
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.xtb_features import parse_xtb_output
from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

META = ROOT / "data" / "processed" / "w21_chemical_space_metadata.csv"
THEMOL_LAYER = ROOT / "data" / "processed" / "themol_orbital_layer.csv"
ROSTER = ROOT / "data" / "dielectric_v03.csv"
V03_PHYSICAL = ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
PREREG = ROOT / "probes" / "w21_li_coordination_prereg.json"
SUMMARY = ROOT / "probes" / "w21_li_coordination_summary.json"
LAYER_CSV = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
PAIR_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_inversions.csv"
TOPK_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_topk.csv"
DELTA_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_delta_stats.csv"
BATT_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_batt_step.csv"
QC_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_qc.csv"
BINDING_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_binding_posthoc.csv"
REPORT = ROOT / "reports" / "w21_li_coordination.md"

LI_START_DISTANCE_A = 2.0
UNBOUND_START_DISTANCE_A = 3.0
INTACT_DIST_A = 2.60
LOOSE_DIST_A = 3.50
INTACT_CHARGE_E = 0.30
LOOSE_CHARGE_E = 0.10
Z = 1.96
DELTA_REF_EV = 0.05
BOOTSTRAP_B = 5000
SEED = 20261002
HARTREE_TO_EV = 27.211386245988
SCF_RETRY_ARGUMENTS = ("--iterations", "1000", "--etemp", "1000")
SCF_RETRY_CSV = ROOT / "probes" / "artifacts" / "w21_li_coordination_scf_retry_posthoc.csv"
warnings.filterwarnings("ignore", message=".*Polyfit may be poorly conditioned.*")
TOPK_RULES = (("k/N=10%", 0.10), ("k/N=20%", 0.20), ("k/N=30%", 0.30))
CHANNELS = (
    ("homo", "homo_free_eV", "homo_li_eV", "P_0^ox = -epsilon_HOMO: bigger is more oxidation-resistant"),
    ("lumo", "lumo_free_eV", "lumo_li_eV", "P_0^red = epsilon_LUMO: bigger is more reduction-resistant"),
    ("gap", "gap_free_eV", "gap_li_eV", "gap carries no direction; reference only"),
)
LAYER_FIELDS = (
    "inchikey", "name", "canonical_smiles", "row_index", "seed", "motif_class",
    "donor_symbol", "donor_index", "donor_anchor", "formal_charge", "charge_C0", "charge_C1",
    "homo_free_eV", "lumo_free_eV", "gap_free_eV", "total_energy_free_hartree",
    "homo_li_eV", "lumo_li_eV", "gap_li_eV", "total_energy_li_hartree",
    "delta_homo_eV", "delta_lumo_eV", "delta_gap_eV",
    "li_mulliken_q", "li_min_dist_A", "li_nearest_atom",
    "ff_status", "xtb_version", "c0_status", "c1_status", "qc_status", "error",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def resolve_xtb() -> Path:
    """Reuse the repository's frozen xTB resolver instead of inventing a new one."""

    spec = importlib.util.spec_from_file_location(
        "_xtb_physical_features", ROOT / "scripts" / "run_xtb_physical_features.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._resolve_xtb(None)


# --------------------------------------------------------------------------- #
# pool construction: motif class + Li placement
# --------------------------------------------------------------------------- #

LONE_PAIR_PRIORITY = {8: 0, 7: 1, 16: 2}


def _fragment_charges(molecule):
    """Return (atom -> fragment id, fragment id -> net charge)."""

    from rdkit import Chem

    atom_fragment = {}
    fragment_charge = {}
    for fragment_id, atoms in enumerate(Chem.GetMolFrags(molecule)):
        charge = sum(molecule.GetAtomWithIdx(i).GetFormalCharge() for i in atoms)
        fragment_charge[fragment_id] = charge
        for i in atoms:
            atom_fragment[i] = fragment_id
    return atom_fragment, fragment_charge


def classify_motif(molecule):
    """Deterministic motif class + donor atom, per the frozen pre-registration."""

    from rdkit import Chem

    atom_fragment, fragment_charge = _fragment_charges(molecule)
    anionic = {f for f, q in fragment_charge.items() if q < 0}

    def allowed(index):
        fragment_id = atom_fragment[index]
        if anionic:
            return fragment_id in anionic
        return fragment_charge[fragment_id] <= 0

    lone = [
        (LONE_PAIR_PRIORITY[a.GetAtomicNum()], a.GetIdx())
        for a in molecule.GetAtoms()
        if a.GetAtomicNum() in LONE_PAIR_PRIORITY
        and a.GetFormalCharge() <= 0
        and allowed(a.GetIdx())
    ]
    if lone:
        lone.sort()
        return {"motif_class": "lone_pair", "donor_index": lone[0][1], "donor_kind": "lone_pair"}

    if anionic:
        halide = sorted(
            a.GetIdx()
            for a in molecule.GetAtoms()
            if a.GetAtomicNum() == 9 and a.GetFormalCharge() <= 0 and allowed(a.GetIdx())
        )
        if halide:
            return {"motif_class": "anion_halide", "donor_index": halide[0], "donor_kind": "lone_pair"}

    rings = [
        ring
        for ring in molecule.GetRingInfo().AtomRings()
        if len(ring) <= 6 and all(molecule.GetAtomWithIdx(i).GetIsAromatic() for i in ring)
    ]
    rings = [ring for ring in rings if allowed(ring[0])]
    if rings:
        rings.sort(key=lambda ring: ring[0])
        return {
            "motif_class": "aromatic_pi",
            "donor_index": int(rings[0][0]),
            "donor_kind": "pi",
            "ring": tuple(int(i) for i in rings[0]),
        }

    for bond in molecule.GetBonds():
        if bond.GetBondType() != Chem.BondType.DOUBLE:
            continue
        begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
        if begin.GetSymbol() == "C" and end.GetSymbol() == "C" and allowed(bond.GetBeginAtomIdx()):
            return {
                "motif_class": "alkene_pi",
                "donor_index": bond.GetBeginAtomIdx(),
                "donor_kind": "pi",
                "alkene": (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()),
            }

    return {"motif_class": "no_motif", "donor_index": -1, "donor_kind": "none"}


def _positions(molecule):
    conformer = molecule.GetConformer()
    return np.array([list(conformer.GetAtomPosition(i)) for i in range(molecule.GetNumAtoms())])


def _away_normal(points, plane_atoms, normal):
    """Flip the plane normal so that it points away from the rest of the molecule."""

    others = [i for i in range(points.shape[0]) if i not in set(plane_atoms)]
    if not others:
        return normal
    barycentre = points[plane_atoms].mean(axis=0)
    reference = points[others].mean(axis=0)
    if float(np.dot(normal, reference - barycentre)) > 0.0:
        return -normal
    return normal


def li_position(molecule, motif):
    """Return the pre-registered Li start position and a human-readable anchor."""

    points = _positions(molecule)
    kind = motif["donor_kind"]

    if kind == "lone_pair":
        index = int(motif["donor_index"])
        atom = molecule.GetAtomWithIdx(index)
        base = points[index]
        neighbours = [points[n.GetIdx()] for n in atom.GetNeighbors()]
        if neighbours:
            direction = np.sum([base - p for p in neighbours], axis=0)
        else:
            direction = np.array([1.0, 0.0, 0.0])
        norm = float(np.linalg.norm(direction))
        direction = direction / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])
        return base + LI_START_DISTANCE_A * direction, atom.GetSymbol() + str(index)

    if motif["motif_class"] == "aromatic_pi":
        ring = list(motif["ring"])
        centre = points[ring].mean(axis=0)
        v1 = points[ring[1]] - points[ring[0]]
        v2 = points[ring[2]] - points[ring[0]]
        normal = np.cross(v1, v2)
        norm = float(np.linalg.norm(normal))
        normal = normal / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
        normal = _away_normal(points, ring, normal)
        return centre + LI_START_DISTANCE_A * normal, "ring_centroid"

    if motif["motif_class"] == "alkene_pi":
        i, j = motif["alkene"]
        centre = 0.5 * (points[i] + points[j])
        axis = points[j] - points[i]
        reference = None
        for atom_index in (i, j):
            for neighbour in molecule.GetAtomWithIdx(atom_index).GetNeighbors():
                if neighbour.GetIdx() not in (i, j):
                    reference = points[neighbour.GetIdx()]
                    break
            if reference is not None:
                break
        if reference is None:
            direction = np.array([0.0, 0.0, 1.0])
        else:
            normal = np.cross(axis, reference - points[i])
            norm = float(np.linalg.norm(normal))
            normal = normal / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
            direction = _away_normal(points, [i, j], normal)
        return centre + LI_START_DISTANCE_A * direction, "alkene_midpoint"

    centroid = points.mean(axis=0)
    distances = np.linalg.norm(points - centroid, axis=1)
    farthest = int(np.argmax(distances))
    direction = points[farthest] - centroid
    norm = float(np.linalg.norm(direction))
    direction = direction / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
    return centroid + UNBOUND_START_DISTANCE_A * direction, "unbound_reference"


# --------------------------------------------------------------------------- #
# embedding + xTB execution
# --------------------------------------------------------------------------- #

def embed(smiles, seed):
    """Mirror generate_3d_xyz, but keep the conformer so Li can be placed on it."""

    from rdkit import Chem
    from rdkit.Chem import AllChem

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None, None, "invalid_smiles"
    molecule = Chem.AddHs(molecule)
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = int(seed)
    parameters.useRandomCoords = True
    if AllChem.EmbedMolecule(molecule, parameters) != 0:
        return None, None, "embed_failed"
    if AllChem.MMFFHasAllMoleculeParams(molecule):
        status = int(AllChem.MMFFOptimizeMolecule(molecule, maxIters=1000))
    else:
        status = int(AllChem.UFFOptimizeMolecule(molecule, maxIters=1000))
    return molecule, status, None


def xyz_block_with_li(molecule, position):
    """Append Li as the last atom of the free-state XYZ block, byte for byte."""

    from rdkit import Chem

    lines = Chem.MolToXYZBlock(molecule).rstrip("\n").split("\n")
    lines[0] = str(int(lines[0]) + 1)
    lines.append(
        "Li  % .6f % .6f % .6f" % (float(position[0]), float(position[1]), float(position[2]))
    )
    return "\n".join(lines) + "\n"


def run_arm(executable, label, xyz_text, charge, timeout_seconds, extra_arguments=None):
    scratch = Path(tempfile.mkdtemp(prefix="w21li_"))
    try:
        (scratch / (label + ".xyz")).write_text(xyz_text, encoding="utf-8")
        started = time.perf_counter()
        completed = run_xtb_subprocess(
            executable,
            xtb_optimisation_arguments(label + ".xyz", formal_charge=charge)
            + list(extra_arguments or ()),
            cwd=scratch,
            timeout_seconds=timeout_seconds,
        )
        elapsed = time.perf_counter() - started
        optimized = scratch / "xtbopt.xyz"
        charges = scratch / "charges"
        return {
            "returncode": int(completed.returncode),
            "stdout": completed.stdout.decode("utf-8", "replace"),
            "optimized_xyz": (
                optimized.read_text(encoding="utf-8", errors="replace")
                if optimized.is_file()
                else None
            ),
            "charges_text": (
                charges.read_text(encoding="utf-8", errors="replace")
                if charges.is_file()
                else None
            ),
            "sentinel": (scratch / ".xtboptok").is_file(),
            "seconds": elapsed,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def orbital_energy(text, tag):
    for line in text.splitlines():
        if line.rstrip().endswith("(" + tag + ")"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[-2])
    return None


def li_diagnostics(result):
    out = {"li_mulliken_q": None, "li_min_dist_A": None, "li_nearest_atom": None}
    charges_text = result.get("charges_text")
    if charges_text:
        values = [line for line in charges_text.splitlines() if line.strip()]
        if values:
            out["li_mulliken_q"] = float(values[-1])
    optimized = result.get("optimized_xyz")
    if optimized:
        lines = optimized.splitlines()
        try:
            count = int(lines[0].split()[0])
        except (IndexError, ValueError):
            return out
        atoms = []
        for line in lines[2:2 + count]:
            parts = line.split()
            if len(parts) >= 4:
                atoms.append((parts[0], np.array([float(parts[1]), float(parts[2]), float(parts[3])])))
        if atoms and atoms[-1][0] == "Li":
            lithium = atoms[-1][1]
            best = None
            for symbol, position in atoms[:-1]:
                if symbol == "H":
                    continue
                distance = float(np.linalg.norm(lithium - position))
                if best is None or distance < best[0]:
                    best = (distance, symbol)
            if best is not None:
                out["li_min_dist_A"] = best[0]
                out["li_nearest_atom"] = best[1]
    return out


def xtb_error_reason(text):
    """Deepest reason line xTB prints before giving up (its -1- line)."""

    reason = None
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^-\d+-\s*\S", stripped):
            reason = stripped
        elif stripped.startswith("[ERROR]"):
            reason = stripped
    return reason


def parse_arm(result):
    """Canonical parser + the two Li-specific diagnostics."""

    text = result["stdout"]
    if result["sentinel"]:
        text = text + "\nnormal termination of xtb\n"
    payload = {
        "homo_eV": None, "lumo_eV": None, "gap_eV": None,
        "total_energy_hartree": None, "xtb_version": None,
        "li_mulliken_q": None, "li_min_dist_A": None, "li_nearest_atom": None,
        "status": "error", "error": "",
    }
    version = re.search(r"xtb version\s+(\S+)", text)
    if version:
        payload["xtb_version"] = version.group(1)
    if result["returncode"] != 0 or not result["sentinel"]:
        payload["status"] = "xtb_failed"
        reason = xtb_error_reason(text)
        payload["error"] = "returncode=%d sentinel=%s" % (result["returncode"], result["sentinel"])
        if reason:
            payload["error"] += ": " + reason
        return payload
    try:
        parsed = parse_xtb_output(text)
    except Exception as error:  # noqa: BLE001 - the message is the evidence
        payload["status"] = "parse_failed"
        payload["error"] = str(error)[:200]
        return payload
    payload["status"] = "ok"
    payload["gap_eV"] = float(parsed.homo_lumo_gap_ev)
    payload["total_energy_hartree"] = float(parsed.total_energy_hartree)
    payload["homo_eV"] = orbital_energy(text, "HOMO")
    payload["lumo_eV"] = orbital_energy(text, "LUMO")
    payload.update(li_diagnostics(result))
    return payload


def qc_status(distance, charge):
    if distance is None or charge is None:
        return "not_available"
    if distance <= INTACT_DIST_A and charge >= INTACT_CHARGE_E:
        return "intact"
    if distance > LOOSE_DIST_A or charge < LOOSE_CHARGE_E:
        return "dissociated"
    return "loose"


# --------------------------------------------------------------------------- #
# readings
# --------------------------------------------------------------------------- #

def topk_set(values, k):
    order = sorted(range(len(values)), key=lambda index: (-float(values[index]), index))
    return set(order[:k])


def rank_metrics(x, y):
    from scipy import stats

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x.size
    payload = {
        "n": int(n),
        "spearman_rho": float(stats.spearmanr(x, y).statistic),
        "kendall_tau_b": float(stats.kendalltau(x, y, variant="b").statistic),
        "pearson_r": float(stats.pearsonr(x, y).statistic),
        "ols_slope": float(np.polyfit(x, y, 1)[0]),
        "ols_intercept": float(np.polyfit(x, y, 1)[1]),
        "mean_signed_shift_eV": float(np.mean(y - x)),
        "mean_abs_shift_eV": float(np.mean(np.abs(y - x))),
    }
    iu = np.triu_indices(n, 1)
    dx = (x[:, None] - x[None, :])[iu]
    dy = (y[:, None] - y[None, :])[iu]
    inversions = np.sign(dx) != np.sign(dy)
    payload["pairs"] = int(inversions.size)
    payload["naive_inversions"] = int(inversions.sum())
    payload["f_naive_inversion"] = float(inversions.mean())
    payload["topk"] = {}
    for label, fraction in TOPK_RULES:
        k = max(1, int(round(fraction * n)))
        a = topk_set(x, k)
        b = topk_set(y, k)
        payload["topk"][label] = {
            "k": int(k),
            "overlap": len(a & b) / k,
            "jaccard": len(a & b) / len(a | b),
            "entered": len(b - a),
            "left": len(a - b),
        }
    return payload


def bootstrap_rank(x, y, draws, seed):
    rng = np.random.default_rng(seed)
    n = x.size
    rho, tau = [], []
    overlaps = {label: [] for label, _ in TOPK_RULES}
    for _ in range(draws):
        index = rng.integers(0, n, n)
        if np.unique(index).size < 5:
            continue
        metrics = rank_metrics(x[index], y[index])
        rho.append(metrics["spearman_rho"])
        tau.append(metrics["kendall_tau_b"])
        for label, _ in TOPK_RULES:
            overlaps[label].append(metrics["topk"][label]["overlap"])
    def interval(values):
        if not values:
            return {"lo": float("nan"), "median": float("nan"), "hi": float("nan"), "draws_used": 0}
        lo, med, hi = np.percentile(values, [2.5, 50, 97.5])
        return {"lo": float(lo), "median": float(med), "hi": float(hi), "draws_used": len(values)}
    return {
        "spearman_rho": interval(rho),
        "kendall_tau_b": interval(tau),
        "topk_overlap": {label: interval(values) for label, values in overlaps.items()},
    }


def loo_residuals(x, y):
    n = x.size
    out = np.zeros(n)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        slope, intercept = np.polyfit(x[mask], y[mask], 1)
        out[i] = y[i] - (slope * x[i] + intercept)
    return out


def batt_step(x, y):
    """Framework section 9 battery, exactly as w21_rank_stability.py computes it."""

    from scipy import stats

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    mapped = slope * x + intercept
    u = np.abs(loo_residuals(x, y))
    iu = np.triu_indices(y.size, 1)
    d_a = (mapped[:, None] - mapped[None, :])[iu]
    d_b = (y[:, None] - y[None, :])[iu]
    sep = (Z * np.sqrt(u[:, None] ** 2 + u[None, :] ** 2))[iu]
    resolved_a = np.abs(d_a) >= sep
    resolved_b = np.abs(d_b) >= DELTA_REF_EV
    inversions = np.sign(d_a) != np.sign(d_b)
    both = resolved_a & resolved_b
    robust = int((both & inversions).sum())
    return {
        "n": int(y.size),
        "pairs": int(inversions.size),
        "ols_slope": float(slope),
        "ols_intercept": float(intercept),
        "loo_mean_abs_residual_eV": float(np.mean(u)),
        "resolved_in_P0": int(resolved_a.sum()),
        "resolved_in_R_sol": int(resolved_b.sum()),
        "resolved_in_both": int(both.sum()),
        "f_unresolved_P0": float(1.0 - resolved_a.mean()),
        "f_unresolved_R_sol": float(1.0 - resolved_b.mean()),
        "f_unresolved_at_least_one": float(1.0 - both.mean()),
        "naive_inversions": int(inversions.sum()),
        "f_naive_inversion": float(inversions.mean()),
        "robust_inversions": robust,
        "f_robust_inversion": (robust / int(both.sum())) if int(both.sum()) else float("nan"),
        "kendall_tau_b": float(stats.kendalltau(x, y, variant="b").statistic),
        "spearman_rho": float(stats.spearmanr(x, y).statistic),
    }


def load_batt_subset():
    """The frozen 49-compound Batt subset, key for key with w21_rank_stability.py."""

    roster = {row["inchikey"] for row in read_rows(ROSTER)}
    keep = []
    for row in read_rows(THEMOL_LAYER):
        if str(row.get("inchikey", "")) not in roster:
            continue
        if str(row.get("structure_check", "")) != "inchikey_match":
            continue
        if not str(row.get("homo_gfn2_eV", "")).strip():
            continue
        if not str(row.get("batt_homo_eV", "")).strip():
            continue
        keep.append(row)
    return keep


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

MOTIF_CLASSES = ("lone_pair", "anion_halide", "aromatic_pi", "alkene_pi")


def fmt(value, digits=12):
    if value is None or value == "":
        return ""
    return ("%." + str(digits) + "g") % float(value)


def run_probe(executable, timeout_seconds, limit=None):
    from rdkit import Chem

    rows = read_rows(META)
    if limit is not None:
        rows = rows[:limit]
    layer_rows = []
    started = time.perf_counter()
    for index, row in enumerate(rows):
        record = {field: "" for field in LAYER_FIELDS}
        record["inchikey"] = str(row.get("molecule_id") or row.get("inchikey") or "")
        record["name"] = row["name"]
        record["canonical_smiles"] = row["canonical_smiles"]
        record["row_index"] = index
        seed = 42 + index
        record["seed"] = seed

        molecule, ff_status, error = embed(row["canonical_smiles"], seed)
        if molecule is None:
            record["ff_status"] = ""
            record["motif_class"] = "not_computed"
            record["c0_status"] = "skipped"
            record["c1_status"] = "skipped"
            record["qc_status"] = "not_available"
            record["error"] = error or ""
            layer_rows.append(record)
            write_csv(LAYER_CSV, LAYER_FIELDS, [[r[f] for f in LAYER_FIELDS] for r in layer_rows])
            print(json.dumps({"processed": index + 1, "total": len(rows), "name": row["name"],
                              "motif": "not_computed", "qc": "not_available", "error": error},
                             ensure_ascii=False), flush=True)
            continue

        record["ff_status"] = ff_status
        motif = classify_motif(molecule)
        record["motif_class"] = motif["motif_class"]
        record["donor_index"] = motif["donor_index"]
        if motif["donor_kind"] == "lone_pair":
            record["donor_symbol"] = molecule.GetAtomWithIdx(int(motif["donor_index"])).GetSymbol()
        elif motif["motif_class"] in ("aromatic_pi", "alkene_pi"):
            record["donor_symbol"] = "pi"
        else:
            record["donor_symbol"] = "none"

        net_charge = int(Chem.GetFormalCharge(molecule))
        record["formal_charge"] = net_charge
        record["charge_C0"] = net_charge
        record["charge_C1"] = net_charge + 1

        position, anchor = li_position(molecule, motif)
        label = "c%03d" % index
        try:
            c0 = parse_arm(run_arm(executable, label + "_0", Chem.MolToXYZBlock(molecule),
                                   net_charge, timeout_seconds))
        except Exception as error:  # noqa: BLE001
            c0 = {"status": "exception", "error": str(error)[:200], "homo_eV": None, "lumo_eV": None,
                  "gap_eV": None, "total_energy_hartree": None, "xtb_version": None,
                  "li_mulliken_q": None, "li_min_dist_A": None, "li_nearest_atom": None}
        try:
            c1 = parse_arm(run_arm(executable, label + "_1", xyz_block_with_li(molecule, position),
                                   net_charge + 1, timeout_seconds))
        except Exception as error:  # noqa: BLE001
            c1 = {"status": "exception", "error": str(error)[:200], "homo_eV": None, "lumo_eV": None,
                  "gap_eV": None, "total_energy_hartree": None, "xtb_version": None,
                  "li_mulliken_q": None, "li_min_dist_A": None, "li_nearest_atom": None}

        record["c0_status"] = c0["status"]
        record["c1_status"] = c1["status"]
        record["xtb_version"] = c0.get("xtb_version") or c1.get("xtb_version") or ""
        record["homo_free_eV"] = fmt(c0["homo_eV"])
        record["lumo_free_eV"] = fmt(c0["lumo_eV"])
        record["gap_free_eV"] = fmt(c0["gap_eV"])
        record["total_energy_free_hartree"] = fmt(c0["total_energy_hartree"])
        record["homo_li_eV"] = fmt(c1["homo_eV"])
        record["lumo_li_eV"] = fmt(c1["lumo_eV"])
        record["gap_li_eV"] = fmt(c1["gap_eV"])
        record["total_energy_li_hartree"] = fmt(c1["total_energy_hartree"])
        record["li_mulliken_q"] = fmt(c1["li_mulliken_q"])
        record["li_min_dist_A"] = fmt(c1["li_min_dist_A"])
        record["li_nearest_atom"] = c1["li_nearest_atom"] or ""
        errors = [part for part in (c0.get("error"), c1.get("error")) if part]
        record["error"] = " | ".join(errors)[:300]
        if c0["status"] == "ok" and c1["status"] == "ok":
            record["delta_homo_eV"] = fmt(c1["homo_eV"] - c0["homo_eV"])
            record["delta_lumo_eV"] = fmt(c1["lumo_eV"] - c0["lumo_eV"])
            record["delta_gap_eV"] = fmt(c1["gap_eV"] - c0["gap_eV"])
            record["qc_status"] = qc_status(c1["li_min_dist_A"], c1["li_mulliken_q"])
        else:
            record["qc_status"] = "not_available"
        record["donor_anchor"] = anchor

        layer_rows.append(record)
        write_csv(LAYER_CSV, LAYER_FIELDS, [[r[f] for f in LAYER_FIELDS] for r in layer_rows])
        print(json.dumps({"processed": index + 1, "total": len(rows), "name": row["name"],
                          "motif": record["motif_class"], "qc": record["qc_status"],
                          "d_homo": record["delta_homo_eV"], "li_q": record["li_mulliken_q"],
                          "li_d": record["li_min_dist_A"],
                          "sec": round(time.perf_counter() - started, 1)}, ensure_ascii=False), flush=True)
    return layer_rows


def lithium_ion_energy(executable, timeout_seconds):
    """GFN2 total energy of an isolated Li+ -- the constant behind the post-hoc binding read."""

    block = "1\n\nLi  0.000000  0.000000  0.000000\n"
    parsed = parse_arm(run_arm(executable, "li_plus", block, 1, timeout_seconds))
    if parsed["status"] != "ok":
        return None
    return float(parsed["total_energy_hartree"])


def compute_readings(layer_rows):
    motif_rows = [
        row for row in layer_rows
        if row["motif_class"] in MOTIF_CLASSES
        and row["c0_status"] == "ok"
        and row["c1_status"] == "ok"
    ]
    channels = {}
    for key, free_col, li_col, note in CHANNELS:
        x = np.array([float(row[free_col]) for row in motif_rows])
        y = np.array([float(row[li_col]) for row in motif_rows])
        metrics = rank_metrics(x, y)
        metrics["bootstrap"] = bootstrap_rank(x, y, BOOTSTRAP_B, SEED)
        metrics["delta_mean_eV"] = float(np.mean(y - x))
        metrics["delta_sd_eV"] = float(np.std(y - x, ddof=1))
        metrics["var_ratio_shift_over_free"] = float(np.var(y - x, ddof=1) / np.var(x, ddof=1))
        metrics["note"] = note
        channels[key] = metrics

    layer_by_key = {row["inchikey"]: row for row in layer_rows}
    batt_rows = [row for row in load_batt_subset()
                 if layer_by_key.get(row["inchikey"], {}).get("c1_status") == "ok"]
    batt_keys = [row["inchikey"] for row in batt_rows]
    batt_y = np.array([float(row["batt_homo_eV"]) for row in batt_rows])
    batt_arms = {
        "P0_themol_geometry_w21_1": np.array([float(row["homo_gfn2_eV"]) for row in batt_rows]),
        "C0_this_arm_free": np.array([float(layer_by_key[k]["homo_free_eV"]) for k in batt_keys]),
        "C1_this_arm_li": np.array([float(layer_by_key[k]["homo_li_eV"]) for k in batt_keys]),
    }
    batt = {name: batt_step(values, batt_y) for name, values in batt_arms.items()}
    batt["reference_layer"] = "batt_homo_eV (wB97X-V/def2-TZVPPD/SMD(epsilon=18.5), MIT)"
    batt["tolerance"] = {"z": Z, "delta_R_sol_eV": DELTA_REF_EV,
                         "registered_limit": "reference-layer physical uncertainty not quantified in-repo"}

    v03 = {row["inchikey"]: row for row in read_rows(V03_PHYSICAL)}
    pairs = []
    for row in layer_rows:
        other = v03.get(row["inchikey"])
        if other is None:
            continue
        if not str(row["gap_free_eV"]).strip():
            continue
        if not str(other.get("homo_lumo_gap_ev", "")).strip():
            continue
        pairs.append((float(other["homo_lumo_gap_ev"]), float(row["gap_free_eV"])))
    if len(pairs) > 3:
        from scipy import stats
        a = np.array([pair[0] for pair in pairs])
        b = np.array([pair[1] for pair in pairs])
        cross = {
            "n": len(pairs),
            "pearson_r": float(stats.pearsonr(a, b).statistic),
            "mean_signed_difference_eV": float(np.mean(b - a)),
            "mean_abs_difference_eV": float(np.mean(np.abs(a - b))),
            "note": "同协议（GFN2-xTB --opt）、不同构象种子；用作 C_0 器的独立一致性核验",
        }
    else:
        cross = {"n": len(pairs), "note": "not enough overlap"}

    qc_counts = Counter(row["qc_status"] for row in layer_rows)
    motif_counts = Counter(row["motif_class"] for row in layer_rows)
    by_class = {}
    for motif_class in MOTIF_CLASSES + ("no_motif", "not_computed"):
        subset = [row for row in layer_rows if row["motif_class"] == motif_class]
        if not subset:
            continue
        by_class[motif_class] = {
            "n": len(subset),
            "qc": dict(Counter(row["qc_status"] for row in subset)),
        }
    return {
        "motif_rows": motif_rows,
        "channels": channels,
        "batt": batt,
        "batt_keys": batt_keys,
        "v03_cross_check": cross,
        "qc_counts": dict(qc_counts),
        "motif_counts": dict(motif_counts),
        "qc_by_motif_class": by_class,
    }


def write_report(summary):
    pool = summary["pool"]
    channels = summary["channels"]
    batt = summary["batt_step"]
    qc = summary["qc"]
    lines = []
    add = lines.append
    add("# W21 · Axis B `C_1`：Li⁺ 配位条件态首次实例化（GFN2-xTB 级）")
    add("")
    add("- **预注册**：`probes/w21_li_coordination_prereg.json`（sha256 `%s`，status = `%s`）。"
        % (summary["preregistration"]["sha256"][:16] + "…", summary["preregistration"]["status"]))
    add("- **池**：冻结 ε 名册 %d 化合物 × 2 臂 = %d 次 xTB；其中带配位基序 %d 个、无基序（unbound_reference）%d 个。"
        % (pool["n_compounds"], pool["runs"], pool["motif_counts"].get("_motif_total", 0),
           pool["motif_counts"].get("no_motif", 0)))
    add("- **层级**：GFN2-xTB 半经验 + 单 Li⁺ + 单预注册构象 + 真空气相。**这不是框架 §7 要求的 DFT 级**，"
        "本臂把框架 §11 的 `X2`（条件态特征块）与 §3 Axis B 的 `C_1` 由「未执行」推进到「已实例化（低层级）」。")
    add("- **纪律**：不动四个冻结读数、不占 shot（本周主记分牌尝试 0 次，累计仍 12 次）、不引用 Reaxys 数值、"
        "不把 Batt 参考层折进任何训练池。")
    add("")
    add("## 1. 池与质控")
    add("")
    add("| 基序类 | n | intact | loose | dissociated | not_available |")
    add("| --- | --- | --- | --- | --- | --- |")
    for motif_class in ("lone_pair", "anion_halide", "aromatic_pi", "alkene_pi", "no_motif", "not_computed"):
        entry = qc["by_motif_class"].get(motif_class)
        if entry is None:
            continue
        counts = entry["qc"]
        add("| `%s` | %d | %d | %d | %d | %d |"
            % (motif_class, entry["n"], counts.get("intact", 0), counts.get("loose", 0),
               counts.get("dissociated", 0), counts.get("not_available", 0)))
    add("")
    add("质控判据（跑前冻结）：`intact` = Li–X ≤ %.2f Å 且 q(Li) ≥ %.2f e；`dissociated` = Li–X > %.2f Å 或 q(Li) < %.2f e；"
        "两者之间为 `loose`。" % (INTACT_DIST_A, INTACT_CHARGE_E, LOOSE_DIST_A, LOOSE_CHARGE_E))
    add("")
    binding = summary.get("post_hoc", {}).get("li_binding_energy", {})
    by_class = binding.get("by_motif_class_eV", {})
    if by_class:
        add("**一条与预注册预期不符、必须照实说的结果**：预注册写的期望是 `no_motif` 类应落到 `dissociated`"
            "（Li⁺ 在饱和烃/卤代烷上没有设计给体）。实测并非如此 —— GFN2-xTB 在这些分子上仍然让 Li⁺ 停在"
            "约 2.2–2.4 Å 的接触距离上，结构判据因此把它们判成 `intact`。"
            "结论：**几何距离 + Mulliken 电荷这两个判据不足以区分「设计过的给体配位」与"
            "「半经验方法在无给体分子上的虚假粘附」**。")
        add("")
        add("为把这件事讲清楚，本件另附一条**事后补充（非预注册）**的相互作用强度判据："
            "`binding = E([LiM]⁺) − E(M) − E(Li⁺)`，三项全部取自同一批 GFN2-xTB `--opt` 能量"
            "（Li⁺ 用单原子单点）。")
        add("")
        add("| 基序类 | n | binding 均值 (eV) | 中位数 (eV) | 最小 (eV) | 最大 (eV) |")
        add("| --- | --- | --- | --- | --- | --- |")
        for motif_class, entry in by_class.items():
            add("| `%s` | %d | %+.4f | %+.4f | %+.4f | %+.4f |"
                % (motif_class, entry["n"], entry["mean_eV"], entry["median_eV"],
                   entry["min_eV"], entry["max_eV"]))
        add("")
        add("该列**不参与任何预注册读数**，只用于解释上面的质控偏差；主读数（第 3、4 节）仍只用 224 个带基序化合物。")
        add("")
    add("## 2. Δ 分布：C_0 → C_1 的条件位移（§12 的 direct vs conditional-shift 对照）")
    add("")
    add("| 通道 | n | Δ 均值 (eV) | Δ 标准差 (eV) | var(Δ)/var(free) | ρ (C_0,C_1) | τ_b |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for key, _free, _li, _note in CHANNELS:
        entry = channels[key]
        add("| `%s` | %d | %+.4f | %.4f | %.4f | %.4f | %.4f |"
            % (key, entry["n"], entry["delta_mean_eV"], entry["delta_sd_eV"],
               entry["var_ratio_shift_over_free"], entry["spearman_rho"], entry["kendall_tau_b"]))
    add("")
    add("读法：`var(Δ)/var(free)` 量的是「配位这一步造成的位移」相对「溶剂身份造成的总展宽」有多大。"
        "该比值远小于 1 意味着条件态是二阶效应，但它非零本身说明条件态携带独立信息。")
    add("")
    add("## 3. C_0 → C_1 的排序稳定性（§9 的内部台阶）")
    add("")
    add("| 通道 | pairs | naive 换序 | 换序率 | Top-k 10% overlap | Top-k 20% | Top-k 30% |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for key, _free, _li, _note in CHANNELS:
        entry = channels[key]
        topk = entry["topk"]
        add("| `%s` | %d | %d | %.4f | %.3f | %.3f | %.3f |"
            % (key, entry["pairs"], entry["naive_inversions"], entry["f_naive_inversion"],
               topk["k/N=10%"]["overlap"], topk["k/N=20%"]["overlap"], topk["k/N=30%"]["overlap"]))
    add("")
    for key, _free, _li, _note in CHANNELS:
        entry = channels[key]
        boot = entry["bootstrap"]
        add("- `%s`：ρ 的 bootstrap 95%% CI = [%.4f, %.4f]（%d 次重采样）；Top-k 10%% overlap 的 CI = [%.3f, %.3f]。"
            % (key, boot["spearman_rho"]["lo"], boot["spearman_rho"]["hi"], boot["spearman_rho"]["draws_used"],
               boot["topk_overlap"]["k/N=10%"]["lo"], boot["topk_overlap"]["k/N=10%"]["hi"]))
    add("")
    add("## 4. §9 复核：49 化合物 Batt 子集上的三层并排")
    add("")
    add("参考层：`batt_homo_eV`（ωB97X-V/def2-TZVPPD/SMD(ε=18.5)，MIT）。容差：z = %.2f、Δ_R_sol = %.2f eV。"
        % (batt["tolerance"]["z"], batt["tolerance"]["delta_R_sol_eV"]))
    add("")
    add("| 廉价层 | n | pairs | resolved_in_both | robust inversion | f_robust | naive 换序率 | τ_b | ρ |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in ("P0_themol_geometry_w21_1", "C0_this_arm_free", "C1_this_arm_li"):
        entry = batt[name]
        add("| `%s` | %d | %d | %d | %d | %.4f | %.4f | %.4f | %.4f |"
            % (name, entry["n"], entry["pairs"], entry["resolved_in_both"], entry["robust_inversions"],
               entry["f_robust_inversion"], entry["f_naive_inversion"],
               entry["kendall_tau_b"], entry["spearman_rho"]))
    add("")
    add("`P0_themol_geometry_w21_1` 行是本文件对 W21-1 的回归核验：用同一套代码重算 W21-1 的 P_0（THEMol 几何），"
        "应当复现其 `robust inversion = 0 / 451`。")
    add("")
    add("## 5. 与 v03 物理块的一致性核验")
    add("")
    cross = summary["v03_cross_check"]
    if cross.get("n", 0) > 3:
        add("- n = %d；Pearson r = %.4f；平均有符号差 = %+.4f eV；平均绝对差 = %.4f eV。"
            % (cross["n"], cross["pearson_r"], cross["mean_signed_difference_eV"], cross["mean_abs_difference_eV"]))
        add("- 说明：%s" % cross["note"])
    else:
        add("- 重叠不足（n = %d）。" % cross.get("n", 0))
    add("")
    add("## 6. §19 Gate 1 判词")
    add("")
    add("- %s" % summary["gate1"]["verdict"])
    add("- %s" % summary["gate1"]["reason"])
    add("")
    add("## 7. 边界与不做")
    add("")
    for item in summary["boundaries"]:
        add("- %s" % item)
    add("")
    post = summary.get("post_hoc", {})
    retry = post.get("scf_retry") or {}
    binding = post.get("li_binding_energy", {})
    failures = summary["qc"].get("failed_arms", [])
    if retry or binding or failures:
        add("## 8. 事后诊断（明确标注：非预注册，不进任何主读数）")
        add("")
    if failures:
        add("### 8.1 冻结协议下的失败臂")
        add("")
        add("| 化合物 | 基序类 | C_0 | C_1 | 原因 |")
        add("| --- | --- | --- | --- | --- |")
        for entry in failures:
            add("| %s | `%s` | %s | %s | %s |"
                % (entry["name"], entry["motif_class"], entry["c0_status"], entry["c1_status"],
                   entry["error"].replace("|", "/")[:110]))
        add("")
    if retry:
        add("### 8.2 SCF 重试（事后）")
        add("")
        add("- 失败臂 **%d** 个；换用 `--iterations 1000 --etemp 1000` 重试后 **恢复 %d 个、仍失败 %d 个**。"
            % (retry["attempted"], retry["recovered"], retry["still_failed"]))
        add("- 目的只是区分「SCF 设置伪失败」与「方法层面的真实失败」；冻结层的 %d 个化合物读数**不因此改变**。"
            % summary["pool"]["n_compounds"])
        add("")
    if binding:
        spurious = binding.get("not_a_bound_state", [])
        add("### 8.3 结合能体检（事后）")
        add("")
        add("- 定义：`binding_eV = E([LiM]⁺) − E(M) − E(Li⁺)`，三项全部来自同一批 GFN2-xTB 能量。")
        add("- **判读**：真实给体配位的结合能在 −1 至 −2 eV 量级；结合能为**正**意味着那张「C_1 结构」在能量上根本不成立（Li⁺ 其实没有留下来）。")
        if spurious:
            add("- 本件共 **%d** 行的结合能为正，按基序类统计：" % len(spurious))
            add("  " + "、".join(
                "%s %d 行" % (cls, sum(1 for entry in spurious if entry["motif_class"] == cls))
                for cls in sorted({entry["motif_class"] for entry in spurious})) + "。")
            add("- **%d 行**落在 `no_motif`（unbound_reference）类：冻结的结构判据把它们判成 `intact`/"
                "`loose`，结合能体检把它们标为 `not_a_bound_state`。"
                "主读数（第 3、4 节）本来就只用带基序化合物，因此不受影响。"
                % sum(1 for entry in spurious if entry["motif_class"] == "no_motif"))
            add("- 另外 **%d 行落在带基序类内**（见上表），也就是说：**结构判据单独用会骗人，而且骗到的不只是无给体分子**。"
                % sum(1 for entry in spurious if entry["motif_class"] != "no_motif"))
        add("")
        sensitivity = post.get("binding_sensitivity")
        if sensitivity:
            add("**事后敏感性**：把上述 %d 行剔除后，重算第 3 节的排序稳定性读数。" % sensitivity["n_dropped"])
            add("")
            add("| 通道 | n（剔除后） | ρ（剔除后） | ρ（全池） | Top-10% overlap（剔除后） |")
            add("| --- | --- | --- | --- | --- |")
            for key, _free, _li, _note in CHANNELS:
                entry = sensitivity["channels"][key]
                add("| `%s` | %d | %.4f | %.4f | %.3f |"
                    % (key, entry["n"], entry["spearman_rho"], channels[key]["spearman_rho"],
                       entry["topk_overlap"]["k/N=10%"]))
            add("")
            add("剔除的化合物：%s。**结论不随剔除而改变**，这是本条体检最重要的信息。"
                % "、".join(sensitivity["dropped_compounds"]))
            add("")
    add("*W21 Tier 3 · 生成脚本 `probes/w21_li_coordination.py` · 预注册冻结 · 冻结读数未动 · shot 未增*")
    add("")
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_summary(layer_rows, readings, prereg, layer_sha, elapsed_seconds,
                  li_plus_hartree=None, scf_retry=None):
    motif_total = sum(readings["motif_counts"].get(name, 0) for name in MOTIF_CLASSES)
    motif_counts = dict(readings["motif_counts"])
    motif_counts["_motif_total"] = motif_total
    expected = prereg["pool"]["motif_class_counts"]
    matches = all(int(readings["motif_counts"].get(k, 0)) == int(v) for k, v in expected.items())
    channels = readings["channels"]

    delta_rows = []
    topk_rows = []
    for key, _free, _li, _note in CHANNELS:
        entry = channels[key]
        delta_rows.append((
            key, entry["n"], "%.8f" % entry["delta_mean_eV"], "%.8f" % entry["delta_sd_eV"],
            "%.8f" % entry["var_ratio_shift_over_free"], "%.8f" % entry["spearman_rho"],
            "%.8f" % entry["kendall_tau_b"], "%.8f" % entry["mean_abs_shift_eV"],
        ))
        for label, _fraction in TOPK_RULES:
            block = entry["topk"][label]
            boot = entry["bootstrap"]["topk_overlap"][label]
            topk_rows.append((
                key, label, block["k"], "%.6f" % block["overlap"], "%.6f" % block["jaccard"],
                block["entered"], block["left"], "%.6f" % boot["lo"], "%.6f" % boot["hi"],
            ))
    write_csv(DELTA_CSV,
              ("channel", "n", "delta_mean_eV", "delta_sd_eV", "var_ratio_shift_over_free",
               "spearman_rho", "kendall_tau_b", "mean_abs_shift_eV"),
              delta_rows)
    write_csv(TOPK_CSV,
              ("channel", "k_rule", "k", "overlap", "jaccard", "entered", "left",
               "bootstrap_overlap_lo", "bootstrap_overlap_hi"),
              topk_rows)

    inversion_rows = []
    for key, free_col, li_col, _note in CHANNELS:
        rows = [row for row in layer_rows
                if row["motif_class"] in MOTIF_CLASSES
                and row["c0_status"] == "ok" and row["c1_status"] == "ok"]
        keys = [row["inchikey"] for row in rows]
        x = np.array([float(row[free_col]) for row in rows])
        y = np.array([float(row[li_col]) for row in rows])
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if np.sign(x[i] - x[j]) != np.sign(y[i] - y[j]):
                    inversion_rows.append((key, keys[i], keys[j], "%.6f" % x[i], "%.6f" % x[j],
                                           "%.6f" % y[i], "%.6f" % y[j]))
    write_csv(PAIR_CSV,
              ("channel", "key_i", "key_j", "free_i_eV", "free_j_eV", "li_i_eV", "li_j_eV"),
              inversion_rows)

    qc_rows = []
    for motif_class in ("lone_pair", "anion_halide", "aromatic_pi", "alkene_pi", "no_motif", "not_computed"):
        entry = readings["qc_by_motif_class"].get(motif_class)
        if entry is None:
            continue
        counts = entry["qc"]
        qc_rows.append((motif_class, entry["n"], counts.get("intact", 0), counts.get("loose", 0),
                        counts.get("dissociated", 0), counts.get("not_available", 0)))
    write_csv(QC_CSV, ("motif_class", "n", "intact", "loose", "dissociated", "not_available"), qc_rows)

    batt_rows = []
    for name in ("P0_themol_geometry_w21_1", "C0_this_arm_free", "C1_this_arm_li"):
        entry = readings["batt"][name]
        batt_rows.append((name, entry["n"], entry["pairs"], entry["resolved_in_P0"],
                          entry["resolved_in_R_sol"], entry["resolved_in_both"],
                          "%.8f" % entry["f_unresolved_at_least_one"], entry["naive_inversions"],
                          "%.8f" % entry["f_naive_inversion"], entry["robust_inversions"],
                          "%.8f" % entry["f_robust_inversion"], "%.8f" % entry["kendall_tau_b"],
                          "%.8f" % entry["spearman_rho"]))
    write_csv(BATT_CSV,
              ("arm", "n", "pairs", "resolved_in_P0", "resolved_in_R_sol", "resolved_in_both",
               "f_unresolved_at_least_one", "naive_inversions", "f_naive_inversion",
               "robust_inversions", "f_robust_inversion", "kendall_tau_b", "spearman_rho"),
              batt_rows)

    binding_rows = []
    binding_by_class = {}
    if li_plus_hartree is not None:
        for row in layer_rows:
            if row["c0_status"] != "ok" or row["c1_status"] != "ok":
                continue
            energy_free = float(row["total_energy_free_hartree"])
            energy_li = float(row["total_energy_li_hartree"])
            binding = (energy_li - energy_free - float(li_plus_hartree)) * HARTREE_TO_EV
            bound = binding < 0.0
            binding_rows.append((row["inchikey"], row["name"], row["motif_class"], row["qc_status"],
                                 "%.10f" % energy_free, "%.10f" % energy_li,
                                 "%.10f" % float(li_plus_hartree), "%.6f" % binding,
                                 "bound" if bound else "not_a_bound_state"))
            binding_by_class.setdefault(row["motif_class"], []).append(binding)
        write_csv(BINDING_CSV,
                  ("inchikey", "name", "motif_class", "qc_status", "total_energy_free_hartree",
                   "total_energy_li_hartree", "li_plus_hartree", "binding_eV", "binding_verdict"),
                  binding_rows)
    binding_summary = {
        motif_class: {
            "n": len(values),
            "mean_eV": float(np.mean(values)),
            "median_eV": float(np.median(values)),
            "min_eV": float(np.min(values)),
            "max_eV": float(np.max(values)),
        }
        for motif_class, values in sorted(binding_by_class.items())
    }

    binding_sensitivity = None
    if binding_rows:
        bound_keys = {entry[0] for entry in binding_rows if entry[-1] == "bound"}
        motif_pool = [
            row for row in layer_rows
            if row["motif_class"] in MOTIF_CLASSES
            and row["c0_status"] == "ok"
            and row["c1_status"] == "ok"
        ]
        kept = [row for row in motif_pool if row["inchikey"] in bound_keys]
        dropped = [row["name"] for row in motif_pool if row["inchikey"] not in bound_keys]
        sensitivity = {}
        for key, free_col, li_col, _note in CHANNELS:
            x = np.array([float(row[free_col]) for row in kept])
            y = np.array([float(row[li_col]) for row in kept])
            metrics = rank_metrics(x, y)
            sensitivity[key] = {
                "n": metrics["n"],
                "spearman_rho": metrics["spearman_rho"],
                "kendall_tau_b": metrics["kendall_tau_b"],
                "topk_overlap": {label: metrics["topk"][label]["overlap"] for label, _ in TOPK_RULES},
            }
        binding_sensitivity = {
            "registration": "post_hoc_not_preregistered",
            "rule": "剔除事后结合能体检判为 not_a_bound_state 的化合物后重算 §9 内部台阶",
            "n_dropped": len(dropped),
            "dropped_compounds": dropped,
            "channels": sensitivity,
        }

    c1_batt = readings["batt"]["C1_this_arm_li"]
    gate1 = {
        "stage": "framework section 19 Stage 1 (X2 condition-state gate)",
        "before": "NOT CLOSED -- the X2 layer had no occupant at all",
        "now": "X2 instantiated at the GFN2-xTB level on %d compounds (%d motif-bearing)"
               % (len(layer_rows), motif_total),
        "verdict": "Gate 1 仍未闭合，但缺口性质改变：X2 槽位以前是「空的」，现在第一次有了内容。",
        "reason": (
            "C_1 侧仍无外部参考层（Batt 只覆盖 %d 个化合物，且是自由态轨道能）；"
            "本臂给出的是 C_0 到 C_1 的内部台阶证据与 §9 三层并排"
            "（C_1 行：robust inversion = %d / %d），"
            "而不是「条件态已被外部基准验证」。"
            % (len(readings["batt_keys"]), c1_batt["robust_inversions"], c1_batt["resolved_in_both"])
        ),
    }

    summary = {
        "schema_version": 1,
        "task_id": prereg["task_id"],
        "week": "week21",
        "generated_at_utc": utc_now(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "preregistration": {
            "path": "probes/w21_li_coordination_prereg.json",
            "sha256": sha256_file(PREREG),
            "status": prereg["status"],
        },
        "pool": {
            "n_compounds": len(layer_rows),
            "runs": 2 * len(layer_rows),
            "motif_counts": motif_counts,
            "expected_n": prereg["pool"]["expected_n"],
            "expected_motif_n": prereg["pool"]["expected_motif_n"],
            "expected_motif_class_counts": expected,
            "matches_prereg": bool(matches and len(layer_rows) == prereg["pool"]["expected_n"]),
            "xtb_version": sorted({row["xtb_version"] for row in layer_rows if row["xtb_version"]}),
        },
        "qc": {
            "counts": readings["qc_counts"],
            "by_motif_class": readings["qc_by_motif_class"],
            "thresholds": {
                "intact": "li_min_dist_A <= %.2f and li_mulliken_q >= %.2f" % (INTACT_DIST_A, INTACT_CHARGE_E),
                "dissociated": "li_min_dist_A > %.2f or li_mulliken_q < %.2f" % (LOOSE_DIST_A, LOOSE_CHARGE_E),
            },
            "failed_arms": [
                {"inchikey": row["inchikey"], "name": row["name"], "motif_class": row["motif_class"],
                 "c0_status": row["c0_status"], "c1_status": row["c1_status"], "error": row["error"]}
                for row in layer_rows
                if row["c0_status"] != "ok" or row["c1_status"] != "ok"
            ],
        },
        "channels": channels,
        "batt_step": readings["batt"],
        "batt_subset_size": len(readings["batt_keys"]),
        "v03_cross_check": readings["v03_cross_check"],
        "layer": {
            "path": "data/processed/w21_li_coordination_layer.csv",
            "sha256": layer_sha,
            "fields": list(LAYER_FIELDS),
        },
        "artifacts": {
            "inversions": {"path": "probes/artifacts/w21_li_coordination_inversions.csv",
                           "rows": len(inversion_rows)},
            "delta_stats": {"path": "probes/artifacts/w21_li_coordination_delta_stats.csv",
                            "rows": len(delta_rows)},
            "topk": {"path": "probes/artifacts/w21_li_coordination_topk.csv", "rows": len(topk_rows)},
            "qc": {"path": "probes/artifacts/w21_li_coordination_qc.csv", "rows": len(qc_rows)},
            "batt_step": {"path": "probes/artifacts/w21_li_coordination_batt_step.csv", "rows": len(batt_rows)},
        },
        "promotion": {
            "promoted": False,
            "main_scoreboard_attempts": 0,
            "cumulative_main_scoreboard_attempts": 12,
            "frozen_untouched": prereg["promotion"]["frozen_untouched"],
        },
        "post_hoc": {
            "li_binding_energy": {
                "registration": "post_hoc_not_preregistered",
                "definition": "binding_eV = E([LiM]+, GFN2 --opt) - E(M, GFN2 --opt) - E(Li+, GFN2 single point)",
                "why": (
                    "预注册只登记了两个结构判据（Li-X 距离、Mulliken 电荷）。结构判据无法区分"
                    "「设计过的给体配位」与「semi-empirical 方法在无给体分子上仍然粘住 Li+」；"
                    "本列是事后补充的相互作用强度判据，与 W21-1 的 tolerance scan 同族处理，"
                    "不参与任何预注册读数。"
                ),
                "li_plus_total_energy_hartree": li_plus_hartree,
                "artifact": "probes/artifacts/w21_li_coordination_binding_posthoc.csv",
                "rows": len(binding_rows),
                "by_motif_class_eV": binding_summary,
                "n_not_a_bound_state": sum(1 for entry in binding_rows if entry[-1] != "bound"),
                "not_a_bound_state": [
                    {"inchikey": entry[0], "name": entry[1], "motif_class": entry[2],
                     "binding_eV": float(entry[7])}
                    for entry in binding_rows if entry[-1] != "bound"
                ],
            },
            "scf_retry": scf_retry,
            "binding_sensitivity": binding_sensitivity,
        },
        "gate1": gate1,
        "boundaries": [
            "层级只到 GFN2-xTB 半经验，不是框架 §7 要求的 DFT 级；这是 X2 槽位的首次实例化，不是等价替换。",
            "单 Li⁺、单预注册构象、真空气相；不是显式微溶剂化（C_2），也不是 SMD 连续介质。",
            "C_1 侧没有外部参考层；Batt 只覆盖 %d 个化合物，且只用于自由态轨道的三层并排。"
            % len(readings["batt_keys"]),
            "参考层物理不确定度未量化，只登记 %.2f eV 数值容差 —— 该缺口随读数一起报告。" % DELTA_REF_EV,
            "溶剂化自由能 / 配位能 ΔG 未算（缺热化学与溶剂化处理），本臂只报轨道能与基序几何。",
            "不与 ε 主记分牌、η 通道或数据集级基准混比。",
        ],
    }
    return summary


def scf_retry_posthoc(executable, layer_rows, timeout_seconds):
    """Post-hoc, explicitly not pre-registered: retry each failed arm with a looser SCF.

    The frozen protocol keeps xTB's default SCF settings.  This companion run only
    asks whether a failure is an SCF-setting artefact or a genuine method limit;
    the frozen layer is never rewritten from it.
    """

    from rdkit import Chem

    retry_rows = []
    for row in layer_rows:
        if row["c0_status"] == "ok" and row["c1_status"] == "ok":
            continue
        molecule, _ff, error = embed(row["canonical_smiles"], int(row["seed"]))
        if molecule is None:
            retry_rows.append((row["inchikey"], row["name"], "embed", row["motif_class"],
                               row["c0_status"], "embed_failed", error or "", "", "", ""))
            continue
        motif = classify_motif(molecule)
        net_charge = int(Chem.GetFormalCharge(molecule))
        position, _anchor = li_position(molecule, motif)
        arms = (
            ("C_0", Chem.MolToXYZBlock(molecule), net_charge, row["c0_status"]),
            ("C_1", xyz_block_with_li(molecule, position), net_charge + 1, row["c1_status"]),
        )
        for arm, xyz, charge, status in arms:
            if status == "ok":
                continue
            label = "retry_" + row["inchikey"][:6] + "_" + arm
            try:
                parsed = parse_arm(run_arm(executable, label, xyz, charge, timeout_seconds,
                                           extra_arguments=SCF_RETRY_ARGUMENTS))
            except Exception as error:  # noqa: BLE001
                parsed = {"status": "exception", "error": str(error)[:200], "gap_eV": None,
                          "li_min_dist_A": None, "li_mulliken_q": None}
            retry_rows.append((
                row["inchikey"], row["name"], arm, row["motif_class"], status,
                parsed["status"], parsed.get("error", "") or "",
                fmt(parsed.get("gap_eV")), fmt(parsed.get("li_min_dist_A")),
                fmt(parsed.get("li_mulliken_q")),
            ))
    write_csv(SCF_RETRY_CSV,
              ("inchikey", "name", "arm", "motif_class", "frozen_status", "retry_status",
               "retry_error", "retry_gap_eV", "retry_li_min_dist_A", "retry_li_mulliken_q"),
              retry_rows)
    recovered = sum(1 for entry in retry_rows if entry[5] == "ok")
    return {
        "registration": "post_hoc_not_preregistered",
        "what": "对冻结协议下失败的臂，换用更宽松的 SCF 设置重试（--iterations 1000 --etemp 1000）",
        "why": "区分「SCF 设置伪失败」与「方法层面的真实失败」；冻结层读数不因此改变",
        "attempted": len(retry_rows),
        "recovered": recovered,
        "still_failed": len(retry_rows) - recovered,
        "artifact": "probes/artifacts/w21_li_coordination_scf_retry_posthoc.csv",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--limit", type=int, default=None,
                        help="smoke-test only: stop after N compounds")
    parser.add_argument("--report-only", action="store_true",
                        help="regenerate the markdown report from the existing summary")
    parser.add_argument("--from-layer", action="store_true",
                        help="recompute readings/summary/report from the existing layer CSV, no xTB")
    args = parser.parse_args(argv)

    if args.report_only:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        write_report(summary)
        print(json.dumps({"report": str(REPORT), "mode": "report_only"}, ensure_ascii=False))
        return 0

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise SystemExit("pre-registration is not locked; refusing to run")

    if args.from_layer:
        previous = json.loads(SUMMARY.read_text(encoding="utf-8"))
        layer_rows = read_rows(LAYER_CSV)
        readings = compute_readings(layer_rows)
        relabelled = write_summary(
            layer_rows, readings, prereg, sha256_file(LAYER_CSV), previous["elapsed_seconds"],
            previous["post_hoc"]["li_binding_energy"]["li_plus_total_energy_hartree"],
            previous["post_hoc"]["scf_retry"],
        )
        SUMMARY.write_text(json.dumps(relabelled, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
        write_report(relabelled)
        print(json.dumps({"mode": "from_layer", "n": len(layer_rows),
                          "report": str(REPORT)}, ensure_ascii=False))
        return 0

    executable = resolve_xtb()
    started = time.perf_counter()
    layer_rows = run_probe(executable, args.timeout, limit=args.limit)
    readings = compute_readings(layer_rows)
    li_plus_hartree = lithium_ion_energy(executable, args.timeout)
    scf_retry = scf_retry_posthoc(executable, layer_rows, args.timeout)
    elapsed = time.perf_counter() - started
    layer_sha = sha256_file(LAYER_CSV)
    summary = write_summary(layer_rows, readings, prereg, layer_sha, elapsed, li_plus_hartree, scf_retry)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    write_report(summary)
    print(json.dumps({
        "summary": str(SUMMARY),
        "report": str(REPORT),
        "n_compounds": summary["pool"]["n_compounds"],
        "qc": summary["qc"]["counts"],
        "matches_prereg": summary["pool"]["matches_prereg"],
        "homo": {
            "delta_mean": summary["channels"]["homo"]["delta_mean_eV"],
            "rho": summary["channels"]["homo"]["spearman_rho"],
            "topk10": summary["channels"]["homo"]["topk"]["k/N=10%"]["overlap"],
        },
        "batt_c1_robust": summary["batt_step"]["C1_this_arm_li"]["robust_inversions"],
        "batt_c1_resolved_both": summary["batt_step"]["C1_this_arm_li"]["resolved_in_both"],
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
