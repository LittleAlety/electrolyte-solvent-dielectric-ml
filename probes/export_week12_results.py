"""Export the Week 12 deliverables.

Covers the S-5 placebo verdict, the xTB thread-determinism fix, the Reaxys
dielectric first cut (five compounds) and the AL Round 3 open-access triage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week12"

README_TEXT = """# Week 12 交付包（placebo 判决 + xTB 线程修复 + Reaxys 第一刀 + MOPN 复验 + L3 回溯验证预注册 + OA 分流）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（digest
ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4）；
本轮全部产物为新增文件，v1.0 已发布工件未被触碰。
生成脚本: probes/export_week12_results.py

## 头条（一句话）

**S-5 三臂 placebo 判决为 `data_volume_effect`** —— Week 11 的 ΔR² = +0.1241
**不得对外引用**（Arm A 过、Arm B 剂量曲线非单调）。这是本轮最重要的结论，
也是唯一一条改变对外叙事的结果。

## 入口

- week12_summary.json - 机器可读摘要（四路结果 + 投稿门禁状态）
- verification.json - verifier 退出码与报告
- decisions_log.md - 含 §10（预注册，跑批前锁定）、§11（判决）、§12（手册回退恢复）、§13（Reaxys MOPN 复验）、§14（L3 预注册）、§15（本轮 amend：池闸门 + 阈值 rationale 勘误）
- dielectric_coverage_placebo_arms.md / .py / _summary.json - placebo 三臂本体
- artifacts/dielectric_coverage_placebo_arms_{folds,repeats,predictions}.csv - 逐折明细
- xtb_thread_determinism.md / _probe.py / _probe_summary.json / xtb_runner.py - 线程确定性修复
- reaxys_dielectric_queue_first_cut.md / .csv / _summary.json - Reaxys 第一刀（FEC/VC/GVL/DME/sulfolane）+ MOPN 复验（三级否定：物质层无介电分类 / 属性检索 0 条 / 文献层 112 篇无值）
- al_round3_oa_triage.md / .csv / _summary.json / .py - 37 条 OA 线索分流
- l3_backvalidation_prereg.json - L3 回溯验证**锁定预注册**（冠军集真值 / C1 K=20 / C2 0.10 与 0.15 eV / C3 种子 20260928 / 池规则 ≥100 + 池必须先落盘并记录 sha256 才允许评分的机读闸门）；正文见 decisions_log.md §14 与 §15，手册附录 U 与 U-6；守卫 test_l3_backvalidation_prereg.py
- manual_appendix_reconciliation.json / manual_appendix_j_snapshot.md - §12 手册正文回退恢复的机读证据（手册在仓库外，其抽取留在 tests/fixtures/；stale 命中 0 / forbidden 命中 0 / digest 钉住）

## 合规

- Reaxys 取值一律 `restricted_crosscheck_only`，**永不进可分发数据集**；手动逐条查询，未使用批量爬虫。
- 手动记录，无时间戳；带 `--overwrite` 重跑产物应逐字节一致。
"""

ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/dielectric_coverage_placebo_arms.md", "dielectric_coverage_placebo_arms.md"),
    ("probes/dielectric_coverage_placebo_arms.py", "dielectric_coverage_placebo_arms.py"),
    (
        "probes/dielectric_coverage_placebo_arms_summary.json",
        "dielectric_coverage_placebo_arms_summary.json",
    ),
    (
        "probes/artifacts/dielectric_coverage_placebo_arms_folds.csv",
        "artifacts/dielectric_coverage_placebo_arms_folds.csv",
    ),
    (
        "probes/artifacts/dielectric_coverage_placebo_arms_repeats.csv",
        "artifacts/dielectric_coverage_placebo_arms_repeats.csv",
    ),
    (
        "probes/artifacts/dielectric_coverage_placebo_arms_predictions.csv",
        "artifacts/dielectric_coverage_placebo_arms_predictions.csv",
    ),
    ("tests/test_dielectric_coverage_placebo_arms.py", "test_dielectric_coverage_placebo_arms.py"),
    ("reports/xtb_thread_determinism.md", "xtb_thread_determinism.md"),
    ("probes/xtb_thread_determinism_probe.py", "xtb_thread_determinism_probe.py"),
    (
        "probes/xtb_thread_determinism_probe_summary.json",
        "xtb_thread_determinism_probe_summary.json",
    ),
    ("tests/test_xtb_thread_determinism.py", "test_xtb_thread_determinism.py"),
    ("src/electrolyte_ml/xtb_runner.py", "xtb_runner.py"),
    ("reports/reaxys_dielectric_queue_first_cut.md", "reaxys_dielectric_queue_first_cut.md"),
    ("probes/reaxys_dielectric_queue_first_cut.csv", "reaxys_dielectric_queue_first_cut.csv"),
    (
        "probes/reaxys_dielectric_queue_first_cut_summary.json",
        "reaxys_dielectric_queue_first_cut_summary.json",
    ),
    (
        "probes/verify_reaxys_dielectric_queue_first_cut.py",
        "verify_reaxys_dielectric_queue_first_cut.py",
    ),
    ("reports/al_round3_oa_triage.md", "al_round3_oa_triage.md"),
    ("probes/al_round3_oa_triage.py", "al_round3_oa_triage.py"),
    ("probes/al_round3_oa_triage.csv", "al_round3_oa_triage.csv"),
    ("probes/al_round3_oa_triage_summary.json", "al_round3_oa_triage_summary.json"),
    (
        "probes/dielectric_coverage_paired_benchmark_summary.json",
        "dielectric_coverage_paired_benchmark_summary.json",
    ),
    ("reports/dielectric_coverage_paired_benchmark.md", "dielectric_coverage_paired_benchmark.md"),
    ("probes/l3_backvalidation_prereg.json", "l3_backvalidation_prereg.json"),
    ("tests/test_l3_backvalidation_prereg.py", "test_l3_backvalidation_prereg.py"),
    (
        "probes/manual_appendix_reconciliation.json",
        "manual_appendix_reconciliation.json",
    ),
    (
        "tests/fixtures/manual_appendix_j_snapshot.md",
        "manual_appendix_j_snapshot.md",
    ),
)

VERIFIERS = (
    "probes/verify_reaxys_dielectric_queue_first_cut.py",
    "scripts/verify_dielectric_observations_v11plus.py",
    "scripts/verify_dielectric_v03.py",
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


def _submission_state(source_root: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "scripts/check_release_readiness.py", "--phase", "submission"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    text = ((completed.stdout or "") + (completed.stderr or "")).strip()
    todos = [line.strip() for line in text.splitlines() if "unresolved TODO" in line]
    return {
        "exit_code": completed.returncode,
        "green": completed.returncode == 0,
        "remaining_todos": todos,
        "note": (
            "仍为红：cover letter 的三个作者项（姓名/单位/email）属个人数据，"
            "必须由用户提供，不得编造。"
        ),
    }


def _arm_block(summary: dict, name: str) -> dict:
    arm = summary.get("arms", {}).get(name, {})
    return {
        "train_pool_rows": arm.get("train_pool_rows"),
        "train_pool_compounds": arm.get("train_pool_compounds"),
        "hybrid_r2": arm.get("hybrid_r2"),
        "delta_vs_paired_base": arm.get("delta_vs_paired_base"),
    }


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    placebo = read_json(REPOSITORY_ROOT / "probes" / "dielectric_coverage_placebo_arms_summary.json")
    xtb = read_json(REPOSITORY_ROOT / "probes" / "xtb_thread_determinism_probe_summary.json")
    reaxys = read_json(REPOSITORY_ROOT / "probes" / "reaxys_dielectric_queue_first_cut_summary.json")
    triage = read_json(REPOSITORY_ROOT / "probes" / "al_round3_oa_triage_summary.json")

    summary = {
        "week": WEEK,
        "head_commit": _head_commit(REPOSITORY_ROOT),
        "frozen_dataset": {
            "path": "data/dielectric_v03.csv",
            "sha256": placebo.get("frozen_table", {}).get("sha256"),
            "digest_unchanged": placebo.get("integrity", {}).get("frozen_v03_digest_unchanged"),
        },
        "placebo_arms": {
            "decision": placebo.get("verdict", {}).get("decision"),
            "headline": placebo.get("verdict", {}).get("headline"),
            "observation_level_information_driven": placebo.get("verdict", {}).get(
                "observation_level_information_driven"
            ),
            "criteria": placebo.get("criteria"),
            "integrity_ok": placebo.get("integrity", {}).get("ok"),
            "seeds": placebo.get("seeds"),
            "arms": {
                "paired_base": _arm_block(placebo, "paired_base"),
                "paired_plus_coverage": _arm_block(placebo, "paired_plus_coverage"),
                "arm_a_label_placebo": _arm_block(placebo, "arm_a_label_placebo"),
                "arm_b_dose_25": _arm_block(placebo, "arm_b_dose_25"),
                "arm_b_dose_50": _arm_block(placebo, "arm_b_dose_50"),
                "arm_b_dose_75": _arm_block(placebo, "arm_b_dose_75"),
                "arm_c_mean_row_only": _arm_block(placebo, "arm_c_mean_row_only"),
                "arm_c_nearest_real_row": _arm_block(placebo, "arm_c_nearest_real_row"),
            },
            "integrity_scope_note": (
                "placebo 探针的 verification_passed=False 指的是 S-5 判据未全过，"
                "不是实现缺陷；15 项完整性自检全 PASS。"
            ),
        },
        "xtb_thread_determinism": {
            "root_cause": xtb.get("root_cause"),
            "fix": xtb.get("fix"),
            "deterministic_threads": xtb.get("deterministic_threads"),
            "verdict": xtb.get("verdict"),
        },
        "reaxys_first_cut": {
            "compounds": reaxys.get("extended_to"),
            "net_new_numbers": reaxys.get("net_new_numbers"),
            "local_observation_rows": reaxys.get("local_observation_rows"),
            "reaxys_data_model": reaxys.get("reaxys_data_model"),
            "mopn_ticket": reaxys.get("mopn_ticket"),
            "key_findings": reaxys.get("key_findings"),
            "open_items": reaxys.get("open_items"),
        },
        "al_round3_oa_triage": {
            "lead_count": triage.get("lead_count"),
            "priority_counts": triage.get("priority_counts"),
            "disposition_counts": triage.get("disposition_counts"),
            "epsilon_numeric_clue_count": triage.get("epsilon_numeric_clue_count"),
            "temperature_window_counts": triage.get("temperature_window_counts"),
            "api_requests_used": triage.get("api", {}).get("requests_used"),
            "unread_abstracts": len(triage.get("unread_abstracts", [])),
        },
        "submission_phase": _submission_state(REPOSITORY_ROOT),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week12_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
    write_sha256s(week_root)
    return summary


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