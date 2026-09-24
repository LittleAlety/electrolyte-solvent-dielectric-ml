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

README_TEXT = """# Week 8 交付包

数据血缘: v0.3.12（规范数据集 dielectric_v03.csv，246 行 x 38 列）
生成脚本: probes/export_week8_results.py

## 入口
- week8_report.md - Week 8 基准冻结主报告
- week8_summary.json - 机器可读摘要
- verification.json - verifier 退出码与报告
- SHA256SUMS - 本目录全部文件的清单

## 关键内容
- C1 分裂共形: week8_c1_split_conformal.md, dielectric_split_conformal_*
- C2 排序头: week8_c2_ranking_head.md, dielectric_ranking_head_*
- C4 Onsager Delta: week8_c4_onsager_delta.md, dielectric_onsager_delta_*
- C6 NBS alpha 协调化: week8_c6_nbs_alpha_harmonization.md,
  nbs514_alpha_harmonization_*
- 模型比较: model_comparison.md, v034_model_ready_gate.md
- 论文快照: paper/ 下的 7 份文件

## 校验
在本目录运行:
python scripts/verify_export_manifests.py --output-dir <本目录>
python scripts/check_paper_artifact_consistency.py
python scripts/verify_v032_benchmarks.py

## 仍未闭环
- VC 与 FEC 两行仍 model_ready=false；
- 主基准的 236 行拟合集与 240 行 model-ready 行未被 v0.3.12 改动；
- FEC 107 腿与 MOPN 独立确认仍需访问权限或新证据。
"""
ARTIFACTS = (
    ("reports/week8_benchmark_freeze.md", "week8_report.md"),
    ("reports/week8_c1_split_conformal.md", "week8_c1_split_conformal.md"),
    ("reports/week8_c2_ranking_head.md", "week8_c2_ranking_head.md"),
    ("reports/week8_c4_onsager_delta.md", "week8_c4_onsager_delta.md"),
    (
        "reports/week8_c6_nbs_alpha_harmonization.md",
        "week8_c6_nbs_alpha_harmonization.md",
    ),
    ("reports/thermoml_local_coverage_audit.md", "thermoml_local_coverage_audit.md"),
    ("reports/v034_model_ready_gate.md", "v034_model_ready_gate.md"),
    ("reports/model_comparison.md", "model_comparison.md"),
    ("reports/g1plus_crawl_round3_findings.md", "g1plus_crawl_round3_findings.md"),
    ("probes/g1plus_crawl_round3_evidence.json", "g1plus_crawl_round3_evidence.json"),
    ("reports/g1plus_crawl_round4_findings.md", "g1plus_crawl_round4_findings.md"),
    ("probes/g1plus_crawl_round4_evidence.json", "g1plus_crawl_round4_evidence.json"),
    ("tests/test_g1plus_crawl_round4.py", "test_g1plus_crawl_round4.py"),
    ("reports/g1plus_crawl_round5_findings.md", "g1plus_crawl_round5_findings.md"),
    ("probes/g1plus_crawl_round5_evidence.json", "g1plus_crawl_round5_evidence.json"),
    ("tests/test_g1plus_crawl_round5.py", "test_g1plus_crawl_round5.py"),
    ("probes/g1plus_round5_crosscheck.py", "g1plus_round5_crosscheck.py"),
    (
        "probes/g1plus_round5_crosscheck_summary.json",
        "g1plus_round5_crosscheck_summary.json",
    ),
    ("paper/full_draft.md", "paper/full_draft.md"),
    ("paper/abstract_and_intro.md", "paper/abstract_and_intro.md"),
    ("paper/methods_data_records.md", "paper/methods_data_records.md"),
    ("paper/technical_validation.md", "paper/technical_validation.md"),
    ("paper/benchmark_and_figures.md", "paper/benchmark_and_figures.md"),
    ("paper/code_and_data.md", "paper/code_and_data.md"),
    ("paper/outline.md", "paper/outline.md"),
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
        "probes/dielectric_split_conformal_summary.json",
        "dielectric_split_conformal_summary.json",
    ),
    (
        "probes/dielectric_ranking_head_summary.json",
        "dielectric_ranking_head_summary.json",
    ),
    (
        "probes/dielectric_onsager_delta_summary.json",
        "dielectric_onsager_delta_summary.json",
    ),
    (
        "probes/dielectric_onsager_delta_feature_audit.json",
        "dielectric_onsager_delta_feature_audit.json",
    ),
    (
        "probes/dielectric_onsager_delta_paired_comparison.json",
        "dielectric_onsager_delta_paired_comparison.json",
    ),
    (
        "probes/nbs514_alpha_harmonization_summary.json",
        "nbs514_alpha_harmonization_summary.json",
    ),
    (
        "probes/thermoml_local_coverage_summary.json",
        "thermoml_local_coverage_summary.json",
    ),
    (
        "data/processed/dielectric_split_conformal_splits.csv",
        "dielectric_split_conformal_splits.csv",
    ),
    (
        "data/processed/dielectric_ranking_head_metrics.csv",
        "dielectric_ranking_head_metrics.csv",
    ),
    (
        "data/processed/dielectric_ranking_head_predictions.csv",
        "dielectric_ranking_head_predictions.csv",
    ),
    (
        "data/processed/dielectric_ranking_head_qid_audit.csv",
        "dielectric_ranking_head_qid_audit.csv",
    ),
    (
        "data/processed/dielectric_onsager_delta_metrics.csv",
        "dielectric_onsager_delta_metrics.csv",
    ),
    (
        "data/processed/dielectric_onsager_delta_rows.csv",
        "dielectric_onsager_delta_rows.csv",
    ),
    (
        "data/processed/dielectric_onsager_delta_predictions.csv",
        "dielectric_onsager_delta_predictions.csv",
    ),
    (
        "data/processed/dielectric_onsager_delta_failure_cases.csv",
        "dielectric_onsager_delta_failure_cases.csv",
    ),
    (
        "data/processed/nbs514_alpha_harmonization.csv",
        "nbs514_alpha_harmonization.csv",
    ),
    (
        "data/processed/nbs514_alpha_internal_validation.csv",
        "nbs514_alpha_internal_validation.csv",
    ),
    (
        "data/processed/thermoml_local_coverage.csv",
        "thermoml_local_coverage.csv",
    ),
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
        "probes/artifacts/dielectric_split_conformal.png",
        "dielectric_split_conformal.png",
    ),
    (
        "probes/artifacts/nbs514_alpha_harmonization.png",
        "nbs514_alpha_harmonization.png",
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
    "scripts/verify_v032_benchmarks.py",
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
    conformal = read_json(
        source_root / "probes" / "dielectric_split_conformal_summary.json"
    )
    ranking = read_json(source_root / "probes" / "dielectric_ranking_head_summary.json")
    onsager_delta = read_json(
        source_root / "probes" / "dielectric_onsager_delta_summary.json"
    )
    nbs_alpha = read_json(
        source_root / "probes" / "nbs514_alpha_harmonization_summary.json"
    )
    local_coverage = read_json(
        source_root / "probes" / "thermoml_local_coverage_summary.json"
    )
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
            "c1_split_conformal": {
                "nominal_coverage": 1.0
                - conformal["design"]["alpha"],
                "min_calibration_n": conformal["design"]["min_calibration_n"],
                "target_strata_sizes": conformal["exchangeability"][
                    "target_strata_sizes"
                ],
                "series": {
                    name: {
                        "coverage": values["coverage"]["mean"],
                        "coverage_repeat_dispersion_interval": values["coverage"][
                            "repeat_dispersion_interval"
                        ],
                        "interval_width": values["interval_width"]["mean"],
                        "infinite_interval_rate": values["infinite_interval_rate"][
                            "mean"
                        ],
                        "coverage_lt20": values["coverage_lt20"]["mean"],
                        "coverage_20_60": values["coverage_20_60"]["mean"],
                        "coverage_gt60": values["coverage_gt60"]["mean"],
                        "normalized_coverage_gt60": values[
                            "normalized_coverage_gt60"
                        ]["mean"],
                    }
                    for name, values in conformal["series"].items()
                },
            },
            "c2_ranking_head": {
                "qid_count": ranking["qid_count"],
                "singleton_count": ranking["singleton_count"],
                "total_pair_capacity": ranking["total_pair_capacity"],
                "decision": ranking["decision"]["label"],
                "macro_pairwise_accuracy_ci95": ranking["decision"][
                    "macro_pairwise_accuracy_ci95"
                ],
                "global_spearman_ci95": ranking["decision"]["global_spearman_ci95"],
                "calibrated_mae_ci95": ranking["decision"]["calibrated_mae_ci95"],
                "primary_arm_results": {
                    arm: values["per_repeat_metric_summary"]
                    for arm, values in ranking["results"][
                        "primary_arm_results"
                    ].items()
                },
            },
            "c4_onsager_delta": {
                "decision": onsager_delta["decision"]["decision"],
                "headline_arm": onsager_delta["decision"]["headline_arm"],
                "best_confirmatory_overall_mae": onsager_delta["decision"][
                    "best_confirmatory_overall_mae"
                ],
                "onsager_promoted_to_standalone_predictor": onsager_delta[
                    "decision"
                ].get("onsager_promoted_to_standalone_predictor"),
                "learned_delta_layer_confirmed": onsager_delta["decision"].get(
                    "learned_delta_layer_confirmed"
                ),
            },
            "c6_nbs_alpha_harmonization": {
                "n_nbs_rows_in_v03": nbs_alpha["frozen_dataset"]["n_nbs_rows_in_v03"],
                "correctability_counts": nbs_alpha["harmonization_v03_subset"][
                    "correctability_counts"
                ],
                "absolute_delta_epsilon": nbs_alpha["harmonization_v03_subset"][
                    "absolute_delta_epsilon"
                ],
                "internal_validation": {
                    "n_pairs": nbs_alpha["internal_validation"]["n_pairs"],
                    "n_pairs_strict": nbs_alpha["internal_validation"]["n_pairs_strict"],
                    "mean_relative_error": nbs_alpha["internal_validation"][
                        "mean_relative_error"
                    ],
                },
                "thermoml_overlap_keys": nbs_alpha["thermoml_overlap"][
                    "keys_with_pure_near_298_observation"
                ],
            },
            "thermoml_local_coverage": {
                "xml_files_scanned": local_coverage["inputs"]["xml_files_scanned"],
                "extraction_rows": local_coverage["inputs"]["extraction_rows"],
                "summary": local_coverage["summary"],
            },
            "verification": verification["passed"],
        },
    )
    (week_root / "README.md").write_text(
        README_TEXT, encoding="utf-8", newline="\n"
    )
    written.append("README.md")
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
