#!/usr/bin/env python
"""KPI 15+14 短清单 vs 本仓漏斗：一次跨池交叉试跑（执行手册 AA-5 五）。

预注册（跑前冻结，跑后不回填、不放宽）：
    probes/kpi_funnel_cross_run_prereg.json

本探针只做三件事，不多做一件：
  1. 身份层：把短清单 29 行（14 行带 SMILES、15 行带 CAS）解析成 InChIKey，
     使交集按身份算而不是按名字算。
  2. 漏斗复跑：在本仓 Batt-P30K 池上独立跑 S0-S3，逐级报存活数与存活率。
     S4（MP/BP/FP 三阈值）本仓没有模型，登记为缺口，不猜、不插值、不用别人的表补。
  3. 交集与属性交叉核对：短清单 vs Batt-P30K / vs 314 键名册 / vs 冻结 epsilon 表；
     以及 KPI 印刷 MP/BP/FP 与本仓独立取得的 PubChem 汇编值的对照。

不做：不拟合任何模型、不产任何 R2、不把 Batt-P30K 计数当成 KPI 级联的复现、
不用猜的结构补齐未解析的 CAS 行、不把名字匹配当身份匹配、不再分发短清单。

用法：
    python probes/kpi_funnel_cross_run.py --resolve-online   # 首跑：联网解析 CAS，写表
    python probes/kpi_funnel_cross_run.py                    # 增量：缓存里已有的不再联网
    python probes/kpi_funnel_cross_run.py --check            # 离线重跑，与磁盘产物比对

离线可复现的边界：CAS 行的值一旦落进 data/reference/kpi_shortlist_identity.csv（已提交），
离线模式就直接采用该表的取值，因此身份层与全部判据在干净克隆上 --check 可复现。
但属性交叉核对要读 data/external/g1plus/ 下的 PubChem 缓存，该目录被 .gitignore 忽略，
干净克隆上没有它，那一节会照实记 available=false。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.al_round1 import HAZARD_SMARTS

DEFAULT_PREREG = REPOSITORY_ROOT / "probes" / "kpi_funnel_cross_run_prereg.json"
DEFAULT_SHORTLIST = REPOSITORY_ROOT / "data" / "reference" / "kpi_15_14_shortlists.csv"
DEFAULT_IDENTITY_CSV = REPOSITORY_ROOT / "data" / "reference" / "kpi_shortlist_identity.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "kpi_funnel_cross_run_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "kpi_funnel_cross_run.md"

PUBCHEM_CACHE_DIR = (
    REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "kpi_shortlist_identity"
)
BATT_P30K_H5 = REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
EPS_V03_CSV = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
EPS_V11PLUS_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
LIQUID_WINDOW_CSV = (
    REPOSITORY_ROOT
    / "data"
    / "external"
    / "g1plus"
    / "pubchem"
    / "liquid_window"
    / "liquid_window_selected.csv"
)

PUBCHEM_PROPERTY_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}"
    "/property/SMILES,ConnectivitySMILES,InChIKey,MolecularFormula,MolecularWeight/JSON"
)
USER_AGENT = "electrolyte-ml-kpi-funnel-cross-run/1.0 (structure cross-check)"
RESOLVED_CAS_NOTE = "PubChem PUG-REST 解析；source_url 与 retrieved_at 即本行取数凭据，本地缓存见 data/external/g1plus/pubchem/kpi_shortlist_identity/"
THROTTLE_SECONDS = 0.25

IDENTITY_COLUMNS: tuple[str, ...] = (
    "row_key",
    "shortlist",
    "rank",
    "cas",
    "smiles_from_shortlist",
    "resolved_route",
    "inchikey",
    "canonical_smiles",
    "connectivity_smiles",
    "molecular_formula",
    "molecular_weight",
    "heavy_atom_count",
    "elements",
    "pubchem_cid",
    "resolution_status",
    "resolved_from",
    "source_url",
    "retrieved_at",
    "notes",
)

# S1：KPI SI 第 11 节的结构过滤，逐字来自手册 AA-3 第 3 条。
S1_SMARTS: tuple[tuple[str, str], ...] = (
    ("hydroxyl", "[OX2H]"),
    ("carboxyl", "[CX3](=O)[OX2H1]"),
)
MOLWT_GATE = 600.0
HEAVY_ATOM_GATE = 30

# S4：KPI SI 第 11 节的三阈值。本仓无 MP/BP/FP 模型，只用于 A 判据的自洽性核对。
THRESHOLDS: tuple[tuple[str, str, float], ...] = (
    ("mp_k", "<", 230.0),
    ("bp_k", ">", 430.0),
    ("fp_k", ">", 360.0),
)

LIQUID_WINDOW_PROPERTY: dict[str, str] = {
    "mp_k": "melting_point",
    "bp_k": "boiling_point",
    "fp_k": "flash_point",
}

BATT_LABEL_NAMES: tuple[str, ...] = ("homo", "lumo", "gap", "ip", "ea", "ener")

NETWORK_CALLS = 0
CACHE_HITS = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def file_provenance(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": path.relative_to(REPOSITORY_ROOT).as_posix(), "available": False}
    return {
        "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
        "available": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def row_key(row: Mapping[str, str]) -> str:
    return "{}-{}".format(row["shortlist"], row["rank"])


def _rdkit_record(smiles: str) -> dict[str, Any]:
    """SMILES 路线：RDKit 直解，不重写、不规范化后再转录。"""

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {"resolution_status": "unresolved_rdkit", "notes": "RDKit 无法解析该 SMILES"}
    inchikey = Chem.MolToInchiKey(molecule)
    if not inchikey:
        return {"resolution_status": "unresolved_rdkit", "notes": "RDKit 未能给出 InChIKey"}
    elements = sorted({atom.GetSymbol() for atom in molecule.GetAtoms()})
    return {
        "inchikey": inchikey,
        "canonical_smiles": Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True),
        "connectivity_smiles": Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(molecule),
        "molecular_weight": f"{Descriptors.MolWt(molecule):.4f}",
        "heavy_atom_count": molecule.GetNumHeavyAtoms(),
        "elements": " ".join(elements),
        "resolution_status": "resolved_rdkit",
        "resolved_from": "rdkit_from_shortlist_smiles",
        "notes": "",
    }


def _cache_paths(cas: str) -> tuple[Path, Path]:
    stem = PUBCHEM_CACHE_DIR / f"{cas}.json"
    return stem, stem.with_suffix(stem.suffix + ".url")


def _fetch_pubchem(cas: str, *, refresh: bool) -> tuple[str | None, str, str]:
    """返回 (响应正文, url, 来源标签)。取数失败不抛异常，交由调用方记 unresolved。"""

    global NETWORK_CALLS, CACHE_HITS

    url = PUBCHEM_PROPERTY_URL.format(cas=urllib.parse.quote(cas, safe=""))
    cache, marker = _cache_paths(cas)
    if (
        not refresh
        and cache.is_file()
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == url
    ):
        CACHE_HITS += 1
        return cache.read_text(encoding="utf-8"), url, "local_cache"

    last: Exception | None = None
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            NETWORK_CALLS += 1
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, url, "not_found_404"
            last = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        else:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(body, encoding="utf-8")
            marker.write_text(url + chr(10), encoding="utf-8")
            time.sleep(THROTTLE_SECONDS)
            return body, url, "network"
        time.sleep(THROTTLE_SECONDS * (2**attempt))
    raise RuntimeError(f"PubChem 取数失败 {url}: {last}")


def _parse_pubchem_record(body: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
        properties = payload["PropertyTable"]["Properties"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    if "InChIKey" not in properties:
        return None
    return properties


def _pubchem_record(properties: Mapping[str, Any]) -> dict[str, Any]:
    canonical = str(properties.get("SMILES", ""))
    connectivity = str(properties.get("ConnectivitySMILES", ""))
    elements = ""
    heavy = ""
    molecule = Chem.MolFromSmiles(canonical) if canonical else None
    if molecule is None and connectivity:
        molecule = Chem.MolFromSmiles(connectivity)
    if molecule is not None:
        heavy = str(molecule.GetNumHeavyAtoms())
        elements = " ".join(sorted({atom.GetSymbol() for atom in molecule.GetAtoms()}))
    return {
        "inchikey": str(properties["InChIKey"]),
        "canonical_smiles": canonical,
        "connectivity_smiles": connectivity,
        "molecular_formula": str(properties.get("MolecularFormula", "")),
        "molecular_weight": str(properties.get("MolecularWeight", "")),
        "heavy_atom_count": heavy,
        "elements": elements,
        "pubchem_cid": str(properties.get("CID", "")),
        "resolution_status": "resolved_pubchem",
        "resolved_from": "pubchem_pug_rest",
    }


def _identity_from_committed_table(table: Mapping[str, str]) -> dict[str, Any]:
    return {
        "inchikey": table["inchikey"],
        "canonical_smiles": table["canonical_smiles"],
        "connectivity_smiles": table["connectivity_smiles"],
        "molecular_formula": table["molecular_formula"],
        "molecular_weight": table["molecular_weight"],
        "heavy_atom_count": table["heavy_atom_count"],
        "elements": table["elements"],
        "pubchem_cid": table.get("pubchem_cid", ""),
        "resolution_status": table["resolution_status"],
        "resolved_from": table["resolved_from"],
        "source_url": table.get("source_url", ""),
        "retrieved_at": table.get("retrieved_at", ""),
    }


def _retrieved_at_from_disk(committed: Mapping[str, Mapping[str, str]], key: str, cas: str) -> str:
    """缓存命中时沿用磁盘上已记的取数时刻，保证身份表字节可复现。"""

    if key in committed and committed[key].get("retrieved_at"):
        return committed[key]["retrieved_at"]
    cache, _ = _cache_paths(cas)
    if cache.is_file():
        stamp = datetime.fromtimestamp(cache.stat().st_mtime, tz=UTC)
        return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return utc_now()


def resolve_identities(
    shortlist: Sequence[Mapping[str, str]],
    *,
    online: bool,
    refresh: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """逐行解析身份。SMILES 行永远本地 RDKit；CAS 行走缓存/网络/已提交表。"""

    committed: dict[str, dict[str, str]] = {}
    if DEFAULT_IDENTITY_CSV.is_file():
        committed = {row["row_key"]: row for row in read_csv_rows(DEFAULT_IDENTITY_CSV)}

    records: list[dict[str, Any]] = []
    drift: list[str] = []
    for row in shortlist:
        key = row_key(row)
        record: dict[str, Any] = {
            "row_key": key,
            "shortlist": row["shortlist"],
            "rank": row["rank"],
            "cas": row["cas"],
            "smiles_from_shortlist": row["smiles"],
            "resolved_route": "",
            "inchikey": "",
            "canonical_smiles": "",
            "connectivity_smiles": "",
            "molecular_formula": "",
            "molecular_weight": "",
            "heavy_atom_count": "",
            "elements": "",
            "pubchem_cid": "",
            "resolution_status": "unresolved_no_identifier",
            "resolved_from": "",
            "source_url": "",
            "retrieved_at": "",
            "notes": "",
        }

        if row["smiles"]:
            record.update(_rdkit_record(row["smiles"]))
            record["resolved_route"] = "smiles_rdkit"
        elif row["cas"]:
            record["resolved_route"] = "cas_pubchem"
            body: str | None = None
            url = ""
            origin = ""
            if online:
                body, url, origin = _fetch_pubchem(row["cas"], refresh=refresh)
            if (
                body is None
                and key in committed
                and committed[key]["resolution_status"].startswith("resolved_pubchem")
            ):
                record.update(_identity_from_committed_table(committed[key]))
                record["notes"] = RESOLVED_CAS_NOTE
                records.append(record)
                continue
            if body is None:
                record["resolution_status"] = (
                    "unresolved_offline_no_cache" if not online else "unresolved_pubchem_" + origin
                )
                record["source_url"] = url
                record["notes"] = "照实记 unresolved，不用猜的结构补位。"
                records.append(record)
                continue
            properties = _parse_pubchem_record(body)
            if properties is None:
                record["resolution_status"] = "unresolved_pubchem_unparsable_payload"
                record["source_url"] = url
                records.append(record)
                continue
            record.update(_pubchem_record(properties))
            record["source_url"] = url
            if origin == "local_cache":
                record["retrieved_at"] = _retrieved_at_from_disk(committed, key, row["cas"])
            else:
                record["retrieved_at"] = utc_now()
            record["notes"] = RESOLVED_CAS_NOTE

        if record["inchikey"] and key in committed:
            previous = committed[key]
            if previous.get("inchikey") and previous["inchikey"] != record["inchikey"]:
                drift.append(
                    "{}: 磁盘 {} vs 本轮 {}".format(key, previous["inchikey"], record["inchikey"])
                )
        records.append(record)

    meta = {
        "rows": len(records),
        "resolved": sum(1 for row in records if row["inchikey"]),
        "unresolved": [row["row_key"] for row in records if not row["inchikey"]],
        "drift_vs_committed_table": drift,
    }
    return records, meta


def identity_csv_text(records: Sequence[Mapping[str, Any]]) -> str:
    lines = [",".join(IDENTITY_COLUMNS)]
    for record in sorted(records, key=lambda item: (item["shortlist"], int(item["rank"]))):
        cells: list[str] = []
        for column in IDENTITY_COLUMNS:
            value = str(record.get(column, ""))
            if any(char in value for char in (",", '"', chr(10))):
                value = '"' + value.replace('"', '""') + '"'
            cells.append(value)
        lines.append(",".join(cells))
    return chr(10).join(lines) + chr(10)


def self_consistency(
    records: Sequence[Mapping[str, Any]], shortlist: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    printed = {row_key(row): row for row in shortlist}
    patterns = [(name, Chem.MolFromSmarts(smarts)) for name, smarts in S1_SMARTS]
    rows: list[dict[str, Any]] = []
    violations = 0

    for record in sorted(records, key=lambda item: (item["shortlist"], int(item["rank"]))):
        row = printed[record["row_key"]]
        entry: dict[str, Any] = {
            "row_key": record["row_key"],
            "cas": record["cas"],
            "smiles": record["smiles_from_shortlist"],
            "violations": [],
        }
        structure = record["canonical_smiles"] or record["connectivity_smiles"]
        molecule = Chem.MolFromSmiles(structure) if structure else None

        if molecule is None:
            entry["violations"].append("structure_unavailable")
        else:
            for name, smarts in patterns:
                if smarts is not None and molecule.HasSubstructMatch(smarts):
                    entry["violations"].append("s1_" + name)
            heavy = molecule.GetNumHeavyAtoms()
            entry["heavy_atom_count"] = heavy
            if heavy >= HEAVY_ATOM_GATE:
                entry["violations"].append(f"s1_heavy_atoms_ge_{HEAVY_ATOM_GATE}")
            weight = Descriptors.MolWt(molecule)
            entry["molwt_rdkit"] = round(weight, 4)
            if weight >= MOLWT_GATE:
                entry["violations"].append(f"s1_molwt_ge_{MOLWT_GATE:g}")

        for column, operator, bound in THRESHOLDS:
            raw = row.get(column, "")
            entry[column] = raw
            if raw == "":
                entry["violations"].append("threshold_missing_" + column)
                continue
            value = float(raw)
            satisfied = value < bound if operator == "<" else value > bound
            if not satisfied:
                entry["violations"].append(
                    "threshold_{}_{}_{:g}".format(
                        column, "not_lt" if operator == "<" else "not_gt", bound
                    )
                )

        entry["violations"] = sorted(entry["violations"])
        if entry["violations"]:
            violations += 1
        rows.append(entry)

    return {
        "rows_checked": len(rows),
        "rows_with_violations": violations,
        "violating_rows": [entry["row_key"] for entry in rows if entry["violations"]],
        "allowed_violations": 0,
        "passed": violations == 0,
        "detail": rows,
    }


def _group_sort_key(name: str) -> tuple[int, str]:
    prefix = "CompMol"
    if not name.startswith(prefix):
        return (10**9, name)
    try:
        return (int(name[len(prefix) :]), name)
    except ValueError:
        return (10**9, name)


def _smiles_from_group(group: h5py.Group, key: str) -> str:
    if "smiles" not in group:
        raise ValueError(f"Batt-P30K {key} 缺 smiles")
    raw = group["smiles"][0]
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _labels_from_group(group: h5py.Group, key: str) -> dict[str, Any]:
    labels: dict[str, Any] = {"group": key}
    for name in BATT_LABEL_NAMES:
        if name in group:
            labels[name] = round(float(group[name][0]), 6)
    if "dipole" in group:
        components = [float(value) for value in group["dipole"][...]]
        labels["dipole_norm"] = round(sum(value * value for value in components) ** 0.5, 6)
    return labels


def run_pool_funnel(whitelist: set[str]) -> dict[str, Any]:
    if not BATT_P30K_H5.is_file():
        return {
            "available": False,
            "why": "data/raw/batt/Batt-P30K.h5 缺失（data/raw/* 被 .gitignore 忽略，干净克隆上没有该文件）",
            "provenance": file_provenance(BATT_P30K_H5),
            "stages": [],
            "pool_inchikeys": [],
            "labels_by_inchikey": {},
        }

    RDLogger.DisableLog("rdApp.*")
    s1_patterns = [(name, Chem.MolFromSmarts(smarts)) for name, smarts in S1_SMARTS]
    hazard_patterns = {
        name: [
            Chem.MolFromSmarts(item)
            for item in ((smarts,) if isinstance(smarts, str) else smarts)
        ]
        for name, smarts in HAZARD_SMARTS.items()
    }

    counts = {
        "S0_pool": 0,
        "S1_kpi_structural_filter": 0,
        "S2_our_hazard_gate": 0,
        "S3_element_whitelist_derived": 0,
    }
    unparsable = 0
    s1_reasons: dict[str, int] = {}
    s2_reasons: dict[str, int] = {}
    s3_reasons: dict[str, int] = {}
    keys: list[str] = []
    hits: dict[str, dict[str, Any]] = {}

    with h5py.File(BATT_P30K_H5, "r") as handle:
        for group_key in sorted(handle.keys(), key=_group_sort_key):
            group = handle[group_key]
            molecule = Chem.MolFromSmiles(_smiles_from_group(group, group_key))
            if molecule is None:
                unparsable += 1
                continue
            counts["S0_pool"] += 1

            s1_block: list[str] = []
            for name, smarts in s1_patterns:
                if smarts is not None and molecule.HasSubstructMatch(smarts):
                    s1_block.append(name)
            if molecule.GetNumHeavyAtoms() >= HEAVY_ATOM_GATE:
                s1_block.append("heavy_atoms")
            if Descriptors.MolWt(molecule) >= MOLWT_GATE:
                s1_block.append("molwt")
            if s1_block:
                for reason in s1_block:
                    s1_reasons[reason] = s1_reasons.get(reason, 0) + 1
                continue
            counts["S1_kpi_structural_filter"] += 1

            s2_block = [
                name
                for name, patterns in hazard_patterns.items()
                if any(
                    pattern is not None and molecule.HasSubstructMatch(pattern)
                    for pattern in patterns
                )
            ]
            if s2_block:
                for reason in s2_block:
                    s2_reasons[reason] = s2_reasons.get(reason, 0) + 1
                continue
            counts["S2_our_hazard_gate"] += 1

            elements = {atom.GetSymbol() for atom in molecule.GetAtoms()}
            outside = sorted(elements - whitelist)
            if outside:
                token = "outside_whitelist:" + "+".join(outside)
                s3_reasons[token] = s3_reasons.get(token, 0) + 1
                continue
            counts["S3_element_whitelist_derived"] += 1

            inchikey = Chem.MolToInchiKey(molecule)
            keys.append(inchikey)
            hits[inchikey] = _labels_from_group(group, group_key)

    pool = counts["S0_pool"]
    stages = [
        {
            "id": "S0",
            "name": "pool",
            "survivors": counts["S0_pool"],
            "excluded_here": 0,
            "survival_rate": 1.0,
        },
        {
            "id": "S1",
            "name": "kpi_structural_filter",
            "survivors": counts["S1_kpi_structural_filter"],
            "excluded_here": counts["S0_pool"] - counts["S1_kpi_structural_filter"],
            "survival_rate": counts["S1_kpi_structural_filter"] / pool,
            "exclusion_reasons": s1_reasons,
        },
        {
            "id": "S2",
            "name": "our_hazard_gate",
            "survivors": counts["S2_our_hazard_gate"],
            "excluded_here": counts["S1_kpi_structural_filter"] - counts["S2_our_hazard_gate"],
            "survival_rate": counts["S2_our_hazard_gate"] / pool,
            "exclusion_reasons": s2_reasons,
        },
        {
            "id": "S3",
            "name": "element_whitelist_derived",
            "survivors": counts["S3_element_whitelist_derived"],
            "excluded_here": counts["S2_our_hazard_gate"] - counts["S3_element_whitelist_derived"],
            "survival_rate": counts["S3_element_whitelist_derived"] / pool,
            "exclusion_reasons": s3_reasons,
        },
        {
            "id": "S4",
            "name": "property_thresholds",
            "survivors": None,
            "excluded_here": None,
            "survival_rate": None,
            "registered_as": "gap",
            "why": "本仓没有 MP/BP/FP 模型，Batt-P30K 也不带这三性质；不跑、不猜。",
        },
    ]
    return {
        "available": True,
        "provenance": file_provenance(BATT_P30K_H5),
        "unparsable_smiles": unparsable,
        "stages": stages,
        "pool_inchikeys": keys,
        "labels_by_inchikey": hits,
        "n_declared": 29519,
        "n_measured_this_round": counts["S0_pool"],
    }


def _inchikey_column(path: Path, column: str) -> set[str]:
    if not path.is_file():
        return set()
    return {row[column] for row in read_csv_rows(path) if row.get(column)}


def intersect(
    records: Sequence[Mapping[str, Any]],
    *,
    pool: Mapping[str, Any],
    roster: set[str],
    eps_v03: set[str],
    eps_v11plus: set[str],
) -> dict[str, Any]:
    resolved = {record["inchikey"]: record for record in records if record["inchikey"]}
    pool_keys = set(pool.get("pool_inchikeys", []))
    labels = pool.get("labels_by_inchikey", {})

    def members(keys: set[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key in sorted(keys):
            record = resolved[key]
            entry: dict[str, Any] = {
                "row_key": record["row_key"],
                "shortlist": record["shortlist"],
                "rank": int(record["rank"]),
                "cas": record["cas"],
                "smiles": record["smiles_from_shortlist"],
                "inchikey": key,
            }
            if key in labels:
                entry["batt_p30k_labels"] = labels[key]
            out.append(entry)
        return out

    batt_hits = set(resolved) & pool_keys
    return {
        "distinct_inchikeys": len(resolved),
        "distinct_inchikeys_note": "29 行若出现重复结构则去重后按 InChIKey 计数",
        "vs_batt_p30k": {
            "n": len(batt_hits),
            "members": members(batt_hits) if pool.get("available") else [],
            "comparable": bool(pool.get("available")),
            "why_not_comparable": (
                None if pool.get("available") else "Batt-P30K 缺失，交集不可算"
            ),
        },
        "vs_roster_314": {"n": len(set(resolved) & roster), "members": members(set(resolved) & roster)},
        "vs_epsilon_v03": {
            "n": len(set(resolved) & eps_v03),
            "members": members(set(resolved) & eps_v03),
        },
        "vs_epsilon_v11plus": {
            "n": len(set(resolved) & eps_v11plus),
            "members": members(set(resolved) & eps_v11plus),
        },
    }


def property_crosscheck(
    records: Sequence[Mapping[str, Any]], shortlist: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    printed = {row_key(row): row for row in shortlist}
    if not LIQUID_WINDOW_CSV.is_file():
        return {"available": False, "comparisons": [], "n_compared": 0}

    window: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv_rows(LIQUID_WINDOW_CSV):
        window[(row["inchikey"], row["property"])] = row

    comparisons: list[dict[str, Any]] = []
    for record in records:
        if not record["inchikey"]:
            continue
        row = printed[record["row_key"]]
        for column, prop in LIQUID_WINDOW_PROPERTY.items():
            source = window.get((record["inchikey"], prop))
            raw = row.get(column, "")
            if source is None or raw == "":
                continue
            if source.get("unit") != "degC" or not source.get("value_numeric"):
                continue
            deposited_k = float(source["value_numeric"]) + 273.15
            printed_k = float(raw)
            comparisons.append(
                {
                    "row_key": record["row_key"],
                    "inchikey": record["inchikey"],
                    "property": prop,
                    "printed_k": printed_k,
                    "deposited_k": round(deposited_k, 2),
                    "deposited_raw": source.get("value_raw", ""),
                    "delta_k": round(printed_k - deposited_k, 2),
                    "depositor": source.get("depositor", ""),
                    "reference": source.get("reference", ""),
                }
            )

    deltas = sorted(abs(item["delta_k"]) for item in comparisons)
    return {
        "available": True,
        "source": file_provenance(LIQUID_WINDOW_CSV),
        "n_compared": len(comparisons),
        "max_abs_delta_k": max(deltas) if deltas else None,
        "median_abs_delta_k": deltas[len(deltas) // 2] if deltas else None,
        "comparisons": comparisons,
        "scope_note": "只比对本仓名册已覆盖到的行；未覆盖的行没有独立值，照实不填。",
    }


def build_summary(
    *,
    prereg: Mapping[str, Any],
    shortlist: Sequence[Mapping[str, str]],
    records: Sequence[Mapping[str, Any]],
    identity_meta: Mapping[str, Any],
    criterion_a: Mapping[str, Any],
    pool: Mapping[str, Any],
    intersections: Mapping[str, Any],
    crosscheck: Mapping[str, Any],
    whitelist: Sequence[str],
    whitelist_rows: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task": "kpi_funnel_cross_run",
        "generated_at_utc": utc_now(),
        "prereg": {
            "path": DEFAULT_PREREG.relative_to(REPOSITORY_ROOT).as_posix(),
            "locked_at_utc": prereg["locked_at_utc"],
            "sha256": sha256_file(DEFAULT_PREREG),
            "note": "判据与阶段定义在跑之前冻结；本轮未回填、未放宽。",
        },
        "source": {
            "shortlist_csv": file_provenance(DEFAULT_SHORTLIST),
            "shortlist_rows": len(shortlist),
            "shortlist_by_shortlist": {
                "15": sum(1 for row in shortlist if row["shortlist"] == "15"),
                "14": sum(1 for row in shortlist if row["shortlist"] == "14"),
            },
            "identity_csv": file_provenance(DEFAULT_IDENTITY_CSV),
            "roster_csv": file_provenance(ROSTER_CSV),
            "epsilon_v03_csv": file_provenance(EPS_V03_CSV),
            "epsilon_v11plus_csv": file_provenance(EPS_V11PLUS_CSV),
            "liquid_window_csv": file_provenance(LIQUID_WINDOW_CSV),
        },
        "pools": {
            "ours": {
                "id": prereg["pools"]["ours"]["id"],
                "path": prereg["pools"]["ours"]["path"],
                "n_declared": prereg["pools"]["ours"]["n_declared"],
                "n_measured_this_round": pool.get("n_measured_this_round"),
                "available": pool.get("available"),
                "unparsable_smiles": pool.get("unparsable_smiles"),
            },
            "kpi": prereg["pools"]["kpi"],
            "comparability": prereg["pools"]["comparability"],
        },
        "identity_resolution": {
            "rows": identity_meta["rows"],
            "resolved": identity_meta["resolved"],
            "unresolved": identity_meta["unresolved"],
            "by_route": {
                "smiles_rdkit": sum(
                    1 for record in records if record["resolved_route"] == "smiles_rdkit"
                ),
                "cas_pubchem": sum(
                    1 for record in records if record["resolved_route"] == "cas_pubchem"
                ),
            },
            "declared": prereg["identity_resolution"],
        },
        "stages": [dict(stage) for stage in prereg["stages"]],
        "funnel_ours": pool.get("stages", []),
        "funnel_kpi_declared": {
            "note": "KPI 自己声明的级联，转述不复算；本仓没有 QM9 池，不声称复现。",
            "recomputed_by_this_project": False,
        },
        "criterion_a_self_consistency": criterion_a,
        "criterion_b_identity": {
            "statement": prereg["pre_registered_criteria"]["B_identity"]["statement"],
            "resolved": identity_meta["resolved"],
            "required": 29,
            "passed": identity_meta["resolved"] == 29,
            "unresolved_rows": identity_meta["unresolved"],
        },
        "criterion_c_intersection": intersections,
        "element_whitelist": {
            "elements": list(whitelist),
            "n_elements": len(whitelist),
            "derived_from_rows": whitelist_rows,
            "status": "derived_not_declared",
            "caveat": prereg["stages"][3]["caveat"],
        },
        "property_crosscheck": crosscheck,
        "model_fitting": {
            "fitted_any_model": False,
            "r2_reported": False,
            "note": "本轮不产任何判决性 R2；这不是模型评测。",
        },
        "forbidden_compliance": {
            "batt_counts_presented_as_kpi_cascade": False,
            "guessed_structures_filled_in": False,
            "name_matching_used_as_identity": False,
            "s4_claimed_as_run": False,
            "kpi_printed_values_presented_as_our_measurements": False,
            "shortlist_redistributed": False,
            "random_row_leakage_used": False,
        },
        "usage_boundary": (
            "短清单仍为 cross_check_only / redistributable=false，永进不了 data/ 冻结表，"
            "也进不了任何交付包或模型特征。PubChem 侧结构为公有领域。"
        ),
    }


def _code(text: str) -> str:
    mark = chr(96)
    return mark + text + mark


def render_report(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    pool = summary["pools"]["ours"]
    identity = summary["identity_resolution"]
    criterion_b = summary["criterion_b_identity"]
    criterion_a = summary["criterion_a_self_consistency"]
    criterion_c = summary["criterion_c_intersection"]
    crosscheck = summary["property_crosscheck"]

    add("# KPI 15+14 短清单 vs 本仓漏斗：交叉试跑")
    add("")
    add(
        "本轮是 " + _code("probes/kpi_funnel_cross_run.py") + " 的一次跨池交叉试跑。"
        "预注册在跑之前冻结（" + summary["prereg"]["locked_at_utc"] + "），"
        "判据与阶段定义跑后未回填、未放宽。"
    )
    add("")
    add("## 1 一句话结论")
    add("")
    add(
        "- 身份层：29 行里解析出 " + str(identity["resolved"]) + " 行 InChIKey"
        "（SMILES 路线 " + str(identity["by_route"]["smiles_rdkit"]) + " 行，"
        "PubChem CAS 路线 " + str(identity["by_route"]["cas_pubchem"]) + " 行），"
        "判据 B " + ("达成" if criterion_b["passed"] else "未达成") + "。"
    )
    add("- 短清单与本仓 Batt-P30K 的交集：" + str(criterion_c["vs_batt_p30k"]["n"]) + " 个分子。")
    add(
        "- 短清单与本仓 314 键名册的交集：" + str(criterion_c["vs_roster_314"]["n"]) + " 个；"
        "与冻结 epsilon v0.3 表 " + str(criterion_c["vs_epsilon_v03"]["n"]) + " 个；"
        "与 v1.x 观测表 " + str(criterion_c["vs_epsilon_v11plus"]["n"]) + " 个。"
    )
    add(
        "- 判据 A（29 行自洽）：违反行数 " + str(criterion_a["rows_with_violations"])
        + "，允许 " + str(criterion_a["allowed_violations"]) + "，判 "
        + ("通过" if criterion_a["passed"] else "未通过") + "。"
    )
    add("")
    add("## 2 池与可比性")
    add("")
    add(
        "- 我方池：Batt-P30K，" + _code(pool["path"]) + "，声明 "
        + str(pool["n_declared"]) + " 个分子。"
    )
    add(
        "- 本轮实测读入：" + (
            str(pool["n_measured_this_round"]) if pool["available"] else "不可用（文件缺失）"
        )
        + " 个；SMILES 不可解析 " + str(pool["unparsable_smiles"]) + " 个。"
    )
    add("- KPI 池：QM9（133,885），本仓不存在，也未联网获取。")
    add(
        "- 可比性：两池不同（pool_different）。只允许比比例与规则，不允许比绝对计数，"
        "也不允许把比例差异单方面归因于漏斗。"
    )
    add("")
    add("## 3 判据 A：29 行自洽性")
    add("")
    add(
        "逐行核对 KPI 结构过滤（无 -OH / -COOH、Molwt < 600、重原子数 < 30）"
        "与三阈值（MP < 230 K、BP > 430 K、FP > 360 K）。"
    )
    add("")
    add("| 行 | CAS | SMILES | 违反项 |")
    add("| --- | --- | --- | --- |")
    for entry in criterion_a["detail"]:
        violations = "、".join(entry["violations"]) if entry["violations"] else "无"
        add(
            "| " + entry["row_key"] + " | " + (entry["cas"] or "—") + " | "
            + (entry["smiles"] or "—") + " | " + violations + " |"
        )
    add("")
    if criterion_a["passed"]:
        add("判据 A 通过：29 行全部满足结构过滤与三阈值，违反数 0。")
    else:
        add(
            "判据 A 未通过：违反行为 " + "、".join(criterion_a["violating_rows"])
            + "。按预注册，先修我方转录或规则读法，再谈交叉；不得把违反解释成 KPI 的错。"
        )
    add("")
    add("## 4 本仓漏斗 S0-S3（S4 登记为缺口）")
    add("")
    if not pool["available"]:
        add("- Batt-P30K 缺失，漏斗不可跑。原因：data/raw/* 被 .gitignore 忽略，干净克隆上没有该文件。")
    else:
        add("| 阶段 | 名称 | 存活 | 本级剔除 | 对池存活率 |")
        add("| --- | --- | --- | --- | --- |")
        for stage in summary["funnel_ours"]:
            if stage.get("survivors") is None:
                add("| " + stage["id"] + " | " + stage["name"] + " | 不跑 | 不跑 | 不跑 |")
            else:
                add(
                    "| " + stage["id"] + " | " + stage["name"] + " | " + str(stage["survivors"])
                    + " | " + str(stage["excluded_here"]) + " | "
                    + "{:.6f}".format(stage["survival_rate"]) + " |"
                )
        add("")
        for stage in summary["funnel_ours"]:
            reasons = stage.get("exclusion_reasons")
            if reasons:
                add(
                    "- " + stage["id"] + " 本级剔除原因：" + "，".join(
                        f"{name}={count}" for name, count in sorted(reasons.items())
                    )
                )
        add("- S4：本仓没有 MP/BP/FP 模型，Batt-P30K 也不带这三性质，登记为缺口，不跑、不猜、不插值。")
    add("")
    add("## 5 元素白名单（导出值，非原文声明）")
    add("")
    add(
        "- 白名单 = 短清单解析出的元素并集：" + " ".join(summary["element_whitelist"]["elements"])
        + "（" + str(summary["element_whitelist"]["n_elements"]) + " 种，来自 "
        + str(summary["element_whitelist"]["derived_from_rows"]) + " 行）。"
    )
    add(
        "- 状态：" + _code(summary["element_whitelist"]["status"])
        + "。" + summary["element_whitelist"]["caveat"]
    )
    add(
        "- 因此 S3 的存活数是我方规则下的数字，不是 KPI 规则的复现：本仓导出的白名单"
        "比 KPI 声明的 11 元素白名单更严（29 行末端只出现 3 种元素），S3 存活数只能当下界读。"
    )
    add("")
    add("## 6 交集")
    add("")
    for label, key in (
        ("Batt-P30K", "vs_batt_p30k"),
        ("314 键名册", "vs_roster_314"),
        ("冻结 epsilon v0.3", "vs_epsilon_v03"),
        ("v1.x 观测表 v11plus", "vs_epsilon_v11plus"),
    ):
        block = criterion_c[key]
        add("- " + label + "：" + str(block["n"]) + " 个")
        for member in block["members"]:
            detail = "  - " + member["row_key"] + " （CAS " + (member["cas"] or "—") + "，"
            detail += member["smiles"] if member["smiles"] else member["inchikey"]
            detail += "）"
            add(detail)
            labels = member.get("batt_p30k_labels")
            if labels:
                add(
                    "    - Batt-P30K 标签：dipole_norm=" + str(labels.get("dipole_norm"))
                    + "，homo=" + str(labels.get("homo")) + "，lumo=" + str(labels.get("lumo"))
                    + "，gap=" + str(labels.get("gap")) + "，ip=" + str(labels.get("ip"))
                    + "，ea=" + str(labels.get("ea"))
                )
    add("")
    add("预注册写明：交集为 0 不算失败，但必须逐条给出分歧来源。本轮分歧来源见第 7 节。")
    add("")
    add("## 7 分歧来源（逐条）")
    add("")
    add("- 池不同：我方 Batt-P30K 是电池分子池，KPI 池是 QM9；同一结构在两池中存在与否本就不同。")
    add("- 规则不同：S2 危险官能团是本仓独有的附加闸门，KPI 侧没有这一级。")
    add("- 身份未解析：见判据 B 的未解析清单；未解析行不进交集。")
    add("- 转录错：判据 A 已机械核对；任何违反都会列出具体行。")
    add("")
    add("## 8 属性交叉核对（KPI 印刷值 vs 本仓独立取得的 PubChem 汇编值）")
    add("")
    if not crosscheck["available"]:
        add("- 本仓名册侧属性表缺失，本轮不可比。")
    elif crosscheck["n_compared"] == 0:
        add("- 可比对行数为 0：短清单解析出的身份没有一个落在本仓名册覆盖范围内，故没有独立值可比。")
        add("- 这是照实结果，不做任何补位。")
    else:
        add(
            "- 比对 " + str(crosscheck["n_compared"]) + " 组，|Δ| 中位数 "
            + str(crosscheck["median_abs_delta_k"]) + " K，最大 "
            + str(crosscheck["max_abs_delta_k"]) + " K。"
        )
        add(
            "- 口径提醒：KPI 侧 MP/BP/FP 是论文模型的预测值，本仓侧是 PubChem 汇编的实验值；"
            "这不是两个实验源之间的比对。"
        )
        add("")
        add("| 行 | 性质 | KPI 印刷 (K) | 本仓独立值 (K) | Δ (K) | 沉积者 |")
        add("| --- | --- | --- | --- | --- | --- |")
        for item in crosscheck["comparisons"]:
            add(
                "| " + item["row_key"] + " | " + item["property"] + " | "
                + str(item["printed_k"]) + " | " + str(item["deposited_k"]) + " | "
                + str(item["delta_k"]) + " | " + item["depositor"] + " |"
            )
    add("")
    add("## 9 使用边界")
    add("")
    add("- " + summary["usage_boundary"])
    add(
        "- 本轮不拟合任何模型、不产任何 R2；" + _code("forbidden_compliance")
        + " 逐条登记在 summary 里。"
    )
    add("- S4 是缺口，不是结论：任何把 Batt-P30K 各级存活数当作 KPI 级联复现的说法都是错的。")
    add("- 短清单是论文模型的预测值，不是本仓实测值。")
    add("")
    return chr(10).join(lines) + chr(10)


def _stable_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(summary, ensure_ascii=False))
    clone.pop("generated_at_utc", None)
    clone.pop("run_telemetry", None)
    return clone


def run(*, online: bool, refresh: bool) -> tuple[str, str, dict[str, Any], str]:
    global NETWORK_CALLS, CACHE_HITS
    NETWORK_CALLS = 0
    CACHE_HITS = 0

    if not DEFAULT_PREREG.is_file():
        raise SystemExit(f"预注册缺失：{DEFAULT_PREREG}")
    prereg = json.loads(DEFAULT_PREREG.read_text(encoding="utf-8"))
    shortlist = read_csv_rows(DEFAULT_SHORTLIST)
    if len(shortlist) != prereg["identity_resolution"]["shortlist_rows"]:
        raise SystemExit(f"短清单行数与预注册不符：{len(shortlist)}")

    records, identity_meta = resolve_identities(shortlist, online=online, refresh=refresh)
    if identity_meta["drift_vs_committed_table"] and not refresh:
        for item in identity_meta["drift_vs_committed_table"]:
            print("FAIL 身份漂移 " + item)
        print("已提交身份表与本轮重解不一致；先人工确认，再决定是否 --refresh-identity")
        raise SystemExit(2)

    elements: set[str] = set()
    contributing = 0
    for record in records:
        if record["elements"]:
            elements.update(record["elements"].split())
            contributing += 1

    criterion_a = self_consistency(records, shortlist)
    pool = run_pool_funnel(elements)
    intersections = intersect(
        records,
        pool=pool,
        roster=_inchikey_column(ROSTER_CSV, "inchikey"),
        eps_v03=_inchikey_column(EPS_V03_CSV, "inchikey"),
        eps_v11plus=_inchikey_column(EPS_V11PLUS_CSV, "inchikey"),
    )
    crosscheck = property_crosscheck(records, shortlist)

    summary = build_summary(
        prereg=prereg,
        shortlist=shortlist,
        records=records,
        identity_meta=identity_meta,
        criterion_a=criterion_a,
        pool=pool,
        intersections=intersections,
        crosscheck=crosscheck,
        whitelist=sorted(elements),
        whitelist_rows=contributing,
    )
    summary["run_telemetry"] = {
        "run_mode": "resolve_online" if online else "offline",
        "network_calls": NETWORK_CALLS,
        "cache_hits": CACHE_HITS,
    }
    identity_text = identity_csv_text(records)
    identity_bytes = identity_text.encode("utf-8")
    summary["source"]["identity_csv"] = {
        "path": DEFAULT_IDENTITY_CSV.relative_to(REPOSITORY_ROOT).as_posix(),
        "available": True,
        "bytes": len(identity_bytes),
        "sha256": hashlib.sha256(identity_bytes).hexdigest(),
        "note": "写盘前由本轮重解结果算出，故与首次运行时文件是否存在无关。",
    }
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2) + chr(10)
    return identity_text, summary_text, summary, render_report(summary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KPI shortlist vs our funnel cross-run.")
    parser.add_argument("--resolve-online", action="store_true", help="允许联网解析 CAS 行")
    parser.add_argument("--refresh-identity", action="store_true", help="忽略缓存与已提交表，强制重解")
    parser.add_argument("--check", action="store_true", help="离线重跑并与磁盘产物比对")
    parser.add_argument("--identity-csv", default=str(DEFAULT_IDENTITY_CSV))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    online = args.resolve_online and not args.check
    identity_text, summary_text, summary, report_text = run(
        online=online, refresh=args.refresh_identity and online
    )

    identity_path = Path(args.identity_csv)
    summary_path = Path(args.summary)
    report_path = Path(args.report)
    criterion_a = summary["criterion_a_self_consistency"]
    criterion_b = summary["criterion_b_identity"]
    criterion_c = summary["criterion_c_intersection"]

    if args.check:
        problems: list[str] = []
        if not identity_path.is_file() or identity_path.read_text(encoding="utf-8") != identity_text:
            problems.append(f"身份表与离线重解不一致：{identity_path}")
        if not summary_path.is_file():
            problems.append(f"summary 缺失：{summary_path}")
        elif _stable_view(json.loads(summary_path.read_text(encoding="utf-8"))) != _stable_view(summary):
            problems.append("summary 与离线重解不一致")
        if not report_path.is_file():
            problems.append(f"report 缺失：{report_path}")
        elif report_path.read_text(encoding="utf-8") != report_text:
            problems.append("report 不是 render_report(summary) 的输出")
        for problem in problems:
            print("FAIL " + problem)
        if problems:
            return 1
        print(
            "OK 29 行身份 {}/29，判据A {}，判据B {}，Batt-P30K 交集 {}".format(
                summary["identity_resolution"]["resolved"],
                "通过" if criterion_a["passed"] else "未通过",
                "达成" if criterion_b["passed"] else "未达成",
                criterion_c["vs_batt_p30k"]["n"],
            )
        )
        return 0

    write_text(identity_path, identity_text)
    write_text(summary_path, summary_text)
    write_text(report_path, report_text)
    print("wrote {} 行身份表 -> {}".format(summary["identity_resolution"]["rows"], identity_path))
    print(
        "判据A 违反行数={}，判据B 解析={}/29".format(
            criterion_a["rows_with_violations"], summary["identity_resolution"]["resolved"]
        )
    )
    print(
        "Batt-P30K 交集={}，名册交集={}，v0.3 交集={}，v11plus 交集={}".format(
            criterion_c["vs_batt_p30k"]["n"],
            criterion_c["vs_roster_314"]["n"],
            criterion_c["vs_epsilon_v03"]["n"],
            criterion_c["vs_epsilon_v11plus"]["n"],
        )
    )
    if not criterion_b["passed"]:
        print("FAIL 未解析行：" + "、".join(criterion_b["unresolved_rows"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
