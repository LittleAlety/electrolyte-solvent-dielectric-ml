"""Figure 1: growth and source composition of the dielectric corpus.

Every number in this figure is re-derived from committed local artifacts; the
probe trains nothing and writes no dataset file.

Panel A reads the compound count of each released revision straight from its
own CSV. The version-to-file mapping matches
``scripts/check_paper_artifact_consistency.py``: the confusingly named
``data/dielectric_v03.csv`` is the current v0.3.3 roster, while the 243-row
v0.3 revision lives in ``data/dielectric_v031.csv``.

Panel B decomposes the current v0.3.3 roster by ``evidence_level``. The
modelling subset is not taken from that roster: it is read from the frozen
v0.3.2 ablation summary and re-checked against the exclusion arithmetic that
``probes/dielectric_representation_ablation.py`` enforces, namely

    fitted + exclusion-file rows + physical-feature failures + not-model_ready
        == rows of the source table

so a figure caption cannot quote a subset the pipeline no longer produces.

Usage:
    python probes/paper_figure_dataset_growth.py
    python probes/paper_figure_dataset_growth.py --check
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from electrolyte_ml.exporting import canonical_text_sha256

DATASET_PATH = "data/dielectric_v03.csv"
ABLATION_SUMMARY_PATH = "probes/v032_ablation_summary.json"
OUTPUT_PNG = "probes/artifacts/paper_fig1_dataset_growth.png"
OUTPUT_JSON = "probes/paper_figure_dataset_growth_summary.json"

# Version label -> the CSV that holds that revision's roster.
VERSION_FILES = (
    ("v0.1", "data/dielectric_v01.csv"),
    ("v0.2", "data/dielectric_v02.csv"),
    ("v0.3", "data/dielectric_v031.csv"),
    ("v0.3.2", "data/dielectric_v032.csv"),
    ("v0.3.3", "data/dielectric_v03.csv"),
)

EXPECTED_COUNTS = {"v0.1": 100, "v0.2": 210, "v0.3": 243, "v0.3.2": 245, "v0.3.3": 246}

EVIDENCE_LABELS = {
    "v0.2_primary_or_critical_compilation": "v0.2 core: primary measurements\nor critical compilations",
    "open_access_review_table": "Open-access review tables\n(2024-2026)",
    "primary": "Primary literature\n(open access)",
    "secondary_compilation_unverified": "Secondary compilation\n(no traceable primary)",
}


def _read_rows(relative_path: str) -> list[dict[str, str]]:
    path = REPOSITORY_ROOT / relative_path
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _flag_counts(rows: list[dict[str, str]], column: str) -> dict[str, int]:
    counter = Counter((row.get(column) or "").strip() or "unlabelled" for row in rows)
    return dict(counter)


def collect() -> dict:
    """Return the figure payload plus the digest of every input it read."""
    counts: dict[str, int] = {}
    rows_by_version: dict[str, list[dict[str, str]]] = {}
    digests: dict[str, str] = {}
    for label, relative_path in VERSION_FILES:
        rows = _read_rows(relative_path)
        counts[label] = len(rows)
        rows_by_version[label] = rows
        digests[relative_path] = canonical_text_sha256(REPOSITORY_ROOT / relative_path)

    for label, expected in EXPECTED_COUNTS.items():
        if counts[label] != expected:
            raise SystemExit(
                f"{label} roster is {counts[label]} rows, expected {expected}; "
                "a release file changed, so the figure must be re-derived"
            )

    current_rows = rows_by_version["v0.3.3"]
    evidence = _flag_counts(current_rows, "evidence_level")
    gate = _flag_counts(current_rows, "model_ready")
    temperature_band = _flag_counts(current_rows, "temperature_band")
    chodera_overlap = sum(
        1 for row in current_rows if "chodera" in (row.get("source_scope") or "")
    )
    withheld_names = [
        row["name"]
        for row in current_rows
        if (row.get("model_ready") or "").strip().lower() != "true"
    ]
    if sum(evidence.values()) != len(current_rows):
        raise SystemExit("evidence_level does not cover every row of the current roster")

    with (REPOSITORY_ROOT / ABLATION_SUMMARY_PATH).open(encoding="utf-8") as handle:
        ablation = json.load(handle)
    digests[ABLATION_SUMMARY_PATH] = canonical_text_sha256(
        REPOSITORY_ROOT / ABLATION_SUMMARY_PATH
    )

    source_rows = int(ablation["source_count"])
    fitted_rows = int(ablation["compound_count"])
    exclusion_rows = int(ablation["excluded_count"])
    feature_failures = int(ablation["failed_physical_feature_count"])
    withheld_not_ready = int(ablation["withheld_not_model_ready_count"])
    if fitted_rows + exclusion_rows + feature_failures + withheld_not_ready != source_rows:
        raise SystemExit(
            "the frozen ablation accounting no longer closes: "
            f"{fitted_rows} + {exclusion_rows} + {feature_failures} + "
            f"{withheld_not_ready} != {source_rows}"
        )
    source_gate = _flag_counts(rows_by_version["v0.3.2"], "model_ready")
    if int(source_gate.get("true", 0)) - feature_failures != fitted_rows:
        raise SystemExit("the source-table gate does not reproduce the fitted row count")

    return {
        "counts": counts,
        "evidence": evidence,
        "model_ready": gate,
        "temperature_band": temperature_band,
        "chodera_overlap": chodera_overlap,
        "roster_rows": len(current_rows),
        "withheld_names": withheld_names,
        "source_rows": source_rows,
        "fitted_rows": fitted_rows,
        "exclusion_rows": exclusion_rows,
        "feature_failures": feature_failures,
        "withheld_not_ready": withheld_not_ready,
        "source_gate": source_gate,
        "inputs": digests,
    }


def render(payload: dict, output_png: Path) -> None:
    counts = payload["counts"]
    labels = [label for label, _ in VERSION_FILES]
    values = [counts[label] for label in labels]

    fig, axes = plt.subplots(1, 2, figsize=(13.8, 5.8), gridspec_kw={"width_ratios": [1, 1.2]})

    # Panel A: released roster size per revision.
    ax = axes[0]
    bars = ax.bar(labels, values, color="#2563eb", alpha=0.85)
    for bar, value in zip(bars, values):
        ax.annotate(
            str(value),
            (bar.get_x() + bar.get_width() / 2, value),
            textcoords="offset points",
            xytext=(0, 3),
            ha="center",
            fontsize=9,
        )
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        ax.annotate(
            f"{delta:+d}",
            (index - 0.5, max(values[index], values[index - 1]) + 14),
            ha="center",
            fontsize=8,
            color="#7c3aed",
        )
    ax.axhline(payload["fitted_rows"], color="#dc2626", linestyle="--", linewidth=1.0)
    ax.annotate(
        f"modelling subset {payload['fitted_rows']} rows\n(frozen on the v0.3.2 table)",
        xy=(len(values) - 0.55, payload["fitted_rows"]),
        ha="left",
        va="center",
        fontsize=7.5,
        color="#dc2626",
    )
    ax.set_xlim(-0.7, len(values) + 0.55)
    ax.set_ylabel("compounds in the released roster")
    ax.set_title("A. Corpus growth")
    ax.set_ylim(0, max(values) * 1.24)
    ax.grid(axis="y", alpha=0.2)

    # Panel B: provenance mix of the current roster.
    ax = axes[1]
    order = sorted(payload["evidence"].items(), key=lambda item: item[1])
    names = [EVIDENCE_LABELS.get(key, key) for key, _ in order]
    sizes = [value for _, value in order]
    colors = [
        "#dc2626" if key == "secondary_compilation_unverified" else "#059669"
        for key, _ in order
    ]
    bars = ax.barh(names, sizes, color=colors, alpha=0.85)
    for bar, size in zip(bars, sizes):
        ax.annotate(
            str(size),
            (size, bar.get_y() + bar.get_height() / 2),
            textcoords="offset points",
            xytext=(4, 0),
            va="center",
            fontsize=9,
        )
    ax.set_xlabel("compounds in the v0.3.3 roster")
    ax.set_title("B. Provenance mix of the current roster")
    ax.grid(axis="x", alpha=0.2)
    ax.set_xlim(0, max(sizes) * 1.22)

    extended = payload["temperature_band"].get("extended_temperature", 0)
    ax.annotate(
        (
            f"roster {payload['roster_rows']}: model_ready true "
            f"{payload['model_ready'].get('true', 0)} / false {payload['model_ready'].get('false', 0)}\n"
            f"{payload['temperature_band'].get('room_temperature', 0)} room-temperature rows, "
            f"{extended} extended (EC, 313.15 K)\n"
            f"ThermoML rows also present in Chodera 2015: {payload['chodera_overlap']}\n"
            f"v0.3.2 modelling subset: {payload['fitted_rows']} rows\n"
            f"   {payload['source_rows']} - {payload['exclusion_rows']} excluded - "
            f"{payload['feature_failures']} xTB failures - {payload['withheld_not_ready']} not ready"
        ),
        xy=(0.14, 0.03),
        xycoords="axes fraction",
        fontsize=7,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )

    fig.suptitle("Dataset growth and source composition", fontsize=12)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=180)
    plt.close(fig)


def build_summary(payload: dict) -> dict:
    return {
        "schema_version": "paper_figure_dataset_growth/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "figure": OUTPUT_PNG,
        "sources": dict(VERSION_FILES),
        "counts": payload["counts"],
        "evidence_counts": payload["evidence"],
        "model_ready_counts": payload["model_ready"],
        "temperature_band_counts": payload["temperature_band"],
        "chodera_overlap_rows": payload["chodera_overlap"],
        "roster_rows": payload["roster_rows"],
        "withheld_not_model_ready_names": payload["withheld_names"],
        "source_rows": payload["source_rows"],
        "fitted_rows": payload["fitted_rows"],
        "exclusion_file_rows_in_source": payload["exclusion_rows"],
        "physical_feature_failure_rows": payload["feature_failures"],
        "withheld_not_model_ready_rows": payload["withheld_not_ready"],
        "source_table_model_ready_counts": payload["source_gate"],
        "inputs": payload["inputs"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive the payload and compare against the committed summary",
    )
    args = parser.parse_args(argv)

    summary = build_summary(collect())
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
        print(f"PASS: {OUTPUT_JSON} matches the committed rosters")
        return 0

    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    render(collect(), REPOSITORY_ROOT / OUTPUT_PNG)
    print(f"wrote {OUTPUT_JSON} and {OUTPUT_PNG}")
    for label in summary["counts"]:
        print(f"  {label:7s} {summary['counts'][label]:4d}")
    print(f"  fitted  {summary['fitted_rows']:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())