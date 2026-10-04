# -*- coding: utf-8 -*-
"""W43 共享计算层：大样本同层级扩展层的只读装载与层级残差工具。

W43 四条 lane 共用一份装载：扩展层 data/processed/themol_orbital_layer_expanded.csv 有 5117 行
GFN2-xTB//B3LYP-D3(BJ)/DZVP 气相单点（DFT 几何），把 241 名册上只有 73 行的 xTB–Batt 对扩到 4668 行。
这里只加扩展层装载与描述符联结；统计与重抽一律复用 w42_common。

  * load_expanded_layer    —— 扩展层的 {InChIKey: {列名: 值}}（只读，按行去重）。
  * expanded_join_roster   —— 把名册描述符按 InChIKey 接到扩展层行上。
  * load_transfer_pairs    —— W42 落下的六对秩相关表。
  * iter_summary_json      —— 治理守卫用的全仓 summary 迭代器。

只读；不写标签池或特征列。
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA = REPOSITORY_ROOT / "data" / "processed"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"

EXPANDED_CSV = DATA / "themol_orbital_layer_expanded.csv"
TRANSFER_PAIRS_CSV = ARTIFACTS / "w42_transfer_pairs.csv"
ROSTER_CSV = DATA / "dielectric_physical_features_v03.csv"

EXPANDED_NUMERIC = (
    "gap_gfn2_eV", "homo_gfn2_eV", "lumo_gfn2_eV",
    "batt_gap_eV", "batt_homo_eV", "batt_lumo_eV",
    "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "gfn2_minus_batt_gap_eV", "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV",
    "gfn2_minus_pubchemqc_homo_eV", "gfn2_minus_pubchemqc_lumo_eV",
)

ROSTER_DESCRIPTORS = (
    "heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
    "polarizability_A3", "dipole_D", "homo_lumo_gap_ev",
)


def _float_or_none(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def load_expanded_layer() -> dict[str, dict[str, object]]:
    """扩展层 {InChIKey: {数值列 + 元数据列}}；同键重复时保留首个非空行。"""
    out: dict[str, dict[str, object]] = {}
    with EXPANDED_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("inchikey") or "").strip()
            if not key:
                continue
            record: dict[str, object] = {
                "name": row.get("name", ""),
                "expansion_tier": row.get("expansion_tier", ""),
                "structure_check": row.get("structure_check", ""),
                "in_epsilon_roster": row.get("in_epsilon_roster", ""),
                "source_level": row.get("source_level", ""),
                "unit_check": row.get("unit_check", ""),
                "geometry_sha256": row.get("geometry_sha256", ""),
                "natoms": _float_or_none(row.get("natoms", "")),
                "calibration_id": row.get("calibration_id", ""),
                "role": row.get("role", ""),
            }
            for column in EXPANDED_NUMERIC:
                record[column] = _float_or_none(row.get(column, ""))
            if key in out:
                existing = out[key]
                if existing.get("gap_gfn2_eV") is None and record.get("gap_gfn2_eV") is not None:
                    out[key] = record
            else:
                out[key] = record
    return out


def load_roster_descriptors() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with ROSTER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["inchikey"]
            record: dict[str, float] = {}
            for column in ROSTER_DESCRIPTORS:
                value = _float_or_none(row.get(column, ""))
                if value is not None:
                    record[column] = value
            out[key] = record
    return out


def expanded_join_roster(layer: Mapping[str, Mapping[str, object]],
                         descriptors: Mapping[str, Mapping[str, float]],
                         ) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, record in layer.items():
        merged: dict[str, object] = {"inchikey": key}
        merged.update(record)
        merged.update(descriptors.get(key, {}))
        rows.append(merged)
    rows.sort(key=lambda item: str(item["inchikey"]))
    return rows


def load_transfer_pairs() -> list[dict[str, str]]:
    with TRANSFER_PAIRS_CSV.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def iter_summary_json(artifacts_dir: Path | None = None) -> Iterator[tuple[Path, Mapping[str, object]]]:
    base = artifacts_dir or ARTIFACTS
    for path in sorted(base.glob("*_summary.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            yield path, payload


def descriptor_panel(rows: Sequence[Mapping[str, object]],
                     descriptor: str) -> tuple[list[int], "list[float]" ]:
    import numpy as np

    indices: list[int] = []
    values: list[float] = []
    for index, row in enumerate(rows):
        value = row.get(descriptor)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            indices.append(index)
            values.append(float(value))
    return indices, values
