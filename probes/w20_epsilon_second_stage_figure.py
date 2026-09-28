"""W20-4 cross-seed figure: the bounded epsilon 0.60 gun against its gate (section 28.60).

Reads the locked probes/w20_epsilon_second_stage_summary.json and draws every arm's
cross-seed mean R2, with the pre-registered arm separated from the side arms, against the
0.60 pass line, the 0.55 five-seed lower-bound line and three frozen caliber reference lines
(0.5861142332208197 / 0.5998203128630835 / 0.6080587938801277).  The figure measures nothing
of its own and never decides the verdict; it only re-draws a reading that was already locked.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_epsilon_second_stage_summary.json"
FIGURE_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "w20_epsilon_second_stage_cross_seed.png"
)
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w20_epsilon_second_stage.md"

REGISTERED_ARM = "hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128"
REFERENCE_ARM = "xgb_reference"
INNER_ARM = "hp2_inner_cv"

PASS_LINE = 0.60
LOWER_BOUND_LINE = 0.55
FROZEN_CROSS_SEED = 0.5861142332208197
W18_BEST = 0.5998203128630835
FROZEN_ANCHOR = 0.6080587938801277

COLOR_REGISTERED = "#b22222"
COLOR_SIDE = "#1f4e79"
COLOR_ANCHOR = "#555555"
COLOR_INNER = "#e08a1e"

REPORT_HEADING = "## \u516b\u3001\u56fe\u4e0e\u5224\u636e\u7ebf"
REPORT_LINES = (
    (
        "- \u8de8\u79cd\u5b50\u5747\u503c\u56fe\uff1a`probes/artifacts/w20_epsilon_s"
        "econd_stage_cross_seed.png`"
    ),
    (
        "- \u56fe\u4e2d\u7ed9\u51fa\u5168\u90e8 9 \u81c2\u7684\u8de8"
        "\u79cd\u5b50\u5747\u503c R2\uff0c\u5e76\u6807\u51fa 0."
        "60 \u8fc7\u7ebf\u30010.55 \u4e0b\u754c\u7ebf"
        "\u4e0e\u4e09\u6761\u51bb\u7ed3\u53e3\u5f84\u53c2\u8003\u7ebf\uff080.5"
        "86114233220819"
        "7 / 0.59982031"
        "28630835 / 0.6"
        "08058793880127"
        "7\uff09\uff1b\u9884\u6ce8\u518c\u81c2\u5355\u72ec\u7740\u8272\uff0c\u4fa7\u81c2"
        "\u53ea\u4f5c\u9644\u5e26\u4fe1\u606f\u3001\u4e0d\u53c2\u4e0e\u5224\u8bcd\u3002"
    ),
    (
        "- \u5224\u636e\u7ebf\u53d6\u503c\u6309\u9884\u6ce8\u518c\u5199\u6b7b\uff1a\u8fc7\u7ebf"
        " = **0.600000**\u3001"
        "\u4e94\u79cd\u5b50\u4e0b\u754c = **0.5500"
        "00**\u3002"
    ),
)


def load_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _bar_color(arm: str) -> str:
    if arm == REGISTERED_ARM:
        return COLOR_REGISTERED
    if arm == REFERENCE_ARM:
        return COLOR_ANCHOR
    if arm == INNER_ARM:
        return COLOR_INNER
    return COLOR_SIDE


def write_figure(path: Path = FIGURE_PATH) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = load_summary()
    rows = list(summary["cross_seed"])
    arms = [str(row["arm"]) for row in rows]
    means = [float(row["r2_seed_mean"]) for row in rows]
    seed_min = [float(row["r2_seed_min"]) for row in rows]
    positions = list(range(len(arms)))

    figure, axes = plt.subplots(figsize=(11.5, 5.8))
    bars = axes.barh(
        positions, means,
        color=[_bar_color(arm) for arm in arms], alpha=0.9, height=0.66,
    )
    for index, arm in enumerate(arms):
        if arm == REGISTERED_ARM:
            bars[index].set_hatch("//")
            bars[index].set_edgecolor("#000000")
            bars[index].set_linewidth(1.2)
        axes.annotate(
            format(means[index], ".6f"), (means[index], index),
            textcoords="offset points", xytext=(5, 0), va="center", fontsize=8.5,
        )
    registered_index = arms.index(REGISTERED_ARM)
    axes.plot(
        [seed_min[registered_index]], [registered_index],
        marker="D", color="#000000", ms=6, zorder=5,
        label="registered arm five-seed lower bound = "
        + format(seed_min[registered_index], ".6f"),
    )

    axes.axvline(
        PASS_LINE, color="#b22222", linestyle="--", linewidth=1.7,
        label="0.60 pass line",
    )
    axes.axvline(
        LOWER_BOUND_LINE, color="#2e7d32", linestyle=":", linewidth=1.7,
        label="0.55 five-seed lower-bound line",
    )
    axes.axvline(
        FROZEN_CROSS_SEED, color="#4a6fa5", linestyle="-.", linewidth=1.1,
        label="frozen cross-seed " + format(FROZEN_CROSS_SEED, ".16f"),
    )
    axes.axvline(
        W18_BEST, color="#6a1b9a", linestyle="-.", linewidth=1.1,
        label="W18 best arm " + format(W18_BEST, ".16f"),
    )
    axes.axvline(
        FROZEN_ANCHOR, color="#8d6e63", linestyle="-.", linewidth=1.1,
        label="seed-42 anchor single draw " + format(FROZEN_ANCHOR, ".16f"),
    )

    span_low = min([LOWER_BOUND_LINE - 0.006, min(means) - 0.004])
    span_high = max([FROZEN_ANCHOR + 0.006, max(means) + 0.006])
    axes.set_xlim(span_low, span_high)
    axes.set_yticks(positions)
    axes.set_yticklabels(arms, fontsize=8)
    axes.invert_yaxis()
    axes.set_xlabel("cross-seed mean R2 (5 locked seeds, 5 folds x 10 repeats)")
    axes.set_title(
        "W20-4 cross-seed mean R2 vs the 0.60 gate "
        "(registered arm highlighted; side arms are side information only)",
        fontsize=11,
    )
    axes.grid(alpha=0.25, axis="x")
    axes.legend(loc="lower left", fontsize=8, framealpha=0.95)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return path


def append_report_note() -> bool:
    text = REPORT_PATH.read_text(encoding="utf-8")
    if FIGURE_PATH.name in text:
        return False
    note = chr(10).join([REPORT_HEADING, ""] + list(REPORT_LINES) + [""])
    REPORT_PATH.write_text(
        text.rstrip(chr(10)) + chr(10) + chr(10) + note,
        encoding="utf-8",
        newline=chr(10),
    )
    return True


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-report-note", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    path = write_figure()
    print("wrote " + str(path))
    if not bool(args.no_report_note):
        print("report note " + ("appended" if append_report_note() else "already present"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

