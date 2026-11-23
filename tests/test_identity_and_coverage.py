# -*- coding: utf-8 -*-
"""B-G0-J05 身份冲突裁决与覆盖缺口登记的反例测试.

关键纪律:
  * 立体异构体是两个化合物, 不得被合并、平均或选代表;
  * 同一化合物同值同源才是重复登记;
  * "观测层没有" 不等于 "观测为 0";
  * 判决必须落到来源机制上, 不能凭文件是否存在.
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

import audit_identity_and_coverage as J  # noqa: E402

WORKSPACE = REPOSITORY_ROOT.parent
OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "identity_and_coverage"
REPAIR_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
INTERSECTIONS = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "intersections"


def _paths() -> dict[str, Path]:
    return J.locate_inputs(WORKSPACE, None)


def _present() -> bool:
    return all(Path(p).is_file() for p in _paths().values())


needs_inputs = pytest.mark.skipif(not _present(), reason="权威输入不在本机")


def _row(name: str, inchikey: str, eps: str, *, doi: str = "10.1/a",
         t: str = "298.15", conflict: str = "", flags: str = "zero_frequency") -> dict[str, str]:
    return {
        "name": name, "inchikey": inchikey, "smiles": "C", "T_K": t,
        "dielectric": eps, "source_doi": doi, "n_observations": "1",
        "gate_flags": flags, "conflict_status": conflict,
    }


# ===========================================================================
# J05-A 身份冲突裁决
# ===========================================================================

def test_stereoisomers_are_distinct_compounds_not_conflict() -> None:
    rows = [
        _row("cis-3-Hexene", "ZQDPJFUHLCOCRG-WAYWQWQTSA-N", "2.062"),
        _row("trans-3-Hexene", "ZQDPJFUHLCOCRG-AATRIKPKSA-N", "2.000"),
    ]
    verdict = J.classify_identity(rows)
    assert verdict["resolution"] == J.RES_ISOMER
    assert verdict["is_true_conflict"] is False
    assert verdict["stereo_difference"] is True
    assert verdict["distinct_full_inchikey"] == "2"
    assert "禁止按骨架合并或平均" in verdict["handling_rule"]


def test_same_compound_different_sources_is_true_conflict() -> None:
    rows = [
        _row("gamma-valerolactone", "GAEKPEKOJKCEMS-UHFFFAOYSA-N", "36.1",
             doi="10.1016/j.isci.2026.115778",
             conflict="unresolved_dual_row_review_table_36.1_vs_primary_si_36.9"),
        _row("gamma-valerolactone", "GAEKPEKOJKCEMS-UHFFFAOYSA-N", "36.9",
             doi="10.1016/j.ica.2021.120372",
             conflict="unresolved_dual_row_primary_si_36.9_vs_review_table_36.1"),
    ]
    verdict = J.classify_identity(rows)
    assert verdict["resolution"] == J.RES_CONFLICT
    assert verdict["is_true_conflict"] is True
    assert verdict["stereo_difference"] is False
    assert "人工裁决" in verdict["downstream_action"]


def test_identical_duplicate_entry_is_deduplicated() -> None:
    rows = [
        _row("methanol", "OKKJLVBELUTLKV-UHFFFAOYSA-N", "32.7"),
        _row("methanol", "OKKJLVBELUTLKV-UHFFFAOYSA-N", "32.7"),
    ]
    verdict = J.classify_identity(rows)
    assert verdict["resolution"] == J.RES_DUPLICATE
    assert verdict["is_true_conflict"] is False


def test_only_three_resolutions_exist() -> None:
    assert {J.RES_ISOMER, J.RES_CONFLICT, J.RES_DUPLICATE} == {
        "STEREOISOMER_DISTINCT_COMPOUNDS",
        "SAME_COMPOUND_SOURCE_CONFLICT",
        "SAME_COMPOUND_DUPLICATE_ENTRY",
    }


def test_same_value_different_sources_is_still_conflict_not_duplicate() -> None:
    """同值但不同来源 —— 不是重复登记, 需要分别保留以保留来源独立性."""
    rows = [
        _row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0", doi="10.1/a"),
        _row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0", doi="10.1/b"),
    ]
    verdict = J.classify_identity(rows)
    assert verdict["resolution"] == J.RES_CONFLICT


# ===========================================================================
# J05-B 覆盖缺口分类
# ===========================================================================

def test_nbs514_manual_entry_is_recoverable_not_lost() -> None:
    row = _row("benzene", "UHOVQNZJYSORNB-UHFFFAOYSA-N", "2.284",
               doi=J.NBS514_DOI,
               flags="zero_frequency|pure_component|experimental|literature_manual_entry|single_source|nbs514_circular_514")
    verdict = J.classify_source_mechanism(row)
    assert verdict["source_mechanism"] == "NBS514_CIRCULAR_MANUAL_ENTRY"
    assert verdict["recoverability"] == J.FIX_NBS514
    assert "机制性缺席" in verdict["recoverability_reason"]


def test_empty_gate_flags_is_not_claimed_recoverable() -> None:
    """gate_flags 为空时录入路径不明, 不得声称可修复."""
    row = _row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0", doi="10.1/unknown", flags="")
    verdict = J.classify_source_mechanism(row)
    assert verdict["source_mechanism"] == "UNFLAGGED_NO_OBSERVATION"
    assert verdict["recoverability"] == J.FIX_UNKNOWN
    assert "路径不明" in verdict["recoverability_reason"]


def test_thermoml_path_without_observation_is_pending_not_unknown() -> None:
    row = _row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0",
               doi="10.1/thermoml", flags="zero_frequency|pure_component|experimental")
    verdict = J.classify_source_mechanism(row)
    assert verdict["source_mechanism"] == "THERMOML_PATH_NO_OBSERVATION"
    assert verdict["recoverability"] == J.FIX_PENDING


def test_recoverability_values_are_distinct() -> None:
    values = {J.FIX_NBS514, J.FIX_MANUAL, J.FIX_PENDING, J.FIX_UNKNOWN}
    assert len(values) == 4


def test_missing_observation_is_not_zero() -> None:
    """观测层没有该分子时, 只能登记缺口, 不能写出 0 值行."""
    v04 = [_row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0",
                doi=J.NBS514_DOI, flags="literature_manual_entry")]
    obs: list[dict[str, str]] = []
    rows, summary = J.build_coverage_registry(v04, obs, {})
    assert len(rows) == 1
    assert rows[0]["v04_dielectric"] == "5.0"   # 原值逐字保留, 不规范化
    assert rows[0]["gap_status"] == "NO_OBSERVATION_IN_SOURCE_LAYER"
    assert rows[0]["has_observation"] == "false"
    # 没有伪造观测
    assert summary["n_rows_without_observation"] == 1


def test_molecule_with_observation_is_not_in_gap_registry() -> None:
    v04 = [_row("x", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "5.0")]
    obs = [{"inchikey": "AAAAAAAAAAAAAA-UHFFFAOYSA-N-UHFFFAOYSA-N",
            "T_K": "298.15", "epsilon": "5.0", "phase": "Liquid",
            "frequency_mhz": "0", "source_doi": "10.1/a"}]
    rows, _ = J.build_coverage_registry(v04, obs, {})
    assert rows == []


# ===========================================================================
# B02 工作单
# ===========================================================================

def test_work_order_covers_both_tracks() -> None:
    work = J.build_work_order(
        {"by_source_mechanism": {"NBS514_CIRCULAR_MANUAL_ENTRY": 102,
                                 "THERMOML_PATH_NO_OBSERVATION": 33,
                                 "UNFLAGGED_NO_OBSERVATION": 0}},
        {"n_skeletons_with_multiple_rows": 3, "n_extra_rows": 3},
    )
    tracks = {r["track"] for r in work}
    assert tracks == {"A_STRUCTURE", "B_EXTERNAL"}


def test_human_signoff_is_first_and_unblocked() -> None:
    work = J.build_work_order({"by_source_mechanism": {}, "by_recoverability": {}},
                              {"n_skeletons_with_multiple_rows": 0, "n_extra_rows": 0})
    first = work[0]
    assert first["work_id"] == "B02-A1"
    assert "R252" in first["subject"]
    assert first["can_start_now"] == "true"


def test_every_work_item_has_acceptance() -> None:
    work = J.build_work_order({"by_source_mechanism": {}, "by_recoverability": {}},
                              {"n_skeletons_with_multiple_rows": 0, "n_extra_rows": 0})
    for row in work:
        assert row["acceptance"]
        assert row["priority"] in ("P0", "P1", "P2")
        assert row["can_start_now"] in ("true", "false")


def test_zero_observation_molecules_are_named() -> None:
    work = J.build_work_order({"by_source_mechanism": {}, "by_recoverability": {}},
                              {"n_skeletons_with_multiple_rows": 0, "n_extra_rows": 0})
    b1 = [r for r in work if r["work_id"] == "B02-B1"][0]
    for name in ("EC", "PC", "EMC", "FEC", "VC", "DOL", "EA", "MA", "TMP"):
        assert name in b1["target"]


# ===========================================================================
# 渲染与确定性
# ===========================================================================

def test_render_is_deterministic() -> None:
    assert J.render_json({"b": 1, "a": [2]}) == J.render_json({"a": [2], "b": 1})
    assert b"\r\n" not in J.render_csv(("x",), [{"x": "1"}])


def test_check_detects_mutation(tmp_path: Path) -> None:
    files = {"a.json": b"1\n"}
    J.write_outputs(tmp_path, files)
    assert J.check_outputs(tmp_path, files) == []
    (tmp_path / "a.json").write_bytes(b"2\n")
    assert J.check_outputs(tmp_path, files) == ["不一致: a.json"]


# ===========================================================================
# 真实输入
# ===========================================================================

@needs_inputs
def test_real_three_skeletons_resolved() -> None:
    device = J.load_dataset(_paths())
    rows, summary = J.build_identity_resolution(device["v04"])
    assert len(rows) == 3
    assert summary["n_extra_rows"] == 3
    by_key = {r["skeleton"]: r for r in rows}
    assert by_key["ZQDPJFUHLCOCRG"]["resolution"] == J.RES_ISOMER
    assert by_key["KFUSEUYYWQURPO"]["resolution"] == J.RES_ISOMER
    assert by_key["GAEKPEKOJKCEMS"]["resolution"] == J.RES_CONFLICT
    assert by_key["GAEKPEKOJKCEMS"]["is_true_conflict"] == "true"


@needs_inputs
def test_real_a18_unaffected_by_stereoisomer_folding() -> None:
    device = J.load_dataset(_paths())
    _, summary = J.build_identity_resolution(device["v04"])
    stereo = {r for r in
              (x["skeleton"] for x in J.build_identity_resolution(device["v04"])[0]
               if x["stereo_difference"] == "true")}
    assert set(device["a18_by_skeleton"]) & stereo == set()


@needs_inputs
def test_real_coverage_gap_is_135() -> None:
    device = J.load_dataset(_paths())
    rows, summary = J.build_coverage_registry(
        device["v04"], device["observations"], device["a18_by_skeleton"])
    assert summary["n_rows_without_observation"] == 135
    assert summary["by_source_mechanism"]["NBS514_CIRCULAR_MANUAL_ENTRY"] == 102
    assert summary["by_source_mechanism"]["UNFLAGGED_NO_OBSERVATION"] == 33


@needs_inputs
def test_real_nbs_gap_is_labelled_mechanism_not_data_loss() -> None:
    device = J.load_dataset(_paths())
    _, summary = J.build_coverage_registry(
        device["v04"], device["observations"], device["a18_by_skeleton"])
    assert summary["by_recoverability"][J.FIX_NBS514] == 102
    assert "从设计上就不进观测层" in summary["key_insight"]


@needs_inputs
def test_real_gap_registry_does_not_invent_values() -> None:
    path = OUT / "coverage_gap_registry.csv"
    if not path.is_file():
        pytest.skip("J05 产物不存在")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 135
    for row in rows:
        assert row["has_observation"] == "false"
        assert row["gap_status"] == "NO_OBSERVATION_IN_SOURCE_LAYER"
        # v04 原值保留, 不出现空的 dielectric 被填 0
        assert row["v04_dielectric"] != "0"


@needs_inputs
def test_real_work_order_written() -> None:
    path = OUT / "b02_work_order.csv"
    if not path.is_file():
        pytest.skip("J05 产物不存在")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) >= 9
    assert {r["track"] for r in rows} == {"A_STRUCTURE", "B_EXTERNAL"}


# ===========================================================================
# 冻结产物
# ===========================================================================

def test_prior_stages_untouched() -> None:
    checks = [
        (INTERSECTIONS / "joint_go_nogo.json", "verdict", "NO_GO_INSUFFICIENT_ELIGIBLE_DATA"),
        (INTERSECTIONS / "pool_version_decision.json", "decision",
         "PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE"),
    ]
    for path, key, value in checks:
        if not path.is_file():
            pytest.skip(f"{path.name} 不存在")
        assert json.loads(path.read_text(encoding="utf-8"))[key] == value
    v05 = REPAIR_OUT / "dataset_v05_manifest.json"
    if v05.is_file():
        assert json.loads(v05.read_text(encoding="utf-8"))["supersedes_nothing"] is True


@needs_inputs
def test_j05_rebuild_is_deterministic() -> None:
    assert J.run(workspace=WORKSPACE, a_repo=None, out_dir=OUT, check=True) == 0
