"""B05 boundary-report guards.

The boundary report is the project's public statement of what the descriptors can
and cannot do. Its failure mode is over-claiming: turning "no detectable signal in
22 molecules" into "electronic descriptors are useless". These tests pin the
distinction.

Guarded:
  1. the report exists and is generated (not hand-written)
  2. required experiments (E1/E4/E6) are complete
  3. "cannot claim" list is present and substantial
  4. supported conclusions are derived from the manifests, not asserted
  5. absent feature tiers are recorded
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B05 = REPO_ROOT / "outputs" / "b05"

pytestmark = pytest.mark.skipif(
    not (B05 / "b05_gate_status.json").is_file(),
    reason="B05 boundary report not built yet",
)


def _gate() -> dict:
    return json.loads((B05 / "b05_gate_status.json").read_text(encoding="utf-8"))


def test_required_experiments_complete() -> None:
    g = _gate()
    assert g["required_experiments_complete"] is True
    for k in ("E1", "E4", "E6"):
        assert g["experiments"][k]["required"] is True
        assert g["experiments"][k]["done"] is True, f"{k} not done"
    assert g["gate_open"] is True


def test_conditional_experiments_are_marked_not_run() -> None:
    """E2/E3/E5 must be explicitly NOT_RUN, not silently omitted."""
    g = _gate()
    for k in ("E2", "E3", "E5"):
        assert g["experiments"][k]["required"] is False
        assert "NOT_RUN" in g["experiments"][k]["status"]


def test_report_states_what_cannot_be_claimed() -> None:
    g = _gate()
    assert len(g["cannot_claim"]) >= 5, (
        "the cannot-claim list is too short to be meaningful")
    joined = " ".join(g["cannot_claim"])
    assert "普遍" in joined, "must refuse the 'universally useless' over-claim"
    assert "外推" in joined or "extrapolat" in joined.lower()
    assert "来源聚类" in joined

    report = (B05 / "model_boundary_report.md").read_text(encoding="utf-8")
    assert "证据**不支持**的结论" in report
    assert "不能宣称" in report


def test_supported_conclusions_come_from_manifests() -> None:
    """Each supported conclusion must trace to an experiment manifest."""
    g = _gate()
    assert len(g["supported_conclusions"]) >= 3
    e1 = json.loads((B05 / "E1_structure_vs_electronic" / "e1_manifest.json")
                    .read_text(encoding="utf-8"))
    e4 = json.loads((B05 / "E4_domain_generalization" / "e4_manifest.json")
                    .read_text(encoding="utf-8"))
    e6 = json.loads((B05 / "E6_screening_decisions" / "e6_manifest.json")
                    .read_text(encoding="utf-8"))

    joined = " ".join(g["supported_conclusions"])
    # The baseline claim must reflect E1's actual numbers.
    if e1["constant_baseline"]["n_models_beating_baseline"] == 0:
        assert "不能**优于" in joined or "不能" in joined
    # The OOD claim must reflect E4.
    if e4["counts"]["n_families_beating_baseline"] == 0:
        assert "家族" in joined
    # The screening claim must reflect E6's p-value.
    if e6["metrics"]["p_model_beats_random"] > 0.05:
        assert "随机" in joined


def test_absent_feature_tiers_are_recorded() -> None:
    inp = json.loads((B05 / "model_input_manifest.json").read_text(encoding="utf-8"))
    absent = {a["tier"] for a in inp["feature_tiers_absent"]}
    assert "X2" in absent and "X3" in absent, (
        "X2/X3 must be registered as absent")
    assert len(inp["feature_tiers_present"]) >= 2

    report = (B05 / "model_boundary_report.md").read_text(encoding="utf-8")
    assert "完整描述符体系" in report, (
        "report must refuse the 'complete descriptor set' claim")


def test_feature_registry_covers_the_pool() -> None:
    import csv
    with (B05 / "feature_registry_v2.csv").open(encoding="utf-8-sig",
                                                newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for r in rows:
        assert float(r["coverage_pct"]) >= 100.0, (
            f"{r['feature']} only covers {r['coverage_pct']}% of the pool")
        assert r["tier"] in ("X0", "X1", "X2", "X3")
        assert r["used_in"], "feature must declare which experiment uses it"


def test_hypothesis_mapping_is_present() -> None:
    report = (B05 / "model_boundary_report.md").read_text(encoding="utf-8")
    for h in ("H1", "H2", "H3"):
        assert h in report, f"{h} not addressed in the boundary report"
