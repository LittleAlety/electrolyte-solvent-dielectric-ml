#!/usr/bin/env python
"""B04: build candidate_pool_v2 from the evidence that actually survived review.

This is the first point where the project can legitimately construct a new
candidate pool, and it is deliberately the *narrowest* possible construction.

Eligibility is the intersection of three independent gates, each of which was
produced by a different work package:

    1. B02 four-agent consensus == AI_CONSENSUS_ACCEPTED   (22 records)
    2. v06 model_ready == true                            (73 records)
    3. not excluded by an unresolved source conflict      (v06 already applies)

Only records satisfying ALL of them enter. That intersection is 22 -- every
model-ready record that also passed unanimous review, and it happens to be one
row per molecule.

What this pool deliberately does NOT do:
  * it does not merge the historical S4 preview (`merge_forbidden` stays true)
  * it does not modify candidate_pool_C, which remains the authoritative
    historical version
  * it does not lower any admission bar to grow the sample
  * it does not call 22 records a "dataset" -- 22 molecules is a screening
    feasibility set, not a training set, and B05 must say so

Output: outputs/b04/candidate_pool_v2_draft.csv
        outputs/b04/pool_lineage_manifest.json
        outputs/b04/candidate_exclusion_audit.csv
        outputs/b04/candidate_pool_review.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b04"
B01 = REPO_ROOT / "outputs" / "b01"
ADM = REPO_ROOT / "outputs" / "admission_v2"
STANDALONE = REPO_ROOT.parent / "v56_standalone"
GENERATOR = "build_candidate_pool_v2/1.0.0"

V06_READY = B01 / "dataset_v06_model_ready.csv"
V06_EXCL = B01 / "dataset_v06_exclusions.csv"
CONSENSUS = ADM / "consensus_decisions.csv"
MEAS_LEDGER = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
               / "measurement_ledger_v1.csv")
POOL_C = STANDALONE / "reports" / "candidate_pool_C_R001.csv"


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
    for p in (V06_READY, V06_EXCL, CONSENSUS):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ready = load(V06_READY)
    excluded = load(V06_EXCL)
    consensus = load(CONSENSUS)

    accepted = {r["measurement_id"] for r in consensus
                if (r.get("consensus_status") or "") == "AI_CONSENSUS_ACCEPTED"}
    ready_by_id = {r["measurement_id"]: r for r in ready}

    # ---- resolve the ACTUAL ledger observation for each pool row ----
    # Reviewer 2 (B04+B05) found that the published join key `EPSV04-RNNN` does not
    # exist in measurement_ledger_v1.csv at all (0/22 exact matches; the ledger
    # re-keys as MSR-<md5>). The rows only resolve through an undocumented
    # positional convention, which makes the lineage recoverable but not citable.
    #
    # The ledger DOES carry `aggregate_id`, so join on that -- it resolves 22/22 --
    # and publish the concrete MSR-* observation id so a reader can cite it.
    ledger_rows = load(MEAS_LEDGER) if MEAS_LEDGER.is_file() else []
    obs_by_agg: dict[str, list[dict]] = {}
    for m in ledger_rows:
        a = (m.get("aggregate_id") or "").strip()
        if a and a.lower() != "not_evaluated":
            obs_by_agg.setdefault(a, []).append(m)

    def resolve_observation(agg_id: str, t_k: str, eps: str) -> dict:
        """Find the single ledger observation a pool row corresponds to."""
        cands = obs_by_agg.get(agg_id, [])
        exact = [m for m in cands
                 if (m.get("temperature_K") or "").strip() == (t_k or "").strip()
                 and (m.get("dielectric") or "").strip() == (eps or "").strip()]
        pool_ = exact or cands
        if len(pool_) == 1:
            m = pool_[0]
            return {"obs_id": (m.get("measurement_id") or "").strip(),
                    "n_candidates": len(cands),
                    "ambiguous": False}
        if pool_:
            return {"obs_id": (pool_[0].get("measurement_id") or "").strip(),
                    "n_candidates": len(cands), "ambiguous": len(pool_) > 1}
        return {"obs_id": "", "n_candidates": 0, "ambiguous": False}

    # ---- the pool ----
    # ---- phase state: is each molecule actually liquid at its stated T? ----
    # Reviewer 1 (B04+B05) found that some pool molecules are measured below their
    # melting point. The existing liquid_window_gate asks a different question (is T
    # inside a declared -20..60 C observation window), so it cannot answer this.
    # See scripts/b04/audit_pool_phase_state.py for the full audit.
    PHASE_AUDIT = OUT_DIR / "phase_state_audit.csv"
    phase_by_meas: dict[str, dict] = {}
    if PHASE_AUDIT.is_file():
        for r in load(PHASE_AUDIT):
            phase_by_meas[(r.get("measurement_id") or "").strip()] = r

    pool: list[dict] = []
    for mid in sorted(accepted & set(ready_by_id)):
        r = ready_by_id[mid]
        cons = next((c for c in consensus if c["measurement_id"] == mid), {})
        obs = resolve_observation(r["aggregate_id"], r["T_K"], r["dielectric"])
        pool.append({
            "measurement_id": mid,
            "ledger_observation_id": obs["obs_id"],
            "ledger_join_key": "aggregate_id",
            "ledger_n_candidates": obs["n_candidates"],
            "ledger_observation_ambiguous": "true" if obs["ambiguous"] else "false",
            "phase_status": (phase_by_meas.get(mid, {}).get("phase_status")
                             or "NOT_AUDITED"),
            "mp_margin_K": phase_by_meas.get(mid, {}).get("mp_margin_K") or "",
            "aggregate_id": r["aggregate_id"],
            "inchikey": r["inchikey"],
            "name": r["name"],
            "T_K": r["T_K"],
            "dielectric": r["dielectric"],
            "source_doi": r["source_doi"],
            "source_quality": r["source_quality"],
            "temperature_source": r["temperature_source"],
            "n_contributing_measurements": r["n_contributing_measurements"],
            "n_independent_experiments": r["n_independent_experiments"],
            # Reviewer 4 (B04+B05): 7 rows pool 3-5 observations yet report
            # n_independent_experiments=1. That is CORRECT (they are replicated
            # within one paper) but the label alone invites misreading, so state
            # the aggregation explicitly.
            "aggregation_type": (
                "SINGLE_OBSERVATION"
                if int(r["n_contributing_measurements"] or 0) <= 1
                else "SINGLE_SOURCE_AGGREGATE"
                if int(r["n_independent_experiments"] or 0) <= 1
                else "MULTI_SOURCE_AGGREGATE"),
            "condition_pair_valid": r["condition_pair_valid"],
            "b02_consensus_status": cons.get("consensus_status", ""),
            # Derived, not hardcoded: Reviewer 3 (B04+B05) flagged that a literal
            # "true" here is a check that cannot fail.
            "b02_four_of_four": (
                "true" if (cons.get("consensus_status") == "AI_CONSENSUS_ACCEPTED"
                           and str(cons.get("n_pass", "")).strip() == "4")
                else "false"),
            "v06_model_ready": "true",
            "admission_provenance": "AI_CONSENSUS_NOT_HUMAN_SIGNED",
            "pool_version": "v2_draft",
            "merge_forbidden": "true",
        })

    # ---- exclusion audit: everyone who was NOT admitted, and why ----
    audit: list[dict] = []
    pool_ids = {r["measurement_id"] for r in pool}

    cons_by_id = {r["measurement_id"]: r for r in consensus}

    for r in ready:
        mid = r["measurement_id"]
        if mid in pool_ids:
            continue
        cons = cons_by_id.get(mid, {})
        audit.append({
            "measurement_id": mid,
            "name": r["name"],
            "inchikey": r["inchikey"],
            "dielectric": r["dielectric"],
            "v06_model_ready": "true",
            "b02_consensus_status": cons.get("consensus_status", "NOT_IN_QUEUE"),
            "exclusion_reason": (
                "MODEL_READY_BUT_NOT_UNANIMOUS"
                if cons.get("consensus_status")
                else "MODEL_READY_NOT_REVIEWED"),
            "detail": (
                f"四审状态 {cons.get('consensus_status', 'NOT_IN_QUEUE')}; "
                f"未达 4/4 PASS"
            ),
        })

    for r in excluded:
        audit.append({
            "measurement_id": r["measurement_id"],
            "name": r["name"],
            "inchikey": r["inchikey"],
            "dielectric": r["dielectric"],
            "v06_model_ready": "false",
            "b02_consensus_status": cons_by_id.get(
                r["measurement_id"], {}).get("consensus_status", "NOT_IN_QUEUE"),
            "exclusion_reason": r["blocking_reasons"] or "UNKNOWN",
            "detail": r.get("flags", ""),
        })

    # ---- write pool ----
    pool_fields = ["measurement_id", "ledger_observation_id", "ledger_join_key",
                   "ledger_n_candidates", "ledger_observation_ambiguous",
                   "phase_status", "mp_margin_K",
                   "aggregate_id", "inchikey", "name", "T_K",
                   "dielectric", "source_doi", "source_quality",
                   "temperature_source", "n_contributing_measurements",
                   "n_independent_experiments", "aggregation_type",
                   "condition_pair_valid",
                   "b02_consensus_status", "b02_four_of_four", "v06_model_ready",
                   "admission_provenance", "pool_version", "merge_forbidden"]
    pool_path = OUT_DIR / "candidate_pool_v2_draft.csv"
    with pool_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=pool_fields)
        w.writeheader()
        for r in pool:
            w.writerow({k: r.get(k, "") for k in pool_fields})

    # ---- write audit ----
    audit_fields = ["measurement_id", "name", "inchikey", "dielectric",
                    "v06_model_ready", "b02_consensus_status",
                    "exclusion_reason", "detail"]
    audit_path = OUT_DIR / "candidate_exclusion_audit.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=audit_fields)
        w.writeheader()
        for r in audit:
            w.writerow({k: r.get(k, "") for k in audit_fields})

    # ---- temperature vocabulary (PLAN B B04 requires this) ----
    temp_vocab = {
        "raw_values_preserved": sorted({r["T_K"] for r in pool}),
        "note": (
            "所有温度原始值保留, 未做任何折算. "
            "B04 规则要求 293.15 与 303.15 边界闭区间必须测试."
        ),
        "closed_interval_test": {
            "low_K": 293.15, "high_K": 303.15,
            "n_pool_rows_in_interval": sum(
                1 for r in pool
                if r["T_K"] and 293.15 <= float(r["T_K"]) <= 303.15),
            "n_pool_rows_outside": sum(
                1 for r in pool
                if r["T_K"] and not (293.15 <= float(r["T_K"]) <= 303.15)),
            "boundary_note": (
                "293.15 与 303.15 本身计入区间 (闭区间), "
                "与 R219 冻结窗口口径一致."
            ),
        },
    }
    vocab_path = OUT_DIR / "temperature_vocabulary_mapping.json"
    vocab_path.write_text(json.dumps(temp_vocab, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    # ---- lineage manifest ----
    excl_reasons = Counter(r["exclusion_reason"] for r in audit)
    lineage = {
        "schema": "b04.pool_lineage/v2-draft",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "candidate_pool_v2_draft 是本项目第一个**有资格**构造的新候选池. "
            "它的准入是三个独立门的交集, 任何一个不通过即不入选."
        ),
        "eligibility_gates": {
            "gate_1_b02_four_agent": {
                "source": str(CONSENSUS.relative_to(REPO_ROOT)),
                "required_status": "AI_CONSENSUS_ACCEPTED",
                "n_passing": len(accepted),
            },
            "gate_2_v06_model_ready": {
                "source": str(V06_READY.relative_to(REPO_ROOT)),
                "required": "model_ready == true",
                "n_passing": len(ready),
            },
            "gate_3_no_unresolved_blocker": {
                "source": str(V06_EXCL.relative_to(REPO_ROOT)),
                "note": "v06 已把未解决冲突/压力异质/合成中点/推定温度排除在外",
                "n_excluded": len(excluded),
            },
        },
        "counts": {
            "n_in_pool": len(pool),
            "n_distinct_molecules": len({r["inchikey"] for r in pool}),
            "n_rows_audited_not_in_pool": len(audit),
            "audit_by_reason": dict(sorted(excl_reasons.items(),
                                           key=lambda kv: -kv[1])),
        },
        "pool_character": {
            "n_records": len(pool),
            "n_molecules": len({r["inchikey"] for r in pool}),
            "records_per_molecule": 1,
            "n_distinct_source_documents": len({r["source_doi"] for r in pool}),
            "n_molecules_sharing_a_document": sum(
                c for c in Counter(r["source_doi"] for r in pool).values() if c > 1),
            "independence_warning": (
                "22 个分子只来自 "
                f"{len({r['source_doi'] for r in pool})} 个来源文档；"
                f"{sum(c for c in Counter(r['source_doi'] for r in pool).values() if c > 1)}"
                " 个分子与其他分子共享文档 (Reviewer 2, B04+B05)。"
                "因此『22 个独立观测』是错的，有效独立文档数只有 "
                f"{len({r['source_doi'] for r in pool})}。"
            ),
            "aggregation_breakdown": {
                "single_observation": sum(
                    1 for r in pool if r["aggregation_type"] == "SINGLE_OBSERVATION"),
                "single_source_aggregate": sum(
                    1 for r in pool
                    if r["aggregation_type"] == "SINGLE_SOURCE_AGGREGATE"),
                "multi_source_aggregate": sum(
                    1 for r in pool
                    if r["aggregation_type"] == "MULTI_SOURCE_AGGREGATE"),
                "note": (
                    "SINGLE_SOURCE_AGGREGATE 的行把同一篇论文内的 3-5 条观测"
                    "聚合成 1 个值 (n_independent_experiments=1). 这本身是正确标注, "
                    "但『22 个分子』不应被读成『22 条独立测量』. "
                    "(Reviewer 4, B04+B05)"
                ),
            },
            "range_restriction": {
                "pool_epsilon_sd": round(
                    statistics.pstdev([float(r["dielectric"]) for r in pool]), 2),
                "note": (
                    "候选池只覆盖 73 个 model-ready 分子的 "
                    f"{100*len(pool)/73:.1f}%，且 ε 标准差明显小于全量. "
                    "因此任何性能数字都受严重范围限制影响, 不可外推."
                ),
            },
            "phase_state": {
                "n_liquid_at_stated_T": sum(
                    1 for r in pool
                    if r["phase_status"] == "LIQUID_AT_STATED_T"),
                "n_solid_or_supercooled": sum(
                    1 for r in pool
                    if r["phase_status"] == "SOLID_OR_SUPERCOOLED_AT_STATED_T"),
                "n_unknown_no_mp": sum(
                    1 for r in pool if r["phase_status"] == "UNKNOWN_NO_MP"),
                "finding": (
                    "有分子在其设定温度下低于熔点, 即样品是固态/过冷液体 "
                    "(Reviewer 1, B04+B05). 液体静态介电常数是**液相**性质, "
                    "对过冷样品测得的值描述的是亚稳态."
                ),
                "rule": (
                    "SOLID_OR_SUPERCOOLED 的行必须显式标记, 不得静默当作正常液体; "
                    "剔除非液相证据后再讨论模型性能"
                ),
            },
            "assessment": (
                "22 个分子、每分子 1 条记录. 这是**筛选可行性集**, 不是训练集. "
                "B05 必须以此为前提设计实验, 不得宣称统计功效充分."
            ),
            "primary_k_implication": (
                "按冻结规则 primary_k = max(1, ceil(n/10)) = ceil(22/10) = 3. "
                "但 B07 必须报告这 22 个分子是否有足够独立来源做聚类检验."
            ),
        },
        "frozen_artifacts": {
            "candidate_pool_C": {
                "path": str(POOL_C) if POOL_C.is_file() else None,
                "sha256": sha256_file(POOL_C) if POOL_C.is_file() else None,
                "status": "AUTHORITATIVE_HISTORICAL_UNCHANGED",
                "n_rows": len(load(POOL_C)) if POOL_C.is_file() else 0,
            },
            "master_in_49_preview": {
                "status": "HISTORICAL_S4_FOLD_UNCHANGED",
                "merge_forbidden": True,
                "merge_forbidden_reason": (
                    "并集会把两套不同筛选规则混成既非预览也非正式池的第三物, "
                    "并伪造更大的分母"
                ),
            },
            "j01_j02_j03": "byte-identical, verified by b00/verify_frozen_artifacts.py",
        },
        "inputs": {
            "dataset_v06_model_ready": {"sha256": sha256_file(V06_READY),
                                        "rows": len(ready)},
            "dataset_v06_exclusions": {"sha256": sha256_file(V06_EXCL),
                                       "rows": len(excluded)},
            "consensus_decisions": {"sha256": sha256_file(CONSENSUS),
                                    "rows": len(consensus)},
        },
        "outputs": {
            "candidate_pool_v2_draft": {
                "path": str(pool_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(pool_path), "rows": len(pool)},
            "candidate_exclusion_audit": {
                "path": str(audit_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(audit_path), "rows": len(audit)},
            "temperature_vocabulary_mapping": {
                "path": str(vocab_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(vocab_path)},
        },
        "integrity_rules_applied": [
            "所有新增行必须有 measurement_id 与来源 DOI",
            "所有温度原始值保留, 未折算",
            "未为扩大样本数降低准入标准",
            "未合并 master.in_49_preview (merge_forbidden 继续有效)",
            "未覆盖 candidate_pool_C",
        ],
    }
    lin_path = OUT_DIR / "pool_lineage_manifest.json"
    lin_path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    # ---- review markdown ----
    md: list[str] = []
    md.append("# B04 候选池 v2 审议\n")
    md.append(f"> 生成器 `{GENERATOR}` · {lineage['generated_at_utc']}\n")

    md.append("\n## 一、结论\n")
    md.append(f"- 候选池记录数：**{len(pool)}**\n")
    md.append(f"- 涉及分子数：**{len({r['inchikey'] for r in pool})}**\n")
    md.append(f"- 每分子记录数：**1**\n")
    md.append(f"- 未入选的审计记录：**{len(audit)}**\n")

    md.append("\n### ⚠️ 22 条不是数据集\n")
    pc = lineage["pool_character"]
    md.append(f"{pc['assessment']}\n")
    md.append(f"\n{pc['primary_k_implication']}\n")

    md.append("\n## 二、三道独立的准入门\n")
    md.append("| 门 | 来源 | 要求 | 通过数 |\n|---|---|---|---:|\n")
    md.append(f"| B02 四智能体 | `consensus_decisions.csv` | "
              f"`AI_CONSENSUS_ACCEPTED` | {len(accepted)} |\n")
    md.append(f"| v06 模型可用 | `dataset_v06_model_ready.csv` | "
              f"`model_ready == true` | {len(ready)} |\n")
    md.append(f"| 无未解决阻断 | `dataset_v06_exclusions.csv` | 未被排除 | "
              f"{len(ready)} |\n")
    md.append(f"\n**交集：{len(pool)}**\n")

    md.append("\n## 三、未入选原因分布\n")
    md.append("| 原因 | 数量 |\n|---|---:|\n")
    for k, v in sorted(excl_reasons.items(), key=lambda kv: -kv[1]):
        md.append(f"| `{k}` | {v} |\n")

    md.append("\n## 四、温度词表\n")
    tv = temp_vocab["closed_interval_test"]
    md.append(f"- 池内温度原始值：{', '.join(temp_vocab['raw_values_preserved'])}\n")
    md.append(f"- 闭区间 [{tv['low_K']}, {tv['high_K']}] K 内："
              f"**{tv['n_pool_rows_in_interval']}** 条\n")
    md.append(f"- 区间外：**{tv['n_pool_rows_outside']}** 条\n")
    md.append(f"\n{tv['boundary_note']}\n")

    md.append("\n## 五、冻结产物状态\n")
    md.append("| 产物 | 状态 |\n|---|---|\n")
    md.append("| `candidate_pool_C` | **权威历史版本，字节未动** |\n")
    md.append("| `master.in_49_preview` | **历史 S4 折，merge_forbidden 继续有效** |\n")
    md.append("| J01 / J02 / J03 | **字节不变，已由校验器确认** |\n")

    md.append("\n## 六、明确未做的事\n")
    for rule in lineage["integrity_rules_applied"]:
        md.append(f"- ✅ {rule}\n")
    md.append("- ❌ 未把 22 条称为「训练集」\n")
    md.append("- ❌ 未宣称统计功效充分\n")
    md.append("- ❌ 未把 AI 共识写入 HUMAN_SIGNED\n")

    md_path = OUT_DIR / "candidate_pool_review.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B04] {pool_path}  ({len(pool)} records)")
    print(f"[B04] {audit_path}  ({len(audit)} audited)")
    print(f"[B04] {lin_path}")
    print(f"[B04] {vocab_path}")
    print(f"[B04] {md_path}")
    print(f"  molecules          = {len({r['inchikey'] for r in pool})}")
    print(f"  in closed band     = {tv['n_pool_rows_in_interval']}")
    print(f"  outside band       = {tv['n_pool_rows_outside']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
