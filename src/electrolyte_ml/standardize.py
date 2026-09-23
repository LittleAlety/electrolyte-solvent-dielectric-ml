"""Shared molecule standardization and property-schema helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from rdkit import Chem

UNIFIED_COLUMNS = (
    "inchikey",
    "smiles",
    "T_K",
    "dielectric",
    "viscosity_Pa_s",
    "density",
    "source_doi",
    "gate_flags",
)

GATE_FLAGS = (
    "not_found",
    "missing_viscosity",
    "not_training_ready",
    "historical_fallback_target",
    "target_308_unavailable",
    "zero_frequency",
    "frequency_dependent",
    "pure_component",
    "mixture_only",
    "experimental",
    "predicted",
    "temperature_delta_le_5K",
    "temperature_delta_gt_5K",
    "temperature_gate",
    "exclude_liquid_298K",
    "dipole_units_unreported",
    "r2_gate_failed",
    "high_temperature_extension",
    "literature_manual_entry",
    "single_source",
    "frequency_1mhz",
    "nbs514_circular_514",
    "crosscheck_only",
)


class MoleculeStandardizationError(ValueError):
    """Raised when a structure cannot be converted to a canonical identity."""


@dataclass(frozen=True, slots=True)
class StandardizedMolecule:
    input_smiles: str
    smiles: str
    inchikey: str


def canonicalize_smiles(smiles: str) -> str:
    """Return RDKit's isomeric canonical SMILES or raise a typed error."""

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MoleculeStandardizationError(f"RDKit could not parse SMILES: {smiles!r}")
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def standardize_molecule(smiles: str) -> StandardizedMolecule:
    """Canonicalize SMILES and derive its standard InChIKey."""

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MoleculeStandardizationError(f"RDKit could not parse SMILES: {smiles!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    inchikey = Chem.MolToInchiKey(molecule)
    if not inchikey:
        raise MoleculeStandardizationError(
            f"RDKit could not derive an InChIKey for SMILES: {smiles!r}"
        )
    return StandardizedMolecule(
        input_smiles=smiles,
        smiles=canonical,
        inchikey=inchikey,
    )


def centipoise_to_pascal_second(value: Decimal | float | str) -> Decimal:
    """Convert dynamic viscosity from cP to Pa s."""

    return Decimal(str(value)) * Decimal("0.001")


def grams_per_cubic_centimeter_to_kg_per_cubic_meter(
    value: Decimal | float | str,
) -> Decimal:
    """Convert density from g/cm3 to kg/m3."""

    return Decimal(str(value)) * Decimal(1000)


def render_decimal(value: Decimal) -> str:
    """Render a Decimal without losing scientific notation or adding zeros."""

    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)
