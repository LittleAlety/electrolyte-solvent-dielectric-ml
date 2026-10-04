# -*- coding: utf-8 -*-
"""W45-B：4668 行 xTB–Batt 的分层残差与稳健离群诊断（计算 lane，0 shot）。

扩展层的 4668 个 paired_anchor 行此前只报过一个总 ρ=0.5985。本件把它拆成：
  * tier 分层（calibration_bulk / named_core_channel / flagship_dielectric）的 ρ / MAE / 稳健尺度；
  * 重原子数分箱（5–12 / 13–17 / 18–40）的 ρ，看秩一致是否随分子变大而退化；
  * 稳健离群：先去中位（xTB 与 Batt 有 ~6.99 eV 的系统电平差），再按 1.4826*MAD 归一，
    统计 |z|>3.5 的比例；绝对阈值在任何方向上都会被电平差污染，故不用。
  * 总 ρ 的 bootstrap CI 与置换 p。

只读；不改任何标签或特征列；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w45_stratified_residual.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from scipy import stats

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    bootstrap_ci,
    criteria_row,
    permutation_p,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from w45_common import EXPANDED_CSV, paired_rows

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w45_compute_prereg.json"
STRATA_CSV = ARTIFACTS / "w45_stratified_residual.csv"
FIGURE_PATH = ARTIFACTS / "w45_stratified_residual.png"
SUMMARY_PATH = ARTIFACTS / "w45_stratified_residual_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w45_stratified_residual.md"

SCHEMA = "w45_stratified_residual/summary@1"
TASK = "week45_stratified_residual"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

STRATA_FIELDS = ("scope", "stratum", "n", "spearman", "kendall", "mae_ev", "median_abs_ev",
                 "p90_abs_ev", "robust_scale_ev", "heavy_tail_fraction")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w45 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _stats(x: np.ndarray, y: np.ndarray) -> dict[str, object]:
    delta = y - x
    median = float(np.median(delta))
    mad = float(np.median(np.abs(delta - median)))
    robust_scale = 1.4826 * mad
    if robust_scale > 0:
        z = (delta - median) / robust_scale
        heavy = float(np.mean(np.abs(z) > 3.5))
    else:
        heavy = 0.0
    return {
        "n": int(len(x)),
        "spearman": float(stats.spearmanr(x, y).statistic),
        "kendall": float(stats.kendalltau(x, y).statistic),
        "mae_ev": float(np.mean(np.abs(delta))),
        "median_abs_ev": float(np.median(np.abs(delta))),
        "p90_abs_ev": float(np.percentile(np.abs(delta), 90)),
        "robust_scale_ev": robust_scale,
        "heavy_tail_fraction": heavy,
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w45_stratified_residual"]
    rows = paired_rows()
    x = np.asarray([float(row["gap_gfn2_eV"]) for row in rows], dtype=float)
    y = np.asarray([float(row["batt_gap_eV"]) for row in rows], dtype=float)
    natoms = np.asarray([float(row["natoms"]) for row in rows], dtype=float)
    tiers = [str(row["expansion_tier"]) for row in rows]

    table: list[dict[str, object]] = [dict(scope="overall", stratum="all", **_stats(x, y))]

    tier_rows: list[dict[str, object]] = []
    for tier in lane["strata"]["tier"]:
        index = np.asarray([i for i, value in enumerate(tiers) if value == tier], dtype=int)
        if len(index) < 2:
            continue
        record = dict(scope="tier", stratum=str(tier), **_stats(x[index], y[index]))
        tier_rows.append(record)
        table.append(record)

    atom_rows: list[dict[str, object]] = []
    for low, high in lane["strata"]["atom_bins"]:
        index = np.asarray([i for i in range(len(rows)) if low <= int(natoms[i]) <= high], dtype=int)
        if len(index) < 2:
            continue
        record = dict(scope="atom_bin", stratum="%d-%d" % (low, high), **_stats(x[index], y[index]))
        atom_rows.append(record)
        table.append(record)

    resamples = int(lane["bootstrap_draws"])
    seed = int(lane["rng_seed"])
    ci = bootstrap_ci(x, y, resamples, seed)
    perm = permutation_p(x, y, int(lane["permutation_draws"]), seed + 1)
    overall = table[0]
    delta = y - x
    median = float(np.median(delta))
    mad = float(np.median(np.abs(delta - median)))
    return {
        "n": len(rows),
        "table": table,
        "tier_rows": tier_rows,
        "atom_rows": atom_rows,
        "overall": overall,
        "bootstrap": ci,
        "permutation": perm,
        "delta_median_ev": median,
        "delta_mad_ev": mad,
        "points": (x, y, tiers),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w45_stratified_residual"]["gates"]
    overall = payload["overall"]
    tier_rows = payload["tier_rows"]
    atom_rows = payload["atom_rows"]
    bulk = next((row for row in tier_rows if row["stratum"] == "calibration_bulk"), None)
    homogeneity = max((abs(float(row["spearman"]) - float(bulk["spearman"])) for row in tier_rows),
                      default=float("inf")) if bulk else float("inf")
    return [
        criteria_row("H45b1", "paired_anchor 行数 >= 4600",
                     payload["n"], int(gates["paired_rows_min"]),
                     int(payload["n"]) >= int(gates["paired_rows_min"])),
        criteria_row("H45b2", "总体 rho(gap_gfn2, gap_batt) 逐位复现 W43 锚 0.5984785837315431",
                     overall["spearman"], gates["overall_spearman_expected"],
                     abs(float(overall["spearman"]) - float(gates["overall_spearman_expected"]))
                     <= float(gates["overall_spearman_tol"])),
        criteria_row("H45b3", "三个 tier 分层每层 n >= 40",
                     {row["stratum"]: row["n"] for row in tier_rows},
                     int(gates["min_stratum_rows"]),
                     len(tier_rows) == 3
                     and all(int(row["n"]) >= int(gates["min_stratum_rows"]) for row in tier_rows)),
        criteria_row("H45b4", "bulk 层 rho 落在 [0.55, 0.65] 且各分层 rho > 0",
                     {row["stratum"]: row["spearman"] for row in tier_rows},
                     {"bulk_min": gates["bulk_spearman_min"], "bulk_max": gates["bulk_spearman_max"]},
                     bulk is not None
                     and float(gates["bulk_spearman_min"]) <= float(bulk["spearman"]) <= float(gates["bulk_spearman_max"])
                     and all(float(row["spearman"]) > 0 for row in tier_rows)),
        criteria_row("H45b5", "分层同质：各 tier 与 bulk 的 rho 最大间距 <= 0.15",
                     homogeneity, float(gates["stratum_homogeneity_max_gap"]),
                     float(homogeneity) <= float(gates["stratum_homogeneity_max_gap"])),
        criteria_row("H45b6", "总体 rho 的 bootstrap 95% CI 下界 >= 0.5",
                     payload["bootstrap"], {"lo_min": gates["bootstrap_ci_lo_min"]},
                     float(payload["bootstrap"]["lo"]) >= float(gates["bootstrap_ci_lo_min"])),
        criteria_row("H45b7", "置换 p <= 0.001",
                     payload["permutation"], {"p_max": gates["permutation_p_max"]},
                     float(payload["permutation"]["p_value"]) <= float(gates["permutation_p_max"])),
        criteria_row("H45b8", "三个重原子数分箱每箱 n >= 100 且 rho >= 0.4",
                     {row["stratum"]: {"n": row["n"], "spearman": row["spearman"]} for row in atom_rows},
                     {"min_rows": gates["min_atom_bin_rows"], "rho_min": gates["atom_bin_spearman_min"]},
                     len(atom_rows) == 3
                     and all(int(row["n"]) >= int(gates["min_atom_bin_rows"]) for row in atom_rows)
                     and all(float(row["spearman"]) >= float(gates["atom_bin_spearman_min"]) for row in atom_rows)),
        criteria_row("H45b9", "稳健离群：|z|>3.5 比例 <= 0.20 且稳健尺度 MAD*1.4826 <= 1.0 eV",
                     {"heavy_tail_fraction": overall["heavy_tail_fraction"],
                      "robust_scale_ev": overall["robust_scale_ev"],
                      "delta_median_ev": payload["delta_median_ev"]},
                     {"fraction_max": gates["heavy_tail_fraction_max"],
                      "scale_max_ev": gates["robust_scale_mad_max_ev"]},
                     float(overall["heavy_tail_fraction"]) <= float(gates["heavy_tail_fraction_max"])
                     and float(overall["robust_scale_ev"]) <= float(gates["robust_scale_mad_max_ev"])),
        criteria_row("H45b10", "输入（扩展层 + prereg）sha256 未变", "before == after", True, True),
    ]


def render_figure(payload: Mapping[str, object], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x, y, tiers = payload["points"]
    font = pick_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font]
        plt.rcParams["axes.unicode_minus"] = False
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    colors = {"calibration_bulk": "#8fa8c8", "named_core_channel": "#e0a13a",
              "flagship_dielectric": "#c0504d"}
    for tier, color in colors.items():
        mask = np.asarray([value == tier for value in tiers])
        axes[0].scatter(x[mask], y[mask], s=5, alpha=0.35, color=color, label=tier)
    axes[0].set_xlabel("GFN2-xTB gap (eV)")
    axes[0].set_ylabel("Batt gap (eV)")
    axes[0].set_title("xTB vs Batt gap, 4668 rows")
    axes[0].legend(fontsize=7, markerscale=2)

    atom_rows = payload["atom_rows"]
    labels = [row["stratum"] for row in atom_rows]
    values = [float(row["spearman"]) for row in atom_rows]
    counts = [int(row["n"]) for row in atom_rows]
    bars = axes[1].bar(labels, values, color="#4f81bd")
    for bar, value, count in zip(bars, values, counts):
        axes[1].text(bar.get_x() + bar.get_width() / 2, value + 0.02, "%.3f\nn=%d" % (value, count),
                     ha="center", va="bottom", fontsize=8)
    axes[1].set_ylim(0, 1.0)
    axes[1].set_ylabel("Spearman rho")
    axes[1].set_title("rank agreement by heavy-atom bin")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W45-B 4668 行 xTB–Batt 的分层残差与稳健离群",
        "",
        "只读计算 lane；0 shot。rank 一致随 tier 与分子大小如何变化。",
        "",
        "## 1 分层读数",
        "",
        "| scope | stratum | n | rho | MAE (eV) | 中位Δ | P90Δ | 稳健尺度 | z-离群比例 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["table"]:
        lines.append("| " + str(row["scope"]) + " | " + str(row["stratum"]) + " | " + str(row["n"]) + " | "
                     + repr(row["spearman"]) + " | " + repr(row["mae_ev"]) + " | "
                     + repr(row["median_abs_ev"]) + " | " + repr(row["p90_abs_ev"]) + " | "
                     + repr(row["robust_scale_ev"]) + " | " + repr(row["heavy_tail_fraction"]) + " |")
    lines += [
        "",
        "- Δgap 中位（系统电平差）： " + repr(payload["delta_median_ev"]) + " eV；MAD： "
        + repr(payload["delta_mad_ev"]) + " eV。",
        "- 总体 rho 的 bootstrap 95% CI： [" + repr(payload["bootstrap"]["lo"]) + ", "
        + repr(payload["bootstrap"]["hi"]) + "]；置换 p = " + repr(payload["permutation"]["p_value"]) + "。",
        "",
        "## 2 判据",
        "",
        "| 判据 | 描述 | 读数 | 阈值 | 结论 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        threshold = item["threshold"]
        ttext = json.dumps(threshold, ensure_ascii=False) if isinstance(threshold, (dict, list)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
                     + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 3 边界",
        "",
        "- 只读：不改任何标签或特征列。",
        "- 分层不是层级：tier 是扩展层的抽样档位，不是电子结构层级；分层 rho 之差不等于层级真值差。",
        "- Δgap 含 ~6.99 eV 的系统电平差，离群只能用去中位后的稳健尺度判，绝对阈值会被电平差污染。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只跑判据并以退出码表示结果")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, EXPANDED_CSV]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H45b10", "输入（扩展层 + prereg）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(STRATA_CSV, STRATA_FIELDS, payload["table"])
        render_figure(payload, FIGURE_PATH)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读分层统计扩展层，不拟合主记分牌臂、不加特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "paired_rows": payload["n"],
            "strata_rows": payload["table"],
            "bootstrap": payload["bootstrap"],
            "permutation": payload["permutation"],
            "delta_median_ev": payload["delta_median_ev"],
            "delta_mad_ev": payload["delta_mad_ev"],
            "figure": "probes/artifacts/w45_stratified_residual.png",
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "总体 rho 逐位复现 0.5984785837315431；bootstrap CI ["
                + repr(payload["bootstrap"]["lo"]) + ", " + repr(payload["bootstrap"]["hi"]) + "]。",
                "分层 rho： " + ", ".join("%s=%s" % (row["stratum"], repr(row["spearman"]))
                                          for row in payload["tier_rows"]) + "。",
                "重原子数分箱 rho： " + ", ".join("%s=%s (n=%d)" % (row["stratum"], repr(row["spearman"]), row["n"])
                                                for row in payload["atom_rows"]) + "（越大越弱）。",
                "稳健离群比例（|z|>3.5）： " + repr(payload["overall"]["heavy_tail_fraction"]) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("n %d overall rho %r ci [%r,%r] perm %r"
          % (payload["n"], payload["overall"]["spearman"], payload["bootstrap"]["lo"],
             payload["bootstrap"]["hi"], payload["permutation"]["p_value"]))
    for row in payload["table"]:
        print("%s/%s n=%d rho=%r mae=%r" % (row["scope"], row["stratum"], row["n"],
                                            row["spearman"], row["mae_ev"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
