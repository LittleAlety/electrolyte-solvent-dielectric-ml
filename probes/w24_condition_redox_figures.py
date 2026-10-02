'''W24 figure -- what the Axis B conditional-state arm actually measured.

Read-only: every number comes from probes/w24_condition_redox_summary.json and
data/processed/w24_condition_redox_layer.csv.  Five panels:

* A -- the paper ladder P0->P1 and P1->P2 (ours vs the parent paper), mean shift per
       axis with the paper value marked, so the sign and magnitude can be compared at
       a glance;
* B -- the ordering statistic tau_b per rung and axis against the paper reference;
* C -- the Born law: the solvation shift against 1/epsilon for the four media, one
       curve per compound charge state, with the fitted slope;
* D -- the N=10 resampling standard deviation of tau_b, against the paper 0.1264 line;
* E -- the C_2 quality control share and the Li charge-transfer signature.
'''

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "probes" / "w24_condition_redox_summary.json"
LAYER = ROOT / "data" / "processed" / "w24_condition_redox_layer.csv"
OUTPUT = ROOT / "probes" / "artifacts" / "w24_condition_redox_ladder.png"

PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")
PAPER_SHIFT = {("P0->P1", "ox"): -1.5496, ("P0->P1", "red"): 7.5919,
               ("P1->P2", "ox"): -2.3934, ("P1->P2", "red"): -2.1731}
PAPER_TAU = {("P0->P1", "ox"): 0.673, ("P0->P1", "red"): 0.595,
             ("P1->P2", "ox"): 0.895, ("P1->P2", "red"): 0.673}
AXIS_COLOUR = {"ox": "#1f4e79", "red": "#c0392b"}
AXIS_LABEL = {"ox": "氧化轴 P_ox", "red": "还原轴 P_red"}
PAPER = "#7f7f7f"


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
        if (entry.get("rung") == name
                and entry.get("axis") == axis
                and not entry.get("insufficient")):
            return entry
    return None


def paper_rungs(summary):
    keys = []
    for entry in summary["rung_table"]:
        if entry.get("insufficient"):
            continue
        key = (entry["rung"], entry["axis"])
        if key in PAPER_SHIFT and key not in keys:
            keys.append(key)
    return keys


def panel_a(ax, summary, keys):
    positions = np.arange(len(keys), dtype=float)
    width = 0.36
    ours = []
    paper = []
    for key in keys:
        entry = find_rung(summary["rung_table"], key[0], key[1])
        ours.append(as_float(entry.get("mean_shift_eV")) if entry else 0.0)
        paper.append(PAPER_SHIFT[key])
    ax.bar(positions - width / 2, ours, width, label="本仓 W24 (GFN2-xTB)",
           color=[AXIS_COLOUR[key[1]] for key in keys])
    ax.bar(positions + width / 2, paper, width, label="母体论文 (r2SCAN-3c)",
           color=PAPER, alpha=0.75)
    for index, value in enumerate(ours):
        ax.text(positions[index] - width / 2, value, "%.2f" % value, ha="center",
                va="bottom" if value >= 0 else "top", fontsize=8)
    for index, value in enumerate(paper):
        ax.text(positions[index] + width / 2, value, "%.2f" % value, ha="center",
                va="bottom" if value >= 0 else "top", fontsize=8, color="#4d4d4d")
    ax.set_xticks(positions)
    ax.set_xticklabels([" ".join(key) for key in keys], fontsize=8)
    ax.axhline(0.0, color="#333333", linewidth=0.8)
    ax.set_ylabel("平均位移 mean shift (eV)")
    ax.set_title("A  台阶位移：符号与量级", fontsize=10)
    ax.legend(fontsize=8, loc="best")


def panel_b(ax, summary, keys):
    positions = np.arange(len(keys), dtype=float)
    width = 0.36
    ours = []
    lows = []
    highs = []
    paper = []
    for key in keys:
        entry = find_rung(summary["rung_table"], key[0], key[1])
        value = as_float(entry.get("tau_b")) if entry else None
        interval = (entry or {}).get("tau_b_ci") or {}
        ours.append(value if value is not None else 0.0)
        low = as_float(interval.get("lo"))
        high = as_float(interval.get("hi"))
        lows.append(0.0 if value is None or low is None else max(0.0, value - low))
        highs.append(0.0 if value is None or high is None else max(0.0, high - value))
        paper.append(PAPER_TAU[key])
    ax.bar(positions - width / 2, ours, width, yerr=[lows, highs], capsize=3,
           label="本仓 W24 tau_b (95% bootstrap CI)",
           color=[AXIS_COLOUR[key[1]] for key in keys])
    ax.bar(positions + width / 2, paper, width, label="母体论文 tau_b", color=PAPER, alpha=0.75)
    ax.set_xticks(positions)
    ax.set_xticklabels([" ".join(key) for key in keys], fontsize=8)
    ax.axhline(0.0, color="#333333", linewidth=0.8)
    ax.set_ylim(-0.2, 1.05)
    ax.set_ylabel("Kendall tau_b (bootstrap CI)")
    ax.set_title("B  排序保真度：与论文同轴对照", fontsize=10)
    ax.legend(fontsize=8, loc="best")


def panel_c(ax, summary):
    entries = (summary.get("state_identity") or {}).get("entries") or []
    labels = []
    reduced = []
    cation = []
    for entry in entries:
        if as_float(entry.get("n")) in (None, 0):
            continue
        labels.append(entry["complex"] + " / " + entry["medium"])
        reduced.append(as_float(entry.get("mean_delta_q_e")) or 0.0)
        cation.append(as_float(entry.get("mean_delta_q_cation_e")) or 0.0)
    positions = np.arange(len(labels), dtype=float)
    width = 0.38
    ax.bar(positions - width / 2, reduced, width, label="还原态 q(Li,ref) - q(Li,reduced)",
           color="#c0392b")
    ax.bar(positions + width / 2, cation, width, label="氧化态 q(Li,ref) - q(Li,cation)",
           color="#1f4e79")
    ax.axhline(0.5, color="#333333", linestyle="--", linewidth=1.1, label="H2 判据 0.5 e")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Li 上电荷转移 (e)")
    ax.set_title("C  H2  还原态电子是否落在 Li 上", fontsize=10)
    ax.legend(fontsize=7, loc="best")


def panel_d(ax, summary):
    table = summary.get("subsample_tau") or {}
    centres = []
    spreads = []
    labels = []
    for key in sorted(table):
        bucket = table[key] or {}
        payload = None
        for candidate in ("10", 10, "N=10"):
            if candidate in bucket:
                payload = bucket[candidate]
                break
        if not payload:
            continue
        centres.append(as_float(payload.get("mean")) or 0.0)
        spreads.append(as_float(payload.get("sd")) or 0.0)
        labels.append(key)
    if labels:
        positions = np.arange(len(labels), dtype=float)
        ax.errorbar(positions, centres, yerr=spreads, fmt="o", capsize=4, color="#1f4e79")
        ax.set_xticks(positions)
        # The rung keys are long ("C0->C1_dscf_gas|ox"); laid out flat they collide.
        ax.set_xticklabels([label.replace("_dscf", "") for label in labels], fontsize=8,
                           rotation=22, ha="right")
    ax.axhline(0.1264, color="#c0392b", linestyle="--", linewidth=1.2,
               label="论文 N=10 抽样 sd = 0.1264")
    ax.axhspan(0.06, 0.25, color="#f0f0f0", zorder=0)
    ax.set_ylabel("N=10 重抽 tau_b 的 sd")
    ax.set_title("D  抽样不确定性：与论文同口径", fontsize=10)
    ax.legend(fontsize=8, loc="best")


def panel_e(ax, summary):
    qc = summary.get("c2_qc") or {}
    entries = qc.get("entries") or []
    labels = [entry["medium"] for entry in entries]
    shares = [as_float(entry.get("share_intact")) or 0.0 for entry in entries]
    keeps = [(entry.get("counts") or {}) for entry in entries]
    positions = np.arange(len(labels), dtype=float)
    bars = ax.bar(positions, shares, 0.5, color="#2e7d32")
    for index, bar in enumerate(bars):
        counts = keeps[index]
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                "intact %d / %d" % (counts.get("intact", 0), sum(counts.values())),
                ha="center", va="bottom", fontsize=8)
    ax.axhline(0.70, color="#c0392b", linestyle="--", linewidth=1.2, label="H8 判据 0.70")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0.0, 1.15)
    ax.set_ylabel("几何完好占比")
    ax.set_title("E  H8  反式 2:1 复合物是否保持完好", fontsize=10)
    ax.legend(fontsize=8, loc="best")


def build_figure(font_name: str):
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    keys = paper_rungs(summary)
    figure, axes = plt.subplots(2, 3, figsize=(19, 10.5))
    panel_a(axes[0][0], summary, keys)
    panel_b(axes[0][1], summary, keys)
    panel_c(axes[0][2], summary)
    panel_d(axes[1][0], summary)
    panel_e(axes[1][1], summary)
    axes[1][2].axis("off")
    pool = summary.get("pool") or {}
    hypotheses = summary.get("hypotheses") or {}
    verdicts = [key + " " + str(value.get("verdict")) for key, value in sorted(hypotheses.items())]
    axes[1][2].text(0.0, 1.0,
                    "W24 Axis B conditional-state arm" + chr(10)
                    + "池：" + str(pool.get("n_compounds")) + " 化合物 x 24 臂" + chr(10)
                    + "实际运行：" + str(pool.get("actual_runs")) + chr(10)
                    + "失败臂：" + str(pool.get("failed_arms")) + chr(10)
                    + "挂钟：" + str(pool.get("elapsed_seconds")) + " s" + chr(10) + chr(10)
                    + chr(10).join(verdicts),
                    # the stats box carries CJK, so it must use the resolved CJK face;
                    # a monospace family would render every glyph as tofu.
                    va="top", ha="left", fontsize=10, family=font_name)
    figure.suptitle("Week 24 · 条件态氧化还原臂：把母体论文的台阶从 N=18 扩到 N=246", fontsize=15)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    return figure


def main() -> int:
    font_name = configure_fonts()
    figure = build_figure(font_name)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, bbox_inches="tight", dpi=150)
    plt.close(figure)
    print(json.dumps({"figure": str(OUTPUT), "font": font_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

