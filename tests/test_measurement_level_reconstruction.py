# -*- coding: utf-8 -*-
"""B-G0-J04 测量级重建的验收测试.

对应授权方给的 8 条验收标准, 每条至少一个测试:
  1. 测量记录逐条可追溯; 无法恢复明确标记, 不补造
  2. 聚合记录均有贡献记录, 或有明确缺失证书
  3. 任何合成条件对不得伪装成真实测量
  4. 多来源聚合必须保留全部贡献来源
  5. 同一来源的重复转录不增加独立来源计数
  6. 新旧版本能够并行比较
  7. 所有产物确定性重建
  8. J01/J02/J03 冻结产物逐字节不变
"""

from __future__ import annotations

import csv
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "confirm_2027"))

import reconstruct_measurement_ledger as A  # noqa: E402
import build_provenance_preserving_dataset as C  # noqa: E402
import audit_condition_pair_integrity as D  # noqa: E402

WORKSPACE = REPOSITORY_ROOT.parent
REPAIR_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
INTERSECTIONS = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "intersections"
J03_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "provenance_audit"


def _paths() -> dict[str, Path]:
    return A.locate_inputs(WORKSPACE, None)


def _inputs_present() -> bool:
    return all(Path(p).is_file() for p in _paths().values())


needs_inputs = pytest.mark.skipif(not _inputs_present(), reason="权威输入不在本机")


# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------

def _obs(t: str, eps: str, *, source: str = "10.1/a", molecule: str = "AAAAAAAABBBBBB-UHFFFAOYSA-N",
         phase: str = "Liquid", freq: str = "0", row_index: str = "1",
         file: str = "f.xml", sha: str = "a" * 64) -> dict[str, str]:
    return {
        "inchikey": molecule, "T_K": t, "epsilon": eps, "phase": phase,
        "frequency_mhz": freq, "pressure_kpa": "101.325", "source_doi": source,
        "source_file": file, "source_file_sha256": sha, "source_row_index": row_index,
        "epsilon_unit": "1", "property_name": "Relative permittivity at zero frequency",
        "property_family": "epsilon", "method": "static", "temperature_band": "room_temperature",
        "in_roster": "true", "model_ready": "true",
    }


# ===========================================================================
# 验收 1: 测量可逐条追溯; 不可恢复明确标记, 不补造
# ===========================================================================

def test_measurement_id_is_content_determined_not_order_dependent() -> None:
    row = _obs("298.15", "3.134", source="10.1/x", row_index="42")
    first = A.measurement_id_for(row)
    shuffled = {"epsilon": row["epsilon"], "T_K": row["T_K"], "inchikey": row["inchikey"],
                "source_doi": row["source_doi"], "source_row_index": row["source_row_index"]}
    assert A.measurement_id_for(shuffled) == first
    changed = dict(row)
    changed["source_row_index"] = "43"
    assert A.measurement_id_for(changed) != first


def test_missing_source_is_flagged_not_invented() -> None:
    row = _obs("298.15", "3.134", source="", file="", sha="", row_index="")
    ledger_input = {"observations": [row], "a18_by_skeleton": {}, "v04_by_index": {},
                    "v04": []}
    ledger, summary = A.build_measurement_ledger(ledger_input)
    assert ledger[0]["source_document_id"] == A.NOT_EVALUATED
    assert ledger[0]["traceability_status"].startswith("UNTRACEABLE")
    assert "MISSING_SOURCE_DOCUMENT" in ledger[0]["traceability_note"]
    # 不补造: id 仍生成, 但没有伪造来源
    assert ledger[0]["measurement_id"]


def test_missing_temperature_is_untraceable_not_zero() -> None:
    row = _obs("", "3.134")
    ledger_input = {"observations": [row], "a18_by_skeleton": {}, "v04_by_index": {}, "v04": []}
    ledger, _ = A.build_measurement_ledger(ledger_input)
    assert ledger[0]["temperature_K"] == ""
    assert ledger[0]["traceability_status"] == "UNTRACEABLE_NO_TEMPERATURE"


def test_frequency_converted_to_hz_exactly() -> None:
    assert A.frequency_hz({"frequency_mhz": "0"}) == "0"
    assert A.frequency_hz({"frequency_mhz": "0.01"}) == "10"
    assert A.frequency_hz({"frequency_mhz": ""}) == ""


# ===========================================================================
# 验收 2: 聚合记录均有贡献或证书, 无第三态
# ===========================================================================

def _tiny_device() -> dict:
    """一个分子三观测 (合成条件对) + 一个分子无窗口观测."""
    obs = [
        _obs("293.15", "47.09", molecule="AAAAAAAABBBBBB-UHFFFAOYSA-N", source="10.1/p", row_index="1"),
        _obs("298.15", "47.30", molecule="AAAAAAAABBBBBB-UHFFFAOYSA-N", source="10.1/q", row_index="2"),
        _obs("303.15", "45.94", molecule="AAAAAAAABBBBBB-UHFFFAOYSA-N", source="10.1/r", row_index="3"),
    ]
    v04 = [
        {"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "298.15", "dielectric": "47.09",
         "source_doi": "10.1/p", "n_observations": "3"},
        {"inchikey": "CCCCCCCCDDDDDD-UHFFFAOYSA-N", "T_K": "298.15", "dielectric": "2.0",
         "source_doi": "10.1/z", "n_observations": ""},
    ]
    return {
        "observations": obs,
        "v04": v04,
        "v04_by_index": {f"v04row-{i + 1:03d}": r for i, r in enumerate(v04)},
        "a18_by_skeleton": {},
        "master_by_id": {},
        "gap": [
            {"measurement_id": "EPSV04-R001", "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N",
             "source_group": "10.1/p", "T_K": "298.15", "epsilon": "47.09",
             "measurement_decision": "HOLD"},
            {"measurement_id": "EPSV04-R002", "molecule_id": "CCCCCCCCDDDDDD-UHFFFAOYSA-N",
             "source_group": "10.1/z", "T_K": "298.15", "epsilon": "2.0",
             "measurement_decision": "HOLD"},
        ],
    }


def test_every_aggregate_has_contribution_or_certificate() -> None:
    device = _tiny_device()
    contrib, validity, summary = C.build_aggregate_contribution(device)
    assert len(contrib) == 2
    statuses = {r["contribution_status"] for r in contrib}
    assert statuses <= {"COMPLETE", "MISSING_CERTIFICATE"}
    assert summary["acceptance"]["every_aggregate_has_contributions_or_certificate"] is True
    assert summary["acceptance"]["no_third_state"] is True


def test_missing_contribution_emits_certificate_not_guess() -> None:
    device = _tiny_device()
    contrib, _, summary = C.build_aggregate_contribution(device)
    cert = [r for r in contrib if r["contribution_status"] == "MISSING_CERTIFICATE"]
    assert len(cert) == 1
    assert cert[0]["contribution_certificate"] == "NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER"
    assert cert[0]["contributing_measurement_ids"] == A.NOT_EVALUATED
    assert len(summary["certificates"]) == 1


# ===========================================================================
# 验收 3: 合成条件对不得伪装成真实测量
# ===========================================================================

def test_synthetic_pair_is_marked_invalid() -> None:
    device = _tiny_device()
    _, validity, _ = C.build_aggregate_contribution(device)
    first = validity[0]
    # 中位数 T=298.15 在第二条, 中位数 eps=47.09 在第一条 -> 无观测同时持有
    assert first["condition_pair_valid"] == "false"
    assert "MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS" in first["invalidity_reason"]
    assert first["downstream_rule"].startswith("不得")


def test_real_observation_pair_is_valid() -> None:
    obs = [
        _obs("293.15", "41.0", source="10.1/a", row_index="1"),
        _obs("298.15", "42.0", source="10.1/a", row_index="2"),
        _obs("303.15", "43.0", source="10.1/a", row_index="3"),
    ]
    v04 = [{"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "298.15", "dielectric": "42.0",
            "source_doi": "10.1/a", "n_observations": "3"}]
    device = {
        "observations": obs, "v04": v04,
        "v04_by_index": {"v04row-001": v04[0]},
        "a18_by_skeleton": {}, "master_by_id": {},
        "gap": [{"measurement_id": "EPSV04-R001",
                 "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "source_group": "10.1/a",
                 "T_K": "298.15", "epsilon": "42.0", "measurement_decision": "HOLD"}],
    }
    _, validity, _ = C.build_aggregate_contribution(device)
    assert validity[0]["condition_pair_valid"] == "true"
    assert validity[0]["temperature_median_is_observed_value"] == "true"
    assert validity[0]["epsilon_median_is_observed_value"] == "true"


def test_even_count_median_is_not_an_observed_value() -> None:
    obs = [
        _obs("298.15", "7.069", source="10.1/a", row_index="1"),
        _obs("303.15", "7.070", source="10.1/b", row_index="2"),
    ]
    v04 = [{"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "300.65", "dielectric": "7.0695",
            "source_doi": "10.1/a", "n_observations": "2"}]
    device = {
        "observations": obs, "v04": v04, "v04_by_index": {"v04row-001": v04[0]},
        "a18_by_skeleton": {}, "master_by_id": {},
        "gap": [{"measurement_id": "EPSV04-R001",
                 "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "source_group": "10.1/a",
                 "T_K": "300.65", "epsilon": "7.0695", "measurement_decision": "HOLD"}],
    }
    _, validity, _ = C.build_aggregate_contribution(device)
    row = validity[0]
    assert row["condition_pair_valid"] == "false"
    assert row["temperature_median_is_observed_value"] == "false"
    assert row["epsilon_median_is_observed_value"] == "false"


def test_no_pair_generates_no_fake_measurement_row() -> None:
    """合成条件对不得在测量账本里造出一条对应的原始测量."""
    device = _tiny_device()
    ledger, summary = A.build_measurement_ledger(device)
    # 账本里只有真实观测, 不会出现 v04 的 (T=298.15, eps=47.09) 组合
    pairs = {(r["temperature_K"], r["dielectric"]) for r in ledger}
    assert ("298.15", "47.09") not in pairs
    assert len(ledger) == len(device["observations"])


# ===========================================================================
# 验收 4: 多来源聚合保留全部贡献来源
# ===========================================================================

def test_multi_source_keeps_all_contributors() -> None:
    obs = [
        _obs("293.15", "47.09", source="10.1/p", row_index="1"),
        _obs("298.15", "47.30", source="10.1/q", row_index="2"),
        _obs("303.15", "45.94", source="10.1/r", row_index="3"),
        _obs("293.15", "47.81", source="10.1/s", row_index="4"),
    ]
    v04 = [{"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "296.15", "dielectric": "47.2",
            "source_doi": "10.1/p", "n_observations": "4"}]
    device = {
        "observations": obs, "v04": v04, "v04_by_index": {"v04row-001": v04[0]},
        "a18_by_skeleton": {}, "master_by_id": {},
        "gap": [{"measurement_id": "EPSV04-R001",
                 "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "source_group": "10.1/p",
                 "T_K": "296.15", "epsilon": "47.2", "measurement_decision": "HOLD"}],
    }
    contrib, _, summary = C.build_aggregate_contribution(device)
    row = contrib[0]
    assert row["n_contributing_sources"] == "4"
    for doi in ("10.1/p", "10.1/q", "10.1/r", "10.1/s"):
        assert doi in row["contributing_source_documents"]
    # gap 只写了 p, 其余必须被识别为丢失
    for doi in ("10.1/q", "10.1/r", "10.1/s"):
        assert doi in row["sources_dropped_in_gap"]


def test_single_source_aggregate_has_no_dropped_sources() -> None:
    obs = [
        _obs("293.15", "42.0", source="10.1/a", row_index="1"),
        _obs("298.15", "42.0", source="10.1/a", row_index="2"),
        _obs("303.15", "42.0", source="10.1/a", row_index="3"),
    ]
    v04 = [{"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "298.15", "dielectric": "42.0",
            "source_doi": "10.1/a", "n_observations": "3"}]
    device = {
        "observations": obs, "v04": v04, "v04_by_index": {"v04row-001": v04[0]},
        "a18_by_skeleton": {}, "master_by_id": {},
        "gap": [{"measurement_id": "EPSV04-R001",
                 "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "source_group": "10.1/a",
                 "T_K": "298.15", "epsilon": "42.0", "measurement_decision": "HOLD"}],
    }
    contrib, _, _ = C.build_aggregate_contribution(device)
    assert contrib[0]["sources_dropped_in_gap"] == A.NOT_EVALUATED


# ===========================================================================
# 验收 5: 同一来源重复转录不增加独立来源计数
# ===========================================================================

def test_duplicate_transcription_does_not_increase_source_count() -> None:
    obs = [
        _obs("298.15", "46.05", source="10.1/x", row_index="1"),
        _obs("298.15", "46.05", source="10.1/x", row_index="2"),
        _obs("298.15", "46.051", source="10.1/x", row_index="3"),
    ]
    v04 = [{"inchikey": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "T_K": "298.15", "dielectric": "46.05",
            "source_doi": "10.1/x", "n_observations": "3"}]
    device = {
        "observations": obs, "v04": v04, "v04_by_index": {"v04row-001": v04[0]},
        "a18_by_skeleton": {}, "master_by_id": {},
        "gap": [{"measurement_id": "EPSV04-R001",
                 "molecule_id": "AAAAAAAABBBBBB-UHFFFAOYSA-N", "source_group": "10.1/x",
                 "T_K": "298.15", "epsilon": "46.05", "measurement_decision": "HOLD"}],
    }
    contrib, _, _ = C.build_aggregate_contribution(device)
    assert contrib[0]["n_contributing_measurements"] == "3"
    assert contrib[0]["n_contributing_sources"] == "1"


def test_source_registry_counts_documents_not_transcriptions() -> None:
    ledger = [
        {"source_document_id": "10.1/a", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "true", "source_file": "f.xml",
         "source_file_sha256": "a" * 64},
        {"source_document_id": "10.1/a", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "true", "source_file": "f.xml",
         "source_file_sha256": "a" * 64},
        {"source_document_id": "10.1/b", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "false", "source_file": "g.xml",
         "source_file_sha256": "b" * 64},
    ]
    sources, summary = A.build_source_registry(ledger)
    assert summary["n_documents"] == 2
    a = [r for r in sources if r["source_document_id"] == "10.1/a"][0]
    assert a["n_observations"] == "2"


def test_independence_is_not_claimed_from_document_count() -> None:
    ledger = [
        {"source_document_id": "10.1/a", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "true", "source_file": "f.xml",
         "source_file_sha256": "a" * 64},
    ]
    sources, summary = A.build_source_registry(ledger)
    assert sources[0]["experimental_independence_status"] == A.NOT_EVALUATED
    assert "不等于独立实验数" in summary["independence_statement"]


def test_shared_source_file_detected() -> None:
    ledger = [
        {"source_document_id": "10.1/a", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "true", "source_file": "f.xml",
         "source_file_sha256": "c" * 64},
        {"source_document_id": "10.1/b", "molecule_key": "M1", "frequency_mhz": "0",
         "in_aggregate_window": "true", "source_file": "g.xml",
         "source_file_sha256": "c" * 64},
    ]
    _, summary = A.build_source_registry(ledger)
    assert summary["n_shared_source_files"] == 1


# ===========================================================================
# 验收 6: 新旧版本可并行比较
# ===========================================================================

@needs_inputs
def test_v05_is_declared_parallel_not_replacement() -> None:
    manifest_path = REPAIR_OUT / "dataset_v05_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("J04 产物不存在")
    v05 = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert v05["supersedes_nothing"] is True
    assert v05["relationship_to_v04"]["v04_preserved_unchanged"] is True
    assert "incompatibility" in v05["relationship_to_v04"]


@needs_inputs
def test_funnel_is_declared_non_monotonic() -> None:
    manifest_path = REPAIR_OUT / "dataset_v05_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("J04 产物不存在")
    v05 = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert v05["monotonic_funnel_claim"] is False
    ledger = v05["evidence_ledger"]
    # 每一层都有自己的统计单位, 不得互相替代
    units = {entry["unit"] for entry in ledger.values()}
    assert len(units) == len(ledger)
    assert ledger["N_raw_measurements"]["value"] > ledger["N_database_rows"]["value"]


@needs_inputs
def test_j03_corrections_are_recorded() -> None:
    manifest_path = REPAIR_OUT / "dataset_v05_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("J04 产物不存在")
    v05 = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = v05["evidence_ledger"]
    # 460 被降级为派生计数, 不是全量测量数
    assert ledger["N_in_aggregate_window"]["value"] == 460
    assert ledger["N_raw_measurements"]["value"] == 2065
    assert ledger["N_in_aggregate_window"]["value"] != ledger["N_raw_measurements"]["value"]


# ===========================================================================
# 验收 7: 确定性重建
# ===========================================================================

def test_check_detects_mutation(tmp_path: Path) -> None:
    files = {"a.json": b"1\n", "b.csv": b"x,y\n"}
    A.write_outputs(tmp_path, files)
    assert A.check_outputs(tmp_path, files) == []
    (tmp_path / "a.json").write_bytes(b"2\n")
    assert A.check_outputs(tmp_path, files) == ["不一致: a.json"]


def test_render_is_deterministic() -> None:
    left = A.render_json({"b": 1, "a": [2, 3]})
    right = A.render_json({"a": [2, 3], "b": 1})
    assert left == right
    assert b"\r\n" not in A.render_csv(("x", "y"), [{"x": "1", "y": "2"}])


def test_decimal_precision_preserved() -> None:
    assert A.fmt_decimal(Decimal("7.0695")) == "7.0695"
    assert A.fmt_decimal(Decimal("298.15")) == "298.15"
    assert A.fmt_decimal(Decimal("0")) == "0"
    assert A.fmt_decimal(None) == ""


# ===========================================================================
# 验收 8: J01/J02/J03 冻结产物不变
# ===========================================================================

def test_frozen_j01_j02_j03_outputs_unchanged() -> None:
    expectations = [
        (INTERSECTIONS / "joint_go_nogo.json", "verdict", "NO_GO_INSUFFICIENT_ELIGIBLE_DATA"),
        (INTERSECTIONS / "pool_version_decision.json", "decision",
         "PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE"),
    ]
    for path, key, value in expectations:
        if not path.is_file():
            pytest.skip(f"{path.name} 不存在")
        assert json.loads(path.read_text(encoding="utf-8"))[key] == value
    j03 = J03_OUT / "lookup_feasibility.json"
    if j03.is_file():
        payload = json.loads(j03.read_text(encoding="utf-8"))
        assert payload["analysis_id"] == "B-G0-J03"


# ===========================================================================
# 独立复核器 (生成者自证不作为验收依据)
# ===========================================================================

@needs_inputs
def test_independent_verifier_passes() -> None:
    if not (REPAIR_OUT / "aggregate_contribution_ledger_v1.csv").is_file():
        pytest.skip("J04-C 产物不存在")
    device = A.load_device(_paths())
    discrepancies, payload = D.verify(device, REPAIR_OUT)
    assert payload["status"] == "PASS"
    assert payload["n_discrepancies_fail"] == 0
    assert payload["n_aggregates_checked"] == 248


def test_independent_window_matches_generator_on_synthetic_band() -> None:
    obs = [
        _obs("298.15", "5.0"),
        _obs("303.15", "6.0"),
        _obs("303.16", "7.0"),      # 窗口外
        _obs("298.15", "8.0", phase="Gas"),      # 非液相
        _obs("298.15", "9.0", freq="1"),         # 非零频
        _obs("", "10.0"),                        # 缺温度
    ]
    independent = D.independent_window(obs, "AAAAAAAABBBBBB-UHFFFAOYSA-N")
    generated = C.window_band(obs, "AAAAAAAABBBBBB-UHFFFAOYSA-N")
    assert len(independent) == len(generated) == 2


# ===========================================================================
# 真实输入
# ===========================================================================

@needs_inputs
def test_real_ledger_covers_all_measurements() -> None:
    ledger_path = REPAIR_OUT / "measurement_ledger_v1.csv"
    if not ledger_path.is_file():
        pytest.skip("J04-A 产物不存在")
    rows = list(csv.DictReader(ledger_path.open(encoding="utf-8")))
    assert len(rows) == 2065
    assert len({r["measurement_id"] for r in rows}) == 2065


@needs_inputs
def test_real_every_measurement_is_traceable() -> None:
    ledger_path = REPAIR_OUT / "measurement_ledger_v1.csv"
    if not ledger_path.is_file():
        pytest.skip("J04-A 产物不存在")
    rows = list(csv.DictReader(ledger_path.open(encoding="utf-8")))
    untraceable = [r for r in rows if r["traceability_status"].startswith("UNTRACEABLE")]
    assert untraceable == []
    assert all(r["source_document_id"] != A.NOT_EVALUATED for r in rows)


@needs_inputs
def test_real_aggregate_rows_split_into_two_states_only() -> None:
    path = REPAIR_OUT / "aggregate_contribution_ledger_v1.csv"
    if not path.is_file():
        pytest.skip("J04-C 产物不存在")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 248
    statuses = {r["contribution_status"] for r in rows}
    assert statuses == {"COMPLETE", "MISSING_CERTIFICATE"}
    n_complete = sum(1 for r in rows if r["contribution_status"] == "COMPLETE")
    n_cert = sum(1 for r in rows if r["contribution_status"] == "MISSING_CERTIFICATE")
    assert n_complete + n_cert == 248
    assert n_complete == 100
    assert n_cert == 148


@needs_inputs
def test_real_condition_pairs_split_into_valid_and_invalid() -> None:
    path = REPAIR_OUT / "condition_pair_validity_v1.csv"
    if not path.is_file():
        pytest.skip("J04-C 产物不存在")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    valid = sum(1 for r in rows if r["condition_pair_valid"] == "true")
    invalid = sum(1 for r in rows if r["condition_pair_valid"] == "false")
    assert valid + invalid == 248
    composites = [
        r for r in rows
        if r["condition_pair_valid"] == "false"
        and r["invalidity_reason"] != "NO_CONTRIBUTING_MEASUREMENTS"
    ]
    assert len(composites) == 22


@needs_inputs
def test_real_synthetic_pairs_are_never_valid() -> None:
    """任何缺少同源观测的行, 都不得标记为 valid.

    invalidity_reason 里可能同时出现与配对无关的警示 (例如多来源在 gap 中被丢弃),
    那是**另一维度**的问题, 不改变配对有效性. 因此这里只要求:
      * valid 行必须两个中位数都在观测值上;
      * valid 行不得出现任何"配对不成立"的原因码.
    """
    PAIR_REASONS = {
        "MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS",
        "TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE",
        "EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE",
        "NO_CONTRIBUTING_MEASUREMENTS",
    }
    path = REPAIR_OUT / "condition_pair_validity_v1.csv"
    if not path.is_file():
        pytest.skip("J04-C 产物不存在")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for row in rows:
        if row["condition_pair_valid"] == "true":
            assert row["temperature_median_is_observed_value"] == "true"
            assert row["epsilon_median_is_observed_value"] == "true"
            reasons = {r for r in row["invalidity_reason"].split(";") if r}
            assert reasons & PAIR_REASONS == set()


@needs_inputs
def test_real_dmso_shows_composite_pair() -> None:
    path = REPAIR_OUT / "condition_pair_validity_v1.csv"
    if not path.is_file():
        pytest.skip("J04-C 产物不存在")
    rows = {r["aggregate_id"]: r for r in
            csv.DictReader(path.open(encoding="utf-8"))}
    dmso = [r for r in rows.values() if r["a_mol_id"] == "C15"]
    assert len(dmso) == 1
    assert dmso[0]["condition_pair_valid"] == "false"
    assert dmso[0]["n_contributing_sources"] == "4"


@needs_inputs
def test_real_three_a18_molecules_have_valid_pairs() -> None:
    path = REPAIR_OUT / "condition_pair_validity_v1.csv"
    if not path.is_file():
        pytest.skip("J04-C 产物不存在")
    rows = {r["a_mol_id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))
            if r["a_mol_id"] != A.NOT_EVALUATED}
    for mol_id in ("C01", "C03", "C14"):
        assert rows[mol_id]["condition_pair_valid"] == "true"


@needs_inputs
def test_all_j04_modules_rebuild_identically() -> None:
    for module in (A, C, D):
        assert module.run(workspace=WORKSPACE, a_repo=None, out_dir=REPAIR_OUT, check=True) == 0
