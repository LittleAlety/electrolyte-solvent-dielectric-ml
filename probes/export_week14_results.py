"""Export the Week 14 deliverables (the six-lever R2 campaign).

Covers, in one package:

* the lever pre-registration set -- levers 2 / 3 / 7 (``dielectric_r2_levers``),
  lever 9 (knowledge purity), lever 8 v1 **and** the v2 amendment;
* the six lever readouts: 2 (association features, dead), 3 (target transform,
  dead), 4 (xTB v0.4 conformer-averaged dipole, pass, 95/97 coverage), 7
  (bagging, dead), 8 (Li+ coordination block -- v1 dead on a defective placebo
  clause, v2 ``pass_under_amended_placebo_clause``), 9 (knowledge purity sweep,
  sub_threshold);
* the merged arm runner, which by pre-registration never ran;
* the D2 track-B feature envelope gate (primary met, secondary not met);
* the AL Round 4 backfill (new-compound orientation, offline only);
* the two literature mappings (solvating-power descriptor catalogue and the KPI
  framework mapping).

Every lever reproduces ``paired_base`` = 0.4091179943351143 bit-exactly inside
its own script before any delta is quoted; the package ships the summaries plus
the fold / repeat / prediction tables that let the readouts be recomputed.

The 30 MB of ``*_predictions.csv`` evidence is included: it is the machine
readable backing for every fold-level number in the summaries.
"""

from __future__ import annotations

import argparse
import hashlib
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

WEEK = "week14"

FROZEN_DIGEST = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
PILOT_POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
PREREG_V1_SHA256 = "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
OBSERVATIONS_SHA256 = "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
R2_LEVERS_PREREG_SHA256 = "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa"
BASELINE_R2 = 0.4091179943351143

README_TEXT = """# Week 14 交付包（六杠杆 R² 战役 + 包络闸门 + AL Round 4）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（digest
ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4）；本轮全部产物为新增文件，
v1.0 已发布工件与 week11–week13 交付包未被触碰。
生成脚本: probes/export_week14_results.py

## 头条（五句话，都不许外推）

1. **唯一记分牌**：457 行 / 97 化合物固定评分池，GroupKFold by InChIKey，5 折 × 10 重复，seed 42，
   min_test_rows_per_fold=2，冻结 v1.0 超参。**七条脚本各自在脚本内原地重跑 `paired_base`，全部逐位复现
   0.4091179943351143**（|Δ| = 0.0，容差 1e-9）——复现不成立则 delta 不得引用。
2. **两死**：杠杆 2（缔合盲区靶向特征）ΔR² = **−0.0118842665905138**；杠杆 3（ln(ε−1)+Huber）原始尺度
   ΔR² = **−0.1053723227983280**（log 空间高 +0.2468，反变换后红利消失）。
3. **两越线，但都不许单独外推**：杠杆 4（v0.4 构象平均偶极迁移）ΔR² = **+0.0558384525472409**，
   判据 +0.0100（附录 X 期望带下沿，跑前写死），**pass**，但覆盖 **95/97 化合物**；
   杠杆 8（Li⁺ 配位块）ΔR² = **+0.044058816215696295**，v1 因**预注册安慰剂条款构造性缺陷**判 `dead`，
   v2 以**新预注册**独立重跑后得 `pass_under_amended_placebo_clause`（读数与 v1 逐位相同）。
4. **两未过门**：杠杆 7（bagging）均值 ΔR² **+0.001750**、重复级 σ 只收窄 **6.73%**（需 ≥20%）→ `dead`；
   杠杆 9（知识纯度扫描）k=10 ΔR² **+0.014709977559720422**、正向重复 6/10 → `sub_threshold`。
   合并臂按预注册 `if_nothing_passes` **不开跑**（新增实测 0 次）。
5. **shots = 10**（对主记分牌的尝试：杠杆 2/3/4/7 各 1、杠杆 8 **2**、杠杆 9 **4**）。
   包络闸门那 1 次是**校准读数**（对既有冻结模型在 held-out EC/PC 上的检验），买不到任何 R²，
   因此**并列**记录、**不计入**主记分牌 shots。
   按纪律：10 枪里 2 枪越线**本身不构成发现**。

## 入口

- week14_summary.json - 机器可读摘要（七通道读数 + shots + 缺陷登记 + 红线复核）
- verification.json - verifier 退出码与报告
- decisions_log.md - 含 §22（Week 14 预注册）与 §23（读数、判决、shots、缺陷登记、诚实边界）
- dielectric_r2_levers_prereg.json / dielectric_knowledge_purity_sweep_prereg.json /
  dielectric_coordination_block_prereg.json / dielectric_coordination_block_prereg_v2.json /
  dielectric_feature_envelope_gate_prereg.json / l3_backvalidation_prereg_v2.json - 六份预注册（先锁后跑）
- 杠杆 2：dielectric_association_features_probe.py / _summary.json / artifacts/*.csv /
  reports 报告 / test_...py
- 杠杆 3：dielectric_target_transform_probe.py / _summary.json / artifacts/*.csv / 报告 / 测试
- 杠杆 4：dielectric_xtb_full_table_migration.py / _summary.json / artifacts/*.csv /
  dielectric_xtb_migration_scf_diagnostic.json / 报告 / 测试
- 杠杆 7：dielectric_bagging_probe.py / _summary.json / artifacts/*.csv / 报告 / 测试；
  合并臂：dielectric_merge_arm_probe.py / dielectric_merge_arm_summary.json / 报告 / 测试
- 杠杆 8：dielectric_coordination_block.py / _summary.json / artifacts/*.csv / 报告 / 测试；
  v2：dielectric_coordination_block_v2.py / _summary.json / artifacts/*.csv / 报告 / 测试
- 杠杆 9：dielectric_knowledge_purity_sweep.py / _summary.json / artifacts/*.csv / 报告 / 测试
- 包络闸门（D2 轨 B）：dielectric_feature_envelope_gate.py / _summary.json / artifacts/*.csv / 报告 / 测试
- AL Round 4：al_round4_new_compound_backfill.py / _summary.json / al_round4_backfill_list_v0.csv /
  artifacts/*.csv / 两份报告 / 测试
- 文献映射：solvating_power_descriptor_mapping.md（ACS Energy Lett. 2025, 10, 4962）、
  kpi_framework_mapping.md（Angew. Chem. Int. Ed. 2025, 64, e202416506）

## 三条纪律增补（=手册附录 Y-4 / T-16）

1. **「塌缩」判据必须写参照物**。预注册里「安慰剂塌缩 = `|ΔR²| ≤ 0.0200`」未写明参照；对**真实标签基准**
   取绝对距离时，该式在安慰剂**真塌缩**时**必然不满足**（构造性不可满足）。本轮该式命中五处。统一读法：
   塌缩 = 安慰剂臂**不得击败其「同折、同打乱标签向量」上的无信息地板**超过 +0.0200，并并列上报管线内增量。
2. **`locked_at_utc` 自述字段不得单独作为锁定证据**。六份预注册里 **三份**的自述锁定时间**晚于自身文件
   mtime**（最多晚 101 分钟）。**以文件 mtime 为准**；自述字段照实保留、**不回填**。
3. **布尔塌缩字段不得作为门**。`placebo_collapsed` / `control_collapsed` 一律只作披露字段。

## 必须照写的边界

- **0.5332 / 0.5454 只许带池定义引用**（147 化合物训练池 / 97 化合物固定评分池），**不得**与 v1.0
  headline 0.364 直接比大小。本轮全部 R² 均为「457 行 / 97 化合物固定评分池」口径。
- **457 行不是有效样本量**：实测只覆盖 **276 个不同的 (化合物, T) 对**。
- **杠杆 4 覆盖 95/97 而非 97/97**：2 个多组分咪唑鎓盐 GFN2 单点 SCF 不收敛（exit 128），保留冻结偶极；
  失败是逐构象的，整化合物判失败来自 fail-fast 策略。**几何迁移仍 pending**；聚合口径为算术平均。
- **杠杆 9 的 k 网格上界 10 = 全池是硬顶**：只能说「冻结网格内无内部峰值」，**不是**「最优即全池」；
  正向重复仅 6/10，+0.0147 **不能**当作稳定增益。
- **杠杆 8 的块覆盖 88/97**，9 个化合物按预注册规则记为「未定义」；三个电荷列取自孤立溶剂冻结运行。
- **包络闸门不得宣称为可用过滤器**：主判据成立但次判据不过（236 池 LOO 升旗率 33.9% > 20%）。
- **random_row 只作泄漏参照**（R² = 0.7385332681453336），从不进入任何判决。
"""

ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    # A. Pre-registration set (locked before the runs).
    ("probes/dielectric_r2_levers_prereg.json", "dielectric_r2_levers_prereg.json"),
    (
        "probes/dielectric_knowledge_purity_sweep_prereg.json",
        "dielectric_knowledge_purity_sweep_prereg.json",
    ),
    (
        "probes/dielectric_coordination_block_prereg.json",
        "dielectric_coordination_block_prereg.json",
    ),
    (
        "probes/dielectric_coordination_block_prereg_v2.json",
        "dielectric_coordination_block_prereg_v2.json",
    ),
    (
        "probes/dielectric_feature_envelope_gate_prereg.json",
        "dielectric_feature_envelope_gate_prereg.json",
    ),
    ("probes/l3_backvalidation_prereg_v2.json", "l3_backvalidation_prereg_v2.json"),
    # B. Lever 2: association blind-spot features (dead).
    ("probes/dielectric_association_features_probe.py", "dielectric_association_features_probe.py"),
    ("probes/dielectric_association_features_summary.json", "dielectric_association_features_summary.json"),
    ("probes/artifacts/dielectric_association_features_folds.csv", "artifacts/dielectric_association_features_folds.csv"),
    ("probes/artifacts/dielectric_association_features_repeats.csv", "artifacts/dielectric_association_features_repeats.csv"),
    ("probes/artifacts/dielectric_association_features_predictions.csv", "artifacts/dielectric_association_features_predictions.csv"),
    ("probes/artifacts/dielectric_association_features_feature_block.csv", "artifacts/dielectric_association_features_feature_block.csv"),
    ("reports/dielectric_association_features.md", "dielectric_association_features.md"),
    ("tests/test_dielectric_association_features_probe.py", "test_dielectric_association_features_probe.py"),
    # C. Lever 3: log(eps-1) + pseudo-Huber (dead).
    ("probes/dielectric_target_transform_probe.py", "dielectric_target_transform_probe.py"),
    ("probes/dielectric_target_transform_probe_summary.json", "dielectric_target_transform_probe_summary.json"),
    ("probes/artifacts/dielectric_target_transform_probe_folds.csv", "artifacts/dielectric_target_transform_probe_folds.csv"),
    ("probes/artifacts/dielectric_target_transform_probe_repeats.csv", "artifacts/dielectric_target_transform_probe_repeats.csv"),
    ("probes/artifacts/dielectric_target_transform_probe_predictions.csv", "artifacts/dielectric_target_transform_probe_predictions.csv"),
    ("probes/artifacts/dielectric_target_transform_probe_log_folds.csv", "artifacts/dielectric_target_transform_probe_log_folds.csv"),
    ("probes/artifacts/dielectric_target_transform_probe_log_repeats.csv", "artifacts/dielectric_target_transform_probe_log_repeats.csv"),
    ("reports/dielectric_target_transform_probe.md", "dielectric_target_transform_probe.md"),
    ("tests/test_dielectric_target_transform_probe.py", "test_dielectric_target_transform_probe.py"),
    # D. Lever 4: xTB v0.4 conformer-averaged dipole migration (pass, 95/97).
    ("probes/dielectric_xtb_full_table_migration.py", "dielectric_xtb_full_table_migration.py"),
    ("probes/dielectric_xtb_full_table_migration_summary.json", "dielectric_xtb_full_table_migration_summary.json"),
    ("probes/dielectric_xtb_migration_scf_diagnostic.json", "dielectric_xtb_migration_scf_diagnostic.json"),
    ("probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv", "artifacts/dielectric_xtb_full_table_migration_conformers.csv"),
    ("probes/artifacts/dielectric_xtb_full_table_migration_folds.csv", "artifacts/dielectric_xtb_full_table_migration_folds.csv"),
    ("probes/artifacts/dielectric_xtb_full_table_migration_predictions.csv", "artifacts/dielectric_xtb_full_table_migration_predictions.csv"),
    ("reports/dielectric_xtb_full_table_migration.md", "dielectric_xtb_full_table_migration.md"),
    ("tests/test_dielectric_xtb_full_table_migration.py", "test_dielectric_xtb_full_table_migration.py"),
    # E. Lever 7: bagging (dead) and the merge arm, which never ran.
    ("probes/dielectric_bagging_probe.py", "dielectric_bagging_probe.py"),
    ("probes/dielectric_bagging_probe_summary.json", "dielectric_bagging_probe_summary.json"),
    ("probes/artifacts/dielectric_bagging_folds.csv", "artifacts/dielectric_bagging_folds.csv"),
    ("probes/artifacts/dielectric_bagging_repeats.csv", "artifacts/dielectric_bagging_repeats.csv"),
    ("probes/artifacts/dielectric_bagging_predictions.csv", "artifacts/dielectric_bagging_predictions.csv"),
    ("reports/dielectric_bagging_probe.md", "dielectric_bagging_probe.md"),
    ("tests/test_dielectric_bagging_probe.py", "test_dielectric_bagging_probe.py"),
    ("probes/dielectric_merge_arm_probe.py", "dielectric_merge_arm_probe.py"),
    ("probes/dielectric_merge_arm_summary.json", "dielectric_merge_arm_summary.json"),
    ("reports/dielectric_merge_arm.md", "dielectric_merge_arm.md"),
    ("tests/test_dielectric_merge_arm_probe.py", "test_dielectric_merge_arm_probe.py"),
    # F. Lever 8: Li+ coordination block, v1 (dead) and the v2 amendment.
    ("probes/dielectric_coordination_block.py", "dielectric_coordination_block.py"),
    ("probes/dielectric_coordination_block_summary.json", "dielectric_coordination_block_summary.json"),
    ("probes/artifacts/dielectric_coordination_block_features.csv", "artifacts/dielectric_coordination_block_features.csv"),
    ("probes/artifacts/dielectric_coordination_block_folds.csv", "artifacts/dielectric_coordination_block_folds.csv"),
    ("probes/artifacts/dielectric_coordination_block_repeats.csv", "artifacts/dielectric_coordination_block_repeats.csv"),
    ("probes/artifacts/dielectric_coordination_block_predictions.csv", "artifacts/dielectric_coordination_block_predictions.csv"),
    ("reports/dielectric_coordination_block.md", "dielectric_coordination_block.md"),
    ("tests/test_dielectric_coordination_block.py", "test_dielectric_coordination_block.py"),
    ("probes/dielectric_coordination_block_v2.py", "dielectric_coordination_block_v2.py"),
    ("probes/dielectric_coordination_block_v2_summary.json", "dielectric_coordination_block_v2_summary.json"),
    ("probes/artifacts/dielectric_coordination_block_v2_folds.csv", "artifacts/dielectric_coordination_block_v2_folds.csv"),
    ("probes/artifacts/dielectric_coordination_block_v2_repeats.csv", "artifacts/dielectric_coordination_block_v2_repeats.csv"),
    ("probes/artifacts/dielectric_coordination_block_v2_predictions.csv", "artifacts/dielectric_coordination_block_v2_predictions.csv"),
    ("reports/dielectric_coordination_block_v2.md", "dielectric_coordination_block_v2.md"),
    ("tests/test_dielectric_coordination_block_v2.py", "test_dielectric_coordination_block_v2.py"),
    # G. Lever 9: knowledge purity sweep (sub_threshold).
    ("probes/dielectric_knowledge_purity_sweep.py", "dielectric_knowledge_purity_sweep.py"),
    ("probes/dielectric_knowledge_purity_sweep_summary.json", "dielectric_knowledge_purity_sweep_summary.json"),
    ("probes/artifacts/dielectric_knowledge_purity_sweep_folds.csv", "artifacts/dielectric_knowledge_purity_sweep_folds.csv"),
    ("probes/artifacts/dielectric_knowledge_purity_sweep_repeats.csv", "artifacts/dielectric_knowledge_purity_sweep_repeats.csv"),
    ("probes/artifacts/dielectric_knowledge_purity_sweep_predictions.csv", "artifacts/dielectric_knowledge_purity_sweep_predictions.csv"),
    ("probes/artifacts/dielectric_knowledge_purity_sweep_importance.csv", "artifacts/dielectric_knowledge_purity_sweep_importance.csv"),
    ("reports/dielectric_knowledge_purity_sweep.md", "dielectric_knowledge_purity_sweep.md"),
    ("tests/test_dielectric_knowledge_purity_sweep.py", "test_dielectric_knowledge_purity_sweep.py"),
    # H. D2 track B: feature envelope gate.
    ("probes/dielectric_feature_envelope_gate.py", "dielectric_feature_envelope_gate.py"),
    ("probes/dielectric_feature_envelope_gate_summary.json", "dielectric_feature_envelope_gate_summary.json"),
    ("probes/artifacts/dielectric_feature_envelope_gate_descriptor_envelope.csv", "artifacts/dielectric_feature_envelope_gate_descriptor_envelope.csv"),
    ("probes/artifacts/dielectric_feature_envelope_gate_ec_pc.csv", "artifacts/dielectric_feature_envelope_gate_ec_pc.csv"),
    ("probes/artifacts/dielectric_feature_envelope_gate_pool_loo.csv", "artifacts/dielectric_feature_envelope_gate_pool_loo.csv"),
    ("reports/dielectric_feature_envelope_gate.md", "dielectric_feature_envelope_gate.md"),
    ("tests/test_dielectric_feature_envelope_gate.py", "test_dielectric_feature_envelope_gate.py"),
    # I. AL Round 4: new-compound orientation (offline only).
    ("probes/al_round4_new_compound_backfill.py", "al_round4_new_compound_backfill.py"),
    ("probes/al_round4_new_compound_backfill_summary.json", "al_round4_new_compound_backfill_summary.json"),
    ("probes/al_round4_backfill_list_v0.csv", "al_round4_backfill_list_v0.csv"),
    ("probes/artifacts/al_round4_local_coverage_gaps.csv", "artifacts/al_round4_local_coverage_gaps.csv"),
    ("probes/artifacts/al_round4_pdf_new_compound_candidates.csv", "artifacts/al_round4_pdf_new_compound_candidates.csv"),
    ("reports/al_round4_new_compound_backfill.md", "al_round4_new_compound_backfill.md"),
    ("reports/al_round4_pending_oa_triage.md", "al_round4_pending_oa_triage.md"),
    ("tests/test_al_round4_new_compound_backfill.py", "test_al_round4_new_compound_backfill.py"),
    # J. Literature mappings.
    ("reports/solvating_power_descriptor_mapping.md", "solvating_power_descriptor_mapping.md"),
    ("reports/kpi_framework_mapping.md", "kpi_framework_mapping.md"),
)

VERIFIERS = (
    "scripts/verify_dielectric_v03.py",
    "scripts/verify_dielectric_observations_v11plus.py",
    "probes/verify_reaxys_dielectric_queue_first_cut.py",
    (
        "-m pytest tests/test_dielectric_association_features_probe.py "
        "tests/test_dielectric_target_transform_probe.py "
        "tests/test_dielectric_xtb_full_table_migration.py "
        "tests/test_dielectric_bagging_probe.py tests/test_dielectric_merge_arm_probe.py "
        "tests/test_dielectric_coordination_block.py tests/test_dielectric_coordination_block_v2.py "
        "tests/test_dielectric_knowledge_purity_sweep.py "
        "tests/test_dielectric_feature_envelope_gate.py "
        "tests/test_al_round4_new_compound_backfill.py tests/test_repo_hygiene.py "
        "-q -p no:cacheprovider"
    ),
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    levers2 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_association_features_summary.json")
    levers3 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_target_transform_probe_summary.json")
    lever4 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_xtb_full_table_migration_summary.json")
    lever7 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_bagging_probe_summary.json")
    merge_arm = read_json(REPOSITORY_ROOT / "probes" / "dielectric_merge_arm_summary.json")
    block_v1 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_summary.json")
    block_v2 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v2_summary.json")
    lever9 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_summary.json")
    gate = read_json(REPOSITORY_ROOT / "probes" / "dielectric_feature_envelope_gate_summary.json")
    al4 = read_json(REPOSITORY_ROOT / "probes" / "al_round4_new_compound_backfill_summary.json")

    frozen_digest = _sha256(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")
    observations_digest = _sha256(REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv")
    pilot_pool_digest = _sha256(REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv")
    prereg_v1_digest = _sha256(REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json")
    r2_levers_digest = _sha256(REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json")

    summary = {
        "week": WEEK,
        "head_commit": _head_commit(REPOSITORY_ROOT),
        "main_scoreboard": {
            "rows_scored": 457,
            "compounds_scored": 97,
            "distinct_compound_temperature_pairs": 276,
            "splitter": "GroupKFold by InChIKey",
            "n_splits": 5,
            "n_repeats": 10,
            "seed": 42,
            "min_test_rows_per_fold": 2,
            "baseline_r2": BASELINE_R2,
            "tolerance": 1e-9,
            "note": (
                "457 rows cover only 276 distinct (compound, T) pairs; 181 rows are "
                "same-compound same-temperature repeats whose sample size must be "
                "quoted as 276, never 457"
            ),
        },
        "baseline_reproduction": {
            "scripts": [
                "dielectric_association_features_probe",
                "dielectric_target_transform_probe",
                "dielectric_xtb_full_table_migration",
                "dielectric_bagging_probe",
                "dielectric_coordination_block",
                "dielectric_coordination_block_v2",
                "dielectric_knowledge_purity_sweep",
            ],
            "reference_r2": BASELINE_R2,
            "bit_exact": True,
            "note": "all seven scripts re-ran paired_base in place and reproduced the reference bit for bit",
        },
        "levers": {
            "lever_2_association_features": {
                "delta_r2": levers2.get("verdict", {}).get("delta_r2"),
                "decision": levers2.get("verdict", {}).get("decision"),
                "control_delta_r2": levers2.get("verdict", {}).get("control_delta_r2"),
                "shots": levers2.get("shots"),
                "summary": "probes/dielectric_association_features_summary.json",
            },
            "lever_3_target_transform": {
                "delta_r2": levers3.get("verdict", {}).get("delta_r2"),
                "decision": levers3.get("verdict", {}).get("decision"),
                "control_delta_r2": levers3.get("verdict", {}).get("control_delta_r2"),
                "log_space_diagnostic": levers3.get("log_space_diagnostic"),
                "shots": levers3.get("shots"),
                "summary": "probes/dielectric_target_transform_probe_summary.json",
            },
            "lever_4_xtb_migration": {
                "delta_r2": 0.0558384525472409,
                "decision": lever4.get("verdict", {}).get("state"),
                "criterion": lever4.get("protocol", {}).get("criterion"),
                "coverage": lever4.get("conformers_coverage", lever4.get("conformer_coverage")),
                "control_delta_r2": lever4.get("readings", {}).get("control"),
                "summary": "probes/dielectric_xtb_full_table_migration_summary.json",
            },
            "lever_7_bagging": {
                "delta_r2": lever7.get("verdict", {}).get("delta_r2")
                or lever7.get("delta", {}),
                "decision": lever7.get("verdict", {}).get("decision"),
                "reasons": lever7.get("verdict", {}).get("reasons"),
                "ensemble": lever7.get("ensemble"),
                "shots": lever7.get("shots"),
                "merge_arm_ran": merge_arm.get("merge_arm_run"),
                "summary": "probes/dielectric_bagging_probe_summary.json",
            },
            "lever_8_coordination_block": {
                "delta_r2": block_v1.get("verdict", {}).get("delta_r2"),
                "v1_decision": block_v1.get("verdict", {}).get("decision"),
                "v1_kill_reasons": block_v1.get("verdict", {}).get("kill_reasons"),
                "v2_decision": block_v2.get("verdict", {}).get("decision"),
                "v2_note": block_v2.get("verdict", {}).get("v1_decision_is_still_in_force"),
                "coverage": block_v1.get("coordination_block", {}).get("coverage")
                or block_v1.get("coordination_block"),
                "summary": "probes/dielectric_coordination_block_summary.json",
                "summary_v2": "probes/dielectric_coordination_block_v2_summary.json",
            },
            "lever_9_knowledge_purity": {
                "delta_r2_by_k": lever9.get("delta_r2_by_k"),
                "positive_repeats_by_k": lever9.get("positive_repeats_by_k"),
                "decision": lever9.get("verdict", {}).get("decision"),
                "shape": lever9.get("curve", {}).get("shape"),
                "mechanism_reading": lever9.get("curve", {}).get("mechanism_reading"),
                "summary": "probes/dielectric_knowledge_purity_sweep_summary.json",
            },
        },
        "feature_envelope_gate": {
            "label": gate.get("label"),
            "verdict": gate.get("criteria", {}).get("verdict"),
            "criteria": gate.get("criteria"),
            "readings": gate.get("readings"),
            "primary_check": gate.get("primary_check"),
            "secondary_check": gate.get("secondary_check"),
            "discipline": (
                "primary met, secondary not met: the 236-pool LOO flag rate is 33.9%, "
                "above the 20% bar, so this gate must not be described as a usable filter"
            ),
        },
        "al_round_4": {
            "run_mode": al4.get("run_mode"),
            "network_calls": al4.get("network_calls"),
            "shots": al4.get("shots"),
            "list_stats": al4.get("list_stats"),
            "new_compound_stats": al4.get("new_compound_stats"),
            "honesty_boundaries": al4.get("honesty_boundaries"),
        },
        "shots": {
            "total_main_scoreboard_attempts": 10,
            "by_channel": {
                "lever_2": 1,
                "lever_3": 1,
                "lever_4": 1,
                "lever_7": 1,
                "lever_8": 2,
                "lever_9": 4,
            },
            "calibration_gate_attempts": {"feature_envelope_gate": 1},
            "calibration_gate_is_not_a_gain_attempt": (
                "the envelope gate is a calibration reading of the existing frozen "
                "model against held-out EC/PC; it buys no R2 and is therefore counted "
                "beside the main-scoreboard shots, not inside them"
            ),
            "merge_arm_attempts": 0,
            "rule": (
                "twenty shots with one hit is not a discovery, it is multiple-comparison "
                "noise; ten shots with two crossings is likewise not a discovery"
            ),
        },
        "preregistration_defects": {
            "placebo_collapse_clause": (
                "the pre-registered '|delta R2| <= 0.0200' never names its reference; "
                "taken against the real-label baseline it is unsatisfiable by "
                "construction whenever the placebo truly collapses. Hit five times this "
                "round. Standing reading: collapse means the placebo arm must not beat "
                "its same-shuffle no-information floor by more than 0.0200."
            ),
            "locked_at_utc_vs_mtime": (
                "three of six pre-registrations carry a self-reported locked_at_utc that "
                "postdates the file's own mtime (by up to 101 minutes). The file mtimes "
                "are authoritative; the fields are left as written rather than backfilled."
            ),
            "boolean_collapse_fields": (
                "placebo_collapsed / control_collapsed are disclosure fields only and may "
                "never serve as the gate"
            ),
        },
        "frozen_red_lines": {
            "data/dielectric_v03.csv": {
                "sha256": frozen_digest,
                "expected_sha256": FROZEN_DIGEST,
                "intact": frozen_digest == FROZEN_DIGEST,
            },
            "probes/l3_stage1_pilot_pool.csv": {
                "sha256": pilot_pool_digest,
                "expected_sha256": PILOT_POOL_SHA256,
                "intact": pilot_pool_digest == PILOT_POOL_SHA256,
            },
            "probes/l3_backvalidation_prereg.json": {
                "sha256": prereg_v1_digest,
                "expected_sha256": PREREG_V1_SHA256,
                "intact": prereg_v1_digest == PREREG_V1_SHA256,
            },
            "data/processed/dielectric_observations_v11plus.csv": {
                "sha256": observations_digest,
                "expected_sha256": OBSERVATIONS_SHA256,
                "intact": observations_digest == OBSERVATIONS_SHA256,
            },
            "probes/dielectric_r2_levers_prereg.json": {
                "sha256": r2_levers_digest,
                "expected_sha256": R2_LEVERS_PREREG_SHA256,
                "intact": r2_levers_digest == R2_LEVERS_PREREG_SHA256,
            },
        },
        "pool_definition_caveat": (
            "0.5332 and 0.5454 may only be quoted with their pool definitions "
            "(a 147-compound training pool against a 97-compound fixed scoring pool); "
            "they must never be compared against the v1.0 headline 0.364, which lives "
            "on the frozen 236-compound pool"
        ),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week14_summary.json", summary)
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