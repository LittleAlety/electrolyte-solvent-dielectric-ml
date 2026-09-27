r"""W19-1 步骤 1 剩余开口：Batt-P30K 直接命中核查（逐字 / RDKit 规范化两版）。

本件是**复核性**工作（只读已冻结资产）：不拟合模型、不产 R2/MAE、不写任何池、
不动任何冻结件、不引入任何 Reaxys 数值。它回答三个问题：

  1. 冻结 eps 名册（data/dielectric_v03.csv）里有多少化合物**直接**落在
     Batt-P30K 里？逐字 SMILES 一版、RDKit 规范化后一版。
  2. 规范化命中集与 reports/decisions_log.md 第 28.17 节的 n = 111 配对锚点是什么
     包含关系？（两者口径不同：一个是 PubChemQC 中介，一个是 Batt 直连；
     差异必须解释，不许硬凑。）
  3. 计划书写下的「逐字 SMILES 匹配 76 / 239」能否复现？不能就如实报差异。

读取纪律（硬约束）：h5 只按 group 逐个读 smiles dataset；coord / dipole /
quadrupole / elems 等大数组一个字节都不碰，绝不把整表读进内存。

只读输入：
  data/raw/batt/Batt-P30K.h5                          (sha256 必须等于 587f1490...)
  data/dielectric_v03.csv                             (冻结名册，绝不改写)
  data/processed/orbital_second_source_layer.csv      (第 28.17 节 n = 111 锚点来源)
  data/processed/four_core_key_registry.csv           (交叉核对用，只读)

用法（PowerShell，仓库根）：
    .\.venv\Scripts\python.exe probes/w19_batt_direct_hit.py
    .\.venv\Scripts\python.exe probes/w19_batt_direct_hit.py --raw
    .\.venv\Scripts\python.exe probes/w19_batt_direct_hit.py --normalized
    .\.venv\Scripts\python.exe probes/w19_batt_direct_hit.py --limit 400
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
from rdkit import Chem, RDLogger
from rdkit.Chem.MolStandardize import rdMolStandardize

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BATT_H5 = REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5"
DEFAULT_ROSTER = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_ORBITAL_LAYER = REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv"
DEFAULT_REGISTRY = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "w19_batt_direct_hit_summary.json"

EXPECTED_BATT_SHA256 = "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d"
ANCHOR_ROLE = "paired_anchor"

# 命中阶梯在脚本里先声明、后测数；RUNGS 的次序就是「从严到宽」的判定次序。
VERBATIM_RUNG = "verbatim_raw_smiles"
RUNGS: tuple[str, ...] = (
    VERBATIM_RUNG,
    "rdkit_canonical_smiles_isomeric_true",
    "inchikey_full_27_bare_rdkit",
    "inchikey_skeleton_14_bare_rdkit",
    "inchikey_full_27_desalted_uncharged",
    "inchikey_skeleton_14_desalted_uncharged",
)
NORMALIZED_RUNGS: tuple[str, ...] = RUNGS[1:]

# 主读数：与第 28.17 节的 Batt 键**同一配方**（裸 RDKit MolFromSmiles -> MolToInchiKey），
# 因此本数字与既有 registry / 锚点口径可直接对齐。
PRIMARY_RUNG = "inchikey_full_27_bare_rdkit"
# 最宽读数：去盐 + 去电荷后取 InChIKey 骨架前 14 位。
MAX_RUNG = "inchikey_skeleton_14_desalted_uncharged"

NORMALIZATION_RECIPE: dict[str, Any] = {
    VERBATIM_RUNG: "两侧 SMILES 字符串逐字相等（不去空白、不做任何解析）。",
    "rdkit_canonical_smiles_isomeric_true": (
        "Chem.MolFromSmiles -> Chem.MolToSmiles(mol)（默认 isomericSmiles=True，保留立体）"
    ),
    "inchikey_full_27_bare_rdkit": (
        "Chem.MolFromSmiles -> Chem.MolToInchiKey(mol)，取全 27 位；不去盐、不去电荷。"
        "该配方与仓内第 28.17 节 Batt 键的生成配方逐字相同。"
    ),
    "inchikey_skeleton_14_bare_rdkit": (
        "同上，但只取 InChIKey 前 14 位（骨架块，忽略质子化/立体层）。"
    ),
    "inchikey_full_27_desalted_uncharged": (
        "Chem.MolFromSmiles -> rdMolStandardize.Cleanup -> FragmentParent（去盐，保留最大片段）"
        " -> Uncharger().uncharge（去电荷） -> Chem.MolToInchiKey，取全 27 位。"
    ),
    "inchikey_skeleton_14_desalted_uncharged": "同上，但只取 InChIKey 前 14 位。",
    "isomeric_smiles": "规范 SMILES 阶梯一律 isomericSmiles=True（保留立体）；未使用 False 变体。",
    "inchikey_length_decision": (
        "主读数取全 27 位（与 registry 键逐字可比）；前 14 位只作更宽的敏感性读数，非主读数。"
    ),
}


class BattSchemaError(RuntimeError):
    """Raised when the Batt-P30K HDF5 schema does not match the audited shape."""


@dataclass(frozen=True, slots=True)
class Identity:
    """One molecule's layered structural identity."""

    raw_smiles: str
    parsed: bool | None
    canonical_isomeric: str | None
    inchikey_full: str | None
    standardized_full: str | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def decode_smiles(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _group_sort_key(key: str) -> tuple[int, str]:
    if key.startswith("CompMol") and key.removeprefix("CompMol").isdigit():
        return int(key.removeprefix("CompMol")), key
    return 2**31 - 1, key


def iter_batt_smiles(
    h5_path: Path,
    *,
    limit: int | None = None,
) -> tuple[list[str], int, int, list[str]]:
    """Stream only the smiles dataset of every group; never touch the big cubes."""

    smiles_values: list[str] = []
    groups_seen = 0
    groups_without_smiles = 0
    skipped_keys: list[str] = []
    with h5py.File(h5_path, "r") as handle:
        keys = sorted(handle.keys(), key=_group_sort_key)
        for key in keys:
            if limit is not None and groups_seen >= limit:
                break
            group = handle[key]
            groups_seen += 1
            if not isinstance(group, h5py.Group) or "smiles" not in group:
                groups_without_smiles += 1
                skipped_keys.append(key)
                continue
            dataset = group["smiles"]
            if dataset.shape != (1,):
                raise BattSchemaError(f"{key}/smiles has shape {dataset.shape}, expected (1,)")
            smiles_values.append(decode_smiles(dataset[0]))
    return smiles_values, groups_seen, groups_without_smiles, skipped_keys


_UNCHARGER = rdMolStandardize.Uncharger()


def _standardize(mol: Chem.Mol) -> Chem.Mol | None:
    try:
        cleaned = rdMolStandardize.Cleanup(mol)
        parent = rdMolStandardize.FragmentParent(cleaned)
        if parent is None or parent.GetNumAtoms() == 0:
            return None
        return _UNCHARGER.uncharge(parent)
    except Exception:  # noqa: BLE001 - RDKit raises bare exceptions on odd valence
        return None


def identity_of(raw_smiles: str) -> Identity:
    mol = Chem.MolFromSmiles(raw_smiles)
    if mol is None:
        return Identity(raw_smiles, False, None, None, None)
    canonical = Chem.MolToSmiles(mol)
    inchikey = Chem.MolToInchiKey(mol)
    standardized = _standardize(mol)
    standardized_key = Chem.MolToInchiKey(standardized) if standardized is not None else ""
    return Identity(
        raw_smiles=raw_smiles,
        parsed=True,
        canonical_isomeric=canonical or None,
        inchikey_full=inchikey or None,
        standardized_full=standardized_key or None,
    )


def identity_map(values: Sequence[str], *, active: Sequence[str]) -> list[Identity]:
    if tuple(active) == (VERBATIM_RUNG,):
        return [Identity(value, None, None, None, None) for value in values]
    cache: dict[str, Identity] = {}
    out: list[Identity] = []
    for value in values:
        item = cache.get(value)
        if item is None:
            item = identity_of(value)
            cache[value] = item
        out.append(item)
    return out


def rung_value(item: Identity, rung: str) -> str | None:
    if rung == VERBATIM_RUNG:
        return item.raw_smiles or None
    if rung == "rdkit_canonical_smiles_isomeric_true":
        return item.canonical_isomeric
    if rung == "inchikey_full_27_bare_rdkit":
        return item.inchikey_full
    if rung == "inchikey_skeleton_14_bare_rdkit":
        return item.inchikey_full[:14] if item.inchikey_full else None
    if rung == "inchikey_full_27_desalted_uncharged":
        return item.standardized_full
    if rung == "inchikey_skeleton_14_desalted_uncharged":
        return item.standardized_full[:14] if item.standardized_full else None
    raise KeyError(f"unknown rung: {rung}")


def build_rung_sets(
    items: Iterable[Identity], active: Sequence[str]
) -> dict[str, set[str]]:
    sets: dict[str, set[str]] = {name: set() for name in active}
    for item in items:
        for name in active:
            value = rung_value(item, name)
            if value:
                sets[name].add(value)
    return sets


def first_rung_hit(item: Identity, other: dict[str, set[str]], active: Sequence[str]) -> str | None:
    for name in active:
        value = rung_value(item, name)
        if value and value in other[name]:
            return name
    return None


def read_anchor_keys(path: Path) -> tuple[list[str], int]:
    rows = read_csv_rows(path)
    anchors = sorted(
        {
            row["inchikey"]
            for row in rows
            if row.get("role") == ANCHOR_ROLE and (row.get("batt_homo_eV") or "").strip()
        }
    )
    return anchors, len(rows)


def read_registry_orbit_keys(path: Path) -> set[str]:
    return {
        row["inchikey"]
        for row in read_csv_rows(path)
        if (row.get("has_orbitals") or "").strip().lower() == "true"
    }


def evaluate_roster(
    rows: Sequence[dict[str, str]],
    batt_sets: dict[str, set[str]],
    active: Sequence[str],
) -> dict[str, Any]:
    identities = identity_map([(row.get("smiles") or "") for row in rows], active=active)
    rung_hits: dict[str, int] = {name: 0 for name in active}
    row_rung: list[str | None] = []
    for item in identities:
        reached = first_rung_hit(item, batt_sets, active)
        row_rung.append(reached)
        if reached is not None:
            rung_hits[reached] += 1

    cumulative: dict[str, int] = {}
    running = 0
    for name in active:
        running += rung_hits[name]
        cumulative[name] = running

    lost_by_verbatim: list[dict[str, Any]] = []
    misses_still: list[dict[str, Any]] = []
    for row, item, reached in zip(rows, identities, row_rung, strict=True):
        record: dict[str, Any] = {
            "inchikey": row.get("inchikey", ""),
            "name": row.get("name", ""),
            "roster_smiles": item.raw_smiles,
            "parse_ok": item.parsed,
        }
        if reached == VERBATIM_RUNG:
            continue
        if reached is None:
            if item.parsed is False:
                reason = "unparseable_roster_smiles"
            elif item.inchikey_full is None and item.parsed is True:
                reason = "inchikey_derivation_failed"
            else:
                reason = "no_rung_matched"
            misses_still.append({**record, "reason": reason})
            continue
        lost_by_verbatim.append({**record, "first_rung": reached})

    return {
        "roster_rows": len(rows),
        "roster_unique_inchikeys": len({row.get("inchikey", "") for row in rows}),
        "roster_unparseable": (
            sum(1 for item in identities if item.parsed is False)
            if VERBATIM_RUNG not in active or len(active) > 1
            else None
        ),
        "rung_hits": rung_hits,
        "rung_cumulative_hits": cumulative,
        "rung_ratios": {
            name: (cumulative[name] / len(rows) if rows else 0.0) for name in active
        },
        "verbatim_hit_inchikeys": sorted(
            {
                identities[index].inchikey_full
                for index, reached in enumerate(row_rung)
                if reached == VERBATIM_RUNG and identities[index].inchikey_full
            }
        ),
        "any_hit_inchikeys": sorted(
            {
                identities[index].inchikey_full
                for index, reached in enumerate(row_rung)
                if reached is not None and identities[index].inchikey_full
            }
        ),
        "lost_by_verbatim": lost_by_verbatim,
        "misses_still": misses_still,
        "roster_rows_missing_verbatim": len(lost_by_verbatim) + len(misses_still),
    }


def render_report(summary: dict[str, Any]) -> str:
    ladder = summary["ladder"]["rung_cumulative_hits"]
    containment = summary["anchor_containment"]
    crosscheck = summary["registry_crosscheck"]
    rows = summary["roster_rows"]
    verbatim = summary["verbatim_hits"]
    normalized = summary["normalized_hits"]
    inclusive = summary["inclusive_hits_max_rung"]
    unique_keys = summary["roster_unique_inchikeys"]
    a_def = containment["anchor_definition"]
    a_n = containment["anchors"]
    a_batt = containment["anchors_in_batt_primary_key_set"]
    a_batt_sub = containment["anchors_subset_of_batt_primary_key_set"]
    a_roster = containment["anchors_in_roster"]
    a_verb = containment["anchors_in_verbatim_hit_keys"]
    a_skeleton = containment["anchors_skeleton_in_max_rung_key_set"]
    a_hits = containment["anchors_in_roster_hit_keys"]
    a_sub = containment["anchors_subset_of_roster_hit_keys"]
    hit_keys = containment["roster_hit_keys"]
    hit_not_anchor = containment["roster_hit_keys_not_in_anchors"]
    anchor_not_roster = containment["anchors_not_in_roster"]
    universe = containment["universe_note"]
    reg_n = crosscheck["registry_orbit_keys"]
    reg_found = crosscheck["registry_orbit_keys_found_in_batt"]
    reg_sub = crosscheck["batt_keys_subset_of_registry_orbit"]
    lines = [
        "# W19-1 步骤 1 剩余开口：Batt-P30K 直接命中核查（D2）",
        "",
        (
            "只读复核：不拟合模型（models_fitted = 0）、不产 R2/MAE、不动任何冻结件、"
            "不引用 Reaxys 数值。"
        ),
        "",
        "## 1. 直接命中",
        "",
        "| 读数 | 命中 | 分母 | 比率 |",
        "| --- | --- | --- | --- |",
        f"| 逐字 SMILES 相等 | {verbatim} | {rows} | {verbatim / rows:.6f} |",
        f"| RDKit 规范化（主读数 = InChIKey 全 27 位） | {normalized} | {rows} | {normalized / rows:.6f} |",
        f"| 最宽阶梯（去盐去电荷后取骨架前 14 位） | {inclusive} | {rows} | {inclusive / rows:.6f} |",
        "",
        (
            "主读数用的是与第 28.17 节 Batt 键**同一配方**（裸 RDKit MolFromSmiles -> "
            "MolToInchiKey，取全 27 位），因此与既有 registry / 锚点可直接对齐；"
            "逐级配方写在 summary 的 normalization_recipe。"
        ),
        "",
        "## 2. 阶梯（逐级累计命中）",
        "",
        "| 阶梯 | 累计命中 |",
        "| --- | --- |",
    ]
    for name in summary["ladder"]["rung_order"]:
        lines.append(f"| {name} | {ladder[name]} |")
    lines.extend(
        [
            "",
            "## 3. 分母发现（计划书写 239 / 76，磁盘实测 246 / 77）",
            "",
            (
                f"磁盘 data/dielectric_v03.csv 实测 {rows} 行、唯一 InChIKey {unique_keys} 个；"
                f"逐字命中 {verbatim}、规范化命中 {normalized}。"
                "计划书写的 239 / 76 两个数都对不上——这是**分母口径分歧**，不是数据变化"
                "（该文件是冻结件，本次未改一个字节）。"
            ),
            "",
            "## 4. 与第 28.17 节 n = 111 配对锚点的包含关系",
            "",
            f"- 锚点定义：{a_def}；总数 {a_n}。",
            (
                f"- 锚点落在 Batt 键全集里：{a_batt} / {a_n}（子集判定 {a_batt_sub}）"
                " → 两条链的身份配方一致，这一点成立。"
            ),
            (
                f"- 锚点落在冻结 eps 名册里：{a_roster} / {a_n}；"
                f"落在逐字命中键集里：{a_verb}；落在规范化命中键集里：{a_hits}"
                f"（骨架口径 {a_skeleton}）。"
            ),
            f"- **111 是否为本轮命中集的子集：{a_sub}**。",
            "",
            universe,
            "",
            (
                f"补充：本轮名册命中集共 {hit_keys} 个键，其中 {hit_not_anchor} 个不在锚点集内；"
                f"111 锚点里有 {anchor_not_roster} 个根本不在这份 eps 名册里。"
            ),
            "",
            "## 5. 与 four_core_key_registry 的配方交叉核对",
            "",
            f"- registry 的 has_orbitals 键数：{reg_n}；其中能在 Batt 里找到：{reg_found}。",
            f"- 本轮 Batt 键集是否全在 registry 轨道键里：{reg_sub}。",
            "",
            "## 6. 边界",
            "",
        ]
    )
    for item in summary["boundaries"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5", type=Path, default=DEFAULT_BATT_H5)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--alt-roster", type=Path, default=None)
    parser.add_argument("--orbital-layer", type=Path, default=DEFAULT_ORBITAL_LAYER)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--report",
        type=Path,
        default=REPOSITORY_ROOT / "reports" / "w19_batt_direct_hit.md",
    )
    parser.add_argument("--raw", action="store_true", help="run only the verbatim pass")
    parser.add_argument("--normalized", action="store_true", help="run only the normalized pass")
    parser.add_argument("--limit", type=int, default=None, help="smoke test: scan N groups only")
    args = parser.parse_args()

    if args.raw and args.normalized:
        parser.error("--raw and --normalized are mutually exclusive (default runs both)")
    if args.raw:
        active: tuple[str, ...] = (VERBATIM_RUNG,)
    elif args.normalized:
        active = NORMALIZED_RUNGS
    else:
        active = RUNGS

    RDLogger.DisableLog("rdApp.*")

    h5_sha = sha256_file(args.h5)
    batt_smiles, groups_seen, groups_without_smiles, skipped = iter_batt_smiles(
        args.h5, limit=args.limit
    )
    batt_identities = identity_map(sorted(set(batt_smiles)), active=active)
    batt_sets = build_rung_sets(batt_identities, active)

    roster_rows = read_csv_rows(args.roster)
    evaluation = evaluate_roster(roster_rows, batt_sets, active)

    verbatim_hits = evaluation["rung_cumulative_hits"].get(VERBATIM_RUNG)
    normalized_hits = evaluation["rung_cumulative_hits"].get(PRIMARY_RUNG)
    inclusive_hits = evaluation["rung_cumulative_hits"].get(MAX_RUNG)
    roster_row_count = evaluation["roster_rows"]
    ratio = (normalized_hits / roster_row_count) if (normalized_hits and roster_row_count) else None

    anchors, anchor_rows = read_anchor_keys(args.orbital_layer)
    registry_orbit_keys = read_registry_orbit_keys(args.registry)
    roster_keys = {row.get("inchikey", "") for row in roster_rows}
    anchor_set = set(anchors)
    batt_key_set = batt_sets.get(PRIMARY_RUNG, set())
    roster_hit_keys = set(evaluation.get("any_hit_inchikeys", []))
    verbatim_hit_keys = set(evaluation.get("verbatim_hit_inchikeys", []))

    containment = {
        "anchor_source": str(args.orbital_layer),
        "anchor_definition": (
            "orbital_second_source_layer.csv 中 role == paired_anchor 且 batt_homo_eV 非空的行"
        ),
        "anchor_layer_rows": anchor_rows,
        "anchors": len(anchors),
        "anchors_in_roster": len(anchor_set & roster_keys),
        "anchors_in_batt_primary_key_set": len(anchor_set & batt_key_set),
        "anchors_subset_of_batt_primary_key_set": anchor_set <= batt_key_set,
        "anchors_skeleton_in_max_rung_key_set": len(
            {key[:14] for key in anchor_set} & batt_sets.get(MAX_RUNG, set())
        ),
        "anchors_in_verbatim_hit_keys": len(anchor_set & verbatim_hit_keys),
        "anchors_in_roster_hit_keys": len(anchor_set & roster_hit_keys),
        "anchors_subset_of_roster_hit_keys": anchor_set <= roster_hit_keys,
        "roster_hit_keys": len(roster_hit_keys),
        "roster_hit_keys_not_in_anchors": len(roster_hit_keys - anchor_set),
        "anchors_not_in_roster": len(anchor_set - roster_keys),
        "universe_note": (
            "两个集合的宇宙不同，不能直接说谁包含谁：111 锚点的分母是 PubChemQC 抓取窗口内、"
            "恰好也落在 four_core_key_registry 的 has_orbitals 键上的分子"
            "（全 Batt 池 29,519 键 + 名册外分子），不限于 eps 名册；"
            "本轮命中集的分母是冻结 eps 名册的 246 行。"
            "真正有意义的核对是三条：锚点是否落在 Batt 键全集里（配方一致性检验）、"
            "锚点有多少落在 eps 名册里、以及名册命中集与锚点集的交并。"
        ),
    }

    registry_crosscheck = {
        "registry_source": str(args.registry),
        "registry_orbit_keys": len(registry_orbit_keys),
        "batt_keys": len(batt_key_set),
        "registry_orbit_keys_found_in_batt": len(registry_orbit_keys & batt_key_set),
        "batt_keys_found_in_registry_orbit": len(batt_key_set & registry_orbit_keys),
        "batt_keys_subset_of_registry_orbit": batt_key_set <= registry_orbit_keys,
    }

    alternate: dict[str, Any] | None = None
    if args.alt_roster is not None:
        alt_rows = read_csv_rows(args.alt_roster)
        alt_eval = evaluate_roster(alt_rows, batt_sets, active)
        alternate = {
            "path": str(args.alt_roster),
            "rows": alt_eval["roster_rows"],
            "unique_inchikeys": alt_eval["roster_unique_inchikeys"],
            "rung_hits": alt_eval["rung_hits"],
            "rung_cumulative_hits": alt_eval["rung_cumulative_hits"],
        }

    summary: dict[str, Any] = {
        "probe": "w19_batt_direct_hit",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "read_only": True,
        "models_fitted": 0,
        "reaxys_values_used": False,
        "writes_any_pool": False,
        "batt_h5": {
            "path": str(args.h5),
            "sha256": h5_sha,
            "sha256_matches_registered": h5_sha == EXPECTED_BATT_SHA256,
            "expected_sha256": EXPECTED_BATT_SHA256,
            "groups_scanned": groups_seen,
            "groups_without_smiles": groups_without_smiles,
            "groups_without_smiles_keys": skipped[:20],
            "unique_raw_smiles": len(set(batt_smiles)),
            "partial_scan": args.limit is not None,
            "scan_limit": args.limit,
        },
        "roster": {
            "path": str(args.roster),
            "rows": evaluation["roster_rows"],
            "unique_inchikeys": evaluation["roster_unique_inchikeys"],
            "unparseable_smiles": evaluation["roster_unparseable"],
        },
        "roster_rows": evaluation["roster_rows"],
        "roster_unique_inchikeys": evaluation["roster_unique_inchikeys"],
        "batt_molecules": len(batt_smiles),
        "batt_parsed_molecules": (
            sum(1 for item in batt_identities if item.parsed is True)
            if len(active) > 1
            else None
        ),
        "batt_invalid_smiles": (
            sum(1 for item in batt_identities if item.parsed is False)
            if len(active) > 1
            else None
        ),
        "active_rungs": list(active),
        "verbatim_hits": verbatim_hits,
        "normalized_hits": normalized_hits,
        "hit_ratio": ratio,
        "verbatim_ratio": (
            (verbatim_hits / roster_row_count) if (verbatim_hits and roster_row_count) else None
        ),
        "inclusive_hits_max_rung": inclusive_hits,
        "primary_rung": PRIMARY_RUNG,
        "max_rung": MAX_RUNG,
        "normalization_recipe": NORMALIZATION_RECIPE,
        "ladder": {
            "rung_order": list(active),
            "rung_hits": evaluation["rung_hits"],
            "rung_cumulative_hits": evaluation["rung_cumulative_hits"],
            "rung_ratios": evaluation["rung_ratios"],
        },
        "lost_by_verbatim": evaluation["lost_by_verbatim"],
        "misses_still": evaluation["misses_still"],
        "anchor_containment": containment,
        "registry_crosscheck": registry_crosscheck,
        "alternate_roster": alternate,
        "shot_accounting_judgement": {
            "recommendation": (
                "建议判定为**复核性工作、不占用新 shot 编号**（复核不占号，见计划 W19-9）。"
            ),
            "basis": [
                "本件零拟合：models_fitted = 0，无任何 R2/MAE，不产杠杆、不碰主记分牌。",
                (
                    "它只读三件已冻结资产（Batt-P30K h5、dielectric_v03.csv、"
                    "orbital_second_source_layer.csv），属既有资产的身份核对，不是新算法/新表示。"
                ),
                (
                    "该脚的标定部分（n = 111）已被登记为已用资源；本件只是补登该脚从未登记的"
                    "「直接命中数」字段。"
                ),
            ],
            "counter_consideration": (
                "若要按「新信息产出」计号，可主张本件首次给出规范化命中下界、并修正了名册行数"
                "口径（计划书写 239，磁盘实测 246），那么应取 22 号之后的编号；"
                "该判定应由作者在预注册层拍板，本件不代为决定。"
            ),
            "author_decision_required": True,
            "does_not_self_assign_shot_number": True,
        },
        "boundaries": [
            (
                "只统计「名册直接落在 Batt-P30K 里」的键数；命中不等于拿到 Batt 级 HOMO/LUMO 估计，"
                "更不等于过第 28.17 节的 cross-level 标定门。"
            ),
            (
                "计划书写名册 239 行；磁盘上 data/dielectric_v03.csv 实测 246 行。"
                "本件按磁盘实测口径报数，并把差异登记在案，不静默改用 239。"
            ),
            "前 14 位骨架读数只作敏感性上界：它会抹掉质子化/立体差异，不得当主读数引用。",
            "本件不引用任何 Reaxys 数值，无受限值进入任何交付层。",
        ],
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with open(args.summary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_report(summary))
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "roster_rows",
                    "batt_molecules",
                    "verbatim_hits",
                    "normalized_hits",
                    "hit_ratio",
                    "inclusive_hits_max_rung",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
