"""Week 17 shot-16 picture: is the single-representation 0.6081 a seed-42 artifact?

One figure, redrawn from the committed summary only; nothing here fits a model or
opens the network.  The left panel is the per-seed difference on the lever4 arm
(Physical - Morgan+Physical), the right panel is the cross-seed mean R2 of every
(arm, representation) pair next to the 0.60 gate.  The literals in PINNED are what
--check asserts against, never a drawing input.

Figure (written into probes/artifacts/):
  w17_representation_seed_robustness.png

Labels are Chinese when a CJK font is present and English otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes/artifacts"
SUMMARY = ROOT / "probes/dielectric_representation_seed_robustness_summary.json"
FIGURE = "w17_representation_seed_robustness.png"

GATE = 0.60
SEED_42_PHYSICAL = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
PINNED = {
    "seed42_physical": SEED_42_PHYSICAL,
    "cross_seed_physical": 0.586114,
    "cross_seed_hybrid": 0.541625,
    "frozen_headline": FROZEN_HEADLINE,
}

GREEN = "#2f7d4f"
RED = "#a3320b"
ACCENT = "#c8a45c"
INK = "#3a3a3a"
GRID = "#d8d8d8"
FROZEN = "#9aa4ad"

CJK_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
)


def pick_cjk_font() -> str | None:
    have = {font.name for font in font_manager.fontManager.ttflist}
    for name in CJK_CANDIDATES:
        if name in have:
            return name
    return None


def labels(cjk: bool) -> dict[str, str]:
    if cjk:
        return {
            "title": "W17 第 16 枪：单表示 0.6081 的换折种子复验（5 个种子）",
            "left_title": "判据臂 full_table_lever4：逐种子差值",
            "right_title": "跨种子平均 R²（每格 = 5 个种子的均值）",
            "delta": "R²(Physical) − R²(Morgan+Physical)",
            "seed": "折种子",
            "gate": "0.60 目标",
            "headline": "冻结头条 0.4766",
            "worst": "最差种子",
            "note": "种子 42 是冻结种子，其读数在预注册前已知；本枪非盲、诊断性、不提升",
            "physical": "Physical",
            "hybrid": "Morgan+Physical",
            "morgan": "Morgan",
        }
    return {
        "title": "W17 shot 16: the single-representation 0.6081 under five fold seeds",
        "left_title": "lever4 arm: per-seed difference",
        "right_title": "cross-seed mean R2 (each cell = mean of 5 seeds)",
        "delta": "R2(Physical) - R2(Morgan+Physical)",
        "seed": "fold seed",
        "gate": "0.60 target",
        "headline": "frozen headline 0.4766",
        "worst": "worst seed",
        "note": "seed 42 is the frozen seed and was known before locking: diagnostic, non-blind, never promoted",
        "physical": "Physical",
        "hybrid": "Morgan+Physical",
        "morgan": "Morgan",
    }


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def draw(summary: dict, *, cjk: bool) -> Path:
    text = labels(cjk)
    if cjk:
        plt.rcParams["font.sans-serif"] = [pick_cjk_font() or "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    per_seed = summary["hypothesis"]["per_seed"]
    seeds = [str(row["seed"]) for row in per_seed]
    deltas = [float(row["delta"]) for row in per_seed]
    averaged = summary["seed_averaged"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(13.6, 5.8))
    fig.suptitle(text["title"], fontsize=14, color=INK, y=0.97)

    left.set_title(text["left_title"], fontsize=11, color=INK)
    colors = [GREEN if value > 0 else RED for value in deltas]
    bars = left.bar(seeds, deltas, color=colors, width=0.62)
    left.axhline(0.0, color=INK, linewidth=1.0)
    worst = min(deltas)
    left.axhline(worst, color=ACCENT, linewidth=1.0, linestyle="--")
    left.text(
        -0.45,
        worst,
        text["worst"] + " " + format(worst, "+.4f"),
        color=ACCENT,
        fontsize=9,
        va="top",
        ha="left",
    )
    for bar, value in zip(bars, deltas, strict=True):
        left.text(
            bar.get_x() + bar.get_width() / 2.0,
            value,
            " " + format(value, "+.4f"),
            ha="center",
            va="bottom" if value > 0 else "top",
            fontsize=9,
            color=INK,
        )
    left.set_ylabel(text["delta"], fontsize=10, color=INK)
    left.set_xlabel(text["seed"], fontsize=10, color=INK)
    left.grid(axis="y", color=GRID, linewidth=0.7)
    left.set_axisbelow(True)
    for side in ("top", "right"):
        left.spines[side].set_visible(False)

    right.set_title(text["right_title"], fontsize=11, color=INK)
    arms = ["baseline_hybrid", "full_table_hybrid", "full_table_lever4"]
    reps = ["Morgan", "Physical", "Morgan+Physical"]
    palette = {"Morgan": FROZEN, "Physical": GREEN, "Morgan+Physical": ACCENT}
    width = 0.26
    for index, representation in enumerate(reps):
        values = []
        for arm in arms:
            match = [
                row for row in averaged
                if row["arm"] == arm and row["representation"] == representation
            ]
            values.append(float(match[0]["r2_seed_mean"]) if match else 0.0)
        offsets = [position + (index - 1) * width for position in range(len(arms))]
        right.bar(
            offsets,
            values,
            width=width,
            color=palette[representation],
            label=representation,
        )
        for offset, value in zip(offsets, values, strict=True):
            right.text(
                offset,
                value,
                format(value, ".3f"),
                ha="center",
                va="bottom",
                fontsize=8,
                color=INK,
            )
    right.axhline(GATE, color=RED, linewidth=1.2, linestyle="--")
    right.text(
        -0.45,
        GATE,
        text["gate"],
        color=RED,
        fontsize=9,
        ha="left",
        va="bottom",
    )
    right.axhline(FROZEN_HEADLINE, color=FROZEN, linewidth=1.0, linestyle=":")
    right.text(
        len(arms) - 0.5,
        FROZEN_HEADLINE,
        text["headline"],
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="bottom",
    )
    right.set_xticks(range(len(arms)))
    right.set_xticklabels(arms, fontsize=9, color=INK)
    right.set_ylabel("R²", fontsize=10, color=INK)
    right.set_ylim(-0.05, GATE + 0.06)
    right.grid(axis="y", color=GRID, linewidth=0.7)
    right.set_axisbelow(True)
    right.legend(
        handles=[Patch(facecolor=palette[rep], label=rep) for rep in reps],
        frameon=False,
        fontsize=9,
        loc="lower right",
    )
    for side in ("top", "right"):
        right.spines[side].set_visible(False)

    fig.text(0.5, 0.015, text["note"], ha="center", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    destination = ARTIFACTS / FIGURE
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    summary = load_summary()
    for key, expected in PINNED.items():
        if key == "cross_seed_physical" or key == "cross_seed_hybrid":
            arm = "full_table_lever4"
            representation = "Physical" if key == "cross_seed_physical" else "Morgan+Physical"
            match = [
                row for row in summary["seed_averaged"]
                if row["arm"] == arm and row["representation"] == representation
            ]
            measured = float(match[0]["r2_seed_mean"])
        elif key == "seed42_physical":
            match = [
                row for row in summary["seed_rows"]
                if row["arm"] == "full_table_lever4"
                and row["representation"] == "Physical"
                and row["seed"] == 42
            ]
            measured = float(match[0]["r2_mean"])
        else:
            measured = float(summary["promotion"]["frozen_headline"])
        if abs(measured - expected) > 1e-6:
            print("PINNED MISMATCH " + key + ": " + repr(measured) + " != " + repr(expected))
            return 1
    if args.check:
        print("pins ok; no figure written")
        return 0
    destination = draw(summary, cjk=pick_cjk_font() is not None)
    print("wrote " + str(destination))
    return 0


if __name__ == "__main__":
    sys.exit(main())
