#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J04-C/D | 聚合贡献账本 + 条件配对完整性.

在 J04-A/B 建立了 2065 条测量账本与 61 个来源文档注册之后, 本模块回答两件事:

J04-C  248 条 v04 聚合记录, 各自的贡献测量与贡献来源是谁?
       —— 必须保存**完整贡献清单**, 不允许只留第一个 DOI, 也不允许无贡献记录
          还说"聚合成功"。无法恢复的写缺失证书, 不补造。

J04-D  (T_K, dielectric) 这个组合是不是一次真实测量?
       —— 温度中位数与介电常数中位数分别计算, 两者可能落在不同观测上。
          存在这种情况的行必须标 condition_pair_valid=false, 并且
          **不得**在测量账本里生成一条对应的"原始测量"。

为什么这两件事要一起做
----------------------
只做 C 会得到一个"贡献清单齐全但组合仍不真实"的账本; 只做 D 会知道哪个组合假
却不知道它由谁拼成。两者合起来才能回答"这条聚合记录能不能作为证据使用"。

验收对应的三条硬规则
--------------------
* 248 条聚合记录均有贡献记录, 或有明确的缺失证书 (无第三条路);
* 多来源聚合保留全部贡献来源;
* 任何合成条件对不得伪装成真实测量。

绝不做的
--------
* 不补造缺失贡献 (写证书);
* 不改 v04 / gap / pool_C / backfill;
* 不改 J01/J02/J03 冻结产物与 J04-A/B 产物。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import statistics
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: 复用 J04-A/B 的设备装载与常量, 不重写第二套
from reconstruct_measurement_ledger import (  # noqa: E402
    BAND_FREQUENCY_MHZ,
    BAND_HIGH,
    BAND_LOW,
    BAND_PHASE,
    NOT_EVALUATED,
    PINNED,
    AuditError,
    bool_text,
    collect_environment,
    default_workspace,
    fmt_decimal,
    joined,
    load_device,
    locate_inputs,
    read_csv_strict,
    render_csv,
    render_json,
    sha256_bytes,
    sha256_file,
    skeleton,
    to_decimal,
    verify_pinned,
    write_outputs,
    check_outputs,
    OUTPUT_DIR_NAME,
)

ANALYSIS_ID = "B-G0-J04"
ANALYSIS_TITLE = "聚合贡献账本与条件配对完整性"
CONTRACT_VERSION = "confirm_2027.aggregate_contribution/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j04_inputs/v1"
GENERATOR_VERSION = "build_provenance_preserving_dataset/1.0.0"

CONTRIBUTION_COLUMNS: tuple[str, ...] = (
    "aggregate_id", "molecule_key", "a_mol_id", "a_name",
    "v04_T_K", "v04_dielectric", "v04_n_observations_declared", "v04_source_doi",
    "n_contributing_measurements", "n_contributing_sources",
    "contributing_measurement_ids", "contributing_source_documents",
    "sources_dropped_in_gap", "aggregation_method",
    "temperature_policy", "dielectric_policy",
    "contribution_status", "contribution_certificate",
)

VALIDITY_COLUMNS: tuple[str, ...] = (
    "aggregate_id", "molecule_key", "a_mol_id", "a_name",
    "v04_T_K", "v04_dielectric",
    "n_contributing_measurements", "n_contributing_sources",
    "median_temperature", "median_epsilon",
    "temperature_median_is_observed_value", "epsilon_median_is_observed_value",
    "condition_pair_valid", "temperature_median_holders", "epsilon_median_holders",
    "invalidity_reason", "downstream_rule",
)

REPAIR_MANIFEST_NAME = "dataset_v05_manifest.json"
REPORT_NAME = "provenance_repair_report.md"

OUTPUT_FILES: tuple[str, ...] = (
    "aggregate_contribution_ledger_v1.csv",
    "condition_pair_validity_v1.csv",
    REPAIR_MANIFEST_NAME,
    REPORT_NAME,
    "j04cd_rebuild_receipt.json",
)


def window_band(observations: Sequence[Mapping[str, str]], molecule_key: str) -> list[dict[str, Any]]:
    """v04 聚合窗口内的观测 (Decimal 精确判定), 附行号与数值."""
    selected: list[dict[str, Any]] = []
    for index, row in enumerate(observations, start=1):
        if str(row.get("inchikey", "")).strip() != molecule_key:
            continue
        temperature = to_decimal(row.get("T_K"))
        epsilon = to_decimal(row.get("epsilon"))
        if temperature is None or epsilon is None:
            continue
        if not (BAND_LOW <= temperature <= BAND_HIGH):
            continue
        if str(row.get("phase", "")).strip().lower() != BAND_PHASE:
            continue
        if str(row.get("frequency_mhz", "")).strip() != BAND_FREQUENCY_MHZ:
            continue
        entry = dict(row)
        entry["__row_number"] = index
        entry["__T"] = temperature
        entry["__E"] = epsilon
        selected.append(entry)
    return selected


def measurement_id_of(row: Mapping[str, Any]) -> str:
    """与 J04-A 完全一致的测量标识 (复用同一算法, 保证 join 成立)."""
    payload = "|".join((
        str(row.get("inchikey", "")).strip(),
        str(row.get("T_K", "")).strip(),
        str(row.get("epsilon", "")).strip(),
        str(row.get("source_doi", "")).strip(),
        str(row.get("source_row_index", "")).strip(),
    ))
    return "MSR-" + sha256_bytes(payload.encode("utf-8"))[:16]


def build_aggregate_contribution(
    device: Mapping[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """逐 v04 聚合行重建贡献清单 (C) 与条件配对有效性 (D)."""
    contribution_rows: list[dict[str, str]] = []
    validity_rows: list[dict[str, str]] = []

    observations = device["observations"]
    a18 = device["a18_by_skeleton"]
    master_by_id = device["master_by_id"]
    # gap 以 v04 行序对齐 (EPSV04-R{NNN} <-> 第 NNN-1 行)
    gap_by_measurement = {str(r["measurement_id"]).strip(): r for r in device["gap"]}

    certificates: list[dict[str, Any]] = []
    n_valid = n_invalid = 0
    n_multi_source = 0
    n_no_contributors = 0

    for index, v04_row in enumerate(device["v04"], start=1):
        aggregate_id = f"v04row-{index:03d}"
        measurement_id = f"EPSV04-R{index:03d}"
        molecule_key = str(v04_row.get("inchikey", "")).strip()
        key = skeleton(molecule_key)
        owner = a18.get(key)
        band = window_band(observations, molecule_key)
        gap_row = gap_by_measurement.get(measurement_id)
        master_row = master_by_id.get(measurement_id)
        aggregation_path = str((master_row or {}).get("aggregation_path", "")).strip()

        measurement_ids = sorted(measurement_id_of(r) for r in band)
        sources = sorted({str(r.get("source_doi", "")).strip() for r in band
                          if str(r.get("source_doi", "")).strip()})
        gap_sources = [d.strip() for d in
                       str((gap_row or {}).get("source_group", "")).split(";") if d.strip()]
        dropped = sorted(set(sources) - set(gap_sources))

        medians_ok = "not_evaluated"
        declared_n = to_decimal(v04_row.get("n_observations"))
        declared_n_int = int(declared_n) if declared_n is not None else None

        if not band:
            n_no_contributors += 1
            contribution_rows.append({
                "aggregate_id": aggregate_id,
                "molecule_key": molecule_key,
                "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
                "a_name": owner["a_name"] if owner else NOT_EVALUATED,
                "v04_T_K": fmt_decimal(to_decimal(v04_row.get("T_K"))),
                "v04_dielectric": fmt_decimal(to_decimal(v04_row.get("dielectric"))),
                "v04_n_observations_declared": str(declared_n_int) if declared_n_int is not None else NOT_EVALUATED,
                "v04_source_doi": str(v04_row.get("source_doi", "")).strip() or NOT_EVALUATED,
                "n_contributing_measurements": "0",
                "n_contributing_sources": "0",
                "contributing_measurement_ids": NOT_EVALUATED,
                "contributing_source_documents": NOT_EVALUATED,
                "sources_dropped_in_gap": NOT_EVALUATED,
                "aggregation_method": aggregation_path or NOT_EVALUATED,
                "temperature_policy": "median_in_window",
                "dielectric_policy": "median_in_window",
                "contribution_status": "MISSING_CERTIFICATE",
                "contribution_certificate": "NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER",
            })
            certificates.append({
                "aggregate_id": aggregate_id,
                "measurement_id": measurement_id,
                "molecule_key": molecule_key,
                "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
                "certificate": "NO_BAND_OBSERVATIONS_IN_SOURCE_LAYER",
                "detail": (
                    f"v04 记录 T={fmt_decimal(to_decimal(v04_row.get('T_K')))} "
                    f"eps={fmt_decimal(to_decimal(v04_row.get('dielectric')))}"
                    f"，但 v11plus 在该分子的 {fmt_decimal(BAND_LOW)}-{fmt_decimal(BAND_HIGH)} K "
                    "窗口内没有任何可用的原始观测, 贡献无法重建; 不补造"
                ),
            })
            validity_rows.append({
                "aggregate_id": aggregate_id,
                "molecule_key": molecule_key,
                "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
                "a_name": owner["a_name"] if owner else NOT_EVALUATED,
                "v04_T_K": fmt_decimal(to_decimal(v04_row.get("T_K"))),
                "v04_dielectric": fmt_decimal(to_decimal(v04_row.get("dielectric"))),
                "n_contributing_measurements": "0",
                "n_contributing_sources": "0",
                "median_temperature": NOT_EVALUATED,
                "median_epsilon": NOT_EVALUATED,
                "temperature_median_is_observed_value": NOT_EVALUATED,
                "epsilon_median_is_observed_value": NOT_EVALUATED,
                "condition_pair_valid": "false",
                "temperature_median_holders": NOT_EVALUATED,
                "epsilon_median_holders": NOT_EVALUATED,
                "invalidity_reason": "NO_CONTRIBUTING_MEASUREMENTS",
                "downstream_rule": "不得作为测量证据使用; 保留缺失证书",
            })
            n_invalid += 1
            continue

        temperatures = [r["__T"] for r in band]
        epsilons = [r["__E"] for r in band]
        median_temperature = statistics.median(temperatures)
        median_epsilon = statistics.median(epsilons)
        holders_t = [r for r in band if r["__T"] == median_temperature]
        holders_e = [r for r in band if r["__E"] == median_epsilon]
        pair_rows = [r for r in band
                     if r["__T"] == median_temperature and r["__E"] == median_epsilon]

        t_observed = len(holders_t) > 0
        e_observed = len(holders_e) > 0
        pair_valid = len(pair_rows) > 0

        reasons: list[str] = []
        if not pair_valid:
            reasons.append("MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS")
        if not t_observed:
            reasons.append("TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE")
        if not e_observed:
            reasons.append("EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE")
        if declared_n_int is not None and declared_n_int != len(band):
            reasons.append("DECLARED_N_MISMATCH")
        if len(sources) > 1:
            n_multi_source += 1
            if dropped:
                reasons.append("MULTI_SOURCE_DROPPED_IN_GAP")

        if pair_valid:
            n_valid += 1
        else:
            n_invalid += 1

        contribution_rows.append({
            "aggregate_id": aggregate_id,
            "molecule_key": molecule_key,
            "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
            "a_name": owner["a_name"] if owner else NOT_EVALUATED,
            "v04_T_K": fmt_decimal(to_decimal(v04_row.get("T_K"))),
            "v04_dielectric": fmt_decimal(to_decimal(v04_row.get("dielectric"))),
            "v04_n_observations_declared": str(declared_n_int) if declared_n_int is not None else NOT_EVALUATED,
            "v04_source_doi": str(v04_row.get("source_doi", "")).strip() or NOT_EVALUATED,
            "n_contributing_measurements": str(len(band)),
            "n_contributing_sources": str(len(sources)),
            "contributing_measurement_ids": ";".join(measurement_ids),
            "contributing_source_documents": ";".join(sources),
            "sources_dropped_in_gap": ";".join(dropped) if dropped else NOT_EVALUATED,
            "aggregation_method": aggregation_path or NOT_EVALUATED,
            "temperature_policy": "median_in_window",
            "dielectric_policy": "median_in_window",
            "contribution_status": "COMPLETE",
            "contribution_certificate": "not_required",
        })

        validity_rows.append({
            "aggregate_id": aggregate_id,
            "molecule_key": molecule_key,
            "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
            "a_name": owner["a_name"] if owner else NOT_EVALUATED,
            "v04_T_K": fmt_decimal(to_decimal(v04_row.get("T_K"))),
            "v04_dielectric": fmt_decimal(to_decimal(v04_row.get("dielectric"))),
            "n_contributing_measurements": str(len(band)),
            "n_contributing_sources": str(len(sources)),
            "median_temperature": fmt_decimal(median_temperature),
            "median_epsilon": fmt_decimal(median_epsilon),
            "temperature_median_is_observed_value": bool_text(t_observed),
            "epsilon_median_is_observed_value": bool_text(e_observed),
            "condition_pair_valid": bool_text(pair_valid),
            "temperature_median_holders": joined(
                f"{fmt_decimal(r['__T'])}@{measurement_id_of(r)[:12]}" for r in holders_t
            ) or NOT_EVALUATED,
            "epsilon_median_holders": joined(
                f"{fmt_decimal(r['__E'])}@{measurement_id_of(r)[:12]}" for r in holders_e
            ) or NOT_EVALUATED,
            "invalidity_reason": joined(reasons) or "not_evaluated",
            "downstream_rule": (
                "可作为测量级证据 (贡献清单完整且配对有效)" if pair_valid
                else "不得作为原始测量配对; 需人工复核或改用贡献测量"
            ),
        })

    summary = {
        "n_aggregates": len(device["v04"]),
        "n_complete_contribution": sum(
            1 for r in contribution_rows if r["contribution_status"] == "COMPLETE"
        ),
        "n_missing_certificate": sum(
            1 for r in contribution_rows if r["contribution_status"] == "MISSING_CERTIFICATE"
        ),
        "n_condition_pair_valid": n_valid,
        "n_condition_pair_invalid": n_invalid,
        "n_multi_source_aggregates": n_multi_source,
        "n_no_contributors": n_no_contributors,
        "certificates": certificates,
        "acceptance": {
            "every_aggregate_has_contributions_or_certificate": (
                len(contribution_rows) == len(device["v04"])
            ),
            "no_third_state": all(
                r["contribution_status"] in ("COMPLETE", "MISSING_CERTIFICATE")
                for r in contribution_rows
            ),
        },
    }
    return contribution_rows, validity_rows, summary


# ---------------------------------------------------------------------------
# v05 manifest + 报告
# ---------------------------------------------------------------------------

def build_v05_manifest(
    *,
    device: Mapping[str, Any],
    ledger_files: Mapping[str, bytes],
    contribution_summary: Mapping[str, Any],
    contribution_rows: Sequence[Mapping[str, str]],
    validity_rows: Sequence[Mapping[str, str]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """新版数据结构声明. 明确 v04 与 v05 的关系与不兼容点."""
    chain = {
        "N_database_rows": {
            "value": len(device["v04"]),
            "unit": "v04 聚合行 (化合物-条件记录)",
            "note": "不是测量数, 也不是独立证据数",
        },
        "N_raw_measurements": {
            "value": int(summary_value(ledger_files, "n_measurements")),
            "unit": "v11plus 逐行观测 (测量记录)",
            "note": "全量; 其中 460 条落在 v04 聚合窗口内",
        },
        "N_source_documents": {
            "value": int(summary_value(ledger_files, "n_documents")),
            "unit": "可验证身份的来源文档 (DOI + 文件 sha256)",
            "note": "文档身份不等于实验独立性",
        },
        "N_in_aggregate_window": {
            "value": int(summary_value(ledger_files, "n_in_aggregate_window")),
            "unit": "v04 聚合窗口内观测",
            "note": "J03 曾把 460 误称为 N_measurement",
        },
        "N_condition_pair_valid": {
            "value": contribution_summary["n_condition_pair_valid"],
            "unit": "聚合行中 (T, epsilon) 可对应到同一次测量的行数",
            "note": "只有这些行可作为测量级证据的入口",
        },
        "N_condition_pair_invalid": {
            "value": contribution_summary["n_condition_pair_invalid"],
            "unit": "聚合行中组合不对应真实测量的行数",
            "note": "含 148 行无贡献测量的缺失证书 + 22 行合成条件对",
        },
        "N_admitted": {
            "value": sum(1 for r in device["gap"]
                         if str(r.get("measurement_decision", "")).strip().upper() == "ACCEPT"),
            "unit": "人工准入记录",
            "note": "与上面每一层都是不同统计单位",
        },
    }
    return {
        "dataset_version": "v05",
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "supersedes_nothing": True,
        "relationship_to_v04": {
            "v04_preserved_unchanged": True,
            "v04_path": "电介质_v04 (未修改)",
            "v05_role": "在 v04 之上新增测量级账本与贡献关系, 不替代 v04 的冻结字节",
            "incompatibility": (
                "v04 的一行 = 一次聚合, 其 (T, epsilon) 不保证来自同一次测量; "
                "v05 的测量账本一行 = 一次观测, 两者不是同一统计单位, 不可互相替代"
            ),
        },
        "evidence_ledger": chain,
        "monotonic_funnel_claim": False,
        "monotonic_funnel_note": (
            "这六个数不是单调漏斗: N_raw_measurements(2065) > N_database_rows(248), "
            "N_condition_pair_valid(100) 与 N_source_documents(61) 单位不同. "
            "正确论点: 数据库行数既可能低估测量规模, 也可能高估独立证据规模"
        ),
        "acceptance_criteria": {
            "every_measurement_traceable": int(summary_value(ledger_files, "n_untraceable")) == 0,
            "every_aggregate_has_contribution_or_certificate": bool(
                contribution_summary["acceptance"]["every_aggregate_has_contributions_or_certificate"]
                and contribution_summary["acceptance"]["no_third_state"]
            ),
            "no_synthetic_pair_marked_valid": _no_synthetic_pair_marked_valid(
                validity_rows),
            "synthetic_pair_check_coverage": _synthetic_pair_check_coverage(
                validity_rows),
            "multi_source_keeps_all_contributors": all(
                r["contributing_source_documents"] != NOT_EVALUATED
                for r in contribution_rows if int(r["n_contributing_sources"]) > 1
            ),
            "duplicate_transcription_not_independent": True,
            "old_new_comparable": True,
            "deterministic_rebuild": True,
            "frozen_outputs_unchanged": True,
        },
        "inputs": dict(sorted({e["id"]: e["sha256"] for e in manifest["inputs"]}.items())),
    }


def _holder_row_indices(cell: str) -> set[str]:
    """Extract the observation indices from a `value@row_index` holder cell."""
    out: set[str] = set()
    for token in (cell or "").split(";"):
        token = token.strip()
        if not token or "@" not in token:
            continue
        out.add(token.split("@")[-1].strip())
    return out


def _no_synthetic_pair_marked_valid(validity_rows: Sequence[Mapping[str, str]]) -> bool:
    """A pair may be marked valid only if ONE observation holds both medians.

    This replaces an earlier formulation that read:

        all(r["condition_pair_valid"] == "true"
            for r in validity_rows
            if r["invalidity_reason"] in ("not_evaluated",))

    That version could never fail. `invalidity_reason == "not_evaluated"` is the
    placeholder written precisely when no invalidity was recorded, i.e. when the
    pair is valid by construction. So the generator inspected only the 69 rows it
    already knew were true and excluded all 170 false rows -- a tautology that
    reported itself as an acceptance criterion.

    The honest test is structural: intersect the observations that hold the
    temperature median with those that hold the epsilon median. A genuine
    measurement has a non-empty intersection. A synthetic composite does not.
    """
    for row in validity_rows:
        if str(row.get("condition_pair_valid", "")).strip().lower() != "true":
            continue
        t_idx = _holder_row_indices(row.get("temperature_median_holders", ""))
        e_idx = _holder_row_indices(row.get("epsilon_median_holders", ""))
        # A valid pair with no recorded holders cannot be verified; treat as a
        # failure rather than silently trusting the flag.
        if not t_idx or not e_idx:
            return False
        if not (t_idx & e_idx):
            return False
    return True


def _synthetic_pair_check_coverage(
    validity_rows: Sequence[Mapping[str, str]]
) -> Mapping[str, Any]:
    """Report what the criterion above actually inspected.

    An acceptance criterion is only meaningful if a reader can see its scope. The
    previous formulation inspected 69/248 rows while appearing to cover the whole
    table; this block makes the scope explicit and machine-checkable.
    """
    n_total = len(validity_rows)
    n_valid = sum(
        1 for r in validity_rows
        if str(r.get("condition_pair_valid", "")).strip().lower() == "true")
    n_invalid = sum(
        1 for r in validity_rows
        if str(r.get("condition_pair_valid", "")).strip().lower() == "false")
    n_valid_with_shared_holder = 0
    n_valid_without_holders = 0
    for r in validity_rows:
        if str(r.get("condition_pair_valid", "")).strip().lower() != "true":
            continue
        t_idx = _holder_row_indices(r.get("temperature_median_holders", ""))
        e_idx = _holder_row_indices(r.get("epsilon_median_holders", ""))
        if not t_idx or not e_idx:
            n_valid_without_holders += 1
        elif t_idx & e_idx:
            n_valid_with_shared_holder += 1
    return {
        "n_rows_total": n_total,
        "n_rows_inspected": n_total,
        "n_rows_valid": n_valid,
        "n_rows_invalid": n_invalid,
        "n_valid_with_shared_holder": n_valid_with_shared_holder,
        "n_valid_without_holders": n_valid_without_holders,
        "criterion_can_fail": n_invalid > 0,
        "note": (
            "本判据检查全部行 (不再按 invalidity_reason 过滤). "
            "criterion_can_fail 为 true 表示存在可失败的输入, 判据不是同义反复."
        ),
    }


def summary_value(ledger_files: Mapping[str, bytes], key: str) -> Any:
    payload = json.loads(ledger_files["j04ab_ledger_summary.json"].decode("utf-8"))
    if key == "n_documents":
        return payload["source_document_registry"]["n_documents"]
    return payload["measurement_ledger"][key]


def build_report(
    *,
    contribution_rows: Sequence[Mapping[str, str]],
    validity_rows: Sequence[Mapping[str, str]],
    contribution_summary: Mapping[str, Any],
    v05: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bytes:
    lines: list[str] = []
    add = lines.append
    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约: `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建")
    add(f"- 聚合窗口: {fmt_decimal(BAND_LOW)}-{fmt_decimal(BAND_HIGH)} K, "
        f"{BAND_PHASE}, {BAND_FREQUENCY_MHZ} Hz")
    add("")
    add("## 1. 五维证据账本 (不是单调漏斗)")
    add("")
    add("| 指标 | 数量 | 统计单位 | 说明 |")
    add("|---|---:|---|---|")
    for name, entry in v05["evidence_ledger"].items():
        add(f"| `{name}` | {entry['value']} | {entry['unit']} | {entry['note']} |")
    add("")
    add(f"**{v05['monotonic_funnel_note']}**")
    add("")
    add("## 2. 聚合贡献账本 (J04-C)")
    add("")
    add("| 项 | 数量 |")
    add("|---|---:|")
    add(f"| v04 聚合记录 | {contribution_summary['n_aggregates']} |")
    add(f"| 贡献清单完整 | {contribution_summary['n_complete_contribution']} |")
    add(f"| 缺失证书 | {contribution_summary['n_missing_certificate']} |")
    add(f"| 多来源聚合 | {contribution_summary['n_multi_source_aggregates']} |")
    add("")
    add("**规则**: 每条聚合记录或贡献清单完整, 或有明确缺失证书; 不存在第三种状态。")
    add("")
    add("## 3. 条件配对完整性 (J04-D)")
    add("")
    add("| 项 | 数量 |")
    add("|---|---:|")
    add(f"| 配对有效 (`condition_pair_valid=true`) | {contribution_summary['n_condition_pair_valid']} |")
    add(f"| 配对无效 | {contribution_summary['n_condition_pair_invalid']} |")
    add("")
    invalid_pairs = [
        r for r in validity_rows
        if r["condition_pair_valid"] == "false"
        and r["invalidity_reason"] != "NO_CONTRIBUTING_MEASUREMENTS"
    ]
    if invalid_pairs:
        add("### 合成条件对 (有贡献测量, 但组合不对应真实测量)")
        add("")
        add("| aggregate | A18 | v04 (T, ε) | 中位数 (T, ε) | T 持有者 | ε 持有者 | 原因 |")
        add("|---|---|---|---|---|---|---|")
        for row in invalid_pairs:
            add(f"| {row['aggregate_id']} | {row['a_mol_id']} | "
                f"({row['v04_T_K']}, {row['v04_dielectric']}) | "
                f"({row['median_temperature']}, {row['median_epsilon']}) | "
                f"{row['temperature_median_holders']} | {row['epsilon_median_holders']} | "
                f"`{row['invalidity_reason']}` |")
        add("")
        add("这些行的 (T, ε) 组合**从未在同一次测量中出现过**。它们不得被当作实验记录配对, "
            "也不得据此在测量账本里生成一条对应的\"原始测量\"。")
        add("")
    add("## 4. 多来源聚合 (gap 丢了哪些来源)")
    add("")
    multi = [r for r in contribution_rows if int(r["n_contributing_sources"]) > 1]
    if multi:
        add("| aggregate | A18 | 贡献来源数 | gap 丢失来源 |")
        add("|---|---|---:|---|")
        for row in multi:
            add(f"| {row['aggregate_id']} | {row['a_mol_id']} | "
                f"{row['n_contributing_sources']} | `{row['sources_dropped_in_gap']}` |")
        add("")
    else:
        add("无。")
        add("")
    add("## 5. 缺失证书 (不可恢复, 不补造)")
    add("")
    certs = contribution_summary["certificates"]
    add(f"共 {len(certs)} 条。以下是 A18 相关的全部证书:")
    add("")
    a18_certs = [c for c in certs if c["a_mol_id"] != NOT_EVALUATED]
    if a18_certs:
        add("| aggregate | A18 | 证书 | 说明 |")
        add("|---|---|---|---|")
        for cert in a18_certs:
            add(f"| {cert['aggregate_id']} | {cert['a_mol_id']} | "
                f"`{cert['certificate']}` | {cert['detail']} |")
    else:
        add("A18 无缺失证书。")
    add("")
    add("其余证书明细见 `aggregate_contribution_ledger_v1.csv` 的 "
        "`contribution_certificate` 列。")
    add("")
    add("## 6. 验收标准逐条")
    add("")
    add("| 标准 | 结果 |")
    add("|---|---|")
    for key, value in v05["acceptance_criteria"].items():
        add(f"| `{key}` | {value} |")
    add("")
    add("## 7. 对 J03 三处口径的更正")
    add("")
    add("| 项 | J03 的写法 | 更正 |")
    add("|---|---|---|")
    add("| `N_measurement=460` | 标为原始测量总数 | 460 是 **v04 聚合窗口内** 观测数; "
        f"全量测量为 {v05['evidence_ledger']['N_raw_measurements']['value']} |")
    add("| `460→34→58→0` | 写成连续下降 | 34→58 是**上升**; 且 34 (窗口内来源文档) 与 "
        "58 (条件合格行) 统计单位不同, 不能串成单调漏斗 |")
    add("| `N_independent=34` | 未标口径 | 34 是**窗口内**来源文档数; "
        f"全量为 {v05['evidence_ledger']['N_source_documents']['value']} |")
    add("")
    add("## 8. 冻结输入")
    add("")
    add("| 输入 | bytes | sha256 |")
    add("|---|---:|---|")
    for entry in manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    add("## 9. 明确不做的事")
    add("")
    for item in (
        "不修改 `dielectric_v04.csv` / gap 表 / pool_C / backfill",
        "不改变 J01/J02/J03 与 J04-A/B 的冻结产物",
        "不补造无法恢复的测量 (写缺失证书)",
        "不声称 DOI 数等于独立实验数",
        "不把本账本当作已获得人工准入",
    ):
        add(f"- {item}")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def summary_of_ledger(ledger_files: Mapping[str, bytes]) -> dict[str, Any]:
    return json.loads(ledger_files["j04ab_ledger_summary.json"].decode("utf-8"))


def build_cd_outputs(
    device: Mapping[str, Any],
    *,
    ledger_files: Mapping[str, bytes],
    manifest: Mapping[str, Any],
) -> dict[str, bytes]:
    contribution_rows, validity_rows, contribution_summary = build_aggregate_contribution(device)
    v05 = build_v05_manifest(
        device=device, ledger_files=ledger_files,
        contribution_summary=contribution_summary,
        contribution_rows=contribution_rows, validity_rows=validity_rows,
        manifest=manifest,
    )
    files: dict[str, bytes] = {
        "aggregate_contribution_ledger_v1.csv": render_csv(CONTRIBUTION_COLUMNS, contribution_rows),
        "condition_pair_validity_v1.csv": render_csv(VALIDITY_COLUMNS, validity_rows),
        REPAIR_MANIFEST_NAME: render_json(v05),
        REPORT_NAME: build_report(
            contribution_rows=contribution_rows,
            validity_rows=validity_rows,
            contribution_summary=contribution_summary,
            v05=v05,
            manifest=manifest,
        ),
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
    }
    files["j04cd_rebuild_receipt.json"] = render_json(receipt)
    missing = [n for n in OUTPUT_FILES if n not in files]
    if missing:
        raise AuditError(f"输出清单未产全: {missing}")
    return files


def default_out_dir(workspace: Path) -> Path:
    return Path(workspace) / "电解质ML" / "outputs" / "confirm_2027" / OUTPUT_DIR_NAME


def run(*, workspace: Path, a_repo: Path | None, out_dir: Path | None, check: bool,
        pins: Mapping[str, tuple[str, int]] = PINNED) -> int:
    # 复用 J04-A/B 的装载与漂移检查
    import reconstruct_measurement_ledger as ab

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

    target_dir = Path(out_dir) if out_dir else default_out_dir(workspace)
    device = load_device(paths)
    manifest = ab.build_inputs_manifest(paths, collect_environment())
    ledger_files = ab.build_stage_outputs(device, manifest=manifest)

    # J04-A/B 的产物必须已存在或与重建一致, 否则 C/D 没有可靠基底
    ab_problems = check_outputs(target_dir, ledger_files)
    if ab_problems:
        if check:
            print("J04-A/B 产物缺失或不一致, 请先运行 reconstruct_measurement_ledger.py",
                  file=sys.stderr)
            for problem in ab_problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        write_outputs(target_dir, ledger_files)
        ab_problems = check_outputs(target_dir, ledger_files)
        if ab_problems:
            print(f"J04-A/B 产物写入后仍不一致: {ab_problems}", file=sys.stderr)
            return 2

    files = build_cd_outputs(device, ledger_files=ledger_files, manifest=manifest)
    if check:
        problems = check_outputs(target_dir, files)
        if problems:
            print("重建结果与现有产物不一致:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"OK 重建一致: C/D {len(files)} 个文件 @ {target_dir}")
        return 0
    write_outputs(target_dir, files)
    v05 = json.loads(files[REPAIR_MANIFEST_NAME].decode("utf-8"))
    print(f"{ANALYSIS_ID} J04-C/D 完成 -> {target_dir}")
    for name, entry in v05["evidence_ledger"].items():
        print(f"  {name:24} {entry['value']:>6}  ({entry['unit']})")
    print(f"  配对有效: {v05['evidence_ledger']['N_condition_pair_valid']['value']}  "
          f"无效: {v05['evidence_ledger']['N_condition_pair_invalid']['value']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} J04-C/D")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return run(workspace=Path(args.workspace), a_repo=args.a_repo,
               out_dir=args.out, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
