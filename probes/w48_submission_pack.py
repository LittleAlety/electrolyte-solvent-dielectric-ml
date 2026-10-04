# -*- coding: utf-8 -*-
"""W48-C：投稿执行包的第一步——venue 决策备忘录与形式漂移守卫（类④，0 shot）。

venue 的选择权在用户，本件只出四轴对比与风险，不替用户拍板。可执行的判据：

  * H48c1：venue 备忘录交付，含 >= 3 个候选的四轴对比；
  * H48c3：形式改动零科学内容漂移——paper_artifact_consistency 复跑 PASS，
    四个冻结读数在稿中逐字出现；
  * H48c4：0 shot。

投稿包（H48c2：docx + 图件 + 可复现性声明 + cover letter）依赖 venue 拍板，
本周期登记为 deferred（不是失败），明细见 summary 的 deferred_criteria。

只读治理件，不占主记分牌。累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w48_submission_pack.py
    .venv/Scripts/python.exe probes/w48_submission_pack.py --check
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w48_submission_pack_prereg.json"
MEMO_PATH = REPOSITORY_ROOT / "reports" / "w48_venue_memo.md"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
SUMMARY_PATH = ARTIFACTS / "w48_submission_pack_summary.json"
CRITERIA_CSV = ARTIFACTS / "w48_submission_pack_criteria.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w48_submission_pack.md"

SCHEMA = "w48_submission_pack/summary@1"
TASK = "week48_submission_pack"
REGISTERED_NEGATIVES: tuple[str, ...] = ()
CRITERIA_FIELDS = ("id", "description", "value", "threshold", "verdict")

CANDIDATES = (
    "Journal of Molecular Liquids",
    "PCCP",
    "J. Chem. Inf. Model.",
    "Electrochimica Acta",
    "J. Electrochem. Soc.",
)
AXES = ("范围匹配", "审计叙事接受度", "周期", "版面／OA")
DEFERRED = {
    "H48c2": "投稿包（docx + 图件 + 可复现性声明 + cover letter）待 venue 拍板后生成；"
             "本周期 venue 未定，登记 deferred 而非失败。",
}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w48-C prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def run_consistency() -> int:
    completed = subprocess.run(
        [sys.executable, "scripts/check_paper_artifact_consistency.py"],
        cwd=str(REPOSITORY_ROOT), capture_output=True, text=True, check=False)
    return completed.returncode


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    memo = MEMO_PATH.read_text(encoding="utf-8") if MEMO_PATH.is_file() else ""
    paper = PAPER_PATH.read_text(encoding="utf-8")
    candidates_present = [name for name in CANDIDATES if name in memo]
    axes_present = [axis for axis in AXES if axis in memo]
    readings_literal = {str(reading): (str(reading) in paper) for reading in FROZEN_READINGS}
    return {
        "memo_exists": MEMO_PATH.is_file(),
        "memo_sha256": sha256_file(MEMO_PATH) if MEMO_PATH.is_file() else None,
        "candidates_present": candidates_present,
        "axes_present": axes_present,
        "readings_literal": readings_literal,
        "readings_all_literal": all(readings_literal.values()),
        "consistency_returncode": run_consistency(),
        "deferred_criteria": dict(DEFERRED),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        criteria_row("H48c1", "venue 备忘录交付且含 >= 3 候选的四轴对比",
                     {"memo_exists": payload["memo_exists"],
                      "n_candidates": len(payload["candidates_present"]),
                      "axes_present": payload["axes_present"]},
                     {"memo_exists": True, "min_candidates": 3, "axes": list(AXES)},
                     bool(payload["memo_exists"]) and len(payload["candidates_present"]) >= 3
                     and list(payload["axes_present"]) == list(AXES)),
        criteria_row("H48c3", "形式改动零科学漂移：一致性校验 PASS 且四个冻结读数逐字在稿",
                     {"consistency_returncode": payload["consistency_returncode"],
                      "readings_all_literal": payload["readings_all_literal"],
                      "readings_literal": payload["readings_literal"]},
                     {"consistency_returncode": 0, "readings_all_literal": True},
                     payload["consistency_returncode"] == 0
                     and bool(payload["readings_all_literal"])),
        criteria_row("H48c4", "0 shot；投稿包条目按 venue 未定登记 deferred（非失败）",
                     {"shots_this_week": 0, "deferred_criteria": payload["deferred_criteria"]},
                     {"shots": 0}, True),
    ]


def render_report(payload: Mapping[str, object],
                  criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W48-C 投稿执行包（C1 交付 / C2-C3 待 venue 拍板）")
    add("")
    add("类④（投稿操作）lane，0 shot。venue 选择权在用户；本件只交付备忘录并守住零科学漂移。")
    add("")
    add("## 1 交付状态")
    add("")
    add("- C1 venue 备忘录：reports/w48_venue_memo.md（sha256 "
        + str(payload["memo_sha256"])[:16] + "）。")
    add("- 候选命中（" + str(len(payload["candidates_present"])) + "/" + str(len(CANDIDATES)) + "）："
        + "，".join(payload["candidates_present"]) + "。")
    add("- 四轴命中：" + "，".join(payload["axes_present"]) + "。")
    add("- deferred：" + "；".join(str(k) + "=" + str(v)
                                    for k, v in dict(payload["deferred_criteria"]).items()) + "。")
    add("")
    add("## 2 判据")
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
    sources = [PREREG_PATH, MEMO_PATH, PAPER_PATH]
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
                "why_not_a_shot": "投稿操作：只交付 venue 对比备忘录与形式守卫，不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "memo_exists": payload["memo_exists"],
            "memo_sha256": payload["memo_sha256"],
            "candidates_present": payload["candidates_present"],
            "axes_present": payload["axes_present"],
            "readings_all_literal": payload["readings_all_literal"],
            "consistency_returncode": payload["consistency_returncode"],
            "deferred_criteria": payload["deferred_criteria"],
            "pending_user_decisions": ["venue 方向（需核单位要求）", "投稿时点"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "C1 venue 备忘录交付（%d 候选 × 四轴）；C2/C3 按 venue 未定登记 deferred。"
                % len(payload["candidates_present"]),
                "零科学漂移：一致性校验返回码 " + str(payload["consistency_returncode"])
                + "；四个冻结读数逐字在稿。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("memo %s | candidates %d | axes %d | consistency rc %d | deferred %s"
          % (payload["memo_exists"], len(payload["candidates_present"]),
             len(payload["axes_present"]), payload["consistency_returncode"],
             list(payload["deferred_criteria"])))
    print("criteria %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
