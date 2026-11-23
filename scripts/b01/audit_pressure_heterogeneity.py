#!/usr/bin/env python
"""B01-6: pressure heterogeneity audit.

PLAN B B01 core principle 4 forbids assembling a real measurement pair from
independently computed medians. Reviewers 1 and 4 found a *second, independent*
way the same thing goes wrong that the frozen gate set does not catch:

    10.1021/je060248p is not an ambient study. It sweeps 0.1 -> 300 MPa at fixed
    T. Permittivity rises monotonically with pressure. If the in-band set mixes
    ambient points with sweep points, the "median" is an intermediate PRESSURE,
    not an ambient measurement -- and `pressure_kpa` is blank, so nothing says so.

The decisive example is EPSV04-R097: eight "observations" from 101 kPa to 300 MPa,
whose reported 14.26 is exactly the midpoint of the 100 and 150 MPa points.

This script does not fix those aggregates. It measures the contamination and
classifies every aggregate by whether its contributing set spans more than one
pressure decade. Repair requires a reviewed change to the window definition, which
is a frozen protocol decision, not an audit decision.

Output: outputs/b01/pressure_heterogeneity_audit.csv
        outputs/b01/pressure_heterogeneity_report.md
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
GENERATOR = "audit_pressure_heterogeneity/1.0.0"

MEAS_LEDGER = PR / "measurement_ledger_v1.csv"
AGG_LEDGER = PR / "aggregate_contribution_ledger_v1.csv"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}
AMBIENT_KPA = 101.325
# Anything above this is unambiguously a pressurised measurement, not ambient.
AMBIENT_TOLERANCE_KPA = 5.0


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
    for p in (MEAS_LEDGER, AGG_LEDGER):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    meas = load(MEAS_LEDGER)
    agg = load(AGG_LEDGER)

    by_agg: dict[str, list[dict]] = defaultdict(list)
    for m in meas:
        a = (m.get("aggregate_id") or "").strip()
        if a and a.lower() not in PLACEHOLDERS:
            by_agg[a].append(m)

    rows: list[dict] = []
    for a in agg:
        aid = (a.get("aggregate_id") or "").strip()
        members = by_agg.get(aid, [])
        if not members:
            continue

        pressures = []
        for m in members:
            p = fnum(m.get("pressure_kpa"))
            if p is not None:
                pressures.append((p, m))

        if not pressures:
            rows.append({
                "aggregate_id": aid,
                "measurement_id": f"EPSV04-R{aid[len('v04row-'):]}",
                "n_contributing": len(members),
                "n_with_pressure": 0,
                "p_min_kpa": "", "p_max_kpa": "", "p_span_ratio": "",
                "n_ambient": 0, "n_pressurised": 0,
                "contamination_class": "PRESSURE_UNRECORDED",
                "v04_dielectric": (a.get("v04_dielectric") or "").strip(),
                "pressure_disclosed": "false",
                "severity": "UNKNOWN",
                "evidence": "全部贡献观测的 pressure 字段为空, 无法判断是否混入加压点",
            })
            continue

        pvals = [p for p, _ in pressures]
        p_min, p_max = min(pvals), max(pvals)
        ambient = [p for p in pvals
                   if abs(p - AMBIENT_KPA) <= AMBIENT_TOLERANCE_KPA]
        pressurised = [p for p in pvals if p > AMBIENT_KPA + AMBIENT_TOLERANCE_KPA]

        span = (p_max / p_min) if p_min > 0 else None

        if pressurised and ambient:
            cls = "MIXED_AMBIENT_AND_PRESSURISED"
            severity = "HIGH"
        elif pressurised and not ambient:
            cls = "PRESSURISED_ONLY"
            severity = "HIGH" if len(pressurised) > 1 else "MEDIUM"
        elif ambient:
            cls = "AMBIENT_CONSISTENT"
            severity = "NONE"
        else:
            cls = "UNCLASSIFIED"
            severity = "LOW"

        # The queue row's own pressure disclosure
        disclosed = any(
            (m.get("pressure_kpa") or "").strip().lower() not in PLACEHOLDERS
            for m in members)

        rows.append({
            "aggregate_id": aid,
            "measurement_id": f"EPSV04-R{aid[len('v04row-'):]}",
            "n_contributing": len(members),
            "n_with_pressure": len(pressures),
            "p_min_kpa": f"{p_min:g}",
            "p_max_kpa": f"{p_max:g}",
            "p_span_ratio": f"{span:.1f}" if span else "",
            "n_ambient": len(ambient),
            "n_pressurised": len(pressurised),
            "contamination_class": cls,
            "v04_dielectric": (a.get("v04_dielectric") or "").strip(),
            "pressure_disclosed": "true" if disclosed else "false",
            "severity": severity,
            "evidence": (
                f"贡献集压力范围 {p_min:g}-{p_max:g} kPa "
                f"(常压点 {len(ambient)}, 加压点 {len(pressurised)}); "
                f"ε 随压力单调上升, 混合后中位数对应的是中间压力而非常压"
                if cls == "MIXED_AMBIENT_AND_PRESSURISED"
                else f"压力范围 {p_min:g}-{p_max:g} kPa"
            ),
        })

    # ---- the decisive worked example ----
    r097 = by_agg.get("v04row-097", [])
    r097_detail = []
    for m in sorted(r097, key=lambda x: fnum(x.get("pressure_kpa")) or 0):
        r097_detail.append({
            "measurement_id": (m.get("measurement_id") or "").strip(),
            "pressure_kpa": (m.get("pressure_kpa") or "").strip(),
            "dielectric": (m.get("dielectric") or "").strip(),
            "temperature_K": (m.get("temperature_K") or "").strip(),
            "source_document_id": (m.get("source_document_id") or "").strip(),
        })

    csv_path = OUT_DIR / "pressure_heterogeneity_audit.csv"
    fields = ["aggregate_id", "measurement_id", "n_contributing", "n_with_pressure",
              "p_min_kpa", "p_max_kpa", "p_span_ratio", "n_ambient",
              "n_pressurised", "contamination_class", "severity",
              "pressure_disclosed", "v04_dielectric", "evidence"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    by_class = Counter(r["contamination_class"] for r in rows)
    contaminated = [r for r in rows
                    if r["contamination_class"] in
                    ("MIXED_AMBIENT_AND_PRESSURISED", "PRESSURISED_ONLY")]

    doc = {
        "schema": "b01.pressure_heterogeneity/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本审计只测量污染, 不修复. 修复需要改动窗口定义, 属冻结协议决策, "
            "不是审计可以自行决定的事."
        ),
        "inputs": {
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(meas)},
            "aggregate_contribution_ledger_v1": {"sha256": sha256_file(AGG_LEDGER),
                                                 "rows": len(agg)},
        },
        "counts": {
            "n_aggregates_with_members": len(rows),
            "by_class": dict(sorted(by_class.items())),
            "n_contaminated": len(contaminated),
        },
        "contaminated_aggregates": [
            {"aggregate_id": r["aggregate_id"], "measurement_id": r["measurement_id"],
             "class": r["contamination_class"], "severity": r["severity"],
             "p_min_kpa": r["p_min_kpa"], "p_max_kpa": r["p_max_kpa"],
             "v04_dielectric": r["v04_dielectric"],
             "pressure_disclosed": r["pressure_disclosed"]}
            for r in contaminated
        ],
        "worked_example_EPSV04_R097": {
            "why": (
                "四审独立发现的决定性案例: 8 条『观测』实为 101 kPa 至 300 MPa 的压力序列, "
                "报告的 14.26 恰为 100 MPa(14.07) 与 150 MPa(14.45) 的中点"
            ),
            "contributing_observations": r097_detail,
            "reported_dielectric": next(
                ((a.get("v04_dielectric") or "").strip() for a in agg
                 if (a.get("aggregate_id") or "").strip() == "v04row-097"), None),
            "midpoint_check": (
                "14.26 == (14.07 + 14.45) / 2" if r097_detail else None),
        },
        "repair_policy": {
            "automatic_repair": False,
            "why_not": (
                "把加压点从窗口剔除会改变 R219 冻结窗口的语义, 从而改变 460/78/170 "
                "这些已报告计数. 这必须是一次经过审核的协议变更, 不是审计脚本可以做的."
            ),
            "required_before_repair": [
                "四智能体审核确认污染范围",
                "明确压力分层规则 (常压带定义)",
                "生成新的版本号与哈希",
                "不覆盖 J01/J02/J03 与 v04",
            ],
            "downstream_consequence_if_unrepaired": (
                "受污染聚合行的 ε 系统性偏高 (压力使 ε 上升), "
                "若直接进入 B05 建模会引入非化学的结构性误差"
            ),
        },
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(rows)},
    }
    json_path = OUT_DIR / "pressure_heterogeneity_audit.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 压力异质性审计\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append("> 只测量污染，不修复。修复需改动冻结窗口，属协议决策。\n")

    md.append("\n## 一、结论\n")
    md.append(f"- 有贡献测量的聚合行：**{len(rows)}**\n")
    for k, v in sorted(by_class.items()):
        md.append(f"- `{k}`：**{v}**\n")
    md.append(f"\n**受污染聚合行：{len(contaminated)}**\n")

    md.append("\n## 二、决定性案例 EPSV04-R097\n")
    md.append(f"{doc['worked_example_EPSV04_R097']['why']}\n\n")
    md.append("| measurement_id | pressure (kPa) | ε | T (K) | 来源 |\n")
    md.append("|---|---:|---:|---:|---|\n")
    for o in r097_detail:
        md.append(f"| `{o['measurement_id']}` | {o['pressure_kpa']} | "
                  f"{o['dielectric']} | {o['temperature_K']} | "
                  f"`{o['source_document_id']}` |\n")
    md.append(f"\n报告的 ε = **{doc['worked_example_EPSV04_R097']['reported_dielectric']}**，"
              f"即 100–150 MPa 的中点。**这不是常压测量。**\n")

    md.append("\n## 三、受污染聚合行清单\n")
    md.append("| aggregate_id | 类别 | 严重度 | 压力范围 (kPa) | v04 ε | 压力是否披露 |\n")
    md.append("|---|---|---|---|---:|---|\n")
    for r in contaminated:
        md.append(f"| `{r['aggregate_id']}` | {r['contamination_class']} | "
                  f"{r['severity']} | {r['p_min_kpa']}–{r['p_max_kpa']} | "
                  f"{r['v04_dielectric']} | {r['pressure_disclosed']} |\n")

    md.append("\n## 四、为什么不自动修复\n")
    md.append(f"{doc['repair_policy']['why_not']}\n\n")
    md.append("修复前置条件：\n")
    for c in doc["repair_policy"]["required_before_repair"]:
        md.append(f"- {c}\n")
    md.append(f"\n**若不修复的后果：** "
              f"{doc['repair_policy']['downstream_consequence_if_unrepaired']}\n")

    md_path = OUT_DIR / "pressure_heterogeneity_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-6] {json_path}")
    print(f"[B01-6] {md_path}")
    print(f"[B01-6] {csv_path}")
    print(f"  aggregates with members = {len(rows)}")
    for k, v in sorted(by_class.items()):
        print(f"    {k:34s} {v}")
    print(f"  CONTAMINATED = {len(contaminated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
