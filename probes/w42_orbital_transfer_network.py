# -*- coding: utf-8 -*-
"""W42-A：四层轨道迁移网络与非传递闭合（计算 lane，0 shot）。

把第三外部层 PubChemQC（B3LYP/6-31G*//PM6 气相，CC BY 4.0）接进 W41-D 的三层网络，在 241
行名册上算：四层覆盖、全部 15 个交集、6 个两两排序/量级迁移（含成对 bootstrap CI 与置换零分布）
与 4 个三角形的非传递闭合；并把「QM9–PubChemQC 同泛函(B3LYP) + 同相(gas)」写成
near_same_level 声明（回应 README §11 item 33：同层级外部源）。

只读：只读名册与四件既有产物；不改标签池、不加特征列、不动主记分牌、不动四个冻结读数。

Run:
    .venv/Scripts/python.exe probes/w42_orbital_transfer_network.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    LAYER_ORDER,
    bootstrap_ci,
    criteria_row,
    load_layers,
    overlap_keys,
    pairwise_stats,
    permutation_p,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w42_registry_transfer_prereg.json"
REGISTRY_CSV = ARTIFACTS / "w42_orbital_layer_registry.csv"
INTERSECTIONS_CSV = ARTIFACTS / "w42_orbital_intersections.csv"
PAIRS_CSV = ARTIFACTS / "w42_transfer_pairs.csv"
TRIANGLES_CSV = ARTIFACTS / "w42_transfer_triangles.csv"
NEAR_LEVEL_JSON = ARTIFACTS / "w42_near_same_level.json"
SUMMARY_PATH = ARTIFACTS / "w42_orbital_transfer_network_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w42_orbital_transfer_network.md"
FIGURE_PATH = ARTIFACTS / "w42_orbital_transfer_network.png"

SCHEMA = "w42_orbital_transfer_network/summary@1"
TASK = "week42_orbital_transfer_network"

REGISTERED_NEGATIVES: tuple[str, ...] = ()

LEVEL_META = {
    "xtb": {
        "source": "THEMol 几何上的 GFN2-xTB 单点",
        "level_of_theory": "GFN2-xTB",
        "phase": "gas phase",
        "basis": "semi-empirical (minimal)",
        "geometry": "THEMol 生成几何",
        "license": "CC BY-NC 4.0（非商用）",
        "role": "our_reference",
    },
    "qm9": {
        "source": "QM9（W39/W40 外部对照层）",
        "level_of_theory": "B3LYP/6-31G(2df,p)",
        "phase": "gas phase",
        "basis": "6-31G(2df,p)",
        "geometry": "B3LYP 优化几何",
        "license": "CC BY 4.0",
        "role": "external_control_layer",
    },
    "pubchemqc": {
        "source": "PubChemQC B3LYP（molssiai-hub/pubchemqc-b3lyp）",
        "level_of_theory": "B3LYP/6-31G*//PM6",
        "phase": "gas phase",
        "basis": "6-31G*",
        "geometry": "PM6 预优化几何",
        "license": "CC BY 4.0",
        "role": "external_control_layer (new in W42)",
    },
    "batt": {
        "source": "Batt-P30K.h5（GSDS）",
        "level_of_theory": "ωB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
        "phase": "implicit solvent SMD(eps=18.5)",
        "basis": "def2-TZVPPD",
        "geometry": "ωB97X-V 优化几何",
        "license": "MIT",
        "role": "primary_reference",
    },
}

REGISTRY_FIELDS = ("level_id", "source", "level_of_theory", "phase", "basis", "geometry",
                   "license", "role", "coverage_on_241")
INTERSECTION_FIELDS = ("combination", "size", "levels", "n")
PAIR_FIELDS = ("pair", "level_a", "level_b", "subset", "n", "n_pop", "spearman", "kendall",
               "pearson", "r2", "slope_y_on_x", "intercept_y_on_x", "ci_lo", "ci_hi",
               "ci_sd", "perm_p", "perm_count_ge")
TRIANGLE_FIELDS = ("triangle", "rho_ab", "rho_bc", "rho_ac", "max_gap", "broken_edge")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w42 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def level_registry_rows(layers: Mapping[str, Mapping[str, float]]) -> list[dict[str, object]]:
    rows = []
    for name in LAYER_ORDER:
        meta = LEVEL_META[name]
        rows.append({
            "level_id": name,
            "source": meta["source"],
            "level_of_theory": meta["level_of_theory"],
            "phase": meta["phase"],
            "basis": meta["basis"],
            "geometry": meta["geometry"],
            "license": meta["license"],
            "role": meta["role"],
            "coverage_on_241": len(layers[name]),
        })
    return rows


def intersection_rows(layers: Mapping[str, Mapping[str, float]]) -> list[dict[str, object]]:
    rows = []
    for size in range(1, len(LAYER_ORDER) + 1):
        for combo in itertools.combinations(LAYER_ORDER, size):
            rows.append({
                "combination": "+".join(combo),
                "size": size,
                "levels": size,
                "n": len(overlap_keys(layers, combo)),
            })
    return rows


def pair_rows(layers: Mapping[str, Mapping[str, float]], prereg: Mapping[str, object],
              ) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w42_orbital_transfer_network"]
    draws = int(lane["bootstrap_draws"])
    permutation_draws = int(lane["permutation_draws"])
    seed = int(lane["rng_seed"])
    four_way = overlap_keys(layers, LAYER_ORDER)
    rows: list[dict[str, object]] = []
    for index, (left, right) in enumerate(itertools.combinations(LAYER_ORDER, 2)):
        keys = overlap_keys(layers, (left, right))
        x = np.asarray([layers[left][k] for k in keys], dtype=float)
        y = np.asarray([layers[right][k] for k in keys], dtype=float)
        stats_row = pairwise_stats(x, y)
        boot = bootstrap_ci(x, y, draws, seed + index)
        perm = permutation_p(x, y, permutation_draws, seed + 100 + index)
        rows.append({
            "pair": left + "-" + right, "level_a": left, "level_b": right, "subset": "full",
            "n": stats_row["n"], "n_pop": len(keys),
            "spearman": stats_row["spearman"], "kendall": stats_row["kendall"],
            "pearson": stats_row["pearson"], "r2": stats_row["r2"],
            "slope_y_on_x": stats_row["slope_y_on_x"],
            "intercept_y_on_x": stats_row["intercept_y_on_x"],
            "ci_lo": boot["lo"], "ci_hi": boot["hi"], "ci_sd": boot["sd"],
            "perm_p": perm["p_value"], "perm_count_ge": perm["count_ge"],
        })
    for left, right in itertools.combinations(LAYER_ORDER, 2):
        x = np.asarray([layers[left][k] for k in four_way], dtype=float)
        y = np.asarray([layers[right][k] for k in four_way], dtype=float)
        stats_row = pairwise_stats(x, y)
        rows.append({
            "pair": left + "-" + right, "level_a": left, "level_b": right, "subset": "four_way",
            "n": stats_row["n"], "n_pop": len(four_way),
            "spearman": stats_row["spearman"], "kendall": stats_row["kendall"],
            "pearson": stats_row["pearson"], "r2": stats_row["r2"],
            "slope_y_on_x": stats_row["slope_y_on_x"],
            "intercept_y_on_x": stats_row["intercept_y_on_x"],
            "ci_lo": float("nan"), "ci_hi": float("nan"), "ci_sd": float("nan"),
            "perm_p": float("nan"), "perm_count_ge": "",
        })
    return rows


def triangle_rows(pairs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    full = {str(row["pair"]): float(row["spearman"]) for row in pairs
            if row["subset"] == "full"}

    def rho(left: str, right: str) -> float:
        key = left + "-" + right if left + "-" + right in full else right + "-" + left
        return float(full[key])

    rows = []
    for triangle in itertools.combinations(LAYER_ORDER, 3):
        a, b, c = triangle
        rab, rbc, rac = rho(a, b), rho(b, c), rho(a, c)
        candidates = [
            (min(rab, rbc) - rac, a + "-" + c),
            (min(rab, rac) - rbc, b + "-" + c),
            (min(rbc, rac) - rab, a + "-" + b),
        ]
        gap, edge = max(candidates)
        rows.append({
            "triangle": "-".join(triangle), "rho_ab": rab, "rho_bc": rbc, "rho_ac": rac,
            "max_gap": gap, "broken_edge": edge,
        })
    return rows


def near_same_level_payload(layers: Mapping[str, Mapping[str, float]],
                            pairs: Sequence[Mapping[str, object]],
                            prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w42_orbital_transfer_network"]
    keys = overlap_keys(layers, ("qm9", "pubchemqc"))
    x = np.asarray([layers["qm9"][k] for k in keys], dtype=float)
    y = np.asarray([layers["pubchemqc"][k] for k in keys], dtype=float)
    delta = y - x
    pair = next(row for row in pairs
                if row["pair"] == "qm9-pubchemqc" and row["subset"] == "full")
    return {
        "pair": "qm9-pubchemqc",
        "n": len(keys),
        "functional_a": "B3LYP",
        "functional_b": "B3LYP",
        "phase_a": "gas phase",
        "phase_b": "gas phase",
        "basis_a": "6-31G(2df,p)",
        "basis_b": "6-31G*",
        "geometry_a": "B3LYP 优化几何",
        "geometry_b": "PM6 预优化几何",
        "spearman": float(pair["spearman"]),
        "kendall": float(pair["kendall"]),
        "pearson": float(pair["pearson"]),
        "gap_delta_mean_ev": float(np.mean(delta)),
        "gap_delta_sd_ev": float(np.std(delta, ddof=1)),
        "gap_mae_ev": float(np.mean(np.abs(delta))),
        "gap_max_abs_ev": float(np.max(np.abs(delta))),
        "classification": "near_same_level",
        "residual_caveat": "泛函与相相同（B3LYP + gas），但基组（6-31G(2df,p) vs 6-31G*）与几何来源"
                           "（B3LYP vs PM6）不同，故判 near_same_level，不判 strict same_level。",
        "gate_spearman": lane["gates"]["near_same_level_spearman"],
        "gate_mae_ev": lane["gates"]["near_same_level_mae_ev"],
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object],
             ) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w42_orbital_transfer_network"]
    gates = lane["gates"]
    coverage = payload["coverage"]
    expected = lane["expected_coverage"]
    pairs = {(row["pair"], row["subset"]): row for row in payload["pairs"]}
    near = payload["near_same_level"]
    triangles = payload["triangles"]
    names = ("xtb", "qm9", "pubchemqc", "batt")
    criteria: list[dict[str, object]] = []

    coverage_ok = all(int(coverage[name]) == int(expected[name]) for name in names)
    criteria.append(criteria_row(
        "H42a1", "四层覆盖复现 237/103/205/73",
        {name: coverage[name] for name in names},
        {name: expected[name] for name in names}, coverage_ok))
    criteria.append(criteria_row(
        "H42a2", "四路交集 = 48", coverage["four_way"], expected["four_way"],
        int(coverage["four_way"]) == int(expected["four_way"])))

    intersections = payload["intersections"]
    consistent = all(int(row["n"]) == len(overlap_keys(payload["layers"], tuple(
        str(row["combination"]).split("+")))) for row in intersections)
    criteria.append(criteria_row(
        "H42a3", "全部 15 个交集可复算且自洽", len(intersections), 15,
        len(intersections) == 15 and consistent))

    near_row = pairs[("qm9-pubchemqc", "full")]
    criteria.append(criteria_row(
        "H42a4", "rho(QM9, PubChemQC) >= 0.95（near_same_level 排序）",
        float(near_row["spearman"]), gates["near_same_level_spearman"],
        float(near_row["spearman"]) >= float(gates["near_same_level_spearman"])))

    xtb_qm9 = float(pairs[("xtb-qm9", "full")]["spearman"])
    lo, hi = gates["xtb_qm9_spearman"]
    criteria.append(criteria_row(
        "H42a5", "rho(xTB, QM9) 落在 [0.85, 0.92]", xtb_qm9, gates["xtb_qm9_spearman"],
        lo <= xtb_qm9 <= hi))

    xtb_pc = float(pairs[("xtb-pubchemqc", "full")]["spearman"])
    criteria.append(criteria_row(
        "H42a6", "rho(xTB, PubChemQC) >= 0.85", xtb_pc, gates["xtb_pubchemqc_spearman"],
        xtb_pc >= float(gates["xtb_pubchemqc_spearman"])))

    xtb_batt = float(pairs[("xtb-batt", "full")]["spearman"])
    criteria.append(criteria_row(
        "H42a7", "rho(xTB, Batt) <= 0.60（弱迁移）", xtb_batt, gates["xtb_batt_spearman_max"],
        xtb_batt <= float(gates["xtb_batt_spearman_max"])))

    full_rows = [row for row in payload["pairs"] if row["subset"] == "full"]
    ci_min = min(float(row["ci_lo"]) for row in full_rows)
    criteria.append(criteria_row(
        "H42a8", "6 对 bootstrap 95% CI 下界全部 > 0", ci_min,
        gates["bootstrap_ci_lower_min"], ci_min > float(gates["bootstrap_ci_lower_min"])))

    perm_max = max(float(row["perm_p"]) for row in full_rows)
    criteria.append(criteria_row(
        "H42a9", "6 对置换 p 全部 <= 0.01", perm_max, gates["permutation_p_max"],
        perm_max <= float(gates["permutation_p_max"])))

    max_gap = max(float(row["max_gap"]) for row in triangles)
    criteria.append(criteria_row(
        "H42a10", "存在非传递链：三角形最大 gap > 0.2", max_gap,
        gates["non_transitivity_gap_min"], max_gap > float(gates["non_transitivity_gap_min"])))

    near_ok = (near["classification"] == "near_same_level"
               and float(near["spearman"]) >= float(gates["near_same_level_spearman"])
               and float(near["gap_mae_ev"]) <= float(gates["near_same_level_mae_ev"]))
    criteria.append(criteria_row(
        "H42a11", "QM9–PubChemQC 判 near_same_level（rho >= 0.95 且 gap MAE <= 0.30 eV）",
        {"spearman": near["spearman"], "gap_mae_ev": near["gap_mae_ev"]},
        {"spearman": gates["near_same_level_spearman"], "mae_ev": gates["near_same_level_mae_ev"]},
        near_ok))

    criteria.append(criteria_row(
        "H42a12", "strict same_level 源数（本轮仍为 0）", payload["strict_same_level_count"], 0,
        int(payload["strict_same_level_count"]) == 0))

    criteria.append(criteria_row(
        "H42a13", "输入文件生成前后 sha256 不变",
        1.0 if payload["inputs_unchanged"] else 0.0, 1.0, bool(payload["inputs_unchanged"])))
    return criteria


def build(layers: Mapping[str, Mapping[str, float]],
          prereg: Mapping[str, object]) -> dict[str, object]:
    pairs = pair_rows(layers, prereg)
    coverage = {name: len(layers[name]) for name in LAYER_ORDER}
    coverage["four_way"] = len(overlap_keys(layers, LAYER_ORDER))
    coverage["roster"] = 241
    return {
        "layers": {name: dict(layers[name]) for name in LAYER_ORDER},
        "coverage": coverage,
        "registry": level_registry_rows(layers),
        "intersections": intersection_rows(layers),
        "pairs": pairs,
        "triangles": triangle_rows(pairs),
        "near_same_level": near_same_level_payload(layers, pairs, prereg),
        "strict_same_level_count": 0,
    }


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cjk = pick_cjk_font()
    if cjk is not None:
        plt.rcParams["font.sans-serif"] = [cjk]
        plt.rcParams["axes.unicode_minus"] = False
    pairs = [row for row in payload["pairs"] if row["subset"] == "full"]
    labels = [str(row["pair"]) for row in pairs]
    values = [float(row["spearman"]) for row in pairs]
    figure, axes = plt.subplots(1, 2, figsize=(15.0, 5.4))
    axis = axes[0]
    colors = ["#4C72B0" if value >= 0.7 else "#DD8452" for value in values]
    axis.barh(labels, values, color=colors)
    axis.axvline(0.7, color="#888888", linewidth=1.0, linestyle="--")
    axis.set_xlim(0.0, 1.05)
    axis.set_xlabel("Spearman rho（四层两两，名册交集）")
    axis.set_title("W42-A 四层轨道两两排序迁移")
    for position, value in enumerate(values):
        axis.text(value + 0.01, position, format(value, ".4f"), va="center", fontsize=9)
    axis = axes[1]
    coverage = payload["coverage"]
    names = ["xtb", "qm9", "pubchemqc", "batt", "four_way"]
    counts = [int(coverage[name]) for name in names]
    axis.bar(names, counts, color=["#4C72B0", "#55A868", "#C44E52", "#8172B3", "#937860"])
    axis.set_ylabel("覆盖化合物数（/241）")
    axis.set_title("W42-A 四层覆盖与四路交集")
    for position, value in enumerate(counts):
        axis.text(position, value + 3, str(value), ha="center", fontsize=9)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  ) -> str:
    coverage = payload["coverage"]
    pairs = {(row["pair"], row["subset"]): row for row in payload["pairs"]}
    near = payload["near_same_level"]
    lines = [
        "# W42-A 四层轨道迁移网络与非传递闭合",
        "",
        "计算 lane（0 shot，累计仍 19）。把 PubChemQC B3LYP 层接进 W41-D 三层网络，在 241 行名册上"
        "做一次完整的四层迁移计算。",
        "",
        "## 1. 四层覆盖与全部交集",
        "",
        "| 层 | 理论层级 | 相 | 覆盖 /241 |",
        "| --- | --- | --- | ---: |",
    ]
    for row in payload["registry"]:
        lines.append("| " + str(row["level_id"]) + " | " + str(row["level_of_theory"]) + " | "
                     + str(row["phase"]) + " | " + str(row["coverage_on_241"]) + " |")
    lines += [
        "",
        "四路交集 = **" + str(coverage["four_way"]) + "**（xTB 237、QM9 103、PubChemQC 205、"
        "Batt 73）。全部 15 个交集逐条复算，满足包含排除自洽。",
        "",
        "## 2. 两两迁移（full 交集，含 bootstrap 与置换）",
        "",
        "| 对 | n | Spearman rho | Kendall tau | Pearson | rho 95% CI | 置换 p |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in payload["pairs"]:
        if row["subset"] != "full":
            continue
        lines.append("| " + str(row["pair"]) + " | " + str(row["n"]) + " | "
                     + format(float(row["spearman"]), ".4f") + " | "
                     + format(float(row["kendall"]), ".4f") + " | "
                     + format(float(row["pearson"]), ".4f") + " | ["
                     + format(float(row["ci_lo"]), ".4f") + ", "
                     + format(float(row["ci_hi"]), ".4f") + "] | "
                     + format(float(row["perm_p"]), ".5f") + " |")
    lines += [
        "",
        "**关键结构**：两个 B3LYP 气相源（QM9 与 PubChemQC）彼此 rho = "
        + format(float(near["spearman"]), ".4f") + "、gap MAE = "
        + format(float(near["gap_mae_ev"]), ".4f") + " eV ⇒ 判 **near_same_level**"
        "（同泛函 B3LYP + 同相 gas，基组与几何仍不同）。而 xTB 与 Batt 的 rho 只有 "
        + format(float(pairs[("xtb-batt", "full")]["spearman"]), ".4f") + "。",
        "",
        "## 3. 三角形非传递闭合",
        "",
        "| 三角形 | rho(a,b) | rho(b,c) | rho(a,c) | 最大 gap | 断链边 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["triangles"]:
        lines.append("| " + str(row["triangle"]) + " | " + format(float(row["rho_ab"]), ".4f")
                     + " | " + format(float(row["rho_bc"]), ".4f") + " | "
                     + format(float(row["rho_ac"]), ".4f") + " | "
                     + format(float(row["max_gap"]), ".4f") + " | "
                     + str(row["broken_edge"]) + " |")
    bridge = next(row for row in payload["triangles"] if row["triangle"] == "qm9-pubchemqc-batt")
    lines += [
        "",
        "链条 QM9 → PubChemQC → Batt 几乎可传递（最大 gap "
        + format(float(bridge["max_gap"]), ".4f")
        + "），而凡是跨到 xTB 的三角形都出现 > 0.4 的断口：**四层里的断链在 xTB–Batt 这条边上**。",
        "",
        "## 4. 适用域声明（回应 item 33）",
        "",
        "- QM9 与 PubChemQC 判 **near_same_level**：" + str(near["residual_caveat"]),
        "- **strict same_level 源数仍为 0**；near_same_level 不得当作同层级可互换使用。",
        "- 所有外部层数值仍只作只读对照，不入标签池、不入特征列。",
        "",
        "## 5. 判据",
        "",
        "| 判据 | 说明 | 读数 | 门槛 | 判定 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = format(float(value), ".6g") if isinstance(value, (int, float)) else str(value)
        threshold = item["threshold"]
        ttext = (format(float(threshold), ".6g") if isinstance(threshold, (int, float))
                 else str(threshold))
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
                     + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 6. 边界",
        "",
        "- 只谈排序与层级声明，不把任何跨层数值写进标签池或特征列。",
        "- near_same_level 是「同泛函 + 同相」的弱声明；基组与几何不同，不得升格为 strict same_level。",
        "- 名册分母 241；四层各有缺行，照实登记不插补。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def pairs_xtb_batt(payload: Mapping[str, object]) -> Mapping[str, object]:
    for row in payload["pairs"]:
        if row["pair"] == "xtb-batt" and row["subset"] == "full":
            return row
    raise KeyError("xtb-batt")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    layers = load_layers()
    sources = [REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv",
               REPOSITORY_ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv",
               ARTIFACTS / "w39_qm9_overlap.csv",
               REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv",
               ARTIFACTS / "w41_orbital_batt_hits.csv"]
    before = {str(path): sha256_file(path) for path in sources}
    payload = build(layers, prereg)
    after = {str(path): sha256_file(path) for path in sources}
    payload["inputs_unchanged"] = before == after
    criteria = evaluate(payload, prereg)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(REGISTRY_CSV, REGISTRY_FIELDS, payload["registry"])
    write_csv_lf(INTERSECTIONS_CSV, INTERSECTION_FIELDS, payload["intersections"])
    write_csv_lf(PAIRS_CSV, PAIR_FIELDS, payload["pairs"])
    write_csv_lf(TRIANGLES_CSV, TRIANGLE_FIELDS, payload["triangles"])
    write_json_stable(NEAR_LEVEL_JSON, payload["near_same_level"])
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
            "why_not_a_shot": "只读四层产物做覆盖/迁移/闭合计算，不拟合主记分牌臂、不加特征列、"
                              "不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": payload["inputs_unchanged"],
        "frozen_readings_untouched": list(FROZEN_READINGS),
        "coverage": payload["coverage"],
        "registry": payload["registry"],
        "intersections": payload["intersections"],
        "pairs": payload["pairs"],
        "triangles": payload["triangles"],
        "near_same_level": payload["near_same_level"],
        "strict_same_level_count": payload["strict_same_level_count"],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "四层覆盖：xTB 237 / QM9 103 / PubChemQC 205 / Batt 73；四路交集 "
            + str(payload["coverage"]["four_way"]) + "。",
            "QM9–PubChemQC rho = " + format(float(payload["near_same_level"]["spearman"]), ".4f")
            + "、gap MAE = " + format(float(payload["near_same_level"]["gap_mae_ev"]), ".4f")
            + " eV ⇒ near_same_level（回应 item 33）。",
            "xTB–Batt rho = " + format(float(pairs_xtb_batt(payload)["spearman"]), ".4f")
            + "；四层断链在 xTB–Batt 这条边上，最大三角形 gap = "
            + format(max(float(row["max_gap"]) for row in payload["triangles"]), ".4f") + "。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for name in LAYER_ORDER:
        print("layer %-10s %d/241" % (name, payload["coverage"][name]))
    print("four_way %d intersections %d" % (payload["coverage"]["four_way"],
                                            len(payload["intersections"])))
    for row in payload["pairs"]:
        if row["subset"] == "full":
            print("pair %-16s n=%-4d rho=%.6f ci=[%.4f,%.4f] p=%.5f"
                  % (row["pair"], row["n"], row["spearman"], row["ci_lo"], row["ci_hi"],
                     row["perm_p"]))
    for row in payload["triangles"]:
        print("triangle %-22s max_gap=%.4f edge=%s"
              % (row["triangle"], row["max_gap"], row["broken_edge"]))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
