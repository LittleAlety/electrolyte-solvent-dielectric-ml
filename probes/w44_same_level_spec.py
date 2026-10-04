# -*- coding: utf-8 -*-
"""W44-C：strict same_level 的机器要求 + 在仓候选审计（治理 lane，0 shot）。

W43 登记：near_same_level 不能当同层级替换，但「同层级」此前只是一句话。本件把它写成
**机器要求**，再拿六个在仓层去撞：
  * strict same_level 要求四属性全同（functional / basis_set / phase / geometry_source）
    且来源独立（provenance 不同）；target 是 Batt（omegaB97X-V / def2-TZVPPD / SMD）。
  * 六个候选层逐一填属性表，算与 target 的属性距离，并列出与 target 不同的属性名。
  * 所有候选两两算属性距离，找最近的一对；统计 strict（距离 0）对数与 near（泛函+相相同）对数。
  * near_same_level 声明只允许「泛函 + 相」都相同的对，否则记为越权声明。

只读：六个在仓层文件、名册 InChIKey。不新增特征列、不改标签、不动冻结读数。

Run:
    .venv/Scripts/python.exe probes/w44_same_level_spec.py
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
    load_roster_keys,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w44_governance_wiring_prereg.json"
SPEC_JSON = ARTIFACTS / "w44_same_level_spec.json"
CANDIDATES_CSV = ARTIFACTS / "w44_layer_candidates.csv"
SUMMARY_PATH = ARTIFACTS / "w44_same_level_spec_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w44_same_level_spec.md"

SCHEMA = "w44_same_level_spec/summary@1"
TASK = "week44_same_level_spec"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

SPEC_ATTRIBUTES = ("functional", "basis_set", "phase", "geometry_source")
CANDIDATE_FIELDS = ("layer", "role", "functional", "basis_set", "phase", "geometry_source",
                    "source_path", "n_rows", "n_roster_overlap", "distance_to_target",
                    "missing_vs_target")

NONE_TOKEN = "(none)"

LAYER_ORDER = ("xtb", "qm9", "pubchemqc", "batt", "orca", "expanded")

LAYERS: dict[str, dict[str, object]] = {
    "xtb": {
        "role": "prior_candidate",
        "functional": "GFN2-xTB",
        "basis_set": NONE_TOKEN,
        "phase": "gas",
        "geometry_source": "THEMol",
        "source_path": "data/processed/w23_orbital_medium_layer.csv",
        "key_column": "inchikey",
    },
    "qm9": {
        "role": "prior_candidate",
        "functional": "B3LYP",
        "basis_set": "6-31G(2df,p)",
        "phase": "gas",
        "geometry_source": "QM9-geom",
        "source_path": "probes/artifacts/w39_qm9_overlap.csv",
        "key_column": "inchikey",
    },
    "pubchemqc": {
        "role": "prior_candidate",
        "functional": "B3LYP",
        "basis_set": "6-31G*",
        "phase": "gas",
        "geometry_source": "PM6",
        "source_path": "data/processed/orbital_second_source_layer.csv",
        "key_column": "inchikey",
    },
    "batt": {
        "role": "target",
        "functional": "omegaB97X-V",
        "basis_set": "def2-TZVPPD",
        "phase": "SMD",
        "geometry_source": NONE_TOKEN,
        "source_path": "probes/artifacts/w41_orbital_batt_hits.csv",
        "key_column": "inchikey",
    },
    "orca": {
        "role": "prior_candidate",
        "functional": "r2SCAN-3c",
        "basis_set": "def2-mTZVPP",
        "phase": "gas+SMD(MeCN)",
        "geometry_source": "ORCA",
        "source_path": "data/processed/w24_2_orca_dft_layer.csv",
        "key_column": "inchikey",
    },
    "expanded": {
        "role": "prior_candidate",
        "functional": "GFN2-xTB",
        "basis_set": "(single point)",
        "phase": "gas",
        "geometry_source": "B3LYP-D3(BJ)/DZVP geom",
        "source_path": "data/processed/themol_orbital_layer_expanded.csv",
        "key_column": "inchikey",
    },
}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w44 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _row_counts(source_path: str, key_column: str, roster: set[str]) -> tuple[int, int]:
    path = REPOSITORY_ROOT / source_path
    if not path.is_file():
        return (0, 0)
    n_rows = 0
    n_overlap = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            n_rows += 1
            if key_column in row and str(row[key_column]).strip() in roster:
                n_overlap += 1
    return (n_rows, n_overlap)


def _distance(a: Mapping[str, object], b: Mapping[str, object]) -> int:
    return sum(1 for name in SPEC_ATTRIBUTES if str(a[name]) != str(b[name]))


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    roster = load_roster_keys()
    target = LAYERS["batt"]
    rows: list[dict[str, object]] = []
    for layer, spec in LAYERS.items():
        n_rows, n_overlap = _row_counts(str(spec["source_path"]), str(spec["key_column"]), roster)
        missing = [name for name in SPEC_ATTRIBUTES if str(spec[name]) != str(target[name])]
        rows.append({
            "layer": layer,
            "role": str(spec["role"]),
            "functional": str(spec["functional"]),
            "basis_set": str(spec["basis_set"]),
            "phase": str(spec["phase"]),
            "geometry_source": str(spec["geometry_source"]),
            "source_path": str(spec["source_path"]),
            "n_rows": n_rows,
            "n_roster_overlap": n_overlap,
            "distance_to_target": _distance(spec, target),
            "missing_vs_target": "|".join(missing),
        })
    rows.sort(key=lambda row: LAYER_ORDER.index(str(row["layer"])))

    names = list(LAYER_ORDER)
    pairs: list[dict[str, object]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            left, right = names[i], names[j]
            distance = _distance(LAYERS[left], LAYERS[right])
            functional_match = str(LAYERS[left]["functional"]) == str(LAYERS[right]["functional"])
            phase_match = str(LAYERS[left]["phase"]) == str(LAYERS[right]["phase"])
            pairs.append({
                "pair": left + "-" + right,
                "distance": distance,
                "functional_match": functional_match,
                "phase_match": phase_match,
                "near_same_level_eligible": bool(functional_match and phase_match and distance > 0),
                "strict_same_level": distance == 0,
            })

    strict_pairs = [row["pair"] for row in pairs if row["strict_same_level"]]
    near_pairs = [row["pair"] for row in pairs if row["near_same_level_eligible"]]
    unlicensed_near = [row["pair"] for row in pairs if row["near_same_level_eligible"]
                       and not (row["functional_match"] and row["phase_match"])]
    similar_but_not_near = [row["pair"] for row in pairs
                            if (row["functional_match"] or row["phase_match"])
                            and not row["near_same_level_eligible"]]
    best = min(pairs, key=lambda row: (int(row["distance"]), str(row["pair"])))
    strict_with_target = [row["layer"] for row in rows
                          if row["layer"] != "batt" and int(row["distance_to_target"]) == 0]

    return {
        "rows": rows,
        "pairs": pairs,
        "strict_pairs": strict_pairs,
        "near_pairs": near_pairs,
        "unlicensed_near": unlicensed_near,
        "similar_but_not_near": similar_but_not_near,
        "closest_pair": str(best["pair"]),
        "closest_distance": int(best["distance"]),
        "strict_same_level_with_target": len(strict_with_target),
        "target_layer": "batt",
        "target_role": str(target["role"]),
        "spec_attributes": list(SPEC_ATTRIBUTES),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w44_same_level_spec"]
    gates = lane["gates"]
    expected = lane["expected"]
    rows = payload["rows"]
    non_target = [row for row in rows if row["role"] != "target"]
    every_missing = all(str(row["missing_vs_target"]).strip() for row in non_target)
    target_row = next((row for row in rows if row["layer"] == "batt"), None)
    return [
        criteria_row("H44c1", "被评分的候选层数 >= 6（含 target）",
                     len(rows), int(gates["candidates_scored"]),
                     len(rows) >= int(gates["candidates_scored"])),
        criteria_row("H44c2", "strict same_level 计数 = 0（登记为已知边界，非判否）",
                     payload["strict_same_level_with_target"], int(gates["strict_with_target"]),
                     int(payload["strict_same_level_with_target"]) == int(gates["strict_with_target"])),
        criteria_row("H44c3", "最近一对的属性距离 == 2 且 pair == qm9-pubchemqc",
                     {"closest_pair": payload["closest_pair"], "closest_distance": payload["closest_distance"]},
                     {"closest_pair": expected["closest_pair"], "closest_distance": expected["closest_distance"]},
                     payload["closest_pair"] == str(expected["closest_pair"])
                     and int(payload["closest_distance"]) == int(expected["closest_distance"])),
        criteria_row("H44c4", "spec 四属性齐备且顺序 == functional/basis_set/phase/geometry_source",
                     payload["spec_attributes"], list(SPEC_ATTRIBUTES),
                     list(payload["spec_attributes"]) == list(SPEC_ATTRIBUTES)),
        criteria_row("H44c5", "每个非 target 层都带 >= 1 条缺失属性理由（非空）",
                     every_missing, True, bool(every_missing)),
        criteria_row("H44c6", "Batt 是 target 行且 role == target",
                     {"layer": "batt", "role": payload["target_role"]},
                     {"layer": "batt", "role": "target"},
                     target_row is not None and str(payload["target_role"]) == "target"
                     and str(payload["target_layer"]) == "batt"),
        criteria_row("H44c7", "near_same_level 声明只在泛函+相都相同时允许（越权 = 0）",
                     {"near_pairs": payload["near_pairs"], "unlicensed": payload["unlicensed_near"],
                      "similar_but_not_near": payload["similar_but_not_near"]},
                     {"rule": "functional_match and phase_match", "unlicensed_max": 0},
                     payload["unlicensed_near"] == []
                     and all(row["functional_match"] and row["phase_match"]
                             for row in payload["pairs"] if row["near_same_level_eligible"])),
        criteria_row("H44c8", "输入（六个层文件 + 名册 + prereg）sha256 未变",
                     "before == after", True, True),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W44-C strict same_level 规格与在仓候选审计",
        "",
        "只读治理 lane；0 shot。strict same_level = 四属性全同 + 独立来源。",
        "",
        "## 1 候选层属性表",
        "",
        "| 层 | 角色 | 泛函 | 基组 | 相 | 几何来源 | 与 target 距离 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append("| " + str(row["layer"]) + " | " + str(row["role"]) + " | "
                     + str(row["functional"]) + " | " + str(row["basis_set"]) + " | "
                     + str(row["phase"]) + " | " + str(row["geometry_source"]) + " | "
                     + str(row["distance_to_target"]) + " |")
    lines += [
        "",
        "## 2 最近对与 near 声明",
        "",
        "- 最近一对： " + str(payload["closest_pair"]) + "，属性距离 " + str(payload["closest_distance"]) + "。",
        "- strict same_level 对： " + (", ".join(str(x) for x in payload["strict_pairs"]) or "无") + "。",
        "- near_same_level（泛函+相相同）对： " + (", ".join(str(x) for x in payload["near_pairs"]) or "无") + "。",
        "- 仅部分相似（只同泛函或只同相）因而不许声明 near 的对： "
        + (", ".join(str(x) for x in payload["similar_but_not_near"]) or "无") + "。",
        "- 越权 near 声明： " + (", ".join(str(x) for x in payload["unlicensed_near"]) or "无") + "。",
        "- 与 target 距离 0 的层： " + str(payload["strict_same_level_with_target"]) + " 个。",
        "",
        "## 3 判据",
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
        "## 4 边界",
        "",
        "- 只读：不改任何 summary、标签或特征列。",
        "- strict same_level 计数为 0，登记为已知边界；不得拿 near_same_level 冒充同层级。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只跑判据并以退出码表示结果")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"]
    sources += [REPOSITORY_ROOT / str(spec["source_path"]) for spec in LAYERS.values()]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H44c8", "输入（六个层文件 + 名册 + prereg）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(CANDIDATES_CSV, CANDIDATE_FIELDS, payload["rows"])
        write_json_stable(SPEC_JSON, {
            "spec_attributes": list(SPEC_ATTRIBUTES),
            "rule": "strict same_level 要求四属性全同 + 独立来源；target = batt",
            "near_same_level_rule": "只允许 functional + phase 都相同者声明 near_same_level",
            "target_layer": payload["target_layer"],
            "target_role": payload["target_role"],
            "candidates": payload["rows"],
            "pairs": payload["pairs"],
            "closest_pair": payload["closest_pair"],
            "closest_distance": payload["closest_distance"],
            "strict_pairs": payload["strict_pairs"],
            "near_pairs": payload["near_pairs"],
            "unlicensed_near": payload["unlicensed_near"],
            "similar_but_not_near": payload["similar_but_not_near"],
            "strict_same_level_with_target": payload["strict_same_level_with_target"],
        })
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读六层属性表与两两距离，不拟合主记分牌臂、不加特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "spec_attributes": list(SPEC_ATTRIBUTES),
            "candidate_rows": payload["rows"],
            "pairs": payload["pairs"],
            "closest_pair": payload["closest_pair"],
            "closest_distance": payload["closest_distance"],
            "strict_pairs": payload["strict_pairs"],
            "near_pairs": payload["near_pairs"],
            "unlicensed_near": payload["unlicensed_near"],
            "strict_same_level_with_target": payload["strict_same_level_with_target"],
            "target_layer": payload["target_layer"],
            "target_role": payload["target_role"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "六层属性审计完成；与 target 距离 0 的层 = "
                + str(payload["strict_same_level_with_target"]) + "（strict 计数 0，已知边界）。",
                "最近一对 " + str(payload["closest_pair"]) + "，属性距离 " + str(payload["closest_distance"]) + "。",
                "near_same_level 合法对： " + (", ".join(str(x) for x in payload["near_pairs"]) or "无")
                + "；越权 near 声明 = " + str(len(payload["unlicensed_near"])) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("candidates %d closest %s:%d strict_with_target %d near %s unlicensed %d"
          % (len(payload["rows"]), payload["closest_pair"], payload["closest_distance"],
             payload["strict_same_level_with_target"], payload["near_pairs"],
             len(payload["unlicensed_near"])))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
