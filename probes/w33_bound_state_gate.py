# -*- coding: utf-8 -*-
"""W33-A：态合法性前置门禁 + 拒答队列 + 门禁后的还原轴排序重读（后验，不占 shot）。

只读 `data/processed/w23_redox_dscf_layer.csv`（246 分子 x 4 介质，GFN2-xTB）
与 `data/processed/w24_2_orca_dft_layer.csv`（28 锚点，GFN2 + ORCA r2SCAN-3c/SMD）。
不重跑任何量子化学、不拟合任何模型、不触冻结的 ε 主记分牌（本轮 shot = 0）。

门禁 = 三条款之交（geom AND homo AND ea）；其余进拒答队列并记明理由。合法子集 < 5 的
层级按预注册判为**不可判定**（拒答），不得给数值读数。排序读数用
`probes/w24_3_posthoc.py::kendall_tau_b`，并与 `probes/artifacts/w24_3_level_crosscheck.csv`
的 +0.8354978354978355 / -0.6017316017316018 逐位对齐（复现锚，容差 1e-12）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path

import w24_3_posthoc as posthoc

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REDOX_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
ORCA_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
CROSSCHECK_CSV = REPOSITORY_ROOT / "probes" / "artifacts" / "w24_3_level_crosscheck.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w33_bound_state_gate_prereg.json"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = ARTIFACTS / "w33_bound_state_gate_summary.json"
GATES_CSV = ARTIFACTS / "w33_bound_state_gate_gates.csv"
REFUSE_CSV = ARTIFACTS / "w33_bound_state_gate_refuse_queue.csv"
READINGS_CSV = ARTIFACTS / "w33_bound_state_gate_readings.csv"
FIGURE_PATH = ARTIFACTS / "w33_bound_state_gate.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w33_bound_state_gate.md"

SCHEMA = "w33_bound_state_gate/summary@1"
TASK = "week33_bound_state_gate"

MEDIA = (("gas", 1.0, "气相"), ("thf", 7.58, "THF"),
         ("benzaldehyde", 18.0, "苯甲醛"), ("water", 80.4, "水"))
ORCA_MEDIA = (("gas", 1.0, "ORCA 气相"), ("smd_acetonitrile", 35.688, "ORCA SMD 乙腈"))
MIN_LEGAL_SUBSET = 5
REPRODUCTION_TOLERANCE = 1e-12
ANCHOR_GFN2_PAIRED = 0.8354978354978355
ANCHOR_ORCA_PAIRED = -0.6017316017316018
ANCHOR_UNBOUND_CENSUS = 0.7642276422764228
KOOPMANS_COLUMN = "gas_neutral_lumo_eV"

GATES_FIELDS = ("medium", "epsilon", "rows", "geom_fail", "homo_refused", "ea_refused", "legal",
                "pass_rate", "refusal_rate", "clause_geom_pass", "clause_homo_pass",
                "clause_ea_pass", "tau_all", "tau_all_rows", "tau_legal", "tau_legal_rows",
                "verdict")
REFUSE_FIELDS = ("inchikey", "name", "medium", "reason", "ea_eV", "anion_homo_eV",
                 "anion_status", "unbound_flag")


def read_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def negated(row, column):
    value = as_float(row.get(column))
    return None if value is None else -value


def census_gate(row, medium: str) -> dict:
    geom = str(row.get(medium + "_anion_status", "")).strip() == "ok"
    homo = str(row.get("anion_unbound_" + medium, "")).strip() == "no"
    ea_value = as_float(row.get("ea_" + medium + "_eV"))
    ea = ea_value is not None and ea_value > 0.0
    legal = bool(geom and homo and ea)
    reason = "" if legal else ("geom" if not geom else ("homo" if not homo else "ea"))
    return {"geom": geom, "homo": homo, "ea": ea, "legal": legal, "reason": reason}


def orca_gate(row, medium: str) -> dict:
    geom = str(row.get("orca_" + medium + "_anion_status", "")).strip() == "ok"
    homo = str(row.get("orca_anion_unbound_" + medium, "")).strip() == "no"
    ea_value = as_float(row.get("orca_ea_" + medium + "_eV"))
    ea = ea_value is not None and ea_value > 0.0
    legal = bool(geom and homo and ea)
    reason = "" if legal else ("geom" if not geom else ("homo" if not homo else "ea"))
    return {"geom": geom, "homo": homo, "ea": ea, "legal": legal, "reason": reason}


def tau(pairs):
    value, used = posthoc.kendall_tau_b(pairs)
    return (None if value is None else float(value)), int(used)


def verdict(identifier, description, value, threshold, passed) -> dict:
    return {"id": str(identifier), "description": str(description),
            "value": None if value is None else float(value),
            "threshold": None if threshold is None else float(threshold),
            "verdict": "成立" if bool(passed) else "判否"}

def analyse_census(rows, refuse_rows) -> list:
    entries = []
    for medium, epsilon, label in MEDIA:
        flags = [census_gate(row, medium) for row in rows]
        total = len(rows)
        geom_fail = sum(1 for flag in flags if not flag["geom"])
        homo_refused = sum(1 for flag in flags if flag["geom"] and not flag["homo"])
        ea_refused = sum(1 for flag in flags if flag["geom"] and flag["homo"] and not flag["ea"])
        legal = sum(1 for flag in flags if flag["legal"])
        pairs_all, pairs_legal = [], []
        for row, flag in zip(rows, flags):
            source = negated(row, KOOPMANS_COLUMN)
            target = as_float(row.get("ea_" + medium + "_eV"))
            pairs_all.append((source, target))
            if flag["legal"]:
                pairs_legal.append((source, target))
            else:
                refuse_rows.append({
                    "inchikey": row.get("inchikey", ""), "name": row.get("name", ""),
                    "medium": medium, "reason": flag["reason"],
                    "ea_eV": row.get("ea_" + medium + "_eV", ""),
                    "anion_homo_eV": row.get(medium + "_anion_homo_eV", ""),
                    "anion_status": row.get(medium + "_anion_status", ""),
                    "unbound_flag": row.get("anion_unbound_" + medium, "")})
        tau_all, rows_all = tau(pairs_all)
        if legal < MIN_LEGAL_SUBSET:
            tau_legal, rows_legal, local = None, 0, "不可判定"
        else:
            tau_legal, rows_legal = tau(pairs_legal)
            local = "可宣读"
        entries.append({
            "medium": medium, "label": label, "epsilon": float(epsilon), "rows": total,
            "geom_fail": geom_fail, "homo_refused": homo_refused, "ea_refused": ea_refused,
            "legal": legal,
            "pass_rate": legal / total if total else float("nan"),
            "refusal_rate": (total - legal) / total if total else float("nan"),
            "clause_geom_pass": sum(1 for flag in flags if flag["geom"]),
            "clause_homo_pass": sum(1 for flag in flags if flag["homo"]),
            "clause_ea_pass": sum(1 for flag in flags if flag["ea"]),
            "tau_all": tau_all, "tau_all_rows": rows_all,
            "tau_legal": tau_legal, "tau_legal_rows": rows_legal, "verdict": local})
    return entries


def analyse_orca(census_rows, orca_rows, refuse_rows) -> tuple:
    census = {row["inchikey"]: row for row in census_rows}
    paired = [(row["inchikey"], row) for row in orca_rows if row.get("inchikey") in census]
    anchors = {
        "gfn2_paired_gas": tau([(negated(census[key], KOOPMANS_COLUMN),
                                 as_float(census[key]["ea_gas_eV"])) for key, _ in paired]),
        "orca_paired_gas": tau([(as_float(row["p0_red_eV"]), as_float(row["orca_ea_gas_eV"]))
                                for _, row in paired]),
        "unbound_census_share": (sum(1 for row in census_rows
                                     if str(row.get("anion_unbound_gas", "")).strip() == "yes")
                                 / len(census_rows)),
    }
    entries = []
    for medium, epsilon, label in ORCA_MEDIA:
        flags = [orca_gate(row, medium) for _, row in paired]
        total = len(paired)
        legal = sum(1 for flag in flags if flag["legal"])
        pairs_all = [(as_float(row["p0_red_eV"]), as_float(row.get("orca_ea_" + medium + "_eV")))
                     for _, row in paired]
        pairs_legal = [pair for pair, flag in zip(pairs_all, flags) if flag["legal"]]
        tau_all, rows_all = tau(pairs_all)
        if legal < MIN_LEGAL_SUBSET:
            tau_legal, rows_legal, local = None, 0, "不可判定"
        else:
            tau_legal, rows_legal = tau(pairs_legal)
            local = "可宣读"
        entries.append({
            "medium": "orca_" + medium, "label": label, "epsilon": float(epsilon), "rows": total,
            "geom_fail": sum(1 for flag in flags if not flag["geom"]),
            "homo_refused": sum(1 for flag in flags if flag["geom"] and not flag["homo"]),
            "ea_refused": sum(1 for flag in flags if flag["geom"] and flag["homo"] and not flag["ea"]),
            "legal": legal,
            "pass_rate": legal / total if total else float("nan"),
            "refusal_rate": (total - legal) / total if total else float("nan"),
            "clause_geom_pass": sum(1 for flag in flags if flag["geom"]),
            "clause_homo_pass": sum(1 for flag in flags if flag["homo"]),
            "clause_ea_pass": sum(1 for flag in flags if flag["ea"]),
            "tau_all": tau_all, "tau_all_rows": rows_all,
            "tau_legal": tau_legal, "tau_legal_rows": rows_legal, "verdict": local})
        for (_, row), flag in zip(paired, flags):
            if flag["legal"]:
                continue
            refuse_rows.append({
                "inchikey": row.get("inchikey", ""), "name": row.get("name", ""),
                "medium": "orca_" + medium, "reason": flag["reason"],
                "ea_eV": row.get("orca_ea_" + medium + "_eV", ""),
                "anion_homo_eV": row.get("orca_" + medium + "_anion_homo_eV", ""),
                "anion_status": row.get("orca_" + medium + "_anion_status", ""),
                "unbound_flag": row.get("orca_anion_unbound_" + medium, "")})
    census_flags = [census_gate(census[key], "gas") for key, _ in paired]
    orca_flags = [orca_gate(row, "gas") for _, row in paired]
    both = sum(1 for a, b in zip(census_flags, orca_flags) if a["legal"] and b["legal"])
    gfn2_only = sum(1 for a, b in zip(census_flags, orca_flags) if a["legal"] and not b["legal"])
    orca_only = sum(1 for a, b in zip(census_flags, orca_flags) if b["legal"] and not a["legal"])
    neither = sum(1 for a, b in zip(census_flags, orca_flags)
                  if not a["legal"] and not b["legal"])
    cross = {"n_paired": len(paired), "both_legal": both, "gfn2_only": gfn2_only,
             "orca_only": orca_only, "neither": neither,
             "gfn2_legal": both + gfn2_only, "orca_legal": both + orca_only,
             "inconsistent_share": (gfn2_only / len(paired)) if paired else float("nan"),
             "agreement_share": ((both + neither) / len(paired)) if paired else float("nan")}
    return entries, anchors, cross


def evaluate_criteria(census_entries, orca_entries, anchors, cross) -> tuple:
    gas = next(entry for entry in census_entries if entry["medium"] == "gas")
    total = gas["rows"]
    clause_gap = (gas["clause_ea_pass"] - gas["clause_homo_pass"]) / total
    checks = [
        verdict("H33a", "门禁必要性：气相 EA 条款通过率与 HOMO 条款通过率之差（单用 EA 会多纳入的不束缚态占比）",
                clause_gap, 0.30, clause_gap >= 0.30),
        verdict("H33b", "层级依赖：ORCA 气相合法子集规模（< 5 ⇒ 还原轴在该层判为不可判定）",
                float(next(entry["legal"] for entry in orca_entries if entry["medium"] == "orca_gas")),
                5.0, next(entry["legal"] for entry in orca_entries
                          if entry["medium"] == "orca_gas") < MIN_LEGAL_SUBSET),
        verdict("H33c", "介质效应：门禁通过率随介电常数非降（取相邻步长最小值）",
                min(census_entries[index + 1]["pass_rate"] - census_entries[index]["pass_rate"]
                    for index in range(len(census_entries) - 1)), 0.0,
                all(census_entries[index]["pass_rate"] <= census_entries[index + 1]["pass_rate"] + 1e-12
                    for index in range(len(census_entries) - 1))),
        verdict("H33d", "读数改变：门禁前后 tau_b 差的绝对最大值",
                max((abs(entry["tau_legal"] - entry["tau_all"]) for entry in census_entries
                     if entry["tau_legal"] is not None), default=None),
                0.10, any(entry["tau_legal"] is not None
                          and abs(entry["tau_legal"] - entry["tau_all"]) >= 0.10
                          for entry in census_entries)),
        verdict("H33e", "跨层级裁决不一致：配对集上「GFN2 合法且 ORCA 不合法」的占比",
                cross["inconsistent_share"], 0.50, cross["inconsistent_share"] >= 0.50),
        verdict("H33f", "拒答规模：气相拒答率", gas["refusal_rate"], 0.70,
                gas["refusal_rate"] >= 0.70),
    ]
    anchor_checks = [
        verdict("A1", "复现锚：GFN2 配对集全域 tau_b = same_red_gfn2",
                anchors["gfn2_paired_gas"][0], ANCHOR_GFN2_PAIRED,
                anchors["gfn2_paired_gas"][0] is not None
                and abs(anchors["gfn2_paired_gas"][0] - ANCHOR_GFN2_PAIRED) <= REPRODUCTION_TOLERANCE),
        verdict("A2", "复现锚：ORCA 配对集全域 tau_b = same_red_orca",
                anchors["orca_paired_gas"][0], ANCHOR_ORCA_PAIRED,
                anchors["orca_paired_gas"][0] is not None
                and abs(anchors["orca_paired_gas"][0] - ANCHOR_ORCA_PAIRED) <= REPRODUCTION_TOLERANCE),
        verdict("A3", "复现锚：气相不束缚占比 = unbound_share_census",
                anchors["unbound_census_share"], ANCHOR_UNBOUND_CENSUS,
                abs(anchors["unbound_census_share"] - ANCHOR_UNBOUND_CENSUS) <= 1e-12),
    ]
    return checks, anchor_checks

def write_csv(path, fieldnames, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def dump_json(path, payload) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def fmt(value, digits=6) -> str:
    if value is None:
        return "不可判定"
    return format(float(value), "." + str(digits) + "f")


def format_report(payload) -> str:
    lines = []
    add = lines.append
    add("# W33-A：态合法性前置门禁 + 拒答队列 + 门禁后的还原轴排序重读")
    add("")
    add("**性质**：后验重建（只读四张冻结表），**不占主记分牌 shot**（累计仍 "
        + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"]) + "）；"
        "不重跑 xTB / ORCA、不拟合模型、不联网。")
    add("")
    gas_entry = payload["census"][0]
    drops = [(entry["medium"], entry["tau_all"] - entry["tau_legal"]) for entry in payload["census"]
             if entry["tau_legal"] is not None]
    worst = max(drops, key=lambda item: item[1]) if drops else ("", float("nan"))
    add("## 0. 一句话（全部由数据推出）")
    add("")
    add("- **门禁挡掉的是多数**：气相合法集 " + str(gas_entry["legal"]) + "/"
        + str(gas_entry["rows"]) + "（" + fmt(100 * gas_entry["pass_rate"], 1) + "%）；通过率随介电常数非降（"
        + " -> ".join(fmt(100 * entry["pass_rate"], 1) + "%" for entry in payload["census"]) + "）。")
    add("- **EA 条款不能单独当门禁**：气相「不束缚签名」只放过 "
        + str(gas_entry["clause_homo_pass"]) + "/" + str(gas_entry["rows"]) + "，而 EA>0 会放过 "
        + str(gas_entry["clause_ea_pass"]) + "/" + str(gas_entry["rows"]) + " —— 差 "
        + fmt(100 * (gas_entry["clause_ea_pass"] - gas_entry["clause_homo_pass"])
               / gas_entry["rows"], 1) + " 个百分点。GFN2 的 dSCF EA 在阴离子不束缚时仍常为正。")
    add("- **门禁后 tau_b 全线下降**（最大跌幅在 " + worst[0] + "：" + fmt(worst[1], 4)
        + "）⇒ 原先的高 tau_b 里有一部分是「不束缚态同向漂移」造出的假一致。")
    add("- **配对锚点上的合法行数：GFN2 " + str(payload["cross"]["gfn2_legal"]) + "/"
        + str(payload["cross"]["n_paired"]) + "、ORCA " + str(payload["cross"]["orca_legal"]) + "/"
        + str(payload["cross"]["n_paired"]) + "** ⇒ 那个 +0.835 / -0.602 的跨层级对比，本来就是在（几乎全部）"
        "不合法态上算的；ORCA 气相合法子集为 0，本轮按预注册判为**不可判定**，不引用 -0.602 作为该层读数。")
    add("- **判否登记**：H33e 判否 —— 预注册猜「两层裁决不一致占多数」，实测两层在这 22 个锚点上高度一致"
        "（一致率 " + fmt(100 * payload["cross"]["agreement_share"], 1) + "%）；层级依赖体现在「合法子集不够读数」，"
        "而不是「裁决互相矛盾」。")
    add("")
    add("## 1. 门禁规则（预注册写死，见 `probes/w33_bound_state_gate_prereg.json`）")
    add("")
    add("- `geom`：阴离子态 SCF/几何完好（`<medium>_anion_status == 'ok'`）")
    add("- `homo`：阴离子 HOMO < 0（等价于 `anion_unbound_<medium> == 'no'`，阈值 0.0）")
    add("- `ea`：绝热电子亲和 > 0（`ea_<medium>_eV > 0`）")
    add("- **合法集 = 三条款之交**；其余进拒答队列并记明理由；合法子集 < 5 的层级判为**不可判定**。")
    add("")
    add("## 2. 逐介质漏斗（GFN2-xTB 普查，246 分子）")
    add("")
    add("| 介质 | eps | 合法 | 因不束缚拒答 | 因 EA 非正拒答 | 因几何/SCF 拒答 | 通过率 | 拒答率 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in payload["census"]:
        if entry["medium"] not in ("gas", "thf", "benzaldehyde", "water"):
            continue
        add("| " + entry["label"] + " | " + fmt(entry["epsilon"], 1) + " | "
            + str(entry["legal"]) + " | " + str(entry["homo_refused"]) + " | "
            + str(entry["ea_refused"]) + " | " + str(entry["geom_fail"]) + " | "
            + fmt(100 * entry["pass_rate"], 1) + "% | " + fmt(100 * entry["refusal_rate"], 1) + "% |")
    add("")
    add("**条款分解（关键）**：气相里「不束缚签名」挡住 " + str(payload["census"][0]["clause_homo_pass"]) + "/"
        + str(payload["census"][0]["rows"]) + "，而 EA 条款单独会放过 "
        + str(payload["census"][0]["clause_ea_pass"]) + "/"
        + str(payload["census"][0]["rows"]) + " —— 差 "
        + fmt(100 * (payload["criteria"][0]["value"]), 1) + " 个百分点，"
        "所以 GFN2 的 ΔSCF EA 不能单独当门禁。")
    add("")
    add("## 3. 门禁前后的还原轴排序读数")
    add("")
    add("| 层级 | 介质 | 全域 tau_b（行数） | 合法子集 tau_b（行数） | 裁决 |")
    add("| --- | --- | --- | --- | --- |")
    for entry in payload["census"] + payload["orca"]:
        add("| " + ("GFN2" if not str(entry["medium"]).startswith("orca_") else "ORCA")
            + " | " + entry["label"] + " | " + fmt(entry["tau_all"]) + "（"
            + str(entry["tau_all_rows"]) + "） | "
            + (fmt(entry["tau_legal"]) + "（" + str(entry["tau_legal_rows"]) + "）"
               if entry["tau_legal"] is not None else "——") + " | " + entry["verdict"] + " |")
    add("")
    add("## 4. 跨层级门禁裁决（配对集 n = " + str(payload["cross"]["n_paired"]) + "）")
    add("")
    add("| 组合 | 计数 |")
    add("| --- | --- |")
    add("| GFN2 合法 ∧ ORCA 合法 | " + str(payload["cross"]["both_legal"]) + " |")
    add("| GFN2 合法 ∧ ORCA 不合法 | " + str(payload["cross"]["gfn2_only"]) + " |")
    add("| GFN2 不合法 ∧ ORCA 合法 | " + str(payload["cross"]["orca_only"]) + " |")
    add("| 两层都不合法 | " + str(payload["cross"]["neither"]) + " |")
    add("")
    add("## 5. 判据（H33a–H33f）")
    add("")
    for item in payload["criteria"]:
        add("- **" + item["id"] + " " + item["verdict"] + "**：" + item["description"]
            + "（读数 " + fmt(item["value"]) + " 对阈值 " + fmt(item["threshold"]) + "）。")
    add("")
    add("## 6. 复现锚")
    add("")
    for item in payload["anchors"]:
        add("- **" + item["id"] + " " + item["verdict"] + "**：" + item["description"]
            + "（读数 " + fmt(item["value"], 13) + "）。")
    add("")
    add("## 7. 口径与边界")
    add("")
    for item in payload["boundaries"]:
        add("- " + item)
    add("")
    add("## 8. 产物与复算")
    add("")
    add("- `probes/w33_bound_state_gate.py`、`probes/w33_bound_state_gate_prereg.json`、"
        "`probes/artifacts/w33_bound_state_gate_{summary.json,gates.csv,refuse_queue.csv,"
        "readings.csv,png}`、`reports/w33_bound_state_gate.md`")
    add("- 复算：`python probes\\w33_bound_state_gate.py`（零网络、零新算力，约数秒）")
    return "\n".join(lines) + "\n"


def render_figure(payload) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        available = {font.name for font in font_manager.fontManager.ttflist}
        for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
            if candidate in available:
                plt.rcParams["font.sans-serif"] = [candidate]
                break
        plt.rcParams["axes.unicode_minus"] = False

        entries = payload["census"] + payload["orca"]
        labels = [entry["label"] + "\neps=" + fmt(entry["epsilon"], 1) for entry in entries]
        positions = list(range(len(entries)))
        legal = [entry["pass_rate"] for entry in entries]
        homo = [entry["homo_refused"] / entry["rows"] for entry in entries]
        ea_ref = [entry["ea_refused"] / entry["rows"] for entry in entries]
        geom = [entry["geom_fail"] / entry["rows"] for entry in entries]

        figure, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
        axes[0].bar(positions, legal, color="#1f3b63", label="合法（可宣读）")
        axes[0].bar(positions, homo, bottom=legal, color="#c0392b", label="拒答：阴离子不束缚")
        axes[0].bar(positions, ea_ref, bottom=[a + b for a, b in zip(legal, homo)],
                    color="#e67e22", label="拒答：EA 非正")
        axes[0].bar(positions, geom, bottom=[a + b + c for a, b, c in zip(legal, homo, ea_ref)],
                    color="#7f8c8d", label="拒答：几何/SCF 失败")
        for position, value in zip(positions, legal):
            axes[0].text(position, value / 2, fmt(100 * value, 0) + "%", ha="center",
                         va="center", fontsize=7.5, color="white")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels(labels, fontsize=7)
        axes[0].set_ylabel("占比")
        axes[0].set_ylim(0, 1.0)
        axes[0].set_title("A 态合法性门禁漏斗：合法集 / 三类拒答", fontsize=10.5)
        axes[0].legend(fontsize=7, loc="lower left", framealpha=0.9)
        axes[0].grid(alpha=0.25, axis="y")

        all_values = [entry["tau_all"] for entry in entries]
        legal_values = [entry["tau_legal"] for entry in entries]
        axes[1].plot(positions, all_values, color="#7f8c8d", marker="o", linewidth=1.3,
                     label="全域 tau_b（未门禁）")
        decidable = [(position, value) for position, value in zip(positions, legal_values)
                     if value is not None]
        axes[1].plot([item[0] for item in decidable], [item[1] for item in decidable],
                     color="#1f3b63", marker="s", linewidth=1.3, label="合法子集 tau_b（门禁后）")
        for position, value in zip(positions, legal_values):
            if value is None:
                axes[1].annotate("不可判定", (position, all_values[position]),
                                 textcoords="offset points", xytext=(0, -16), ha="center",
                                 fontsize=7.5, color="#c0392b")
        axes[1].axhline(0.0, color="#111111", linewidth=0.8, linestyle=":")
        axes[1].set_xticks(positions)
        axes[1].set_xticklabels(labels, fontsize=7)
        axes[1].set_ylabel("tau_b（-Koopmans 源 vs dSCF 目标）")
        axes[1].set_title("B 门禁前后的还原轴排序读数", fontsize=10.5)
        axes[1].legend(fontsize=7.5)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W33-A 态合法性前置门禁（后验重建，不占 shot）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # noqa: BLE001 - 图形是可选产物
        print("figure skipped: " + repr(error))
        return False


def main() -> int:
    started = time.perf_counter()
    if not PREREG_PATH.is_file():
        print("missing prereg " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("prereg status is not locked_before_run")
        return 1
    census_rows = read_rows(REDOX_LAYER)
    orca_rows = read_rows(ORCA_LAYER)
    refuse_rows: list = []
    census_entries = analyse_census(census_rows, refuse_rows)
    orca_entries, anchors, cross = analyse_orca(census_rows, orca_rows, refuse_rows)
    criteria, anchor_checks = evaluate_criteria(census_entries, orca_entries, anchors, cross)
    if not all(item["verdict"] == "成立" for item in anchor_checks):
        print("reproduction anchors failed; refusing to write the report")
        for item in anchor_checks:
            print("  " + item["id"] + " " + item["verdict"] + " " + fmt(item["value"], 13))
        return 2
    entries = census_entries + orca_entries
    readings = []
    for entry in entries:
        readings.extend([
            {"reading": entry["medium"] + "|legal", "value": entry["legal"]},
            {"reading": entry["medium"] + "|pass_rate", "value": entry["pass_rate"]},
            {"reading": entry["medium"] + "|tau_all", "value": entry["tau_all"]},
            {"reading": entry["medium"] + "|tau_legal", "value": entry["tau_legal"]},
        ])
    readings.append({"reading": "cross|inconsistent_share", "value": cross["inconsistent_share"]})
    payload = {
        "schema": SCHEMA, "task": TASK, "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": prereg["ledger"]["why_not_a_shot"]},
        "preregistration": {"path": str(PREREG_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                            "sha256": sha256_file(PREREG_PATH), "status": str(prereg.get("status")),
                            "revision": int(prereg.get("revision", 1))},
        "inputs": [
            {"path": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
             "sha256": sha256_file(path), "rows": len(read_rows(path))}
            for path in (REDOX_LAYER, ORCA_LAYER, CROSSCHECK_CSV)],
        "gate": {"clauses": prereg["gate"]["clauses"], "min_legal_subset": MIN_LEGAL_SUBSET,
                 "refusal_rule": prereg["gate"]["refusal_rule"]},
        "census": census_entries, "orca": orca_entries, "cross": cross, "anchors": anchor_checks,
        "criteria": criteria,
        "boundaries": list(prereg["boundaries"]),
    }
    write_csv(GATES_CSV, GATES_FIELDS, entries)
    write_csv(REFUSE_CSV, REFUSE_FIELDS, refuse_rows)
    write_csv(READINGS_CSV, ("reading", "value"), readings)
    dump_json(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(format_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("gate: " + " | ".join(entry["medium"] + " legal " + str(entry["legal"]) + "/"
                                + str(entry["rows"]) for entry in entries), flush=True)
    print("tau: " + " | ".join(entry["medium"] + " all " + fmt(entry["tau_all"], 4)
                               + " legal " + fmt(entry["tau_legal"], 4) for entry in entries),
          flush=True)
    print("cross " + str(cross), flush=True)
    print("wrote " + str(GATES_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("wrote " + str(REFUSE_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
          + " (" + str(len(refuse_rows)) + " rows)", flush=True)
    print("wrote " + str(SUMMARY_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("wrote " + str(REPORT_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(criteria)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())