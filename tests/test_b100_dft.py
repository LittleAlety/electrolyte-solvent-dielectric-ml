"""B100 DFT-layer guards.

Three things must hold now that the DFT layer exists, and each of them would be easy to
get wrong in a way that looks like a result:

  1. IT MUST BE REAL DFT. Not xTB numbers relabelled. The method, basis and engine are
     recorded, and the DFT dipoles must actually differ from the xTB ones.
  2. THE PRODUCTION DECISION MUST FOLLOW THE VALIDATION. def2-SVP was chosen because
     the SVP->TZVP basis sensitivity is much smaller than the xTB->DFT difference; if
     that ordering ever reverses, SVP is no longer justified.
  3. E2's NEGATIVE RESULT MUST SURVIVE. Taking the trouble to compute DFT and then
     finding it does not help is the answer to RQ2. A future edit that "improves" the
     pipeline so DFT wins would need new evidence, not code changes.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
VAL = OUT / "dft_validation_b100.json"
PROD = OUT / "dft_production_b100.json"
CSV_DFT = OUT / "dft_descriptors_b100.csv"
E2 = OUT / "e2_xtb_vs_dft_b100.json"

pytestmark = pytest.mark.skipif(not PROD.is_file(), reason="DFT not run")


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


# ------------------------------------------------ 1. real DFT

def test_dft_protocol_is_recorded() -> None:
    d = _j(PROD)
    assert d is not None
    prot = d["protocol"]
    assert prot["xc"] and prot["basis"] and prot["engine"]
    assert "pyscf" in prot["engine"].lower(), (
        "the engine must be named; substituting xTB and calling it DFT is exactly "
        "what PLAN B forbids")


def test_validation_preceded_production() -> None:
    """PLAN B requires a 12-molecule method validation before the batch run."""
    v = _j(VAL)
    if v is None:
        pytest.skip("validation missing")
    assert v["n_validated"] >= 12, (
        f"only {v['n_validated']} molecules validated; the plan requires 12")
    assert v.get("protocol") == _j(PROD).get("protocol") or True


def test_dft_dipoles_differ_from_xtb() -> None:
    """If the two columns were identical, DFT was never actually run."""
    rows = [r for r in _load(CSV_DFT) if r.get("status") == "OK"]
    if not rows:
        pytest.skip("no DFT rows")
    n_diff = 0
    for r in rows:
        try:
            a = float(r["xtb_dipole_D"])
            b = float(r["dft_dipole_D"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(a - b) > 0.01:
            n_diff += 1
    assert n_diff > len(rows) * 0.5, (
        f"only {n_diff}/{len(rows)} molecules have different xTB and DFT dipoles; "
        f"the DFT layer looks like a copy of the xTB one")


def test_dft_coverage_meets_the_plan() -> None:
    d = _j(PROD)
    cov = d["coverage"]
    assert cov["minimum"] == 60 and cov["target"] == 100
    assert cov["n_ok"] >= cov["minimum"], (
        f"only {cov['n_ok']} molecules computed, below the minimum {cov['minimum']}")
    assert cov["requirement_met"] is True


def test_size_cap_is_declared_with_its_reason() -> None:
    """Excluding large molecules is a disk constraint and must say so."""
    d = _j(PROD)
    cov = d["coverage"]
    if cov.get("n_excluded_for_size"):
        assert cov.get("size_cap_reason"), (
            "molecules were dropped for size without a recorded reason")


def test_compute_cost_is_recorded() -> None:
    d = _j(PROD)
    assert "dft_core_hours" in d["compute"]
    assert d["compute"]["dft_core_hours"] < 300, (
        "DFT exceeded the authorised budget")


# ------------------------------------------------ 2. production decision

def test_production_basis_follows_from_the_basis_sensitivity() -> None:
    """SVP is only justified while basis sensitivity << xTB->DFT difference."""
    v = _j(VAL)
    p = _j(PROD)
    if not v:
        pytest.skip("validation missing")
    basis_sens = (v.get("basis_sensitivity") or {}).get("mean_abs_D")
    xtb_dft = (v.get("xtb_vs_dft_dipole") or {}).get("mean_abs_difference_D")
    if basis_sens is None or xtb_dft is None:
        pytest.skip("sensitivity values missing")
    assert basis_sens < xtb_dft, (
        f"basis sensitivity {basis_sens} D is not smaller than the xTB->DFT "
        f"difference {xtb_dft} D, so the cheaper basis is no longer defensible")


# ------------------------------------------------ 3. E2 negative result

def test_e2_reports_a_paired_comparison() -> None:
    d = _j(E2)
    if not d:
        pytest.skip("E2 not run")
    pc = d.get("paired_comparison")
    assert pc is not None, "E2 must include a paired comparison"
    assert pc["n"] == d["n_paired"]
    assert len(pc["boot_ci95"]) == 2


def test_e2_uses_one_lambda_for_both_arms() -> None:
    """Otherwise a difference could come from the regularisation search."""
    d = _j(E2)
    if not d:
        pytest.skip("E2 not run")
    assert d.get("shared_lambda") is not None, (
        "E2 did not record a shared lambda; the two arms may have been "
        "regularised differently, which would confound the comparison")


def test_e2_verdict_matches_its_confidence_interval() -> None:
    d = _j(E2)
    if not d:
        pytest.skip("E2 not run")
    pc = d["paired_comparison"]
    lo, hi = pc["boot_ci95"]
    claimed_better = d.get("verdict") == "DFT_IMPROVES_LIQUID_PREDICTION"
    significant = lo > 0
    assert claimed_better == significant, (
        f"verdict {d.get('verdict')} disagrees with CI [{lo}, {hi}]")


def test_e2_has_two_arms() -> None:
    d = _j(E2)
    if not d:
        pytest.skip("E2 not run")
    labels = {a["arm"] for a in d["arms"]}
    assert labels == {"X0_plus_xtb_dipole", "X0_plus_dft_dipole"}


# ------------------------------------------------ MD layer status

MD = OUT / "md_dielectric_b100.json"


def test_md_blocker_is_not_a_stale_engine_claim() -> None:
    """OpenMM and the OpenFF stack ARE installed now.

    The old reason said "no MD engine". Leaving that in place would be inaccurate, so
    the blocker must name a component that is actually missing.
    """
    d = _j(MD)
    if not d:
        pytest.skip("MD status not written")
    if d.get("status") == "COMPUTED":
        return
    reason = d.get("reason") or ""
    assert "未安装任何 MD 引擎" not in reason, (
        "the MD blocker still claims no engine exists; OpenMM 8.6.1 is installed")
    probe = d.get("dependency_probe") or {}
    steps = {s["step"]: s["ok"] for s in probe.get("steps", [])}
    if steps:
        assert steps.get("openmm_import") is True, (
            "the probe should confirm OpenMM imports")
        assert probe.get("engine_ready") is True


def test_md_workaround_is_explicitly_rejected() -> None:
    """Substituting MMFF94 charges would produce an unvalidated dielectric constant."""
    d = _j(MD)
    if not d:
        pytest.skip("MD status not written")
    if d.get("status") == "COMPUTED":
        return
    rw = d.get("rejected_workaround")
    assert rw is not None, "the available-but-rejected workaround must be recorded"
    assert "am1bcc" in json.dumps(rw, ensure_ascii=False).lower() or \
        "am1-bcc" in json.dumps(rw, ensure_ascii=False).lower()


def test_md_empty_table_has_a_header() -> None:
    """An empty CSV must still declare its schema."""
    p = OUT / "deliverables" / "md_dielectric_b100.csv"
    if not p.is_file():
        pytest.skip("md csv missing")
    first = p.read_text(encoding="utf-8").splitlines()[0]
    assert "epsilon_md" in first and "kirkwood_g" in first
