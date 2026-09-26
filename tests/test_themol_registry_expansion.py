"""Offline tests for the W17-17 THEMol registry-wide orbital expansion.

The roster is frozen before the run, so its literals are pinned here.  The
delivered row count is not pinned: the arm reports `run_status` as `complete`
or `partial` and the tests hold it to whichever one its own numbers imply, so
a throttled night shows up as `partial` instead of being rounded up to done.

Nothing here touches the network or xTB.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

ROSTER = REPOSITORY_ROOT / "probes/themol_registry_expansion_roster.csv"
ROSTER_SUMMARY = REPOSITORY_ROOT / "probes/themol_registry_expansion_roster_summary.json"
PREREG = REPOSITORY_ROOT / "probes/themol_registry_expansion_prereg.json"
LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
SUMMARY = REPOSITORY_ROOT / "probes/themol_orbital_layer_expanded_summary.json"
VERIFIER = REPOSITORY_ROOT / "scripts/verify_themol_orbital_layer_expanded.py"
ROSTER_BUILDER = REPOSITORY_ROOT / "probes/build_themol_registry_expansion_roster.py"
LAYER_BUILDER = REPOSITORY_ROOT / "probes/build_themol_orbital_layer_expanded.py"
PRIOR_LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer.csv"

ROSTER_SHA256 = "71277d2c2607dfc5efb31654e2bb668a2618ef6e830073c4aea7fcb48d0136d6"
ROSTER_ROWS = 5117
REGISTRY_ROWS = 31949
NOT_IN_THEMOL = 26830
UNPARSABLE = 2
ROSTER_BYTES = 956973
TIER_ORDER = ["no_reference_orbital", "flagship_dielectric", "named_core_channel", "calibration_bulk"]
ROWS_BY_TIER = {
    "no_reference_orbital": 421,
    "flagship_dielectric": 54,
    "named_core_channel": 68,
    "calibration_bulk": 4574,
}
PRIOR_LAYER_SHA256 = "6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80"

EXPECTED_LAYER_COLUMNS = [
    "inchikey", "name", "smiles", "canonical_smiles", "expansion_tier",
    "structure_check", "in_epsilon_roster", "epsilon", "has_reference_orbital",
    "themol_uuid", "themol_h5_file", "natoms", "geometry_sha256",
    "source_dataset", "source_level", "source_license", "xtb_version",
    "unit_check", "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV",
    "batt_homo_eV", "batt_lumo_eV", "batt_gap_eV",
    "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV", "gfn2_minus_batt_gap_eV",
    "gfn2_minus_pubchemqc_homo_eV", "gfn2_minus_pubchemqc_lumo_eV",
    "calib_homo_eV", "calib_lumo_eV", "calibration_id", "role",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_roster_digest_is_the_frozen_one() -> None:
    assert ROSTER.stat().st_size == ROSTER_BYTES
    assert sha256_file(ROSTER) == ROSTER_SHA256


def test_prereg_locks_the_same_roster_and_calls_itself_a_plan() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "locked_before_run"
    assert prereg["is_a_plan_not_a_measurement"] is True
    assert prereg["queries_executed"] == 0
    assert prereg["inputs"]["target_roster"]["sha256"] == ROSTER_SHA256
    assert prereg["inputs"]["target_roster"]["rows"] == ROSTER_ROWS


def test_roster_counts_match_the_frozen_summary() -> None:
    summary = json.loads(ROSTER_SUMMARY.read_text(encoding="utf-8"))
    rows = read_rows(ROSTER)
    assert len(rows) == ROSTER_ROWS == summary["roster_rows"]
    assert summary["roster_sha256"] == ROSTER_SHA256
    assert summary["counters"]["registry_rows"] == REGISTRY_ROWS
    assert summary["counters"]["not_in_themol"] == NOT_IN_THEMOL
    assert summary["counters"]["unparsable_smiles"] == UNPARSABLE
    assert summary["counters"]["matched"] == ROSTER_ROWS
    assert summary["rows_by_tier"] == ROWS_BY_TIER
    assert summary["is_a_plan_not_a_measurement"] is True
    assert summary["queries_executed"] == 0


def test_every_roster_row_is_a_keyed_themol_hit() -> None:
    rows = read_rows(ROSTER)
    assert {row["expansion_tier"] for row in rows} <= set(TIER_ORDER)
    assert all(row["inchikey"] for row in rows)
    assert all(row["themol_uuid"] for row in rows)
    assert all(row["themol_h5_file"].startswith("hessian_") for row in rows)
    assert [int(row["expansion_order"]) for row in rows] == list(range(1, ROSTER_ROWS + 1))
    keys = [row["inchikey"] for row in rows]
    assert len(set(keys)) == len(keys)


def test_tier_ordering_is_priority_order() -> None:
    rows = read_rows(ROSTER)
    rank = {tier: position for position, tier in enumerate(TIER_ORDER)}
    seen = [rank[row["expansion_tier"]] for row in rows]
    assert seen == sorted(seen)


def test_roster_builder_check_reproduces_the_bytes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROSTER_BUILDER), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_prior_arm_layer_is_untouched() -> None:
    assert sha256_file(PRIOR_LAYER) == PRIOR_LAYER_SHA256


def test_layer_header_matches_the_verifier_contract() -> None:
    with LAYER.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == EXPECTED_LAYER_COLUMNS


def test_layer_builder_and_verifier_agree_on_the_frozen_constants() -> None:
    builder = LAYER_BUILDER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    shared_literals = (
        'SOURCE_DATASET = "ByteDance-Seed/THEMol (Hessian subset) + GFN2-xTB 6.7.1"',
        'SOURCE_LEVEL = "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"',
        'SOURCE_LICENSE = "THEMol CC BY-NC 4.0; derived values non-commercial"',
        'CALIBRATION_ID = "themol_gfn2_to_batt_2fold_v2_registry_wide"',
    )
    for constant in shared_literals:
        assert constant in builder, constant
        assert constant in verifier, constant
    # The builder imports the two gates from the W17-14 module rather than
    # restating them, so the agreement is checked through that import.
    for gate in ("MAE_LIMIT_EV = 0.35", "R_LIMIT = 0.80"):
        assert gate in verifier, gate
    assert "from probes.build_themol_orbital_layer import (" in builder
    from probes.build_themol_orbital_layer import MAE_LIMIT_EV, MIN_PAIRED_N, R_LIMIT

    assert (MAE_LIMIT_EV, R_LIMIT, MIN_PAIRED_N) == (0.35, 0.80, 40)


def test_layer_summary_is_internally_consistent() -> None:
    rows = read_rows(LAYER)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["delivered_rows"] == len(rows)
    assert summary["roster_rows"] == ROSTER_ROWS
    assert summary["roster"]["sha256"] == ROSTER_SHA256
    expected = "complete" if len(rows) == ROSTER_ROWS else "partial"
    assert summary["run_status"] == expected
    assert summary["models_fitted"] == 0
    assert summary["harvest"]["rows_off_roster"] == 0
    assert summary["structure_check"]["inchikey_mismatch"] == 0
    assert summary["structure_check"]["smiles_unparsable"] == 0
    assert set(summary["roles"]) <= {
        "paired_anchor",
        "calibrated_estimate",
        "uncalibrated_reference",
    }


def test_verifier_recomputes_the_layer_without_the_builder() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


@pytest.mark.skipif(
    not (REPOSITORY_ROOT / "data/raw/themol/expand").exists(),
    reason="the raw expansion harvest is git-ignored and absent in CI",
)
def test_raw_harvest_only_contains_roster_keys() -> None:
    roster_keys = {row["inchikey"] for row in read_rows(ROSTER)}
    observed: set[str] = set()
    for path in sorted((REPOSITORY_ROOT / "data/raw/themol/expand").glob("shard_*.csv")):
        for row in read_rows(path):
            key = (row.get("inchikey") or "").strip()
            if key:
                observed.add(key)
    assert observed <= roster_keys
