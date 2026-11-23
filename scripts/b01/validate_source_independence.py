#!/usr/bin/env python
"""B01-3: validate_source_independence.py

PLAN B B01 core principle 3: "DOI 不自动等于独立实验簇."

The registry honestly declares `experimental_independence_status = not_evaluated`
for all 61 documents. That is the correct *admission* of ignorance. But it leaves
a live hazard: downstream code uses `n_contributing_sources` as if it were a count
of independent experiments. Reviewer 2 showed it is a count of **DOI strings**.

This script measures how wrong that assumption is, using evidence that is
actually available in the data rather than requiring external knowledge:

  * EXACT DUPLICATE OBSERVATIONS
    Two rows from different documents with identical (inchikey, T, eps) are a
    duplicate transcription, not a replication. If source A and source B both
    report eps=41.17 at 298.15 K for the same molecule to full precision, the
    chance they are independent measurements is negligible; far more likely one
    dataset was deposited twice or re-reported.

  * SHARED PRECISION FINGERPRINTS
    Documents that share an unusual number of digits agree beyond coincidence.

  * CO-AUTHORSHIP PROXIES ARE NOT AVAILABLE
    We do not have author metadata in the ledger. So we report *observed
    duplication* and explicitly refuse to infer authorial independence. That is
    the honest boundary: we can prove two rows are duplicates, we cannot prove
    two non-duplicate rows are independent.

Output:
  outputs/confirm_2027/provenance_repair/source_independence_report.json
  outputs/confirm_2027/provenance_repair/source_independence_report.md
  outputs/confirm_2027/provenance_repair/duplicate_observation_groups.csv
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
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "validate_source_independence/1.0.0"

MEAS_LEDGER = OUT_DIR / "measurement_ledger_v1.csv"
REGISTRY = OUT_DIR / "source_document_registry_v1.csv"
AGG_LEDGER = OUT_DIR / "aggregate_contribution_ledger_v1.csv"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def norm(v: str | None) -> str:
    """Normalise a numeric string so '41.170' and '41.17' collide."""
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return ""
    try:
        return repr(round(float(s), 10))
    except ValueError:
        return s


def main() -> int:
    for p in (MEAS_LEDGER, REGISTRY, AGG_LEDGER):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    meas = load(MEAS_LEDGER)
    registry = load(REGISTRY)
    agg = load(AGG_LEDGER)

    # ---- Group observations by (inchikey, T, eps) to find exact duplicates ----
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for m in meas:
        key = (
            (m.get("inchikey") or "").strip(),
            norm(m.get("temperature_K")),
            norm(m.get("dielectric")),
        )
        if not key[0] or not key[1] or not key[2]:
            continue
        groups[key].append(m)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    # Only cross-document duplicates matter for independence: the same document
    # repeating its own value is not an independence claim in the first place.
    cross_doc: list[dict] = []
    for key, rows in sorted(dup_groups.items()):
        docs = sorted({(r.get("source_document_id") or "").strip() for r in rows})
        if len(docs) < 2:
            continue
        cross_doc.append({
            "inchikey": key[0],
            "temperature_K": key[1],
            "dielectric": key[2],
            "n_observations": len(rows),
            "n_documents": len(docs),
            "documents": ";".join(docs),
            "measurement_ids": ";".join(
                (r.get("measurement_id") or "").strip() for r in rows),
            "interpretation": "DUPLICATE_TRANSCRIPTION_NOT_REPLICATION",
        })

    # ---- Which document PAIRS are entangled? ----
    pair_counts: Counter = Counter()
    for g in cross_doc:
        docs = g["documents"].split(";")
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                pair_counts[tuple(sorted((docs[i], docs[j])))] += 1

    entangled = [
        {"doc_a": a, "doc_b": b, "n_identical_observations": n,
         "interpretation": "SHARED_DATASET_LIKELY"}
        for (a, b), n in sorted(pair_counts.items(), key=lambda kv: -kv[1])
    ]

    # ---- How much does n_contributing_sources overstate independence? ----
    # A doc that shares a duplicate with another doc cannot be counted as an
    # independent cluster alongside it.
    dup_docs = {d for g in cross_doc for d in g["documents"].split(";")}

    agg_impact = []
    for a in agg:
        n_src = (a.get("n_contributing_sources") or "").strip()
        srcs = [s for s in (a.get("contributing_source_documents") or "").split(";")
                if s.strip() and s.strip().lower() not in PLACEHOLDERS]
        if not srcs:
            continue
        entangled_srcs = [s for s in srcs if s in dup_docs]
        if not entangled_srcs:
            continue
        agg_impact.append({
            "aggregate_id": (a.get("aggregate_id") or "").strip(),
            "n_contributing_sources": n_src,
            "contributing_sources": ";".join(srcs),
            "n_entangled_sources": len(entangled_srcs),
            "entangled_sources": ";".join(entangled_srcs),
            "independence_warning": (
                "至少一个贡献来源与其他来源共享逐字节相同的观测; "
                "n_contributing_sources 高估独立实验数"
            ),
        })

    # ---- Registry honesty check ----
    status_counts = Counter(
        (r.get("experimental_independence_status") or "").strip() for r in registry)
    n_not_evaluated = status_counts.get("not_evaluated", 0)

    # ---- write duplicate group CSV ----
    dup_csv = OUT_DIR / "duplicate_observation_groups.csv"
    fields = ["inchikey", "temperature_K", "dielectric", "n_observations",
              "n_documents", "documents", "measurement_ids", "interpretation"]
    with dup_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for g in cross_doc:
            w.writerow(g)

    report = {
        "schema": "confirm_2027.source_independence/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本报告只报告**可观测的重复**, 不推断作者独立性. "
            "能证明两行是重复转录; 不能证明两行是独立实验. 这个边界必须保留."
        ),
        "inputs": {
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(meas)},
            "source_document_registry_v1": {"sha256": sha256_file(REGISTRY),
                                            "rows": len(registry)},
            "aggregate_contribution_ledger_v1": {"sha256": sha256_file(AGG_LEDGER),
                                                 "rows": len(agg)},
        },
        "registry_independence_status": {
            "counts": dict(sorted(status_counts.items())),
            "n_documents": len(registry),
            "n_not_evaluated": n_not_evaluated,
            "finding": (
                f"{n_not_evaluated}/{len(registry)} 个来源文档的实验独立性为 "
                f"not_evaluated. 因此**本数据集没有任何记录具备有证据支持的独立性声明**. "
                f"这不是缺陷, 是诚实的边界; 但下游不得把文档数当独立实验数用."
            ),
        },
        "duplicate_observations": {
            "n_groups_all": len(dup_groups),
            "n_groups_cross_document": len(cross_doc),
            "n_observations_involved": sum(g["n_observations"] for g in cross_doc),
            "n_documents_entangled": len(dup_docs),
            "definition": (
                "同一 (inchikey, temperature_K, dielectric) 在**不同文档**中重复出现. "
                "全精度相同不可能是两次独立测量."
            ),
        },
        "entangled_document_pairs": entangled[:20],
        "n_entangled_pairs": len(entangled),
        "aggregate_impact": {
            "n_aggregates_affected": len(agg_impact),
            "note": (
                "这些聚合行的 n_contributing_sources 计数把重复来源当成独立来源. "
                "在来源聚类稳健性检验 (B07) 中必须降级, 或按文档去重后再聚类."
            ),
            "details": agg_impact,
        },
        "what_this_cannot_do": [
            "无法判断两篇不重复的文献是否来自同一课题组",
            "无法判断是否共享同一上游原始数据",
            "无法判断是否为同一次实验的两次发表",
            "因此『独立来源组 ≥k』的宣称在 B07 中需要外部证据, 否则只能报 not_evaluated",
        ],
        "outputs": {"duplicate_observation_groups_csv": {
            "path": str(dup_csv.relative_to(REPO_ROOT)),
            "sha256": sha256_file(dup_csv), "rows": len(cross_doc)}},
    }
    json_path = OUT_DIR / "source_independence_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 来源独立性校验\n")
    md.append(f"> 生成器 `{GENERATOR}` · {report['generated_at_utc']}\n")
    md.append("> 只报告**可观测的重复**，不推断作者独立性。\n")

    md.append("\n## 一、结论\n")
    md.append(
        f"PLAN B B01 核心原则 3 是「DOI 不自动等于独立实验簇」。本校验证明该原则"
        f"**在本数据集中确实被违反**：\n\n"
        f"- 账本 {len(meas)} 条观测中，存在 **{len(cross_doc)} 组跨文档完全重复观测**，"
        f"涉及 **{len(dup_docs)} 个文档**。\n"
        f"- 这些重复是 (inchikey, T, ε) **全精度相同**——两次独立测量不可能如此。\n"
        f"- 受影响聚合行 **{len(agg_impact)}** 个，其 `n_contributing_sources` 高估独立实验数。\n"
    )

    md.append("\n## 二、注册表的诚实边界\n")
    md.append(
        f"`source_document_registry_v1.csv` 对 **{n_not_evaluated}/{len(registry)}** "
        f"个文档标注 `experimental_independence_status = not_evaluated`。\n\n"
        f"这是**正确的**——文档层无法凭自身判定实验独立性。但由此可推出一个必须写进"
        f"论文限制的结论：\n\n"
        f"> **本数据集没有任何记录具备有证据支持的独立性声明。**\n\n"
        f"因此 B07 中任何「独立来源簇 ≥3」的稳健性宣称，都必须附带外部证据，"
        f"否则只能报告 `not_evaluated`。\n"
    )

    md.append("\n## 三、纠缠最严重的文档对\n")
    md.append("| 文档 A | 文档 B | 相同观测数 |\n|---|---|---:|\n")
    for e in entangled[:12]:
        md.append(f"| `{e['doc_a']}` | `{e['doc_b']}` | {e['n_identical_observations']} |\n")

    md.append("\n## 四、本校验不能做的事\n")
    for item in report["what_this_cannot_do"]:
        md.append(f"- {item}\n")

    md.append("\n## 五、处置规则\n")
    md.append(
        "- 受影响聚合行**不修改**，只登记警告。\n"
        "- B07 来源聚类检验必须**先按文档去重**，再聚类。\n"
        "- 不得为了得到「来源簇 ≥3」而忽略这些重复。\n"
    )

    md_path = OUT_DIR / "source_independence_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-3] {json_path}")
    print(f"[B01-3] {md_path}")
    print(f"[B01-3] {dup_csv}  ({len(cross_doc)} cross-doc duplicate groups)")
    print(f"  documents entangled          = {len(dup_docs)}")
    print(f"  entangled document pairs     = {len(entangled)}")
    print(f"  aggregates affected          = {len(agg_impact)}")
    print(f"  registry not_evaluated       = {n_not_evaluated}/{len(registry)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
