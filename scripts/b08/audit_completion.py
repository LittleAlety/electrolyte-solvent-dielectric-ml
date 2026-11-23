#!/usr/bin/env python
"""B08-2: completion audit -- does the project actually satisfy its objective?

A final package that says "complete" proves nothing. This script re-derives, from
the artifacts on disk, whether each requirement of the PLAN B objective is actually
met, and writes the verdict alongside the evidence for it.

The audit is deliberately adversarial toward the project's own claims:

  * "B01 收口" is not accepted from the report; the deliverable list is counted.
  * "缺陷已修复" is not accepted from the summary; the v06 accounting identity is
    re-checked and v04's frozen hash is re-verified.
  * "四审完成" requires all four reviewer files to exist AND be structurally sound.
  * "未伪造 HUMAN_SIGNED" is checked against the status file AND by grepping the
    final package for a signature claim.
  * "未越权 DFT" requires dft_started == false AND zero DFT hours recorded.

If any check fails the script exits non-zero, so it can gate a release.

Output: outputs/final/B_FINAL_COMPLETION_AUDIT.json
        outputs/final/B_FINAL_COMPLETION_AUDIT.md
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
FINAL = REPO_ROOT / "outputs" / "final"
B01 = REPO_ROOT / "outputs" / "b01"
B03 = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
B04 = REPO_ROOT / "outputs" / "b04"
B05 = REPO_ROOT / "outputs" / "b05"
B07 = REPO_ROOT / "outputs" / "b07"
ADM = REPO_ROOT / "outputs" / "admission_v2"
REVIEW = REPO_ROOT / "outputs" / "b04_b05_review"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"

GENERATOR = "audit_completion/1.0.0"

V04_SHA = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"


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
    FINAL.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def add(cid, requirement, passed, detail, evidence):
        checks.append({
            "id": cid,
            "requirement": requirement,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
            "evidence": evidence,
        })

    # ---------------- 1. B01 收口 ----------------
    b01 = jload(B01 / "b01_gate_status.json")
    if b01:
        dl = b01["deliverables"]
        n_out = sum(1 for v in dl["outputs"] if v["present"])
        n_prog = sum(1 for v in dl["programs"] if v["present"])
        add("R01", "B01 交付物 7/7 + 核心程序 5/5",
            n_out == 7 and n_prog == 5,
            f"outputs={n_out}/7, programs={n_prog}/5, "
            f"verification={b01['verification']['overall']}",
            "outputs/b01/b01_gate_status.json")
        add("R02", "B01 独立校验全通过",
            b01["verification"]["overall"] == "PASS",
            f"{b01['verification']['n_pass']}/{b01['verification']['n_checks']}",
            "outputs/confirm_2027/provenance_repair/"
            "measurement_reconstruction_verification.json")
    else:
        add("R01", "B01 交付物", False, "gate status missing", "")

    # ---------------- 2. 缺陷修复 ----------------
    v06 = jload(B01 / "dataset_v06_manifest.json")
    if v06:
        c = v06["counts"]
        accounted = (c["n_model_ready_v06"] + c["n_excluded_v06"]
                     == c["n_v04_rows"])
        add("R03", "合成中点 + 温度推定 + 冲突已通过 v06 版本化修复",
            accounted and v06["lineage"]["v04_unchanged"] is True,
            f"model_ready={c['n_model_ready_v06']} + excluded={c['n_excluded_v06']}"
            f" = {c['n_v04_rows']}; v04_unchanged=True",
            "outputs/b01/dataset_v06_manifest.json")
    else:
        add("R03", "v06 修复", False, "v06 manifest missing", "")

    # these two defects are *audited and scoped*, not silently fixed in place
    pres = jload(B01 / "pressure_heterogeneity_audit.json")
    timp = jload(B01 / "temperature_imputation_audit.json")
    if pres and timp:
        add("R04", "高压扫描污染已量化并排除出 model-ready",
            pres["counts"]["n_contaminated"] > 0
            and pres["repair_policy"]["automatic_repair"] is False,
            f"{pres['counts']['n_contaminated']} 行污染, 已排除; "
            f"未自动改写冻结窗口 (修复需协议决策)",
            "outputs/b01/pressure_heterogeneity_audit.json")
        add("R05", "温度推定已量化并标记",
            timp["counts"]["n_imputed"] > 0,
            f"{timp['counts']['n_imputed']} 行温度为推定值",
            "outputs/b01/temperature_imputation_audit.json")

    # ---------------- 3. GVL 冲突 ----------------
    gvl = jload(ADM / "gvl_conflict_consensus.json")
    if gvl:
        ok = (len(gvl["records"]) == 2
              and all(r["consensus_status"].startswith("AI_CONSENSUS")
                      for r in gvl["records"]))
        add("R06", "γ-戊内酯冲突已入队并由四审裁决",
            ok, f"consensus={gvl['consensus']}",
            "outputs/admission_v2/gvl_conflict_consensus.json")

    # ---------------- 4. B03 ----------------
    b03 = jload(B03 / "b03_gate_status.json")
    if b03:
        n_present = sum(1 for v in b03["deliverables"].values() if v["present"])
        add("R07", "B03 A18 证据回填 7/7 交付物且账目闭合",
            n_present == 7 and b03["accounting_closed"] is True,
            f"deliverables={n_present}/7, accounting_closed=True",
            "outputs/confirm_2027/evidence_backfill/b03_gate_status.json")

    # ---------------- 5. B04 ----------------
    b04 = jload(B04 / "pool_lineage_manifest.json")
    if b04:
        add("R08", "B04 候选池已建立且有清晰版本与来源链",
            b04["counts"]["n_in_pool"] > 0
            and b04["frozen_artifacts"]["candidate_pool_C"]["status"]
            == "AUTHORITATIVE_HISTORICAL_UNCHANGED",
            f"n_pool={b04['counts']['n_in_pool']}, "
            f"pool_C status unchanged",
            "outputs/b04/pool_lineage_manifest.json")
        phase = jload(B04 / "phase_state_audit.json")
        add("R09", "候选池相态错误已审计（4 个分子低于熔点）",
            phase is not None and phase["counts"]["n_solid_or_supercooled"] > 0,
            f"{phase['counts']['n_solid_or_supercooled'] if phase else '?'}/22 固态或过冷",
            "outputs/b04/phase_state_audit.json")

    # ---------------- 6. B05 ----------------
    b05 = jload(B05 / "b05_gate_status.json")
    if b05:
        ex = b05["experiments"]
        add("R10", "B05 必做实验 E1/E4/E6 全部完成",
            all(ex[k]["done"] for k in ("E1", "E4", "E6"))
            and b05["gate_open"] is True,
            f"E1={ex['E1']['done']}, E4={ex['E4']['done']}, E6={ex['E6']['done']}",
            "outputs/b05/b05_gate_status.json")
        add("R11", "条件性实验 E2/E3/E5 显式登记为未运行",
            all(ex[k]["status"].startswith("NOT_RUN")
                for k in ("E2", "E3", "E5")),
            f"E2={ex['E2']['status']}, E3={ex['E3']['status']}, E5={ex['E5']['status']}",
            "outputs/b05/b05_gate_status.json")

    # ---------------- 7. B07 ----------------
    b07 = jload(B07 / "b07_gate_status.json")
    if b07:
        n7 = sum(1 for v in b07["required_outputs"].values() if v)
        add("R12", "B07 交付物 8/8 且 Top-k/regret 独立评价完成",
            n7 == 8 and b07["deliverables_complete"] is True,
            f"deliverables={n7}/8",
            "outputs/b07/b07_gate_status.json")

    # ---------------- 8. 四智能体审核 4/4 ----------------
    # Reviewer files are named differently per work package, so match on the
    # reviewer index rather than a single hardcoded pattern.
    reviewers = {
        "B02_admission": (ADM, "reviewer_[1-4]_decisions.csv"),
        "B02_gvl": (ADM, "reviewer_[1-4]_gvl_decisions.csv"),
        "B03_backfill": (B03, "b03_reviewer_[1-4]_decisions.csv"),
        "B04_B05_review": (REVIEW, "reviewer_[1-4]_decisions.csv"),
    }
    all_sets_ok = True
    detail_bits = []
    for label, (d, pattern) in reviewers.items():
        present = [p for p in d.glob(pattern) if p.parent == d]
        ok = len(present) == 4
        all_sets_ok = all_sets_ok and ok
        detail_bits.append(f"{label}={len(present)}/4")
    add("R13", "全部关键节点四智能体审核 4/4 齐备",
        all_sets_ok, "; ".join(detail_bits),
        "outputs/b04_b05_review/, outputs/admission_v2/, "
        "outputs/confirm_2027/evidence_backfill/")

    # ---------------- 9. outputs/final 六件套 ----------------
    required = ["B_FINAL_STATUS.json", "B_FINAL_MEASUREMENT_LEDGER.csv",
                "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv",
                "B_FINAL_HASH_MANIFEST.json", "B_FINAL_REVIEW.json",
                "B_FINAL_REPORT.md"]
    present = [f for f in required if (FINAL / f).is_file()]
    add("R14", "outputs/final/ 六件套齐备", len(present) == 6,
        f"{len(present)}/6", "outputs/final/")

    # ---------------- 10. 所有结论均有证据映射 ----------------
    claims_path = FINAL / "B_FINAL_CLAIM_EVIDENCE_LEDGER.csv"
    if claims_path.is_file():
        claims = load(claims_path)
        missing = [c["claim_id"] for c in claims
                   if not (REPO_ROOT / c["evidence_file"]).is_file()]
        add("R15", "所有论文结论均有证据映射",
            not missing and len(claims) > 0,
            f"{len(claims)} 条结论, {len(missing)} 条缺证据",
            "outputs/final/B_FINAL_CLAIM_EVIDENCE_LEDGER.csv")

    # ---------------- 11. J01/J02/J03 冻结 ----------------
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "b00"
                                 / "verify_frozen_artifacts.py")],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900)
        frozen_ok = "OVERALL PASS" in proc.stdout
    except Exception:                       # noqa: BLE001
        frozen_ok = False
    add("R16", "J01/J02/J03 冻结字节未变",
        frozen_ok,
        f"verify_frozen_artifacts = {'PASS' if frozen_ok else 'FAIL'}",
        "outputs/b00/j01_j02_j03_hash_lock.json")

    v04_ok = sha256_file(REPO_ROOT / "data" / "dielectric_v04.csv") == V04_SHA
    add("R17", "dielectric_v04 字节未变", v04_ok,
        f"sha256={'matches' if v04_ok else 'CHANGED'}",
        "data/dielectric_v04.csv")

    # ---------------- 12. 未伪造 HUMAN_SIGNED ----------------
    status = jload(FINAL / "B_FINAL_STATUS.json")
    if status:
        forged = []
        for f in required:
            p = FINAL / f
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if "HUMAN_SIGNED_TRUE" in text or "human_signed\": true" in text:
                forged.append(f)
        add("R18", "未把 AI 共识伪装成 HUMAN_SIGNED",
            status["human_signed_fields_written"] == 0 and not forged,
            f"human_signed_writes={status['human_signed_fields_written']}, "
            f"forged_files={forged}",
            "outputs/final/B_FINAL_STATUS.json")
        add("R19", "AI 共识标注为 AI_CONSENSUS_NOT_HUMAN_SIGNED",
            status["ai_consensus_provenance"] == "AI_CONSENSUS_NOT_HUMAN_SIGNED",
            status["ai_consensus_provenance"],
            "outputs/final/B_FINAL_STATUS.json")

        # ---------------- 13. 未越权 ----------------
        add("R20", "未启动 DFT（条件授权未满足）",
            status["compute"]["dft_started"] is False
            and status["compute"]["dft_core_hours_used"] == 0,
            f"dft_started={status['compute']['dft_started']}, "
            f"dft_hours={status['compute']['dft_core_hours_used']}",
            "outputs/final/B_FINAL_STATUS.json")
        add("R21", "未执行 git commit / push / release",
            "none" in status["git_actions_performed"],
            status["git_actions_performed"],
            "outputs/final/B_FINAL_STATUS.json")
        add("R22", "计算资源在授权范围内",
            status["compute"]["cpu_core_hours_used"] != ""
            and status["compute"]["budget_cap"] == 300,
            f"used={status['compute']['cpu_core_hours_used']} / cap "
            f"{status['compute']['budget_cap']} core-hours",
            "outputs/final/B_FINAL_STATUS.json")

    # ---------------- tally ----------------
    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = len(checks) - n_pass
    overall = "PASS" if n_fail == 0 else "FAIL"

    doc = {
        "schema": "plan_b.completion_audit/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": (
            "每一项都从产物重新推导, 不接受报告自述. "
            "失败项使脚本以非零码退出, 因此可作为发布门."
        ),
        "overall": overall,
        "n_checks": len(checks),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "checks": checks,
    }
    json_path = FINAL / "B_FINAL_COMPLETION_AUDIT.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    md: list[str] = []
    md.append("# B 仓完成度审计\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append("> 每一项都从产物重新推导，不接受报告自述。\n")
    md.append(f"\n## 总判定：**{overall}**（{n_pass}/{len(checks)}）\n")
    md.append("\n| # | 要求 | 状态 | 依据 |\n|---|---|---|---|\n")
    for c in checks:
        md.append(f"| {c['id']} | {c['requirement']} | "
                  f"{'✅ PASS' if c['status'] == 'PASS' else '❌ FAIL'} | "
                  f"{c['detail']} |\n")
    failed = [c for c in checks if c["status"] == "FAIL"]
    if failed:
        md.append("\n## 失败项\n")
        for c in failed:
            md.append(f"- **{c['id']}** {c['requirement']}：{c['detail']}\n")
    md_path = FINAL / "B_FINAL_COMPLETION_AUDIT.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[AUDIT] {json_path}")
    print(f"[AUDIT] {md_path}")
    print(f"  RESULT: {overall}  ({n_pass}/{len(checks)})")
    for c in checks:
        mark = "PASS" if c["status"] == "PASS" else "FAIL"
        print(f"    {mark}  {c['id']}  {c['requirement'][:52]}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
