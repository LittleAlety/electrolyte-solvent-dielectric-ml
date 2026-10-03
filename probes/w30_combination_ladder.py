"""W30 -- combination and interaction ladder on the dense lever-4 block.

By Week 29 all four capacity keys (max_depth, min_child_weight, max_bin,
colsample_bytree) had their own single-key reading, and the four side arms inside the
Week 20-4 pre-registration grid sit within 0.0033 of each other -- inside seed noise.
What was never run is a *combination*: max_bin = 128 with min_child_weight = 5 at depth
2, max_bin = 128 with the slow fit path (400 trees, lr 0.02), and reg_lambda = 200 on
top of the Week 20-4 champion.

This probe therefore does not re-price single keys.  It is a ladder of six fixed
configurations fit once each on the frozen folds, and it carries three reproduction
anchors so that the whole code path is checked byte for byte against Weeks 20, 28 and
29 before anything is reported:

    entry 0  frozen d2                     -> 0.5861142332208197 / seed 42 0.6080587938801277
    entry 1  depth 2 + max_bin 128         -> 0.6031674542995844  (Week 29 best)
    entry 2  W20-4 registered d4/mcw5/bin128 -> 0.6216672295270079 (Week 20 champion)

Run:
    .venv/Scripts/python.exe probes/w30_combination_ladder.py --jobs 12
    .venv/Scripts/python.exe probes/w30_combination_ladder.py --stage smoke --jobs 8
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
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable

from xgboost import XGBRegressor

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w30_combination_ladder_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w30_combination_ladder_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w30_combination_ladder.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_CSV = ARTIFACTS_DIR / "w30_combination_ladder_repeats.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w30_combination_ladder.png"

SCHEMA = "w30_combination_ladder/summary@1"
TASK = "week30_combination_ladder"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED = 0.5861142332208197
W29_BEST = 0.6031674542995844
W20_4_REGISTERED = 0.6216672295270079
REPRODUCTION_TOLERANCE = 1e-09
CROSS_CHECK_TOLERANCE = 1e-06
GATE_R2 = 0.60
MIN_SEEDS_BEATING_W29 = 4
CEILING_SLACK = 0.005
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_SHOTS_THIS_WEEK = 1
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 17

#: Entry 0 / 1 / 2 are reproduction anchors; entries 3 / 4 / 5 are the new combinations.
CONFIGS = (
    ("frozen_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                   "min_child_weight": 1, "colsample_bytree": 0.8, "max_bin": 64,
                   "reg_lambda": 1.0}),
    ("w29_bin128_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                       "min_child_weight": 1, "colsample_bytree": 0.8, "max_bin": 128,
                       "reg_lambda": 1.0}),
    ("w20_4_registered_d4", {"max_depth": 4, "n_estimators": 200, "learning_rate": 0.05,
                             "min_child_weight": 5, "colsample_bytree": 0.8, "max_bin": 128,
                             "reg_lambda": 1.0}),
    ("bin128_mcw5_d2", {"max_depth": 2, "n_estimators": 200, "learning_rate": 0.05,
                        "min_child_weight": 5, "colsample_bytree": 0.8, "max_bin": 128,
                        "reg_lambda": 1.0}),
    ("bin128_n400_lr02_d2", {"max_depth": 2, "n_estimators": 400, "learning_rate": 0.02,
                             "min_child_weight": 1, "colsample_bytree": 0.8, "max_bin": 128,
                             "reg_lambda": 1.0}),
    ("d4_mcw5_bin128_l200", {"max_depth": 4, "n_estimators": 200, "learning_rate": 0.05,
                             "min_child_weight": 5, "colsample_bytree": 0.8, "max_bin": 128,
                             "reg_lambda": 200.0}),
)
FROZEN_INDEX = 0
W29_INDEX = 1
W20_INDEX = 2
NEW_INDICES = (3, 4, 5)
ARM_PREFIX = "combination_"
ANCHOR_ARM = ARM_PREFIX + CONFIGS[FROZEN_INDEX][0]
LADDER_COLUMNS = ("max_depth", "n_estimators", "learning_rate", "min_child_weight",
                  "colsample_bytree", "max_bin", "reg_lambda")

METRIC_COLUMNS = w28.METRIC_COLUMNS
REPEAT_COLUMNS = ("seed", "arm", "repeat", *METRIC_COLUMNS)

CLAIM = ("单键定价闭合之后，稠密 13 列物理块的组合点（深度 2 + max_bin 128 + min_child_weight 5、"
         "max_bin 128 + 慢拟合路径、W20-4 冠军 + reg_lambda 200）是否还有增量，以及容量天花板"
         "是否仍然停在 W20-4 注册臂")


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
    values = [float(str(row[key])) for row in rows if row.get(key) is not None]
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
        repeat_rows.append({"arm": ARM_PREFIX + label, "seed": int(seed),
                            "repeat": int(repeat),
                            **{metric: float(metrics[metric]) for metric in METRIC_COLUMNS}})
    per_config: dict[str, object] = {}
    for label in labels:
        rows = [row for row in repeat_rows if row["arm"] == ARM_PREFIX + label]
        values = [float(str(row["r2"])) for row in rows]
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


def _gap(value, reference):
    return None if value is None else abs(float(value) - float(reference))


def build_verdicts(readings) -> list[dict[str, object]]:
    return [
        build_verdict("H30a", "复现锚：seed 42 的冻结档位逐位复现冻结值",
                      readings["anchor_seed42_gap"], REPRODUCTION_TOLERANCE,
                      readings["anchor_seed42_gap"] is not None
                      and readings["anchor_seed42_gap"] <= REPRODUCTION_TOLERANCE),
        build_verdict("H30b", "交叉验证：冻结档位的五种子端点复现 W28/W29 冻结臂",
                      readings["frozen_gap"], CROSS_CHECK_TOLERANCE,
                      readings["frozen_gap"] is not None
                      and readings["frozen_gap"] <= CROSS_CHECK_TOLERANCE),
        build_verdict("H30c", "交叉验证：深度 2 + max_bin 128 复现 W29 最佳档位",
                      readings["w29_gap"], CROSS_CHECK_TOLERANCE,
                      readings["w29_gap"] is not None and readings["w29_gap"] <= CROSS_CHECK_TOLERANCE),
        build_verdict("H30d", "交叉验证：W20-4 注册臂复现 0.6216672295270079",
                      readings["w20_gap"], CROSS_CHECK_TOLERANCE,
                      readings["w20_gap"] is not None and readings["w20_gap"] <= CROSS_CHECK_TOLERANCE),
        build_verdict("H30e", "跨折泄漏：含跨界化合物的折数",
                      float(readings["leak_folds"]), 0.0,
                      int(readings["leak_folds"]) == 0),
        build_verdict("H30f", "最佳新组合档位高于 W29 最佳档位",
                      readings["best_new_delta"], 0.0,
                      readings["best_new_delta"] is not None and readings["best_new_delta"] > 0.0),
        build_verdict("H30g", "过门：最佳新组合档位的五种子均值 >= 0.60",
                      readings["best_new_mean"], GATE_R2,
                      readings["best_new_mean"] is not None and readings["best_new_mean"] >= GATE_R2),
        build_verdict("H30h", "稳健性：最佳新组合档位在多少个种子上高于 W29 最佳档位",
                      float(readings["seeds_beating_w29"]), float(MIN_SEEDS_BEATING_W29),
                      int(readings["seeds_beating_w29"]) >= MIN_SEEDS_BEATING_W29),
        build_verdict("H30i", "容量天花板未被打破：最高档位与 W20-4 注册臂之差",
                      readings["ceiling_delta"], CEILING_SLACK,
                      readings["ceiling_delta"] is not None
                      and readings["ceiling_delta"] <= CEILING_SLACK),
    ]


def build_notes(readings) -> list[str]:
    return [
        "池、评分掩码、训练掩码、分组切分器与五种子集合逐字复用冻结主记分牌；表示是 physical_lever4（13 列稠密块），拟合器是冻结的 XGBoost 估计器，random_state 固定为 " + str(FIT_SEED) + "。",
        "这是阶梯不是搜索：六个固定配置在同样的折上各拟合一次，没有任何选择，因此每一档都是一个诚实读数。",
        "档位 0 / 1 / 2 是复现锚（冻结、W29 最佳、W20-4 注册臂），用来确认代码路径与前两周字节一致；档位 3 / 4 / 5 是本轮的新组合点。",
        "全部折叠任务与外层测试行只被预测、从未被用于任何选择；GroupKFold by InChIKey 的分组口径与冻结主记分牌一致。",
        "AUC>15 / AUC>30 / Spearman 与 R² 在同一批重复上同时记录（探针自己的重复表列），因此『过门的是量级还是序』可以在这块记分牌内部直接回答；**不改 METRIC_NAMES**。",
        "本枪不新增量子化学、不装依赖、不联网；全部由盘上已有产物派生。",
        "主记分牌 shot = " + str(SCOREBOARD_SHOTS_THIS_WEEK) + "（累计 " + str(CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS) + "）；四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。",
    ]


def tick(text) -> str:
    character = chr(96)
    return character + str(text) + character


def fmt(value, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return "nan"
    return format(number, "." + str(int(digits)) + "f")


def render_figure(summary) -> bool:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w28.configure_fonts()
    labels = [config_label(index) for index in range(len(CONFIGS))]
    means = [float(summary["cross_seed"][label]) for label in labels]
    figure, axis = plt.subplots(figsize=(12.5, 6.2))
    positions = np.arange(len(labels), dtype=float)
    colors = []
    for index, label in enumerate(labels):
        if index in NEW_INDICES:
            colors.append("#c44e52")
        elif index in (W29_INDEX, W20_INDEX):
            colors.append("#8172b2")
        else:
            colors.append("#4c72b0")
    axis.bar(positions, means, color=colors, width=0.62)
    for seed, values in summary["per_seed"].items():
        series = [float(values[label]) for label in labels]
        axis.scatter(positions, series, s=18, color="#333333", alpha=0.7, zorder=3,
                     label="逐种子" if seed == list(summary["per_seed"])[0] else None)
    axis.axhline(FROZEN_CROSS_SEED, color="#555555", linestyle=":", linewidth=1.2,
                 label="冻结端点 " + fmt(FROZEN_CROSS_SEED))
    axis.axhline(W20_4_REGISTERED, color="#8172b2", linestyle="-.", linewidth=1.2,
                 label="W20-4 注册臂 " + fmt(W20_4_REGISTERED))
    axis.axhline(GATE_R2, color="#2ca02c", linestyle="--", linewidth=1.4, label="门 0.60")
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=16, ha="right")
    axis.set_ylabel("R2（10 次重复均值）")
    axis.set_title("W30 稠密块组合/交互阶梯：红 = 新组合点，紫 = 复现锚（shot = 1，累计 17）")
    axis.legend(loc="lower right", fontsize=9)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_PATH, dpi=160)
    plt.close(figure)
    return True


def format_report(summary) -> str:
    lines: list[str] = []
    lines.append("# W30 结题报告：稠密 13 列物理块的组合/交互阶梯")
    lines.append("")
    lines.append("- 预注册 " + tick("probes/w30_combination_ladder_prereg.json")
                 + "（status = locked_before_run，revision 1）")
    lines.append("- 池：冻结主记分牌池，评分 " + str(SCOREBOARD_ROWS) + " 行 / "
                 + str(SCOREBOARD_COMPOUNDS) + " 化合物；训练掩码 full_base")
    lines.append("- 主记分牌 shot：" + str(summary["main_scoreboard_attempts_delta"])
                 + "（累计 " + str(summary["cumulative_main_scoreboard_attempts"]) + "）")
    lines.append("")
    lines.append("## 1. 裁决表")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for entry in summary["verdicts"]:
        lines.append("| " + str(entry["id"]) + " " + str(entry["description"]) + " | "
                     + fmt(entry["value"]) + " | " + fmt(entry["threshold"]) + " | "
                     + str(entry["verdict"]) + " |")
    lines.append("")
    lines.append("## 2. 六个固定配置（每档在同样的折上各拟合一次，没有任何选择）")
    lines.append("")
    lines.append("| 档位 | " + " | ".join(LADDER_COLUMNS) + " | 五种子均值 | 与冻结档位之差 |")
    lines.append("| --- |" + " --- |" * (len(LADDER_COLUMNS) + 2))
    for index in range(len(CONFIGS)):
        label = config_label(index)
        overrides = CONFIGS[index][1]
        cells = [label] + [str(overrides[column]) for column in LADDER_COLUMNS]
        cells.append(fmt(summary["cross_seed"][label]))
        cells.append(fmt(summary["cross_seed"][label]
                         - summary["cross_seed"][config_label(FROZEN_INDEX)]))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("最佳新组合档位：" + str(summary["readings"]["best_new_label"]) + "（五种子均值 "
                 + fmt(summary["readings"]["best_new_mean"]) + "）。")
    lines.append("")
    lines.append("## 3. 逐种子读数")
    lines.append("")
    header = "| 种子 | " + " | ".join(config_label(index) for index in range(len(CONFIGS))) + " |"
    lines.append(header)
    lines.append("| --- |" + " --- |" * len(CONFIGS))
    for seed in sorted(summary["per_seed"], key=lambda item: int(item)):
        block = summary["per_seed"][seed]
        values = [str(seed)] + [fmt(block[config_label(index)]) for index in range(len(CONFIGS))]
        lines.append("| " + " | ".join(values) + " |")
    lines.append("| 五种子均值 | "
                 + " | ".join(fmt(summary["cross_seed"][config_label(index)])
                               for index in range(len(CONFIGS))) + " |")
    lines.append("")
    lines.append("## 4. 量级对序（同一批重复上的 AUC / Spearman）")
    lines.append("")
    lines.append("| 档位 | R2 | Spearman | AUC(eps>15) | AUC(eps>30) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for index in range(len(CONFIGS)):
        label = config_label(index)
        block = summary["per_config"][label]
        lines.append("| " + label + " | " + fmt(block["r2_mean"]) + " | "
                     + fmt(block["spearman_mean"]) + " | " + fmt(block["auc_gt15_mean"])
                     + " | " + fmt(block["auc_gt30_mean"]) + " |")
    lines.append("")
    lines.append("## 5. 口径与边界")
    lines.append("")
    for note in summary["notes"]:
        lines.append("- " + str(note))
    lines.append("")
    return "\n".join(lines)


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
        print("re-rendered " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
              flush=True)
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
    scored = np.asarray(context["scored"], dtype=bool)
    target = np.asarray(context["target"], dtype=float)
    features = np.asarray(context["physical_lever4"], dtype=float)
    print("pool: " + str(len(groups)) + " rows | scored " + str(int(scored.sum()))
          + " rows | physical block " + str(features.shape), flush=True)

    cache: dict[int, dict[str, object]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for seed in seeds:
        splits = w28.splits_for_seed(int(seed), context)
        if int(seed) == ANCHOR_SEED:
            moved = bn.fold_signature(splits) != bn.fold_signature(context["frozen_splits"])
            if moved:
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
    cross_seed: dict[str, float] = {}
    for label in labels:
        values = [float(cache[int(seed)]["per_config"][label]["r2_mean"]) for seed in seeds]
        cross_seed[label] = float(np.mean(values))
    per_seed: dict[str, object] = {}
    for seed in seeds:
        per_seed[str(int(seed))] = {label: float(cache[int(seed)]["per_config"][label]["r2_mean"])
                                    for label in labels}
    per_config: dict[str, object] = {}
    for label in labels:
        keys = ("r2_mean", "r2_min", "r2_max", "spearman_mean", "auc_gt15_mean",
                "auc_gt30_mean", "mae_mean", "repeats")
        per_config[label] = {key: float(np.mean([float(cache[int(seed)]["per_config"][label][key])
                                                 for seed in seeds])) for key in keys}
    frozen_label = labels[FROZEN_INDEX]
    frozen_mean = cross_seed[frozen_label]
    anchor_seed42 = per_seed[str(ANCHOR_SEED)][frozen_label] if str(ANCHOR_SEED) in per_seed else None
    best_new_label = None
    best_new_mean = float("nan")
    for index in NEW_INDICES:
        label = labels[index]
        if np.isfinite(cross_seed[label]) and (best_new_label is None
                                               or cross_seed[label] > best_new_mean):
            best_new_label, best_new_mean = label, float(cross_seed[label])
    global_best_label = None
    global_best_mean = float("nan")
    for label in labels:
        if np.isfinite(cross_seed[label]) and (global_best_label is None
                                               or cross_seed[label] > global_best_mean):
            global_best_label, global_best_mean = label, float(cross_seed[label])
    w29_label = labels[W29_INDEX]
    leak_folds = sum(int(block["folds_with_a_straddling_compound"]) for block in leakage.values())
    seeds_beating = sum(1 for seed in seeds
                        if best_new_label is not None
                        and float(per_seed[str(int(seed))][best_new_label])
                        > float(per_seed[str(int(seed))][w29_label]))
    readings = {
        "anchor_seed42": None if anchor_seed42 is None else float(anchor_seed42),
        "anchor_seed42_gap": _gap(anchor_seed42, FROZEN_SINGLE_REPRESENTATION),
        "frozen_label": frozen_label,
        "frozen_mean": float(frozen_mean),
        "frozen_expected": FROZEN_CROSS_SEED,
        "frozen_gap": _gap(frozen_mean, FROZEN_CROSS_SEED),
        "w29_label": w29_label,
        "w29_mean": float(cross_seed[w29_label]),
        "w29_expected": W29_BEST,
        "w29_gap": _gap(cross_seed[w29_label], W29_BEST),
        "w20_label": labels[W20_INDEX],
        "w20_mean": float(cross_seed[labels[W20_INDEX]]),
        "w20_expected": W20_4_REGISTERED,
        "w20_gap": _gap(cross_seed[labels[W20_INDEX]], W20_4_REGISTERED),
        "best_new_label": best_new_label,
        "best_new_mean": None if not np.isfinite(best_new_mean) else float(best_new_mean),
        "best_new_delta": (None if best_new_label is None or not np.isfinite(best_new_mean)
                           else float(best_new_mean) - float(cross_seed[w29_label])),
        "seeds_beating_w29": int(seeds_beating),
        "global_best_label": global_best_label,
        "global_best_mean": None if not np.isfinite(global_best_mean) else float(global_best_mean),
        "ceiling_delta": (None if not np.isfinite(global_best_mean)
                          else float(global_best_mean) - W20_4_REGISTERED),
        "leak_folds": int(leak_folds),
    }
    verdicts = build_verdicts(readings)
    notes = build_notes(readings)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": time.perf_counter() - started,
        "stage": stage,
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(PREREG_PATH),
            "status": str(prereg.get("status")),
            "revision": prereg.get("revision"),
        },
        "claim": CLAIM,
        "pool": {"rows": len(groups), "scored_rows": int(scored.sum()),
                 "scored_compounds": len({group for group, flag in zip(groups, scored) if flag}),
                 "matches_preregistration": bool(int(scored.sum()) == SCOREBOARD_ROWS)},
        "configs": [{"index": index, "label": config_label(index),
                     **dict(CONFIGS[index][1])} for index in range(len(CONFIGS))],
        "new_combination_indices": [int(index) for index in NEW_INDICES],
        "frozen_params": dict(XGB_PARAMS),
        "frozen_index": int(FROZEN_INDEX),
        "fit_seed": int(FIT_SEED),
        "seeds": [int(seed) for seed in seeds],
        "per_seed": per_seed,
        "cross_seed": cross_seed,
        "per_config": per_config,
        "readings": readings,
        "leakage": leakage,
        "verdicts": verdicts,
        "notes": notes,
        "artifacts": {"repeats": REPEATS_CSV.name},
        "figures": {"main": FIGURE_PATH.name},
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
    }

    write_csv(REPEATS_CSV, REPEAT_COLUMNS,
              [[row.get(column) for column in REPEAT_COLUMNS] for row in spreadsheet])
    summary["figures"]["written"] = bool(render_figure(summary))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(format_report(summary))
    dump_json(SUMMARY_PATH, summary)

    for entry in verdicts:
        print("  " + str(entry["id"]) + " " + str(entry["verdict"]) + " "
              + fmt(entry["value"]) + " (阈值 " + fmt(entry["threshold"]) + ")", flush=True)
    print("frozen " + fmt(frozen_mean) + " | w29 " + fmt(cross_seed[w29_label])
          + " | w20-4 " + fmt(cross_seed[labels[W20_INDEX]])
          + " | best new " + str(best_new_label) + " " + fmt(best_new_mean)
          + " | best all " + str(global_best_label) + " " + fmt(global_best_mean), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())