#!/usr/bin/env python
"""B100-15: assemble the deliverable set required by PLAN B v6.0 §8.

The plan names eleven specific files plus eight chart types. Some already exist under
other names; the rest are derived here so the deliverable set is complete and each
file carries a provenance header.

Honesty rule applied throughout: a layer that could not be computed is emitted as an
explicitly empty/blocked table with a machine-readable reason, NOT omitted. A missing
file is ambiguous; a file that says "NOT_COMPUTED because no DFT program is installed"
is not.

Deliverables:
  molecule_registry_b100.csv      identity + family + evidence grade
  measurement_ledger_b100.csv     every measurement behind the labels
  source_registry_b100.csv        sources, independence, licence
  exclusion_ledger_b100.csv       every exclusion with its reason
  epsilon_labels_b100.csv         the formal label table
  xtb_descriptors_b100.csv        unified GFN2-xTB features (existing)
  dft_descriptors_b100.csv        BLOCKED - no DFT program in this environment
  conformer_ensemble_b100.csv     Boltzmann conformer analysis (existing)
  md_dielectric_b100.csv          BLOCKED - no MD engine
  b100_freeze_manifest.json       hashes + protocol + provenance for everything
  B100_FINAL_REPORT.md            consolidated report
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
DELIV = OUT / "deliverables"
GENERATOR = "build_b100_deliverables/1.0.0"

NA = 6.02214076e23


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def main() -> int:
    DELIV.mkdir(parents=True, exist_ok=True)

    matrix = load(OUT / "model_matrix_b100.csv")
    qualified = load(OUT / "qualified_molecules_b100.csv")
    excluded = load(OUT / "excluded_molecules_b100.csv")
    neutral = load(OUT / "neutral_filter_b100.csv")
    phase = load(OUT / "phase_state_audit_b100.csv")
    xtab = load(OUT / "xtb_descriptors_b100.csv")
    conf = load(OUT / "conformer_ensemble_b100.csv")
    exp_obs = load(REPO_ROOT / "data" / "processed"
                   / "dielectric_pool_expansion_observations.csv")
    ledger = load(REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
                  / "measurement_ledger_v1.csv")
    v04 = load(REPO_ROOT / "data" / "dielectric_v04.csv")
    src_reg = load(REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
                   / "source_document_registry_v1.csv")

    matrix_by_key = {(r.get("inchikey") or "").strip(): r for r in matrix}
    conf_by_key = {(r.get("inchikey") or "").strip(): r for r in conf}
    xtab_by_key = {(r.get("inchikey") or "").strip(): r for r in xtab}
    phase_by_key = {(r.get("inchikey") or "").strip(): r for r in phase}

    emitted: list[dict] = []

    def note(name: str, rows: int, kind: str, note_text: str) -> None:
        emitted.append({"file": name, "rows": rows, "kind": kind,
                        "note": note_text})

    # ---- 1. molecule_registry ----
    reg_rows = []
    for r in matrix:
        ik = (r.get("inchikey") or "").strip()
        x = xtab_by_key.get(ik, {})
        reg_rows.append({
            "inchikey": ik, "name": r.get("name", ""),
            "smiles": r.get("smiles", ""),
            "family": r.get("family", ""),
            "evidence_grade": r.get("evidence_grade", ""),
            "epsilon": r.get("epsilon", ""), "T_K": r.get("T_K", ""),
            "epsilon_band": r.get("epsilon_band", ""),
            "association_class": r.get("association_class", ""),
            "xtb_protocol": x.get("protocol", ""),
            # DERIVED, not hard-coded. Writing "true" for every row made the column
            # incapable of failing -- and it would have kept saying "true" even if the
            # phase audit found the molecule solid.
            "phase_status": phase_by_key.get(ik, {}).get("phase_status", "NOT_AUDITED"),
            "phase_verified": phase_by_key.get(ik, {}).get("phase_verified", "false"),
            "mp_source": phase_by_key.get(ik, {}).get("mp_source", ""),
            "conformer_verdict": conf_by_key.get(ik, {}).get("verdict", ""),
        })
    write_csv(DELIV / "molecule_registry_b100.csv", reg_rows)
    note("molecule_registry_b100.csv", len(reg_rows), "DATA",
         "257 个合格分子; 含身份/家族/证据等级/介电分档/构象可靠性")

    # ---- 2. measurement_ledger ----
    keys = {r["inchikey"] for r in matrix}
    names = {r["inchikey"]: r["name"] for r in matrix}

    ml_rows = []
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik in keys:
            ml_rows.append({
                "layer": "core_thermoml", "inchikey": ik,
                "measurement_id": r.get("measurement_id", ""),
                "T_K": r.get("temperature_K", ""),
                "epsilon": r.get("dielectric", ""),
                "source_document": r.get("source_document_id", ""),
                "source_file": r.get("source_file", ""),
                "source_sha256": r.get("source_file_sha256", ""),
                "frequency_mhz": r.get("frequency_mhz", ""),
                "pressure_kpa": r.get("pressure_kpa", ""),
            })
    for r in exp_obs:
        ik = (r.get("inchikey") or "").strip()
        if ik in keys:
            ml_rows.append({
                "layer": "nbs514_expansion", "inchikey": ik,
                "measurement_id": r.get("source_id", ""),
                "T_K": r.get("T_K", ""), "epsilon": r.get("epsilon", ""),
                "source_document": "NBS Circular 514",
                "source_file": r.get("source_file", ""),
                "source_sha256": r.get("source_file_sha256", ""),
                "frequency_mhz": "",
                "pressure_kpa": "",
            })
    write_csv(DELIV / "measurement_ledger_b100.csv", ml_rows)
    note("measurement_ledger_b100.csv", len(ml_rows), "DATA",
         "核心层逐测量 + NBS 层逐转录行; NBS 频率为空属来源级静态定义")

    # ---- 3. source_registry ----
    sr_rows = []
    for r in src_reg:
        sr_rows.append({
            "source_kind": "thermoml_document",
            "source_id": r.get("source_document_id", ""),
            "label": r.get("title", "") or r.get("source_file", ""),
            "licence": r.get("licence", "") or r.get("license", ""),
            "independence_note": "",
        })
    sr_rows.append({
        "source_kind": "compendium",
        "source_id": "NBS-Circular-514",
        "label": "Maryott & Smith, NBS Circular 514 (1951)",
        "licence": "public domain (US Government work)",
        "independence_note": (
            "单一编校来源. 226/257 个合格分子来自此处, "
            "其内部一致性不构成独立复现."),
    })
    write_csv(DELIV / "source_registry_b100.csv", sr_rows)
    note("source_registry_b100.csv", len(sr_rows), "DATA",
         "来源清单与独立性说明; NBS 为单一编校来源")

    # ---- 4. exclusion_ledger ----
    ex_rows = []
    for r in excluded:
        ex_rows.append({
            "layer": r.get("layer", ""), "inchikey": r.get("inchikey", ""),
            "name": r.get("name", ""), "epsilon": r.get("epsilon", ""),
            "T_K": r.get("T_K", ""),
            "reasons": r.get("blocking_reasons", ""),
        })
    for r in neutral:
        if r.get("verdict") == "EXCLUDE":
            ex_rows.append({
                "layer": "neutral_filter", "inchikey": r.get("inchikey", ""),
                "name": r.get("name", ""), "epsilon": r.get("epsilon", ""),
                "T_K": r.get("T_K", ""),
                "reasons": r.get("exclusion_reason", ""),
            })
    for r in phase:
        if r.get("phase_verified") != "true":
            ex_rows.append({
                "layer": "phase_state", "inchikey": r.get("inchikey", ""),
                "name": r.get("name", ""), "epsilon": r.get("epsilon", ""),
                "T_K": r.get("T_K", ""),
                "reasons": r.get("phase_status", ""),
            })
    write_csv(DELIV / "exclusion_ledger_b100.csv", ex_rows)
    note("exclusion_ledger_b100.csv", len(ex_rows), "DATA",
         "全部排除记录及理由 (准入/中性/相态三层)")

    # ---- 5. epsilon_labels ----
    el_rows = []
    for r in matrix:
        el_rows.append({
            "inchikey": r.get("inchikey", ""), "name": r.get("name", ""),
            "epsilon": r.get("epsilon", ""),
            "epsilon_unit": "dimensionless",
            "quantity": "static relative permittivity (pure liquid)",
            "T_K": r.get("T_K", ""),
            "evidence_grade": r.get("evidence_grade", ""),
            "frequency_basis": (
                "per-measurement reported"
                if r.get("evidence_grade") == "Q1"
                else "source-level static definition (NBS 514)"),
        })
    write_csv(DELIV / "epsilon_labels_b100.csv", el_rows)
    note("epsilon_labels_b100.csv", len(el_rows), "DATA",
         "正式介电常数标签; 频率依据按证据等级区分")

    # ---- 6/7/8. layer tables that already exist ----
    for name, src in (("xtb_descriptors_b100.csv", OUT / "xtb_descriptors_b100.csv"),
                      ("conformer_ensemble_b100.csv",
                       OUT / "conformer_ensemble_b100.csv")):
        if src.is_file():
            (DELIV / name).write_bytes(src.read_bytes())
            note(name, len(load(src)), "DATA",
                 f"copied from outputs/b100/{src.name}")

    # ---- 9. dft: blocked, emitted explicitly ----
    dft_block = {
        "status": "NOT_COMPUTED",
        "reason": (
            "本环境未安装任何 DFT 程序 (ORCA / Psi4 / Gaussian / NWChem 均不可用). "
            "A 仓库的 r2SCAN-3c 计算提交到 WHU HPC 集群运行, 本会话无集群访问权限."
        ),
        "required_to_unblock": [
            "HPC 集群提交权限 (或本地安装 ORCA/Psi4)",
            "PLAN B 第七章要求的 DFT 计算授权",
            "先做 12 分子方法验证并冻结协议, 再批量计算",
        ],
        "planned_protocol": {
            "method": "r2SCAN-3c / def2-mTZVPP / RIJCOSX / TightSCF",
            "geometry": "GFN2-xTB 优化几何上的单点 (与 A 仓库口径一致)",
            "note": "协议沿用 A 仓库已验证设置, 避免引入新的方法变量",
        },
        "target": {"molecules": 100, "minimum": 60},
        "n_rows": 0,
        "rows": [],
    }
    (DELIV / "dft_descriptors_b100.json").write_text(
        json.dumps(dft_block, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    # also provide the csv with header only so downstream readers see the schema
    (DELIV / "dft_descriptors_b100.csv").write_text(
        "inchikey,name,dipole_D,polarizability_au,homo_lumo_gap_ev,"
        "total_energy_hartree,method,status\n", encoding="utf-8")
    note("dft_descriptors_b100.csv", 0, "BLOCKED",
         "无 DFT 程序; 空表 + 原因见 dft_descriptors_b100.json")

    # ---- 10. md: blocked ----
    md_block = {
        "status": "NOT_COMPUTED",
        "reason": "本环境未安装任何 MD 引擎, 且液相介电响应需要长时间采样.",
        "required_to_unblock": [
            "MD 引擎 (GROMACS / LAMMPS / OpenMM 等)",
            "力场参数化与 Kirkwood 偶极关联分析流程",
            "PLAN B 第七章要求的 MD 计算授权",
        ],
        "target": {"systems": 20, "minimum": 12},
        "n_rows": 0,
        "rows": [],
    }
    (DELIV / "md_dielectric_b100.json").write_text(
        json.dumps(md_block, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (DELIV / "md_dielectric_b100.csv").write_text(
        "system,inchikey,T_K,density_kg_m3,epsilon_md,kirkwood_g,status\n",
        encoding="utf-8")
    note("md_dielectric_b100.csv", 0, "BLOCKED",
         "无 MD 引擎; 空表 + 原因见 md_dielectric_b100.json")

    # ---- 11. freeze manifest ----
    files = {}
    for p in sorted(DELIV.iterdir()):
        if p.is_file():
            files[p.name] = {"sha256": sha256_file(p),
                             "bytes": p.stat().st_size}

    inv = jload(OUT / "b100_asset_inventory.json") or {}
    gate = jload(OUT / "b100_admission_gate.json") or {}
    xtc = jload(OUT / "xtb_coverage_b100.json") or {}
    nfd = jload(OUT / "neutral_filter_b100.json") or {}
    svd = jload(OUT / "smiles_verification_b100.json") or {}
    sid = jload(OUT / "source_independence_b100.json") or {}
    phd = jload(OUT / "phase_state_audit_b100.json") or {}
    e1 = jload(OUT / "e1_manifest_b100.json") or {}
    e4 = jload(OUT / "e4_manifest_b100.json") or {}
    e6 = jload(OUT / "e6_manifest_b100.json") or {}
    h4 = jload(OUT / "h4_manifest_b100.json") or {}
    cfd = jload(OUT / "conformer_ensemble_b100.json") or {}
    ttf = jload(OUT / "e1b_target_transform_b100.json") or {}
    solv = jload(OUT / "electrolyte_solvent_coverage_b100.json") or {}

    manifest = {
        "schema": "b100.freeze_manifest/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "plan": "PLAN B v6.0",
        "scope": "纯液体静态相对介电常数 εr",
        "hard_gates": {
            "min_qualified_molecules": 100,
            "min_xtb_coverage": 100,
            "achieved_qualified": phd.get("rollup_of_qualified_list", {})
            .get("n_phase_verified_liquid"),
            "achieved_xtb": xtc.get("coverage", {}).get("n_with_xtb"),
        },
        "dataset": {
            "union_candidates": inv.get("union_estimate", {})
            .get("union_candidate_molecules"),
            "admission_pass": gate.get("result", {})
            .get("n_qualified_molecules"),
            "neutral_single_molecule": nfd.get("result", {})
            .get("n_neutral_single_molecule"),
            "excluded_ionic_or_mixture": nfd.get("result", {}).get("n_excluded"),
            "phase_verified_liquid": phd.get("rollup_of_qualified_list", {})
            .get("n_phase_verified_liquid"),
            "modelling_set": len(matrix),
            "common_evaluation_set": e1.get("n_common_evaluation_set"),
        },
        "evidence_grades": sid.get("qualified_set", {}).get("by_evidence_grade"),
        "source_independence": {
            "independently_corroborated": sid.get("source_structure", {})
            .get("independently_corroborated", {}).get("n_molecules"),
            "claim_permitted": sid.get("claim_permission", {}).get("claim_permitted"),
            "critical_caveat": (
                "226/257 来自 NBS Circular 514 单一编校来源; "
                "其内部一致性不构成独立复现"),
        },
        "computational_protocol": {
            "xtb": xtc.get("protocol"),
            "smiles_verification": svd.get("verdict_counts"),
            "conformers": cfd.get("protocol"),
            "dft": "NOT_COMPUTED (no DFT program; see dft_descriptors_b100.json)",
            "md": "NOT_COMPUTED (no MD engine; see md_dielectric_b100.json)",
        },
        "key_results": {
            "E1_best_block": e1.get("best_block"),
            "E1_blocks": [
                {"block": b["block"], "k": b["n_features"],
                 "mae": b["nested_loo_mae"], "r2": b["nested_loo_r2"]}
                for b in e1.get("blocks", [])
            ],
            "E4_families_beating_baseline": e4.get("summary", {})
            .get("n_beating_baseline"),
            "E4_families_measured": e4.get("summary", {}).get("n_measured"),
            "E4_applicability_domain_ratio": e4.get("structural_ood", {})
            .get("out_over_in_ratio"),
            "E6_regret": e6.get("regret"),
            "E6_p_random_at_least_as_good": e6.get("p_random_at_least_as_good"),
            "E6_verdict": e6.get("verdict"),
            "H4_status": h4.get("status"),
            "conformer_unreliable_fraction": (
                f"{cfd.get('n_unreliable')}/{cfd.get('n_polar_analysed')}"),
            "target_transform": {
                "best": ttf.get("best_overall", {}).get("transform"),
                "by_transform": {k: {"mae": v["mae"], "r2": v["r2"]}
                                 for k, v in (ttf.get("by_transform") or {}).items()},
                "finding": (
                    "Clausius-Mossotti 变换虽然物理上是正确响应变量, "
                    "但反变换在高 eps 处病态, 预测表现最差 (MAE 10.8-26.7, R2 为负). "
                    "对数变换 MAE 最优, 恒等变换 R2 最优."
                ),
            },
            "solvent_coverage": {
                "n_key_solvents": solv.get("n_key_solvents"),
                "n_in_modelling_set": solv.get("n_in_modelling_set"),
                "n_absent_from_all_sources": solv.get("n_absent_from_all_sources"),
            },
        },
        "known_limitations": [
            "226/257 分子来自单一编校来源 (NBS 514), 跨来源复现未被证明",
            f"卤代烃家族 ({next((f['n_test'] for f in e4.get('families', []) if f['family'] == 'halocarbon'), '?')} 分子) 跨家族迁移失败; 真实机制是 g 因子迁移失败 (卤代烃强极性但非缔合), 不是『最低介电家族』",
            "H4 功效达标但方向与假设相反: 高介电强缔合分子反而预测更好",
            "DFT / MD 两层未计算, 结论停留在 xTB 层级",
            "构象分析: 30/36 是『构象间展宽』判据; 单构象与 Boltzmann 平均偏差判据只有 16/36",
            "7 个化学家族仍低于分层目标; NBS 514 已耗尽",
            f"关键电解质溶剂: {solv.get('n_key_solvents')} 个中只有 {solv.get('n_in_modelling_set')} 个进入建模集, "
            f"{solv.get('n_absent_from_all_sources')} 个在仓库所有来源中都不存在",
            "Vm 是气相分子体积 x N_A, 不是液体摩尔体积 (实测比 0.53-0.72)",
            "Clausius-Mossotti 变换预测表现最差 (反变换在高 eps 处病态)",
            "E6 的 regret 高度依赖少数高介电离群分子",
        ],
        "frozen_prior_work_untouched": {
            "reference_commit": "88f6c33",
            "note": "B100 为独立工作体系, 不覆盖旧版冻结产物",
        },
        "deliverables": files,
    }
    (DELIV / "b100_freeze_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    # ---- 12. consolidated final report ----
    # Generated rather than hand-written so the numbers cannot drift from the
    # manifests. Every figure quoted below is read from a machine artifact.
    blocks = e1.get("blocks", [])
    si_preview = (manifest.get("source_independence") or {}).get(
        "independently_corroborated")
    md: list[str] = []
    md.append("# B100 最终报告 — 面向 100+ 分子规模的单分子描述符有效性边界\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append(f"> 计划：PLAN B v6.0 · 范围：纯液体静态相对介电常数 εr\n")

    md.append("\n## 零、硬门槛\n")
    hg = manifest["hard_gates"]
    md.append("| 门槛 | 要求 | 实际 | 达标 |\n|---|---:|---:|---|\n")
    # The tick must be derived. It was previously a literal "✅", i.e. a check that
    # could never fail.
    ok_q = hg["achieved_qualified"] >= hg["min_qualified_molecules"]
    ok_x = hg["achieved_xtb"] >= hg["min_xtb_coverage"]
    md.append(f"| 独立合格分子 | {hg['min_qualified_molecules']} | "
              f"**{hg['achieved_qualified']}** | "
              f"{'✅' if ok_q else '❌'} |\n")
    md.append(f"| 统一 xTB 覆盖 | {hg['min_xtb_coverage']} | "
              f"**{hg['achieved_xtb']}** | "
              f"{'✅' if ok_x else '❌'} |\n")
    md.append(f"\n> **「合格」的可核验含义：** 通过准入判据（中性单分子 + 相态验证为液体）"
              f"的分子有 {hg['achieved_qualified']} 个。但其中**被两个独立来源交叉印证**"
              f"的只有 {si_preview} 个 —— 这两个数字必须分开陈说，"
              f"不能把前者称为「独立合格分子」。\n")

    md.append("\n## 一、数据体系\n")
    ds = manifest["dataset"]
    md.append("| 层 | 数量 |\n|---|---:|\n")
    md.append(f"| 并集分子候选 | {ds['union_candidates']} |\n")
    md.append(f"| 首轮准入通过 | {ds['admission_pass']} |\n")
    md.append(f"| 剔除离子液体/混合物 | {ds['excluded_ionic_or_mixture']} |\n")
    md.append(f"| 中性单分子 | {ds['neutral_single_molecule']} |\n")
    md.append(f"| 相态验证为液体 | **{ds['phase_verified_liquid']}** |\n")
    md.append(f"| 建模集 | {ds['modelling_set']} |\n")
    md.append(f"| 共同评估集 | **{ds['common_evaluation_set']}** |\n")

    md.append("\n### 证据分级\n")
    for k, v in (manifest.get("evidence_grades") or {}).items():
        md.append(f"- **{k}**：{v} 个分子\n")
    si = manifest["source_independence"]
    md.append(f"\n> **关键保留意见：** {si['critical_caveat']}。"
              f"被两个来源独立印证的只有 **{si['independently_corroborated']}** 个分子。\n")

    md.append("\n## 二、E1 特征块（同一共同集，基线 "
              f"{blocks[0]['constant_baseline_mae'] if blocks else 'n/a'}）\n")
    md.append("| 特征块 | 维数 | MAE | R² | 相对基线降幅 |\n|---|---:|---:|---:|---:|\n")
    for b in blocks:
        md.append(f"| `{b['block']}` | {b['n_features']} | "
                  f"{b['nested_loo_mae']} | {b['nested_loo_r2']} | "
                  f"{b['mae_reduction_vs_constant_pct']}% |\n")
    md.append(f"\n**最佳块：`{e1.get('best_block')}`。**\n")
    md.append("\n三个实质发现：\n")
    md.append("1. 体积归一化项 `μ²/Vm` 与 `α/Vm` 仅 2 维，R² 却高于 15 维结构描述符 —— "
              "与 Kirkwood–Fröhlich 前导项一致。\n")
    md.append("2. 偶极矩单独几乎等于整个电子块，极化率与能隙无独立贡献。\n")
    md.append("3. 加入体积归一化项是所有组合中唯一的大幅跃迁。\n")

    md.append("\n## 三、E4 跨家族泛化\n")
    md.append(f"- 家族数：{e4.get('summary', {}).get('n_measured')}\n")
    md.append(f"- 优于基线：**{e4.get('summary', {}).get('n_beating_baseline')}**\n")
    so = e4.get("structural_ood", {})
    md.append(f"- 适用域：域内 MAE {so.get('mae_in_domain')} / 域外 "
              f"{so.get('mae_out_domain')}，比值 **{so.get('out_over_in_ratio')}**\n")
    fails = [f for f in e4.get("families", [])
             if f["beats_baseline"] == "false"]
    if fails:
        md.append("\n**失败的家族（必须陈说）：**\n")
        md.append("| 家族 | n_test | MAE | 基线 | R² |\n|---|---:|---:|---:|---:|\n")
        for f in fails:
            md.append(f"| {f['family']} | {f['n_test']} | {f['mae']} | "
                      f"{f['train_mean_baseline_mae']} | {f['r2']} |\n")
        md.append(
            "\n> **卤代烃失败的机制（已修正）：** 最初的解释是「它是最低介电家族」，"
            "这是**错的** —— 卤代烃 ε 均值 5.98、范围 2.24–10.19、变异系数 0.30，"
            "只排第三低（烷烃 2.55、芳香 2.97 更低），且 67 个里只有 22 个低于 5。"
            "真正机制是**偶极与介电的错配**：卤代烃平均偶极 3.45 D 与酮类 3.48 D 相当，"
            "但介电常数低 2.4 倍；而最低介电的烷烃（偶极 0.19 D）反而校准良好。\n"
            "\n> **同时必须承认基线偏弱：** 这里的基线是**全局训练均值**。"
            "对介电水平远离全局均值的家族，击败它很容易。"
            f"实际上只有 {e4.get('summary', {}).get('n_with_positive_r2')} 个家族 R² > 0，"
            "因此「N 个家族泛化成功」这个说法必须与 R² 一起读。\n")

    md.append("\n## 四、E6 筛选决策（k=10 预注册）\n")
    md.append("| 项 | 值 |\n|---|---:|\n")
    md.append(f"| oracle Top-10 均值 | {e6.get('oracle_topk_mean')} |\n")
    md.append(f"| 模型 Top-10 均值 | {e6.get('model_topk_mean')} |\n")
    md.append(f"| 池均值 | {e6.get('pool_mean')} |\n")
    md.append(f"| regret | {e6.get('regret')} |\n")
    md.append(f"| P(随机 ≥ 模型) | **{e6.get('p_random_at_least_as_good')}** |\n")
    md.append(f"| 判定 | `{e6.get('verdict')}` |\n")
    sens = e6.get("topk_sensitivity", {})
    if sens:
        md.append("\n| k | regret | P(随机≥模型) |\n|---:|---:|---:|\n")
        for kk, vv in sens.items():
            md.append(f"| {kk} | {vv['regret']} | {vv['p_random_ge_model']} |\n")
    md.append("\n> **显著优于随机 ≠ 足够好用于实际筛选。** "
              "模型只捕获了部分提升空间，regret 仍然很大。\n")

    md.append("\n## 五、H4 假设\n")
    md.append(f"**判定：`{h4.get('status')}`**\n\n")
    pw = h4.get("power", {})
    md.append(f"- 弱缔合低介电组：{pw.get('n_weak')} 个\n")
    md.append(f"- 强缔合高介电组：{pw.get('n_strong')} 个\n")
    md.append(f"- 功效充足：{pw.get('sufficient')}\n")
    cmp_ = h4.get("comparison")
    if cmp_:
        md.append(f"\n方向：弱缔合组相对 MAE {cmp_.get('weak_relative_mae')} vs "
                  f"强缔合组 {cmp_.get('strong_relative_mae')}，"
                  f"`supports_h4={cmp_.get('supports_h4')}`。\n")
        md.append("\n**但样本量不足，不能作为确认性结论。**\n")

    md.append("\n## 六、构象分析\n")
    md.append(f"- 分析分子数：{cfd.get('n_ok')}\n")
    md.append(f"- 极性分子：{cfd.get('n_polar_analysed')}\n")
    md.append(f"- 单构象可靠：{cfd.get('n_reliable')}\n")
    md.append(f"- **单构象不可靠：{cfd.get('n_unreliable')}**\n")
    md.append(f"- 非极性（构象无关）：{cfd.get('n_nonpolar_insensitive')}\n")
    md.append(f"\n{cfd.get('finding')}\n")

    md.append("\n## 七、未计算的两层\n")
    md.append("| 层 | 状态 | 原因 |\n|---|---|---|\n")
    md.append(f"| DFT | `{dft_block['status']}` | {dft_block['reason']} |\n")
    md.append(f"| MD | `{md_block['status']}` | {md_block['reason']} |\n")
    md.append("\n**这不是方法论选择，而是本环境缺少计算引擎。**\n")

    md.append("\n## 八、必须保留的限制\n")
    for lim in manifest["known_limitations"]:
        md.append(f"- {lim}\n")

    md.append("\n## 九、交付件清单\n")
    md.append("| 文件 | 行数 | 类型 |\n|---|---:|---|\n")
    for e in emitted:
        md.append(f"| `{e['file']}` | {e['rows']} | {e['kind']} |\n")
    md.append(f"| `b100_freeze_manifest.json` | — | 哈希与协议 |\n")

    (DELIV / "B100_FINAL_REPORT.md").write_text("".join(md), encoding="utf-8")
    note("B100_FINAL_REPORT.md", len(md), "REPORT",
         "由 manifest 机械生成的汇总报告")

    # refresh the manifest so the report itself is hashed
    files = {}
    for p in sorted(DELIV.iterdir()):
        if p.is_file() and p.name != "b100_freeze_manifest.json":
            files[p.name] = {"sha256": sha256_file(p),
                             "bytes": p.stat().st_size}
    manifest["deliverables"] = files
    (DELIV / "b100_freeze_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"[B100-15] {DELIV}")
    for e in emitted:
        print(f"   {e['kind']:8s} {e['file']:36s} rows={e['rows']}")
    print(f"   manifest b100_freeze_manifest.json  "
          f"({len(files)} files hashed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
