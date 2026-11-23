#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J03 | 聚合来源可追溯性检查器.

要回答的方法学问题
------------------
**聚合后的实验数据, 是否仍保留足够的来源可追溯性, 以支持后续材料筛选和独立证据
验证?** 这是一个可以逐行判定、可以计数、可以产生损失原因的工程问题, 不是判断题.

五个必须回答的检查维度
----------------------
1. 聚合类型   原始单条观测, 还是聚合值?
2. 测量数量   epsilon 实际由几条原始测量贡献?
3. 来源数量   涉及几个真正独立的来源文档?
4. 数值对应性 epsilon 与温度是否来自**同一条**真实观测?
5. 查找可行性 能否通过当前 `source_group` 精确回溯?

第 4 项是本模块的核心, 也是 `A3_aggregation_audit_R219.md` 已经点明但从未逐行落实的
事实: `dielectric_v04.csv` 的 `T_K` 与 `dielectric` 是**分别取中位数**得到的
(`build_dataset_v01.py: build_dielectric_compound_rows` —— `_median(temperatures)`
与 `_median(values)` 各算各的). 两个中位数可能落在不同的原始观测上, 于是
"(T_K, epsilon)" 这个组合可能**从来不是一次真实测量**. 把这种组合当实验记录使用,
就是在用两个不同实验的边拼出一个不存在的实验.

为什么必须从贡献记录重建, 不能从结果反推
----------------------------------------
`gap.source_group` 只保留了 v04 `source_doi` 分号串的第一个 DOI. DMSO 的 v04 行实际
有 4 个来源, gap 只写 1 个. 如果从 gap 反推来源, 会得出"单来源"的错误结论 —— 这正是
R302 记录的缺陷: "系统的缺陷是「只搜声明来源, 不搜全部贡献来源」".
因此本模块的贡献来源**只从带内原始观测重建**: 在 v04 的聚合窗口 (293.15-303.15 K,
Liquid, 零频) 内, 逐条取观测层的 `source_doi`.

六值裁决枚举 (只允许这些)
-------------------------
RAW_SINGLE_OBSERVATION        原始单条观测, 可直接核对
SINGLE_SOURCE_AGGREGATE       单来源多观测聚合, 回溯原始测量
MULTI_SOURCE_AGGREGATE        多来源聚合, 必须拆分来源
PROVENANCE_INCOMPLETE         来源贡献记录不完整, HOLD
AGGREGATION_UNDOCUMENTED      聚合规则不明, HOLD
COMPOSITE_CONDITION_UNMATCHED 温度与 epsilon 无法对应到同一实验, 人工复核

绝不做的
--------
* 不写 v04 / gap 表 / pool_C / backfill; 不生成准入记录; 不改 J01/J02 冻结产物;
* 不用聚合值构造"原始候选行";
* 不把"中位数恰好等于某条观测的某字段"当成"该条观测就是来源".

确定性
------
无墙钟, 行序/列序固定, 相同输入逐字节相同; `--check` 逐字节比较.
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
import statistics
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_ID = "B-G0-J03"
ANALYSIS_TITLE = "聚合来源可追溯性检查器"
CONTRACT_VERSION = "confirm_2027.aggregation_provenance/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j03_inputs/v1"
GENERATOR_VERSION = "audit_gap_aggregation_provenance/1.0.0"

#: v04 的聚合窗口 (R219 已锁定: p1 ThermoML 预过滤到 293.15-303.15 K)
BAND_LOW = 293.15
BAND_HIGH = 303.15
BAND_PHASE = "liquid"
BAND_FREQUENCY = "0"

# 六值裁决
V_RAW = "RAW_SINGLE_OBSERVATION"
V_SINGLE = "SINGLE_SOURCE_AGGREGATE"
V_MULTI = "MULTI_SOURCE_AGGREGATE"
V_INCOMPLETE = "PROVENANCE_INCOMPLETE"
V_UNDOCUMENTED = "AGGREGATION_UNDOCUMENTED"
V_COMPOSITE = "COMPOSITE_CONDITION_UNMATCHED"

VERDICTS: tuple[str, ...] = (V_RAW, V_SINGLE, V_MULTI, V_INCOMPLETE, V_UNDOCUMENTED, V_COMPOSITE)

#: 通过 (可进入下一步来源拆分/回填) 的裁决
PASSING_VERDICTS = frozenset({V_RAW, V_SINGLE})
#: 必须 HOLD 的裁决
HOLD_VERDICTS = frozenset({V_INCOMPLETE, V_UNDOCUMENTED})
#: 必须人工复核的裁决
REVIEW_VERDICTS = frozenset({V_MULTI, V_COMPOSITE})

PINNED: dict[str, tuple[str, int]] = {
    "a_core_set": ("630b0ee8c09dc4141124e335181572bf27a63f297a8df95f9c774683a10cf91b", 3149),
    "dielectric_v04": ("e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c", 134460),
    "observations_v11plus": ("159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9", 921601),
    "admission_gap": ("597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1", 50040),
    "candidate_master": ("63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d", 72349),
    "target_protocol": ("0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4", 13420),
}

OUTPUT_FILES: tuple[str, ...] = (
    "j03_inputs_manifest.json",
    "gap_aggregation_audit.csv",
    "source_contributor_map.csv",
    "measurement_reconstruction.csv",
    "lookup_feasibility.json",
    "aggregation_provenance_report.md",
    "j03_rebuild_receipt.json",
)

AUDIT_COLUMNS: tuple[str, ...] = (
    "measurement_id", "molecule_id", "a_mol_id", "a_name",
    "gap_T_K", "gap_epsilon", "gap_source_group", "gap_source_group_doi_count",
    "v04_T_K", "v04_epsilon", "v04_source_doi_count", "v04_source_dois_all",
    "aggregation_documented", "aggregation_rule",
    "in_band_n_observations", "v04_n_observations_declared",
    "n_contributing_measurements", "n_contributing_sources",
    "contributing_sources", "sources_lost_in_gap",
    "temperature_median_present_in_band", "epsilon_median_present_in_band",
    "pair_present_in_single_observation",
    "temperature_median_holders", "epsilon_median_holders",
    "single_source_lookup_possible", "lookup_successes",
    "verdict", "verdict_reason", "downstream_action",
)

CONTRIBUTOR_COLUMNS: tuple[str, ...] = (
    "measurement_id", "molecule_id", "source_doi", "n_observations_in_band",
    "n_distinct_temperature", "n_distinct_epsilon",
    "holds_temperature_median", "holds_epsilon_median",
    "is_first_in_gap_source_group", "present_in_gap_source_group",
    "observation_row_numbers",
)

RECONSTRUCTION_COLUMNS: tuple[str, ...] = (
    "measurement_id", "molecule_id", "observation_row_number", "T_K", "epsilon",
    "source_doi", "phase", "frequency_mhz", "pressure_kpa",
    "is_temperature_median", "is_epsilon_median", "is_exact_median_pair",
    "contributes_to_temperature", "contributes_to_epsilon",
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


def to_decimal(text: Any) -> Decimal | None:
    raw = str(text).strip() if text is not None else ""
    if not raw:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None


def to_float(text: Any) -> float | None:
    value = to_decimal(text)
    return float(value) if value is not None else None


def fmt_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    text = format(normalized, "f")
    return text if text else "0"


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


def split_dois(text: str) -> list[str]:
    return [d.strip() for d in str(text or "").split(";") if d.strip()]


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
        "dielectric_v04": mirror / "data" / "dielectric_v04.csv",
        "observations_v11plus": mirror / "data" / "processed" / "dielectric_observations_v11plus.csv",
        "admission_gap": drafts / "deliverables" / "experimental_epsilon_admission_gap.csv",
        "candidate_master": v56 / "reports" / "candidate_master_R001.csv",
        "target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
        "r219_audit": drafts / "reports" / "execution" / "A3_aggregation_audit_R219.md",
        "build_dataset": workspace / "电解质ML" / "scripts" / "build_dataset_v01.py",
    }


def verify_pinned(paths: Mapping[str, Path], pins: Mapping[str, tuple[str, int]] = PINNED) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    for name in sorted(pins):
        expected, _ = pins[name]
        path = paths.get(name)
        if path is None:
            drift.append({"input": name, "expected": expected, "actual": "PATH_UNMAPPED"})
            continue
        if not Path(path).is_file():
            drift.append({"input": name, "expected": expected, "actual": "FILE_MISSING"})
            continue
        actual = sha256_file(Path(path))
        if actual != expected:
            drift.append({"input": name, "expected": expected, "actual": actual})
    return drift


def load_protocol(path: Path) -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AuditError("target_protocol.yaml 顶层不是映射")
    return document


# ---------------------------------------------------------------------------
# 聚合证据重建 (从贡献记录, 不从结果反推)
# ---------------------------------------------------------------------------

def band_observations(
    observations: Sequence[Mapping[str, str]], molecule_id: str
) -> list[dict[str, str]]:
    """v04 聚合窗口内的原始观测: 293.15-303.15 K, Liquid, 零频, 数值齐全."""
    selected: list[dict[str, str]] = []
    for index, row in enumerate(observations, start=1):
        if str(row.get("inchikey", "")).strip() != molecule_id:
            continue
        temperature = to_decimal(row.get("T_K"))
        epsilon = to_decimal(row.get("epsilon"))
        if temperature is None or epsilon is None:
            continue
        if not (Decimal(str(BAND_LOW)) <= temperature <= Decimal(str(BAND_HIGH))):
            continue
        if str(row.get("phase", "")).strip().lower() != BAND_PHASE:
            continue
        if str(row.get("frequency_mhz", "")).strip() != BAND_FREQUENCY:
            continue
        entry = dict(row)
        entry["__row_number"] = str(index)
        entry["__T"] = temperature
        entry["__E"] = epsilon
        selected.append(entry)
    return selected


def reconstruct_aggregation(
    band: Sequence[Mapping[str, Any]],
    declared_n: int | None,
) -> dict[str, Any]:
    """从带内观测重建 R219 两段式中位数, 并判定 T 与 epsilon 是否同源.

    这是本模块最关键的函数: 它回答"温度与 epsilon 是否来自同一条真实观测".
    """
    temperatures = [row["__T"] for row in band]
    epsilons = [row["__E"] for row in band]
    median_temperature = statistics.median(temperatures) if temperatures else None
    median_epsilon = statistics.median(epsilons) if epsilons else None

    holders_temperature = [
        row for row in band if median_temperature is not None and row["__T"] == median_temperature
    ]
    holders_epsilon = [
        row for row in band if median_epsilon is not None and row["__E"] == median_epsilon
    ]
    exact_pairs = [
        row for row in band
        if median_temperature is not None and median_epsilon is not None
        and row["__T"] == median_temperature and row["__E"] == median_epsilon
    ]
    # 更宽松但仍严格的定义: 是否存在**某一条**观测, 其 (T,E) 就是 (medT, medE)
    pair_exists = len(exact_pairs) > 0

    return {
        "n_band": len(band),
        "declared_n": declared_n,
        "declared_n_matches": declared_n is not None and declared_n == len(band),
        "median_temperature": median_temperature,
        "median_epsilon": median_epsilon,
        "holders_temperature": holders_temperature,
        "holders_epsilon": holders_epsilon,
        "exact_pairs": exact_pairs,
        "temperature_median_present": len(holders_temperature) > 0,
        "epsilon_median_present": len(holders_epsilon) > 0,
        "pair_present": pair_exists,
        "sources": sorted({str(row.get("source_doi", "")).strip() for row in band
                           if str(row.get("source_doi", "")).strip()}),
    }


def lookup_feasibility(
    reconstruction: Mapping[str, Any],
    gap_source_group: str,
    band: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[dict[str, str]]]:
    """能否用 gap.source_group 单键精确回溯到一条观测.

    注意: 这里的"可行"指的是**用单键能查到东西**, 不代表查到的就是正确来源.
    多来源聚合时单键查找即便成功也只覆盖其中一个来源 —— 因此本源判定要与
    n_contributing_sources 一起看, 不能单独当成"可追溯".
    """
    attempts: list[dict[str, str]] = []
    group = gap_source_group.strip()
    hits = [row for row in band if str(row.get("source_doi", "")).strip() == group]
    attempts.append({
        "lookup_key": group,
        "n_hits": str(len(hits)),
        "hit_rows": ";".join(str(row["__row_number"]) for row in hits),
        "hit_sources": joined(str(row.get("source_doi", "")) for row in hits),
    })
    return len(hits) > 0, attempts


# ---------------------------------------------------------------------------
# 裁决
# ---------------------------------------------------------------------------

def decide_verdict(
    *,
    aggregation_documented: bool,
    reconstruction: Mapping[str, Any],
    gap_source_group_dois: int,
    n_contributing_sources: int,
    lookup_ok: bool,
) -> dict[str, str]:
    """按六值枚举裁决.

    判定顺序由**证据强度**决定, 不由字段是否缺失决定:
      1. 窗口内找不到观测 -> 无从重建 (INCOMPLETE)
      2. 窗口内恰好一条观测 -> 聚合在事实上是恒等的, 结果是硬证据, 可判 RAW.
         此时 aggregation_path 写 NOT_DOCUMENTED 只说明"口径没写", 不改变
         "实际上没发生聚合"这一事实 —— 若因字段空就抹掉硬证据, 会把最干净的
         行也压进 HOLD, 这不是保守, 是让口径缺失冒充科学不确定.
      3. 多条观测且口径未写明 -> 无法判定类型 (UNDOCUMENTED)
      4. 多条观测且 T/epsilon 不对应同一条 -> 合成条件对 (COMPOSITE)
      5. 其余按来源数分 SINGLE / MULTI
    """
    reasons: list[str] = []

    if reconstruction["n_band"] == 0:
        return {
            "verdict": V_INCOMPLETE,
            "reason": "NO_BAND_OBSERVATIONS_FOUND",
            "action": "HOLD: 聚合窗口内找不到贡献观测, 来源无法重建",
        }

    # 窗口内只有一条观测: 无论口径是否写明, 聚合都是恒等映射
    if reconstruction["n_band"] == 1:
        if n_contributing_sources > 1:
            return {
                "verdict": V_INCOMPLETE,
                "reason": "SINGLE_OBSERVATION_WITH_MULTIPLE_DECLARED_SOURCES",
                "action": "HOLD: 单条观测却有多个声明来源, 归属矛盾",
            }
        if not reconstruction["pair_present"]:
            return {
                "verdict": V_COMPOSITE,
                "reason": "SINGLE_OBSERVATION_BUT_MEDIANS_NOT_ON_IT",
                "action": "人工复核: 单观测窗口内中位数却不在该观测上, 说明聚合口径不一致",
            }
        reason = "SINGLE_OBSERVATION_BAND"
        if not aggregation_documented:
            reasons.append("AGGREGATION_RULE_NOT_DOCUMENTED_BUT_MOOT_SINGLE_OBSERVATION")
        return {
            "verdict": V_RAW,
            "reason": joined([reason, *reasons]),
            "action": "PASS: 原始单条观测, 可直接核对",
        }

    # 以下都是多条观测的窗口.
    # 先判合成条件对: 这一项**不依赖**聚合规则是否写明 —— 只要窗口内没有任何
    # 一条观测的 (T, epsilon) 等于 (中位数T, 中位数E), 这个组合就不是一次真实
    # 测量. 它是可证明的硬缺陷, 比"口径没写"更具体也更严重, 因此排在前面.
    if not reconstruction["pair_present"]:
        reasons = []
        if not reconstruction["temperature_median_present"]:
            reasons.append("TEMPERATURE_MEDIAN_NOT_AN_OBSERVED_VALUE")
        if not reconstruction["epsilon_median_present"]:
            reasons.append("EPSILON_MEDIAN_NOT_AN_OBSERVED_VALUE")
        reasons.insert(0, "MEDIAN_T_AND_EPSILON_FROM_DIFFERENT_OBSERVATIONS")
        if not aggregation_documented:
            reasons.append("AGGREGATION_RULE_NOT_DOCUMENTED")
        if not reconstruction["declared_n_matches"]:
            reasons.append("DECLARED_N_MISMATCH")
        return {
            "verdict": V_COMPOSITE,
            "reason": joined(reasons),
            "action": "人工复核: (T,epsilon) 组合不是一次真实测量, 禁止作为实验记录配对",
        }

    if not aggregation_documented:
        return {
            "verdict": V_UNDOCUMENTED,
            "reason": "AGGREGATION_RULE_NOT_DOCUMENTED_WITHOUT_BAND_INFERENCE",
            "action": "HOLD: 多条观测聚合但规则未写明, 无法判定聚合类型",
        }

    if not reconstruction["declared_n_matches"]:
        reasons.append("DECLARED_N_MISMATCH")
    if reconstruction["declared_n"] is None:
        reasons.append("DECLARED_N_ABSENT")

    if n_contributing_sources == 1:
        return {
            "verdict": V_SINGLE,
            "reason": "MULTIPLE_OBSERVATIONS_ONE_SOURCE",
            "action": "PASS: 单来源多观测聚合, 回溯到该来源的原始测量",
        }

    if n_contributing_sources > 1:
        if gap_source_group_dois < n_contributing_sources:
            reasons.append("GAP_SOURCE_GROUP_DROPS_CONTRIBUTORS")
        if not lookup_ok:
            reasons.append("SINGLE_KEY_LOOKUP_FAILS")
        return {
            "verdict": V_MULTI,
            "reason": joined(["MULTIPLE_CONTRIBUTING_SOURCES", *reasons]),
            "action": "必须拆分来源: 不得用单个 DOI 代表全部来源",
        }

    return {
        "verdict": V_INCOMPLETE,
        "reason": "SOURCE_ATTRIBUTION_EMPTY",
        "action": "HOLD: 贡献观测没有可用来源标识",
    }


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

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
        ("inchikey", "T_K", "dielectric", "source_doi", "n_observations", "source_dois_all"),
    )
    observations = read_csv_strict(
        paths["observations_v11plus"],
        ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz", "pressure_kpa", "source_doi"),
    )
    gap = read_csv_strict(
        paths["admission_gap"],
        ("molecule_id", "measurement_id", "source_group", "T_K", "epsilon", "measurement_decision"),
    )
    master = read_csv_strict(
        paths["candidate_master"],
        ("measurement_id", "molecule_id", "aggregation_path"),
    )
    return {
        "core": core,
        "a18_by_skeleton": a18_by_skeleton,
        "v04": v04,
        "v04_by_skeleton": {skeleton(r["inchikey"]): r for r in v04 if skeleton(r["inchikey"])},
        "observations": observations,
        "gap": gap,
        "master_by_id": {str(r["measurement_id"]).strip(): r for r in master},
        "protocol": load_protocol(paths["target_protocol"]),
    }


def build_audit(
    dataset: Mapping[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    audit_rows: list[dict[str, str]] = []
    contributor_rows: list[dict[str, str]] = []
    reconstruction_rows: list[dict[str, str]] = []
    feasibility: dict[str, Any] = {
        "analysis_id": ANALYSIS_ID,
        "window": {"low_K": BAND_LOW, "high_K": BAND_HIGH,
                   "phase": BAND_PHASE, "frequency_mhz": BAND_FREQUENCY},
        "criterion": ("能否用 gap.source_group 单键精确回溯; 单键命中不等于可追溯全部来源"),
        "per_measurement": [],
    }

    for gap_row in sorted(dataset["gap"], key=lambda r: str(r.get("measurement_id", ""))):
        molecule_id = str(gap_row.get("molecule_id", "")).strip()
        measurement_id = str(gap_row.get("measurement_id", "")).strip()
        gap_source_group = str(gap_row.get("source_group", "")).strip()
        gap_dois = split_dois(gap_source_group)
        v04_row = dataset["v04_by_skeleton"].get(skeleton(molecule_id))
        master_row = dataset["master_by_id"].get(measurement_id)
        owner = dataset["a18_by_skeleton"].get(skeleton(molecule_id))

        aggregation_path = str((master_row or {}).get("aggregation_path", "")).strip()
        aggregation_documented = aggregation_path not in ("", "NOT_DOCUMENTED")
        aggregation_rule = aggregation_path or NOT_EVALUATED

        band = band_observations(dataset["observations"], molecule_id)
        declared_n = None
        if v04_row is not None:
            declared_n = to_float(v04_row.get("n_observations"))
            declared_n = int(declared_n) if declared_n is not None else None
        reconstruction = reconstruct_aggregation(band, declared_n)
        lookup_ok, attempts = lookup_feasibility(reconstruction, gap_source_group, band)

        n_sources = len(reconstruction["sources"])
        decision = decide_verdict(
            aggregation_documented=aggregation_documented,
            reconstruction=reconstruction,
            gap_source_group_dois=len(gap_dois),
            n_contributing_sources=n_sources,
            lookup_ok=lookup_ok,
        )

        v04_dois = split_dois(str((v04_row or {}).get("source_doi", "")))
        v04_dois_all = split_dois(str((v04_row or {}).get("source_dois_all", "")))
        lost = sorted(set(reconstruction["sources"]) - set(gap_dois))

        holders_t = reconstruction["holders_temperature"]
        holders_e = reconstruction["holders_epsilon"]

        audit_rows.append({
            "measurement_id": measurement_id,
            "molecule_id": molecule_id,
            "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
            "a_name": owner["a_name"] if owner else NOT_EVALUATED,
            "gap_T_K": fmt_decimal(to_decimal(gap_row.get("T_K"))),
            "gap_epsilon": fmt_decimal(to_decimal(gap_row.get("epsilon"))),
            "gap_source_group": gap_source_group or NOT_EVALUATED,
            "gap_source_group_doi_count": str(len(gap_dois)),
            "v04_T_K": fmt_decimal(to_decimal((v04_row or {}).get("T_K"))),
            "v04_epsilon": fmt_decimal(to_decimal((v04_row or {}).get("dielectric"))),
            "v04_source_doi_count": str(len(v04_dois)),
            "v04_source_dois_all": ";".join(v04_dois_all) or NOT_EVALUATED,
            "aggregation_documented": bool_text(aggregation_documented),
            "aggregation_rule": aggregation_rule,
            "in_band_n_observations": str(reconstruction["n_band"]),
            "v04_n_observations_declared": str(reconstruction["declared_n"]) if reconstruction["declared_n"] is not None else NOT_EVALUATED,
            "n_contributing_measurements": str(reconstruction["n_band"]),
            "n_contributing_sources": str(n_sources),
            "contributing_sources": ";".join(reconstruction["sources"]) or NOT_EVALUATED,
            "sources_lost_in_gap": ";".join(lost) or NOT_EVALUATED,
            "temperature_median_present_in_band": bool_text(reconstruction["temperature_median_present"]),
            "epsilon_median_present_in_band": bool_text(reconstruction["epsilon_median_present"]),
            "pair_present_in_single_observation": bool_text(reconstruction["pair_present"]),
            "temperature_median_holders": ";".join(
                f"{fmt_decimal(r['__T'])}@{r['__row_number']}" for r in holders_t
            ) or NOT_EVALUATED,
            "epsilon_median_holders": ";".join(
                f"{fmt_decimal(r['__E'])}@{r['__row_number']}" for r in holders_e
            ) or NOT_EVALUATED,
            "single_source_lookup_possible": bool_text(lookup_ok),
            "lookup_successes": ";".join(a["lookup_key"] for a in attempts if int(a["n_hits"]) > 0) or NOT_EVALUATED,
            "verdict": decision["verdict"],
            "verdict_reason": decision["reason"],
            "downstream_action": decision["action"],
        })

        # 贡献来源映射 (从贡献记录重建)
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in band:
            by_source[str(row.get("source_doi", "")).strip() or NOT_EVALUATED].append(row)
        for source in sorted(by_source):
            rows = by_source[source]
            contributor_rows.append({
                "measurement_id": measurement_id,
                "molecule_id": molecule_id,
                "source_doi": source,
                "n_observations_in_band": str(len(rows)),
                "n_distinct_temperature": str(len({r["__T"] for r in rows})),
                "n_distinct_epsilon": str(len({r["__E"] for r in rows})),
                "holds_temperature_median": bool_text(any(r in holders_t for r in rows)),
                "holds_epsilon_median": bool_text(any(r in holders_e for r in rows)),
                "is_first_in_gap_source_group": bool_text(
                    bool(gap_dois) and source == gap_dois[0]
                ),
                "present_in_gap_source_group": bool_text(source in gap_dois),
                "observation_row_numbers": ";".join(str(r["__row_number"]) for r in rows),
            })

        for row in band:
            is_t = row in holders_t
            is_e = row in holders_e
            reconstruction_rows.append({
                "measurement_id": measurement_id,
                "molecule_id": molecule_id,
                "observation_row_number": str(row["__row_number"]),
                "T_K": fmt_decimal(row["__T"]),
                "epsilon": fmt_decimal(row["__E"]),
                "source_doi": str(row.get("source_doi", "")).strip() or NOT_EVALUATED,
                "phase": str(row.get("phase", "")).strip(),
                "frequency_mhz": str(row.get("frequency_mhz", "")).strip(),
                "pressure_kpa": str(row.get("pressure_kpa", "")).strip() or NOT_EVALUATED,
                "is_temperature_median": bool_text(is_t),
                "is_epsilon_median": bool_text(is_e),
                "is_exact_median_pair": bool_text(is_t and is_e),
                "contributes_to_temperature": bool_text(is_t),
                "contributes_to_epsilon": bool_text(is_e),
            })

        feasibility["per_measurement"].append({
            "measurement_id": measurement_id,
            "gap_source_group": gap_source_group or NOT_EVALUATED,
            "n_contributing_sources": n_sources,
            "gap_source_group_doi_count": len(gap_dois),
            "single_key_lookup_ok": lookup_ok,
            "single_key_lookup_covers_all_sources": bool(
                lookup_ok and n_sources == 1
            ),
            "attempts": attempts,
            "verdict": decision["verdict"],
        })

    feasibility["summary"] = {
        "n_measurements": len(audit_rows),
        "n_lookup_ok": sum(1 for r in audit_rows if r["single_source_lookup_possible"] == "true"),
        "n_lookup_covers_all_sources": sum(
            1 for e in feasibility["per_measurement"]
            if e["single_key_lookup_covers_all_sources"]
        ),
        "n_multi_source": sum(1 for r in audit_rows if r["n_contributing_sources"] not in ("0", "1")),
        "n_pair_unmatched": sum(
            1 for r in audit_rows if r["pair_present_in_single_observation"] == "false"
        ),
    }
    return audit_rows, contributor_rows, reconstruction_rows, feasibility


# ---------------------------------------------------------------------------
# 证据转化链
# ---------------------------------------------------------------------------

def build_evidence_funnel(
    audit_rows: Sequence[Mapping[str, str]], dataset: Mapping[str, Any]
) -> dict[str, Any]:
    """N_database → N_measurement → N_independent → N_condition_qualified → N_admitted.

    每一层都有自己的损失原因; 这是本模块要输给论文的方法学骨架, 不是新指标.
    """
    n_database = len(dataset["v04"])
    n_measurement = sum(int(r["in_band_n_observations"]) for r in audit_rows
                        if r["in_band_n_observations"].isdigit())
    independent = set()
    qualified = 0
    admitted = 0
    for row in audit_rows:
        sources = [s for s in row["contributing_sources"].split(";") if s and s != NOT_EVALUATED]
        independent.update(sources)
        if row["verdict"] in PASSING_VERDICTS:
            qualified += 1
    n_admitted = sum(
        1 for r in dataset["gap"]
        if str(r.get("measurement_decision", "")).strip().upper() == "ACCEPT"
    )
    reasons: dict[str, list[str]] = defaultdict(list)
    for row in audit_rows:
        reasons[row["verdict"]].append(row["measurement_id"])
    return {
        "chain": [
            {"stage": "N_database", "value": n_database,
             "definition": "v04 主表行数 (聚合后的化合物-条件行)",
             "loss_reason": NOT_EVALUATED},
            {"stage": "N_measurement", "value": n_measurement,
             "definition": "v04 聚合窗口内的原始观测条数 (逐行累加)",
             "loss_reason": "聚合把多条观测压成一行; 行数不等于测量数"},
            {"stage": "N_independent", "value": len(independent),
             "definition": "带内贡献观测涉及的独立来源文档数",
             "loss_reason": "同一来源的多条转录不构成独立证据"},
            {"stage": "N_condition_qualified", "value": qualified,
             "definition": "T 与 epsilon 可对应到同一次测量的行数",
             "loss_reason": "中位数分别计算导致组合不对应"},
            {"stage": "N_admitted", "value": n_admitted,
             "definition": "measurement_decision = ACCEPT 的行数",
             "loss_reason": "人工准入未完成"},
        ],
        "verdict_counts": {
            verdict: len(reasons.get(verdict, [])) for verdict in VERDICTS
        },
        "verdict_members": {verdict: sorted(reasons.get(verdict, [])) for verdict in VERDICTS},
        "key_finding": (
            "N_database 与 N_measurement 之间隔着聚合, N_measurement 与 N_independent 之间"
            "隔着来源去重, N_independent 与 N_condition_qualified 之间隔着合成条件对, "
            "N_condition_qualified 与 N_admitted 之间隔着人工准入。四个损失机制彼此独立。"
        ),
    }


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

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


def render_report(
    *,
    audit_rows: Sequence[Mapping[str, str]],
    feasibility: Mapping[str, Any],
    funnel: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bytes:
    lines: list[str] = []
    add = lines.append
    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约: `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建")
    add(f"- 聚合窗口: {BAND_LOW}-{BAND_HIGH} K, {BAND_PHASE}, {BAND_FREQUENCY} Hz")
    add("")
    add("## 1. 六值裁决分布")
    add("")
    add("| 裁决 | 行数 | 含义 | 后续 |")
    add("|---|---:|---|---|")
    meanings = {
        V_RAW: ("原始单条观测", "可直接核对"),
        V_SINGLE: ("单来源多观测聚合", "回溯原始测量"),
        V_MULTI: ("多来源聚合", "必须拆分来源"),
        V_INCOMPLETE: ("来源贡献记录不完整", "HOLD"),
        V_UNDOCUMENTED: ("聚合规则不明", "HOLD"),
        V_COMPOSITE: ("温度与 ε 无法对应到同一实验", "人工复核"),
    }
    for verdict in VERDICTS:
        meaning, action = meanings[verdict]
        add(f"| `{verdict}` | {funnel['verdict_counts'].get(verdict, 0)} | {meaning} | {action} |")
    add("")
    add("## 2. 证据转化链")
    add("")
    add("| 阶段 | 值 | 定义 | 该层损失原因 |")
    add("|---|---:|---|---|")
    for stage in funnel["chain"]:
        add(f"| `{stage['stage']}` | {stage['value']} | {stage['definition']} | "
            f"{stage['loss_reason']} |")
    add("")
    add(f"{funnel['key_finding']}")
    add("")
    add("## 3. 五个检查维度 (逐行)")
    add("")
    add("| 测量 | A18 | 带内 n | 来源数 | T中位数在带内 | ε中位数在带内 | 同条观测配对 | 单键回溯 | 裁决 |")
    add("|---|---|---:|---:|---|---|---|---|---|")
    for row in audit_rows:
        add(f"| {row['measurement_id']} | {row['a_mol_id'] if row['a_mol_id'] != NOT_EVALUATED else '—'} | "
            f"{row['in_band_n_observations']} | {row['n_contributing_sources']} | "
            f"{row['temperature_median_present_in_band']} | "
            f"{row['epsilon_median_present_in_band']} | "
            f"{row['pair_present_in_single_observation']} | "
            f"{row['single_source_lookup_possible']} | `{row['verdict']}` |")
    add("")
    add("## 4. 合成条件对 (T 与 ε 来自不同观测)")
    add("")
    composite = [r for r in audit_rows if r["pair_present_in_single_observation"] == "false"]
    if composite:
        add("| 测量 | A18 | gap (T, ε) | T 中位数持有者 | ε 中位数持有者 | 真实配对数 |")
        add("|---|---|---|---|---|---|")
        for row in composite:
            add(f"| {row['measurement_id']} | {row['a_mol_id']} | "
                f"({row['gap_T_K']}, {row['gap_epsilon']}) | "
                f"{row['temperature_median_holders']} | {row['epsilon_median_holders']} | 0 |")
        add("")
        add("这些 (T, ε) 组合**从未在同一次测量中出现过**。它们不得被当作实验记录配对使用, "
            "也不得据此构造原始候选行。")
    else:
        add("无。")
    add("")
    add("## 5. 来源可追溯性 (gap 丢失了哪些贡献来源)")
    add("")
    lost_rows = [r for r in audit_rows
                 if r["sources_lost_in_gap"] not in (NOT_EVALUATED, "")]
    if lost_rows:
        add("| 测量 | A18 | gap 声明 | 实际贡献来源 | 丢失 |")
        add("|---|---|---|---|---|")
        for row in lost_rows:
            add(f"| {row['measurement_id']} | {row['a_mol_id']} | `{row['gap_source_group']}` | "
                f"{row['n_contributing_sources']} 个 | `{row['sources_lost_in_gap']}` |")
        add("")
        add("来源从**实际贡献观测**重建, 不从聚合结果反推; 也不因为 gap 只写了第一个 DOI "
            "就丢掉其余来源。")
    else:
        add("无。")
    add("")
    add("## 6. 查找可行性")
    add("")
    summary = feasibility["summary"]
    add("| 指标 | 值 |")
    add("|---|---:|")
    add(f"| 测量行数 | {summary['n_measurements']} |")
    add(f"| 单键能查到东西 | {summary['n_lookup_ok']} |")
    add(f"| 单键能覆盖全部来源 | {summary['n_lookup_covers_all_sources']} |")
    add(f"| 多来源聚合行 | {summary['n_multi_source']} |")
    add(f"| 合成条件对行 | {summary['n_pair_unmatched']} |")
    add("")
    add("**关键区分**: 「单键能查到一条观测」与「单键能覆盖全部贡献来源」是两件事。"
        "多来源聚合行即便单键命中, 也只覆盖其中一个来源, 不构成完整可追溯。")
    add("")
    add("## 7. 冻结输入")
    add("")
    add("| 输入 | bytes | sha256 |")
    add("|---|---:|---|")
    for entry in manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    add("## 8. 对 B02 的前置门作用")
    add("")
    add("| 情况 | 允许 | 禁止 |")
    add("|---|---|---|")
    add("| 裁决通过 (`RAW_SINGLE_OBSERVATION` / `SINGLE_SOURCE_AGGREGATE`) | "
        "可进入来源回填与原始测量回溯 | — |")
    add("| 多来源聚合 (`MULTI_SOURCE_AGGREGATE`) | — | 用单个 DOI 代表多个来源; 必须先拆分 |")
    add("| 记录不全或规则不明 (`PROVENANCE_INCOMPLETE` / `AGGREGATION_UNDOCUMENTED`) | — | "
        "用聚合值构造原始候选行; 保留 HOLD |")
    add("| 合成条件对 (`COMPOSITE_CONDITION_UNMATCHED`) | — | 把 (T, ε) 当同一次实验配对 |")
    add("")
    add("零观测分子的原始文献检索不受本门限制, 可并行进行。")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 中性母体",
    "dielectric_v04": "v04 聚合主表 (被审计对象)",
    "observations_v11plus": "v11plus 原始观测层 (贡献记录来源)",
    "admission_gap": "248 行 admission 缺口表",
    "candidate_master": "聚合口径记录 (aggregation_path)",
    "target_protocol": "冻结协议温窗",
    "r219_audit": "R219 聚合规则审计 (规则出处)",
    "build_dataset": "聚合实现代码 (_median(T) 与 _median(E))",
}


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
        "band_window": {"low_K": BAND_LOW, "high_K": BAND_HIGH,
                        "phase": BAND_PHASE, "frequency_mhz": BAND_FREQUENCY},
        "verdict_enum": list(VERDICTS),
        "inputs": inputs,
        "environment": dict(sorted(environment.items())),
    }


def collect_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(terse=True)}


def build_outputs(dataset: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    audit_rows, contributor_rows, reconstruction_rows, feasibility = build_audit(dataset)
    funnel = build_evidence_funnel(audit_rows, dataset)
    feasibility = {**feasibility, "evidence_funnel": funnel}
    files: dict[str, bytes] = {
        "j03_inputs_manifest.json": render_json(manifest),
        "gap_aggregation_audit.csv": render_csv(AUDIT_COLUMNS, audit_rows),
        "source_contributor_map.csv": render_csv(CONTRIBUTOR_COLUMNS, contributor_rows),
        "measurement_reconstruction.csv": render_csv(RECONSTRUCTION_COLUMNS, reconstruction_rows),
        "lookup_feasibility.json": render_json(feasibility),
        "aggregation_provenance_report.md": render_report(
            audit_rows=audit_rows, feasibility=feasibility, funnel=funnel, manifest=manifest
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
        "note": "只读审计; 不写 v04/gap/pool_C/backfill, 不改 J01/J02 冻结产物",
    }
    files["j03_rebuild_receipt.json"] = render_json(receipt)
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
    manifest = build_inputs_manifest(paths, collect_environment())
    files = build_outputs(dataset, manifest=manifest)
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
    feasibility = json.loads(files["lookup_feasibility.json"].decode("utf-8"))
    counts = feasibility["evidence_funnel"]["verdict_counts"]
    print(f"{ANALYSIS_ID} 完成 -> {out_dir}")
    for verdict in VERDICTS:
        print(f"  {verdict:32} {counts.get(verdict, 0):4}")
    for stage in feasibility["evidence_funnel"]["chain"]:
        print(f"  {stage['stage']:24} {stage['value']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    out_dir = args.out or (workspace / "电解质ML" / "outputs" / "confirm_2027" / "provenance_audit")
    return run(workspace=workspace, a_repo=args.a_repo, out_dir=out_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
