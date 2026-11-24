"""B100 conformer-analysis guards.

The question is whether one embedded conformer represents a flexible molecule's
dipole moment. The measure is a Boltzmann average over GFN2-optimised conformers.

The subtle failure mode here is arithmetic rather than chemical: a near-zero dipole
makes relative deviations explode. For n-dodecane the absolute spread was 0.027 D but
the relative deviation came out at 1.95 (195%) simply because the mean dipole is
~0.01 D. Reporting that as "single conformer unreliable" would manufacture a finding
out of a division by zero.

Guarded:
  1. non-polar molecules are separated, not counted as unreliable
  2. the polar floor is stated in the manifest
  3. relative-deviation arithmetic is consistent with the reported absolutes
  4. every analysed molecule records its conformer count
  5. the reliability fraction is computed over polar molecules only
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
CSV = OUT / "conformer_ensemble_b100.csv"
MAN = OUT / "conformer_ensemble_b100.json"

pytestmark = pytest.mark.skipif(
    not (CSV.is_file() and MAN.is_file()),
    reason="conformer analysis not run yet",
)


def _load() -> list[dict]:
    raw = CSV.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    import io
    return list(csv.DictReader(io.StringIO(text or "", newline="")))


def _man() -> dict:
    return json.loads(MAN.read_text(encoding="utf-8"))


def test_nonpolar_molecules_are_not_labelled_unreliable() -> None:
    """A ~0 D molecule cannot be conformationally sensitive in its dipole."""
    floor = _man()["polar_floor_D"]
    for r in _load():
        if r.get("status") != "OK":
            continue
        try:
            b = float(r["boltzmann_dipole"])
            s = float(r["single_conformer_dipole"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(b) < floor and abs(s) < floor:
            assert r["verdict"] == "NONPOLAR_CONFORMATION_INSENSITIVE", (
                f"{r['name']} has |dipole| < {floor} D on both sides but is "
                f"labelled {r['verdict']}; the relative-deviation test is "
                f"meaningless near zero")


def test_polar_floor_is_declared() -> None:
    m = _man()
    assert "polar_floor_D" in m
    assert m["polar_floor_D"] > 0
    assert m["n_nonpolar_insensitive"] >= 0


def test_relative_deviation_matches_the_absolute_numbers() -> None:
    """Checked only for POLAR molecules.

    For a dipole near 0.01 D, rounding the two values to 4 decimal places changes
    their ratio by more than the tolerance -- the same near-zero artefact that made
    the verdict rule need a polar floor.
    """
    floor = _man()["polar_floor_D"]
    for r in _load():
        if r.get("status") != "OK":
            continue
        try:
            b = float(r["boltzmann_dipole"])
            s = float(r["single_conformer_dipole"])
            dev = float(r["single_vs_boltzmann_rel_dev"])
        except (KeyError, TypeError, ValueError):
            continue
        if b == 0 or abs(b) < floor:
            continue
        expected = abs(s - b) / abs(b)
        assert abs(dev - expected) < 0.01, (
            f"{r['name']}: reported dev {dev} but |s-b|/|b| = {expected}")


def test_each_analysed_molecule_records_conformer_counts() -> None:
    for r in _load():
        assert r.get("n_conformers_found", "") != "", (
            f"{r['name']} has no conformer count")
        if r.get("status") == "OK":
            assert int(r["n_conformers_converged"]) >= 2, (
                f"{r['name']} marked OK with fewer than 2 converged conformers")


def test_two_conformer_questions_are_counted_separately() -> None:
    """Spread and single-vs-Boltzmann are different questions.

    The earlier version merged them and quoted the spread count as if it were the
    single-conformer count (30/36 vs the true 20/36), overstating the finding.
    """
    m = _man()
    for key in ("n_conformer_spread_large", "n_single_conformer_off"):
        assert key in m, f"{key} not reported"
        assert m[key] >= 0
    # the single-conformer criterion is the stricter one and must not exceed the
    # spread count
    assert m["n_single_conformer_off"] <= m["n_conformer_spread_large"], (
        "more molecules deviate from the Boltzmann average than have a large "
        "spread, which is logically impossible")
    assert "metric_clarification" in m


def test_reliability_fraction_uses_polar_molecules_only() -> None:
    m = _man()
    rows = _load()
    polar = [r for r in rows
             if r.get("verdict") in ("SINGLE_CONFORMER_RELIABLE",
                                     "SINGLE_CONFORMER_UNRELIABLE")]
    n_rel = sum(1 for r in polar if r["verdict"] == "SINGLE_CONFORMER_RELIABLE")
    n_unrel = sum(1 for r in polar
                  if r["verdict"] == "SINGLE_CONFORMER_UNRELIABLE")
    assert m["n_reliable"] == n_rel
    assert m["n_unreliable"] == n_unrel
    assert m["n_polar_analysed"] == n_rel + n_unrel


def test_target_scale_is_met() -> None:
    """PLAN B v6.0 requires at least 30 molecules in the conformer study."""
    m = _man()
    assert m["n_ok"] >= 30, (
        f"only {m['n_ok']} molecules analysed; the plan requires >= 30")


def test_sample_is_described_as_purposive() -> None:
    """The flexible-molecule sample must not be presented as random."""
    m = _man()
    assert "目的性" in m["protocol"]["sample"] or "purposive" in \
        m["protocol"]["sample"].lower()


def test_both_counts_are_restricted_to_polar_molecules() -> None:
    """A 0.01 D dipole cannot have a meaningful relative spread."""
    m = _man()
    rows = _load()
    polar = [r for r in rows
             if r.get("verdict") in ("SINGLE_CONFORMER_RELIABLE",
                                     "SINGLE_CONFORMER_UNRELIABLE")]
    n_spread = sum(1 for r in polar if r.get("conformer_spread_large") == "true")
    n_off = sum(1 for r in polar if r.get("single_conformer_off") == "true")
    assert m["n_conformer_spread_large"] == n_spread, (
        "spread count includes non-polar molecules")
    assert m["n_single_conformer_off"] == n_off
