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
            "phase_verified": "true",
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
        },
        "known_limitations": [
            "226/257 分子来自单一编校来源 (NBS 514), 跨来源复现未被证明",
            "卤代烃家族 (67 分子) 跨家族迁移失败: MAE 6.78 vs 基线 2.53",
            "H4 功效不足: 强缔合组仅 15 个分子",
            "DFT / MD 两层未计算, 结论停留在 xTB 层级",
            "30/36 极性柔性分子的单构象偶极不可靠 (已量化)",
            "7 个化学家族仍低于分层目标; NBS 514 已耗尽",
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

    print(f"[B100-15] {DELIV}")
    for e in emitted:
        print(f"   {e['kind']:8s} {e['file']:36s} rows={e['rows']}")
    print(f"   manifest b100_freeze_manifest.json  "
          f"({len(files)} files hashed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
