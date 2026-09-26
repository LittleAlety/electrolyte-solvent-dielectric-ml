"""Export the Week 15 deliverables (the data-layer arm plus the hybrid-SHAP read).

Covers, in one package:

* T1 -- the full re-parse of every local ThermoML XML document for viscosity
  rows that the stored extractions never harvested;
* T2 -- the stored viscosity table versus Schrodinger et al. (2024) supplement 2,
  compared both row-aligned and as a row-order-independent multiset;
* T3 -- the PubChem identity layer L0 covering every key of the coverage set;
* T4 -- the 64-column KPI descriptor module replica and its fidelity ledger;
* T5 -- exact TreeSHAP importance rankings computed inside every training fold
  of the frozen epsilon hybrid (2061 columns, 50 folds);
* the AL Round 4 recompute that the two new data files forced;
* the reporting-accuracy guards the Week 15 adversarial review added.

Week 15 buys no new R2.  The single time the frozen main scoreboard is touched
is T5's reproduction check, which re-derives `paired_base` = 0.4091179943351143
bit for bit on the same 50 folds before a single ranking is described.  The
package therefore ships the readouts plus the tables that let each readout be
recomputed from the artefacts rather than restated from memory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
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

WEEK = "week15"

FROZEN_DIGEST = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
PILOT_POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
PREREG_V1_SHA256 = "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
OBSERVATIONS_SHA256 = "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
R2_LEVERS_PREREG_SHA256 = "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa"
VISCOSITY_V01_SHA256 = "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"
BASELINE_R2 = 0.4091179943351143

# The lever-9 column-order defect (decisions_log.md 24.6 / 24.9) was described
# in Week 15 with the wrong label attached to one number.  The Week 16 erratum
# round re-ran the whole k grid three ways and settled it; the sentence below is
# shared verbatim by the README and the machine summary so the two can never
# drift, and the Week 15 sections themselves are left as written (the project
# rule is that a landed reading is never quietly rewritten).
ORDER_LABEL_ERRATUM_NOTE = (
    "24.6 / 24.9 把 +0.008666009048 标成「修正（正确）列序」下的 k=10 读数，"
    "这个**标签是错的**：+0.008666009048 是**预注册池序**读数（12 位逐位吻合，"
    "k10_exact_difference <= 1e-12），修正重要度列序下的 k=10 读数是 +0.015746812。"
    "三序并列：v1 破损列序 +0.014709978 / 预注册池序 +0.008666009 / 修正重要度序 "
    "+0.015746812（spread 0.007080803），**三序全部低于 +0.0200 判据带**，"
    "判决仍为 sub_threshold。该更正不改变任何判决，只更正标签。"
)

README_TEXT = f"""# Week 15 交付包（数据层四件 + ε hybrid 的逐折 SHAP 排序）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（digest
ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4）；v1.0 已发布工件与
week11–week14 交付包未被触碰；本轮全部产物为新增文件。
生成脚本: probes/export_week15_results.py

## 头条（六句话，都不许外推）

1. **本轮不产新 R²**。W15 是数据层 + 归因层：五条通道里没有一条拿冻结主记分牌去换分数。
   唯一一次触碰主记分牌的读数是 T5 的**复现校验**——它在同一 50 折上逐位复现
   `paired_base` = **0.4091179943351143**（|Δ| = 0.0，容差 1e-9），买到 **0 分** R²。
2. **T1（本地 ThermoML 黏度重解析）：前提成立，规模必须下修**。242 个本地 XML 里躺着
   **2,725 行黏度观测**（分布在 29 个文件；`Viscosity, Pa*s` 2,549 + 运动黏度 176），
   而本项目从**同一语料**建的三张抽取表里黏度行数**全为 0**、连黏度列都不存在——「未收割」由假设
   升格为机读事实。但**纯组分只有 569 行 / 47 个 InChIKey**，相对 ε 观测表(153 键) ∪ 存量黏度表
   (957 键) **净新增仅 3 个键**。**这是补给线，不是新矿脉**；ηε-joint 骨架规模由 ε∩η 决定，
   不由本地黏度本体的行数决定。
3. **T2（存量 vs Schrödinger SI）：假设落锤**。`data/viscosity_v01.csv`（3,582 行）与
   `chew_2024_viscosity_supp_2.csv` **逐行对齐 3,582/3,582、mismatches = 0**
   （T_K / viscosity_cP 容差 1e-9），独立的多重集比对 `multiset_matches = True`，
   `source_doi` 唯一 = `10.1186/s13321-024-00820-5`。「存量表 = 论文开放子集」
   由「待核实假设」降级为**已证实的既定条件**。**受限的 858 条（4,440 − 3,582）不得以任何方式绕版权
   获取、不得推测内容、不得计入本地语料规模**；supp_3 的 650 行是模型预测（`data_status=predicted`），
   实测扫两张实验表得 `rows_merged_into_experimental_table = 0`。
4. **T3（PubChem 身份层 L0）**：覆盖集 **314**（名册 246 ∪ lowfreq 50 ∪ ilthermo 47），
   **314/314 解析出 CID**、名册 **246/246**、InChIKey 回环 **314/314 roundtrip_match**、缺口 0。
   提交态 `network_calls = 0`（缓存全命中）；可复算的填充痕迹 = 628 个缓存文件
   （314 `.json` + 314 `.url`）、mtime 窗口 **352.7 s**、限流常量 **0.25** s/请求。
   顺带查出 **1 条 cid_conflict**、**15 条同一 InChIKey 下的画法差异**（stereo_only 10 / structural 5）。
5. **T4（KPI 64 维模块）**：64 列**同名同序**；保真度四档 = 逐字复刻 3 / RDKit 原生 15 /
   本仓自写 42 / 未确证 4；名册 246 条 SMILES 全表 64×246 = 15,744 格，**非有限值 0 格**。
   **不是 byte 级复刻**：SI 没印元素值表、没给 SMARTS、没说电荷模型 → 8 条差异逐条披露
   （Fe 三表皆无取 0.0、水按 RDKit 定义 `#Donor = 0`、2 条六氟磷酸盐各 7 个原子走显式 0.0 兜底）。
6. **T5（ε hybrid 逐折 SHAP）**：**2,061 列**（2,048 Morgan 位 + 13 物理列）在冻结 50 折上做**精确
   TreeSHAP**，泄漏守卫 `test_rows_visible_to_ranking = 0`（150 折次全过），加性校验
   max 相对残差 **4.73e-06**（单精度累加，不是 float64 机器 epsilon）。**与 AB-6 引用的杠杆 9 置换表
   逐折 top-3 一致率 2/50 = 0.040 → `inconsistent`**；与修正后的置换读数为 27/50 = 0.540 →
   `partially_consistent`。三强里 `donor_acceptor_pair_density` **复现**、
   `heteroatom_over_carbon` **削弱**、`ring_count` **丢失（0/50）**；
   「线性计数垫底」按字面规则**不成立**。

## 入口

- week15_summary.json - 机器可读摘要（五通道读数 + 红线复核 + 开放勘误 + AL4 重算）
- verification.json - verifier 退出码与报告
- decisions_log.md - 含 §24（Week 15 三臂落盘、审查收口轮 §24.9）
- T1：thermoml_viscosity_coverage_probe.py / thermoml_viscosity_coverage_summary.json /
  reports/thermoml_viscosity_coverage.md / test_thermoml_viscosity_coverage_probe.py /
  data/processed/viscosity_observations_thermoml.csv
- T2：schrodinger_si_reconciliation.py / schrodinger_si_reconciliation_summary.json /
  reports/schrodinger_si_reconciliation.md / test_schrodinger_si_reconciliation.py /
  data/viscosity_v01.csv
- T3：pubchem_identity_layer.py / pubchem_identity_layer_summary.json /
  test_pubchem_identity_layer.py / data/reference/identity_map.csv
- T4：src/electrolyte_ml/kpi_descriptors.py / test_kpi_descriptors.py / reports/kpi_64_feature_module.md
- T5：dielectric_hybrid_shap.py / dielectric_hybrid_shap_summary.json /
  artifacts/dielectric_hybrid_shap_importance.csv（10.0 MB）/ artifacts/dielectric_hybrid_shap_rank_stability.csv /
  reports/dielectric_hybrid_shap.md / test_dielectric_hybrid_shap.py
- 报送口径守卫：test_week15_reporting_accuracy.py（断言 §24 与附录 AC 不再出现被证伪的句子）
- 附录对账快照：manual_appendix_j_snapshot.md
- AL Round 4 重算：al_round4_backfill_list_v0.csv / al_round4_new_compound_backfill_summary.json
  （**导出时按生成器重算**：清单的 `local_trace_files` 是**磁盘状态的函数**，本包落盘那天又有两个
  `data/processed/eta_epsilon_joint_*.csv` 到位，故此处计数是「导出当时的盘面读数」，
  不是「Week 15 提交所对应的数字」。扫描语义问题原样登记、**未擅自改**。）

## 三条纪律增补（=手册附录 AC 口径）

1. **「未收割」与「新矿脉」是两件事**。T1 证明了字段确实在原始 XML 里没被收割，但纯组分只有
   47 个键、净新增 3 个键。**不许把「有 2,725 行」讲成「多出 2,725 行新化合物」**。
2. **受限数据只能登记、不能获取**。Schrödinger 的 858 条受限点与 supp_3 的 650 行预测，只许作为
   **边界陈述**出现；supp_3 的 `data_status=predicted` 由测试钉死，禁止并入实验表、禁止进入拟合或评估。
3. **重要度不是因果，且实现之间不可互推**。SHAP（平均 |贡献|）与置换重要度（训练 MSE 下降量）对行的
   加权方式不同，二者不一致**只说明这两个实现不同**，不说明哪个错；**不声称任何特征是物理机制**。

## 本轮之后登记的开放勘误（Week 16 勘误轮，照实登记不静默修）

- {ORDER_LABEL_ERRATUM_NOTE}

## 必须照写的边界

- **0.5332 / 0.5454 只许带池定义引用**（147 化合物训练池 / 97 化合物固定评分池），**不得**与 v1.0
  headline 0.364 直接比大小。本轮全部 R² 均为「457 行 / 97 化合物固定评分池」口径。
- **457 行不是有效样本量**：实测只覆盖 **276 个不同的 (化合物, T) 对**。
- **T1：本地 XML 是 NIST 全库（11,923 条记录）的筛选子集**，「29 个文件含黏度」**不构成 NIST 黏度总体上界**；
  要下总体结论必须另做在线黏度切片核查（**本轮未做**）。多组分 2,156 行**未做**溶质/溶剂角色拆分。
- **T1：运动黏度 176 行没有密度就无法换算成 Pa·s**，原样留在 kinematic 列、不参与任何 ε+η 配对。
- **T2：逐行同一性只证明「存量表 = 开放子集」**，**不能**证明开放子集本身没有抄录错误；本地没有
  Schrödinger 官方的校验和可对。**4,440 是论文声称值，本地不可复算。**
- **T3：请求级计数在仓库内不可复现**——`_harvest_runs.jsonl` 现存各行**全是收割之后**的缓存命中运行，
  收割那一次没有落运行记录行。可复算的只有缓存文件数、mtime 窗口与限流常量。
- **T4：元素性质值表是本仓另择**（Pauling / NIST ASD），论文若用别的数据源，AvgX/AvgI/AvgA 会系统性偏移。
- **T5：名次不能跨臂比较**（hybrid 臂 2,061 列 vs 知识臂 10 列）；**任何树都没分裂过的列**贡献恰为 0，
  它的名次是并列位次里由固定列序决定的位置，**不是测量值**（2,061 列里 **1,880 列**从未被任何树使用）。
- **AL Round 4 的 `local_trace_files` 是磁盘状态的函数**，不是版本库内容的函数：它会把未入库的下载缓存
  当作「项目知识痕迹」。本轮按生成器重算（114 → 128）；导出当天又有两张 ηε 联表（`data/processed/eta_epsilon_joint_*.csv`）落地，故按生成器二次重算为 **146**，机器字段以导出的 summary 为准。扫描语义问题登记为待办、**不擅自改**。
- **random_row 只作泄漏参照**（R² = 0.7385332681453336），**从不进入任何判决**。
"""

ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    # A. T1 -- ThermoML viscosity re-parse.
    ("probes/thermoml_viscosity_coverage_probe.py", "thermoml_viscosity_coverage_probe.py"),
    ("probes/thermoml_viscosity_coverage_summary.json", "thermoml_viscosity_coverage_summary.json"),
    ("reports/thermoml_viscosity_coverage.md", "thermoml_viscosity_coverage.md"),
    ("tests/test_thermoml_viscosity_coverage_probe.py", "test_thermoml_viscosity_coverage_probe.py"),
    (
        "data/processed/viscosity_observations_thermoml.csv",
        "data/processed/viscosity_observations_thermoml.csv",
    ),
    # B. T2 -- stored table versus the Schrodinger supplement.
    ("probes/schrodinger_si_reconciliation.py", "schrodinger_si_reconciliation.py"),
    ("probes/schrodinger_si_reconciliation_summary.json", "schrodinger_si_reconciliation_summary.json"),
    ("reports/schrodinger_si_reconciliation.md", "schrodinger_si_reconciliation.md"),
    ("tests/test_schrodinger_si_reconciliation.py", "test_schrodinger_si_reconciliation.py"),
    ("data/viscosity_v01.csv", "data/viscosity_v01.csv"),
    # C. T3 -- PubChem identity layer L0.
    ("probes/pubchem_identity_layer.py", "pubchem_identity_layer.py"),
    ("probes/pubchem_identity_layer_summary.json", "pubchem_identity_layer_summary.json"),
    ("tests/test_pubchem_identity_layer.py", "test_pubchem_identity_layer.py"),
    ("data/reference/identity_map.csv", "data/reference/identity_map.csv"),
    # D. T4 -- KPI 64-descriptor module replica.
    ("src/electrolyte_ml/kpi_descriptors.py", "kpi_descriptors.py"),
    ("tests/test_kpi_descriptors.py", "test_kpi_descriptors.py"),
    ("reports/kpi_64_feature_module.md", "kpi_64_feature_module.md"),
    # E. T5 -- per-fold TreeSHAP on the frozen epsilon hybrid.
    ("probes/dielectric_hybrid_shap.py", "dielectric_hybrid_shap.py"),
    ("probes/dielectric_hybrid_shap_summary.json", "dielectric_hybrid_shap_summary.json"),
    (
        "probes/artifacts/dielectric_hybrid_shap_importance.csv",
        "artifacts/dielectric_hybrid_shap_importance.csv",
    ),
    (
        "probes/artifacts/dielectric_hybrid_shap_rank_stability.csv",
        "artifacts/dielectric_hybrid_shap_rank_stability.csv",
    ),
    ("reports/dielectric_hybrid_shap.md", "dielectric_hybrid_shap.md"),
    ("tests/test_dielectric_hybrid_shap.py", "test_dielectric_hybrid_shap.py"),
    # F. Reporting guards and the appendix excerpt the guards run against.
    ("tests/test_week15_reporting_accuracy.py", "test_week15_reporting_accuracy.py"),
    ("tests/fixtures/manual_appendix_j_snapshot.md", "manual_appendix_j_snapshot.md"),
    # G. AL Round 4 recompute, forced by the two new data files.
    ("probes/al_round4_backfill_list_v0.csv", "al_round4_backfill_list_v0.csv"),
    (
        "probes/al_round4_new_compound_backfill_summary.json",
        "al_round4_new_compound_backfill_summary.json",
    ),
)

VERIFIERS = (
    "scripts/verify_dielectric_v03.py",
    "scripts/verify_dielectric_observations_v11plus.py",
    "probes/verify_reaxys_dielectric_queue_first_cut.py",
    (
        "-m pytest tests/test_thermoml_viscosity_coverage_probe.py "
        "tests/test_schrodinger_si_reconciliation.py tests/test_pubchem_identity_layer.py "
        "tests/test_kpi_descriptors.py tests/test_dielectric_hybrid_shap.py "
        "tests/test_week15_reporting_accuracy.py tests/test_al_round4_new_compound_backfill.py "
        "tests/test_repo_hygiene.py tests/test_manual_appendix_reconciliation.py "
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


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    """Say whether the worktree was dirty at export time, and by how many paths."""

    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    paths = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(paths), len(paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def kpi_fidelity_counts(report_path: Path) -> dict[str, int]:
    """Read the KPI fidelity ledger off the shipped report's summary table.

    The module exposes column names and blocks but not the fidelity tier of each
    column, so the ledger lives in the report.  Parsing it here means the summary
    cannot advertise counts the report no longer states, and a re-tiered column
    fails the export instead of silently disagreeing with the prose.
    """

    labels = {
        "逐字复刻": "verbatim",
        "RDKit 原生": "rdkit_native",
        "本仓自写": "in_repo",
        "未确证": "unconfirmed",
    }
    counts: dict[str, int] = {}
    in_section = False
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 3 "):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        for label, key in labels.items():
            if cells[0].startswith(label):
                counts[key] = int(cells[1])
    missing = sorted(key for key in labels.values() if key not in counts)
    if missing:
        raise SystemExit(
            "the KPI fidelity summary table no longer yields " + repr(missing)
        )
    if sum(counts.values()) != 64:
        raise SystemExit(
            "the KPI fidelity tiers add up to "
            + str(sum(counts.values()))
            + " rather than the 64 columns the module declares"
        )
    return counts


def kpi_block_sizes() -> dict[str, int]:
    from electrolyte_ml.kpi_descriptors import KPI_BLOCKS

    return {name: len(columns) for name, columns in KPI_BLOCKS.items()}


def measure_kpi_roster(source_root: Path) -> dict[str, int]:
    """Recompute the roster descriptor table so the NaN claim is measured."""

    from electrolyte_ml.kpi_descriptors import compute_kpi_table

    with (source_root / "data" / "dielectric_v03.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        smiles = [row["smiles"] for row in csv.DictReader(handle)]
    table = compute_kpi_table(smiles)
    non_finite = sum(
        1 for row in table for value in row.values() if not math.isfinite(value)
    )
    return {
        "roster_smiles": len(smiles),
        "descriptor_cells": len(table) * 64,
        "non_finite_cells": non_finite,
    }


def distinct_local_trace_files(list_path: Path) -> int:
    """Count the distinct files the AL Round 4 list cites as local traces.

    The generator records `path:tier` entries; the metric the handover quotes
    is distinct *files*, so the tier suffix is stripped before counting.
    """

    with list_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    paths = {
        entry.split(":")[0]
        for row in rows
        for entry in (row.get("local_trace_files") or "").split(";")
        if entry.strip()
    }
    return len(paths)


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    t1 = read_json(REPOSITORY_ROOT / "probes" / "thermoml_viscosity_coverage_summary.json")
    t2 = read_json(REPOSITORY_ROOT / "probes" / "schrodinger_si_reconciliation_summary.json")
    t3 = read_json(REPOSITORY_ROOT / "probes" / "pubchem_identity_layer_summary.json")
    t5 = read_json(REPOSITORY_ROOT / "probes" / "dielectric_hybrid_shap_summary.json")
    al4 = read_json(
        REPOSITORY_ROOT / "probes" / "al_round4_new_compound_backfill_summary.json"
    )

    fidelity = kpi_fidelity_counts(
        REPOSITORY_ROOT / "reports" / "kpi_64_feature_module.md"
    )
    roster = measure_kpi_roster(REPOSITORY_ROOT)
    trace_files = distinct_local_trace_files(
        REPOSITORY_ROOT / "probes" / "al_round4_backfill_list_v0.csv"
    )

    frozen_digest = _sha256(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")
    observations_digest = _sha256(
        REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
    )
    pilot_pool_digest = _sha256(REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv")
    prereg_v1_digest = _sha256(
        REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
    )
    r2_levers_digest = _sha256(
        REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
    )
    viscosity_v01_digest = _sha256(REPOSITORY_ROOT / "data" / "viscosity_v01.csv")

    artifacts_commit = _head_commit(REPOSITORY_ROOT)
    worktree_dirty, worktree_dirty_paths = _worktree_status(REPOSITORY_ROOT)

    baseline = t5.get("baseline_reproduces", {})
    leak = t5.get("leak_guard", {})
    additivity = t5.get("shap_additivity", {})
    stability = t5.get("rank_stability", {}).get("hybrid", {})
    ab6 = t5.get("comparison_to_ab6", {})
    ab6_readings = ab6.get("readings", {})
    hybrid_top = (t5.get("top10_features") or [{}])[0]
    knowledge_top = (t5.get("knowledge_top10") or [{}])[0]
    differing = Counter(
        entry.get("difference_kind") for entry in t3.get("smiles_differing_keys", [])
    )

    summary = {
        "week": WEEK,
        # The export-time HEAD.  Kept under its historical name; on its own it is
        # not a coordinate for the shipped files, see provenance_note.
        "head_commit": artifacts_commit,
        "artifacts_commit": artifacts_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": worktree_dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit to fetch the shipped artefacts from, but "
            "only when worktree_dirty is false; head_commit is kept under its "
            "historical name and carries the same value. When worktree_dirty is true, "
            "at least one shipped file was copied from an uncommitted working tree, "
            "so no commit on its own identifies the shipped bytes: seal the worktree "
            "into a commit, re-export from that commit and cite it before quoting any "
            "artefact coordinate."
        ),
        "buys_no_new_r2": (
            "Week 15 is a data-layer and attribution round: none of the five lanes "
            "spends the frozen main scoreboard on a candidate feature set. The single "
            "time the scoreboard is touched is T5's reproduction check, which re-derives "
            "paired_base bit for bit before any ranking is described, and buys no R2."
        ),
        "shots": {
            "main_scoreboard_attempts": 0,
            "calibration_reproductions": 1,
            "calibration_reproduction_is_not_a_gain_attempt": (
                "T5's 50-fold reproduction of paired_base is a check that the ranking "
                "describes the model the scoreboard scores; it buys no R2 and is "
                "therefore counted beside the main-scoreboard shots, not inside them"
            ),
            "rule": (
                "a round that buys no R2 has nothing to deflate; the discipline is "
                "that it also claims no R2"
            ),
        },
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
            "arm": "dielectric_hybrid_shap",
            "reference_r2": BASELINE_R2,
            "reproduced_r2": baseline.get("reproduced_r2"),
            "abs_difference": baseline.get("abs_difference"),
            "tolerance": 1e-9,
            "bit_exact": baseline.get("abs_difference") == 0.0,
            "folds_compared": t5.get(
                "fold_fit_matches_the_frozen_function", {}
            ).get("folds_compared"),
            "note": (
                "the hybrid that is ranked has to be the hybrid the main scoreboard "
                "scores; the readout is reproduced before a single ranking is described"
            ),
        },
        "lanes": {
            "t1_thermoml_viscosity_reparse": {
                "probe": "probes/thermoml_viscosity_coverage_probe.py",
                "xml_files_scanned": t1.get("xml_files_scanned"),
                "viscosity_files": t1.get("viscosity_files"),
                "viscosity_rows": t1.get("viscosity_rows"),
                "viscosity_rows_pa_s": t1.get("viscosity_rows_pa_s"),
                "viscosity_rows_kinematic": t1.get("viscosity_rows_kinematic"),
                "pure_rows": t1.get("pure_rows"),
                "mixture_rows": t1.get("mixture_rows"),
                "pure_keys": t1.get("pure_keys"),
                "new_keys_vs_epsilon_and_stored_viscosity": t1.get("new_vs_eps_and_v01"),
                "stored_thermoml_extraction_viscosity_rows": t1.get(
                    "extraction_gap", {}
                ).get("viscosity_rows_in_stored_thermoml_extractions"),
                "distinct_source_dois": t1.get("source_doi", {}).get("distinct_dois"),
                "rows_without_doi": t1.get("source_doi", {}).get("rows_without_doi"),
                "acceptance_values_reconciled": len(
                    t1.get("expectation_vs_remeasured", [])
                ),
                "expectation_mismatches": t1.get("expectation_mismatches"),
                "boundary": (
                    "the local XML corpus is a filtered subset of NIST's 11,923 records, so "
                    "29 files carrying viscosity is not an upper bound on NIST viscosity and "
                    "no population claim may be made from it; the 2,156 multi-component rows "
                    "are not split into solute and solvent roles, and the inchikey column of a "
                    "multi-component row is only its first component"
                ),
            },
            "t2_schrodinger_si_reconciliation": {
                "probe": "probes/schrodinger_si_reconciliation.py",
                "stored_rows": t2.get("stored_table", {}).get("rows"),
                "row_aligned_matches": t2.get("row_aligned_matches"),
                "mismatches": t2.get("mismatches"),
                "multiset_matches": t2.get("row_multiset_comparison", {}).get(
                    "multiset_matches"
                ),
                "unique_keys": t2.get("unique_keys"),
                "source_doi": (t2.get("source_doi_set") or [None])[0],
                "claimed_total_points": t2.get("open_subset", {}).get(
                    "claimed_total_points"
                ),
                "withheld_points": t2.get("open_subset", {}).get("withheld_points"),
                "supp_3_rows": t2.get("supp_3", {}).get("rows"),
                "supp_3_rows_merged_into_experimental_table": t2.get("supp_3", {}).get(
                    "rows_merged_into_experimental_table"
                ),
                "boundary": (
                    "row-level identity proves the stored table equals the open subset; it "
                    "does not prove the open subset is free of transcription errors, and the "
                    "858 withheld points may not be obtained, guessed at or counted towards "
                    "the local corpus. 4,440 is the paper's claim and is not recomputable here."
                ),
            },
            "t3_pubchem_identity_layer": {
                "probe": "probes/pubchem_identity_layer.py",
                "coverage_set": t3.get("coverage_set"),
                "roster_keys": t3.get("roster_keys"),
                "roster_resolved_with_cid": t3.get("roster_resolved_with_cid"),
                "resolved_with_cid": t3.get("resolved_with_cid"),
                "unresolved": t3.get("unresolved_count"),
                "identity_check_counts": t3.get("identity_check_counts"),
                "network_calls_at_export": t3.get("network_calls"),
                "cache_hits": t3.get("cache_hits"),
                "cache_entries": t3.get("cache_entries_for_coverage_set"),
                "cid_conflicts": t3.get("cid_conflicts"),
                "smiles_differing_keys_by_kind": dict(sorted(differing.items())),
                "cost_accounting": (
                    "the committed run is a cache-hit run (network_calls 0), because the "
                    "harvest itself wrote no run record: every line of _harvest_runs.jsonl "
                    "postdates the cache window, so request counts are not reproducible from "
                    "anything committed. What is reproducible is the cache: 628 files, an "
                    "mtime window of 352.7 s, and the 0.25 s/request throttle constant."
                ),
                "boundary": (
                    "the 15 smiles_differing_keys entries are drawing differences under one "
                    "and the same identifier (identity_check is roundtrip_match for all 314 "
                    "and pubchem_inchikey equals the local inchikey verbatim); the machine "
                    "field name 'structural' is kept as written and must not be read as an "
                    "identity doubt"
                ),
            },
            "t4_kpi_64_feature_module": {
                "module": "src/electrolyte_ml/kpi_descriptors.py",
                "columns": 64,
                "block_sizes": kpi_block_sizes(),
                "fidelity_counts": fidelity,
                "roster": roster,
                "charge_fallback": (
                    "two hexafluorophosphate ionic liquids give non-finite Gasteiger charges "
                    "on exactly seven atoms each; the module substitutes an explicit 0.0 and "
                    "exposes charge_fallback_atoms, so the fallback cannot drift silently"
                ),
                "boundary": (
                    "this is not a byte-level replica: the SI prints no element value table, "
                    "no SMARTS and no charge model, so eight differences are disclosed "
                    "column by column. The value tables are this repository's choice (Pauling "
                    "electronegativity, NIST ASD energies), and Fe has no entry in any of the "
                    "three tables and contributes 0.0."
                ),
            },
            "t5_hybrid_shap": {
                "probe": "probes/dielectric_hybrid_shap.py",
                "feature_columns": t5.get("feature_count"),
                "knowledge_feature_columns": t5.get("knowledge_feature_count"),
                "folds": t5.get("repeats_x_folds"),
                "repeats": t5.get("repeats"),
                "importance_implementation": t5.get("importance_impl"),
                "leak_guard_folds_checked": leak.get("folds_checked"),
                "test_rows_visible_to_ranking": t5.get("test_rows_visible_to_ranking"),
                "additivity_verified": additivity.get("verified"),
                "max_relative_residual_hybrid_arm": additivity.get(
                    "max_relative_residual_hybrid_arm"
                ),
                "max_relative_residual_knowledge_arm": additivity.get(
                    "max_relative_residual_knowledge_arm"
                ),
                "additivity_tolerance": additivity.get("tolerance"),
                "clipped_test_predictions": t5.get("clipped_test_predictions"),
                "top_feature_hybrid": {
                    "feature": hybrid_top.get("feature"),
                    "mean_importance": hybrid_top.get("mean_importance"),
                    "mean_rank": hybrid_top.get("mean_rank"),
                    "top_3_folds": hybrid_top.get("top_3_folds"),
                },
                "top_feature_knowledge": {
                    "feature": knowledge_top.get("feature"),
                    "mean_importance": knowledge_top.get("mean_importance"),
                    "mean_rank": knowledge_top.get("mean_rank"),
                    "top_3_folds": knowledge_top.get("top_3_folds"),
                },
                "rank_stability": {
                    "stable_features": stability.get("stable_features"),
                    "unstable_features": stability.get("unstable_features"),
                    "features_never_used_by_any_tree": stability.get(
                        "features_never_used_by_any_tree"
                    ),
                    "rule": stability.get("rule"),
                },
                "comparison_to_ab6": {
                    "verdict": ab6.get("verdict"),
                    "verdict_rule": ab6.get("verdict_rule"),
                    "shap_vs_quoted_lever9": ab6_readings.get("shap_vs_quoted_lever9"),
                    "shap_vs_corrected_permutation": ab6_readings.get(
                        "shap_vs_corrected_permutation"
                    ),
                    "quoted_lever9_vs_corrected_permutation": ab6_readings.get(
                        "quoted_lever9_vs_corrected_permutation"
                    ),
                    "top_three_status": ab6.get("top_three_status"),
                    "counts_rank_last_holds": ab6.get("counts_rank_last", {}).get("holds"),
                },
                "boundaries": t5.get("honest_boundaries"),
            },
        },
        "open_corrections": {
            "lever_9_k10_column_order_label": ORDER_LABEL_ERRATUM_NOTE,
        },
        "al_round_4_recompute": {
            "list": "probes/al_round4_backfill_list_v0.csv",
            "summary": "probes/al_round4_new_compound_backfill_summary.json",
            "rows": al4.get("list_stats", {}).get("rows"),
            "by_row_kind": al4.get("list_stats", {}).get("by_row_kind"),
            "new_compound_rows": al4.get("list_stats", {}).get("new_compound_rows"),
            "distinct_local_trace_files": trace_files,
            "recomputed_at_export": True,
            "trace_files_counting_rule": (
                "distinct files cited across the list's local_trace_files entries, with the "
                "path:tier suffix stripped"
            ),
            "why_it_moved_again": (
                "the list shipped here was regenerated at export time because two further "
                "data files named the same day (data/processed/eta_epsilon_joint_*.csv) landed "
                "after the Week 15 commit; the count is therefore a reading of the disk as of "
                "this export, not a number that belongs to the Week 15 commit"
            ),
            "known_fragility": (
                "local_trace_files is a function of the disk, not of the version-control "
                "contents: it counts git-ignored download caches as project knowledge, so the "
                "list cannot be reproduced byte for byte in a fresh clone, and it drifts every "
                "time a new file lands under data/. The correct fix is to filter through "
                "git ls-files; the scan semantics are left as landed and the issue is "
                "registered as a to-do rather than changed here."
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
            "data/viscosity_v01.csv": {
                "sha256": viscosity_v01_digest,
                "expected_sha256": VISCOSITY_V01_SHA256,
                "intact": viscosity_v01_digest == VISCOSITY_V01_SHA256,
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

    write_json(week_root / "week15_summary.json", summary)
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
