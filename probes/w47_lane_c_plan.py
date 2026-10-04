# -*- coding: utf-8 -*-
"""W47-C：D2 r2SCAN-3c 重算 + D3 ddCOSMO 新单点的协议锁定与欠账登记（只读，0 shot）。

本环境无 ORCA 可执行体，因此本件不产数值，只把 W46 登记的算力缺口锁成一份可执行的计划：
  * D2 (r2SCAN-3c)：[Li(M)]+ 垂直 Delta SCF；必须多构象采样并报构象散布（Borodin 2015 EC/Li+
    三个几何 0.48/0.53/0.61 V ⇒ 构象敏感性约 0.13 V，不许只报单一构象）。
  * D3 (ddCOSMO)：垂直用非平衡 NE、绝热用 EQ（V4 分工）；沿用 W26 ddCOSMO 管线。
  * 腈类（GN/MPN/BC）三项专项检查（Timerghazin 2008 偶极束缚态警告）：SOMO 空间分布、
    偶极束缚态判据、门禁注册表条目——缺一项即该溶剂的检查判据不成立。
  * 完成后按 w47_anchor_prereg.json **同一口径**重跑 Lane A（计划内复跑，不是前置依赖），
    两版读数并列登记。
  * dipole_transfer_v1 维持 registered_not_authorized，本轮不碰。

顺带给出一个可复算的算力估算（ORCA 单点数），作为排期依据——是**估算**，不是读数。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w47_lane_c_plan.py
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_orca_rerun_prereg.json"
ANCHOR_PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_anchor_prereg.json"
PLAN_CSV = ARTIFACTS / "w47_lane_c_plan.csv"
SUMMARY_PATH = ARTIFACTS / "w47_lane_c_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w47_lane_c_plan.md"

SCHEMA = "w47_orca_rerun/summary@1"
TASK = "week47_orca_rerun"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

PLAN_FIELDS = ("item_id", "group", "target", "requirement", "status", "evidence")
PENDING = "pending_orca_compute"

D2_ITEMS: tuple[tuple[str, str], ...] = (
    ("d2_definition", "definition", "[Li(M)]+ 垂直 Delta SCF 相对裸分子的位移"),
    ("d2_method", "method", "ORCA r2SCAN-3c RIJCOSX TightSCF"),
    ("d2_geometry", "geometry", "与 W24 阶梯同构（同一批分子、同一几何来源）"),
    ("d2_level", "level_declaration", "r2SCAN-3c（与 D0/D1 同层，可与 Lane A 主判据同层自比）"),
    ("d2_conformer_sampling", "conformer_sampling", "多构象采样：每分子 >= 3 个还原几何（Borodin 2015 先例）"),
    ("d2_conformer_report", "conformer_report", "必须报构象散布；不得只报单一构象（敏感度量级约 0.13 V）"),
)
D3_ITEMS: tuple[tuple[str, str], ...] = (
    ("d3_vertical", "vertical", "阴离子单点（非平衡 NE 溶剂化）- 中性单点"),
    ("d3_adiabatic", "adiabatic_component", "EQ 溶剂化弛豫（V4：垂直用 NE、绝热用 EQ）"),
    ("d3_dielectric_pipeline", "dielectric_pipeline", "沿用 W26 ddCOSMO 管线（冻结介电响应口径）"),
    ("d3_level", "level_declaration", "r2SCAN-3c"),
)
NITRILE_SOLVENTS = ("GN", "MPN", "BC")
NITRILE_ITEMS = ("somo_spatial_extent", "dipole_bound_state_test", "legality_registry_entry")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w47-C prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def plan_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item_id, target, requirement in D2_ITEMS:
        rows.append({"item_id": item_id, "group": "d2_r2scan3c", "target": target,
                     "requirement": requirement, "status": PENDING,
                     "evidence": "probes/w47_orca_rerun_prereg.json#protocol.d2_r2scan3c"})
    for item_id, target, requirement in D3_ITEMS:
        rows.append({"item_id": item_id, "group": "d3_ddcosmo", "target": target,
                     "requirement": requirement, "status": PENDING,
                     "evidence": "probes/w47_orca_rerun_prereg.json#protocol.d3_ddcosmo"})
    for solvent in NITRILE_SOLVENTS:
        for item in NITRILE_ITEMS:
            rows.append({"item_id": "nitrile_%s_%s" % (solvent, item), "group": "nitrile_check",
                         "target": solvent, "requirement": item, "status": PENDING,
                         "evidence": "probes/w47_orca_rerun_prereg.json#protocol.nitrile_check"})
    rows.append({"item_id": "rerun_lane_a", "group": "rerun", "target": "lane_a_main_judgment",
                 "requirement": "r2SCAN-3c 全层完成后按 w47_anchor_prereg.json 同一口径重跑；两版并列登记",
                 "status": "pending_after_orca_compute",
                 "evidence": "probes/w47_anchor_prereg.json"})
    rows.append({"item_id": "dipole_transfer_v1", "group": "external", "target": "dipole_transfer_v1",
                 "requirement": "维持 registered_not_authorized；本轮不碰、不授权任何修数",
                 "status": "registered_not_authorized",
                 "evidence": "reports/decisions_log.md W43-B 登记"})
    return rows


def orca_single_point_estimate(core_set_size: int) -> dict[str, object]:
    """按声明口径估算 ORCA 单点数（估算，不是读数）。"""
    conformers_min = 3
    d2 = core_set_size * 2 * conformers_min
    d3 = core_set_size * 4
    nitrile = len(NITRILE_SOLVENTS) * 2
    return {
        "basis": {"core_set_size": core_set_size, "conformers_min": conformers_min,
                  "nitrile_solvents": list(NITRILE_SOLVENTS)},
        "d2_r2scan3c": {"formula": "N_core * 2 * n_conformers", "value": d2},
        "d3_ddcosmo": {"formula": "N_core * 4 (NE/EQ x neutral/anion)", "value": d3},
        "nitrile_check": {"formula": "n_nitrile * 2", "value": nitrile},
        "total": d2 + d3 + nitrile,
        "disclaimer": "排期用估算，不是读数；实际单点数以完成后的 ORCA 日志计数为准。",
    }


def compute(prereg: Mapping[str, object], anchor_prereg: Mapping[str, object]) -> dict[str, object]:
    rows = plan_rows()
    groups = {
        "d2_r2scan3c": [r for r in rows if r["group"] == "d2_r2scan3c"],
        "d3_ddcosmo": [r for r in rows if r["group"] == "d3_ddcosmo"],
        "nitrile_check": [r for r in rows if r["group"] == "nitrile_check"],
        "rerun": [r for r in rows if r["group"] == "rerun"],
        "external": [r for r in rows if r["group"] == "external"],
    }
    nitrile_pairs = sorted({(r["target"], r["requirement"]) for r in groups["nitrile_check"]})
    expected_pairs = sorted((s, i) for s in NITRILE_SOLVENTS for i in NITRILE_ITEMS)
    compute_status = dict(prereg["compute_status"])
    return {
        "rows": rows,
        "groups": {k: len(v) for k, v in groups.items()},
        "protocol_groups": {"d2_r2scan3c": len(D2_ITEMS), "d3_ddcosmo": len(D3_ITEMS),
                            "nitrile_check": len(expected_pairs)},
        "nitrile_pairs": [list(p) for p in nitrile_pairs],
        "nitrile_pairs_expected": [list(p) for p in expected_pairs],
        "nitrile_complete": nitrile_pairs == expected_pairs,
        "statuses": sorted({r["status"] for r in rows}),
        "all_pending_or_declared": all(r["status"] in (PENDING, "pending_after_orca_compute",
                                                       "registered_not_authorized") for r in rows),
        "orca_available": bool(compute_status.get("orca_available")),
        "compute_status": compute_status,
        "conformer_report_required": bool(prereg["gates"]["conformer_report_required"]),
        "nitrile_items_required": int(prereg["gates"]["nitrile_items_required"]),
        "must_not_touch_dipole_transfer_v1": bool(prereg["gates"]["must_not_touch_dipole_transfer_v1"]),
        "dipole_transfer_rows": [r for r in groups["external"]],
        "estimate": orca_single_point_estimate(len(anchor_prereg["core_set"])),
        "core_set": [str(s) for s in anchor_prereg["core_set"]],
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    external = payload["dipole_transfer_rows"]
    return [
        criteria_row("H47c1", "D2 (r2SCAN-3c) 协议六项齐备（定义/方法/几何/层级/构象采样/构象散布）",
                     {"n": payload["groups"]["d2_r2scan3c"], "expected": len(D2_ITEMS)},
                     {"expected": len(D2_ITEMS)}, payload["groups"]["d2_r2scan3c"] == len(D2_ITEMS)),
        criteria_row("H47c2", "D3 (ddCOSMO) 协议四项齐备（垂直 NE / 绝热 EQ / 介电管线 / 层级）",
                     {"n": payload["groups"]["d3_ddcosmo"], "expected": len(D3_ITEMS)},
                     {"expected": len(D3_ITEMS)}, payload["groups"]["d3_ddcosmo"] == len(D3_ITEMS)),
        criteria_row("H47c3", "腈类三项 x 3 溶剂 = 9 行齐备（缺一项即该溶剂检查判据不成立）",
                     {"n": payload["groups"]["nitrile_check"], "pairs": payload["nitrile_pairs"],
                      "complete": payload["nitrile_complete"]},
                     {"expected_pairs": 9}, bool(payload["nitrile_complete"])
                     and payload["groups"]["nitrile_check"] == 9),
        criteria_row("H47c4", "计算可得性照实登记：orca_available = false、全部条目 pending/declared（不强建数值）",
                     {"orca_available": payload["orca_available"], "statuses": payload["statuses"],
                      "compute_status": payload["compute_status"]},
                     {"orca_available": False, "all_pending_or_declared": True},
                     payload["orca_available"] is False and bool(payload["all_pending_or_declared"])),
        criteria_row("H47c5", "D2 构象散布必须报（conformer_report_required = true，敏感度量级约 0.13 V）",
                     {"conformer_report_required": payload["conformer_report_required"]},
                     {"required": True}, bool(payload["conformer_report_required"])),
        criteria_row("H47c6", "计划内复跑登记：r2SCAN-3c 全层后按同一预注册重跑 Lane A，两版并列",
                     {"rerun_rows": [r for r in payload["rows"] if r["group"] == "rerun"]},
                     {"status": "pending_after_orca_compute"},
                     any(r["group"] == "rerun" and r["status"] == "pending_after_orca_compute"
                         for r in payload["rows"])),
        criteria_row("H47c7", "dipole_transfer_v1 维持 registered_not_authorized（本轮不碰、不授权修数）",
                     {"rows": external}, {"status": "registered_not_authorized"},
                     len(external) == 1 and external[0]["status"] == "registered_not_authorized"
                     and bool(payload["must_not_touch_dipole_transfer_v1"])),
        criteria_row("H47c8", "算力估算可复算（公式 + 值），且标注为估算而非读数",
                     payload["estimate"], {"total_reported": True},
                     int(payload["estimate"]["total"]) > 0
                     and "估算" in str(payload["estimate"]["disclaimer"])),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W47-C Lane C 协议锁定与算力欠账登记")
    add("")
    add("只读 lane，0 shot。本环境无 ORCA，本件只锁协议、登记欠账、给排期估算，不产数值。")
    add("")
    add("## 1 计划条目（" + str(len(payload["rows"])) + " 项）")
    add("")
    add("| id | 组 | 目标 | 状态 |")
    add("| --- | --- | --- | --- |")
    for row in payload["rows"]:
        add("| " + row["item_id"] + " | " + row["group"] + " | " + row["target"] + " | " + row["status"] + " |")
    add("")
    add("## 2 腈类专项（V4：Timerghazin 2008 偶极束缚态警告）")
    add("")
    add("- 溶剂 x 项 = " + str(len(payload["nitrile_pairs"])) + " / 9；齐备 = "
        + ("是" if payload["nitrile_complete"] else "否") + "。")
    add("- 三项分别为 " + " / ".join("GN/MPN/BC".split("/")) + " 的 somo_spatial_extent、dipole_bound_state_test、legality_registry_entry。")
    add("")
    add("## 3 算力估算（排期用，不是读数）")
    add("")
    add("- D2：" + payload["estimate"]["d2_r2scan3c"]["formula"] + " = " + str(payload["estimate"]["d2_r2scan3c"]["value"]) + "。")
    add("- D3：" + payload["estimate"]["d3_ddcosmo"]["formula"] + " = " + str(payload["estimate"]["d3_ddcosmo"]["value"]) + "。")
    add("- 腈类：" + payload["estimate"]["nitrile_check"]["formula"] + " = " + str(payload["estimate"]["nitrile_check"]["value"]) + "。")
    add("- 合计 = **" + str(payload["estimate"]["total"]) + "** 个 ORCA 单点（估算）。")
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
    anchor_prereg = json.loads(ANCHOR_PREREG_PATH.read_text(encoding="utf-8-sig"))
    sources = [PREREG_PATH, ANCHOR_PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg, anchor_prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria.append(criteria_row(
        "H47c9", "输入（Lane C 预注册 + Lane A 预注册）sha256 未变",
        {"inputs_unchanged": inputs_unchanged}, {"unchanged": True}, inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(PLAN_CSV, PLAN_FIELDS, payload["rows"])
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读协议锁定与欠账登记：不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "n_items": len(payload["rows"]),
            "groups": payload["groups"],
            "nitrile_pairs": payload["nitrile_pairs"],
            "nitrile_complete": payload["nitrile_complete"],
            "statuses": payload["statuses"],
            "orca_available": payload["orca_available"],
            "compute_status": payload["compute_status"],
            "conformer_report_required": payload["conformer_report_required"],
            "estimate": payload["estimate"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "D2 六项 + D3 四项协议齐备；腈类 3 溶剂 x 3 项 = 9 行齐备（缺一即判据不成立）。",
                "orca_available = false ⇒ 全部条目 pending_orca_compute，按计划内复跑口径登记（不阻塞 Lane A）。",
                "算力估算合计 %d 个 ORCA 单点（排期用，不是读数）。" % int(payload["estimate"]["total"]),
                "dipole_transfer_v1 维持 registered_not_authorized；0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("items %d | groups %s | nitrile %s | statuses %s | estimate %d"
          % (len(payload["rows"]), payload["groups"], payload["nitrile_complete"],
             payload["statuses"], int(payload["estimate"]["total"])))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
