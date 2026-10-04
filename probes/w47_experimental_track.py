# -*- coding: utf-8 -*-
"""W47-B：实验还原轨候选的逐件裁定与台账（只读，0 shot）。

W47 计划把 Moshkovich 2001 当实验还原系列候选。取件核实（reports/w47_literature_verdict.md）后：
它只有 PC 一种溶剂、窗口值在 CV 图里而无溶剂×盐表，**不能当锚点行**。本件把它重分类为
「阳离子依赖机理证据」，并把实验还原轨的每一条候选源逐件裁定进台账（含不可得件），
避免用一个被误分类的源冒充锚点，也避免空结果被静默吞掉。

三条护栏：
  * 每行必须有非空 condition_flag（条件差异是本轮的登记重点）；
  * 核心集实验还原覆盖 1/7 < 5 ⇒ 实验轨登记 not_evaluable_condition_differs；
  * Ue 1997（JES 144, 2684）的还原侧是否含值仍是开着的欠账，登记为 pending_source_retrieval。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w47_experimental_track.py
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_experimental_track_prereg.json"
VERDICT_REPORT_PATH = REPOSITORY_ROOT / "reports" / "w47_literature_verdict.md"
ANCHOR_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_anchor_prereg.json"
LEDGER_CSV = ARTIFACTS / "w47_experimental_ledger.csv"
SUMMARY_PATH = ARTIFACTS / "w47_experimental_track_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w47_experimental_track.md"

SCHEMA = "w47_experimental_track/summary@1"
TASK = "week47_experimental_track"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEDGER_FIELDS = ("item_id", "source", "citation", "axis", "solvent_scope", "verdict",
                 "condition_flag", "evidence", "note")

LEDGER_ROWS: tuple[dict[str, str], ...] = (
    {
        "item_id": "moshkovich2001", "source": "Moshkovich, Gofer & Aurbach 2001",
        "citation": "J. Electrochem. Soc. 148, A295 (10.1149/1.1357316)",
        "axis": "reduction", "solvent_scope": "PC (single solvent)",
        "verdict": "mechanism_evidence_only",
        "condition_flag": "CONDITION_DIFFERS_LI_DEPOSITION",
        "evidence": "C:/Users/Little Alety/Downloads/moshkovich2001.pdf (677701 B, "
                    "da19bbc4ff841e9ea8a3fe9f81c194ae3e0ffc412a256b503c9d96bcf1638e0d)",
        "note": "PC 单溶剂 x LiClO4/NaClO4/KClO4，Au 电极；窗口值在 CV 图里、无溶剂 x 盐表；"
                "只作 D2 的阳离子依赖敏感性检验对象，不作 Gate 1 主检验替换。",
    },
    {
        "item_id": "ue1997", "source": "Ue 1997", "citation": "J. Electrochem. Soc. 144, 2684 (Borodin2013 TC3 ref53)",
        "axis": "oxidation", "solvent_scope": "EC/PC/EMC/DMC (single solvent rows)",
        "verdict": "anchor_candidate_pending_source",
        "condition_flag": "CONDITION_MATCH_UNVERIFIED",
        "evidence": "data/external/w47_borodin2013_table3_experimental_oxidation.csv 脚注 a / ref53",
        "note": "已证含氧化侧（同 5 mV/s + 1 mA/cm^2 判据）；**还原侧是否含值待取原件核实**（open item）。",
    },
    {
        "item_id": "okoshi2015", "source": "Okoshi 2015", "citation": "via Borodin2013 Table 3 notes",
        "axis": "oxidation", "solvent_scope": "EC / EMC",
        "verdict": "not_available_on_disk", "condition_flag": "CONDITION_MATCH_UNVERIFIED",
        "evidence": "data/external/w47_borodin2013_table3_experimental_oxidation.csv notes 列交叉核对",
        "note": "EC 6.5 vs Ue 6.2、EMC 7.0 vs Ue 6.7（各差 0.3 V）；条件差异已登记，未取原件。",
    },
    {
        "item_id": "ue1994", "source": "Ue 1994", "citation": "via Borodin2013 Table 3 notes",
        "axis": "oxidation", "solvent_scope": "PC",
        "verdict": "not_available_on_disk", "condition_flag": "CONDITION_MATCH_UNVERIFIED",
        "evidence": "data/external/w47_borodin2013_table3_experimental_oxidation.csv notes 列",
        "note": "原表 PC = +3.65 V vs SCE（约 6.93 vs Li），与 Borodin2013 转录 6.6 差 0.33 V。",
    },
    {
        "item_id": "borodin2013_table1", "source": "Borodin, Behl & Jow 2013 Table 1",
        "citation": "J. Phys. Chem. C 117, 8661-8682 (10.1021/jp400527c)",
        "axis": "oxidation", "solvent_scope": "16 rows / 14 solvents (computed)",
        "verdict": "rejected_computed_only", "condition_flag": "NOT_APPLICABLE_SINGLE_SOLVENT",
        "evidence": "data/external/w47_borodin2013_table1_computed_oxidation.csv (16 rows, "
                    "0c2809df482fa4e6ef44e194f9511ce99e62a5d8c86cc1586769d30b2b4fb86f)",
        "note": "G4MP2/PCM 计算氧化表；**不是实验还原锚点**，不得补造还原侧。",
    },
    {
        "item_id": "borodin2013_table3", "source": "Borodin, Behl & Jow 2013 Table 3",
        "citation": "J. Phys. Chem. C 117, 8661-8682 (10.1021/jp400527c)",
        "axis": "oxidation", "solvent_scope": "26 rows (experimental)",
        "verdict": "rejected_criterion_mismatch", "condition_flag": "NOT_APPLICABLE_SINGLE_SOLVENT",
        "evidence": "data/external/w47_borodin2013_table3_experimental_oxidation.csv (26 rows, "
                    "14e4978fb133594d03ac8b1f9fa4eb57487622b2791d7f1f4a8ae49d7c71b28b)",
        "note": "轴不匹配：全表为**氧化**极限，无还原列；只作氧化轴锚点，不作还原轨锚点。",
    },
    {
        "item_id": "borodin2015_fig6_7_8", "source": "Borodin et al. 2015 fig. 6/7/8",
        "citation": "Nanotechnology 26, 354003 (10.1088/0957-4484/26/35/354003)",
        "axis": "reduction", "solvent_scope": "EC / DMC / FEC (computed, Li+ coupled)",
        "verdict": "rejected_computed_only", "condition_flag": "NOT_APPLICABLE_SINGLE_SOLVENT",
        "evidence": "data/external/w47_borodin2015_li_coupled_reduction.csv (8 rows, "
                    "5792c3f5376b303419a28d38a5303b6dd4d16e89ba6e4fbca21585b8d3961739)",
        "note": "Li+ 耦合**计算**还原；给 D2 定义性先例（EC/Li+ 0.48/0.53/0.61 V，构象敏感性约 0.13 V），"
                "但**不能当实验锚点**。",
    },
    {
        "item_id": "borodin2019_conversion", "source": "Borodin et al. 2019",
        "citation": "vs Li/Li+ 换算链（offset 1.4 V，+/-0.17 V 不确定）",
        "axis": "reduction", "solvent_scope": "n/a (conversion convention)",
        "verdict": "rejected_computed_only", "condition_flag": "NOT_APPLICABLE_SINGLE_SOLVENT",
        "evidence": "reports/w47_literature_verdict.md 覆盖核算一节",
        "note": "只提供标度换算口径，不是可测系列；eps 1->20 平均压低 Delta Ga 2.05 V 亦记在案。",
    },
    {
        "item_id": "doe_apr_fy2016", "source": "DOE APR FY2016 secondary values",
        "citation": "FEC 1.2 / VC 0.74 / EC 0.7 V（secondary，n_pairs = 3）",
        "axis": "reduction", "solvent_scope": "FEC / VC / EC",
        "verdict": "not_available_on_disk", "condition_flag": "CONDITION_MATCH_UNVERIFIED",
        "evidence": "probes/artifacts/w46_reduction_anchor_ledger.csv（W46-B 侦察件）",
        "note": "secondary 汇编值，n_pairs = 3 且核心集内仅 EC；离盘、未取原件。",
    },
)

OPEN_ITEM = {
    "id": "Ue1997_reduction_side",
    "description": "Ue 1997 (JES 144, 2684) 是否含还原侧需取原件核实；取件优先级最高。",
    "status": "pending_source_retrieval",
}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w47-B prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    vocabulary = [str(v) for v in prereg["verdict_vocabulary"]]
    flags = [str(v) for v in prereg["condition_registration"]["values"]]
    rows = [dict(row) for row in LEDGER_ROWS]
    verdicts = sorted({row["verdict"] for row in rows})
    flag_values = sorted({row["condition_flag"] for row in rows})
    coverage = dict(prereg["coverage"])
    exp_members = [str(s) for s in prereg["coverage"]["experimental_reduction_members"]]
    evaluable = len(exp_members) >= int(coverage["min_core_anchors"])
    return {
        "rows": rows,
        "n_items": len(rows),
        "verdicts_used": verdicts,
        "verdicts_outside_vocabulary": [v for v in verdicts if v not in vocabulary],
        "verdict_vocabulary": vocabulary,
        "flags_used": flag_values,
        "flags_outside_vocabulary": [f for f in flag_values if f not in flags],
        "condition_flag_vocabulary": flags,
        "rows_missing_condition_flag": [row["item_id"] for row in rows if not str(row["condition_flag"]).strip()],
        "experimental_reduction_members": exp_members,
        "core_set_size": int(coverage["core_set_size"]),
        "min_core_anchors": int(coverage["min_core_anchors"]),
        "evaluable": evaluable,
        "experimental_track_verdict": ("evaluable" if evaluable else "not_evaluable_condition_differs"),
        "sensitivity_only_object": "moshkovich2001",
        "not_available_items": [row["item_id"] for row in rows if row["verdict"] == "not_available_on_disk"],
        "rejected_computed_only_items": [row["item_id"] for row in rows
                                         if row["verdict"] == "rejected_computed_only"],
        "open_item": dict(OPEN_ITEM),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        criteria_row("H47b1", "实验轨台账逐件给出 verdict，且每行 condition_flag 非空",
                     {"n_items": payload["n_items"], "missing": payload["rows_missing_condition_flag"]},
                     {"missing": []}, not payload["rows_missing_condition_flag"]),
        criteria_row("H47b2", "Moshkovich 2001 重分类为 mechanism_evidence_only（PC 单溶剂，非锚点行）",
                     {"sensitivity_only_object": payload["sensitivity_only_object"],
                      "verdict": [r["verdict"] for r in payload["rows"] if r["item_id"] == "moshkovich2001"]},
                     {"verdict": "mechanism_evidence_only"},
                     [r["verdict"] for r in payload["rows"] if r["item_id"] == "moshkovich2001"] == ["mechanism_evidence_only"]),
        criteria_row("H47b3", "核心集实验还原覆盖 1/7 < 5 ⇒ 实验轨登记 not_evaluable_condition_differs",
                     {"experimental_reduction_members": payload["experimental_reduction_members"],
                      "min_core_anchors": payload["min_core_anchors"],
                      "experimental_track_verdict": payload["experimental_track_verdict"]},
                     {"verdict": "not_evaluable_condition_differs"},
                     payload["experimental_track_verdict"] == "not_evaluable_condition_differs"),
        criteria_row("H47b4", "空结果/不可得件逐件登记（not_available_on_disk 至少 1 件）",
                     {"not_available_items": payload["not_available_items"]},
                     {"min_items": 1}, len(payload["not_available_items"]) >= 1),
        criteria_row("H47b5", "Ue1997_reduction_side 开项登记为 pending_source_retrieval",
                     payload["open_item"], {"status": "pending_source_retrieval"},
                     payload["open_item"]["status"] == "pending_source_retrieval"),
        criteria_row("H47b6", "verdict 与 condition_flag 取值都落在预注册词汇表内（封闭）",
                     {"verdicts": payload["verdicts_used"], "flags": payload["flags_used"]},
                     {"vocabularies_closed": True},
                     not payload["verdicts_outside_vocabulary"] and not payload["flags_outside_vocabulary"]),
        criteria_row("H47b7", "计算系列一律 rejected_computed_only（不得当实验锚点）",
                     {"rejected_computed_only_items": payload["rejected_computed_only_items"]},
                     {"min_items": 2}, len(payload["rejected_computed_only_items"]) >= 2),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W47-B 实验还原轨候选逐件裁定")
    add("")
    add("只读 lane，0 shot。取件核实后 Moshkovich 2001 降级为**机理证据**（PC 单溶剂、无溶剂 x 盐表），")
    add("实验还原轨核心集覆盖 1/7 < 5 ⇒ 登记 `not_evaluable_condition_differs`；计算系列一律不得当实验锚点。")
    add("")
    add("## 1 逐件台账（" + str(payload["n_items"]) + " 件）")
    add("")
    add("| id | 源 | 轴 | verdict | condition_flag |")
    add("| --- | --- | --- | --- | --- |")
    for row in payload["rows"]:
        add("| " + row["item_id"] + " | " + row["source"] + " | " + row["axis"] + " | "
            + row["verdict"] + " | " + row["condition_flag"] + " |")
    add("")
    add("## 2 覆盖与裁决")
    add("")
    add("- 核心集实验还原成员：" + " / ".join(payload["experimental_reduction_members"])
        + "（" + str(len(payload["experimental_reduction_members"])) + "/" + str(payload["core_set_size"])
        + "）；min_core_anchors = " + str(payload["min_core_anchors"]) + "。")
    add("- 实验轨裁决 = **" + payload["experimental_track_verdict"] + "**；只作 D2 的敏感性检验对象，不作 Gate 1 替换。")
    add("- 不可得件：" + "，".join(payload["not_available_items"]) + "；计算件（不得当锚点）："
        + "，".join(payload["rejected_computed_only_items"]) + "。")
    add("- 开项：" + payload["open_item"]["id"] + " -> " + payload["open_item"]["status"] + "。")
    add("")
    add("## 3 判据")
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
    sources = [PREREG_PATH, VERDICT_REPORT_PATH, ANCHOR_PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria.append(criteria_row(
        "H47b8", "输入（预注册 + 取件裁决报告 + Lane A 预注册）sha256 未变",
        {"inputs_unchanged": inputs_unchanged}, {"unchanged": True}, inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(LEDGER_CSV, LEDGER_FIELDS, payload["rows"])
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读逐件裁定与台账登记：不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "n_items": payload["n_items"],
            "verdicts_used": payload["verdicts_used"],
            "flags_used": payload["flags_used"],
            "experimental_reduction_members": payload["experimental_reduction_members"],
            "experimental_track_verdict": payload["experimental_track_verdict"],
            "evaluable": payload["evaluable"],
            "sensitivity_only_object": payload["sensitivity_only_object"],
            "not_available_items": payload["not_available_items"],
            "rejected_computed_only_items": payload["rejected_computed_only_items"],
            "open_item": payload["open_item"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "实验还原轨核心集覆盖 %d/%d < %d ⇒ not_evaluable_condition_differs（不阻塞计算轨）。"
                % (len(payload["experimental_reduction_members"]), payload["core_set_size"],
                   payload["min_core_anchors"]),
                "Moshkovich 2001 重分类为 mechanism_evidence_only；台账 %d 件全有 verdict + condition_flag。"
                % payload["n_items"],
                "Ue1997_reduction_side 仍 pending_source_retrieval（取件优先级最高）。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("items %d | verdict %s | flags %s | exp_track %s | open %s"
          % (payload["n_items"], payload["verdicts_used"], payload["flags_used"],
             payload["experimental_track_verdict"], payload["open_item"]["status"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
