"""Literal pins for the Week 19 D6 ranking key (AF-13 discipline).

Every number this file asserts is typed out here instead of being re-derived
from prose: the gate table, the example ordering, the exact example scores and
the three generation-loop evidence strings.  A silent edit to the module or to
the spec turns this file red instead of quietly re-baselining the deliverable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w19_ranking_key as ranking

SPEC = REPOSITORY_ROOT / "reports" / "w19_ranking_key_spec.md"
MODULE_PATH = REPOSITORY_ROOT / "probes" / "w19_ranking_key.py"
TEST_PATH = Path(__file__)
NEW_FILES = (SPEC, MODULE_PATH, TEST_PATH)

# Gate table as measured from the repository artefacts on 2026-09-28:
# channel -> (gate, measured, passed).  'dielectric' is an R2 gate (higher is
# better), the other five are MAE gates (lower is better).
GATE_TABLE: dict[str, tuple[float, float, bool]] = {
    "dielectric": (0.60, 0.4766400383507876, False),
    "viscosity": (0.15, 0.17477197208762, False),
    "homo": (0.20, 0.19050925839013938, True),
    "lumo": (0.20, 0.13855083976437643, True),
    "oxidation": (0.15, 0.2905180517963865, False),
    "reduction": (0.15, 0.4096241620366996, False),
}

# Example fixture under the shipped equal weights.
BASELINE_ORDER = ("demo-v", "demo-y", "demo-x", "demo-z", "demo-w")
BASELINE_SCORES = {
    "demo-v": 0.7833333333333333,
    "demo-y": 0.7833333333333333,
    "demo-x": 0.5,
    "demo-z": 0.5,
    "demo-w": 0.41666666666666663,
}
BASELINE_FRONT = ("demo-x", "demo-y", "demo-z", "demo-v")

# The same fixture after the weights move to HOMO 0.9 / LUMO 0.1.
HEAVY_HOMO_KEYS = (
    ranking.KeySpec(channel="homo", column="HOMO_eV", direction="min", weight=0.9),
    ranking.KeySpec(channel="lumo", column="LUMO_eV", direction="max", weight=0.1),
)
HEAVY_HOMO_ORDER = ("demo-x", "demo-v", "demo-y", "demo-w", "demo-z")
HEAVY_HOMO_SCORES = {
    "demo-x": 0.9,
    "demo-v": 0.69,
    "demo-y": 0.69,
    "demo-w": 0.35,
    "demo-z": 0.1,
}

# Every literal the spec must keep, including the three generation-loop
# evidence strings and the owning artefact of every gate reading.
SPEC_LITERALS = (
    "0.349",
    "never subjected to a group-split audit",
    "CC-BY-NC-ND",
    "不做生成闭环",
    "永不作为训练数据",
    "0.4766400383507876",
    "0.17477197208762",
    "0.15686276760094522",
    "0.19050925839013938",
    "0.13855083976437643",
    "0.2905180517963865",
    "0.4096241620366996",
    "75.95675695251926",
    "0/5",
    "0.60",
    "0.15",
    "0.20",
    "high_permittivity_excluded",
    "probes/four_channel_coverage_summary.json",
    "models/homo_lumo_baselines.json",
    "probes/viscosity_baseline_summary.json",
    "probes/p4_redox_v2_summary.json",
    "probes/dielectric_onsager_delta_summary.json",
    "reports/dielectric_pool_expansion_audit.md",
    "physics-informed descriptors that can implicitly capture intermolecular interactions",
)


def _by_name(rows: Any) -> dict[str, Any]:
    return {str(row["name"]): row for row in rows}


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_the_example_ranking_is_pinned_literally() -> None:
    table = ranking.ranking_key_table(ranking.EXAMPLE_MOLECULES)
    assert tuple(str(entry["name"]) for entry in table) == BASELINE_ORDER
    assert tuple(int(entry["rank"]) for entry in table) == (1, 2, 3, 4, 5)
    assert {str(entry["name"]): float(entry["score"]) for entry in table} == BASELINE_SCORES
    assert {str(entry["name"]): bool(entry["on_front"]) for entry in table} == {
        "demo-v": True,
        "demo-y": True,
        "demo-x": True,
        "demo-z": True,
        "demo-w": False,
    }


def test_the_example_front_is_pinned_literally() -> None:
    front = tuple(str(row["name"]) for row in ranking.pareto_front(ranking.EXAMPLE_MOLECULES))
    assert front == BASELINE_FRONT


def test_the_default_key_is_equal_weight_over_the_two_gated_channels() -> None:
    assert ranking.DEFAULT_WEIGHTS == {"homo": 0.5, "lumo": 0.5}
    assert tuple(spec.channel for spec in ranking.DEFAULT_KEYS) == ("homo", "lumo")
    assert tuple(spec.direction for spec in ranking.DEFAULT_KEYS) == ("min", "max")


def test_the_gate_table_matches_the_recorded_readings() -> None:
    for channel, (gate, measured, passed) in GATE_TABLE.items():
        record = ranking.CHANNEL_GATE_STATUS[channel]
        assert float(record["gate"]) == gate
        assert float(record["measured"]) == measured
        assert bool(record["passed"]) is passed
        assert str(record["source"]).strip()
    assert ranking.GATED_CHANNELS == ("homo", "lumo")


def test_no_ungated_channel_can_enter_the_key() -> None:
    assert "dielectric" not in ranking.DEFAULT_WEIGHTS
    assert set(ranking.DEFAULT_WEIGHTS) <= set(ranking.GATED_CHANNELS)
    with pytest.raises(ValueError, match="gated"):
        ranking.validate_keys((ranking.KeySpec("dielectric", "eps", "max", 1.0),))
    with pytest.raises(ValueError, match="sum to one"):
        ranking.validate_keys(
            (
                ranking.KeySpec("homo", "HOMO_eV", "min", 0.4),
                ranking.KeySpec("lumo", "LUMO_eV", "max", 0.4),
            )
        )
    with pytest.raises(ValueError, match="share one input column"):
        ranking.validate_keys(
            (
                ranking.KeySpec("homo", "HOMO_eV", "min", 0.5),
                ranking.KeySpec("lumo", "HOMO_eV", "max", 0.5),
            )
        )


def test_a_weight_change_moves_the_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = ranking.ranking_key_table(ranking.EXAMPLE_MOLECULES)
    assert tuple(str(entry["name"]) for entry in baseline) == BASELINE_ORDER

    monkeypatch.setattr(ranking, "DEFAULT_KEYS", HEAVY_HOMO_KEYS)

    changed = ranking.ranking_key_table(ranking.EXAMPLE_MOLECULES)
    changed_order = tuple(str(entry["name"]) for entry in changed)
    assert changed_order == HEAVY_HOMO_ORDER
    assert changed_order != BASELINE_ORDER
    assert {str(entry["name"]): float(entry["score"]) for entry in changed} == HEAVY_HOMO_SCORES


def test_ties_are_non_dominating_and_broken_by_name() -> None:
    rows = _by_name(ranking.EXAMPLE_MOLECULES)
    assert ranking.dominates(rows["demo-v"], rows["demo-y"]) is False
    assert ranking.dominates(rows["demo-y"], rows["demo-v"]) is False
    assert ranking.dominates(rows["demo-y"], rows["demo-w"]) is True
    assert ranking.dominates(rows["demo-v"], rows["demo-w"]) is True
    assert ranking.dominates(rows["demo-w"], rows["demo-y"]) is False

    table = ranking.ranking_key_table(ranking.EXAMPLE_MOLECULES)
    scores = {str(entry["name"]): float(entry["score"]) for entry in table}
    assert scores["demo-v"] == scores["demo-y"]
    tied_order = [name for name in BASELINE_ORDER if name in {"demo-v", "demo-y"}]
    assert tied_order == ["demo-v", "demo-y"]


def test_the_failure_zone_is_declared_and_never_ranked() -> None:
    assert ranking.HIGH_PERMITTIVITY_EPS == 60.0
    assert ranking.high_permittivity_excluded(60.0) is False
    assert ranking.high_permittivity_excluded(60.1) is True
    assert ranking.high_permittivity_excluded(None) is False
    assert "dielectric" not in ranking.DEFAULT_WEIGHTS


def test_a_missing_or_non_finite_reading_is_refused() -> None:
    with pytest.raises(ValueError):
        ranking.assign_scores(
            [{"name": "broken", "HOMO_eV": float("nan"), "LUMO_eV": 1.0}]
        )
    with pytest.raises(ValueError):
        ranking.assign_scores([{"name": "short", "HOMO_eV": -8.0}])


def test_empty_input_is_empty_output() -> None:
    assert ranking.ranking_key_table([]) == []
    assert ranking.assign_scores([]) == []
    assert ranking.pareto_front([]) == []


def test_the_module_exports_the_documented_api() -> None:
    for name in (
        "CHANNEL_GATE_STATUS",
        "DEFAULT_KEYS",
        "DEFAULT_WEIGHTS",
        "EXAMPLE_MOLECULES",
        "GATED_CHANNELS",
        "HIGH_PERMITTIVITY_EPS",
        "KeySpec",
        "assign_scores",
        "dominates",
        "high_permittivity_excluded",
        "pareto_front",
        "ranking_key_table",
        "validate_keys",
    ):
        assert name in ranking.__all__
        assert hasattr(ranking, name)


def test_the_spec_keeps_every_pinned_literal() -> None:
    text = _spec_text()
    missing = [literal for literal in SPEC_LITERALS if literal not in text]
    assert missing == []


def test_the_spec_states_the_ranking_key_position() -> None:
    text = _spec_text()
    assert "排序键，不是候选生成器" in text
    assert "Pareto" in text
    assert "权重" in text


def test_the_three_new_files_are_lf_without_bom() -> None:
    for path in NEW_FILES:
        payload = path.read_bytes()
        assert payload, str(path)
        assert not payload.startswith(b"\xef\xbb\xbf"), str(path)
        assert b"\r\n" not in payload, str(path)
