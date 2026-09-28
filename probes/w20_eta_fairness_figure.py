"""W20-1 eta fairness figure: the per-seed, per-repeat delta between the two arms.

Reads the locked probes/w20_eta_fairness_summary.json and the locked
probes/artifacts/w20_eta_fairness_repeats.csv, then draws the per-seed and
per-repeat delta MAE_chemprop - MAE_incumbent over the primary pool's five-fold
by five-repeat grouped grid, together with the registered -0.02 verdict band, the
|delta| <= 0.02 undetermined band and the 0.15 gate on both arms' levels.

The figure re-draws a reading that was already locked.  It measures nothing of
its own, it decides nothing, and it never touches a frozen number.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_eta_fairness_summary.json"
REPEATS_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_eta_fairness_repeats.csv"
FIGURE_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_eta_fairness_delta.png"

POOL = "row_level"
GATE = 0.15
TOLERANCE = 0.02

CHEMPROP_ARM = "chemprop_aligned"
INCUMBENT_ARM = "incumbent_aligned"

COLOR_CHEMPROP = "#1f4e79"
COLOR_INCUMBENT = "#b22222"
COLOR_MEAN = "#111111"
COLOR_BAND = "#2e7d32"
COLOR_UNDETERMINED = "#9e9e9e"


def _pooled_by_repeat_and_member() -> dict[tuple[int, str, str], float]:
    """Pool each (repeat, arm, member) over its folds, weighting by test rows."""

    with REPEATS_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    weighted: dict[tuple[int, str, str], float] = defaultdict(float)
    weights: dict[tuple[int, str, str], float] = defaultdict(float)
    for row in rows:
        if str(row["pool"]) != POOL:
            continue
        key = (int(row["repeat_seed"]), str(row["arm"]), str(row["member"]))
        weight = float(row["test_rows"])
        weighted[key] += float(row["mae_log10_cP"]) * weight
        weights[key] += weight
    return {key: weighted[key] / weights[key] for key in weighted}


def _grid() -> tuple[list[str], dict[int, dict[str, dict[str, float]]]]:
    pooled = _pooled_by_repeat_and_member()
    repeats = sorted({key[0] for key in pooled})
    members = sorted({key[2] for key in pooled})
    grid: dict[int, dict[str, dict[str, float]]] = {}
    for repeat in repeats:
        block: dict[str, dict[str, float]] = {}
        for arm in (CHEMPROP_ARM, INCUMBENT_ARM):
            block[arm] = {
                member: pooled[(repeat, arm, member)]
                for member in members
                if (repeat, arm, member) in pooled
            }
        grid[repeat] = block
    return members, grid


def write_figure(path: Path = FIGURE_PATH) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    members, grid = _grid()
    repeats = sorted(grid)

    deltas: dict[int, dict[str, float]] = {}
    for repeat in repeats:
        block = grid[repeat]
        deltas[repeat] = {
            member: block[CHEMPROP_ARM][member] - block[INCUMBENT_ARM][member]
            for member in block[CHEMPROP_ARM]
        }

    figure, axes = plt.subplots(1, 2, figsize=(13.0, 5.8))

    left = axes[0]
    left.axhspan(-TOLERANCE, TOLERANCE, color=COLOR_UNDETERMINED, alpha=0.18, zorder=0)
    left.axhspan(-0.42, -TOLERANCE, color=COLOR_BAND, alpha=0.10, zorder=0)
    left.axhline(-TOLERANCE, color=COLOR_BAND, linestyle="--", linewidth=1.7,
                 label="delta = -0.02: the eta gate-crossing band")
    left.axhline(TOLERANCE, color=COLOR_BAND, linestyle=":", linewidth=1.4,
                 label="delta = +0.02")
    left.axhline(0.0, color="#000000", linewidth=1.0, alpha=0.7,
                 label="no difference between the arms")

    positions = list(range(len(repeats)))
    offsets = [-0.22, 0.0, 0.22]
    palette = ["#1f4e79", "#e08a1e", "#6a1b9a"]
    for index, repeat in enumerate(repeats):
        for slot, member in enumerate(members):
            value = deltas[repeat][member]
            left.plot([index + offsets[slot % len(offsets)]], [value], marker="o",
                      ms=7, color=palette[slot % len(palette)], zorder=3,
                      label=member if index == 0 else None)
        mean = sum(deltas[repeat].values()) / len(deltas[repeat])
        left.plot([index], [mean], marker="D", ms=10, color=COLOR_MEAN, zorder=4,
                  label="cross-seed mean of the repeat" if index == 0 else None)
    overall = sum(
        value for block in deltas.values() for value in block.values()
    ) / sum(len(block) for block in deltas.values())
    left.axhline(overall, color=COLOR_MEAN, linestyle="-.", linewidth=1.3,
                 label="pooled delta = " + format(overall, ".6f"))

    left.set_xticks(positions)
    left.set_xticklabels([str(repeat) for repeat in repeats])
    left.set_xlabel("repeat seed (GroupKFold by InChIKey, 5 folds each)")
    left.set_ylabel("delta MAE log10(cP)   [chemprop - budget-aligned incumbent]")
    left.set_title("Per-seed, per-repeat delta on the primary pool (" + POOL + ")", fontsize=11)
    left.grid(alpha=0.25, axis="y")
    left.legend(loc="lower right", fontsize=7.5, framealpha=0.95)

    right = axes[1]
    for arm, colour, label in (
        (CHEMPROP_ARM, COLOR_CHEMPROP, "Chemprop D-MPNN ensemble"),
        (INCUMBENT_ARM, COLOR_INCUMBENT, "budget-aligned in-service arm"),
    ):
        means = []
        for repeat in repeats:
            values = list(grid[repeat][arm].values())
            means.append(sum(values) / len(values))
        right.plot(positions, means, marker="o", ms=8, color=colour, linewidth=1.9,
                   label=label + " cross-seed mean")
    right.axhline(GATE, color=COLOR_BAND, linestyle="--", linewidth=1.8,
                  label="registered gate = 0.15 log10(cP)")
    right.set_xticks(positions)
    right.set_xticklabels([str(repeat) for repeat in repeats])
    right.set_xlabel("repeat seed")
    right.set_ylabel("cross-seed mean MAE log10(cP)")
    right.set_title("Both arms against the 0.15 gate", fontsize=11)
    right.grid(alpha=0.25, axis="y")
    right.legend(loc="center right", fontsize=7.5, framealpha=0.95)

    figure.suptitle(
        "W20-1 eta fairness: delta = "
        + format(float(summary["delta_mae_log10_cP"]), ".15f")
        + " log10(cP), verdict = "
        + str(summary["verdict"]),
        fontsize=12,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return path


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=FIGURE_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print("wrote " + str(write_figure(args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
