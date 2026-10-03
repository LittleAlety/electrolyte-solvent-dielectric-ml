# -*- coding: utf-8 -*-
"""W33-B：Kendall tau_b 的精确零分布工具（P4 的最快兑现件，不占 shot）。

R1 的闭式 `sd(N) = s0·sqrt(1/N - 1/N_pop)` 是**拟合**出来的；而小样本的零分布可以**精确**
算出来：Kendall tau_b（无并列）与逆序数 K 一一对应
    tau = 1 - 4K / (n(n-1)),
而逆序数的 Mahonian 分布由生成函数 `prod_{i=1..n}(1 + x + ... + x^{i-1})` 精确给出。于是

* 精确 p 值与精确临界值（alpha = 0.05 / 0.01 / 0.001）不需要正态近似（用 Fraction 精确有理数）；
* 精确 sd(tau_null) = sqrt(2(2n+5) / (9n(n-1)))；
* 把精确 sd 与 R1 闭式并排给出（口径不同：零分布对应无限总体，闭式对应有限总体 N_pop）；
* 给 P1/P2 预注册用的 CLI：`--n` 查临界值与 p 值，`--channel/--target` 反查所需 N。

只读（可选）`probes/artifacts/w32_rank_stability.json` 取各通道的 s0 与 N_pop。不联网、不装依赖。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from fractions import Fraction
from pathlib import Path

from export_results_common import write_json_stable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RANK_JSON = REPOSITORY_ROOT / "probes" / "artifacts" / "w32_rank_stability.json"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = ARTIFACTS / "w33_kendall_null_summary.json"
TABLE_CSV = ARTIFACTS / "w33_kendall_null_table.csv"
BUDGET_CSV = ARTIFACTS / "w33_kendall_null_budget.csv"
FIGURE_PATH = ARTIFACTS / "w33_kendall_null.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w33_kendall_null_tool.md"

SCHEMA = "w33_kendall_null/summary@1"
TASK = "week33_kendall_null_tool"
ALPHAS = (0.05, 0.01, 0.001)
N_GRID = tuple(range(5, 13))
ANCHOR_N = 7
ANCHOR_TAU = 0.90
TARGETS = (0.05, 0.10, 0.15, 0.20)
POWER_FACTOR = 2.80 * math.sqrt(2.0)
SCALING_SPREAD_GATE = 0.25
ANCHOR_P_GATE = 0.01
CHANNELS = ("dielectric", "viscosity", "orbital", "redox")


def mahonian_counts(n: int) -> list:
    """逆序数为 K 的排列数（K = 0..n(n-1)/2），精确整数。"""
    counts = [1]
    for size in range(2, n + 1):
        limit = size * (size - 1) // 2
        nxt = [0] * (limit + 1)
        for index, value in enumerate(counts):
            if value:
                for offset in range(size):
                    nxt[index + offset] += value
        counts = nxt
    return counts


def tau_from_inversions(inversions: int, n: int) -> float:
    return 1.0 - 4.0 * inversions / (n * (n - 1))


def exact_sd(n: int) -> float:
    return math.sqrt(2.0 * (2 * n + 5) / (9.0 * n * (n - 1)))


def p_upper(n: int, tau: float) -> Fraction:
    """P(tau_null >= tau)，精确有理数。"""
    counts = mahonian_counts(n)
    total = sum(counts)
    keep = Fraction(0)
    for inversions, count in enumerate(counts):
        if tau_from_inversions(inversions, n) >= tau - 1e-12:
            keep += Fraction(count, total)
    return keep


def critical_tau(n: int, alpha: float) -> float:
    """alpha 水平下的最小显著 tau（单侧上尾）。

    tau 随逆序数 K **递减**，所以上尾对应小 K：取「累积概率仍 <= alpha 的最大 K」，
    即该 K 对应的 tau 是仍能在 alpha 水平上被判显著的最小值。
    """
    counts = mahonian_counts(n)
    total = sum(counts)
    target = Fraction(alpha).limit_denominator(10 ** 9)
    best = None
    cumulative = 0
    for inversions, count in enumerate(counts):
        cumulative += count
        if Fraction(cumulative, total) <= target:
            best = inversions
    return float("nan") if best is None else tau_from_inversions(best, n)


def p_value_table(n: int) -> list:
    counts = mahonian_counts(n)
    total = sum(counts)
    rows = []
    for inversions in range(len(counts)):
        rows.append({"inversions": inversions,
                     "tau": tau_from_inversions(inversions, n),
                     "count": counts[inversions],
                     "p_upper": float(Fraction(sum(counts[inversions:]), total))})
    return rows


def load_channels() -> dict:
    if not RANK_JSON.is_file():
        return {}
    payload = json.loads(RANK_JSON.read_text(encoding="utf-8"))
    out = {}
    for row in payload.get("channels", []):
        out[row["channel"]] = {"label": row["label"], "s0": float(row["s0_median"]),
                              "n_population": float(row["n_population_median"])}
    return out

def required_n(s0: float, n_population: float, target: float) -> tuple:
    inner = (target / (POWER_FACTOR * s0)) ** 2 + 1.0 / n_population
    value = 1.0 / inner
    return value, bool(value <= n_population)


def build_table() -> list:
    rows = []
    for n in N_GRID:
        sd = exact_sd(n)
        entry = {"n": n, "sd_exact": sd, "sd_times_sqrt_n": sd * math.sqrt(n),
                 "median_tau_step": 2.0 / (n * (n - 1))}
        for alpha in ALPHAS:
            entry["critical_tau_alpha_" + str(alpha).replace(".", "_")] = critical_tau(n, alpha)
        rows.append(entry)
    return rows


def build_budget(channels: dict) -> list:
    rows = []
    for name in CHANNELS:
        payload = channels.get(name)
        if not payload:
            continue
        for target in TARGETS:
            value, reachable = required_n(payload["s0"], payload["n_population"], target)
            rows.append({"channel": name, "label": payload["label"], "s0": payload["s0"],
                         "n_population": payload["n_population"], "target": target,
                         "required_n": value, "reachable": bool(reachable)})
    return rows


def evaluate(rows: list) -> list:
    scales = [entry["sd_times_sqrt_n"] for entry in rows]
    median = sorted(scales)[len(scales) // 2]
    spread = (max(scales) - min(scales)) / median
    anchor_p = float(p_upper(ANCHOR_N, ANCHOR_TAU))
    criticals = [entry["critical_tau_alpha_0_05"] for entry in rows]
    monotone = all(criticals[index] >= criticals[index + 1] - 1e-12
                   for index in range(len(criticals) - 1))
    return [
        {"id": "H33g", "description": "1/sqrt(n) 律：精确零分布 sd(n)·sqrt(n) 在 n = 5..12 上的极差/中位",
         "value": spread, "threshold": SCALING_SPREAD_GATE,
         "verdict": "成立" if spread <= SCALING_SPREAD_GATE else "判否"},
        {"id": "H33h", "description": "锚点规模显著性：n = 7 时 tau >= 0.90 的精确单侧 p 值",
         "value": anchor_p, "threshold": ANCHOR_P_GATE,
         "verdict": "成立" if anchor_p <= ANCHOR_P_GATE else "判否"},
        {"id": "H33i", "description": "临界值单调性：alpha = 0.05 的精确临界 tau 随 n（5..12）单调不增",
         "value": criticals[-1] - criticals[0], "threshold": 0.0,
         "verdict": "成立" if monotone else "判否"},
    ]


def write_csv(path, fieldnames, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def dump_json(path, payload) -> None:
    write_json_stable(Path(path), payload)


def fmt(value, digits=6) -> str:
    if value is None:
        return "——"
    return format(float(value), "." + str(digits) + "f")


def format_report(payload) -> str:
    lines = []
    add = lines.append
    add("# W33-B：Kendall tau_b 的精确零分布与立项前预算工具")
    add("")
    add("**性质**：统计工具化（P4）。不拟合模型、不占主记分牌 shot（累计仍 "
        + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"]) + "）、不联网。")
    add("")
    add("## 0. 一句话（全部由数据推出）")
    add("")
    add("- **精确、不靠正态近似**：Kendall tau_b 与逆序数一一对应（`tau = 1 - 4K/(n(n-1))`），"
        "逆序数的 Mahonian 分布可精确枚举 ⇒ p 值与临界值用有理数精确算。")
    add("- **锚点 n = 7 上 0.90 是显著的**：`P(tau_null >= 0.90) = " + fmt(payload["criteria"][1]["value"], 6)
        + "`（判据门 " + fmt(payload["criteria"][1]["threshold"], 2) + "）⇒ 母体论文那条 n=7 的 0.9 阈值"
        "不是拍出来的，是精确算得出来的。")
    add("- **1/sqrt(n) 律在 n = 5..12 上成立**：`sd(n)·sqrt(n)` 的极差/中位 = "
        + fmt(payload["criteria"][0]["value"], 4) + "（门 " + fmt(payload["criteria"][0]["threshold"], 2)
        + "）⇒ R1 闭式的 1/sqrt(N) 形状在小 N 外推上也站得住。")
    add("- **口径不同不能混比**：精确零分布对应「无限总体、纯随机排列」，R1 闭式对应「有限总体 N_pop」；"
        "两者只在同一 N 上并排展示，不相互替换。")
    add("")
    add("## 1. 精确零分布表")
    add("")
    add("| n | 精确 sd | sd·sqrt(n) | tau 步长 | 临界 tau(0.05) | 临界 tau(0.01) | 临界 tau(0.001) |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in payload["table"]:
        add("| " + str(entry["n"]) + " | " + fmt(entry["sd_exact"], 5) + " | "
            + fmt(entry["sd_times_sqrt_n"], 5) + " | " + fmt(entry["median_tau_step"], 5) + " | "
            + fmt(entry["critical_tau_alpha_0_05"], 4) + " | "
            + fmt(entry["critical_tau_alpha_0_01"], 4) + " | "
            + fmt(entry["critical_tau_alpha_0_001"], 4) + " |")
    add("")
    add("## 2. 与 R1 闭式的并排对照（口径：零分布 = 无限总体；闭式 = 有限总体 N_pop）")
    add("")
    add("| 通道 | s0 | N_pop | 闭式 sd(N=7) | 精确 sd(n=7) | 闭式 sd(N=12) | 精确 sd(n=12) |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    exact_7 = next(entry["sd_exact"] for entry in payload["table"] if entry["n"] == 7)
    exact_12 = next(entry["sd_exact"] for entry in payload["table"] if entry["n"] == 12)
    for name in payload["channels"]:
        item = payload["channels"][name]
        closed_7 = item["s0"] * math.sqrt(1.0 / 7.0 - 1.0 / item["n_population"])
        closed_12 = item["s0"] * math.sqrt(1.0 / 12.0 - 1.0 / item["n_population"])
        add("| " + item["label"] + " | " + fmt(item["s0"], 4) + " | " + fmt(item["n_population"], 0)
            + " | " + fmt(closed_7, 5) + " | " + fmt(exact_7, 5) + " | " + fmt(closed_12, 5)
            + " | " + fmt(exact_12, 5) + " |")
    add("")
    add("## 3. 立项前预算：分得清多大的排序差")
    add("")
    add("规则（写死）：要把两套排序的差 `Delta tau` 判出来，取 `sigma_diff = sd·sqrt(2)`，"
        "80% 功效对应 `2.80·sigma_diff <= Delta tau` ⇒ `sd <= Delta tau / 3.96`。")
    add("")
    add("| 通道 | 目标 Delta tau | 所需 N | 是否可达（N <= N_pop） |")
    add("| --- | --- | --- | --- |")
    for row in payload["budget"]:
        add("| " + row["label"] + " | " + fmt(row["target"], 2) + " | " + fmt(row["required_n"], 1)
            + " | " + ("可达" if row["reachable"] else "不可达（总体不够）") + " |")
    add("")
    add("## 4. 判据（H33g–H33i）")
    add("")
    for item in payload["criteria"]:
        add("- **" + item["id"] + " " + item["verdict"] + "**：" + item["description"]
            + "（读数 " + fmt(item["value"], 6) + " 对阈值 " + fmt(item["threshold"], 3) + "）。")
    add("")
    add("## 5. CLI（预注册前随手算）")
    add("")
    add("```text")
    add("python probes\\w33_kendall_null_tool.py --n 7                     # 精确 sd 与三个 alpha 的临界 tau")
    add("python probes\\w33_kendall_null_tool.py --n 7 --tau 0.9           # 精确单侧 p 值")
    add("python probes\\w33_kendall_null_tool.py --n 7 --alpha 0.05        # 精确临界 tau")
    add("python probes\\w33_kendall_null_tool.py --channel dielectric --target 0.10   # 所需 N")
    add("python probes\\w33_kendall_null_tool.py                          # 重建全部产物")
    add("```")
    add("")
    add("## 6. 口径与边界")
    add("")
    add("- 精确零分布假设**无并列**（Kendall tau_a 口径）；有并列的真实读数按 tau_b 处理，"
        "此时精确表是**下界参考**，不得当作精确 p 值引用。")
    add("- 预算表的 s0 与 N_pop 取 W32-A 各通道中位，是**粗算**：正式预注册必须用该序列自己的 s0。")
    add("- 不改 METRIC_NAMES、不动冻结读数、不占 shot。")
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

        ns = [entry["n"] for entry in payload["table"]]
        scales = [entry["sd_times_sqrt_n"] for entry in payload["table"]]
        median = sorted(scales)[len(scales) // 2]
        figure, axes = plt.subplots(1, 2, figsize=(13.2, 5.2))
        axes[0].plot(ns, scales, marker="o", color="#1f3b63", linewidth=1.5,
                     label="精确 sd(n)·sqrt(n)")
        axes[0].axhline(median, color="#c0392b", linestyle="--", linewidth=1.0,
                        label="中位 " + fmt(median, 4))
        axes[0].fill_between(ns, median * (1 - SCALING_SPREAD_GATE), median * (1 + SCALING_SPREAD_GATE),
                             color="#c0392b", alpha=0.08, label="±25% 带")
        axes[0].set_xlabel("n（排序的条目数）")
        axes[0].set_ylabel("sd(n)·sqrt(n)")
        axes[0].set_title("A 1/sqrt(n) 律：精确零分布在 n = 5..12 上", fontsize=10.5)
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=0.25)

        for alpha, color in zip(ALPHAS, ("#1f3b63", "#16a085", "#8e44ad")):
            key = "critical_tau_alpha_" + str(alpha).replace(".", "_")
            axes[1].plot(ns, [entry[key] for entry in payload["table"]], marker="o",
                         color=color, linewidth=1.4, label="临界 tau（alpha = " + str(alpha) + "）")
        axes[1].axhline(ANCHOR_TAU, color="#e67e22", linestyle="--", linewidth=1.1,
                        label="母体论文锚点阈值 0.90（n = 7）")
        annotation = "P(tau >= 0.90 | n = 7) = " + fmt(payload["criteria"][1]["value"], 6)
        axes[1].annotate(annotation, (ANCHOR_N, ANCHOR_TAU), textcoords="offset points",
                         xytext=(10, 6), fontsize=8, color="#e67e22")
        axes[1].set_xlabel("n（排序的条目数）")
        axes[1].set_ylabel("临界 Kendall tau_b")
        axes[1].set_title("B 精确临界值：样本越小越需要高 tau", fontsize=10.5)
        axes[1].legend(fontsize=8)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W33-B Kendall tau_b 精确零分布（Mahonian DP，有理数精确）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:
        print("figure skipped: " + repr(error))
        return False

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Kendall tau_b 精确零分布与立项前预算工具")
    parser.add_argument("--n", type=int, default=None, help="排序的条目数（查询模式）")
    parser.add_argument("--tau", type=float, default=None, help="要查精确 p 值的 tau")
    parser.add_argument("--alpha", type=float, default=None, help="要查精确临界 tau 的显著性水平")
    parser.add_argument("--channel", choices=CHANNELS, default=None, help="通道名（配上 --target 反查所需 N）")
    parser.add_argument("--target", type=float, default=None, help="要分辨的 Delta tau")
    parser.add_argument("--json", action="store_true", help="以 JSON 打印结果")
    return parser.parse_args(argv)


def query(args, channels) -> int:
    n = int(args.n) if args.n else ANCHOR_N
    if n < 3:
        print("n 至少为 3")
        return 1
    payload = {"n": n, "sd_exact": exact_sd(n), "sd_times_sqrt_n": exact_sd(n) * math.sqrt(n),
               "critical_tau": {str(alpha): critical_tau(n, alpha) for alpha in ALPHAS}}
    if args.tau is not None:
        payload["p_upper"] = float(p_upper(n, float(args.tau)))
    if args.channel and args.target is not None:
        item = channels.get(args.channel)
        if item is None:
            print("通道 " + str(args.channel) + " 不在 W32-A 的通道表里")
            return 1
        value, reachable = required_n(item["s0"], item["n_population"], float(args.target))
        payload["budget"] = {"channel": args.channel, "label": item["label"], "target": float(args.target),
                             "s0": item["s0"], "n_population": item["n_population"],
                             "required_n": value, "reachable": bool(reachable)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("n = " + str(n) + " | 精确 sd = " + fmt(payload["sd_exact"])
          + " | sd*sqrt(n) = " + fmt(payload["sd_times_sqrt_n"]))
    for alpha in ALPHAS:
        print("  临界 tau(alpha = " + str(alpha) + ") = "
              + fmt(payload["critical_tau"][str(alpha)], 4))
    if "p_upper" in payload:
        print("  P(tau_null >= " + fmt(args.tau, 4) + ") = " + fmt(payload["p_upper"], 8))
    if "budget" in payload:
        item = payload["budget"]
        print("  通道 " + item["label"] + " 目标 Delta tau " + fmt(item["target"], 2)
              + " -> 所需 N ≈ " + fmt(item["required_n"], 1)
              + ("（可达）" if item["reachable"] else "（不可达：总体不够）"))
    return 0


def main(argv=None) -> int:
    started = time.perf_counter()
    args = parse_args(argv)
    channels = load_channels()
    if args.n or args.tau is not None or args.alpha is not None or args.channel or args.target is not None:
        return query(args, channels)
    table = build_table()
    budget = build_budget(channels)
    criteria = evaluate(table)
    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "统计工具化：输出精确零分布与临界值，不是模型读数，不触 ε 主记分牌。"},
        "method": {"null": "Mahonian（逆序数）分布，精确整数/有理数",
                   "tau_of_inversions": "tau = 1 - 4K/(n(n-1))",
                   "exact_sd": "sqrt(2(2n+5)/(9n(n-1)))",
                   "closed_form": "sd(N) = s0*sqrt(1/N - 1/N_pop)（R1，有限总体，拟合）",
                   "power_rule": "2.80*sqrt(2)*sd <= Delta tau"},
        "alphas": list(ALPHAS), "n_grid": list(N_GRID),
        "anchor": {"n": ANCHOR_N, "tau": ANCHOR_TAU, "p_upper": float(p_upper(ANCHOR_N, ANCHOR_TAU))},
        "channels": channels, "table": table, "budget": budget, "criteria": criteria,
        "inputs": ([{"path": "probes/artifacts/w32_rank_stability.json",
                     "sha256": __import__("hashlib").sha256(RANK_JSON.read_bytes()).hexdigest()}]
                   if RANK_JSON.is_file() else []),
    }
    fieldnames = tuple(table[0].keys())
    write_csv(TABLE_CSV, fieldnames, table)
    write_csv(BUDGET_CSV, ("channel", "label", "s0", "n_population", "target", "required_n",
                           "reachable"), budget)
    dump_json(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(format_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("exact sd: " + " | ".join("n=" + str(entry["n"]) + " " + fmt(entry["sd_exact"], 4)
                                    for entry in table), flush=True)
    print("anchor P(tau>=0.90 | n=7) = " + fmt(payload["anchor"]["p_upper"], 8), flush=True)
    print("critical tau(0.05): " + " | ".join("n=" + str(entry["n"]) + " "
                                              + fmt(entry["critical_tau_alpha_0_05"], 3)
                                              for entry in table), flush=True)
    print("wrote " + str(TABLE_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("wrote " + str(BUDGET_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("wrote " + str(SUMMARY_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("wrote " + str(REPORT_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(criteria)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())