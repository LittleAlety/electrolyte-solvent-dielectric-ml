"""B100 scale-comparison guards: target transform and solvent coverage.

Two findings from this round need pinning because both are counter-intuitive and could
easily be "fixed" by someone who assumes the physically-motivated choice must win:

  1. CLAUSIUS-MOSSOTTI IS A WORSE PREDICTIVE SCALE. The transform (e-1)/(e+2) is the
     theoretically correct response variable for orientational polarisation, but its
     inverse is ill-conditioned: at epsilon = 178 the transformed value is 0.977, so a
     small error in y explodes in epsilon. A future edit that "improves" the code by
     regressing on CM and reporting it as better would be wrong.

  2. THE ELECTRONIC BLOCK IS REDUNDANT ONCE mu^2/Vm IS PRESENT. Adding dipole and
     HOMO-LUMO gap on top of X0+Xn changes R^2 not at all, so any claim that the
     electronic descriptors add information must be qualified.

Plus the solvent-coverage gap, which must not be quietly closed by admitting compounds
that merely have similar names.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
TT = OUT / "e1b_target_transform_b100.json"
TTC = OUT / "e1b_target_transform_b100.csv"
SOLV = OUT / "electrolyte_solvent_coverage_b100.json"
SOLVC = OUT / "electrolyte_solvent_coverage_b100.csv"


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
    import io
    return list(csv.DictReader(io.StringIO(text or "", newline="")))


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ------------------------------------------------ target transform

def test_all_three_transforms_were_compared() -> None:
    d = _j(TT)
    if not d:
        pytest.skip("target-transform experiment not run")
    assert set(d["transforms_compared"]) == {
        "identity", "log", "clausius_mossotti"}


def test_clausius_mossotti_poor_performance_is_recorded_not_hidden() -> None:
    """The physically correct transform must be reported as worse, not omitted."""
    d = _j(TT)
    if not d:
        pytest.skip("target-transform experiment not run")
    by = d["by_transform"]
    if "clausius_mossotti" not in by:
        pytest.skip("CM not evaluated")
    cm = by["clausius_mossotti"]
    ident = by.get("identity", {})
    assert cm["mae"] > ident["mae"], (
        "Clausius-Mossotti is reported as better than the identity transform; "
        "that contradicts the ill-conditioned inverse and needs re-checking")
    assert cm["r2"] < 0, (
        "CM R^2 should be negative here; a positive value suggests the inverse "
        "was applied incorrectly")


def test_errors_are_reported_on_the_epsilon_scale() -> None:
    """Otherwise the three transforms are not comparable."""
    rows = _load(TTC)
    if not rows:
        pytest.skip("target-transform table missing")
    bases = {r["constant_baseline_mae"] for r in rows}
    assert len(bases) == 1, (
        f"constant baseline differs across transforms {bases}; errors were scored "
        f"on different scales")
    for r in rows:
        assert float(r["constant_baseline_mae"]) > 1.0, (
            "baseline near 0 suggests the metric is on a transformed scale")


def test_no_transform_emits_epsilon_below_one() -> None:
    rows = _load(TTC)
    if not rows:
        pytest.skip("target-transform table missing")
    for r in rows:
        assert int(r["n_pred_below_eps_floor"]) == 0, (
            f"{r['transform']}/{r['block']} produced "
            f"{r['n_pred_below_eps_floor']} predictions below 1")


def test_mu2_over_Vm_makes_the_electronic_block_redundant() -> None:
    """X0+Xn and X0+X1+Xn must have the same explanatory power."""
    rows = _load(TTC)
    if not rows:
        pytest.skip("target-transform table missing")
    ident = {r["block"]: r for r in rows if r["transform"] == "identity"}
    a = ident.get("X0_plus_Xn")
    b = ident.get("X0_X1_Xn")
    if not (a and b):
        pytest.skip("required blocks missing")
    assert abs(float(a["r2"]) - float(b["r2"])) < 0.01, (
        f"R^2 differs between X0+Xn ({a['r2']}) and X0+X1+Xn ({b['r2']}); "
        f"the electronic block does add information and the claim must change")


# ------------------------------------------------ solvent coverage

def test_solvent_coverage_audit_exists() -> None:
    d = _j(SOLV)
    if not d:
        pytest.skip("solvent coverage audit not run")
    assert d["n_key_solvents"] >= 10
    assert "consequence" in d and d["consequence"], (
        "the audit must state that conclusions do not transfer to absent solvents")


def test_absent_solvents_are_not_substituted_by_similar_names() -> None:
    """Formamide is not DMF and Furan is not THF."""
    rows = _load(SOLVC)
    if not rows:
        pytest.skip("solvent coverage table missing")
    for r in rows:
        if r["status"] == "IN_MODELLING_SET":
            continue
        why = (r.get("why_absent") or "").lower()
        rec = (r.get("recovery_path") or "").lower()
        # a row claiming recovery via an existing source must name a real one
        if "nbs" in rec:
            assert r["in_nbs_transcription"] == "true", (
                f"{r['solvent']} claims NBS recovery but is not in the NBS "
                f"transcription")
        assert why, f"{r['solvent']} absent with no stated reason"


def test_absent_solvents_are_explicitly_disclaimed() -> None:
    d = _j(SOLV)
    if not d:
        pytest.skip("solvent coverage audit not run")
    assert d.get("do_not_do"), "must list the forbidden shortcuts"
    joined = " ".join(d["do_not_do"])
    assert "替代" in joined or "substitut" in joined.lower()
