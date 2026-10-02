"""W23-1 figure -- what an ALPB dielectric background does to the orbital layer.

Read-only: every number comes from probes/w23_orbital_medium_summary.json and
data/processed/w23_orbital_medium_layer.csv, both written by
probes/w23_orbital_medium.py.  Four panels:

* A -- per-channel mean shift against the dielectric ladder, for both states;
* B -- per-compound dHOMO distribution per rung (box), free state vs Li+ state;
* C -- ordering stability rho(gas -> medium) against the dielectric ladder,
       with the 0.90 pre-registered line;
* D -- the section 9 Batt-subset rho of all nine cheap layers.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes" / "w23_orbital_medium_summary.json"
LAYER = ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv"
OUTPUT = ROOT / "probes" / "artifacts" / "w23_orbital_medium_shift.png"

PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")
MEDIA = ("thf", "benzaldehyde", "water")
EPSILON = {"thf": 7.58, "benzaldehyde": 18.0, "water": 80.4}
STATE_COLOUR = {"free": "#1f4e79", "li": "#c0392b"}
STATE_LABEL = {"free": "自由态 C_0", "li": "Li+ 配位态 C_1"}
CHANNEL_LABEL = {"homo": "dHOMO", "lumo": "dLUMO", "gap": "dgap"}


def configure_fonts() -> str:
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in installed:
            plt.rcParams["font.family"] = name
            return name
    plt.rcParams["font.family"] = "sans-serif"
    return "sans-serif"


def read_rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value):
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return None


def build_figure(font_name: str):
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    rows = read_rows(LAYER)
    figure, axes = plt.subplots(2, 2, figsize=(13.2, 9.0))
    x = [EPSILON[medium] for medium in MEDIA]

    # ---- A: mean shift per channel ---------------------------------------- #
    panel = axes[0][0]
    for state in ("free", "li"):
        for channel, style in (("homo", "-o"), ("lumo", "--s"), ("gap", ":^")):
            values = [summary["channel_shifts"][state][medium][channel]["delta_mean_eV"]
                      for medium in MEDIA]
            panel.plot(x, values, style, color=STATE_COLOUR[state],
                       alpha={"homo": 1.0, "lumo": 0.72, "gap": 0.45}[channel],
                       label=STATE_LABEL[state] + " · " + CHANNEL_LABEL[channel],
                       markersize=5.2, linewidth=1.7)
    panel.axhline(0.0, color="#888888", linewidth=1.0)
    panel.set_xscale("log")
    panel.set_xlabel("ALPB 介电常数 eps（对数轴）", fontsize=10)
    panel.set_ylabel("相对气相的位移 (eV)", fontsize=10)
    panel.set_title("A 轨道条件位移 vs 介电阶梯", fontsize=11.5)
    panel.legend(fontsize=7.2, ncol=2, framealpha=0.95)
    panel.grid(alpha=0.25, linewidth=0.6)
    panel.annotate("自由态：均值 < 离散\nLi+ 态：双轨道整体上移 3–4 eV",
                   xy=(0.03, 0.72), xycoords="axes fraction", fontsize=8.4,
                   bbox=dict(boxstyle="round,pad=0.35", facecolor="#fdf6e3", edgecolor="#c9b458"))

    # ---- B: per-compound dHOMO boxes -------------------------------------- #
    panel = axes[0][1]
    positions, data, colours, labels = [], [], [], []
    base = 1.0
    for state in ("free", "li"):
        for index, medium in enumerate(MEDIA):
            values = [as_float(row[state + "_" + medium + "_d_homo_eV"]) for row in rows
                      if row["motif_class"] in ("lone_pair", "anion_halide", "aromatic_pi", "alkene_pi")]
            values = [value for value in values if value is not None]
            positions.append(base + index * 0.85)
            data.append(values)
            colours.append(STATE_COLOUR[state])
            labels.append(STATE_LABEL[state][:2] + "\n" + medium[:4])
        base += 3.1
    box = panel.boxplot(data, positions=positions, widths=0.6, patch_artist=True, showfliers=False)
    for patch, colour in zip(box["boxes"], colours):
        patch.set_facecolor(colour)
        patch.set_alpha(0.42)
        patch.set_edgecolor(colour)
    for element in ("whiskers", "caps", "medians"):
        for item in box[element]:
            item.set_color("#333333")
    panel.axhline(0.0, color="#888888", linewidth=1.0)
    panel.set_xticks(positions)
    panel.set_xticklabels(labels, fontsize=7.4)
    panel.set_ylabel("逐化合物 dHOMO (eV)", fontsize=10)
    panel.set_title("B dHOMO 的逐化合物分布", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6, axis="y")

    # ---- C: ordering stability vs the ladder ------------------------------ #
    panel = axes[1][0]
    for state in ("free", "li"):
        for channel, style in (("homo", "-o"), ("lumo", "--s")):
            values = []
            for medium in MEDIA:
                match = [row for row in summary["rank_rows"]
                         if row["state"] == state and row["channel"] == channel
                         and row["left"] == "gas" and row["right"] == medium]
                values.append(match[0]["spearman_rho"] if match else float("nan"))
            panel.plot(x, values, style, color=STATE_COLOUR[state],
                       alpha={"homo": 1.0, "lumo": 0.65}[channel],
                       label=STATE_LABEL[state] + " · " + channel.upper(),
                       markersize=5.2, linewidth=1.7)
    panel.axhline(0.90, color="#c0392b", linestyle="-.", linewidth=1.2)
    panel.text(x[-1], 0.903, "H4 门槛 0.90", ha="right", va="bottom", fontsize=8.2, color="#c0392b")
    panel.set_xscale("log")
    panel.set_ylim(0.78, 1.005)
    panel.set_xlabel("ALPB 介电常数 eps（对数轴）", fontsize=10)
    panel.set_ylabel("rho(气相, 介质)", fontsize=10)
    panel.set_title("C 排序稳定性（对照：C_1 台阶的 lumo rho = 0.2296）", fontsize=11.5)
    panel.legend(fontsize=7.6, framealpha=0.95)
    panel.grid(alpha=0.25, linewidth=0.6)

    # ---- D: section 9 layer comparison ------------------------------------ #
    panel = axes[1][1]
    order = ["P0_themol_geometry_w21_1", "C0_gas", "C1_gas", "C0_thf", "C0_benzaldehyde",
             "C0_water", "C1_thf", "C1_benzaldehyde", "C1_water"]
    arms = summary["batt"]["arms"]
    labels, values, colours = [], [], []
    for name in order:
        if name not in arms:
            continue
        labels.append(name.replace("_", "\n"))
        values.append(arms[name]["spearman_rho"])
        colours.append("#c0392b" if name.startswith("C1_") else
                       ("#1f4e79" if name.startswith("C0_") else "#7f8c8d"))
    positions = np.arange(len(values))
    panel.bar(positions, values, color=colours, alpha=0.85, width=0.62)
    for position, value in zip(positions, values):
        panel.text(position, value + 0.004, "%.4f" % value, ha="center", va="bottom", fontsize=7.4)
    panel.set_xticks(positions)
    panel.set_xticklabels(labels, fontsize=6.6)
    panel.set_ylim(min(values) - 0.03, max(values) + 0.02)
    panel.set_ylabel("rho vs Batt 参考层", fontsize=10)
    panel.set_title("D §9 Batt 子集（49 化合物）九层并排", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6, axis="y")

    figure.suptitle("W23-1 · GFN2-xTB + ALPB 三档介电阶梯下的轨道条件位移（246 化合物 x 8 臂）"
                    "    字体：" + font_name, fontsize=12.6)
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    return figure


def main() -> int:
    font_name = configure_fonts()
    figure = build_figure(font_name)
    figure.savefig(OUTPUT, bbox_inches="tight", dpi=150)
    print(json.dumps({"figure": str(OUTPUT), "font": font_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
