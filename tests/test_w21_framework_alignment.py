"""Guards for the Week 21 Tier 1 alignment tables.

The framework原文 is copied byte for byte and pinned; the three derived tables
must stay reproducible and must keep telling the truth about what the repo does
*not* have (no Li-complex layer, no conformer counts).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes/w21_framework_alignment_summary.json"
FRAMEWORK_COPY = ROOT / "docs/framework/ranking-electrolyte-materials-v2.md"
FEATURE_COST = ROOT / "probes/artifacts/w21_feature_cost_map.csv"
CHEM_SPACE = ROOT / "data/processed/w21_chemical_space_metadata.csv"
GATES = ROOT / "probes/artifacts/w21_stage_gate_verdicts.csv"
REPORT = ROOT / "reports/w21_framework_alignment.md"
VERDICTS = {"成立", "部分成立", "不成立", "未执行"}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def test_framework_copy_is_byte_identical_and_pinned() -> None:
    summary = _json(SUMMARY)
    assert FRAMEWORK_COPY.is_file()
    payload = FRAMEWORK_COPY.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == summary["framework"]["sha256"]
    assert summary["framework"]["byte_identical"] is True
    assert summary["framework"]["bytes"] == len(payload)
    assert summary["framework"]["sha256"].startswith("e55c1b07")
    sha_sidecar = (ROOT / "docs/framework/ranking-electrolyte-materials-v2.sha256").read_text(encoding="utf-8")
    assert summary["framework"]["sha256"] in sha_sidecar


def test_feature_cost_map_carries_every_level_and_the_empty_x2_layer() -> None:
    header, rows = _rows(FEATURE_COST)
    assert header == ["block", "feature", "cost_level", "available_when", "evidence_path", "note"]
    levels = {row["cost_level"] for row in rows}
    assert {"X0", "X1", "X2", "target", "reference"} <= levels
    assert not FEATURE_COST.read_bytes().startswith(b"\xef\xbb\xbf")
    assert bytes([13, 10]) not in FEATURE_COST.read_bytes()
    x2 = [row for row in rows if row["cost_level"] == "X2"]
    assert len(x2) == 1
    assert x2[0]["evidence_path"] == ""
    summary = _json(SUMMARY)
    assert summary["feature_cost"]["rows"] == len(rows)


def test_chemical_space_metadata_is_multi_axis_and_refuses_to_invent() -> None:
    header, rows = _rows(CHEM_SPACE)
    for column in (
        "structural_family",
        "functionalization_tags",
        "use_role",
        "donor_atoms",
        "formal_charge",
        "rotatable_bonds",
        "conformer_count",
        "Li_motif_count",
        "state_identity_status",
        "reactivity_status",
        "qc_status",
    ):
        assert column in header, column
    assert len(rows) == 246
    assert len({row["molecule_id"] for row in rows}) == 246
    assert bytes([13, 10]) not in CHEM_SPACE.read_bytes()
    for column in ("conformer_count", "Li_motif_count", "state_identity_status", "reactivity_status"):
        assert {row[column] for row in rows} == {"not_available_in_repo"}, column
    roles = {row["use_role"] for row in rows}
    assert roles == {"state_of_the_art_solvent", "background_candidate"}
    assert sum(1 for row in rows if row["use_role"] == "state_of_the_art_solvent") >= 12
    families = {row["structural_family"] for row in rows}
    for family in ("cyclic_carbonate", "linear_carbonate", "ester", "ether", "nitrile", "sulfone", "water"):
        assert family in families, family
    assert len(families) >= 12


def test_stage_gate_verdicts_are_three_state_and_gate_one_is_not_closed() -> None:
    header, rows = _rows(GATES)
    assert header == ["gate_id", "item", "verdict", "detail", "evidence_path"]
    assert {row["verdict"] for row in rows} <= VERDICTS
    ids = {row["gate_id"] for row in rows}
    assert {"S0-1", "S0-5", "S0-6", "S0-7", "S1-1", "S1-6"} <= ids
    assert any(row["verdict"] == "未执行" for row in rows)
    summary = _json(SUMMARY)
    assert "NOT CLOSED" in summary["framework_red_lines"]["stage1_gate"]
    assert summary["models_fitted"] == 0
    assert summary["network_calls"] == 0
    assert summary["writes_any_pool"] is False


def test_the_alignment_report_says_it_produced_no_reading() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for needle in ("不拟合任何模型", "X2 是空的", "Stage 0 / Stage 1 判词", "未执行"):
        assert needle in text, needle