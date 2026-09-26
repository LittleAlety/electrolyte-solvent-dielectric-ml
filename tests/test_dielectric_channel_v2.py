"""Guards for the dielectric-channel v2 model-family comparison.

These tests pin what makes v2 auditable rather than self-serving:

* the pool digest and the judged thresholds are read from the locked
  pre-registration and are not restated from memory;
* EC and PC leave every training side of all 50 folds, and the per-fold
  removal count is written down;
* the SELECTION_RULE is a declared, machine-executable constant and the
  reported winner is exactly what that rule returns;
* every declared family is present in every artifact (no silent omission);
* the C1 and C2 readouts recompute from the per-repeat prediction artifact;
* the frozen v1 family still reproduces the stage-1 pilot numbers;
* the tree-ceiling diagnostic is reproducible from the extrapolation artifact;
* every new artifact is LF-only.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import pathlib
import sys

import numpy as np
import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE_PATH = REPOSITORY_ROOT / "probes" / "dielectric_channel_v2.py"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
PILOT_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_channel_v2_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_channel_v2.md"
ARTIFACT_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
FOLDS_PATH = ARTIFACT_DIR / "dielectric_channel_v2_folds.csv"
PREDICTIONS_PATH = ARTIFACT_DIR / "dielectric_channel_v2_predictions.csv"
STRATA_PATH = ARTIFACT_DIR / "dielectric_channel_v2_strata.csv"
EXTRAPOLATION_PATH = ARTIFACT_DIR / "dielectric_channel_v2_extrapolation.csv"

POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
# Literal pin of the *current* pre-registration revision.  The live file is
# re-hashed as well, so the two must agree: a silent revision bump has to fail
# this guard rather than quietly re-baseline it.
PREREG_SHA256 = "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
POOL_ROWS = 236
EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
PC_INCHIKEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
TRUTH = {"EC": 90.5, "PC": 64.9}
K = 20
C2_GATE = 0.10
PASS_EXPRESSION = "C1 and C2_solvent and C2_additive and C3"
REQUIRED_GROUPS = {"a", "b", "c", "d", "e", "control"}
LF_ARTIFACTS = (FOLDS_PATH, PREDICTIONS_PATH, STRATA_PATH, EXTRAPOLATION_PATH)

_MODULE: object | None = None


def _module():
    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("dielectric_channel_v2_probe", PROBE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _prereg() -> dict:
    return _json(PREREG_PATH)


def _table_row(family: str) -> dict:
    return next(row for row in _summary()["family_table"] if row["family"] == family)


def _aggregated(family: str) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for row in _rows(PREDICTIONS_PATH):
        if row["family"] == family:
            buckets.setdefault(row["inchikey"], []).append(float(row["prediction"]))
    assert buckets, f"no predictions for {family}"
    return {key: float(np.mean(values)) for key, values in buckets.items()}


def _rank_of(aggregated: dict[str, float], inchikey: str) -> int:
    order = sorted(aggregated, key=lambda key: (-aggregated[key], key))
    return order.index(inchikey) + 1


def test_pool_digest_is_pinned_to_the_preregistration() -> None:
    digest = hashlib.sha256(POOL_PATH.read_bytes()).hexdigest()
    assert digest == POOL_SHA256
    assert _prereg()["pool_rule"]["pool_sha256"] == POOL_SHA256
    pool = _summary()["pool"]
    assert pool["sha256"] == POOL_SHA256
    assert pool["sha256_expected"] == POOL_SHA256
    assert pool["rows"] == POOL_ROWS
    assert len(_rows(POOL_PATH)) == POOL_ROWS


def test_judgement_criteria_come_from_the_preregistration_and_are_unchanged() -> None:
    criteria = _prereg()["criteria"]
    assert criteria["C1_recall_at_K"]["K"] == K
    assert criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"] == C2_GATE
    assert criteria["pass_expression"] == PASS_EXPRESSION
    locked = _summary()["prereg"]["locked_constants_read_verbatim"]
    assert locked["C1_K"] == criteria["C1_recall_at_K"]["K"]
    assert (
        locked["C2_solvent_max_abs_delta_log10_epsilon"]
        == criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"]
    )
    assert locked["pass_expression"] == criteria["pass_expression"]
    assert _summary()["outcome"]["c1_gate_K"] == criteria["C1_recall_at_K"]["K"]
    assert (
        _summary()["outcome"]["c2_gate_abs_delta_log10"]
        == criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"]
    )


def test_prereg_sha256_is_recorded_and_matches_the_locked_file() -> None:
    module = _module()
    recorded = _summary()["prereg"]["sha256"]
    assert recorded == PREREG_SHA256
    assert module.canonical_text_sha256(PREREG_PATH) == PREREG_SHA256
    assert recorded == module.canonical_text_sha256(PREREG_PATH)
    assert _summary()["prereg"]["status"] == "LOCKED"


def test_fold_geometry_matches_the_frozen_precedent() -> None:
    folds = _rows(FOLDS_PATH)
    assert len(folds) == 50
    assert {row["fold"] for row in folds} == {str(value) for value in range(5)}
    assert {row["repeat"] for row in folds} == {str(value) for value in range(10)}
    for row in folds:
        split_index = int(row["split_index"])
        assert int(row["fold"]) == split_index % 5
        assert int(row["repeat"]) == split_index // 5
        assert int(row["seed"]) == 42 + split_index
        assert int(row["test_count"]) in (47, 48)
    for repeat in range(10):
        assert (
            sum(int(row["test_count"]) for row in folds if int(row["repeat"]) == repeat)
            == POOL_ROWS
        )
    assert _summary()["fold_and_seed"]["fold_scheme"] == (
        "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)"
    )
    assert _summary()["fold_and_seed"]["seed_scheme"] == (
        "42 + global RepeatedKFold split index"
    )


def test_every_fold_removes_both_champions_from_the_training_side() -> None:
    folds = _rows(FOLDS_PATH)
    for row in folds:
        assert row["champions_intersect_train_after_exclusion"] == "0"
        removed = int(row["champions_removed_EC"]) + int(row["champions_removed_PC"])
        in_test = len([short for short in row["champions_in_test"].split(";") if short])
        assert removed + in_test == 2
        assert int(row["train_count_after_exclusion"]) == (
            int(row["train_count_before_exclusion"]) - removed
        )
    assert _summary()["exclusion"]["champions_intersect_train_ids_empty"] is True
    assert _summary()["exclusion"]["min_train_rows_after_exclusion"] == 186
    assert _summary()["exclusion"]["max_train_rows_after_exclusion"] == 189


def test_champion_removal_counts_are_recorded() -> None:
    exclusion = _summary()["exclusion"]
    assert exclusion["excluded_champions"] == ["EC", "PC"]
    for short in ("EC", "PC"):
        assert exclusion["champion_train_side_removals"][short] == 40
        assert exclusion["champion_held_out_folds"][short] == 10
    folds = _rows(FOLDS_PATH)
    assert sum(int(row["champions_removed_EC"]) for row in folds) == 40
    assert sum(int(row["champions_removed_PC"]) for row in folds) == 40
    assert sum(1 for row in folds if "EC" in row["champions_in_test"].split(";")) == 10
    assert sum(1 for row in folds if "PC" in row["champions_in_test"].split(";")) == 10


def test_dummy_shares_the_same_folds_as_every_other_family() -> None:
    rows = _rows(PREDICTIONS_PATH)
    families = {row["family"] for row in rows}
    assert "dummy_mean" in families
    reference = {
        (row["repeat"], row["inchikey"]): row["fold"]
        for row in rows
        if row["family"] == "dummy_mean"
    }
    for row in rows:
        assert reference[(row["repeat"], row["inchikey"])] == row["fold"]


def test_all_declared_families_are_reported_everywhere() -> None:
    summary = _summary()
    declared = [family["id"] for family in summary["families"]]
    assert len(declared) == len(set(declared))
    assert sorted(declared) == sorted(row["family"] for row in summary["family_table"])
    assert sorted(declared) == sorted({row["family"] for row in _rows(PREDICTIONS_PATH)})
    assert sorted(declared) == sorted({row["family"] for row in _rows(STRATA_PATH)})
    reported = {row["family"] for row in summary["family_table"]}
    assert "frozen_v1_log_eps_xgb" in reported
    assert _summary()["outcome"]["winner_id"] in (None, *declared)


def test_required_family_groups_are_all_present() -> None:
    groups = {family["group"] for family in _summary()["families"]}
    assert REQUIRED_GROUPS <= groups
    assert {row["family_group"] for row in _summary()["family_table"]} == groups


def test_c1_readout_recomputes_from_the_predictions_artifact() -> None:
    for family in [family["id"] for family in _summary()["families"]]:
        aggregated = _aggregated(family)
        hits = 0
        for short, inchikey in (("EC", EC_INCHIKEY), ("PC", PC_INCHIKEY)):
            rank = _rank_of(aggregated, inchikey)
            assert rank == _table_row(family)[f"{short.lower()}_rank"]
            hits += int(rank <= K)
        assert hits == _table_row(family)["c1_hits"]
        assert bool(_table_row(family)["c1_passed"]) == (hits == 2)


def test_c2_readout_recomputes_from_the_predictions_artifact() -> None:
    for family in [family["id"] for family in _summary()["families"]]:
        aggregated = _aggregated(family)
        deltas = {
            short: abs(math.log10(aggregated[inchikey] / TRUTH[short]))
            for short, inchikey in (("EC", EC_INCHIKEY), ("PC", PC_INCHIKEY))
        }
        row = _table_row(family)
        assert deltas["EC"] == pytest.approx(row["ec_abs_delta_log10"], abs=1e-12)
        assert deltas["PC"] == pytest.approx(row["pc_abs_delta_log10"], abs=1e-12)
        assert max(deltas.values()) == pytest.approx(row["c2_max_abs_delta_log10"], abs=1e-12)
        assert bool(row["c2_passed"]) == (max(deltas.values()) <= C2_GATE)


def test_c2_truths_come_from_the_preregistered_champion_set() -> None:
    champions = {
        item["short"]: item
        for item in _prereg()["champion_set"]["solvent_list"]
    }
    for short, truth in TRUTH.items():
        assert champions[short]["truth_dielectric"] == truth
        reported = _table_row("frozen_v1_log_eps_xgb")["champions"][short]
        assert reported["truth_dielectric"] == truth
        assert reported["inchikey"] == (
            EC_INCHIKEY if short == "EC" else PC_INCHIKEY
        )


def test_selection_rule_is_declared_and_the_winner_follows_it() -> None:
    module = _module()
    rule = _summary()["selection_rule"]
    assert rule["rule_id"] == module.SELECTION_RULE["rule_id"]
    assert rule["text"] == module.SELECTION_RULE["text"]
    assert rule["declared_before_execution"] is True
    assert rule["baseline_family"] == "frozen_v1_log_eps_xgb"
    winner, eligible = module.select_winner(_summary()["family_table"])
    outcome = _summary()["outcome"]
    assert eligible == outcome["eligible_families_under_selection_rule"]
    assert (winner["family"] if winner else None) == outcome["winner_id"]
    baseline = _table_row(rule["baseline_family"])
    for row in _summary()["family_table"]:
        if row["family"] == baseline["family"]:
            continue
        is_eligible = (
            row["oof_raw_mae"] <= baseline["oof_raw_mae"]
            and row["c1_hits"] > baseline["c1_hits"]
        )
        assert is_eligible == (row["family"] in eligible)


def test_baseline_reproduces_the_stage1_pilot_readout() -> None:
    anchor = _summary()["regression_anchor_vs_stage1_pilot"]
    pilot = _json(PILOT_SUMMARY_PATH)["readings"]
    assert anchor["ranks_match"] is True
    assert anchor["max_abs_delta_diff"] <= anchor["tolerance"]
    assert anchor["recomputed_ec_rank"] == anchor["pilot_ec_rank"] == 24
    assert anchor["recomputed_pc_rank"] == anchor["pilot_pc_rank"] == 58
    assert anchor["recomputed_ec_delta_log10"] == pytest.approx(
        pilot["C2_magnitude_solvent"]["champions"]["EC"]["delta_log10"], abs=1e-9
    )
    assert anchor["recomputed_pc_delta_log10"] == pytest.approx(
        pilot["C2_magnitude_solvent"]["champions"]["PC"]["delta_log10"], abs=1e-9
    )
    baseline = _table_row("frozen_v1_log_eps_xgb")
    assert baseline["is_baseline"] is True
    assert baseline["c1_hits"] == 0
    assert baseline["c2_passed"] is False


def test_frozen_tree_predictions_are_capped_by_the_training_ceiling() -> None:
    rows = _rows(EXTRAPOLATION_PATH)
    assert len(rows) == 20
    assert all(row["prediction_at_or_below_train_max"] == "true" for row in rows)
    for row in rows:
        assert float(row["ensemble_prediction"]) <= float(row["train_max_epsilon"]) + 1e-9
    diagnostic = _summary()["extrapolation_diagnostic"]
    assert diagnostic["all_predictions_at_or_below_train_max"] is True
    assert diagnostic["max_prediction_minus_train_max"] <= 0.0
    for short in ("EC", "PC"):
        assert diagnostic["per_champion"][short]["fold_rows"] == 10


def test_strata_artifact_covers_every_family_and_stratum() -> None:
    rows = _rows(STRATA_PATH)
    families = [family["id"] for family in _summary()["families"]]
    assert len(rows) == len(families) * 3
    for family in families:
        subset = [row for row in rows if row["family"] == family]
        assert {row["stratum"] for row in subset} == {"le_20", "20_60", "gt60"}
        assert sum(int(row["n"]) for row in subset) == POOL_ROWS


def test_onsager_pole_blowups_are_reported_not_hidden() -> None:
    evidence = _summary()["extrapolation_failure_evidence"]
    assert evidence["onsager_inverse_clip_bounds"] == [-0.999999, 1.0 - 1e-9]
    events = evidence["onsager_clip_events_by_family"]
    assert set(events) == {family["id"] for family in _summary()["families"]}
    for family in ("onsager_mu", "ridge_onsager_multivar"):
        assert events[family] > 0
        assert _table_row(family)["max_prediction"] > 1e3
    assert "onsager_mu" in evidence["families_with_predictions_above_1e3"]
    secondary = _summary()["secondary_diagnostic_median_aggregation"]
    assert secondary["gating"] is False
    assert secondary["families_passing_c2_under_median_aggregation"] == []


def test_no_family_passes_c1_and_c2_together() -> None:
    outcome = _summary()["outcome"]
    assert outcome["families_passing_c1_and_c2"] == []
    assert outcome["families_passing_c2_solvent"] == []
    assert outcome["best_by_c2_family"]["c2_max_abs_delta_log10"] > C2_GATE
    assert outcome["l3_verdict_status"] == (
        "not_run_dielectric_channel_only_not_a_verdict"
    )


def test_new_artifacts_are_lf_only() -> None:
    for path in (*LF_ARTIFACTS, SUMMARY_PATH, REPORT_PATH):
        assert path.is_file(), f"missing artifact: {path}"
        assert b"\r" not in path.read_bytes(), f"{path} is not LF-only"


def test_summary_carries_the_required_disclaimer_and_is_not_a_verdict() -> None:
    summary = _summary()
    module = _module()
    assert summary["disclaimer"] == module.DISCLAIMER
    assert "先声明后执行" in summary["disclaimer"]
    assert "无一遗漏上报" in summary["disclaimer"]
    assert summary["not_a_verdict"] is True
    assert summary["verdict_eligible"] is False


def test_report_exists_and_repeats_the_same_winner() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "## 七、诚实结论" in text
    assert "## 五、外推失败机制诊断" in text
    for family in [family["id"] for family in _summary()["families"]]:
        assert family in text
    outcome = _summary()["outcome"]
    if outcome["winner_id"] is None:
        assert "胜者：**无**" in text
    else:
        assert outcome["winner_id"] in text