"""Offline tests for the W17-12 second-source orbital layer.

The pinned literals are what the frozen pre-registration committed to before
the run plus what the run then produced.  They are written out literally rather
than recomputed so that a silent edit to the layer, the summary or the
pre-registration shows up as a failure instead of quietly re-baselining.

Nothing here touches the network.  Tests that need the (git-ignored) raw
harvest are skipped when it is absent, which is the normal state in CI.
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

LAYER = REPOSITORY_ROOT / "data/processed/orbital_second_source_layer.csv"
SUMMARY = REPOSITORY_ROOT / "probes/orbital_second_source_summary.json"
PREREG = REPOSITORY_ROOT / "probes/orbital_second_source_prereg.json"
REGISTRY = REPOSITORY_ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = REPOSITORY_ROOT / "data/dielectric_v04.csv"
VISCOSITY_ROSTER = REPOSITORY_ROOT / "data/viscosity_v02.csv"
VERIFIER = REPOSITORY_ROOT / "scripts/verify_orbital_second_source.py"
RAW_MANIFEST = REPOSITORY_ROOT / "data/raw/pubchemqc_w17/manifest.json"

RAW_LAYER_PRESENT = RAW_MANIFEST.exists()

PREREG_SHA256 = "162361c973c97d5be8b9ce68b4f5b7761813a2c6b09202e11d53dafe245326ed"
LAYER_SHA256 = "ba55897a296181267cc0673cbf2d4d98d17b3e5de8280958b7896556e053abfe"
LAYER_ROWS = 912
REGISTRY_SHA256 = "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee"
EPSILON_SHA256 = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"
VISCOSITY_SHA256 = "907f5368ff6d4d6c15fa26c8c2b57e8bbc8c7ac7a7b3db06ec2c689b283bf3a5"

EPSILON_KEYS = 247
EPSILON_HITS = 210
VISCOSITY_ROSTER_KEYS = 1228
VISCOSITY_ROSTER_HITS = 240
VISCOSITY_SAMPLE_SIZE = 300
VISCOSITY_SAMPLE_HITS = 139
REGISTRY_ORBIT_SAMPLE_SIZE = 200
REGISTRY_ORBIT_SAMPLE_HITS = 12
PAIRED_ANCHORS = 111
CALIBRATED_ESTIMATES = 801
UNCALIBRATED = 0

HOMO_SLOPE = 1.0132507837193052
HOMO_INTERCEPT = -2.8354161402050426
HOMO_R = 0.9717477841107552
HOMO_MAE = 0.17662467232470583
LUMO_SLOPE = 0.2588045572302973
LUMO_INTERCEPT = 1.3888951334640842
LUMO_R = 0.7349044734023142
LUMO_MAE = 0.24935401611452185
HOMO_OFFSET_MEAN = -2.9297346756756757
LUMO_OFFSET_MEAN = 1.0941013063063063

HARVEST_HTTP_REQUESTS = 1246
HARVEST_HTTP_BYTES = 352262591
HARVEST_LOCATED = 347
HEAD_RECORDS = 608

EXPECTED_COLUMNS = [
    "inchikey", "pubchem_cid", "pubchem_version", "record_name", "formula",
    "molecular_mass", "charge", "multiplicity", "source_dataset", "source_level",
    "source_license", "source_doi", "homo_eV", "lumo_eV", "gap_eV", "homo_beta_eV",
    "lumo_beta_eV", "dipole_debye", "unit_check", "structure_check", "tags",
    "in_key_registry", "in_batt_orbit_pool", "in_epsilon_roster", "in_viscosity_roster",
    "in_viscosity_sample", "in_calibration_sample",
    "batt_homo_eV", "batt_lumo_eV", "batt_minus_pubchemqc_homo_eV",
    "batt_minus_pubchemqc_lumo_eV", "calib_homo_eV", "calib_lumo_eV",
    "calibration_id", "role",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_layer():
    with open(LAYER, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def num(value):
    return None if value in (None, "") else float(value)


@pytest.fixture(scope="module")
def summary():
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def layer():
    return load_layer()


def test_prereg_is_frozen_before_run():
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    assert sha256(PREREG) == PREREG_SHA256
    assert payload["source"]["license"] == "CC BY 4.0"
    assert payload["source"]["citation_doi"] == "10.1021/acs.jcim.3c00899"
    assert payload["sampling"]["seed"] == 20260927


def test_layer_header_and_digest_are_pinned(layer):
    header, rows = layer
    assert header == EXPECTED_COLUMNS
    assert len(rows) == LAYER_ROWS
    assert sha256(LAYER) == LAYER_SHA256


def test_layer_keys_unique_and_sorted(layer):
    _, rows = layer
    keys = [row["inchikey"] for row in rows]
    assert keys == sorted(set(keys))


def test_input_digests_are_pinned(summary):
    digests = summary["input_digests"]
    assert digests["data/processed/four_core_key_registry.csv"] == REGISTRY_SHA256
    assert sha256(REGISTRY) == REGISTRY_SHA256
    assert digests["data/dielectric_v04.csv"] == EPSILON_SHA256
    assert sha256(EPSILON_ROSTER) == EPSILON_SHA256
    assert digests["data/viscosity_v02.csv"] == VISCOSITY_SHA256
    assert sha256(VISCOSITY_ROSTER) == VISCOSITY_SHA256


def test_coverage_is_reproducible_from_the_layer(layer, summary):
    _, rows = layer
    with open(EPSILON_ROSTER, newline="", encoding="utf-8") as handle:
        epsilon = {row["inchikey"] for row in csv.DictReader(handle) if row.get("inchikey")}
    with open(VISCOSITY_ROSTER, newline="", encoding="utf-8") as handle:
        viscosity = {row["inchikey"] for row in csv.DictReader(handle) if row.get("inchikey")}
    with open(REGISTRY, newline="", encoding="utf-8") as handle:
        registry = {row["inchikey"]: row for row in csv.DictReader(handle)}

    epsilon_hits = sum(1 for row in rows if row["inchikey"] in epsilon)
    viscosity_hits = sum(1 for row in rows if row["inchikey"] in viscosity)
    registry_hits = sum(1 for row in rows if row["inchikey"] in registry)
    paired = sum(1 for row in rows if row["role"] == "paired_anchor")

    assert len(epsilon) == EPSILON_KEYS
    assert epsilon_hits == EPSILON_HITS
    assert viscosity_hits == VISCOSITY_ROSTER_HITS
    assert paired == PAIRED_ANCHORS

    coverage = summary["coverage"]
    assert coverage["epsilon_roster_hits"] == epsilon_hits
    assert coverage["viscosity_roster_hits"] == viscosity_hits
    assert coverage["key_registry_hits"] == registry_hits
    assert coverage["paired_anchor_rows"] == paired
    assert coverage["calibrated_estimate_rows"] == CALIBRATED_ESTIMATES
    assert coverage["uncalibrated_reference_rows"] == UNCALIBRATED
    assert coverage["structure_mismatches"] == 0
    assert coverage["viscosity_roster_keys"] == VISCOSITY_ROSTER_KEYS
    assert coverage["viscosity_roster_sample_size"] == VISCOSITY_SAMPLE_SIZE
    assert coverage["viscosity_roster_sample_hits"] == VISCOSITY_SAMPLE_HITS
    assert coverage["viscosity_roster_sample_hit_rate"] == pytest.approx(
        VISCOSITY_SAMPLE_HITS / VISCOSITY_SAMPLE_SIZE, rel=1e-12
    )
    assert coverage["registry_orbit_sample_size"] == REGISTRY_ORBIT_SAMPLE_SIZE
    assert coverage["registry_orbit_sample_hits"] == REGISTRY_ORBIT_SAMPLE_HITS
    assert sum(1 for row in rows if row["in_viscosity_sample"] == "true") == VISCOSITY_SAMPLE_HITS
    assert (
        sum(1 for row in rows if row["in_calibration_sample"] == "true")
        == REGISTRY_ORBIT_SAMPLE_HITS
    )


def test_second_source_beats_the_rejected_alternative(summary):
    rate = summary["coverage"]["epsilon_roster_hit_rate"]
    assert rate == pytest.approx(EPSILON_HITS / EPSILON_KEYS, rel=1e-12)
    assert rate > 0.80
    assert summary["judgements"]["C_second_source_coverage"] == {
        "epsilon_pass": True,
        "viscosity_pass": True,
    }


def refit(rows, channel):
    pairs = [
        {
            "inchikey": row["inchikey"],
            "x": num(row[channel + "_eV"]),
            "y": num(row["batt_" + channel + "_eV"]),
        }
        for row in rows
        if num(row[channel + "_eV"]) is not None
        and num(row["batt_" + channel + "_eV"]) is not None
    ]
    assert len(pairs) == PAIRED_ANCHORS
    folds = {
        p["inchikey"]: index % 2
        for index, p in enumerate(sorted(pairs, key=lambda p: p["inchikey"]))
    }
    xs = [p["x"] for p in pairs]
    ys = [p["y"] for p in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / math.sqrt(sxx * syy)
    errors = []
    for held in (0, 1):
        train = [p for p in pairs if folds[p["inchikey"]] != held]
        test = [p for p in pairs if folds[p["inchikey"]] == held]
        tx = [p["x"] for p in train]
        ty = [p["y"] for p in train]
        tmx = sum(tx) / len(tx)
        tmy = sum(ty) / len(ty)
        tsxx = sum((x - tmx) ** 2 for x in tx)
        tsxy = sum((x - tmx) * (y - tmy) for x, y in zip(tx, ty))
        ts = tsxy / tsxx
        ti = tmy - ts * tmx
        errors.extend(abs((ts * p["x"] + ti) - p["y"]) for p in test)
    return {"slope": slope, "intercept": intercept, "r": r, "mae": sum(errors) / len(errors)}


def test_homo_calibration_is_usable_and_pinned(layer, summary):
    _, rows = layer
    block = summary["calibration"]["homo"]
    assert block["status"] == "usable_with_flag"
    assert block["n"] == PAIRED_ANCHORS
    assert block["slope"] == pytest.approx(HOMO_SLOPE, rel=1e-12)
    assert block["intercept"] == pytest.approx(HOMO_INTERCEPT, rel=1e-12)
    assert block["pearson_r_in_sample"] == pytest.approx(HOMO_R, rel=1e-12)
    assert block["mae_out_of_sample_eV"] == pytest.approx(HOMO_MAE, rel=1e-12)

    got = refit(rows, "homo")
    assert got["slope"] == pytest.approx(block["slope"], rel=1e-9)
    assert got["intercept"] == pytest.approx(block["intercept"], abs=1e-9)
    assert got["mae"] == pytest.approx(block["mae_out_of_sample_eV"], rel=1e-9)
    assert got["r"] == pytest.approx(block["pearson_r_in_sample"], rel=1e-9)


def test_lumo_calibration_is_honestly_downgraded(layer, summary):
    _, rows = layer
    block = summary["calibration"]["lumo"]
    assert block["slope"] == pytest.approx(LUMO_SLOPE, rel=1e-12)
    assert block["intercept"] == pytest.approx(LUMO_INTERCEPT, rel=1e-12)
    assert block["pearson_r_in_sample"] == pytest.approx(LUMO_R, rel=1e-12)
    assert block["mae_out_of_sample_eV"] == pytest.approx(LUMO_MAE, rel=1e-12)
    assert block["mae_out_of_sample_eV"] <= block["mae_limit_eV"]
    assert block["pearson_r_in_sample"] < block["r_limit"]
    assert block["status"] == "reference_only"
    assert all(row["calib_lumo_eV"] == "" for row in rows)


def test_level_offsets_are_pinned(summary):
    offsets = summary["level_offsets_batt_minus_pubchemqc"]
    assert offsets["homo"]["n"] == PAIRED_ANCHORS
    assert offsets["homo"]["mean_eV"] == pytest.approx(HOMO_OFFSET_MEAN, rel=1e-12)
    assert offsets["lumo"]["mean_eV"] == pytest.approx(LUMO_OFFSET_MEAN, rel=1e-12)
    assert offsets["homo"]["stdev_eV"] < offsets["lumo"]["stdev_eV"]


def test_roles_and_untouched_registry(layer):
    _, rows = layer
    allowed = {"paired_anchor", "calibrated_estimate", "uncalibrated_reference"}
    assert {row["role"] for row in rows} <= allowed
    with open(REGISTRY, newline="", encoding="utf-8") as handle:
        registry = {row["inchikey"]: row for row in csv.DictReader(handle)}
    for row in rows:
        if row["role"] == "paired_anchor":
            assert row["calib_homo_eV"] == "" and row["calib_lumo_eV"] == ""
            assert row["batt_homo_eV"] != ""
            assert abs(num(row["batt_homo_eV"]) - float(registry[row["inchikey"]]["HOMO_eV"])) < 5e-7
        if row["role"] == "calibrated_estimate":
            assert row["calib_homo_eV"] != ""
            assert row["calibration_id"] == "linear_2fold_v1"


def test_layer_self_consistency(layer):
    _, rows = layer
    for row in rows:
        assert row["unit_check"] in {"verified_eV_audited", "dataset_level_eV"}
        assert row["structure_check"] in {
            "inchikey_match_target",
            "inchikey_from_pubchem_cid",
        }
        assert row["source_license"] == "CC BY 4.0"
        homo, lumo, gap = num(row["homo_eV"]), num(row["lumo_eV"]), num(row["gap_eV"])
        assert homo is not None and lumo is not None and gap is not None
        assert abs(gap - (lumo - homo)) < 1e-5
        assert -30.0 <= homo <= -1.0


def test_unit_audit_documents_the_card_defect(summary):
    audit = summary["unit_audit"]
    assert audit["declared_unit_in_card"] == "hartree"
    assert audit["observed_unit"] == "eV"
    assert audit["pass_rate"] == 1.0
    assert audit["n"] == 240
    assert audit["passed"] == 240
    assert audit["strata"] == 12
    assert audit["cid_span_checked"] == [1, 233866]
    assert audit["valence_window_discriminates_units"] is True
    assert audit["card_declares_unit_for_scalar_fields"] is False
    assert audit["energy_field_equals_orbital_array"] is True
    assert audit["gap_identity_holds"] is True
    assert "helium" in audit["noble_gas_anchor"]


@pytest.mark.skipif(not RAW_LAYER_PRESENT, reason="raw harvest layer is not committed")
def test_harvest_manifest_matches_the_run(summary):
    manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["http_requests"] == HARVEST_HTTP_REQUESTS
    assert manifest["http_bytes_read"] == HARVEST_HTTP_BYTES
    assert manifest["located_record_count"] == HARVEST_LOCATED
    assert manifest["head_record_count"] == HEAD_RECORDS
    assert manifest["shard_cid_window"] == [1, 253696]
    assert summary["harvest_manifest_sha256"] == sha256(RAW_MANIFEST)


@pytest.mark.skipif(not RAW_LAYER_PRESENT, reason="raw harvest layer is not committed")
def test_compose_requires_the_raw_layer(tmp_path, monkeypatch):
    from probes import build_orbital_second_source as builder

    monkeypatch.setattr(builder, "RAW_DIR", tmp_path)
    with pytest.raises(SystemExit):
        builder.compose()


@pytest.mark.skipif(not RAW_LAYER_PRESENT, reason="raw harvest layer is not committed")
def test_compose_relays_byte_identically():
    from probes import build_orbital_second_source as builder

    rows, _ = builder.compose()
    assert builder.render(rows).encode("utf-8") == LAYER.read_bytes()


def test_verify_script_passes_without_the_raw_layer():
    result = subprocess.run(
        [sys.executable, str(VERIFIER), "--check"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        cwd=str(REPOSITORY_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_pure_helpers():
    from probes import build_orbital_second_source as builder

    assert builder.q6(1.23456789) == 1.234568
    assert builder.q6(None) is None
    assert builder.q6("") is None
    assert builder.fit_line([0.0, 1.0, 2.0], [1.0, 3.0, 5.0]) == (2.0, 1.0)
    assert builder.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    folds = builder.fold_map(["b", "a", "c", "d"], folds=2)
    assert folds == {"a": 0, "b": 1, "c": 0, "d": 1}
    assert builder.fmt(None) == ""
    assert builder.fmt(float("nan")) == ""