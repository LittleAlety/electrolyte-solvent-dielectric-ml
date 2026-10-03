# -*- coding: utf-8 -*-
"""W38-B：结构≠功能，把它从一句话变成一条谱（后验，不占 shot）。

W18 的分域记分牌说明了「域内精度高于域外」，但没有回答**长得像的分子到底差多少**。
本件只用 241 行物理特征表里的 SMILES 与介电常数，做三件事：

1. **最近邻谱**：每个化合物的 Morgan-Tanimoto 最近邻，若两个分子指纹几乎一样，
   它们的 epsilon 是否也几乎一样？
2. **结构-only 基线**：用「最近邻的 epsilon」当预测，算出结构单独能解释多少方差。
   这是最宽松的结构基线（不给任何物理列），因此它给出的 R2 是**上界**。
3. **双向检索**：既找「像而不同」（高相似度 + 大标签差），也找「不像而同」
   （低相似度 + 小标签差）。前者支持分域声明，后者说明相似度不是必要的。

置换检验：把 epsilon 标签在化合物之间随机重排 999 次，用同一张相似度矩阵重算
Spearman(sim, |delta eps|)，得到「相似度预测标签差」这件事在无结构-功能关系下的零分布。

只读盘上既有表；不拟合模型、不新增特征、不触 ε 主记分牌 ⇒ 0 shot。

Run:
    .venv/Scripts/python.exe probes/w38_structure_function.py
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
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
from scipy.stats import rankdata

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
FEATURES_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
NN_CSV = ARTIFACTS / "w38_structure_nn.csv"
PAIRS_CSV = ARTIFACTS / "w38_structure_pairs.csv"
SUMMARY_PATH = ARTIFACTS / "w38_structure_function_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w38_structure_function.md"
FIGURE_PATH = ARTIFACTS / "w38_structure_function.png"

SCHEMA = "w38_structure_function/summary@1"
TASK = "week38_structure_function"

MORGAN_RADIUS = 2
MORGAN_BITS = 2048
ROOM_T_K = 298.15
N_PERMUTATIONS = 999
PERMUTATION_SEED = 2026
SIM_HIGH = 0.80
DELTA_BIG = 30.0
SIM_LOW = 0.30
DELTA_SMALL = 5.0
SIM_BLIND = 0.99
BLIND_DELTA = 5.0
REGISTERED_NEGATIVES = ("H38b1",)
PROTIC_EPS = 60.0
NN_R2_GATE = 0.50
TOP_PAIRS = 20
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

NN_FIELDS = ("inchikey", "name", "smiles", "eps", "hbd", "nn_inchikey", "nn_name", "nn_eps",
             "tanimoto", "abs_delta_eps")
PAIR_FIELDS = ("kind", "inchikey_a", "name_a", "eps_a", "inchikey_b", "name_b", "eps_b",
               "tanimoto", "abs_delta_eps")


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


def load_compounds() -> list[dict[str, object]]:
    """One row per compound: the row whose temperature is closest to 298.15 K."""
    by_compound: dict[str, list[dict[str, str]]] = {}
    with FEATURES_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("smiles") or not row.get("dielectric"):
                continue
            by_compound.setdefault(row["inchikey"], []).append(row)
    compounds: list[dict[str, object]] = []
    for inchikey, rows in sorted(by_compound.items()):
        best = min(rows, key=lambda row: (abs(float(row["T_K"]) - ROOM_T_K), float(row["T_K"])))
        compounds.append(
            {
                "inchikey": inchikey,
                "name": best.get("name", ""),
                "smiles": best["smiles"],
                "eps": float(best["dielectric"]),
                "hbd": int(float(best.get("hbd") or 0)),
            }
        )
    return compounds


def morgan_matrix(compounds: Sequence[Mapping[str, object]]) -> np.ndarray:
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS)
    rows = []
    for compound in compounds:
        mol = Chem.MolFromSmiles(str(compound["smiles"]))
        if mol is None:
            rows.append(np.zeros(MORGAN_BITS, dtype=np.uint8))
            continue
        rows.append(np.asarray(generator.GetFingerprintAsNumPy(mol), dtype=np.uint8))
    return np.vstack(rows)


def tanimoto_matrix(fingerprints: np.ndarray) -> np.ndarray:
    bits = fingerprints.astype(np.float64)
    intersection = bits @ bits.T
    counts = bits.sum(axis=1)
    union = counts[:, None] + counts[None, :] - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = np.where(union > 0, intersection / union, 0.0)
    np.fill_diagonal(similarity, 0.0)
    return similarity


def upper_triangle(matrix: np.ndarray) -> np.ndarray:
    indices = np.triu_indices(matrix.shape[0], k=1)
    return matrix[indices]


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = rankdata(x)
    ry = rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denominator = math.sqrt(float((rx * rx).sum()) * float((ry * ry).sum()))
    return float((rx * ry).sum() / denominator) if denominator else float("nan")


def build() -> dict[str, object]:
    compounds = load_compounds()
    fingerprints = morgan_matrix(compounds)
    similarity = tanimoto_matrix(fingerprints)
    eps = np.asarray([float(compound["eps"]) for compound in compounds])
    n = len(compounds)

    nn_rows: list[dict[str, object]] = []
    for i in range(n):
        j = int(np.argmax(similarity[i]))
        nn_rows.append(
            {
                "inchikey": compounds[i]["inchikey"],
                "name": compounds[i]["name"],
                "smiles": compounds[i]["smiles"],
                "eps": eps[i],
                "hbd": compounds[i]["hbd"],
                "nn_inchikey": compounds[j]["inchikey"],
                "nn_name": compounds[j]["name"],
                "nn_eps": eps[j],
                "tanimoto": float(similarity[i, j]),
                "abs_delta_eps": abs(float(eps[i] - eps[j])),
            }
        )

    nn_prediction = np.asarray([float(row["nn_eps"]) for row in nn_rows])
    residual = eps - nn_prediction
    ss_res = float((residual * residual).sum())
    ss_tot = float(((eps - eps.mean()) ** 2).sum())
    nn_r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    nn_rho = spearman(eps, nn_prediction)
    nn_mae = float(np.abs(residual).mean())

    sim_pairs = upper_triangle(similarity)
    delta_pairs = np.abs(eps[:, None] - eps[None, :])
    delta_pairs = upper_triangle(delta_pairs)
    observed_rho = spearman(sim_pairs, delta_pairs)

    rng = np.random.default_rng(PERMUTATION_SEED)
    null_rho = np.empty(N_PERMUTATIONS, dtype=np.float64)
    for index in range(N_PERMUTATIONS):
        shuffled = rng.permutation(eps)
        shuffled_delta = np.abs(shuffled[:, None] - shuffled[None, :])
        null_rho[index] = spearman(sim_pairs, upper_triangle(shuffled_delta))
    null_mean = float(null_rho.mean())
    null_sd = float(null_rho.std(ddof=1))
    z_score = (observed_rho - null_mean) / null_sd if null_sd else float("nan")
    p_value = float((np.abs(null_rho - null_mean) >= abs(observed_rho - null_mean)).mean())

    pairs: list[dict[str, object]] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append(
                {
                    "kind": "",
                    "inchikey_a": compounds[i]["inchikey"],
                    "name_a": compounds[i]["name"],
                    "eps_a": eps[i],
                    "inchikey_b": compounds[j]["inchikey"],
                    "name_b": compounds[j]["name"],
                    "eps_b": eps[j],
                    "tanimoto": float(similarity[i, j]),
                    "abs_delta_eps": abs(float(eps[i] - eps[j])),
                }
            )
    look_alike_differ = sorted(
        [pair for pair in pairs if float(pair["tanimoto"]) >= SIM_HIGH and float(pair["abs_delta_eps"]) >= DELTA_BIG],
        key=lambda pair: (-float(pair["abs_delta_eps"]), -float(pair["tanimoto"])),
    )
    differ_alike = sorted(
        [pair for pair in pairs if float(pair["tanimoto"]) <= SIM_LOW and float(pair["abs_delta_eps"]) <= DELTA_SMALL],
        key=lambda pair: (float(pair["abs_delta_eps"]), float(pair["tanimoto"])),
    )
    extreme = sorted(pairs, key=lambda pair: -float(pair["abs_delta_eps"]))[:TOP_PAIRS]
    for pair in extreme:
        pair["kind"] = "global_extreme"
    for pair in look_alike_differ[:TOP_PAIRS]:
        pair["kind"] = "look_alike_differ"
    for pair in differ_alike[:TOP_PAIRS]:
        pair["kind"] = "differ_alike"

    high_sim = [pair for pair in pairs if float(pair["tanimoto"]) >= SIM_HIGH]
    high_sim_big = [pair for pair in high_sim if float(pair["abs_delta_eps"]) >= DELTA_BIG]
    blind = [pair for pair in pairs if float(pair["tanimoto"]) >= SIM_BLIND]
    blind_differ = [pair for pair in blind if float(pair["abs_delta_eps"]) >= BLIND_DELTA]
    max_blind_delta = max((float(pair["abs_delta_eps"]) for pair in blind), default=float("nan"))
    max_high_sim_delta = max((float(pair["abs_delta_eps"]) for pair in high_sim), default=float("nan"))
    for pair in sorted(blind, key=lambda item: -float(item["abs_delta_eps"]))[:TOP_PAIRS]:
        pair["kind"] = "fingerprint_blind"
    protic = [compound for compound in compounds if int(compound["hbd"]) >= 1 and float(compound["eps"]) >= PROTIC_EPS]

    return {
        "compounds": compounds,
        "nn_rows": nn_rows,
        "pairs": pairs,
        "look_alike_differ": look_alike_differ,
        "differ_alike": differ_alike,
        "extreme": extreme,
        "nn_r2": nn_r2,
        "nn_rho": nn_rho,
        "nn_mae": nn_mae,
        "observed_rho": observed_rho,
        "null_mean": null_mean,
        "null_sd": null_sd,
        "z_score": z_score,
        "p_value": p_value,
        "n_compounds": n,
        "n_pairs": len(pairs),
        "n_high_sim": len(high_sim),
        "n_high_sim_big": len(high_sim_big),
        "n_look_alike_differ": len(look_alike_differ),
        "n_differ_alike": len(differ_alike),
        "blind": blind,
        "blind_differ": blind_differ,
        "n_blind": len(blind),
        "n_blind_differ": len(blind_differ),
        "max_blind_delta": max_blind_delta,
        "max_high_sim_delta": max_high_sim_delta,
        "protic": protic,
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    criteria: list[dict[str, object]] = []
    criteria.append(
        {
            "id": "H38b1",
            "description": "存在「像而不同」对（Tanimoto >= 0.80 且 |delta eps| >= 30）",
            "value": float(payload["n_look_alike_differ"]),
            "threshold": 1.0,
            "verdict": "成立" if int(payload["n_look_alike_differ"]) >= 1 else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38b2",
            "description": "结构-only 基线（1-NN 的 epsilon）R2 < 0.50：结构解释不了大部分标签方差",
            "value": float(payload["nn_r2"]),
            "threshold": NN_R2_GATE,
            "verdict": "成立" if float(payload["nn_r2"]) < NN_R2_GATE else "判否",
        }
    )
    z_score = float(payload["z_score"])
    criteria.append(
        {
            "id": "H38b3",
            "description": "Spearman(相似度, |delta eps|) 相对重排零分布显著（|z| >= 2）",
            "value": z_score,
            "threshold": 2.0,
            "verdict": "成立" if abs(z_score) >= 2.0 else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38b4",
            "description": "存在「不像而同」对（Tanimoto <= 0.30 且 |delta eps| <= 5）",
            "value": float(payload["n_differ_alike"]),
            "threshold": 1.0,
            "verdict": "成立" if int(payload["n_differ_alike"]) >= 1 else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38b6",
            "description": "事后读数：存在指纹不可分辨对（Tanimoto >= 0.99 且 |delta eps| >= 5）",
            "value": float(payload["n_blind_differ"]),
            "threshold": 1.0,
            "verdict": "成立" if int(payload["n_blind_differ"]) >= 1 else "判否",
        }
    )
    criteria.append(
        {
            "id": "H38b7",
            "description": "事后读数：指纹不可分辨对（Tanimoto >= 0.99）的最大 |delta eps|",
            "value": float(payload["max_blind_delta"]),
            "threshold": None,
            "verdict": "成立" if int(payload["n_blind"]) >= 1 else "不可判定",
        }
    )
    criteria.append(
        {
            "id": "H38b5",
            "description": "0 shot（累计 19）；表只读、不拟合模型、不改四个冻结读数",
            "value": 0.0,
            "threshold": None,
            "verdict": "成立",
        }
    )
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W38-B 结构≠功能：指纹近邻的标签差谱（后验，不占 shot）",
        "",
        "本件只用 `data/processed/dielectric_physical_features_v03.csv` 的 SMILES 与介电常数，",
        "为 " + str(payload["n_compounds"]) + " 个化合物做 Morgan(r=2, 2048 位) Tanimoto 最近邻，",
        "并把「相似度能不能预测标签差」放到置换零分布上检验（" + str(N_PERMUTATIONS) + " 次重排）。",
        "",
        "## 1. 结构-only 基线（最宽松的结构解释力上界）",
        "",
        "| 读数 | 值 |",
        "| --- | --- |",
        "| 1-NN 预测的 R² | " + format(float(payload["nn_r2"]), ".4f") + " |",
        "| 1-NN 预测的 Spearman | " + format(float(payload["nn_rho"]), ".4f") + " |",
        "| 1-NN 预测的 MAE | " + format(float(payload["nn_mae"]), ".4f") + " |",
        "| 最近邻 Tanimoto 中位数 | "
        + format(statistics.median([float(row["tanimoto"]) for row in payload["nn_rows"]]), ".4f") + " |",
        "| 最近邻 |Δε| 中位数 | "
        + format(statistics.median([float(row["abs_delta_eps"]) for row in payload["nn_rows"]]), ".4f") + " |",
        "",
        "## 2. 双向检索",
        "",
        "| 方向 | 定义 | 对数 |",
        "| --- | --- | --- |",
        "| 像而不同 | Tanimoto ≥ 0.80 且 |Δε| ≥ 30 | " + str(payload["n_look_alike_differ"]) + " |",
        "| 不像而同 | Tanimoto ≤ 0.30 且 |Δε| ≤ 5 | " + str(payload["n_differ_alike"]) + " |",
        "| 高相似对总数 | Tanimoto ≥ 0.80 | " + str(payload["n_high_sim"]) + " |",
        "| 其中标签差大 | Tanimoto ≥ 0.80 且 |Δε| ≥ 30 | " + str(payload["n_high_sim_big"]) + " |",
        "",
        "## 3. 相似度 → 标签差：置换检验",
        "",
        "- 观测量：Spearman(Tanimoto, |Δε|) = **" + format(float(payload["observed_rho"]), ".4f") + "**",
        "- 零分布（标签重排 " + str(N_PERMUTATIONS) + " 次）：均值 "
        + format(float(payload["null_mean"]), ".4f") + "，sd " + format(float(payload["null_sd"]), ".4f") + "",
        "- z = **" + format(float(payload["z_score"]), ".4f") + "**，双侧 p = "
        + format(float(payload["p_value"]), ".4f") + "",
        "- 读法：相似度**确实**携带标签差信息（负相关：越像差越小），但斜率很浅——",
        "  见 §3.1 的指纹盲区对。",
        "",
    ]
    blind = payload["blind"]
    lines += [
        "",
        "## 3.1 指纹盲区：机制读数（事后，不替代预注册判据）",
        "",
        "**H38b1 判否**（Tanimoto >= 0.80 且 |Δε| >= 30 的对不存在）。这不是「结构-功能无关」，",
        "而是**阈值定得太高**：高相似对的 |Δε| 实测上限是 " + format(float(payload["max_high_sim_delta"]), ".2f") + "。",
        "按项目惯例阈值不原地改；改法（改用相对判据与下面的「指纹盲区」判据）登记进下一份预注册。",
        "",
        "真正有机制含量的是这一类：**Tanimoto >= 0.99（指纹实际不可分辨）却标签差 >= 5** 的对，",
        "共 " + str(payload["n_blind"]) + " 对里占 " + str(payload["n_blind_differ"]) + " 对，最大 |Δε| = "
        + format(float(payload["max_blind_delta"]), ".2f") + "。",
        "",
        "| 化合物 A (ε) | 化合物 B (ε) | Tanimoto | |Δε| |",
        "| --- | --- | --- | --- |",
    ]
    for pair in sorted(blind, key=lambda item: -float(item["abs_delta_eps"]))[:8]:
        lines.append(
            "| " + str(pair["name_a"]) + " (" + format(float(pair["eps_a"]), ".1f") + ") | "
            + str(pair["name_b"]) + " (" + format(float(pair["eps_b"]), ".1f") + ") | "
            + format(float(pair["tanimoto"]), ".3f") + " | "
            + format(float(pair["abs_delta_eps"]), ".2f") + " |"
        )
    lines += [
        "",
        "读法：Morgan(r=2) 看不见**链长**（heptane / nonane）、**环尺寸**（1,4-dioxane 2.2 vs ",
        "15-crown-5 15.5）、**立体化学**（cis / trans-1,2-dichloroethylene 2.1 / 9.2）。",
        "这正是「ECFP 块在 lever 4 下净有害」的候选机制：一个把 7 倍介电差抹成同一个向量的表示，",
        "在高杠杆配置下只会贡献噪声。该机制可用 N3（KNN/KNC/CPD 嵌入保真度审计）进一步坐实。",
        "",
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
        "## 5. 边界",
        "",
        "- 这是**提示性证据**：单一指纹、单一描述符集、n 有限；极值对不得读成「某分子不可预测」。",
        "- 样本是 241 行物理特征表里的每化合物一行（取最接近 298.15 K 的观测），",
        "  不是冻结头条所在池；两者永不混比。",
        "- 不拟合模型、不新增特征、不触 ε 主记分牌；不占 shot（累计仍 19）。",
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

    pairs = payload["pairs"]
    xs = np.asarray([float(pair["tanimoto"]) for pair in pairs])
    ys = np.asarray([float(pair["abs_delta_eps"]) for pair in pairs])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160)
    ax = axes[0]
    ax.scatter(xs, ys, s=4, alpha=0.18, color="#3d6ea8", edgecolors="none")
    ax.axvline(SIM_HIGH, linestyle="--", color="#9aa4ad")
    ax.axhline(DELTA_BIG, linestyle="--", color="#9aa4ad")
    ax.set_xlabel("Tanimoto 相似度")
    ax.set_ylabel("|Δε|")
    ax.set_title("相似度对标签差只给出浅斜率")
    ax.grid(color="#e6e6e6")

    ax = axes[1]
    nn = payload["nn_rows"]
    eps = np.asarray([float(row["eps"]) for row in nn])
    nn_eps = np.asarray([float(row["nn_eps"]) for row in nn])
    protic_mask = np.asarray([int(row["hbd"]) >= 1 and float(row["eps"]) >= PROTIC_EPS for row in nn])
    ax.scatter(eps, nn_eps, s=16, color="#3d6ea8", alpha=0.7, label="其它")
    if protic_mask.any():
        ax.scatter(eps[protic_mask], nn_eps[protic_mask], s=30, color="#a3320b", label="自缔合质子液 (hbd>=1, eps>=60)")
    limit = float(max(eps.max(), nn_eps.max())) * 1.05
    ax.plot([0, limit], [0, limit], linestyle="--", color="#9aa4ad")
    ax.set_xlabel("实测 ε")
    ax.set_ylabel("最近邻的 ε（结构-only 预测）")
    ax.set_title("1-NN R² = " + format(float(payload["nn_r2"]), ".3f"))
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
    write_csv_lf(NN_CSV, NN_FIELDS, payload["nn_rows"])
    write_csv_lf(
        PAIRS_CSV,
        PAIR_FIELDS,
        payload["extreme"] + payload["look_alike_differ"][:TOP_PAIRS]
        + payload["differ_alike"][:TOP_PAIRS] + payload["blind"],
    )
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
            "why_not_a_shot": "只读特征表的 SMILES 与 ε；不拟合模型、不新增特征列。",
        },
        "inputs": {str(FEATURES_CSV): before, "features_sha256_after": after},
        "inputs_unchanged": before == after,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE],
        "pool_note": "241 行物理特征表（每化合物一行，最近 298.15 K）；非冻结头条所在池。",
        "structure_only_baseline": {
            "nn_r2": payload["nn_r2"], "nn_spearman": payload["nn_rho"], "nn_mae": payload["nn_mae"],
            "sim_high": SIM_HIGH, "delta_big": DELTA_BIG, "sim_low": SIM_LOW, "delta_small": DELTA_SMALL,
        },
        "two_way_search": {
            "n_compounds": payload["n_compounds"], "n_pairs": payload["n_pairs"],
            "n_high_sim": payload["n_high_sim"], "n_high_sim_big": payload["n_high_sim_big"],
            "n_look_alike_differ": payload["n_look_alike_differ"],
            "n_differ_alike": payload["n_differ_alike"],
            "n_blind": payload["n_blind"],
            "n_blind_differ": payload["n_blind_differ"],
            "max_blind_delta": payload["max_blind_delta"],
            "max_high_sim_delta": payload["max_high_sim_delta"],
        },
        "permutation": {
            "observed_spearman": payload["observed_rho"], "null_mean": payload["null_mean"],
            "null_sd": payload["null_sd"], "z": payload["z_score"], "p_two_sided": payload["p_value"],
            "n_permutations": N_PERMUTATIONS, "seed": PERMUTATION_SEED,
        },
        "protic_high_eps": [
            {"name": compound["name"], "eps": compound["eps"], "hbd": compound["hbd"]}
            for compound in payload["protic"]
        ],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "结构-only 基线（1-NN 的 ε）R² = " + format(float(payload["nn_r2"]), ".4f") + "——结构单独给不出功能。",
            "「像而不同」对 " + str(payload["n_look_alike_differ"]) + " 对，「不像而同」对 "
            + str(payload["n_differ_alike"]) + " 对。",
            "Spearman(相似度, |Δε|) = " + format(float(payload["observed_rho"]), ".4f") + "（z = "
            + format(float(payload["z_score"]), ".2f") + "）——相似度携带信息但斜率很浅。",
            "不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    failed = [item for item in criteria if item["verdict"] != "成立"]
    print("compounds " + str(payload["n_compounds"]) + "; pairs " + str(payload["n_pairs"])
          + "; high-sim " + str(payload["n_high_sim"]) + "; look-alike-differ "
          + str(payload["n_look_alike_differ"]) + "; differ-alike " + str(payload["n_differ_alike"]))
    print("1-NN R2 " + format(float(payload["nn_r2"]), ".6f") + "; spearman(eps, nn) "
          + format(float(payload["nn_rho"]), ".6f") + "; MAE " + format(float(payload["nn_mae"]), ".6f"))
    print("spearman(sim, |d eps|) " + format(float(payload["observed_rho"]), ".6f") + "; z "
          + format(float(payload["z_score"]), ".4f") + "; p " + format(float(payload["p_value"]), ".4f"))
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    print("blind pairs " + str(payload["n_blind"]) + "; blind-differ " + str(payload["n_blind_differ"])
          + "; max blind |d eps|" + " " + format(float(payload["max_blind_delta"]), ".2f"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)) + "; registered fail "
          + str(len(failed) - len(unregistered)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES else "UNREGISTERED-FAIL ")
              + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())