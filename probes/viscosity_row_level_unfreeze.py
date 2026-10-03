"""Week 18 lane A: the viscosity channel at row level, with the 176-row kinematic thaw.

The frozen viscosity baseline (``probes/viscosity_baseline_summary.json``) reads
MAE 0.17477197208762 / R2 0.7481271437772365 on its group-key split; the gate is
MAE <= 0.15 on log10(cP).  The Walden registration
(``probes/walden_dn_channel_prereg.json``, section ``kinematic_thaw``) recorded the
176 ThermoML kinematic rows as a family-level fact only, blocked on
``data/density_v01.csv``.  That dependency is on disk and 176/176 rows pair to a
density at |dT| <= 1e-3 K, so this arm carries the channel from family level to row
level.

Three scoreboards, reported side by side and never subtracted from one another:

* ``family_level``  the frozen pool itself, reproduced in place (the control);
* ``thaw_only``     the frozen pool plus the 86 admissible thawed rows;
* ``row_level``     the frozen pool plus 483 pure ThermoML Pa*s rows and the 86 thawed
                    rows.

Every rule is imported and never re-implemented: the split, the features, the fitter
and the criterion come from ``probes/viscosity_baseline.py``; the thaw pairing comes
from ``probes/build_viscosity_v02.py``.  Nothing here reads or writes the frozen
epsilon numbers 0.4091179943351143 / 0.4766400383507876, and nothing here is
promoted: this arm produces a pool reading only.
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import build_viscosity_v02 as thaw_rule
import numpy as np
import viscosity_baseline as frozen
from export_results_common import write_json_stable

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

TASK_ID = "week18_w18a_viscosity_row_level_unfreeze"

V01_PATH = REPOSITORY_ROOT / "data" / "viscosity_v01.csv"
V02_PATH = REPOSITORY_ROOT / "data" / "viscosity_v02.csv"
THERMOML_PATH = REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
DENSITY_PATH = REPOSITORY_ROOT / "data" / "density_v01.csv"
DIELECTRIC_PATH = REPOSITORY_ROOT / "data" / "dielectric_v04.csv"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "viscosity_row_level_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "viscosity_row_level_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "viscosity_row_level_unfreeze.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_PATH = ARTIFACTS_DIR / "viscosity_row_level_repeats.csv"

#: The frozen baseline reading and its own input digest, quoted from
#: ``probes/viscosity_baseline_summary.json``.  They are never rewritten here.
FROZEN_MAE = 0.17477197208762
FROZEN_R2 = 0.7481271437772365
FROZEN_V01_SHA256 = "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"
FROZEN_TOLERANCE = 1e-9

MAE_GATE = frozen.MAE_GATE
SEED = frozen.SEED
MODEL_NAME = "MorganTemperatureXGBoost"

POOL_FAMILY = "family_level"
POOL_THAW_ONLY = "thaw_only"
POOL_ROW_LEVEL = "row_level"
POOL_ORDER = (POOL_FAMILY, POOL_THAW_ONLY, POOL_ROW_LEVEL)
POOL_ROLE = {
    POOL_FAMILY: "族级读数：冻结基线的原位复现（control）",
    POOL_THAW_ONLY: "增量读数：只加 86 行解冻纯组分运动黏度",
    POOL_ROW_LEVEL: "行级读数：+483 行 ThermoML 纯组分 Pa*s、+86 行解冻行",
}

SPLIT_ORDER = ("random_row", "group_key")

EXPECTED = {
    "v01_rows": 3582,
    "v01_keys": 957,
    "thermoml_rows": 2725,
    "thermoml_dynamic_rows": 2549,
    "thermoml_kinematic_rows": 176,
    "thawed_converted_rows": 176,
    "thawed_pooled_rows": 86,
    "thawed_deferred_rows": 90,
    "thermoml_pure_dynamic_rows": 483,
    "thermoml_pure_dynamic_keys": 43,
    "pool_family_rows": 3582,
    "pool_family_keys": 957,
    "pool_thaw_only_rows": 3668,
    "pool_thaw_only_keys": 960,
    "pool_row_level_rows": 4151,
    "pool_row_level_keys": 976,
}

READING_COLUMNS = (
    "reading",
    "pool",
    "split_type",
    "model",
    "train_rows",
    "test_rows",
    "train_keys",
    "test_keys",
    "group_overlap_keys",
    "thawed_rows_in_test",
    "mae_on_thawed_test_rows_log10_cP",
    "mae_log10_cP",
    "rmse_log10_cP",
    "r2_log10_cP",
    "mae_cP",
    "mae_Pa_s",
    "gate_mae_lt_0_15",
    "train_id_hash",
    "test_id_hash",
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write LF-only CSV: .gitattributes pins *.csv to eol=lf."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_smiles_map() -> dict[str, str]:
    """The local InChIKey -> SMILES lookup, built from the tables that carry SMILES.

    First writer wins; the order is fixed so a rebuild is byte identical.
    """

    mapping: dict[str, str] = {}
    for path in (V01_PATH, V02_PATH, DENSITY_PATH, DIELECTRIC_PATH):
        for row in read_csv_rows(path):
            key = (row.get("inchikey") or "").strip()
            value = (row.get("smiles") or "").strip()
            if key and value:
                mapping.setdefault(key, value)
    return mapping


def _row(
    *,
    inchikey: str,
    smiles: str,
    name: str,
    temperature: float,
    eta_pa_s: float,
    provenance: str,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "inchikey": inchikey,
        "smiles": smiles,
        "name": name,
        "T_K": float(temperature),
        "viscosity_Pa_s": float(eta_pa_s),
        "provenance": provenance,
    }
    if extra:
        record.update(extra)
    return record


def build_pools() -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    """Build the three pools plus the census that must agree with the pre-registration."""

    smiles_map = build_smiles_map()
    v01_rows = read_csv_rows(V01_PATH)
    if len(v01_rows) != EXPECTED["v01_rows"]:
        raise RuntimeError("the v01 row count moved")

    family: list[dict[str, object]] = []
    for row in v01_rows:
        family.append(
            _row(
                inchikey=str(row["inchikey"]),
                smiles=str(row["smiles"]),
                name=str(row["name"]),
                temperature=float(row["T_K"]),
                eta_pa_s=float(row["viscosity_Pa_s"]),
                provenance="viscosity_v01",
            )
        )

    thermoml_rows = read_csv_rows(THERMOML_PATH)
    if len(thermoml_rows) != EXPECTED["thermoml_rows"]:
        raise RuntimeError("the ThermoML observation table moved")
    kinematic = [
        row for row in thermoml_rows if (row.get("viscosity_kinematic_m2_s") or "").strip()
    ]
    dynamic = [row for row in thermoml_rows if (row.get("viscosity_Pa_s") or "").strip()]
    if len(kinematic) != EXPECTED["thermoml_kinematic_rows"]:
        raise RuntimeError("the frozen kinematic count moved")
    if len(dynamic) != EXPECTED["thermoml_dynamic_rows"]:
        raise RuntimeError("the ThermoML dynamic row count moved")

    pairing = thaw_rule.pair_kinematic_rows(kinematic, read_csv_rows(DENSITY_PATH))
    thawed: list[dict[str, object]] = []
    thawed_missing_smiles: list[str] = []
    pooled_keys: list[str] = []
    for entry in pairing["per_row"]:
        if not entry["pooled_into_main_table"]:
            continue
        key = str(entry["inchikey"])
        pooled_keys.append(key)
        smiles = smiles_map.get(key, "")
        if not smiles:
            thawed_missing_smiles.append(key)
            continue
        thawed.append(
            _row(
                inchikey=key,
                smiles=smiles,
                name=str(entry["name"]),
                temperature=float(entry["T_K"]),
                eta_pa_s=float(entry["converted_pa_s"]),
                provenance="kinematic_thawed",
                extra={
                    "kinematic_m2_s": float(entry["viscosity_kinematic_m2_s"]),
                    "density_kg_m3": float(entry["density_kg_m3"]),
                    "density_delta_t_k": float(entry["delta_t_k"]),
                },
            )
        )
    thawed.sort(key=lambda item: (str(item["inchikey"]), float(item["T_K"])))

    pure_dynamic: list[dict[str, object]] = []
    dynamic_multi_component = 0
    dynamic_missing_smiles: list[str] = []
    for row in dynamic:
        if (row.get("n_components") or "").strip() != "1":
            dynamic_multi_component += 1
            continue
        key = str(row["inchikey"])
        smiles = smiles_map.get(key, "")
        if not smiles:
            dynamic_missing_smiles.append(key)
            continue
        pure_dynamic.append(
            _row(
                inchikey=key,
                smiles=smiles,
                name=str(row.get("name") or ""),
                temperature=float(row["T_K"]),
                eta_pa_s=float(row["viscosity_Pa_s"]),
                provenance="thermoml_pa_s_pure",
            )
        )
    pure_dynamic.sort(
        key=lambda item: (str(item["inchikey"]), float(item["T_K"]), float(item["viscosity_Pa_s"]))
    )

    pools = {
        POOL_FAMILY: list(family),
        POOL_THAW_ONLY: [*family, *thawed],
        POOL_ROW_LEVEL: [*family, *thawed, *pure_dynamic],
    }
    census: dict[str, object] = {
        "v01_rows": len(family),
        "v01_keys": len({str(row["inchikey"]) for row in family}),
        "v01_sha256": canonical_text_sha256(V01_PATH),
        "thermoml_rows": len(thermoml_rows),
        "thermoml_dynamic_rows": len(dynamic),
        "thermoml_kinematic_rows": len(kinematic),
        "thaw_pairing": {
            "local_rows": int(pairing["local_rows"]),
            "exact_rows": int(pairing["exact_rows"]),
            "nearest_rows": int(pairing["nearest_rows"]),
            "converted_rows": int(pairing["converted_rows"]),
            "pooled_rows": int(pairing["pooled_rows"]),
            "deferred_multi_component_rows": int(pairing["deferred_multi_component_rows"]),
            "exact_tolerance_k": float(pairing["exact_tolerance_k"]),
            "nearest_tolerance_k": float(pairing["nearest_tolerance_k"]),
            "pooled_keys": sorted(set(pooled_keys)),
        },
        "thawed_rows_admitted": len(thawed),
        "thawed_rows_missing_smiles": thawed_missing_smiles,
        "thermoml_pure_dynamic_rows": len(pure_dynamic),
        "thermoml_pure_dynamic_keys": len({str(row["inchikey"]) for row in pure_dynamic}),
        "thermoml_dynamic_multi_component_rows": dynamic_multi_component,
        "thermoml_dynamic_missing_smiles_keys": sorted(set(dynamic_missing_smiles)),
        "pools": {
            name: {
                "rows": len(rows),
                "keys": len({str(row["inchikey"]) for row in rows}),
            }
            for name, rows in pools.items()
        },
    }
    return pools, census


def _check_census(census: Mapping[str, object]) -> list[str]:
    """Every count the pre-registration fixed, checked against the census."""

    problems: list[str] = []
    pairing = census["thaw_pairing"]
    pools = census["pools"]
    assert isinstance(pairing, Mapping)
    assert isinstance(pools, Mapping)
    pairs = (
        ("v01_rows", census["v01_rows"]),
        ("v01_keys", census["v01_keys"]),
        ("thermoml_rows", census["thermoml_rows"]),
        ("thermoml_dynamic_rows", census["thermoml_dynamic_rows"]),
        ("thermoml_kinematic_rows", census["thermoml_kinematic_rows"]),
        ("thawed_converted_rows", pairing["converted_rows"]),
        ("thawed_pooled_rows", pairing["pooled_rows"]),
        ("thawed_deferred_rows", pairing["deferred_multi_component_rows"]),
        ("thermoml_pure_dynamic_rows", census["thermoml_pure_dynamic_rows"]),
        ("thermoml_pure_dynamic_keys", census["thermoml_pure_dynamic_keys"]),
        ("pool_family_rows", pools[POOL_FAMILY]["rows"]),
        ("pool_family_keys", pools[POOL_FAMILY]["keys"]),
        ("pool_thaw_only_rows", pools[POOL_THAW_ONLY]["rows"]),
        ("pool_thaw_only_keys", pools[POOL_THAW_ONLY]["keys"]),
        ("pool_row_level_rows", pools[POOL_ROW_LEVEL]["rows"]),
        ("pool_row_level_keys", pools[POOL_ROW_LEVEL]["keys"]),
    )
    for name, observed in pairs:
        if int(observed) != EXPECTED[name]:
            problems.append(f"{name}: expected {EXPECTED[name]}, observed {observed}")
    return problems


_WORKER_STATE: dict[str, object] = {}


def _init_worker(state: Mapping[str, object]) -> None:
    _WORKER_STATE.clear()
    _WORKER_STATE.update(state)


def _fit_task(task: tuple[str, str]) -> dict[str, object]:
    """One (pool, split) cell: the frozen fitter on the frozen split protocol."""

    pool_name, split_type = task
    record = _WORKER_STATE[pool_name]
    assert isinstance(record, Mapping)
    features = record["features"]
    target = record["target"]
    keys = record["keys"]
    groups = record["groups"]
    thawed_mask = record["thawed_mask"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(thawed_mask, np.ndarray)
    if split_type == "random_row":
        train_indices, test_indices = frozen._random_row_split(len(target))
    else:
        train_indices, test_indices = frozen._group_key_split(groups)
    prediction = frozen._fit_predict(MODEL_NAME, features, target, train_indices, test_indices)
    metrics = frozen.transformed_metrics(target[test_indices], prediction)
    thawed_in_test = thawed_mask[test_indices]
    thawed_mae: object = ""
    if bool(thawed_in_test.any()):
        thawed_mae = float(
            np.mean(np.abs(target[test_indices][thawed_in_test] - prediction[thawed_in_test]))
        )
    train_keys = {str(keys[int(index)]) for index in train_indices}
    test_keys = {str(keys[int(index)]) for index in test_indices}
    return {
        "reading": split_type,
        "pool": pool_name,
        "split_type": split_type,
        "model": MODEL_NAME,
        "train_rows": len(train_indices),
        "test_rows": len(test_indices),
        "train_keys": len(train_keys),
        "test_keys": len(test_keys),
        "group_overlap_keys": len(train_keys & test_keys),
        "thawed_rows_in_test": int(thawed_in_test.sum()),
        "mae_on_thawed_test_rows_log10_cP": thawed_mae,
        "mae_log10_cP": float(metrics["log10_cP"]["mae"]),
        "rmse_log10_cP": float(metrics["log10_cP"]["rmse"]),
        "r2_log10_cP": float(metrics["log10_cP"]["r2"]),
        "mae_cP": float(metrics["cP"]["mae"]),
        "mae_Pa_s": float(metrics["Pa_s"]["mae"]),
        "gate_mae_lt_0_15": bool(metrics["log10_cP"]["mae"] < MAE_GATE),
        "train_id_hash": frozen._split_hash(keys, train_indices),
        "test_id_hash": frozen._split_hash(keys, test_indices),
    }


def _pool_state(
    pools: Mapping[str, list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for name in POOL_ORDER:
        rows = pools[name]
        features, _feature_names = frozen.build_feature_matrix(
            [str(row["smiles"]) for row in rows],
            [float(row["T_K"]) for row in rows],
        )
        target = np.log10(
            np.asarray([float(row["viscosity_Pa_s"]) for row in rows], dtype=float) * 1000.0
        )
        state[name] = {
            "features": features,
            "target": target,
            "keys": [str(row["inchikey"]) for row in rows],
            "groups": [str(row["inchikey"]) for row in rows],
            "thawed_mask": np.asarray(
                [str(row["provenance"]) == "kinematic_thawed" for row in rows], dtype=bool
            ),
        }
    return state


def evaluate(
    jobs: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fit every (pool, split) cell and return the readings in (pool, split) order.

    The fan-out is a thread pool, not a process pool: XGBoost releases the GIL
    inside a fit, so threads buy the whole speed-up here, while a spawn pool would
    re-import this probe and the frozen baselines in every child.  Every cell is
    independent of every other, so the readings do not depend on ``jobs``.
    """

    pools, census = build_pools()
    problems = _check_census(census)
    if problems:
        raise RuntimeError("census disagrees with the pre-registration: " + "; ".join(problems))
    state = _pool_state(pools)
    _init_worker(state)
    tasks = [(name, split) for name in POOL_ORDER for split in SPLIT_ORDER]
    if jobs <= 1:
        return [_fit_task(task) for task in tasks], census
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        readings = list(pool.map(_fit_task, tasks))
    return readings, census


def _reading(
    readings: Sequence[Mapping[str, object]], pool: str, split: str
) -> Mapping[str, object]:
    for row in readings:
        if row["pool"] == pool and row["split_type"] == split:
            return row
    raise KeyError(f"missing reading {pool}/{split}")


def build_summary(
    *,
    readings: Sequence[dict[str, object]],
    census: Mapping[str, object],
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    family = _reading(readings, POOL_FAMILY, "group_key")
    thrown = {
        name: {split: dict(_reading(readings, name, split)) for split in SPLIT_ORDER}
        for name in POOL_ORDER
    }
    observed_mae = float(family["mae_log10_cP"])
    observed_r2 = float(family["r2_log10_cP"])
    reproduction = {
        "published_mae_log10_cP": FROZEN_MAE,
        "published_r2_log10_cP": FROZEN_R2,
        "observed_mae_log10_cP": observed_mae,
        "observed_r2_log10_cP": observed_r2,
        "mae_abs_delta": abs(observed_mae - FROZEN_MAE),
        "r2_abs_delta": abs(observed_r2 - FROZEN_R2),
        "tolerance": FROZEN_TOLERANCE,
        "input_sha256": census["v01_sha256"],
        "published_input_sha256": FROZEN_V01_SHA256,
        "reproduced": (
            abs(observed_mae - FROZEN_MAE) <= FROZEN_TOLERANCE
            and abs(observed_r2 - FROZEN_R2) <= FROZEN_TOLERANCE
            and census["v01_sha256"] == FROZEN_V01_SHA256
        ),
    }
    row_level = _reading(readings, POOL_ROW_LEVEL, "group_key")
    thaw_only = _reading(readings, POOL_THAW_ONLY, "group_key")
    if not reproduction["reproduced"]:
        verdict = "unverified"
    elif float(row_level["mae_log10_cP"]) < MAE_GATE:
        verdict = "passes_gate_at_row_level"
    else:
        verdict = "refuted"
    gate = {
        "metric": "log10_cP mae on the group_key split",
        "threshold": MAE_GATE,
        "family_level_mae": observed_mae,
        "thaw_only_mae": float(thaw_only["mae_log10_cP"]),
        "row_level_mae": float(row_level["mae_log10_cP"]),
        "family_level_passed": bool(family["gate_mae_lt_0_15"]),
        "thaw_only_passed": bool(thaw_only["gate_mae_lt_0_15"]),
        "row_level_passed": bool(row_level["gate_mae_lt_0_15"]),
        "which_pool_passed": [
            name
            for name in POOL_ORDER
            if bool(_reading(readings, name, "group_key")["gate_mae_lt_0_15"])
        ],
    }
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "generated_at_utc": _utc_now(),
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "status": "locked_before_run",
        },
        "inputs": {
            name: {
                "path": portable_relative_path(path, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(path),
            }
            for name, path in (
                ("viscosity_v01", V01_PATH),
                ("viscosity_v02", V02_PATH),
                ("viscosity_observations_thermoml", THERMOML_PATH),
                ("density_v01", DENSITY_PATH),
                ("dielectric_v04", DIELECTRIC_PATH),
            )
        },
        "census": dict(census),
        "pool_roles": {name: POOL_ROLE[name] for name in POOL_ORDER},
        "readings": thrown,
        "reproduction_check": reproduction,
        "primary_gate": gate,
        "verdict": verdict,
        "promoted": False,
        "promotion_rule": "本枪只产出池升级读数；提升为主臂要另开一次预注册（判据 + 安慰剂 + 折签名）后才成立。",
        "honest_boundaries": [
            "族级、行级、增量是三块不同记分牌的并列读数，差值不构成本枪的任何结论。",
            "解冻只接受纯组分（n_components == 1）行；90 行多组分运动黏度按冻结规则 deferred，未入池。",
            "ThermoML 动态行同样只接受纯组分；2066 行多组分 Pa*s 行未入池。",
            "同一 (inchikey, T_K) 的重复观测两条都留、不做平均；v01 与 ThermoML 侧重叠 22 个单元。",
            "组键折只证明新分子外推，不排除骨架相似；random_row 折只作泄漏参照，永不进判决。",
            "本枪不动任何冻结数字：ε 基线 0.4091179943351143 与 ε 头条 0.4766400383507876 不在此记分牌上。",
        ],
        "telemetry": dict(telemetry),
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    census = summary["census"]
    gate = summary["primary_gate"]
    reproduction = summary["reproduction_check"]
    readings = summary["readings"]
    pool_roles = summary["pool_roles"]
    assert isinstance(census, Mapping)
    assert isinstance(gate, Mapping)
    assert isinstance(reproduction, Mapping)
    assert isinstance(readings, Mapping)
    assert isinstance(pool_roles, Mapping)
    lines = [
        "# η 通道行级解冻（W18-A）",
        "",
        "冻结基线的组键读数是 MAE 0.17477197208762 / R2 0.7481271437772365（池 data/viscosity_v01.csv，3582 行 / 957 键），",
        "门是 log10(cP) MAE < 0.15。probes/walden_dn_channel_prereg.json 的 kinematic_thaw 把 176 行运动黏度登记为族级读数、",
        "解冻依赖 data/density_v01.csv。本枪把该依赖用上：176/176 行按 |dT| <= 1e-3 K 精确配到密度，eta = nu * rho 反解成动态黏度，",
        "其中纯组分 86 行入池、多组分 90 行按冻结规则另册。",
        "",
        "## 三个池、三块记分牌（并列报，绝不相减）",
        "",
        "| 读数 | 池 | 行 / 键 | group_key MAE | group_key R2 | 过 0.15 门 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in POOL_ORDER:
        block = readings[name]["group_key"]
        loose = readings[name]["random_row"]
        pool_census = census["pools"][name]
        passed = "是" if block["gate_mae_lt_0_15"] else "否"
        lines.append(
            "| `{}` | {} | {} / {} | `{:.14g}` | `{:.14g}` | {} |".format(
                name,
                pool_roles[name],
                pool_census["rows"],
                pool_census["keys"],
                block["mae_log10_cP"],
                block["r2_log10_cP"],
                passed,
            )
        )
        lines.append(
            "|  |  |  | random_row MAE `{:.14g}`（泄漏参照，不进判决） |  |  |".format(
                loose["mae_log10_cP"]
            )
        )
    passed_pools = gate["which_pool_passed"] or "（无）"
    verdict_text = summary["verdict"]
    lines.extend([
        "",
        "## 判决",
        "",
        f"- verdict：{verdict_text}",
        f"- 过门的池：{passed_pools}",
        "- 族级原位复现：MAE 偏差 {:.3e}、R2 偏差 {:.3e}（容差 {:.0e}）；输入摘要同钉：{}".format(
            reproduction["mae_abs_delta"],
            reproduction["r2_abs_delta"],
            reproduction["tolerance"],
            reproduction["reproduced"],
        ),
        f"- promoted：{summary['promoted']}",
        "",
        "## 解冻账本",
        "",
        "- 运动黏度行 {}；精确配对 {}、最近邻配对 {}、反解成功 {}".format(
            census["thermoml_kinematic_rows"],
            census["thaw_pairing"]["exact_rows"],
            census["thaw_pairing"]["nearest_rows"],
            census["thaw_pairing"]["converted_rows"],
        ),
        "- 入池（纯组分）{}；另册（多组分）{}".format(
            census["thaw_pairing"]["pooled_rows"],
            census["thaw_pairing"]["deferred_multi_component_rows"],
        ),
        "- 解冻涉及的键：{}".format(census["thaw_pairing"]["pooled_keys"]),
        "- ThermoML 纯组分动态行 {} 行 / {} 键；多组分未入池 {} 行".format(
            census["thermoml_pure_dynamic_rows"],
            census["thermoml_pure_dynamic_keys"],
            census["thermoml_dynamic_multi_component_rows"],
        ),
        "",
        "## 诚实边界",
        "",
    ])
    lines.extend("- " + str(item) for item in summary["honest_boundaries"])
    prereg = summary["preregistration"]
    telemetry = summary["telemetry"]
    lines.extend([
        "",
        "## 产物",
        "",
        "- 脚本：probes/viscosity_row_level_unfreeze.py",
        "- 预注册：{}（sha256 {}）".format(prereg["path"], prereg["sha256"]),
        "- 读数表：probes/artifacts/viscosity_row_level_repeats.csv",
        "- 摘要：probes/viscosity_row_level_summary.json",
        "- 墙钟：{:.1f} s，jobs {}".format(telemetry["wall_seconds"], telemetry["jobs"]),
        "",
    ])
    return lines


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = max(1, int(args.jobs))
    required = (PREREG_PATH, V01_PATH, V02_PATH, THERMOML_PATH, DENSITY_PATH, DIELECTRIC_PATH)
    for path in required:
        if not path.is_file():
            print("MISSING " + str(path))
            return 1
    started = time.perf_counter()
    readings, census = evaluate(jobs)
    telemetry = {
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "python": platform.python_version(),
        "platform": sys.platform,
        "fits": len(readings),
        "network_used": False,
        "xtb_executed": False,
    }
    summary = build_summary(readings=readings, census=census, telemetry=telemetry)
    summary["outputs"] = {
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        "repeats": portable_relative_path(REPEATS_PATH, root=REPOSITORY_ROOT),
    }
    write_csv_rows(
        REPEATS_PATH,
        READING_COLUMNS,
        [{column: row[column] for column in READING_COLUMNS} for row in readings],
    )
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(
        "\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n"
    )
    print()
    for name in POOL_ORDER:
        block = summary["readings"][name]["group_key"]
        print(
            "{:<12s} group_key MAE {:.16f}  R2 {:+.6f}  gate {}".format(
                name, block["mae_log10_cP"], block["r2_log10_cP"], block["gate_mae_lt_0_15"]
            )
        )
    print("reproduction ok : {}".format(summary["reproduction_check"]["reproduced"]))
    print("verdict         : {}".format(summary["verdict"]))
    print("passed pools    : {}".format(summary["primary_gate"]["which_pool_passed"]))
    print("wall seconds    : {:.1f}".format(telemetry["wall_seconds"]))
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
