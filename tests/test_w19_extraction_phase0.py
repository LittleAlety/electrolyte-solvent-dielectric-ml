"""Literal-pin guards for the Week 19 D4 extraction Phase-0 design artefact.

The Week 19 plan asks for a pre-registration that locks the extraction template,
the thresholds and the red lines *before* any extraction runs (plan sections
W19-2 and W19-9).  Nothing here executes an extraction, touches the network or
fits a model: these tests only compare the two committed design files against the
values the plan fixes, and pin their bytes so an edit cannot pass unnoticed.

The sha256 pins are the point.  Section W19-9 carries the lever-8 precedent that a
locked pre-registration is never amended in place, so the digest is the mechanism
that turns that rule into something a machine can check.  If the report or the
pre-registration is ever corrected, the pins below must move with it in the same
commit, which is exactly the audit trail the plan asks for.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = REPOSITORY_ROOT / "reports" / "w19_extraction_phase0.md"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_extraction_phase0_prereg.json"

REPORT_SHA256 = "10c7913cefa2f431827d4582250aa2f805c096dd32dce24330c1cdc0230bb25f"
PREREG_SHA256 = "5f83efa632cf7de79c017c938dfb6c63102ae13cbacb0b3f50eeb541d74ccb11"

# Proposed thresholds from the plan.  Every one of them is pending the author,
# which is why `thresholds_pending_author_confirmation` must stay true.
REGISTERED_THRESHOLDS = {
    "numeric_field_precision_min": 0.95,
    "numeric_field_recall_min": 0.80,
    "compound_disambiguation_precision_min": 0.90,
    "doi_plus_locator_completeness_min": 1.00,
}

RED_LINE_KEYWORDS = ("restricted_crosscheck_only", "永不入", "批量爬虫", "无定位不入库")

REQUIRED_TEMPLATE_FIELDS = (
    "compound_name",
    "smiles",
    "inchikey",
    "disambiguation_confidence",
    "property_value",
    "unit",
    "temperature_K",
    "method",
    "source_doi",
    "locator_table_figure",
    "extraction_confidence",
)

PENDING_LABEL = "待作者确认，不得由本稿单方生效"


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def _report() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


def test_the_two_design_files_exist() -> None:
    assert REPORT_PATH.is_file(), REPORT_PATH
    assert PREREG_PATH.is_file(), PREREG_PATH


def test_both_files_are_utf8_lf_without_bom() -> None:
    for path in (REPORT_PATH, PREREG_PATH):
        payload = _read_bytes(path)
        assert not payload.startswith(b"\xef\xbb\xbf"), path.name
        assert b"\r\n" not in payload, path.name
        payload.decode("utf-8")


def test_sha256_pins() -> None:
    assert _sha256(_read_bytes(REPORT_PATH)) == REPORT_SHA256
    assert _sha256(_read_bytes(PREREG_PATH)) == PREREG_SHA256


def test_prereg_is_locked_before_run_and_runs_nothing_this_week() -> None:
    prereg = _prereg()
    assert prereg["status"] == "locked_before_run"
    assert prereg["executes_extraction_this_week"] is False
    assert prereg["produces_reading"] is False
    assert prereg["deliverable"] == "D4"


def test_thresholds_are_pinned_and_flagged_as_pending() -> None:
    prereg = _prereg()
    assert prereg["thresholds_pending_author_confirmation"] is True
    thresholds = prereg["thresholds"]
    for key, value in REGISTERED_THRESHOLDS.items():
        assert thresholds[key] == value, key
    assert thresholds["status"] == "proposed_pending_author_confirmation"


def test_report_states_the_same_thresholds_by_literal() -> None:
    text = _report()
    for literal in ("≥ 0.95", "≥ 0.80", "≥ 0.90", "100%"):
        assert literal in text, literal
    assert PENDING_LABEL in text
    assert PENDING_LABEL in _prereg()["design_only_language"]


def test_prereg_records_every_template_field_with_its_contract() -> None:
    fields = _prereg()["template_v0"]["fields"]
    names = [field["name"] for field in fields]
    for name in REQUIRED_TEMPLATE_FIELDS:
        assert name in names, name
    for field in fields:
        for key in ("name", "type", "required", "missing_behaviour", "validation"):
            assert key in field, (field.get("name"), key)


def test_red_lines_appear_in_both_files() -> None:
    report = _report()
    prereg_text = json.dumps(_prereg(), ensure_ascii=False)
    for keyword in RED_LINE_KEYWORDS:
        assert keyword in report, keyword
        assert keyword in prereg_text, keyword


def test_epsilon_template_is_deferred_to_the_w18_7_reading() -> None:
    priority = _prereg()["channel_priority"]
    assert priority["first"] == ["eta", "homo_lumo", "redox"]
    assert priority["epsilon_template_activation"] == "deferred_to_w18_7"
    branch = priority["epsilon_branch"]
    assert "if_w18_7_freezes_the_lane" in branch
    assert "if_w18_7_unfreezes_or_replaces_the_lane" in branch


def test_shot_accounting_is_a_recommendation_only() -> None:
    accounting = _prereg()["shot_accounting"]
    assert accounting["status"] == "proposed_pending_author_confirmation"
    assert accounting["recommended_shot"] == 21
    assert accounting["fallback_if_shot_19_20_counted"] == 22
    assert accounting["this_file_consumes_a_shot"] is False


def test_no_reading_is_promoted_by_this_design_artefact() -> None:
    rule = _prereg()["promotion_rule"]
    assert "0.4766400383507876" in rule
    assert "0.4091179943351143" in rule
