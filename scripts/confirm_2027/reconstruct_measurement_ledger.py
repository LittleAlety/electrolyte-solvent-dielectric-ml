#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J04-A/B | 测量级数据重建 + 来源文档注册.

要解决的问题
------------
B-G0-J03 证明: `dielectric_v04.csv` 的 `(T_K, dielectric)` 是把窗口内观测的
**温度中位数与介电常数中位数分别计算**得到的两个独立中位数, 因此这个组合可能
从来不是一次真实测量; 而 `gap.source_group` 只保留了多个贡献来源里的第一个 DOI.
两者叠加, 使"聚合记录"不能被安全地当作"测量证据"使用.

本模块做的事: 把聚合结果**还原回它的贡献测量**, 并让每一条测量都带上可核对的
来源身份. 它不改 v04, 不覆盖 J01/J02/J03 产物, 只新增一层测量级账本.

对 J03 三处口径的更正 (写进产物, 不静默改)
------------------------------------------
1. J03 把 "460" 标成 `N_measurement`. 460 实际上是 **v04 聚合窗口 (293.15-303.15 K,
   Liquid, 0 Hz) 内的观测数**, 不是全量测量数. 全量 v11plus 是 2065. 本模块因此
   把测量账本做成全量, 并把 460 降级为一个派生计数 (`in_aggregate_window`).
2. J03 写 "460→34→58→0 连续下降". 34→58 是**上升**, 且 34 (窗口内来源文档) 与
   58 (条件合格行) 统计单位不同, 不能串成单调漏斗. 本模块改用五维并列账本.
3. J03 的 `N_independent=34` 是**窗口内**来源数. 全量 v11plus 有 61 个来源文档.
   两个数各自成立, 但必须标明口径.

关键区分: 文档身份 != 实验独立性
--------------------------------
DOI 数不等于独立实验数. 不同文献可能报告同一批实验, 或共享同一上游数据.
本模块只记录**可验证的**文档身份 (DOI + 文件 sha256), 并把实验独立性单独标为
`not_evaluated`, 附上"需要外部证据才能判定"的说明 —— 不用文档数冒充实验数.

绝不做的
--------
* 不补造无法恢复的测量 (缺失写证书, 不写值);
* 不修改 v04 / gap / pool_C / backfill;
* 不改变 J01/J02/J03 冻结产物;
* 不声称 DOI 数就是独立实验数.

确定性
------
无墙钟, 行序/列序固定, Decimal 精确运算, 相同输入逐字节相同; `--check` 逐字节比较.
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

ANALYSIS_ID = "B-G0-J04"
ANALYSIS_TITLE = "测量级数据重建与来源文档注册"
CONTRACT_VERSION = "confirm_2027.measurement_ledger/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j04_inputs/v1"
GENERATOR_VERSION = "reconstruct_measurement_ledger/1.0.0"

#: v04 聚合窗口 (R219 冻结: p1 ThermoML 预过滤到 293.15-303.15 K)
BAND_LOW = Decimal("293.15")
BAND_HIGH = Decimal("303.15")
BAND_PHASE = "liquid"
BAND_FREQUENCY_MHZ = "0"

#: 从 J03 复用的契约常量 (不在此重新定义语义)
from audit_gap_aggregation_provenance import (  # noqa: E402
    NOT_EVALUATED,
    V_COMPOSITE,
    V_INCOMPLETE,
    V_RAW,
    V_SINGLE,
    band_observations as _j03_band_observations,
    reconstruct_aggregation as _j03_reconstruct,
)

PINNED: dict[str, tuple[str, int]] = {
    "a_core_set": ("630b0ee8c09dc4141124e335181572bf27a63f297a8df95f9c774683a10cf91b", 3149),
    "dielectric_v04": ("e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c", 134460),
    "observations_v11plus": ("159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9", 921601),
    "admission_gap": ("597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1", 50040),
    "candidate_master": ("63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d", 72349),
    "target_protocol": ("0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4", 13420),
}

LEDGER_COLUMNS: tuple[str, ...] = (
    "measurement_id", "molecule_key", "a_mol_id", "a_name", "inchikey",
    "temperature_K", "dielectric", "epsilon_unit", "phase",
    "frequency_mhz", "frequency_hz", "pressure_kpa",
    "source_document_id", "source_file", "source_file_sha256", "source_row_index",
    "evidence_group_id", "experimental_independence_unit",
    "property_name", "property_family", "method",
    "temperature_band_v11", "in_roster", "model_ready",
    "in_aggregate_window", "aggregate_id", "traceability_status", "traceability_note",
)

SOURCE_COLUMNS: tuple[str, ...] = (
    "source_document_id", "n_observations", "n_molecules", "n_static_zero_hz",
    "n_in_aggregate_window", "source_file", "source_file_sha256",
    "document_identity_verified", "experimental_independence_unit",
    "experimental_independence_status", "independence_note",
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


def fmt_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value.normalize(), "f")
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


def joined(values: Iterable[str], sep: str = ";") -> str:
    return sep.join(sorted({v for v in values if v and str(v).strip()}))


def bool_text(flag: bool) -> str:
    return "true" if flag else "false"


# ---------------------------------------------------------------------------
# 路径
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


# ---------------------------------------------------------------------------
# 测量账本 (J04-A) 与来源注册 (J04-B)
# ---------------------------------------------------------------------------

def measurement_id_for(row: Mapping[str, str]) -> str:
    """确定性测量标识: 只由内容决定, 不由遍历顺序决定.

    不补造: 标识来自原始字段拼串, 同一行永远得到同一 id.
    """
    payload = "|".join((
        str(row.get("inchikey", "")).strip(),
        str(row.get("T_K", "")).strip(),
        str(row.get("epsilon", "")).strip(),
        str(row.get("source_doi", "")).strip(),
        str(row.get("source_row_index", "")).strip(),
    ))
    return "MSR-" + sha256_bytes(payload.encode("utf-8"))[:16]


def frequency_hz(row: Mapping[str, str]) -> str:
    """MHz -> Hz. 用 Decimal 精确换算, 空值保持空 (不补 0)."""
    value = to_decimal(row.get("frequency_mhz"))
    if value is None:
        return ""
    return fmt_decimal(value * Decimal(1000))


def build_measurement_ledger(
    device: Mapping[str, Any]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """全量测量账本. 每条 v11plus 观测一行, 标明是否进入某个聚合窗口."""
    observations = device["observations"]
    a18 = device["a18_by_skeleton"]

    # 聚合窗口内观测 -> 归属 aggregate_id (v04 行)。多头归属单独记, 不静默取一个
    window_owner: dict[int, list[str]] = defaultdict(list)
    for aggregate_id, v04_row in device["v04_by_index"].items():
        key = skeleton(v04_row["inchikey"])
        band = _j03_band_observations(observations, v04_row["inchikey"].strip())
        for row in band:
            window_owner[int(row["__row_number"]) - 1].append(aggregate_id)

    rows: list[dict[str, str]] = []
    for index, observation in enumerate(observations):
        molecule = str(observation.get("inchikey", "")).strip()
        key = skeleton(molecule)
        owner = a18.get(key)
        owners = window_owner.get(index, [])
        temperature = to_decimal(observation.get("T_K"))
        epsilon = to_decimal(observation.get("epsilon"))
        document = str(observation.get("source_doi", "")).strip()

        notes: list[str] = []
        if not document:
            notes.append("MISSING_SOURCE_DOCUMENT")
            status = "UNTRACEABLE_NO_SOURCE"
        elif not str(observation.get("source_file_sha256", "")).strip():
            notes.append("MISSING_SOURCE_FILE_SHA")
            status = "PARTIALLY_TRACEABLE"
        elif not str(observation.get("source_row_index", "")).strip():
            notes.append("MISSING_SOURCE_ROW_INDEX")
            status = "PARTIALLY_TRACEABLE"
        else:
            status = "TRACEABLE"
        if temperature is None:
            notes.append("TEMPERATURE_NOT_NUMERIC")
            status = "UNTRACEABLE_NO_TEMPERATURE"
        if epsilon is None:
            notes.append("EPSILON_NOT_NUMERIC")
            status = "UNTRACEABLE_NO_EPSILON"
        if len(owners) > 1:
            notes.append("MULTIPLE_AGGREGATE_OWNERS")
        if not owners:
            notes.append("NOT_IN_ANY_AGGREGATE_WINDOW")

        rows.append({
            "measurement_id": measurement_id_for(observation),
            "molecule_key": molecule,
            "a_mol_id": owner["a_mol_id"] if owner else NOT_EVALUATED,
            "a_name": owner["a_name"] if owner else NOT_EVALUATED,
            "inchikey": molecule,
            "temperature_K": fmt_decimal(temperature),
            "dielectric": fmt_decimal(epsilon),
            "epsilon_unit": str(observation.get("epsilon_unit", "")).strip() or "not_evaluated",
            "phase": str(observation.get("phase", "")).strip(),
            "frequency_mhz": str(observation.get("frequency_mhz", "")).strip(),
            "frequency_hz": frequency_hz(observation),
            "pressure_kpa": str(observation.get("pressure_kpa", "")).strip() or NOT_EVALUATED,
            "source_document_id": document or NOT_EVALUATED,
            "source_file": str(observation.get("source_file", "")).strip() or NOT_EVALUATED,
            "source_file_sha256": str(observation.get("source_file_sha256", "")).strip() or NOT_EVALUATED,
            "source_row_index": str(observation.get("source_row_index", "")).strip() or NOT_EVALUATED,
            "evidence_group_id": f"EG-DOC-{document}" if document else NOT_EVALUATED,
            "experimental_independence_unit": "source_document",
            "property_name": str(observation.get("property_name", "")).strip() or NOT_EVALUATED,
            "property_family": str(observation.get("property_family", "")).strip() or NOT_EVALUATED,
            "method": str(observation.get("method", "")).strip() or NOT_EVALUATED,
            "temperature_band_v11": str(observation.get("temperature_band", "")).strip() or NOT_EVALUATED,
            "in_roster": str(observation.get("in_roster", "")).strip() or NOT_EVALUATED,
            "model_ready": str(observation.get("model_ready", "")).strip() or NOT_EVALUATED,
            "in_aggregate_window": bool_text(bool(owners)),
            "aggregate_id": ";".join(sorted(owners)) if owners else NOT_EVALUATED,
            "traceability_status": status,
            "traceability_note": joined(notes) or NOT_EVALUATED,
        })

    # 去重校验: 同一 measurement_id 不得出现两次
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["measurement_id"]] += 1
    duplicated = sorted(k for k, v in counts.items() if v > 1)

    summary = {
        "n_measurements": len(rows),
        "n_distinct_measurement_ids": len(counts),
        "duplicate_measurement_ids": duplicated,
        "n_traceable": sum(1 for r in rows if r["traceability_status"] == "TRACEABLE"),
        "n_partially_traceable": sum(1 for r in rows if r["traceability_status"] == "PARTIALLY_TRACEABLE"),
        "n_untraceable": sum(1 for r in rows if r["traceability_status"].startswith("UNTRACEABLE")),
        "n_in_aggregate_window": sum(1 for r in rows if r["in_aggregate_window"] == "true"),
        "n_static_zero_hz": sum(1 for r in rows if r["frequency_mhz"] == BAND_FREQUENCY_MHZ),
        "correction_of_j03": {
            "j03_labelled": "N_measurement = 460",
            "actual_definition_of_460": "v04 聚合窗口 (293.15-303.15 K, Liquid, 0 Hz) 内观测数",
            "full_measurement_count": len(rows),
            "note": "460 是派生计数, 不是全量测量数; 本账本以全量为基数",
        },
    }
    return rows, summary


def build_source_registry(
    ledger: Sequence[Mapping[str, str]]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """来源文档注册. 文档身份可验证; 实验独立性不可从此数据判定."""
    by_document: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in ledger:
        by_document[row["source_document_id"]].append(row)

    rows: list[dict[str, str]] = []
    for document in sorted(by_document):
        items = by_document[document]
        files = {r["source_file"] for r in items if r["source_file"] != NOT_EVALUATED}
        shas = {r["source_file_sha256"] for r in items if r["source_file_sha256"] != NOT_EVALUATED}
        identity_ok = (
            document != NOT_EVALUATED and len(files) == 1 and len(shas) == 1
        )
        if document == NOT_EVALUATED:
            identity_ok = False
        note_parts: list[str] = []
        if len(files) > 1:
            note_parts.append("MULTIPLE_FILES_FOR_ONE_DOI")
        if len(shas) > 1:
            note_parts.append("MULTIPLE_FILE_SHAS_FOR_ONE_DOI")
        rows.append({
            "source_document_id": document,
            "n_observations": str(len(items)),
            "n_molecules": str(len({r["molecule_key"] for r in items})),
            "n_static_zero_hz": str(sum(1 for r in items if r["frequency_mhz"] == BAND_FREQUENCY_MHZ)),
            "n_in_aggregate_window": str(sum(1 for r in items if r["in_aggregate_window"] == "true")),
            "source_file": next(iter(files)) if len(files) == 1 else NOT_EVALUATED,
            "source_file_sha256": next(iter(shas)) if len(shas) == 1 else NOT_EVALUATED,
            "document_identity_verified": bool_text(identity_ok),
            "experimental_independence_unit": "source_document",
            "experimental_independence_status": NOT_EVALUATED,
            "independence_note": (
                "文档身份可验证 (DOI + 文件 sha256); 但不同文献可能报告同一批实验或共享"
                "上游数据, 该风险无法仅凭本数据判定, 故独立实验数记为 not_evaluated"
                + ("; " + "; ".join(sorted(note_parts)) if note_parts else "")
            ),
        })

    by_document_sha: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_file_sha256"] != NOT_EVALUATED:
            by_document_sha[row["source_file_sha256"]].add(row["source_document_id"])
    shared = {s: sorted(d) for s, d in by_document_sha.items() if len(d) > 1}

    summary = {
        "n_documents": len(rows),
        "n_document_identity_verified": sum(
            1 for r in rows if r["document_identity_verified"] == "true"
        ),
        "n_documents_with_observations_in_aggregate_window": sum(
            1 for r in rows if int(r["n_in_aggregate_window"]) > 0
        ),
        "n_shared_source_files": len(shared),
        "shared_source_files": shared,
        "independence_statement": (
            "DOI 数不等于独立实验数. 本注册表报告的是**可验证的文档身份**; "
            "独立实验数需要外部证据 (同一作者组/同一批次/共享上游) 才能判定, "
            "因此记为 not_evaluated 而不是用文档数替代."
        ),
    }
    return rows, summary


INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 中性母体",
    "dielectric_v04": "v04 聚合主表 (被还原对象)",
    "observations_v11plus": "v11plus 原始观测层 (测量证据来源)",
    "admission_gap": "248 行 admission 缺口表",
    "candidate_master": "聚合口径记录",
    "target_protocol": "冻结协议温窗",
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
        "aggregate_window": {
            "low_K": fmt_decimal(BAND_LOW), "high_K": fmt_decimal(BAND_HIGH),
            "phase": BAND_PHASE, "frequency_mhz": BAND_FREQUENCY_MHZ,
        },
        "inputs": inputs,
        "environment": dict(sorted(environment.items())),
    }


def collect_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(terse=True)}


def load_device(paths: Mapping[str, Path]) -> dict[str, Any]:
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
        ("inchikey", "T_K", "dielectric", "source_doi", "n_observations"),
    )
    observations = read_csv_strict(
        paths["observations_v11plus"],
        ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz", "pressure_kpa",
         "source_doi", "source_file", "source_file_sha256", "source_row_index",
         "epsilon_unit", "property_name", "property_family", "method",
         "temperature_band", "in_roster", "model_ready"),
    )
    gap = read_csv_strict(
        paths["admission_gap"],
        ("molecule_id", "measurement_id", "source_group", "T_K", "epsilon",
         "measurement_decision"),
    )
    master = read_csv_strict(
        paths["candidate_master"],
        ("measurement_id", "molecule_id", "aggregation_path"),
    )
    # v04 行主键 = EPSV04-R{NNN} -> 第 NNN-1 行 (与 formal_decision_adapter 同一约定)
    v04_by_index: dict[str, dict[str, str]] = {}
    for index, row in enumerate(v04, start=1):
        v04_by_index[f"v04row-{index:03d}"] = row
    return {
        "core": core,
        "a18_by_skeleton": a18_by_skeleton,
        "v04": v04,
        "v04_by_index": v04_by_index,
        "observations": observations,
        "gap": gap,
        "master_by_id": {str(r["measurement_id"]).strip(): r for r in master},
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


OUTPUT_DIR_NAME = "provenance_repair"


def build_stage_outputs(device: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    """J04-A + J04-B 的产物."""
    ledger, ledger_summary = build_measurement_ledger(device)
    sources, source_summary = build_source_registry(ledger)
    payload = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "stage": "J04-A/B",
        "measurement_ledger": ledger_summary,
        "source_document_registry": source_summary,
        "inputs": dict(sorted({e["id"]: e["sha256"] for e in manifest["inputs"]}.items())),
    }
    files: dict[str, bytes] = {
        "measurement_ledger_v1.csv": render_csv(LEDGER_COLUMNS, ledger),
        "source_document_registry_v1.csv": render_csv(SOURCE_COLUMNS, sources),
        "j04ab_ledger_summary.json": render_json(payload),
    }
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
            print(f"  {item['input']}: expected {item['expected'][:16]} "
                  f"actual {item['actual'][:16]}", file=sys.stderr)
        return 3
    missing = [n for n, p in paths.items() if not Path(p).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2
    device = load_device(paths)
    manifest = build_inputs_manifest(paths, collect_environment())
    files = build_stage_outputs(device, manifest=manifest)
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
    summary = json.loads(files["j04ab_ledger_summary.json"].decode("utf-8"))
    ledger = summary["measurement_ledger"]
    print(f"{ANALYSIS_ID} J04-A/B 完成 -> {target_dir}")
    print(f"  测量账本: {ledger['n_measurements']} 条 (唯一 id {ledger['n_distinct_measurement_ids']})")
    print(f"  可追溯: {ledger['n_traceable']}  部分: {ledger['n_partially_traceable']}  "
          f"不可追溯: {ledger['n_untraceable']}")
    print(f"  聚合窗口内: {ledger['n_in_aggregate_window']} (J03 曾称 460)")
    print(f"  来源文档: {summary['source_document_registry']['n_documents']} "
          f"(身份已验证 {summary['source_document_registry']['n_document_identity_verified']})")
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
