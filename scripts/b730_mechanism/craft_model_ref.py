"""Faithful re-implementation of CRAFT-epsilon's model (MIT, pinned commit 65fa0fb).

This module exists so CRAFT can be evaluated on THIS project's conformer
ensembles. The published package generates its own GFN2-xTB/ALPB ensembles, so
importing it would confound "different model" with "different conformers".

What is reproduced, from data/external_raw/craft_epsilon/:
  groups.py      -> fragments(), base_label(), family(), atom_group(), atom_type()
  molar_volume   -> VM_CONTRIBUTIONS and the atom-code V_m
  descriptors.py -> Boltzmann weights, atom-type polarizabilities, group dipoles
  model.py       -> classify, effective dipole, Clausius-Mossotti eps_inf, OKF eps

Not reproduced: conformer GENERATION (we feed our own), and name resolution.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

# ---- constants (craft_epsilon/constants.py, pinned) ----
N_A = 6.02214076e23
EPS0 = 8.8541878128e-12
KB = 1.380649e-23
DEBYE = 1e-21 / 299792458.0
R_KCAL = 0.0019872041
HARTREE_TO_KCAL = 627.5094740631
KAPPA_D = 4.80320471257
AU_TO_A3 = 0.14818471
AU_TO_DEBYE = 2.541746473
TEMPERATURE_K = 298.15
THERMAL_EXPANSION_PER_K = 1.0e-3
X_MAX = 0.99
POLAR_Z = {7, 8, 9, 15, 16, 17, 35, 53}

ATOM_TYPES = ["B_SP2_A", "Br", "C_SP2_A", "C_SP2_R", "C_SP3_A", "C_SP3_R", "C_SP_A",
              "Cl", "F", "H", "I", "N_SP2_A", "N_SP2_R", "N_SP3_A", "N_SP3_R", "N_SP_A",
              "O_SP2_A", "O_SP2_R", "O_SP3_A", "O_SP3_R", "P_SP3_A", "S_SP2_A",
              "S_SP2_R", "S_SP3_A", "S_SP3_R", "Si_SP3_A"]

# ---- SOLVENTS: ALPB solvent used for the conformer ensembles ----
SOLVENT = "ether"

VM_CONTRIBUTIONS = {
    'B30': 7.61, 'Br10': 27.52, 'C10': 14.68, 'C20': 9.89, 'C21': 22.77, 'C30': -0.0,
    'C30a': -0.0, 'C31': 13.23, 'C31a': 13.23, 'C32': 27.17, 'C40': -8.4, 'C41': 4.46,
    'C42': 16.57, 'C43': 29.58, 'Cl10': 24.74, 'F10': 17.63, 'Ge40': 9.36, 'I10': 35.64,
    'N10': 14.09, 'N20': 7.42, 'N20a': 7.42, 'N21': 18.14, 'N30': -3.08, 'N30a': -3.08,
    'N31': 7.74, 'N31a': 7.74, 'N32': 17.81, 'N43': 5.36, 'O10': 14.89, 'O20': 6.25,
    'O20a': 6.25, 'O21': 11.78, 'P30': 10.42, 'P40': -1.94, 'P41': 10.06, 'R5': 9.41,
    'R6': 6.89, 'R<5': 10.89, 'R>6': 3.75, 'S10': 25.92, 'S20': 14.9, 'S20a': 14.9,
    'S21': 26.14, 'S30': 5.58, 'S40': -3.74, 'Se20': 19.0, 'Se20a': 19.0, 'Si40': 9.28,
    'Si41': 23.35, 'Sn40': 14.47, 'Ti40': 6.09, 'aromat': 1.82,
}

PATTERN_SMARTS = {
    "ketone": "[CX3](=[OX1])", "aldehyde": "[CX3H1](=[OX1])", "nitrile": "[CX2]#[NX1]",
    "furan": "[o;r5]", "alcohol": "[OX2H]", "phenol": "[OX2H][c]",
    "ether": "[OD2]([#6])[#6]", "ester": "[CX3](=[OX1])[OX2]",
    "carboxylic_acid": "[CX3](=[OX1])[OX2H]", "amide": "[NX3][CX3](=[OX1])",
    "amine": "[NX3]", "nitro": "[N+](=O)[O-]", "phosphoryl_P=O": "[#15]=[OX1]",
    "phosphate_phosphonate": "[#15](=[OX1])[OX2]", "sulfoxide": "[#16X3]=[OX1]",
    "sulfone": "[#16X4](=[OX1])=[OX1]", "thioether": "[#16X2]", "thiol": "[#16X2H]",
    "azole": "[n;r5]", "aromatic_N_heterocycle": "[n]", "aromatic_N_oxide": "[n+][O-]",
    "isocyanate": "[NX2]=[CX2]=[OX1]",
    "thiocyanate": "[$([#16X2][CX2]#[NX1]),$([NX2]=[CX2]=[SX1])]",
    "urea": "[NX3][CX3](=[OX1])[NX3]",
    "carbonate/carbamate": "[OX2][CX3](=[OX1])[OX2,NX3]",
    "nitrate_ester": "[OX2][N+](=O)[O-]", "nitrite_ester": "[OX2][NX2]=[OX1]",
    "acyl_halide": "[CX3](=[OX1])[F,Cl,Br,I]", "epoxide": "[O;r3]1CC1",
    "fluoro": "[F]", "chloro": "[Cl]", "bromo": "[Br]", "iodo": "[I]",
    "anhydride": "[CX3](=[OX1])[OX2][CX3]=[OX1]",
    "sulfate_ester": "[OX2][SX4](=[OX1])(=[OX1])[OX2]",
    "siloxane/silyl_ether": "[#14][OX2]", "borate_B-O": "[#5][OX2]",
}
PATTERNS = {k: Chem.MolFromSmarts(v) for k, v in PATTERN_SMARTS.items()}
PRIORITY = ["urea", "carbonate/carbamate", "anhydride", "carboxylic_acid", "ester", "amide",
            "acyl_halide", "nitrate_ester", "nitrite_ester", "nitro", "phosphate_phosphonate",
            "sulfate_ester", "sulfone", "sulfoxide", "aromatic_N_oxide", "isocyanate",
            "thiocyanate", "nitrile", "aldehyde", "ketone", "phenol", "epoxide", "furan",
            "alcohol", "ether", "thiol", "thioether", "azole", "amine"]
FORMAMIDE = Chem.MolFromSmarts("[NX3][CX3H1]=[OX1]")
ACETAMIDE = Chem.MolFromSmarts("[NX3][CX3](=[OX1])[CH3]")
HB_SMARTS = {
    "carboxylic_acid": "[CX3](=O)[OX2H1]", "phosphate_acid": "[PX4](=O)[OX2H1]",
    "amide_primary": "[CX3](=[OX1])[NX3H2]", "amide_secondary": "[CX3](=[OX1])[NX3H1][#6]",
    "phenol": "[OX2H][c]",
    "alcohol_primary": "[CX4H2;!$(C(O)(O))][OX2H1]",
    "alcohol_secondary": "[CX4H1;!$(C(O)(O))][OX2H1]",
    "alcohol_tertiary": "[CX4H0;!$(C(O)(O))][OX2H1]",
    "thiol": "[#6][SX2H1]", "amine_primary": "[NX3H2;!$(NC=O)]",
    "amine_secondary": "[NX3H1;!$(NC=O)]([!#1])[!#1]",
}
HB_PATTERNS = {k: Chem.MolFromSmarts(v) for k, v in HB_SMARTS.items()}


@dataclass(frozen=True)
class Fragment:
    label: str
    atoms: tuple
    donor_labels: tuple


def fragment_context(mol):
    atoms = {a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() in POLAR_Z}
    atoms.update(n.GetIdx() for i in tuple(atoms)
                 for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetAtomicNum() == 6)
    sel = [mol.GetAtomWithIdx(i) for i in atoms]
    if any(a.GetIsAromatic() or any(n.GetIsAromatic() for n in a.GetNeighbors())
           for a in sel):
        return "_arom"
    if any(a.IsInRing() or any(n.IsInRing() for n in a.GetNeighbors()) for a in sel):
        return "_alicyc"
    return ""


def fragments(smiles):
    heavy = Chem.MolFromSmiles(smiles)
    full = Chem.AddHs(heavy)
    suffix, claimed, result = fragment_context(heavy), set(), []
    formamide = [set(m[:3]) for m in heavy.GetSubstructMatches(FORMAMIDE)]
    acetamide = [set(m[:3]) for m in heavy.GetSubstructMatches(ACETAMIDE)]
    donor_matches = [(name, next(i for i in m
                                 if heavy.GetAtomWithIdx(i).GetAtomicNum() not in (1, 6)))
                     for name, pat in HB_PATTERNS.items()
                     for m in heavy.GetSubstructMatches(pat)]
    for name in PRIORITY + sorted(set(PATTERNS) - set(PRIORITY)):
        for match in heavy.GetSubstructMatches(PATTERNS[name]):
            atoms, label = set(match), name
            if atoms & claimed:
                continue
            if name == "amide":
                if any(atoms <= x for x in formamide):
                    label = "formamide"
                elif any(atoms <= x for x in acetamide):
                    label = "acetamide"
            atoms.update(n.GetIdx() for i in tuple(atoms)
                         if full.GetAtomWithIdx(i).GetAtomicNum() in POLAR_Z
                         for n in full.GetAtomWithIdx(i).GetNeighbors()
                         if n.GetAtomicNum() == 1)
            donors = tuple(n for n, anchor in donor_matches if anchor in atoms)
            result.append(Fragment(label + suffix, tuple(sorted(atoms)), donors))
            claimed.update(atoms)
    for atom in heavy.GetAtoms():
        if atom.GetAtomicNum() in POLAR_Z and atom.GetIdx() not in claimed:
            atoms = {atom.GetIdx()}
            atoms.update(n.GetIdx() for n
                         in full.GetAtomWithIdx(atom.GetIdx()).GetNeighbors()
                         if n.GetAtomicNum() == 1)
            result.append(Fragment("other" + suffix, tuple(sorted(atoms)), ()))
            claimed.update(atoms)
    if len({i for f in result for i in f.atoms}) != sum(len(f.atoms) for f in result):
        raise ValueError("overlapping fragments")
    return result


def base_label(label):
    for suffix in ("_arom", "_alicyc"):
        if label.endswith(suffix):
            return label[:-len(suffix)]
    return label


def family(label):
    b = base_label(label)
    if b.startswith(("acetamide", "formamide", "amide", "aldehyde", "ketone", "ester",
                     "anhydride", "carbonate", "carboxylic", "acyl_halide")):
        return "carbonyl"
    if b.startswith(("ether", "furan", "alcohol", "phenol", "epoxide")):
        return "oxygen"
    if b.startswith(("amine", "nitrile", "aromatic_N", "azole", "isocyanate", "urea")):
        return "nitrogen"
    if b.startswith(("nitro", "nitrate", "nitrite")):
        return "nitro"
    if b.startswith(("fluoro", "chloro", "bromo", "iodo")):
        return "halogen"
    if b.startswith(("phosphate", "phosphoryl")):
        return "phosphorus"
    if b.startswith(("sulfate", "sulfone", "sulfoxide", "thioether", "thiol",
                     "thiocyanate")):
        return "sulfur"
    if b.startswith("siloxane"):
        return "silicon"
    return "other"


def atom_group(t):
    return t[:-2] if t.endswith(("_A", "_R")) else t


def atom_type(atom):
    sym = atom.GetSymbol()
    if sym == "H":
        return "H"
    if sym in ("F", "Cl", "Br", "I"):
        return sym
    if sym == "Si":
        return "Si_SP3_A"
    hyb = {Chem.HybridizationType.SP: "SP", Chem.HybridizationType.SP2: "SP2",
           Chem.HybridizationType.SP3: "SP3"}.get(atom.GetHybridization())
    if hyb is None:
        raise ValueError(f"unsupported hybridization for {sym}")
    return f"{sym}_{hyb}_{'R' if atom.IsInRing() else 'A'}"


# ---------------- molar volume ----------------
def get_atom_code(atom):
    nD = len([x for x in atom.GetNeighbors() if x.GetMass() > 2 and x.GetSymbol() == "H"])
    code = atom.GetSymbol() + str(atom.GetTotalDegree()) + str(atom.GetTotalNumHs() + nD)
    return code + "a" * int(atom.GetIsAromatic())


def molar_volume(mol):
    atoms = Counter(get_atom_code(a) for a in mol.GetAtoms())
    missing = set(atoms) - set(VM_CONTRIBUTIONS)
    if missing:
        raise ValueError(f"no V_m contribution for {sorted(missing)}")
    rings = Counter()
    for ring in mol.GetRingInfo().AtomRings():
        size = len(ring)
        lab = "R>6" if size > 6 else "R<5" if size < 5 else f"R{size}"
        rings[lab] += 1
        if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
            rings["aromat"] += 1
    return (sum(n * VM_CONTRIBUTIONS[c] for c, n in atoms.items())
            + sum(n * VM_CONTRIBUTIONS.get(c, 0.0) for c, n in rings.items()))


# ---------------- descriptors ----------------
def boltzmann_weights(energies):
    rel = (np.asarray(energies) - np.min(energies)) * HARTREE_TO_KCAL
    w = np.exp(-rel / (R_KCAL * TEMPERATURE_K))
    return w / w.sum()


def ensemble_weights(conformers):
    labels = [c.get("diastereomer", 0) for c in conformers]
    uniq = sorted(set(labels))
    w = np.zeros(len(conformers))
    for lab in uniq:
        idx = [i for i, x in enumerate(labels) if x == lab]
        sub = boltzmann_weights([conformers[i]["alpb"]["qrrho_free_energy_hartree"]
                                 for i in idx])
        w[idx] = sub / len(uniq)
    return w


def fragment_anchor(mol, atoms):
    members = set(atoms)
    outside = sorted({n.GetIdx() for a in atoms
                      for n in mol.GetAtomWithIdx(a).GetNeighbors()
                      if n.GetIdx() not in members})
    heavy = [i for i in outside if mol.GetAtomWithIdx(i).GetAtomicNum() > 1]
    return heavy or outside or atoms


def conformer_descriptors(record, frags):
    conformers = record["conformers"]
    weights = ensemble_weights(conformers)
    alpha = np.zeros(len(ATOM_TYPES))
    type_index = {t: i for i, t in enumerate(ATOM_TYPES)}
    per_conformer = []
    for conf, weight in zip(conformers, weights):
        mol = Chem.MolFromMolBlock(conf["molblock"], removeHs=False)
        if mol is None:
            raise ValueError("molblock unparsable")
        alpb = conf["alpb"]
        positions = np.asarray(mol.GetConformer().GetPositions())
        charges = np.asarray(alpb["charges_e"], dtype=float)
        total = np.asarray(alpb["dipole_vector_debye"], dtype=float)
        if alpb.get("dipole_vector_unit") != "debye":
            total = total * AU_TO_DEBYE
        for atom, val in zip(mol.GetAtoms(), alpb["alpha_atoms_au"]):
            name = atom_type(atom)
            if name not in type_index:
                raise ValueError(f"atom type {name} not in regression list")
            alpha[type_index[name]] += weight * float(val)
        atomic_dipoles = np.asarray(alpb["atomic_dipoles_debye"], dtype=float)
        groups = defaultdict(lambda: np.zeros(3))
        for frag in frags:
            atoms = list(frag.atoms)
            anchor = positions[fragment_anchor(mol, atoms)].mean(axis=0)
            groups[frag.label] += (KAPPA_D * (charges[atoms, None]
                                              * (positions[atoms] - anchor)).sum(axis=0)
                                   + atomic_dipoles[atoms].sum(axis=0))
        remainder = total - sum(groups.values(), np.zeros(3))
        per_conformer.append((float(weight), dict(groups), remainder))
    return alpha, per_conformer


# ---------------- model ----------------
def load_parameters():
    import json
    from pathlib import Path
    here = Path(__file__).resolve().parents[2]
    p = here / "data" / "external_raw" / "craft_epsilon" / "parameters.py"
    src = p.read_text(encoding="utf-8")
    i = src.index("{", src.index("PARAMETERS = {"))
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    ns = {}
    exec("PARAMETERS = " + src[i:j + 1], ns)   # noqa: S102
    return ns["PARAMETERS"]


def classify(smiles, frags):
    if rdMolDescriptors.CalcNumHBD(Chem.MolFromSmiles(smiles)) > 0:
        return "H_bonding"
    return "non_polar" if not frags else "single_polar" if len(frags) == 1 else "multiple_polar"


def group_parameter(label, cls, P):
    if cls == "H_bonding":
        base = base_label(label)
        scales = P["hbond"]["fragment_scales"]
        if base in scales:
            return f"hbond:{base}", scales[base]
        return "hbond:rare", P["hbond"]["rare_scale"]
    fam = family(label)
    return f"family:{fam}", P["polar"]["family_scales"][fam]


def atom_type_scales(cls, P):
    groups = dict(P["nonpolar"]["atom_group_scales"])
    if cls != "non_polar":
        groups.update(P["polar"]["atom_group_scales"])
    return np.array([groups.get(atom_group(t), 1.0) for t in ATOM_TYPES])


def epsilon_from_record(record, smiles, P, temperature=TEMPERATURE_K):
    mol = Chem.MolFromSmiles(smiles)
    frags = fragments(smiles)
    cls = classify(smiles, frags)
    vm_298 = molar_volume(mol)
    vm = vm_298 * (1 + THERMAL_EXPANSION_PER_K * (temperature - TEMPERATURE_K))
    alpha, per_conformer = conformer_descriptors(record, frags)

    alpha_scaled = float(alpha @ atom_type_scales(cls, P))
    x = min(4 * math.pi / 3 * N_A * alpha_scaled * AU_TO_A3 * 1e-24 / vm, X_MAX)
    eps_inf = (1 + 2 * x) / (1 - x)

    if cls == "non_polar":
        rest = P["nonpolar"]["dipole_scale"]
        gscale = {}
    else:
        rest = P["hbond" if cls == "H_bonding" else "polar"]["rest_scale"]
        gscale = {f.label: group_parameter(f.label, cls, P)[1] for f in frags}

    mu_sq_eff = mu_sq_raw = 0.0
    for weight, groups, remainder in per_conformer:
        vector = rest * remainder + sum((gscale[lab] * v for lab, v in groups.items()),
                                        np.zeros(3))
        raw = remainder + sum(groups.values(), np.zeros(3))
        mu_sq_eff += weight * float(vector @ vector)
        mu_sq_raw += weight * float(raw @ raw)

    a = N_A * mu_sq_eff * DEBYE ** 2 / (9 * EPS0 * KB * temperature * vm * 1e-6)
    b = eps_inf + a * (eps_inf + 2) ** 2
    eps = (b + math.sqrt(b * b + 8 * eps_inf ** 2)) / 4
    return {
        "epsilon": eps, "class": cls, "molar_volume_cm3_mol": vm,
        "molar_volume_298K_cm3_mol": vm_298, "eps_inf": eps_inf,
        "alpha_boltzmann_A3": float(alpha.sum()) * AU_TO_A3,
        "alpha_scaled_A3": alpha_scaled * AU_TO_A3,
        "mu_rms_xtb_D": math.sqrt(mu_sq_raw),
        "mu_eff_rms_D": math.sqrt(mu_sq_eff),
        "A": a, "rest_scale": rest,
        "n_conformers": len(record["conformers"]),
        "n_polar_groups": len(frags),
        "polar_group_labels": [f.label for f in frags],
    }
