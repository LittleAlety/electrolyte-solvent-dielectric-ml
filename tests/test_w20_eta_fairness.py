"""Literal pins for the Week 20 W20-1 eta fairness review (section 28.57).

The lane removes the two boundaries W19-D5 could not: the incumbent viscosity arm was a
frozen single-configuration single-seed XGBoost against a three-seed Chemprop ensemble, and
the grouped protocol was one 20 percent hold-out draw with no fold-level variance.  This
lane grants the incumbent the tuning and multi-seed budget it was denied and upgrades the
split to GroupKFold by InChIKey, five folds by five repeats.

Everything asserted here is typed out rather than re-derived from prose: the locked grid,
the locked seeds, the gate and the tolerance, the frozen caliber numbers, the no-shot
accounting and the no-promotion stand.  A silent edit to the preregistration, the summary,
the report, the repeats CSV or the fragment turns this file red instead of quietly
re-baselining the deliverable.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_eta_fairness as eta

MODULE_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness.py"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_eta_fairness.md"
REPEATS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_eta_fairness_repeats.csv"
FIGURE_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_eta_fairness_delta.png"
FRAGMENT_PATH = REPOSITORY_ROOT / "reports" / "_w20_section_w201.md"
TEST_PATH = Path(__file__)

FILES = (
    MODULE_PATH,
    PREREG_PATH,
    SUMMARY_PATH,
    REPORT_PATH,
    REPEATS_PATH,
    FIGURE_PATH,
    FRAGMENT_PATH,
    TEST_PATH,
)

# The LF/BOM rule applies to committed *text*.  A PNG cannot satisfy it by construction:
# the PNG signature itself is b"\x89PNG\r\n\x1a\n", so a CRLF scan over the figure would
# be unsatisfiable.  The figure is guarded by its own signature and size test instead.
TEXT_FILES = (
    MODULE_PATH,
    PREREG_PATH,
    SUMMARY_PATH,
    REPORT_PATH,
    REPEATS_PATH,
    FRAGMENT_PATH,
    TEST_PATH,
)

# The frozen caliber this lane re-asks its question against; never mixed, never rewritten.
CALIBER_INCUMBENT_ROW = 0.15686276760094522
CALIBER_INCUMBENT_FAMILY = 0.17477197208762
CALIBER_CHEMPROP_ROW = 0.08506361044387624
CALIBER_CHEMPROP_FAMILY = 0.08908094784092072
GATE = 0.15
TOLERANCE = 0.02
CUMULATIVE_ATTEMPTS = 11

POOL_PRIMARY = "row_level"
POOL_SECONDARY = "family_level"
POOL_ORDER = (POOL_PRIMARY, POOL_SECONDARY)

VERDICT_VOCABULARY = (
    "eta_crosses_gate_out_of_fold",
    "incumbent_budget_closes_gate",
    "representation_sensitive_gate_undetermined",
    "incumbent_confirmed",
)

# W19-D5 gate states on the primary pool, as registered before this run.
W19_CHEMPROP_ROW_PASSED = True
W19_INCUMBENT_ROW_PASSED = False

INCUMBENT_GRID_PIN = (
    ("frozen_default", 800, 10, 0.05, 0.8, 0.6, 1.0),
    ("shallow_wide", 1200, 6, 0.05, 0.8, 0.6, 1.0),
    ("shallow_slow", 1500, 4, 0.03, 0.9, 0.8, 2.0),
)

FRAGMENT_FIRST_LINE_PREFIX = "## 28.57 "
FRAGMENT_FIRST_LINE_SUFFIX = "\uff082026-09-28\uff09"

W20_3_RULE = (
    "Only a verdict of eta_crosses_gate_out_of_fold authorises W20-3 to fold eta into "
    "the ranking key v1. Every other verdict means W20-3 must NOT fold eta in."
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prereg() -> dict:
    return json.loads(_text(PREREG_PATH))


def _summary() -> dict:
    return json.loads(_text(SUMMARY_PATH))


def _verdict_from(delta: float, chemprop_gate: bool, incumbent_gate: bool) -> str:
    """The registered rule, re-typed so a module edit cannot move both sides at once."""

    if abs(delta) <= TOLERANCE:
        return "representation_sensitive_gate_undetermined"
    if delta <= -TOLERANCE:
        if chemprop_gate and not incumbent_gate:
            return "eta_crosses_gate_out_of_fold"
        return "incumbent_budget_closes_gate"
    return "incumbent_confirmed"


def test_every_file_exists() -> None:
    for path in FILES:
        assert path.is_file(), f"missing file: {path}"


def test_utf8_no_bom_and_lf_only() -> None:
    for path in TEXT_FILES:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        assert b"\r\n" not in raw, f"CRLF in {path.name}"


def test_prereg_is_locked_before_the_run() -> None:
    data = _prereg()
    assert data["status"] == "locked_before_run"
    assert data["task_id"] == "week20_w20_1_eta_fairness"
    assert data["lane_section"] == "28.57"
    assert data["schema_version"] == 1


def test_prereg_pins_the_budget_aligned_grid() -> None:
    arms = _prereg()["arms"]
    incumbent = arms["incumbent_aligned"]
    assert incumbent["model"] == "MorganTemperatureXGBoost"
    assert [
        (
            row["name"],
            row["n_estimators"],
            row["max_depth"],
            row["learning_rate"],
            row["subsample"],
            row["colsample_bytree"],
            row["reg_lambda"],
        )
        for row in incumbent["grid"]
    ] == list(INCUMBENT_GRID_PIN)
    assert incumbent["ensemble_seeds"] == [42, 1234, 2026]
    assert "GroupKFold(3)" in incumbent["selection"]
    chemprop = arms["chemprop_aligned"]
    assert chemprop["ensemble_seeds"] == [42, 1234, 2026]
    assert "D-MPNN" in chemprop["model"]


def test_prereg_pins_the_upgraded_split() -> None:
    split = _prereg()["design"]["split_upgrade"]
    assert split["n_splits"] == 5
    assert split["n_repeats"] == 5
    assert split["repeat_seeds"] == [42, 1234, 2026, 31337, 7]
    assert "GroupShuffleSplit" in split["previous_protocol"]
    assert "GroupKFold" in split["new_protocol"]
    assert len(split["identity_assertions"]) == 2


def test_prereg_pins_the_criterion_and_the_gate_states() -> None:
    criterion = _prereg()["criterion"]
    assert criterion["gate"] == {"value": GATE, "units": "log10(cP)"}
    assert criterion["tolerance"] == TOLERANCE
    assert "MAE_chemprop_cross_seed_mean - MAE_incumbent_cross_seed_mean" in (
        criterion["delta_definition"]
    )
    states = criterion["registered_w19_gate_states_on_the_primary_pool"]
    assert states["chemprop_row_level_passed"] is W19_CHEMPROP_ROW_PASSED
    assert states["incumbent_row_level_passed"] is W19_INCUMBENT_ROW_PASSED
    branches = {branch["verdict"]: branch["condition"] for branch in criterion["branches"]}
    assert branches == {
        "representation_sensitive_gate_undetermined": "abs(delta) <= 0.02",
        "eta_crosses_gate_out_of_fold": "delta <= -0.02 and gate_state_unchanged",
        "incumbent_budget_closes_gate": "delta <= -0.02 and not gate_state_unchanged",
        "incumbent_confirmed": "delta >= +0.02",
    }


def test_prereg_keeps_the_pools_target_and_units_unchanged() -> None:
    design = _prereg()["design"]
    assert design["pools_unchanged"]["row_level"] == {"rows": 4151, "keys": 976}
    assert design["pools_unchanged"]["family_level"] == {"rows": 3582, "keys": 957}
    target = design["target_and_units_unchanged"]
    assert target["target"] == "log10(viscosity_cP) = log10(viscosity_Pa_s * 1000.0)"
    assert target["metric"] == "MAE in log10(cP)"
    assert design["budget_alignment"]["rule"]
    assert "conservative against the Chemprop arm" in design["budget_alignment"]["asymmetry_declared"]


def test_prereg_records_the_frozen_caliber_untouched() -> None:
    reference = _prereg()["reference_baselines_on_record_not_modified"]
    assert reference["incumbent_row_level_mae_log10_cP"] == CALIBER_INCUMBENT_ROW
    assert reference["incumbent_family_level_mae_log10_cP"] == CALIBER_INCUMBENT_FAMILY
    assert reference["chemprop_row_level_mae_log10_cP"] == CALIBER_CHEMPROP_ROW
    assert reference["chemprop_family_level_mae_log10_cP"] == CALIBER_CHEMPROP_FAMILY
    motivation = _prereg()["motivation"]["w19_d5_primary_reading"]
    assert motivation["incumbent_row_level_mae_log10_cP"] == CALIBER_INCUMBENT_ROW
    assert motivation["chemprop_row_level_mae_log10_cP"] == CALIBER_CHEMPROP_ROW
    assert motivation["incumbent_family_level_mae_log10_cP"] == CALIBER_INCUMBENT_FAMILY
    assert motivation["chemprop_family_level_mae_log10_cP"] == CALIBER_CHEMPROP_FAMILY
    assert motivation["gate"] == GATE
    assert motivation["delta_mae_log10_cP"] == pytest.approx(-0.07179915715706899, abs=0.0)


def test_prereg_takes_no_shot_and_promotes_nothing() -> None:
    red_lines = _prereg()["red_lines"]
    assert red_lines["promotes_no_reading"] is True
    assert red_lines["main_scoreboard_attempts_added"] == 0
    assert red_lines["cumulative_main_scoreboard_attempts_after_this_shot"] == CUMULATIVE_ATTEMPTS
    assert red_lines["uses_no_reaxys_numbers"] is True
    assert red_lines["frozen_numbers_not_touched"] == ["0.4091179943351143", "0.4766400383507876"]


def test_summary_pins_the_preregistration_digest() -> None:
    summary = _summary()
    payload = PREREG_PATH.read_bytes()
    digest = hashlib.sha256(
        payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()
    assert summary["preregistration"]["sha256"] == digest
    assert summary["preregistration"]["status"] == "locked_before_run"
    assert summary["preregistration"]["path"] == "probes/w20_eta_fairness_prereg.json"
    assert summary["lane_section"] == "28.57"


def test_summary_declares_no_main_scoreboard_attempt() -> None:
    summary = _summary()
    assert summary["promoted"] is False
    assert summary["main_scoreboard_attempts_added"] == 0
    assert summary["cumulative_main_scoreboard_attempts"] == CUMULATIVE_ATTEMPTS
    assert summary["uses_no_reaxys_numbers"] is True
    assert summary["gate_log10_cP"] == GATE
    assert summary["tolerance"] == TOLERANCE
    assert summary["task_id"] == "week20_w20_1_eta_fairness"


def test_registered_config_records_the_run_that_happened() -> None:
    config = _summary()["registered_config"]
    assert config["n_splits"] == 5
    assert config["n_repeats"] == 5
    assert config["repeat_seeds"] == [42, 1234, 2026, 31337, 7]
    assert config["ensemble_seeds"] == [42, 1234, 2026]
    assert config["inner_splits"] == 3
    assert config["chemprop_epochs"] == 30
    assert config["chemprop_epochs_registered_in_w19"] == 60
    assert config["incumbent_grid"] == [row[0] for row in INCUMBENT_GRID_PIN]
    assert config["placebo_seed"] == 20260928


def test_the_incumbent_reproduces_its_frozen_reading_exactly() -> None:
    """The run is void unless abs_gap is 0.0 on the W19-D5 split; it is registered first."""

    pools = _summary()["pools"]
    expected = {
        POOL_PRIMARY: CALIBER_INCUMBENT_ROW,
        POOL_SECONDARY: CALIBER_INCUMBENT_FAMILY,
    }
    for name in POOL_ORDER:
        reproduction = pools[name]["incumbent_in_place_reproduction"]
        assert reproduction["model"] == "MorganTemperatureXGBoost"
        assert reproduction["abs_gap"] == 0.0
        assert reproduction["matches_frozen"] is True
        assert reproduction["mae_log10_cP"] == expected[name]
        assert reproduction["frozen_mae_log10_cP"] == expected[name]
        assert "GroupShuffleSplit" in reproduction["split"]


def test_the_grouped_grid_covers_the_pool_exactly() -> None:
    pools = _summary()["pools"]
    for name in POOL_ORDER:
        record = pools[name]
        assert record["cells"] == 25
        assert record["keys"] < record["rows"]
        assert record["test_rows_pooled"] == 5 * record["rows"]


def test_both_arms_gate_status_is_reported_and_handled() -> None:
    for name in POOL_ORDER:
        gate = _summary()["pools"][name]["gate"]
        chemprop = _summary()["pools"][name]["chemprop_aligned"]
        incumbent = _summary()["pools"][name]["incumbent_aligned"]
        chemprop_passed = bool(chemprop["cross_seed_mean_mae_log10_cP"] < GATE)
        incumbent_passed = bool(incumbent["cross_seed_mean_mae_log10_cP"] < GATE)
        assert gate["chemprop_cross_seed_mean_passed"] is chemprop_passed
        assert gate["incumbent_cross_seed_mean_passed"] is incumbent_passed
        unchanged = (
            chemprop_passed == W19_CHEMPROP_ROW_PASSED
            and incumbent_passed == W19_INCUMBENT_ROW_PASSED
        )
        assert gate["gate_state_unchanged_vs_w19"] is unchanged
        assert gate["value"] == GATE
        assert gate["tolerance"] == TOLERANCE


def test_the_verdict_follows_the_registered_rule() -> None:
    summary = _summary()
    assert summary["verdict"] in VERDICT_VOCABULARY
    for name in POOL_ORDER:
        record = summary["pools"][name]
        chemprop_gate = bool(record["gate"]["chemprop_cross_seed_mean_passed"])
        incumbent_gate = bool(record["gate"]["incumbent_cross_seed_mean_passed"])
        expected = _verdict_from(float(record["delta"]["mean"]), chemprop_gate, incumbent_gate)
        assert record["verdict"] == expected
    assert summary["verdict"] == summary["pools"][POOL_PRIMARY]["verdict"]


def test_the_primary_delta_is_reported_consistently() -> None:
    summary = _summary()
    primary = summary["pools"][POOL_PRIMARY]
    chemprop = primary["chemprop_aligned"]
    incumbent = primary["incumbent_aligned"]
    delta = primary["delta"]
    assert summary["delta_mae_log10_cP"] == delta["mean"]
    assert delta["mean"] == pytest.approx(
        chemprop["cross_seed_mean_mae_log10_cP"] - incumbent["cross_seed_mean_mae_log10_cP"],
        abs=1e-15,
    )
    assert set(delta["seed_values"]) == {"42", "1234", "2026"}
    for seed in ("42", "1234", "2026"):
        assert delta["seed_values"][seed] == pytest.approx(
            chemprop["seed_values"][seed] - incumbent["seed_values"][seed], abs=1e-15
        )
    assert delta["min"] <= delta["mean"] <= delta["max"]
    assert chemprop["cross_seed_mean_mae_log10_cP"] == pytest.approx(
        sum(chemprop["seed_values"].values()) / 3, abs=1e-15
    )
    assert incumbent["cross_seed_mean_mae_log10_cP"] == pytest.approx(
        sum(incumbent["seed_values"].values()) / 3, abs=1e-15
    )
    assert set(primary["incumbent_aligned"]["selected_config_counts"]) <= {
        row[0] for row in INCUMBENT_GRID_PIN
    }
    assert sum(primary["incumbent_aligned"]["selected_config_counts"].values()) == 25


def test_the_delta_matches_the_registered_verdict_bands() -> None:
    summary = _summary()
    delta = float(summary["delta_mae_log10_cP"])
    verdict = str(summary["verdict"])
    if abs(delta) <= TOLERANCE:
        assert verdict == "representation_sensitive_gate_undetermined"
    elif delta <= -TOLERANCE:
        assert verdict in ("eta_crosses_gate_out_of_fold", "incumbent_budget_closes_gate")
    else:
        assert verdict == "incumbent_confirmed"


def test_w20_3_authorisation_follows_the_verdict() -> None:
    summary = _summary()
    assert summary["w20_3_rule_text"] == W20_3_RULE
    assert summary["w20_3_eta_authorised"] is (
        summary["verdict"] == "eta_crosses_gate_out_of_fold"
    )


def test_the_placebo_is_reported_with_its_collapse_state() -> None:
    placebo = _summary()["pools"][POOL_PRIMARY]["placebo"]
    assert placebo is not None
    assert placebo["arm"] == "placebo_shuffled_target"
    assert placebo["seed"] == 20260928
    assert placebo["cells"] == 25
    assert placebo["members"] == 1
    assert placebo["collapsed"] is (
        placebo["mae_log10_cP"] >= placebo["constant_predictor_mae_log10_cP"]
    )


def test_repeats_csv_is_exactly_the_grid_projection() -> None:
    with REPEATS_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(POOL_ORDER) * 25 * 3 * 2
    assert {row["arm"] for row in rows} == {"chemprop_aligned", "incumbent_aligned"}
    assert {row["pool"] for row in rows} == set(POOL_ORDER)
    assert {row["member"] for row in rows} == {"seed-42", "seed-1234", "seed-2026"}
    assert {int(row["repeat_seed"]) for row in rows} == {42, 1234, 2026, 31337, 7}
    assert {int(row["fold_index"]) for row in rows} == {0, 1, 2, 3, 4}
    for row in rows:
        assert float(row["mae_log10_cP"]) >= 0.0
        assert int(row["train_rows"]) > 0 and int(row["test_rows"]) > 0


def test_the_summary_pins_both_artifact_digests() -> None:
    summary = _summary()
    for name, path in (
        ("w20_eta_fairness_repeats.csv", REPEATS_PATH),
        ("w20_eta_fairness.md", REPORT_PATH),
    ):
        payload = path.read_bytes()
        digest = hashlib.sha256(
            payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ).hexdigest()
        assert summary["artifacts"][name] == digest


def test_the_report_states_the_verdict_and_the_w20_3_rule() -> None:
    summary = _summary()
    text = _text(REPORT_PATH)
    assert "# W20-1: the eta fairness review" in text
    assert str(summary["verdict"]) in text
    assert "delta = " in text
    assert "GroupKFold by InChIKey" in text
    assert "W20-3 decision" in text
    assert summary["w20_3_rule_text"] in text
    for name in POOL_ORDER:
        assert name in text


def test_the_fragment_opens_the_lane_section() -> None:
    first_line = _text(FRAGMENT_PATH).splitlines()[0]
    assert first_line.startswith(FRAGMENT_FIRST_LINE_PREFIX)
    assert first_line.endswith(FRAGMENT_FIRST_LINE_SUFFIX)


def test_the_fragment_carries_the_discipline_fields() -> None:
    text = _text(FRAGMENT_PATH)
    assert "promoted = false" in text
    assert "cumulative_main_scoreboard_attempts_after_this_shot = 11" in text
    assert "reaxys_values_used = 0" in text
    assert str(_summary()["verdict"]) in text


def test_the_figure_is_a_real_png() -> None:
    raw = FIGURE_PATH.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 10_000


def test_module_constants_match_the_preregistration() -> None:
    assert eta.TASK_ID == "week20_w20_1_eta_fairness"
    assert eta.N_SPLITS == 5
    assert eta.N_REPEATS == 5
    assert eta.REPEAT_SEEDS == (42, 1234, 2026, 31337, 7)
    assert eta.ENSEMBLE_SEEDS == (42, 1234, 2026)
    assert eta.INNER_SPLITS == 3
    assert eta.MAE_GATE == GATE
    assert eta.TOLERANCE == TOLERANCE
    assert eta.EPOCHS == 30
    assert eta.EPOCHS_REGISTERED_IN_W19 == 60
    assert eta.PLACEBO_SEED == 20260928
    assert eta.INCUMBENT_MODEL == "MorganTemperatureXGBoost"
    assert eta.INCUMBENT_GRID_NAMES == tuple(row[0] for row in INCUMBENT_GRID_PIN)
    assert eta.INCUMBENT_FROZEN_MAE == {
        POOL_PRIMARY: CALIBER_INCUMBENT_ROW,
        POOL_SECONDARY: CALIBER_INCUMBENT_FAMILY,
    }
    assert eta.W19_REGISTERED_GATE_STATES == {
        "chemprop_row_level_passed": W19_CHEMPROP_ROW_PASSED,
        "incumbent_row_level_passed": W19_INCUMBENT_ROW_PASSED,
    }


def test_the_repeat_grid_is_group_disjoint_and_partitions_the_rows() -> None:
    """The split identity properties are asserted on a synthetic key list, cheaply."""

    keys = [f"K{index % 12}" for index in range(60)]
    folds = eta.build_repeat_folds(keys, repeat_seeds=eta.REPEAT_SEEDS[:2], n_splits=5)
    assert len(folds) == 10
    for seed in eta.REPEAT_SEEDS[:2]:
        covered: set[int] = set()
        for fold in folds:
            if fold["repeat_seed"] != seed:
                continue
            train_keys = {keys[int(index)] for index in fold["train_indices"]}
            test_keys = {keys[int(index)] for index in fold["test_indices"]}
            assert not (train_keys & test_keys)
            covered |= {int(index) for index in fold["test_indices"]}
        assert covered == set(range(len(keys)))
