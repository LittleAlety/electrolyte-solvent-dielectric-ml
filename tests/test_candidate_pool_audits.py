# -*- coding: utf-8 -*-
"""B-G0-J02A / J02B / J01K 的反例测试集.

纪律与 J01 一致: 每个失败用例都对应一种"看起来对、其实会放宽结论"的写法.
测试调用生产代码的同一函数, 不在测试里重写判定.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "confirm_2027"))

import audit_candidate_exclusion as A  # noqa: E402
import audit_candidate_pool_lineage as L  # noqa: E402
import audit_temperature_band as K  # noqa: E402

WORKSPACE = REPOSITORY_ROOT.parent
REAL_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "intersections"


def _windows() -> list[dict[str, object]]:
    return [
        {"name": "room_temperature", "low": 293.15, "high": 303.15},
        {"name": "extended_temperature", "low": 313.15, "high": 323.15},
        {"name": "high_temperature", "low": 333.15, "high": 373.15},
    ]


# ===========================================================================
# J02A: 三值裁决
# ===========================================================================

def _gap(**overrides: str) -> dict[str, str]:
    base = {
        "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N",
        "measurement_id": "EPSV04-R001",
        "source_group": "10.1/src",
        "T_K": "298.15",
        "epsilon": "7.0695",
        "measurement_decision": "HOLD",
        "qc_reason": "",
    }
    base.update(overrides)
    return base


def _obs(t: str = "298.15", eps: str = "7.0695", **overrides: str) -> dict[str, str]:
    base = {
        "inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N",
        "T_K": t,
        "epsilon": eps,
        "phase": "Liquid",
        "frequency_mhz": "0",
        "pressure_kpa": "101.325",
        "source_doi": "10.1/src",
        "temperature_band": "room_temperature",
    }
    base.update(overrides)
    return base


def test_exact_match_requires_one_observation() -> None:
    result = A.match_observations(_gap(), [_obs()])
    assert result["n_exact"] == 1
    assert result["n_on_key"] == 1


def test_two_observations_break_the_unique_rule() -> None:
    """同一键上命中同一条观测的两次转录 -> 冻结的"恰好一条"规则判否, 不得挑一条."""
    result = A.match_observations(_gap(), [_obs(), _obs(source_file="copy.xml")])
    assert result["n_exact"] == 2
    assert result["n_on_key"] == 2


def test_temperature_tolerance_is_not_widened() -> None:
    """295.65 与 298.15 差 2.5 K, 远超 0.01 K 容差 -> 必须算不匹配."""
    result = A.match_observations(_gap(T_K="295.65"), [_obs(t="298.15"), _obs(t="293.15")])
    assert result["n_exact"] == 0
    assert result["nearest"]


def test_epsilon_tolerance_is_not_widened() -> None:
    """7.798 与 7.78 差 0.018, 超过 1e-6 -> 必须算不匹配 (TEGDME 实例)."""
    result = A.match_observations(_gap(epsilon="7.798"), [_obs(eps="7.78")])
    assert result["n_exact"] == 0
    assert result["nearest"][0][1] > A.EPS_TOL


def test_mechanical_failure_alone_allows_v2_construction() -> None:
    match = A.match_observations(_gap(T_K="295.65"), [_obs(t="298.15")])
    decision = A.classify_exclusion(
        match=match,
        backfill_row={"status": "UNRESOLVED", "reason": "0 candidate"},
        gap_row=_gap(T_K="295.65"),
        in_pool_c=False,
        in_preview=False,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": False, "is_cross_source_aggregate": False,
                     "n_contributing_sources": 1, "aggregation_documented": True},
    )
    assert decision["verdict"] == A.VERDICT_MISSING
    assert decision["is_mechanical"] is True


def test_cross_source_aggregate_forces_human_review() -> None:
    """gap 的 epsilon 是 4 个来源的中位数 -> 归属不可辨识, 不得判为可补建."""
    match = A.match_observations(_gap(epsilon="46.05"), [_obs(eps="49.0")])
    decision = A.classify_exclusion(
        match=match,
        backfill_row=None,
        gap_row=_gap(epsilon="46.05"),
        in_pool_c=False,
        in_preview=True,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": True, "is_cross_source_aggregate": True,
                     "n_contributing_sources": 4, "aggregation_documented": True},
    )
    assert decision["verdict"] == A.VERDICT_HUMAN
    assert decision["is_mechanical"] is False
    assert "GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE" in decision["exclusion_reason"]
    assert "MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION" in decision["exclusion_reason"]


def test_within_source_band_median_is_not_called_cross_source() -> None:
    """单来源带内中位数与跨来源聚合后果不同, 不得混标."""
    decision = A.classify_exclusion(
        match=A.match_observations(_gap(), [_obs()]),
        backfill_row=None,
        gap_row=_gap(),
        in_pool_c=False,
        in_preview=False,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": True, "is_cross_source_aggregate": False,
                     "n_contributing_sources": 1, "aggregation_documented": True},
    )
    assert decision["verdict"] == A.VERDICT_HUMAN
    assert "GAP_EPSILON_IS_WITHIN_SOURCE_BAND_MEDIAN" in decision["exclusion_reason"]
    assert "GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE" not in decision["exclusion_reason"]


def test_undocumented_aggregation_forces_human_review() -> None:
    decision = A.classify_exclusion(
        match=A.match_observations(_gap(), [_obs()]),
        backfill_row=None,
        gap_row=_gap(),
        in_pool_c=False,
        in_preview=False,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": False, "is_cross_source_aggregate": False,
                     "n_contributing_sources": 2, "aggregation_documented": False},
    )
    assert decision["verdict"] == A.VERDICT_HUMAN
    assert "GAP_SOURCE_PROVENANCE_UNDOCUMENTED" in decision["exclusion_reason"]


def test_evidence_fails_gate_is_not_mechanical() -> None:
    decision = A.classify_exclusion(
        match=A.match_observations(_gap(), [_obs()]),
        backfill_row={"status": "EVIDENCE_FAILS_GATE", "reason": "A5=False"},
        gap_row=_gap(),
        in_pool_c=False,
        in_preview=False,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": False, "is_cross_source_aggregate": False,
                     "n_contributing_sources": 1, "aggregation_documented": True},
    )
    assert decision["verdict"] == A.VERDICT_HUMAN
    assert "EVIDENCE_FAILS_A5_A6_A7" in decision["exclusion_reason"]


def test_resolved_but_absent_from_pool_is_internal_inconsistency() -> None:
    decision = A.classify_exclusion(
        match=A.match_observations(_gap(), [_obs()]),
        backfill_row={"status": "RESOLVED", "reason": ""},
        gap_row=_gap(),
        in_pool_c=False,
        in_preview=False,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
        aggregation={"is_aggregate": False, "is_cross_source_aggregate": False,
                     "n_contributing_sources": 1, "aggregation_documented": True},
    )
    assert decision["verdict"] == A.VERDICT_HUMAN
    assert "RESOLVED_BUT_ABSENT_FROM_POOL_C" in decision["exclusion_reason"]


def test_present_in_pool_c_is_not_an_exclusion() -> None:
    decision = A.classify_exclusion(
        match=A.match_observations(_gap(), [_obs()]),
        backfill_row={"status": "RESOLVED", "reason": ""},
        gap_row=_gap(),
        in_pool_c=True,
        in_preview=True,
        window_band_of_gap="room_temperature",
        observation_band_of_nearest="room_temperature",
    )
    assert decision["verdict"] is None
    assert decision["exclusion_reason"] == "NOT_EXCLUDED_PRESENT_IN_POOL_C"


def test_only_three_verdicts_exist() -> None:
    allowed = {A.VERDICT_INTENTIONAL, A.VERDICT_MISSING, A.VERDICT_HUMAN}
    assert allowed == {
        "INTENTIONAL_EXCLUSION",
        "CANDIDATE_CONSTRUCTION_MISSING",
        "REQUIRES_HUMAN_REVIEW",
    }


def test_only_missing_allows_v2_in_summary() -> None:
    rows = [
        {"review_order": "1", "a_mol_id": "C01", "a_name": "A", "observation_id": "R1",
         "candidate_pool_C": "false", "master_preview": "false", "temperature_raw_K": "298.15",
         "temperature_band_protocol": "room_temperature", "backfill_status": "UNRESOLVED",
         "verdict": A.VERDICT_MISSING, "exclusion_reason": "MEASUREMENT_NOT_IN_DECLARED_LIST"},
        {"review_order": "2", "a_mol_id": "C02", "a_name": "B", "observation_id": "R2",
         "candidate_pool_C": "false", "master_preview": "true", "temperature_raw_K": "298.15",
         "temperature_band_protocol": "room_temperature", "backfill_status": "UNRESOLVED",
         "verdict": A.VERDICT_HUMAN, "exclusion_reason": "GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE"},
    ]
    summary = A.build_summary(rows)
    by_id = {m["a_mol_id"]: m for m in summary["molecules"]}
    assert by_id["C01"]["pool_c_v2_construction_allowed"] is True
    assert by_id["C02"]["pool_c_v2_construction_allowed"] is False
    assert summary["verdict_counts"][A.VERDICT_MISSING] == 1
    assert summary["verdict_counts"][A.VERDICT_HUMAN] == 1


# ===========================================================================
# J02B: 两值裁决
# ===========================================================================

def _checks(**statuses: str) -> list[dict[str, str]]:
    base = {
        "master_in_49_preview_upstream_is_s4_preview": "PASS",
        "candidate_pool_C_upstream_is_evidence_backfill": "PASS",
        "candidate_pool_C_does_not_read_preview": "PASS",
    }
    base.update(statuses)
    return [{"check": name, "status": status, "detail": ""} for name, status in base.items()]


def _diff(preview_only: int = 26, pool_only: int = 26) -> dict[str, object]:
    relation = ("neither_subset" if preview_only and pool_only
                else "preview_subset_pool_c" if not preview_only
                else "pool_c_subset_preview")
    return {"n_preview_only": preview_only, "n_pool_c_only": pool_only,
            "n_common": 23, "is_subset_relation": relation}


def test_historical_decision_when_upstreams_differ_and_not_nested() -> None:
    decision = L.decide(_checks(), _diff(), pool_c_status="CURRENT_AUTHORITATIVE_OPERATIONAL_POOL")
    assert decision["decision"] == L.DECISION_HISTORICAL
    assert decision["preview_classification"] == "LEGACY_OR_UNRESOLVED_PREVIEW"
    assert decision["merge_forbidden"] is True


def test_rewrite_decision_when_pool_reads_preview() -> None:
    """若能证明 pool 生成器读了 preview, 就不再是"两个对象", 必须改判."""
    decision = L.decide(
        _checks(candidate_pool_C_does_not_read_preview="FAIL"), _diff(),
        pool_c_status="CURRENT_AUTHORITATIVE_OPERATIONAL_POOL",
    )
    assert decision["decision"] == L.DECISION_REWRITE
    assert decision["preview_classification"] == "STALE_MIRROR_OF_POOL_C"


def test_rewrite_decision_when_nested() -> None:
    """如果一个池是另一个的子集, "两个不同对象"的解释不成立."""
    decision = L.decide(_checks(), _diff(preview_only=0, pool_only=26),
                        pool_c_status="CURRENT_AUTHORITATIVE_OPERATIONAL_POOL")
    assert decision["decision"] == L.DECISION_REWRITE


def test_rewrite_decision_when_same_upstream() -> None:
    decision = L.decide(
        _checks(candidate_pool_C_upstream_is_evidence_backfill="FAIL"), _diff(),
        pool_c_status="CURRENT_AUTHORITATIVE_OPERATIONAL_POOL",
    )
    assert decision["decision"] == L.DECISION_REWRITE


def test_only_two_decisions_exist() -> None:
    assert {L.DECISION_HISTORICAL, L.DECISION_REWRITE} == {
        "PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE",
        "PREVIEW_SHOULD_REFLECT_CURRENT_POOL_C_FIX_UPSTREAM_AND_RERUN",
    }


def test_membership_diff_never_reports_union_as_a_pool() -> None:
    rows = [
        {"skeleton": "AAA", "in_49_preview": "true", "in_candidate_pool_C": "true",
         "membership_class": "IN_BOTH"},
        {"skeleton": "BBB", "in_49_preview": "true", "in_candidate_pool_C": "false",
         "membership_class": "PREVIEW_ONLY"},
        {"skeleton": "CCC", "in_49_preview": "false", "in_candidate_pool_C": "true",
         "membership_class": "POOL_C_ONLY"},
    ]
    diff = L.build_membership_diff(rows)
    assert diff["n_common"] == 1
    assert diff["n_preview_only"] == 1
    assert diff["n_pool_c_only"] == 1
    assert diff["n_union"] == 3
    assert diff["is_subset_relation"] == "neither_subset"
    # 并集只是统计量, 不是池
    assert "n_union" in diff and "union_pool" not in diff


# ===========================================================================
# J01K: 温度分带双字段
# ===========================================================================

@pytest.mark.parametrize(
    "temperature,expected",
    [
        (293.15, "room_temperature"),
        (303.15, "room_temperature"),
        (313.15, "extended_temperature"),
        (323.15, "extended_temperature"),
        (333.15, "high_temperature"),
        (373.15, "high_temperature"),
    ],
)
def test_room_band_bounds_stay_inclusive(temperature: float, expected: str) -> None:
    """293.15 与 303.15 必须仍是闭区间 —— 这条测试不能被删."""
    assert K.band_of(temperature, _windows()) == expected


def test_303_16_is_outside_room_band() -> None:
    assert K.band_of(303.16, _windows()) == "outside_declared_window"


def test_missing_temperature_not_defaulted() -> None:
    assert K.band_of(None, _windows()) == "temperature_missing"


def test_high_temperature_vocabulary_gap_is_not_a_rule_conflict() -> None:
    """v11 枚举缺 high_temperature, 不得把这种覆盖差异说成两套规则给出相反结论."""
    band = K.reconcile_band("outside_declared_window", "high_temperature")
    assert band == "VOCABULARY_GAP_HIGH_TEMPERATURE_NOT_IN_V11_ENUM"
    assert "DISAGREE" not in band


def test_agree_is_named_agree() -> None:
    assert K.reconcile_band("room_temperature", "room_temperature") == "AGREE"
    assert K.reconcile_band("outside_declared_window", "outside_declared_window") == "AGREE"


def test_v11_vocabulary_has_no_high_temperature() -> None:
    assert "high_temperature" not in K.V11_BAND_VOCABULARY
    assert set(K.V11_BAND_VOCABULARY) == {
        "room_temperature", "extended_temperature", "outside_declared_window"
    }


def _band_row(temperature: float, *, mol: str = "C18", name: str = "SN") -> dict[str, str]:
    dataset = {
        "a18_by_skeleton": {
            "IAHFWCOBPZCAEA": {"a_mol_id": mol, "a_name": name},
        },
        "observations": [{
            "inchikey": "IAHFWCOBPZCAEA-UHFFFAOYSA-N",
            "T_K": str(temperature),
            "epsilon": "56.09",
            "phase": "Liquid",
            "frequency_mhz": "0",
            "pressure_kpa": "101.325",
            "source_doi": "10.1021/je300958c",
            "temperature_band": "outside_declared_window",
            "observation_id": f"row-{temperature}",
        }],
    }
    return K.build_reconciliation(dataset, _windows())[0]


def test_sn_333_15_is_not_counted_as_room_band() -> None:
    row = _band_row(333.15)
    assert row["counts_as_room_band_qualified"] == "false"
    assert row["in_room_band_protocol"] == "false"
    assert row["is_sn_333_15_boundary_case"] == "true"


def test_sn_333_15_is_not_deleted() -> None:
    row = _band_row(333.15)
    assert row["temperature_raw_K"] == "333.15"
    assert "ORIGINAL_TEMPERATURE_NOT_ALTERED" in row["evidence_note"]
    assert "SN_333_15_RETAINED_NOT_COUNTED_AS_ROOM_BAND" in row["evidence_note"]


def test_both_band_fields_are_kept_side_by_side() -> None:
    row = _band_row(333.15)
    assert row["temperature_band_v11"] == "outside_declared_window"
    assert row["temperature_band_protocol"] == "high_temperature"
    assert row["temperature_band_reconciliation"] in (
        "VOCABULARY_GAP_HIGH_TEMPERATURE_NOT_IN_V11_ENUM", "DISAGREE_OTHER"
    )
    # 两个字段都在, 且互不覆盖
    assert row["temperature_band_v11"] != row["temperature_band_protocol"]


def test_room_band_row_is_counted() -> None:
    row = _band_row(298.15, mol="C01", name="DMC")
    row = dict(row)
    row["observation_id"] = "x"
    dataset = {
        "a18_by_skeleton": {"IAHFWCOBPZCAEA": {"a_mol_id": "C01", "a_name": "DMC"}},
        "observations": [{
            "inchikey": "IAHFWCOBPZCAEA-UHFFFAOYSA-N", "T_K": "298.15", "epsilon": "3.134",
            "phase": "Liquid", "frequency_mhz": "0", "pressure_kpa": "101.325",
            "source_doi": "10.1/a", "temperature_band": "room_temperature",
            "observation_id": "r1",
        }],
    }
    out = K.build_reconciliation(dataset, _windows())[0]
    assert out["counts_as_room_band_qualified"] == "true"
    assert out["is_sn_333_15_boundary_case"] == "false"


# ===========================================================================
# 真实输入集成检查
# ===========================================================================

def _paths() -> dict[str, Path]:
    return A.locate_inputs(WORKSPACE, None)


@pytest.fixture(scope="module")
def j02a_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if any(not Path(p).is_file() for p in _paths().values()):
        pytest.skip("权威输入不在本机")
    out = tmp_path_factory.mktemp("j02a")
    assert A.run(workspace=WORKSPACE, a_repo=None, out_dir=out, check=False) == 0
    return {n: (out / n).read_bytes() for n in A.OUTPUT_FILES}


def test_real_j02a_all_four_require_human_review(j02a_files: dict[str, bytes]) -> None:
    summary = json.loads(j02a_files["j02a_exclusion_summary.json"].decode("utf-8"))
    assert summary["verdict_counts"][A.VERDICT_MISSING] == 0
    assert summary["verdict_counts"][A.VERDICT_HUMAN] == 4
    for entry in summary["molecules"]:
        assert entry["verdict"] == A.VERDICT_HUMAN
        assert entry["pool_c_v2_construction_allowed"] is False


def test_real_j02a_targets_are_the_four_named(j02a_files: dict[str, bytes]) -> None:
    summary = json.loads(j02a_files["j02a_exclusion_summary.json"].decode("utf-8"))
    assert {m["a_mol_id"] for m in summary["molecules"]} == {"C08", "C10", "C13", "C15"}
    assert {m["a_name"] for m in summary["molecules"]} == {"DME", "TEGDME", "GBL", "DMSO"}


def test_real_j02a_gbl_is_single_source_median(j02a_files: dict[str, bytes]) -> None:
    rows = list(csv.DictReader(io.StringIO(
        j02a_files["candidate_exclusion_reconciliation.csv"].decode("utf-8"))))
    gbl = [r for r in rows if r["a_mol_id"] == "C13"][0]
    assert gbl["aggregation_is_aggregate"] == "true"
    assert gbl["aggregation_is_cross_source"] == "false"
    assert gbl["n_contributing_sources"] == "1"


def test_real_j02a_dmso_is_cross_source(j02a_files: dict[str, bytes]) -> None:
    rows = list(csv.DictReader(io.StringIO(
        j02a_files["candidate_exclusion_reconciliation.csv"].decode("utf-8"))))
    dmso = [r for r in rows if r["a_mol_id"] == "C15"][0]
    assert dmso["aggregation_is_cross_source"] == "true"
    assert int(dmso["n_contributing_sources"]) >= 2


def test_real_j02b_decision_is_historical(j02a_files: dict[str, bytes]) -> None:
    del j02a_files
    paths = L.locate_inputs(WORKSPACE, None)
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    manifest = L.build_inputs_manifest(paths, L.collect_environment())
    files = L.build_outputs(paths, manifest=manifest)
    decision = json.loads(files["pool_version_decision.json"].decode("utf-8"))
    assert decision["decision"] == L.DECISION_HISTORICAL
    assert decision["membership_summary"]["n_common"] == 23
    assert decision["membership_summary"]["n_preview_only"] == 26
    assert decision["membership_summary"]["n_pool_c_only"] == 26
    assert decision["membership_summary"]["n_union"] == 75
    assert decision["merge_forbidden"] is True


def test_real_j02b_lineage_checks_all_pass(j02a_files: dict[str, bytes]) -> None:
    del j02a_files
    paths = L.locate_inputs(WORKSPACE, None)
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    checks = L.static_source_evidence(paths)
    assert all(c["status"] == "PASS" for c in checks)


def test_real_j01k_sn_is_preserved_and_excluded(j02a_files: dict[str, bytes]) -> None:
    del j02a_files
    paths = K.locate_inputs(WORKSPACE, None)
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    dataset = K.load_dataset(paths)
    windows = list(dataset["protocol"]["allowed_temperature_windows_K"])
    rows = K.build_reconciliation(dataset, windows)
    summary = K.build_summary(rows, windows)
    sn = summary["sn_333_15"]
    assert sn["n_rows"] == 1
    assert sn["counts_as_room_band_qualified"] is False
    assert sn["temperature_preserved"] is True
    assert sn["rows_retained_not_deleted"] is True
    assert summary["disagreement_kind"] == "VOCABULARY_COVERAGE_NOT_RULE_CONFLICT"
    assert "high_temperature" in summary["vocabulary_missing_in_v11"]


def test_real_j01_frozen_outputs_untouched() -> None:
    """J02A/J02B/J01K 不得改动 B-G0-J01 的冻结产物."""
    frozen = ("joint_go_nogo.json", "joint_eligibility.csv")
    if not all((REAL_OUT / n).is_file() for n in frozen):
        pytest.skip("J01 产物不存在")
    go_nogo = json.loads((REAL_OUT / "joint_go_nogo.json").read_text(encoding="utf-8"))
    assert go_nogo["verdict"] == "NO_GO_INSUFFICIENT_ELIGIBLE_DATA"
    assert go_nogo["input_contract_version"] == "confirm_2027.joint_inputs/v1"
    denominators = go_nogo["denominators"]
    assert denominators["n_condition_resolvable"] == 4
    assert denominators["n_room_band_qualified"] == 3
    assert denominators["n_admitted"] == 0


def test_all_three_audits_rebuild_byte_identically(j02a_files: dict[str, bytes],
                                                   tmp_path: Path) -> None:
    del j02a_files
    for module in (A, L, K):
        paths = module.locate_inputs(WORKSPACE, None)
        if any(not Path(p).is_file() for p in paths.values()):
            pytest.skip("权威输入不在本机")
        assert module.run(workspace=WORKSPACE, a_repo=None, out_dir=REAL_OUT, check=True) == 0
