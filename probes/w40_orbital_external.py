# -*- coding: utf-8 -*-
"""W40-D：QM9 接入轨道通道外部对照层 + PubChemQC 单文件子集可行性评估（后验，0 shot）。

W39 已经把 QM9 定成第三条轨道能外部层（覆盖 103 / 241），并给出层级标定
（xTB = 2.026697 * B3LYP - 8.872895）。本件把那条读数从一次性审计**升级为常驻的
轨道通道外部对照层**，并把 W38 留下的第二个问题（PubChemQC 能不能按名册取单文件
子集）做成完性的可行性评估与照实登记。

口径（必须先声明，且写进交付表）：
  1. QM9 是 B3LYP/6-31G(2df,p) **气相**轨道能差；我们的 homo_lumo_gap_ev 是 xTB
     GFN2 **单点**。两者都是「轨道间隙」，但**层级不同** ⇒ 本件只谈**排序**
     （Spearman / Kendall）与**标定**（线性映射），**不得直接互换**。
  2. QM9 数值**不得写入任何标签池 / 特征列 / 交付标签**（红线，见 H40d10）。
     QM9 许可 = CC BY 4.0（原始 deposition 10.6084/m9.figshare.978904）。
  3. W39 已判决的结论（尤其「刚性 vs 柔性构象」那条判否）本件**只作引用**，
     不重复声明为新发现。

记账：0 shot（累计仍 19）；不拟合主记分牌臂、不改 METRIC_NAMES、不动四个冻结读数。

Run:
    .venv/Scripts/python.exe probes/w40_orbital_external.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np  # noqa: E402
from probes.export_results_common import write_json_stable  # noqa: E402
from rdkit import Chem, RDLogger  # noqa: E402
from scipy.stats import kendalltau, pearsonr, spearmanr  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
QM9_CSV = REPOSITORY_ROOT / "data" / "external" / "qm9_dataset.csv"
CONTROL_CSV = ARTIFACTS / "w40_orbital_external_control.csv"
CHANNELS_IN = ARTIFACTS / "w38_recon_channels.csv"
CHANNELS_OUT = ARTIFACTS / "w40_orbital_channels_update.csv"
SUMMARY_PATH = ARTIFACTS / "w40_orbital_external_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w40_orbital_external.md"
FIGURE_PATH = ARTIFACTS / "w40_orbital_external.png"

SCHEMA = "w40_orbital_external/summary@1"
TASK = "week40_orbital_external"

# H40d8（「PubChemQC 名册级单文件子集本机可行」）在首次运行时判否并照实登记：
# 最小单文件其实**不到 1 GB**（536,126,834 B），所以阻塞不在「单片体量」，
# 而在**可定位性**：数据集没有 CID / InChIKey 索引、没有 parquet 分支，分片按 CID
# 区间切分，而本机 PubChem PUG REST 不可达 ⇒ 连「该下哪一片」都判定不了。
# 阈值不原地改；机制解释见报告 §5。
REGISTERED_NEGATIVES: tuple[str, ...] = ("H40d8",)

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

HARTREE_TO_EV = 27.211386245988
QM9_ROWS_EXPECTED = 133885
QM9_SHA256 = "01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053"
ROSTER_SHA256 = "b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3"
ROSTER_TOTAL_EXPECTED = 241

# W39 冻结的层级标定（本件必须逐位复现，否则口径不可比）。
W39_SLOPE = 2.0266971543817958
W39_INTERCEPT = -8.872894552951406
W39_SPEARMAN = 0.8856281475401158
CALIB_TOLERANCE = 1e-9

# 阈值首次冻结（H40d1..H40d6），依据写在报告 §4 表下：
HITS_GATE = 100          # 对齐 W39 的 103（只把「够宽」量化，不追高）
SPEARMAN_GATE = 0.70     # 沿用 W39 判据的同一门，保持口径连续
KENDALL_GATE = 0.50      # Spearman 0.70 在双变量正态下的对应 tau 约 0.5
RAW_MEDIAN_DELTA_GATE = 1.0   # 未标定 |delta| 中位数必须 >= 1 eV（不可直接互换）
CALIB_REDUCTION_GATE = 1.0 / 3.0   # 标定至少消去三分之一的层级差，否则标定无意义
OUTLIER_MIN_COUNT = 1    # |delta| >= 1 eV 的离群必须有清单（>= 1 条）

# ---------------------------------------------------------------------------
# PubChemQC 单文件子集侦察（只读 HTTP，2026-10-03，hf-mirror.com dataset tree API）。
# 端点模板：
#   https://hf-mirror.com/api/datasets/{dataset}/tree/main/data/{config}/train
# 每个分片文件名就是一个**闭区间 CID 范围**（形如 121433757-121494125.json），
# 没有 InChIKey / CID 索引文件；refs/convert/parquet 分支不存在（Invalid rev id）。
# 下面记的是各 config 的 train 目录统计（bytes 为 LFS 实文件大小）。
# ---------------------------------------------------------------------------
PUBCHEMQC_CENSUS = (
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6",
     "n_files": 430, "min_shard_bytes": 3451907673, "max_shard_bytes": 9905178633,
     "total_bytes": 2244891376968, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6_chnopsfcl300nosalt",
     "n_files": 149, "min_shard_bytes": 3329101674, "max_shard_bytes": 4279899464,
     "total_bytes": 585419076926, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6_chnopsfcl500nosalt",
     "n_files": 339, "min_shard_bytes": 3166530000, "max_shard_bytes": 6182779852,
     "total_bytes": 1658006696822, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6_chnopsfclnakmgca500",
     "n_files": 347, "min_shard_bytes": 2113728631, "max_shard_bytes": 6197949096,
     "total_bytes": 1696785969280, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6_chon300nosalt",
     "n_files": 87, "min_shard_bytes": 2184575419, "max_shard_bytes": 4371881945,
     "total_bytes": 349293321756, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-b3lyp", "config": "b3lyp_pm6_chon500nosalt",
     "n_files": 232, "min_shard_bytes": 536126834, "max_shard_bytes": 6280942234,
     "total_bytes": 1135035374141, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-pm6", "config": "pm6opt",
     "n_files": 1000, "min_shard_bytes": 2482690433, "max_shard_bytes": 7031196000,
     "total_bytes": 3873347155187, "truncated": True},
    {"dataset": "molssiai-hub/pubchemqc-pm6", "config": "pm6opt_chon300nosalt",
     "n_files": 87, "min_shard_bytes": 1498874351, "max_shard_bytes": 3011860000,
     "total_bytes": 238937813600, "truncated": False},
    {"dataset": "molssiai-hub/pubchemqc-pm6", "config": "pm6opt_chon500nosalt",
     "n_files": 156, "min_shard_bytes": 2423347276, "max_shard_bytes": 4158000000,
     "total_bytes": 510618083373, "truncated": False},
)

# 全局最小分片的身份（b3lyp chon500nosalt 的尾片）。
MIN_SHARD = {
    "path": "data/b3lyp_pm6_chon500nosalt/train/121433757-121494125.json",
    "bytes": 536126834,
    "cid_lo": 121433757,
    "cid_hi": 121494125,
    "n_cids_nominal": 121494125 - 121433757 + 1,
}

PUBCHEMQC_BLOCKED_REASONS = (
    "无 CID / InChIKey 索引：分片文件名只是闭区间 CID 范围，没有「按 InChIKey 定位分片」的索引文件。",
    "无 parquet 分支：refs/convert/parquet 返回 Invalid rev id（该数据集 viewer: false，未自动转换）。",
    "本机 PubChem PUG REST 不可达（pubchem.ncbi.nlm.nih.gov 挂起超时）⇒ 无法把名册 241 条 InChIKey 解析成 CID。",
    "名册化合物（常见溶剂）CID 分散在 1-1.2 亿区间 ⇒ 即使拿到全部 CID，覆盖也必须跨多个 0.5-6 GB 分片。",
)

CONTROL_FIELDS = (
    "inchikey", "name", "xTB_gap_ev", "qm9_homo_ha", "qm9_lumo_ha", "qm9_gap_ev",
    "qm9_gap_ev_calibrated", "delta_gap_ev", "abs_delta_gap_ev", "residual_gap_ev",
    "qm9_homo_ev", "qm9_lumo_ev", "qm9_gap_minus_lumo_homo_ev",
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


def load_qm9_orbital(roster: Mapping[str, Mapping[str, str]]) -> tuple[int, list[dict[str, object]]]:
    """把 QM9 的 homo / lumo / gap（Hartree）按 InChIKey 连到名册上。

    QM9 的 homo / lumo 单位是 **Hartree**（1 Ha = 27.211386245988 eV）；gap 同为
    Hartree 且恒等于 lumo - homo（本件把这条自洽性也写进对照表做守卫）。
    """

    total = 0
    rows: list[dict[str, object]] = []
    with QM9_CSV.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for item in csv.DictReader(handle):
            total += 1
            key = inchikey_from_inchi(item.get("inchi") or "")
            if key is None or key not in roster:
                continue
            entry = roster[key]
            homo_ha = float(item["homo"])
            lumo_ha = float(item["lumo"])
            gap_ha = float(item["gap"])
            rows.append({
                "inchikey": key,
                "name": entry.get("name") or "",
                "smiles": entry.get("smiles") or "",
                "xTB_gap_ev": float(entry["homo_lumo_gap_ev"]),
                "qm9_homo_ha": homo_ha,
                "qm9_lumo_ha": lumo_ha,
                "qm9_gap_ev": gap_ha * HARTREE_TO_EV,
                "qm9_homo_ev": homo_ha * HARTREE_TO_EV,
                "qm9_lumo_ev": lumo_ha * HARTREE_TO_EV,
                "qm9_gap_minus_lumo_homo_ev": (gap_ha - (lumo_ha - homo_ha)) * HARTREE_TO_EV,
            })
    return total, rows


def _loo_calibrated_residual(qm9: np.ndarray, xtb: np.ndarray) -> np.ndarray:
    """留一标定残差：每次用其余 n-1 点拟合，再预测被留出那点。"""

    residual = np.empty_like(xtb)
    for index in range(xtb.size):
        mask = np.ones(xtb.size, dtype=bool)
        mask[index] = False
        design = np.vstack([qm9[mask], np.ones(int(mask.sum()))]).T
        slope, intercept = np.linalg.lstsq(design, xtb[mask], rcond=None)[0]
        residual[index] = xtb[index] - (float(slope) * qm9[index] + float(intercept))
    return residual


def build() -> dict[str, object]:
    roster = load_roster()
    total, rows = load_qm9_orbital(roster)
    rows.sort(key=lambda item: str(item["name"]))

    xtb = np.array([float(item["xTB_gap_ev"]) for item in rows])
    qm9 = np.array([float(item["qm9_gap_ev"]) for item in rows])

    design = np.vstack([qm9, np.ones_like(qm9)]).T
    slope, intercept = (float(value) for value in np.linalg.lstsq(design, xtb, rcond=None)[0])
    calibrated = slope * qm9 + intercept
    residual = xtb - calibrated
    loo_residual = _loo_calibrated_residual(qm9, xtb)

    raw_abs = np.abs(qm9 - xtb)
    delta = qm9 - xtb
    for item, cal, res, loo in zip(rows, calibrated, residual, loo_residual):
        item["qm9_gap_ev_calibrated"] = float(cal)
        item["delta_gap_ev"] = float(item["qm9_gap_ev"]) - float(item["xTB_gap_ev"])
        item["abs_delta_gap_ev"] = abs(float(item["delta_gap_ev"]))
        item["residual_gap_ev"] = float(res)
        item["loo_residual_gap_ev"] = float(loo)

    raw_mae = float(raw_abs.mean())
    in_sample_mae = float(np.abs(residual).mean())
    loo_mae = float(np.abs(loo_residual).mean())
    outliers = sorted((item for item in rows if float(item["abs_delta_gap_ev"]) >= 1.0),
                      key=lambda item: float(item["abs_delta_gap_ev"]), reverse=True)

    metrics = {
        "xtb_gap_ev": {
            "spearman": float(spearmanr(xtb, qm9)[0]),
            "kendall": float(kendalltau(xtb, qm9)[0]),
            "pearson": float(pearsonr(xtb, qm9)[0]),
            "median_ratio_xtb_over_qm9": float(np.median(xtb / qm9)),
        },
        "delta": {
            "raw_mae_ev": raw_mae,
            "median_abs_delta_ev": float(np.median(raw_abs)),
            "n_abs_delta_ge_1ev": len(outliers),
            "frac_abs_delta_ge_1ev": float(len(outliers) / max(len(rows), 1)),
        },
        "calibration": {
            "slope": slope,
            "intercept": intercept,
            "in_sample_mae_ev": in_sample_mae,
            "in_sample_reduction": float(1.0 - in_sample_mae / raw_mae),
            "loo_mae_ev": loo_mae,
            "loo_reduction": float(1.0 - loo_mae / raw_mae),
            "matches_w39": (abs(slope - W39_SLOPE) <= CALIB_TOLERANCE
                            and abs(intercept - W39_INTERCEPT) <= CALIB_TOLERANCE),
            "w39_slope": W39_SLOPE,
            "w39_intercept": W39_INTERCEPT,
        },
        "qm9_self_consistency_max_abs_ev": float(
            max(abs(float(item["qm9_gap_minus_lumo_homo_ev"])) for item in rows)) if rows else None,
    }

    min_shard = min(PUBCHEMQC_CENSUS, key=lambda item: int(item["min_shard_bytes"]))
    pubchemqc = {
        "evaluated": True,
        "roster_level_download_feasible": False,
        "min_shard_bytes": int(min_shard["min_shard_bytes"]),
        "min_shard_path": MIN_SHARD["path"],
        "min_shard_cid_range": [MIN_SHARD["cid_lo"], MIN_SHARD["cid_hi"]],
        "min_shard_under_1gib": int(MIN_SHARD["bytes"]) < (1 << 30),
        "census": [dict(item) for item in PUBCHEMQC_CENSUS],
        "blocked_reasons": list(PUBCHEMQC_BLOCKED_REASONS),
        "minimal_viable_alternative":
            "在能访问 PubChem 的机器上先做 InChIKey -> CID 解析（只读、便宜），"
            "再按 CID 落在哪个分片决定下载；对 1-3 个化合物的实证校验成本约 "
            "0.5-6 GB/片。本机（PubChem 不可达）不可行。",
    }

    return {
        "qm9_rows": total,
        "roster_total": len(roster),
        "n_hits": len(rows),
        "rows": rows,
        "metrics": metrics,
        "outliers": outliers,
        "pubchemqc": pubchemqc,
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    metrics = payload["metrics"]
    ordering = metrics["xtb_gap_ev"]
    delta = metrics["delta"]
    calibration = metrics["calibration"]
    pubchemqc = payload["pubchemqc"]
    criteria: list[dict[str, object]] = []

    criteria.append({
        "id": "H40d1",
        "description": "名册命中 >= 100（轨道通道外部对照层的宽度，对齐 W39 的 103）",
        "value": float(payload["n_hits"]),
        "threshold": float(HITS_GATE),
        "verdict": "成立" if int(payload["n_hits"]) >= HITS_GATE else "判否",
    })

    spearman = float(ordering["spearman"])
    criteria.append({
        "id": "H40d2",
        "description": "xTB 间隙与 QM9 间隙的 Spearman >= 0.70（排序可互相代理）",
        "value": spearman,
        "threshold": SPEARMAN_GATE,
        "verdict": "成立" if spearman >= SPEARMAN_GATE else "判否",
    })

    kendall = float(ordering["kendall"])
    criteria.append({
        "id": "H40d3",
        "description": "同一对齐的 Kendall tau >= 0.50（对并列与秩更稳健的第二口径）",
        "value": kendall,
        "threshold": KENDALL_GATE,
        "verdict": "成立" if kendall >= KENDALL_GATE else "判否",
    })

    median_abs = float(delta["median_abs_delta_ev"])
    criteria.append({
        "id": "H40d4",
        "description": "未标定 |delta| 中位数 >= 1.0 eV（两个层级不能直接互换的定量证据）",
        "value": median_abs,
        "threshold": RAW_MEDIAN_DELTA_GATE,
        "verdict": "成立" if median_abs >= RAW_MEDIAN_DELTA_GATE else "判否",
    })

    loo_reduction = float(calibration["loo_reduction"])
    criteria.append({
        "id": "H40d5",
        "description": "留一标定后 MAE 下降比例 >= 1/3（标定必须是一阶有效修正，而非装饰）",
        "value": loo_reduction,
        "threshold": CALIB_REDUCTION_GATE,
        "verdict": "成立" if loo_reduction >= CALIB_REDUCTION_GATE else "判否",
    })

    n_outliers = int(delta["n_abs_delta_ge_1ev"])
    criteria.append({
        "id": "H40d6",
        "description": "|delta| >= 1 eV 的离群条数 >= 1 且已登记清单（对照层不得被当成标签）",
        "value": float(n_outliers),
        "threshold": float(OUTLIER_MIN_COUNT),
        "verdict": "成立" if n_outliers >= OUTLIER_MIN_COUNT else "判否",
    })

    criteria.append({
        "id": "H40d7",
        "description": "PubChemQC 单文件子集可行性评估完成且结论已登记（census + 受阻原因 + 替代）",
        "value": 1.0 if pubchemqc["evaluated"] else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if pubchemqc["evaluated"] else "判否",
    })

    criteria.append({
        "id": "H40d8",
        "description": "PubChemQC 存在「按名册命中定位的单文件子集」本机可行下载路径（判否：登记为受阻）",
        "value": 1.0 if pubchemqc["roster_level_download_feasible"] else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if pubchemqc["roster_level_download_feasible"] else "判否",
    })

    criteria.append({
        "id": "H40d9",
        "description": "本件重算的层级标定与 W39 冻结值逐位一致（口径可复现）",
        "value": 1.0 if calibration["matches_w39"] else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if calibration["matches_w39"] else "判否",
    })

    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  inputs: Mapping[str, object]) -> str:
    metrics = payload["metrics"]
    ordering = metrics["xtb_gap_ev"]
    delta = metrics["delta"]
    calibration = metrics["calibration"]
    rows = list(payload["rows"])
    outliers = list(payload["outliers"])
    pubchemqc = payload["pubchemqc"]

    lines: list[str] = []
    lines.append("# W40-D 轨道通道外部对照层（QM9）与 PubChemQC 单文件子集可行性")
    lines.append("")
    lines.append("- 任务：W40-D（后验读数，0 shot）")
    lines.append("- 名册：data/processed/dielectric_physical_features_v03.csv（"
                 + str(payload["roster_total"]) + " 行）")
    lines.append("- 外部层：data/external/qm9_dataset.csv（sha256 " + QM9_SHA256 + "）")
    lines.append("- 记账：**不占 shot**（累计仍 19）；不改 METRIC_NAMES、不新增特征列、不动四个冻结读数")
    lines.append("")
    lines.append("## 0. 口径声明（口径先于读数）")
    lines.append("")
    lines.append("1. QM9 的 homo / lumo / gap 单位是 **Hartree**（1 Ha = "
                 + format(HARTREE_TO_EV, ".12f") + " eV）；它们是 **B3LYP/6-31G(2df,p) 气相**轨道能。")
    lines.append("2. 我们的 homo_lumo_gap_ev 是 **xTB GFN2 单点**。两者**层级不同** ⇒")
    lines.append("   本件**只谈排序（Spearman / Kendall）与标定（线性映射）**，")
    lines.append("   **不把 QM9 数值写进任何标签池 / 特征列 / 交付标签**，**不得直接互换**。")
    lines.append("3. QM9 许可 = CC BY 4.0（原始 deposition 10.6084/m9.figshare.978904）。")
    lines.append("4. W39 已判决的结论（含「刚性 vs 柔性构象」那条判否）本件**只引用、不重复声明为新发现**。")
    lines.append("")
    lines.append("## 0.1 一句话结论")
    lines.append("")
    lines.append("QM9 作为轨道通道**外部对照层**是宽的（**" + str(payload["n_hits"]) + " / "
                 + str(payload["roster_total"]) + "**）、排序是可信的（Spearman "
                 + format(float(ordering["spearman"]), ".4f") + "、Kendall "
                 + format(float(ordering["kendall"]), ".4f") + "），但**量级不可互换**"
                 "（未标定 |delta| 中位数 " + format(float(delta["median_abs_delta_ev"]), ".3f")
                 + " eV，" + str(delta["n_abs_delta_ge_1ev"]) + "/" + str(len(rows))
                 + " 条 >= 1 eV）；线性标定只消掉约 "
                 + format(float(calibration["loo_reduction"]) * 100.0, ".1f")
                 + "% 的误差（留一）⇒ 仍然只能当**排序先验**，不能当标签。"
                 "PubChemQC 的扩大覆盖路线**照实登记为受阻**（详见 §5）。")
    lines.append("")
    lines.append("## 1. 对照层读数")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 名册命中 | " + str(payload["n_hits"]) + " / " + str(payload["roster_total"]) + " |")
    lines.append("| Spearman | " + format(float(ordering["spearman"]), ".6f") + " |")
    lines.append("| Kendall tau | " + format(float(ordering["kendall"]), ".6f") + " |")
    lines.append("| Pearson | " + format(float(ordering["pearson"]), ".6f") + " |")
    lines.append("| 中位数比 xTB / QM9 | " + format(float(ordering["median_ratio_xtb_over_qm9"]), ".6f") + " |")
    lines.append("| 未标定 MAE | " + format(float(delta["raw_mae_ev"]), ".6f") + " eV |")
    lines.append("| 未标定 中位数 \\|delta\\| | " + format(float(delta["median_abs_delta_ev"]), ".6f") + " eV |")
    lines.append("| \\|delta\\| >= 1 eV | " + str(delta["n_abs_delta_ge_1ev"]) + " / " + str(len(rows))
                 + "（" + format(float(delta["frac_abs_delta_ge_1ev"]) * 100.0, ".1f") + "%） |")
    lines.append("| QM9 内部自洽 max \\|gap - (lumo - homo)\\| | "
                 + format(float(metrics["qm9_self_consistency_max_abs_ev"]), ".3e") + " eV |")
    lines.append("")
    lines.append("## 2. 层级不可互换的定量证据")
    lines.append("")
    lines.append("- 两个层级的中位数比（xTB / QM9）= "
                 + format(float(ordering["median_ratio_xtb_over_qm9"]), ".4f")
                 + " ⇒ 系统性压缩，方向与 W39 一致。")
    lines.append("- 未标定偏差：MAE " + format(float(delta["raw_mae_ev"]), ".3f") + " eV，"
                 "中位数 |delta| " + format(float(delta["median_abs_delta_ev"]), ".3f") + " eV。")
    lines.append("- 在 " + str(len(rows)) + " 条命中里有 " + str(delta["n_abs_delta_ge_1ev"])
                 + " 条 |delta| >= 1 eV ⇒ **任何把 QM9 值当标签或特征的做法都会引入 >= 1 eV 的层级误差**。")
    lines.append("- 完整离群清单见 w40_orbital_external_control.csv 的 abs_delta_gap_ev 列；下表列前 15 条。")
    lines.append("")
    lines.append("| 化合物 | xTB (eV) | QM9 (eV) | delta (eV) |")
    lines.append("| --- | --- | --- | --- |")
    for item in outliers[:15]:
        lines.append("| " + str(item["name"]) + " | " + format(float(item["xTB_gap_ev"]), ".3f")
                     + " | " + format(float(item["qm9_gap_ev"]), ".3f")
                     + " | " + format(float(item["delta_gap_ev"]), ".3f") + " |")
    lines.append("")
    lines.append("## 3. 标定（只在排序意义上可用）")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 标定式 | xTB = " + format(float(calibration["slope"]), ".6f")
                 + " * QM9 " + format(float(calibration["intercept"]), ".6f") + " |")
    lines.append("| 与 W39 冻结值一致 | " + ("是" if calibration["matches_w39"] else "否") + " |")
    lines.append("| 样本内标定 MAE | " + format(float(calibration["in_sample_mae_ev"]), ".6f") + " eV |")
    lines.append("| 样本内下降比例 | " + format(float(calibration["in_sample_reduction"]), ".6f") + " |")
    lines.append("| 留一标定 MAE | " + format(float(calibration["loo_mae_ev"]), ".6f") + " eV |")
    lines.append("| 留一下降比例 | " + format(float(calibration["loo_reduction"]), ".6f") + " |")
    lines.append("")
    lines.append("读数：标定把 MAE 从 " + format(float(delta["raw_mae_ev"]), ".3f") + " eV 降到 "
                 + format(float(calibration["loo_mae_ev"]), ".3f") + " eV（留一），下降 "
                 + format(float(calibration["loo_reduction"]) * 100.0, ".1f") + "%。"
                 "这**低于 50%** ⇒ 线性标定只修复了层级差的一小部分（其余来自泛函/基组/相态差异），"
                 "所以对照层只能用于**相对排序**，不能用于**绝对量级**。")
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
    lines.append("阈值首次冻结的依据：H40d2 沿用 W39 已经用过的 0.70，保持口径连续；"
                 "H40d3 的 0.50 是 0.70 在双变量正态下的对应 tau；"
                 "H40d4 的 1 eV 是「不能当标签」的物理下限；"
                 "H40d5 的 1/3 是「标定若有效至少应消去三分之一层级差」的下限；"
                 "H40d1 的 100 对齐 W39 的 103，只把「够宽」量化。")
    lines.append("")
    lines.append("## 5. PubChemQC 单文件子集可行性评估（只读侦察，未下载）")
    lines.append("")
    lines.append("侦察端点（2026-10-03，hf-mirror.com dataset tree API，只读）：")
    lines.append("")
    lines.append("- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-b3lyp/tree/main/data")
    lines.append("- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-pm6/tree/main/data")
    lines.append("- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-b3lyp/tree/refs%2Fconvert%2Fparquet")
    lines.append("  （返回 Invalid rev id ⇒ **无 parquet 分支**）")
    lines.append("")
    lines.append("各 config 的 train 分片统计（bytes 为 LFS 实文件大小）：")
    lines.append("")
    lines.append("| dataset | config | 分片数 | 最小分片 (B) | 最大分片 (B) | 合计 (B) | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in pubchemqc["census"]:
        lines.append("| " + str(item["dataset"]) + " | " + str(item["config"]) + " | "
                     + str(item["n_files"]) + " | " + str(item["min_shard_bytes"]) + " | "
                     + str(item["max_shard_bytes"]) + " | " + str(item["total_bytes"]) + " | "
                     + ("tree API 1000 项截断，合计为下界" if item["truncated"] else "") + " |")
    lines.append("")
    lines.append("**结论：名册级（" + str(payload["roster_total"]) + " 化合物）单文件子集下载 — 受阻（判否，已登记）。**")
    lines.append("")
    lines.append("- 全局最小单文件 = " + str(pubchemqc["min_shard_bytes"]) + " B（"
                 + format(float(pubchemqc["min_shard_bytes"]) / (1 << 20), ".1f") + " MiB），"
                 "路径 " + str(pubchemqc["min_shard_path"]) + "，"
                 "CID 区间 " + str(pubchemqc["min_shard_cid_range"]) + "。")
    lines.append("- 该值**低于 1 GiB** ⇒ 「单片体量」本身**不是**绝对阻塞；"
                 "**必须照实写这一点**，不能笼统记成「最小切片 325 GB 不可行」。")
    lines.append("- 真正阻塞的是可定位性：")
    for reason in pubchemqc["blocked_reasons"]:
        lines.append("  - " + str(reason))
    lines.append("- 最小可行替代：" + str(pubchemqc["minimal_viable_alternative"]))
    lines.append("")
    lines.append("## 6. 边界")
    lines.append("")
    lines.append("- QM9 = **CC BY 4.0 外部对照层**：可参考、可审计，但**不入任何池 / 特征 / 交付标签**。")
    lines.append("- 「刚性 vs 柔性」结论属 **W39**（H39a7 判否，刚性与柔性 |dmu| 中位数几乎一样）；"
                 "本件**只引用**，不重复声明为新发现。")
    lines.append("- 标定是**样本内 + 留一**两种读数；本件不做任何超参搜索，也不占用主记分牌 shot。")
    lines.append("- PubChemQC 部分**只做只读侦察**：本机未下载任何分片，结论的量化依据是 tree API 的 LFS 大小。")
    lines.append("- 本机 PubChem PUG REST 不可达这一条是**环境事实**，换机器后需要重新评估（见最小可行替代）。")
    lines.append("")
    lines.append("## 7. 输入指纹")
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
    metrics = payload["metrics"]
    calibration = metrics["calibration"]
    delta = metrics["delta"]
    qm9 = np.array([float(item["qm9_gap_ev"]) for item in rows])
    xtb = np.array([float(item["xTB_gap_ev"]) for item in rows])
    calibrated = np.array([float(item["qm9_gap_ev_calibrated"]) for item in rows])
    residual = np.array([float(item["residual_gap_ev"]) for item in rows])
    raw_delta = qm9 - xtb

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.5), dpi=160)

    axis = axes[0]
    axis.scatter(qm9, xtb, s=16, c="#2f6f9f", alpha=0.75, edgecolors="none", label="命中化合物")
    grid = np.linspace(float(qm9.min()), float(qm9.max()), 50)
    axis.plot(grid, float(calibration["slope"]) * grid + float(calibration["intercept"]),
              color="#b03a2e", linewidth=1.6,
              label="标定：xTB = " + format(float(calibration["slope"]), ".3f") + "*QM9 "
                    + format(float(calibration["intercept"]), ".2f"))
    axis.plot(grid, grid, color="#666666", linestyle="--", linewidth=1.0, label="y = x")
    axis.set_xlabel("QM9 B3LYP 间隙 (eV)", fontsize=9)
    axis.set_ylabel("本地 xTB GFN2 间隙 (eV)", fontsize=9)
    axis.set_title("外部对照层：排序一致、量级压缩（n = " + str(len(rows)) + "，Spearman "
                   + format(float(metrics["xtb_gap_ev"]["spearman"]), ".3f") + "）", fontsize=10)
    axis.legend(fontsize=7.5, loc="upper left")

    axis = axes[1]
    axis.hist(raw_delta, bins=24, color="#c98b3a", alpha=0.75,
              label="未标定 delta = QM9 - xTB")
    axis.hist(residual, bins=24, color="#2f7d4f", alpha=0.75,
              label="样本内标定残差 = xTB - 标定(QM9)")
    axis.axvline(0.0, color="#444444", linewidth=1.0, linestyle="--")
    axis.set_xlabel("偏差 (eV)", fontsize=9)
    axis.set_ylabel("化合物数", fontsize=9)
    axis.set_title("标定前后残差（MAE " + format(float(delta["raw_mae_ev"]), ".2f") + " -> "
                   + format(float(calibration["in_sample_mae_ev"]), ".2f") + " eV）", fontsize=10)
    axis.legend(fontsize=7.5)

    axis = axes[2]
    hits = int(payload["n_hits"])
    total = int(payload["roster_total"])
    labels = ["QM9 命中", "QM9 未命中"]
    axis.barh([0], [hits], color="#2f6f9f", height=0.45, label="命中 " + str(hits))
    axis.barh([0], [total - hits], left=[hits], color="#cccccc", height=0.45,
              label="未命中 " + str(total - hits))
    axis.set_yticks([0])
    axis.set_yticklabels(["名册 " + str(total) + " 行"], fontsize=9)
    axis.set_xlim(0, total)
    axis.set_xlabel("化合物数", fontsize=9)
    axis.set_title("名册命中面：" + str(hits) + " / " + str(total) + "（"
                   + format(hits / total * 100.0, ".1f") + "%）", fontsize=10)
    axis.legend(fontsize=7.5, loc="lower right")
    axis.text(hits * 0.5, 0.0, str(hits), ha="center", va="center", color="white", fontsize=9)

    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def write_channels_update() -> int:
    """在 W38 渠道准入清单基础上，为 PubChemQC 两行补 W40 判词。"""

    with CHANNELS_IN.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    extra = ("w40_verdict", "w40_note", "min_shard_bytes")
    out_fields = fields + [name for name in extra if name not in fields]
    b3lyp = next(item for item in PUBCHEMQC_CENSUS if item["config"] == "b3lyp_pm6_chon300nosalt")
    pm6 = next(item for item in PUBCHEMQC_CENSUS if item["config"] == "pm6opt_chon300nosalt")
    notes = {
        "molssiai_pubchemqc_b3lyp": {
            "w40_verdict": "受阻（名册级）",
            "w40_note": "最小单文件 536,126,834 B（511.3 MiB，b3lyp_pm6_chon500nosalt 尾片，"
                        "CID 区间 121433757-121494125）< 1 GiB；但无 CID/InChIKey 索引、无 parquet 分支、"
                        "分片按 CID 区间切分，且本机 PubChem PUG REST 不可达 ⇒ 无法定位名册化合物所在分片。"
                        "最小配置 chon300nosalt 全量 " + str(b3lyp["total_bytes"]) + " B（≈349 GB）。",
            "min_shard_bytes": 536126834,
        },
        "molssiai_pubchemqc_pm6": {
            "w40_verdict": "受阻（名册级）",
            "w40_note": "最小单文件 1,498,874,351 B（pm6opt_chon300nosalt 尾片）；"
                        "pm6opt 全量 >= 3,873,347,155,187 B（tree API 1000 项截断，W38 文档记 ~8.4 TB）。"
                        "同样受 CID 索引缺失与 PubChem 不可达阻塞。",
            "min_shard_bytes": int(pm6["min_shard_bytes"]),
        },
    }
    filled = 0
    for row in rows:
        key = str(row.get("channel_key") or "")
        if key in notes:
            row.update(notes[key])
            filled += 1
        else:
            for name in extra:
                row.setdefault(name, "")
    write_csv_lf(CHANNELS_OUT, out_fields, rows)
    return filled


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    parser.add_argument("--skip-channels", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()

    before_roster = sha256_file(ROSTER_CSV)
    before_qm9 = sha256_file(QM9_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(CONTROL_CSV, CONTROL_FIELDS, payload["rows"])
    channels_note = 0
    if not args.skip_channels:
        channels_note = write_channels_update()
    after_roster = sha256_file(ROSTER_CSV)
    after_qm9 = sha256_file(QM9_CSV)
    if not args.skip_figure:
        make_figure(payload)

    inputs = {
        str(ROSTER_CSV): before_roster,
        "roster_sha256_after": after_roster,
        "roster_expected_sha256": ROSTER_SHA256,
        str(QM9_CSV): before_qm9,
        "qm9_sha256_after": after_qm9,
        "qm9_expected_sha256": QM9_SHA256,
    }
    inputs_unchanged = (
        before_roster == after_roster
        and before_qm9 == after_qm9
        and before_roster == ROSTER_SHA256
        and before_qm9 == QM9_SHA256
    )
    criteria.append({
        "id": "H40d10",
        "description": "输入未被改写：名册与 QM9 的 sha256 前后一致，且两者与登记指纹相符",
        "value": 1.0 if inputs_unchanged else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if inputs_unchanged else "判否",
    })

    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    metrics = payload["metrics"]
    ordering = metrics["xtb_gap_ev"]
    delta = metrics["delta"]
    calibration = metrics["calibration"]
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读盘上既有的名册与 QM9 对照层，并用只读 HTTP 侦察 PubChemQC 的"
                              "分片元数据；不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES、"
                              "不动四个冻结读数。",
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
            "level_of_theory": "B3LYP/6-31G(2df,p)（气相）",
            "license": "CC BY 4.0（原始 deposition 10.6084/m9.figshare.978904，DataCite rightsList）",
            "unit": "homo / lumo / gap 单位为 Hartree；1 Ha = " + format(HARTREE_TO_EV, ".12f") + " eV",
            "columns_used": ["inchi", "homo", "lumo", "gap"],
            "not_used_as": "外部对照层：不入标签池、不入特征列、不与 xTB 直接互换；只谈排序与标定",
        },
        "roster_total": int(payload["roster_total"]),
        "n_hits": int(payload["n_hits"]),
        "orbital_ordering": ordering,
        "gap_delta": delta,
        "calibration": calibration,
        "pubchemqc_recon": payload["pubchemqc"],
        "channels_rows_filled": channels_note,
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "QM9 轨道对照层覆盖 " + str(payload["n_hits"]) + " / " + str(payload["roster_total"])
            + "；排序可信（Spearman " + format(float(ordering["spearman"]), ".4f") + "、Kendall "
            + format(float(ordering["kendall"]), ".4f") + "），量级不可互换（未标定 |delta| 中位数 "
            + format(float(delta["median_abs_delta_ev"]), ".3f") + " eV，"
            + str(delta["n_abs_delta_ge_1ev"]) + "/" + str(len(payload["rows"])) + " 条 >= 1 eV）。",
            "线性标定（留一）把 MAE 从 " + format(float(delta["raw_mae_ev"]), ".3f") + " eV 降到 "
            + format(float(calibration["loo_mae_ev"]), ".3f") + " eV，下降 "
            + format(float(calibration["loo_reduction"]) * 100.0, ".1f") + "%（< 50%）⇒ 只作排序先验。",
            "标定式复现 W39 冻结值（xTB = " + format(float(calibration["slope"]), ".6f") + " * QM9 "
            + format(float(calibration["intercept"]), ".6f") + "），口径连续。",
            "PubChemQC 名册级单文件子集下载：**受阻**（已登记判否，H40d8）；"
            "全局最小分片 " + str(payload["pubchemqc"]["min_shard_bytes"]) + " B < 1 GiB，"
            "阻塞在索引缺失与 PubChem 不可达，而非单片体量。",
            "不占 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, inputs), encoding="utf-8", newline="\n")

    print("qm9 rows " + str(payload["qm9_rows"]) + "; roster " + str(payload["roster_total"])
          + "; hits " + str(payload["n_hits"]))
    print("gap spearman " + format(float(ordering["spearman"]), ".6f")
          + "; kendall " + format(float(ordering["kendall"]), ".6f")
          + "; pearson " + format(float(ordering["pearson"]), ".6f")
          + "; median ratio " + format(float(ordering["median_ratio_xtb_over_qm9"]), ".6f"))
    print("raw mae " + format(float(delta["raw_mae_ev"]), ".6f")
          + "; median |delta| " + format(float(delta["median_abs_delta_ev"]), ".6f")
          + "; n|delta|>=1eV " + str(delta["n_abs_delta_ge_1ev"]) + "/" + str(len(payload["rows"])))
    print("calibration slope " + format(float(calibration["slope"]), ".9f")
          + "; intercept " + format(float(calibration["intercept"]), ".9f")
          + "; matches_w39 " + str(bool(calibration["matches_w39"])))
    print("in-sample mae " + format(float(calibration["in_sample_mae_ev"]), ".6f")
          + " (reduction " + format(float(calibration["in_sample_reduction"]), ".6f") + ")"
          + "; loo mae " + format(float(calibration["loo_mae_ev"]), ".6f")
          + " (reduction " + format(float(calibration["loo_reduction"]), ".6f") + ")")
    print("pubchemqc min shard bytes " + str(payload["pubchemqc"]["min_shard_bytes"])
          + "; under 1 GiB " + str(bool(payload["pubchemqc"]["min_shard_under_1gib"]))
          + "; roster-level feasible " + str(bool(payload["pubchemqc"]["roster_level_download_feasible"]))
          + "; channels rows filled " + str(channels_note))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
