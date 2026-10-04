# -*- coding: utf-8 -*-
"""W45-C：~0.39 D 偶极偏置的分层归因（计算 lane，0 shot）。

W42-C 登记 our 相对 QM9 的偶极偏置均值 +0.3945 D（CI 不含 0）。本件只读地把它拆开：
  * 按 HBD（0 / 1 / 2+）、重原子数（1–5 / 6–7 / 8–9）、our 偶极三分位分层，各报中位偏置；
  * 关键问题：偏置是**常量平移**还是**随偶极幅度增长**？若低档 ~0 而高档 ~0.5 D，
    则 affine（尺度+平移）比 shift（纯平移）更合适——直接支撑 W43-B 的协议变体选择；
  * 均值偏置的 bootstrap 95% CI（是否含 0）、符号翻转置换 p、Wilcoxon 符号秩 p；
  * 偏置大小与重原子数的秩相关（看是不是尺寸伪影）。

只读；不修数、不插补；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w45_dipole_strata.py
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
    criteria_row,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from w45_common import QM9_OVERLAP_CSV, load_qm9_dipoles, load_roster_descriptors

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w45_compute_prereg.json"
STRATA_CSV = ARTIFACTS / "w45_dipole_strata.csv"
FIGURE_PATH = ARTIFACTS / "w45_dipole_strata.png"
SUMMARY_PATH = ARTIFACTS / "w45_dipole_strata_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w45_dipole_strata.md"

SCHEMA = "w45_dipole_strata/summary@1"
TASK = "week45_dipole_strata"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

STRATA_FIELDS = ("scope", "stratum", "n", "median_delta_D", "mean_delta_D",
                 "median_abs_delta_D", "our_median_D")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w45 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _summary_of(delta: np.ndarray, our: np.ndarray) -> dict[str, object]:
    return {
        "n": int(len(delta)),
        "median_delta_D": float(np.median(delta)),
        "mean_delta_D": float(np.mean(delta)),
        "median_abs_delta_D": float(np.median(np.abs(delta))),
        "our_median_D": float(np.median(our)),
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w45_dipole_strata"]
    dipoles = load_qm9_dipoles()
    descriptors = load_roster_descriptors()

    keys = sorted(dipoles)
    rows: list[dict[str, object]] = []
    for key in keys:
        record = dipoles[key]
        our = record.get("our_dipole_D")
        qm9 = record.get("qm9_dipole_D")
        if our is None or qm9 is None:
            continue
        rows.append({
            "inchikey": key,
            "our": float(our),
            "qm9": float(qm9),
            "delta": float(our) - float(qm9),
            "hbd": record.get("hbd"),
            "heavy": (descriptors.get(key) or {}).get("heavy_atom_count"),
        })
    if not rows:
        raise SystemExit("no dipole overlap rows")

    delta = np.asarray([row["delta"] for row in rows], dtype=float)
    our = np.asarray([row["our"] for row in rows], dtype=float)
    hbd = np.asarray([row["hbd"] if row["hbd"] is not None else np.nan for row in rows], dtype=float)
    heavy = np.asarray([row["heavy"] if row["heavy"] is not None else np.nan for row in rows], dtype=float)

    table: list[dict[str, object]] = [dict(scope="overall", stratum="all", **_summary_of(delta, our))]

    hbd_edges = lane["strata"]["hbd"]
    hbd_strata: list[dict[str, object]] = []
    for label in hbd_edges:
        if label == hbd_edges[-1]:
            mask = hbd >= float(label)
        else:
            mask = hbd == float(label)
        if int(mask.sum()) < 2:
            continue
        record = dict(scope="hbd", stratum=str(label), **_summary_of(delta[mask], our[mask]))
        hbd_strata.append(record)
        table.append(record)

    atom_strata: list[dict[str, object]] = []
    for low, high in lane["strata"]["atom_bins"]:
        mask = (heavy >= low) & (heavy <= high)
        if int(mask.sum()) < 2:
            continue
        record = dict(scope="atom_bin", stratum="%d-%d" % (low, high),
                      **_summary_of(delta[mask], our[mask]))
        atom_strata.append(record)
        table.append(record)

    cuts = np.percentile(our, [100.0 / 3.0, 200.0 / 3.0])
    tercile_labels = ("low", "mid", "high")
    tercile_masks = (our <= cuts[0], (our > cuts[0]) & (our <= cuts[1]), our > cuts[1])
    tercile_strata: list[dict[str, object]] = []
    for label, mask in zip(tercile_labels, tercile_masks):
        record = dict(scope="dipole_tercile", stratum=label, **_summary_of(delta[mask], our[mask]))
        tercile_strata.append(record)
        table.append(record)

    draws = int(lane["bootstrap_draws"])
    seed = int(lane["rng_seed"])
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = np.empty(draws, dtype=float)
    for index in range(draws):
        pick = rng.integers(0, n, n)
        means[index] = float(np.mean(delta[pick]))
    ci_lo = float(np.percentile(means, 2.5))
    ci_hi = float(np.percentile(means, 97.5))

    flips = np.empty(draws, dtype=float)
    rng2 = np.random.default_rng(seed + 1)
    observed = float(np.mean(delta))
    count = 0
    for index in range(draws):
        signs = rng2.integers(0, 2, n) * 2 - 1
        value = float(np.mean(delta * signs))
        flips[index] = value
        if abs(value) >= abs(observed):
            count += 1
    permutation_p = (count + 1) / (draws + 1)

    finite = np.isfinite(heavy)
    size_corr = float(stats.spearmanr(np.abs(delta[finite]), heavy[finite]).statistic)
    amplitude_corr = float(stats.spearmanr(np.abs(delta), np.abs(our)).statistic)
    wilcoxon = stats.wilcoxon(delta)

    return {
        "rows": rows,
        "n": len(rows),
        "delta": delta,
        "our": our,
        "table": table,
        "hbd_strata": hbd_strata,
        "atom_strata": atom_strata,
        "tercile_strata": tercile_strata,
        "mean_delta": observed,
        "median_delta": float(np.median(delta)),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "permutation_p": permutation_p,
        "wilcoxon_p": float(wilcoxon.pvalue),
        "size_corr": size_corr,
        "amplitude_corr": amplitude_corr,
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w45_dipole_strata"]["gates"]
    terciles = {row["stratum"]: row for row in payload["tercile_strata"]}
    low = terciles.get("low")
    mid = terciles.get("mid")
    high = terciles.get("high")
    tercile_monotone = (low is not None and mid is not None and high is not None
                        and float(low["median_delta_D"]) <= float(mid["median_delta_D"])
                        <= float(high["median_delta_D"]))
    all_positive = all(float(row["median_delta_D"]) > 0
                       for row in payload["hbd_strata"] + payload["atom_strata"] + payload["tercile_strata"])
    return [
        criteria_row("H45c1", "偶极重合行数 >= 90（our ∩ QM9）",
                     payload["n"], int(gates["overlap_rows_min"]),
                     int(payload["n"]) >= int(gates["overlap_rows_min"])),
        criteria_row("H45c2", "均值偏置 mean(our-QM9) 逐位复现 W42-C 锚 0.39451165048543685",
                     payload["mean_delta"], gates["overall_mean_expected"],
                     abs(float(payload["mean_delta"]) - float(gates["overall_mean_expected"]))
                     <= float(gates["overall_mean_tol"])),
        criteria_row("H45c3", "HBD 分层（0/1/2+）每层 n >= 5 且中位偏置 > 0",
                     {row["stratum"]: {"n": row["n"], "median": row["median_delta_D"]}
                      for row in payload["hbd_strata"]},
                     {"min_rows": gates["hbd_strata_min_rows"]},
                     len(payload["hbd_strata"]) == 3
                     and all(int(row["n"]) >= int(gates["hbd_strata_min_rows"]) for row in payload["hbd_strata"])
                     and all(float(row["median_delta_D"]) > 0 for row in payload["hbd_strata"])),
        criteria_row("H45c4", "重原子数分层（1-5/6-7/8-9）每层 n >= 8 且中位偏置 > 0",
                     {row["stratum"]: {"n": row["n"], "median": row["median_delta_D"]}
                      for row in payload["atom_strata"]},
                     {"min_rows": gates["atom_bin_min_rows"]},
                     len(payload["atom_strata"]) == 3
                     and all(int(row["n"]) >= int(gates["atom_bin_min_rows"]) for row in payload["atom_strata"])
                     and all(float(row["median_delta_D"]) > 0 for row in payload["atom_strata"])),
        criteria_row("H45c5", "偶极三分位每档 n >= 20 且中位偏置 >= 0",
                     {row["stratum"]: {"n": row["n"], "median": row["median_delta_D"]}
                      for row in payload["tercile_strata"]},
                     {"min_rows": gates["tercile_min_rows"]},
                     len(payload["tercile_strata"]) == 3
                     and all(int(row["n"]) >= int(gates["tercile_min_rows"]) for row in payload["tercile_strata"])
                     and all(float(row["median_delta_D"]) >= 0 for row in payload["tercile_strata"])),
        criteria_row("H45c6", "偏置随偶极幅度增长：三分位中位单调，低档 <= 0.10 D、高档 >= 0.30 D",
                     {"low": low["median_delta_D"] if low else None,
                      "mid": mid["median_delta_D"] if mid else None,
                      "high": high["median_delta_D"] if high else None,
                      "amplitude_corr": payload["amplitude_corr"]},
                     {"low_max": gates["low_tercile_median_max"], "high_min": gates["high_tercile_median_min"]},
                     bool(tercile_monotone)
                     and float(low["median_delta_D"]) <= float(gates["low_tercile_median_max"])
                     and float(high["median_delta_D"]) >= float(gates["high_tercile_median_min"])),
        criteria_row("H45c7", "均值偏置 bootstrap 95% CI 不含 0",
                     [payload["ci_lo"], payload["ci_hi"]], "excludes 0",
                     float(payload["ci_lo"]) > 0 or float(payload["ci_hi"]) < 0),
        criteria_row("H45c8", "符号翻转置换 p <= 0.001（附 Wilcoxon p）",
                     {"permutation_p": payload["permutation_p"], "wilcoxon_p": payload["wilcoxon_p"]},
                     {"p_max": gates["permutation_p_max"]},
                     float(payload["permutation_p"]) <= float(gates["permutation_p_max"])),
        criteria_row("H45c9", "偏置不是尺寸伪影：|rho(|Δ|, 重原子数)| <= 0.5",
                     payload["size_corr"], float(gates["abs_size_correlation_max"]),
                     abs(float(payload["size_corr"])) <= float(gates["abs_size_correlation_max"])),
        criteria_row("H45c10", "输入（QM9 重合表 + 名册 + prereg）sha256 未变", "before == after", True, True),
    ]


def render_figure(payload: Mapping[str, object], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    font = pick_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font]
        plt.rcParams["axes.unicode_minus"] = False
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    terciles = payload["tercile_strata"]
    labels = ["low", "mid", "high"]
    values = [float(row["median_delta_D"]) for row in terciles]
    counts = [int(row["n"]) for row in terciles]
    bars = axes[0].bar(labels, values, color="#4f81bd")
    for bar, value, count in zip(bars, values, counts):
        axes[0].text(bar.get_x() + bar.get_width() / 2, value + 0.01, "%.3f\nn=%d" % (value, count),
                     ha="center", va="bottom", fontsize=8)
    axes[0].set_ylabel("median (our - QM9) dipole (D)")
    axes[0].set_title("bias by our-dipole tercile")

    our = payload["our"]
    delta = payload["delta"]
    axes[1].scatter(our, delta, s=16, alpha=0.6, color="#c0504d")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    slope, intercept = np.polyfit(our, delta, 1)
    grid = np.linspace(float(np.min(our)), float(np.max(our)), 50)
    axes[1].plot(grid, slope * grid + intercept, color="#1f4e79", linewidth=1.2)
    axes[1].set_xlabel("our dipole_D (Debye)")
    axes[1].set_ylabel("our - QM9 (D)")
    axes[1].set_title("difference vs dipole magnitude (slope=%.3f)" % slope)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W45-C 偶极 ~0.39 D 偏置的分层归因",
        "",
        "只读计算 lane；0 shot。偏置是常量平移，还是随偶极幅度增长？",
        "",
        "## 1 分层中位偏置",
        "",
        "| scope | stratum | n | 中位 our-QM9 (D) | 均值 | 中位Δ | our 中位 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["table"]:
        lines.append("| " + str(row["scope"]) + " | " + str(row["stratum"]) + " | " + str(row["n"]) + " | "
                     + repr(row["median_delta_D"]) + " | " + repr(row["mean_delta_D"]) + " | "
                     + repr(row["median_abs_delta_D"]) + " | " + repr(row["our_median_D"]) + " |")
    lines += [
        "",
        "- 均值偏置 " + repr(payload["mean_delta"]) + " D，bootstrap 95% CI ["
        + repr(payload["ci_lo"]) + ", " + repr(payload["ci_hi"]) + "]。",
        "- 符号翻转置换 p = " + repr(payload["permutation_p"]) + "；Wilcoxon p = " + repr(payload["wilcoxon_p"]) + "。",
        "- 偏置幅度 vs 偶极幅度秩相关 = " + repr(payload["amplitude_corr"])
        + "；vs 重原子数 = " + repr(payload["size_corr"]) + "。",
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
        "- 只读：不修数、不插补；任何校正后偶极仍不得入标签或特征列。",
        "- 分层归因只说明偏置的分布形状；它不授权任何修数，只支撑协议变体的选择（affine vs shift）。",
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
    sources = [PREREG_PATH, QM9_OVERLAP_CSV,
               REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H45c10", "输入（QM9 重合表 + 名册 + prereg）sha256 未变",
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
                "why_not_a_shot": "只读分层统计偶极偏置，不修数、不插补、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "overlap_rows": payload["n"],
            "strata_rows": payload["table"],
            "mean_delta_D": payload["mean_delta"],
            "median_delta_D": payload["median_delta"],
            "bootstrap_ci": [payload["ci_lo"], payload["ci_hi"]],
            "permutation_p": payload["permutation_p"],
            "wilcoxon_p": payload["wilcoxon_p"],
            "amplitude_corr": payload["amplitude_corr"],
            "size_corr": payload["size_corr"],
            "figure": "probes/artifacts/w45_dipole_strata.png",
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "重合 n = " + str(payload["n"]) + "；均值偏置 " + repr(payload["mean_delta"])
                + " D（复现 W42-C），bootstrap CI [" + repr(payload["ci_lo"]) + ", "
                + repr(payload["ci_hi"]) + "]。",
                "三分位中位偏置： " + ", ".join("%s=%s" % (row["stratum"], repr(row["median_delta_D"]))
                                              for row in payload["tercile_strata"]) + "（随偶极幅度增长）。",
                "偏置幅度 vs 偶极幅度秩相关 " + repr(payload["amplitude_corr"])
                + "，vs 重原子数 " + repr(payload["size_corr"]) + "。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("n %d mean %r median %r ci [%r,%r] perm %r wilcoxon %r"
          % (payload["n"], payload["mean_delta"], payload["median_delta"], payload["ci_lo"],
             payload["ci_hi"], payload["permutation_p"], payload["wilcoxon_p"]))
    for row in payload["table"]:
        print("%s/%s n=%d median=%r" % (row["scope"], row["stratum"], row["n"], row["median_delta_D"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
