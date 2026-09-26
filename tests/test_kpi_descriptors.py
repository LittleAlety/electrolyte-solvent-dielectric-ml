"""Unit tests for the KPI 64-descriptor replication module.

The expected numbers in this file are hand-derived from the Supporting
Information of Gao et al. (Angew. Chem. Int. Ed. 2024/2025, 64, e202416506),
Tables S6-S9, plus the averaging formula quoted in SI section 4. They are
written out literally rather than recomputed, so a silent change to the module
shows up as a failure instead of as a matching recomputation.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.kpi_descriptors import (
    KPI_BLOCKS,
    KPI_COLUMNS,
    S6_COLUMNS,
    S7_COLUMNS,
    S8_COLUMNS,
    S9_COLUMNS,
    charge_fallback_atoms,
    compute_kpi_descriptors,
    compute_kpi_table,
    element_coverage,
    kpi_columns_table,
)

# The 64 abbreviations exactly as printed in Tables S6-S9, transcribed by hand
# from the SI PDF. This literal is the replication anchor: it must never be
# derived from the module it is testing.
PAPER_ABBREVIATIONS: tuple[str, ...] = (
    # Table S6
    "Molwt",
    "#Heavy",
    "#C",
    "#O",
    "#O/#C",
    "#Het",
    "#Het/#C",
    # Table S7
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
    # Table S8
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
    # Table S9
    "AvgX",
    "AvgI",
    "AvgA",
    "MaxAPC",
    "MinAPC",
    "MaxPC",
    "MinPC",
    "ValE",
)

WATER = "O"
METHANOL = "CO"
ETHYLENE_CARBONATE = "C1COC(=O)O1"
SULFOLANE = "O=S1(=O)CCCC1"
ACETONITRILE = "CC#N"


def _roster_smiles() -> list[str]:
    path = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return [row["smiles"] for row in csv.DictReader(handle)]


# --------------------------------------------------------------------------
# Shape of the module.
# --------------------------------------------------------------------------


def test_column_count_and_block_sizes_match_the_paper() -> None:
    assert len(S6_COLUMNS) == 7
    assert len(S7_COLUMNS) == 17
    assert len(S8_COLUMNS) == 32
    assert len(S9_COLUMNS) == 8
    assert len(KPI_COLUMNS) == 64
    assert KPI_COLUMNS == PAPER_ABBREVIATIONS


def test_blocks_partition_the_columns_without_overlap() -> None:
    flattened = [
        column
        for block in ("atoms_and_mass", "bond_nature", "functional_groups", "electronic_properties")
        for column in KPI_BLOCKS[block]
    ]
    assert flattened == list(KPI_COLUMNS)
    assert len(set(flattened)) == 64


def test_every_column_carries_the_paper_gloss() -> None:
    table = kpi_columns_table()
    assert len(table) == 64
    assert {row["abbreviation"] for row in table} == set(PAPER_ABBREVIATIONS)
    assert all(row["gloss"].strip() for row in table)
    by_abbreviation = {row["abbreviation"]: row["gloss"] for row in table}
    assert by_abbreviation["#Nring"] == "Number of atoms on the maximum ring"
    assert by_abbreviation["#Bran"] == "Number of branches"
    assert by_abbreviation["ValE"] == "Number of valence electrons"


def test_row_keys_and_order_follow_the_paper() -> None:
    row = compute_kpi_descriptors(METHANOL)
    assert list(row) == list(KPI_COLUMNS)
    assert len(row) == 64


# --------------------------------------------------------------------------
# One assertion per hand-checkable column.
# --------------------------------------------------------------------------


def test_molwt_column_matches_the_average_molecular_weight() -> None:
    assert compute_kpi_descriptors(WATER)["Molwt"] == pytest.approx(18.015, abs=1e-3)
    assert compute_kpi_descriptors(METHANOL)["Molwt"] == pytest.approx(32.042, abs=1e-3)
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["Molwt"] == pytest.approx(88.062, abs=1e-3)


def test_heavy_atom_column_excludes_hydrogen() -> None:
    assert compute_kpi_descriptors(WATER)["#Heavy"] == 1
    assert compute_kpi_descriptors(METHANOL)["#Heavy"] == 2
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Heavy"] == 6


def test_carbon_and_oxygen_counts() -> None:
    ec = compute_kpi_descriptors(ETHYLENE_CARBONATE)
    assert ec["#C"] == 3
    assert ec["#O"] == 3
    assert compute_kpi_descriptors(ACETONITRILE)["#O"] == 0


def test_ratio_columns_and_the_zero_carbon_convention() -> None:
    assert compute_kpi_descriptors(METHANOL)["#O/#C"] == 1.0
    assert compute_kpi_descriptors(SULFOLANE)["#O/#C"] == 0.5
    assert compute_kpi_descriptors(SULFOLANE)["#Het/#C"] == 0.75
    assert compute_kpi_descriptors(ACETONITRILE)["#Het/#C"] == 0.5
    # Water has no carbon, so the paper's ratio is mathematically undefined.
    # The module adopts 0.0 and this test pins that convention rather than
    # letting an inf/nan leak into the table.
    assert compute_kpi_descriptors(WATER)["#O/#C"] == 0.0
    assert compute_kpi_descriptors(WATER)["#Het/#C"] == 0.0


def test_heteroatom_column_counts_non_carbon_non_hydrogen() -> None:
    assert compute_kpi_descriptors(WATER)["#Het"] == 1
    assert compute_kpi_descriptors(SULFOLANE)["#Het"] == 3
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Het"] == 3


def test_double_and_triple_bond_columns() -> None:
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#R=R"] == 1
    assert compute_kpi_descriptors(ACETONITRILE)["#R#R"] == 1
    assert compute_kpi_descriptors("N#CCCC#N")["#R#R"] == 2
    # A literal reading of "number of double bonds" counts every double bond,
    # so the sulfone S=O bonds are included. Pinned here so the convention
    # cannot drift unnoticed.
    assert compute_kpi_descriptors(SULFOLANE)["#R=R"] == 2
    assert compute_kpi_descriptors("CS(C)=O")["#R=R"] == 1


def test_donor_and_acceptor_columns_use_the_rdkit_definitions() -> None:
    assert compute_kpi_descriptors(METHANOL)["#Donor"] == 1
    assert compute_kpi_descriptors("CCO")["#Donor"] == 1
    assert compute_kpi_descriptors("Oc1ccccc1O")["#Donor"] == 2
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Accept"] == 3
    assert compute_kpi_descriptors(ACETONITRILE)["#Accept"] == 1


def test_rotatable_bond_column() -> None:
    assert compute_kpi_descriptors(METHANOL)["#Rot"] == 0
    assert compute_kpi_descriptors("CCCCCC")["#Rot"] == 3
    assert compute_kpi_descriptors("CCCC(C)C")["#Rot"] == 2


def test_ring_count_and_largest_ring_columns() -> None:
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Ring"] == 1
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Nring"] == 5
    assert compute_kpi_descriptors(SULFOLANE)["#Nring"] == 5
    assert compute_kpi_descriptors("c1ccc2ccccc2c1")["#Ring"] == 2
    assert compute_kpi_descriptors(METHANOL)["#Ring"] == 0
    assert compute_kpi_descriptors(METHANOL)["#Nring"] == 0


def test_ring_class_columns_split_aliphatic_aromatic_and_saturated() -> None:
    pyridine = compute_kpi_descriptors("c1ccncc1")
    assert pyridine["#ArR"] == 1
    assert pyridine["#ArHR"] == 1
    assert pyridine["#ArCR"] == 0
    assert pyridine["#AlR"] == 0
    assert pyridine["#SR"] == 0

    piperidine = compute_kpi_descriptors("C1CCNCC1")
    assert piperidine["#AlR"] == 1
    assert piperidine["#AlHR"] == 1
    assert piperidine["#SR"] == 1
    assert piperidine["#SHR"] == 1

    assert compute_kpi_descriptors("c1ccccc1C")["#ArCR"] == 1
    assert compute_kpi_descriptors("c1ccc2ccccc2c1")["#ArCR"] == 2


def test_branch_column_counts_carbons_hanging_off_the_longest_chain() -> None:
    assert compute_kpi_descriptors("CCCCCC")["#Bran"] == 0
    assert compute_kpi_descriptors("CCCC(C)C")["#Bran"] == 1
    assert compute_kpi_descriptors(METHANOL)["#Bran"] == 0
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Bran"] == 0


def test_hydroxyl_columns() -> None:
    assert compute_kpi_descriptors("CCO")["#OH"] == 1
    assert compute_kpi_descriptors("CCO")["#AlOH"] == 1
    assert compute_kpi_descriptors("CCO")["#ArOH"] == 0
    assert compute_kpi_descriptors("Oc1ccccc1")["#OH"] == 1
    assert compute_kpi_descriptors("Oc1ccccc1")["#ArOH"] == 1
    assert compute_kpi_descriptors("Oc1ccccc1O")["#OH"] == 2


def test_carboxylic_acid_columns() -> None:
    acetic = compute_kpi_descriptors("CC(=O)O")
    assert acetic["#COO"] == 1
    assert acetic["#AlCOO"] == 1
    assert acetic["#ArCOO"] == 0
    benzoic = compute_kpi_descriptors("O=C(O)c1ccccc1")
    assert benzoic["#COO"] == 1
    assert benzoic["#ArCOO"] == 1
    assert benzoic["#AlCOO"] == 0


def test_carbonyl_column_and_the_cooh_excluded_variant() -> None:
    assert compute_kpi_descriptors("CC(=O)O")["#C=O"] == 1
    assert compute_kpi_descriptors("CC(=O)O")["#C=O\\COO"] == 0
    assert compute_kpi_descriptors("CC=O")["#C=O\\COO"] == 1
    assert compute_kpi_descriptors("CC(C)=O")["#C=O\\COO"] == 1
    assert compute_kpi_descriptors(SULFOLANE)["#C=O"] == 0


def test_ether_ester_and_lactone_columns_do_not_double_count() -> None:
    # Ethylene carbonate is a single cyclic carbonate; a naive substructure
    # count matches the ester pattern twice, once through each ring oxygen.
    ec = compute_kpi_descriptors(ETHYLENE_CARBONATE)
    assert ec["#Ester"] == 1
    assert ec["#Lactone"] == 1
    lactone = compute_kpi_descriptors("O=C1CCCO1")
    assert lactone["#Ester"] == 1
    assert lactone["#Lactone"] == 1
    assert compute_kpi_descriptors("COCCOC")["#Ether"] == 2
    assert compute_kpi_descriptors("COCCOC")["#Ester"] == 0


def test_halogen_and_benzene_columns() -> None:
    assert compute_kpi_descriptors("ClC(Cl)(Cl)Cl")["#Halogen"] == 4
    assert compute_kpi_descriptors("c1ccccc1")["#Benzene"] == 1
    assert compute_kpi_descriptors("Cc1ccccc1")["#Benzene"] == 1
    assert compute_kpi_descriptors("c1ccc2ccccc2c1")["#Benzene"] == 2
    assert compute_kpi_descriptors("C1CCNCC1")["#Benzene"] == 0


def test_aromatic_nitrogen_columns() -> None:
    pyridine = compute_kpi_descriptors("c1ccncc1")
    assert pyridine["#Ar-N"] == 1
    assert compute_kpi_descriptors("c1ccncn1")["#Ar-N"] == 2
    aniline = compute_kpi_descriptors("Nc1ccccc1")
    assert aniline["#ArN"] == 1
    assert aniline["#ArNH"] == 1
    assert aniline["#Aniline"] == 1


def test_amine_columns_exclude_amides_and_charged_nitrogens() -> None:
    assert compute_kpi_descriptors("CCN")["#NH2"] == 1
    assert compute_kpi_descriptors("CCNCC")["#NH1"] == 1
    assert compute_kpi_descriptors("CCN(CC)CC")["#NH0"] == 1
    acetamide = compute_kpi_descriptors("CC(N)=O")
    assert acetamide["#Amide"] == 1
    assert acetamide["#NH2"] == 0
    assert acetamide["#NH1"] == 0
    assert acetamide["#NH0"] == 0
    # A nitro group is not an amine: its nitrogen is charged and bonded to O.
    nitrobenzene = compute_kpi_descriptors("O=[N+]([O-])c1ccccc1")
    assert nitrobenzene["#NH0"] == 0
    assert nitrobenzene["#NH1"] == 0
    assert nitrobenzene["#NH2"] == 0
    assert nitrobenzene["#Aniline"] == 0
    assert nitrobenzene["#ArN"] == 0


def test_imine_amide_aniline_phenol_and_thiol_columns() -> None:
    assert compute_kpi_descriptors("CC=N")["#Imine"] == 1
    assert compute_kpi_descriptors("CN(C)C=O")["#Amide"] == 1
    assert compute_kpi_descriptors("Nc1ccccc1")["#Aniline"] == 1
    assert compute_kpi_descriptors("Oc1ccccc1")["#Phenol"] == 1
    assert compute_kpi_descriptors("Oc1ccccc1O")["#Phenol"] == 2
    assert compute_kpi_descriptors("CCS")["#SH"] == 1
    assert compute_kpi_descriptors("CCO")["#SH"] == 0


def test_small_ring_and_heterocycle_columns() -> None:
    assert compute_kpi_descriptors("CC=O")["#Aldehyde"] == 1
    assert compute_kpi_descriptors("C1CO1")["#Epoxide"] == 1
    assert compute_kpi_descriptors("c1ccoc1")["#Furan"] == 1
    assert compute_kpi_descriptors("C1CCNCC1")["#Piperdine"] == 1
    assert compute_kpi_descriptors("C1CNCCN1")["#Piperdine"] == 0
    assert compute_kpi_descriptors("c1ccncc1")["#Pyridine"] == 1
    assert compute_kpi_descriptors("c1ccncn1")["#Pyridine"] == 0


def test_ketone_nitrile_and_sulfone_columns() -> None:
    assert compute_kpi_descriptors("CC(C)=O")["#Ketone"] == 1
    assert compute_kpi_descriptors("CC(=O)O")["#Ketone"] == 0
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["#Ketone"] == 0
    assert compute_kpi_descriptors(ACETONITRILE)["#Nitrile"] == 1
    assert compute_kpi_descriptors("N#CCCC#N")["#Nitrile"] == 2
    assert compute_kpi_descriptors(SULFOLANE)["#Sulfone"] == 1
    assert compute_kpi_descriptors("CS(C)=O")["#Sulfone"] == 0


def test_valence_electron_column_includes_hydrogens() -> None:
    # H(1)*2 + O(6) = 8
    assert compute_kpi_descriptors(WATER)["ValE"] == 8
    # C(4) + H(1)*4 + O(6) = 14
    assert compute_kpi_descriptors(METHANOL)["ValE"] == 14
    # C(4)*3 + H(1)*4 + O(6)*3 = 34
    assert compute_kpi_descriptors(ETHYLENE_CARBONATE)["ValE"] == 34
    # C(4)*4 + H(1)*8 + O(6)*2 + S(6) = 42
    assert compute_kpi_descriptors(SULFOLANE)["ValE"] == 42


def test_average_electronegativity_uses_the_si_averaging_formula() -> None:
    # water: (2*2.20 + 3.44) / 3
    assert compute_kpi_descriptors(WATER)["AvgX"] == pytest.approx(7.84 / 3.0, abs=1e-12)
    # methanol: (4*2.20 + 2.55 + 3.44) / 6
    assert compute_kpi_descriptors(METHANOL)["AvgX"] == pytest.approx(14.79 / 6.0, abs=1e-12)


def test_average_ionization_energy_uses_the_printed_elemental_values() -> None:
    # water: (2*13.598 + 13.618) / 3
    expected = (2 * 13.598 + 13.618) / 3.0
    assert compute_kpi_descriptors(WATER)["AvgI"] == pytest.approx(expected, abs=1e-12)


def test_average_electron_affinity_keeps_the_negative_nitrogen_value() -> None:
    # water: (2*0.754 + 1.461) / 3
    assert compute_kpi_descriptors(WATER)["AvgA"] == pytest.approx(
        (2 * 0.754 + 1.461) / 3.0, abs=1e-12
    )
    # acetonitrile CH3CN = C2H3N, six atoms: (2*1.263 + 3*0.754 + (-0.070)) / 6
    assert compute_kpi_descriptors(ACETONITRILE)["AvgA"] == pytest.approx(
        (2 * 1.263 + 3 * 0.754 + -0.070) / 6.0, abs=1e-12
    )


def test_partial_charge_columns_are_gasteiger_on_the_drawn_molecule() -> None:
    methanol = compute_kpi_descriptors(METHANOL)
    # Pinned so a silent switch of charge model cannot pass unnoticed.
    assert methanol["MaxPC"] == pytest.approx(0.031941, abs=1e-5)
    assert methanol["MinPC"] == pytest.approx(-0.399630, abs=1e-5)
    assert methanol["MaxAPC"] == pytest.approx(0.399630, abs=1e-5)
    assert methanol["MinAPC"] == pytest.approx(0.031941, abs=1e-5)
    for smiles in (WATER, METHANOL, ETHYLENE_CARBONATE, SULFOLANE):
        row = compute_kpi_descriptors(smiles)
        assert row["MinPC"] <= row["MaxPC"]
        assert 0.0 <= row["MinAPC"] <= row["MaxAPC"]
        assert row["MaxAPC"] == pytest.approx(
            max(abs(row["MaxPC"]), abs(row["MinPC"])), abs=1e-12
        )


# --------------------------------------------------------------------------
# Roster-wide guarantees.
# --------------------------------------------------------------------------


def test_every_roster_smiles_is_describable_without_a_single_nan() -> None:
    smiles_rows = _roster_smiles()
    assert len(smiles_rows) == 246
    table = compute_kpi_table(smiles_rows)
    assert len(table) == 246
    non_finite = [
        (index, column, value)
        for index, row in enumerate(table)
        for column, value in row.items()
        if not math.isfinite(value)
    ]
    assert non_finite == []
    assert all(len(row) == 64 for row in table)


def test_unparseable_smiles_raise_instead_of_becoming_zeros() -> None:
    with pytest.raises(ValueError, match="could not parse SMILES"):
        compute_kpi_descriptors("this is not a molecule")


def test_charge_fallback_is_confined_to_the_two_hexafluorophosphate_ionic_liquids() -> None:
    fallback = {
        smiles: charge_fallback_atoms(smiles)
        for smiles in _roster_smiles()
        if charge_fallback_atoms(smiles) > 0
    }
    assert len(fallback) == 2
    assert all(count == 7 for count in fallback.values())
    assert all("[P-]" in smiles for smiles in fallback)
    assert charge_fallback_atoms(METHANOL) == 0


def test_roster_element_coverage_is_reported_including_off_whitelist_elements() -> None:
    symbols = element_coverage(_roster_smiles())
    assert {"H", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I"} <= symbols
    # B, Si and Fe are outside the KPI element whitelist and are reported as a
    # known limitation rather than silently zero-weighted away.
    assert {"B", "Si", "Fe"} <= symbols


def test_iron_pentacarbonyl_still_produces_a_finite_row() -> None:
    row = compute_kpi_descriptors("[C]=O.[C]=O.[C]=O.[C]=O.[C]=O.[Fe]")
    assert all(math.isfinite(value) for value in row.values())
    assert row["#Het"] == 6
