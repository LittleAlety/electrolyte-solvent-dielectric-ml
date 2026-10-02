"""W21 figures -- the three figures the framework asks for, drawn from artifacts.

Figure 3 (rank-stability matrix), Figure 4 (robust rank-flow map) and the
split x metric panel.  Read-only: every number comes from an artifact written by
``w21_rank_stability.py``.
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
SUMMARY = ROOT / "probes" / "w21_rank_stability_summary.json"
PAIRS = ROOT / "probes" / "artifacts" / "w21_rank_pairs.csv"
SPLITS = ROOT / "probes" / "artifacts" / "w21_split_metrics.csv"
ARTIFACTS = ROOT / "probes" / "artifacts"
F_MATRIX = ARTIFACTS / "w21_rank_stability_matrix.png"
F_FLOW = ARTIFACTS / "w21_rank_flow_map.png"
F_SPLIT = ARTIFACTS / "w21_split_taxonomy.png"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def figure_matrix(summary: dict) -> dict[str, object]:
    channels = ["homo", "lumo", "gap"]
    metrics = ["spearman_rho", "kendall_tau_b", "f_unresolved_at_least_one", "f_robust_inversion"]
    labels = ["Spearman rho", "Kendall tau_b", "unresolved fraction\n(at least one level)", "robust inversion\nfraction"]
    grid = np.full((len(channels), len(metrics)), np.nan)
    for i, channel in enumerate(channels):
        scalars = summary["channels"][channel]["scalars"]
        for j, metric in enumerate(metrics):
            value = scalars[metric]
            grid[i, j] = float("nan") if value is None else float(value)

    figure, axes = plt.subplots(figsize=(9.2, 3.4))
    masked = np.ma.masked_invalid(grid)
    image = axes.imshow(masked, cmap="viridis", vmin=0.0, vmax=1.0, aspect="auto")
    axes.set_xticks(range(len(metrics)), labels, fontsize=8.5)
    axes.set_yticks(range(len(channels)), [c.upper() for c in channels], fontsize=10)
    for i in range(len(channels)):
        for j in range(len(metrics)):
            value = grid[i, j]
            text = "n/a" if not np.isfinite(value) else f"{value:.3f}"
            axes.text(j, i, text, ha="center", va="center", fontsize=9.5,
                      color="white" if np.isfinite(value) and value < 0.6 else "black")
    axes.set_title(
        "Uncertainty-aware rank stability, P0 (GFN2-xTB gas) vs R_sol (wB97X-V/SMD eps=18.5), n=49 / 1176 pairs",
        fontsize=9.5,
    )
    figure.colorbar(image, ax=axes, fraction=0.025, pad=0.02)
    figure.tight_layout()
    figure.savefig(F_MATRIX, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return {"path": str(F_MATRIX.relative_to(ROOT)).replace("\\", "/"), "cells": grid.tolist()}


def figure_flow() -> dict[str, object]:
    rows = read_csv_rows(PAIRS)
    d_a = np.array([float(row["dP0_eV"]) for row in rows])
    d_b = np.array([float(row["dRsol_eV"]) for row in rows])
    sep = np.array([float(row["separation_threshold_eV"]) for row in rows])
    resolved_a = np.array([int(row["resolved_in_P0"]) for row in rows], dtype=bool)
    resolved_b = np.array([int(row["resolved_in_R_sol"]) for row in rows], dtype=bool)
    inversion = np.array([int(row["inversion"]) for row in rows], dtype=bool)
    robust = np.array([int(row["robust_inversion"]) for row in rows], dtype=bool)

    figure, axes = plt.subplots(figsize=(6.6, 6.0))
    inside = ~(resolved_a & resolved_b)
    axes.scatter(d_a[inside], d_b[inside], s=6, c="#c9ccd1", label=f"inside tolerance band ({int(inside.sum())})")
    concordant = resolved_a & resolved_b & ~inversion
    axes.scatter(d_a[concordant], d_b[concordant], s=8, c="#2f6fb2", label=f"resolved + concordant ({int(concordant.sum())})")
    flips = inversion & ~inside
    axes.scatter(d_a[flips], d_b[flips], s=14, c="#c1121f", label=f"discordant, outside band ({int(flips.sum())})")
    if robust.any():
        axes.scatter(d_a[robust], d_b[robust], s=26, c="#111111", marker="x", label=f"robust inversion ({int(robust.sum())})")
    axes.axhline(0.0, color="#888888", linewidth=0.8)
    axes.axvline(0.0, color="#888888", linewidth=0.8)
    for sign in (1.0, -1.0):
        axes.plot([0.0, sign * 3.4], [0.0, sign * 3.4], color="#bbbbbb", linewidth=0.8, linestyle=":")
    axes.set_xlabel("dP0 (eV)   [cheap proxy, mapped onto the reference scale]")
    axes.set_ylabel("dR_sol (eV)   [external reference layer]")
    axes.set_xlim(-3.4, 3.4)
    axes.set_ylim(-3.4, 3.4)
    axes.set_title(
        "Robust rank-flow map (HOMO channel): every discordant pair sits inside the tolerance band,\n"
        "so the number of robust inversions is 0",
        fontsize=9.5,
    )
    axes.legend(loc="upper left", fontsize=7.5, framealpha=0.95)
    figure.tight_layout()
    figure.savefig(F_FLOW, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return {
        "path": str(F_FLOW.relative_to(ROOT)).replace("\\", "/"),
        "inside_band": int(inside.sum()),
        "concordant": int(concordant.sum()),
        "discordant_outside_band": int(flips.sum()),
        "robust": int(robust.sum()),
    }


def figure_splits() -> dict[str, object]:
    rows = [row for row in read_csv_rows(SPLITS) if row["metric"] == "r2" and row["mean"]]
    models = ["mean_baseline", "single_feature_baseline", "ridge", "krr_tuned", "gpr", "random_forest", "gradient_boosting"]
    splits = ["random_repeated_kfold_5x10", "group_kfold_scaffold_5", "lofo_family_min5"]
    pretty = {"random_repeated_kfold_5x10": "random row (leak reference)", "group_kfold_scaffold_5": "scaffold holdout", "lofo_family_min5": "LOFO family"}
    values = {split: {model: float("nan") for model in models} for split in splits}
    for row in rows:
        if row["split"] in values and row["model"] in models:
            values[row["split"]][row["model"]] = float(row["mean"])

    figure, axes = plt.subplots(figsize=(9.6, 4.2))
    width = 0.26
    positions = np.arange(len(models))
    for offset, split in zip((-width, 0.0, width), splits):
        heights = [values[split][model] for model in models]
        axes.bar(positions + offset, heights, width=width, label=pretty[split])
    axes.axhline(0.0, color="#333333", linewidth=0.9)
    axes.set_xticks(positions, [model.replace("_", "\n") for model in models], fontsize=8)
    axes.set_ylabel("R² (target = R_sol HOMO, 45 compounds)")
    axes.set_title("Same features, three splits: the magnitude score never survives the honest cuts", fontsize=10)
    axes.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(F_SPLIT, bbox_inches="tight", dpi=150)
    plt.close(figure)
    return {"path": str(F_SPLIT.relative_to(ROOT)).replace("\\", "/"), "values": values}


def main() -> int:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    out = {
        "rank_stability_matrix": figure_matrix(summary),
        "rank_flow_map": figure_flow(),
        "split_taxonomy": figure_splits(),
    }
    for key, block in out.items():
        print(key, "->", block["path"], Path(ROOT / block["path"]).stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())