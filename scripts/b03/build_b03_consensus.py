#!/usr/bin/env python
"""B03-5: fold the four-agent review into a B03 consensus decision.

The four reviewers split on EA/MA: R1 and R3 PASS the *values*, R2 and R4 HOLD
because the provenance is weaker than the first two treated it as. Under the
project's rule (4/4 PASS required, no majority vote) that is a HOLD -- but a HOLD
with a precise, actionable reason is worth more than a vague PASS.

This script records the split honestly and separates two things that are easy to
conflate:

    the VALUES are reproducible and chemically sound   (R1, R3)
    the PROVENANCE is single-source and circular       (R2, R4)

Both can be true at once. The output states which is which so B04 does not
mistake "the number is right" for "the evidence is strong".

Output: outputs/confirm_2027/evidence_backfill/b03_consensus_decisions.csv
        outputs/confirm_2027/evidence_backfill/b03_consensus.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
GENERATOR = "build_b03_consensus/1.0.0"

REVIEWERS = {
    "R1": "b03_reviewer_1_decisions.csv",
    "R2": "b03_reviewer_2_decisions.csv",
    "R3": "b03_reviewer_3_decisions.csv",
    "R4": "b03_reviewer_4_decisions.csv",
}
TARGETS = {"C11": "EA", "C12": "MA"}
VALID = {"PASS", "HOLD", "FAIL"}


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

    decisions: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}
    problems: list[str] = []

    for label, fname in REVIEWERS.items():
        p = OUT_DIR / fname
        if not p.is_file():
            problems.append(f"{label}: 缺少 {fname}")
            decisions[label] = {}
            meta[label] = {"present": False, "rows": 0, "sha256": None}
            continue
        rows = load(p)
        # R3 and R4 also emit package-level rows (a_mol_id == "ALL"); keep only
        # the per-molecule decisions for the consensus and report the rest.
        by_id = {(r.get("a_mol_id") or "").strip(): r for r in rows}
        decisions[label] = by_id
        meta[label] = {
            "present": True,
            "rows": len(rows),
            "per_molecule_rows": sum(1 for r in rows
                                     if (r.get("a_mol_id") or "") in TARGETS),
            "package_level_rows": sum(1 for r in rows
                                      if (r.get("a_mol_id") or "") == "ALL"),
            "sha256": sha256_file(p),
            "decision_counts": dict(Counter(
                (r.get("decision") or "").strip().upper() for r in rows)),
        }
        for mid in TARGETS:
            if mid not in by_id:
                problems.append(f"{label}: 未覆盖 {mid}")
            else:
                d = (by_id[mid].get("decision") or "").strip().upper()
                if d not in VALID:
                    problems.append(f"{label}: {mid} decision={d!r} 非法")

    out_rows: list[dict] = []
    tally: Counter = Counter()

    for mid, name in TARGETS.items():
        votes = {}
        for label in REVIEWERS:
            rec = decisions[label].get(mid)
            votes[label] = ((rec or {}).get("decision") or "MISSING").strip().upper()

        n_pass = sum(1 for v in votes.values() if v == "PASS")
        n_hold = sum(1 for v in votes.values() if v == "HOLD")
        n_fail = sum(1 for v in votes.values() if v == "FAIL")
        missing = [k for k, v in votes.items() if v == "MISSING"]

        if missing:
            status = "AI_CONSENSUS_INCOMPLETE"
            reason = f"缺少评审: {','.join(missing)}"
        elif n_fail:
            status = "AI_CONSENSUS_REJECTED"
            reason = f"{n_fail} 位 FAIL"
        elif n_hold:
            status = "AI_CONSENSUS_HOLD"
            reason = (f"{n_hold} 位 HOLD (4/4 PASS 未达成). "
                      f"分裂点: R1/R3 认可**数值**, R2/R4 质疑**溯源**")
        elif n_pass == 4:
            status = "AI_CONSENSUS_ACCEPTED"
            reason = "4/4 PASS"
        else:
            status = "AI_CONSENSUS_HOLD"
            reason = "未达成 4/4 PASS"

        tally[status] += 1

        def field(label: str, col: str) -> str:
            return ((decisions[label].get(mid) or {}).get(col) or "").strip()

        out_rows.append({
            "a_mol_id": mid,
            "a_name": name,
            "r1_decision": votes["R1"],
            "r2_decision": votes["R2"],
            "r3_decision": votes["R3"],
            "r4_decision": votes["R4"],
            "n_pass": n_pass,
            "n_hold": n_hold,
            "n_fail": n_fail,
            "consensus_status": status,
            "consensus_reason": reason,
            # The two axes that the split is really about.
            "value_reproducible": field("R3", "recompute_match"),
            "value_recomputed": field("R3", "value_recomputed"),
            "chemistry_plausible": field("R1", "chemistry_plausible"),
            "phase_physical": field("R1", "phase_physical"),
            "source_is_primary": field("R2", "source_is_primary"),
            "doi_verified": field("R2", "doi_verified"),
            "is_genuinely_new": field("R4", "is_genuinely_new"),
            "adversarial_finding": field("R4", "adversarial_finding"),
            "may_enter_b04": "false",
            "b04_blocking_reason": (
                "未达 4/4 PASS; 且 EA/MA 各自 SINGLE_SOURCE, 两者共享 NBS514 ref 63, "
                "不构成两个独立观测"
            ),
            "provenance_class": "AI_CONSENSUS_NOT_HUMAN_SIGNED",
        })

    csv_path = OUT_DIR / "b03_consensus_decisions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    doc = {
        "schema": "confirm_2027.b03_consensus/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reviewers": meta,
        "structural_problems": problems,
        "consensus": dict(sorted(tally.items())),
        "records": out_rows,
        "split_analysis": {
            "finding": (
                "四位评审的分裂不在数值上, 而在**溯源强度**上. "
                "R1 与 R3 都独立复核了 ε=6.02/6.68 并判 PASS; "
                "R2 与 R4 判 HOLD, 理由是 NBS514 是 1951 年二手汇编、"
                "EA/MA 共享参考文献 63、且 v04 值与页面读取同源."
            ),
            "why_hold_not_pass": (
                "按 PLAN B「4/4 PASS」规则, 任一 HOLD 即不得通过. "
                "这正确反映了证据状态: 数值可信, 但不足以支撑"
                "「两条独立来源的测量」这一更强的主张."
            ),
            "why_not_reject": (
                "没有任何一位判 FAIL 认为数值错误; R4 的 FAIL 是针对**整包**"
                "（INFLATED_RESOLVED_COUNT），不是针对 EA/MA 的 ε 值本身."
            ),
        },
        "agreed_facts": [
            "ε=6.02 (EA) 与 ε=6.68 (MA) 可由 NBS514 页面读取复现 (R1/R3 独立确认, R3 另用 PDF 抽取验证)",
            "两者均为 298.15 K 液态单组分酯, 化学上合理",
            "NBS Circular 514 是二手汇编, 不是原始测量 (R2 引原文 §2.6 证明)",
            "EA 与 MA 共享 NBS514 参考文献 63 (Williams & Krchma, JACS 49, 1676, 1927)",
            "EA/MA 的值早已存在于 dielectric_v04.csv (dataset_origin=v0.2), B03 未新增观测",
            "v04 的 source_record_id 与本次页面读取相同, 故『一致』是转录完整性而非独立佐证",
        ],
        "hard_constraints": [
            "不得把 EA/MA 当作两个独立来源参与 B07 来源聚类",
            "不得把 epsilon_agrees=true 引用为独立佐证",
            "不得声称 B03 增加了样本量",
            "不得把 AI 共识写入 HUMAN_SIGNED",
        ],
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(out_rows)},
    }
    json_path = OUT_DIR / "b03_consensus.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B03-5] {csv_path}  ({len(out_rows)} records)")
    print(f"[B03-5] {json_path}")
    for label, m in meta.items():
        print(f"  {label} present={m['present']} rows={m.get('rows')} "
              f"{m.get('decision_counts')}")
    print("  consensus:", dict(sorted(tally.items())))
    if problems:
        for p in problems:
            print("   PROBLEM:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
