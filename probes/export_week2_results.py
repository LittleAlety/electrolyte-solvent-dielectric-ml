"""Export Week 2 P2 results to the project output folder."""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path(r"E:\Claude Code\电解质ML\成果输出\week2")


def export_week2_results(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = REPOSITORY_ROOT / "probes" / "artifacts"
    copies = {
        REPOSITORY_ROOT
        / "probes"
        / "p2_battp30k_baseline.ipynb": output_dir
        / "p2_battp30k_baseline.ipynb",
        REPOSITORY_ROOT / "reports" / "p2_battp30k_report.md": output_dir
        / "p2_battp30k_report.md",
        REPOSITORY_ROOT / "data" / "processed" / "p2_learning_curve.csv": output_dir
        / "p2_learning_curve.csv",
        REPOSITORY_ROOT
        / "data"
        / "processed"
        / "p2_test_predictions.csv": output_dir
        / "p2_test_predictions.csv",
        artifacts / "p2_dipole_parity.png": output_dir / "p2_dipole_parity.png",
        artifacts
        / "p2_dipole_learning_curve.png": output_dir
        / "p2_dipole_learning_curve.png",
        artifacts / "p2_dipole_model.json": output_dir / "p2_dipole_model.json",
    }
    for source, destination in copies.items():
        shutil.copy2(source, destination)

    summary = json.loads(
        (REPOSITORY_ROOT / "probes" / "p2_summary.json").read_text(encoding="utf-8")
    )
    summary["outputs"] = {
        "parity_plot": "p2_dipole_parity.png",
        "learning_curve_plot": "p2_dipole_learning_curve.png",
        "learning_curve_csv": "p2_learning_curve.csv",
        "test_predictions_csv": "p2_test_predictions.csv",
        "model_json": "p2_dipole_model.json",
    }
    (output_dir / "p2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    export_week2_results(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
