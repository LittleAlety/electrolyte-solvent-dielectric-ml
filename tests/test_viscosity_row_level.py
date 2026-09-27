"""Guards for the Week 18 lane-A arm: the viscosity channel at row level.

Three things are pinned here.  The frozen baseline has to reproduce in place, so
the control reading is the published one bit for bit; the three scoreboards have
to stay separate objects that nothing subtracts; and the thaw ledger has to keep
the counts the pre-registration froze.  None of these tests refits the model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from probes import viscosity_row_level_unfreeze as probe

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json"


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(probe.PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(probe.SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def frozen_baseline() -> dict:
    return json.loads(FROZEN_SUMMARY_PATH.read_text(encoding="utf-8"))


def test_prereg_is_locked_before_the_run(prereg: dict) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["promotion"]["promoted"] is False
    assert prereg["protocol"]["gate"]["threshold"] == 0.15


def test_the_code_constants_agree_with_the_preregistration(prereg: dict) -> None:
    registered = prereg["pools"]
    pairs = (
        ("pool_family_rows", registered["family_level"]["expected_rows"]),
        ("pool_family_keys", registered["family_level"]["expected_keys"]),
        ("pool_thaw_only_rows", registered["thaw_only"]["expected_rows"]),
        ("pool_thaw_only_keys", registered["thaw_only"]["expected_keys"]),
        ("pool_row_level_rows", registered["row_level"]["expected_rows"]),
        ("pool_row_level_keys", registered["row_level"]["expected_keys"]),
        ("thawed_converted_rows", prereg["thaw_contract"]["expected"]["converted_rows"]),
        ("thawed_pooled_rows", prereg["thaw_contract"]["expected"]["pooled_rows"]),
        ("thawed_deferred_rows", prereg["thaw_contract"]["expected"]["deferred_multi_component_rows"]),
        ("thermoml_pure_dynamic_rows", prereg["dynamic_contract"]["expected"]["pure_rows"]),
        ("thermoml_pure_dynamic_keys", prereg["dynamic_contract"]["expected"]["pure_keys"]),
    )
    for name, value in pairs:
        assert probe.EXPECTED[name] == int(value), name


def test_frozen_gate_and_seed_are_imported_not_restated() -> None:
    assert probe.MAE_GATE == 0.15
    assert probe.SEED == 42


def test_the_family_level_reading_reproduces_the_frozen_baseline(
    summary: dict, frozen_baseline: dict
) -> None:
    published = frozen_baseline["splits"]["group_key"]["models"]["MorganTemperatureXGBoost"]
    observed = summary["readings"]["family_level"]["group_key"]
    assert observed["mae_log10_cP"] == pytest.approx(published["log10_cP"]["mae"], abs=1e-9)
    assert observed["r2_log10_cP"] == pytest.approx(published["log10_cP"]["r2"], abs=1e-9)
    assert summary["reproduction_check"]["reproduced"] is True
    assert summary["reproduction_check"]["input_sha256"] == probe.FROZEN_V01_SHA256


def test_the_three_scoreboards_are_reported_as_three_separate_objects(summary: dict) -> None:
    readings = summary["readings"]
    assert set(readings) == set(probe.POOL_ORDER)
    for pool in probe.POOL_ORDER:
        assert set(readings[pool]) == set(probe.SPLIT_ORDER)
    assert "delta_vs_family_level" not in json.dumps(summary)
    assert "差值不构成本枪的任何结论" in json.dumps(summary, ensure_ascii=False)


def test_the_gate_verdict_follows_from_the_row_level_reading(summary: dict) -> None:
    gate = summary["primary_gate"]
    row_level = summary["readings"]["row_level"]["group_key"]["mae_log10_cP"]
    assert row_level == pytest.approx(gate["row_level_mae"], abs=1e-12)
    passed = row_level < probe.MAE_GATE
    assert gate["row_level_passed"] is passed
    assert gate["which_pool_passed"] == (["row_level"] if passed else [])
    assert summary["verdict"] == ("passes_gate_at_row_level" if passed else "refuted")
    assert summary["verdict"] == "refuted"
    assert gate["row_level_passed"] is False


def test_the_thaw_ledger_keeps_the_frozen_counts(summary: dict) -> None:
    pairing = summary["census"]["thaw_pairing"]
    assert pairing["local_rows"] == 176
    assert pairing["exact_rows"] == 176
    assert pairing["nearest_rows"] == 176
    assert pairing["converted_rows"] == 176
    assert pairing["pooled_rows"] == 86
    assert pairing["deferred_multi_component_rows"] == 90
    assert summary["census"]["thawed_rows_admitted"] == 86
    assert len(pairing["pooled_keys"]) == 4


def test_the_group_key_split_never_shares_a_compound(summary: dict) -> None:
    for pool in probe.POOL_ORDER:
        assert summary["readings"][pool]["group_key"]["group_overlap_keys"] == 0


def test_the_repeats_table_lists_all_six_cells_lf_only() -> None:
    payload = probe.REPEATS_PATH.read_bytes()
    assert b"\r\n" not in payload
    assert not payload.startswith(b"\xef\xbb\xbf")
    lines = payload.decode("utf-8").splitlines()
    assert lines[0] == ",".join(probe.READING_COLUMNS)
    assert len(lines) == 1 + len(probe.POOL_ORDER) * len(probe.SPLIT_ORDER)


EXPECTED_POOL_ROWS = {
    "family_level": "pool_family_rows",
    "thaw_only": "pool_thaw_only_rows",
    "row_level": "pool_row_level_rows",
}


def test_the_pools_rebuild_to_the_registered_counts() -> None:
    pools, census = probe.build_pools()
    assert probe._check_census(census) == []
    for name in probe.POOL_ORDER:
        assert len(pools[name]) == probe.EXPECTED[EXPECTED_POOL_ROWS[name]]
