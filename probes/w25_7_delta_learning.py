# -*- coding: utf-8 -*-
# W25-7 (POST-HOC): direction 9 of the parent manuscript v6 -- direct learning
# versus shift (delta) learning -- on this repository's frozen Li+ coordination layer.
# Zero electronic-structure work.
#
# Discipline: this arm is NOT pre-registered.  The frozen Week 25 pre-registration
# (probes/w25_v6_alignment_prereg.json) governs W25-1..W25-4 and is untouched; W25-7
# is a post-hoc addition, takes no main-scoreboard shot, and must never be cited as
# a pre-registered reading.
#
# Two feature sets, because the comparison is only informative in one of them:
#   * x0       = the five cheap columns used by W25-3.  This set already contains the
#                free level itself, so shift = direct - free is near-degenerate here:
#                the pair is carried as a CONTROL, not as evidence.
#   * off_free = the same set with the three orbital columns removed.  Here the free
#                level cannot be read off a feature, so injecting it through the
#                target algebra (shift learning) is a real change of parameterisation.
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w25_v6_alignment as w25

ROOT = w25.ROOT
LEDGER = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
ART = ROOT / "probes" / "artifacts"
CSV_OUT = ART / "w25_7_delta_learning.csv"
FIG = ART / "w25_7_delta_learning.png"
REPORT = ROOT / "reports" / "w25_7_delta_learning.md"
SUMMARY = ROOT / "probes" / "w25_7_delta_learning_summary.json"

POST_HOC = True
NEW_SHOT = False
SCOREBOARD_SHOTS = 0

# (axis, free level column, coordinated level column, shift column)
AXES = (
    ("ox", "homo_free_eV", "homo_li_eV", "delta_homo_eV"),
    ("red", "lumo_free_eV", "lumo_li_eV", "delta_lumo_eV"),
)
X0 = w25.AL_FEATURES
FEATURE_SETS = (
    ("x0", X0, "control: the free level is itself a feature"),
    ("off_free", ("formal_charge", "total_energy_free_hartree"),
     "the free level enters only through the shift target"),
)
SEEDS = 10
N_FOLDS = 5
CI_DRAWS = 20000
CI_SEED = 20261107


def load_pool():
    records = []
    for row in w25.read_rows(LEDGER):
        values = [row.get(name) for name in X0]
        if any(value in (None, "") for value in values):
            continue
        levels = {}
        complete = True
        for axis, free, li, delta in AXES:
            triple = (row.get(free), row.get(li), row.get(delta))
            if any(value in (None, "") for value in triple):
                complete = False
                break
            levels[axis] = tuple(float(value) for value in triple)
        if not complete:
            continue
        records.append({
            "inchikey": row.get("inchikey") or "",
            "name": row.get("name") or "",
            "family": row.get("motif_class") or "unknown",
            "columns": {name: float(row[name]) for name in X0},
            "levels": levels,
        })
    return records


def feature_matrix(pool, columns):
    return np.asarray([[record["columns"][name] for name in columns] for record in pool], dtype=float)


def fit_predict(x_train, y_train, x_test):
    a_train, a_test = w25._standardize(x_train, x_test)
    alpha = w25.pick_alpha(a_train, y_train)
    model = w25.krr_fit(a_train, y_train, alpha)
    return w25.krr_predict(model, a_test), alpha


def kfold_indices(size, folds, rng):
    order = list(range(size))
    rng.shuffle(order)
    buckets = [[] for _ in range(folds)]
    for position, index in enumerate(order):
        buckets[position % folds].append(index)
    return buckets


def r2_score(truth, prediction):
    truth = np.asarray(truth, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    total = float(((truth - truth.mean()) ** 2).sum())
    if total <= 0.0:
        return float("nan")
    return 1.0 - float(((truth - prediction) ** 2).sum()) / total


def cross_validate(pool, axis, folds, shape, columns):
    x = feature_matrix(pool, columns)
    free = np.asarray([record["levels"][axis][0] for record in pool], dtype=float)
    truth = np.asarray([record["levels"][axis][1] for record in pool], dtype=float)
    shift = np.asarray([record["levels"][axis][2] for record in pool], dtype=float)
    prediction = np.full(len(pool), np.nan, dtype=float)
    covered = []
    alphas = []
    for test_idx in folds:
        held = set(int(value) for value in test_idx)
        train_idx = np.asarray([i for i in range(len(pool)) if i not in held], dtype=int)
        test_idx = np.asarray(test_idx, dtype=int)
        covered.append(test_idx)
        target = truth if shape == "direct" else shift
        fitted, alpha = fit_predict(x[train_idx], target[train_idx], x[test_idx])
        alphas.append(alpha)
        if shape == "direct":
            prediction[test_idx] = fitted
        else:
            prediction[test_idx] = free[test_idx] + fitted
    # Metrics are read on the covered rows only.  In leave-one-family-out mode the
    # held-out block is a single family, and an earlier version scored against the
    # whole vector (np.empty, so undefined entries) -- which silently mixed garbage
    # into tau_b and R2 for every LOFO reading.
    idx = np.concatenate(covered) if covered else np.asarray([], dtype=int)
    return {
        "axis": axis,
        "shape": shape,
        "n_scored": int(idx.size),
        "tau_b": w25.kendall_tau_b(prediction[idx], truth[idx]),
        "r2": r2_score(truth[idx], prediction[idx]),
        "mae": float(np.mean(np.abs(truth[idx] - prediction[idx]))),
        "alpha_median": float(np.median(alphas)),
    }


def run_over(pool, folds, tag, seed):
    rows = []
    for axis, _, _, _ in AXES:
        for set_name, columns, _ in FEATURE_SETS:
            window = {"mode": tag, "axis": axis, "feature_set": set_name, "seed": seed, "family": ""}
            for shape in ("direct", "shift"):
                result = cross_validate(pool, axis, folds, shape, columns)
                window[shape + "_tau_b"] = result["tau_b"]
                window[shape + "_r2"] = result["r2"]
                window[shape + "_mae"] = result["mae"]
            window["delta_tau_b"] = window["shift_tau_b"] - window["direct_tau_b"]
            window["delta_r2"] = window["shift_r2"] - window["direct_r2"]
            rows.append(window)
    return rows


def random_mode(pool):
    rows = []
    for seed in range(SEEDS):
        rng = random.Random(20261000 + seed)
        folds = kfold_indices(len(pool), N_FOLDS, rng)
        rows.extend(run_over(pool, folds, "random", seed))
    return rows


def lofo_mode(pool):
    rows = []
    for family in sorted({record["family"] for record in pool}):
        test_idx = [i for i, record in enumerate(pool) if record["family"] == family]
        window_rows = run_over(pool, [test_idx], "lofo", -1)
        for window in window_rows:
            window["family"] = family
            window["n_test"] = len(test_idx)
            window["n_train"] = len(pool) - len(test_idx)
        rows.extend(window_rows)
    return rows


def paired_ci(values, draws, seed):
    values = [value for value in values if not math.isnan(value)]
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    size = len(values)
    means = []
    for _ in range(draws):
        means.append(sum(values[rng.randrange(size)] for _ in range(size)) / size)
    means.sort()
    return (float(sum(values) / size),
            float(means[int(0.025 * len(means))]),
            float(means[min(len(means) - 1, int(0.975 * len(means)))]))


def _nanmean(values):
    kept = [value for value in values if not math.isnan(value)]
    return float(np.mean(kept)) if kept else float("nan")


def summarise(rows):
    out = {}
    for axis, _, _, _ in AXES:
        out[axis] = {}
        for set_name, _, _ in FEATURE_SETS:
            random_rows = [row for row in rows if row["mode"] == "random" and row["axis"] == axis
                           and row["feature_set"] == set_name]
            lofo_rows = [row for row in rows if row["mode"] == "lofo" and row["axis"] == axis
                         and row["feature_set"] == set_name]
            deltas = [row["delta_tau_b"] for row in random_rows]
            mean, lo, hi = paired_ci(deltas, CI_DRAWS, CI_SEED)
            out[axis][set_name] = {
                "random": {
                    "direct_tau_b_mean": float(np.mean([row["direct_tau_b"] for row in random_rows])),
                    "shift_tau_b_mean": float(np.mean([row["shift_tau_b"] for row in random_rows])),
                    "direct_r2_mean": float(np.mean([row["direct_r2"] for row in random_rows])),
                    "shift_r2_mean": float(np.mean([row["shift_r2"] for row in random_rows])),
                    "direct_mae_mean": float(np.mean([row["direct_mae"] for row in random_rows])),
                    "shift_mae_mean": float(np.mean([row["shift_mae"] for row in random_rows])),
                    "delta_tau_b_mean": mean,
                    "delta_tau_b_ci": [lo, hi],
                    "delta_tau_b_min": float(np.min(deltas)),
                    "delta_tau_b_max": float(np.max(deltas)),
                    "positive_repeats": int(sum(1 for value in deltas if value > 0.0)),
                    "repeats": len(deltas),
                    "delta_r2_mean": float(np.mean([row["delta_r2"] for row in random_rows])),
                },
                "lofo": {
                    "delta_tau_b_mean": _nanmean([row["delta_tau_b"] for row in lofo_rows]),
                    "positive_families": int(sum(1 for row in lofo_rows if row["delta_tau_b"] > 0.0)),
                    "families": int(sum(1 for row in lofo_rows if not math.isnan(row["delta_tau_b"]))),
                    "families_total": len(lofo_rows),
                    "per_family": {
                        row["family"]: (None if math.isnan(row["delta_tau_b"]) else row["delta_tau_b"])
                        for row in lofo_rows
                    },
                },
            }
    return out


def figure(plt, readings):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for panel, (axis, _, _, _) in enumerate(AXES):
        labels = []
        values = []
        colors = []
        for set_name, _, _ in FEATURE_SETS:
            entry = readings[axis][set_name]["random"]
            labels.extend([set_name + chr(10) + "direct", set_name + chr(10) + "shift"])
            values.extend([entry["direct_tau_b_mean"], entry["shift_tau_b_mean"]])
            colors.extend(["#4a5568", "#2b6cb0"])
        axes[panel].bar(labels, values, color=colors, width=0.6)
        axes[panel].set_ylim(0.0, 1.05)
        axes[panel].set_ylabel("tau_b (out-of-fold, mean of " + str(SEEDS) + " repeats)")
        off = readings[axis]["off_free"]["random"]
        ctrl = readings[axis]["x0"]["random"]
        axes[panel].set_title("(" + "ab"[panel] + ") " + axis + " axis  |  off_free delta = "
                              + w25.fmt(off["delta_tau_b_mean"], 4)
                              + " [" + w25.fmt(off["delta_tau_b_ci"][0], 3) + ", "
                              + w25.fmt(off["delta_tau_b_ci"][1], 3) + "]  |  x0 control delta = "
                              + w25.fmt(ctrl["delta_tau_b_mean"], 4), fontsize=9)
        for position, value in enumerate(values):
            axes[panel].text(position, value + 0.02, w25.fmt(value, 3), ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG, dpi=160)
    plt.close(fig)


def render(readings, pool):
    lines = []
    lines.append("# W25-7（后验）：直接学习 vs 位移学习（母体论文 v6 方向 9 的本仓对照）")
    lines.append("")
    lines.append("- **性质**：后验臂（post_hoc = true、new_shot = false、主记分牌 shot = **0**）。**未预注册**，不得引用为预注册结论。")
    lines.append("- **池**：" + str(len(pool)) + " 个化合物（冻结 246 名册里 5 项廉价特征与前缘轨道自由/配位两表齐全者），每化合物一行，按 InChIKey 唯一。")
    lines.append("- **代理模型**：KRR（RBF，alpha 由训练折 LOO 选择）；**划分**：random 5 折 x " + str(SEEDS) + " 种子（配对区间 2x10^4 bootstrap）与 LOFO（留一家族出，motif_class 五家族）。")
    lines.append("- **两种形状**：direct 直接学配位层能级；shift 学位移 delta 再把自由层回加（预测 = 自由层 + delta_hat）。")
    lines.append("- **两套特征**：")
    for set_name, columns, note in FEATURE_SETS:
        lines.append("  - " + set_name + " = " + ", ".join(columns) + "（" + note + "）")
    lines.append("")
    lines.append("## 1. 随机划分")
    lines.append("")
    lines.append("| 轴 | 特征集 | direct tau_b | shift tau_b | delta tau_b | 95% CI | 正向重复 | direct R2 | shift R2 | delta R2 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for axis, _, _, _ in AXES:
        for set_name, _, _ in FEATURE_SETS:
            entry = readings[axis][set_name]["random"]
            lines.append("| " + axis + " | " + set_name + " | " + w25.fmt(entry["direct_tau_b_mean"], 4)
                         + " | " + w25.fmt(entry["shift_tau_b_mean"], 4)
                         + " | **" + w25.fmt(entry["delta_tau_b_mean"], 4) + "** | ["
                         + w25.fmt(entry["delta_tau_b_ci"][0], 3) + ", " + w25.fmt(entry["delta_tau_b_ci"][1], 3)
                         + "] | " + str(entry["positive_repeats"]) + "/" + str(entry["repeats"])
                         + " | " + w25.fmt(entry["direct_r2_mean"], 4) + " | " + w25.fmt(entry["shift_r2_mean"], 4)
                         + " | " + w25.fmt(entry["delta_r2_mean"], 4) + " |")
    lines.append("")
    lines.append("## 2. 留一家族出（LOFO）")
    lines.append("")
    lines.append("| 轴 | 特征集 | delta tau_b 均值 | 正向家族 | 逐家族 delta tau_b |")
    lines.append("| --- | --- | --- | --- | --- |")
    for axis, _, _, _ in AXES:
        for set_name, _, _ in FEATURE_SETS:
            entry = readings[axis][set_name]["lofo"]
            per = ", ".join([name + " " + (w25.fmt(value, 3) if value is not None else "未定义(n<3)")
                         for name, value in sorted(entry["per_family"].items())])
            lines.append("| " + axis + " | " + set_name + " | **" + w25.fmt(entry["delta_tau_b_mean"], 4) + "** | "
                         + str(entry["positive_families"]) + "/" + str(entry["families"]) + " | " + per + " |")
    lines.append("")
    lines.append("![图 W25-7 direct vs shift](probes/artifacts/w25_7_delta_learning.png)")
    lines.append("")
    lines.append("## 3. 口径与限制")
    lines.append("")
    lines.append("- 本臂**未预注册**，是 W25 冻结预注册之外的后验追加；W25-1..W25-4 的裁决不受它影响。")
    lines.append("- **x0 那一对是控制组，不是证据**：该特征集本身就含自由层能级，而 shift 目标 = direct 目标 − 自由层，所以两者在数学上近乎同一份信息，delta tau_b 接近 0 是设计的预期结果。")
    lines.append("- **off_free 那一对才是本臂的实质比较**：自由层不可由特征读出，只能经目标代数注入——这正是 v6 所说的「位移学习把先验注入」。")
    lines.append("- 池是 237 行、v6 是 18 分子池；特征是 2 项或 5 项、v6 是 12 项 X0。两边**不可相加**、不比绝对值。")
    lines.append("- random 划分的 10 个重复共享同一批化合物，配对区间只读作重复间稳健性，不读作独立样本检验。")
    lines.append("- LOFO 五家族大小悬殊（最大 175、最小 2），小家族的 delta tau_b 抽样噪声大；逐家族值只作方向读数。")
    lines.append("- LOFO 的 anion_halide 家族只有 2 个化合物，tau_b 在 n < 3 时未定义（表中标「未定义(n<3)」）：该族从均值与正向计数里剔除，families_total 仍记 5。")
    lines.append("- 指标只在被预测到的行上读取（LOFO 只读留出家族那一块）；早期版本用 np.empty 的整条向量计分，会把未定义项混进 tau_b，已修。")
    lines.append("")
    lines.append("## 4. 产物")
    lines.append("")
    lines.append("| 文件 | 内容 |")
    lines.append("| --- | --- |")
    lines.append("| probes/artifacts/w25_7_delta_learning.csv | 逐划分逐特征集逐形状读数 |")
    lines.append("| probes/artifacts/w25_7_delta_learning.png | 本图 |")
    lines.append("| probes/w25_7_delta_learning_summary.json | 机读摘要 |")
    lines.append("")
    REPORT.write_text(chr(10).join(lines) + chr(10), encoding="utf-8", newline=chr(10))
    return lines


def main():
    pool = load_pool()
    print("[w25-7] pool = " + str(len(pool)), flush=True)
    rows = random_mode(pool)
    print("[w25-7] random mode done", flush=True)
    rows.extend(lofo_mode(pool))
    print("[w25-7] LOFO mode done", flush=True)
    header = ["mode", "axis", "feature_set", "seed", "family", "n_test", "direct_tau_b", "shift_tau_b",
              "delta_tau_b", "direct_r2", "shift_r2", "delta_r2", "direct_mae", "shift_mae"]
    table = []
    for row in rows:
        table.append([row["mode"], row["axis"], row["feature_set"], row["seed"], row.get("family", ""),
                      row.get("n_test", ""), w25.fmt(row["direct_tau_b"]), w25.fmt(row["shift_tau_b"]),
                      w25.fmt(row["delta_tau_b"]), w25.fmt(row["direct_r2"]), w25.fmt(row["shift_r2"]),
                      w25.fmt(row["delta_r2"]), w25.fmt(row["direct_mae"]), w25.fmt(row["shift_mae"])])
    w25.write_csv(CSV_OUT, header, table)
    summary = {"task": "w25_7_delta_learning", "post_hoc": POST_HOC, "new_shot": NEW_SHOT,
               "scoreboard_shots": SCOREBOARD_SHOTS, "n_pool": len(pool),
               "feature_sets": {name: list(columns) for name, columns, _ in FEATURE_SETS},
               "axes": [axis for axis, _, _, _ in AXES], "seeds": SEEDS, "folds": N_FOLDS,
               "readings": summarise(rows)}
    plt = w25.configure_fonts()
    figure(plt, summary["readings"])
    render(summary["readings"], pool)
    summary["artifacts_sha256"] = {str(path.relative_to(ROOT)): w25.sha256_file(path)
                                   for path in (CSV_OUT, FIG, REPORT) if path.exists()}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline=chr(10))
    print(json.dumps({axis: {name: summary["readings"][axis][name]["random"]["delta_tau_b_mean"]
                             for name, _, _ in FEATURE_SETS} for axis, _, _, _ in AXES}, ensure_ascii=False))


if __name__ == "__main__":
    main()
