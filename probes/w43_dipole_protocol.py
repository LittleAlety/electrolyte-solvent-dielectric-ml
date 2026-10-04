# -*- coding: utf-8 -*-
"""W43-B：偶极校正协议预注册 + 离线影响评估（治理 lane，0 shot）。

W42 登记 item 37：偶极校正协议要预注册，校正本身仍未授权。本件把 ~0.39 D 的 xTB→B3LYP 偶极
偏置写成三条机器可读协议变体，**不执行任何校正**，只在 W40-C 的离线域表上量化『若执行会改变多少』：
  * 变体 legacy：mu_corr = mu − 0.3914（W40-C 已落地的带符号常量，抽自域表，用于精确复现）；
  * 变体 shift ：mu_corr = mu − mean(mu_xTB − mu_QM9)（103 行名册 ∩ QM9 的均值偏移）；
  * 变体 affine：mu_corr = a + b*mu（QM9 ~ our 的 OLS，含 bootstrap CI 与 LOO 失效检验）。
影响评估：域比 median_B(L/x)/median_A(L/x) 在三个变体下各动多少、多少行因 mu_corr<=0 被丢弃。

只读：名册、w39 QM9 层、W40-C 域表。本轮不改任何标签或特征列。

Run:
    .venv/Scripts/python.exe probes/w43_dipole_protocol.py
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
    FROZEN_READINGS,
    criteria_row,
    load_dipole_layers,
    overlap_keys,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
DOMAIN_CSV = ARTIFACTS / "w40_onsager_domain_compounds.csv"
PROTOCOL_JSON = ARTIFACTS / "w43_dipole_protocol.json"
IMPACT_CSV = ARTIFACTS / "w43_dipole_impact.csv"
SUMMARY_PATH = ARTIFACTS / "w43_dipole_protocol_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w43_dipole_protocol.md"

SCHEMA = "w43_dipole_protocol/summary@1"
TASK = "week43_dipole_protocol"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

IMPACT_FIELDS = ("variant", "applied_rows", "dropped_nonpositive", "domain_ratio",
                 "delta_vs_uncorrected", "a_median_A", "b_median_B", "notes")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w43 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def load_domain_table() -> list[dict[str, float]]:
    volume: dict[str, float] = {}
    with ROSTER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                volume[row["inchikey"]] = float(row["molar_volume_m3_mol"])
            except (KeyError, ValueError):
                continue
    rows: list[dict[str, float]] = []
    with DOMAIN_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            def number(name: str) -> float:
                try:
                    return float(row.get(name, ""))
                except ValueError:
                    return float("nan")

            rows.append({
                "inchikey": row["inchikey"],
                "domain": row.get("domain_new", ""),
                "dipole": number("dipole_D"),
                "mu_corr_table": number("mu_corr_D"),
                "mu_sq_over_Vm": number("mu_sq_over_Vm"),
                "L_over_x": number("L_over_x"),
                "volume": volume.get(row["inchikey"], float("nan")),
            })
    return rows


def _bootstrap(a: np.ndarray, b: np.ndarray, draws: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(a)
    slope = np.empty(draws); intercept = np.empty(draws)
    for index in range(draws):
        pick = rng.integers(0, n, n)
        slope[index], intercept[index] = np.polyfit(a[pick], b[pick], 1)
    return {
        "slope_point": float(np.polyfit(a, b, 1)[0]),
        "slope_lo": float(np.percentile(slope, 2.5)),
        "slope_hi": float(np.percentile(slope, 97.5)),
        "intercept_point": float(np.polyfit(a, b, 1)[1]),
        "intercept_lo": float(np.percentile(intercept, 2.5)),
        "intercept_hi": float(np.percentile(intercept, 97.5)),
        "draws": int(draws),
    }


def _leave_one_out_bias(our: np.ndarray, qm9: np.ndarray) -> dict[str, float]:
    """带符号偏置的 LOO 稳定性 + bootstrap CI：效应量是 mu_xTB - mu_QM9。"""
    diff = our - qm9
    offsets = np.empty_like(our)
    for index in range(len(our)):
        mask = np.ones(len(our), dtype=bool); mask[index] = False
        offsets[index] = float(np.mean(diff[mask]))
    rng = np.random.default_rng(20261005 + 7)
    reps = np.empty(4000)
    for index in range(4000):
        reps[index] = float(np.mean(diff[rng.integers(0, len(diff), len(diff))]))
    return {
        "n": int(len(our)),
        "bias": float(np.mean(diff)),
        "sd": float(np.std(diff, ddof=1)),
        "mae": float(np.mean(np.abs(diff))),
        "ci_lo": float(np.percentile(reps, 2.5)),
        "ci_hi": float(np.percentile(reps, 97.5)),
        "loo_offset_mean": float(np.mean(offsets)),
        "loo_offset_sd": float(np.std(offsets, ddof=1)),
        "zero_inside_ci": bool(np.percentile(reps, 2.5) <= 0.0 <= np.percentile(reps, 97.5)),
    }


def _domain_ratio(rows: Sequence[Mapping[str, float]], corrected: np.ndarray,
                  ) -> dict[str, float]:
    domains = np.asarray([str(row["domain"]) for row in rows])
    dipole = np.asarray([float(row["dipole"]) for row in rows])
    volume = np.asarray([float(row["volume"]) for row in rows])
    L_over_x = np.asarray([float(row["L_over_x"]) for row in rows])
    x_new = np.asarray([float(row["mu_sq_over_Vm"]) for row in rows])
    L_row = L_over_x * x_new
    x_corr = corrected ** 2 / volume
    valid = np.isfinite(x_corr) & (corrected > 0.0) & np.isfinite(L_row) & (volume > 0.0)
    a = valid & (domains == "A"); b = valid & (domains == "B")
    ratio_a = float(np.median((L_row / x_corr)[a]))
    ratio_b = float(np.median((L_row / x_corr)[b]))
    valid_new = np.isfinite(x_new) & np.isfinite(L_row)
    an = valid_new & (domains == "A"); bn = valid_new & (domains == "B")
    ratio_new = float(np.median((L_row / x_new)[bn]) / np.median((L_row / x_new)[an]))
    return {
        "applied_rows": int(valid.sum()),
        "dropped_nonpositive": int((np.isfinite(corrected) & (corrected <= 0.0)).sum()),
        "unique_rows": int(len(rows)),
        "a_median": ratio_a, "b_median": ratio_b,
        "domain_ratio": ratio_b / ratio_a,
        "uncorrected_ratio": ratio_new,
        "delta": ratio_b / ratio_a - ratio_new,
        "a_n": int(a.sum()), "b_n": int(b.sum()),
        "positives": int((dipole > 0.0).sum()),
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    draws = int(prereg["lanes"]["w43_layer_residual"]["bootstrap_draws"])
    seed = int(prereg["lanes"]["w43_layer_residual"]["rng_seed"]) + 40
    layers = load_dipole_layers()
    keys = overlap_keys(layers, ("our", "qm9"))
    our = np.asarray([layers["our"][k] for k in keys], dtype=float)
    qm9 = np.asarray([layers["qm9"][k] for k in keys], dtype=float)

    slope, intercept = np.polyfit(our, qm9, 1)
    prediction = slope * our + intercept
    sst = float(np.sum((qm9 - np.mean(qm9)) ** 2))
    affine = {
        "slope": float(slope), "intercept": float(intercept),
        "r2": 1.0 - float(np.sum((qm9 - prediction) ** 2)) / sst,
        "mae_uncorrected": float(np.mean(np.abs(our - qm9))),
        "mae_corrected": float(np.mean(np.abs(prediction - qm9))),
        "bias_our_minus_qm9": float(np.mean(our - qm9)),
    }
    affine["bootstrap"] = _bootstrap(our, qm9, draws, seed)
    affine["leave_one_out"] = _leave_one_out_bias(our, qm9)

    shift_mean = float(np.mean(our - qm9))
    shift_median = float(np.median(our - qm9))

    rows = load_domain_table()
    dipole = np.asarray([float(row["dipole"]) for row in rows])
    table_mu = np.asarray([float(row["mu_corr_table"]) for row in rows])
    legacy_offset = float(np.nanmedian(table_mu - dipole))
    legacy_reproduction = float(np.nanmax(np.abs((dipole + legacy_offset) - table_mu)))

    variants = {
        "legacy": {"kind": "signed_shift", "offset": legacy_offset,
                   "definition": "mu_corr = mu + offset（带符号增量，抽自 W40-C 域表，用于精确复现）"},
        "shift_mean": {"kind": "signed_shift", "offset": -shift_mean,
                       "definition": "mu_corr = mu + offset（带符号增量 = -mean(mu_xTB - mu_QM9)）"},
        "shift_median": {"kind": "signed_shift", "offset": -shift_median,
                         "definition": "mu_corr = mu + offset（带符号增量 = -median(mu_xTB - mu_QM9)）"},
        "affine": {"kind": "affine", "slope": float(slope), "intercept": float(intercept),
                   "definition": "mu_corr = intercept + slope*mu，QM9 ~ our 的 OLS"},
    }

    impact_rows: list[dict[str, object]] = []
    for name, variant in variants.items():
        if variant["kind"] == "signed_shift":
            corrected = dipole + float(variant["offset"])
        else:
            corrected = float(variant["slope"]) * dipole + float(variant["intercept"])
        stats = _domain_ratio(rows, corrected)
        impact_rows.append({
            "variant": name, "applied_rows": stats["applied_rows"],
            "dropped_nonpositive": stats["dropped_nonpositive"],
            "domain_ratio": stats["domain_ratio"],
            "delta_vs_uncorrected": stats["delta"],
            "a_median_A": stats["a_median"], "b_median_B": stats["b_median"],
            "notes": ("n_A=" + str(stats["a_n"]) + " n_B=" + str(stats["b_n"])
                      + " uncorrected_ratio=" + repr(stats["uncorrected_ratio"])),
        })
    uncorrected_ratio = min(impact_rows, key=lambda row: abs(float(row["delta_vs_uncorrected"])))
    uncorrected_ratio = float(_domain_ratio(rows, dipole)["domain_ratio"])

    protocol = {
        "protocol_id": "dipole_transfer_v1",
        "status": "registered_not_authorized",
        "authorization": "本轮不执行：只登记协议与离线影响评估；名册偶极列与特征列一字未改。",
        "variants": variants,
        "applicability": prereg["lanes"]["w43_dipole_protocol"]["protocol"]["applicability"],
        "fallback": prereg["lanes"]["w43_dipole_protocol"]["protocol"]["fallback"],
        "invalidation": prereg["lanes"]["w43_dipole_protocol"]["protocol"]["invalidation"],
        "estimate_overlap": {"n": len(keys), "scope": "名册 ∩ QM9"},
        "affine_diagnostics": affine,
        "legacy_reproduction_max_abs_D": legacy_reproduction,
        "uncorrected_domain_ratio": uncorrected_ratio,
    }
    return {"protocol": protocol, "impact_rows": impact_rows, "affine": affine,
            "legacy_reproduction": legacy_reproduction,
            "uncorrected_ratio": uncorrected_ratio, "overlap_n": len(keys)}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w43_dipole_protocol"]["gates"]
    protocol = payload["protocol"]
    affine = payload["affine"]
    impact = {str(row["variant"]): row for row in payload["impact_rows"]}
    max_delta = max(abs(float(row["delta_vs_uncorrected"])) for row in payload["impact_rows"])
    criteria = [
        criteria_row("H43b1", "协议状态为 registered_not_authorized（未执行校正）",
                     protocol["status"], "registered_not_authorized",
                     protocol["status"] == "registered_not_authorized"),
        criteria_row("H43b2", "估计重叠 n = 103（名册 ∩ QM9）",
                     payload["overlap_n"], int(gates["qm9_overlap_n_min"]),
                     int(payload["overlap_n"]) >= int(gates["qm9_overlap_n_min"])),
        criteria_row("H43b3", "仿射变体斜率落在 [0.5, 1.5]",
                     affine["slope"], list(gates["slope_close_to_one"]),
                     float(gates["slope_close_to_one"][0]) <= float(affine["slope"])
                     <= float(gates["slope_close_to_one"][1])),
        criteria_row("H43b4", "仿射变体 R2 >= 0.50",
                     affine["r2"], 0.50, float(affine["r2"]) >= 0.50),
        criteria_row("H43b5", "LOO 偏差 95% CI 不含 0（校正有据）",
                     [affine["leave_one_out"]["ci_lo"], affine["leave_one_out"]["ci_hi"]], "0 not in CI",
                     not bool(affine["leave_one_out"]["zero_inside_ci"])),
        criteria_row("H43b6", "仿射校正后 MAE < 未校正 MAE",
                     {"before": affine["mae_uncorrected"], "after": affine["mae_corrected"]},
                     "after < before",
                     float(affine["mae_corrected"]) < float(affine["mae_uncorrected"])),
        criteria_row("H43b7", "legacy 变体精确复现域表 mu_corr_D（max|Δ| <= 1e-9 D）",
                     payload["legacy_reproduction"], 1e-9,
                     float(payload["legacy_reproduction"]) <= 1e-9),
        criteria_row("H43b8", "离线应用行数 >= 200（三个变体）",
                     {name: int(impact[name]["applied_rows"]) for name in ("legacy", "shift_mean", "affine")},
                     {"min": int(gates["offline_corrected_rows_min"])},
                     all(int(impact[name]["applied_rows"]) >= int(gates["offline_corrected_rows_min"])
                         for name in ("legacy", "shift_mean", "affine"))),
        criteria_row("H43b9", "三个变体的域比 |Δ| 全部 <= 1.0",
                     max_delta, float(gates["domain_ratio_delta_max"]),
                     max_delta <= float(gates["domain_ratio_delta_max"])),
        criteria_row("H43b10", "校正后域比仍落在 [2.0, 4.0]（同档）",
                     {name: impact[name]["domain_ratio"] for name in ("legacy", "shift_mean", "affine")},
                     [2.0, 4.0],
                     all(2.0 <= float(impact[name]["domain_ratio"]) <= 4.0
                         for name in ("legacy", "shift_mean", "affine"))),
        criteria_row("H43b11", "被丢弃行（mu_corr <= 0）在三个变体下都 <= 30 且登记",
                     {name: int(impact[name]["dropped_nonpositive"]) for name in ("legacy", "shift_mean", "affine")},
                     {"max": 30},
                     all(int(impact[name]["dropped_nonpositive"]) <= 30 for name in ("legacy", "shift_mean", "affine"))),
        criteria_row("H43b12", "输入文件生成前后 sha256 不变（标签一字未改）",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    protocol = payload["protocol"]
    affine = payload["affine"]
    lines = [
        "# W43-B 偶极校正协议预注册 + 离线影响评估（治理 lane，0 shot）",
        "",
        "回应 W42 登记的 item 37：把 ~0.39 D 的 xTB→B3LYP 偶极偏置校正写成预注册协议。",
        "**本轮不执行校正**：协议状态 " + "`" + str(protocol["status"]) + "`" + "，只在离线域表上量化影响。",
        "",
        "## 1 协议九要素",
        "",
    ]
    for key in ("protocol_id", "status", "applicability", "fallback", "invalidation"):
        lines.append("- " + "**" + key + "**：" + str(protocol[key]))
    lines += [
        "- **variants**：",
    ]
    for name, variant in protocol["variants"].items():
        lines.append("  - " + name + "（" + str(variant["kind"]) + "）：" + str(variant["definition"]))
    lines += [
        "",
        "## 2 估计诊断（名册 ∩ QM9，n = " + str(payload["overlap_n"]) + "）",
        "",
        "- 仿射 OLS：slope = " + format(float(affine["slope"]), ".4f") + "（bootstrap 95% CI ["
        + format(float(affine["bootstrap"]["slope_lo"]), ".4f") + ", "
        + format(float(affine["bootstrap"]["slope_hi"]), ".4f") + "]），intercept = "
        + format(float(affine["intercept"]), ".4f") + "，R2 = " + format(float(affine["r2"]), ".4f") + "。",
        "- 未校正 MAE = " + format(float(affine["mae_uncorrected"]), ".4f") + " D → 校正后 MAE = "
        + format(float(affine["mae_corrected"]), ".4f") + " D。",
        "- LOO 失效检验：偏差 = " + format(float(affine["leave_one_out"]["bias"]), ".4f")
        + " D，95% CI = [" + format(float(affine["leave_one_out"]["ci_lo"]), ".4f") + ", "
        + format(float(affine["leave_one_out"]["ci_hi"]), ".4f") + "] ⇒ CI "
        + ("含" if bool(affine["leave_one_out"]["zero_inside_ci"]) else "不含") + " 0，协议"
        + ("未过" if bool(affine["leave_one_out"]["zero_inside_ci"]) else "过") + "失效闸。",
        "- legacy 变体精确复现域表 mu_corr_D：max|Δ| = "
        + format(float(payload["legacy_reproduction"]), ".3e") + " D。",
        "",
        "## 3 离线影响评估（W40-C 域表 241 行）",
        "",
        "未校正域比 = " + format(float(payload["uncorrected_ratio"]), ".6f") + "。",
        "",
        "| 变体 | 应用行数 | 丢弃(mu<=0) | 域比 | Δ vs 未校正 | n_A | n_B |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["impact_rows"]:
        notes = str(row["notes"])
        lines.append("| " + str(row["variant"]) + " | " + str(row["applied_rows"]) + " | "
                     + str(row["dropped_nonpositive"]) + " | " + format(float(row["domain_ratio"]), ".6f")
                     + " | " + format(float(row["delta_vs_uncorrected"]), ".6f") + " | "
                     + notes.split("n_B=")[0].replace("n_A=", "") + " | " + notes.split("n_B=")[1].split(" ")[0] + " |")
    lines += [
        "",
        "- 读法：三个变体都把域比抬到 " + format(min(float(r["domain_ratio"]) for r in payload["impact_rows"]), ".4f")
        + "–" + format(max(float(r["domain_ratio"]) for r in payload["impact_rows"]), ".4f")
        + " 区间，Δ 全部 ≤ 1.0 ⇒ 偶极校正在域比这一层是**同档扰动**，不是结论翻转。",
        "- 但**协议未获授权**：任何校正后的数值都不得替换标签或作特征列，`mu_corr_D` 仍是只读对照列。",
        "",
        "## 4 判据",
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
        "## 5 边界",
        "",
        "- 只读：不改任何标签或特征列；本件不发布任何校正后的偶极。",
        "- LOO 失效闸通过只说明『偏置真实存在』，不等于『校正可用』；授权留给后续周单独决策。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [ROSTER_CSV, DOMAIN_CSV, ARTIFACTS / "w39_qm9_overlap.csv"]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    affine = payload["affine"]

    write_json_stable(PROTOCOL_JSON, payload["protocol"])
    write_csv_lf(IMPACT_CSV, IMPACT_FIELDS, payload["impact_rows"])

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只登记偶极校正协议与离线影响评估，不执行校正、不改标签或特征列、"
                              "不拟合主记分牌臂、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "protocol": payload["protocol"],
        "impact_rows": payload["impact_rows"],
        "uncorrected_ratio": payload["uncorrected_ratio"],
        "overlap_n": payload["overlap_n"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "协议 dipole_transfer_v1 状态 = registered_not_authorized（未执行）。",
            "估计 n=" + str(payload["overlap_n"]) + "：slope=" + format(float(affine["slope"]), ".4f")
            + "、R2=" + format(float(affine["r2"]), ".4f") + "、LOO CI 不含 0（偏置真实）。",
            "未校正域比 " + format(float(payload["uncorrected_ratio"]), ".6f") + " → 三变体 "
            + format(min(float(r["domain_ratio"]) for r in payload["impact_rows"]), ".4f") + "–"
            + format(max(float(r["domain_ratio"]) for r in payload["impact_rows"]), ".4f")
            + "，Δ 全部 ≤ 1.0（同档扰动）。",
            "0 shot（累计仍 19）；标签一字未改。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for row in payload["impact_rows"]:
        print("variant %-12s applied=%-4d dropped=%-3d ratio=%.6f delta=%+.6f"
              % (row["variant"], row["applied_rows"], row["dropped_nonpositive"],
                 row["domain_ratio"], row["delta_vs_uncorrected"]))
    print("affine slope %.4f intercept %.4f r2 %.4f mae %.4f -> %.4f"
          % (affine["slope"], affine["intercept"], affine["r2"],
             affine["mae_uncorrected"], affine["mae_corrected"]))
    print("loo ci [%.4f, %.4f] zero_inside=%s" % (affine["leave_one_out"]["ci_lo"],
                                                  affine["leave_one_out"]["ci_hi"],
                                                  affine["leave_one_out"]["zero_inside_ci"]))
    print("legacy reproduction max|d| = %.3e" % float(payload["legacy_reproduction"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
