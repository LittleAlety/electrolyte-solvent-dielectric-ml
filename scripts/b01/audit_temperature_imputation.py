#!/usr/bin/env python
"""B01-9: temperature imputation audit.

Discovered while adjudicating the gamma-valerolactone conflict, but the defect is
far wider than that one molecule. `data/dielectric_v04.csv` carries a
`temperature_source` column, and it is not uniform:

    reported                                226 rows -- the source states a temperature
    review_table_standard_room_temperature   21 rows -- a review table had no T column,
                                                       so 298.15 K was assumed
    not_reported                              1 row  -- the source never gave a T

That means 22 rows carry a temperature the experiment did not report, and **18 of
them are flagged `model_ready = true`**. Any model trained on those rows is being
taught that a value measured at an unknown temperature belongs at 298.15 K.

The GVL conflict is the visible symptom: its entire premise ("same T, different
epsilon") rests on two independent imputations landing on the same default.

This script measures the scope. It does not rewrite v04 -- correcting an imputed
temperature requires going back to the source, which is B03 work.

Output: outputs/b01/temperature_imputation_audit.csv
        outputs/b01/temperature_imputation_report.md
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
V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
GENERATOR = "audit_temperature_imputation/1.0.0"

IMPUTED_SOURCES = {
    "review_table_standard_room_temperature",
    "not_reported",
}

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


def main() -> int:
    if not V04.is_file():
        print(f"FATAL: missing {V04}", file=sys.stderr)
        return 2

    rows = load(V04)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_rows: list[dict] = []
    for i, r in enumerate(rows, 1):
        src = (r.get("temperature_source") or "").strip()
        imputed = src in IMPUTED_SOURCES
        out_rows.append({
            "aggregate_id": f"v04row-{i:03d}",
            "measurement_id": f"EPSV04-R{i:03d}",
            "inchikey": (r.get("inchikey") or "").strip(),
            "name": (r.get("name") or "").strip(),
            "T_K": (r.get("T_K") or "").strip(),
            "dielectric": (r.get("dielectric") or "").strip(),
            "temperature_source": src,
            "temperature_imputed": "true" if imputed else "false",
            "source_quality": (r.get("source_quality") or "").strip(),
            "evidence_level": (r.get("evidence_level") or "").strip(),
            "model_ready": (r.get("model_ready") or "").strip(),
            "source_doi": (r.get("source_doi") or "").strip(),
            "conflict_status": (r.get("conflict_status") or "").strip(),
            "downstream_rule": (
                "温度未报告; 298.15 K 是推定值. 不得作为同温证据使用, "
                "建模时须标记为温度不确定或排除"
                if imputed else ""
            ),
        })

    imputed_rows = [r for r in out_rows if r["temperature_imputed"] == "true"]
    imputed_model_ready = [r for r in imputed_rows if r["model_ready"] == "true"]

    csv_path = OUT_DIR / "temperature_imputation_audit.csv"
    fields = ["aggregate_id", "measurement_id", "inchikey", "name", "T_K",
              "dielectric", "temperature_source", "temperature_imputed",
              "source_quality", "evidence_level", "model_ready", "source_doi",
              "conflict_status", "downstream_rule"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    by_source = Counter(r["temperature_source"] or "(empty)" for r in out_rows)
    # Which review-table documents contributed the imputed rows?
    imputed_dois = Counter(r["source_doi"] for r in imputed_rows if r["source_doi"])

    doc = {
        "schema": "b01.temperature_imputation/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本审计只测量范围, 不改写 v04. 修正推定温度必须回原始文献, 属 B03 工作."
        ),
        "inputs": {"dielectric_v04": {"sha256": sha256_file(V04), "rows": len(rows)}},
        "counts": {
            "n_rows": len(rows),
            "by_temperature_source": dict(sorted(by_source.items())),
            "n_imputed": len(imputed_rows),
            "n_imputed_model_ready": len(imputed_model_ready),
            "imputed_pct": round(100.0 * len(imputed_rows) / len(rows), 2) if rows else 0.0,
        },
        "finding": (
            f"{len(imputed_rows)}/{len(rows)} 行的温度是**推定**而非实测 "
            f"(review_table_standard_room_temperature 或 not_reported). "
            f"其中 **{len(imputed_model_ready)} 行标记 model_ready=true** —— "
            f"模型会被训练成『一个未知温度下的测量值属于 298.15 K』."
        ),
        "why_it_matters": (
            "介电常数有显著的 dε/dT (例如甲醇约 -0.116 K⁻¹). "
            "0.8 个 ε 单位约对应 2.7-4.0 K 的未记录温差. "
            "因此 GVL 的 36.1 vs 36.9 冲突**可能根本不是冲突**, "
            "而是两次温度推定之差."
        ),
        "imputed_rows": [
            {"measurement_id": r["measurement_id"], "name": r["name"],
             "T_K": r["T_K"], "dielectric": r["dielectric"],
             "temperature_source": r["temperature_source"],
             "model_ready": r["model_ready"],
             "source_quality": r["source_quality"]}
            for r in imputed_rows
        ],
        "imputed_source_documents": dict(sorted(imputed_dois.items())),
        "consequence_for_the_gvl_conflict": (
            "GVL 冲突的两条腿温度都是推定 (review_table_standard_room_temperature "
            "与 not_reported), 因此『同一温度下数值矛盾』这一前提不成立. "
            "裁决应基于来源质量, 不应基于同温实测矛盾."
        ),
        "downstream_rule": {
            "for_b04": "推定温度行不得以 298.15 K 作为条件参与同温冲突判定",
            "for_b05": "建模时须标记 temperature_imputed, 或从确认性样本中排除",
            "forbidden": [
                "把推定温度当作实测温度",
                "为凑同温条件而保留推定值",
                "因推定温度而拒绝一条本来有效的测量",
            ],
        },
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(out_rows)},
    }
    json_path = OUT_DIR / "temperature_imputation_audit.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    md = []
    md.append("# B01 温度推定审计\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append("> 只测量范围，不改写 v04。修正推定温度须回原始文献。\n")

    md.append("\n## 一、结论\n")
    md.append(f"{doc['finding']}\n")

    md.append("\n## 二、temperature_source 分布\n")
    md.append("| 来源 | 行数 |\n|---|---:|\n")
    for k, v in sorted(by_source.items()):
        md.append(f"| `{k}` | {v} |\n")

    md.append("\n## 三、为什么重要\n")
    md.append(f"{doc['why_it_matters']}\n")

    md.append("\n## 四、推定温度行清单\n")
    md.append("| measurement_id | 分子 | T (K) | ε | 温度来源 | model_ready | 来源质量 |\n")
    md.append("|---|---|---:|---:|---|---|---|\n")
    for r in imputed_rows:
        md.append(f"| `{r['measurement_id']}` | {r['name'][:24]} | {r['T_K']} | "
                  f"{r['dielectric']} | `{r['temperature_source']}` | "
                  f"{r['model_ready']} | {r['source_quality']} |\n")

    md.append("\n## 五、对 GVL 冲突的含义\n")
    md.append(f"{doc['consequence_for_the_gvl_conflict']}\n")

    md.append("\n## 六、下游规则\n")
    for k, v in doc["downstream_rule"].items():
        if isinstance(v, str):
            md.append(f"- **{k}**：{v}\n")
        else:
            for item in v:
                md.append(f"- 禁止：{item}\n")

    md_path = OUT_DIR / "temperature_imputation_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-9] {json_path}")
    print(f"[B01-9] {md_path}")
    print(f"[B01-9] {csv_path}")
    print(f"  rows                  = {len(rows)}")
    print(f"  imputed temperature   = {len(imputed_rows)} ({doc['counts']['imputed_pct']}%)")
    print(f"  of which model_ready  = {len(imputed_model_ready)}")
    for k, v in sorted(by_source.items()):
        print(f"    {k:42s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
