#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J01 | A18 x B 共同候选资格审计与证据缺口登记.

结论性目的（本模块唯一要回答的问题）
------------------------------------
在 A 的 18 个中性母体与 B 当前可准入的介电证据之间, **是否存在足以支撑确认性联合
Top-k / regret 的合格样本**? 本模块只负责把这个问题变成可复核的分母与逐条证据,
不产出任何联合性能指标.

为什么要有这个模块
------------------
A/B 两仓库各有冻结产物, 但词汇不同: A 用 mol_id (C01..C18) + 电子态机器, B 用
EPSV04-R{NNN} measurement + v11 观测层 + admission 门 A1..A12. 直接"按名字对上"
会犯三类错:
  1. 把 A 的 Li 配合物 (LiM_plus / LiM_2plus) 当成纯液体实验分子——物理上不成立;
  2. 把"同一母体出现过"当成"资格匹配"——一个 matched=true 会吞掉身份/来源/温度/
     相态/频率/人工签批/独立来源数七类不同原因;
  3. 另起第三套并列记分牌——与本项目"不新增第二套 parser/aggregator"的纪律冲突.
因此本模块只做**连接与裁决**: 身份用 A 的中性母体 InChIKey 骨架, 资格读 B 已冻结的
协议 (target_protocol.yaml) 与既有 admission 产物, 逐层报告, 最后给 GO/NO-GO.

复用的既有机制（不重造）
------------------------
* 身份规范化: InChIKey 骨架(首段) —— 与 B 的 molecule_id / v04 inchikey 同一约定;
  完整键与骨架分别报告: 骨架命中不等于立体/质子化态相同.
* 观测来源: data/processed/dielectric_observations_v11plus.csv 的逐行 T/phase/
  frequency/pressure/source_doi/source_file, 不从 v04 反推.
* admission: experimental_epsilon_admission_gap.csv (measurement_decision) +
  admission_v3_formal_decision_DRAFT.csv (A1..A12 逐门) +
  human_audit_worksheet_R007.csv (人类审计状态). 本模块**不重算** A1..A12, 只读结论.
* 数据版本: 冻结约定 EPSV04-R{NNN} -> v04 第 NNN-1 行 (formal_decision_adapter.py 同
  一约定); 本模块全量 248 行校验该映射.
* 门定义与温窗: drafts/configs/frozen/target_protocol.yaml.
  注意: 该协议自身 status=DRAFT_PENDING_HUMAN_APPROVAL, frozen=false, 本模块如实记录,
  不谎称已冻结.
* k 规则: primary_k_adoption.FROZEN.yaml -> primary_k = max(1, ceil(n_eligible/10)).

绝不做的事
----------
* 不修改任何输入; 不写 v1.3 冻结产物; 不执行人类 admission 签批; 不发算; 不联网.
* 不产出联合性能指标 (Top-k / regret / 联合模型对比), 因为当前分母不成立.
* 不把"没尝试"写成 0: 未评估处一律 not_evaluated.

确定性与重建
------------
所有输出不含墙钟时间; 行序、列序、数值表示固定. 相同输入 => 逐字节相同输出.
`--check` 在临时目录重建并与现有产物逐字节比较, 不一致退出码 1.

退出码
------
0 正常; 1 输出不一致 (--check); 2 输入缺失/结构不合法; 3 输入 SHA256 漂移;
4 快照与固化值不一致 (数据被换但契约版本未升).

用法
----
    python scripts/confirm_2027/build_joint_eligibility.py
    python scripts/confirm_2027/build_joint_eligibility.py --check
    python scripts/confirm_2027/build_joint_eligibility.py --a-repo <path> --out <dir>
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
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 契约与常量
# ---------------------------------------------------------------------------

ANALYSIS_ID = "B-G0-J01"
ANALYSIS_TITLE = "A18 x B 共同候选资格审计与证据缺口登记"
#: 语义契约版本: 改动"什么算合格"必须升版本, 不能静默放宽.
CONTRACT_VERSION = "confirm_2027.joint_eligibility/v1"
#: 输入契约版本: 改动下面任何一处 SHA256 必须同时升版本.
INPUT_CONTRACT_VERSION = "confirm_2027.joint_inputs/v1"
GENERATOR_VERSION = "build_joint_eligibility/1.0.0"

#: 本次固化的快照 (授权范围 B-G0-J01 第 5 条). 输入未变却算出别的数 => 退出码 4.
EXPECTED_SNAPSHOT: dict[str, Any] = {
    "n_a_core_neutral_parents": 18,
    "n_identity_common_in_candidate_master": 18,
    "n_condition_resolvable": 4,
    "n_room_band_qualified": 3,
    "n_admitted": 0,
    "off_room_band_condition_resolvable": ["C18"],
}

#: 冻结输入的 SHA256 (确定性重建的唯一依据).
PINNED_INPUT_SHA256: dict[str, str] = {
    # A 仓 (只读; 18 个中性母体)
    "a_core_set": "630b0ee8c09dc4141124e335181572bf27a63f297a8df95f9c774683a10cf91b",
    # B 仓
    "b_dielectric_v04": "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c",
    "b_observations_v11plus": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    # v56_standalone 权威产物
    "v56_candidate_master": "63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d",
    "v56_candidate_pool_c": "c50f9349ec6de434f2b81d7a138292581fb661f4b1b9b1d54fdd3f7dc9055ba8",
    "v56_candidate_pool_b": "e2f18d4fd09b2ba9a9c5680c55c943d93a7381bef0c3d78a87676dc00540c176",
    "v56_human_audit_worksheet": "2346b707c46e8204d01bc516556288f73a194b170887bf4324b9fcc160a0f1ab",
    # 与 admission_v2_draft.PINNED_GAP_SHA256 同一把锁, 复用而非另立
    "v56_admission_gap": "597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1",
    "v56_formal_decision_draft": "d2bfea53546f6197237f5b51d5fad9143eab4e3c842e1019ea6afe2e528d132a",
    "v56_target_protocol": "0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4",
    "v56_primary_k_adoption": "c44d83583f38ba02bb83efc562876c4e75025fa5ef4abc85e0b4f7455e143052",
    "v56_manifest": "ec289e3dcd39b8afa35e397e846ad956a589fdea466b7f63d1bad7b008bd9703",
    "v56_round_r007": "3a223479ab4d66876bf6d129d8eba2e85c0e95acb662d45f7694a6c5c8c14ce3",
    "v56_three_questions_r001": "95bd6ed86668821c40520df43de372c2e66aac65f00270d190b02b246989e236",
}

#: A 的连接对象: 只有中性母体. 电子态/加 Li 物种一律不进本表 (授权范围第 2 条).
A_JOIN_UNIT = "neutral_parent_inchikey_skeleton"

#: 候选层定义: (层名, 内存数据集键, 身份列)
CANDIDATE_LAYERS: tuple[tuple[str, str, str], ...] = (
    ("candidate_master", "master", "molecule_id"),
    ("pool_c", "pool_c", "molecule_id"),
    ("pool_b", "pool_b", "molecule_id"),
    ("worksheet_40", "worksheet", "molecule_id"),
    ("formal_draft_20", "formal", "inchikey"),
)

#: 但 "出现在 248 行主表里" 不等于 "证据可解析": 主表是全集, 不是资格.
#: 条件可解析只认这四层 —— 它们各自带逐行证据裁决 (evidence_group/decision).
QUALIFYING_LAYERS: frozenset[str] = frozenset(
    {"pool_c", "pool_b", "worksheet_40", "formal_draft_20"}
)

#: B 的 admission 门代号 (来自 target_protocol.yaml 的 accept_prerequisites, 本模块只读不重定义)
ADMISSION_GATES: tuple[str, ...] = (
    "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12",
)

NBS514_DOI = "10.6028/nbs.circ.514"

OUTPUT_FILES: tuple[str, ...] = (
    "joint_inputs_manifest.json",
    "joint_pool_layer_summary.json",
    "joint_eligibility.csv",
    "joint_v11_observation_rows.csv",
    "joint_candidate_measurement_rows.csv",
    "a18_source_backfill_priority.csv",
    "joint_eligibility_criteria.json",
    "joint_go_nogo.json",
    "joint_eligibility_report.md",
    "joint_rebuild_receipt.json",
)

VERDICT_ADMITTED = "ELIGIBLE_ADMITTED"
VERDICT_QUALIFIED = "CONDITION_QUALIFIED_ADMISSION_PENDING"
VERDICT_OFF_BAND = "CONDITION_QUALIFIED_OFF_ROOM_BAND"
VERDICT_OBS_ONLY = "OBSERVATION_READY_NOT_IN_CANDIDATE_POOL"
VERDICT_IDENTITY_ONLY = "IDENTITY_ONLY_NO_CONDITION_OBSERVATION"
VERDICT_NO_IDENTITY = "IDENTITY_ABSENT"


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

class JointEligibilityError(RuntimeError):
    """输入结构不合法/缺失时抛出 (退出码 2)."""


class SnapshotMismatch(RuntimeError):
    """输入被换但契约版本未升 (退出码 4)."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def read_csv_strict(path: Path, required: Sequence[str]) -> list[dict[str, str]]:
    """读 CSV 并强制列存在; 任何缺失都 fail-closed (不静默补列)."""
    path = Path(path)
    if not path.is_file():
        raise JointEligibilityError(f"输入缺失: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [c for c in required if c not in header]
        if missing:
            raise JointEligibilityError(f"{path.name} 缺少必需列: {missing}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise JointEligibilityError(f"{path.name} 为空表")
    return rows


def skeleton(inchikey: str) -> str:
    """InChIKey 首段 (14 字符骨架). 空值返回空串, 绝不伪造."""
    text = (inchikey or "").strip()
    return text.split("-")[0] if text else ""


def inchikey_from_smiles(smiles: str) -> str:
    """从 SMILES 求标准 InChIKey; 失败即抛, 不回落."""
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        raise JointEligibilityError(f"SMILES 无法解析: {smiles!r}")
    key = Chem.MolToInchiKey(mol)
    if not re.fullmatch(r"[A-Z]{14}-[A-Z]{10}-[A-Z]", key or ""):
        raise JointEligibilityError(f"InChIKey 形状不合法: {key!r} (from {smiles!r})")
    return key


def to_float(text: Any) -> float | None:
    """宽松数值解析: 空/不可解析返回 None (绝不补 0, 见协议 N6)."""
    raw = str(text).strip() if text is not None else ""
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def band_of(temperature: float | None, windows: Sequence[Mapping[str, Any]]) -> str:
    """按冻结协议温窗分带; 缺失/超界都返回显式状态, 不猜."""
    if temperature is None:
        return "temperature_missing"
    for window in windows:
        if float(window["low"]) <= temperature <= float(window["high"]):
            return str(window["name"])
    return "outside_declared_window"


def fmt_number(value: float | None) -> str:
    """固定小数表示, 让重建逐字节可比."""
    if value is None:
        return ""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


#: 未评估的统一写法 (授权范围要求 "未评估不准写成 0")
NOT_EVALUATED = "not_evaluated"


def _prefer(current: str, candidate: str) -> str:
    """合并多层同名字段时的取舍: 真实值优先, not_evaluated 只在实在没有值时保留."""
    candidate = (candidate or "").strip()
    if not current or current == NOT_EVALUATED:
        return candidate or current
    return current


def joined(values: Iterable[str], sep: str = ";") -> str:
    return sep.join(sorted({v for v in values if v and str(v).strip()}))


def bool_text(flag: bool) -> str:
    return "true" if flag else "false"


# ---------------------------------------------------------------------------
# 路径、协议、k 规则
# ---------------------------------------------------------------------------

def default_workspace() -> Path:
    """B 仓工作区 (本文件位于 <workspace>/电解质ML/scripts/confirm_2027/)."""
    return Path(__file__).resolve().parents[3]


def locate_inputs(workspace: Path, a_repo: Path | None) -> dict[str, Path]:
    """把 14 个冻结输入映射到实际路径; 路径只由参数决定, 不猜."""
    workspace = Path(workspace)
    v56 = workspace / "v56_standalone"
    repo_b = workspace / "电解质ML"
    repo_a = Path(a_repo) if a_repo else Path(
        os.environ.get("J01_REPO_A", str(workspace.parent / "电解液溶剂-HB" / "电解液溶剂HB-Code"))
    )
    drafts = v56 / "app" / "电解质ML" / "v56_round1"
    return {
        "a_core_set": repo_a / "data" / "metadata" / "core_set.csv",
        "b_dielectric_v04": repo_b / "data" / "dielectric_v04.csv",
        "b_observations_v11plus": repo_b / "data" / "processed" / "dielectric_observations_v11plus.csv",
        "v56_candidate_master": v56 / "reports" / "candidate_master_R001.csv",
        "v56_candidate_pool_c": v56 / "reports" / "candidate_pool_C_R001.csv",
        "v56_candidate_pool_b": v56 / "reports" / "candidate_pool_B_R001.csv",
        "v56_human_audit_worksheet": v56 / "reports" / "human_audit_worksheet_R007.csv",
        "v56_admission_gap": drafts / "deliverables" / "experimental_epsilon_admission_gap.csv",
        "v56_formal_decision_draft": drafts / "deliverables" / "admission_v3_formal_decision_DRAFT.csv",
        "v56_target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
        "v56_primary_k_adoption": drafts / "drafts" / "configs" / "frozen" / "primary_k_adoption.FROZEN.yaml",
        "v56_manifest": v56 / "MANIFEST.json",
        "v56_round_r007": v56 / "reports" / "ROUND_R007.md",
        "v56_three_questions_r001": v56 / "reports" / "THREE_QUESTIONS_R001.md",
    }


def verify_pinned_inputs(paths: Mapping[str, Path], pins: Mapping[str, str] = PINNED_INPUT_SHA256) -> list[dict[str, str]]:
    """返回漂移记录 (空列表 = 全部匹配). 缺文件也算漂移并带原因."""
    drift: list[dict[str, str]] = []
    for name in sorted(pins):
        path = paths.get(name)
        if path is None:
            drift.append({"input": name, "expected": pins[name], "actual": "PATH_UNMAPPED"})
            continue
        if not Path(path).is_file():
            drift.append({"input": name, "expected": pins[name], "actual": "FILE_MISSING", "path": str(path)})
            continue
        actual = sha256_file(Path(path))
        if actual != pins[name]:
            drift.append({"input": name, "expected": pins[name], "actual": actual, "path": str(path)})
    return drift


def load_protocol(path: Path) -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise JointEligibilityError("target_protocol.yaml 顶层不是映射")
    windows = document.get("allowed_temperature_windows_K")
    if not isinstance(windows, list) or not windows:
        raise JointEligibilityError("target_protocol.yaml 缺 allowed_temperature_windows_K")
    for window in windows:
        if not {"name", "low", "high"} <= set(window):
            raise JointEligibilityError(f"温窗条目缺字段: {window!r}")
    return document


def load_primary_k_rule(path: Path) -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "rule" not in document:
        raise JointEligibilityError("primary_k_adoption.FROZEN.yaml 缺 rule")
    return document


def primary_k(n_eligible: int, rule_text: str) -> int:
    """按冻结规则 primary_k = max(1, ceil(n_eligible/10)); 规则文本不含该式则拒绝."""
    if "n_eligible" not in rule_text or "10" not in rule_text:
        raise JointEligibilityError(f"无法从冻结文本推导 k 规则: {rule_text!r}")
    return max(1, math.ceil(max(0, int(n_eligible)) / 10))


def min_n_for_primary_k(target_k: int, rule_text: str) -> int:
    for n in range(0, 10001):
        if primary_k(n, rule_text) >= target_k:
            return n
    raise JointEligibilityError("无法求解 primary_k 的最小 n")


# ---------------------------------------------------------------------------
# 数据集装载
# ---------------------------------------------------------------------------

def load_dataset(paths: Mapping[str, Path]) -> dict[str, Any]:
    """装载全部输入到内存, 并做结构性强校验."""
    core = read_csv_strict(paths["a_core_set"], ("mol_id", "name", "smiles"))
    v04 = read_csv_strict(
        paths["b_dielectric_v04"],
        ("inchikey", "smiles", "name", "T_K", "dielectric", "source_doi",
         "temperature_band", "gate_flags"),
    )
    observations = read_csv_strict(
        paths["b_observations_v11plus"],
        ("inchikey", "T_K", "epsilon", "phase", "frequency_mhz", "pressure_kpa",
         "source_doi", "source_file", "temperature_band", "model_ready", "property_name"),
    )
    gap = read_csv_strict(
        paths["v56_admission_gap"],
        ("molecule_id", "measurement_id", "source_group", "phase", "T_K", "P",
         "frequency", "epsilon", "license", "measurement_decision", "qc_reason"),
    )
    master = read_csv_strict(
        paths["v56_candidate_master"],
        ("measurement_id", "molecule_id", "source_primary", "in_49_preview",
         "evidence_status", "admission_status"),
    )
    pool_c = read_csv_strict(
        paths["v56_candidate_pool_c"],
        ("measurement_id", "molecule_id", "source_group", "epsilon_recorded", "T_K",
         "evidence_group_id", "decision_v2"),
    )
    pool_b = read_csv_strict(
        paths["v56_candidate_pool_b"],
        ("measurement_id", "molecule_id", "source_group", "epsilon_recorded", "T_K",
         "evidence_group_id", "decision_v2"),
    )
    worksheet = read_csv_strict(
        paths["v56_human_audit_worksheet"],
        ("measurement_id", "molecule_id", "source_group", "epsilon", "T_K",
         "machine_audit_status", "human_audit_status", "a9_group_level"),
    )
    formal = read_csv_strict(
        paths["v56_formal_decision_draft"],
        ("measurement_id", "inchikey", "epsilon", "T_K", "failed_gates", "formal_verdict_draft"),
    )
    protocol = load_protocol(paths["v56_target_protocol"])
    k_rule = load_primary_k_rule(paths["v56_primary_k_adoption"])
    v56_manifest = json.loads(Path(paths["v56_manifest"]).read_text(encoding="utf-8"))
    return {
        "core": core,
        "v04": v04,
        "observations": observations,
        "gap": gap,
        "master": master,
        "pool_c": pool_c,
        "pool_b": pool_b,
        "worksheet": worksheet,
        "formal": formal,
        "protocol": protocol,
        "k_rule": k_rule,
        "v56_manifest": v56_manifest,
    }


# ---------------------------------------------------------------------------
# 完整性校验 (只记录, 不修复)
# ---------------------------------------------------------------------------

def check_gap_v04_mapping(
    gap: Sequence[Mapping[str, str]], v04: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    """EPSV04-R{NNN} <-> v04 第 NNN-1 行 (formal_decision_adapter 的冻结约定)."""
    ok = 0
    problems: list[str] = []
    for row in gap:
        match = re.fullmatch(r"EPSV04-R(\d{3})", str(row.get("measurement_id", "")).strip())
        if not match:
            problems.append(f"非法 measurement_id: {row.get('measurement_id')!r}")
            continue
        index = int(match.group(1)) - 1
        if index < 0 or index >= len(v04):
            problems.append(f"{row['measurement_id']}: 越界 (v04 共 {len(v04)} 行)")
            continue
        if v04[index].get("inchikey") != row.get("molecule_id"):
            problems.append(f"{row['measurement_id']}: v04 第 {index + 1} 行身份不一致")
            continue
        left = to_float(v04[index].get("dielectric"))
        right = to_float(row.get("epsilon"))
        if left is None or right is None or abs(left - right) > 1e-9:
            problems.append(f"{row['measurement_id']}: epsilon 与 v04 不一致")
            continue
        ok += 1
    return {
        "name": "gap_to_v04_row_mapping",
        "status": "PASS" if not problems else "FAIL",
        "checked": len(gap),
        "passed": ok,
        "problems": problems[:20],
    }


def check_mirror_equality(paths: Mapping[str, Path], workspace: Path) -> list[dict[str, Any]]:
    """v56 镜像里的 v04 / v11 是否与主仓逐字节一致 (单向复制的静默漂移检测)."""
    del paths
    workspace = Path(workspace)
    repo_b = workspace / "电解质ML"
    mirror_b = workspace / "v56_standalone" / "app" / "电解质ML" / "电解质ML"
    checks: list[dict[str, Any]] = []
    for name, rel in (
        ("dielectric_v04_mirror", "data/dielectric_v04.csv"),
        ("observations_v11plus_mirror", "data/processed/dielectric_observations_v11plus.csv"),
    ):
        left = repo_b / rel
        right = mirror_b / rel
        if not left.is_file() or not right.is_file():
            checks.append({"name": name, "status": "NOT_EVALUATED", "detail": "镜像或主仓文件缺失"})
            continue
        left_sha = sha256_file(left)
        right_sha = sha256_file(right)
        checks.append({
            "name": name,
            "status": "PASS" if left_sha == right_sha else "DRIFT_RECORDED",
            "detail": f"main={left_sha[:16]} mirror={right_sha[:16]}",
        })
    return checks


def check_pool_layer_disagreement(dataset: Mapping[str, Any]) -> list[dict[str, Any]]:
    """登记候选层之间的既知不一致: 只报告, 不择优覆盖."""
    master = dataset["master"]
    preview = {
        skeleton(r["molecule_id"]) for r in master
        if str(r.get("in_49_preview", "")).strip().lower() == "yes"
    }
    pool_c_keys = {skeleton(r["molecule_id"]) for r in dataset["pool_c"]}
    worksheet_keys = {skeleton(r["molecule_id"]) for r in dataset["worksheet"]}
    return [
        {
            "name": "master_in_49_preview_vs_candidate_pool_c",
            "status": "DISAGREEMENT_RECORDED",
            "detail": (
                f"master.in_49_preview=yes 有 {len(preview)} 个骨架, candidate_pool_C 有 "
                f"{len(pool_c_keys)} 个骨架; {len(preview - pool_c_keys)} 个只在 preview, "
                f"{len(pool_c_keys - preview)} 个只在 pool_C — 两者不是同一套 49 池"
            ),
            "authority_used": "candidate_pool_C (逐行 epsilon / evidence_group_id / decision_v2)",
            "not_authoritative": "master.in_49_preview (preview 标记, 与最终池不同)",
        },
        {
            "name": "worksheet_40_not_subset_of_pool_c",
            "status": "DISAGREEMENT_RECORDED",
            "detail": (
                f"human_audit_worksheet_R007 (40 行) 有 {len(worksheet_keys - pool_c_keys)} 个骨架"
                " 不在 pool_C — 候选层是相互重叠的子集, 不是嵌套结构"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# 分层索引
# ---------------------------------------------------------------------------

_LAYER_TABLES: dict[str, str] = {
    "candidate_master": "master",
    "pool_c": "pool_c",
    "pool_b": "pool_b",
    "worksheet_40": "worksheet",
    "formal_draft_20": "formal",
}


def build_layer_records(dataset: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    """每层 -> [(skeleton, measurement_id)]; 层内按 (骨架, measurement_id) 排序."""
    layers: dict[str, list[dict[str, str]]] = {}
    for layer_name, _input_key, id_column in CANDIDATE_LAYERS:
        rows = dataset[_LAYER_TABLES[layer_name]]
        records = [{
            "skeleton": skeleton(str(row.get(id_column, ""))),
            "measurement_id": str(row.get("measurement_id", "")).strip(),
        } for row in rows]
        records = [r for r in records if r["skeleton"] and r["measurement_id"]]
        records.sort(key=lambda r: (r["skeleton"], r["measurement_id"]))
        layers[layer_name] = records
    return layers


def build_candidate_index(
    dataset: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> dict[str, list[dict[str, str]]]:
    """骨架 -> 该骨架在各候选层里的真实行 (含 T/band/裁决), 供逐条证据表使用."""
    index: dict[str, list[dict[str, str]]] = {}
    for layer_name, _input_key, id_column in CANDIDATE_LAYERS:
        for row in dataset[_LAYER_TABLES[layer_name]]:
            key = skeleton(str(row.get(id_column, "")))
            if not key:
                continue
            temperature = to_float(row.get("T_K"))
            # 这一层没有的字段写 not_evaluated, 不写空串也绝不写 0 (协议 N6)
            epsilon = (
                str(row.get("epsilon_recorded", "")).strip()
                or str(row.get("epsilon", "")).strip()
                or "not_evaluated"
            )
            source_group = (
                str(row.get("source_group", "")).strip()
                or str(row.get("source_primary", "")).strip()
                or "not_evaluated"
            )
            decision = (
                str(row.get("decision_v2", "")).strip()
                or str(row.get("measurement_decision", "")).strip()
                or str(row.get("formal_verdict_draft", "")).strip()
                or "not_evaluated"
            )
            index.setdefault(key, []).append({
                "layer": layer_name,
                "measurement_id": str(row.get("measurement_id", "")).strip(),
                "epsilon": epsilon,
                "T_K": fmt_number(temperature),
                "band": band_of(temperature, windows),
                "source_group": source_group,
                "decision": decision,
                "evidence_group_id": str(row.get("evidence_group_id", "")).strip() or "not_evaluated",
                "failed_gates": str(row.get("failed_gates", "")).strip(),
                "human_audit_status": str(row.get("human_audit_status", "")).strip(),
                "machine_audit_status": str(row.get("machine_audit_status", "")).strip(),
            })
    for key in index:
        index[key].sort(key=lambda r: (r["measurement_id"], r["layer"]))
    return index


def index_by_skeleton(rows: Sequence[Mapping[str, str]], column: str) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = skeleton(str(row.get(column, "")))
        if not key:
            continue
        index.setdefault(key, []).append(dict(row))
    return index


# ---------------------------------------------------------------------------
# 七维裁决
# ---------------------------------------------------------------------------

def describe_sources(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """独立来源统计: DOI 优先, 文件名为回退; 两者皆空只计 MISSING_DOI, 不计来源数.

    同一 DOI 的多行只算一个来源 (重复转录不得冒充独立证据).
    """
    groups: set[str] = set()
    missing_doi_rows = 0
    for row in rows:
        doi = str(row.get("source_doi", "")).strip()
        file_name = str(row.get("source_file", "")).strip()
        if doi:
            groups.add(f"doi:{doi}")
        elif file_name:
            groups.add(f"file:{file_name}")
        else:
            missing_doi_rows += 1
    n_groups = len(groups)
    if n_groups == 0:
        status = "NO_SOURCE"
    elif n_groups == 1:
        status = "SINGLE_SOURCE"
    elif n_groups == 2:
        status = "DUAL_SOURCE"
    else:
        status = "CLUSTER_GE3"
    return {
        "n_source_doi": len({str(r.get("source_doi", "")).strip() for r in rows} - {""}),
        "n_source_file": len({str(r.get("source_file", "")).strip() for r in rows} - {""}),
        "n_source_groups": n_groups,
        "n_missing_doi_rows": missing_doi_rows,
        "independent_source_status": status,
        "source_groups": sorted(groups),
    }


def source_alignment(v04_dois: set[str], observation: Mapping[str, Any]) -> str:
    """v04 记录来源 vs v11 观测来源 的对齐状态; 空交集即冲突, 不静默取并集."""
    obs_dois = {g.split("doi:", 1)[1] for g in observation["source_groups"] if g.startswith("doi:")}
    if not v04_dois or not obs_dois:
        return "NOT_EVALUATED"
    if obs_dois <= v04_dois:
        return "ALIGNED"
    if obs_dois & v04_dois:
        return "PARTIAL_ALIGNMENT"
    return "SOURCE_CONFLICT"


def phase_status_of(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "NOT_EVALUATED"
    phases = {str(r.get("phase", "")).strip().lower() for r in rows}
    phases.discard("")
    if not phases:
        return "PHASE_UNKNOWN"
    if phases == {"liquid"}:
        return "LIQUID_EVIDENCED_IN_V11"
    return "MIXED_PHASE_EVIDENCE"


def frequency_status_of(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    static = rf = unknown = 0
    for row in rows:
        value = to_float(row.get("frequency_mhz"))
        if value is None:
            unknown += 1
        elif value == 0.0:
            static += 1
        else:
            rf += 1
    if not rows:
        status = "NOT_EVALUATED"
    elif static > 0:
        status = "STATIC_ZERO_HZ_EVIDENCED"
    elif rf > 0:
        status = "RF_ONLY"
    else:
        status = "FREQUENCY_UNKNOWN"
    return {"n_static": static, "n_rf": rf, "n_unknown": unknown, "frequency_status": status}


def pressure_status_of(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "NOT_EVALUATED"
    present = sum(1 for r in rows if (to_float(r.get("pressure_kpa")) or 0.0) > 0.0)
    if present == len(rows):
        return "PRESSURE_EVIDENCED"
    if present == 0:
        return "PRESSURE_UNKNOWN"
    return "PRESSURE_PARTIAL"


def human_admission_of(
    measurement_ids: Sequence[str],
    worksheet_by_id: Mapping[str, Mapping[str, str]],
    gap_by_id: Mapping[str, Mapping[str, str]],
    formal_by_id: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    """人类准入状态: 只有显式 ACCEPT/签批才算签批; 其余一律 NOT_SIGNED, 不升级."""
    if not measurement_ids:
        return {"human_audit_status": "NO_ADMISSION_ROW", "human_admission_status": "NO_ADMISSION_ROW"}
    signed = False
    tokens: set[str] = set()
    for measurement_id in measurement_ids:
        formal = formal_by_id.get(measurement_id)
        if formal and str(formal.get("formal_verdict_draft", "")).strip().upper().startswith("ACCEPT"):
            signed = True
        sheet = worksheet_by_id.get(measurement_id)
        if sheet:
            tokens.add(f"worksheet:{str(sheet.get('human_audit_status', '')).strip() or 'UNKNOWN'}")
        gap = gap_by_id.get(measurement_id)
        if gap:
            tokens.add(f"gap:{str(gap.get('measurement_decision', '')).strip() or 'UNKNOWN'}")
    return {
        "human_audit_status": joined(tokens) if tokens else "NO_WORKSHEET_ROW",
        "human_admission_status": "SIGNED_ACCEPT" if signed else "NOT_SIGNED",
    }


def adjudicate_molecule(
    core_row: Mapping[str, str],
    *,
    v04_by_skeleton: Mapping[str, Mapping[str, str]],
    observations_by_skeleton: Mapping[str, Sequence[Mapping[str, str]]],
    gap_by_skeleton: Mapping[str, Mapping[str, str]],
    candidate_index: Mapping[str, Sequence[Mapping[str, str]]],
    layers: Mapping[str, Sequence[Mapping[str, str]]],
    worksheet_by_id: Mapping[str, Mapping[str, str]],
    gap_by_id: Mapping[str, Mapping[str, str]],
    formal_by_id: Mapping[str, Mapping[str, str]],
    windows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """对单个 A 母体做**分层**裁决; 每一维独立可判, 没有 matched 位."""
    inchikey = inchikey_from_smiles(str(core_row.get("smiles", "")))
    key = skeleton(inchikey)
    mol_id = str(core_row.get("mol_id", "")).strip()

    v04_row = v04_by_skeleton.get(key)
    if v04_row is None:
        identity_status = VERDICT_NO_IDENTITY
    elif str(v04_row.get("inchikey", "")).strip() == inchikey:
        identity_status = "IDENTITY_FULL_KEY"
    else:
        identity_status = "IDENTITY_SKELETON_ONLY"

    observations = list(observations_by_skeleton.get(key, []))
    candidates = list(candidate_index.get(key, []))
    qualifying_candidates = [c for c in candidates if c["layer"] in QUALIFYING_LAYERS]
    candidate_ids = sorted({c["measurement_id"] for c in candidates})
    layer_hits = sorted({c["layer"] for c in candidates})
    qualifying_layers = sorted({c["layer"] for c in qualifying_candidates})

    v04_dois = {d.strip() for d in str(v04_row.get("source_doi", "")).split(";") if d.strip()} if v04_row else set()
    observation_source = describe_sources(observations)
    frequency = frequency_status_of(observations)
    rooms = sum(1 for r in observations if band_of(to_float(r.get("T_K")), windows) == "room_temperature")
    admission = human_admission_of(candidate_ids, worksheet_by_id, gap_by_id, formal_by_id)

    candidate_temperatures = [c["T_K"] for c in qualifying_candidates]
    candidate_bands = [c["band"] for c in qualifying_candidates]
    candidate_rooms = sum(1 for c in qualifying_candidates if c["band"] == "room_temperature")
    failed = sorted({
        g.strip() for c in qualifying_candidates for g in c["failed_gates"].split(",") if g.strip()
    })

    gap_row = gap_by_skeleton.get(key, {})
    gap_decision = str(gap_row.get("measurement_decision", "")).strip()

    condition_resolvable = bool(qualifying_layers)
    signed_accept = admission["human_admission_status"] == "SIGNED_ACCEPT"
    admitted = signed_accept and gap_decision.upper() == "ACCEPT"
    room_band_qualified = condition_resolvable and candidate_rooms > 0

    if identity_status == VERDICT_NO_IDENTITY:
        verdict = VERDICT_NO_IDENTITY
    elif admitted:
        verdict = VERDICT_ADMITTED
    elif condition_resolvable and room_band_qualified:
        verdict = VERDICT_QUALIFIED
    elif condition_resolvable:
        verdict = VERDICT_OFF_BAND
    elif observations:
        verdict = VERDICT_OBS_ONLY
    else:
        verdict = VERDICT_IDENTITY_ONLY

    reasons: list[str] = []
    reasons.append({
        "IDENTITY_FULL_KEY": "IDENTITY_FULL_KEY_MATCH",
        "IDENTITY_SKELETON_ONLY": "IDENTITY_SKELETON_ONLY_MATCH",
        VERDICT_NO_IDENTITY: "NO_IDENTITY_IN_B_MASTER",
    }[identity_status])
    if not observations:
        reasons.append("NO_V11_OBSERVATION")
    if not condition_resolvable:
        reasons.append("NOT_IN_ANY_CANDIDATE_POOL")
    if rooms > 0:
        reasons.append("ROOM_BAND_OBSERVATION_PRESENT")
    elif observations:
        reasons.append("NO_ROOM_BAND_OBSERVATION")
    if condition_resolvable and not room_band_qualified:
        reasons.append("CANDIDATE_OFF_ROOM_BAND")
    if frequency["frequency_status"] == "STATIC_ZERO_HZ_EVIDENCED":
        reasons.append("STATIC_FREQUENCY_EVIDENCED")
    elif frequency["frequency_status"] == "RF_ONLY":
        reasons.append("RF_FREQUENCY_ONLY")
    if observation_source["n_missing_doi_rows"] > 0:
        reasons.append("MISSING_DOI_ROWS_EXCLUDED_FROM_SOURCE_COUNT")
    if observation_source["independent_source_status"] == "SINGLE_SOURCE":
        reasons.append("SINGLE_INDEPENDENT_SOURCE")
    elif observation_source["independent_source_status"] == "DUAL_SOURCE":
        reasons.append("DUAL_INDEPENDENT_SOURCE")
    elif observation_source["independent_source_status"] == "CLUSTER_GE3":
        reasons.append("CLUSTER_GE3_INDEPENDENT_SOURCE")
    if source_alignment(v04_dois, observation_source) == "SOURCE_CONFLICT":
        reasons.append("SOURCE_CONFLICT_V04_VS_V11")
    if condition_resolvable and not signed_accept:
        reasons.append("HUMAN_SIGNATURE_PENDING")
    if "A9" in failed:
        reasons.append("EVIDENCE_GROUP_GATE_A9_FAILED")
    if "A11" in failed:
        reasons.append("HUMAN_QUALITY_GATE_A11_FAILED")

    return {
        "a_mol_id": mol_id,
        "a_name": str(core_row.get("name", "")).strip(),
        "a_smiles": str(core_row.get("smiles", "")).strip(),
        "a_inchikey": inchikey,
        "a_inchikey_skeleton": key,
        "identity_status": identity_status,
        "b_molecule_id": str(v04_row.get("inchikey", "")).strip() if v04_row else "",
        "b_source_doi_v04": joined(v04_dois),
        "b_T_K_v04": fmt_number(to_float(v04_row.get("T_K"))) if v04_row else "",
        "b_epsilon_v04": fmt_number(to_float(v04_row.get("dielectric"))) if v04_row else "",
        "b_band_v04": band_of(to_float(v04_row.get("T_K")), windows) if v04_row else "not_evaluated",
        "b_gate_flags_v04": str(v04_row.get("gate_flags", "")).strip() if v04_row else "",
        "candidate_layers": joined(layer_hits),
        "candidate_layer_count": str(len(layer_hits)),
        "qualifying_layers": joined(qualifying_layers),
        "qualifying_layer_count": str(len(qualifying_layers)),
        "candidate_measurement_ids": joined(candidate_ids),
        "n_candidate_measurements": str(len(candidate_ids)),
        "candidate_T_K": joined(candidate_temperatures),
        "candidate_bands": joined(candidate_bands),
        "candidate_n_room_band": str(candidate_rooms),
        "candidate_decisions": joined(c["decision"] for c in qualifying_candidates),
        "candidate_failed_gates": joined(failed),
        "v11_n_observations": str(len(observations)),
        "v11_n_room_band": str(rooms),
        "v11_n_source_doi": str(observation_source["n_source_doi"]),
        "v11_n_source_file": str(observation_source["n_source_file"]),
        "v11_n_source_groups": str(observation_source["n_source_groups"]),
        "v11_n_missing_doi_rows": str(observation_source["n_missing_doi_rows"]),
        "independent_source_status": observation_source["independent_source_status"],
        "phase_status": phase_status_of(observations),
        "frequency_status": frequency["frequency_status"],
        "v11_n_static_frequency": str(frequency["n_static"]),
        "v11_n_rf_frequency": str(frequency["n_rf"]),
        "pressure_status": pressure_status_of(observations),
        "source_alignment_status": source_alignment(v04_dois, observation_source),
        "gap_measurement_decision": gap_decision or "not_evaluated",
        "gap_license": str(gap_row.get("license", "")).strip() or "not_evaluated",
        "human_audit_status": admission["human_audit_status"],
        "human_admission_status": admission["human_admission_status"],
        "condition_resolvable": bool_text(condition_resolvable),
        "room_band_qualified": bool_text(room_band_qualified),
        "admitted": bool_text(admitted),
        "eligibility_verdict": verdict,
        "eligibility_reason_codes": joined(reasons),
    }


# ---------------------------------------------------------------------------
# 回填优先级 (逐分子)
# ---------------------------------------------------------------------------

#: (tier, rank_base, action) —— 顺序即优先级: 签名不是回填, 排在最前只为可见.
BACKFILL_TIERS: dict[str, dict[str, Any]] = {
    "P0_HUMAN_SIGNATURE_ONLY": {"rank": 0, "action": "SIGN_ADMISSION"},
    "P1_ADMISSION_ROW_CONSTRUCTION": {"rank": 10, "action": "CONSTRUCT_ADMISSION_ROW_FROM_V11"},
    "P2_ROOM_BAND_EVIDENCE": {"rank": 20, "action": "FIND_ROOM_BAND_MEASUREMENT"},
    "P3_STATIC_FREQUENCY_EVIDENCE": {"rank": 30, "action": "FIND_STATIC_FREQUENCY_EVIDENCE"},
    "P4_SOURCE_RETRIEVAL": {"rank": 40, "action": "RETRIEVE_SOURCE_ROW"},
    "P9_NO_ACTION_IDENTITY_MISSING": {"rank": 90, "action": "RESOLVE_IDENTITY_FIRST"},
}


def _retrieval_subrank(row: Mapping[str, str]) -> int:
    """P4 内部次序: 已有汇编 DOI 最先, 自带 zero_frequency 断言其次, 其余最后."""
    dois = {d.strip() for d in str(row.get("b_source_doi_v04", "")).split(";") if d.strip()}
    if NBS514_DOI in dois:
        return 0
    if "zero_frequency" in str(row.get("b_gate_flags_v04", "")):
        return 1
    return 2


def classify_backfill(row: Mapping[str, str]) -> dict[str, Any]:
    """给出该分子的 tier / rank / action / 下一动作目标源."""
    verdict = row["eligibility_verdict"]
    if verdict == VERDICT_NO_IDENTITY:
        tier = "P9_NO_ACTION_IDENTITY_MISSING"
        target = "not_evaluated"
    elif row["admitted"] == "true" or verdict == VERDICT_ADMITTED:
        tier = "P0_HUMAN_SIGNATURE_ONLY"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    elif verdict == VERDICT_QUALIFIED:
        tier = "P0_HUMAN_SIGNATURE_ONLY"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    elif verdict == VERDICT_OFF_BAND:
        tier = "P2_ROOM_BAND_EVIDENCE"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    elif verdict == VERDICT_OBS_ONLY and row["frequency_status"] == "STATIC_ZERO_HZ_EVIDENCED":
        tier = "P1_ADMISSION_ROW_CONSTRUCTION"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    elif verdict == VERDICT_OBS_ONLY:
        tier = "P3_STATIC_FREQUENCY_EVIDENCE"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    else:
        tier = "P4_SOURCE_RETRIEVAL"
        target = joined(str(row["b_source_doi_v04"]).split(";"))
    base = BACKFILL_TIERS[tier]["rank"]
    sub = _retrieval_subrank(row) if tier == "P4_SOURCE_RETRIEVAL" else 0
    return {
        "backfill_tier": tier,
        "backfill_rank": base + sub,
        "backfill_action": BACKFILL_TIERS[tier]["action"],
        "backfill_target_source": target or "not_evaluated",
    }


def apply_backfill_priority(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """写入 tier/rank/action, 并按 (rank, mol_id) 给出全局顺序."""
    for row in rows:
        row.update(classify_backfill(row))
    rows.sort(key=lambda r: (int(r["backfill_rank"]), r["a_mol_id"]))
    for position, row in enumerate(rows, start=1):
        row["backfill_order"] = str(position)
    return rows


# ---------------------------------------------------------------------------
# GO / NO-GO
# ---------------------------------------------------------------------------

def build_gate_table(rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    """要求的七维分别给出行数; 任何一维都不代表其余维度."""
    total = len(rows)

    def counter(predicate) -> tuple[int, list[str]]:
        passed = [r["a_mol_id"] for r in rows if predicate(r)]
        blocked = [r["a_mol_id"] for r in rows if not predicate(r)]
        return len(passed), blocked

    identity_pass, identity_blocked = counter(lambda r: r["identity_status"] != VERDICT_NO_IDENTITY)
    source_pass, source_blocked = counter(lambda r: r["independent_source_status"] != "NO_SOURCE")
    temperature_pass, temperature_blocked = counter(
        lambda r: int(r["v11_n_room_band"]) > 0 or int(r["candidate_n_room_band"]) > 0
    )
    phase_pass, phase_blocked = counter(lambda r: r["phase_status"] == "LIQUID_EVIDENCED_IN_V11")
    frequency_pass, frequency_blocked = counter(
        lambda r: r["frequency_status"] == "STATIC_ZERO_HZ_EVIDENCED"
    )
    human_pass, human_blocked = counter(lambda r: r["human_admission_status"] == "SIGNED_ACCEPT")
    dual_pass, dual_blocked = counter(lambda r: int(r["v11_n_source_groups"]) >= 2)
    cluster_pass, cluster_blocked = counter(lambda r: int(r["v11_n_source_groups"]) >= 3)

    return [
        {"dimension": "identity", "criterion": "A 母体在 B 主表中身份命中",
         "n_pass": identity_pass, "n_total": total, "blocking_molecules": identity_blocked},
        {"dimension": "source", "criterion": "至少一条可追溯来源 (DOI 或来源文件)",
         "n_pass": source_pass, "n_total": total, "blocking_molecules": source_blocked},
        {"dimension": "temperature", "criterion": "存在室温带 (293.15-303.15 K) 观测或候选行",
         "n_pass": temperature_pass, "n_total": total, "blocking_molecules": temperature_blocked},
        {"dimension": "phase", "criterion": "v11 逐行相态证据均为液体",
         "n_pass": phase_pass, "n_total": total, "blocking_molecules": phase_blocked},
        {"dimension": "frequency", "criterion": "存在 static/zero-frequency 逐行证据",
         "n_pass": frequency_pass, "n_total": total, "blocking_molecules": frequency_blocked},
        {"dimension": "human_admission", "criterion": "存在显式 ACCEPT 签批",
         "n_pass": human_pass, "n_total": total, "blocking_molecules": human_blocked},
        {"dimension": "independent_source_count_ge2", "criterion": "独立来源组 >= 2",
         "n_pass": dual_pass, "n_total": total, "blocking_molecules": dual_blocked},
        {"dimension": "independent_source_count_ge3", "criterion": "独立来源组 >= 3 (来源簇检验下限)",
         "n_pass": cluster_pass, "n_total": total, "blocking_molecules": cluster_blocked},
    ]


def build_go_nogo(
    rows: Sequence[Mapping[str, str]],
    *,
    protocol: Mapping[str, Any],
    k_rule: Mapping[str, Any],
    gates: Sequence[Mapping[str, Any]],
    criteria_sha256: str,
    inputs_sha256: Mapping[str, str],
    environment: Mapping[str, str],
    v56_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """当前证据下确认性联合 Top-k / regret 的裁决."""
    total = len(rows)
    n_identity = sum(1 for r in rows if r["identity_status"] != VERDICT_NO_IDENTITY)
    n_condition = sum(1 for r in rows if r["condition_resolvable"] == "true")
    n_room = sum(1 for r in rows if r["room_band_qualified"] == "true")
    n_admitted = sum(1 for r in rows if r["admitted"] == "true")
    qualified = [r for r in rows if r["condition_resolvable"] == "true"]
    n_dual = sum(1 for r in qualified if int(r["v11_n_source_groups"]) >= 2)
    n_cluster = sum(1 for r in qualified if int(r["v11_n_source_groups"]) >= 3)
    rule_text = str(k_rule.get("rule", ""))
    k_now = primary_k(n_room, rule_text)
    n_for_k3 = min_n_for_primary_k(3, rule_text)

    blocking = [
        {
            "code": "NO_ADMITTED_LABEL",
            "detail": (
                f"{total} 个 A 母体中 {n_admitted} 个取得 ACCEPT 标签; "
                "B 的 admission 仍全部停在 HOLD/待人类签批"
            ),
            "evidence": "joint_eligibility.csv::human_admission_status",
        },
        {
            "code": "CONDITION_RESOLVABLE_POOL_TOO_SMALL",
            "detail": (
                f"条件可解析 {n_condition}/{total}; 室温带合格 {n_room}/{total}; "
                f"按冻结 k 规则 primary_k={k_now}, 需 n>={n_for_k3} 才能得到 primary_k>=3"
            ),
            "evidence": "joint_pool_layer_summary.json + joint_go_nogo.json::denominators",
        },
        {
            "code": "NO_DUAL_INDEPENDENT_SOURCE_IN_QUALIFIED_POOL",
            "detail": (
                f"合格池内独立来源组 >=2 的分子 {n_dual} 个、>=3 的 {n_cluster} 个; "
                "来源簇稳健性检验在合格池上不可估"
            ),
            "evidence": "joint_eligibility.csv::v11_n_source_groups",
        },
        {
            "code": "A_SIDE_REDOX_NOT_EVALUATED",
            "detail": "A 侧 redox/pair 合格标签 (ox_eligible) 本轮未评估, 联合分母不能只按 B 侧算",
            "evidence": "joint_go_nogo.json::not_evaluated",
        },
    ]

    return {
        "analysis_id": ANALYSIS_ID,
        "analysis_title": ANALYSIS_TITLE,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "question": "在当前可准入证据上, A18 x B 的确认性联合 Top-k / regret 是否可以评估?",
        "verdict": "NO_GO_INSUFFICIENT_ELIGIBLE_DATA",
        "verdict_scope": (
            "仅限确认性联合 Top-k / regret / 联合模型对比; "
            "逐分子处置与证据缺口登记仍照常报告"
        ),
        "descriptive_only": True,
        "confirmatory_metrics_emitted": [],
        "join_unit": A_JOIN_UNIT,
        "denominators": {
            "n_a_core_neutral_parents": total,
            "n_identity_common_in_candidate_master": n_identity,
            "n_condition_resolvable": n_condition,
            "n_room_band_qualified": n_room,
            "n_admitted": n_admitted,
            "n_dual_or_more_independent_sources_in_qualified_pool": n_dual,
            "n_cluster_ge3_independent_sources_in_qualified_pool": n_cluster,
            "primary_k_under_frozen_rule": k_now,
            "n_required_for_primary_k_ge_3": n_for_k3,
            "primary_k_rule_text": rule_text,
        },
        "snapshot": {
            "n_identity_common": n_identity,
            "n_condition_resolvable": n_condition,
            "n_room_band_qualified": n_room,
            "n_admitted": n_admitted,
            "condition_resolvable_ids": sorted(r["a_mol_id"] for r in qualified),
            "room_band_qualified_ids": sorted(r["a_mol_id"] for r in rows if r["room_band_qualified"] == "true"),
            "off_room_band_condition_resolvable": sorted(
                ({"mol_id": r["a_mol_id"], "name": r["a_name"],
                  "candidate_T_K": r["candidate_T_K"], "candidate_bands": r["candidate_bands"]}
                 for r in qualified if r["room_band_qualified"] != "true"),
                key=lambda d: d["mol_id"],
            ),
        },
        "gate_table": list(gates),
        "gap_groups": {
            "zero_observation": {
                "criterion": "身份命中但 v11 观测层 0 条",
                "count": sum(1 for r in rows if r["v11_n_observations"] == "0"),
                "mol_ids": sorted(r["a_mol_id"] for r in rows if r["v11_n_observations"] == "0"),
            },
            "observation_ready_unqualified": {
                "criterion": "有 v11 观测但不属于任何带证据裁决的候选层",
                "count": sum(1 for r in rows if r["eligibility_verdict"] == VERDICT_OBS_ONLY),
                "mol_ids": sorted(r["a_mol_id"] for r in rows if r["eligibility_verdict"] == VERDICT_OBS_ONLY),
            },
            "condition_resolvable_off_room_band": {
                "criterion": "属于候选层但候选行温度全部在室温带之外",
                "count": sum(1 for r in rows if r["eligibility_verdict"] == VERDICT_OFF_BAND),
                "mol_ids": sorted(r["a_mol_id"] for r in rows if r["eligibility_verdict"] == VERDICT_OFF_BAND),
            },
            "condition_qualified_pending_human": {
                "criterion": "候选行落在室温带且只缺人工签批",
                "count": sum(1 for r in rows if r["eligibility_verdict"] == VERDICT_QUALIFIED),
                "mol_ids": sorted(r["a_mol_id"] for r in rows if r["eligibility_verdict"] == VERDICT_QUALIFIED),
            },
        },
        "blocking_reasons": blocking,
        "reopen_conditions": [
            {
                "id": "R1",
                "condition": (
                    f"联合室温带合格并签批的分子数 >= {n_for_k3}, "
                    "使 primary_k = max(1, ceil(n/10)) >= 3"
                ),
                "current": n_admitted,
                "target": n_for_k3,
                "status": "OPEN",
            },
            {
                "id": "R2",
                "condition": "新证据进入确认分析之前, 资格标准与统计方案已冻结并预注册",
                "current": f"criteria_sha256={criteria_sha256[:16]}; "
                           f"target_protocol.status={protocol.get('status')}, frozen={protocol.get('frozen')}",
                "target": "protocol 由 DRAFT_PENDING_HUMAN_APPROVAL 转为人工批准版本 + 预注册件",
                "status": "OPEN",
            },
            {
                "id": "R3",
                "condition": "任何来源簇/聚类稳健性主张要求所报分组内独立来源组 >= 3",
                "current": n_cluster,
                "target": 3,
                "status": "OPEN",
            },
            {
                "id": "R4",
                "condition": "输入 SHA256 与契约版本一并显式升级, 并重建本目录",
                "current": INPUT_CONTRACT_VERSION,
                "target": "新 input contract 版本 + 新 joint_inputs_manifest.json",
                "status": "OPEN",
            },
        ],
        "preregistration_requirement": {
            "status": "NOT_FROZEN",
            "criteria_sha256": criteria_sha256,
            "protocol_status": protocol.get("status"),
            "protocol_frozen": protocol.get("frozen"),
            "protocol_version": protocol.get("protocol_version"),
            "gate_ids": list(ADMISSION_GATES),
            "rule": (
                "本条裁决的资格标准由 joint_eligibility_criteria.json 固化; "
                "新证据可以重评 GO, 但必须先冻结该文件与统计方案, 再让新证据进入确认分析"
            ),
        },
        "forbidden_outputs": [
            "joint_topk_sets",
            "joint_mean_regret",
            "joint_model_comparison",
            "joint_confirmatory_effect_size",
            "any_per_molecule_ranking_presented_as_confirmatory",
        ],
        "not_evaluated": [
            "a_side_redox_pair_eligible",
            "joint_topk",
            "joint_regret",
            "joint_cluster_robustness",
            "source_license_redistribution_scope",
        ],
        "inputs": dict(sorted(inputs_sha256.items())),
        "environment": dict(sorted(environment.items())),
        "v56_version_record": {
            "project": v56_manifest.get("project"),
            "generated_by": v56_manifest.get("generated_by"),
            "counts": v56_manifest.get("counts"),
        },
    }


def build_criteria_snapshot(
    *,
    protocol: Mapping[str, Any],
    k_rule: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """可被冻结的资格标准快照; 冻结后任何改动都要新契约版本."""
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "freeze_state": "NOT_FROZEN_DRAFT",
        "join_unit": A_JOIN_UNIT,
        "join_rule": (
            "A 侧只取 18 个中性母体的规范 SMILES -> InChIKey, 以首段骨架与 B 的 "
            "molecule_id / v04 inchikey 连接; Li 配合物(LiM_plus/LiM_2plus)与带电态不参与连接"
        ),
        "layers_reported_separately": [name for name, _k, _c in CANDIDATE_LAYERS],
        "dimensions": [
            {"key": "identity_status", "allowed": [
                "IDENTITY_FULL_KEY", "IDENTITY_SKELETON_ONLY", "IDENTITY_ABSENT"]},
            {"key": "independent_source_status", "allowed": [
                "NO_SOURCE", "SINGLE_SOURCE", "DUAL_SOURCE", "CLUSTER_GE3"]},
            {"key": "temperature", "windows_K": [dict(w) for w in windows]},
            {"key": "phase", "allowed": [
                "LIQUID_EVIDENCED_IN_V11", "MIXED_PHASE_EVIDENCE",
                "PHASE_UNKNOWN", "NOT_EVALUATED"]},
            {"key": "frequency", "allowed": [
                "STATIC_ZERO_HZ_EVIDENCED", "RF_ONLY", "FREQUENCY_UNKNOWN", "NOT_EVALUATED"]},
            {"key": "human_admission", "allowed": [
                "SIGNED_ACCEPT", "NOT_SIGNED", "NO_ADMISSION_ROW"]},
            {"key": "independent_source_count", "ge2_for_source_robustness": True,
             "ge3_for_cluster_claims": True},
        ],
        "verdict_rules": [
            f"{VERDICT_ADMITTED}: human_admission=SIGNED_ACCEPT 且 gap measurement_decision=ACCEPT",
            f"{VERDICT_QUALIFIED}: condition_resolvable=true 且候选行存在室温带",
            f"{VERDICT_OFF_BAND}: condition_resolvable=true 但候选行全部在室温带之外",
            f"{VERDICT_OBS_ONLY}: 有 v11 观测但不属于任何候选层",
            f"{VERDICT_IDENTITY_ONLY}: 身份命中但无 v11 观测",
        ],
        "condition_resolvable_definition": "分子出现在 candidate_master / pool_c / pool_b / worksheet_40 / formal_draft_20 任一层",
        "room_band_qualified_definition": "condition_resolvable 且至少一条候选行的 T_K 落在 room_temperature 温窗内",
        "admitted_definition": "gap measurement_decision=ACCEPT 且人类签批状态为 SIGNED_ACCEPT",
        "k_rule": dict(k_rule),
        "admission_gates": list(ADMISSION_GATES),
        "never_default_rules": [
            "未知温度不得默认 298.15 K",
            "未知相态不得默认 liquid",
            "未知频率不得写 0 Hz",
            "未知压强不得写 1 atm",
            "epsilon 不得跨来源平均",
            "缺失必需字段只能 HOLD/REJECT, 不得静默补 0",
            "缺失 DOI 的行不计入独立来源数, 另计 missing_doi_rows",
        ],
        "forbidden": [
            "以单一 matched=true 代替七维裁决",
            "把 Li 配合物或带电态直接 join 到纯液体实验记录",
            "在分母不足时产出 Top-k / regret 等确认性指标",
            "为了让 GO 成立而事后放宽本文件",
        ],
    }


# ---------------------------------------------------------------------------
# 输出渲染
# ---------------------------------------------------------------------------

ELIGIBILITY_COLUMNS: tuple[str, ...] = (
    "a_mol_id", "a_name", "a_smiles", "a_inchikey", "a_inchikey_skeleton",
    "identity_status", "b_molecule_id", "b_source_doi_v04", "b_T_K_v04",
    "b_epsilon_v04", "b_band_v04", "b_gate_flags_v04",
    "candidate_layers", "candidate_layer_count", "qualifying_layers",
    "qualifying_layer_count", "candidate_measurement_ids",
    "n_candidate_measurements", "candidate_T_K", "candidate_bands",
    "candidate_n_room_band", "candidate_decisions", "candidate_failed_gates",
    "v11_n_observations", "v11_n_room_band", "v11_n_source_doi", "v11_n_source_file",
    "v11_n_source_groups", "v11_n_missing_doi_rows", "independent_source_status",
    "phase_status", "frequency_status", "v11_n_static_frequency", "v11_n_rf_frequency",
    "pressure_status", "source_alignment_status", "gap_measurement_decision",
    "gap_license", "human_audit_status", "human_admission_status",
    "condition_resolvable", "room_band_qualified", "admitted",
    "eligibility_verdict", "eligibility_reason_codes",
    "backfill_tier", "backfill_rank", "backfill_order", "backfill_action",
    "backfill_target_source",
)

OBSERVATION_COLUMNS: tuple[str, ...] = (
    "a_mol_id", "a_name", "a_inchikey_skeleton", "v11_row_number", "inchikey",
    "T_K", "temperature_band_v11", "declared_band", "phase", "frequency_mhz",
    "pressure_kpa", "property_name", "source_doi", "source_file", "model_ready",
    "freq_is_static", "phase_is_liquid", "pressure_present", "temperature_in_room_band",
    "source_key", "evidence_note",
)

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "a_mol_id", "a_name", "measurement_id", "layers", "epsilon", "T_K",
    "declared_band", "source_group", "decision", "evidence_group_id",
    "failed_gates", "human_audit_status", "machine_audit_status",
)

PRIORITY_COLUMNS: tuple[str, ...] = (
    "priority_order", "a_mol_id", "a_name", "backfill_tier", "backfill_action",
    "eligibility_verdict", "v11_n_observations", "v11_n_room_band",
    "frequency_status", "independent_source_status", "backfill_target_source",
    "current_blocker",
)


def render_csv(columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")


def render_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_layer_summary(
    dataset: Mapping[str, Any], layers: Mapping[str, Sequence[Mapping[str, str]]], a18_skeletons: set[str]
) -> dict[str, Any]:
    """逐层行数/骨架数/A18 命中, 以及层间两两交集 (单独报告, 不合并)."""
    per_layer: dict[str, Any] = {}
    keysets: dict[str, set[str]] = {}
    for layer_name, _input_key, _id_column in CANDIDATE_LAYERS:
        records = layers[layer_name]
        keys = {r["skeleton"] for r in records}
        keysets[layer_name] = keys
        hits = sorted(s for s in keys if s in a18_skeletons)
        per_layer[layer_name] = {
            "n_rows": len(records),
            "n_unique_skeletons": len(keys),
            "n_a18_hits": len(hits),
            "a18_hit_skeletons": hits,
        }
    # v11 观测层单独作为一层报告 (它不是候选层, 但必须一起看交集)
    observation_skeletons = {skeleton(r["inchikey"]) for r in dataset["observations"]}
    keysets["v11_observation_layer"] = observation_skeletons
    observation_hits = sorted(s for s in observation_skeletons if s in a18_skeletons)
    per_layer["v11_observation_layer"] = {
        "n_rows": len(dataset["observations"]),
        "n_unique_skeletons": len(observation_skeletons),
        "n_a18_hits": len(observation_hits),
        "a18_hit_skeletons": observation_hits,
    }
    preview = {
        skeleton(r["molecule_id"]) for r in dataset["master"]
        if str(r.get("in_49_preview", "")).strip().lower() == "yes"
    }
    keysets["master_49_preview"] = preview
    per_layer["master_49_preview"] = {
        "n_rows": len(preview),
        "n_unique_skeletons": len(preview),
        "n_a18_hits": len([s for s in preview if s in a18_skeletons]),
        "a18_hit_skeletons": sorted(s for s in preview if s in a18_skeletons),
        "note": "preview 标记不是最终池, 仅作对照 (见 integrity_checks)",
    }
    pairwise: dict[str, int] = {}
    names = sorted(keysets)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            pairwise[f"{left}&{right}"] = len(keysets[left] & keysets[right])
    return {
        "analysis_id": ANALYSIS_ID,
        "join_unit": A_JOIN_UNIT,
        "n_a18_skeletons": len(a18_skeletons),
        "layers": per_layer,
        "pairwise_intersection_sizes": dict(sorted(pairwise.items())),
        "note": "每层独立报告; 任何单一层的命中数都不能代替七维裁决",
    }


def render_report(
    *,
    rows: Sequence[Mapping[str, str]],
    go_nogo: Mapping[str, Any],
    layer_summary: Mapping[str, Any],
    inputs_manifest: Mapping[str, Any],
    priority_rows: Sequence[Mapping[str, str]],
) -> bytes:
    """人读审计报告; 内容全部来自已计算结构, 不含墙钟时间."""
    denominators = go_nogo["denominators"]
    snapshot = go_nogo["snapshot"]
    lines: list[str] = []
    add = lines.append

    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约版本: `{ANALYSIS_ID}` / `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add(f"- 连接单位: `{A_JOIN_UNIT}` (只连中性母体; Li 配合物与带电态不参与)")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建 (见 `joint_rebuild_receipt.json`)")
    add("")
    add("## 1. 结论")
    add("")
    add(f"**`{go_nogo['verdict']}`** — {go_nogo['verdict_scope']}")
    add("")
    add("| 分母 | 值 |")
    add("|---|---:|")
    for key in (
        "n_a_core_neutral_parents",
        "n_identity_common_in_candidate_master",
        "n_condition_resolvable",
        "n_room_band_qualified",
        "n_admitted",
        "n_dual_or_more_independent_sources_in_qualified_pool",
        "n_cluster_ge3_independent_sources_in_qualified_pool",
        "primary_k_under_frozen_rule",
        "n_required_for_primary_k_ge_3",
    ):
        add(f"| `{key}` | {denominators[key]} |")
    add("")
    add("本轮没有生成任何联合性能指标 (字段 `confirmatory_metrics_emitted` 为空); "
        "分子级排序只能作为描述性处置, 不得当作确认性结论。")
    add("")
    add("## 2. 输入与冻结")
    add("")
    add(f"- B 仓 HEAD: `{inputs_manifest['provenance']['b_repo']['head']}` "
        f"(tag `v1.3` = `{inputs_manifest['provenance']['b_repo']['tag_v1_3_commit']}`, "
        f"已跟踪文件改动 {inputs_manifest['provenance']['b_repo']['tracked_modifications']}, "
        f"领先 origin/main {inputs_manifest['provenance']['b_repo']['commits_ahead_of_origin_main']} 个提交)")
    counts = inputs_manifest["provenance"]["v56"].get("counts") or {}
    add(f"- v56 版本记录: `{inputs_manifest['provenance']['v56']['project']}` "
        f"(生成器 `{inputs_manifest['provenance']['v56']['generated_by']}`, "
        f"files={counts.get('files')}, rewritten_files={counts.get('rewritten_files')}), "
        f"MANIFEST sha256 `{inputs_manifest['v56_manifest_sha256'][:16]}`")
    add("")
    add("| 输入 | 角色 | bytes | sha256 |")
    add("|---|---|---:|---|")
    for entry in inputs_manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['role']} | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    add("### 已登记的不一致 (记录, 不修复)")
    add("")
    add("| 检查 | 状态 | 说明 |")
    add("|---|---|---|")
    for check in inputs_manifest["integrity_checks"]:
        if "problems" in check:
            detail = f"problems={len(check['problems'])}, passed={check.get('passed')}/{check.get('checked')}"
        else:
            detail = str(check.get("detail", ""))
        add(f"| `{check['name']}` | {check['status']} | {detail} |")
    add("")
    add("## 3. 分层交集")
    add("")
    add("| 层 | 行 | 唯一骨架 | A18 命中 |")
    add("|---|---:|---:|---:|")
    for layer_name in sorted(layer_summary["layers"]):
        info = layer_summary["layers"][layer_name]
        add(f"| `{layer_name}` | {info['n_rows']} | {info['n_unique_skeletons']} | {info['n_a18_hits']} |")
    add("")
    add("## 4. 七维裁决")
    add("")
    add("注: 本表按 A 全部 18 个母体统计; 第 1 节 `denominators` 里的来源稳健性计数只在"
        "**已可解析池** (4 个) 上算 —— 两者分母不同, 不可互相替代。")
    add("")
    add("| 维度 | 判据 | 通过 | 合计 | 未通过分子 |")
    add("|---|---|---:|---:|---|")
    for gate in go_nogo["gate_table"]:
        blocked = ",".join(gate["blocking_molecules"]) or "—"
        add(f"| `{gate['dimension']}` | {gate['criterion']} | {gate['n_pass']} | "
            f"{gate['n_total']} | {blocked} |")
    add("")
    add("## 5. 逐分子结果")
    add("")
    add("| mol | 名称 | 候选层 | v11观测 | 室温 | 来源组 | 频段 | 温带(候选或v04) | 裁决 |")
    add("|---|---|---|---:|---:|---:|---|---|---|")
    for row in rows:
        add(
            f"| {row['a_mol_id']} | {row['a_name']} | {row['candidate_layers'] or '—'} | "
            f"{row['v11_n_observations']} | {row['v11_n_room_band']} | "
            f"{row['v11_n_source_groups']} | {row['frequency_status']} | "
            f"{row['candidate_bands'] or row['b_band_v04']} | {row['eligibility_verdict']} |"
        )
    add("")
    add("## 6. 三类点名缺口")
    add("")
    gap_groups = go_nogo["gap_groups"]
    add("这三组互不重叠, 加起来覆盖 A18 的全部未合格分子; 报告顺序即处置顺序。")
    add("")
    add("### 6.1 零观测分子 (需要取数)")
    add("")
    zero = gap_groups["zero_observation"]
    add(f"判定: {zero['criterion']}; 计数 **{zero['count']}**。")
    add("")
    add("| mol | 名称 | v04 已登记来源 | v04 T_K | v04 温带 |")
    add("|---|---|---|---:|---|")
    zero_ids = set(zero["mol_ids"])
    for row in rows:
        if row["a_mol_id"] in zero_ids:
            add(f"| {row['a_mol_id']} | {row['a_name']} | {row['b_source_doi_v04']} | "
                f"{row['b_T_K_v04']} | {row['b_band_v04']} |")
    add("")
    add("### 6.2 已有观测但未取得资格的分子 (证据在, 候选行不在)")
    add("")
    ready = gap_groups["observation_ready_unqualified"]
    add(f"判定: {ready['criterion']}; 计数 **{ready['count']}**。")
    add("")
    add("| mol | 名称 | v11观测 | 室温 | 来源组 | 频段 | 相态 | 对齐 | 阻断原因 |")
    add("|---|---|---:|---:|---:|---|---|---|---|")
    ready_ids = set(ready["mol_ids"])
    for row in rows:
        if row["a_mol_id"] in ready_ids:
            add(f"| {row['a_mol_id']} | {row['a_name']} | {row['v11_n_observations']} | "
                f"{row['v11_n_room_band']} | {row['v11_n_source_groups']} | "
                f"{row['frequency_status']} | {row['phase_status']} | "
                f"{row['source_alignment_status']} | {row['eligibility_verdict']} |")
    add("")
    add("### 6.3 温带外已可解析 (只差室温证据)")
    add("")
    off = gap_groups["condition_resolvable_off_room_band"]
    add(f"判定: {off['criterion']}; 计数 **{off['count']}**。")
    add("")
    add("## 7. 温带记录 (不在室温带的已可解析候选)")
    add("")
    off_band = snapshot["off_room_band_condition_resolvable"]
    if off_band:
        add("| mol | 名称 | 候选 T_K | 候选温带 |")
        add("|---|---|---|---|")
        for entry in off_band:
            add(f"| {entry['mol_id']} | {entry['name']} | {entry['candidate_T_K']} | "
                f"{entry['candidate_bands']} |")
        add("")
        add("这些行保留原始温度, 不折算到室温, 也不因不在室温带而被删除。")
    else:
        add("无。")
    add("")
    add("## 8. 来源回填优先级")
    add("")
    add("| 序 | mol | 名称 | 层 | 动作 | 当前阻断 | 目标来源 |")
    add("|---:|---|---|---|---|---|---|")
    for row in priority_rows:
        add(
            f"| {row['priority_order']} | {row['a_mol_id']} | {row['a_name']} | "
            f"`{row['backfill_tier']}` | `{row['backfill_action']}` | "
            f"{row['current_blocker']} | {row['backfill_target_source']} |"
        )
    add("")
    add("## 9. 重开条件")
    add("")
    add("| id | 条件 | 当前 | 目标 | 状态 |")
    add("|---|---|---|---|---|")
    for item in go_nogo["reopen_conditions"]:
        add(f"| {item['id']} | {item['condition']} | {item['current']} | {item['target']} | {item['status']} |")
    add("")
    add(f"资格标准快照: `joint_eligibility_criteria.json` "
        f"(freeze_state = `{go_nogo['preregistration_requirement']['status']}`; "
        f"sha256 `{go_nogo['preregistration_requirement']['criteria_sha256'][:16]}`)。"
        "新证据可以重评 GO, 但必须先冻结该文件与统计方案。")
    add("")
    add("## 10. 未评估与不授权项")
    add("")
    for item in go_nogo["not_evaluated"]:
        add(f"- `{item}`: not_evaluated")
    add("")
    add("- 本轮不修改 v1.3 冻结产物, 不执行人类 admission 签批, 不新增 ORCA/DFT 计算, 不执行 git push。")
    add("")
    add("## 11. 重建")
    add("")
    add("```")
    add("python scripts/confirm_2027/build_joint_eligibility.py --check")
    add("```")
    add("")
    add("相同输入下重建产物逐字节一致; 输入 SHA256 或契约版本变化时本工具以非零退出码拒绝出数。")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def collect_environment() -> dict[str, str]:
    try:
        from rdkit import rdBase

        rdkit_version = rdBase.rdkitVersion
    except Exception:  # pragma: no cover - 环境缺失时不能假装
        rdkit_version = "not_importable"
    return {
        "python": platform.python_version(),
        "rdkit": rdkit_version,
        "platform": platform.platform(terse=True),
    }


def prepare_indices(
    dataset: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """把原始表整理成逐维裁决需要的索引; 唯一入口, 避免测试与生产各写一套."""
    v04_by_skeleton = {
        skeleton(r["inchikey"]): r for r in dataset["v04"] if skeleton(r["inchikey"])
    }
    gap_by_skeleton: dict[str, Mapping[str, str]] = {}
    for row in dataset["gap"]:
        gap_by_skeleton.setdefault(skeleton(row["molecule_id"]), row)
    return {
        "v04_by_skeleton": v04_by_skeleton,
        "observations_by_skeleton": index_by_skeleton(dataset["observations"], "inchikey"),
        "gap_by_skeleton": gap_by_skeleton,
        "worksheet_by_id": {str(r["measurement_id"]).strip(): r for r in dataset["worksheet"]},
        "gap_by_id": {str(r["measurement_id"]).strip(): r for r in dataset["gap"]},
        "formal_by_id": {str(r["measurement_id"]).strip(): r for r in dataset["formal"]},
        "layers": build_layer_records(dataset),
        "candidate_index": build_candidate_index(dataset, windows),
    }


def adjudicate_all(
    dataset: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """对 A 全部母体逐条裁决并写入回填优先级; 返回按 mol_id 排序的完整行.

    返回的行已是"可直接进 CSV 的成品": 既含七维裁决, 也含 backfill_tier/rank/order.
    """
    indices = prepare_indices(dataset, windows)
    rows = [
        adjudicate_molecule(
            row,
            v04_by_skeleton=indices["v04_by_skeleton"],
            observations_by_skeleton=indices["observations_by_skeleton"],
            gap_by_skeleton=indices["gap_by_skeleton"],
            candidate_index=indices["candidate_index"],
            layers=indices["layers"],
            worksheet_by_id=indices["worksheet_by_id"],
            gap_by_id=indices["gap_by_id"],
            formal_by_id=indices["formal_by_id"],
            windows=windows,
        )
        for row in sorted(dataset["core"], key=lambda r: str(r.get("mol_id", "")))
    ]
    rows = apply_backfill_priority(rows)
    rows.sort(key=lambda r: r["a_mol_id"])
    return rows


def build_outputs(
    dataset: Mapping[str, Any],
    *,
    inputs_manifest: Mapping[str, Any],
    environment: Mapping[str, str],
) -> dict[str, bytes]:
    """纯函数式装配: 相同 dataset => 相同 bytes (无墙钟、无随机)."""
    windows = list(dataset["protocol"]["allowed_temperature_windows_K"])
    core = sorted(dataset["core"], key=lambda r: str(r.get("mol_id", "")))
    if len(core) != 18:
        raise JointEligibilityError(f"A 中性母体应为 18 个, 实际 {len(core)}")

    v04_by_skeleton = {
        skeleton(r["inchikey"]): r for r in dataset["v04"] if skeleton(r["inchikey"])
    }
    indices = prepare_indices(dataset, windows)
    layers = indices["layers"]
    candidate_index = indices["candidate_index"]

    eligibility_rows = adjudicate_all(dataset, windows)
    priority_rows = sorted(
        eligibility_rows, key=lambda r: (int(r["backfill_rank"]), r["a_mol_id"])
    )

    # 逐条观测证据 (A18 x v11), 行号用文件内 1-based 数据行序, 便于回查
    obs_rows: list[dict[str, str]] = []
    mol_ids_by_skeleton = {r["a_inchikey_skeleton"]: r for r in eligibility_rows}
    for row_number, observation in enumerate(dataset["observations"], start=1):
        key = skeleton(observation["inchikey"])
        if key not in mol_ids_by_skeleton:
            continue
        owner = mol_ids_by_skeleton[key]
        temperature = to_float(observation.get("T_K"))
        frequency = to_float(observation.get("frequency_mhz"))
        pressure = to_float(observation.get("pressure_kpa"))
        doi = str(observation.get("source_doi", "")).strip()
        file_name = str(observation.get("source_file", "")).strip()
        notes: list[str] = []
        if not doi:
            notes.append("MISSING_DOI")
        if temperature is None:
            notes.append("TEMPERATURE_UNKNOWN")
        if not str(observation.get("phase", "")).strip():
            notes.append("PHASE_UNKNOWN")
        if frequency is None:
            notes.append("FREQUENCY_UNKNOWN")
        if pressure is None:
            notes.append("PRESSURE_UNKNOWN")
        if band_of(temperature, windows) != str(observation.get("temperature_band", "")).strip():
            notes.append("DECLARED_BAND_DIFFERS")
        obs_rows.append({
            "a_mol_id": owner["a_mol_id"],
            "a_name": owner["a_name"],
            "a_inchikey_skeleton": key,
            "v11_row_number": str(row_number),
            "inchikey": str(observation.get("inchikey", "")).strip(),
            "T_K": fmt_number(temperature),
            "temperature_band_v11": str(observation.get("temperature_band", "")).strip(),
            "declared_band": band_of(temperature, windows),
            "phase": str(observation.get("phase", "")).strip(),
            "frequency_mhz": fmt_number(frequency),
            "pressure_kpa": fmt_number(pressure),
            "property_name": str(observation.get("property_name", "")).strip(),
            "source_doi": doi,
            "source_file": file_name,
            "model_ready": str(observation.get("model_ready", "")).strip(),
            "freq_is_static": bool_text(frequency == 0.0),
            "phase_is_liquid": bool_text(str(observation.get("phase", "")).strip().lower() == "liquid"),
            "pressure_present": bool_text((pressure or 0.0) > 0.0),
            "temperature_in_room_band": bool_text(band_of(temperature, windows) == "room_temperature"),
            "source_key": f"doi:{doi}" if doi else (f"file:{file_name}" if file_name else ""),
            "evidence_note": joined(notes),
        })
    obs_rows.sort(key=lambda r: (r["a_mol_id"], int(r["v11_row_number"])))

    # 逐条候选测量行 (A18 x 4 候选层, 按 measurement_id 去重后每行一条, layers 列写明所属层)
    cand_rows: list[dict[str, str]] = []
    for key, candidates in candidate_index.items():
        if key not in mol_ids_by_skeleton:
            continue
        owner = mol_ids_by_skeleton[key]
        merged: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            entry = merged.setdefault(candidate["measurement_id"], {
                "layers": set(), "epsilon": "", "T_K": "", "band": "", "source_group": "",
                "decision": set(), "evidence_group_id": "", "failed_gates": set(),
                "human_audit_status": set(), "machine_audit_status": set(),
            })
            entry["layers"].add(candidate["layer"])
            # 哪一层真正带这个字段就用哪一层的值; not_evaluated 视为"没有", 不许占位
            entry["epsilon"] = _prefer(entry["epsilon"], candidate["epsilon"])
            entry["T_K"] = _prefer(entry["T_K"], candidate["T_K"])
            entry["band"] = band_of(to_float(entry["T_K"]), windows)
            entry["source_group"] = _prefer(entry["source_group"], candidate["source_group"])
            if candidate["decision"] and candidate["decision"] != NOT_EVALUATED:
                entry["decision"].add(candidate["decision"])
            entry["evidence_group_id"] = _prefer(entry["evidence_group_id"], candidate["evidence_group_id"])
            if candidate["failed_gates"]:
                entry["failed_gates"].update(
                    g.strip() for g in candidate["failed_gates"].split(",") if g.strip()
                )
            if candidate["human_audit_status"]:
                entry["human_audit_status"].add(candidate["human_audit_status"])
            if candidate["machine_audit_status"]:
                entry["machine_audit_status"].add(candidate["machine_audit_status"])
        for measurement_id in sorted(merged):
            entry = merged[measurement_id]
            cand_rows.append({
                "a_mol_id": owner["a_mol_id"],
                "a_name": owner["a_name"],
                "measurement_id": measurement_id,
                "layers": joined(entry["layers"]),
                "epsilon": entry["epsilon"],
                "T_K": entry["T_K"],
                "declared_band": entry["band"],
                "source_group": entry["source_group"],
                "decision": joined(entry["decision"]) or NOT_EVALUATED,
                "evidence_group_id": entry["evidence_group_id"],
                "failed_gates": joined(entry["failed_gates"]),
                "human_audit_status": joined(entry["human_audit_status"]),
                "machine_audit_status": joined(entry["machine_audit_status"]),
            })
    cand_rows.sort(key=lambda r: (r["a_mol_id"], r["measurement_id"]))

    criteria = build_criteria_snapshot(protocol=dataset["protocol"], k_rule=dataset["k_rule"], windows=windows)
    criteria_bytes = render_json(criteria)
    criteria_sha = sha256_bytes(criteria_bytes)

    gates = build_gate_table(eligibility_rows)
    inputs_sha = {entry["id"]: entry["sha256"] for entry in inputs_manifest["inputs"]}
    go_nogo = build_go_nogo(
        eligibility_rows,
        protocol=dataset["protocol"],
        k_rule=dataset["k_rule"],
        gates=gates,
        criteria_sha256=criteria_sha,
        inputs_sha256=inputs_sha,
        environment=environment,
        v56_manifest=dataset["v56_manifest"],
    )

    # 快照固化: 输入未变而数变了 => 说明有东西被静默替换
    actual_snapshot = {
        "n_a_core_neutral_parents": go_nogo["denominators"]["n_a_core_neutral_parents"],
        "n_identity_common_in_candidate_master": go_nogo["denominators"]["n_identity_common_in_candidate_master"],
        "n_condition_resolvable": go_nogo["denominators"]["n_condition_resolvable"],
        "n_room_band_qualified": go_nogo["denominators"]["n_room_band_qualified"],
        "n_admitted": go_nogo["denominators"]["n_admitted"],
        "off_room_band_condition_resolvable": sorted(
            entry["mol_id"] for entry in go_nogo["snapshot"]["off_room_band_condition_resolvable"]
        ),
    }
    assert_snapshot(actual_snapshot, EXPECTED_SNAPSHOT)

    a18_skeletons = {r["a_inchikey_skeleton"] for r in eligibility_rows}
    layer_summary = build_layer_summary(dataset, layers, a18_skeletons)
    priority_table = [
        {
            "priority_order": row["backfill_order"],
            "a_mol_id": row["a_mol_id"],
            "a_name": row["a_name"],
            "backfill_tier": row["backfill_tier"],
            "backfill_action": row["backfill_action"],
            "eligibility_verdict": row["eligibility_verdict"],
            "v11_n_observations": row["v11_n_observations"],
            "v11_n_room_band": row["v11_n_room_band"],
            "frequency_status": row["frequency_status"],
            "independent_source_status": row["independent_source_status"],
            "backfill_target_source": row["backfill_target_source"],
            "current_blocker": joined(row["eligibility_reason_codes"].split(";")),
        }
        for row in priority_rows
    ]

    report = render_report(
        rows=eligibility_rows,
        go_nogo=go_nogo,
        layer_summary=layer_summary,
        inputs_manifest=inputs_manifest,
        priority_rows=priority_table,
    )

    files: dict[str, bytes] = {
        "joint_inputs_manifest.json": render_json(inputs_manifest),
        "joint_pool_layer_summary.json": render_json(layer_summary),
        "joint_eligibility.csv": render_csv(ELIGIBILITY_COLUMNS, eligibility_rows),
        "joint_v11_observation_rows.csv": render_csv(OBSERVATION_COLUMNS, obs_rows),
        "joint_candidate_measurement_rows.csv": render_csv(CANDIDATE_COLUMNS, cand_rows),
        "a18_source_backfill_priority.csv": render_csv(PRIORITY_COLUMNS, priority_table),
        "joint_eligibility_criteria.json": criteria_bytes,
        "joint_go_nogo.json": render_json(go_nogo),
        "joint_eligibility_report.md": report,
    }
    receipt = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "excludes": ["wall-clock timestamps", "random seeds", "filesystem ordering"],
        "rebuild_command": "python scripts/confirm_2027/build_joint_eligibility.py --check",
        "output_sha256": {name: sha256_bytes(payload) for name, payload in sorted(files.items())},
        "output_bytes": {name: len(payload) for name, payload in sorted(files.items())},
        "criteria_sha256": criteria_sha,
        "environment": dict(sorted(environment.items())),
    }
    files["joint_rebuild_receipt.json"] = render_json(receipt)
    missing = [name for name in OUTPUT_FILES if name not in files]
    if missing:
        raise JointEligibilityError(f"输出清单未产全: {missing}")
    return files


def assert_snapshot(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """快照不一致即拒绝出数 (输入被换但契约版本未升)."""
    problems = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            problems.append(f"{key}: expected {expected_value!r}, actual {actual_value!r}")
    if problems:
        raise SnapshotMismatch(
            "固化快照不一致 (输入数据可能已被替换): " + "; ".join(problems)
            + f" —— 若确属新证据, 请升 {INPUT_CONTRACT_VERSION} 与 CONTRACT_VERSION 并更新 EXPECTED_SNAPSHOT"
        )


# ---------------------------------------------------------------------------
# 输入清单
# ---------------------------------------------------------------------------

INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 个中性母体 (只读连接对象)",
    "b_dielectric_v04": "B 仓 248 行介电主表 (审计基准)",
    "b_observations_v11plus": "B 仓 v11 逐条观测层 (T/相态/频率/压强/来源)",
    "v56_candidate_master": "v56 248 行候选主表 (含 in_49_preview 标记)",
    "v56_candidate_pool_c": "v56 池 C 49 行 (逐行 epsilon/evidence_group_id/decision_v2)",
    "v56_candidate_pool_b": "v56 高置信池 24 行",
    "v56_human_audit_worksheet": "v56 40 行机器审计/人类签批工作表",
    "v56_admission_gap": "v56 248 行 admission 缺口表 (measurement_decision)",
    "v56_formal_decision_draft": "v56 20 行 A1..A12 逐门草案",
    "v56_target_protocol": "v56 冻结协议 (门定义/温窗/never-default 规则)",
    "v56_primary_k_adoption": "v56 primary_k 采用声明 (FROZEN)",
    "v56_manifest": "v56 独立包版本记录 (逐文件 sha256 账本)",
    "v56_round_r007": "v56 Round R007 记录 (纠正/缺口/人类审计状态)",
    "v56_three_questions_r001": "v56 三问结论 (ACCEPT=0 的权威陈述)",
}


def git_provenance(repo: Path) -> dict[str, Any]:
    """读取 git HEAD / tag / 已跟踪文件改动数; 失败返回 not_evaluated 而不是猜.

    只统计已跟踪文件的改动 (`--untracked-files=no`): 本分析自己产生的 outputs/ 与
    脚本本来就是新文件, 把它们算进"脏树"会让同一份输入每次重建得出不同回执.
    """
    import subprocess

    def run(args: list[str]) -> str:
        try:
            completed = subprocess.run(
                args, cwd=str(repo), capture_output=True, text=True, check=False, timeout=30
            )
        except Exception:
            return "not_evaluated"
        if completed.returncode != 0:
            return "not_evaluated"
        return completed.stdout.strip()

    head = run(["git", "rev-parse", "HEAD"])
    tag = run(["git", "rev-parse", "v1.3^{commit}"])
    status = run(["git", "status", "--porcelain", "--untracked-files=no"])
    tracked = len([line for line in status.splitlines() if line.strip()]) if status != "not_evaluated" else -1
    ahead = run(["git", "rev-list", "--count", "origin/main..HEAD"])
    return {
        "path": str(repo),
        "head": head,
        "tag_v1_3_commit": tag,
        "tracked_modifications": tracked,
        "commits_ahead_of_origin_main": ahead,
    }


def build_inputs_manifest(
    paths: Mapping[str, Path],
    *,
    workspace: Path,
    a_repo_present: bool,
    environment: Mapping[str, str],
    v56_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = []
    for name in sorted(paths):
        path = Path(paths[name])
        present = path.is_file()
        inputs.append({
            "id": name,
            "role": INPUT_ROLES.get(name, ""),
            "path": str(path.relative_to(workspace)) if present and workspace in path.parents else str(path),
            "bytes": path.stat().st_size if present else 0,
            "sha256": sha256_file(path) if present else "FILE_MISSING",
            "in_v56_manifest": name not in {"a_core_set", "b_dielectric_v04", "b_observations_v11plus"},
        })
    v56_manifest_files = {
        str(entry.get("dest", "")) for entry in v56_manifest.get("files", [])
    } if isinstance(v56_manifest.get("files"), list) else set()
    r007_covered = any(dest.endswith("reports/ROUND_R007.md") for dest in v56_manifest_files)
    return {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "join_unit": A_JOIN_UNIT,
        "provenance": {
            "b_repo": git_provenance(workspace / "电解质ML"),
            "v56": {
                "path": str(workspace / "v56_standalone"),
                "project": v56_manifest.get("project"),
                "generated_by": v56_manifest.get("generated_by"),
                "schema": v56_manifest.get("schema"),
                "counts": v56_manifest.get("counts"),
            },
            "a_repo": {
                "present": a_repo_present,
                "note": "只读取 data/metadata/core_set.csv; 不读 A 的任何计算产物",
            },
        },
        "v56_manifest_sha256": sha256_file(paths["v56_manifest"]),
        "v56_manifest_coverage": {
            "n_files_in_manifest": len(v56_manifest_files),
            "r007_artifacts_covered": r007_covered,
            "note": (
                "MANIFEST 生成于 2026-11-19, R001-R006 之外的 R007 产物可能未入账; "
                "未入账时以本文件记录的逐输入 SHA256 为准"
            ),
        },
        "inputs": inputs,
        "environment": dict(sorted(environment.items())),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def write_outputs(out_dir: Path, files: Mapping[str, bytes]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (out_dir / name).write_bytes(files[name])


def check_outputs(out_dir: Path, files: Mapping[str, bytes]) -> list[str]:
    """逐字节比较现有产物与重建结果; 返回差异清单."""
    problems: list[str] = []
    out_dir = Path(out_dir)
    for name in sorted(files):
        target = out_dir / name
        if not target.is_file():
            problems.append(f"缺失: {name}")
            continue
        if target.read_bytes() != files[name]:
            problems.append(f"不一致: {name}")
    for name in OUTPUT_FILES:
        if name not in files and (out_dir / name).is_file():
            problems.append(f"多余: {name}")
    return problems


def run(
    *,
    workspace: Path,
    a_repo: Path | None,
    out_dir: Path,
    check: bool,
    pins: Mapping[str, str] = PINNED_INPUT_SHA256,
) -> int:
    paths = locate_inputs(workspace, a_repo)
    drift = verify_pinned_inputs(paths, pins)
    if drift:
        print("输入 SHA256 漂移 (拒绝出数):", file=sys.stderr)
        for item in drift:
            print(f"  {item['input']}: expected {item['expected'][:16]} actual {item['actual'][:16]}"
                  f" ({item.get('path', '')})", file=sys.stderr)
        return 3
    missing = [name for name, path in paths.items() if not Path(path).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2

    dataset = load_dataset(paths)
    integrity = [
        check_gap_v04_mapping(dataset["gap"], dataset["v04"]),
        *check_mirror_equality(paths, workspace),
        *check_pool_layer_disagreement(dataset),
    ]
    environment = collect_environment()
    inputs_manifest = build_inputs_manifest(
        paths,
        workspace=workspace,
        a_repo_present=Path(paths["a_core_set"]).is_file(),
        environment=environment,
        v56_manifest=dataset["v56_manifest"],
    )
    inputs_manifest["integrity_checks"] = integrity
    inputs_manifest["drift"] = []

    try:
        files = build_outputs(dataset, inputs_manifest=inputs_manifest, environment=environment)
    except SnapshotMismatch as error:
        print(str(error), file=sys.stderr)
        return 4

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
    go_nogo = json.loads(files["joint_go_nogo.json"].decode("utf-8"))
    print(f"{ANALYSIS_ID} 完成 -> {out_dir}")
    print(f"  verdict: {go_nogo['verdict']}")
    for key in (
        "n_identity_common_in_candidate_master",
        "n_condition_resolvable",
        "n_room_band_qualified",
        "n_admitted",
    ):
        print(f"  {key}: {go_nogo['denominators'][key]}")
    print(f"  输出 {len(files)} 个文件")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    workspace_default = default_workspace()
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=workspace_default,
                        help="工作区根 (含 电解质ML/ 与 v56_standalone/)")
    parser.add_argument("--a-repo", type=Path, default=None, help="A 仓 电解液溶剂HB-Code 路径")
    parser.add_argument("--out", type=Path, default=None,
                        help="输出目录 (默认 <B 仓>/outputs/confirm_2027/intersections)")
    parser.add_argument("--check", action="store_true", help="只重建并比较, 不写盘")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    out_dir = args.out or (workspace / "电解质ML" / "outputs" / "confirm_2027" / "intersections")
    return run(workspace=workspace, a_repo=args.a_repo, out_dir=out_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
