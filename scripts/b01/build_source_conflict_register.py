#!/usr/bin/env python
"""B01-7: build the unresolved source-conflict register.

Reviewer 4 found a scope gap that no other check covers: gamma-valerolactone
(EPSV04-R227 vs EPSV04-R248) carries two live, conflicting epsilon values for the
same compound at the same temperature -- 36.1 vs 36.9 -- and was simply **absent
from the admission queue**. It was excluded from review rather than adjudicated.

An audit that never sees a conflict cannot resolve it. This script finds every
such conflict mechanically instead of waiting for a reviewer to notice, so the
conflict enters a queue by construction rather than by luck.

Conflict definition (deliberately narrow, to avoid drowning in noise):
    same InChIKey
    AND same temperature (within a tolerance)
    AND epsilon values differing by more than a relative tolerance
    AND both rows are database rows (aggregate level)

Rows differing only because they are *different temperatures* are not conflicts;
that is ordinary physics.

Output: outputs/b01/source_conflict_register.csv
        outputs/b01/source_conflict_report.md
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
OUT_DIR = REPO_ROOT / "outputs" / "b01"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "build_source_conflict_register/1.0.0"

PAIR_VALIDITY = PR / "condition_pair_validity_v1.csv"
AGG_LEDGER = PR / "aggregate_contribution_ledger_v1.csv"

T_TOLERANCE_K = 0.5          # treat these as "the same temperature"
REL_EPS_TOLERANCE = 0.02     # 2% relative difference is a real disagreement

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


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    for p in (PAIR_VALIDITY, AGG_LEDGER):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    pair = load(PAIR_VALIDITY)
    agg = {r["aggregate_id"]: r for r in load(AGG_LEDGER)}

    # Index by molecule, then compare temperatures PAIRWISE against a real
    # tolerance.
    #
    # History: this used to bucket on `round(t, 1)` -- equality of a rounded key,
    # which is not a tolerance. It silently missed the canonical "room
    # temperature" disagreement 298.15 vs 298.2 K (different buckets), and could
    # split an identical pair across a bucket boundary. T_TOLERANCE_K was
    # declared but only printed, never applied, so the documented tolerance and
    # the implemented one disagreed. Fixed to pairwise comparison.
    by_mol: dict[str, list[dict]] = defaultdict(list)
    for p in pair:
        mol = (p.get("molecule_key") or "").strip()
        t = fnum(p.get("v04_T_K"))
        e = fnum(p.get("v04_dielectric"))
        if not mol or mol.lower() in PLACEHOLDERS or t is None or e is None:
            continue
        by_mol[mol].append(p)

    conflicts: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for mol, rows in sorted(by_mol.items()):
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                ta, tb = fnum(a.get("v04_T_K")), fnum(b.get("v04_T_K"))
                ea, eb = fnum(a.get("v04_dielectric")), fnum(b.get("v04_dielectric"))
                if None in (ta, tb, ea, eb):
                    continue
                if abs(ta - tb) > T_TOLERANCE_K:
                    continue
                if ea <= 0 or eb <= 0:
                    continue
                rel = abs(ea - eb) / min(ea, eb)
                if rel <= REL_EPS_TOLERANCE:
                    continue
                key = (a.get("aggregate_id", ""), b.get("aggregate_id", ""))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                rows_pair = [a, b]
                eps_vals = [ea, eb]
                lo, hi = min(eps_vals), max(eps_vals)
                ids = [(r.get("aggregate_id") or "").strip() for r in rows_pair]
                srcs = []
                for r in rows_pair:
                    agg_row = agg.get((r.get("aggregate_id") or "").strip(), {})
                    s = (agg_row.get("contributing_source_documents") or "").strip()
                    srcs.append(s if s.lower() not in PLACEHOLDERS else
                                (agg_row.get("v04_source_doi") or "").strip())
                names = [(r.get("a_name") or "").strip() for r in rows_pair]

                conflicts.append({
                    "conflict_id": f"CONF-{mol[:14]}-{min(ta, tb):g}",
                    "molecule_key": mol,
                    "a_name": next((n for n in names
                                    if n.lower() not in PLACEHOLDERS), ""),
                    "temperature_K": f"{min(ta, tb):g}",
                    "temperature_pair": f"{ta:g};{tb:g}",
                    "n_rows": len(rows_pair),
                    "aggregate_ids": ";".join(ids),
                    "epsilon_values": ";".join(f"{v:g}" for v in eps_vals),
                    "eps_min": f"{lo:g}",
                    "eps_max": f"{hi:g}",
                    "relative_spread_pct": f"{rel*100:.2f}",
                    "source_documents": ";".join(s for s in srcs if s),
                    "distinct_sources": len({s for s in srcs if s}),
                    "both_pair_valid": ";".join(
                        (r.get("condition_pair_valid") or "").strip() for r in rows_pair),
                    "in_review_queue": "unknown",
                    "resolution_status": "UNRESOLVED",
                    "rule": (
                        "同一化合物、温度差在容差内、不同 ε 超过容差. "
                        "不得平均、不得择一、不得按骨架合并. "
                        "必须并列保留并进入裁决队列."
                    ),
                })

    # Mark which conflicts reached the B02 queue (they were excluded before).
    queue_path = REPO_ROOT / "outputs" / "admission_v2" / "admission_review_queue.csv"
    queued_ids: set[str] = set()
    if queue_path.is_file():
        with queue_path.open(encoding="utf-8-sig", newline="") as fh:
            queued_ids = {(r.get("measurement_id") or "").strip()
                          for r in csv.DictReader(fh)}
    for c in conflicts:
        mids = [f"EPSV04-R{a[len('v04row-'):]}" for a in c["aggregate_ids"].split(";")
                if a.startswith("v04row-")]
        c["in_review_queue"] = ("true" if any(m in queued_ids for m in mids) else "false")

    csv_path = OUT_DIR / "source_conflict_register.csv"
    fields = ["conflict_id", "molecule_key", "a_name", "temperature_K", "n_rows",
              "aggregate_ids", "epsilon_values", "eps_min", "eps_max",
              "relative_spread_pct", "source_documents", "distinct_sources",
              "both_pair_valid", "in_review_queue", "resolution_status", "rule"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in conflicts:
            w.writerow({k: c.get(k, "") for k in fields})

    # ---- Second layer: measurement-level conflicts ----
    # The aggregate layer collapses to one row per compound-condition, so it can
    # only show a conflict when two *database rows* disagree. Real disagreements
    # are far more common at the observation layer: two papers measuring the same
    # compound at the same temperature and reporting different epsilon. Those are
    # the conflicts that actually matter for B05, because a model fed both values
    # as separate training points learns from label noise.
    meas_ledger = PR / "measurement_ledger_v1.csv"
    meas_conflicts: list[dict] = []
    if meas_ledger.is_file():
        mrows = load(meas_ledger)
        # Same pairwise-tolerance approach as the aggregate layer above; the
        # round()-bucket version had the identical 298.15-vs-298.2 blind spot.
        mby_mol: dict[str, list[dict]] = defaultdict(list)
        for m in mrows:
            mol = (m.get("inchikey") or "").strip()
            t = fnum(m.get("temperature_K"))
            e = fnum(m.get("dielectric"))
            if not mol or mol.lower() in PLACEHOLDERS or t is None or e is None:
                continue
            mby_mol[mol].append(m)

        for mol, mol_rows in sorted(mby_mol.items()):
            # Group this molecule's observations into temperature clusters, then
            # report any cluster whose epsilon spread exceeds tolerance.
            used: set[int] = set()
            for i in range(len(mol_rows)):
                if i in used:
                    continue
                ti = fnum(mol_rows[i].get("temperature_K"))
                if ti is None:
                    continue
                cluster = [mol_rows[i]]
                used.add(i)
                for j in range(i + 1, len(mol_rows)):
                    if j in used:
                        continue
                    tj = fnum(mol_rows[j].get("temperature_K"))
                    if tj is None:
                        continue
                    if abs(ti - tj) <= T_TOLERANCE_K:
                        cluster.append(mol_rows[j])
                        used.add(j)
                if len(cluster) < 2:
                    continue
                eps_vals = [fnum(r.get("dielectric")) for r in cluster]
                eps_vals = [v for v in eps_vals if v is not None]
                if len(eps_vals) < 2:
                    continue
                lo, hi = min(eps_vals), max(eps_vals)
                if lo <= 0:
                    continue
                rel = (hi - lo) / lo
                if rel <= REL_EPS_TOLERANCE:
                    continue
                t = ti
                rows = cluster
                docs = sorted({(r.get("source_document_id") or "").strip()
                               for r in rows
                               if (r.get("source_document_id") or "").strip()})
                meas_conflicts.append({
                "conflict_id": f"MCONF-{mol[:14]}-{t:g}",
                "molecule_key": mol,
                "temperature_K": f"{t:g}",
                "n_observations": len(rows),
                "epsilon_min": f"{lo:g}",
                "epsilon_max": f"{hi:g}",
                "relative_spread_pct": f"{rel*100:.2f}",
                "n_distinct_sources": len(docs),
                "source_documents": ";".join(docs),
                "measurement_ids": ";".join(
                    (r.get("measurement_id") or "").strip() for r in rows),
                "resolution_status": "UNRESOLVED",
                "rule": (
                    "同一分子、同一温度、不同 ε 超过容差. "
                    "两条都不得被当作独立训练点; 必须先裁决或标记为不确定标签."
                ),
            })

    meas_csv = OUT_DIR / "measurement_conflict_register.csv"
    if meas_conflicts:
        mfields = ["conflict_id", "molecule_key", "temperature_K", "n_observations",
                   "epsilon_min", "epsilon_max", "relative_spread_pct",
                   "n_distinct_sources", "source_documents", "measurement_ids",
                   "resolution_status", "rule"]
        with meas_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=mfields)
            w.writeheader()
            for c in meas_conflicts:
                w.writerow({k: c.get(k, "") for k in mfields})

    excluded = [c for c in conflicts if c["in_review_queue"] == "false"]

    doc = {
        "schema": "b01.source_conflicts/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本登记表只识别冲突, 不裁决. 冲突不得通过平均、择一或按骨架合并消解; "
            "必须并列保留并进入裁决队列."
        ),
        "tolerances": {
            "temperature_K": T_TOLERANCE_K,
            "relative_epsilon": REL_EPS_TOLERANCE,
            "rationale": (
                "温度容差 0.5 K 用于识别『同一条件』; "
                "ε 相对容差 2% 用于排除测量不确定度级别的差异. "
                "两者都是本审计的选择, 不是冻结协议的一部分."
            ),
        },
        "inputs": {
            "condition_pair_validity_v1": {"sha256": sha256_file(PAIR_VALIDITY),
                                           "rows": len(pair)},
            "aggregate_contribution_ledger_v1": {"sha256": sha256_file(AGG_LEDGER),
                                                 "rows": len(agg)},
        },
        "counts": {
            "n_conflicts_aggregate_layer": len(conflicts),
            "n_conflicts_measurement_layer": len(meas_conflicts),
            "n_conflicts_excluded_from_review_queue": len(excluded),
            "n_molecules_affected": len({c["molecule_key"] for c in conflicts}
                                        | {c["molecule_key"] for c in meas_conflicts}),
            "layer_note": (
                "两层必须分开报. 聚合层每化合物-条件只有一行, 只有当两个数据库行"
                "互相矛盾时才显出冲突; 观测层才承载真实的跨文献分歧."
            ),
        },
        "conflicts": conflicts,
        "critical_caveat_on_this_conflict": {
            "finding": (
                "该冲突的『同一温度 298.15 K』前提是**两条独立的温度推定碰巧一致**, "
                "不是两次实测. R227 的 temperature_source = "
                "review_table_standard_room_temperature (综述表统一标注室温); "
                "R248 的 temperature_source = not_reported (原始 SI 未报温度, "
                "Reaxys 记录的 T_K 为空)."
            ),
            "consequence": (
                "因此**不得以『同温下数值矛盾』为由裁决**. 正确的裁决路径是按来源质量 "
                "(primary SI > 综述表), 而不是把它当成同条件实测的冲突."
            ),
            "evidence_location": "data/dielectric_v04.csv 的 temperature_source 列",
            "reviewer": "Reviewer 3 (B02-CONFLICT) 独立发现",
        },
        "measurement_layer_conflicts": {
            "n": len(meas_conflicts),
            "top": sorted(meas_conflicts,
                          key=lambda c: -float(c["relative_spread_pct"]))[:10],
            "note": (
                "观测层冲突数量远高于聚合层, 因为聚合把分歧压成了单个中位数. "
                "这些分歧在 B05 中会被当作独立训练点, 从而放大样本量并引入标签噪声."
            ),
        },
        "review_coverage_gap": {
            "finding": (
                f"{len(excluded)} 个真实来源冲突**没有进入** B02 审核队列. "
                f"审核队列只覆盖了 J02A 的 4 个分子、P0/P1 分子和 22 条合成条件对, "
                f"没有覆盖『同一条件两个冲突值』这一类."
            ),
            "why_it_matters": (
                "未被审核的冲突无法被裁决. 若这些分子进入 B05 建模, "
                "冲突值会被当作两条独立观测, 凭空放大样本量并引入标签噪声."
            ),
            "remedy": (
                "B03/B04 在引入这些分子前, 必须先把冲突登记项送入审核队列. "
                "本表即为该队列的输入."
            ),
        },
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(conflicts)},
    }
    json_path = OUT_DIR / "source_conflict_register.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 未决来源冲突登记\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append("> 只识别冲突，不裁决。不得平均、择一或按骨架合并。\n")

    md.append("\n## 一、结论\n")
    md.append(f"- 聚合层冲突：**{len(conflicts)}** 组\n")
    md.append(f"- 观测层冲突：**{len(meas_conflicts)}** 组\n")
    md.append(f"- 其中 **{len(excluded)}** 组聚合层冲突**未进入** B02 审核队列\n")
    md.append(f"\n{doc['counts']['layer_note']}\n")

    md.append("\n## 二、冲突清单\n")
    md.append("| 分子 | T (K) | ε 值 | 相对差异 | 来源数 | 是否入队 |\n")
    md.append("|---|---:|---|---:|---:|---|\n")
    for c in conflicts:
        nm = c["a_name"] or c["molecule_key"][:14]
        md.append(f"| {nm} | {c['temperature_K']} | {c['epsilon_values']} | "
                  f"{c['relative_spread_pct']}% | {c['distinct_sources']} | "
                  f"{'✅' if c['in_review_queue']=='true' else '❌'} |\n")

    md.append("\n## 三、观测层冲突（最严重的前 10）\n")
    md.append("| 分子 | T (K) | ε 范围 | 相对差异 | 观测数 | 来源数 |\n")
    md.append("|---|---:|---|---:|---:|---:|\n")
    for c in sorted(meas_conflicts,
                    key=lambda c: -float(c["relative_spread_pct"]))[:10]:
        md.append(f"| `{c['molecule_key'][:14]}` | {c['temperature_K']} | "
                  f"{c['epsilon_min']}–{c['epsilon_max']} | "
                  f"{c['relative_spread_pct']}% | {c['n_observations']} | "
                  f"{c['n_distinct_sources']} |\n")
    md.append(f"\n{doc['measurement_layer_conflicts']['note']}\n")

    md.append("\n## 四、审核覆盖缺口\n")
    md.append(f"{doc['review_coverage_gap']['finding']}\n\n")
    md.append(f"**为什么重要：** {doc['review_coverage_gap']['why_it_matters']}\n\n")
    md.append(f"**补救：** {doc['review_coverage_gap']['remedy']}\n")

    md.append("\n## 四、容差声明\n")
    md.append(f"- 温度容差：{T_TOLERANCE_K} K\n")
    md.append(f"- ε 相对容差：{REL_EPS_TOLERANCE*100:.0f}%\n")
    md.append(f"\n{doc['tolerances']['rationale']}\n")

    md_path = OUT_DIR / "source_conflict_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-7] {json_path}")
    print(f"[B01-7] {md_path}")
    print(f"[B01-7] {csv_path}")
    print(f"  conflicts found = {len(conflicts)}")
    print(f"  excluded from review queue = {len(excluded)}")
    for c in conflicts:
        print(f"    {c['a_name'] or c['molecule_key'][:14]:20s} T={c['temperature_K']:8s} "
              f"eps={c['epsilon_values']:20s} queued={c['in_review_queue']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
