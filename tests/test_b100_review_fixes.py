"""B100 review-response guards: four defects found by the four-agent review.

Each of these produced a number that looked like a result but was an artefact:

  1. FABRICATED MELTING POINTS. The PubChem parser fell back to "the first number in
     any string", so 85 molecules got mp = 1.0 from the "1" of "InChI=1S/...", 18 got
     2.0, 6 got 3.0. Those values certified them as liquid and produced a false
     "257 phase-verified" claim.

  2. BOILING POINTS READ AS MELTING POINTS. "157 °C @760 mm Hg" was accepted, which
     both fabricated values and wrongly excluded seven real liquids.

  3. NITRO SMARTS THAT CANNOT MATCH. RDKit represents nitro as [N+](=O)[O-], so
     `[NX3](=O)=O` never fires; the nitro family read zero and 14 nitro + 6 nitrate
     compounds were misfiled as "amine".

  4. p = 0.0. With 200 permutations the smallest attainable p is 1/201; reporting 0
     overstates the evidence.

Plus two reporting defects: a hard-coded `phase_verified="true"` column and a
hard-coded tick in the hard-gate table, neither of which could ever fail.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
MPLOOKUP = OUT / "pubchem_mp_lookup_b100.csv"
IDENT = OUT / "identity_audit_b100.json"
REGISTRY = OUT / "molecule_registry_b100.csv"
DELIV = OUT / "deliverables"


def _load(p: Path) -> list[dict]:
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


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ------------------------------------------------ 1 & 2. melting points

def test_no_melting_point_is_marked_assumed() -> None:
    """The ASSUMED_C fallback must be gone entirely."""
    rows = _load(MPLOOKUP)
    if not rows:
        pytest.skip("mp lookup missing")
    assumed = [r for r in rows if "ASSUMED" in (r.get("mp_note") or "").upper()]
    assert not assumed, (
        f"{len(assumed)} melting points came from the bare-number fallback, e.g. "
        f"{[(r['name'], r['mp_C']) for r in assumed[:5]]}")


def test_suspicious_round_melting_points_are_absent() -> None:
    """mp exactly 1.0/2.0/3.0 was the signature of the InChI-string artefact.

    A round value is only suspicious when the note is ALSO bare -- i.e. there is no
    source and no unit marker. Genuine values like adiponitrile's 3 C carry an HSDB
    attribution and must not be flagged.
    """
    rows = _load(MPLOOKUP)
    if not rows:
        pytest.skip("mp lookup missing")
    suspects = []
    for r in rows:
        v = (r.get("mp_C") or "").strip()
        if not v:
            continue
        try:
            f = float(v)
        except ValueError:
            continue
        note = (r.get("mp_note") or "").upper()
        if f in (1.0, 2.0, 3.0, -1.0):
            has_source = any(k in note for k in
                             ("HSDB", "PAC", "ILO", "OK:", "CONVERTED"))
            if not has_source:
                suspects.append((r["name"], f, r.get("mp_note")))
    assert not suspects, f"bare round melting points: {suspects[:5]}"


def test_no_boiling_point_accepted_as_melting_point() -> None:
    """A pressure qualifier means it is a boiling point."""
    rows = _load(MPLOOKUP)
    if not rows:
        pytest.skip("mp lookup missing")
    markers = ("mm hg", "mmhg", "kpa", "mpa", " atm", "torr", "@", "b.p", "760")
    bad = []
    for r in rows:
        if not (r.get("mp_C") or "").strip():
            continue
        note = (r.get("mp_note") or "").lower()
        if any(m in note for m in markers):
            bad.append((r["name"], r.get("mp_note")))
    assert not bad, f"pressure-qualified values accepted as melting points: {bad[:5]}"


def test_melting_points_are_physically_plausible() -> None:
    """Real organic liquids reach about -190 C (propene is -185.3, 1-pentene -165.2),
    so the bound must not be tighter than that or genuine values are called defects."""
    rows = _load(MPLOOKUP)
    if not rows:
        pytest.skip("mp lookup missing")
    for r in rows:
        v = (r.get("mp_C") or "").strip()
        if not v:
            continue
        f = float(v)
        assert -200.0 <= f <= 400.0, f"{r['name']} has mp={f} C"


# ------------------------------------------------ 3. nitro family

def test_nitro_family_is_not_empty_when_nitro_compounds_exist() -> None:
    reg = _load(REGISTRY)
    if not reg:
        pytest.skip("registry missing")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    patt = Chem.MolFromSmarts("[$([NX3](=O)=O),$([N+](=O)[O-])]")
    n_containing = 0
    for r in reg:
        smi = r.get("smiles") or ""
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is not None and patt is not None and mol.HasSubstructMatch(patt):
            n_containing += 1
    assigned = sum(1 for r in reg if r.get("family") == "nitro")
    if n_containing > 0:
        assert assigned > 0, (
            f"{n_containing} molecules contain a nitro group but none are "
            f"classified as nitro; the SMARTS cannot match RDKit's charged form")


def test_nitro_compounds_are_not_labelled_amine() -> None:
    reg = _load(REGISTRY)
    if not reg:
        pytest.skip("registry missing")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    nitro = Chem.MolFromSmarts("[$([NX3](=O)=O),$([N+](=O)[O-])]")
    wrong = []
    for r in reg:
        if r.get("family") != "amine":
            continue
        smi = r.get("smiles") or ""
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is not None and nitro is not None and mol.HasSubstructMatch(nitro):
            wrong.append(r["name"])
    assert not wrong, (
        f"{len(wrong)} nitro compounds are still labelled amine: {wrong[:5]}")


# ------------------------------------------------ 4. p-value floor

def test_permutation_p_values_respect_the_plus_one_floor() -> None:
    e1 = _j(OUT / "e1_manifest_b100.json")
    if not e1:
        pytest.skip("E1 manifest missing")
    for b in e1["blocks"]:
        n = b.get("n_permutations")
        floor = b.get("p_value_floor")
        if n and floor:
            assert b["p_feature_permutation"] >= floor - 1e-9, (
                f"{b['block']}: p={b['p_feature_permutation']} is below the "
                f"attainable floor {floor}")
            assert b["p_label_permutation"] >= floor - 1e-9


def test_no_p_value_is_exactly_zero() -> None:
    e1 = _j(OUT / "e1_manifest_b100.json")
    if not e1:
        pytest.skip("E1 manifest missing")
    for b in e1["blocks"]:
        assert b["p_feature_permutation"] > 0.0, (
            f"{b['block']} reports p=0.0, which is arithmetically impossible "
            f"with a finite permutation count")


# ------------------------------------------------ 5. duplicates

def test_duplicate_substances_are_recorded() -> None:
    d = _j(IDENT)
    if not d:
        pytest.skip("identity audit missing")
    dup = d.get("duplicate_substances")
    assert dup is not None, "duplicate-substance check missing"
    assert "n_groups" in dup and "n_actionable_excess" in dup
    # cis/trans pairs must NOT be counted as actionable duplicates
    cis = [g for g in dup.get("groups", [])
           if g["kind"] == "CIS_TRANS_ISOMERS_DISTINCT"]
    if cis:
        assert dup["n_actionable_excess"] < dup["n_groups"], (
            "cis/trans pairs were counted as duplicates; they are different "
            "substances with different dipole moments")


# ------------------------------------------------ 6. no hard-coded status

def test_phase_verified_is_not_hard_coded() -> None:
    p = DELIV / "molecule_registry_b100.csv"
    if not p.is_file():
        pytest.skip("deliverables missing")
    rows = _load(p)
    src = (REPO_ROOT / "scripts" / "b100"
           / "build_b100_deliverables.py").read_text(encoding="utf-8")
    assert '"phase_verified": "true"' not in src, (
        "phase_verified is hard-coded in the deliverables builder")
    # the column must be derivable from the audit, not constant by construction
    statuses = {r.get("phase_status", "") for r in rows}
    assert statuses, "phase_status column missing"


def test_hard_gate_tick_is_derived() -> None:
    src = (REPO_ROOT / "scripts" / "b100"
           / "build_b100_deliverables.py").read_text(encoding="utf-8")
    # a literal tick in an f-string that does not depend on the comparison
    assert "| ✅ |" not in src, (
        "the hard-gate table contains a hard-coded tick that can never fail")
