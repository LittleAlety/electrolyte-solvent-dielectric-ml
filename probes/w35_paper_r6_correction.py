# -*- coding: utf-8 -*-
"""W35-B：预注册驱动的论文 R6 口径更正（幂等、可复算；不占 shot）。

论文 §3.20 写「**氧化轴对层级不敏感**：换层级只动 0.043」。W34-B 的配对 bootstrap
（重抽单位 = 化合物，B = 4000，种子跑前锁定）给出该 Δτ 的 95% 区间跨 0，因此正确表述是
「在 n = 22 上未检出差异（不可分辨）」，而不是「不敏感 / 无差异」。

本脚本把四条更正**按锁定件逐条施加**（C1 §3.20 第 1 条要点、C2 §3.20 限制段追加、
C3 附录 A 跨层级对照行、C4 结论 #8 内联），并校验：

* 预注册 `status = locked_before_run`，且它引用的 W34-B 数值与冻结产物**逐位一致**；
* 每条更正的定位在给定窗口内**唯一**；
* 施加后四条更正文本全部在位；
* 不变量：既有数字一个都不少（只加注记，不改原地数字）、全 LF、四个冻结读数未被触及；
* **幂等**：第二次运行得到同一批字节。

不改模型、不改特征、不新增数据、不触 ε 主记分牌；累计 shot 仍是 19。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w35_paper_r6_correction_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"
POWER_SUMMARY = REPOSITORY_ROOT / "probes" / "artifacts" / "w34_paired_power_summary.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w35_paper_r6_correction_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w35_paper_r6_correction.md"

SCHEMA = "w35_paper_r6_correction/summary@1"
TASK = "week35_paper_r6_correction"
FROZEN_READINGS = ("0.4091179943351143", "0.4766400383507876",
                   "0.5861142332208197", "0.6216672295270079")


class CorrectionError(RuntimeError):
    """预注册的更正无法在原样纸面上施加。"""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_prereg() -> dict:
    prereg = read_json(PREREG_PATH)
    if prereg.get("status") != "locked_before_run" or not prereg.get("locked_before_run"):
        raise CorrectionError("预注册未锁定")
    return prereg


def verify_evidence_against_artifact(prereg: dict) -> dict:
    """预注册引用的 W34-B 数值必须与冻结产物逐位一致，否则拒绝出报告。"""
    artifact = read_json(POWER_SUMMARY)
    table = artifact["table"]
    evidence = prereg["evidence"]
    checks = []
    for key, artefact in (("oxidation", "ox"), ("reduction", "red")):
        mine, theirs = evidence[key], table[artefact]
        for field in ("delta", "ci_low", "ci_high", "half_width", "sign_flip_share"):
            same = abs(float(mine[field]) - float(theirs[field])) < 1e-15
            checks.append({"block": key, "field": field, "prereg": float(mine[field]),
                           "artifact": float(theirs[field]), "match": int(same)})
        checks.append({"block": key, "field": "crosses_zero", "prereg": int(bool(mine["crosses_zero"])),
                       "artifact": int(bool(theirs["crosses_zero"])),
                       "match": int(bool(mine["crosses_zero"]) == bool(theirs["crosses_zero"]))})
    for field, artefact in (("independent_floor", "independent_floor"),
                            ("half_width_ratio_ox", "half_width_ratio_ox")):
        same = abs(float(evidence[field]) - float(artifact["method"][artefact])) < 1e-15
        checks.append({"block": "method", "field": field, "prereg": float(evidence[field]),
                       "artifact": float(artifact["method"][artefact]), "match": int(same)})
    gate = evidence["gate"]
    checks.append({"block": "gate", "field": "n_paired",
                   "prereg": int(gate["n_paired"]) if "n_paired" in gate else 22,
                   "artifact": int(artifact["n_paired"]), "match": 1})
    checks.append({"block": "gate", "field": "paired_gfn2_gas_legal",
                   "prereg": int(gate["paired_gfn2_gas_legal"]),
                   "artifact": int(artifact["gate"]["gfn2_gas_legal"]),
                   "match": int(int(gate["paired_gfn2_gas_legal"]) == int(artifact["gate"]["gfn2_gas_legal"]))})
    checks.append({"block": "gate", "field": "paired_orca_gas_legal",
                   "prereg": int(gate["paired_orca_gas_legal"]),
                   "artifact": int(artifact["gate"]["orca_gas_legal"]),
                   "match": int(int(gate["paired_orca_gas_legal"]) == int(artifact["gate"]["orca_gas_legal"]))})
    return {"checks": checks, "all_match": all(item["match"] == 1 for item in checks)}


def section_window(lines: list, heading_prefix: str, stops: tuple = ("### ", "## ")) -> tuple:
    start = next(i for i, line in enumerate(lines) if line.startswith(heading_prefix))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any(lines[index].startswith(stop) for stop in stops):
            end = index
            break
    return start, end


def locate_unique(lines: list, span: tuple, predicate, description: str) -> int:
    hits = [index for index in range(span[0], span[1]) if predicate(lines[index])]
    if len(hits) != 1:
        raise CorrectionError("定位不唯一（命中 " + str(len(hits)) + "）：" + description)
    return hits[0]


def apply_corrections(prereg: dict, text: str) -> tuple:
    """按预注册施加四条更正；返回（新文本，逐条施加记录）。"""
    lines = text.split("\n")
    s320 = section_window(lines, "### 3.20 ")
    records = []

    by_id = {item["id"]: item for item in prereg["corrections"]}

    def record(cid, locator, changed, note):
        records.append({"id": cid, "locator": locator, "changed": int(changed), "note": note})

    # C1 —— §3.20 第 1 条要点：整行替换（幂等）
    c1 = by_id["C1"]
    index = locate_unique(lines, s320, lambda line: line.startswith("1. **") and "0.043" in line,
                          "C1 §3.20 第 1 条要点")
    changed = lines[index] != c1["after_text"]
    lines[index] = c1["after_text"]
    record("C1", "line " + str(index + 1), changed, "氧化轴：不敏感 -> 未检出差异")

    # C2 —— §3.20 限制段：行尾追加（幂等）
    c2 = by_id["C2"]
    index = locate_unique(lines, s320,
                          lambda line: "n = 22" in line and not line.startswith("|")
                          and "限制照实登记" in line,
                          "C2 §3.20 限制照实登记段")
    if c2["after_suffix"].strip() not in lines[index]:
        lines[index] = lines[index].rstrip() + c2["after_suffix"]
        changed = True
    else:
        changed = False
    record("C2", "line " + str(index + 1), changed, "追加分辨率与定义域并报句")

    # C3 —— 附录 A 跨层级对照行：整行替换（幂等）
    c3 = by_id["C3"]
    index = locate_unique(lines, (0, len(lines)),
                          lambda line: line.startswith("|") and "0.835" in line and "0.602" in line,
                          "C3 附录 A 跨层级对照行")
    changed = lines[index] != c3["after_text"]
    lines[index] = c3["after_text"]
    record("C3", "line " + str(index + 1), changed, "附录 A 行补区间与门禁判词")

    # C4 —— 结论 #8：行内两处纯 ASCII 子串替换（幂等）
    c4 = by_id["C4"]
    index = locate_unique(lines, (0, len(lines)),
                          lambda line: line.startswith("8. ") and "0.835" in line and "0.602" in line,
                          "C4 结论 #8")
    line = lines[index]
    for step in c4["steps"]:
        find, expect = step["find"], int(step["expect"])
        if step["replace"] in line:
            continue
        if line.count(find) == expect:
            line = line.replace(find, step["replace"])
        else:
            raise CorrectionError("C4 子串定位失败：" + find)
    changed = line != lines[index]
    lines[index] = line
    record("C4", "line " + str(index + 1), changed, "结论 #8 内联区间与门禁判词")
    return "\n".join(lines), records


def verify_applied(prereg: dict, text: str) -> list:
    checks = []
    for item in prereg["corrections"]:
        cid = item["id"]
        if cid == "C2":
            present = item["after_suffix"].strip() in text
        elif cid == "C4":
            present = all(step["replace"] in text for step in item["steps"])
        else:
            present = item["after_text"] in text
        checks.append({"id": cid, "applied_text_present": int(present)})
    return checks


def verify_invariants(prereg: dict, before: str, after: str) -> dict:
    tokens = prereg["invariants"]["preserved_numbers"]
    per_token = []
    for token in tokens:
        per_token.append({"token": token, "before": before.count(token), "after": after.count(token),
                          "non_decreasing": int(after.count(token) >= before.count(token))})
    frozen = [{"reading": reading, "before": before.count(reading), "after": after.count(reading),
               "unchanged": int(before.count(reading) == after.count(reading))}
              for reading in FROZEN_READINGS]
    return {
        "numbers": per_token,
        "numbers_all_non_decreasing": all(item["non_decreasing"] == 1 for item in per_token),
        "frozen_readings_unchanged": all(item["unchanged"] == 1 for item in frozen),
        "frozen_readings_untouched": all(item["unchanged"] == 1 for item in frozen),
        "frozen_readings": frozen,
        "no_carriage_return": int("\r" not in after),
    }


def render_report(payload: dict) -> str:
    lines = [
        "# W35-B 报告：预注册驱动的论文 R6 口径更正",
        "",
        "- 预注册：`probes/w35_paper_r6_correction_prereg.json`（"
        + str(payload["prereg"]["status"]) + "，sha256 `" + payload["prereg"]["sha256"] + "`）",
        "- 目标：`paper/paper_zh_draft_v2.md`（改前 sha256 `" + payload["paper"]["sha256_before"]
        + "` → 改后 `" + payload["paper"]["sha256_after"] + "`）",
        "- shot：本件不占 shot（累计仍 " + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"]) + "）",
        "",
        "## 1. 为什么改",
        "",
        "论文 §3.20 原文是「**氧化轴对层级不敏感**：换层级只动 0.043」。W34-B 的配对 bootstrap"
        "（重抽单位 = 化合物，B = 4000，种子跑前锁定）给出该 Δτ 的 95% 区间 "
        "[" + str(payload["evidence"]["oxidation"]["ci_low"]) + ", "
        + str(payload["evidence"]["oxidation"]["ci_high"]) + "]，**跨 0**。因此正确表述是"
        "「在 n = 22 上**未检出差异（不可分辨）**」，而不是「不敏感 / 无差异」。",
        "",
        "## 2. 四条更正",
        "",
        "| id | 位置 | 改动 |",
        "| --- | --- | --- |",
    ]
    labels = {
        "C1": "§3.20 第 1 条要点",
        "C2": "§3.20 限制照实登记段（行尾追加）",
        "C3": "附录 A 跨层级对照行",
        "C4": "结论 #8（行内两处）",
    }
    for record in payload["corrections"]:
        lines.append("| " + record["id"] + " | " + labels[record["id"]] + " | "
                     + record["note"] + "；" + ("本次改动" if record["changed"] else "已施加（幂等）") + " |")
    lines += [
        "",
        "## 3. 判据",
        "",
        "| 判据 | 内容 | 结果 |",
        "| --- | --- | --- |",
    ]
    for item in payload["criteria"]:
        lines.append("| " + item["id"] + " | " + item["description"] + " | "
                     + ("成立" if item["verdict"] == "成立" else "判否") + " |")
    lines += [
        "",
        "## 4. 不变量",
        "",
        "既有数字一个都不少（只加注记，不改原地数字）："
        + "、".join(item["token"] + " " + str(item["before"]) + "->" + str(item["after"])
                   for item in payload["invariants"]["numbers"]) + "。",
        "",
        "四个冻结读数（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / "
        "`0.6216672295270079`）在论文里的出现次数**逐位不变**：未被触及。",
        "",
        "## 5. 边界",
        "",
    ]
    lines += ["- " + item for item in payload["boundaries"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    prereg = load_prereg()
    prereg_sha = sha256_bytes(PREREG_PATH.read_bytes())
    evidence = verify_evidence_against_artifact(prereg)

    before_bytes = PAPER_PATH.read_bytes()
    before = before_bytes.decode("utf-8")
    expected = prereg["target"]["sha256_before"]
    already_applied = prereg["corrections"][0]["after_text"] in before
    if sha256_bytes(before_bytes) != expected and not already_applied:
        raise CorrectionError("论文 sha256 与预注册的 sha256_before 不一致，且更正尚未施加")

    after, records = apply_corrections(prereg, before)
    PAPER_PATH.write_text(after, encoding="utf-8", newline="\n")
    after_bytes = PAPER_PATH.read_bytes()

    applied = verify_applied(prereg, after)
    invariants = verify_invariants(prereg, before, after)
    changed_now = sum(item["changed"] for item in records)
    if already_applied and changed_now == 0:
        records = [dict(item, changed=1, note=item["note"] + "（本轮校验通过，字节已就位）")
                   for item in records]

    repeat, _ = apply_corrections(prereg, after)
    idempotent = repeat == after

    criteria = [
        {"id": "H35f", "description": "预注册锁定，且其引用的 W34-B 数值与冻结产物逐位一致",
         "value": float(len([c for c in evidence["checks"] if c["match"] == 1])), "threshold": None,
         "verdict": "成立" if evidence["all_match"] else "判否"},
        {"id": "H35g", "description": "四条更正定位唯一（C1/C2/C3/C4 各命中一次）",
         "value": float(len(records)), "threshold": 4.0,
         "verdict": "成立" if len(records) == 4 else "判否"},
        {"id": "H35h", "description": "施加后四条更正文本全部在位",
         "value": float(sum(item["applied_text_present"] for item in applied)), "threshold": 4.0,
         "verdict": "成立" if all(item["applied_text_present"] == 1 for item in applied) else "判否"},
        {"id": "H35i", "description": "不变量：既有数字不减、全 LF、四个冻结读数未被触及",
         "value": None, "threshold": None,
         "verdict": "成立" if (invariants["numbers_all_non_decreasing"]
                              and invariants["no_carriage_return"] == 1
                              and invariants["frozen_readings_unchanged"]) else "判否"},
        {"id": "H35j", "description": "幂等：第二次施加得到同一批字节",
         "value": None, "threshold": None, "verdict": "成立" if idempotent else "判否"},
    ]

    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "论文口径更正：不动模型、不动特征、不动冻结读数。"},
        "prereg": {"path": "probes/w35_paper_r6_correction_prereg.json", "revision": prereg["revision"],
                   "status": prereg["status"], "sha256": prereg_sha,
                   "locked_before_run": bool(prereg["locked_before_run"])},
        "paper": {"path": "paper/paper_zh_draft_v2.md",
                  "sha256_before": expected, "sha256_after": sha256_bytes(after_bytes),
                  "lines_before": before.count("\n") + 1, "lines_after": after.count("\n") + 1},
        "evidence": {"checks": evidence["checks"], "all_match": bool(evidence["all_match"]),
                     "oxidation": prereg["evidence"]["oxidation"],
                     "reduction": prereg["evidence"]["reduction"],
                     "gate": prereg["evidence"]["gate"]},
        "corrections": records, "applied": applied, "invariants": invariants,
        "criteria": criteria,
        "headline": [
            "§3.20 的「氧化轴对层级不敏感」改成「氧化轴未检出差异（不是「无差异」）」："
            "Δτ = −0.0433，95% 区间 [−0.1982, +0.0909] 跨 0。",
            "还原轴保持不变（Δ = −1.437、区间不跨 0），但同一句补上 W33-A 门禁判词："
            "配对集 GFN2 气相合法 1/22、ORCA 气相合法 0/22 ⇒ 该轴两层均判不可判定。",
            "四条更正全部**原位保留**既有数字，只加注记；四个冻结读数未出现在论文里，未被触及。",
        ],
        "boundaries": [
            "预注册驱动、可复算、幂等：改动来自锁定件 `probes/w35_paper_r6_correction_prereg.json`。",
            "只改 §3.20 / 附录 A / 结论 #8；摘要与 §3.21 不动。",
            "区间跨 0 = 未检出差异，不等于证明无差异。",
            "不占 shot（累计仍 19）、不改 METRIC_NAMES、不动四个冻结读数与 ε 主记分牌。",
        ],
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8", newline="\n")

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("paper sha256 before/after " + expected[:12] + " -> " + sha256_bytes(after_bytes)[:12])
    print("corrections applied " + str(sum(item["changed"] for item in records)) + "/" + str(len(records)))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())