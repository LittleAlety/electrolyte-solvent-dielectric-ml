"""Literal-pin test for the Week 19 W19-7 channel-transfer section (§28.51)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTION = REPO_ROOT / "reports" / "w19_channel_transfer.md"

EXPECTED_TITLE = (
    "## 28.51 Week 19 通道转移预案：ε 表示层封顶后 η ⇒ HOMO-LUMO ⇒ 氧化还原 三级转移，"
    "触发成立、主记分牌不动（2026-09-28）"
)

REQUIRED_TOKENS = [
    "0.5998203128630835",
    "0.00018",
    "0.17477197208762",
    "0.15",
    "0.15686276760094522",
    "0.006863",
    "0.08506361044387624",
    "0.08908094784092072",
    "0.19050925839013938",
    "0.13855083976437643",
    "0.20",
    "77",
    "246",
    "28.51",
    "11",
]


def _read() -> str:
    return SECTION.read_text(encoding="utf-8")


def test_section_file_exists() -> None:
    assert SECTION.is_file(), f"missing section file: {SECTION}"


def test_no_bom_and_no_crlf() -> None:
    raw = SECTION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "section must be UTF-8 without BOM"
    assert b"\r\n" not in raw, "section must use LF line endings"


def test_first_line_is_the_exact_title() -> None:
    lines = _read().split("\n")
    assert lines[0] == EXPECTED_TITLE


def test_second_and_last_lines_are_pipe() -> None:
    lines = _read().rstrip("\n").split("\n")
    assert lines[1] == "|"
    assert lines[-1] == "|"


def test_required_numeric_tokens_are_pinned_verbatim() -> None:
    text = _read()
    missing = [token for token in REQUIRED_TOKENS if token not in text]
    assert not missing, f"missing pinned tokens: {missing}"

