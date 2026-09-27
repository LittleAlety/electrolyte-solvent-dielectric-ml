"""Literal-pin test for the Week 19 W19-1 orbital-migration gate ruling report and its section fragment."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "reports" / "w19_orbital_migration_gate.md"
SECTION = REPO_ROOT / "reports" / "_w19_section_d8.md"

REPORT_TITLE_PREFIX = "# W19-1 "

EXPECTED_SECTION_TITLE = (
    "## 28.54 Week 19 W19-1 步骤 2 轨道迁移决策门裁定："
    "Batt-P30K 不升为 HOMO-LUMO 通道主源、仅作第二参考层，THEMol 主源不变（2026-09-28）"
)

REQUIRED_TOKENS = [
    "0.8223",
    "0.3475",
    "0.35",
    "0.80",
    "0.0025",
    "0.4663",
    "0.1984",
    "0.0550",
    "0.1921",
    "0.7445",
    "78",
    "246",
    "49",
    "29",
    "11",
    "28.54",
]

REQUIRED_PHRASES = [
    "no_reference_orbital",
    "reference_only",
    "usable",
    "第二参考层",
    "不升为主描述符源",
    "cross_level",
    "promoted = false",
    "累计仍 **11** 次",
    "0.4091179943351143",
    "0.4766400383507876",
    "**78** 键",
    "**246** 行",
    "**49** 键",
    "**29** 个命中键",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_no_bom_no_crlf(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} must be UTF-8 without BOM"
    assert b"\r\n" not in raw, f"{path.name} must use LF line endings"


def test_report_exists_and_has_h1_title() -> None:
    assert REPORT.is_file(), f"missing report: {REPORT}"
    assert _read(REPORT).split("\n")[0].startswith(REPORT_TITLE_PREFIX)


def test_report_has_number_selfcheck_section() -> None:
    assert "## 数字自检" in _read(REPORT)


def test_report_is_clean_utf8_lf() -> None:
    _assert_no_bom_no_crlf(REPORT)


def test_section_exists() -> None:
    assert SECTION.is_file(), f"missing section file: {SECTION}"


def test_section_is_clean_utf8_lf() -> None:
    _assert_no_bom_no_crlf(SECTION)


def test_section_first_line_is_the_exact_title() -> None:
    assert _read(SECTION).split("\n")[0] == EXPECTED_SECTION_TITLE


def test_section_second_and_last_lines_are_pipe() -> None:
    lines = _read(SECTION).rstrip("\n").split("\n")
    assert lines[1] == "|"
    assert lines[-1] == "|"


def test_report_required_tokens_are_pinned_verbatim() -> None:
    text = _read(REPORT)
    missing = [token for token in REQUIRED_TOKENS if token not in text]
    assert not missing, f"missing pinned tokens: {missing}"


def test_section_required_tokens_are_pinned_verbatim() -> None:
    text = _read(SECTION)
    missing = [token for token in REQUIRED_TOKENS if token not in text]
    assert not missing, f"missing pinned tokens: {missing}"


def test_report_ruling_phrases_present() -> None:
    text = _read(REPORT)
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    assert not missing, f"missing ruling phrases: {missing}"


def test_section_ruling_phrases_present() -> None:
    text = _read(SECTION)
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    assert not missing, f"missing ruling phrases: {missing}"

