# -*- coding: utf-8 -*-
"""W31-A -- 母体论文 v6 的三条结论与本仓读数的跨层级对接。

性质：**后验读数**（post-hoc）。只读盘上已冻结的产物表与本仓在 v6 结语里
已经发表的读数；不重新拟合、不新增特征列、不联网、不占主记分牌 shot。

对接的三条 v6 结论（v6 PDF 第 4 节 结语，p27-p28）：
  C1 值误差与排序误差是近似独立的两个量（MAE 变小 18 倍，tau_b 反而更低）；
  C2 改写排序的不是位移幅值而是位移离散度，并给出闭式判据 sigma_ij；
  C3 若干「昂贵层」在排序意义上可省，从而得到小分子集的最小信息预算。

本探针把 C1/C2 抬到「三层」上（电子结构层级 / 分子表示族 / 模型超参），
并用本仓的抽样误差律去核 v6 自己给出的噪声地板 0.126（N = 10）。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


REPO_ROOT = Path(__file__).resolve().parents[1]

ARTIFACTS = REPO_ROOT / "probes" / "artifacts"
OUT_CSV = ARTIFACTS / "w31_v6_bridge.csv"
OUT_JSON = ARTIFACTS / "w31_v6_bridge.json"
OUT_PNG = ARTIFACTS / "w31_v6_bridge.png"
OUT_MD = REPO_ROOT / "reports" / "w31_v6_bridge.md"

SAMPLING_LAW_CSV = ARTIFACTS / "w24_3_sampling_law.csv"
LEVEL_CROSSCHECK_CSV = ARTIFACTS / "w24_3_level_crosscheck.csv"
W28_REPEATS = ARTIFACTS / "w28_dense_hyperparameters_repeats.csv"
W29_REPEATS = ARTIFACTS / "w29_dense_binning_repeats.csv"
W30_REPEATS = ARTIFACTS / "w30_combination_ladder_repeats.csv"
W30_SUMMARY = REPO_ROOT / "probes" / "w30_combination_ladder_summary.json"

#: 母体论文 v6 已发表读数。只读引用，不重算、不改写。
V6_LEVELS = (
    ("GFN2-xTB dSCF", 4.48, 0.91),
    ("Koopmans", 1.38, 0.61),
    ("r2SCAN-3c", 0.25, 0.73),
)
V6_SD_AT_N10 = 0.126
V6_RHO_STD_TAU = -0.8511
V6_RHO_ABSMEAN_TAU = -0.5350
V6_RHO_STD_FUNRESOLVED = 0.894

LADDERS = (
    ("W28 固定档位阶梯", "grid_fixed_", W28_REPEATS,
     "probes/artifacts/w28_dense_hyperparameters_repeats.csv"),
    ("W29 分箱阶梯", "binning_", W29_REPEATS,
     "probes/artifacts/w29_dense_binning_repeats.csv"),
    ("W30 组合阶梯", "combination_", W30_REPEATS,
     "probes/artifacts/w30_combination_ladder_repeats.csv"),
)

REPRESENTATION_ARMS = (
    ("lever4_morgan_frozen", "稀疏 Morgan 块（冻结超参）"),
    ("lever4_morgan_retuned", "稀疏 Morgan 块（重调超参）"),
    ("lever4_physical_frozen", "稠密 Physical 13 列块（冻结超参）"),
    ("lever4_physical_retuned", "稠密 Physical 13 列块（重调超参）"),
)
PLACEBO_ARM = "lever4_physical_retuned_shuffled_target"

SAMPLING_LAW_SOURCE = "probes/artifacts/w24_3_sampling_law.csv（冻结，W24-3 后验产物）"
V6_SOURCE = "母体论文 v6 PDF 第 4 节 结语 p27-p28"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def mean(values) -> float:
    values = [float(value) for value in values]
    return float(sum(values) / len(values)) if values else float("nan")


def median(values) -> float:
    values = sorted(float(value) for value in values)
    if not values:
        return float("nan")
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def upper_middle(values) -> float:
    values = sorted(float(value) for value in values)
    return values[len(values) // 2]


def arm_means(path: Path, prefix: str, metric: str) -> dict[str, float]:
    buckets = defaultdict(list)
    for row in read_rows(path):
        if row["arm"].startswith(prefix):
            buckets[row["arm"]].append(float(row[metric]))
    return {arm: mean(values) for arm, values in sorted(buckets.items())}


def ladder_row(label: str, prefix: str, path: Path, source: str) -> dict[str, object]:
    r2 = arm_means(path, prefix, "r2")
    auc = arm_means(path, prefix, "auc_gt30")
    r2_values = list(r2.values())
    auc_values = list(auc.values())
    r2_range = max(r2_values) - min(r2_values)
    auc_range = max(auc_values) - min(auc_values)
    return {
        "layer": "hyperparameter",
        "family": label,
        "n_entries": len(r2_values),
        "magnitude_metric": "R2 档位间极差",
        "magnitude_range": r2_range,
        "order_metric": "AUC(eps>30) 档位间极差",
        "order_range": auc_range,
        "range_ratio": r2_range / auc_range if auc_range else float("inf"),
        "best_entry": max(r2, key=lambda arm: r2[arm]),
        "best_r2": max(r2_values),
        "worst_entry": min(r2, key=lambda arm: r2[arm]),
        "worst_r2": min(r2_values),
        "source": source,
    }


def sampling_table() -> list[dict[str, float]]:
    rows = []
    for row in read_rows(SAMPLING_LAW_CSV):
        s0 = float(row["s0"])
        n_pop = float(row["n_population"])
        entry = {"series": row["series"], "n_population": n_pop, "s0": s0,
                 "fit_rmse": float(row["fit_rmse"])}
        for n in (10, 12, 18, 25):
            entry[f"sd_at_n{n}"] = s0 * (1.0 / n - 1.0 / n_pop) ** 0.5
        rows.append(entry)
    return rows


def level_layer_rows() -> list[dict[str, object]]:
    cross = read_rows(LEVEL_CROSSCHECK_CSV)[0]
    rows = []
    baseline_mae, baseline_tau = V6_LEVELS[0][1], V6_LEVELS[0][2]
    for name, mae, tau in V6_LEVELS[1:]:
        rows.append({
            "layer": "electronic-structure level",
            "family": "v6 气相台阶：GFN2-xTB dSCF -> " + name,
            "n_entries": 2,
            "magnitude_metric": "MAE / eV",
            "magnitude_from": baseline_mae,
            "magnitude_to": mae,
            "magnitude_range": baseline_mae - mae,
            "magnitude_ratio": baseline_mae / mae,
            "order_metric": "tau_b",
            "order_from": baseline_tau,
            "order_to": tau,
            "order_range": abs(baseline_tau - tau),
            "order_signed_change": tau - baseline_tau,
            "source": V6_SOURCE,
        })
    rows.append({
        "layer": "electronic-structure level",
        "family": "本仓 R6：同 22 化合物、只换层级（还原轴）",
        "n_entries": 2,
        "magnitude_metric": "还原轴位移极差 / eV",
        "magnitude_from": float(cross["gfn2_red_shift_spread"]),
        "magnitude_to": float(cross["orca_red_shift_spread"]),
        "magnitude_range": float(cross["orca_red_shift_spread"]) - float(cross["gfn2_red_shift_spread"]),
        "magnitude_ratio": float(cross["dispersion_ratio"]),
        "order_metric": "tau_b（还原轴）",
        "order_from": float(cross["same_red_gfn2"]),
        "order_to": float(cross["same_red_orca"]),
        "order_range": abs(float(cross["red_move"])),
        "order_signed_change": float(cross["red_move"]),
        "source": "probes/artifacts/w24_3_level_crosscheck.csv（冻结，W24-3 后验产物）",
    })
    return rows


def representation_layer_rows() -> list[dict[str, object]]:
    metrics = {}
    for arm, label in REPRESENTATION_ARMS:
        r2 = arm_means(W28_REPEATS, arm, "r2")[arm]
        auc = arm_means(W28_REPEATS, arm, "auc_gt30")[arm]
        metrics[arm] = (label, r2, auc)
    morgan_r2 = metrics["lever4_morgan_frozen"][1]
    physical_r2 = metrics["lever4_physical_frozen"][1]
    morgan_auc = metrics["lever4_morgan_frozen"][2]
    physical_auc = metrics["lever4_physical_frozen"][2]
    placebo_r2 = arm_means(W28_REPEATS, PLACEBO_ARM, "r2")[PLACEBO_ARM]
    placebo_auc = arm_means(W28_REPEATS, PLACEBO_ARM, "auc_gt30")[PLACEBO_ARM]
    rows = [{
        "layer": "representation family",
        "family": "W28 lever4：稀疏 Morgan 块 -> 稠密 Physical 13 列块（两端都冻结超参）",
        "n_entries": 2,
        "magnitude_metric": "R2",
        "magnitude_from": morgan_r2,
        "magnitude_to": physical_r2,
        "magnitude_range": physical_r2 - morgan_r2,
        "magnitude_ratio": None,
        "order_metric": "AUC(eps>30)",
        "order_from": morgan_auc,
        "order_to": physical_auc,
        "order_range": abs(physical_auc - morgan_auc),
        "order_signed_change": physical_auc - morgan_auc,
        "source": "probes/artifacts/w28_dense_hyperparameters_repeats.csv（1 种子 x 1 重复，过程对照级）",
    }, {
        "layer": "placebo",
        "family": "W28 安慰剂（打乱标签）对同臂真实读数",
        "n_entries": 2,
        "magnitude_metric": "R2",
        "magnitude_from": placebo_r2,
        "magnitude_to": physical_r2,
        "magnitude_range": physical_r2 - placebo_r2,
        "magnitude_ratio": None,
        "order_metric": "AUC(eps>30)",
        "order_from": placebo_auc,
        "order_to": physical_auc,
        "order_range": abs(physical_auc - placebo_auc),
        "order_signed_change": physical_auc - placebo_auc,
        "source": "probes/artifacts/w28_dense_hyperparameters_repeats.csv（1 种子，过程对照级）",
    }]
    return rows


def build() -> dict[str, object]:
    law = sampling_table()
    sd10 = [entry["sd_at_n10"] for entry in law]
    sd12 = [entry["sd_at_n12"] for entry in law]
    sd18 = [entry["sd_at_n18"] for entry in law]

    ladder_rows = [ladder_row(label, prefix, path, "probes/artifacts/" + path.name)
                   for label, prefix, path, _ in LADDERS]
    rows = level_layer_rows() + representation_layer_rows() + ladder_rows

    hyper_ratios = [row["range_ratio"] for row in rows if row["layer"] == "hyperparameter"]
    readings = [
        {"id": "B1", "reading": "v6 的噪声地板被本仓闭式独立复核",
         "statistic": "v6 自报 sd(tau_b) @ N=10 对本仓 sd(N) 律在 N=10 的中位",
         "v6_value": V6_SD_AT_N10,
         "ours_median": median(sd10), "ours_mean": mean(sd10),
         "ours_min": min(sd10), "ours_max": max(sd10),
         "relative_gap": abs(median(sd10) - V6_SD_AT_N10) / V6_SD_AT_N10,
         "unit": "tau_b",
         "support": "两个独立项目（18 分子台阶 vs 246 分子普查）给出同量级噪声地板"},
        {"id": "B2", "reading": "量级/序独立性在本仓超参层复现",
         "statistic": "R2 档位间极差 / AUC(eps>30) 档位间极差（三条阶梯的最小值）",
         "value": min(hyper_ratios), "unit": "倍",
         "support": "同一表示、同一折、同一种子集，只动超参：量级可挪的幅度是序的 8 倍以上"},
        {"id": "B3", "reading": "表示族是两量独立性的边界（反例）",
         "statistic": "稀疏 Morgan -> 稠密 Physical 时 R2 与 AUC30 的同时变化",
         "value": None, "unit": "R2 / AUC",
         "support": "换表示族时两个量一起动，说明独立性只在同一族内成立"},
        {"id": "B4", "reading": "气相阴离子不束缚在两个项目上一致",
         "statistic": "本仓普查层（GFN2）与配对层（ORCA）的阴离子不束缚占比",
         "value": None, "unit": "占比",
         "support": "ORCA 层 1.0000 与 v6 的 18/18 一致；普查层只有 0.7642，差的是层级"},
        {"id": "B5", "reading": "噪声地板口径更正（AF-12 同族）",
         "statistic": "W24-3 记录值 0.1335681773982666 与六条 sd@N=12 的真中位之比",
         "recorded": 0.1335681773982666,
         "true_median": median(sd12), "true_mean": mean(sd12),
         "upper_middle": upper_middle(sd12),
         "unit": "tau_b",
         "support": "论文把 0.134 写成「六条的中位」，但 0.1336 是六条排序后的上中位（也是三条氧化轴序列的中位）；真中位是 0.1222"},
    ]

    cross = read_rows(LEVEL_CROSSCHECK_CSV)[0]
    readings[3]["value"] = float(cross["unbound_share_paired_orca"])
    readings[3]["census_value"] = float(cross["unbound_share_census"])
    readings[2]["value"] = rows[3]["magnitude_range"]

    return {
        "schema": "w31_v6_bridge/summary@1",
        "task": "week31_v6_bridge",
        "post_hoc": True,
        "new_shot": 0,
        "title": "母体论文 v6 的三条结论 × 本仓三层读数",
        "v6_readings": {
            "source": V6_SOURCE,
            "levels": [{"name": name, "mae_eV": mae, "tau_b": tau} for name, mae, tau in V6_LEVELS],
            "sd_tau_b_at_n10": V6_SD_AT_N10,
            "rho_std_tau": V6_RHO_STD_TAU,
            "rho_absmean_tau": V6_RHO_ABSMEAN_TAU,
            "rho_std_funresolved": V6_RHO_STD_FUNRESOLVED,
        },
        "readings": readings,
        "sampling_law": law,
        "layer_table": rows,
        "sources": {
            "sampling_law": SAMPLING_LAW_SOURCE,
            "level_crosscheck": "probes/artifacts/w24_3_level_crosscheck.csv",
            "w28": "probes/artifacts/w28_dense_hyperparameters_repeats.csv",
            "w29": "probes/artifacts/w29_dense_binning_repeats.csv",
            "w30": "probes/artifacts/w30_combination_ladder_repeats.csv",
        },
    }


def fmt(value, digits=6):
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def format_report(payload) -> str:
    lines = []
    lines.append("# W31-A 结题报告：母体论文 v6 的三条结论 × 本仓三层读数")
    lines.append("")
    lines.append("- **性质**：后验读数（post-hoc）。只读冻结产物与 v6 已发表读数；不重新拟合、不联网、**不占主记分牌 shot**。")
    lines.append("- **对照对象**：母体论文 v6（`" + V6_SOURCE + "`）。")
    lines.append("- **输入**：`probes/artifacts/w24_3_sampling_law.csv`、`w24_3_level_crosscheck.csv`、`w28/w29/w30` 三张重复表，逐位只读。")
    lines.append("- **产出**：`probes/artifacts/w31_v6_bridge.csv` / `.json` / `.png`。")
    lines.append("")
    lines.append("## 0. 一句话")
    lines.append("")
    lines.append("v6 把「廉价代理能不能用于筛选」从数值误差改写成排序稳定性，并在**电子结构层级**上给出三条结论；"
                 "本仓把同一套问题搬到**分子表示族**与**模型超参**两层，得到的是同一条规律的三个刻度："
                 "**量级可以被层级、表示和超参三类操作大幅移动，序在每一族内部近似不动。**"
                 "唯一同时移动两个量的（非安慰剂）层是**换表示族**——这正是这条规律的边界。")
    lines.append("")
    lines.append("## 1. 三层独立性表")
    lines.append("")
    lines.append("| 层 | 对照 | 量级侧 | 序侧 | 量级/序 | 来源 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in payload["layer_table"]:
        if row["layer"] == "hyperparameter":
            magnitude = ("档位间极差（R²）= " + fmt(row["magnitude_range"], 4))
            order = ("档位间极差（AUC(ε>30)）= " + fmt(row["order_range"], 4))
            ratio = fmt(row["range_ratio"], 1) + " 倍"
        else:
            magnitude = (row["magnitude_metric"] + " " + fmt(row["magnitude_from"], 4)
                         + " → " + fmt(row["magnitude_to"], 4)
                         + "（变化 " + fmt(row["magnitude_range"], 4) + "）")
            order = (row["order_metric"] + " " + fmt(row["order_from"], 4)
                     + " → " + fmt(row["order_to"], 4)
                     + "（变化 " + fmt(abs(row["order_signed_change"]), 4) + "）")
            ratio = "—"
        lines.append("| " + row["layer"] + " | " + row["family"] + " | " + magnitude
                     + " | " + order + " | " + ratio + " | " + row["source"] + " |")
    lines.append("")
    lines.append("## 2. v6 的噪声地板被本仓独立复核（B1）")
    lines.append("")
    lines.append("| 序列 | N_pop | s0 | 拟合 rmse | sd@N=10 | sd@N=12 | sd@N=18 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in payload["sampling_law"]:
        lines.append("| `" + entry["series"] + "` | " + fmt(entry["n_population"], 0) + " | "
                     + fmt(entry["s0"], 3) + " | " + fmt(entry["fit_rmse"], 4) + " | "
                     + fmt(entry["sd_at_n10"], 4) + " | " + fmt(entry["sd_at_n12"], 4) + " | "
                     + fmt(entry["sd_at_n18"], 4) + " |")
    reading = payload["readings"][0]
    lines.append("")
    lines.append("- v6 自报 `sd(tau_b) @ N=10 = 0.126`；本仓闭式在 N=10 给 **中位 "
                 + fmt(reading["ours_median"], 4) + " / 均值 " + fmt(reading["ours_mean"], 4)
                 + "**（区间 " + fmt(reading["ours_min"], 4) + "–" + fmt(reading["ours_max"], 4) + "）。")
    lines.append("- 两个项目、两套代码、两个化合物池（18 vs 246），给出同一量级的噪声地板；"
                 "相对差 " + fmt(100.0 * reading["relative_gap"], 1) + "%。")
    lines.append("- 这条读数把 v6 局限里的「样本规模」从一句免责声明变成可复算的数：**在 N=10–12 上，"
                 "小于约 0.12–0.13 的两档 `tau_b` 差异不可读**。")
    lines.append("")
    lines.append("## 3. 三条 v6 结论的本仓落点")
    lines.append("")
    lines.append("| v6 结论 | v6 的原证据 | 本仓的对应读数 | 状态 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| C1 值误差与排序误差近似独立 | GFN2 气相 MAE 4.48 eV / `tau_b` 0.91；r2SCAN-3c MAE 0.25 eV / `tau_b` 0.73 | 同一表示、同一折、只动超参：R² 档位间极差 0.0989–0.1525，AUC(ε>30) 极差 0.0056–0.0189 | **复现（换层）** |")
    lines.append("| C2 改写排序的是位移离散度，且有闭式判据 | `rho(std, tau_b) = -0.8511`（10 台阶） | 本仓 38 台阶-轴上 `-0.7878`（W25 已交付）；噪声地板闭式 `sd(N) = s0*sqrt(1/N - 1/N_pop)` | **复现（扩样）** |")
    lines.append("| C3 若干昂贵层在排序意义上可省 | 几何台阶 `std ≈ 0.05–0.08 eV` / `tau_b ≥ 0.85`；`|ΔE|·ε ≈ 2.1 eV` 幂律 | 超参侧同样可省：深度 2 -> 4 只值 `+0.0045840097020970`；六档组合无一超过注册臂 `0.6216672295270079` | **扩到 ML 侧** |")
    lines.append("")
    lines.append("C3 的迁移是本轮最有信息量的一条：v6 的「最小信息预算」只覆盖电子结构维度，"
                 "本仓在**排序口径**下补上 ML 维度——**模型容量也是可省的**，"
                 "把深度从 2 提到 4 换来的量级增益不到 0.005，而六档组合点的最高值仍停在注册臂。")
    lines.append("")
    lines.append("## 4. 边界与口径（必须并报）")
    lines.append("")
    lines.append("1. **B3 是反例，不是例外**：换表示族（稀疏 Morgan -> 稠密 Physical）时 R² 与 AUC30 同时移动"
                 "（" + fmt(payload["layer_table"][3]["magnitude_range"], 4) + " / "
                 + fmt(payload["layer_table"][3]["order_range"], 4) + "）。"
                 "因此「量级与序独立」只在**同一表示族内部**成立，不得外推成普适命题。")
    lines.append("2. **v6 的读数是引用，不是重算**：本探针不重跑 v6 的电子结构台阶，v6 侧数字全部转自其结语页。")
    lines.append("3. **B5 是口径更正**：W24-3 记录值 `0.1335681773982666` 是六条 `sd@N=12` 排序后的**上中位**"
                 "（也恰好等于三条氧化轴序列的中位），而论文把它写成「六条的中位」；"
                 "六条的真中位是 `" + fmt(payload["readings"][4]["true_median"], 4)
                 + "`、均值 `" + fmt(payload["readings"][4]["true_mean"], 4) + "`。"
                 "本件**不修改 W24-3 的任何冻结产物**，只在论文与 README 的口径描述里改正统计量名称。")
    lines.append("4. **过程对照级读数**：Morgan 两臂与安慰剂臂各只有 1 个种子 x 1 个重复，"
                 "按 W28/W30-A 的既有声明不作结论级主张。")
    lines.append("")
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

        figure, axes = plt.subplots(1, 2, figsize=(13.0, 5.0))
        markers = {"hyperparameter": ("o", "#1f3b63"), "representation family": ("s", "#c0392b")}
        for row in payload["layer_table"]:
            if row["layer"] not in markers:
                continue
            style, color = markers[row["layer"]]
            axes[0].scatter(row["magnitude_range"], row["order_range"], marker=style,
                            color=color, s=90, zorder=3)
            axes[0].annotate(row["family"][:22], (row["magnitude_range"], row["order_range"]),
                             textcoords="offset points", xytext=(6, 6), fontsize=7)
        limits = [0.004, 0.8]
        axes[0].plot(limits, limits, color="#7f8c8d", linestyle="--", linewidth=1.0)
        axes[0].plot(limits, [value / 8.0 for value in limits], color="#16a085",
                     linestyle=":", linewidth=1.0, label="量级/序 = 8")
        axes[0].plot(limits, [value / 20.0 for value in limits], color="#16a085",
                     linestyle="-", linewidth=0.8, label="量级/序 = 20")
        axes[0].set_xscale("log")
        axes[0].set_yscale("log")
        axes[0].set_xlim(*limits)
        axes[0].set_ylim(*limits)
        axes[0].set_xlabel("量级侧变化幅度（R² 极差）")
        axes[0].set_ylabel("序侧变化幅度（AUC(ε>30) 极差）")
        axes[0].set_title("A 三层上的量级—序位移：超参层贴 8–20 倍分隔线，表示层透出")
        axes[0].legend(fontsize=7)
        axes[0].grid(alpha=0.25, which="both")

        for entry in payload["sampling_law"]:
            grid = list(range(10, 121, 5))
            values = [entry["s0"] * (1.0 / n - 1.0 / entry["n_population"]) ** 0.5 for n in grid]
            axes[1].plot(grid, values, linewidth=1.0, alpha=0.85)
        law_rows = payload["sampling_law"]
        sd10 = [entry["sd_at_n10"] for entry in law_rows]
        sd12 = [entry["sd_at_n12"] for entry in law_rows]
        axes[1].scatter([10.0], [V6_SD_AT_N10], color="#c0392b", marker="*", s=170, zorder=4,
                        label="v6 自报 sd@N=10 = 0.126")
        axes[1].scatter([10.0], [sum(sd10) / len(sd10)], color="#1f3b63", marker="x", s=80,
                        zorder=4, label="本仓闭式均值 @ N=10")
        axes[1].scatter([12.0], [sum(sd12) / len(sd12)], color="#16a085", marker="x", s=80,
                        zorder=4, label="本仓闭式均值 @ N=12")
        axes[1].axhline(0.134, color="#7f8c8d", linestyle=":", linewidth=1.0)
        axes[1].annotate("论文原记 0.134（上中位）", (60.0, 0.134), fontsize=7,
                         textcoords="offset points", xytext=(0, 6))
        axes[1].set_xlabel("子样本量 N")
        axes[1].set_ylabel("sd(tau_b)")
        axes[1].set_title("B 抽样误差律：六条实测曲线与 v6 的独立估计")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W31-A 母体论文 v6 结论 x 本仓三层读数（后验，不占 shot）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(OUT_PNG, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover - plotting is best effort
        print("figure failure: " + type(error).__name__ + ": " + str(error))
        return False


def main() -> int:
    payload = build()
    rows = payload["layer_table"]
    header = ["layer", "family", "n_entries", "magnitude_metric", "magnitude_from", "magnitude_to",
              "magnitude_range", "magnitude_ratio", "order_metric", "order_from", "order_to",
              "order_range", "order_signed_change", "source"]
    write_csv(OUT_CSV, header, [[row.get(column) for column in header] for row in rows])
    write_json(OUT_JSON, payload)
    OUT_MD.write_text(format_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)
    print("wrote " + str(OUT_CSV))
    print("wrote " + str(OUT_JSON))
    print("wrote " + str(OUT_MD))
    print("figure " + ("ok" if figure_ok else "skipped"))
    for reading in payload["readings"]:
        print("[" + reading["id"] + "] " + reading["reading"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())