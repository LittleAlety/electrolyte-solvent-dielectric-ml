# -*- coding: utf-8 -*-
"""W45-D：把 W44 接进机器的三条治理守卫 + 台账在本轮复跑成一张快照（治理 lane，0 shot）。

W44-A/B/D 定义了三条守卫（准入闸门、逐轮验收、AST 静态守卫），W43-D 定义了台账不变式。它们此前
只在各自那一轮跑过。本件把它们在 W45 本轮一次性复跑，并把关键读数收成一张表：
  * 闸门：`admit_prior` 的拒绝集合与运营性先验使用；
  * 验收：扫交付摘要的轮数 / 声明数 / fail 数 / 最近五轮 / 台账不变式；
  * 静态守卫：文件数 / 解析错误 / mutation / 冻结读数写入 / 未登记晋升；
  * 台账：登记负结果并集、冻结读数越界、累计 shot 上限；
  * 交叉一致性：闸门判决表与 W43 准入表判决表逐项一致；
  * 本轮自检：W45 各件 shots_this_week 全为 0。

只读；不写任何既有 summary；累计 shot 仍是 19。

Run:
    .venv/Scripts/python.exe probes/w45_governance_rerun.py
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
import w44_acceptance_runner as acceptance
import w44_prior_gate as gate
import w44_static_shot_guard as static_guard
from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w45_compute_prereg.json"
W43_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
W44_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
GUARDS_CSV = ARTIFACTS / "w45_governance_rerun.csv"
SUMMARY_PATH = ARTIFACTS / "w45_governance_rerun_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w45_governance_rerun.md"

SCHEMA = "w45_governance_rerun/summary@1"
TASK = "week45_governance_rerun"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

GUARD_FIELDS = ("guard", "metric", "value")
EXPECTED_VERDICTS = {"xtb": "defer", "qm9": "defer", "pubchemqc": "admit", "batt": "reject"}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w45 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    w43_prereg = json.loads(W43_PREREG_PATH.read_text(encoding="utf-8-sig"))
    w44_prereg = json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig"))

    gate_payload = gate.compute(w44_prereg)
    acceptance_payload = acceptance.compute(w44_prereg)
    static_payload = static_guard.compute(w44_prereg)
    ledger_payload = ledger.compute(w43_prereg)
    invariants = ledger_payload["invariants"]

    refused = [row for row in gate_payload["refusal_rows"] if row["verdict"] == "refused"]
    operational = [row for row in gate_payload["consumer_rows"]
                   if row["use_class"] == "operational_prior"]
    operational_ok = all(row["gate_verdict"] == "admitted" for row in operational)

    week45_shots: dict[str, int] = {}
    for path in sorted(ARTIFACTS.glob("w45_*_summary.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        shots = (payload.get("ledger") or {}).get("main_scoreboard_shots_this_week")
        week45_shots[path.name] = int(shots) if shots is not None else -1

    rows: list[dict[str, object]] = [
        {"guard": "gate", "metric": "refused_controls", "value": len(refused)},
        {"guard": "gate", "metric": "admitted_positive", "value": gate_payload["positive_control"].get("pubchemqc")},
        {"guard": "gate", "metric": "undeclared_prior_uses", "value": len(gate_payload["undeclared"])},
        {"guard": "gate", "metric": "operational_prior_uses", "value": len(operational)},
        {"guard": "acceptance", "metric": "weeks_scanned", "value": acceptance_payload["weeks_scanned"]},
        {"guard": "acceptance", "metric": "declared_weeks", "value": acceptance_payload["declared_weeks"]},
        {"guard": "acceptance", "metric": "failing_weeks", "value": len(acceptance_payload["failing_weeks"])},
        {"guard": "acceptance", "metric": "recent_all_pass", "value": acceptance_payload["recent_all_pass"]},
        {"guard": "static", "metric": "files_scanned", "value": static_payload["files_scanned"]},
        {"guard": "static", "metric": "parse_errors", "value": len(static_payload["parse_errors"])},
        {"guard": "static", "metric": "metric_name_mutations", "value": len(static_payload["metric_name_mutations"])},
        {"guard": "static", "metric": "frozen_reading_writes", "value": len(static_payload["frozen_reading_writes"])},
        {"guard": "static", "metric": "unregistered_promotions", "value": len(static_payload["unregistered_promotions"])},
        {"guard": "ledger", "metric": "summaries_scanned", "value": invariants["summaries_scanned"]},
        {"guard": "ledger", "metric": "registered_negatives", "value": len(invariants["registered_negatives_union"])},
        {"guard": "ledger", "metric": "frozen_outside_canon", "value": invariants["frozen_outside_canon"]},
        {"guard": "ledger", "metric": "cumulative_shots_max", "value": invariants["cumulative_shots_max"]},
    ]

    return {
        "gate": gate_payload,
        "acceptance": acceptance_payload,
        "static": static_payload,
        "invariants": invariants,
        "refused_controls": len(refused),
        "operational_prior_uses": len(operational),
        "operational_all_admitted": bool(operational_ok),
        "week45_shots": week45_shots,
        "rows": rows,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w45_governance_rerun"]["gates"]
    gate_payload = payload["gate"]
    acceptance_payload = payload["acceptance"]
    static_payload = payload["static"]
    invariants = payload["invariants"]
    verdicts_match = gate_payload["admission_verdicts"] == EXPECTED_VERDICTS
    return [
        criteria_row("H45d1", "准入闸门：3 个负对照被拒、PubChemQC 过闸、未申报 0、运营性全过闸",
                     {"refused": payload["refused_controls"],
                      "positive": gate_payload["positive_control"],
                      "undeclared": len(gate_payload["undeclared"]),
                      "operational_uses": payload["operational_prior_uses"],
                      "operational_all_admitted": payload["operational_all_admitted"]},
                     {"refused": gates["refused_controls"], "undeclared_max": gates["undeclared_prior_uses_max"]},
                     int(payload["refused_controls"]) == int(gates["refused_controls"])
                     and gate_payload["positive_control"].get("pubchemqc") == "admitted"
                     and len(gate_payload["undeclared"]) <= int(gates["undeclared_prior_uses_max"])
                     and bool(payload["operational_all_admitted"])),
        criteria_row("H45d2", "逐轮验收：轮数 >= 40、fail 0、最近五轮全过、台账不变式成立",
                     {"weeks": acceptance_payload["weeks_scanned"],
                      "declared": acceptance_payload["declared_weeks"],
                      "failing": len(acceptance_payload["failing_weeks"]),
                      "recent_all_pass": acceptance_payload["recent_all_pass"],
                      "invariants_hold": acceptance_payload["invariants_hold"]},
                     {"weeks_min": gates["weeks_scanned_min"], "failing_max": gates["failing_weeks_max"]},
                     int(acceptance_payload["weeks_scanned"]) >= int(gates["weeks_scanned_min"])
                     and len(acceptance_payload["failing_weeks"]) <= int(gates["failing_weeks_max"])
                     and bool(acceptance_payload["recent_all_pass"])
                     and bool(acceptance_payload["invariants_hold"])),
        criteria_row("H45d3", "AST 静态守卫：文件 >= 350、解析错误 0、mutation 0、冻结读数写入 0、未登记晋升 0",
                     {"files": static_payload["files_scanned"],
                      "parse_errors": len(static_payload["parse_errors"]),
                      "mutations": len(static_payload["metric_name_mutations"]),
                      "writes": len(static_payload["frozen_reading_writes"]),
                      "promotions": len(static_payload["unregistered_promotions"])},
                     {"files_min": gates["static_files_min"]},
                     int(static_payload["files_scanned"]) >= int(gates["static_files_min"])
                     and static_payload["parse_errors"] == []
                     and len(static_payload["metric_name_mutations"]) <= int(gates["metric_name_mutations_max"])
                     and len(static_payload["frozen_reading_writes"]) <= int(gates["frozen_reading_writes_max"])
                     and len(static_payload["unregistered_promotions"]) <= int(gates["unregistered_promotions_max"])),
        criteria_row("H45d4", "台账：登记负结果并集 == 9、冻结读数越界 0、累计 shot 上限 19",
                     {"negatives": len(invariants["registered_negatives_union"]),
                      "negatives_stable": invariants["negatives_stable"],
                      "frozen_outside_canon": invariants["frozen_outside_canon"],
                      "frozen_intact": invariants["frozen_readings_intact"],
                      "shots_max": invariants["cumulative_shots_max"]},
                     {"negatives": gates["registered_negatives_expected"], "shot_cap": gates["cumulative_shot_cap"]},
                     len(invariants["registered_negatives_union"]) == int(gates["registered_negatives_expected"])
                     and bool(invariants["negatives_stable"])
                     and int(invariants["frozen_outside_canon"]) == 0
                     and bool(invariants["frozen_readings_intact"])
                     and int(invariants["cumulative_shots_max"]) <= int(gates["cumulative_shot_cap"])),
        criteria_row("H45d5", "交叉一致性：闸门判决表 == W43 准入表（xtb defer / qm9 defer / pubchemqc admit / batt reject）",
                     gate_payload["admission_verdicts"], EXPECTED_VERDICTS, bool(verdicts_match)),
        criteria_row("H45d6", "本轮自检：W45 各件 shots_this_week 全为 0",
                     payload["week45_shots"], {"all_zero": True},
                     len(payload["week45_shots"]) >= 3
                     and all(int(value) == 0 for value in payload["week45_shots"].values())),
        criteria_row("H45d7", "输入（W43/W44/W45 预注册 + 三条守卫探针）sha256 未变", "before == after", True, True),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W45-D 三条治理守卫 + 台账的本轮复跑快照",
        "",
        "只读治理 lane；0 shot。把 W44 接进机器的守卫在 W45 再跑一遍。",
        "",
        "## 1 守卫读数",
        "",
        "| guard | metric | value |",
        "| --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append("| " + str(row["guard"]) + " | " + str(row["metric"]) + " | "
                     + str(row["value"]) + " |")
    lines += [
        "",
        "- 本轮 W45 各件 shots： " + json.dumps(payload["week45_shots"], ensure_ascii=False) + "。",
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
        "- 只读：不写任何既有 summary，不重跑轮次导出。",
        "- 早期轮次缺字段记为 not_declared，不算 fail；轮数随交付推进只增不减。",
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
    sources = [PREREG_PATH, W43_PREREG_PATH, W44_PREREG_PATH,
               REPOSITORY_ROOT / "probes" / "w44_prior_gate.py",
               REPOSITORY_ROOT / "probes" / "w44_acceptance_runner.py",
               REPOSITORY_ROOT / "probes" / "w44_static_shot_guard.py"]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H45d7", "输入（W43/W44/W45 预注册 + 三条守卫探针）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(GUARDS_CSV, GUARD_FIELDS, payload["rows"])
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只复跑三条只读守卫与台账，不拟合主记分牌臂、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "guard_rows": payload["rows"],
            "week45_shots": payload["week45_shots"],
            "refused_controls": payload["refused_controls"],
            "operational_prior_uses": payload["operational_prior_uses"],
            "invariants": payload["invariants"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "闸门：负对照 " + str(payload["refused_controls"]) + " 全被拒、PubChemQC 过闸、未申报 0、运营性先验 "
                + str(payload["operational_prior_uses"]) + "（全过闸）。",
                "验收：扫 " + str(payload["acceptance"]["weeks_scanned"]) + " 轮、fail "
                + str(len(payload["acceptance"]["failing_weeks"])) + "、最近五轮全过。",
                "静态守卫：扫 " + str(payload["static"]["files_scanned"]) + " 文件、mutation "
                + str(len(payload["static"]["metric_name_mutations"])) + "、冻结读数写入 "
                + str(len(payload["static"]["frozen_reading_writes"])) + "。",
                "台账：负结果并集 " + str(len(payload["invariants"]["registered_negatives_union"]))
                + " 条、冻结读数越界 " + str(payload["invariants"]["frozen_outside_canon"])
                + "、累计 shot 上限 " + str(payload["invariants"]["cumulative_shots_max"]) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("gate refused %d operational %d | acceptance weeks %d failing %d | static files %d mut %d writes %d | ledger negatives %d shots %d"
          % (payload["refused_controls"], payload["operational_prior_uses"],
             payload["acceptance"]["weeks_scanned"], len(payload["acceptance"]["failing_weeks"]),
             payload["static"]["files_scanned"], len(payload["static"]["metric_name_mutations"]),
             len(payload["static"]["frozen_reading_writes"]),
             len(payload["invariants"]["registered_negatives_union"]),
             payload["invariants"]["cumulative_shots_max"]))
    print("week45 shots %s" % json.dumps(payload["week45_shots"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
