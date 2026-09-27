"""Literal pins for the Week 19 D5 eta cross-model consistency shot (AF-13 discipline).

Every number this file asserts is typed out here rather than re-derived from prose: the pool
census, both deltas, the incumbent reproduction, the split hashes and the tolerance band.  A
silent edit to the probe or to its stored readings turns this file red instead of quietly
re-baselining the deliverable.

Scope note: this shot never touches the epsilon scoreboard.  The numbers 457 / 97 / 276 / 2029
appear here only inside the boundary sentence that keeps the two channels apart.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from probes import w19_chemprop_viscosity as probe

MODULE_PATH = REPOSITORY_ROOT / "probes" / "w19_chemprop_viscosity.py"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_chemprop_viscosity_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_chemprop_viscosity_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_chemprop_viscosity.md"
REPEATS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w19_chemprop_viscosity_repeats.csv"
TEST_PATH = Path(__file__)

NEW_FILES = (MODULE_PATH, PREREG_PATH, SUMMARY_PATH, REPORT_PATH, REPEATS_PATH, TEST_PATH)

# Digests taken on 2026-09-28, over the raw bytes of the LF, no-BOM files themselves.
PREREG_SHA256 = "c42846ccb9c898ebfd7da429e40247132134c90089b0d41d684ce6c5f313f7b9"
MODULE_SHA256 = "2e2a582b8627aafcbfd5547ba8151c6d1612441cd3a0ad9036d4bb35ea98b15c"

TOLERANCE = 0.02
GATE = 0.15

INCUMBENT_TRAIN_ID_HASH = {
    "row_level": "48b17e76c1edcdce0369d8118ad21ea0beb1b472ec744cee3c579c02fa6e3111",
    "family_level": "e9a63ff49a3f54380ad1241be8db156c8bd7f4c3c9c0308859f8dcaa121c9506",
}
INCUMBENT_TEST_ID_HASH = {
    "row_level": "2dedfc6ae3ac3dae98e7404556535030d5d3fd000b8119c25d230db791507119",
    "family_level": "dfea9aa151cd5b0f86eede1d6929b8fe5a1e0ab34926a851e90d3f7de6d4d63f",
}

POOL_PINS: dict[str, dict[str, Any]] = {
    "row_level": {
        "rows": 4151,
        "keys": 976,
        "train_rows": 3313,
        "train_keys": 780,
        "test_rows": 838,
        "test_keys": 196,
        "incumbent_mae": 0.15686276760094522,
        "chemprop_mae": 0.08506361044387624,
        "delta": -0.07179915715706899,
    },
    "family_level": {
        "rows": 3582,
        "keys": 957,
        "train_rows": 2874,
        "train_keys": 765,
        "test_rows": 708,
        "test_keys": 192,
        "incumbent_mae": 0.17477197208762,
        "chemprop_mae": 0.08908094784092072,
        "delta": -0.08569102424669928,
    },
}

MEMBER_MAES = {
    "row_level": (0.0882960774167516, 0.08523774199790451, 0.09018705670994248),
    "family_level": (0.09404638489966256, 0.09243975729389908, 0.08818446634125515),
}
MEMBER_SEEDS = (42, 1234, 2026)

# Every literal the report must keep, including the correction sentence and the
# confound boundary that keeps the W18 epsilon number honest.
REPORT_LITERALS = (
    "0.15686276760094522",
    "0.08506361044387624",
    "0.17477197208762",
    "0.08908094784092072",
    "-0.07179915715706899",
    "-0.08569102424669928",
    "chemprop_better",
    "214 is a family-level exclusion count",
    "86 rows",
    "28.38",
    "0.01370607964226378",
    "0.15",
    "0.02",
    "457 / 97 / 276 / 2029",
    "split_verified_against_incumbent = true",
)

# The three registered verdicts and the report-only entry point.
MODULE_LITERALS = (
    "chemprop_better",
    "incumbent_confirmed",
    "consistency_confirmed",
    "--report-only",
    "frozen._group_key_split(",
    "INCUMBENT_TRAIN_ID_HASH",
    "no model was re-fitted and no number moved",
)

def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    return _read_json(SUMMARY_PATH)


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    return _read_json(PREREG_PATH)


@pytest.fixture(scope="module")
def report_text() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


def test_new_files_exist() -> None:
    for path in NEW_FILES:
        assert path.is_file(), path


def test_new_text_files_are_lf_without_bom() -> None:
    for path in NEW_FILES:
        payload = path.read_bytes()
        assert b"\r\n" not in payload, path
        assert not payload.startswith(b"\xef\xbb\xbf"), path


def test_preregistration_is_locked_before_the_run(prereg: dict[str, Any]) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["tolerance_preregistered"]["delta_definition"] == (
        "delta = MAE_chemprop - MAE_incumbent_XGB (same pool, same split, same units)"
    )
    assert prereg["gate"]["value"] == GATE
    assert prereg["amendment_rule_declared_before_run"]["obligation"] != ""
    assert prereg["red_lines"]["promotes_no_reading"] is True
    assert prereg["red_lines"]["uses_no_reaxys_numbers"] is True
    assert prereg["red_lines"]["main_scoreboard_attempts_added"] == 0
    assert prereg["red_lines"]["cumulative_main_scoreboard_attempts_after_this_shot"] == 11


def test_preregistration_registers_the_214_row_correction(prereg: dict[str, Any]) -> None:
    correction = prereg["correction_registered_before_run"]
    registered = " ".join(str(value) for value in correction.values())
    assert "214" in registered
    assert "86" in registered
    assert "28.38" in registered
    assert correction["verdict"] == "doubly wrong"


def test_preregistration_digest_is_pinned_and_recorded(summary: dict[str, Any]) -> None:
    assert _sha256(PREREG_PATH) == PREREG_SHA256
    assert summary["preregistration"]["sha256"] == PREREG_SHA256
    assert summary["preregistration"]["status"] == "locked_before_run"


def test_module_digest_is_pinned() -> None:
    assert _sha256(MODULE_PATH) == MODULE_SHA256


def test_summary_verdict_and_red_lines(summary: dict[str, Any]) -> None:
    assert summary["verdict"] == "chemprop_better"
    assert summary["delta_mae_log10_cP"] == POOL_PINS["row_level"]["delta"]
    assert summary["promoted"] is False
    assert summary["main_scoreboard_attempts_added"] == 0
    assert summary["uses_no_reaxys_numbers"] is True
    assert summary["gate_log10_cP"] == GATE
    assert summary["tolerance"] == TOLERANCE
    assert summary["registered_config"]["ensemble_seeds"] == list(MEMBER_SEEDS)
    assert summary["registered_config"]["epochs"] == 60
    assert summary["registered_config"]["validation_fold"] == "none (fixed epoch budget)"
    assert summary["registered_config"]["torch_threads"] <= 2
    assert summary["figure_written"] is True
    assert summary["boundary_revision"] != ""


@pytest.mark.parametrize("pool", sorted(POOL_PINS))
def test_pool_readings_are_pinned(summary: dict[str, Any], pool: str) -> None:
    pins = POOL_PINS[pool]
    record = summary["pools"][pool]
    assert record["rows"] == pins["rows"]
    assert record["keys"] == pins["keys"]
    assert record["train_rows"] == pins["train_rows"]
    assert record["train_keys"] == pins["train_keys"]
    assert record["test_rows"] == pins["test_rows"]
    assert record["test_keys"] == pins["test_keys"]
    assert record["incumbent"]["mae_log10_cP"] == pins["incumbent_mae"]
    assert record["chemprop"]["ensemble_mae_log10_cP"] == pins["chemprop_mae"]
    assert record["delta_mae_log10_cP"] == pins["delta"]
    assert record["verdict"] == "chemprop_better"
    assert record["gate_0_15_passed_by_chemprop"] is True
    assert record["gate_0_15_passed_by_incumbent"] is False


@pytest.mark.parametrize("pool", sorted(POOL_PINS))
def test_split_identity_and_no_group_overlap(summary: dict[str, Any], pool: str) -> None:
    record = summary["pools"][pool]
    assert record["split_verified_against_incumbent"] is True
    assert record["train_id_hash"] == INCUMBENT_TRAIN_ID_HASH[pool]
    assert record["test_id_hash"] == INCUMBENT_TEST_ID_HASH[pool]
    assert record["group_overlap_keys"] == 0


@pytest.mark.parametrize("pool", sorted(POOL_PINS))
def test_incumbent_is_reproduced_exactly(summary: dict[str, Any], pool: str) -> None:
    reproduction = summary["pools"][pool]["incumbent_reproduction"]
    assert reproduction["matches_frozen"] is True
    assert reproduction["abs_gap"] == 0.0
    assert reproduction["mae_log10_cP"] == POOL_PINS[pool]["incumbent_mae"]


@pytest.mark.parametrize("pool", sorted(POOL_PINS))
def test_the_registered_tolerance_produces_the_stored_verdict(
    summary: dict[str, Any], pool: str
) -> None:
    record = summary["pools"][pool]
    delta = record["chemprop"]["ensemble_mae_log10_cP"] - record["incumbent"]["mae_log10_cP"]
    assert delta == pytest.approx(record["delta_mae_log10_cP"], abs=0.0)
    if delta <= -TOLERANCE:
        expected = "chemprop_better"
    elif delta >= TOLERANCE:
        expected = "incumbent_confirmed"
    else:
        expected = "consistency_confirmed"
    assert record["verdict"] == expected


@pytest.mark.parametrize("pool", sorted(POOL_PINS))
def test_every_member_clears_the_tolerance_on_its_own(
    summary: dict[str, Any], pool: str
) -> None:
    members = summary["pools"][pool]["chemprop"]["members"]
    assert tuple(member["seed"] for member in members) == MEMBER_SEEDS
    assert tuple(member["epochs"] for member in members) == (60, 60, 60)
    assert tuple(member["mae_log10_cP"] for member in members) == pytest.approx(
        MEMBER_MAES[pool]
    )
    incumbent = POOL_PINS[pool]["incumbent_mae"]
    for member in members:
        assert member["mae_log10_cP"] - incumbent <= -TOLERANCE


def test_report_carries_the_pinned_literals(report_text: str) -> None:
    for literal in REPORT_LITERALS:
        assert literal in report_text, literal


def test_module_verdict_vocabulary_and_split_reuse() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for literal in MODULE_LITERALS:
        assert literal in source, literal
    assert "from sklearn" not in source
    folded = source.replace("GroupShuffleSplit(test_size=0.2, seed=42)", "")
    assert "GroupShuffleSplit(" not in folded


def test_module_exposes_the_registered_constants() -> None:
    assert probe.POOL_PRIMARY == "row_level"
    assert probe.POOL_SECONDARY == "family_level"
    assert probe.POOL_ORDER == ("row_level", "family_level")
    assert probe.TOLERANCE == TOLERANCE
    assert probe.MAE_GATE == GATE
    assert probe.ENSEMBLE_SEEDS == MEMBER_SEEDS
    assert probe.EPOCHS == 60
    assert probe.INCUMBENT_MAE["row_level"] == POOL_PINS["row_level"]["incumbent_mae"]
    assert probe.INCUMBENT_MAE["family_level"] == POOL_PINS["family_level"]["incumbent_mae"]
    assert probe.INCUMBENT_TEST_ROWS["row_level"] == 838


def test_repeats_csv_has_one_row_per_member_plus_one_ensemble_row() -> None:
    with REPEATS_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    members = [row for row in rows if row["member"] != "ensemble"]
    ensembles = [row for row in rows if row["member"] == "ensemble"]
    assert len(members) == 6
    assert len(ensembles) == 2
    for row in members:
        assert float(row["delta_vs_incumbent"]) <= -TOLERANCE
        assert int(row["epochs"]) == 60
        assert int(row["test_rows"]) in (708, 838)
    for row in ensembles:
        assert float(row["delta_vs_incumbent"]) <= -TOLERANCE
        assert row["fit_seconds"] == ""
