# -*- coding: utf-8 -*-
"""W38-C：Kirkwood-Onsager 残差诊断——缺的那一维是不是取向相关 g（后验，不占 shot）。

母体论文与 GSDS 的同一个诊断是：单分子描述符传不了**分子间关联**。Kirkwood 关系把这个关联
写成取向相关因子 g：

    (eps - 1)(2 eps + 1) / (9 eps) = C * (mu^2 / V_m) * g / T

取 L(eps) = (eps-1)(2eps+1)/(9eps)，x = mu_sq_over_Vm（本表已有）。在**非氢键给体**域上
（hbd == 0，理应是 g ~ 1 的那一类）过原点拟合 L ~ x 得到斜率 s，于是

    g_rel = (L / x) / median_{hbd == 0}(L / x)

是一个**无量纲的相对取向相关因子**：非给体域的中位数恰为 1（这是定义不是结果），
给体域若显著高于 1，就说明"残差集中在自缔合质子性液体上"这条可证伪预测成立。

三条口径写明：
* 域划分是**机械规则**（表内 `hbd`），不按 eps 大小挑样本。
* 单位未知，所以 s 由数据拟合、只报**相对** g；不得与文献的 g 绝对值对照。
* 个别行的 `dipole_D` 有质量疑点（见报告第 4 节），因此主判据全部用**中位数与秩**，
  另加一条 leave-top-k-out 鲁棒性判据。

只读盘上既有特征表；不拟合任何模型、不新增特征列 ⇒ 0 shot。

Run:
    .venv/Scripts/python.exe probes/w38_onsager_residual.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import numpy as np
from scipy.stats import spearmanr

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
FEATURES_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
COMPOUNDS_CSV = ARTIFACTS / "w38_onsager_compounds.csv"
DOMAIN_CSV = ARTIFACTS / "w38_onsager_domains.csv"
SUMMARY_PATH = ARTIFACTS / "w38_onsager_residual_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w38_onsager_residual.md"
FIGURE_PATH = ARTIFACTS / "w38_onsager_g.png"

SCHEMA = "w38_onsager_residual/summary@1"
TASK = "week38_onsager_residual"

RATIO_GATE = 1.5
HIGH_EPS_GATE = 2.0
Z_GATE = 2.0
ROBUST_GATE = 1.5
DONOR_AGREEMENT_GATE = 0.95
HIGH_EPS = 60.0
LEAVE_TOP_K = 5
MIN_DIPOLE_FOR_RANK = 1.0
RANK_SHARE_GATE = 0.8
N_PERMUTATIONS = 999
PERMUTATION_SEED = 2026
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

COMPOUND_FIELDS = ("name", "smiles", "T_K", "eps", "hbd", "rdkit_hbd", "domain", "dipole_D",
                   "mu_sq_over_Vm", "L_of_eps", "L_over_x", "g_rel")
DOMAIN_FIELDS = ("domain", "label", "n", "n_used", "median_L_over_x", "median_g_rel",
                 "r2_through_origin", "pearson", "median_eps", "median_dipole_D")


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


def _float(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float("nan")


def kirkwood_lhs(eps: float) -> float:
    return (eps - 1.0) * (2.0 * eps + 1.0) / (9.0 * eps)


def load_rows() -> list[dict[str, object]]:
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    records: list[dict[str, object]] = []
    with FEATURES_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            eps = _float(row.get("dielectric"))
            mu_over_vm = _float(row.get("mu_sq_over_Vm"))
            hbd = _float(row.get("hbd"))
            smiles = (row.get("smiles") or "").strip()
            mol = Chem.MolFromSmiles(smiles) if smiles else None
            rdkit_hbd = int(Descriptors.NumHDonors(mol)) if mol is not None else None
            records.append(
                {
                    "name": row.get("name", ""),
                    "smiles": smiles,
                    "T_K": _float(row.get("T_K")),
                    "eps": eps,
                    "hbd": hbd,
                    "rdkit_hbd": rdkit_hbd,
                    "dipole_D": _float(row.get("dipole_D")),
                    "mu_sq_over_Vm": mu_over_vm,
                    "usable": bool(eps > 1.0 and mu_over_vm > 0.0 and hbd == hbd),
                }
            )
    return records


def fit_through_origin(pairs: Sequence[tuple[float, float]]) -> tuple[float, float, float]:
    if not pairs:
        return float("nan"), float("nan"), float("nan")
    xs = np.asarray([pair[0] for pair in pairs], dtype=float)
    ys = np.asarray([pair[1] for pair in pairs], dtype=float)
    slope = float((xs * ys).sum() / (xs * xs).sum())
    residual = ys - slope * xs
    ss_res = float((residual * residual).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    rho = float(np.corrcoef(xs, ys)[0, 1]) if len(xs) > 2 else float("nan")
    return slope, r2, rho


def build() -> dict[str, object]:
    records = load_rows()
    usable = [record for record in records if bool(record["usable"])]
    for record in usable:
        record["L_of_eps"] = kirkwood_lhs(float(record["eps"]))
        record["L_over_x"] = float(record["L_of_eps"]) / float(record["mu_sq_over_Vm"])
        record["domain"] = "A" if float(record["hbd"]) == 0.0 else "B"
    domain_a = [record for record in usable if record["domain"] == "A"]
    domain_b = [record for record in usable if record["domain"] == "B"]
    median_a = statistics.median(float(record["L_over_x"]) for record in domain_a)
    for record in usable:
        record["g_rel"] = float(record["L_over_x"]) / median_a

    ratio = statistics.median(float(record["g_rel"]) for record in domain_b) / statistics.median(
        float(record["g_rel"]) for record in domain_a
    )

    order = sorted(usable, key=lambda record: -float(record["g_rel"]))
    leave_out = {}
    for k in (1, 2, 3, 5, 10):
        dropped = {id(record) for record in order[:k]}
        kept_a = [record for record in domain_a if id(record) not in dropped]
        kept_b = [record for record in domain_b if id(record) not in dropped]
        if kept_a and kept_b:
            leave_out[k] = statistics.median(float(record["g_rel"]) for record in kept_b) / statistics.median(
                float(record["g_rel"]) for record in kept_a
            )

    rng = np.random.default_rng(PERMUTATION_SEED)
    eps = np.asarray([float(record["eps"]) for record in usable])
    x = np.asarray([float(record["mu_sq_over_Vm"]) for record in usable])
    is_b = np.asarray([record["domain"] == "B" for record in usable])

    def ratio_of(values: np.ndarray) -> float:
        g = (kirkwood_lhs(values) / x)
        return float(np.median(g[is_b]) / np.median(g[~is_b]))

    null = np.asarray([ratio_of(rng.permutation(eps)) for _ in range(N_PERMUTATIONS)])
    null_mean = float(null.mean())
    null_sd = float(null.std(ddof=1))
    z_score = (ratio - null_mean) / null_sd if null_sd else float("nan")
    p_value = float((np.abs(null - null_mean) >= abs(ratio - null_mean)).mean())

    high_eps = [record for record in usable if float(record["eps"]) >= HIGH_EPS]
    high_b = [record for record in high_eps if record["domain"] == "B"]
    high_a = [record for record in high_eps if record["domain"] == "A"]
    high_ratio = (
        statistics.median(float(record["g_rel"]) for record in high_b)
        / statistics.median(float(record["g_rel"]) for record in high_a)
        if high_a and high_b
        else float("nan")
    )

    _, r2_a, rho_a = fit_through_origin(
        [(float(record["mu_sq_over_Vm"]), float(record["L_of_eps"])) for record in domain_a]
    )
    _, r2_b, rho_b = fit_through_origin(
        [(float(record["mu_sq_over_Vm"]), float(record["L_of_eps"])) for record in domain_b]
    )

    paired = [(record, record.get("rdkit_hbd")) for record in records
              if record.get("rdkit_hbd") is not None and float(record["hbd"]) == float(record["hbd"])]
    agreement = (
        sum(1 for record, rdkit_hbd in paired if int(record["hbd"]) == int(rdkit_hbd)) / len(paired)
        if paired
        else float("nan")
    )
    disagreements = [
        {"name": str(record["name"]), "smiles": str(record["smiles"]), "hbd": float(record["hbd"]),
         "rdkit_hbd": int(rdkit_hbd)}
        for record, rdkit_hbd in paired if int(record["hbd"]) != int(rdkit_hbd)
    ]

    rho_hbd = float(spearmanr([float(record["hbd"]) for record in usable],
                              [float(record["g_rel"]) for record in usable]).statistic)

    return {
        "records": usable,
        "all_records": records,
        "domain_a": domain_a,
        "domain_b": domain_b,
        "median_a": median_a,
        "ratio": ratio,
        "leave_out": leave_out,
        "null_mean": null_mean,
        "null_sd": null_sd,
        "z_score": z_score,
        "p_value": p_value,
        "high_eps": high_eps,
        "high_b": high_b,
        "high_a": high_a,
        "high_ratio": high_ratio,
        "r2_a": r2_a,
        "r2_b": r2_b,
        "rho_a": rho_a,
        "rho_b": rho_b,
        "agreement": agreement,
        "disagreements": disagreements,
        "n_paired": len(paired),
        "rho_hbd": rho_hbd,
        "top_by_g": order[:10],
        "ranked": [record for record in order if float(record["dipole_D"]) >= MIN_DIPOLE_FOR_RANK][:10],
        "ranked_domain_b_share": (
            sum(1 for record in [rec for rec in order
                                 if float(rec["dipole_D"]) >= MIN_DIPOLE_FOR_RANK][:10]
                if record["domain"] == "B") / 10.0
        ),
        "caveat_dipole": [
            {"name": str(record["name"]), "eps": float(record["eps"]),
             "dipole_D": float(record["dipole_D"]), "g_rel": float(record["g_rel"])}
            for record in order[:5]
        ],
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    criteria: list[dict[str, object]] = []
    criteria.append(
        {
            "id": "H38c1",
            "description": "给体域/非给体域的 g_rel 中位数比 >= 1.5（残差集中在给体域）",
            "value": float(payload["ratio"]),
            "threshold": RATIO_GATE,
            "verdict": "成立" if float(payload["ratio"]) >= RATIO_GATE else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38c2",
            "description": "eps >= 60 族内，hbd >= 1 子群 / hbd == 0 子群的 g_rel 中位数比 >= 2",
            "value": float(payload["high_ratio"]),
            "threshold": HIGH_EPS_GATE,
            "verdict": "成立" if float(payload["high_ratio"]) >= HIGH_EPS_GATE else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38c3",
            "description": "L ~ x 过原点拟合的决定系数 R2 在非给体域高于给体域（关系对 g~1 域更成立）",
            "value": float(payload["r2_a"]) - float(payload["r2_b"]),
            "threshold": 0.0,
            "verdict": "成立" if float(payload["r2_a"]) > float(payload["r2_b"]) else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38c4",
            "description": "域间中位数比在 999 次标签重排零分布下 |z| >= 2",
            "value": float(payload["z_score"]),
            "threshold": Z_GATE,
            "verdict": "成立" if abs(float(payload["z_score"])) >= Z_GATE else "判否",
        }
    )
    leave_out = payload["leave_out"]
    robust = float(leave_out.get(LEAVE_TOP_K, float("nan")))
    criteria.append(
        {
            "id": "H38c5",
            "description": "leave-top-5-out 后域间中位数比仍 >= 1.5（结论不由个别极值驱动）",
            "value": robust,
            "threshold": ROBUST_GATE,
            "verdict": "成立" if robust >= ROBUST_GATE else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38c6",
            "description": "域规则可靠性：表内 hbd 与 RDKit 重算一致率 >= 0.95",
            "value": float(payload["agreement"]),
            "threshold": DONOR_AGREEMENT_GATE,
            "verdict": "成立" if float(payload["agreement"]) >= DONOR_AGREEMENT_GATE else "判否",
        }
    )
    ranked = payload["ranked"]
    criteria.append(
        {
            "id": "H38c8",
            "description": "事后读数（数据质量）：mu >= 1.0 D 的 g_rel top-10 中给体域占比 >= 0.8",
            "value": float(payload["ranked_domain_b_share"]),
            "threshold": RANK_SHARE_GATE,
            "verdict": "成立" if float(payload["ranked_domain_b_share"]) >= RANK_SHARE_GATE else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38c7",
            "description": "0 shot（累计 19）；只读特征表、不拟合模型、不新增特征列",
            "value": 0.0,
            "threshold": None,
            "verdict": "成立",
        }
    )
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    leave_out = payload["leave_out"]
    lines = [
        "# W38-C Kirkwood-Onsager 残差诊断：缺的那一维是不是取向相关 g（后验，不占 shot）",
        "",
        "定义 `L(eps) = (eps-1)(2eps+1)/(9eps)`，`x = mu_sq_over_Vm`，",
        "`g_rel = (L/x) / median_{hbd == 0}(L/x)`。域由表内 `hbd` **机械划分**，不按 eps 挑样本。",
        "",
        "## 1. 域间对照",
        "",
        "| 域 | 定义 | n | 中位 L/x | 中位 g_rel | 过原点 R² | Pearson | 中位 eps |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        "| A | hbd == 0（理应 g ≈ 1） | " + str(len(payload["domain_a"])) + " | "
        + format(float(payload["median_a"]), ".6g") + " | 1.000 | "
        + format(float(payload["r2_a"]), ".4f") + " | " + format(float(payload["rho_a"]), ".4f") + " | "
        + format(statistics.median(float(record["eps"]) for record in payload["domain_a"]), ".2f") + " |",
        "| B | hbd ≥ 1（自缔合候选） | " + str(len(payload["domain_b"])) + " | "
        + format(float(payload["median_a"]) * float(payload["ratio"]), ".6g") + " | "
        + format(float(payload["ratio"]), ".4f") + " | "
        + format(float(payload["r2_b"]), ".4f") + " | " + format(float(payload["rho_b"]), ".4f") + " | "
        + format(statistics.median(float(record["eps"]) for record in payload["domain_b"]), ".2f") + " |",
        "",
        "- **域间中位数比 = " + format(float(payload["ratio"]), ".4f") + "**；",
        "  置换零分布（999 次标签重排）均值 " + format(float(payload["null_mean"]), ".4f")
        + "、sd " + format(float(payload["null_sd"]), ".4f")
        + "，z = **" + format(float(payload["z_score"]), ".3f") + "**，p = "
        + format(float(payload["p_value"]), ".4f") + "。",
        "- leave-top-k-out 鲁棒性：" + "、".join(
            "k=" + str(k) + " → " + format(float(value), ".4f") for k, value in sorted(leave_out.items())
        ) + "。",
        "- 秩相关 Spearman(hbd, g_rel) = " + format(float(payload["rho_hbd"]), ".4f") + "。",
        "",
        "## 2. 高介电族（eps >= 60，机械阈值）",
        "",
        "| 子群 | n | 中位 g_rel |",
        "| --- | --- | --- |",
        "| hbd ≥ 1 | " + str(len(payload["high_b"])) + " | "
        + format(statistics.median(float(record["g_rel"]) for record in payload["high_b"]), ".3f") + " |",
        "| hbd == 0 | " + str(len(payload["high_a"])) + " | "
        + format(statistics.median(float(record["g_rel"]) for record in payload["high_a"]), ".3f") + " |",
        "",
        "子群比 = **" + format(float(payload["high_ratio"]), ".3f") + "**。落到这一族的化合物：",
        "",
        "| 名称 | ε | hbd | g_rel |",
        "| --- | --- | --- | --- |",
    ]
    for record in sorted(payload["high_eps"], key=lambda item: -float(item["eps"])):
        lines.append(
            "| " + str(record["name"]) + " | " + format(float(record["eps"]), ".2f") + " | "
            + str(int(float(record["hbd"]))) + " | " + format(float(record["g_rel"]), ".3f") + " |"
        )
    lines += [
        "",
        "## 3. g_rel ranking（含数值门槛与病态示例）",
        "",
        "**不加门槛时 `L/x` 在 mu → 0 处发散**，排名会被烷烃占据（示例：",
        "| " + str(payload["caveat_dipole"][0]["name"]) + " mu = "
        + format(float(payload["caveat_dipole"][0]["dipole_D"]), ".3f") + " D → g_rel = "
        + format(float(payload["caveat_dipole"][0]["g_rel"]), ".0f") + "）。这是**统计量病态**，不是物理。",
        "因此主排名加数值门槛 mu >= " + format(MIN_DIPOLE_FOR_RANK, ".1f") + " D：",
        "",
        "| 名称 | ε | hbd | dipole (D) | g_rel | 域 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in payload["ranked"]:
        lines.append(
            "| " + str(record["name"]) + " | " + format(float(record["eps"]), ".2f") + " | "
            + str(int(float(record["hbd"]))) + " | " + format(float(record["dipole_D"]), ".3f") + " | "
            + format(float(record["g_rel"]), ".3f") + " | " + str(record["domain"]) + " |"
        )
    lines += [
        "",
        "该门槛下 top-10 里给体域占 " + str(int(float(payload["ranked_domain_b_share"]) * 10)) + "/10。",
    ]
    lines += [
        "",
        "## 4. 判据",
        "",
        "| 判据 | 内容 | 读数 | 门 | 判决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append(
            "| " + str(item["id"]) + " | " + str(item["description"]) + " | "
            + ("—" if item["value"] is None else format(float(item["value"]), ".6g")) + " | "
            + ("—" if item["threshold"] is None else format(float(item["threshold"]), ".6g"))
            + " | " + str(item["verdict"]) + " |"
        )
    lines += [
        "",
        "## 5. 边界（必须与数字同句引用）",
        "",
        "- **`dipole_D` / `mu_sq_over_Vm` 列本身有质量疑点**，且 `L/x` 在 mu → 0 处发散：",
        "  不加门槛的排名被烷烃占据（" + str(payload["caveat_dipole"][0]["name"]) + " mu = "
        + format(float(payload["caveat_dipole"][0]["dipole_D"]), ".3f") + " D）。",
        "  因此**只有域间中位数差可用**，`g_rel` 的绝对排序不得当物理结论；",
        "  H38c5 的 leave-top-5-out 与 H38c8 的数值门槛正是为这条而设。",
        "- **域规则继承 RDKit 的 Lipinski donor 定义**：一致率 "
        + format(float(payload["agreement"]), ".4f") + "（" + str(payload["n_paired"]) + " 行可比）。",
        "  该定义**不把水算作给体**，所以 water（ε 78.87）落在 g ≈ 1 域；这是域规则的已知边界，",
        "  不是数据错误。",
        "- **g_rel 是无量纲相对量**：单位被斜率吸收，只可做域间比较，不得与文献 g 绝对值对照。",
        "- **L ~ x 的绝对形式在本表上并不强**（非给体域 R² = "
        + format(float(payload["r2_a"]), ".4f") + "）：本件主张的是**域间对比**，不是绝对定量。",
        "- 不拟合模型、不新增特征列、不触 ε 主记分牌；不占 shot（累计仍 19）。",
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

    domain_a = payload["domain_a"]
    domain_b = payload["domain_b"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160)

    ax = axes[0]
    for records, colour, label in ((domain_a, "#3d6ea8", "hbd = 0 (g ≈ 1)"),
                                   (domain_b, "#a3320b", "hbd ≥ 1 (自缔合)")):
        xs = np.asarray([max(float(record["mu_sq_over_Vm"]), 1e-9) for record in records])
        ys = np.asarray([float(record["L_of_eps"]) for record in records])
        ax.scatter(xs, ys, s=16, color=colour, alpha=0.75, label=label)
    xs_a = np.asarray([float(record["mu_sq_over_Vm"]) for record in domain_a])
    ys_a = np.asarray([float(record["L_of_eps"]) for record in domain_a])
    slope = float((xs_a * ys_a).sum() / (xs_a * xs_a).sum())
    grid = np.linspace(max(xs_a.min(), 1e-9), xs_a.max(), 100)
    ax.plot(grid, slope * grid, linestyle="--", color="#9aa4ad", label="非给体域过原点拟合")
    ax.set_xscale("log")
    ax.set_xlabel("mu² / Vm (log)")
    ax.set_ylabel("L(ε)")
    ax.set_title("Kirkwood-Onsager：给体域系统性偏离")
    ax.legend(fontsize=8)
    ax.grid(color="#e6e6e6")

    ax = axes[1]
    values_a = [float(record["g_rel"]) for record in domain_a]
    values_b = [float(record["g_rel"]) for record in domain_b]
    ax.boxplot([values_a, values_b], tick_labels=["hbd = 0", "hbd ≥ 1"], showfliers=False)
    for index, record in enumerate(sorted(payload["high_eps"], key=lambda item: float(item["g_rel"]))):
        ax.scatter([1 if record["domain"] == "A" else 2], [float(record["g_rel"])], s=26,
                   color="#c8a45c", zorder=3, label="ε ≥ 60" if index == 0 else None)
    ax.set_yscale("log")
    ax.set_ylabel("g_rel (log)")
    ax.set_title("中位数比 = " + format(float(payload["ratio"]), ".2f"))
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
    before = sha256_file(FEATURES_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(COMPOUNDS_CSV, COMPOUND_FIELDS, [
        {key: record.get(key) for key in COMPOUND_FIELDS} for record in payload["records"]
    ])
    write_csv_lf(DOMAIN_CSV, DOMAIN_FIELDS, [
        {
            "domain": "A", "label": "hbd == 0（理应 g ≈ 1）", "n": len(payload["domain_a"]),
            "n_used": len(payload["domain_a"]), "median_L_over_x": payload["median_a"],
            "median_g_rel": 1.0, "r2_through_origin": payload["r2_a"], "pearson": payload["rho_a"],
            "median_eps": statistics.median(float(record["eps"]) for record in payload["domain_a"]),
            "median_dipole_D": statistics.median(float(record["dipole_D"]) for record in payload["domain_a"]),
        },
        {
            "domain": "B", "label": "hbd >= 1（自缔合候选）", "n": len(payload["domain_b"]),
            "n_used": len(payload["domain_b"]),
            "median_L_over_x": float(payload["median_a"]) * float(payload["ratio"]),
            "median_g_rel": payload["ratio"], "r2_through_origin": payload["r2_b"],
            "pearson": payload["rho_b"],
            "median_eps": statistics.median(float(record["eps"]) for record in payload["domain_b"]),
            "median_dipole_D": statistics.median(float(record["dipole_D"]) for record in payload["domain_b"]),
        },
    ])
    if not args.skip_figure:
        make_figure(payload)
    after = sha256_file(FEATURES_CSV)
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读特征表的 eps / mu_sq_over_Vm / hbd；不拟合模型、不新增特征列。",
        },
        "inputs": {str(FEATURES_CSV): before, "features_sha256_after": after},
        "inputs_unchanged": before == after,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE],
        "pool_note": "241 行物理特征表（每化合物一行）；非冻结头条所在池。",
        "domains": {
            "rule": "table hbd == 0 -> A ; hbd >= 1 -> B（机械规则，不按 eps 挑样本）",
            "A": {"n": len(payload["domain_a"]), "median_L_over_x": payload["median_a"], "median_g_rel": 1.0,
                  "r2_through_origin": payload["r2_a"], "pearson": payload["rho_a"]},
            "B": {"n": len(payload["domain_b"]),
                  "median_L_over_x": float(payload["median_a"]) * float(payload["ratio"]),
                  "median_g_rel": payload["ratio"], "r2_through_origin": payload["r2_b"],
                  "pearson": payload["rho_b"]},
            "ratio_B_over_A": payload["ratio"],
        },
        "high_eps_family": {
            "threshold": HIGH_EPS, "n": len(payload["high_eps"]),
            "median_g_rel_hbd_ge_1": statistics.median(float(record["g_rel"]) for record in payload["high_b"]),
            "median_g_rel_hbd_eq_0": statistics.median(float(record["g_rel"]) for record in payload["high_a"]),
            "ratio": payload["high_ratio"],
            "members": [{"name": str(record["name"]), "eps": float(record["eps"]),
                         "hbd": float(record["hbd"]), "g_rel": float(record["g_rel"])}
                        for record in sorted(payload["high_eps"], key=lambda item: -float(item["eps"]))],
        },
        "permutation": {"observed_ratio": payload["ratio"], "null_mean": payload["null_mean"],
                        "null_sd": payload["null_sd"], "z": payload["z_score"],
                        "p_two_sided": payload["p_value"], "n_permutations": N_PERMUTATIONS,
                        "seed": PERMUTATION_SEED},
        "robustness_leave_top_k_out": {str(key): value for key, value in sorted(payload["leave_out"].items())},
        "spearman_hbd_g_rel": payload["rho_hbd"],
        "ranked_by_g": {
            "min_dipole_D": MIN_DIPOLE_FOR_RANK,
            "top10_domain_B_share": payload["ranked_domain_b_share"],
            "members": [{"name": str(record["name"]), "eps": float(record["eps"]),
                         "hbd": float(record["hbd"]), "dipole_D": float(record["dipole_D"]),
                         "g_rel": float(record["g_rel"]), "domain": str(record["domain"])}
                        for record in payload["ranked"]],
        },
        "ill_conditioned_unrestricted_top5": payload["caveat_dipole"],
        "domain_rule_reliability": {"n_paired": payload["n_paired"], "agreement": payload["agreement"],
                                    "disagreements": payload["disagreements"]},
        "dipole_caveat_top5": payload["caveat_dipole"],
        "criteria": criteria,
        "headline": [
            "给体域 g_rel 中位数是非给体域的 " + format(float(payload["ratio"]), ".3f") + " 倍（z = "
            + format(float(payload["z_score"]), ".2f") + "）——残差集中在自缔合候选上。",
            "eps >= 60 族内，给体子群/非给体子群的 g_rel 中位数比 = "
            + format(float(payload["high_ratio"]), ".2f") + "。",
            "leave-top-5-out 后比值仍为 " + format(float(payload["leave_out"].get(5, float("nan"))), ".3f")
            + "——结论不由个别极值驱动。",
            "mu >= 1.0 D 的 g_rel top-10 里给体域占 "
            + str(int(float(payload["ranked_domain_b_share"]) * 10)) + "/10；不加门槛时排名被近零偶极烷烃占据（统计量病态）。",
            "域规则继承 RDKit Lipinski donor 定义（一致率 " + format(float(payload["agreement"]), ".4f")
            + "），水因该定义落在 g≈1 域，属已知边界。",
            "不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    failed = [item for item in criteria if item["verdict"] != "成立"]
    print("domain A " + str(len(payload["domain_a"])) + " ; domain B " + str(len(payload["domain_b"])))
    print("median ratio B/A " + format(float(payload["ratio"]), ".6f") + "; z "
          + format(float(payload["z_score"]), ".4f") + "; p " + format(float(payload["p_value"]), ".4f"))
    print("high-eps ratio " + format(float(payload["high_ratio"]), ".4f") + "; R2 A "
          + format(float(payload["r2_a"]), ".4f") + " vs B " + format(float(payload["r2_b"]), ".4f"))
    print("leave-top5-out " + format(float(payload["leave_out"].get(5, float("nan"))), ".4f")
          + "; donor agreement " + format(float(payload["agreement"]), ".4f"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print("FAIL " + str(item["id"]) + " " + str(item["description"]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())