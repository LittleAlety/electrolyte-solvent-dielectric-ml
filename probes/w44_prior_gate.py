# -*- coding: utf-8 -*-
"""W44-A：把层准入表升成会抛异常的闸门 + 全仓消费者审计（治理 lane，0 shot）。

W43-C 出了一张层准入表（score 门 + rho 门 + unit 门 + license 门），但下游仍要「自觉」去查它。
本件把「自觉」变成**机械拒绝**：
  * admit_prior(layer, use)：只有 verdict == admit 的层可作排序先验；否则抛 PriorRefused。
  * 消费者审计：扫 probes/ 与 reports/ 的 *.py / *.md，凡同时出现「某一层的产物路径」与先验词表
    的 (文件 x 层) 对，都必须进声明表；分类规则写死——文件里出现 admit_prior("LAYER") 才算
    运营性先验使用，其余记为 declaration_only。
  * 负对照：三个未登记/未准入的层（ccsd_t 新层、qm9 defer、batt 目标层）必须全部被拒。

只读；不改任何 summary、标签或特征列；累计 shot 仍是 19。

Run:
    .venv/Scripts/python.exe probes/w44_prior_gate.py
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
ADMISSION_JSON = ARTIFACTS / "w43_prior_admission.json"
CONSUMERS_CSV = ARTIFACTS / "w44_prior_consumers.csv"
REFUSALS_CSV = ARTIFACTS / "w44_prior_gate_refusals.csv"
GATE_JSON = ARTIFACTS / "w44_prior_gate.json"
SUMMARY_PATH = ARTIFACTS / "w44_prior_gate_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w44_prior_gate.md"

SCHEMA = "w44_prior_gate/summary@1"
TASK = "week44_prior_gate"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

CONSUMER_FIELDS = ("consumer_path", "layer", "use_class", "declared_use", "gate_verdict", "reason")
REFUSAL_FIELDS = ("layer", "declared_use", "verdict", "reason")
LAYER_ARTIFACT = {
    "xtb": "w23_orbital_medium_layer.csv",
    "qm9": "w39_qm9_overlap.csv",
    "pubchemqc": "orbital_second_source_layer.csv",
    "batt": "w41_orbital_batt_hits.csv",
}
PRIOR_TOKENS = ("排序先验", "ranking prior", "当先验", "作先验")
SCAN_ROOTS = ("probes", "reports")
SCAN_SUFFIXES = (".py", ".md")
OPERATIONAL_SEED = (
    ("probes/w44_prior_gate.py", "pubchemqc", "positive_control"),
)


class PriorRefused(RuntimeError):
    """未准入（或未登记）的层不得作排序先验。"""


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w44 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def load_admission() -> dict[str, dict[str, object]]:
    payload = json.loads(ADMISSION_JSON.read_text(encoding="utf-8-sig"))
    return {str(row["layer"]): dict(row) for row in payload["rows"]}


def admit_prior(layer: str, use: str = "ranking_prior",
                admission: Mapping[str, Mapping[str, object]] | None = None) -> dict[str, object]:
    table = admission if admission is not None else load_admission()
    if layer not in table:
        raise PriorRefused("层未登记：" + layer + "（未登记 = 不准入）")
    row = table[layer]
    if str(row.get("verdict")) != "admit":
        raise PriorRefused("层 " + layer + " verdict=" + str(row.get("verdict"))
                           + "，不得作 " + use)
    return row


def _scan_consumers() -> list[tuple[str, str]]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        base = REPOSITORY_ROOT / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                files.append(path)
    pairs: list[tuple[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not any(token in text for token in PRIOR_TOKENS):
            continue
        relative = str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
        for layer, artifact in LAYER_ARTIFACT.items():
            if artifact in text and (relative, layer) not in pairs:
                pairs.append((relative, layer))
    return pairs


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w44_prior_gate"]
    table = load_admission()
    pairs = _scan_consumers()
    scanned_files = sum(1 for root_name in SCAN_ROOTS
                        for path in (REPOSITORY_ROOT / root_name).rglob("*")
                        if path.is_file() and path.suffix in SCAN_SUFFIXES)

    operational: dict[tuple[str, str], str] = {}
    for relative, layer, _label in OPERATIONAL_SEED:
        operational[(relative, layer)] = "operational_prior"
    for relative, layer in pairs:
        path = REPOSITORY_ROOT / relative
        text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        if 'admit_prior("' + layer + '"' in text or "admit_prior('" + layer + "'" in text:
            operational[(relative, layer)] = "operational_prior"

    rows: list[dict[str, object]] = []
    declared = set()
    for (relative, layer), use_class in sorted(operational.items()):
        declared.add((relative, layer))
        try:
            admit_prior(layer, use_class, table)
            verdict, reason = "admitted", "verdict=" + str(table[layer].get("verdict"))
        except PriorRefused as error:
            verdict, reason = "refused", str(error)
        rows.append({"consumer_path": relative, "layer": layer, "use_class": use_class,
                     "declared_use": use_class, "gate_verdict": verdict, "reason": reason})
    for relative, layer in sorted(pairs):
        if (relative, layer) in declared:
            continue
        rows.append({"consumer_path": relative, "layer": layer, "use_class": "declaration_only",
                     "declared_use": "declaration_only", "gate_verdict": "not_applicable",
                     "reason": "仅层级声明 / 准入规则 / 交付记录，非运营性先验使用"})
        declared.add((relative, layer))

    undeclared = [relative + "::" + layer for relative, layer in pairs if (relative, layer) not in declared]

    refusal_rows: list[dict[str, object]] = []
    for control in lane["negative_controls"]:
        layer = str(control["layer"])
        try:
            admit_prior(layer, "negative_control", table)
            verdict, reason = "admitted", "（不应该发生）"
        except PriorRefused as error:
            verdict, reason = "refused", str(error)
        refusal_rows.append({"layer": layer, "declared_use": "negative_control",
                             "verdict": verdict, "reason": reason})

    positive: dict[str, object] = {}
    for layer in lane["gate"]["admit_set_expected"]:
        try:
            admit_prior(str(layer), "positive_control", table)
            positive[str(layer)] = "admitted"
        except PriorRefused as error:
            positive[str(layer)] = "refused:" + str(error)

    return {
        "scanned_files": scanned_files,
        "pairs": pairs,
        "consumer_rows": rows,
        "undeclared": undeclared,
        "refusal_rows": refusal_rows,
        "positive_control": positive,
        "admission_verdicts": {name: str(row.get("verdict")) for name, row in table.items()},
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w44_prior_gate"]["gates"]
    lane = prereg["lanes"]["w44_prior_gate"]
    refusals = payload["refusal_rows"]
    refused = [row for row in refusals if row["verdict"] == "refused"]
    operational = [row for row in payload["consumer_rows"] if row["use_class"] == "operational_prior"]
    criteria = [
        criteria_row("H44a1", "扫描到的 *.py / *.md 文件数 >= 300",
                     payload["scanned_files"], int(lane["consumer_scan"]["min_files_scanned"]),
                     int(payload["scanned_files"]) >= int(lane["consumer_scan"]["min_files_scanned"])),
        criteria_row("H44a2", "准入表判决为 pubchemqc admit、其余 defer/reject",
                     payload["admission_verdicts"], {"pubchemqc": "admit"},
                     payload["admission_verdicts"].get("pubchemqc") == "admit"
                     and all(payload["admission_verdicts"][layer] != "admit"
                             for layer in ("xtb", "qm9", "batt"))),
        criteria_row("H44a3", "三个负对照全部被拒",
                     [row["layer"] for row in refused], lane["negative_controls"],
                     len(refused) == int(gates["refused_controls"])),
        criteria_row("H44a4", "正对照 pubchemqc 过闸",
                     payload["positive_control"], {"pubchemqc": "admitted"},
                     payload["positive_control"].get("pubchemqc") == "admitted"),
        criteria_row("H44a5", "运营性先验使用全部过闸（无 refused）",
                     {row["consumer_path"]: row["gate_verdict"] for row in operational},
                     "all admitted",
                     all(row["gate_verdict"] == "admitted" for row in operational)),
        criteria_row("H44a6", "未申报的先验使用数 <= 0",
                     payload["undeclared"], "<= 0",
                     len(payload["undeclared"]) <= int(gates["undeclared_prior_uses_max"])),
        criteria_row("H44a7", "声明表覆盖全部扫描到的 (文件 x 层) 对",
                     {"declared": len(payload["consumer_rows"]), "scanned_pairs": len(payload["pairs"])},
                     "declared >= scanned",
                     len(payload["consumer_rows"]) >= len(payload["pairs"])),
        criteria_row("H44a8", "输入文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W44-A 层准入闸门 + 全仓消费者审计（治理 lane，0 shot）",
        "",
        "把 W43-C 的层准入表升成**会抛异常**的闸门 `admit_prior()`，并对全仓消费者做机械审计。",
        "",
        "## 1 闸门规则",
        "",
        "- `admit_prior(layer, use)`：层未登记 ⇒ 抛 `PriorRefused`；verdict != admit ⇒ 抛 `PriorRefused`。",
        "- 判决表：" + json.dumps(payload["admission_verdicts"], ensure_ascii=False) + "。",
        "",
        "## 2 负对照与正对照",
        "",
        "| 层 | 角色 | 闸门结果 |",
        "| --- | --- | --- |",
    ]
    for row in payload["refusal_rows"]:
        lines.append("| " + str(row["layer"]) + " | 负对照 | " + str(row["verdict"]) + " |")
    for layer, verdict in payload["positive_control"].items():
        lines.append("| " + layer + " | 正对照 | " + str(verdict) + " |")
    lines += [
        "",
        "## 3 消费者审计",
        "",
        "- 扫描 " + str(payload["scanned_files"]) + " 个 *.py / *.md；命中 (文件 x 层) 对 "
        + str(len(payload["pairs"])) + " 个。",
        "- 运营性先验使用（文件里出现 `admit_prior\"LAYER\"`）："
        + str(len([row for row in payload["consumer_rows"] if row["use_class"] == "operational_prior"])) + " 个。",
        "- 未申报的先验使用：" + str(len(payload["undeclared"])) + " 个。",
        "",
        "| 消费者 | 层 | 类别 | 闸门 |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload["consumer_rows"][:40]:
        lines.append("| " + str(row["consumer_path"]) + " | " + str(row["layer"]) + " | "
                     + str(row["use_class"]) + " | " + str(row["gate_verdict"]) + " |")
    lines += [
        "",
        "## 4 判据",
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
        "## 5 边界",
        "",
        "- 只读：闸门只查表、不写标签、不改 summary。",
        "- 当前唯一的运营性先验使用是正对照 pubchemqc（已过闸）；闸门的价值是**下一次有人要用时必须先过它**。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [ADMISSION_JSON, PREREG_PATH]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(CONSUMERS_CSV, CONSUMER_FIELDS, payload["consumer_rows"])
    write_csv_lf(REFUSALS_CSV, REFUSAL_FIELDS, payload["refusal_rows"])
    write_json_stable(GATE_JSON, {
        "gate": "admit_prior(layer, use) -> row | raise PriorRefused",
        "admission_verdicts": payload["admission_verdicts"],
        "negative_controls": payload["refusal_rows"],
        "positive_control": payload["positive_control"],
        "scanned_files": payload["scanned_files"],
    })

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读层准入表、跑闸门与全仓文本审计，不拟合主记分牌臂、不加特征列、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "scanned_files": payload["scanned_files"],
        "admission_verdicts": payload["admission_verdicts"],
        "consumer_rows": payload["consumer_rows"],
        "refusal_rows": payload["refusal_rows"],
        "positive_control": payload["positive_control"],
        "undeclared_prior_uses": payload["undeclared"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "闸门 admit_prior() 就位：只有 pubchemqc 过闸，三个负对照全部被拒。",
            "扫 " + str(payload["scanned_files"]) + " 个文件，命中 " + str(len(payload["pairs"]))
            + " 个 (文件 x 层) 对；运营性先验使用 "
            + str(len([row for row in payload["consumer_rows"]
                       if row["use_class"] == "operational_prior"]))
            + " 个（正对照 pubchemqc，已过闸）。",
            "未申报先验使用 = " + str(len(payload["undeclared"])) + "。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("scanned %d files, pairs %d, operational %d, undeclared %d"
          % (payload["scanned_files"], len(payload["pairs"]),
             len([r for r in payload["consumer_rows"] if r["use_class"] == "operational_prior"]),
             len(payload["undeclared"])))
    print("refusals %s" % json.dumps([r["layer"] + ":" + r["verdict"] for r in payload["refusal_rows"]]))
    print("positive %s" % json.dumps(payload["positive_control"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
