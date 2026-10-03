# W24 -- Axis B C_1 redox arm and C_2 explicit-microsolvation arm first instantiation.
#
# Section 3.2 of the frozen framework defines two conditional-state rungs that this
# repository has never computed: C_1 (the [LiM]+ conditional state) carried by a *redox*
# quantity rather than an orbital energy, and C_2 (an explicit microsolvation state).
# The Week 21 C_1 layer is orbital-only, so the framework quantity
#
#     DDG_ox^coord = DG_ox^Li - DG_ox^free ,  DDG_red^coord = DG_red^Li - DG_red^free
#
# has never had a value here.  This arm fills both slots and, because the frozen roster
# holds 246 compounds, it also scales the parent paper ladder (N = 18, C-rungs N = 10-12)
# by a factor of 13.7.
#
# Discipline: no frozen reading moves, no main-scoreboard shot is taken (cumulative 12),
# no Reaxys number is used, and the reference layers (RX-392, Batt-P30K) are not touched.
# The frozen closed-shell argument builder is untouched: open-shell states go through
# electrolyte_ml.xtb_runner.xtb_open_shell_arguments.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))
import w21_li_coordination as w21
import w23_redox_dscf as w23
from export_results_common import write_json_stable

from electrolyte_ml.xtb_runner import (
    xtb_open_shell_arguments,
)

PREREG = ROOT / "probes" / "w24_condition_redox_prereg.json"
SUMMARY = ROOT / "probes" / "w24_condition_redox_summary.json"
LAYER_CSV = ROOT / "data" / "processed" / "w24_condition_redox_layer.csv"
C1_LAYER = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
MEDIUM_LAYER = ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv"
DSCF_LAYER = ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
ARTIFACTS = ROOT / "probes" / "artifacts"
REPORT = ROOT / "reports" / "w24_condition_redox.md"

HARTREE_TO_EV = 27.211386245988
MEDIA = (
    ("gas", None, 1.0),
    ("thf", "thf", 7.58),
    ("benzaldehyde", "benzaldehyde", 18.0),
    ("water", "water", 80.4),
)
COMPLEXES = (("c1", 1), ("c2", 2))
STATES = (("cation", 1, 1), ("ref", 0, 0), ("reduced", -1, 1))
ARM_KEYS = tuple(
    complex_key + "_" + medium + "_" + state
    for complex_key, _ligands in COMPLEXES
    for medium, _solvent, _eps in MEDIA
    for state, _dq, _uhf in STATES
)
CHARGE_STATES = (("neutral", 0), ("cation", 1), ("anion", -1))

H2_THRESHOLD_E = 0.5
H2_SHARE = 0.50
H3_TOLERANCE = 1e-9
H4_RHO = -0.5
H5_R2 = 0.90
H5_SHARE = 0.70
H6_SD_LO = 0.06
H6_SD_HI = 0.25
H7_TOL_HARTREE = 1e-9
H7_TOL_EV = 1e-6
H8_DONOR_MAX_A = 3.2
H8_INTER_MIN_A = 1.3
H8_SHARE = 0.70
H9_TAU_MIN = 0.20
H9_OX_MIN = 0.40
H9_RED_MAX = 0.40
Z_RULES = ((1.0, "z=1"), (1.96, "z=1.96"))
DELTA_REF_EV = 0.05
BOOTSTRAP_B = 5000
SEED = 20261002
SUBSAMPLE_N = (10, 18, 25, 49, 100, 246)
SUBSAMPLE_DRAWS = 2000
TOPK_RULES = (("k/N=10%", 0.10), ("k/N=20%", 0.20), ("k/N=30%", 0.30))
PAPER_TABLE2 = (
    ("P0->P1", "ox", -1.550, 0.735, 0.673, 0.157),
    ("P0->P1", "red", 7.592, 2.209, 0.595, 0.621),
    ("P1->P2", "ox", -2.393, 0.302, 0.895, 0.111),
    ("P1->P2", "red", -2.173, 0.321, 0.673, 0.222),
    ("G1->G2", "ox", -0.002, 0.052, 0.939, 0.030),
    ("G1->G2", "red", -0.118, 0.080, 0.848, 0.061),
    ("C0->C1", "ox", 4.887, 0.595, 0.689, 0.200),
    ("C0->C1", "red", -6.578, 0.832, -0.467, 0.800),
    ("C1->C2", "ox", -1.700, 0.259, 0.867, 0.089),
    ("C1->C2", "red", 1.199, 0.335, 0.289, 0.356),
)



def utc_now():
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fmt(value, digits=12):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return ("%." + str(int(digits)) + "f") % float(value)


def as_float(value):
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# geometry: the C_1 motif (reused) and the C_2 antipodal 2:1 construction (new)
# --------------------------------------------------------------------------- #

def parse_xyz_atoms(text):
    """Return [(symbol, xyz)] for an xTB/XYZ block, or None."""

    if not text:
        return None
    lines = text.splitlines()
    if not lines:
        return None
    try:
        count = int(lines[0].split()[0])
    except (IndexError, ValueError):
        return None
    atoms = []
    for line in lines[2:2 + count]:
        parts = line.split()
        if len(parts) >= 4:
            atoms.append((parts[0], np.array([float(parts[1]), float(parts[2]), float(parts[3])])))
    return atoms if len(atoms) == count else None


def dimer_xyz(molecule, lithium_position):
    """Pre-registered antipodal 2:1 construction.

    Ligand A is the embedded molecule, placed verbatim.  Ligand B is ligand A
    reflected through the lithium start position, so that its donor lone pair
    points back at the metal and the two ligands sit anti to one another.
    The lithium is appended last so that the frozen atom-order convention of
    w21_li_coordination (Li is the last atom, hence the last line of the xTB
    `charges` file) carries over unchanged.
    """

    from rdkit import Chem

    lines = Chem.MolToXYZBlock(molecule).rstrip(chr(10)).split(chr(10))
    ligand_lines = lines[2:2 + int(lines[0].split()[0])]
    mirror = [2.0 * float(lithium_position[0]), 2.0 * float(lithium_position[1]),
              2.0 * float(lithium_position[2])]
    reflected = []
    for line in ligand_lines:
        parts = line.split()
        coords = [mirror[axis] - float(parts[axis + 1]) for axis in range(3)]
        reflected.append("%-2s % .6f % .6f % .6f" % (parts[0], coords[0], coords[1], coords[2]))
    body = [str(2 * len(ligand_lines) + 1), "w24 antipodal 2:1 dimer"] + ligand_lines + reflected
    body.append("Li  % .6f % .6f % .6f" % (float(lithium_position[0]),
                                            float(lithium_position[1]),
                                            float(lithium_position[2])))
    return chr(10).join(body) + chr(10)


def donor_distance(result, atom_index):
    """Distance from the last atom (Li) to atom_index in the optimised geometry."""

    atoms = parse_xyz_atoms(result.get("optimized_xyz"))
    if not atoms or atom_index < 0 or atom_index >= len(atoms) - 1:
        return None
    if atoms[-1][0] != "Li":
        return None
    return float(np.linalg.norm(atoms[-1][1] - atoms[atom_index][1]))


def inter_ligand_min(atoms, ligand_atoms):
    """Minimum heavy-atom distance between ligand A and ligand B."""

    if not atoms or ligand_atoms <= 0 or len(atoms) < 2 * ligand_atoms + 1:
        return None
    first = [position for symbol, position in atoms[:ligand_atoms] if symbol != "H"]
    second = [position for symbol, position in atoms[ligand_atoms:2 * ligand_atoms] if symbol != "H"]
    if not first or not second:
        return None
    best = None
    for left in first:
        for right in second:
            distance = float(np.linalg.norm(left - right))
            if best is None or distance < best:
                best = distance
    return best


def geometry_probe(result, complex_key, ligand_atoms, donor_index):
    """Per-arm geometry QC: donor distances and, for C_2, the inter-ligand gap."""

    payload = {
        "li_donor_a_A": donor_distance(result, donor_index),
        "li_donor_b_A": donor_distance(result, ligand_atoms + donor_index)
        if complex_key == "c2" else None,
        "inter_ligand_min_A": None,
        "geom_qc": "",
    }
    atoms = parse_xyz_atoms(result.get("optimized_xyz"))
    if complex_key == "c2":
        payload["inter_ligand_min_A"] = inter_ligand_min(atoms, ligand_atoms)
    first = payload["li_donor_a_A"]
    if first is None:
        payload["geom_qc"] = "not_available"
        return payload
    if complex_key == "c1":
        payload["geom_qc"] = "intact" if first <= H8_DONOR_MAX_A else "loose"
        return payload
    second = payload["li_donor_b_A"]
    gap = payload["inter_ligand_min_A"]
    if second is None or gap is None:
        payload["geom_qc"] = "not_available"
    elif first <= H8_DONOR_MAX_A and second <= H8_DONOR_MAX_A and gap >= H8_INTER_MIN_A:
        payload["geom_qc"] = "intact"
    else:
        payload["geom_qc"] = "broken"
    return payload



# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

def empty_arm(status, error=""):
    return {
        "status": status, "homo_eV": None, "lumo_eV": None, "gap_eV": None,
        "total_E_hartree": None, "xtb_version": None, "li_mulliken_q": None,
        "li_min_dist_A": None, "li_nearest_atom": None,
        "li_donor_a_A": None, "li_donor_b_A": None, "inter_ligand_min_A": None,
        "geom_qc": "", "error": error[:200], "seconds": 0.0,
    }


def run_compound(payload):
    index, name, smiles, executable, timeout_seconds = payload
    from rdkit import Chem

    record = {
        "row_index": index, "name": name, "canonical_smiles": smiles,
        "arms": {}, "error": "", "ff_status": "", "formal_charge": "",
        "motif_class": "", "donor_index": -1, "donor_symbol": "", "donor_anchor": "",
        "ligand_atoms": 0, "seconds_total": 0.0,
    }
    molecule, ff_status, error = w21.embed(smiles, 42 + index)
    if molecule is None:
        record["error"] = error or "embed_failed"
        return record
    record["ff_status"] = ff_status
    net_charge = int(Chem.GetFormalCharge(molecule))
    record["formal_charge"] = net_charge
    motif = w21.classify_motif(molecule)
    donor_index = int(motif.get("donor_index", -1))
    record["motif_class"] = motif.get("motif_class", "")
    record["donor_index"] = donor_index
    record["ligand_atoms"] = int(molecule.GetNumAtoms())
    if donor_index >= 0:
        record["donor_symbol"] = molecule.GetAtomWithIdx(donor_index).GetSymbol()
    lithium_position, anchor = w21.li_position(molecule, motif)
    record["donor_anchor"] = anchor
    c1_xyz = w21.xyz_block_with_li(molecule, lithium_position) if donor_index >= 0 else None
    c2_xyz = dimer_xyz(molecule, lithium_position) if donor_index >= 0 else None
    for complex_key, _ligands in COMPLEXES:
        xyz_text = c1_xyz if complex_key == "c1" else c2_xyz
        for medium, solvent, _epsilon in MEDIA:
            for state, delta_q, unpaired in STATES:
                arm_key = complex_key + "_" + medium + "_" + state
                if xyz_text is None:
                    record["arms"][arm_key] = empty_arm("no_motif", "classify_motif returned no donor")
                    continue
                label = "c%03d_%s_%s_%s" % (index, complex_key, medium, state)
                try:
                    result = w23.run_arm(executable, label, xyz_text, net_charge + 1 + delta_q,
                                         unpaired, solvent, timeout_seconds)
                    parsed = w23.parse_arm(result)
                    parsed.update(geometry_probe(result, complex_key, record["ligand_atoms"],
                                                donor_index))
                    record["arms"][arm_key] = parsed
                except Exception as exc:
                    record["arms"][arm_key] = empty_arm("exception", str(exc))
    record["seconds_total"] = float(
        sum((arm.get("seconds") or 0.0) for arm in record["arms"].values())
    )
    return record


# --------------------------------------------------------------------------- #
# layer assembly
# --------------------------------------------------------------------------- #

def layer_fields():
    fields = [
        "inchikey", "name", "canonical_smiles", "row_index", "seed", "formal_charge",
        "charge_class", "motif_class", "donor_symbol", "donor_index", "donor_anchor",
        "ff_status",
    ]
    for arm in ARM_KEYS:
        fields += [arm + "_homo_eV", arm + "_lumo_eV", arm + "_gap_eV",
                   arm + "_total_E_hartree", arm + "_li_q", arm + "_status"]
    for complex_key, _ligands in COMPLEXES:
        for medium, _solvent, _epsilon in MEDIA:
            fields += [complex_key + "_" + medium + "_ip_eV",
                       complex_key + "_" + medium + "_ea_eV"]
            fields += [complex_key + "_" + medium + "_li_donor_a_A",
                       complex_key + "_" + medium + "_li_donor_b_A",
                       complex_key + "_" + medium + "_inter_ligand_min_A",
                       complex_key + "_" + medium + "_geom_qc"]
    fields += ["anchor_delta_hartree", "anchor_delta_homo_eV", "anchor_delta_lumo_eV",
               "seconds_total", "error"]
    return fields


LAYER_FIELDS = layer_fields()


def build_layer_rows(records, meta_rows, c1_reference):
    rows = []
    for record in sorted(records, key=lambda item: item.get("row_index", 0)):
        row = {field: "" for field in LAYER_FIELDS}
        index = int(record.get("row_index", 0))
        meta = meta_rows[index] if index < len(meta_rows) else {}
        row["inchikey"] = str(meta.get("molecule_id") or meta.get("inchikey") or "")
        row["name"] = record.get("name") or meta.get("name") or ""
        row["canonical_smiles"] = record.get("canonical_smiles") or ""
        row["row_index"] = index
        row["seed"] = 42 + index
        row["formal_charge"] = record.get("formal_charge", "")
        net = record.get("formal_charge")
        row["charge_class"] = "neutral" if net == 0 else ("charged" if isinstance(net, int) else "")
        row["motif_class"] = record.get("motif_class", "")
        row["donor_symbol"] = record.get("donor_symbol", "")
        row["donor_index"] = record.get("donor_index", "")
        row["donor_anchor"] = record.get("donor_anchor", "")
        row["ff_status"] = record.get("ff_status", "")
        row["error"] = record.get("error") or ""
        row["seconds_total"] = fmt(record.get("seconds_total") or 0.0, 6)
        arms = record.get("arms") or {}
        version = ""
        for arm_key in ARM_KEYS:
            payload = arms.get(arm_key) or empty_arm("not_computed")
            row[arm_key + "_homo_eV"] = fmt(payload.get("homo_eV"))
            row[arm_key + "_lumo_eV"] = fmt(payload.get("lumo_eV"))
            row[arm_key + "_gap_eV"] = fmt(payload.get("gap_eV"))
            row[arm_key + "_total_E_hartree"] = fmt(payload.get("total_E_hartree"))
            row[arm_key + "_li_q"] = fmt(payload.get("li_mulliken_q"))
            row[arm_key + "_status"] = payload.get("status") or "not_computed"
            if payload.get("xtb_version"):
                version = payload["xtb_version"]
            if payload.get("error"):
                row["error"] = (row["error"] + " | " + str(payload["error"]))[:300].strip(" |")
        row["xtb_version"] = ""
        for complex_key, _ligands in COMPLEXES:
            for medium, _solvent, _epsilon in MEDIA:
                ref = arms.get(complex_key + "_" + medium + "_ref") or {}
                cation = arms.get(complex_key + "_" + medium + "_cation") or {}
                reduced = arms.get(complex_key + "_" + medium + "_reduced") or {}
                e_ref = as_float(ref.get("total_E_hartree"))
                e_cation = as_float(cation.get("total_E_hartree"))
                e_reduced = as_float(reduced.get("total_E_hartree"))
                prefix = complex_key + "_" + medium + "_"
                if ref.get("status") == "ok" and cation.get("status") == "ok" \
                        and e_ref is not None and e_cation is not None:
                    row[prefix + "ip_eV"] = fmt((e_cation - e_ref) * HARTREE_TO_EV)
                if ref.get("status") == "ok" and reduced.get("status") == "ok" \
                        and e_ref is not None and e_reduced is not None:
                    row[prefix + "ea_eV"] = fmt((e_ref - e_reduced) * HARTREE_TO_EV)
                for key in ("li_donor_a_A", "li_donor_b_A", "inter_ligand_min_A"):
                    row[prefix + key] = fmt(ref.get(key))
                row[prefix + "geom_qc"] = ref.get("geom_qc") or ""
        row["xtb_version"] = version
        previous = c1_reference.get(row["inchikey"]) or {}
        anchor = previous.get("total_energy_li_hartree")
        own = as_float(row["c1_gas_ref_total_E_hartree"])
        if anchor not in (None, "") and own is not None:
            row["anchor_delta_hartree"] = fmt(own - float(anchor))
        for channel, reference_key in (("homo", "homo_li_eV"), ("lumo", "lumo_li_eV")):
            reference = previous.get(reference_key)
            mine = as_float(row["c1_gas_ref_" + channel + "_eV"])
            if reference not in (None, "") and mine is not None:
                row["anchor_delta_" + channel + "_eV"] = fmt(mine - float(reference))
        rows.append(row)
    return rows



# --------------------------------------------------------------------------- #
# the ladder: axis tables, rungs, metrics
# --------------------------------------------------------------------------- #

# Each rung changes exactly one thing.  source/target are axis keys resolved by
# build_axes; the trailing field maps the rung onto the parent paper table 2 row.
RUNGS = (
    ("P0->P1", "method: Koopmans -> dSCF, same GFN2 Hamiltonian",
     "free_ox_orb_gas", "free_ox_dscf_gas", "free_red_orb_gas", "free_red_dscf_gas", "P0->P1"),
    ("P1->P2_thf", "environment: gas -> ALPB thf",
     "free_ox_dscf_gas", "free_ox_dscf_thf", "free_red_dscf_gas", "free_red_dscf_thf", "P1->P2"),
    ("P1->P2_benzaldehyde", "environment: gas -> ALPB benzaldehyde",
     "free_ox_dscf_gas", "free_ox_dscf_benzaldehyde", "free_red_dscf_gas",
     "free_red_dscf_benzaldehyde", "P1->P2"),
    ("P1->P2_water", "environment: gas -> ALPB water",
     "free_ox_dscf_gas", "free_ox_dscf_water", "free_red_dscf_gas", "free_red_dscf_water", "P1->P2"),
    ("P0->P2orb_thf", "method + environment: gas Koopmans -> ALPB thf orbital",
     "free_ox_orb_gas", "free_ox_orb_thf", "free_red_orb_gas", "free_red_orb_thf", None),
    ("C0->C1_orb", "conditional state on the orbital axis (W21 carrier)",
     "free_ox_orb_gas", "c1_ox_orb_gas", "free_red_orb_gas", "c1_red_orb_gas", "C0->C1"),
    ("C0->C1_dscf_gas", "conditional state on the redox axis, gas (this arm)",
     "free_ox_dscf_gas", "c1_ox_dscf_gas", "free_red_dscf_gas", "c1_red_dscf_gas", "C0->C1"),
    ("C0->C1_dscf_thf", "conditional state on the redox axis, ALPB thf (this arm)",
     "free_ox_dscf_thf", "c1_ox_dscf_thf", "free_red_dscf_thf", "c1_red_dscf_thf", "C0->C1"),
    ("C0->C1_dscf_benzaldehyde", "conditional state on the redox axis, ALPB benzaldehyde",
     "free_ox_dscf_benzaldehyde", "c1_ox_dscf_benzaldehyde", "free_red_dscf_benzaldehyde",
     "c1_red_dscf_benzaldehyde", "C0->C1"),
    ("C0->C1_dscf_water", "conditional state on the redox axis, ALPB water",
     "free_ox_dscf_water", "c1_ox_dscf_water", "free_red_dscf_water", "c1_red_dscf_water", "C0->C1"),
    ("C1->C2_dscf_gas", "second shell on the redox axis, gas (this arm)",
     "c1_ox_dscf_gas", "c2_ox_dscf_gas", "c1_red_dscf_gas", "c2_red_dscf_gas", "C1->C2"),
    ("C1->C2_dscf_thf", "second shell on the redox axis, ALPB thf (this arm)",
     "c1_ox_dscf_thf", "c2_ox_dscf_thf", "c1_red_dscf_thf", "c2_red_dscf_thf", "C1->C2"),
    ("C1->C2_dscf_benzaldehyde", "second shell on the redox axis, ALPB benzaldehyde",
     "c1_ox_dscf_benzaldehyde", "c2_ox_dscf_benzaldehyde", "c1_red_dscf_benzaldehyde",
     "c2_red_dscf_benzaldehyde", "C1->C2"),
    ("C1->C2_dscf_water", "second shell on the redox axis, ALPB water",
     "c1_ox_dscf_water", "c2_ox_dscf_water", "c1_red_dscf_water", "c2_red_dscf_water", "C1->C2"),
)

PRIMARY_RUNGS = ("P0->P1", "P1->P2_water", "P0->P2orb_thf", "C0->C1_orb",
                 "C0->C1_dscf_gas", "C1->C2_dscf_gas")


def build_axes(layer_rows, dscf_rows, medium_rows):
    """Resolve every ladder axis key for every compound, or None where undefined."""

    dscf = {row.get("inchikey"): row for row in dscf_rows}
    medium_layer = {row.get("inchikey"): row for row in medium_rows}
    axes = {}
    for row in layer_rows:
        key = row.get("inchikey")
        if not key:
            continue
        free_dscf = dscf.get(key) or {}
        free_orb = medium_layer.get(key) or {}
        entry = {}
        for medium, _solvent, _epsilon in MEDIA:
            homo = as_float(free_orb.get("gas_free_homo_eV" if medium == "gas"
                                           else "free_" + medium + "_homo_eV"))
            lumo = as_float(free_orb.get("gas_free_lumo_eV" if medium == "gas"
                                           else "free_" + medium + "_lumo_eV"))
            if homo is not None:
                entry["free_ox_orb_" + medium] = -homo
            if lumo is not None:
                entry["free_red_orb_" + medium] = lumo
            ip = as_float(free_dscf.get("ip_" + medium + "_eV"))
            ea = as_float(free_dscf.get("ea_" + medium + "_eV"))
            if ip is not None:
                entry["free_ox_dscf_" + medium] = ip
            if ea is not None:
                entry["free_red_dscf_" + medium] = -ea
        li_homo = as_float(free_orb.get("gas_li_homo_eV"))
        li_lumo = as_float(free_orb.get("gas_li_lumo_eV"))
        if li_homo is not None:
            entry["c1_ox_orb_gas"] = -li_homo
        if li_lumo is not None:
            entry["c1_red_orb_gas"] = li_lumo
        for complex_key, _ligands in COMPLEXES:
            for medium, _solvent, _epsilon in MEDIA:
                ip = as_float(row.get(complex_key + "_" + medium + "_ip_eV"))
                ea = as_float(row.get(complex_key + "_" + medium + "_ea_eV"))
                if ip is not None:
                    entry[complex_key + "_ox_dscf_" + medium] = ip
                if ea is not None:
                    entry[complex_key + "_red_dscf_" + medium] = -ea
        axes[key] = entry
    return axes


def pair_arrays(axes, source_key, target_key):
    source, target, keys = [], [], []
    for key in sorted(axes):
        entry = axes[key]
        left, right = entry.get(source_key), entry.get(target_key)
        if left is None or right is None:
            continue
        source.append(left)
        target.append(right)
        keys.append(key)
    return np.asarray(source, dtype=float), np.asarray(target, dtype=float), keys


def topk_set(values, k):
    order = sorted(range(len(values)), key=lambda index: (-float(values[index]), index))
    return set(order[:k])


def rung_metrics(source, target):
    from scipy import stats

    n = int(source.size)
    shift = target - source
    payload = {
        "n": n,
        "mean_shift_eV": float(shift.mean()),
        "std_shift_eV": float(shift.std(ddof=1)) if n > 1 else 0.0,
        "mean_abs_shift_eV": float(np.abs(shift).mean()),
        "tau_b": float(stats.kendalltau(source, target, variant="b").statistic),
        "spearman_rho": float(stats.spearmanr(source, target).statistic),
        "pearson_r": float(stats.pearsonr(source, target).statistic),
    }
    iu = np.triu_indices(n, 1)
    gap = np.abs(target[:, None] - target[None, :])[iu]
    spread = np.abs(shift[:, None] - shift[None, :])[iu]
    sigma = spread / np.sqrt(2.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(spread <= 0.0, 0.0,
                         np.where(gap > 0.0, spread / np.where(gap > 0.0, gap, 1.0), np.inf))
    payload["pairs"] = int(gap.size)
    payload["sigma_mean_eV"] = float(sigma.mean())
    payload["pair_gap_median_eV"] = float(np.median(gap))
    payload["q_mean"] = float(np.mean(ratio[np.isfinite(ratio)])) if np.any(np.isfinite(ratio)) else float("inf")
    payload["q_p95"] = float(np.percentile(ratio[np.isfinite(ratio)], 95)) if np.any(np.isfinite(ratio)) else float("inf")
    for z, label in Z_RULES:
        direct = gap < z * sigma
        closed = ratio > (np.sqrt(2.0) / z)
        payload["f_unresolved_" + label] = float(direct.mean())
        payload["f_unresolved_closed_" + label] = float(closed.mean())
        payload["closed_form_max_abs_diff_" + label] = float(
            np.max(np.abs(direct.astype(float) - closed.astype(float)))
        )
    payload["f_unresolved_delta_0.05eV"] = float((gap < DELTA_REF_EV).mean())
    signed_source = np.sign(source[:, None] - source[None, :])[iu]
    signed_target = np.sign(target[:, None] - target[None, :])[iu]
    resolved_both = (np.abs(source[:, None] - source[None, :])[iu] >= DELTA_REF_EV) & (gap >= DELTA_REF_EV)
    flips = resolved_both & (signed_source != signed_target)
    payload["pairs_resolved_both"] = int(resolved_both.sum())
    payload["robust_inversions"] = int(flips.sum())
    payload["f_robust_inversion"] = (
        float(flips.sum() / resolved_both.sum()) if resolved_both.sum() else 0.0
    )
    payload["topk"] = {}
    for label, fraction in TOPK_RULES:
        k = max(1, int(round(fraction * n)))
        left, right = topk_set(source, k), topk_set(target, k)
        payload["topk"][label] = {
            "k": int(k), "overlap": len(left & right) / k,
            "jaccard": len(left & right) / len(left | right),
            "entered": len(right - left), "left": len(left - right),
        }
    return payload


def bootstrap_rung(source, target, draws, seed):
    from scipy import stats

    rng = np.random.default_rng(seed)
    n = int(source.size)
    tau, rho = [], []
    for _ in range(draws):
        index = rng.integers(0, n, n)
        if np.unique(index).size < 5:
            continue
        tau.append(float(stats.kendalltau(source[index], target[index], variant="b").statistic))
        rho.append(float(stats.spearmanr(source[index], target[index]).statistic))
    def interval(values):
        if not values:
            return {"lo": float("nan"), "median": float("nan"), "hi": float("nan"), "draws_used": 0}
        lo, med, hi = np.percentile(values, [2.5, 50, 97.5])
        return {"lo": float(lo), "median": float(med), "hi": float(hi), "draws_used": len(values)}
    return {"tau_b": interval(tau), "spearman_rho": interval(rho)}


def subsample_tau_sd(source, target, sizes, draws, seed):
    from scipy import stats

    rng = np.random.default_rng(seed)
    n = int(source.size)
    out = {}
    for size in sizes:
        if size > n:
            continue
        values = []
        for _ in range(draws):
            index = rng.choice(n, size=size, replace=False)
            values.append(float(stats.kendalltau(source[index], target[index], variant="b").statistic))
        out["N=%d" % size] = {
            "draws": int(draws), "mean": float(np.mean(values)),
            "sd": float(np.std(values, ddof=1)),
            "p2_5": float(np.percentile(values, 2.5)),
            "p97_5": float(np.percentile(values, 97.5)),
        }
        if size == n:
            break
    return out



# --------------------------------------------------------------------------- #
# cross-layer readings: Born law, state identity, anchors, gap map
# --------------------------------------------------------------------------- #

def born_fit(energies, epsilons):
    """One-parameter Born fit y = -C (1 - 1/eps), y anchored at the gas energy."""

    values = np.asarray(energies, dtype=float)
    if not np.all(np.isfinite(values)):
        return None
    y = values - values[0]
    x = 1.0 - 1.0 / np.asarray(epsilons, dtype=float)
    denom = float(np.dot(x, x))
    if denom <= 0.0:
        return None
    c = -float(np.dot(x, y)) / denom
    predicted = -c * x
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "C_eV": c,
        "r2": (1.0 - ss_res / ss_tot) if ss_tot > 0.0 else float("nan"),
        "ss_res": ss_res,
        "residual_at_max_eps_eV": abs(c) / max(float(epsilons[-1]), 1.0),
        "dE_times_eps_max_eV": float(np.max(np.abs(y) * np.asarray(epsilons, dtype=float))),
    }


def born_law(dscf_rows):
    """H5: does the free-molecule solvation energy follow Born on four eps points?"""

    epsilons = [item[2] for item in MEDIA]
    curves = []
    for row in dscf_rows:
        for state, _delta in CHARGE_STATES:
            energies = []
            for medium, _solvent, _epsilon in MEDIA:
                energies.append(as_float(row.get(medium + "_" + state + "_total_E_hartree")))
            if any(value is None for value in energies):
                continue
            converted = [value * HARTREE_TO_EV for value in energies]
            fit = born_fit(converted, epsilons)
            if fit is None:
                continue
            fit["inchikey"] = row.get("inchikey")
            fit["name"] = row.get("name")
            fit["charge_state"] = state
            curves.append(fit)
    if not curves:
        return {"n_curves": 0, "share_r2_ge_threshold": 0.0, "verdict": "no_data", "curves": []}
    values = np.asarray([curve["r2"] for curve in curves], dtype=float)
    finite = values[np.isfinite(values)]
    share = float(np.mean(finite >= H5_R2)) if finite.size else 0.0
    ions = [curve for curve in curves if curve["charge_state"] in ("cation", "anion")]
    ion_values = np.asarray([curve["r2"] for curve in ions], dtype=float)
    ion_finite = ion_values[np.isfinite(ion_values)]
    return {
        "n_curves": len(curves),
        "r2_mean": float(np.mean(finite)) if finite.size else float("nan"),
        "r2_median": float(np.median(finite)) if finite.size else float("nan"),
        "r2_p05": float(np.percentile(finite, 5)) if finite.size else float("nan"),
        "share_r2_ge_threshold": share,
        "threshold": H5_R2,
        "n_ion_curves": len(ions),
        "ion_r2_mean": float(np.mean(ion_finite)) if ion_finite.size else float("nan"),
        "ion_share_r2_ge_threshold": float(np.mean(ion_finite >= H5_R2)) if ion_finite.size else 0.0,
        "c_eV_mean": float(np.mean([abs(curve["C_eV"]) for curve in curves])),
        "residual_at_max_eps_mean_eV": float(np.mean(
            [curve["residual_at_max_eps_eV"] for curve in curves]
        )),
        "residual_at_eps200_mean_eV": float(np.mean([abs(curve["C_eV"]) / 200.0 for curve in curves])),
        "residual_at_eps200_max_eV": float(np.max([abs(curve["C_eV"]) / 200.0 for curve in curves])),
        "verdict": "成立" if share >= H5_SHARE else "判否",
        "curves": curves,
    }



def state_identity(layer_rows):
    """H2: does the extra electron of the reduced complex sit on Li?"""

    entries = []
    for complex_key, _ligands in COMPLEXES:
        for medium, _solvent, _epsilon in MEDIA:
            deltas = []
            removed = []
            for row in layer_rows:
                ref = as_float(row.get(complex_key + "_" + medium + "_ref_li_q"))
                reduced = as_float(row.get(complex_key + "_" + medium + "_reduced_li_q"))
                cation = as_float(row.get(complex_key + "_" + medium + "_cation_li_q"))
                if ref is not None and reduced is not None:
                    deltas.append(ref - reduced)
                if ref is not None and cation is not None:
                    removed.append(ref - cation)
            share = float(np.mean(np.asarray(deltas) >= H2_THRESHOLD_E)) if deltas else 0.0
            entries.append({
                "complex": complex_key, "medium": medium, "n": len(deltas),
                "mean_delta_q_e": float(np.mean(deltas)) if deltas else float("nan"),
                "share_ge_threshold": share, "threshold_e": H2_THRESHOLD_E,
                "n_cation_pairs": len(removed),
                "mean_delta_q_cation_e": float(np.mean(removed)) if removed else float("nan"),
                "share_cation_ge_threshold": float(
                    np.mean(np.asarray(removed) >= H2_THRESHOLD_E)
                ) if removed else 0.0,
                "verdict": "成立" if share >= H2_SHARE else "判否",
            })
    gas = [entry for entry in entries if entry["medium"] == "gas"]
    return {
        "entries": entries,
        "gas_complex_share": {entry["complex"]: entry["share_ge_threshold"] for entry in gas},
        "verdict": "成立" if all(entry["share_ge_threshold"] >= H2_SHARE for entry in gas)
                   else "部分成立" if any(entry["share_ge_threshold"] >= H2_SHARE for entry in gas)
                   else "判否",
    }


def anchors(layer_rows, medium_rows):
    """H7: the C_1 reference state must reproduce the frozen Week 21 layer."""

    hartree, homo, lumo = [], [], []
    for row in layer_rows:
        for value, bucket in (("anchor_delta_hartree", hartree),
                              ("anchor_delta_homo_eV", homo),
                              ("anchor_delta_lumo_eV", lumo)):
            parsed = as_float(row.get(value))
            if parsed is not None:
                bucket.append(abs(parsed))
    previous = {row.get("inchikey"): row for row in medium_rows}
    orbital, orbital_pairs = [], 0
    for row in layer_rows:
        reference = previous.get(row.get("inchikey")) or {}
        for channel, key in (("homo", "gas_li_homo_eV"), ("lumo", "gas_li_lumo_eV")):
            mine = as_float(row.get("c1_gas_ref_" + channel + "_eV"))
            theirs = as_float(reference.get(key))
            if mine is not None and theirs is not None:
                orbital.append(abs(mine - theirs))
                orbital_pairs += 1
    return {
        "n_hartree_pairs": len(hartree),
        "max_abs_delta_hartree": max(hartree) if hartree else None,
        "tolerance_hartree": H7_TOL_HARTREE,
        "n_orbital_pairs": orbital_pairs,
        "max_abs_delta_orbital_eV": max(orbital) if orbital else None,
        "tolerance_eV": H7_TOL_EV,
        "verdict": "成立" if (hartree and max(hartree) <= H7_TOL_HARTREE
                             and orbital and max(orbital) <= H7_TOL_EV)
                   else ("部分成立" if hartree and max(hartree) <= H7_TOL_HARTREE else "判否"),
    }


def c2_qc(layer_rows):
    """H8: does the antipodal 2:1 construction survive the optimisation?"""

    entries = []
    for medium, _solvent, _epsilon in MEDIA:
        states = Counter()
        for row in layer_rows:
            states[row.get("c2_" + medium + "_geom_qc") or "not_available"] += 1
        total = max(1, sum(value for key, value in states.items() if key != "not_available"))
        share = states["intact"] / total if total else 0.0
        entries.append({
            "medium": medium, "counts": dict(states), "denominator": total,
            "share_intact": share, "threshold": H8_SHARE,
            "verdict": "成立" if share >= H8_SHARE else "判否",
        })
    return {
        "entries": entries,
        "verdict": "成立" if all(entry["share_intact"] >= H8_SHARE for entry in entries)
                   else "判否",
    }


def paper_gap_map(rung_table):
    """R5: our rungs against the parent paper table 2, three axes at a time."""

    paper = {}
    for name, axis, mean, std, tau, unresolved in PAPER_TABLE2:
        paper.setdefault(name, {})[axis] = {
            "mean_shift_eV": mean, "std_shift_eV": std, "tau_b": tau,
            "f_unresolved": unresolved,
        }
    entries = []
    for entry in rung_table:
        maps_to = entry.get("maps_to_paper")
        if not maps_to:
            continue
        reference = (paper.get(maps_to) or {}).get(entry["axis"])
        if not reference:
            continue
        entries.append({
            "our_rung": entry["rung"], "axis": entry["axis"], "paper_rung": maps_to,
            "our_mean_shift_eV": entry["mean_shift_eV"],
            "our_std_shift_eV": entry["std_shift_eV"],
            "our_tau_b": entry["tau_b"],
            "our_f_unresolved": entry["f_unresolved_z=1.96"],
            "paper_mean_shift_eV": reference["mean_shift_eV"],
            "paper_std_shift_eV": reference["std_shift_eV"],
            "paper_tau_b": reference["tau_b"],
            "paper_f_unresolved": reference["f_unresolved"],
            "sign_agrees": (entry["mean_shift_eV"] > 0) == (reference["mean_shift_eV"] > 0),
            "tau_sign_agrees": (entry["tau_b"] > 0) == (reference["tau_b"] > 0),
            "delta_tau_b": entry["tau_b"] - reference["tau_b"],
        })
    return {"entries": entries, "n": len(entries)}



def displacement_law(rung_table):
    """H4: rho(std, tau_b) versus rho(|mean|, tau_b) across the ladder."""

    from scipy import stats

    std = np.asarray([entry["std_shift_eV"] for entry in rung_table], dtype=float)
    magnitude = np.asarray([abs(entry["mean_shift_eV"]) for entry in rung_table], dtype=float)
    tau = np.asarray([entry["tau_b"] for entry in rung_table], dtype=float)
    unresolved = np.asarray([entry["f_unresolved_z=1.96"] for entry in rung_table], dtype=float)
    if std.size < 3:
        return {"n": int(std.size), "verdict": "no_data"}
    rho_std = float(stats.spearmanr(std, tau).statistic)
    rho_mag = float(stats.spearmanr(magnitude, tau).statistic)
    rho_unresolved = float(stats.spearmanr(std, unresolved).statistic)
    mask = np.asarray([entry["rung"] in PRIMARY_RUNGS for entry in rung_table], dtype=bool)
    primary = {
        "n": int(mask.sum()),
        "rho_std_tau": float(stats.spearmanr(std[mask], tau[mask]).statistic) if mask.sum() >= 3 else None,
        "rho_absmean_tau": float(stats.spearmanr(magnitude[mask], tau[mask]).statistic)
                            if mask.sum() >= 3 else None,
        "rho_std_unresolved": float(stats.spearmanr(std[mask], unresolved[mask]).statistic)
                              if mask.sum() >= 3 else None,
    }
    ok = rho_std <= H4_RHO and rho_mag > H4_RHO
    return {
        "n": int(std.size),
        "rho_std_tau": rho_std, "rho_absmean_tau": rho_mag,
        "rho_std_unresolved": rho_unresolved,
        "primary_single_medium_subset": primary,
        "paper": {"rho_std_tau": -0.8511, "rho_absmean_tau": -0.5350, "rho_std_unresolved": 0.8936},
        "threshold_rho_std_tau": H4_RHO,
        "verdict": "成立" if ok else "判否",
    }


def build_summary(records, layer_rows, axes, prereg, prereg_sha, elapsed, generated_at,
                  c1_reference, dscf_rows, medium_rows):
    rung_table = []
    rung_pairs = {}
    for name, description, ox_source, ox_target, red_source, red_target, maps_to in RUNGS:
        for axis, source_key, target_key in (("ox", ox_source, ox_target),
                                             ("red", red_source, red_target)):
            source, target, keys = pair_arrays(axes, source_key, target_key)
            if source.size < 5:
                rung_table.append({
                    "rung": name, "axis": axis, "description": description, "n": int(source.size),
                    "maps_to_paper": maps_to, "insufficient": True,
                })
                continue
            metrics = rung_metrics(source, target)
            metrics.update({"rung": name, "axis": axis, "description": description,
                            "maps_to_paper": maps_to, "source_axis": source_key,
                            "target_axis": target_key, "insufficient": False})
            boot = bootstrap_rung(source, target, BOOTSTRAP_B, SEED)
            metrics["tau_b_ci"] = boot["tau_b"]
            metrics["spearman_rho_ci"] = boot["spearman_rho"]
            entries_compact = []
            for position, key in enumerate(keys):
                entries_compact.append({"inchikey": key, "source": float(source[position]),
                                        "target": float(target[position]),
                                        "shift": float(target[position] - source[position])})
            rung_pairs[name + "|" + axis] = entries_compact
            rung_table.append(metrics)
    usable = [entry for entry in rung_table if not entry.get("insufficient")]

    law = displacement_law(usable)
    born = born_law(dscf_rows)
    identity = state_identity(layer_rows)
    anchor = anchors(layer_rows, medium_rows)
    qc = c2_qc(layer_rows)
    gap = paper_gap_map(usable)

    rung_lookup = {item[0]: (("ox", item[2], item[3]), ("red", item[4], item[5])) for item in RUNGS}
    subsample = {}
    for name in SUBSAMPLE_RUNG_KEYS:
        for axis, source_key, target_key in rung_lookup[name]:
            source, target, _keys = pair_arrays(axes, source_key, target_key)
            if source.size >= 10:
                subsample[name + "|" + axis] = subsample_tau_sd(
                    source, target, SUBSAMPLE_N, SUBSAMPLE_DRAWS, SEED
                )


    def find(rung, axis):
        for entry in usable:
            if entry["rung"] == rung and entry["axis"] == axis:
                return entry
        return None

    def conditional_verdict(pairs):
        seen = []
        for rung_name in pairs:
            for axis, wants_positive in (("ox", True), ("red", False)):
                entry = find(rung_name, axis)
                if entry is None:
                    return "no_data"
                if abs(entry["tau_b"]) < H9_TAU_MIN:
                    return "不可判（|tau_b| < %.2f）" % H9_TAU_MIN
                ok = (entry["tau_b"] > 0) if wants_positive else (entry["tau_b"] < 0)
                if not ok:
                    return "判否"
                seen.append(rung_name + "|" + axis)
        return "成立"

    h1 = {
        "statement": "C0->C1: ox keeps order, red loses it",
        "rungs": ["C0->C1_dscf_gas", "C0->C1_dscf_water"],
        "readings": {
            name + "|" + axis: (find(name, axis) or {}).get("tau_b")
            for name in ("C0->C1_dscf_gas", "C0->C1_dscf_water") for axis in ("ox", "red")
        },
        "paper": {"ox": 0.689, "red": -0.4667},
        "verdict": conditional_verdict(("C0->C1_dscf_gas", "C0->C1_dscf_water")),
    }
    h9 = {
        "statement": "C1->C2: ox keeps order (tau_b > 0.40), red loses it (tau_b < 0.40)",
        "readings": {
            name + "|" + axis: (find(name, axis) or {}).get("tau_b")
            for name in ("C1->C2_dscf_gas", "C1->C2_dscf_water") for axis in ("ox", "red")
        },
        "paper": {"ox": 0.867, "red": 0.289},
        "verdict": "成立" if all(
            (find(name, "ox") or {}).get("tau_b") is not None
            and (find(name, "ox") or {}).get("tau_b") > H9_OX_MIN
            and (find(name, "red") or {}).get("tau_b") is not None
            and (find(name, "red") or {}).get("tau_b") < H9_RED_MAX
            for name in ("C1->C2_dscf_gas", "C1->C2_dscf_water")
        ) else "判否",
    }
    closed_form_max = 0.0
    for entry in usable:
        for _z, label in Z_RULES:
            value = entry.get("closed_form_max_abs_diff_" + label)
            if value is not None:
                closed_form_max = max(closed_form_max, float(value))
    h3 = {
        "statement": "sigma_ij identity: direct pair loop == Pr(q_ij > sqrt(2)/z)",
        "max_abs_difference": closed_form_max,
        "tolerance": H3_TOLERANCE,
        "rungs_checked": len(usable),
        "verdict": "成立" if closed_form_max <= H3_TOLERANCE else "判否",
    }
    n10 = {}
    inside = []
    for key, table in subsample.items():
        value = (table.get("N=10") or {}).get("sd")
        n10[key] = value
        if value is not None:
            inside.append(H6_SD_LO <= value <= H6_SD_HI)
    h6 = {
        "statement": "tau_b sampling sd at N=10 lands in [0.06, 0.25]",
        "sd_at_N10": n10,
        "paper": 0.1264,
        "verdict": "成立" if inside and all(inside) else "判否",
    }
    failed = sum(1 for row in layer_rows for arm in ARM_KEYS
                 if row.get(arm + "_status") not in ("ok",))
    total_arms = len(layer_rows) * len(ARM_KEYS)
    pool = {
        "n_compounds": len(layer_rows),
        "arms_per_compound": len(ARM_KEYS),
        "planned_runs": int(prereg["arms"]["planned_runs"]),
        "actual_runs": int(total_arms - failed),
        "failed_arms": int(failed),
        "matches_prereg": len(layer_rows) * len(ARM_KEYS) == int(prereg["arms"]["planned_runs"]),
        "elapsed_seconds": round(float(elapsed), 1),
        "generated_at_utc": generated_at,
    }
    summary = {
        "schema_version": "w24_condition_redox_summary@1",
        "task": prereg["task"],
        "title": prereg["title"],
        "prereg_sha256": prereg_sha,
        "pool": pool,
        "rung_table": rung_table,
        "rung_pairs": rung_pairs,
        "displacement_law": law,
        "born_law": born,
        "state_identity": identity,
        "anchors": anchor,
        "c2_qc": qc,
        "paper_gap_map": gap,
        "subsample_tau": subsample,
        "hypotheses": {"H1": h1, "H3": h3, "H6": h6, "H9": h9,
                       "H2": {"verdict": identity["verdict"], "share": identity["gas_complex_share"]},
                       "H4": {"verdict": law.get("verdict"), "rho_std_tau": law.get("rho_std_tau"),
                              "rho_absmean_tau": law.get("rho_absmean_tau")},
                       "H5": {"verdict": born.get("verdict"),
                              "share_r2_ge_threshold": born.get("share_r2_ge_threshold")},
                       "H7": {"verdict": anchor.get("verdict"),
                              "max_abs_delta_hartree": anchor.get("max_abs_delta_hartree")},
                       "H8": {"verdict": qc.get("verdict")}},
        "declared_limits": prereg["declared_limits"],
    }
    return summary


SUBSAMPLE_RUNG_KEYS = ("P0->P1", "C0->C1_dscf_gas", "C1->C2_dscf_gas")



# --------------------------------------------------------------------------- #
# artifacts


RUNG_CSV_FIELDS = (
    "rung", "axis", "description", "maps_to_paper", "n", "pairs",
    "mean_shift_eV", "std_shift_eV", "mean_abs_shift_eV",
    "tau_b", "tau_b_lo", "tau_b_hi", "spearman_rho", "spearman_lo", "spearman_hi",
    "f_unresolved_z=1", "f_unresolved_z=1.96", "f_unresolved_delta_0.05eV",
    "f_unresolved_closed_z=1", "f_unresolved_closed_z=1.96",
    "f_robust_inversion", "pairs_resolved_both", "robust_inversions",
    "sigma_mean_eV", "pair_gap_median_eV", "q_mean", "q_p95",
    "topk10_overlap", "topk20_overlap", "topk30_overlap",
)


def rung_rows(summary):
    rows = []
    for entry in summary["rung_table"]:
        if entry.get("insufficient"):
            rows.append([entry["rung"], entry["axis"], entry.get("description", ""),
                         entry.get("maps_to_paper") or "", entry["n"]] + [""] * (len(RUNG_CSV_FIELDS) - 5))
            continue
        boot = entry.get("tau_b_ci") or {}
        boot_rho = entry.get("spearman_rho_ci") or {}
        rows.append([
            entry["rung"], entry["axis"], entry["description"], entry.get("maps_to_paper") or "",
            entry["n"], entry["pairs"],
            fmt(entry["mean_shift_eV"]), fmt(entry["std_shift_eV"]), fmt(entry["mean_abs_shift_eV"]),
            fmt(entry["tau_b"]), fmt(boot.get("lo")), fmt(boot.get("hi")),
            fmt(entry["spearman_rho"]), fmt(boot_rho.get("lo")), fmt(boot_rho.get("hi")),
            fmt(entry["f_unresolved_z=1"]), fmt(entry["f_unresolved_z=1.96"]),
            fmt(entry["f_unresolved_delta_0.05eV"]),
            fmt(entry["f_unresolved_closed_z=1"]), fmt(entry["f_unresolved_closed_z=1.96"]),
            fmt(entry["f_robust_inversion"]), entry["pairs_resolved_both"], entry["robust_inversions"],
            fmt(entry["sigma_mean_eV"]), fmt(entry["pair_gap_median_eV"]),
            fmt(entry["q_mean"]), fmt(entry["q_p95"]),
            fmt(entry["topk"]["k/N=10%"]["overlap"]), fmt(entry["topk"]["k/N=20%"]["overlap"]),
            fmt(entry["topk"]["k/N=30%"]["overlap"]),
        ])
    return rows



def write_artifacts(summary):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    w21.write_csv(ARTIFACTS / "w24_rung_table.csv", list(RUNG_CSV_FIELDS), rung_rows(summary))
    law = summary["displacement_law"]
    primary = law.get("primary_single_medium_subset") or {}
    w21.write_csv(
        ARTIFACTS / "w24_displacement_law.csv",
        ["quantity", "value"],
        [["n_rungs", law.get("n")],
         ["rho_std_tau", fmt(law.get("rho_std_tau"))],
         ["rho_absmean_tau", fmt(law.get("rho_absmean_tau"))],
         ["rho_std_unresolved", fmt(law.get("rho_std_unresolved"))],
         ["primary_n", primary.get("n")],
         ["primary_rho_std_tau", fmt(primary.get("rho_std_tau"))],
         ["primary_rho_absmean_tau", fmt(primary.get("rho_absmean_tau"))],
         ["primary_rho_std_unresolved", fmt(primary.get("rho_std_unresolved"))],
         ["paper_rho_std_tau", -0.8511],
         ["paper_rho_absmean_tau", -0.5350],
         ["paper_rho_std_unresolved", 0.8936],
         ["verdict", law.get("verdict")]],
    )
    closed = []
    for entry in summary["rung_table"]:
        if entry.get("insufficient"):
            continue
        closed.append([entry["rung"], entry["axis"], entry["n"], entry["pairs"],
                       fmt(entry["f_unresolved_z=1"]), fmt(entry["f_unresolved_closed_z=1"]),
                       fmt(entry["closed_form_max_abs_diff_z=1"]),
                       fmt(entry["f_unresolved_z=1.96"]), fmt(entry["f_unresolved_closed_z=1.96"]),
                       fmt(entry["closed_form_max_abs_diff_z=1.96"])])
    w21.write_csv(ARTIFACTS / "w24_closed_form.csv",
                  ["rung", "axis", "n", "pairs", "f_direct_z1", "f_closed_z1", "max_abs_diff_z1",
                   "f_direct_z196", "f_closed_z196", "max_abs_diff_z196"], closed)
    born = summary["born_law"]
    w21.write_csv(ARTIFACTS / "w24_born_curves.csv",
                  ["inchikey", "name", "charge_state", "C_eV", "r2",
                   "residual_at_max_eps_eV", "dE_times_eps_max_eV"],
                  [[curve["inchikey"], curve["name"], curve["charge_state"],
                    fmt(curve["C_eV"]), fmt(curve["r2"]),
                    fmt(curve["residual_at_max_eps_eV"]), fmt(curve["dE_times_eps_max_eV"])]
                   for curve in born.get("curves", [])])
    w21.write_csv(ARTIFACTS / "w24_state_identity.csv",
                  ["complex", "medium", "n", "mean_delta_q_e", "share_ge_threshold",
                   "n_cation_pairs", "mean_delta_q_cation_e", "share_cation_ge_threshold", "verdict"],
                  [[entry["complex"], entry["medium"], entry["n"],
                    fmt(entry["mean_delta_q_e"]), fmt(entry["share_ge_threshold"]),
                    entry["n_cation_pairs"], fmt(entry["mean_delta_q_cation_e"]),
                    fmt(entry["share_cation_ge_threshold"]), entry["verdict"]]
                   for entry in summary["state_identity"]["entries"]])
    subsample_rows = []
    for key, table in sorted(summary["subsample_tau"].items()):
        for size, payload in table.items():
            subsample_rows.append([key, size, payload["draws"], fmt(payload["mean"]),
                                   fmt(payload["sd"]), fmt(payload["p2_5"]), fmt(payload["p97_5"])])
    w21.write_csv(ARTIFACTS / "w24_subsample_tau.csv",
                  ["rung_axis", "N", "draws", "mean", "sd", "p2_5", "p97_5"], subsample_rows)
    gap = summary["paper_gap_map"]
    w21.write_csv(ARTIFACTS / "w24_paper_gap_map.csv",
                  ["our_rung", "axis", "paper_rung", "our_mean_shift_eV", "our_std_shift_eV",
                   "our_tau_b", "our_f_unresolved", "paper_mean_shift_eV", "paper_std_shift_eV",
                   "paper_tau_b", "paper_f_unresolved", "sign_agrees", "tau_sign_agrees", "delta_tau_b"],
                  [[entry["our_rung"], entry["axis"], entry["paper_rung"],
                    fmt(entry["our_mean_shift_eV"]), fmt(entry["our_std_shift_eV"]), fmt(entry["our_tau_b"]),
                    fmt(entry["our_f_unresolved"]), fmt(entry["paper_mean_shift_eV"]),
                    fmt(entry["paper_std_shift_eV"]), fmt(entry["paper_tau_b"]),
                    fmt(entry["paper_f_unresolved"]), entry["sign_agrees"], entry["tau_sign_agrees"],
                    fmt(entry["delta_tau_b"])] for entry in gap["entries"]])
    anchor = summary["anchors"]
    w21.write_csv(ARTIFACTS / "w24_anchor.csv", ["quantity", "value"],
                  [["n_hartree_pairs", anchor["n_hartree_pairs"]],
                   ["max_abs_delta_hartree", fmt(anchor["max_abs_delta_hartree"])],
                   ["tolerance_hartree", H7_TOL_HARTREE],
                   ["n_orbital_pairs", anchor["n_orbital_pairs"]],
                   ["max_abs_delta_orbital_eV", fmt(anchor["max_abs_delta_orbital_eV"])],
                   ["tolerance_eV", H7_TOL_EV], ["verdict", anchor["verdict"]]])
    w21.write_csv(ARTIFACTS / "w24_c2_qc.csv", ["medium", "intact", "broken", "not_available",
                                                "denominator", "share_intact", "verdict"],
                  [[entry["medium"], entry["counts"].get("intact", 0), entry["counts"].get("broken", 0),
                    entry["counts"].get("not_available", 0), entry["denominator"],
                    fmt(entry["share_intact"]), entry["verdict"]]
                   for entry in summary["c2_qc"]["entries"]])
    w21.write_csv(ARTIFACTS / "w24_ladder.csv", ["rung", "axis", "n", "mean_shift_eV",
                                                 "std_shift_eV", "tau_b", "f_unresolved_z196",
                                                 "f_robust_inversion", "topk10_overlap"],
                  [[entry["rung"], entry["axis"], entry["n"], fmt(entry["mean_shift_eV"]),
                    fmt(entry["std_shift_eV"]), fmt(entry["tau_b"]), fmt(entry["f_unresolved_z=1.96"]),
                    fmt(entry["f_robust_inversion"]), fmt(entry["topk"]["k/N=10%"]["overlap"])]
                   for entry in summary["rung_table"] if not entry.get("insufficient")])



def write_qc_csv(summary, layer_rows):
    rows = []
    for arm in ARM_KEYS:
        counts = Counter(row.get(arm + "_status") or "missing" for row in layer_rows)
        rows.append([arm, counts.get("ok", 0), counts.get("xtb_failed", 0),
                     counts.get("parse_failed", 0), counts.get("no_motif", 0),
                     counts.get("exception", 0), len(layer_rows)])
    w21.write_csv(ARTIFACTS / "w24_qc.csv",
                  ["arm", "ok", "xtb_failed", "parse_failed", "no_motif", "exception", "n_rows"], rows)


def f4(value):
    if value is None:
        return "n/a"
    return "%.4f" % float(value)


def render_report(summary):
    rows = []
    def add(text):
        rows.append(text)
    h = summary["hypotheses"]
    law = summary["displacement_law"]
    primary = law.get("primary_single_medium_subset") or {}
    born = summary["born_law"]
    pool = summary["pool"]
    add("# W24 · Axis B `C_1` 氧化还原臂与 `C_2` 显式微溶剂化臂首次实例化（N=246 大样本）")
    add("")
    add("- **预注册**：`probes/w24_condition_redox_prereg.json`（sha256 `" + summary["prereg_sha256"][:16] + "...`）")
    add("- **池**：" + str(pool["n_compounds"]) + " 化合物 x " + str(pool["arms_per_compound"]) + " 臂 = **" + str(pool["actual_runs"]) + " 次 GFN2-xTB**（计划 " + str(pool["planned_runs"]) + " 次，失败 " + str(pool["failed_arms"]) + " 臂）")
    add("- **口径**：绝热（三态各自 `--opt`）；`IP = E(cation) - E(ref)`、`EA = E(ref) - E(reduced)`；与论文的垂直三点法不同口径")
    add("- **纪律**：冻结读数不动、主记分牌尝试 0 次（累计 12）、不引用 Reaxys 数值、参考层不折进任何池")
    add("")
    add("## 1. 九条跑前假设的判词")
    add("")
    add("| id | 假设 | 判词 | 关键读数 |")
    add("| --- | --- | --- | --- |")
    add("| H1 | C0->C1：氧化轴保序、还原轴失序 | " + str(h["H1"]["verdict"]) + " | " + "；".join("%s=%s" % (k, f4(v)) for k, v in h["H1"]["readings"].items()) + " |")
    add("| H2 | 还原态多余电子落在 Li 上（>=0.5 e） | " + str(h["H2"]["verdict"]) + " | 气相占比 " + str(h["H2"]["share"]) + " |")
    add("| H3 | sigma_ij 闭式恒等式 | " + str(h["H3"]["verdict"]) + " | 最大绝对差 " + ("%.2e" % h["H3"]["max_abs_difference"]) + " |")
    add("| H4 | rho(std, tau_b) <= -0.5 | " + str(h["H4"]["verdict"]) + " | rho_std=" + f4(h["H4"]["rho_std_tau"]) + "，rho_absmean=" + f4(h["H4"]["rho_absmean_tau"]) + " |")
    add("| H5 | Born 律 R2 >= 0.90 占比 >= 0.70 | " + str(h["H5"]["verdict"]) + " | 占比 " + f4(h["H5"]["share_r2_ge_threshold"]) + " |")
    add("| H6 | N=10 的 tau_b 抽样 sd 落在 [0.06, 0.25] | " + str(h["H6"]["verdict"]) + " | 论文 " + f4(h["H6"]["paper"]) + " |")
    add("| H7 | 回归锚（资格审查） | " + str(h["H7"]["verdict"]) + " | max abs dE = " + ("%.2e" % h["H7"]["max_abs_delta_hartree"]) + " hartree |")
    add("| H8 | C_2 反式二聚 QC 成立占比 >= 0.70 | " + str(h["H8"]["verdict"]) + " | 见第 4 节 |")
    add("| H9 | C1->C2：tau_b(ox) > 0.40 且 tau_b(red) < 0.40 | " + str(h["H9"]["verdict"]) + " | " + "；".join("%s=%s" % (k, f4(v)) for k, v in h["H9"]["readings"].items()) + " |")
    add("")
    add("## 2. 台阶表（唯一变量逐级隔离，N=246）")
    add("")
    add("| 台阶 | 轴 | n | 位移均值/eV | 位移 std/eV | tau_b | 95% CI | f_unresolved(z=1.96) | Top-10% 重叠 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary["rung_table"]:
        if entry.get("insufficient"):
            add("| `" + entry["rung"] + "` | " + entry["axis"] + " | " + str(entry["n"]) + " | 样本不足 | | | | | |")
            continue
        boot = entry.get("tau_b_ci") or {}
        line = "| `" + entry["rung"] + "` | " + entry["axis"] + " | " + str(entry["n"]) + " | " + f4(entry["mean_shift_eV"]) + " | " + f4(entry["std_shift_eV"]) + " | " + f4(entry["tau_b"]) + " | [" + f4(boot.get("lo")) + ", " + f4(boot.get("hi")) + "] | " + f4(entry["f_unresolved_z=1.96"]) + " | " + f4(entry["topk"]["k/N=10%"]["overlap"]) + " |"
        add(line)
    add("")
    add("## 3. 论文三定律在 N=246 上的复核")
    add("")
    add("| 量 | 本仓（全部 " + str(law.get("n")) + " 个台阶-轴） | 本仓（" + str(primary.get("n")) + " 个单变量主台阶） | 论文（N=18 十级台阶） |")
    add("| --- | --- | --- | --- |")
    add("| rho(std, tau_b) | " + f4(law.get("rho_std_tau")) + " | " + f4(primary.get("rho_std_tau")) + " | -0.8511 |")
    add("| rho(absmean, tau_b) | " + f4(law.get("rho_absmean_tau")) + " | " + f4(primary.get("rho_absmean_tau")) + " | -0.5350 |")
    add("| rho(std, f_unresolved) | " + f4(law.get("rho_std_unresolved")) + " | " + f4(primary.get("rho_std_unresolved")) + " | +0.8936 |")
    add("")
    add("**Born 律**（免费态四档 eps 点，单参数过原点拟合）：n = " + str(born.get("n_curves")) + " 条（化合物, 电荷态）曲线，R2 均值 " + f4(born.get("r2_mean")) + "、中位 " + f4(born.get("r2_median")) + "、5 分位 " + f4(born.get("r2_p05")) + "，R2 >= 0.90 占比 " + f4(born.get("share_r2_ge_threshold")) + "。")
    add("仅离子态（cation + anion）n = " + str(born.get("n_ion_curves")) + "，R2 均值 " + f4(born.get("ion_r2_mean")) + "，R2 >= 0.90 占比 " + f4(born.get("ion_share_r2_ge_threshold")) + "。")
    add("前因子 abs(C) 均值 " + f4(born.get("c_eV_mean")) + " eV；eps=80.4 残余均值 " + f4(born.get("residual_at_max_eps_mean_eV")) + " eV；外推到 eps=200 的残余均值 " + f4(born.get("residual_at_eps200_mean_eV")) + " eV、最大 " + f4(born.get("residual_at_eps200_max_eV")) + " eV（外推，须标注）。")
    add("")
    add("**sigma 闭式恒等式**：逐对直算的 f_unresolved 与 Pr(q_ij > sqrt(2)/z) 的最大绝对差 " + ("%.2e" % h["H3"]["max_abs_difference"]) + "（z=1 与 z=1.96，覆盖 " + str(h["H3"]["rungs_checked"]) + " 个台阶-轴）。")
    add("")
    add("## 4. 态身份、C_2 QC、抽样误差与论文 gap map")
    add("")
    add("### 4.1 态身份探针（H2）")
    add("")
    add("| complex | 介质 | n | 还原前后 mean dq(Li)/e | 占比 >= 0.5 e | 氧化前后 mean dq(Li)/e | 判词 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary["state_identity"]["entries"]:
        add("| " + entry["complex"] + " | " + entry["medium"] + " | " + str(entry["n"]) + " | " + f4(entry["mean_delta_q_e"]) + " | " + f4(entry["share_ge_threshold"]) + " | " + f4(entry["mean_delta_q_cation_e"]) + " | " + entry["verdict"] + " |")
    add("")
    add("### 4.2 C_2 反式二聚 QC（H8）")
    add("")
    add("| 介质 | intact | broken | not_available | 分母 | 成立占比 | 判词 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary["c2_qc"]["entries"]:
        add("| " + entry["medium"] + " | " + str(entry["counts"].get("intact", 0)) + " | " + str(entry["counts"].get("broken", 0)) + " | " + str(entry["counts"].get("not_available", 0)) + " | " + str(entry["denominator"]) + " | " + f4(entry["share_intact"]) + " | " + entry["verdict"] + " |")
    add("")
    add("### 4.3 tau_b 抽样误差 vs N（H6）")
    add("")
    add("| 台阶-轴 | N | sd(tau_b) | 备注 |")
    add("| --- | --- | --- | --- |")
    for key in sorted(summary["subsample_tau"]):
        table = summary["subsample_tau"][key]
        for size in sorted(table):
            note = "论文 N=10 sd = 0.1264" if size == "N=10" else ""
            add("| `" + key + "` | " + size + " | " + f4(table[size]["sd"]) + " | " + note + " |")
    add("")
    add("### 4.4 与论文 Table 2 的逐台阶 gap map（只作对照，不作证伪）")
    add("")
    add("| 本仓台阶 | 轴 | 论文台阶 | 本仓均值/eV | 论文均值/eV | 符号一致 | 本仓 tau_b | 论文 tau_b | 带符号 tau_b 差 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary["paper_gap_map"]["entries"]:
        add("| `" + entry["our_rung"] + "` | " + entry["axis"] + " | `" + entry["paper_rung"] + "` | " + f4(entry["our_mean_shift_eV"]) + " | " + f4(entry["paper_mean_shift_eV"]) + " | " + str(entry["sign_agrees"]) + " | " + f4(entry["our_tau_b"]) + " | " + f4(entry["paper_tau_b"]) + " | " + f4(entry["delta_tau_b"]) + " |")
    add("")
    add("## 5. 如实登记的限制")
    add("")
    for item in summary["declared_limits"]:
        add("- " + item)
    add("")
    add("## 6. 池与回归锚")
    add("")
    add("- 计划 / 实际 xTB 次数：" + str(pool["planned_runs"]) + " / " + str(pool["actual_runs"]) + "，失败臂 " + str(pool["failed_arms"]) + "，matches_prereg = " + str(pool["matches_prereg"]))
    anchor = summary["anchors"]
    add("- 回归锚 H7：hartree 对数 " + str(anchor["n_hartree_pairs"]) + "，max|dE| = " + ("%.3e" % anchor["max_abs_delta_hartree"]) + " hartree（容差 1e-9）；轨道对数 " + str(anchor["n_orbital_pairs"]) + "，max|d| = " + ("%.3e" % anchor["max_abs_delta_orbital_eV"]) + " eV（容差 1e-6）")
    add("- 挂钟秒（本机）：" + str(pool["elapsed_seconds"]))
    add("")
    return chr(10).join(rows) + chr(10)



SCF_RETRY_ARGUMENTS = ("--iterations", "1000", "--etemp", "1000")


def scf_retry_posthoc(executable, layer_rows, timeout_seconds):
    """Missed-solution fallback: rerun every failed arm with a relaxed SCF."""

    import shutil
    import tempfile

    from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

    entries = []
    recovered = 0
    for row in layer_rows:
        failed = [arm for arm in ARM_KEYS if row.get(arm + "_status") != "ok"]
        if not failed:
            continue
        index = int(row.get("row_index") or 0)
        molecule, _ff, _error = w21.embed(row.get("canonical_smiles") or "", 42 + index)
        if molecule is None:
            continue
        motif = w21.classify_motif(molecule)
        if int(motif.get("donor_index", -1)) < 0:
            continue
        lithium_position, _anchor = w21.li_position(molecule, motif)
        blocks = {"c1": w21.xyz_block_with_li(molecule, lithium_position),
                  "c2": dimer_xyz(molecule, lithium_position)}
        net = int(row.get("formal_charge") or 0)
        for arm in failed:
            parts = arm.split("_", 2)
            if len(parts) != 3:
                continue
            complex_key, medium, state = parts
            solvent = dict((item[0], item[1]) for item in MEDIA).get(medium)
            offsets = dict((item[0], (item[1], item[2])) for item in STATES)
            if state not in offsets:
                continue
            delta_q, unpaired = offsets[state]
            name = "retry_c%03d_%s_%s_%s.xyz" % (index, complex_key, medium, state)
            scratch = Path(tempfile.mkdtemp(prefix="w24retry_"))
            try:
                (scratch / name).write_text(blocks[complex_key], encoding="utf-8")
                charge = net + 1 + delta_q
                if unpaired:
                    arguments = xtb_open_shell_arguments(name, formal_charge=charge, unpaired_electrons=unpaired)
                else:
                    arguments = xtb_optimisation_arguments(name, formal_charge=charge)
                if solvent:
                    arguments = list(arguments) + ["--alpb", solvent]
                arguments = list(arguments) + list(SCF_RETRY_ARGUMENTS)
                completed = run_xtb_subprocess(executable, arguments, cwd=scratch, timeout_seconds=timeout_seconds)
                optimized = scratch / "xtbopt.xyz"
                payload = w23.parse_arm({
                    "returncode": int(completed.returncode),
                    "stdout": completed.stdout.decode("utf-8", "replace"),
                    "optimized_xyz": optimized.read_text(encoding="utf-8", errors="replace") if optimized.is_file() else None,
                    "charges_text": (scratch / "charges").read_text(encoding="utf-8", errors="replace") if (scratch / "charges").is_file() else None,
                    "sentinel": (scratch / ".xtboptok").is_file(),
                    "seconds": 0.0,
                })
                ok = payload.get("status") == "ok"
                recovered += 1 if ok else 0
                entries.append({"inchikey": row.get("inchikey"), "arm": arm,
                                "first_status": row.get(arm + "_status"),
                                "retry_status": payload.get("status"),
                                "retry_total_E_hartree": fmt(payload.get("total_E_hartree")),
                                "recovered": bool(ok)})
            except Exception as exc:
                entries.append({"inchikey": row.get("inchikey"), "arm": arm,
                                "first_status": row.get(arm + "_status"),
                                "retry_status": "exception", "retry_total_E_hartree": "",
                                "recovered": False, "error": str(exc)[:120]})
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
    return {"attempted": len(entries), "recovered": recovered,
            "post_hoc": "post_hoc", "entries": entries}


def record_checkpoint_path():
    return ARTIFACTS / "w24_condition_redox_records.jsonl"


def load_checkpoint(path):
    """Reuse records that already finished; a long arm must survive a crash."""

    records = {}
    if not path.is_file():
        return records
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            index = payload.get("row_index")
            if index is None:
                continue
            records[int(index)] = payload
    return records


def append_checkpoint(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, record)


def estimated_cost(smiles):
    """Heavy-atom count as a cheap dispatch-order proxy for the ALPB optimisation cost."""

    from rdkit import Chem
    molecule = Chem.MolFromSmiles(smiles)
    return 0 if molecule is None else int(molecule.GetNumHeavyAtoms())


def dispatch_order(meta_rows):
    """Heaviest first: the long poles then overlap with the whole tail of the queue."""

    return sorted(range(len(meta_rows)),
                  key=lambda index: (-estimated_cost(meta_rows[index]["canonical_smiles"]), index))


def main(argv=None):
    parser = argparse.ArgumentParser(description="W24 Axis B C_1 redox and C_2 microsolvation arms")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--from-layer", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--no-retry", action="store_true")
    parser.add_argument("--no-checkpoint", action="store_true")
    args = parser.parse_args(argv)

    if args.report_only:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
        print(json.dumps({"mode": "report_only", "report": str(REPORT)}, ensure_ascii=False))
        return 0

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise SystemExit("pre-registration is not locked; refusing to run")
    prereg_sha = sha256_file(PREREG)
    meta_rows = w21.read_rows(w21.META)
    c1_reference = {row.get("inchikey"): row for row in w21.read_rows(C1_LAYER)}
    dscf_rows = w21.read_rows(DSCF_LAYER)
    medium_rows = w21.read_rows(MEDIUM_LAYER)

    if args.from_layer:
        previous = json.loads(SUMMARY.read_text(encoding="utf-8"))
        layer_rows = w21.read_rows(LAYER_CSV)
        axes = build_axes(layer_rows, dscf_rows, medium_rows)
        summary = build_summary([], layer_rows, axes, prereg, prereg_sha,
                                previous["pool"]["elapsed_seconds"],
                                previous["pool"]["generated_at_utc"], c1_reference,
                                dscf_rows, medium_rows)
        summary["retry"] = previous.get("retry", {"attempted": 0, "recovered": 0,
                                                 "post_hoc": "not_executed", "entries": []})
        write_artifacts(summary)
        write_qc_csv(summary, layer_rows)
        write_json_stable(SUMMARY, summary)
        REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
        print(json.dumps({"mode": "from_layer", "n": len(layer_rows)}, ensure_ascii=False))
        return 0

    if args.limit is not None:
        meta_rows = meta_rows[:args.limit]
    total = len(meta_rows)
    executable = str(w21.resolve_xtb())
    order = dispatch_order(meta_rows)
    checkpoint = record_checkpoint_path()
    reused = {} if args.no_checkpoint else load_checkpoint(checkpoint)
    payloads = [(index, meta_rows[index]["name"], meta_rows[index]["canonical_smiles"],
                 executable, args.timeout) for index in order if index not in reused]
    started = time.perf_counter()
    records = list(reused.values())
    skipped = len(records)
    if skipped:
        print(json.dumps({"mode": "resume", "reused": skipped, "remaining": len(payloads),
                          "checkpoint": str(checkpoint)}, ensure_ascii=False), flush=True)
    workers = max(1, int(args.workers))

    def snapshot():
        partial = build_layer_rows(records, meta_rows, c1_reference)
        w21.write_csv(LAYER_CSV, LAYER_FIELDS,
                      [[row[field] for field in LAYER_FIELDS] for row in partial])
        return partial

    def announce(last_name):
        so_far = time.perf_counter() - started
        finished = len(records) - skipped
        remaining = total - len(records)
        eta = (so_far / finished * remaining) if finished else 0.0
        print(json.dumps({"processed": len(records), "total": total, "last": last_name,
                          "sec": round(so_far, 1), "eta_sec": round(eta, 1)},
                         ensure_ascii=False), flush=True)

    def keep(record):
        records.append(record)
        if not args.no_checkpoint:
            append_checkpoint(checkpoint, record)

    if workers == 1:
        for payload in payloads:
            record = run_compound(payload)
            keep(record)
            if len(records) % 5 == 0 or len(records) == total:
                snapshot()
                announce(record.get("name"))
    elif payloads:
        with ProcessPoolExecutor(max_workers=workers) as pool_executor:
            futures = [pool_executor.submit(run_compound, payload) for payload in payloads]
            for future in as_completed(futures):
                record = future.result()
                keep(record)
                if len(records) % 5 == 0 or len(records) == total:
                    snapshot()
                    announce(record.get("name"))
    layer_rows = snapshot()
    retry = ({"attempted": 0, "recovered": 0, "post_hoc": "disabled_by_flag", "entries": []}
             if args.no_retry else scf_retry_posthoc(executable, layer_rows, args.timeout))
    elapsed = time.perf_counter() - started
    compute_seconds = float(sum(float(record.get("seconds_total") or 0.0) for record in records))
    if skipped == total and total:
        # A full resume does no work in this process, so the wall clock would read 0.0 and
        # misreport the arm.  Fall back to the summed per-molecule xTB seconds, which is the
        # compute that actually produced these records.
        elapsed = compute_seconds
    axes = build_axes(layer_rows, dscf_rows, medium_rows)
    summary = build_summary(records, layer_rows, axes, prereg, prereg_sha, elapsed, utc_now(),
                            c1_reference, dscf_rows, medium_rows)
    summary["retry"] = retry
    summary["pool"]["checkpoint"] = {"path": str(checkpoint), "reused_records": skipped,
                                     "disabled": bool(args.no_checkpoint)}
    summary["pool"]["compute_seconds_from_records"] = round(compute_seconds, 1)
    summary["pool"]["resumed_records"] = skipped
    write_artifacts(summary)
    write_qc_csv(summary, layer_rows)
    write_json_stable(SUMMARY, summary)
    REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
    print(json.dumps({
        "summary": str(SUMMARY), "report": str(REPORT),
        "n_compounds": summary["pool"]["n_compounds"],
        "actual_runs": summary["pool"]["actual_runs"],
        "failed_arms": summary["pool"]["failed_arms"],
        "matches_prereg": summary["pool"]["matches_prereg"],
        "H7_anchor": summary["anchors"]["max_abs_delta_hartree"],
        "H1": summary["hypotheses"]["H1"]["verdict"],
        "H2": summary["hypotheses"]["H2"]["verdict"],
        "H3": summary["hypotheses"]["H3"]["verdict"],
        "H4": summary["hypotheses"]["H4"]["verdict"],
        "H5": summary["hypotheses"]["H5"]["verdict"],
        "H6": summary["hypotheses"]["H6"]["verdict"],
        "H8": summary["hypotheses"]["H8"]["verdict"],
        "H9": summary["hypotheses"]["H9"]["verdict"],
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
