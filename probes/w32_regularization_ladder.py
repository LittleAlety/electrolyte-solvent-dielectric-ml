# -*- coding: utf-8 -*-
"""W32-B -- 稠密块的第三个容量面：正则化中间值阶梯（第 19 枪）。

W29/W30/W31 把容量这件事拆成了深度、叶惩罚、分箱三个面，并证到「深度与叶惩罚
正交、不可互换」。剩下唯一从没被扫过的面是**正则化**：`colsample_bytree` 只测过
冻结的 0.8 与放开的 1.0（两处读数都掉 0.039 ~ 0.048），而 `subsample` 自冻结以来
**从未动过**（一直是 0.8）。W29+W30 的结论是「正则化在扛事」——到底是缺还是多，
只有中间值能回答。

本枪因此把 W20-4 注册臂（深度 4 / mcw 5 / bin 128）当作固定底座，只沿两条正则化
轴各扫一条曲线：`colsample_bytree` ∈ {0.8, 0.9, 1.0}、`subsample` ∈ {0.6, 0.7,
0.8, 0.9, 1.0}。九个固定配置在同样的折上各拟合一次，零选择器。

实现上直接复用 W31 已经过四条复现锚验证的拟合路径（`w31_capacity_exchange`），
只替换其模块级 `CONFIGS` 与 `ARM_PREFIX`，不复制任何一行拟合代码。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import dielectric_pool_expansion_benchmark as bn
import dielectric_representation_seed_robustness as sr
import numpy as np
import w28_dense_hyperparameters as w28
import w31_capacity_exchange as ladder
from dielectric_representation_ablation import SEED as FIT_SEED
from export_results_common import write_json_stable

from electrolyte_ml.pathing import portable_relative_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w32_regularization_ladder_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w32_regularization_ladder_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w32_regularization_ladder.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_CSV = ARTIFACTS_DIR / "w32_regularization_ladder_repeats.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w32_regularization_ladder.png"

SCHEMA = "w32_regularization_ladder/summary@1"
TASK = "week32_regularization_ladder"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED = 0.5861142332208197
W20_4_REGISTERED = 0.6216672295270079
W31_FIXED_BEST = 0.6223892738254433
GATE_R2 = 0.60

REPRODUCTION_TOLERANCE = 1e-09
CROSS_CHECK_TOLERANCE = 1e-06
CEILING_SLACK = 0.005
MIDPOINT_MIN_GAIN = 0.002
ORDER_INVARIANCE_AUC_RANGE = 0.02
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_SHOTS_THIS_WEEK = 1
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 19

BASE = {"max_depth": 4, "n_estimators": 200, "learning_rate": 0.05, "min_child_weight": 5,
        "colsample_bytree": 0.8, "subsample": 0.8, "max_bin": 128, "reg_lambda": 1.0}


def _cfg(**overrides):
    return {**BASE, **overrides}


CONFIGS = (
    ("anch_frozen_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                        "min_child_weight": 1, "colsample_bytree": 0.8, "subsample": 0.8,
                        "max_bin": 64, "reg_lambda": 1.0}),
    ("anch_w20_4_registered_d4_mcw5", _cfg()),
    ("anch_w31_fixed_bin128_mcw7_d4", _cfg(min_child_weight=7)),
    ("cs09_d4_mcw5_bin128", _cfg(colsample_bytree=0.9)),
    ("cs10_d4_mcw5_bin128", _cfg(colsample_bytree=1.0)),
    ("ss06_d4_mcw5_bin128", _cfg(subsample=0.6)),
    ("ss07_d4_mcw5_bin128", _cfg(subsample=0.7)),
    ("ss09_d4_mcw5_bin128", _cfg(subsample=0.9)),
    ("ss10_d4_mcw5_bin128", _cfg(subsample=1.0)),
)
FROZEN_INDEX = 0
REGISTERED_INDEX = 1
W31_FIXED_INDEX = 2
NEW_INDICES = (3, 4, 5, 6, 7, 8)
CS_INDICES = {0.8: REGISTERED_INDEX, 0.9: 3, 1.0: 4}
SS_INDICES = {0.6: 5, 0.7: 6, 0.8: REGISTERED_INDEX, 0.9: 7, 1.0: 8}
LADDER_COLUMNS = ("max_depth", "n_estimators", "learning_rate", "min_child_weight",
                  "colsample_bytree", "subsample", "max_bin", "reg_lambda")
METRIC_COLUMNS = w28.METRIC_COLUMNS
REPEAT_COLUMNS = ("seed", "arm", "repeat", *METRIC_COLUMNS)

#: 复用 W31 的拟合路径：只替换模块级的配置表与臂前缀。
ladder.CONFIGS = CONFIGS
ladder.ARM_PREFIX = "regularization_"

CLAIM = ("把 W20-4 注册臂当固定底座，沿两条从未扫过的正则化轴各扫一条曲线"
         "（colsample_bytree 0.8/0.9/1.0、subsample 0.6/0.7/0.8/0.9/1.0），"
         "检验『正则化在扛事』到底是缺还是多，并复核容量天花板是否仍停在 W20-4 注册臂")

def collect(seeds, jobs: int, stage: str):
    context = sr.build_context()
    groups = [str(item) for item in context["groups"]]
    target = np.asarray(context["target"], dtype=float)
    features = np.asarray(context["physical_lever4"], dtype=float)
    print("pool: " + str(len(groups)) + " rows | physical block " + str(features.shape), flush=True)

    cache: dict[int, dict] = {}
    spreadsheet: list[dict] = []
    leakage: dict[str, dict] = {}
    for seed in seeds:
        splits = w28.splits_for_seed(int(seed), context)
        if int(seed) == ANCHOR_SEED:
            if bn.fold_signature(splits) != bn.fold_signature(context["frozen_splits"]):
                raise SystemExit("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
        if stage == "smoke":
            splits = [item for item in splits if int(item[0]) == 0]
        result = ladder.evaluate_ladder(features, splits, groups, target, int(seed), jobs)
        cache[int(seed)] = result
        spreadsheet.extend(dict(row) for row in result["repeat_rows"])
        leakage[str(int(seed))] = dict(result["leak"])
        labels = [ladder.config_label(index) for index in range(len(CONFIGS))]
        print("  seed " + str(int(seed)) + " | "
              + "  ".join(label + " " + format(float(result["per_config"][label]["r2_mean"]), ".6f")
                          for label in labels)
              + "  (" + format(float(result["seconds"]), ".1f") + "s)", flush=True)
    return cache, spreadsheet, leakage


def build_payload(cache, spreadsheet, leakage, seeds, prereg, elapsed, stage) -> dict:
    labels = [ladder.config_label(index) for index in range(len(CONFIGS))]
    keys = ("r2_mean", "r2_min", "r2_max", "spearman_mean", "auc_gt15_mean", "auc_gt30_mean",
            "mae_mean", "repeats")
    cross_seed = {label: float(np.mean([float(cache[int(seed)]["per_config"][label]["r2_mean"])
                                        for seed in seeds])) for label in labels}
    per_seed = {str(int(seed)): {label: float(cache[int(seed)]["per_config"][label]["r2_mean"])
                                 for label in labels} for seed in seeds}
    per_config = {label: {key: float(np.mean([float(cache[int(seed)]["per_config"][label][key])
                                              for seed in seeds])) for key in keys}
                  for label in labels}

    frozen_label = labels[FROZEN_INDEX]
    registered_label = labels[REGISTERED_INDEX]
    anchor_seed42 = per_seed[str(ANCHOR_SEED)][frozen_label]

    cs_curve = {str(settings): cross_seed[labels[index]] for settings, index in CS_INDICES.items()}
    ss_curve = {str(settings): cross_seed[labels[index]] for settings, index in SS_INDICES.items()}
    cs_gap_09 = cs_curve["0.9"] - cs_curve["0.8"]
    cs_gap_10 = cs_curve["1.0"] - cs_curve["0.9"]
    ss_best = max(((settings, index) for settings, index in SS_INDICES.items() if index in NEW_INDICES),
                  key=lambda item: cross_seed[labels[item[1]]])
    ss_best_label = labels[ss_best[1]]
    ss_best_mean = cross_seed[ss_best_label]
    ss_best_gain = ss_best_mean - cross_seed[registered_label]

    best_new_label, best_new_mean = None, float("nan")
    for index in NEW_INDICES:
        label = labels[index]
        if np.isfinite(cross_seed[label]) and (best_new_label is None or cross_seed[label] > best_new_mean):
            best_new_label, best_new_mean = label, cross_seed[label]
    global_best_label, global_best_mean = None, float("nan")
    for label in labels:
        if np.isfinite(cross_seed[label]) and (global_best_label is None
                                               or cross_seed[label] > global_best_mean):
            global_best_label, global_best_mean = label, cross_seed[label]

    all_r2 = [cross_seed[label] for label in labels]
    all_auc30 = [per_config[label]["auc_gt30_mean"] for label in labels]
    r2_range = float(max(all_r2) - min(all_r2))
    auc30_range = float(max(all_auc30) - min(all_auc30))
    ratio = r2_range / auc30_range if auc30_range else float("inf")
    leak_folds = int(sum(int(block["folds_with_a_straddling_compound"]) for block in leakage.values()))

    readings = {
        "anchor_seed42": anchor_seed42,
        "anchor_seed42_gap": ladder.gap(anchor_seed42, FROZEN_SINGLE_REPRESENTATION),
        "frozen_label": frozen_label,
        "frozen_mean": cross_seed[frozen_label],
        "frozen_expected": FROZEN_CROSS_SEED,
        "frozen_gap": ladder.gap(cross_seed[frozen_label], FROZEN_CROSS_SEED),
        "registered_label": registered_label,
        "registered_mean": cross_seed[registered_label],
        "registered_expected": W20_4_REGISTERED,
        "registered_gap": ladder.gap(cross_seed[registered_label], W20_4_REGISTERED),
        "w31_fixed_label": labels[W31_FIXED_INDEX],
        "w31_fixed_mean": cross_seed[labels[W31_FIXED_INDEX]],
        "w31_fixed_expected": W31_FIXED_BEST,
        "w31_fixed_gap": ladder.gap(cross_seed[labels[W31_FIXED_INDEX]], W31_FIXED_BEST),
        "colsample_curve": cs_curve,
        "colsample_gap_09": cs_gap_09,
        "colsample_gap_10": cs_gap_10,
        "subsample_curve": ss_curve,
        "subsample_best_label": ss_best_label,
        "subsample_best_mean": ss_best_mean,
        "subsample_best_gain_vs_registered": ss_best_gain,
        "best_new_label": best_new_label,
        "best_new_mean": best_new_mean,
        "global_best_label": global_best_label,
        "global_best_mean": global_best_mean,
        "ceiling_delta": (global_best_mean - W20_4_REGISTERED
                          if np.isfinite(global_best_mean) else float("nan")),
        "r2_range": r2_range,
        "auc_gt30_range": auc30_range,
        "range_ratio": ratio,
        "leak_folds": leak_folds,
    }

    verdicts = [
        ladder.build_verdict("H32a", "复现锚：seed 42 的冻结档位逐位复现冻结值",
                             readings["anchor_seed42_gap"], 0.0,
                             abs(readings["anchor_seed42_gap"]) <= REPRODUCTION_TOLERANCE),
        ladder.build_verdict("H32b", "交叉验证：冻结档位的五种子端点复现 0.5861142332208197",
                             readings["frozen_gap"], CROSS_CHECK_TOLERANCE,
                             abs(readings["frozen_gap"]) <= CROSS_CHECK_TOLERANCE),
        ladder.build_verdict("H32c", "交叉验证：W20-4 注册臂复现 0.6216672295270079",
                             readings["registered_gap"], CROSS_CHECK_TOLERANCE,
                             abs(readings["registered_gap"]) <= CROSS_CHECK_TOLERANCE),
        ladder.build_verdict("H32d", "交叉验证：W31 固定最优配置复现 0.6223892738254433",
                             readings["w31_fixed_gap"], CROSS_CHECK_TOLERANCE,
                             abs(readings["w31_fixed_gap"]) <= CROSS_CHECK_TOLERANCE),
        ladder.build_verdict("H32e", "跨折泄漏：含跨界化合物的折数", float(leak_folds), 0.0,
                             leak_folds == 0),
        ladder.build_verdict("H32f", "列采样单调下降：colsample 0.8 -> 0.9 的增量",
                             readings["colsample_gap_09"], 0.0,
                             readings["colsample_gap_09"] < 0.0
                             and readings["colsample_gap_10"] < 0.0),
        ladder.build_verdict("H32g", "行采样存在中间最优点：subsample != 0.8 的最佳档对注册臂的增量",
                             readings["subsample_best_gain_vs_registered"], MIDPOINT_MIN_GAIN,
                             readings["subsample_best_gain_vs_registered"] > MIDPOINT_MIN_GAIN),
        ladder.build_verdict("H32h", "容量天花板未被打破：最高档位与 W20-4 注册臂之差",
                             readings["ceiling_delta"], CEILING_SLACK,
                             readings["ceiling_delta"] <= CEILING_SLACK),
        ladder.build_verdict("H32i", "序不变量（比值判据：R2 极差 / AUC30 极差 "
                             + ladder.fmt(ratio, 2) + "，且 AUC30 极差 < 0.02）",
                             readings["auc_gt30_range"], ORDER_INVARIANCE_AUC_RANGE,
                             readings["auc_gt30_range"] < ORDER_INVARIANCE_AUC_RANGE
                             and ratio > 1.0),
        ladder.build_verdict("H32j", "过门：最佳档位的五种子均值 >= 0.60",
                             readings["best_new_mean"], GATE_R2,
                             np.isfinite(best_new_mean) and float(best_new_mean) >= GATE_R2),
    ]

    return {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": ladder.utc_now(),
        "elapsed_seconds": float(elapsed),
        "stage": stage,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": ladder.sha256_file(PREREG_PATH),
            "status": str(prereg.get("status")),
            "revision": int(prereg.get("revision", 1)),
            "thresholds_moved": bool(prereg.get("revision_note", {}).get("thresholds_moved", False)),
        },
        "claim": CLAIM,
        "pool": {"scoreboard_rows": SCOREBOARD_ROWS, "scoreboard_compounds": SCOREBOARD_COMPOUNDS,
                 "training_mask": "full_base"},
        "configs": [{"index": index, "label": label, "overrides": dict(overrides)}
                    for index, (label, overrides) in enumerate(CONFIGS)],
        "new_combination_indices": list(NEW_INDICES),
        "frozen_params": {key: CONFIGS[FROZEN_INDEX][1][key] for key in LADDER_COLUMNS},
        "frozen_index": FROZEN_INDEX,
        "fit_seed": int(FIT_SEED),
        "seeds": [int(seed) for seed in seeds],
        "per_seed": per_seed,
        "cross_seed": cross_seed,
        "per_config": per_config,
        "readings": readings,
        "leakage": leakage,
        "verdicts": verdicts,
        "notes": [
            "本枪是阶梯不是搜索：固定配置、零选择器，因此不设安慰剂臂。",
            "拟合路径直接复用 W31 的 evaluate_ladder（四条复现锚已在 W31 逐位命中），本枪只替换配置表与臂前缀。",
            "单表示（Physical 13 列）读数永不与冻结头条 0.4766400383507876 混比。",
            "H32i 采用 W31 教训后的**比值判据**（R2 极差 / AUC30 极差），不再拿绝对门去卡窄阶梯。",
        ],
        "artifacts": {
            "repeats_csv": portable_relative_path(REPEATS_CSV, root=REPOSITORY_ROOT),
            "figure": portable_relative_path(FIGURE_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        },
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
    }

def format_report(payload: dict) -> str:
    fmt = ladder.fmt
    lines: list[str] = []
    lines.append("# W32 结题报告：稠密块的第三个容量面 —— 正则化中间值阶梯")
    lines.append("")
    lines.append("- 预注册 `probes/w32_regularization_ladder_prereg.json`（status = locked_before_run，revision 1）")
    lines.append("- 池：冻结主记分牌池，评分 457 行 / 97 化合物；训练掩码 full_base；表示 physical_lever4（13 列稠密块）")
    lines.append("- 主记分牌 shot：1（累计 19）")
    lines.append("")
    lines.append("## 1. 裁决表")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for verdict in payload["verdicts"]:
        lines.append("| " + verdict["description"] + " | " + fmt(verdict["value"], 6) + " | "
                     + fmt(verdict["threshold"], 6) + " | " + verdict["verdict"] + " |")
    lines.append("")
    failed = [v for v in payload["verdicts"] if v["verdict"] == "判否"]
    lines.append("## 2. 判否登记（" + str(len(failed)) + " 条）")
    lines.append("")
    if not failed:
        lines.append("- 本轮没有判否。")
    for verdict in failed:
        note = ladder.VERDICT_NOTES.get(verdict["id"], "**实质判否**：读数 " + fmt(verdict["value"], 6)
                                        + " 对阈值 " + fmt(verdict["threshold"], 6) + "。")
        lines.append("- **" + verdict["id"] + "**：" + verdict["description"] + "（读数 "
                     + fmt(verdict["value"], 6) + " 对阈值 " + fmt(verdict["threshold"], 6)
                     + "）。" + note)
    lines.append("")
    readings = payload["readings"]
    lines.append("## 3. 九个固定配置（五种子均值）")
    lines.append("")
    lines.append("| 档位 | 只列与底座的差异 | 五种子均值 | 对冻结档位 | 对注册臂 |")
    lines.append("| --- | --- | --- | --- | --- |")
    labels = [ladder.config_label(index) for index in range(len(CONFIGS))]
    base_keys = ("max_depth", "n_estimators", "learning_rate", "min_child_weight",
                 "colsample_bytree", "subsample", "max_bin", "reg_lambda")
    for index, label in enumerate(labels):
        overrides = CONFIGS[index][1]
        diff = ", ".join(key + " " + str(overrides[key]) for key in base_keys
                         if overrides[key] != CONFIGS[REGISTERED_INDEX][1][key])
        lines.append("| " + ("**" + label + "**" if index in NEW_INDICES else label)
                     + " | " + (diff if diff else "——")
                     + " | " + fmt(payload["cross_seed"][label], 6)
                     + " | " + ladder.fmt_signed(payload["cross_seed"][label]
                                                 - payload["cross_seed"][labels[FROZEN_INDEX]], 6)
                     + " | " + ladder.fmt_signed(payload["cross_seed"][label]
                                                 - readings["registered_mean"], 6) + " |")
    lines.append("")
    lines.append("## 4. 两条正则化曲线")
    lines.append("")
    lines.append("**列采样 `colsample_bytree`（底座 = 注册臂，其余全冻）**")
    lines.append("")
    lines.append("| colsample_bytree | 五种子均值 | 相对 0.8 的增量 |")
    lines.append("| --- | --- | --- |")
    for settings in ("0.8", "0.9", "1.0"):
        value = readings["colsample_curve"][settings]
        lines.append("| " + settings + " | " + fmt(value, 6) + " | "
                     + ladder.fmt_signed(value - readings["colsample_curve"]["0.8"], 6) + " |")
    lines.append("")
    lines.append("**行采样 `subsample`（底座 = 注册臂，其余全冻）**")
    lines.append("")
    lines.append("| subsample | 五种子均值 | 相对 0.8 的增量 |")
    lines.append("| --- | --- | --- |")
    for settings in ("0.6", "0.7", "0.8", "0.9", "1.0"):
        value = readings["subsample_curve"][settings]
        lines.append("| " + settings + " | " + fmt(value, 6) + " | "
                     + ladder.fmt_signed(value - readings["subsample_curve"]["0.8"], 6) + " |")
    lines.append("")
    lines.append("- 本轮唯一的新知识落在这两条曲线上；其余八个档位都是复现锚或对照。")
    lines.append("")
    lines.append("## 5. 逐种子读数")
    lines.append("")
    lines.append("| 种子 | " + " | ".join(labels) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in labels) + " |")
    for seed in payload["seeds"]:
        row = payload["per_seed"][str(seed)]
        lines.append("| " + str(seed) + " | " + " | ".join(fmt(row[label], 6) for label in labels) + " |")
    lines.append("| 五种子均值 | " + " | ".join(fmt(payload["cross_seed"][label], 6)
                                              for label in labels) + " |")
    lines.append("")
    lines.append("## 6. 量级对序")
    lines.append("")
    lines.append("| 档位 | R2 | Spearman | AUC(eps>15) | AUC(eps>30) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for label in labels:
        row = payload["per_config"][label]
        lines.append("| " + label + " | " + fmt(row["r2_mean"], 6) + " | "
                     + fmt(row["spearman_mean"], 6) + " | " + fmt(row["auc_gt15_mean"], 6)
                     + " | " + fmt(row["auc_gt30_mean"], 6) + " |")
    lines.append("")
    lines.append("档位间极差：R² " + fmt(readings["r2_range"], 6) + "，AUC(ε>30) "
                 + fmt(readings["auc_gt30_range"], 6) + "，比值 " + fmt(readings["range_ratio"], 2)
                 + "。")
    lines.append("")
    lines.append("## 7. 口径与边界")
    lines.append("")
    lines.append("- 池、评分掩码、训练掩码、分组切分器与五种子集合逐字复用冻结主记分牌；`random_state` 固定为 42。")
    lines.append("- 这是阶梯不是搜索：九个固定配置在同样的折上各拟合一次，没有任何选择，外层测试行只被预测、从未参与任何决定。")
    lines.append("- 档位 0 / 1 / 2 是复现锚（冻结档位、W20-4 注册臂、W31 固定最优配置），用来确认代码路径与前三周字节一致。")
    lines.append("- 单表示（Physical 13 列）读数永不与冻结头条 `0.4766400383507876` 混比；W27 的「Physical 单表示不单独构成晋升路径」声明不因本枪改变。")
    lines.append("- 本枪不新增量子化学、不装依赖、不联网；全部由盘上已有产物派生。")
    lines.append("- 主记分牌 shot = 1（累计 19）；四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。")
    lines.append("")
    return "\n".join(lines)

def render_figure(payload: dict) -> bool:
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

        labels = [ladder.config_label(index) for index in range(len(CONFIGS))]
        values = [payload["cross_seed"][label] for label in labels]
        colors = ["#7f8c8d" if index not in NEW_INDICES else "#1f3b63"
                  for index in range(len(CONFIGS))]

        figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))
        positions = np.arange(len(labels))
        axes[0].bar(positions, values, color=colors)
        axes[0].axhline(GATE_R2, color="#16a085", linestyle="--", linewidth=1.0, label="门 0.60")
        axes[0].axhline(payload["readings"]["registered_mean"], color="#c0392b", linestyle=":",
                        linewidth=1.0, label="W20-4 注册臂")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels([label.replace("_", "\n", 1) for label in labels], fontsize=6)
        axes[0].set_ylim(0.54, max(values) + 0.012)
        axes[0].set_ylabel("五种子均值 R²")
        axes[0].set_title("A 九个固定配置（灰 = 复现锚，蓝 = 新档位）")
        axes[0].legend(fontsize=7)
        axes[0].grid(alpha=0.25, axis="y")

        for curve, color, marker, name in (
                (payload["readings"]["colsample_curve"], "#1f3b63", "o", "colsample_bytree"),
                (payload["readings"]["subsample_curve"], "#c0392b", "s", "subsample")):
            xs = sorted(float(key) for key in curve)
            axes[1].plot(xs, [curve[str(key)] for key in xs], marker=marker, color=color,
                         linewidth=1.3, label=name)
        axes[1].axhline(payload["readings"]["registered_mean"], color="#7f8c8d", linestyle=":",
                        linewidth=1.0)
        axes[1].set_xlabel("正则化旋钮取值（0.8 = 冻结值）")
        axes[1].set_ylabel("五种子均值 R²")
        axes[1].set_title("B 两条正则化曲线：底座 = W20-4 注册臂")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W32 稠密块的正则化中间值阶梯（第 19 枪，零选择器）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover
        print("figure failure: " + type(error).__name__ + ": " + str(error))
        return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--stage", choices=("smoke", "full"), default="full")
    parser.add_argument("--seeds", type=str, default=",".join(str(seed) for seed in SEEDS))
    parser.add_argument("--render-only", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    jobs = max(1, int(args.jobs))
    stage = str(args.stage)
    seeds = tuple(int(part) for part in str(args.seeds).split(",") if part.strip())

    if bool(args.render_only):
        payload = ladder.read_json(SUMMARY_PATH)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(format_report(payload))
        print("figure " + ("ok" if render_figure(payload) else "skipped"))
        return 0

    prereg: dict = {}
    if PREREG_PATH.is_file():
        prereg = ladder.read_json(PREREG_PATH)
    if stage == "full":
        if not prereg:
            print("MISSING " + str(PREREG_PATH))
            return 1
        if str(prereg.get("status")) != "locked_before_run":
            print("the pre-registration is not locked_before_run")
            return 1

    cache, spreadsheet, leakage = collect(seeds, jobs, stage)
    if stage == "smoke":
        print("stage smoke finished in " + format(time.perf_counter() - started, ".1f")
              + "s; no artifact written", flush=True)
        return 0

    payload = build_payload(cache, spreadsheet, leakage, seeds, prereg,
                            time.perf_counter() - started, stage)
    ladder.write_csv(REPEATS_CSV, REPEAT_COLUMNS,
                     [[row[column] for column in REPEAT_COLUMNS] for row in spreadsheet])
    write_json_stable(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(format_report(payload))
    figure_ok = render_figure(payload)
    readings = payload["readings"]
    print("colsample " + str(readings["colsample_curve"]) + " | subsample "
          + str(readings["subsample_curve"]), flush=True)
    print("best new: " + str(readings["best_new_label"]) + " "
          + ladder.fmt(readings["best_new_mean"], 6)
          + " | ceiling delta " + ladder.fmt_signed(readings["ceiling_delta"], 6), flush=True)
    print("wrote " + portable_relative_path(REPEATS_CSV, root=REPOSITORY_ROOT), flush=True)
    print("wrote " + portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT), flush=True)
    print("wrote " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(sum(1 for verdict in payload["verdicts"] if verdict["verdict"] == "成立"))
          + "/" + str(len(payload["verdicts"])), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())