"""Parser and feature transforms for GFN2-xTB calculations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds

AU_POLARIZABILITY_TO_A3 = 0.148184743
_AVOGADRO_CONSTANT = 6.02214076e23
_BOLTZMANN_CONSTANT_J_PER_K = 1.380649e-23
_DEBYE_TO_COULOMB_METRE = 3.3356409519815204e-30
_VACUUM_PERMITTIVITY_F_PER_M = 8.8541878128e-12


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


def onsager_dielectric_estimate(
    dipole_debye: float,
    molar_volume_m3_mol: float,
    polarizability_A3: float,
    temperature_K: float,
) -> float:
    """Estimate static dielectric constant from a simple Onsager model.

    Assumes a homogeneous, isotropic, non-associated liquid of rigid point
    dipoles in an Onsager cavity. The high-frequency dielectric constant is
    approximated from the molecular polarizability with the Lorentz-Lorenz
    relation,

        (n^2 - 1) / (n^2 + 2) = N_A alpha / (3 V_m),

    and the static dielectric constant solves the Onsager reaction-field
    equation,

        (eps - n^2)(2 eps + n^2) / (eps (n^2 + 2)^2)
            = N_A mu^2 / (9 eps_0 k_B T V_m).

    Here alpha is the polarizability volume in m^3, mu is the gas-phase dipole
    moment in C m, V_m is molar volume in m^3 mol^-1, and T is in K. The model
    intentionally neglects hydrogen bonding and association; it is therefore
    used only as a model-independent screening threshold.
    """
    values = (
        dipole_debye,
        molar_volume_m3_mol,
        polarizability_A3,
        temperature_K,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Onsager inputs must be finite")
    if dipole_debye < 0:
        raise ValueError("dipole_debye must be non-negative")
    if polarizability_A3 < 0:
        raise ValueError("polarizability_A3 must be non-negative")
    if temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    if molar_volume_m3_mol <= 0:
        raise ValueError("molar_volume_m3_mol must be positive")

    alpha_density = (
        _AVOGADRO_CONSTANT
        * polarizability_A3
        * 1e-30
        / (3.0 * molar_volume_m3_mol)
    )
    if not 0.0 <= alpha_density < 1.0:
        raise ValueError("Lorentz-Lorenz polarizability density must be in [0, 1)")
    high_frequency_epsilon = (1.0 + 2.0 * alpha_density) / (1.0 - alpha_density)

    reaction_field_term = (
        onsager_proxy(dipole_debye, molar_volume_m3_mol)
        * _DEBYE_TO_COULOMB_METRE**2
        * _AVOGADRO_CONSTANT
        / (
            9.0
            * _VACUUM_PERMITTIVITY_F_PER_M
            * _BOLTZMANN_CONSTANT_J_PER_K
            * temperature_K
        )
    )
    if not math.isfinite(reaction_field_term) or reaction_field_term < 0:
        raise ValueError("Onsager reaction-field term must be finite and non-negative")

    denominator = (high_frequency_epsilon + 2.0) ** 2
    linear_term = high_frequency_epsilon + reaction_field_term * denominator
    discriminant = linear_term**2 + 8.0 * high_frequency_epsilon**2
    return (linear_term + math.sqrt(discriminant)) / 4.0


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
