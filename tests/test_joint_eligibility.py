# -*- coding: utf-8 -*-
"""B-G0-J01 联合资格审计的反例测试集.

纪律
----
这组测试里, 失败用例比成功用例更重要: 每一个都对应一个"看起来对、其实会把资格
放宽"的具体写法。测试只调用生产代码里的**同一个**函数 (prepare_indices /
adjudicate_all / describe_sources ...), 不在测试里重写一套判定, 否则测试通过不能
说明生产路径正确。
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "confirm_2027"))

import build_joint_eligibility as J  # noqa: E402

WORKSPACE = REPOSITORY_ROOT.parent
REAL_OUT = REPOSITORY_ROOT / "outputs" / "confirm_2027" / "intersections"

K_RULE_TEXT = "primary_k = max(1, ceil(n_eligible / 10))"


# ---------------------------------------------------------------------------
# 合成小数据: 覆盖四类裁决与三类反例
# ---------------------------------------------------------------------------

def _windows() -> list[dict[str, object]]:
    return [
        {"name": "room_temperature", "low": 293.15, "high": 303.15},
        {"name": "extended_temperature", "low": 313.15, "high": 323.15},
        {"name": "high_temperature", "low": 333.15, "high": 373.15},
    ]


def _tiny_dataset() -> dict[str, object]:
    """C01 室温合格 / C02 温带外+来源冲突 / C03 仅主表 / C04 仅观测.

    设计意图:
      * C03 与 C04 都出现在 248 行主表里 —— 主表成员身份**不得**让它们变成"条件可解析";
      * C01 的两条观测同一 DOI —— 重复转录不得算成两个独立来源;
      * C01 第三条观测 DOI 与来源文件皆空 —— 缺失 DOI 不得计入来源数;
      * C02 的 v04 来源与 v11 来源无交集 —— 必须标 SOURCE_CONFLICT 而不是取并集.
    """
    molecules = {
        "C01": ("methanol", "CO"),
        "C02": ("ethanol", "CCO"),
        "C03": ("acetone", "CC(C)=O"),
        "C04": ("water", "O"),
    }
    keys = {mol_id: J.inchikey_from_smiles(smiles) for mol_id, (_n, smiles) in molecules.items()}

    core = [
        {"mol_id": mol_id, "name": name, "smiles": smiles}
        for mol_id, (name, smiles) in molecules.items()
    ]
    v04 = []
    for mol_id, (name, smiles) in molecules.items():
        temperature = "333.15" if mol_id == "C02" else "298.15"
        doi = "10.9/v04-c02" if mol_id == "C02" else f"10.9/v04-{mol_id.lower()}"
        v04.append({
            "inchikey": keys[mol_id], "smiles": smiles, "name": name,
            "T_K": temperature, "dielectric": "30.0", "source_doi": doi,
            "temperature_band": "high_temperature" if mol_id == "C02" else "room_temperature",
            "gate_flags": "zero_frequency|pure_component",
        })

    observations = [
        # C01: 同一 DOI 两条 + 一条缺 DOI
        {"inchikey": keys["C01"], "T_K": "298.15", "epsilon": "32.7", "phase": "Liquid",
         "frequency_mhz": "0", "pressure_kpa": "101.325", "source_doi": "10.9/v04-c01",
         "source_file": "f1.xml", "temperature_band": "room_temperature",
         "model_ready": "true", "property_name": "Relative permittivity at zero frequency"},
        {"inchikey": keys["C01"], "T_K": "298.15", "epsilon": "32.8", "phase": "Liquid",
         "frequency_mhz": "0", "pressure_kpa": "101.325", "source_doi": "10.9/v04-c01",
         "source_file": "f2.xml", "temperature_band": "room_temperature",
         "model_ready": "true", "property_name": "Relative permittivity at zero frequency"},
        {"inchikey": keys["C01"], "T_K": "298.15", "epsilon": "32.9", "phase": "Liquid",
         "frequency_mhz": "0", "pressure_kpa": "101.325", "source_doi": "",
         "source_file": "", "temperature_band": "room_temperature",
         "model_ready": "false", "property_name": "Relative permittivity at zero frequency"},
        # C02: 温带外, 来源与 v04 无交集
        {"inchikey": keys["C02"], "T_K": "333.15", "epsilon": "24.3", "phase": "Liquid",
         "frequency_mhz": "0", "pressure_kpa": "101.325", "source_doi": "10.9/obs-c02",
         "source_file": "f3.xml", "temperature_band": "outside_declared_window",
         "model_ready": "false", "property_name": "Relative permittivity at zero frequency"},
        # C04: 只有射频观测
        {"inchikey": keys["C04"], "T_K": "298.15", "epsilon": "78.4", "phase": "Liquid",
         "frequency_mhz": "1", "pressure_kpa": "101.325", "source_doi": "10.9/obs-c04",
         "source_file": "f4.xml", "temperature_band": "room_temperature",
         "model_ready": "true", "property_name": "Relative permittivity at various frequencies"},
    ]

    def gap_row(mol_id: str, measurement_id: str) -> dict[str, str]:
        return {
            "molecule_id": keys[mol_id], "measurement_id": measurement_id,
            "source_group": f"10.9/v04-{mol_id.lower()}", "phase": "UNKNOWN",
            "T_K": "298.15", "P": "", "frequency": "", "epsilon": "30.0",
            "license": "UNKNOWN", "measurement_decision": "HOLD", "qc_reason": "",
        }

    gap = [gap_row(m, f"EPSV04-R00{i + 1}") for i, m in enumerate(sorted(molecules))]
    master = [
        {"measurement_id": f"EPSV04-R00{i + 1}", "molecule_id": keys[m],
         "source_primary": f"10.9/v04-{m.lower()}", "in_49_preview": "yes",
         "evidence_status": "PENDING", "admission_status": "HOLD",
         "T_K": "333.15" if m == "C02" else "298.15", "epsilon": "30.0"}
        for i, m in enumerate(sorted(molecules))
    ]
    pool_c = [
        {"measurement_id": "EPSV04-R001", "molecule_id": keys["C01"],
         "source_group": "10.9/v04-c01", "epsilon_recorded": "30.0", "T_K": "298.15",
         "evidence_group_id": "EG-R001", "decision_v2": "CANDIDATE"},
        {"measurement_id": "EPSV04-R002", "molecule_id": keys["C02"],
         "source_group": "10.9/v04-c02", "epsilon_recorded": "30.0", "T_K": "333.15",
         "evidence_group_id": "EG-R002", "decision_v2": "CANDIDATE"},
    ]
    worksheet = [
        {"measurement_id": "EPSV04-R001", "molecule_id": keys["C01"], "source_group": "10.9/v04-c01",
         "epsilon": "30.0", "T_K": "298.15", "machine_audit_status": "AUDITED_CLEAN",
         "human_audit_status": "PENDING_HUMAN", "a9_group_level": "BLOCK"},
        {"measurement_id": "EPSV04-R002", "molecule_id": keys["C02"], "source_group": "10.9/v04-c02",
         "epsilon": "30.0", "T_K": "333.15", "machine_audit_status": "AUDITED_CLEAN",
         "human_audit_status": "PENDING_HUMAN", "a9_group_level": "BLOCK"},
    ]
    formal = [
        {"measurement_id": "EPSV04-R001", "inchikey": keys["C01"], "epsilon": "30.0",
         "T_K": "298.15", "failed_gates": "A9,A11", "formal_verdict_draft": "HOLD_A9,A11"},
    ]
    return {
        "core": core,
        "v04": v04,
        "observations": observations,
        "gap": gap,
        "master": master,
        "pool_c": pool_c,
        "pool_b": [],
        "worksheet": worksheet,
        "formal": formal,
        "protocol": {
            "status": "DRAFT_PENDING_HUMAN_APPROVAL",
            "frozen": False,
            "protocol_version": "test",
            "allowed_temperature_windows_K": _windows(),
        },
        "k_rule": {"rule": K_RULE_TEXT},
        "v56_manifest": {"files": [], "project": "test", "generated_by": "tests", "counts": {}},
    }


def _tiny_rows() -> dict[str, dict[str, str]]:
    rows = J.adjudicate_all(_tiny_dataset(), _windows())
    return {row["a_mol_id"]: row for row in rows}


# ---------------------------------------------------------------------------
# 1. 身份: 主表成员身份 ≠ 资格
# ---------------------------------------------------------------------------

def test_master_membership_alone_is_not_condition_resolvable() -> None:
    """248 行主表是全集, 不是资格; 只在主表里的分子不得算"条件可解析"."""
    rows = _tiny_rows()
    assert rows["C03"]["candidate_layers"] == "candidate_master"
    assert rows["C03"]["qualifying_layers"] == ""
    assert rows["C03"]["condition_resolvable"] == "false"
    assert rows["C03"]["eligibility_verdict"] == J.VERDICT_IDENTITY_ONLY


def test_identity_status_distinguishes_full_key_and_skeleton() -> None:
    dataset = _tiny_dataset()
    # 把 C01 的 v04 身份改成"同骨架不同立体/质子化态": 完整键不匹配, 骨架匹配
    dataset["v04"][0]["inchikey"] = dataset["v04"][0]["inchikey"].replace("UHFFFAOYSA", "UHFFFFAAAA")
    row = {r["a_mol_id"]: r for r in J.adjudicate_all(dataset, _windows())}["C01"]
    assert row["identity_status"] == "IDENTITY_SKELETON_ONLY"
    assert row["eligibility_verdict"] != J.VERDICT_NO_IDENTITY


def test_identity_absent_when_not_in_master() -> None:
    dataset = _tiny_dataset()
    dataset["v04"] = [r for r in dataset["v04"] if r["name"] != "acetone"]
    row = {r["a_mol_id"]: r for r in J.adjudicate_all(dataset, _windows())}["C03"]
    assert row["identity_status"] == J.VERDICT_NO_IDENTITY
    assert row["eligibility_verdict"] == J.VERDICT_NO_IDENTITY
    assert row["backfill_tier"] == "P9_NO_ACTION_IDENTITY_MISSING"


# ---------------------------------------------------------------------------
# 2. 来源: 重复转录 / 缺失 DOI / 来源冲突
# ---------------------------------------------------------------------------

def test_duplicate_source_rows_do_not_inflate_independent_sources() -> None:
    dataset = _tiny_dataset()
    c01 = [r for r in dataset["observations"] if r["source_doi"] == "10.9/v04-c01"]
    assert len(c01) == 2  # 两条转录
    described = J.describe_sources(c01)
    assert described["n_source_groups"] == 1
    assert described["independent_source_status"] == "SINGLE_SOURCE"


def test_missing_doi_rows_are_counted_separately_not_as_sources() -> None:
    rows = _tiny_rows()
    assert rows["C01"]["v11_n_missing_doi_rows"] == "1"
    assert rows["C01"]["v11_n_source_groups"] == "1"
    assert "MISSING_DOI_ROWS_EXCLUDED_FROM_SOURCE_COUNT" in rows["C01"]["eligibility_reason_codes"]


def test_source_conflict_is_flagged_not_union_merged() -> None:
    """v04 来源与 v11 来源无交集时必须是 SOURCE_CONFLICT, 不能取并集当对齐."""
    rows = _tiny_rows()
    assert rows["C02"]["source_alignment_status"] == "SOURCE_CONFLICT"
    assert "SOURCE_CONFLICT_V04_VS_V11" in rows["C02"]["eligibility_reason_codes"]
    observation = J.describe_sources([
        r for r in _tiny_dataset()["observations"] if r["source_doi"] == "10.9/obs-c02"
    ])
    assert J.source_alignment({"10.9/v04-c02"}, observation) == "SOURCE_CONFLICT"


def test_partial_alignment_when_only_some_observation_sources_are_recorded() -> None:
    observation = J.describe_sources([
        {"source_doi": "10.1/known", "source_file": "a.xml"},
        {"source_doi": "10.1/extra", "source_file": "b.xml"},
    ])
    assert J.source_alignment({"10.1/known"}, observation) == "PARTIAL_ALIGNMENT"


# ---------------------------------------------------------------------------
# 3. 温度: 温带边界与"温带外保留原值"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "temperature,expected",
    [
        (293.15, "room_temperature"),
        (303.15, "room_temperature"),
        (303.16, "outside_declared_window"),
        (313.15, "extended_temperature"),
        (333.15, "high_temperature"),
        (373.15, "high_temperature"),
        (373.16, "outside_declared_window"),
    ],
)
def test_band_boundaries_are_inclusive(temperature: float, expected: str) -> None:
    assert J.band_of(temperature, _windows()) == expected


def test_missing_temperature_is_not_defaulted() -> None:
    assert J.band_of(None, _windows()) == "temperature_missing"


def test_off_band_candidate_keeps_original_temperature() -> None:
    """SN 型反例: 温带外不得折算到室温, 也不得因不在室温带而被删."""
    rows = _tiny_rows()
    assert rows["C02"]["candidate_T_K"] == "333.15"
    assert rows["C02"]["candidate_bands"] == "high_temperature"
    assert rows["C02"]["v11_n_room_band"] == "0"
    assert rows["C02"]["eligibility_verdict"] == J.VERDICT_OFF_BAND
    assert rows["C02"]["room_band_qualified"] == "false"
    assert rows["C02"]["backfill_tier"] == "P2_ROOM_BAND_EVIDENCE"


# ---------------------------------------------------------------------------
# 4. 相态 / 频率 / 压强
# ---------------------------------------------------------------------------

def test_rf_only_frequency_is_not_static() -> None:
    rows = _tiny_rows()
    assert rows["C04"]["frequency_status"] == "RF_ONLY"
    assert rows["C04"]["v11_n_static_frequency"] == "0"


def test_static_zero_hertz_is_evidence_not_a_default() -> None:
    rows = _tiny_rows()
    assert rows["C01"]["frequency_status"] == "STATIC_ZERO_HZ_EVIDENCED"
    unknown = J.frequency_status_of([{"frequency_mhz": ""}])
    assert unknown["frequency_status"] == "FREQUENCY_UNKNOWN"
    assert unknown["n_static"] == 0


def test_phase_and_pressure_status_are_explicit_when_absent() -> None:
    assert J.phase_status_of([]) == "NOT_EVALUATED"
    assert J.phase_status_of([{"phase": ""}]) == "PHASE_UNKNOWN"
    assert J.phase_status_of([{"phase": "Liquid"}]) == "LIQUID_EVIDENCED_IN_V11"
    assert J.phase_status_of([{"phase": "Liquid"}, {"phase": "Gas"}]) == "MIXED_PHASE_EVIDENCE"
    assert J.pressure_status_of([]) == "NOT_EVALUATED"
    assert J.pressure_status_of([{"pressure_kpa": ""}]) == "PRESSURE_UNKNOWN"
    assert J.pressure_status_of([{"pressure_kpa": "101.325"}]) == "PRESSURE_EVIDENCED"
    assert J.pressure_status_of(
        [{"pressure_kpa": "101.325"}, {"pressure_kpa": ""}]
    ) == "PRESSURE_PARTIAL"


# ---------------------------------------------------------------------------
# 5. 人类准入: 未签批不得升级
# ---------------------------------------------------------------------------

def test_pending_human_audit_is_not_signed() -> None:
    rows = _tiny_rows()
    assert rows["C01"]["human_admission_status"] == "NOT_SIGNED"
    assert rows["C01"]["human_audit_status"] == "gap:HOLD;worksheet:PENDING_HUMAN"
    assert rows["C01"]["admitted"] == "false"
    assert rows["C01"]["eligibility_verdict"] == J.VERDICT_QUALIFIED
    assert "HUMAN_SIGNATURE_PENDING" in rows["C01"]["eligibility_reason_codes"]


def test_machine_clean_and_human_signed_are_different_states() -> None:
    worksheet = {"R1": {"measurement_id": "R1", "human_audit_status": "PENDING_HUMAN"}}
    gap = {"R1": {"measurement_id": "R1", "measurement_decision": "HOLD"}}
    formal = {"R1": {"measurement_id": "R1", "formal_verdict_draft": "HOLD_A9,A11"}}
    pending = J.human_admission_of(["R1"], worksheet, gap, formal)
    assert pending["human_admission_status"] == "NOT_SIGNED"
    signed = J.human_admission_of(
        ["R1"], worksheet, gap, {"R1": {"measurement_id": "R1", "formal_verdict_draft": "ACCEPT"}}
    )
    assert signed["human_admission_status"] == "SIGNED_ACCEPT"
    assert J.human_admission_of([], worksheet, gap, formal)["human_admission_status"] == "NO_ADMISSION_ROW"


# ---------------------------------------------------------------------------
# 6. 七维独立, 不得塌成单一 matched
# ---------------------------------------------------------------------------

def test_no_single_matched_flag_replaces_the_seven_dimensions() -> None:
    assert "matched" not in J.ELIGIBILITY_COLUMNS
    required = {
        "identity_status": "身份",
        "independent_source_status": "来源",
        "candidate_bands": "温度",
        "phase_status": "相态",
        "frequency_status": "频率",
        "human_admission_status": "人类准入",
        "v11_n_source_groups": "独立来源数",
    }
    for column in required:
        assert column in J.ELIGIBILITY_COLUMNS, f"缺少维度列 {column}"


def test_gate_table_reports_each_dimension_separately() -> None:
    rows = J.adjudicate_all(_tiny_dataset(), _windows())
    gates = J.build_gate_table(rows)
    dimensions = [gate["dimension"] for gate in gates]
    assert dimensions == [
        "identity", "source", "temperature", "phase", "frequency",
        "human_admission", "independent_source_count_ge2", "independent_source_count_ge3",
    ]
    by_dimension = {gate["dimension"]: gate for gate in gates}
    assert by_dimension["identity"]["n_pass"] == 4
    assert by_dimension["human_admission"]["n_pass"] == 0
    assert by_dimension["independent_source_count_ge2"]["n_pass"] == 0


def test_condition_resolvable_and_room_band_are_separate_flags() -> None:
    rows = _tiny_rows()
    assert rows["C02"]["condition_resolvable"] == "true"
    assert rows["C02"]["room_band_qualified"] == "false"
    assert rows["C01"]["condition_resolvable"] == "true"
    assert rows["C01"]["room_band_qualified"] == "true"


# ---------------------------------------------------------------------------
# 7. 输入完整性: 版本漂移与映射冲突
# ---------------------------------------------------------------------------

def test_pinned_input_drift_is_detected(tmp_path: Path) -> None:
    target = tmp_path / "input.csv"
    target.write_bytes(b"a,b\n1,2\n")
    pins = {"x": J.sha256_file(target)}
    assert J.verify_pinned_inputs({"x": target}, pins) == []
    drifted = J.verify_pinned_inputs({"x": target}, {"x": "0" * 64})
    assert len(drifted) == 1 and drifted[0]["input"] == "x"
    missing = J.verify_pinned_inputs({"x": tmp_path / "nope.csv"}, pins)
    assert missing[0]["actual"] == "FILE_MISSING"


def test_gap_v04_mapping_mismatch_is_an_error_not_a_warning() -> None:
    v04 = [
        {"inchikey": "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "dielectric": "3.0"},
        {"inchikey": "BBBBBBBBBBBBBB-UHFFFAOYSA-N", "dielectric": "4.0"},
    ]
    good = [{"measurement_id": "EPSV04-R001", "molecule_id": "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "epsilon": "3.0"},
            {"measurement_id": "EPSV04-R002", "molecule_id": "BBBBBBBBBBBBBB-UHFFFAOYSA-N", "epsilon": "4.0"}]
    assert J.check_gap_v04_mapping(good, v04)["status"] == "PASS"
    bad_identity = [{"measurement_id": "EPSV04-R001", "molecule_id": "CCCCCCCCCCCCCC-UHFFFAOYSA-N", "epsilon": "3.0"}]
    assert J.check_gap_v04_mapping(bad_identity, v04)["status"] == "FAIL"
    bad_epsilon = [{"measurement_id": "EPSV04-R001", "molecule_id": "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "epsilon": "9.9"}]
    assert J.check_gap_v04_mapping(bad_epsilon, v04)["status"] == "FAIL"
    bad_id = [{"measurement_id": "R001", "molecule_id": "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "epsilon": "3.0"}]
    assert J.check_gap_v04_mapping(bad_id, v04)["status"] == "FAIL"


def test_snapshot_mismatch_refuses_to_emit_numbers() -> None:
    J.assert_snapshot({"a": 1, "b": 2}, {"a": 1, "b": 2})
    with pytest.raises(J.SnapshotMismatch):
        J.assert_snapshot({"a": 1, "b": 3}, {"a": 1, "b": 2})


def test_read_csv_strict_fails_closed_on_missing_column(tmp_path: Path) -> None:
    target = tmp_path / "x.csv"
    target.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(J.JointEligibilityError):
        J.read_csv_strict(target, ("a", "c"))


def test_unparseable_number_is_none_not_zero() -> None:
    assert J.to_float("") is None
    assert J.to_float("n/a") is None
    assert J.to_float("0") == 0.0
    assert J.fmt_number(None) == ""
    assert J.fmt_number(298.15) == "298.15"


# ---------------------------------------------------------------------------
# 8. k 规则与 GO/NO-GO 的门槛推导
# ---------------------------------------------------------------------------

def test_primary_k_follows_the_frozen_rule() -> None:
    assert J.primary_k(0, K_RULE_TEXT) == 1
    assert J.primary_k(3, K_RULE_TEXT) == 1
    assert J.primary_k(10, K_RULE_TEXT) == 1
    assert J.primary_k(11, K_RULE_TEXT) == 2
    assert J.primary_k(21, K_RULE_TEXT) == 3
    assert J.min_n_for_primary_k(3, K_RULE_TEXT) == 21
    with pytest.raises(J.JointEligibilityError):
        J.primary_k(5, "no such rule")


def test_go_nogo_is_no_go_and_emits_no_confirmatory_metric() -> None:
    rows = J.adjudicate_all(_tiny_dataset(), _windows())
    go_nogo = J.build_go_nogo(
        rows,
        protocol=_tiny_dataset()["protocol"],
        k_rule={"rule": K_RULE_TEXT},
        gates=J.build_gate_table(rows),
        criteria_sha256="0" * 64,
        inputs_sha256={},
        environment={},
        v56_manifest={"files": []},
    )
    assert go_nogo["verdict"] == "NO_GO_INSUFFICIENT_ELIGIBLE_DATA"
    assert go_nogo["confirmatory_metrics_emitted"] == []
    assert go_nogo["descriptive_only"] is True
    assert "joint_topk" in go_nogo["not_evaluated"]
    assert go_nogo["denominators"]["n_admitted"] == 0
    assert go_nogo["denominators"]["n_room_band_qualified"] == 1
    # 三条点名缺口必须进机器产物, 不能只写在报告里
    assert go_nogo["gap_groups"]["zero_observation"]["count"] == 1
    assert go_nogo["gap_groups"]["observation_ready_unqualified"]["count"] == 1
    assert go_nogo["gap_groups"]["condition_resolvable_off_room_band"]["count"] == 1


# ---------------------------------------------------------------------------
# 9. 输出一致性 / 确定性
# ---------------------------------------------------------------------------

def test_check_detects_mutated_output(tmp_path: Path) -> None:
    files = {"a.json": b"1\n", "b.csv": b"x,y\n"}
    J.write_outputs(tmp_path, files)
    assert J.check_outputs(tmp_path, files) == []
    (tmp_path / "a.json").write_bytes(b"2\n")
    problems = J.check_outputs(tmp_path, files)
    assert problems == ["不一致: a.json"]


def test_check_detects_missing_output(tmp_path: Path) -> None:
    files = {"a.json": b"1\n"}
    J.write_outputs(tmp_path, files)
    (tmp_path / "a.json").unlink()
    assert J.check_outputs(tmp_path, files) == ["缺失: a.json"]


def test_rendering_is_deterministic_for_dict_order() -> None:
    left = J.render_json({"b": 1, "a": [2, 3]})
    right = J.render_json({"a": [2, 3], "b": 1})
    assert left == right
    csv_left = J.render_csv(("x", "y"), [{"x": "1", "y": "2"}])
    csv_right = J.render_csv(("x", "y"), [{"y": "2", "x": "1"}])
    assert csv_left == csv_right
    assert b"\r\n" not in csv_left


# ---------------------------------------------------------------------------
# 10. 真实输入的集成检查 (缺输入则跳过)
# ---------------------------------------------------------------------------

def _real_paths() -> dict[str, Path]:
    return J.locate_inputs(WORKSPACE, None)


@pytest.fixture(scope="module")
def real_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    paths = _real_paths()
    missing = [name for name, path in paths.items() if not Path(path).is_file()]
    if missing:
        pytest.skip(f"权威输入不在本机: {missing}")
    out_dir = tmp_path_factory.mktemp("j01-real")
    code = J.run(workspace=WORKSPACE, a_repo=None, out_dir=out_dir, check=False)
    assert code == 0
    return {name: (out_dir / name).read_bytes() for name in J.OUTPUT_FILES}


def test_real_snapshot_matches_the_authorised_numbers(real_files: dict[str, bytes]) -> None:
    go_nogo = json.loads(real_files["joint_go_nogo.json"].decode("utf-8"))
    assert go_nogo["verdict"] == "NO_GO_INSUFFICIENT_ELIGIBLE_DATA"
    denominators = go_nogo["denominators"]
    assert denominators["n_a_core_neutral_parents"] == 18
    assert denominators["n_identity_common_in_candidate_master"] == 18
    assert denominators["n_condition_resolvable"] == 4
    assert denominators["n_room_band_qualified"] == 3
    assert denominators["n_admitted"] == 0
    assert go_nogo["confirmatory_metrics_emitted"] == []


def test_real_sn_off_band_condition_is_preserved(real_files: dict[str, bytes]) -> None:
    go_nogo = json.loads(real_files["joint_go_nogo.json"].decode("utf-8"))
    off_band = go_nogo["snapshot"]["off_room_band_condition_resolvable"]
    assert [entry["mol_id"] for entry in off_band] == ["C18"]
    assert off_band[0]["candidate_T_K"] == "333.15"
    assert off_band[0]["candidate_bands"] == "high_temperature"


def test_real_gap_groups_are_the_three_named_sets(real_files: dict[str, bytes]) -> None:
    go_nogo = json.loads(real_files["joint_go_nogo.json"].decode("utf-8"))
    groups = go_nogo["gap_groups"]
    assert groups["zero_observation"]["count"] == 9
    assert groups["observation_ready_unqualified"]["count"] == 5
    assert groups["condition_resolvable_off_room_band"]["count"] == 1
    assert groups["condition_qualified_pending_human"]["count"] == 3
    named = (
        set(groups["zero_observation"]["mol_ids"])
        | set(groups["observation_ready_unqualified"]["mol_ids"])
        | set(groups["condition_resolvable_off_room_band"]["mol_ids"])
        | set(groups["condition_qualified_pending_human"]["mol_ids"])
    )
    assert len(named) == 18  # 四类互不重叠且覆盖全部 A 母体


def test_real_eligibility_table_covers_every_molecule_once(real_files: dict[str, bytes]) -> None:
    rows = list(csv.DictReader(io.StringIO(real_files["joint_eligibility.csv"].decode("utf-8"))))
    assert len(rows) == 18
    assert [r["a_mol_id"] for r in rows] == sorted(r["a_mol_id"] for r in rows)
    assert not any(r["admitted"] == "true" for r in rows)
    # 每个分子都必须有一条可读的裁决与一条回填动作
    assert all(r["eligibility_verdict"] for r in rows)
    assert all(r["backfill_action"] for r in rows)


def test_real_candidate_rows_never_leave_fields_silently_blank(real_files: dict[str, bytes]) -> None:
    """缺失字段写 not_evaluated, 不写空串也绝不写 0 (协议 N6)."""
    rows = list(csv.DictReader(
        io.StringIO(real_files["joint_candidate_measurement_rows.csv"].decode("utf-8"))
    ))
    assert rows
    for row in rows:
        assert row["epsilon"] != ""
        assert row["decision"] != ""
        assert row["source_group"] != ""
        assert row["T_K"] != ""


def test_real_layer_summary_reports_layers_separately(real_files: dict[str, bytes]) -> None:
    summary = json.loads(real_files["joint_pool_layer_summary.json"].decode("utf-8"))
    layers = summary["layers"]
    for layer in ("candidate_master", "pool_c", "pool_b", "worksheet_40",
                  "formal_draft_20", "v11_observation_layer"):
        assert layer in layers
    assert layers["candidate_master"]["n_a18_hits"] == 18
    assert layers["pool_c"]["n_a18_hits"] == 4
    assert layers["formal_draft_20"]["n_a18_hits"] == 1
    assert "note" in summary


def test_real_rebuild_is_byte_identical(real_files: dict[str, bytes],
                                        tmp_path: Path) -> None:
    paths = _real_paths()
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    J.write_outputs(tmp_path, real_files)
    assert J.check_outputs(tmp_path, real_files) == []


def test_real_committed_outputs_match_a_fresh_rebuild(tmp_path: Path) -> None:
    if not REAL_OUT.is_dir():
        pytest.skip("尚无已提交产物")
    paths = _real_paths()
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    assert J.run(workspace=WORKSPACE, a_repo=None, out_dir=REAL_OUT, check=True) == 0


def test_run_refuses_on_input_drift(tmp_path: Path) -> None:
    paths = _real_paths()
    if any(not Path(p).is_file() for p in paths.values()):
        pytest.skip("权威输入不在本机")
    pins = dict(J.PINNED_INPUT_SHA256)
    pins["a_core_set"] = "0" * 64
    code = J.run(workspace=WORKSPACE, a_repo=None, out_dir=tmp_path, check=False, pins=pins)
    assert code == 3
    assert not (tmp_path / "joint_go_nogo.json").exists()
