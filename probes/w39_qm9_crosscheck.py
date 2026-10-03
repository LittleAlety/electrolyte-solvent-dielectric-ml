# -*- coding: utf-8 -*-
"""W39：QM9 作为第三个轨道/偶极外部层 —— 层级对齐 + 偶极质量审计（后验，不占 shot）。

W38-D 把「哪些来源合法可用」钉死之后，可商用轨道线变成两条半：Batt-P30K（MIT）、
镜像上的 PubChemQC（CC-BY-4.0，但**最小切片 325 GB，不可行**）与 QM9（原始 deposition
DataCite rightsList = CC BY 4.0，**整份只有 28.6 MB，可行**）。本件取 QM9。

QM9 是 133,885 个小分子（C/N/O/F，重原子 <= 9）的 B3LYP/6-31G(2df,p) 计算，带
~~homo~~ / ~~lumo~~ / ~~gap~~ / ~~dipole_moment~~。它对名册的覆盖是 **103 / 241**，
比 Batt-P30K 的 73 / 241 还宽 —— 这是本项目第三个独立的轨道能层。

本件回答三个问题（全部后验，不改任何池 / 特征 / 冻结读数）：

1. **W39-A 层级对齐**：我们的 xTB GFN2 间隙与 QM9 的 B3LYP 间隙是什么关系？
   排序能不能互相代理？量级能不能直接互换？
2. **W39-B 偶极质量审计**：W38-C 登记过一条自我削弱 —— ~~dipole_D~~ 有质量疑点
   （formamide 0.439 D、NMA 1.593 D「与实验值差数倍」）。QM9 给了同分子、不同层级的
   偶极，正好当独立审计员。**关键是把两类差异分开**：刚性分子（可旋转键 = 0）在两个
   来源里必须是同一个构象，任何差异都是**来源本身的错**；柔性分子的差异可能只是
   **QM9 取了 anti 构象**，不一定是我们的错。
3. **W39-C 结论稳健性**：把 W38-C 的 g_rel 统计量在同一个 103 化合物子集上，分别用
   「我们的 μ」与「QM9 的 μ」重算，看给体/非给体之比是否稳。

红线：QM9 是 CC-BY-4.0（可商用），可作**对照层**；但本件**不把 QM9 数值写进任何
标签池或特征列**，不改 METRIC_NAMES，不动四个冻结读数 ⇒ 0 shot（累计仍 19）。

Run:
    .venv/Scripts/python.exe probes/w39_qm9_crosscheck.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np  # noqa: E402
from rdkit import Chem, RDLogger  # noqa: E402
from rdkit.Chem import rdMolDescriptors  # noqa: E402
from scipy.stats import pearsonr, spearmanr  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
QM9_CSV = REPOSITORY_ROOT / "data" / "external" / "qm9_dataset.csv"
OVERLAP_CSV = ARTIFACTS / "w39_qm9_overlap.csv"
SUMMARY_PATH = ARTIFACTS / "w39_qm9_crosscheck_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w39_qm9_crosscheck.md"
FIGURE_PATH = ARTIFACTS / "w39_qm9_alignment.png"

SCHEMA = "w39_qm9_crosscheck/summary@1"
TASK = "week39_qm9_crosscheck"
# H39a7（「构象自由度是差异主因」）在首次运行时判否并照实登记：刚性域的 |Δμ| 中位数
# 0.4442 D 反而**略高于**柔性域的 0.4205 D。阈值不原地改；真正的解释由后验读数给出
# （系统偏置 + 少数极端样本），见报告 §2 末段。
REGISTERED_NEGATIVES: tuple[str, ...] = ("H39a7",)

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

HARTREE_TO_EV = 27.211386245988
QM9_ROWS_EXPECTED = 133885
QM9_SHA256 = "01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053"

HITS_GATE = 80
GAP_SPEARMAN_GATE = 0.70
GAP_RATIO_LOW = 0.50
GAP_RATIO_HIGH = 1.00
DIPOLE_SPEARMAN_GATE = 0.70
RIGID_DELTA_GATE = 1.00
DOMAIN_RATIO_GATE = 1.50

OVERLAP_FIELDS = (
    "inchikey", "name", "smiles", "n_rotatable_bonds", "rigid",
    "xtb_gap_ev", "qm9_gap_ev", "gap_delta_ev",
    "our_dipole_D", "qm9_dipole_D", "dipole_delta_D",
    "dielectric", "hbd", "molar_volume_m3_mol",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (",", '"', "\n")):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def inchikey_from_inchi(inchi: str) -> str | None:
    if not inchi:
        return None
    mol = Chem.MolFromInchi(inchi)
    if mol is None:
        return None
    try:
        return Chem.MolToInchiKey(mol) or None
    except Exception:
        return None


def load_roster() -> dict[str, dict[str, str]]:
    roster: dict[str, dict[str, str]] = {}
    with ROSTER_CSV.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("inchikey") or "").strip()
            if key:
                roster[key] = row
    return roster


def load_qm9(roster: dict[str, dict[str, str]]) -> tuple[int, list[dict[str, object]]]:
    total = 0
    hits: list[dict[str, object]] = []
    with QM9_CSV.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            key = inchikey_from_inchi(row.get("inchi") or "")
            if key is None or key not in roster:
                continue
            entry = roster[key]
            mol = Chem.MolFromSmiles(entry.get("smiles") or "")
            rotors = int(rdMolDescriptors.CalcNumRotatableBonds(mol)) if mol is not None else -1
            xtb_gap = float(entry["homo_lumo_gap_ev"])
            qm9_gap = float(row["gap"]) * HARTREE_TO_EV
            our_mu = float(entry["dipole_D"])
            qm9_mu = float(row["dipole_moment"])
            hits.append({
                "inchikey": key,
                "name": entry.get("name") or "",
                "smiles": entry.get("smiles") or "",
                "n_rotatable_bonds": rotors,
                "rigid": rotors == 0,
                "xtb_gap_ev": xtb_gap,
                "qm9_gap_ev": qm9_gap,
                "gap_delta_ev": qm9_gap - xtb_gap,
                "our_dipole_D": our_mu,
                "qm9_dipole_D": qm9_mu,
                "dipole_delta_D": qm9_mu - our_mu,
                "dielectric": float(entry["dielectric"]),
                "hbd": int(entry["hbd"]),
                "molar_volume_m3_mol": float(entry["molar_volume_m3_mol"]),
            })
    return total, hits


def _domain_ratio(rows: Sequence[Mapping[str, object]], mu_field: str) -> dict[str, object]:
    """W38-C 的 g_rel 中位数比，在同一子集上换 mu 来源重算。"""
    values: list[tuple[int, float]] = []
    for row in rows:
        mu = float(row[mu_field])
        volume = float(row["molar_volume_m3_mol"])
        eps = float(row["dielectric"])
        if mu < 1.0 or volume <= 0.0 or eps <= 1.0:
            continue
        l_value = (eps - 1.0) * (2.0 * eps + 1.0) / (9.0 * eps)
        values.append((int(row["hbd"]), l_value / (mu * mu / volume)))
    donor = [item for hbd, item in values if hbd >= 1]
    acceptor = [item for hbd, item in values if hbd == 0]
    if len(donor) < 3 or len(acceptor) < 3:
        return {"n_donor": len(donor), "n_acceptor": len(acceptor), "ratio": None}
    return {
        "n_donor": len(donor),
        "n_acceptor": len(acceptor),
        "median_donor": statistics.median(donor),
        "median_acceptor": statistics.median(acceptor),
        "ratio": statistics.median(donor) / statistics.median(acceptor),
    }


def build() -> dict[str, object]:
    roster = load_roster()
    total, hits = load_qm9(roster)
    hits_sorted = sorted(hits, key=lambda item: str(item["name"]))

    xtb = np.array([float(item["xtb_gap_ev"]) for item in hits])
    qm9 = np.array([float(item["qm9_gap_ev"]) for item in hits])
    our_mu = np.array([float(item["our_dipole_D"]) for item in hits])
    qm9_mu = np.array([float(item["qm9_dipole_D"]) for item in hits])

    gap_pearson = float(pearsonr(xtb, qm9)[0]) if len(hits) > 2 else None
    gap_spearman = float(spearmanr(xtb, qm9)[0]) if len(hits) > 2 else None
    design = np.vstack([qm9, np.ones_like(qm9)]).T
    slope, intercept = (float(value) for value in np.linalg.lstsq(design, xtb, rcond=None)[0])
    residual = xtb - (slope * qm9 + intercept)
    gap_r2 = float(1.0 - residual.var() / xtb.var()) if xtb.var() > 0 else None

    signed = qm9_mu - our_mu
    agreeing = signed[np.abs(signed) < 1.0]
    dip_pearson = float(pearsonr(our_mu, qm9_mu)[0]) if len(hits) > 2 else None
    dip_spearman = float(spearmanr(our_mu, qm9_mu)[0]) if len(hits) > 2 else None
    abs_dip = np.abs(qm9_mu - our_mu)

    rigid = [item for item in hits if bool(item["rigid"])]
    flex = [item for item in hits if not bool(item["rigid"])]
    rigid_delta = [abs(float(item["qm9_dipole_D"]) - float(item["our_dipole_D"])) for item in rigid]
    flex_delta = [abs(float(item["qm9_dipole_D"]) - float(item["our_dipole_D"])) for item in flex]
    rigid_flagged = sorted(
        (item for item in rigid
         if abs(float(item["qm9_dipole_D"]) - float(item["our_dipole_D"])) >= RIGID_DELTA_GATE),
        key=lambda item: abs(float(item["qm9_dipole_D"]) - float(item["our_dipole_D"])),
        reverse=True,
    )

    ours_domain = _domain_ratio(hits, "our_dipole_D")
    qm9_domain = _domain_ratio(hits, "qm9_dipole_D")

    return {
        "qm9_rows": total,
        "roster_total": len(roster),
        "n_hits": len(hits),
        "rows": hits_sorted,
        "gap": {
            "pearson": gap_pearson,
            "spearman": gap_spearman,
            "median_ratio_xtb_over_qm9": float(np.median(xtb / qm9)),
            "mae_ev": float(np.mean(np.abs(xtb - qm9))),
            "slope": slope,
            "intercept": intercept,
            "r2": gap_r2,
            "residual_sd_ev": float(residual.std(ddof=2)),
            "median_xtb_ev": float(np.median(xtb)),
            "median_qm9_ev": float(np.median(qm9)),
        },
        "dipole": {
            "pearson": dip_pearson,
            "spearman": dip_spearman,
            "mae_D": float(abs_dip.mean()),
            "median_abs_delta_D": float(np.median(abs_dip)),
            "n_abs_delta_ge_1D": int((abs_dip >= 1.0).sum()),
            "n": len(hits),
            "median_signed_delta_D": float(np.median(signed)),
            "n_agreeing": int(agreeing.size),
            "median_signed_delta_agreeing_D": (float(np.median(agreeing))
                                               if agreeing.size else None),
            "min_signed_delta_D": float(signed.min()),
            "max_signed_delta_D": float(signed.max()),
        },
        "rigidity": {
            "n_rigid": len(rigid),
            "n_flexible": len(flex),
            "median_abs_delta_rigid_D": statistics.median(rigid_delta) if rigid_delta else None,
            "median_abs_delta_flexible_D": statistics.median(flex_delta) if flex_delta else None,
            "n_rigid_flagged": len(rigid_flagged),
            "rigid_flagged": [
                {"name": item["name"], "our_dipole_D": item["our_dipole_D"],
                 "qm9_dipole_D": item["qm9_dipole_D"]}
                for item in rigid_flagged
            ],
        },
        "domain_ratio": {
            "our_mu": ours_domain,
            "qm9_mu": qm9_domain,
        },
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    gap = payload["gap"]
    dipole = payload["dipole"]
    rigidity = payload["rigidity"]
    domain = payload["domain_ratio"]
    criteria: list[dict[str, object]] = []

    criteria.append({
        "id": "H39a1",
        "description": "QM9 行数 = 133,885（取到的确是完整 QM9，不是切片）",
        "value": float(payload["qm9_rows"]),
        "threshold": float(QM9_ROWS_EXPECTED),
        "verdict": "成立" if int(payload["qm9_rows"]) == QM9_ROWS_EXPECTED else "判否",
    })

    criteria.append({
        "id": "H39a2",
        "description": "名册命中 >= 80（QM9 限 C/N/O/F 且重原子 <= 9，覆盖仍是三条轨道线里最宽）",
        "value": float(payload["n_hits"]),
        "threshold": float(HITS_GATE),
        "verdict": "成立" if int(payload["n_hits"]) >= HITS_GATE else "判否",
    })

    spearman = gap["spearman"]
    criteria.append({
        "id": "H39a3",
        "description": "xTB 间隙与 B3LYP 间隙的 Spearman >= 0.70（两个层级能互相排序代理）",
        "value": float(spearman) if spearman is not None else None,
        "threshold": GAP_SPEARMAN_GATE,
        "verdict": "成立" if spearman is not None and float(spearman) >= GAP_SPEARMAN_GATE else "判否",
    })

    ratio = float(gap["median_ratio_xtb_over_qm9"])
    criteria.append({
        "id": "H39a4",
        "description": "中位数比 xTB/B3LYP 落在 [0.50, 1.00]（系统性压缩，方向已知）",
        "value": ratio,
        "threshold": GAP_RATIO_LOW,
        "verdict": "成立" if GAP_RATIO_LOW <= ratio <= GAP_RATIO_HIGH else "判否",
    })

    dip_spearman = dipole["spearman"]
    criteria.append({
        "id": "H39a5",
        "description": "偶极的 Spearman >= 0.70（我们的 dipole_D 大体可用）",
        "value": float(dip_spearman) if dip_spearman is not None else None,
        "threshold": DIPOLE_SPEARMAN_GATE,
        "verdict": "成立" if dip_spearman is not None and float(dip_spearman) >= DIPOLE_SPEARMAN_GATE else "判否",
    })

    n_rigid_flagged = int(rigidity["n_rigid_flagged"])
    criteria.append({
        "id": "H39a6",
        "description": "刚性分子（可旋转键 = 0）里仍有 |Δμ| >= 1 D 的样本 ⇒ 错在我们这一列，不是构象",
        "value": float(n_rigid_flagged),
        "threshold": 1.0,
        "verdict": "成立" if n_rigid_flagged >= 1 else "判否",
    })

    rigid_med = rigidity["median_abs_delta_rigid_D"]
    flex_med = rigidity["median_abs_delta_flexible_D"]
    criteria.append({
        "id": "H39a7",
        "description": "刚性域的 |Δμ| 中位数 < 柔性域（构象自由度是差异的主要放大器）",
        "value": float(rigid_med) if rigid_med is not None else None,
        "threshold": float(flex_med) if flex_med is not None else None,
        "verdict": ("成立" if rigid_med is not None and flex_med is not None and rigid_med < flex_med
                    else "判否"),
    })

    ratio_qm9 = domain["qm9_mu"]["ratio"]
    criteria.append({
        "id": "H39a8",
        "description": "换成 QM9 的 μ 重算后，给体/非给体 g_rel 中位数比仍 >= 1.50（W38-C 结论稳健）",
        "value": float(ratio_qm9) if ratio_qm9 is not None else None,
        "threshold": DOMAIN_RATIO_GATE,
        "verdict": "成立" if ratio_qm9 is not None and float(ratio_qm9) >= DOMAIN_RATIO_GATE else "判否",
    })

    ratio_ours = domain["our_mu"]["ratio"]
    criteria.append({
        "id": "H39a9",
        "description": "同一子集上，用我们的 μ 也算出 >= 1.50（两套 μ 给同方向结论）",
        "value": float(ratio_ours) if ratio_ours is not None else None,
        "threshold": DOMAIN_RATIO_GATE,
        "verdict": "成立" if ratio_ours is not None and float(ratio_ours) >= DOMAIN_RATIO_GATE else "判否",
    })

    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  inputs: Mapping[str, object]) -> str:
    gap = payload["gap"]
    dipole = payload["dipole"]
    rigidity = payload["rigidity"]
    domain = payload["domain_ratio"]
    lines: list[str] = []
    lines.append("# W39：QM9 作为第三个轨道/偶极外部层 —— 层级对齐 + 偶极质量审计")
    lines.append("")
    lines.append("- 生成件：probes/w39_qm9_crosscheck.py（可复算；本文件由它写出）")
    lines.append("- 外部层：QM9（Ramakrishnan et al. 2014，B3LYP/6-31G(2df,p)），"
                 + str(payload["qm9_rows"]) + " 行；文件 data/external/qm9_dataset.csv")
    lines.append("- 名册分母：data/processed/dielectric_physical_features_v03.csv，"
                 + str(payload["roster_total"]) + " 行；命中 **" + str(payload["n_hits"]) + "**")
    lines.append("- 记账：后验读数，**不占 shot**（累计仍 19）；不改 METRIC_NAMES、不新增特征列")
    lines.append("")
    lines.append("## 0. 一句话结论")
    lines.append("")
    lines.append("QM9 是本项目覆盖最宽的轨道能外部层（**" + str(payload["n_hits"]) + " / "
                 + str(payload["roster_total"]) + "**，比 Batt-P30K 的 73 还多），"
                 "两个层级的间隙**排序高度一致、量级系统性压缩**；"
                 "而 W38-C 登记的那条偶极质量疑点被独立证实，且能拆成**两种不同成因**。")
    lines.append("")
    lines.append("## 1. W39-A 层级对齐（间隙）")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| Pearson | " + format(float(gap["pearson"]), ".4f") + " |")
    lines.append("| Spearman | " + format(float(gap["spearman"]), ".4f") + " |")
    lines.append("| 中位数比（xTB / B3LYP） | " + format(float(gap["median_ratio_xtb_over_qm9"]), ".4f") + " |")
    lines.append("| MAE | " + format(float(gap["mae_ev"]), ".4f") + " eV |")
    lines.append("| 线性标定 | xTB = " + format(float(gap["slope"]), ".4f") + " * B3LYP "
                 + format(float(gap["intercept"]), ".4f") + " |")
    lines.append("| 标定 R² | " + format(float(gap["r2"]), ".4f") + " |")
    lines.append("| 残差 sd | " + format(float(gap["residual_sd_ev"]), ".4f") + " eV |")
    lines.append("| 中位数（xTB / QM9） | " + format(float(gap["median_xtb_ev"]), ".3f") + " / "
                 + format(float(gap["median_qm9_ev"]), ".3f") + " eV |")
    lines.append("")
    lines.append("## 2. W39-B 偶极质量审计")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| Pearson | " + format(float(dipole["pearson"]), ".4f") + " |")
    lines.append("| Spearman | " + format(float(dipole["spearman"]), ".4f") + " |")
    lines.append("| MAE | " + format(float(dipole["mae_D"]), ".4f") + " D |")
    lines.append("| 中位数 |Δ| | " + format(float(dipole["median_abs_delta_D"]), ".4f") + " D |")
    lines.append("| |Δ| >= 1 D 的样本数 | " + str(dipole["n_abs_delta_ge_1D"])
                 + " / " + str(dipole["n"]) + " |")
    lines.append("| 刚性域 |Δ| 中位数（n = " + str(rigidity["n_rigid"]) + "） | "
                 + (format(float(rigidity["median_abs_delta_rigid_D"]), ".4f")
                    if rigidity["median_abs_delta_rigid_D"] is not None else "n/a") + " D |")
    lines.append("| 柔性域 |Δ| 中位数（n = " + str(rigidity["n_flexible"]) + "） | "
                 + (format(float(rigidity["median_abs_delta_flexible_D"]), ".4f")
                    if rigidity["median_abs_delta_flexible_D"] is not None else "n/a") + " D |")
    lines.append("")
    lines.append("**刚性域被点名的样本**（可旋转键 = 0，两来源必是同一构象 ⇒ 差异只能来自来源本身）：")
    lines.append("")
    lines.append("| 化合物 | 我们的 μ (D) | QM9 的 μ (D) |")
    lines.append("| --- | --- | --- |")
    for item in rigidity["rigid_flagged"]:
        lines.append("| " + str(item["name"]) + " | " + format(float(item["our_dipole_D"]), ".4f")
                     + " | " + format(float(item["qm9_dipole_D"]), ".4f") + " |")
    lines.append("")
    lines.append("**后验读数（不占判据，专为此前的 H39a7 判否而加）**：把两类差异拆开看 ——")
    lines.append("")
    lines.append("- **一个几乎与分子无关的系统偏置**：在 |Δ| < 1 D 的 "
                 + str(dipole["n_agreeing"]) + " 个化合物上，签署差（QM9 − 我们）的中位数是 "
                 + format(float(dipole["median_signed_delta_agreeing_D"]), ".4f")
                 + " D ⇒ 我们的列**系统性偏高**约 0.4 D。")
    lines.append("- **少数样本的巨大偏差**（两端都有）：签署差全域极值 "
                 + format(float(dipole["min_signed_delta_D"]), ".3f") + " 到 "
                 + format(float(dipole["max_signed_delta_D"]), ".3f") + " D。")
    lines.append("- **机制结论要改写**：H39a7 判否说明差异**不是**主要由构象自由度驱动"
                 "（刚性 0.4442 D vs 柔性 0.4205 D，几乎一样）。真正的主项是上面的系统偏置；"
                 "构象只解释其中一部分极端样本（二醇类的 QM9 anti 构象）。")
    lines.append("")
    lines.append("## 3. W39-C 结论稳健性（同一个子集换 μ 来源）")
    lines.append("")
    lines.append("| μ 来源 | n(给体) | n(非给体) | g_rel 中位数比 |")
    lines.append("| --- | --- | --- | --- |")
    for label, key in (("我们的 μ", "our_mu"), ("QM9 的 μ", "qm9_mu")):
        block = domain[key]
        value = block["ratio"]
        lines.append("| " + label + " | " + str(block["n_donor"]) + " | " + str(block["n_acceptor"])
                     + " | " + (format(float(value), ".4f") if value is not None else "n/a") + " |")
    lines.append("")
    lines.append("## 4. 判据")
    lines.append("")
    lines.append("| id | 判据 | 读数 | 门槛 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in criteria:
        lines.append("| " + str(item["id"]) + " | " + str(item["description"])
                     + " | " + str(item["value"]) + " | " + str(item["threshold"])
                     + " | " + str(item["verdict"]) + " |")
    lines.append("")
    lines.append("## 5. 边界")
    lines.append("")
    lines.append("- QM9 是 **CC-BY-4.0 对照层**：可作参考与审计，但本件**不把它的数值写进任何标签池或特征列**。")
    lines.append("- QM9 的间隙是 **B3LYP/6-31G(2df,p) 气相轨道能差**；我们的列是 **xTB GFN2 单点**。"
                 "两者都是「轨道间隙」，但层级不同 ⇒ **只能谈排序与标定，不能直接互换**。")
    lines.append("- gap 与 homo/lumo 同源自洽（gap = lumo - homo），本件只用 gap。")
    lines.append("- 偶极比对里 **QM9 的构象不保证是全局最小**（柔性分子差距可能是它的问题）；"
                 "刚性子集才是能定责的那一半。")
    lines.append("- 本件的域比只作 **W38-C 的稳健性检查**，不重开 W38-C、不改它的读数。")
    lines.append("")
    lines.append("## 6. 输入指纹")
    lines.append("")
    for key, value in inputs.items():
        lines.append("- " + str(key) + " = " + str(value))
    lines.append("")
    return "\n".join(lines)


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "Arial Unicode MS"):
        try:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    rows = list(payload["rows"])
    qm9_gap = np.array([float(item["qm9_gap_ev"]) for item in rows])
    xtb_gap = np.array([float(item["xtb_gap_ev"]) for item in rows])
    qm9_mu = np.array([float(item["qm9_dipole_D"]) for item in rows])
    our_mu = np.array([float(item["our_dipole_D"]) for item in rows])
    rigid = np.array([bool(item["rigid"]) for item in rows])
    gap = payload["gap"]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=160)

    axis = axes[0]
    axis.scatter(qm9_gap, xtb_gap, s=16, c="#2f6f9f", alpha=0.75, edgecolors="none")
    grid = np.linspace(float(qm9_gap.min()), float(qm9_gap.max()), 50)
    axis.plot(grid, float(gap["slope"]) * grid + float(gap["intercept"]), color="#b03a2e",
              linewidth=1.6,
              label="标定：xTB = " + format(float(gap["slope"]), ".3f") + "*B3LYP "
                    + format(float(gap["intercept"]), ".2f"))
    axis.plot(grid, grid, color="#666666", linestyle="--", linewidth=1.0, label="y = x")
    axis.set_xlabel("QM9 B3LYP 间隙 (eV)", fontsize=9)
    axis.set_ylabel("本地 xTB GFN2 间隙 (eV)", fontsize=9)
    axis.set_title("W39-A 轨道间隙层级对齐（n = " + str(len(rows)) + "，Spearman "
                   + format(float(gap["spearman"]), ".3f") + "）", fontsize=10)
    axis.legend(fontsize=7.5, loc="upper left")

    axis = axes[1]
    axis.scatter(qm9_mu[rigid], our_mu[rigid], s=18, c="#2f7d4f", alpha=0.85,
                 edgecolors="none", label="刚性（可旋转键 = 0，n = " + str(int(rigid.sum())) + "）")
    axis.scatter(qm9_mu[~rigid], our_mu[~rigid], s=18, c="#b03a2e", alpha=0.75,
                 edgecolors="none", label="柔性（n = " + str(int((~rigid).sum())) + "）")
    span = np.linspace(0.0, max(float(qm9_mu.max()), float(our_mu.max())) * 1.05, 50)
    axis.plot(span, span, color="#666666", linestyle="--", linewidth=1.0, label="y = x")
    for item in payload["rigidity"]["rigid_flagged"]:
        axis.annotate(str(item["name"]),
                      (float(item["qm9_dipole_D"]), float(item["our_dipole_D"])),
                      fontsize=6.5, xytext=(3, 3), textcoords="offset points", color="#1b4f72")
    axis.set_xlabel("QM9 偶极 (D)", fontsize=9)
    axis.set_ylabel("本地 dipole_D (D)", fontsize=9)
    axis.set_title("W39-B 偶极审计（Spearman " + format(float(payload["dipole"]["spearman"]), ".3f")
                   + "）", fontsize=10)
    axis.legend(fontsize=7.5, loc="upper left")

    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    before_roster = sha256_file(ROSTER_CSV)
    before_qm9 = sha256_file(QM9_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(OVERLAP_CSV, OVERLAP_FIELDS, payload["rows"])
    after_roster = sha256_file(ROSTER_CSV)
    after_qm9 = sha256_file(QM9_CSV)
    if not args.skip_figure:
        make_figure(payload)

    inputs = {
        str(ROSTER_CSV): before_roster,
        "roster_sha256_after": after_roster,
        str(QM9_CSV): before_qm9,
        "qm9_sha256_after": after_qm9,
        "qm9_expected_sha256": QM9_SHA256,
    }
    inputs_unchanged = before_roster == after_roster and before_qm9 == after_qm9
    criteria.append({
        "id": "H39a10",
        "description": "输入未被改写（名册与 QM9 的 sha256 前后一致）且 QM9 文件与登记指纹相符",
        "value": 1.0 if inputs_unchanged else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if inputs_unchanged and before_qm9 == QM9_SHA256 else "判否",
    })

    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    gap = payload["gap"]
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读盘上既有的名册与 QM9 对照层；不拟合主记分牌臂、"
                              "不新增特征列、不改 METRIC_NAMES、不动四个冻结读数。",
        },
        "inputs": inputs,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "external_layer": {
            "name": "QM9",
            "file": "data/external/qm9_dataset.csv",
            "sha256": QM9_SHA256,
            "rows": int(payload["qm9_rows"]),
            "level_of_theory": "B3LYP/6-31G(2df,p)",
            "license": "CC BY 4.0（原始 deposition 10.6084/m9.figshare.978904，DataCite rightsList）",
            "mirror": "hf-mirror.com/datasets/n0w0f/qm9-csv（镜像卡片未声明许可，"
                      "以原始 deposition 为准，署名按 Ramakrishnan et al. 2014）",
            "columns_used": ["inchi", "gap", "dipole_moment"],
            "not_used_as": "不作为标签或特征写入任何池；只作对照与审计",
        },
        "roster_total": int(payload["roster_total"]),
        "n_hits": int(payload["n_hits"]),
        "alignment": payload["gap"],
        "dipole_audit": payload["dipole"],
        "rigidity_split": payload["rigidity"],
        "domain_ratio": payload["domain_ratio"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "QM9 覆盖 " + str(payload["n_hits"]) + " / " + str(payload["roster_total"])
            + " —— 三条轨道线里最宽的一条（Batt-P30K 73、Batt-SLM.smi 79）。",
            "间隙排序高度一致（Spearman " + format(float(gap["spearman"]), ".4f")
            + "），但量级系统性压缩（中位数比 "
            + format(float(gap["median_ratio_xtb_over_qm9"]), ".4f") + "）"
            + " ⇒ 与「排序学会了、量级学不会」同构。",
            "偶极审计证实 W38-C 的质量疑点，但「构象自由度是主因」这条判否（H39a7：刚性 0.444 D vs 柔性 0.420 D）；"
            + format(float(payload["rigidity"]["median_abs_delta_rigid_D"]), ".3f")
            + " D vs 柔性域 "
            + format(float(payload["rigidity"]["median_abs_delta_flexible_D"]), ".3f") + " D。",
            "不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria, inputs), encoding="utf-8", newline="\n")

    print("qm9 rows " + str(payload["qm9_rows"]) + "; hits " + str(payload["n_hits"])
          + "/" + str(payload["roster_total"]))
    print("gap spearman " + format(float(gap["spearman"]), ".6f")
          + "; pearson " + format(float(gap["pearson"]), ".6f")
          + "; median ratio " + format(float(gap["median_ratio_xtb_over_qm9"]), ".6f")
          + "; mae " + format(float(gap["mae_ev"]), ".6f"))
    print("dipole spearman " + format(float(payload["dipole"]["spearman"]), ".6f")
          + "; mae " + format(float(payload["dipole"]["mae_D"]), ".6f")
          + "; n|d|>=1 " + str(payload["dipole"]["n_abs_delta_ge_1D"]))
    print("rigid median |d| " + format(float(payload["rigidity"]["median_abs_delta_rigid_D"]), ".6f")
          + " (n=" + str(payload["rigidity"]["n_rigid"]) + "); flexible "
          + format(float(payload["rigidity"]["median_abs_delta_flexible_D"]), ".6f")
          + " (n=" + str(payload["rigidity"]["n_flexible"]) + ")")
    ours = payload["domain_ratio"]["our_mu"]["ratio"]
    qm9r = payload["domain_ratio"]["qm9_mu"]["ratio"]
    print("domain ratio ours " + (format(float(ours), ".6f") if ours is not None else "n/a")
          + "; qm9 " + (format(float(qm9r), ".6f") if qm9r is not None else "n/a"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
