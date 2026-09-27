"""Guards for the Week 18 lane-B arm: the epsilon applicability-domain scoreboard.

The frozen headline has to reproduce bit for bit, the two scoreboards have to stay
separate objects that nothing averages together, the D1 rule has to stay a feature-only
rule that the code recomputes, and the placebo has to collapse.  Nothing here refits the
ten-fold arm: the expensive numbers are read from the committed summary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from probes import dielectric_applicability_domain as probe

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
V3_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v3_summary.json"


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(probe.PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(probe.SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v3_summary() -> dict:
    return json.loads(V3_SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scoreboard() -> dict:
    import dielectric_coordination_block as v1

    return v1.build_scoreboard()


def test_prereg_is_locked_before_the_run(prereg: dict) -> None:
    assert prereg["status"] == "locked_before_run"
    assert prereg["decisions"]["promoted"] is False
    assert prereg["frozen_headline"]["r2"] == probe.HEADLINE_R2
    assert prereg["seeds"]["set"] == list(probe.SEEDS)


def test_the_headline_is_pinned_in_three_places(prereg: dict, v3_summary: dict) -> None:
    published = v3_summary["arms"][probe.ARM_HEADLINE][probe.REPRESENTATION]["r2"]["mean"]
    assert published == pytest.approx(probe.HEADLINE_R2, abs=1e-15)
    assert prereg["frozen_headline"]["r2"] == published
    assert v3_summary["verdict"]["baseline_r2_published"] != probe.HEADLINE_R2


def test_the_summary_reproduces_the_frozen_headline(summary: dict) -> None:
    check = summary["reproduction_check"]
    assert check["reproduced"] is True
    assert check["abs_delta"] <= 1e-09
    assert check["observed_r2"] == pytest.approx(probe.HEADLINE_R2, abs=1e-09)
    assert int(check["seed"]) == probe.FROZEN_SEED


def test_both_scoreboards_are_reported_for_every_rule(summary: dict) -> None:
    endpoint = summary["endpoint"]
    assert set(endpoint) >= {"global", "D1", "D2", "D3"}
    assert endpoint["global"]["all"]["r2_mean"] is not None
    for rule in ("D1", "D2", "D3"):
        for scope in ("in_domain", "out_of_domain"):
            assert endpoint[rule][scope] is not None, (rule, scope)
    for item in summary["per_seed"]:
        assert item["rules"]["global"]["all"]["r2_mean"] is not None
        for rule in ("D1", "D2", "D3"):
            assert item["rules"][rule]["in_domain"]["rows_mean"] > 0
    compare = summary["headline_vs_in_domain"]
    assert compare["global_endpoint_r2"] == pytest.approx(
        endpoint["global"]["all"]["r2_mean"], abs=1e-12
    )
    assert "不得替换或提升为主记分牌读数" in compare["never_a_headline"]


def test_the_report_prints_the_global_reading_next_to_the_domain_reading() -> None:
    text = probe.REPORT_PATH.read_text(encoding="utf-8")
    assert "全域（无域声明）" in text
    assert "域内" in text and "域外" in text
    assert "域内数不得当作达标题" in text
    assert "0.4766400383507876" in text


def test_rule_d1_is_recomputed_from_features_only(scoreboard: dict, summary: dict) -> None:
    flags = probe.d1_out_of_domain(scoreboard)
    scored = [
        str(row["inchikey"])
        for row, is_scored in zip(scoreboard["rows"], scoreboard["scored"], strict=True)
        if bool(is_scored)
    ]
    assert set(flags) == set(scored)
    roster = sorted(key for key, flag in flags.items() if flag)
    assert roster == summary["domain_rules"]["D1"]["out_of_domain_compounds"]
    assert probe.D1_MIN_TPSA == 20.0 and probe.D1_MIN_HBD == 1
    assert summary["domain_rules"]["D1"]["definition"] == (
        "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0"
    )


def test_rule_d3_is_the_verified_roster_and_is_a_diagnostic(summary: dict, scoreboard: dict) -> None:
    scored = {
        str(row["inchikey"])
        for row, is_scored in zip(scoreboard["rows"], scoreboard["scored"], strict=True)
        if bool(is_scored)
    }
    assert set(probe.D3_KEYS) <= scored
    assert len(probe.D3_KEYS) == 7
    assert summary["domain_rules"]["D3"]["role"].startswith("diagnostic")
    assert summary["domain_rules"]["D3"]["keys"] == list(probe.D3_KEYS)


def test_rule_d2_reads_only_the_training_side(summary: dict) -> None:
    rule = summary["domain_rules"]["D2"]
    assert "p95" in rule["definition"] and "training labels" in rule["definition"]
    assert set(rule["roster_per_seed"]) == {str(seed) for seed in probe.SEEDS}
    assert all(
        isinstance(int(value), int) and int(value) >= 0
        for value in rule["fallback_folds_per_seed"].values()
    )


def test_the_placebo_collapses(summary: dict) -> None:
    placebo = summary["placebo"]
    assert placebo["r2_mean"] < 0.25
    assert placebo["r2_mean"] < summary["endpoint"]["global"]["all"]["r2_mean"]
    assert placebo["floor_r2_mean"] is not None


def test_nothing_is_promoted(summary: dict) -> None:
    assert summary["promoted"] is False
    assert summary["verdict"] == "domain_split_reported"
    assert any("promoted 恒为 false" in item for item in summary["honest_boundaries"])


def test_the_repeats_table_lists_every_cell_lf_only(summary: dict) -> None:
    payload = probe.REPEATS_PATH.read_bytes()
    assert b"\r\n" not in payload
    assert not payload.startswith(b"\xef\xbb\xbf")
    lines = payload.decode("utf-8").splitlines()
    assert lines[0] == ",".join(probe.READING_COLUMNS)
    expected = len(summary["per_seed"]) * 8 + 8
    assert len(lines) == 1 + expected
    endpoints = [line for line in lines[1:] if line.startswith("endpoint,")]
    assert len(endpoints) == 8
