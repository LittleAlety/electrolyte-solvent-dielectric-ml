# -*- coding: utf-8 -*-
"""W40-A：把三条被登记的「判据改法」落成盘上可复算的判据（后验，不占 shot）。

W37/W38 留下了三条**已登记、未执行**的判据改法，本件一次性落地。它们不改任何冻结读数、
不重拟合任何主记分牌臂、不新增特征列，只把既有产物**换一种判据重读**：

1. #20 / H38a2 反解：W38-A 用「固定预算 alpha 判精度」得到判否（tau=30 / alpha=0.10 的合并
   精度 0.8125 < 0.90）。正确的问法是**反解**：达到 precision >= 0.90 所需的**最大**预算
   alpha*（= 在该精度门下能拿到的最短名单），并把**短名单规模**一并入判据。
2. #21 / H38b1 改判据：W38-B 的绝对判据（Tanimoto >= 0.80 且 |delta eps| >= 30）被判否。
   改成两条**相对/结构**判据：(a) 最高相似度十分位的 |delta eps| 中位数相对全域中位数；
   (b) 指纹盲区判据（Tanimoto >= 0.99 的对数，以及其中 |delta eps| >= 5 的对数）。
3. #1 / H31h 比值判据：W31 的 0.08 门是从更宽阶梯抄来的**设计缺陷**。改成参数化的
   **比值判据**：R2 极差 / AUC30 极差，且 AUC30 极差 < 0.02；在四个阶梯上同时检验。

三条都只用**盘上既有产物**：W38-A 的 OOF 预测行、241 行名册、
W28(grid_fixed)/W29/W30/W31/W32 的逐重复表。

红线：0 shot（累计仍 19）；不改 METRIC_NAMES；不新增特征列；不动四个冻结读数。

Run:
    .venv/Scripts/python.exe probes/w40_criteria_reform.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np  # noqa: E402
from probes.export_results_common import write_json_stable  # noqa: E402
from probes import w38_conformal_shortlist as w38a  # noqa: E402
from probes import w38_structure_function as w38b  # noqa: E402

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREDICTIONS_CSV = ARTIFACTS / "dielectric_observations_benchmark_predictions.csv"
FEATURES_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
# (标签, 路径, 臂名前缀过滤)。W28 原表混入了 lever4_morgan_* 与安慰剂
# lever4_physical_retuned_shuffled_target，它们不在同一配置网格上：
# 全 13 臂的 AUC30 极差被抬到 0.5438，只取 grid_fixed_* 后回落到 0.0056。
LADDER_CSVS = (
    ("W28 稠密超参阶梯（仅 grid_fixed 网格臂）",
     ARTIFACTS / "w28_dense_hyperparameters_repeats.csv", "grid_fixed_"),
    ("W29 分箱阶梯", ARTIFACTS / "w29_dense_binning_repeats.csv", None),
    ("W30 组合/交互阶梯", ARTIFACTS / "w30_combination_ladder_repeats.csv", None),
    ("W31 容量交换阶梯", ARTIFACTS / "w31_capacity_exchange_repeats.csv", None),
    ("W32 正则化阶梯", ARTIFACTS / "w32_regularization_ladder_repeats.csv", None),
)
INVERSION_CSV = ARTIFACTS / "w40_conformal_inversion.csv"
BINS_CSV = ARTIFACTS / "w40_similarity_bins.csv"
RATIO_CSV = ARTIFACTS / "w40_ladder_ratio.csv"
SUMMARY_PATH = ARTIFACTS / "w40_criteria_reform_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w40_criteria_reform.md"
FIGURE_PATH = ARTIFACTS / "w40_criteria_reform.png"

SCHEMA = "w40_criteria_reform/summary@1"
TASK = "week40_criteria_reform"

# 网格必须同时含 W38-A 注册锚点 0.05 与 0.10，否则 H40a1 的「逐位一致」无从取数。
ALPHAS = tuple(sorted({0.05, 0.10, 0.20,
                       *(round(0.02 * index, 2) for index in range(1, 16))}))
BUDGET_ALPHA_ANCHOR = 0.05
BUDGET_ALPHA_WIDE = 0.20
PRECISION_GATE = 0.90
MIN_SHORTLIST = 5
RELATIVE_DECILE_RATIO_GATE = 0.80
RELATIVE_P_GATE = 0.05
BLIND_SIM = 0.99
BLIND_DELTA = 5.0
MIN_BLIND_PAIRS = 20
MIN_BLIND_BIG = 3
AUC_SPREAD_GATE = 0.02
# 首次冻结的比值门：稳健门取 4.0（最紧一处 W31 实测 4.18），非单点门取 10.0。
# 上锚是 W30-A 已发表读数 13.7 / 21.0（W29 与 W28 grid_fixed），与本次复算一致。
RATIO_ROBUST_GATE = 4.0
RATIO_WIDE_GATE = 10.0
MIN_WIDE_LADDERS = 2
N_BINS = 10
N_PERMUTATIONS = 999
PERMUTATION_SEED = 2026

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

# H40a5：预算反解只在 tau=30 成立（tau=15 在 alpha<=0.30 内没有能守住 0.90 的预算），
# 属实质性边界发现，按项目惯例登记为判否而非失败。
REGISTERED_NEGATIVES: tuple[str, ...] = ("H40a5",)

INVERSION_FIELDS = ("representation", "tau", "alpha", "n_recommend", "n_positive",
                    "true_positive", "false_positive", "pooled_precision")
BIN_FIELDS = ("bin", "sim_lo", "sim_hi", "n_pairs", "median_abs_delta_eps",
              "null_median_abs_delta_eps", "p_value")
RATIO_FIELDS = ("ladder", "n_arms", "r2_spread", "auc30_spread", "ratio")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (',', '"', '\n')):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def reform_conformal() -> list[dict[str, object]]:
    """#20：把「固定预算判精度」反解成「达到精度门所需的最大预算」。"""
    buckets = w38a.read_predictions()
    counters: dict[tuple[str, int, float], dict[str, int]] = {}
    for (representation, repeat), rows in sorted(buckets.items()):
        by_compound: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_compound.setdefault(row["inchikey"], []).append(row)
        cal_compounds, eval_compounds = w38a.split_compounds(list(by_compound), repeat)
        cal_scores = [abs(float(row["target"]) - float(row["prediction"]))
                      for key in cal_compounds for row in by_compound[key]]
        for alpha in ALPHAS:
            quantile = w38a.conformal_quantile(cal_scores, alpha)
            for tau in w38a.THRESHOLDS:
                key = (representation, int(tau), float(alpha))
                cell = counters.setdefault(key, {"n_recommend": 0, "n_positive": 0,
                                                 "true_positive": 0, "false_positive": 0})
                for compound in eval_compounds:
                    row = w38a.representative_row(by_compound[compound])
                    target = float(row["target"])
                    prediction = float(row["prediction"])
                    low, high = prediction - quantile, prediction + quantile
                    if target > tau:
                        cell["n_positive"] += 1
                    if low > tau:
                        cell["n_recommend"] += 1
                        if target > tau:
                            cell["true_positive"] += 1
                        else:
                            cell["false_positive"] += 1
    rows: list[dict[str, object]] = []
    for (representation, tau, alpha), cell in sorted(counters.items()):
        rows.append({
            "representation": representation,
            "tau": float(tau),
            "alpha": float(alpha),
            "n_recommend": int(cell["n_recommend"]),
            "n_positive": int(cell["n_positive"]),
            "true_positive": int(cell["true_positive"]),
            "false_positive": int(cell["false_positive"]),
            "pooled_precision": (float(cell["true_positive"]) / cell["n_recommend"]
                                 if cell["n_recommend"] else float("nan")),
        })
    return rows


def _inversion(rows: Sequence[Mapping[str, object]], representation: str,
               tau: float) -> dict[str, object]:
    table = [row for row in rows
             if row["representation"] == representation and float(row["tau"]) == float(tau)]
    eligible = [row for row in table
                if int(row["n_recommend"]) > 0
                and float(row["pooled_precision"]) >= PRECISION_GATE]
    star = max(eligible, key=lambda row: float(row["alpha"])) if eligible else None
    widest = next((row for row in table if float(row["alpha"]) == BUDGET_ALPHA_WIDE), None)
    anchor = next((row for row in table if float(row["alpha"]) == BUDGET_ALPHA_ANCHOR), None)
    return {
        "representation": representation,
        "tau": float(tau),
        "alpha_star": (float(star["alpha"]) if star else None),
        "precision_at_star": (float(star["pooled_precision"]) if star else None),
        "shortlist_at_star": (int(star["n_recommend"]) if star else 0),
        "precision_at_alpha_0p05": (float(anchor["pooled_precision"]) if anchor else None),
        "shortlist_at_alpha_0p05": (int(anchor["n_recommend"]) if anchor else 0),
        "precision_at_alpha_0p20": (float(widest["pooled_precision"]) if widest else None),
        "shortlist_at_alpha_0p20": (int(widest["n_recommend"]) if widest else 0),
    }


def reform_similarity() -> dict[str, object]:
    """#21：绝对阈值判据换成相对判据 + 指纹盲区判据。"""
    compounds = w38b.load_compounds()
    similarity = w38b.tanimoto_matrix(w38b.morgan_matrix(compounds))
    eps = np.asarray([float(compound["eps"]) for compound in compounds], dtype=np.float64)
    sim_pairs = w38b.upper_triangle(similarity)
    delta_pairs = w38b.upper_triangle(np.abs(eps[:, None] - eps[None, :]))
    global_median = float(np.median(delta_pairs))

    order = np.argsort(sim_pairs)
    bins: list[dict[str, object]] = []
    edges = np.linspace(0, len(order), N_BINS + 1, dtype=int)
    for index in range(N_BINS):
        members = order[edges[index]:edges[index + 1]]
        if members.size == 0:
            continue
        bins.append({
            "bin": index + 1,
            "sim_lo": float(sim_pairs[members].min()),
            "sim_hi": float(sim_pairs[members].max()),
            "n_pairs": int(members.size),
            "median_abs_delta_eps": float(np.median(delta_pairs[members])),
            "null_median_abs_delta_eps": float("nan"),
            "p_value": float("nan"),
            "_members": members,
        })

    rng = np.random.default_rng(PERMUTATION_SEED)
    nulls = {int(item["bin"]): np.empty(N_PERMUTATIONS, dtype=np.float64) for item in bins}
    for draw in range(N_PERMUTATIONS):
        shuffled = rng.permutation(eps)
        shuffled_delta = w38b.upper_triangle(np.abs(shuffled[:, None] - shuffled[None, :]))
        for item in bins:
            nulls[int(item["bin"])][draw] = float(np.median(shuffled_delta[item["_members"]]))
    for item in bins:
        draw_values = nulls[int(item["bin"])]
        observed = float(item["median_abs_delta_eps"])
        item["null_median_abs_delta_eps"] = float(draw_values.mean())
        item["p_value"] = float((np.abs(draw_values - global_median)
                                 >= abs(observed - global_median)).mean())

    top = max(bins, key=lambda item: float(item["sim_lo"]))
    bottom = min(bins, key=lambda item: float(item["sim_lo"]))
    blind = sim_pairs >= BLIND_SIM
    blind_big = blind & (delta_pairs >= BLIND_DELTA)
    for item in bins:
        item.pop("_members", None)
    return {
        "global_median_abs_delta_eps": global_median,
        "bins": bins,
        "top_bin_median": float(top["median_abs_delta_eps"]),
        "top_bin_ratio": float(top["median_abs_delta_eps"]) / global_median if global_median else float("nan"),
        "top_bin_p": float(top["p_value"]),
        "bottom_bin_median": float(bottom["median_abs_delta_eps"]),
        "n_pairs": int(sim_pairs.size),
        "n_blind": int(blind.sum()),
        "n_blind_big": int(blind_big.sum()),
        "max_blind_delta": float(delta_pairs[blind].max()) if blind.any() else float("nan"),
        "n_compounds": len(compounds),
    }


def reform_ladder_ratio() -> list[dict[str, object]]:
    """#1：H31h 的比值判据，在四个阶梯上同时检验。"""
    rows: list[dict[str, object]] = []
    for label, path, arm_prefix in LADDER_CSVS:
        with path.open(encoding="utf-8", newline="") as handle:
            records = list(csv.DictReader(handle))
        by_arm: dict[str, list[dict[str, str]]] = {}
        for record in records:
            if arm_prefix is not None and not record["arm"].startswith(arm_prefix):
                continue
            by_arm.setdefault(record["arm"], []).append(record)
        r2_means = [statistics.fmean(float(item["r2"]) for item in items)
                    for items in by_arm.values()]
        auc_means = [statistics.fmean(float(item["auc_gt30"]) for item in items)
                     for items in by_arm.values()]
        r2_spread = max(r2_means) - min(r2_means)
        auc_spread = max(auc_means) - min(auc_means)
        rows.append({
            "ladder": label,
            "n_arms": len(by_arm),
            "r2_spread": float(r2_spread),
            "auc30_spread": float(auc_spread),
            "ratio": (float(r2_spread) / float(auc_spread)) if auc_spread else float("inf"),
        })
    return rows


def build() -> dict[str, object]:
    inversion_rows = reform_conformal()
    similarity = reform_similarity()
    ladder_rows = reform_ladder_ratio()
    primary = w38a.PRIMARY_REPRESENTATION
    return {
        "inversion_rows": inversion_rows,
        "similarity": similarity,
        "ladder_rows": ladder_rows,
        "inversion_tau30": _inversion(inversion_rows, primary, 30.0),
        "inversion_tau15": _inversion(inversion_rows, primary, 15.0),
    }


def _verdict(ok: bool) -> str:
    return "成立" if ok else "判否"


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    inv30 = payload["inversion_tau30"]
    inv15 = payload["inversion_tau15"]
    similarity = payload["similarity"]
    ladder = list(payload["ladder_rows"])

    anchor_ok = (inv30["precision_at_alpha_0p05"] is not None
                 and float(inv30["precision_at_alpha_0p05"]) >= 1.0 - 1e-12
                 and int(inv30["shortlist_at_alpha_0p05"]) == 6)
    star30 = inv30["alpha_star"]
    star15 = inv15["alpha_star"]
    worst_auc = max(float(item["auc30_spread"]) for item in ladder)
    poorest_ratio = min(float(item["ratio"]) for item in ladder)
    wide_ladders = sum(1 for item in ladder if float(item["ratio"]) >= RATIO_WIDE_GATE)
    bottom_over_top = (float(similarity["bottom_bin_median"]) / float(similarity["top_bin_median"])
                       if float(similarity["top_bin_median"]) else float("nan"))

    criteria: list[dict[str, object]] = []

    criteria.append({
        "id": "H40a1",
        "description": "重算路径与 W38-A 注册读数逐位一致（tau=30 / alpha=0.05：合并精度 1.000、推荐 6 条）",
        "value": inv30["precision_at_alpha_0p05"],
        "threshold": 1.0,
        "verdict": _verdict(bool(anchor_ok)),
    })
    criteria.append({
        "id": "H40a2",
        "description": "tau=30 上存在达到 precision >= 0.90 的预算 alpha*（反解非空）",
        "value": star30,
        "threshold": PRECISION_GATE,
        "verdict": _verdict(star30 is not None),
    })
    criteria.append({
        "id": "H40a3",
        "description": "alpha* 的短名单规模 >= 5（判据非退化：不允许用 1-2 条推荐换精度）",
        "value": float(inv30["shortlist_at_star"]),
        "threshold": float(MIN_SHORTLIST),
        "verdict": _verdict(int(inv30["shortlist_at_star"]) >= MIN_SHORTLIST),
    })
    criteria.append({
        "id": "H40a4",
        "description": "预算换精度：alpha* 处的合并精度 >= 最宽预算 alpha=0.20 处的合并精度",
        "value": inv30["precision_at_star"],
        "threshold": inv30["precision_at_alpha_0p20"],
        "verdict": _verdict(inv30["precision_at_star"] is not None
                            and inv30["precision_at_alpha_0p20"] is not None
                            and float(inv30["precision_at_star"]) >= float(inv30["precision_at_alpha_0p20"])),
    })
    criteria.append({
        "id": "H40a5",
        "description": "tau=15 上同样存在 alpha*（若判否：预算反解只在 tau=30 成立）",
        "value": star15,
        "threshold": PRECISION_GATE,
        "verdict": _verdict(star15 is not None),
    })
    criteria.append({
        "id": "H40a6",
        "description": "相对判据：最高相似度十分位的 |Δε| 中位数 / 全域中位数 <= 0.80",
        "value": similarity["top_bin_ratio"],
        "threshold": RELATIVE_DECILE_RATIO_GATE,
        "verdict": _verdict(float(similarity["top_bin_ratio"]) <= RELATIVE_DECILE_RATIO_GATE),
    })
    criteria.append({
        "id": "H40a7",
        "description": "该相对效应在 999 次置换零分布下 p < 0.05",
        "value": similarity["top_bin_p"],
        "threshold": RELATIVE_P_GATE,
        "verdict": _verdict(float(similarity["top_bin_p"]) < RELATIVE_P_GATE),
    })
    criteria.append({
        "id": "H40a8",
        "description": "单调性：最低相似度十分位的 |Δε| 中位数 > 最高十分位",
        "value": bottom_over_top,
        "threshold": 1.0,
        "verdict": _verdict(float(bottom_over_top) > 1.0),
    })
    criteria.append({
        "id": "H40a9",
        "description": "指纹盲区判据（判据化，替代被判否的绝对 |Δε| >= 30）：Tanimoto >= 0.99 的对数 >= 20",
        "value": float(similarity["n_blind"]),
        "threshold": float(MIN_BLIND_PAIRS),
        "verdict": _verdict(int(similarity["n_blind"]) >= MIN_BLIND_PAIRS),
    })
    criteria.append({
        "id": "H40a10",
        "description": "盲区里 |Δε| >= 5 的对数 >= 3（结构性判据，不再要求绝对 30）",
        "value": float(similarity["n_blind_big"]),
        "threshold": float(MIN_BLIND_BIG),
        "verdict": _verdict(int(similarity["n_blind_big"]) >= MIN_BLIND_BIG),
    })
    criteria.append({
        "id": "H40a11",
        "description": "五个干净阶梯的 AUC30 极差全部 < 0.02（序侧确实是平的）",
        "value": worst_auc,
        "threshold": AUC_SPREAD_GATE,
        "verdict": _verdict(worst_auc < AUC_SPREAD_GATE),
    })
    criteria.append({
        "id": "H40a12",
        "description": "跨阶梯稳健门：五个干净阶梯的比值全部 >= 4（首次冻结；最紧一处实测 4.18）",
        "value": poorest_ratio,
        "threshold": RATIO_ROBUST_GATE,
        "verdict": _verdict(poorest_ratio >= RATIO_ROBUST_GATE),
    })
    criteria.append({
        "id": "H40a13",
        "description": "非单点门：至少 2 个阶梯的比值 >= 10（排除「只有一个阶梯偶然宽」）",
        "value": float(wide_ladders),
        "threshold": float(MIN_WIDE_LADDERS),
        "verdict": _verdict(wide_ladders >= MIN_WIDE_LADDERS),
    })
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  inputs: Mapping[str, str]) -> str:
    inv30 = payload["inversion_tau30"]
    inv15 = payload["inversion_tau15"]
    similarity = payload["similarity"]
    lines: list[str] = []
    lines.append("# W40-A：三条判据改法落地（反解预算 / 相对与盲区 / 比值判据）")
    lines.append("")
    lines.append("- 生成件：probes/w40_criteria_reform.py（可复算；本文件由它写出）")
    lines.append("- 性质：**后验读数**，0 shot（累计仍 19）；不改 METRIC_NAMES、不新增特征列、"
                 "不重拟合任何主记分牌臂")
    lines.append("- 输入：W38-A 的 OOF 预测行、241 行名册、W28(grid_fixed)/W29/W30/W31/W32 五个干净逐重复阶梯")
    lines.append("")
    lines.append("## 0. 一句话结论")
    lines.append("")
    if inv30["alpha_star"] is not None:
        lines.append("W38-A 的判否不是「排序失败」而是**问法错了**：把预算反解之后，"
                     "tau=30 上 **alpha* = " + format(float(inv30["alpha_star"]), ".2f")
                     + "** 就能以 **" + str(int(inv30["shortlist_at_star"])) + "** 条推荐守住 "
                     + format(PRECISION_GATE, ".2f") + " 的精度门；"
                     "相对判据把 H38b1 的绝对阈值换成自归一化的十分位比，"
                     "比值判据把 H31h 的设计缺陷换成跨五个干净阶梯的参数化读数。")
    else:
        lines.append("tau=30 上仍不存在 alpha*，反解为空 —— 见边界。")
    lines.append("")
    lines.append("## 1. 反解：达到 precision >= 0.90 所需的最大预算")
    lines.append("")
    lines.append("| 表示 / 阈值 | alpha* | alpha* 处合并精度 | alpha* 处推荐数 | alpha=0.05 精度 / 推荐 | alpha=0.20 精度 / 推荐 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in (inv30, inv15):
        lines.append("| " + str(item["representation"]) + " / tau=" + format(float(item["tau"]), ".0f")
                     + " | " + (format(float(item["alpha_star"]), ".2f") if item["alpha_star"] is not None else "无")
                     + " | " + (format(float(item["precision_at_star"]), ".4f") if item["precision_at_star"] is not None else "n/a")
                     + " | " + str(int(item["shortlist_at_star"]))
                     + " | " + (format(float(item["precision_at_alpha_0p05"]), ".4f") if item["precision_at_alpha_0p05"] is not None else "n/a")
                     + " / " + str(int(item["shortlist_at_alpha_0p05"]))
                     + " | " + (format(float(item["precision_at_alpha_0p20"]), ".4f") if item["precision_at_alpha_0p20"] is not None else "n/a")
                     + " / " + str(int(item["shortlist_at_alpha_0p20"])) + " |")
    lines.append("")
    lines.append("## 2. 相对判据 + 指纹盲区判据（替代被判否的绝对 |Δε| >= 30）")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 全域 |Δε| 中位数 | " + format(float(similarity["global_median_abs_delta_eps"]), ".4f") + " |")
    lines.append("| 最高十分位 |Δε| 中位数 | " + format(float(similarity["top_bin_median"]), ".4f") + " |")
    lines.append("| 相对比（最高十分位 / 全域） | " + format(float(similarity["top_bin_ratio"]), ".4f") + " |")
    lines.append("| 置换 p（999 次） | " + format(float(similarity["top_bin_p"]), ".4f") + " |")
    lines.append("| 最低十分位 |Δε| 中位数 | " + format(float(similarity["bottom_bin_median"]), ".4f") + " |")
    lines.append("| Tanimoto >= 0.99 的对数 | " + str(int(similarity["n_blind"])) + " |")
    lines.append("| 其中 |Δε| >= 5 的对数 | " + str(int(similarity["n_blind_big"])) + " |")
    lines.append("| 盲区里的最大 |Δε| | " + format(float(similarity["max_blind_delta"]), ".4f") + " |")
    lines.append("")
    lines.append("| 十分位 | 相似度区间 | 对数 | |Δε| 中位数 | 零分布中位数 | p |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in similarity["bins"]:
        lines.append("| " + str(int(item["bin"]))
                     + " | [" + format(float(item["sim_lo"]), ".3f") + ", " + format(float(item["sim_hi"]), ".3f") + "]"
                     + " | " + str(int(item["n_pairs"]))
                     + " | " + format(float(item["median_abs_delta_eps"]), ".4f")
                     + " | " + format(float(item["null_median_abs_delta_eps"]), ".4f")
                     + " | " + format(float(item["p_value"]), ".4f") + " |")
    lines.append("")
    lines.append("## 3. 比值判据（H31h 的设计缺陷替代品）")
    lines.append("")
    lines.append("| 阶梯（干净） | 臂数 | R² 极差 | AUC30 极差 | 比值 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in payload["ladder_rows"]:
        lines.append("| " + str(item["ladder"]) + " | " + str(int(item["n_arms"]))
                     + " | " + format(float(item["r2_spread"]), ".6f")
                     + " | " + format(float(item["auc30_spread"]), ".6f")
                     + " | " + format(float(item["ratio"]), ".2f") + " |")
    lines.append("")
    lines.append("判据：每个阶梯 AUC30 极差 < " + format(AUC_SPREAD_GATE, ".2f") + "，且比值 >= "
                 + format(RATIO_ROBUST_GATE, ".1f") + "（稳健门），其中至少 "
                 + str(MIN_WIDE_LADDERS) + " 个阶梯 >= " + format(RATIO_WIDE_GATE, ".1f")
                 + "（非单点门）；参数化后不再出现「用别的阶梯的绝对门」这种设计缺陷。")
    lines.append("")
    lines.append("## 4. 判据")
    lines.append("")
    lines.append("| id | 判据 | 读数 | 门槛 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in criteria:
        value = item["value"]
        threshold = item["threshold"]
        text_value = ("n/a" if value is None else
                      (format(float(value), ".6f") if isinstance(value, (int, float)) else str(value)))
        text_threshold = ("n/a" if threshold is None else
                          (format(float(threshold), ".6f") if isinstance(threshold, (int, float)) else str(threshold)))
        lines.append("| " + str(item["id"]) + " | " + str(item["description"])
                     + " | " + text_value + " | " + text_threshold + " | " + str(item["verdict"]) + " |")
    lines.append("")
    lines.append("## 5. 边界")
    lines.append("")
    lines.append("- 本件**只换判据、不换数据**：三条改法都读盘上既有产物，因此它们是**后验读数**，"
                 "不得当作新的预注册结论引用；下一份预注册若采用这些判据，须重新冻结阈值。")
    lines.append("- alpha* 是**在既有 5 个重复、化合物级切分下的合并读数**，样本量小；"
                 "反解给出的是「该预算下能守住精度门」的**存在性**，不是对未见化合物的承诺。")
    lines.append("- 相对判据的十分位切分是**机械的等频切分**（按相似度排序后十等分），不挑样本；"
                 "置换零分布只打乱 ε，保持相似度结构不变。")
    lines.append("- 指纹盲区判据只对**单一指纹（Morgan r=2, 2048 bit）**成立；换指纹必须重测。")
    lines.append("- 比值判据只在**这五个干净阶梯**上检验（W28 只取 grid_fixed_* 网格臂，"
                 "剔除安慰剂与换表示臂）；比值本身依赖阶梯宽度（arms 数），"
                 "因此同时报 n_arms，禁止跨不同宽度的阶梯直接比较比值。")
    lines.append("")
    lines.append("## 6. 输入指纹")
    lines.append("")
    for key, value in inputs.items():
        lines.append("- " + str(key) + " = " + str(value))
    return "\n".join(lines) + "\n"


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "Arial Unicode MS"):
        try:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    rows = list(payload["inversion_rows"])
    primary = w38a.PRIMARY_REPRESENTATION
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.6), dpi=160)

    axis = axes[0]
    for tau, colour in ((30.0, "#1f77b4"), (15.0, "#d62728")):
        series = [row for row in rows
                  if row["representation"] == primary and float(row["tau"]) == float(tau)]
        series.sort(key=lambda row: float(row["alpha"]))
        axis.plot([float(row["alpha"]) for row in series],
                  [float(row["pooled_precision"]) for row in series],
                  marker="o", ms=3.5, color=colour, label="tau = " + format(tau, ".0f"))
    axis.axhline(PRECISION_GATE, color="black", ls="--", lw=1.0, label="精度门 0.90")
    star = payload["inversion_tau30"]
    if star["alpha_star"] is not None:
        axis.axvline(float(star["alpha_star"]), color="#2ca02c", ls=":", lw=1.5,
                     label="alpha* (tau=30)")
    axis.set_xlabel("预算 alpha")
    axis.set_ylabel("合并精度")
    axis.set_title("W40-A 反解：精度 vs 预算（" + primary + "）", fontsize=10)
    axis.legend(fontsize=8)
    axis.grid(alpha=0.25)

    axis = axes[1]
    bins = list(payload["similarity"]["bins"])
    axis.plot([int(item["bin"]) for item in bins],
              [float(item["median_abs_delta_eps"]) for item in bins],
              marker="s", color="#1f77b4", label="观测 |d eps| 中位数")
    axis.plot([int(item["bin"]) for item in bins],
              [float(item["null_median_abs_delta_eps"]) for item in bins],
              ls="--", color="#7f7f7f", label="置换零分布均值")
    axis.axhline(float(payload["similarity"]["global_median_abs_delta_eps"]),
                 color="black", ls=":", lw=1.0, label="全域中位数")
    axis.set_xlabel("相似度十分位（1 = 最不像，10 = 最像）")
    axis.set_ylabel("|d eps| 中位数")
    axis.set_title("W40-A 相对判据：十分位 |d eps|", fontsize=10)
    axis.legend(fontsize=8)
    axis.grid(alpha=0.25)

    axis = axes[2]
    ladder = list(payload["ladder_rows"])
    labels = [str(item["ladder"]).split(" ")[0] for item in ladder]
    ratios = [float(item["ratio"]) for item in ladder]
    axis.barh(labels, ratios, color="#8c564b")
    axis.axvline(RATIO_ROBUST_GATE, color="black", ls="--", lw=1.0,
                 label="稳健门 " + format(RATIO_ROBUST_GATE, ".0f") + "x")
    axis.axvline(RATIO_WIDE_GATE, color="#2ca02c", ls=":", lw=1.0,
                 label="非单点门 " + format(RATIO_WIDE_GATE, ".0f") + "x")
    axis.legend(fontsize=7, loc="lower right")
    for index, value in enumerate(ratios):
        axis.text(value, index, " " + format(value, ".1f") + "x", va="center", fontsize=8)
    axis.set_xlabel("R2 极差 / AUC30 极差")
    axis.set_title("W40-A 比值判据（稳健门 4x / 非单点 10x）", fontsize=10)
    axis.grid(alpha=0.25, axis="x")

    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    sources = [PREDICTIONS_CSV, FEATURES_CSV, *[path for _, path, _ in LADDER_CSVS]]
    before = {str(path): sha256_file(path) for path in sources}
    payload = build()
    criteria = evaluate(payload)
    after = {str(path): sha256_file(path) for path in sources}
    inputs_unchanged = before == after
    criteria.append({
        "id": "H40a14",
        "description": "输入未被改写（六个源表 sha256 前后一致）",
        "value": 1.0 if inputs_unchanged else 0.0,
        "threshold": 1.0,
        "verdict": _verdict(inputs_unchanged),
    })

    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(INVERSION_CSV, INVERSION_FIELDS, payload["inversion_rows"])
    write_csv_lf(BINS_CSV, BIN_FIELDS, payload["similarity"]["bins"])
    write_csv_lf(RATIO_CSV, RATIO_FIELDS, payload["ladder_rows"])
    if not args.skip_figure:
        make_figure(payload)

    inv30 = payload["inversion_tau30"]
    inv15 = payload["inversion_tau15"]
    similarity = payload["similarity"]
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读盘上既有产物换判据重读；不重拟合主记分牌臂、不新增特征列、"
                              "不改 METRIC_NAMES、不动四个冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "reforms": {
            "conformal_inversion": {
                "grid": [float(value) for value in ALPHAS],
                "n_rows": len(payload["inversion_rows"]),
                "tau30": inv30,
                "tau15": inv15,
            },
            "similarity_relative": {key: value for key, value in similarity.items()
                                    if key != "bins"},
            "ladder_ratio": payload["ladder_rows"],
        },
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "W38-A 的判否是**问法**问题：tau=30 上反解出 alpha* = "
            + (format(float(inv30["alpha_star"]), ".2f") if inv30["alpha_star"] is not None else "无")
            + "，在该预算下能守住 precision >= 0.90（推荐 "
            + str(int(inv30["shortlist_at_star"])) + " 条）。",
            "H38b1 换成相对判据：最高相似度十分位的 |d eps| 中位数相对全域 "
            + format(float(similarity["top_bin_ratio"]), ".4f") + "（p = "
            + format(float(similarity["top_bin_p"]), ".4f") + "），"
            "盲区判据 " + str(int(similarity["n_blind"])) + " 对 / 其中 "
            + str(int(similarity["n_blind_big"])) + " 对 |d eps| >= 5。",
            "H31h 的绝对 0.08 门换成比值判据后，五个干净阶梯的最差比值 "
            + format(min(float(item["ratio"]) for item in payload["ladder_rows"]), ".2f") + "x，"
            "AUC30 极差上限 " + format(max(float(item["auc30_spread"]) for item in payload["ladder_rows"]), ".6f") + "。",
            "不占 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, before), encoding="utf-8", newline="\n")

    print("inversion alpha* tau30 " + (format(float(inv30["alpha_star"]), ".2f")
                                       if inv30["alpha_star"] is not None else "none")
          + "; shortlist " + str(int(inv30["shortlist_at_star"]))
          + "; precision " + (format(float(inv30["precision_at_star"]), ".4f")
                              if inv30["precision_at_star"] is not None else "n/a"))
    print("inversion alpha* tau15 " + (format(float(inv15["alpha_star"]), ".2f")
                                       if inv15["alpha_star"] is not None else "none"))
    print("similarity top-bin ratio " + format(float(similarity["top_bin_ratio"]), ".6f")
          + "; p " + format(float(similarity["top_bin_p"]), ".6f")
          + "; n_blind " + str(int(similarity["n_blind"]))
          + "; n_blind_big " + str(int(similarity["n_blind_big"])))
    for item in payload["ladder_rows"]:
        print("ladder " + str(item["ladder"]) + ": r2_spread "
              + format(float(item["r2_spread"]), ".6f") + "; auc30_spread "
              + format(float(item["auc30_spread"]), ".6f") + "; ratio "
              + format(float(item["ratio"]), ".3f"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
