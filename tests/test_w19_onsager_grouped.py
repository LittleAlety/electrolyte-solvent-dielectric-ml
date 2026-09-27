"""Literal pins for the Week 19 D3 Onsager out-of-family rerun (AF-13 discipline).

Every number this file asserts is typed out here rather than re-derived from prose: the pool census, the
three question verdicts, the five gate bars, the per-arm gate outcomes and the bit-for-bit reproduction
check.  A silent edit to the probe, to its stored readings or to the report turns this file red instead of
quietly re-baselining the deliverable.

Scope note: this shot never touches the epsilon scoreboard.  The frozen baseline and the frozen headline
are asserted only inside the boundary that keeps them out of this lane, and the cumulative attempt count
stays at 11.
"""

from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_onsager_grouped.md"
SECTION_PATH = REPOSITORY_ROOT / "reports" / "_w19_section_d3.md"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_onsager_grouped_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_onsager_grouped_summary.json"
PROBE_PATH = REPOSITORY_ROOT / "probes" / "w19_onsager_grouped.py"
TEST_PATH = Path(__file__)

NEW_FILES = (PROBE_PATH, PREREG_PATH, SUMMARY_PATH, REPORT_PATH, SECTION_PATH, TEST_PATH)

POOL_ROWS = 234
POOL_DISTINCT_INCHIKEY = 234
POOL_STRUCTURE_GROUPS = 111
POOL_SINGLETON_GROUPS = 76
POOL_MAX_GROUP_SIZE = 31
POOL_FAILED_ROWS = 4
POOL_WITHHELD_ROWS = 1
POOL_N_FOLDS = 50
PRIMARY_TRAIN_MIN = 149
PRIMARY_TRAIN_MAX = 206

# The three question verdicts, verbatim from the summary.
VERDICT_Q1 = "delta_layer_survives_out_of_family"
VERDICT_Q2 = "sign_split_not_preserved_out_of_family"
VERDICT_Q3 = "zone_still_unsolvable_out_of_family"

# The five gate names, verbatim from the pre-registration.
GATE_NAMES = (
    "a_donor_mae_below_onsager",
    "b_ionic_mae_not_worse_than_onsager",
    "c_high_permittivity_improved",
    "d_overall_mae_below_structured_offset",
    "e_donor_mae_below_structured_offset",
)

# Gate bars on the primary grouped reading, all taken from the stored summary.
BAR_A_MAE_ASSOC = 16.66422703535138
BAR_B_MAE_IONIC = 41.22140207561585
BAR_C_MAE_GT60 = 87.02347866934045
BAR_C_SPEARMAN_GT60 = -0.7999999999999999
BAR_D_MAE = 9.712536036273614
BAR_E_MAE_ASSOC = 14.83331535120289

# Registered per-arm gate outcomes on the primary grouped reading.
PER_ARM_FAILED_GATES = {
    "D0_delta_core": (),
    "D1_delta_core_morgan": ("d_overall_mae_below_structured_offset",),
    "D2_delta_log": (
        "a_donor_mae_below_onsager",
        "b_ionic_mae_not_worse_than_onsager",
        "d_overall_mae_below_structured_offset",
        "e_donor_mae_below_structured_offset",
    ),
}
CONFIRMATORY_ARMS = ("D0_delta_core", "D1_delta_core_morgan", "D2_delta_log")
PRIMARY_HEADLINE_ARM = "D0_delta_core"

# Reproduction check and frozen coordinates.
ROW_LEVEL_REFERENCE_PATH = "probes/dielectric_onsager_delta_summary.json"
ROW_LEVEL_REFERENCE_SHA256 = "3acd499b2653135556bcdd61a1bdb2e8977973821f8b00f804e2431edef1754b"
PREREG_SHA256 = "921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839"
FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
SCOREBOARD_ATTEMPTS_LITERAL = "11"

REPORT_FIRST_LINE = "# W19-D3: the Onsager residual layer under an out-of-family split"
SECTION_FIRST_LINE_PREFIX = "## 28.52 "


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _summary() -> dict:
    return json.loads(_read(SUMMARY_PATH))


def _prereg() -> dict:
    return json.loads(_read(PREREG_PATH))


def test_three_new_files_exist() -> None:
    for path in NEW_FILES:
        assert path.is_file(), f"missing lane file: {path}"
        assert path.stat().st_size > 0, f"empty lane file: {path}"


def test_report_first_line() -> None:
    assert _read(REPORT_PATH).splitlines()[0] == REPORT_FIRST_LINE


def test_report_carries_the_required_sections() -> None:
    text = _read(REPORT_PATH)
    for heading in (
        "## 0. Red lines and positioning",
        "## 1. Pool and splitters",
        "## 2. Readings, per arm",
        "## 3. Gate table for the primary grouped reading",
        "## 4. The three questions",
        "## 5. Reproduction check",
        "## 6. Limitations and honest boundary",
        "## 7. What this does not do",
        "## 8. Artifacts",
    ):
        assert heading in text, f"missing section: {heading}"


def test_report_is_lf_without_bom() -> None:
    raw = REPORT_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw


def test_pool_census_is_literal_and_matches_the_summary() -> None:
    text = _read(REPORT_PATH)
    summary = _summary()
    pool = summary["pool"]
    groups = summary["structure_groups"]
    assert pool["rows"] == POOL_ROWS
    assert pool["distinct_inchikey"] == POOL_DISTINCT_INCHIKEY
    assert pool["failed_rows"] == POOL_FAILED_ROWS
    assert pool["withheld_rows"] == POOL_WITHHELD_ROWS
    assert groups["n_groups"] == POOL_STRUCTURE_GROUPS
    assert groups["singleton_groups"] == POOL_SINGLETON_GROUPS
    assert groups["max_group_size"] == POOL_MAX_GROUP_SIZE
    for literal in ("234", "111", "76", "31"):
        assert literal in text, f"pool literal not printed in the report: {literal}"


def test_primary_reading_shape_is_literal() -> None:
    text = _read(REPORT_PATH)
    reading = _summary()["readings"]["structure_family"]
    assert reading["n_folds"] == POOL_N_FOLDS
    assert reading["train_count_min"] == PRIMARY_TRAIN_MIN
    assert reading["train_count_max"] == PRIMARY_TRAIN_MAX
    assert "50 folds" in text
    assert "train 149-206" in text


def test_three_question_verdicts_are_literal_and_match_the_summary() -> None:
    text = _read(REPORT_PATH)
    questions = _summary()["three_questions"]
    assert questions["q1_grouped_delta_gates"]["verdict"] == VERDICT_Q1
    assert questions["q2_domain_sign_split"]["verdict"] == VERDICT_Q2
    assert questions["q3_high_permittivity_zone"]["verdict"] == VERDICT_Q3
    for verdict in (VERDICT_Q1, VERDICT_Q2, VERDICT_Q3):
        assert verdict in text, f"verdict not printed in the report: {verdict}"


def test_gate_names_and_bars_are_literal_and_match_the_summary() -> None:
    text = _read(REPORT_PATH)
    prereg = _prereg()
    for name in GATE_NAMES:
        assert name in prereg["gates"], f"gate missing from the pre-registration: {name}"
        assert name in text, f"gate name not printed in the report: {name}"
    metrics = _summary()["readings"]["structure_family"]["overall_metrics"]
    onsager = metrics["O0_onsager"]
    offset = metrics["O1_structured_offset"]
    assert onsager["mae_assoc"] == BAR_A_MAE_ASSOC
    assert onsager["mae_ionic"] == BAR_B_MAE_IONIC
    assert onsager["mae_gt60"] == BAR_C_MAE_GT60
    assert onsager["spearman_gt60"] == BAR_C_SPEARMAN_GT60
    assert offset["mae"] == BAR_D_MAE
    assert offset["mae_assoc"] == BAR_E_MAE_ASSOC
    for bar in (
        "16.66422703535138",
        "41.22140207561585",
        "87.02347866934045",
        "-0.7999999999999999",
        "9.712536036273614",
        "14.83331535120289",
    ):
        assert bar in text, f"gate bar not printed in the report: {bar}"


def _recompute_gates(reading: dict) -> dict:
    metrics = reading["overall_metrics"]
    onsager = metrics["O0_onsager"]
    offset = metrics["O1_structured_offset"]
    out = {}
    for arm in CONFIRMATORY_ARMS:
        arm_metrics = metrics[arm]
        out[arm] = {
            "a_donor_mae_below_onsager": arm_metrics["mae_assoc"] < onsager["mae_assoc"],
            "b_ionic_mae_not_worse_than_onsager": arm_metrics["mae_ionic"] <= onsager["mae_ionic"],
            "c_high_permittivity_improved": (
                arm_metrics["mae_gt60"] < onsager["mae_gt60"]
                or arm_metrics["spearman_gt60"] > onsager["spearman_gt60"]
            ),
            "d_overall_mae_below_structured_offset": arm_metrics["mae"] < offset["mae"],
            "e_donor_mae_below_structured_offset": arm_metrics["mae_assoc"] < offset["mae_assoc"],
        }
    return out


def test_per_arm_gate_outcomes_match_the_summary() -> None:
    reading = _summary()["readings"]["structure_family"]
    gates = reading["gates"]
    assert gates["headline_arm"] == PRIMARY_HEADLINE_ARM
    assert gates["passed"] is True
    recomputed = _recompute_gates(reading)
    for arm in CONFIRMATORY_ARMS:
        stored = gates["per_arm"][arm]
        assert stored["gates"] == recomputed[arm], f"gate booleans disagree for {arm}"
        assert stored["failed_gates"] == list(PER_ARM_FAILED_GATES[arm])
        assert stored["passed"] is (len(PER_ARM_FAILED_GATES[arm]) == 0)
    assert all(recomputed["D0_delta_core"].values())


def test_report_states_the_per_arm_gate_failures() -> None:
    text = _read(REPORT_PATH)
    assert "PASS |" in text
    assert "FAIL |" in text
    assert "**true**" in text


def test_reproduction_check_is_literal_and_matches_the_summary() -> None:
    text = _read(REPORT_PATH)
    check = _summary()["reproduction_check"]
    assert check["max_abs_difference"] == 0
    assert check["reproduced_bit_for_bit"] is True
    assert check["row_level_reference_path"] == ROW_LEVEL_REFERENCE_PATH
    assert check["row_level_reference_sha256"] == ROW_LEVEL_REFERENCE_SHA256
    assert "max_abs_difference = 0.0" in text
    assert "reproduced_bit_for_bit = true" in text
    assert ROW_LEVEL_REFERENCE_SHA256 in text
    assert "0.0" in text


def test_prereg_digest_and_frozen_coordinates_are_literal() -> None:
    text = _read(REPORT_PATH)
    prereg = _prereg()
    assert prereg["status"] == "locked_before_run"
    assert prereg["frozen_baseline"] == FROZEN_BASELINE
    assert prereg["frozen_headline"] == FROZEN_HEADLINE
    assert PREREG_SHA256 in text
    assert str(FROZEN_BASELINE) in text
    assert str(FROZEN_HEADLINE) in text


def test_no_promotion_and_no_scoreboard_attempt_is_spent() -> None:
    text = _read(REPORT_PATH)
    summary = _summary()
    assert summary["promotes_no_reading"] is True
    assert summary["main_scoreboard_untouched"] is True
    assert summary["scoreboard_attempts_delta"] == 0
    assert summary["produces_deployable_model"] is False
    assert SCOREBOARD_ATTEMPTS_LITERAL in text
    assert "not a promotion arm" in text
    assert "never averaged" in text


def test_section_fragment_format() -> None:
    lines = _read(SECTION_PATH).splitlines()
    assert lines[0].startswith(SECTION_FIRST_LINE_PREFIX)
    assert "Week 19 D3" in lines[0]
    assert lines[1] == "|"
    assert lines[-1] == "|"
    assert "**数字自检**" in "\n".join(lines)


def test_section_fragment_repeats_the_pinned_tokens() -> None:
    text = _read(SECTION_PATH)
    for token in (
        "234",
        "111",
        "76",
        "31",
        VERDICT_Q1,
        VERDICT_Q2,
        VERDICT_Q3,
        "0.0",
        "a_donor_mae_below_onsager",
        "e_donor_mae_below_structured_offset",
        SCOREBOARD_ATTEMPTS_LITERAL,
    ):
        assert token in text, f"section fragment is missing the pinned token: {token}"

