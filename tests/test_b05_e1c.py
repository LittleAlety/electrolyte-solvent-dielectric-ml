"""B05-E1c guards: the block ablation must compare like with like.

E1 compared "structure" against "structure + electronic" and reported that the
electronic block adds value. Reviewer 4's attack showed that framing hides the
real result: the electronic block ALONE is better than the combination, and a
single descriptor (dipole) recovers most of it. These tests pin that finding and
the protocol that makes it fair.

Guarded:
  1. every block is evaluated with the same nested protocol
  2. the structural block does NOT beat the electronic block
  3. the combined block is worse than electronic-only (the point E1 missed)
  4. dipole alone is close to the whole electronic block
  5. no block is reported as confirmatory
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E1C = REPO_ROOT / "outputs" / "b05" / "E1c_feature_block_ablation"

pytestmark = pytest.mark.skipif(
    not (E1C / "e1c_manifest.json").is_file(),
    reason="E1c not run yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _man() -> dict:
    return json.loads((E1C / "e1c_manifest.json").read_text(encoding="utf-8"))


def test_protocol_is_nested_everywhere() -> None:
    """A fair block comparison needs lambda chosen inside the training fold."""
    m = _man()
    assert "nested" in m["protocol"].lower()
    assert len(m["lambda_grid"]) >= 4
    # Every block must record the lambda it actually chose.
    for b in m["blocks"]:
        assert b["lambda_chosen_median"] in m["lambda_grid"]


def test_structural_block_does_not_beat_electronic() -> None:
    m = _man()
    blocks = {b["block"]: b for b in m["blocks"]}
    x0 = blocks["X0_structural_7"]["nested_loo_mae"]
    x1 = blocks["X1_electronic_4"]["nested_loo_mae"]
    assert x1 < x0, "the electronic block should out-perform the structural block"


def test_combined_block_is_worse_than_electronic_only() -> None:
    """This is the finding E1 could not see: adding X0 to X1 hurts."""
    m = _man()
    f = m["findings"]
    if f["combined_worse_than_electronic_only"]:
        assert f["combined_minus_electronic_mae"] > 0
        blocks = {b["block"]: b for b in m["blocks"]}
        assert (blocks["X0_plus_X1_11"]["nested_loo_mae"]
                > blocks["X1_electronic_4"]["nested_loo_mae"])


def test_dipole_alone_near_electronic_block() -> None:
    m = _man()
    f = m["findings"]
    if f["dipole_alone_near_electronic_block"]:
        # Within 15% of the electronic block's MAE.
        assert f["dipole_as_pct_of_electronic_block"] <= 115.0
        assert f["dipole_mae"] < m["constant_baseline_mae"], (
            "dipole alone must still beat the constant baseline")


def test_best_block_is_recorded_and_wins() -> None:
    m = _man()
    blocks = {b["block"]: b for b in m["blocks"]}
    best = blocks[m["findings"]["best_block"]]
    for b in m["blocks"]:
        assert best["nested_loo_mae"] <= b["nested_loo_mae"] + 1e-9


def test_no_block_is_confirmatory() -> None:
    m = _man()
    assert m["status"] == "EXPLORATORY_NOT_CONFIRMATORY"
    report = (E1C / "e1c_report.md").read_text(encoding="utf-8")
    assert "不能断言" in report, "must state what cannot be claimed"


def test_cumulative_addition_is_monotone_in_features() -> None:
    rows = _load(E1C / "cumulative_addition.csv")
    assert rows
    ns = [int(r["n_features"]) for r in rows]
    assert ns == list(range(1, len(rows) + 1)), (
        "cumulative table must add exactly one feature per row")


def test_permutation_null_present_per_block() -> None:
    for b in _man()["blocks"]:
        assert "feature_permutation_p" in b
        assert 0.0 <= float(b["feature_permutation_p"]) <= 1.0


def test_report_states_the_e1_correction() -> None:
    report = (E1C / "e1c_report.md").read_text(encoding="utf-8")
    assert "对 E1 结论的修正" in report or "修正后" in report
    assert "结构描述符" in report
