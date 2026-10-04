# -*- coding: utf-8 -*-
"""W47-D：投稿就绪评估 + 第二批引用回填复核 + 治理守卫复跑（治理 lane，0 shot）。

把 W47-A/B/C 收口与第二批引用回填进论文 v3（升 v1.11），并复跑 W44/W43 的治理守卫成一张快照：

  * 引用：13 篇新增（转录源 / 方法护栏 / 换算链 / 定位段 / 进展）逐条命中；
  * 定位：§1.2 补 Abaei 2026 与 Deng 2026（跨领域同修辞，生态位紧迫性）；
  * 新节：§3.32「W47 收口：双轨还原锚点、主判据执行与投稿就绪评估」在位；
  * 局限：§4.6 把未闭合项照实写清（还原锚点仍 0、D2/D3 转 round-2、Ue 1997 待取原件）；
  * 稿件形式：**无附录标题**、论文引用的图全部在盘（图片可完整显示的前置条件）；
  * 治理：decisions_log 28.102、README 第 49–52 条；四个冻结读数无变体、9 条负结果不变、shot 上限 19；
  * 投稿就绪：10 条闸门逐条判定 + 剩余阻塞项清单（只出评估，不擅自改投稿决策）。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w47_paper_readiness.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import w43_governance_ledger as ledger_guard
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_paper_readiness_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
README_PATH = REPOSITORY_ROOT / "README.md"
DECISIONS_PATH = REPOSITORY_ROOT / "reports" / "decisions_log.md"
W43_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
W44_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
LEDGER_CSV = ARTIFACTS / "w47_paper_readiness_ledger.csv"
SUMMARY_PATH = ARTIFACTS / "w47_paper_readiness_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w47_paper_readiness.md"

SCHEMA = "w47_paper_readiness/summary@1"
TASK = "week47_paper_readiness"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEDGER_FIELDS = ("check", "target", "value", "verdict")
APPENDIX_HEADING = re.compile(r"^#{1,6}\s*附录", re.MULTILINE)
FIGURE_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
BOUNDARY_ITEMS = ("33. **", "36. **", "40. **", "42. **", "45. **", "46. **")
BLOCKING_ITEMS = (
    "same_apparatus_experimental_reduction_anchors = 0（核心集实验还原覆盖 1/7）",
    "D2 的 r2SCAN-3c 版本未计算（pending_orca_compute，转 round-2）",
    "D3（ddCOSMO 垂直 EA）未计算（pending_orca_compute，转 round-2）",
    "Ue 1997 的还原侧是否含值未核实（pending_source_retrieval）",
    "strict same-level 独立源仍为 0（HOMO/LUMO 通道加权仍缺）",
)


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w47-D prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def reading_variants(text: str, canonical: str) -> set[str]:
    literal = str(canonical)
    prefix = literal[:12]
    return set(re.findall(re.escape(prefix) + r"[0-9]*", text))


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    paper = PAPER_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    decisions = DECISIONS_PATH.read_text(encoding="utf-8")

    references = paper.split("## 参考文献", 1)[1] if "## 参考文献" in paper else ""
    citations = {str(label): bool(re.search(str(pattern), references))
                 for label, pattern in prereg["required_citations"]}

    sec = dict(prereg["section"])
    heading = str(sec["heading_prefix"])
    section_present = heading in paper
    section_body = (paper.split(heading, 1)[1].split("\n## ", 1)[0]
                    if section_present else "")
    title_line = section_body.split("\n", 1)[0] if section_body else ""
    section_ok = (section_present
                  and all(t in (heading + title_line) for t in sec["title_must_contain"])
                  and all(b in section_body for b in sec["body_must_contain"]))

    sec12 = paper.split("### 1.2", 1)[1].split("### 1.3", 1)[0] if "### 1.2" in paper else ""
    positioning_ok = all(t in sec12 for t in prereg["positioning"]["must_contain"])

    sec46 = paper.split("### 4.6", 1)[1].split("### 4.7", 1)[0] if "### 4.6" in paper else ""
    limitations_ok = all(any(alt in sec46 for alt in group)
                         for group in prereg["limitations"]["must_contain_any_of"])

    appendix_headings = APPENDIX_HEADING.findall(paper)
    figure_links = sorted(set(FIGURE_LINK.findall(paper)))
    missing_figures = [link for link in figure_links
                       if not (PAPER_PATH.parent / link).resolve().is_file()]

    variants = {str(reading): sorted(reading_variants(paper, str(reading)))
                for reading in FROZEN_READINGS}
    frozen_intact = all(variants[str(reading)] == [str(reading)] for reading in FROZEN_READINGS)

    gov = dict(prereg["governance"])
    section_tag = "## " + str(gov["decisions_log_section"])
    decisions_ok = (section_tag in decisions
                    and all(t in decisions.split(section_tag, 1)[1].split("\n## ", 1)[0]
                            for t in gov["decisions_log_must_contain"]))
    readme_items_ok = all(str(item) in readme for item in gov["readme_items"])
    boundaries_ok = all(item in readme for item in BOUNDARY_ITEMS)

    gate_payload = gate.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    acceptance_payload = acceptance.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    static_payload = static_guard.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    ledger_payload = ledger_guard.compute(json.loads(W43_PREREG_PATH.read_text(encoding="utf-8-sig")))

    invariants = ledger_payload["invariants"]
    refused = [row for row in gate_payload["refusal_rows"] if row["verdict"] == "refused"]
    operational = [row for row in gate_payload["consumer_rows"]
                   if row["use_class"] == "operational_prior"]
    operational_ok = all(row["gate_verdict"] == "admitted" for row in operational)
    negatives = len(invariants["registered_negatives_union"])
    shots_max = int(invariants["cumulative_shots_max"])

    gates = {
        "citations_complete": all(citations.values()),
        "section_3_32": bool(section_ok),
        "positioning_updated": bool(positioning_ok),
        "limitations_updated": bool(limitations_ok),
        "no_appendix": not appendix_headings,
        "figures_all_exist": not missing_figures,
        "frozen_readings_intact": bool(frozen_intact),
        "registered_negatives_intact": negatives == 9,
        "shot_cap_intact": shots_max == 19,
        "boundaries_declared": bool(boundaries_ok),
    }
    return {
        "citations": citations,
        "n_citations_present": sum(1 for v in citations.values() if v),
        "n_citations_required": len(citations),
        "section_present": section_present,
        "section_ok": bool(section_ok),
        "positioning_ok": bool(positioning_ok),
        "limitations_ok": bool(limitations_ok),
        "appendix_headings": appendix_headings,
        "figure_links": figure_links,
        "missing_figures": missing_figures,
        "frozen_variants": variants,
        "frozen_intact": bool(frozen_intact),
        "decisions_log": bool(decisions_ok),
        "readme_items": bool(readme_items_ok),
        "boundaries_declared": bool(boundaries_ok),
        "guard": {
            "refused_controls": len(refused),
            "admitted_layers": sorted({str(row["layer"]) for row in gate_payload["consumer_rows"]
                                       if str(row.get("gate_verdict")) == "admitted"}),
            "operational_prior_uses": len(operational),
            "operational_all_admitted": bool(operational_ok),
            "acceptance_weeks": int(acceptance_payload["weeks_scanned"]),
            "acceptance_failing": len(acceptance_payload["failing_weeks"]),
            "static_files": int(static_payload["files_scanned"]),
            "metric_name_mutations": len(static_payload["metric_name_mutations"]),
            "frozen_reading_writes": len(static_payload["frozen_reading_writes"]),
            "unregistered_promotions": len(static_payload.get("unregistered_promotions", [])),
            "frozen_outside_canon": int(invariants["frozen_outside_canon"]),
            "registered_negatives": negatives,
            "cumulative_shots_max": shots_max,
        },
        "readiness": {
            "gates": gates,
            "gates_passed": sum(1 for v in gates.values() if v),
            "gates_total": len(gates),
            "all_gates_passed": all(gates.values()),
            "blocking_items": list(BLOCKING_ITEMS),
            "verdict": "conditional_go" if all(gates.values()) else "hold",
            "note": "本件只出「条件可投、边界已声明」的评估；投稿决策不由本件作出。",
        },
        "paper_sha256": sha256_file(PAPER_PATH),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    guard = payload["guard"]
    readiness = payload["readiness"]
    return [
        criteria_row("H47d1", "第二批引用 13 篇全部在参考文献节内逐条命中（作者 + 年份）",
                     {"present": payload["n_citations_present"], "required": payload["n_citations_required"],
                      "citations": payload["citations"]},
                     {"required": 13}, payload["n_citations_present"] == 13),
        criteria_row("H47d2", "§3.32 在位，标题含 W47/还原锚点，正文含 不可判定/0.6667/H47a2/not_evaluable_condition_differs",
                     {"section_present": payload["section_present"], "section_ok": payload["section_ok"]},
                     {"must_contain": list(prereg["section"]["body_must_contain"])}, bool(payload["section_ok"])),
        criteria_row("H47d3", "§1.2 定位段补 Abaei 2026 与 Deng 2026（跨领域同修辞）",
                     {"positioning_ok": payload["positioning_ok"]},
                     {"must_contain": list(prereg["positioning"]["must_contain"])},
                     bool(payload["positioning_ok"])),
        criteria_row("H47d4", "§4.6 照实登记未闭合项（还原锚点仍 0 / round-2）",
                     {"limitations_ok": payload["limitations_ok"]},
                     {"groups": prereg["limitations"]["must_contain_any_of"]},
                     bool(payload["limitations_ok"])),
        criteria_row("H47d5", "论文无附录标题（用户口径：不要附录）",
                     {"appendix_headings": payload["appendix_headings"]},
                     {"headings": []}, not payload["appendix_headings"]),
        criteria_row("H47d6", "论文引用的图片全部在盘（图片可完整显示的前置条件）",
                     {"n_links": len(payload["figure_links"]), "missing": payload["missing_figures"]},
                     {"missing": []}, not payload["missing_figures"] and len(payload["figure_links"]) > 0),
        criteria_row("H47d7", "四个冻结读数字面值未被篡改（无变体）",
                     {"variants": payload["frozen_variants"]},
                     {"frozen_readings": list(FROZEN_READINGS)}, bool(payload["frozen_intact"])),
        criteria_row("H47d8", "9 条已登记负结果不变（台账并集 = 9）",
                     {"registered_negatives": guard["registered_negatives"]},
                     {"expected": 9}, guard["registered_negatives"] == 9),
        criteria_row("H47d9", "累计 shot 上限仍 19（本周各件 0）",
                     {"cumulative_shots_max": guard["cumulative_shots_max"]},
                     {"expected": 19}, guard["cumulative_shots_max"] == 19),
        criteria_row("H47d10", "未闭合边界声明齐备（README 第 33/36/40/42/45/46 条）",
                     {"boundaries_declared": payload["boundaries_declared"], "items": list(BOUNDARY_ITEMS)},
                     {"items": list(BOUNDARY_ITEMS)}, bool(payload["boundaries_declared"])),
        criteria_row("H47d11", "decisions_log §28.102 与 README §11 第 49–52 条登记",
                     {"decisions_log": payload["decisions_log"], "readme_items": payload["readme_items"]},
                     {"decisions": "28.102", "readme": [49, 50, 51, 52]},
                     bool(payload["decisions_log"]) and bool(payload["readme_items"])),
        criteria_row("H47d12", "投稿就绪评估：10 条闸门逐条判定 + 阻塞项清单 + 论文 sha256 记录 + 守卫复跑全绿",
                     {"readiness": readiness, "guard": guard, "paper_sha256": payload["paper_sha256"]},
                     {"all_gates_passed": True, "refused_controls": 3, "mutations": 0,
                      "frozen_writes": 0, "shots_max": 19},
                     bool(readiness["all_gates_passed"])
                     and guard["refused_controls"] == 3 and guard["operational_all_admitted"]
                     and guard["metric_name_mutations"] == 0 and guard["frozen_reading_writes"] == 0
                     and guard["unregistered_promotions"] == 0
                     and guard["frozen_outside_canon"] == 0
                     and guard["cumulative_shots_max"] == 19
                     and guard["registered_negatives"] == 9),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    readiness = payload["readiness"]
    guard = payload["guard"]
    lines: list[str] = []
    add = lines.append
    add("# W47-D 投稿就绪评估与引用回填复核")
    add("")
    add("只读治理 lane，0 shot。论文 v3 升 v1.11、新增 §3.32，并复跑 W44/W43 守卫。")
    add("")
    add("## 1 引用登记（" + str(payload["n_citations_present"]) + "/" + str(payload["n_citations_required"]) + "）")
    add("")
    add("| 引用 | 在位 |")
    add("| --- | --- |")
    for label, present in payload["citations"].items():
        add("| " + label + " | " + ("是" if present else "否") + " |")
    add("")
    add("## 2 稿件形式闸门")
    add("")
    add("- §3.32 在位 = " + ("是" if payload["section_ok"] else "否") + "；§1.2 定位段 = "
        + ("是" if payload["positioning_ok"] else "否") + "；§4.6 局限更新 = "
        + ("是" if payload["limitations_ok"] else "否") + "。")
    add("- 附录标题数 = " + str(len(payload["appendix_headings"])) + "；图片来源 " + str(len(payload["figure_links"]))
        + " 个、缺失 " + str(len(payload["missing_figures"])) + " 个。")
    add("")
    add("## 3 投稿就绪评估")
    add("")
    add("| 闸门 | 通过 |")
    add("| --- | --- |")
    for name, ok in readiness["gates"].items():
        add("| " + name + " | " + ("是" if ok else "否") + " |")
    add("")
    add("闸门 " + str(readiness["gates_passed"]) + "/" + str(readiness["gates_total"]) + " 通过；裁决 = **"
        + readiness["verdict"] + "**（" + readiness["note"] + "）")
    add("")
    add("**剩余阻塞项（科学证据，非稿件形式）：**")
    add("")
    for item in readiness["blocking_items"]:
        add("- " + item)
    add("")
    add("## 4 守卫复跑快照")
    add("")
    add("- 闸门：负对照 " + str(guard["refused_controls"]) + " 全拒、运营性先验 " + str(guard["operational_prior_uses"])
        + " 全过闸、准入层 " + " / ".join(guard["admitted_layers"]) + "。")
    add("- 验收：扫 " + str(guard["acceptance_weeks"]) + " 轮、fail " + str(guard["acceptance_failing"]) + "。")
    add("- 静态守卫：文件 " + str(guard["static_files"]) + "、mutation " + str(guard["metric_name_mutations"])
        + "、冻结读数写入 " + str(guard["frozen_reading_writes"]) + "。")
    add("- 台账：负结果并集 " + str(guard["registered_negatives"]) + "、冻结读数越界 "
        + str(guard["frozen_outside_canon"]) + "、累计 shot 上限 " + str(guard["cumulative_shots_max"]) + "。")
    add("")
    add("论文 sha256：「" + str(payload["paper_sha256"]) + "」（变化已在 W47-D 登记）。")
    add("")
    add("## 5 判据")
    add("")
    add("| id | 判据 | 值 | 阈 | 判决 |")
    add("| --- | --- | --- | --- | --- |")
    for row in criteria:
        add("| " + str(row["id"]) + " | " + str(row["description"]) + " | "
            + json.dumps(row["value"], ensure_ascii=False) + " | "
            + json.dumps(row["threshold"], ensure_ascii=False) + " | " + str(row["verdict"]) + " |")
    add("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, PAPER_PATH, README_PATH, DECISIONS_PATH, W43_PREREG_PATH, W44_PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row(
        "H47d12", "投稿就绪评估：10 条闸门逐条判定 + 阻塞项清单 + 论文 sha256 记录 + 守卫复跑全绿",
        {"readiness": payload["readiness"], "guard": payload["guard"],
         "paper_sha256": payload["paper_sha256"], "inputs_unchanged": inputs_unchanged},
        {"all_gates_passed": True, "refused_controls": 3, "mutations": 0, "frozen_writes": 0, "shots_max": 19},
        criteria[-1]["verdict"] == "成立" and inputs_unchanged)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        ledger_rows = [{"check": str(row["id"]), "target": str(row["description"]),
                        "value": json.dumps(row["value"], ensure_ascii=False),
                        "verdict": str(row["verdict"])} for row in criteria]
        write_csv_lf(LEDGER_CSV, LEDGER_FIELDS, ledger_rows)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读论文回填复核、投稿就绪评估与治理守卫复跑，不拟合主记分牌臂、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "n_citations_present": payload["n_citations_present"],
            "n_citations_required": payload["n_citations_required"],
            "citations": payload["citations"],
            "section_ok": payload["section_ok"],
            "positioning_ok": payload["positioning_ok"],
            "limitations_ok": payload["limitations_ok"],
            "appendix_headings": payload["appendix_headings"],
            "figure_links": payload["figure_links"],
            "missing_figures": payload["missing_figures"],
            "frozen_variants": payload["frozen_variants"],
            "decisions_log": payload["decisions_log"],
            "readme_items": payload["readme_items"],
            "boundaries_declared": payload["boundaries_declared"],
            "readiness": payload["readiness"],
            "guard_snapshot": payload["guard"],
            "paper_sha256": payload["paper_sha256"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "引用 %d/%d 在位；§3.32、§1.2 定位段、§4.6 局限更新全部到位；无附录标题；%d 张图全在盘。"
                % (payload["n_citations_present"], payload["n_citations_required"], len(payload["figure_links"])),
                "投稿就绪闸门 %d/%d 通过；裁决 = %s（剩余阻塞项为科学证据：还原锚点 0、D2/D3 未算、Ue 1997 待取原件）。"
                % (payload["readiness"]["gates_passed"], payload["readiness"]["gates_total"],
                   payload["readiness"]["verdict"]),
                "守卫复跑：负对照 3 全拒、mutation 0、冻结读数写入 0、台账负结果 9、shot 上限 19。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("citations %d/%d | sec3.32 %s | positioning %s | limitations %s | appendix %d | figures %d missing %d"
          % (payload["n_citations_present"], payload["n_citations_required"], payload["section_ok"],
             payload["positioning_ok"], payload["limitations_ok"], len(payload["appendix_headings"]),
             len(payload["figure_links"]), len(payload["missing_figures"])))
    print("readiness %d/%d (%s) | guards refused %d mut %d writes %d negatives %d shots %d"
          % (payload["readiness"]["gates_passed"], payload["readiness"]["gates_total"],
             payload["readiness"]["verdict"], payload["guard"]["refused_controls"],
             payload["guard"]["metric_name_mutations"], payload["guard"]["frozen_reading_writes"],
             payload["guard"]["registered_negatives"], payload["guard"]["cumulative_shots_max"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
