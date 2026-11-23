#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J02A | DME/TEGDME/GBL/DMSO 候选行排除原因复核.

要回答的唯一问题
----------------
这四个分子有 v11 观测、液相、static 0 Hz、压强齐全、温度在室温带 —— 它们为什么
不在 candidate_pool_C (49 行) 里? 是**有依据的科学排除**, 还是**候选行构建时漏掉
的机械失败**?

为什么不能靠"看起来像"来判断
----------------------------
pool_C 的生成器 (tools/build_candidate_pool_R001.py) 只做一件事:
    mids = [m for m in backfill if backfill[m]["status"] == "RESOLVED"]
而 evidence_backfill_R001.py 的 RESOLVED 需要 (molecule, source_doi, |ΔT|<0.01,
|Δeps|<1e-6) 命中**恰好一条** v11 观测. 所以一个分子不在 pool_C 里, 可能的原因有
至少六种, 彼此后果完全不同:
  * 真的没有实验数据;
  * 有数据但 ΔT 超容差 (GBL 的 gap 值是 295.65 K, 而源里最接近的是 293.15/298.15);
  * 有数据但同一 (mol,src) 键上命中多条 -> "need exactly 1" 判否 (TEGDME/DME);
  * gap 的 source_group 只是 v04 多来源串里的第一个, 导致按单键查找失败 (DMSO);
  * 命中了但 A5/A6/A7 有 false;
  * 构建时名单是显式声明的有限列表, 该 measurement 压根不在名单里.
把它们压成一个 "excluded" 会把"机械容差失败"和"科学不适用"混为一谈 —— 前者可以
零取数修复, 后者不能. 本模块逐条区分, 并且**只允许三种裁决**.

三种裁决 (由授权方规定)
-----------------------
* INTENTIONAL_EXCLUSION        存在明确、符合冻结协议的排除原因
* CANDIDATE_CONSTRUCTION_MISSING 符合冻结规则, 但候选行构建时遗漏
* REQUIRES_HUMAN_REVIEW        来源或科学条件仍存在不确定性

只有第二种允许启动 pool_C_v2 的候选行补建.

绝不做的
--------
* 不写 pool_C, 不改 evidence_backfill, 不改 gap 表, 不生成 v2 池;
* 不把"补建候选行"当成"获得合格标签"——补建只增加候选规模, 不增加 ACCEPT;
* 不对 v11 与 v11plus 的差异做合并; 两者分别报告.

确定性
------
同 J01: 无墙钟, 行序列序列序固定, 相同输入逐字节相同输出; `--check` 逐字节比较.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_ID = "B-G0-J02A"
ANALYSIS_TITLE = "DME/TEGDME/GBL/DMSO 候选行排除原因复核"
CONTRACT_VERSION = "confirm_2027.candidate_exclusion/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j02a_inputs/v1"
GENERATOR_VERSION = "audit_candidate_exclusion/1.0.0"

#: 本轮复核对象 (授权方点名), 顺序即报告顺序.
REVIEW_TARGETS: tuple[tuple[str, str], ...] = (
    ("C15", "DMSO"),
    ("C10", "TEGDME"),
    ("C08", "DME"),
    ("C13", "GBL"),
)

#: backfill 生成器的冻结匹配容差 (不能在本模块里改宽).
T_TOL = 0.01
EPS_TOL = 1e-6

VERDICT_INTENTIONAL = "INTENTIONAL_EXCLUSION"
VERDICT_MISSING = "CANDIDATE_CONSTRUCTION_MISSING"
VERDICT_HUMAN = "REQUIRES_HUMAN_REVIEW"

#: 机械失败原因 -> 是否可在不改科学条件的前提下补建
MECHANICAL_REASONS = frozenset({
    "GAP_SOURCE_GROUP_IS_FIRST_OF_MULTI",
    "TEMPERATURE_TOLERANCE_OVERFLOW",
    "EPSILON_TOLERANCE_OVERFLOW",
    "MULTIPLE_OBSERVATIONS_TOO_STRICT_UNIQUE_RULE",
    "MEASUREMENT_NOT_IN_DECLARED_LIST",
    "NO_EXACT_MATCH_GAP_VS_OBSERVATION",
})

#: 会把裁决抬到"人工复核"的原因 (来源归属或科学条件不确定)
HUMAN_REVIEW_REASONS = frozenset({
    "GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE",
    "GAP_EPSILON_IS_WITHIN_SOURCE_BAND_MEDIAN",
    "GAP_SOURCE_PROVENANCE_UNDOCUMENTED",
    "MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION",
    "GAP_SOURCE_GROUP_IS_FIRST_OF_MULTI",
    "RESOLVED_BUT_ABSENT_FROM_POOL_C",
    "EVIDENCE_FAILS_A5_A6_A7",
    "SCOPE_REVIEW_REQUIRED",
    "GAP_MARKED_REJECT",
})

PINNED: dict[str, tuple[str, int]] = {
    "candidate_master": ("63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d", 72349),
    "candidate_pool_C": ("c50f9349ec6de434f2b81d7a138292581fb661f4b1b9b1d54fdd3f7dc9055ba8", 9479),
    "evidence_backfill": ("7ef1502439b3422bc1792e6499cbb4e3b75ed3e3df6eaae7bdda7faedfce6cd2", 6178),
    "s4_preview": ("cb57ab59fb0f2d9f46809799ff173cbee83d230f66159a905ab6296a674eb73a", 4923),
    "admission_gap": ("597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1", 50040),
    "formal_draft": ("d2bfea53546f6197237f5b51d5fad9143eab4e3c842e1019ea6afe2e528d132a", 6312),
    "worksheet_40": ("2346b707c46e8204d01bc516556288f73a194b170887bf4324b9fcc160a0f1ab", 14056),
    "target_protocol": ("0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4", 13420),
}

OUTPUT_FILES: tuple[str, ...] = (
    "j02a_inputs_manifest.json",
    "candidate_exclusion_reconciliation.csv",
    "j02a_exclusion_summary.json",
    "j02a_review_report.md",
    "j02a_rebuild_receipt.json",
)

RECON_COLUMNS: tuple[str, ...] = (
    "review_order", "a_mol_id", "a_name", "observation_id", "evidence_group_id",
    "source_DOI", "source_row_index", "temperature_raw_K", "epsilon_raw",
    "temperature_band_v11", "temperature_band_protocol", "temperature_band_reconciliation",
    "candidate_pool_C", "master_preview", "decision_v2",
    "temperature_status", "phase_status", "frequency_status", "pressure_status",
    "human_admission", "backfill_status", "backfill_reason",
    "aggregation_path", "aggregation_is_cross_source", "aggregation_is_aggregate", "n_contributing_sources",
    "exclusion_reason", "exclusion_is_mechanical", "verdict", "evidence_note",
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


def to_float(text: Any) -> float | None:
    raw = str(text).strip() if text is not None else ""
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def band_of(temperature: float | None, windows: Sequence[Mapping[str, Any]]) -> str:
    if temperature is None:
        return "temperature_missing"
    for window in windows:
        if float(window["low"]) <= temperature <= float(window["high"]):
            return str(window["name"])
    return "outside_declared_window"


def joined(values: Iterable[str], sep: str = ";") -> str:
    return sep.join(sorted({v for v in values if v and str(v).strip()}))


NOT_EVALUATED = "not_evaluated"


def bool_text(flag: bool) -> str:
    return "true" if flag else "false"


# ---------------------------------------------------------------------------
# 路径与装载
# ---------------------------------------------------------------------------

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
        "candidate_master": v56 / "reports" / "candidate_master_R001.csv",
        "candidate_pool_C": v56 / "reports" / "candidate_pool_C_R001.csv",
        "evidence_backfill": v56 / "reports" / "evidence_backfill_R001.csv",
        "s4_preview": drafts / "drafts" / "artifacts" / "s4_fold_DRAFT_INDICATIVE_R293.csv",
        "admission_gap": drafts / "deliverables" / "experimental_epsilon_admission_gap.csv",
        "formal_draft": drafts / "deliverables" / "admission_v3_formal_decision_DRAFT.csv",
        "worksheet_40": v56 / "reports" / "human_audit_worksheet_R007.csv",
        "target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
        "observations_v11": mirror / "data" / "processed" / "dielectric_observations_v11.csv",
        "observations_v11plus": mirror / "data" / "processed" / "dielectric_observations_v11plus.csv",
        "dielectric_v04": mirror / "data" / "dielectric_v04.csv",
        "build_candidate_pool": v56 / "tools" / "build_candidate_pool_R001.py",
        "evidence_backfill_script": v56 / "tools" / "evidence_backfill_R001.py",
    }


def verify_pinned(paths: Mapping[str, Path], pins: Mapping[str, tuple[str, int]] = PINNED) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    for name in sorted(pins):
        expected, _bytes = pins[name]
        path = paths.get(name)
        if path is None:
            drift.append({"input": name, "expected": expected, "actual": "PATH_UNMAPPED"})
            continue
        if not Path(path).is_file():
            drift.append({"input": name, "expected": expected, "actual": "FILE_MISSING", "path": str(path)})
            continue
        actual = sha256_file(Path(path))
        if actual != expected:
            drift.append({"input": name, "expected": expected, "actual": actual})
    return drift


def load_protocol(path: Path) -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    windows = (document or {}).get("allowed_temperature_windows_K")
    if not isinstance(windows, list) or not windows:
        raise AuditError("target_protocol.yaml 缺温窗")
    return document


# ---------------------------------------------------------------------------
# 核心: 逐观测精确重建 backfill 的匹配判定
# ---------------------------------------------------------------------------

def match_observations(
    gap_row: Mapping[str, str],
    observations: Sequence[Mapping[str, str]],
    *,
    temperature_tolerance: float = T_TOL,
    epsilon_tolerance: float = EPS_TOL,
) -> dict[str, Any]:
    """按 backfill 的冻结规则在 (molecule, source_doi) 键上找精确匹配.

    返回匹配计数与最近候选, 供判定"机械失败"还是"科学排除". 不平均、不就近取温度.
    """
    molecule = str(gap_row.get("molecule_id", "")).strip()
    source = str(gap_row.get("source_group", "")).strip()
    temperature = to_float(gap_row.get("T_K"))
    epsilon = to_float(gap_row.get("epsilon"))

    on_key = [
        r for r in observations
        if str(r.get("inchikey", "")).strip() == molecule
        and str(r.get("source_doi", "")).strip() == source
    ]
    exact: list[dict[str, str]] = []
    nearest: list[tuple[float, float, dict[str, str]]] = []
    for row in on_key:
        obs_t = to_float(row.get("T_K"))
        obs_e = to_float(row.get("epsilon"))
        if obs_t is None or obs_e is None or temperature is None or epsilon is None:
            continue
        d_t = abs(obs_t - temperature)
        d_e = abs(obs_e - epsilon)
        nearest.append((d_t, d_e, dict(row)))
        if d_t < temperature_tolerance and d_e < epsilon_tolerance:
            exact.append(dict(row))
    nearest.sort(key=lambda item: (item[0], item[1]))
    return {
        "n_on_key": len(on_key),
        "n_exact": len(exact),
        "exact": exact,
        "nearest": nearest[:5],
        "gap_temperature": temperature,
        "gap_epsilon": epsilon,
        "gap_source": source,
        "gap_molecule": molecule,
    }


def classify_exclusion(
    *,
    match: Mapping[str, Any],
    backfill_row: Mapping[str, str] | None,
    gap_row: Mapping[str, str],
    in_pool_c: bool,
    in_preview: bool,
    window_band_of_gap: str,
    observation_band_of_nearest: str | None,
    aggregation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """只输出三种裁决. 机械失败可补建; 科学/来源不确定交人审.

    `aggregation` 给出该 measurement 在 v04 的聚合口径 (R219 带内中位数等). 只要
    gap 的 epsilon 不是单条观测值, 它就不可能被"精确匹配一条观测"复现 —— 这时
    "不在 pool_C" 是聚合口径与单观测口径的冲突, 不是构建遗漏, 必须交人审.
    """
    aggregation = aggregation or {}
    if in_pool_c:
        return {
            "verdict": None,
            "exclusion_reason": "NOT_EXCLUDED_PRESENT_IN_POOL_C",
            "is_mechanical": False,
        }

    reasons: list[str] = []
    mechanical = True

    n_exact = match["n_exact"]
    n_on_key = match["n_on_key"]
    backfill_status = str((backfill_row or {}).get("status", "")).strip()

    multi_source = ";" in str(gap_row.get("source_group", ""))
    if multi_source:
        reasons.append("GAP_SOURCE_GROUP_IS_FIRST_OF_MULTI")
        mechanical = False  # 但这不是科学排除, 是字段口径问题 -> 下面单独处理

    if backfill_row is None:
        reasons.append("MEASUREMENT_NOT_IN_DECLARED_LIST")
    elif backfill_status == "RESOLVED":
        reasons.append("RESOLVED_BUT_ABSENT_FROM_POOL_C")  # 内部不一致, 必须人审
        mechanical = False
    elif backfill_status == "EVIDENCE_FAILS_GATE":
        reasons.append("EVIDENCE_FAILS_A5_A6_A7")
        mechanical = False
    elif backfill_status == "UNRESOLVED":
        if n_exact == 0 and n_on_key == 0:
            reasons.append("NO_OBSERVATION_ON_GAP_SOURCE_KEY")
        elif n_exact == 0:
            reasons.append("NO_EXACT_MATCH_GAP_VS_OBSERVATION")
        elif n_exact > 1:
            reasons.append("MULTIPLE_OBSERVATIONS_TOO_STRICT_UNIQUE_RULE")
        else:
            reasons.append("BACKFILL_UNRESOLVED_WITHOUT_LOCAL_REPRODUCTION")
            mechanical = False

    # 用最近候选细分容差成因 (只做解释, 不改判定口径)
    nearest = match["nearest"]
    if nearest:
        d_t, d_e, _row = nearest[0]
        gap_t = match["gap_temperature"]
        gap_e = match["gap_epsilon"]
        if d_t >= T_TOL and gap_t is not None:
            reasons.append("TEMPERATURE_TOLERANCE_OVERFLOW")
        if d_e >= EPS_TOL and gap_e is not None:
            reasons.append("EPSILON_TOLERANCE_OVERFLOW")

    # 温度带口径冲突: gap 落在室温带, 但最近观测被 v11 判成窗外
    if window_band_of_gap == "room_temperature" and observation_band_of_nearest == "outside_declared_window":
        reasons.append("TEMPERATURE_BAND_DISAGREEMENT_V11_VS_PROTOCOL")

    # gap 的 epsilon 若是聚合值, 则"精确匹配一条观测"在定义上不可能成立
    if aggregation.get("is_aggregate"):
        if aggregation.get("is_cross_source_aggregate"):
            reasons.append("GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE")
        else:
            reasons.append("GAP_EPSILON_IS_WITHIN_SOURCE_BAND_MEDIAN")
        mechanical = False
    if aggregation.get("n_contributing_sources", 0) and not aggregation.get("aggregation_documented"):
        reasons.append("GAP_SOURCE_PROVENANCE_UNDOCUMENTED")
        mechanical = False
    if aggregation.get("is_cross_source_aggregate") and aggregation.get("n_contributing_sources", 0) > 1:
        reasons.append("MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION")
        mechanical = False

    # 任何"科学条件不确定"的上游信号都把裁决抬到人审
    qc_reason = str(gap_row.get("qc_reason", ""))
    if "scope_review_required" in qc_reason or "salt_form_identity" in qc_reason:
        reasons.append("SCOPE_REVIEW_REQUIRED")
        mechanical = False
    if str(gap_row.get("measurement_decision", "")).strip().upper() == "REJECT":
        reasons.append("GAP_MARKED_REJECT")
        mechanical = False

    if mechanical and reasons:
        verdict = VERDICT_MISSING
    elif reasons:
        # 只要有一条不是机械原因, 就不能自动补建
        verdict = VERDICT_HUMAN
    else:
        verdict = VERDICT_HUMAN
        reasons.append("NO_EXCLUSION_REASON_LOCATED")

    return {
        "verdict": verdict,
        "exclusion_reason": joined(reasons),
        "is_mechanical": mechanical,
    }


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def collect_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(terse=True)}


def build_reconciliation(
    dataset: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """逐观测一行的复核表. 一个分子可能有多条观测 -> 多条行, 不合并."""
    rows: list[dict[str, str]] = []
    order = 0
    for mol_id, name in REVIEW_TARGETS:
        order += 1
        core = dataset["core_by_mol"].get(mol_id)
        if core is None:
            raise AuditError(f"A 核心集里没有 {mol_id}")
        key = skeleton(dataset["inchikey_of"][mol_id])
        gap_row = dataset["gap_by_skeleton"].get(key)
        if gap_row is None:
            raise AuditError(f"gap 表里没有 {mol_id} 对应身份")
        measurement_id = str(gap_row.get("measurement_id", "")).strip()
        in_pool_c = measurement_id in dataset["pool_c_by_id"]
        preview_row = dataset["preview_by_skeleton"].get(key)
        in_preview = preview_row is not None

        match = match_observations(gap_row, dataset["observations_v11plus"])
        backfill_row = dataset["backfill_by_id"].get(measurement_id)
        gap_temperature = match["gap_temperature"]
        window_band = band_of(gap_temperature, windows)
        nearest_band = None
        if match["nearest"]:
            nearest_band = band_of(to_float(match["nearest"][0][2].get("T_K")), windows)

        aggregation = dataset["aggregation_by_id"].get(measurement_id)
        decision = classify_exclusion(
            match=match,
            backfill_row=backfill_row,
            gap_row=gap_row,
            in_pool_c=in_pool_c,
            in_preview=in_preview,
            window_band_of_gap=window_band,
            observation_band_of_nearest=nearest_band,
            aggregation=aggregation,
        )

        # 观测行: 命中则用命中行, 否则用最近候选解释成因; 两者都保留原始值
        chosen = match["exact"][0] if len(match["exact"]) == 1 else (
            match["nearest"][0][2] if match["nearest"] else None
        )
        if chosen is None:
            rows.append({
                "review_order": str(order), "a_mol_id": mol_id, "a_name": name,
                "observation_id": measurement_id, "evidence_group_id": NOT_EVALUATED,
                "source_DOI": str(gap_row.get("source_group", "")).strip(),
                "source_row_index": NOT_EVALUATED,
                "temperature_raw_K": fmt(gap_temperature), "epsilon_raw": fmt(match["gap_epsilon"]),
                "temperature_band_v11": NOT_EVALUATED, "temperature_band_protocol": window_band,
                "temperature_band_reconciliation": "NOT_EVALUATED",
                "candidate_pool_C": bool_text(in_pool_c),
                "master_preview": bool_text(in_preview),
                "decision_v2": str(gap_row.get("measurement_decision", "")).strip(),
                "temperature_status": "NO_OBSERVATION",
                "phase_status": "NO_OBSERVATION",
                "frequency_status": "NO_OBSERVATION",
                "pressure_status": "NO_OBSERVATION",
                "human_admission": "NOT_SIGNED",
                "backfill_status": str((backfill_row or {}).get("status", "NOT_IN_LIST")),
                "backfill_reason": str((backfill_row or {}).get("reason", NOT_EVALUATED)),
                "aggregation_path": (aggregation or {}).get("aggregation_path", NOT_EVALUATED),
                "aggregation_is_cross_source": bool_text(
                    bool((aggregation or {}).get("is_cross_source_aggregate"))
                ),
                "aggregation_is_aggregate": bool_text(
                    bool((aggregation or {}).get("is_aggregate"))
                ),
                "n_contributing_sources": str(
                    (aggregation or {}).get("n_contributing_sources", 0)
                ),
                "exclusion_reason": decision["exclusion_reason"],
                "exclusion_is_mechanical": bool_text(decision["is_mechanical"]),
                "verdict": decision["verdict"] or NOT_EVALUATED,
                "evidence_note": joined(["NO_V11_OBSERVATION_FOR_MOLECULE"]),
            })
            continue

        obs_temperature = to_float(chosen.get("T_K"))
        band_v11 = str(chosen.get("temperature_band", "")).strip() or NOT_EVALUATED
        band_protocol = band_of(obs_temperature, windows)
        frequency = to_float(chosen.get("frequency_mhz"))
        pressure = to_float(chosen.get("pressure_kpa"))
        phase = str(chosen.get("phase", "")).strip()
        notes: list[str] = []
        if band_v11 != band_protocol:
            notes.append("DECLARED_BAND_DIFFERS")
        if len(match["exact"]) > 1:
            notes.append("MULTIPLE_EXACT_MATCHES")
        if len(match["exact"]) == 0:
            notes.append("NO_EXACT_MATCH_USING_NEAREST_FOR_EXPLANATION")
        if abs((obs_temperature or 0.0) - (gap_temperature or 0.0)) >= T_TOL:
            notes.append("TEMPERATURE_DIFFERS_FROM_GAP_ROW")

        rows.append({
            "review_order": str(order),
            "a_mol_id": mol_id,
            "a_name": name,
            "observation_id": measurement_id,
            "evidence_group_id": f"proposed:EG-{measurement_id.replace('EPSV04-', '')}",
            "source_DOI": str(chosen.get("source_doi", "")).strip(),
            "source_row_index": str(chosen.get("source_row_index", "")).strip() or NOT_EVALUATED,
            "temperature_raw_K": fmt(obs_temperature),
            "epsilon_raw": fmt(to_float(chosen.get("epsilon"))),
            "temperature_band_v11": band_v11,
            "temperature_band_protocol": band_protocol,
            "temperature_band_reconciliation": (
                "AGREE" if band_v11 == band_protocol else "DISAGREE_V11_VS_PROTOCOL"
            ),
            "candidate_pool_C": bool_text(in_pool_c),
            "master_preview": bool_text(in_preview),
            "decision_v2": str(gap_row.get("measurement_decision", "")).strip(),
            "temperature_status": f"{band_protocol}@{fmt(obs_temperature)}K",
            "phase_status": "LIQUID" if phase.lower() == "liquid" else (phase.upper() or "UNKNOWN"),
            "frequency_status": (
                "STATIC_0HZ" if frequency == 0.0
                else (f"RF_{fmt(frequency)}MHZ" if frequency else "UNKNOWN")
            ),
            "pressure_status": (
                "PRESENT" if (pressure or 0.0) > 0.0 else "UNKNOWN"
            ),
            "human_admission": "NOT_SIGNED",
            "backfill_status": str((backfill_row or {}).get("status", "NOT_IN_LIST")),
            "backfill_reason": str((backfill_row or {}).get("reason", "")) or NOT_EVALUATED,
            "aggregation_path": (aggregation or {}).get("aggregation_path", NOT_EVALUATED),
            "aggregation_is_cross_source": bool_text(
                bool((aggregation or {}).get("is_cross_source_aggregate"))
            ),
            "aggregation_is_aggregate": bool_text(
                bool((aggregation or {}).get("is_aggregate"))
            ),
            "n_contributing_sources": str(
                (aggregation or {}).get("n_contributing_sources", 0)
            ),
            "exclusion_reason": decision["exclusion_reason"],
            "exclusion_is_mechanical": bool_text(decision["is_mechanical"]),
            "verdict": decision["verdict"] or NOT_EVALUATED,
            "evidence_note": joined(notes) or NOT_EVALUATED,
        })
    return rows


def build_summary(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    by_mol: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_mol.setdefault(row["a_mol_id"], {
            "a_name": row["a_name"],
            "verdicts": set(),
            "exclusion_reasons": set(),
            "observation_id": row["observation_id"],
            "in_pool_c": row["candidate_pool_C"],
            "in_preview": row["master_preview"],
            "temperature_raw_K": row["temperature_raw_K"],
            "temperature_band_protocol": row["temperature_band_protocol"],
            "backfill_status": row["backfill_status"],
        })
        entry["verdicts"].add(row["verdict"])
        entry["exclusion_reasons"].update(
            r for r in row["exclusion_reason"].split(";") if r
        )
    molecules = []
    counts = {VERDICT_INTENTIONAL: 0, VERDICT_MISSING: 0, VERDICT_HUMAN: 0}
    for mol_id in sorted(by_mol, key=lambda m: int(next(
        r["review_order"] for r in rows if r["a_mol_id"] == m))):
        entry = by_mol[mol_id]
        verdicts = {v for v in entry["verdicts"] if v and v != NOT_EVALUATED}
        verdict = (
            VERDICT_MISSING if verdicts == {VERDICT_MISSING}
            else VERDICT_INTENTIONAL if verdicts == {VERDICT_INTENTIONAL}
            else VERDICT_HUMAN
        )
        counts[verdict] = counts.get(verdict, 0) + 1
        molecules.append({
            "a_mol_id": mol_id,
            "a_name": entry["a_name"],
            "observation_id": entry["observation_id"],
            "verdict": verdict,
            "exclusion_reasons": sorted(entry["exclusion_reasons"]),
            "in_pool_c": entry["in_pool_c"],
            "master_preview": entry["in_preview"],
            "temperature_raw_K": entry["temperature_raw_K"],
            "temperature_band_protocol": entry["temperature_band_protocol"],
            "backfill_status": entry["backfill_status"],
            "pool_c_v2_construction_allowed": verdict == VERDICT_MISSING,
        })
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "n_review_targets": len(REVIEW_TARGETS),
        "verdict_counts": counts,
        "molecules": molecules,
        "rule": {
            "only_missing_allows_v2": True,
            "statement": "只有 CANDIDATE_CONSTRUCTION_MISSING 允许启动 pool_C_v2 候选行补建; "
                         "INTENTIONAL_EXCLUSION 保持原状态; REQUIRES_HUMAN_REVIEW 继续 HOLD",
            "candidate_construction_does_not_create_accept": True,
        },
    }


def build_outputs(
    dataset: Mapping[str, Any],
    *,
    inputs_manifest: Mapping[str, Any],
) -> dict[str, bytes]:
    windows = list(dataset["protocol"]["allowed_temperature_windows_K"])
    rows = build_reconciliation(dataset, windows)
    summary = build_summary(rows)

    files: dict[str, bytes] = {
        "j02a_inputs_manifest.json": render_json(inputs_manifest),
        "candidate_exclusion_reconciliation.csv": render_csv(RECON_COLUMNS, rows),
        "j02a_exclusion_summary.json": render_json(summary),
        "j02a_review_report.md": render_report(rows, summary, inputs_manifest),
    }
    receipt = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "excludes": ["wall-clock timestamps", "random seeds", "filesystem ordering"],
        "output_sha256": {k: sha256_bytes(v) for k, v in sorted(files.items())},
        "output_bytes": {k: len(v) for k, v in sorted(files.items())},
        "note": "本模块不写 pool_C / backfill / gap 表; 只产出复核证据",
    }
    files["j02a_rebuild_receipt.json"] = render_json(receipt)
    missing = [n for n in OUTPUT_FILES if n not in files]
    if missing:
        raise AuditError(f"输出清单未产全: {missing}")
    return files


def render_csv(columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")


def render_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_report(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
    inputs_manifest: Mapping[str, Any],
) -> bytes:
    lines: list[str] = []
    add = lines.append
    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约: `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建")
    add(f"- 复核对象: {len(REVIEW_TARGETS)} 个分子 ({', '.join(n for _m, n in REVIEW_TARGETS)})")
    add("")
    add("## 1. 三值裁决结果")
    add("")
    add("| 裁决 | 数量 |")
    add("|---|---:|")
    for key in (VERDICT_INTENTIONAL, VERDICT_MISSING, VERDICT_HUMAN):
        add(f"| `{key}` | {summary['verdict_counts'].get(key, 0)} |")
    add("")
    add("**只有 `CANDIDATE_CONSTRUCTION_MISSING` 允许启动 pool_C_v2 候选行补建。** "
        "补建候选行不产生任何 ACCEPT 标签, 也不改变 `primary_k` 门槛。")
    add("")
    add("## 2. 逐分子结论")
    add("")
    add("| mol | 名称 | 观测 | v11 idx 温度 | 协议温带 | in pool_C | preview | backfill | 裁决 | 可否补建 v2 |")
    add("|---|---|---|---:|---|---:|---:|---|---|---|")
    for entry in summary["molecules"]:
        add(f"| {entry['a_mol_id']} | {entry['a_name']} | {entry['observation_id']} | "
            f"{entry['temperature_raw_K']} | {entry['temperature_band_protocol']} | "
            f"{entry['in_pool_c']} | {entry['master_preview']} | {entry['backfill_status']} | "
            f"`{entry['verdict']}` | {bool_text(entry['pool_c_v2_construction_allowed'])} |")
    add("")
    add("## 3. 逐观测证据")
    add("")
    add("| mol | 观测 | 来源 | T_K | 带(v11) | 带(协议) | 相态 | 频率 | 压强 | 机械原因 | 裁决 |")
    add("|---|---|---|---:|---|---|---|---|---|---|---|")
    for row in rows:
        add(f"| {row['a_mol_id']} | {row['observation_id']} | {row['source_DOI']} | "
            f"{row['temperature_raw_K']} | {row['temperature_band_v11']} | "
            f"{row['temperature_band_protocol']} | {row['phase_status']} | "
            f"{row['frequency_status']} | {row['pressure_status']} | "
            f"{row['exclusion_is_mechanical']} | `{row['verdict']}` |")
    add("")
    add("## 4. 排除原因逐条")
    add("")
    add("| mol | 名称 | 原因码 | 说明 |")
    add("|---|---|---|---|")
    explanations = {
        "MEASUREMENT_NOT_IN_DECLARED_LIST": (
            "该 measurement 不在 backfill 的显式测量名单里, 从来没有进入候选资格链"
        ),
        "NO_EXACT_MATCH_GAP_VS_OBSERVATION": (
            "gap 行与 v11plus 观测在同一 (分子,来源) 键上不满足 |ΔT|<0.01 且 |Δeps|<1e-6"
        ),
        "TEMPERATURE_TOLERANCE_OVERFLOW": "gap 记录温度在源数据里没有精确对应温度点",
        "EPSILON_TOLERANCE_OVERFLOW": "gap 记录 epsilon 与源数据值不是一个数 (转录/取舍差异)",
        "MULTIPLE_OBSERVATIONS_TOO_STRICT_UNIQUE_RULE": (
            "同一键上命中多条观测, 冻结的 '恰好一条' 规则判否"
        ),
        "NO_OBSERVATION_ON_GAP_SOURCE_KEY": "gap 的 source_group 键在观测层找不到任何行",
        "GAP_SOURCE_GROUP_IS_FIRST_OF_MULTI": (
            "v04 该行有多个来源 DOI, gap 只取了第一个作为键"
        ),
        "TEMPERATURE_BAND_DISAGREEMENT_V11_VS_PROTOCOL": (
            "v11 的 temperature_band 与冻结协议温窗给出不同结论"
        ),
        "EVIDENCE_FAILS_A5_A6_A7": "命中观测但相态/频率/压强证据有一条不成立",
        "RESOLVED_BUT_ABSENT_FROM_POOL_C": "backfill 判 RESOLVED 却不在 pool_C — 内部不一致",
        "GAP_EPSILON_IS_CROSS_SOURCE_AGGREGATE": (
            "gap 的 epsilon 是多个来源在室温带内的中位数, 不是任何单条观测值; 归属不可辨识"
        ),
        "GAP_EPSILON_IS_WITHIN_SOURCE_BAND_MEDIAN": (
            "gap 的 epsilon 是同一来源在带内多条记录的中位数, 温度点已被中位化"
        ),
        "GAP_SOURCE_PROVENANCE_UNDOCUMENTED": "该 measurement 的聚合口径标为 NOT_DOCUMENTED",
        "MULTI_SOURCE_ROW_WITH_UNRESOLVED_ATTRIBUTION": (
            "该行汇总了多个来源, 但单条候选行无法声明自己归属哪一个来源"
        ),
    }
    seen: set[tuple[str, str]] = set()
    for entry in summary["molecules"]:
        for reason in entry["exclusion_reasons"]:
            if (entry["a_mol_id"], reason) in seen:
                continue
            seen.add((entry["a_mol_id"], reason))
            add(f"| {entry['a_mol_id']} | {entry['a_name']} | `{reason}` | "
                f"{explanations.get(reason, '见代码')} |")
    add("")
    add("## 5. 冻结输入")
    add("")
    add("| 输入 | bytes | sha256 |")
    add("|---|---:|---|")
    for entry in inputs_manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    add("## 6. 明确不做的事")
    add("")
    for item in (
        "不写 `candidate_pool_C_R001.csv`, 不写 `evidence_backfill_R001.csv`, 不改 gap 表",
        "不生成 pool_C_v2 (是否补建由人工依据本表裁决)",
        "不把补建候选行当作已获得合格标签",
        "不合并 v11 与 v11plus 的口径差异",
        "不修改 B-G0-J01 的任何冻结产物",
    ):
        add(f"- {item}")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_dataset(paths: Mapping[str, Path]) -> dict[str, Any]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    core = read_csv_strict(paths["a_core_set"], ("mol_id", "name", "smiles"))
    inchikey_of: dict[str, str] = {}
    core_by_mol: dict[str, dict[str, str]] = {}
    for row in core:
        mol = Chem.MolFromSmiles(str(row.get("smiles", "")))
        if mol is None:
            raise AuditError(f"SMILES 无法解析: {row.get('smiles')!r}")
        inchikey_of[str(row["mol_id"])] = Chem.MolToInchiKey(mol)
        core_by_mol[str(row["mol_id"])] = dict(row)

    gap = read_csv_strict(paths["admission_gap"],
                          ("molecule_id", "measurement_id", "source_group", "T_K",
                           "epsilon", "measurement_decision", "qc_reason"))
    pool_c = read_csv_strict(paths["candidate_pool_C"],
                             ("measurement_id", "molecule_id", "decision_v2"))
    backfill = read_csv_strict(paths["evidence_backfill"],
                               ("measurement_id", "molecule_id", "status", "reason"))
    preview = read_csv_strict(paths["s4_preview"],
                              ("molecule_id", "role", "measurement_ids"))
    observations = read_csv_strict(paths["observations_v11plus"],
                                   ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz",
                                    "pressure_kpa", "source_doi", "temperature_band"))
    master = read_csv_strict(paths["candidate_master"],
                             ("measurement_id", "molecule_id", "aggregation_path",
                              "sources_contributing", "n_contributing_sources"))
    gap_by_skeleton: dict[str, dict[str, str]] = {}
    for row in gap:
        gap_by_skeleton.setdefault(skeleton(row["molecule_id"]), dict(row))
    preview_by_skeleton = {skeleton(r["molecule_id"]): dict(r) for r in preview}
    aggregation_by_id: dict[str, dict[str, Any]] = {}
    for row in master:
        path_text = str(row.get("aggregation_path", "")).strip()
        sources = [x for x in str(row.get("sources_contributing", "")).split(";") if x.strip()]
        n_sources = len(sources)
        try:
            declared_n = int(str(row.get("n_contributing_sources", "")).strip() or 0)
        except ValueError:
            declared_n = 0
        # R219 带内中位数 = 聚合值 (不是单条观测); 其中 n>=2 个来源才是跨来源聚合.
        # 二者后果不同: 跨来源 = 归属不可辨识; 单来源带内 = 温度点被中位化.
        is_aggregate = "中位数" in path_text or "median" in path_text.lower()
        n_contributing = max(n_sources, declared_n)
        aggregation_by_id[str(row["measurement_id"]).strip()] = {
            "aggregation_path": path_text or NOT_EVALUATED,
            "aggregation_documented": path_text not in ("", "NOT_DOCUMENTED"),
            "is_aggregate": is_aggregate,
            "is_cross_source_aggregate": bool(is_aggregate and n_contributing >= 2),
            "n_contributing_sources": n_contributing,
            "sources_contributing": sorted(sources),
        }
    return {
        "core": core,
        "inchikey_of": inchikey_of,
        "core_by_mol": core_by_mol,
        "aggregation_by_id": aggregation_by_id,
        "gap": gap,
        "gap_by_skeleton": gap_by_skeleton,
        "pool_c_by_id": {str(r["measurement_id"]).strip(): dict(r) for r in pool_c},
        "backfill_by_id": {str(r["measurement_id"]).strip(): dict(r) for r in backfill},
        "preview_by_skeleton": preview_by_skeleton,
        "observations_v11plus": observations,
        "protocol": load_protocol(paths["target_protocol"]),
        "environment": collect_environment(),
    }


INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 中性母体 (身份来源)",
    "candidate_master": "v56 248 行候选主表 (in_49_preview 来源)",
    "candidate_pool_C": "v56 当前权威候选池 49 行",
    "evidence_backfill": "v56 49 行机械证据回填 (pool_C 的准入依据)",
    "s4_preview": "v56 S4 折预览表 (preview 的真实来源, 非候选池)",
    "admission_gap": "v56 248 行 admission 缺口表",
    "formal_draft": "v56 20 行 A1..A12 逐门草案",
    "worksheet_40": "v56 40 行人类签批工作表",
    "target_protocol": "v56 冻结协议 (温窗/门/never-default)",
    "observations_v11": "v11 观测层 1630 行 (对照)",
    "observations_v11plus": "v11plus 观测层 2065 行 (v11 的严格超集)",
    "dielectric_v04": "v04 主表 248 行",
    "build_candidate_pool": "pool_C 的生成器 (准入逻辑出处)",
    "evidence_backfill_script": "backfill 的生成器 (匹配规则出处)",
}


def build_inputs_manifest(paths: Mapping[str, Path], workspace: Path,
                          environment: Mapping[str, str]) -> dict[str, Any]:
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
        })
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "inputs": inputs,
        "environment": dict(sorted(environment.items())),
        "frozen_constants": {
            "T_TOL": T_TOL,
            "EPS_TOL": EPS_TOL,
            "review_targets": [{"mol_id": m, "name": n} for m, n in REVIEW_TARGETS],
        },
    }


def write_outputs(out_dir: Path, files: Mapping[str, bytes]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (out_dir / name).write_bytes(files[name])


def check_outputs(out_dir: Path, files: Mapping[str, bytes]) -> list[str]:
    problems: list[str] = []
    out_dir = Path(out_dir)
    for name in sorted(files):
        target = out_dir / name
        if not target.is_file():
            problems.append(f"缺失: {name}")
        elif target.read_bytes() != files[name]:
            problems.append(f"不一致: {name}")
    return problems


def run(*, workspace: Path, a_repo: Path | None, out_dir: Path, check: bool,
        pins: Mapping[str, tuple[str, int]] = PINNED) -> int:
    paths = locate_inputs(workspace, a_repo)
    drift = verify_pinned(paths, pins)
    if drift:
        print("输入 SHA256 漂移 (拒绝出数):", file=sys.stderr)
        for item in drift:
            print(f"  {item['input']}: expected {item['expected'][:16]} "
                  f"actual {item['actual'][:16]}", file=sys.stderr)
        return 3
    missing = [n for n, p in paths.items() if not Path(p).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2
    dataset = load_dataset(paths)
    manifest = build_inputs_manifest(paths, workspace, dataset["environment"])
    files = build_outputs(dataset, inputs_manifest=manifest)
    if check:
        problems = check_outputs(out_dir, files)
        if problems:
            print("重建结果与现有产物不一致:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"OK 重建一致: {len(files)} 个文件 @ {out_dir}")
        return 0
    write_outputs(out_dir, files)
    summary = json.loads(files["j02a_exclusion_summary.json"].decode("utf-8"))
    print(f"{ANALYSIS_ID} 完成 -> {out_dir}")
    for entry in summary["molecules"]:
        allowed = "v2_allowed" if entry["pool_c_v2_construction_allowed"] else "no_v2"
        print(f"  {entry['a_mol_id']} {entry['a_name']:7} {entry['verdict']:32} {allowed}")
    print(f"  输出 {len(files)} 个文件")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    out_dir = args.out or (workspace / "电解质ML" / "outputs" / "confirm_2027" / "intersections")
    return run(workspace=workspace, a_repo=args.a_repo, out_dir=out_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
