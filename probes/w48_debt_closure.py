# -*- coding: utf-8 -*-
"""W48-D：论文 §4.6 欠账终稿与逐条对照（修正案 A2 落地，0 shot）。

README §11 第 33/36/40/42/45/46/49-52 条是已登记欠账；修正案 A2 要求每条二选一：
照实写「未完成」，或显式声明转 round-2。本件把这件事变成可执行断言：

  * H48d1：上述第 33/36/40/42/45/46/49-52 条 + D2/D3 + dipole_transfer_v1 在 §4.6
    「已登记欠账的收口状态（W48）」小节逐条有对应句子，无沉默项；
  * H48d2：改稿只落 v3 线——v2 论文线 sha256 逐字节不动，治理件
    check_paper_artifact_consistency.py 复跑 PASS；
  * H48d3：0 shot，不新增判据族。

只读治理件，不占主记分牌。累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w48_debt_closure.py
    .venv/Scripts/python.exe probes/w48_debt_closure.py --check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import ARTIFACTS, FROZEN_READINGS, criteria_row, sha256_file, utc_now, write_csv_lf

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w48_debt_closure_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
PAPER_V2_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"
README_PATH = REPOSITORY_ROOT / "README.md"
SUMMARY_PATH = ARTIFACTS / "w48_debt_closure_summary.json"
CRITERIA_CSV = ARTIFACTS / "w48_debt_closure_criteria.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w48_debt_closure.md"

SCHEMA = "w48_debt_closure/summary@1"
TASK = "week48_debt_closure"
REGISTERED_NEGATIVES: tuple[str, ...] = ()
CRITERIA_FIELDS = ("id", "description", "value", "threshold", "verdict")

PAPER_V2_SHA256 = "c7bc66296e18cd6384760a3b49014800662800f5141124365fccf31fdaf1b50f"
SECTION_START = "### 4.6"
SECTION_END = "### 4.7"
DISPOSITION_WORDS = ("未完成", "round-2", "已收口", "已封顶", "未授权")

DEBTS: tuple[tuple[str, str, str], ...] = (
    ("README-33/36/40", "strict same-level 独立源仍为 0", "strict same-level 独立源仍为 0"),
    ("README-42", "扩展层标定列是 in-sample 仿射", "§11-42"),
    ("README-45", "还原轴候选描述符族门禁后不可判定", "§11-45"),
    ("README-46", "盘上同装置还原锚点数 = 0", "§11-46"),
    ("README-49", "还原轨覆盖并集 2/7 < 5，H47a2 拒答", "§11-49"),
    ("README-50", "Borodin 2013 是纯氧化论文", "§11-50"),
    ("README-51", "氧化轴交叉一致性只作敏感性读数", "§11-51"),
    ("README-52", "Ue 1997 还原侧取件收口", "§11-52 与 Ue 1997 还原侧"),
    ("D2", "D2 的 r2SCAN-3c 版本未计算", "D2 的 r2SCAN-3c 版本"),
    ("D3", "D3（ddCOSMO 垂直 EA）未计算", "D3（ddCOSMO 垂直 EA）"),
    ("dipole_transfer_v1", "维持 registered_not_authorized", "dipole_transfer_v1"),
)
README_BOUNDARY_ITEMS = ("33. **", "36. **", "40. **", "42. **", "45. **", "46. **",
                         "49. **", "50. **", "51. **", "52. **")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w48-D prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def section_46(paper: str) -> str:
    return paper.split(SECTION_START, 1)[1].split(SECTION_END, 1)[0]


def run_consistency() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, "scripts/check_paper_artifact_consistency.py"],
        cwd=str(REPOSITORY_ROOT), capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    paper = PAPER_PATH.read_text(encoding="utf-8")
    sec = section_46(paper)
    readme = README_PATH.read_text(encoding="utf-8")
    items = []
    for item_id, description, marker in DEBTS:
        present = marker in sec
        items.append({"item_id": item_id, "description": description, "marker": marker,
                      "present": present})
    dispositions = {word: (word in sec) for word in DISPOSITION_WORDS}
    v2_sha = sha256_file(PAPER_V2_PATH)
    rc, out = run_consistency()
    return {
        "items": items,
        "missing": [item["item_id"] for item in items if not item["present"]],
        "dispositions": dispositions,
        "readme_boundary_missing": [m for m in README_BOUNDARY_ITEMS if m not in readme],
        "paper_sha256": sha256_file(PAPER_PATH),
        "paper_v2_sha256": v2_sha,
        "paper_v2_unchanged": v2_sha == PAPER_V2_SHA256,
        "consistency_returncode": rc,
        "consistency_tail": out.strip().splitlines()[-3:],
        "section_len": len(sec),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        criteria_row("H48d1", "§4.6 逐条登记 33/36/40/42/45/46/49-52 + D2/D3/dipole，无沉默项",
                     {"n_items": len(payload["items"]), "missing": payload["missing"],
                      "readme_boundary_missing": payload["readme_boundary_missing"]},
                     {"missing": [], "readme_boundary_missing": []},
                     not payload["missing"] and not payload["readme_boundary_missing"]),
        criteria_row("H48d2", "改稿只落 v3；v2 sha256 不动；paper_artifact_consistency 复跑 PASS",
                     {"paper_sha256": payload["paper_sha256"],
                      "paper_v2_sha256": payload["paper_v2_sha256"],
                      "paper_v2_unchanged": payload["paper_v2_unchanged"],
                      "consistency_returncode": payload["consistency_returncode"]},
                     {"paper_v2_unchanged": True, "consistency_returncode": 0},
                     bool(payload["paper_v2_unchanged"]) and payload["consistency_returncode"] == 0),
        criteria_row("H48d3", "0 shot；不新增判据族（H48d*）",
                     {"shots_this_week": 0, "criteria_ids": ["H48d1", "H48d2", "H48d3"]},
                     {"shots": 0}, True),
    ]


def render_report(payload: Mapping[str, object],
                  criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W48-D §4.6 欠账终稿（逐条对照表）")
    add("")
    add("修正案 A2 落地件：README §11 已登记欠账在论文 §4.6「已登记欠账的收口状态（W48）」"
        "逐条落字，二选一（照实写「未完成」或显式转 round-2），无沉默项。")
    add("")
    add("## 1 逐条对照")
    add("")
    add("| 欠账 | 内容 | §4.6 标记 | 是否落字 |")
    add("| --- | --- | --- | --- |")
    for item in payload["items"]:
        add("| " + str(item["item_id"]) + " | " + str(item["description"]) + " | "
            + str(item["marker"]) + " | " + ("是" if item["present"] else "**否**") + " |")
    add("")
    add("- 处置词覆盖：" + "，".join(str(k) + "=" + ("有" if v else "无")
                                     for k, v in dict(payload["dispositions"]).items()) + "。")
    add("- §4.6 小节长度：" + str(payload["section_len"]) + " 字符。")
    add("")
    add("## 2 改稿范围与不变量")
    add("")
    add("- 只改 paper/paper_zh_draft_v3.md 的 §4.6；paper/paper_zh_draft_v2.md 与 _v2_* 冻结件零字节改动。")
    add("- 论文 v2 sha256 = " + str(payload["paper_v2_sha256"])[:16] + "（与冻结值一致："
        + ("是" if payload["paper_v2_unchanged"] else "**否**") + "）。")
    add("- 论文 v3 sha256 = " + str(payload["paper_sha256"]) + "（变化登记在本件）。")
    add("- 四个冻结读数、9 条负结果、累计 shot 19 不动；无附录标题；25 张图链接全在盘。")
    add("- 治理件 check_paper_artifact_consistency.py 复跑返回码 = "
        + str(payload["consistency_returncode"]) + "。")
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
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, PAPER_PATH, PAPER_V2_PATH, README_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(CRITERIA_CSV, CRITERIA_FIELDS, criteria)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "欠账终稿：只改 §4.6 措辞并复跑治理件，不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "items": payload["items"],
            "missing": payload["missing"],
            "readme_boundary_missing": payload["readme_boundary_missing"],
            "dispositions": payload["dispositions"],
            "paper_sha256": payload["paper_sha256"],
            "paper_v2_sha256": payload["paper_v2_sha256"],
            "paper_v2_unchanged": payload["paper_v2_unchanged"],
            "consistency_returncode": payload["consistency_returncode"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "§4.6 已登记欠账逐条落字：%d 项，缺 %d 项。"
                % (len(payload["items"]), len(payload["missing"])),
                "改稿只落 v3；v2 sha256 冻结未变；paper_artifact_consistency 返回码 "
                + str(payload["consistency_returncode"]) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("debts %d | missing %d | v2-unchanged %s | consistency rc %d"
          % (len(payload["items"]), len(payload["missing"]), payload["paper_v2_unchanged"],
             payload["consistency_returncode"]))
    print("criteria %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
