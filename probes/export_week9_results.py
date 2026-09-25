"""Export the Week 9 decision, figure-convergence and manuscript artefacts."""

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

WEEK = "week9"

README_TEXT = """# Week 9 交付包

数据血缘: v0.3.14（规范数据集 dielectric_v03.csv，246 行 x 38 列；拟合子集 236 行，冻结在 v0.3.2 表上）
生成脚本: probes/export_week9_results.py

## 入口
- week9_summary.json - 机器可读摘要（六图清单、D1/D2 闭环数字、条件覆盖率、FEC/VC 状态）
- verification.json - verifier 退出码与报告
- SHA256SUMS - 本目录全部文件的清单

## 本周闭环
- **D1 EC 313.15 K 例外**：规则写入 Methods，并补预注册 leave-EC-out 敏感性探针
  （baseline 7,080 个冻结预测值逐位复现；EC 在训练折出现 0 次；家族排名不变）。
- **D2 四行重新归类**：3 个离子液体 + Fe(CO)5 从 feature_failure 改为
  out_of_scope_ionic_or_organometallic，不动任何拟合行。
- **六图收敛**：论文图节从 8 图（其中 2 图无产物）收敛为 6 图，每图都在图注里
  写明产物路径与生成脚本；适用域内容改为散文但保留 33.66% 触发率。
- **G2 口径修正**：parity 图标题的样本数由数据推出（29），不再硬编码 30。
- **J-STAGE 前提证伪 + PC/EC 免费旁证**：计划里「走错了门、J-STAGE 开放」的前提被三重独立证据推翻
  （Crossref 出版商为 OUP、DOI 302 解析到 academic.oup.com、OpenAlex oa_status=closed 且
  any_repository_has_fulltext=false；**期刊根 /browse/cl 亦 404**，故不是 URL 写错）；同时 PC/EC 由
  Nanbu 2007（J-STAGE 开放）ref 12 = Riddick 4th ed. (1986) 取得免费旁证，已写入论文
  Technical Validation。证据见 jstage_corroboration.md。

## 六图清单
1. paper_fig1_dataset_growth.png - 语料增长与来源构成（新探针）
2. v032_ablation.png - 主基准（R2/MAE/RMSE/Spearman）
3. domain_gap_parity.png - G2 域外 parity（29 个新溶剂）
4. paper_fig4_conformal_strata.png - 共形条件覆盖率塌缩（新探针，用户点名要求）
5. v032_target_scaffold.png - 目标变换与 scaffold/cluster 外推
6. nbs514_alpha_harmonization.png - NBS 514 温度协调化

## 校验
从仓库根目录运行（scripts/ 不在交付包内，此处同名脚本为副本）:
python scripts/verify_d1_leave_ec_out.py
python scripts/verify_paper_figures.py
python scripts/check_paper_artifact_consistency.py
python scripts/build_paper_full_draft.py --check
python scripts/verify_export_manifests.py --output-dir <本目录>

## 仍未闭环（不阻塞 v1.0）
- VC 与 FEC 维持 model_ready=false；FEC 78.4@296.15 K 与 ~107@298.15 K 两条腿
  仍不平均、不裁决，仅登记为下游引文温度漂移冲突；
- 3-methoxypropionitrile 无独立一手测量，维持 secondary_compilation_unverified；
- Hagiyama 2008 原文仍未读到，且**该文不在 J-STAGE**（期刊根目录同样 404），DOI 解析到 OUP 闭源页，
  OpenAlex 判定 closed 且无任何仓储全文；第①级 URL 重试已判定不可能成功，只剩馆际互借；
- PC/EC 已取得免费独立旁证（Nanbu 2007 -> ref 12 = Riddick 4th ed.）：PC 64.92@25 C 对库存 64.9
  （偏差 0.03%）、EC 89.78@40 C 对库存 90.5（偏差 0.80%），两者同温；
- eps > 60 条件覆盖率只有 5 个化合物支撑，只能作为 exploratory diagnostic。
"""

ARTIFACTS = (
    ("reports/d1_leave_ec_out_sensitivity.md", "d1_leave_ec_out_sensitivity.md"),
    ("scripts/verify_d1_leave_ec_out.py", "verify_d1_leave_ec_out.py"),
    ("probes/dielectric_leave_ec_out_summary.json", "dielectric_leave_ec_out_summary.json"),
    ("probes/artifacts/dielectric_leave_ec_out.png", "artifacts/dielectric_leave_ec_out.png"),
    (
        "reports/g1plus_fec_temperature_attribution_findings.md",
        "g1plus_fec_temperature_attribution_findings.md",
    ),
    (
        "probes/g1plus_fec_temperature_attribution_evidence.json",
        "g1plus_fec_temperature_attribution_evidence.json",
    ),
    ("reports/jstage_corroboration.md", "jstage_corroboration.md"),
    ("probes/jstage_corroboration_evidence.json", "jstage_corroboration_evidence.json"),
    ("tests/test_jstage_corroboration.py", "test_jstage_corroboration.py"),
    ("probes/g2_domain_gap_summary.json", "g2_domain_gap_summary.json"),
    ("probes/artifacts/domain_gap_parity.png", "artifacts/domain_gap_parity.png"),
    ("probes/paper_figure_dataset_growth.py", "paper_figure_dataset_growth.py"),
    (
        "probes/paper_figure_dataset_growth_summary.json",
        "paper_figure_dataset_growth_summary.json",
    ),
    (
        "probes/artifacts/paper_fig1_dataset_growth.png",
        "artifacts/paper_fig1_dataset_growth.png",
    ),
    ("probes/paper_figure_conformal_strata.py", "paper_figure_conformal_strata.py"),
    (
        "probes/paper_figure_conformal_strata_summary.json",
        "paper_figure_conformal_strata_summary.json",
    ),
    (
        "probes/artifacts/paper_fig4_conformal_strata.png",
        "artifacts/paper_fig4_conformal_strata.png",
    ),
    ("probes/artifacts/v032_ablation.png", "artifacts/v032_ablation.png"),
    ("probes/artifacts/v032_target_scaffold.png", "artifacts/v032_target_scaffold.png"),
    (
        "probes/artifacts/dielectric_split_conformal.png",
        "artifacts/dielectric_split_conformal.png",
    ),
    (
        "probes/artifacts/nbs514_alpha_harmonization.png",
        "artifacts/nbs514_alpha_harmonization.png",
    ),
    ("scripts/verify_paper_figures.py", "verify_paper_figures.py"),
    ("tests/test_paper_figures.py", "test_paper_figures.py"),
    ("paper/full_draft.md", "paper/full_draft.md"),
    ("paper/abstract_and_intro.md", "paper/abstract_and_intro.md"),
    ("paper/methods_data_records.md", "paper/methods_data_records.md"),
    ("paper/technical_validation.md", "paper/technical_validation.md"),
    ("paper/benchmark_and_figures.md", "paper/benchmark_and_figures.md"),
    ("paper/code_and_data.md", "paper/code_and_data.md"),
    ("paper/outline.md", "paper/outline.md"),
)

VERIFIERS = (
    "scripts/verify_d1_leave_ec_out.py",
    "scripts/verify_paper_figures.py",
    "scripts/check_paper_artifact_consistency.py",
    "scripts/build_paper_full_draft.py --check",
    "scripts/verify_v032_benchmarks.py",
)

FIGURES = (
    (1, "artifacts/paper_fig1_dataset_growth.png", "paper_figure_dataset_growth_summary.json"),
    (2, "artifacts/v032_ablation.png", "v032_ablation_summary.json"),
    (3, "artifacts/domain_gap_parity.png", "g2_domain_gap_summary.json"),
    (4, "artifacts/paper_fig4_conformal_strata.png", "paper_figure_conformal_strata_summary.json"),
    (5, "artifacts/v032_target_scaffold.png", "v032_target_scaffold_summary.json"),
    (6, "artifacts/nbs514_alpha_harmonization.png", "nbs514_alpha_harmonization_summary.json"),
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

    leave_ec_out = read_json(source_root / "probes" / "dielectric_leave_ec_out_summary.json")
    ablation = read_json(source_root / "probes" / "v032_ablation_summary.json")
    g2 = read_json(source_root / "probes" / "g2_domain_gap_summary.json")
    conformal_figure = read_json(
        source_root / "probes" / "paper_figure_conformal_strata_summary.json"
    )
    growth = read_json(source_root / "probes" / "paper_figure_dataset_growth_summary.json")
    fec = read_json(
        source_root / "probes" / "g1plus_fec_temperature_attribution_evidence.json"
    )
    jstage = read_json(source_root / "probes" / "jstage_corroboration_evidence.json")

    write_json(
        week_root / "week9_summary.json",
        {
            "dataset_version": "0.3.14",
            "fitted_rows": ablation["compound_count"],
            "input_sha256": ablation["input_sha256"],
            "figures": [
                {"number": number, "artifact": artifact, "source": source}
                for number, artifact, source in FIGURES
            ],
            "d1_leave_ec_out": {
                "removed_name": leave_ec_out["removed_name"],
                "removed_temperature_K": leave_ec_out["removed_temperature_K"],
                "removed_temperature_band": leave_ec_out["removed_temperature_band"],
                "baseline_matches_frozen_predictions": leave_ec_out[
                    "baseline_matches_frozen_predictions"
                ],
                "frozen_prediction_rows_checked": leave_ec_out[
                    "frozen_prediction_rows_checked"
                ],
                "ec_in_training_folds": leave_ec_out["ec_in_training_folds"],
                "same_fold_ids_for_235": leave_ec_out["same_fold_ids_for_235"],
                "family_ranking_changed": leave_ec_out["family_ranking"].get("changed"),
                "hybrid_ec_holdout": {
                    "target": leave_ec_out["ec_leave_one_out"]["Morgan+Physical"]["target"],
                    "prediction_mean": leave_ec_out["ec_leave_one_out"]["Morgan+Physical"][
                        "prediction_mean"
                    ],
                    "rank_percentile_among_235": leave_ec_out["ec_leave_one_out"][
                        "Morgan+Physical"
                    ]["rank_percentile_among_235"],
                },
                "hybrid_r2": {
                    "baseline_full_236": leave_ec_out["metrics"]["Morgan+Physical"][
                        "baseline_full_236"
                    ]["r2"]["mean"],
                    "baseline_surviving_235": leave_ec_out["metrics"]["Morgan+Physical"][
                        "baseline_surviving_235"
                    ]["r2"]["mean"],
                    "leave_ec_out_235": leave_ec_out["metrics"]["Morgan+Physical"][
                        "leave_ec_out_235"
                    ]["r2"]["mean"],
                },
            },
            "roster_gate": {
                "roster_rows": growth["roster_rows"],
                "model_ready_counts": growth["model_ready_counts"],
                "withheld_not_model_ready_names": growth["withheld_not_model_ready_names"],
                "physical_feature_failure_rows": growth["physical_feature_failure_rows"],
                "source_table_model_ready_counts": growth["source_table_model_ready_counts"],
            },
            "g2_domain_gap": {
                "train_count": g2["train_count"],
                "test_count": g2["test_count"],
                "metrics": g2["metrics"],
            },
            "conformal_conditional_coverage": {
                "nominal_coverage": conformal_figure["nominal_coverage"],
                "strata_sizes": conformal_figure["strata_sizes"],
                "representations": {
                    name: {
                        "marginal": values["marginal"],
                        "coverage_lt20": values["absolute"]["lt20"],
                        "coverage_20_60": values["absolute"]["20_60"],
                        "coverage_gt60": values["absolute"]["gt60"],
                        "normalized_coverage_gt60": values["normalized"]["gt60"],
                    }
                    for name, values in conformal_figure["representations"].items()
                },
                "caveats": conformal_figure["caveats"],
            },
            "fec_status": {
                "answer": fec["answer"],
                "decision": fec["decision"],
            },
            "jstage_route": {
                "hagiyama_premise_verdict": jstage["access_gate"]["verdict"],
                "hagiyama_doi": jstage["access_gate"]["doi"],
                "open_full_text_exists": False,
                "remaining_primary_route": "interlibrary loan / document delivery",
                "free_corroboration": [
                    {
                        "compound": target["compound"],
                        "stored_value": target["stored"]["value"],
                        "stored_T_K": target["stored"]["T_K"],
                        "corroborating_value": target["corroborating"]["value"],
                        "corroborating_T_C": target["corroborating"]["T_C"],
                        "relative_deviation_percent": target["relative_deviation_percent"],
                    }
                    for target in jstage["corroboration_gate"]["targets"]
                ],
            },
            "verification": verification["passed"],
        },
    )
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
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
    return 0 if result["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
