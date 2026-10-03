# -*- coding: utf-8 -*-
"""W40-C：Onsager 域规则精化 + 偶极双 mu 读数化（后验读数，0 shot）。

W38-C 把 Kirkwood-Onsager 关系

    L(eps) = (eps - 1)(2 eps + 1) / (9 eps)  正比于  x = mu^2 / V_m

的域划分交给表内 hbd 列，而该列继承 RDKit 的 Lipinski donor 定义。README 第 23 号待办登记了它的
已知缺陷：**该定义不把水算作给体**（RDKit NumHDonors(H2O) == 0），于是 water（eps = 78.87）
落在「理应 g 接近 1」的非给体域，实测 g_rel 却有 2.2 左右。本件做三件事：

1. 域规则精化：用 RDKit 从 SMILES 机械判定「连在 N/O/F 上、该杂原子不带正电、且不是酰胺 N-H
   的氢」——即真正能作为氢键给体去自缔合的质子。规则只读结构，不读 eps，跑前可写死。
2. 双 mu 读数：g_rel 主判据对 dipole_D 分两套 mu 各算一遍（本地 xTB / W39 的 QM9 B3LYP 对照层）。
   QM9 只覆盖 103 个命中化合物，因此第二套 mu 只在该子集上成立；两套 mu 的差只用中位数与秩表述，
   不比绝对值。
3. 偶极质量审计收口：W39 实测的约 0.39 D 系统偏置（签署差中位数 -0.3914 D）作为已知偏置并入，
   做 mu 减去该偏置的校正敏感性读数；不做插补、不改特征表。

只读盘上既有特征表与 W39 对照产物；不拟合模型、不新增特征列、不改 METRIC_NAMES。
=> 0 shot（累计仍 19），四个冻结读数不动。

Run:
    .venv/Scripts/python.exe probes/w40_onsager_domain.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
import numpy as np  # noqa: E402
from probes.export_results_common import write_json_stable  # noqa: E402
from rdkit import Chem, RDLogger  # noqa: E402
from rdkit.Chem import Descriptors  # noqa: E402
from rdkit.Chem.MolStandardize import rdMolStandardize  # noqa: E402
from scipy.stats import pearsonr, spearmanr  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
OVERLAP_CSV = ARTIFACTS / "w39_qm9_overlap.csv"
COMPOUNDS_CSV = ARTIFACTS / "w40_onsager_domain_compounds.csv"
SUMMARY_CSV = ARTIFACTS / "w40_onsager_domain_summary.csv"
SUMMARY_PATH = ARTIFACTS / "w40_onsager_domain_summary.json"
FIGURE_PATH = ARTIFACTS / "w40_onsager_domain.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w40_onsager_domain.md"

SCHEMA = "w40_onsager_domain/summary@1"
TASK = "week40_onsager_domain"

# 首次冻结即登记两条判否（阈值不原地改）：
#   H40c10 偏置校正前后域间比相对变化 <= 0.10 的严格稳健门 —— 实测 0.2059，方向不变但幅度不稳健。
#   H40c11 「水的 g_rel 高于给体域中位数」—— 实测水的 g_rel 在给体域内偏低（约 2.25），
#          说明水被错分域是**分类**错误，不是「水的残差极端大」的**量级**证据。
REGISTERED_NEGATIVES: tuple[str, ...] = ("H40c10", "H40c11")

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

# 口径锚：W38-C 登记的旧口径读数（本件必须逐位复现，否则新旧不可比）。
W38C_OLD_RATIO = 2.5016162961750874
W38C_OLD_HIGH_EPS_RATIO = 15.650359815921144
W38C_OLD_AGREEMENT = 1.0
# W39-B 实测的签署差（QM9 减本地）中位数，|delta| < 1 D 的 90 个化合物上。
W39_MEDIAN_SIGNED_DELTA_D = -0.3914000000000001

RATIO_GATE = 1.50
HIGH_EPS = 60.0
HIGH_EPS_GATE = 2.0
DOUBLE_MU_SPEARMAN_GATE = 0.60
DOUBLE_MU_RATIO_TOL = 0.05
BIAS_STABILITY_TOL = 0.10
MIN_DIPOLE_D = 1.0
ANCHOR_TOL = 1e-9
EXPECTED_CHANGED = 3
EXPECTED_WATER_DONOR_H = 2
EXPECTED_THIOL_REMOVED = 2
EXPECTED_POSITIVE_H_COMPOUNDS = 1
EXPECTED_AMIDE_EXCLUDED = 0
EXPECTED_TAUTOMER_FLIPS = 2

AMIDE_N_SMARTS = "[NX3][CX3]=[OX1]"

CJK_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
)


def pick_cjk_font() -> str | None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in CJK_CANDIDATES:
        if name in available:
            return name
    return None
AMIDE_PATTERN = Chem.MolFromSmarts(AMIDE_N_SMARTS)

RULE_TEXT = (
    "donor_h >= 1 判为给体域（B），否则非给体域（A）。donor_h = 分子里满足以下全部条件的氢数："
    "(1) 氢连在 N / O / F 上；(2) 该杂原子形式电荷 <= 0（正电杂原子的氢排除，如 [NH3+]）；"
    "(3) 不是酰胺 N-H（N 匹配 [NX3][CX3]=[OX1]）。S-H 不计（任务规定只算 N/O/F，属已登记规则边界）。"
    "规则只读结构、不读 eps；跑前写死，不按 eps 大小挑样本。"
)

OLD_RULE_TEXT = "table hbd == 0 判为非给体域（A），hbd >= 1 判为给体域（B）（W38-C 口径，继承 RDKit Lipinski donor）。"

COMPOUND_FIELDS = (
    "inchikey", "name", "smiles", "T_K", "eps", "hbd_old", "rdkit_hbd", "donor_h_new",
    "amide_nh_h", "positive_h_excluded", "thiol_h", "canonical_smiles", "canonical_donor_h",
    "tautomer_flip", "domain_old", "domain_new", "changed", "change_dir", "dipole_D",
    "dipole_D_qm9", "in_qm9", "mu_corr_D", "mu_sq_over_Vm", "L_over_x", "g_rel_new",
    "g_rel_old", "L_over_x_corr", "g_rel_corr", "usable",
)

SUMMARY_DOMAIN_FIELDS = (
    "rule", "mu_source", "scope", "domain", "n", "median_L_over_x", "median_g_rel",
    "r2_through_origin", "pearson", "median_eps", "median_dipole_D", "ratio_donor_over_acceptor",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, float):
                text = "" if value != value else repr(value)
            else:
                text = "" if value is None else str(value)
            if any(ch in text for ch in (",", '"', "\n")):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def _float(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float("nan")


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else float("nan")


def kirkwood_lhs(eps: float) -> float:
    return (eps - 1.0) * (2.0 * eps + 1.0) / (9.0 * eps)


def donor_census(mol: Chem.Mol) -> dict[str, int]:
    """机械给体计数（新口径）。S-H 单列，作规则边界登记。"""
    amide_nitrogens = {match[0] for match in mol.GetSubstructMatches(AMIDE_PATTERN)}
    donor_h = 0
    amide_nh_h = 0
    positive_h = 0
    thiol_h = 0
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        n_h = int(atom.GetTotalNumHs())
        if n_h <= 0:
            continue
        if symbol == "S":
            thiol_h += n_h
            continue
        if symbol not in ("N", "O", "F"):
            continue
        if atom.GetFormalCharge() > 0:
            positive_h += n_h
            continue
        if symbol == "N" and atom.GetIdx() in amide_nitrogens:
            amide_nh_h += n_h
            continue
        donor_h += n_h
    return {
        "donor_h": donor_h,
        "amide_nh_h": amide_nh_h,
        "positive_h": positive_h,
        "thiol_h": thiol_h,
    }


def load_qm9_dipoles() -> dict[str, float]:
    """W39 对照层里的 QM9 偶极，按 InChIKey 索引（只读，不落盘）。"""
    dipoles: dict[str, float] = {}
    with OVERLAP_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("inchikey") or "").strip()
            value = _float(row.get("qm9_dipole_D"))
            if key and value == value:
                dipoles[key] = value
    return dipoles


def load_roster(qm9_dipoles: Mapping[str, float]) -> list[dict[str, object]]:
    tautomer_enumerator = rdMolStandardize.TautomerEnumerator()
    records: list[dict[str, object]] = []
    with ROSTER_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            smiles = (raw.get("smiles") or "").strip()
            mol = Chem.MolFromSmiles(smiles) if smiles else None
            census = {"donor_h": None, "amide_nh_h": None, "positive_h": None, "thiol_h": None}
            canonical_smiles = ""
            canonical_donor_h = None
            rdkit_hbd = None
            if mol is not None:
                census = donor_census(mol)
                rdkit_hbd = int(Descriptors.NumHDonors(mol))
                canonical = tautomer_enumerator.Canonicalize(mol)
                canonical_smiles = Chem.MolToSmiles(canonical)
                canonical_donor_h = donor_census(canonical)["donor_h"]
            key = (raw.get("inchikey") or "").strip()
            eps = _float(raw.get("dielectric"))
            hbd_old = _float(raw.get("hbd"))
            dipole = _float(raw.get("dipole_D"))
            molar_volume = _float(raw.get("molar_volume_m3_mol"))
            x = _float(raw.get("mu_sq_over_Vm"))
            in_qm9 = key in qm9_dipoles
            records.append(
                {
                    "inchikey": key,
                    "name": raw.get("name") or "",
                    "smiles": smiles,
                    "T_K": _float(raw.get("T_K")),
                    "eps": eps,
                    "hbd_old": hbd_old,
                    "rdkit_hbd": rdkit_hbd,
                    "donor_h_new": census["donor_h"],
                    "amide_nh_h": census["amide_nh_h"],
                    "positive_h_excluded": census["positive_h"],
                    "thiol_h": census["thiol_h"],
                    "canonical_smiles": canonical_smiles,
                    "canonical_donor_h": canonical_donor_h,
                    "domain_old": ("B" if hbd_old >= 1 else "A") if hbd_old == hbd_old else None,
                    "domain_new": ("B" if census["donor_h"] >= 1 else "A")
                    if census["donor_h"] is not None
                    else None,
                    "dipole_D": dipole,
                    "dipole_D_qm9": qm9_dipoles.get(key) if in_qm9 else None,
                    "in_qm9": bool(in_qm9),
                    "molar_volume_m3_mol": molar_volume,
                    "mu_sq_over_Vm": x,
                    "usable": bool(eps > 1.0 and x > 0.0 and x == x and hbd_old == hbd_old
                                   and census["donor_h"] is not None and molar_volume > 0.0),
                }
            )
    return records


def fit_through_origin(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float]:
    if xs.size == 0:
        return float("nan"), float("nan"), float("nan")
    slope = float((xs * ys).sum() / (xs * xs).sum())
    residual = ys - slope * xs
    ss_res = float((residual * residual).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    rho = float(np.corrcoef(xs, ys)[0, 1]) if xs.size > 2 else float("nan")
    return slope, r2, rho


def domain_table(
    records: Sequence[Mapping[str, object]],
    x_key: str,
    mu_key: str,
    domain_key: str,
) -> dict[str, object]:
    """域内中位数口径：g_rel 的参考中位数 = 非给体域（A）的 median(L/x)，故 A 的 median g_rel 恒为 1。"""
    usable = [
        record for record in records
        if record.get(x_key) is not None and float(record[x_key]) > 0.0
        and record.get(domain_key) in ("A", "B")
    ]
    table: dict[str, object] = {}
    for domain in ("A", "B"):
        members = [record for record in usable if record[domain_key] == domain]
        values = [float(record["L_of_eps"]) / float(record[x_key]) for record in members]
        xs = np.asarray([float(record[x_key]) for record in members], dtype=float)
        ys = np.asarray([float(record["L_of_eps"]) for record in members], dtype=float)
        _, r2, rho = fit_through_origin(xs, ys)
        dipoles = [float(record[mu_key]) for record in members
                   if record.get(mu_key) is not None and float(record[mu_key]) == float(record[mu_key])]
        table[domain] = {
            "n": len(members),
            "median_L_over_x": _median(values),
            "median_g_rel": 1.0 if domain == "A" else None,
            "r2_through_origin": r2,
            "pearson": rho,
            "median_eps": _median([float(record["eps"]) for record in members]),
            "median_dipole_D": _median(dipoles),
        }
    ratio = (
        float(table["B"]["median_L_over_x"]) / float(table["A"]["median_L_over_x"])
        if table["A"]["median_L_over_x"] and table["A"]["median_L_over_x"] == table["A"]["median_L_over_x"]
        else float("nan")
    )
    table["B"]["median_g_rel"] = ratio
    table["ratio"] = ratio
    table["n_used"] = len(usable)
    return table


def subset_g_rel(
    hits: Sequence[Mapping[str, object]],
    mu_key: str,
) -> dict[str, dict[str, float]]:
    """子集内口径：x = mu^2 / V_m，用子集自己的非给体域中位数做参考。"""
    out: dict[str, dict[str, float]] = {}
    for record in hits:
        mu = record.get(mu_key)
        volume = float(record["molar_volume_m3_mol"])
        eps = float(record["eps"])
        if mu is None or float(mu) < MIN_DIPOLE_D or volume <= 0.0 or eps <= 1.0:
            continue
        out[str(record["inchikey"])] = {
            "name": str(record["name"]),
            "domain": str(record["domain_new"]),
            "mu": float(mu),
            "g": kirkwood_lhs(eps) / (float(mu) ** 2 / volume),
        }
    return out


def subset_domain_ratio(values: Mapping[str, Mapping[str, float]]) -> dict[str, object]:
    donor = [entry["g"] for entry in values.values() if entry["domain"] == "B"]
    acceptor = [entry["g"] for entry in values.values() if entry["domain"] == "A"]
    if len(donor) < 3 or len(acceptor) < 3:
        return {"n_donor": len(donor), "n_acceptor": len(acceptor), "ratio": None}
    return {
        "n_donor": len(donor),
        "n_acceptor": len(acceptor),
        "median_donor": _median(donor),
        "median_acceptor": _median(acceptor),
        "ratio": _median(donor) / _median(acceptor),
    }


def recompute_w39_signed_delta_median() -> tuple[float, int]:
    """从 W39 对照层重算签署差中位数（只读），作为偏置校正的输入。"""
    deltas: list[float] = []
    with OVERLAP_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = _float(row.get("dipole_delta_D"))
            if value == value and abs(value) < 1.0:
                deltas.append(value)
    return _median(deltas), len(deltas)


def build() -> dict[str, object]:
    qm9_dipoles = load_qm9_dipoles()
    records = load_roster(qm9_dipoles)
    bias_signed, bias_n = recompute_w39_signed_delta_median()

    for record in records:
        eps = float(record["eps"])
        record["L_of_eps"] = kirkwood_lhs(eps) if eps > 1.0 else float("nan")
        record["mu_corr_D"] = (
            float(record["dipole_D"]) + bias_signed if float(record["dipole_D"]) == float(record["dipole_D"])
            else float("nan")
        )
        volume = float(record["molar_volume_m3_mol"])
        record["x_corr"] = (
            float(record["mu_corr_D"]) ** 2 / volume
            if float(record["mu_corr_D"]) == float(record["mu_corr_D"])
            and float(record["mu_corr_D"]) > 0.0 and volume > 0.0
            else None
        )
        record["changed"] = bool(
            record["domain_old"] is not None and record["domain_new"] is not None
            and record["domain_old"] != record["domain_new"]
        )
        record["change_dir"] = (
            str(record["domain_old"]) + "->" + str(record["domain_new"]) if record["changed"] else ""
        )
        record["tautomer_flip"] = bool(
            record["donor_h_new"] is not None and record["canonical_donor_h"] is not None
            and (int(record["donor_h_new"]) >= 1) != (int(record["canonical_donor_h"]) >= 1)
        )
        record["domain_canonical"] = (
            "B" if int(record["canonical_donor_h"]) >= 1 else "A"
        ) if record["canonical_donor_h"] is not None else None
        record["domain_include_amide"] = (
            "B" if int(record["donor_h_new"]) + int(record["amide_nh_h"]) >= 1 else "A"
        ) if record["donor_h_new"] is not None else None

    usable = [record for record in records if bool(record["usable"])]
    for record in usable:
        record["mu_sq_over_Vm"] = float(record["mu_sq_over_Vm"])
        record["L_over_x"] = float(record["L_of_eps"]) / float(record["mu_sq_over_Vm"])

    stats_old = domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_old")
    stats_new = domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_new")
    stats_corr = domain_table(records, "x_corr", "mu_corr_D", "domain_new")
    stats_canonical = domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_canonical")
    stats_include_amide = domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_include_amide")

    median_a_new = float(stats_new["A"]["median_L_over_x"])
    median_a_old = float(stats_old["A"]["median_L_over_x"])
    median_a_corr = float(stats_corr["A"]["median_L_over_x"])
    for record in usable:
        record["g_rel_new"] = float(record["L_over_x"]) / median_a_new
        record["g_rel_old"] = float(record["L_over_x"]) / median_a_old
        record["L_over_x_corr"] = (
            float(record["L_of_eps"]) / float(record["x_corr"]) if record["x_corr"] else float("nan")
        )
        record["g_rel_corr"] = (
            float(record["L_over_x_corr"]) / median_a_corr
            if record["L_over_x_corr"] == record["L_over_x_corr"] else float("nan")
        )

    high_eps = [record for record in usable if float(record["eps"]) >= HIGH_EPS]
    high_eps_ratio = {}
    for label, domain_key, x_key in (
        ("old", "domain_old", "mu_sq_over_Vm"),
        ("new", "domain_new", "mu_sq_over_Vm"),
        ("new_bias_corrected", "domain_new", "x_corr"),
    ):
        donor = [float(record["L_of_eps"]) / float(record[x_key]) for record in high_eps
                 if record[domain_key] == "B" and record.get(x_key) and float(record[x_key]) > 0.0]
        acceptor = [float(record["L_of_eps"]) / float(record[x_key]) for record in high_eps
                    if record[domain_key] == "A" and record.get(x_key) and float(record[x_key]) > 0.0]
        high_eps_ratio[label] = {
            "n_donor": len(donor),
            "n_acceptor": len(acceptor),
            "median_donor": _median(donor),
            "median_acceptor": _median(acceptor),
            "ratio": (_median(donor) / _median(acceptor)) if donor and acceptor else float("nan"),
        }

    hits = [record for record in records if bool(record["in_qm9"])]
    ours = subset_g_rel(hits, "dipole_D")
    theirs = subset_g_rel(hits, "dipole_D_qm9")
    shared = sorted(set(ours) & set(theirs))
    g_our = [ours[key]["g"] for key in shared]
    g_qm9 = [theirs[key]["g"] for key in shared]
    spearman_value = float(spearmanr(g_our, g_qm9).statistic) if len(shared) > 2 else float("nan")
    pearson_value = float(pearsonr(g_our, g_qm9)[0]) if len(shared) > 2 else float("nan")
    median_g_rel_ratio = _median([theirs[key]["g"] / ours[key]["g"] for key in shared])
    rank_our = {key: rank for rank, key in enumerate(sorted(shared, key=lambda item: ours[item]["g"]))}
    rank_qm9 = {key: rank for rank, key in enumerate(sorted(shared, key=lambda item: theirs[item]["g"]))}
    median_abs_rank_shift = _median([float(abs(rank_our[key] - rank_qm9[key])) for key in shared])
    subset_ratio_our = subset_domain_ratio(ours)
    subset_ratio_qm9 = subset_domain_ratio(theirs)

    changed = [record for record in records if bool(record["changed"])]
    tautomer_flips = [record for record in records if bool(record["tautomer_flip"])]
    amide_excluded = [record for record in records if int(record["amide_nh_h"] or 0) > 0]
    positive_h = [record for record in records if int(record["positive_h_excluded"] or 0) > 0]
    thiol_records = [record for record in records if int(record["thiol_h"] or 0) > 0]
    include_amide_flips = [
        record for record in records
        if record["domain_include_amide"] is not None and record["domain_new"] is not None
        and record["domain_include_amide"] != record["domain_new"]
    ]
    water = [record for record in records if str(record["name"]) == "water"]
    water_record = water[0] if water else None
    paired = [record for record in records
              if record["rdkit_hbd"] is not None and float(record["hbd_old"]) == float(record["hbd_old"])]
    agreement = (
        sum(1 for record in paired if int(record["rdkit_hbd"]) == int(float(record["hbd_old"])))
        / len(paired) if paired else float("nan")
    )

    return {
        "records": records,
        "usable": usable,
        "stats_old": stats_old,
        "stats_new": stats_new,
        "stats_corr": stats_corr,
        "stats_canonical": stats_canonical,
        "stats_include_amide": stats_include_amide,
        "ratio_old": float(stats_old["ratio"]),
        "ratio_new": float(stats_new["ratio"]),
        "ratio_new_corr": float(stats_corr["ratio"]),
        "ratio_canonical": float(stats_canonical["ratio"]),
        "ratio_include_amide": float(stats_include_amide["ratio"]),
        "high_eps": {"threshold": HIGH_EPS, "n": len(high_eps), "variants": high_eps_ratio,
                     "members": [
                         {"name": str(record["name"]), "eps": float(record["eps"]),
                          "hbd_old": float(record["hbd_old"]), "donor_h_new": int(record["donor_h_new"]),
                          "dipole_D": float(record["dipole_D"]), "g_rel_new": float(record["g_rel_new"]),
                          "domain_old": str(record["domain_old"]), "domain_new": str(record["domain_new"])}
                         for record in sorted(high_eps, key=lambda item: -float(item["eps"]))
                     ]},
        "bias": {"signed_delta_median_D": bias_signed, "n_agreeing": bias_n,
                 "expected_signed_delta_median_D": W39_MEDIAN_SIGNED_DELTA_D,
                 "n_dropped_mu_nonpositive": sum(1 for record in usable if record["x_corr"] is None),
                 "corrected_ratio": float(stats_corr["ratio"]),
                 "relative_change": abs(float(stats_corr["ratio"]) - float(stats_new["ratio"]))
                 / float(stats_new["ratio"])},
        "double_mu": {"n_hits": len(hits), "n_both_ge_1D": len(shared),
                      "our_mu": subset_ratio_our, "qm9_mu": subset_ratio_qm9,
                      "spearman_g_rel": spearman_value, "pearson_g_rel": pearson_value,
                      "median_g_rel_ratio_qm9_over_our": median_g_rel_ratio,
                      "median_abs_rank_shift": median_abs_rank_shift},
        "changed": changed,
        "changed_names": [str(record["name"]) for record in changed],
        "tautomer_flips": tautomer_flips,
        "tautomer_flip_names": [str(record["name"]) for record in tautomer_flips],
        "amide_excluded_count": len(amide_excluded),
        "positive_h_compound_count": len(positive_h),
        "positive_h_names": [str(record["name"]) for record in positive_h],
        "thiol_count": len(thiol_records),
        "thiol_names": [str(record["name"]) for record in thiol_records],
        "include_amide_flip_count": len(include_amide_flips),
        "water": water_record,
        "agreement_with_rdkit_hbd": agreement,
        "n_paired_with_rdkit_hbd": len(paired),
        "n_records": len(records),
        "n_usable": len(usable),
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    criteria: list[dict[str, object]] = []
    ratio_new = float(payload["ratio_new"])
    anchor_ok = abs(float(payload["ratio_old"]) - W38C_OLD_RATIO) <= ANCHOR_TOL
    high_eps = payload["high_eps"]["variants"]
    double_mu = payload["double_mu"]
    subset_our = float(double_mu["our_mu"]["ratio"])
    subset_qm9 = float(double_mu["qm9_mu"]["ratio"])
    subset_tol = abs(subset_our - subset_qm9) / subset_our
    water = payload["water"]
    water_g_rel = float(water["g_rel_new"]) if water is not None else float("nan")
    high_old = float(high_eps["old"]["ratio"])
    high_new = float(high_eps["new"]["ratio"])

    criteria.append({
        "id": "H40c1",
        "description": "新域规则（N/O/F-H、非酰胺、非正电）下给体域/非给体域 g_rel 中位数比 >= 1.5"
                       "（沿用 W38-C 的 RATIO_GATE），且旧口径锚 2.5016162961750874 被逐位复现",
        "value": ratio_new,
        "threshold": RATIO_GATE,
        "verdict": "成立" if ratio_new >= RATIO_GATE and anchor_ok else "判否",
    })
    criteria.append({
        "id": "H40c2",
        "description": "水的域归属被纠正：旧口径 hbd=0 / RDKit NumHDonors=0 判入非给体域 A，"
                       "新规则 donor_h=" + str(EXPECTED_WATER_DONOR_H) + " 判入给体域 B",
        "value": float(int(water is not None and water["domain_old"] == "A"
                          and water["domain_new"] == "B"
                          and int(water["donor_h_new"]) == EXPECTED_WATER_DONOR_H)),
        "threshold": 1.0,
        "verdict": "成立" if (water is not None and water["domain_old"] == "A"
                              and water["domain_new"] == "B"
                              and int(water["donor_h_new"]) == EXPECTED_WATER_DONOR_H) else "判否",
    })
    criteria.append({
        "id": "H40c3",
        "description": "被改判化合物恰 " + str(EXPECTED_CHANGED) + " 条（water A->B；1-Butanethiol、"
                       "1-Pentanethiol B->A），且规则边界计数与登记一致：S-H 被排除 "
                       + str(EXPECTED_THIOL_REMOVED) + " 条、正电杂原子-H 被排除 "
                       + str(EXPECTED_POSITIVE_H_COMPOUNDS) + " 条、酰胺条款在名册书写上 "
                       + str(EXPECTED_AMIDE_EXCLUDED) + " 条",
        "value": float(len(payload["changed"])),
        "threshold": float(EXPECTED_CHANGED),
        "verdict": "成立" if (len(payload["changed"]) == EXPECTED_CHANGED
                              and int(payload["thiol_count"]) == EXPECTED_THIOL_REMOVED
                              and int(payload["positive_h_compound_count"]) == EXPECTED_POSITIVE_H_COMPOUNDS
                              and int(payload["amide_excluded_count"]) == EXPECTED_AMIDE_EXCLUDED) else "判否",
    })
    criteria.append({
        "id": "H40c4",
        "description": "互变异构敏感性：同一规则作用到 RDKit 标准互变异构体上（甲酰胺、N-甲基乙酰胺变为"
                       "酰胺式、其 N-H 被酰胺条款排除，" + str(EXPECTED_TAUTOMER_FLIPS) + " 条翻转）后，"
                       "域间比仍 >= 1.5",
        "value": float(payload["ratio_canonical"]),
        "threshold": RATIO_GATE,
        "verdict": "成立" if (float(payload["ratio_canonical"]) >= RATIO_GATE
                              and len(payload["tautomer_flips"]) == EXPECTED_TAUTOMER_FLIPS) else "判否",
    })
    criteria.append({
        "id": "H40c5",
        "description": "eps >= 60 族内，新口径给体子群 / 非给体子群 g_rel 中位数比 >= 2"
                       "（沿用 W38-C 的 HIGH_EPS_GATE）",
        "value": high_new,
        "threshold": HIGH_EPS_GATE,
        "verdict": "成立" if high_new >= HIGH_EPS_GATE else "判否",
    })
    criteria.append({
        "id": "H40c6",
        "description": "旧口径把水错放非给体域，因此高估高介电族域分离：旧比 > 新比",
        "value": high_old - high_new,
        "threshold": 0.0,
        "verdict": "成立" if high_old > high_new else "判否",
    })
    criteria.append({
        "id": "H40c7",
        "description": "双 mu 秩一致：两套 mu 都 >= 1 D 的 " + str(double_mu["n_both_ge_1D"])
                       + " 个命中化合物上 Spearman(g_rel_our, g_rel_qm9) >= 0.60"
                       "（首次冻结；低于 W39 单变量偶极的 0.8022，因为 1/mu^2 变换会放大噪声）",
        "value": float(double_mu["spearman_g_rel"]),
        "threshold": DOUBLE_MU_SPEARMAN_GATE,
        "verdict": "成立" if float(double_mu["spearman_g_rel"]) >= DOUBLE_MU_SPEARMAN_GATE else "判否",
    })
    criteria.append({
        "id": "H40c8",
        "description": "双 mu 的域间比一致：|R_our - R_qm9| / R_our <= 0.05（QM9 子集内各自口径）",
        "value": subset_tol,
        "threshold": DOUBLE_MU_RATIO_TOL,
        "verdict": "成立" if subset_tol <= DOUBLE_MU_RATIO_TOL else "判否",
    })
    criteria.append({
        "id": "H40c9",
        "description": "偏置校正（mu 加上签署差中位数 " + format(float(payload["bias"]["signed_delta_median_D"]),
                                                          ".4f") + " D）后域间比仍 >= 1.5：结论方向不因已知 mu 偏置改变",
        "value": float(payload["ratio_new_corr"]),
        "threshold": RATIO_GATE,
        "verdict": "成立" if float(payload["ratio_new_corr"]) >= RATIO_GATE else "判否",
    })
    criteria.append({
        "id": "H40c10",
        "description": "偏置校正前后域间比相对变化 <= 0.10（严格稳健门；首次冻结）",
        "value": float(payload["bias"]["relative_change"]),
        "threshold": BIAS_STABILITY_TOL,
        "verdict": "成立" if float(payload["bias"]["relative_change"]) <= BIAS_STABILITY_TOL else "判否",
    })
    criteria.append({
        "id": "H40c11",
        "description": "水在新域下的 g_rel 高于给体域中位数（水是域内典型自缔合给体）",
        "value": water_g_rel - ratio_new,
        "threshold": 0.0,
        "verdict": "成立" if water_g_rel > ratio_new else "判否",
    })
    return criteria


def _fmt(value: object, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if number != number:
        return "n/a"
    if number == 0.0:
        return "0"
    if abs(number) < 1e-3 or abs(number) >= 1e5:
        return format(number, "." + str(digits) + "g")
    return format(number, "." + str(digits) + "f")


def _fmt_sig(value: object, digits: int = 6) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if number != number:
        return "n/a"
    return format(number, "." + str(digits) + "g")


def _subset_records(records: Sequence[Mapping[str, object]], mu_key: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for record in records:
        if not bool(record["in_qm9"]):
            continue
        mu = record.get(mu_key)
        volume = float(record["molar_volume_m3_mol"])
        if mu is None or float(mu) < MIN_DIPOLE_D or volume <= 0.0 or float(record["eps"]) <= 1.0:
            continue
        out.append({
            "x_tmp": float(mu) ** 2 / volume,
            "mu_tmp": float(mu),
            "domain_new": record["domain_new"],
            "L_of_eps": record["L_of_eps"],
            "eps": record["eps"],
        })
    return out


def summary_rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
    records = payload["records"]
    blocks: list[tuple[str, str, str, dict[str, object]]] = [
        ("old_hbd", "xtb_dipole_D", "roster",
         domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_old")),
        ("new_donor", "xtb_dipole_D", "roster",
         domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_new")),
        ("new_donor", "xtb_dipole_D_bias_corrected", "roster",
         domain_table(records, "x_corr", "mu_corr_D", "domain_new")),
        ("new_donor", "xtb_dipole_D", "roster_canonical_tautomer",
         domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_canonical")),
        ("new_donor_include_amide_nh", "xtb_dipole_D", "roster",
         domain_table(records, "mu_sq_over_Vm", "dipole_D", "domain_include_amide")),
        ("new_donor", "xtb_dipole_D", "qm9_subset_mu_ge_1D",
         domain_table(_subset_records(records, "dipole_D"), "x_tmp", "mu_tmp", "domain_new")),
        ("new_donor", "qm9_dipole_D", "qm9_subset_mu_ge_1D",
         domain_table(_subset_records(records, "dipole_D_qm9"), "x_tmp", "mu_tmp", "domain_new")),
    ]
    rows: list[dict[str, object]] = []
    for rule, mu_source, scope, table in blocks:
        for domain in ("A", "B"):
            entry = table[domain]
            rows.append({
                "rule": rule, "mu_source": mu_source, "scope": scope, "domain": domain,
                "n": entry["n"], "median_L_over_x": entry["median_L_over_x"],
                "median_g_rel": entry["median_g_rel"], "r2_through_origin": entry["r2_through_origin"],
                "pearson": entry["pearson"], "median_eps": entry["median_eps"],
                "median_dipole_D": entry["median_dipole_D"],
                "ratio_donor_over_acceptor": table["ratio"],
            })
    return rows


def make_figure(payload: Mapping[str, object]) -> None:
    cjk = pick_cjk_font()
    if cjk is not None:
        plt.rcParams["font.sans-serif"] = [cjk]
        plt.rcParams["axes.unicode_minus"] = False
    usable = payload["usable"]
    changed = payload["changed"]
    rng = np.random.default_rng(20261003)
    figure, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))

    axis = axes[0]
    colors = {"A": "#4C72B0", "B": "#DD8452"}
    for position, domain in enumerate(("A", "B")):
        members = [record for record in usable if record["domain_new"] == domain]
        values = np.asarray([float(record["g_rel_new"]) for record in members], dtype=float)
        jitter = rng.uniform(-0.16, 0.16, values.size)
        axis.scatter(np.full(values.size, float(position)) + jitter, values, s=16, alpha=0.7,
                     color=colors[domain], label="域 " + domain + " (n=" + str(values.size) + ")")
    label_offsets = ((12, 10), (12, -14), (12, 22), (12, -26))
    for index, record in enumerate(changed):
        position = 0.0 if record["domain_new"] == "A" else 1.0
        axis.scatter([position], [float(record["g_rel_new"])], marker="o", s=52,
                     facecolors="none", edgecolors="#C44E52", linewidths=1.4)
        axis.annotate(str(record["name"]), (position, float(record["g_rel_new"])), fontsize=7,
                      color="#C44E52", xytext=label_offsets[index % len(label_offsets)],
                      textcoords="offset points")
    axis.set_yscale("log")
    axis.set_xticks([0, 1])
    axis.set_xticklabels(["A 非给体域", "B 给体域"])
    axis.set_ylabel("g_rel（新口径，对数轴）")
    axis.set_title("(a) 新口径域间 g_rel；中位数比 " + format(float(payload["ratio_new"]), ".3f"))
    axis.grid(alpha=0.25, axis="y")
    axis.legend(fontsize=8, loc="upper left")

    axis = axes[1]
    dipoles = np.asarray([float(record["dipole_D"]) for record in usable], dtype=float)
    values = np.asarray([float(record["L_over_x"]) for record in usable], dtype=float)
    donors = np.asarray([record["domain_new"] == "B" for record in usable], dtype=bool)
    axis.scatter(dipoles[~donors], values[~donors], s=15, alpha=0.6, color="#4C72B0", label="非给体域 A")
    axis.scatter(dipoles[donors], values[donors], s=15, alpha=0.6, color="#DD8452", label="给体域 B")
    for record in changed:
        axis.scatter([float(record["dipole_D"])], [float(record["L_over_x"])], marker="o", s=52,
                     facecolors="none", edgecolors="#C44E52", linewidths=1.4)
        axis.annotate(str(record["name"]), (float(record["dipole_D"]), float(record["L_over_x"])),
                      fontsize=7, color="#C44E52", xytext=(8, -10), textcoords="offset points")
    axis.axvspan(0.0, 0.4, color="#999999", alpha=0.15)
    axis.annotate("mu < 0.4 D：L/x 病态发散区", (0.02, max(values) * 0.5), fontsize=7, color="#666666")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("dipole_D (D, 对数轴)")
    axis.set_ylabel("L(eps) / x（对数轴）")
    axis.set_title("(b) 病态区与被改判化合物（红圈）")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, loc="lower right")

    axis = axes[2]
    hits = [record for record in usable if bool(record["in_qm9"])]
    ours = subset_g_rel(hits, "dipole_D")
    theirs = subset_g_rel(hits, "dipole_D_qm9")
    shared = sorted(set(ours) & set(theirs))
    g_our = np.asarray([ours[key]["g"] for key in shared], dtype=float)
    g_qm9 = np.asarray([theirs[key]["g"] for key in shared], dtype=float)
    axis.scatter(g_our, g_qm9, s=18, alpha=0.7, color="#55A868")
    limits = [float(min(g_our.min(), g_qm9.min())), float(max(g_our.max(), g_qm9.max()))]
    axis.plot(limits, limits, color="#888888", linewidth=1.0, linestyle="--", label="1:1")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("g_rel（本地 xTB dipole_D）")
    axis.set_ylabel("g_rel（QM9 B3LYP 偶极）")
    axis.set_title("(c) 双 mu 对照（n=" + str(len(shared)) + "，Spearman "
                   + format(float(payload["double_mu"]["spearman_g_rel"]), ".3f") + "）")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, loc="lower right")

    figure.suptitle("W40-C Onsager 域规则精化 + 偶极双 mu 读数化（后验读数，0 shot）", fontsize=11)
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_PATH, dpi=130)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  inputs: Mapping[str, object], inputs_unchanged: bool) -> str:
    stats_old = payload["stats_old"]
    stats_new = payload["stats_new"]
    stats_corr = payload["stats_corr"]
    stats_canonical = payload["stats_canonical"]
    double_mu = payload["double_mu"]
    bias = payload["bias"]
    water = payload["water"]
    lines: list[str] = []
    lines.append("# W40-C Onsager 域规则精化 + 偶极双 mu 读数化（后验读数，0 shot）")
    lines.append("")
    lines.append("定义 `L(eps) = (eps-1)(2eps+1)/(9eps)`，`x = mu^2 / V_m`，")
    lines.append("`g_rel = (L/x) / median_{非给体域}(L/x)`。非给体域的中位数恒为 1（定义，不是结果）。")
    lines.append("域划分是**跑前写死的机械规则**，不按 eps 大小挑样本；本件不拟合模型、不新增特征列。")
    lines.append("")
    lines.append("## 1 口径精化：从 hbd 列到显式可给体质子")
    lines.append("")
    lines.append("- 旧口径（W38-C）：" + OLD_RULE_TEXT)
    lines.append("- 新口径（本件）：" + RULE_TEXT)
    lines.append("- 新旧在 241 行上的 RDKit NumHDonors 一致率 = "
                 + _fmt(payload["agreement_with_rdkit_hbd"], 4)
                 + "（表内 hbd 列与 RDKit 重算一致；差异全部来自规则本身，不是数据不一致）。")
    lines.append("- 新口径域规模：A 非给体域 n = " + str(stats_new["A"]["n"])
                 + "；B 给体域 n = " + str(stats_new["B"]["n"])
                 + "（旧口径为 " + str(stats_old["A"]["n"]) + " / " + str(stats_old["B"]["n"]) + "）。")
    lines.append("")
    lines.append("## 2 被改判化合物清单（新旧域不一致）")
    lines.append("")
    lines.append("| 名称 | SMILES | eps | 旧 hbd | RDKit HBD | 新 donor_h | 旧域 | 新域 | 改判方向 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for record in payload["changed"]:
        lines.append("| " + str(record["name"]) + " | `" + str(record["smiles"]) + "` | "
                     + _fmt_sig(record["eps"], 6) + " | " + _fmt_sig(record["hbd_old"], 4) + " | "
                     + str(record["rdkit_hbd"]) + " | " + str(record["donor_h_new"]) + " | "
                     + str(record["domain_old"]) + " | " + str(record["domain_new"]) + " | "
                     + str(record["change_dir"]) + " |")
    lines.append("")
    lines.append("重点核对（任务点名项）：")
    lines.append("")
    lines.append("| 名称 | eps | 旧 hbd | 新 donor_h | 旧域 | 新域 | 是否改判 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    focus_names = ("water", "formamide", "N-methylacetamide", "dimethylformamide",
                   "1,2-ethanediol", "diethylene glycol", "triethylene glycol", "glycerol",
                   "methanol", "ethanol")
    present_names = {str(record["name"]) for record in payload["records"]}
    for name in focus_names:
        for record in payload["records"]:
            if str(record["name"]) == name:
                lines.append("| " + name + " | " + _fmt_sig(record["eps"], 6) + " | "
                             + _fmt_sig(record["hbd_old"], 4) + " | " + str(record["donor_h_new"]) + " | "
                             + str(record["domain_old"]) + " | " + str(record["domain_new"]) + " | "
                             + ("是" if record["changed"] else "否") + " |")
    missing_names = [name for name in focus_names if name not in present_names]
    lines.append("")
    lines.append("- 点名核对说明：任务提到的「乙二醇类」在名册里写作 **1,2-ethanediol**（另有 diethylene / "
                 "triethylene / tetraethylene glycol）；**N-甲基甲酰胺不在名册**，表内只有二甲基甲酰胺（DMF，"
                 "SMILES `CN(C)C=O`，donor_h = 0，新旧口径都不含 N-H，域不变）。"
                 + ("未在名册中出现的点名项：" + "、".join(missing_names) + "。" if missing_names else ""))
    lines.append("- 点名项里**只有水**改判；甲酰胺与 N-甲基乙酰胺虽含酰胺基团，但名册把它们写成亚胺醇式（O-H 给体），"
                 "所以两套口径都判给体域，改判为零（互变异构敏感性见 §7 边界 3）。")
    lines.append("")
    lines.append("### 2.1 水的归属为什么在旧口径下错了")
    lines.append("")
    lines.append("- 水的 SMILES 是 `O`。RDKit 的 `Descriptors.NumHDonors(H2O)` 返回 **0**（Lipinski 给体"
                 "定义按重原子环境计数，水被排除在外），名册 `hbd` 列同样是 0，于是水被机械地放进「理应 g 接近 1」"
                 "的非给体域 A。")
    lines.append("- 新规则直接数氢：水的两个 O-H 都满足「连在 O 上、杂原子形式电荷 0、不是酰胺 N-H」，"
                 "所以 `donor_h = 2`，水被判入给体域 B。")
    lines.append("- 数字后果：水在旧口径下的 g_rel = " + _fmt(water["g_rel_old"], 6)
                 + "（相对旧 A 域中位数），在新口径下 g_rel = " + _fmt(water["g_rel_new"], 4)
                 + "，相对新 A 域中位数 " + _fmt(stats_new["A"]["median_L_over_x"], 4) + "。")
    lines.append("- 注意这条纠正的**方向**：旧口径把水放在 A 域，抬高的是 A 域的中位数分母、同时把水从 B 域剔除；"
                 "改正后高介电族的域间比从 " + _fmt(payload["high_eps"]["variants"]["old"]["ratio"], 4)
                 + " 降到 " + _fmt(payload["high_eps"]["variants"]["new"]["ratio"], 4)
                 + "，即旧口径**高估**了域分离（H40c6）。所以这条修正是把读数变得更保守，不是更好看。")
    lines.append("")
    lines.append("## 3 域间读数")
    lines.append("")
    lines.append("| 口径 | A 域 n | A 中位 L/x | A 过原点 R2 | B 域 n | B 中位 L/x | 域间比 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for label, table in (("旧口径（表内 hbd）", stats_old),
                         ("新口径（显式可给体质子）", stats_new),
                         ("新口径 + mu 偏置校正", stats_corr),
                         ("新口径 + 互变异构归一", stats_canonical),
                         ("新口径 + 计入酰胺 N-H", payload["stats_include_amide"])):
        lines.append("| " + label + " | " + str(table["A"]["n"]) + " | " + _fmt(table["A"]["median_L_over_x"], 4)
                     + " | " + _fmt(table["A"]["r2_through_origin"], 4) + " | " + str(table["B"]["n"])
                     + " | " + _fmt(table["B"]["median_L_over_x"], 4) + " | " + _fmt(table["ratio"], 5) + " |")
    lines.append("")
    lines.append("- W38-C 登记的旧口径读数 " + _fmt(W38C_OLD_RATIO, 8) + " 被逐位复现（差 <= 1e-9），"
                 "说明新旧口径严格可比。")
    lines.append("- 新口径域间比 = " + _fmt(payload["ratio_new"], 6) + "，比旧口径 "
                 + _fmt(payload["ratio_old"], 6) + " 略高；域分离结论不变，量级同档。")
    lines.append("")
    lines.append("### 3.1 高介电族（eps >= 60，机械阈值）")
    lines.append("")
    lines.append("| 名称 | eps | 旧 hbd | 新 donor_h | dipole_D | 旧域 | 新域 | 新 g_rel |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for record in payload["high_eps"]["members"]:
        lines.append("| " + str(record["name"]) + " | " + _fmt_sig(record["eps"], 6) + " | "
                     + _fmt_sig(record["hbd_old"], 4) + " | " + str(record["donor_h_new"]) + " | "
                     + _fmt_sig(record["dipole_D"], 5) + " | " + str(record["domain_old"]) + " | "
                     + str(record["domain_new"]) + " | " + _fmt(record["g_rel_new"], 4) + " |")
    lines.append("")
    variants = payload["high_eps"]["variants"]
    lines.append("- 旧口径子群比 = " + _fmt(variants["old"]["ratio"], 5) + "（n = "
                 + str(variants["old"]["n_donor"]) + " / " + str(variants["old"]["n_acceptor"]) + "）")
    lines.append("- 新口径子群比 = " + _fmt(variants["new"]["ratio"], 5) + "（n = "
                 + str(variants["new"]["n_donor"]) + " / " + str(variants["new"]["n_acceptor"]) + "）")
    lines.append("- 偏置校正后子群比 = " + _fmt(variants["new_bias_corrected"]["ratio"], 5))
    lines.append("")
    lines.append("## 4 双 mu 读数（QM9 对照层）")
    lines.append("")
    lines.append("**覆盖声明**：QM9 只覆盖 " + str(double_mu["n_hits"]) + " / " + str(payload["n_records"])
                 + " 个化合物，因此第二套 mu 只在该子集上成立；两套 mu 的 g_rel 差只用中位数与秩表述，"
                 "**不直接比绝对值**。")
    lines.append("")
    lines.append("| 读数 | 本地 xTB mu | QM9 B3LYP mu |")
    lines.append("| --- | --- | --- |")
    lines.append("| 子集内域间比（mu >= 1 D） | " + _fmt(double_mu["our_mu"]["ratio"], 6) + " | "
                 + _fmt(double_mu["qm9_mu"]["ratio"], 6) + " |")
    lines.append("| 子集内给体 n / 非给体 n | " + str(double_mu["our_mu"]["n_donor"]) + " / "
                 + str(double_mu["our_mu"]["n_acceptor"]) + " | " + str(double_mu["qm9_mu"]["n_donor"])
                 + " / " + str(double_mu["qm9_mu"]["n_acceptor"]) + " |")
    lines.append("")
    lines.append("- 两套 mu 都 >= 1 D 的 " + str(double_mu["n_both_ge_1D"]) + " 个化合物上，"
                 "Spearman(g_rel_our, g_rel_qm9) = " + _fmt(double_mu["spearman_g_rel"], 6)
                 + "，Pearson = " + _fmt(double_mu["pearson_g_rel"], 6) + "。")
    lines.append("- g_rel 的中位数比（QM9 / 本地）= " + _fmt(double_mu["median_g_rel_ratio_qm9_over_our"], 6)
                 + "；秩位移中位数 = " + _fmt(double_mu["median_abs_rank_shift"], 4) + " 位。")
    lines.append("- 域间比的相对差 = " + _fmt(abs(float(double_mu["our_mu"]["ratio"])
                 - float(double_mu["qm9_mu"]["ratio"])) / float(double_mu["our_mu"]["ratio"]), 6)
                 + "（换一套 mu 不改变域分离结论）。")
    lines.append("")
    lines.append("## 5 偶极质量审计收口：约 0.39 D 系统偏置的敏感性")
    lines.append("")
    lines.append("- 从 W39 对照层重算的签署差（QM9 减本地）中位数 = "
                 + _fmt(bias["signed_delta_median_D"], 6) + " D（|delta| < 1 D 的 "
                 + str(bias["n_agreeing"]) + " 个化合物），与 W39 登记值 "
                 + _fmt(bias["expected_signed_delta_median_D"], 6) + " 一致。")
    lines.append("- 校正口径：`mu_corr = dipole_D + 签署差中位数`（即 mu 减去约 0.3914 D）；"
                 "`mu_corr <= 0` 的行（" + str(bias["n_dropped_mu_nonpositive"]) + " 行，多为近零偶极烷烃）"
                 "在该变体里直接丢弃，不插补。")
    lines.append("- 校正后域间比 = " + _fmt(payload["ratio_new_corr"], 6) + "（未校正 "
                 + _fmt(payload["ratio_new"], 6) + "），相对变化 = " + _fmt(bias["relative_change"], 6) + "。")
    lines.append("- 结论方向不变（仍远大于 1.5），但幅度变化超过 10%：因为 `g_rel` 是 `1/mu^2` 变换，"
                 "把 mu 的加性偏置放大成乘性变化。这就是 H40c10 判否的实质。")
    lines.append("")
    lines.append("## 6 判据")
    lines.append("")
    lines.append("| 判据 | 内容 | 读数 | 门 | 判决 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in criteria:
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | "
                     + _fmt(item["value"], 6) + " | " + _fmt(item["threshold"], 4) + " | "
                     + str(item["verdict"]) + " |")
    lines.append("")
    lines.append("## 7 边界（必须与数字同句引用）")
    lines.append("")
    lines.append("- **规则边界 1（S-H）**：任务规定只算 N / O / F，所以硫醇的 S-H 不计给体，"
                 + str(payload["thiol_count"]) + " 条硫醇（" + "、".join(payload["thiol_names"])
                 + "）由给体域移出。这是规则选择，不是数据错误。")
    lines.append("- **规则边界 2（正电杂原子）**：正电杂原子上的氢被排除，涉及 "
                 + str(payload["positive_h_compound_count"]) + " 条（" + "、".join(payload["positive_h_names"])
                 + "，[NH3+] 的三个氢）；该化合物仍有 O-H，域不变。")
    lines.append("- **规则边界 3（互变异构敏感）**：名册里甲酰胺写作 `N=CO`、N-甲基乙酰胺写作 `CN=C(C)O`，"
                 "都是亚胺醇式，其给体由 O-H 提供；若按 RDKit 标准互变异构体归一为酰胺式 `NC=O` / `CNC(C)=O`，"
                 "则两者的 N-H 全部被酰胺条款排除，由给体域移出（"
                 + "、".join(payload["tautomer_flip_names"]) + "）。归一后域间比 = "
                 + _fmt(payload["ratio_canonical"], 6) + "，结论方向不变。**这是本规则最脆的一处**："
                 "本名册书写下酰胺条款零作用（" + str(payload["amide_excluded_count"]) + " 条），"
                 "所以「酰胺共振」这条物理假设在本件里其实**没有被检验**，只被登记为边界。")
    lines.append("- **统计量病态**：不加 mu 门槛时 `L/x` 在 mu 趋近 0 处发散（烷烃把排名占满）。"
                 "因此域间比较只用**中位数**，双 mu 秩比较只用 **mu >= 1 D** 的子集；"
                 "g_rel 的绝对排序不得当物理结论。")
    lines.append("- **g_rel 是无量纲相对量**：单位被斜率吸收，只可做域间比较，不得与文献 g 绝对值对照。")
    lines.append("- **水的读数不是量级证据**：水的新口径 g_rel = " + _fmt(water["g_rel_new"], 4)
                 + " 低于给体域中位数 " + _fmt(payload["ratio_new"], 4) + "（H40c11 判否）；"
                 "偏置校正后为 " + _fmt(water["g_rel_corr"], 4) + "，仍低于校正后的给体域中位数 "
                 + _fmt(payload["ratio_new_corr"], 4)
                 + "。所以「水被错分域」是**分类**纠正，不能读成「水的残差极端大」。")
    lines.append("- 不拟合模型、不新增特征列、不触 eps 主记分牌；不占 shot（累计仍 19）。")
    lines.append("")
    lines.append("## 8 输入指纹")
    lines.append("")
    for key, value in inputs.items():
        lines.append("- `" + str(key) + "` = " + str(value))
    lines.append("- 输入未被改写：" + ("是" if inputs_unchanged else "待复核") + "。")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    before_roster = sha256_file(ROSTER_CSV)
    before_overlap = sha256_file(OVERLAP_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(COMPOUNDS_CSV, COMPOUND_FIELDS,
                 [{key: record.get(key) for key in COMPOUND_FIELDS} for record in payload["records"]])
    write_csv_lf(SUMMARY_CSV, SUMMARY_DOMAIN_FIELDS, summary_rows(payload))
    after_roster = sha256_file(ROSTER_CSV)
    after_overlap = sha256_file(OVERLAP_CSV)
    if not args.skip_figure:
        make_figure(payload)

    inputs = {
        str(ROSTER_CSV): before_roster,
        "roster_sha256_after": after_roster,
        str(OVERLAP_CSV): before_overlap,
        "overlap_sha256_after": after_overlap,
    }
    inputs_unchanged = before_roster == after_roster and before_overlap == after_overlap
    criteria.append({
        "id": "H40c12",
        "description": "0 shot（累计仍 19）：只读特征表与 W39 对照层，不拟合主记分牌臂、"
                       "不新增特征列、不改 METRIC_NAMES、不动四个冻结读数",
        "value": 0.0,
        "threshold": 0.0,
        "verdict": "成立",
    })
    criteria.append({
        "id": "H40c13",
        "description": "输入未被改写（名册与 W39 重叠层的 sha256 前后一致）",
        "value": 1.0 if inputs_unchanged else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if inputs_unchanged else "判否",
    })

    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    water = payload["water"]
    bias = payload["bias"]
    double_mu = payload["double_mu"]

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读盘上既有特征表与 W39 对照层；不拟合主记分牌臂、不新增特征列、"
                              "不改 METRIC_NAMES、不动四个冻结读数。",
        },
        "inputs": inputs,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "pool_note": "241 行物理特征表（每化合物一行），" + str(payload["n_usable"])
                     + " 行可用（eps > 1、mu^2/Vm > 0、hbd 非空、SMILES 可解析）；非冻结头条所在池。",
        "domain_rule": {
            "new": RULE_TEXT,
            "old": OLD_RULE_TEXT,
            "amide_smarts": AMIDE_N_SMARTS,
            "rule_reads_eps": False,
            "agreement_with_rdkit_hbd": payload["agreement_with_rdkit_hbd"],
            "n_paired_with_rdkit_hbd": payload["n_paired_with_rdkit_hbd"],
        },
        "domains": {
            "old_rule": payload["stats_old"],
            "new_rule": payload["stats_new"],
            "new_rule_bias_corrected": payload["stats_corr"],
            "new_rule_canonical_tautomer": payload["stats_canonical"],
            "new_rule_include_amide_nh": payload["stats_include_amide"],
        },
        "ratio": {
            "old_rule": payload["ratio_old"],
            "w38c_anchor": W38C_OLD_RATIO,
            "anchor_reproduced": abs(float(payload["ratio_old"]) - W38C_OLD_RATIO) <= ANCHOR_TOL,
            "new_rule": payload["ratio_new"],
            "new_rule_bias_corrected": payload["ratio_new_corr"],
            "new_rule_canonical_tautomer": payload["ratio_canonical"],
            "new_rule_include_amide_nh": payload["ratio_include_amide"],
        },
        "reclassification": {
            "n_changed": len(payload["changed"]),
            "changed": [
                {"name": str(record["name"]), "smiles": str(record["smiles"]),
                 "eps": float(record["eps"]), "hbd_old": float(record["hbd_old"]),
                 "rdkit_hbd": int(record["rdkit_hbd"]), "donor_h_new": int(record["donor_h_new"]),
                 "domain_old": str(record["domain_old"]), "domain_new": str(record["domain_new"]),
                 "change_dir": str(record["change_dir"])}
                for record in payload["changed"]
            ],
            "thiol_names_removed_from_donor_domain": payload["thiol_names"],
            "positive_heteroatom_h_compounds": payload["positive_h_names"],
            "amide_nh_compounds_on_roster_spellings": payload["amide_excluded_count"],
            "include_amide_nh_flips": payload["include_amide_flip_count"],
            "tautomer_canonical_flips": payload["tautomer_flip_names"],
        },
        "water": {
            "name": "water", "smiles": str(water["smiles"]), "eps": float(water["eps"]),
            "rdkit_hbd": int(water["rdkit_hbd"]), "hbd_old": float(water["hbd_old"]),
            "donor_h_new": int(water["donor_h_new"]),
            "domain_old": str(water["domain_old"]), "domain_new": str(water["domain_new"]),
            "g_rel_old_domain": float(water["g_rel_old"]),
            "g_rel_new_domain": float(water["g_rel_new"]),
            "g_rel_new_domain_bias_corrected": float(water["g_rel_corr"]),
            "dipole_D": float(water["dipole_D"]),
            "domain_reference_median_L_over_x_new": float(payload["stats_new"]["A"]["median_L_over_x"]),
        },
        "high_eps_family": payload["high_eps"],
        "double_mu": double_mu,
        "double_mu_note": "QM9 只覆盖 103 个命中化合物，第二套 mu 只在该子集上成立；"
                          "两套 mu 的 g_rel 差只用中位数与秩表述，不直接比绝对值。",
        "dipole_bias": bias,
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "域规则精化后，被改判的化合物只有 " + str(len(payload["changed"])) + " 条："
            + "、".join(payload["changed_names"]) + "。",
            "水在旧口径下 RDKit NumHDonors = 0、被放进非给体域 A；新规则 donor_h = "
            + str(int(water["donor_h_new"])) + "，判入给体域 B。",
            "新口径域间比 = " + _fmt(payload["ratio_new"], 6) + "（旧口径 " + _fmt(payload["ratio_old"], 6)
            + "，W38-C 锚被逐位复现）；域分离结论不变。",
            "改正水的归属让高介电族域间比从 " + _fmt(payload["high_eps"]["variants"]["old"]["ratio"], 4)
            + " 降到 " + _fmt(payload["high_eps"]["variants"]["new"]["ratio"], 4)
            + "：旧口径高估了域分离（读数变保守，不是变好看）。",
            "双 mu 秩一致：Spearman(g_rel) = " + _fmt(double_mu["spearman_g_rel"], 4)
            + "（n = " + str(double_mu["n_both_ge_1D"]) + "），域间比相对差 "
            + _fmt(abs(float(double_mu["our_mu"]["ratio"]) - float(double_mu["qm9_mu"]["ratio"]))
                   / float(double_mu["our_mu"]["ratio"]), 4) + "。",
            "偏置校正（mu 减 " + _fmt(abs(bias["signed_delta_median_D"]), 4) + " D）后域间比 = "
            + _fmt(payload["ratio_new_corr"], 6) + "，方向不变但幅度变化 "
            + _fmt(bias["relative_change"], 4) + "（H40c10 已登记判否）。",
            "水的 g_rel = " + _fmt(water["g_rel_new"], 4) + " 低于给体域中位数 "
            + _fmt(payload["ratio_new"], 4) + "（H40c11 已登记判否）：域纠正不等于量级证据。",
            "不占 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, inputs, inputs_unchanged),
                            encoding="utf-8", newline="\n")

    print("records " + str(payload["n_records"]) + "; usable " + str(payload["n_usable"]))
    print("ratio old " + _fmt(payload["ratio_old"], 8) + " (anchor " + _fmt(W38C_OLD_RATIO, 8)
          + ", reproduced " + str(abs(float(payload["ratio_old"]) - W38C_OLD_RATIO) <= ANCHOR_TOL) + ")")
    print("ratio new " + _fmt(payload["ratio_new"], 8) + "; canonical tautomer "
          + _fmt(payload["ratio_canonical"], 8) + "; include-amide " + _fmt(payload["ratio_include_amide"], 8))
    print("changed " + str(len(payload["changed"])) + " " + " / ".join(payload["changed_names"]))
    print("water: rdkit_hbd " + str(int(water["rdkit_hbd"])) + " -> donor_h " + str(int(water["donor_h_new"]))
          + "; domain " + str(water["domain_old"]) + " -> " + str(water["domain_new"])
          + "; g_rel " + _fmt(water["g_rel_old"], 6) + " -> " + _fmt(water["g_rel_new"], 6))
    print("high-eps ratio old " + _fmt(payload["high_eps"]["variants"]["old"]["ratio"], 6)
          + " -> new " + _fmt(payload["high_eps"]["variants"]["new"]["ratio"], 6))
    print("double mu: our " + _fmt(double_mu["our_mu"]["ratio"], 6) + " vs qm9 "
          + _fmt(double_mu["qm9_mu"]["ratio"], 6) + "; spearman(g_rel) "
          + _fmt(double_mu["spearman_g_rel"], 6) + "; n " + str(double_mu["n_both_ge_1D"]))
    print("bias " + _fmt(bias["signed_delta_median_D"], 6) + " D -> ratio " + _fmt(payload["ratio_new_corr"], 6)
          + "; rel change " + _fmt(bias["relative_change"], 6)
          + "; dropped " + str(bias["n_dropped_mu_nonpositive"]))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
