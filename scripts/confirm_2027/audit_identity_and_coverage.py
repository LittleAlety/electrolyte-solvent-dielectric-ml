#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J05 | 身份冲突裁决 + 覆盖缺口登记 + B02 工作单.

为什么还要多这一步
------------------
J01-J04 全程用 **InChIKey 首段骨架** 做连接. 这个选择在 A18 上没问题 (J05 实证:
18 个分子全部落在单行骨架上), 但对全量 248 行有代价: 立体异构体会被折叠.
本模块把这个代价**量化并裁决**, 而不是留一句"注意立体化学".

同时 J04 暴露了第二个结构性事实: 135 条 v04 记录在观测层没有任何对应观测,
因此它们的聚合贡献**不可能**被重建. J04 只能开缺失证书. 本模块要回答: 这 135 条
里有哪几类, 各自能不能靠已有材料修好, 还是必须重新取数.

三个产出
--------
1. 身份冲突裁决 (J05-A)
   3 个骨架各 2 行的真实原因分三类, 处置也不同:
   * 顺/反立体异构 -> 两个不同化合物, 不是冲突, 骨架连接是**假合并**;
   * 同一化合物两个来源两个值 -> 真冲突, 需人工裁决;
   * 同一化合物同一来源重复登记 -> 去重.
   判决一律"不静默合并", 并给每种情形一个可执行处置.

2. 覆盖缺口登记 (J05-B)
   135 条无观测记录按来源机制分类, 每类给"能否靠已有材料修复"的判定.

3. B02 工作单
   把路线 A (结构修复) 与路线 B (外部证据) 落成可执行条目, 带优先级与前置门.

绝不做的
--------
* 不改 v04 / gap / pool_C / backfill / v11plus;
* 不改 J01-J04 任何冻结产物;
* 不为立体异构体选择"代表行", 也不把它们的值合并或平均;
* 不把"没有观测"写成"观测为 0"或"值不存在".
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_ID = "B-G0-J05"
ANALYSIS_TITLE = "身份冲突裁决与覆盖缺口登记"
CONTRACT_VERSION = "confirm_2027.identity_and_coverage/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j05_inputs/v1"
GENERATOR_VERSION = "audit_identity_and_coverage/1.0.0"

#: 已知会导致"无观测"的来源机制 (来自 gate_flags 与 source_doi 实证)
NBS514_DOI = "10.6028/nbs.circ.514"

#: 身份冲突的处置类型
RES_ISOMER = "STEREOISOMER_DISTINCT_COMPOUNDS"
RES_CONFLICT = "SAME_COMPOUND_SOURCE_CONFLICT"
RES_DUPLICATE = "SAME_COMPOUND_DUPLICATE_ENTRY"

#: 覆盖缺口的可修复性 (四值, 互不重叠)
FIX_NBS514 = "RECOVERABLE_NBS514_MANUAL_TRANSCRIPTION"
FIX_MANUAL = "RECOVERABLE_OTHER_MANUAL_TRANSCRIPTION"
FIX_PENDING = "RECOVERABLE_THERMOML_NOT_YET_INGESTED"
FIX_UNKNOWN = "NOT_EVALUATED_INGESTION_PATH_UNKNOWN"

PINNED: dict[str, tuple[str, int]] = {
    "a_core_set": ("630b0ee8c09dc4141124e335181572bf27a63f297a8df95f9c774683a10cf91b", 3149),
    "dielectric_v04": ("e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c", 134460),
    "observations_v11plus": ("159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9", 921601),
    "admission_gap": ("597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1", 50040),
    "candidate_master": ("63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d", 72349),
    "candidate_pool_C": ("c50f9349ec6de434f2b81d7a138292581fb661f4b1b9b1d54fdd3f7dc9055ba8", 9479),
    "evidence_backfill": ("7ef1502439b3422bc1792e6499cbb4e3b75ed3e3df6eaae7bdda7faedfce6cd2", 6178),
    "s4_preview": ("cb57ab59fb0f2d9f46809799ff173cbee83d230f66159a905ab6296a674eb73a", 4923),
    "target_protocol": ("0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4", 13420),
}

IDENTITY_COLUMNS: tuple[str, ...] = (
    "skeleton", "n_v04_rows", "resolution", "is_true_conflict",
    "aggregate_ids", "measurement_ids", "names", "inchikeys", "smiles",
    "T_K_values", "epsilon_values", "source_documents", "source_group_count",
    "conflict_status_values", "distinct_full_inchikey", "stereo_difference",
    "handling_rule", "downstream_action",
)

COVERAGE_COLUMNS: tuple[str, ...] = (
    "aggregate_id", "measurement_id", "molecule_key", "a_mol_id", "a_name",
    "v04_T_K", "v04_dielectric", "v04_n_observations", "source_doi",
    "source_mechanism", "ingestion_path", "gap_status",
    "has_observation", "recoverability", "recoverability_reason", "next_action",
)

WORKORDER_COLUMNS: tuple[str, ...] = (
    "order", "track", "work_id", "priority", "subject", "target", "action",
    "blocking_gate", "can_start_now", "acceptance",
)


class AuditError(RuntimeError):
    """输入缺失/结构不合法 (退出码 2)."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def skeleton(inchikey: str) -> str:
    text = (inchikey or "").strip()
    return text.split("-")[0] if text else ""


def read_csv_strict(path: Path, required: Sequence[str]) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise AuditError(f"输入缺失: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise AuditError(f"{path.name} 缺少必需列: {missing}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise AuditError(f"{path.name} 为空表")
    return rows


def joined(values: Iterable[str], sep: str = ";") -> str:
    return sep.join(sorted({v for v in values if v and str(v).strip()}))


def bool_text(flag: bool) -> str:
    return "true" if flag else "false"


NOT_EVALUATED = "not_evaluated"


def to_float(text: Any) -> float | None:
    raw = str(text).strip() if text is not None else ""
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[3]


def locate_inputs(workspace: Path, a_repo: Path | None) -> dict[str, Path]:
    workspace = Path(workspace)
    v56 = workspace / "v56_standalone"
    mirror = v56 / "app" / "电解质ML" / "电解质ML"
    drafts = v56 / "app" / "电解质ML" / "v56_round1"
    repo_a = Path(a_repo) if a_repo else Path(
        os.environ.get("J01_REPO_A", str(workspace.parent / "电解液溶剂-HB" / "电解液溶剂HB-Code"))
    )
    return {
        "a_core_set": repo_a / "data" / "metadata" / "core_set.csv",
        "dielectric_v04": mirror / "data" / "dielectric_v04.csv",
        "observations_v11plus": mirror / "data" / "processed" / "dielectric_observations_v11plus.csv",
        "admission_gap": drafts / "deliverables" / "experimental_epsilon_admission_gap.csv",
        "candidate_master": v56 / "reports" / "candidate_master_R001.csv",
        "candidate_pool_C": v56 / "reports" / "candidate_pool_C_R001.csv",
        "evidence_backfill": v56 / "reports" / "evidence_backfill_R001.csv",
        "s4_preview": drafts / "drafts" / "artifacts" / "s4_fold_DRAFT_INDICATIVE_R293.csv",
        "target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
    }


def verify_pinned(paths: Mapping[str, Path],
                  pins: Mapping[str, tuple[str, int]] = PINNED) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    for name in sorted(pins):
        expected, _ = pins[name]
        path = paths.get(name)
        if path is None or not Path(path).is_file():
            drift.append({"input": name, "expected": expected, "actual": "FILE_MISSING"})
            continue
        actual = sha256_file(Path(path))
        if actual != expected:
            drift.append({"input": name, "expected": expected, "actual": actual})
    return drift


# ---------------------------------------------------------------------------
# J05-A 身份冲突裁决
# ---------------------------------------------------------------------------

def classify_identity(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """判定一个骨架下多行的真实原因. 只返回三种处置之一."""
    full_keys = {str(r.get("inchikey", "")).strip() for r in rows}
    names = {str(r.get("name", "")).strip() for r in rows}
    values = [(to_float(r.get("T_K")), to_float(r.get("dielectric"))) for r in rows]
    distinct_values = len({(t, e) for t, e in values})
    sources = {str(r.get("source_doi", "")).strip() for r in rows}
    conflict = joined(str(r.get("conflict_status", "")) for r in rows)

    stereo = len(full_keys) > 1
    # 同名 + 同值 + 同源 = 重复登记; 否则同骨架不同值 = 真冲突
    if stereo:
        resolution = RES_ISOMER
        handling = "分别作为两个化合物保存; 禁止按骨架合并或平均"
        action = "在按骨架连接的分析中必须显式排除这两个骨架, 或改用完整 InChIKey 连接"
        true_conflict = False
    elif len(names) == 1 and distinct_values == 1 and len(sources) == 1:
        resolution = RES_DUPLICATE
        handling = "同一化合物同一来源重复登记; 保留一行并登记去重理由"
        action = "去重; 不改变聚合值"
        true_conflict = False
    else:
        resolution = RES_CONFLICT
        handling = "同一化合物、不同来源给出不同值; 属于真实未决冲突"
        action = "人工裁决 (保留并列或选主); 在裁决前不得选出代表值"
        true_conflict = True

    return {
        "resolution": resolution,
        "is_true_conflict": true_conflict,
        "stereo_difference": stereo,
        "distinct_full_inchikey": str(len(full_keys)),
        "handling_rule": handling,
        "downstream_action": action,
    }


def build_identity_resolution(
    v04: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    by_skeleton: dict[str, list[tuple[int, Mapping[str, str]]]] = defaultdict(list)
    for index, row in enumerate(v04, start=1):
        by_skeleton[skeleton(str(row.get("inchikey", "")))].append((index, row))

    multi = {k: v for k, v in by_skeleton.items() if len(v) > 1}
    rows_out: list[dict[str, str]] = []
    for key in sorted(multi):
        items = multi[key]
        source_rows = [r for _, r in items]
        verdict = classify_identity(source_rows)
        names = [str(r.get("name", "")).strip() for _, r in items]
        rows_out.append({
            "skeleton": key,
            "n_v04_rows": str(len(items)),
            "resolution": verdict["resolution"],
            "is_true_conflict": bool_text(verdict["is_true_conflict"]),
            "aggregate_ids": joined(f"v04row-{i:03d}" for i, _ in items),
            "measurement_ids": joined(f"EPSV04-R{i:03d}" for i, _ in items),
            "names": joined(names),
            "inchikeys": joined(str(r.get("inchikey", "")) for _, r in items),
            "smiles": joined(str(r.get("smiles", "")) for _, r in items),
            "T_K_values": joined(fmt(to_float(r.get("T_K"))) for _, r in items),
            "epsilon_values": joined(fmt(to_float(r.get("dielectric"))) for _, r in items),
            "source_documents": joined(str(r.get("source_doi", "")).split(";")[0] for _, r in items),
            "source_group_count": str(len({str(r.get("source_doi", "")).split(";")[0]
                                           for _, r in items})),
            "conflict_status_values": joined(str(r.get("conflict_status", "")) for _, r in items)
                                     or NOT_EVALUATED,
            "distinct_full_inchikey": verdict["distinct_full_inchikey"],
            "stereo_difference": bool_text(verdict["stereo_difference"]),
            "handling_rule": verdict["handling_rule"],
            "downstream_action": verdict["downstream_action"],
        })

    counts = Counter(r["resolution"] for r in rows_out)
    # A18 是否受影响 (按骨架)
    return rows_out, {
        "n_skeletons_with_multiple_rows": len(multi),
        "n_extra_rows": sum(len(v) - 1 for v in multi.values()),
        "resolution_counts": dict(sorted(counts.items())),
        "skeleton_join_risk": (
            "J01-J05 按 InChIKey 首段骨架连接. 立体异构体会折叠到同一骨架, "
            "因此骨架级计数对这类分子偏高. 本表列出全部受影响骨架及其处置."
        ),
    }


# ---------------------------------------------------------------------------
# J05-B 覆盖缺口
# ---------------------------------------------------------------------------

def classify_source_mechanism(v04_row: Mapping[str, str]) -> dict[str, str]:
    """按来源机制分类, 并给出可修复性判定. 判定必须落到机制上, 不是文件在哪."""
    doi = str(v04_row.get("source_doi", "")).strip()
    flags = str(v04_row.get("gate_flags", "")).strip()
    first = doi.split(";")[0].strip()
    notes: list[str] = []

    if NBS514_DOI in doi:
        mechanism = "NBS514_CIRCULAR_MANUAL_ENTRY"
        path = "literature_manual_entry"
        recoverable = FIX_NBS514
        reason = (
            "该记录来自 NBS Circular 514 印刷手册的人工转录 (gate_flags 含 "
            "literature_manual_entry|nbs514_circular_514); 观测层只承载 ThermoML 解析结果, "
            "因此这类记录本来就不会出现在 v11plus 里. 它是**机制性缺席**, 不是数据丢失"
        )
        action = "从 NBS514 原件逐页复核该行 (值、温度限定词、频率脚注), 补齐后可升级为可追溯"
    elif "literature_manual_entry" in flags:
        mechanism = "OTHER_MANUAL_ENTRY"
        path = "literature_manual_entry"
        recoverable = FIX_MANUAL
        reason = "gate_flags 标明人工录入, 观测层不承载此路径"
        action = "定位原始文献逐条复核"
    elif not flags:
        mechanism = "UNFLAGGED_NO_OBSERVATION"
        path = "unknown"
        recoverable = FIX_UNKNOWN
        reason = (
            "该行 gate_flags 为空且观测层无对应观测; 既不是 ThermoML 解析结果, "
            "也未标为人工录入, 录入路径不明"
        )
        action = "追溯该行的生成路径; 在路径明确前不得当作可核对记录"
    else:
        mechanism = "THERMOML_PATH_NO_OBSERVATION"
        path = "thermoml"
        recoverable = FIX_PENDING
        reason = (
            "该行标为 ThermoML 路径, 但观测层在当前 293.15-303.15 K / Liquid / 零频窗口内"
            "没有匹配观测; 可能原始数据落在窗口外或该 DOI 尚未重新摄取"
        )
        action = "检查该 DOI 的原始 XML 是否缺失, 并核对窗口外是否有可用点"
    return {
        "source_mechanism": mechanism,
        "ingestion_path": path,
        "recoverability": recoverable,
        "recoverability_reason": reason,
        "next_action": action,
    }


def build_coverage_registry(
    v04: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
    a18_by_skeleton: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    observed = {skeleton(str(r.get("inchikey", ""))) for r in observations}
    rows: list[dict[str, str]] = []
    for index, row in enumerate(v04, start=1):
        key = skeleton(str(row.get("inchikey", "")))
        owner = a18_by_skeleton.get(key)
        has_observation = key in observed
        if has_observation:
            continue  # 只登记缺口
        mechanism = classify_source_mechanism(row)
        rows.append({
            "aggregate_id": f"v04row-{index:03d}",
            "measurement_id": f"EPSV04-R{index:03d}",
            "molecule_key": str(row.get("inchikey", "")).strip(),
            "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
            "a_name": owner["a_name"] if owner else NOT_EVALUATED,
            # 保留 v04 原始字符串: 缺口登记是"照抄", 不做数值规范化
            "v04_T_K": str(row.get("T_K", "")).strip() or NOT_EVALUATED,
            "v04_dielectric": str(row.get("dielectric", "")).strip() or NOT_EVALUATED,
            "v04_n_observations": str(row.get("n_observations", "")).strip() or NOT_EVALUATED,
            "source_doi": str(row.get("source_doi", "")).strip() or NOT_EVALUATED,
            "source_mechanism": mechanism["source_mechanism"],
            "ingestion_path": mechanism["ingestion_path"],
            "gap_status": "NO_OBSERVATION_IN_SOURCE_LAYER",
            "has_observation": "false",
            "recoverability": mechanism["recoverability"],
            "recoverability_reason": mechanism["recoverability_reason"],
            "next_action": mechanism["next_action"],
        })

    by_mechanism = Counter(r["source_mechanism"] for r in rows)
    by_recover = Counter(r["recoverability"] for r in rows)
    a18_gap = [r for r in rows if r["a_mol_id"] != NOT_EVALUATED]
    return rows, {
        "n_rows_without_observation": len(rows),
        "by_source_mechanism": dict(sorted(by_mechanism.items())),
        "by_recoverability": dict(sorted(by_recover.items())),
        "n_a18_affected": len(a18_gap),
        "a18_affected": sorted(r["a_mol_id"] for r in a18_gap),
        "key_insight": (
            "绝大多数缺口不是'数据丢失', 而是**观测层承载范围**与 v04 录入路径不匹配: "
            "NBS514 人工转录行从设计上就不进观测层. 把这类缺口与真正的数据缺失混为一谈, "
            "会高估'需要重新取数'的量并低估'已有材料可复核'的量"
        ),
    }


# ---------------------------------------------------------------------------
# B02 工作单
# ---------------------------------------------------------------------------

def build_work_order(
    coverage_summary: Mapping[str, Any],
    identity_summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    order = 0

    def add(**kwargs: Any) -> None:
        nonlocal order
        order += 1
        rows.append({
            "order": str(order),
            "track": kwargs["track"],
            "work_id": kwargs["work_id"],
            "priority": kwargs["priority"],
            "subject": kwargs["subject"],
            "target": kwargs["target"],
            "action": kwargs["action"],
            "blocking_gate": kwargs["blocking_gate"],
            "can_start_now": kwargs["can_start_now"],
            "acceptance": kwargs["acceptance"],
        })

    add(track="A_STRUCTURE", work_id="B02-A1", priority="P0",
        subject="人工准入签批 (R252)",
        target="40 行候选池的人类质量审计",
        action="按 human_audit_worksheet_R007.csv 逐行判定并留痕",
        blocking_gate="NONE — 这是唯一能解锁 ACCEPT 的动作",
        can_start_now="true",
        acceptance="ACCEPT 行数 > 0, 且每行有 reviewer/date/decision")
    add(track="A_STRUCTURE", work_id="B02-A2", priority="P0",
        subject="NBS514 人工转录行复核",
        target=f"{coverage_summary['by_source_mechanism'].get('NBS514_CIRCULAR_MANUAL_ENTRY', 0)} 行",
        action="按原件逐页核对数值/温度限定词/频率脚注, 补齐后进入可追溯层",
        blocking_gate="none",
        can_start_now="true",
        acceptance="每行有 page-level 证据与复核人")
    add(track="A_STRUCTURE", work_id="B02-A3", priority="P0",
        subject="立体异构骨架连接修正",
        target=f"{identity_summary['n_skeletons_with_multiple_rows']} 个骨架 / "
               f"{identity_summary['n_extra_rows']} 条多余行",
        action="在确认分析前改用完整 InChIKey 连接, 或显式排除这些骨架",
        blocking_gate="B02-A1 (可并行)",
        can_start_now="true",
        acceptance="连接键改为完整 InChIKey, 且重跑后计数变化有说明")
    add(track="A_STRUCTURE", work_id="B02-A4", priority="P0",
        subject="gamma-valerolactone 双行冲突裁决",
        target="EPSV04-R227 (36.1) vs EPSV04-R248 (36.9)",
        action="核对两个来源原件, 决定保留并列还是选主; 裁决前不得选代表值",
        blocking_gate="none",
        can_start_now="true",
        acceptance="有 conflict_status 终态与裁决理由")
    add(track="B_EXTERNAL", work_id="B02-B1", priority="P0",
        subject="九个零观测分子取数",
        target="EC, PC, EMC, FEC, VC, DOL, EA, MA, TMP",
        action="按 P4 检索表逐分子找温度/相态/频率可核实的来源",
        blocking_gate="none — 不受结构修复阻塞",
        can_start_now="true",
        acceptance="每分子至少一条可追溯观测或明确 NOT_FOUND 证书")
    add(track="B_EXTERNAL", work_id="B02-B2", priority="P1",
        subject="SN 室温带补证",
        target="succinonitrile 293.15-303.15 K",
        action="检索该温度区间的静介电测量",
        blocking_gate="none",
        can_start_now="true",
        acceptance="找到则升级室温候选; 找不到则保留 333.15 K 并记 NOT_FOUND")
    add(track="B_EXTERNAL", work_id="B02-B3", priority="P1",
        subject="AN 静态频率补证",
        target="acetonitrile 现有证据仅 0.01/1 MHz",
        action="检索 static/零频测量, 并核对 v04 与 v11 来源冲突",
        blocking_gate="none",
        can_start_now="true",
        acceptance="有 static 证据且来源冲突已裁决")
    add(track="B_EXTERNAL", work_id="B02-B4", priority="P2",
        subject="ThermoML 路径无观测行核查",
        target=f"{coverage_summary['by_source_mechanism'].get('THERMOML_PATH_NO_OBSERVATION', 0)} 行",
        action="检查对应 DOI 的原始 XML 是否存在, 以及窗口外是否有可用点",
        blocking_gate="none",
        can_start_now="true",
        acceptance="每行标注 XML 存在性与窗口外点位")
    add(track="B_EXTERNAL", work_id="B02-B5", priority="P2",
        subject="无标记无观测行路径追溯",
        target=f"{coverage_summary['by_source_mechanism'].get('UNFLAGGED_NO_OBSERVATION', 0)} 行",
        action="追溯这些行的录入路径; 路径未明前不得当作可核对记录",
        blocking_gate="none",
        can_start_now="true",
        acceptance="每行有录入路径结论或 NOT_EVALUATED 标记")
    return rows


# ---------------------------------------------------------------------------
# 装配与渲染
# ---------------------------------------------------------------------------

INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 中性母体",
    "dielectric_v04": "v04 聚合主表",
    "observations_v11plus": "v11plus 观测层 (覆盖判定基准)",
    "admission_gap": "248 行 admission 缺口表",
    "candidate_master": "候选主表",
    "candidate_pool_C": "当前权威候选池",
    "evidence_backfill": "49 行机械证据回填",
    "s4_preview": "S4 折预览表",
    "target_protocol": "冻结协议",
}


def load_dataset(paths: Mapping[str, Path]) -> dict[str, Any]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    core = read_csv_strict(paths["a_core_set"], ("mol_id", "name", "smiles"))
    a18_by_skeleton: dict[str, dict[str, str]] = {}
    for row in core:
        mol = Chem.MolFromSmiles(str(row.get("smiles", "")))
        if mol is None:
            raise AuditError(f"SMILES 无法解析: {row.get('smiles')!r}")
        entry = dict(row)
        entry["a_mol_id"] = str(row.get("mol_id", "")).strip()
        entry["a_name"] = str(row.get("name", "")).strip()
        a18_by_skeleton[skeleton(Chem.MolToInchiKey(mol))] = entry
    v04 = read_csv_strict(
        paths["dielectric_v04"],
        ("inchikey", "smiles", "name", "T_K", "dielectric", "source_doi",
         "n_observations", "gate_flags", "conflict_status"),
    )
    observations = read_csv_strict(
        paths["observations_v11plus"],
        ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz", "source_doi"),
    )
    return {
        "a18_by_skeleton": a18_by_skeleton,
        "v04": v04,
        "observations": observations,
    }


def render_csv(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")


def render_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


OUTPUT_DIR_NAME = "identity_and_coverage"
OUTPUT_FILES: tuple[str, ...] = (
    "j05_inputs_manifest.json",
    "identity_conflict_resolution.csv",
    "coverage_gap_registry.csv",
    "b02_work_order.csv",
    "j05_summary.json",
    "j05_report.md",
    "j05_rebuild_receipt.json",
)


def build_report(
    *,
    identity_rows: Sequence[Mapping[str, str]],
    identity_summary: Mapping[str, Any],
    coverage_rows: Sequence[Mapping[str, str]],
    coverage_summary: Mapping[str, Any],
    work_order: Sequence[Mapping[str, str]],
    manifest: Mapping[str, Any],
) -> bytes:
    lines: list[str] = []
    add = lines.append
    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约: `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建")
    add("")
    add("## 1. 身份冲突裁决 (J05-A)")
    add("")
    add(f"发现 **{identity_summary['n_skeletons_with_multiple_rows']}** 个骨架各持多行, "
        f"共 **{identity_summary['n_extra_rows']}** 条多余行。")
    add("")
    add("| 骨架 | 行数 | 名称 | 处置 | 真冲突 | 完整键数 |")
    add("|---|---:|---|---|---|---:|")
    for row in identity_rows:
        add(f"| `{row['skeleton']}` | {row['n_v04_rows']} | {row['names']} | "
            f"`{row['resolution']}` | {row['is_true_conflict']} | "
            f"{row['distinct_full_inchikey']} |")
    add("")
    add(f"**骨架连接风险**: {identity_summary['skeleton_join_risk']}")
    add("")
    add("### 逐条处置")
    add("")
    add("| 骨架 | 值 | 规则 | 下游动作 |")
    add("|---|---|---|---|")
    for row in identity_rows:
        add(f"| `{row['skeleton']}` | T={row['T_K_values']} ε={row['epsilon_values']} | "
            f"{row['handling_rule']} | {row['downstream_action']} |")
    add("")
    add("## 2. 覆盖缺口登记 (J05-B)")
    add("")
    add(f"共有 **{coverage_summary['n_rows_without_observation']}** 条 v04 记录在观测层没有任何观测。")
    add("")
    add("| 来源机制 | 行数 |")
    add("|---|---:|")
    for mechanism, count in coverage_summary["by_source_mechanism"].items():
        add(f"| `{mechanism}` | {count} |")
    add("")
    add("| 可修复性 | 行数 |")
    add("|---|---:|")
    for key, count in coverage_summary["by_recoverability"].items():
        add(f"| `{key}` | {count} |")
    add("")
    add(f"**关键认知**: {coverage_summary['key_insight']}")
    add("")
    a18_rows = [r for r in coverage_rows if r["a_mol_id"] != NOT_EVALUATED]
    add(f"A18 受影响分子: {coverage_summary['n_a18_affected']} 个 "
        f"({', '.join(coverage_summary['a18_affected'])})。")
    add("")
    add("## 3. B02 工作单")
    add("")
    add("| 序 | 轨道 | 编号 | 优先级 | 任务 | 目标 | 可否立即开始 |")
    add("|---:|---|---|---|---|---|---|")
    for row in work_order:
        add(f"| {row['order']} | {row['track']} | {row['work_id']} | {row['priority']} | "
            f"{row['subject']} | {row['target']} | {row['can_start_now']} |")
    add("")
    add("### 逐项验收")
    add("")
    add("| 编号 | 前置门 | 验收标准 |")
    add("|---|---|---|")
    for row in work_order:
        add(f"| {row['work_id']} | {row['blocking_gate']} | {row['acceptance']} |")
    add("")
    add("## 4. 冻结输入")
    add("")
    add("| 输入 | bytes | sha256 |")
    add("|---|---:|---|")
    for entry in manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    add("## 5. 不做的事")
    add("")
    for item in (
        "不为立体异构体选择代表行, 不合并或平均它们的值",
        "不把「观测层没有」写成「观测为 0」或「值不存在」",
        "不修改 v04 / gap / pool_C / backfill / v11plus",
        "不改变 J01-J04 的冻结产物",
    ):
        add(f"- {item}")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_inputs_manifest(paths: Mapping[str, Path], environment: Mapping[str, str]) -> dict[str, Any]:
    inputs = []
    for name in sorted(paths):
        path = Path(paths[name])
        present = path.is_file()
        inputs.append({
            "id": name,
            "role": INPUT_ROLES.get(name, ""),
            "path": str(path),
            "bytes": path.stat().st_size if present else 0,
            "sha256": sha256_file(path) if present else "FILE_MISSING",
            "pinned": name in PINNED,
        })
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "inputs": inputs,
        "environment": dict(sorted(environment.items())),
    }


def collect_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(terse=True)}


def build_outputs(dataset: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    identity_rows, identity_summary = build_identity_resolution(dataset["v04"])
    coverage_rows, coverage_summary = build_coverage_registry(
        dataset["v04"], dataset["observations"], dataset["a18_by_skeleton"]
    )
    work_order = build_work_order(coverage_summary, identity_summary)

    # A18 是否受立体异构影响 (显式记录, 不让读者自己推)
    a18_keys = set(dataset["a18_by_skeleton"])
    stereo_keys = {r["skeleton"] for r in identity_rows if r["stereo_difference"] == "true"}
    a18_affected = sorted(a18_keys & stereo_keys)

    summary = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "identity": identity_summary,
        "identity_rows": identity_rows,
        "coverage": coverage_summary,
        "a18_affected_by_stereoisomer_folding": a18_affected,
        "a18_stereoisomer_risk": (
            "A18 全部落在单行骨架上, 立体异构折叠不触及 A18; "
            "但全量审计的骨架级计数对这 3 个骨架偏高"
            if not a18_affected else
            f"A18 中有 {len(a18_affected)} 个分子落在多行骨架: {a18_affected}"
        ),
        "work_order_counts": dict(Counter(r["priority"] for r in work_order)),
        "work_order_tracks": dict(Counter(r["track"] for r in work_order)),
    }
    files: dict[str, bytes] = {
        "j05_inputs_manifest.json": render_json(manifest),
        "identity_conflict_resolution.csv": render_csv(IDENTITY_COLUMNS, identity_rows),
        "coverage_gap_registry.csv": render_csv(COVERAGE_COLUMNS, coverage_rows),
        "b02_work_order.csv": render_csv(WORKORDER_COLUMNS, work_order),
        "j05_summary.json": render_json(summary),
        "j05_report.md": build_report(
            identity_rows=identity_rows, identity_summary=identity_summary,
            coverage_rows=coverage_rows, coverage_summary=coverage_summary,
            work_order=work_order, manifest=manifest,
        ),
    }
    receipt = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "output_sha256": {k: sha256_bytes(v) for k, v in sorted(files.items())},
        "output_bytes": {k: len(v) for k, v in sorted(files.items())},
    }
    files["j05_rebuild_receipt.json"] = render_json(receipt)
    missing = [n for n in OUTPUT_FILES if n not in files]
    if missing:
        raise AuditError(f"输出清单未产全: {missing}")
    return files


def write_outputs(out_dir: Path, files: Mapping[str, bytes]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (out_dir / name).write_bytes(files[name])


def check_outputs(out_dir: Path, files: Mapping[str, bytes]) -> list[str]:
    problems: list[str] = []
    for name in sorted(files):
        target = Path(out_dir) / name
        if not target.is_file():
            problems.append(f"缺失: {name}")
        elif target.read_bytes() != files[name]:
            problems.append(f"不一致: {name}")
    return problems


def default_out_dir(workspace: Path) -> Path:
    return Path(workspace) / "电解质ML" / "outputs" / "confirm_2027" / OUTPUT_DIR_NAME


def run(*, workspace: Path, a_repo: Path | None, out_dir: Path | None, check: bool,
        pins: Mapping[str, tuple[str, int]] = PINNED) -> int:
    paths = locate_inputs(workspace, a_repo)
    drift = verify_pinned(paths, pins)
    if drift:
        print("输入 SHA256 漂移 (拒绝出数):", file=sys.stderr)
        for item in drift:
            print(f"  {item['input']}: {item['expected'][:16]} != {item['actual'][:16]}",
                  file=sys.stderr)
        return 3
    missing = [n for n, p in paths.items() if not Path(p).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2
    dataset = load_dataset(paths)
    manifest = build_inputs_manifest(paths, collect_environment())
    files = build_outputs(dataset, manifest=manifest)
    target_dir = Path(out_dir) if out_dir else default_out_dir(workspace)
    if check:
        problems = check_outputs(target_dir, files)
        if problems:
            print("重建结果与现有产物不一致:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"OK 重建一致: {len(files)} 个文件 @ {target_dir}")
        return 0
    write_outputs(target_dir, files)
    summary = json.loads(files["j05_summary.json"].decode("utf-8"))
    print(f"{ANALYSIS_ID} 完成 -> {target_dir}")
    print(f"  身份冲突骨架: {summary['identity']['n_skeletons_with_multiple_rows']} "
          f"({summary['identity']['resolution_counts']})")
    print(f"  覆盖缺口: {summary['coverage']['n_rows_without_observation']} "
          f"{summary['coverage']['by_source_mechanism']}")
    print(f"  A18 受立体异构影响: {summary['a18_affected_by_stereoisomer_folding'] or 'none'}")
    print(f"  B02 工作单: {len(summary['work_order_counts'])} 类优先级, "
          f"{summary['work_order_tracks']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return run(workspace=Path(args.workspace), a_repo=args.a_repo,
               out_dir=args.out, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
