"""Week 18 picture: the ordering survives what the magnitude does not.

Two panels, redrawn from the committed splitter table only; nothing here fits a
model or opens the network.  The left panel is R2 by splitter, the right panel is
AUC>30 by splitter, on the same arms and representations.  The point of putting
them side by side is that R2 collapses when the splitter stops leaking while AUC
barely moves, which is the whole "the ranking was learned, the magnitude was
not" reading.  The literals in PINNED are what --check asserts against, never a
drawing input.

Figure (written into probes/artifacts/):
  w17_ordering_vs_magnitude.png

Labels are Chinese when a CJK font is present and English otherwise.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "probes/artifacts"
SUMMARY = ROOT / "probes/dielectric_splitters_auc_summary.json"
FIGURE = "w17_ordering_vs_magnitude.png"

PRIMARY_PROTOCOL = "grouped"
PRIMARY_REPRESENTATION = "Morgan+Physical"
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
PINNED = {
    "random_row_hybrid_r2": 0.9337,
    "grouped_hybrid_r2": 0.1602,
}
PIN_TOLERANCE = 1e-03

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
            "title": "W18：同一臂、同一表示，只换划分器 —— R² 塌了，排序没有",
            "left_title": "量级：R²（每格 = 10 个重复的均值）",
            "right_title": "排序：AUC>30（同一批预测）",
            "gate070": "0.70 目标",
            "gate060": "0.60 旧目标",
            "noskill": "0.5 无技能",
            "leak": "泄漏参考（不可引用）",
            "honest": "诚实口径",
            "hostile": "最苛刻",
            "control": "对照臂",
            "note": "行级随机划分器把同一化合物的行同时放在两侧，R² 与 AUC 都是乐观值；决不可当达标题",
            "y_r2": "R²",
            "y_auc": "AUC>30",
            "protocol": "划分器",
            "role_random_row": "泄漏参考",
            "role_grouped": "诚实口径",
            "role_scaffold": "最苛刻",
            "role_grouped_single_row": "对照臂",
        }
    return {
        "title": "W18: same arm, same representation, only the splitter changes",
        "left_title": "magnitude: R2 (each cell = mean of 10 repeats)",
        "right_title": "ordering: AUC>30 (same predictions)",
        "gate070": "0.70 target",
        "gate060": "0.60 old target",
        "noskill": "0.5 no-skill",
        "leak": "leak reference (not citable)",
        "honest": "honest number",
        "hostile": "most hostile",
        "control": "control arm",
        "note": "the row-level splitter puts rows of one compound on both sides: both R2 and AUC are optimistic",
        "y_r2": "R2",
        "y_auc": "AUC>30",
        "protocol": "splitter",
        "role_random_row": "leak ref",
        "role_grouped": "honest",
        "role_scaffold": "hostile",
        "role_grouped_single_row": "control",
    }


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def series(summary: dict, representation: str, metric: str) -> list[float]:
    by_protocol = summary["by_protocol"]
    values = []
    for protocol in summary["protocol_order"]:
        cell = by_protocol.get(str(protocol), {}).get(representation)
        values.append(float(cell[metric]) if cell else float("nan"))
    return values


def draw(summary: dict, *, cjk: bool) -> Path:
    text = labels(cjk)
    if cjk:
        plt.rcParams["font.sans-serif"] = [pick_cjk_font() or "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    protocols = [str(item) for item in summary["protocol_order"]]
    representations = [str(item) for item in summary["frozen_side"]["representations"]]
    palette = {"Morgan": FROZEN, "Physical": GREEN, "Morgan+Physical": ACCENT}
    width = 0.26
    positions = list(range(len(protocols)))
    all_values = [
        value
        for representation in representations
        for metric in ("r2", "auc_gt30")
        for value in series(summary, representation, metric)
        if math.isfinite(value)
    ]
    floor = min(-0.05, min(all_values) - 0.10)
    tick_labels = [
        protocol + chr(10) + "(" + text["role_" + protocol] + ")" for protocol in protocols
    ]

    fig, (left, right) = plt.subplots(1, 2, figsize=(14.0, 6.2))
    fig.suptitle(text["title"], fontsize=14, color=INK, y=0.975)

    for panel, metric, ylabel in (
        (left, "r2", text["y_r2"]),
        (right, "auc_gt30", text["y_auc"]),
    ):
        for index, representation in enumerate(representations):
            values = series(summary, representation, metric)
            offsets = [
                position + (index - 1) * width for position in positions
            ]
            panel.bar(
                offsets,
                values,
                width=width,
                color=palette.get(representation, BLUE),
                label=representation,
            )
            for offset, value in zip(offsets, values, strict=True):
                panel.text(
                    offset,
                    value,
                    format(value, ".3f"),
                    ha="center",
                    va="bottom",
                    fontsize=7.5,
                    color=INK,
                )
        panel.set_xticks(positions)
        panel.set_xticklabels(tick_labels, fontsize=8.5, rotation=12, ha="right", color=INK)
        panel.set_ylabel(ylabel, fontsize=10, color=INK)
        panel.set_ylim(floor, 1.08)
        panel.grid(axis="y", color=GRID, linewidth=0.7)
        panel.set_axisbelow(True)
        for side in ("top", "right"):
            panel.spines[side].set_visible(False)

    left.set_title(text["left_title"], fontsize=11, color=INK)
    left.axhline(0.0, color=INK, linewidth=1.0)
    left.axhline(0.70, color=RED, linewidth=1.2, linestyle="--")
    left.text(-0.45, 0.70, text["gate070"], color=RED, fontsize=9, ha="left", va="bottom")
    left.axhline(0.60, color=ACCENT, linewidth=1.0, linestyle="--")
    left.text(-0.45, 0.60, text["gate060"], color=ACCENT, fontsize=9, ha="left", va="bottom")
    left.axhline(FROZEN_HEADLINE, color=FROZEN, linewidth=1.0, linestyle=":")
    left.text(
        len(protocols) - 0.5,
        FROZEN_HEADLINE,
        "冻结头条 0.4766",
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="bottom",
    )

    right.set_title(text["right_title"], fontsize=11, color=INK)
    right.axhline(0.5, color=RED, linewidth=1.2, linestyle="--")
    right.text(-0.45, 0.5, text["noskill"], color=RED, fontsize=9, ha="left", va="bottom")
    right.axhline(FROZEN_BASELINE, color=FROZEN, linewidth=1.0, linestyle=":")
    right.text(
        len(protocols) - 0.5,
        FROZEN_BASELINE,
        "冻结基线 0.4091",
        color=FROZEN,
        fontsize=9,
        ha="right",
        va="top",
    )

    left.legend(
        handles=[Patch(facecolor=palette[rep], label=rep) for rep in representations],
        frameon=False,
        fontsize=9,
        loc="upper right",
    )
    left.set_ylim(floor, 1.08)
    fig.text(0.5, 0.012, text["note"], ha="center", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 0.945))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    destination = ARTIFACTS / FIGURE
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    return destination


def check(summary: dict) -> int:
    by_protocol = summary["by_protocol"]
    measured = {
        "random_row_hybrid_r2": float(by_protocol["random_row"][PRIMARY_REPRESENTATION]["r2"]),
        "grouped_hybrid_r2": float(by_protocol[PRIMARY_PROTOCOL][PRIMARY_REPRESENTATION]["r2"]),
    }
    for key, expected in PINNED.items():
        if abs(float(measured[key]) - expected) > PIN_TOLERANCE:
            print("PINNED MISMATCH " + key + ": " + repr(measured[key]) + " != " + repr(expected))
            return 1
    if bool(summary["promotion"]["promoted"]):
        print("the summary promotes a reading; refusing to draw")
        return 1
    if float(summary["promotion"]["frozen_headline"]) != FROZEN_HEADLINE:
        print("the frozen headline moved; refusing to draw")
        return 1
    if float(summary["promotion"]["frozen_baseline"]) != FROZEN_BASELINE:
        print("the frozen baseline moved; refusing to draw")
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
