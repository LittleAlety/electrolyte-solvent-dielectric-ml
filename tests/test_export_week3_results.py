from __future__ import annotations

import json

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week3_results import export_week3_results


def test_week3_export_is_self_contained_and_manifested(tmp_path) -> None:
    export_week3_results(tmp_path)

    summary = json.loads((tmp_path / "week3_summary.json").read_text(encoding="utf-8"))
    assert (tmp_path / "SHA256SUMS").is_file()
    assert verify_export_manifest(tmp_path) == []
    assert {
        "chodera_crosscheck",
        "chodera_summary",
        "dielectric_ext",
        "dielectric_ext_observations",
        "dielectric_ext_summary",
        "dielectric_kernel_comparison",
        "dielectric_kernel_summary",
        "dielectric_kernel_plot",
        "dielectric_kernel_report",
        "dielectric_kernel_docs",
        "viscosity_baseline_predictions",
        "viscosity_baseline_summary",
        "viscosity_baseline_plot",
        "viscosity_baseline_report",
        "viscosity_baseline_docs",
        "al_round1_longlist",
        "al_round1_top30",
        "al_round1_summary",
        "al_round1_plot",
        "al_round1_report",
        "al_round1_docs",
        "p4_redox_merged",
        "p4_redox_predictions",
        "p4_redox_summary",
        "p4_redox_linear_plot",
        "p4_redox_parity_plot",
        "p4_redox_notebook",
        "p4_redox_report",
        "p4_redox_docs",
        "data_expansion_audit",
        "data_expansion_summary",
        "milestone_2_report",
        "data_expansion_docs",
    }.issubset(summary["outputs"])
    for relative_path in summary["outputs"].values():
        assert (tmp_path / relative_path).is_file()
