"""Guard the shared gate-flag vocabulary against silent drift.

`nbs514_circular_514` shipped in the committed v0.2 dataset while being absent
from `GATE_FLAGS`.  Nothing failed, because no check compared a dataset's flags
against the enum, so the dataset was only accidentally consistent with the
validators that test membership in it.  These tests close that loop.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from verify_dielectric_v02 import check_gate_flag_vocabulary

from electrolyte_ml.standardize import GATE_FLAGS


def _v02_rows() -> list[dict[str, str]]:
    path = REPOSITORY_ROOT / "data" / "dielectric_v02.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_new_labels_are_registered() -> None:
    assert "nbs514_circular_514" in GATE_FLAGS
    assert "crosscheck_only" in GATE_FLAGS


def test_provenance_restrictions_are_not_gate_flags() -> None:
    # These are dedicated columns in the manual-entry schema; duplicating them
    # in the flag vocabulary would create a second source of truth.
    assert "closed_source" not in GATE_FLAGS
    assert "non_redistributable" not in GATE_FLAGS


def test_vocabulary_has_no_duplicates() -> None:
    assert len(GATE_FLAGS) == len(set(GATE_FLAGS))


def test_committed_v02_uses_only_registered_flags() -> None:
    check = check_gate_flag_vocabulary(_v02_rows())
    assert check.passed, check.detail


def test_check_rejects_an_unregistered_flag() -> None:
    rows = [{"gate_flags": "zero_frequency|invented_label"}]
    check = check_gate_flag_vocabulary(rows)
    assert not check.passed
    assert "invented_label" in check.detail


def test_check_accepts_the_real_labels() -> None:
    rows = [
        {"gate_flags": "zero_frequency|pure_component|nbs514_circular_514"},
        {"gate_flags": "crosscheck_only"},
    ]
    check = check_gate_flag_vocabulary(rows)
    assert check.passed, check.detail
