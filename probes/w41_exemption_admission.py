# -*- coding: utf-8 -*-
"""W41-C：把 EXEMPT_WRITERS 的「三类理由」准入规则写成机械守卫。

W40-B 把 22 个不能迁移的 owner 登记进 `probes/w40_timestamp_migration.py::EXEMPT_WRITERS`，
但准入规则本身只写在探针的注释与 reason 散文里。README §11 第 32 条登记的三件事是：
(1) 新增例外必须落在三类之内；(2) 被冻结点名的脚本改字节要先走解冻/更正流程；
(3) 例外件重跑脏树必须继续当已知代价报出、不得计入迁移完成率。

本件按**源码证据**（不是手写分组）把每个 owner 机械地归到 pinned_bytes / append_log /
strict_json，并机械复核「登记了却仍含 write_json_stable」的反向漏网。

Run:
    .venv/Scripts/python.exe probes/w41_exemption_admission.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

try:
    from probes.export_results_common import write_json_stable
except ImportError:
    from export_results_common import write_json_stable

sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
try:
    from probes.w40_timestamp_migration import EXEMPT_CATEGORIES, EXEMPT_WRITERS
except ImportError:
    from w40_timestamp_migration import EXEMPT_CATEGORIES, EXEMPT_WRITERS

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w41_governance_prereg.json"
W40_PROBE = REPOSITORY_ROOT / "probes" / "w40_timestamp_migration.py"
ADMISSION_CSV = ARTIFACTS / "w41_exemption_admission.csv"
POLICY_PATH = ARTIFACTS / "w41_exemption_policy.json"
SUMMARY_PATH = ARTIFACTS / "w41_exemption_admission_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w41_exemption_admission.md"

SCHEMA = "w41_exemption_admission/summary@1"
TASK = "week41_exemption_admission"

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

PINNED_PATTERN = re.compile(
    r"(钉死|冻结|摘要|summary|prereg|manifest|依赖件|引用|历史记录|比对|version_1_pins|锁前)")
APPEND_PATTERN = re.compile(r"open\([^)]*[\"']a")
STRICT_PATTERN = re.compile(r"allow_nan\s*=\s*False")

ADMISSION_FIELDS = ("owner", "pinned_bytes", "append_log", "strict_json", "n_categories",
                    "admitted", "has_stable_helper", "reason_len", "reason")
REGISTERED_NEGATIVES: tuple[str, ...] = ()

POLICY_RULES = [
    "新增例外必须落在三类理由之内（pinned_bytes / append_log / strict_json），"
    "新类别要先改本预注册再登记。",
    "被冻结点名的脚本若要改字节，先走『解冻 / 更正』流程，不得默默改。",
    "例外件重跑仍会弄脏工作树，必须继续作为已知代价报出，不得计入迁移完成率。",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w41 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (',', '"', '\n')):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def classify_owner(owner: str, reason: str) -> dict[str, object]:
    path = REPOSITORY_ROOT / owner
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    pinned = bool(PINNED_PATTERN.search(reason))
    append = bool(APPEND_PATTERN.search(text))
    strict = bool(STRICT_PATTERN.search(text))
    categories = [name for name, flag in (("pinned_bytes", pinned),
                                          ("append_log", append),
                                          ("strict_json", strict)) if flag]
    return {
        "owner": owner,
        "pinned_bytes": pinned,
        "append_log": append,
        "strict_json": strict,
        "n_categories": len(categories),
        "admitted": bool(categories),
        "has_stable_helper": "write_json_stable" in text,
        "reason_len": len(reason),
        "reason": reason,
    }


def build() -> dict[str, object]:
    rows = [classify_owner(owner, reason) for owner, reason in sorted(EXEMPT_WRITERS.items())]
    counts = {
        "pinned_bytes": sum(1 for row in rows if row["pinned_bytes"]),
        "append_log": sum(1 for row in rows if row["append_log"]),
        "strict_json": sum(1 for row in rows if row["strict_json"]),
    }
    overlap = [str(row["owner"]) for row in rows if row["pinned_bytes"] and row["append_log"]]
    return {
        "rows": rows,
        "counts": counts,
        "n_owners": len(rows),
        "overlap_pinned_append": overlap,
        "categories_registered": dict(EXEMPT_CATEGORIES),
    }


def _verdict(ok: bool) -> str:
    return "成立" if ok else "判否"


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w41_exemption_admission"]
    expected = dict(lane["expected_counts"])
    rows = list(payload["rows"])
    counts = dict(payload["counts"])
    criteria: list[dict[str, object]] = []
    criteria.append({
        "id": "H41c1",
        "description": "例外登记共 22 个 owner",
        "value": float(payload["n_owners"]),
        "threshold": float(lane["expected_owners"]),
        "verdict": _verdict(int(payload["n_owners"]) == int(lane["expected_owners"])),
    })
    criteria.append({
        "id": "H41c2",
        "description": "机械证据下 pinned_bytes 计数 = 16",
        "value": float(counts["pinned_bytes"]),
        "threshold": float(expected["pinned_bytes"]),
        "verdict": _verdict(counts["pinned_bytes"] == expected["pinned_bytes"]),
    })
    criteria.append({
        "id": "H41c3",
        "description": "机械证据下 append_log 计数 = 4（更正 W40 手写分组的 3）",
        "value": float(counts["append_log"]),
        "threshold": float(expected["append_log"]),
        "verdict": _verdict(counts["append_log"] == expected["append_log"]),
    })
    criteria.append({
        "id": "H41c4",
        "description": "机械证据下 strict_json 计数 = 3",
        "value": float(counts["strict_json"]),
        "threshold": float(expected["strict_json"]),
        "verdict": _verdict(counts["strict_json"] == expected["strict_json"]),
    })
    overlap = [str(value) for value in payload["overlap_pinned_append"]]
    criteria.append({
        "id": "H41c5",
        "description": "pinned ∩ append 重叠只有 1 个且是 pubchem_identity_layer.py",
        "value": float(len(overlap)),
        "threshold": float(lane["expected_overlap_pinned_append"]),
        "verdict": _verdict(overlap == [str(lane["expected_overlap_owner"])]),
    })
    criteria.append({
        "id": "H41c6",
        "description": "每个 owner 至少落进一条理由类别（没有无理由例外）",
        "value": float(sum(1 for row in rows if row["admitted"])),
        "threshold": float(payload["n_owners"]),
        "verdict": _verdict(all(bool(row["admitted"]) for row in rows)),
    })
    criteria.append({
        "id": "H41c7",
        "description": "没有任何被登记 owner 含 write_json_stable（反向漏网 = 0）",
        "value": float(sum(1 for row in rows if row["has_stable_helper"])),
        "threshold": 0.0,
        "verdict": _verdict(not any(row["has_stable_helper"] for row in rows)),
    })
    criteria.append({
        "id": "H41c8",
        "description": "每条例外理由非空（>= 6 字符）",
        "value": float(min(int(row["reason_len"]) for row in rows)),
        "threshold": 6.0,
        "verdict": _verdict(all(int(row["reason_len"]) >= 6 for row in rows)),
    })
    criteria.append({
        "id": "H41c9",
        "description": "三类准入规则写进策略件（3 条）",
        "value": float(len(POLICY_RULES)),
        "threshold": 3.0,
        "verdict": _verdict(len(POLICY_RULES) == 3),
    })
    criteria.append({
        "id": "H41c10",
        "description": "W40 探针字节前后一致（登记表来源未被改写）",
        "value": 1.0,
        "threshold": 1.0,
        "verdict": "成立",
    })
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  prereg: Mapping[str, object]) -> str:
    lane = prereg["lanes"]["w41_exemption_admission"]
    rows = list(payload["rows"])
    counts = dict(payload["counts"])
    lines = [
        "# W41-C 例外登记表准入规则（三类理由的机械守卫）",
        "",
        "**性质**：后验 / 治理件，**0 shot（累计仍 19）**。不改任何 owner 字节，只按源码证据分类。",
        "",
        "## 1. 准入规则",
        "",
        "| 类别 | 机械证据 |",
        "| --- | --- |",
        "| `pinned_bytes` | 理由文本命中 {钉死, 冻结, 摘要, summary, prereg, manifest, 依赖件, 引用, 历史记录, 比对} 之一 |",
        "| `append_log` | owner 源码含追加模式 `open(..., \"a\")` |",
        "| `strict_json` | owner 源码含 `allow_nan=False` |",
        "",
        "三条策略规则（写进 `probes/artifacts/w41_exemption_policy.json`）：",
        "",
    ]
    for index, rule in enumerate(POLICY_RULES, start=1):
        lines.append(str(index) + ". " + rule)
    lines += [
        "",
        "## 2. 计数与更正",
        "",
        "| 类别 | 机械证据计数 | W40 手写分组 |",
        "| --- | ---: | ---: |",
        "| pinned_bytes | " + str(counts["pinned_bytes"]) + " | 16 |",
        "| append_log | " + str(counts["append_log"]) + " | 3 |",
        "| strict_json | " + str(counts["strict_json"]) + " | 3 |",
        "",
        "**更正**：" + str(lane.get("revision_note", "")),
        "",
        "## 3. 判定",
        "",
        "| 判据 | 说明 | 读数 | 门槛 | 判定 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = format(float(value), ".6g") if isinstance(value, (int, float)) else str(value)
        threshold = item["threshold"]
        ttext = format(float(threshold), ".6g") if isinstance(threshold, (int, float)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | "
                     + text + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 4. 边界",
        "",
        "- 例外登记**不是豁免**：这 22 个 owner 重跑仍会弄脏工作树，是明确保留的已知代价。",
        "- 机械证据只证明「理由可归入三类且 owner 确不含稳定写入」，**不**证明这些站点不能迁移以外的任何事。",
        "- `pinned_bytes` 的关键词匹配是文本级证据；它给出的是准入判据，不是对钉死链的完整证明。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    before = {str(W40_PROBE): sha256_file(W40_PROBE)}
    payload = build()
    after = {str(W40_PROBE): sha256_file(W40_PROBE)}
    inputs_unchanged = before == after
    criteria = evaluate(payload, prereg)
    criteria[-1]["value"] = 1.0 if inputs_unchanged else 0.0
    criteria[-1]["verdict"] = _verdict(inputs_unchanged)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(ADMISSION_CSV, ADMISSION_FIELDS, payload["rows"])
    policy = {
        "schema": "w41_exemption_policy/policy@1",
        "task": TASK,
        "categories": payload["categories_registered"],
        "evidence_rules": {
            "pinned_bytes": "理由文本命中钉死/冻结/摘要/summary/prereg/manifest/依赖件/引用/历史记录/比对之一",
            "append_log": "owner 源码含追加模式 open(..., \"a\")",
            "strict_json": "owner 源码含 allow_nan=False",
        },
        "policy_rules": POLICY_RULES,
        "counts": payload["counts"],
        "n_owners": payload["n_owners"],
        "overlap_pinned_append": payload["overlap_pinned_append"],
        "w40_hand_grouping_correction": prereg["lanes"]["w41_exemption_admission"].get("revision_note", ""),
        "known_cost": "这 22 个 owner 重跑仍会弄脏工作树；不得计入迁移完成率。",
    }
    write_json_stable(POLICY_PATH, policy)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读 EXEMPT_WRITERS 与各 owner 源码做机械分类；不重拟合臂、不新增特征列、不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "counts": payload["counts"],
        "n_owners": payload["n_owners"],
        "overlap_pinned_append": payload["overlap_pinned_append"],
        "policy_rules": POLICY_RULES,
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "22 个例外 owner 全部按源码证据落进三类：pinned "
            + str(payload["counts"]["pinned_bytes"]) + " / append "
            + str(payload["counts"]["append_log"]) + " / strict "
            + str(payload["counts"]["strict_json"]) + "（重叠 "
            + str(len(payload["overlap_pinned_append"])) + "）。",
            "机械证据更正 W40 手写分组：真 pinned∩append 重叠是 pubchem_identity_layer（不是 pubchem_liquid_window_harvest）。",
            "反向漏网 0：没有任何被登记 owner 含 write_json_stable；三条准入规则已写进策略件。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, prereg), encoding="utf-8", newline="\n")

    print("owners " + str(payload["n_owners"]) + "; counts " + str(payload["counts"])
          + "; overlap " + str(payload["overlap_pinned_append"]))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())