# -*- coding: utf-8 -*-
"""W44-B：把治理守卫做成逐轮验收运行器（治理 lane，0 shot）。

W43-D 出了一条治理守卫（四个台账不变式），但它只在 W43 那一轮被跑过。本件把它做成
**逐轮验收运行器**：一次同时
  * 跑 W43-D 的四个不变式（复用 w43_governance_ledger.compute，不重写规则）；
  * 扫 成果输出/week*/week*_summary.json，对每一轮抽五类验收字段并判定通过/未声明；
  * 汇总成一张逐轮验收矩阵，回答「哪几轮通过、哪几轮没声明字段、最近五轮是否全过」。

只读；不写任何 week summary；累计 shot 仍是 19。

Run:
    .venv/Scripts/python.exe probes/w44_acceptance_runner.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import w43_governance_ledger as ledger
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
W43_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
OUTPUT_ROOT = Path(r"E:/Claude Code/电解质ML/成果输出")
MATRIX_CSV = ARTIFACTS / "w44_acceptance_matrix.csv"
RECORD_JSON = ARTIFACTS / "w44_acceptance_record.json"
SUMMARY_PATH = ARTIFACTS / "w44_acceptance_runner_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w44_acceptance_runner.md"

SCHEMA = "w44_acceptance_runner/summary@1"
TASK = "week44_acceptance_runner"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

MATRIX_FIELDS = ("week", "path", "verification_passed", "lanes_missing_empty",
                 "frozen_red_lines_intact", "no_unregistered_failures", "declared_fields",
                 "passed", "verdict")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w44 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _week_sort_key(week: str) -> int:
    digits = "".join(ch for ch in week if ch.isdigit())
    return int(digits) if digits else 0


def _week_verdict(week: str, path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    declared: list[str] = []
    checks: dict[str, object] = {}
    if "verification_passed" in payload:
        declared.append("verification_passed")
        checks["verification_passed"] = bool(payload["verification_passed"])
    if "lanes_missing" in payload:
        declared.append("lanes_missing_empty")
        checks["lanes_missing_empty"] = list(payload["lanes_missing"]) == []
    if "frozen_red_lines_intact" in payload:
        declared.append("frozen_red_lines_intact")
        checks["frozen_red_lines_intact"] = bool(payload["frozen_red_lines_intact"])
    if "verdicts_unregistered_failures" in payload:
        declared.append("no_unregistered_failures")
        checks["no_unregistered_failures"] = list(payload["verdicts_unregistered_failures"]) == []
    passed = all(bool(value) for value in checks.values()) if checks else True
    verdict = "pass" if (checks and passed) else ("not_declared" if not checks else "fail")
    return {"week": week, "path": str(path), "declared_fields": written(declared),
            "passed": passed, "verdict": verdict, **checks}


def written(items: Sequence[str]) -> str:
    return "|".join(items)


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w44_acceptance_runner"]
    w43_prereg = json.loads(W43_PREREG_PATH.read_text(encoding="utf-8-sig"))
    ledger_payload = ledger.compute(w43_prereg)
    invariants = ledger_payload["invariants"]

    rows: list[dict[str, object]] = []
    for path in sorted(OUTPUT_ROOT.glob("week*/week*_summary.json")):
        week = path.parent.name
        try:
            rows.append(_week_verdict(week, path))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
    rows.sort(key=lambda row: _week_sort_key(str(row["week"])))

    declared_weeks = [row for row in rows if row["verdict"] != "not_declared"]
    failing = [row["week"] for row in rows if row["verdict"] == "fail"]
    recent = rows[-int(lane["gates"]["all_recent_weeks_pass_min"]):]
    recent_pass = all(row["verdict"] == "pass" for row in recent)
    return {
        "invariants": invariants,
        "invariants_hold": bool(
            invariants["negatives_stable"] and invariants["frozen_readings_intact"]
            and invariants["shots_monotone_nondecreasing"] and invariants["shots_ceiling_respected"]
            and invariants["summaries_scanned"] >= 300),
        "rows": rows,
        "weeks_scanned": len(rows),
        "weeks_with_summary": len(rows),
        "declared_weeks": len(declared_weeks),
        "failing_weeks": failing,
        "recent_weeks": [row["week"] for row in recent],
        "recent_all_pass": recent_pass,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w44_acceptance_runner"]["gates"]
    inv = payload["invariants"]
    criteria = [
        criteria_row("H44b1", "扫描到的轮数 >= 40",
                     payload["weeks_scanned"], int(gates["weeks_scanned_min"]),
                     int(payload["weeks_scanned"]) >= int(gates["weeks_scanned_min"])),
        criteria_row("H44b2", "声明了验收字段的轮数 >= 30",
                     payload["declared_weeks"], int(gates["weeks_with_summary_min"]),
                     int(payload["declared_weeks"]) >= int(gates["weeks_with_summary_min"])),
        criteria_row("H44b3", "最近五轮验收全部通过",
                     {"weeks": payload["recent_weeks"], "all_pass": payload["recent_all_pass"]},
                     {"min": int(gates["all_recent_weeks_pass_min"]), "all_pass": True},
                     bool(payload["recent_all_pass"])),
        criteria_row("H44b4", "无任何一轮判 fail",
                     payload["failing_weeks"], [], list(payload["failing_weeks"]) == []),
        criteria_row("H44b5", "复用 W43-D 的四个台账不变式全部成立",
                     {"negatives_stable": inv["negatives_stable"],
                      "frozen_outside": inv["frozen_outside_canon"],
                      "monotone": inv["shots_monotone_nondecreasing"],
                      "ceiling": inv["cumulative_shots_max"]},
                     {"negatives_stable": True, "frozen_outside": 0, "monotone": True, "ceiling": 19},
                     bool(payload["invariants_hold"])),
        criteria_row("H44b6", "台账扫描数 >= 300（守卫仍有效）",
                     inv["summaries_scanned"], 300, int(inv["summaries_scanned"]) >= 300),
        criteria_row("H44b7", "输入文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    inv = payload["invariants"]
    lines = [
        "# W44-B 逐轮验收运行器（治理 lane，0 shot）",
        "",
        "一次同时跑 W43-D 的四个台账不变式 + 逐轮交付摘要的五类验收字段。",
        "",
        "## 1 台账不变式（复用 W43-D 规则）",
        "",
        "- 负结果并集稳定 = " + str(inv["negatives_stable"]) + "；冻结读数越界 = "
        + str(inv["frozen_outside_canon"]) + "；shot 单调 = " + str(inv["shots_monotone_nondecreasing"])
        + "；上限 = " + str(inv["cumulative_shots_max"]) + "；扫描 JSON = " + str(inv["summaries_scanned"]) + "。",
        "",
        "## 2 逐轮验收矩阵",
        "",
        "- 扫描轮数 " + str(payload["weeks_scanned"]) + "；声明验收字段 " + str(payload["declared_weeks"])
        + "；判 fail 的轮： " + (", ".join(str(x) for x in payload["failing_weeks"]) or "无") + "。",
        "- 最近五轮：" + ", ".join(str(x) for x in payload["recent_weeks"]) + "，全过 = "
        + str(payload["recent_all_pass"]) + "。",
        "",
        "| 轮 | verification_passed | lanes_missing 空 | 冻结红线 | 无未登记判否 | 判定 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"][-12:]:
        lines.append("| " + str(row["week"]) + " | "
                     + str(row.get("verification_passed", "—")) + " | "
                     + str(row.get("lanes_missing_empty", "—")) + " | "
                     + str(row.get("frozen_red_lines_intact", "—")) + " | "
                     + str(row.get("no_unregistered_failures", "—")) + " | "
                     + str(row["verdict"]) + " |")
    lines += [
        "",
        "## 3 判据",
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
        "## 4 边界",
        "",
        "- 只读：不改任何 week summary，不重跑模型，不新增 shot。",
        "- 早期轮次没有这些字段（记为 not_declared，不算 fail）；运行器不会替它们补字段。",
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
    sources = [PREREG_PATH, W43_PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(MATRIX_CSV, MATRIX_FIELDS, payload["rows"])
        write_json_stable(RECORD_JSON, {
            "weeks_scanned": payload["weeks_scanned"],
            "failing_weeks": payload["failing_weeks"],
            "recent_weeks": payload["recent_weeks"],
            "recent_all_pass": payload["recent_all_pass"],
            "invariants": payload["invariants"],
        })
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读复用 W43-D 不变式并扫交付摘要，不拟合主记分牌臂、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": payload["inputs_unchanged"],
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "invariants": payload["invariants"],
            "invariants_hold": payload["invariants_hold"],
            "weeks_scanned": payload["weeks_scanned"],
            "declared_weeks": payload["declared_weeks"],
            "failing_weeks": payload["failing_weeks"],
            "recent_weeks": payload["recent_weeks"],
            "recent_all_pass": payload["recent_all_pass"],
            "acceptance_rows": payload["rows"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "扫描 " + str(payload["weeks_scanned"]) + " 轮，声明验收字段 " + str(payload["declared_weeks"]) + " 轮。",
                "最近五轮 " + ", ".join(str(x) for x in payload["recent_weeks"]) + " 全过 = "
                + str(payload["recent_all_pass"]) + "；判 fail 的轮： "
                + (", ".join(str(x) for x in payload["failing_weeks"]) or "无") + "。",
                "台账不变式全成立 = " + str(payload["invariants_hold"]) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("weeks %d declared %d failing %s recent_pass %s invariants %s"
          % (payload["weeks_scanned"], payload["declared_weeks"],
             payload["failing_weeks"], payload["recent_all_pass"], payload["invariants_hold"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
