# -*- coding: utf-8 -*-
"""B-G0-J03 聚合来源可追溯性检查器的反例测试集.

纪律: 每个失败用例都对应一种"看起来对、其实会让聚合值冒充原始观测"的写法.
测试调用生产代码的同一函数.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "confirm_2027"))

import audit_gap_aggregation_provenance as G  # noqa: E402

WORKSPACE = REPOSITORY_ROOT.parent
REAL_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "provenance_audit"


# ---------------------------------------------------------------------------
# 合成观测构造
# ---------------------------------------------------------------------------

def _obs(
    t: str,
    eps: str,
    *,
    source: str = "10.1/a",
    molecule: str = "AAAAAAAABBBBBB-UHFFFAOYSA-N",
    phase: str = "Liquid",
    frequency: str = "0",
    pressure: str = "101.325",
) -> dict[str, str]:
    return {
        "inchikey": molecule, "T_K": t, "epsilon": eps, "phase": phase,
        "frequency_mhz": frequency, "pressure_kpa": pressure, "source_doi": source,
    }


def _band(rows: list[dict[str, str]], molecule: str = "AAAAAAAABBBBBB-UHFFFAOYSA-N") -> list[dict]:
    return G.band_observations(rows, molecule)


def _recon(band: list[dict], declared: int | None) -> dict:
    return G.reconstruct_aggregation(band, declared)


def _decide(recon: dict, *, documented: bool = True, gap_dois: int = 1,
            n_sources: int = 1, lookup_ok: bool = True) -> dict[str, str]:
    return G.decide_verdict(
        aggregation_documented=documented,
        reconstruction=recon,
        gap_source_group_dois=gap_dois,
        n_contributing_sources=n_sources,
        lookup_ok=lookup_ok,
    )


# ===========================================================================
# 1. 单条原始观测能够准确回溯
# ===========================================================================

def test_single_observation_is_raw_and_traceable() -> None:
    band = _band([_obs("298.15", "3.134")])
    recon = _recon(band, 1)
    assert recon["n_band"] == 1
    assert recon["declared_n_matches"] is True
    assert recon["pair_present"] is True
    decision = _decide(recon)
    assert decision["verdict"] == G.V_RAW
    assert "NOT_DOCUMENTED" not in decision["reason"]


def test_single_observation_stays_raw_even_if_rule_undocumented() -> None:
    """窗口内恰好一条观测 = 聚合在事实上是恒等映射; 口径没写不改变这个事实.

    若因 aggregation_path=NOT_DOCUMENTED 就把它压成 UNDOCUMENTED, 那是让
    口径缺失冒充科学不确定, 会把最干净的行也关进 HOLD.
    """
    band = _band([_obs("298.15", "3.134")])
    decision = _decide(_recon(band, 1), documented=False)
    assert decision["verdict"] == G.V_RAW
    assert "MOOT_SINGLE_OBSERVATION" in decision["reason"]


# ===========================================================================
# 2. 同一来源多条测量不会被错误计为多个独立来源
# ===========================================================================

def test_same_source_multiple_measurements_is_one_source() -> None:
    band = _band([
        _obs("293.15", "42.34", source="10.1/a"),
        _obs("298.15", "41.64", source="10.1/a"),
        _obs("303.15", "41.10", source="10.1/a"),
    ])
    recon = _recon(band, 3)
    assert recon["n_band"] == 3
    assert len(recon["sources"]) == 1
    decision = _decide(recon, gap_dois=1, n_sources=1)
    assert decision["verdict"] == G.V_SINGLE


def test_same_doi_different_rows_still_one_source() -> None:
    """同一 DOI 的多条转录是重复, 不是独立证据."""
    band = _band([
        _obs("298.15", "46.05", source="10.1/x"),
        _obs("298.15", "46.05", source="10.1/x"),
        _obs("298.15", "46.051", source="10.1/x"),
    ])
    assert len(_recon(band, 3)["sources"]) == 1


# ===========================================================================
# 3. 多来源中位数能够识别全部贡献来源
# ===========================================================================

def test_multi_source_median_identifies_all_contributors() -> None:
    band = _band([
        _obs("293.15", "47.09", source="10.1/p"),
        _obs("298.00", "49.00", source="10.1/q"),
        _obs("298.15", "47.30", source="10.1/r"),
        _obs("303.15", "45.94", source="10.1/s"),
    ])
    recon = _recon(band, 4)
    assert set(recon["sources"]) == {"10.1/p", "10.1/q", "10.1/r", "10.1/s"}
    assert len(recon["sources"]) == 4


def test_multi_source_aggregate_is_flagged_as_multi() -> None:
    band = _band([
        _obs("298.15", "1.0", source="10.1/a"),
        _obs("298.15", "3.0", source="10.1/b"),
    ])
    recon = _recon(band, 2)
    assert len(recon["sources"]) == 2
    decision = _decide(recon, gap_dois=2, n_sources=2)
    # 两条观测但中位数不在任何一条上 -> 合成条件对优先
    assert decision["verdict"] in (G.V_MULTI, G.V_COMPOSITE)


def test_multi_source_with_matching_pair_is_multi() -> None:
    band = _band([
        _obs("298.15", "5.0", source="10.1/a"),
        _obs("298.15", "5.0", source="10.1/b"),
        _obs("298.15", "5.0", source="10.1/c"),
    ])
    recon = _recon(band, 3)
    assert recon["pair_present"] is True
    assert len(recon["sources"]) == 3
    decision = _decide(recon, gap_dois=1, n_sources=3)
    assert decision["verdict"] == G.V_MULTI
    assert "GAP_SOURCE_GROUP_DROPS_CONTRIBUTORS" in decision["reason"]


# ===========================================================================
# 4. 仅保存第一个 DOI 时, 不允许误判为单来源
# ===========================================================================

def test_gap_holding_first_doi_only_is_not_single_source() -> None:
    """DMSO 形态: gap 只写第一个 DOI, 但贡献来源有 4 个."""
    band = _band([
        _obs("293.15", "47.09", source="10.1/p"),
        _obs("298.00", "49.00", source="10.1/q"),
        _obs("298.15", "47.30", source="10.1/r"),
        _obs("303.15", "45.94", source="10.1/s"),
    ])
    recon = _recon(band, 4)
    decision = _decide(recon, documented=True, gap_dois=1, n_sources=4)
    # 无论最终落 MULTI 还是 COMPOSITE, 都绝不允许是 SINGLE 或 RAW
    assert decision["verdict"] not in (G.V_SINGLE, G.V_RAW)


def test_sources_are_rebuilt_from_contributors_not_from_gap() -> None:
    """来源必须从贡献观测重建; 从 gap 反推会得到错误的 1 个来源."""
    band = _band([
        _obs("298.15", "1.0", source="10.1/a"),
        _obs("298.15", "2.0", source="10.1/b"),
        _obs("298.15", "3.0", source="10.1/c"),
    ])
    recon = _recon(band, 3)
    assert len(recon["sources"]) == 3
    # gap 声明 1 个, 重建 3 个 -> 必须能被识别为丢失
    gap_dois = {"10.1/a"}
    assert set(recon["sources"]) - gap_dois == {"10.1/b", "10.1/c"}


# ===========================================================================
# 5. epsilon 中位数与温度中位数来自不同观测时, 禁止直接配对
# ===========================================================================

def test_medians_from_different_observations_forbid_pairing() -> None:
    """温度中位数与 epsilon 中位数分别计算, 可能落在不同观测上."""
    band = _band([
        _obs("293.15", "47.09", source="10.1/p"),
        _obs("298.15", "47.30", source="10.1/r"),
        _obs("303.15", "45.94", source="10.1/s"),
    ])
    recon = _recon(band, 3)
    # 温度中位数 298.15 在第二条; epsilon 中位数 47.09 在第一条
    assert recon["median_temperature"] == Decimal("298.15")
    assert recon["median_epsilon"] == Decimal("47.09")
    assert recon["pair_present"] is False
    decision = _decide(recon)
    assert decision["verdict"] == G.V_COMPOSITE
    assert "MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS" in decision["reason"]


def test_even_length_median_between_two_values_is_composite() -> None:
    """偶数条时中位数是两个值的均值, 不可能等于任何单条观测的 epsilon."""
    band = _band([
        _obs("298.15", "7.069", source="10.1/a"),
        _obs("298.15", "7.070", source="10.1/b"),
    ])
    recon = _recon(band, 2)
    assert recon["median_epsilon"] == Decimal("7.0695")
    assert recon["epsilon_median_present"] is False
    assert recon["pair_present"] is False
    assert _decide(recon)["verdict"] == G.V_COMPOSITE


def test_composite_beats_multi_source_in_priority() -> None:
    """合成条件对是更严重的问题, 不能被多来源标签掩盖."""
    band = _band([
        _obs("293.15", "1.0", source="10.1/a"),
        _obs("303.15", "3.0", source="10.1/b"),
    ])
    decision = _decide(_recon(band, 2), gap_dois=2, n_sources=2)
    assert decision["verdict"] == G.V_COMPOSITE


def test_exact_pair_present_allows_non_composite() -> None:
    band = _band([
        _obs("293.15", "41.0", source="10.1/a"),
        _obs("298.15", "42.0", source="10.1/a"),
        _obs("303.15", "43.0", source="10.1/a"),
    ])
    recon = _recon(band, 3)
    assert recon["median_temperature"] == Decimal("298.15")
    assert recon["median_epsilon"] == Decimal("42.0")
    assert recon["pair_present"] is True
    assert _decide(recon)["verdict"] == G.V_SINGLE


# ===========================================================================
# 6. NOT_DOCUMENTED 不得自动判定为单条原始观测
# ===========================================================================

def test_not_documented_with_multiple_observations_is_undocumented() -> None:
    band = _band([
        _obs("298.15", "5.0", source="10.1/a"),
        _obs("298.15", "5.0", source="10.1/b"),
    ])
    decision = _decide(_recon(band, 2), documented=False, n_sources=2)
    assert decision["verdict"] == G.V_UNDOCUMENTED
    assert decision["verdict"] in G.HOLD_VERDICTS


def test_undocumented_is_never_raw_with_multiple_rows() -> None:
    band = _band([
        _obs("298.15", "5.0", source="10.1/a"),
        _obs("303.15", "6.0", source="10.1/a"),
    ])
    decision = _decide(_recon(band, 2), documented=False)
    assert decision["verdict"] != G.V_RAW


# ===========================================================================
# 7. 缺失原始贡献清单时必须 HOLD
# ===========================================================================

def test_no_band_observations_is_incomplete_hold() -> None:
    recon = _recon([], 17)
    assert recon["n_band"] == 0
    decision = _decide(recon, documented=True)
    assert decision["verdict"] == G.V_INCOMPLETE
    assert decision["verdict"] in G.HOLD_VERDICTS


def test_declared_n_mismatch_is_surfaced() -> None:
    band = _band([_obs("298.15", "5.0")])
    recon = _recon(band, 99)
    assert recon["declared_n_matches"] is False


def test_single_observation_with_multiple_declared_sources_is_incomplete() -> None:
    band = _band([_obs("298.15", "5.0", source="10.1/a")])
    decision = _decide(_recon(band, 1), n_sources=3)
    assert decision["verdict"] == G.V_INCOMPLETE


def test_out_of_window_observations_are_not_counted() -> None:
    """窗口外的观测不参与重建 (SN 的 17 条全在 333.15 K 以上)."""
    band = _band([
        _obs("298.15", "5.0"),
        _obs("333.15", "56.09"),
        _obs("373.15", "47.11"),
    ])
    assert len(band) == 1


def test_non_liquid_and_rf_observations_excluded() -> None:
    band = _band([
        _obs("298.15", "5.0"),
        _obs("298.15", "6.0", phase="Gas"),
        _obs("298.15", "7.0", frequency="1"),
    ])
    assert len(band) == 1


# ===========================================================================
# 8. 输入变化能够触发版本失效
# ===========================================================================

def test_input_drift_is_detected(tmp_path: Path) -> None:
    target = tmp_path / "x.csv"
    target.write_bytes(b"a\n1\n")
    pins = {"x": (G.sha256_file(target), 4)}
    assert G.verify_pinned({"x": target}, pins) == []
    drifted = G.verify_pinned({"x": target}, {"x": ("0" * 64, 4)})
    assert len(drifted) == 1
    missing = G.verify_pinned({"x": tmp_path / "nope.csv"}, pins)
    assert missing[0]["actual"] == "FILE_MISSING"


def test_run_refuses_on_drift_and_writes_nothing(tmp_path: Path) -> None:
    paths = G.locate_inputs(WORKSPACE, None)
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    pins = dict(G.PINNED)
    pins["dielectric_v04"] = ("0" * 64, 134460)
    code = G.run(workspace=WORKSPACE, a_repo=None, out_dir=tmp_path, check=False, pins=pins)
    assert code == 3
    assert not (tmp_path / "gap_aggregation_audit.csv").exists()


# ===========================================================================
# 9. 输出能够逐字节重建
# ===========================================================================

def test_check_detects_mutated_and_missing(tmp_path: Path) -> None:
    files = {"a.json": b"1\n", "b.csv": b"x,y\n"}
    G.write_outputs(tmp_path, files)
    assert G.check_outputs(tmp_path, files) == []
    (tmp_path / "a.json").write_bytes(b"2\n")
    assert G.check_outputs(tmp_path, files) == ["不一致: a.json"]
    (tmp_path / "b.csv").unlink()
    assert "缺失: b.csv" in G.check_outputs(tmp_path, files)


def test_rendering_is_deterministic() -> None:
    left = G.render_json({"b": 1, "a": [2, 3]})
    right = G.render_json({"a": [2, 3], "b": 1})
    assert left == right
    csv_left = G.render_csv(("x", "y"), [{"x": "1", "y": "2"}])
    csv_right = G.render_csv(("x", "y"), [{"y": "2", "x": "1"}])
    assert csv_left == csv_right
    assert b"\r\n" not in csv_left


def test_decimal_median_is_exact_not_float_rounded() -> None:
    """7.069 与 7.070 的中位数必须是 7.0695, 不能被浮点吃掉精度."""
    band = _band([_obs("298.15", "7.069"), _obs("298.15", "7.070")])
    assert _recon(band, 2)["median_epsilon"] == Decimal("7.0695")


# ===========================================================================
# 裁决枚举与门控
# ===========================================================================

def test_six_verdicts_only() -> None:
    assert set(G.VERDICTS) == {
        "RAW_SINGLE_OBSERVATION",
        "SINGLE_SOURCE_AGGREGATE",
        "MULTI_SOURCE_AGGREGATE",
        "PROVENANCE_INCOMPLETE",
        "AGGREGATION_UNDOCUMENTED",
        "COMPOSITE_CONDITION_UNMATCHED",
    }


def test_verdict_gate_sets_do_not_overlap() -> None:
    assert G.PASSING_VERDICTS & G.HOLD_VERDICTS == set()
    assert G.PASSING_VERDICTS & G.REVIEW_VERDICTS == set()
    assert G.HOLD_VERDICTS & G.REVIEW_VERDICTS == set()
    assert (G.PASSING_VERDICTS | G.HOLD_VERDICTS | G.REVIEW_VERDICTS) == set(G.VERDICTS)


def test_every_verdict_has_downstream_action() -> None:
    band = _band([_obs("298.15", "5.0")])
    cases = [
        _decide(_recon(band, 1)),                                        # RAW
        _decide(_recon(_band([_obs("298.15", "5.0", source="10.1/a"),
                              _obs("303.15", "6.0", source="10.1/a")]), 2)),  # COMPOSITE
        _decide(_recon([], 1)),                                          # INCOMPLETE
        _decide(_recon(_band([_obs("298.15", "5.0", source="10.1/a"),
                              _obs("298.15", "6.0", source="10.1/b")]), 2),
                documented=False, n_sources=2),                          # UNDOCUMENTED
    ]
    for case in cases:
        assert case["action"]
        assert case["verdict"] in G.VERDICTS


# ===========================================================================
# 真实输入集成检查
# ===========================================================================

def _paths() -> dict[str, Path]:
    return G.locate_inputs(WORKSPACE, None)


@pytest.fixture(scope="module")
def j03_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if any(not Path(p).is_file() for p in _paths().values()):
        pytest.skip("权威输入不在本机")
    out = tmp_path_factory.mktemp("j03")
    assert G.run(workspace=WORKSPACE, a_repo=None, out_dir=out, check=False) == 0
    return {n: (out / n).read_bytes() for n in G.OUTPUT_FILES}


def _audit_rows(files: dict[str, bytes]) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(
        files["gap_aggregation_audit.csv"].decode("utf-8"))))


def test_real_dmso_is_composite_with_four_sources(j03_files: dict[str, bytes]) -> None:
    rows = {r["measurement_id"]: r for r in _audit_rows(j03_files)}
    dmso = rows["EPSV04-R031"]
    assert dmso["a_mol_id"] == "C15"
    assert int(dmso["n_contributing_sources"]) == 4
    assert dmso["gap_source_group_doi_count"] == "1"
    assert dmso["pair_present_in_single_observation"] == "false"
    assert dmso["verdict"] in (G.V_COMPOSITE, G.V_MULTI)
    assert dmso["sources_lost_in_gap"] != G.NOT_EVALUATED


def test_real_dmc_and_dec_are_raw(j03_files: dict[str, bytes]) -> None:
    rows = {r["measurement_id"]: r for r in _audit_rows(j03_files)}
    for measurement_id in ("EPSV04-R032", "EPSV04-R056"):
        assert rows[measurement_id]["verdict"] == G.V_RAW
        assert rows[measurement_id]["pair_present_in_single_observation"] == "true"


def test_real_gbl_and_tegdme_are_composite(j03_files: dict[str, bytes]) -> None:
    rows = {r["measurement_id"]: r for r in _audit_rows(j03_files)}
    for measurement_id in ("EPSV04-R086", "EPSV04-R099"):
        assert rows[measurement_id]["verdict"] == G.V_COMPOSITE
        assert rows[measurement_id]["pair_present_in_single_observation"] == "false"


def test_real_sn_has_no_band_observations(j03_files: dict[str, bytes]) -> None:
    """SN 的 17 条观测全在 333.15 K 以上; 窗口内 0 条 -> INCOMPLETE, 不是删除."""
    rows = {r["measurement_id"]: r for r in _audit_rows(j03_files)}
    sn = rows["EPSV04-R247"]
    assert sn["in_band_n_observations"] == "0"
    assert sn["verdict"] == G.V_INCOMPLETE


def test_real_audit_covers_all_248_rows(j03_files: dict[str, bytes]) -> None:
    rows = _audit_rows(j03_files)
    assert len(rows) == 248
    assert len({r["measurement_id"] for r in rows}) == 248


def test_real_evidence_funnel_is_monotone(j03_files: dict[str, bytes]) -> None:
    feasibility = json.loads(j03_files["lookup_feasibility.json"].decode("utf-8"))
    chain = {s["stage"]: s["value"] for s in feasibility["evidence_funnel"]["chain"]}
    assert chain["N_database"] == 248
    assert chain["N_measurement"] > chain["N_database"]  # 聚合压缩
    assert chain["N_independent"] < chain["N_measurement"]  # 来源去重
    assert chain["N_condition_qualified"] <= chain["N_independent"] + 60
    assert chain["N_admitted"] == 0


def test_real_verdict_counts_sum_to_total(j03_files: dict[str, bytes]) -> None:
    feasibility = json.loads(j03_files["lookup_feasibility.json"].decode("utf-8"))
    counts = feasibility["evidence_funnel"]["verdict_counts"]
    assert sum(counts.values()) == 248
    assert set(counts) == set(G.VERDICTS)


def test_real_lookup_covers_all_sources_is_stricter_than_lookup_ok(
    j03_files: dict[str, bytes]
) -> None:
    """单键命中不等于可追溯全部来源 —— 这是本模块要传达的核心区分."""
    feasibility = json.loads(j03_files["lookup_feasibility.json"].decode("utf-8"))
    summary = feasibility["summary"]
    assert summary["n_lookup_ok"] >= summary["n_lookup_covers_all_sources"]


def test_real_rebuild_is_byte_identical(j03_files: dict[str, bytes], tmp_path: Path) -> None:
    G.write_outputs(tmp_path, j03_files)
    assert G.check_outputs(tmp_path, j03_files) == []


def test_committed_outputs_match_fresh_rebuild(tmp_path: Path) -> None:
    del tmp_path
    if not REAL_OUT.is_dir():
        pytest.skip("尚无已提交产物")
    if any(not Path(p).is_file() for p in _paths().values()):
        pytest.skip("权威输入不在本机")
    assert G.run(workspace=WORKSPACE, a_repo=None, out_dir=REAL_OUT, check=True) == 0


def test_j01_and_j02_frozen_outputs_untouched() -> None:
    """J03 不得改动 J01/J02 的冻结产物."""
    intersections = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "intersections"
    frozen = {
        "joint_go_nogo.json": "NO_GO_INSUFFICIENT_ELIGIBLE_DATA",
        "pool_version_decision.json": "PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE",
    }
    for name, expected in frozen.items():
        path = intersections / name
        if not path.is_file():
            pytest.skip(f"{name} 不存在")
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = "verdict" if "verdict" in payload else "decision"
        assert payload[key] == expected
    go_nogo = json.loads((intersections / "joint_go_nogo.json").read_text(encoding="utf-8"))
    assert go_nogo["denominators"]["n_condition_resolvable"] == 4
    assert go_nogo["denominators"]["n_room_band_qualified"] == 3
