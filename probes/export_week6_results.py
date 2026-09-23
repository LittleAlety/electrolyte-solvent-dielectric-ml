"""Export the Week 6 v0.3 and model-freeze artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.verify_dielectric_v03 import (
    read_csv_rows as read_v03_rows,
)
from scripts.verify_dielectric_v03 import (
    verify_v03_rows,
)

DEFAULT_OUTPUT_ROOT = Path(r"E:\Claude Code\电解质ML\成果输出")
WEEK = "week6"
ARTIFACTS = (
    ("reports/week6_v03_model_freeze.md", "week6_report.md"),
    ("docs/week6/data_v03_and_model_freeze.md", "data_v03_and_model_freeze.md"),
    ("paper/outline.md", "scientific_data_outline.md"),
    ("data/dielectric_v03.csv", "dielectric_v03.csv"),
    (
        "data/processed/modern_solvent_public_observations.csv",
        "modern_solvent_public_observations.csv",
    ),
    (
        "data/processed/modern_solvent_public_review_observations.csv",
        "modern_solvent_public_review_observations.csv",
    ),
    (
        "data/processed/dielectric_v03_exclusions.csv",
        "dielectric_v03_exclusions.csv",
    ),
    (
        "data/processed/dielectric_physical_features_v03.csv",
        "dielectric_physical_features_v03.csv",
    ),
    (
        "data/processed/dielectric_applicability_flags.csv",
        "dielectric_applicability_flags.csv",
    ),
    (
        "data/processed/dielectric_density_feature_repeats.csv",
        "density_feature_repeats.csv",
    ),
    (
        "data/processed/dielectric_density_feature_predictions.csv",
        "density_feature_predictions.csv",
    ),
    (
        "data/processed/dielectric_mlp_probe_repeats.csv",
        "mlp_probe_repeats.csv",
    ),
    (
        "data/processed/dielectric_mlp_probe_predictions.csv",
        "mlp_probe_predictions.csv",
    ),
    (
        "data/processed/dielectric_chemprop_repeats.csv",
        "chemprop_repeats.csv",
    ),
    (
        "data/processed/dielectric_chemprop_predictions.csv",
        "chemprop_predictions.csv",
    ),
    (
        "data/processed/dielectric_v03_representation_ablation_repeats.csv",
        "v03_representation_ablation_repeats.csv",
    ),
    (
        "data/processed/dielectric_v03_representation_ablation_predictions.csv",
        "v03_representation_ablation_predictions.csv",
    ),
    ("probes/dielectric_v03_summary.json", "dielectric_v03_summary.json"),
    (
        "probes/dielectric_density_feature_summary.json",
        "density_feature_summary.json",
    ),
    ("probes/dielectric_mlp_probe_summary.json", "mlp_probe_summary.json"),
    ("probes/dielectric_chemprop_summary.json", "chemprop_summary.json"),
    (
        "probes/dielectric_v03_representation_ablation_summary.json",
        "v03_representation_ablation_summary.json",
    ),
    (
        "probes/artifacts/dielectric_density_feature_comparison.png",
        "density_feature_comparison.png",
    ),
    ("probes/artifacts/dielectric_mlp_probe.png", "mlp_probe.png"),
    ("probes/artifacts/model_comparison.png", "model_comparison.png"),
    (
        "probes/artifacts/dielectric_v03_representation_ablation.png",
        "v03_representation_ablation.png",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_sha256s(directory: Path) -> None:
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [
        f"{sha256_file(path)}  {path.relative_to(directory).as_posix()}"
        for path in files
    ]
    (directory / "SHA256SUMS").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def export_results(
    *,
    source_root: Path,
    output_root: Path,
    overwrite: bool = False,
) -> dict[str, object]:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing output: {week_root}")
    written: list[str] = []
    for source, destination in ARTIFACTS:
        source_path = source_root / source
        if not source_path.is_file():
            raise FileNotFoundError(f"missing artifact: {source_path}")
        destination_path = week_root / destination
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        written.append(destination_path.relative_to(output_root).as_posix())

    _, v03_rows = read_v03_rows(source_root / "data" / "dielectric_v03.csv")
    verification_errors = verify_v03_rows(v03_rows, minimum_additions=30)
    verification = {
        "passed": not verification_errors,
        "errors": verification_errors,
    }
    write_json(week_root / "verification.json", verification)

    density = json.loads(
        (
            source_root / "probes" / "dielectric_density_feature_summary.json"
        ).read_text(encoding="utf-8")
    )
    mlp = json.loads(
        (source_root / "probes" / "dielectric_mlp_probe_summary.json").read_text(
            encoding="utf-8"
        )
    )
    chemprop = json.loads(
        (
            source_root / "probes" / "dielectric_chemprop_summary.json"
        ).read_text(encoding="utf-8")
    )
    v03_model = json.loads(
        (
            source_root
            / "probes"
            / "dielectric_v03_representation_ablation_summary.json"
        ).read_text(encoding="utf-8")
    )
    write_json(
        week_root / "week6_summary.json",
        {
            "dataset_version": "0.3",
            "compound_count": len(v03_rows),
            "density_experimental_count": density["experimental_density_count"],
            "density_minus_xtb": density["density_minus_xtb"],
            "mlp_best": mlp["comparison"]["best_mlp"],
            "mlp_go_kill": mlp["comparison"]["go_kill"],
            "chemprop_summary": chemprop["summary"]["Chemprop_DMPNN_raw"],
            "v03_representation_summary": v03_model["summary"],
            "v03_compound_count_fitted": v03_model["compound_count"],
        },
    )
    write_sha256s(week_root)
    return {
        "output_root": str(output_root),
        "week": WEEK,
        "written": written,
        "verification": verification,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(
        source_root=REPOSITORY_ROOT,
        output_root=DEFAULT_OUTPUT_ROOT,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
