"""B05 feature-quality guards.

Reviewers 3 and 4 (B04+B05) raised six defects about the feature set. Four were
measurable facts, all pointing the same way: the nominal column count overstates the
information content. These tests pin the audit and the corrections.

Guarded:
  1. the audit measures effective rank, not just column count
  2. exact collinearity is recorded
  3. the molar-volume algebraic identity is recorded
  4. the registry covers every feature the model actually fits
  5. feature sets are consistent across experiments
  6. family-rule precedence is documented, and sulfolane is classified
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B05 = REPO_ROOT / "outputs" / "b05"
FQA = B05 / "feature_quality_audit.json"
MI = B05 / "model_input_manifest.json"
REG = B05 / "feature_registry_v2.csv"

pytestmark = pytest.mark.skipif(
    not FQA.is_file() or not MI.is_file(),
    reason="feature audit not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _fqa() -> dict:
    return json.loads(FQA.read_text(encoding="utf-8"))


def _mi() -> dict:
    return json.loads(MI.read_text(encoding="utf-8"))


def test_effective_rank_is_measured_and_lower_than_nominal() -> None:
    """12 columns but fewer independent directions -- that gap must be reported."""
    fqa = _fqa()["effective_rank"]
    assert fqa["rank_of_E1_matrix"] < fqa["nominal_columns_E1"], (
        "effective rank should be below the nominal column count")
    assert "rank" in fqa["interpretation"].lower() or "秩" in fqa["interpretation"]


def test_exact_collinearity_is_recorded() -> None:
    pairs = _fqa()["defect_2_exact_collinearity"]["pairs"]
    assert pairs, "exact collinearity not recorded"
    names = {(p["feature_a"], p["feature_b"]) for p in pairs}
    assert ("polarizability_A3", "polarizability_au") in names or \
           ("polarizability_au", "polarizability_A3") in names
    for p in pairs:
        assert abs(float(p["pearson_r"])) > 0.999999
        assert p["verdict"] in ("EXACTLY_COLLINEAR", "NEARLY_COLLINEAR")


def test_molar_volume_identity_is_recorded() -> None:
    identities = _fqa()["defect_3_derived_feature_disguised"]["identities"]
    assert identities, "molar volume identity not recorded"
    ident = identities[0]
    assert "N_A" in ident["identity"] or "N_A" in ident["relation"]
    assert ident["holds_exactly"] == "true"
    assert "vdW" in ident["consequence"] or "腔体积" in ident["consequence"]


def test_registry_covers_every_fitted_feature() -> None:
    """The manifest must describe what the model actually consumed."""
    unreg = _fqa()["defect_1_unregistered_feature"]["unregistered"]
    registry = {(r.get("feature") or "").strip() for r in _load(REG)}
    # After the fix, nothing the model fits may be absent from the registry.
    for feature in unreg:
        assert feature in registry, (
            f"{feature} is fitted but still missing from the registry")
    assert "total_energy_hartree" in registry


def test_feature_sets_are_consistent_across_experiments() -> None:
    """E1 used to fit 12 columns while E4/E6/B07 fit 11."""
    mi = _mi()
    fs = mi["feature_set_inconsistency"]
    assert "11" in fs["E4_E6_B07_use"] or "12" in fs["E1_uses"]
    # The registry note must explain the resolution.
    assert fs["note"], "must state how the inconsistency was resolved"

    e1 = json.loads(
        (B05 / "E1_structure_vs_electronic" / "e1_manifest.json")
        .read_text(encoding="utf-8"))
    n_e1 = e1["feature_sets"]["n_features_total"]
    # E1 now uses the same 11 as everyone else.
    assert n_e1 == 11, f"E1 still fits {n_e1} features, expected 11"
    assert "total_energy_hartree" in e1["feature_sets"]["excluded"]


def test_family_rule_precedence_is_documented() -> None:
    e4 = json.loads(
        (B05 / "E4_domain_generalization" / "e4_manifest.json")
        .read_text(encoding="utf-8"))
    prec = e4["family_rules_precedence"]
    assert prec["order"], "rule precedence order not exported"
    assert prec["smarts"], "SMARTS patterns not exported"
    assert prec["n_molecules_matching_multiple_rules"] > 0, (
        "the multi-rule overlap should be recorded, not hidden")
    for ex in prec["multi_rule_examples"]:
        assert ex["matched"].count(";") >= 1 or len(ex["matched"]) > 0


def test_sulfolane_is_classified_as_a_sulfone() -> None:
    """It was 'unclassified' before a sulfone rule existed."""
    e4 = json.loads(
        (B05 / "E4_domain_generalization" / "e4_manifest.json")
        .read_text(encoding="utf-8"))
    fam = e4["family_counts"]
    assert fam.get("sulfone", 0) >= 1, (
        "sulfolane is still unclassified; the sulfone rule is missing")


def test_redundancies_are_declared_in_the_manifest() -> None:
    mi = _mi()
    assert len(mi["redundancies"]) >= 2
    kinds = {r["kind"] for r in mi["redundancies"]}
    assert "EXACT_UNIT_DUPLICATE" in kinds
    assert "ALGEBRAIC_IDENTITY" in kinds


def test_hypothesis_table_is_not_hardcoded() -> None:
    """The boundary report used to hardcode '12.8-21.3' and '0.16'."""
    report = (B05 / "model_boundary_report.md").read_text(encoding="utf-8")
    # The stale literals must be gone.
    assert "12.8–21.3" not in report, "stale hardcoded family range remains"
    assert "MAE 仅降 0.16" not in report, "stale hardcoded delta remains"
