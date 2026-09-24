"""Export Week 4 and Week 5 artifacts to the user-facing output directory."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.verify_dielectric_representation_ablation import (
    verify as verify_representation,
)
from scripts.verify_dielectric_target_scaffold import (
    verify as verify_target_scaffold,
)

DEFAULT_OUTPUT_ROOT = Path(r"E:\Claude Code\电解质ML\成果输出")
ARTIFACTS: dict[str, tuple[tuple[str, str], ...]] = {
    "week4": (
        ("reports/week4_physical_features.md", "week4_report.md"),
        ("docs/week4/physical_feature_ablation.md", "physical_feature_ablation.md"),
        ("data/processed/dielectric_physical_features.csv", "dielectric_physical_features.csv"),
        ("data/processed/dielectric_representation_ablation_cv.csv", "representation_ablation_cv.csv"),
        (
            "data/processed/dielectric_representation_ablation_repeats.csv",
            "representation_ablation_repeats.csv",
        ),
        (
            "data/processed/dielectric_representation_ablation_predictions.csv",
            "representation_ablation_predictions.csv",
        ),
        (
            "probes/dielectric_representation_ablation_summary.json",
            "representation_ablation_summary.json",
        ),
        (
            "probes/artifacts/dielectric_representation_ablation.png",
            "representation_ablation.png",
        ),
        ("probes/p5b_xtb_timing.csv", "p5b_xtb_timing.csv"),
    ),
    "week5": (
        ("reports/week5_target_scaffold_database.md", "week5_report.md"),
        ("docs/week5/target_and_scaffold.md", "target_and_scaffold_protocol.md"),
        ("data/dielectric_v02.csv", "dielectric_v02.csv"),
        ("data/processed/database_recheck.csv", "database_recheck.csv"),
        ("probes/database_recheck.json", "database_recheck.json"),
        (
            "data/processed/dielectric_target_scaffold_metrics.csv",
            "target_scaffold_metrics.csv",
        ),
        (
            "data/processed/dielectric_target_scaffold_predictions.csv",
            "target_scaffold_predictions.csv",
        ),
        ("data/processed/dielectric_scaffold_folds.csv", "scaffold_fold_assignments.csv"),
        ("probes/dielectric_target_scaffold_summary.json", "target_scaffold_summary.json"),
        ("probes/artifacts/dielectric_target_scaffold.png", "target_scaffold.png"),
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_artifact(
    *,
    source_root: Path,
    output_root: Path,
    source: str,
    destination: str,
) -> Path:
    source_path = source_root / source
    if not source_path.is_file():
        raise FileNotFoundError(f"missing artifact: {source_path}")
    destination_path = output_root / destination
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return destination_path


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_sha256s(directory: Path) -> None:
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [
        f"{sha256_file(path)}  {path.relative_to(directory).as_posix()}"
        for path in files
    ]
    # Pin the newline so the manifest itself is byte-stable across platforms.
    with (directory / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def export_results(
    *,
    source_root: Path,
    output_root: Path,
) -> dict[str, object]:
    written: dict[str, list[str]] = {}
    for week, artifacts in ARTIFACTS.items():
        week_root = output_root / week
        written[week] = [
            _copy_artifact(
                source_root=source_root,
                output_root=week_root,
                source=source,
                destination=destination,
            ).relative_to(output_root).as_posix()
            for source, destination in artifacts
        ]

    representation_verification = verify_representation(source_root)
    target_scaffold_verification = verify_target_scaffold(source_root)
    _write_json(
        output_root / "week4" / "verification.json",
        representation_verification,
    )
    _write_json(
        output_root / "week5" / "verification.json",
        target_scaffold_verification,
    )

    target_summary = json.loads(
        (
            source_root / "probes" / "dielectric_target_scaffold_summary.json"
        ).read_text(encoding="utf-8")
    )
    database_recheck = json.loads(
        (source_root / "probes" / "database_recheck.json").read_text(
            encoding="utf-8"
        )
    )
    _write_json(
        output_root / "week5" / "week5_summary.json",
        {
            "headline": (
                "No universal target transform; raw hybrid leads random-CV R2, "
                "log Physical leads scaffold/cluster R2 and MAE."
            ),
            "target_transform_decisions": target_summary[
                "target_transform_decisions"
            ],
            "scaffold_cluster": target_summary["scaffold_cv"],
            "database_conclusion": database_recheck["conclusion"],
        },
    )

    for week in ARTIFACTS:
        _write_sha256s(output_root / week)
    return {
        "output_root": str(output_root),
        "written": written,
        "representation_verifier_passed": representation_verification["passed"],
        "target_scaffold_verifier_passed": target_scaffold_verification["passed"],
    }


def main() -> int:
    result = export_results(
        source_root=REPOSITORY_ROOT,
        output_root=DEFAULT_OUTPUT_ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
