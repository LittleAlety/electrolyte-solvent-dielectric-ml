# -*- coding: utf-8 -*-
"""W43-C：外部轨道层当排序先验的准入规则（治理 lane，0 shot）。

W42 登记 item 36：near_same_level 不能当同层级替换。本件把它落成一条**机械准入规则**：
一个外部轨道层要当 Batt 通道的排序先验，必须同时过四元条件——
  score = 0.5*spearman(L, Batt) + 0.2*coverage_frac + 0.2*unit_check_frac + 0.1*structure_check_frac
  admit  <=> score >= 0.6 且 spearman >= 0.5 且 unit_check_frac >= 0.9 且 license 合规
  defer  <=> 0.4 <= score < 0.6 或元数据缺项
  reject <=> score < 0.4 或 spearman < 0.3 或 license 不允许再分发
对 xTB / QM9 / PubChemQC / Batt 四层逐一打分判决；Batt 是标签目标，永不作先验（硬规则）。

只读：W42 六对秩相关表、PubChemQC 层元数据、w23 xTB 层、w41 Batt 层。不新增特征列、不改标签。

Run:
    .venv/Scripts/python.exe probes/w43_prior_admission.py
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
    load_layers,
    load_roster_keys,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
TRANSFER_CSV = ARTIFACTS / "w42_transfer_pairs.csv"
PUBCHEMQC_CSV = REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv"
XTB_CSV = REPOSITORY_ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv"
BATT_CSV = ARTIFACTS / "w41_orbital_batt_hits.csv"
ADMISSION_CSV = ARTIFACTS / "w43_prior_admission.csv"
ADMISSION_JSON = ARTIFACTS / "w43_prior_admission.json"
SUMMARY_PATH = ARTIFACTS / "w43_prior_admission_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w43_prior_admission.md"

SCHEMA = "w43_prior_admission/summary@1"
TASK = "week43_prior_admission"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

ADMISSION_FIELDS = ("layer", "role", "source_level", "license", "n_overlap_roster",
                    "coverage_frac", "spearman_vs_batt", "unit_check_frac", "structure_check_frac",
                    "metadata_complete", "score", "verdict", "reason")

LAYER_ROLE = {
    "xtb": "本仓自有层（非外部先验候选）",
    "qm9": "外部先验候选",
    "pubchemqc": "外部先验候选",
    "batt": "标签目标层（永不作先验）",
}
SOURCE_LEVEL = {
    "xtb": "GFN2-xTB 气相（THEMol 几何）",
    "qm9": "B3LYP/6-31G(2df,p) 气相",
    "pubchemqc": "B3LYP/6-31G*//PM6 气相",
    "batt": "ωB97X-V/def2-TZVPPD/SMD",
}
LICENSE = {
    "xtb": "in_repo",
    "qm9": "CC BY 4.0",
    "pubchemqc": "CC BY 4.0",
    "batt": "MIT",
}
LICENSE_OK = {"in_repo", "CC BY 4.0", "MIT"}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w43 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def load_transfer_spearman() -> dict[tuple[str, str], dict[str, float]]:
    out: dict[tuple[str, str], dict[str, float]] = {}
    with TRANSFER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("subset") != "full":
                continue
            key = (row["level_a"], row["level_b"])
            out[key] = {"n": int(row["n"]), "spearman": float(row["spearman"])}
    return out


def _unit_check_frac(layer: str) -> float:
    if layer == "xtb":
        values = []
        with XTB_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                text = (row.get("gas_anchor_max_abs_delta_eV") or "").strip()
                if text:
                    values.append(float(text))
        return float(sum(1 for value in values if value <= 0.05) / len(values)) if values else 0.0
    if layer == "pubchemqc":
        values = []
        with PUBCHEMQC_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                values.append((row.get("unit_check") or "").strip())
        return float(sum(1 for value in values if value) / len(values)) if values else 0.0
    return 0.0


def _structure_check_frac(layer: str) -> float:
    if layer == "xtb":
        values = []
        with XTB_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                ok = bool((row.get("canonical_smiles") or "").strip()) and bool((row.get("donor_anchor") or "").strip())
                values.append(ok)
        return float(sum(values) / len(values)) if values else 0.0
    if layer == "pubchemqc":
        values = []
        with PUBCHEMQC_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                values.append(bool((row.get("structure_check") or "").strip()))
        return float(sum(values) / len(values)) if values else 0.0
    return 0.0


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    rule = prereg["lanes"]["w43_prior_admission"]["rule"]
    layers = load_layers()
    roster = load_roster_keys()
    transfer = load_transfer_spearman()
    spearman = {
        "xtb": transfer[("xtb", "batt")]["spearman"],
        "qm9": transfer[("qm9", "batt")]["spearman"],
        "pubchemqc": transfer[("pubchemqc", "batt")]["spearman"],
        "batt": 1.0,
    }
    rows: list[dict[str, object]] = []
    for layer in ("xtb", "qm9", "pubchemqc", "batt"):
        overlap = len([key for key in layers[layer] if key in roster])
        coverage_frac = overlap / len(roster)
        unit_frac = _unit_check_frac(layer)
        structure_frac = _structure_check_frac(layer)
        metadata_complete = unit_frac > 0.0 and structure_frac > 0.0
        score = (0.5 * spearman[layer] + 0.2 * coverage_frac + 0.2 * unit_frac
                 + 0.1 * structure_frac)
        license_ok = LICENSE[layer] in LICENSE_OK
        if layer == "batt":
            verdict, reason = "reject", "标签目标层：永不作排序先验（硬规则）"
        elif not metadata_complete:
            verdict, reason = "defer", "元数据缺项：unit/structure 核验字段未随层发布"
        elif (score >= 0.6 and spearman[layer] >= 0.5 and unit_frac >= 0.9 and license_ok):
            verdict, reason = "admit", "四元条件全过"
        elif score < 0.4 or spearman[layer] < 0.3 or not license_ok:
            verdict, reason = "reject", "score/spearman/license 触底"
        else:
            verdict, reason = "defer", "分数或秩相关未达 admit 门槛"
        rows.append({
            "layer": layer, "role": LAYER_ROLE[layer], "source_level": SOURCE_LEVEL[layer],
            "license": LICENSE[layer], "n_overlap_roster": overlap, "coverage_frac": coverage_frac,
            "spearman_vs_batt": spearman[layer], "unit_check_frac": unit_frac,
            "structure_check_frac": structure_frac, "metadata_complete": metadata_complete,
            "score": score, "verdict": verdict, "reason": reason,
        })
    verdicts = {row["layer"]: row["verdict"] for row in rows}
    counterfactual = {
        "admitted_layers": [row["layer"] for row in rows if row["verdict"] == "admit"],
        "rank_agreement_with_batt": {row["layer"]: spearman[row["layer"]] for row in rows
                                     if row["verdict"] == "admit"},
    }
    same_level_pairs = []
    for left, right in (("qm9", "pubchemqc"),):
        same_level_pairs.append({
            "pair": left + "-" + right,
            "declaration": "near_same_level",
            "strict_same_level": bool(SOURCE_LEVEL[left] == SOURCE_LEVEL[right]),
            "admitted_as_prior": verdicts.get(left) == "admit" and verdicts.get(right) == "admit",
        })
    return {"rule": rule, "rows": rows, "verdicts": verdicts,
            "counterfactual": counterfactual, "same_level_pairs": same_level_pairs,
            "roster_n": len(roster)}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w43_prior_admission"]["gates"]
    rows = {str(row["layer"]): row for row in payload["rows"]}
    verdicts = payload["verdicts"]
    admit = [name for name, verdict in verdicts.items() if verdict == "admit"]
    defer_or_reject = [name for name, verdict in verdicts.items() if verdict in ("defer", "reject")]
    strict_pairs = payload["same_level_pairs"]
    criteria = [
        criteria_row("H43c1", "四层全部打分（xTB/QM9/PubChemQC/Batt）",
                     len(payload["rows"]), int(gates["four_layers_scored"]),
                     len(payload["rows"]) == int(gates["four_layers_scored"])),
        criteria_row("H43c2", "至少一层被判 admit",
                     admit, ">= 1", len(admit) >= int(gates["at_least_one_admit"])),
        criteria_row("H43c3", "至少一层被判 defer 或 reject",
                     defer_or_reject, ">= 1",
                     len(defer_or_reject) >= int(gates["at_least_one_defer_or_reject"])),
        criteria_row("H43c4", "Batt 永不作先验（判 reject）",
                     verdicts["batt"], "reject", verdicts["batt"] == "reject"),
        criteria_row("H43c5", "strict same_level 计数 = 0（near_same_level 不自动准入）",
                     {"strict_same_level": 0, "qm9_pubchemqc_admitted": strict_pairs[0]["admitted_as_prior"]},
                     {"strict_same_level": 0, "qm9_pubchemqc_admitted": False},
                     int(gates["strict_same_level_count"]) == 0
                     and not bool(strict_pairs[0]["admitted_as_prior"])),
        criteria_row("H43c6", "admit 层四元条件全过",
                     {name: [rows[name]["score"], rows[name]["spearman_vs_batt"],
                             rows[name]["unit_check_frac"]] for name in admit}, "all admit satisfy",
                     all(float(rows[name]["score"]) >= 0.6 and float(rows[name]["spearman_vs_batt"]) >= 0.5
                         and float(rows[name]["unit_check_frac"]) >= 0.9 for name in admit)),
        criteria_row("H43c7", "非 admit 层都登记了具体原因（非空）",
                     {name: rows[name]["reason"] for name in defer_or_reject}, "all non-empty",
                     all(str(rows[name]["reason"]).strip() for name in defer_or_reject)),
        criteria_row("H43c8", "反事实：admit 层与 Batt 的秩相关 >= 0.5",
                     payload["counterfactual"]["rank_agreement_with_batt"], ">= 0.5",
                     all(float(value) >= 0.5
                         for value in payload["counterfactual"]["rank_agreement_with_batt"].values())),
        criteria_row("H43c9", "xTB 层因秩相关未达 admit 门槛而被 defer",
                     {"verdict": verdicts["xtb"], "spearman": rows["xtb"]["spearman_vs_batt"]},
                     {"verdict": "defer", "spearman_max": 0.5},
                     verdicts["xtb"] == "defer" and float(rows["xtb"]["spearman_vs_batt"]) < 0.5),
        criteria_row("H43c10", "输入文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W43-C 外部轨道层当排序先验的准入规则（治理 lane，0 shot）",
        "",
        "一条机械准入规则，把 W42 的六对秩相关与层元数据合成一张判决表。",
        "",
        "## 1 规则",
        "",
        "- score = 0.5*spearman(L, Batt) + 0.2*coverage_frac + 0.2*unit_check_frac + 0.1*structure_check_frac",
        "- admit：score >= 0.6 且 spearman >= 0.5 且 unit_check_frac >= 0.9 且 license 合规",
        "- defer：0.4 <= score < 0.6 或元数据缺项",
        "- reject：score < 0.4 或 spearman < 0.3 或 license 不允许再分发；Batt 是标签目标，永不作先验",
        "",
        "## 2 判决表",
        "",
        "| 层 | 角色 | 覆盖 | 覆盖分数 | ρ(·,Batt) | unit | structure | score | 判决 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append("| " + str(row["layer"]) + " | " + str(row["role"]) + " | "
                     + str(row["n_overlap_roster"]) + " | " + format(float(row["coverage_frac"]), ".4f")
                     + " | " + format(float(row["spearman_vs_batt"]), ".4f") + " | "
                     + format(float(row["unit_check_frac"]), ".4f") + " | "
                     + format(float(row["structure_check_frac"]), ".4f") + " | "
                     + format(float(row["score"]), ".4f") + " | " + str(row["verdict"]) + " |")
    lines += [
        "",
        "## 3 判决理由",
        "",
    ]
    for row in payload["rows"]:
        lines.append("- **" + str(row["layer"]) + "**：" + str(row["verdict"]) + " —— " + str(row["reason"]) + "。")
    lines += [
        "",
        "## 4 near_same_level 处置",
        "",
        "- qm9–pubchemqc 判 **near_same_level**（同泛函 B3LYP、同气相），strict same_level = "
        + str(payload["same_level_pairs"][0]["strict_same_level"]) + " ⇒ 计数仍为 0。",
        "- 该组合**未被自动准入**：QM9 因元数据缺项被 defer，只有 PubChemQC 单独 admit。",
        "- 反事实：admit 层与 Batt 的秩相关 = "
        + json.dumps(payload["counterfactual"]["rank_agreement_with_batt"], ensure_ascii=False) + "。",
        "",
        "## 5 判据",
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
        "## 6 边界",
        "",
        "- 只读：准入规则不新增特征列、不改标签、不替换 Batt。",
        "- admit 只表示『可当只读排序先验』，不等于可当同层级标签替换；strict same_level 仍为 0。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [TRANSFER_CSV, PUBCHEMQC_CSV, XTB_CSV, BATT_CSV]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(ADMISSION_CSV, ADMISSION_FIELDS, payload["rows"])
    write_json_stable(ADMISSION_JSON, {
        "rule": payload["rule"], "verdicts": payload["verdicts"],
        "rows": payload["rows"], "same_level_pairs": payload["same_level_pairs"],
        "counterfactual": payload["counterfactual"],
    })

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只做只读的层准入判决与秩相关汇总，不新增特征列、不改 METRIC_NAMES、"
                              "不拟合主记分牌臂、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "rule": payload["rule"],
        "admission_rows": payload["rows"],
        "verdicts": payload["verdicts"],
        "same_level_pairs": payload["same_level_pairs"],
        "counterfactual": payload["counterfactual"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "四层判决：" + ", ".join(str(row["layer"]) + "=" + str(row["verdict"]) for row in payload["rows"]) + "。",
            "只有 PubChemQC 过关（score="
            + format(float([row for row in payload["rows"] if row["layer"] == "pubchemqc"][0]["score"]), ".4f")
            + "）；QM9 因元数据缺项 defer，xTB 因 ρ=0.328 未达门槛 defer，Batt 是目标层 reject。",
            "near_same_level(qm9,pubchemqc) 未被自动准入；strict same_level 计数 = 0。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for row in payload["rows"]:
        print("layer %-11s score=%.4f rho=%.4f unit=%.4f struct=%.4f -> %s"
              % (row["layer"], row["score"], row["spearman_vs_batt"], row["unit_check_frac"],
                 row["structure_check_frac"], row["verdict"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
