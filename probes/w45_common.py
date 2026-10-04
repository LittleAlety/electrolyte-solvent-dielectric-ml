# -*- coding: utf-8 -*-
"""W45 共享计算层：扩展层标定列、分层边界与确定性分折工具。

W45 是计算周，四条 lane 共用同一份只读装载与工具：
  * load_layer_rows   —— 扩展层逐行的轨道/标定数值列（homo/lumo/gap × gfn2/batt/pubchemqc + calib）。
  * paired_rows       —— role == paired_anchor 且有双端 gap 的行（4668）。
  * calibrated_rows   —— role == calibrated_estimate 的行（449，只有 gfn2 + calib）。
  * affine_fit        —— 一元最小二乘 (slope, intercept) 与最大绝对残差。
  * kfold_by_key      —— 按 InChIKey 的确定性 k 折（sha256(seed:key) mod k），用于 out-of-sample 复拟合。
  * atom_bin          —— 重原子数分箱。

只读；不写标签池或特征列。
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA = REPOSITORY_ROOT / "data" / "processed"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"

EXPANDED_CSV = DATA / "themol_orbital_layer_expanded.csv"
ROSTER_CSV = DATA / "dielectric_physical_features_v03.csv"
QM9_OVERLAP_CSV = ARTIFACTS / "w39_qm9_overlap.csv"

NUMERIC_COLUMNS = (
    "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV",
    "batt_homo_eV", "batt_lumo_eV", "batt_gap_eV",
    "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "calib_homo_eV", "calib_lumo_eV", "natoms",
)
ROSTER_COLUMNS = ("heavy_atom_count", "hbd", "hba", "tpsa_A2",
                  "molecular_volume_A3", "polarizability_A3", "dipole_D")


def _float_or_none(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def load_layer_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with EXPANDED_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("inchikey") or "").strip()
            if not key:
                continue
            record: dict[str, object] = {
                "inchikey": key,
                "expansion_tier": (row.get("expansion_tier") or "").strip(),
                "role": (row.get("role") or "").strip(),
                "in_epsilon_roster": (row.get("in_epsilon_roster") or "").strip(),
                "calibration_id": (row.get("calibration_id") or "").strip(),
            }
            for column in NUMERIC_COLUMNS:
                record[column] = _float_or_none(row.get(column, ""))
            rows.append(record)
    rows.sort(key=lambda item: str(item["inchikey"]))
    return rows


def paired_rows() -> list[dict[str, object]]:
    return [row for row in load_layer_rows()
            if row["role"] == "paired_anchor"
            and isinstance(row.get("gap_gfn2_eV"), float)
            and isinstance(row.get("batt_gap_eV"), float)]


def calibrated_rows() -> list[dict[str, object]]:
    return [row for row in load_layer_rows()
            if row["role"] == "calibrated_estimate"
            and isinstance(row.get("homo_gfn2_eV"), float)
            and isinstance(row.get("calib_homo_eV"), float)]


def load_roster_descriptors() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with ROSTER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["inchikey"]
            record: dict[str, float] = {}
            for column in ROSTER_COLUMNS:
                value = _float_or_none(row.get(column, ""))
                if value is not None:
                    record[column] = value
            out[key] = record
    return out


def load_qm9_dipoles() -> dict[str, dict[str, float]]:
    columns = ("our_dipole_D", "qm9_dipole_D", "dipole_delta_D",
               "dielectric", "hbd", "n_rotatable_bonds", "rigid")
    out: dict[str, dict[str, float]] = {}
    with QM9_OVERLAP_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            record: dict[str, float] = {}
            for column in columns:
                value = _float_or_none(row.get(column, ""))
                if value is not None:
                    record[column] = value
            out[row["inchikey"]] = record
    return out


def arrays(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for column in columns:
        out.append(np.asarray([float(row[column]) for row in rows], dtype=float))
    return out


def affine_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    residual = float(np.max(np.abs(y - (slope * x + intercept))))
    return float(slope), float(intercept), residual


def max_abs_residual(x: np.ndarray, y: np.ndarray, slope: float, intercept: float) -> float:
    return float(np.max(np.abs(y - (slope * x + intercept))))


def kfold_by_key(keys: Sequence[str], folds: int, seed: int) -> list[int]:
    out: list[int] = []
    for key in keys:
        digest = hashlib.sha256(("%d:%s" % (seed, key)).encode("utf-8")).hexdigest()
        out.append(int(digest[:12], 16) % folds)
    return out


def atom_bin(natoms: float, edges: Sequence[Sequence[int]]) -> str:
    value = int(natoms)
    for low, high in edges:
        if low <= value <= high:
            return "%d-%d" % (low, high)
    return "out_of_range"
