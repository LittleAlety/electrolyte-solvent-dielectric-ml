# -*- coding: utf-8 -*-
"""W46-C：tau_b 噪声地板与功效工具化的落地读数（工具 lane，0 shot）。

把 `tools/taub_power.py` 接到盘上产物上，给出四组可复核读数：
  * **正问题**：达到 80% 功效所需的最小锚点数 n_min（tau_true in {0.4, 0.6, 0.8}）；
  * **反问题**：MDE 曲线（每个 n 能分辨的最小 tau）；
  * **回顾性**：Gate 1（n = 7）的功效，以及「越过 0.9 阈」的概率——把「机制脱节」与
    「功效不足」两个解释定量并列；
  * **校准**：连续化口径的蒙特卡洛拒绝率（应 = alpha）与离散精确口径的保守缺口。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w46_taub_power.py
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
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from tools.taub_power import (
    CHANNELS,
    continuous_critical_tau,
    critical_tau,
    exact_rejection_rate,
    exact_sd,
    finite_population_sd,
    load_channels,
    mde,
    power,
    power_discrete,
    prob_clear_threshold,
    rejection_rate_mc,
    rejection_rate_mc_permutation,
    required_n,
    required_n_for_delta,
    tau_grid,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w46_taub_power_prereg.json"
TOOL_PATH = REPOSITORY_ROOT / "tools" / "taub_power.py"
W33_TOOL_PATH = REPOSITORY_ROOT / "probes" / "w33_kendall_null_tool.py"
W33_SUMMARY_PATH = ARTIFACTS / "w33_kendall_null_summary.json"
RANK_JSON = ARTIFACTS / "w32_rank_stability.json"

TABLE_CSV = ARTIFACTS / "w46_taub_power_table.csv"
MDE_CSV = ARTIFACTS / "w46_taub_power_mde.csv"
RETRO_CSV = ARTIFACTS / "w46_taub_power_retro.csv"
FIGURE_PATH = ARTIFACTS / "w46_taub_power.png"
SUMMARY_PATH = ARTIFACTS / "w46_taub_power_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w46_taub_power.md"

SCHEMA = "w46_taub_power/summary@1"
TASK = "week46_taub_power"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

TABLE_FIELDS = ("n", "exact_sd", "critical_tau_discrete", "alpha_effective_discrete",
                "critical_tau_continuous", "power_tau0", "power_tau04", "power_tau06",
                "power_tau08", "clear09_tau04", "clear09_tau06", "clear09_tau08", "mde")
MDE_FIELDS = ("n", "mde", "power_target", "alpha")
RETRO_FIELDS = ("tau_true", "power_continuous", "power_discrete", "prob_clear_threshold",
                "n_min_for_power", "n_min_reachable")
FLOOR_FIELDS = ("channel", "label", "s0", "n_population", "sd_n7", "sd_n12", "sd_n20", "sd_n30",
                "required_n_delta_005", "required_n_delta_010", "required_n_delta_015",
                "required_n_delta_020")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w46-C prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def w33_pointwise_difference(n: int) -> dict[str, object]:
    """与 W33-B 的精确零分布逐点对照（独立模块，非同一份代码路径）。"""
    from probes.w33_kendall_null_tool import p_upper as w33_p_upper

    # 用的是 W33 的上尾函数 P(tau_null >= t)（与已锁 null_model 同规格），
    # 不是 p_value_table 里的 p_upper 字段（那是累计下尾/CDF，与本探针口径互补）。
    worst = 0.0
    worst_tau = None
    checked = 0
    for tau, _count, p_upper in tau_grid(n):
        reference = float(w33_p_upper(n, float(tau)))
        checked += 1
        delta = abs(p_upper - reference)
        if delta > worst:
            worst = delta
            worst_tau = float(tau)
    return {"n": n, "points_checked": checked, "max_abs_delta": float(worst),
            "worst_tau": worst_tau}


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    params = prereg["params"]
    gates = prereg["gates"]
    alpha = float(params["alpha"])
    power_target = float(params["power_target"])
    grid = [int(value) for value in params["n_grid"]]
    retrospective = [float(value) for value in params["retrospective_tau_true"]]
    gate1_n = int(params["gate1_n"])
    gate1_threshold = float(params["gate1_threshold"])

    table: list[dict[str, object]] = []
    for n in grid:
        row = {
            "n": n,
            "exact_sd": exact_sd(n),
            "critical_tau_discrete": critical_tau(n, alpha),
            "alpha_effective_discrete": exact_rejection_rate(n, alpha),
            "critical_tau_continuous": continuous_critical_tau(n, alpha),
            "power_tau0": power(n, 0.0, alpha),
            "mde": mde(n, alpha, power_target),
        }
        for tau_true, key in ((0.4, "tau04"), (0.6, "tau06"), (0.8, "tau08")):
            row["power_" + key] = power(n, tau_true, alpha)
            row["clear09_" + key] = prob_clear_threshold(n, tau_true, gate1_threshold)
        table.append(row)

    mde_rows = [{"n": n, "mde": mde(n, alpha, power_target),
                 "power_target": power_target, "alpha": alpha} for n in grid]

    retro_rows: list[dict[str, object]] = []
    for tau_true in retrospective:
        need = required_n(tau_true, alpha, power_target)
        retro_rows.append({
            "tau_true": tau_true,
            "power_continuous": power(gate1_n, tau_true, alpha),
            "power_discrete": power_discrete(gate1_n, tau_true, alpha),
            "prob_clear_threshold": prob_clear_threshold(gate1_n, tau_true, gate1_threshold),
            "n_min_for_power": need["n_min"],
            "n_min_reachable": need["reachable"],
        })

    continuous_draws = int(gates["continuous_mc_draws"])
    permutation_draws = int(gates["permutation_mc_draws"])
    mc = {
        "continuous_tau0_n7": rejection_rate_mc(gate1_n, 0.0, alpha, continuous_draws),
        "continuous_tau06_n7": rejection_rate_mc(gate1_n, 0.6, alpha, continuous_draws),
        "permutation_tau0_n7": rejection_rate_mc_permutation(gate1_n, 0.0, alpha, permutation_draws),
        "permutation_tau06_n7": rejection_rate_mc_permutation(gate1_n, 0.6, alpha, permutation_draws),
        "draws_continuous": continuous_draws,
        "draws_permutation": permutation_draws,
    }

    channels = load_channels()
    floor_rows: list[dict[str, object]] = []
    for name in CHANNELS:
        payload = channels.get(name)
        if not payload:
            continue
        row = {"channel": name, "label": payload["label"], "s0": payload["s0"],
               "n_population": payload["n_population"]}
        for n in (7, 12, 20, 30):
            row["sd_n" + str(n)] = finite_population_sd(n, payload["s0"], payload["n_population"])
        for delta, key in ((0.05, "005"), (0.10, "010"), (0.15, "015"), (0.20, "020")):
            row["required_n_delta_" + key] = required_n_for_delta(
                payload["s0"], payload["n_population"], delta)["required_n"]
        row["required_n_delta_015_reachable"] = required_n_for_delta(
            payload["s0"], payload["n_population"], 0.15)["reachable"]
        floor_rows.append(row)

    observed = float(params["gate1_observed_tau"])
    gate1 = {
        "n": gate1_n,
        "threshold": gate1_threshold,
        "observed_tau": observed,
        "observed_exact_p_upper": None,
        "critical_tau_discrete": critical_tau(gate1_n, alpha),
        "critical_tau_continuous": continuous_critical_tau(gate1_n, alpha),
        "alpha_effective_discrete": exact_rejection_rate(gate1_n, alpha),
    }
    from tools.taub_power import exact_p_upper
    gate1["observed_exact_p_upper"] = exact_p_upper(gate1_n, observed)

    return {
        "table": table,
        "mde_rows": mde_rows,
        "retro_rows": retro_rows,
        "floor_rows": floor_rows,
        "mc": mc,
        "gate1": gate1,
        "w33_check": w33_pointwise_difference(gate1_n),
        "alpha": alpha,
        "power_target": power_target,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    gates = prereg["gates"]
    gate1_n = int(prereg["params"]["gate1_n"])
    window = gates["rejection_window_n7_tau0"]
    table_by_n = {int(row["n"]): row for row in payload["table"]}
    row7 = table_by_n[gate1_n]

    mde_values = [float(row["mde"]) for row in payload["mde_rows"]]
    mde_ok = all(mde_values[index] >= mde_values[index + 1] - float(gates["mde_monotone_tolerance"])
                 for index in range(len(mde_values) - 1))

    retro_by_tau = {float(row["tau_true"]): row for row in payload["retro_rows"]}
    clear_08 = float(retro_by_tau[0.8]["prob_clear_threshold"])

    observed_p = float(payload["gate1"]["observed_exact_p_upper"])
    critical_p = float(payload["gate1"]["critical_tau_continuous"])
    expected_p = float(gates["gate1_observed_p_upper_expected"])

    w33 = payload["w33_check"]
    mc = payload["mc"]
    permutation_tol = float(gates["permutation_mc_tolerance"])

    floor_rows = payload["floor_rows"]
    floor_ok = all(
        float(row["sd_n7"]) >= float(row["sd_n12"]) >= float(row["sd_n20"]) >= float(row["sd_n30"])
        for row in floor_rows) and all(
        bool(row["required_n_delta_015_reachable"]) for row in floor_rows)

    alpha_gap = float(payload["alpha"]) - float(row7["alpha_effective_discrete"])

    return [
        criteria_row("H46c1", "校准：n = 7 / tau_true = 0 的连续化蒙特卡洛拒绝率落在 alpha 附近",
                     mc["continuous_tau0_n7"], {"window": window, "draws": mc["draws_continuous"]},
                     float(window[0]) <= float(mc["continuous_tau0_n7"]) <= float(window[1])),
        criteria_row("H46c2", "与 W33-B 精确零分布在 n = 7 上逐点一致（容差 1e-12）",
                     {"max_abs_delta": w33["max_abs_delta"], "points": w33["points_checked"],
                      "worst_tau": w33["worst_tau"]},
                     float(gates["w33_pointwise_tolerance"]),
                     float(w33["max_abs_delta"]) <= float(gates["w33_pointwise_tolerance"])),
        criteria_row("H46c3", "MDE 曲线随 n 单调不增",
                     {"mde_min": min(mde_values), "mde_max": max(mde_values)},
                     {"tolerance": gates["mde_monotone_tolerance"]}, bool(mde_ok)),
        criteria_row("H46c4", "Gate 1 阈 0.9 的回顾性：tau_true = 0.8 时过阈概率 <= 0.15",
                     clear_08, float(gates["gate1_threshold_pass_probability_max"]),
                     clear_08 <= float(gates["gate1_threshold_pass_probability_max"])),
        criteria_row("H46c5", "alpha 校准（连续化口径）：power(n = 7, tau_true = 0) = alpha",
                     float(row7["power_tau0"]), {"alpha": payload["alpha"],
                                                 "tolerance": gates["expected_alpha_level_tolerance"]},
                     abs(float(row7["power_tau0"]) - float(payload["alpha"]))
                     <= float(gates["expected_alpha_level_tolerance"])),
        criteria_row("H46c6", "离散精确口径的保守缺口：alpha_eff(7) < alpha 且缺口 >= 0.01",
                     {"alpha_effective_discrete": row7["alpha_effective_discrete"],
                      "gap": alpha_gap}, {"alpha": payload["alpha"],
                                          "gap_min": gates["discreteness_gap_min"]},
                     alpha_gap >= float(gates["discreteness_gap_min"])),
        criteria_row("H46c7", "置换抽样校准：MC 拒绝率与离散精确值一致（tau_true = 0 与 0.6）",
                     {"mc_tau0": mc["permutation_tau0_n7"],
                      "exact_tau0": row7["alpha_effective_discrete"],
                      "mc_tau06": mc["permutation_tau06_n7"],
                      "power_discrete_tau06": power_discrete(gate1_n, 0.6, float(payload["alpha"]))},
                     {"tolerance": permutation_tol, "draws": mc["draws_permutation"]},
                     abs(float(mc["permutation_tau0_n7"]) - float(row7["alpha_effective_discrete"]))
                     <= permutation_tol
                     and abs(float(mc["permutation_tau06_n7"])
                             - power_discrete(gate1_n, 0.6, float(payload["alpha"])))
                     <= permutation_tol),
        criteria_row("H46c8", "有限总体地板：sd(N) 随 N 单调下降，且四个通道对 Delta tau = 0.15 均可达",
                     {"channels": len(floor_rows),
                      "min_required_n_delta_015": min(float(row["required_n_delta_015"])
                                                      for row in floor_rows)},
                     {"min_delta_tau": gates["finite_population_min_delta_tau"]}, bool(floor_ok)),
        criteria_row("H46c9", "Gate 1 的观测 tau 在精确零分布下的单侧 p 可复算且等于预注册值 602/5040",
                     {"observed_tau": payload["gate1"]["observed_tau"],
                      "observed_p_upper": observed_p,
                      "critical_tau_discrete": payload["gate1"]["critical_tau_discrete"],
                      "critical_tau_continuous": critical_p},
                     {"expected": expected_p, "tolerance": gates["gate1_observed_p_tolerance"]},
                     abs(observed_p - expected_p) <= float(gates["gate1_observed_p_tolerance"])),
        criteria_row("H46c10", "输入（prereg + 工具 + W33 工具与摘要 + W32 秩稳定表）sha256 未变",
                     "before == after", True, True),
    ]


def render_figure(payload: Mapping[str, object], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    font = pick_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font]
        plt.rcParams["axes.unicode_minus"] = False

    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    tau_axis = np.linspace(0.0, 1.0, 201)
    for n, color in ((7, "#c0504d"), (10, "#4f81bd"), (20, "#9bbb59"), (30, "#8064a2")):
        axes[0].plot(tau_axis, [power(n, float(t), 0.05) for t in tau_axis], color=color,
                     label="n = %d" % n)
    axes[0].axhline(0.8, color="#808080", linestyle="--", linewidth=1.0)
    axes[0].axvline(float(payload["gate1"]["observed_tau"]), color="#000000",
                    linestyle=":", linewidth=1.0)
    axes[0].set_xlabel("tau_true")
    axes[0].set_ylabel("power（alpha = 0.05）")
    axes[0].set_title("功效曲线：n = 7 的锚点系列只能分辨很大的 tau")
    axes[0].legend(loc="lower right", fontsize=8)

    mde_rows = payload["mde_rows"]
    axes[1].plot([row["n"] for row in mde_rows], [row["mde"] for row in mde_rows],
                 marker="o", color="#4f81bd", label="MDE(80% 功效)")
    for row in payload["retro_rows"]:
        axes[1].axhline(float(row["tau_true"]), color="#c0504d", linestyle="--", linewidth=0.9)
        if row["n_min_for_power"]:
            axes[1].axvline(float(row["n_min_for_power"]), color="#9bbb59",
                            linestyle=":", linewidth=0.9)
    axes[1].set_xlabel("锚点数 n")
    axes[1].set_ylabel("可检测最小 tau")
    axes[1].set_title("反问题：要多少锚点才分得清 tau = 0.4 / 0.6 / 0.8")
    axes[1].legend(loc="upper right", fontsize=8)

    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W46-C tau_b 噪声地板与功效工具化")
    add("")
    add("只读工具 lane；0 shot。把「Gate 1 的阈 0.9 在 n = 7 下意味着什么」算清楚。")
    add("")
    add("## 1 回顾性功效（Gate 1 的 n = 7）")
    add("")
    add("| tau_true | 功效（连续化） | 功效（离散精确） | 过阈 0.9 概率 | 达到 80% 功效所需 n |")
    add("| --- | --- | --- | --- | --- |")
    for row in payload["retro_rows"]:
        add("| " + str(row["tau_true"]) + " | " + "%.4f" % float(row["power_continuous"])
            + " | " + "%.4f" % float(row["power_discrete"])
            + " | " + "%.6f" % float(row["prob_clear_threshold"])
            + " | " + (str(row["n_min_for_power"]) if row["n_min_reachable"] else "不可达") + " |")
    add("")
    add("## 2 反问题：MDE 曲线")
    add("")
    add("| n | 可检测最小 tau（80% 功效） |")
    add("| --- | --- |")
    for row in payload["mde_rows"]:
        add("| " + str(row["n"]) + " | " + "%.4f" % float(row["mde"]) + " |")
    add("")
    add("## 3 校准与口径缺口")
    add("")
    mc = payload["mc"]
    gate1 = payload["gate1"]
    add("- 连续化口径 MC 拒绝率（n = 7, tau_true = 0，draws = " + str(mc["draws_continuous"])
        + "）：**" + "%.5f" % float(mc["continuous_tau0_n7"]) + "**（名义 alpha 0.05）。")
    add("- 离散精确口径的 alpha_eff（n = 7）：**" + "%.6f" % float(gate1["alpha_effective_discrete"])
        + "** ⇒ 精确检验在 n = 7 上比名义水平保守 **"
        + "%.4f" % (0.05 - float(gate1["alpha_effective_discrete"])) + "**。")
    add("- 置换抽样 MC（draws = " + str(mc["draws_permutation"]) + "）：tau_true = 0 时 **"
        + "%.5f" % float(mc["permutation_tau0_n7"]) + "**，tau_true = 0.6 时 **"
        + "%.5f" % float(mc["permutation_tau06_n7"]) + "**。")
    add("- 与 W33-B 精确零分布逐点对照：检查 " + str(payload["w33_check"]["points_checked"])
        + " 个网格点，最大绝对差 **" + "%.3e" % float(payload["w33_check"]["max_abs_delta"]) + "**。")
    add("- Gate 1 观测值 " + repr(float(gate1["observed_tau"])) + " 的精确单侧 p = **"
        + "%.6f" % float(gate1["observed_exact_p_upper"]) + "**，连续化临界值 "
        + "%.4f" % float(gate1["critical_tau_continuous"]) + " ⇒ 观测值远未过阈。")
    add("")
    add("> 一句话读数：**在 n = 7 上，Gate 1 的 0.9 阈连 tau_true = 0.8 都只有 "
        + "%.1f%%" % (100.0 * float(payload["retro_rows"][2]["prob_clear_threshold"]))
        + " 的通过率；要稳定分辨 tau = 0.4 需要约 "
        + str(int(payload["retro_rows"][0]["n_min_for_power"])) + " 个锚点。** 因此"
        "「机制脱节」与「功效不足」必须并列，不能只报前者。")
    add("")
    add("## 4 有限总体地板（R1 闭式，四通道）")
    add("")
    add("| 通道 | s0 | N_pop | sd(N=7) | sd(N=12) | sd(N=30) | Delta tau = 0.15 所需 N |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for row in payload["floor_rows"]:
        add("| " + str(row["label"]) + " | " + "%.4f" % float(row["s0"]) + " | "
            + "%.0f" % float(row["n_population"]) + " | " + "%.4f" % float(row["sd_n7"])
            + " | " + "%.4f" % float(row["sd_n12"]) + " | " + "%.4f" % float(row["sd_n30"])
            + " | " + "%.1f" % float(row["required_n_delta_015"]) + " |")
    add("")
    add("![图 23 W46-C 功效边界](../probes/artifacts/w46_taub_power.png)")
    add("")
    add("## 5 判据")
    add("")
    add("| 判据 | 描述 | 读数 | 阈值 | 结论 |")
    add("| --- | --- | --- | --- | --- |")
    for item in criteria:
        value = item["value"]
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        threshold = item["threshold"]
        ttext = threshold if isinstance(threshold, str) else json.dumps(threshold, ensure_ascii=False)
        add("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
            + " | " + ttext + " | " + str(item["verdict"]) + " |")
    add("")
    add("## 6 边界")
    add("")
    add("- 只读工具：不接主记分牌、不写标签池或特征列。")
    add("- shifted-null 是**预注册的替代模型**，不是物理机制；它只用来量化「n 太小时分不清」。")
    add("- 连续化零分布只在网格点之间插值，网格点上取值与精确零分布逐位相同。")
    add("- 0 shot；四个冻结读数一个不动。")
    add("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, TOOL_PATH, W33_TOOL_PATH, W33_SUMMARY_PATH, RANK_JSON]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H46c10", "输入（prereg + 工具 + W33 工具与摘要 + W32 秩稳定表）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(TABLE_CSV, TABLE_FIELDS, payload["table"])
        write_csv_lf(MDE_CSV, MDE_FIELDS, payload["mde_rows"])
        write_csv_lf(RETRO_CSV, RETRO_FIELDS, payload["retro_rows"])
        write_csv_lf(ARTIFACTS / "w46_taub_power_floor.csv", FLOOR_FIELDS, payload["floor_rows"])
        render_figure(payload, FIGURE_PATH)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读功效工具化，不接主记分牌、不写标签池或特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "alpha": payload["alpha"],
            "power_target": payload["power_target"],
            "table": payload["table"],
            "mde_rows": payload["mde_rows"],
            "retro_rows": payload["retro_rows"],
            "floor_rows": payload["floor_rows"],
            "mc": payload["mc"],
            "gate1": payload["gate1"],
            "w33_check": payload["w33_check"],
            "figure": "probes/artifacts/w46_taub_power.png",
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "Gate 1（n = 7）的 0.9 阈：tau_true = 0.8 时过阈概率 "
                + "%.6f" % float(payload["retro_rows"][2]["prob_clear_threshold"]) + "。",
                "达到 80% 功效所需锚点数：tau_true = 0.4 -> "
                + str(payload["retro_rows"][0]["n_min_for_power"]) + "，0.6 -> "
                + str(payload["retro_rows"][1]["n_min_for_power"]) + "，0.8 -> "
                + str(payload["retro_rows"][2]["n_min_for_power"]) + "。",
                "MDE（n = 7）= " + repr(mde(7, 0.05, 0.8)) + "；n = 30 时降到 "
                + repr(mde(30, 0.05, 0.8)) + "。",
                "离散精确口径 alpha_eff(7) = " + repr(payload["gate1"]["alpha_effective_discrete"])
                + "（名义 0.05）。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    retro = payload["retro_rows"]
    print("retro n=7:", ", ".join("tau=%s power=%.4f clear0.9=%.4f n_min=%s"
                                  % (row["tau_true"], row["power_continuous"],
                                     row["prob_clear_threshold"], row["n_min_for_power"])
                                  for row in retro))
    print("mde:", ", ".join("n=%d %.4f" % (row["n"], row["mde"]) for row in payload["mde_rows"]))
    print("mc continuous tau0 %.5f | permutation tau0 %.5f tau0.6 %.5f | alpha_eff %.6f"
          % (payload["mc"]["continuous_tau0_n7"], payload["mc"]["permutation_tau0_n7"],
             payload["mc"]["permutation_tau06_n7"], payload["gate1"]["alpha_effective_discrete"]))
    print("w33 max abs delta %.3e" % payload["w33_check"]["max_abs_delta"])
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
