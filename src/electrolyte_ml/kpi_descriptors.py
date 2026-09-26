"""KPI 64-descriptor module, replicated from Tables S6-S9 of Gao et al.

Source of truth (repository-external, read-only, never copied into the repo):

    Y.-C. Gao, Y.-H. Yuan, N. Yao, L. Yu, Y.-P. Chen, Q. Zhang, X. Chen,
    "A Knowledge-Data Dual-Driven Framework for Predicting the Molecular
    Properties of Rechargeable Battery Electrolytes",
    Angew. Chem. Int. Ed. 2024/2025, 64, e202416506, DOI 10.1002/anie.202416506.

Tables S6-S9 of its Supporting Information
(``anie202416506-sup-0001-misc_information.pdf``, 64 pages) enumerate the 64
descriptor names, their glosses and their abbreviations, and split them into
four blocks: atoms/mass (7), bond nature (17), functional groups (32) and
electronic properties (8). The SI narrative section "4. Molecular feature
extraction" states that the descriptors are "primarily constructed using the
RDKit toolkit" and quotes the averaging formula for AvgI / AvgA / AvgX.

Fidelity ledger -- which columns are copied and which are inferred
-----------------------------------------------------------------
VERBATIM (definition literally present in the paper)
    * the 64 column names and their block order (Tables S6-S9);
    * ``AvgI`` / ``AvgA`` / ``AvgX``. The SI gives
      ``AvgM = (x*E(A) + y*E(B) + z*E(C)) / (x + y + z)`` where ``x, y, z``
      count the atoms of each element and ``E`` is the first ionization
      energy, electron affinity or electronegativity. The elemental *value
      tables* are NOT printed by the paper, so the numbers in
      ``FIRST_IONIZATION_ENERGY_EV`` / ``ELECTRON_AFFINITY_EV`` /
      ``ELECTRONEGATIVITY_PAULING`` are CRC/NIST reference values chosen here.

APPROXIMATE (paper gives words only, no SMARTS, no formula)
    Every count in Tables S6-S8. Where RDKit ships a descriptor with the same
    name, that descriptor is used (``#Heavy``, ``#Donor``, ``#Accept``,
    ``#Rot``, ``#Ring``, the nine ring-class counts). Where it does not, a
    SMARTS pattern or a graph algorithm is written here; each such choice is
    listed in ``reports/kpi_64_feature_module.md``.

    ``ValE`` belongs here too, not to the tier above. Table S9 names it
    ("number of valence electrons") but never says which electrons are
    counted, so the choice is ours: the module sums the outer-shell electron
    count of every atom *including hydrogens* (``PeriodicTable.GetNOuterElecs``),
    which is the reason ``compute_kpi_descriptors`` calls ``Chem.AddHs``.

UNCONFIRMED (paper never states the method at all)
    ``MaxPC`` / ``MinPC`` / ``MaxAPC`` / ``MinAPC``. No charge model is named.
    Gasteiger charges are used as the closest RDKit-native choice, computed on
    the molecule *as drawn* (implicit hydrogens), so these four descriptors are
    heavy-atom statistics. Two roster molecules (the [PF6]- ionic liquids) have
    no Gasteiger parameters for P/F; those atoms receive the documented 0.0
    fallback and ``charge_fallback_atoms`` reports the count.

This module is a replication aid, not a claim of byte-equality with the
paper's private pipeline. It is deliberately free of any dependence on the
project's own datasets so it can be unit-tested in isolation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Lipinski, rdMolDescriptors

__all__ = [
    "KPI_BLOCKS",
    "KPI_COLUMNS",
    "S6_COLUMNS",
    "S7_COLUMNS",
    "S8_COLUMNS",
    "S9_COLUMNS",
    "charge_fallback_atoms",
    "compute_kpi_descriptors",
    "compute_kpi_table",
    "element_coverage",
    "kpi_columns_table",
]

# --------------------------------------------------------------------------
# Column order: Table S6, then S7, then S8, then S9 (64 columns in total).
# --------------------------------------------------------------------------

S6_COLUMNS: tuple[str, ...] = (
    "Molwt",
    "#Heavy",
    "#C",
    "#O",
    "#O/#C",
    "#Het",
    "#Het/#C",
)

S7_COLUMNS: tuple[str, ...] = (
    "#R=R",
    "#R#R",
    "#Donor",
    "#Accept",
    "#Rot",
    "#Ring",
    "#Nring",
    "#AlCR",
    "#AlHR",
    "#AlR",
    "#ArCR",
    "#ArHR",
    "#ArR",
    "#SCR",
    "#SHR",
    "#SR",
    "#Bran",
)

S8_COLUMNS: tuple[str, ...] = (
    "#OH",
    "#AlOH",
    "#ArOH",
    "#COO",
    "#AlCOO",
    "#ArCOO",
    "#C=O",
    "#C=O\\COO",
    "#Ether",
    "#Ester",
    "#Halogen",
    "#Benzene",
    "#Ar-N",
    "#ArN",
    "#ArNH",
    "#Imine",
    "#NH2",
    "#NH1",
    "#NH0",
    "#SH",
    "#Aldehyde",
    "#Amide",
    "#Aniline",
    "#Phenol",
    "#Epoxide",
    "#Furan",
    "#Piperdine",
    "#Pyridine",
    "#Lactone",
    "#Ketone",
    "#Nitrile",
    "#Sulfone",
)

S9_COLUMNS: tuple[str, ...] = (
    "AvgX",
    "AvgI",
    "AvgA",
    "MaxAPC",
    "MinAPC",
    "MaxPC",
    "MinPC",
    "ValE",
)

KPI_BLOCKS: dict[str, tuple[str, ...]] = {
    "atoms_and_mass": S6_COLUMNS,
    "bond_nature": S7_COLUMNS,
    "functional_groups": S8_COLUMNS,
    "electronic_properties": S9_COLUMNS,
}

KPI_COLUMNS: tuple[str, ...] = S6_COLUMNS + S7_COLUMNS + S8_COLUMNS + S9_COLUMNS

# --------------------------------------------------------------------------
# Elemental reference values for AvgX / AvgI / AvgA and ValE.
# --------------------------------------------------------------------------

# Pauling electronegativity (CRC Handbook of Chemistry and Physics, 97th ed.,
# Table "Electronegativity (Pauling scale)").
ELECTRONEGATIVITY_PAULING: dict[int, float] = {
    1: 2.20,
    3: 0.98,
    5: 2.04,
    6: 2.55,
    7: 3.04,
    8: 3.44,
    9: 3.98,
    11: 0.93,
    14: 1.90,
    15: 2.19,
    16: 2.58,
    17: 3.16,
    19: 0.82,
    35: 2.96,
    53: 2.66,
}

# First ionization energy in eV (NIST Atomic Spectra Database, ionization
# energies for neutral atoms).
FIRST_IONIZATION_ENERGY_EV: dict[int, float] = {
    1: 13.598,
    3: 5.392,
    5: 8.298,
    6: 11.260,
    7: 14.534,
    8: 13.618,
    9: 17.423,
    11: 5.139,
    14: 8.152,
    15: 10.487,
    16: 10.360,
    17: 12.968,
    19: 4.341,
    35: 11.814,
    53: 10.451,
}

# Electron affinity in eV (NIST ASD). Nitrogen's is slightly negative, which is
# kept as published rather than clamped to zero.
ELECTRON_AFFINITY_EV: dict[int, float] = {
    1: 0.754,
    3: 0.618,
    5: 0.280,
    6: 1.263,
    7: -0.070,
    8: 1.461,
    9: 3.401,
    11: 0.548,
    14: 1.390,
    15: 0.746,
    16: 2.077,
    17: 3.613,
    19: 0.501,
    35: 3.364,
    53: 3.059,
}

# --------------------------------------------------------------------------
# SMARTS used for the functional-group block. Every pattern is a guess that
# the paper does not pin down, and is listed as approximate in the report.
# --------------------------------------------------------------------------

_FUNCTIONAL_GROUP_SMARTS: dict[str, str] = {
    "#OH": "[OX2H]",
    "#AlOH": "[OX2H][CX4]",
    "#ArOH": "[OX2H]c",
    "#COO": "[CX3](=[OX1])[OX2H1]",
    "#AlCOO": "[CX4][CX3](=[OX1])[OX2H1]",
    "#ArCOO": "c[CX3](=[OX1])[OX2H1]",
    "#C=O": "[CX3]=[OX1]",
    "#Ether": "[OD2]([#6])[#6]",
    "#Ester": "[CX3](=[OX1])[OX2H0][#6]",
    "#Halogen": "[F,Cl,Br,I]",
    "#Ar-N": "[n]",
    "#ArN": "[NX3,NX2;+0;!$([n]);!$([NX3][CX3]=[OX1])]-c",
    "#ArNH": "[NX3;H1,H2;!$([NX3][CX3]=[OX1])]-c",
    "#Imine": "[CX3]=[NX2]",
    "#NH2": "[NX3;H2;+0;!$([NX3][CX3]=[OX1])]",
    "#NH1": "[NX3;H1;+0;!$([NX3][CX3]=[OX1])]",
    "#NH0": "[NX3;H0;+0;!$([NX3][CX3]=[OX1])]",
    "#SH": "[SX2H]",
    "#Aldehyde": "[CX3H1](=[OX1])[#6]",
    "#Amide": "[NX3][CX3]=[OX1]",
    "#Aniline": "[NX3;+0;!$([NX3][CX3]=[OX1])]-c1ccccc1",
    "#Epoxide": "[OX2r3]",
    "#Furan": "c1ccoc1",
    "#Piperdine": "C1CCNCC1",
    "#Pyridine": "c1ccncc1",
    "#Lactone": "[CX3;R](=[OX1])[OX2;R][#6]",
    "#Ketone": "[#6][CX3](=[OX1])[#6]",
    "#Nitrile": "[NX1]#[CX2]",
    "#Sulfone": "[$([#16](=[#8])(=[#8]))]",
}

_PHENOL_RING_SMARTS = "[OX2H]c1ccccc1"

def _compiled(smarts: str) -> Chem.Mol:
    """Compile a SMARTS once and fail loudly if the pattern itself is broken."""

    pattern = Chem.MolFromSmarts(smarts)
    if pattern is None:
        raise ValueError(f"invalid SMARTS in kpi_descriptors: {smarts!r}")
    return pattern


_COMPILED_SMARTS: dict[str, Chem.Mol] = {
    name: _compiled(smarts) for name, smarts in _FUNCTIONAL_GROUP_SMARTS.items()
}
_PHENOL_RING = _compiled(_PHENOL_RING_SMARTS)


# --------------------------------------------------------------------------
# Graph helpers for #Nring and #Bran.
# --------------------------------------------------------------------------


def _carbon_adjacency(mol: Chem.Mol) -> dict[int, tuple[int, ...]]:
    """Return the carbon-only skeleton as an adjacency map of atom indices."""

    carbons = {atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6}
    neighbours: dict[int, list[int]] = {index: [] for index in carbons}
    for bond in mol.GetBonds():
        begin = bond.GetBeginAtomIdx()
        end = bond.GetEndAtomIdx()
        if begin in carbons and end in carbons:
            neighbours[begin].append(end)
            neighbours[end].append(begin)
    return {index: tuple(sorted(values)) for index, values in neighbours.items()}


def _component_sizes(neighbours: dict[int, tuple[int, ...]]) -> dict[int, int]:
    sizes: dict[int, int] = {}
    seen: set[int] = set()
    for start in sorted(neighbours):
        if start in seen:
            continue
        stack = [start]
        component: list[int] = []
        seen.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for nxt in neighbours[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for node in component:
            sizes[node] = len(component)
    return sizes


def _longest_carbon_path(neighbours: dict[int, tuple[int, ...]]) -> list[int]:
    """Longest simple path in the carbon skeleton, deterministic on ties.

    The paper says the longest carbon chain was found with NetworkX by
    enumerating "all possible simple paths between each pair of atoms". That is
    exponential, so this implementation runs the same search with a
    branch-and-bound cut: a partial path is abandoned once the size of its
    connected component cannot beat the best path already found. Ties are
    resolved by ascending atom index, which makes the result reproducible.
    """

    if not neighbours:
        return []
    sizes = _component_sizes(neighbours)
    best: list[int] = []

    for start in sorted(neighbours):
        if sizes[start] <= len(best):
            continue
        stack: list[tuple[int, list[int], frozenset[int]]] = [
            (start, [start], frozenset({start}))
        ]
        while stack:
            node, path, visited = stack.pop()
            if len(path) > len(best):
                best = list(path)
            if len(path) + sizes[start] - len(visited) <= len(best):
                # The component cannot supply enough unvisited carbons to win.
                continue
            for nxt in reversed(neighbours[node]):
                if nxt not in visited:
                    stack.append((nxt, path + [nxt], visited | {nxt}))
    return best


def _branch_carbons(mol: Chem.Mol, path: Sequence[int]) -> int:
    """Carbons hanging off the longest chain but not part of it."""

    if not path:
        return 0
    on_path = set(path)
    branches = set()
    for index in path:
        atom = mol.GetAtomWithIdx(index)
        for neighbour in atom.GetNeighbors():
            if neighbour.GetAtomicNum() == 6 and neighbour.GetIdx() not in on_path:
                branches.add(neighbour.GetIdx())
    return len(branches)


def _group_count(mol: Chem.Mol, pattern: Chem.Mol) -> int:
    """Count functional-group instances, one per anchor atom.

    A plain ``GetSubstructMatches`` count over-counts when a group can be
    written down in two equivalent ways: the cyclic carbonate of ethylene
    carbonate matches an ester twice, once through each ring oxygen, even
    though it is a single ester. Every pattern here is anchored on the atom
    that defines the group (the carbonyl carbon, the oxygen, the halogen, ...),
    so deduplicating by the first matched atom restores the intended count.
    """

    return len({match[0] for match in mol.GetSubstructMatches(pattern)})


def _largest_ring_size(mol: Chem.Mol) -> int:
    ring_info = mol.GetRingInfo()
    sizes = [len(ring) for ring in ring_info.AtomRings()]
    return max(sizes) if sizes else 0


def _benzene_ring_count(mol: Chem.Mol) -> int:
    """Six-membered all-carbon aromatic rings, counted once per ring."""

    count = 0
    for ring in mol.GetRingInfo().AtomRings():
        if len(ring) != 6:
            continue
        atoms = [mol.GetAtomWithIdx(index) for index in ring]
        if all(atom.GetAtomicNum() == 6 and atom.GetIsAromatic() for atom in atoms):
            count += 1
    return count


# --------------------------------------------------------------------------
# Charges.
# --------------------------------------------------------------------------


def _gasteiger_charges(mol: Chem.Mol) -> tuple[list[float], int]:
    """Return (per-heavy-atom Gasteiger charge, number of fallback atoms).

    ``throwOnParamFailure=False`` leaves the ``_GasteigerCharge`` property
    unset (or non-finite) exactly on the atoms whose element has no Gasteiger
    parameter -- in this roster, P and F of the [PF6]- anion. Those atoms
    receive the documented 0.0 fallback instead of a NaN, so the electronic
    block can never silently poison a downstream matrix.
    """

    charges: list[float] = []
    fallback = 0
    for atom in mol.GetAtoms():
        if not atom.HasProp("_GasteigerCharge"):
            charges.append(0.0)
            fallback += 1
            continue
        value = atom.GetDoubleProp("_GasteigerCharge")
        if not math.isfinite(value):
            charges.append(0.0)
            fallback += 1
            continue
        charges.append(value)
    return charges, fallback


# --------------------------------------------------------------------------
# Public API.
# --------------------------------------------------------------------------


def compute_kpi_descriptors(smiles: str) -> dict[str, float]:
    """Compute the 64 KPI descriptors for one SMILES string.

    Raises ``ValueError`` for a SMILES that RDKit cannot parse, so a broken
    input is never silently turned into a row of zeros.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    return _compute_for_mol(mol)


def compute_kpi_table(smiles_iterable: Iterable[str]) -> list[dict[str, float]]:
    """Compute the descriptor table for many SMILES, one dict per molecule."""

    return [compute_kpi_descriptors(smiles) for smiles in smiles_iterable]


def charge_fallback_atoms(smiles: str) -> int:
    """Number of atoms that had to take the documented 0.0 charge fallback."""

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    working = Chem.Mol(mol)
    AllChem.ComputeGasteigerCharges(working, nIter=12, throwOnParamFailure=False)
    _, fallback = _gasteiger_charges(working)
    return fallback


def element_coverage(smiles_iterable: Iterable[str]) -> set[str]:
    """Element symbols appearing in a SMILES collection, for whitelist audits."""

    symbols: set[str] = set()
    for smiles in smiles_iterable:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        # AddHs, so the hydrogen of a SMILES such as "CO" is reported too.
        symbols.update(atom.GetSymbol() for atom in Chem.AddHs(mol).GetAtoms())
    return symbols


def kpi_columns_table() -> list[dict[str, str]]:
    """The 64 columns with their block and the paper's gloss, in paper order."""

    rows: list[dict[str, str]] = []
    for block, columns in KPI_BLOCKS.items():
        for column in columns:
            rows.append({"block": block, "abbreviation": column, "gloss": _GLOSS[column]})
    return rows


_GLOSS: dict[str, str] = {
    "Molwt": "Molecular weight",
    "#Heavy": "Number of heavy atoms (any atoms other than hydrogen)",
    "#C": "Number of carbon atoms",
    "#O": "Number of oxygen atoms",
    "#O/#C": "Ratio of oxygen atoms to carbon atoms",
    "#Het": "Number of heteroatoms",
    "#Het/#C": "Ratio of heteroatoms to carbon atoms",
    "#R=R": "Number of double bonds",
    "#R#R": "Number of triple bonds",
    "#Donor": "Number of hydrogen bond donors",
    "#Accept": "Number of hydrogen bond acceptors",
    "#Rot": "Number of rotatable bonds",
    "#Ring": "Number of rings",
    "#Nring": "Number of atoms on the maximum ring",
    "#AlCR": "Number of aliphatic carbocycles",
    "#AlHR": "Number of aliphatic heterocycles",
    "#AlR": "Number of aliphatic rings",
    "#ArCR": "Number of aromatic carbocycles",
    "#ArHR": "Number of aromatic heterocycles",
    "#ArR": "Number of aromatic rings",
    "#SCR": "Number of saturated carbocycles",
    "#SHR": "Number of saturated heterocycles",
    "#SR": "Number of saturated rings",
    "#Bran": "Number of branches",
    "#OH": "Number of hydroxyl groups",
    "#AlOH": "Number of aliphatic hydroxyl groups",
    "#ArOH": "Number of aromatic hydroxyl groups",
    "#COO": "Number of carboxylic acids",
    "#AlCOO": "Number of aliphatic carboxylic acids",
    "#ArCOO": "Number of aromatic carboxylic acids",
    "#C=O": "Number of carbonyl O",
    "#C=O\\COO": "Number of carbonyl O, excluding COOH",
    "#Ether": "Number of ether oxygens (including phenoxy)",
    "#Ester": "Number of esters",
    "#Halogen": "Number of halogens",
    "#Benzene": "Number of benzene rings",
    "#Ar-N": "Number of aromatic nitrogens",
    "#ArN": "Number of N functional groups attached to aromatics",
    "#ArNH": "Number of aromatic amines",
    "#Imine": "Number of imines",
    "#NH2": "Number of primary amines",
    "#NH1": "Number of secondary amines",
    "#NH0": "Number of tertiary amines",
    "#SH": "Number of thiol groups",
    "#Aldehyde": "Number of aldehydes",
    "#Amide": "Number of amides",
    "#Aniline": "Number of anilines",
    "#Phenol": "Number of phenols",
    "#Epoxide": "Number of epoxide rings",
    "#Furan": "Number of furan rings",
    "#Piperdine": "Number of piperdine rings",
    "#Pyridine": "Number of pyridine rings",
    "#Lactone": "Number of cyclic esters (lactones)",
    "#Ketone": "Number of ketones",
    "#Nitrile": "Number of nitriles",
    "#Sulfone": "Number of sulfone groups",
    "AvgX": "Average electronegativity",
    "AvgI": "Average ionization energy",
    "AvgA": "Average electron affinity",
    "MaxAPC": "Maximum absolute partial charge",
    "MinAPC": "Minimum absolute partial charge",
    "MaxPC": "Maximum partial charge",
    "MinPC": "Minimum partial charge",
    "ValE": "Number of valence electrons",
}


def _element_average(mol_with_hydrogens: Chem.Mol, table: dict[int, float]) -> float:
    """The SI's ``AvgM`` formula, averaged over every atom including hydrogen.

    The caller must pass an explicit-hydrogen molecule: the SI says the sum runs
    over "the total number of atoms in the molecule", which includes the
    hydrogens, and ``Mol.GetAtoms()`` on an implicit-hydrogen molecule silently
    omits them. Iron pentacarbonyl is the roster's reminder that this matters:
    without the hydrogens, water would average to O alone (3.44) instead of
    2.613.
    """

    total = 0.0
    count = 0
    for atom in mol_with_hydrogens.GetAtoms():
        total += table.get(atom.GetAtomicNum(), 0.0)
        count += 1
    return total / count if count else 0.0


def _compute_for_mol(mol: Chem.Mol) -> dict[str, float]:
    periodic_table = Chem.GetPeriodicTable()
    atoms = list(mol.GetAtoms())

    counts: dict[str, int] = {}
    for atom in atoms:
        symbol = atom.GetSymbol()
        counts[symbol] = counts.get(symbol, 0) + 1

    n_carbon = counts.get("C", 0)
    n_oxygen = counts.get("O", 0)
    n_heavy = mol.GetNumHeavyAtoms()
    n_hetero = sum(
        1 for atom in atoms if atom.GetAtomicNum() != 1 and atom.GetAtomicNum() != 6
    )

    path = _longest_carbon_path(_carbon_adjacency(mol))

    row: dict[str, float] = {}

    # Table S6 -- number and mass of atoms.
    row["Molwt"] = float(Descriptors.MolWt(mol))
    row["#Heavy"] = float(n_heavy)
    row["#C"] = float(counts.get("C", 0))
    row["#O"] = float(counts.get("O", 0))
    # The paper's ratio is undefined at #C == 0. 0.0 is adopted as the
    # documented convention so no roster row needs a NaN.
    row["#O/#C"] = float(n_oxygen / n_carbon) if n_carbon else 0.0
    row["#Het"] = float(n_hetero)
    row["#Het/#C"] = float(n_hetero / n_carbon) if n_carbon else 0.0

    # Table S7 -- nature of bonds.
    double_bonds = 0
    triple_bonds = 0
    for bond in mol.GetBonds():
        if bond.GetBondType() == Chem.BondType.DOUBLE:
            double_bonds += 1
        elif bond.GetBondType() == Chem.BondType.TRIPLE:
            triple_bonds += 1
    row["#R=R"] = float(double_bonds)
    row["#R#R"] = float(triple_bonds)
    row["#Donor"] = float(Lipinski.NumHDonors(mol))
    row["#Accept"] = float(Lipinski.NumHAcceptors(mol))
    row["#Rot"] = float(Lipinski.NumRotatableBonds(mol))
    row["#Ring"] = float(rdMolDescriptors.CalcNumRings(mol))
    row["#Nring"] = float(_largest_ring_size(mol))
    row["#AlCR"] = float(rdMolDescriptors.CalcNumAliphaticCarbocycles(mol))
    row["#AlHR"] = float(rdMolDescriptors.CalcNumAliphaticHeterocycles(mol))
    row["#AlR"] = float(rdMolDescriptors.CalcNumAliphaticRings(mol))
    row["#ArCR"] = float(rdMolDescriptors.CalcNumAromaticCarbocycles(mol))
    row["#ArHR"] = float(rdMolDescriptors.CalcNumAromaticHeterocycles(mol))
    row["#ArR"] = float(rdMolDescriptors.CalcNumAromaticRings(mol))
    row["#SCR"] = float(rdMolDescriptors.CalcNumSaturatedCarbocycles(mol))
    row["#SHR"] = float(rdMolDescriptors.CalcNumSaturatedHeterocycles(mol))
    row["#SR"] = float(rdMolDescriptors.CalcNumSaturatedRings(mol))
    row["#Bran"] = float(_branch_carbons(mol, path))

    # Table S8 -- functional groups.
    for column, pattern in _COMPILED_SMARTS.items():
        row[column] = float(_group_count(mol, pattern))
    row["#C=O\\COO"] = float(row["#C=O"] - row["#COO"])
    row["#Benzene"] = float(_benzene_ring_count(mol))
    row["#Phenol"] = float(_group_count(mol, _PHENOL_RING))

    # Table S9 -- electronic properties.
    explicit_hydrogens = Chem.AddHs(mol)
    row["AvgX"] = _element_average(explicit_hydrogens, ELECTRONEGATIVITY_PAULING)
    row["AvgI"] = _element_average(explicit_hydrogens, FIRST_IONIZATION_ENERGY_EV)
    row["AvgA"] = _element_average(explicit_hydrogens, ELECTRON_AFFINITY_EV)

    working = Chem.Mol(mol)
    AllChem.ComputeGasteigerCharges(working, nIter=12, throwOnParamFailure=False)
    charges, _ = _gasteiger_charges(working)
    absolute = [abs(value) for value in charges]
    row["MaxAPC"] = float(max(absolute)) if absolute else 0.0
    row["MinAPC"] = float(min(absolute)) if absolute else 0.0
    row["MaxPC"] = float(max(charges)) if charges else 0.0
    row["MinPC"] = float(min(charges)) if charges else 0.0
    row["ValE"] = float(
        sum(
            periodic_table.GetNOuterElecs(atom.GetAtomicNum())
            for atom in explicit_hydrogens.GetAtoms()
        )
    )

    assert set(row) == set(KPI_COLUMNS), sorted(set(row) ^ set(KPI_COLUMNS))
    return {column: row[column] for column in KPI_COLUMNS}