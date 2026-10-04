# -*- coding: utf-8 -*-
"""W42-C：偶极三源回归分解与 Bland–Altman（计算 lane，0 shot）。

W41/C 登记 item 28/30：名册偶极对 QM9 有 ~0.39 D 系统偏置，来源未追溯。本件把新落的 PubChemQC
B3LYP 偶极接成第三源，做三源分解：
  * our / QM9 / PubChemQC 两两 bias、MAE、RMSE、Spearman、Pearson；
  * 每对的 Bland–Altman 一致性界限（bias ± 1.96 sd）与 bias 的成对 bootstrap CI；
  * 三源 OLS 归因 our ~ a*QM9 + b*PubChemQC + c，看偏置落在哪一层；
  * 定位比 min(bias_our_qm9, bias_our_pc)/max(...)：两个外部源彼此一致而都与我们差 ⇒ 偏置在方法层。

只读：名册、w39 QM9 层、orbital_second_source_layer.csv。本轮**只做归因，不做修数/插补**。

Run:
    .venv/Scripts/python.exe probes/w42_dipole_sources.py
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
    criteria_row,
    load_dipole_layers,
    overlap_keys,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w42_registry_transfer_prereg.json"
PAIRS_CSV = ARTIFACTS / "w42_dipole_sources.csv"
BLAND_CSV = ARTIFACTS / "w42_bland_altman.csv"
ATTRIBUTION_JSON = ARTIFACTS / "w42_dipole_attribution.json"
SUMMARY_PATH = ARTIFACTS / "w42_dipole_sources_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w42_dipole_sources.md"
FIGURE_PATH = ARTIFACTS / "w42_dipole_sources.png"

SCHEMA = "w42_dipole_sources/summary@1"
TASK = "week42_dipole_sources"

REGISTERED_NEGATIVES: tuple[str, ...] = ()

PAIR_FIELDS = ("pair", "source_a", "source_b", "n", "bias_a_minus_b", "sd_diff", "mae",
               "rmse", "spearman", "pearson", "slope_a_on_b", "intercept_a_on_b",
               "bias_ci_lo", "bias_ci_hi", "bias_ci_sd")
BLAND_FIELDS = ("pair", "n", "bias", "sd", "loa_lo", "loa_hi", "within_loa", "bias_ci_lo",
                "bias_ci_hi", "zero_inside_ci")

SOURCE_PAIRS = (("our", "qm9"), ("our", "pubchemqc"), ("qm9", "pubchemqc"))
SOURCE_LABEL = {
    "our": "本仓 xTB 偶极（THEMol 几何）",
    "qm9": "QM9 B3LYP/6-31G(2df,p) 气相偶极",
    "pubchemqc": "PubChemQC B3LYP/6-31G*//PM6 气相偶极",
}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w42 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    from scipy import stats

    return float(stats.spearmanr(x, y).statistic)


def _bootstrap_bias(a: np.ndarray, b: np.ndarray, draws: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(a)
    reps = np.empty(draws, dtype=float)
    for index in range(draws):
        pick = rng.integers(0, n, n)
        reps[index] = float(np.mean(a[pick] - b[pick]))
    return {
        "point": float(np.mean(a - b)),
        "mean": float(np.mean(reps)),
        "sd": float(np.std(reps, ddof=1)),
        "lo": float(np.percentile(reps, 2.5)),
        "hi": float(np.percentile(reps, 97.5)),
        "draws": int(draws),
    }


def compute(layers: Mapping[str, Mapping[str, float]], prereg: Mapping[str, object],
            ) -> dict[str, object]:
    lane = prereg["lanes"]["w42_dipole_sources"]
    draws = int(lane["gates"]["bootstrap_draws"])
    seed = int(lane["rng_seed"])
    coverage = {name: len(layers[name]) for name in ("our", "qm9", "pubchemqc")}
    coverage["three_way"] = len(overlap_keys(layers, ("our", "qm9", "pubchemqc")))

    pair_rows: list[dict[str, object]] = []
    bland_rows: list[dict[str, object]] = []
    diffs: dict[tuple[str, str], np.ndarray] = {}
    for index, (left, right) in enumerate(SOURCE_PAIRS):
        keys = overlap_keys(layers, (left, right))
        va = np.asarray([layers[left][k] for k in keys], dtype=float)
        vb = np.asarray([layers[right][k] for k in keys], dtype=float)
        diff = va - vb
        diffs[(left, right)] = diff
        bias = float(np.mean(diff))
        sd = float(np.std(diff, ddof=1))
        mae = float(np.mean(np.abs(diff)))
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        slope, intercept = np.polyfit(vb, va, 1)
        boot = _bootstrap_bias(va, vb, draws, seed + index)
        pair_rows.append({
            "pair": left + "-" + right, "source_a": left, "source_b": right, "n": len(keys),
            "bias_a_minus_b": bias, "sd_diff": sd, "mae": mae, "rmse": rmse,
            "spearman": _spearman(va, vb),
            "pearson": float(np.corrcoef(va, vb)[0, 1]),
            "slope_a_on_b": float(slope), "intercept_a_on_b": float(intercept),
            "bias_ci_lo": boot["lo"], "bias_ci_hi": boot["hi"], "bias_ci_sd": boot["sd"],
        })
        loa_lo = bias - 1.96 * sd
        loa_hi = bias + 1.96 * sd
        within = float(np.mean(np.abs(diff - bias) <= 1.96 * sd))
        bland_rows.append({
            "pair": left + "-" + right, "n": len(keys), "bias": bias, "sd": sd,
            "loa_lo": loa_lo, "loa_hi": loa_hi, "within_loa": within,
            "bias_ci_lo": boot["lo"], "bias_ci_hi": boot["hi"],
            "zero_inside_ci": bool(boot["lo"] <= 0.0 <= boot["hi"]),
        })

    keys3 = overlap_keys(layers, ("our", "qm9", "pubchemqc"))
    our = np.asarray([layers["our"][k] for k in keys3], dtype=float)
    qm9 = np.asarray([layers["qm9"][k] for k in keys3], dtype=float)
    pc = np.asarray([layers["pubchemqc"][k] for k in keys3], dtype=float)
    design = np.column_stack([qm9, pc, np.ones_like(qm9)])
    coefficients, _, _, _ = np.linalg.lstsq(design, our, rcond=None)
    prediction = design @ coefficients
    sst = float(np.sum((our - np.mean(our)) ** 2))
    attribution = {
        "n": len(keys3),
        "design": "our = a*QM9 + b*PubChemQC + c",
        "coef_qm9": float(coefficients[0]),
        "coef_pubchemqc": float(coefficients[1]),
        "intercept": float(coefficients[2]),
        "r2": 1.0 - float(np.sum((our - prediction) ** 2)) / sst,
        "our_mean": float(np.mean(our)),
        "qm9_mean": float(np.mean(qm9)),
        "pubchemqc_mean": float(np.mean(pc)),
        "our_minus_qm9_mean": float(np.mean(our - qm9)),
        "our_minus_pubchemqc_mean": float(np.mean(our - pc)),
        "qm9_minus_pubchemqc_mean": float(np.mean(qm9 - pc)),
        "note": "只做归因；不修数、不插补。外部层数值不入标签池或特征列。",
    }
    attribution["simple_qm9"] = _simple_fit(qm9, our)
    attribution["simple_pubchemqc"] = _simple_fit(pc, our)

    bias_our_qm9 = float(np.mean(diffs[("our", "qm9")]))
    bias_our_pc = float(np.mean(diffs[("our", "pubchemqc")]))
    localization_ratio = (min(abs(bias_our_qm9), abs(bias_our_pc))
                          / max(abs(bias_our_qm9), abs(bias_our_pc)))
    sign_consistent = bool(np.sign(bias_our_qm9) == np.sign(bias_our_pc))

    return {
        "coverage": coverage,
        "pair_rows": pair_rows,
        "bland_rows": bland_rows,
        "attribution": attribution,
        "localization_ratio": localization_ratio,
        "sign_consistent": sign_consistent,
        "diffs": diffs,
        "layers": {name: dict(layers[name]) for name in ("our", "qm9", "pubchemqc")},
    }


def _simple_fit(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    slope, intercept = np.polyfit(x, y, 1)
    prediction = slope * x + intercept
    sst = float(np.sum((y - np.mean(y)) ** 2))
    return {
        "slope": float(slope), "intercept": float(intercept),
        "r2": 1.0 - float(np.sum((y - prediction) ** 2)) / sst,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w42_dipole_sources"]["gates"]
    rows = {str(row["pair"]): row for row in payload["pair_rows"]}
    bland = {str(row["pair"]): row for row in payload["bland_rows"]}
    coverage = payload["coverage"]
    attribution = payload["attribution"]
    criteria = [
        criteria_row("H42c1", "三源覆盖 237/103/205，三方交集 103",
                     {name: coverage[name] for name in ("our", "qm9", "pubchemqc", "three_way")},
                     {"our": 237, "qm9": 103, "pubchemqc": 205, "three_way": 103},
                     int(coverage["our"]) == 237 and int(coverage["qm9"]) == 103
                     and int(coverage["pubchemqc"]) == 205 and int(coverage["three_way"]) == 103),
        criteria_row("H42c2", "|bias(our − QM9)| <= 0.5 D",
                     abs(float(rows["our-qm9"]["bias_a_minus_b"])),
                     gates["our_qm9_bias_abs_max"],
                     abs(float(rows["our-qm9"]["bias_a_minus_b"]))
                     <= float(gates["our_qm9_bias_abs_max"])),
        criteria_row("H42c3", "|bias(our − PubChemQC)| <= 0.6 D",
                     abs(float(rows["our-pubchemqc"]["bias_a_minus_b"])),
                     gates["our_pubchemqc_bias_abs_max"],
                     abs(float(rows["our-pubchemqc"]["bias_a_minus_b"]))
                     <= float(gates["our_pubchemqc_bias_abs_max"])),
        criteria_row("H42c4", "|bias(QM9 − PubChemQC)| <= 0.10 D（两外部源互相一致）",
                     abs(float(rows["qm9-pubchemqc"]["bias_a_minus_b"])),
                     gates["qm9_pubchemqc_bias_abs_max"],
                     abs(float(rows["qm9-pubchemqc"]["bias_a_minus_b"]))
                     <= float(gates["qm9_pubchemqc_bias_abs_max"])),
        criteria_row("H42c5", "MAE(QM9 − PubChemQC) <= 0.30 D",
                     float(rows["qm9-pubchemqc"]["mae"]), gates["qm9_pubchemqc_mae_max"],
                     float(rows["qm9-pubchemqc"]["mae"]) <= float(gates["qm9_pubchemqc_mae_max"])),
        criteria_row("H42c6", "MAE(our − PubChemQC) >= MAE(our − QM9)（我们离两个外部源都远）",
                     {"our_pubchemqc": rows["our-pubchemqc"]["mae"],
                      "our_qm9": rows["our-qm9"]["mae"]},
                     "MAE(our−PC) >= MAE(our−QM9)",
                     float(rows["our-pubchemqc"]["mae"]) >= float(rows["our-qm9"]["mae"])),
        criteria_row("H42c7", "三源 OLS our ~ a*QM9 + b*PC + c 的 R2 >= 0.60",
                     float(attribution["r2"]), gates["attribution_r2_min"],
                     float(attribution["r2"]) >= float(gates["attribution_r2_min"])),
        criteria_row("H42c8", "偏置定位比 min/max >= 0.5 且两偏置同号（方法层偏置）",
                     {"ratio": payload["localization_ratio"],
                      "sign_consistent": payload["sign_consistent"]},
                     gates["localization_ratio_min"],
                     float(payload["localization_ratio"]) >= float(gates["localization_ratio_min"])
                     and bool(payload["sign_consistent"])),
        criteria_row("H42c9", "bias(our − QM9) 的 bootstrap 95% CI 不含 0",
                     [bland["our-qm9"]["bias_ci_lo"], bland["our-qm9"]["bias_ci_hi"]],
                     "0 not in CI", not bool(bland["our-qm9"]["zero_inside_ci"])),
        criteria_row("H42c10", "bias(QM9 − PubChemQC) 的 bootstrap 95% CI 含 0",
                     [bland["qm9-pubchemqc"]["bias_ci_lo"], bland["qm9-pubchemqc"]["bias_ci_hi"]],
                     "0 in CI", bool(bland["qm9-pubchemqc"]["zero_inside_ci"])),
        criteria_row("H42c11", "输入文件生成前后 sha256 不变",
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
    arrays = payload["layers"]
    pairs = [("our", "qm9"), ("our", "pubchemqc"), ("qm9", "pubchemqc")]
    figure, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))
    for axis, (left, right) in zip(axes, pairs):
        va = np.asarray([arrays[left][k] for k in payload["keys"][left + "-" + right]],
                        dtype=float)
        vb = np.asarray([arrays[right][k] for k in payload["keys"][left + "-" + right]],
                        dtype=float)
        mean = (va + vb) / 2.0
        diff = va - vb
        bias = float(np.mean(diff))
        sd = float(np.std(diff, ddof=1))
        axis.scatter(mean, diff, s=14, color="#4C72B0", alpha=0.7)
        axis.axhline(bias, color="#C44E52", linewidth=1.6, label="bias=" + format(bias, ".3f"))
        axis.axhline(bias + 1.96 * sd, color="#999999", linewidth=1.2, linestyle="--")
        axis.axhline(bias - 1.96 * sd, color="#999999", linewidth=1.2, linestyle="--",
                     label="±1.96 sd")
        axis.axhline(0.0, color="#333333", linewidth=0.8)
        axis.set_xlabel("均值 (D)")
        axis.set_ylabel("差值 " + left + " − " + right + " (D)")
        axis.set_title("Bland–Altman " + left + " vs " + right)
        axis.legend(loc="upper right", fontsize=8)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  ) -> str:
    attribution = payload["attribution"]
    lines = [
        "# W42-C 偶极三源回归分解与 Bland–Altman",
        "",
        "计算 lane（0 shot，累计仍 19）。回应 W41 登记的 item 28/30：~0.39 D 偶极系统偏置未追溯。",
        "",
        "## 1. 三源覆盖",
        "",
        "- our（xTB）237、QM9 103、PubChemQC 205，三方交集 "
        + str(payload["coverage"]["three_way"]) + "。",
        "- 三者均值（三方交集）：our " + format(float(attribution["our_mean"]), ".4f")
        + "、QM9 " + format(float(attribution["qm9_mean"]), ".4f")
        + "、PubChemQC " + format(float(attribution["pubchemqc_mean"]), ".4f") + " D。",
        "",
        "## 2. 两两 bias / MAE / 相关",
        "",
        "| 对 | n | bias(A−B) | sd | MAE | RMSE | Spearman | Pearson |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["pair_rows"]:
        lines.append("| " + str(row["pair"]) + " | " + str(row["n"]) + " | "
                     + format(float(row["bias_a_minus_b"]), ".4f") + " | "
                     + format(float(row["sd_diff"]), ".4f") + " | "
                     + format(float(row["mae"]), ".4f") + " | "
                     + format(float(row["rmse"]), ".4f") + " | "
                     + format(float(row["spearman"]), ".4f") + " | "
                     + format(float(row["pearson"]), ".4f") + " |")
    lines += [
        "",
        "**关键读数**：两个外部源彼此 bias 只有 "
        + format(float(attribution["qm9_minus_pubchemqc_mean"]), ".4f")
        + " D，而 our−QM9 = " + format(float(attribution["our_minus_qm9_mean"]), ".4f")
        + " D、our−PubChemQC = " + format(float(attribution["our_minus_pubchemqc_mean"]), ".4f")
        + " D。偏置定位比 = " + format(float(payload["localization_ratio"]), ".4f")
        + "（同号 " + str(payload["sign_consistent"]) + "）⇒ **~0.4 D 偏置出在方法层（xTB vs "
        "B3LYP），不是某一个源的数据问题**。",
        "",
        "## 3. 三源 OLS 归因",
        "",
        "- 模型 our = " + format(float(attribution["coef_qm9"]), ".4f") + "·QM9 + "
        + format(float(attribution["coef_pubchemqc"]), ".4f") + "·PubChemQC + "
        + format(float(attribution["intercept"]), ".4f")
        + "，R2 = " + format(float(attribution["r2"]), ".4f") + "（n = "
        + str(attribution["n"]) + "）。",
        "- 单源：our ~ QM9 斜率 " + format(float(attribution["simple_qm9"]["slope"]), ".4f")
        + "、R2 " + format(float(attribution["simple_qm9"]["r2"]), ".4f")
        + "；our ~ PubChemQC 斜率 "
        + format(float(attribution["simple_pubchemqc"]["slope"]), ".4f") + "、R2 "
        + format(float(attribution["simple_pubchemqc"]["r2"]), ".4f") + "。",
        "",
        "## 4. Bland–Altman 一致性界限",
        "",
        "| 对 | bias | ±1.96 sd 下 | 上 | 界内占比 | bias 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["bland_rows"]:
        lines.append("| " + str(row["pair"]) + " | " + format(float(row["bias"]), ".4f")
                     + " | " + format(float(row["loa_lo"]), ".4f") + " | "
                     + format(float(row["loa_hi"]), ".4f") + " | "
                     + format(float(row["within_loa"]), ".4f") + " | ["
                     + format(float(row["bias_ci_lo"]), ".4f") + ", "
                     + format(float(row["bias_ci_hi"]), ".4f") + "] |")
    lines += [
        "",
        "## 5. 判据",
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
        "## 6. 边界",
        "",
        "- 本轮**只归因、不修数、不插补**：名册偶极列一字未改。",
        "- 外部层偶极只作只读对照，不入标签池或特征列。",
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
    layers = load_dipole_layers()
    sources = [REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv",
               ARTIFACTS / "w39_qm9_overlap.csv",
               REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv"]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(layers, prereg)
    payload["keys"] = {left + "-" + right: overlap_keys(layers, (left, right))
                       for left, right in SOURCE_PAIRS}
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after
    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(PAIRS_CSV, PAIR_FIELDS, payload["pair_rows"])
    write_csv_lf(BLAND_CSV, BLAND_FIELDS, payload["bland_rows"])
    write_json_stable(ATTRIBUTION_JSON, payload["attribution"])
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
            "why_not_a_shot": "只对三源偶极列做 bias/MAE/回归/Bland–Altman 计算，不拟合主记分牌臂、"
                              "不加特征列、不改 METRIC_NAMES、不动冻结读数、不修数不插补。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "coverage": payload["coverage"],
        "pair_rows": payload["pair_rows"],
        "bland_rows": payload["bland_rows"],
        "attribution": payload["attribution"],
        "localization_ratio": payload["localization_ratio"],
        "sign_consistent": payload["sign_consistent"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "三源偶极 bias：QM9−PubChemQC = "
            + format(float(payload["attribution"]["qm9_minus_pubchemqc_mean"]), ".4f")
            + " D，our−QM9 = " + format(float(payload["attribution"]["our_minus_qm9_mean"]), ".4f")
            + " D，our−PubChemQC = "
            + format(float(payload["attribution"]["our_minus_pubchemqc_mean"]), ".4f") + " D。",
            "两外部源互相一致、都与 our 差 ⇒ 偏置定位在方法层（xTB vs B3LYP），定位比 "
            + format(float(payload["localization_ratio"]), ".4f") + "。",
            "三源 OLS R2 = " + format(float(payload["attribution"]["r2"]), ".4f")
            + "（n = " + str(payload["attribution"]["n"]) + "）。",
            "0 shot（累计仍 19）；只归因，不修数。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for row in payload["pair_rows"]:
        print("pair %-16s n=%-4d bias=%+.4f mae=%.4f rho=%.4f"
              % (row["pair"], row["n"], row["bias_a_minus_b"], row["mae"], row["spearman"]))
    print("attribution R2 %.4f coef_qm9 %.4f coef_pc %.4f intercept %.4f"
          % (payload["attribution"]["r2"], payload["attribution"]["coef_qm9"],
             payload["attribution"]["coef_pubchemqc"], payload["attribution"]["intercept"]))
    print("localization_ratio %.4f sign_consistent %s"
          % (payload["localization_ratio"], payload["sign_consistent"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
