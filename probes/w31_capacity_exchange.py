"""W31 -- capacity-exchange ladder on the dense lever-4 block.

W31-A moved the parent paper's third conclusion ("several expensive layers are
skippable in the ranking sense") to the ML side: within this repository the
largest such reading is that raising max_depth from 2 to 4 buys only
+0.0045840097020970.  Every existing reading, however, stops at
min_child_weight in {1, 5}; the leaf penalty is the other capacity knob and the
substitutability of the two has never been measured.

This probe therefore asks one question and nothing else: can the depth margin be
bought back with a larger leaf penalty?  Three reproduction anchors confirm the
code path byte for byte against Weeks 20 and 30 and against the frozen
configuration, then three new combination points sweep min_child_weight to 7 and
10 at depth 2 and add depth 4 at min_child_weight 7 as the interaction point.

Run:
    .venv/Scripts/python.exe probes/w31_capacity_exchange.py --jobs 12
    .venv/Scripts/python.exe probes/w31_capacity_exchange.py --stage smoke --jobs 8
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import dielectric_pool_expansion_benchmark as bn
import dielectric_representation_seed_robustness as sr
import numpy as np
import w28_dense_hyperparameters as w28
from dielectric_representation_ablation import SEED as FIT_SEED
from dielectric_representation_ablation import XGB_PARAMS, evaluate_repeat
from export_results_common import write_json_stable
from xgboost import XGBRegressor

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w31_capacity_exchange_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w31_capacity_exchange_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w31_capacity_exchange.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_CSV = ARTIFACTS_DIR / "w31_capacity_exchange_repeats.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w31_capacity_exchange.png"

SCHEMA = "w31_capacity_exchange/summary@1"
TASK = "week31_capacity_exchange"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED = 0.5861142332208197
W20_4_REGISTERED = 0.6216672295270079
W30_BEST_D2_MCW5 = 0.6170832198249109
REPRODUCTION_TOLERANCE = 1e-09
CROSS_CHECK_TOLERANCE = 1e-06
CAPACITY_EXCHANGE_MIN_GAIN = 0.002
ORDER_INVARIANCE_AUC_RANGE = 0.02
ORDER_INVARIANCE_R2_RANGE = 0.08
GATE_R2 = 0.60
CEILING_SLACK = 0.005
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_SHOTS_THIS_WEEK = 1
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 18

CONFIGS = (
    ("anch_frozen_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                        "min_child_weight": 1, "colsample_bytree": 0.8, "max_bin": 64,
                        "reg_lambda": 1.0}),
    ("anch_w20_4_registered_d4_mcw5", {"max_depth": 4, "n_estimators": 200,
                                       "learning_rate": 0.05, "min_child_weight": 5,
                                       "colsample_bytree": 0.8, "max_bin": 128,
                                       "reg_lambda": 1.0}),
    ("anch_w30_best_d2_mcw5", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                               "min_child_weight": 5, "colsample_bytree": 0.8, "max_bin": 128,
                               "reg_lambda": 1.0}),
    ("bin128_mcw7_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                        "min_child_weight": 7, "colsample_bytree": 0.8, "max_bin": 128,
                        "reg_lambda": 1.0}),
    ("bin128_mcw10_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                         "min_child_weight": 10, "colsample_bytree": 0.8, "max_bin": 128,
                         "reg_lambda": 1.0}),
    ("bin128_mcw7_d4", {"max_depth": 4, "n_estimators": 200, "learning_rate": 0.05,
                        "min_child_weight": 7, "colsample_bytree": 0.8, "max_bin": 128,
                        "reg_lambda": 1.0}),
)
FROZEN_INDEX = 0
W20_INDEX = 1
W30_INDEX = 2
MCW5_D2_INDEX = 2
MCW7_D2_INDEX = 3
MCW10_D2_INDEX = 4
MCW7_D4_INDEX = 5
NEW_INDICES = (3, 4, 5)
ARM_PREFIX = "capacity_"
LADDER_COLUMNS = ("max_depth", "n_estimators", "learning_rate", "min_child_weight",
                  "colsample_bytree", "max_bin", "reg_lambda")
METRIC_COLUMNS = w28.METRIC_COLUMNS
REPEAT_COLUMNS = ("seed", "arm", "repeat", *METRIC_COLUMNS)

VERDICT_NOTES = {
    "H31f": ("**实质判否**：叶惩罚曲线在 mcw = 5 之后**饱和** —— 1 → 5 一次性给 +0.0139157655253265，"
             "5 → 7 只给 +0.0006648，7 → 10 只给 +0.0002680（三档合计 +0.000932 对预注册门 +0.002）。"
             "因此『深度那 +0.0046 能否用叶惩罚换回来』的答案是**不能**：换回来的是 mcw 1 → 5 那一级，"
             "而那一级 W20-4 早已付过。"),
    "H31g": ("**实质判否**：预测是『深度边际在更高叶惩罚下收缩』，实测是不收缩 —— "
             "depth_margin(mcw5) = +0.004584 对 depth_margin(mcw7) = +0.004641，差 -0.000057（约为前者的 1.2%）。"
             "结合 W30 已知的『mcw 边际近似配置无关』（+0.0120 ~ +0.0139 跨三处配置），"
             "结论是**两个容量旋钮正交、不可互换**，而不是可替代。"),
    "H31h": ("**判据设计缺陷（不是实质判否）**：序侧成立 —— AUC(ε>30) 档位间极差 0.008681 < 0.02；"
             "量级侧不成立，但原因是**本轮阶梯按设计就窄**：R² 极差 0.036275 < 0.08，"
             "而 0.08 那个门是从 W28/W29/W30 三条更宽阶梯（0.0989 ~ 0.1525）抄来的。"
             "本判据在跑前冻结，**不改阈值**；下一份预注册应把它改成比值判据"
             "（`R2 极差 / AUC30 极差` 且 AUC30 极差 < 0.02）。本轮比值 4.2，方向与更宽阶梯一致（8.1 ~ 21.0），"
             "只是幅度随阶梯变窄而变小。"),
    "H31i": ("**名义越过、但未打破天花板**：`bin128_mcw7_d4` = 0.622389 比 W20-4 注册臂高 **+0.000722**，"
             "这是首次有档位在名义上更高；但幅度远小于该配置的种子间抖动（W28/W30 报 sd 约 0.0175），"
             "且落在预注册的 0.005 松弛带内，因此**不构成新纪录、不改冻结读数、不构成晋升**。"),
}
CLAIM = ("在稠密 13 列物理块上把叶惩罚从 5 提到 7 / 10（深度 2），检验深度 2 -> 4 那 +0.0046 "
         "的边际能否用叶惩罚换回来，并检验『深度边际在更高叶惩罚下收缩』这一预测；"
         "同时复核容量天花板是否仍停在 W20-4 注册臂")

def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def dump_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def config_label(index: int) -> str:
    return str(CONFIGS[index][0])


def params_for(index: int) -> dict:
    overrides = dict(CONFIGS[index][1])
    return {**XGB_PARAMS, **overrides, "random_state": FIT_SEED}


def mean_of(rows, key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return float(np.mean(values)) if values else float("nan")


_STATE: dict[str, object] = {}


def _init_worker(features, target) -> None:
    _STATE["features"] = features
    _STATE["target"] = target


def _fit_predict(features, target, train, test, params) -> np.ndarray:
    model = XGBRegressor(**params)
    model.fit(features[train], target[train])
    return np.maximum(model.predict(features[test]), 1.0)


def _ladder_task(task):
    repeat, fold, train_index, test_index = task
    features = _STATE["features"]
    target = _STATE["target"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    predictions: dict[str, list[float]] = {}
    for index in range(len(CONFIGS)):
        prediction = _fit_predict(features, target, train, test, params_for(index))
        predictions[config_label(index)] = [float(value) for value in prediction]
    return (int(repeat), int(fold), [int(index) for index in train],
            [int(index) for index in test], predictions)


def parallel_map(function, tasks, jobs: int, *, initargs=()) -> list:
    if jobs <= 1 or len(tasks) <= 1:
        _init_worker(*initargs)
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker,
                             initargs=initargs) as pool:
        return list(pool.map(function, tasks))


def evaluate_ladder(features, splits, groups, target, seed, jobs) -> dict[str, object]:
    tasks = [(repeat, fold, [int(index) for index in train], [int(index) for index in test])
             for repeat, fold, train, test in splits]
    clock = time.perf_counter()
    raw = parallel_map(_ladder_task, tasks, jobs, initargs=(features, target))
    seconds = time.perf_counter() - clock
    labels = [config_label(index) for index in range(len(CONFIGS))]
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    group_array = np.asarray(groups)
    for repeat, fold, train_index, test_index, predictions in raw:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(group_array[train], group_array[test]).size))
        for label in labels:
            bucket = buckets.setdefault((label, int(repeat)), {"target": [], "prediction": []})
            bucket["target"].append(target[test])
            bucket["prediction"].append(np.asarray(predictions[label], dtype=float))
    repeat_rows: list[dict[str, object]] = []
    for (label, repeat), bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(np.concatenate(bucket["target"]),
                                  np.concatenate(bucket["prediction"]))
        repeat_rows.append({"arm": ARM_PREFIX + label, "seed": int(seed), "repeat": int(repeat),
                            **{metric: float(metrics[metric]) for metric in METRIC_COLUMNS}})
    per_config: dict[str, object] = {}
    for label in labels:
        rows = [row for row in repeat_rows if row["arm"] == ARM_PREFIX + label]
        values = [float(row["r2"]) for row in rows]
        per_config[label] = {
            "r2_mean": float(np.mean(values)) if values else float("nan"),
            "r2_min": float(np.min(values)) if values else float("nan"),
            "r2_max": float(np.max(values)) if values else float("nan"),
            "spearman_mean": mean_of(rows, "spearman"),
            "auc_gt15_mean": mean_of(rows, "auc_gt15"),
            "auc_gt30_mean": mean_of(rows, "auc_gt30"),
            "mae_mean": mean_of(rows, "mae"),
            "repeats": len(rows),
        }
    return {"repeat_rows": repeat_rows, "per_config": per_config, "seconds": seconds,
            "leak": {"folds": len(straddling),
                     "folds_with_a_straddling_compound":
                         int(sum(1 for count in straddling if count)),
                     "max_straddling_compounds_in_a_fold":
                         int(max(straddling)) if straddling else 0}}

def build_verdict(identifier, description, value, threshold, passed) -> dict[str, object]:
    return {"id": str(identifier), "description": str(description),
            "value": None if value is None else float(value),
            "threshold": None if threshold is None else float(threshold),
            "verdict": "成立" if bool(passed) else "判否"}


def gap(value, reference):
    if value is None or reference is None:
        return None
    return float(value) - float(reference)


def tick(text) -> str:
    return chr(96) + str(text) + chr(96)


def fmt(value, digits: int = 6) -> str:
    if value is None:
        return "\u2014"
    return format(float(value), "." + str(digits) + "f")


def fmt_signed(value, digits: int = 6) -> str:
    if value is None:
        return "\u2014"
    return format(float(value), "+." + str(digits) + "f")


def render_figure(summary) -> bool:
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

        labels = [config_label(index) for index in range(len(CONFIGS))]
        values = [float(summary["cross_seed"][label]) for label in labels]
        colors = ["#7f8c8d", "#8e44ad", "#8e44ad", "#c0392b", "#c0392b", "#c0392b"]
        figure, axes = plt.subplots(1, 2, figsize=(13.0, 4.8))
        positions = list(range(len(labels)))
        axes[0].bar(positions, values, 0.6, color=colors)
        for position, value in zip(positions, values):
            axes[0].annotate(format(value, ".4f"), (position, value), fontsize=7,
                             textcoords="offset points", xytext=(0, 3), ha="center")
        axes[0].axhline(GATE_R2, color="#16a085", linestyle="--", linewidth=1.0, label="0.60 门线")
        axes[0].axhline(W20_4_REGISTERED, color="#2c3e50", linestyle=":", linewidth=1.0,
                        label="W20-4 注册臂 0.6217")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels([label.replace("_", "\n", 1) for label in labels], fontsize=6)
        axes[0].set_ylim(0.40, 0.66)
        axes[0].set_ylabel("五种子均值 R²（同折配对）")
        axes[0].set_title("A 六档固定配置（灰=冻结，紫=复现锚，红=新组合点）")
        axes[0].legend(fontsize=7)
        axes[0].grid(alpha=0.25, axis="y")

        curve = [(1, float(summary["cross_seed"][labels[FROZEN_INDEX]])),
                 (5, float(summary["cross_seed"][labels[MCW5_D2_INDEX]])),
                 (7, float(summary["cross_seed"][labels[MCW7_D2_INDEX]])),
                 (10, float(summary["cross_seed"][labels[MCW10_D2_INDEX]]))]
        axes[1].plot([point[0] for point in curve], [point[1] for point in curve],
                     marker="o", color="#c0392b", label="深度 2（max_bin 128）")
        axes[1].axhline(GATE_R2, color="#16a085", linestyle="--", linewidth=1.0, label="0.60 门线")
        depth5 = float(summary["readings"]["depth_margin_mcw5"])
        depth7 = float(summary["readings"]["depth_margin_mcw7"])
        axes[1].set_xticks([1, 5, 7, 10])
        axes[1].set_xlabel("min_child_weight")
        axes[1].set_ylabel("五种子均值 R²")
        axes[1].set_title("B 叶惩罚曲线与深度边际（mcw5 " + fmt_signed(depth5, 4)
                          + " / mcw7 " + fmt_signed(depth7, 4) + "）")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W31 容量交换阶梯：深度买到的边际能不能用叶惩罚换回来", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.93))
        FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover - plotting is best effort
        print("figure failure: " + type(error).__name__ + ": " + str(error), flush=True)
        return False

def format_report(summary) -> str:
    lines: list[str] = []
    lines.append("# W31 结题报告：稠密 13 列物理块的容量交换阶梯")
    lines.append("")
    lines.append("- 预注册 " + tick("probes/w31_capacity_exchange_prereg.json")
                 + "（status = locked_before_run，revision 1）")
    lines.append("- 池：冻结主记分牌池，评分 " + str(SCOREBOARD_ROWS) + " 行 / "
                 + str(SCOREBOARD_COMPOUNDS) + " 化合物；训练掩码 full_base")
    lines.append("- 主记分牌 shot：1（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS)
                 + "）；对照对象：母体论文 v6 结语第三条（昂贵层在排序意义上可省）")
    lines.append("")
    lines.append("## 1. 裁决表")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for verdict in summary["verdicts"]:
        lines.append("| " + verdict["id"] + " " + verdict["description"] + " | "
                     + fmt(verdict["value"], 6) + " | " + fmt(verdict["threshold"], 6) + " | "
                     + verdict["verdict"] + " |")
    lines.append("")
    failures = [verdict for verdict in summary["verdicts"] if verdict["verdict"] != "成立"]
    lines.append("## 2. 判否登记（" + str(len(failures)) + " 条）")
    lines.append("")
    if failures:
        for verdict in failures:
            note = VERDICT_NOTES.get(str(verdict["id"]), "")
            lines.append("- **" + str(verdict["id"]) + "**：" + str(verdict["description"])
                         + "（读数 " + fmt(verdict["value"], 6) + " 对阈值 "
                         + fmt(verdict["threshold"], 6) + "）。" + note)
    else:
        lines.append("- 无。")
    lines.append("")
    lines.append("## 3. 六个固定配置")
    lines.append("")
    lines.append("| 档位 | 配置（只列与冻结档位不同的键） | 五种子均值 | 与冻结档位之差 |")
    lines.append("| --- | --- | --- | --- |")
    labels = [config_label(index) for index in range(len(CONFIGS))]
    frozen_overrides = CONFIGS[FROZEN_INDEX][1]
    frozen_value = float(summary["cross_seed"][labels[FROZEN_INDEX]])
    for index, (label, overrides) in enumerate(CONFIGS):
        differences = [key + " " + str(overrides[key]) for key in LADDER_COLUMNS
                       if str(overrides.get(key)) != str(frozen_overrides.get(key))]
        text = "、".join(differences) if differences else "——"
        value = float(summary["cross_seed"][label])
        shown = "**" + label + "**" if index in NEW_INDICES else label
        lines.append("| " + shown + " | " + text + " | " + fmt(value, 6) + " | "
                     + fmt_signed(value - frozen_value, 6) + " |")
    lines.append("")
    lines.append("最佳新组合档位：" + str(summary["readings"]["best_new_label"])
                 + "（五种子均值 " + fmt(summary["readings"]["best_new_mean"], 6)
                 + "，相对 W30 最佳新组合 "
                 + fmt_signed(summary["readings"]["best_new_delta_vs_w30"], 6) + "）。")
    lines.append("")
    lines.append("## 4. 逐种子读数")
    lines.append("")
    lines.append("| 种子 | " + " | ".join(labels) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in labels) + " |")
    for seed in summary["seeds"]:
        row = summary["per_seed"][str(int(seed))]
        lines.append("| " + str(int(seed)) + " | "
                     + " | ".join(fmt(row[label], 6) for label in labels) + " |")
    lines.append("| 五种子均值 | " + " | ".join(fmt(summary["cross_seed"][label], 6)
                                                for label in labels) + " |")
    lines.append("")
    lines.append("## 5. 量级对序（同一批重复上的 AUC / Spearman）")
    lines.append("")
    lines.append("| 档位 | R2 | Spearman | AUC(eps>15) | AUC(eps>30) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for label in labels:
        block = summary["per_config"][label]
        lines.append("| " + label + " | " + fmt(block["r2_mean"], 6) + " | "
                     + fmt(block["spearman_mean"], 6) + " | " + fmt(block["auc_gt15_mean"], 6)
                     + " | " + fmt(block["auc_gt30_mean"], 6) + " |")
    readings = summary["readings"]
    lines.append("")
    lines.append("档位间极差：R² " + fmt(readings["r2_range"], 6) + "，AUC(ε>30) "
                 + fmt(readings["auc30_range"], 6) + "，比值 " + fmt(readings["range_ratio"], 1)
                 + "。")
    lines.append("")
    lines.append("## 6. 三条与 v6 结语对齐的机制读数")
    lines.append("")
    lines.append("- **深度边际**：`depth_margin(mcw5) = `"
                 + fmt_signed(readings["depth_margin_mcw5"], 6) + "，`depth_margin(mcw7) = `"
                 + fmt_signed(readings["depth_margin_mcw7"], 6) + "，收缩量 "
                 + fmt_signed(readings["depth_margin_shrink"], 6) + "。")
    lines.append("- **叶惩罚曲线**（深度 2、max_bin 128）：mcw 1 "
                 + fmt(summary["cross_seed"][labels[FROZEN_INDEX]], 6) + " → mcw 5 "
                 + fmt(summary["cross_seed"][labels[MCW5_D2_INDEX]], 6) + " → mcw 7 "
                 + fmt(summary["cross_seed"][labels[MCW7_D2_INDEX]], 6) + " → mcw 10 "
                 + fmt(summary["cross_seed"][labels[MCW10_D2_INDEX]], 6) + "。")
    lines.append("- **容量天花板**：" + str(readings["global_best_label"]) + " "
                 + fmt(readings["global_best_mean"], 6) + "，对 W20-4 注册臂 "
                 + fmt_signed(readings["ceiling_delta"], 6) + "。")
    lines.append("")
    lines.append("## 7. 口径与边界")
    lines.append("")
    lines.append("- 池、评分掩码、训练掩码、分组切分器与五种子集合逐字复用冻结主记分牌；"
                 "表示是 physical_lever4（13 列稠密块），random_state 固定为 42。")
    lines.append("- 这是阶梯不是搜索：六个固定配置在同样的折上各拟合一次，没有任何选择，"
                 "因此每一档都是一个诚实读数；全部折叠任务与外层测试行只被预测、从未被用于任何选择。")
    lines.append("- 档位 0 / 1 / 2 是复现锚（冻结、W20-4 注册臂、W30 最佳新组合），"
                 "用来确认代码路径与前两周字节一致。")
    lines.append("- 本枪是固定配置阶梯、零选择器，因此**不设安慰剂臂**：没有选择器就没有可塌缩的对象。")
    lines.append("- 单表示（Physical 13 列）读数永不与冻结头条 " + tick("0.4766400383507876")
                 + " 混比；W27 的『Physical 单表示不单独构成晋升路径』声明不因本枪改变。")
    lines.append("- 本枪不新增量子化学、不装依赖、不联网；全部由盘上已有产物派生。")
    lines.append("- 主记分牌 shot = 1（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）；"
                 "四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / "
                 "0.6216672295270079）未动。")
    lines.append("")
    return "\n".join(lines) + "\n"

def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--stage", default="full", choices=("smoke", "full"))
    parser.add_argument("--render-only", action="store_true",
                        help="re-render the report from the committed summary; no refit")
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in SEEDS))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    jobs = max(1, int(args.jobs))
    stage = str(args.stage)
    seeds = tuple(int(part) for part in str(args.seeds).split(",") if part.strip())

    if bool(args.render_only):
        summary = read_json(SUMMARY_PATH)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(format_report(summary))
        print("re-rendered " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT))
        return 0

    prereg: dict = {}
    if PREREG_PATH.is_file():
        prereg = read_json(PREREG_PATH)
    if stage == "full":
        if not prereg:
            print("MISSING " + str(PREREG_PATH))
            return 1
        if str(prereg.get("status")) != "locked_before_run":
            print("the pre-registration is not locked_before_run")
            return 1

    context = sr.build_context()
    groups = [str(item) for item in context["groups"]]
    target = np.asarray(context["target"], dtype=float)
    features = np.asarray(context["physical_lever4"], dtype=float)
    print("pool: " + str(len(groups)) + " rows | physical block " + str(features.shape), flush=True)

    cache: dict[int, dict[str, object]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for seed in seeds:
        splits = w28.splits_for_seed(int(seed), context)
        if int(seed) == ANCHOR_SEED:
            if bn.fold_signature(splits) != bn.fold_signature(context["frozen_splits"]):
                print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
                return 1
        if stage == "smoke":
            splits = [item for item in splits if int(item[0]) == 0]
        result = evaluate_ladder(features, splits, groups, target, int(seed), jobs)
        cache[int(seed)] = result
        spreadsheet.extend(dict(row) for row in result["repeat_rows"])
        leakage[str(int(seed))] = dict(result["leak"])
        print("  seed " + str(int(seed)) + " | "
              + "  ".join(config_label(index) + " "
                          + format(float(result["per_config"][config_label(index)]["r2_mean"]),
                                   ".6f")
                          for index in range(len(CONFIGS)))
              + "  (" + format(float(result["seconds"]), ".1f") + "s)", flush=True)

    if stage == "smoke":
        print("stage smoke finished in " + format(time.perf_counter() - started, ".1f")
              + "s; no artifact written", flush=True)
        return 0

    labels = [config_label(index) for index in range(len(CONFIGS))]
    cross_seed = {label: float(np.mean([float(cache[int(seed)]["per_config"][label]["r2_mean"])
                                        for seed in seeds])) for label in labels}
    per_seed = {str(int(seed)): {label: float(cache[int(seed)]["per_config"][label]["r2_mean"])
                                 for label in labels} for seed in seeds}
    keys = ("r2_mean", "r2_min", "r2_max", "spearman_mean", "auc_gt15_mean", "auc_gt30_mean",
            "mae_mean", "repeats")
    per_config = {label: {key: float(np.mean([float(cache[int(seed)]["per_config"][label][key])
                                              for seed in seeds])) for key in keys}
                  for label in labels}

    frozen_label = labels[FROZEN_INDEX]
    anchor_seed42 = per_seed[str(ANCHOR_SEED)][frozen_label]
    leak_folds = sum(int(block["folds_with_a_straddling_compound"]) for block in leakage.values())
    best_new_label, best_new_mean = None, float("nan")
    for index in NEW_INDICES:
        label = labels[index]
        if np.isfinite(cross_seed[label]) and (best_new_label is None
                                               or cross_seed[label] > best_new_mean):
            best_new_label, best_new_mean = label, float(cross_seed[label])
    global_best_label, global_best_mean = None, float("nan")
    for label in labels:
        if np.isfinite(cross_seed[label]) and (global_best_label is None
                                               or cross_seed[label] > global_best_mean):
            global_best_label, global_best_mean = label, float(cross_seed[label])

    depth_margin_mcw5 = cross_seed[labels[W20_INDEX]] - cross_seed[labels[MCW5_D2_INDEX]]
    depth_margin_mcw7 = cross_seed[labels[MCW7_D4_INDEX]] - cross_seed[labels[MCW7_D2_INDEX]]
    depth_margin_shrink = depth_margin_mcw5 - depth_margin_mcw7
    r2_values = [cross_seed[label] for label in labels]
    auc_values = [per_config[label]["auc_gt30_mean"] for label in labels]
    r2_range = max(r2_values) - min(r2_values)
    auc30_range = max(auc_values) - min(auc_values)
    mcw_gain = max(cross_seed[labels[MCW7_D2_INDEX]], cross_seed[labels[MCW10_D2_INDEX]]) \
        - cross_seed[labels[MCW5_D2_INDEX]]

    readings = {
        "anchor_seed42": float(anchor_seed42),
        "anchor_seed42_gap": gap(anchor_seed42, FROZEN_SINGLE_REPRESENTATION),
        "frozen_label": frozen_label,
        "frozen_mean": float(cross_seed[frozen_label]),
        "frozen_expected": FROZEN_CROSS_SEED,
        "frozen_gap": gap(cross_seed[frozen_label], FROZEN_CROSS_SEED),
        "w20_label": labels[W20_INDEX],
        "w20_mean": float(cross_seed[labels[W20_INDEX]]),
        "w20_expected": W20_4_REGISTERED,
        "w20_gap": gap(cross_seed[labels[W20_INDEX]], W20_4_REGISTERED),
        "w30_best_label": labels[W30_INDEX],
        "w30_best_mean": float(cross_seed[labels[W30_INDEX]]),
        "w30_best_expected": W30_BEST_D2_MCW5,
        "w30_best_gap": gap(cross_seed[labels[W30_INDEX]], W30_BEST_D2_MCW5),
        "best_new_label": best_new_label,
        "best_new_mean": None if not np.isfinite(best_new_mean) else float(best_new_mean),
        "best_new_delta_vs_w30": None if not np.isfinite(best_new_mean)
        else float(best_new_mean) - float(cross_seed[labels[W30_INDEX]]),
        "global_best_label": global_best_label,
        "global_best_mean": None if not np.isfinite(global_best_mean)
        else float(global_best_mean),
        "ceiling_delta": None if not np.isfinite(global_best_mean)
        else float(global_best_mean) - W20_4_REGISTERED,
        "mcw_gain_at_d2": float(mcw_gain),
        "depth_margin_mcw5": float(depth_margin_mcw5),
        "depth_margin_mcw7": float(depth_margin_mcw7),
        "depth_margin_shrink": float(depth_margin_shrink),
        "r2_range": float(r2_range),
        "auc30_range": float(auc30_range),
        "range_ratio": float(r2_range / auc30_range) if auc30_range else float("inf"),
        "leak_folds": int(leak_folds),
        "mcw_curve_d2": {str(weight): float(cross_seed[labels[index]])
                         for weight, index in ((1, FROZEN_INDEX), (5, MCW5_D2_INDEX),
                                               (7, MCW7_D2_INDEX), (10, MCW10_D2_INDEX))},
    }

    verdicts = [
        build_verdict("H31a", "复现锚：seed 42 的冻结档位逐位复现冻结值",
                      readings["anchor_seed42_gap"], 0.0,
                      abs(float(readings["anchor_seed42_gap"])) <= REPRODUCTION_TOLERANCE),
        build_verdict("H31b", "交叉验证：冻结档位的五种子端点复现 W28/W29 冻结臂",
                      readings["frozen_gap"], CROSS_CHECK_TOLERANCE,
                      abs(float(readings["frozen_gap"])) <= CROSS_CHECK_TOLERANCE),
        build_verdict("H31c", "交叉验证：W20-4 注册臂复现 0.6216672295270079",
                      readings["w20_gap"], CROSS_CHECK_TOLERANCE,
                      abs(float(readings["w20_gap"])) <= CROSS_CHECK_TOLERANCE),
        build_verdict("H31d", "交叉验证：W30 最佳新组合复现 0.6170832198249109",
                      readings["w30_best_gap"], CROSS_CHECK_TOLERANCE,
                      abs(float(readings["w30_best_gap"])) <= CROSS_CHECK_TOLERANCE),
        build_verdict("H31e", "跨折泄漏：含跨界化合物的折数", float(leak_folds), 0.0,
                      int(leak_folds) == 0),
        build_verdict("H31f", "容量交换存在：深度 2 上 mcw 7 / 10 高出 mcw 5 的幅度",
                      readings["mcw_gain_at_d2"], CAPACITY_EXCHANGE_MIN_GAIN,
                      float(readings["mcw_gain_at_d2"]) > CAPACITY_EXCHANGE_MIN_GAIN),
        build_verdict("H31g", "深度边际收缩：depth_margin(mcw5) - depth_margin(mcw7)",
                      readings["depth_margin_shrink"], 0.0,
                      float(readings["depth_margin_shrink"]) > 0.0),
        build_verdict("H31h", "序不变量：AUC(eps>30) 档位间极差（并报 R2 极差 "
                      + fmt(r2_range, 4) + "）", readings["auc30_range"],
                      ORDER_INVARIANCE_AUC_RANGE,
                      float(readings["auc30_range"]) < ORDER_INVARIANCE_AUC_RANGE
                      and float(r2_range) > ORDER_INVARIANCE_R2_RANGE),
        build_verdict("H31i", "容量天花板未被打破：最高档位与 W20-4 注册臂之差",
                      readings["ceiling_delta"], CEILING_SLACK,
                      float(readings["ceiling_delta"]) <= CEILING_SLACK),
        build_verdict("H31j", "过门：最佳档位的五种子均值 >= 0.60",
                      readings["best_new_mean"], GATE_R2,
                      readings["best_new_mean"] is not None
                      and float(readings["best_new_mean"]) >= GATE_R2),
    ]

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "stage": stage,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(PREREG_PATH),
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
            "本枪是阶梯不是搜索：固定配置、零选择器，因此不设安慰剂臂（没有选择器就没有可塌缩的对象）。",
            "v6 结语第三条（昂贵层在排序意义上可省）在本枪被迁移到 ML 侧：模型容量也是一种昂贵层。",
            "单表示（Physical 13 列）读数永不与冻结头条 0.4766400383507876 混比。",
        ],
        "artifacts": {
            "repeats_csv": portable_relative_path(REPEATS_CSV, root=REPOSITORY_ROOT),
            "figure": portable_relative_path(FIGURE_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        },
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
    }

    write_csv(REPEATS_CSV, REPEAT_COLUMNS,
              [[row[column] for column in REPEAT_COLUMNS] for row in spreadsheet])
    dump_json(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(format_report(summary))
    figure_ok = render_figure(summary)
    print("best new: " + str(best_new_label) + " " + fmt(best_new_mean, 6)
          + " | depth margin mcw5 " + fmt_signed(depth_margin_mcw5, 6)
          + " mcw7 " + fmt_signed(depth_margin_mcw7, 6), flush=True)
    print("wrote " + portable_relative_path(REPEATS_CSV, root=REPOSITORY_ROOT))
    print("wrote " + portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT))
    print("wrote " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT))
    print("figure " + ("ok" if figure_ok else "skipped"))
    print("verdicts " + str(sum(1 for verdict in verdicts if verdict["verdict"] == "成立"))
          + "/" + str(len(verdicts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())