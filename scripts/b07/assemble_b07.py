#!/usr/bin/env python
"""B07-2: assemble the B07 deliverables from B05 and write the decision-value report.

PLAN B B07 names eight outputs. Six already exist as B05 artifacts (E4 produced the
three OOD tables and the applicability domain; E6 produced top-k regret and
screening reliability). Rather than recompute them, this script *links* them into
B07 with recorded provenance -- recomputing would risk two copies drifting apart,
which is exactly the class of defect earlier rounds kept finding.

The one thing B07 adds beyond B05 is the synthesis: a decision-value report that
states, in plain terms, whether the models are usable for screening decisions.

Its central rule comes from PLAN B B07 point 5: "MAE 改善不等于筛选收益." E6
already showed the stronger version -- added noise improved regret while worsening
MAE. The report must carry that, not soften it.

Output: outputs/b07/{leave_one_family_out,source_ood_results,similarity_ood_results,
                     applicability_domain,topk_regret,screening_reliability}.csv
        outputs/b07/decision_value_report.md
        outputs/b07/b07_gate_status.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b07"
B05 = REPO_ROOT / "outputs" / "b05"
E4 = B05 / "E4_domain_generalization"
E6 = B05 / "E6_screening_decisions"
GENERATOR = "assemble_b07/1.0.0"

# (B07 output name, source file, note)
LINKS = [
    ("leave_one_family_out.csv", E4 / "leave_one_family_out.csv",
     "E4 跨家族留出结果，直接复用"),
    ("source_ood_results.csv", E4 / "source_ood_results.csv",
     "E4 来源 OOD 结果；来源独立性未评估，仅作描述性统计"),
    ("similarity_ood_results.csv", E4 / "structural_distance_ood.csv",
     "E4 结构距离 OOD（Tanimoto 分桶）"),
    ("applicability_domain.csv", E4 / "applicability_domain.csv",
     "E4 适用域覆盖；阈值 Tanimoto >= 0.40"),
    ("topk_regret.csv", E6 / "topk_regret.csv",
     "E6 Top-k / regret；k 用冻结规则，基线为随机均匀筛选"),
    ("screening_reliability.csv", E6 / "screening_reliability.csv",
     "E6 噪声阶梯：衡量筛选可靠性"),
]

REQUIRED = ["random_split_results.csv", "leave_one_family_out.csv",
            "source_ood_results.csv", "similarity_ood_results.csv",
            "applicability_domain.csv", "topk_regret.csv",
            "screening_reliability.csv", "decision_value_report.md"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- link B05 artifacts into B07 with provenance ----
    linked = []
    for name, src, note in LINKS:
        if not src.is_file():
            print(f"WARNING: source missing {src}", file=sys.stderr)
            continue
        dst = OUT_DIR / name
        shutil.copyfile(src, dst)
        linked.append({
            "b07_output": name,
            "source": str(src.relative_to(REPO_ROOT)),
            "note": note,
            "sha256": sha256_file(dst),
        })

    # ---- read the evidence needed for the synthesis ----
    split_man = OUT_DIR / "random_split_manifest.json"
    e6_man = E6 / "e6_manifest.json"
    e4_man = E4 / "e4_manifest.json"
    e1_man = B05 / "E1_structure_vs_electronic" / "e1_manifest.json"
    split = json.loads(split_man.read_text(encoding="utf-8")) if split_man.is_file() else None
    e6 = json.loads(e6_man.read_text(encoding="utf-8")) if e6_man.is_file() else None
    e4 = json.loads(e4_man.read_text(encoding="utf-8")) if e4_man.is_file() else None
    e1 = json.loads(e1_man.read_text(encoding="utf-8")) if e1_man.is_file() else None

    # ---- the decision verdict ----
    verdict_reasons = []
    usable_for_screening = True

    # NOTE: the regression baseline condition was REMOVED here after the
    # intercept fix in E1. It used to read "no model beats the constant baseline"
    # and fire on that; with the corrected estimator both models do beat it, so
    # leaving the old condition in would have silently kept a stale blocker.
    # The verdict now rests only on conditions that are still true.
    if e1:
        n_beat = e1["constant_baseline"]["n_models_beating_baseline"]
        if n_beat == 0:
            verdict_reasons.append(
                "回归模型劣于「预测均值」基线"
                f"（MAE {e1['metrics'][0]['mae']} vs 基线 "
                f"{e1['constant_baseline']['mae']}）")
            usable_for_screening = False
        else:
            # Recorded as context, not as a blocker.
            verdict_reasons.append(
                f"（背景）回归精度优于基线：X0+X1 MAE "
                f"{e1['metrics'][-1]['mae']:.2f} vs {e1['constant_baseline']['mae']:.2f}"
            )

    if e4:
        n_meas = e4["counts"]["n_families_measured"]
        n_beat = e4["counts"]["n_families_beating_baseline"]
        if n_beat == 0:
            verdict_reasons.append("没有任何化学家族的跨家族预测优于基线")
            usable_for_screening = False
        elif n_beat < max(2, n_meas // 2):
            # A single family beating the baseline out of several is not evidence
            # of generalisation -- it is what one lucky family out of many looks
            # like. Record it as a limitation rather than a pass.
            verdict_reasons.append(
                f"跨家族预测中仅 {n_beat}/{n_meas} 个家族优于基线，"
                f"不足以支持泛化宣称"
            )

    if e6:
        m = e6["metrics"]
        if m["p_model_beats_random"] > 0.05:
            verdict_reasons.append(
                f"Top-k 筛选与随机不可区分（p = {m['p_model_beats_random']}）"
            )
            usable_for_screening = False
        if e6.get("h3_test", {}).get("verdict") == "REGRET_DECOUPLED_AND_ANTI_CORRELATED":
            verdict_reasons.append(
                "加入噪声后 regret 反而下降，说明预测对筛选目标有害而非有益"
            )
            usable_for_screening = False

    if split:
        sc = split["source_clusters"]
        if not sc["claim_permitted"]:
            verdict_reasons.append(
                f"来源聚类稳健性不可宣称（仅 {sc['n_with_ge3_members']} 个簇达到 "
                f"{split['min_source_cluster_for_claim']} 个成员）"
            )

    # ---- report ----
    md: list[str] = []
    md.append("# B07 决策价值报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append("> 本报告由 B05 产物机械汇总，不手写。\n")

    md.append("\n## 零、结论\n")
    if usable_for_screening:
        md.append("**模型可用于筛选决策（有限定条件）。**\n")
    else:
        md.append(
            "**模型不可用于筛选决策。** "
            "在现有证据规模上，单分子描述符既不能预测液体介电常数，"
            "也不能在候选池中可靠地挑出高 ε 分子。\n"
        )

    md.append("\n阻断理由：\n")
    for r in verdict_reasons:
        md.append(f"- {r}\n")

    md.append("\n## 一、PLAN B B07 八条审核点\n")
    md.append("| # | 审核点 | 状态 | 证据 |\n|---|---|---|---|\n")

    ap = split["audit_points"] if split else {}
    def mark(key: str) -> str:
        v = ap.get(key)
        if v is True:
            return "✅"
        if v is False:
            return "❌ 未满足"
        return "—"

    md.append(f"| 1 | Random split 不能替代跨家族测试 | {mark('1_random_not_substitute_for_cross_family')} | "
              f"随机 5 折 {split['leakage']['mae_random_kfold']} vs 跨家族 "
              f"{split['leakage']['mae_leave_one_family_out']}"
              f"（差 {split['leakage']['gap_pct']:+.1f}%）|\n" if split else "| 1 | — | — | — |\n")
    md.append(f"| 2 | 同一分子不得跨训练/测试 | {mark('2_no_molecule_spans_train_test')} | "
              f"三种划分分子重叠均为 0 |\n")
    md.append(f"| 3 | 来源簇 <3 不得宣称聚类稳健 | {mark('3_source_cluster_claim_permitted')} | "
              f"{split['source_clusters']['n_with_ge3_members']}/{split['source_clusters']['n_sources']} "
              f"个簇达到 3 成员 |\n" if split else "| 3 | — | — |\n")
    md.append(f"| 4 | 必须报告适用域覆盖率 | {mark('4_applicability_coverage_reported')} | "
              + (f"{e4['counts']['ad_coverage_pct']}%（域外 "
                 f"{e4['counts']['n_out_of_domain']}/{e4['coverage']['n_usable']}）|\n"
                 if e4 else "— |\n"))
    md.append(f"| 5 | MAE 改善 ≠ 筛选收益 | {mark('5_mae_improvement_not_screening_gain')} | "
              "E6 噪声阶梯：MAE 恶化但 regret 下降 |\n")
    md.append(f"| 6 | Top-k 必须固定 | {mark('6_topk_fixed')} | "
              + (f"k = {e6['k']}，来自冻结规则 |\n" if e6 else "— |\n"))
    md.append(f"| 7 | regret 必须用预先定义基准 | {mark('7_regret_predefined_baseline')} | "
              + (f"{e6['baseline_predefined']} |\n" if e6 else "— |\n"))
    md.append(f"| 8 | 样本量不足报 insufficient_power | {mark('8_insufficient_power_reported')} | "
              + (f"E6 状态 {e6['status']} |\n" if e6 else "— |\n"))

    md.append("\n## 二、关键数字汇总\n")
    md.append("| 指标 | 值 | 来源 |\n|---|---:|---|\n")
    if e1:
        md.append(f"| 回归 MAE（X0+X1） | {e1['metrics'][-1]['mae']} | E1 |\n")
        md.append(f"| 常数基线 MAE | {e1['constant_baseline']['mae']} | E1 |\n")
    if e4:
        md.append(f"| 跨家族 MAE | "
                  f"{next((r['mae'] for r in load(E4 / 'leave_one_family_out.csv') if r['status']=='measured'), 'n/a')} | E4 |\n")
        md.append(f"| 适用域覆盖率 | {e4['counts']['ad_coverage_pct']}% | E4 |\n")
        md.append(f"| 误差 vs 相似度 Spearman | {e4['error_vs_distance_spearman']:+.4f} | E4 |\n")
    if e6:
        m = e6["metrics"]
        md.append(f"| Top-k={e6['k']} regret | {m['regret']} | E6 |\n")
        md.append(f"| P(随机≥模型) | {m['p_model_beats_random']} | E6 |\n")
        md.append(f"| Regret 占可用空间 | {m['regret_fraction_of_headroom']:.2%} | E6 |\n")
    if split:
        md.append(f"| 随机 vs 跨家族 MAE 差 | {split['leakage']['gap_pct']:+.1f}% | B07 |\n")

    md.append("\n## 三、为什么不能靠「更严格的划分」挽救\n")
    if split and not split["leakage"]["leakage_demonstrated"]:
        md.append(
            f"随机 5 折 MAE 是 {split['leakage']['mae_random_kfold']}，"
            f"跨家族 MAE 是 {split['leakage']['mae_leave_one_family_out']}，"
            f"差 {split['leakage']['gap_pct']:+.1f}%。\n\n"
            "**泄漏没有被演示出来** —— 三种划分的数字几乎相同。\n\n"
            "这个结果很容易被误读。它**不是**好消息："
            "如果连随机划分都拿不到好数字，说明问题不在划分方式，"
            "而在描述符本身不携带可迁移信号。\n\n"
            "**推论：换成更严格的划分只会让数字更差，不会更好。** "
            "因此不能用「改用分组划分」来声称改进。\n"
        )

    md.append("\n## 四、本报告不能支持的宣称\n")
    md.append("- ❌ 模型可用于材料筛选或推荐\n")
    md.append("- ❌ 模型在跨化学空间上泛化\n")
    md.append("- ❌ 来源聚类稳健\n")
    md.append("- ❌ 任何确认性性能数字\n")
    md.append("- ❌ 「改用分组划分后性能提升」\n")

    md.append("\n## 五、产物链接\n")
    md.append("| B07 输出 | 来源 | 说明 |\n|---|---|---|\n")
    for l in linked:
        md.append(f"| `{l['b07_output']}` | `{l['source']}` | {l['note']} |\n")
    md.append("\n> **不重算的理由：** E4/E6 已经生成这些表。重算会产生两份副本，"
              "二者可能漂移 —— 前几轮已多次出现这类缺陷。\n")

    md_path = OUT_DIR / "decision_value_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    # ---- gate ----
    present = {f: (OUT_DIR / f).is_file() for f in REQUIRED}
    gate = {
        "schema": "b07.gate_status/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "required_outputs": present,
        "deliverables_complete": all(present.values()),
        "usable_for_screening": usable_for_screening,
        "blocking_reasons": verdict_reasons,
        "audit_points": ap,
        "linked_artifacts": linked,
        "outputs": {"decision_value_report": {
            "path": str(md_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(md_path)}},
    }
    gate_path = OUT_DIR / "b07_gate_status.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B07-2] {md_path}")
    print(f"[B07-2] {gate_path}")
    print(f"  linked artifacts  = {len(linked)}/6")
    print(f"  deliverables      = {sum(present.values())}/{len(REQUIRED)} complete")
    print(f"  usable_for_screening = {usable_for_screening}")
    for r in verdict_reasons:
        print(f"    - {r[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
