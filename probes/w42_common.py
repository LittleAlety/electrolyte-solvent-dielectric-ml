# -*- coding: utf-8 -*-
"""W42 共享计算层：四层轨道/偶极数据的只读装载与离线统计工具。

W42 是计算密集型周，四条 lane 共用同一份装载与重抽代码，放在这里避免逐件复制：
  * load_roster_keys   —— 241 行名册的 InChIKey 集合（覆盖分母）。
  * load_layers        —— xTB / QM9 / PubChemQC / Batt 四层 {InChIKey: gap_eV}。
  * load_dipole_layers —— our / QM9 / PubChemQC 三源 {InChIKey: dipole_D}。
  * bootstrap_ci / permutation_p —— 秩统计量的重抽工具。
  * write_csv_lf / criteria_row / verdict_of / pick_cjk_font。

只读；不写标签池或特征列。
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy import stats

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA = REPOSITORY_ROOT / "data" / "processed"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"

ROSTER_CSV = DATA / "dielectric_physical_features_v03.csv"
XTB_CSV = DATA / "w23_orbital_medium_layer.csv"
QM9_CSV = ARTIFACTS / "w39_qm9_overlap.csv"
PUBCHEMQC_CSV = DATA / "orbital_second_source_layer.csv"
BATT_CSV = ARTIFACTS / "w41_orbital_batt_hits.csv"
DOMAIN_CSV = ARTIFACTS / "w40_onsager_domain_compounds.csv"

LAYER_ORDER = ("xtb", "qm9", "pubchemqc", "batt")
LAYER_LABEL = {
    "xtb": "GFN2-xTB 气相（THEMol 几何）",
    "qm9": "QM9 B3LYP/6-31G(2df,p) 气相",
    "pubchemqc": "PubChemQC B3LYP/6-31G*//PM6 气相",
    "batt": "Batt-P30K ωB97X-V/def2-TZVPPD/SMD",
}

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079
FROZEN_READINGS = (FROZEN_BASELINE, FROZEN_HEADLINE,
                   FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _float_or_none(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def load_roster_keys() -> set[str]:
    keys: set[str] = set()
    with ROSTER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            keys.add(row["inchikey"])
    return keys


def _layer_from_csv(path: Path, column: str, roster: set[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["inchikey"]
            value = _float_or_none(row.get(column, ""))
            if key in roster and value is not None:
                values[key] = value
    return values


def load_layers() -> dict[str, dict[str, float]]:
    """四层轨道通道的 {InChIKey: gap_eV}，只留名册内的行。"""
    roster = load_roster_keys()
    return {
        "xtb": _layer_from_csv(XTB_CSV, "gas_free_gap_eV", roster),
        "qm9": _layer_from_csv(QM9_CSV, "qm9_gap_ev", roster),
        "pubchemqc": _layer_from_csv(PUBCHEMQC_CSV, "gap_eV", roster),
        "batt": _layer_from_csv(BATT_CSV, "batt_gap_ev", roster),
    }


def load_dipole_layers() -> dict[str, dict[str, float]]:
    """our / QM9 / PubChemQC 三源偶极 {InChIKey: Debye}，只留名册内的行。"""
    roster = load_roster_keys()
    return {
        "our": _layer_from_csv(ROSTER_CSV, "dipole_D", roster),
        "qm9": _layer_from_csv(QM9_CSV, "qm9_dipole_D", roster),
        "pubchemqc": _layer_from_csv(PUBCHEMQC_CSV, "dipole_debye", roster),
    }


def overlap_keys(layers: Mapping[str, Mapping[str, float]],
                 names: Sequence[str]) -> list[str]:
    if not names:
        return []
    keys = set(layers[names[0]])
    for name in names[1:]:
        keys &= set(layers[name])
    return sorted(keys)


def arrays(layers: Mapping[str, Mapping[str, float]],
           names: Sequence[str], keys: Sequence[str]) -> tuple[np.ndarray, ...]:
    return tuple(np.asarray([layers[name][k] for k in keys], dtype=float) for name in names)


def pairwise_stats(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    spearman = stats.spearmanr(x, y)
    kendall = stats.kendalltau(x, y)
    slope, intercept = np.polyfit(x, y, 1)
    pearson = float(np.corrcoef(x, y)[0, 1]) if len(x) > 1 else float("nan")
    return {
        "n": int(len(x)),
        "spearman": float(spearman.statistic),
        "kendall": float(kendall.statistic),
        "pearson": pearson,
        "r2": pearson ** 2,
        "slope_y_on_x": float(slope),
        "intercept_y_on_x": float(intercept),
    }


def bootstrap_ci(x: np.ndarray, y: np.ndarray, draws: int, seed: int,
                 statistic: Callable[[np.ndarray, np.ndarray], float] | None = None,
                 alpha: float = 0.05) -> dict[str, float]:
    """成对 bootstrap：同一行下标同时重抽 x 与 y。"""
    stat = statistic or (lambda a, b: float(stats.spearmanr(a, b).statistic))
    rng = np.random.default_rng(seed)
    n = len(x)
    reps = np.empty(draws, dtype=float)
    for index in range(draws):
        pick = rng.integers(0, n, n)
        reps[index] = stat(x[pick], y[pick])
    return {
        "point": float(stat(x, y)),
        "mean": float(np.mean(reps)),
        "sd": float(np.std(reps, ddof=1)),
        "lo": float(np.percentile(reps, 100 * alpha / 2)),
        "hi": float(np.percentile(reps, 100 * (1 - alpha / 2))),
        "draws": int(draws),
    }


def permutation_p(x: np.ndarray, y: np.ndarray, draws: int, seed: int,
                  statistic: Callable[[np.ndarray, np.ndarray], float] | None = None,
                  ) -> dict[str, float]:
    stat = statistic or (lambda a, b: float(stats.spearmanr(a, b).statistic))
    rng = np.random.default_rng(seed)
    observed = float(stat(x, y))
    count = 0
    extreme = 0.0
    for _ in range(draws):
        value = float(stat(x, rng.permutation(y)))
        if abs(value) >= abs(observed):
            count += 1
        extreme = max(extreme, abs(value))
    return {
        "observed": observed,
        "p_value": (count + 1) / (draws + 1),
        "count_ge": int(count),
        "max_abs_null": extreme,
        "draws": int(draws),
    }


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, float):
                text = "" if value != value else repr(value)
            else:
                text = "" if value is None else str(value)
            if any(ch in text for ch in (",", '"', "\n")):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def verdict_of(ok: bool) -> str:
    return "成立" if ok else "判否"


def criteria_row(identifier: str, description: str, value: object, threshold: object,
                 ok: bool) -> dict[str, object]:
    return {
        "id": identifier,
        "description": description,
        "value": value,
        "threshold": threshold,
        "verdict": verdict_of(ok),
    }


def pick_cjk_font() -> str | None:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "SimSun"):
        if candidate in available:
            return candidate
    return None
