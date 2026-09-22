"""Export Week 3 Chodera cross-check and high-temperature extension artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import write_export_manifest

DEFAULT_OUTPUT_DIR = Path(r"E:\Claude Code\电解质ML\成果输出\week3")


def export_week3_results(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = REPOSITORY_ROOT / "probes" / "artifacts"
    copies = {
        REPOSITORY_ROOT / "data" / "processed" / "chodera_crosscheck.csv": output_dir
        / "chodera_crosscheck.csv",
        REPOSITORY_ROOT / "probes" / "chodera_crosscheck_summary.json": output_dir
        / "chodera_crosscheck_summary.json",
        REPOSITORY_ROOT / "reports" / "chodera_crosscheck.md": output_dir
        / "chodera_crosscheck.md",
        artifacts / "chodera_crosscheck.png": output_dir
        / "chodera_crosscheck.png",
        REPOSITORY_ROOT / "data" / "dielectric_v01_ext.csv": output_dir
        / "dielectric_v01_ext.csv",
        REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_v01_ext_observations.csv": output_dir
        / "dielectric_v01_ext_observations.csv",
        REPOSITORY_ROOT / "probes" / "dielectric_v01_ext_summary.json": output_dir
        / "dielectric_v01_ext_summary.json",
        REPOSITORY_ROOT / "docs" / "week3" / "dielectric_v01_ext.md": output_dir
        / "dielectric_v01_ext.md",
        REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_kernel_comparison.csv": output_dir
        / "dielectric_kernel_comparison.csv",
        REPOSITORY_ROOT
        / "probes"
        / "dielectric_kernel_comparison_summary.json": output_dir
        / "dielectric_kernel_comparison_summary.json",
        REPOSITORY_ROOT / "reports" / "dielectric_kernel_comparison.md": output_dir
        / "dielectric_kernel_comparison.md",
        REPOSITORY_ROOT
        / "docs"
        / "week3"
        / "dielectric_kernel_comparison.md": output_dir
        / "dielectric_kernel_comparison_docs.md",
        artifacts
        / "dielectric_kernel_comparison.png": output_dir
        / "dielectric_kernel_comparison.png",
        REPOSITORY_ROOT
        / "data"
        / "processed"
        / "viscosity_baseline_predictions.csv": output_dir
        / "viscosity_baseline_predictions.csv",
        REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json": output_dir
        / "viscosity_baseline_summary.json",
        REPOSITORY_ROOT / "reports" / "viscosity_baseline.md": output_dir
        / "viscosity_baseline.md",
        REPOSITORY_ROOT / "docs" / "week3" / "viscosity_baseline.md": output_dir
        / "viscosity_baseline_docs.md",
        artifacts / "viscosity_baseline_parity.png": output_dir
        / "viscosity_baseline_parity.png",
    }
    for source, destination in copies.items():
        shutil.copy2(source, destination)
    outputs = {
        "chodera_crosscheck": "chodera_crosscheck.csv",
        "chodera_summary": "chodera_crosscheck_summary.json",
        "chodera_plot": "chodera_crosscheck.png",
        "chodera_report": "chodera_crosscheck.md",
        "dielectric_ext": "dielectric_v01_ext.csv",
        "dielectric_ext_observations": "dielectric_v01_ext_observations.csv",
        "dielectric_ext_summary": "dielectric_v01_ext_summary.json",
        "dielectric_ext_docs": "dielectric_v01_ext.md",
        "dielectric_kernel_comparison": "dielectric_kernel_comparison.csv",
        "dielectric_kernel_summary": "dielectric_kernel_comparison_summary.json",
        "dielectric_kernel_plot": "dielectric_kernel_comparison.png",
        "dielectric_kernel_report": "dielectric_kernel_comparison.md",
        "dielectric_kernel_docs": "dielectric_kernel_comparison_docs.md",
        "viscosity_baseline_predictions": "viscosity_baseline_predictions.csv",
        "viscosity_baseline_summary": "viscosity_baseline_summary.json",
        "viscosity_baseline_plot": "viscosity_baseline_parity.png",
        "viscosity_baseline_report": "viscosity_baseline.md",
        "viscosity_baseline_docs": "viscosity_baseline_docs.md",
    }
    (output_dir / "week3_summary.json").write_text(
        json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_export_manifest(output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    export_week3_results(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
