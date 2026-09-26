"""Guards for the Week 17 v0.4 roster patch (succinonitrile + GVL dual row)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from scripts.build_dielectric_v04 import (
    PROTECTED_PATCH_FIELDS,
    V03_FROZEN_SHA256,
    build_v04_rows,
    load_additions,
    load_patches,
    temperature_band_v04,
)

DATA = REPOSITORY_ROOT / "data"
V03 = DATA / "dielectric_v03.csv"
V04 = DATA / "dielectric_v04.csv"
ADDITIONS = DATA / "processed" / "dielectric_v04_roster_additions.csv"
PATCHES = DATA / "processed" / "dielectric_v04_provenance_patches.csv"
SUMMARY = REPOSITORY_ROOT / "probes" / "dielectric_v04_summary.json"

SUCCINONITRILE = "IAHFWCOBPZCAEA-UHFFFAOYSA-N"
GVL = "GAEKPEKOJKCEMS-UHFFFAOYSA-N"


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def test_frozen_v03_digest_is_intact() -> None:
    assert canonical_text_sha256(V03) == V03_FROZEN_SHA256


def test_v04_reproduces_from_the_pinned_inputs() -> None:
    fields, v03_rows = _read(V03)
    output_fields, output_rows = _read(V04)
    additions, _ = load_additions(ADDITIONS, fields)
    patches = load_patches(PATCHES)
    expected, applied = build_v04_rows(v03_rows, additions, patches, fields)
    assert output_fields == fields
    assert len(output_rows) == len(expected) == len(v03_rows) + 2 == 248
    for actual, want in zip(output_rows, expected, strict=True):
        assert {f: actual.get(f, "") for f in fields} == {
            f: want.get(f, "") for f in fields
        }
    assert len(applied) == 2


def test_no_protected_field_moved() -> None:
    _, v03_rows = _read(V03)
    _, output_rows = _read(V04)
    for legacy, shipped in zip(v03_rows, output_rows, strict=False):
        for field in PROTECTED_PATCH_FIELDS:
            assert legacy.get(field, "") == shipped.get(field, ""), field


def test_only_the_declared_patch_fields_changed() -> None:
    fields, v03_rows = _read(V03)
    _, output_rows = _read(V04)
    patches = load_patches(PATCHES)
    declared = {(p["inchikey"], p["field"]) for p in patches}
    changed = {
        (legacy["inchikey"], field)
        for legacy, shipped in zip(v03_rows, output_rows, strict=False)
        for field in fields
        if legacy.get(field, "") != shipped.get(field, "")
    }
    assert changed == declared
    assert declared == {(GVL, "conflict_status"), (GVL, "notes")}


def test_succinonitrile_row_closes_the_roster_gap() -> None:
    fields, _ = _read(V03)
    additions, _ = load_additions(ADDITIONS, fields)
    succ = next(a for a in additions if a["inchikey"] == SUCCINONITRILE)
    assert succ["name"] == "succinonitrile"
    assert succ["T_K"] == "333.15"
    assert succ["dielectric"] == "56.09"
    assert succ["n_observations"] == "17"
    assert succ["temperature_band"] == "high_temperature"
    assert temperature_band_v04(333.15) == "high_temperature"
    assert succ["model_ready"] == "false"
    assert succ["dataset_origin"] == "v0.4_addition"


def test_gvl_dual_row_is_kept_as_two_rows_and_not_averaged() -> None:
    _, output_rows = _read(V04)
    legs = [row for row in output_rows if row["inchikey"] == GVL]
    assert len(legs) == 2
    assert sorted(row["dielectric"] for row in legs) == ["36.1", "36.9"]
    review_leg = next(row for row in legs if row["dielectric"] == "36.1")
    primary_leg = next(row for row in legs if row["dielectric"] == "36.9")
    # The review-table leg keeps v0.3's model_ready=true: that field is protected
    # and v0.4 must not silently rewrite it.  The newly added primary leg carries
    # no temperature, so it is model_ready=false; both legs share the unresolved
    # dual-row conflict stamp.
    assert review_leg["model_ready"] == "true"
    assert primary_leg["model_ready"] == "false"
    assert primary_leg["dataset_origin"] == "v0.4_addition"
    assert primary_leg["temperature_source"] == "not_reported"
    assert all("unresolved_dual_row" in row["conflict_status"] for row in legs)


def test_v04_is_lf_only() -> None:
    assert b"\r\n" not in V04.read_bytes()


def test_summary_matches_the_shipped_table() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["v03_row_count"] == 246
    assert summary["row_count"] == 248
    assert summary["addition_count"] == 2
    assert summary["output"]["sha256"] == canonical_text_sha256(V04)
    assert summary["inputs"]["dielectric_v03"]["sha256"] == V03_FROZEN_SHA256
    assert summary["provenance_patches"]["applied_count"] == 2
    assert summary["temperature_band_counts"]["high_temperature"] == 1


def test_patch_on_a_protected_field_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad_patches.csv"
    bad.write_text(
        "inchikey,field,value,rationale\n"
        f"{GVL},dielectric,99,illegal\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        load_patches(bad)
    except ValueError as error:
        assert "protected" in str(error)
    else:  # pragma: no cover - the guard must fire
        raise AssertionError("a protected-field patch was accepted")


def test_verifier_passes_on_the_shipped_tree() -> None:
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "verify_dielectric_v04.py")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["passed"] is True
