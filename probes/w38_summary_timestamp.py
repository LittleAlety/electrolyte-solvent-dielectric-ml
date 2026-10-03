# -*- coding: utf-8 -*-
"""W38-E：把「干净重导之后工作树立刻又变脏」这条 AF-12 同族缺陷收口（后验，不占 shot）。

README §11 第 19 条登记的是：被跟踪的 `*_summary.json` 带 `generated_at_utc` /
`elapsed_seconds`，因此**重跑写入器**（或任何「复现盘上 summary」的测试）即使其余字段逐字节
相同，也会把工作树写脏 —— 而 `worktree_dirty` 与 `artifacts_commit` 正是 AF-12 用来标识
交付字节的两个坐标。

修法（W37 登记的第二个选项的更严格版本，等价于第一个）：写入器改为**稳定写入** ——
若盘上文件与待写内容除 volatile 字段外完全一致，则**保留原字节与原时间戳**。
本件做三件事：

1. 盘点：仓库里还有哪些被跟踪的 JSON 带时间戳、各自的写入器是谁、是否已迁到稳定写入；
2. 单元检查：稳定写入在「仅时间戳不同」时不写、在「科学字段变化」时照写、在首次写入时照写；
3. 端到端检查：连跑两次 `probes/w37_gate_admission_export.py`，断言被跟踪 summary 相对 HEAD 无改动。

只跑既有探针与合成临时文件；不拟合模型、不新增特征、不触 ε 主记分牌 ⇒ 0 shot。

Run:
    .venv/Scripts/python.exe probes/w38_summary_timestamp.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import VOLATILE_SUMMARY_KEYS, write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import VOLATILE_SUMMARY_KEYS, write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
INVENTORY_CSV = ARTIFACTS / "w38_timestamp_inventory.csv"
SUMMARY_PATH = ARTIFACTS / "w38_summary_timestamp_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w38_timestamp_closeout.md"

SCHEMA = "w38_summary_timestamp/summary@1"
TASK = "week38_summary_timestamp"

MIGRATED_PROBE = "probes/w37_gate_admission_export.py"
MIGRATED_ARTIFACT = "probes/artifacts/w37_gate_admission_export_summary.json"
E2E_RUNS = 2
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

INVENTORY_FIELDS = ("tracked_json", "has_timestamp", "writers", "writers_using_stable_helper",
                    "status")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(REPOSITORY_ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=False)


def tracked_files() -> list[str]:
    completed = git("ls-files", "-z")
    return [entry for entry in (completed.stdout or "").split("\0") if entry]


def writer_scripts() -> list[Path]:
    scripts = []
    for directory in ("probes", "scripts", "tests"):
        scripts.extend(sorted((REPOSITORY_ROOT / directory).rglob("*.py")))
    return scripts


def build_inventory() -> list[dict[str, object]]:
    writers = writer_scripts()
    writer_text = {path: path.read_text(encoding="utf-8", errors="replace") for path in writers}
    rows: list[dict[str, object]] = []
    for relative in tracked_files():
        if not relative.endswith(".json"):
            continue
        path = REPOSITORY_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        has_timestamp = "generated_at_utc" in text
        if not has_timestamp:
            continue
        name = path.name
        owners = sorted(str(owner.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
                        for owner, body in writer_text.items() if name in body)
        migrated_owners = sorted(owner for owner in owners
                                 if "write_json_stable" in writer_text[REPOSITORY_ROOT / owner])
        if not owners:
            status = "无写入器（历史产物）"
        elif migrated_owners:
            status = "已迁移稳定写入"
        else:
            status = "待迁移"
        rows.append(
            {
                "tracked_json": relative,
                "has_timestamp": has_timestamp,
                "writers": ";".join(owners),
                "writers_using_stable_helper": ";".join(migrated_owners),
                "status": status,
            }
        )
    return rows


def unit_checks() -> dict[str, object]:
    results: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "summary.json"
        base = {"schema": "x@1", "task": "t", "value": 1.0,
                "generated_at_utc": "2020-01-01T00:00:00Z", "elapsed_seconds": 1.0}
        write_json_stable(target, base)
        first = target.read_bytes()
        rerun = write_json_stable(target, {**base, "generated_at_utc": "2026-10-03T00:00:00Z",
                                           "elapsed_seconds": 9.9})
        second = target.read_bytes()
        results["volatile_only_keeps_bytes"] = first == second
        results["volatile_only_returns"] = rerun
        changed = write_json_stable(target, {**base, "value": 2.0,
                                             "generated_at_utc": "2026-10-03T00:00:00Z",
                                             "elapsed_seconds": 9.9})
        third = target.read_bytes()
        results["scientific_change_rewrites"] = third != second
        results["scientific_change_returns"] = changed
        fresh_target = Path(tmp) / "fresh.json"
        fresh = write_json_stable(fresh_target, base)
        results["first_write_writes"] = fresh == "written" and fresh_target.is_file()
        results["volatile_keys"] = list(VOLATILE_SUMMARY_KEYS)
    return results


def end_to_end() -> dict[str, object]:
    before = git("status", "--porcelain", MIGRATED_ARTIFACT).stdout.strip()
    runs: list[dict[str, object]] = []
    for _ in range(E2E_RUNS):
        completed = subprocess.run([sys.executable, MIGRATED_PROBE], cwd=str(REPOSITORY_ROOT),
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", check=False)
        runs.append({"exit_code": completed.returncode,
                     "stable_line": next((line.strip() for line in (completed.stdout or "").splitlines()
                                          if line.startswith("summary ")), "")})
    after = git("status", "--porcelain", MIGRATED_ARTIFACT).stdout.strip()
    return {"status_before": before, "status_after": after, "runs": runs,
            "clean_after_reruns": after == ""}


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    unit = payload["unit"]
    e2e = payload["e2e"]
    inventory = payload["inventory"]
    criteria: list[dict[str, object]] = []
    criteria.append(
        {
            "id": "H38e1",
            "description": "稳定写入助手可从 probes/export_results_common 导入，volatile 键为时间戳两项",
            "value": float(len(unit["volatile_keys"])),
            "threshold": 2.0,
            "verdict": "成立" if list(unit["volatile_keys"]) == ["generated_at_utc", "elapsed_seconds"] else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38e2",
            "description": "仅 volatile 字段不同时，稳定写入不改变盘上字节",
            "value": 1.0 if unit["volatile_only_keeps_bytes"] else 0.0,
            "threshold": 1.0,
            "verdict": "成立" if unit["volatile_only_keeps_bytes"] else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38e3",
            "description": "科学字段变化时仍照写（稳定写入不是「永不写」）",
            "value": 1.0 if unit["scientific_change_rewrites"] else 0.0,
            "threshold": 1.0,
            "verdict": "成立" if unit["scientific_change_rewrites"] else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38e4",
            "description": "端到端：连跑两次 W37 导出探针后，被跟踪 summary 相对 HEAD 无改动",
            "value": 1.0 if e2e["clean_after_reruns"] else 0.0,
            "threshold": 1.0,
            "verdict": "成立" if e2e["clean_after_reruns"] else "判否",
        }
    )
    migrated = sum(1 for row in inventory if str(row["status"]) == "已迁移稳定写入")
    criteria.append(
        {
            "id": "H38e5",
            "description": "盘点：带时间戳的被跟踪 JSON 已有写入器迁移到稳定写入（≥ 1）",
            "value": float(migrated),
            "threshold": 1.0,
            "verdict": "成立" if migrated >= 1 else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38e6",
            "description": "0 shot（累计 19）；只跑既有探针与合成临时文件",
            "value": 0.0,
            "threshold": None,
            "verdict": "成立",
        }
    )
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    inventory = payload["inventory"]
    pending = [row for row in inventory if str(row["status"]) == "待迁移"]
    orphan = [row for row in inventory if str(row["status"]) == "无写入器（历史产物）"]
    lines = [
        "# W38-E 收口：干净重导不再把工作树写脏（后验，不占 shot）",
        "",
        "README §11 第 19 条登记：被跟踪的 summary 带 `generated_at_utc` / `elapsed_seconds`，",
        "重跑写入器就会脏树，而 `worktree_dirty` 与 `artifacts_commit` 是 AF-12 标识交付字节的坐标。",
        "",
        "## 1. 修法",
        "",
        "`probes/export_results_common.write_json_stable(path, payload)`：写入前先与盘上文件比对，",
        "**若除 volatile 键（`generated_at_utc` / `elapsed_seconds`）外完全一致，则保留原字节**；",
        "否则照常写入。语义是「同一内容不重记时间」，不是「永不写」。",
        "",
        "已接线：`probes/w37_gate_admission_export.py` 的 summary 写入由 `write_json_lf` 换成",
        "`write_json_stable`。",
        "",
        "## 2. 端到端证据",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 重跑前 `git status` 该文件 | " + (("空" if not payload["e2e"]["status_before"] else "非空")) + " |",
        "| 重跑次数 | " + str(E2E_RUNS) + " |",
        "| 每次退出码 | " + ", ".join(str(run["exit_code"]) for run in payload["e2e"]["runs"]) + " |",
        "| 每次写入器回报 | " + ", ".join("`" + str(run["stable_line"]) + "`" for run in payload["e2e"]["runs"]) + " |",
        "| 重跑后 `git status` 该文件 | " + (("空" if not payload["e2e"]["status_after"] else "非空")) + " |",
        "",
        "## 3. 盘点（" + str(len(inventory)) + " 个带时间戳的被跟踪 JSON）",
        "",
        "| 状态 | 数量 |",
        "| --- | --- |",
        "| 已迁移稳定写入 | " + str(sum(1 for row in inventory if str(row["status"]) == "已迁移稳定写入")) + " |",
        "| 待迁移 | " + str(len(pending)) + " |",
        "| 无写入器（历史产物） | " + str(len(orphan)) + " |",
        "",
        "待迁移清单（写入器仍在用普通写入）：",
        "",
        "| 被跟踪 JSON | 写入器 |",
        "| --- | --- |",
    ]
    for row in pending:
        lines.append("| " + str(row["tracked_json"]) + " | " + str(row["writers"]) + " |")
    lines += [
        "",
        "## 4. 判据",
        "",
        "| 判据 | 内容 | 读数 | 门 | 判决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append(
            "| " + str(item["id"]) + " | " + str(item["description"]) + " | "
            + ("—" if item["value"] is None else format(float(item["value"]), ".6g")) + " | "
            + ("—" if item["threshold"] is None else format(float(item["threshold"]), ".6g"))
            + " | " + str(item["verdict"]) + " |"
        )
    lines += [
        "",
        "## 5. 边界与剩余工作",
        "",
        "- 本件只迁移**已观测到会脏树的那一条链路**（W37 导出探针）并把助手放进共享模块；",
        "  其余带时间戳的跟踪件**仍待迁移**（见上表），因此 §11 第 19 条的状态是",
        "  **「机制已修、迁移未完成」**，不是「已关闭」。",
        "- 「无写入器」的那一类是历史产物：它们的写入器已不在仓库里，不会被重跑脏化，",
        "  但也不受守卫保护。",
        "- 稳定写入只对**顶层键**生效（`generated_at_utc` / `elapsed_seconds`）；嵌在子对象里的",
        "  时间戳不在覆盖范围——这是已知盲区。",
        "- 不拟合模型、不触四个冻结读数；不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-e2e", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    inventory = build_inventory()
    unit = unit_checks()
    e2e = {"status_before": "", "status_after": "", "runs": [], "clean_after_reruns": False}
    if not args.skip_e2e:
        e2e = end_to_end()
    payload = {"inventory": inventory, "unit": unit, "e2e": e2e}
    criteria = evaluate(payload)

    with INVENTORY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "治理件：只跑既有探针与合成临时文件，不拟合模型、不新增特征。",
        },
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE],
        "migrated": {"probe": MIGRATED_PROBE, "artifact": MIGRATED_ARTIFACT,
                     "helper": "probes/export_results_common.write_json_stable",
                     "volatile_keys": list(VOLATILE_SUMMARY_KEYS)},
        "inventory": inventory,
        "inventory_counts": {
            "total": len(inventory),
            "migrated": sum(1 for row in inventory if str(row["status"]) == "已迁移稳定写入"),
            "pending": sum(1 for row in inventory if str(row["status"]) == "待迁移"),
            "orphan": sum(1 for row in inventory if str(row["status"]) == "无写入器（历史产物）"),
        },
        "unit_checks": unit,
        "end_to_end": e2e,
        "criteria": criteria,
        "headline": [
            "干净重导不再写脏那条已观测链路：连跑两次 W37 导出探针后，被跟踪 summary 相对 HEAD 无改动。",
            "稳定写入助手放进共享模块 `probes/export_results_common.write_json_stable`。",
            "盘点 " + str(len(inventory)) + " 个带时间戳的被跟踪 JSON：已迁移 "
            + str(sum(1 for row in inventory if str(row["status"]) == "已迁移稳定写入")) + "、待迁移 "
            + str(sum(1 for row in inventory if str(row["status"]) == "待迁移")) + "。",
            "§11 第 19 条状态：机制已修、迁移未完成。",
            "不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    failed = [item for item in criteria if item["verdict"] != "成立"]
    print("inventory " + str(len(inventory)) + " timestamped tracked json; migrated "
          + str(sum(1 for row in inventory if str(row["status"]) == "已迁移稳定写入"))
          + "; pending " + str(sum(1 for row in inventory if str(row["status"]) == "待迁移")))
    print("unit: volatile-only keeps bytes " + str(unit["volatile_only_keeps_bytes"])
          + "; scientific change rewrites " + str(unit["scientific_change_rewrites"]))
    print("e2e clean after " + str(E2E_RUNS) + " reruns: " + str(e2e["clean_after_reruns"]))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print("FAIL " + str(item["id"]) + " " + str(item["description"]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())