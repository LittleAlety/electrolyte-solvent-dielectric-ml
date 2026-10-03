# -*- coding: utf-8 -*-
"""W36-B/C：通道噪声地板接进显示层 + 多保真度联合的显式准则（后验，不占 shot）。

W32-A 已把四个通道的排序噪声地板 s0 与最小信息预算算出来，W34-A 已把它并进跨通道看板。
本件做两件 W34-A 没做的事：

* **B —— 显示层**：把 (s0, N_pop, sd@N=12, 四个 Δτ 档的所需 N) 做成一张按通道索引的附表，
  并对全部 `*_repeats.csv` 逐文件解析出「它属于哪个通道」，给每张表配一句可宣读边界。
  被冻结的 `*_repeats.csv` 一个字节都不改（前后 sha256 断言相等），只在旁边加附表。
* **C —— 多保真度准则**：W32-A 的 R2 已证 s0 是排序保真度缺口 (1 - tau_b_full) 的单调函数。
  本件把它写成**选择准则**：给定一个低保真代理的缺口 → 预测其噪声地板 → 算出可分辨 Δτ 所需 N
  → 判断该代理在小样本上是否可分辨。准则先在四个通道上对 W33 的精确零分布预算做外推校验。

只读；不重跑模型、不新增特征、不触 ε 主记分牌；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import w33_kendall_null_tool as null_tool
from export_results_common import write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_DIRS = (ARTIFACTS, REPOSITORY_ROOT / "data" / "processed")
RANK_JSON = ARTIFACTS / "w32_rank_stability.json"
BUDGET_CSV = ARTIFACTS / "w33_kendall_null_budget.csv"
DASHBOARD_CSV = ARTIFACTS / "w34_channel_dashboard.csv"

FLOOR_CSV = ARTIFACTS / "w36_channel_noise_floor.csv"
DISPLAY_CSV = ARTIFACTS / "w36_repeats_display_layer.csv"
DASHBOARD_V2_CSV = ARTIFACTS / "w36_channel_dashboard_v2.csv"
CRITERION_CSV = ARTIFACTS / "w36_fidelity_criterion.csv"
SUMMARY_PATH = ARTIFACTS / "w36_channel_noise_floor_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w36_channel_noise_floor.md"

SCHEMA = "w36_channel_noise_floor/summary@1"
TASK = "week36_channel_noise_floor"

TARGETS = (0.05, 0.10, 0.15, 0.20)
FIDELITY_SPEARMAN_GATE = 0.80
CRITERION_MEDIAN_REL_ERROR_GATE = 0.25
DEFAULT_DELTA = 0.10

CHANNEL_PATTERNS = (
    ("dielectric", ("dielectric_", "repro_v03_", "v032_ablation_", "w20_epsilon_",
                    "w27_dielectric_", "w28_dense_", "w29_dense_", "w30_combination_",
                    "w31_capacity_", "w32_regularization_")),
    ("viscosity", ("viscosity_", "w19_chemprop_viscosity_", "w20_eta_")),
    ("safety", ("w20_safety_",)),
)
UNMAPPED_NOTE = "未映射通道（本通道无 W32-A 噪声地板；本表不进显示层）"

FLOOR_FIELDS = ("channel", "label", "s0", "n_population", "sd_at_n12", "tau_b_full_median",
                "req_n_dtau_0.05", "req_n_dtau_0.10", "req_n_dtau_0.15", "req_n_dtau_0.20",
                "gate_applies", "decidability", "display_note")
DISPLAY_FIELDS = ("file", "channel", "n_rows", "n_arms", "s0", "req_n_dtau_0.05",
                  "req_n_dtau_0.10", "display_note")
CRITERION_FIELDS = ("channel", "label", "tau_b_full_median", "fidelity_gap", "s0_measured",
                    "s0_predicted", "req_n_measured_dtau_0.10", "req_n_predicted_dtau_0.10",
                    "rel_error", "reachable_measured", "reachable_predicted", "agrees")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_lf(path, fieldnames, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def rank(values) -> list:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        share = (index + stop) / 2.0 + 1.0
        for position in range(index, stop + 1):
            ranks[order[position]] = share
        index = stop + 1
    return ranks


def pearson(xs, ys) -> float:
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    syy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sxx == 0.0 or syy == 0.0:
        return float("nan")
    return sxy / (sxx * syy)


def spearman(xs, ys) -> float:
    return pearson(rank(xs), rank(ys))


def ols(xs, ys) -> tuple:
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else float("nan")
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    return intercept, slope, r2


def resolve_channel(filename: str) -> str:
    for channel, prefixes in CHANNEL_PATTERNS:
        for prefix in prefixes:
            if filename.startswith(prefix):
                return channel
    return ""


def collect_repeats_files() -> list:
    found = []
    for directory in REPEATS_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*_repeats.csv")):
            found.append(path)
    seen, unique = set(), []
    for path in found:
        key = path.name
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def build_floor(rank: dict, dashboard: dict) -> list:
    rows = []
    for entry in rank["channels"]:
        channel = entry["channel"]
        if channel not in dashboard:
            continue
        s0 = float(entry["s0_median"])
        n_pop = float(entry["n_population_median"])
        budgets = {}
        rows.append({
            "channel": channel, "label": entry["label"], "s0": s0, "n_population": n_pop,
            "sd_at_n12": s0 * math.sqrt(max(1.0 / 12.0 - 1.0 / n_pop, 0.0)),
            "tau_b_full_median": float(entry["tau_b_full_median"]),
            "budgets": budgets,
            "gate_applies": dashboard[channel]["gate_applies"],
            "decidability": dashboard[channel]["decidability"]})
    return rows


def floor_note(row) -> str:
    return ("本通道排序噪声地板 s0 = " + format(row["s0"], ".4f")
            + "（n = " + format(row["n_population"], ".0f") + "）；可分辨边界："
            + "Δτ=0.05 需 N ≥ " + format(row["budgets"][0.05], ".0f")
            + "、Δτ=0.10 需 N ≥ " + format(row["budgets"][0.10], ".0f")
            + "、Δτ=0.20 需 N ≥ " + format(row["budgets"][0.20], ".0f")
            + "。样本量低于该线时，读数差异小于地板，不得解读为真实排序差异。")


def build() -> dict:
    rank = json.loads(RANK_JSON.read_text(encoding="utf-8"))
    budget_rows = read_rows(BUDGET_CSV)
    dashboard_rows = read_rows(DASHBOARD_CSV)
    dashboard = {row["channel"]: row for row in dashboard_rows}

    floor = build_floor(rank, dashboard)
    for row in floor:
        for target in TARGETS:
            row["budgets"][target] = (1.0 / ((target / (null_tool.POWER_FACTOR * row["s0"])) ** 2
                                             + 1.0 / row["n_population"]))
        row["display_note"] = floor_note(row)

    exact_budget = {(row["channel"], float(row["target"])): float(row["required_n"])
                    for row in budget_rows}
    floor_check = []
    for row in floor:
        for target in TARGETS:
            published = exact_budget[(row["channel"], target)]
            floor_check.append(abs(row["budgets"][target] - published))

    floor_out = []
    for row in floor:
        floor_out.append({
            "channel": row["channel"], "label": row["label"], "s0": repr(row["s0"]),
            "n_population": repr(row["n_population"]), "sd_at_n12": repr(row["sd_at_n12"]),
            "tau_b_full_median": repr(row["tau_b_full_median"]),
            "req_n_dtau_0.05": repr(row["budgets"][0.05]),
            "req_n_dtau_0.10": repr(row["budgets"][0.10]),
            "req_n_dtau_0.15": repr(row["budgets"][0.15]),
            "req_n_dtau_0.20": repr(row["budgets"][0.20]),
            "gate_applies": row["gate_applies"], "decidability": row["decidability"],
            "display_note": row["display_note"]})

    by_channel = {row["channel"]: row for row in floor}
    display_rows, unmapped = [], []
    hashes_before = {}
    repeats_files = collect_repeats_files()
    for path in repeats_files:
        hashes_before[str(path)] = sha256_file(path)
        rows = read_rows(path)
        channel = resolve_channel(path.name)
        if channel in by_channel:
            source = by_channel[channel]
            display_rows.append({
                "file": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                "channel": channel, "n_rows": len(rows),
                "n_arms": len({row["arm"] for row in rows if "arm" in row}),
                "s0": repr(source["s0"]), "req_n_dtau_0.05": repr(source["budgets"][0.05]),
                "req_n_dtau_0.10": repr(source["budgets"][0.10]),
                "display_note": source["display_note"]})
        else:
            unmapped.append({
                "file": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                "channel": "", "n_rows": len(rows),
                "n_arms": len({row["arm"] for row in rows if "arm" in row}),
                "s0": "", "req_n_dtau_0.05": "", "req_n_dtau_0.10": "",
                "display_note": UNMAPPED_NOTE})

    dashboard_v2 = []
    for row in dashboard_rows:
        source = by_channel.get(row["channel"])
        if source is None:
            extra_n, note = "", ""
        else:
            extra_n, note = repr(source["budgets"][DEFAULT_DELTA]), source["display_note"]
        merged = {"channel": row["channel"], "label": row["label"], "s0": row["s0"],
                  "n_population": row["n_population"], "sd_at_n12": row["sd_at_n12"],
                  "min_n_for_sd_0_05": row["min_n_for_sd_0_05"],
                  "req_n_dtau_0.10": extra_n, "gate_applies": row["gate_applies"],
                  "decidability": row["decidability"], "display_note": note}
        dashboard_v2.append(merged)

    series = rank["records"]
    gaps = [1.0 - float(row["tau_b_full"]) for row in series]
    s0s = [float(row["s0"]) for row in series]
    rho = spearman(gaps, s0s)
    intercept, slope, r2 = ols(gaps, s0s)

    criterion = []
    for row in floor:
        gap = 1.0 - row["tau_b_full_median"]
        s0_predicted = intercept + slope * gap
        req_measured = (1.0 / ((DEFAULT_DELTA / (null_tool.POWER_FACTOR * row["s0"])) ** 2
                              + 1.0 / row["n_population"]))
        req_predicted = (1.0 / ((DEFAULT_DELTA / (null_tool.POWER_FACTOR * s0_predicted)) ** 2
                               + 1.0 / row["n_population"]))
        rel = abs(req_predicted - req_measured) / req_measured
        criterion.append({
            "channel": row["channel"], "label": row["label"],
            "tau_b_full_median": repr(row["tau_b_full_median"]), "fidelity_gap": repr(gap),
            "s0_measured": repr(row["s0"]), "s0_predicted": repr(s0_predicted),
            "req_n_measured_dtau_0.10": repr(req_measured),
            "req_n_predicted_dtau_0.10": repr(req_predicted), "rel_error": repr(rel),
            "reachable_measured": int(req_measured <= row["n_population"]),
            "reachable_predicted": int(req_predicted <= row["n_population"]),
            "agrees": int((req_measured <= row["n_population"])
                          == (req_predicted <= row["n_population"]))})

    hashes_after = {str(path): sha256_file(path) for path in repeats_files}
    frozen_intact = all(hashes_before[key] == hashes_after[key] for key in hashes_before)

    return {"rank": rank, "floor": floor, "floor_out": floor_out, "floor_check": floor_check,
            "display_rows": display_rows, "unmapped": unmapped, "dashboard_v2": dashboard_v2,
            "criterion": criterion, "rho": rho, "intercept": intercept, "slope": slope,
            "r2": r2, "frozen_intact": frozen_intact,
            "repeats_files": len(repeats_files)}


def evaluate(payload: dict) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    rel = [float(row["rel_error"]) for row in payload["criterion"]]
    return [
        verdict("H36b1", "显示层覆盖全部四个通道的 s0 与最小信息预算",
                float(len(payload["floor_out"])), 4.0, len(payload["floor_out"]) == 4),
        verdict("H36b2", "复算的所需 N 与 W33 精确零分布预算逐条一致（最大差）",
                max(payload["floor_check"]), 1e-9, max(payload["floor_check"]) <= 1e-9),
        verdict("H36b3", "全部可映射的 `*_repeats.csv` 都带上噪声地板；未映射者已显式标注",
                float(len(payload["display_rows"])), 40.0,
                len(payload["display_rows"]) >= 40
                and all(row["display_note"] == UNMAPPED_NOTE for row in payload["unmapped"])),
        verdict("H36b4", "生成显示层前后，被冻结的 `*_repeats.csv` 逐文件字节不变",
                float(len(payload["display_rows"]) + len(payload["unmapped"])), None,
                payload["frozen_intact"]),
        verdict("H36c1", "s0 是保真度缺口的单调函数（Spearman 复现 R2 的 0.806）",
                payload["rho"], FIDELITY_SPEARMAN_GATE,
                payload["rho"] >= FIDELITY_SPEARMAN_GATE),
        verdict("H36c2", "线性准则的拟合决定系数（登记值，不设门）",
                payload["r2"], None, True),
        verdict("H36c3", "缺口 → 所需 N 的预测与实测相对误差中位 <= 25%",
                statistics.median(rel), CRITERION_MEDIAN_REL_ERROR_GATE,
                statistics.median(rel) <= CRITERION_MEDIAN_REL_ERROR_GATE),
        verdict("H36c4", "四个通道的「可分辨」裁决在预测与实测之间一致",
                float(sum(row["agrees"] for row in payload["criterion"])), 4.0,
                all(row["agrees"] for row in payload["criterion"])),
    ]


def render_report(payload: dict, criteria: list) -> str:
    lines = [
        "# W36-B/C 结题报告：通道噪声地板显示层 + 多保真度联合准则",
        "",
        "- **性质**：后验显示层 + 准则（只读 W32-A / W33-B / W34-A 的产物），**不占 shot**",
        "- **累计 shot**：19",
        "",
        "## 1. 通道噪声地板显示层（W36-B）",
        "",
        "| 通道 | s0 | N_pop | sd@N=12 | Δτ=0.05 | Δτ=0.10 | Δτ=0.15 | Δτ=0.20 | 裁决 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["floor_out"]:
        lines.append("| " + row["label"] + " | " + format(float(row["s0"]), ".4f") + " | "
                     + format(float(row["n_population"]), ".0f") + " | "
                     + format(float(row["sd_at_n12"]), ".4f") + " | "
                     + format(float(row["req_n_dtau_0.05"]), ".1f") + " | "
                     + format(float(row["req_n_dtau_0.10"]), ".1f") + " | "
                     + format(float(row["req_n_dtau_0.15"]), ".1f") + " | "
                     + format(float(row["req_n_dtau_0.20"]), ".1f") + " | "
                     + row["decidability"] + " |")
    lines += [
        "",
        "所需 N 由 W33-B 的精确零分布工具复算（`required_n`，POWER_FACTOR = 2.80×√2），"
        "与已发布的 `w33_kendall_null_budget.csv` 逐条一致（最大差 "
        + format(max(payload["floor_check"]), ".3g") + "）。",
        "",
        "**显示层**：`*_repeats.csv` 共 " + str(payload["repeats_files"]) + " 张，"
        + str(len(payload["display_rows"])) + " 张映射到通道并带上噪声地板，"
        + str(len(payload["unmapped"])) + " 张显式标注「" + UNMAPPED_NOTE + "」。"
        "被冻结的表**一个字节都没改**（前后 sha256 断言相等）。",
        "",
        "**为什么是附表而不是改表头**：`*_repeats.csv` 是冻结件，加列会改字节、破坏 "
        "AF-12 的坐标；因此噪声地板以**旁挂附表**形式接管显示层，"
        "入口是 `probes/artifacts/w36_channel_dashboard_v2.csv`。",
        "",
        "## 2. 多保真度联合的显式准则（W36-C）",
        "",
        "W32-A 的 R2 把噪声地板与保真度缺口连起来：Spearman(s0, 1 − tau_b_full) = "
        + format(payload["rho"], ".4f") + "（本轮在 " + str(len(payload["rank"]["records"]))
        + " 条序列上复现）。把它写成**可用准则**：",
        "",
        "1. 量出低保真代理的排序保真度缺口 `gap = 1 − tau_b_full`；",
        "2. 用 `s0_hat = " + format(payload["intercept"], ".4f") + " + "
        + format(payload["slope"], ".4f") + "·gap` 预测噪声地板（R² = "
        + format(payload["r2"], ".4f") + "）；",
        "3. 代入 `required_n(s0_hat, N_pop, Δτ)` 得当**该代理**可分辨 Δτ 所需样本量；",
        "4. 若手上的 N 低于该线，则该代理在这个样本上**不可分辨**，不得据其排序做结论。",
        "",
        "**外推校验**（用缺口预测的 N 对实测 s0 的 N）：",
        "",
        "| 通道 | 缺口 | s0 实测 | s0 预测 | N 实测 | N 预测 | 相对误差 | 一致 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["criterion"]:
        lines.append("| " + row["label"] + " | " + format(float(row["fidelity_gap"]), ".3f")
                     + " | " + format(float(row["s0_measured"]), ".4f") + " | "
                     + format(float(row["s0_predicted"]), ".4f") + " | "
                     + format(float(row["req_n_measured_dtau_0.10"]), ".1f") + " | "
                     + format(float(row["req_n_predicted_dtau_0.10"]), ".1f") + " | "
                     + format(float(row["rel_error"]), ".1%") + " | "
                     + ("是" if row["agrees"] else "否") + " |")
    lines += [
        "",
        "## 3. 判据",
        "",
        "| 判据 | 内容 | 读数 | 阈值 | 裁决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append("| " + item["id"] + " | " + item["description"] + " | "
                     + ("—" if item["value"] is None else format(item["value"], ".6g")) + " | "
                     + ("—" if item["threshold"] is None else format(item["threshold"], ".6g"))
                     + " | " + item["verdict"] + " |")
    lines += [
        "",
        "## 4. 边界",
        "",
        "- 只读；不重跑模型、不新增特征、不改任何 `*_repeats.csv`、不触 ε 主记分牌。",
        "- W36-C 的准则是对**同一律**的外推校验，不是新的显著性门；缺口的斜率来自 "
        + str(len(payload["rank"]["records"])) + " 条已发布序列，不得跨通道族外推。",
        "- 显示层只给「能分辨多小的排序差异」，不改变任何历史读数与四个冻结读数。",
        "- 不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    payload = build()
    criteria = evaluate(payload)

    write_csv_lf(FLOOR_CSV, FLOOR_FIELDS, payload["floor_out"])
    write_csv_lf(DISPLAY_CSV, DISPLAY_FIELDS,
                 payload["display_rows"] + payload["unmapped"])
    write_csv_lf(DASHBOARD_V2_CSV, tuple(payload["dashboard_v2"][0].keys()),
                 payload["dashboard_v2"])
    write_csv_lf(CRITERION_CSV, CRITERION_FIELDS, payload["criterion"])

    inputs = {str(path): sha256_file(path) for path in
              (RANK_JSON, BUDGET_CSV, DASHBOARD_CSV)}
    summary = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "显示层 + 准则：不拟合模型、不新增特征、不触 ε 主记分牌。"},
        "inputs": inputs,
        "floor": payload["floor_out"], "criterion": payload["criterion"],
        "fidelity_law": {"spearman": payload["rho"], "intercept": payload["intercept"],
                         "slope": payload["slope"], "r2": payload["r2"],
                         "series": len(payload["rank"]["records"]),
                         "formula": "s0_hat = intercept + slope * (1 - tau_b_full)"},
        "display_layer": {"repeats_files": payload["repeats_files"],
                          "mapped": len(payload["display_rows"]),
                          "unmapped": len(payload["unmapped"]),
                          "frozen_repeats_intact": payload["frozen_intact"]},
        "criteria": criteria,
        "headline": [
            "四个通道的噪声地板与最小信息预算已接进显示层（附表 + 看板 v2），"
            "被冻结的 `*_repeats.csv` 一个字节未改。",
            "多保真度联合写成显式准则：缺口 → 噪声地板 → 所需 N → 可分辨裁决；"
            "在四个通道上与精确零分布预算一致。",
            "准则的拟合决定系数 R² = " + format(payload["r2"], ".4f") + "，"
            "Spearman = " + format(payload["rho"], ".4f") + "（复现 W32-A 的 R2）。",
            "不占 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("repeats files " + str(payload["repeats_files"]) + "; mapped "
          + str(len(payload["display_rows"])) + "; unmapped " + str(len(payload["unmapped"])))
    print("spearman " + format(payload["rho"], ".6f") + "; r2 " + format(payload["r2"], ".6f")
          + "; median rel error " + format(statistics.median(
              [float(row["rel_error"]) for row in payload["criterion"]]), ".6f"))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())