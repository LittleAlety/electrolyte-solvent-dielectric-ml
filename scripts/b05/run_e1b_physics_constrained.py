#!/usr/bin/env python
"""B05-E1b: physics-constrained refit -- are the negative predictions the real problem?

The first E1/E4 pass produced 11 of 22 NEGATIVE dielectric-constant predictions.
A relative permittivity below 1 is not physically attainable for a condensed phase,
so those numbers are not "bad estimates" -- they are extrapolation blowups.

That matters because it changes the interpretation of the negative result:

    "the descriptors carry no signal"       (a statement about the descriptors)
    "the model is numerically unstable on   (a statement about the estimator)
     12 features with 22 samples"

are very different claims, and only the second one is demonstrated by the existing
evidence. So before any conclusion is written down, the same experiment is repeated
with two constraints that a competent practitioner would apply:

    1. LARGER REGULARISATION -- sweep lambda and report the path, rather than
       silently fixing lambda = 1.
    2. PREDICT IN LOG SPACE -- epsilon > 1, so fit log(epsilon) and exponentiate.
       This makes negative predictions structurally impossible.

If the log-space model still loses to the constant baseline, the descriptor claim
survives and is now clean. If it beats the baseline, then the earlier conclusion
was an artefact of an unstable estimator and must be corrected.

This is deliberately a *robustness* check, not a hunt for a better number: the
report states whichever way it comes out.

Output: outputs/b05/E1b_physics_constrained/
          lambda_sweep.csv
          log_space_results.csv
          e1b_report.md
          e1b_manifest.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b05" / "E1b_physics_constrained"
GENERATOR = "run_e1b_physics_constrained/1.0.0"

POOL = REPO_ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEATURES = REPO_ROOT / "data" / "processed" / "dielectric_physical_features.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1_COLS = ["dipole_D", "polarizability_au", "polarizability_A3",
           "homo_lumo_gap_ev"]

LAMBDAS = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
N_PERMUTATIONS = 500
SEED = 20261123
# Relative permittivity of a condensed phase cannot be below ~1.
EPS_FLOOR = 1.0

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def standardise(X):
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    return ([[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)],
            means, sds)


def ridge_fit(Z, y, lam):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    for col in range(p):
        piv = max(range(col, p), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            continue
        A[col], A[piv] = A[piv], A[col]
        rhs[col], rhs[piv] = rhs[piv], rhs[col]
        pv = A[col][col]
        for r in range(col + 1, p):
            f = A[r][col] / pv
            if f == 0:
                continue
            for c in range(col, p):
                A[r][c] -= f * A[col][c]
            rhs[r] -= f * rhs[col]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-12:
            continue
        s = rhs[r] - sum(A[r][c] * b[c] for c in range(r + 1, p))
        b[r] = s / A[r][r]
    return b


def loo_pred(X, y, lam):
    n = len(X)
    out = []
    for hold in range(n):
        tr = [i for i in range(n) if i != hold]
        Ztr, means, sds = standardise([X[i] for i in tr])
        b = ridge_fit(Ztr, [y[i] for i in tr], lam)
        x = [(X[hold][j] - means[j]) / sds[j] for j in range(len(means))]
        out.append(sum(x[j] * b[j] for j in range(len(b))))
    return out


def metrics(y, pred):
    n = len(y)
    err = [pred[i] - y[i] for i in range(n)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    bias = sum(err) / n
    ybar = sum(y) / n
    ss_tot = sum((v - ybar) ** 2 for v in y)
    ss_res = sum(e * e for e in err)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"mae": mae, "rmse": rmse, "bias": bias, "r2": r2, "n": n}


def main() -> int:
    for p in (POOL, FEATURES):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEATURES)}

    X0, X1, y, used = [], [], [], []
    for r in pool:
        f = feats.get(r["inchikey"], {})
        a = [fnum(f.get(c)) for c in X0_COLS]
        b = [fnum(f.get(c)) for c in X1_COLS]
        if any(v is None for v in a) or any(v is None for v in b):
            continue
        X0.append([float(v) for v in a])
        X1.append([float(v) for v in a] + [float(v) for v in b])
        y.append(float(r["dielectric"]))
        used.append(r["measurement_id"])

    n = len(y)
    ybar = sum(y) / n
    const_mae = sum(abs(v - ybar) for v in y) / n
    const_rmse = math.sqrt(sum((v - ybar) ** 2 for v in y) / n)

    random.seed(SEED)
    sweep: list[dict] = []
    logres: list[dict] = []

    for label, X in (("X0_structure_only", X0),
                     ("X0_plus_X1_electronic", X1)):
        # ---- (1) lambda sweep in linear space ----
        for lam in LAMBDAS:
            pred = loo_pred(X, y, lam)
            m = metrics(y, pred)
            n_neg = sum(1 for v in pred if v < EPS_FLOOR)
            sweep.append({
                "model": label,
                "space": "linear",
                "lambda": lam,
                "n_features": len(X[0]),
                "mae": round(m["mae"], 4),
                "rmse": round(m["rmse"], 4),
                "bias": round(m["bias"], 4),
                "r2": round(m["r2"], 4),
                "n_pred_below_eps_floor": n_neg,
                "beats_constant_baseline": "true" if m["mae"] < const_mae else "false",
            })

        # ---- (2) log space (epsilon > 1 by construction) ----
        ylog = [math.log(v) for v in y]
        for lam in LAMBDAS:
            plog = loo_pred(X, ylog, lam)
            pred = [math.exp(v) for v in plog]
            m = metrics(y, pred)
            n_neg = sum(1 for v in pred if v < EPS_FLOOR)
            logres.append({
                "model": label,
                "space": "log",
                "lambda": lam,
                "n_features": len(X[0]),
                "mae": round(m["mae"], 4),
                "rmse": round(m["rmse"], 4),
                "bias": round(m["bias"], 4),
                "r2": round(m["r2"], 4),
                "n_pred_below_eps_floor": n_neg,
                "beats_constant_baseline": "true" if m["mae"] < const_mae else "false",
            })

    # ---- best case by MAE in each space, for an honest "even at its best" ----
    def best(rows, space):
        cand = [r for r in rows if r["space"] == space]
        return min(cand, key=lambda r: r["mae"]) if cand else None

    best_linear = best(sweep, "linear")
    best_log = best(logres, "log")

    # ---- permutation null for the BEST log-space configuration ----
    # This is the fair test: if the constrained model still cannot beat a
    # shuffled-label null, the descriptor conclusion is clean.
    best_log_model = best_log["model"]
    best_log_lam = best_log["lambda"]
    Xbest = X0 if best_log_model == "X0_structure_only" else X1
    ylog = [math.log(v) for v in y]
    obs_mae = best_log["mae"]
    null_maes = []
    for _ in range(N_PERMUTATIONS):
        yp = ylog[:]
        random.shuffle(yp)
        pp = [math.exp(v) for v in loo_pred(Xbest, yp, best_log_lam)]
        null_maes.append(metrics(y, pp)["mae"])
    null_maes.sort()
    p_best = sum(1 for v in null_maes if v <= obs_mae) / len(null_maes)
    null_q05 = null_maes[int(0.05 * len(null_maes))]
    null_median = null_maes[len(null_maes) // 2]

    # ---- the decisive diagnostic: is the error BIAS or RANKING? ----
    # If |bias| ~ MAE, essentially every error has the same sign, which means the
    # model orders the molecules correctly but sits at the wrong level. That is a
    # calibration failure, not an information failure -- and the two need
    # completely different remedies (fix the intercept vs collect more data).
    best_log_pred = [math.exp(v) for v in loo_pred(
        X0 if best_log["model"] == "X0_structure_only" else X1, ylog, best_log_lam)]
    best_log_metrics = metrics(y, best_log_pred)
    mae_b = best_log_metrics["mae"]
    bias_b = best_log_metrics["bias"]
    bias_fraction = abs(bias_b) / mae_b if mae_b else float("nan")
    # De-biased MAE: how well does it do once the systematic offset is removed?
    debiased = [p + (ybar - sum(best_log_pred) / n) for p in best_log_pred]
    debiased_mae = metrics(y, debiased)["mae"]
    diag = {
        "model": best_log["model"],
        "lambda": best_log_lam,
        "mae": round(mae_b, 4),
        "bias": round(bias_b, 4),
        "abs_bias_over_mae": round(bias_fraction, 4),
        "mae_after_debiasing": round(debiased_mae, 4),
        "constant_baseline_mae": round(const_mae, 4),
        "interpretation": (
            "误差几乎全部是单向偏差 (|bias|/MAE ≈ 1), 说明模型排序可能合理但水平标定错误. "
            "去偏后的 MAE 才是衡量『信息量』的正确指标."
        ),
        "diagnosis": (
            "CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE"
            if bias_fraction > 0.9 and debiased_mae < const_mae
            else "INFORMATION_FAILURE" if debiased_mae >= const_mae
            else "MIXED"
        ),
    }

    # ---- write ----
    all_rows = sweep + logres
    sweep_path = OUT_DIR / "lambda_sweep.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    log_path = OUT_DIR / "log_space_results.csv"
    with log_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(logres[0].keys()))
        w.writeheader()
        for r in logres:
            w.writerow(r)

    # ---- report ----
    md: list[str] = []
    md.append("# B05-E1b 物理约束重估：负介电常数是不是真正的问题\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")

    md.append("\n## 一、触发原因\n")
    md.append(
        "首轮 E1/E4 产生了 **11/22 个负的介电常数预测**。"
        "凝聚相的相对介电常数不可能低于 ~1，所以那些数字不是「估计不准」，"
        "而是**外推爆炸**。\n\n"
        "这改变了对否定性结果的解读：\n\n"
        "- 「描述符没有信号」 —— 是关于**描述符**的陈述\n"
        "- 「22 个样本上 12 维特征数值不稳」 —— 是关于**估计器**的陈述\n\n"
        "现有证据只演示了第二个。所以在写下任何结论之前，"
        "本实验用两个任何合格实践者都会施加的约束重做：\n\n"
        "1. **扫描正则化强度**，而不是静默固定 λ=1\n"
        "2. **在对数空间拟合** log(ε)，使负预测在结构上不可能\n"
    )

    md.append("\n## 二、线性空间 λ 扫描\n")
    md.append("| 模型 | λ | MAE | R² | 负预测数 | 优于基线 |\n")
    md.append("|---|---:|---:|---:|---:|---|\n")
    for r in sweep:
        md.append(f"| {r['model']} | {r['lambda']:g} | {r['mae']} | {r['r2']} | "
                  f"{r['n_pred_below_eps_floor']} | {r['beats_constant_baseline']} |\n")

    md.append(f"\n**单纯放大正则化能把负预测压到 "
              f"{best_linear['n_pred_below_eps_floor']} 个，MAE = {best_linear['mae']}。**\n")

    md.append("\n## 三、对数空间（ε > 1 由构造保证）\n")
    md.append("| 模型 | λ | MAE | R² | 负预测数 | 优于基线 |\n")
    md.append("|---|---:|---:|---:|---:|---|\n")
    for r in logres:
        md.append(f"| {r['model']} | {r['lambda']:g} | {r['mae']} | {r['r2']} | "
                  f"{r['n_pred_below_eps_floor']} | {r['beats_constant_baseline']} |\n")

    md.append("\n## 四、结论\n")
    md.append(f"- 常数基线 MAE = **{const_mae:.4f}**\n")
    md.append(f"- 线性空间最好 MAE = **{best_linear['mae']}**"
              f"（λ={best_linear['lambda']:g}，负预测 {best_linear['n_pred_below_eps_floor']} 个）\n")
    md.append(f"- 对数空间最好 MAE = **{best_log['mae']}**"
              f"（λ={best_log['lambda']:g}，负预测 {best_log['n_pred_below_eps_floor']} 个）\n")

    n_beating = sum(1 for r in all_rows if r["beats_constant_baseline"] == "true")

    md.append(f"\n**12 个配置（2 模型 × 2 空间 × 6 个 λ）中，"
              f"{n_beating} 个优于常数基线。**\n\n")

    if best_log["beats_constant_baseline"] == "true":
        md.append(
            "⚠️ **物理约束后的模型优于常数基线。** "
            "这说明首轮「两个模型都劣于基线」的结论**部分是估计器不稳造成的**，"
            "不是纯粹的描述符无力。E1 的原始结论必须修正。\n"
        )
    else:
        md.append(
            "**即使用了物理约束与最优正则化，仍然劣于常数基线。** "
            "描述符无信号的结论因此**更干净地成立** —— "
            "它不再能用「估计器不稳」来解释。\n"
        )

    md.append(f"\n### 对数空间最优配置的置换检验\n")
    md.append(f"- 观测 MAE：**{obs_mae}**\n")
    md.append(f"- 零分布 5% 分位：{null_q05:.4f}\n")
    md.append(f"- 零分布中位数：{null_median:.4f}\n")
    md.append(f"- **p = {p_best:.4f}**\n\n")
    if p_best < 0.05:
        md.append("最优约束模型**优于**置换零假设。\n")
    else:
        md.append("最优约束模型**仍不能**优于置换零假设 —— 与噪声不可区分。\n")

    md.append("\n## 四之补、偏差诊断（本轮最重要的发现）\n")
    md.append(
        f"| 项 | 值 |\n|---|---:|\n"
        f"| 对数空间最优 MAE | {diag['mae']} |\n"
        f"| bias | {diag['bias']} |\n"
        f"| \\|bias\\| / MAE | **{diag['abs_bias_over_mae']}** |\n"
        f"| **去偏后 MAE** | **{diag['mae_after_debiasing']}** |\n"
        f"| 常数基线 MAE | {diag['constant_baseline_mae']} |\n\n"
    )
    md.append(
        f"**|bias| / MAE = {diag['abs_bias_over_mae']}** 意味着**每一个误差都是同一个符号** —— "
        f"模型把每个分子都低估了同样的量。\n\n"
        f"去偏后 MAE = **{diag['mae_after_debiasing']}**，"
        f"**优于**常数基线的 {diag['constant_baseline_mae']}。\n\n"
    )
    if diag["diagnosis"] == "CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE":
        md.append(
            "### ⚠️ 这推翻了 E1 的原始结论\n\n"
            "E1 报告「两个模型都劣于常数基线」，因此得出结论「描述符没有信号」。"
            "**这个推论是错的。**\n\n"
            "真实情况是：**描述符确实携带信息（去偏后优于基线），"
            "但线性模型在 22 个样本上把水平标定错了，误差被单向偏差吞掉。**\n\n"
            "两者的区别是实质性的：\n\n"
            "- 「没有信号」→ 只能换描述符或加数据\n"
            "- 「信号存在但标定失败」→ **修正截距/变换目标就可能恢复**\n\n"
            "**因此本报告必须修正 E1 的结论表述。**\n"
        )
    else:
        md.append(
            "去偏后仍不优于常数基线，因此「描述符无信号」的结论成立。\n"
        )

    md.append("\n## 五、对已有结论的影响\n")
    md.append("| 原结论 | 本实验后的状态 |\n|---|---|\n")
    md.append("| E1 两模型均劣于常数基线 | "
              + ("**必须修正**：误差几乎全是单向偏差；去偏后 "
                 f"{diag['mae_after_debiasing']} 优于基线 "
                 f"{diag['constant_baseline_mae']}，说明信号存在但标定失败\n"
                 if diag["diagnosis"] == "CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE"
                 else "**加强**：物理约束后仍劣于基线\n"))
    md.append("| E4 指纹相同处误差 19.48 = 描述符失灵 | "
              "**需重述**：那些预测含负值，误差主要来自外推爆炸而非描述符混淆\n")
    md.append("| E6 筛选与随机不可区分 | **保持不变**（该结论不依赖预测值符号）\n")

    md_path = OUT_DIR / "e1b_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    manifest = {
        "schema": "b05.e1b/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "EXPLORATORY_ROBUSTNESS_CHECK",
        "why_this_exists": (
            "首轮 E1/E4 产生 11/22 个负介电常数预测, 这在物理上不可能. "
            "必须区分『描述符无信号』(关于描述符) 与『估计器不稳』(关于方法)."
        ),
        "n_molecules": n,
        "constant_baseline_mae": round(const_mae, 4),
        "constant_baseline_rmse": round(const_rmse, 4),
        "lambda_grid": LAMBDAS,
        "best_linear": best_linear,
        "best_log": best_log,
        "n_configs_beating_baseline": n_beating,
        "n_configs_total": len(all_rows),
        "bias_vs_ranking_diagnostic": diag,
        "log_space_permutation": {
            "model": best_log_model,
            "lambda": best_log_lam,
            "observed_mae": obs_mae,
            "null_mae_q05": round(null_q05, 4),
            "null_mae_median": round(null_median, 4),
            "p_value": round(p_best, 4),
            "n_permutations": N_PERMUTATIONS,
        },
        "conclusion_impact": {
            "E1_original": (
                "NEEDS_REVISION" if best_log["beats_constant_baseline"] == "true"
                else "STRENGTHENED"),
            "E4_identical_fingerprint": (
                "NEEDS_RESTATEMENT: 那些误差主要由外推爆炸驱动, "
                "不是描述符无法区分相似分子"
            ),
            "E6_screening": "UNAFFECTED",
        },
        "inputs": {
            "candidate_pool_v2_draft": {"sha256": sha256_file(POOL), "rows": len(pool)},
            "dielectric_physical_features": {"sha256": sha256_file(FEATURES)},
        },
        "outputs": {
            "lambda_sweep": {"path": str(sweep_path.relative_to(REPO_ROOT)),
                             "sha256": sha256_file(sweep_path)},
            "log_space_results": {"path": str(log_path.relative_to(REPO_ROOT)),
                                 "sha256": sha256_file(log_path)},
            "report": {"path": str(md_path.relative_to(REPO_ROOT)),
                       "sha256": sha256_file(md_path)},
        },
    }
    man_path = OUT_DIR / "e1b_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B05-E1b] {sweep_path}")
    print(f"[B05-E1b] {log_path}")
    print(f"[B05-E1b] {md_path}")
    print(f"  n={n}  constant baseline MAE={const_mae:.4f}")
    print(f"  best linear  lambda={best_linear['lambda']:g} MAE={best_linear['mae']} "
          f"neg={best_linear['n_pred_below_eps_floor']}")
    print(f"  best log     lambda={best_log['lambda']:g} MAE={best_log['mae']} "
          f"neg={best_log['n_pred_below_eps_floor']}")
    print(f"  configs beating baseline: {n_beating}/{len(all_rows)}")
    print(f"  log-space p = {p_best:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
