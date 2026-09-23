"""Parser and feature transforms for GFN2-xTB calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds

AU_POLARIZABILITY_TO_A3 = 0.148184743


class XtbFeatureError(ValueError):
    """Raised when an xTB result cannot provide a complete physical feature."""


@dataclass(frozen=True, slots=True)
class XtbParsed:
    total_energy_hartree: float
    homo_lumo_gap_ev: float
    dipole_debye: float
    polarizability_au: float
    normal_termination: bool


def _required_match(pattern: str, text: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise XtbFeatureError(f"missing {label}")
    return match


def parse_xtb_output(text: str) -> XtbParsed:
    """Extract total energy, HOMO-LUMO gap, dipole, and alpha(0)."""

    normal_termination = "normal termination of xtb" in text
    if not normal_termination:
        raise XtbFeatureError("xTB run did not report normal termination")
    energy = float(
        _required_match(
            r"::\s*total energy\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+Eh",
            text,
            "total energy",
        ).group(1)
    )
    gap = float(
        _required_match(
            r"HL-Gap\s+[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?\s+Eh"
            r"\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+eV",
            text,
            "HOMO-LUMO gap",
        ).group(1)
    )
    polarizability = float(
        _required_match(
            r"Mol\.\s*\S+\(0\)\s*/au\s*:\s*"
            r"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)",
            text,
            "polarizability alpha(0)",
        ).group(1)
    )
    dipole = float(
        _required_match(
            r"^\s*full:.*?([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s*$",
            text,
            "molecular dipole",
        ).group(1)
    )
    return XtbParsed(
        total_energy_hartree=energy,
        homo_lumo_gap_ev=gap,
        dipole_debye=dipole,
        polarizability_au=polarizability,
        normal_termination=normal_termination,
    )


def onsager_proxy(dipole_debye: float, molar_volume_m3_mol: float) -> float:
    """Return the Onsager-style dipole-density term in D^2 m^-3 mol."""

    if molar_volume_m3_mol <= 0:
        raise ValueError("molar_volume_m3_mol must be positive")
    return dipole_debye**2 / molar_volume_m3_mol


def clausius_mossotti_proxy(
    polarizability_au: float,
    molecular_volume_A3: float,
) -> float:
    """Return alpha_A3 / V_A3 as a dimensionless polarizability-density proxy."""

    if molecular_volume_A3 <= 0:
        raise ValueError("molecular_volume_A3 must be positive")
    return polarizability_au * AU_POLARIZABILITY_TO_A3 / molecular_volume_A3


def generate_3d_xyz(smiles: str, *, seed: int) -> str:
    """Embed and force-field optimize a molecule, returning an XYZ block."""

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise XtbFeatureError(f"invalid SMILES: {smiles!r}")
    molecule = Chem.AddHs(molecule)
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = int(seed)
    parameters.useRandomCoords = True
    if AllChem.EmbedMolecule(molecule, parameters) != 0:
        raise XtbFeatureError(f"RDKit could not embed SMILES: {smiles!r}")
    if AllChem.MMFFHasAllMoleculeParams(molecule):
        AllChem.MMFFOptimizeMolecule(molecule, maxIters=1000)
    else:
        AllChem.UFFOptimizeMolecule(molecule, maxIters=1000)
    return Chem.MolToXYZBlock(molecule)


def molecular_volume_A3(xyz_block: str) -> float:
    """Estimate molecular volume from an XYZ geometry using RDKit."""

    molecule = Chem.MolFromXYZBlock(xyz_block)
    if molecule is None:
        raise XtbFeatureError("cannot parse xTB optimized XYZ geometry")
    rdDetermineBonds.DetermineConnectivity(molecule)
    volume = float(AllChem.ComputeMolVolume(molecule, confId=0, gridSpacing=0.2))
    if not volume > 0:
        raise XtbFeatureError("RDKit molecular volume is not positive")
    return volume
