"""L3 exit 2: HOMO/LUMO/IP/EA structure-to-property models for Batt-P30K.

Manual appendix Q-2 asks for four structure-to-property models (HOMO, LUMO, IP, EA)
reusing the P2 pipeline on Batt-P30K, with an acceptance gate of MAE <= 0.2 eV, and a
self-contained scoring entry point (``models/homo_lumo_baselines.json``) plus a
``--score-smiles`` CLI that the screening funnel can actually call.

Two hard constraints drive the design:

* **L1 exclusion** (``probes/l3_backvalidation_prereg.json`` ->
  ``exclusion_levels[0]``): no fit may have a champion in its training rows,
  including every cross-validation fold's training side.  The champions are removed
  from the modelling pool and every fold re-asserts ``champions & train_ids == {}``.
* **Structure-only features**: Morgan count fingerprint (radius 2, 2048 bits) plus
  pure 2D RDKit descriptors.  The DFT label family (``gap``, ``homo``, ``lumo``,
  ``ip``, ``ea``, ``dipole``, ``quadrupole``, ``ener*``, ``coord``) may never enter
  the feature path; the only HDF5 dataset the feature path reads is ``smiles``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import functools
import hashlib
import json
import os
import platform
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import rdkit
import sklearn
import xgboost
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdFingerprintGenerator
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import RepeatedKFold
from xgboost import XGBRegressor

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

H5_RELATIVE_PATH = "data/raw/batt/Batt-P30K.h5"
PREREG_RELATIVE_PATH = "probes/l3_backvalidation_prereg.json"
P4_SUMMARY_RELATIVE_PATH = "probes/p4_redox_summary.json"
CACHE_RELATIVE_PATH = "data/processed/l3_homo_lumo_features.npz"
SCREENING_RELATIVE_PATH = "probes/homo_lumo_baselines_screening.json"
SUMMARY_RELATIVE_PATH = "probes/homo_lumo_baselines_summary.json"
BASELINES_RELATIVE_PATH = "models/homo_lumo_baselines.json"
FOLD_CSV_RELATIVE_PATH = "data/processed/l3_homo_lumo_repeated_cv.csv"
PREDICTIONS_CSV_RELATIVE_PATH = "data/processed/l3_homo_lumo_cv_predictions.csv"
MODEL_ARTIFACT_DIR = "models"

FEATURE_SCHEMA_VERSION = 1
BASELINES_SCHEMA_VERSION = 1

MORGAN_RADIUS = 2
MORGAN_FP_SIZE = 2048

DESCRIPTOR_NAMES: tuple[str, ...] = (
    "MolWt",
    "MolLogP",
    "TPSA",
    "LabuteASA",
    "NumHDonors",
    "NumHAcceptors",
    "NumHeteroatoms",
    "NOCount",
    "NumRotatableBonds",
    "NumValenceElectrons",
    "NumAliphaticRings",
    "NumAromaticRings",
    "NumSaturatedRings",
    "RingCount",
    "FractionCSP3",
    "HeavyAtomCount",
    "BalabanJ",
    "BertzCT",
    "Chi0v",
    "Chi1v",
    "HallKierAlpha",
    "Ipc",
    "Kappa1",
    "Kappa2",
    "Kappa3",
    "MaxPartialCharge",
    "MinPartialCharge",
    "MaxAbsPartialCharge",
    "MinAbsPartialCharge",
    "PEOE_VSA1",
)

TARGET_DATASETS: dict[str, str] = {"HOMO": "homo", "LUMO": "lumo", "IP": "ip", "EA": "ea"}
TARGET_ORDER: tuple[str, ...] = ("HOMO", "LUMO", "IP", "EA")
LABEL_DATASETS: tuple[str, ...] = tuple(TARGET_DATASETS.values())

# The feature path is allowed to read exactly one HDF5 dataset.  Everything else in a
# Batt-P30K group is either a label or a DFT-derived quantity.
FEATURE_SOURCE_H5_DATASETS: tuple[str, ...] = ("smiles",)
FORBIDDEN_FEATURE_INPUTS: tuple[str, ...] = (
    "gap",
    "homo",
    "lumo",
    "ip",
    "ea",
    "dipole",
    "quadrupole",
    "ener",
    "ener_anion",
    "ener_cation",
    "coord",
)

CV_SPLITS = 5
CV_REPEATS = 10
CV_SEED = 42
SCREEN_REPEATS = 1

# Compute grid order: the cheapest, most likely to pass target first so that an
# interrupted run still leaves the most informative partial artifact behind.
FORMAL_RUN_ORDER: tuple[str, ...] = ("LUMO", "HOMO", "IP", "EA")
XGB_N_JOBS = max(8, min(os.cpu_count() or 8, 8))

GATE_MAE_THRESHOLD = 0.2
GATE_UNIT = "eV"
GATE_CRITERION = (
    "per-target selected main model mean fold MAE strictly below 0.2 eV on the formal "
    "RepeatedKFold(5, 10, random_state=42) protocol; the 'all four pass' criterion "
    "additionally requires every one of HOMO/LUMO/IP/EA to pass"
)

SELECTION_TIE_TOLERANCE = 1e-3
SELECTION_RULE = (
    "Declared before any fit: for each target independently, rank the pre-declared "
    "screening configurations by mean held-out MAE over the screening folds "
    "(RepeatedKFold n_splits=5, n_repeats=1, random_state=42; every configuration and "
    "the DummyRegressor control share identical folds). The winner must be strictly "
    "better than the DummyRegressor(strategy='mean') mean MAE on the same folds; if no "
    "configuration beats Dummy the lowest-MAE configuration is still reported with "
    "beat_dummy=false. Candidates within 1e-3 eV of the best MAE are treated as tied "
    "and the tie is broken by (1) fewer features, then (2) the declared model-variant "
    "order. Configurations are screened in the declared order regardless of outcome."
)

P2_XGB_PARAMS: dict[str, Any] = {
    "objective": "reg:squarederror",
    "n_estimators": 800,
    "max_depth": 10,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.6,
    "reg_lambda": 1.0,
    "tree_method": "hist",
}

MODEL_VARIANTS: dict[str, dict[str, Any]] = {
    "p2_xgboost": P2_XGB_PARAMS,
    "deeper_slower": {
        "objective": "reg:squarederror",
        "n_estimators": 1000,
        "max_depth": 12,
        "learning_rate": 0.04,
        "subsample": 0.9,
        "colsample_bytree": 0.5,
        "reg_lambda": 1.0,
        "tree_method": "hist",
    },
}
MODEL_VARIANT_ORDER: tuple[str, ...] = ("p2_xgboost", "deeper_slower")

NON_FINITE_DESCRIPTOR_POLICY = (
    "non-finite descriptor values are replaced by 0.0 by the same code path at fit "
    "time and at scoring time"
)


class CacheMismatchError(RuntimeError):
    """Raised when a feature cache does not match its source or configuration."""


class DatasetSchemaError(ValueError):
    """Raised when the Batt-P30K HDF5 schema is incomplete or inconsistent."""


class ChampionLeakError(RuntimeError):
    """Raised when a champion molecule would enter a training set (L1 violation)."""


class FeatureLeakError(RuntimeError):
    """Raised when a non-structural quantity would enter the feature path (L2)."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def id_block_sha256(identifiers: Sequence[str]) -> str:
    """Digest of a sorted identifier list, used for fold train/test fingerprints."""

    return sha256_text("\n".join(sorted(identifiers)))


def repo_path(path: Path) -> str:
    """Repository-relative POSIX path when possible, absolute path otherwise."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def decode_smiles(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def group_sort_key(name: str) -> tuple[int, str]:
    """Numeric ordering for ``CompMol{N}`` groups (the indices are not contiguous)."""

    prefix = "CompMol"
    if name.startswith(prefix):
        suffix = name[len(prefix) :]
        if suffix.isdigit():
            return int(suffix), name
    return 10**9, name


def regression_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if target.shape != prediction.shape or target.ndim != 1:
        raise ValueError("target and prediction must be one-dimensional and aligned")
    if not len(target):
        raise ValueError("metrics require at least one observation")
    r2 = float("nan")
    if len(target) > 1 and float(np.var(target)) > 0.0:
        r2 = float(r2_score(target, prediction))
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": r2,
    }


@dataclass(frozen=True, slots=True)
class FeatureVariant:
    name: str
    descriptor_names: tuple[str, ...]

    @property
    def n_features(self) -> int:
        return MORGAN_FP_SIZE + len(self.descriptor_names)


FEATURE_VARIANTS: dict[str, FeatureVariant] = {
    "morgan_only": FeatureVariant("morgan_only", ()),
    "morgan_plus_2d": FeatureVariant("morgan_plus_2d", DESCRIPTOR_NAMES),
}

SCREEN_COMBINATIONS: tuple[tuple[str, str], ...] = (
    ("morgan_only", "p2_xgboost"),
    ("morgan_plus_2d", "p2_xgboost"),
    ("morgan_plus_2d", "deeper_slower"),
)


def descriptor_functions(names: Sequence[str]) -> list[tuple[str, Callable[[Chem.Mol], float]]]:
    functions: list[tuple[str, Callable[[Chem.Mol], float]]] = []
    for name in names:
        function = getattr(Descriptors, name, None)
        if function is None or not callable(function):
            raise FeatureLeakError(f"unknown RDKit descriptor {name!r}")
        functions.append((name, function))
    return functions


def assert_structure_only_features() -> None:
    """Guard the feature allowlists against label/DFT-derived quantities (L2)."""

    declared = {name.lower() for name in DESCRIPTOR_NAMES}
    forbidden = {token.lower() for token in FORBIDDEN_FEATURE_INPUTS}
    overlap = sorted(declared & forbidden)
    if overlap:
        raise FeatureLeakError(f"declared features collide with forbidden inputs: {overlap}")
    if FEATURE_SOURCE_H5_DATASETS != ("smiles",):
        raise FeatureLeakError(
            "the feature path may only read the 'smiles' dataset, got "
            f"{FEATURE_SOURCE_H5_DATASETS!r}"
        )


def read_smiles_dataset(group: h5py.Group, key: str) -> str:
    """Read the single HDF5 dataset the feature path is allowed to touch."""

    dataset = FEATURE_SOURCE_H5_DATASETS[0]
    if dataset not in group:
        raise DatasetSchemaError(f"{key} is missing the {dataset} dataset")
    return decode_smiles(group[dataset][0])


def read_label_dataset(group: h5py.Group, key: str, dataset: str) -> float:
    if dataset not in LABEL_DATASETS:
        raise DatasetSchemaError(f"{dataset!r} is not a declared label dataset")
    if dataset not in group:
        raise DatasetSchemaError(f"{key} is missing the {dataset} dataset")
    value = np.asarray(group[dataset][...], dtype=float)
    if value.size != 1 or not np.isfinite(value).all():
        raise DatasetSchemaError(f"{key}/{dataset} must contain one finite value")
    return float(value.reshape(-1)[0])


def parse_molecules(smiles_values: Sequence[str]) -> list[Chem.Mol | None]:
    RDLogger.DisableLog("rdApp.*")
    return [Chem.MolFromSmiles(value) for value in smiles_values]


def morgan_count_features(molecules: Sequence[Chem.Mol]) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS,
        fpSize=MORGAN_FP_SIZE,
    )
    rows = [generator.GetCountFingerprintAsNumPy(molecule) for molecule in molecules]
    return np.vstack(rows).astype(np.float32, copy=False)


def descriptor_features(molecules: Sequence[Chem.Mol]) -> np.ndarray:
    functions = descriptor_functions(DESCRIPTOR_NAMES)
    rows = [
        [float(function(molecule)) for _, function in functions] for molecule in molecules
    ]
    return np.asarray(rows, dtype=np.float64)


def clean_descriptors(values: np.ndarray) -> np.ndarray:
    return np.nan_to_num(
        np.asarray(values, dtype=np.float64),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )


def featurize_smiles(smiles_values: Sequence[str], descriptor_names: Sequence[str]) -> np.ndarray:
    """Deterministic SMILES -> feature matrix used identically for fit and scoring."""

    molecules = parse_molecules(smiles_values)
    invalid = [index for index, molecule in enumerate(molecules) if molecule is None]
    if invalid:
        raise DatasetSchemaError(f"cannot parse SMILES at rows {invalid[:5]}")
    blocks = [morgan_count_features(molecules)]  # type: ignore[arg-type]
    if descriptor_names:
        if tuple(descriptor_names) == DESCRIPTOR_NAMES:
            block = descriptor_features(molecules)  # type: ignore[arg-type]
        else:
            block = np.asarray(
                [
                    [float(getattr(Descriptors, name)(molecule)) for name in descriptor_names]
                    for molecule in molecules
                ],
                dtype=np.float64,
            )
        blocks.append(block)
    return np.hstack([clean_descriptors(block) for block in blocks]).astype(
        np.float32,
        copy=False,
    )


def feature_config() -> dict[str, Any]:
    return {
        "fingerprint": {
            "kind": "morgan_count",
            "radius": MORGAN_RADIUS,
            "fp_size": MORGAN_FP_SIZE,
            "generator": "rdkit.Chem.rdFingerprintGenerator.GetMorganGenerator",
            "materializer": "GetCountFingerprintAsNumPy",
        },
        "descriptors": {
            "library": "rdkit.Chem.Descriptors",
            "names": list(DESCRIPTOR_NAMES),
            "non_finite_policy": NON_FINITE_DESCRIPTOR_POLICY,
        },
        "feature_order": (
            f"morgan_count({MORGAN_FP_SIZE}) then descriptors in the declared order"
        ),
        "variants": {
            name: {
                "descriptor_names": list(variant.descriptor_names),
                "n_features": variant.n_features,
            }
            for name, variant in FEATURE_VARIANTS.items()
        },
        "only_source": "SMILES (2D structure)",
        "h5_datasets_read_for_features": list(FEATURE_SOURCE_H5_DATASETS),
        "forbidden_inputs": list(FORBIDDEN_FEATURE_INPUTS),
    }


def _feature_config_json() -> str:
    return json.dumps(feature_config(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class FeatureBundle:
    morgan: np.ndarray
    descriptors: np.ndarray
    smiles: np.ndarray
    molecule_ids: np.ndarray
    inchikeys: np.ndarray
    targets: Mapping[str, np.ndarray]
    source_sha256: str
    source_group_count: int
    invalid_smiles_count: int
    non_finite_descriptor_count: int
    cache_status: str

    def matrix(self, variant: FeatureVariant) -> np.ndarray:
        base = clean_descriptors(self.morgan)
        if not variant.descriptor_names:
            return base.astype(np.float32, copy=False)
        columns = [DESCRIPTOR_NAMES.index(name) for name in variant.descriptor_names]
        block = clean_descriptors(self.descriptors)[:, columns]
        return np.hstack([base, block]).astype(np.float32, copy=False)


def _load_valid_cache(cache_path: Path, *, source_sha256: str) -> FeatureBundle | None:
    if not cache_path.exists():
        return None
    with np.load(cache_path, allow_pickle=False) as cached:
        required = {
            "schema_version",
            "feature_config_json",
            "source_sha256",
            "source_group_count",
            "invalid_smiles_count",
            "non_finite_descriptor_count",
            "morgan",
            "descriptors",
            "smiles",
            "molecule_ids",
            "inchikeys",
            "targets",
        }
        missing = sorted(required.difference(cached.files))
        if missing:
            raise CacheMismatchError(
                f"feature cache is missing metadata arrays: {', '.join(missing)}"
            )
        if int(cached["schema_version"]) != FEATURE_SCHEMA_VERSION:
            raise CacheMismatchError(
                "feature cache schema version mismatch: "
                f"{int(cached['schema_version'])} != {FEATURE_SCHEMA_VERSION}"
            )
        if str(cached["feature_config_json"].item()) != _feature_config_json():
            raise CacheMismatchError("feature cache configuration mismatch")
        if str(cached["source_sha256"].item()) != source_sha256:
            raise CacheMismatchError(
                "feature cache source SHA256 mismatch: "
                f"{cached['source_sha256'].item()} != {source_sha256}"
            )
        morgan = cached["morgan"]
        descriptors = cached["descriptors"]
        smiles = cached["smiles"]
        molecule_ids = cached["molecule_ids"]
        inchikeys = cached["inchikeys"]
        targets = cached["targets"]
        if morgan.ndim != 2 or morgan.shape[1] != MORGAN_FP_SIZE:
            raise CacheMismatchError(f"feature cache has invalid morgan shape {morgan.shape}")
        if descriptors.ndim != 2 or descriptors.shape[1] != len(DESCRIPTOR_NAMES):
            raise CacheMismatchError(
                f"feature cache has invalid descriptor shape {descriptors.shape}"
            )
        rows = morgan.shape[0]
        if not all(len(array) == rows for array in (descriptors, smiles, molecule_ids, inchikeys)):
            raise CacheMismatchError("feature cache arrays have inconsistent row counts")
        if targets.ndim != 2 or targets.shape[0] != rows or targets.shape[1] != len(TARGET_ORDER):
            raise CacheMismatchError(f"feature cache has invalid target shape {targets.shape}")
        return FeatureBundle(
            morgan=morgan,
            descriptors=descriptors,
            smiles=smiles,
            molecule_ids=molecule_ids,
            inchikeys=inchikeys,
            targets={
                target: np.asarray(targets[:, column], dtype=np.float64)
                for column, target in enumerate(TARGET_ORDER)
            },
            source_sha256=source_sha256,
            source_group_count=int(cached["source_group_count"]),
            invalid_smiles_count=int(cached["invalid_smiles_count"]),
            non_finite_descriptor_count=int(cached["non_finite_descriptor_count"]),
            cache_status="cache_hit",
        )


def build_feature_bundle(
    h5_path: Path,
    cache_path: Path,
    *,
    rebuild_cache: bool = False,
) -> FeatureBundle:
    assert_structure_only_features()
    source_sha256 = sha256_file(h5_path)
    if not rebuild_cache:
        cached = _load_valid_cache(cache_path, source_sha256=source_sha256)
        if cached is not None:
            return cached

    RDLogger.DisableLog("rdApp.*")
    smiles_values: list[str] = []
    molecule_ids: list[str] = []
    label_columns: dict[str, list[float]] = {target: [] for target in TARGET_ORDER}
    with h5py.File(h5_path, "r") as handle:
        keys = sorted(handle.keys(), key=group_sort_key)
        if not keys:
            raise DatasetSchemaError("Batt-P30K HDF5 file contains no molecule groups")
        for index, key in enumerate(keys, start=1):
            group = handle[key]
            if not isinstance(group, h5py.Group):
                raise DatasetSchemaError(f"{key} is not an HDF5 group")
            smiles_values.append(read_smiles_dataset(group, key))
            molecule_ids.append(key)
            for target, dataset in TARGET_DATASETS.items():
                label_columns[target].append(read_label_dataset(group, key, dataset))
            if index % 5000 == 0:
                print(f"read {index}/{len(keys)} groups", flush=True)

    molecules = parse_molecules(smiles_values)
    invalid_smiles = [index for index, molecule in enumerate(molecules) if molecule is None]
    if invalid_smiles:
        raise DatasetSchemaError(
            f"Batt-P30K contains {len(invalid_smiles)} unparsable SMILES rows"
        )
    parsed = [molecule for molecule in molecules if molecule is not None]
    morgan = morgan_count_features(parsed)
    raw_descriptors = descriptor_features(parsed)
    non_finite = int(np.count_nonzero(~np.isfinite(raw_descriptors)))
    descriptors = clean_descriptors(raw_descriptors)
    targets = np.column_stack(
        [np.asarray(label_columns[target], dtype=np.float64) for target in TARGET_ORDER]
    )
    inchikeys = np.asarray([Chem.MolToInchiKey(molecule) for molecule in parsed], dtype=str)
    smiles_array = np.asarray(smiles_values, dtype=str)
    molecule_id_array = np.asarray(molecule_ids, dtype=str)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        morgan=morgan,
        descriptors=descriptors.astype(np.float32),
        smiles=smiles_array,
        molecule_ids=molecule_id_array,
        inchikeys=inchikeys,
        targets=targets.astype(np.float32),
        schema_version=np.asarray(FEATURE_SCHEMA_VERSION, dtype=np.int32),
        feature_config_json=np.asarray(_feature_config_json()),
        source_sha256=np.asarray(source_sha256),
        source_group_count=np.asarray(len(keys), dtype=np.int32),
        invalid_smiles_count=np.asarray(0, dtype=np.int32),
        non_finite_descriptor_count=np.asarray(non_finite, dtype=np.int32),
    )
    print(f"built feature cache: {morgan.shape[0]} rows, non-finite descriptors {non_finite}")
    return FeatureBundle(
        morgan=morgan,
        descriptors=descriptors,
        smiles=smiles_array,
        molecule_ids=molecule_id_array,
        inchikeys=inchikeys,
        targets={target: targets[:, column] for column, target in enumerate(TARGET_ORDER)},
        source_sha256=source_sha256,
        source_group_count=len(keys),
        invalid_smiles_count=0,
        non_finite_descriptor_count=non_finite,
        cache_status="rebuilt",
    )
@dataclass(frozen=True, slots=True)
class FoldSpec:
    repeat: int
    fold: int
    index: int
    seed: int
    train: np.ndarray
    test: np.ndarray

    @property
    def label(self) -> str:
        return f"repeat={self.repeat} fold={self.fold}"


def cv_folds(
    row_count: int,
    *,
    splits: int = CV_SPLITS,
    repeats: int = CV_REPEATS,
    seed: int = CV_SEED,
) -> list[FoldSpec]:
    """RepeatedKFold folds with the project's per-fold seed convention (42 + index)."""

    if row_count < splits:
        raise ValueError("row_count must be at least the number of splits")
    splitter = RepeatedKFold(n_splits=splits, n_repeats=repeats, random_state=seed)
    placeholder = np.zeros((row_count, 1), dtype=np.float32)
    folds: list[FoldSpec] = []
    for index, (train, test) in enumerate(splitter.split(placeholder)):
        repeat, fold = divmod(index, splits)
        folds.append(
            FoldSpec(
                repeat=repeat,
                fold=fold,
                index=index,
                seed=seed + index,
                train=np.asarray(train, dtype=np.int64),
                test=np.asarray(test, dtype=np.int64),
            )
        )
    return folds


def exclude_champions(
    train_indices: np.ndarray,
    pool_inchikeys: np.ndarray,
    champion_inchikeys: frozenset[str],
) -> np.ndarray:
    """Drop champion rows from a fold's training side before any fit (prereg L1)."""

    train_indices = np.asarray(train_indices, dtype=np.int64)
    if not champion_inchikeys:
        return train_indices
    blocked = np.asarray(sorted(champion_inchikeys), dtype=str)
    keep = ~np.isin(pool_inchikeys[train_indices], blocked)
    return train_indices[keep]


def assert_champions_absent(
    train_inchikeys: np.ndarray,
    champion_inchikeys: frozenset[str],
    *,
    context: str,
) -> None:
    """Assert ``champions & train_ids == {}`` for one fold's training side."""

    leaked = sorted(set(np.asarray(train_inchikeys, dtype=str).tolist()) & champion_inchikeys)
    if leaked:
        raise ChampionLeakError(
            f"L1 violation: champion molecules are in the training rows of {context}: {leaked}"
        )


def build_model(variant: str, seed: int) -> XGBRegressor:
    if variant not in MODEL_VARIANTS:
        raise ValueError(f"unknown model variant {variant!r}")
    return XGBRegressor(
        n_jobs=XGB_N_JOBS,
        random_state=seed,
        **MODEL_VARIANTS[variant],
    )


class MeanDummyModel:
    """``DummyRegressor(strategy='mean')`` sharing the identical fold protocol."""

    def __init__(self) -> None:
        self.estimator = DummyRegressor(strategy="mean")

    def fit(self, features: np.ndarray, target: np.ndarray) -> MeanDummyModel:
        self.estimator.fit(np.zeros((len(target), 1), dtype=float), target)
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        return self.estimator.predict(np.zeros((len(features), 1), dtype=float))


@dataclass(slots=True)
class OofAccumulator:
    total: np.ndarray
    total_square: np.ndarray
    counts: np.ndarray

    @classmethod
    def empty(cls, size: int) -> OofAccumulator:
        return cls(
            total=np.zeros(size, dtype=np.float64),
            total_square=np.zeros(size, dtype=np.float64),
            counts=np.zeros(size, dtype=np.int64),
        )

    def add(self, index: np.ndarray, prediction: np.ndarray) -> None:
        prediction = np.asarray(prediction, dtype=np.float64)
        self.total[index] += prediction
        self.total_square[index] += prediction**2
        self.counts[index] += 1

    def mean(self) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(self.counts > 0, self.total / np.maximum(self.counts, 1), np.nan)

    def std(self) -> np.ndarray:
        mean = self.mean()
        with np.errstate(invalid="ignore", divide="ignore"):
            variance = self.total_square / np.maximum(self.counts, 1) - mean**2
        return np.sqrt(np.maximum(variance, 0.0))


FOLD_CSV_COLUMNS = (
    "model",
    "seed",
    "repeat",
    "fold",
    "n_train",
    "n_test",
    "train_sha",
    "test_sha",
    "mae",
    "rmse",
    "r2",
)


def evaluate_one_fold(
    features: np.ndarray,
    target: np.ndarray,
    spec: FoldSpec,
    *,
    label: str,
    make_model: Callable[[int], Any],
    pool_ids: np.ndarray,
    pool_inchikeys: np.ndarray,
    champion_inchikeys: frozenset[str],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    train = exclude_champions(spec.train, pool_inchikeys, champion_inchikeys)
    context = f"{label} {spec.label}"
    assert_champions_absent(pool_inchikeys[train], champion_inchikeys, context=context)
    if np.intersect1d(train, spec.test).size:
        raise ValueError(f"{context} has overlapping train and test rows")
    estimator = make_model(spec.seed)
    estimator.fit(features[train], target[train])
    prediction = np.asarray(estimator.predict(features[spec.test]), dtype=np.float64)
    metrics = regression_metrics(np.asarray(target[spec.test], dtype=np.float64), prediction)
    row = {
        "model": label,
        "seed": spec.seed,
        "repeat": spec.repeat,
        "fold": spec.fold,
        "n_train": len(train),
        "n_test": len(spec.test),
        "train_sha": id_block_sha256(pool_ids[train].tolist()),
        "test_sha": id_block_sha256(pool_ids[spec.test].tolist()),
        **metrics,
    }
    return row, prediction, spec.test


def evaluate_folds(
    features: np.ndarray,
    target: np.ndarray,
    folds: Sequence[FoldSpec],
    *,
    label: str,
    make_model: Callable[[int], Any],
    pool_ids: np.ndarray,
    pool_inchikeys: np.ndarray,
    champion_inchikeys: frozenset[str],
    collect_oof: bool = False,
    fold_jobs: int = 1,
) -> tuple[list[dict[str, Any]], OofAccumulator | None]:
    """Run every fold; `fold_jobs` only parallelises whole folds.

    Each fold still fits with the identical per-model thread count, so the recorded
    numbers do not depend on `fold_jobs`.
    """

    arguments = {
        "features": features,
        "target": target,
        "label": label,
        "make_model": make_model,
        "pool_ids": pool_ids,
        "pool_inchikeys": pool_inchikeys,
        "champion_inchikeys": champion_inchikeys,
    }
    if fold_jobs > 1 and len(folds) > 1:
        with ThreadPoolExecutor(max_workers=fold_jobs) as executor:
            results = list(
                executor.map(
                    lambda spec: evaluate_one_fold(spec=spec, **arguments),
                    folds,
                )
            )
    else:
        results = [evaluate_one_fold(spec=spec, **arguments) for spec in folds]

    rows: list[dict[str, Any]] = []
    accumulator = OofAccumulator.empty(len(target)) if collect_oof else None
    for row, prediction, test_index in results:
        rows.append(row)
        if accumulator is not None:
            accumulator.add(test_index, prediction)
        print(
            f"  [{row['model']} repeat={row['repeat']} fold={row['fold']}] "
            f"mae={row['mae']:.4f} rmse={row['rmse']:.4f}",
            flush=True,
        )
    return rows, accumulator


def mean_fold_metric(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def config_id(feature_variant: str, model_variant: str) -> str:
    return f"{feature_variant}+{model_variant}"


def run_screening(
    bundle: FeatureBundle,
    pool_indices: np.ndarray,
    folds: Sequence[FoldSpec],
    champion_inchikeys: frozenset[str],
    *,
    fold_jobs: int = 1,
) -> dict[str, Any]:
    pool_inchikeys = bundle.inchikeys[pool_indices]
    pool_ids = bundle.molecule_ids[pool_indices]
    records: list[dict[str, Any]] = []
    dummy: dict[str, Any] = {}
    for target in TARGET_ORDER:
        labels = bundle.targets[target][pool_indices]
        dummy_rows, _ = evaluate_folds(
            np.zeros((len(labels), 1), dtype=np.float32),
            labels,
            folds,
            label=f"{target}:dummy_mean",
            make_model=lambda seed: MeanDummyModel(),
            pool_ids=pool_ids,
            pool_inchikeys=pool_inchikeys,
            champion_inchikeys=champion_inchikeys,
            fold_jobs=fold_jobs,
        )
        dummy[target] = {
            "model": "DummyRegressor(strategy='mean')",
            "fold_mae_mean": mean_fold_metric(dummy_rows, "mae"),
            "fold_rmse_mean": mean_fold_metric(dummy_rows, "rmse"),
            "fold_r2_mean": mean_fold_metric(dummy_rows, "r2"),
        }
        print(f"[screen] {target} dummy mae={dummy[target]['fold_mae_mean']:.4f}", flush=True)
        for feature_variant_name, model_variant in SCREEN_COMBINATIONS:
            variant = FEATURE_VARIANTS[feature_variant_name]
            identifier = config_id(feature_variant_name, model_variant)
            features = bundle.matrix(variant)[pool_indices]
            rows, _ = evaluate_folds(
                features,
                labels,
                folds,
                label=f"{target}:{identifier}",
                make_model=functools.partial(build_model, model_variant),
                pool_ids=pool_ids,
                pool_inchikeys=pool_inchikeys,
                champion_inchikeys=champion_inchikeys,
                fold_jobs=fold_jobs,
            )
            record = {
                "target": target,
                "config_id": identifier,
                "feature_variant": feature_variant_name,
                "model_variant": model_variant,
                "n_features": variant.n_features,
                "fold_mae_mean": mean_fold_metric(rows, "mae"),
                "fold_mae_std": float(np.std([float(row["mae"]) for row in rows])),
                "fold_rmse_mean": mean_fold_metric(rows, "rmse"),
                "fold_r2_mean": mean_fold_metric(rows, "r2"),
                "dummy_fold_mae_mean": dummy[target]["fold_mae_mean"],
            }
            record["beat_dummy"] = bool(
                record["fold_mae_mean"] < record["dummy_fold_mae_mean"]
            )
            records.append(record)
            print(
                f"[screen] {target} {identifier} mae={record['fold_mae_mean']:.4f} "
                f"(dummy {record['dummy_fold_mae_mean']:.4f})",
                flush=True,
            )
    return {
        "schema_version": 1,
        "protocol": {
            "kind": "screening",
            "splitter": "RepeatedKFold",
            "n_splits": CV_SPLITS,
            "n_repeats": SCREEN_REPEATS,
            "random_state": CV_SEED,
            "seed_rule": "42 + global fold index",
            "note": "screening protocol only; the acceptance gate uses the formal protocol",
        },
        "selection_rule": SELECTION_RULE,
        "selection_tie_tolerance_ev": SELECTION_TIE_TOLERANCE,
        "source_sha256": bundle.source_sha256,
        "pool_row_count": len(pool_indices),
        "dummy": dummy,
        "records": records,
    }


def select_main_configurations(screening: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Execute the pre-declared selection rule; the rule is never re-tuned to results."""

    records = list(screening["records"])
    dummy = screening["dummy"]
    selections: dict[str, dict[str, Any]] = {}
    for target in TARGET_ORDER:
        candidates = [record for record in records if record["target"] == target]
        if not candidates:
            raise ValueError(f"no screening records for target {target}")
        dummy_mae = float(dummy[target]["fold_mae_mean"])
        beat = [record for record in candidates if record["beat_dummy"]]
        considered = beat or candidates
        ordered = sorted(
            considered,
            key=lambda record: (
                float(record["fold_mae_mean"]),
                int(record["n_features"]),
                MODEL_VARIANT_ORDER.index(record["model_variant"]),
            ),
        )
        best_mae = float(ordered[0]["fold_mae_mean"])
        tied = [
            record
            for record in ordered
            if float(record["fold_mae_mean"]) <= best_mae + SELECTION_TIE_TOLERANCE
        ]
        chosen = min(
            tied,
            key=lambda record: (
                int(record["n_features"]),
                MODEL_VARIANT_ORDER.index(record["model_variant"]),
            ),
        )
        selections[target] = {
            "target": target,
            "config_id": chosen["config_id"],
            "feature_variant": chosen["feature_variant"],
            "model_variant": chosen["model_variant"],
            "n_features": int(chosen["n_features"]),
            "screening_fold_mae_mean": float(chosen["fold_mae_mean"]),
            "screening_dummy_fold_mae_mean": dummy_mae,
            "beat_dummy": bool(beat),
            "tied_configs": [record["config_id"] for record in tied],
            "candidates_beating_dummy": [record["config_id"] for record in beat],
            "rule": SELECTION_RULE,
            "tie_tolerance_ev": SELECTION_TIE_TOLERANCE,
        }
    return selections
def champion_key_map(prereg: Mapping[str, Any]) -> dict[str, str]:
    champion_set = prereg["champion_set"]
    entries = list(champion_set["solvent_list"]) + list(champion_set["additive_list"])
    mapping = {str(entry["inchikey"]): str(entry["short"]) for entry in entries}
    if len(mapping) != 4:
        raise ValueError(f"expected four prereg champions, found {len(mapping)}")
    return mapping


def build_pool(bundle: FeatureBundle, champion_keys: Iterable[str]) -> np.ndarray:
    """Champion-free modelling pool; also the L1 exclusion at the pool level."""

    champion_keys = frozenset(champion_keys)
    present = set(bundle.inchikeys.tolist())
    missing = sorted(champion_keys - present)
    if missing:
        raise DatasetSchemaError(
            f"prereg champions are absent from Batt-P30K: {missing}"
        )
    blocked = np.asarray(sorted(champion_keys), dtype=str)
    pool = np.flatnonzero(~np.isin(bundle.inchikeys, blocked)).astype(np.int64)
    assert_champions_absent(bundle.inchikeys[pool], champion_keys, context="modelling pool")
    return pool


def pool_sha256(bundle: FeatureBundle, pool_indices: np.ndarray) -> str:
    lines = [
        f"{molecule_id}\t{smiles}"
        for molecule_id, smiles in zip(
            bundle.molecule_ids[pool_indices].tolist(),
            bundle.smiles[pool_indices].tolist(),
            strict=True,
        )
    ]
    return sha256_text("\n".join(lines) + "\n")


def target_distribution(labels: np.ndarray) -> dict[str, float]:
    labels = np.asarray(labels, dtype=np.float64)
    return {
        "count": int(labels.size),
        "min": float(labels.min()),
        "max": float(labels.max()),
        "mean": float(labels.mean()),
        "std": float(labels.std()),
    }


def label_space_diagnostics(
    bundle: FeatureBundle,
    pool_indices: np.ndarray,
) -> dict[str, Any]:
    """Label-vs-label statistics for the report; never used as features or inputs."""

    columns = {target: bundle.targets[target][pool_indices] for target in TARGET_ORDER}
    pairs = {
        "IP_vs_HOMO": ("IP", "HOMO", 1.0),
        "EA_vs_LUMO": ("EA", "LUMO", -1.0),
    }
    summary: dict[str, Any] = {}
    for name, (first, second, sign) in pairs.items():
        offset = columns[first] + sign * columns[second]
        summary[name] = {
            "pearson_r": float(np.corrcoef(columns[first], columns[second])[0, 1]),
            "mean_offset_ev": float(offset.mean()),
            "std_offset_ev": float(offset.std()),
        }
    return {
        "note": (
            "diagnostic only: label-vs-label statistics, never used as features, "
            "never fed to a model, never part of the gate"
        ),
        "used_as_feature": False,
        "pairs": summary,
        "target_distribution": {
            target: target_distribution(columns[target]) for target in TARGET_ORDER
        },
    }


def cv_summary(
    fold_rows: Sequence[Mapping[str, Any]],
    accumulator: OofAccumulator,
    labels: np.ndarray,
) -> dict[str, Any]:
    mean_prediction = accumulator.mean()
    covered = accumulator.counts > 0
    pooled = regression_metrics(labels[covered], mean_prediction[covered])
    return {
        "n_folds": len(fold_rows),
        "fold_mae_mean": mean_fold_metric(fold_rows, "mae"),
        "fold_mae_std": float(np.std([float(row["mae"]) for row in fold_rows])),
        "fold_rmse_mean": mean_fold_metric(fold_rows, "rmse"),
        "fold_r2_mean": mean_fold_metric(fold_rows, "r2"),
        "pooled_oof_mae": pooled["mae"],
        "pooled_oof_rmse": pooled["rmse"],
        "pooled_oof_r2": pooled["r2"],
        "oof_rows_covered": int(covered.sum()),
        "oof_repeats_per_row": int(np.unique(accumulator.counts[covered]).max())
        if covered.any()
        else 0,
    }


def fit_production_model(
    features: np.ndarray,
    labels: np.ndarray,
    model_variant: str,
    *,
    seed: int = CV_SEED,
) -> XGBRegressor:
    model = build_model(model_variant, seed)
    model.fit(features, labels)
    return model


def load_target_models(payload: Mapping[str, Any], root: Path) -> dict[str, XGBRegressor]:
    models: dict[str, XGBRegressor] = {}
    for target in TARGET_ORDER:
        artifact = payload["targets"][target]["model"]["artifact"]
        path = root / artifact["path"]
        if not path.exists():
            raise FileNotFoundError(f"missing model artifact for {target}: {path}")
        digest = sha256_file(path)
        if digest != artifact["sha256"]:
            raise CacheMismatchError(
                f"model artifact digest mismatch for {target}: {digest} != {artifact['sha256']}"
            )
        model = XGBRegressor()
        model.load_model(path)
        models[target] = model
    return models


def predict_smiles(
    smiles_values: Sequence[str],
    payload: Mapping[str, Any],
    models: Mapping[str, XGBRegressor],
) -> dict[str, np.ndarray]:
    """Score SMILES with each target's own selected feature variant."""

    blocks: dict[tuple[str, ...], np.ndarray] = {}
    predictions: dict[str, np.ndarray] = {}
    for target in TARGET_ORDER:
        names = tuple(payload["targets"][target]["feature_variant_detail"]["descriptor_names"])
        if names not in blocks:
            blocks[names] = featurize_smiles(smiles_values, names)
        predictions[target] = np.asarray(
            models[target].predict(blocks[names]),
            dtype=np.float64,
        )
    return predictions


def score_smiles_file(
    smiles_path: Path,
    baselines_path: Path,
    output_path: Path | None,
    *,
    root: Path = REPOSITORY_ROOT,
) -> list[dict[str, str]]:
    payload = json.loads(baselines_path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", -1)) != BASELINES_SCHEMA_VERSION:
        raise CacheMismatchError("baselines payload schema version mismatch")
    requested = [
        line.split()[0]
        for line in smiles_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not requested:
        raise ValueError(f"no SMILES found in {smiles_path}")
    models = load_target_models(payload, root)
    predictions = predict_smiles(requested, payload, models)
    rows: list[dict[str, str]] = []
    for index, smiles in enumerate(requested):
        row = {
            "smiles": smiles,
            "canonical_smiles": Chem.MolToSmiles(Chem.MolFromSmiles(smiles)),
        }
        for target in TARGET_ORDER:
            row[f"{target}_eV"] = f"{predictions[target][index]:.6f}"
        row["gap_eV"] = f"{predictions['LUMO'][index] - predictions['HOMO'][index]:.6f}"
        rows.append(row)
    columns = (
        "smiles",
        "canonical_smiles",
        *[f"{target}_eV" for target in TARGET_ORDER],
        "gap_eV",
    )
    if output_path is None:
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return rows


def write_fold_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(FOLD_CSV_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model": row["model"],
                    "seed": row["seed"],
                    "repeat": row["repeat"],
                    "fold": row["fold"],
                    "n_train": row["n_train"],
                    "n_test": row["n_test"],
                    "train_sha": row["train_sha"],
                    "test_sha": row["test_sha"],
                    "mae": f"{float(row['mae']):.8f}",
                    "rmse": f"{float(row['rmse']):.8f}",
                    "r2": f"{float(row['r2']):.8f}",
                }
            )


PREDICTION_CSV_COLUMNS = (
    "target",
    "model",
    "molecule_id",
    "inchikey",
    "smiles",
    "prediction_mean",
    "prediction_std",
    "n_folds",
    "target_value",
    "abs_error_mean",
)


def write_prediction_csv(
    path: Path,
    bundle: FeatureBundle,
    pool_indices: np.ndarray,
    records: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(PREDICTION_CSV_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            target = str(record["target"])
            labels = bundle.targets[target][pool_indices]
            mean_prediction = record["mean"]
            std_prediction = record["std"]
            counts = record["counts"]
            for position, row_index in enumerate(pool_indices.tolist()):
                writer.writerow(
                    {
                        "target": target,
                        "model": record["model"],
                        "molecule_id": bundle.molecule_ids[row_index],
                        "inchikey": bundle.inchikeys[row_index],
                        "smiles": bundle.smiles[row_index],
                        "prediction_mean": f"{mean_prediction[position]:.8f}",
                        "prediction_std": f"{std_prediction[position]:.8f}",
                        "n_folds": int(counts[position]),
                        "target_value": f"{labels[position]:.8f}",
                        "abs_error_mean": f"{abs(labels[position] - mean_prediction[position]):.8f}",
                    }
                )
def versions_block() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "rdkit": rdkit.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "h5py": h5py.__version__,
    }


def unit_block(p4_summary_path: Path) -> dict[str, Any]:
    payload = json.loads(p4_summary_path.read_text(encoding="utf-8"))
    units = payload.get("units", {})
    missing = [target for target in TARGET_ORDER if units.get(target) != GATE_UNIT]
    if missing:
        raise DatasetSchemaError(
            f"p4 units block does not declare {GATE_UNIT} for {missing}"
        )
    return {
        "unit": GATE_UNIT,
        "source": P4_SUMMARY_RELATIVE_PATH,
        "source_sha256": sha256_file(p4_summary_path),
        "source_note": (
            "the Batt-P30K HDF5 file carries no unit metadata (attrs is empty); the "
            "repository declares eV for HOMO/LUMO/IP/EA in the p4 redox units block, "
            "which this run reuses unchanged"
        ),
        "dataset_method": "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
        "source_doi": "10.1021/acsnano.6c06255",
        "hdf5_metadata_declares_unit": False,
    }


def gate_block(per_target_mae: Mapping[str, float]) -> dict[str, Any]:
    per_target = {}
    for target in TARGET_ORDER:
        value = float(per_target_mae[target])
        per_target[target] = {
            "threshold_mae": GATE_MAE_THRESHOLD,
            "unit": GATE_UNIT,
            "criterion": (
                "mean fold MAE of the selected main model over the formal "
                "RepeatedKFold(5, 10, random_state=42) folds below the threshold"
            ),
            "best_model_mae": value,
            "passed": bool(value < GATE_MAE_THRESHOLD),
        }
    passed_targets = [target for target in TARGET_ORDER if per_target[target]["passed"]]
    return {
        "threshold_mae": GATE_MAE_THRESHOLD,
        "unit": GATE_UNIT,
        "criterion": GATE_CRITERION,
        "best_model_mae": {target: per_target[target]["best_model_mae"] for target in TARGET_ORDER},
        "passed": len(passed_targets) == len(TARGET_ORDER),
        "per_target": per_target,
        "targets_passed": len(passed_targets),
        "targets_total": len(TARGET_ORDER),
        "criterion_scopes": {
            "per_target": (
                "MAE < 0.2 eV for that individual target "
                f"(passed: {len(passed_targets)}/{len(TARGET_ORDER)})"
            ),
            "all_four": (
                "MAE < 0.2 eV simultaneously for HOMO/LUMO/IP/EA "
                f"(passed: {len(passed_targets) == len(TARGET_ORDER)})"
            ),
        },
    }


def learning_curve(
    features: np.ndarray,
    labels: np.ndarray,
    fold: FoldSpec,
    *,
    model_variant: str,
    pool_ids: np.ndarray,
    pool_inchikeys: np.ndarray,
    champion_inchikeys: frozenset[str],
    train_sizes: Sequence[int] = (1000, 5000, 12000),
    seed: int = CV_SEED,
) -> list[dict[str, Any]]:
    train = exclude_champions(fold.train, pool_inchikeys, champion_inchikeys)
    assert_champions_absent(pool_inchikeys[train], champion_inchikeys, context="learning curve")
    rng = np.random.default_rng(seed)
    curve: list[dict[str, Any]] = []
    sizes = list(train_sizes) + [len(train)]
    for requested in sizes:
        size = min(int(requested), len(train))
        selected = np.sort(rng.choice(train, size=size, replace=False))
        model = build_model(model_variant, seed)
        model.fit(features[selected], labels[selected])
        prediction = np.asarray(model.predict(features[fold.test]), dtype=np.float64)
        metrics = regression_metrics(labels[fold.test], prediction)
        curve.append({"train_size": size, **metrics})
        print(f"  [curve] train_size={size} mae={metrics['mae']:.4f}", flush=True)
    return curve


def run_baselines(
    *,
    h5_path: Path,
    cache_path: Path,
    prereg_path: Path,
    p4_summary_path: Path,
    screening_path: Path,
    summary_path: Path,
    baselines_path: Path,
    fold_csv_path: Path,
    predictions_csv_path: Path,
    model_dir: Path,
    rebuild_cache: bool = False,
    skip_screening: bool = False,
    screen_only: bool = False,
    run_analysis: bool = True,
    fold_jobs: int = 1,
    cv_repeats: int = CV_REPEATS,
) -> dict[str, Any]:
    bundle = build_feature_bundle(h5_path, cache_path, rebuild_cache=rebuild_cache)
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg_sha = sha256_file(prereg_path)
    champion_keys = champion_key_map(prereg)
    champion_inchikeys = frozenset(champion_keys)
    pool_indices = build_pool(bundle, champion_inchikeys)
    pool_sha = pool_sha256(bundle, pool_indices)
    pool_inchikeys = bundle.inchikeys[pool_indices]
    pool_ids = bundle.molecule_ids[pool_indices]
    print(
        f"pool: {len(pool_indices)} rows (source groups {bundle.source_group_count}, "
        f"champions excluded {bundle.source_group_count - len(pool_indices)})",
        flush=True,
    )

    if not screen_only and skip_screening and screening_path.exists():
        screening = json.loads(screening_path.read_text(encoding="utf-8"))
        if screening.get("source_sha256") != bundle.source_sha256:
            raise CacheMismatchError("screening cache source SHA256 mismatch")
        if int(screening.get("pool_row_count", -1)) != len(pool_indices):
            raise CacheMismatchError("screening cache pool row count mismatch")
        print("reusing screening cache", flush=True)
    else:
        screening = run_screening(
            bundle,
            pool_indices,
            cv_folds(len(pool_indices), repeats=SCREEN_REPEATS, seed=CV_SEED),
            champion_inchikeys,
            fold_jobs=fold_jobs,
        )
        screening["prereg_path"] = PREREG_RELATIVE_PATH
        screening["prereg_sha256"] = prereg_sha
        screening["pool_sha256"] = pool_sha
        screening_path.parent.mkdir(parents=True, exist_ok=True)
        screening_path.write_text(
            json.dumps(screening, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    selections = select_main_configurations(screening)
    if screen_only:
        return {"screening": screening, "selections": selections}

    folds = cv_folds(len(pool_indices), repeats=cv_repeats, seed=CV_SEED)
    deviation: dict[str, Any] = {
        "project_standard": {
            "n_splits": CV_SPLITS,
            "n_repeats": CV_REPEATS,
            "random_state": CV_SEED,
        },
        "used_in_this_run": {
            "n_splits": CV_SPLITS,
            "n_repeats": cv_repeats,
            "random_state": CV_SEED,
        },
        "deviates_from_project_standard": cv_repeats != CV_REPEATS,
        "declaration": (
            f"this run used {CV_SPLITS}x{cv_repeats} "
            f"(RepeatedKFold n_splits={CV_SPLITS}, n_repeats={cv_repeats}, "
            f"random_state={CV_SEED}), which deviates from the project standard "
            f"{CV_SPLITS}x{CV_REPEATS}; the reason is compute/time budget, not the "
            f"science; strict alignment with existing project artefacts requires a "
            f"re-run at {CV_SPLITS}x{CV_REPEATS}"
        )
        if cv_repeats != CV_REPEATS
        else (
            f"this run used the project standard {CV_SPLITS}x{CV_REPEATS} "
            f"(RepeatedKFold, random_state={CV_SEED})"
        ),
    }
    fold_rows: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    targets_payload: dict[str, Any] = {}
    per_target_mae: dict[str, float] = {}
    artifacts: dict[str, dict[str, str]] = {}
    completed: list[str] = []
    analysis: dict[str, Any] = {
        "label_space_diagnostics": label_space_diagnostics(bundle, pool_indices)
    }

    def assemble_summary(*, complete: bool) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "schema_version": 1,
            "task": "homo_lumo_baselines",
            "generated_at_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "complete": complete,
            "completed_targets": list(completed),
            "remaining_targets": [
                target for target in FORMAL_RUN_ORDER if target not in completed
            ],
            "unit": unit_block(p4_summary_path),
            "pool_rows": len(pool_indices),
            "pool_sha256": pool_sha,
            "champions_excluded": sorted(champion_keys),
            "screening_protocol": screening["protocol"],
            "screening_records": screening["records"],
            "screening_dummy": screening["dummy"],
            "selection_rule": SELECTION_RULE,
            "selections": selections,
            "cv_protocol": {
                "splitter": "RepeatedKFold",
                "n_splits": CV_SPLITS,
                "n_repeats": cv_repeats,
                "random_state": CV_SEED,
                "seed_rule": "42 + global fold index (repeat * n_splits + fold)",
                "n_folds": len(folds),
                "xgb_n_jobs": XGB_N_JOBS,
                "fold_jobs": fold_jobs,
                "target_run_order": list(FORMAL_RUN_ORDER),
                "deviation": deviation,
            },
            "formal_cv": {
                target: {
                    **targets_payload[target]["cv"],
                    "dummy_fold_mae_mean": targets_payload[target]["dummy_control"][
                        "fold_mae_mean"
                    ],
                }
                for target in FORMAL_RUN_ORDER
                if target in targets_payload
            },
            "analysis": analysis,
            "versions": versions_block(),
            "outputs": {
                "baselines_json": repo_path(baselines_path),
                "fold_csv": repo_path(fold_csv_path),
                "predictions_csv": repo_path(predictions_csv_path),
                "screening_json": repo_path(screening_path),
                "model_artifacts": {
                    target: artifacts[target]["path"] for target in sorted(artifacts)
                },
            },
        }
        if complete:
            summary["gate"] = gate_block(per_target_mae)
            summary["gate_status"] = "final"
        else:
            summary["gate_status"] = (
                "pending: the gate is finalised only after all four targets finish"
            )
        return summary

    def flush_partial() -> None:
        write_fold_csv(fold_csv_path, fold_rows)
        write_prediction_csv(predictions_csv_path, bundle, pool_indices, prediction_records)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(assemble_summary(complete=False), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[flush] partial artifacts written, completed={completed}", flush=True)

    for target in FORMAL_RUN_ORDER:
        selection = selections[target]
        variant = FEATURE_VARIANTS[selection["feature_variant"]]
        features = bundle.matrix(variant)[pool_indices]
        labels = bundle.targets[target][pool_indices]
        print(f"[formal] {target} {selection['config_id']}", flush=True)
        main_rows, main_accumulator = evaluate_folds(
            features,
            labels,
            folds,
            label=f"{target}:{selection['config_id']}",
            make_model=functools.partial(build_model, selection["model_variant"]),
            pool_ids=pool_ids,
            pool_inchikeys=pool_inchikeys,
            champion_inchikeys=champion_inchikeys,
            collect_oof=True,
            fold_jobs=fold_jobs,
        )
        dummy_rows, dummy_accumulator = evaluate_folds(
            np.zeros((len(labels), 1), dtype=np.float32),
            labels,
            folds,
            label=f"{target}:dummy_mean",
            make_model=lambda seed: MeanDummyModel(),
            pool_ids=pool_ids,
            pool_inchikeys=pool_inchikeys,
            champion_inchikeys=champion_inchikeys,
            collect_oof=True,
            fold_jobs=fold_jobs,
        )
        fold_rows.extend(main_rows)
        fold_rows.extend(dummy_rows)
        assert main_accumulator is not None
        assert dummy_accumulator is not None
        cv_block = cv_summary(main_rows, main_accumulator, labels)
        dummy_summary = cv_summary(dummy_rows, dummy_accumulator, labels)
        per_target_mae[target] = cv_block["fold_mae_mean"]
        targets_payload[target] = {
            "label_source": f"Batt-P30K/{TARGET_DATASETS[target]}",
            "selection": selection,
            "feature_variant": selection["feature_variant"],
            "feature_variant_detail": {
                "descriptor_names": list(variant.descriptor_names),
                "n_features": variant.n_features,
            },
            "model": {
                "framework": "xgboost",
                "version": xgboost.__version__,
                "variant": selection["model_variant"],
                "params": dict(MODEL_VARIANTS[selection["model_variant"]]),
                "seed": CV_SEED,
                "seed_rule": "42 + global fold index for CV folds; 42 for the shipped model",
                "n_jobs": XGB_N_JOBS,
            },
            "training_pool_rows": len(pool_indices),
            "training_pool_sha256": pool_sha,
            "cv": cv_block,
            "dummy_control": {
                "model": "DummyRegressor(strategy='mean')",
                "folds": "identical to the main model (same RepeatedKFold instance)",
                **dummy_summary,
            },
        }
        prediction_records.append(
            {
                "target": target,
                "model": f"{target}:{selection['config_id']}",
                "mean": main_accumulator.mean(),
                "std": main_accumulator.std(),
                "counts": main_accumulator.counts,
            }
        )
        prediction_records.append(
            {
                "target": target,
                "model": f"{target}:dummy_mean",
                "mean": dummy_accumulator.mean(),
                "std": dummy_accumulator.std(),
                "counts": dummy_accumulator.counts,
            }
        )
        completed.append(target)
        flush_partial()

    if run_analysis:
        worst_target = max(FORMAL_RUN_ORDER, key=lambda target: per_target_mae[target])
        worst_selection = selections[worst_target]
        worst_variant = FEATURE_VARIANTS[worst_selection["feature_variant"]]
        print(f"[analysis] learning curve for worst target {worst_target}", flush=True)
        analysis["worst_target"] = worst_target
        analysis["learning_curve"] = {
            "target": worst_target,
            "fold": folds[0].label,
            "model_variant": worst_selection["model_variant"],
            "feature_variant": worst_selection["feature_variant"],
            "curve": learning_curve(
                bundle.matrix(worst_variant)[pool_indices],
                bundle.targets[worst_target][pool_indices],
                folds[0],
                model_variant=worst_selection["model_variant"],
                pool_ids=pool_ids,
                pool_inchikeys=pool_inchikeys,
                champion_inchikeys=champion_inchikeys,
            ),
        }
    gate = gate_block(per_target_mae)
    model_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, str]] = {}
    for target in TARGET_ORDER:
        selection = selections[target]
        variant = FEATURE_VARIANTS[selection["feature_variant"]]
        model = fit_production_model(
            bundle.matrix(variant)[pool_indices],
            bundle.targets[target][pool_indices],
            selection["model_variant"],
            seed=CV_SEED,
        )
        artifact_path = model_dir / f"homo_lumo_{target.lower()}.ubj"
        model.save_model(artifact_path)
        artifacts[target] = {
            "path": repo_path(artifact_path),
            "sha256": sha256_file(artifact_path),
            "format": "xgboost ubj",
        }
        targets_payload[target]["model"]["artifact"] = artifacts[target]

    write_fold_csv(fold_csv_path, fold_rows)
    write_prediction_csv(predictions_csv_path, bundle, pool_indices, prediction_records)

    payload: dict[str, Any] = {
        "schema_version": BASELINES_SCHEMA_VERSION,
        "task": "homo_lumo_baselines",
        "title": (
            "L3 exit 2: Morgan + 2D-descriptor XGBoost baselines for HOMO/LUMO/IP/EA "
            "(manual appendix Q-2)"
        ),
        "generated_at_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unit": unit_block(p4_summary_path),
        "source_dataset": {
            "path": H5_RELATIVE_PATH,
            "sha256": bundle.source_sha256,
            "group_count": bundle.source_group_count,
            "method": "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
            "source_doi": "10.1021/acsnano.6c06255",
        },
        "feature_config": feature_config(),
        "scoring": {
            "cli": (
                "python probes/homo_lumo_baselines.py --score-smiles <file.smi> "
                "[--score-output <out.csv>]"
            ),
            "output_columns": [
                "smiles",
                "canonical_smiles",
                *[f"{target}_eV" for target in TARGET_ORDER],
                "gap_eV",
            ],
            "gap_eV": "derived as LUMO_prediction - HOMO_prediction, in eV",
            "feature_order": (
                f"morgan_count({MORGAN_FP_SIZE}) then descriptors in the declared order; "
                "identical code path for fit and scoring"
            ),
        },
        "exclusion": {
            "level": "L1",
            "prereg_path": PREREG_RELATIVE_PATH,
            "prereg_sha256": prereg_sha,
            "rule": prereg["exclusion_levels"][0],
            "champions": [
                {"short": champion_keys[key], "inchikey": key} for key in sorted(champion_keys)
            ],
            "pool_rows_after_exclusion": len(pool_indices),
            "pool_sha256": pool_sha,
            "per_fold_assertion": (
                "champions & train_ids == {} asserted for every fold of both the "
                "screening and the formal protocol, for the main model and the Dummy "
                "control"
            ),
        },
        "cv_protocol": {
            "splitter": "RepeatedKFold",
            "n_splits": CV_SPLITS,
            "n_repeats": cv_repeats,
            "random_state": CV_SEED,
            "seed_rule": "42 + global fold index (repeat * n_splits + fold)",
            "n_folds": len(folds),
            "xgb_n_jobs": XGB_N_JOBS,
            "fold_jobs": fold_jobs,
            "target_run_order": list(FORMAL_RUN_ORDER),
            "deviation": deviation,
        },
        "targets": targets_payload,
        "gate": gate,
        "analysis": analysis,
        "versions": versions_block(),
    }

    baselines_path.parent.mkdir(parents=True, exist_ok=True)
    baselines_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    champion_rows = np.flatnonzero(np.isin(bundle.inchikeys, np.asarray(sorted(champion_inchikeys), dtype=str)))
    champion_smiles = [bundle.smiles[index] for index in champion_rows.tolist()]
    reloaded = load_target_models(payload, REPOSITORY_ROOT)
    champion_predictions = predict_smiles(champion_smiles, payload, reloaded)
    champion_scores = []
    for position, index in enumerate(champion_rows.tolist()):
        entry: dict[str, Any] = {
            "short": champion_keys[bundle.inchikeys[index]],
            "inchikey": bundle.inchikeys[index],
            "molecule_id": bundle.molecule_ids[index],
            "smiles": bundle.smiles[index],
        }
        for target in TARGET_ORDER:
            entry[f"{target}_eV"] = float(champion_predictions[target][position])
        entry["gap_eV"] = float(
            champion_predictions["LUMO"][position] - champion_predictions["HOMO"][position]
        )
        entry["path"] = "scored through the same --score-smiles code path"
        champion_scores.append(entry)
    payload["champion_scores"] = champion_scores
    payload["asymmetry_note"] = (
        "all four champions were removed from the modelling pool for this channel; the "
        "prereg records that FEC/VC were already withheld from the dielectric fit while "
        "EC/PC were not, which is an asymmetry that must not be blurred away"
    )
    baselines_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    summary = assemble_summary(complete=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5", type=Path, default=REPOSITORY_ROOT / H5_RELATIVE_PATH)
    parser.add_argument("--cache", type=Path, default=REPOSITORY_ROOT / CACHE_RELATIVE_PATH)
    parser.add_argument("--prereg", type=Path, default=REPOSITORY_ROOT / PREREG_RELATIVE_PATH)
    parser.add_argument(
        "--p4-summary",
        type=Path,
        default=REPOSITORY_ROOT / P4_SUMMARY_RELATIVE_PATH,
    )
    parser.add_argument(
        "--screening",
        type=Path,
        default=REPOSITORY_ROOT / SCREENING_RELATIVE_PATH,
    )
    parser.add_argument("--summary", type=Path, default=REPOSITORY_ROOT / SUMMARY_RELATIVE_PATH)
    parser.add_argument(
        "--baselines",
        type=Path,
        default=REPOSITORY_ROOT / BASELINES_RELATIVE_PATH,
    )
    parser.add_argument("--fold-csv", type=Path, default=REPOSITORY_ROOT / FOLD_CSV_RELATIVE_PATH)
    parser.add_argument(
        "--predictions-csv",
        type=Path,
        default=REPOSITORY_ROOT / PREDICTIONS_CSV_RELATIVE_PATH,
    )
    parser.add_argument("--model-dir", type=Path, default=REPOSITORY_ROOT / MODEL_ARTIFACT_DIR)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--skip-screening", action="store_true")
    parser.add_argument("--screen-only", action="store_true")
    parser.add_argument("--no-analysis", action="store_true")
    parser.add_argument(
        "--repeats",
        type=int,
        default=CV_REPEATS,
        help=(
            "RepeatedKFold n_repeats; the project standard is 10 and any other value "
            "is declared as a deviation in the summary"
        ),
    )
    parser.add_argument(
        "--fold-jobs",
        type=int,
        default=1,
        help="parallelise whole folds (each fold keeps the identical per-model threads)",
    )
    parser.add_argument("--score-smiles", type=Path, default=None)
    parser.add_argument("--score-output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.score_smiles is not None:
        score_smiles_file(args.score_smiles, args.baselines, args.score_output)
        return 0
    summary = run_baselines(
        h5_path=args.h5,
        cache_path=args.cache,
        prereg_path=args.prereg,
        p4_summary_path=args.p4_summary,
        screening_path=args.screening,
        summary_path=args.summary,
        baselines_path=args.baselines,
        fold_csv_path=args.fold_csv,
        predictions_csv_path=args.predictions_csv,
        model_dir=args.model_dir,
        rebuild_cache=args.rebuild_cache,
        skip_screening=args.skip_screening,
        screen_only=args.screen_only,
        run_analysis=not args.no_analysis,
        fold_jobs=args.fold_jobs,
        cv_repeats=args.repeats,
    )
    print(json.dumps(summary.get("gate", summary.get("selections")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())