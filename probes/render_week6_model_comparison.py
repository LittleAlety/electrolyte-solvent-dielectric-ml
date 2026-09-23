"""Render the Week 6 frozen-model and neural-probe comparison."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _metrics(
    summary: dict[str, object],
    key: str,
) -> dict[str, float]:
    values = summary["summary"][key]  # type: ignore[index]
    return {
        metric: float(values[metric]["mean"])  # type: ignore[index]
        for metric in ("r2", "mae", "spearman")
    }


def render(source_root: Path, destination: Path) -> None:
    xgb = json.loads(
        (
            source_root / "probes" / "dielectric_representation_ablation_summary.json"
        ).read_text(encoding="utf-8")
    )
    mlp = json.loads(
        (source_root / "probes" / "dielectric_mlp_probe_summary.json").read_text(
            encoding="utf-8"
        )
    )
    chemprop = json.loads(
        (source_root / "probes" / "dielectric_chemprop_summary.json").read_text(
            encoding="utf-8"
        )
    )
    series = (
        ("Morgan", _metrics(xgb, "Morgan")),
        ("Physical", _metrics(xgb, "Physical")),
        ("Hybrid", _metrics(xgb, "Morgan+Physical")),
        ("MLP Phys.", _metrics(mlp, "MLP_Physical")),
        ("Chemprop", _metrics(chemprop, "Chemprop_DMPNN_raw")),
    )
    labels = [name for name, _ in series]
    colors = ("#64748b", "#0f766e", "#0369a1", "#b45309", "#be123c")
    figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.5))
    for axis, metric, title in zip(
        axes,
        ("r2", "mae", "spearman"),
        ("R2", "MAE", "Spearman"),
        strict=True,
    ):
        values = [metrics[metric] for _, metrics in series]
        axis.bar(labels, values, color=colors)
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.25)
        if metric != "mae":
            axis.axhline(0.0, color="#111827", linewidth=0.7)
    figure.suptitle("Frozen benchmark and neural probes")
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "model_comparison.png",
    )
    args = parser.parse_args()
    render(REPOSITORY_ROOT, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
