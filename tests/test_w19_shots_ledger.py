"""Literal-pin tests for the Week 19 W19-9 shots ledger (§W19-9)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / "probes" / "w19_shots_ledger.json"
REPORT = REPO_ROOT / "reports" / "w19_shots_ledger.md"
SECTION = REPO_ROOT / "reports" / "_w19_section_d9.md"
THIS_TEST = Path(__file__).resolve()

REQUIRED_TOP_LEVEL_KEYS = [
    "schema_version",
    "prereg_status",
    "ruling",
    "ruling_basis",
    "shots",
    "next_shot_number",
    "main_scoreboard_untouched",
    "scoreboard_attempts_delta",
    "cumulative_main_scoreboard_attempts",
    "reaxys_numeric_red_line",
    "author_confirmation_required",
]

REQUIRED_SHOT_FIELDS = [
    "shot",
    "claimed_by",
    "asset_path",
    "asset_present_before_this_week",
    "produces_reading",
    "status",
    "evidence",
]

REQUIRED_SHOTS = [19, 20, 21]

REPORT_TOKENS = [
    "shot 19",
    "shot 20",
    "shot 21",
    "n = 111",
    'decision.decision = "go"',
    "2026-09-25T05:55:35.227743+00:00",
    "a6ed806",
    "4208fe8adf4ed6eee305b1a83ad322aada7f5bea01f538a57e45462a86899838",
    "locked_pending_author_confirmation",
    "next_shot_number = 22",
    "effective_after_author_confirmation = true",
    "no_retroactive_edit = true",
    "produces_reading = false",
    "复核不占号",
    "不得事后改",
    "0.4091179943351143",
    "0.4766400383507876",
    "11",
]

SECTION_TOKENS = [
    "n = 111",
    "0.4091179943351143",
    "0.4766400383507876",
    "next_shot_number = 22",
    "2026-09-25T05:55:35.227743+00:00",
    "locked_pending_author_confirmation",
    "复核不占号",
    "不得事后改",
    "11",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ledger() -> dict:
    return json.loads(_text(LEDGER))


def test_all_four_files_exist() -> None:
    for path in (LEDGER, REPORT, SECTION, THIS_TEST):
        assert path.is_file(), f"missing file: {path}"


def test_utf8_no_bom_and_lf_only() -> None:
    for path in (LEDGER, REPORT, SECTION, THIS_TEST):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        assert b"\r\n" not in raw, f"CRLF in {path.name}"


def test_top_level_keys_and_scoreboard_flags() -> None:
    data = _ledger()
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in data]
    assert not missing, f"missing ledger keys: {missing}"
    assert data["main_scoreboard_untouched"] is True
    assert data["scoreboard_attempts_delta"] == 0
    assert data["cumulative_main_scoreboard_attempts"] == 11
    assert data["author_confirmation_required"] is True
    assert data["scoreboard_attempts_delta"] == 0


def test_prereg_status_is_self_consistent_literal() -> None:
    data = _ledger()
    assert data["prereg_status"] in {"locked_before_run", "locked_pending_author_confirmation"}
    note = data.get("prereg_status_note", "")
    assert "locked_before_run" in note, "the choice must explain why the other literal is not claimed"
    assert data["no_retroactive_edit"] is True
    assert data["effective_after_author_confirmation"] is True


def test_shots_19_20_21_each_carry_every_field() -> None:
    shots = _ledger()["shots"]
    by_number = {row["shot"]: row for row in shots}
    for number in REQUIRED_SHOTS:
        assert number in by_number, f"shot {number} missing"
        row = by_number[number]
        missing = [field for field in REQUIRED_SHOT_FIELDS if field not in row]
        assert not missing, f"shot {number} missing fields: {missing}"
        assert row["evidence"], f"shot {number} has no evidence"


def test_shots_19_and_20_are_consumed_and_21_is_this_weeks_phase0() -> None:
    by_number = {row["shot"]: row for row in _ledger()["shots"]}
    for number in (19, 20):
        assert by_number[number]["asset_present_before_this_week"] is True
        assert by_number[number]["status"] == "consumed"
    assert by_number[21]["asset_present_before_this_week"] is False
    assert by_number[21]["produces_reading"] is False
    assert by_number[21]["status"].startswith("taken_this_week")


def test_ruling_and_next_shot_number_are_self_consistent() -> None:
    data = _ledger()
    assert "已用" in data["ruling"]
    assert data["next_shot_number"] == 22
    assert data["ruling_basis"], "ruling must carry a basis list"


def test_every_this_week_lane_is_not_promoted() -> None:
    lanes = _ledger()["this_week_lanes"]
    assert len(lanes) == 9, f"expected 9 W19 work items, got {len(lanes)}"
    for lane in lanes:
        assert lane["promoted"] is False, lane["lane"]
        assert lane["scored_on_main_scoreboard"] is False, lane["lane"]


def test_report_pins_required_tokens() -> None:
    text = _text(REPORT)
    missing = [token for token in REPORT_TOKENS if token not in text]
    assert not missing, f"missing pinned report tokens: {missing}"


def test_report_states_the_two_branches_and_their_convergence() -> None:
    text = _text(REPORT)
    assert "分支 A" in text
    assert "分支 B" in text
    assert "分支稳健性" in text


def test_report_declares_this_weeks_zero_attempts() -> None:
    text = _text(REPORT)
    assert "scoreboard_attempts_delta = 0" in text
    assert "累计主记分牌尝试 **11** 次" in text


def test_section_first_line_names_28_55() -> None:
    lines = _text(SECTION).split("\n")
    assert lines[0].startswith("## 28.55 Week 19 D9 shots 记账台账"), lines[0]


def test_section_second_and_last_lines_are_pipe() -> None:
    lines = _text(SECTION).rstrip("\n").split("\n")
    assert lines[1] == "|"
    assert lines[-1] == "|"


def test_section_carries_the_same_pinned_tokens() -> None:
    text = _text(SECTION)
    missing = [token for token in SECTION_TOKENS if token not in text]
    assert not missing, f"missing pinned section tokens: {missing}"


def test_section_has_no_unicode_escapes_left() -> None:
    text = _text(SECTION)
    assert "\\u" not in text, "section must carry real CJK, not \\uXXXX escapes"
