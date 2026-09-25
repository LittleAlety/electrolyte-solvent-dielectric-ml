"""Figure: conditional coverage collapse of the split-conformal intervals.

``probes/dielectric_split_conformal.png`` shows the *marginal* coverage, which
is at the nominal level for every representation. That panel is necessary but it
is also the flattering view: the guarantee is marginal in compounds, so it says
nothing about the high-permittivity tail the benchmark exists to qualify.

This figure plots the conditional (target-stratum) coverage that the same
frozen intervals achieve inside eps < 20, 20-60 and eps > 60, for the absolute
and the 1+|prediction|-normalized residual variants, and carries the probe's own
caveat on the figure: the > 60 stratum holds five compounds, so its conditional
coverage is diagnostic only and must not be read as a guarantee.

No model is fitted and no dataset file is written; the probe re-reads
``probes/dielectric_split_conformal_summary.json``.

Usage:
    python probes/paper_figure_conformal_strata.py
    python probes/paper_figure_conformal_strata.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from electrolyte_ml.exporting import canonical_text_sha256

SUMMARY_PATH = "probes/dielectric_split_conformal_summary.json"
OUTPUT_PNG = "probes/artifacts/paper_fig4_conformal_strata.png"
OUTPUT_JSON = "probes/paper_figure_conformal_strata_summary.json"

BASELINE_ARM = "baseline_v0.3"
REPRESENTATION_ORDER = ("Morgan", "Physical", "Morgan+Physical")
REPRESENTATION_COLORS = {"Morgan": "#2563eb", "Physical": "#dc2626", "Morgan+Physical": "#059669"}
STRATA = (("lt20", "eps < 20"), ("20_60", "20 <= eps <= 60"), ("gt60", "eps > 60"))
EXPECTED_STRATA_SIZES = {"lt20": 182, "20_60": 47, "gt60": 5}


def collect() -> dict:
    path = REPOSITORY_ROOT / SUMMARY_PATH
    with path.open(encoding="utf-8") as handle:
        summary = json.load(handle)

    nominal = float(summary["design"]["nominal_coverage"])
    strata_sizes = {key: int(value) for key, value in summary["exchangeability"]["target_strata_sizes"].items()}
    for key, expected in EXPECTED_STRATA_SIZES.items():
        if strata_sizes.get(key) != expected:
            raise SystemExit(
                f"stratum {key} holds {strata_sizes.get(key)} compounds, expected {expected}"
            )

    series = summary["series"]
    payload: dict[str, dict] = {}
    for representation in REPRESENTATION_ORDER:
        key = f"{representation}|{BASELINE_ARM}"
        if key not in series:
            raise SystemExit(f"missing series {key}")
        block = series[key]
        payload[representation] = {
            "marginal": float(block["coverage"]["mean"]),
            "absolute": {name: float(block[f"coverage_{name}"]["mean"]) for name, _ in STRATA},
            "absolute_std": {name: float(block[f"coverage_{name}"]["std"]) for name, _ in STRATA},
            "normalized": {
                name: float(block[f"normalized_coverage_{name}"]["mean"]) for name, _ in STRATA
            },
            "interval_width": float(block["interval_width"]["mean"]),
        }

    # The figure is only meaningful if the marginal guarantee holds while the
    # conditional one does not; fail loudly if either half stops being true.
    for representation, block in payload.items():
        if not 0.9 <= block["marginal"] <= 0.94:
            raise SystemExit(f"{representation} marginal coverage moved off the nominal band")
        if block["absolute"]["gt60"] > 0.3:
            raise SystemExit(f"{representation} no longer shows a >60 coverage collapse")
        if block["absolute"]["lt20"] < 0.93:
            raise SystemExit(f"{representation} no longer holds up in the <20 stratum")

    return {
        "nominal": nominal,
        "strata_sizes": strata_sizes,
        "representations": payload,
        "caveats": list(summary["honest_boundary"]),
        "summary_sha256": canonical_text_sha256(path),
    }


def render(payload: dict, output_png: Path) -> None:
    strata_keys = [key for key, _ in STRATA]
    strata_labels = [
        f"{label}\n(n={payload['strata_sizes'][key]})" for key, label in STRATA
    ]
    nominal = payload["nominal"]

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.6), sharey=True)

    for ax, variant, title in (
        (axes[0], "absolute", "A. Absolute-residual intervals"),
        (axes[1], "normalized", "B. Width-normalized intervals"),
    ):
        width = 0.26
        for index, representation in enumerate(REPRESENTATION_ORDER):
            block = payload["representations"][representation]
            offsets = [position + (index - 1) * width for position in range(len(strata_keys))]
            values = [block[variant][key] for key in strata_keys]
            bars = ax.bar(
                offsets,
                values,
                width=width,
                label=representation,
                color=REPRESENTATION_COLORS[representation],
                alpha=0.85,
            )
            for bar, value in zip(bars, values):
                ax.annotate(
                    f"{value:.2f}",
                    (bar.get_x() + bar.get_width() / 2, value),
                    textcoords="offset points",
                    xytext=(0, 3),
                    ha="center",
                    fontsize=7.5,
                )
        ax.axhline(nominal, color="#111827", linestyle="--", linewidth=1.0)
        ax.set_xticks(range(len(strata_keys)))
        ax.set_xticklabels(strata_labels)
        ax.set_xlabel("experimental permittivity stratum")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.2)
        ax.set_ylim(0, 1.08)

    axes[0].set_ylabel("empirical coverage of the nominal 90% interval")
    axes[0].annotate(
        f"nominal {nominal:.2f}",
        xy=(len(strata_keys) - 0.5, nominal),
        ha="right",
        va="bottom",
        fontsize=8,
    )
    axes[1].legend(loc="upper right", fontsize=8, ncol=1)

    axes[0].annotate(
        (
            "Marginal coverage holds at the nominal level for every\n"
            "representation (0.915-0.916), but it is marginal in compounds:\n"
            "inside eps > 60 the same intervals cover 0.01-0.26 of the points."
        ),
        xy=(0.33, 0.70),
        xycoords="axes fraction",
        fontsize=7.5,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "#fef2f2", "edgecolor": "#fca5a5"},
    )
    axes[1].annotate(
        (
            "Width re-scaling by 1+|prediction| raises eps > 60 coverage to\n"
            "0.20-0.48 but does not restore it: it is still a marginal\n"
            "interval. The eps > 60 stratum holds 5 compounds, so these\n"
            "conditional values are an exploratory diagnostic, not a guarantee."
        ),
        xy=(0.02, 0.03),
        xycoords="axes fraction",
        fontsize=7.5,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )

    fig.suptitle(
        "Split-conformal coverage is marginal, and it collapses in the high-permittivity stratum",
        fontsize=11.5,
    )
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=180)
    plt.close(fig)


def build_summary(payload: dict) -> dict:
    return {
        "schema_version": "paper_figure_conformal_strata/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "figure": OUTPUT_PNG,
        "source_summary": SUMMARY_PATH,
        "source_summary_sha256": payload["summary_sha256"],
        "nominal_coverage": payload["nominal"],
        "strata_sizes": payload["strata_sizes"],
        "representations": payload["representations"],
        "caveats": payload["caveats"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive the payload and compare against the committed summary",
    )
    args = parser.parse_args(argv)

    payload = collect()
    summary = build_summary(payload)
    target = REPOSITORY_ROOT / OUTPUT_JSON
    if args.check:
        if not target.is_file():
            print(f"FAIL: {OUTPUT_JSON} is missing", file=sys.stderr)
            return 1
        with target.open(encoding="utf-8") as handle:
            committed = json.load(handle)
        drift = [
            key
            for key in summary
            if key != "generated_at_utc" and committed.get(key) != summary[key]
        ]
        if drift:
            print(f"FAIL: {OUTPUT_JSON} is stale for {', '.join(drift)}", file=sys.stderr)
            return 1
        print(f"PASS: {OUTPUT_JSON} matches the conformal probe summary")
        return 0

    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    render(payload, REPOSITORY_ROOT / OUTPUT_PNG)
    print(f"wrote {OUTPUT_JSON} and {OUTPUT_PNG}")
    for representation in REPRESENTATION_ORDER:
        block = payload["representations"][representation]
        print(
            f"  {representation:16s} marginal {block['marginal']:.4f} "
            f"lt20 {block['absolute']['lt20']:.4f} "
            f"20-60 {block['absolute']['20_60']:.4f} "
            f"gt60 {block['absolute']['gt60']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())