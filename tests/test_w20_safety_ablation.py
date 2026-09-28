"""Literal pins for the Week 20 W20-2 Step 1 influence ablation (section 28.58).

Everything this file asserts is typed out here rather than re-derived from prose:
the three preregistration pins, the coverage table, the two arm purities with
their containment baseline, the overlap numbers, the placebo envelope and the two
declarations the lane is not allowed to omit.  A silent edit to the module, the
preregistration, the summary or the report turns this file red instead of quietly
re-baselining the deliverable.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_safety_ablation as ablation

MODULE_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_ablation.py"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_ablation_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_ablation_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_safety_ablation.md"
TEST_PATH = Path(__file__)

FILES = (MODULE_PATH, PREREG_PATH, SUMMARY_PATH, REPORT_PATH, TEST_PATH)

# Pinned coverage, re-measured from disk on 2026-09-28.
COVERAGE_PINS: dict[str, tuple[int, int, float, bool]] = {
    "v03": (181, 246, 0.7357723577235772, True),
    "v01": (158, 957, 0.16509926854754442, False),
    "v02": (156, 1228, 0.1270358306188925, False),
}

# Arm pins: name -> (pool size, density, purity@10, purity@20, purity@50).
ARM_PINS: dict[str, tuple[int, float, float, float, float]] = {
    "arm0_v0_unfiltered": (29519, 0.002642365933805346, 0.0, 0.0, 0.02),
    "arm1_v0_liquid_window": (70, 0.9142857142857143, 1.0, 1.0, 0.98),
}

OVERLAP_PINS: dict[str, tuple[float, float, int]] = {
    "10": (0.0, 0.0, 20),
    "20": (0.0, 0.0, 40),
    "50": (0.010101010101010102, 0.02, 98),
}

PLACEBO_MAX_PINS = {"10": 0.1, "20": 0.05, "50": 0.04}

DOMAIN_DECLARATION = "安全通道只进 ε 侧，不得进 η 侧。"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prereg() -> dict:
    return json.loads(_text(PREREG_PATH))


def _summary() -> dict:
    return json.loads(_text(SUMMARY_PATH))


def test_all_five_files_exist() -> None:
    for path in FILES:
        assert path.is_file(), f"missing file: {path}"


def test_utf8_no_bom_and_lf_only() -> None:
    for path in FILES:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        assert b"\r\n" not in raw, f"CRLF in {path.name}"


def test_prereg_pins_the_three_registration_fields() -> None:
    data = _prereg()
    assert data["prereg_status"] == "locked_before_run"
    assert data["safety_key_set"] == "registry_liquid_window_channel"
    assert data["scored_universe"] == "registry_wide"
    assert data["recommended_set"] == "data/dielectric_v03.csv"
    assert data["recommended_set_role"]
    assert data["coverage_gate"] == 0.3


def test_prereg_records_no_blocker_and_a_stable_input_digest_set() -> None:
    data = _prereg()
    assert data["blocking_conditions"] == []
    assert data["blocking_conditions_at_lock"] == []
    inputs = data["inputs"]
    assert "data/dielectric_v03.csv" in inputs
    assert "data/processed/four_core_key_registry.csv" in inputs
    assert inputs["data/dielectric_v03.csv"]["sha256"] == (
        "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
    )


def test_prereg_declares_step_one_as_shapeless_and_shotless() -> None:
    data = _prereg()
    assert data["shot_number_taken"] is None
    assert data["produces_reading"] is False
    assert data["models_fitted"] == 0
    assert data["promoted"] is False


def test_summary_keeps_every_discipline_flag() -> None:
    data = _summary()
    assert data["status"] == "executed"
    assert data["produces_reading"] is False
    assert data["produces_ablation_numbers"] is True
    assert data["models_fitted"] == 0
    assert data["reaxys_values_used"] == 0
    assert data["writes_any_pool"] is False
    assert data["promoted"] is False
    assert data["main_scoreboard_untouched"] is True
    assert data["scoreboard_attempts_delta"] == 0
    assert data["shot_number_taken"] is None


def test_summary_reproduces_the_frozen_coverage_table() -> None:
    coverage = _summary()["coverage"]
    for roster, (covered, denominator, fraction, passed) in COVERAGE_PINS.items():
        row = coverage[roster]
        assert row["covered_keys"] == covered
        assert row["target_keys"] == denominator
        assert row["coverage_fraction"] == pytest.approx(fraction, abs=1e-15)
        assert row["passed"] is passed
        assert row["gate"] == 0.3


def test_summary_lifts_the_epsilon_side_and_fails_the_eta_side() -> None:
    coverage = _summary()["coverage"]
    assert coverage["v03"]["passed"] is True
    assert coverage["v01"]["passed"] is False
    assert coverage["v02"]["passed"] is False


def test_arm_pins_purity_density_and_pool_size() -> None:
    arms = {arm["name"]: arm for arm in _summary()["arms"]}
    assert set(arms) == set(ARM_PINS)
    for name, (pool, density, p10, p20, p50) in ARM_PINS.items():
        arm = arms[name]
        assert arm["pool_size"] == pool
        assert arm["reference_density_in_pool"] == pytest.approx(density, abs=1e-15)
        assert arm["head_purity"]["10"] == pytest.approx(p10, abs=1e-15)
        assert arm["head_purity"]["20"] == pytest.approx(p20, abs=1e-15)
        assert arm["head_purity"]["50"] == pytest.approx(p50, abs=1e-15)


def test_the_containment_baseline_differs_by_more_than_two_orders() -> None:
    arms = {arm["name"]: arm for arm in _summary()["arms"]}
    filtered = arms["arm1_v0_liquid_window"]["reference_density_in_pool"]
    unfiltered = arms["arm0_v0_unfiltered"]["reference_density_in_pool"]
    assert filtered / unfiltered > 300.0


def test_overlap_pins_jaccard_retention_and_membership_changes() -> None:
    overlap = _summary()["overlap"]
    for k, (jaccard, retention, changes) in OVERLAP_PINS.items():
        row = overlap[k]
        assert row["jaccard"] == pytest.approx(jaccard, abs=1e-15)
        assert row["head_retention"] == pytest.approx(retention, abs=1e-15)
        assert row["membership_changes"] == changes


def test_the_two_heads_are_disjoint_at_the_small_k() -> None:
    overlap = _summary()["overlap"]
    assert overlap["10"]["jaccard"] == 0.0
    assert overlap["20"]["jaccard"] == 0.0


def test_placebo_envelope_is_far_below_the_filtered_arm() -> None:
    placebo = _summary()["placebo_head_purity"]
    for k, ceiling in PLACEBO_MAX_PINS.items():
        row = placebo[k]
        assert row["max"] == pytest.approx(ceiling, abs=1e-15)
        assert row["median"] == 0.0
        assert row["min"] == 0.0
        assert row["max"] < 1.0


def test_report_states_the_domain_declaration_verbatim() -> None:
    assert DOMAIN_DECLARATION in _text(REPORT_PATH)


def test_report_states_the_isolation_rule_with_all_four_numbers() -> None:
    text = _text(REPORT_PATH)
    assert "隔离声明" in text
    assert "不得与 ε 主记分牌" in text
    for number in (
        "0.4091179943351143",
        "0.4766400383507876",
        "0.08506361044387624",
        "0.08908094784092072",
    ):
        assert number in text, f"report is missing {number}"


def test_report_sections_present() -> None:
    text = _text(REPORT_PATH)
    for section in (
        "## 1. 分域声明",
        "## 2. 覆盖门实测",
        "## 7. 判定与边界",
        "## 8. 隔离声明与记分牌纪律",
        "## 9. 数字出处与不可核登记",
    ):
        assert section in text, f"missing section: {section}"


def test_report_pins_the_headline_numbers_verbatim() -> None:
    text = _text(REPORT_PATH)
    for token in (
        "0.7357723577235772",
        "0.16509926854754442",
        "0.1270358306188925",
        "0.002642365933805346",
        "0.9142857142857143",
        "0.010101010101010102",
        "0.8302752293577982",
        "28.58",
    ):
        assert token in text, f"missing pinned token: {token}"


def test_module_pins_match_the_preregistration() -> None:
    assert ablation.SAFETY_KEY_SET == "registry_liquid_window_channel"
    assert ablation.SCORED_UNIVERSE == "registry_wide"
    assert ablation.RECOMMENDED_SET_PATH is not None
    assert ablation.RECOMMENDED_SET_PATH.name == "dielectric_v03.csv"
    assert ablation.COVERAGE_GATE == 0.3
    assert ablation.TOP_K_VALUES == (10, 20, 50)
    assert ablation.COVERAGE_READINGS[ablation.REGISTRY_CHANNEL]["key_count"] == 218


def test_blocking_conditions_refuse_while_a_field_is_unset() -> None:
    blockers = ablation.blocking_conditions(
        safety_key_set_name=None,
        universe=None,
        recommended_set_path=None,
    )
    assert len(blockers) == 3
    assert any("SAFETY_KEY_SET" in blocker for blocker in blockers)
    assert any("SCORED_UNIVERSE" in blocker for blocker in blockers)
    assert any("RECOMMENDED_SET_PATH" in blocker for blocker in blockers)


def test_blocking_conditions_clear_once_the_three_pins_are_set() -> None:
    blockers = ablation.blocking_conditions(
        safety_key_set_name=ablation.REGISTRY_CHANNEL,
        universe=ablation.REGISTRY_UNIVERSE,
        recommended_set_path=ablation.RECOMMENDED_SET_PATH,
    )
    assert blockers == []


def test_blocking_conditions_reject_a_name_outside_the_two_pinned_ones() -> None:
    blockers = ablation.blocking_conditions(
        safety_key_set_name="invented_key_set",
        universe=ablation.REGISTRY_UNIVERSE,
        recommended_set_path=ablation.RECOMMENDED_SET_PATH,
    )
    assert any("not a pinned name" in blocker for blocker in blockers)


def test_safety_key_set_refuses_an_unknown_source() -> None:
    with pytest.raises(ValueError, match="unknown safety key set"):
        ablation.safety_key_set("nonsense", [], [])


def test_purity_and_jaccard_helpers_on_a_hand_checked_case() -> None:
    assert ablation.purity(["a", "b", "c", "d"], {"a", "b"}) == 0.5
    assert ablation.jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
    assert ablation.jaccard([], []) == 0.0
    assert ablation.head_retention(["a", "b"], ["b", "c"]) == 0.5
    with pytest.raises(ValueError, match="empty head"):
        ablation.purity([], {"a"})


def test_placebo_key_sets_keep_the_cardinality_and_vary_the_content() -> None:
    pool = [f"key-{index:03d}" for index in range(120)]
    drawn = ablation.placebo_key_sets(pool, size=40, permutations=25, seed=7)
    assert len(drawn) == 25
    assert {len(entry) for entry in drawn} == {40}
    assert len({tuple(sorted(entry)) for entry in drawn}) > 1
    assert all(entry <= set(pool) for entry in drawn)
    repeated = ablation.placebo_key_sets(pool, size=40, permutations=25, seed=7)
    assert drawn == repeated
    with pytest.raises(ValueError, match="placebo size"):
        ablation.placebo_key_sets(pool, size=121)


def test_coverage_verdicts_come_from_the_frozen_readings() -> None:
    verdicts = ablation.coverage_verdicts()
    for roster, (covered, denominator, fraction, passed) in COVERAGE_PINS.items():
        row = verdicts[roster]
        assert row["covered_keys"] == covered
        assert row["target_keys"] == denominator
        assert row["coverage_fraction"] == pytest.approx(fraction, abs=1e-15)
        assert row["passed"] is passed


def test_run_reproduces_the_summary_on_disk() -> None:
    assert ablation.run() == _summary()



ARMS_CSV_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_safety_ablation_arms.csv"


def test_arms_csv_is_a_projection_of_the_frozen_summary() -> None:
    assert ARMS_CSV_PATH.is_file()
    raw = ARMS_CSV_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    arms = {arm["name"]: arm for arm in _summary()["arms"]}
    overlap = _summary()["overlap"]
    assert len(rows) == 6
    for row in rows:
        name = row["arm"]
        k = row["k"]
        assert row["pool_size"] == str(arms[name]["pool_size"])
        assert float(row["top_k_hit_rate"]) == pytest.approx(arms[name]["head_purity"][k])
        assert float(row["reference_density_in_pool"]) == pytest.approx(
            arms[name]["reference_density_in_pool"]
        )
        if name == "arm0_v0_unfiltered":
            assert row["jaccard_vs_arm0"] == "1.0"
            assert row["head_retention_vs_arm0"] == "1.0"
            assert row["candidate_list_change_count"] == "0"
        else:
            assert float(row["jaccard_vs_arm0"]) == pytest.approx(overlap[k]["jaccard"])
            assert float(row["head_retention_vs_arm0"]) == pytest.approx(
                overlap[k]["head_retention"]
            )
            assert row["candidate_list_change_count"] == str(
                overlap[k]["membership_changes"]
            )
