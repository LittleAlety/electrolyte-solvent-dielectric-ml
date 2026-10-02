"""W21 Tier 3 figures -- what the Li+ coordination step does to the orbital layer.

Read-only: every number comes from probes/w21_li_coordination_layer.csv and
probes/w21_li_coordination_summary.json, both written by
probes/w21_li_coordination.py.  Two panels:

* left  -- the per-compound shift vector (dHOMO, dLUMO), coloured by motif class;
* right -- the C_0 -> C_1 ordering stability per channel (Spearman rho and the
  Top-k overlaps), with the section 9 Batt-subset rho drawn as a reference line.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
SUMMARY = ROOT / "probes" / "w21_li_coordination_summary.json"
OUTPUT = ROOT / "probes" / "artifacts" / "w21_li_coordination_shift.png"

MOTIF_ORDER = ("lone_pair", "anion_halide", "aromatic_pi", "alkene_pi")
MOTIF_COLOURS = {
    "lone_pair": "#1f4e79",
    "anion_halide": "#e07b39",
    "aromatic_pi": "#2e8b57",
    "alkene_pi": "#8e44ad",
}
MOTIF_LABELS = {
    "lone_pair": "lone pair (O/N/S)",
    "anion_halide": "anion halide (F)",
    "aromatic_pi": "aromatic pi",
    "alkene_pi": "alkene pi",
}


def read_rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    rows = [
        row for row in read_rows(LAYER)
        if row["motif_class"] in MOTIF_ORDER
        and row["c0_status"] == "ok"
        and row["c1_status"] == "ok"
    ]
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    figure, axes = plt.subplots(1, 2, figsize=(12.6, 5.2))

    panel = axes[0]
    for motif_class in MOTIF_ORDER:
        subset = [row for row in rows if row["motif_class"] == motif_class]
        if not subset:
            continue
        panel.scatter(
            [float(row["delta_homo_eV"]) for row in subset],
            [float(row["delta_lumo_eV"]) for row in subset],
            s=26, alpha=0.78, linewidths=0.0,
            color=MOTIF_COLOURS[motif_class],
            label="%s (n=%d)" % (MOTIF_LABELS[motif_class], len(subset)),
        )
    panel.axhline(0.0, color="#999999", linewidth=0.8)
    panel.axvline(0.0, color="#999999", linewidth=0.8)
    panel.plot([-12.0, 0.0], [-12.0, 0.0], color="#bbbbbb", linewidth=0.8, linestyle=":")
    panel.set_xlabel("dHOMO  (eV)   [C_1 - C_0]")
    panel.set_ylabel("dLUMO  (eV)   [C_1 - C_0]")
    panel.set_title(
        "The Li+ step shifts both orbitals down, but the LUMO shift is 2x larger\n"
        "and far more dispersed -- so the LUMO ordering is what breaks (n=%d)" % len(rows),
        fontsize=9.5,
    )
    panel.legend(loc="upper right", fontsize=8.0, framealpha=0.95)
    panel.grid(alpha=0.22, linewidth=0.6)

    panel = axes[1]
    channels = ["homo", "lumo", "gap"]
    rules = ["k/N=10%", "k/N=20%", "k/N=30%"]
    positions = np.arange(len(channels), dtype=float)
    width = 0.2
    series = [
        ("Spearman rho", [float(summary["channels"][c]["spearman_rho"]) for c in channels], "#1f4e79"),
        ("Top-k 10%", [float(summary["channels"][c]["topk"]["k/N=10%"]["overlap"]) for c in channels], "#5b9bd5"),
        ("Top-k 20%", [float(summary["channels"][c]["topk"]["k/N=20%"]["overlap"]) for c in channels], "#a6c8e8"),
        ("Top-k 30%", [float(summary["channels"][c]["topk"]["k/N=30%"]["overlap"]) for c in channels], "#d6e4f2"),
    ]
    for offset, (label, values, colour) in enumerate(series):
        panel.bar(positions + (offset - 1.5) * width, values, width, label=label, color=colour)
        for x, value in zip(positions + (offset - 1.5) * width, values):
            panel.text(x, value + 0.02, "%.2f" % value, ha="center", va="bottom", fontsize=7.0)
    batt_rho = float(summary["batt_step"]["C1_this_arm_li"]["spearman_rho"])
    panel.axhline(batt_rho, color="#c1121f", linewidth=1.2, linestyle="--",
                  label="section 9 Batt-subset rho, C_1 arm (%.3f)" % batt_rho)
    panel.set_xticks(positions, [c.upper() for c in channels])
    panel.set_ylim(0.0, 1.30)
    panel.set_ylabel("agreement between the C_0 and C_1 orderings")
    panel.set_title(
        "Ordering stability survives the coordination step on HOMO and collapses on LUMO\n"
        "(same 217 motif-bearing compounds, registered rule)",
        fontsize=9.5,
    )
    panel.legend(loc="upper right", fontsize=7.4, framealpha=0.95, ncol=2)
    panel.grid(axis="y", alpha=0.22, linewidth=0.6)

    figure.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, bbox_inches="tight", dpi=150)
    plt.close(figure)

    payload = {
        "path": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "n_compounds": len(rows),
        "channels": {c: {"spearman_rho": float(summary["channels"][c]["spearman_rho"]),
                         "topk": {r: float(summary["channels"][c]["topk"][r]["overlap"]) for r in rules}}
                     for c in channels},
        "batt_c1_spearman_rho": batt_rho,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
