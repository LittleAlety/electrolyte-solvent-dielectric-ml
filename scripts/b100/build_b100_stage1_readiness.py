#!/usr/bin/env python
"""B100-6: stage-1 readiness report -- the honest distance to 100 qualified molecules.

This assembles the asset inventory, admission gate, phase audit, melting-point lookup
and family registry into a single statement of where the project actually stands.

The purpose is to prevent the failure PLAN B v6.0 warns about: "计算了很多, 但真正
能够用于论文的只有二十几个分子". So the report leads with the hard number (how many
molecules are verified) rather than with the size of the candidate pool.

It also states explicitly what would be needed to close the gap, separating:
  * data that exists and only needs auditing
  * data that must be fetched from an external source
  * data that does not exist anywhere yet and would need new curation

Output: outputs/b100/B100_STAGE1_READINESS.md
        outputs/b100/b100_stage1_readiness.json
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
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "build_b100_stage1_readiness/1.0.0"

INVENTORY = OUT / "b100_asset_inventory.json"
GATE = OUT / "b100_admission_gate.json"
PHASE = OUT / "phase_state_audit_b100.json"
FAMILY = OUT / "family_coverage_b100.json"
MPLOOKUP = OUT / "pubchem_mp_lookup_b100.csv"
REGISTRY = OUT / "molecule_registry_b100.csv"
QUALIFIED = OUT / "qualified_molecules_b100.csv"
EXCLUDED = OUT / "excluded_molecules_b100.csv"
NBS_AUDIT = OUT / "nbs514_condition_audit.csv"
CROSS_CONFLICT = OUT / "cross_source_conflict_b100.csv"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def main() -> int:
    inv = jload(INVENTORY)
    gate = jload(GATE)
    phase = jload(PHASE)
    fam = jload(FAMILY)
    nf = jload(OUT / "neutral_filter_b100.json")
    xtb = jload(OUT / "xtb_coverage_b100.json")
    ids = jload(OUT / "identity_audit_b100.json")
    sv = jload(OUT / "smiles_verification_b100.json")
    si = jload(OUT / "source_independence_b100.json")
    mplook = load(MPLOOKUP)
    registry = load(REGISTRY)
    qualified = load(QUALIFIED)

    if not (inv and gate and phase and fam):
        print("FATAL: run the earlier B100 stages first", file=sys.stderr)
        return 2

    n_mp_with = sum(1 for r in mplook if (r.get("mp_C") or "").strip())
    n_mp_missing = len(mplook) - n_mp_with

    # recompute phase verification with the freshly-fetched melting points, so the
    # number reflects the data actually available now, not the first pass
    mp_by_key = {}
    for r in mplook:
        ik = (r.get("inchikey") or "").strip()
        v = (r.get("mp_C") or "").strip()
        if ik and v:
            try:
                mp_by_key[ik] = float(v)
            except ValueError:
                continue

    def fnum(v):
        s = (v or "").strip()
        if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    recheck_liquid = 0
    recheck_solid = 0
    recheck_unknown = 0
    solid_names: list[tuple[str, float, float]] = []
    for q in qualified:
        ik = q["inchikey"]
        t_k = fnum(q.get("T_K"))
        mp = mp_by_key.get(ik)
        if mp is None or t_k is None:
            recheck_unknown += 1
            continue
        t_c = t_k - 273.15
        if mp < t_c:
            recheck_liquid += 1
        else:
            recheck_solid += 1
            solid_names.append((q.get("name", ""), t_c, mp))

    hard = 100
    gap = max(0, hard - recheck_liquid)

    fam_rows = fam.get("family_coverage", [])
    fams_zero = [f["family"] for f in fam_rows if f["n_present"] == 0]
    fams_below = [f["family"] for f in fam_rows
                  if f["n_phase_verified"] < f["target_low"]]

    doc = {
        "schema": "b100.stage1_readiness/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "stage": "第一阶段（数据扩展与审计）",
        "headline": (
            f"候选池 {gate['result']['n_qualified_molecules']} 个分子通过第一轮准入, "
            f"其中 **{recheck_liquid}** 个经熔点验证在设定温度下确为液态"
            + (f", 剔除 {nf['result']['n_excluded']} 个离子液体/混合物"
               if nf else "")
            + f". 距硬门槛 {hard} 还差 **{gap}** 个."
        ),
        "integrity_filters": {
            "neutral_single_molecule": {
                "n_input": nf["n_input"] if nf else None,
                "n_excluded": nf["result"]["n_excluded"] if nf else None,
                "reasons": nf["exclusion_reasons"] if nf else None,
                "rule": ("PLAN B v6.0: 离子液体、混合物、金属配合物不混入"
                         "中性单分子核心数据集"),
            },
            "phase_liquid_at_stated_T": {
                "n_verified_liquid": recheck_liquid,
                "n_solid_or_supercooled": recheck_solid,
                "n_unknown_no_mp": recheck_unknown,
            },
            "identity_inchikey": {
                "status_counts": ids["status_counts"] if ids else None,
                "note": ("InChIKey 由记录的 SMILES 重算, 必须一致. "
                         "但 InChI 归一化可移动氢, 因此该检查抓不到互变异构体替换"),
            },
            "tautomer_smiles_vs_pubchem": {
                "verdict_counts": sv["verdict_counts"] if sv else None,
                "n_usable": sv["n_usable_after_check"] if sv else None,
                "note": ("用 PubChem 权威 SMILES 复核. 发现的 1 例 "
                         "(N-甲基乙酰胺被写成亚胺酸) 已用正确酰胺 SMILES 重算, "
                         "偶极由 1.07 D 修正为 4.34 D"),
            },
            "xtb_protocol_unified": {
                "n_with_xtb": xtb["coverage"]["n_with_xtb"] if xtb else None,
                "n_phase_verified": xtb["coverage"]["n_phase_verified"]
                if xtb else None,
                "protocol": xtb["protocol"]["id"] if xtb else None,
                "note": ("全部 GFN2-xTB 几何优化, 同一命令同一二进制; "
                         "新增 16 个核心层分子后覆盖率 100%"),
            },
            "source_independence": {
                "by_evidence_grade": si["qualified_set"]["by_evidence_grade"]
                if si else None,
                "n_independently_corroborated":
                    si["source_structure"]["independently_corroborated"]["n_molecules"]
                    if si else None,
                "claim_permitted": si["claim_permission"]["claim_permitted"]
                if si else None,
                "critical_point": (
                    "226/257 来自 NBS Circular 514 单一编校来源, "
                    "其内部一致性不构成独立复现. 跨来源结论只能基于被独立印证的分子"
                    "与核心层 Q1 分子."),
            },
        },
        "hard_numbers": {
            "union_candidate_molecules": inv["union_estimate"]["union_candidate_molecules"],
            "core_thermoml_molecules": inv["union_estimate"]["core_molecules"],
            "nbs514_molecules": inv["union_estimate"]["expansion_molecules"],
            "overlap": inv["union_estimate"]["overlap_core_and_expansion"],
            "admission_pass_first_round": gate["result"]["n_qualified_molecules"],
            "phase_verified_liquid_now": recheck_liquid,
            "also_verified_solid": recheck_solid,
            "still_unknown_no_mp": recheck_unknown,
            "hard_threshold": hard,
            "gap": gap,
            "meets_threshold": recheck_liquid >= hard,
        },
        "melting_point_lookup": {
            "n_rows": len(mplook),
            "n_with_mp": n_mp_with,
            "n_missing_mp": n_mp_missing,
            "hit_rate": round(n_mp_with / max(len(mplook), 1), 3),
            "note": (
                "PubChem 的实验熔点覆盖率约 40-45%. 未命中不等于分子无熔点, "
                "而是该库无可用实验值; 需从原始文献补充, 不得估算填充."
            ),
        },
        "family_status": {
            "families_with_zero_molecules": fams_zero,
            "families_below_target_low": fams_below,
            "n_families_present": fam["family_totals"]["families_present"],
            "epsilon_distribution": fam["epsilon_distribution"],
            "note": (
                "PLAN B v6.0 要求 8-12 个家族分层. 当前已覆盖多数家族, "
                "但仍有家族为 0, 必须补充而非用相近家族替代."
            ),
        },
        "known_defects_found_and_fixed_in_stage1": [
            {
                "defect": "家族规则 SMARTS 被逗号分割破坏",
                "impact": (
                    "amine 的正则 [NX3;H2,H1,H0;!$(NC=O)] 内含逗号, 被 "
                    "split(',') 切成三段无效片段, 导致 28 个含胺基分子被误归"
                    "为醇类, amine 家族计数为 0"),
                "fix": "规则表改为 SMARTS 元组, 不再按逗号切分; 并重排优先级",
                "verification": "amine 由 0 恢复为 23 个",
            },
            {
                "defect": "相态审计只覆盖 22 个分子",
                "impact": "306 个『合格』分子中 290 个从未检查相态",
                "fix": "把同一判据扩展到全部候选 (B100-3)",
                "verification": "37 个通过相态验证, 其余标记 UNKNOWN 而非默认液态",
            },
            {
                "defect": "v04 有 135/248 行无法追溯到账本",
                "impact": (
                    "这些行的 value 无 measurement 支撑, 不能进入以"
                    "测量级可追溯为核心价值的数据集"),
                "fix": "准入时标记 UNTRACEABLE 并排除出合格集",
                "verification": "core traceability = 113 matched / 135 untraceable",
            },
        ],
        "nbs514_frequency_finding": {
            "summary": inv["nbs514_frequency_audit"]["conclusion"],
            "n_footnotes": inv["nbs514_frequency_audit"][
                "n_transcription_with_frequency_footnote"],
            "selected_with_footnote": inv["nbs514_frequency_audit"][
                "n_selected_with_frequency_footnote"],
            "verdict": (
                "扩展层 392 行全部来自不带频率脚注的转录行, "
                "空白 frequency_mhz 属来源级静态定义, 按 Q2 处理"),
        },
        "cross_source_check": {
            "n_in_both_layers": gate["cross_source_check"]["n_molecules_in_both_layers"],
            "n_agree": gate["cross_source_check"]["n_agree"],
            "n_conflict": gate["cross_source_check"]["n_conflict"],
            "assessment": (
                "136 对一致 / 11 对冲突. 高一致率说明两层介电数值总体可信; "
                "11 个冲突已单独登记, 未取平均."),
        },
        "paths_to_close_the_gap": {
            "a_audit_existing": [
                (
                    f"补充 {recheck_unknown} 个缺熔点分子的熔点 (PubChem 已尽力, "
                    "剩余需原始文献)"),
                "把 v04 中 135 个 UNTRACEABLE 行追溯回原始文档或正式排除",
                "对 NBS 扩展层做来源独立性检查 (全部来自 NBS 514 单一汇编, "
                "不构成来源稳健性证据)",
            ],
            "b_fetch_external": [
                "Chodera 2015 (45 SMILES) 与 LiquidBenchmark (69 记录) 交叉核查",
                "补入 PLAN B v6.0 要求但当前为 0 的家族 (amide / nitro 等)",
            ],
            "c_new_curation": [
                "DFT / 构象 / MD 三层尚未开始, 需要新的计算",
                "xTB 只覆盖 NBS 扩展层; 核心层 64 个合格分子尚无 xTB 特征",
            ],
            "explicitly_forbidden": [
                "降低准入标准以凑够 100",
                "用缺少熔点的分子默认当作液态",
                "把同一分子的多条测量记成多个独立分子",
                "对跨来源冲突取平均",
            ],
        },
        "inputs": {
            "b100_asset_inventory": {"sha256": sha256_file(INVENTORY)},
            "b100_admission_gate": {"sha256": sha256_file(GATE)},
            "phase_state_audit_b100": {"sha256": sha256_file(PHASE)},
            "family_coverage_b100": {"sha256": sha256_file(FAMILY)},
            "pubchem_mp_lookup_b100": {
                "sha256": sha256_file(MPLOOKUP) if MPLOOKUP.is_file() else None,
                "rows": len(mplook)},
            "molecule_registry_b100": {"rows": len(registry)},
        },
    }

    j_path = OUT / "b100_stage1_readiness.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    # ---------- markdown ----------
    hn = doc["hard_numbers"]
    md: list[str] = []
    md.append("# B100 第一阶段就绪报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · {doc['generated_at_utc']}\n")
    md.append(f"> 阶段：{doc['stage']}\n")

    md.append("\n## 零、一句话\n")
    md.append(f"{doc['headline']}\n")

    md.append("\n## 一、硬数字\n")
    md.append("| 项 | 数量 |\n|---|---:|\n")
    md.append(f"| 并集分子候选 | {hn['union_candidate_molecules']} |\n")
    md.append(f"| 核心 ThermoML | {hn['core_thermoml_molecules']} |\n")
    md.append(f"| NBS 514 扩展 | {hn['nbs514_molecules']} |\n")
    md.append(f"| 两层重叠 | {hn['overlap']} |\n")
    md.append(f"| 首轮准入通过 | {hn['admission_pass_first_round']} |\n")
    md.append(f"| **相态验证为液体的** | **{hn['phase_verified_liquid_now']}** |\n")
    md.append(f"| 验证为固态/过冷 | {hn['also_verified_solid']} |\n")
    md.append(f"| 仍缺熔点数据 | {hn['still_unknown_no_mp']} |\n")
    md.append(f"| **硬门槛** | **{hn['hard_threshold']}** |\n")
    md.append(f"| **差距** | **{hn['gap']}** |\n")

    md.append("\n## 二、NBS 514 频率审计结论\n")
    f = doc["nbs514_frequency_finding"]
    md.append(f"{f['summary']}\n\n")
    md.append(f"**判定：** {f['verdict']}\n")

    md.append("\n## 三、跨来源协和检查\n")
    c = doc["cross_source_check"]
    md.append(f"- 两层共有分子：{c['n_in_both_layers']}\n")
    md.append(f"- 一致：**{c['n_agree']}**\n")
    md.append(f"- 冲突：**{c['n_conflict']}**\n")
    md.append(f"\n{c['assessment']}\n")

    md.append("\n## 四、家族覆盖\n")
    md.append(f"- 已有分子家族：{doc['family_status']['n_families_present']}\n")
    if fams_zero:
        md.append(f"- **完全为 0 的家族：** {', '.join(fams_zero)}\n")
    md.append(f"\n介电常数分布：`{doc['family_status']['epsilon_distribution']}`\n")

    md.append("\n## 六、完整性过滤（本轮新增）\n")
    inf = doc["integrity_filters"]
    md.append("| 过滤层 | 结果 |\n|---|---|\n")
    md.append(f"| 中性单分子 | 排除 **{inf['neutral_single_molecule']['n_excluded']}** "
              f"个离子液体/混合物 |\n")
    md.append(f"| 设定温度下为液体 | **{inf['phase_liquid_at_stated_T']['n_verified_liquid']}** "
              f"个通过, {inf['phase_liquid_at_stated_T']['n_solid_or_supercooled']} "
              f"个固态/过冷, {inf['phase_liquid_at_stated_T']['n_unknown_no_mp']} "
              f"个缺熔点 |\n")
    md.append(f"| InChIKey 身份 | "
              f"`{inf['identity_inchikey']['status_counts']}` |\n")
    md.append(f"| 互变异构体复核 | "
              f"`{inf['tautomer_smiles_vs_pubchem']['verdict_counts']}` |\n")
    md.append(f"| 统一 xTB 协议 | "
              f"{inf['xtb_protocol_unified']['n_with_xtb']}/"
              f"{inf['xtb_protocol_unified']['n_phase_verified']} |\n")
    md.append(f"| 来源独立性 | Q1={inf['source_independence']['by_evidence_grade']}, "
              f"独立印证 "
              f"{inf['source_independence']['n_independently_corroborated']} 个 |\n")

    md.append("\n### 必须记住的保留意见\n")
    md.append(f"- {inf['identity_inchikey']['note']}\n")
    md.append(f"- {inf['tautomer_smiles_vs_pubchem']['note']}\n")
    md.append(f"- {inf['source_independence']['critical_point']}\n")

    md.append("\n## 七、第一阶段发现并修复的缺陷\n")
    for d in doc["known_defects_found_and_fixed_in_stage1"]:
        md.append(f"\n### {d['defect']}\n")
        md.append(f"- **影响：** {d['impact']}\n")
        md.append(f"- **修复：** {d['fix']}\n")
        md.append(f"- **验证：** {d['verification']}\n")

    md.append("\n## 六、补齐差距的路径\n")
    p = doc["paths_to_close_the_gap"]
    md.append("\n**A. 审计已有数据**\n")
    for x in p["a_audit_existing"]:
        md.append(f"- {x}\n")
    md.append("\n**B. 从外部补充**\n")
    for x in p["b_fetch_external"]:
        md.append(f"- {x}\n")
    md.append("\n**C. 需要新的整理工作**\n")
    for x in p["c_new_curation"]:
        md.append(f"- {x}\n")
    md.append("\n**明确禁止**\n")
    for x in p["explicitly_forbidden"]:
        md.append(f"- ❌ {x}\n")

    md_path = OUT / "B100_STAGE1_READINESS.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B100-6] {j_path}")
    print(f"[B100-6] {md_path}")
    print(f"  union candidates     = {hn['union_candidate_molecules']}")
    print(f"  admission pass       = {hn['admission_pass_first_round']}")
    print(f"  PHASE-VERIFIED LIQUID= {hn['phase_verified_liquid_now']}")
    print(f"  hard threshold       = {hn['hard_threshold']}   gap = {hn['gap']}")
    print(f"  mp lookup            = {n_mp_with}/{len(mplook)}")
    print(f"  families at zero     = {fams_zero}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
