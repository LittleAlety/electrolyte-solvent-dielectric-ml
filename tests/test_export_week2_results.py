from __future__ import annotations

import json
import subprocess
from pathlib import Path

from xgboost import XGBRegressor

from probes.export_week2_results import REPOSITORY_ROOT, export_week2_results


def _resolved_output_path(output_dir: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (output_dir / path).resolve()


def test_week2_export_is_self_contained(tmp_path) -> None:
    export_week2_results(tmp_path)

    exported_summary_path = tmp_path / "p2_summary.json"
    exported_summary = json.loads(exported_summary_path.read_text(encoding="utf-8"))
    output_root = tmp_path.resolve()

    assert {
        "diagnostics_notebook",
        "diagnostics_summary",
        "diagnostics_csv",
        "target_distribution_plot",
        "model_comparison_plot",
        "dataset_dielectric_v01",
        "dataset_viscosity_v01",
        "dataset_dielectric_observations",
        "dataset_summary",
        "dataset_v01_docs",
        "dielectric_gpr_summary",
        "dielectric_gpr_predictions",
        "dielectric_gpr_parity",
        "dielectric_gpr_report",
        "dielectric_gpr_docs",
        "dielectric_baseline_comparison",
        "dielectric_repeated_cv",
        "dielectric_learning_curve",
        "dielectric_baseline_diagnostics_summary",
        "dielectric_baseline_comparison_plot",
        "dielectric_learning_curve_plot",
        "dielectric_baseline_diagnostics_report",
        "dielectric_baseline_diagnostics_docs",
    }.issubset(exported_summary["outputs"])
    for value in exported_summary["outputs"].values():
        destination = _resolved_output_path(tmp_path, value)
        assert destination.is_relative_to(output_root)
        assert destination.is_file()

    model_path = _resolved_output_path(tmp_path, exported_summary["outputs"]["model_json"])
    model = XGBRegressor()
    model.load_model(model_path)
    assert model_path.name == "p2_dipole_model.json"


def test_week2_model_artifact_is_not_git_ignored() -> None:
    model_path = REPOSITORY_ROOT / "probes" / "artifacts" / "p2_dipole_model.json"

    assert model_path.is_file()
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(model_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result.returncode == 1
