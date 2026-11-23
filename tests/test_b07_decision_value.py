"""B07 guards: the decision-value verdict must follow the evidence.

B07's failure mode is a report that lists the right audit points and then reaches a
comfortable conclusion anyway. These tests pin the link between the numbers and the
verdict.

Guarded:
  1. all eight B07 outputs exist
  2. the verdict is derived from the artifacts, not asserted
  3. "MAE improvement != screening value" is carried through, not softened
  4. a leakage result showing NO gap is not spun as good news
  5. source-cluster claim is refused when clusters are too few
  6. linked artifacts match their sources (no drift)
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B07 = REPO_ROOT / "outputs" / "b07"
B05 = REPO_ROOT / "outputs" / "b05"

REQUIRED = ["random_split_results.csv", "leave_one_family_out.csv",
            "source_ood_results.csv", "similarity_ood_results.csv",
            "applicability_domain.csv", "topk_regret.csv",
            "screening_reliability.csv", "decision_value_report.md"]

pytestmark = pytest.mark.skipif(
    not (B07 / "b07_gate_status.json").is_file(),
    reason="B07 not assembled yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _gate() -> dict:
    return json.loads((B07 / "b07_gate_status.json").read_text(encoding="utf-8"))


def test_all_eight_outputs_exist() -> None:
    g = _gate()
    assert g["deliverables_complete"] is True
    for f in REQUIRED:
        assert (B07 / f).is_file(), f"missing {f}"
        assert g["required_outputs"][f] is True


def test_verdict_is_derived_from_artifacts() -> None:
    """Every blocking reason must trace to a number in a manifest."""
    g = _gate()
    assert g["usable_for_screening"] is False
    assert len(g["blocking_reasons"]) >= 3, (
        "a negative verdict needs several independent reasons")

    e1 = json.loads((B05 / "E1_structure_vs_electronic" / "e1_manifest.json")
                    .read_text(encoding="utf-8"))
    e6 = json.loads((B05 / "E6_screening_decisions" / "e6_manifest.json")
                    .read_text(encoding="utf-8"))

    joined = " ".join(g["blocking_reasons"])
    # The regression baseline reason must cite E1's numbers.
    if e1["constant_baseline"]["n_models_beating_baseline"] == 0:
        assert "基线" in joined
    # The screening reason must cite E6's p-value.
    if e6["metrics"]["p_model_beats_random"] > 0.05:
        assert "随机" in joined


def test_mae_vs_screening_decoupling_is_carried() -> None:
    """PLAN B B07 point 5: MAE improvement is not screening value.

    E6 shows regret falls as noise grows. After the intercept fix the mechanism is
    a LOCAL RANK INVERSION, not global anti-correlation -- the report must carry
    whichever verdict E6 actually reached.
    """
    report = (B07 / "decision_value_report.md").read_text(encoding="utf-8")
    assert "MAE 改善 ≠ 筛选收益" in report
    e6 = json.loads((B05 / "E6_screening_decisions" / "e6_manifest.json")
                    .read_text(encoding="utf-8"))
    ladder = e6["noise_ladder"]
    if ladder[-1]["mean_regret"] < ladder[0]["mean_regret"] - 0.5:
        assert ("regret 下降" in report
                or "局部排序倒置" in report
                or "脱钩" in report), (
            "the noise-ladder reversal must be stated, not softened")


def test_no_gap_leakage_result_is_not_spun_as_good() -> None:
    """If random and grouped splits score the same, that is not good news."""
    man = json.loads((B07 / "random_split_manifest.json").read_text(encoding="utf-8"))
    report = (B07 / "decision_value_report.md").read_text(encoding="utf-8")
    if not man["leakage"]["leakage_demonstrated"]:
        assert "泄漏没有被演示出来" in report or "问题不在划分方式" in report
        # The key inference: stricter splitting cannot HELP.
        assert ("只会让数字更差" in report
                or "只会更差" in report
                or "不能声称改进" in report), (
            "must state that stricter splitting cannot improve the number")


def test_source_cluster_claim_refused() -> None:
    man = json.loads((B07 / "random_split_manifest.json").read_text(encoding="utf-8"))
    sc = man["source_clusters"]
    if not sc["claim_permitted"]:
        assert sc["claim_blockers"], "refusal must state why"
        g = _gate()
        assert any("来源" in r for r in g["blocking_reasons"]), (
            "the gate must carry the source-cluster refusal")


def test_audit_points_are_all_recorded() -> None:
    g = _gate()
    ap = g["audit_points"]
    assert len(ap) == 8, f"expected 8 audit points, got {len(ap)}"
    # Point 2 must always hold: no molecule spans train and test.
    assert ap["2_no_molecule_spans_train_test"] is True
    # Point 3 must be honestly refused here.
    assert ap["3_source_cluster_claim_permitted"] is False


def test_linked_artifacts_match_sources() -> None:
    """Copies must not drift from the B05 originals."""
    g = _gate()
    for link in g["linked_artifacts"]:
        dst = B07 / link["b07_output"]
        src = REPO_ROOT / link["source"]
        assert dst.is_file() and src.is_file()
        h_dst = hashlib.sha256(dst.read_bytes()).hexdigest()
        h_src = hashlib.sha256(src.read_bytes()).hexdigest()
        assert h_dst == h_src, (
            f"{link['b07_output']} drifted from {link['source']}")


def test_random_split_covers_three_schemes() -> None:
    rows = _load(B07 / "random_split_results.csv")
    schemes = {r["scheme"] for r in rows}
    assert any(s.startswith("random_") for s in schemes), "no random split"
    assert "leave_one_molecule_out" in schemes
    assert "leave_one_family_out" in schemes


def test_no_molecule_overlap_anywhere() -> None:
    rows = _load(B07 / "split_leakage_audit.csv")
    for r in rows:
        assert int(r["molecule_overlap"]) == 0, (
            f"{r['scheme']} has molecule overlap")
