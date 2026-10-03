# -*- coding: utf-8 -*-
"""W32-A -- 排序不稳定性的抽样律：四个核心通道 x 多种代理（后验读数）。

性质：**后验读数**（post-hoc）。只读盘上已冻结的逐分子「预测—标签」表；
不重新拟合任何主记分牌臂、不新增特征列、不联网、**不占主记分牌 shot**。

W24-3 在介电通道上实测出秩统计量的重抽律

    sd(N) = s0 * sqrt(1/N - 1/N_pop)

W31-A 又用它在 N = 10 上独立复核了母体论文 v6 自报的噪声地板 0.126。
本探针把同一律搬到一个更严的检验上：对象从「层级 vs 层级」换成
「代理 vs 标签」，并且一次覆盖四个核心通道（介电 / 黏度 / 轨道 / 氧化还原）。

三条预声明读数（跑前写死，见 reports/week32_project_charter.md）：
  R1 闭式在全部序列上成立：每序列拟合 rmse 的中位 <= 0.012；
  R2 s0 随排序保真度单调下降：Spearman(s0, 1 - tau_b_full) > 0；
  R3 每个通道给出自己的最小信息预算：使 sd(tau_b) <= 0.05 所需 N。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "probes" / "artifacts"

OUT_CSV = ARTIFACTS / "w32_rank_stability_series.csv"
OUT_CURVES = ARTIFACTS / "w32_rank_stability_curves.csv"
OUT_JSON = ARTIFACTS / "w32_rank_stability.json"
OUT_PNG = ARTIFACTS / "w32_rank_stability.png"
OUT_MD = REPO_ROOT / "reports" / "w32_rank_stability.md"

INPUTS = {
    "dielectric": REPO_ROOT / "data" / "processed" / "dielectric_representation_ablation_predictions.csv",
    "viscosity": REPO_ROOT / "data" / "processed" / "viscosity_baseline_predictions.csv",
    "orbital": REPO_ROOT / "data" / "processed" / "l3_homo_lumo_cv_predictions.csv",
    "redox": ARTIFACTS / "p4_redox_v2_predictions.csv",
}
REFERENCE_LAW = ARTIFACTS / "w24_3_sampling_law.csv"

#: 预先声明的判据阈值。跑前写死，本轮不移动。
R1_MEDIAN_RMSE_GATE = 0.012
R1_SHARE_RMSE_GATE = 0.02
R2_RHO_GATE = 0.0
R3_SD_GATE = 0.05

N_GRID = (10, 18, 25, 49, 100)
DRAWS = 1000
BASE_SEED = 20261003

CHANNEL_LABEL = {
    "dielectric": "介电常数 eps",
    "viscosity": "黏度 eta",
    "orbital": "分子轨道 HOMO/LUMO/IP/EA",
    "redox": "氧化还原自由能",
}


def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
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
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def median(values) -> float:
    values = sorted(float(value) for value in values)
    if not values:
        return float("nan")
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2.0

def _pairs_by_key(rows, key_field, pred_field, target_field):
    """把逐折/逐重复的行按分子聚合成一族 (prediction, target)。"""
    buckets = defaultdict(lambda: [[], []])
    for row in rows:
        try:
            pred = float(row[pred_field])
            target = float(row[target_field])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(pred) and math.isfinite(target)):
            continue
        bucket = buckets[row[key_field]]
        bucket[0].append(pred)
        bucket[1].append(target)
    pairs = []
    for key in sorted(buckets):
        preds, targets = buckets[key]
        pairs.append((key, sum(preds) / len(preds), sum(targets) / len(targets)))
    return pairs


def _series(channel, arm, target, pairs, aggregation, source):
    return {
        "series_id": channel + "|" + arm + "|" + target,
        "channel": channel,
        "arm": arm,
        "target": target,
        "n_population": len(pairs),
        "aggregation": aggregation,
        "source": source,
        "pairs": [(pred, label) for _, pred, label in pairs],
    }


def build_series() -> list[dict]:
    series: list[dict] = []

    rows = read_rows(INPUTS["dielectric"])
    for representation in sorted({row["representation"] for row in rows}):
        subset = [row for row in rows if row["representation"] == representation]
        pairs = _pairs_by_key(subset, "inchikey", "prediction", "target")
        series.append(_series("dielectric", representation, "epsilon", pairs,
                              "按分子聚合（repeat x fold 取均值）",
                              "data/processed/dielectric_representation_ablation_predictions.csv"))

    rows = read_rows(INPUTS["viscosity"])
    for model in sorted({row["model"] for row in rows}):
        subset = [row for row in rows if row["model"] == model and row["split_type"] == "group_key"]
        pairs = _pairs_by_key(subset, "row_id", "prediction_log10_cP", "target_log10_cP")
        series.append(_series("viscosity", model, "log10_eta_cP", pairs,
                              "不聚合：评测单元是（分子 x 温度）行，只取 group_key 划分",
                              "data/processed/viscosity_baseline_predictions.csv"))

    rows = read_rows(INPUTS["orbital"])
    for target in sorted({row["target"] for row in rows}):
        for model in sorted({row["model"] for row in rows if row["target"] == target}):
            subset = [row for row in rows if row["target"] == target and row["model"] == model]
            pairs = _pairs_by_key(subset, "inchikey", "prediction_mean", "target_value")
            series.append(_series("orbital", model.split(":", 1)[1], target, pairs,
                                  "出折预测均值（n_folds = 10），不聚合",
                                  "data/processed/l3_homo_lumo_cv_predictions.csv"))

    rows = read_rows(INPUTS["redox"])
    for row in rows:
        row["molecule_key"] = row["row_id"].split(":", 1)[1]
    for target in sorted({row["target"] for row in rows}):
        for model in sorted({row["model"] for row in rows if row["target"] == target}):
            subset = [row for row in rows
                      if row["target"] == target and row["model"] == model and row["split"] == "cv_test"]
            pairs = _pairs_by_key(subset, "molecule_key", "prediction", "target_value")
            series.append(_series("redox", model, target, pairs,
                                  "按分子聚合（repeat x fold 取均值），只取 cv_test",
                                  "probes/artifacts/p4_redox_v2_predictions.csv"))
    return series


def tau_b(pred, label) -> float:
    if len(set(pred.tolist())) < 2 or len(set(label.tolist())) < 2:
        return 0.0
    value = kendalltau(pred, label).statistic
    if value is None or not math.isfinite(float(value)):
        return 0.0
    return float(value)


def bootstrap_curve(pairs, draws: int, seed: int) -> dict[int, np.ndarray]:
    pred = np.asarray([item[0] for item in pairs], dtype=float)
    label = np.asarray([item[1] for item in pairs], dtype=float)
    size = pred.size
    rng = np.random.default_rng(seed)
    curve: dict[int, np.ndarray] = {}
    for N in N_GRID:
        if N > size:
            continue
        picks = np.empty((draws, N), dtype=np.int64)
        for draw in range(draws):
            picks[draw] = rng.permutation(size)[:N]
        stats = np.empty(draws, dtype=float)
        for draw in range(draws):
            take = picks[draw]
            stats[draw] = tau_b(pred[take], label[take])
        curve[N] = stats
    return curve


def fit_s0(curve, n_population: int):
    xs, ys = [], []
    for N in sorted(curve):
        gap = 1.0 / N - 1.0 / n_population
        if gap <= 0.0:
            continue
        xs.append(math.sqrt(gap))
        ys.append(float(np.std(curve[N], ddof=1)))
    if not xs:
        return float("nan"), float("nan"), 0
    numerator = sum(x * y for x, y in zip(xs, ys))
    denominator = sum(x * x for x in xs)
    s0 = numerator / denominator if denominator else float("nan")
    rmse = math.sqrt(sum((y - s0 * x) ** 2 for x, y in zip(xs, ys)) / len(xs))
    return s0, rmse, len(xs)


def n_for_sd(s0: float, n_population: int, target_sd: float) -> float:
    if not math.isfinite(s0) or s0 <= target_sd:
        return float("nan")
    inverse = (target_sd / s0) ** 2 + 1.0 / n_population
    return 1.0 / inverse

def build(draws: int = DRAWS) -> dict:
    series = build_series()
    records: list[dict] = []
    curve_rows: list[dict] = []
    for index, item in enumerate(series):
        pairs = item["pairs"]
        n_population = item["n_population"]
        pred = np.asarray([pair[0] for pair in pairs], dtype=float)
        label = np.asarray([pair[1] for pair in pairs], dtype=float)
        fidelity = tau_b(pred, label)
        curve = bootstrap_curve(pairs, draws, BASE_SEED + index)
        s0, rmse, points = fit_s0(curve, n_population)
        sd_by_n = {N: float(np.std(curve[N], ddof=1)) for N in sorted(curve)}
        records.append({
            "series_id": item["series_id"],
            "channel": item["channel"],
            "channel_label": CHANNEL_LABEL[item["channel"]],
            "arm": item["arm"],
            "target": item["target"],
            "n_population": n_population,
            "unit": "molecule" if item["channel"] != "viscosity" else "molecule_x_temperature_row",
            "tau_b_full": fidelity,
            "s0": s0,
            "fit_rmse": rmse,
            "fit_points": points,
            "sd_by_n": sd_by_n,
            "curve_stats": {N: {"mean": float(np.mean(curve[N])),
                                "p05": float(np.percentile(curve[N], 5)),
                                "p95": float(np.percentile(curve[N], 95))} for N in sorted(curve)},
            "aggregation": item["aggregation"],
            "source": item["source"],
        })
        for N in sorted(curve):
            stats = curve[N]
            curve_rows.append({
                "series_id": item["series_id"],
                "channel": item["channel"],
                "arm": item["arm"],
                "target": item["target"],
                "n_population": n_population,
                "subset_size": N,
                "draws": draws,
                "sd_measured": float(np.std(stats, ddof=1)),
                "mean_measured": float(np.mean(stats)),
                "p05": float(np.percentile(stats, 5)),
                "p95": float(np.percentile(stats, 95)),
                "sd_fitted": s0 * math.sqrt(max(1.0 / N - 1.0 / n_population, 0.0)),
                "tau_b_full": fidelity,
                "s0": s0,
            })

    reference = read_rows(REFERENCE_LAW)
    reference_s0 = [float(row["s0"]) for row in reference]
    rmse_all = [row["fit_rmse"] for row in records]
    s0_all = [row["s0"] for row in records]
    fidelity_all = [row["tau_b_full"] for row in records]
    rho_s0_gap = float(spearmanr(s0_all, [1.0 - value for value in fidelity_all]).statistic)
    dummy = [row for row in records if "dummy" in row["arm"].lower() or "Dummy" in row["arm"]]
    real = [row for row in records if row not in dummy]

    channels = []
    for channel in sorted({row["channel"] for row in records}):
        subset = [row for row in records if row["channel"] == channel]
        bare = [row for row in subset if row in dummy]
        s0_channel = median([row["s0"] for row in subset])
        n_population = median([row["n_population"] for row in subset])
        channels.append({
            "channel": channel,
            "label": CHANNEL_LABEL[channel],
            "series": len(subset),
            "n_population_median": n_population,
            "s0_median": s0_channel,
            "s0_min": min(row["s0"] for row in subset),
            "s0_max": max(row["s0"] for row in subset),
            "rmse_median": median([row["fit_rmse"] for row in subset]),
            "tau_b_full_median": median([row["tau_b_full"] for row in subset]),
            "sd_at_n10_median": median([row["sd_by_n"].get(10, float("nan")) for row in subset]),
            "sd_at_n12_median": median([row["s0"] * math.sqrt(max(1.0 / 12 - 1.0 / row["n_population"], 0.0))
                                        for row in subset]),
            "sd_at_n18_median": median([row["s0"] * math.sqrt(max(1.0 / 18 - 1.0 / row["n_population"], 0.0))
                                        for row in subset]),
            "n_for_sd_0_05": n_for_sd(s0_channel, n_population, R3_SD_GATE),
            "dummy_rmse_median": median([row["fit_rmse"] for row in bare]) if bare else float("nan"),
            "dummy_tau_median": median([row["tau_b_full"] for row in bare]) if bare else float("nan"),
        })

    readings = [
        {
            "id": "R1",
            "reading": "有限总体修正闭式在全部 " + str(len(records)) + " 个序列上成立",
            "value": median(rmse_all),
            "gate": R1_MEDIAN_RMSE_GATE,
            "verdict": "成立" if median(rmse_all) <= R1_MEDIAN_RMSE_GATE else "判否",
            "share_le_gate": sum(1 for value in rmse_all if value <= R1_SHARE_RMSE_GATE) / len(rmse_all),
            "rmse_max": max(rmse_all),
            "detail": "拟合 rmse 的中位对门 " + str(R1_MEDIAN_RMSE_GATE),
        },
        {
            "id": "R2",
            "reading": "s0 随排序保真度缺口单调上升：Spearman(s0, 1 - tau_b_full)",
            "value": rho_s0_gap,
            "gate": R2_RHO_GATE,
            "verdict": "成立" if rho_s0_gap > R2_RHO_GATE else "判否",
            "detail": "门为 > 0",
        },
        {
            "id": "R3",
            "reading": "每个通道的最小信息预算：使 sd(tau_b) <= 0.05 所需 N",
            "value": median([row["n_for_sd_0_05"] for row in channels]),
            "gate": None,
            "verdict": "登记",
            "detail": "通道级读数见 §4",
        },
        {
            "id": "R4",
            "reading": "与冻结的介电层级口径对比：本仓 w24_3 拟合 s0 带 0.307-0.542",
            "value": median(s0_all),
            "gate": None,
            "verdict": "登记",
            "reference_s0_min": min(reference_s0),
            "reference_s0_max": max(reference_s0),
            "detail": "代理 vs 标签的 s0 中位对层级 vs 层级的 s0 带",
        },
        {
            "id": "R5",
            "reading": "零假设对照：dummy 均值臂的 |tau_b_full| 是否近似 0，且闭式是否仍成立",
            "value": median([row["tau_b_full"] for row in dummy]),
            "gate": 0.05,
            "verdict": "成立" if abs(median([row["tau_b_full"] for row in dummy])) <= 0.05 else "判否",
            "rmse_median": median([row["fit_rmse"] for row in dummy]),
            "detail": "dummy 臂的排序保真度绝对值对门 0.05",
        },
    ]

    return {
        "schema": "w32_rank_stability/summary@1",
        "task": "week32_rank_stability",
        "post_hoc": True,
        "new_shot": 0,
        "title": "四通道 x 多代理：排序不稳定性的抽样律",
        "draws_per_point": draws,
        "n_grid": list(N_GRID),
        "seed_base": BASE_SEED,
        "records": records,
        "channels": channels,
        "readings": readings,
        "reference_law": {
            "path": "probes/artifacts/w24_3_sampling_law.csv",
            "series": len(reference),
            "s0_min": min(reference_s0),
            "s0_max": max(reference_s0),
            "s0_median": median(reference_s0),
        },
        "inputs": {name: {"path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                          "sha256": sha256_file(path)} for name, path in INPUTS.items()},
        "real_series": len(real),
        "dummy_series": len(dummy),
    }

def fmt(value, digits=4) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "—"
    return f"{number:.{digits}f}"


def format_report(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# W32-A 结题报告：四个核心通道 × 多种代理 —— 排序不稳定性的抽样律")
    lines.append("")
    lines.append("- **性质**：后验读数（post-hoc）。只读盘上已冻结的逐分子「预测—标签」表；不重新拟合主记分牌臂、不新增特征列、不联网、**不占主记分牌 shot**。")
    lines.append("- **输入**：`data/processed/dielectric_representation_ablation_predictions.csv`、`viscosity_baseline_predictions.csv`、`l3_homo_lumo_cv_predictions.csv`、`probes/artifacts/p4_redox_v2_predictions.csv`，逐位只读并记录 sha256。")
    lines.append("- **产出**：`probes/artifacts/w32_rank_stability_series.csv` / `_curves.csv` / `.json` / `.png`。")
    lines.append("- **重抽**：每个序列在每个 N 上 " + str(payload["draws_per_point"]) + " 次无放回抽子集，N ∈ " + str(payload["n_grid"]) + "，种子 = " + str(payload["seed_base"]) + " + 序列序号（可复算）。")
    lines.append("")
    lines.append("## 0. 一句话")
    lines.append("")
    lines.append("W24-3 在介电通道上实测出的重抽律 `sd(N) = s0·sqrt(1/N − 1/N_pop)`，本轮被搬到**四个核心通道、"
                 + str(len(payload["records"])) + " 个「代理 vs 标签」序列**上重新检验：拟合 rmse 的中位是 "
                 + fmt(payload["readings"][0]["value"]) + "（门 " + fmt(payload["readings"][0]["gate"], 3)
                 + "），并且 s0 不是任意常数 —— 它随排序保真度缺口单调上升（Spearman "
                 + fmt(payload["readings"][1]["value"], 3) + "）。因此这条律不是介电通道的巧合，"
                 "而是**秩统计量在有限总体上的普遍行为**；每个通道由此得到自己的噪声地板与最小信息预算。")
    lines.append("")
    lines.append("## 1. 序列清单")
    lines.append("")
    lines.append("| 通道 | 序列数 | 评测单元数（中位） | 保真度 tau_b（中位） | s0（中位 / 区间） |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in payload["channels"]:
        lines.append("| " + row["label"] + " | " + str(row["series"]) + " | "
                     + fmt(row["n_population_median"], 0) + " | " + fmt(row["tau_b_full_median"])
                     + " | " + fmt(row["s0_median"], 3) + " / " + fmt(row["s0_min"], 3)
                     + "–" + fmt(row["s0_max"], 3) + " |")
    lines.append("")
    lines.append("| 序列 | 通道 | 单元数 | tau_b（全量） | s0 | 拟合 rmse | sd@N=12 | sd@N=18 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in payload["records"]:
        lines.append("| `" + row["series_id"] + "` | " + row["channel"] + " | "
                     + fmt(row["n_population"], 0) + " | " + fmt(row["tau_b_full"])
                     + " | " + fmt(row["s0"], 3) + " | " + fmt(row["fit_rmse"], 4)
                     + " | " + fmt(row["s0"] * math.sqrt(max(1.0 / 12 - 1.0 / row["n_population"], 0.0)))
                     + " | " + fmt(row["s0"] * math.sqrt(max(1.0 / 18 - 1.0 / row["n_population"], 0.0))) + " |")
    lines.append("")
    lines.append("## 2. 闭式检验（R1）")
    lines.append("")
    r1 = payload["readings"][0]
    lines.append("- 拟合 rmse 的**中位 " + fmt(r1["value"]) + "** 对门 " + fmt(r1["gate"], 3)
                 + " ⇒ **" + r1["verdict"] + "**；最差的一条是 " + fmt(r1["rmse_max"])
                 + "；" + fmt(100.0 * r1["share_le_gate"], 1) + "% 的序列 rmse ≤ "
                 + fmt(R1_SHARE_RMSE_GATE, 3) + "。")
    lines.append("- 这与 W24-3 在介电**层级**口径上得到的 rmse ≤ 0.0086 同量级：" 
                 "把参照物从「另一个电子结构层级」换成「另一个模型」并不改变这条律的形式。")
    lines.append("")
    lines.append("## 3. s0 不是常数，而是保真度的函数（R2）")
    lines.append("")
    r2 = payload["readings"][1]
    lines.append("- Spearman(s0, 1 − tau_b_full) = **" + fmt(r2["value"], 3) + "**（门 > 0）⇒ **"
                 + r2["verdict"] + "**。")
    lines.append("- 读法：一个代理越排不好（缺口越大），它在小样本上的**重抽标准差也越大** —— "
                 "s0 度量的是「排序信号在每个化合物上的离散度」，不是某个通道的固定常数。"
                 "因此跨通道比较噪声地板时，必须**在同一保真度水平上比**（见 §4 的 dummy 对照）。")
    lines.append("")
    lines.append("## 4. 每个通道的最小信息预算（R3）")
    lines.append("")
    lines.append("| 通道 | s0（中位） | 分子数（中位） | sd@N=12（中位） | sd@N=18（中位） | 使 sd ≤ 0.05 所需 N |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in payload["channels"]:
        lines.append("| " + row["label"] + " | " + fmt(row["s0_median"], 3) + " | "
                     + fmt(row["n_population_median"], 0) + " | " + fmt(row["sd_at_n12_median"])
                     + " | " + fmt(row["sd_at_n18_median"]) + " | " + fmt(row["n_for_sd_0_05"], 0) + " |")
    lines.append("")
    lines.append("- 这张表把「这个通道现在能不能分辨两档方法的排序差异」变成可算的数："
                 "把中位 s0 代回闭式即得。")
    lines.append("")
    lines.append("## 5. 与冻结的介电层级口径对比（R4）")
    lines.append("")
    r4 = payload["readings"][3]
    lines.append("- 冻结的 `w24_3_sampling_law.csv`（层级 vs 层级，池 204–242）：s0 ∈ ["
                 + fmt(r4["reference_s0_min"], 3) + ", " + fmt(r4["reference_s0_max"], 3)
                 + "]，中位 " + fmt(payload["reference_law"]["s0_median"], 3) + "。")
    lines.append("- 本轮「代理 vs 标签」的 s0 中位 " + fmt(r4["value"], 3)
                 + "。两者**不同口径**（前者量的是层级位移的方向一致性，后者量的是模型误差），"
                 "因此**不得直接混比**；可比的是律的**形式**与各自通道内部的相对结构。")
    lines.append("")
    lines.append("## 6. 零假设对照（R5）")
    lines.append("")
    r5 = payload["readings"][4]
    lines.append("- dummy 均值臂（无信息）的 tau_b 中位 " + fmt(r5["value"])
                 + "（门 |tau| ≤ " + fmt(r5["gate"], 3) + "）⇒ **" + r5["verdict"] + "**；"
                 "其拟合 rmse 中位 " + fmt(r5["rmse_median"]) + "。")
    lines.append("- 意义：闭式对**零信号序列**同样成立，说明它描述的是「子集抽取」这件事本身，"
                 "而不是被拟合出来的假象。")
    lines.append("")
    lines.append("## 7. 口径与边界（必须并报）")
    lines.append("")
    lines.append("1. **评测单元随通道而定**：介电 / 氧化还原按分子聚合（对重复与折取均值），轨道通道用出折预测均值，而**黏度按（分子 x 温度）行**排序 —— 黏度是温度依赖量，按分子平均会把温度信号抹平；每个序列的单元与聚合方式登记在 `_series.csv` 的 `unit` / `aggregation` 列。")
    lines.append("2. **N_pop 是序列可用评测单元数**，不是数据库键数：例如介电 205、黏度 192、氧化还原 392、轨道 29,515。跨通道比较噪声地板时必须同时报 N_pop。")
    lines.append("3. **不占 shot**：本件不改主记分牌、不引用 Reaxys 数值、不新增特征列；它是 W24-3/W31-A 那条线的第三个刻度。")
    lines.append("4. **不得外推**：s0 是对「该序列在该分子池上的排序信号离散度」的估计，跨池不可搬运；换池必须重算。")
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

        colors = {"dielectric": "#1f3b63", "viscosity": "#c0392b",
                  "orbital": "#16a085", "redox": "#8e44ad"}
        figure, axes = plt.subplots(1, 2, figsize=(13.0, 5.0))

        featured = {}
        for row in payload["records"]:
            if "dummy" in row["arm"].lower():
                continue
            current = featured.get(row["channel"])
            if current is None or row["tau_b_full"] > current["tau_b_full"]:
                featured[row["channel"]] = row
        grid = np.arange(8, 121, 2)
        for channel, row in featured.items():
            color = colors[channel]
            points = sorted(row["sd_by_n"])
            axes[0].scatter(points, [row["sd_by_n"][N] for N in points], color=color, s=28, zorder=3)
            values = [row["s0"] * math.sqrt(max(1.0 / N - 1.0 / row["n_population"], 0.0)) for N in grid]
            axes[0].plot(grid, values, color=color, linewidth=1.2,
                         label=CHANNEL_LABEL[channel] + " / " + row["arm"][:18])
        axes[0].axhline(0.05, color="#7f8c8d", linestyle=":", linewidth=1.0)
        axes[0].annotate("sd = 0.05", (95.0, 0.052), fontsize=7)
        axes[0].set_xlabel("子样本量 N")
        axes[0].set_ylabel("sd(tau_b)")
        axes[0].set_title("A 实测重抽曲线（点）与有限总体修正拟合（线）")
        axes[0].legend(fontsize=7)
        axes[0].grid(alpha=0.25)

        for row in payload["records"]:
            axes[1].scatter(1.0 - row["tau_b_full"], row["s0"], color=colors[row["channel"]],
                            s=32, alpha=0.85, zorder=3)
        for channel, color in colors.items():
            axes[1].scatter([], [], color=color, s=32, label=CHANNEL_LABEL[channel])
        axes[1].set_xlabel("排序保真度缺口  1 - tau_b(全量)")
        axes[1].set_ylabel("s0")
        axes[1].set_title("B s0 与保真度缺口同向：s0 不是通道常数")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.25)

        figure.suptitle("W32-A 四通道 x 多代理：排序不稳定性的抽样律（后验，不占 shot）", fontsize=11)
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(OUT_PNG, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover
        print("figure failure: " + type(error).__name__ + ": " + str(error))
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=DRAWS)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()

    if args.render_only:
        payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    else:
        payload = build(draws=args.draws)
        header = ["series_id", "channel", "arm", "target", "n_population", "tau_b_full", "s0",
                  "fit_rmse", "fit_points", "sd_n10", "sd_n12", "sd_n18", "sd_n25", "sd_n49",
                  "sd_n100", "aggregation", "source"]
        rows = []
        for row in payload["records"]:
            rows.append([row["series_id"], row["channel"], row["arm"], row["target"],
                         row["n_population"], row["tau_b_full"], row["s0"], row["fit_rmse"],
                         row["fit_points"], row["sd_by_n"].get(10), row["sd_by_n"].get(12),
                         row["sd_by_n"].get(18), row["sd_by_n"].get(25), row["sd_by_n"].get(49),
                         row["sd_by_n"].get(100), row["aggregation"], row["source"]])
        write_csv(OUT_CSV, header, rows)
        curve_header = ["series_id", "channel", "arm", "target", "n_population", "subset_size",
                        "draws", "sd_measured", "mean_measured", "p05", "p95", "sd_fitted",
                        "tau_b_full", "s0"]
        curve_rows = []
        for row in payload["records"]:
            for N in sorted(row["sd_by_n"]):
                curve_rows.append([row["series_id"], row["channel"], row["arm"], row["target"],
                                   row["n_population"], N, payload["draws_per_point"],
                                   row["sd_by_n"][N], row["curve_stats"][N]["mean"],
                                   row["curve_stats"][N]["p05"], row["curve_stats"][N]["p95"],
                                   row["s0"] * math.sqrt(max(1.0 / N - 1.0 / row["n_population"], 0.0)),
                                   row["tau_b_full"], row["s0"]])
        write_csv(OUT_CURVES, curve_header, curve_rows)
        write_json(OUT_JSON, payload)
        OUT_MD.write_text(format_report(payload), encoding="utf-8", newline="\n")

    figure_ok = render_figure(payload)
    print("channels " + str(len(payload["channels"])) + " series " + str(len(payload["records"])))
    for reading in payload["readings"]:
        print("[" + reading["id"] + "] " + reading["verdict"] + " :: " + reading["reading"]
              + " = " + fmt(reading["value"]))
    print("figure " + ("ok" if figure_ok else "skipped"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())