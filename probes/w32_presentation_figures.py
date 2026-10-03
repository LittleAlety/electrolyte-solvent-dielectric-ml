# -*- coding: utf-8 -*-
"""W32 呈现层：把 W32-A / W32-B 的冻结产物画成四张直观图。

本脚本按附录 C 属**呈现层**：只读 `probes/artifacts/w32_rank_stability.json` 与
`probes/w32_regularization_ladder_summary.json`，不产生任何新读数、不占 shot、
不改任何冻结文件、不引用外部数据。四张图：

A `w32_fig_noise_floor.png`            四通道噪声地板与最小信息预算（重抽波动 vs 子集大小）
B `w32_fig_fidelity_law.png`           s0 与「1 − τ_b」的关系（s0 不是通道常数）
C `w32_fig_milestones.png`             项目里程碑阶梯（冻结读数 vs 读数，含 0.60 门）
D `w32_fig_regularization_curves.png`  两条正则化曲线的逐种子散点与五种子均值
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RANK_JSON = REPOSITORY_ROOT / "probes" / "artifacts" / "w32_rank_stability.json"
LADDER_JSON = REPOSITORY_ROOT / "probes" / "w32_regularization_ladder_summary.json"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"

FIG_NOISE = ARTIFACTS / "w32_fig_noise_floor.png"
FIG_LAW = ARTIFACTS / "w32_fig_fidelity_law.png"
FIG_MILESTONE = ARTIFACTS / "w32_fig_milestones.png"
FIG_CURVES = ARTIFACTS / "w32_fig_regularization_curves.png"

CHANNEL_ORDER = ("dielectric", "viscosity", "orbital", "redox")
CHANNEL_COLOR = {"dielectric": "#1f3b63", "viscosity": "#c0392b",
                 "orbital": "#16a085", "redox": "#8e44ad"}
GATE = 0.60
SD_TARGET = 0.05
NORMAL_QUANTILE = 1.6448536269514722

#: 冻结读数逐字引用（scripts/verify_four_core_registry.py --check 与预注册文件同源）
FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
PINNED_READINGS = (
    (REPOSITORY_ROOT / "probes" / "dielectric_anchor_prereg.json", FROZEN_BASELINE),
    (REPOSITORY_ROOT / "probes" / "dielectric_applicability_domain_prereg.json", FROZEN_HEADLINE),
)


def read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def contains_value(node, target) -> bool:
    if isinstance(node, dict):
        return any(contains_value(value, target) for value in node.values())
    if isinstance(node, list):
        return any(contains_value(value, target) for value in node)
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return False
    return abs(float(node) - float(target)) <= 1e-15


def verify_pins() -> None:
    for path, value in PINNED_READINGS:
        if not contains_value(read_json(path), value):
            raise SystemExit("冻结读数未在 " + str(path) + " 中逐字钉住：" + repr(value))


def empirical_sd(block: dict) -> float:
    return (float(block["p95"]) - float(block["p05"])) / (2.0 * NORMAL_QUANTILE)


def use_chinese_font(plt) -> None:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False


def channel_labels(rank: dict) -> dict:
    return {row["channel"]: row["label"] for row in rank["channels"]}

def figure_noise_floor(rank: dict, plt) -> Path:
    grid = [int(value) for value in rank["n_grid"]]
    channels = {row["channel"]: row for row in rank["channels"]}
    figure, axes = plt.subplots(2, 2, figsize=(13.5, 8.6))
    for axis, channel in zip(axes.ravel(), CHANNEL_ORDER):
        row = channels[channel]
        records = [item for item in rank["records"] if item["channel"] == channel]
        color = CHANNEL_COLOR[channel]
        models = []
        for index, record in enumerate(records):
            model = np.array([float(record["sd_by_n"][str(n)]) for n in grid])
            empirical = np.array([empirical_sd(record["curve_stats"][str(n)]) for n in grid])
            models.append(model)
            axis.plot(grid, model, color=color, alpha=0.30, linewidth=1.0,
                      label="闭式 sd(N)" if index == 0 else None)
            axis.plot(grid, empirical, color=color, alpha=0.75, linewidth=0.0, marker="o",
                      markersize=3.2,
                      label="经验 sigma（p05-p95 反推）" if index == 0 else None)
        axis.plot(grid, np.median(np.vstack(models), axis=0), color="#111111", linewidth=2.0,
                  label="闭式中位（跨序列）")
        axis.axhline(SD_TARGET, color="#e67e22", linestyle="--", linewidth=1.0, label="目标 sd = 0.05")
        axis.axvline(float(row["n_for_sd_0_05"]), color="#7f8c8d", linestyle=":", linewidth=1.0,
                     label="预算 N = " + format(float(row["n_for_sd_0_05"]), ".0f"))
        axis.set_yscale("log")
        axis.set_xlabel("子集大小 N")
        axis.set_ylabel("Kendall tau_b 的重抽波动 sd")
        axis.set_title(row["label"] + "（" + str(int(row["series"])) + " 条序列，N_pop 中位 "
                       + format(float(row["n_population_median"]), ".0f") + "）", fontsize=10)
        axis.grid(alpha=0.25, which="both")
        axis.text(0.03, 0.04,
                  "s0 中位 " + format(float(row["s0_median"]), ".3f")
                  + "・tau_b 中位 " + format(float(row["tau_b_full_median"]), ".3f")
                  + "・闭式拟合 rmse 中位 " + format(float(row["rmse_median"]), ".4f"),
                  transform=axis.transAxes, fontsize=7.5, color="#333333")
        axis.legend(fontsize=7, loc="upper right")
    figure.suptitle("W32-A 四通道噪声地板：闭式 sd(N) = s0·sqrt(1/N − 1/N_pop) 对经验波动，"
                    "以及使 sd ≤ 0.05 的最小信息预算", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(FIG_NOISE, dpi=150)
    plt.close(figure)
    return FIG_NOISE


def figure_fidelity_law(rank: dict, plt) -> Path:
    records = rank["records"]
    labels = channel_labels(rank)
    gap = np.array([1.0 - float(item["tau_b_full"]) for item in records])
    s0 = np.array([float(item["s0"]) for item in records])
    figure, axis = plt.subplots(figsize=(9.8, 6.0))
    for channel in CHANNEL_ORDER:
        mask = np.array([item["channel"] == channel for item in records])
        axis.scatter(gap[mask], s0[mask], s=52, color=CHANNEL_COLOR[channel], alpha=0.85,
                     edgecolor="white", linewidth=0.6, label=labels[channel])
    slope, intercept = np.polyfit(gap, s0, 1)
    xs = np.linspace(float(gap.min()) * 0.97, float(gap.max()) * 1.03, 40)
    axis.plot(xs, slope * xs + intercept, color="#111111", linestyle="--", linewidth=1.2,
              label="最小二乘 " + format(slope, "+.3f") + "·(1 − tau_b) "
                    + format(intercept, "+.3f"))
    for index in np.flatnonzero(s0 <= 1e-12):
        axis.annotate("退化序列：重抽下 tau_b 恒为 0（s0 = 0）",
                      (float(gap[index]), float(s0[index])), textcoords="offset points",
                      xytext=(9, 6), ha="left", fontsize=8, color="#555555")
    law = {item["id"]: item for item in rank["readings"]}["R2"]
    axis.set_xlabel("保真度缺口 1 − tau_b（tau_b = 全量评分下的 Kendall tau_b）")
    axis.set_ylabel("噪声幅度 s0")
    axis.set_title("W32-A 保真度律：s0 不是通道常数，而是排序保真度的函数\n"
                   "Spearman(s0, 1 − tau_b) = " + format(float(law["value"]), ".3f")
                   + "（n = " + str(len(records)) + "，判据 " + str(law["verdict"]) + "）",
                   fontsize=11)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(FIG_LAW, dpi=150)
    plt.close(figure)
    return FIG_LAW


def figure_milestones(ladder: dict, plt) -> Path:
    readings = ladder["readings"]
    milestones = (
        ("冻结基线", FROZEN_BASELINE, "#7f8c8d", "冻结：主记分牌基线，原位保留"),
        ("冻结头条", FROZEN_HEADLINE, "#5d6d7e", "冻结：Morgan+Physical+lever4+lever8"),
        ("单表示 5 种子均值", float(ladder["cross_seed"]["anch_frozen_d2"]), "#c0392b",
         "读数：Physical 13 列；seed 42 = 0.608059"),
        ("W20-4 晋升翼", float(readings["registered_mean"]), "#1f3b63",
         "唯一被晋升的翼"),
        ("W31 固定最优", float(readings["w31_fixed_mean"]), "#95a5a6",
         "读数：落在松弛带内 → 不晋升"),
        ("W32 最佳 ss07", float(readings["global_best_mean"]), "#16a085",
         "读数：对注册臂 " + format(float(readings["ceiling_delta"]), "+.4f") + " → 不晋升"),
    )
    figure, axis = plt.subplots(figsize=(11.6, 5.6))
    positions = list(range(len(milestones)))[::-1]
    for position, (name, value, color, note) in zip(positions, milestones):
        axis.barh(position, value, height=0.60, color=color, alpha=0.9)
        axis.text(value + 0.0022, position, format(value, ".4f"), va="center", fontsize=9)
        axis.text(value + 0.0205, position, note, va="center", fontsize=7.5, color="#555555")
    axis.axvline(GATE, color="#e67e22", linestyle="--", linewidth=1.2, label="门 0.60")
    axis.set_yticks(positions)
    axis.set_yticklabels([item[0] for item in milestones], fontsize=9.5)
    axis.set_xlim(0.39, 0.72)
    axis.set_xlabel("原尺度 R²（后三项为 5 种子均值；冻结头条是混合表示的单读数，不同口径不混比）")
    axis.set_title("项目里程碑阶梯：冻结读数 vs 读数（过门 ≠ 晋升）", fontsize=11)
    axis.grid(alpha=0.25, axis="x")
    axis.legend(fontsize=8, loc="lower right")
    figure.tight_layout()
    figure.savefig(FIG_MILESTONE, dpi=150)
    plt.close(figure)
    return FIG_MILESTONE


def figure_regularization_curves(ladder: dict, plt) -> Path:
    readings = ladder["readings"]
    per_seed = ladder["per_seed"]
    labels = [item["label"] for item in ladder["configs"]]
    registered = float(readings["registered_mean"])
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.4))
    plans = (
        (axes[0], {"0.8": labels[1], "0.9": labels[3], "1.0": labels[4]},
         readings["colsample_curve"],
         "A 列采样：0.8 → 0.9 → 1.0 严格单调下降，0.8 是端点最优"),
        (axes[1], {"0.6": labels[5], "0.7": labels[6], "0.8": labels[1],
                   "0.9": labels[7], "1.0": labels[8]},
         readings["subsample_curve"],
         "B 行采样：0.7 最高（" + format(float(readings["subsample_best_mean"]), ".6f") + "）"),
    )
    for axis, mapping, curve, title in plans:
        xs = sorted(float(key) for key in curve)
        means = [float(curve[str(key)]) for key in xs]
        for index, key in enumerate(xs):
            arm = mapping[str(key)]
            values = [float(per_seed[seed][arm]) for seed in per_seed]
            is_anchor = float(key) == 0.8
            jitter = np.linspace(-0.010, 0.010, len(values))
            axis.scatter(np.full(len(values), float(key)) + jitter, values, s=26,
                         color="#7f8c8d" if is_anchor else "#34495e", alpha=0.65,
                         label=("逐种子（灰 = 复现锚 0.8）" if index == 0 else None))
        axis.plot(xs, means, color="#1f3b63", marker="o", linewidth=1.7, markersize=5.0,
                  label="五种子均值")
        axis.axhline(GATE, color="#e67e22", linestyle="--", linewidth=1.1, label="门 0.60")
        axis.axhline(registered, color="#c0392b", linestyle=":", linewidth=1.1,
                     label="W20-4 注册臂 " + format(registered, ".6f"))
        best = max(range(len(means)), key=lambda position: means[position])
        axis.annotate(format(means[best], ".6f"), (xs[best], means[best]),
                      textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8.5,
                      color="#16a085")
        axis.set_xlabel("正则化旋钮取值（0.8 = 冻结值）")
        axis.set_ylabel("原尺度 R²")
        axis.set_title(title, fontsize=10.5)
        axis.grid(alpha=0.25)
        axis.legend(fontsize=7.5, loc="lower left")
    figure.suptitle("W32-B 第 19 枪：两条正则化曲线（九档固定配置，零选择器）", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(FIG_CURVES, dpi=150)
    plt.close(figure)
    return FIG_CURVES


def main() -> int:
    verify_pins()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    use_chinese_font(plt)
    rank = read_json(RANK_JSON)
    ladder = read_json(LADDER_JSON)
    written = (
        figure_noise_floor(rank, plt),
        figure_fidelity_law(rank, plt),
        figure_milestones(ladder, plt),
        figure_regularization_curves(ladder, plt),
    )
    for path in written:
        print("wrote " + str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
              + " " + format(path.stat().st_size, "d") + " B")
    print("sequences " + str(len(rank["records"])) + " | arms " + str(len(ladder["configs"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())