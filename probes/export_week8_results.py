"""Export the Week 8 analysis-freeze and benchmark artefacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week8"
ARTIFACTS = (
    ("reports/week8_benchmark_freeze.md", "week8_report.md"),
    ("reports/v034_model_ready_gate.md", "v034_model_ready_gate.md"),
    ("reports/model_comparison.md", "model_comparison.md"),
    ("paper/full_draft.md", "paper/full_draft.md"),
    ("paper/abstract_and_intro.md", "paper/abstract_and_intro.md"),
    ("paper/methods_data_records.md", "paper/methods_data_records.md"),
    ("paper/technical_validation.md", "paper/technical_validation.md"),
    ("paper/benchmark_and_figures.md", "paper/benchmark_and_figures.md"),
    ("paper/code_and_data.md", "paper/code_and_data.md"),
    ("paper/outline.md", "paper/outline.md"),
    ("scripts/check_paper_artifact_consistency.py", "tools/check_paper_artifact_consistency.py"),
    ("probes/v032_ablation_summary.json", "v032_ablation_summary.json"),
    ("probes/v032_target_scaffold_summary.json", "v032_target_scaffold_summary.json"),
    (
        "probes/v032_controlled_comparison_summary.json",
        "v032_controlled_comparison_summary.json",
    ),
    (
        "probes/dielectric_v03_representation_ablation_summary.json",
        "dielectric_v03_representation_ablation_summary.json",
    ),
    (
        "probes/dielectric_mlp_calibration_summary.json",
        "dielectric_mlp_calibration_summary.json",
    ),
    ("probes/dielectric_mlp_probe_summary.json", "dielectric_mlp_probe_summary.json"),
    ("probes/dielectric_chemprop_summary.json", "dielectric_chemprop_summary.json"),
    (
        "probes/dielectric_density_feature_summary.json",
        "dielectric_density_feature_summary.json",
    ),
    ("data/processed/v032_ablation_predictions.csv", "v032_ablation_predictions.csv"),
    ("data/processed/v032_ablation_repeats.csv", "v032_ablation_repeats.csv"),
    ("data/processed/v032_ablation_cv.csv", "v032_ablation_cv.csv"),
    (
        "data/processed/v032_target_scaffold_predictions.csv",
        "v032_target_scaffold_predictions.csv",
    ),
    (
        "data/processed/v032_target_scaffold_metrics.csv",
        "v032_target_scaffold_metrics.csv",
    ),
    ("data/processed/v032_scaffold_folds.csv", "v032_scaffold_folds.csv"),
    (
        "probes/v032_controlled_comparison_repeats.csv",
        "v032_controlled_comparison_repeats.csv",
    ),
    (
        "probes/v032_controlled_comparison_repeats_oof.csv",
        "v032_controlled_comparison_repeats_oof.csv",
    ),
    (
        "data/processed/dielectric_v03_representation_ablation_predictions.csv",
        "dielectric_v03_representation_ablation_predictions.csv",
    ),
    (
        "data/processed/dielectric_v03_representation_ablation_repeats.csv",
        "dielectric_v03_representation_ablation_repeats.csv",
    ),
    (
        "data/processed/dielectric_mlp_calibration_repeats.csv",
        "dielectric_mlp_calibration_repeats.csv",
    ),
    (
        "data/processed/dielectric_mlp_calibration_predictions.csv",
        "dielectric_mlp_calibration_predictions.csv",
    ),
    ("probes/artifacts/v032_ablation.png", "v032_ablation.png"),
    ("probes/artifacts/v032_target_scaffold.png", "v032_target_scaffold.png"),
    (
        "probes/artifacts/v032_controlled_comparison.png",
        "v032_controlled_comparison.png",
    ),
    (
        "probes/artifacts/dielectric_v03_representation_ablation.png",
        "dielectric_v03_representation_ablation.png",
    ),
    (
        "probes/artifacts/dielectric_mlp_calibration.png",
        "dielectric_mlp_calibration.png",
    ),
    (
        "probes/artifacts/dielectric_density_feature_comparison.png",
        "dielectric_density_feature_comparison.png",
    ),
)
VERIFIERS = (
    "scripts/verify_dielectric_representation_ablation.py",
    "scripts/verify_dielectric_target_scaffold.py",
    "scripts/check_paper_artifact_consistency.py",
)


def export_results(
    *,
    source_root: Path = REPOSITORY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    overwrite: bool = False,
) -> dict[str, object]:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing output: {week_root}")
    written = copy_artifacts(source_root, week_root, ARTIFACTS)

    verification = run_verifiers(source_root, VERIFIERS)
    write_json(week_root / "verification.json", verification)

    ablation = read_json(source_root / "probes" / "v032_ablation_summary.json")
    ablation_v033 = read_json(
        source_root / "probes" / "dielectric_v03_representation_ablation_summary.json"
    )
    scaffold = read_json(source_root / "probes" / "v032_target_scaffold_summary.json")
    controlled = read_json(source_root / "probes" / "v032_controlled_comparison_summary.json")
    calibration = read_json(source_root / "probes" / "dielectric_mlp_calibration_summary.json")
    paired = controlled["paired_deltas"]["Morgan+Physical"]["r2"]
    write_json(
        week_root / "week8_summary.json",
        {
            "fitted_rows": ablation["compound_count"],
            "input_sha256": ablation["input_sha256"],
            "lineages": {
                "v0.3.2": {
                    "source_rows": ablation["source_count"],
                    "fitted_rows": ablation["compound_count"],
                    "curated_exclusions": ablation["excluded_count"],
                    "excluded_not_in_source": ablation["excluded_not_in_source"],
                    "feature_failures": ablation["failed_physical_feature_count"],
                },
                "v0.3.3": {
                    "source_rows": ablation_v033["source_count"],
                    "fitted_rows": ablation_v033["compound_count"],
                    "curated_exclusions": ablation_v033["excluded_count"],
                    "excluded_not_in_source": ablation_v033["excluded_not_in_source"],
                    "feature_failures": ablation_v033["failed_physical_feature_count"],
                },
            },
            "withheld_not_model_ready": ablation["withheld_not_model_ready_names"],
            "withheld_inchikeys": ablation["withheld_not_model_ready_inchikeys"],
            "accounting_identity": "fitted + feature_failures + curated_exclusions + withheld == source_rows",
            "main_benchmark_raw": {
                name: {
                    metric: values["mean"]
                    for metric, values in ablation["summary"][name].items()
                    if metric in {"r2", "mae", "spearman", "auc_gt30", "mae_lt20"}
                }
                for name in ("Morgan", "Physical", "Morgan+Physical")
            },
            "scaffold_cluster_5fold": {
                target: {
                    name: {
                        metric: values["mean"]
                        for metric, values in scaffold["summary"]["scaffold_cluster_5fold"][target][
                            name
                        ].items()
                        if metric in {"r2", "mae", "spearman"}
                    }
                    for name in ("Morgan", "Physical", "Morgan+Physical")
                }
                for target in ("raw", "log_epsilon_minus_one")
            },
            "controlled_pc_ec": {
                "baseline_r2": paired["baseline_mean"],
                "augmented_r2": paired["augmented_mean"],
                "delta_r2": paired["delta_mean"],
                "ci95": paired["delta_ci95"],
                "paired_t_pvalue": paired["paired_t_pvalue"],
                "wilcoxon_pvalue": paired.get("wilcoxon_pvalue"),
                "fold_churn_diagnostic": controlled["fold_churn_diagnostic"],
                "pc_ec_external_holdout": {
                    name: {
                        compound.get("name"): {
                            "target": compound.get("target"),
                            "prediction_mean": compound.get("prediction_mean"),
                        }
                        for compound in values.values()
                    }
                    for name, values in controlled["pc_ec_external_holdout"].items()
                },
            },
            "mlp_calibration": {
                "compound_count": calibration.get("compound_count"),
                "summary": calibration.get("summary"),
            },
            "verification": verification["passed"],
        },
    )
    write_sha256s(week_root)
    return {
        "week": WEEK,
        "output": str(week_root),
        "written_count": len(written),
        "verification_passed": verification["passed"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
