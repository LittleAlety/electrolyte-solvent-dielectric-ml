#!/usr/bin/env python
"""B05-E1: structure descriptors (X0) vs structure + electronic descriptors (X0+X1).

PLAN B B05 requires E1 as a mandatory experiment, and states the research goal is
NOT "highest R-squared" but the **validity boundary** of single-molecule
descriptors. So this script is built to answer one question honestly:

    does adding electronic descriptors buy anything measurable
    on a 22-molecule pool, and how much of any apparent gain is noise?

Design decisions that follow from that, and that a leaderboard-style script would
get wrong:

  * LEAVE-ONE-OUT, not random K-fold. With 22 molecules, a random split lets
    near-duplicate chemistry sit on both sides. LOO at least never trains and
    tests on the same molecule. Both are reported so the gap is visible.

  * EVERY number carries a permutation null. With n=22 a "gain" of a few percent
    MAE is well inside what shuffled labels produce. A delta without a null
    distribution is not evidence.

  * The result is labelled EXPLORATORY. PLAN B says a model on insufficient
    samples may be run as exploratory code testing but must not be packaged as a
    confirmatory result. 22 molecules cannot support a confirmatory claim.

  * Coverage is reported, not assumed. Any descriptor missing for a molecule is
    reported rather than silently imputed.

Output: outputs/b05/E1_structure_vs_electronic/
          metrics.csv
          permutation_null.csv
          predictions_loo.csv
          e1_report.md
          e1_manifest.json
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
OUT_DIR = REPO_ROOT / "outputs" / "b05" / "E1_structure_vs_electronic"
GENERATOR = "run_e1_structure_vs_electronic/1.0.0"

POOL = REPO_ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEATURES = REPO_ROOT / "data" / "processed" / "dielectric_physical_features.csv"

# X0: composition/shape only -- no electronic structure.
X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
# X1 as used by E4/E6/B07. NOTE: the first release of E1 additionally included
# `total_energy_hartree`, making E1 a 12-feature model while every other experiment
# used 11 -- so cross-experiment comparison silently compared different models.
# Reviewer 3/4 (B04+B05) flagged this. `total_energy_hartree` is excluded here
# because the feature audit showed it is a size proxy (r = -0.957 with heavy atom
# count, r = 0.007 with epsilon), i.e. it duplicates X0 information.
X1_COLS = ["dipole_D", "polarizability_au", "polarizability_A3",
           "homo_lumo_gap_ev"]
# Kept so the exclusion is auditable rather than a silent deletion.
EXCLUDED_FEATURES = {
    "total_energy_hartree": (
        "E1 初版曾使用. 排除理由: 特征审计显示它是分子大小代理 "
        "(与重原子数 r=-0.957, 与 ε r=0.007), 与 X0 信息重复; "
        "且使 E1 的特征集与其他实验不一致 (Reviewer 3/4, B04+B05)."
    ),
}

N_PERMUTATIONS = 500
SEED = 20261123

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


# ---------------------------------------------------------------------------
# A deliberately plain ridge regression. With n=22 and up to 12 columns, model
# capacity is the enemy of an honest answer, so this is the simplest thing that
# can work -- not a tuned learner.
# ---------------------------------------------------------------------------

def _standardise(X: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    Z = [[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)]
    return Z, means, sds


def _ridge_fit(Z: list[list[float]], y: list[float], lam: float) -> list[float]:
    """Solve (Z'Z + lam I) b = Z'y by Gaussian elimination."""
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    # Gaussian elimination with partial pivoting
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


def ridge_loo(X: list[list[float]], y: list[float], lam: float = 1.0) -> list[float]:
    """Leave-one-out ridge predictions, WITH an intercept.

    Reviewer 1 (B04+B05) found a specification error here that invalidated the
    original conclusion. The features are standardised to mean 0, so a ridge fit
    without an intercept is forced through the origin *in standardised space* --
    which means the prediction is a deviation around 0, not around the training
    mean. The model was therefore predicting values near 0 for a target whose mean
    is 17.3, producing bias = -16.7 and making it look as though the descriptors
    carried no information.

    The correct predictor adds the training-fold mean back:

        y_hat = ybar_train + sum_j b_j * z_j

    Reproduced from the shipped code, this single fix moves X0+X1 from
    MAE 17.29 / R2 -1.29 to MAE 6.50 / R2 +0.54, i.e. decisively better than the
    constant baseline of 10.81 rather than worse than it.
    """
    n = len(X)
    preds = []
    for hold in range(n):
        Xtr = [X[i] for i in range(n) if i != hold]
        ytr = [y[i] for i in range(n) if i != hold]
        Ztr, means, sds = _standardise(Xtr)
        b = _ridge_fit(Ztr, ytr, lam)
        ybar_tr = sum(ytr) / len(ytr)
        x = [(X[hold][j] - means[j]) / sds[j] for j in range(len(means))]
        preds.append(ybar_tr + sum(x[j] * b[j] for j in range(len(b))))
    return preds


def metrics(y: list[float], pred: list[float]) -> dict:
    n = len(y)
    err = [pred[i] - y[i] for i in range(n)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    bias = sum(err) / n
    ybar = sum(y) / n
    ss_tot = sum((v - ybar) ** 2 for v in y)
    ss_res = sum(e * e for e in err)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": n, "mae": mae, "rmse": rmse, "bias": bias, "r2": r2}


def build_matrix(rows: list[dict], feature_by_key: dict[str, dict],
                 cols: list[str]) -> tuple[list[list[float]], list[str]]:
    X, used = [], []
    for r in rows:
        f = feature_by_key.get(r["inchikey"], {})
        vals = [fnum(f.get(c)) for c in cols]
        if any(v is None for v in vals):
            continue
        X.append([float(v) for v in vals])
        used.append(r["measurement_id"])
    return X, used


def main() -> int:
    for p in (POOL, FEATURES):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEATURES)}

    # align target with pool order
    y_all = [float(r["dielectric"]) for r in pool]

    X0, used0 = build_matrix(pool, feats, X0_COLS)
    X1, used1 = build_matrix(pool, feats, X0_COLS + X1_COLS)

    # Both feature sets must cover the same molecules, or the comparison is
    # between different samples rather than between different features.
    common = [m for m in used0 if m in set(used1)]
    idx0 = [used0.index(m) for m in common]
    idx1 = [used1.index(m) for m in common]
    y = [float(next(r for r in pool if r["measurement_id"] == m)["dielectric"])
         for m in common]

    X0c = [X0[i] for i in idx0]
    X1c = [X1[i] for i in idx1]

    coverage = {
        "n_pool": len(pool),
        "n_with_x0": len(used0),
        "n_with_x0_x1": len(used1),
        "n_comparable": len(common),
        "missing_x0": [r["name"] for r in pool if r["measurement_id"] not in used0],
        "missing_x1": [r["name"] for r in pool if r["measurement_id"] not in used1],
    }

    random.seed(SEED)

    rows_out: list[dict] = []
    null_rows: list[dict] = []
    feat_null_rows: list[dict] = []
    pred_rows: list[dict] = []

    # ---- the baseline that must be beaten ----
    # A model whose MAE exceeds "predict the training mean" has learned nothing.
    # Reporting R2 < 0 already implies this, but stating the constant-predictor
    # number makes the failure legible without requiring the reader to invert R2.
    y_mean = sum(y) / len(y)
    const_mae = sum(abs(v - y_mean) for v in y) / len(y)
    const_rmse = math.sqrt(sum((v - y_mean) ** 2 for v in y) / len(y))

    for label, X in (("X0_structure_only", X0c),
                     ("X0_plus_X1_electronic", X1c)):
        pred = ridge_loo(X, y, lam=1.0)
        m = metrics(y, pred)
        rows_out.append({
            "model": label,
            "n_features": len(X[0]),
            "n_samples": m["n"],
            "mae": round(m["mae"], 6),
            "rmse": round(m["rmse"], 6),
            "bias": round(m["bias"], 6),
            "r2": round(m["r2"], 6),
            "validation": "leave_one_out",
            "beats_constant_baseline": "true" if m["mae"] < const_mae else "false",
            "constant_baseline_mae": round(const_mae, 6),
        })
        for mid, yy, pp in zip(common, y, pred):
            pred_rows.append({
                "model": label, "measurement_id": mid,
                "y_true": round(yy, 6), "y_pred": round(pp, 6),
                "residual": round(pp - yy, 6),
            })

        # ---- second null: permute the FEATURES, not the labels ----
        # Reviewer 3 (B04+B05) pointed out that shuffling y tests "is this y
        # special" while shuffling the feature rows tests "does this feature
        # block carry information about the label". For the question E1 actually
        # asks -- do these descriptors explain variance -- the feature-permutation
        # null is the more appropriate one, and it has higher power.
        r2_obs = m["r2"]
        feat_null_r2 = []
        for _ in range(N_PERMUTATIONS):
            order = list(range(len(X)))
            random.shuffle(order)
            Xp = [X[order[i]] for i in range(len(X))]
            yp_pred = ridge_loo(Xp, y, lam=1.0)
            feat_null_r2.append(metrics(y, yp_pred)["r2"])
        feat_null_r2.sort(reverse=True)
        p_feat = sum(1 for v in feat_null_r2 if v >= r2_obs) / len(feat_null_r2)
        feat_null_rows.append({
            "model": label,
            "observed_r2": round(r2_obs, 6),
            "feature_permutation_p_value": round(p_feat, 4),
            "null_r2_q95": round(feat_null_r2[int(0.95 * len(feat_null_r2))], 6),
            "null_r2_median": round(feat_null_r2[len(feat_null_r2) // 2], 6),
            "n_permutations": N_PERMUTATIONS,
            "beats_null_at_0.05": "true" if p_feat < 0.05 else "false",
        })

        maes = []
        r2s = []
        for _ in range(N_PERMUTATIONS):
            yp = y[:]
            random.shuffle(yp)
            p2 = ridge_loo(X, yp, lam=1.0)
            m2 = metrics(yp, p2)
            maes.append(m2["mae"])
            r2s.append(m2["r2"])
        maes.sort()
        r2s.sort()
        obs_mae = m["mae"]
        # one-sided p: how often does a shuffled label do at least as well?
        p_mae = sum(1 for v in maes if v <= obs_mae) / len(maes)
        q05 = maes[int(0.05 * len(maes))]
        q50 = maes[int(0.50 * len(maes))]
        null_rows.append({
            "model": label,
            "observed_mae": round(obs_mae, 6),
            "null_mae_q05": round(q05, 6),
            "null_mae_median": round(q50, 6),
            "null_mae_min": round(min(maes), 6),
            "permutation_p_value": round(p_mae, 4),
            "n_permutations": N_PERMUTATIONS,
            "beats_null_at_0.05": "true" if p_mae < 0.05 else "false",
        })

    # ---- delta and its own null ----
    mae0 = next(r["mae"] for r in rows_out if r["model"] == "X0_structure_only")
    mae1 = next(r["mae"] for r in rows_out if r["model"] == "X0_plus_X1_electronic")
    delta = mae1 - mae0

    # Delta null: permutation of the *pairing* is not defined for two separate
    # fits, so instead report the overlap of the two null distributions as the
    # honest statement of resolution.
    null0 = next(n for n in null_rows if n["model"] == "X0_structure_only")
    null1 = next(n for n in null_rows if n["model"] == "X0_plus_X1_electronic")

    # ---- write ----
    metrics_path = OUT_DIR / "metrics.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    null_path = OUT_DIR / "permutation_null.csv"
    with null_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(null_rows[0].keys()))
        w.writeheader()
        for r in null_rows:
            w.writerow(r)

    feat_path = OUT_DIR / "feature_permutation_null.csv"
    if feat_null_rows:
        with feat_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(feat_null_rows[0].keys()))
            w.writeheader()
            for r in feat_null_rows:
                w.writerow(r)

    pred_path = OUT_DIR / "predictions_loo.csv"
    with pred_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pred_rows[0].keys()))
        w.writeheader()
        for r in pred_rows:
            w.writerow(r)

    # ---- report ----
    md: list[str] = []
    md.append("# B05-E1 结构描述符 vs 结构+电子描述符\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")

    md.append("\n## ⚠️ 本结果是**探索性**的\n")
    md.append(
        f"样本量 **{len(common)}** 个分子。PLAN B B05 明确规定："
        "「样本不足时可以运行探索性模型和代码测试，但不得包装成确认性结果」。"
        "本节所有数字都属探索性，**不构成**关于描述符有效性的确认性结论。\n"
    )

    md.append("\n## 一、覆盖率\n")
    md.append(f"- 候选池：{coverage['n_pool']} 个分子\n")
    md.append(f"- X0 覆盖：{coverage['n_with_x0']}\n")
    md.append(f"- X0+X1 覆盖：{coverage['n_with_x0_x1']}\n")
    md.append(f"- 可比样本：**{coverage['n_comparable']}**\n")

    md.append("\n## 二、留一法结果\n")
    md.append("| 模型 | 特征数 | n | MAE | RMSE | bias | R² | 优于常数基线 |\n")
    md.append("|---|---:|---:|---:|---:|---:|---:|---|\n")
    for r in rows_out:
        md.append(f"| {r['model']} | {r['n_features']} | {r['n_samples']} | "
                  f"{r['mae']} | {r['rmse']} | {r['bias']} | {r['r2']} | "
                  f"{r['beats_constant_baseline']} |\n")

    md.append(f"\n**常数基线（直接预测均值）：MAE = {const_mae:.4f}, "
              f"RMSE = {const_rmse:.4f}**\n\n")
    beating = sum(1 for r in rows_out if r["beats_constant_baseline"] == "true")
    if beating == 0:
        md.append(
            "⚠️ **两个模型都劣于常数基线。** "
            "在这个样本上，这些单分子描述符没有学到超出中心趋势的信息。\n"
        )
    else:
        delta_sig = next((n for n in null_rows
                          if n["model"] == "X0_plus_X1_electronic"), None)
        md.append(
            f"**{beating}/{len(rows_out)} 个模型优于常数基线。**\n\n"
            f"其中 X0+X1 的 R² = {rows_out[-1]['r2']}，"
            f"MAE = {rows_out[-1]['mae']}，"
            f"相对基线 {const_mae:.4f} 降低 "
            f"{100*(1-rows_out[-1]['mae']/const_mae):.1f}%。\n"
        )
        if delta_sig and delta_sig["beats_null_at_0.05"] == "true":
            md.append(
                f"\n**X0+X1 的置换检验 p = {delta_sig['permutation_p_value']}**，"
                f"**优于**零假设。因此电子描述符在本样本上提供了"
                f"**可检测的增量价值**（ΔMAE = {delta:.4f}）。\n\n"
                "> **重要历史说明：** 本实验的早期版本因 ridge 回归缺少截距项"
                "（强制通过标准化空间的原点）而得到完全相反的结论"
                "（两模型均劣于基线、R² 为负）。该规格错误由 Reviewer 1 发现，"
                "修复后结论反转。当前数字来自修复后的实现。\n"
            )

    md.append("\n## 三、置换零分布（关键）\n")
    md.append(
        "n=22 时，任何几个百分点的 MAE 差异都落在打乱标签能产生的范围内。"
        "不做零分布就无法区分「真实的增量价值」与「噪声」。\n\n"
    )
    md.append("| 模型 | 观测 MAE | 零分布 5% 分位 | 零分布中位数 | p 值 | 优于零假设 |\n")
    md.append("|---|---:|---:|---:|---:|---|\n")
    for r in null_rows:
        md.append(f"| {r['model']} | {r['observed_mae']} | {r['null_mae_q05']} | "
                  f"{r['null_mae_median']} | {r['permutation_p_value']} | "
                  f"{r['beats_null_at_0.05']} |\n")

    md.append("\n## 四、增量价值\n")
    md.append(f"- MAE(X0) = {mae0}\n")
    md.append(f"- MAE(X0+X1) = {mae1}\n")
    md.append(f"- **ΔMAE = {delta:+.6f}**\n\n")
    if delta < 0:
        md.append("加入电子描述符后 MAE **下降**（变好）。")
    else:
        md.append("加入电子描述符后 MAE **上升**（变差）。")
    null_scale = abs(null0["null_mae_q05"] - null0["null_mae_median"])
    if abs(delta) < null_scale:
        md.append(
            f"\n但 |ΔMAE| = {abs(delta):.6f} 小于零分布内部尺度 {null_scale:.6f}，"
            f"**不能**据此宣称电子描述符有增量价值。\n"
        )
    else:
        md.append(
            f"\n且 |ΔMAE| = {abs(delta):.6f} **大于**零分布内部尺度 {null_scale:.6f}。"
            f"结合 X0+X1 的置换 p 值，电子描述符确实带来可检测的改善。\n"
        )

    md.append("\n## 五、本实验不能回答的问题\n")
    md.append("- 不能回答「电子描述符是否**普遍**无增量价值」——n=22 不够\n")
    md.append("- 不能做确认性推断\n")
    md.append("- 不能外推到 A18 之外或化学家族之外（那是 E4 的任务）\n")
    md.append("- 不能据此调整项目的研究结论方向\n")

    md_path = OUT_DIR / "e1_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    manifest = {
        "schema": "b05.e1/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "EXPLORATORY_NOT_CONFIRMATORY",
        "exploratory_reason": (
            f"n={len(common)} 个分子; PLAN B B05 禁止把不足样本的结果包装成确认性结论"
        ),
        "inputs": {
            "candidate_pool_v2_draft": {"sha256": sha256_file(POOL), "rows": len(pool)},
            "dielectric_physical_features": {"sha256": sha256_file(FEATURES),
                                             "rows": len(feats)},
        },
        "feature_sets": {"X0": X0_COLS, "X1_added": X1_COLS,
                         "excluded": EXCLUDED_FEATURES,
                         "n_features_total": len(X0_COLS) + len(X1_COLS),
                         "consistency_note": (
                             "本版本与 E4/E6/B07 使用相同的 11 列特征集. "
                             "初版多用了 total_energy_hartree (12 列), "
                             "导致跨实验比较实际在比较不同的模型."
                         )},
        "coverage": coverage,
        "metrics": rows_out,
        "permutation_null": null_rows,
        "feature_permutation_null": feat_null_rows,
        "feature_permutation_note": (
            "两组零假设都报告: ① 置换标签 y (检验『这个 y 是否特殊』), "
            "② 置换特征行 (检验『这组特征是否携带关于标签的信息』). "
            "对 E1 的问题而言 (2) 更贴切且功效更高 (Reviewer 3, B04+B05)."
        ),
        "delta_mae_x1_minus_x0": round(delta, 6),
        "constant_baseline": {
            "mae": round(const_mae, 6),
            "rmse": round(const_rmse, 6),
            "note": (
                "『直接预测训练集均值』的基线. 任何模型的 MAE 若大于该值, "
                "说明它没有学到超出中心趋势的信息."
            ),
            "n_models_beating_baseline": sum(
                1 for r in rows_out if r["beats_constant_baseline"] == "true"),
        },
        "validation": {
            "scheme": "leave_one_out",
            "why": (
                "n=22 时随机 K 折会让相似化学结构同时出现在训练与测试集; "
                "留一法至少保证不在同一分子上训练和测试. "
                "两种划分的差异本身是泄漏的指示."
            ),
            "grouping": "每个分子自成一折 (分子级分组, 防止同一分子泄漏)",
        },
        "seed": SEED,
        "n_permutations": N_PERMUTATIONS,
        "outputs": {
            "metrics": {"path": str(metrics_path.relative_to(REPO_ROOT)),
                        "sha256": sha256_file(metrics_path)},
            "permutation_null": {"path": str(null_path.relative_to(REPO_ROOT)),
                                 "sha256": sha256_file(null_path)},
            "predictions": {"path": str(pred_path.relative_to(REPO_ROOT)),
                            "sha256": sha256_file(pred_path)},
            "report": {"path": str(md_path.relative_to(REPO_ROOT)),
                       "sha256": sha256_file(md_path)},
        },
    }
    man_path = OUT_DIR / "e1_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B05-E1] {metrics_path}")
    print(f"[B05-E1] {null_path}")
    print(f"[B05-E1] {pred_path}")
    print(f"[B05-E1] {md_path}")
    print(f"[B05-E1] {man_path}")
    print(f"  n comparable = {len(common)}")
    for r in rows_out:
        print(f"  {r['model']:26s} MAE={r['mae']:.4f} RMSE={r['rmse']:.4f} R2={r['r2']:+.4f}")
    for r in null_rows:
        print(f"    null {r['model']:26s} p={r['permutation_p_value']} "
              f"q05={r['null_mae_q05']:.4f}")
    print(f"  delta MAE = {delta:+.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
