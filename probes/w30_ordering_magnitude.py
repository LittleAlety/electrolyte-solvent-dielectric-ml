"""W30-A -- ordering versus magnitude: a post-hoc, zero-cost decomposition.

The repository headline diagnosis is "the ordering was learned, the magnitude was
not".  So far that sentence is carried by AUC / Spearman sidecars that sit *next to*
the R-squared scoreboard.  This probe turns it into a controlled within-family
comparison at zero cost.

The W28 and W29 ladders re-fit the same representation, on the same folds, with the
same five seeds, and move nothing but hyperparameters.  If hyperparameters buy
magnitude and not ordering, then inside one ladder R-squared must move far more than
Spearman / AUC.  The ladders also contain two different feature families (the 13
column dense physical block and the 2048 column sparse Morgan block), which lets the
same decomposition say *which* family fails in *which* way.

This is deliberately post hoc: the eleven criteria below were written after the W28 and
W29 artifacts already existed, so this reading occupies no main-scoreboard shot, is not
a pre-registered conclusion, and never replaces the frozen readings.  It reads two
committed per-repeat CSVs, writes one CSV, one figure and one report, and changes
nothing else: no refit, no new feature column, no network, no METRIC_NAMES edit.

Run:
    .venv/Scripts/python.exe probes/w30_ordering_magnitude.py
"""

from __future__ import annotations

import csv
import hashlib
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import numpy as np
import w28_dense_hyperparameters as w28
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


from electrolyte_ml.pathing import portable_relative_path

ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
W28_REPEATS = ARTIFACTS_DIR / "w28_dense_hyperparameters_repeats.csv"
W29_REPEATS = ARTIFACTS_DIR / "w29_dense_binning_repeats.csv"
OUT_CSV = ARTIFACTS_DIR / "w30_ordering_magnitude.csv"
FIGURE_PATH = ARTIFACTS_DIR / "w30_ordering_magnitude.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w30_ordering_magnitude.md"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w30_ordering_magnitude_summary.json"

SCHEMA = "w30_ordering_magnitude/summary@1"
TASK = "week30_ordering_magnitude"

METRICS = ("r2", "spearman", "auc_gt15", "auc_gt30")
SEEDS = ("42", "1234", "2026", "31337", "7")

#: The two pre-registered ladders.  Prefix selects the ladder entries inside each file;
#: everything else in those files is a context arm (Morgan block, response block,
#: placebo) and is reported separately.
LADDERS = (
    {
        "week": "W28",
        "path": W28_REPEATS,
        "prefix": "grid_fixed_",
        "family": "physical_dense_13col",
        "frozen_arm": "grid_fixed_frozen_d2_n200_lr05",
    },
    {
        "week": "W29",
        "path": W29_REPEATS,
        "prefix": "binning_",
        "family": "physical_dense_13col",
        "frozen_arm": "binning_frozen_bin64_cs08_l1",
    },
)

#: Context arms worth one line each: the sparse Morgan pair (frozen versus retuned) and
#: the target-shuffled placebo.  They are not ladders, but they answer the same question.
CONTEXT = (
    ("W28", "lever4_morgan_frozen", "sparse_morgan_2048col", "稀疏 Morgan 冻结档位"),
    ("W28", "lever4_morgan_retuned", "sparse_morgan_2048col", "稀疏 Morgan 重调档位"),
    ("W28", "lever4_physical_frozen", "physical_dense_13col", "稠密块冻结档位（W28 副本臂）"),
    ("W28", "lever4_physical_retuned", "physical_dense_13col", "稠密块嵌套重调档位"),
    ("W28", "lever4_plus_response_frozen", "physical_response_26col", "响应块叠加（冻结口径）"),
    ("W28", "lever4_physical_retuned_shuffled_target", "placebo", "靶值置换（安慰剂）"),
)

CLAIM = ("在同一表示、同一折、同一种子集上只移动超参：五种子 R² 的档位间极差是否显著大于 "
         "Spearman / AUC 的档位间极差（即超参买的是量级而不是序）")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def dump_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def aggregate(path: Path):
    """Per-arm cross-seed mean of the per-repeat means, for every metric."""

    by_arm_seed: dict[str, dict[str, list[dict]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            by_arm_seed.setdefault(str(row["arm"]), {}).setdefault(str(row["seed"]), []).append(row)
    table: dict[str, dict[str, float]] = {}
    for arm, per_seed in by_arm_seed.items():
        per_seed_means: dict[str, list[float]] = {metric: [] for metric in METRICS}
        for seed, rows in per_seed.items():
            for metric in METRICS:
                per_seed_means[metric].append(statistics.fmean(float(row[metric]) for row in rows))
        entry: dict[str, float] = {}
        for metric in METRICS:
            values = per_seed_means[metric]
            entry[metric + "_mean"] = float(np.mean(values))
            entry[metric + "_sd"] = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        entry["seeds"] = float(len(per_seed))
        entry["repeats_per_seed"] = float(statistics.fmean(len(rows) for rows in per_seed.values()))
        table[arm] = entry
    return table


def spread(values):
    finite = [float(value) for value in values if value is not None and np.isfinite(value)]
    if not finite:
        return None
    return float(max(finite) - min(finite))


def fmt(value, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return "nan"
    return format(number, "." + str(int(digits)) + "f")


def build_verdict(identifier, description, value, threshold, passed):
    return {"id": str(identifier), "description": str(description),
            "value": None if value is None else float(value),
            "threshold": None if threshold is None else float(threshold),
            "verdict": "成立" if bool(passed) else "判否"}


def render_figure(rows, ladders) -> bool:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w28.configure_fonts()
    colors = {"W28": "#4c72b0", "W29": "#c44e52", "context": "#55a868"}
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 6.0))
    for week, entries in ladders.items():
        axis = axes[0]
        axis.scatter([entry["r2_mean"] for entry in entries],
                     [entry["auc_gt30_mean"] for entry in entries],
                     s=64, color=colors.get(week, "#333333"), label=week + " 固定阶梯", zorder=3)
        axis2 = axes[1]
        axis2.scatter([entry["r2_mean"] for entry in entries],
                      [entry["spearman_mean"] for entry in entries],
                      s=64, color=colors.get(week, "#333333"), label=week + " 固定阶梯", zorder=3)
    for entry in rows:
        if entry["group"] != "context":
            continue
        for axis, key in ((axes[0], "auc_gt30_mean"), (axes[1], "spearman_mean")):
            axis.scatter([entry["r2_mean"]], [entry[key]], s=44, marker="s",
                         color=colors["context"], alpha=0.85, zorder=2)
    axes[0].scatter([], [], s=44, marker="s", color=colors["context"], label="上下文臂（Morgan / 响应块 / 安慰剂）")
    for axis, key, label in ((axes[0], "auc_gt30_mean", "AUC(eps>30)"), (axes[1], "spearman_mean", "Spearman rho")):
        axis.set_xlabel("R2（5 种子均值，原尺度）")
        axis.set_ylabel(label)
        axis.grid(alpha=0.25)
        axis.legend(loc="lower right", fontsize=9)
        axis.axvline(0.60, color="#2ca02c", linestyle="--", linewidth=1.2)
        axis.text(0.602, axis.get_ylim()[0], " 门 0.60", color="#2ca02c", fontsize=8, va="bottom")
    axes[0].set_title("量级（R2）对排序（AUC30）：同一阶梯内 R2 大幅移动，AUC 几乎不动")
    axes[1].set_title("量级（R2）对排序（Spearman 相关）")
    figure.suptitle("W30-A 后验读数：超参买的是量级，不是序（不占 shot）", fontsize=12)
    figure.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_PATH, dpi=160)
    plt.close(figure)
    return True


def format_report(summary) -> str:
    lines = []
    lines.append("# W30-A 后验读数：超参买的是量级，不是序")
    lines.append("")
    lines.append("- 性质：**后验读数**（判据在看到 W28/W29 产物之后才写），**不占主记分牌 shot**，不构成预注册结论")
    lines.append("- 输入：`probes/artifacts/w28_dense_hyperparameters_repeats.csv`（512 行）、"
                 "`probes/artifacts/w29_dense_binning_repeats.csv`（300 行），逐位只读")
    lines.append("- 口径：同一表示、同一折、同一种子集；每档的逐重复指标先按种子平均，再对五个种子平均")
    lines.append("- 主记分牌 shot：0（累计仍为 " + str(summary["cumulative_main_scoreboard_attempts"]) + "）")
    lines.append("")
    lines.append("## 1. 十一条判据")
    lines.append("")
    lines.append("| 判据 | 读数 | 阈值 | 裁决 |")
    lines.append("| --- | --- | --- | --- |")
    for entry in summary["verdicts"]:
        lines.append("| " + str(entry["id"]) + " " + str(entry["description"]) + " | "
                     + fmt(entry["value"]) + " | " + fmt(entry["threshold"]) + " | "
                     + str(entry["verdict"]) + " |")
    lines.append("")
    lines.append("## 2. 全部读数")
    lines.append("")
    lines.append("| 组 | 来源 | 档位 | R2 | Spearman | AUC15 | AUC30 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in summary["readings"]:
        lines.append("| " + str(row["group"]) + " | " + str(row["week"]) + " | `" + str(row["arm"])
                     + "` | " + fmt(row["r2_mean"]) + " | " + fmt(row["spearman_mean"]) + " | "
                     + fmt(row["auc_gt15_mean"]) + " | " + fmt(row["auc_gt30_mean"]) + " |")
    lines.append("")
    lines.append("## 3. 阶梯内的档位间极差（同族、同折、同种子）")
    lines.append("")
    lines.append("| 阶梯 | 表示族 | 档位数 | R2 极差 | Spearman 极差 | AUC30 极差 | R2/AUC30 极差比 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for block in summary["ladders"]:
        lines.append("| " + str(block["week"]) + " | " + str(block["family"]) + " | "
                     + str(block["arms"]) + " | " + fmt(block["spread"]["r2_mean"]) + " | "
                     + fmt(block["spread"]["spearman_mean"]) + " | "
                     + fmt(block["spread"]["auc_gt30_mean"]) + " | "
                     + fmt(block["ratio_r2_over_auc30"], 1) + " |")
    lines.append("")
    lines.append("## 4. 四条必须并报的边界")
    lines.append("")
    for note in summary["notes"]:
        lines.append("- " + str(note))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    for path in (W28_REPEATS, W29_REPEATS):
        if not path.is_file():
            print("MISSING " + str(path))
            return 1

    tables = {"W28": aggregate(W28_REPEATS), "W29": aggregate(W29_REPEATS)}

    readings = []
    ladders = {}
    for ladder in LADDERS:
        week = str(ladder["week"])
        prefix = str(ladder["prefix"])
        table = tables[week]
        arms = sorted(arm for arm in table if arm.startswith(prefix))
        ladders[week] = [{"arm": arm, **table[arm]} for arm in arms]
        for arm in arms:
            readings.append({"group": "ladder", "week": week, "family": str(ladder["family"]),
                             "arm": arm, **{metric + "_mean": table[arm][metric + "_mean"] for metric in METRICS}})
    for week, arm, family, _label in CONTEXT:
        if arm in tables[week]:
            readings.append({"group": "context", "week": week, "family": family, "arm": arm,
                             **{metric + "_mean": tables[week][arm][metric + "_mean"] for metric in METRICS}})

    ladder_blocks = []
    for ladder in LADDERS:
        week = str(ladder["week"])
        table = tables[week]
        prefix = str(ladder["prefix"])
        arms = sorted(arm for arm in table if arm.startswith(prefix))
        spreads = {metric + "_mean": spread(table[arm][metric + "_mean"] for arm in arms)
                   for metric in METRICS}
        ratio = None
        if spreads["auc_gt30_mean"]:
            ratio = float(spreads["r2_mean"] / spreads["auc_gt30_mean"])
        ladder_blocks.append({"week": week, "family": str(ladder["family"]), "arms": len(arms),
                              "frozen_arm": str(ladder["frozen_arm"]), "spread": spreads,
                              "ratio_r2_over_auc30": ratio})

    # --- criteria (written post hoc, recorded as such) -------------------------------
    r2_spreads = [float(block["spread"]["r2_mean"]) for block in ladder_blocks]
    spearman_spreads = [float(block["spread"]["spearman_mean"]) for block in ladder_blocks]
    auc_spreads = [float(block["spread"]["auc_gt30_mean"]) for block in ladder_blocks]
    ratios = [float(block["ratio_r2_over_auc30"]) for block in ladder_blocks]
    morgan = tables["W28"]
    verdicts = [
        build_verdict("P1", "每条稠密阶梯的 R2 档位间极差", min(r2_spreads), 0.05,
                      all(value > 0.05 for value in r2_spreads)),
        build_verdict("P2", "每条稠密阶梯的 AUC30 档位间极差", max(auc_spreads), 0.01,
                      all(value < 0.01 for value in auc_spreads)),
        build_verdict("P3", "每条稠密阶梯的 Spearman 档位间极差", max(spearman_spreads), 0.025,
                      all(value < 0.025 for value in spearman_spreads)),
        build_verdict("P4", "R2 极差 / AUC30 极差的比值（最小值）", min(ratios), 5.0,
                      all(value > 5.0 for value in ratios)),
        build_verdict("P5", "稠密块全部档位的 AUC30 下界",
                      min(entry["auc_gt30_mean"] for entry in readings
                          if entry["family"] == "physical_dense_13col"), 0.90,
                      all(entry["auc_gt30_mean"] >= 0.90 for entry in readings
                          if entry["family"] == "physical_dense_13col")),
        build_verdict("P6", "Morgan 冻结档位 R2（量级侧失败）",
                      morgan["lever4_morgan_frozen"]["r2_mean"], 0.10,
                      morgan["lever4_morgan_frozen"]["r2_mean"] < 0.10),
        build_verdict("P7", "Morgan 冻结档位 AUC30（排序侧也失败）",
                      morgan["lever4_morgan_frozen"]["auc_gt30_mean"], 0.70,
                      morgan["lever4_morgan_frozen"]["auc_gt30_mean"] < 0.70),
        build_verdict("P8", "Morgan 重调后 AUC30 的恢复量",
                      morgan["lever4_morgan_retuned"]["auc_gt30_mean"]
                      - morgan["lever4_morgan_frozen"]["auc_gt30_mean"], 0.15,
                      morgan["lever4_morgan_retuned"]["auc_gt30_mean"]
                      - morgan["lever4_morgan_frozen"]["auc_gt30_mean"] > 0.15),
        build_verdict("P9", "Morgan 重调后 R2 仍近零（量级未恢复）",
                      morgan["lever4_morgan_retuned"]["r2_mean"], 0.10,
                      morgan["lever4_morgan_retuned"]["r2_mean"] < 0.10),
        build_verdict("P10", "安慰剂 AUC30 塌缩（低于 0.50）",
                      morgan["lever4_physical_retuned_shuffled_target"]["auc_gt30_mean"], 0.50,
                      morgan["lever4_physical_retuned_shuffled_target"]["auc_gt30_mean"] < 0.50),
        build_verdict("P11", "重复臂逐位一致（W28 两条冻结臂同值）",
                      abs(morgan["lever4_physical_frozen"]["r2_mean"]
                          - morgan["grid_fixed_frozen_d2_n200_lr05"]["r2_mean"]), 1e-09,
                      abs(morgan["lever4_physical_frozen"]["r2_mean"]
                          - morgan["grid_fixed_frozen_d2_n200_lr05"]["r2_mean"]) <= 1e-09),
    ]

    notes = [
        "这是**后验读数**：十一条判据写在 W28/W29 产物既存之后，因此**不占主记分牌 shot**，也不得当作预注册结论引用（附录 C「后验读数」定义）。",
        "四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）**字节未动**；本探针不重拟合、不新增特征列、不联网、不改 `METRIC_NAMES`。",
        "R² 与 AUC/Spearman 量的是两件事：R² 量量级，AUC/Spearman 量序。本读数只说「在本仓的稠密 13 列块上，超参主要买量级」，**不外推**到别的表示、名册或池。",
        "Morgan 对照在 W28 的重复表里只有 1 个种子 × 1 个重复（臂 `lever4_morgan_frozen` / `lever4_morgan_retuned` 的 seeds = 1、repeats_per_seed = 1），因此 P6–P9 是**过程对照级**读数，不作结论级主张；安慰剂臂同样是 1 个种子。",
    ]

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": time.perf_counter() - started,
        "post_hoc": True,
        "occupies_main_scoreboard_shot": False,
        "claim": CLAIM,
        "inputs": {
            "w28_repeats": {"path": portable_relative_path(W28_REPEATS, root=REPOSITORY_ROOT),
                            "sha256": sha256_file(W28_REPEATS)},
            "w29_repeats": {"path": portable_relative_path(W29_REPEATS, root=REPOSITORY_ROOT),
                            "sha256": sha256_file(W29_REPEATS)},
        },
        "seeds": list(SEEDS),
        "readings": readings,
        "ladders": ladder_blocks,
        "frozen_readings": {"baseline": 0.4091179943351143, "headline": 0.4766400383507876,
                            "single_representation_endpoint": 0.5861142332208197,
                            "week20_registered_arm": 0.6216672295270079},
        "verdicts": verdicts,
        "notes": notes,
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 16,
        "artifacts": {"table": OUT_CSV.name},
        "figures": {"main": FIGURE_PATH.name},
    }

    header = ("group", "week", "family", "arm", "r2_mean", "r2_sd", "spearman_mean",
              "auc_gt15_mean", "auc_gt30_mean", "seeds", "repeats_per_seed")
    rows = []
    for row in readings:
        table = tables[str(row["week"])][str(row["arm"])]
        rows.append([row["group"], row["week"], row["family"], row["arm"],
                     table["r2_mean"], table["r2_sd"], table["spearman_mean"],
                     table["auc_gt15_mean"], table["auc_gt30_mean"], int(table["seeds"]),
                     table["repeats_per_seed"]])
    write_csv(OUT_CSV, header, rows)
    summary["figures"]["written"] = bool(render_figure(readings, ladders))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(format_report(summary))
    dump_json(SUMMARY_PATH, summary)

    for entry in verdicts:
        print("  " + str(entry["id"]) + " " + str(entry["verdict"]) + " " + fmt(entry["value"])
              + " (阈值 " + fmt(entry["threshold"]) + ")", flush=True)
    for block in ladder_blocks:
        print("  " + str(block["week"]) + " 阶梯：R2 极差 " + fmt(block["spread"]["r2_mean"])
              + " | Spearman 极差 " + fmt(block["spread"]["spearman_mean"])
              + " | AUC30 极差 " + fmt(block["spread"]["auc_gt30_mean"])
              + " | 比值 " + fmt(block["ratio_r2_over_auc30"], 1), flush=True)
    print("report " + portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())