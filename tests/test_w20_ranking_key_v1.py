"""Literal pins for the Week 20 W20-3 ranking key v1 + intersection fill (AF-13).

Every number this file asserts is typed out here instead of re-derived from prose:
the example ordering, the exact example scores, the two collinearity correlations,
the applied-domain behaviour and the empty-front result.  A silent edit to the
module, the spec or the fill summary turns this file red instead of quietly
re-baselining the deliverable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes import w20_ranking_key_v1 as ranking

SPEC = REPOSITORY_ROOT / "reports" / "w20_ranking_key_v1_spec.md"
SECTION = REPOSITORY_ROOT / "reports" / "_w20_section_w203.md"
MODULE_PATH = REPOSITORY_ROOT / "probes" / "w20_ranking_key_v1.py"
PREREG = REPOSITORY_ROOT / "probes" / "w20_ranking_key_v1_prereg.json"
SUMMARY = REPOSITORY_ROOT / "probes" / "w20_ranking_key_v1_summary.json"
CANDIDATES = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_ranking_key_v1_candidates.csv"
TEST_PATH = Path(__file__)
NEW_FILES = (SPEC, SECTION, MODULE_PATH, TEST_PATH, SUMMARY, PREREG)

# The synthetic example under the shipped equal weights (0.5 / 0.5).
EXAMPLE_ORDER = ("demo-b", "demo-c", "demo-d", "demo-f", "demo-a", "demo-e")
EXAMPLE_SCORES = {
    "demo-b": 0.8285714285714287,
    "demo-c": 0.5,
    "demo-d": 0.5,
    "demo-f": 0.34285714285714286,
    "demo-a": None,
    "demo-e": None,
}
EXAMPLE_FRONT = ("demo-b", "demo-c", "demo-d")

# The same example after the weights move to HOMO 0.9 / LUMO 0.1: the order moves,
# so the weights are explicit and falsifiable rather than decorative.
HEAVY_HOMO_KEYS = (
    ranking.KeySpec(channel="homo", column="HOMO_eV", direction="min", weight=0.9),
    ranking.KeySpec(channel="lumo", column="LUMO_eV", direction="max", weight=0.1),
)
HEAVY_HOMO_ORDER = ("demo-d", "demo-b", "demo-f", "demo-c", "demo-a", "demo-e")
HEAVY_HOMO_SCORES = {
    "demo-d": 0.9,
    "demo-b": 0.8057142857142858,
    "demo-f": 0.3885714285714286,
    "demo-c": 0.1,
    "demo-a": None,
    "demo-e": None,
}

# The two on-record collinear pairs that may not be double-weighted.
COLLINEAR_PAIRS = (("HOMO_eV", "IP_eV", -0.9876), ("LUMO_eV", "EA_eV", -0.9513))

# Literals the lane report must keep, including the discipline block.
SPEC_LITERALS = (
    "排序键，不是候选生成器",
    "no_cost_ratio_evidence",
    "PREREG_WEIGHTS",
    "COLLINEARITY_RECORD",
    "−0.9876",
    "−0.9513",
    "HOMO_eV",
    "IP_eV",
    "LUMO_eV",
    "EA_eV",
    "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0",
    "HIGH_PERMITTIVITY_EPS",
    "homo+lumo",
    "rdkit_morgan_count_r2_2048+30_descriptors",
    "models/homo_lumo_homo.ubj@7e945fc5647f",
    "models/homo_lumo_lumo.ubj@9f6c2d6e6f86",
    "c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d",
    "0.8285714285714287",
    "0.8057142857142858",
    "0.34285714285714286",
    "0.3885714285714286",
    "115756",
    "0.45401075998423623",
    "0.524012313223719",
    "0.3198024498133034",
    "0.17477197208762",
    "0.4091179943351143",
    "0.4766400383507876",
    "31949",
    "29519",
    "0.349",
    "never subjected to a group-split audit",
    "CC-BY-NC-ND",
    "welded shut",
    "promoted",
    "reaxys_values_used",
)


def _by_name(rows: Any) -> dict[str, Any]:
    return {str(row["name"]): row for row in rows}


def test_the_example_ranking_is_pinned_literally() -> None:
    table = ranking.ranking_key_table(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    assert tuple(str(entry["name"]) for entry in table) == EXAMPLE_ORDER
    assert {str(entry["name"]): entry["score"] for entry in table} == EXAMPLE_SCORES


def test_the_example_front_is_pinned_literally() -> None:
    front = ranking.pareto_front(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    assert tuple(str(row["name"]) for row in front) == EXAMPLE_FRONT


def test_the_default_key_is_equal_weight_over_the_two_gated_channels() -> None:
    assert ranking.DEFAULT_WEIGHTS == {"homo": 0.5, "lumo": 0.5}
    assert tuple(spec.channel for spec in ranking.DEFAULT_KEYS) == ("homo", "lumo")
    assert tuple(spec.direction for spec in ranking.DEFAULT_KEYS) == ("min", "max")
    assert ranking.PREREG_WEIGHTS == ranking.DEFAULT_WEIGHTS
    assert ranking.PREREG_WEIGHTS_SOURCE == "no_cost_ratio_evidence"
    assert ranking.GATED_CHANNELS == ("homo", "lumo")


def test_out_of_domain_rows_get_no_score_at_all() -> None:
    table = ranking.ranking_key_table(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    by_name = _by_name(table)
    for name in ("demo-a", "demo-e"):
        entry = by_name[name]
        assert entry["domain"] == ranking.DOMAIN_OUT
        assert entry["score"] is None
        assert entry["rank"] is None
        assert entry["on_front"] is False
        assert entry["excluded_reason"] == ranking.DOMAIN_OUT
    # The two in-domain rows carry numbers; the out-of-domain rows carry nothing.
    assert isinstance(by_name["demo-b"]["score"], float)
    assert isinstance(by_name["demo-f"]["score"], float)


def test_a_rejected_row_cannot_move_a_kept_score() -> None:
    kept = [
        {"name": "kept-a", "HOMO_eV": -8.0, "LUMO_eV": 1.8, "NumHDonors": 1, "TPSA": 20.23},
        {"name": "kept-b", "HOMO_eV": -6.0, "LUMO_eV": 1.0, "NumHDonors": 2, "TPSA": 40.46},
    ]
    rejected = {
        "name": "rejected",
        "HOMO_eV": -9.0,
        "LUMO_eV": 0.0,
        "NumHDonors": 0,
        "TPSA": 9.23,
    }
    without = ranking.assign_scores(ranking.annotate_domains(kept))
    with_rejected = ranking.assign_scores(ranking.annotate_domains([*kept, rejected]))
    assert with_rejected[:2] == without
    assert with_rejected[2] is None


def test_an_out_of_domain_row_carries_no_order() -> None:
    rows = _by_name(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    with pytest.raises(ValueError, match="no order"):
        ranking.dominates(rows["demo-a"], rows["demo-b"])
    with pytest.raises(ValueError, match="no order"):
        ranking.dominates(rows["demo-b"], rows["demo-e"])


def test_the_collinearity_record_matches_the_on_record_correlations() -> None:
    recorded = {
        tuple(str(column) for column in record["columns"]): float(record["pearson_r"])
        for record in ranking.COLLINEARITY_RECORD
    }
    for first, second, correlation in COLLINEAR_PAIRS:
        assert recorded[(first, second)] == correlation
    assert ranking.DEDUP_KEPT_COLUMNS == ("HOMO_eV", "LUMO_eV")
    assert ranking.DEDUP_DROPPED_COLUMNS == ("IP_eV", "EA_eV")


def test_a_collinear_pair_may_not_be_counted_twice() -> None:
    with pytest.raises(ValueError, match="collinear"):
        ranking.validate_keys(
            (
                ranking.KeySpec("homo", "HOMO_eV", "min", 0.5),
                ranking.KeySpec("homo", "IP_eV", "min", 0.5),
            )
        )
    with pytest.raises(ValueError, match="collinear"):
        ranking.validate_keys(
            (
                ranking.KeySpec("lumo", "LUMO_eV", "max", 0.5),
                ranking.KeySpec("lumo", "EA_eV", "max", 0.5),
            )
        )


def test_an_ungated_or_unnormalised_key_is_refused() -> None:
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
    baseline = ranking.ranking_key_table(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    assert tuple(str(entry["name"]) for entry in baseline) == EXAMPLE_ORDER

    monkeypatch.setattr(ranking, "DEFAULT_KEYS", HEAVY_HOMO_KEYS)

    changed = ranking.ranking_key_table(ranking.annotate_domains(ranking.EXAMPLE_MOLECULES))
    changed_order = tuple(str(entry["name"]) for entry in changed)
    assert changed_order == HEAVY_HOMO_ORDER
    assert changed_order != EXAMPLE_ORDER
    assert {str(entry["name"]): entry["score"] for entry in changed} == HEAVY_HOMO_SCORES


def test_the_extension_register_is_consistent_with_disk() -> None:
    scan = ranking.scan_extension_verdicts()
    for channel, record in ranking.CHANNEL_EXTENSION_STATUS.items():
        assert bool(record["verdict_present"]) is bool(scan[channel]["verdict_present"])
        assert bool(record["merged"]) is (
            bool(record["verdict_present"]) and str(record["verdict"]) == "passed"
        )
        assert str(record["condition"]).strip()
    # A verdict artefact the module was not told about must not widen the key.
    ranking.assert_no_unregistered_verdicts()
    # Either way the shipped key still stands on the two gated orbital channels.
    assert ranking.ELIGIBLE_CHANNELS == ("homo", "lumo")
    assert tuple(ranking.DEFAULT_WEIGHTS) == ("homo", "lumo")


def test_the_fill_summary_records_the_empty_front() -> None:
    payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
    fill = payload["fill"]
    assert fill["candidates_in_file"] == 115756
    assert fill["candidates_read"] == 115756
    assert fill["smiles_invalid"] == 0
    assert fill["unique_inchikey"] == 115756
    assert fill["duplicate_inchikey_rows"] == 0
    assert fill["in_domain"] == 0
    assert fill["out_of_domain"] == 115756
    assert fill["out_of_domain_share"] == 1.0
    assert fill["scoreable_on_key_dimensions_rows"] == 0
    assert fill["front_size"] == 0
    assert fill["top_20"] == []
    assert fill["key_dimensions"] == ["HOMO_eV", "LUMO_eV"]
    assert fill["core_channels_filled"] == ["orbitals"]


def test_the_summary_carries_the_discipline_block() -> None:
    payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
    discipline = payload["discipline"]
    assert discipline["promoted"] is False
    assert discipline["main_scoreboard_attempts_this_week"] == 0
    assert discipline["main_scoreboard_attempts_cumulative"] == 11
    assert discipline["predictions_written_to_any_pool"] is False
    assert discipline["reaxys_values_used"] is False
    assert "0.349" in str(discipline["generation_loop"])
    assert payload["position_en"] == "this is a ranking key, not a candidate generator"


def test_the_candidate_csv_carries_the_sixteen_column_contract() -> None:
    with CANDIDATES.open(encoding="utf-8", newline="") as handle:
        header = handle.readline().rstrip("\n")
    assert header == ",".join(ranking.CANDIDATE_COLUMNS)
    assert header.count(",") == 15
    assert header.startswith("inchikey,smiles,canonical_smiles,source_line")
    assert header.endswith("excluded_reason,provenance")


def test_the_module_exports_the_documented_api() -> None:
    for name in (
        "CHANNEL_EXTENSION_STATUS",
        "CANDIDATE_COLUMNS",
        "COLLINEARITY_RECORD",
        "DEFAULT_KEYS",
        "DEFAULT_WEIGHTS",
        "DEDUP_DROPPED_COLUMNS",
        "DEDUP_KEPT_COLUMNS",
        "DOMAIN_IN",
        "DOMAIN_OUT",
        "ELIGIBLE_CHANNELS",
        "EXAMPLE_MOLECULES",
        "GATED_CHANNELS",
        "HIGH_PERMITTIVITY_EPS",
        "KeySpec",
        "annotate_domains",
        "assign_scores",
        "build_default_keys",
        "classify_domain",
        "d1_in_domain",
        "dominates",
        "fill_candidates",
        "high_permittivity_excluded",
        "pareto_front",
        "ranking_key_table",
        "scan_extension_verdicts",
        "validate_keys",
        "write_candidate_csv",
    ):
        assert name in ranking.__all__
        assert hasattr(ranking, name)


def test_the_spec_keeps_every_pinned_literal() -> None:
    text = SPEC.read_text(encoding="utf-8")
    missing = [literal for literal in SPEC_LITERALS if literal not in text]
    assert missing == []


def test_the_spec_states_the_three_locked_rules() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert "不得重复计权" in text
    assert "域外" in text
    assert "等权" in text
    assert "不给分" in text


def test_the_section_file_opens_with_its_heading() -> None:
    first_line = SECTION.read_text(encoding="utf-8").split("\n", 1)[0]
    assert first_line.startswith("## 28.59 ")
    assert first_line.endswith("（2026-09-28）")


def test_the_new_files_are_lf_without_bom() -> None:
    for path in NEW_FILES:
        payload = path.read_bytes()
        assert payload, str(path)
        assert not payload.startswith(b"\xef\xbb\xbf"), str(path)
        assert b"\r\n" not in payload, str(path)
