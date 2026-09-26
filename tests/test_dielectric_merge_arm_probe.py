"""Guards for the Week 14 merge arm.

These tests pin the three pre-registered outcomes, and they are written so the
guard cannot pass vacuously:

* the merge rule is read from the pre-registration, not restated from memory;
* no lever passing means **no merge run** - and the summary has to say so with
  the pre-registered reason rather than going quiet;
* a lever with no readable pass/fail keeps the arm waiting instead of guessing;
* exactly one lever passing produces a merge that is *labelled degenerate*, with
  a delta of exactly 0.0 against the best single lever;
* two levers passing raises, because this round does not implement the joint
  refit and refusing is better than reporting an identity as a combination;
* a dead lever is never carried into the passing list;
* the summary on disk is not stale: it is rebuilt from the lever files and has
  to agree;
* the report file is byte-identical to what the summary renders.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_merge_arm_probe as merge

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_merge_arm_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_merge_arm.md"


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict:
    assert SUMMARY_PATH.is_file(), "run probes/dielectric_merge_arm_probe.py first"
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _state(lever_id: str, state: str, *, r2: float, baseline: float) -> dict:
    return {
        "lever_id": lever_id,
        "summary": f"probes/{lever_id}_summary.json",
        "summary_sha256": "0" * 64,
        "state": state,
        "decision": {"pass": "pass", "dead": "dead", "pending": None}[state],
        "reasons": [f"synthetic {state} reading"],
        "carried_into_the_merge_arm": state == "pass",
        "reading": {
            "available": True,
            "arm": lever_id,
            "representation": merge.HYBRID,
            "r2_mean": r2,
            "r2_std": 0.06,
            "mae_mean": 8.0,
            "mae_gt60_mean": 60.0,
            "spearman_mean": 0.78,
            "baseline_r2_mean": baseline,
            "baseline_r2_std": 0.089,
        },
    }


def _build(states: list[dict], prereg: dict) -> dict:
    return merge.build_summary(
        lever_states=states,
        prereg_payload=prereg,
        prereg_path=PREREG_PATH,
        generated_at="2026-09-26T00:00:00Z",
    )


def test_the_merge_rule_is_read_from_the_preregistration(summary: dict, prereg: dict) -> None:
    assert summary["prereg"]["merge_rule"] == prereg["merge_rule"]
    assert summary["prereg"]["if_nothing_passes"] == prereg["merge_rule"]["if_nothing_passes"]


def test_the_inventory_covers_the_preregistered_levers(summary: dict, prereg: dict) -> None:
    declared = [lever["id"] for lever in prereg["levers"]]
    assert declared == ["lever_2_association_blind_spot_features",
                        "lever_3_target_transform_and_robust_loss",
                        "lever_7_bagging"]
    assert [item["lever_id"] for item in summary["lever_inventory"]] == declared


def test_no_passing_lever_means_no_merge_run(prereg: dict) -> None:
    states = [
        _state("lever_2_association_blind_spot_features", "dead", r2=0.3972, baseline=0.4091),
        _state("lever_3_target_transform_and_robust_loss", "dead", r2=0.3038, baseline=0.4091),
        _state("lever_7_bagging", "dead", r2=0.40, baseline=0.4091),
    ]
    built = _build(states, prereg)
    assert built["merge_arm_run"] is False
    assert built["degenerate_single_lever_merge"] is False
    assert built["scored_attempts"] == 0
    assert "if_nothing_passes" in built["reason"]
    assert built["passing_levers"] == []
    assert built["dead_levers"] == [state["lever_id"] for state in states]
    assert built["merged_reading"] is None


def test_a_pending_lever_keeps_the_arm_waiting(prereg: dict) -> None:
    states = [
        _state("lever_2_association_blind_spot_features", "dead", r2=0.3972, baseline=0.4091),
        {
            "lever_id": "lever_3_target_transform_and_robust_loss",
            "summary": "probes/dielectric_target_transform_probe_summary.json",
            "state": "pending",
            "reason": "not on disk",
            "reading": None,
        },
        _state("lever_7_bagging", "pass", r2=0.42, baseline=0.4091),
    ]
    built = _build(states, prereg)
    assert built["merge_arm_run"] is False
    assert built["pending_levers"] == ["lever_3_target_transform_and_robust_loss"]
    assert "waits rather than guessing" in built["reason"]
    assert built["passing_levers"] == ["lever_7_bagging"]


def test_a_single_passing_lever_merges_degenerately(prereg: dict) -> None:
    states = [
        _state("lever_2_association_blind_spot_features", "dead", r2=0.3972, baseline=0.4091),
        _state("lever_3_target_transform_and_robust_loss", "dead", r2=0.3038, baseline=0.4091),
        _state("lever_7_bagging", "pass", r2=0.4185, baseline=0.4091),
    ]
    built = _build(states, prereg)
    assert built["merge_arm_run"] is True
    assert built["degenerate_single_lever_merge"] is True
    assert built["passing_levers"] == ["lever_7_bagging"]
    assert built["merged_reading"]["equivalent_to"] == "lever_7_bagging"
    assert built["merged_reading"]["r2_mean"] == 0.4185
    assert built["delta_vs_best_single_lever"] == 0.0
    assert built["delta_vs_baseline"] == pytest.approx(0.4185 - 0.4091, abs=1e-12)
    assert built["scored_attempts"] == 0


def test_two_passing_levers_refuse_to_be_called_a_merge(prereg: dict) -> None:
    states = [
        _state("lever_2_association_blind_spot_features", "pass", r2=0.43, baseline=0.4091),
        _state("lever_3_target_transform_and_robust_loss", "dead", r2=0.3038, baseline=0.4091),
        _state("lever_7_bagging", "pass", r2=0.4185, baseline=0.4091),
    ]
    with pytest.raises(merge.MergeArmNotImplemented):
        _build(states, prereg)


def test_a_dead_lever_is_never_carried_into_the_passing_list(summary: dict) -> None:
    states = {item["lever_id"]: item["state"] for item in summary["lever_inventory"]}
    for lever_id, state in states.items():
        if state != "pass":
            assert lever_id not in summary["passing_levers"]
        else:
            assert lever_id in summary["passing_levers"]


def test_the_stored_summary_is_not_stale(summary: dict, prereg: dict) -> None:
    """Rebuild the decision from the lever files and compare with what is stored."""

    states = [merge.read_lever_state(lever_id, path) for lever_id, path in merge.LEVER_SUMMARIES]
    rebuilt = _build(states, prereg)
    assert rebuilt["passing_levers"] == summary["passing_levers"]
    assert rebuilt["dead_levers"] == summary["dead_levers"]
    assert rebuilt["pending_levers"] == summary["pending_levers"]
    assert rebuilt["merge_arm_run"] == summary["merge_arm_run"]
    assert rebuilt["degenerate_single_lever_merge"] == summary["degenerate_single_lever_merge"]
    stored = {item["lever_id"]: item["state"] for item in summary["lever_inventory"]}
    fresh = {item["lever_id"]: item["state"] for item in rebuilt["lever_inventory"]}
    assert stored == fresh


def test_check_recomputes_the_stored_decision(summary: dict) -> None:
    assert merge.check_summary(summary) == []


def test_check_catches_a_tampered_summary(summary: dict) -> None:
    tampered = copy.deepcopy(summary)
    tampered["scored_attempts"] = 1
    assert merge.check_summary(tampered) != []
    tampered = copy.deepcopy(summary)
    if summary["passing_levers"]:
        tampered["passing_levers"] = []
        assert merge.check_summary(tampered) != []
    else:
        tampered["passing_levers"] = ["lever_7_bagging"]
        assert merge.check_summary(tampered) != []


def test_report_is_the_rendered_summary(summary: dict) -> None:
    assert REPORT_PATH.read_text(encoding="utf-8") == "\n".join(merge.render_report(summary))


def test_every_artifact_is_lf_only(summary: dict) -> None:
    for path in (SUMMARY_PATH, REPORT_PATH):
        raw = path.read_bytes()
        assert b"\r" not in raw, path
        assert not raw.startswith(b"\xef\xbb\xbf"), path