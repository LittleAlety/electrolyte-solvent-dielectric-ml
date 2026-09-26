"""Offline tests for the W17-14 THEMol / GFN2-xTB orbital layer.

The pinned literals are what the pre-registration committed to before the run
plus what the run then produced.  They are written out literally rather than
recomputed so that a silent edit to the layer, the summary or the
pre-registration shows up as a failure instead of quietly re-baselining.

Nothing here touches the network or xTB.  The raw harvest under
``data/raw/themol/`` is git-ignored, so the tests that need it are skipped in
CI, which is the normal state.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer.csv"
SUMMARY = REPOSITORY_ROOT / "probes/themol_orbital_layer_summary.json"
PREREG = REPOSITORY_ROOT / "probes/themol_orbital_layer_prereg.json"
REGISTRY = REPOSITORY_ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = REPOSITORY_ROOT / "data/dielectric_v04.csv"
SECOND_SOURCE_LAYER = REPOSITORY_ROOT / "data/processed/orbital_second_source_layer.csv"
VERIFIER = REPOSITORY_ROOT / "scripts/verify_themol_orbital_layer.py"
HARVEST_DIR = REPOSITORY_ROOT / "data/raw/themol"

HARVEST_PRESENT = (HARVEST_DIR / "themol_registry_index.csv").exists()

PREREG_SHA256 = "36132f7264251269b22ae88850b581434a75b575215706153b56a680698c1959"
LAYER_SHA256 = "6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80"
REGISTRY_SHA256 = "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee"
EPSILON_SHA256 = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"

LAYER_ROWS = 166
LAYER_COLUMNS = 34
PAIRED_ANCHORS = 74
UNCALIBRATED_REFERENCE = 92
CALIBRATED_ESTIMATES = 0
ANCHOR_ROSTER_KEYS = 111
ANCHOR_HITS = 72
EPSILON_KEYS = 247
EPSILON_HITS = 142

HOMO_SLOPE = 1.0389102752198223
HOMO_INTERCEPT = 1.4879804327425656
HOMO_R = 0.8557447540814086
HOMO_MAE = 0.353095083458508
LUMO_SLOPE = 0.0903748834229043
LUMO_INTERCEPT = 1.9336417639360564
LUMO_R = 0.5295614175613801
LUMO_MAE = 0.33112379444503637
GAP_SLOPE = 0.11635116670254111
GAP_INTERCEPT = 10.749742707994933
GAP_R = 0.3072262053474138
GAP_MAE = 0.7775085413700225
HOMO_OFFSET_MEAN = -1.0595081063325675
LUMO_OFFSET_MEAN = -7.01262702330219

FETCHED_BYTES_TOTAL = 142150508
UNIT_AUDIT_N = 8

EXPECTED_COLUMNS = [
    "inchikey", "name", "smiles", "canonical_smiles", "structure_check",
    "in_epsilon_roster", "epsilon", "in_anchor_roster", "themol_uuid",
    "themol_h5_file", "natoms", "geometry_sha256", "source_dataset",
    "source_level", "source_license", "xtb_version", "unit_check",
    "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV", "batt_homo_eV",
    "batt_lumo_eV", "batt_gap_eV", "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV", "gfn2_minus_batt_gap_eV",
    "gfn2_minus_pubchemqc_homo_eV", "gfn2_minus_pubchemqc_lumo_eV",
    "calib_homo_eV", "calib_lumo_eV", "calibration_id", "role",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows() -> list[dict[str, str]]:
    with LAYER.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def number(value: str) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def test_preregistration_is_frozen() -> None:
    assert sha256_file(PREREG) == PREREG_SHA256
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["thresholds"]["mae_limit_eV"] == 0.35
    assert prereg["thresholds"]["r_limit"] == 0.80
    assert prereg["thresholds"]["inherited_from"] == "probes/orbital_second_source_prereg.json"


def test_layer_matches_its_pinned_digest() -> None:
    assert sha256_file(LAYER) == LAYER_SHA256
    assert sha256_file(REGISTRY) == REGISTRY_SHA256
    assert sha256_file(EPSILON_ROSTER) == EPSILON_SHA256


def test_layer_shape_and_columns() -> None:
    rows = load_rows()
    assert len(rows) == LAYER_ROWS
    assert list(rows[0].keys()) == EXPECTED_COLUMNS
    assert len(EXPECTED_COLUMNS) == LAYER_COLUMNS
    assert len({row["inchikey"] for row in rows}) == LAYER_ROWS


def test_coverage_against_the_rosters() -> None:
    summary = load_summary()
    assert summary["coverage"]["epsilon_roster_keys"] == EPSILON_KEYS
    assert summary["coverage"]["epsilon_roster_in_layer"] == EPSILON_HITS
    assert summary["coverage"]["anchor_roster_keys"] == ANCHOR_ROSTER_KEYS
    assert summary["coverage"]["anchor_roster_in_layer"] == ANCHOR_HITS
    with EPSILON_ROSTER.open(newline="", encoding="utf-8") as handle:
        epsilon = {row["inchikey"] for row in csv.DictReader(handle)}
    rows = load_rows()
    assert sum(1 for row in rows if row["inchikey"] in epsilon) == EPSILON_HITS


def test_roles_are_partitioned_and_the_calibration_columns_are_empty() -> None:
    """No channel passed its gate, so no calibrated estimate may exist."""

    summary = load_summary()
    assert summary["roles"] == {
        "paired_anchor": PAIRED_ANCHORS,
        "uncalibrated_reference": UNCALIBRATED_REFERENCE,
    }
    assert sum(summary["roles"].values()) == LAYER_ROWS
    assert CALIBRATED_ESTIMATES == 0
    rows = load_rows()
    assert all(row["calib_homo_eV"] == "" for row in rows)
    assert all(row["calib_lumo_eV"] == "" for row in rows)
    assert all(row["calibration_id"] == "" for row in rows)


def test_every_channel_is_reference_only() -> None:
    summary = load_summary()
    for name, slope, intercept, r_value, mae in (
        ("homo", HOMO_SLOPE, HOMO_INTERCEPT, HOMO_R, HOMO_MAE),
        ("lumo", LUMO_SLOPE, LUMO_INTERCEPT, LUMO_R, LUMO_MAE),
        ("gap", GAP_SLOPE, GAP_INTERCEPT, GAP_R, GAP_MAE),
    ):
        channel = summary["calibration"][name]
        assert channel["n"] == PAIRED_ANCHORS
        assert channel["slope"] == pytest.approx(slope, rel=0, abs=1e-12)
        assert channel["intercept"] == pytest.approx(intercept, rel=0, abs=1e-12)
        assert channel["pearson_r_in_sample"] == pytest.approx(r_value, rel=0, abs=1e-12)
        assert channel["mae_out_of_sample_eV"] == pytest.approx(mae, rel=0, abs=1e-12)
        assert channel["status"] == "reference_only"


def test_the_homo_gate_is_missed_by_the_mean_absolute_error_not_the_correlation() -> None:
    """The headline is a near miss on MAE and a clean miss on LUMO and gap."""

    summary = load_summary()
    homo = summary["calibration"]["homo"]
    assert homo["pearson_r_in_sample"] >= 0.80
    assert homo["mae_out_of_sample_eV"] > 0.35
    assert summary["calibration"]["lumo"]["pearson_r_in_sample"] < 0.80
    assert summary["calibration"]["gap"]["pearson_r_in_sample"] < 0.80


def test_level_offsets_are_recorded_with_both_neighbours() -> None:
    summary = load_summary()
    assert summary["level_offsets_gfn2_minus_batt"]["homo"]["n"] == PAIRED_ANCHORS
    assert summary["level_offsets_gfn2_minus_batt"]["homo"]["mean_eV"] == pytest.approx(
        HOMO_OFFSET_MEAN, rel=0, abs=1e-12
    )
    assert summary["level_offsets_gfn2_minus_batt"]["lumo"]["mean_eV"] == pytest.approx(
        LUMO_OFFSET_MEAN, rel=0, abs=1e-12
    )
    assert summary["level_offsets_gfn2_minus_pubchemqc"]["homo"]["n"] == 161


def test_structure_and_unit_checks_are_not_constants() -> None:
    summary = load_summary()
    assert summary["structure_check"] == {
        "inchikey_match": LAYER_ROWS,
        "inchikey_mismatch": 0,
        "smiles_unparsable": 0,
    }
    assert summary["unit_check"]["status"] == "ok"
    assert summary["unit_check"]["n"] == UNIT_AUDIT_N
    assert summary["unit_check"]["pass_rate"] == 1.0
    assert all(check["passed"] for check in summary["unit_check"]["rows"])
    assert summary["unit_check"]["max_abs_residual_eV"] <= 1e-3


def test_derived_columns_are_exact_differences() -> None:
    rows = load_rows()
    for row in rows:
        homo = number(row["homo_gfn2_eV"])
        lumo = number(row["lumo_gfn2_eV"])
        batt_homo = number(row["batt_homo_eV"])
        batt_lumo = number(row["batt_lumo_eV"])
        assert homo is not None and lumo is not None
        assert number(row["gap_gfn2_eV"]) == lumo - homo
        if batt_homo is not None:
            assert number(row["gfn2_minus_batt_homo_eV"]) == homo - batt_homo
        else:
            assert row["gfn2_minus_batt_homo_eV"] == ""
        if batt_lumo is not None:
            assert number(row["batt_gap_eV"]) == batt_lumo - batt_homo
            assert number(row["gfn2_minus_batt_lumo_eV"]) == lumo - batt_lumo
            assert number(row["gfn2_minus_batt_gap_eV"]) == (lumo - homo) - (batt_lumo - batt_homo)
        assert row["unit_check"] == "pipeline_audited_eV"
        assert row["source_license"].startswith("THEMol CC BY-NC 4.0")


def test_source_level_and_harvest_bookkeeping() -> None:
    summary = load_summary()
    assert summary["harvest"]["rows_total"] == LAYER_ROWS
    assert sum(summary["harvest"]["rows_by_shard"].values()) == LAYER_ROWS
    assert summary["harvest"]["skipped"] == []
    assert summary["harvest"]["fetched_bytes_total"] == FETCHED_BYTES_TOTAL
    assert summary["harvest"]["xtb_versions"] == ["6.7.1pre"]
    rows = load_rows()
    assert {row["xtb_version"] for row in rows} == {"6.7.1pre"}
    assert all(row["source_dataset"].startswith("ByteDance-Seed/THEMol") for row in rows)


def test_three_way_counts_are_internally_consistent() -> None:
    three_way = load_summary()["three_way"]
    assert sum(three_way.values()) == LAYER_ROWS
    assert three_way["has_batt_and_pubchemqc"] == PAIRED_ANCHORS - 2
    rows = load_rows()
    both = sum(
        1 for row in rows if row["batt_homo_eV"] != "" and row["pubchemqc_homo_eV"] != ""
    )
    assert both == three_way["has_batt_and_pubchemqc"]


def test_verifier_check_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--check"],
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.startswith("PASS")


@pytest.mark.skipif(not HARVEST_PRESENT, reason="raw THEMol harvest is not present")
def test_layer_recomposes_byte_identically_from_the_raw_harvest() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--check", "--check-raw"],
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(not HARVEST_PRESENT, reason="raw THEMol harvest is not present")
def test_shard_files_cover_every_layer_row() -> None:
    keys = set()
    total = 0
    for path in sorted(HARVEST_DIR.glob("shard_*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                total += 1
                assert row["status"] == "ok"
                assert row["returncode"] == "0"
                assert row["homo_eV"] and row["lumo_eV"]
                keys.add(row["inchikey"])
    assert total == LAYER_ROWS
    assert keys == {row["inchikey"] for row in load_rows()}


def test_geometry_digest_is_a_sha256_hex_string() -> None:
    for row in load_rows():
        digest = row["geometry_sha256"]
        assert len(digest) == 64
        assert all(character in "0123456789abcdef" for character in digest)
        assert math.isfinite(float(row["natoms"]))