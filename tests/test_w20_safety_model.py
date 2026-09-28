"""Literal pins for the Week 20 W20-2 Step 2 safety-channel modelability lane.

Section 28.58, the reading-producing half.  Everything asserted here is typed out
rather than re-derived from prose: the frozen shot number, the locked split,
features, learner and decision rule, the three per-property readings with their
baseline and placebo arms, the declared sample gap, the isolation rule, the
decisions fragment header and the repeats CSV projection.  A silent edit to the
module, the preregistration, the summary, the report or the fragment turns this
file red instead of quietly re-baselining the deliverable.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_safety_model as model

MODULE_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_model.py"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_model_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_model_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_safety_model.md"
REPEATS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_safety_model_repeats.csv"
ARMS_CSV_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_safety_ablation_arms.csv"
FRAGMENT_PATH = REPOSITORY_ROOT / "reports" / "_w20_section_w202.md"
TEST_PATH = Path(__file__)

FILES = (
    MODULE_PATH,
    PREREG_PATH,
    SUMMARY_PATH,
    REPORT_PATH,
    REPEATS_PATH,
    ARMS_CSV_PATH,
    FRAGMENT_PATH,
    TEST_PATH,
)

# property -> (reference MAE K, cross-seed mean MAE K, baseline MAE K,
#              relative reduction, placebo MAE K, seed spread K, verdict)
PER_PROPERTY_PINS: dict[str, tuple[float, float, float, float, float, float, str]] = {
    "mp": (
        10.4,
        24.97767123875773,
        40.645869505093216,
        0.3854807009202288,
        48.35533498846853,
        0.3526180978662765,
        "modelable",
    ),
    "bp": (
        4.6,
        25.395136749805708,
        51.918480354950496,
        0.5108651760184995,
        59.37467148362235,
        0.39471736728302176,
        "modelable",
    ),
    "fp": (
        4.8,
        18.93154740989103,
        41.417524232531726,
        0.5429097281719921,
        47.20429030793726,
        0.26310250787105716,
        "modelable",
    ),
}

SAMPLE_GAP_PINS = (18.838709677419356, 22.768817204301076)

ISOLATION_NUMBERS = (
    "0.4091179943351143",
    "0.4766400383507876",
    "0.08506361044387624",
    "0.08908094784092072",
)

DOMAIN_DECLARATION = "安全通道只进 ε 侧，不得进 η 侧。"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prereg() -> dict:
    return json.loads(_text(PREREG_PATH))


def _summary() -> dict:
    return json.loads(_text(SUMMARY_PATH))


def test_every_file_exists() -> None:
    for path in FILES:
        assert path.is_file(), f"missing file: {path}"


def test_utf8_no_bom_and_lf_only() -> None:
    for path in FILES:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        assert b"\r\n" not in raw, f"CRLF in {path.name}"


def test_prereg_pins_the_locked_design() -> None:
    data = _prereg()
    assert data["prereg_status"] == "locked_before_run"
    assert data["schema_version"] == "w20_safety_model_plan_v0"
    assert data["task"] == "week20_w20_2_step2_safety_channel_modelability"
    assert data["section"] == "28.58"
    assert data["usable_rows_pin"] == 186
    assert data["split"]["group_column"] == "inchikey"
    assert data["split"]["n_splits"] == 5
    assert data["split"]["seeds"] == [42, 1234, 2026, 31337, 7]
    assert data["model"]["family"] == "sklearn.ensemble.ExtraTreesRegressor"
    assert data["model"]["params"] == {"n_estimators": 300, "n_jobs": 1}
    assert data["features"]["morgan_bits"] == 256
    assert data["features"]["feature_count"] == 281
    assert data["decision_rule"]["modelability_relative_margin"] == 0.2
    assert data["decision_rule"]["seed_spread_tolerance_K"] == 2.0
    assert data["decision_rule"]["placebo_seed"] == 20260928


def test_prereg_declares_shot_22_and_no_promotion() -> None:
    data = _prereg()
    assert data["produces_reading"] is True
    assert data["shot_number_taken"] == 22
    assert data["promoted"] is False
    assert data["main_scoreboard_untouched"] is True
    assert data["scoreboard_attempts_delta"] == 0
    assert data["reaxys_values_used"] == 0
    assert data["writes_any_pool"] is False
    assert data["models_fitted"] == 0
    assert data["blocking_conditions_at_lock"] == []


def test_prereg_records_the_reference_target_and_the_isolation_rule() -> None:
    data = _prereg()
    assert data["reference_target"]["mae_K"] == {"mp": 10.4, "bp": 4.6, "fp": 4.8}
    assert data["reference_target"]["train_rows_per_property"] == {"min": 3504, "max": 4235}
    assert data["reference_target"]["forbidden_use"] == (
        "direct benchmarking or any superiority claim"
    )
    assert data["isolation"]["rule"] == "this lane may never be compared against either set"


def test_prereg_digest_is_recorded_in_the_summary() -> None:
    summary = _summary()
    import hashlib

    digest = hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()
    assert summary["prereg"]["sha256"] == digest
    assert summary["prereg"]["bytes"] == PREREG_PATH.stat().st_size


def test_summary_declares_the_reading_and_the_discipline_flags() -> None:
    data = _summary()
    assert data["status"] == "executed"
    assert data["produces_reading"] is True
    assert data["shot_number_taken"] == 22
    assert data["promoted"] is False
    assert data["main_scoreboard_untouched"] is True
    assert data["scoreboard_attempts_delta"] == 0
    assert data["reaxys_values_used"] == 0
    assert data["writes_any_pool"] is False
    assert data["models_fitted"] == 150


def test_summary_pins_the_tree_per_property_readings() -> None:
    data = _summary()["per_property"]
    assert set(data) == set(PER_PROPERTY_PINS)
    for name, pins in PER_PROPERTY_PINS.items():
        reference_mae, model_mae, baseline_mae, reduction, placebo_mae, spread, verdict = pins
        block = data[name]
        assert block["model"]["cross_seed_mean_mae_K"] == pytest.approx(model_mae, abs=1e-12)
        assert block["model"]["cross_seed_mean_baseline_mae_K"] == pytest.approx(
            baseline_mae, abs=1e-12
        )
        assert block["model"]["relative_reduction_vs_baseline"] == pytest.approx(
            reduction, abs=1e-15
        )
        assert block["model"]["seed_spread_K"] == pytest.approx(spread, abs=1e-12)
        assert block["placebo"]["cross_seed_mean_mae_K"] == pytest.approx(placebo_mae, abs=1e-12)
        assert block["verdict"] == verdict
        assert block["seed_spread_within_tolerance"] is True
        # the lane never claims to beat the reference: our MAE is the larger one
        assert block["model"]["cross_seed_mean_mae_K"] > reference_mae


def test_summary_verdict_is_modelable_all() -> None:
    assert _summary()["verdict"] == "modelable_all"


def test_the_placebo_never_clears_the_modelability_margin() -> None:
    for name, block in _summary()["per_property"].items():
        placebo_block = block["placebo"]
        model_block = block["model"]
        assert placebo_block["relative_reduction_vs_baseline"] < 0.0, name
        assert (
            placebo_block["relative_reduction_vs_baseline"]
            < model_block["relative_reduction_vs_baseline"]
        )
        assert placebo_block["cross_seed_mean_mae_K"] > model_block["cross_seed_mean_mae_K"]
        assert block["verdict"] != "void_placebo_leak"


def test_the_sample_gap_is_declared_next_to_the_reference() -> None:
    gap = _summary()["sample_gap"]
    assert gap["our_usable_rows"] == 186
    assert gap["our_rows_per_target"] == {"mp": 202, "bp": 216, "fp": 189}
    assert gap["reference_rows_per_property"] == {"min": 3504, "max": 4235}
    assert gap["ratio_min"] == pytest.approx(SAMPLE_GAP_PINS[0], abs=1e-12)
    assert gap["ratio_max"] == pytest.approx(SAMPLE_GAP_PINS[1], abs=1e-12)
    assert gap["ratio_min"] > 18.0 and gap["ratio_max"] < 23.0


def test_repeats_csv_is_exactly_the_summary_projection() -> None:
    rows = list(csv.DictReader(_text(REPEATS_PATH).splitlines()))
    expected = [
        {key: str(value) for key, value in row.items()} for row in _summary()["repeats"]
    ]
    assert len(rows) == 150
    assert rows == expected
    assert {row["arm"] for row in rows} == {"model", "placebo"}
    assert {row["property"] for row in rows} == set(PER_PROPERTY_PINS)


def test_arms_csv_left_by_step_one_is_present_and_unchanged() -> None:
    rows = list(csv.DictReader(_text(ARMS_CSV_PATH).splitlines()))
    assert len(rows) == 6
    assert [row["arm"] for row in rows] == (
        ["arm0_v0_unfiltered"] * 3 + ["arm1_v0_liquid_window"] * 3
    )
    arm1_at_fifty = [row for row in rows if row["arm"] == "arm1_v0_liquid_window"][-1]
    assert arm1_at_fifty["top_k_hit_rate"] == "0.98"
    assert arm1_at_fifty["candidate_list_change_count"] == "98"


def test_report_states_the_domain_declaration_verbatim() -> None:
    assert DOMAIN_DECLARATION in _text(REPORT_PATH)


def test_report_quotes_the_reference_and_the_sample_gap_together() -> None:
    text = _text(REPORT_PATH)
    for token in ("10.4", "4.6", "4.8", "3,504", "4,235", "186"):
        assert token in text, f"report is missing {token}"
    assert "直接对标" in text and "宣称超越" in text
    assert "18.838709677419356" in text and "22.768817204301076" in text


def test_report_states_the_isolation_rule_with_all_four_numbers() -> None:
    text = _text(REPORT_PATH)
    assert "隔离声明" in text
    assert "不得与 ε 主记分牌" in text
    for number in ISOLATION_NUMBERS:
        assert number in text, f"report is missing {number}"
    assert "scoreboard_attempts_delta = 0" in text
    assert "reaxys_values_used = 0" in text
    assert "shot 22" in text


def test_report_sections_present() -> None:
    text = _text(REPORT_PATH)
    for section in (
        "## 1. 参考靶与样本差",
        "## 2. 分域声明",
        "## 6. 读数",
        "## 7. 判定与边界",
        "## 8. 隔离声明与记分牌纪律",
        "## 12. 复现与产物摘要",
    ):
        assert section in text, f"missing section: {section}"


def test_report_pins_the_headline_numbers_verbatim() -> None:
    text = _text(REPORT_PATH)
    for token in (
        "0.7357723577235772",
        "0.16509926854754442",
        "0.1270358306188925",
        "24.97767123875773",
        "25.395136749805708",
        "18.93154740989103",
        "modelable_all",
        "28.58",
    ):
        assert token in text, f"missing pinned token: {token}"


def test_fragment_starts_with_section_28_58_and_is_dated() -> None:
    first_line = _text(FRAGMENT_PATH).splitlines()[0]
    assert first_line.startswith("## 28.58 ")
    assert first_line.endswith("（2026-09-28）")


def test_fragment_declares_the_four_required_fields() -> None:
    text = _text(FRAGMENT_PATH)
    for token in (
        "produces_reading",
        "shot_number_taken",
        "scoreboard_attempts_delta",
        "reaxys_values_used",
    ):
        assert token in text, f"fragment is missing {token}"
    assert "shot_number_taken = 22" in text
    assert DOMAIN_DECLARATION in text


def test_module_pins_match_the_preregistration() -> None:
    assert model.SHOT_NUMBER_TAKEN == 22
    assert model.PRODUCES_READING is True
    assert model.PROMOTED is False
    assert model.SCOREBOARD_ATTEMPTS_DELTA == 0
    assert model.REAXYS_VALUES_USED == 0
    assert model.N_SPLITS == 5
    assert model.SEEDS == (42, 1234, 2026, 31337, 7)
    assert model.MORGAN_BITS == 256
    assert model.FEATURE_COUNT == 281
    assert model.MODELABILITY_RELATIVE_MARGIN == 0.20
    assert model.SEED_SPREAD_TOLERANCE_K == 2.0
    assert model.EXPECTED_USABLE_ROWS == 186
    assert model.MODEL_PARAMS == {"n_estimators": 300, "n_jobs": 1}


def test_module_refuses_to_run_without_the_preregistration(tmp_path: Path) -> None:
    blockers = model.blocking_conditions(prereg_path=tmp_path / "absent.json")
    assert any("preregistration is not on disk" in blocker for blocker in blockers)


def test_usable_rows_are_the_complete_window_set() -> None:
    liquid_rows = model.read_csv_rows(model.LIQUID_WINDOW_PATH)
    registry_rows = model.read_csv_rows(model.REGISTRY_PATH)
    rows = model.usable_rows(liquid_rows, registry_rows)
    assert len(rows) == 186
    assert len({row["inchikey"] for row in rows}) == 186
    assert model.target_availability(liquid_rows) == {"mp": 202, "bp": 216, "fp": 189}


def test_repeat_folds_are_deterministic_and_cover_every_row() -> None:
    rows = model.usable_rows(
        model.read_csv_rows(model.LIQUID_WINDOW_PATH),
        model.read_csv_rows(model.REGISTRY_PATH),
    )
    first = model.repeat_folds(rows, seed=42)
    second = model.repeat_folds(rows, seed=42)
    assert first == second
    assert len(first) == 5
    covered = sorted(index for _, test in first for index in test)
    assert covered == list(range(186))


def test_run_reproduces_the_summary_on_disk() -> None:
    assert model.run() == _summary()