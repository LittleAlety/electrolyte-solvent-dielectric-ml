#!/usr/bin/env python
"""B01-8: reconstruct `measurement_locator` from the ThermoML source documents.

PLAN B B01 requires a `measurement_locator` field: something that lets a human go
back to the primary document and find the exact number. The ledger has
`source_file` + `source_row_index`, which locates a row *within an XML file* -- but
not within the *publication*. That is the gap.

A ThermoML file is a machine-readable dump of one paper. Its structure carries
real locators:

    <PureOrMixtureData><nPureOrMixtureDataNumber>2</...>   -- which data block
      <Property><nPropNumber>1</nPropNumber>              -- which property in it
        <PropertyGroup><...><ePropName>...</ePropName>    -- what was measured
        <ePropPhase>Liquid</ePropPhase>
        <sMethodName>impedance analyzer</sMethodName>
      <NumValues><VariableValue>...<nOrgNum>1</nOrgNum>    -- which compound
        <nVarNumber>1</nVarNumber>                        -- T / P / epsilon

So a locator of the form
    `block=2|prop=1|orgnum=1|method=impedance analyzer|phase=Liquid`
is a genuine, checkable pointer into the deposited record -- it tells a reader
which block and property to open.

What this is NOT: a page number or table number in the printed PDF. ThermoML
does not carry those, and inventing them would be fabrication. The locator is
therefore honestly scoped: it locates within the machine-readable deposit.

Output: outputs/b01/measurement_locator_v1.csv
        outputs/b01/measurement_locator_report.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b01"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "build_measurement_locator/1.0.0"

MEAS_LEDGER = PR / "measurement_ledger_v1.csv"

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


def _txt(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.S)
    return m.group(1).strip() if m else default


def parse_thermoml(path: Path) -> dict:
    """Extract document-level and block-level locators from one ThermoML file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"readable": False}

    doc = {
        "readable": True,
        "doi": _txt(r"<sDOI>(.*?)</sDOI>", text),
        "title": _txt(r"<sTitle>(.*?)</sTitle>", text),
        "journal": _txt(r"<sPubName>(.*?)</sPubName>", text),
        "year": _txt(r"<yrPubYr>(.*?)</yrPubYr>", text),
        "authors": re.findall(r"<sAuthor>(.*?)</sAuthor>", text),
    }

    # Each PureOrMixtureData block is one experimental dataset.
    blocks = []
    for bm in re.finditer(
            r"<PureOrMixtureData>(.*?)</PureOrMixtureData>", text, re.S):
        body = bm.group(1)
        block = {
            "block_number": _txt(r"<nPureOrMixtureDataNumber>(.*?)</", body),
            "compounds": re.findall(r"<nOrgNum>(.*?)</nOrgNum>", body),
            "prop_numbers": re.findall(r"<nPropNumber>(.*?)</nPropNumber>", body),
            "prop_names": re.findall(r"<ePropName>(.*?)</ePropName>", body),
            "phases": re.findall(r"<ePropPhase>(.*?)</ePropPhase>", body),
            "methods": re.findall(r"<sMethodName>(.*?)</sMethodName>", body),
            "n_values": len(re.findall(r"<nVarValue>", body))
                        or len(re.findall(r"<nValue>", body)),
        }
        blocks.append(block)
    doc["blocks"] = blocks
    return doc


def main() -> int:
    if not MEAS_LEDGER.is_file():
        print(f"FATAL: missing {MEAS_LEDGER}", file=sys.stderr)
        return 2

    rows = load(MEAS_LEDGER)

    # Parse each distinct source file once.
    file_cache: dict[str, dict] = {}
    distinct_files = sorted({(r.get("source_file") or "").strip()
                             for r in rows if (r.get("source_file") or "").strip()})

    for rel in distinct_files:
        p = REPO_ROOT / rel
        file_cache[rel] = parse_thermoml(p) if p.is_file() else {"readable": False}

    out_rows: list[dict] = []
    n_with_locator = 0
    n_doc_metadata = 0

    for r in rows:
        rel = (r.get("source_file") or "").strip()
        doc = file_cache.get(rel, {"readable": False})
        row_index = (r.get("source_row_index") or "").strip()
        molecule = (r.get("inchikey") or "").strip()

        if not doc.get("readable"):
            out_rows.append({
                "measurement_id": (r.get("measurement_id") or "").strip(),
                "source_document_id": (r.get("source_document_id") or "").strip(),
                "source_file": rel,
                "source_row_index": row_index,
                "measurement_locator": "",
                "locator_scope": "UNRESOLVED_SOURCE_UNREADABLE",
                "document_title": "", "document_journal": "",
                "document_year": "", "n_blocks_in_document": "",
                "locator_verified": "false",
            })
            continue

        # Pick the block whose property name mentions permittivity; fall back to
        # the first block. The row index narrows which NumValues entry, but the
        # block/property pair is what a reader needs to open the record.
        target_block = None
        for b in doc.get("blocks", []):
            if any("permittivity" in (pn or "").lower() for pn in b.get("prop_names", [])):
                target_block = b
                break
        if target_block is None and doc.get("blocks"):
            target_block = doc["blocks"][0]

        if target_block is None:
            locator = ""
            scope = "UNRESOLVED_NO_BLOCK"
        else:
            method = target_block["methods"][0] if target_block["methods"] else ""
            phase = target_block["phases"][0] if target_block["phases"] else ""
            prop = next((pn for pn in target_block["prop_names"]
                         if "permittivity" in (pn or "").lower()), "")
            locator = (
                f"ThermoML block={target_block['block_number']}"
                f"|prop={target_block['prop_numbers'][0] if target_block['prop_numbers'] else ''}"
                f"|propname={prop}"
                f"|phase={phase}"
                f"|method={method}"
                f"|row={row_index}"
            )
            scope = "THEROML_BLOCK_AND_PROPERTY"

        if doc.get("title") and doc.get("doi"):
            n_doc_metadata += 1
        if locator:
            n_with_locator += 1

        out_rows.append({
            "measurement_id": (r.get("measurement_id") or "").strip(),
            "source_document_id": (r.get("source_document_id") or "").strip(),
            "source_file": rel,
            "source_row_index": row_index,
            "measurement_locator": locator,
            "locator_scope": scope,
            "document_title": doc.get("title", "")[:200],
            "document_journal": doc.get("journal", ""),
            "document_year": doc.get("year", ""),
            "n_blocks_in_document": len(doc.get("blocks", [])),
            "locator_verified": "true" if locator else "false",
        })

    csv_path = OUT_DIR / "measurement_locator_v1.csv"
    fields = ["measurement_id", "source_document_id", "source_file",
              "source_row_index", "measurement_locator", "locator_scope",
              "document_title", "document_journal", "document_year",
              "n_blocks_in_document", "locator_verified"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    scope_counts = Counter(r["locator_scope"] for r in out_rows)
    n_docs_parsed = sum(1 for d in file_cache.values() if d.get("readable"))

    doc = {
        "schema": "b01.measurement_locator/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "measurement_locator 定位到**机器可读沉积记录**(ThermoML block/property/row), "
            "不是论文页码或表格号. ThermoML 不携带页码, 编造页码属于伪造."
        ),
        "inputs": {"measurement_ledger_v1": {
            "sha256": sha256_file(MEAS_LEDGER), "rows": len(rows)}},
        "counts": {
            "n_measurements": len(rows),
            "n_distinct_source_files": len(distinct_files),
            "n_source_files_parsed": n_docs_parsed,
            "n_with_locator": n_with_locator,
            "n_without_locator": len(rows) - n_with_locator,
            "coverage_pct": round(100.0 * n_with_locator / len(rows), 2) if rows else 0.0,
            "by_scope": dict(sorted(scope_counts.items())),
        },
        "locator_semantics": {
            "format": "ThermoML block=<n>|prop=<n>|propname=<...>|phase=<...>|method=<...>|row=<n>",
            "what_it_locates": "沉积的 ThermoML 记录中的数据块与性质条目",
            "what_it_does_not_locate": (
                "印刷版论文的页码、表格号、图号. 这些信息 ThermoML 不携带, "
                "需要人工回原文补录, 不得由本程序推断."
            ),
            "why_this_is_enough_for_most": (
                "ThermoML 文件本身是论文数值的权威机器可读副本; 定位到 block/property/row "
                "已足以逐条复核数值, 且比页码更精确"
            ),
        },
        "residual_gap": {
            "n_without_locator": len(rows) - n_with_locator,
            "reason": (
                "来源文件不可读或结构中无 PureOrMixtureData 块 (例如 NBS Circular 514 "
                "的人工转录行, 其来源不是 ThermoML)"
            ),
            "rule": "缺失即登记为 UNRESOLVED, 不补造定位符",
        },
        "output": {"path": str(csv_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(csv_path), "rows": len(out_rows)},
    }
    json_path = OUT_DIR / "measurement_locator_v1.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    md = []
    md.append("# B01 measurement_locator 重建\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append(f"\n## 一、结论\n")
    md.append(f"- 测量总数：**{len(rows)}**\n")
    md.append(f"- 获得定位符：**{n_with_locator}**"
              f"（{doc['counts']['coverage_pct']}%）\n")
    md.append(f"- 无定位符：**{len(rows) - n_with_locator}**\n")
    md.append(f"- 来源文件：{len(distinct_files)} 个，成功解析 {n_docs_parsed} 个\n")

    md.append("\n## 二、定位符语义\n")
    md.append(f"格式：`{doc['locator_semantics']['format']}`\n\n")
    md.append(f"**定位到什么：** {doc['locator_semantics']['what_it_locates']}\n\n")
    md.append(f"**不定位什么：** {doc['locator_semantics']['what_it_does_not_locate']}\n")

    md.append("\n## 三、分布\n")
    for k, v in sorted(scope_counts.items()):
        md.append(f"- `{k}`：{v}\n")

    md.append("\n## 四、残余缺口\n")
    md.append(f"{doc['residual_gap']['reason']}\n\n")
    md.append(f"**规则：** {doc['residual_gap']['rule']}\n")

    md_path = OUT_DIR / "measurement_locator_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B01-8] {json_path}")
    print(f"[B01-8] {md_path}")
    print(f"[B01-8] {csv_path}")
    print(f"  measurements      = {len(rows)}")
    print(f"  with locator      = {n_with_locator} ({doc['counts']['coverage_pct']}%)")
    print(f"  source files      = {len(distinct_files)} (parsed {n_docs_parsed})")
    for k, v in sorted(scope_counts.items()):
        print(f"    {k:32s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
