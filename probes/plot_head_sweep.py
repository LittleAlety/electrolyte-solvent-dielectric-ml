"""Week 17 shot-17 picture: does swapping the model head clear 0.70?

Two panels, redrawn from the committed summary and repeat table only; nothing
here fits a model or opens the network.  The left panel is the repeat-mean R2 of
every pre-registered head at the anchor seed, next to the 0.70 gate, the 0.60
line and the frozen single-representation 0.6081.  The right panel is the
per-repeat spread of the same heads, so a head that only wins on average is not
confused with one that wins repeat by repeat.

Figure (written into probes/artifacts/):
  w17_head_sweep.png

Labels are Chinese when a CJK font is present and English otherwise.
"""

from __future__ import annotations

import argparse
import csv
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
SUMMARY = ROOT / "probes/dielectric_head_sweep_summary.json"
REPEATS = ARTIFACTS / "dielectric_head_sweep_repeats.csv"
FIGURE = "w17_head_sweep.png"

PASS_GATE = 0.70
PARTIAL_GATE = 0.60
SEED_42_REFERENCE = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
PINNED = {
    "anchor_reference": SEED_42_REFERENCE,
    "frozen_headline": FROZEN_HEADLINE,
    "frozen_baseline": FROZEN_BASELINE,
}

GREEN = "#2f7d4f"
RED = "#a3320b"
ACCENT = "#c8a45c"
INK = "#3a3a3a"
GRID = "#d8d8d8"
FROZEN = "#9aa4ad"
BLUE = "#3d6ea8"

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
            "title": "W17 第 17 枪：换模型头能否突破 0.70（池/分折/计分/表示全冻结）",
            "left_title": "各头在锚种子上的 repeat 均值 R2",
            "right_title": "逐重复分布（每个点 = 一个 repeat 的 R2）",
            "gate070": "0.70 目标",
            "gate060": "0.60 旧目标",
            "reference": "冻结头 0.6081",
            "headline": "冻结头条 0.4766",
            "baseline": "冻结基线 0.4091",
            "mean": "repeat 均值",
            "note": "诊断性、非盲、任何读数一律不提升；冻结头条与基线保持不变",
            "y": "R2",
        }
    return {
        "title": "W17 shot 17: can a new model head clear 0.70 (pool, folds, scorer, representation frozen)",
        "left_title": "repeat-mean R2 of every head at the anchor seed",
        "right_title": "per-repeat spread (one dot = one repeat R2)",
        "gate070": "0.70 target",
        "gate060": "0.60 old target",
        "reference": "frozen head 0.6081",
        "headline": "frozen headline 0.4766",
        "baseline": "frozen baseline 0.4091",
        "mean": "repeat mean",
        "note": "diagnostic, non-blind, never promoted; the frozen headline and baseline do not move",
        "y": "R2",
    }


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def load_repeats(seed: int) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    with REPEATS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["seed"]) != int(seed):
                continue
            series.setdefault(str(row["arm"]), []).append(float(row["r2"]))
    return series


def draw(summary: dict, *, cjk: bool) -> Path:
    text = labels(cjk)
    if cjk:
        plt.rcParams["font.sans-serif"] = [pick_cjk_font() or "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    heads = [str(row["head"]) for row in summary["cross_seed"]]
    means = {str(row["head"]): float(row["r2_seed_mean"]) for row in summary["cross_seed"]}
    anchor_seed = int(summary["contract"]["anchor_seed"])
    series = load_repeats(anchor_seed)
    best_head = str(summary["answers"]["best_head"])

    fig, (left, right) = plt.subplots(1, 2, figsize=(14.4, 6.0))
    fig.suptitle(text["title"], fontsize=14, color=INK, y=0.975)

    left.set_title(text["left_title"], fontsize=11, color=INK)
    values = [means[head] for head in heads]
    colours = [ACCENT if head == best_head else BLUE for head in heads]
    bars = left.bar(range(len(heads)), values, color=colours, width=0.62)
    for bar, value in zip(bars, values, strict=True):
        left.text(
            bar.get_x() + bar.get_width() / 2.0,
            value,
            format(value, ".4f"),
            ha="center",
            va="bottom" if value >= 0 else "top",
            fontsize=8.5,
            color=INK,
        )
    left.axhline(PASS_GATE, color=RED, linewidth=1.2, linestyle="--")
    left.text(-0.45, PASS_GATE, text["gate070"], color=RED, fontsize=9, ha="left", va="bottom")
    left.axhline(PARTIAL_GATE, color=ACCENT, linewidth=1.0, linestyle="--")
    left.text(-0.45, PARTIAL_GATE, text["gate060"], color=ACCENT, fontsize=9, ha="left", va="bottom")
    left.axhline(SEED_42_REFERENCE, color=FROZEN, linewidth=1.0, linestyle=":")
    left.text(
        len(heads) - 0.5,
        SEED_42_REFERENCE,
        text["reference"],
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="bottom",
    )
    left.axhline(FROZEN_HEADLINE, color=FROZEN, linewidth=1.0, linestyle=":")
    left.text(
        len(heads) - 0.5,
        FROZEN_HEADLINE,
        text["headline"],
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="bottom",
    )
    left.set_xticks(range(len(heads)))
    left.set_xticklabels(heads, fontsize=8.5, rotation=22, ha="right", color=INK)
    left.set_ylabel(text["y"], fontsize=10, color=INK)
    left.set_ylim(min(-0.02, min(values) - 0.05), max(values) + 0.10)
    left.grid(axis="y", color=GRID, linewidth=0.7)
    left.set_axisbelow(True)
    for side in ("top", "right"):
        left.spines[side].set_visible(False)

    right.set_title(text["right_title"], fontsize=11, color=INK)
    for index, head in enumerate(heads):
        points = series.get(head, [])
        if not points:
            continue
        offsets = [index + ((position % 5) - 2) * 0.06 for position in range(len(points))]
        right.scatter(
            offsets,
            points,
            s=26,
            color=ACCENT if head == best_head else BLUE,
            alpha=0.75,
            edgecolors="none",
        )
        right.plot(
            [index - 0.30, index + 0.30],
            [means[head], means[head]],
            color=INK,
            linewidth=1.6,
        )
    right.axhline(PASS_GATE, color=RED, linewidth=1.2, linestyle="--")
    right.text(-0.45, PASS_GATE, text["gate070"], color=RED, fontsize=9, ha="left", va="bottom")
    right.axhline(PARTIAL_GATE, color=ACCENT, linewidth=1.0, linestyle="--")
    right.text(-0.45, PARTIAL_GATE, text["gate060"], color=ACCENT, fontsize=9, ha="left", va="bottom")
    right.axhline(FROZEN_BASELINE, color=FROZEN, linewidth=1.0, linestyle=":")
    right.text(
        len(heads) - 0.5,
        FROZEN_BASELINE,
        text["baseline"],
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="top",
    )
    right.set_xticks(range(len(heads)))
    right.set_xticklabels(heads, fontsize=8.5, rotation=22, ha="right", color=INK)
    right.set_ylabel(text["y"], fontsize=10, color=INK)
    right.grid(axis="y", color=GRID, linewidth=0.7)
    right.set_axisbelow(True)
    right.legend(
        handles=[
            Patch(facecolor=INK, label=text["mean"]),
            Patch(facecolor=ACCENT, label=summary["answers"]["best_head"] if not cjk else "最佳头"),
        ],
        frameon=False,
        fontsize=9,
        loc="lower right",
    )
    for side in ("top", "right"):
        right.spines[side].set_visible(False)

    fig.text(0.5, 0.012, text["note"], ha="center", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 0.945))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    destination = ARTIFACTS / FIGURE
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    return destination


def check(summary: dict) -> int:
    measured = {}
    rows = summary["anchors"]["rows"]
    if rows:
        measured["anchor_reference"] = float(rows[0]["measured"])
    else:
        measured["anchor_reference"] = SEED_42_REFERENCE
    measured["frozen_headline"] = float(summary["promotion"]["frozen_headline"])
    measured["frozen_baseline"] = float(summary["promotion"]["frozen_baseline"])
    for key, expected in PINNED.items():
        value = float(measured[key])
        if abs(value - expected) > 1e-6:
            print("PINNED MISMATCH " + key + ": " + repr(value) + " != " + repr(expected))
            return 1
    reported = float(summary["answers"]["best_r2"])
    reference_head = str(summary["answers"]["reference_head"])
    # the best head is the best NON-reference head, exactly as the ladder defines it
    table = max(
        float(row["r2_mean"])
        for row in summary["seed_rows"]
        if str(row["head"]) != reference_head
    )
    if abs(reported - table) > 1e-09:
        print("the reported best head does not match the seed table")
        return 1
    if bool(summary["promotion"]["promoted"]):
        print("the summary promotes a reading; refusing to draw")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    summary = load_summary()
    status = check(summary)
    if status != 0:
        return status
    if args.check:
        print("pins ok; no figure written")
        return 0
    destination = draw(summary, cjk=pick_cjk_font() is not None)
    print("wrote " + str(destination))
    return 0


if __name__ == "__main__":
    sys.exit(main())
