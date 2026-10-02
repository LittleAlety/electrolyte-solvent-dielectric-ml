"""W21 Tier 1 -- align the frozen in-repo assets onto the v2 framework slots.

Zero compute, zero fitting, zero network.  The framework原文 is copied byte for
byte into ``docs/framework/`` and pinned by sha256.  The three derived tables
(feature-cost map, chemical-space metadata, stage/gate verdicts) are new files;
no shipped artifact is rewritten.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_SOURCE = Path(
    r"E:\Claude Code\电解液溶剂-HB\核心文件\ranking-electrolyte-materials-v2.md"
)
FRAMEWORK_DIR = ROOT / "docs" / "framework"
FRAMEWORK_COPY = FRAMEWORK_DIR / "ranking-electrolyte-materials-v2.md"
FRAMEWORK_SHA = FRAMEWORK_DIR / "ranking-electrolyte-materials-v2.sha256"
ROSTER = ROOT / "data" / "dielectric_v03.csv"
SCAFFOLD_FOLDS = ROOT / "data" / "processed" / "v032_scaffold_folds.csv"
PHYSICAL_FEATURES = ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
FEATURE_COST_CSV = ROOT / "probes" / "artifacts" / "w21_feature_cost_map.csv"
CHEM_SPACE_CSV = ROOT / "data" / "processed" / "w21_chemical_space_metadata.csv"
GATES_CSV = ROOT / "probes" / "artifacts" / "w21_stage_gate_verdicts.csv"
SUMMARY = ROOT / "probes" / "w21_framework_alignment_summary.json"
REPORT = ROOT / "reports" / "w21_framework_alignment.md"

CARBONATE = Chem.MolFromSmarts("[CX3](=O)([OX2][#6])[OX2][#6]")
SULFONE = Chem.MolFromSmarts("[#16](=O)(=O)")
SULFOXIDE = Chem.MolFromSmarts("[#16]=O")
PHOSPHATE = Chem.MolFromSmarts("[PX4](=O)")
NITRILE = Chem.MolFromSmarts("[NX1]#[CX2]")
AMIDE = Chem.MolFromSmarts("[NX3][CX3]=O")
ESTER = Chem.MolFromSmarts("[CX3](=O)[OX2][#6]")
ETHER = Chem.MolFromSmarts("[OD2]([#6])[#6]")
ALCOHOL = Chem.MolFromSmarts("[OX2H]")
AMINE = Chem.MolFromSmarts("[NX3]")
NITRO = Chem.MolFromSmarts("[NX3](=O)=O")
HALOGEN = Chem.MolFromSmarts("[F,Cl,Br,I]")
AROMATIC_C = Chem.MolFromSmarts("c")

FAMILY_ORDER = (
    ("cyclic_carbonate", CARBONATE, "ring"),
    ("linear_carbonate", CARBONATE, "acyclic"),
    ("sulfone", SULFONE, None),
    ("sulfoxide", SULFOXIDE, None),
    ("phosphate", PHOSPHATE, None),
    ("nitrile", NITRILE, None),
    ("amide", AMIDE, None),
    ("ester", ESTER, None),
    ("ether", ETHER, None),
    ("alcohol", ALCOHOL, None),
    ("amine", AMINE, None),
    ("nitro", NITRO, None),
    ("aromatic_hydrocarbon", AROMATIC_C, None),
    ("halogenated", HALOGEN, None),
)

TAG_PATTERNS = (
    ("fluorinated", Chem.MolFromSmarts("[F]")),
    ("chlorinated", Chem.MolFromSmarts("[Cl]")),
    ("unsaturated", Chem.MolFromSmarts("[CX3]=[CX3]")),
    ("carbonyl", Chem.MolFromSmarts("[CX3]=O")),
    ("hydroxyl", ALCOHOL),
    ("nitrile", NITRILE),
    ("sulfonyl", SULFONE),
    ("aromatic", AROMATIC_C),
    ("nitro", NITRO),
)

STATE_OF_THE_ART = (
    "propylene carbonate",
    "ethylene carbonate",
    "dimethyl carbonate",
    "ethyl methyl carbonate",
    "diethyl carbonate",
    "1,2-dimethoxyethane",
    "1,3-dioxolane",
    "ethyl acetate",
    "gamma-butyrolactone",
    "sulfolane",
    "acetonitrile",
    "dimethyl sulfoxide",
    "n,n-dimethylformamide",
    "water",
    "triethyl phosphate",
    "fluoroethylene carbonate",
    "vinylene carbonate",
)

FEATURE_COST_ROWS = (
    ("x0", "Morgan count fingerprint (radius 2, 2048 bits)", "X0", "query 前", "probes/dielectric_representation_ablation.py::morgan_count_features", "纯结构，无需任何量子化学"),
    ("x0", "RDKit descriptors: heavy atoms / HBD / HBA / TPSA", "X0", "query 前", "data/processed/dielectric_physical_features_v03.csv", "物理块列，直接可算"),
    ("x0", "formal charge / rotatable bonds", "X0", "query 前", "data/processed/w21_chemical_space_metadata.csv", "本件新增"),
    ("x0", "structural_family / functionalization_tags", "X0", "query 前", "data/processed/w21_chemical_space_metadata.csv", "本件新增，框架 §5.2"),
    ("x0", "use_role", "X0", "query 前", "data/processed/w21_chemical_space_metadata.csv", "本件新增，框架 §5.2"),
    ("x0", "xTB orbital proxy (homo_gfn2/lumo_gfn2/gap_gfn2)", "X0", "query 前", "data/processed/themol_orbital_layer.csv", "GFN2-xTB 气相单点，本仓 P_0"),
    ("x0", "xTB dipole / polarizability / mu_sq_over_Vm / alpha_over_Vm", "X0", "query 前", "data/processed/dielectric_physical_features_v03.csv", "13 维物理块列"),
    ("x0", "molecular volume / molar volume", "X0", "query 前", "data/processed/dielectric_physical_features_v03.csv", "同上"),
    ("x0", "common embedding (GFN2-xTB 气相单点)", "X0", "query 前", "data/processed/themol_orbital_layer.csv", "本仓 P_0 的物理含义"),
    ("x1", "DFT mu / alpha", "X1", "free-molecule DFT 之后", "data/processed/themol_orbital_layer.csv", "缺口：本仓只有 xTB 级，无 DFT 级"),
    ("x1", "free-molecule gas redox quantities (IP/EA)", "X1", "free-molecule DFT 之后", "data/processed/four_core_key_registry.csv", "registry 的 IP_eV/EA_eV 来自 Batt 参考层，不是本仓自算 -> 只作 reference"),
    ("x2", "Li-complex binding / Li-X distance / charge redistribution", "X2", "Li 配合物 DFT 之后", "", "缺口：本仓无任何 Li+ 配位计算"),
    ("ref", "experimental dielectric epsilon", "target", "-", "data/dielectric_v03.csv", "框外：本仓主记分牌目标量"),
    ("ref", "experimental dynamic viscosity eta", "target", "-", "data/viscosity_v02.csv", "框外：独立通道"),
    ("ref", "Batt-P30K HOMO/LUMO/gap (SMD eps=18.5)", "reference", "-", "data/external", "外部参考层 R_sol，MIT 许可"),
    ("ref", "RX-392 redox labels", "reference", "-", "data/external/Batt-SLM-RX-392.csv", "外部参考层，392 行"),
    ("ref", "SolvFunc-87 HOMO/LUMO/DN/DC predictions", "reference", "-", "data/external/SolvFunc-87.csv", "独立外部对照"),
    ("ref", "density_v01", "reference", "-", "data/density_v01.csv", "182,154 行；η 解冻的依赖项"),
)

STAGE0_GATES = (
    ("S0-1", "确定 core set 与 broad pool", "成立", "epsilon 名册 246 / 建模集 236；轨道可核主臂 n=49；eta 4,151 行 / 976 键", "data/processed/four_core_key_registry.csv"),
    ("S0-2", "建立 structural_family / functionalization_tags / use_role", "成立", "本件新建，246/246 全覆盖（互斥主家族 + 多选标签 + 角色）", "data/processed/w21_chemical_space_metadata.csv"),
    ("S0-4", "定义 oxidation/reduction quantity 与方向", "部分成立", "轨道通道按 §4.1 约定（P_0^ox=-HOMO, P_0^red=LUMO）；排序键 v1 仍把两方向混在一条键里 -> 待拆", "reports/w19_ranking_key_v1_spec.md"),
    ("S0-5", "冻结 common embedding 的物理含义", "成立", "P_0 = GFN2-xTB 气相单点（THEMol B3LYP-D3(BJ)/DZVP 几何）；R_sol = wB97X-V/def2-TZVPPD/SMD(eps=18.5)", "data/processed/themol_orbital_layer.csv"),
    ("S0-6", "预注册 k/N = 10%,20%,30%", "成立", "本件预注册 k=5/10/15（n=49）", "probes/w21_rank_stability_prereg.json"),
    ("S0-7", "预注册 robust-pair tolerance 的确定方法", "成立", "本件预注册：delta 由留一残差与 bootstrap 共同决定", "probes/w21_rank_stability_prereg.json"),
    ("S0-8", "冻结 reference ligand R", "未执行", "本仓不做 Li+ 配位，故无 R", ""),
    ("S0-9", "冻结 external anchor 搜集规则", "成立", "四角色 sidecar（primary_reference / calibrated_estimate / reference_only）+ 许可分级", "probes/artifacts/w20_label_provenance_sidecar.csv"),
)

STAGE1_GATES = (
    ("S1-1", "选 8-10 个 method-audit molecules", "未执行", "本仓无 DFT 方法审计；轨道层为 xTB 单点 + 外部源交叉核对", ""),
    ("S1-2", "比较 functionals / basis / diffuse treatment", "未执行", "同上", ""),
    ("S1-4", "建立 gas-phase external anchors", "部分成立", "pubchemqc 第二源（B3LYP/6-31G*//PM6, 801+111 行）已入 sidecar；Batt 为 SMD 溶剂化层，不是气相锚", "probes/artifacts/w20_label_provenance_sidecar.csv"),
    ("S1-5", "搜集 solution redox anchor subset", "成立", "RX-392 392 行，含显式溶剂清单", "data/external/Batt-SLM-RX-392.csv"),
    ("S1-6", "比较 absolute error 与 rank stability", "成立", "w19_batt_gap_crosscheck：homo r=0.8223 / rho=0.8640 / 留一 MAE 0.3475 eV（常数基线 0.7383）", "probes/w19_batt_gap_crosscheck_summary.json"),
    ("S1-7", "冻结 production protocol", "部分成立", "GFN2-xTB 6.7.1pre 已冻结并跑了全名册；DFT production protocol 不存在", "data/processed/themol_orbital_layer.csv"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def ingest_framework() -> dict[str, object]:
    if not FRAMEWORK_SOURCE.is_file():
        raise FileNotFoundError(str(FRAMEWORK_SOURCE))
    payload = FRAMEWORK_SOURCE.read_bytes()
    FRAMEWORK_DIR.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_COPY.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    FRAMEWORK_SHA.write_text(digest + "  ranking-electrolyte-materials-v2.md\n", encoding="utf-8", newline="\n")
    text = payload.decode("utf-8")
    return {
        "source_path": str(FRAMEWORK_SOURCE),
        "copy_path": str(FRAMEWORK_COPY.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "bytes": len(payload),
        "lines": text.count("\n") + 1,
        "byte_identical": FRAMEWORK_COPY.read_bytes() == payload,
        "section_headings": sum(1 for line in text.splitlines() if line.startswith("# ")),
    }


def family_of(mol: Chem.Mol) -> str:
    if any(atom.GetFormalCharge() != 0 for atom in mol.GetAtoms()):
        return "ionic_liquid_or_salt"
    if mol.GetNumAtoms() == 1 and mol.GetAtomWithIdx(0).GetSymbol() == "O":
        return "water"
    for name, pattern, ring_rule in FAMILY_ORDER:
        if pattern is None:
            continue
        matches = mol.GetSubstructMatches(pattern)
        if not matches:
            continue
        if ring_rule is None:
            return name
        in_ring = any(mol.GetAtomWithIdx(match[0]).IsInRing() for match in matches)
        if ring_rule == "ring" and in_ring:
            return name
        if ring_rule == "acyclic" and not in_ring:
            return name
    return "other"


def tags_of(mol: Chem.Mol) -> str:
    tags = [name for name, pattern in TAG_PATTERNS if mol.HasSubstructMatch(pattern)]
    if mol.GetRingInfo().NumRings() > 0:
        tags.append("cyclic")
    return ";".join(sorted(set(tags)))


def chemical_space() -> tuple[list[tuple[object, ...]], dict[str, object]]:
    roster = read_rows(ROSTER)
    scaffolds: dict[str, str] = {}
    for row in read_rows(SCAFFOLD_FOLDS):
        if str(row.get("partition_seed")) == "42":
            scaffolds[str(row["inchikey"])] = str(row.get("scaffold", ""))
    physical = {row["inchikey"]: row for row in read_rows(PHYSICAL_FEATURES)}
    header = (
        "molecule_id",
        "canonical_smiles",
        "name",
        "structural_family",
        "functionalization_tags",
        "use_role",
        "donor_atoms",
        "formal_charge",
        "rotatable_bonds",
        "conformer_count",
        "Li_motif_count",
        "state_identity_status",
        "reactivity_status",
        "qc_status",
        "scaffold",
        "epsilon",
        "epsilon_T_K",
        "evidence_path",
    )
    rows: list[tuple[object, ...]] = []
    unknown_charge = 0
    for record in roster:
        key = str(record["inchikey"]).strip()
        smiles = str(record["smiles"]).strip()
        name = str(record.get("name", "")).strip()
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("unparsable roster smiles: " + smiles)
        family = family_of(mol)
        feat = physical.get(key)
        if feat is None or str(feat.get("formal_charge", "")).strip() == "":
            charge = ""
            qc_status = "no_xtb_features"
            unknown_charge += 1
        else:
            charge = int(float(feat["formal_charge"]))
            qc_status = str(feat.get("status", ""))
        donor_atoms = sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() in {"N", "O", "S"})
        rows.append(
            (
                key,
                Chem.MolToSmiles(mol),
                name,
                family,
                tags_of(mol),
                "state_of_the_art_solvent" if name.lower() in STATE_OF_THE_ART else "background_candidate",
                donor_atoms,
                charge,
                rdMolDescriptors.CalcNumRotatableBonds(mol),
                "not_available_in_repo",
                "not_available_in_repo",
                "not_available_in_repo",
                "not_available_in_repo",
                qc_status,
                scaffolds.get(key, "not_available_in_repo"),
                record.get("dielectric", ""),
                record.get("T_K", ""),
                "data/dielectric_v03.csv",
            )
        )
    families = {}
    for row in rows:
        families[row[3]] = families.get(row[3], 0) + 1
    report = {
        "rows": len(rows),
        "distinct_keys": len({row[0] for row in rows}),
        "families": dict(sorted(families.items(), key=lambda item: (-item[1], item[0]))),
        "roles": {role: sum(1 for row in rows if row[5] == role) for role in ("state_of_the_art_solvent", "background_candidate")},
        "rows_without_xtb_charge": unknown_charge,
        "fields_not_available_in_repo": [
            "conformer_count",
            "Li_motif_count",
            "state_identity_status",
            "reactivity_status",
        ],
    }
    return rows, report


def main() -> int:
    framework = ingest_framework()

    feature_rows = [tuple(row) for row in FEATURE_COST_ROWS]
    write_csv(
        FEATURE_COST_CSV,
        ("block", "feature", "cost_level", "available_when", "evidence_path", "note"),
        feature_rows,
    )

    space_rows, space_report = chemical_space()
    write_csv(
        CHEM_SPACE_CSV,
        (
            "molecule_id",
            "canonical_smiles",
            "name",
            "structural_family",
            "functionalization_tags",
            "use_role",
            "donor_atoms",
            "formal_charge",
            "rotatable_bonds",
            "conformer_count",
            "Li_motif_count",
            "state_identity_status",
            "reactivity_status",
            "qc_status",
            "scaffold",
            "epsilon",
            "epsilon_T_K",
            "evidence_path",
        ),
        space_rows,
    )

    gate_rows = [tuple(row) for row in (STAGE0_GATES + STAGE1_GATES)]
    write_csv(GATES_CSV, ("gate_id", "item", "verdict", "detail", "evidence_path"), gate_rows)

    cost_counts: dict[str, int] = {}
    for row in feature_rows:
        cost_counts[str(row[2])] = cost_counts.get(str(row[2]), 0) + 1

    summary = {
        "schema_version": 1,
        "task": "week21_w21_0_framework_alignment",
        "title": "Tier 1：v2 框架原文入库 + 槽位接口三表（特征成本 / 多轴 metadata / Stage 0-1 判词）",
        "generated_at_utc": utc_now(),
        "run_mode": "offline",
        "models_fitted": 0,
        "network_calls": 0,
        "writes_any_pool": False,
        "frozen_files_touched": [],
        "framework": framework,
        "feature_cost": {
            "path": "probes/artifacts/w21_feature_cost_map.csv",
            "rows": len(feature_rows),
            "by_cost_level": dict(sorted(cost_counts.items())),
            "sha256": sha256_file(FEATURE_COST_CSV),
        },
        "chemical_space": {
            "path": "data/processed/w21_chemical_space_metadata.csv",
            "sha256": sha256_file(CHEM_SPACE_CSV),
            **space_report,
        },
        "stage_gates": {
            "path": "probes/artifacts/w21_stage_gate_verdicts.csv",
            "sha256": sha256_file(GATES_CSV),
            "by_verdict": {
                verdict: sum(1 for row in gate_rows if row[2] == verdict)
                for verdict in sorted({str(row[2]) for row in gate_rows})
            },
        },
        "framework_red_lines": {
            "stage0_gate": "成立（本件不改动任何已冻结定义）",
            "stage1_gate": "NOT CLOSED（本仓不跑 DFT 批量计算，框架不禁止本仓工作）",
        },
        "outputs": {
            "framework_copy": framework["copy_path"],
            "slot_map": "reports/w21_framework_slot_map.md",
            "summary": "probes/w21_framework_alignment_summary.json",
            "report": "reports/w21_framework_alignment.md",
        },
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        "# W21 Tier 1：v2 框架原文入库与槽位接口三表",
        "",
        "本件不拟合任何模型、不联网、不动任何冻结件；只把已经做出来的资产按《Understanding Electrolyte Materials through Decision-Centric Ranking Stability》(v2) 的槽位重新编址。",
        "",
        "## 1. 框架原文入库（逐字节）",
        "",
        f"- 来源：`{framework['source_path']}`",
        f"- 落点：`{framework['copy_path']}`",
        f"- sha256：`{framework['sha256']}`（{framework['bytes']} B / {framework['lines']} 行 / {framework['section_headings']} 个一级章节）",
        f"- 逐字节一致：`{framework['byte_identical']}`",
        "",
        "## 2. 特征成本分级（框架 §11）",
        "",
        "| cost level | 条数 | 含义 |",
        "| --- | --- | --- |",
    ]
    meaning = {
        "X0": "query 前即可得（结构、RDKit、xTB 代理量）",
        "X1": "free-molecule DFT 之后可得",
        "X2": "Li 配合物 DFT 之后可得",
        "target": "本仓要预测的实验标签（§18 不许塞进单一综合分）",
        "reference": "外部参考层（§3.3），不是标签源",
    }
    for level, count in sorted(cost_counts.items()):
        lines.append(f"| {level} | {count} | {meaning.get(level, '')} |")
    lines += [
        "",
        f"完整表：`{summary['feature_cost']['path']}`（sha256 `{summary['feature_cost']['sha256']}`）。",
        "",
        "**X2 是空的**：本仓没有做任何 Li⁺ 配位计算，因此框架 §11.3 的一整层在本仓不存在——这不是遗漏，是边界，§2 槽位表里如实登记为「未执行」。",
        "",
        "## 3. 多轴 chemical-space metadata（框架 §5.2）",
        "",
        f"- 行数：**{space_report['rows']}**（去重键 {space_report['distinct_keys']}）",
        f"- 主家族分布：`{json.dumps(space_report['families'], ensure_ascii=False)}`",
        f"- 角色分布：`{json.dumps(space_report['roles'], ensure_ascii=False)}`",
        f"- 无 xTB 特征的登记行：{space_report['rows_without_xtb_charge']}",
        f"- 仓内**不存在**的字段（如实留空而非编造）：`{', '.join(space_report['fields_not_available_in_repo'])}`",
        "",
        "## 4. Stage 0 / Stage 1 判词（框架 §19）",
        "",
        "| gate | 条目 | 判词 | 依据 |",
        "| --- | --- | --- | --- |",
    ]
    for row in gate_rows:
        lines.append(f"| {row[0]} | {row[1]} | **{row[2]}** | {row[3]} |")
    lines += [
        "",
        f"- Gate 0：{summary['framework_red_lines']['stage0_gate']}",
        f"- Gate 1：{summary['framework_red_lines']['stage1_gate']}",
        "",
        "## 5. 边界",
        "",
        "- 不拟合、不联网、不写任何池；新增文件只有三张表 + 框架副本 + 本摘要。",
        "- 不引用 Reaxys 数值；不把 Batt 参考层当标签源。",
        "- 框架原文**不进** `data/`，也不参与任何训练。",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print("framework bytes:", framework["bytes"], "sha256:", framework["sha256"][:16])
    print("feature cost rows:", len(feature_rows), dict(sorted(cost_counts.items())))
    print("chemical space rows:", space_report["rows"], "families:", len(space_report["families"]))
    print("gate rows:", len(gate_rows), summary["stage_gates"]["by_verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())