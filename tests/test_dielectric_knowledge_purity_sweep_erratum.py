"""Guards for the week 16 lever 9 erratum round.

Version 1 of the knowledge purity sweep handed ``permutation_importance`` ten
pool names while giving it a matrix whose leading columns were the frozen
physical block, so every score it reported was a physical column' s importance
wearing a pool member' s name.  The erratum re-runs the whole k grid with the
column targeting corrected, publishes both readings side by side, and has to
show that the defect was real rather than assert it.

These tests pin the four things that would make the erratum worthless:

* the defect reproduction is not vacuous -- a synthetic case where the answer is
  known has to come out with the same structure the real run reports;
* the label-to-column binding is checked against an explicit-index computation;
* the order sensitivity is real and is reported with all three orders, because
  the whole substance of the finding is that the k=10 cell is not an invariant;
* version 1' s files are byte-identical to the digest the pre-registration
  pinned, so the erratum never rewrote the reading it is correcting.

Nothing here fits a model on the real table: the heavy run belongs to the probe.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from xgboost import XGBRegressor

import probes.dielectric_knowledge_purity_sweep as v1
from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_knowledge_purity_sweep_erratum import (
    ARTIFACT_STEM,
    ARTIFACTS_DIR,
    CSV_TRUE,
    DEFECT_TOLERANCE,
    PHYSICAL_LABEL_PREFIX,
    PREREG_PATH,
    RE_REVIEW_AGREEMENT_TOLERANCE,
    RE_REVIEW_CANONICAL_ORDER_DELTA,
    REPORT_PATH,
    SUMMARY_PATH,
    defect_reproduction,
    offset_aware_importance,
    version_1_importance,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_erratum.py"
V1_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_summary.json"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def test_prereg_is_locked_before_the_run_and_keeps_version_1_thresholds(
    prereg: dict,
) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["correction_rule"]["k_grid"] == [2, 4, 6, 10]
    assert prereg["thresholds"]["pass_delta_r2"] == v1.PASS_DELTA_R2
    assert prereg["thresholds"]["kill_delta_r2"] == v1.KILL_DELTA_R2
    assert prereg["thresholds"]["min_positive_repeats"] == v1.MIN_POSITIVE_REPEATS
    assert prereg["thresholds"]["placebo_collapse_tolerance"] == v1.PLACEBO_COLLAPSE_TOLERANCE


def test_prereg_carries_the_version_1_pins(prereg: dict) -> None:
    pins = prereg["version_1_pins"]
    for relative, digest in pins.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file(), relative
        assert canonical_text_sha256(path) == digest, relative


def test_summary_was_written_by_the_script_on_disk(summary: dict) -> None:
    assert summary["inputs"]["lever_script_sha256"] == canonical_text_sha256(SCRIPT_PATH)


def test_version_1_files_are_untouched(summary: dict) -> None:
    observed = summary["version_1_digest_check"]
    assert observed, "the erratum has to record what it pinned"
    for relative, entry in observed.items():
        assert entry["intact"], relative
    assert canonical_text_sha256(V1_SUMMARY_PATH) == observed[
        "probes/dielectric_knowledge_purity_sweep_summary.json"
    ]["expected"]


def test_baseline_reproduces_the_published_r2(summary: dict) -> None:
    baseline = summary["baseline_reproduces"]
    assert baseline["verified"] is True
    assert abs(baseline["reproduced_r2"] - v1.REFERENCE_R2) <= v1.REFERENCE_TOLERANCE
    assert summary["main_scoreboard"]["fold_deal"]["matches_version_1_signature"] is True

def _synthetic_case() -> tuple[np.ndarray, np.ndarray]:
    """A matrix shaped like the real one, small enough to check by hand.

    `defect_reproduction` compares the ten scores version 1 reported against
    the first ten columns of the frozen block, so the synthetic frozen block has
    to be at least as wide as the knowledge pool (ten) or the reproduction would
    be reported as failing for a reason that has nothing to do with the defect.
    Twelve frozen columns plus the full ten-member pool reproduce the real
    13 + 10 shape without copying it.  Exactly one knowledge column drives the
    target, so the answer to "which member should win" is known in advance.
    """

    rng = np.random.default_rng(20260926)
    physical = rng.normal(size=(80, 12))
    knowledge = rng.normal(size=(80, 10))
    target = 5.0 * knowledge[:, 0] + 0.05 * physical[:, 0]
    return np.hstack([physical, knowledge]), target


def test_the_defect_is_reproducible_on_a_case_with_a_known_answer() -> None:
    """The exercise the whole finding rests on, on a matrix small enough to check.

    The version-1 call has to attribute the frozen block' s importances to pool
    names; the corrected call has to attribute the real driver to its own member.
    """

    features, target = _synthetic_case()
    rows = np.arange(features.shape[0])
    model = XGBRegressor(n_estimators=40, max_depth=3, random_state=0)
    model.fit(features, target)

    pool_ranking, physical = offset_aware_importance(
        model, features, target, rows=rows, shuffles=2, seed=0
    )
    assert [name for name, _ in physical] == [
        f"{PHYSICAL_LABEL_PREFIX}{index}" for index in range(12)
    ]
    assert sorted(name for name, _ in pool_ranking) == sorted(v1.KNOWLEDGE_POOL)
    # The second knowledge member is pure noise, so the first has to win.
    assert pool_ranking[0][0] == v1.KNOWLEDGE_POOL[0]
    assert pool_ranking[0][1] > dict(pool_ranking)[v1.KNOWLEDGE_POOL[1]]

    reported = version_1_importance(
        model, features, target, rows=rows, shuffles=2, seed=0
    )
    reproduction = defect_reproduction(reported, physical)
    assert reproduction["labels_sat_on_the_frozen_block"] is True
    assert reproduction["label_position_pairs_matched"] == len(v1.KNOWLEDGE_POOL)
    assert reproduction["max_abs_score_difference"] <= DEFECT_TOLERANCE
    assert reproduction["max_abs_multiset_difference"] <= DEFECT_TOLERANCE
    # And the defect is visible in the scores themselves.  Version 1 shuffled the
    # leading columns of the matrix, so every number it printed is on the frozen
    # block' s scale, and the member that actually drives the target is never
    # credited with anything near its measured importance.
    honest_driver = dict(pool_ranking)[v1.KNOWLEDGE_POOL[0]]
    assert honest_driver > max(score for _name, score in reported)
    assert honest_driver > dict(pool_ranking)[v1.KNOWLEDGE_POOL[1]]


def test_defect_reproduction_fails_when_the_labels_are_honest() -> None:
    """The check has to be able to say no, or it is decoration."""

    features, target = _synthetic_case()
    rows = np.arange(features.shape[0])
    model = XGBRegressor(n_estimators=40, max_depth=3, random_state=0)
    model.fit(features, target)
    pool_ranking, physical = offset_aware_importance(
        model, features, target, rows=rows, shuffles=2, seed=0
    )
    honest = defect_reproduction(pool_ranking[: len(v1.KNOWLEDGE_POOL)], physical)
    assert honest["labels_sat_on_the_frozen_block"] is False


def test_real_run_reproduced_the_defect_in_every_fold(summary: dict) -> None:
    block = summary["defect_reproduction"]
    assert block["folds_checked"] == 50
    assert block["folds_where_version_1_labels_sat_on_the_frozen_block"] == 50
    assert block["reproduced_in_every_fold"] is True
    assert block["worst_max_abs_score_difference"] <= block["tolerance"]


def test_real_run_verified_the_label_to_column_binding(summary: dict) -> None:
    block = summary["label_to_column_binding"]
    assert block["folds_checked"] == 3
    assert block["folds_verified"] == 3
    assert block["worst_max_abs_difference"] <= block["tolerance"]


def test_the_k10_cell_is_not_an_invariant_and_all_three_orders_are_reported(
    summary: dict,
) -> None:
    block = summary["order_sensitivity"]
    k10 = block["k10_by_order"]
    assert len(k10) == 3
    assert block["k10_spread"] == pytest.approx(max(k10.values()) - min(k10.values()))
    assert block["k10_spread"] > 0.0
    assert block["all_orders_below_the_pass_line"] is True
    assert max(k10.values()) < v1.PASS_DELTA_R2
    # `k10_by_order` names the version-1 order the long way round, because that entry
    # is the reading the Week 15 ledger quoted; `grid_by_order` uses the short label.
    # The mapping is written out rather than hidden behind a prefix match, so a
    # rename on either side fails here instead of sliding by.
    label_to_grid_label = {
        "version_1_broken_order_quoted_from_the_pinned_v1_summary": (
            "version_1_broken_order"
        ),
        "preregistered_pool_order": "preregistered_pool_order",
        "corrected_importance_order": "corrected_importance_order",
    }
    assert set(k10) == set(label_to_grid_label)
    for label, value in k10.items():
        grid = block["grid_by_order"][label_to_grid_label[label]]
        assert set(grid) == {"2", "4", "6", "10"}, label
        assert grid["10"] == pytest.approx(value), label
    # The value the ledger quoted as "the corrected k=10" has to be the one the
    # pinned version-1 summary published, or the erratum is correcting a number
    # nobody wrote down.
    version_1 = json.loads(V1_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert k10[
        "version_1_broken_order_quoted_from_the_pinned_v1_summary"
    ] == pytest.approx(version_1["verdict"]["delta_r2_by_k"]["10"])


def test_the_re_review_figure_is_identified_as_the_pool_order(summary: dict) -> None:
    """The ledger quoted a 'corrected' k=10 that is really the pool-order reading.

    Pinning that identification is the point: without it the erratum' s own k=10
    looks like a contradiction of the review instead of a third order.
    """

    block = summary["order_sensitivity"]["re_review_canonical_order_is_the_pool_order"]
    assert block["agreement"] == {str(k): True for k in RE_REVIEW_CANONICAL_ORDER_DELTA}
    for key, value in RE_REVIEW_CANONICAL_ORDER_DELTA.items():
        measured = summary["order_sensitivity"]["grid_by_order"]["preregistered_pool_order"][
            str(key)
        ]
        assert abs(float(measured) - float(value)) <= RE_REVIEW_AGREEMENT_TOLERANCE
    assert block["k10_exact_difference"] <= 1e-12


def test_verdict_is_sub_threshold_and_version_1_decision_is_preserved(summary: dict) -> None:
    assert summary["verdict"]["decision"] == "sub_threshold"
    comparison = summary["comparison_with_version_1"]
    assert comparison["version_1_decision"] == "sub_threshold"
    assert comparison["k10_version_1"] == float(
        comparison["version_1_delta_r2_by_k"]["10"]
    )
    assert comparison["k10_corrected"] == float(
        comparison["corrected_delta_r2_by_k"]["10"]
    )


def test_the_csv_artefacts_carry_the_pass_flags() -> None:
    defect = _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_defect_check.csv")
    binding = _rows(ARTIFACTS_DIR / f"{ARTIFACT_STEM}_binding_check.csv")
    assert defect and binding
    assert all(row["labels_sat_on_the_frozen_block"] in CSV_TRUE for row in defect)
    assert all(row["binding_verified"] in CSV_TRUE for row in binding)
    assert {row["protocol"] for row in defect} == {"corrected_purity"}


def test_the_erratum_does_not_overwrite_the_version_1_artefacts() -> None:
    """A correction that edits its subject is not a correction."""

    v1_report = REPOSITORY_ROOT / "reports" / "dielectric_knowledge_purity_sweep.md"
    assert v1_report.is_file()
    assert REPORT_PATH.is_file()
    assert REPORT_PATH != v1_report
    assert "offset-aware" in REPORT_PATH.read_text(encoding="utf-8")