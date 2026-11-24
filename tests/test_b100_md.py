"""B100 MD-layer guards.

The MD layer produces numbers that are easy to believe and hard to trust, so the
guards here are mostly about NOT over-claiming:

  1. THE PLATFORM MUST ACTUALLY BE A REAL ONE. The pip OpenMM build registers only
     Reference and segfaults on this system; results must come from the conda env's CPU
     platform. A run on Reference would be both slow and unsound here.
  2. DENSITY MUST BE PHYSICAL. A unit slip in the density formula reported 8.9e8 kg/m3
     for ethanol -- six orders of magnitude out -- and nothing caught it until the
     number was read. Density is now checked against a physical band per system.
  3. EPSILON_MD MUST NOT BE PRESENTED AS AN EXPERIMENTAL REPLACEMENT. A fixed-charge
     model under-predicts epsilon for hydrogen-bonded liquids; the ratio check makes the
     underestimate explicit instead of letting a reader mistake it for agreement.
  4. THE CONVERGENCE CAVEAT MUST TRAVEL WITH THE RESULT.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
MD = OUT / "md_dielectric_b100.json"
MDC = OUT / "md_dielectric_b100.csv"


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
    header = (text or "").splitlines()[0] if (text or "").splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text or "", newline=""), delimiter=delim))


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _doc():
    d = _j(MD)
    if not d:
        pytest.skip("MD status not written")
    return d


def _ok_rows():
    d = _doc()
    rows = [r for r in (d.get("results") or []) if r.get("status") == "OK"]
    if not rows:
        pytest.skip("MD has no successful systems yet")
    return rows


# ------------------------------------------------ status honesty

def test_md_status_is_consistent_with_its_results() -> None:
    d = _doc()
    ok = [r for r in (d.get("results") or []) if r.get("status") == "OK"]
    if ok:
        assert d["status"] == "COMPUTED"
        assert d["n_ok"] == len(ok)
    else:
        assert d["status"] == "NOT_COMPUTED"
        assert d["n_ok"] == 0


def test_md_requirement_matches_the_plan() -> None:
    """PLAN B requires >= 12 liquid systems."""
    d = _doc()
    assert d["target"]["minimum"] == 12
    assert d["requirement_met"] == (d["n_ok"] >= 12)


# ------------------------------------------------ platform

def test_md_ran_on_a_real_platform() -> None:
    d = _doc()
    plat = (d.get("engine") or {}).get("platform")
    if not plat:
        pytest.skip("platform not recorded")
    avail = (d.get("engine") or {}).get("available_platforms") or []
    assert plat in avail, (
        f"platform {plat} is not among the registered platforms {avail}")
    assert "Reference" != plat or "CPU" not in avail, (
        "the run used Reference even though a CPU platform was available; "
        "Reference segfaults on this system")


# ------------------------------------------------ physics sanity

def test_density_is_physical() -> None:
    """Organic liquids sit roughly 500-2000 kg/m3.

    A unit slip in the box-mass formula gave 8.9e8 kg/m3 and nothing flagged it.
    """
    for r in _ok_rows():
        rho = r.get("density_kg_m3")
        assert rho is not None, f"{r.get('system')} has no density"
        assert 300.0 < float(rho) < 2500.0, (
            f"{r.get('system')} has density {rho} kg/m3, outside the physical range "
            f"for an organic liquid")


def test_epsilon_md_is_above_one() -> None:
    for r in _ok_rows():
        assert float(r["epsilon_md"]) >= 1.0, (
            f"{r.get('system')} has epsilon_md < 1, which a condensed phase cannot have")


def test_epsilon_md_is_not_claimed_to_match_experiment() -> None:
    """A fixed-charge model under-predicts eps for H-bonded liquids; say so."""
    d = _doc()
    if not d.get("results"):
        pytest.skip("no results")
    limits = " ".join(d.get("limits") or [])
    assert "低估" in limits or "under" in limits.lower(), (
        "the documented limits must state that the model under-predicts epsilon")


def test_convergence_caveat_is_recorded() -> None:
    d = _doc()
    joined = " ".join(d.get("limits") or [])
    assert "收敛" in joined or "converg" in joined.lower(), (
        "the slow convergence of the dielectric constant must be stated")


def test_declared_calibration_is_present() -> None:
    """The density is an input, calibrated by one stated constant."""
    d = _doc()
    cal = d.get("declared_calibration")
    assert cal is not None, "the volume calibration must be declared"
    assert cal.get("liquid_volume_factor") is not None
    assert cal.get("meaning")


# ------------------------------------------------ file shape

def test_md_csv_schema_matches_the_json_fields() -> None:
    rows = _load(MDC)
    if not rows:
        # header-only is legitimate while nothing has been computed
        first = (MDC.read_text(encoding="utf-8").splitlines() or [""])[0]
        assert "epsilon_md" in first and "kirkwood_g" in first
        return
    for r in rows:
        assert "epsilon_md" in r and "kirkwood_g" in r


def test_energy_or_step_count_is_recorded() -> None:
    """A result without its sampling length cannot be judged."""
    for r in _ok_rows():
        assert r.get("production_ps"), f"{r.get('system')} lacks production_ps"
        assert r.get("n_molecules"), f"{r.get('system')} lacks n_molecules"
