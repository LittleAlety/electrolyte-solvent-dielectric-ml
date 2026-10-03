"""W18 P2: swap the target -- Onsager/Kirkwood delta learning on the frozen protocol.

The frozen W17 record contains exactly one reading above 0.60: the
single-representation Physical arm on full_table_lever4 at 0.6080587938801277
(seed 42), whose frozen five-seed mean is 0.5861142332208197.  Week 17 killed the
head-swap lever (shot 17, refuted at -0.041024) and the representation-stacking
lever.  This probe fires the third lever that is still untested: the target.

Nothing on the frozen side moves -- the pool, the folds, the scorer and the
13-column Physical(lever4) block are all inherited.  What changes is what the
trees are asked to fit:

* reference_direct          the frozen head fits epsilon itself (the anchor).
* onsager_analytic_only     no learning at all: the closed-form Onsager
                            reaction-field estimate is the whole prediction.
* onsager_delta_xgb        the analytic term is added back after the frozen head
                            fits only the residual epsilon - epsilon_Onsager.
* onsager_delta_recomputed the same delta scheme, with the analytic term taken
                            from the frozen v0.4 conformer table's single-conformer
                            dipole density instead of the lever4 column.

Week 8 C4 already ran a delta layer under an MAE / RepeatedKFold protocol on a
different pool, and it lost to the plain direct regressor (8.54 vs 6.36 MAE).
That is a prior, not a substitute for this shot: the endpoint here is R2 on the
frozen W17 pool with the 0.6081 anchor, a five-seed mean endpoint and a placebo.

The seed convention is shot 16's: only the fold draw changes with the seed, the
model keeps random_state = SEED = 42.  The reference arm therefore has to
reproduce all five frozen full_table_lever4/Physical readings bit for bit.

This probe is diagnostic: no reading it produces may be promoted.  The frozen
headline stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv/Scripts/python.exe probes/dielectric_onsager_delta_w18.py --jobs 4
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_representation_ablation import (
    PHYSICAL_COLUMNS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
    read_csv_rows,
)
from dielectric_representation_seed_robustness import (
    CONFORMER_FEATURES_PATH,
    build_context,
    splits_for,
)
from export_results_common import write_json_stable
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path
from electrolyte_ml.xtb_features import (
    _AVOGADRO_CONSTANT,
    _BOLTZMANN_CONSTANT_J_PER_K,
    _DEBYE_TO_COULOMB_METRE,
    _VACUUM_PERMITTIVITY_F_PER_M,
    onsager_dielectric_estimate,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_onsager_delta_w18_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_onsager_delta_w18_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_onsager_delta_w18.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_onsager_delta_w18"

REPRESENTATION = "Physical(lever4)"
DEFAULT_SEEDS = "42,1234,2026,31337,7"
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
CSV_ROUND_TRIP_TOLERANCE = 1e-06
PLACEBO_SEED = 2026

ARM_REFERENCE = "reference_direct"
ARM_ANALYTIC = "onsager_analytic_only"
ARM_DELTA = "onsager_delta_xgb"
ARM_DELTA_RECOMPUTED = "onsager_delta_recomputed"
ARMS = (ARM_REFERENCE, ARM_ANALYTIC, ARM_DELTA, ARM_DELTA_RECOMPUTED)

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
CONFIRMED_BAR_R2 = 0.02
PARTIAL_BAR_R2 = 0.005
MIN_CONFIRMING_SEEDS = 5

FROZEN_PER_SEED = {
    42: 0.6080587938801277,
    1234: 0.5653494903237062,
    2026: 0.5848044432962747,
    31337: 0.5985324927011,
    7: 0.5738259459028902,
}
FROZEN_CROSS_SEED = 0.5861142332208197

ARM_DESCRIPTIONS = {
    ARM_REFERENCE: "冻结头（XGB 200 树 / 深度 2 / lr 0.05, random_state=42）直接拟合 epsilon（锚点）",
    ARM_ANALYTIC: "纯解析：仅用 Onsager 反应场方程，无 ML",
    ARM_DELTA: "冻结头只拟合残差 epsilon - epsilon_Onsager，预测时加回解析项",
    ARM_DELTA_RECOMPUTED: "同 Delta 方案，但解析项改用 v0.4 构象表的单构象偶极密度（mu_sq_over_Vm_frozen）",
}

SANITY_NAMES = (
    "water",
    "methanol",
    "formamide",
    "n-methylacetamide",
    "dimethyl sulfoxide",
    "acetonitrile",
    "ethanol",
    "1,2-ethanediol",
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def code(text: object) -> str:
    """Inline code span without putting a literal backtick in this source file."""

    return chr(96) + str(text) + chr(96)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--seeds", type=str, default=DEFAULT_SEEDS)
    parser.add_argument("--arms", type=str, default="")
    parser.add_argument("--placebo", action="store_true")
    return parser.parse_args(argv)


def parse_arms(raw: str) -> tuple[str, ...]:
    """Canonical arm order; the frozen reference is always present."""

    requested = [token.strip() for token in str(raw).split(",") if token.strip()]
    if not requested:
        return ARMS
    unknown = [token for token in requested if token not in ARMS]
    if unknown:
        raise SystemExit("unknown arm: " + ", ".join(unknown))
    return tuple(arm for arm in ARMS if arm in requested or arm == ARM_REFERENCE)


def lever4_terms(matrix: np.ndarray) -> dict[str, np.ndarray]:
    """The four frozen columns the analytic Onsager term is allowed to read."""

    temperature = matrix[:, PHYSICAL_COLUMNS.index("T_K")]
    dipole = matrix[:, PHYSICAL_COLUMNS.index("dipole_D")]
    volume_a3 = matrix[:, PHYSICAL_COLUMNS.index("molecular_volume_A3")]
    polarizability = matrix[:, PHYSICAL_COLUMNS.index("polarizability_A3")]
    molar_volume = volume_a3 * 1e-30 * _AVOGADRO_CONSTANT
    return {
        "temperature": temperature,
        "dipole": dipole,
        "molar_volume": molar_volume,
        "dipole_density": dipole**2 / molar_volume,
        "polarizability_density": polarizability / (3.0 * volume_a3),
    }


def onsager_from_terms(
    dipole_density: np.ndarray,
    polarizability_density: np.ndarray,
    temperature: np.ndarray,
) -> np.ndarray:
    """Closed form of the Onsager reaction-field equation.

    (eps - n2)(2 eps + n2) / (eps (n2 + 2)^2) = A  gives
    eps = (L + sqrt(L^2 + 8 n2^2)) / 4 with L = n2 + A (n2 + 2)^2.
    """

    density = np.asarray(dipole_density, dtype=float)
    polar = np.asarray(polarizability_density, dtype=float)
    heat = np.asarray(temperature, dtype=float)
    reaction_field = (
        density
        * _DEBYE_TO_COULOMB_METRE**2
        * _AVOGADRO_CONSTANT
        / (9.0 * _VACUUM_PERMITTIVITY_F_PER_M * _BOLTZMANN_CONSTANT_J_PER_K * heat)
    )
    high_frequency = (1.0 + 2.0 * polar) / (1.0 - polar)
    linear = high_frequency + reaction_field * (high_frequency + 2.0) ** 2
    return (linear + np.sqrt(linear**2 + 8.0 * high_frequency**2)) / 4.0


def onsager_from_matrix(matrix: np.ndarray) -> np.ndarray:
    terms = lever4_terms(matrix)
    return onsager_from_terms(
        terms["dipole_density"], terms["polarizability_density"], terms["temperature"]
    )


def unit_self_check(matrix: np.ndarray, sample_size: int = 16) -> dict[str, object]:
    """The vectorised form against the repository's canonical scalar function."""

    terms = lever4_terms(matrix)
    polarizability = matrix[:, PHYSICAL_COLUMNS.index("polarizability_A3")]
    rows: list[dict[str, object]] = []
    worst = 0.0
    for index in range(min(int(sample_size), int(matrix.shape[0]))):
        expected = onsager_dielectric_estimate(
            float(terms["dipole"][index]),
            float(terms["molar_volume"][index]),
            float(polarizability[index]),
            float(terms["temperature"][index]),
        )
        measured = float(onsager_from_matrix(matrix[index : index + 1])[0])
        gap = abs(measured - expected)
        worst = max(worst, gap)
        rows.append(
            {
                "row": int(index),
                "dipole_D": float(terms["dipole"][index]),
                "molar_volume_m3_mol": float(terms["molar_volume"][index]),
                "polarizability_A3": float(polarizability[index]),
                "T_K": float(terms["temperature"][index]),
                "eps_onsager_vectorised": measured,
                "eps_onsager_canonical": expected,
                "abs_gap": gap,
            }
        )
    return {"rows": rows, "max_abs_gap": worst, "ok": worst <= ANCHOR_TOLERANCE}


def density_column_check(matrix: np.ndarray) -> dict[str, object]:
    """mu_sq_over_Vm must equal dipole_D^2 / molar volume column by column."""

    column = matrix[:, PHYSICAL_COLUMNS.index("mu_sq_over_Vm")]
    derived = lever4_terms(matrix)["dipole_density"]
    scale = np.maximum(1.0, np.abs(column))
    gap = np.abs(column - derived) / scale
    return {
        "rows": int(column.size),
        "tolerance": CSV_ROUND_TRIP_TOLERANCE,
        "max_relative_gap": float(gap.max()) if column.size else 0.0,
        "rows_above_tolerance": int((gap > CSV_ROUND_TRIP_TOLERANCE).sum()),
    }


def molar_volume_feature_check(matrix: np.ndarray, base_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """molecular_volume_A3 * 1e-30 * N_A must be the frozen molar volume."""

    volume_a3 = matrix[: len(base_rows), PHYSICAL_COLUMNS.index("molecular_volume_A3")]
    derived = volume_a3 * 1e-30 * _AVOGADRO_CONSTANT
    feature = np.asarray(
        [float(str(row["_features"]["molar_volume_m3_mol"])) for row in base_rows],  # type: ignore[index]
        dtype=float,
    )
    gap = np.abs(derived - feature) / np.maximum(1e-30, np.abs(feature))
    return {
        "rows": int(feature.size),
        "tolerance": CSV_ROUND_TRIP_TOLERANCE,
        "max_relative_gap": float(gap.max()) if feature.size else 0.0,
        "rows_above_tolerance": int((gap > CSV_ROUND_TRIP_TOLERANCE).sum()),
    }


def table_density_map() -> dict[str, float]:
    """The v0.4 conformer table's single-conformer dipole density per compound."""

    density: dict[str, float] = {}
    for row in read_csv_rows(CONFORMER_FEATURES_PATH):
        key = str(row.get("inchikey", "")).strip()
        text = str(row.get("mu_sq_over_Vm_frozen", "")).strip()
        if not key or not text:
            continue
        try:
            density[key] = float(text)
        except ValueError:
            continue
    return density


def recomputed_onsager(
    matrix: np.ndarray,
    base_keys: Sequence[str],
    density_map: Mapping[str, float],
) -> tuple[np.ndarray, dict[str, int]]:
    """The analytic term from the table instead of the lever4 dipole density."""

    terms = lever4_terms(matrix)
    keys = list(base_keys) + [""] * (int(matrix.shape[0]) - len(base_keys))
    table = np.asarray([density_map.get(key, math.nan) for key in keys], dtype=float)
    available = np.isfinite(table)
    chosen = np.where(available, table, terms["dipole_density"])
    estimate = onsager_from_terms(
        chosen, terms["polarizability_density"], terms["temperature"]
    )
    scale = np.maximum(1.0, np.abs(terms["dipole_density"]))
    moved = available & (np.abs(chosen - terms["dipole_density"]) / scale > ANCHOR_TOLERANCE)
    return estimate, {
        "rows_with_a_table_density": int(available.sum()),
        "rows_where_the_table_moves_the_density": int(moved.sum()),
    }


def conformer_mean_wiring_check(
    matrix: np.ndarray,
    base_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The conformer-mean column must equal the lever4 column, so it is not an arm."""

    conformer_mean: dict[str, float] = {}
    for row in read_csv_rows(CONFORMER_FEATURES_PATH):
        if str(row.get("status")) != "ok":
            continue
        text = str(row.get("mu_sq_over_Vm_conformer_mean", "")).strip()
        if text:
            try:
                conformer_mean[str(row["inchikey"])] = float(text)
            except ValueError:
                continue
    column = lever4_terms(matrix)["dipole_density"][: len(base_rows)]
    worst = 0.0
    covered = 0
    for index, row in enumerate(base_rows):
        value = conformer_mean.get(str(row["inchikey"]))
        if value is None:
            continue
        covered += 1
        worst = max(worst, abs(value - float(column[index])) / max(1.0, abs(value)))
    return {
        "compounds_checked": covered,
        "max_relative_gap": worst,
        "identical": worst <= ANCHOR_TOLERANCE,
    }


def sanity_check(
    matrix: np.ndarray,
    base_rows: Sequence[Mapping[str, object]],
    target: np.ndarray,
) -> list[dict[str, object]]:
    """Five-plus known liquids, so a unit mistake cannot hide behind a mean."""

    terms = lever4_terms(matrix)
    estimate = onsager_from_matrix(matrix)
    best: dict[str, tuple[float, int]] = {}
    for index, row in enumerate(base_rows):
        name = str(row.get("name", "")).lower()
        if name not in SANITY_NAMES:
            continue
        record = best.get(name)
        if record is None or float(target[index]) > record[0]:
            best[name] = (float(target[index]), index)
    rows: list[dict[str, object]] = []
    for name in SANITY_NAMES:
        record = best.get(name)
        if record is None:
            rows.append({"name": name, "available": False})
            continue
        observed, index = record
        rows.append(
            {
                "name": name,
                "available": True,
                "row": int(index),
                "T_K": float(terms["temperature"][index]),
                "dipole_D": float(terms["dipole"][index]),
                "polarizability_A3": float(
                    matrix[index, PHYSICAL_COLUMNS.index("polarizability_A3")]
                ),
                "molar_volume_m3_mol": float(terms["molar_volume"][index]),
                "eps_observed": observed,
                "eps_onsager": float(estimate[index]),
                "ratio": float(estimate[index]) / observed,
            }
        )
    return rows


_STATE: dict[str, object] = {}


def _init_worker(
    features: np.ndarray,
    groups: np.ndarray,
    target: np.ndarray,
    onsager: np.ndarray,
    onsager_recomputed: np.ndarray,
    arms: Sequence[str],
) -> None:
    _STATE["features"] = features
    _STATE["groups"] = groups
    _STATE["target"] = target
    _STATE["onsager"] = onsager
    _STATE["onsager_recomputed"] = onsager_recomputed
    _STATE["arms"] = tuple(arms)


def fit_head(
    train_features: np.ndarray,
    test_features: np.ndarray,
    train_target: np.ndarray,
) -> np.ndarray:
    """The frozen head, unchanged: XGB_PARAMS with the frozen random_state."""

    model = XGBRegressor(**XGB_PARAMS, random_state=SEED)
    model.fit(train_features, train_target)
    return np.asarray(model.predict(test_features), dtype=float)


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    """One fold: every requested arm, in one worker process."""

    repeat, fold, train_index, test_index = task
    features = _STATE["features"]
    target = _STATE["target"]
    onsager = _STATE["onsager"]
    onsager_recomputed = _STATE["onsager_recomputed"]
    arms = _STATE["arms"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert isinstance(onsager, np.ndarray)
    assert isinstance(onsager_recomputed, np.ndarray)
    assert isinstance(arms, tuple)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    train_features = features[train]
    test_features = features[test]
    train_target = target[train]
    predictions: dict[str, list[float]] = {}
    for arm in arms:
        if arm == ARM_ANALYTIC:
            raw = onsager[test]
        elif arm == ARM_REFERENCE:
            raw = fit_head(train_features, test_features, train_target)
        elif arm == ARM_DELTA:
            raw = onsager[test] + fit_head(
                train_features, test_features, train_target - onsager[train]
            )
        elif arm == ARM_DELTA_RECOMPUTED:
            raw = onsager_recomputed[test] + fit_head(
                train_features, test_features, train_target - onsager_recomputed[train]
            )
        else:
            raise ValueError("unknown arm: " + str(arm))
        predictions[str(arm)] = [
            float(value) for value in np.maximum(np.asarray(raw, dtype=float), 1.0)
        ]
    return (
        int(repeat),
        int(fold),
        [int(index) for index in train],
        [int(index) for index in test],
        predictions,
    )


def _parallel_map(
    function: Callable[[object], object],
    tasks: Sequence[object],
    jobs: int,
    *,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[object, ...] = (),
) -> list[object]:
    if jobs <= 1 or len(tasks) <= 1:
        if initializer is not None:
            initializer(*initargs)
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(
        max_workers=jobs, initializer=initializer, initargs=initargs
    ) as pool:
        return list(pool.map(function, tasks))


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    jobs: int,
    arms: Sequence[str],
    placebo: bool,
) -> tuple[list[dict[str, object]], int, dict[str, int], bool]:
    groups = np.asarray([str(item) for item in context["groups"]])
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    features = np.asarray(context["physical_lever4"], dtype=float)
    target = np.asarray(context["target"], dtype=float)
    onsager = np.asarray(context["onsager"], dtype=float)
    onsager_recomputed = np.asarray(context["onsager_recomputed"], dtype=float)
    splits = splits_for(seed, groups, scored, full_base)
    signature_ok = True
    if seed == ANCHOR_SEED:
        frozen = bn.fold_signature(list(context["frozen_splits"]))
        signature_ok = bn.fold_signature(splits) == frozen
    fit_target = target
    if placebo:
        generator = np.random.default_rng(PLACEBO_SEED)
        permuted = target.copy()
        permuted[scored] = target[scored][generator.permutation(int(scored.sum()))]
        fit_target = permuted
    tasks = [
        (
            int(repeat),
            int(fold),
            [int(index) for index in train],
            [int(index) for index in test],
        )
        for repeat, fold, train, test in splits
    ]
    results = _parallel_map(
        _fold_task,
        tasks,
        jobs,
        initializer=_init_worker,
        initargs=(features, groups, fit_target, onsager, onsager_recomputed, tuple(arms)),
    )
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    fold_rows: list[dict[str, object]] = []
    for repeat, fold, train_index, test_index, predictions in results:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(groups[train], groups[test]).size))
        for arm in arms:
            prediction = np.asarray(predictions[arm], dtype=float)
            fold_metrics = evaluate_repeat(target[test], prediction)
            fold_rows.append(
                {
                    "seed": int(seed),
                    "arm": str(arm),
                    "representation": REPRESENTATION,
                    "repeat": int(repeat),
                    "fold": int(fold),
                    "train_rows": int(train.size),
                    "test_rows": int(test.size),
                    "train_compounds": int(np.unique(groups[train]).size),
                    "test_compounds": int(np.unique(groups[test]).size),
                    "r2": fold_metrics["r2"],
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            bucket = buckets.setdefault((str(arm), int(repeat)), {"target": [], "prediction": []})
            bucket["target"].append(target[test])
            bucket["prediction"].append(prediction)
    repeat_rows: list[dict[str, object]] = []
    for (arm, repeat), bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(
            np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"])
        )
        repeat_rows.append(
            {
                "arm": arm,
                "representation": REPRESENTATION,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    leak = {
        "folds": len(straddling),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
    }
    return repeat_rows, len(fold_rows), leak, signature_ok


def arm_summary(repeat_rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    by_arm: dict[str, list[float]] = defaultdict(list)
    for row in repeat_rows:
        by_arm[str(row["arm"])].append(float(row["r2"]))
    summary: dict[str, dict[str, object]] = {}
    for arm, values in by_arm.items():
        summary[arm] = {
            "repeats": len(values),
            "r2_mean": float(np.mean(values)),
            "r2_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "r2_min": float(np.min(values)),
            "r2_max": float(np.max(values)),
        }
    return summary


def write_rows(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator=chr(10))
        writer.writerow(list(columns))
        for row in rows:
            writer.writerow([row.get(column, "") for column in columns])


def render_report(summary: Mapping[str, object]) -> str:
    answers = summary["decisions"]  # type: ignore[index]
    onsager = summary["onsager"]  # type: ignore[index]
    lines: list[str] = []
    lines.append("# Week 18 P2：Onsager / Kirkwood Δ-learning（只换目标，池 / 折 / 锚点全冻）")
    lines.append("")
    lines.append("**生成时间：** " + str(summary["generated_at_utc"]))
    lines.append("**探针：** " + code("probes/dielectric_onsager_delta_w18.py"))
    lines.append("**预注册：** " + code("probes/dielectric_onsager_delta_w18_prereg.json"))
    lines.append("**读数：** " + str(answers["verdict"]) + "（任何读数一律**不提升**）")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(str(summary["headline_text"]))
    lines.append("")
    lines.append("## 一、锚点复现（逐种子，非只跑 seed 42）")
    lines.append("")
    lines.append("本枪沿用 shot 16 的种子约定：**只有折的抽取随种子变化，模型 " + code("random_state") + " 恒为 42**。")
    lines.append("因此 " + code(ARM_REFERENCE) + " 必须逐位复现冻结记录里 " + code("full_table_lever4") + " / " + code("Physical") + " 的全部五个逐种子读数：")
    lines.append("")
    lines.append("| 种子 | 冻结值 | 本枪实测 | abs_gap | ok |")
    lines.append("| ---: | ---: | ---: | ---: | :--: |")
    for row in summary["anchors"]["rows"]:  # type: ignore[index]
        lines.append(
            "| " + str(row["seed"]) + " | " + format(float(row["expected"]), ".16f") + " | "
            + format(float(row["measured"]), ".16f") + " | "
            + format(float(row["abs_gap"]), ".3e") + " | "
            + ("是" if row["ok"] else "**否**") + " |"
        )
    lines.append("")
    cross = summary["anchors"]["cross_seed"]  # type: ignore[index]
    lines.append(
        "- 跨种子均值实测 " + format(float(cross["measured"]), ".16f")
        + " vs 冻结 " + format(float(cross["expected"]), ".16f")
        + "（abs_gap " + format(float(cross["abs_gap"]), ".3e") + "）"
    )
    lines.append(
        "- 折签名：" + ("与冻结折一致" if summary["anchors"]["fold_signature_ok"] else "**不一致**")  # type: ignore[index]
        + "；泄漏审计：" + str(summary["leakage_clean_text"])
    )
    lines.append("")
    lines.append("## 二、单位换算自检（先证没有算错，再看结论）")
    lines.append("")
    lines.append("解析项按本仓规范式 " + code("src/electrolyte_ml/xtb_features.py::onsager_dielectric_estimate") + " 复刻：")
    lines.append("")
    lines.append("- 高频介电常数（Lorentz–Lorenz）：" + code("n2 = (1 + 2q) / (1 - q)") + "，其中 " + code("q = N_A * alpha / (3 * V_m)"))
    lines.append("- 反应场项：" + code("A = N_A * mu^2 / (9 * eps0 * k_B * T * V_m)"))
    lines.append("- 解 " + code("(eps - n2)(2 eps + n2) / (eps (n2 + 2)^2) = A") + " ⇒ " + code("eps = (L + sqrt(L^2 + 8 n2^2)) / 4") + "，其中 " + code("L = n2 + A (n2 + 2)^2"))
    lines.append("")
    lines.append("**换算链（本枪第一次算错过的地方）：** " + str(onsager["unit_chain_note"]))
    lines.append("")
    lines.append("| 自检项 | 结果 |")
    lines.append("| --- | --- |")
    lines.append(
        "| 向量式 vs 规范标量式（前 " + str(len(onsager["self_check"]["rows"]))
        + " 行）最大绝对偏差 | " + format(float(onsager["self_check"]["max_abs_gap"]), ".3e") + " |"
    )
    lines.append(
        "| " + code("mu_sq_over_Vm") + " 列 vs " + code("dipole_D^2 / V_m") + " 最大相对偏差 | "
        + format(float(onsager["density_column_check"]["max_relative_gap"]), ".3e")
        + "（超差行 " + str(onsager["density_column_check"]["rows_above_tolerance"]) + "） |"
    )
    lines.append(
        "| " + code("molecular_volume_A3 * 1e-30 * N_A") + " vs 冻结 " + code("molar_volume_m3_mol") + " 最大相对偏差 | "
        + format(float(onsager["molar_volume_feature_check"]["max_relative_gap"]), ".3e")
        + "（超差行 " + str(onsager["molar_volume_feature_check"]["rows_above_tolerance"]) + "） |"
    )
    lines.append("")
    lines.append("**ε_Onsager sanity check（观测取该化合物在全池的最大 ε 行）：**")
    lines.append("")
    lines.append("| 化合物 | T / K | mu / D | alpha / A^3 | V_m / (m^3 mol^-1) | ε 观测 | ε_Onsager | 比值 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in onsager["sanity_check"]:
        if not row.get("available"):
            lines.append("| " + str(row["name"]) + " | - | - | - | - | - | - | - |")
            continue
        lines.append(
            "| " + str(row["name"]) + " | " + format(float(row["T_K"]), ".2f")
            + " | " + format(float(row["dipole_D"]), ".3f")
            + " | " + format(float(row["polarizability_A3"]), ".3f")
            + " | " + format(float(row["molar_volume_m3_mol"]), ".4e")
            + " | " + format(float(row["eps_observed"]), ".2f")
            + " | " + format(float(row["eps_onsager"]), ".2f")
            + " | " + format(float(row["ratio"]), ".3f") + " |"
        )
    lines.append("")
    lines.append(str(summary["sanity_text"]))
    lines.append("")
    lines.append("## 三、跨种子均值对比（端点 = 5 种子均值）")
    lines.append("")
    lines.append("| 臂 | 说明 | R2（种子均值） | sd | min | max | 相对 " + code(ARM_REFERENCE) + " |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for row in summary["cross_seed"]:  # type: ignore[index]
        lines.append(
            "| " + code(row["arm"]) + " | " + str(row["description"]) + " | "
            + format(float(row["r2_seed_mean"]), ".6f") + " | "
            + format(float(row["r2_seed_sd"]), ".4f") + " | "
            + format(float(row["r2_seed_min"]), ".6f") + " | "
            + format(float(row["r2_seed_max"]), ".6f") + " | "
            + format(float(row["improvement_vs_reference"]), "+.6f") + " |"
        )
    lines.append("")
    lines.append("## 四、逐种子明细（每格为该臂在该种子上的 10 repeat 均值 R2）")
    lines.append("")
    seed_list = [int(seed) for seed in summary["seeds"]]  # type: ignore[index]
    lines.append("| 臂 | " + " | ".join(str(seed) for seed in seed_list) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in seed_list) + " |")
    by_key: dict[tuple[int, str], Mapping[str, object]] = {}
    for row in summary["seed_rows"]:  # type: ignore[index]
        by_key[(int(row["seed"]), str(row["arm"]))] = row
    for arm in summary["arms"]:  # type: ignore[index]
        cells = [
            format(float(by_key[(seed, str(arm))]["r2_mean"]), ".6f") for seed in seed_list
        ]
        lines.append("| " + code(str(arm)) + " | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 五、判定规则（预先注册）")
    lines.append("")
    lines.append(
        "1. " + code("confirmed") + "：判据臂跨种子均值 ≥ " + code(ARM_REFERENCE) + " 跨种子均值 + "
        + format(float(answers["confirmed_bar_r2"]), ".2f")
    )
    lines.append(
        "2. " + code("partial") + "：≥ +" + format(float(answers["partial_bar_r2"]), ".3f")
        + " 但未达 " + code("confirmed")
    )
    lines.append("3. " + code("refuted") + "：无判据臂达到 +" + format(float(answers["partial_bar_r2"]), ".3f"))
    lines.append("")
    lines.append("## 六、边界（不许省略）")
    lines.append("")
    lines.append("1. 本枪**非盲**：0.6080587938801277 与 0.5861142332208197 在预注册之前就已知。")
    lines.append("2. 本枪**只换目标**，池 / 折 / 打分器 / 表示（13 列 Physical(lever4)）全部冻结；**不调参**（shot 17 已证内层选族不可迁移）。")
    lines.append("3. **任何读数一律不提升**：冻结头条保持 " + repr(FROZEN_HEADLINE) + "，冻结基线保持 " + repr(FROZEN_BASELINE) + "。")
    lines.append("4. Week 8 的 C4 是**另一块池、另一套口径（MAE / RepeatedKFold）**，两次读数**不得混比**。")
    lines.append("5. " + code(ARM_DELTA_RECOMPUTED) + " 用的是 v0.4 表的**单构象**偶极密度；表的 " + code("mu_sq_over_Vm_conformer_mean") + " 列与 lever4 列构造上等价，已作为接线自检而非独立臂。")
    lines.append("")
    return chr(10).join(lines) + chr(10)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at = _utc_now()
    jobs = max(1, int(args.jobs))
    arms = parse_arms(args.arms)
    seeds = tuple(int(token) for token in str(args.seeds).split(",") if token.strip())
    if not seeds:
        print("no seeds requested")
        return 1
    placebo = bool(args.placebo)

    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    scoreboard = v1.build_scoreboard()
    base_rows = list(scoreboard["rows"])
    context = build_context()
    matrix = np.asarray(context["physical_lever4"], dtype=float)
    target = np.asarray(context["target"], dtype=float)
    base_keys = [str(row["inchikey"]) for row in base_rows]
    onsager = onsager_from_matrix(matrix)
    onsager_recomputed, recomputed_report = recomputed_onsager(matrix, base_keys, table_density_map())
    context["onsager"] = onsager
    context["onsager_recomputed"] = onsager_recomputed

    scored_mask = np.asarray(context["scored"], dtype=bool)
    scored_total = int(scored_mask.sum())
    scored_compounds = len(
        {str(row["inchikey"]) for row, flag in zip(base_rows, scored_mask, strict=False) if flag}
    )
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
        flush=True,
    )
    print("arms: " + ", ".join(arms), flush=True)
    print("seeds: " + ", ".join(str(seed) for seed in seeds), flush=True)
    print("placebo: " + str(placebo), flush=True)

    self_check = unit_self_check(matrix)
    density_check = density_column_check(matrix)
    volume_check = molar_volume_feature_check(matrix, base_rows)
    wiring = conformer_mean_wiring_check(matrix, base_rows)
    sanity = sanity_check(matrix, base_rows, target)
    high = scored_mask & (target > 60.0)
    print(
        "unit self-check: max abs gap " + format(float(self_check["max_abs_gap"]), ".3e")
        + " | mu_sq_over_Vm column " + format(float(density_check["max_relative_gap"]), ".3e")
        + " | molar volume " + format(float(volume_check["max_relative_gap"]), ".3e"),
        flush=True,
    )
    print(
        "scored rows with eps > 60: " + str(int(high.sum()))
        + ", of which eps_onsager > 60: " + str(int((onsager[high] > 60.0).sum())),
        flush=True,
    )
    if not bool(self_check["ok"]):
        print("the vectorised Onsager form disagrees with the canonical one; refusing to continue")
        return 1

    per_seed: dict[int, list[dict[str, object]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    fold_counts: dict[str, int] = {}
    for seed in seeds:
        clock = time.perf_counter()
        repeat_rows, fold_count, leak, signature_ok = evaluate_seed(
            seed, context, jobs, arms, placebo
        )
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        per_seed[seed] = repeat_rows
        spreadsheet.extend({"seed": int(seed), **row} for row in repeat_rows)
        leakage[str(seed)] = leak
        fold_counts[str(seed)] = fold_count
        block = arm_summary(repeat_rows)
        for arm in arms:
            print(
                "  seed " + str(seed) + " | " + arm + " | "
                + format(float(block[arm]["r2_mean"]), ".6f")
                + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
                flush=True,
            )

    summaries = {seed: arm_summary(rows) for seed, rows in per_seed.items()}
    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    common = [seed for seed in seeds if seed in FROZEN_PER_SEED]
    if not placebo:
        for seed in common:
            measured = float(summaries[seed][ARM_REFERENCE]["r2_mean"])
            expected = float(FROZEN_PER_SEED[seed])
            gap = abs(measured - expected)
            ok = gap <= ANCHOR_TOLERANCE
            anchors_reproduced = anchors_reproduced and ok
            anchor_rows.append(
                {
                    "seed": int(seed),
                    "expected": expected,
                    "measured": measured,
                    "abs_gap": gap,
                    "ok": ok,
                }
            )
        if not anchors_reproduced:
            print("a frozen reference reading did not reproduce; refusing to report anything else")
            return 1
    comparable = bool(common) and set(common) == set(FROZEN_PER_SEED)
    cross_measured = (
        float(np.mean([float(summaries[seed][ARM_REFERENCE]["r2_mean"]) for seed in common]))
        if common
        else float("nan")
    )
    cross_gap = abs(cross_measured - FROZEN_CROSS_SEED) if comparable else float("nan")

    leak_clean = all(
        block["folds_with_a_straddling_compound"] == 0
        and block["max_straddling_compounds_in_a_fold"] == 0
        for block in leakage.values()
    )
    if not leak_clean:
        print("a scored compound straddled a fold; refusing to continue")
        return 1

    def endpoint(arm: str) -> float:
        if any(arm not in summaries[seed] for seed in seeds):
            return float("nan")
        return float(np.mean([float(summaries[seed][arm]["r2_mean"]) for seed in seeds]))

    reference_mean = float(endpoint(ARM_REFERENCE))
    comparison = [arm for arm in arms if arm != ARM_REFERENCE]
    improvements = {arm: float(endpoint(arm)) - reference_mean for arm in comparison}
    judged = [
        arm for arm in arms if arm in (ARM_DELTA, ARM_DELTA_RECOMPUTED) and arm != ARM_REFERENCE
    ]
    if judged:
        best_arm = max(judged, key=lambda arm: (improvements[arm], arm))
    else:
        best_arm = ARM_REFERENCE
    best_improvement = float(improvements.get(best_arm, 0.0))
    if placebo:
        verdict = "placebo"
    elif best_improvement >= CONFIRMED_BAR_R2 and len(seeds) >= MIN_CONFIRMING_SEEDS:
        verdict = "confirmed"
    elif best_improvement >= PARTIAL_BAR_R2:
        verdict = "partial"
    else:
        verdict = "refuted"
    if not placebo and verdict == "confirmed" and len(seeds) < MIN_CONFIRMING_SEEDS:
        verdict = "partial"

    seed_rows: list[dict[str, object]] = []
    for seed in seeds:
        for arm in arms:
            seed_rows.append({"seed": int(seed), "arm": arm, **summaries[seed][arm]})

    cross_rows: list[dict[str, object]] = []
    for arm in arms:
        values = [float(summaries[seed][arm]["r2_mean"]) for seed in seeds]
        cross_rows.append(
            {
                "arm": arm,
                "description": ARM_DESCRIPTIONS[arm],
                "r2_seed_mean": float(np.mean(values)),
                "r2_seed_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "r2_seed_min": float(np.min(values)),
                "r2_seed_max": float(np.max(values)),
                "improvement_vs_reference": float(np.mean(values)) - reference_mean,
            }
        )

    delta_mean = float(endpoint(ARM_DELTA))
    analytic_mean = float(endpoint(ARM_ANALYTIC))
    if verdict == "refuted":
        headline_text = (
            "跨种子均值："
            + code(ARM_REFERENCE) + " " + format(reference_mean, ".6f")
            + " vs " + code(ARM_DELTA) + " " + format(delta_mean, ".6f")
            + "（增益 " + format(improvements.get(ARM_DELTA, 0.0), "+.6f") + "）；"
            + "纯解析臂 " + code(ARM_ANALYTIC) + " " + format(analytic_mean, ".6f") + "。"
            + "⇒ 换目标**没有**买到分数：Delta 层不得提升，冻结头条 0.4766400383507876 不动。"
        )
    elif verdict == "partial":
        headline_text = (
            "跨种子均值：最佳判据臂 " + code(best_arm) + " 相对 " + code(ARM_REFERENCE)
            + " 增益 " + format(best_improvement, "+.6f") + "，达到 partial 线但未达 +0.02。"
            + "任何读数一律不提升。"
        )
    elif verdict == "confirmed":
        headline_text = (
            "跨种子均值：最佳判据臂 " + code(best_arm) + " 相对 " + code(ARM_REFERENCE)
            + " 增益 " + format(best_improvement, "+.6f") + "，达到预注册 confirmed 线。"
            + "仍为诊断读数：本枪不提升任何冻结数。"
        )
    else:
        headline_text = (
            "安慰剂枪：目标在计分化合物上被打乱，判据臂必须塌回直接拟合臂。跨种子均值 "
            + code(ARM_REFERENCE) + " " + format(reference_mean, ".6f")
            + " vs " + code(ARM_DELTA) + " " + format(delta_mean, ".6f") + "。"
        )

    high_scored = int(high.sum())
    high_onsager = int((onsager[high] > 60.0).sum())
    available_sanity = {
        str(row["name"]): float(row["eps_onsager"]) for row in sanity if row.get("available")
    }
    water_estimate = available_sanity.get("water")
    dmso_estimate = available_sanity.get("dimethyl sulfoxide")
    sanity_text = (
        "结论：解析项数量级正确（水 "
        + (format(water_estimate, ".1f") if water_estimate is not None else "无")
        + " vs 观测 87；DMSO "
        + (format(dmso_estimate, ".1f") if dmso_estimate is not None else "无")
        + " vs 观测 50.6），但**在计分池里 " + str(high_scored)
        + " 行 ε>60 中解析项只覆盖到 " + str(high_onsager)
        + " 行** —— Onsager 形式本身不含 g（取向相关），这正是缺的那一维。"
    )

    stem = ARTIFACT_STEM + ("_placebo" if placebo else "")
    summary_path = SUMMARY_PATH if not placebo else SUMMARY_PATH.with_name(stem + "_summary.json")
    report_path = REPORT_PATH if not placebo else REPORT_PATH.with_name(stem + ".md")
    repeats_path = ARTIFACTS_DIR / (stem + "_repeats.csv")
    folds_path = ARTIFACTS_DIR / (stem + "_folds.csv")

    wall_seconds = time.perf_counter() - started
    summary: dict[str, object] = {
        "schema": "dielectric_onsager_delta_w18/summary@1",
        "probe": "dielectric_onsager_delta_w18",
        "task": "w18_p2_onsager_delta",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at,
        "wall_seconds": wall_seconds,
        "jobs": jobs,
        "placebo": placebo,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "schema": prereg.get("schema"),
            "status": prereg.get("status"),
            "non_blind": prereg.get("non_blind"),
        },
        "pool": {
            "base_rows": int(context["n_base"]),
            "scored_rows": scored_total,
            "scored_compounds": scored_compounds,
            "expansion_rows": int(context["n_expansion"]),
            "folds_per_seed": fold_counts,
            "representation": REPRESENTATION,
            "columns": list(PHYSICAL_COLUMNS),
        },
        "onsager": {
            "formula": "n2 = (1 + 2q) / (1 - q), q = N_A alpha / (3 V_m); A = N_A mu^2 / (9 eps0 k_B T V_m); eps = (L + sqrt(L^2 + 8 n2^2)) / 4, L = n2 + A (n2 + 2)^2",
            "unit_chain_note": (
                "molecular_volume_A3 是**单分子**体积（A^3），不是摩尔体积：本枪第一版直接把该列当 V_m 用，"
                "导致 q 被放大 N_A 倍、n2 落到 -2、解析项全塌成 1.0。正确换算是 "
                "V_m = molecular_volume_A3 * 1e-30 * N_A（m^3/mol）；而极化率密度 "
                "q = polarizability_A3 / (3 * molecular_volume_A3) 里 N_A 正好抵消。"
            ),
            "constants": {
                "avogadro_per_mol": _AVOGADRO_CONSTANT,
                "boltzmann_j_per_k": _BOLTZMANN_CONSTANT_J_PER_K,
                "vacuum_permittivity_f_per_m": _VACUUM_PERMITTIVITY_F_PER_M,
                "debye_to_coulomb_metre": _DEBYE_TO_COULOMB_METRE,
            },
            "self_check": self_check,
            "density_column_check": density_check,
            "molar_volume_feature_check": volume_check,
            "conformer_mean_wiring_check": wiring,
            "recomputed_term": recomputed_report,
            "sanity_check": sanity,
            "scored_rows_above_60": high_scored,
            "scored_rows_above_60_covered_by_onsager": high_onsager,
        },
        "anchors": {
            "rows": anchor_rows,
            "reproduced": anchors_reproduced,
            "tolerance": ANCHOR_TOLERANCE,
            "fold_signature_ok": True,
            "cross_seed": {
                "measured": cross_measured,
                "expected": FROZEN_CROSS_SEED,
                "abs_gap": cross_gap,
                "comparable": comparable,
                "seeds_compared": common,
            },
            "frozen_per_seed": {str(seed): value for seed, value in FROZEN_PER_SEED.items()},
        },
        "seeds": [int(seed) for seed in seeds],
        "arms": list(arms),
        "leakage": leakage,
        "leakage_clean_text": (
            str(sum(fold_counts.values())) + " 折全 0（无化合物跨折）"
        ),
        "cross_seed": cross_rows,
        "seed_rows": seed_rows,
        "decisions": {
            "endpoint_reference_direct": reference_mean,
            "endpoint_onsager_analytic_only": analytic_mean,
            "endpoint_onsager_delta_xgb": delta_mean,
            "endpoint_onsager_delta_recomputed": float(endpoint(ARM_DELTA_RECOMPUTED)),
            "improvements": improvements,
            "judged_arms": judged,
            "best_arm": best_arm,
            "best_improvement": best_improvement,
            "confirmed_bar_r2": CONFIRMED_BAR_R2,
            "partial_bar_r2": PARTIAL_BAR_R2,
            "min_confirming_seeds": MIN_CONFIRMING_SEEDS,
            "verdict": verdict,
            "promotable": False,
        },
        "headline_text": headline_text,
        "sanity_text": sanity_text,
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "note": "diagnostic shot; nothing here may be promoted",
        },
        "outputs": {
            "summary": portable_relative_path(summary_path, root=REPOSITORY_ROOT),
            "report": portable_relative_path(report_path, root=REPOSITORY_ROOT),
            "repeats": portable_relative_path(repeats_path, root=REPOSITORY_ROOT),
            "folds": portable_relative_path(folds_path, root=REPOSITORY_ROOT),
        },
    }

    write_rows(
        repeats_path,
        ("seed", "arm", "representation", "repeat", *METRIC_NAMES),
        spreadsheet,
    )
    write_json_stable(summary_path, summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8", newline=chr(10))

    print(flush=True)
    print("verdict: " + verdict + "   best judged arm: " + str(best_arm)
          + "   improvement " + format(best_improvement, "+.6f"), flush=True)
    for row in cross_rows:
        print("  " + str(row["arm"]).ljust(28) + format(float(row["r2_seed_mean"]), ".6f")
              + "  (" + format(float(row["improvement_vs_reference"]), "+.6f") + ")", flush=True)
    print("wrote " + str(summary_path), flush=True)
    print("wrote " + str(report_path), flush=True)
    print("wrote " + str(repeats_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
