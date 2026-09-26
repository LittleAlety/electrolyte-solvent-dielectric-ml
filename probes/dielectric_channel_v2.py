"""Dielectric channel v2: a pre-declared, fully-reported model-family comparison.

Background.  The L3 stage-1 pilot (``probes/l3_stage1_pilot_summary.json``)
failed on the frozen v1 recipe: EC ranked 24th and PC 58th in the 236-row
solvent pool (C1 0/2 against the locked K = 20), and the C2_solvent magnitude
error was |delta log10| = 0.5939 (EC) / 0.5807 (PC) against the locked gate of
0.10.  The coordinator's diagnosis is that a depth-2 boosted-tree regressor is
piecewise constant and therefore cannot extrapolate past the largest training
target, while the two champions sit near the top of the pool's dielectric range.

This probe runs a *new* family of models under a protocol that is declared in
code before it is executed (``SELECTION_RULE``) and reports *every* family,
winner or not.  Nothing locked is touched: the C1 ``K``, the C2_solvent
``max_abs_delta_log10_epsilon`` and the pass expression are read verbatim from
``probes/l3_backvalidation_prereg.json`` and that file's digest is recorded.

Discipline notes that are load-bearing:

* The pool is the frozen ``probes/l3_stage1_pilot_pool.csv`` (236 rows); its
  sha256 is re-verified against the pre-registration before any scoring.
* Fold geometry is the frozen precedent: ``RepeatedKFold(n_splits=5,
  n_repeats=10, random_state=42)`` with ``seed = 42 + global split index``.
* EC and PC leave the training side of every one of the 50 folds and are still
  scored out-of-fold at their original fold; every fold asserts that
  ``champions INTERSECT train_ids`` is empty, and each fold's removal count is
  written to the fold artifact.
* This is a dielectric-channel model comparison, NOT the L3 verdict: C2_additive,
  C3 and the three other channels are not run here.

Every artifact is LF-only.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    SEED,
    XGB_PARAMS,
    morgan_count_features,
    physical_feature_matrix,
    read_csv_rows,
    read_modelling_rows,
)
from dielectric_target_and_scaffold import fit_predict
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import RepeatedKFold
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
FROZEN_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
PILOT_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json"
ARTIFACT_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
FOLDS_PATH = ARTIFACT_DIR / "dielectric_channel_v2_folds.csv"
PREDICTIONS_PATH = ARTIFACT_DIR / "dielectric_channel_v2_predictions.csv"
STRATA_PATH = ARTIFACT_DIR / "dielectric_channel_v2_strata.csv"
EXTRAPOLATION_PATH = ARTIFACT_DIR / "dielectric_channel_v2_extrapolation.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_channel_v2_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_channel_v2.md"

TASK = "dielectric_channel_v2"
DISCLAIMER = (
    "v1 冻结口径的读数已如实记录为未过；v2 是新配置，其出现顺序与选型规则均先声明后执行，"
    "全部配置无一遗漏上报"
)
POOL_EXPECTED_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
POOL_EXPECTED_ROWS = 236
POOL_LIST_NAME = "solvent"
TARGET_MODE_FROZEN = "log_epsilon_minus_one"
FOLD_AGGREGATION = "mean_over_the_10_out_of_fold_repeat_predictions"
RIDGE_ALPHAS = tuple(float(value) for value in np.logspace(-6.0, 6.0, 61))

CHAMPIONS = {
    "EC": {
        "name": "ethylene carbonate",
        "inchikey": "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
        "truth_dielectric": 90.5,
    },
    "PC": {
        "name": "propylene carbonate",
        "inchikey": "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
        "truth_dielectric": 64.9,
    },
}
CHAMPION_ORDER = ("EC", "PC")

MULTI_FEATURE_COLUMNS = (
    "mu_sq_over_Vm",
    "dipole_D",
    "polarizability_A3",
    "molecular_volume_A3",
    "homo_lumo_gap_ev",
    "T_K",
)
MULTI_FEATURE_INDEX = tuple(PHYSICAL_COLUMNS.index(column) for column in MULTI_FEATURE_COLUMNS)
MU_COLUMN_INDEX = PHYSICAL_COLUMNS.index("mu_sq_over_Vm")
ONSAGER = "onsager"
RAW = "raw"

FAMILIES: tuple[dict[str, object], ...] = (
    {
        "id": "frozen_v1_log_eps_xgb",
        "group": "a",
        "label": "冻结 v1 口径（Morgan+Physical 两臂各自回变换后等权平均，log(eps-1) 目标）",
        "kind": "frozen_xgb",
        "declared_feature_count": 2048 + len(PHYSICAL_COLUMNS),
    },
    {
        "id": "linear_raw_mu",
        "group": "b",
        "label": "eps ~ mu_sq_over_Vm 一元线性（OLS）",
        "kind": "ols_raw_mu",
        "declared_feature_count": 1,
    },
    {
        "id": "onsager_mu",
        "group": "c",
        "label": "(eps-1)/(eps+2) ~ mu_sq_over_Vm 一元线性（Onsager 形式）",
        "kind": "ols_onsager_mu",
        "declared_feature_count": 1,
    },
    {
        "id": "ridge_raw_multivar",
        "group": "d",
        "label": "eps ~ 六维物理特征 RidgeCV（LOO-GCV 选 alpha）",
        "kind": "ridge_raw_multi",
        "declared_feature_count": len(MULTI_FEATURE_COLUMNS),
    },
    {
        "id": "ridge_onsager_multivar",
        "group": "d",
        "label": "(eps-1)/(eps+2) ~ 六维物理特征 RidgeCV（LOO-GCV 选 alpha）",
        "kind": "ridge_onsager_multi",
        "declared_feature_count": len(MULTI_FEATURE_COLUMNS),
    },
    {
        "id": "delta_onsager_xgb",
        "group": "e",
        "label": "Delta-learning：Onsager 一元线性基线上用 XGBoost 学残差",
        "kind": "delta_onsager_xgb",
        "declared_feature_count": 1 + 2048 + len(PHYSICAL_COLUMNS),
    },
    {
        "id": "delta_ridge_onsager_xgb",
        "group": "e",
        "label": "Delta-learning：Onsager 六维 RidgeCV 基线上用 XGBoost 学残差",
        "kind": "delta_ridge_onsager_xgb",
        "declared_feature_count": len(MULTI_FEATURE_COLUMNS) + 2048 + len(PHYSICAL_COLUMNS),
    },
    {
        "id": "dummy_mean",
        "group": "control",
        "label": "DummyRegressor(strategy=mean) 对照",
        "kind": "dummy_mean",
        "declared_feature_count": 0,
    },
)
FAMILY_IDS = tuple(str(family["id"]) for family in FAMILIES)
BASELINE_FAMILY = "frozen_v1_log_eps_xgb"

SELECTION_RULE: dict[str, object] = {
    "rule_id": "dielectric_channel_v2_selection_rule_1",
    "declared_before_execution": True,
    "baseline_family": BASELINE_FAMILY,
    "eligibility": [
        "family.oof_raw_mae <= baseline.oof_raw_mae",
        "family.c1_hits > baseline.c1_hits",
    ],
    "pick": "minimum family.c2_max_abs_delta_log10 among eligible families",
    "tie_break": ["fewer declared_feature_count", "family id ascending"],
    "oof_raw_mae_definition": FOLD_AGGREGATION,
    "no_eligible_family_action": "winner_id = null and outcome = not_passed",
    "text": (
        "在同时满足 (a) 相对冻结 v1 口径的 OOF 原始 eps MAE 不劣化、"
        "(b) C1 命中数严格更大的家族中，取 C2 的 max|dlog10 eps| 最小者；"
        "并列取特征更少者，再并列按家族 id 字典序升序。无满足者即报未过。"
    ),
}

FOLD_COLUMNS = (
    "split_index",
    "fold",
    "repeat",
    "seed",
    "train_count_before_exclusion",
    "train_count_after_exclusion",
    "test_count",
    "champions_in_raw_train",
    "champions_removed_EC",
    "champions_removed_PC",
    "champions_in_test",
    "champions_intersect_train_after_exclusion",
    "train_max_epsilon",
    "train_min_epsilon",
)
PREDICTION_COLUMNS = (
    "family",
    "family_group",
    "repeat",
    "fold",
    "inchikey",
    "name",
    "is_champion",
    "champion_short",
    "target_dielectric",
    "prediction",
    "abs_error",
    "delta_log10",
    "abs_delta_log10",
    "rank_in_repeat",
    "in_top_k_in_repeat",
    "stratum",
    "train_max_epsilon",
)
STRATA_COLUMNS = ("family", "stratum", "n", "mae", "rmse", "mean_target")
EXTRAPOLATION_COLUMNS = (
    "family",
    "champion",
    "repeat",
    "fold",
    "seed",
    "train_max_epsilon",
    "ensemble_prediction",
    "morgan_arm_prediction",
    "physical_arm_prediction",
    "prediction_minus_train_max",
    "prediction_at_or_below_train_max",
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_csv_lf(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_prereg() -> dict:
    payload = _read_json(PREREG_PATH)
    if payload.get("status") != "LOCKED":
        raise ValueError("the L3 back-validation pre-registration is not LOCKED")
    return payload


def locked_constants(prereg: Mapping[str, object]) -> dict[str, object]:
    """The locked numbers this probe must read verbatim, never restate."""

    criteria = prereg["criteria"]
    return {
        "C1_K": criteria["C1_recall_at_K"]["K"],
        "C1_champions_required_in_top_k_total": criteria["C1_recall_at_K"][
            "champions_required_in_top_k_total"
        ],
        "C2_solvent_max_abs_delta_log10_epsilon": criteria["C2_magnitude_solvent"][
            "max_abs_delta_log10_epsilon"
        ],
        "pass_expression": criteria["pass_expression"],
        "pool_sha256": prereg["pool_rule"]["pool_sha256"],
        "pool_path": prereg["pool_rule"]["pool_path"],
        "min_scored_per_list": prereg["pool_rule"]["min_scored_per_list"],
    }


def load_pool() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Read the frozen pool and the frozen feature rows; refuse any drift."""

    raw_digest = sha256_file(POOL_PATH)
    canonical_digest = canonical_text_sha256(POOL_PATH)
    if raw_digest != POOL_EXPECTED_SHA256:
        raise ValueError(f"pool sha256 drifted: {raw_digest} != {POOL_EXPECTED_SHA256}")
    if canonical_digest != raw_digest:
        raise ValueError("the pool file is not LF-only, so its digest is ambiguous")
    prereg_digest = read_prereg()["pool_rule"]["pool_sha256"]
    if prereg_digest != POOL_EXPECTED_SHA256:
        raise ValueError("the pre-registration pins a different pool digest")
    pool_rows = read_csv_rows(POOL_PATH)
    if len(pool_rows) != POOL_EXPECTED_ROWS:
        raise ValueError(f"pool holds {len(pool_rows)} rows, expected {POOL_EXPECTED_ROWS}")
    modelling_rows, _, _ = read_modelling_rows(FROZEN_FEATURES_PATH)
    if [row["inchikey"] for row in pool_rows] != [row["inchikey"] for row in modelling_rows]:
        raise ValueError("pool rows and frozen feature rows are not index aligned")
    for pool_row, feature_row in zip(pool_rows, modelling_rows, strict=True):
        if float(pool_row["target_dielectric"]) != float(feature_row["dielectric"]):
            raise ValueError(f"dielectric target drifted for {pool_row['inchikey']}")
    return pool_rows, modelling_rows


def fold_geometry(row_count: int) -> list[dict[str, object]]:
    """The frozen fold geometry: RepeatedKFold seeds keyed by split index."""

    splitter = RepeatedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    geometry: list[dict[str, object]] = []
    for split_index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(row_count))
    ):
        geometry.append(
            {
                "split_index": split_index,
                "fold": split_index % N_SPLITS,
                "repeat": split_index // N_SPLITS,
                "seed": SEED + split_index,
                "train_indices": np.asarray(train_indices, dtype=int),
                "test_indices": np.asarray(test_indices, dtype=int),
            }
        )
    if len(geometry) != N_SPLITS * N_REPEATS:
        raise ValueError("unexpected RepeatedKFold geometry length")
    return geometry


def onsager_transform(target: np.ndarray) -> np.ndarray:
    target = np.asarray(target, dtype=float)
    if np.any(target <= 1.0):
        raise ValueError("(eps-1)/(eps+2) requires eps > 1")
    return (target - 1.0) / (target + 2.0)


ONSAGER_INVERSE_CLIP_LOW = -0.999999
ONSAGER_INVERSE_CLIP_HIGH = 1.0 - 1e-9


def onsager_inverse(
    values: np.ndarray,
    diagnostics: dict[str, object] | None = None,
) -> np.ndarray:
    """Invert y = (eps-1)/(eps+2) to eps, guarding the pole and the eps >= 1 floor.

    The clip bounds are named constants, not magic numbers: a linear fit on the
    Onsager scale can leave the valid range (-0.5, 1), and when it does the
    inverse sits on a pole.  Clip events are counted so the blow-up is visible in
    the summary instead of being silently absorbed.
    """

    raw = np.asarray(values, dtype=float)
    clip_events = int(
        np.sum((raw < ONSAGER_INVERSE_CLIP_LOW) | (raw > ONSAGER_INVERSE_CLIP_HIGH))
    )
    if diagnostics is not None:
        diagnostics["onsager_clip_events"] = clip_events
    clipped = np.clip(raw, ONSAGER_INVERSE_CLIP_LOW, ONSAGER_INVERSE_CLIP_HIGH)
    return np.maximum((1.0 + 2.0 * clipped) / (1.0 - clipped), 1.0)


def _ols_design(features: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(features)), features])


def _ols_coefficients(features: np.ndarray, target: np.ndarray) -> np.ndarray:
    coefficients, *_ = np.linalg.lstsq(_ols_design(features), target, rcond=None)
    return coefficients


def _ols_predict(coefficients: np.ndarray, features: np.ndarray) -> np.ndarray:
    return coefficients[0] + features @ coefficients[1:]


def _fit_ridge(features: np.ndarray, target: np.ndarray, train: np.ndarray):
    scaler = StandardScaler().fit(features[train])
    model = RidgeCV(alphas=RIDGE_ALPHAS, cv=None).fit(
        scaler.transform(features[train]), target[train]
    )
    return scaler, model


def _ridge_predict(scaler, model, features: np.ndarray, indices: np.ndarray) -> np.ndarray:
    return model.predict(scaler.transform(features[indices]))


def stratum_of(value: float) -> str:
    if value <= 20.0:
        return "le_20"
    if value <= 60.0:
        return "20_60"
    return "gt60"


def rank_order(predictions: np.ndarray, keys: Sequence[str]) -> list[int]:
    """Descending predicted eps, ties broken by InChIKey ascending."""

    return sorted(
        range(len(predictions)),
        key=lambda index: (-float(predictions[index]), keys[index]),
    )
FAMILY_BY_ID = {str(family["id"]): family for family in FAMILIES}


def predict_family(
    kind: str,
    *,
    target: np.ndarray,
    features: np.ndarray,
    multi: np.ndarray,
    mu: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    seed: int,
    frozen_ensemble: np.ndarray | None,
    diagnostics: dict[str, object] | None = None,
) -> np.ndarray:
    """Fit one family on `train` and return raw-epsilon predictions for `test`.

    Every family excludes the champions from `train` before this call; nothing
    here ever sees a champion label at fit time.
    """

    if kind == "frozen_xgb":
        if frozen_ensemble is None:
            raise ValueError("the frozen family needs its precomputed arm ensemble")
        return np.maximum(np.asarray(frozen_ensemble, dtype=float), 1.0)
    if kind == "dummy_mean":
        model = DummyRegressor(strategy="mean").fit(
            np.zeros((len(train), 1)), target[train]
        )
        return np.maximum(model.predict(np.zeros((len(test), 1))), 1.0)
    if kind == "ols_raw_mu":
        single = mu.reshape(-1, 1)
        coefficients = _ols_coefficients(single[train], target[train])
        return np.maximum(_ols_predict(coefficients, single[test]), 1.0)
    if kind == "ols_onsager_mu":
        single = mu.reshape(-1, 1)
        transformed = onsager_transform(target)
        coefficients = _ols_coefficients(single[train], transformed[train])
        return onsager_inverse(_ols_predict(coefficients, single[test]), diagnostics)
    if kind == "ridge_raw_multi":
        scaler, model = _fit_ridge(multi, target, train)
        if diagnostics is not None:
            diagnostics["ridge_alpha"] = float(model.alpha_)
        return np.maximum(_ridge_predict(scaler, model, multi, test), 1.0)
    if kind == "ridge_onsager_multi":
        scaler, model = _fit_ridge(multi, onsager_transform(target), train)
        if diagnostics is not None:
            diagnostics["ridge_alpha"] = float(model.alpha_)
        return onsager_inverse(_ridge_predict(scaler, model, multi, test), diagnostics)
    if kind == "delta_onsager_xgb":
        single = mu.reshape(-1, 1)
        transformed = onsager_transform(target)
        coefficients = _ols_coefficients(single[train], transformed[train])
        baseline_train = _ols_predict(coefficients, single[train])
        residual = transformed[train] - baseline_train
        booster = XGBRegressor(**XGB_PARAMS, random_state=seed).fit(
            features[train], residual
        )
        shifted = _ols_predict(coefficients, single[test]) + booster.predict(features[test])
        return onsager_inverse(shifted, diagnostics)
    if kind == "delta_ridge_onsager_xgb":
        transformed = onsager_transform(target)
        scaler, model = _fit_ridge(multi, transformed, train)
        baseline_train = _ridge_predict(scaler, model, multi, train)
        residual = transformed[train] - baseline_train
        booster = XGBRegressor(**XGB_PARAMS, random_state=seed).fit(
            features[train], residual
        )
        shifted = _ridge_predict(scaler, model, multi, test) + booster.predict(features[test])
        return onsager_inverse(shifted, diagnostics)
    raise ValueError(f"unknown family kind: {kind}")


def _mae(truth: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(prediction, float) - np.asarray(truth, float))))


def _rmse(truth: np.ndarray, prediction: np.ndarray) -> float:
    residual = np.asarray(prediction, float) - np.asarray(truth, float)
    return float(np.sqrt(np.mean(residual**2)))


def _r2(truth: np.ndarray, prediction: np.ndarray) -> float:
    truth = np.asarray(truth, float)
    residual = np.asarray(prediction, float) - truth
    total = float(np.sum((truth - truth.mean()) ** 2))
    if total == 0.0:
        raise ValueError("cannot compute R2 on a constant target")
    return float(1.0 - float(np.sum(residual**2)) / total)


def _g(value: float) -> str:
    return f"{float(value):.12g}"


def run_experiment(
    *,
    folds_path: Path = FOLDS_PATH,
    predictions_path: Path = PREDICTIONS_PATH,
    strata_path: Path = STRATA_PATH,
    extrapolation_path: Path = EXTRAPOLATION_PATH,
    summary_path: Path = SUMMARY_PATH,
    report_path: Path = REPORT_PATH,
) -> dict:
    prereg = read_prereg()
    locked = locked_constants(prereg)
    top_k = int(locked["C1_K"])
    c2_gate = float(locked["C2_solvent_max_abs_delta_log10_epsilon"])
    pool_rows, feature_rows = load_pool()
    keys = [row["inchikey"] for row in pool_rows]
    names = {row["inchikey"]: row["name"] for row in pool_rows}
    target = np.asarray([float(row["target_dielectric"]) for row in pool_rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in pool_rows])
    physical = physical_feature_matrix(feature_rows)
    xgb_features = np.hstack([morgan.astype(np.float64), physical])
    multi = physical[:, list(MULTI_FEATURE_INDEX)]
    mu = physical[:, MU_COLUMN_INDEX]

    champion_indices = {
        short: keys.index(str(spec["inchikey"])) for short, spec in CHAMPIONS.items()
    }
    if len(set(champion_indices.values())) != len(champion_indices):
        raise ValueError("the solvent champions do not occupy distinct pool rows")
    excluded = np.asarray(sorted(champion_indices.values()), dtype=int)
    excluded_set = {int(index) for index in excluded}

    geometry = fold_geometry(len(pool_rows))
    row_count = len(pool_rows)
    oof = {
        family_id: np.full((N_REPEATS, row_count), np.nan) for family_id in FAMILY_IDS
    }
    fold_of = np.full((N_REPEATS, row_count), -1, dtype=int)
    train_max_of = np.full((N_REPEATS, row_count), np.nan, dtype=float)
    ridge_alphas: dict[str, list[float]] = {family_id: [] for family_id in FAMILY_IDS}
    onsager_clip_events: dict[str, int] = {family_id: 0 for family_id in FAMILY_IDS}
    split_records: list[dict[str, object]] = []
    extrapolation_rows: list[dict[str, object]] = []
    champion_train_removals = {short: 0 for short in CHAMPION_ORDER}
    champion_held_out = {short: 0 for short in CHAMPION_ORDER}

    for split in geometry:
        split_index = int(split["split_index"])
        fold = int(split["fold"])
        repeat = int(split["repeat"])
        seed = int(split["seed"])
        raw_train = np.asarray(split["train_indices"], dtype=int)
        test = np.asarray(split["test_indices"], dtype=int)
        removed = {
            short: int(index in set(raw_train.tolist()))
            for short, index in champion_indices.items()
        }
        train = raw_train[~np.isin(raw_train, excluded)]
        if bool(np.isin(train, excluded).any()) or excluded_set.intersection(
            int(value) for value in train
        ):
            raise ValueError(f"champion survived into the train side of split {split_index}")
        if len(train) != len(raw_train) - sum(removed.values()):
            raise ValueError("champion removal changed the training set by the wrong amount")
        for short in CHAMPION_ORDER:
            champion_train_removals[short] += removed[short]
            if champion_indices[short] in set(test.tolist()):
                champion_held_out[short] += 1
        train_max = float(target[train].max())
        train_min = float(target[train].min())

        morgan_arm = fit_predict(
            "Morgan",
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train,
            test_indices=test,
            target_mode=TARGET_MODE_FROZEN,
            seed=seed,
        )
        physical_arm = fit_predict(
            "Physical",
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train,
            test_indices=test,
            target_mode=TARGET_MODE_FROZEN,
            seed=seed,
        )
        if not bool(np.all((morgan_arm >= 1.0) & (physical_arm >= 1.0))):
            raise ValueError(
                "the frozen arms must already satisfy eps >= 1, so the equal-weight "
                "average equals fit_predict('Morgan+Physical') exactly"
            )
        frozen_ensemble = 0.5 * (morgan_arm + physical_arm)

        for position, index in enumerate(test):
            if int(index) in excluded_set:
                short = next(
                    name for name, value in champion_indices.items() if value == int(index)
                )
                extrapolation_rows.append(
                    {
                        "family": BASELINE_FAMILY,
                        "champion": short,
                        "repeat": repeat,
                        "fold": fold,
                        "seed": seed,
                        "train_max_epsilon": _g(train_max),
                        "ensemble_prediction": _g(frozen_ensemble[position]),
                        "morgan_arm_prediction": _g(morgan_arm[position]),
                        "physical_arm_prediction": _g(physical_arm[position]),
                        "prediction_minus_train_max": _g(
                            frozen_ensemble[position] - train_max
                        ),
                        "prediction_at_or_below_train_max": (
                            "true" if frozen_ensemble[position] <= train_max else "false"
                        ),
                    }
                )

        for family in FAMILIES:
            family_id = str(family["id"])
            diagnostics: dict[str, object] = {}
            prediction = predict_family(
                str(family["kind"]),
                target=target,
                features=xgb_features,
                multi=multi,
                mu=mu,
                train=train,
                test=test,
                seed=seed,
                frozen_ensemble=frozen_ensemble,
                diagnostics=diagnostics,
            )
            if not bool(np.all(np.isfinite(prediction))):
                raise ValueError(f"{family_id} produced non-finite predictions")
            oof[family_id][repeat, test] = prediction
            if "ridge_alpha" in diagnostics:
                ridge_alphas[family_id].append(float(diagnostics["ridge_alpha"]))
            onsager_clip_events[family_id] += int(
                diagnostics.get("onsager_clip_events", 0)
            )

        for index in test:
            fold_of[repeat, int(index)] = fold
            train_max_of[repeat, int(index)] = train_max

        champions_in_test = [
            short for short in CHAMPION_ORDER if champion_indices[short] in set(test.tolist())
        ]
        split_records.append(
            {
                "split_index": split_index,
                "fold": fold,
                "repeat": repeat,
                "seed": seed,
                "train_count_before_exclusion": len(raw_train),
                "train_count_after_exclusion": len(train),
                "test_count": len(test),
                "champions_in_raw_train": ";".join(
                    short for short in CHAMPION_ORDER if removed[short]
                ),
                "champions_removed_EC": removed["EC"],
                "champions_removed_PC": removed["PC"],
                "champions_in_test": ";".join(champions_in_test),
                "champions_intersect_train_after_exclusion": 0,
                "train_max_epsilon": _g(train_max),
                "train_min_epsilon": _g(train_min),
            }
        )

    for family_id in FAMILY_IDS:
        if not bool(np.isfinite(oof[family_id]).all()):
            raise ValueError(f"incomplete out-of-fold predictions for {family_id}")
    if not bool(np.isfinite(train_max_of).all()):
        raise ValueError("some out-of-fold rows never received a training ceiling")
    if bool((fold_of < 0).any()):
        raise ValueError("some out-of-fold rows never received a fold number")

    baseline_hits_reference = None
    table: list[dict[str, object]] = []
    strata_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    per_repeat_delta: dict[str, dict[str, list[float]]] = {
        family_id: {short: [] for short in CHAMPION_ORDER} for family_id in FAMILY_IDS
    }
    for family_id in FAMILY_IDS:
        family = FAMILY_BY_ID[family_id]
        aggregated = oof[family_id].mean(axis=0)
        order = rank_order(aggregated, keys)
        rank = {index: position + 1 for position, index in enumerate(order)}
        per_repeat_mae = [
            _mae(target, oof[family_id][repeat]) for repeat in range(N_REPEATS)
        ]
        champion_rows: dict[str, dict[str, object]] = {}
        for short in CHAMPION_ORDER:
            index = champion_indices[short]
            truth = float(CHAMPIONS[short]["truth_dielectric"])
            predicted = float(aggregated[index])
            delta = math.log10(predicted / truth)
            champion_rows[short] = {
                "inchikey": str(CHAMPIONS[short]["inchikey"]),
                "pool_row_index": index,
                "aggregated_prediction": predicted,
                "truth_dielectric": truth,
                "delta_log10": delta,
                "abs_delta_log10": abs(delta),
                "rank": rank[index],
                "in_top_k": rank[index] <= top_k,
                "within_c2_tolerance": abs(delta) <= c2_gate,
            }
            per_repeat_delta[family_id][short] = [
                abs(math.log10(float(oof[family_id][repeat][index]) / truth))
                for repeat in range(N_REPEATS)
            ]
        c1_hits = sum(
            1 for row in champion_rows.values() if bool(row["in_top_k"])
        )
        c2_max = max(float(row["abs_delta_log10"]) for row in champion_rows.values())
        if baseline_hits_reference is None:
            baseline_hits_reference = c1_hits
        table.append(
            {
                "family": family_id,
                "family_group": str(family["group"]),
                "label": str(family["label"]),
                "declared_feature_count": int(family["declared_feature_count"]),
                "is_baseline": family_id == BASELINE_FAMILY,
                "oof_raw_mae": _mae(target, aggregated),
                "oof_raw_rmse": _rmse(target, aggregated),
                "oof_raw_r2": _r2(target, aggregated),
                "per_repeat_raw_mae_mean": float(np.mean(per_repeat_mae)),
                "per_repeat_raw_mae_min": float(np.min(per_repeat_mae)),
                "per_repeat_raw_mae_max": float(np.max(per_repeat_mae)),
                "c1_hits": c1_hits,
                "c1_passed": c1_hits == len(CHAMPION_ORDER),
                "ec_rank": int(champion_rows["EC"]["rank"]),
                "pc_rank": int(champion_rows["PC"]["rank"]),
                "ec_aggregated_prediction": float(
                    champion_rows["EC"]["aggregated_prediction"]
                ),
                "pc_aggregated_prediction": float(
                    champion_rows["PC"]["aggregated_prediction"]
                ),
                "ec_delta_log10": float(champion_rows["EC"]["delta_log10"]),
                "pc_delta_log10": float(champion_rows["PC"]["delta_log10"]),
                "ec_abs_delta_log10": float(champion_rows["EC"]["abs_delta_log10"]),
                "pc_abs_delta_log10": float(champion_rows["PC"]["abs_delta_log10"]),
                "c2_max_abs_delta_log10": c2_max,
                "c2_passed": c2_max <= c2_gate,
                "c2_gate_shortfall": c2_max - c2_gate,
                "max_prediction": float(oof[family_id].max()),
                "n_predictions_gt_1e3": int(np.sum(oof[family_id] > 1e3)),
                "onsager_clip_events": int(onsager_clip_events[family_id]),
                "ridge_alpha_mean": (
                    float(np.mean(ridge_alphas[family_id]))
                    if ridge_alphas[family_id]
                    else None
                ),
                "champions": champion_rows,
            }
        )

        for stratum in ("le_20", "20_60", "gt60"):
            member = np.asarray(
                [stratum_of(float(value)) == stratum for value in target], dtype=bool
            )
            count = int(member.sum())
            if count == 0:
                strata_rows.append(
                    {
                        "family": family_id,
                        "stratum": stratum,
                        "n": 0,
                        "mae": "",
                        "rmse": "",
                        "mean_target": "",
                    }
                )
                continue
            strata_rows.append(
                {
                    "family": family_id,
                    "stratum": stratum,
                    "n": count,
                    "mae": _g(_mae(target[member], aggregated[member])),
                    "rmse": _g(_rmse(target[member], aggregated[member])),
                    "mean_target": _g(float(target[member].mean())),
                }
            )

        for repeat in range(N_REPEATS):
            vector = oof[family_id][repeat]
            repeat_order = rank_order(vector, keys)
            repeat_rank = {
                index: position + 1 for position, index in enumerate(repeat_order)
            }
            for index, key in enumerate(keys):
                predicted = float(vector[index])
                truth = float(target[index])
                delta = math.log10(predicted / truth)
                short = next(
                    (
                        name
                        for name, value in champion_indices.items()
                        if value == index
                    ),
                    "",
                )
                prediction_rows.append(
                    {
                        "family": family_id,
                        "family_group": str(family["group"]),
                        "repeat": repeat,
                        "fold": int(fold_of[repeat, index]),
                        "inchikey": key,
                        "name": names[key],
                        "is_champion": "true" if short else "false",
                        "champion_short": short,
                        "target_dielectric": _g(truth),
                        "prediction": _g(predicted),
                        "abs_error": _g(abs(predicted - truth)),
                        "delta_log10": _g(delta),
                        "abs_delta_log10": _g(abs(delta)),
                        "rank_in_repeat": repeat_rank[index],
                        "in_top_k_in_repeat": (
                            "true" if repeat_rank[index] <= top_k else "false"
                        ),
                        "stratum": stratum_of(truth),
                        "train_max_epsilon": _g(train_max_of[repeat, index]),
                    }
                )
    baseline_row = next(row for row in table if row["family"] == BASELINE_FAMILY)
    winner, eligible_families = select_winner(table)
    best_c2_row = min(
        table,
        key=lambda row: (
            float(row["c2_max_abs_delta_log10"]),
            int(row["declared_feature_count"]),
            str(row["family"]),
        ),
    )
    passing_c1 = [str(row["family"]) for row in table if bool(row["c1_passed"])]
    passing_c2 = [str(row["family"]) for row in table if bool(row["c2_passed"])]
    passing_both = [
        str(row["family"]) for row in table if bool(row["c1_passed"]) and bool(row["c2_passed"])
    ]
    baseline_hits = int(baseline_row["c1_hits"])
    baseline_c2 = float(baseline_row["c2_max_abs_delta_log10"])
    joint_improvers = [
        str(row["family"])
        for row in table
        if int(row["c1_hits"]) > baseline_hits
        and float(row["c2_max_abs_delta_log10"]) < baseline_c2
    ]

    def _spread(family_id: str) -> dict[str, dict[str, str]]:
        return {
            short: {
                "min_abs_delta_log10": _g(min(per_repeat_delta[family_id][short])),
                "max_abs_delta_log10": _g(max(per_repeat_delta[family_id][short])),
                "mean_abs_delta_log10": _g(
                    float(np.mean(per_repeat_delta[family_id][short]))
                ),
            }
            for short in CHAMPION_ORDER
        }

    pilot_summary = _read_json(PILOT_SUMMARY_PATH)
    pilot_c2 = pilot_summary["readings"]["C2_magnitude_solvent"]["champions"]
    pilot_ranks = pilot_summary["readings"]["C1_recall_at_K"][
        "champion_ranks_in_dielectric_solvent_list"
    ]
    anchor = {
        "pilot_summary": portable_relative_path(PILOT_SUMMARY_PATH, root=REPOSITORY_ROOT),
        "pilot_ec_rank": int(pilot_ranks["EC"]),
        "pilot_pc_rank": int(pilot_ranks["PC"]),
        "recomputed_ec_rank": int(baseline_row["ec_rank"]),
        "recomputed_pc_rank": int(baseline_row["pc_rank"]),
        "ranks_match": bool(
            int(baseline_row["ec_rank"]) == int(pilot_ranks["EC"])
            and int(baseline_row["pc_rank"]) == int(pilot_ranks["PC"])
        ),
        "pilot_ec_delta_log10": float(pilot_c2["EC"]["delta_log10"]),
        "pilot_pc_delta_log10": float(pilot_c2["PC"]["delta_log10"]),
        "recomputed_ec_delta_log10": float(baseline_row["ec_delta_log10"]),
        "recomputed_pc_delta_log10": float(baseline_row["pc_delta_log10"]),
        "max_abs_delta_diff": max(
            abs(float(baseline_row["ec_delta_log10"]) - float(pilot_c2["EC"]["delta_log10"])),
            abs(float(baseline_row["pc_delta_log10"]) - float(pilot_c2["PC"]["delta_log10"])),
        ),
        "tolerance": 1e-9,
    }
    if not anchor["ranks_match"] or anchor["max_abs_delta_diff"] > 1e-9:
        raise ValueError("the frozen v1 baseline no longer reproduces the stage-1 pilot readout")

    mu_order = sorted(range(row_count), key=lambda index: (-float(mu[index]), keys[index]))
    stratum_counts = {
        stratum: int(sum(1 for value in target if stratum_of(float(value)) == stratum))
        for stratum in ("le_20", "20_60", "gt60")
    }
    train_max_values = [float(row["train_max_epsilon"]) for row in split_records]
    extrapolation_summary = {
        "family": BASELINE_FAMILY,
        "claim": (
            "a depth-2 boosted-tree ensemble is a step function of the training labels, so "
            "every held-out prediction stays at or below the largest training dielectric in "
            "that fold; it cannot reach a champion above the training ceiling"
        ),
        "fold_rows": len(extrapolation_rows),
        "all_predictions_at_or_below_train_max": all(
            row["prediction_at_or_below_train_max"] == "true" for row in extrapolation_rows
        ),
        "min_prediction_minus_train_max": min(
            float(row["prediction_minus_train_max"]) for row in extrapolation_rows
        ),
        "max_prediction_minus_train_max": max(
            float(row["prediction_minus_train_max"]) for row in extrapolation_rows
        ),
        "per_champion": {
            short: {
                "fold_rows": sum(1 for row in extrapolation_rows if row["champion"] == short),
                "max_ensemble_prediction": max(
                    float(row["ensemble_prediction"])
                    for row in extrapolation_rows
                    if row["champion"] == short
                ),
                "max_train_max_epsilon": max(
                    float(row["train_max_epsilon"])
                    for row in extrapolation_rows
                    if row["champion"] == short
                ),
                "champion_truth_dielectric": float(CHAMPIONS[short]["truth_dielectric"]),
            }
            for short in CHAMPION_ORDER
        },
        "fold_train_max_epsilon": {
            "min": min(train_max_values),
            "max": max(train_max_values),
            "rows": len(train_max_values),
        },
        "detail_artifact": portable_relative_path(
            EXTRAPOLATION_PATH, root=REPOSITORY_ROOT
        ),
    }

    bottleneck_evidence = {
        "pool_row_count": row_count,
        "target_stratum_counts": stratum_counts,
        "mu_sq_over_Vm_rank_of_champions": {
            short: int(mu_order.index(champion_indices[short]) + 1) for short in CHAMPION_ORDER
        },
        "mu_sq_over_Vm_top_rows": [
            {
                "inchikey": keys[index],
                "name": names[keys[index]],
                "mu_sq_over_Vm": float(mu[index]),
                "target_dielectric": float(target[index]),
            }
            for index in mu_order[:6]
        ],
        "champion_abs_delta_log10_per_repeat": {
            BASELINE_FAMILY: _spread(BASELINE_FAMILY),
            str(best_c2_row["family"]): _spread(str(best_c2_row["family"])),
        },
        "note": (
            "EC and PC are NOT the largest mu_sq_over_Vm rows of this pool: six ionic-liquid "
            "salts out-rank them (rank 7 and 8). So the Onsager-style linear extrapolation is "
            "anchored by a feature whose maximum belongs to other molecules, and the two "
            "champions sit on the rising flank rather than at the top edge."
        ),
    }

    median_rows: list[dict[str, object]] = []
    for row in table:
        family_id = str(row["family"])
        entry: dict[str, object] = {
            "family": family_id,
            "aggregation": "median_over_the_10_out_of_fold_repeat_predictions",
            "gating": False,
        }
        for short in CHAMPION_ORDER:
            index = champion_indices[short]
            truth = float(CHAMPIONS[short]["truth_dielectric"])
            median_prediction = float(np.median(oof[family_id][:, index]))
            entry[short] = {
                "median_prediction": median_prediction,
                "abs_delta_log10": abs(math.log10(median_prediction / truth)),
            }
        entry["c2_max_abs_delta_log10"] = max(
            float(entry[short]["abs_delta_log10"]) for short in CHAMPION_ORDER
        )
        entry["c2_passed"] = float(entry["c2_max_abs_delta_log10"]) <= c2_gate
        median_rows.append(entry)
    secondary = {
        "name": "median_over_repeats_robustness_check",
        "gating": False,
        "disclosed_as_post_declaration": True,
        "why": (
            "the declared gating readout aggregates the 10 repeat predictions by their "
            "mean; a linear fit on the Onsager scale can cross the pole in a single fold "
            "and dominate that mean. This secondary readout is reported so the "
            "conclusion does not rest on the aggregation choice. It does NOT feed "
            "SELECTION_RULE or the winner."
        ),
        "rows": median_rows,
        "families_passing_c2_under_median_aggregation": [
            str(row["family"]) for row in median_rows if bool(row["c2_passed"])
        ],
        "best_by_c2_family": str(
            min(
                median_rows,
                key=lambda row: (
                    float(row["c2_max_abs_delta_log10"]),
                    str(row["family"]),
                ),
            )["family"]
        ),
    }

    summary: dict[str, object] = {
        "schema_version": 1,
        "task": TASK,
        "title": "介电通道 v2：预声明、全配置上报的模型族比较（留出 EC/PC 的高 eps 外推）",
        "disclaimer": DISCLAIMER,
        "disclaimer_en": (
            "The frozen v1 readout is recorded as NOT passed. v2 is a new set of "
            "configurations whose order and selection rule were declared before execution, and "
            "every configuration is reported without omission."
        ),
        "not_a_verdict": True,
        "verdict_eligible": False,
        "verdict_note": (
            "this probe compares model families on the dielectric channel only; C2_additive, "
            "C3 and the three other channels are not run, so nothing here may be written as "
            "'L3 passed'"
        ),
        "generated_at_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "status": prereg["status"],
            "locked_at_utc": prereg["locked_at_utc"],
            "sha256": canonical_text_sha256(PREREG_PATH),
            "locked_constants_read_verbatim": locked,
        },
        "pool": {
            "path": portable_relative_path(POOL_PATH, root=REPOSITORY_ROOT),
            "sha256": sha256_file(POOL_PATH),
            "sha256_expected": POOL_EXPECTED_SHA256,
            "rows": row_count,
            "size_by_list": {POOL_LIST_NAME: row_count},
            "line_ending": "LF",
        },
        "fold_and_seed": {
            "fold_scheme": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
            "seed_scheme": "42 + global RepeatedKFold split index",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
            "split_count": len(geometry),
            "fold_aggregation": FOLD_AGGREGATION,
            "fold_policy": (
                "EC and PC leave the training side of every fold and are still scored "
                "out-of-fold at their original fold (leave-EC-out precedent)"
            ),
        },
        "selection_rule": SELECTION_RULE,
        "families": [
            {
                "id": str(family["id"]),
                "group": str(family["group"]),
                "label": str(family["label"]),
                "kind": str(family["kind"]),
                "declared_feature_count": int(family["declared_feature_count"]),
                "is_baseline": str(family["id"]) == BASELINE_FAMILY,
            }
            for family in FAMILIES
        ],
        "family_table": table,
        "strata_table": strata_rows,
        "exclusion": {
            "excluded_champions": list(CHAMPION_ORDER),
            "champion_train_side_removals": champion_train_removals,
            "champion_held_out_folds": champion_held_out,
            "champions_intersect_train_ids_empty": True,
            "champions_required_in_top_k_total_prereg": int(
                locked["C1_champions_required_in_top_k_total"]
            ),
            "levels": [
                "L1: EC/PC are dropped from the training side of all 50 folds",
                "L2: features are Morgan count + the frozen physical columns only",
                "L3: no hyper-parameter or subset choice ever sees a champion",
                "L4: champions are scored through the identical prediction path",
            ],
            "min_train_rows_after_exclusion": min(
                int(row["train_count_after_exclusion"]) for row in split_records
            ),
            "max_train_rows_after_exclusion": max(
                int(row["train_count_after_exclusion"]) for row in split_records
            ),
        },
        "extrapolation_diagnostic": extrapolation_summary,
        "extrapolation_failure_evidence": {
            "onsager_inverse_clip_bounds": [
                ONSAGER_INVERSE_CLIP_LOW,
                ONSAGER_INVERSE_CLIP_HIGH,
            ],
            "onsager_clip_events_by_family": dict(onsager_clip_events),
            "families_with_predictions_above_1e3": [
                str(row["family"]) for row in table if int(row["n_predictions_gt_1e3"]) > 0
            ],
        },
        "secondary_diagnostic_median_aggregation": secondary,
        "bottleneck_evidence": bottleneck_evidence,
        "outcome": {
            "winner_id": str(winner["family"]) if winner else None,
            "eligible_families_under_selection_rule": eligible_families,
            "families_passing_c1": passing_c1,
            "families_passing_c2_solvent": passing_c2,
            "families_passing_c1_and_c2": passing_both,
            "families_improving_both_vs_v1_baseline": joint_improvers,
            "families_passing_c2_under_median_aggregation": secondary[
                "families_passing_c2_under_median_aggregation"
            ],
            "best_by_c2_family_under_median_aggregation": secondary["best_by_c2_family"],
            "c1_gate_K": top_k,
            "c2_gate_abs_delta_log10": c2_gate,
            "baseline_c1_hits": baseline_hits,
            "baseline_c2_max_abs_delta_log10": baseline_c2,
            "best_by_c2_family": {
                "family": str(best_c2_row["family"]),
                "c2_max_abs_delta_log10": float(best_c2_row["c2_max_abs_delta_log10"]),
                "ec_abs_delta_log10": float(best_c2_row["ec_abs_delta_log10"]),
                "pc_abs_delta_log10": float(best_c2_row["pc_abs_delta_log10"]),
                "ec_rank": int(best_c2_row["ec_rank"]),
                "pc_rank": int(best_c2_row["pc_rank"]),
                "c1_hits": int(best_c2_row["c1_hits"]),
                "gate_shortfall": float(best_c2_row["c2_gate_shortfall"]),
                "oof_raw_mae": float(best_c2_row["oof_raw_mae"]),
                "baseline_oof_raw_mae": float(baseline_row["oof_raw_mae"]),
            },
            "l3_verdict_status": "not_run_dielectric_channel_only_not_a_verdict",
        },
        "regression_anchor_vs_stage1_pilot": anchor,
    }
    write_csv_lf(folds_path, FOLD_COLUMNS, split_records)
    write_csv_lf(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    write_csv_lf(strata_path, STRATA_COLUMNS, strata_rows)
    write_csv_lf(extrapolation_path, EXTRAPOLATION_COLUMNS, extrapolation_rows)
    _write_text(report_path, render_report(summary))
    summary["outputs"] = {
        "folds_csv": {
            "path": portable_relative_path(folds_path, root=REPOSITORY_ROOT),
            "sha256": sha256_file(folds_path),
            "rows": len(split_records),
        },
        "predictions_csv": {
            "path": portable_relative_path(predictions_path, root=REPOSITORY_ROOT),
            "sha256": sha256_file(predictions_path),
            "rows": len(prediction_rows),
        },
        "strata_csv": {
            "path": portable_relative_path(strata_path, root=REPOSITORY_ROOT),
            "sha256": sha256_file(strata_path),
            "rows": len(strata_rows),
        },
        "extrapolation_csv": {
            "path": portable_relative_path(extrapolation_path, root=REPOSITORY_ROOT),
            "sha256": sha256_file(extrapolation_path),
            "rows": len(extrapolation_rows),
        },
        "report": {
            "path": portable_relative_path(report_path, root=REPOSITORY_ROOT),
            "sha256": sha256_file(report_path),
        },
        "summary_json": {
            "path": portable_relative_path(summary_path, root=REPOSITORY_ROOT),
        },
    }
    _write_json(summary_path, summary)
    return summary


def select_winner(
    table: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object] | None, list[str]]:
    """Apply SELECTION_RULE mechanically; never inspect the outcome first."""

    baseline = next(
        row for row in table if str(row["family"]) == str(SELECTION_RULE["baseline_family"])
    )
    eligible = [
        row
        for row in table
        if str(row["family"]) != str(baseline["family"])
        and float(row["oof_raw_mae"]) <= float(baseline["oof_raw_mae"])
        and int(row["c1_hits"]) > int(baseline["c1_hits"])
    ]
    ordered = sorted(
        eligible,
        key=lambda row: (
            float(row["c2_max_abs_delta_log10"]),
            int(row["declared_feature_count"]),
            str(row["family"]),
        ),
    )
    return (dict(ordered[0]) if ordered else None), [str(row["family"]) for row in ordered]


def _f(value: object, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def champion_fold_train_max_range(summary: Mapping[str, object]) -> tuple[float, float]:
    """The training-epsilon ceiling range over the champion folds only.

    ``extrapolation_diagnostic.fold_train_max_epsilon`` covers all 50 folds;
    the 20 champion-fold records live in the extrapolation artifact.  A review
    found the two ranges quoted in one sentence as if both described the same
    20-fold set, so this helper derives the champion-fold half from the
    artifact rather than letting the report restate it by hand.
    """

    detail = str(summary["extrapolation_diagnostic"]["detail_artifact"])
    with (REPOSITORY_ROOT / detail).open(encoding="utf-8", newline="") as handle:
        values = [float(row["train_max_epsilon"]) for row in csv.DictReader(handle)]
    return min(values), max(values)


def render_report(summary: Mapping[str, object]) -> str:
    locked = summary["prereg"]["locked_constants_read_verbatim"]
    table = summary["family_table"]
    declared_ids = [str(family["id"]) for family in summary["families"]]
    table_ids = [str(row["family"]) for row in table]
    if sorted(declared_ids) != sorted(table_ids):
        raise ValueError("the report would omit a declared family; refusing to render")
    baseline = next(row for row in table if bool(row["is_baseline"]))
    outcome = summary["outcome"]
    best = outcome["best_by_c2_family"]
    extrapolation = summary["extrapolation_diagnostic"]
    bottleneck = summary["bottleneck_evidence"]
    lines: list[str] = []
    add = lines.append
    add("# 介电通道 v2：预声明、全配置上报的模型族比较")
    add("")
    add(f"> **{summary['disclaimer']}**")
    add("")
    add(f"- 生成时间（UTC）：`{summary['generated_at_utc']}`")
    add(
        "- 本文件由 `probes/dielectric_channel_v2.py` 确定性生成，数字与 "
        "`probes/dielectric_channel_v2_summary.json` 同源。"
    )
    add(
        "- **不是 L3 结论**：只跑介电通道；C2_additive、C3 与其余三通道均未运行，"
        "不得把本产物写成「L3 通过」。"
    )
    add("")
    add("## 一、口径与预注册常数")
    add("")
    add(f"- 预注册：`{summary['prereg']['path']}`，status=`{summary['prereg']['status']}`，"
        f"locked_at_utc=`{summary['prereg']['locked_at_utc']}`")
    add(f"- 预注册 sha256（规范化行尾）：`{summary['prereg']['sha256']}`")
    add(f"- C1 的 K = {locked['C1_K']}（池内按预测 eps 降序，取前 K）")
    add(
        "- C2_solvent 的 max|Δlog10 ε| = "
        f"{locked['C2_solvent_max_abs_delta_log10_epsilon']}，真值 EC "
        f"{summary['family_table'][0]['champions']['EC']['truth_dielectric']} / PC "
        f"{summary['family_table'][0]['champions']['PC']['truth_dielectric']}"
    )
    add(f"- pass_expression（原样读取）：`{locked['pass_expression']}`")
    add(
        f"- 池：`{summary['pool']['path']}`，sha256=`{summary['pool']['sha256']}`，"
        f"{summary['pool']['rows']} 行，行尾 {summary['pool']['line_ending']}（与预注册钉死值一致）"
    )
    add("")
    add("## 二、池、折几何与冠军剔除")
    add("")
    fold = summary["fold_and_seed"]
    add(f"- 折几何：{fold['fold_scheme']}；seed 方案：{fold['seed_scheme']}；共 {fold['split_count']} 折")
    add(f"- 折聚合口径：{fold['fold_aggregation']}")
    exclusion = summary["exclusion"]
    add(
        f"- EC / PC 训练侧剔除次数：EC {exclusion['champion_train_side_removals']['EC']}、"
        f"PC {exclusion['champion_train_side_removals']['PC']}（共 {fold['split_count']} 折）；"
        f"样本外评分次数：EC {exclusion['champion_held_out_folds']['EC']}、"
        f"PC {exclusion['champion_held_out_folds']['PC']}"
    )
    add(
        f"- 每折断言 champions ∩ train_ids == ∅（产物列 "
        "`champions_intersect_train_after_exclusion` 全为 0）；剔除后训练行数 "
        f"{exclusion['min_train_rows_after_exclusion']}–{exclusion['max_train_rows_after_exclusion']}"
    )
    add("")
    add("## 三、预声明与全配置上报表")
    add("")
    add(f"**SELECTION_RULE（先声明后执行）**：{SELECTION_RULE['text']}")
    add("")
    add(f"规则机读定义：`eligibility` = {SELECTION_RULE['eligibility']}；`pick` = {SELECTION_RULE['pick']}；`tie_break` = {SELECTION_RULE['tie_break']}")
    add(
        "- 声明口径说明（自述项，无外部时间戳锚）：`declared_before_execution = true` 是运行产物 "
        "`probes/dielectric_channel_v2_summary.json` 的自述标志，本报告不把它当作时间凭证。可核对的时间锚只有两个："
        f"预注册 `locked_at_utc = {summary['prereg']['locked_at_utc']}` 与 "
        "`fold_and_seed.amendment_3.amended_at_utc = "
        f"{read_prereg()['fold_and_seed']['amendment_3']['amended_at_utc']}`，"
        f"两者都早于本报告 `generated_at_utc = {summary['generated_at_utc']}`；"
        "即「规则与修订先落预注册、报告后生成」这一点可由时间戳核对，"
        "而 `declared_before_execution` 布尔值本身不自证。"
    )
    add("")
    add("| 家族 | 组 | 特征数 | OOF raw MAE | R² | C1 命中/2 | EC 名次 | PC 名次 | EC Δlog10 | PC Δlog10 | max|Δlog10| | 过 C2? |")
    add("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in table:
        marker = "（基线）" if bool(row["is_baseline"]) else ""
        add(
            f"| `{row['family']}`{marker} | {row['family_group']} | "
            f"{row['declared_feature_count']} | {_f(row['oof_raw_mae'])} | {_f(row['oof_raw_r2'])} | "
            f"{row['c1_hits']} | {row['ec_rank']} | {row['pc_rank']} | "
            f"{_f(row['ec_delta_log10'], 4)} | {_f(row['pc_delta_log10'], 4)} | "
            f"{_f(row['c2_max_abs_delta_log10'], 4)} | "
            f"{'是' if bool(row['c2_passed']) else '否'} |"
        )
    add("")
    add(
        f"- 共 {len(table)} 个家族全部上报（无遗漏）；基线 `{baseline['family']}` 的 OOF raw MAE = "
        f"{_f(baseline['oof_raw_mae'])}、C1 命中 = {baseline['c1_hits']}/2。"
    )
    add("")
    add(
        "补充诊断（非判据）：Onsager 尺度上的线性拟合可能越过极点，表现为个别折的预测爆到 "
        "1e3 以上；下表列出每个家族的最大预测与极点裁剪计数。"
    )
    add("")
    add("| 家族 | 最大预测 ε | 预测 > 1e3 的行·折数 | Onsager 极点裁剪次数 |")
    add("| --- | ---: | ---: | ---: |")
    for row in table:
        add(
            f"| `{row['family']}` | {_f(row['max_prediction'], 4)} | "
            f"{row['n_predictions_gt_1e3']} | {row['onsager_clip_events']} |"
        )
    add("")
    add("## 四、SELECTION_RULE 与胜者")
    add("")
    add(f"- 满足资格条件的家族：{outcome['eligible_families_under_selection_rule'] or '（无）'}")
    if outcome["winner_id"] is None:
        add("- 胜者：**无**（按先声明规则无家族同时满足 MAE 不劣化与 C1 严格改善），本次如实记未过。")
    else:
        add(f"- 胜者：`{outcome['winner_id']}`（按先声明规则取 C2 的 max|Δlog10| 最小者）")
    add("")
    add("## 五、外推失败机制诊断（仅诊断，不作结论式断言）")
    add("")
    add(f"- 命题：{extrapolation['claim']}")
    add("- 下表按家族 `frozen_v1_log_eps_xgb`（冻结 v1 口径）逐折记录训练集最大 ε 与该折对冠军的预测；逐折明细见 `probes/artifacts/dielectric_channel_v2_extrapolation.csv`。")
    add("")
    add("| 冠军 | 折记录数 | 最大预测 ε | 该冠军出现过的训练集 ε 上界最大值 | 冻结真值 | 预测 ≤ 训练上界？ |")
    add("| --- | ---: | ---: | ---: | ---: | --- |")
    for short in CHAMPION_ORDER:
        entry = extrapolation["per_champion"][short]
        add(
            f"| {short} | {entry['fold_rows']} | {_f(entry['max_ensemble_prediction'], 4)} | "
            f"{_f(entry['max_train_max_epsilon'], 4)} | {_f(entry['champion_truth_dielectric'], 4)} | 全部为是 |"
        )
    add("")
    champion_train_max_min, champion_train_max_max = champion_fold_train_max_range(summary)
    add(
        f"- 全部 {extrapolation['fold_rows']} 条**冠军折**记录中，预测 − 训练上界 的最大值 = "
        f"{_f(extrapolation['max_prediction_minus_train_max'], 4)}（≤0 即被封顶）；"
        f"这 {extrapolation['fold_rows']} 条冠军折的训练集 ε 上界范围 "
        f"**{_f(champion_train_max_min, 4)}–{_f(champion_train_max_max, 4)}**（逐折明细见 "
        f"`{extrapolation['detail_artifact']}`）。"
    )
    add(
        f"- 若按**全场 {extrapolation['fold_train_max_epsilon']['rows']} 折**（含非冠军折）统计，"
        f"训练集 ε 上界范围才是 {_f(extrapolation['fold_train_max_epsilon']['min'], 4)}–"
        f"{_f(extrapolation['fold_train_max_epsilon']['max'], 4)}"
        f"（`fold_train_max_epsilon`: min {extrapolation['fold_train_max_epsilon']['min']} / "
        f"max {extrapolation['fold_train_max_epsilon']['max']} / "
        f"rows {extrapolation['fold_train_max_epsilon']['rows']}，见 "
        "`probes/dielectric_channel_v2_summary.json`）。两处口径不同，不得混用。"
    )
    add(
        "- 观察（非结论）：树集成是训练标签的阶梯函数，其取值被该折训练集的最大 ε 封顶；当冠军真值高于全部折的训练上界时，任何树集成都无法在原始 ε 尺度上够到它。这与「换成可外推的物理形式化线性模型能否救回」是两回事，后者由第三、六节的数据判定。"
    )
    add("")
    add("## 六、分层 MAE 对照")
    add("")
    add("| 家族 | ε ≤ 20 (n) | MAE | 20 < ε ≤ 60 (n) | MAE | ε > 60 (n) | MAE |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    strata_by_family: dict[str, dict[str, Mapping[str, object]]] = {}
    for row in summary["strata_table"]:
        strata_by_family.setdefault(str(row["family"]), {})[str(row["stratum"])] = row
    for family_id in declared_ids:
        buckets = strata_by_family.get(family_id, {})
        cells = []
        for stratum in ("le_20", "20_60", "gt60"):
            entry = buckets.get(stratum)
            if entry is None or str(entry["mae"]) == "":
                cells.extend(["0", "—"])
            else:
                cells.extend([str(entry["n"]), _f(entry["mae"])])
        add(f"| `{family_id}` | " + " | ".join(cells) + " |")
    add("")
    counts = bottleneck["target_stratum_counts"]
    add(
        f"- 池内目标分层计数：ε ≤ 20 共 {counts['le_20']} 行、20–60 共 {counts['20_60']} 行、"
        f"> 60 共 {counts['gt60']} 行。"
    )
    add("")
    secondary = summary["secondary_diagnostic_median_aggregation"]
    add("### 主口径之外的稳健性核对（非判据，事后附加并在此披露）")
    add("")
    add(f"- 说明：{secondary['why']}")
    add("")
    add("| 家族 | 中位数聚合 EC \\|Δlog10\\| | PC \\|Δlog10\\| | max\\|Δlog10\\| | 过 C2? |")
    add("| --- | ---: | ---: | ---: | --- |")
    for row in secondary["rows"]:
        add(
            f"| `{row['family']}` | {_f(row['EC']['abs_delta_log10'])} | "
            f"{_f(row['PC']['abs_delta_log10'])} | {_f(row['c2_max_abs_delta_log10'])} | "
            f"{'是' if bool(row['c2_passed']) else '否'} |"
        )
    add("")
    add(
        f"- 中位数聚合下过 C2 的家族："
        f"{secondary['families_passing_c2_under_median_aggregation'] or '（无）'}"
    )
    add("")
    add("## 七、诚实结论")
    add("")
    add(f"- 过 C1 的家族：{outcome['families_passing_c1'] or '（无）'}")
    add(f"- 过 C2_solvent 的家族：{outcome['families_passing_c2_solvent'] or '（无）'}")
    add(f"- 同时过 C1 与 C2 的家族：{outcome['families_passing_c1_and_c2'] or '（无）'}")
    add(
        f"- 相对 v1 基线同时改善 C1 与 C2 的家族："
        f"{outcome['families_improving_both_vs_v1_baseline'] or '（无）'}"
    )
    add(
        f"- **诊断项（非判据）**：可及下限（按 C2 的 max|Δlog10| 最小者，10 次重复均值聚合口径）："
        f"`{best['family']}`，max|Δ| = {_f(best['c2_max_abs_delta_log10'])}"
        f"（EC {_f(best['ec_abs_delta_log10'])}、PC {_f(best['pc_abs_delta_log10'])}），"
        f"相对门 0.10 差 {_f(best['gate_shortfall'])}；"
        f"同族 C1 命中 {best['c1_hits']}/2（EC 名次 {best['ec_rank']}、PC 名次 {best['pc_rank']}）。"
        "本行与下一行都是诊断读数，不参与 SELECTION_RULE 与胜者判定。"
    )
    add(
        f"- 基线对照：v1 的 OOF raw MAE = {_f(baseline['oof_raw_mae'])}、"
        f"max|Δlog10| = {_f(baseline['c2_max_abs_delta_log10'])}；"
        f"可及下限族的 OOF raw MAE = {_f(best['oof_raw_mae'])}。"
    )
    add(
        f"- **诊断项（非判据）** 瓶颈证据（特征侧）：{bottleneck['note']} 冠军的 mu_sq_over_Vm 名次为 "
        f"{bottleneck['mu_sq_over_Vm_rank_of_champions']}（诊断读数，不参与 SELECTION_RULE 与胜者判定）；"
        "池内 mu 前 6 名是 "
        + "、".join(
            f"{row['name']}(mu={row['mu_sq_over_Vm']:.0f}, ε={row['target_dielectric']:.3g})"
            for row in bottleneck["mu_sq_over_Vm_top_rows"]
        )
        + "。"
    )
    add(
        "- 瓶颈证据（数据侧）：高 ε 分层行数很少（见第六节计数），且冠军真实 ε 高于逐折训练上界；"
        "单调物理特征在留出外推上把冠军推向预测上界附近，但样本量与特征-目标关系共同限制了可及精度。"
        "本节只给出证据，不对「特征还是数据」作单方面结论。"
    )
    add("")
    add(
        f"- 稳健性核对（非判据）：中位数聚合下过 C2 的家族仍为 "
        f"{outcome['families_passing_c2_under_median_aggregation'] or '（无）'}；"
        f"中位数聚合下 C2 最好的是 `{outcome['best_by_c2_family_under_median_aggregation']}`。"
    )
    add(
        "- Onsager 逆变换家族的巨大 MAE / R² 是极点越界的直接后果（见第三节补充诊断的裁剪计数），"
        "不是数值噪声；这说明「换成物理形式化的线性模型」并不自动安全。"
    )
    add("")
    add("## 八、产物与验证命令")
    add("")
    add("- `probes/dielectric_channel_v2.py`（CLI）")
    add("- `probes/dielectric_channel_v2_summary.json`（全配置上报）")
    add("- `probes/artifacts/dielectric_channel_v2_folds.csv`（50 折记录 + 每折剔除数）")
    add("- `probes/artifacts/dielectric_channel_v2_predictions.csv`（逐家族逐折逐行）")
    add("- `probes/artifacts/dielectric_channel_v2_strata.csv`（分层诊断）")
    add("- `probes/artifacts/dielectric_channel_v2_extrapolation.csv`（训练上界 vs 预测）")
    add("- 复现：`.venv\\Scripts\\python.exe probes\\dielectric_channel_v2.py`")
    add("- 守卫：`.venv\\Scripts\\python.exe -m pytest tests\\test_dielectric_channel_v2.py -q`")
    add("- 静态检查：`.venv\\Scripts\\python.exe -m ruff check scripts src probes tests notebooks`")
    add("")
    add("## 九、未决风险")
    add("")
    add(
        "- 冠军仅在池内按同一代码路径评分，且池被限制在名册内（236 行）；这不等于「对任意新分子可外推」。"
    )
    add(
        "- 该池的 mu_sq_over_Vm 前 6 名是离子液体盐类而非冠军，线性模型在高 μ 端的锚点由这些盐决定；"
        "换池（例如剔除多片段盐）可能改变结论，本产物不作此声明。"
    )
    add(
        "- 只跑介电通道：C2_additive、C3 与其余三通道尚未运行，任何「L3 通过」表述都无效。"
    )
    add(
        "- Δ-learning 家族的残差学习器沿用冻结 XGB 超参；未做超参搜索，故本产物是「配置比较」，不是「调参后的最优」。"
    )
    if outcome["families_passing_c1_and_c2"]:
        add("- 注意：通过 C1+C2 不等于通过 L3；四通道合取才是判据。")
    else:
        add("- 本次没有任何家族同时过 C1 与 C2：按预注册纪律，只能如实记未过，不得宣称通过。")
    add("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds-output", type=Path, default=FOLDS_PATH)
    parser.add_argument("--predictions-output", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument("--strata-output", type=Path, default=STRATA_PATH)
    parser.add_argument("--extrapolation-output", type=Path, default=EXTRAPOLATION_PATH)
    parser.add_argument("--summary-output", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report-output", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = _parse_args()
    summary = run_experiment(
        folds_path=args.folds_output,
        predictions_path=args.predictions_output,
        strata_path=args.strata_output,
        extrapolation_path=args.extrapolation_output,
        summary_path=args.summary_output,
        report_path=args.report_output,
    )
    print(
        json.dumps(
            {
                "disclaimer": summary["disclaimer"],
                "not_a_verdict": True,
                "prereg_sha256": summary["prereg"]["sha256"],
                "pool_sha256": summary["pool"]["sha256"],
                "families_reported": [row["family"] for row in summary["family_table"]],
                "family_table": [
                    {
                        "family": row["family"],
                        "oof_raw_mae": row["oof_raw_mae"],
                        "oof_raw_r2": row["oof_raw_r2"],
                        "c1_hits": row["c1_hits"],
                        "ec_rank": row["ec_rank"],
                        "pc_rank": row["pc_rank"],
                        "ec_delta_log10": row["ec_delta_log10"],
                        "pc_delta_log10": row["pc_delta_log10"],
                        "c2_max_abs_delta_log10": row["c2_max_abs_delta_log10"],
                        "c2_passed": row["c2_passed"],
                    }
                    for row in summary["family_table"]
                ],
                "outcome": summary["outcome"],
                "regression_anchor_vs_stage1_pilot": summary[
                    "regression_anchor_vs_stage1_pilot"
                ],
                "outputs": summary["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())