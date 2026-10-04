# -*- coding: utf-8 -*-
"""W48-B：Ue 1997 取件裁决与欠账收口（修正案 A1 第③类，0 shot）。

W47-B 把 Ue 1997（JES 144, 2684）的还原侧登记为 pending_source_retrieval，
取件优先级最高。本件是那条开项的唯一收口动作：

  * DOI 更正：计划里的候选 DOI 10.1149/1.1837585 经 Crossref 证伪（它指向
    Ohmori/Kimura/Masuda 1997 的多孔铂电极阻抗文）；正确条目是
    Ue/Takeda/Takehara/Mori, JES 144(8) 2684-2688 (1997), DOI 10.1149/1.1837882。
  * 三态落定：transcribed_and_adjudicated / no_reduction_side / not_available。
    本周期取件失败（出版方机器人墙 + 无 OA 镜像 + 元数据服务不供摘要），
    登记 not_available 作为合法收口 —— 取件失败本身也是收口。
  * 诚实条款：即使取到且含还原侧，n = 4 时 MDE = 0.9826、精确拒绝率 = 1/24，
    功效也极可能不足。本轮价值是收口欠账，不是翻盘主判据。

护栏：不改 W47 已冻结预注册文件本身；不新增判据族；不占主记分牌 shot。

Run:
    .venv/Scripts/python.exe probes/w48_ue1997_track.py
    .venv/Scripts/python.exe probes/w48_ue1997_track.py --check
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w48_ue1997_prereg.json"
ANCHOR_PREREG = REPOSITORY_ROOT / "probes" / "w47_anchor_prereg.json"
TRACK_PREREG = REPOSITORY_ROOT / "probes" / "w47_experimental_track_prereg.json"
README_PATH = REPOSITORY_ROOT / "README.md"
LEDGER_CSV = ARTIFACTS / "w48_ue1997_ledger.csv"
SUMMARY_PATH = ARTIFACTS / "w48_ue1997_summary.json"
CRITERIA_CSV = ARTIFACTS / "w48_ue1997_criteria.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w48_ue1997.md"

SCHEMA = "w48_ue1997/summary@1"
TASK = "week48_ue1997_adjudication"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEDGER_FIELDS = ("item_id", "source", "citation", "axis", "solvent_scope",
                 "disposition", "condition_flag", "evidence", "note")
CRITERIA_FIELDS = ("id", "description", "value", "threshold", "verdict")

DISPOSITION = "not_available"
DISPOSITION_VOCABULARY = ("transcribed_and_adjudicated", "no_reduction_side", "not_available")
MAIN_CRITERION_EXECUTED = False
README_MARKERS = ("Ue 1997", "not_available", "10.1149/1.1837882", "round-2")

LEDGER_ROWS: tuple[dict[str, str], ...] = (
    {
        "item_id": "ue1997_doi",
        "source": "Ue 1997 DOI 更正",
        "citation": "10.1149/1.1837585 -> 10.1149/1.1837882",
        "axis": "n/a",
        "solvent_scope": "n/a",
        "disposition": "corrected",
        "condition_flag": "NOT_APPLICABLE_SOURCE_METADATA",
        "evidence": "api.crossref.org/works/10.1149/1.1837882",
        "note": "旧 DOI 指向 Ohmori/Kimura/Masuda, JES 144(4) 1286-1288 (1997) 多孔铂电极阻抗文；"
                "正确条目为 Ue/Takeda/Takehara/Mori, JES 144(8) 2684-2688 (1997)。",
    },
    {
        "item_id": "ue1997_reduction_side",
        "source": "Ue 1997",
        "citation": "J. Electrochem. Soc. 144(8) 2684-2688 (10.1149/1.1837882)",
        "axis": "reduction (open item)",
        "solvent_scope": "EC/PC/EMC/DMC (unverified)",
        "disposition": DISPOSITION,
        "condition_flag": "CONDITION_MATCH_UNVERIFIED",
        "evidence": "IOP Radware 挑战页 / 无 OA 镜像；OpenAlex abstract_inverted_index",
        "note": "取件失败，登记 not_available（合法收口）；不转录、不补锚点。"
                "OpenAlex 摘要显示该文同时考察 limiting reduction potentials，"
                "故仍是 round-2 优先取件对象。",
    },
)


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w48-B prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    rows = [dict(row) for row in LEDGER_ROWS]
    frozen = {str(k): str(v) for k, v in dict(prereg["reuses_frozen_criteria"]).items()}
    observed = {
        ANCHOR_PREREG.name: sha256_file(ANCHOR_PREREG),
        TRACK_PREREG.name: sha256_file(TRACK_PREREG),
    }
    frozen_unchanged = all(observed.get(name) == digest for name, digest in frozen.items())
    readme = README_PATH.read_text(encoding="utf-8")
    markers = {marker: (marker in readme) for marker in README_MARKERS}
    return {
        "rows": rows,
        "disposition": DISPOSITION,
        "disposition_in_vocabulary": DISPOSITION in DISPOSITION_VOCABULARY,
        "still_pending": DISPOSITION == "pending_source_retrieval",
        "main_criterion_executed": bool(MAIN_CRITERION_EXECUTED),
        "transcribed": bool(MAIN_CRITERION_EXECUTED),
        "rows_missing_condition_flag": [row["item_id"] for row in rows
                                        if not str(row["condition_flag"]).strip()],
        "frozen_prereg_sha256": observed,
        "frozen_prereg_unchanged": frozen_unchanged,
        "readme_markers": markers,
        "readme_markers_ok": all(markers.values()),
        "readme_sha256": sha256_file(README_PATH),
        "doi_correction": dict(prereg["doi_correction"]),
        "honesty_clause": dict(prereg["honesty_clause"]),
        "branches": {str(k): dict(v) for k, v in dict(prereg["branches"]).items()},
        "retrieval_attempts": [str(x) for x in prereg["retrieval_attempts"]],
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        criteria_row("H48b1", "Ue 1997 处置三态之一落定，台账状态不再是 pending_source_retrieval",
                     {"disposition": payload["disposition"],
                      "in_vocabulary": payload["disposition_in_vocabulary"],
                      "still_pending": payload["still_pending"]},
                     {"allowed": list(DISPOSITION_VOCABULARY),
                      "not": "pending_source_retrieval"},
                     bool(payload["disposition_in_vocabulary"]) and not payload["still_pending"]),
        criteria_row("H48b2", "若转录：行数 + sha256 三处钉住且每行带 condition_flag；未转录则不适用",
                     {"transcribed": payload["transcribed"],
                      "n_rows": len(payload["rows"]),
                      "rows_missing_condition_flag": payload["rows_missing_condition_flag"]},
                     {"applies_only_if": "transcribed_and_adjudicated"},
                     (not payload["transcribed"]) and not payload["rows_missing_condition_flag"]),
        criteria_row("H48b3", "主判据未执行时 README §11 对应条目更新为显式降级措辞",
                     {"main_criterion_executed": payload["main_criterion_executed"],
                      "readme_markers": payload["readme_markers"]},
                     {"markers": list(README_MARKERS)},
                     bool(payload["main_criterion_executed"]) or bool(payload["readme_markers_ok"])),
        criteria_row("H48b4", "0 shot；不新增判据族（H48b*）；不改 W47 已冻结预注册文件本身",
                     {"shots_this_week": 0,
                      "criteria_ids": ["H48b1", "H48b2", "H48b3", "H48b4"],
                      "frozen_prereg_sha256": payload["frozen_prereg_sha256"],
                      "frozen_prereg_unchanged": payload["frozen_prereg_unchanged"]},
                     {"shots": 0, "frozen_prereg_unchanged": True},
                     bool(payload["frozen_prereg_unchanged"])),
    ]


def render_report(payload: Mapping[str, object],
                  criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W48-B Ue 1997 取件裁决与欠账收口")
    add("")
    add("类③（已登记欠账显式收口）lane，0 shot。W47-B 的 pending_source_retrieval 在此落定为 **"
        + str(payload["disposition"]) + "**。")
    add("")
    add("## 1 DOI 更正（并案登记）")
    add("")
    doi = payload["doi_correction"]
    add("- 计划候选 DOI " + str(doi["planned_doi"]) + "：" + str(doi["planned_doi_verdict"]))
    add("- 正确条目 " + str(doi["correct_doi"]) + "：" + str(doi["correct_citation"]))
    add("- 核验途径：" + str(doi["verified_via"]))
    add("")
    add("## 2 三态落定与台账")
    add("")
    add("| item_id | disposition | condition_flag | 说明 |")
    add("| --- | --- | --- | --- |")
    for row in payload["rows"]:
        add("| " + str(row["item_id"]) + " | " + str(row["disposition"]) + " | "
            + str(row["condition_flag"]) + " | " + str(row["note"]) + " |")
    add("")
    add("- 取件尝试（全部失败）：")
    for attempt in payload["retrieval_attempts"]:
        add("  - " + attempt)
    add("- 未转录 ⇒ H48b2 不适用；不补造任何还原锚点数值。")
    add("- 本轮收口不改变 W47 已冻结预注册："
        + ("未变" if payload["frozen_prereg_unchanged"] else "**已变**")
        + "（" + ", ".join(str(k) + "=" + str(v)[:12]
                           for k, v in dict(payload["frozen_prereg_sha256"]).items()) + "）。")
    add("- README §11 显式降级措辞已落字：" + ("是" if payload["readme_markers_ok"] else "否") + "。")
    add("")
    add("## 3 诚实条款")
    add("")
    clause = payload["honesty_clause"]
    add("- MDE（n = 4）= **" + str(clause["mde_n4"]) + "**；精确拒绝率（alpha = 0.05）= **"
        + str(clause["exact_rejection_rate_n4"]) + "**（= 1/24）。")
    add("- 已知条件偏差：" + str(clause["known_condition_bias"]))
    add("- " + str(clause["statement"]))
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
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, ANCHOR_PREREG, TRACK_PREREG, README_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(LEDGER_CSV, LEDGER_FIELDS, payload["rows"])
        write_csv_lf(CRITERIA_CSV, CRITERIA_FIELDS, criteria)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "欠账收口：只读三态落定与 DOI 更正登记，不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "disposition": payload["disposition"],
            "disposition_in_vocabulary": payload["disposition_in_vocabulary"],
            "still_pending": payload["still_pending"],
            "main_criterion_executed": payload["main_criterion_executed"],
            "n_rows": len(payload["rows"]),
            "rows_missing_condition_flag": payload["rows_missing_condition_flag"],
            "frozen_prereg_sha256": payload["frozen_prereg_sha256"],
            "frozen_prereg_unchanged": payload["frozen_prereg_unchanged"],
            "readme_markers": payload["readme_markers"],
            "readme_markers_ok": payload["readme_markers_ok"],
            "readme_sha256": payload["readme_sha256"],
            "doi_correction": payload["doi_correction"],
            "honesty_clause": payload["honesty_clause"],
            "retrieval_attempts": payload["retrieval_attempts"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "Ue 1997 还原侧收口为 " + str(payload["disposition"])
                + "（不再是 pending_source_retrieval）。",
                "DOI 更正：10.1149/1.1837585（证伪）-> 10.1149/1.1837882（Ue 1997 JES 144(8) 2684）。",
                "n = 4 时 MDE 0.9826 / 精确拒绝率 1/24：本轮收口价值不是翻盘主判据。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("disposition %s | rows %d | readme-ok %s | frozen-prereg %s"
          % (payload["disposition"], len(payload["rows"]),
             payload["readme_markers_ok"], payload["frozen_prereg_unchanged"]))
    print("criteria %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
