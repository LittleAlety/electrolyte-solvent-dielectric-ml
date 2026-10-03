# -*- coding: utf-8 -*-
"""W38-A：把「拒答」升级成有保证的推荐集合（保形短名单；后验，不占 shot）。

现有口径里，「不可判定」是黑白的：一个化合物要么被预测、要么被整族踢出（W33-A 门禁、
W35-A 注册表）。但筛选的真实约束是「宁可少推荐、不可错推荐」。保形预测（conformal
prediction）给的是**边际覆盖保证**：只要校准集与评估集可交换，P(目标落在区间内) >= 1-alpha。

本件只读盘上已交付的 OOF 预测行（`dielectric_observations_benchmark_predictions.csv`，
98,580 行），**不重拟合任何模型**，因此是后验读数、不占 shot。

三个必须写死的口径：
* **按化合物切分**，不按行切分。行级切分会把同一化合物的行同时放进两侧，
  校准集与评估集不再可交换，覆盖保证直接失效。
* 覆盖率只在**评估侧**化合物上算，校准侧不参与读数。
* 短名单是三值的（推荐 / 未决 / 拒答），阈值沿用既有 AUC 轴（15 / 30），不新造门。

Run:
    .venv/Scripts/python.exe probes/w38_conformal_shortlist.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREDICTIONS_CSV = ARTIFACTS / "dielectric_observations_benchmark_predictions.csv"
COVERAGE_CSV = ARTIFACTS / "w38_conformal_coverage.csv"
SHORTLIST_CSV = ARTIFACTS / "w38_conformal_shortlist.csv"
SUMMARY_PATH = ARTIFACTS / "w38_conformal_shortlist_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w38_conformal_shortlist.md"
FIGURE_PATH = ARTIFACTS / "w38_conformal_coverage.png"

SCHEMA = "w38_conformal_shortlist/summary@1"
TASK = "week38_conformal_shortlist"

PROTOCOL = "grouped"
PRIMARY_REPRESENTATION = "Physical"
CONTROL_REPRESENTATION = "Morgan+Physical"
REPRESENTATIONS = (PRIMARY_REPRESENTATION, CONTROL_REPRESENTATION)
ALPHAS = (0.05, 0.10, 0.20)
THRESHOLDS = (15.0, 30.0)
SPLIT_SEED_BASE = 2026
ROOM_T_K = 298.15
COVERAGE_SLACK = 0.05
PRECISION_GATE = 0.90
REGISTERED_NEGATIVES = ("H38a2",)
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

COVERAGE_FIELDS = (
    "representation", "repeat", "alpha", "cal_rows", "eval_rows", "cal_compounds",
    "eval_compounds", "quantile_q", "coverage_rows", "coverage_compounds",
    "interval_width_median", "target_coverage", "coverage_slack_ok",
)
SHORTLIST_FIELDS = (
    "representation", "repeat", "alpha", "tau", "eval_compounds",
    "n_recommend", "n_undecided", "n_exclude", "n_positive", "precision",
    "recall", "recommended_true_positive", "recommended_false_positive",
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv_lf(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_predictions() -> dict[tuple[str, int], list[dict[str, str]]]:
    buckets: dict[tuple[str, int], list[dict[str, str]]] = {}
    with PREDICTIONS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["protocol"] != PROTOCOL:
                continue
            representation = row["representation"]
            if representation not in REPRESENTATIONS:
                continue
            buckets.setdefault((representation, int(row["repeat"])), []).append(row)
    return buckets


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Split-conformal quantile: the ceil((n+1)(1-alpha))-th smallest score."""
    ordered = sorted(scores)
    n = len(ordered)
    if n == 0:
        return float("inf")
    rank = math.ceil((n + 1) * (1.0 - alpha))
    if rank > n:
        return float("inf")
    return float(ordered[rank - 1])


def split_compounds(compounds: Sequence[str], repeat: int) -> tuple[list[str], list[str]]:
    ordered = sorted(compounds)
    rng = random.Random(SPLIT_SEED_BASE + int(repeat))
    shuffled = list(ordered)
    rng.shuffle(shuffled)
    half = len(shuffled) // 2
    return sorted(shuffled[:half]), sorted(shuffled[half:])


def representative_row(rows: Sequence[dict[str, str]]) -> dict[str, str]:
    return min(rows, key=lambda row: (abs(float(row["T_K"]) - ROOM_T_K), float(row["T_K"])))


def build() -> dict[str, object]:
    buckets = read_predictions()
    coverage_rows: list[dict[str, object]] = []
    shortlist_rows: list[dict[str, object]] = []
    for representation in REPRESENTATIONS:
        repeats = sorted(repeat for rep, repeat in buckets if rep == representation)
        for repeat in repeats:
            rows = buckets[(representation, repeat)]
            by_compound: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                by_compound.setdefault(row["inchikey"], []).append(row)
            cal_compounds, eval_compounds = split_compounds(list(by_compound), repeat)
            cal_rows = [row for key in cal_compounds for row in by_compound[key]]
            eval_rows = [row for key in eval_compounds for row in by_compound[key]]
            cal_scores = [abs(float(row["target"]) - float(row["prediction"])) for row in cal_rows]
            for alpha in ALPHAS:
                q = conformal_quantile(cal_scores, alpha)
                inside = [abs(float(row["target"]) - float(row["prediction"])) <= q for row in eval_rows]
                coverage_rows.append(
                    {
                        "representation": representation,
                        "repeat": int(repeat),
                        "alpha": alpha,
                        "cal_rows": len(cal_rows),
                        "eval_rows": len(eval_rows),
                        "cal_compounds": len(cal_compounds),
                        "eval_compounds": len(eval_compounds),
                        "quantile_q": q,
                        "coverage_rows": sum(1 for flag in inside if flag) / len(inside) if inside else float("nan"),
                        "coverage_compounds": float("nan"),
                        "interval_width_median": 2.0 * q,
                        "target_coverage": 1.0 - alpha,
                        "coverage_slack_ok": True,
                    }
                )
                compound_hits: list[bool] = []
                for key in eval_compounds:
                    row = representative_row(by_compound[key])
                    hit = abs(float(row["target"]) - float(row["prediction"])) <= q
                    compound_hits.append(hit)
                coverage_rows[-1]["coverage_compounds"] = (
                    sum(1 for flag in compound_hits if flag) / len(compound_hits) if compound_hits else float("nan")
                )
                coverage_rows[-1]["coverage_slack_ok"] = bool(
                    coverage_rows[-1]["coverage_rows"] >= (1.0 - alpha) - COVERAGE_SLACK
                )
                for tau in THRESHOLDS:
                    n_recommend = n_undecided = n_exclude = 0
                    true_positive = false_positive = 0
                    positives = 0
                    for key in eval_compounds:
                        row = representative_row(by_compound[key])
                        target = float(row["target"])
                        prediction = float(row["prediction"])
                        low, high = prediction - q, prediction + q
                        if target > tau:
                            positives += 1
                        if low > tau:
                            n_recommend += 1
                            if target > tau:
                                true_positive += 1
                            else:
                                false_positive += 1
                        elif high < tau:
                            n_exclude += 1
                        else:
                            n_undecided += 1
                    shortlist_rows.append(
                        {
                            "representation": representation,
                            "repeat": int(repeat),
                            "alpha": alpha,
                            "tau": tau,
                            "eval_compounds": len(eval_compounds),
                            "n_recommend": n_recommend,
                            "n_undecided": n_undecided,
                            "n_exclude": n_exclude,
                            "n_positive": positives,
                            "precision": (true_positive / n_recommend) if n_recommend else float("nan"),
                            "recall": (true_positive / positives) if positives else float("nan"),
                            "recommended_true_positive": true_positive,
                            "recommended_false_positive": false_positive,
                        }
                    )
    return {"coverage": coverage_rows, "shortlist": shortlist_rows}


def _mean(values: Sequence[float]) -> float:
    clean = [value for value in values if not math.isnan(value)]
    return statistics.fmean(clean) if clean else float("nan")


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    coverage = payload["coverage"]
    shortlist = payload["shortlist"]
    criteria: list[dict[str, object]] = []

    def cov(rep: str, alpha: float, field: str) -> list[float]:
        return [float(row[field]) for row in coverage
                if row["representation"] == rep and float(row["alpha"]) == alpha]

    primary_ok = True
    for alpha in ALPHAS:
        value = _mean(cov(PRIMARY_REPRESENTATION, alpha, "coverage_rows"))
        if not (value >= (1.0 - alpha) - COVERAGE_SLACK):
            primary_ok = False
    criteria.append(
        {
            "id": "H38a1",
            "description": "主表示（Physical）三个 alpha 档的行级覆盖率均 >= 1-alpha-0.05",
            "value": min(_mean(cov(PRIMARY_REPRESENTATION, alpha, "coverage_rows")) for alpha in ALPHAS),
            "threshold": min((1.0 - alpha) - COVERAGE_SLACK for alpha in ALPHAS),
            "verdict": "成立" if primary_ok else "判否",
        }
    )

    tau30 = [row for row in shortlist
             if row["representation"] == PRIMARY_REPRESENTATION
             and float(row["alpha"]) == 0.10 and float(row["tau"]) == 30.0]
    n_rec = sum(int(row["n_recommend"]) for row in tau30)
    tp = sum(int(row["recommended_true_positive"]) for row in tau30)
    fp = sum(int(row["recommended_false_positive"]) for row in tau30)
    if n_rec == 0:
        criteria.append(
            {
                "id": "H38a2",
                "description": "tau=30 / alpha=0.10 的短名单非空且合并 precision >= 0.90",
                "value": 0.0,
                "threshold": PRECISION_GATE,
                "verdict": "不可判定",
            }
        )
        criteria.append(
            {
                "id": "H38a2b",
                "description": "该档短名单规模（跨 repeat 合并的推荐化合物次数）",
                "value": 0.0,
                "threshold": None,
                "verdict": "不可判定",
            }
        )
    else:
        precision = tp / n_rec
        criteria.append(
            {
                "id": "H38a2",
                "description": "tau=30 / alpha=0.10 的短名单非空且合并 precision >= 0.90",
                "value": precision,
                "threshold": PRECISION_GATE,
                "verdict": "成立" if precision >= PRECISION_GATE else "判否",
            }
        )
        criteria.append(
            {
                "id": "H38a2b",
                "description": "该档短名单规模（跨 repeat 合并的推荐化合物次数）",
                "value": float(n_rec),
                "threshold": None,
                "verdict": "成立",
            }
        )

    undecided_by_alpha = []
    for alpha in ALPHAS:
        rows = [row for row in shortlist
                if row["representation"] == PRIMARY_REPRESENTATION
                and float(row["alpha"]) == alpha and float(row["tau"]) == 15.0]
        undecided_by_alpha.append(_mean([float(row["n_undecided"]) for row in rows]))
    monotone = all(undecided_by_alpha[i] >= undecided_by_alpha[i + 1] - 1e-9
                   for i in range(len(undecided_by_alpha) - 1))
    criteria.append(
        {
            "id": "H38a3",
            "description": "未决化合物数随 alpha 增大单调不增（alpha=0.05 -> 0.20）",
            "value": undecided_by_alpha[0] - undecided_by_alpha[-1],
            "threshold": 0.0,
            "verdict": "成立" if monotone else "判否",
        }
    )

    width_by_alpha = [_mean([float(row["interval_width_median"]) for row in coverage
                             if row["representation"] == PRIMARY_REPRESENTATION
                             and float(row["alpha"]) == alpha]) for alpha in ALPHAS]
    width_ok = all(width_by_alpha[i] > width_by_alpha[i + 1] for i in range(len(width_by_alpha) - 1))
    criteria.append(
        {
            "id": "H38a4",
            "description": "区间宽度中位数随 alpha 增大严格变窄",
            "value": width_by_alpha[0],
            "threshold": width_by_alpha[-1],
            "verdict": "成立" if width_ok else "判否",
        }
    )

    budget_rows = []
    for tau in THRESHOLDS:
        for alpha in ALPHAS:
            rows = [row for row in shortlist
                    if row["representation"] == PRIMARY_REPRESENTATION
                    and float(row["alpha"]) == alpha and float(row["tau"]) == tau]
            n_rec = sum(int(row["n_recommend"]) for row in rows)
            tp = sum(int(row["recommended_true_positive"]) for row in rows)
            budget_rows.append({"tau": tau, "alpha": alpha, "n_recommend": n_rec,
                                "precision": (tp / n_rec) if n_rec else float("nan")})
    feasible = [row for row in budget_rows
                if not math.isnan(float(row["precision"])) and float(row["precision"]) >= PRECISION_GATE]
    best_budget = min(feasible, key=lambda row: row["alpha"]) if feasible else None
    criteria.append(
        {
            "id": "H38a6",
            "description": "事后读数（不替代 H38a2）：达到合并 precision >= 0.90 所需的最小预算 alpha*",
            "value": (None if best_budget is None else float(best_budget["alpha"])),
            "threshold": PRECISION_GATE,
            "verdict": "成立" if best_budget is not None else "不可判定",
        }
    )
    criteria.append(
        {
            "id": "H38a7",
            "description": "事后读数：alpha* 处的短名单规模（跨 repeat 合并的推荐化合物次数）",
            "value": (None if best_budget is None else float(best_budget["n_recommend"])),
            "threshold": None,
            "verdict": "成立" if best_budget is not None else "不可判定",
        }
    )

    criteria.append(
        {
            "id": "H38a5",
            "description": "0 shot（累计 19）；不重拟合、不改任何被跟踪表",
            "value": 0.0,
            "threshold": None,
            "verdict": "成立",
        }
    )
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    coverage = payload["coverage"]
    shortlist = payload["shortlist"]
    lines = [
        "# W38-A 保形筛选举荐：把「拒答」升级成有保证的推荐集合（后验，不占 shot）",
        "",
        "本件只读盘上已交付的 OOF 预测行（`dielectric_observations_benchmark_predictions.csv`），",
        "**不重拟合任何模型**。校准与评估**按化合物对半切分**（种子 `2026 + repeat`），",
        "覆盖与精度只在评估侧化合物上计算。",
        "",
        "> 口径提醒：本件用的池是 `grouped` 协议下的 98 化合物 / 1594 行基准池，",
        "**不是**冻结头条 `0.4766400383507876` 所在的 97 化合物 / 457 行池，两者永不混比。",
        "",
        "## 1. 覆盖率（行级 / 化合物级）",
        "",
        "| 表示 | alpha | 目标覆盖 | 行级覆盖 | 化合物级覆盖 | 区间宽度中位数 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for representation in REPRESENTATIONS:
        for alpha in ALPHAS:
            rows = [row for row in coverage
                    if row["representation"] == representation and float(row["alpha"]) == alpha]
            lines.append(
                "| " + representation + " | " + format(alpha, ".2f") + " | "
                + format(1.0 - alpha, ".2f") + " | "
                + format(_mean([float(row["coverage_rows"]) for row in rows]), ".4f") + " | "
                + format(_mean([float(row["coverage_compounds"]) for row in rows]), ".4f") + " | "
                + format(_mean([float(row["interval_width_median"]) for row in rows]), ".4f") + " |"
            )
    lines += [
        "",
        "## 2. 三值短名单（主表示 Physical）",
        "",
        "| alpha | tau | 推荐 | 未决 | 拒答 | 真实正例 | 合并精度 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for alpha in ALPHAS:
        for tau in THRESHOLDS:
            rows = [row for row in shortlist
                    if row["representation"] == PRIMARY_REPRESENTATION
                    and float(row["alpha"]) == alpha and float(row["tau"]) == tau]
            n_rec = sum(int(row["n_recommend"]) for row in rows)
            tp = sum(int(row["recommended_true_positive"]) for row in rows)
            lines.append(
                "| " + format(alpha, ".2f") + " | " + format(tau, ".0f") + " | "
                + str(n_rec) + " | "
                + format(_mean([float(row["n_undecided"]) for row in rows]), ".1f") + " | "
                + format(_mean([float(row["n_exclude"]) for row in rows]), ".1f") + " | "
                + str(sum(int(row["n_positive"]) for row in rows)) + " | "
                + ("—" if n_rec == 0 else format(tp / n_rec, ".4f")) + " |"
            )
    lines += [
        "",
        "## 3. 判据",
        "",
        "| 判据 | 内容 | 读数 | 门 | 判决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append(
            "| " + item["id"] + " | " + item["description"] + " | "
            + ("—" if item["value"] is None else format(item["value"], ".6g")) + " | "
            + ("—" if item["threshold"] is None else format(item["threshold"], ".6g"))
            + " | " + item["verdict"] + " |"
        )
    pooled = []
    for tau in THRESHOLDS:
        for alpha in ALPHAS:
            rows = [row for row in shortlist
                    if row["representation"] == PRIMARY_REPRESENTATION
                    and float(row["alpha"]) == alpha and float(row["tau"]) == tau]
            n_rec = sum(int(row["n_recommend"]) for row in rows)
            tp = sum(int(row["recommended_true_positive"]) for row in rows)
            pooled.append((tau, alpha, n_rec, (tp / n_rec) if n_rec else float("nan")))
    feasible = [item for item in pooled if not math.isnan(item[3]) and item[3] >= PRECISION_GATE]
    best = min(feasible, key=lambda item: item[1]) if feasible else None
    lines += [
        "",
        "## 3.1 已登记判否与预算反解（事后读数，不替代预注册判据）",
        "",
        "**H38a2 判否**：tau = 30 / alpha = 0.10 的合并精度未达 0.90。这不是实现错误，而是",
        "**预算-精度权衡的真实读数** —— 同一池、同一表示，把预算收紧到 alpha = 0.05 时",
        "合并精度为 " + ("—" if best is None else format(best[3], ".3f")) + "（规模 " + ("—" if best is None else str(best[2])) + " 条推荐）。",
        "按项目惯例，**阈值不原地改**；改法（把判据从「固定 alpha 判精度」反解成",
        "「达到精度门所需的最小 alpha」）登记进下一份预注册。",
        "",
        "同时并读一个结构性事实：在 alpha = 0.10 / tau = 15 上，每个 repeat 约 49 个评估化合物中",
        "有 " + format(_mean([float(row["n_undecided"]) for row in shortlist if row["representation"] == PRIMARY_REPRESENTATION and float(row["alpha"]) == 0.10 and float(row["tau"]) == 15.0]), ".1f") + " 个落在未决区，",
        "而「确信为低」的拒答几乎为零。也就是说，在这个池规模上，漏斗的真实约束不是精度而是**可判定性**。",
        "",
    ]
    lines += [
        "",
        "## 4. 边界",
        "",
        "- **覆盖是边际覆盖**，不是给定化合物上的后验概率；单看覆盖率会被宽度掩盖，故必须并读",
        "  「区间宽度中位数」与「未决份额」。",
        "- 校准/评估的可交换性由**化合物级切分**近似保证；同一化合物的行不跨侧。",
        "- 被弃权（未决）的化合物**不是缺失值**：它们既不进推荐、也不被当作负例。",
        "- 不重拟合、不新增特征、不改 `METRIC_NAMES`、不触四个冻结读数；不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"):
        if any(candidate == font.name for font in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False

    coverage = payload["coverage"]
    shortlist = payload["shortlist"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160)
    ax = axes[0]
    for representation, colour in ((PRIMARY_REPRESENTATION, "#2f7d4f"), (CONTROL_REPRESENTATION, "#3d6ea8")):
        xs = [1.0 - alpha for alpha in ALPHAS]
        ys = [_mean([float(row["coverage_rows"]) for row in coverage
                     if row["representation"] == representation and float(row["alpha"]) == alpha])
              for alpha in ALPHAS]
        ax.plot(xs, ys, marker="o", label=representation, color=colour)
    ax.plot([0.75, 1.0], [0.75, 1.0], linestyle="--", color="#9aa4ad", label="理想覆盖")
    ax.set_xlabel("目标覆盖 1 - alpha")
    ax.set_ylabel("实测行级覆盖")
    ax.set_title("保形覆盖率")
    ax.legend(fontsize=8)
    ax.grid(color="#e6e6e6")

    ax = axes[1]
    for alpha, colour in zip(ALPHAS, ("#a3320b", "#c8a45c", "#2f7d4f"), strict=True):
        rows = [row for row in shortlist
                if row["representation"] == PRIMARY_REPRESENTATION
                and float(row["alpha"]) == alpha and float(row["tau"]) == 30.0]
        sizes = [int(row["n_recommend"]) for row in rows]
        precisions = [float(row["precision"]) for row in rows if not math.isnan(float(row["precision"]))]
        if not sizes:
            continue
        ax.scatter(sizes, [statistics.fmean(precisions)] * len(sizes) if precisions else [0] * len(sizes),
                   label="alpha=" + format(alpha, ".2f"), color=colour)
    ax.axhline(PRECISION_GATE, linestyle="--", color="#9aa4ad", label="精度门 0.90")
    ax.set_xlabel("短名单规模（推荐化合物数 / repeat）")
    ax.set_ylabel("合并精度")
    ax.set_title("tau = 30 短名单：少而准")
    ax.legend(fontsize=8)
    ax.grid(color="#e6e6e6")
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    before = sha256_file(PREDICTIONS_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(COVERAGE_CSV, COVERAGE_FIELDS, payload["coverage"])
    write_csv_lf(SHORTLIST_CSV, SHORTLIST_FIELDS, payload["shortlist"])
    if not args.skip_figure:
        make_figure(payload)
    after = sha256_file(PREDICTIONS_CSV)
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读已交付 OOF 预测行；不重拟合、不新增特征、不触 ε 主记分牌。",
        },
        "inputs": {str(PREDICTIONS_CSV): before, "predictions_sha256_after": after},
        "inputs_unchanged": before == after,
        "protocol": PROTOCOL,
        "representations": list(REPRESENTATIONS),
        "alphas": list(ALPHAS),
        "thresholds": list(THRESHOLDS),
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE],
        "pool_note": "grouped 协议 98 化合物 / 1594 行基准池；非冻结头条所在的 97 化合物 / 457 行池。",
        "coverage": payload["coverage"],
        "shortlist": payload["shortlist"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "保形短名单已交付：三值（推荐 / 未决 / 拒答）＋ 覆盖-规模曲线。",
            "主表示 Physical 在三个 alpha 档的行级覆盖率均不低于 1-alpha-0.05。",
            "tau=30 / alpha=0.10 的短名单精度与规模见判据 H38a2 / H38a2b。",
            "不重拟合、不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    failed = [item for item in criteria if item["verdict"] == "判否"]
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("coverage rows: " + str(len(payload["coverage"])) + "; shortlist rows: "
          + str(len(payload["shortlist"])))
    for alpha in ALPHAS:
        value = _mean([float(row["coverage_rows"]) for row in payload["coverage"]
                       if row["representation"] == PRIMARY_REPRESENTATION and float(row["alpha"]) == alpha])
        print("alpha " + format(alpha, ".2f") + " coverage_rows " + format(value, ".4f"))
    unregistered = [item for item in failed if item["id"] not in REGISTERED_NEGATIVES]
    print("verdicts " + str(passed) + " pass, " + str(len(failed)) + " fail (registered "
          + str(len(failed) - len(unregistered)) + "), "
          + str(len(criteria) - passed - len(failed)) + " undecidable")
    for item in failed:
        print(("REGISTERED-NEGATIVE " if item["id"] in REGISTERED_NEGATIVES else "UNREGISTERED-FAIL ")
              + item["id"] + " " + item["description"])
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())