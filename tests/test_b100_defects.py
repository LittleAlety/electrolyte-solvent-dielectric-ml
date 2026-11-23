"""B100 defect guards: four integrity failures found while scaling to 100+ molecules.

Each of these was a real bug that produced a plausible-looking but wrong number. They
are pinned here because every one of them was invisible from the summary statistics.

  1. FAMILY SMARTS SPLIT ON COMMAS. The amine pattern contains commas
     ([NX3;H2,H1,H0;!$(NC=O)]), so splitting a rule string on "," shattered it into
     invalid fragments and the amine family counted ZERO despite 28 members.

  2. IONIC LIQUIDS IN A NEUTRAL-LIQUID DATASET. Ten imidazolium/pyrrolidinium/
     ammonium salts matched a sulfone SMARTS through their TFSI anion, and the
     expansion table records them as component_count = 1. PLAN B v6.0 forbids them.

  3. TAUTOMER SUBSTITUTION. "N-methylacetamide" carried SMILES CN=C(C)O (the imidic
     acid). Standard InChI normalises mobile hydrogens, so the InChIKey check passed
     while xTB computed the wrong species (dipole 1.07 D instead of 4.34 D).

  4. WRONG ENERGY COLUMN. The xTB orbital table prints Energy/Eh AND Energy/eV; taking
     the eV column and multiplying by 27.211 produced a 121 eV "HOMO-LUMO gap".
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"


def _load(name: str) -> list[dict]:
    p = OUT / name
    if not p.is_file():
        return []
    raw = p.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    header = text.splitlines()[0] if text and text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text or "", newline=""),
                              delimiter=delim))


def _j(name: str):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ------------------------------------------------ 1. family classification

def test_amine_family_not_zero_when_amines_present() -> None:
    reg = _load("molecule_registry_b100.csv")
    if not reg:
        pytest.skip("registry missing")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    patt = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O)]")
    n_containing = 0
    for r in reg:
        mol = Chem.MolFromSmiles(r["smiles"]) if r["smiles"] else None
        if mol is not None and patt is not None and mol.HasSubstructMatch(patt):
            n_containing += 1
    if n_containing > 0:
        assert any(r["family"] == "amine" for r in reg), (
            "amine family is empty although amine-containing molecules exist; "
            "the SMARTS list is probably being split on commas")


# ------------------------------------------------ 2. neutral-only dataset

def test_ionic_liquids_are_excluded() -> None:
    nf = _j("neutral_filter_b100.json")
    if not nf:
        pytest.skip("neutral filter missing")
    assert nf["result"]["n_excluded"] > 0, (
        "no ionic liquids excluded; the filter is not doing anything")
    rows = _load("neutral_filter_b100.csv")
    for r in rows:
        if r["verdict"] == "EXCLUDE":
            assert r["exclusion_reason"], f"{r['name']} excluded with no reason"


def test_no_salt_survives_in_the_kept_set() -> None:
    rows = _load("neutral_filter_b100.csv")
    if not rows:
        pytest.skip("neutral filter missing")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    for r in rows:
        if r["verdict"] != "KEEP":
            continue
        mol = Chem.MolFromSmiles(r["smiles"]) if r["smiles"] else None
        if mol is None:
            continue
        frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
        assert len(frags) == 1, (
            f"{r['name']} is kept but has {len(frags)} fragments")
        assert Chem.GetFormalCharge(mol) == 0, (
            f"{r['name']} is kept but carries net charge "
            f"{Chem.GetFormalCharge(mol)}")


def test_family_coverage_respects_neutral_filter() -> None:
    """Excluded salts must not be counted as family coverage."""
    fam = _j("family_coverage_b100.json")
    nf = _j("neutral_filter_b100.json")
    if not (fam and nf):
        pytest.skip("missing artifacts")
    if nf["result"]["n_excluded"] == 0:
        pytest.skip("nothing excluded")
    # sulfone_sulfoxide was made up entirely of ionic liquids
    sf = next((b for b in fam["family_coverage"]
               if b["family"] == "sulfone_sulfoxide"), None)
    if sf is not None:
        assert sf["n_present"] == 0, (
            "sulfone family still counts molecules after the ionic liquids "
            "were excluded")


# ------------------------------------------------ 3. tautomer verification

def test_smiles_verification_ran_and_found_zero_defects() -> None:
    sv = _j("smiles_verification_b100.json")
    if not sv:
        pytest.skip("smiles verification missing")
    counts = sv["verdict_counts"]
    assert "TAUTOMER_OR_FORM" not in counts or counts["TAUTOMER_OR_FORM"] == 0, (
        f"tautomer defects remain: {sv.get('defects')}")


def test_pubchem_lookup_actually_returned_smiles() -> None:
    """Guards the bug where all 257 rows were falsely PUBCHEM_UNAVAILABLE."""
    sv = _j("smiles_verification_b100.json")
    if not sv:
        pytest.skip("smiles verification missing")
    n_unavail = sv["verdict_counts"].get("PUBCHEM_UNAVAILABLE", 0)
    assert n_unavail == 0, (
        f"{n_unavail} molecules reported PubChem-unavailable; the property key "
        f"is probably wrong (response uses SMILES / ConnectivitySMILES, not "
        f"CanonicalSMILES)")


def test_n_methylacetamide_uses_the_amide_form() -> None:
    """The concrete regression: the imidic acid was being computed."""
    rows = _load("xtb_descriptors_b100.csv")
    if not rows:
        pytest.skip("descriptors missing")
    nma = next((r for r in rows
                if r.get("name", "").lower() == "n-methylacetamide"), None)
    if nma is None:
        pytest.skip("N-methylacetamide not in set")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(nma["smiles"])
    assert mol is not None
    amide = Chem.MolFromSmarts("[CX3](=O)[NX3]")
    assert amide is not None and mol.HasSubstructMatch(amide), (
        f"N-methylacetamide is using {nma['smiles']}, which is not an amide")
    # the amide's dipole is several times the imidate's 1.07 D
    assert float(nma["dipole_D"]) > 2.5, (
        f"dipole {nma['dipole_D']} D looks like the imidic-acid tautomer")


# ------------------------------------------------ 4. energy column

def test_homo_lumo_gaps_are_physical() -> None:
    rows = _load("xtb_descriptors_b100.csv")
    if not rows:
        pytest.skip("descriptors missing")
    gaps = []
    for r in rows:
        v = (r.get("homo_lumo_gap_ev") or "").strip()
        if not v:
            continue
        gaps.append(float(v))
    assert gaps, "no HOMO-LUMO gaps parsed"
    assert all(0.0 < g < 30.0 for g in gaps), (
        f"nonphysical gaps present: "
        f"{[g for g in gaps if not (0 < g < 30)][:5]}; the orbital table's eV "
        f"column must not be multiplied by 27.211")


def test_dipoles_are_in_a_physical_range() -> None:
    rows = _load("xtb_descriptors_b100.csv")
    if not rows:
        pytest.skip("descriptors missing")
    bad = []
    for r in rows:
        v = (r.get("dipole_D") or "").strip()
        if not v:
            continue
        d = float(v)
        if not (0.0 <= d <= 20.0):
            bad.append((r["name"], d))
    assert not bad, f"implausible dipoles: {bad[:5]}"
