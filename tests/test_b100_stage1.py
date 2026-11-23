"""B100 stage-1 guards: the qualified count must be honest.

PLAN B v6.0 sets a hard threshold of 100 independent qualified molecules and forbids
reaching it by lowering standards. The most dangerous failure mode is a number that
looks big because unverified candidates were counted as verified, or because one
molecule was counted several times through its multiple measurements.

Guarded:
  1. molecules are counted by full InChIKey, never by row
  2. a solid-at-temperature sample is never counted as a liquid
  3. a molecule with no melting point is UNKNOWN, not assumed liquid
  4. the family classifier actually distinguishes the families it claims
  5. cross-source conflicts are recorded, not averaged away
  6. the readiness report states the gap rather than hiding it
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B100 = REPO_ROOT / "outputs" / "b100"

GATE = B100 / "b100_admission_gate.json"
PHASE = B100 / "phase_state_audit_b100.json"
FAMILY = B100 / "family_coverage_b100.json"
READY = B100 / "b100_stage1_readiness.json"
REGISTRY = B100 / "molecule_registry_b100.csv"
QUALIFIED = B100 / "qualified_molecules_b100.csv"

pytestmark = pytest.mark.skipif(
    not (GATE.is_file() and PHASE.is_file() and FAMILY.is_file()),
    reason="B100 stage 1 not run yet",
)


def _load(path: Path) -> list[dict]:
    raw = path.read_bytes()
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


def _j(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- identity

def test_molecules_are_counted_by_inchikey_not_by_row() -> None:
    """One molecule with three measurements is still one molecule."""
    rows = _load(QUALIFIED)
    keys = [r["inchikey"] for r in rows]
    assert len(keys) == len(set(keys)), (
        "a molecule appears more than once in the qualified list")
    gate = _j(GATE)
    assert gate["result"]["n_qualified_molecules"] == len(set(keys))


def test_duplicate_measurements_do_not_inflate_the_count() -> None:
    """The NBS layer has 392 rows for 389 molecules; only 389 may count."""
    inv = _j(B100 / "b100_asset_inventory.json")
    exp = inv["layer_1_experimental_labels"]["nbs514_expansion"]
    assert exp["n_molecules"] < exp["n_measurement_rows"], (
        "expected some molecules to have multiple temperature rows")
    assert exp["n_duplicate_rows_same_molecule"] == (
        exp["n_measurement_rows"] - exp["n_molecules"])


# ---------------------------------------------------------------- phase

def test_solid_at_temperature_is_never_counted_as_liquid() -> None:
    phase = _j(PHASE)
    rows = _load(B100 / "phase_state_audit_b100.csv")
    for r in rows:
        if r["mp_C"] == "" or r["T_C"] == "":
            assert r["phase_status"] == "UNKNOWN_NO_MP"
            continue
        mp, t = float(r["mp_C"]), float(r["T_C"])
        if mp >= t:
            assert r["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T"
            assert r["phase_verified"] == "false", (
                f"{r['name']} is solid at its stated T but marked verified")


def test_missing_melting_point_is_unknown_not_liquid() -> None:
    """The decisive honesty rule: no mp data means no liquid claim."""
    rows = _load(B100 / "phase_state_audit_b100.csv")
    for r in rows:
        if r["mp_C"] == "":
            assert r["phase_verified"] == "false", (
                f"{r['name']} has no melting point yet is marked verified")


def test_phase_audit_covers_every_qualified_molecule() -> None:
    """The first pass only covered 22 molecules; that is the defect being guarded."""
    q = {(r.get("inchikey") or "").strip() for r in _load(QUALIFIED)}
    p = {(r.get("inchikey") or "").strip()
         for r in _load(B100 / "phase_state_audit_b100.csv")}
    missing = q - p
    assert not missing, (
        f"{len(missing)} qualified molecules have no phase audit: "
        f"{list(missing)[:3]}")


# ---------------------------------------------------------------- families

def test_amine_family_is_not_empty_when_amines_exist() -> None:
    """A comma-splitting bug once made this family count zero.

    The check must exclude nitro/nitrate compounds: RDKit's amine pattern matches the
    nitro nitrogen (NX3), so counting every "amine-containing" molecule would demand
    that nitro compounds be labelled amines -- the opposite of correct. What matters
    is that genuine amines are classified as amine.
    """
    reg = _load(REGISTRY)
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    amine = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O)]")
    nitro = Chem.MolFromSmarts("[$([NX3](=O)=O),$([N+](=O)[O-])]")
    genuine = 0
    for r in reg:
        smi = r.get("smiles") or ""
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None or amine is None:
            continue
        if not mol.HasSubstructMatch(amine):
            continue
        # a nitro/nitrate nitrogen is not an amine
        if nitro is not None and mol.HasSubstructMatch(nitro):
            continue
        genuine += 1
    assigned = sum(1 for r in reg if r.get("family") == "amine")
    if genuine > 0:
        assert assigned > 0, (
            f"{genuine} molecules contain a genuine amine group but none are "
            f"classified as amine -- the SMARTS list is probably split on commas")
        assert assigned >= genuine * 0.5, (
            f"only {assigned} of {genuine} genuine amine-containing molecules "
            f"were assigned to the amine family")


def test_every_registry_row_has_a_structure_or_a_reason() -> None:
    reg = _load(REGISTRY)
    for r in reg:
        if not r.get("smiles"):
            assert r["family"].startswith("UNCLASSIFIED"), (
                f"{r['name']} has no SMILES but was assigned family "
                f"{r['family']}")


def test_family_coverage_reports_gaps_honestly() -> None:
    fam = _j(FAMILY)
    rows = fam["family_coverage"]
    for b in rows:
        assert b["gap_to_low"] >= 0
        if b["n_phase_verified"] < b["target_low"]:
            assert b["meets_target_low"] is False
            assert b["gap_to_low"] == b["target_low"] - b["n_phase_verified"]


# ---------------------------------------------------------------- conflicts

def test_cross_source_conflicts_are_recorded_not_averaged() -> None:
    gate = _j(GATE)
    cs = gate["cross_source_check"]
    assert cs["n_molecules_in_both_layers"] == cs["n_agree"] + cs["n_conflict"]
    conflicts = _load(B100 / "cross_source_conflict_b100.csv")
    assert len(conflicts) == cs["n_conflict"]
    # a conflicted molecule must not be silently admitted
    for c in conflicts:
        assert c["core_epsilon"] and c["nbs_epsilon"], (
            "a conflict record must keep BOTH values")
        assert c["verdict"] != "AGREE"


# ---------------------------------------------------------------- threshold

def test_threshold_is_reported_with_its_gap() -> None:
    if not READY.is_file():
        pytest.skip("readiness report not built")
    r = _j(READY)
    hn = r["hard_numbers"]
    assert hn["hard_threshold"] == 100
    assert hn["gap"] == max(0, hn["hard_threshold"]
                            - hn["phase_verified_liquid_now"])
    assert hn["meets_threshold"] == (
        hn["phase_verified_liquid_now"] >= hn["hard_threshold"])


def test_readiness_states_forbidden_shortcuts() -> None:
    if not READY.is_file():
        pytest.skip("readiness report not built")
    r = _j(READY)
    forbidden = " ".join(r["paths_to_close_the_gap"]["explicitly_forbidden"])
    assert "降低准入标准" in forbidden
    assert "默认当作液态" in forbidden
    assert "独立分子" in forbidden
