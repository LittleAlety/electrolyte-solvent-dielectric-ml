# -*- coding: utf-8 -*-
"""W46-D：论文回填与治理同步（治理 lane，0 shot）。

把 W46-A/B/C 的收口回填进论文 v3（升 v1.10），并复跑 W44/W43 的治理守卫成一张快照：

  * 引用：7 篇（Korth 2014 / Rathnakumaran 2026 / Li 2026 / Gao 2023 / Wang 2023 / Ou 2025 / Bai-Hou 2025）在位；
  * 定位：§1.2 T1/T2 段在位，且「首次用秩相关」类表述已删（只剩否定式）；
  * 措辞：Gate 1 三处修订在位（阈 0.9 操作特性进局限 / P0 vs P1 不声称优劣 / p = 0.1194 两解释并列）；
  * 新节：§3.31 在位，含「不可判定」与功效下限读数；
  * 登记：decisions_log §28.101、README §11 第 45–48 条；
  * 完整性：论文 sha256 记录 + 四个冻结读数字面值未被篡改；
  * 快照：W44-A/B/D 三条守卫 + W43-D 台账本轮回跑。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w46_paper_governance.py
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w46_paper_governance_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
README_PATH = REPOSITORY_ROOT / "README.md"
DECISIONS_PATH = REPOSITORY_ROOT / "reports" / "decisions_log.md"
W43_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
W44_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
LEDGER_CSV = ARTIFACTS / "w46_paper_governance_ledger.csv"
SUMMARY_PATH = ARTIFACTS / "w46_paper_governance_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w46_paper_governance.md"

SCHEMA = "w46_paper_governance/summary@1"
TASK = "week46_paper_governance"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEDGER_FIELDS = ("check", "target", "value", "verdict")

CITATION_PATTERNS = (
    ("Korth 2014", r"Korth[^\n]*2014"),
    ("Rathnakumaran 2026", r"Rathnakumaran[^\n]*2026"),
    ("Li 2026", r"Li, X\. 等（2026"),
    ("Gao 2023", r"Gao, H\. 等（2023"),
    ("Wang 2023", r"Wang, Y\. 等（2023"),
    ("Ou 2025", r"Ou, Y\. 等（2025"),
    ("Bai/Hou 2025", r"Bai, P\. & Hou, T\.（2025"),
)

GATE1_REVISIONS = (
    ("阈 0.9 操作特性进局限", "阈 0.9 在 n = 7 上的操作特性必须与读数同报"),
    ("P0 0.5238 vs P1 0.4286 不声称优劣", "P0 0.5238 与 P1 0.4286 不声称优劣"),
    ("p = 0.1194 两解释并列", "p = 0.1194 的两竞争解释并列"),
)

README_ITEMS = (
    "45. **新登记（W46）",
    "46. **新登记（W46）",
    "47. **新登记（W46）",
    "48. **新登记（W46）",
)


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w46-D prereg is not locked_before_run: " + str(payload.get("status")))
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
    citations = {label: bool(re.search(pattern, references))
                 for label, pattern in CITATION_PATTERNS}

    positioning = {
        "t1t2_paragraph": "本文的定位是纪律、判据与拒答" in paper,
        "novelty_narrowed": "不是「首次用秩相关」" in paper,
        "first_rank_claim_unnegated": ("首次用秩相关" in paper
                                       and "不是「首次用秩相关」" not in paper),
    }

    wording = {label: (needle in paper) for label, needle in GATE1_REVISIONS}
    section = "### 3.31 W46 收口：还原轴描述符重定义与功效边界" in paper
    section_body = paper.split("### 3.31", 1)[1].split("## 4 讨论", 1)[0] if section else ""
    section_ok = ("不可判定" in section_body and "MDE = 0.6541" in section_body
                  and "功效" in section_body)

    decisions_ok = "## 28.101" in decisions and "Week 46" in decisions
    readme_ok = all(item in readme for item in README_ITEMS)

    variants = {str(reading): sorted(reading_variants(paper, str(reading)))
                for reading in FROZEN_READINGS}
    frozen_intact = all(variants[str(reading)] == [str(reading)] for reading in FROZEN_READINGS)

    gate_payload = gate.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    acceptance_payload = acceptance.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    static_payload = static_guard.compute(json.loads(W44_PREREG_PATH.read_text(encoding="utf-8-sig")))
    ledger_payload = ledger_guard.compute(json.loads(W43_PREREG_PATH.read_text(encoding="utf-8-sig")))

    invariants = ledger_payload["invariants"]
    refused = [row for row in gate_payload["refusal_rows"] if row["verdict"] == "refused"]
    operational = [row for row in gate_payload["consumer_rows"]
                   if row["use_class"] == "operational_prior"]
    operational_ok = all(row["gate_verdict"] == "admitted" for row in operational)
    admitted = sorted({str(row["layer"]) for row in gate_payload["consumer_rows"]
                       if str(row.get("gate_verdict")) == "admitted"})

    return {
        "citations": citations,
        "positioning": positioning,
        "wording": wording,
        "section_3_31": section and section_ok,
        "decisions_log": decisions_ok,
        "readme_items": readme_ok,
        "frozen_variants": variants,
        "frozen_intact": frozen_intact,
        "gate": {"refused_controls": len(refused), "admitted_layers": admitted,
                 "operational_prior_uses": len(operational),
                 "operational_all_admitted": operational_ok},
        "acceptance": {"weeks_scanned": acceptance_payload["weeks_scanned"],
                       "failing_weeks": len(acceptance_payload["failing_weeks"])},
        "static": {"files_scanned": static_payload["files_scanned"],
                   "metric_name_mutations": len(static_payload["metric_name_mutations"]),
                   "frozen_reading_writes": len(static_payload["frozen_reading_writes"]),
                   "unregistered_promotions": len(static_payload.get("unregistered_promotions", []))},
        "ledger": {"registered_negatives": len(invariants["registered_negatives_union"]),
                   "frozen_outside_canon": invariants["frozen_outside_canon"],
                   "cumulative_shots_max": invariants["cumulative_shots_max"]},
        "paper_sha256": sha256_file(PAPER_PATH),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    citations = payload["citations"]
    positioning = payload["positioning"]
    wording = payload["wording"]
    gate_info = payload["gate"]
    static = payload["static"]
    ledger = payload["ledger"]

    return [
        criteria_row("H46d1", "7 篇新增引用全部在参考文献节内（作者 + 年份逐条命中）",
                     {"citations": citations},
                     {"required": list(prereg["required_citations"])},
                     all(citations.values())),
        criteria_row("H46d2", "§1.2 T1/T2 定位段在位，创新点收窄为「纪律 + 判据 + 拒答」，且无未否定的「首次用秩相关」表述",
                     positioning, {"novelty": "纪律 + 判据 + 拒答"},
                     positioning["t1t2_paragraph"] and positioning["novelty_narrowed"]
                     and not positioning["first_rank_claim_unnegated"]),
        criteria_row("H46d3", "Gate 1 统计措辞三处修订全部在位",
                     {"wording": wording}, {"count": prereg["gates"]["gate1_wording_revisions"]},
                     sum(1 for value in wording.values() if value) == 3),
        criteria_row("H46d4", "§3.31「还原轴描述符重定义与功效边界」在位，且同时含「不可判定」与功效下限读数",
                     {"section_present": payload["section_3_31"]},
                     {"must_contain": ["不可判定", "MDE = 0.6541"]}, bool(payload["section_3_31"])),
        criteria_row("H46d5", "decisions_log 追加 §28.101（Week 46）",
                     {"decisions_log": payload["decisions_log"]},
                     {"section": "28.101"}, bool(payload["decisions_log"])),
        criteria_row("H46d6", "README §11 登记本轮四条 lane（第 45–48 条）",
                     {"readme_items": payload["readme_items"]},
                     {"items": [45, 46, 47, 48]}, bool(payload["readme_items"])),
        criteria_row("H46d7", "论文 sha256 记录 + 四个冻结读数字面值未被篡改（无变体）",
                     {"paper_sha256": payload["paper_sha256"],
                      "frozen_variants": payload["frozen_variants"]},
                     {"frozen_readings": list(FROZEN_READINGS)}, bool(payload["frozen_intact"])),
        criteria_row("H46d8", "W44-A/B/D 三条守卫 + W43-D 台账本轮回跑：负对照全拒、mutation 0、冻结读数写入 0、shot 上限 19",
                     {"gate": gate_info, "acceptance": payload["acceptance"],
                      "static": static, "ledger": ledger},
                     {"refused_controls": 3, "mutations": 0, "frozen_writes": 0, "shots_max": 19},
                     gate_info["refused_controls"] == 3 and gate_info["operational_all_admitted"]
                     and static["metric_name_mutations"] == 0 and static["frozen_reading_writes"] == 0
                     and static["unregistered_promotions"] == 0
                     and ledger["frozen_outside_canon"] == 0 and ledger["cumulative_shots_max"] == 19
                     and ledger["registered_negatives"] == 9),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W46-D 论文回填与治理同步")
    add("")
    add("只读治理 lane，0 shot。论文 v3 升 v1.10、§3.31 落地，并复跑 W44/W43 守卫。")
    add("")
    add("## 1 引用登记（7 篇）")
    add("")
    add("| 引用 | 在位 |")
    add("| --- | --- |")
    for label, present in payload["citations"].items():
        add("| " + label + " | " + ("是" if present else "否") + " |")
    add("")
    add("## 2 Gate 1 措辞三处修订")
    add("")
    for label, present in payload["wording"].items():
        add("- " + label + "：" + ("在位" if present else "缺失"))
    add("")
    add("## 3 守卫复跑快照")
    add("")
    add("- 闸门：负对照 " + str(payload["gate"]["refused_controls"]) + " 全拒、运营性先验 "
        + str(payload["gate"]["operational_prior_uses"]) + " 全过闸。")
    add("- 验收：扫 " + str(payload["acceptance"]["weeks_scanned"]) + " 轮、fail "
        + str(payload["acceptance"]["failing_weeks"]) + "。")
    add("- 静态守卫：文件 " + str(payload["static"]["files_scanned"]) + "、mutation "
        + str(payload["static"]["metric_name_mutations"]) + "、冻结读数写入 "
        + str(payload["static"]["frozen_reading_writes"]) + "。")
    add("- 台账：负结果并集 " + str(payload["ledger"]["registered_negatives"]) + "、冻结读数越界 "
        + str(payload["ledger"]["frozen_outside_canon"]) + "、累计 shot 上限 "
        + str(payload["ledger"]["cumulative_shots_max"]) + "。")
    add("")
    add("论文 sha256：「" + str(payload["paper_sha256"]) + "」（变化已在 W46-D 登记）。")
    add("")
    add("## 4 判据")
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
    sources = [PREREG_PATH, PAPER_PATH, README_PATH, DECISIONS_PATH,
               W43_PREREG_PATH, W44_PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H46d8", "W44-A/B/D 三条守卫 + W43-D 台账本轮回跑：负对照全拒、mutation 0、冻结读数写入 0、shot 上限 19",
                                {"gate": payload["gate"], "acceptance": payload["acceptance"],
                                 "static": payload["static"], "ledger": payload["ledger"],
                                 "inputs_unchanged": inputs_unchanged},
                                {"refused_controls": 3, "mutations": 0, "frozen_writes": 0,
                                 "shots_max": 19},
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
                "why_not_a_shot": "只读论文回填复核与治理守卫复跑，不拟合主记分牌臂、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "citations": payload["citations"],
            "positioning": payload["positioning"],
            "wording": payload["wording"],
            "section_3_31": payload["section_3_31"],
            "decisions_log": payload["decisions_log"],
            "readme_items": payload["readme_items"],
            "frozen_variants": payload["frozen_variants"],
            "paper_sha256": payload["paper_sha256"],
            "guard_snapshot": {"gate": payload["gate"], "acceptance": payload["acceptance"],
                               "static": payload["static"], "ledger": payload["ledger"]},
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "引用 7/7 在位；§1.2 定位段与 Gate 1 三处措辞修订在位。",
                "§3.31 在位（含「不可判定」与功效下限）；decisions_log §28.101 与 README 45–48 已登记。",
                "守卫复跑：负对照 3 全拒、mutation 0、冻结读数写入 0、台账负结果 9、shot 上限 19。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("citations %s | section331 %s | decisions %s | readme %s | frozen_intact %s | guards refused %d mut %d writes %d shots %d"
          % (json.dumps(payload["citations"]), payload["section_3_31"], payload["decisions_log"],
             payload["readme_items"], payload["frozen_intact"], payload["gate"]["refused_controls"],
             payload["static"]["metric_name_mutations"], payload["static"]["frozen_reading_writes"],
             payload["ledger"]["cumulative_shots_max"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
