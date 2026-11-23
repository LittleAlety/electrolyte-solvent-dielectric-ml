#!/usr/bin/env python
"""B05-0: feature registry and model input manifest.

PLAN B B05 requires `feature_registry_v2.csv` and `model_input_manifest.json`.
They exist so that every number produced by E1/E4/E6 can be traced back to an
exact feature list and an exact input hash.

The registry deliberately records the *provenance class* of each descriptor:

    X0  composition / shape      -- from SMILES, no quantum chemistry
    X1  isolated-molecule electronic -- from xTB, single conformer
    X2  conformer statistics     -- NOT computed here (see E3, conditional)
    X3  condensed-phase physics  -- NOT available (see E5, conditional)

Recording which tiers are absent is as important as recording which are present,
because PLAN B B05 assigns different evidential weight to each.

Output: outputs/b05/feature_registry_v2.csv
        outputs/b05/model_input_manifest.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b05"
POOL = REPO_ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEATURES = REPO_ROOT / "data" / "processed" / "dielectric_physical_features.csv"
GENERATOR = "build_feature_registry/2.0.0"

# (name, tier, source, unit, description, used_in)
REGISTRY = [
    ("heavy_atom_count", "X0", "RDKit", "count",
     "重原子数; 分子大小的最粗描述", "E1,E4,E6"),
    ("hbd", "X0", "RDKit", "count",
     "氢键供体数", "E1,E4,E6"),
    ("hba", "X0", "RDKit", "count",
     "氢键受体数", "E1,E4,E6"),
    ("tpsa_A2", "X0", "RDKit", "A^2",
     "拓扑极性表面积", "E1,E4,E6"),
    ("molecular_volume_A3", "X0", "RDKit", "A^3",
     "分子体积", "E1,E4,E6"),
    ("molar_volume_m3_mol", "X0", "derived", "m^3/mol",
     "摩尔体积; 连接单分子与凝聚态的最弱桥梁", "E1,E4,E6"),
    ("formal_charge", "X0", "RDKit", "e",
     "形式电荷", "E1,E4,E6"),
    ("dipole_D", "X1", "xTB", "Debye",
     "孤立分子偶极矩; Kirkwood 理论中 ε 的一阶驱动量", "E1,E4,E6"),
    ("polarizability_au", "X1", "xTB", "a.u.",
     "各向同性极化率 (原子单位)", "E1,E4,E6"),
    ("polarizability_A3", "X1", "xTB", "A^3",
     "各向同性极化率 (A^3); 与 Onsager 反应场耦合", "E1,E4,E6"),
    ("homo_lumo_gap_ev", "X1", "xTB", "eV",
     "HOMO-LUMO 能隙; 电子软度代理", "E1,E4,E6"),
    # Reviewer 3 (B04+B05) found this column was fitted by E1 but missing from the
    # registry, so the manifest did not describe what the model consumed.
    ("total_energy_hartree", "X1", "xTB", "hartree",
     "总能量; **实为分子大小代理** (与重原子数相关 −0.957, 与 ε 仅相关 0.007)",
     "E1_only"),
]

# Features that are algebraically redundant -- recorded so the nominal count is
# never mistaken for the information content. (Reviewer 3, B04+B05.)
REDUNDANCIES = [
    {
        "features": ["polarizability_au", "polarizability_A3"],
        "relation": "same quantity, two units (ratio 0.148184)",
        "kind": "EXACT_UNIT_DUPLICATE",
        "consequence": "投喂两列等于投喂一列两次; 岭回归会把权重平分",
    },
    {
        "features": ["molecular_volume_A3", "molar_volume_m3_mol"],
        "relation": "molar_volume = molecular_volume * N_A (vdW cavity sum)",
        "kind": "ALGEBRAIC_IDENTITY",
        "consequence": (
            "molar_volume_m3_mol 不是独立的体相摩尔体积, 而是 vdW 腔体积求和的重述; "
            "不得解释为『一摩尔液体占据的体积』"
        ),
    },
]

ABSENT_TIERS = [
    {"tier": "X2", "name": "conformer statistics",
     "status": "NOT_COMPUTED",
     "why": "PLAN B B05 E3 为条件性实验, 当前未授权运行",
     "planned_in": "E3_conformer_ablation"},
    {"tier": "X3", "name": "condensed-phase independent physics",
     "status": "NOT_AVAILABLE",
     "why": "PLAN B B05 E5 依赖有限独立相互作用信息, 当前证据不足以构造",
     "planned_in": "E5_physical_information"},
]


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
    for p in (POOL, FEATURES):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEATURES)}

    # coverage per feature
    rows = []
    for name, tier, source, unit, desc, used in REGISTRY:
        n_present = 0
        for r in pool:
            v = (feats.get(r["inchikey"], {}).get(name) or "").strip()
            if v and v.lower() not in ("not_evaluated", "nan", "none"):
                n_present += 1
        rows.append({
            "feature": name,
            "tier": tier,
            "source": source,
            "unit": unit,
            "description": desc,
            "used_in": used,
            "n_pool_present": n_present,
            "n_pool_total": len(pool),
            "coverage_pct": round(100.0 * n_present / len(pool), 2) if pool else 0.0,
        })

    reg_path = OUT_DIR / "feature_registry_v2.csv"
    with reg_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by_tier: dict[str, list[str]] = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r["feature"])

    # Effective rank, measured rather than assumed.
    fqa_path = OUT_DIR / "feature_quality_audit.json"
    fqa = json.loads(fqa_path.read_text(encoding="utf-8")) if fqa_path.is_file() else None
    effective_rank = fqa["effective_rank"] if fqa else None

    manifest = {
        "schema": "b05.model_input_manifest/v2",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": (
            "让 E1/E4/E6 的每个数字都能追溯回确切的特征清单与输入哈希"
        ),
        "feature_tiers_present": by_tier,
        "feature_tiers_absent": ABSENT_TIERS,
        "n_features_present": len(rows),
        "inputs": {
            "candidate_pool_v2_draft": {
                "path": str(POOL.relative_to(REPO_ROOT)),
                "sha256": sha256_file(POOL), "rows": len(pool)},
            "dielectric_physical_features": {
                "path": str(FEATURES.relative_to(REPO_ROOT)),
                "sha256": sha256_file(FEATURES),
                "rows": len(load(FEATURES))},
        },
        "experiments": {
            "E1_structure_vs_electronic": {
                "features_X0": by_tier.get("X0", []),
                "features_X1_added": by_tier.get("X1", []),
                "status": "COMPLETED_EXPLORATORY",
            },
            "E2_xtb_vs_dft": {
                "status": "NOT_RUN",
                "why": "针对性实验; 需先确认 xTB 与 DFT 的可比口径",
            },
            "E3_conformer_ablation": {
                "status": "NOT_RUN_CONDITIONAL",
                "why": "条件性实验, 需多构象数据; 当前 X2 未计算",
            },
            "E4_domain_generalization": {
                "features": by_tier.get("X0", []) + by_tier.get("X1", []),
                "status": "COMPLETED_EXPLORATORY",
            },
            "E5_physical_information": {
                "status": "NOT_RUN_CONDITIONAL",
                "why": "依赖有限独立相互作用信息, 证据不足",
            },
            "E6_screening_decisions": {
                "features": by_tier.get("X0", []) + by_tier.get("X1", []),
                "status": "COMPLETED_INSUFFICIENT_POWER",
            },
        },
        "honesty_rules": [
            "缺失的特征层必须显式登记, 不得静默省略",
            "X2/X3 未计算, 因此任何『完整描述符体系』的宣称都不成立",
            "所有实验共用同一分子身份与同一候选池",
            "名义特征数不等于有效信息量: 必须同时报告有效秩",
        ],
        "redundancies": REDUNDANCIES,
        "effective_rank": effective_rank,
        "feature_set_inconsistency": {
            "E1_uses": "12 列 (含 total_energy_hartree)",
            "E4_E6_B07_use": "11 列 (不含 total_energy_hartree)",
            "note": (
                "跨实验比较因此不是完全同一个模型 (Reviewer 3/4, B04+B05). "
                "E1c 已按 11 列口径重做块消融, 与 E4/E6/B07 对齐."
            ),
        },
        "output": {"path": str(reg_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(reg_path), "rows": len(rows)},
    }
    man_path = OUT_DIR / "model_input_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B05-0] {reg_path}  ({len(rows)} features)")
    print(f"[B05-0] {man_path}")
    for tier, names in sorted(by_tier.items()):
        print(f"  {tier}: {len(names)} features")
    print(f"  absent tiers: {[a['tier'] for a in ABSENT_TIERS]}")
    min_cov = min(r["coverage_pct"] for r in rows)
    print(f"  min coverage = {min_cov}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
