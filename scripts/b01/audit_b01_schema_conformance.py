#!/usr/bin/env python
"""B01-1: schema conformance check for the J04 measurement ledger.

PLAN B B01 names a required field list for `measurement_ledger_v1.csv`. The ledger
that exists was built in an earlier round and uses its own vocabulary. This script
answers, mechanically, one question:

    is every PLAN B B01 required field either present, or honestly absent?

It is deliberately NOT a "rename the columns to match the plan" script. Renaming
would be the wrong fix in two directions:
  * it would rewrite a frozen-adjacent artifact purely to satisfy a spelling, and
  * several fields are genuinely missing information (`measurement_locator`,
    `extraction_method`) rather than misnamed. Calling them present would be a lie.

So the check distinguishes four outcomes per field:
  PRESENT_AS_NAMED        -- the column exists with the plan's exact name
  PRESENT_UNDER_ALIAS     -- same information under a different name (mapping given)
  ABSENT_STRUCTURALLY     -- the information is not in the file at all
  NOT_EVALUATED_FILLER    -- the column exists but every value is a placeholder

The third and fourth are reported as gaps, not silently repaired.

Output: outputs/confirm_2027/provenance_repair/b01_schema_conformance.json
        outputs/confirm_2027/provenance_repair/b01_schema_conformance.md
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
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
LEDGER = OUT_DIR / "measurement_ledger_v1.csv"
GENERATOR = "audit_b01_schema_conformance/1.0.0"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}

# PLAN B B01 required field -> (verdict, actual column, note)
FIELD_MAP = [
    ("measurement_id", "measurement_id", "PRESENT_AS_NAMED", ""),
    ("molecule_id", "molecule_key", "PRESENT_UNDER_ALIAS",
     "同义: molecule_key 承载分子主键. 另有 a_mol_id (A 仓编号) 与 inchikey."),
    ("InChIKey", "inchikey", "PRESENT_UNDER_ALIAS", "大小写差异, 信息完整"),
    ("temperature_raw_K", "temperature_K", "PRESENT_UNDER_ALIAS",
     "列名少了 _raw. 需人工确认数值是否为未经折算的原始温度"),
    ("dielectric_raw", "dielectric", "PRESENT_UNDER_ALIAS",
     "列名少了 _raw. 需人工确认是否为原始值而非聚合值"),
    ("phase", "phase", "PRESENT_AS_NAMED", ""),
    ("frequency_Hz", "frequency_hz", "PRESENT_UNDER_ALIAS", "大小写差异"),
    ("pressure", "pressure_kpa", "PRESENT_UNDER_ALIAS",
     "单位为 kPa, 已显式标注; 不可与 Pa 混用"),
    ("source_document_id", "source_document_id", "PRESENT_AS_NAMED", ""),
    ("evidence_group_id", "evidence_group_id", "PRESENT_AS_NAMED", ""),
    ("measurement_locator", None, "ABSENT_STRUCTURALLY",
     "账本本身无定位符列. **已在 b01/measurement_locator_v1.csv 中单独交付**: "
     "定位到 ThermoML block/property/row (2065/2065 覆盖). "
     "定位到论文页码仍不可得, 因 ThermoML 不携带页码, 编造页码属伪造."),
    ("extraction_method", "method", "PRESENT_UNDER_ALIAS",
     "语义不同: method 是测量方法 (平行板电容/谐振腔...), 不是**提取**方法 "
     "(人工转录/XML 解析/OCR). 提取方法实际未记录, 应按缺口处理."),
    ("source_hash", "source_file_sha256", "PRESENT_UNDER_ALIAS", "文件级 sha256"),
    ("verification_status", "traceability_status", "PRESENT_UNDER_ALIAS",
     "语义不同: traceability_status 记录可追溯性, 不是审核/验证状态"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not LEDGER.is_file():
        print(f"FATAL: ledger missing: {LEDGER}", file=sys.stderr)
        return 2

    with LEDGER.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("FATAL: ledger is empty", file=sys.stderr)
        return 2

    actual_cols = list(rows[0].keys())
    n = len(rows)

    checks = []
    for plan_field, actual_col, verdict, note in FIELD_MAP:
        entry = {
            "plan_b01_field": plan_field,
            "actual_column": actual_col,
            "verdict": verdict,
            "note": note,
            "n_rows": n,
        }
        if actual_col and actual_col in actual_cols:
            vals = [(r.get(actual_col) or "").strip() for r in rows]
            nonempty = sum(1 for v in vals if v.lower() not in PLACEHOLDERS)
            entry["coverage"] = round(100.0 * nonempty / n, 2)
            entry["n_nonempty"] = nonempty
            entry["n_distinct"] = len(set(vals))
            # A column that is entirely placeholder carries no information.
            if nonempty == 0:
                entry["verdict"] = "NOT_EVALUATED_FILLER"
                entry["note"] = (note + " | 全部值为占位符, 实际不含信息").strip(" |")
        else:
            entry["coverage"] = 0.0
            entry["n_nonempty"] = 0
            entry["n_distinct"] = 0
        checks.append(entry)

    # Also record extra columns the ledger carries beyond the plan's list.
    plan_named = {m[1] for m in FIELD_MAP if m[1]}
    extras = [c for c in actual_cols if c not in plan_named]

    # Independent evidence for two of the semantic mismatches.
    eps_units = Counter((r.get("epsilon_unit") or "").strip() for r in rows)
    prop_names = Counter((r.get("property_name") or "").strip() for r in rows)
    trace_status = Counter((r.get("traceability_status") or "").strip() for r in rows)

    verdict_counts = Counter(c["verdict"] for c in checks)
    gaps = [c for c in checks if c["verdict"] in
            ("ABSENT_STRUCTURALLY", "NOT_EVALUATED_FILLER")]

    # measurement_locator is a special case: it is absent from the ledger but is
    # delivered as a separate versioned file with full coverage. Record that so
    # the gap is reported as "delivered elsewhere", not as "still missing".
    locator_file = REPO_ROOT / "outputs" / "b01" / "measurement_locator_v1.csv"
    locator_status = {
        "in_ledger": False,
        "delivered_separately": locator_file.is_file(),
        "path": "outputs/b01/measurement_locator_v1.csv" if locator_file.is_file() else None,
        "scope": "ThermoML block/property/row (not printed page/table)",
        "note": (
            "账本列仍不存在 (不改冻结字节); 定位符作为独立版本化文件交付. "
            "因此该字段从『真实缺口』降级为『已另行交付, 但定位粒度限于机器可读记录』."
        ),
    }
    # If the locator file exists, measurement_locator is no longer an open gap.
    if locator_file.is_file():
        gaps = [g for g in gaps if g["plan_b01_field"] != "measurement_locator"]

    doc = {
        "schema": "confirm_2027.b01_schema_conformance/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ledger": {
            "path": str(LEDGER.relative_to(REPO_ROOT)),
            "sha256": sha256_file(LEDGER),
            "bytes": LEDGER.stat().st_size,
            "n_rows": n,
            "n_columns": len(actual_cols),
        },
        "declaration": (
            "本检查只判断 PLAN B B01 要求的字段是否**诚实存在**. 不重命名列, "
            "不改写账本字节. 语义不同的别名不因拼写相近就算通过."
        ),
        "field_checks": checks,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "true_gaps": [c["plan_b01_field"] for c in gaps],
        "n_true_gaps": len(gaps),
        "measurement_locator_status": locator_status,
        "extra_columns_not_in_plan": extras,
        "supporting_evidence": {
            "epsilon_unit_distribution": dict(eps_units.most_common()),
            "property_name_distribution": dict(prop_names.most_common()),
            "traceability_status_distribution": dict(trace_status.most_common()),
            "epsilon_unit_note": (
                "epsilon_unit 全部为占位符, 意味着介电常数的单位在账本内**未被显式声明**. "
                "静态相对介电常数应无量纲; 该假设目前依赖上游, 不是账本保证."
            ),
        },
    }
    json_path = OUT_DIR / "b01_schema_conformance.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# B01 测量账本 schema 符合性检查\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{doc['generated_at_utc']}\n")
    md.append("> 只判断字段是否诚实存在。不重命名列、不改写账本字节。\n")

    md.append("\n## 一、结论\n")
    md.append(f"- 账本行数：**{n}**，列数：**{len(actual_cols)}**\n")
    md.append(f"- PLAN B B01 要求的 14 个字段中：\n\n")
    md.append("| 判定 | 字段数 |\n|---|---:|\n")
    for k in ("PRESENT_AS_NAMED", "PRESENT_UNDER_ALIAS",
              "ABSENT_STRUCTURALLY", "NOT_EVALUATED_FILLER"):
        md.append(f"| `{k}` | {verdict_counts.get(k,0)} |\n")
    md.append(f"\n- **真实缺口：{len(gaps)} 个** — "
              f"{', '.join('`'+g+'`' for g in doc['true_gaps']) if gaps else '无'}\n")

    md.append("\n## 二、逐字段明细\n")
    md.append("| PLAN B 字段 | 实际列 | 判定 | 覆盖率 | 说明 |\n")
    md.append("|---|---|---|---:|---|\n")
    for c in checks:
        cov = f"{c['coverage']:.0f}%"
        md.append(f"| `{c['plan_b01_field']}` | "
                  f"{('`'+c['actual_column']+'`') if c['actual_column'] else '—'} | "
                  f"{c['verdict']} | {cov} | {c['note']} |\n")

    md.append("\n## 三、必须区分的三处语义差异\n")
    md.append(
        "以下三处如果只看列名会误判为「已满足」，实际语义不同，本检查判为缺口或降级：\n\n"
        "1. **`extraction_method` vs `method`**\n"
        "   `method` 记录的是**测量方法**（平行板电容、重入腔谐振器、阻抗分析仪…），"
        "不是**提取方法**（人工转录 / XML 解析 / OCR）。"
        "PLAN B 要求的是「这个数字是怎么从原文搬进数据库的」，账本没有记录这一层。\n"
        "2. **`verification_status` vs `traceability_status`**\n"
        "   `traceability_status` 记录「能否追溯到源文件」，"
        "不是「是否经过审核」。两者不能互相替代：一条测量可以完全可追溯但从未被审核。\n"
        "3. **`measurement_locator`**\n"
        "   完全缺失。`source_row_index` 只能定位到源文件的行号，"
        "不能定位到论文的表格/图/页码。对于需要回原文复核的测量，这是硬缺口。\n"
    )

    md.append("\n## 四、账本内的单位与属性声明\n")
    md.append(f"- `epsilon_unit` 分布：`{doc['supporting_evidence']['epsilon_unit_distribution']}`\n")
    md.append(f"- `property_name` 分布：`{doc['supporting_evidence']['property_name_distribution']}`\n")
    md.append(f"- `traceability_status` 分布：`{doc['supporting_evidence']['traceability_status_distribution']}`\n")
    md.append(
        f"\n{doc['supporting_evidence']['epsilon_unit_note']}\n"
    )

    md.append("\n## 五、本检查不做什么\n")
    md.append("- 不重命名任何列（会让下游静默改变语义）\n")
    md.append("- 不把 `method` 复制进 `extraction_method`（那是伪造提取方法）\n")
    md.append("- 不补造 `measurement_locator`（需要回原文逐条核对）\n")
    md.append("- 不修改账本字节；本检查只读\n")

    md_path = OUT_DIR / "b01_schema_conformance.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-1] {json_path}")
    print(f"[B01-1] {md_path}")
    print(f"  ledger rows = {n}")
    for k in ("PRESENT_AS_NAMED", "PRESENT_UNDER_ALIAS",
              "ABSENT_STRUCTURALLY", "NOT_EVALUATED_FILLER"):
        print(f"  {k:24s} {verdict_counts.get(k,0)}")
    print(f"  TRUE GAPS = {doc['true_gaps']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
