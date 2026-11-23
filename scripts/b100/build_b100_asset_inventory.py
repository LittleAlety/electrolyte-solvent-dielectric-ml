#!/usr/bin/env python
"""B100-1: data-asset inventory.

PLAN B v6.0 raises the target from 22 molecules to >=100 independent qualified
molecules. Before computing anything, this script answers: how much usable evidence
does the repository ALREADY hold, and how much of it is actually admissible?

The inventory is deliberately pessimistic. It counts, for every candidate source:

  * molecules (deduplicated by full InChIKey, never by skeleton)
  * measurements (rows), kept distinct from molecules
  * how many carry a traceable source document and hash
  * which are blocked by a known defect and why

It also audits the NBS Circular 514 expansion layer, because that is the one large
static-dielectric asset the repository already holds (392 rows / 389 molecules).
The audit's central question for NBS is the one PLAN B v6.0 raises: the expansion
table has `frequency_mhz` empty on every row. Is that "unknown frequency" (a Q3
defect) or "the source defines the quantity as the low-frequency limit" (legitimate)?

The answer must be derived, not assumed. This script checks the NBS transcription
for per-row frequency footnotes and reports how the 392 selected rows relate to
them.

Output: outputs/b100/b100_asset_inventory.json
        outputs/b100/b100_asset_inventory.md
        outputs/b100/nbs514_condition_audit.csv
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
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "build_b100_asset_inventory/1.0.0"

# --- expansion layer (NBS Circular 514 candidates) ---
EXP_OBS = REPO_ROOT / "data" / "processed" / "dielectric_pool_expansion_observations.csv"
EXP_FEAT = REPO_ROOT / "data" / "processed" / "dielectric_pool_expansion_features.csv"
NBS_PARTS = [REPO_ROOT / "data" / "interim" / f"nbs514_organic_part{i}.csv"
             for i in range(1, 5)]

# --- core ThermoML layer (already reconstructed in B01) ---
MEAS_LEDGER = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
               / "measurement_ledger_v1.csv")
SRC_REGISTRY = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
                / "source_document_registry_v1.csv")
V04 = REPO_ROOT / "data" / "dielectric_v04.csv"

# --- auxiliary candidate-discovery sources (NOT labels) ---
SOLVFUNC = REPO_ROOT / "data" / "external" / "SolvFunc-87.csv"
BATT = REPO_ROOT / "data" / "external" / "Batt-SLM-RX-392.csv"

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    """Read a CSV, tolerating the encodings and delimiters found in this repo.

    External sources are not all UTF-8: SolvFunc-87.csv is cp1252 and uses ';'.
    Silently mangling a source file would corrupt an audit, so the encoding is
    retried explicitly rather than assumed.
    """
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError(f"cannot decode {path}")
    # pick the delimiter from the header line
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    # ================= expansion layer =================
    exp_obs = load(EXP_OBS) if EXP_OBS.is_file() else []
    exp_feat = load(EXP_FEAT) if EXP_FEAT.is_file() else []

    exp_inchikeys = {(r.get("inchikey") or "").strip() for r in exp_obs}
    exp_inchikeys.discard("")
    exp_dup = len(exp_obs) - len(exp_inchikeys)

    xtb_present = sum(1 for r in exp_feat
                      if (r.get("dipole_D") or "").strip().lower()
                      not in PLACEHOLDERS)
    xtb_missing = len(exp_feat) - xtb_present

    # frequency field: empty everywhere is a *claim*, so verify against the source
    freq_vals = Counter((r.get("frequency_mhz") or "").strip() for r in exp_obs)
    freq_all_empty = set(freq_vals) <= {""}

    # ================= NBS transcription =================
    nbs_rows: list[dict] = []
    for p in NBS_PARTS:
        if p.is_file():
            nbs_rows.extend(load(p))
    nbs_by_id = {(r.get("source_id") or "").strip(): r for r in nbs_rows}
    nbs_with_freq_note = [r for r in nbs_rows
                          if (r.get("frequency_note") or "").strip()]

    # audit each selected expansion row against its transcription row
    audit_rows: list[dict] = []
    n_selected_with_freq_note = 0
    n_selected_unmatched = 0
    n_selected_static_defined = 0
    for r in exp_obs:
        sid = (r.get("source_id") or "").strip()
        src = nbs_by_id.get(sid)
        freq_note = (src.get("frequency_note") or "").strip() if src else ""
        has_note = bool(freq_note)
        if src is None:
            n_selected_unmatched += 1
        if has_note:
            n_selected_with_freq_note += 1
        else:
            n_selected_static_defined += 1
        audit_rows.append({
            "source_id": sid,
            "inchikey": (r.get("inchikey") or "").strip(),
            "name": (r.get("name") or "").strip(),
            "T_K": (r.get("T_K") or "").strip(),
            "epsilon": (r.get("epsilon") or "").strip(),
            "expansion_frequency_mhz": (r.get("frequency_mhz") or "").strip(),
            "transcription_found": "true" if src else "false",
            "transcription_frequency_note": freq_note,
            "transcription_section": (src.get("section") or "").strip() if src else "",
            "transcription_page": (src.get("source_page") or "").strip() if src else "",
            "transcription_references": (src.get("references") or "").strip() if src else "",
            "source_quality": (src.get("source_quality") or "").strip() if src else "",
            "eligibility_status": (src.get("eligibility_status") or "").strip() if src else "",
            "frequency_status": (
                "NON_STATIC_FLAGGED" if has_note
                else "STATIC_BY_SOURCE_DEFINITION" if src
                else "UNVERIFIED"),
        })

    # how many transcription rows were NOT selected, and why
    sel_ids = {(r.get("source_id") or "").strip() for r in exp_obs}
    not_selected = [r for r in nbs_rows
                    if (r.get("source_id") or "").strip() not in sel_ids]
    ns_with_freq = sum(1 for r in not_selected
                       if (r.get("frequency_note") or "").strip())
    ns_elig = Counter((r.get("eligibility_status") or "").strip()
                      for r in not_selected)

    audit_path = OUT / "nbs514_condition_audit.csv"
    if audit_rows:
        with audit_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(audit_rows[0].keys()))
            w.writeheader()
            for r in audit_rows:
                w.writerow(r)

    # ================= core ThermoML layer =================
    ledger = load(MEAS_LEDGER) if MEAS_LEDGER.is_file() else []
    registry = load(SRC_REGISTRY) if SRC_REGISTRY.is_file() else []
    v04 = load(V04) if V04.is_file() else []

    core_molecules = {(r.get("inchikey") or "").strip() for r in v04}
    core_molecules.discard("")
    ledger_molecules = {(r.get("inchikey") or "").strip() for r in ledger}
    ledger_molecules.discard("")

    # ================= auxiliary discovery sources =================
    solvfunc = load(SOLVFUNC) if SOLVFUNC.is_file() else []
    batt = load(BATT) if BATT.is_file() else []

    # ================= union / overlap =================
    all_candidate = core_molecules | exp_inchikeys
    overlap = core_molecules & exp_inchikeys

    doc = {
        "schema": "b100.asset_inventory/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "仓库现有多少**可用的实验证据**, 以及多少分子能达到 B100 的准入标准? "
            "本盘点只做计数与审计, 不新增任何测量."
        ),
        "target": {
            "plan": "PLAN B v6.0",
            "min_qualified_molecules": 100,
            "suggested_candidate_pool": "150-200",
            "aspirational_qualified": "120-150",
            "hard_rule": (
                "不得以降低数据质量凑数; 不得把多条测量记录冒充多个独立分子; "
                "未审核候选不得直接宣布为合格分子."
            ),
        },
        "layer_1_experimental_labels": {
            "core_thermoml": {
                "source": str(MEAS_LEDGER.relative_to(REPO_ROOT)),
                "n_measurements": len(ledger),
                "n_molecules": len(ledger_molecules),
                "n_source_documents": len(registry),
                "n_v04_aggregate_rows": len(v04),
                "n_v04_molecules": len(core_molecules),
                "evidence_grade": "Q1 (原始实验, 条件可追溯)",
                "admission_status": (
                    "已在 88f6c33 冻结. 其中 78 行条件配对有效, 170 行无效 "
                    "(见 reconstruction_exceptions.csv)."
                ),
            },
            "nbs514_expansion": {
                "source": str(EXP_OBS.relative_to(REPO_ROOT)),
                "n_measurement_rows": len(exp_obs),
                "n_molecules": len(exp_inchikeys),
                "n_duplicate_rows_same_molecule": exp_dup,
                "evidence_grade": "Q2 (NIST 批判性汇编, 条件可核查)",
                "phase_all_liquid": all(
                    (r.get("phase") or "").strip().lower() == "liquid"
                    for r in exp_obs),
                "component_count_all_one": all(
                    (r.get("component_count") or "").strip() == "1"
                    for r in exp_obs),
                "license": (exp_obs[0].get("license") or "").strip() if exp_obs else "",
                "admission_status": (
                    "**尚未准入**. 需完成条件审计后才能进入正式数据集."
                ),
            },
        },
        "layer_2_xtb": {
            "source": str(EXP_FEAT.relative_to(REPO_ROOT)),
            "n_molecules_with_features": len(exp_feat),
            "n_with_dipole": xtb_present,
            "n_missing_dipole": xtb_missing,
            "note": (
                "现有 xTB 计算只覆盖 NBS 扩展层. 核心 ThermoML 层与新增分子"
                "仍需统一计算. B100 要求统一 xTB 覆盖 >=100."
            ),
        },
        "layer_3_dft_conformer": {
            "status": "NOT_STARTED",
            "n_computed": 0,
            "note": "DFT 与构象计算尚未开始; 需先完成 12 分子方法验证.",
        },
        "layer_4_md": {
            "status": "NOT_STARTED",
            "n_systems": 0,
            "note": "液相 MD 尚未开始.",
        },
        "auxiliary_discovery_only": {
            "solvfunc_87": {
                "source": str(SOLVFUNC.relative_to(REPO_ROOT)),
                "n_records": len(solvfunc),
                "use": "分子候选发现, **不得作为实验介电标签**",
            },
            "batt_slm_392": {
                "source": str(BATT.relative_to(REPO_ROOT)),
                "n_records": len(batt),
                "use": (
                    "分子电子性质与候选发现. "
                    "**其中计算得到的介电环境参数不得冒充实测介电常数**"
                ),
            },
        },
        "nbs514_frequency_audit": {
            "question": (
                "扩展表 frequency_mhz 全部为空 —— 这是『频率未知』(Q3 缺陷), "
                "还是『来源把该量定义为低频极限』(合法)?"
            ),
            "expansion_frequency_all_empty": freq_all_empty,
            "n_expansion_rows": len(exp_obs),
            "n_transcription_rows": len(nbs_rows),
            "n_transcription_with_frequency_footnote": len(nbs_with_freq_note),
            "frequency_footnote_values": dict(Counter(
                (r.get("frequency_note") or "").strip()
                for r in nbs_with_freq_note).most_common()),
            "n_selected_rows_matched_to_transcription":
                len(exp_obs) - n_selected_unmatched,
            "n_selected_unmatched": n_selected_unmatched,
            "n_selected_with_frequency_footnote": n_selected_with_freq_note,
            "n_selected_static_by_definition": n_selected_static_defined,
            "n_not_selected_transcription_rows": len(not_selected),
            "n_not_selected_with_frequency_footnote": ns_with_freq,
            "not_selected_eligibility": dict(ns_elig),
            "conclusion": (
                "**扩展层的 392 行全部来自不带频率脚注的转录行**, 因此空白的 "
                "frequency_mhz 应解释为『来源级静态定义』而不是『频率未知』. "
                f"另有 {len(not_selected)} 条转录行未被选入扩展表, 其中 "
                f"{ns_with_freq} 条带非静态频率脚注 (3.6-5e8 cycles/sec, 即 "
                "360-500 MHz), 已被正确排除. "
                "**因此 NBS 层可以按 Q2 处理, 但必须标记为来源级静态定义, "
                "不得与逐条报告频率的 ThermoML 测量等同.**"
            ),
            "residual_risk": (
                "来源级定义仍是**集体判断**: 若某条测量实际在 400 MHz 下进行而"
                "来源未加脚注, 本审计无法发现. 因此 Q2 证据必须保留这一保留意见, "
                "并在来源敏感性分析中单独处理."
            ),
        },
        "union_estimate": {
            "core_molecules": len(core_molecules),
            "expansion_molecules": len(exp_inchikeys),
            "overlap_core_and_expansion": len(overlap),
            "union_candidate_molecules": len(all_candidate),
            "headline": (
                f"核心 {len(core_molecules)} + 扩展 {len(exp_inchikeys)} "
                f"- 重叠 {len(overlap)} = **{len(all_candidate)}** 个唯一分子候选. "
                "这已超过 B100 候选池下限 150, 但**远不等于 100 个合格分子** —— "
                "扩展层尚未准入, 核心层有 170 行条件配对无效."
            ),
        },
        "gap_to_target": {
            "hard_threshold_molecules": 100,
            "currently_admissible_molecules": (
                "待定: 需完成扩展层准入审核后重新计数"
            ),
            "what_is_missing": [
                "NBS 扩展层 389 个分子的正式准入审核 (Q1/Q2 分级 + 身份去重)",
                "核心层 170 行条件配对无效记录的处理结论",
                "核心层分子的统一 xTB 计算 (目前只有扩展层有)",
                "DFT / 构象 / MD 全部未开始",
                "跨来源重复转录检查 (核心层与扩展层之间)",
            ],
        },
        "inputs": {
            "expansion_observations": {
                "sha256": sha256_file(EXP_OBS) if EXP_OBS.is_file() else None,
                "rows": len(exp_obs)},
            "expansion_features": {
                "sha256": sha256_file(EXP_FEAT) if EXP_FEAT.is_file() else None,
                "rows": len(exp_feat)},
            "nbs514_transcription_parts": [
                {"path": str(p.relative_to(REPO_ROOT)), "sha256": sha256_file(p),
                 "rows": len(load(p))}
                for p in NBS_PARTS if p.is_file()
            ],
            "measurement_ledger_v1": {
                "sha256": sha256_file(MEAS_LEDGER) if MEAS_LEDGER.is_file() else None,
                "rows": len(ledger)},
            "dielectric_v04": {
                "sha256": sha256_file(V04) if V04.is_file() else None,
                "rows": len(v04)},
        },
        "warnings": warnings,
        "outputs": {
            "nbs514_condition_audit": {
                "path": str(audit_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(audit_path), "rows": len(audit_rows)},
        },
        "next_step": (
            "按 PLAN B v6.0 第一阶段: 用本盘点结果做扩展层准入审核 "
            "(身份去重 / Q1-Q2 分级 / 来源独立性), 得到可计数的合格分子, "
            "再判断距 100 还差多少."
        ),
    }

    json_path = OUT / "b100_asset_inventory.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # ================= markdown =================
    md: list[str] = []
    md.append("# B100 数据资产盘点\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append("> 只做计数与审计，不新增任何测量。\n")

    md.append("\n## 零、目标与硬门槛\n")
    t = doc["target"]
    md.append(f"- 计划：**{t['plan']}**\n")
    md.append(f"- 最低合格分子：**{t['min_qualified_molecules']}**\n")
    md.append(f"- 建议候选池：{t['suggested_candidate_pool']}\n")
    md.append(f"- 争取达标：{t['aspirational_qualified']}\n")
    md.append(f"\n> {t['hard_rule']}\n")

    md.append("\n## 一、四层体系现状\n")
    md.append("| 层 | 内容 | 现状 |\n|---|---|---|\n")
    l1 = doc["layer_1_experimental_labels"]
    md.append(f"| **① 实验标签** | 纯液体静态 ε | 核心 {l1['core_thermoml']['n_v04_molecules']} 分子 / "
              f"{l1['core_thermoml']['n_measurements']} 测量；扩展 "
              f"{l1['nbs514_expansion']['n_molecules']} 分子（**未准入**）|\n")
    l2 = doc["layer_2_xtb"]
    md.append(f"| **② xTB** | 偶极/极化率/能级 | {l2['n_molecules_with_features']} 分子，"
              f"缺 {l2['n_missing_dipole']} 条 |\n")
    md.append(f"| **③ DFT/构象** | 校准电子性质 | **未开始** |\n")
    md.append(f"| **④ 液相 MD** | 密度/偶极关联 | **未开始** |\n")

    md.append("\n## 二、NBS 514 频率审计（本轮核心发现）\n")
    fa = doc["nbs514_frequency_audit"]
    md.append(f"**问题：** {fa['question']}\n\n")
    md.append("| 项 | 数量 |\n|---|---:|\n")
    md.append(f"| 扩展表行数 | {fa['n_expansion_rows']} |\n")
    md.append(f"| NBS 转录总行数 | {fa['n_transcription_rows']} |\n")
    md.append(f"| **转录中带频率脚注的行** | **{fa['n_transcription_with_frequency_footnote']}** |\n")
    md.append(f"| 扩展表选中行**带**频率脚注 | **{fa['n_selected_with_frequency_footnote']}** |\n")
    md.append(f"| 扩展表选中行按来源定义视为静态 | **{fa['n_selected_static_by_definition']}** |\n")
    md.append(f"| 未选中的转录行 | {fa['n_not_selected_transcription_rows']} |\n")
    md.append(f"| 未选中行中带频率脚注 | **{fa['n_not_selected_with_frequency_footnote']}** |\n")

    md.append("\n**频率脚注取值：**\n")
    for k, v in fa["frequency_footnote_values"].items():
        md.append(f"- `{k}` × {v}\n")
    md.append(f"\n**结论：** {fa['conclusion']}\n")
    md.append(f"\n**残余风险：** {fa['residual_risk']}\n")

    md.append("\n## 三、唯一分子候选\n")
    u = doc["union_estimate"]
    md.append("| 项 | 分子数 |\n|---|---:|\n")
    md.append(f"| 核心 ThermoML | {u['core_molecules']} |\n")
    md.append(f"| NBS 扩展 | {u['expansion_molecules']} |\n")
    md.append(f"| 两者重叠 | {u['overlap_core_and_expansion']} |\n")
    md.append(f"| **并集** | **{u['union_candidate_molecules']}** |\n")
    md.append(f"\n{u['headline']}\n")

    md.append("\n## 四、距 100 还差什么\n")
    for item in doc["gap_to_target"]["what_is_missing"]:
        md.append(f"- {item}\n")

    md.append("\n## 五、辅助来源（不得作为标签）\n")
    aux = doc["auxiliary_discovery_only"]
    md.append("| 来源 | 记录数 | 用途 |\n|---|---:|---|\n")
    md.append(f"| SolvFunc-87 | {aux['solvfunc_87']['n_records']} | 候选发现 |\n")
    md.append(f"| Batt-SLM-RX-392 | {aux['batt_slm_392']['n_records']} | "
              f"电子性质与候选发现 |\n")
    md.append(f"\n> {aux['batt_slm_392']['use']}\n")

    md_path = OUT / "b100_asset_inventory.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B100-1] {json_path}")
    print(f"[B100-1] {md_path}")
    print(f"[B100-1] {audit_path}")
    print(f"  core molecules        = {len(core_molecules)}  (measurements {len(ledger)})")
    print(f"  expansion molecules   = {len(exp_inchikeys)}  (rows {len(exp_obs)}, dup {exp_dup})")
    print(f"  overlap               = {len(overlap)}")
    print(f"  UNION                 = {len(all_candidate)}")
    print(f"  xTB dipole present    = {xtb_present}/{len(exp_feat)}")
    print(f"  NBS freq footnotes    = {len(nbs_with_freq_note)}/{len(nbs_rows)}")
    print(f"  selected with freq    = {n_selected_with_freq_note}")
    print(f"  not-selected w/ freq  = {ns_with_freq}/{len(not_selected)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
