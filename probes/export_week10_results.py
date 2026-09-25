"""Export the Week 10 adversarial-review (M-1) decision record."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week10"

BASELINE_COMMIT = "795b52c"

README_TEXT = """# Week 10 交付包（M-1 论文对抗审读）

数据血缘: 规范数据集 data/dielectric_v03.csv 未改动（246 行 × 38 列，digest 见 week10_summary.json）
生成脚本: probes/export_week10_results.py

## 入口
- week10_summary.json - 机器可读摘要（M-1 分级结论、修复清单、守卫自检、闸门退出码）
- verification.json - verifier 退出码与报告
- paper_adversarial_review_round.md - 审读记录全文
- SHA256SUMS - 本目录全部文件的清单

## 本周闭环（M-1）
审读基线 `795b52c`，reviewer 为独立只读 agent，主线程为 writer/auditor。

- **C-1（Critical，已修）**：摘要"表征天花板"六个数（0.801 / 0.689 / 0.223 / 0.354 / 0.366 / 0.814）
  是 v0.3.4 已明示 superseded 的 pre-gate 值，而同文件 :25 已写正确值，摘要自相矛盾。
  改为 0.802 / 0.722 / 0.240 / 0.342 / 0.364 / 0.828。
- **I-2（Important，已修）**：补 Tier-3/Tier-4 未闭环披露 —— 缺口是"权限/入口阻断"，不是"查无此值"。
- **m-1 / m-2 / m-3 / m-5（Minor，已修）**：Hagiyama/MOPN 断言改为可证伪的"as of 2026-09-25"；
  817-819 vs 820-822 转述归属改正；Fig6 拆开 74 行（56 / 0.757）与 42 行（32 / 0.762）两个分母；
  Fig5 补误差棒口径。
- **I-1（reviewer 主张 C2/C4 负结果缺失）→ 驳回**：两条负结果的**内容与数字**均在文
  （methods 159-164 与 abstract 76；methods 188-192 与 technical_validation 283-292），
  缺的只是内部标签；手册要求的是内容保留，不是标签入文。

## 防回归守卫
`check_abstract_ceiling_numbers()` 把摘要那句的 6 个数字绑到 `probes/v032_ablation_summary.json`。
原先的 `check_main_benchmark_table()` 只读 `benchmark_and_figures.md`，摘要散文是校验盲区，
这正是 C-1 能活到本轮的原因。守卫已自检：把 0.802 改回 0.801 会让检查器非零退出。

## 投稿包（Week 11–12）
- paper/cover_letter.md - Scientific Data 投稿信草稿（含 [TODO] 占位，发信前必须替换）
- paper/submission_checklist.md - 打 tag / 投稿的机械清单（含 Zenodo 必须先于 tag 的顺序规则）

## 校验
从仓库根目录运行（scripts/ 不在交付包内，此处同名脚本为副本）:
python scripts/check_paper_artifact_consistency.py
python scripts/build_paper_full_draft.py --check
python scripts/verify_paper_figures.py
python scripts/verify_dielectric_v03.py
python scripts/verify_export_manifests.py --output-dir <本目录>

## 仍未闭环（不阻塞 v1.0）
- FEC 与 VC 维持 model_ready=false；冲突如实记录即闭环。
- Hagiyama 2008 无开放全文（第①级兜底穷尽），只剩馆际互借。
- DC-200 成员表需向通讯作者索取（ACS Nano SI 无成员表，作者仓库亦无）。
"""

ARTIFACTS = (
    ("reports/paper_adversarial_review_round.md", "paper_adversarial_review_round.md"),
    ("scripts/check_paper_artifact_consistency.py", "check_paper_artifact_consistency.py"),
    ("tests/test_paper_artifact_consistency.py", "test_paper_artifact_consistency.py"),
    ("scripts/verify_paper_figures.py", "verify_paper_figures.py"),
    ("tests/test_paper_figures.py", "test_paper_figures.py"),
    ("paper/full_draft.md", "paper/full_draft.md"),
    ("paper/abstract_and_intro.md", "paper/abstract_and_intro.md"),
    ("paper/methods_data_records.md", "paper/methods_data_records.md"),
    ("paper/technical_validation.md", "paper/technical_validation.md"),
    ("paper/benchmark_and_figures.md", "paper/benchmark_and_figures.md"),
    ("paper/code_and_data.md", "paper/code_and_data.md"),
    ("paper/outline.md", "paper/outline.md"),
    ("paper/cover_letter.md", "paper/cover_letter.md"),
    ("paper/submission_checklist.md", "paper/submission_checklist.md"),
    ("probes/artifacts/paper_fig1_dataset_growth.png", "artifacts/paper_fig1_dataset_growth.png"),
    ("probes/artifacts/v032_ablation.png", "artifacts/v032_ablation.png"),
    ("probes/artifacts/domain_gap_parity.png", "artifacts/domain_gap_parity.png"),
    (
        "probes/artifacts/paper_fig4_conformal_strata.png",
        "artifacts/paper_fig4_conformal_strata.png",
    ),
    ("probes/artifacts/v032_target_scaffold.png", "artifacts/v032_target_scaffold.png"),
    (
        "probes/artifacts/nbs514_alpha_harmonization.png",
        "artifacts/nbs514_alpha_harmonization.png",
    ),
)

VERIFIERS = (
    "scripts/check_paper_artifact_consistency.py",
    "scripts/build_paper_full_draft.py --check",
    "scripts/verify_paper_figures.py",
    "scripts/verify_dielectric_v03.py",
)

FIGURES = (
    (1, "artifacts/paper_fig1_dataset_growth.png", "paper_figure_dataset_growth_summary.json"),
    (2, "artifacts/v032_ablation.png", "v032_ablation_summary.json"),
    (3, "artifacts/domain_gap_parity.png", "g2_domain_gap_summary.json"),
    (4, "artifacts/paper_fig4_conformal_strata.png", "paper_figure_conformal_strata_summary.json"),
    (5, "artifacts/v032_target_scaffold.png", "v032_target_scaffold_summary.json"),
    (6, "artifacts/nbs514_alpha_harmonization.png", "nbs514_alpha_harmonization_summary.json"),
)


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").strip()


def _dielectric_digest(verification: dict) -> str | None:
    for check in verification.get("checks", []):  # type: ignore[union-attr]
        if check.get("command") == "scripts/verify_dielectric_v03.py":
            report = check.get("report") or {}
            return report.get("output_sha256")
    return None


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

    full_draft_lines = len(
        (source_root / "paper" / "full_draft.md").read_text(encoding="utf-8").splitlines()
    )

    write_json(
        week_root / "week10_summary.json",
        {
            "schema_version": "week10_export/v1",
            "week": WEEK,
            "head_commit": _head_commit(source_root),
            "review_baseline_commit": BASELINE_COMMIT,
            "dielectric_v03_sha256": _dielectric_digest(verification),
            "review": {
                "reviewer": "Mill (independent read-only agent)",
                "verdict": (
                    "1 Critical + 1 Important + 4 Minor fixed; "
                    "1 reviewer claim rejected; 1 static finding left on record"
                ),
                "critical_fixed": [
                    (
                        "abstract ceiling numbers 0.801/0.689/0.223/0.354/0.366/0.814 "
                        "-> 0.802/0.722/0.240/0.342/0.364/0.828"
                    ),
                ],
                "important_fixed": [
                    "disclose Tier-3/Tier-4 as attempted-but-not-closed",
                ],
                "minor_fixed": [
                    "817-819 restates PC only; 820-822 restates PC and EC",
                    "no open full text discoverable as of 2026-09-25",
                    "Fig6 splits the 74-row (56/0.757) and 42-row (32/0.762) denominators",
                    "Fig5 declares the +/-1 SD across five partitions convention",
                ],
                "rejected": [
                    (
                        "C2 ranking-head and C4 Onsager-delta negative results are present "
                        "in descriptive prose with their numbers; only the internal labels "
                        "are absent, and the manual requires content retention, not labels"
                    ),
                ],
                "left_on_record": [
                    (
                        "probes/dielectric_target_and_scaffold.py relative_to(REPOSITORY_ROOT) "
                        "on the non-paper --refresh-summary path; static finding, not reproduced"
                    ),
                ],
            },
            "guard": {
                "function": "check_abstract_ceiling_numbers",
                "artifact": "probes/v032_ablation_summary.json",
                "self_test": (
                    "reverting 0.802 -> 0.801 makes the checker exit 1 with "
                    "abstract_and_intro.md: Physical spearman is 0.801, artifact says 0.802"
                ),
                "regression_test": (
                    "tests/test_paper_artifact_consistency.py::"
                    "test_a_stale_abstract_ceiling_number_is_rejected"
                ),
            },
            "gates": {
                "full_draft_lines": full_draft_lines,
                "pytest": "847 passed",
                "ruff": "exit 0",
                "compileall": "exit 0",
            },
            "figures": [
                {"number": number, "artifact": artifact, "summary": summary}
                for number, artifact, summary in FIGURES
            ],
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
