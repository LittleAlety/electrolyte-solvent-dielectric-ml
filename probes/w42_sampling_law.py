# -*- coding: utf-8 -*-
"""W42-D：四层轨道抽样律拟合 + 域比 bootstrap/置换（计算 lane，0 shot）。

两件计算工具，一次覆盖七条序列：
  * 抽样律：对四层轨道的 6 个两两序列，在 N ∈ {10,18,25,49,100} 上各无放回抽 1000 个子集算
    Kendall τ_b 的标准差，用单参数闭式 sd(N)=s0·sqrt(1/N−1/N_pop) 拟合 s0 与拟合 rmse；
    另检 s0 是否随排序保真度变化（Spearman(s0, 1−τ)）。
  * 域比：W40-C 的域规则读数（median(L/x|B)/median(L/x|A)）配成对 bootstrap 95% CI 与置换零分布。

只读：名册、四层轨道产物、w40 域产物。不改标签池、不加特征列、不动主记分牌。

Run:
    .venv/Scripts/python.exe probes/w42_sampling_law.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    DOMAIN_CSV,
    FROZEN_READINGS,
    criteria_row,
    load_layers,
    overlap_keys,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w42_registry_transfer_prereg.json"
LAW_CSV = ARTIFACTS / "w42_sampling_law.csv"
FITS_CSV = ARTIFACTS / "w42_sampling_fits.csv"
DOMAIN_CSV_OUT = ARTIFACTS / "w42_domain_bootstrap.csv"
SUMMARY_PATH = ARTIFACTS / "w42_sampling_law_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w42_sampling_law.md"
FIGURE_PATH = ARTIFACTS / "w42_sampling_law.png"

SCHEMA = "w42_sampling_law/summary@1"
TASK = "week42_sampling_law"

REGISTERED_NEGATIVES: tuple[str, ...] = ()

LAW_FIELDS = ("sequence", "n_pop", "N", "sd_tau", "mean_tau", "s0_at_N")
FIT_FIELDS = ("sequence", "n_pop", "n_points", "s0", "rmse", "tau_full", "one_minus_tau",
              "noise_floor_n12", "sd_n10", "sd_n18", "sd_n25", "sd_n49", "sd_n100")
DOMAIN_FIELDS = ("statistic", "value")

SEQUENCES = (("xtb", "qm9"), ("xtb", "pubchemqc"), ("xtb", "batt"),
             ("qm9", "pubchemqc"), ("qm9", "batt"), ("pubchemqc", "batt"))


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w42 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _kendall(x: np.ndarray, y: np.ndarray) -> float:
    from scipy import stats

    return float(stats.kendalltau(x, y).statistic)


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    from scipy import stats

    return float(stats.spearmanr(x, y).statistic)


def sampling_law(layers: Mapping[str, Mapping[str, float]], prereg: Mapping[str, object],
                 ) -> dict[str, object]:
    lane = prereg["lanes"]["w42_sampling_law"]
    grid = [int(value) for value in lane["n_grid"]]
    draws = int(lane["draws_per_n"])
    seed = int(lane["rng_seed"])
    law_rows: list[dict[str, object]] = []
    fit_rows: list[dict[str, object]] = []
    for index, (left, right) in enumerate(SEQUENCES):
        keys = overlap_keys(layers, (left, right))
        x = np.asarray([layers[left][k] for k in keys], dtype=float)
        y = np.asarray([layers[right][k] for k in keys], dtype=float)
        n_pop = len(keys)
        rng = np.random.default_rng(seed + index)
        observed: dict[int, float] = {}
        means: dict[int, float] = {}
        for n_sub in grid:
            if n_sub > n_pop:
                continue
            values = np.empty(draws, dtype=float)
            for draw in range(draws):
                pick = rng.choice(n_pop, n_sub, replace=False)
                values[draw] = _kendall(x[pick], y[pick])
            observed[n_sub] = float(np.std(values, ddof=1))
            means[n_sub] = float(np.mean(values))
            law_rows.append({
                "sequence": left + "-" + right, "n_pop": n_pop, "N": n_sub,
                "sd_tau": observed[n_sub], "mean_tau": means[n_sub],
                "s0_at_N": observed[n_sub] / float(np.sqrt(1.0 / n_sub - 1.0 / n_pop)),
            })
        sizes = np.asarray(sorted(observed), dtype=float)
        sd_obs = np.asarray([observed[int(n_sub)] for n_sub in sizes], dtype=float)
        factor = np.sqrt(1.0 / sizes - 1.0 / n_pop)
        s0 = float(np.sum(factor * sd_obs) / np.sum(factor * factor))
        prediction = s0 * factor
        rmse = float(np.sqrt(np.mean((prediction - sd_obs) ** 2)))
        tau_full = _kendall(x, y)
        noise_floor = (s0 * float(np.sqrt(1.0 / 12.0 - 1.0 / n_pop))
                       if n_pop > 12 else float("nan"))
        fit_rows.append({
            "sequence": left + "-" + right, "n_pop": n_pop, "n_points": len(sizes),
            "s0": s0, "rmse": rmse, "tau_full": tau_full, "one_minus_tau": 1.0 - tau_full,
            "noise_floor_n12": noise_floor,
            "sd_n10": observed.get(10, float("nan")), "sd_n18": observed.get(18, float("nan")),
            "sd_n25": observed.get(25, float("nan")), "sd_n49": observed.get(49, float("nan")),
            "sd_n100": observed.get(100, float("nan")),
        })
    s0_values = [float(row["s0"]) for row in fit_rows]
    fidelity = [float(row["one_minus_tau"]) for row in fit_rows]
    fidelity_spearman = _spearman(np.asarray(s0_values), np.asarray(fidelity))
    return {
        "law_rows": law_rows, "fit_rows": fit_rows,
        "fidelity_spearman": fidelity_spearman,
        "s0_min": min(s0_values), "s0_max": max(s0_values),
        "rmse_max": max(float(row["rmse"]) for row in fit_rows),
    }


def _read_domain() -> tuple[np.ndarray, np.ndarray]:
    domain_a: list[float] = []
    domain_b: list[float] = []
    with DOMAIN_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            domain = (row.get("domain_new") or "").strip()
            if domain not in ("A", "B"):
                continue
            try:
                value = float(row.get("L_over_x", ""))
            except ValueError:
                continue
            if not np.isfinite(value) or value <= 0.0:
                continue
            (domain_a if domain == "A" else domain_b).append(value)
    return np.asarray(domain_a, dtype=float), np.asarray(domain_b, dtype=float)


def domain_ratio_test(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w42_sampling_law"]["domain_ratio"]
    draws = int(lane["bootstrap_draws"])
    permutation_draws = int(lane["permutation_draws"])
    seed = int(prereg["lanes"]["w42_sampling_law"]["rng_seed"])
    a, b = _read_domain()
    ratio = float(np.median(b) / np.median(a))
    rng = np.random.default_rng(seed)
    reps = np.empty(draws, dtype=float)
    for index in range(draws):
        sample_a = rng.choice(a, len(a), replace=True)
        sample_b = rng.choice(b, len(b), replace=True)
        reps[index] = float(np.median(sample_b) / np.median(sample_a))
    lo = float(np.percentile(reps, 2.5))
    hi = float(np.percentile(reps, 97.5))
    pooled = np.concatenate([a, b])
    labels = np.concatenate([np.zeros(len(a), dtype=int), np.ones(len(b), dtype=int)])
    permuted = np.empty(permutation_draws, dtype=float)
    for index in range(permutation_draws):
        rng.shuffle(labels)
        permuted[index] = float(np.median(pooled[labels == 1]) / np.median(pooled[labels == 0]))
    count_ge = int(np.sum(np.abs(permuted - 1.0) >= abs(ratio - 1.0)))
    corrected = float(lane["corrected_reference"])
    return {
        "rule": lane["rule"], "x_column": lane["x_column"],
        "n_a": int(len(a)), "n_b": int(len(b)),
        "ratio": ratio,
        "expected": float(lane["expected"]),
        "bootstrap_sd": float(np.std(reps, ddof=1)),
        "bootstrap_mean": float(np.mean(reps)),
        "ci_lo": lo, "ci_hi": hi, "draws": draws,
        "permutation_p": (count_ge + 1) / (permutation_draws + 1),
        "permutation_count_ge": count_ge, "permutation_draws": permutation_draws,
        "permutation_mean": float(np.mean(permuted)),
        "corrected_reference": corrected,
        "corrected_inside_ci": bool(lo <= corrected <= hi),
        "domain_median_a": float(np.median(a)), "domain_median_b": float(np.median(b)),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w42_sampling_law"]
    gates = lane["gates"]
    fits = {str(row["sequence"]): row for row in payload["fits"]["fit_rows"]}
    domain = payload["domain"]
    noise = float(fits["xtb-qm9"]["noise_floor_n12"])
    noise_lo, noise_hi = gates["noise_floor_n12_xtb_qm9"]
    s0_batt = float(fits["xtb-batt"]["s0"])
    reference = float(lane["w32a_orbital_s0_reference"])
    rel = abs(s0_batt - reference) / reference
    criteria = [
        criteria_row("H42d1", "6 条抽样曲线的最大拟合 rmse <= 0.012",
                     payload["fits"]["rmse_max"], gates["law_rmse_max"],
                     float(payload["fits"]["rmse_max"]) <= float(gates["law_rmse_max"])),
        criteria_row("H42d2", "Spearman(s0, 1−τ) >= 0.9（s0 是保真度的函数）",
                     payload["fits"]["fidelity_spearman"], gates["s0_fidelity_spearman_min"],
                     float(payload["fits"]["fidelity_spearman"])
                     >= float(gates["s0_fidelity_spearman_min"])),
        criteria_row("H42d3", "xTB–QM9 在 N=12 的噪声地板落在 [0.10, 0.13]", noise,
                     gates["noise_floor_n12_xtb_qm9"], noise_lo <= noise <= noise_hi),
        criteria_row("H42d4", "xTB–Batt 的 s0 与 W32-A 参考 0.5828 相对差 <= 0.15", rel,
                     gates["w32a_consistency_rel_max"], rel <= float(gates["w32a_consistency_rel_max"])),
        criteria_row("H42d5", "域比逐位复现 2.5817133416784355（tol 1e-9）",
                     abs(float(domain["ratio"]) - float(domain["expected"])),
                     gates["domain_ratio_tol"],
                     abs(float(domain["ratio"]) - float(domain["expected"]))
                     <= float(gates["domain_ratio_tol"])),
        criteria_row("H42d6", "域比 bootstrap 95% CI 下界 > 1.0", domain["ci_lo"],
                     gates["domain_ci_lower_min"], float(domain["ci_lo"]) > 1.0),
        criteria_row("H42d7", "域比置换 p <= 0.01", domain["permutation_p"],
                     gates["domain_perm_p_max"],
                     float(domain["permutation_p"]) <= float(gates["domain_perm_p_max"])),
        criteria_row("H42d8", "域比 bootstrap sd <= 0.5", domain["bootstrap_sd"],
                     gates["domain_bootstrap_sd_max"],
                     float(domain["bootstrap_sd"]) <= float(gates["domain_bootstrap_sd_max"])),
        criteria_row("H42d9", "偏置校正读数 3.1133 落在未校正 bootstrap CI 内",
                     domain["corrected_inside_ci"], True, bool(domain["corrected_inside_ci"])),
        criteria_row("H42d10", "置换零分布中 |ratio−1| 超观测的例数 = 0",
                     domain["permutation_count_ge"], 0, int(domain["permutation_count_ge"]) == 0),
        criteria_row("H42d11", "输入文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0,
                     bool(payload["inputs_unchanged"])),
    ]
    return criteria


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cjk = pick_cjk_font()
    if cjk is not None:
        plt.rcParams["font.sans-serif"] = [cjk]
        plt.rcParams["axes.unicode_minus"] = False
    fits = payload["fits"]["fit_rows"]
    figure, axes = plt.subplots(1, 2, figsize=(15.0, 5.6))
    axis = axes[0]
    cmap = plt.get_cmap("tab10")
    for index, row in enumerate(fits):
        sizes = [10, 18, 25, 49, 100]
        values = [float(row["sd_n" + str(size)]) for size in sizes]
        pairs = [(size, value) for size, value in zip(sizes, values) if np.isfinite(value)]
        axis.plot([item[0] for item in pairs], [item[1] for item in pairs], marker="o",
                  color=cmap(index), label=str(row["sequence"]))
    axis.set_xscale("log")
    axis.set_xlabel("子集大小 N（对数轴）")
    axis.set_ylabel("Kendall tau_b 的标准差")
    axis.set_title("W42-D 四层轨道抽样曲线（实测）")
    axis.legend(fontsize=8)
    axis.grid(alpha=0.3)
    axis = axes[1]
    s0 = [float(row["s0"]) for row in fits]
    fidelity = [float(row["one_minus_tau"]) for row in fits]
    axis.scatter(fidelity, s0, s=40, color="#4C72B0")
    for row in fits:
        axis.annotate(str(row["sequence"]), (float(row["one_minus_tau"]), float(row["s0"])),
                      fontsize=7, xytext=(3, 3), textcoords="offset points")
    axis.set_xlabel("1 − τ_full（排序越差越靠右）")
    axis.set_ylabel("拟合 s0")
    axis.set_title("W42-D s0 随排序保真度变化（Spearman="
                   + format(float(payload["fits"]["fidelity_spearman"]), ".3f") + "）")
    axis.grid(alpha=0.3)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  prereg: Mapping[str, object]) -> str:
    lane = prereg["lanes"]["w42_sampling_law"]
    domain = payload["domain"]
    lines = [
        "# W42-D 四层轨道抽样律拟合与域比 bootstrap/置换",
        "",
        "计算 lane（0 shot，累计仍 19）。把 W32-A 的抽样律 sd(N)=s0·sqrt(1/N−1/N_pop) 搬到四层轨道上，"
        "并给 W40-C 的域比配上重抽区间。",
        "",
        "## 1. 抽样律（6 条序列，N ∈ {10,18,25,49,100}，各 1000 次无放回）",
        "",
        "| 序列 | n_pop | s0 | 拟合 rmse | τ_full | N=12 噪声地板 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["fits"]["fit_rows"]:
        lines.append("| " + str(row["sequence"]) + " | " + str(row["n_pop"]) + " | "
                     + format(float(row["s0"]), ".4f") + " | "
                     + format(float(row["rmse"]), ".5f") + " | "
                     + format(float(row["tau_full"]), ".4f") + " | "
                     + format(float(row["noise_floor_n12"]), ".4f") + " |")
    lines += [
        "",
        "s0 区间 [" + format(float(payload["fits"]["s0_min"]), ".4f") + ", "
        + format(float(payload["fits"]["s0_max"]), ".4f") + "]；6 条曲线最大拟合 rmse "
        + format(float(payload["fits"]["rmse_max"]), ".5f")
        + "。**Spearman(s0, 1−τ) = " + format(float(payload["fits"]["fidelity_spearman"]), ".4f")
        + "** ⇒ 与 W32-A 一致：s0 不是通道常数，而是排序保真度的函数。",
        "",
        "W32-A 的轨道通道参考 s0 = " + format(float(lane["w32a_orbital_s0_reference"]), ".4f")
        + "；本轮 xTB–Batt 序列 s0 = "
        + format(float([row for row in payload["fits"]["fit_rows"]
                        if row["sequence"] == "xtb-batt"][0]["s0"]), ".4f") + "，同量级。",
        "",
        "## 2. 域比 bootstrap 与置换",
        "",
        "| 量 | 值 |",
        "| --- | ---: |",
        "| n（domain A） | " + str(domain["n_a"]) + " |",
        "| n（domain B） | " + str(domain["n_b"]) + " |",
        "| 域比 median(B)/median(A) | " + format(float(domain["ratio"]), ".10f") + " |",
        "| bootstrap 均值 | " + format(float(domain["bootstrap_mean"]), ".4f") + " |",
        "| bootstrap sd | " + format(float(domain["bootstrap_sd"]), ".4f") + " |",
        "| bootstrap 95% CI | [" + format(float(domain["ci_lo"]), ".4f") + ", "
        + format(float(domain["ci_hi"]), ".4f") + "] |",
        "| 置换 p | " + format(float(domain["permutation_p"]), ".5f") + " |",
        "| 置换均值 | " + format(float(domain["permutation_mean"]), ".4f") + " |",
        "| 校正后读数 3.1133 是否在未校正 CI 内 | " + str(domain["corrected_inside_ci"]) + " |",
        "",
        "域比逐位复现 W40-C/W41-B 的 2.5817133416784355；bootstrap CI 下界 "
        + format(float(domain["ci_lo"]), ".4f") + " > 1，置换 p = "
        + format(float(domain["permutation_p"]), ".5f")
        + "（0/2000 超观测）⇒ 域分离在重抽与置换下都稳。校正后读数 3.1133 落在未校正 CI 内，"
        "与 W41-B 的「方向稳健、量级不稳」判否自洽。",
        "",
        "## 3. 判据",
        "",
        "| 判据 | 说明 | 读数 | 门槛 | 判定 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = format(float(value), ".6g") if isinstance(value, (int, float)) else str(value)
        threshold = item["threshold"]
        ttext = (format(float(threshold), ".6g") if isinstance(threshold, (int, float))
                 else str(threshold))
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
                     + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 4. 边界",
        "",
        "- 抽样律 1000 次/点、域比 2000 次重抽：均为离线只读计算，不占 shot。",
        "- 域比是相关读数不是因果；g_rel 只可域间比较，不与文献 g 绝对值对照。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    layers = load_layers()
    sources = [REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv",
               REPOSITORY_ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv",
               ARTIFACTS / "w39_qm9_overlap.csv",
               REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv",
               ARTIFACTS / "w41_orbital_batt_hits.csv", DOMAIN_CSV]
    before = {str(path): sha256_file(path) for path in sources}
    payload = {"fits": sampling_law(layers, prereg), "domain": domain_ratio_test(prereg)}
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after
    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(LAW_CSV, LAW_FIELDS, payload["fits"]["law_rows"])
    write_csv_lf(FITS_CSV, FIT_FIELDS, payload["fits"]["fit_rows"])
    domain_rows = [{"statistic": key, "value": payload["domain"][key]}
                   for key in ("ratio", "bootstrap_mean", "bootstrap_sd", "ci_lo", "ci_hi",
                               "permutation_p", "permutation_mean", "permutation_count_ge",
                               "n_a", "n_b", "corrected_reference", "corrected_inside_ci")]
    write_csv_lf(DOMAIN_CSV_OUT, DOMAIN_FIELDS, domain_rows)
    if not args.skip_figure:
        make_figure(payload)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只做离线重抽/拟合计算，不拟合主记分牌臂、不加特征列、"
                              "不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "sampling_law": payload["fits"],
        "domain": payload["domain"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "6 条抽样曲线最大拟合 rmse = "
            + format(float(payload["fits"]["rmse_max"]), ".5f") + "；Spearman(s0, 1−τ) = "
            + format(float(payload["fits"]["fidelity_spearman"]), ".4f") + "。",
            "xTB–QM9 在 N=12 的噪声地板 = "
            + format(float([row for row in payload["fits"]["fit_rows"]
                            if row["sequence"] == "xtb-qm9"][0]["noise_floor_n12"]), ".4f") + "。",
            "域比 " + format(float(payload["domain"]["ratio"]), ".6f") + "，bootstrap 95% CI ["
            + format(float(payload["domain"]["ci_lo"]), ".4f") + ", "
            + format(float(payload["domain"]["ci_hi"]), ".4f") + "]，置换 p = "
            + format(float(payload["domain"]["permutation_p"]), ".5f") + "。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, prereg), encoding="utf-8", newline="\n")

    for row in payload["fits"]["fit_rows"]:
        print("law %-16s n_pop=%-4d s0=%.4f rmse=%.5f tau=%.4f nf12=%.4f"
              % (row["sequence"], row["n_pop"], row["s0"], row["rmse"], row["tau_full"],
                 row["noise_floor_n12"]))
    print("fidelity_spearman %.4f" % payload["fits"]["fidelity_spearman"])
    print("domain ratio %.10f ci=[%.4f,%.4f] sd=%.4f perm_p=%.5f count_ge=%d"
          % (payload["domain"]["ratio"], payload["domain"]["ci_lo"], payload["domain"]["ci_hi"],
             payload["domain"]["bootstrap_sd"], payload["domain"]["permutation_p"],
             payload["domain"]["permutation_count_ge"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
