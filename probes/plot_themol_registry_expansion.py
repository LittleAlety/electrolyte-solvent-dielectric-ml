"""Figures for the W17-17 THEMol / GFN2-xTB registry-wide orbital expansion.

Reads only committed artifacts (the expanded layer, its summary and the frozen
roster summary) and writes two PNGs into probes/artifacts/:

* themol_expansion_coverage.png    - the frozen 5,117-key roster by tier next
  to what the run actually delivered, plus the calibration pair count that
  W17-14 had to work with (74) for scale
* themol_expansion_calibration.png - the HOMO / LUMO / gap parity against
  Batt-P30K with the fitted 2-fold map, the gate, and the raw offset spread
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data/processed/themol_orbital_layer_expanded.csv"
SUMMARY = ROOT / "probes/themol_orbital_layer_expanded_summary.json"
ROSTER_SUMMARY = ROOT / "probes/themol_registry_expansion_roster_summary.json"
ARTIFACTS = ROOT / "probes/artifacts"

W17_14_PAIRS = 74

GFN2_COLOUR = "#2f6f4e"
BATT_COLOUR = "#a3320b"
ACCENT = "#c8a45c"
GRID = "#d8d8d8"
PLANNED = "#b9c4cc"

TIER_LABELS = {
    "no_reference_orbital": "no reference orbital\n(new numbers)",
    "flagship_dielectric": "flagship eps roster",
    "named_core_channel": "viscosity / redox /\nliquid window",
    "calibration_bulk": "Batt-labelled\n(calibration pairs)",
}


def num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load():
    with LAYER.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    roster = json.loads(ROSTER_SUMMARY.read_text(encoding="utf-8"))
    return rows, summary, roster


def paired(rows, x_key, y_key):
    pairs = []
    for row in rows:
        x = num(row[x_key])
        y = num(row[y_key])
        if x is not None and y is not None:
            pairs.append((x, y))
    return pairs


def style(axes):
    axes.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)


def coverage_figure(rows, summary, roster, path):
    fig, (left, right) = plt.subplots(1, 2, figsize=(13.5, 5.6))
    tiers = [tier for tier in roster["tier_order"]]
    planned = [roster["rows_by_tier"][tier] for tier in tiers]
    delivered = [summary["rows_by_tier"].get(tier, 0) for tier in tiers]
    positions = range(len(tiers))
    left.barh([p + 0.2 for p in positions], planned, height=0.38, color=PLANNED,
              label="frozen roster")
    left.barh([p - 0.2 for p in positions], delivered, height=0.38, color=GFN2_COLOUR,
              label="delivered with a GFN2 number")
    left.set_yticks(list(positions))
    left.set_yticklabels([TIER_LABELS[tier] for tier in tiers], fontsize=9)
    left.set_xlabel("molecules")
    left.set_title(
        "W17-17 target roster vs delivered\n"
        f"({summary['delivered_rows']:,} of {summary['roster_rows']:,} keys, "
        f"run_status = {summary['run_status']})",
        fontsize=11,
    )
    left.legend(frameon=False, fontsize=9)
    style(left)

    calibration = summary["calibration"]
    channels = ["homo", "lumo", "gap"]
    pairs = [calibration[channel].get("n", 0) for channel in channels]
    right.bar([c.upper() for c in channels], pairs, color=GFN2_COLOUR, width=0.55,
              label="W17-17 pairs")
    right.axhline(W17_14_PAIRS, color=BATT_COLOUR, linestyle="--", linewidth=1.3,
                  label=f"W17-14 had {W17_14_PAIRS} anchors")
    right.set_ylabel("cross-level pairs (GFN2 vs wB97X-V)")
    right.set_title("Calibration evidence per channel", fontsize=11)
    right.legend(frameon=False, fontsize=9)
    style(right)
    fig.suptitle("THEMol registry-wide expansion: what was targeted and what landed", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def calibration_figure(rows, summary, path):
    specs = (
        ("homo", "homo_gfn2_eV", "batt_homo_eV", "HOMO"),
        ("lumo", "lumo_gfn2_eV", "batt_lumo_eV", "LUMO"),
        ("gap", "gap_gfn2_eV", "batt_gap_eV", "gap"),
    )
    fig, panels = plt.subplots(2, 3, figsize=(15.5, 9.2))
    for column, (channel, x_key, y_key, label) in enumerate(specs):
        stats = summary["calibration"][channel]
        points = paired(rows, x_key, y_key)
        top = panels[0][column]
        if points:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            top.scatter(xs, ys, s=9, alpha=0.45, color=GFN2_COLOUR, linewidths=0)
            low = min(min(xs), min(ys)) - 1.0
            high = max(max(xs), max(ys)) + 1.0
            top.plot([low, high], [low, high], color=BATT_COLOUR, linewidth=1.1,
                     linestyle="--", label="y = x")
            if stats.get("slope") is not None:
                top.plot(
                    [low, high],
                    [stats["slope"] * low + stats["intercept"],
                     stats["slope"] * high + stats["intercept"]],
                    color=ACCENT,
                    linewidth=1.6,
                    label="2-fold fit",
                )
                top.legend(frameon=False, fontsize=8)
        top.set_xlabel(f"GFN2-xTB {label} (eV)")
        top.set_ylabel(f"wB97X-V {label} (eV)")
        verdict = stats.get("status")
        mae = stats.get("mae_out_of_sample_eV")
        r = stats.get("pearson_r_in_sample")
        top.set_title(
            f"{label}: n={stats.get('n', 0)}  r={r:.3f}  MAE={mae:.3f} eV\n"
            f"gate r>=0.80 and MAE<=0.35 -> {verdict}",
            fontsize=10,
        )
        style(top)

        bottom = panels[1][column]
        deltas = [
            num(row[f"gfn2_minus_batt_{channel}_eV"])
            for row in rows
            if num(row[f"gfn2_minus_batt_{channel}_eV"]) is not None
        ]
        if deltas:
            bottom.hist(deltas, bins=40, color=GFN2_COLOUR, alpha=0.85)
            mean = summary["level_offsets_gfn2_minus_batt"][channel]["mean_eV"]
            bottom.axvline(mean, color=BATT_COLOUR, linewidth=1.4,
                           label=f"mean {mean:+.3f} eV")
            bottom.legend(frameon=False, fontsize=8)
        bottom.set_xlabel(f"GFN2 - wB97X-V {label} (eV)")
        bottom.set_ylabel("molecules")
        bottom.set_title(f"{label} level offset", fontsize=10)
        style(bottom)
    fig.suptitle(
        "W17-17 cross-level calibration on the registry-wide pair set "
        f"({summary['calibration']['homo'].get('n', 0)} pairs)",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    rows, summary, roster = load()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    coverage_figure(rows, summary, roster, ARTIFACTS / "themol_expansion_coverage.png")
    calibration_figure(rows, summary, ARTIFACTS / "themol_expansion_calibration.png")
    print(json.dumps({"rows": len(rows), "run_status": summary["run_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
