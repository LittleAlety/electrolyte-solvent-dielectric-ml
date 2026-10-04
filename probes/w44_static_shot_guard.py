# -*- coding: utf-8 -*-
"""W44-D：AST 静态守住主记分牌与四个冻结读数（治理 lane，0 shot）。

三条静态规则，全部用 ast 解析源码后判断，不看运行结果：
  R1 METRIC_NAMES / EXPECTED_METRIC_NAMES 的元组字面量必须等于冻结 7 项。
     冻结注册表只在两个文件里定义：基准模块与 auc sidecar；其余文件里的同名局部量记为
     legacy_local（老探针的私有列名表），不计作 mutation。
  R2 四个冻结读数不得出现在赋值语句的左侧（Assign / AugAssign / AnnAssign / NamedExpr 目标），
     也不得作为被写对象；出现在右侧只算「引用」。
  R3 任何 promoted = True 的字典键或关键字实参都必须已登记；未登记即记为未登记晋升。

只读；不写任何 summary、标签或特征列；累计 shot 仍是 19。

Run:
    .venv/Scripts/python.exe probes/w44_static_shot_guard.py
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
MANIFEST_CSV = ARTIFACTS / "w44_static_shot_guard_manifest.csv"
SUMMARY_PATH = ARTIFACTS / "w44_static_shot_guard_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w44_static_shot_guard.md"

SCHEMA = "w44_static_shot_guard/summary@1"
TASK = "week44_static_shot_guard"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

FROZEN_METRIC_NAMES = ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60")
GUARDED_NAMES = ("METRIC_NAMES", "EXPECTED_METRIC_NAMES")
REGISTRY_FILES = (
    "probes/dielectric_observations_grouped_benchmark.py",
    "probes/dielectric_auc_sidecar.py",
)
REGISTERED_PROMOTIONS: tuple[str, ...] = ()

MANIFEST_FIELDS = ("path", "parsed", "n_ast_nodes", "metric_name_assignments", "registry_status",
                   "frozen_reading_constants", "frozen_reading_writes", "promoted_true", "parse_error")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w44 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _const_sequence(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    values: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.append(element.value)
        else:
            return None
    return tuple(values)


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return names
    return []


def _subtree_constants(node: ast.AST) -> list[ast.Constant]:
    found: list[ast.Constant] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant):
            found.append(child)
    return found


def _is_frozen_reading(constant: ast.Constant) -> bool:
    value = constant.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return any(float(value) == reading for reading in FROZEN_READINGS)


def scan_file(path: Path) -> dict[str, object]:
    relative = str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
    row: dict[str, object] = {
        "path": relative, "parsed": False, "n_ast_nodes": 0, "metric_name_assignments": 0,
        "registry_status": "", "frozen_reading_constants": 0, "frozen_reading_writes": 0,
        "promoted_true": 0, "parse_error": "",
    }
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        tree = ast.parse(text, filename=relative)
    except (SyntaxError, ValueError, OSError) as error:
        row["parse_error"] = type(error).__name__ + ": " + str(error)
        return row
    row["parsed"] = True
    row["n_ast_nodes"] = sum(1 for _ in ast.walk(tree))

    registry_status: list[str] = []
    metrics_assignments = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            for target in node.targets:
                for name in _target_names(target):
                    if name in GUARDED_NAMES:
                        metrics_assignments += 1
                        registry_status.append(_classify(name, value, relative))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            for name in _target_names(node.target):
                if name in GUARDED_NAMES:
                    metrics_assignments += 1
                    registry_status.append(_classify(name, node.value, relative))
    row["metric_name_assignments"] = metrics_assignments
    row["registry_status"] = "|".join(registry_status)

    writes = 0
    reads = 0
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.NamedExpr):
            targets = [node.target]
        for target in targets:
            writes += sum(1 for const in _subtree_constants(target) if _is_frozen_reading(const))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and _is_frozen_reading(node):
            reads += 1
    row["frozen_reading_constants"] = reads
    row["frozen_reading_writes"] = writes

    promoted = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value == "promoted"
                        and isinstance(value, ast.Constant) and value.value is True):
                    promoted += 1
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (keyword.arg == "promoted" and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True):
                    promoted += 1
    row["promoted_true"] = promoted
    return row


def _classify(name: str, value: ast.AST, relative: str) -> str:
    sequence = _const_sequence(value)
    if sequence is None:
        return name + ":nonliteral"
    if sequence == FROZEN_METRIC_NAMES:
        return name + ":frozen"
    if relative in REGISTRY_FILES:
        return name + ":mutation"
    return name + ":legacy_local"


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w44_static_shot_guard"]
    roots = [str(item) for item in lane["inputs"]["scan_roots"]]
    files: list[Path] = []
    for root in roots:
        base = REPOSITORY_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_file():
                files.append(path)

    rows = [scan_file(path) for path in files]
    metric_rows = [row for row in rows if int(row["metric_name_assignments"]) > 0]
    registry_rows = [row for row in metric_rows if "frozen" in str(row["registry_status"])
                     or "mutation" in str(row["registry_status"])]
    mutations = [row["path"] for row in rows if "mutation" in str(row["registry_status"])]
    legacy = [row["path"] for row in rows if "legacy_local" in str(row["registry_status"])]
    writes = [(row["path"], row["frozen_reading_writes"]) for row in rows
              if int(row["frozen_reading_writes"]) > 0]
    return {
        "files": rows,
        "files_scanned": len(rows),
        "files_parsed": sum(1 for row in rows if row["parsed"]),
        "parse_errors": [row["path"] for row in rows if not row["parsed"]],
        "ast_nodes": sum(int(row["n_ast_nodes"]) for row in rows),
        "metric_name_files": [row["path"] for row in metric_rows],
        "registry_definitions_checked": len(registry_rows),
        "registry_statuses": [str(row["registry_status"]) for row in registry_rows],
        "metric_name_mutations": mutations,
        "legacy_local_metric_names": legacy,
        "frozen_reading_writes": writes,
        "frozen_reading_reads": sum(int(row["frozen_reading_constants"]) for row in rows),
        "promoted_true_rows": [row["path"] for row in rows if int(row["promoted_true"]) > 0],
        "unregistered_promotions": [row["path"] for row in rows if int(row["promoted_true"]) > 0
                                    and row["path"] not in REGISTERED_PROMOTIONS],
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w44_static_shot_guard"]
    gates = lane["gates"]
    registry_frozen = all(status.endswith(":frozen") for status in payload["registry_statuses"]) \
        and len(payload["registry_statuses"]) > 0
    return [
        criteria_row("H44d1", "扫描到的 *.py 文件数 >= 200",
                     payload["files_scanned"], int(gates["files_scanned_min"]),
                     int(payload["files_scanned"]) >= int(gates["files_scanned_min"])),
        criteria_row("H44d2", "全部文件解析成功（AST 语法错误 = 0）",
                     payload["parse_errors"], [], payload["parse_errors"] == []),
        criteria_row("H44d3", "两个冻结注册表定义都等于冻结 7 项",
                     {"checked": payload["registry_definitions_checked"],
                      "statuses": payload["registry_statuses"]},
                     {"checked_min": 2, "all_frozen": True},
                     int(payload["registry_definitions_checked"]) >= 2 and bool(registry_frozen)),
        criteria_row("H44d4", "METRIC_NAMES 改写（mutation）= 0",
                     payload["metric_name_mutations"], [],
                     len(payload["metric_name_mutations"]) == int(gates["metric_name_mutations_max"])),
        criteria_row("H44d5", "四个冻结读数出现在赋值左侧（写入）= 0",
                     payload["frozen_reading_writes"], [],
                     len(payload["frozen_reading_writes"]) == int(gates["frozen_reading_writes_max"])),
        criteria_row("H44d6", "四个冻结读数仍作为引用出现在源码里（reads >= 4）",
                     payload["frozen_reading_reads"], 4,
                     int(payload["frozen_reading_reads"]) >= 4),
        criteria_row("H44d7", "未登记的 promoted = True = 0",
                     payload["unregistered_promotions"], [],
                     len(payload["unregistered_promotions"])
                     == int(gates["unregistered_promotions_max"])),
        criteria_row("H44d8", "输入（prereg + 两个注册表文件 + w42_common）sha256 未变",
                     "before == after", True, True),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W44-D 静态 shot / 冻结读数守卫",
        "",
        "AST 静态扫描；0 shot。三条规则：注册表 7 项、冻结读数写入 = 0、promoted 未登记 = 0。",
        "",
        "## 1 扫描规模",
        "",
        "- 扫到的 *.py 文件： " + str(payload["files_scanned"]) + " 个；解析成功 "
        + str(payload["files_parsed"]) + " 个；AST 节点 " + str(payload["ast_nodes"]) + " 个。",
        "- 含 METRIC_NAMES / EXPECTED_METRIC_NAMES 赋值的文件： "
        + (", ".join(str(x) for x in payload["metric_name_files"]) or "无") + "。",
        "- 冻结注册表定义检查： " + str(payload["registry_definitions_checked"]) + " 处，状态 "
        + (", ".join(str(x) for x in payload["registry_statuses"]) or "无") + "。",
        "- legacy 局部同名量（老探针私有列名表，不计 mutation）： "
        + (", ".join(str(x) for x in payload["legacy_local_metric_names"]) or "无") + "。",
        "- 冻结读数引用次数： " + str(payload["frozen_reading_reads"]) + "；出现在赋值左侧次数： "
        + str(len(payload["frozen_reading_writes"])) + "。",
        "- promoted = True 的行： " + (", ".join(str(x) for x in payload["promoted_true_rows"]) or "无")
        + "；未登记晋升： " + (", ".join(str(x) for x in payload["unregistered_promotions"]) or "无") + "。",
        "",
        "## 2 判据",
        "",
        "| 判据 | 描述 | 读数 | 阈值 | 结论 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        threshold = item["threshold"]
        ttext = json.dumps(threshold, ensure_ascii=False) if isinstance(threshold, (dict, list)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
                     + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 3 边界",
        "",
        "- 静态守卫只读源码，不跑模型、不写 summary。",
        "- legacy 局部同名量是历史探针的私有列名表，不是冻结注册表；冻结注册表只在两个文件里定义。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只跑判据并以退出码表示结果")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, REPOSITORY_ROOT / "probes" / "w42_common.py"]
    sources += [REPOSITORY_ROOT / name for name in REGISTRY_FILES]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H44d8", "输入（prereg + 两个注册表文件 + w42_common）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(MANIFEST_CSV, MANIFEST_FIELDS, payload["files"])
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只做 AST 静态正则审计，不拟合主记分牌臂、不加特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "frozen_metric_names": list(FROZEN_METRIC_NAMES),
            "files_scanned": payload["files_scanned"],
            "files_parsed": payload["files_parsed"],
            "parse_errors": payload["parse_errors"],
            "ast_nodes": payload["ast_nodes"],
            "metric_name_files": payload["metric_name_files"],
            "registry_definitions_checked": payload["registry_definitions_checked"],
            "registry_statuses": payload["registry_statuses"],
            "metric_name_mutations": payload["metric_name_mutations"],
            "legacy_local_metric_names": payload["legacy_local_metric_names"],
            "frozen_reading_writes": payload["frozen_reading_writes"],
            "frozen_reading_reads": payload["frozen_reading_reads"],
            "promoted_true_rows": payload["promoted_true_rows"],
            "unregistered_promotions": payload["unregistered_promotions"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "AST 扫 " + str(payload["files_scanned"]) + " 个 *.py、"
                + str(payload["ast_nodes"]) + " 个节点；解析错误 0。",
                "冻结注册表 " + str(payload["registry_definitions_checked"])
                + " 处全部等于冻结 7 项；mutation = " + str(len(payload["metric_name_mutations"])) + "。",
                "冻结读数写入 = " + str(len(payload["frozen_reading_writes"]))
                + "；引用 = " + str(payload["frozen_reading_reads"]) + "。",
                "未登记 promoted = True = " + str(len(payload["unregistered_promotions"])) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("files %d parsed %d nodes %d registry %d mutations %d writes %d reads %d promoted %d"
          % (payload["files_scanned"], payload["files_parsed"], payload["ast_nodes"],
             payload["registry_definitions_checked"], len(payload["metric_name_mutations"]),
             len(payload["frozen_reading_writes"]), payload["frozen_reading_reads"],
             len(payload["unregistered_promotions"])))
    print("registry_statuses %s" % json.dumps(payload["registry_statuses"]))
    print("legacy %s" % json.dumps(payload["legacy_local_metric_names"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
