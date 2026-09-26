"""Figures for the W17-12 second-source orbital layer.

Reads only committed artifacts (the layer CSV, the summary JSON and the
four-core registry) and writes three PNGs into probes/artifacts/:

* orbital_second_source_calibration.png - paired PubChemQC vs Batt-P30K HOMO/LUMO
  with the 45-degree line, the 2-fold linear map and its out-of-sample error
* orbital_second_source_coverage.png    - roster coverage, with iMolS as the
  rejected alternative, plus the level-offset distributions
* orbital_second_source_landscape.png   - joint HOMO/LUMO landscape of the new
  layer next to the Batt-P30K distribution it is mapped onto
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
SUMMARY = ROOT / "probes/orbital_second_source_summary.json"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
ARTIFACTS = ROOT / "probes/artifacts"

IMOLS_EPSILON_HITS = 103  # measured in the iMolS reconnaissance
IMOLS_EPSILON_KEYS = 247

HOMO_COLOUR = "#1f4e79"
LUMO_COLOUR = "#a3320b"
ACCENT = "#c8a45c"


def num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load():
    with open(LAYER, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    batt = []
    with open(REGISTRY, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("has_orbitals") == "true" and row.get("HOMO_eV"):
                batt.append((num(row["HOMO_eV"]), num(row["LUMO_eV"])))
    return rows, summary, batt


def calibration_figure(rows, summary):
    pairs = [
        {
            "homo": (num(row["homo_eV"]), num(row["batt_homo_eV"])),
            "lumo": (num(row["lumo_eV"]), num(row["batt_lumo_eV"])),
        }
        for row in rows
        if row["role"] == "paired_anchor"
    ]
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 5.2))
    for axis, channel, colour in (
        (axes[0], "homo", HOMO_COLOUR),
        (axes[1], "lumo", LUMO_COLOUR),
    ):
        xs = [p[channel][0] for p in pairs if all(v is not None for v in p[channel])]
        ys = [p[channel][1] for p in pairs if all(v is not None for v in p[channel])]
        axis.scatter(xs, ys, s=26, color=colour, alpha=0.72, edgecolor="white", linewidth=0.5)
        lo = min(min(xs), min(ys)) - 1.0
        hi = max(max(xs), max(ys)) + 1.0
        axis.plot([lo, hi], [lo, hi], linestyle=":", color="#888888", linewidth=1.3,
                  label="y = x (no level offset)")
        block = summary["calibration"][channel]
        slope, intercept = block["slope"], block["intercept"]
        # A reference-only channel is drawn dashed so the figure never reads as
        # "this LUMO map is usable": the honesty boundary lives in the picture too.
        reference_only = block["status"] == "reference_only"
        map_label = "2-fold linear map (reference only)" if reference_only else "2-fold linear map"
        axis.plot([lo, hi], [slope * lo + intercept, slope * hi + intercept],
                  color=ACCENT, linewidth=2.0, linestyle=(0, (5, 3)) if reference_only else "-",
                  label=map_label)
        axis.set_xlim(lo, hi)
        axis.set_ylim(lo, hi)
        axis.set_xlabel(channel.upper() + "  PubChemQC B3LYP/6-31G//PM6  (eV)")
        axis.set_ylabel(channel.upper() + "  Batt-P30K wB97X-V/def2-TZVPPD/SMD  (eV)")
        axis.set_title(f"{channel.upper()}: n = {block['n']} paired anchors", fontsize=10)
        text = (
            f"slope = {slope:.4f}\nintercept = {intercept:+.4f} eV\n"
            f"out-of-sample MAE = {block['mae_out_of_sample_eV']:.3f} eV\n"
            f"Pearson r = {block['pearson_r_in_sample']:.3f}\nstatus: {block['status']}"
        )
        axis.text(0.04, 0.96, text, transform=axis.transAxes, va="top", ha="left",
                  fontsize=8.5, family="monospace",
                  bbox={"boxstyle": "round,pad=0.45", "facecolor": "white",
                        "edgecolor": "#bbbbbb", "alpha": 0.92})
        axis.legend(loc="lower right", fontsize=8, frameon=False)
        axis.grid(alpha=0.18)
    figure.suptitle("Cross-level calibration of the second orbital source", fontsize=12)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    path = ARTIFACTS / "orbital_second_source_calibration.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def coverage_figure(rows, summary):
    coverage = summary["coverage"]
    offsets = summary["level_offsets_batt_minus_pubchemqc"]
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 5.0))

    labels = [
        "epsilon roster\n(second source)",
        "viscosity roster sample\n(second source)",
        "epsilon roster\n(iMolS, rejected)",
    ]
    hits = [
        coverage["epsilon_roster_hits"],
        coverage["viscosity_roster_sample_hits"],
        IMOLS_EPSILON_HITS,
    ]
    totals = [
        coverage["epsilon_roster_keys"],
        coverage["viscosity_roster_sample_size"],
        IMOLS_EPSILON_KEYS,
    ]
    colours = [HOMO_COLOUR, "#2e7d5b", "#a0a0a0"]
    bars = axes[0].bar(range(len(labels)), [100.0 * h / t for h, t in zip(hits, totals)],
                       color=colours, width=0.6)
    axes[0].set_xticks(range(len(labels)))
    axes[0].set_xticklabels(labels, fontsize=8.5)
    axes[0].set_ylabel("roster keys found  (%)")
    axes[0].set_ylim(0, 100)
    for bar, hit, total in zip(bars, hits, totals):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.0,
                     f"{hit} / {total}", ha="center", fontsize=9)
    axes[0].set_title("Coverage of the electrolyte rosters", fontsize=10)
    axes[0].grid(axis="y", alpha=0.18)

    paired = [row for row in rows if row["role"] == "paired_anchor"]
    homo = [num(row["batt_minus_pubchemqc_homo_eV"]) for row in paired]
    lumo = [num(row["batt_minus_pubchemqc_lumo_eV"]) for row in paired]
    homo = [v for v in homo if v is not None]
    lumo = [v for v in lumo if v is not None]
    bins = [i * 0.25 - 4.0 for i in range(int(9.0 / 0.25) + 1)]
    axes[1].hist(homo, bins=bins, color=HOMO_COLOUR, alpha=0.72,
                 label=f"HOMO offset (mean {offsets['homo']['mean_eV']:+.2f} eV)")
    axes[1].hist(lumo, bins=bins, color=LUMO_COLOUR, alpha=0.62,
                 label=f"LUMO offset (mean {offsets['lumo']['mean_eV']:+.2f} eV)")
    axes[1].axvline(0.0, color="#444444", linestyle=":", linewidth=1.2)
    axes[1].set_xlabel("Batt-P30K minus PubChemQC  (eV)")
    axes[1].set_ylabel("paired molecules")
    axes[1].set_title("Level offset between the two sources", fontsize=10)
    axes[1].legend(fontsize=8.5, frameon=False)
    axes[1].grid(alpha=0.18)

    figure.tight_layout()
    path = ARTIFACTS / "orbital_second_source_coverage.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def landscape_figure(rows, batt):
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 5.0))

    est = [(num(r["calib_homo_eV"]), num(r["lumo_eV"])) for r in rows
           if r["role"] == "calibrated_estimate"]
    est = [(h, l) for h, l in est if h is not None and l is not None]
    anchor = [(num(r["batt_homo_eV"]), num(r["batt_lumo_eV"])) for r in rows
              if r["role"] == "paired_anchor"]
    anchor = [(h, l) for h, l in anchor if h is not None and l is not None]
    axes[0].scatter([p[0] for p in est], [p[1] for p in est], s=16, color="#2e7d5b",
                    alpha=0.55, label=f"calibrated estimate ({len(est)})")
    axes[0].scatter([p[0] for p in anchor], [p[1] for p in anchor], s=26, color=ACCENT,
                    alpha=0.9, edgecolor="white", linewidth=0.5,
                    label=f"paired anchor ({len(anchor)})")
    axes[0].set_xlabel("HOMO on the Batt level  (eV)")
    axes[0].set_ylabel("LUMO, PubChemQC  (eV)")
    axes[0].set_title("New molecules added to the orbit channel", fontsize=10)
    axes[0].legend(fontsize=8.5, frameon=False)
    axes[0].grid(alpha=0.18)

    homo_layer = sorted(v for v in (num(r["homo_eV"]) for r in rows) if v is not None)
    homo_layer = [v for v in homo_layer if -25.0 <= v <= 5.0]
    homo_batt = sorted(v for v, _ in batt if v is not None and -25.0 <= v <= 5.0)
    bins = [i * 0.4 - 22.0 for i in range(int(28.0 / 0.4) + 1)]
    axes[1].hist(homo_batt, bins=bins, density=True, color="#a0a0a0", alpha=0.65,
                 label=f"Batt-P30K ({len(homo_batt)} molecules)")
    axes[1].hist(homo_layer, bins=bins, density=True, color=HOMO_COLOUR, alpha=0.6,
                 label=f"PubChemQC layer ({len(homo_layer)} molecules)")
    axes[1].set_xlabel("HOMO  (eV)")
    axes[1].set_ylabel("density")
    axes[1].set_title("Raw level distributions differ, hence the map", fontsize=10)
    axes[1].legend(fontsize=8.5, frameon=False)
    axes[1].grid(alpha=0.18)

    figure.tight_layout()
    path = ARTIFACTS / "orbital_second_source_landscape.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rows, summary, batt = load()
    for path in (calibration_figure(rows, summary),
                 coverage_figure(rows, summary),
                 landscape_figure(rows, batt)):
        print("wrote", path.relative_to(ROOT), path.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())