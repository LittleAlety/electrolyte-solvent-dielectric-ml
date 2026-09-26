"""Figures for the W17-14 THEMol / GFN2-xTB orbital layer.

Reads only committed artifacts (the layer CSV, the summary JSON, the four-core
registry and the W17-12 layer) and writes two PNGs into probes/artifacts/:

* themol_orbital_layer_calibration.png - the three parity plots (HOMO, LUMO,
  gap) against Batt-P30K with the 45-degree line, the fitted 2-fold map, the
  gate, and the distribution of the raw level offset
* themol_orbital_layer_coverage.png    - what THEMol actually covers, next to
  the two sources already in the repository, plus the HOMO/LUMO level offsets
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data/processed/themol_orbital_layer.csv"
SUMMARY = ROOT / "probes/themol_orbital_layer_summary.json"
SECOND_SOURCE_LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
ARTIFACTS = ROOT / "probes/artifacts"

THEMOL_POOL = 2695304
REGISTRY_KEYS = 31949
REGISTRY_HITS = 5117
IMOLS_EPSILON_HITS = 103

GFN2_COLOUR = "#2f6f4e"
BATT_COLOUR = "#a3320b"
PUBQC_COLOUR = "#1f4e79"
ACCENT = "#c8a45c"
GRID = "#d8d8d8"


def num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load():
    with open(LAYER, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    return rows, summary


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


def parity_panel(axes, pairs, channel, title, unit_note):
    xs = [point[0] for point in pairs]
    ys = [point[1] for point in pairs]
    low = min(min(xs), min(ys)) - 1.0
    high = max(max(xs), max(ys)) + 1.0
    axes.plot([low, high], [low, high], color=BATT_COLOUR, linewidth=1.1, linestyle="--",
              label="y = x (perfect transfer)")
    slope = channel["slope"]
    intercept = channel["intercept"]
    axes.plot([low, high], [slope * low + intercept, slope * high + intercept],
              color=GFN2_COLOUR, linewidth=1.6,
              label=f"map  y = {slope:.4f} x + {intercept:.4f}")
    axes.scatter(xs, ys, s=16, color=GFN2_COLOUR, alpha=0.65, edgecolor="white", linewidth=0.4)
    axes.set_xlabel(f"GFN2-xTB {title} on THEMol geometry (eV)")
    axes.set_ylabel(f"Batt-P30K {title} (eV)")
    status = channel["status"]
    verdict = "gate PASSED" if status == "usable_with_flag" else "gate MISSED"
    axes.set_title(
        f"{title}: n={channel['n']}   r={channel['pearson_r_in_sample']:.3f}"
        f"   MAE={channel['mae_out_of_sample_eV']:.4f} eV\n"
        f"{unit_note} -> {verdict} ({status})",
        fontsize=10,
    )
    axes.legend(loc="upper left", fontsize=8, frameon=False)
    style(axes)


def figure_calibration(rows, summary):
    figure, axes_grid = plt.subplots(2, 2, figsize=(12.5, 10.5))
    channels = (
        ("homo", "homo_gfn2_eV", "batt_homo_eV", "HOMO", "r >= 0.80 and MAE <= 0.35 eV"),
        ("lumo", "lumo_gfn2_eV", "batt_lumo_eV", "LUMO", "r >= 0.80 and MAE <= 0.35 eV"),
        ("gap", "gap_gfn2_eV", "batt_gap_eV", "gap", "r >= 0.80 and MAE <= 0.35 eV"),
    )
    for index, (name, x_key, y_key, title, note) in enumerate(channels):
        axes = axes_grid[index // 2][index % 2]
        parity_panel(axes, paired(rows, x_key, y_key), summary["calibration"][name], title, note)

    axes = axes_grid[1][1]
    homo_offsets = [num(row["gfn2_minus_batt_homo_eV"]) for row in rows]
    homo_offsets = [value for value in homo_offsets if value is not None]
    lumo_offsets = [num(row["gfn2_minus_batt_lumo_eV"]) for row in rows]
    lumo_offsets = [value for value in lumo_offsets if value is not None]
    bins = 24
    axes.hist(homo_offsets, bins=bins, color=GFN2_COLOUR, alpha=0.75, label="HOMO offset")
    axes.hist(lumo_offsets, bins=bins, color=BATT_COLOUR, alpha=0.55, label="LUMO offset")
    axes.axvline(0.0, color="#333333", linewidth=1.0, linestyle="--")
    axes.set_xlabel("GFN2-xTB minus Batt-P30K (eV)")
    axes.set_ylabel("molecules")
    axes.set_title(
        "Raw level offsets (n=74 paired anchors)\n"
        f"HOMO mean {summary['level_offsets_gfn2_minus_batt']['homo']['mean_eV']:.3f} eV, "
        f"LUMO mean {summary['level_offsets_gfn2_minus_batt']['lumo']['mean_eV']:.3f} eV",
        fontsize=10,
    )
    axes.legend(fontsize=8, frameon=False)
    style(axes)

    figure.suptitle(
        "W17-14  GFN2-xTB single points on THEMol geometries vs the authoritative wB97X-V level",
        fontsize=12,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS / "themol_orbital_layer_calibration.png"
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return target


def figure_coverage(rows, summary):
    figure, axes_grid = plt.subplots(1, 2, figsize=(13.0, 5.4))

    axes = axes_grid[0]
    labels = ["registry keys\n(themol pool limit)", "epsilon roster", "viscosity roster"]
    themol = [REGISTRY_HITS / REGISTRY_KEYS, summary["coverage"]["epsilon_roster_in_layer"] / 247, 242 / 1228]
    pubchemqc = [None, 210 / 247, 240 / 1228]
    positions = range(len(labels))
    width = 0.36
    axes.bar([p - width / 2 for p in positions], themol, width, color=GFN2_COLOUR,
             label="THEMol (geometry available, 5,117 molecules)")
    axes.bar([p + width / 2 for p in positions], [value or 0.0 for value in pubchemqc], width,
             color=PUBQC_COLOUR, label="W17-12 PubChemQC layer (value available)")
    for position, value, other in zip(positions, themol, pubchemqc):
        axes.text(position - width / 2, value + 0.02, f"{value * 100:.1f}%", ha="center", fontsize=8)
        if other is not None:
            axes.text(position + width / 2, other + 0.02, f"{other * 100:.1f}%", ha="center", fontsize=8)
    axes.axhline(IMOLS_EPSILON_HITS / 247, color=ACCENT, linestyle=":", linewidth=1.4,
                 label="iMolS on the epsilon roster (rejected source)")
    axes.set_xticks(list(positions))
    axes.set_xticklabels(labels, fontsize=9)
    axes.set_ylabel("fraction covered")
    axes.set_ylim(0, 1.0)
    axes.set_title(
        f"THEMol holds {THEMOL_POOL:,} Hessian geometries.\n"
        f"Only {REGISTRY_HITS:,} of this repository's {REGISTRY_KEYS:,} registry keys are among them.",
        fontsize=10,
    )
    axes.legend(fontsize=7.5, frameon=False, loc="upper right")
    style(axes)

    axes = axes_grid[1]
    axes.scatter(
        [num(row["homo_gfn2_eV"]) for row in rows],
        [num(row["lumo_gfn2_eV"]) for row in rows],
        s=18, color=GFN2_COLOUR, alpha=0.7, edgecolor="white", linewidth=0.4,
        label="THEMol + GFN2-xTB (this arm)",
    )
    axes.scatter(
        [num(row["batt_homo_eV"]) for row in rows if num(row["batt_homo_eV"]) is not None],
        [num(row["batt_lumo_eV"]) for row in rows if num(row["batt_lumo_eV"]) is not None],
        s=18, color=BATT_COLOUR, alpha=0.7, edgecolor="white", linewidth=0.4,
        label="Batt-P30K (wB97X-V, anchor set)",
    )
    axes.set_xlabel("HOMO (eV)")
    axes.set_ylabel("LUMO (eV)")
    axes.set_title(
        "GFN2-xTB virtual orbitals sit far below the DFT LUMO manifold.\n"
        "The gap is compressed from a mean 11.38 eV to 5.43 eV.",
        fontsize=10,
    )
    axes.legend(fontsize=8, frameon=False, loc="lower right")
    style(axes)

    figure.tight_layout()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS / "themol_orbital_layer_coverage.png"
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return target


def main():
    rows, summary = load()
    first = figure_calibration(rows, summary)
    second = figure_coverage(rows, summary)
    print(f"wrote {first}")
    print(f"wrote {second}")


if __name__ == "__main__":
    main()