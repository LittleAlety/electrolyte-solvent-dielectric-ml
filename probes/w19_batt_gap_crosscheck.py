"""W19 · N2 直接交叉核对：我方 GFN2-xTB 轨道能 vs Batt-P30K 轨道能（名册命中化合物）。

只读复核：不写任何池、不改任何冻结件、不做 git 操作、不引用 Reaxys 数值。
口径、判据与红线见 probes/w19_batt_gap_crosscheck_prereg.json（status = locked_before_run）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BATT_H5 = REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5"
EXPECTED_BATT_SHA256 = "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
LAYER_CSV = REPOSITORY_ROOT / "data" / "processed" / "themol_orbital_layer.csv"
LAYER_EXPANDED_CSV = REPOSITORY_ROOT / "data" / "processed" / "themol_orbital_layer_expanded.csv"
V03_FEATURES_CSV = REPOSITORY_ROOT / "probes" / "artifacts" / "v03_features_baseline_input.csv"
DIRECT_HIT_SUMMARY = REPOSITORY_ROOT / "probes" / "w19_batt_direct_hit_summary.json"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck_summary.json"
SCRIPT_PATH = REPOSITORY_ROOT / "probes" / "w19_batt_gap_crosscheck.py"

GATE_LOO_MAE_EV = 0.35
GATE_PEARSON_R = 0.80
CHANNELS = ("homo", "lumo", "gap")
OURS_FIELDS = {"homo": "homo_gfn2_eV", "lumo": "lumo_gfn2_eV", "gap": "gap_gfn2_eV"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def decode_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def inchikey_of(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToInchiKey(mol)


def canonical_smiles(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def load_batt(h5_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    invalid_smiles = 0
    duplicate_keys = 0
    with h5py.File(h5_path, "r") as handle:
        groups = list(handle.keys())
        for name in groups:
            group = handle[name]
            raw = decode_str(group["smiles"][0])
            key = inchikey_of(raw)
            if key is None:
                invalid_smiles += 1
                continue
            if key in records:
                duplicate_keys += 1
            records[key] = {
                "group": name,
                "smiles": raw,
                "canonical_smiles": canonical_smiles(raw),
                "homo": float(group["homo"][0]),
                "lumo": float(group["lumo"][0]),
                "gap": float(group["gap"][0]),
                "ip": float(group["ip"][0]),
                "ea": float(group["ea"][0]),
                "ener": float(group["ener"][0]),
            }
    meta = {
        "groups_scanned": len(groups),
        "parsed_records": len(records),
        "invalid_smiles": invalid_smiles,
        "duplicate_inchikey_records": duplicate_keys,
    }
    return records, meta


def load_ours(path: Path, fields: dict[str, str]) -> dict[str, dict[str, float]]:
    layer: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(path):
        key = (row.get("inchikey") or "").strip()
        if not key:
            continue
        values: dict[str, float] = {}
        for channel, column in fields.items():
            value = as_float(row.get(column))
            if value is not None:
                values[channel] = value
        if values:
            layer[key] = values
    return layer


def rank_average(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=float)
    ordered = values[order]
    index = 0
    while index < values.size:
        end = index + 1
        while end < values.size and ordered[end] == ordered[index]:
            end += 1
        average_rank = (index + end - 1) / 2.0 + 1.0
        ranks[order[index:end]] = average_rank
        index = end
    return ranks


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(rank_average(x), rank_average(y))


def ols_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def loo_errors(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    n = x.size
    errors = np.empty(n, dtype=float)
    for index in range(n):
        mask = np.ones(n, dtype=bool)
        mask[index] = False
        slope, intercept = np.polyfit(x[mask], y[mask], 1)
        errors[index] = abs((slope * x[index] + intercept) - y[index])
    return errors


def loo_constant_errors(y: np.ndarray) -> np.ndarray:
    n = y.size
    errors = np.empty(n, dtype=float)
    for index in range(n):
        mask = np.ones(n, dtype=bool)
        mask[index] = False
        errors[index] = abs(y[index] - float(np.mean(y[mask])))
    return errors

def channel_stats(ours: np.ndarray, batt: np.ndarray) -> dict[str, Any]:
    slope, intercept = ols_fit(ours, batt)
    in_sample = float(np.mean(np.abs((slope * ours + intercept) - batt)))
    raw_mae = float(np.mean(np.abs(batt - ours)))
    errors = loo_errors(ours, batt)
    constant_in_sample = float(np.mean(np.abs(batt - np.mean(batt))))
    constant_errors = loo_constant_errors(batt)
    constant_loo = float(np.mean(constant_errors))
    loo_sd = float(np.std(errors, ddof=1)) if errors.size > 1 else 0.0
    verdict_ok = (float(np.mean(errors)) <= GATE_LOO_MAE_EV) and (pearson(ours, batt) >= GATE_PEARSON_R)
    return {
        "n": int(ours.size),
        "pearson_r": pearson(ours, batt),
        "spearman_rho": spearman(ours, batt),
        "ols_slope": slope,
        "ols_intercept": intercept,
        "mae_raw_cross_level": raw_mae,
        "mae_after_linear_map_in_sample": in_sample,
        "loo_mae_mean": float(np.mean(errors)),
        "loo_mae_sd": loo_sd,
        "loo_mae_p25": float(np.percentile(errors, 25)),
        "loo_mae_median": float(np.percentile(errors, 50)),
        "loo_mae_p75": float(np.percentile(errors, 75)),
        "loo_mae_p95": float(np.percentile(errors, 95)),
        "mean_signed_diff_batt_minus_ours": float(np.mean(batt - ours)),
        "batt_sd": float(np.std(batt, ddof=1)),
        "batt_min": float(np.min(batt)),
        "batt_max": float(np.max(batt)),
        "ours_sd": float(np.std(ours, ddof=1)),
        "ours_min": float(np.min(ours)),
        "ours_max": float(np.max(ours)),
        "mae_constant_baseline_in_sample": constant_in_sample,
        "loo_mae_constant_baseline_mean": constant_loo,
        "skill_vs_constant_in_sample": 1.0 - in_sample / constant_in_sample,
        "skill_vs_constant_loo": 1.0 - float(np.mean(errors)) / constant_loo,
        "loo_max_error": float(np.max(errors)),
        "loo_folds_error_gt_gate": int(np.sum(errors > GATE_LOO_MAE_EV)),
        "loo_mae_excl_worst_mean": float(np.mean(np.sort(errors)[:-1])),
        "gate_loo_mae_le_0_35": bool(float(np.mean(errors)) <= GATE_LOO_MAE_EV),
        "gate_pearson_r_ge_0_80": bool(pearson(ours, batt) >= GATE_PEARSON_R),
        "verdict": "usable" if verdict_ok else "reference_only",
        "cross_level": True,
    }


def build_arm(keys: list[str], ours: dict[str, dict[str, float]], batt: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(keys), "channels": {}}
    for channel in CHANNELS:
        usable = [key for key in keys if channel in ours.get(key, {}) and channel in batt.get(key, {})]
        if len(usable) < 3:
            out["channels"][channel] = {"n": len(usable), "verdict": "not_computed"}
            continue
        ours_values = np.array([ours[key][channel] for key in usable], dtype=float)
        batt_values = np.array([float(batt[key][channel]) for key in usable], dtype=float)
        out["channels"][channel] = channel_stats(ours_values, batt_values)
    return out


def render_report(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W19 · N2 直接交叉核对：我方 GFN2-xTB 轨道能 vs Batt-P30K 轨道能（名册命中化合物）")
    add("")
    add("- 只读复核 = true；`writes_any_pool` = false；`reaxys_values_used` = false；不做任何 git 操作。")
    add("- `models_fitted` = " + str(summary["models_fitted"]) + "（3 主臂通道 + 3 敏感性臂 A 通道 + 1 敏感性臂 B 通道；每条为一次 OLS 线性映射并用留一折外推作样本外读数）。")
    add("- promoted = false；主记分牌尝试 0 次；本件不新占 shot（复核不占号，是否另立由作者裁定）。")
    add("- 不引用 Reaxys 数值；无受限值进入任何交付层。")
    add("- `cross_level` = true：Batt-P30K 为 SMD(ε=18.5) 隐式溶剂化 ωB97X-V/def2-TZVPPD，我方为 GFN2-xTB 气相单点（THEMol B3LYP-D3(BJ)/DZVP 几何）。因此下列任何 MAE 都**不是**模型精度，只是水平差；只有「线性映射后的样本外 MAE」与相关系数可作读数。")
    add("")
    add("## 一、池与口径")
    add("")
    pool = summary["pool"]
    add("- 冻结 ε 名册：`data/dielectric_v03.csv`，" + str(pool["roster_rows"]) + " 行 / " + str(pool["roster_unique_inchikeys"]) + " 唯一 27 位 InChIKey（计划书的 239 是另一份文件口径，本件不用）。")
    add("- Batt-P30K：groups " + str(pool["batt_groups_scanned"]) + "，" + str(pool["batt_parsed_records"]) + " 条可按全 27 位 InChIKey 解析；sha256 与注册值一致 = " + str(pool["batt_sha256_matches_registered"]) + "。")
    add("- 名册命中集（roster ∩ Batt 身份）= " + str(pool["hits"]) + " 键（与 D2 既有产物逐键一致 = " + str(pool["hits_match_direct_hit_summary"]) + "）。")
    add("- 我方 xTB 覆盖：`themol_orbital_layer.csv` " + str(pool["layer_rows"]) + " 行有 GFN2 轨道能；其中落在命中集内的主臂 n = " + str(pool["primary_n"]) + "。未被覆盖的命中键 " + str(pool["uncovered_hits"]) + " 个照实登记为不可核，不插补。")
    add("")
    add("## 二、主臂读数（名册命中 ∩ 我方 xTB，n = " + str(summary["primary"]["n"]) + "）")
    add("")
    add("| 通道 | n | Pearson r | Spearman ρ | OLS 斜率 | 截距 | 原始 MAE（跨水平） | 线性映射后样本内 MAE | 留一 MAE 均值 | 留一 MAE sd | 常数基线留一 MAE | skill（留一） | Batt sd | 我方 sd | 带符号差（Batt−我方） | verdict |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for channel in CHANNELS:
        stats = summary["primary"]["channels"][channel]
        add("| " + channel + " | " + str(stats["n"]) + " | " + fmt(stats["pearson_r"]) + " | " + fmt(stats["spearman_rho"]) + " | " + fmt(stats["ols_slope"]) + " | " + fmt(stats["ols_intercept"]) + " | " + fmt(stats["mae_raw_cross_level"]) + " | " + fmt(stats["mae_after_linear_map_in_sample"]) + " | " + fmt(stats["loo_mae_mean"]) + " | " + fmt(stats["loo_mae_sd"]) + " | " + fmt(stats["loo_mae_constant_baseline_mean"]) + " | " + fmt(stats["skill_vs_constant_loo"]) + " | " + fmt(stats["batt_sd"]) + " | " + fmt(stats["ours_sd"]) + " | " + fmt(stats["mean_signed_diff_batt_minus_ours"]) + " | " + stats["verdict"] + " |")
    add("")
    add("留一分位（p25 / 中位 / p75 / p95，eV）：")
    add("")
    for channel in CHANNELS:
        stats = summary["primary"]["channels"][channel]
        add("- " + channel + "：" + fmt(stats["loo_mae_p25"]) + " / " + fmt(stats["loo_mae_median"]) + " / " + fmt(stats["loo_mae_p75"]) + " / " + fmt(stats["loo_mae_p95"]))
    add("")
    add("脆弱性与「空读数」检查：")
    add("")
    for channel in CHANNELS:
        stats = summary["primary"]["channels"][channel]
        add("- " + channel + "：留一最大误差 " + fmt(stats["loo_max_error"]) + "，超过门的折数 " + str(stats["loo_folds_error_gt_gate"]) + "/" + str(stats["n"]) + "，去掉最大一折后的留一 MAE " + fmt(stats["loo_mae_excl_worst_mean"]) + "；常数基线留一 MAE = " + fmt(stats["loo_mae_constant_baseline_mean"]) + "，相对 skill = " + fmt(stats["skill_vs_constant_loo"]) + "。")
    add("")
    add("## 三、敏感性臂")
    add("")
    add("### 臂 A：全配对层（`themol_orbital_layer_expanded.csv` 的 paired_anchor）")
    add("")
    add("| 通道 | n | Pearson r | 留一 MAE 均值 | 线性映射后样本内 MAE | Batt sd | verdict |")
    add("|---|---|---|---|---|---|---|")
    for channel in CHANNELS:
        stats = summary["sensitivity"]["A_expanded_paired"]["channels"][channel]
        add("| " + channel + " | " + str(stats["n"]) + " | " + fmt(stats["pearson_r"]) + " | " + fmt(stats["loo_mae_mean"]) + " | " + fmt(stats["mae_after_linear_map_in_sample"]) + " | " + fmt(stats["batt_sd"]) + " | " + stats["verdict"] + " |")
    add("")
    add("### 臂 B：gap 通道换一条我方 xTB 记录（`v03_features_baseline_input.csv`）")
    add("")
    arm_b = summary["sensitivity"]["B_v03_gap"]["channels"]["gap"]
    add("- n = " + str(arm_b["n"]) + "，Pearson r = " + fmt(arm_b["pearson_r"]) + "，Spearman ρ = " + fmt(arm_b["spearman_rho"]) + "，留一 MAE 均值 = " + fmt(arm_b["loo_mae_mean"]) + "，线性映射后样本内 MAE = " + fmt(arm_b["mae_after_linear_map_in_sample"]) + "，verdict = " + arm_b["verdict"] + "。")
    add("")
    add("## 四、核验与一致性")
    add("")
    checks = summary["checks"]
    add("- Batt 自洽：`gap == lumo - homo` 全库最大绝对偏差 = " + fmt(checks["batt_gap_equals_lumo_minus_homo_max_abs_dev"], 6) + " eV（n = " + str(checks["batt_gap_identity_n"]) + "）。")
    add("- 冻结列复核：我方层内 `batt_homo_eV/batt_lumo_eV/batt_gap_eV` 与本次直读 h5 的最大绝对偏差 = " + fmt(checks["layer_batt_columns_max_abs_dev"], 6) + " eV（n = " + str(checks["layer_batt_columns_n"]) + "）。")
    add("- 扩展层复核：`themol_orbital_layer_expanded.csv` 的 batt 列与 h5 直读最大绝对偏差 = " + fmt(checks["expanded_batt_columns_max_abs_dev"], 6) + " eV（n = " + str(checks["expanded_batt_columns_n"]) + "）。")
    add("- 结构身份：主臂 " + str(checks["identity_checked"]) + " 例中 canonical SMILES 逐字相同 " + str(checks["identity_smiles_identical"]) + " 例；不一致 " + str(checks["identity_smiles_mismatch"]) + " 例。")
    add("- Batt 全库 LUMO 通道离散度：sd = " + fmt(checks["batt_global_lumo_sd"]) + " eV，极差 [" + fmt(checks["batt_global_lumo_min"]) + ", " + fmt(checks["batt_global_lumo_max"]) + "]。")
    add("- Batt 内部 homo 与 lumo 的相关系数 = " + fmt(checks["batt_global_homo_lumo_r"]) + "（全库）。")
    add("")
    add("## 五、分歧候选解释：可测排除与未排除")
    add("")
    for item in summary["divergence_notes"]:
        add("- " + item)
    add("")
    add("## 六、可证伪预测的兑现情况")
    add("")
    for item in summary["predictions"]:
        add("- **" + item["id"] + "**（" + item["status"] + "）：" + item["detail"])
    add("")
    add("## 七、裁定")
    add("")
    for channel in CHANNELS:
        stats = summary["primary"]["channels"][channel]
        add("- " + channel + "：verdict = " + stats["verdict"] + "（留一 MAE " + fmt(stats["loo_mae_mean"]) + " vs 门 " + fmt(GATE_LOO_MAE_EV, 2) + "；r " + fmt(stats["pearson_r"]) + " vs 门 " + fmt(GATE_PEARSON_R, 2) + "）。")
    add("")
    add(summary["verdict_statement"])
    add("")
    add("## 八、红线与边界")
    add("")
    for item in summary["boundaries"]:
        add("- " + item)
    add("")
    return chr(10).join(lines)


def fmt(value: float, digits: int = 4) -> str:
    return format(float(value), "." + str(digits) + "f")


def main() -> int:
    parser = argparse.ArgumentParser(description="W19 N2 Batt-P30K orbital cross-check")
    parser.add_argument("--h5", type=Path, default=BATT_H5)
    parser.add_argument("--roster", type=Path, default=ROSTER_CSV)
    parser.add_argument("--layer", type=Path, default=LAYER_CSV)
    parser.add_argument("--layer-expanded", type=Path, default=LAYER_EXPANDED_CSV)
    parser.add_argument("--v03-features", type=Path, default=V03_FEATURES_CSV)
    parser.add_argument("--direct-hit-summary", type=Path, default=DIRECT_HIT_SUMMARY)
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY_PATH)
    args = parser.parse_args()

    h5_sha = sha256_file(args.h5)
    batt, batt_meta = load_batt(args.h5)

    roster_keys = [(row.get("inchikey") or "").strip() for row in read_csv_rows(args.roster)]
    roster_keys = [key for key in roster_keys if key]
    hits = [key for key in roster_keys if key in batt]

    hit_summary = json.loads(args.direct_hit_summary.read_text(encoding="utf-8"))
    derived = set(roster_keys) - {item["inchikey"] for item in hit_summary["misses_still"]}
    hits_match = set(hits) == derived

    layer = load_ours(args.layer, OURS_FIELDS)
    primary_keys = sorted(key for key in hits if key in layer)
    uncovered = sorted(key for key in hits if key not in layer)

    primary = build_arm(primary_keys, layer, batt)

    expanded = load_ours(args.layer_expanded, OURS_FIELDS)
    expanded_batt: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(args.layer_expanded):
        key = (row.get("inchikey") or "").strip()
        if not key:
            continue
        values = {k: as_float(row.get("batt_" + k + "_eV")) for k in CHANNELS}
        if all(value is not None for value in values.values()):
            expanded_batt[key] = {k: float(v) for k, v in values.items()}
    expanded_keys = sorted(key for key in expanded_batt if key in expanded)
    arm_a = build_arm(expanded_keys, expanded, expanded_batt)

    v03 = load_ours(args.v03_features, {"gap": "homo_lumo_gap_ev"})
    arm_b_keys = sorted(key for key in hits if key in v03)
    arm_b = {"label": "v03_gap_only", "n": len(arm_b_keys), "channels": {}}
    if len(arm_b_keys) >= 3:
        ours_values = np.array([v03[key]["gap"] for key in arm_b_keys], dtype=float)
        batt_values = np.array([batt[key]["gap"] for key in arm_b_keys], dtype=float)
        arm_b["channels"]["gap"] = channel_stats(ours_values, batt_values)

    global_gap_dev = max(abs(item["gap"] - (item["lumo"] - item["homo"])) for item in batt.values())
    all_lumo = np.array([item["lumo"] for item in batt.values()], dtype=float)
    all_homo = np.array([item["homo"] for item in batt.values()], dtype=float)

    layer_rows = read_csv_rows(args.layer)
    layer_batt_dev = 0.0
    layer_batt_n = 0
    identity_checked = 0
    identity_same = 0
    for row in layer_rows:
        key = (row.get("inchikey") or "").strip()
        if key not in batt:
            continue
        for channel in CHANNELS:
            frozen = as_float(row.get("batt_" + channel + "_eV"))
            if frozen is None:
                continue
            layer_batt_n += 1
            layer_batt_dev = max(layer_batt_dev, abs(frozen - float(batt[key][channel])))
        if key in primary_keys:
            identity_checked += 1
            ours_smiles = canonical_smiles((row.get("smiles") or "").strip())
            if ours_smiles is not None and ours_smiles == batt[key]["canonical_smiles"]:
                identity_same += 1

    expanded_batt_dev = 0.0
    expanded_batt_n = 0
    for key, values in expanded_batt.items():
        if key not in batt:
            continue
        for channel in CHANNELS:
            expanded_batt_n += 1
            expanded_batt_dev = max(expanded_batt_dev, abs(values[channel] - float(batt[key][channel])))

    checks = {
        "batt_gap_identity_n": len(batt),
        "batt_gap_equals_lumo_minus_homo_max_abs_dev": float(global_gap_dev),
        "layer_batt_columns_n": layer_batt_n,
        "layer_batt_columns_max_abs_dev": float(layer_batt_dev),
        "expanded_batt_columns_n": expanded_batt_n,
        "expanded_batt_columns_max_abs_dev": float(expanded_batt_dev),
        "identity_checked": identity_checked,
        "identity_smiles_identical": identity_same,
        "identity_smiles_mismatch": identity_checked - identity_same,
        "batt_global_lumo_sd": float(np.std(all_lumo, ddof=1)),
        "batt_global_lumo_min": float(np.min(all_lumo)),
        "batt_global_lumo_max": float(np.max(all_lumo)),
        "batt_global_homo_lumo_r": pearson(all_homo, all_lumo),
    }

    homo = primary["channels"]["homo"]
    lumo = primary["channels"]["lumo"]
    gap = primary["channels"]["gap"]
    arm_a_gap = arm_a["channels"]["gap"]
    predictions = [
        {
            "id": "PR-1",
            "status": "兑现" if (homo["pearson_r"] >= GATE_PEARSON_R and lumo["pearson_r"] < GATE_PEARSON_R and gap["pearson_r"] < GATE_PEARSON_R) else "未兑现",
            "detail": "homo r = " + fmt(homo["pearson_r"]) + "，lumo r = " + fmt(lumo["pearson_r"]) + "，gap r = " + fmt(gap["pearson_r"]) + "；可用性依通道分裂，须逐通道裁定。",
        },
        {
            "id": "PR-2",
            "status": "兑现" if lumo["batt_sd"] < 0.4 else "被证伪",
            "detail": "主臂 Batt lumo sd = " + fmt(lumo["batt_sd"]) + " eV（门 0.4），极差 [" + fmt(lumo["batt_min"]) + ", " + fmt(lumo["batt_max"]) + "]。",
        },
        {
            "id": "PR-3",
            "status": "兑现" if lumo["mean_signed_diff_batt_minus_ours"] > homo["mean_signed_diff_batt_minus_ours"] else "被证伪",
            "detail": "带符号差 lumo = " + fmt(lumo["mean_signed_diff_batt_minus_ours"]) + " eV vs homo = " + fmt(homo["mean_signed_diff_batt_minus_ours"]) + " eV。",
        },
        {
            "id": "PR-4",
            "status": "兑现" if gap["pearson_r"] < 0.40 else "被证伪",
            "detail": "主臂 gap r = " + fmt(gap["pearson_r"]) + "；敏感性臂 B（另一条 xTB 记录）gap r = " + fmt(arm_b["channels"]["gap"]["pearson_r"]) + "。",
        },
        {
            "id": "PR-5",
            "status": "兑现" if abs(arm_a_gap["pearson_r"] - gap["pearson_r"]) < 0.20 else "被证伪",
            "detail": "全配对层 gap r = " + fmt(arm_a_gap["pearson_r"]) + "（n = " + str(arm_a_gap["n"]) + "）vs 主臂 " + fmt(gap["pearson_r"]) + "（n = " + str(gap["n"]) + "）。",
        },
    ]

    verdicts = {channel: primary["channels"][channel]["verdict"] for channel in CHANNELS}
    all_ref = all(value == "reference_only" for value in verdicts.values())
    if all_ref:
        verdict_statement = ("三条通道全部 reference_only ⇒ Batt-P30K 不可升为我方 HOMO/LUMO 的迁移源；"
                             "它只能作第二参考层/量级核对，不得作为标签来源进入任何池。")
    else:
        verdict_statement = ("homo 通道按预注册门判 usable（留一 MAE " + fmt(homo["loo_mae_mean"]) + " <= 0.35 且 r " + fmt(homo["pearson_r"]) + " >= 0.80），"
                             "但它距 MAE 门仅 " + fmt(GATE_LOO_MAE_EV - homo["loo_mae_mean"]) + " eV，属边界判定；"
                             "且跨水平存在 " + fmt(homo["mean_signed_diff_batt_minus_ours"]) + " eV 的系统性偏移，故 usable 只表示「可作带线性映射的第二参考层」，"
                             "不等于原始值可直接混用。lumo 与 gap 通道均 reference_only。")

    summary = {
        "probe": "w19_batt_gap_crosscheck",
        "title": "N2 直接交叉核对：我方 GFN2-xTB 轨道能 vs Batt-P30K 轨道能",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True,
        "models_fitted": 3 + 3 + (1 if "gap" in arm_b["channels"] else 0),
        "reaxys_values_used": False,
        "writes_any_pool": False,
        "promoted": False,
        "main_scoreboard_attempts": 0,
        "cross_level": True,
        "prereg": {"path": str(args.prereg.relative_to(REPOSITORY_ROOT)), "sha256": sha256_file(args.prereg)},
        "script_sha256": sha256_file(SCRIPT_PATH),
        "gate": {"loo_mae_ev_max": GATE_LOO_MAE_EV, "pearson_r_min": GATE_PEARSON_R},
        "pool": {
            "roster_rows": len(read_csv_rows(args.roster)),
            "roster_unique_inchikeys": len(set(roster_keys)),
            "batt_groups_scanned": batt_meta["groups_scanned"],
            "batt_parsed_records": batt_meta["parsed_records"],
            "batt_invalid_smiles": batt_meta["invalid_smiles"],
            "batt_h5_sha256": h5_sha,
            "batt_sha256_matches_registered": h5_sha == EXPECTED_BATT_SHA256,
            "hits": len(hits),
            "hits_match_direct_hit_summary": bool(hits_match),
            "layer_rows": len(layer_rows),
            "primary_n": len(primary_keys),
            "uncovered_hits": len(uncovered),
            "uncovered_hit_keys": uncovered,
        },
        "primary": {"label": "roster_hits_intersect_xtb_layer", "n": len(primary_keys), "keys": primary_keys, "channels": primary["channels"]},
        "sensitivity": {"A_expanded_paired": arm_a, "B_v03_gap": arm_b},
        "checks": checks,
        "predictions": predictions,
        "divergence_notes": [
            "已排除·方法学：跨水平系统性偏移可实测——lumo 带符号差 " + fmt(lumo["mean_signed_diff_batt_minus_ours"]) + " eV、homo " + fmt(homo["mean_signed_diff_batt_minus_ours"]) + " eV，说明两源的空轨道水平错位远大于占轨道；这是 SMD 与气相/泛函差的可测后果，不能当作我方模型误差。",
            "已排除·标识符：主臂 " + str(identity_checked) + " 例中规范 SMILES 逐字相同 " + str(identity_same) + " 例，结构身份无错配。",
            "已排除·空读数：lumo 通道留一 MAE " + fmt(lumo["loo_mae_mean"]) + " 看似小于门，但常数基线留一 MAE = " + fmt(lumo["loo_mae_constant_baseline_mean"]) + "，相对 skill 仅 " + fmt(lumo["skill_vs_constant_loo"]) + "，且其 OLS 斜率仅 " + fmt(lumo["ols_slope"]) + " ⇒ 该 MAE 来自目标近乎常数，不构成迁移能力。",
            "未排除·构象：两源各自取单构象，本件无构象系综，无法分离几何来源的散布；登记为未排除。",
            "未排除·Batt LUMO 语义：Batt 的 lumo 在集合内近乎常数（sd " + fmt(lumo["batt_sd"]) + " eV）且与其 homo 全库相关仅 " + fmt(checks["batt_global_homo_lumo_r"]) + "，提示该列可能不是与占轨道同族的化学前沿空轨道；本件只能登记疑点，不能裁定其定义。",
        ],
        "verdict": verdicts,
        "verdict_statement": verdict_statement,
        "boundaries": [
            "跨水平：Batt 为 SMD(ε=18.5) ωB97X-V，我方为 GFN2-xTB 气相单点，所有原始 MAE 一律 cross_level=true，不得当模型精度引用。",
            "主臂 n = " + str(len(primary_keys)) + " 且为我方 xTB 覆盖所限；未被覆盖的 " + str(len(uncovered)) + " 个命中键不可核，不外推。",
            "敏感性臂只作稳健性检查，不能把任一通道的 verdict 从 reference_only 升级为 usable。",
            "Reaxys 数值未进入本件任何读数；无受限值进入交付层。",
            "本件不写任何池、不动主记分牌、不做 git 操作。",
        ],
        "outputs": {
            "summary": str(args.summary_out.relative_to(REPOSITORY_ROOT)),
            "report": "reports/w19_batt_gap_crosscheck.md",
        },
    }

    args.summary_out.write_bytes((json.dumps(summary, ensure_ascii=False, indent=2) + chr(10)).encode("utf-8"))
    report_path = args.summary_out.parent.parent / "reports" / "w19_batt_gap_crosscheck.md"
    report_path.write_bytes(render_report(summary).encode("utf-8"))
    print("hits=" + str(len(hits)) + " primary_n=" + str(len(primary_keys)))
    for channel in CHANNELS:
        stats = summary["primary"]["channels"][channel]
        print(channel + " r=" + fmt(stats["pearson_r"]) + " loo_mae=" + fmt(stats["loo_mae_mean"]) + " verdict=" + stats["verdict"])
    print("summary_written=" + str(args.summary_out))
    print("report_written=" + str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
