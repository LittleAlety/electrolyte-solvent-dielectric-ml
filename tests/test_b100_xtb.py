"""B100 xTB-coverage guards: one protocol, no substitutions.

The objective requires unified xTB coverage of >=100 molecules and forbids
substituting one level of theory for another. Two failure modes matter here:

  1. MIXED PROTOCOLS. If some rows came from GFN1 and others from GFN2, or from a
     different optimisation setting, the descriptor column is not one quantity.
  2. SILENT FILLING. A failed optimisation must not become a plausible-looking
     number; it must be ERROR and counted as missing.

Guarded:
  1. every row records the protocol id and a status
  2. no ERROR row carries a finite descriptor value
  3. coverage is counted only over usable rows
  4. the protocol command is the same string everywhere
  5. the binary and its hash are recorded so the run is reproducible
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
COV = OUT / "xtb_coverage_b100.json"
DESC = OUT / "xtb_descriptors_b100.csv"

pytestmark = pytest.mark.skipif(
    not (COV.is_file() and DESC.is_file()),
    reason="B100 xTB coverage not built yet",
)

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


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


def _j() -> dict:
    return json.loads(COV.read_text(encoding="utf-8"))


def test_protocol_is_single_and_recorded() -> None:
    p = _j()["protocol"]
    assert p["id"]
    assert "gfn 2" in p["command"].lower().replace("-", " ")
    assert p["binary_sha256"], "binary hash missing; run not reproducible"
    assert p["why_unified"]


def test_no_row_mixes_protocols() -> None:
    rows = _load(DESC)
    ids = {r.get("protocol", "") for r in rows}
    assert ids == {_j()["protocol"]["id"]}, (
        f"multiple protocols present in one descriptor table: {ids}")


def test_error_rows_carry_no_descriptor_value() -> None:
    """A failed optimisation must not look like a computed number."""
    rows = _load(DESC)
    for r in rows:
        if r.get("status") == "ERROR":
            for col in ("dipole_D", "polarizability_au", "homo_lumo_gap_ev",
                        "total_energy_hartree"):
                v = (r.get(col) or "").strip()
                assert v.lower() in PLACEHOLDERS, (
                    f"{r['name']} failed ({r.get('error')}) yet has "
                    f"{col}={v}")


def test_coverage_counts_only_usable_rows() -> None:
    cov = _j()["coverage"]
    rows = _load(DESC)
    n_ok = sum(1 for r in rows
               if r.get("status") in ("EXISTING", "OK", "CACHED"))
    assert cov["n_with_xtb"] == n_ok, (
        "coverage number does not equal the number of usable rows")
    assert cov["requirement_met"] == (n_ok >= cov["requirement_min"])


def test_threshold_is_the_stated_one() -> None:
    cov = _j()["coverage"]
    assert cov["requirement_min"] == 100


def test_every_usable_row_has_a_dipole() -> None:
    rows = _load(DESC)
    for r in rows:
        if r.get("status") in ("EXISTING", "OK", "CACHED"):
            v = (r.get("dipole_D") or "").strip()
            assert v.lower() not in PLACEHOLDERS, (
                f"{r['name']} is marked usable but has no dipole moment")
            float(v)     # must parse


def test_failures_are_enumerated_not_hidden() -> None:
    cov = _j()
    rows = _load(DESC)
    n_err_rows = sum(1 for r in rows if r.get("status") == "ERROR")
    assert len(cov["failures"]) == n_err_rows


def test_molecules_are_unique() -> None:
    rows = _load(DESC)
    keys = [r["inchikey"] for r in rows]
    assert len(keys) == len(set(keys)), "duplicate molecule in xTB table"


def test_existing_run_is_labelled_as_existing() -> None:
    """Reusing the earlier uniform run is fine, but it must be visible."""
    rows = _load(DESC)
    sources = Counter(r.get("source", "") for r in rows)
    assert "EXISTING_UNIFIED_RUN" in sources or "NEWLY_COMPUTED" in sources
    for r in rows:
        assert r.get("source"), f"{r['name']} has no provenance label"
