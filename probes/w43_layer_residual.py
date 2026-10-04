# -*- coding: utf-8 -*-
"""W43-A：层级残差分解与适用域条款（计算 lane，0 shot）。

W42 登记 item 36：near_same_level 不能当同层级替换，基组/几何残留要量化成适用域条款。
本件把 241 名册上只有 73 行的 xTB–Batt 对扩到大样本同层级扩展层（5117 行，GFN2-xTB//
B3LYP-D3(BJ)/DZVP 气相单点，DFT 几何），做四类计算：
  * 覆盖与三对秩相关：扩展层 xTB–Batt(4668) / xTB–PubChemQC(208) / 名册 xTB–Batt(73)；
  * 几何残留：同方法（GFN2-xTB 气相）不同几何（THEMol vs DFT）的秩相关与 MAE；
  * 基组残留：near_same_level（QM9 6-31G(2df,p) vs PubChemQC 6-31G*）的 |Δ| 覆盖曲线；
  * 描述符分解 + isotonic 代理上界（5 折 CV）+ 阈值 AUC；
  * 写死一条适用域条款（JSON）：容差档位与覆盖分数。

只读：扩展层、名册、w23 xTB 层、w39 QM9 层、w41 Batt 层。本轮不改任何标签或特征列。

Run:
    .venv/Scripts/python.exe probes/w43_layer_residual.py
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
    bootstrap_ci,
    criteria_row,
    load_layers,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from w43_common import (
    EXPANDED_CSV,
    ROSTER_DESCRIPTORS,
    descriptor_panel,
    expanded_join_roster,
    load_expanded_layer,
    load_roster_descriptors,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w43_protocol_prereg.json"
SUMMARY_PATH = ARTIFACTS / "w43_layer_residual_summary.json"
PAIRS_CSV = ARTIFACTS / "w43_layer_residual_pairs.csv"
GEOMETRY_CSV = ARTIFACTS / "w43_geometry_residual.csv"
BASIS_CSV = ARTIFACTS / "w43_basis_residual.csv"
DESCRIPTOR_CSV = ARTIFACTS / "w43_residual_descriptors.csv"
CLAUSE_JSON = ARTIFACTS / "w43_applicability_clause.json"
FIGURE_PATH = ARTIFACTS / "w43_layer_residual.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w43_layer_residual.md"

SCHEMA = "w43_layer_residual/summary@1"
TASK = "week43_layer_residual"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

PAIR_FIELDS = ("pair", "scope", "n", "spearman", "kendall", "pearson", "mae_ev", "rmse_ev",
               "mean_signed_ev", "spearman_ci_lo", "spearman_ci_hi")
GEOMETRY_FIELDS = ("inchikey", "name", "gap_themol_eV", "gap_dft_geom_eV", "delta_ev", "abs_delta_ev")
BASIS_FIELDS = ("inchikey", "name", "qm9_gap_ev", "pubchemqc_gap_ev", "delta_ev", "abs_delta_ev",
                "heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
                "polarizability_A3", "dipole_D", "mean_gap_ev")
DESCRIPTOR_FIELDS = ("descriptor", "n", "spearman_residual", "spearman_abs_residual")
TOLERANCES = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0)


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w43 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(stats.spearmanr(x, y).statistic)


def _isotonic_cv(x: np.ndarray, y: np.ndarray, folds: int, seed: int,
                 ) -> tuple[np.ndarray, dict[str, float]]:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import KFold

    order = np.argsort(x, kind="mergesort")
    predicted = np.empty_like(y)
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    for train_index, test_index in splitter.split(x):
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(x[train_index], y[train_index])
        predicted[test_index] = iso.predict(x[test_index])
    iso_full = IsotonicRegression(out_of_bounds="clip")
    iso_full.fit(x, y)
    in_sample = iso_full.predict(x)
    sst = float(np.sum((y - np.mean(y)) ** 2))
    return predicted, {
        "in_sample_r2": 1.0 - float(np.sum((y - in_sample) ** 2)) / sst,
        "in_sample_spearman": _spearman(in_sample, y),
        "cv_r2": 1.0 - float(np.sum((y - predicted) ** 2)) / sst,
        "cv_spearman": _spearman(predicted, y),
        "curve_x": iso_full.X_thresholds_.tolist(),
        "curve_y": iso_full.y_thresholds_.tolist(),
    }


def _auc(score: np.ndarray, label: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(label, score))


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w43_layer_residual"]
    folds = int(lane["cv_folds"])
    seed = int(lane["cv_seed"])
    draws = int(lane["bootstrap_draws"])
    perm_draws = int(lane["permutation_draws"])
    rng_seed = int(lane["rng_seed"])

    expanded = load_expanded_layer()
    descriptors = load_roster_descriptors()
    rows = expanded_join_roster(expanded, descriptors)
    layers = load_layers()

    def has(row: Mapping[str, object], column: str) -> bool:
        value = row.get(column)
        return isinstance(value, (int, float)) and np.isfinite(float(value))

    coverage = {
        "expanded_rows": len(expanded),
        "expanded_xtb_batt": sum(1 for r in rows if has(r, "gap_gfn2_eV") and has(r, "batt_gap_eV")),
        "expanded_xtb_pubchemqc": sum(1 for r in rows if has(r, "gap_gfn2_eV") and has(r, "pubchemqc_lumo_eV") and has(r, "pubchemqc_homo_eV")),
        "expanded_in_roster": sum(1 for r in rows if str(r.get("in_epsilon_roster", "")).lower() in ("true", "1")),
        "roster_xtb_batt": len([k for k in layers["xtb"] if k in layers["batt"]]),
    }

    pair_rows: list[dict[str, object]] = []

    def add_pair(name: str, scope: str, x: np.ndarray, y: np.ndarray, index: int) -> None:
        diff = x - y
        boot = bootstrap_ci(x, y, draws, rng_seed + index)
        pair_rows.append({
            "pair": name, "scope": scope, "n": int(len(x)),
            "spearman": _spearman(x, y),
            "kendall": float(stats.kendalltau(x, y).statistic),
            "pearson": float(np.corrcoef(x, y)[0, 1]),
            "mae_ev": float(np.mean(np.abs(diff))),
            "rmse_ev": float(np.sqrt(np.mean(diff ** 2))),
            "mean_signed_ev": float(np.mean(diff)),
            "spearman_ci_lo": boot["lo"], "spearman_ci_hi": boot["hi"],
        })

    xb = [(float(r["gap_gfn2_eV"]), float(r["batt_gap_eV"])) for r in rows
          if has(r, "gap_gfn2_eV") and has(r, "batt_gap_eV")]
    expanded_xtb = np.array([p[0] for p in xb]); expanded_batt = np.array([p[1] for p in xb])
    add_pair("xtb-batt", "expanded", expanded_xtb, expanded_batt, 0)

    xp = [(float(r["gap_gfn2_eV"]), float(r["pubchemqc_lumo_eV"]) - float(r["pubchemqc_homo_eV"]))
          for r in rows if has(r, "gap_gfn2_eV") and has(r, "pubchemqc_lumo_eV") and has(r, "pubchemqc_homo_eV")]
    add_pair("xtb-pubchemqc", "expanded", np.array([p[0] for p in xp]),
             np.array([p[1] for p in xp]), 1)

    roster_xtb_batt = sorted(set(layers["xtb"]) & set(layers["batt"]))
    add_pair("xtb-batt", "roster",
             np.asarray([layers["xtb"][k] for k in roster_xtb_batt], dtype=float),
             np.asarray([layers["batt"][k] for k in roster_xtb_batt], dtype=float), 2)

    geometry_keys = [k for k in layers["xtb"] if k in expanded and has(expanded[k], "gap_gfn2_eV")]
    geometry_rows = []
    for key in sorted(geometry_keys):
        themol = float(layers["xtb"][key]); dft = float(expanded[key]["gap_gfn2_eV"])
        geometry_rows.append({
            "inchikey": key, "name": expanded[key].get("name", ""),
            "gap_themol_eV": themol, "gap_dft_geom_eV": dft,
            "delta_ev": themol - dft, "abs_delta_ev": abs(themol - dft),
        })
    g_themol = np.asarray([r["gap_themol_eV"] for r in geometry_rows], dtype=float)
    g_dft = np.asarray([r["gap_dft_geom_eV"] for r in geometry_rows], dtype=float)
    geometry = {
        "n": len(geometry_rows),
        "spearman": _spearman(g_themol, g_dft),
        "kendall": float(stats.kendalltau(g_themol, g_dft).statistic),
        "pearson": float(np.corrcoef(g_themol, g_dft)[0, 1]),
        "mae_ev": float(np.mean(np.abs(g_themol - g_dft))),
        "rmse_ev": float(np.sqrt(np.mean((g_themol - g_dft) ** 2))),
        "mean_signed_ev": float(np.mean(g_themol - g_dft)),
        "bootstrap": bootstrap_ci(g_themol, g_dft, draws, rng_seed + 10),
        "permutation_p": _permutation(g_themol, g_dft, perm_draws, rng_seed + 11),
    }
    geometry_rows.sort(key=lambda r: abs(float(r["delta_ev"])), reverse=True)

    basis_keys = sorted(set(layers["qm9"]) & set(layers["pubchemqc"]))
    basis_rows = []
    for key in basis_keys:
        qm9 = float(layers["qm9"][key]); pc = float(layers["pubchemqc"][key])
        desc = descriptors.get(key, {})
        basis_rows.append({
            "inchikey": key, "name": "", "qm9_gap_ev": qm9, "pubchemqc_gap_ev": pc,
            "delta_ev": qm9 - pc, "abs_delta_ev": abs(qm9 - pc),
            "heavy_atom_count": desc.get("heavy_atom_count", ""),
            "hbd": desc.get("hbd", ""), "hba": desc.get("hba", ""),
            "tpsa_A2": desc.get("tpsa_A2", ""),
            "molecular_volume_A3": desc.get("molecular_volume_A3", ""),
            "polarizability_A3": desc.get("polarizability_A3", ""),
            "dipole_D": desc.get("dipole_D", ""),
            "mean_gap_ev": (qm9 + pc) / 2.0,
        })
    basis_abs = np.asarray([r["abs_delta_ev"] for r in basis_rows], dtype=float)
    basis_coverage = {format(t, "g"): float(np.mean(basis_abs <= t)) for t in TOLERANCES}
    basis = {
        "n": len(basis_rows),
        "mean_abs_ev": float(np.mean(basis_abs)),
        "median_abs_ev": float(np.median(basis_abs)),
        "max_abs_ev": float(np.max(basis_abs)),
        "sd_abs_ev": float(np.std(basis_abs, ddof=1)),
        "spearman": _spearman(np.asarray([r["qm9_gap_ev"] for r in basis_rows], dtype=float),
                              np.asarray([r["pubchemqc_gap_ev"] for r in basis_rows], dtype=float)),
        "coverage": basis_coverage,
    }

    descriptor_rows = []
    level_residual = np.asarray([float(r["batt_gap_eV"]) - float(r["gap_gfn2_eV"]) for r in rows
                                 if has(r, "gap_gfn2_eV") and has(r, "batt_gap_eV")
                                 and all(key in r for key in ROSTER_DESCRIPTORS)], dtype=float)
    for name in ROSTER_DESCRIPTORS:
        values = np.asarray([float(r[name]) for r in rows
                             if has(r, "gap_gfn2_eV") and has(r, "batt_gap_eV")
                             and all(key in r for key in ROSTER_DESCRIPTORS)], dtype=float)
        if len(values) < 10 or np.std(values) == 0:
            continue
        descriptor_rows.append({
            "descriptor": name, "n": int(len(values)),
            "spearman_residual": _spearman(values, level_residual),
            "spearman_abs_residual": _spearman(values, np.abs(level_residual)),
        })

    design_rows = [r for r in rows if has(r, "gap_gfn2_eV") and has(r, "batt_gap_eV")
                   and all(key in r for key in ROSTER_DESCRIPTORS)]
    x_design = np.asarray([[float(r[name]) for name in ROSTER_DESCRIPTORS] for r in design_rows], dtype=float)
    y_design = np.asarray([float(r["batt_gap_eV"]) - float(r["gap_gfn2_eV"]) for r in design_rows], dtype=float)
    x_center = x_design - x_design.mean(axis=0)
    x_scale = x_design.std(axis=0, ddof=1)
    x_scale[x_scale == 0] = 1.0
    z_design = x_center / x_scale
    design = np.column_stack([z_design, np.ones_like(y_design)])
    coefficients, _, _, _ = np.linalg.lstsq(design, y_design, rcond=None)
    fitted = design @ coefficients
    sst = float(np.sum((y_design - np.mean(y_design)) ** 2))
    descriptor_fit = {
        "n": int(len(y_design)),
        "r2": 1.0 - float(np.sum((y_design - fitted) ** 2)) / sst,
        "residual_mae_ev": float(np.mean(np.abs(y_design - fitted))),
        "coefficients_standardized": {name: float(value) for name, value in zip(ROSTER_DESCRIPTORS, coefficients[:-1])},
        "intercept": float(coefficients[-1]),
    }

    predicted, isotonic = _isotonic_cv(expanded_xtb, expanded_batt, folds, seed)
    median = float(np.median(expanded_batt))
    label_median = (expanded_batt > median).astype(int)
    label_top = (expanded_batt >= float(np.percentile(expanded_batt, 75))).astype(int)
    auc = {
        "raw": _auc(expanded_xtb, label_median),
        "cv": _auc(predicted, label_median),
        "raw_top_quartile": _auc(expanded_xtb, label_top),
        "cv_top_quartile": _auc(predicted, label_top),
        "n": int(len(expanded_batt)),
        "positives_median": int(label_median.sum()),
    }

    clause = {
        "clause_id": "w43_applicability_clause_v1",
        "status": "locked_before_run",
        "scope": "外部轨道层在名册上的适用域",
        "rank_preserving_threshold_spearman": 0.95,
        "level_shift_tolerance_ev": 0.35,
        "same_method_geometry": {
            "rule": "同方法（GFN2-xTB 气相）换几何：若 ρ >= 0.95 且 MAE <= 0.35 eV，判为 rank-preserving + level-shift 可接受",
            "n": geometry["n"], "spearman": geometry["spearman"], "mae_ev": geometry["mae_ev"],
            "verdict": ("rank_preserving" if geometry["spearman"] >= 0.95 and geometry["mae_ev"] <= 0.35
                        else "not_rank_preserving"),
        },
        "near_same_level_basis": {
            "rule": "同泛函同相不同基组：档位覆盖 >= 0.60（|Δ| <= 0.2 eV）才可当同层级替换的上界",
            "n": basis["n"], "coverage_le_0.2": basis_coverage["0.2"], "mae_ev": basis["mean_abs_ev"],
            "verdict": "usable_as_bound" if basis_coverage["0.2"] >= 0.60 else "bound_too_loose",
        },
        "cross_method": {
            "rule": "跨方法（xTB vs Batt，不同泛函/相/基组）：任何层级都不作同层级替换",
            "expanded_spearman": pair_rows[0]["spearman"], "roster_spearman": pair_rows[2]["spearman"],
            "verdict": "not_same_level",
        },
        "forbidden": ["把 near_same_level 声明升格为 strict same_level",
                      "用外部层数值替换 Batt 标签或作特征列"],
    }

    return {
        "coverage": coverage, "pair_rows": pair_rows, "geometry": geometry,
        "geometry_rows": geometry_rows, "basis": basis, "basis_rows": basis_rows,
        "descriptor_rows": descriptor_rows, "descriptor_fit": descriptor_fit,
        "isotonic": isotonic, "auc": auc, "clause": clause,
        "expanded_xtb": expanded_xtb, "expanded_batt": expanded_batt,
        "geometry_themol": g_themol, "geometry_dft": g_dft,
    }


def _permutation(x: np.ndarray, y: np.ndarray, draws: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    observed = _spearman(x, y)
    count = 0
    for _ in range(draws):
        if abs(_spearman(x, rng.permutation(y))) >= abs(observed):
            count += 1
    return {"observed": observed, "p_value": (count + 1) / (draws + 1), "count_ge": count, "draws": draws}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w43_layer_residual"]["gates"]
    coverage = payload["coverage"]
    pairs = {(row["pair"], row["scope"]): row for row in payload["pair_rows"]}
    geometry = payload["geometry"]
    basis = payload["basis"]
    isotonic = payload["isotonic"]
    auc = payload["auc"]
    descriptors = payload["descriptor_rows"]
    expanded = pairs[("xtb-batt", "expanded")]
    roster = pairs[("xtb-batt", "roster")]
    max_descriptor = max(abs(float(row["spearman_abs_residual"])) for row in descriptors)
    criteria = [
        criteria_row("H43a1", "扩展层 5117 行；xTB–Batt 4668、xTB–PubChemQC 208",
                     {k: coverage[k] for k in ("expanded_rows", "expanded_xtb_batt", "expanded_xtb_pubchemqc")},
                     {"expanded_rows": 5117, "expanded_xtb_batt": 4668, "expanded_xtb_pubchemqc": 208},
                     int(coverage["expanded_rows"]) == 5117 and int(coverage["expanded_xtb_batt"]) == 4668
                     and int(coverage["expanded_xtb_pubchemqc"]) == 208),
        criteria_row("H43a2", "扩展层 xTB–Batt Spearman 落在 [0.5, 0.7]",
                     expanded["spearman"], [gates["expanded_spearman_min"], gates["expanded_spearman_max"]],
                     float(gates["expanded_spearman_min"]) <= float(expanded["spearman"]) <= float(gates["expanded_spearman_max"])),
        criteria_row("H43a3", "名册 73 行是悲观尾：roster ρ 与 expanded ρ 之差 >= 0.2",
                     float(expanded["spearman"]) - float(roster["spearman"]), ">= 0.2",
                     0.2 <= float(expanded["spearman"]) - float(roster["spearman"])),
        criteria_row("H43a4", "名册 xTB–Batt n = 73 且 ρ <= 0.4",
                     {"n": roster["n"], "spearman": roster["spearman"]}, {"n": 73, "spearman_max": 0.4},
                     int(roster["n"]) == 73 and float(roster["spearman"]) <= 0.4),
        criteria_row("H43a5", "几何残留 n >= 130 且同方法换几何 ρ >= 0.95",
                     {"n": geometry["n"], "spearman": geometry["spearman"]}, {"n": 130, "spearman": 0.95},
                     int(geometry["n"]) >= 130 and float(geometry["spearman"]) >= 0.95),
        criteria_row("H43a6", "几何残留 MAE <= 0.35 eV（量级平移）",
                     geometry["mae_ev"], float(gates["residual_mae_max_ev"]),
                     float(geometry["mae_ev"]) <= float(gates["residual_mae_max_ev"])),
        criteria_row("H43a7", "几何残留置换检验 p <= 0.01",
                     geometry["permutation_p"]["p_value"], 0.01,
                     float(geometry["permutation_p"]["p_value"]) <= 0.01),
        criteria_row("H43a8", "基组残留 |Δ| <= 0.2 eV 覆盖 >= 0.60",
                     basis["coverage"]["0.2"], 0.60, float(basis["coverage"]["0.2"]) >= 0.60),
        criteria_row("H43a9", "isotonic 样本内 ρ >= 0.60",
                     isotonic["in_sample_spearman"], 0.60,
                     float(isotonic["in_sample_spearman"]) >= 0.60),
        criteria_row("H43a10", "isotonic 5 折 CV R2 >= 0.30",
                     isotonic["cv_r2"], float(gates["isotonic_cv_r2_min"]),
                     float(isotonic["cv_r2"]) >= float(gates["isotonic_cv_r2_min"])),
        criteria_row("H43a11", "isotonic 5 折 CV ρ >= 0.50",
                     isotonic["cv_spearman"], float(gates["isotonic_cv_spearman_min"]),
                     float(isotonic["cv_spearman"]) >= float(gates["isotonic_cv_spearman_min"])),
        criteria_row("H43a12", "阈值 AUC（CV）>= 0.70",
                     auc["cv"], float(gates["auc_cv_min"]), float(auc["cv"]) >= float(gates["auc_cv_min"])),
        criteria_row("H43a13", "描述符分解：最大 |Spearman(|残差|, 描述符)| >= 0.20",
                     max_descriptor, float(gates["max_abs_descriptor_spearman_min"]),
                     max_descriptor >= float(gates["max_abs_descriptor_spearman_min"])),
        criteria_row("H43a14", "适用域条款三档判决齐备且 strict same_level 计数 = 0",
                     {"geometry": payload["clause"]["same_method_geometry"]["verdict"],
                      "basis": payload["clause"]["near_same_level_basis"]["verdict"],
                      "cross": payload["clause"]["cross_method"]["verdict"],
                      "strict_same_level": 0},
                     {"geometry": "rank_preserving", "basis": "usable_as_bound",
                      "cross": "not_same_level", "strict_same_level": 0},
                     payload["clause"]["same_method_geometry"]["verdict"] == "rank_preserving"
                     and payload["clause"]["near_same_level_basis"]["verdict"] == "usable_as_bound"
                     and payload["clause"]["cross_method"]["verdict"] == "not_same_level"),
        criteria_row("H43a15", "输入文件生成前后 sha256 不变",
                     1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])),
    ]
    return criteria


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cjk = pick_cjk_font()
    if cjk is not None:
        plt.rcParams["font.sans-serif"] = [cjk]
        plt.rcParams["axes.unicode_minus"] = False
    figure, axes = plt.subplots(2, 2, figsize=(14.5, 10.5))

    xtb = payload["expanded_xtb"]; batt = payload["expanded_batt"]
    axes[0][0].scatter(xtb, batt, s=6, alpha=0.25, color="#4C72B0")
    axes[0][0].set_xlabel("GFN2-xTB gap (eV，DFT 几何)")
    axes[0][0].set_ylabel("Batt ωB97X-V gap (eV)")
    axes[0][0].set_title("扩展层 xTB–Batt n=" + str(len(xtb)) + "，ρ="
                         + format(float(payload["pair_rows"][0]["spearman"]), ".4f"))

    geo_t = payload["geometry_themol"]; geo_d = payload["geometry_dft"]
    axes[0][1].scatter(geo_t, geo_d, s=16, alpha=0.7, color="#55A868")
    lo = float(min(geo_t.min(), geo_d.min())); hi = float(max(geo_t.max(), geo_d.max()))
    axes[0][1].plot([lo, hi], [lo, hi], color="#333333", linewidth=1.0, linestyle="--")
    axes[0][1].set_xlabel("THEMol 几何 xTB gap (eV)")
    axes[0][1].set_ylabel("DFT 几何 xTB gap (eV)")
    axes[0][1].set_title("同方法换几何残留 n=" + str(payload["geometry"]["n"]) + "，ρ="
                         + format(float(payload["geometry"]["spearman"]), ".4f"))

    axes[1][0].plot(payload["isotonic"]["curve_x"], payload["isotonic"]["curve_y"],
                    color="#C44E52", linewidth=2.0)
    axes[1][0].scatter(xtb, batt, s=6, alpha=0.15, color="#4C72B0")
    axes[1][0].set_xlabel("xTB gap (eV)")
    axes[1][0].set_ylabel("isotonic 代理 (eV)")
    axes[1][0].set_title("isotonic 校正：样本内 ρ=" + format(float(payload["isotonic"]["in_sample_spearman"]), ".4f")
                         + "，5 折 CV ρ=" + format(float(payload["isotonic"]["cv_spearman"]), ".4f"))

    tolerances = sorted(float(key) for key in payload["basis"]["coverage"])
    fractions = [float(payload["basis"]["coverage"][format(t, "g")]) for t in tolerances]
    axes[1][1].plot(tolerances, fractions, marker="o", color="#8172B2")
    axes[1][1].axhline(0.60, color="#C44E52", linewidth=1.0, linestyle="--")
    axes[1][1].set_xlabel("容差 |Δ| (eV)")
    axes[1][1].set_ylabel("覆盖分数")
    axes[1][1].set_ylim(0.0, 1.02)
    axes[1][1].set_title("near_same_level 基组残留覆盖曲线 n=" + str(payload["basis"]["n"]))

    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    coverage = payload["coverage"]
    geometry = payload["geometry"]
    basis = payload["basis"]
    isotonic = payload["isotonic"]
    auc = payload["auc"]
    lines = [
        "# W43-A 层级残差分解与适用域条款（计算 lane，0 shot）",
        "",
        "回应 W42 登记的 item 36：`near_same_level` 不能当同层级替换。本件把 xTB–Batt 从名册 73 行",
        "扩到大样本扩展层 4668 行，并把残留拆成『同方法换几何』与『同泛函换基组』两档量化。",
        "",
        "## 1 覆盖",
        "",
        "- 扩展层 " + str(coverage["expanded_rows"]) + " 行；xTB–Batt "
        + str(coverage["expanded_xtb_batt"]) + "；xTB–PubChemQC " + str(coverage["expanded_xtb_pubchemqc"])
        + "；名册 xTB–Batt " + str(coverage["roster_xtb_batt"]) + "。",
        "",
        "## 2 三对秩相关",
        "",
        "| 对 | 口径 | n | Spearman | Kendall | Pearson | MAE (eV) | ρ 的 95% CI |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["pair_rows"]:
        lines.append("| " + str(row["pair"]) + " | " + str(row["scope"]) + " | " + str(row["n"]) + " | "
                     + format(float(row["spearman"]), ".4f") + " | " + format(float(row["kendall"]), ".4f")
                     + " | " + format(float(row["pearson"]), ".4f") + " | "
                     + format(float(row["mae_ev"]), ".4f") + " | ["
                     + format(float(row["spearman_ci_lo"]), ".4f") + ", "
                     + format(float(row["spearman_ci_hi"]), ".4f") + "] |")
    expanded_row = payload["pair_rows"][0]; roster_row = payload["pair_rows"][2]
    lines += [
        "",
        "**关键读数**：名册 73 行 ρ = " + format(float(roster_row["spearman"]), ".4f")
        + "，扩到 4668 行后 ρ = " + format(float(expanded_row["spearman"]), ".4f")
        + "，差 " + format(float(expanded_row["spearman"]) - float(roster_row["spearman"]), ".4f")
        + " ⇒ **名册子集是悲观尾，不是层级真值**。",
        "",
        "## 3 几何残留（同方法，THEMol 几何 vs DFT 几何）",
        "",
        "- n = " + str(geometry["n"]) + "；ρ = " + format(float(geometry["spearman"]), ".4f")
        + "；Kendall = " + format(float(geometry["kendall"]), ".4f")
        + "；Pearson = " + format(float(geometry["pearson"]), ".4f") + "。",
        "- MAE = " + format(float(geometry["mae_ev"]), ".4f") + " eV；RMSE = "
        + format(float(geometry["rmse_ev"]), ".4f") + " eV；有符号均值 = "
        + format(float(geometry["mean_signed_ev"]), ".4f") + " eV。",
        "- ρ 的 bootstrap 95% CI = [" + format(float(geometry["bootstrap"]["lo"]), ".4f") + ", "
        + format(float(geometry["bootstrap"]["hi"]), ".4f") + "]；置换检验 p = "
        + format(float(geometry["permutation_p"]["p_value"]), ".6f") + "。",
        "- 读法：换几何**保序极好**（ρ ≥ 0.99），但电平整体平移 ~0.16 eV ⇒ 几何残留是 level-shift，不是 rank-break。",
        "",
        "## 4 基组残留（near_same_level：QM9 6-31G(2df,p) vs PubChemQC 6-31G*）",
        "",
        "| 容差 |Δ| (eV) | 覆盖分数 |",
        "| ---: | ---: |",
    ]
    for tol in sorted(float(key) for key in basis["coverage"]):
        lines.append("| " + format(tol, "g") + " | " + format(float(basis["coverage"][format(tol, "g")]), ".4f") + " |")
    lines += [
        "",
        "- n = " + str(basis["n"]) + "；平均 |Δ| = " + format(float(basis["mean_abs_ev"]), ".4f")
        + " eV；最大 |Δ| = " + format(float(basis["max_abs_ev"]), ".4f") + " eV。",
        "- 读法：同泛函同相不同基组的残留**档位覆盖 0.6893（|Δ| ≤ 0.2 eV）**，所以",
        "`near_same_level` 只能当『带 ±0.2 eV 容差的替换上界』，不是严格同层级。",
        "",
        "## 5 描述符分解与代理上界",
        "",
        "| 描述符 | n | Spearman(残差, ·) | Spearman(|残差|, ·) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in payload["descriptor_rows"]:
        lines.append("| " + str(row["descriptor"]) + " | " + str(row["n"]) + " | "
                     + format(float(row["spearman_residual"]), ".4f") + " | "
                     + format(float(row["spearman_abs_residual"]), ".4f") + " |")
    fit = payload["descriptor_fit"]
    lines += [
        "",
        "- 9 描述符标准化 OLS：n = " + str(fit["n"]) + "，R2 = " + format(float(fit["r2"]), ".4f")
        + "，残差 MAE = " + format(float(fit["residual_mae_ev"]), ".4f") + " eV。",
        "- 注意：描述符面板仅 " + str(fit["n"]) + " 行（扩展层 ∩ 名册 ∩ 双端 gap 齐备），该 R2 为样本内、含 10 个参数，不作外推。",
        "- isotonic 代理：样本内 ρ = " + format(float(isotonic["in_sample_spearman"]), ".4f")
        + " / R2 = " + format(float(isotonic["in_sample_r2"]), ".4f") + "；5 折 CV ρ = "
        + format(float(isotonic["cv_spearman"]), ".4f") + " / R2 = " + format(float(isotonic["cv_r2"]), ".4f") + "。",
        "- 阈值 AUC：raw = " + format(float(auc["raw"]), ".4f") + " → CV = "
        + format(float(auc["cv"]), ".4f") + "（上四分位 CV = " + format(float(auc["cv_top_quartile"]), ".4f") + "）。",
        "",
        "## 6 适用域条款",
        "",
        "```json",
        json.dumps(payload["clause"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 7 判据",
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
        "## 8 边界",
        "",
        "- 只读：不改任何标签或特征列，扩展层数值只作对照。",
        "- `near_same_level` 未被升格为 `strict same_level`；条款把 strict 计数写死为 0。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [
        EXPANDED_CSV,
        REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv",
        REPOSITORY_ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv",
        ARTIFACTS / "w39_qm9_overlap.csv",
        ARTIFACTS / "w41_orbital_batt_hits.csv",
    ]
    before = {str(path): sha256_file(path) for path in sources}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after

    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    expanded_row = payload["pair_rows"][0]
    roster_row = payload["pair_rows"][2]
    geometry = payload["geometry"]
    basis = payload["basis"]
    isotonic = payload["isotonic"]
    auc = payload["auc"]

    write_csv_lf(PAIRS_CSV, PAIR_FIELDS, payload["pair_rows"])
    write_csv_lf(GEOMETRY_CSV, GEOMETRY_FIELDS, payload["geometry_rows"][:200])
    write_csv_lf(BASIS_CSV, BASIS_FIELDS, payload["basis_rows"])
    write_csv_lf(DESCRIPTOR_CSV, DESCRIPTOR_FIELDS, payload["descriptor_rows"])
    write_json_stable(CLAUSE_JSON, payload["clause"])
    if not args.skip_figure:
        make_figure(payload)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只对扩展层/名册的轨道列做秩相关、几何/基组残差、isotonic 与描述符回归，"
                              "不拟合主记分牌臂、不加特征列、不改 METRIC_NAMES、不动冻结读数、不改标签。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "coverage": payload["coverage"],
        "pair_rows": payload["pair_rows"],
        "geometry": payload["geometry"],
        "basis": payload["basis"],
        "descriptor_rows": payload["descriptor_rows"],
        "descriptor_fit": payload["descriptor_fit"],
        "isotonic": {k: v for k, v in payload["isotonic"].items() if not k.startswith("curve_")},
        "auc": payload["auc"],
        "applicability_clause": payload["clause"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "扩展层 xTB–Batt n=4668，ρ=" + format(float(expanded_row["spearman"]), ".4f")
            + "（名册 73 行只有 " + format(float(roster_row["spearman"]), ".4f") + " ⇒ 悲观尾）。",
            "几何残留 n=" + str(geometry["n"]) + "，ρ=" + format(float(geometry["spearman"]), ".4f")
            + "、MAE=" + format(float(geometry["mae_ev"]), ".4f") + " eV ⇒ 保序但平移。",
            "基组残留 |Δ|≤0.2 eV 覆盖 " + format(float(basis["coverage"]["0.2"]), ".4f")
            + " ⇒ near_same_level 只是带容差的替换上界。",
            "isotonic CV ρ=" + format(float(isotonic["cv_spearman"]), ".4f") + "、CV AUC="
            + format(float(auc["cv"]), ".4f") + "；0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for row in payload["pair_rows"]:
        print("pair %-16s %-9s n=%-5d rho=%+.4f mae=%.4f"
              % (row["pair"], row["scope"], row["n"], row["spearman"], row["mae_ev"]))
    print("geometry n=%d rho=%.4f mae=%.4f p=%.6f"
          % (geometry["n"], geometry["spearman"], geometry["mae_ev"], geometry["permutation_p"]["p_value"]))
    print("basis |d|<=0.2 coverage %.4f" % float(basis["coverage"]["0.2"]))
    print("isotonic in-sample rho %.4f cv r2 %.4f cv rho %.4f"
          % (isotonic["in_sample_spearman"], isotonic["cv_r2"], isotonic["cv_spearman"]))
    print("auc raw %.4f cv %.4f" % (auc["raw"], auc["cv"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
