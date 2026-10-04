# -*- coding: utf-8 -*-
"""W42-B：xTB→Batt 单调（isotonic）代理校正与代理上界（计算 lane，0 shot）。

W41-D 登记 item 34：xTB 与 Batt-P30K 的 ωB97X-V/SMD 轨道层只有 ρ=0.328、Pearson=0.088 的弱迁移。
本件把「xTB 当作 Batt 通道的排序代理」这件事算到底：
  * isotonic（保序）回归 Batt_gap ~ xTB_gap，样本内 R²/ρ 与单调性检查；
  * 5 折交叉验证的样本外 R²/ρ（代理上界）；
  * 中位数二分与上四分位二分的阈值 AUC（raw 与 CV isotonic 各一份）；
  * 与 xTB→QM9 的保真度之比（proxy_fidelity_ratio）。

只读：名册、w23 轨道层、w41 Batt 命中表、w39 QM9 层。不改标签池、不加特征列、不动主记分牌。

Run:
    .venv/Scripts/python.exe probes/w42_proxy_calibration.py
"""

from __future__ import annotations

import argparse
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
    FROZEN_READINGS,
    bootstrap_ci,
    criteria_row,
    load_layers,
    overlap_keys,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w42_registry_transfer_prereg.json"
METRICS_CSV = ARTIFACTS / "w42_proxy_calibration.csv"
CURVE_CSV = ARTIFACTS / "w42_isotonic_curve.csv"
SUMMARY_PATH = ARTIFACTS / "w42_proxy_calibration_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w42_proxy_calibration.md"
FIGURE_PATH = ARTIFACTS / "w42_proxy_calibration.png"

SCHEMA = "w42_proxy_calibration/summary@1"
TASK = "week42_proxy_calibration"

REGISTERED_NEGATIVES: tuple[str, ...] = ()

METRIC_FIELDS = ("metric", "subset", "n", "value")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w42 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    from scipy import stats

    return float(stats.spearmanr(x, y).statistic)


def _r2(y: np.ndarray, prediction: np.ndarray) -> float:
    sst = float(np.sum((y - np.mean(y)) ** 2))
    sse = float(np.sum((y - prediction) ** 2))
    return 1.0 - sse / sst


def compute(layers: Mapping[str, Mapping[str, float]], prereg: Mapping[str, object],
            ) -> dict[str, object]:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import KFold

    lane = prereg["lanes"]["w42_proxy_calibration"]
    seed = int(lane["cv_seed"])
    folds = int(lane["cv_folds"])
    keys = overlap_keys(layers, ("xtb", "batt"))
    x = np.asarray([layers["xtb"][k] for k in keys], dtype=float)
    y = np.asarray([layers["batt"][k] for k in keys], dtype=float)
    n = len(keys)

    model = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    fitted = model.predict(x)
    rho_before = _spearman(x, y)
    pearson_before = float(np.corrcoef(x, y)[0, 1])
    in_r2 = _r2(y, fitted)
    in_rho = _spearman(fitted, y)
    in_pearson = float(np.corrcoef(fitted, y)[0, 1])
    monotone = bool(np.all(np.diff(fitted[np.argsort(x, kind="stable")]) >= -1e-12))

    splitter = KFold(folds, shuffle=True, random_state=seed)
    cross = np.empty(n, dtype=float)
    for train, test in splitter.split(x):
        fold_model = IsotonicRegression(out_of_bounds="clip").fit(x[train], y[train])
        cross[test] = fold_model.predict(x[test])
    cv_r2 = _r2(y, cross)
    cv_rho = _spearman(cross, y)

    median_label = (y > float(np.median(y))).astype(int)
    quartile_label = (y >= float(np.quantile(y, 0.75))).astype(int)
    auc = {
        "median_raw": float(roc_auc_score(median_label, x)),
        "median_isotonic_in_sample": float(roc_auc_score(median_label, fitted)),
        "median_isotonic_cv": float(roc_auc_score(median_label, cross)),
        "top_quartile_raw": float(roc_auc_score(quartile_label, x)),
        "top_quartile_isotonic_in_sample": float(roc_auc_score(quartile_label, fitted)),
        "top_quartile_isotonic_cv": float(roc_auc_score(quartile_label, cross)),
        "median_positives": int(median_label.sum()),
        "top_quartile_positives": int(quartile_label.sum()),
    }

    qm9_keys = overlap_keys(layers, ("xtb", "qm9"))
    xq = np.asarray([layers["xtb"][k] for k in qm9_keys], dtype=float)
    yq = np.asarray([layers["qm9"][k] for k in qm9_keys], dtype=float)
    rho_xtb_qm9 = _spearman(xq, yq)
    fidelity_ratio = rho_before / rho_xtb_qm9

    def resample_isfit(sample_x: np.ndarray, sample_y: np.ndarray) -> float:
        try:
            resampled = IsotonicRegression(out_of_bounds="clip").fit(sample_x, sample_y)
            return _spearman(resampled.predict(sample_x), sample_y)
        except ValueError:
            return float("nan")

    rng = np.random.default_rng(seed)
    draws = 2000
    reps = np.empty(draws, dtype=float)
    for index in range(draws):
        pick = rng.integers(0, n, n)
        reps[index] = resample_isfit(x[pick], y[pick])
    reps = reps[np.isfinite(reps)]
    isotonic_bootstrap = {
        "point": in_rho, "mean": float(np.mean(reps)), "sd": float(np.std(reps, ddof=1)),
        "lo": float(np.percentile(reps, 2.5)), "hi": float(np.percentile(reps, 97.5)),
        "draws": int(draws),
    }
    raw_bootstrap = bootstrap_ci(x, y, draws, seed + 7)

    metrics = [
        {"metric": "spearman_raw", "subset": "xtb-batt", "n": n, "value": rho_before},
        {"metric": "pearson_raw", "subset": "xtb-batt", "n": n, "value": pearson_before},
        {"metric": "isotonic_in_sample_r2", "subset": "xtb-batt", "n": n, "value": in_r2},
        {"metric": "isotonic_in_sample_spearman", "subset": "xtb-batt", "n": n,
         "value": in_rho},
        {"metric": "isotonic_in_sample_pearson", "subset": "xtb-batt", "n": n,
         "value": in_pearson},
        {"metric": "isotonic_cv_r2", "subset": "xtb-batt", "n": n, "value": cv_r2},
        {"metric": "isotonic_cv_spearman", "subset": "xtb-batt", "n": n, "value": cv_rho},
        {"metric": "auc_median_raw", "subset": "xtb-batt", "n": n, "value": auc["median_raw"]},
        {"metric": "auc_median_isotonic_cv", "subset": "xtb-batt", "n": n,
         "value": auc["median_isotonic_cv"]},
        {"metric": "auc_top_quartile_raw", "subset": "xtb-batt", "n": n,
         "value": auc["top_quartile_raw"]},
        {"metric": "auc_top_quartile_isotonic_cv", "subset": "xtb-batt", "n": n,
         "value": auc["top_quartile_isotonic_cv"]},
        {"metric": "rho_xtb_qm9_reference", "subset": "xtb-qm9", "n": len(qm9_keys),
         "value": rho_xtb_qm9},
        {"metric": "proxy_fidelity_ratio", "subset": "xtb-batt/xtb-qm9", "n": n,
         "value": fidelity_ratio},
        {"metric": "monotone_violations", "subset": "xtb-batt", "n": n,
         "value": 0.0 if monotone else 1.0},
    ]

    order = np.argsort(x, kind="stable")
    curve = [{"x_xtb_gap_ev": float(x[i]), "y_batt_gap_ev": float(y[i]),
              "fitted_batt_gap_ev": float(fitted[i])} for i in order]

    return {
        "n": n,
        "keys": keys,
        "x": x, "y": y, "fitted": fitted, "cross": cross,
        "auc": auc,
        "rho_before": rho_before, "pearson_before": pearson_before,
        "in_r2": in_r2, "in_rho": in_rho, "in_pearson": in_pearson, "cv_r2": cv_r2,
        "cv_rho": cv_rho, "monotone": monotone, "fidelity_ratio": fidelity_ratio,
        "rho_xtb_qm9": rho_xtb_qm9,
        "isotonic_bootstrap": isotonic_bootstrap, "raw_bootstrap": raw_bootstrap,
        "metrics": metrics, "curve": curve,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w42_proxy_calibration"]["gates"]
    auc = payload["auc"]
    criteria = [
        criteria_row("H42b1", "isotonic 样本内 R2 >= 0.30", payload["in_r2"],
                     gates["isotonic_in_sample_r2"],
                     float(payload["in_r2"]) >= float(gates["isotonic_in_sample_r2"])),
        criteria_row("H42b2", "isotonic 样本内 rho >= 0.50", payload["in_rho"],
                     gates["isotonic_in_sample_spearman"],
                     float(payload["in_rho"]) >= float(gates["isotonic_in_sample_spearman"])),
        criteria_row("H42b3", "isotonic 5 折 CV R2 >= 0.20", payload["cv_r2"],
                     gates["isotonic_cv_r2"],
                     float(payload["cv_r2"]) >= float(gates["isotonic_cv_r2"])),
        criteria_row("H42b4", "isotonic 5 折 CV rho >= 0.40", payload["cv_rho"],
                     gates["isotonic_cv_spearman"],
                     float(payload["cv_rho"]) >= float(gates["isotonic_cv_spearman"])),
        criteria_row("H42b5", "中位数二分 AUC（raw xTB） >= 0.65", auc["median_raw"],
                     gates["auc_raw_min"],
                     float(auc["median_raw"]) >= float(gates["auc_raw_min"])),
        criteria_row("H42b6", "中位数二分 AUC（isotonic CV） >= 0.70", auc["median_isotonic_cv"],
                     gates["auc_cv_min"],
                     float(auc["median_isotonic_cv"]) >= float(gates["auc_cv_min"])),
        criteria_row("H42b7", "上四分位二分 AUC（isotonic CV） >= 0.70",
                     auc["top_quartile_isotonic_cv"], gates["auc_top_quartile_cv_min"],
                     float(auc["top_quartile_isotonic_cv"])
                     >= float(gates["auc_top_quartile_cv_min"])),
        criteria_row("H42b8", "代理保真度比 rho(xTB,Batt)/rho(xTB,QM9) <= 0.40",
                     payload["fidelity_ratio"], gates["proxy_fidelity_ratio_max"],
                     float(payload["fidelity_ratio"]) <= float(gates["proxy_fidelity_ratio_max"])),
        criteria_row("H42b9", "isotonic 拟合单调性零违例",
                     0.0 if payload["monotone"] else 1.0, 0.0, bool(payload["monotone"])),
        criteria_row("H42b10", "输入文件生成前后 sha256 不变",
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
    x = np.asarray(payload["x"], dtype=float)
    y = np.asarray(payload["y"], dtype=float)
    fitted = np.asarray(payload["fitted"], dtype=float)
    cross = np.asarray(payload["cross"], dtype=float)
    order = np.argsort(x, kind="stable")
    figure, axes = plt.subplots(1, 2, figsize=(15.0, 5.6))
    axis = axes[0]
    axis.scatter(x, y, s=16, color="#4C72B0", alpha=0.7, label="Batt 实测 gap")
    axis.plot(x[order], fitted[order], color="#C44E52", linewidth=2.0,
              label="isotonic（样本内）")
    axis.set_xlabel("xTB gas gap (eV)")
    axis.set_ylabel("Batt-P30K gap (eV)")
    axis.set_title("W42-B xTB→Batt 保序校正（n=73）")
    axis.legend(loc="upper left", fontsize=9)
    axis = axes[1]
    axis.scatter(x, y, s=16, color="#BBBBBB", alpha=0.7, label="实测")
    axis.scatter(x, cross, s=16, color="#55A868", alpha=0.8, label="isotonic 5 折 CV")
    axis.set_xlabel("xTB gas gap (eV)")
    axis.set_ylabel("Batt-P30K gap (eV, CV 预测)")
    axis.set_title("W42-B 样本外代理（5 折）")
    axis.legend(loc="upper left", fontsize=9)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  ) -> str:
    auc = payload["auc"]
    lines = [
        "# W42-B xTB→Batt 单调（isotonic）代理校正与代理上界",
        "",
        "计算 lane（0 shot，累计仍 19）。回应 W41-D 登记的 item 34：xTB 与 Batt-P30K 弱迁移。",
        "",
        "## 1. 原始迁移 vs 保序校正",
        "",
        "| 量 | 值 |",
        "| --- | ---: |",
        "| n（xTB ∩ Batt） | " + str(payload["n"]) + " |",
        "| Spearman(raw) | " + format(float(payload["rho_before"]), ".4f") + " |",
        "| Pearson(raw) | " + format(float(payload["pearson_before"]), ".4f") + " |",
        "| isotonic 样本内 R2 | " + format(float(payload["in_r2"]), ".4f") + " |",
        "| isotonic 样本内 Spearman | " + format(float(payload["in_rho"]), ".4f") + " |",
        "| isotonic 5 折 CV R2 | " + format(float(payload["cv_r2"]), ".4f") + " |",
        "| isotonic 5 折 CV Spearman | " + format(float(payload["cv_rho"]), ".4f") + " |",
        "| 保真度比 rho(xTB,Batt)/rho(xTB,QM9) | "
        + format(float(payload["fidelity_ratio"]), ".4f") + " |",
        "",
        "保序校正把 Spearman 从 " + format(float(payload["rho_before"]), ".4f") + " 抬到样本内 "
        + format(float(payload["in_rho"]), ".4f") + "、样本外（CV）"
        + format(float(payload["cv_rho"]), ".4f")
        + "。样本内抬升主要来自保序回归的并列归并（ties）；样本外读数才是可引用的代理上界。",
        "",
        "## 2. 阈值 AUC（中位数二分 / 上四分位二分）",
        "",
        "| 任务 | raw xTB | isotonic 样本内 | isotonic CV |",
        "| --- | ---: | ---: | ---: |",
        "| Batt gap > 中位数（" + str(auc["median_positives"]) + "/" + str(payload["n"]) + " 阳性） | "
        + format(float(auc["median_raw"]), ".4f") + " | "
        + format(float(auc["median_isotonic_in_sample"]), ".4f") + " | "
        + format(float(auc["median_isotonic_cv"]), ".4f") + " |",
        "| Batt gap >= 上四分位（" + str(auc["top_quartile_positives"]) + "/"
        + str(payload["n"]) + " 阳性） | " + format(float(auc["top_quartile_raw"]), ".4f") + " | "
        + format(float(auc["top_quartile_isotonic_in_sample"]), ".4f") + " | "
        + format(float(auc["top_quartile_isotonic_cv"]), ".4f") + " |",
        "",
        "对照：xTB→QM9 的 ρ = " + format(float(payload["rho_xtb_qm9"]), ".4f")
        + "，代理保真度比只有 " + format(float(payload["fidelity_ratio"]), ".4f")
        + " ⇒ **xTB 可以代理 B3LYP 气相通道，不能代理 ωB97X-V/SMD 通道**。",
        "",
        "## 3. 重抽（bootstrap，2000）",
        "",
        "| 量 | 点估计 | 均值 | sd | 95% CI |",
        "| --- | ---: | ---: | ---: | --- |",
        "| raw rho | " + format(float(payload["raw_bootstrap"]["point"]), ".4f") + " | "
        + format(float(payload["raw_bootstrap"]["mean"]), ".4f") + " | "
        + format(float(payload["raw_bootstrap"]["sd"]), ".4f") + " | ["
        + format(float(payload["raw_bootstrap"]["lo"]), ".4f") + ", "
        + format(float(payload["raw_bootstrap"]["hi"]), ".4f") + "] |",
        "| isotonic 重拟合 rho | " + format(float(payload["isotonic_bootstrap"]["point"]), ".4f")
        + " | " + format(float(payload["isotonic_bootstrap"]["mean"]), ".4f") + " | "
        + format(float(payload["isotonic_bootstrap"]["sd"]), ".4f") + " | ["
        + format(float(payload["isotonic_bootstrap"]["lo"]), ".4f") + ", "
        + format(float(payload["isotonic_bootstrap"]["hi"]), ".4f") + "] |",
        "",
        "## 4. 判据",
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
        "## 5. 边界",
        "",
        "- isotonic 是**单调**变换，不改变无并列时的 Spearman；样本内抬升来自并列归并，引用必须用 CV 值。",
        "- 代理只用于「能不能替 Batt 通道排序」的问题；校正后的值不得当标签、不得入特征列。",
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
    sources = [REPOSITORY_ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv",
               ARTIFACTS / "w41_orbital_batt_hits.csv",
               ARTIFACTS / "w39_qm9_overlap.csv",
               REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(layers, prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after
    auc = payload["auc"]
    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(METRICS_CSV, METRIC_FIELDS, payload["metrics"])
    write_csv_lf(CURVE_CSV, ("x_xtb_gap_ev", "y_batt_gap_ev", "fitted_batt_gap_ev"),
                 payload["curve"])
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
            "why_not_a_shot": "只对 xTB 与 Batt 两列做保序回归与 CV/AUC 计算，不拟合主记分牌臂、"
                              "不加特征列、不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "n": payload["n"],
        "auc": payload["auc"],
        "metrics": payload["metrics"],
        "isotonic_bootstrap": payload["isotonic_bootstrap"],
        "raw_bootstrap": payload["raw_bootstrap"],
        "monotone": payload["monotone"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "xTB→Batt：Spearman raw " + format(float(payload["rho_before"]), ".4f")
            + "，isotonic CV " + format(float(payload["cv_rho"]), ".4f")
            + "，CV R2 " + format(float(payload["cv_r2"]), ".4f") + "。",
            "中位数二分 AUC：raw " + format(float(auc["median_raw"]), ".4f")
            + " → isotonic CV " + format(float(auc["median_isotonic_cv"]), ".4f") + "。",
            "代理保真度比 " + format(float(payload["fidelity_ratio"]), ".4f")
            + "（xTB 不能代理 ωB97X-V/SMD 通道）。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("n %d rho_raw %.6f in_r2 %.6f in_rho %.6f cv_r2 %.6f cv_rho %.6f"
          % (payload["n"], payload["rho_before"], payload["in_r2"], payload["in_rho"],
             payload["cv_r2"], payload["cv_rho"]))
    print("auc median raw %.4f cv %.4f | top quartile raw %.4f cv %.4f"
          % (auc["median_raw"], auc["median_isotonic_cv"], auc["top_quartile_raw"],
             auc["top_quartile_isotonic_cv"]))
    print("fidelity_ratio %.4f monotone %s" % (payload["fidelity_ratio"], payload["monotone"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
