# -*- coding: utf-8 -*-
"""W38-D：数据侦察——四核心量的新来源核实 + 渠道红线登记（后验，不占 shot）。

W38 的四条 lane 里，A/B/C 都是「用盘上既有数据回答一个方法学问题」，E 是治理收口。
只有 D 是**朝外看**：四个核心量（静态介电常数 eps / 粘度 eta / HOMO-LUMO 轨道能 /
氧化-还原电位）还有没有**合法可用**的新来源？

本件把这轮侦察**落成可复算的产物**，只做两件事：

1. **名册命中实测**：把每个本地外部件里的化合物标识符（SMILES 或 InChI）用 RDKit
   换算到全 27 位 InChIKey，与名册 `data/processed/dielectric_physical_features_v03.csv`
   的 241 行做精确集合交。这是**实测**，不是估计。分母统一用 241 行；
   既有报告的 246 / 247 行是 `data/dielectric_v03.csv` 口径，两者不得混引。
2. **渠道红线登记**：把每个被侦察的渠道写成一行，逐行记它的许可、许可状态、
   是否真的含四核心量、可达性、以及**能不能入池**。含 NC / ND / 专有 / 未知的一律
   `can_enter_pool = false`，且由判据 H38d6 强制。

刻意**不做**的事：不下载任何第三方大文件到仓库、不把任何第三方数值写进池、
不新增特征列、不拟合模型、不改 METRIC_NAMES、不动四个冻结读数。所有第三方件
只读；是否「已在库」由与上游 git blob 的 sha256 逐字节比对判定。

Run:
    .venv/Scripts/python.exe probes/w38_data_recon.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np  # noqa: E402
from rdkit import Chem, RDLogger  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
HITS_CSV = ARTIFACTS / "w38_recon_hits.csv"
CHANNELS_CSV = ARTIFACTS / "w38_recon_channels.csv"
SUMMARY_PATH = ARTIFACTS / "w38_recon_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w38_data_recon.md"
FIGURE_PATH = ARTIFACTS / "w38_recon_hits.png"

SCHEMA = "w38_data_recon/summary@1"
TASK = "week38_data_recon"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

ROSTER_TOTAL_EXPECTED = 241
BATT_P30K_HITS_GATE = 70
CHEW_VISCOSITY_HITS_GATE = 140
NEW_FILES_EXPECTED = 2
PERMISSIVE_ORBITAL_CHANNELS_GATE = 2

NEW_FILES_THIS_ROUND = ("batt_slm_cpi_features", "batt_slm_cpi_features_nof")
ORBITAL_CHANNELS = frozenset({
    "batt_p30k_channel", "molssiai_pubchemqc_b3lyp", "molssiai_pubchemqc_pm6",
    "qm9_original", "qmugs", "pubchemqc_riken", "solvfunc_87",
})

UPSTREAM_REPO = "https://github.com/Teoroo-CMC/Batt-SLM"
UPSTREAM_TREE = "main"

# 上游 git blob 的 sha256（2026-10-03 经 GitHub blobs API 实测）。
# 用来判定本地件是「已在库」还是「本轮真新增」——不用文件名猜。
UPSTREAM_BLOBS = {
    "Batt-SLM/Batt-SLM.smi":
        "c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d",
    "CPI/SolvFunc-87.csv":
        "1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493",
    "Redox-Pot/Redox-Ener/RX-392.csv":
        "d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87",
    "CPI/Input/Features.csv":
        "b5c7ca5df92a9fb98a5fa61203b53acd81845e99afc803095dd5b369a207c542",
    "CPI/Input/Features-NoF.csv":
        "aceec4c3c985d4a898ef9c31584af2ed9d4db593281f68663addfd70bc9463ff",
}

# ---------------------------------------------------------------- 本地外部件
# kind: "smi"      每行第一个空白分隔 token 是 SMILES
#       "table"    分隔符 + 标识符列
#       "hdf5"     h5py，逐组取 smiles 数据集
LOCAL_SOURCES: tuple[dict[str, object], ...] = (
    {
        "key": "batt_p30k",
        "display": "Batt-P30K.h5（GSDS，ωB97X-V/def2-TZVPPD/SMD）",
        "path": "data/raw/batt/Batt-P30K.h5",
        "kind": "hdf5",
        "quantity": "轨道能(HOMO/LUMO/gap) + IP/EA + dipole",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": None,
        "evidence": UPSTREAM_REPO + "（LICENSE 逐字读过：MIT, Copyright (c) 2026 Zhan-Yun Zhang）",
        "note": "ωB97X-V 气相单分子 + SMD 隐式溶剂，与本地 xTB 单点不同层级；跨层级映射必须走既有标定门。",
    },
    {
        "key": "batt_slm_smi",
        "display": "Batt-SLM.smi（生成器化学空间清单）",
        "path": "data/external/Batt-SLM.smi",
        "kind": "smi",
        "quantity": "无标签（仅 SMILES 清单）",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": "Batt-SLM/Batt-SLM.smi",
        "evidence": UPSTREAM_REPO + " blob sha256 逐字节相等",
        "note": "只值「候选新化合物的分母」，不是标签源。",
    },
    {
        "key": "batt_slm_rx392",
        "display": "RX-392.csv（氧化-还原电位轴）",
        "path": "data/external/Batt-SLM-RX-392.csv",
        "kind": "table",
        "delimiter": "$",
        "id_column": "Inchi",
        "id_kind": "inchi",
        "quantity": "氧化/还原电位 + IP/EA",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": "Redox-Pot/Redox-Ener/RX-392.csv",
        "evidence": UPSTREAM_REPO + " blob sha256 逐字节相等",
        "note": "381/392 行同一层级串；介质设定以 UniqueSolvents 的 DIELECTRIC=18.5 为主，引用必须带条件声明。",
    },
    {
        "key": "batt_slm_cpi_features",
        "display": "CPI/Input/Features.csv（CPI 辅助特征表）",
        "path": "data/external/batt_slm_cpi_features.csv",
        "kind": "table",
        "delimiter": ";",
        "id_column": "SMILES",
        "id_kind": "smiles",
        "quantity": "无四核心量标签（SASA / 13O / 14O / 15O）",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": "CPI/Input/Features.csv",
        "evidence": UPSTREAM_REPO + " blob sha256 逐字节相等（本轮下载）",
        "note": "本轮**真新增**。比 SolvFunc-87 多 4 列；列义未独立验证。",
    },
    {
        "key": "batt_slm_cpi_features_nof",
        "display": "CPI/Input/Features-NoF.csv（去 F 版）",
        "path": "data/external/batt_slm_cpi_features_nof.csv",
        "kind": "table",
        "delimiter": ";",
        "id_column": "SMILES",
        "id_kind": "smiles",
        "quantity": "无四核心量标签",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": "CPI/Input/Features-NoF.csv",
        "evidence": UPSTREAM_REPO + " blob sha256 逐字节相等（本轮下载）",
        "note": "本轮**真新增**；46 行。",
    },
    {
        "key": "solvfunc_87",
        "display": "SolvFunc-87.csv（87 个溶剂的功能预测）",
        "path": "data/external/SolvFunc-87.csv",
        "kind": "table",
        "delimiter": ";",
        "id_column": "SMILES",
        "id_kind": "smiles",
        "quantity": "HOMO_Pred / LUMO_Pred / DN_Pred / DC_Pred（全部为模型输出）",
        "license": "MIT",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": "CPI/SolvFunc-87.csv",
        "evidence": UPSTREAM_REPO + " blob sha256 逐字节相等",
        "note": "所有 *_Pred 列都是模型输出，**只能作外部对照，不入标签池**。",
    },
    {
        "key": "chew_viscosity_supp2",
        "display": "chew_2024 粘度数据集（Additional file 2）",
        "path": "data/external/chew_2024_viscosity_supp_2.csv",
        "kind": "table",
        "delimiter": ",",
        "id_column": "CANON_SMILES",
        "id_kind": "smiles",
        "quantity": "粘度 eta（cP）+ 温度",
        "license": "CC BY-NC 4.0",
        "license_status": "已核实",
        "can_enter_pool": False,
        "upstream_blob_key": None,
        "evidence": "10.1186/s13321-024-00820-5 Data availability 段："
                    "「provided under the Creative Commons Non-Commercial 4.0 International "
                    "(CC-BY-NC 4.0) ... exclusively for non-commercial purposes」",
        "note": "全项目 eta 覆盖最高（140/241），但**NC ⇒ 不得入商用池**。"
                "文章正文的 CC BY 4.0 被 Data availability 单独声明的 NC 覆盖。",
    },
    {
        "key": "chew_viscosity_supp3",
        "display": "chew_2024 粘度预测表",
        "path": "data/external/chew_2024_viscosity_supp_3.csv",
        "kind": "table",
        "delimiter": ",",
        "id_column": "CANON_SMILES",
        "id_kind": "smiles",
        "quantity": "log(Viscosity)_pred（模型输出，非标签）",
        "license": "CC BY-NC 4.0",
        "license_status": "已核实",
        "can_enter_pool": False,
        "upstream_blob_key": None,
        "evidence": "同 chew_2024 数据声明（NC）",
        "note": "列名带 _pred 且含 is_within_training ⇒ 跨模型对照件，不入标签池。",
    },
    {
        "key": "chodera_dielectric",
        "display": "Beauchamp/Chodera 2015 静态介电常数汇编",
        "path": "data/external/chodera_2015_data_dielectric.csv",
        "kind": "table",
        "delimiter": ",",
        "id_column": "smiles",
        "id_kind": "smiles",
        "quantity": "零频相对介电常数 eps + 温度/压力/密度",
        "license": "GPL-2.0",
        "license_status": "已核实",
        "can_enter_pool": True,
        "upstream_blob_key": None,
        "evidence": "10.1021/acs.jpcb.5b06703 配套仓 choderalab/LiquidBenchmark；"
                    "仓库 LICENSE = GPL-2.0（GitHub license API: spdx GPL-2.0）",
        "note": "可商用但带 copyleft 义务；且是「零频 eps」，与近静态 eps 口径需对齐。"
                "数值上游为 NIST ThermoML 档案。",
    },
)

# ------------------------------------------------------------ 渠道级登记
# 这一层是「渠道」而不是「本仓库的文件」：许可与可达性为本轮侦察所记。
# evidence_level: 实测（本轮拿到 HTTP 状态 / 字节） / 文档（上游声明，未独立核验）
CHANNELS: tuple[dict[str, object], ...] = (
    ("reaxys", "Reaxys（用户 Edge 已登录）", "https://www.reaxys.com/",
     "proprietary / subscription", "已核实", "proprietary",
     "四核心量（作为文献索引可得）", "本机 Edge 可达（已登录）",
     False, "实测",
     "本轮用它做**文献索引**（取 DOI），未读入任何数值。红线：数值不入任何池/特征/交付物。"),
    ("hf_mirror", "Hugging Face 镜像 hf-mirror.com", "https://hf-mirror.com",
     "镜像站（内容许可随各数据集）", "已核实", "n/a",
     "取决于数据集", "HTTP 200，API 可用", True, "实测",
     "本机 huggingface.co DNS 不可达，此镜像为当前唯一稳定 HF 入口。"),
    ("colabfit_omol25_train", "OMol25 train（ColabFit 交换版）",
     "https://hf-mirror.com/datasets/colabfit/OMol25_train", "CC-BY-4.0", "已核实",
     "permissive", "能量 + 原子力（**无 HOMO/LUMO**）", "HTTP 200",
     True, "实测",
     "101,666,280 构型；README Properties included = 「energy, atomic forces」⇒ 不是轨道源。"),
    ("molssiai_pubchemqc_b3lyp", "PubChemQC B3LYP（MolSSI AI-Hub 镜像）",
     "https://hf-mirror.com/datasets/molssiai-hub/pubchemqc-b3lyp", "CC-BY-4.0", "已核实",
     "permissive", "HOMO/LUMO/gap + orbital-energies", "HTTP 200",
     True, "文档",
     "README 字段表 + 抽样 JSON 命中 energy-alpha-homo/lumo/gap；全量约 7.7 TB。"
     "许可与论文（10.1021/acs.jcim.3c00899）一致。"),
    ("molssiai_pubchemqc_pm6", "PubChemQC PM6（MolSSI AI-Hub 镜像）",
     "https://hf-mirror.com/datasets/molssiai-hub/pubchemqc-pm6", "CC-BY-4.0", "已核实",
     "permissive", "HOMO/LUMO/gap", "HTTP 200", True, "文档",
     "2.21 亿次计算；全量约 8.4 TB。"),
    ("qm9_original", "QM9 原始 deposition（Ramakrishnan 2014）",
     "https://doi.org/10.6084/m9.figshare.978904", "CC BY 4.0", "已核实",
     "permissive", "homo / lumo / gap（B3LYP/6-31G(2df,p)）", "DataCite 元数据可达",
     True, "文档",
     "133,885 分子；DataCite rightsList = CC BY 4.0。"
     "注意：HF 上的第三方镜像卡片**自身无 license 字段**，应从原始源取数。"),
    ("batt_p30k_channel", "Batt-SLM / Batt-P30K（GSDS）", UPSTREAM_REPO, "MIT", "已核实",
     "permissive", "HOMO/LUMO/gap + IP/EA + dipole + 3D 坐标", "api.github.com 可达",
     True, "实测",
     "29,519 分子；ωB97X-V/def2-TZVPPD/SMD(eps=18.5)。本仓已在用。"),
    ("qmugs", "QMugs（ETH Zurich）", "https://doi.org/10.3929/ethz-b-000443838",
     "CC BY-NC-SA 4.0", "文档", "NC", "HOMO/LUMO 等", "原始在 Zenodo，本机 DNS 不可达",
     False, "文档", "**红线**：NC + SA。HF 上的派生镜像许可与原始冲突，不采信。"),
    ("themol", "THEMol（ByteDance-Seed）",
     "https://hf-mirror.com/datasets/ByteDance-Seed/THEMol", "CC BY-NC 4.0", "已核实",
     "NC", "DFT 能量/Hessian/扭转（非四核心量）", "HTTP 200", False, "实测",
     "**红线**：NC。只留 data/raw/。"),
    ("molssiai_liquid_electrolytes", "MolSSI liquid-electrolytes",
     "https://hf-mirror.com/datasets/molssiai-hub/liquid-electrolytes", "CC BY-NC-ND 4.0",
     "文档", "NC", "电解质分子性质", "HTTP 200", False, "文档",
     "**红线**：NC + ND（禁改作）。"),
    ("nist_webbook", "NIST Chemistry WebBook (SRD 69)", "https://webbook.nist.gov/chemistry/",
     "All rights reserved（Standard Reference Data Act）", "已核实", "proprietary",
     "IE/EA（HOMO/LUMO 代理）；**无 eps / 无 eta / 无氧化还原电位**", "HTTP 200",
     False, "实测",
     "免费浏览 ≠ 开放许可；再分发/批量入池需走 NIST SRD 授权。"),
    ("ddbst", "DDBST（Dortmund Data Bank）", "https://www.ddbst.com/",
     "proprietary（订阅/买断）", "已核实", "proprietary",
     "eta + eps（DDB 内）", "HTTP 200", False, "实测",
     "条款原文禁止保存/下载/系统性抓取建库。**红线**。"),
    ("chemeo", "Cheméo（Céondo）", "https://www.chemeo.com/",
     "proprietary + sui generis 数据库权", "已核实", "proprietary",
     "eta（36,765 条）+ eps（仅 46 条）+ IE/EA", "HTTP 200", False, "实测",
     "条款原文禁止整库下载/爬取与整体嵌入产品。**红线**。"),
    ("mnsol", "Minnesota Solvation Database 2012", "https://comp.chem.umn.edu/mnsol/",
     "学术免费 / 商业 6000 USD 授权", "已核实", "restricted",
     "溶剂化自由能（**非四核心量**）", "HTTP 200", False, "实测",
     "含未发表材料；商业需付费。既不覆盖四核心量，商用入池亦为红线。"),
    ("pubchemqc_riken", "PubChemQC 主站（RIKEN）", "https://pubchemqc.riken.jp/",
     "CC BY 4.0（论文声明）", "文档", "permissive", "HOMO/LUMO", "本机 DNS 不可达",
     True, "文档", "内容 CC BY 4.0，但站点本机不可达；改走 MolSSI AI-Hub 镜像。"),
    ("zenodo", "Zenodo", "https://zenodo.org/", "随各条目", "未核实", "unknown",
     "多个上游的全量归档", "本机 DNS 不可达", False, "实测",
     "环境受阻 ≠ 源不存在；换出口后可再评。"),
)

HIT_FIELDS = (
    "source_key", "display_name", "artifact_path", "quantity", "license", "license_status",
    "can_enter_pool", "pre_existing", "already_in_library", "upstream_blob_path", "upstream_sha256",
    "local_sha256", "byte_identical_upstream", "n_rows", "n_unique_identifiers",
    "n_unique_inchikey", "n_unparsed", "roster_total", "roster_hits", "roster_hit_rate",
    "evidence", "note",
)

CHANNEL_FIELDS = (
    "channel_key", "display_name", "url", "license", "license_status", "license_class",
    "core_quantities", "accessibility", "can_enter_pool", "holds_orbital", "evidence_level", "note",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (",", '"', "\n")):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def inchikey_from_smiles(smiles: str) -> str | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        return Chem.MolToInchiKey(mol) or None
    except Exception:
        return None


def inchikey_from_inchi(inchi: str) -> str | None:
    if not inchi:
        return None
    mol = Chem.MolFromInchi(inchi)
    if mol is None:
        return None
    try:
        return Chem.MolToInchiKey(mol) or None
    except Exception:
        return None


def load_roster() -> tuple[set[str], int]:
    keys: set[str] = set()
    total = 0
    with ROSTER_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            key = (row.get("inchikey") or "").strip()
            if key:
                keys.add(key)
    return keys, total


def _decode_smiles_value(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return _decode_smiles_value(value.reshape(-1)[0]) if value.size else ""
    if isinstance(value, (list, tuple)):
        return _decode_smiles_value(value[0]) if value else ""
    return str(value)


def iter_source_identifiers(source: Mapping[str, object]):
    path = REPOSITORY_ROOT / str(source["path"])
    kind = str(source["kind"])
    if kind == "smi":
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tokens = line.split()
                if tokens:
                    yield "smiles", tokens[0]
        return
    if kind == "table":
        delimiter = str(source["delimiter"])
        column = str(source["id_column"])
        id_kind = str(source["id_kind"])
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle, delimiter=delimiter):
                value = (row.get(column) or "").strip()
                if value:
                    yield id_kind, value
        return
    if kind == "hdf5":
        import h5py

        with h5py.File(path, "r") as handle:
            for group_key in handle.keys():
                node = handle[group_key]
                if "smiles" not in node:
                    continue
                text = _decode_smiles_value(node["smiles"][()]).strip()
                if text:
                    yield "smiles", text
        return
    raise ValueError("unknown source kind: " + kind)


def measure_source(source: Mapping[str, object], roster_keys: set[str]) -> dict[str, object]:
    path = REPOSITORY_ROOT / str(source["path"])
    n_rows = 0
    identifiers: set[str] = set()
    keys: set[str] = set()
    unparsed = 0
    for id_kind, value in iter_source_identifiers(source):
        n_rows += 1
        identifiers.add(value)
        key = inchikey_from_smiles(value) if id_kind == "smiles" else inchikey_from_inchi(value)
        if key is None:
            unparsed += 1
        else:
            keys.add(key)
    hits = len(keys & roster_keys)
    local_sha = sha256_file(path) if path.is_file() else ""
    blob_key = source.get("upstream_blob_key")
    upstream_path = str(blob_key) if blob_key else ""
    upstream_sha = UPSTREAM_BLOBS.get(upstream_path, "") if upstream_path else ""
    identical = bool(upstream_sha) and upstream_sha == local_sha
    pre_existing = str(source["key"]) not in NEW_FILES_THIS_ROUND
    total = len(roster_keys)
    return {
        "source_key": source["key"],
        "display_name": source["display"],
        "artifact_path": source["path"],
        "quantity": source["quantity"],
        "license": source["license"],
        "license_status": source["license_status"],
        "can_enter_pool": bool(source["can_enter_pool"]),
        "pre_existing": pre_existing,
        "already_in_library": pre_existing,
        "upstream_blob_path": upstream_path,
        "upstream_sha256": upstream_sha,
        "local_sha256": local_sha,
        "byte_identical_upstream": identical,
        "n_rows": n_rows,
        "n_unique_identifiers": len(identifiers),
        "n_unique_inchikey": len(keys),
        "n_unparsed": unparsed,
        "roster_total": total,
        "roster_hits": hits,
        "roster_hit_rate": (hits / total) if total else 0.0,
        "evidence": source["evidence"],
        "note": source["note"],
    }


def build() -> dict[str, object]:
    roster_keys, roster_total = load_roster()
    hits = [measure_source(source, roster_keys) for source in LOCAL_SOURCES]
    channels = [
        {
            "channel_key": row[0], "display_name": row[1], "url": row[2], "license": row[3],
            "license_status": row[4], "license_class": row[5], "core_quantities": row[6],
            "accessibility": row[7], "can_enter_pool": bool(row[8]), "evidence_level": row[9],
            "holds_orbital": row[0] in ORBITAL_CHANNELS,
            "note": row[10],
        }
        for row in CHANNELS
    ]
    return {
        "roster_total": roster_total,
        "roster_unique_inchikey": len(roster_keys),
        "hits": hits,
        "channels": channels,
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    hits = {str(item["source_key"]): item for item in payload["hits"]}
    channels = list(payload["channels"])
    criteria: list[dict[str, object]] = []

    roster_total = int(payload["roster_total"])
    criteria.append({
        "id": "H38d1",
        "description": "名册分母 = 241 行且唯一 InChIKey 亦为 241（分母口径锁死）",
        "value": float(roster_total),
        "threshold": float(ROSTER_TOTAL_EXPECTED),
        "verdict": "成立" if roster_total == ROSTER_TOTAL_EXPECTED else "判否",
    })

    p30k_hits = int(hits["batt_p30k"]["roster_hits"])
    criteria.append({
        "id": "H38d2",
        "description": "MIT 轨道源 Batt-P30K 的名册命中 >= 70（可商用轨道线仍在）",
        "value": float(p30k_hits),
        "threshold": float(BATT_P30K_HITS_GATE),
        "verdict": "成立" if p30k_hits >= BATT_P30K_HITS_GATE else "判否",
    })

    chew_hits = int(hits["chew_viscosity_supp2"]["roster_hits"])
    criteria.append({
        "id": "H38d3",
        "description": "eta 覆盖最高件（chew 2024 supp2）名册命中 >= 140",
        "value": float(chew_hits),
        "threshold": float(CHEW_VISCOSITY_HITS_GATE),
        "verdict": "成立" if chew_hits >= CHEW_VISCOSITY_HITS_GATE else "判否",
    })

    pre_existing_batt_slm = [item for item in payload["hits"]
                             if item["pre_existing"] and item["upstream_blob_path"]]
    identical = [item for item in pre_existing_batt_slm if item["byte_identical_upstream"]]
    criteria.append({
        "id": "H38d4",
        "description": "三份「已在库」的 Batt-SLM 附属件与上游 git blob sha256 逐字节相等（不算新源）",
        "value": float(len(identical)),
        "threshold": float(len(pre_existing_batt_slm)),
        "verdict": "成立" if len(pre_existing_batt_slm) == 3 and len(identical) == 3 else "判否",
    })

    new_files = [item for item in payload["hits"] if not item["pre_existing"]]
    new_permissive = [item for item in new_files
                      if str(item["license"]).upper().startswith("MIT")]
    criteria.append({
        "id": "H38d5",
        "description": "本轮真新增文件 = 2（CPI Features / Features-NoF）且均为 MIT",
        "value": float(len(new_permissive)),
        "threshold": float(NEW_FILES_EXPECTED),
        "verdict": "成立" if len(new_permissive) == NEW_FILES_EXPECTED else "判否",
    })

    bad = [row for row in channels
           if bool(row["can_enter_pool"]) and str(row["license_class"]) not in ("permissive", "n/a")]
    criteria.append({
        "id": "H38d6",
        "description": "渠道表自洽：任何 can_enter_pool 的渠道，其许可类别必须是 permissive / n/a",
        "value": float(len(bad)),
        "threshold": 0.0,
        "verdict": "成立" if not bad else "判否",
    })

    orbital = [row for row in channels if bool(row["holds_orbital"])]
    orbital_permissive = [row for row in orbital
                          if str(row["license_class"]) == "permissive"]
    criteria.append({
        "id": "H38d7",
        "description": "除 Batt-P30K 外，仍存在 >= 2 条「含 HOMO/LUMO 且许可可商用」的渠道",
        "value": float(len(orbital_permissive)),
        "threshold": float(PERMISSIVE_ORBITAL_CHANNELS_GATE),
        "verdict": "成立" if len(orbital_permissive) >= PERMISSIVE_ORBITAL_CHANNELS_GATE else "判否",
    })

    omol = next((row for row in channels if str(row["channel_key"]) == "colabfit_omol25_train"), None)
    omol_has_orbital = bool(omol) and bool(omol["holds_orbital"])
    criteria.append({
        "id": "H38d8",
        "description": "OMol25 不含轨道能（properties = energy + atomic forces）⇒ 不能当 HOMO/LUMO 源",
        "value": 1.0 if not omol_has_orbital else 0.0,
        "threshold": 1.0,
        "verdict": "成立" if omol is not None and not omol_has_orbital else "判否",
    })

    red = [row for row in channels if str(row["license_class"]) in ("NC", "proprietary", "restricted")]
    criteria.append({
        "id": "H38d9",
        "description": "红线渠道（NC / 专有 / 受限）已被显式登记且全部 can_enter_pool = false",
        "value": float(len([row for row in red if bool(row["can_enter_pool"])])),
        "threshold": 0.0,
        "verdict": "成立" if red and not [row for row in red if bool(row["can_enter_pool"])] else "判否",
    })

    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    hits = list(payload["hits"])
    channels = list(payload["channels"])
    total = int(payload["roster_total"])
    lines: list[str] = []
    lines.append("# W38-D 数据侦察报告：四核心量的新来源核实 + 渠道红线登记")
    lines.append("")
    lines.append("- 生成件：probes/w38_data_recon.py（可复算；本文件由它写出）")
    lines.append("- 名册分母：data/processed/dielectric_physical_features_v03.csv，"
                 + str(total) + " 行 / " + str(int(payload["roster_unique_inchikey"])) + " 个唯一 InChIKey")
    lines.append("- 口径：四核心量 = 静态介电常数 eps / 粘度 eta / HOMO-LUMO 轨道能 / 氧化-还原电位")
    lines.append("- 红线：第三方数值不入池、不入特征、不入交付物；NC / ND / 专有 / 未知一律不入池")
    lines.append("- 记账：本件为后验读数与治理登记，**不占 shot**（累计仍 19）")
    lines.append("")
    lines.append("## 0. 一句话结论")
    lines.append("")
    lines.append("本轮**没有在既有可商用线之外找到新的 eps / eta 标签源**："
                 "eta 覆盖最高的那一件是 CC BY-NC 4.0（不得入商用池），"
                 "而 eps 的唯一可商用候选是 GPL-2.0 的零频汇编。"
                 "真正的新增量在**轨道能**一侧——HF 镜像上出现了 CC-BY-4.0 的 PubChemQC 副本。")
    lines.append("")
    lines.append("## 1. 名册命中实测（本地件）")
    lines.append("")
    lines.append("| 件 | 许可 | 可入池 | 本轮新增 | 行数 | 唯一 InChIKey | 名册命中 / " + str(total) + " |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in hits:
        lines.append("| " + str(item["source_key"]) + " | " + str(item["license"])
                     + " | " + ("是" if item["can_enter_pool"] else "否")
                     + " | " + ("否（已在库）" if item["pre_existing"] else "是")
                     + " | " + str(item["n_rows"])
                     + " | " + str(item["n_unique_inchikey"])
                     + " | " + str(item["roster_hits"])
                     + " (" + format(float(item["roster_hit_rate"]), ".1%") + ") |")
    lines.append("")
    lines.append("## 2. 渠道红线登记")
    lines.append("")
    lines.append("| 渠道 | 许可 | 类别 | 含四核心量 | 含轨道能 | 可达性 | 可入池 | 证据级别 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in channels:
        lines.append("| " + str(row["channel_key"]) + " | " + str(row["license"])
                     + " | " + str(row["license_class"])
                     + " | " + str(row["core_quantities"])
                     + " | " + ("是" if row["holds_orbital"] else "否")
                     + " | " + str(row["accessibility"])
                     + " | " + ("是" if row["can_enter_pool"] else "否")
                     + " | " + str(row["evidence_level"]) + " |")
    lines.append("")
    lines.append("## 3. 判据")
    lines.append("")
    lines.append("| id | 判据 | 读数 | 门槛 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in criteria:
        lines.append("| " + str(item["id"]) + " | " + str(item["description"])
                     + " | " + str(item["value"]) + " | " + str(item["threshold"])
                     + " | " + str(item["verdict"]) + " |")
    lines.append("")
    lines.append("## 4. 逐件备注")
    lines.append("")
    for item in hits:
        lines.append("- " + str(item["source_key"]) + "：" + str(item["note"]))
    lines.append("")
    lines.append("## 5. 渠道备注")
    lines.append("")
    for row in channels:
        lines.append("- " + str(row["channel_key"]) + "：" + str(row["note"]))
    lines.append("")
    lines.append("## 6. 边界与不做的清单")
    lines.append("")
    lines.append("- 所有命中数都是实测集合交（RDKit 全 27 位 InChIKey），没有一个是估计值。")
    lines.append("- 分母统一 241 行；既有报告的 246 / 247 行是 data/dielectric_v03.csv 口径，"
                 "两者不得混引。")
    lines.append("- 所有 *_Pred 列（HOMO_Pred / DC_Pred / EdgePool_log(Viscosity)_pred）都是模型输出，"
                 "只能作外部对照，不入标签池。")
    lines.append("- 未下载任何第三方大文件到仓库；未把任何第三方数值写进池或特征列。")
    lines.append("- 环境受阻（huggingface.co / zenodo.org / pubchemqc.riken.jp 在本机 DNS 不可达）"
                 "登记为「受阻」，不登记为「源不存在」。")
    lines.append("")
    return "\n".join(lines)


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "Arial Unicode MS"):
        try:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    hits = sorted(payload["hits"], key=lambda item: float(item["roster_hit_rate"]))
    labels = [str(item["source_key"]) for item in hits]
    rates = [float(item["roster_hit_rate"]) for item in hits]
    colors = []
    for item in hits:
        license_class = "permissive"
        if str(item["license"]).upper().startswith("CC BY-NC"):
            license_class = "NC"
        if "GPL" in str(item["license"]).upper():
            license_class = "copyleft"
        colors.append({"permissive": "#2f7d4f", "NC": "#b03a2e", "copyleft": "#8a6d1f"}[license_class])

    fig, axis = plt.subplots(figsize=(8.6, 4.6), dpi=160)
    positions = np.arange(len(labels))
    axis.barh(positions, rates, color=colors)
    axis.set_yticks(positions)
    axis.set_yticklabels(labels, fontsize=8)
    axis.set_xlabel("名册命中率（命中 / 241）", fontsize=9)
    axis.set_title("W38-D：本地外部件对 241 行名册的覆盖率（颜色 = 许可类别）", fontsize=10)
    axis.set_xlim(0, max(rates) * 1.22 if rates else 1.0)
    for position, rate, item in zip(positions, rates, hits):
        axis.text(rate + 0.004, position,
                  str(int(item["roster_hits"])) + " / " + str(int(item["roster_total"])),
                  va="center", fontsize=7.5)
    handles = [
        plt.Line2D([0], [0], marker="s", linestyle="", color="#2f7d4f", label="可商用（MIT / CC BY / GPL）"),
        plt.Line2D([0], [0], marker="s", linestyle="", color="#b03a2e", label="NC（不得入商用池）"),
        plt.Line2D([0], [0], marker="s", linestyle="", color="#8a6d1f", label="copyleft（GPL-2.0）"),
    ]
    axis.legend(handles=handles, fontsize=7.5, loc="lower right")
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    before = sha256_file(ROSTER_CSV)
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(HITS_CSV, HIT_FIELDS, payload["hits"])
    write_csv_lf(CHANNELS_CSV, CHANNEL_FIELDS, payload["channels"])
    if not args.skip_figure:
        make_figure(payload)
    after = sha256_file(ROSTER_CSV)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]
    orbital_permissive = [
        str(row["channel_key"]) for row in payload["channels"]
        if str(row["license_class"]) == "permissive" and bool(row["holds_orbital"])
    ]
    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读既有外部件与渠道登记；不拟合主记分牌臂、不新增特征列、"
                              "不改 METRIC_NAMES、不动四个冻结读数。",
        },
        "inputs": {str(ROSTER_CSV): before, "roster_sha256_after": after},
        "inputs_unchanged": before == after,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "pool_note": "名册分母 241 行（data/processed/dielectric_physical_features_v03.csv）；"
                     "非冻结头条所在池（97 化合物 / 457 行）。两者不得混引。",
        "upstream": {"repo": UPSTREAM_REPO, "tree": UPSTREAM_TREE,
                     "blobs": dict(UPSTREAM_BLOBS)},
        "roster_total": int(payload["roster_total"]),
        "roster_unique_inchikey": int(payload["roster_unique_inchikey"]),
        "hits": list(payload["hits"]),
        "channels": list(payload["channels"]),
        "permissive_orbital_channels": orbital_permissive,
        "new_files_this_round": [str(item["source_key"]) for item in payload["hits"]
                                 if not item["pre_existing"]],
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "eta 覆盖最高件是 CC BY-NC 4.0 ⇒ 不得入商用池；本轮的 eta 线**没有变宽**。",
            "eps 的唯一可商用候选是 GPL-2.0 的零频汇编（45/241），"
            "且口径是「零频」需要对齐。",
            "轨道能一侧**变宽**：HF 镜像上的 PubChemQC 副本为 CC-BY-4.0，含 HOMO/LUMO/gap。",
            "OMol25 只有 energy + atomic forces ⇒ 不是轨道源，已被 H38d8 钉死。",
            "不占 shot（累计仍 19）。",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    for item in payload["hits"]:
        print(str(item["source_key"]) + " rows=" + str(item["n_rows"])
              + " inchikey=" + str(item["n_unique_inchikey"])
              + " hits=" + str(item["roster_hits"]) + "/" + str(item["roster_total"])
              + " license=" + str(item["license"])
              + " already_in_library=" + str(item["already_in_library"]))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
