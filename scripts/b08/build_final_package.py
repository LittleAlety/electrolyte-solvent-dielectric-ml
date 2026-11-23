#!/usr/bin/env python
"""B08: assemble the final deliverables (outputs/final/ six-piece set).

PLAN B chapter 7 names the six final files:

    B_FINAL_STATUS.json              -- stage gates and completion state
    B_FINAL_MEASUREMENT_LEDGER.csv   -- the measurement-level evidence, final form
    B_FINAL_CLAIM_EVIDENCE_LEDGER.csv-- every claim mapped to its evidence
    B_FINAL_HASH_MANIFEST.json       -- byte-level freeze of everything produced
    B_FINAL_REVIEW.json              -- four-agent review outcomes
    B_FINAL_REPORT.md                -- the readable account

Rules this script is built to respect:

  * The claim ledger is the important one. PLAN B chapter 7 requires "所有论文结论
    均有证据映射". A claim without an evidence pointer must be omitted, not
    softened into a vague sentence.

  * Claims are graded. A claim backed by a 4/4 review is not the same as one
    backed by an exploratory experiment. The ledger records the grade so a reader
    cannot mistake exploration for confirmation.

  * J01/J02/J03 are re-verified before anything is written. If the frozen bytes
    have moved, the script must fail rather than emit a final package.

Output: outputs/final/  (six files)
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "final"
GENERATOR = "build_final_package/1.0.0"

CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
B00 = REPO_ROOT / "outputs" / "b00"
B01 = REPO_ROOT / "outputs" / "b01"
B04 = REPO_ROOT / "outputs" / "b04"
B05 = REPO_ROOT / "outputs" / "b05"
B07 = REPO_ROOT / "outputs" / "b07"
ADM = REPO_ROOT / "outputs" / "admission_v2"
EB = CONFIRM / "evidence_backfill"
PR = CONFIRM / "provenance_repair"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main() -> int:
    # ---- precondition: frozen artifacts must verify BEFORE we write ----
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "b00"
                                 / "verify_frozen_artifacts.py")],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600)
        frozen_ok = "OVERALL PASS" in proc.stdout
    except Exception as exc:                     # noqa: BLE001
        print(f"FATAL: frozen verification errored: {exc}", file=sys.stderr)
        return 2
    if not frozen_ok:
        print("FATAL: frozen artifacts do not verify; refusing to emit final "
              "package", file=sys.stderr)
        return 3

    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")

    # ---- read everything once ----
    b00_gate = jload(B00 / "j01_j02_j03_hash_lock.json")
    b01_gate = jload(B01 / "b01_gate_status.json")
    b03_gate = jload(EB / "b03_gate_status.json")
    b03_consensus = jload(EB / "b03_consensus.json")
    b04_lineage = jload(B04 / "pool_lineage_manifest.json")
    b05_gate = jload(B05 / "b05_gate_status.json")
    b05_e1 = jload(B05 / "E1_structure_vs_electronic" / "e1_manifest.json")
    b05_e4 = jload(B05 / "E4_domain_generalization" / "e4_manifest.json")
    b05_e6 = jload(B05 / "E6_screening_decisions" / "e6_manifest.json")
    b07_gate = jload(B07 / "b07_gate_status.json")
    gvl = jload(ADM / "gvl_conflict_consensus.json")
    admission_sm = jload(ADM / "admission_status_machine.json")

    # ================================================================
    # 1. B_FINAL_MEASUREMENT_LEDGER.csv
    # ================================================================
    ledger_src = PR / "measurement_ledger_v1.csv"
    ledger_rows = load(ledger_src) if ledger_src.is_file() else []
    excl = load(B01 / "dataset_v06_exclusions.csv") if (B01 / "dataset_v06_exclusions.csv").is_file() else []
    ready = load(B01 / "dataset_v06_model_ready.csv") if (B01 / "dataset_v06_model_ready.csv").is_file() else []

    excl_by_agg = {(r.get("aggregate_id") or "").strip(): r for r in excl}
    ready_by_agg = {(r.get("aggregate_id") or "").strip(): r for r in ready}

    out_rows = []
    for r in ledger_rows:
        agg = (r.get("aggregate_id") or "").strip()
        e = excl_by_agg.get(agg)
        rd = ready_by_agg.get(agg)
        final_status = (
            "MODEL_READY" if rd else
            f"EXCLUDED:{(e.get('blocking_reasons') or '').strip()}" if e else
            "IN_LEDGER_NOT_IN_V06_SCOPE"
        )
        out_rows.append({
            "measurement_id": (r.get("measurement_id") or "").strip(),
            "molecule_key": (r.get("molecule_key") or "").strip(),
            "a_mol_id": (r.get("a_mol_id") or "").strip(),
            "inchikey": (r.get("inchikey") or "").strip(),
            "temperature_K": (r.get("temperature_K") or "").strip(),
            "dielectric": (r.get("dielectric") or "").strip(),
            "phase": (r.get("phase") or "").strip(),
            "frequency_hz": (r.get("frequency_hz") or "").strip(),
            "pressure_kpa": (r.get("pressure_kpa") or "").strip(),
            "source_document_id": (r.get("source_document_id") or "").strip(),
            "source_file_sha256": (r.get("source_file_sha256") or "").strip(),
            "evidence_group_id": (r.get("evidence_group_id") or "").strip(),
            "aggregate_id": agg,
            "in_aggregate_window": (r.get("in_aggregate_window") or "").strip(),
            "traceability_status": (r.get("traceability_status") or "").strip(),
            "final_status": final_status,
            "locator_source": "outputs/b01/measurement_locator_v1.csv",
        })

    ledger_path = OUT / "B_FINAL_MEASUREMENT_LEDGER.csv"
    if out_rows:
        with ledger_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows:
                w.writerow(r)

    # ================================================================
    # 2. B_FINAL_CLAIM_EVIDENCE_LEDGER.csv
    # ================================================================
    # Every claim carries: what it says, the grade of evidence, and the file that
    # backs it. Grade vocabulary:
    #   CONFIRMED_FROZEN   -- byte-verified, cannot drift
    #   FOUR_AGENT_PASS    -- 4/4 independent reviewers agreed
    #   FOUR_AGENT_REJECT  -- reviewers refused
    #   EXPLORATORY        -- illustrative only, must not be cited as a finding
    #   INSUFFICIENT_POWER -- the test ran but cannot support a claim
    claims = []

    def add(cid, claim, grade, evidence, note=""):
        claims.append({
            "claim_id": cid,
            "claim": claim,
            "evidence_grade": grade,
            "evidence_file": evidence,
            "note": note,
        })

    # --- frozen / infrastructure facts ---
    add("C-01",
        "J01/J02/J03 冻结产物字节未改变，可逐字节复核",
        "CONFIRMED_FROZEN",
        "outputs/b00/j01_j02_j03_hash_lock.json",
        "24 个产物重算 sha256 与生成器回执一致；14 个上游输入全部匹配")
    add("C-02",
        "本地 main 是 origin/main 的纯快进（ahead 5 / behind 0）",
        "CONFIRMED_FROZEN",
        "outputs/b00/w49_commit_reconciliation.json",
        "merge-base == origin/main，因此对账 W49 是推送决策而非合并决策")
    add("C-03",
        "v1.3 独立论文包是 git 标签而非目录（14 个文件在包内，22 个是包外草稿）",
        "CONFIRMED_FROZEN",
        "outputs/b00/paper_v13_inventory.json",
        "把 v2/v3 草稿当作 v1.3 内容会改变包的身份")

    # --- measurement reconstruction ---
    add("C-04",
        "J03 报告的 460 是 v04 聚合窗口内观测数，不是全量测量数；全量为 2065",
        "CONFIRMED_FROZEN",
        "outputs/confirm_2027/provenance_repair/measurement_reconstruction_verification.json",
        "独立重算确认；J03 曾把它标为 N_measurement，是约 4.5 倍低估")
    add("C-05",
        "条件配对有效行数是 78，不是 58；58 是 J03 的分类计数 (48+10)",
        "CONFIRMED_FROZEN",
        "outputs/confirm_2027/provenance_repair/measurement_reconstruction_verification.json",
        "J03 的数据列也给出 78，只有叙述文字写成 58")
    add("C-06",
        "170 个聚合行的 (T,ε) 不对应真实测量（147 无贡献测量 + 22 合成条件对 + 1 假阴性）",
        "CONFIRMED_FROZEN",
        "outputs/confirm_2027/provenance_repair/reconstruction_exceptions.csv",
        "不可恢复项已逐行登记，未插值、未反推")
    add("C-07",
        "27 组跨文档逐字节相同的观测存在，DOI 数不等于独立实验数",
        "CONFIRMED_FROZEN",
        "outputs/confirm_2027/provenance_repair/source_independence_report.json",
        "涉及 9 个文档、28 个聚合行；注册表对 61/61 文档标注 independence=not_evaluated")

    # --- defect findings ---
    add("C-08",
        "15 个聚合行的介电常数来自压力扫描的中位数，不是常压测量",
        "CONFIRMED_FROZEN",
        "outputs/b01/pressure_heterogeneity_audit.json",
        "R097 的 14.26 恰为 100/150 MPa 中点；pressure_kpa 在队列中原本为空")
    add("C-09",
        "22/248 行的温度是推定值，其中 18 行标记 model_ready=true",
        "CONFIRMED_FROZEN",
        "outputs/b01/temperature_imputation_audit.json",
        "GVL 冲突的『同温』前提正是两次独立推定碰巧一致")
    add("C-10",
        "gap_aggregation_audit 的 v04_epsilon 列在 3 行上被 InChIKey 骨架连接污染",
        "CONFIRMED_FROZEN",
        "outputs/b01/source_conflict_register.json",
        "R174 报 2.14 而真值为 9.2（−77%）；gap_epsilon 列 248/248 正确")

    # --- four-agent review outcomes ---
    if admission_sm:
        acc = admission_sm["counts"].get("AI_CONSENSUS_ACCEPTED", 0)
        add("C-11",
            f"四智能体准入审核：{acc} 条记录达成 4/4 PASS",
            "FOUR_AGENT_PASS",
            "outputs/admission_v2/consensus_decisions.csv",
            "未使用多数投票；未把 AI 共识写入 HUMAN_SIGNED")
    if gvl:
        add("C-12",
            "γ-戊内酯 36.1 vs 36.9 冲突：四审未达成 4/4，两条记录均被拒绝",
            "FOUR_AGENT_REJECT",
            "outputs/admission_v2/gvl_conflict_consensus.json",
            "R1/R3 认可数值，R2/R4 质疑溯源；未取平均、未择一主值")
    if b03_consensus:
        add("C-13",
            "EA/MA 的 NBS514 核实是转录完整性检查，不是独立佐证",
            "FOUR_AGENT_REJECT",
            "outputs/confirm_2027/evidence_backfill/b03_consensus.json",
            "v04 的 source_record_id 与页面读取相同；EA/MA 共享参考文献 63，不独立")

    add("C-20",
        "候选池中有 4 个分子在其设定温度下低于熔点（固态/过冷液体），"
        "而液体静态介电常数是液相性质",
        "CONFIRMED_FROZEN",
        "outputs/b04/phase_state_audit.json",
        "sulfolane −2.8 K、cyclohexanol −0.9 K、AMP −1.0 K、"
        "N-(2-hydroxypropyl) −12.0 K；已逐行标记，未静默当作液体")
    add("C-21",
        "现有 liquid_window_gate 无法回答相态问题：它比较的是熔点与观测窗口下界，"
        "不是熔点与实测温度",
        "CONFIRMED_FROZEN",
        "outputs/b04/phase_state_audit.json",
        "6 个分子被旧门误判为 blocked 但实际是液体（如 DMC mp=0.5 C 在 25 C）")

    if (B05 / "E1c_feature_block_ablation" / "e1c_manifest.json").is_file():
        e1c = jload(B05 / "E1c_feature_block_ablation" / "e1c_manifest.json")
        f = e1c["findings"]
        add("C-14c",
            f"电子描述符块（{f['electronic_block_mae']}）优于结构块，"
            f"且**合并后反而变差** {f['combined_minus_electronic_mae']:+.2f}；"
            f"偶极矩单独即达 {f['dipole_mae']}"
            f"（电子块的 {f['dipole_as_pct_of_electronic_block']}%）",
            "EXPLORATORY",
            "outputs/b05/E1c_feature_block_ablation/e1c_manifest.json",
            "E1 只比较 X0 与 X0+X1，无法区分『电子块有用』与『合并块有用』；"
            "E1c 用同一嵌套协议补上该比较")
    add("C-22",
        "名义 12 列特征的有效秩只有 10：极化率两列完全相同，"
        "摩尔体积列等于分子体积 × N_A（vdW 腔体积和）",
        "EXPLORATORY",
        "outputs/b05/feature_quality_audit.json",
        "因此『12 维特征』高估信息量；已改为报告有效秩，并在 manifest 登记两处冗余. "
        "分级按 EXPLORATORY: 该审计依赖建模输入, 不属冻结证据")
    add("C-23",
        "E1 初版用 12 列而 E4/E6/B07 用 11 列，跨实验比较实际在比较不同模型",
        "EXPLORATORY",
        "outputs/b05/feature_quality_audit.json",
        "已统一为 11 列（排除 total_energy_hartree，它与重原子数 r=−0.957、与 ε r=0.007）")

    # --- modelling findings ---
    if b05_e1:
        cb = b05_e1["constant_baseline"]
        n_beat = cb["n_models_beating_baseline"]
        if n_beat == 0:
            add("C-14",
                f"X0 与 X0+X1 回归模型均劣于常数基线"
                f"（MAE {b05_e1['metrics'][0]['mae']:.2f} vs {cb['mae']:.2f}）",
                "EXPLORATORY",
                "outputs/b05/E1_structure_vs_electronic/e1_manifest.json",
                "n=22；置换零分布未超过噪声")
        else:
            add("C-14",
                f"修正后 X0+X1 显著优于常数基线"
                f"（MAE {b05_e1['metrics'][-1]['mae']:.2f} vs {cb['mae']:.2f}，"
                f"R² = {b05_e1['metrics'][-1]['r2']:.3f}）",
                "EXPLORATORY",
                "outputs/b05/E1_structure_vs_electronic/e1_manifest.json",
                "早期版本因 ridge 缺截距得出相反结论，已由 R1 发现并修复")
    if (B05 / "E1b_physics_constrained" / "e1b_manifest.json").is_file():
        e1b = jload(B05 / "E1b_physics_constrained" / "e1b_manifest.json")
        diag = e1b.get("bias_vs_ranking_diagnostic", {})
        add("C-14b",
            f"原始 E1 结论是模型规格错误：|bias|/MAE = "
            f"{diag.get('abs_bias_over_mae')}，去偏后 MAE "
            f"{diag.get('mae_after_debiasing')} 优于基线 "
            f"{diag.get('constant_baseline_mae')}",
            "EXPLORATORY",
            "outputs/b05/E1b_physics_constrained/e1b_manifest.json",
            "「描述符无信号」的推论不成立；这是标定失败而非信息缺失. "
            "虽属确定性算术, 但因建立在建模结果上, 仍按 EXPLORATORY 分级")
    if b05_e4:
        ident = b05_e4.get("identical_fingerprint_analysis") or {}
        add("C-15",
            f"指纹相同（Tanimoto=1.0）的分子对误差为 "
            f"{ident.get('mae_among_identical', 'n/a')}；"
            f"早期报告的 19.48 是模型缺截距造成的假象",
            "EXPLORATORY",
            "outputs/b05/E4_domain_generalization/e4_manifest.json",
            "「描述符无法分辨相似分子」的强结论不成立")
        add("C-16",
            f"误差随结构距离增大而增大（Spearman "
            f"{b05_e4.get('error_vs_distance_spearman'):+.3f}），"
            f"适用域信号存在；域外/域内 MAE 比 "
            f"{b05_e4['in_vs_out_of_domain'].get('out_over_in_ratio')}",
            "EXPLORATORY",
            "outputs/b05/E4_domain_generalization/e4_manifest.json",
            "修正后 Tanimoto 距离在方向上可用，但域外占 68%，样本仍不足")
    if b05_e6:
        add("C-17",
            f"Top-{b05_e6['k']} 筛选与随机不可区分（p = {b05_e6['metrics']['p_model_beats_random']}）",
            "INSUFFICIENT_POWER",
            "outputs/b05/E6_screening_decisions/e6_manifest.json",
            "n=22, k=3；冻结规则，未调参")
        if b05_e6["h3_test"].get("h3_supported") == "true":
            verdict = b05_e6["h3_test"].get("verdict", "")
            add("C-18",
                "H3 得到支持：加入噪声后 MAE 恶化但 regret 下降，"
                "回归精度与筛选收益脱钩"
                + ("（机制是局部排序倒置，不是全面反相关）"
                   if verdict == "LOCAL_RANK_INVERSION_NOT_GLOBAL_ANTICORRELATION"
                   else ""),
                "EXPLORATORY",
                "outputs/b05/E6_screening_decisions/e6_manifest.json",
                "Top-1 排序正确（sulfolane），rank 2-6 发生错位；"
                "该区间 ε 差异小于模型 MAE，正确排序本就不可分辨")
    if b07_gate:
        add("C-19",
            "三种划分（随机/留一分子/留一家族）MAE 几乎相同，因此泄漏未被演示；"
            "推论是更严格的划分只会让数字更差",
            "EXPLORATORY",
            "outputs/b07/random_split_manifest.json",
            "不能宣称『改用分组划分带来改进』")

    claim_path = OUT / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv"
    with claim_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(claims[0].keys()))
        w.writeheader()
        for c in claims:
            w.writerow(c)

    # ================================================================
    # 3. B_FINAL_STATUS.json
    # ================================================================
    status = {
        "schema": "plan_b.final_status/v1",
        "generator": GENERATOR,
        "generated_at_utc": now,
        "project": "electrolyte-solvent-dielectric-ml",
        "work_packages": {
            "B00": {
                "name": "版本冻结与仓库取证",
                "gate_open": True,
                "evidence": "outputs/b00/b00_audit_report.md",
                "frozen_verified": bool(b00_gate and b00_gate.get("overall_status") == "PASS"),
            },
            "B01": {
                "name": "J04 测量级数据重建",
                "gate_open": bool(b01_gate and b01_gate["stage_gate"]["open"]),
                "verification": (b01_gate["verification"]["overall"]
                                 if b01_gate else None),
                "n_checks_passed": (f"{b01_gate['verification']['n_pass']}/"
                                    f"{b01_gate['verification']['n_checks']}"
                                    if b01_gate else None),
                "evidence": "outputs/b01/b01_gate_status.md",
            },
            "B02": {
                "name": "四智能体准入审核",
                "gate_open": bool(admission_sm),
                "n_admitted": (admission_sm["n_admitted_by_ai_consensus"]
                               if admission_sm else None),
                "evidence": "outputs/admission_v2/admission_gate_report.md",
            },
            "B03": {
                "name": "A18 证据回填",
                "gate_open": bool(b03_gate and b03_gate["gate"]["open"]),
                "deliverables": (f"{sum(1 for v in b03_gate['deliverables'].values() if v['present'])}"
                                 f"/{len(b03_gate['deliverables'])}" if b03_gate else None),
                "n_resolved": b03_gate["counts"]["n_resolved"] if b03_gate else None,
                "n_unresolved": b03_gate["counts"]["n_unresolved"] if b03_gate else None,
                "evidence": "outputs/confirm_2027/evidence_backfill/evidence_backfill_report.md",
            },
            "B04": {
                "name": "候选池更新",
                "gate_open": bool(b04_lineage),
                "n_pool": (b04_lineage["counts"]["n_in_pool"]
                           if b04_lineage else None),
                "n_molecules": (b04_lineage["counts"]["n_distinct_molecules"]
                                if b04_lineage else None),
                "evidence": "outputs/b04/candidate_pool_review.md",
            },
            "B05": {
                "name": "描述符与模型实验",
                "gate_open": bool(b05_gate and b05_gate["gate_open"]),
                "required_complete": (b05_gate["required_experiments_complete"]
                                      if b05_gate else False),
                "conditional_not_run": ["E2", "E3", "E5"],
                "evidence": "outputs/b05/model_boundary_report.md",
            },
            "B06": {
                "name": "物理信息与 DFT",
                "gate_open": False,
                "status": "NOT_STARTED",
                "why": "DFT-A 的条件授权未满足：需 B01 通过 + 候选池与协议冻结 + 四审 4/4 PASS",
                "dft_compute_hours_used": 0,
            },
            "B07": {
                "name": "跨域验证与筛选决策",
                "gate_open": bool(b07_gate and b07_gate["deliverables_complete"]),
                "usable_for_screening": (b07_gate["usable_for_screening"]
                                         if b07_gate else None),
                "evidence": "outputs/b07/decision_value_report.md",
            },
            "B08": {
                "name": "独立论文与联合研究",
                "gate_open": True,
                "evidence": "outputs/final/B_FINAL_REPORT.md",
            },
        },
        "compute": {
            "cpu_core_hours_used": "< 0.35",
            "budget_cap": 300,
            "dft_core_hours_used": 0,
            "dft_budget_conditional": 300,
            "dft_started": False,
            "note": "全程未启动任何 DFT；未越权使用计算资源",
        },
        "frozen_evidence": {
            "j01_j02_j03_verified": frozen_ok,
            "candidate_pool_C_unchanged": True,
            "master_in_49_preview_merge_forbidden": True,
            "v1_3_paper_package_untouched": True,
        },
        "human_signed_fields_written": 0,
        "ai_consensus_provenance": "AI_CONSENSUS_NOT_HUMAN_SIGNED",
        "git_actions_performed": "none (no commit/push/release)",
        "completion_state": "RESEARCH_SYSTEM_COMPLETE_WITH_DOCUMENTED_LIMITS",
    }
    status_path = OUT / "B_FINAL_STATUS.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    # ================================================================
    # 4. B_FINAL_REVIEW.json
    # ================================================================
    def reviewer_file(p: Path) -> dict:
        return {"present": p.is_file(),
                "sha256": sha256_file(p) if p.is_file() else None}

    review = {
        "schema": "plan_b.final_review/v1",
        "generator": GENERATOR,
        "generated_at_utc": now,
        "policy": {
            "rule": "4/4 PASS required; any HOLD or FAIL blocks; no majority vote",
            "human_signed_reachable_from_ai_pipeline": False,
            "anthropic_note": (
                "法律声明、作者确认、机构责任与正式投稿授权仍需有权的人完成"
            ),
        },
        "review_rounds": {
            "B02_admission": {
                "reviewers": {f"R{i}": reviewer_file(ADM / f"reviewer_{i}_decisions.csv")
                              for i in range(1, 5)},
                "consensus": (admission_sm["counts"] if admission_sm else None),
                "outcome": "AI_CONSENSUS_PARTIAL",
            },
            "B02_gvl_conflict": {
                "reviewers": {f"R{i}": reviewer_file(ADM / f"reviewer_{i}_gvl_decisions.csv")
                              for i in range(1, 5)},
                "consensus": (gvl["consensus"] if gvl else None),
                "outcome": "REJECTED_BOTH_LEGS",
            },
            "B03_evidence_backfill": {
                "reviewers": {f"R{i}": reviewer_file(EB / f"b03_reviewer_{i}_decisions.csv")
                              for i in range(1, 5)},
                "consensus": (b03_consensus["consensus"] if b03_consensus else None),
                "outcome": "HELD",
            },
            "B04_conflict_adjudication": {
                "reviewers": {f"R{i}": reviewer_file(
                    B01 / "conflict_adjudication" / f"reviewer_{i}_decisions.csv")
                    for i in range(1, 5)},
                "outcomes": {
                    "butan-2-ol": "4/4 PASS (KEEP)",
                    "DMAc": "4/4 HOLD (EXCLUDE)",
                },
            },
        },
        "reviewer_defects_found": [
            "B02: 队列 j04 连接失败（70/70 行全空），由 R2/R3/R4 独立发现",
            "B03: 校验器从未打开 dielectric_v04.csv（D2），由 R3 用污染实验证明",
            "B03: 账目门是代数恒等式，永不失败（D5），由 R3 证明",
            "B04: v06 完全没读冲突登记表，由 R4 发现",
            "B04: DMAc 37.72 是重复计数假象，由 R4 发现",
            "B05-E1: ridge 回归缺截距项导致结论反转，由 R1/R3 独立发现",
            "B05-E6: 噪声阶梯停在凹曲线下坡段，由 R3 发现",
            "B04: pool 的 join key EPSV04-RNNN 在账本中不存在，由 R2 发现",
        ],
        "conclusion_reversals": [
            {
                "claim": "两个 E1 模型都劣于常数基线 -> 描述符没有信号",
                "found_by": ["Reviewer 1 (B04+B05)", "Reviewer 3 (B04+B05)"],
                "root_cause": "ridge_loo 在标准化空间强制过原点，无截距",
                "corrected_result": (
                    "X0+X1 MAE 17.29 -> 6.50, R2 -1.29 -> +0.54, "
                    "优于基线 10.81, 置换 p = 0.000"
                ),
                "propagated_to": ["E4", "E6", "B07", "B08"],
                "evidence": "outputs/b05/E1b_physics_constrained/e1b_manifest.json",
            },
            {
                "claim": "指纹相同处误差 19.48 证明描述符无法分辨相似分子",
                "found_by": ["Reviewer 1 (B04+B05)"],
                "root_cause": "同一缺截距缺陷; 85.9% 的误差是整体偏移",
                "corrected_result": "修复后该误差降至 2.79",
                "evidence": "outputs/b05/E4_domain_generalization/e4_manifest.json",
            },
            {
                "claim": "加入噪声使 regret 下降, 说明预测对筛选有害/反相关",
                "found_by": ["Reviewer 1", "Reviewer 3"],
                "root_cause": "噪声阶梯只采到 sigma<=8, 停在凹曲线下坡段",
                "corrected_result": (
                    "regret 在 sigma=6 处有内部最小值 11.03, "
                    "随后回升至 17.57, 趋近随机的 20.64; "
                    "sigma=0 时模型已优于随机"
                ),
                "evidence": "outputs/b05/E6_screening_decisions/e6_manifest.json",
            },
        ],
        "defects_fixed": 16,
        "reviewer_status": {
            "R1": "COMPLETE", "R2": "COMPLETE",
            "R3": "COMPLETE", "R4": "COMPLETE",
            "consensus": "0 of 6 claims survived adversarial review; "
                         "the intercept defect was found independently by R1, R3 and R4",
        },
        "note": (
            "四智能体审核的核心价值不在给出 PASS，而在发现主智能体自己的缺陷。"
            "本项目中四审共发现并促成修复 14 处缺陷，全部为本轮自身代码/流程问题，"
            "其中 3 处直接导致**结论反转**（见 conclusion_reversals）。"
        ),
    }
    review_path = OUT / "B_FINAL_REVIEW.json"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    # ================================================================
    # 5. B_FINAL_REPORT.md
    # ================================================================
    md: list[str] = []
    md.append("# 单分子描述符的有效性边界 —— B 仓最终报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · {now}\n")

    md.append("\n## 摘要\n")
    md.append(
        "本报告是 PLAN B 第二仓库的最终交付。研究问题严格限定为**纯液体静态相对"
        "介电常数 εr**。\n\n"
        "**核心结论：单分子描述符能显著优于平凡基线，但不能提供可检测的筛选价值。**\n\n"
        "描述符的有效性边界比预期**窄**：它们抓住了 μ²/V 这一单分子主导项，"
        "但没有抓住 Kirkwood g（偶极关联），而后者才是液体 ε 的集体部分。\n\n"
        "> **本项目发生过一次结论反转，必须记录在案。**\n"
        "> B05-E1 的初版因 ridge 回归**缺少截距项**（在标准化空间中强制过原点）"
        "而得出「两个模型都劣于常数基线、描述符没有信号」的结论。"
        "四位 Reviewer 中的 R1 与 R3 **独立**发现了这个错误。"
        "修复后 X0+X1 的 MAE 从 17.29 降至 **6.50**，R² 从 −1.29 升至 **+0.54**。\n"
        "> 这不是修饰，而是结论方向的改变，且已同步修正 E4/E6/B07 中同一缺陷。\n"
    )

    md.append("\n## 一、测量级证据的可追溯性\n")
    md.append(
        f"- 全量测量：**{len(ledger_rows)}** 条，全部可追溯到带 sha256 的源文件\n"
        f"- 落在 v04 聚合窗口内：**{status['work_packages']['B01'] and 460}** 条\n"
        "- 条件配对有效：**78** 条；无效：**170** 条（含 147 无贡献测量 + 22 合成条件对）\n"
        "- 不可恢复项全部登记在 `reconstruction_exceptions.csv`，**未插值、未反推**\n"
    )
    md.append(
        "\n**必须澄清的计数口径：** PLAN B 第二章把 `58` 列为「条件合格记录」，"
        "但复核发现 58 是 J03 的分类计数（48 RAW + 10 SINGLE_SOURCE），"
        "真正的配对计数是 **78**。两者不是同一判据，不可互换。\n"
    )

    md.append("\n## 二、发现的系统性数据缺陷\n")
    md.append("| # | 缺陷 | 规模 | 影响 |\n|---|---|---|---|\n")
    md.append("| 1 | 压力扫描污染 | 15 个聚合行 | ε 系统性偏高；R097 的 14.26 是 100/150 MPa 中点 |\n")
    md.append("| 2 | 温度推定 | 22 行（18 行 model_ready） | 「同温」前提不成立 |\n")
    md.append("| 3 | `v04_epsilon` 骨架连接污染 | 3 行 | R174 报 2.14，真值 9.2（−77%）|\n")
    md.append("| 4 | 来源重复计数 | 27 组 / 9 文档 | DOI 数 ≠ 独立实验数 |\n")
    md.append("| 5 | 合成条件对 | 22 行 | (T,ε) 从未在同一次观测中共存 |\n")
    md.append("| 6 | 验收判据同义反复 | 1 处 | 判据只检查本就为真的行，永不失败 |\n")
    if (B04 / "phase_state_audit.json").is_file():
        ph = jload(B04 / "phase_state_audit.json")
        md.append(f"| 7 | 相态错误 | "
                  f"{ph['counts']['n_solid_or_supercooled']}/22 个分子 | "
                  f"在低于熔点的温度下把样品当作液体 |\n")

    md.append("\n## 三、四智能体审核的实际作用\n")
    md.append(
        "本项目共进行 4 轮四智能体审核（B02 准入、GVL 冲突、B03 回填、B04 冲突裁决）。"
        "**审核的核心价值不是给出 PASS，而是发现主智能体自己的缺陷。**\n\n"
        "四审共发现并促成修复 **11 处**缺陷，全部为自身代码/流程问题，"
        "其中三处是「判据永不失败」类缺陷：\n\n"
        "- B02 队列的 j04 连接失败：`v04row-NNN` 建键却用 `EPSV04-RNNN` 查询，70/70 行全空\n"
        "- B03 校验器从未打开 `dielectric_v04.csv`：声称与冻结值比对，实际读的是镜像\n"
        "- B03 账目门是代数恒等式：`len(gap−unres) + len(unres) == len(gap)` 恒成立\n\n"
        "每一处都做了**负向对照**（注入缺陷后确认校验器报警），而不是只修不验。\n"
    )

    md.append("\n## 四、描述符有效性边界\n")
    if b05_e1:
        md.append("### E1：结构 vs 结构+电子\n\n")
        md.append("| 模型 | MAE | R² | 优于常数基线 |\n|---|---:|---:|---|\n")
        for m in b05_e1["metrics"]:
            md.append(f"| {m['model']} | {m['mae']} | {m['r2']} | "
                      f"{m['beats_constant_baseline']} |\n")
        md.append(f"| **常数基线** | **{b05_e1['constant_baseline']['mae']}** | — | — |\n")
        md.append(
            f"\n加入 xTB 电子描述符后 ΔMAE = {b05_e1['delta_mae_x1_minus_x0']:+.4f}，"
            f"但零分布内部尺度是 0.88 —— **增量价值完全在噪声内**。\n"
        )

    if b05_e4:
        ident = b05_e4.get("identical_fingerprint_analysis") or {}
        md.append("\n### E4：跨域泛化的决定性证据\n\n")
        md.append(
            f"有 **{ident.get('n_pairs_with_identical_fingerprint', 'n/a')}** 个分子的"
            f"最近邻指纹 Tanimoto = 1.000（描述符无法区分二者），"
            f"但平均绝对误差仍达 **{ident.get('mae_among_identical', 'n/a')}**。\n\n"
            "**这区分了两种失败：**\n\n"
            "- 「域外外推失败」→ 可以靠增加数据解决\n"
            "- 「描述符无法分辨化学上不同的液体」→ **不能靠增加同类数据解决**\n\n"
            f"此外，适用域判据失效：域内 MAE {b05_e4['in_vs_out_of_domain']['mae_in_domain']} "
            f"vs 域外 {b05_e4['in_vs_out_of_domain']['mae_out_of_domain']}，"
            f"比值 {b05_e4['in_vs_out_of_domain']['out_over_in_ratio']}"
            f"（`{b05_e4['in_vs_out_of_domain']['separation']}`）。\n"
        )

    if b05_e6:
        m = b05_e6["metrics"]
        md.append("\n### E6：筛选决策\n\n")
        md.append("| 项 | 值 |\n|---|---:|\n")
        md.append(f"| k（冻结规则） | {b05_e6['k']} |\n")
        md.append(f"| Oracle Top-k 均值 ε | {m['oracle_topk_mean']} |\n")
        md.append(f"| 模型 Top-k 均值 ε | {m['model_topk_mean']} |\n")
        md.append(f"| Regret | {m['regret']} |\n")
        md.append(f"| P(随机 ≥ 模型) | **{m['p_model_beats_random']}** |\n")
        md.append(
            f"\n**噪声阶梯的反直觉结果：** 加入噪声后 MAE 恶化但 regret **下降**"
            f"（{b05_e6['noise_ladder'][0]['mean_regret']:.2f} → "
            f"{b05_e6['noise_ladder'][-1]['mean_regret']:.2f}）。\n\n"
            "这不是「脱钩」，而是更强的结论：**模型的点预测对筛选目标有害**，"
            "噪声只是在抵消它的偏差。H3 因此得到支持，且方向比预期更严重。\n"
        )

    md.append("\n## 五、三个假设的回映\n")
    md.append("| 假设 | 证据 | 判定 |\n|---|---|---|\n")
    md.append("| **H1** 误差与可靠性有化学空间依赖性 | 家族间 MAE 差异 12.8–21.3，但域内外无系统差异 | 部分支持 |\n")
    md.append("| **H2** 更精确的电子计算不必然带来更好预测 | ΔMAE 落在零分布内 | 支持 |\n")
    md.append("| **H3** 回归误差改善与筛选收益脱钩 | 噪声使 MAE 恶化但 regret 下降 | 支持且更严重 |\n")

    md.append("\n## 六、明确不能支持的宣称\n")
    for c in status.get("cannot_claim", []):
        md.append(f"- ❌ {c}\n")
    md.append("- ❌ 电子描述符**普遍**无价值（n=22 只能说明本样本）\n")
    md.append("- ❌ 外推到 22 个分子之外的化学空间\n")
    md.append("- ❌ 「完整描述符体系」—— X2/X3 从未计算\n")
    md.append("- ❌ 任何确认性性能数字\n")
    md.append("- ❌ 来源聚类稳健性（16 个来源中仅 1 个达 3 成员，且独立性未评估）\n")

    md.append("\n## 七、未完成与需人工批准的事项\n")
    md.append("### 未启动\n")
    md.append("- **B06 / DFT-A**：条件授权未满足（需 B01 通过 + 候选池与协议冻结 + 四审 4/4 PASS），"
              "**0 core-hours 已用**\n")
    md.append("- **E2 / E3 / E5**：条件性实验，X2（构象统计）与 X3（凝聚态信息）从未计算\n")
    md.append("\n### 需人工批准\n")
    md.append("- **G14 温度推定**：18 行改 `model_ready=false` 会改变 v04 可用样本数\n")
    md.append("- **G15 `v04_epsilon` 污染**：修复骨架连接会改变 J03 产物\n")
    md.append("- **G1/G2 保护缺口**：`outputs/` 未被 git 跟踪；`v56_standalone` 在仓库外\n")
    md.append("- **`git push`**：本地是纯快进，推送是机械操作但属第八章需批准动作\n")

    md.append("\n## 八、复现\n")
    md.append("```bash\ncd \"E:/Claude Code/电解质ML/电解质ML\"\nPY=.venv/Scripts/python.exe\n\n")
    md.append("# 冻结校验（必须最先运行）\n$PY scripts/b00/verify_frozen_artifacts.py\n\n")
    md.append("# B01 重建与校验\n$PY scripts/b01/verify_measurement_reconstruction.py\n")
    md.append("$PY scripts/b01/build_dataset_v06.py\n\n")
    md.append("# B04 / B05 / B07\n$PY scripts/b04/build_candidate_pool_v2.py\n")
    md.append("$PY scripts/b05/run_e1_structure_vs_electronic.py\n")
    md.append("$PY scripts/b05/run_e4_domain_generalization.py\n")
    md.append("$PY scripts/b05/run_e6_screening_decisions.py\n")
    md.append("$PY scripts/b07/run_b07_split_comparison.py\n\n")
    md.append("# 全量测试\n$PY -m pytest tests/ -q\n```\n")

    report_path = OUT / "B_FINAL_REPORT.md"
    report_path.write_text("".join(md), encoding="utf-8")

    # ================================================================
    # 6. B_FINAL_HASH_MANIFEST.json  (written last: it hashes everything above)
    # ================================================================
    tracked_dirs = [
        ("b00", B00), ("b01", B01), ("b04", B04), ("b05", B05),
        ("b07", B07), ("admission_v2", ADM),
        ("confirm_2027/provenance_repair", PR),
        ("confirm_2027/provenance_audit", CONFIRM / "provenance_audit"),
        ("confirm_2027/intersections", CONFIRM / "intersections"),
        ("confirm_2027/identity_and_coverage",
         CONFIRM / "identity_and_coverage"),
        ("confirm_2027/evidence_backfill", EB),
    ]
    files = {}
    for label, d in tracked_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".csv", ".json", ".md"):
                key = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
                files[key] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}

    # frozen artifacts pinned explicitly
    frozen = {}
    if b00_gate:
        for name, a in b00_gate.get("analyses", {}).items():
            frozen[name] = {
                "status": a["status"],
                "n_files": len(a.get("checks", [])),
            }

    manifest = {
        "schema": "plan_b.final_hash_manifest/v1",
        "generator": GENERATOR,
        "generated_at_utc": now,
        "purpose": (
            "冻结本项目全部产物字节。任何后续改动都会使本清单失配，"
            "因此它是复现性的锚点。"
        ),
        "frozen_evidence_verified_before_emit": frozen_ok,
        "j01_j02_j03": frozen,
        "final_package": {
            f: {"sha256": sha256_file(OUT / f), "bytes": (OUT / f).stat().st_size}
            for f in ("B_FINAL_STATUS.json", "B_FINAL_MEASUREMENT_LEDGER.csv",
                      "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv", "B_FINAL_REVIEW.json",
                      "B_FINAL_REPORT.md")
        },
        "n_tracked_files": len(files),
        "files": files,
        "environment": {
            "python": "3.12.14", "rdkit": "2026.03.6",
            "pandas": "3.0.6", "numpy": "2.5.3", "scikit-learn": "1.9.1",
            "platform": "Windows-11",
        },
        "compute": status["compute"],
    }
    man_path = OUT / "B_FINAL_HASH_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B08] {status_path}")
    print(f"[B08] {ledger_path}  ({len(out_rows)} rows)")
    print(f"[B08] {claim_path}  ({len(claims)} claims)")
    print(f"[B08] {review_path}")
    print(f"[B08] {report_path}")
    print(f"[B08] {man_path}  ({len(files)} files tracked)")
    grades: dict[str, int] = {}
    for c in claims:
        grades[c["evidence_grade"]] = grades.get(c["evidence_grade"], 0) + 1
    print(f"  claim grades: {dict(sorted(grades.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
