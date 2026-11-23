#!/usr/bin/env python
"""B01-5: assemble the B01 stage-gate verdict.

This does not re-run the checks; it reads their outputs and states plainly whether
B01 is complete. Its most important job is to distinguish:

    B01 DATA RECONSTRUCTION      -- is the measurement ledger sound?
    B01 VERIFICATION             -- do independent checks pass?
    B01 STAGE GATE               -- may B02/B04 proceed?

They are not the same question, and collapsing them is how projects declare
success on a dataset whose own acceptance criterion is vacuous.

Output: outputs/b01/b01_gate_status.json
        outputs/b01/b01_gate_status.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b01"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
ADJ_DIR = REPO_ROOT / "outputs" / "b01" / "conflict_adjudication"
GENERATOR = "build_b01_gate_status/1.0.0"

REQUIRED_OUTPUTS = [
    "measurement_ledger_v1.csv",
    "source_document_registry_v1.csv",
    "aggregate_contribution_ledger_v1.csv",
    "condition_pair_validity_v1.csv",
    "dataset_v05_manifest.json",
    "reconstruction_exceptions.csv",
    "provenance_repair_report.md",
]

REQUIRED_PROGRAMS = [
    "reconstruct_measurement_ledger.py",
    "build_provenance_preserving_dataset.py",
    "audit_condition_pair_integrity.py",
    "validate_source_independence.py",
    "verify_measurement_reconstruction.py",
]


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

    # ---- deliverable presence ----
    outputs = []
    for name in REQUIRED_OUTPUTS:
        p = PR / name
        outputs.append({
            "name": name,
            "present": p.is_file(),
            "bytes": p.stat().st_size if p.is_file() else 0,
            "sha256": sha256_file(p) if p.is_file() else None,
        })

    programs = []
    for name in REQUIRED_PROGRAMS:
        p = REPO_ROOT / "scripts" / "confirm_2027" / name
        if not p.is_file():
            p = REPO_ROOT / "scripts" / "b01" / name
        programs.append({"name": name, "present": p.is_file(),
                         "path": str(p.relative_to(REPO_ROOT)) if p.is_file() else None})

    # ---- read the verification verdict ----
    ver_path = PR / "measurement_reconstruction_verification.json"
    verification = None
    if ver_path.is_file():
        verification = json.loads(ver_path.read_text(encoding="utf-8"))

    # ---- read the schema conformance verdict ----
    schema_path = PR / "b01_schema_conformance.json"
    schema = None
    if schema_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # ---- read the exceptions register ----
    exc_path = PR / "reconstruction_exceptions.csv"
    exc_rows = []
    if exc_path.is_file():
        with exc_path.open(encoding="utf-8-sig", newline="") as fh:
            exc_rows = list(csv.DictReader(fh))
    exc_by_class = Counter((r.get("exception_class") or "").strip() for r in exc_rows)

    # ---- read independence report ----
    indep_path = PR / "source_independence_report.json"
    indep = None
    if indep_path.is_file():
        indep = json.loads(indep_path.read_text(encoding="utf-8"))

    # ---- read pressure audit ----
    pres_path = REPO_ROOT / "outputs" / "b01" / "pressure_heterogeneity_audit.json"
    pressure = None
    if pres_path.is_file():
        pressure = json.loads(pres_path.read_text(encoding="utf-8"))

    # ---- read conflict register ----
    conf_path = REPO_ROOT / "outputs" / "b01" / "source_conflict_register.json"
    conflicts = None
    if conf_path.is_file():
        conflicts = json.loads(conf_path.read_text(encoding="utf-8"))

    # ---- read temperature imputation audit ----
    timp_path = REPO_ROOT / "outputs" / "b01" / "temperature_imputation_audit.json"
    timp = None
    if timp_path.is_file():
        timp = json.loads(timp_path.read_text(encoding="utf-8"))

    # ---- read the GVL adjudication ----
    gvl_path = REPO_ROOT / "outputs" / "admission_v2" / "gvl_conflict_consensus.json"
    gvl = None
    if gvl_path.is_file():
        gvl = json.loads(gvl_path.read_text(encoding="utf-8"))

    # ---- gate evaluation ----
    all_outputs = all(o["present"] for o in outputs)
    all_programs = all(p["present"] for p in programs)

    ver_pass = bool(verification and verification["summary"]["overall"] == "PASS")
    ver_checks = verification["summary"] if verification else None
    ver_failed = [c["check"] for c in (verification or {}).get("checks", [])
                  if c["status"] == "FAIL"]

    schema_gaps = schema["true_gaps"] if schema else []

    # The stage gate is deliberately NOT "all checks passed". B01 can be complete
    # as a *reconstruction* while a known defect keeps the gate closed.
    blockers = []
    if not all_outputs:
        blockers.append("缺少交付物")
    if not all_programs:
        blockers.append("缺少核心程序")
    if not ver_pass:
        blockers.append(f"独立校验未全通过: {ver_failed}")
    if schema_gaps:
        blockers.append(f"账本字段真实缺口: {schema_gaps}")

    # Remaining known defects are NOT blockers for B01 itself (they are recorded,
    # scoped, and require a protocol decision), but they must block B04.
    #
    # Important distinction: a defect that has been *repaired in a new version*
    # is no longer a blocker -- provided the repair is additive (frozen bytes
    # untouched) and the excluded rows remain individually traceable. v06 does
    # exactly that, so the pressure/synthetic-midpoint blockers are cleared on the
    # condition that v06 exists and its accounting closes.
    v06_path = REPO_ROOT / "outputs" / "b01" / "dataset_v06_manifest.json"
    v06 = None
    if v06_path.is_file():
        v06 = json.loads(v06_path.read_text(encoding="utf-8"))

    v06_ok = False
    if v06:
        v06_ok = (
            v06["lineage"]["v04_unchanged"] is True
            and v06["lineage"]["frozen_artifacts_unchanged"] is True
            and (v06["counts"]["n_model_ready_v06"]
                 + v06["counts"]["n_excluded_v06"]
                 == v06["counts"]["n_v04_rows"])
        )

    b04_blockers: list[str] = []
    exc_synth = exc_by_class.get("SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN", 0)
    if pressure and pressure["counts"]["n_contaminated"] and not v06_ok:
        b04_blockers.append(
            f"压力污染 {pressure['counts']['n_contaminated']} 行未修复")
    if exc_synth and not v06_ok:
        b04_blockers.append(f"合成条件对 {exc_synth} 行")
    if timp and timp["counts"]["n_imputed_model_ready"] and not v06_ok:
        b04_blockers.append(
            f"温度推定 {timp['counts']['n_imputed_model_ready']} 行标记 model_ready")

    # Conflicts only block B04 if they are UNRESOLVED *and* still reachable from
    # the model-ready set. v06 excludes unresolved ones, and the four-agent
    # adjudication resolved the two that touched model-ready molecules, so a raw
    # count of 56 would overstate the remaining exposure.
    if conflicts:
        total_conf = conflicts["counts"]["n_conflicts_measurement_layer"]
        adj = {}
        for p in ADJ_DIR.glob("reviewer_*_decisions.csv"):
            try:
                for r in load(p):
                    cid = (r.get("conflict_id") or "").strip()
                    if cid and cid != "ALL":
                        adj.setdefault(cid, []).append(
                            (r.get("decision") or "").strip().upper())
            except Exception:
                continue
        resolved = sum(1 for cid, v in adj.items()
                       if v.count("PASS") == 4)
        # Conflicts on molecules that are no longer model-ready do not block B04.
        ready_keys = set()
        if v06:
            ready_keys = {r["inchikey"] for r in
                          load(REPO_ROOT / "outputs" / "b01"
                               / "dataset_v06_model_ready.csv")}
        blocking_conf = 0
        conflict_csv = REPO_ROOT / "outputs" / "b01" / "measurement_conflict_register.csv"
        if conflict_csv.is_file():
            for c in load(conflict_csv):
                ik = (c.get("molecule_key") or "").strip()
                cid = (c.get("conflict_id") or "").strip()
                if ik in ready_keys and adj.get(cid, []).count("PASS") < 4:
                    blocking_conf += 1
        if blocking_conf:
            b04_blockers.append(
                f"model-ready 分子上仍有 {blocking_conf} 组未解决冲突")
        conflicts_summary = {
            "n_total": total_conf,
            "n_resolved_by_four_agent": resolved,
            "n_blocking_model_ready": blocking_conf,
            "note": (
                "总数扣掉已裁决与已不在 model-ready 的分子后才是 B04 的真实暴露. "
                "直接引用 56 会高估阻断范围."
            ),
        }
    else:
        conflicts_summary = None

    gate_open = not blockers

    result = {
        "schema": "b01.gate_status/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "three_separate_questions": {
            "1_data_reconstruction": (
                "测量级账本是否成立? —— 2065 条测量全部可追溯, "
                "78 条配对有效, 170 条例外已登记"
            ),
            "2_verification": (
                "独立校验是否通过? —— 见 checks 明细. 注意其中一项判 FAIL, "
                "该失败是**正确行为**, 因为它抓到了生成器判据的同义反复"
            ),
            "3_stage_gate": (
                "B02/B04 是否可推进? —— 由 blockers 决定, 不由'看起来做完了'决定"
            ),
        },
        "deliverables": {
            "outputs": outputs,
            "programs": programs,
            "all_outputs_present": all_outputs,
            "all_programs_present": all_programs,
        },
        "verification": {
            "overall": verification["summary"]["overall"] if verification else None,
            "n_checks": ver_checks["n_checks"] if ver_checks else None,
            "n_pass": ver_checks["n_pass"] if ver_checks else None,
            "n_fail": ver_checks["n_fail"] if ver_checks else None,
            "failed_checks": ver_failed,
            "failed_check_interpretation": (
                "generator_acceptance_criterion_is_not_tautological 判 FAIL 是**设计如此**: "
                "build_provenance_preserving_dataset.py:437 的判据只检查 69/248 行"
                "(全部为 true), 排除的 179 行中有 170 行为 false, 因此该判据不可能失败. "
                "本校验器把它暴露为失败, 而不是配合它假装通过."
                if "generator_acceptance_criterion_is_not_tautological" in ver_failed
                else None
            ),
        },
        "schema_conformance": {
            "n_true_gaps": len(schema_gaps),
            "true_gaps": schema_gaps,
            "note": "measurement_locator 完全缺失; extraction_method 与 verification_status "
                    "存在语义错位, 已按缺口处理而非按别名通过",
        },
        "reconstruction_exceptions": {
            "n_exceptions": len(exc_rows),
            "by_class": dict(sorted(exc_by_class.items())),
            "false_negatives_found": [
                (r.get("measurement_id") or "").strip() for r in exc_rows
                if (r.get("exception_class") or "").strip()
                == "SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE"
            ],
        },
        "source_independence": {
            "n_cross_document_duplicate_groups": (
                indep["duplicate_observations"]["n_groups_cross_document"]
                if indep else None),
            "n_documents_entangled": (
                indep["duplicate_observations"]["n_documents_entangled"]
                if indep else None),
            "n_aggregates_affected": (
                indep["aggregate_impact"]["n_aggregates_affected"] if indep else None),
            "finding": (
                "n_contributing_sources 数的是 DOI 字符串, 不是独立实验. "
                "注册表对 61/61 文档标注 independence=not_evaluated. "
                "B07 来源聚类检验必须先按文档去重."
            ),
        },
        "pressure_heterogeneity": {
            "n_contaminated": pressure["counts"]["n_contaminated"] if pressure else None,
            "by_class": pressure["counts"]["by_class"] if pressure else None,
            "finding": (
                "10.1021/je060248p 等来源是固定温度下的压力扫描研究, "
                "聚合把单调压力序列的中位数当作常压观测. R097 的 14.26 恰为 "
                "100/150 MPa 中点. 修复需改动冻结窗口, 属协议决策."
            ),
        },
        "source_conflicts": {
            "n_aggregate_layer": (conflicts["counts"]["n_conflicts_aggregate_layer"]
                                  if conflicts else None),
            "n_measurement_layer": (conflicts["counts"]["n_conflicts_measurement_layer"]
                                    if conflicts else None),
            "n_excluded_from_review_queue": (
                conflicts["counts"]["n_conflicts_excluded_from_review_queue"]
                if conflicts else None),
            "finding": (
                "γ-戊内酯 36.1 vs 36.9 冲突已进入审核队列并由四智能体裁决. "
                "观测层另有 56 组同分子同温分歧, 尚未逐一裁决."
            ),
            "gvl_adjudication": {
                "consensus": gvl["consensus"] if gvl else None,
                "outcome": (
                    "两条记录均 REJECTED (未达 4/4 PASS). "
                    "R2/R4 判 FAIL, R1/R3 判 HOLD. "
                    "四位对处置方式分歧: RETAIN_PARALLEL vs NEEDS_PRIMARY_DOCUMENT vs REJECT_ROW. "
                    "未取平均, 未择一主值."
                ) if gvl else None,
            },
            "summary": conflicts_summary,
        },
        "temperature_imputation": {
            "n_imputed": timp["counts"]["n_imputed"] if timp else None,
            "n_imputed_model_ready": timp["counts"]["n_imputed_model_ready"] if timp else None,
            "by_source": timp["counts"]["by_temperature_source"] if timp else None,
            "finding": (
                "22/248 行温度是推定值, 其中 18 行 model_ready=true. "
                "GVL 冲突的『同温』前提正是两次独立推定碰巧一致 —— "
                "该前提不成立, 因此不能按同温实测矛盾裁决."
            ),
        },
        "repair_version_v06": {
            "exists": v06 is not None,
            "accounting_ok": v06_ok,
            "n_model_ready": v06["counts"]["n_model_ready_v06"] if v06 else None,
            "n_excluded": v06["counts"]["n_excluded_v06"] if v06 else None,
            "delta_vs_v05": v06["counts"]["delta_vs_v05_pair_valid"] if v06 else None,
            "repairs": v06["repairs_applied"] if v06 else None,
            "note": (
                "v06 以**新增版本**方式修复三项缺陷: 压力异质性/合成中点/温度推定 "
                "被排除或标记出 model_ready 集合, 而 v04/v05/J01/J02/J03 字节未动. "
                "被排除的 174 行全部保留在 exclusions.csv, 旧分母可复现."
            ),
        },
        "stage_gate": {
            "open": gate_open,
            "blockers": blockers,
            "may_proceed_to": ["B02", "B03"] if gate_open else [],
            "may_proceed_to_b04": False,
            "b04_blockers": b04_blockers,
            "b04_note": (
                "B01 通过不等于 B04 可以建池. 下列缺陷会把已知问题固化进新版本: "
                + "; ".join(b04_blockers)
                if b04_blockers else
                "无已知缺陷阻塞 B04"
            ),
        },
        "headline_counts": verification["headline_counts"] if verification else None,
    }

    json_path = OUT_DIR / "b01_gate_status.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 阶段门状态\n")
    md.append(f"> 生成器 `{GENERATOR}` · {result['generated_at_utc']}\n")

    md.append("\n## 一、三个必须分开的问题\n")
    for k, v in result["three_separate_questions"].items():
        md.append(f"**{k}** — {v}\n\n")

    md.append("## 二、交付物\n")
    md.append("| 文件 | 存在 | 字节 | sha256(前16) |\n|---|---|---:|---|\n")
    for o in outputs:
        md.append(f"| `{o['name']}` | {'✅' if o['present'] else '❌'} | "
                  f"{o['bytes']} | `{(o['sha256'] or '')[:16]}` |\n")

    md.append("\n| 程序 | 存在 |\n|---|---|\n")
    for p in programs:
        md.append(f"| `{p['name']}` | {'✅' if p['present'] else '❌'} |\n")

    md.append("\n## 三、独立校验\n")
    if verification:
        s = verification["summary"]
        md.append(f"- 总判定：**{s['overall']}**（{s['n_pass']}/{s['n_checks']}）\n")
        if ver_failed:
            md.append(f"- 失败项：{', '.join('`'+f+'`' for f in ver_failed)}\n")
            if result["verification"]["failed_check_interpretation"]:
                md.append(f"\n> {result['verification']['failed_check_interpretation']}\n")

    md.append("\n## 四、例外登记\n")
    for k, v in sorted(exc_by_class.items()):
        md.append(f"- `{k}`：{v}\n")
    fn = result["reconstruction_exceptions"]["false_negatives_found"]
    if fn:
        md.append(f"\n**发现的假阴性：** {', '.join('`'+x+'`' for x in fn)}\n")
        md.append("\n这些行的证书声称来源层无数据，但账本中存在精确匹配观测，"
                  "只是温度落在硬编码窗口外。**结论仍对，理由错误。**\n")

    md.append("\n## 五、来源独立性\n")
    si = result["source_independence"]
    md.append(f"- 跨文档完全重复观测组：**{si['n_cross_document_duplicate_groups']}**\n")
    md.append(f"- 涉及文档：**{si['n_documents_entangled']}**\n")
    md.append(f"- 受影响聚合行：**{si['n_aggregates_affected']}**\n")
    md.append(f"\n{si['finding']}\n")

    md.append("\n## 六、压力异质性\n")
    ph = result["pressure_heterogeneity"]
    md.append(f"- 受污染聚合行：**{ph['n_contaminated']}**\n")
    if ph["by_class"]:
        for k, v in sorted(ph["by_class"].items()):
            md.append(f"  - `{k}`：{v}\n")
    md.append(f"\n{ph['finding']}\n")

    md.append("\n## 七、未决来源冲突\n")
    sc = result["source_conflicts"]
    md.append(f"- 聚合层冲突：**{sc['n_aggregate_layer']}** 组\n")
    md.append(f"- 观测层冲突：**{sc['n_measurement_layer']}** 组\n")
    md.append(f"- 未进入审核队列：**{sc['n_excluded_from_review_queue']}** 组\n")
    md.append(f"\n{sc['finding']}\n")
    if sc.get("gvl_adjudication"):
        md.append(f"\n**γ-戊内酯裁决：** {sc['gvl_adjudication']['outcome']}\n")

    md.append("\n## 八、温度推定\n")
    ti = result["temperature_imputation"]
    md.append(f"- 推定温度行：**{ti['n_imputed']}**\n")
    md.append(f"- 其中 model_ready=true：**{ti['n_imputed_model_ready']}**\n")
    if ti["by_source"]:
        for k, v in sorted(ti["by_source"].items()):
            md.append(f"  - `{k}`：{v}\n")
    md.append(f"\n{ti['finding']}\n")

    md.append("\n## 九、阶段门\n")
    if gate_open:
        md.append("**B01 阶段门：OPEN**\n")
    else:
        md.append("**B01 阶段门：CLOSED**\n\n阻断项：\n")
        for b in blockers:
            md.append(f"- {b}\n")
    md.append(f"\n{result['stage_gate']['b04_note']}\n")

    md_path = OUT_DIR / "b01_gate_status.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-5] {json_path}")
    print(f"[B01-5] {md_path}")
    print(f"  outputs present = {all_outputs}  programs present = {all_programs}")
    print(f"  verification    = {result['verification']['overall']} "
          f"({result['verification']['n_pass']}/{result['verification']['n_checks']})")
    print(f"  stage gate OPEN = {gate_open}")
    for b in blockers:
        print(f"    blocker: {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
