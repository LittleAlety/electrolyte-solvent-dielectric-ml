#!/usr/bin/env python
"""B02-CONFLICT: fold the gamma-valerolactone adjudication into the main consensus.

The main consensus gate covers the admission queue. This script handles the one
unresolved source conflict that Reviewer 4 found had been excluded from review,
and merges its verdict into `consensus_decisions.csv` so there is a single
authoritative record of what was admitted.

Design rules carried over unchanged from the main gate:
  * 4/4 PASS required; any HOLD or FAIL blocks
  * no majority vote
  * AI consensus is never written as HUMAN_SIGNED
  * a record nobody reviewed stays INCOMPLETE, it does not disappear

The one addition: an unresolved conflict has a *fifth* possible outcome that
ordinary admission does not -- "the conflict itself is the finding". If the four
reviewers agree the two values cannot be reconciled from available evidence, the
correct state is not REJECTED (which implies we know the record is wrong) but
CONFLICT_UNRESOLVED, which records that we know we do not know.

Output: outputs/admission_v2/gvl_conflict_consensus.csv
        outputs/admission_v2/gvl_conflict_consensus.json
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
OUT_DIR = REPO_ROOT / "outputs" / "admission_v2"
GENERATOR = "build_gvl_conflict_consensus/1.0.0"

REVIEWER_FILES = {
    "R1": "reviewer_1_gvl_decisions.csv",
    "R2": "reviewer_2_gvl_decisions.csv",
    "R3": "reviewer_3_gvl_decisions.csv",
    "R4": "reviewer_4_gvl_decisions.csv",
}
EXPECTED_QIDS = ["Q-CONF-EPSV04-R227", "Q-CONF-EPSV04-R248"]
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
    problems: list[str] = []
    meta: dict[str, dict] = {}

    for label, fname in REVIEWER_FILES.items():
        p = OUT_DIR / fname
        if not p.is_file():
            problems.append(f"{label}: 缺少文件 {fname}")
            decisions[label] = {}
            meta[label] = {"present": False, "rows": 0, "sha256": None,
                           "counts": {}}
            continue
        rows = load(p)
        by_qid = {(r.get("queue_id") or "").strip(): r for r in rows}
        decisions[label] = by_qid
        meta[label] = {
            "present": True,
            "rows": len(by_qid),
            "sha256": sha256_file(p),
            "counts": dict(Counter(
                (r.get("decision") or "").strip().upper() for r in rows)),
        }
        for q in EXPECTED_QIDS:
            if q not in by_qid:
                problems.append(f"{label}: 未覆盖 {q}")
            else:
                d = (by_qid[q].get("decision") or "").strip().upper()
                if d not in VALID:
                    problems.append(f"{label}: {q} 的 decision={d!r} 非法")

    # ---- per-record consensus ----
    rows_out: list[dict] = []
    tally = Counter()

    for qid in EXPECTED_QIDS:
        votes = {}
        for label in REVIEWER_FILES:
            rec = decisions[label].get(qid)
            votes[label] = ((rec or {}).get("decision") or "MISSING").strip().upper()

        n_pass = sum(1 for v in votes.values() if v == "PASS")
        n_hold = sum(1 for v in votes.values() if v == "HOLD")
        n_fail = sum(1 for v in votes.values() if v == "FAIL")
        missing = [k for k, v in votes.items() if v == "MISSING"]

        # The recommended resolution each reviewer proposed. Reviewers were asked
        # for different auxiliary columns (R3 reports `authoritative_value`
        # instead), so a missing column is reported rather than silently treated
        # as agreement.
        def field(label: str, col: str) -> str:
            return ((decisions[label].get(qid) or {}).get(col) or "").strip()

        resolutions = []
        for k in REVIEWER_FILES:
            v = field(k, "recommended_resolution")
            if v:
                resolutions.append(v)
        res_tally = Counter(resolutions)
        # Unanimity requires ALL FOUR to state the same resolution; two of four
        # agreeing is not unanimity.
        unanimous_resolution = (
            resolutions[0]
            if len(resolutions) == len(REVIEWER_FILES)
            and len(set(resolutions)) == 1 else "")

        if missing:
            status = "AI_CONSENSUS_INCOMPLETE"
            reason = f"缺少评审: {','.join(missing)}"
        elif n_fail > 0:
            status = "AI_CONSENSUS_REJECTED"
            reason = f"{n_fail} 位 FAIL (4/4 PASS 未达成)"
        elif n_hold > 0:
            status = "AI_CONSENSUS_HOLD"
            reason = f"{n_hold} 位 HOLD (4/4 PASS 未达成)"
        elif n_pass == 4:
            status = "AI_CONSENSUS_ACCEPTED"
            reason = "4/4 PASS"
        else:
            status = "AI_CONSENSUS_HOLD"
            reason = "未达成 4/4 PASS"

        # A conflict whose reviewers all say "we need the primary document" is
        # not rejected -- it is explicitly unresolved. That distinction matters:
        # REJECTED means "we know it is wrong"; UNRESOLVED means "we know we
        # cannot know". Collapsing them would overstate our knowledge.
        if (status != "AI_CONSENSUS_ACCEPTED"
                and unanimous_resolution == "NEEDS_PRIMARY_DOCUMENT"):
            status = "CONFLICT_UNRESOLVED_NEEDS_PRIMARY_DOCUMENT"
            reason = "四位一致: 需回原始文献才能裁决; 现有证据不足以定值"

        tally[status] += 1

        rows_out.append({
            "queue_id": qid,
            "measurement_id": qid.replace("Q-CONF-", ""),
            "r1_decision": votes["R1"],
            "r2_decision": votes["R2"],
            "r3_decision": votes["R3"],
            "r4_decision": votes["R4"],
            "n_pass": n_pass,
            "n_hold": n_hold,
            "n_fail": n_fail,
            "consensus_status": status,
            "consensus_reason": reason,
            "r1_resolution": field("R1", "recommended_resolution"),
            "r2_resolution": field("R2", "recommended_resolution"),
            "r3_resolution": field("R3", "recommended_resolution"),
            "r4_resolution": field("R4", "recommended_resolution"),
            "r3_authoritative_value": field("R3", "authoritative_value"),
            "r3_code_defect_found": field("R3", "code_defect_found"),
            "unanimous_resolution": unanimous_resolution,
            "resolution_votes": ";".join(
                f"{k}={v}" for k, v in sorted(res_tally.items())),
            "r1_evidence": field("R1", "evidence_detail"),
            "r2_evidence": field("R2", "evidence_detail"),
            "r3_evidence": field("R3", "evidence_detail"),
            "r4_evidence": field("R4", "evidence_detail"),
            "provenance_class": "AI_CONSENSUS_NOT_HUMAN_SIGNED",
        })

    csv_path = OUT_DIR / "gvl_conflict_consensus.csv"
    if rows_out:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            for r in rows_out:
                w.writerow(r)

    doc = {
        "schema": "admission_v2.gvl_conflict_consensus/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "subject": {
            "compound": "gamma-valerolactone (γ-pentanolactone)",
            "inchikey": "GAEKPEKOJKCEMS-UHFFFAOYSA-N",
            "temperature_K": "298.15",
            "conflicting_values": {
                "EPSV04-R227": {"epsilon": "36.1",
                                "doi": "10.1016/j.isci.2026.115778"},
                "EPSV04-R248": {"epsilon": "36.9",
                                "doi": "10.1016/j.ica.2021.120372"},
            },
            "why_it_matters": (
                "Reviewer 4 (B02) 发现该冲突**未进入**审核队列 —— 被排除而非被裁决. "
                "未裁决的冲突若进入 B05, 会被当作两条独立观测, 凭空放大样本量并引入标签噪声."
            ),
        },
        "reviewers": meta,
        "structural_problems": problems,
        "consensus": dict(sorted(tally.items())),
        "records": rows_out,
        "outcome_semantics": {
            "AI_CONSENSUS_ACCEPTED": "4/4 PASS, 可直接作为候选",
            "AI_CONSENSUS_REJECTED": "至少一位 FAIL; 已知该记录不可用",
            "AI_CONSENSUS_HOLD": "至少一位 HOLD; 需补证据",
            "CONFLICT_UNRESOLVED_NEEDS_PRIMARY_DOCUMENT": (
                "四位一致认为现有证据不足以定值, 需回原始文献. "
                "这不是 REJECTED —— REJECTED 意味着我们**知道**它错; "
                "本状态意味着我们**知道自己不知道**. 两者不可混为一谈."
            ),
        },
        "hard_constraints": [
            "不得对 36.1 与 36.9 取平均",
            "不得择一作为主值而不回原文",
            "不得把 AI 共识写入 HUMAN_SIGNED",
            "在裁决前, 该分子不得进入 B04 候选池",
        ],
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path) if csv_path.is_file() else None,
                   "rows": len(rows_out)},
    }
    json_path = OUT_DIR / "gvl_conflict_consensus.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B02-CONFLICT] {csv_path}  ({len(rows_out)} records)")
    print(f"[B02-CONFLICT] {json_path}")
    for label, m in meta.items():
        print(f"  {label} present={m['present']} rows={m['rows']} {m['counts']}")
    print("  consensus:", dict(sorted(tally.items())))
    if problems:
        print("  PROBLEMS:")
        for p in problems:
            print("   -", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
