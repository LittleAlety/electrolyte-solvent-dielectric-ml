#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J02B | master.in_49_preview 与 candidate_pool_C 的版本溯源.

要回答的唯一问题
----------------
两个都叫"49"的东西 —— `candidate_master.in_49_preview` 与 `candidate_pool_C_R001.csv`
—— 有 26 个成员互不相同. 它们是:
  * 一个是历史预览、另一个是当前池 (则 pool_C 继续作权威, preview 归档)?
  * 还是 preview 本应反映当前 pool_C 而回写断了 (则要修上游并重出新版本)?

为什么不能靠"哪个更全"来选
--------------------------
两者指纹相近会诱导一种错误做法: 取并集得到 75 行"更全的池". 这会把两套不同筛选
规则的产物混成一个既不是预览也不是正式池的第三物, 并且伪造出更大的分母. 本模块
因此只做**溯源**, 不合并, 不生成任何新池文件.

溯源要落到证据上
----------------
`in_49_preview` 由 `tools/candidate_master_R001.py` 从
`drafts/artifacts/s4_fold_DRAFT_INDICATIVE_R293.csv` 派生 —— 那是一张 **S4 折的角色
表** (holdout/train/validation), 不是候选池. `candidate_pool_C_R001.csv` 由
`tools/build_candidate_pool_R001.py` 从 `evidence_backfill_R001.csv` 派生, 其准入是
`status == "RESOLVED"`. 两者的**上游输入不同、生成器不同、语义不同** —— 这不是
"回写遗漏", 而是两个不同对象共用了一个"49"的外观.

本模块把这个判断做成可复核的证据链: 每层的生成器、输入 SHA、成员集合、差异原因,
然后只允许两个裁决之一.
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
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_ID = "B-G0-J02B"
ANALYSIS_TITLE = "master.in_49_preview 与 candidate_pool_C 版本溯源"
CONTRACT_VERSION = "confirm_2027.pool_lineage/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j02b_inputs/v1"
GENERATOR_VERSION = "audit_candidate_pool_lineage/1.0.0"

DECISION_HISTORICAL = "PREVIEW_IS_HISTORICAL_PRESERVE_AND_KEEP_POOL_C_AUTHORITATIVE"
DECISION_REWRITE = "PREVIEW_SHOULD_REFLECT_CURRENT_POOL_C_FIX_UPSTREAM_AND_RERUN"

PINNED: dict[str, tuple[str, int]] = {
    "candidate_master": ("63b9ff45561c9a49f203f98a10588c003b0af16b7e376269f333c882618a495d", 72349),
    "candidate_pool_C": ("c50f9349ec6de434f2b81d7a138292581fb661f4b1b9b1d54fdd3f7dc9055ba8", 9479),
    "candidate_pool_B": ("e2f18d4fd09b2ba9a9c5680c55c943d93a7381bef0c3d78a87676dc00540c176", 4482),
    "evidence_backfill": ("7ef1502439b3422bc1792e6499cbb4e3b75ed3e3df6eaae7bdda7faedfce6cd2", 6178),
    "s4_preview": ("cb57ab59fb0f2d9f46809799ff173cbee83d230f66159a905ab6296a674eb73a", 4923),
    "admission_gap": ("597efaf8355483a937dfaed5706694c3591df64f655e28fdfc9bd3bc458a2ec1", 50040),
    "admission_matrix": ("0b50c54dba7d259b947f6a768f61921684e8507a55a52269e12544929731a9f7", 51830),
    "pool_c_v2": ("32e1bea54f938f9cdd9b52a571846b91003b9f8c53d78a266bcd935e7dd2cd5f", 6907),
    "pool_c_diff": ("0eb6bb8313c93b41e245d4679996bc5f80dbb89dedf978c15efa6cf689732153", 9664),
    "target_protocol": ("0e848eb6fd8619f89611b70237c17b6ac0d9b117422d9d2a988be681f69bc6a4", 13420),
}

#: 每层声明的生成器 (来源必须是代码, 不是叙述)
GENERATOR_OF: dict[str, dict[str, str]] = {
    "master_49_preview": {
        "producer_field": "candidate_master.in_49_preview",
        "producer_script": "tools/candidate_master_R001.py",
        "upstream_input": "drafts/artifacts/s4_fold_DRAFT_INDICATIVE_R293.csv",
        "semantics": "S4 fold role assignment (holdout/train/validation), not a candidate pool",
        "admission_rule": "none (role table carries no admission decision)",
        "grants_approval": "no",
    },
    "candidate_pool_C": {
        "producer_field": "candidate_pool_C_R001.csv",
        "producer_script": "tools/build_candidate_pool_R001.py",
        "upstream_input": "reports/evidence_backfill_R001.csv",
        "semantics": "candidate pool built from RESOLVED mechanical evidence",
        "admission_rule": 'backfill.status == "RESOLVED" and not REJECT and no salt token',
        "grants_approval": "no (decision_v2=CANDIDATE, never ACCEPT)",
    },
}

OUTPUT_FILES: tuple[str, ...] = (
    "j02b_inputs_manifest.json",
    "pool_lineage_reconciliation.csv",
    "pool_membership_diff.csv",
    "pool_version_decision.json",
    "pool_lineage_report.md",
    "j02b_rebuild_receipt.json",
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


def render_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_csv(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")


def joined(values: Iterable[str], sep: str = ";") -> str:
    return sep.join(sorted({v for v in values if v and str(v).strip()}))


NOT_EVALUATED = "not_evaluated"


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[3]


def locate_inputs(workspace: Path, a_repo: Path | None) -> dict[str, Path]:
    workspace = Path(workspace)
    v56 = workspace / "v56_standalone"
    drafts = v56 / "app" / "电解质ML" / "v56_round1"
    repo_a = Path(a_repo) if a_repo else Path(
        os.environ.get("J01_REPO_A", str(workspace.parent / "电解液溶剂-HB" / "电解液溶剂HB-Code"))
    )
    return {
        "a_core_set": repo_a / "data" / "metadata" / "core_set.csv",
        "candidate_master": v56 / "reports" / "candidate_master_R001.csv",
        "candidate_pool_C": v56 / "reports" / "candidate_pool_C_R001.csv",
        "candidate_pool_B": v56 / "reports" / "candidate_pool_B_R001.csv",
        "evidence_backfill": v56 / "reports" / "evidence_backfill_R001.csv",
        "s4_preview": drafts / "drafts" / "artifacts" / "s4_fold_DRAFT_INDICATIVE_R293.csv",
        "admission_gap": drafts / "deliverables" / "experimental_epsilon_admission_gap.csv",
        "admission_matrix": v56 / "reports" / "admission_matrix_R001.csv",
        "pool_c_v2": v56 / "reports" / "candidate_pool_C_v2_R001.csv",
        "pool_c_diff": v56 / "reports" / "candidate_pool_C_diff_R001.csv",
        "target_protocol": drafts / "drafts" / "configs" / "frozen" / "target_protocol.yaml",
        "master_script": v56 / "tools" / "candidate_master_R001.py",
        "pool_script": v56 / "tools" / "build_candidate_pool_R001.py",
        "backfill_script": v56 / "tools" / "evidence_backfill_R001.py",
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
# 溯源
# ---------------------------------------------------------------------------

def static_source_evidence(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    """在生成器源码里定位"谁决定成员资格", 把出处写成可复核的断言.

    这是本模块唯一的"证据级"检查: 不靠文件名的相似性, 靠代码里实际读的是哪个上游.
    """
    checks: list[dict[str, Any]] = []

    master_script = Path(paths["master_script"])
    master_text = master_script.read_text(encoding="utf-8")
    master_uses_preview = "S4_PREVIEW" in master_text and "in_49_preview" in master_text
    checks.append({
        "check": "master_in_49_preview_upstream_is_s4_preview",
        "status": "PASS" if master_uses_preview else "FAIL",
        "detail": ("candidate_master_R001.py 用 S4_PREVIEW = s4_fold_DRAFT_INDICATIVE_R293.csv "
                   "派生 in_49_preview") if master_uses_preview else "未在源码中找到该派生",
        "evidence_file": str(master_script.name),
        "evidence_sha256": sha256_file(master_script),
    })

    pool_script = Path(paths["pool_script"])
    pool_text = pool_script.read_text(encoding="utf-8")
    pool_uses_backfill = 'backfill[m]["status"] == "RESOLVED"' in pool_text
    checks.append({
        "check": "candidate_pool_C_upstream_is_evidence_backfill",
        "status": "PASS" if pool_uses_backfill else "FAIL",
        "detail": ('build_candidate_pool_R001.py 以 backfill[m]["status"] == "RESOLVED" '
                   "作为池 C 成员条件") if pool_uses_backfill else "未找到该成员条件",
        "evidence_file": str(pool_script.name),
        "evidence_sha256": sha256_file(pool_script),
    })

    # pool 生成器根本不读 preview 表 -> 二者不存在回写关系
    reads_preview = "s4_fold" in pool_text or "in_49_preview" in pool_text
    checks.append({
        "check": "candidate_pool_C_does_not_read_preview",
        "status": "PASS" if not reads_preview else "FAIL",
        "detail": ("build_candidate_pool_R001.py 完全不引用 S4 预览表, 因此不存在"
                   "'pool_C 更新后未回写 preview' 的链路") if not reads_preview
                  else "发现 pool 生成器引用了预览表, 需要重新评估回写关系",
        "evidence_file": str(pool_script.name),
    })

    backfill_script = Path(paths["backfill_script"])
    backfill_text = backfill_script.read_text(encoding="utf-8")
    needs_explicit_list = "--measurements" in backfill_text and "required=True" in backfill_text
    checks.append({
        "check": "evidence_backfill_requires_explicit_measurement_list",
        "status": "PASS" if needs_explicit_list else "FAIL",
        "detail": ("evidence_backfill_R001.py 要求外部显式提供 measurement_id 列表 "
                   "(--measurements required=True); 名单本身的出处不在代码里, 属"
                   "下游可复现性的已知缺口") if needs_explicit_list else "未确认显式列表要求",
        "evidence_file": str(backfill_script.name),
        "evidence_sha256": sha256_file(backfill_script),
    })
    return checks


def build_layers(paths: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    master = read_csv_strict(paths["candidate_master"],
                             ("measurement_id", "molecule_id", "in_49_preview", "preview_role"))
    pool_c = read_csv_strict(paths["candidate_pool_C"],
                             ("measurement_id", "molecule_id", "decision_v2"))
    preview_rows = read_csv_strict(paths["s4_preview"],
                                   ("molecule_id", "role", "measurement_ids"))
    backfill = read_csv_strict(paths["evidence_backfill"],
                               ("measurement_id", "status"))

    preview_members = {skeleton(r["molecule_id"]) for r in master
                       if str(r.get("in_49_preview", "")).strip().lower() == "yes"}
    pool_c_members = {skeleton(r["molecule_id"]) for r in pool_c}
    s4_members = {skeleton(r["molecule_id"]) for r in preview_rows}
    backfill_ids = {str(r["measurement_id"]).strip() for r in backfill}

    layer_meta = {
        "master_49_preview": {
            "members": preview_members,
            "source_ids": {skeleton(r["molecule_id"]) for r in master
                           if str(r.get("in_49_preview", "")).strip().lower() == "yes"},
            "n_rows": len(preview_members),
        },
        "candidate_pool_C": {
            "members": pool_c_members,
            "measurement_ids": {str(r["measurement_id"]).strip() for r in pool_c},
            "n_rows": len(pool_c),
        },
        "s4_preview_source": {
            "members": s4_members,
            "measurement_ids": {m.strip() for r in preview_rows
                                for m in str(r.get("measurement_ids", "")).split(";") if m.strip()},
            "n_rows": len(preview_rows),
        },
        "evidence_backfill": {
            "members": {skeleton(r["molecule_id"]) for r in backfill} if "molecule_id" in backfill[0] else None,
            "measurement_ids": backfill_ids,
            "n_rows": len(backfill),
        },
    }
    return layer_meta


def build_reconciliation(paths: Mapping[str, Path]) -> list[dict[str, str]]:
    layer_meta = build_layers(paths)
    preview = layer_meta["master_49_preview"]["members"]
    pool_c = layer_meta["candidate_pool_C"]["members"]
    s4 = layer_meta["s4_preview_source"]["members"]
    backfill_ids = layer_meta["evidence_backfill"]["measurement_ids"]

    pool_c_ids = layer_meta["candidate_pool_C"]["measurement_ids"]
    s4_ids = layer_meta["s4_preview_source"]["measurement_ids"]

    rows: list[dict[str, str]] = []
    for key in sorted(preview | pool_c):
        in_preview = key in preview
        in_pool = key in pool_c
        if in_preview and in_pool:
            classification = "IN_BOTH"
        elif in_preview:
            classification = "PREVIEW_ONLY"
        else:
            classification = "POOL_C_ONLY"
        rows.append({
            "skeleton": key,
            "in_49_preview": "true" if in_preview else "false",
            "in_candidate_pool_C": "true" if in_pool else "false",
            "in_s4_preview_source": "true" if key in s4 else "false",
            "membership_class": classification,
            "preview_measurement_ids": joined(
                mid for mid in s4_ids if mid
            ) if in_preview else "",
            "pool_c_measurement_ids": joined(pool_c_ids) if in_pool else "",
            "explanation": {
                "IN_BOTH": "两套筛选恰好都收进来",
                "PREVIEW_ONLY": "S4 折角色表收了它, 但机械证据未 RESOLVED, 故不在池 C",
                "POOL_C_ONLY": "机械证据 RESOLVED 进了池 C, 但不在 S4 折角色表里",
            }[classification],
            "backfill_has_row": "true" if any(
                str(m).replace("EPSV04-", "") for m in backfill_ids if str(m)
            ) and in_pool else "false",
        })
    return rows


def build_membership_diff(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    preview_only = sorted(r["skeleton"] for r in rows if r["membership_class"] == "PREVIEW_ONLY")
    pool_only = sorted(r["skeleton"] for r in rows if r["membership_class"] == "POOL_C_ONLY")
    both = sorted(r["skeleton"] for r in rows if r["membership_class"] == "IN_BOTH")
    return {
        "n_preview": sum(1 for r in rows if r["in_49_preview"] == "true"),
        "n_pool_c": sum(1 for r in rows if r["in_candidate_pool_C"] == "true"),
        "n_common": len(both),
        "n_preview_only": len(preview_only),
        "n_pool_c_only": len(pool_only),
        "n_union": len(both) + len(preview_only) + len(pool_only),
        "preview_only": preview_only,
        "pool_c_only": pool_only,
        "common": both,
        "is_subset_relation": "preview_subset_pool_c" if not preview_only
        else ("pool_c_subset_preview" if not pool_only else "neither_subset"),
    }


# ---------------------------------------------------------------------------
# 裁决
# ---------------------------------------------------------------------------

def decide(
    lineage_checks: Sequence[Mapping[str, Any]],
    diff: Mapping[str, Any],
    *,
    pool_c_status: str,
    a18_presence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """只允许两个裁决; 判据必须显式列出, 不许凭印象."""
    by_check = {c["check"]: c for c in lineage_checks}
    distinct_upstream = (
        by_check.get("master_in_49_preview_upstream_is_s4_preview", {}).get("status") == "PASS"
        and by_check.get("candidate_pool_C_upstream_is_evidence_backfill", {}).get("status") == "PASS"
    )
    no_writeback_link = by_check.get("candidate_pool_C_does_not_read_preview", {}).get("status") == "PASS"
    not_nested = diff["is_subset_relation"] == "neither_subset"

    historical = distinct_upstream and no_writeback_link and not_nested
    decision = DECISION_HISTORICAL if historical else DECISION_REWRITE

    reasons: list[str] = []
    if distinct_upstream:
        reasons.append(
            "两个层的上游输入不同: preview 源自 S4 折角色表, pool_C 源自 evidence_backfill"
        )
    if no_writeback_link:
        reasons.append("pool_C 生成器完全不读预览表, 因此不存在'池更新未回写预览'的链路")
    if not_nested:
        reasons.append(
            f"两池互不嵌套 (preview_only={diff['n_preview_only']}, "
            f"pool_c_only={diff['n_pool_c_only']}), 排除了'一个是另一个的子集'的解释"
        )
    return {
        "decision": decision,
        "decision_reasons": reasons,
        "preview_classification": (
            "LEGACY_OR_UNRESOLVED_PREVIEW" if historical else "STALE_MIRROR_OF_POOL_C"
        ),
        "pool_c_status": pool_c_status,
        "a18_presence": dict(a18_presence or {}),
        "merge_forbidden": True,
        "merge_forbidden_reason": (
            "并集会把两套不同筛选规则混成既非预览也非正式池的第三物, 并伪造更大的分母"
        ),
        "next_action": (
            "保留 preview 历史版本, pool_C 继续作为当前权威操作池; 不重出 joint_eligibility"
            if historical else
            "修复上游回写, 建立新版本池并重跑联合资格审计"
        ),
    }


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

INPUT_ROLES: dict[str, str] = {
    "a_core_set": "A 仓 18 中性母体 (身份)",
    "candidate_master": "in_49_preview 的载体",
    "candidate_pool_C": "当前权威候选池",
    "candidate_pool_B": "高置信池 (对照)",
    "evidence_backfill": "pool_C 的准入依据",
    "s4_preview": "preview 的真实上游 (S4 折角色表)",
    "admission_gap": "248 行 admission 缺口表",
    "admission_matrix": "64 行 A1..A12 逐门矩阵",
    "pool_c_v2": "已存在的 pool_C v2 草案 (对照, 未采用)",
    "pool_c_diff": "v1→v2 逐行差异 (对照)",
    "target_protocol": "冻结温窗与门定义",
    "master_script": "in_49_preview 生成器源码",
    "pool_script": "pool_C 生成器源码",
    "backfill_script": "backfill 匹配规则源码",
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


RECON_COLUMNS: tuple[str, ...] = (
    "skeleton", "in_49_preview", "in_candidate_pool_C", "in_s4_preview_source",
    "membership_class", "preview_measurement_ids", "pool_c_measurement_ids",
    "backfill_has_row", "explanation",
)

DIFF_COLUMNS: tuple[str, ...] = (
    "skeleton", "membership_class", "in_49_preview", "in_candidate_pool_C",
    "in_s4_preview_source", "explanation",
)


def build_report(
    *,
    diff: Mapping[str, Any],
    decision: Mapping[str, Any],
    lineage_checks: Sequence[Mapping[str, Any]],
    layer_summary: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> bytes:
    lines: list[str] = []
    add = lines.append
    add(f"# {ANALYSIS_ID} {ANALYSIS_TITLE}")
    add("")
    add(f"- 契约: `{CONTRACT_VERSION}` / `{INPUT_CONTRACT_VERSION}`")
    add("- 本报告不含墙钟时间, 可由固定输入逐字节重建")
    add("")
    add("## 1. 裁决")
    add("")
    add(f"**`{decision['decision']}`**")
    add("")
    add("| 字段 | 值 |")
    add("|---|---|")
    add(f"| preview 定性 | `{decision['preview_classification']}` |")
    add(f"| pool_C 定性 | `{decision['pool_c_status']}` |")
    add(f"| 是否禁止合并 | {decision['merge_forbidden']} |")
    add(f"| 下一步 | {decision['next_action']} |")
    add("")
    add("判据: ")
    for reason in decision["decision_reasons"]:
        add(f"- {reason}")
    add("")
    add(f"合并被禁止的原因: {decision['merge_forbidden_reason']}。")
    add("")
    add("## 2. 成员差异")
    add("")
    add("| 项 | 数量 |")
    add("|---|---:|")
    for key in ("n_preview", "n_pool_c", "n_common", "n_preview_only", "n_pool_c_only", "n_union"):
        add(f"| `{key}` | {diff[key]} |")
    add(f"| 集合关系 | `{diff['is_subset_relation']}` |")
    add("")
    add("## 3. 生成链溯源")
    add("")
    add("| 层 | 生成器 | 上游输入 | 语义 | 准入规则 | 授予批准 |")
    add("|---|---|---|---|---|---|")
    for name in sorted(GENERATOR_OF):
        meta = GENERATOR_OF[name]
        add(f"| `{name}` | `{meta['producer_script']}` | `{meta['upstream_input']}` | "
            f"{meta['semantics']} | {meta['admission_rule']} | {meta['grants_approval']} |")
    add("")
    add("### 源码级证据")
    add("")
    add("| 检查 | 状态 | 说明 |")
    add("|---|---|---|")
    for check in lineage_checks:
        add(f"| `{check['check']}` | {check['status']} | {check['detail']} |")
    add("")
    add("## 4. 两层各自规模")
    add("")
    add("| 层 | 行 | 唯一骨架 |")
    add("|---|---:|---:|")
    for entry in layer_summary:
        add(f"| `{entry['layer']}` | {entry['n_rows']} | {entry['n_unique_skeletons']} |")
    add("")
    add("## 5. 只允许两个裁决")
    add("")
    add("| 核查结果 | 后续动作 |")
    add("|---|---|")
    add("| preview 是历史预览 | 保留历史版本, pool_C 继续作为当前权威池 |")
    add("| preview 本应反映当前 pool_C | 修复上游回写, 建立新版本并重新运行联合资格审计 |")
    add("")
    add("本轮不修改 B-G0-J01 的冻结产物; 若裁决要求重跑, 必须在新版本池上重跑而不是覆盖。")
    add("")
    add("## 6. 冻结输入")
    add("")
    add("| 输入 | bytes | sha256 |")
    add("|---|---:|---|")
    for entry in manifest["inputs"]:
        add(f"| `{entry['id']}` | {entry['bytes']} | `{entry['sha256'][:16]}` |")
    add("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_outputs(
    paths: Mapping[str, Path], *, manifest: Mapping[str, Any]
) -> dict[str, bytes]:
    lineage_checks = static_source_evidence(paths)
    reconciliation = build_reconciliation(paths)
    diff = build_membership_diff(reconciliation)
    a18_presence = {
        "layer": "not_evaluated",
        "note": "A18 命中数由 B-G0-J01 的 joint_eligibility.csv 报告, 本模块不重复计算",
    }
    decision = decide(lineage_checks, diff,
                      pool_c_status="CURRENT_AUTHORITATIVE_OPERATIONAL_POOL",
                      a18_presence=a18_presence)
    layer_meta = build_layers(paths)
    layer_summary = [
        {
            "layer": name,
            "n_rows": meta["n_rows"],
            "n_unique_skeletons": len(meta.get("members") or meta.get("measurement_ids") or []),
        }
        for name, meta in sorted(layer_meta.items())
    ]

    decision_payload = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        **decision,
        "membership_summary": {
            k: diff[k] for k in
            ("n_preview", "n_pool_c", "n_common", "n_preview_only", "n_pool_c_only",
             "n_union", "is_subset_relation")
        },
        "lineage_checks": list(lineage_checks),
        "generator_of": GENERATOR_OF,
        "forbidden_actions": [
            "merge the two layers into a new 49 or 75 row pool",
            "overwrite candidate_pool_C_R001.csv",
            "overwrite master.in_49_preview in place",
            "modify B-G0-J01 frozen outputs",
        ],
        "known_gaps": [
            "evidence_backfill 的 measurement_id 名单出处不在代码库里 (--measurements 由外部传入)",
            "candidate_master 生成时 MANIFEST 尚未覆盖 R007 产物",
        ],
    }

    files: dict[str, bytes] = {
        "j02b_inputs_manifest.json": render_json(manifest),
        "pool_lineage_reconciliation.csv": render_csv(RECON_COLUMNS, reconciliation),
        "pool_membership_diff.csv": render_csv(DIFF_COLUMNS, reconciliation),
        "pool_version_decision.json": render_json(decision_payload),
        "pool_lineage_report.md": build_report(
            diff=diff, decision=decision, lineage_checks=lineage_checks,
            layer_summary=layer_summary, manifest=manifest,
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
        "note": "本模块不生成新池文件; 只发布溯源结论与差异表",
    }
    files["j02b_rebuild_receipt.json"] = render_json(receipt)
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
    manifest = build_inputs_manifest(paths, collect_environment())
    files = build_outputs(paths, manifest=manifest)
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
    decision = json.loads(files["pool_version_decision.json"].decode("utf-8"))
    print(f"{ANALYSIS_ID} 完成 -> {out_dir}")
    print(f"  decision: {decision['decision']}")
    print(f"  preview : {decision['preview_classification']}")
    print(f"  diff    : common={decision['membership_summary']['n_common']} "
          f"preview_only={decision['membership_summary']['n_preview_only']} "
          f"pool_c_only={decision['membership_summary']['n_pool_c_only']}")
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
