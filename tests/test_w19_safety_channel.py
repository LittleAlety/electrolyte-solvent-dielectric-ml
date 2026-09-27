"""Literal-pin tests for the Week 19 W19-6 safety-channel registration (N14)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "reports" / "w19_safety_channel.md"
SECTION = REPO_ROOT / "reports" / "_w19_section_d7.md"
REGISTRY = REPO_ROOT / "probes" / "w19_safety_channel_registry.json"
THIS_TEST = Path(__file__).resolve()

EXPECTED_SECTION_TITLE = (
    "## 28.53 Week 19 D7 安全通道登记（N14）：闪点 / 沸点 / 熔点 / 安全窗口 登记为第四通道，"
    "覆盖门 0.30 与 DN 0.0% 前例在册，只登记不执行（2026-09-28）"
)

REQUIRED_TOP_LEVEL_KEYS = [
    "schema_version",
    "prereg_status",
    "produces_reading",
    "promotes_no_reading",
    "main_scoreboard_untouched",
    "scoreboard_attempts_delta",
    "reaxys_numeric_red_line",
    "channels",
]

REQUIRED_CHANNEL_FIELDS = [
    "channel",
    "property",
    "proposed_tool",
    "tool_reference",
    "status",
    "would_produce_reading",
    "blocking_conditions",
    "licence_note",
]

REQUIRED_CHANNELS = [
    "safety_flash_point",
    "safety_boiling_point",
    "safety_melting_point",
    "safety_window",
]

REPORT_TOKENS = [
    "ADMETlab",
    "Marrero-Gani",
    "GC-ML",
    "au5c01628.pdf",
    "10.1021/jacsau.5c01628",
    "registered_not_executed",
    "not_verifiable_in_repo",
    "channel_does_not_enter_the_feature_table",
    "0.3",
    "0.0%",
    "1043",
    "0.15",
    "0.17477197208762",
    "0.08506361044387624",
    "0.08908094784092072",
    "0.19050925839013938",
    "0.13855083976437643",
    "0.4091179943351143",
    "0.4766400383507876",
    "0.5861142332208197",
    "0.349",
    "457",
    "97",
    "276",
    "2029",
    "4151",
    "976",
    "3582",
    "957",
    "11",
]

REPORT_SECTIONS = [
    "## 0. 本件存在的原因",
    "## 1. 为什么只登记、不执行",
    "## 2. 登记了什么",
    "## 3. 执行前必须补齐的前置条件",
    "## 4. 覆盖门（本件不测，只登记纪律）",
    "## 5. §W19-8 不做清单（逐条重述）",
    "## 6. 记分牌纪律（本件的自我澄清）",
    "## 7. 数字出处与不可核登记",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _registry() -> dict:
    return json.loads(_text(REGISTRY))


def test_all_four_files_exist() -> None:
    for path in (REPORT, SECTION, REGISTRY, THIS_TEST):
        assert path.is_file(), f"missing file: {path}"


def test_utf8_no_bom_and_lf_only() -> None:
    for path in (REPORT, SECTION, REGISTRY):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        assert b"\r\n" not in raw, f"CRLF in {path.name}"


def test_registry_top_level_keys_and_flags() -> None:
    data = _registry()
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in data]
    assert not missing, f"missing registry keys: {missing}"
    assert data["prereg_status"] == "registered_not_executed"
    assert data["produces_reading"] is False
    assert data["promotes_no_reading"] is True
    assert data["main_scoreboard_untouched"] is True
    assert data["scoreboard_attempts_delta"] == 0
    assert data["scoreboard_attempts_cumulative"] == 11
    assert data["shot_number_taken"] is None


def test_every_channel_is_registered_only() -> None:
    data = _registry()
    channels = data["channels"]
    assert [c["channel"] for c in channels] == REQUIRED_CHANNELS
    for channel in channels:
        missing = [f for f in REQUIRED_CHANNEL_FIELDS if f not in channel]
        assert not missing, f"{channel.get('channel')} missing fields: {missing}"
        assert channel["status"] == "registered_not_executed"
        assert channel["would_produce_reading"] is False
        assert channel["blocking_conditions"], f"{channel['channel']} has no blockers"
        assert channel["licence_note"]


def test_every_channel_names_a_pdf_in_the_literature_folder() -> None:
    for channel in _registry()["channels"]:
        reference = channel["tool_reference"]
        assert "au5c01628.pdf" in reference, channel["channel"]
        assert "Week19立项计划_文献驱动三线.md" in reference, channel["channel"]


def test_report_pins_the_registered_channels_verbatim() -> None:
    text = _text(REPORT)
    for name in REQUIRED_CHANNELS:
        assert f"`{name}`" in text, f"report does not name {name}"


def test_report_sections_present() -> None:
    text = _text(REPORT)
    missing = [section for section in REPORT_SECTIONS if section not in text]
    assert not missing, f"missing report sections: {missing}"


def test_report_required_tokens_are_pinned_verbatim() -> None:
    text = _text(REPORT)
    missing = [token for token in REPORT_TOKENS if token not in text]
    assert not missing, f"missing pinned tokens: {missing}"


def test_report_states_the_isolation_rule_explicitly() -> None:
    text = _text(REPORT)
    assert "安全窗口数字一旦引入，必须走独立预注册，且不得与 ε / η 主记分牌混比。" in text


def test_section_first_line_is_the_exact_title() -> None:
    lines = _text(SECTION).split("\n")
    assert lines[0] == EXPECTED_SECTION_TITLE


def test_section_second_and_last_lines_are_pipe() -> None:
    lines = _text(SECTION).rstrip("\n").split("\n")
    assert lines[1] == "|"
    assert lines[-1] == "|"


def test_section_carries_the_same_pinned_tokens() -> None:
    text = _text(SECTION)
    for token in ("0.3", "0.0%", "1043", "11", "28.53", "registered_not_executed"):
        assert token in text, f"section missing token: {token}"


def test_section_does_not_claim_a_reading() -> None:
    text = _text(SECTION)
    assert "produces_reading = false" in text
    assert "scoreboard_attempts_delta = 0" in text
