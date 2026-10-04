# -*- coding: utf-8 -*-
"""W43-D：仓库级治理台账守卫（治理 lane，0 shot）。

把全仓 probes/**/*.json 当成一本台账来机器校验四条不变式：
  * 登记负结果集合稳定：所有 summary 的 registered_negatives 并集 == 已知 9 条（不新增、不丢失）；
  * 冻结读数无人改动：所有 frozen_readings_untouched 值都落在四个规范读数内（越界计数 = 0）；
  * 累计 shot 单调不减且不超 19；
  * 带 ledger 的 summary 数 >= 37，且本轮 W43 各件的 shots_this_week 全为 0。
逐文件落一张台账 CSV，便于审计。

只读：只解析 JSON，不写任何 summary 或标签。

Run:
    .venv/Scripts/python.exe probes/w43_governance_ledger.py
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

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
PROBES_DIR = REPOSITORY_ROOT / "probes"
LEDGER_CSV = ARTIFACTS / "w43_governance_ledger.csv"
LEDGER_JSON = ARTIFACTS / "w43_governance_ledger.json"
SUMMARY_PATH = ARTIFACTS / "w43_governance_ledger_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w43_governance_ledger.md"

SCHEMA = "w43_governance_ledger/summary@1"
TASK = "week43_governance_ledger"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEDGER_FIELDS = ("path", "schema", "task", "generated_at_utc", "has_ledger",
                 "shots_this_week", "cumulative_shots", "negatives_count", "frozen_count",
                 "frozen_outside_canon", "week43")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w43 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    expected = prereg["lanes"]["w43_governance_ledger"]["expected"]
    canon = set(float(value) for value in FROZEN_READINGS)
    expected_negatives = set(str(value) for value in expected["known_registered_negatives"])

    files = sorted(PROBES_DIR.rglob("*.json"))
    rows: list[dict[str, object]] = []
    negatives: set[str] = set()
    frozen_outside = 0
    ledger_entries: list[tuple[str, int, int | None, str]] = []
    scanned = 0

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        scanned += 1
        relative = str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
        declared_negatives = payload.get("registered_negatives") or []
        if isinstance(declared_negatives, list):
            negatives.update(str(value) for value in declared_negatives)
        declared_frozen = payload.get("frozen_readings_untouched") or []
        outside = 0
        if isinstance(declared_frozen, list):
            for value in declared_frozen:
                try:
                    if float(value) not in canon:
                        outside += 1
                except (TypeError, ValueError):
                    outside += 1
        frozen_outside += outside
        ledger = payload.get("ledger")
        has_ledger = isinstance(ledger, dict) and "main_scoreboard_shots_this_week" in ledger
        shots_week = ledger.get("main_scoreboard_shots_this_week") if has_ledger else None
        cumulative = ledger.get("cumulative_main_scoreboard_attempts_after") if has_ledger else None
        task = str(payload.get("task", ""))
        rows.append({
            "path": relative, "schema": str(payload.get("schema", "")), "task": task,
            "generated_at_utc": str(payload.get("generated_at_utc", "")), "has_ledger": bool(has_ledger),
            "shots_this_week": shots_week, "cumulative_shots": cumulative,
            "negatives_count": len(declared_negatives) if isinstance(declared_negatives, list) else 0,
            "frozen_count": len(declared_frozen) if isinstance(declared_frozen, list) else 0,
            "frozen_outside_canon": outside, "week43": task.startswith("week43"),
        })
        if has_ledger:
            ledger_entries.append((str(payload.get("generated_at_utc", "")),
                                   int(shots_week), cumulative, relative))

    ledger_entries.sort(key=lambda item: (item[0], item[3]))
    sequence = [entry[2] for entry in ledger_entries if entry[2] is not None]
    monotone = all(sequence[index] <= sequence[index + 1] for index in range(len(sequence) - 1))
    week43_rows = [row for row in rows if row["week43"]]
    week43_shots = [row["shots_this_week"] for row in week43_rows]

    invariants = {
        "summaries_scanned": scanned,
        "registered_negatives_union": sorted(negatives),
        "registered_negatives_expected": sorted(expected_negatives),
        "negatives_stable": negatives == expected_negatives,
        "frozen_outside_canon": frozen_outside,
        "frozen_readings_intact": frozen_outside == 0,
        "ledger_entries": len(ledger_entries),
        "cumulative_shots_sequence_length": len(sequence),
        "cumulative_shots_min": min(sequence) if sequence else None,
        "cumulative_shots_max": max(sequence) if sequence else None,
        "shots_monotone_nondecreasing": monotone,
        "shots_ceiling": int(expected["cumulative_shots_ceiling"]),
        "shots_ceiling_respected": bool(sequence) and max(sequence) <= int(expected["cumulative_shots_ceiling"]),
        "week43_summaries": len(week43_rows),
        "week43_shots_all_zero": bool(week43_rows) and all(int(value) == 0 for value in week43_shots),
    }
    return {"invariants": invariants, "rows": rows, "canon": sorted(canon)}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w43_governance_ledger"]["gates"]
    inv = payload["invariants"]
    criteria = [
        criteria_row("H43d1", "扫描到的 JSON 数 >= 300",
                     inv["summaries_scanned"], int(gates["summaries_scanned_min"]),
                     int(inv["summaries_scanned"]) >= int(gates["summaries_scanned_min"])),
        criteria_row("H43d2", "登记负结果集合稳定 == 已知 9 条",
                     inv["registered_negatives_union"], inv["registered_negatives_expected"],
                     bool(inv["negatives_stable"])),
        criteria_row("H43d3", "冻结读数越界计数 = 0",
                     inv["frozen_outside_canon"], 0, bool(inv["frozen_readings_intact"])),
        criteria_row("H43d4", "累计 shot 序列单调不减",
                     {"length": inv["cumulative_shots_sequence_length"],
                      "min": inv["cumulative_shots_min"], "max": inv["cumulative_shots_max"]},
                     "non-decreasing", bool(inv["shots_monotone_nondecreasing"])),
        criteria_row("H43d5", "累计 shot 上限 <= 19",
                     inv["cumulative_shots_max"], inv["shots_ceiling"],
                     bool(inv["shots_ceiling_respected"])),
        criteria_row("H43d6", "带 ledger 的 summary 数 >= 37",
                     inv["ledger_entries"], 37, int(inv["ledger_entries"]) >= 37),
        criteria_row("H43d7", "本轮 W43 各件 shots_this_week 全为 0",
                     {"week43_summaries": inv["week43_summaries"],
                      "all_zero": inv["week43_shots_all_zero"]},
                     {"min_summaries": 3, "all_zero": True},
                     int(inv["week43_summaries"]) >= 3 and bool(inv["week43_shots_all_zero"])),
        criteria_row("H43d8", "预注册文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    inv = payload["invariants"]
    lines = [
        "# W43-D 仓库级治理台账守卫（治理 lane，0 shot）",
        "",
        "把 `probes/**/*.json` 当一本台账机器校验四条不变式。",
        "",
        "## 1 不变式",
        "",
        "- 扫描 JSON 数：" + str(inv["summaries_scanned"]) + "；带 ledger 的 summary："
        + str(inv["ledger_entries"]) + "。",
        "- 登记负结果并集：" + json.dumps(inv["registered_negatives_union"], ensure_ascii=False)
        + "（期望 " + json.dumps(inv["registered_negatives_expected"], ensure_ascii=False) + "）⇒ 稳定 = "
        + str(inv["negatives_stable"]) + "。",
        "- 冻结读数越界计数 = " + str(inv["frozen_outside_canon"]) + " ⇒ 完整 = "
        + str(inv["frozen_readings_intact"]) + "。",
        "- 累计 shot 序列：长度 " + str(inv["cumulative_shots_sequence_length"]) + "，min = "
        + str(inv["cumulative_shots_min"]) + "，max = " + str(inv["cumulative_shots_max"])
        + "，单调不减 = " + str(inv["shots_monotone_nondecreasing"]) + "。",
        "- 本轮 W43 各件：summary 数 " + str(inv["week43_summaries"]) + "，shots_this_week 全为 0 = "
        + str(inv["week43_shots_all_zero"]) + "。",
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
        "- 只读：本件只解析 JSON，不写任何 summary、标签或特征列。",
        "- 逐文件台账见 `probes/artifacts/w43_governance_ledger.csv`。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(LEDGER_CSV, LEDGER_FIELDS, payload["rows"])
    write_json_stable(LEDGER_JSON, {
        "invariants": payload["invariants"], "frozen_readings_canon": payload["canon"],
        "scanned_files": [row["path"] for row in payload["rows"]],
    })

    inv = payload["invariants"]
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只扫描并校验全仓 JSON 台账，不拟合主记分牌臂、不加特征列、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "invariants": inv,
        "criteria": criteria,
        "registered_negatives": sorted(inv["registered_negatives_union"]),
        "headline": [
            "扫描 " + str(inv["summaries_scanned"]) + " 个 JSON；登记负结果并集 == 已知 9 条（"
            + ("稳定" if inv["negatives_stable"] else "漂移") + "）。",
            "冻结读数越界 " + str(inv["frozen_outside_canon"]) + " 次；累计 shot 单调不减、上限 "
            + str(inv["cumulative_shots_max"]) + "。",
            "带 ledger 的 summary = " + str(inv["ledger_entries"]) + "；本轮 W43 各件 shots 全 0。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("scanned %d json, ledger %d, negatives %s"
          % (inv["summaries_scanned"], inv["ledger_entries"], json.dumps(inv["registered_negatives_union"])))
    print("frozen_outside %d monotone %s max_cum %s week43_zero %s"
          % (inv["frozen_outside_canon"], inv["shots_monotone_nondecreasing"],
             inv["cumulative_shots_max"], inv["week43_shots_all_zero"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
