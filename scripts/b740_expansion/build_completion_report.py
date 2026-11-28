"""Build an evidence-linked completion report; never turn missing work into completion."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/b750_completion"


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def identities(relative):
    with (ROOT / relative).open(encoding="utf-8-sig", newline="") as handle:
        return {r["inchikey"] for r in csv.DictReader(handle)}


def main():
    validation = load("outputs/b740_expansion/dft_expansion/results_opt/validation/summary.json")
    transfer = load("outputs/b750_completion/electronic_transfer/electronic_transfer_summary.json")
    liquid = load("outputs/b750_completion/leakage_audit/safe_liquid_ablation_summary.json")
    expanded = load(
        "outputs/b750_completion/leakage_audit_expanded/safe_liquid_ablation_summary.json"
    )
    mixtures = load("outputs/b750_completion/mixtures/mixture_cluster_summary.json")
    quadrupole = load("outputs/b750_completion/quadrupole/quadrupole_audit.json")
    retry = load("outputs/b750_completion/retry_opt/submission_record.json")
    with (
        ROOT / "outputs/b740_expansion/dft_expansion/results_opt/validation/validation_ledger.csv"
    ).open(encoding="utf-8") as handle:
        latest = {row["inchikey"]: row for row in csv.DictReader(handle)}
    retry_accepted = sum(latest[j["inchikey"]]["status"] == "ACCEPTED" for j in retry["jobs"])
    retry_outcome = {
        "job_id": retry["job_id"],
        "expected": retry["n_jobs"],
        "accepted": retry_accepted,
        "status": "ACCEPTED_ALL" if retry_accepted == retry["n_jobs"] else "INCOMPLETE",
    }
    (OUT / "retry_opt/outcome.json").write_text(
        json.dumps(retry_outcome, indent=2), encoding="utf-8"
    )
    checks = load("outputs/b750_completion/verification.json")
    conf = identities("outputs/b740_expansion/conformer_analysis/conformer_entropy.csv")
    panel = identities("outputs/b750_completion/leakage_audit_expanded/paired_predictions.csv")
    result = {
        "schema": "b750.completion_summary/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "COMPUTATION_COMPLETE_SCIENTIFIC_GAPS_OPEN"
        if validation["complete"]
        else "IN_PROGRESS_COMPUTATION",
        "plan_complete": False,
        "reason": "Complete scientific plan still needs actual full compute outputs, quadrupoles, vaporization enthalpy and resolved liquid-correlation evidence.",
        "validation": validation,
        "transfer_status": transfer["status"],
        "transfer_evaluable": transfer["n_evaluable"],
        "transfer_results": transfer.get("results"),
        "safe_liquid_panel_n": liquid["n_paired_panel"],
        "safe_liquid_mae_gain": liquid["paired_mae_gain"],
        "expanded_liquid_panel_n": expanded["n_paired_panel"],
        "all_layer_intersection_n": len(conf & panel),
        "cm": mixtures["cm_correction"],
        "pair_contrast": mixtures["by_pair"]["difference"],
        "doi_contrast": mixtures["by_doi"]["difference"],
        "quadrupole_status": quadrupole["status"],
        "retry_job_id": retry["job_id"],
        "retry_outcome": retry_outcome,
        "verification": checks,
        "unresolved": [
            "Complete 67-molecule ORCA results",
            "Quadrupoles were not requested in historical outputs",
            "No vaporization enthalpy for CED/Hildebrand in current corpus",
            "Insufficient frequency coverage for dielectric spectra",
            "Fixed-charge MD failed dielectric preflight",
            "Gas-phase dipole error and collective orientation are not identifiable separately",
        ],
        "supersedes": "Affected v7.4 claims only; historical outputs and frozen results remain unchanged.",
    }
    diagnostic = OUT / "failure_diagnostics/failure_diagnostics.json"
    if diagnostic.exists():
        audit = json.loads(diagnostic.read_text(encoding="utf-8"))
        result["failure_diagnosis"] = audit["counts"]
        result["diagnosis_time"] = audit["generated_at_utc"]
        if not validation["complete"] and "b742" not in audit["queue"]:
            result["status"] = "BLOCKED_NEEDS_SUBMISSION"
    (OUT / "completion_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    all_transfer = transfer.get("results", {}).get("all", {})
    lines = [
        "# PLAN B v7.5 执行与科学更正报告",
        "",
        "状态：**未全部完成**。本地实现和分析已交付；完整计算与数据证据缺口保持开放。",
        "",
        "| 项目 | 实际状态 |",
        "|---|---|",
        f"| ORCA总分母 | {validation['expected']} |",
        f"| 已回收 / 验收通过 / 拒绝 / 未回收 | {validation['recovered']} / {validation['accepted']} / {validation['rejected']} / {validation['not_recovered']} |",
        f"| 同集合电子层迁移 | {transfer['n_evaluable']}分子，{transfer['status']}，仅描述性 |",
        f"| 首轮续算 | 作业 {retry['job_id']}，{retry_accepted}/{retry['n_jobs']}已通过验收 |",
        f"| 无泄漏液相面板 / 当前扩张后面板 | {liquid['n_paired_panel']} / {expanded['n_paired_panel']} |",
        f"| 全层交集 | {len(conf & panel)}，信息不足 |",
        f"| 四极矩 | {quadrupole['n_outputs_scanned']}份历史输出已审计；{quadrupole['status']}，0个可建模张量 |",
        f"| 验收测试 | {checks['pytest']['passed']} passed；代码检查 {checks['ruff']['status']} |",
        "",
        "## 影响论文表述的更正",
        "",
        "1. 历史X3含由目标ε计算的Δf，存在标签泄漏；旧增益−0.0232不能证明液相信息有效或无效。",
        "2. 历史gap_v7实际来自xTB。新电子层只用来源明确的ORCA opt偶极和极化率。",
        f"3. CM错误截断已修正：全部{mixtures['cm_correction']['n_defined']}点有定义，MAE={mixtures['cm_correction']['mae']:.6f}；旧318/2278与14%定义域结论撤回。",
        f"4. 氢键分组残差差值={mixtures['by_pair']['difference']['point_estimate']:.6f}；按对95%区间{mixtures['by_pair']['difference']['ci95']}，按DOI区间{mixtures['by_doi']['difference']['ci95']}，均含零。原先用点级CI不重叠推断组间差异的结论不成立。",
        "",
        "## 当前可报告的读数",
        "",
        f"无泄漏液相配对LOO：n={liquid['n_paired_panel']}，MAE {liquid['base']['mae']:.6f} → {liquid['augmented']['mae']:.6f}，改善 {liquid['paired_mae_gain']:.6f}。模型和特征口径也有更正，不能把变化全部归因于删除Δf。样本小且来源不独立，只作描述性结果。",
    ]
    if all_transfer:
        lines.extend(
            [
                "",
                f"新分子同集合迁移：n={transfer['n_evaluable']}，MAE {all_transfer['X0']['mae']:.6f} → {all_transfer['X0_X1']['mae']:.6f}。子集由计算完成顺序选择，不能作为67分子代表性结果或确认性电子层增益。",
            ]
        )
    lines.extend(
        [
            "",
            "最新根因诊断见 [FAILURE_ANALYSIS.md](failure_diagnostics/FAILURE_ANALYSIS.md)：21个几何步数耗尽、1个中断、7个从未启动；当前需新提交覆盖29分子的批次。",
            "",
            "## 复现与继续执行",
            "",
            "从仓库根目录执行：",
            "",
            '    .venv/Scripts/python.exe scripts/b740_expansion/complete_plan.py --collect --key "C:/Users/Little Alety/.ssh/id_ed25519_whu" --known-hosts "C:/Users/Little Alety/.ssh/known_hosts"',
            "",
            "该命令只回收与分析，不新增作业；会合并独立续算结果与原始结果，并保留67分母。测试证据在verification.json。新的已完成输出回收后需要重跑验收并重建本报告。",
            "",
            "剩余阻塞：完整67分子计算、四极矩新计算、蒸发焓外部数据、充分介电频谱、可验证的极化MD及关联机制可识别性。它们不能通过权限授权或更多契约测试替代。",
            "",
        ]
    )
    (OUT / "COMPLETION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "plan_complete": False,
                "accepted": validation["accepted"],
                "expected": 67,
            }
        )
    )


if __name__ == "__main__":
    main()
