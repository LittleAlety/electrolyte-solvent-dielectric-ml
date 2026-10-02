"""W23-2 figure -- what the GFN2-xTB dSCF redox arm actually measured.

Read-only: every number comes from probes/w23_redox_dscf_summary.json,
data/processed/w23_redox_dscf_layer.csv and the RX-392 reference layer
(data/processed/redox_merged.csv).  Six panels:

* A -- the IP / EA four-medium distributions (adiabatic, neutral molecules);
* B -- the per-compound solvent shifts dIP and dEA per rung;
* C -- ordering stability rho(gas -> medium) for both channels;
* D -- the anion "not bound" signature share per rung (the A5 test);
* E -- dSCF IP against the RX-392 reference layer, n = 10, with the 1:1 line;
* F -- the Koopmans comparison, dSCF IP/EA against -eps_HOMO / -eps_LUMO.
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
SUMMARY = ROOT / "probes" / "w23_redox_dscf_summary.json"
LAYER = ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
REFERENCE = ROOT / "data" / "processed" / "redox_merged.csv"
OUTPUT = ROOT / "probes" / "artifacts" / "w23_redox_dscf_shift.png"

PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")
MEDIA = ("gas", "thf", "benzaldehyde", "water")
SOLVENTS = ("thf", "benzaldehyde", "water")
EPSILON = {"gas": 1.0, "thf": 7.58, "benzaldehyde": 18.0, "water": 80.4}
CHANNEL_COLOUR = {"ip": "#1f4e79", "ea": "#c0392b"}
CHANNEL_LABEL = {"ip": "IP 电离能", "ea": "EA 电子亲和能"}


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
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def neutral_rows(rows, channel):
    keep = []
    for row in rows:
        if row["charge_class"] != "neutral":
            continue
        values = [as_float(row[channel + "_" + medium + "_eV"]) for medium in MEDIA]
        if all(value is not None for value in values):
            keep.append(row)
    return keep


def style_boxes(box, colours):
    for patch, colour in zip(box["boxes"], colours):
        patch.set_facecolor(colour)
        patch.set_alpha(0.42)
        patch.set_edgecolor(colour)
    for element in ("whiskers", "caps"):
        for item in box[element]:
            item.set_color("#333333")
    for item in box["medians"]:
        item.set_color("#111111")
        item.set_linewidth(1.6)


def build_figure(font_name: str):
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    rows = read_rows(LAYER)
    figure, axes = plt.subplots(2, 3, figsize=(19.5, 9.8))

    # ---- A: the four-medium IP / EA distributions -------------------------- #
    panel = axes[0][0]
    positions, data, colours, labels = [], [], [], []
    for index, medium in enumerate(MEDIA):
        for channel, offset in (("ip", -0.18), ("ea", 0.18)):
            values = [as_float(row[channel + "_" + medium + "_eV"])
                      for row in neutral_rows(rows, channel)]
            positions.append(index + offset)
            data.append(values)
            colours.append(CHANNEL_COLOUR[channel])
        labels.append("%s\n(eps=%.2f)" % (medium, EPSILON[medium]))
    box = panel.boxplot(data, positions=positions, widths=0.3, patch_artist=True,
                        showfliers=False)
    style_boxes(box, colours)
    panel.set_xticks(range(len(MEDIA)))
    panel.set_xticklabels(labels, fontsize=8.0)
    panel.set_ylabel("绝热 %s / %s (eV)" % (CHANNEL_LABEL["ip"], CHANNEL_LABEL["ea"]), fontsize=10)
    panel.set_title("A 四介质 IP / EA 分布（中性分子，绝热口径）", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6, axis="y")
    handles = [plt.Line2D([], [], color=CHANNEL_COLOUR[key], linewidth=7, alpha=0.42,
                          label=CHANNEL_LABEL[key]) for key in ("ip", "ea")]
    panel.legend(handles=handles, fontsize=8.2, framealpha=0.95)

    # ---- B: the per-compound solvent shifts -------------------------------- #
    panel = axes[0][1]
    positions, data, colours, labels = [], [], [], []
    for index, medium in enumerate(SOLVENTS):
        for channel, offset in (("ip", -0.18), ("ea", 0.18)):
            values = [as_float(row["d_" + channel + "_" + medium + "_eV"])
                      for row in neutral_rows(rows, channel)]
            positions.append(index + offset)
            data.append(values)
            colours.append(CHANNEL_COLOUR[channel])
        labels.append("%s\n(eps=%.2f)" % (medium, EPSILON[medium]))
    box = panel.boxplot(data, positions=positions, widths=0.3, patch_artist=True,
                        showfliers=False)
    style_boxes(box, colours)
    panel.axhline(0.0, color="#888888", linewidth=1.1)
    panel.set_xticks(range(len(SOLVENTS)))
    panel.set_xticklabels(labels, fontsize=8.0)
    panel.set_ylabel("相对气相的位移 (eV)", fontsize=10)
    panel.set_title("B 溶剂化位移 dIP / dEA 的逐化合物分布", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6, axis="y")
    panel.annotate("dIP 全部为负、dEA 全部为正\n= 溶剂化稳定离子态", xy=(0.03, 0.06),
                   xycoords="axes fraction", fontsize=8.4,
                   bbox=dict(boxstyle="round,pad=0.35", facecolor="#fdf6e3",
                             edgecolor="#c9b458"))

    # ---- C: ordering stability against the ladder --------------------------- #
    panel = axes[0][2]
    x = [EPSILON[medium] for medium in SOLVENTS]
    for channel, style in (("ip", "-o"), ("ea", "--s")):
        values = []
        for medium in SOLVENTS:
            match = [row for row in summary["rank_rows"]
                     if row["charge_class"] == "neutral" and row["channel"] == channel
                     and row["left"] == "gas" and row["right"] == medium]
            values.append(match[0]["spearman_rho"] if match else float("nan"))
        panel.plot(x, values, style, color=CHANNEL_COLOUR[channel],
                   label=CHANNEL_LABEL[channel], markersize=5.6, linewidth=1.8)
        for xi, value in zip(x, values):
            panel.annotate("%.3f" % value, (xi, value), textcoords="offset points",
                           xytext=(0, 6), ha="center", fontsize=7.6,
                           color=CHANNEL_COLOUR[channel])
    panel.axhline(0.90, color="#7f8c8d", linestyle="-.", linewidth=1.1)
    panel.text(x[-1], 0.903, "0.90 参考线", ha="right", va="bottom", fontsize=7.8,
               color="#7f8c8d")
    panel.set_xscale("log")
    panel.set_ylim(0.80, 1.005)
    panel.set_xlabel("ALPB 介电常数 eps（对数轴）", fontsize=10)
    panel.set_ylabel("rho(气相, 介质) 排序稳定性", fontsize=10)
    panel.set_title("C 换溶剂后 IP / EA 的排序是否守住", fontsize=11.5)
    panel.legend(fontsize=8.2, framealpha=0.95)
    panel.grid(alpha=0.25, linewidth=0.6)

    # ---- D: the anion not-bound signature ----------------------------------- #
    panel = axes[1][0]
    shares = [summary["anion_signature"]["by_medium"][medium]["share"] for medium in MEDIA]
    counts = [summary["anion_signature"]["by_medium"][medium]["n"] for medium in MEDIA]
    positions = np.arange(len(MEDIA))
    panel.bar(positions, shares, color=["#c0392b" if value >= 0.5 else "#1f4e79" for value in shares],
              alpha=0.85, width=0.6)
    for position, value, count in zip(positions, shares, counts):
        panel.text(position, value + 0.02, "%.3f\n(n=%d)" % (value, count), ha="center",
                   va="bottom", fontsize=8.0)
    panel.axhline(0.50, color="#c0392b", linestyle="-.", linewidth=1.2)
    panel.text(0.02, 0.52, "H4 气相门槛 0.50", fontsize=8.0, color="#c0392b")
    panel.set_xticks(positions)
    panel.set_xticklabels(["%s\n(eps=%.2f)" % (medium, EPSILON[medium]) for medium in MEDIA],
                          fontsize=8.0)
    panel.set_ylim(0.0, 1.15)
    panel.set_ylabel("阴离子最高占据轨道能 > 0 的占比", fontsize=10)
    panel.set_title("D 阴离子「不束缚」签名 vs 介质（W22 评审 A5）", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6, axis="y")

    # ---- E: the RX-392 external comparison ---------------------------------- #
    panel = axes[1][1]
    reference = []
    if REFERENCE.is_file():
        by_key = {row["inchikey"]: row for row in rows}
        for entry in read_rows(REFERENCE):
            if entry.get("source") != "RX-392":
                continue
            row = by_key.get(str(entry.get("inchikey") or ""))
            if row is None:
                continue
            reference_ip = as_float(entry.get("IP"))
            ours = as_float(row["ip_gas_eV"])
            if reference_ip is None or ours is None:
                continue
            reference.append((reference_ip, ours))
    if reference:
        reference_ip = np.array([item[0] for item in reference])
        ours = np.array([item[1] for item in reference])
        low = float(min(reference_ip.min(), ours.min())) - 1.5
        high = float(max(reference_ip.max(), ours.max())) + 1.5
        panel.plot([low, high], [low, high], color="#888888", linestyle="--", linewidth=1.1,
                   label="1:1")
        panel.scatter(reference_ip, ours, s=52, color="#1f4e79", alpha=0.85, zorder=3,
                      label="n = %d" % len(reference))
        panel.set_xlim(low, high)
        panel.set_ylim(low, high)
        entry = summary["reference_step"].get("ip_gas") or {}
        panel.annotate("rho = %.3f\n平均有符号差 = %.2f eV\n（含自由能约定差）"
                       % (entry.get("spearman_rho", float("nan")),
                          entry.get("mean_signed_difference_eV", float("nan"))),
                       xy=(0.04, 0.72), xycoords="axes fraction", fontsize=8.4,
                       bbox=dict(boxstyle="round,pad=0.35", facecolor="#fdf6e3",
                                 edgecolor="#c9b458"))
        panel.legend(fontsize=8.2, loc="lower right", framealpha=0.95)
    else:
        panel.text(0.5, 0.5, "RX-392 交集不足", ha="center", va="center", fontsize=11)
    panel.set_xlabel("RX-392 参考 IP (eV)", fontsize=10)
    panel.set_ylabel("本臂 dSCF 气相 IP (eV)", fontsize=10)
    panel.set_title("E 量级偏、排序也未守住：dSCF vs RX-392", fontsize=11.5)
    panel.grid(alpha=0.25, linewidth=0.6)

    # ---- F: the Koopmans comparison ----------------------------------------- #
    panel = axes[1][2]
    for channel, orbital in (("ip", "homo"), ("ea", "lumo")):
        xs, ys = [], []
        for row in neutral_rows(rows, channel):
            orbital_energy = as_float(row["gas_neutral_" + orbital + "_eV"])
            value = as_float(row[channel + "_gas_eV"])
            if orbital_energy is None or value is None:
                continue
            xs.append(-orbital_energy)
            ys.append(value)
        panel.scatter(xs, ys, s=26, color=CHANNEL_COLOUR[channel], alpha=0.7,
                      label=CHANNEL_LABEL[channel], zorder=3)
    limits = [float(min(panel.get_xlim()[0], panel.get_ylim()[0])),
              float(max(panel.get_xlim()[1], panel.get_ylim()[1]))]
    panel.plot(limits, limits, color="#888888", linestyle="--", linewidth=1.1, label="1:1")
    panel.set_xlabel("Koopmans 近似 -eps_HOMO / -eps_LUMO (eV)", fontsize=10)
    panel.set_ylabel("dSCF IP / EA (eV)", fontsize=10)
    panel.set_title("F Koopmans 对照：dSCF 相对轨道能的偏离", fontsize=11.5)
    panel.legend(fontsize=8.2, framealpha=0.95)
    panel.grid(alpha=0.25, linewidth=0.6)

    verdicts = " / ".join("%s %s" % (key, summary["hypotheses"][key]["verdict"])
                          for key in ("H1", "H2", "H3", "H4", "H5", "H6"))
    figure.suptitle("W23-2 · GFN2-xTB dSCF 电离能/电子亲和能（246 化合物 x 12 臂 = %d 次）\n%s    字体：%s"
                    % (summary["pool"]["actual_runs"], verdicts, font_name), fontsize=12.8)
    figure.tight_layout(rect=(0, 0, 1, 0.955))
    return figure


def main() -> int:
    font_name = configure_fonts()
    figure = build_figure(font_name)
    figure.savefig(OUTPUT, bbox_inches="tight", dpi=150)
    print(json.dumps({"figure": str(OUTPUT), "font": font_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
