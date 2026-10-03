# -*- coding: utf-8 -*-
"""W37-B：把还原轴准入清单接进交付/导出链路（回答 README §11 第 18 条）。

W36-D 造好了准入件（probes/w36_gate_admission.py + 准入清单 manifest），但它只在被
调用时生效——导出阶段不会自己失败。本校验器把论文侧（附录 A/B/C 的表格行）的还原轴
引用点逐条绑到 probes/artifacts/w35_gated_reference_register.csv：

* 论文行里出现的登记读数（quoted_value 三位有效数字）或（合法子集/总体）分数，必须能在
  登记表里找到对应行 —— 找不到就是「未登记」违规；
* 找到后由 admit() 重算：未登记抛 AdmissionRefused，标记由 W34-A 守卫复算，与登记值
  不一致即违规（禁止手写标记）；
* 氧化轴引用点按既有约定标「不适用（门禁只覆盖还原轴）」。

机械规则（不写死行号）：附录由标题 "## 附录 A/B/C" 定位，表格行由 "|…|" 解析，读数
令牌用带边界的正则匹配。全部通过则 stdout 打印一行 JSON 并 exit 0；否则打印 JSON 并
exit 1。

只读；不拟合模型；不改任何已交付字节；0 shot（累计 19）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBES = REPOSITORY_ROOT / "probes"
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(PROBES))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import w36_gate_admission as admission
import w35_redox_gate_consumers as consumers

SCHEMA = "w37_redox_admission_check/report@1"

DEFAULT_REGISTER = PROBES / "artifacts" / "w35_gated_reference_register.csv"
DEFAULT_REGISTRY = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
DEFAULT_MANIFEST = PROBES / "artifacts" / "w36_gate_admission_manifest.csv"
DEFAULT_PAPER = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"

# 论文侧登记读数令牌：quoted_value 的三位有效数字（符号无关）-> reference_id。
# 这是「预期登记」的静态词汇表：删掉/改名登记行不会让令牌消失，于是能查出未登记。
VALUE_TOKENS = {
    "0.835": "r6_red_gfn2",
    "0.602": "r6_red_orca",
    "0.697": "r6_ox_gfn2",
    "0.654": "r6_ox_orca",
    "0.745": "w33a_gfn2_gas",
    "0.733": "w33a_gfn2_thf",
    "0.674": "w33a_gfn2_benzaldehyde",
    "0.812": "w33a_gfn2_water",
}
# 合法子集/总体 分数令牌 -> reference_id。
FRACTION_TOKENS = {
    "52/246": "w33a_gfn2_gas",
    "1/22": "r6_red_gfn2",
    "0/22": "r6_red_orca",
    "2/22": "w33a_orca_smd_acetonitrile",
}

APPENDIX_RE = re.compile(r"^##\s*附录\s*([ABC])")
TABLE_ROW_RE = re.compile(r"^\|.*\|")
TABLE_SEP_RE = re.compile(r"^\|[\s:\-|]+\|?\s*$")

OXIDATION_MARK = consumers.MARK_ID_APPLICABLE


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_registry(path) -> list:
    rows = read_csv_rows(path)
    for row in rows:
        row["legal"] = int(row["legal"])
    return rows


def token_pattern(token: str):
    return re.compile(r"(?<![\d.])" + re.escape(token) + r"(?![\d])")


def appendix_table_rows(paper_path) -> list:
    """机械定位附录 A/B/C 的表格行（按标题，不写死行号）。"""
    lines = Path(paper_path).read_text(encoding="utf-8").splitlines()
    rows = []
    for index, line in enumerate(lines):
        match = APPENDIX_RE.match(line)
        if not match:
            continue
        label = match.group(1)
        for offset in range(index + 1, len(lines)):
            current = lines[offset]
            if current.startswith("## "):
                break
            if TABLE_ROW_RE.match(current) and not TABLE_SEP_RE.match(current):
                rows.append({"paper_line": offset + 1, "appendix": label, "text": current})
    return rows


def row_label(text: str) -> str:
    cells = [cell.strip() for cell in text.strip().strip("|").split("|")]
    return cells[0] if cells else ""


def bind_reference_ids(text: str):
    """返回（命中的 reference_id 集合，命中的令牌列表）。"""
    found, tokens = set(), []
    for token, reference_id in VALUE_TOKENS.items():
        if token_pattern(token).search(text):
            found.add(reference_id)
            tokens.append(token)
    for token, reference_id in FRACTION_TOKENS.items():
        if token_pattern(token).search(text):
            found.add(reference_id)
            tokens.append(token)
    return found, tokens


def complete_by_source(text: str, found: set, register: list) -> set:
    """同源补全：同一来源表（source_path）下、被论文行提及的轴对应的其余格子，也
    算这一行的引用点（如附录 A 的 R6 索引行同时报氧化/还原两轴）。"""
    by_id = {row["reference_id"]: row for row in register}
    sources = {by_id[rid]["source_path"] for rid in found if rid in by_id}
    extra = set()
    for row in register:
        rid = row["reference_id"]
        if rid in found or row["source_path"] not in sources:
            continue
        axis_word = "氧化" if row["axis"] == "oxidation" else "还原"
        if axis_word in text:
            extra.add(rid)
    return extra


def evaluate(register_path=DEFAULT_REGISTER, registry_path=DEFAULT_REGISTRY,
             manifest_path=DEFAULT_MANIFEST, paper_path=DEFAULT_PAPER) -> dict:
    register_path = Path(register_path)
    registry_path = Path(registry_path)
    manifest_path = Path(manifest_path)
    paper_path = Path(paper_path)

    register = read_csv_rows(register_path)
    registry = load_registry(registry_path)
    paired = consumers.paired_keys(registry)
    manifest = read_csv_rows(manifest_path)
    by_id = {row["reference_id"]: row for row in register}

    violations, sites = [], []

    for row in manifest:
        reference_id = row["reference_id"]
        if row["admission"] != "准入":
            violations.append({"kind": "manifest_admission", "reference_id": reference_id,
                               "detail": "manifest 行未准入：" + str(row["admission"])})
        if reference_id in by_id and row["mark"] != by_id[reference_id]["mark"]:
            violations.append({"kind": "manifest_mark", "reference_id": reference_id,
                               "detail": "manifest mark 与登记表不一致"})

    for entry in appendix_table_rows(paper_path):
        text = entry["text"]
        found, tokens = bind_reference_ids(text)
        if not found:
            continue
        found = found | complete_by_source(text, found, register)
        for reference_id in sorted(found):
            row = by_id.get(reference_id)
            if row is None:
                violations.append({
                    "kind": "unregistered", "paper_line": entry["paper_line"],
                    "appendix": entry["appendix"], "reference_id": reference_id,
                    "tokens": ";".join(tokens),
                    "detail": "论文引用点未登记：登记表里没有 " + reference_id})
                continue
            key = {field: row[field] for field in admission.KEY_FIELDS}
            try:
                record = admission.admit(register, registry, paired, key)
            except admission.AdmissionRefused as error:
                violations.append({"kind": "refused", "paper_line": entry["paper_line"],
                                   "appendix": entry["appendix"], "reference_id": reference_id,
                                   "detail": str(error)})
                continue
            mark = record["mark"]
            if not mark:
                violations.append({"kind": "empty_mark", "paper_line": entry["paper_line"],
                                   "reference_id": reference_id, "detail": "准入后标记为空"})
            if row["axis"] == "reduction" and mark != row["mark"]:
                violations.append({"kind": "mark_mismatch", "paper_line": entry["paper_line"],
                                   "reference_id": reference_id,
                                   "detail": "守卫复算 mark=" + mark + " 与登记值 " + row["mark"] + " 不一致"})
            sites.append({
                "paper_line": entry["paper_line"], "appendix": entry["appendix"],
                "row_label": row_label(text), "axis": row["axis"],
                "matched_reference_id": reference_id, "admission": "准入",
                "mark": mark, "mark_source": record["mark_source"],
                "tokens": ";".join(tokens), "note": record["admission_note"]})

    unregistered = [item for item in violations if item["kind"] == "unregistered"]
    mark_mismatch = [item for item in violations if item["kind"] == "mark_mismatch"]
    oxidation_marks = sorted({site["mark"] for site in sites if site["axis"] == "oxidation"})
    inputs = {}
    for path in (register_path, registry_path, manifest_path, paper_path):
        inputs[str(path.resolve())] = sha256_file(path)
    return {
        "schema": SCHEMA,
        "passed": not violations,
        "sites": len(sites),
        "reduction_sites": sum(1 for site in sites if site["axis"] == "reduction"),
        "oxidation_sites": sum(1 for site in sites if site["axis"] == "oxidation"),
        "paper_rows": len({site["paper_line"] for site in sites}),
        "unregistered": unregistered,
        "mark_mismatch": mark_mismatch,
        "violations": violations,
        "sites_detail": sites,
        "oxidation_marks": oxidation_marks,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": inputs,
        "boundaries": [
            "准入清单只覆盖还原轴（阴离子态审计）；氧化轴引用点按既有约定标「不适用」。",
            "拒答不是缺失值：mark=不可判定的点不得插补、赋伪值或静默丢弃。",
            "本校验器只读；不拟合模型、不改任何已交付字节。",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Redox-axis admission checker for the paper appendix index.")
    parser.add_argument("--register", default=str(DEFAULT_REGISTER))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--paper", default=str(DEFAULT_PAPER))
    args = parser.parse_args(argv)
    payload = evaluate(Path(args.register), Path(args.registry),
                       Path(args.manifest), Path(args.paper))
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
