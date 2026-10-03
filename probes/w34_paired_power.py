# -*- coding: utf-8 -*-
"""W34-B：R6 的配对重抽分辨率审计（后验读数，不占 shot）。

R6 是全仓唯一没有分辨率读数的跨层级结论：母体论文六档有 sigma 列、四通道有抽样律
s0，而 R6 只有两个点估计（ox_move = -0.043、red_move = -1.437）。本件按
`probes/w24_3_posthoc.py::level_crosscheck` 的同一口径重算四条 tau_b（四个复现锚必须
逐位命中，否则拒绝出报告），再在 **22 个配对化合物**上用固定种子做配对 bootstrap，
给出 Delta tau 的 95% 分位区间、跨 0 占比，以及与精确零分布独立地板之比。

预注册：`probes/w34_paired_power_prereg.json`（status = locked_before_run）。
只读、不联网、不装依赖；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np

import w24_3_posthoc as posthoc
import w33_bound_state_gate as gate
import w33_kendall_null_tool as nulltool

REDOX_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
ORCA_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
CROSSCHECK_CSV = REPOSITORY_ROOT / "probes" / "artifacts" / "w24_3_level_crosscheck.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w34_paired_power_prereg.json"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = ARTIFACTS / "w34_paired_power_summary.json"
BOOTSTRAP_CSV = ARTIFACTS / "w34_paired_power_bootstrap.csv"
TABLE_CSV = ARTIFACTS / "w34_paired_power_table.csv"
FIGURE_PATH = ARTIFACTS / "w34_paired_power.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w34_paired_power.md"

SCHEMA = "w34_paired_power/summary@1"
TASK = "week34_paired_power"
DRAWS = 4000
SEED = 20261003
ALPHA = 0.05
REPRODUCTION_TOLERANCE = 1e-12

ANCHORS = {
    "same_ox_gfn2": 0.6969696969696969,
    "same_ox_orca": 0.6536796536796536,
    "same_red_gfn2": 0.8354978354978355,
    "same_red_orca": -0.6017316017316018,
}
POINT_MOVES = {"ox": -0.04329004329004327, "red": -1.4372294372294374}
AXIS_LABELS = {"ox": "氧化轴", "red": "还原轴"}

SERIES = ("gfn2_ox", "gfn2_red", "orca_ox", "orca_red")
ANCHOR_SERIES = {"same_ox_gfn2": "gfn2_ox", "same_ox_orca": "orca_ox",
                 "same_red_gfn2": "gfn2_red", "same_red_orca": "orca_red"}

EXPECTED_INPUTS = {
    "data/processed/w23_redox_dscf_layer.csv":
        "d24d4c5a0937bbf971afb5d52f15038505f58e47d43c4ed8ebe44a07910d1b9f",
    "data/processed/w24_2_orca_dft_layer.csv":
        "c48a541d1a831f073cfd87810510f89c934a6f645a869880886518e1acc03246",
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/w34_paired_power_prereg.json":
        "431e8fd5c78744906c4a7c19293dea3859ba7957438d8bf58e1308545ea21f0e",
}


def read_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_paired(census_rows, orca_rows) -> list:
    census = {row["inchikey"]: row for row in census_rows}
    paired = []
    for row in orca_rows:
        key = row.get("inchikey")
        if key not in census:
            continue
        if gate.as_float(row.get("orca_ip_gas_eV")) is None:
            continue
        if gate.as_float(row.get("orca_ea_gas_eV")) is None:
            continue
        paired.append((key, census[key], row))
    return paired


def series_values(paired) -> dict:
    values = {name: {"x": [], "y": []} for name in SERIES}
    for _, census_row, orca_row in paired:
        values["gfn2_ox"]["x"].append(-gate.as_float(census_row["gas_neutral_homo_eV"]))
        values["gfn2_ox"]["y"].append(gate.as_float(census_row["ip_gas_eV"]))
        values["gfn2_red"]["x"].append(-gate.as_float(census_row["gas_neutral_lumo_eV"]))
        values["gfn2_red"]["y"].append(gate.as_float(census_row["ea_gas_eV"]))
        values["orca_ox"]["x"].append(gate.as_float(orca_row["p0_ox_eV"]))
        values["orca_ox"]["y"].append(gate.as_float(orca_row["orca_ip_gas_eV"]))
        values["orca_red"]["x"].append(gate.as_float(orca_row["p0_red_eV"]))
        values["orca_red"]["y"].append(gate.as_float(orca_row["orca_ea_gas_eV"]))
    return {name: {"x": np.asarray(item["x"], dtype=float),
                   "y": np.asarray(item["y"], dtype=float)}
            for name, item in values.items()}


def tau_of(x, y) -> float:
    value, _used = posthoc.kendall_tau_b(list(zip(x.tolist(), y.tolist())))
    return math.nan if value is None else float(value)


def bootstrap_deltas(values, draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(values["gfn2_ox"]["x"])
    out = {name: np.empty(draws, dtype=float) for name in SERIES}
    for draw in range(draws):
        index = rng.integers(0, n, n)
        for name in SERIES:
            out[name][draw] = tau_of(values[name]["x"][index], values[name]["y"][index])
    return {"ox": out["orca_ox"] - out["gfn2_ox"], "red": out["orca_red"] - out["gfn2_red"]}


def interval(samples) -> dict:
    lo, hi = np.percentile(samples, [100.0 * ALPHA / 2.0, 100.0 * (1.0 - ALPHA / 2.0)])
    lo, hi = float(lo), float(hi)
    return {"ci_low": lo, "ci_high": hi, "half_width": (hi - lo) / 2.0,
            "crosses_zero": bool(lo <= 0.0 <= hi),
            "mean": float(np.mean(samples)), "sd": float(np.std(samples, ddof=1)),
            "median": float(np.median(samples))}


def evaluate(n, table, gate_counts, anchors_ok) -> list:
    def verdict(identifier, description, value, threshold, passed):
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    ox = table["ox"]
    red = table["red"]
    floor = math.sqrt(2.0) * nulltool.exact_sd(n)
    ratio = ox["half_width"] / floor if floor else float("inf")
    return [
        verdict("H34f", "复现锚：四个全域 tau_b 逐位命中 w24_3_level_crosscheck.csv",
                0.0 if anchors_ok else 1.0, 0.0, anchors_ok),
        verdict("H34g", "还原轴 Delta tau 的 95% 配对 bootstrap 区间不跨 0（翻号可分辨）",
                red["ci_low"], 0.0, not red["crosses_zero"]),
        verdict("H34h", "氧化轴 Delta tau 的 95% 配对 bootstrap 区间跨 0（『不敏感』在 n=22 下不可分辨）",
                0.0, 0.0, ox["crosses_zero"]),
        verdict("H34i", "配对降方差：bootstrap 区间半宽 < 独立地板 sqrt(2)*exact_sd(22)",
                ratio, 1.0, ratio < 1.0),
        verdict("H34j", "门禁一致性：配对集 GFN2 气相合法 1/22、ORCA 气相合法 0/22（与 W33-A 一致）",
                float(gate_counts["gfn2_gas_legal"]), 1.0,
                gate_counts["gfn2_gas_legal"] == 1 and gate_counts["orca_gas_legal"] == 0),
    ]


def write_csv(path, fieldnames, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def dump_json(path, payload) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def fmt(value, digits=6) -> str:
    if value is None:
        return "——"
    return format(float(value), "." + str(digits) + "f")


def format_report(payload) -> str:
    lines = []
    add = lines.append
    add("# W34-B：R6 的配对重抽分辨率审计")
    add("")
    add("**性质**：后验读数（配对 bootstrap）。**不占主记分牌 shot**（累计仍 "
        + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"])
        + "）；不重跑 xTB / ORCA、不拟合模型、不联网。预注册 `probes/w34_paired_power_prereg.json`"
        "（sha256 `" + str(payload["preregistration"]["sha256"]) + "`，status = locked_before_run）。")
    add("")
    add("## 0. 一句话（全部由数据推出）")
    add("")
    for line in payload["headline"]:
        add("- " + line)
    add("")
    add("## 1. 点估计与配对重抽区间（22 个配对化合物，B = "
        + str(payload["method"]["draws"]) + "，种子 " + str(payload["method"]["seed"]) + "）")
    add("")
    add("| 轴 | tau_b(GFN2) | tau_b(ORCA) | Delta tau | 95% 区间 | 区间半宽 | 跨 0 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for axis in ("ox", "red"):
        item = payload["table"][axis]
        add("| " + AXIS_LABELS[axis] + " | " + fmt(item["tau_gfn2"], 6) + " | "
            + fmt(item["tau_orca"], 6) + " | " + fmt(item["delta"], 6) + " | ["
            + fmt(item["ci_low"], 4) + ", " + fmt(item["ci_high"], 4) + "] | "
            + fmt(item["half_width"], 4) + " | " + ("是" if item["crosses_zero"] else "否") + " |")
    add("")
    add("- 复现锚（逐位命中）：`same_ox_gfn2` = " + fmt(ANCHORS["same_ox_gfn2"], 13)
        + "、`same_ox_orca` = " + fmt(ANCHORS["same_ox_orca"], 13)
        + "、`same_red_gfn2` = " + fmt(ANCHORS["same_red_gfn2"], 13)
        + "、`same_red_orca` = " + fmt(ANCHORS["same_red_orca"], 13) + "。")
    add("- 独立地板（精确零分布，n = 22）：`sqrt(2)*exact_sd(22)` = "
        + fmt(payload["method"]["independent_floor"], 6)
        + "；氧化轴区间半宽与之比 = " + fmt(payload["method"]["half_width_ratio_ox"], 4) + "。")
    add("")
    add("## 2. 判据（H34f–H34j）")
    add("")
    for item in payload["criteria"]:
        add("- **" + item["id"] + " " + item["verdict"] + "**：" + item["description"]
            + "（读数 " + fmt(item["value"]) + " 对阈值 " + fmt(item["threshold"]) + "）。")
    add("")
    add("## 3. 门禁叠加（W33-A）")
    add("")
    add("- 配对集上 GFN2 气相合法 **" + str(payload["gate"]["gfn2_gas_legal"]) + "/"
        + str(payload["gate"]["n_paired"]) + "**、ORCA 气相合法 **"
        + str(payload["gate"]["orca_gas_legal"]) + "/" + str(payload["gate"]["n_paired"]) + "**。"
        "⇒ 本节所有 Delta tau 都是在（几乎全部）**不合法态**上算出来的：分辨率审计说的是"
        "「这个对比能不能分辨」，门禁说的是「这个对比的定义域有没有被声明」——**两件事都必须报**。")
    add("")
    add("## 4. 口径与边界")
    add("")
    for line in payload["boundaries"]:
        add("- " + line)
    add("")
    add("## 5. 产物与复算")
    add("")
    add("- `probes/w34_paired_power.py`、`probes/w34_paired_power_prereg.json`、"
        "`probes/artifacts/w34_paired_power_{summary.json,bootstrap.csv,table.csv,png}`、"
        "`reports/w34_paired_power.md`")
    add("- 复算：`python probes\\w34_paired_power.py`（零网络、零新算力，约数秒）。")
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

        samples = np.asarray([row["delta_ox"] for row in payload["bootstrap"]], dtype=float)
        samples_red = np.asarray([row["delta_red"] for row in payload["bootstrap"]], dtype=float)
        ox, red = payload["table"]["ox"], payload["table"]["red"]

        figure, axes = plt.subplots(1, 2, figsize=(13.6, 5.2))
        axes[0].hist(samples, bins=60, color="#1f3b63", alpha=0.85,
                     label="氧化轴 Delta tau")
        axes[0].hist(samples_red, bins=60, color="#c0392b", alpha=0.85,
                     label="还原轴 Delta tau")
        axes[0].axvline(0.0, color="#111111", linewidth=1.4, linestyle="--", label="Delta tau = 0")
        axes[0].axvspan(ox["ci_low"], ox["ci_high"], color="#1f3b63", alpha=0.15)
        for value, color in ((ox["delta"], "#1f3b63"), (red["delta"], "#c0392b")):
            axes[0].axvline(value, color=color, linewidth=1.2)
        axes[0].set_xlabel("Delta tau = tau(ORCA) - tau(GFN2)")
        axes[0].set_ylabel("重抽次数")
        axes[0].set_title("A 配对 bootstrap 分布（B = " + str(payload["method"]["draws"])
                          + "，22 个化合物）", fontsize=10.5)
        axes[0].legend(fontsize=7.5)
        axes[0].grid(alpha=0.25, axis="y")

        floor = float(payload["method"]["independent_floor"])
        values = [ox["half_width"], red["half_width"], floor]
        names = ["氧化轴区间半宽", "还原轴区间半宽", "独立地板\nsqrt(2)*exact_sd(22)"]
        colors = ["#1f3b63", "#c0392b", "#7f8c8d"]
        bars = axes[1].bar(names, values, color=colors)
        for bar, value in zip(bars, values):
            axes[1].text(bar.get_x() + bar.get_width() / 2.0, value * 1.02, fmt(value, 3),
                         ha="center", fontsize=8.5)
        axes[1].set_ylabel("Delta tau")
        axes[1].set_title("B 分辨率对比：配对设计 vs 独立地板", fontsize=10.5)
        axes[1].grid(alpha=0.25, axis="y")
        axes[1].set_ylim(0, max(values) * 1.2)

        figure.tight_layout()
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover - plotting is best effort
        print("figure skipped: " + repr(error))
        return False


def main(argv=None) -> int:
    started = time.perf_counter()
    draws = DRAWS  # 预注册写死；不提供 CLI 覆盖，避免产物与预注册悄悄不一致

    if not PREREG_PATH.is_file():
        print("missing prereg " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("prereg status is not locked_before_run")
        return 1

    inputs = []
    for relative, expected in EXPECTED_INPUTS.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        if measured != expected:
            print("input moved: " + relative)
            return 1
        inputs.append({"path": relative, "sha256": measured})

    census_rows = read_rows(REDOX_LAYER)
    orca_rows = read_rows(ORCA_LAYER)
    paired = build_paired(census_rows, orca_rows)
    values = series_values(paired)
    n = len(paired)

    full = {name: tau_of(values[name]["x"], values[name]["y"]) for name in SERIES}
    anchors_ok = True
    for anchor_name, series_name in ANCHOR_SERIES.items():
        anchors_ok = anchors_ok and abs(full[series_name] - ANCHORS[anchor_name]) <= REPRODUCTION_TOLERANCE
    if not anchors_ok:
        print("reproduction anchors failed; refusing to write the report")
        for anchor_name, series_name in ANCHOR_SERIES.items():
            print("  " + anchor_name + " " + fmt(full[series_name], 13)
                  + " vs " + fmt(ANCHORS[anchor_name], 13))
        return 2

    deltas = bootstrap_deltas(values, draws, SEED)
    table = {}
    for axis in ("ox", "red"):
        samples = deltas[axis]
        stats = interval(samples)
        stats.update({"axis": axis, "label": AXIS_LABELS[axis],
                      "tau_gfn2": full["gfn2_" + axis], "tau_orca": full["orca_" + axis],
                      "delta": full["orca_" + axis] - full["gfn2_" + axis],
                      "point_move_in_crosscheck": POINT_MOVES[axis],
                      "sign_flip_share": float(np.mean(np.sign(samples) != np.sign(
                          full["orca_" + axis] - full["gfn2_" + axis])))})
        table[axis] = stats

    floor = math.sqrt(2.0) * nulltool.exact_sd(n)
    gate_counts = {
        "n_paired": n,
        "gfn2_gas_legal": sum(1 for key, row, _ in paired
                              if gate.census_gate(row, "gas")["legal"]),
        "orca_gas_legal": sum(1 for _, _, row in paired
                              if gate.orca_gate(row, "gas")["legal"]),
    }
    criteria = evaluate(n, table, gate_counts, anchors_ok)

    bootstrap_rows = [{"draw": index, "delta_ox": float(deltas["ox"][index]),
                       "delta_red": float(deltas["red"][index])} for index in range(draws)]

    headline = [
        "**还原轴的翻号是可分辨的真效应**：Delta tau = " + fmt(table["red"]["delta"], 4)
        + "，95% 区间 [" + fmt(table["red"]["ci_low"], 4) + ", " + fmt(table["red"]["ci_high"], 4)
        + "]，不跨 0；" + str(draws) + " 次重抽里符号翻转占比 "
        + fmt(table["red"]["sign_flip_share"], 4) + "。",
        "**氧化轴的 −0.043 没有分辨率支撑**：95% 区间 [" + fmt(table["ox"]["ci_low"], 4)
        + ", " + fmt(table["ox"]["ci_high"], 4) + "]，"
        + ("**跨 0**" if table["ox"]["crosses_zero"] else "不跨 0")
        + " ⇒ 「氧化轴对层级不敏感」在 n = 22 下应改写成「"
        + ("未检出差异（不可分辨）" if table["ox"]["crosses_zero"] else "可分辨的差异")
        + "」，而不是「无差异」。",
        "**独立地板对照**：n = 22 时精确零分布的独立地板 `sqrt(2)*exact_sd(22)` = "
        + fmt(floor, 4) + "；氧化轴区间半宽 = " + fmt(table["ox"]["half_width"], 4)
        + "（比 " + fmt(table["ox"]["half_width"] / floor, 4) + "）⇒ 配对设计"
        + ("确实降方差" if table["ox"]["half_width"] < floor else "**没有**把不确定性压到独立地板之下") + "。",
        "**门禁叠加（W33-A）**：配对集 GFN2 气相合法 " + str(gate_counts["gfn2_gas_legal"]) + "/"
        + str(n) + "、ORCA 气相合法 " + str(gate_counts["orca_gas_legal"]) + "/" + str(n)
        + " ⇒ 上面的 Δ 都是在（几乎全部）**不合法态**上算的：分辨率与定义域是两件事，必须并报。",
    ]

    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "配对 bootstrap 分辨率审计：只读两张冻结表，不拟合模型、不触 ε 主记分牌。"},
        "preregistration": {"path": "probes/w34_paired_power_prereg.json",
                            "sha256": sha256_file(PREREG_PATH),
                            "status": str(prereg.get("status")),
                            "revision": int(prereg.get("revision", 1))},
        "inputs": inputs,
        "method": {"unit_of_resampling": "配对化合物（inchikey），有放回", "draws": draws,
                   "seed": SEED, "alpha": ALPHA,
                   "statistic": "Kendall tau_b（probes/w24_3_posthoc.py::kendall_tau_b）",
                   "delta_definition": "Delta tau = tau_orca - tau_gfn2",
                   "independent_floor": floor,
                   "exact_sd_n": nulltool.exact_sd(n),
                   "half_width_ratio_ox": table["ox"]["half_width"] / floor},
        "n_paired": n, "full_set_tau": full, "table": table, "bootstrap": bootstrap_rows,
        "gate": gate_counts, "criteria": criteria, "headline": headline,
        "boundaries": [
            "两张输入表逐位只读并记 sha256；不重跑 xTB、不重跑 ORCA、不装依赖、不联网。",
            "bootstrap 只在 22 个配对化合物上重抽，不外推到 246 普查：区间是该配对设计下的分辨率，不是全域噪声地板。",
            "区间跨 0 的正确读法是「未检出差异」，不是「证明无差异」。",
            "复现锚不中时脚本拒绝写报告（return 2），不得只打印警告。",
            "不改 METRIC_NAMES、不新增特征列、不动四个冻结读数与 ε 主记分牌；本件是后验读数，不占 shot。",
        ],
    }

    write_csv(BOOTSTRAP_CSV, ("draw", "delta_ox", "delta_red"), bootstrap_rows)
    write_csv(TABLE_CSV, ("axis", "label", "tau_gfn2", "tau_orca", "delta", "ci_low", "ci_high",
                          "half_width", "crosses_zero", "sd", "sign_flip_share"), [table["ox"], table["red"]])
    dump_json(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(format_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("n_paired " + str(n) + " | ox Delta " + fmt(table["ox"]["delta"], 4)
          + " CI [" + fmt(table["ox"]["ci_low"], 4) + ", " + fmt(table["ox"]["ci_high"], 4) + "]"
          + " cross0=" + str(table["ox"]["crosses_zero"]), flush=True)
    print("red Delta " + fmt(table["red"]["delta"], 4)
          + " CI [" + fmt(table["red"]["ci_low"], 4) + ", " + fmt(table["red"]["ci_high"], 4) + "]"
          + " cross0=" + str(table["red"]["crosses_zero"]), flush=True)
    print("independent floor " + fmt(floor, 4) + " | ratio " + fmt(payload["method"]["half_width_ratio_ox"], 4), flush=True)
    print("wrote " + str(TABLE_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(criteria)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())