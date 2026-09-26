"""P4 redox baseline v2: enriched (structure-derived + IP/EA) feature probe.

``probes/p4_redox_baseline.py`` (v1) fitted every target with a *single*
pre-registered feature -- ``IP`` for ``oxidation_free_energy`` and ``EA`` for
``reduction_free_energy`` -- and the frozen gate stayed red
(``probes/p4_redox_summary.json`` -> ``gate.passed == false``).  This v2 probe
leaves those anchors untouched and asks a narrower question:

    does a richer feature set (structure-derived descriptors + low-order
    ``IP``/``EA`` interactions) move the frozen 0.15 eV gate?

Two evaluation protocols are reported side by side:

(a) the pre-registered held-out split -- the very same 314/78 partition that
    ``probes/p4_redox_summary.json`` used, so the reading is directly
    comparable with ``gate.best_model_mae``;
(b) the project standard ``RepeatedKFold(n_splits=5, n_repeats=10,
    random_state=42)`` protocol with per-fold model seed ``42 + global fold``,
    recording one CSV row per ``(model, repeat, fold)`` in the style of
    ``data/processed/dielectric_gpr_repeated_cv.csv``.

The two free-energy label columns may never be used as features.  Any
``oxidation_free_energy`` / ``reduction_free_energy`` derived quantity
(``ox + red``, ``ox - red``, ...) is label leakage and is rejected at runtime by
``assert_no_label_leakage``.

The probe starts by re-deriving the v1 anchors (the 78-row held-out id hash and
the ``oxidation_free_energy`` ``linear`` MAE / R^2) and raises before writing
anything if either drifts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors
from sklearn.dummy import DummyRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_gpr_baseline import deterministic_split
from probes.p4_redox_baseline import (
    FP_SIZE,
    GATE_MAE_THRESHOLD,
    RX_SOURCE_ROWS,
    SPLIT_SEED,
    TARGET_FEATURES,
    TEST_FRACTION,
    _morgan_count_features,
    regression_metrics,
)

DATA_SOURCE = "RX-392"
TARGETS = ("oxidation_free_energy", "reduction_free_energy")
LABEL_COLUMNS = ("oxidation_free_energy", "reduction_free_energy")

# Anchors inherited from ``probes/p4_redox_summary.json`` (v1).  They are
# re-derived on every run and a mismatch aborts the probe.
EXPECTED_TEST_ID_HASH = "dba15cd8c3a99215cc3e1fd5b2a73b9a5c0275eb2ee41fba436bcf62f2d2daee"
EXPECTED_V1_OXIDATION_LINEAR_MAE = 0.2905180517963865
EXPECTED_V1_OXIDATION_LINEAR_R2 = 0.9443164629360373
ANCHOR_TOLERANCE = 1e-9

# Feature contract.  ``free_energy`` may not appear in a feature name at all.
FORBIDDEN_FEATURE_NAMES = (
    "oxidation_free_energy",
    "reduction_free_energy",
    "ox_plus_red",
    "ox_minus_red",
    "sum_free_energy",
    "delta_free_energy",
)
FORBIDDEN_FEATURE_SUBSTRING = "free_energy"

INTERACTION_FEATURE_NAMES = ("IP_times_EA", "IP_squared", "EA_squared")
RDKIT_2D_FEATURE_NAMES = (
    "MolWt",
    "TPSA",
    "MolLogP",
    "RingCount",
    "NumHDonors",
    "NumHAcceptors",
    "NumRotatableBonds",
    "FractionCSP3",
)
COMPACT_FEATURE_NAMES = ("IP", "EA", *INTERACTION_FEATURE_NAMES, *RDKIT_2D_FEATURE_NAMES)

RIDGE_ALPHAS = tuple(float(alpha) for alpha in np.logspace(-2.0, 4.0, 25))
CV_SPLITS = 5
CV_REPEATS = 10
CV_SEED = 42
LEARNING_CURVE_SIZES = (100, 200, 300, 392)
LEARNING_CURVE_REPEATS = 3

MODEL_NAMES = (
    "linear_scalar",
    "ridge_enriched",
    "gpr_enriched",
    "xgb_enriched",
    "xgb_structure_only",
    "dummy_mean",
)
GATE_CANDIDATE_MODELS = (
    "linear_scalar",
    "ridge_enriched",
    "gpr_enriched",
    "xgb_enriched",
    "xgb_structure_only",
)
MODEL_CONFIGS = {
    "linear_scalar": (
        "LinearRegression on the single pre-registered feature "
        "(IP for oxidation_free_energy, EA for reduction_free_energy); "
        "identical estimator to probes/p4_redox_baseline.py:linear"
    ),
    "ridge_enriched": (
        "StandardScaler + RidgeCV(alphas=logspace(-2, 4, 25), cv=None -> exact "
        "leave-one-out GCV) on the enriched matrix "
        "(IP, EA, low-order IP/EA interactions, RDKit 2D, Morgan count r=2 n=2048)"
    ),
    "gpr_enriched": (
        "StandardScaler + GaussianProcessRegressor("
        "ConstantKernel(1.0)*RBF(length_scale=1.0)+WhiteKernel(noise_level=1e-3), "
        "alpha=1e-6, normalize_y=True, n_restarts_optimizer=2, random_state=seed) "
        "on the 13-dim compact matrix (no Morgan)"
    ),
    "xgb_enriched": (
        "XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, "
        "subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, tree_method=hist, "
        "random_state=seed) on the enriched matrix"
    ),
    "xgb_structure_only": (
        "same XGBRegressor on RDKit 2D + Morgan count only (no IP/EA); "
        "ablation control for the pre-registered features"
    ),
    "dummy_mean": (
        "DummyRegressor(strategy=mean) on the enriched matrix; shares the "
        "identical folds and is a chance-level control, never a gate candidate"
    ),
}

FOLD_COLUMNS = (
    "model",
    "target",
    "seed",
    "repeat",
    "fold",
    "n_train",
    "n_test",
    "train_id_hash",
    "test_id_hash",
    "mae",
    "rmse",
    "r2",
)
PREDICTION_COLUMNS = (
    "row_id",
    "target",
    "model",
    "split",
    "repeat",
    "fold",
    "used_for_metrics",
    "target_value",
    "prediction",
    "abs_error",
)
LEARNING_CURVE_COLUMNS = (
    "model",
    "target",
    "train_size",
    "repeat",
    "fold",
    "n_train",
    "n_test",
    "train_id_hash",
    "test_id_hash",
    "mae",
    "rmse",
    "r2",
)

def morgan_feature_names(fp_size: int = FP_SIZE) -> tuple[str, ...]:
    return tuple(f"morgan_{index}" for index in range(fp_size))


def assert_no_label_leakage(feature_names: Sequence[str]) -> None:
    """Reject any feature name that smells like a free-energy label derivative."""

    for name in feature_names:
        if name in FORBIDDEN_FEATURE_NAMES or FORBIDDEN_FEATURE_SUBSTRING in name:
            raise ValueError(
                f"feature {name!r} is label-derived and may not be used as an input; "
                f"forbidden names: {FORBIDDEN_FEATURE_NAMES}"
            )
        for label in LABEL_COLUMNS:
            if label in name or name in label:
                raise ValueError(f"feature {name!r} collides with label column {label!r}")


@dataclass(frozen=True)
class FeatureBundle:
    """Recipe-derived feature views over the 392 RX-392 rows."""

    names: tuple[str, ...]
    compact: np.ndarray
    structure_only: np.ndarray
    enriched: np.ndarray
    scalar_columns: Mapping[str, np.ndarray]

    def for_model(self, model_name: str, target_name: str) -> np.ndarray:
        if model_name == "linear_scalar":
            return self.scalar_columns[target_name]
        if model_name == "xgb_structure_only":
            return self.structure_only
        if model_name == "gpr_enriched":
            return self.compact
        return self.enriched


def _rdkit_2d_descriptors(smiles: str) -> list[float]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES for RDKit 2D descriptors: {smiles!r}")
    return [
        float(Descriptors.MolWt(molecule)),
        float(rdMolDescriptors.CalcTPSA(molecule)),
        float(Descriptors.MolLogP(molecule)),
        float(rdMolDescriptors.CalcNumRings(molecule)),
        float(rdMolDescriptors.CalcNumHBD(molecule)),
        float(rdMolDescriptors.CalcNumHBA(molecule)),
        float(rdMolDescriptors.CalcNumRotatableBonds(molecule)),
        float(rdMolDescriptors.CalcFractionCSP3(molecule)),
    ]


def read_rx_rows(path: Path) -> list[dict[str, str]]:
    """Read the RX-392 slice of the frozen merged CSV (never written here)."""

    if not path.exists():
        raise FileNotFoundError(f"merged redox CSV is missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["source"] == DATA_SOURCE]
    if len(rows) != RX_SOURCE_ROWS:
        raise ValueError(f"expected {RX_SOURCE_ROWS} {DATA_SOURCE} rows, found {len(rows)}")
    for row in rows:
        for field in (*LABEL_COLUMNS, "IP", "EA"):
            value = float(row[field])
            if not np.isfinite(value):
                raise ValueError(f"non-finite {field} for {row['row_id']}")
    return rows


def build_feature_matrix(rows: Sequence[Mapping[str, str]]) -> FeatureBundle:
    """Build the compact / structure-only / enriched feature views."""

    smiles = [str(row["smiles"]) for row in rows]
    ip = np.asarray([float(row["IP"]) for row in rows], dtype=float)
    ea = np.asarray([float(row["EA"]) for row in rows], dtype=float)
    interactions = np.column_stack([ip * ea, ip * ip, ea * ea])
    descriptors = np.asarray([_rdkit_2d_descriptors(value) for value in smiles], dtype=float)
    morgan = np.asarray(_morgan_count_features(smiles), dtype=float)

    compact = np.column_stack([ip, ea, interactions, descriptors])
    structure_only = np.hstack([descriptors, morgan])
    enriched = np.hstack([compact, morgan])
    names = (*COMPACT_FEATURE_NAMES, *morgan_feature_names(morgan.shape[1]))
    assert_no_label_leakage(names)
    if enriched.shape[1] != len(names):
        raise ValueError(
            f"feature matrix width {enriched.shape[1]} != {len(names)} feature names"
        )
    return FeatureBundle(
        names=names,
        compact=compact,
        structure_only=structure_only,
        enriched=enriched,
        scalar_columns={
            target_name: np.asarray(
                [float(row[TARGET_FEATURES[target_name]]) for row in rows], dtype=float
            ).reshape(-1, 1)
            for target_name in TARGETS
        },
    )


def make_model(model_name: str, seed: int) -> object:
    if model_name == "linear_scalar":
        return LinearRegression()
    if model_name == "ridge_enriched":
        return make_pipeline(StandardScaler(), RidgeCV(alphas=RIDGE_ALPHAS))
    if model_name == "gpr_enriched":
        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=1e-3)
        return make_pipeline(
            StandardScaler(),
            GaussianProcessRegressor(
                kernel=kernel,
                alpha=1e-6,
                normalize_y=True,
                n_restarts_optimizer=2,
                random_state=seed,
            ),
        )
    if model_name in ("xgb_enriched", "xgb_structure_only"):
        return XGBRegressor(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            tree_method="hist",
            n_jobs=4,
            random_state=seed,
            verbosity=0,
        )
    if model_name == "dummy_mean":
        return DummyRegressor(strategy="mean")
    raise ValueError(f"unknown enriched redox model: {model_name}")


def fit_predict(
    model_name: str,
    features: np.ndarray,
    target: np.ndarray,
    train_indices: Sequence[int],
    test_indices: Sequence[int],
    *,
    seed: int,
) -> np.ndarray:
    model = make_model(model_name, seed)
    model.fit(features[np.asarray(train_indices)], target[np.asarray(train_indices)])
    return np.asarray(model.predict(features[np.asarray(test_indices)]), dtype=float)


def _index_hash(row_ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(str(row_ids[int(index)]) for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    """Write LF-terminated CSV on every platform."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")

def evaluate_heldout(
    bundle: FeatureBundle,
    target_name: str,
    target: np.ndarray,
    row_ids: Sequence[str],
    train_indices: np.ndarray,
    test_indices: np.ndarray,
) -> tuple[dict[str, dict[str, float]], list[dict[str, object]], dict[str, str]]:
    """Fit every model on the 314-row train split and score the 78-row held-out split."""

    metrics: dict[str, dict[str, float]] = {}
    prediction_rows: list[dict[str, object]] = []
    configs: dict[str, str] = {}
    for model_name in MODEL_NAMES:
        features = bundle.for_model(model_name, target_name)
        model = make_model(model_name, SPLIT_SEED)
        model.fit(features[train_indices], target[train_indices])
        prediction = np.asarray(model.predict(features), dtype=float)
        metrics[model_name] = regression_metrics(target[test_indices], prediction[test_indices])
        if isinstance(model, LinearRegression) and features.shape[1] == 1:
            configs[model_name] = (
                f"{MODEL_CONFIGS[model_name]}; coefficients={model.coef_.tolist()}; "
                f"intercept={float(model.intercept_)}"
            )
        elif model_name == "ridge_enriched":
            configs[model_name] = (
                f"{MODEL_CONFIGS[model_name]}; selected_alpha={float(model[-1].alpha_)}"
            )
        else:
            configs[model_name] = MODEL_CONFIGS[model_name]
        train_set = {int(index) for index in train_indices}
        for row_index, row_id in enumerate(row_ids):
            split = "heldout_train" if row_index in train_set else "heldout_test"
            prediction_rows.append(
                {
                    "row_id": row_id,
                    "target": target_name,
                    "model": model_name,
                    "split": split,
                    "repeat": "",
                    "fold": "",
                    "used_for_metrics": "false" if split == "heldout_train" else "true",
                    "target_value": f"{target[row_index]:.12g}",
                    "prediction": f"{prediction[row_index]:.12g}",
                    "abs_error": f"{abs(target[row_index] - prediction[row_index]):.12g}",
                }
            )
    return metrics, prediction_rows, configs


def run_repeated_cv(
    bundle: FeatureBundle,
    target_name: str,
    target: np.ndarray,
    row_ids: Sequence[str],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    model_names: Sequence[str] = MODEL_NAMES,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, float]]]:
    """Run the frozen 5x10 RepeatedKFold grid; every model shares the same folds."""

    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    repeat_count = len(folds) // CV_SPLITS
    per_repeat: dict[str, list[list[float]]] = {
        name: [[] for _ in range(repeat_count)] for name in model_names
    }
    for global_index, (train_indices, test_indices) in enumerate(folds):
        repeat = global_index // CV_SPLITS
        fold = global_index % CV_SPLITS
        for model_name in model_names:
            features = bundle.for_model(model_name, target_name)
            prediction = fit_predict(
                model_name,
                features,
                target,
                train_indices,
                test_indices,
                seed=CV_SEED + global_index,
            )
            fold_rows.append(
                {
                    "model": model_name,
                    "target": target_name,
                    "seed": CV_SEED + global_index,
                    "repeat": repeat,
                    "fold": fold,
                    "n_train": len(train_indices),
                    "n_test": len(test_indices),
                    "train_id_hash": _index_hash(row_ids, train_indices),
                    "test_id_hash": _index_hash(row_ids, test_indices),
                    **regression_metrics(target[test_indices], prediction),
                }
            )
            per_repeat[model_name][repeat].extend(
                float(value) for value in np.abs(target[test_indices] - prediction)
            )
            for row_index, predicted in zip(test_indices, prediction, strict=True):
                row_index = int(row_index)
                prediction_rows.append(
                    {
                        "row_id": row_ids[row_index],
                        "target": target_name,
                        "model": model_name,
                        "split": "cv_test",
                        "repeat": repeat,
                        "fold": fold,
                        "used_for_metrics": "true",
                        "target_value": f"{target[row_index]:.12g}",
                        "prediction": f"{float(predicted):.12g}",
                        "abs_error": f"{abs(target[row_index] - float(predicted)):.12g}",
                    }
                )
    metrics: dict[str, dict[str, float]] = {}
    for model_name in model_names:
        repeat_mae = np.asarray(
            [np.mean(values) for values in per_repeat[model_name] if values], dtype=float
        )
        fold_mae = np.asarray(
            [float(row["mae"]) for row in fold_rows if row["model"] == model_name],
            dtype=float,
        )
        metrics[model_name] = {
            "mae_mean": float(np.mean(repeat_mae)),
            "mae_std": float(np.std(repeat_mae, ddof=1)),
            "fold_mae_mean": float(np.mean(fold_mae)),
            "fold_mae_std": float(np.std(fold_mae, ddof=1)),
        }
    return fold_rows, prediction_rows, metrics


def train_residual_mae(
    bundle: FeatureBundle,
    target_name: str,
    target: np.ndarray,
    *,
    model_names: Sequence[str] = (
        "linear_scalar",
        "ridge_enriched",
        "gpr_enriched",
        "xgb_enriched",
    ),
) -> dict[str, float]:
    """In-sample MAE of the same recipe fitted on all 392 rows (capacity ceiling)."""

    residuals: dict[str, float] = {}
    for model_name in model_names:
        features = bundle.for_model(model_name, target_name)
        model = make_model(model_name, SPLIT_SEED)
        model.fit(features, target)
        prediction = np.asarray(model.predict(features), dtype=float)
        residuals[model_name] = float(np.mean(np.abs(target - prediction)))
    return residuals


def run_learning_curve(
    bundle: FeatureBundle,
    target_names: Sequence[str],
    targets: Mapping[str, np.ndarray],
    row_ids: Sequence[str],
    *,
    model_names: Sequence[str] = ("linear_scalar", "xgb_enriched"),
    sizes: Sequence[int] = LEARNING_CURVE_SIZES,
    repeats: int = LEARNING_CURVE_REPEATS,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, float]]]]:
    """Reduced-budget RepeatedKFold curve over deterministic training subsets."""

    rows: list[dict[str, object]] = []
    summary: dict[str, list[dict[str, float]]] = {name: [] for name in target_names}
    for size in sizes:
        subset = np.random.default_rng(CV_SEED).permutation(len(row_ids))[: int(size)]
        splitter = RepeatedKFold(n_splits=CV_SPLITS, n_repeats=repeats, random_state=CV_SEED)
        folds = list(splitter.split(np.zeros(len(subset))))
        subset_ids = [row_ids[int(index)] for index in subset]
        for target_name in target_names:
            target = targets[target_name]
            for model_name in model_names:
                features = bundle.for_model(model_name, target_name)[subset]
                target_subset = target[subset]
                per_repeat: list[list[float]] = [[] for _ in range(repeats)]
                for global_index, (train_indices, test_indices) in enumerate(folds):
                    prediction = fit_predict(
                        model_name,
                        features,
                        target_subset,
                        train_indices,
                        test_indices,
                        seed=CV_SEED + global_index,
                    )
                    repeat = global_index // CV_SPLITS
                    per_repeat[repeat].extend(
                        float(value)
                        for value in np.abs(target_subset[test_indices] - prediction)
                    )
                    rows.append(
                        {
                            "model": model_name,
                            "target": target_name,
                            "train_size": int(size),
                            "repeat": repeat,
                            "fold": global_index % CV_SPLITS,
                            "n_train": len(train_indices),
                            "n_test": len(test_indices),
                            "train_id_hash": _index_hash(subset_ids, train_indices),
                            "test_id_hash": _index_hash(subset_ids, test_indices),
                            **regression_metrics(target_subset[test_indices], prediction),
                        }
                    )
                repeat_mae = np.asarray(
                    [np.mean(values) for values in per_repeat], dtype=float
                )
                summary[target_name].append(
                    {
                        "model": model_name,
                        "train_size": int(size),
                        "mae_mean": float(np.mean(repeat_mae)),
                        "mae_std": float(np.std(repeat_mae, ddof=1)),
                    }
                )
    return rows, summary

def run_probe(
    *,
    merged_path: Path,
    summary_path: Path,
    folds_path: Path,
    predictions_path: Path,
    learning_curve_path: Path,
    with_learning_curve: bool = True,
) -> dict[str, object]:
    RDLogger.DisableLog("rdApp.*")
    rows = read_rx_rows(merged_path)
    row_ids = [str(row["row_id"]) for row in rows]
    bundle = build_feature_matrix(rows)
    targets = {
        target_name: np.asarray([float(row[target_name]) for row in rows], dtype=float)
        for target_name in TARGETS
    }

    train_indices, test_indices = deterministic_split(
        len(rows), test_fraction=TEST_FRACTION, seed=SPLIT_SEED
    )
    reproduced_hash = _index_hash(row_ids, test_indices)
    if reproduced_hash != EXPECTED_TEST_ID_HASH:
        raise ValueError(
            f"pre-registered held-out split drifted: {reproduced_hash} != {EXPECTED_TEST_ID_HASH}"
        )

    heldout_metrics: dict[str, dict[str, dict[str, float]]] = {}
    heldout_configs: dict[str, str] = {}
    prediction_rows: list[dict[str, object]] = []
    for target_name in TARGETS:
        metrics, target_rows, configs = evaluate_heldout(
            bundle, target_name, targets[target_name], row_ids, train_indices, test_indices
        )
        heldout_metrics[target_name] = metrics
        prediction_rows.extend(target_rows)
        for model_name, config in configs.items():
            heldout_configs[f"{target_name}:{model_name}"] = config

    # Anchor #2: the v1 single-feature linear oxidation model must reproduce bit-for-bit.
    anchor_mae = heldout_metrics["oxidation_free_energy"]["linear_scalar"]["mae"]
    anchor_r2 = heldout_metrics["oxidation_free_energy"]["linear_scalar"]["r2"]
    if (
        abs(anchor_mae - EXPECTED_V1_OXIDATION_LINEAR_MAE) > ANCHOR_TOLERANCE
        or abs(anchor_r2 - EXPECTED_V1_OXIDATION_LINEAR_R2) > ANCHOR_TOLERANCE
    ):
        raise ValueError(
            f"v1 oxidation linear anchor drifted: mae={anchor_mae!r} r2={anchor_r2!r}"
        )

    folds = list(
        RepeatedKFold(n_splits=CV_SPLITS, n_repeats=CV_REPEATS, random_state=CV_SEED).split(
            np.zeros(len(rows))
        )
    )
    fold_rows: list[dict[str, object]] = []
    cv_metrics: dict[str, dict[str, dict[str, float]]] = {}
    for target_name in TARGETS:
        target_fold_rows, target_prediction_rows, metrics = run_repeated_cv(
            bundle, target_name, targets[target_name], row_ids, folds
        )
        fold_rows.extend(target_fold_rows)
        prediction_rows.extend(target_prediction_rows)
        cv_metrics[target_name] = metrics

    residuals = {
        target_name: train_residual_mae(bundle, target_name, targets[target_name])
        for target_name in TARGETS
    }

    learning_rows: list[dict[str, object]] = []
    learning_summary: dict[str, list[dict[str, float]]] = {}
    if with_learning_curve:
        learning_rows, learning_summary = run_learning_curve(bundle, TARGETS, targets, row_ids)

    heldout_best = {
        target_name: min(
            GATE_CANDIDATE_MODELS,
            key=lambda name: heldout_metrics[target_name][name]["mae"],
        )
        for target_name in TARGETS
    }
    heldout_best_mae = {
        target_name: heldout_metrics[target_name][heldout_best[target_name]]["mae"]
        for target_name in TARGETS
    }
    cv_best = {
        target_name: min(
            GATE_CANDIDATE_MODELS,
            key=lambda name: cv_metrics[target_name][name]["mae_mean"],
        )
        for target_name in TARGETS
    }
    cv_best_mae = {
        target_name: cv_metrics[target_name][cv_best[target_name]]["mae_mean"]
        for target_name in TARGETS
    }
    heldout_passed = all(value < GATE_MAE_THRESHOLD for value in heldout_best_mae.values())
    cv_passed = all(value < GATE_MAE_THRESHOLD for value in cv_best_mae.values())

    max_capacity_mae = max(residuals[target_name]["xgb_enriched"] for target_name in TARGETS)
    if heldout_passed:
        bottleneck = "none: the frozen 0.15 eV gate is met on the pre-registered held-out split"
    elif max_capacity_mae < GATE_MAE_THRESHOLD:
        bottleneck = (
            "sample_size: the enriched model reaches "
            f"{max_capacity_mae:.4f} eV in-sample on all {len(rows)} rows (capacity is far below "
            f"the {GATE_MAE_THRESHOLD} eV gate) yet stays at "
            f"{max(heldout_best_mae.values()):.4f} eV held-out, so the ceiling is the "
            f"{len(rows)} labelled rows, not the model"
        )
    else:
        bottleneck = (
            "model_capacity: even in-sample the best enriched model only reaches "
            f"{max_capacity_mae:.4f} eV, above the {GATE_MAE_THRESHOLD} eV gate"
        )
    summary: dict[str, object] = {
        "schema_version": 1,
        "probe": "p4_redox_v2_enriched",
        "inputs": {
            "merged_csv": merged_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "merged_sha256": canonical_text_sha256(merged_path),
            "source_filter": DATA_SOURCE,
            "rows": len(rows),
            "label_columns": list(LABEL_COLUMNS),
            "note": (
                "Batt-P30K rows carry no free-energy labels and are excluded from "
                "training; only the 392 RX-392 rows are used."
            ),
        },
        "anchors": {
            "v1_summary": "probes/p4_redox_summary.json",
            "expected_test_id_hash": EXPECTED_TEST_ID_HASH,
            "reproduced_test_id_hash": reproduced_hash,
            "expected_v1_oxidation_linear": {
                "mae": EXPECTED_V1_OXIDATION_LINEAR_MAE,
                "r2": EXPECTED_V1_OXIDATION_LINEAR_R2,
            },
            "reproduced_v1_oxidation_linear": {"mae": anchor_mae, "r2": anchor_r2},
            "tolerance": ANCHOR_TOLERANCE,
            "matches": True,
        },
        "split": {
            "method": "deterministic permutation",
            "seed": SPLIT_SEED,
            "test_fraction": TEST_FRACTION,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "test_id_hash": reproduced_hash,
        },
        "features": {
            "forbidden_feature_names": list(FORBIDDEN_FEATURE_NAMES),
            "forbidden_feature_substring": FORBIDDEN_FEATURE_SUBSTRING,
            "leakage_guard": "passed",
            "feature_names": list(bundle.names),
            "views": {
                "compact": {"count": int(bundle.compact.shape[1])},
                "structure_only": {"count": int(bundle.structure_only.shape[1])},
                "enriched": {"count": int(bundle.enriched.shape[1])},
            },
            "groups": {
                "pre_registered": ["IP", "EA"],
                "low_order_interactions": list(INTERACTION_FEATURE_NAMES),
                "rdkit_2d": list(RDKIT_2D_FEATURE_NAMES),
                "morgan_count": f"radius=2, fpSize={FP_SIZE}, count fingerprint",
            },
        },
        "model_configs": heldout_configs,
        "heldout": {
            "protocol": (
                "deterministic_split(392, test_fraction=0.2, seed=42) -> 314 train / 78 test; "
                "identical to probes/p4_redox_summary.json"
            ),
            "metrics": heldout_metrics,
            "train_residual_mae": residuals,
        },
        "repeated_cv": {
            "splitter": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
            "protocol": (
                "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42); "
                "per-fold model seed = 42 + global fold index"
            ),
            "n_splits": CV_SPLITS,
            "n_repeats": CV_REPEATS,
            "seed": CV_SEED,
            "fold_count": len(folds),
            "metrics": cv_metrics,
        },
        "dummy_control": {
            "model": "dummy_mean",
            "shared_folds": True,
            "heldout_mae": {
                target_name: heldout_metrics[target_name]["dummy_mean"]["mae"]
                for target_name in TARGETS
            },
            "repeated_cv_mae": {
                target_name: cv_metrics[target_name]["dummy_mean"]["mae_mean"]
                for target_name in TARGETS
            },
        },
        "gate": {
            "threshold_mae": GATE_MAE_THRESHOLD,
            "unit": "eV",
            "criterion": "best model per target has held-out MAE below threshold",
            "protocol": "pre-registered held-out split (78 rows)",
            "best_model": heldout_best,
            "best_model_mae": heldout_best_mae,
            "per_target": {
                target_name: {
                    "mae": heldout_best_mae[target_name],
                    "passed": bool(heldout_best_mae[target_name] < GATE_MAE_THRESHOLD),
                }
                for target_name in TARGETS
            },
            "passed": heldout_passed,
        },
        "gate_repeated_cv": {
            "threshold_mae": GATE_MAE_THRESHOLD,
            "unit": "eV",
            "criterion": "best model per target has repeated-CV mean MAE below threshold",
            "protocol": "RepeatedKFold(5, 10, seed=42), fold seeds 42..91",
            "best_model": cv_best,
            "best_model_mae": cv_best_mae,
            "best_model_mae_std": {
                target_name: cv_metrics[target_name][cv_best[target_name]]["mae_std"]
                for target_name in TARGETS
            },
            "per_target": {
                target_name: {
                    "mae": cv_best_mae[target_name],
                    "passed": bool(cv_best_mae[target_name] < GATE_MAE_THRESHOLD),
                }
                for target_name in TARGETS
            },
            "passed": cv_passed,
        },
        "verdict": {
            "gate_passed": heldout_passed,
            "gate_passed_repeated_cv": cv_passed,
            "bottleneck": bottleneck,
        },
        "outputs": {
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "folds_csv": folds_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "learning_curve_csv": (
                learning_curve_path.relative_to(REPOSITORY_ROOT).as_posix()
                if with_learning_curve
                else None
            ),
            "report": "reports/p4_redox_v2_enriched.md",
        },
    }
    if with_learning_curve:
        summary["learning_curve"] = {
            "protocol": (
                f"deterministic subsample of {len(rows)} rows (seed 42) x "
                f"RepeatedKFold(n_splits={CV_SPLITS}, n_repeats={LEARNING_CURVE_REPEATS}, "
                f"random_state={CV_SEED}); models = linear_scalar, xgb_enriched"
            ),
            "sizes": [int(size) for size in LEARNING_CURVE_SIZES],
            "summary": learning_summary,
        }

    _write_csv(folds_path, fold_rows, FOLD_COLUMNS)
    _write_csv(predictions_path, prediction_rows, PREDICTION_COLUMNS)
    if with_learning_curve:
        _write_csv(learning_curve_path, learning_rows, LEARNING_CURVE_COLUMNS)
    _write_json(summary_path, summary)
    return summary

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--merged",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "redox_merged.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p4_redox_v2_summary.json",
    )
    parser.add_argument(
        "--folds-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_repeated_cv.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_predictions.csv",
    )
    parser.add_argument(
        "--learning-curve-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts" / "p4_redox_v2_learning_curve.csv",
    )
    parser.add_argument(
        "--skip-learning-curve",
        action="store_true",
        help="skip the reduced-budget learning curve (faster local runs)",
    )
    args = parser.parse_args(argv)
    summary = run_probe(
        merged_path=args.merged,
        summary_path=args.summary,
        folds_path=args.folds_output,
        predictions_path=args.predictions_output,
        learning_curve_path=args.learning_curve_output,
        with_learning_curve=not args.skip_learning_curve,
    )
    print(
        json.dumps(
            {"gate": summary["gate"], "gate_repeated_cv": summary["gate_repeated_cv"]},
            indent=2,
        )
    )
    print(json.dumps({"verdict": summary["verdict"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())