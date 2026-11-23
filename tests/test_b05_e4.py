"""B05-E4 guards: OOD analysis must distinguish "far away" from "unresolvable".

The dangerous misreading of E4 is to blame large errors on being out of domain,
because that implies "collect more data and it will work". The identical-fingerprint
test exists to separate those cases, and these tests pin it.

Guarded:
  1. no statistic is emitted for a held-out group too small to support it
  2. the identical-fingerprint analysis exists and is reported
  3. applicability-domain coverage is reported as a number
  4. source-OOD carries the independence caveat (sources are not independent)
  5. leave-one-family-out is real grouping, not a random split
  6. every held-out molecule appears exactly once in the distance analysis
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E4 = REPO_ROOT / "outputs" / "b05" / "E4_domain_generalization"

pytestmark = pytest.mark.skipif(
    not (E4 / "e4_manifest.json").is_file(),
    reason="E4 not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_result_is_labelled_exploratory() -> None:
    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    assert man["status"] == "EXPLORATORY_NOT_CONFIRMATORY"
    report = (E4 / "e4_report.md").read_text(encoding="utf-8")
    assert "探索性" in report


def test_small_holdout_groups_report_insufficient_power() -> None:
    """An n=1 test set must not produce an R-squared or MAE."""
    rows = _load(E4 / "leave_one_family_out.csv")
    min_test_n = json.loads(
        (E4 / "e4_manifest.json").read_text(encoding="utf-8"))["min_test_n_rule"]
    for r in rows:
        if int(r["test_n"]) < int(min_test_n):
            assert r["status"] == "insufficient_power", (
                f"{r['family']}: test_n={r['test_n']} but status={r['status']}")
            assert r["mae"] == "", (
                f"{r['family']}: emitted MAE={r['mae']} for an underpowered group")


def test_identical_fingerprint_analysis_exists() -> None:
    """The test that separates 'extrapolation failure' from 'descriptor blindness'.

    After the intercept fix the absolute magnitude dropped sharply, and the
    analysis must now record that the earlier large value was an artefact of the
    mis-specified model -- not evidence of descriptor degeneracy.
    """
    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    ident = man.get("identical_fingerprint_analysis")
    assert ident is not None, "identical-fingerprint analysis missing"
    assert ident["n_pairs_with_identical_fingerprint"] >= 1
    assert "mae_among_identical" in ident
    assert ident["interpretation"]
    # The correction must be recorded, otherwise a reader could still believe the
    # old "descriptors cannot resolve similar molecules" claim.
    assert "caveat" in ident, "the artefact caveat was dropped"
    assert "截距" in ident["caveat"] or "intercept" in ident["caveat"].lower()

    report = (E4 / "e4_report.md").read_text(encoding="utf-8")
    assert "决定性检验" in report
    assert "必须记录的更正" in report


def test_identical_fingerprint_is_two_pairs_not_four_cases() -> None:
    """Reviewer 1: 4 molecules = 2 pairs, not 4 independent cases."""
    report = (E4 / "e4_report.md").read_text(encoding="utf-8")
    assert "只构成 2 个分子对" in report or "2 个分子对" in report


def test_in_vs_out_domain_is_compared() -> None:
    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    cmp = man["in_vs_out_of_domain"]
    assert cmp["n_in_domain"] + cmp["n_out_of_domain"] == 22
    assert "separation" in cmp


def test_applicability_domain_coverage_reported() -> None:
    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    assert man["counts"]["ad_coverage_pct"] is not None
    rows = _load(E4 / "applicability_domain.csv")
    assert len(rows) == 22
    n_in = sum(1 for r in rows if r["in_applicability_domain"] == "true")
    expected = round(100.0 * n_in / len(rows), 2)
    assert abs(float(man["counts"]["ad_coverage_pct"]) - expected) < 0.01
    # Out-of-domain rows must not be allowed to make a claim.
    for r in rows:
        if r["in_applicability_domain"] == "false":
            assert r["claim_allowed"] == "PREDICTION_OUT_OF_DOMAIN_NO_CLAIM"


def test_source_ood_carries_independence_caveat() -> None:
    """B01 proved DOI count != independent experiments; E4 must not forget it."""
    rows = _load(E4 / "source_ood_results.csv")
    assert rows
    measured = [r for r in rows if r["status"] == "measured"]
    for r in measured:
        assert "独立性" in r["note"] or "independent" in r["note"].lower(), (
            f"{r['source_doi']}: source-OOD row lacks the independence caveat")

    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    assert any("来源聚类" in c for c in man["cannot_claim"])


def test_family_grouping_is_real() -> None:
    """Leave-one-family-out must actually hold a family out."""
    man = json.loads((E4 / "e4_manifest.json").read_text(encoding="utf-8"))
    fam = man["family_counts"]
    assert len(fam) > 1, "only one family -- cross-family OOD is impossible"
    assert sum(fam.values()) == 22

    rows = _load(E4 / "leave_one_family_out.csv")
    for r in rows:
        # train + test must equal the total for a true leave-out design
        assert int(r["n_train"]) + int(r["test_n"]) == 22, (
            f"{r['family']}: train+test != 22")


def test_every_molecule_in_distance_analysis_once() -> None:
    rows = _load(E4 / "structural_distance_ood.csv")
    ids = [r["measurement_id"] for r in rows]
    assert len(ids) == len(set(ids)), "a molecule appears twice"
    assert len(ids) == 22


def test_errors_are_recomputable() -> None:
    for r in _load(E4 / "structural_distance_ood.csv"):
        expected = abs(float(r["y_pred"]) - float(r["y_true"]))
        assert abs(float(r["abs_error"]) - expected) < 1e-4, (
            f"{r['measurement_id']}: abs_error inconsistent")
