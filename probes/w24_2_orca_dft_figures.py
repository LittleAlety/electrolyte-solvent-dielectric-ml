# W24-2 figure -- the first DFT-level instantiation of the paper rungs.
#
# Read-only: every number comes from probes/w24_2_orca_dft_summary.json and
# data/processed/w24_2_orca_dft_layer.csv.  Four panels:
#
# A -- the xTB -> DFT bridge: the GFN2 vertical IP against the ORCA r2SCAN-3c IP for
#      the 27 molecules that have both, with the identity line and the fitted line;
# B -- the anchor ladder: mean absolute error per layer, ours against the paper;
# C -- the rung displacements: our mean shift against the paper value;
# D -- the verdict board together with the quality-control facts that qualify it.

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes" / "w24_2_orca_dft_summary.json"
LAYER = ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
OUTPUT = ROOT / "probes" / "artifacts" / "w24_2_orca_bridge.png"

PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")
PAPER_ANCHOR_MAE = {"P0_koopmans": 1.377, "P0prime_gfn2_dscf": 4.481,
                    "P1_r2scan3c_gas": 0.251}
ANCHOR_LABEL = {"P0_koopmans": "P0 Koopmans",
                "P0prime_gfn2_dscf": "P0-prime GFN2 dSCF",
                "P1_r2scan3c_gas": "P1 r2SCAN-3c"}
PAPER_SHIFT = {("P0->P1", "ox"): -1.5496, ("P0->P1", "red"): 7.5919,
               ("P1->P2", "ox"): -2.3934, ("P1->P2", "red"): -2.1731}
AXIS_LABEL = {"ox": "氧化轴", "red": "还原轴"}
PAPER = "#9e9e9e"
OURS = "#1f4e79"


def configure_fonts() -> str:
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in installed:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["font.family"] = "sans-serif"
    return "sans-serif"


def read_rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value):
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def find_rung(rungs, name, axis):
    for entry in rungs:
        if (entry.get("rung") == name and entry.get("axis") == axis
                and not entry.get("insufficient")):
            return entry
    return None


def panel_a(ax, summary, rows):
    xs, ys, labels = [], [], []
    for row in rows:
        x = as_float(row.get("gfn2_ip_gas_eV"))
        y = as_float(row.get("orca_ip_gas_eV"))
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        labels.append(row.get("name") or "")
    xs = np.asarray(xs)
    ys = np.asarray(ys)
    bridge = summary.get("bridge") or {}
    ax.scatter(xs, ys, s=42, color=OURS, zorder=3, label="分子 n=" + str(len(xs)))
    if len(xs) >= 2:
        lo = float(min(xs.min(), ys.min())) - 1.0
        hi = float(max(xs.max(), ys.max())) + 1.0
        ax.plot([lo, hi], [lo, hi], color=PAPER, linestyle=":", linewidth=1.6,
                label="1:1 参考线")
        slope, intercept = np.polyfit(xs, ys, 1)
        grid = np.linspace(float(xs.min()), float(xs.max()), 50)
        ax.plot(grid, slope * grid + intercept, color="#c0392b", linewidth=1.8,
                label="线性拟合")
        for x, y, name in zip(xs, ys, labels):
            residual = float(y) - (slope * float(x) + intercept)
            if abs(residual) > 1.1:
                ax.annotate(name, (x, y), textcoords="offset points", xytext=(6, -10),
                            fontsize=7, color="#555555")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
    ax.set_xlabel("GFN2-xTB 垂直 dSCF 电离能 (eV)")
    ax.set_ylabel("ORCA r2SCAN-3c 垂直 dSCF 电离能 (eV)")
    ax.set_title("A  xTB -> DFT 尺度桥：秩一致、量级不一致", fontsize=10)
    note = ("Spearman rho = " + format(bridge.get("rho"), ".4f") + chr(10)
            + "Kendall tau_b = " + format(bridge.get("tau_b"), ".4f") + chr(10)
            + "偏移 " + format(bridge.get("offset_mean_eV"), ".3f") + " +/- "
            + format(bridge.get("offset_sd_eV"), ".3f") + " eV")
    ax.text(0.03, 0.97, note, transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="#f4f4f4", edgecolor="#cccccc"))
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.25)


def panel_b(ax, summary):
    anchors = summary.get("anchors") or {}
    keys = [key for key in ("P0_koopmans", "P0prime_gfn2_dscf", "P1_r2scan3c_gas")
            if key in anchors]
    positions = np.arange(len(keys), dtype=float)
    width = 0.36
    ours = [as_float((anchors[key] or {}).get("mae_eV")) or 0.0 for key in keys]
    paper = [PAPER_ANCHOR_MAE.get(key, 0.0) for key in keys]
    left = ax.bar(positions - width / 2, ours, width, color=OURS, label="本机 ORCA 6.1.1")
    right = ax.bar(positions + width / 2, paper, width, color=PAPER, label="母体论文")
    for group in (left, right):
        for bar in group:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    format(bar.get_height(), ".3f"), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(positions)
    ax.set_xticklabels([ANCHOR_LABEL[key] for key in keys], fontsize=8)
    ax.set_ylabel("气相锚点 MAE (eV)")
    ax.set_title("B  锚点复现：三层的量级都对上了", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.25, axis="y")


def panel_c(ax, summary):
    rungs = summary.get("rungs") or []
    keys = [key for key in (("P0->P1", "ox"), ("P0->P1", "red"),
                            ("P1->P2", "ox"), ("P1->P2", "red"))
            if find_rung(rungs, key[0], key[1])]
    positions = np.arange(len(keys), dtype=float)
    width = 0.36
    ours = [as_float(find_rung(rungs, key[0], key[1]).get("mean_shift_eV")) or 0.0
            for key in keys]
    paper = [PAPER_SHIFT.get(key, 0.0) for key in keys]
    left = ax.bar(positions - width / 2, ours, width, color=OURS, label="本机 r2SCAN-3c")
    right = ax.bar(positions + width / 2, paper, width, color=PAPER, label="母体论文")
    for group in (left, right):
        for bar in group:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height, format(height, ".2f"),
                    ha="center", va="bottom" if height >= 0 else "top", fontsize=8)
    ax.axhline(0.0, color="#333333", linewidth=1.0)
    ax.set_xticks(positions)
    ax.set_xticklabels([key[0] + " " + AXIS_LABEL[key[1]] for key in keys], fontsize=8)
    ax.set_ylabel("平均位移 (eV)")
    ax.set_title("C  台阶位移：符号与量级", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.25, axis="y")


def panel_d(ax, summary):
    ax.axis("off")
    pool = summary.get("pool") or {}
    bridge = summary.get("bridge") or {}
    unbound = summary.get("unbound_anion") or {}
    hypotheses = summary.get("hypotheses") or {}
    lines = ["W24-2  Axis A 的 DFT 级首次实例化",
             "分子 " + str(pool.get("n_molecules")) + "    ORCA 作业 "
             + str(pool.get("orca_jobs_ok")) + " 成功 / " + str(pool.get("orca_jobs_bad"))
             + " 失败",
             "唯一失败分子 nitrogen dioxide：NO2 是稳定自由基，预注册的中性态闭壳",
             "单重态对它物理上不可能（ORCA: multiplicity 1 is odd and number of",
             "electrons 23 is odd）",
             "",
             "气相阴离子不束缚 " + str(unbound.get("yes")) + "/" + str(unbound.get("n"))
             + "     xTB-DFT 桥 n = " + str(bridge.get("n")),
             "",
             "假设裁决"]
    for key in sorted(hypotheses):
        lines.append("  " + key + "   " + str((hypotheses[key] or {}).get("verdict")))
    ax.text(0.0, 1.0, chr(10).join(lines), va="top", ha="left", fontsize=9.5)


def main() -> int:
    configure_fonts()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    rows = read_rows(LAYER)
    figure, axes = plt.subplots(2, 2, figsize=(15, 11))
    panel_a(axes[0][0], summary, rows)
    panel_b(axes[0][1], summary)
    panel_c(axes[1][0], summary)
    panel_d(axes[1][1], summary)
    figure.suptitle("Week 24-2 · 用 ORCA r2SCAN-3c 首次实例化母体论文的 P_1 / P_2 台阶",
                    fontsize=15)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, bbox_inches="tight", dpi=150)
    plt.close(figure)
    print(json.dumps({"figure": str(OUTPUT), "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())