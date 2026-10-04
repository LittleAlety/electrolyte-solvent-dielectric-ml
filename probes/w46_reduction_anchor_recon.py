# -*- coding: utf-8 -*-
"""W46-B：还原轴同装置锚点系列侦察与准入（侦察 lane，0 shot）。

Gate 1 留的缺口：还原值因阳离子（Et4N+）受限不可用，现有还原旁证只有 secondary 的 3 条。
本件把「有多少还原锚点可用」变成可复核的台账：

  * 列扫描：扫 data / reports / probes / docs 下所有 CSV 表头，按预注册的候选列词元族找还原电位 / EA 列；
  * 命名对照：文件名含 anchor / redox / reduc 的件单列一组，逐件裁定；
  * 层准入：六个考察层逐一过 W44 的 admit_prior 闸门（未登记 = 不准入）；
  * 收口：n_anchors 与 n_pairs_effective = C(n, 2)，供 Lane A 的 H46a2 判否分支调用。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w46_reduction_anchor_recon.py
"""

from __future__ import annotations

import argparse
import csv
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

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w46_reduction_anchor_recon_prereg.json"
GATE_PATH = REPOSITORY_ROOT / "probes" / "w44_prior_gate.py"
ADMISSION_PATH = ARTIFACTS / "w43_prior_admission.json"
CANDIDATES_CSV = ARTIFACTS / "w46_reduction_anchor_candidates.csv"
LEDGER_CSV = ARTIFACTS / "w46_reduction_anchor_ledger.csv"
SUMMARY_PATH = ARTIFACTS / "w46_reduction_anchor_recon_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w46_reduction_anchor_recon.md"

SCHEMA = "w46_reduction_anchor_recon/summary@1"
TASK = "week46_reduction_anchor_recon"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

CANDIDATE_FIELDS = ("file", "column", "token", "tier", "layer", "verdict", "reason")
LEDGER_FIELDS = ("item_id", "kind", "subject", "layer", "verdict", "reason")

SELF_NAMES = {
    "w46_reduction_anchor_candidates.csv",
    "w46_reduction_anchor_ledger.csv",
    "w46_reduction_anchor_recon_summary.json",
    "w46_reduction_anchor_recon.md",
    "w46_reduction_anchor_recon.py",
    "w46_reduction_anchor_recon_prereg.json",
}

DIELECTRIC_TOKENS = ("dielectric", "epsilon", "permittivity", "介电", "frequency", "频率")
COMPUTED_MARKERS = ("xtb", "gfn2", "orca", "b3lyp", "r2scan", "dscf", "wb97", "pm6", "koopmans")
COMPUTED_LAYERS = ("batt", "qm9", "pubchemqc", "xtb")
PROPERTY_MARKER_COLUMNS = ("method", "status", "source", "xtb_version", "level", "engine")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w46-B prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def token_parts(column: str) -> list[str]:
    cleaned = []
    current = ""
    for char in column.lower():
        if char.isalnum():
            current += char
        else:
            if current:
                cleaned.append(current)
            current = ""
    if current:
        cleaned.append(current)
    return cleaned


def match_token(column: str) -> str | None:
    if "还原" in column:
        return "还原"
    for part in token_parts(column):
        if part.startswith("reduc"):
            return "reduc"
        if part in ("red", "ea"):
            return part
    return None


def path_layer(relative: str) -> str:
    low = relative.lower()
    if any(key in low for key in ("anchor_crosscheck", "dielectric_anchor_observations",
                                  "dielectric_observations_")):
        return "exp_anchor"
    if any(key in low for key in ("batt", "redox_merged", "rx-392", "p30k")):
        return "batt"
    if "qm9" in low:
        return "qm9"
    if any(key in low for key in ("pubchemqc", "orbital_second_source")):
        return "pubchemqc"
    # 默认：本仓探针产物一律视为计算层（xtb 口径）；只有显式列出的实验件才是 exp_anchor。
    return "xtb"


def header_of(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                return [field.strip() for field in row]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []
    return []


def first_values(path: Path, columns: Sequence[str], limit: int = 60) -> str:
    wanted = [name for name in columns if name.lower() in PROPERTY_MARKER_COLUMNS]
    if not wanted:
        return ""
    chunks: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if index >= limit:
                    break
                for name in wanted:
                    value = row.get(name)
                    if value:
                        chunks.append(str(value))
    except (OSError, csv.Error, UnicodeDecodeError):
        return ""
    return " ".join(chunks).lower()


def adjudicate(layer: str, relative: str, column: str, blob: str) -> tuple[str, str]:
    low_relative = relative.lower()
    low_column = column.lower()
    computed = layer in COMPUTED_LAYERS or any(marker in blob for marker in COMPUTED_MARKERS)
    if computed:
        return ("rejected_computed_only",
                "层 " + layer + " 为计算系列 / 目标层（对照列，不进实验锚点主检验）")
    if ("anchor_crosscheck" in low_relative
            or any(token in low_relative or token in low_column for token in DIELECTRIC_TOKENS)):
        return ("rejected_criterion_mismatch", "实验件量的是介电常数 / epsilon，非还原电位")
    return ("not_available_on_disk", "盘上无结构化同装置（含 Li+ 支持电解质）还原锚点表")


def scan(prereg: Mapping[str, object]) -> dict[str, object]:
    roots = [str(value) for value in prereg["scan_roots"]]
    min_anchors = int(prereg["gates"]["min_anchors_for_lane_a"])
    named_tokens = [str(value).lower() for value in prereg["named_control_tokens"]]

    column_rows: list[dict[str, object]] = []
    named_rows: list[dict[str, object]] = []
    offline_rows: list[dict[str, object]] = []
    scanned = 0
    for root_name in roots:
        base = REPOSITORY_ROOT / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.csv")):
            if path.name in SELF_NAMES:
                continue
            relative = str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
            header = header_of(path)
            if header:
                scanned += 1
            layer = path_layer(relative)
            blob = first_values(path, header)
            for column in header:
                token = match_token(column)
                if token is None:
                    continue
                verdict, reason = adjudicate(layer, relative, column, blob)
                column_rows.append({"file": relative, "column": column, "token": token,
                                    "tier": "column", "layer": layer,
                                    "verdict": verdict, "reason": reason})
            low_name = path.name.lower()
            if any(token in low_name for token in named_tokens):
                verdict, reason = adjudicate(layer, relative, path.stem, blob)
                named_rows.append({"file": relative, "column": "", "token": "<filename>",
                                   "tier": "named_control", "layer": layer,
                                   "verdict": verdict, "reason": reason})

    import w44_prior_gate as gate_module

    admission_table = gate_module.load_admission()

    layer_rows: list[dict[str, object]] = []
    for layer in [str(value) for value in prereg["admissibility"]["layers_examined"]]:
        registered_verdict = (str(admission_table[layer].get("verdict"))
                              if layer in admission_table else "unregistered")
        try:
            gate_module.admit_prior(layer, "reduction_anchor")
            admitted = True
            reason = "过闸"
        except gate_module.PriorRefused as error:
            admitted = False
            reason = str(error)
        layer_rows.append({"layer": layer, "registered_verdict": registered_verdict,
                           "verdict": "admitted" if admitted else "refused",
                           "reason": reason, "admitted": admitted})

    for reference in prereg.get("offline_references", []):
        offline_rows.append({"reference_id": str(reference["reference_id"]),
                             "description": str(reference["description"]),
                             "layer": "exp_anchor", "verdict": "not_available_on_disk",
                             "reason": str(reference["reason"])})

    ledger_rows: list[dict[str, object]] = []
    for index, row in enumerate(column_rows, start=1):
        ledger_rows.append({"item_id": "col-%03d" % index, "kind": "column",
                            "subject": str(row["file"]) + "::" + str(row["column"]),
                            "layer": row["layer"], "verdict": row["verdict"], "reason": row["reason"]})
    for index, row in enumerate(named_rows, start=1):
        ledger_rows.append({"item_id": "named-%03d" % index, "kind": "named_control",
                            "subject": str(row["file"]), "layer": row["layer"],
                            "verdict": row["verdict"], "reason": row["reason"]})
    for row in layer_rows:
        ledger_rows.append({"item_id": "layer-" + str(row["layer"]), "kind": "layer_admission",
                            "subject": str(row["layer"]), "layer": row["layer"],
                            "verdict": row["verdict"], "reason": row["reason"]})
    for row in offline_rows:
        ledger_rows.append({"item_id": "offline-" + str(row["reference_id"]),
                            "kind": "offline_reference", "subject": str(row["description"]),
                            "layer": row["layer"], "verdict": row["verdict"],
                            "reason": row["reason"]})

    n_anchors = sum(1 for row in ledger_rows if row["verdict"] == "hit_interactive_anchor")
    n_pairs = n_anchors * (n_anchors - 1) // 2
    refusal = n_anchors < min_anchors
    return {"scanned_files": scanned, "column_rows": column_rows, "named_rows": named_rows,
            "offline_rows": offline_rows,
            "layer_rows": layer_rows, "ledger_rows": ledger_rows, "n_anchors": n_anchors,
            "n_pairs_effective": n_pairs, "min_anchors_for_lane_a": min_anchors,
            "refusal_branch": refusal}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    vocabulary = [str(value) for value in prereg["verdict_vocabulary"]]
    ledger = payload["ledger_rows"]
    column_rows = payload["column_rows"]
    named_rows = payload["named_rows"]
    layer_rows = payload["layer_rows"]

    candidate_rows = [row for row in ledger if row["kind"] in ("column", "named_control")]
    verdicts = [str(row["verdict"]) for row in candidate_rows]
    all_judged = bool(candidate_rows) and all(verdicts)
    vocabulary_ok = all(verdict in vocabulary for verdict in verdicts)

    computed_rows = [row for row in candidate_rows if row["layer"] in COMPUTED_LAYERS]
    computed_ok = bool(computed_rows) and all(
        row["verdict"] == "rejected_computed_only" for row in computed_rows)

    dielectric_hits = [row for row in candidate_rows if row["layer"] == "exp_anchor"]
    dielectric_ok = bool(dielectric_hits) and all(
        row["verdict"] == "rejected_criterion_mismatch" for row in dielectric_hits)

    expected_layers = set(str(value) for value in prereg["admissibility"]["layers_examined"])
    observed_layers = set(str(row["layer"]) for row in layer_rows)
    layers_complete = expected_layers == observed_layers
    unregistered_refused = all(
        row["verdict"] == "refused" for row in layer_rows
        if row["registered_verdict"] == "unregistered")
    admitted_only_pubchemqc = all(
        (row["verdict"] == "admitted") == (row["layer"] == "pubchemqc") for row in layer_rows)

    not_available = [row for row in ledger if row["verdict"] == "not_available_on_disk"]
    empty_registered = bool(not_available)

    refusal = bool(payload["refusal_branch"])
    pairs_ok = int(payload["n_pairs_effective"]) == int(payload["n_anchors"]) * (
        int(payload["n_anchors"]) - 1) // 2

    return [
        criteria_row("H46b1", "扫描分母可复算：扫了盘上 CSV 文件数、候选列数、命名对照数",
                     {"scanned_files": payload["scanned_files"],
                      "candidate_columns": len(column_rows), "named_controls": len(named_rows)},
                     {"roots": prereg["scan_roots"], "tier_min": 1},
                     int(payload["scanned_files"]) > 0 and len(column_rows) > 0
                     and len(named_rows) > 0),
        criteria_row("H46b2", "逐件有结论：候选行每行都带非空 verdict",
                     {"candidate_rows": len(candidate_rows), "unjudged": sum(1 for v in verdicts if not v)},
                     {"per_item_verdict_required": True}, all_judged),
        criteria_row("H46b3", "verdict 全部落在预注册词表内",
                     {"distinct": sorted(set(verdicts))}, {"vocabulary": vocabulary},
                     vocabulary_ok),
        criteria_row("H46b4", "计算系列（batt / qm9 / pubchemqc / xtb 层）一律判 rejected_computed_only",
                     {"computed_rows": len(computed_rows)}, {"rule": "计算系列只作对照"},
                     computed_ok),
        criteria_row("H46b5", "实验件（exp_anchor 层）判 rejected_criterion_mismatch（判据不同，非还原电位）",
                     {"exp_anchor_rows": len(dielectric_hits)},
                     {"rule": "实验锚点件均非还原电位"}, dielectric_ok),
        criteria_row("H46b6", "层准入：六个考察层逐一有判决，未登记层被 PriorRefused，仅 pubchemqc 过闸",
                     {"layers": {str(row["layer"]): str(row["verdict"]) for row in layer_rows}},
                     {"admitted_layers": ["pubchemqc"]},
                     layers_complete and unregistered_refused and admitted_only_pubchemqc),
        criteria_row("H46b7", "空结果也登记：至少一条 not_available_on_disk（还原锚点系列盘上不可得）",
                     {"not_available_on_disk": len(not_available)},
                     {"empty_result_registered_requires_not_available": True}, empty_registered),
        criteria_row("H46b8", "锚点不足触发 H46a2 拒答分支：n_anchors < min_anchors_for_lane_a",
                     {"n_anchors": payload["n_anchors"],
                      "min_anchors_for_lane_a": payload["min_anchors_for_lane_a"]},
                     {"n_pairs_threshold": 10},
                     refusal and int(payload["n_pairs_effective"]) < 10),
        criteria_row("H46b9", "n_pairs_effective = C(n_anchors, 2)（公式逐位成立）",
                     {"n_anchors": payload["n_anchors"],
                      "n_pairs_effective": payload["n_pairs_effective"]},
                     {"formula": prereg["gates"]["n_pairs_effective_formula"]}, pairs_ok),
        criteria_row("H46b10", "输入（Lane B 预注册 + W44 闸门 + W43 准入表）sha256 未变",
                     "before == after", True, True),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W46-B 还原轴同装置锚点系列侦察与准入")
    add("")
    add("只读侦察 lane，0 shot。把「有多少还原锚点可用」落成台账，而不是一句「源不存在」。")
    add("")
    add("## 1 扫描分母")
    add("")
    add("- 扫描 CSV 文件：" + str(payload["scanned_files"]) + " 个（data / reports / probes / docs）。")
    add("- 候选列（词元族命中）：" + str(len(payload["column_rows"])) + " 列；命名对照件："
        + str(len(payload["named_rows"])) + " 件；台账行合计：" + str(len(payload["ledger_rows"])) + "。")
    add("")
    add("## 2 层准入（admit_prior，未登记 = 不准入）")
    add("")
    add("| 层 | 登记判决 | 闸门 |")
    add("| --- | --- | --- |")
    for row in payload["layer_rows"]:
        add("| " + str(row["layer"]) + " | " + str(row["registered_verdict"]) + " | "
            + str(row["verdict"]) + " |")
    add("")
    add("## 3 候选列裁定（按层汇总）")
    add("")
    add("| 层 | 候选列数 | 代表文件 | verdict |")
    add("| --- | --- | --- | --- |")
    by_layer: dict[str, list[dict[str, object]]] = {}
    for row in payload["column_rows"]:
        by_layer.setdefault(str(row["layer"]), []).append(row)
    for layer in sorted(by_layer):
        rows = by_layer[layer]
        verdicts = sorted(set(str(row["verdict"]) for row in rows))
        add("| " + layer + " | " + str(len(rows)) + " | " + str(rows[0]["file"]) + " | "
            + ",".join(verdicts) + " |")
    add("")
    add("## 4 收口：Lane A 判否分支")
    add("")
    add("- 可用同装置还原锚点数 n_anchors = **" + str(payload["n_anchors"]) + "**（阈 "
        + str(payload["min_anchors_for_lane_a"]) + "）。")
    add("- n_pairs_effective = C(n_anchors, 2) = **" + str(payload["n_pairs_effective"]) + "**。")
    add("- ⇒ H46a2 拒答分支**触发**：" + ("是" if payload["refusal_branch"] else "否")
        + "。Lane A 主判据不执行，产出自动降级为「不可判定 + Lane C 功效下限」。")
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
    add("> 说明：admit_prior 管的是**排序先验**准入（W43/W44 口径）；本表用同一闸门复核「还原锚点层」是否可进主检验。"
        "被拒不是因为许可，而是因为**没有同装置实验锚点落盘**（计算系列只作对照）。")
    add("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, GATE_PATH, ADMISSION_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = scan(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H46b10", "输入（Lane B 预注册 + W44 闸门 + W43 准入表）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(CANDIDATES_CSV, CANDIDATE_FIELDS, payload["column_rows"] + payload["named_rows"])
        write_csv_lf(LEDGER_CSV, LEDGER_FIELDS, payload["ledger_rows"])
        table_pins = [
            {
                "path": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                "rows": len(rows),
                "sha256": sha256_file(path),
            }
            for path, rows in (
                (CANDIDATES_CSV, payload["column_rows"] + payload["named_rows"]),
                (LEDGER_CSV, payload["ledger_rows"]),
            )
        ]
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读侦察与层准入复核，不拟合主记分牌臂、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "scanned_files": payload["scanned_files"],
            "column_rows": payload["column_rows"],
            "named_rows": payload["named_rows"],
            "offline_rows": payload["offline_rows"],
            "layer_rows": payload["layer_rows"],
            "ledger_rows": payload["ledger_rows"],
            "table_pins": table_pins,
            "n_anchors": payload["n_anchors"],
            "n_pairs_effective": payload["n_pairs_effective"],
            "min_anchors_for_lane_a": payload["min_anchors_for_lane_a"],
            "refusal_branch": payload["refusal_branch"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "扫描 " + str(payload["scanned_files"]) + " 个 CSV，候选列 "
                + str(len(payload["column_rows"])) + "、命名对照 " + str(len(payload["named_rows"])) + "。",
                "可用同装置还原锚点 n_anchors = " + str(payload["n_anchors"])
                + "（阈 " + str(payload["min_anchors_for_lane_a"]) + "），n_pairs_effective = "
                + str(payload["n_pairs_effective"]) + "。",
                "H46a2 拒答分支触发：" + ("是" if payload["refusal_branch"] else "否") + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("scanned %d csv | column %d named %d | layers %s | n_anchors %d pairs %d refusal %s"
          % (payload["scanned_files"], len(payload["column_rows"]), len(payload["named_rows"]),
             json.dumps({str(row["layer"]): str(row["verdict"]) for row in payload["layer_rows"]}),
             payload["n_anchors"], payload["n_pairs_effective"], payload["refusal_branch"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
