"""W20 3D property-space figure: HOMO x LUMO x dipole, coloured by log10(eps).

Re-draws readings that are already locked in data/processed/four_core_key_registry.csv.
It measures nothing of its own, decides nothing, and never touches a frozen number: the
frozen headline 0.4766400383507876 and the frozen baseline 0.4091179943351143 are not read,
not compared and not restated here.  The Batt-SLM candidate table is deliberately NOT
overlaid: its HOMO/LUMO are our own model predictions, a different caliber from the
Batt-P30K DFT layer drawn here.

The 3D projection registers itself through matplotlib, so no mpl_toolkits import is needed.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from itertools import product
from pathlib import Path

import numpy as np
from matplotlib.lines import Line2D

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
FIGURE_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_property_space_3d.png"

X_COL = "HOMO_eV"
Y_COL = "LUMO_eV"
Z_COL = "dipole_D"
EPS_COL = "dielectric"
NAME_COL = "name"
ID_COL = "inchikey"

HIGH_EPS_TOP_N = 6

# Robust view windows: the raw dipole tail reaches 28.6 D and would otherwise squash the
# epsilon island into a corner.  The percentiles are taken from the unlabelled cloud and the
# labelled points are force-included, so a view window can never hide a labelled point.
VIEW_PERCENTILES = (0.5, 99.5)

# The dashed box is a DRAWN reference window, not a measured gate.  It is fixed here so a
# rerun cannot silently move the picture; change it only together with a recorded reason.
WINDOW_HOMO_EV = (-13.0, -5.0)
WINDOW_LUMO_EV = (0.0, 2.5)
WINDOW_DIPOLE_D = (1.0, 8.0)

COLOUR_BASE = "#9aa0a6"
COLOUR_EDGE = "#111111"
COLOUR_BOX = "#444444"
COLOUR_KEY = "#7f0000"


def _value(row: dict[str, str], key: str) -> float:
    raw = str(row.get(key, "")).strip()
    if not raw:
        return float("nan")
    try:
        return float(raw)
    except ValueError:
        return float("nan")


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def split_layers(
    rows: Sequence[dict[str, str]],
) -> tuple[np.ndarray, list[tuple[float, float, float, float, str]]]:
    """Split the frozen registry into the unlabelled cloud and the eps-labelled points."""

    base: list[tuple[float, float, float]] = []
    labelled: list[tuple[float, float, float, float, str]] = []
    for row in rows:
        triple = tuple(_value(row, column) for column in (X_COL, Y_COL, Z_COL))
        if any(np.isnan(value) for value in triple):
            continue
        epsilon = _value(row, EPS_COL)
        if np.isnan(epsilon):
            base.append(triple)
            continue
        label = str(row.get(NAME_COL) or "").strip() or str(row.get(ID_COL, "")).strip()
        labelled.append((triple[0], triple[1], triple[2], epsilon, label))
    return np.asarray(base, dtype=float), labelled


def view_limits(
    base: np.ndarray,
    labelled: Sequence[tuple[float, float, float, float, str]],
) -> list[tuple[float, float]]:
    """Robust per-axis windows: percentiles of the cloud, widened to hold every label."""

    limits: list[tuple[float, float]] = []
    for column in range(len((X_COL, Y_COL, Z_COL))):
        low, high = np.percentile(base[:, column], VIEW_PERCENTILES)
        values = [row[column] for row in labelled]
        if values:
            low = min(low, min(values))
            high = max(high, max(values))
        span = float(high) - float(low)
        pad = 0.06 * span if span > 0 else 1.0
        limits.append((float(low) - pad, float(high) + pad))
    return limits


def draw_reference_window(axis) -> None:
    corners = np.array(
        list(product(WINDOW_HOMO_EV, WINDOW_LUMO_EV, WINDOW_DIPOLE_D)), dtype=float
    )
    for first in range(len(corners)):
        for second in range(first + 1, len(corners)):
            delta = np.abs(corners[first] - corners[second]) > 1e-9
            if int(delta.sum()) != 1:
                continue
            axis.plot(
                (corners[first][0], corners[second][0]),
                (corners[first][1], corners[second][1]),
                (corners[first][2], corners[second][2]),
                color=COLOUR_BOX,
                linestyle="--",
                linewidth=0.7,
                alpha=0.6,
            )


def write_figure(path: Path = FIGURE_PATH) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    base, labelled = split_layers(load_registry())
    epsilons = np.asarray([row[3] for row in labelled], dtype=float)
    limits = view_limits(base, labelled)
    ranked = sorted(labelled, key=lambda item: -item[3])[:HIGH_EPS_TOP_N]

    figure = plt.figure(figsize=(13.0, 6.4))
    axis = figure.add_subplot(1, 2, 1, projection="3d")
    plane = figure.add_subplot(1, 2, 2)

    axis.scatter(
        base[:, 0], base[:, 1], base[:, 2],
        s=2, c=COLOUR_BASE, alpha=0.10, linewidths=0, rasterized=True,
    )
    cloud = axis.scatter(
        [row[0] for row in labelled],
        [row[1] for row in labelled],
        [row[2] for row in labelled],
        s=26, c=np.log10(epsilons), cmap="viridis",
        edgecolors=COLOUR_EDGE, linewidths=0.3,
    )
    colourbar = figure.colorbar(cloud, ax=axis, shrink=0.62, pad=0.11)
    colourbar.set_label("log10(epsilon)", fontsize=9)

    for index, row in enumerate(ranked, start=1):
        axis.text(
            row[0], row[1], row[2], " " + str(index),
            fontsize=8, fontweight="bold", color=COLOUR_KEY,
        )

    draw_reference_window(axis)
    axis.set_xlim(limits[0][0], limits[0][1])
    axis.set_ylim(limits[1][0], limits[1][1])
    axis.set_zlim(limits[2][0], limits[2][1])
    axis.set_xlabel("HOMO (eV)", fontsize=9)
    axis.set_ylabel("LUMO (eV)", fontsize=9)
    axis.set_zlabel("dipole (D)", fontsize=9)
    axis.set_title(
        "3D property space, Batt-P30K level\n"
        "(dashed box = drawn reference window, not a measurement)",
        fontsize=10,
    )
    axis.legend(
        loc="upper left", fontsize=7, framealpha=0.92,
        handles=[
            Line2D([], [], marker="o", linestyle="", color=COLOUR_BASE, markersize=4,
                   label="no dielectric label (n=" + str(len(base)) + ")"),
            Line2D([], [], marker="o", linestyle="", color="#440154", markersize=5,
                   label="with an epsilon observation (n=" + str(len(labelled)) + ")"),
        ],
    )

    plane.scatter(base[:, 0], base[:, 1], s=2, c=COLOUR_BASE, alpha=0.10, linewidths=0)
    plane.scatter(
        [row[0] for row in labelled], [row[1] for row in labelled],
        s=22, c=np.log10(epsilons), cmap="viridis",
        edgecolors=COLOUR_EDGE, linewidths=0.3,
    )
    plane.axvline(WINDOW_HOMO_EV[1], color=COLOUR_BOX, linestyle="--", linewidth=0.7)
    plane.axhline(WINDOW_LUMO_EV[0], color=COLOUR_BOX, linestyle="--", linewidth=0.7)
    plane.set_xlim(limits[0][0], limits[0][1])
    plane.set_ylim(limits[1][0], limits[1][1])
    plane.set_xlabel("HOMO (eV)", fontsize=9)
    plane.set_ylabel("LUMO (eV)", fontsize=9)
    plane.set_title("projection: HOMO vs LUMO (same points, same colours)", fontsize=10)
    plane.grid(alpha=0.25)

    key_rows = [
        str(index) + ". " + row[4] + " = " + format(row[3], ".2f")
        for index, row in enumerate(ranked, start=1)
    ]
    plane.text(
        0.02, 0.02,
        "highest-epsilon points in this figure:\n" + "\n".join(key_rows),
        transform=plane.transAxes, fontsize=7.5, va="bottom", ha="left",
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#999999"},
    )

    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return path


def main() -> int:
    base, labelled = split_layers(load_registry())
    limits = view_limits(base, labelled)
    print(
        "base points " + str(len(base)) + " | epsilon-labelled points " + str(len(labelled)),
        flush=True,
    )
    for name, window in zip((X_COL, Y_COL, Z_COL), limits):
        print(
            "view " + name + " = [" + format(window[0], ".3f") + ", "
            + format(window[1], ".3f") + "]",
            flush=True,
        )
    print("wrote " + str(write_figure()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())