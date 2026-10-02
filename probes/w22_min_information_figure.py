"""Figure: minimum-information budget for the ranking funnel (W22-4 / review item D6).

The figure turns the prose of section 3.10 into one decision flowchart that
answers four questions the reviewer asked the manuscript to answer in one
pane:

* which layer is computed and which layer is skipped;
* which cells must be run on both axes;
* which pairs can be declared *indistinguishable* without paying for the
  expensive layer at all;
* where the single continuum may never be dropped (review items A5/A6).

Every rule drawn here is a *policy* statement that already exists in the
manuscript or in the Week 22 review-response matrix; the script computes
nothing and fits nothing. It only renders the decision graph.

Policy sources
--------------
* ``paper/review_response_matrix.md`` 1.1 (A3, strict bound ``2 * A_axis``),
  1.2 (A5, reduction axis lives on a continuum layer), 1.3 (A6, the single
  continuum is not optional).
* ``docs/framework/ranking-electrolyte-materials-v2.md`` for the layer names
  P0 / P1 / P2 and C1.

Usage:
    python probes/w22_min_information_figure.py
    python probes/w22_min_information_figure.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUTPUT_PNG = REPOSITORY_ROOT / "probes" / "artifacts" / "w22_min_information_budget.png"

# The figure is Chinese-labelled on purpose: the manuscript body and captions
# are Chinese, so this new figure follows the caption language instead of the
# English in-figure titles that review item C8 flagged.
PREFERRED_FONTS = (
    "Microsoft YaHei",
    "SimHei",
    "Microsoft JhengHei",
    "Noto Sans CJK SC",
)

COLORS = {
    "start": "#dbeafe",
    "process": "#e6f4ea",
    "decision": "#fff3cd",
    "skip": "#fde2e2",
    "refuse": "#fde2e2",
    "axis": "#e8e2fb",
    "exit": "#e0e7ff",
    "note": "#f1f5f9",
}
EDGE = "#334155"
LABEL_BBOX = {"facecolor": "white", "edgecolor": "none", "pad": 1.5}


def configure_fonts() -> str:
    """Pick the first installed CJK font; fall back to the default family."""

    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in installed:
            plt.rcParams["font.family"] = name
            return name
    plt.rcParams["font.family"] = "sans-serif"
    return "sans-serif (CJK glyphs may be missing)"


def rounded_box(ax, x, y, w, h, text, facecolor, fontsize=10.5, bold=False, edge=EDGE):
    """Draw one rounded process box; (x, y) is the lower-left corner."""

    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            linewidth=1.2,
            edgecolor=edge,
            facecolor=facecolor,
            mutation_aspect=1.0,
        )
    )
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight="bold" if bold else "normal",
        wrap=True,
    )


def arrow(ax, start, end, color=EDGE):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=14,
            linewidth=1.3,
            color=color,
            shrinkA=1.0,
            shrinkB=1.0,
        )
    )


def build_figure(font_name: str):
    fig, ax = plt.subplots(figsize=(12.4, 14.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    left_x, left_w = 0.035, 0.50
    right_x, right_w = 0.60, 0.365
    lc = left_x + left_w / 2

    # --- main column -----------------------------------------------------
    boxes = [
        # (y_bottom, height, text, color, bold)
        (0.945, 0.048, "候选分子名册（115,756 个 SMILES）", "start", True),
        (0.878, 0.048, "结构标准化 + D1 域声明\n（只标准化，不做预筛）", "process", False),
        (0.782, 0.066, "决策 A：落在 P0 适用域内？", "decision", True),
        (0.693, 0.062, "计算 P0 单格能量 e_i 与单格效应量 A_axis\n（最省层：廉价代理）", "process", False),
        (0.597, 0.066, "决策 B：pair 间距 |d0| ≥ 2·A_axis ？", "decision", True),
        (0.505, 0.058, "氧化（OX）轴：用 P1 气相层判据", "axis", False),
        (0.408, 0.062, "决策 C：该 pair 需要还原（RED）轴？", "decision", True),
        (0.312, 0.058, "还原轴：必须带单一连续介质\n→ P2 / C1（单腿）", "axis", False),
        (0.212, 0.062, "出口物：候选 + 域声明 + 逐行溯源\n+ 通道出处 + 门槛状态", "exit", True),
    ]
    for y, h, text, key, bold in boxes:
        rounded_box(ax, left_x, y, left_w, h, text, COLORS[key], bold=bold)

    # --- branch outcomes (right column) ---------------------------------
    rounded_box(
        ax, right_x, 0.782, right_w, 0.066,
        "拒答：refused_experimental_queue\n（给低分会误读，拒答更诚实）",
        COLORS["refuse"],
    )
    rounded_box(
        ax, right_x, 0.597, right_w, 0.066,
        "直接判「不可分辨」\n→ 不升级，省下昂贵层算力",
        COLORS["skip"],
    )
    rounded_box(
        ax, right_x, 0.408, right_w, 0.062,
        "否：只用 OX 轴（P1 即可）\nRED 轴结论不得由气相层给出",
        COLORS["skip"],
    )

    # --- arrows: main column --------------------------------------------
    gaps = [
        ((lc, 0.945), (lc, 0.926)),
        ((lc, 0.878), (lc, 0.848)),
        ((lc, 0.782), (lc, 0.755)),
        ((lc, 0.693), (lc, 0.663)),
        ((lc, 0.597), (lc, 0.563)),
        ((lc, 0.505), (lc, 0.470)),
        ((lc, 0.408), (lc, 0.370)),
        ((lc, 0.312), (lc, 0.274)),
    ]
    for start, end in gaps:
        arrow(ax, start, end)

    # decision A -> refuse (否)
    arrow(ax, (left_x + left_w, 0.815), (right_x, 0.815))
    ax.text((left_x + left_w + right_x) / 2, 0.822, "否", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)
    ax.text(lc, 0.851, "是", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)

    # decision B -> indistinguishable (否)
    arrow(ax, (left_x + left_w, 0.630), (right_x, 0.630))
    ax.text((left_x + left_w + right_x) / 2, 0.637, "否", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)
    ax.text(lc, 0.666, "是", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)

    # decision C -> only OX (否)
    arrow(ax, (left_x + left_w, 0.439), (right_x, 0.439))
    ax.text((left_x + left_w + right_x) / 2, 0.446, "否", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)
    ax.text(lc, 0.473, "是", ha="center", va="bottom", fontsize=10, color=EDGE, bbox=LABEL_BBOX)

    # --- budget notes ----------------------------------------------------
    rounded_box(
        ax, left_x, 0.108, left_w + right_w - 0.01, 0.072,
        "预算口径（A6）：可省 = ε ≥ 200 的高介电细化与 ε 扫描；"
        "不可省 = 单一连续介质计算。\n"
        "还原轴只以带连续介质的层为载体（A5）：气相阴离子不束缚时的 ΔSCF「EA」是伪束缚 artifact。",
        COLORS["note"],
        fontsize=9.5,
    )
    rounded_box(
        ax, left_x, 0.028, left_w + right_w - 0.01, 0.064,
        "定理 vs 实测（A3）：严格界是 2·A_axis（三角不等式 |Δ(e_i − e_j)| ≤ |Δe_i| + |Δe_j| ≤ 2·A_axis）；\n"
        "「靶向漏 0 次翻转、τb = 1.0000」是实测经验结果，不能反过来证明定理——两句分开写。",
        COLORS["note"],
        fontsize=9.5,
    )

    ax.set_title(
        "最小信息预算决策流程图（Week 22 / D6）\n"
        "哪层算、哪层跳、哪些格子双腿、哪些 pair 直接判不可分辨",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.text(
        0.5, 0.001, f"font: {font_name}", ha="center", va="bottom", fontsize=7.5, color="#64748b"
    )
    fig.tight_layout()
    return fig


def render(path: Path) -> None:
    font_name = configure_fonts()
    fig = build_figure(font_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-render into a temp file and byte-compare with the committed PNG",
    )
    args = parser.parse_args(argv)

    if not args.check:
        render(OUTPUT_PNG)
        print(f"wrote {OUTPUT_PNG.relative_to(REPOSITORY_ROOT)}")
        return 0

    committed = OUTPUT_PNG.read_bytes()
    tmp = OUTPUT_PNG.with_suffix(".tmp.png")
    render(tmp)
    fresh = tmp.read_bytes()
    tmp.unlink()
    if fresh != committed:
        print(f"FAIL: {OUTPUT_PNG.name} is not reproducible from this script", file=sys.stderr)
        return 1
    print(f"PASS: {OUTPUT_PNG.name} renders deterministically ({len(committed)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())