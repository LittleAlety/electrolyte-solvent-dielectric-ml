"""Week 20 -- W20-2 Step 2: is the liquid-window channel modelable at all?

Step 1 (probes/w20_safety_ablation.py) measured what the safety channel does to
the ranking head; it fitted no model and took no shot number.  Step 2 asks the
other half of the W20-2 question, the half the charter marks "shot after 占号":
can the liquid-window channel -- melting point, boiling point and flash point --
be modelled at all from molecular structure, on the rows this repository holds?

The reference target is fixed by the charter, not chosen here: Angew 2024 (Gao
et al.) reports MAE 10.4 / 4.6 / 4.8 K for MP / BP / FP.  The same sentence that
quotes those numbers must also quote the sample gap, because alone they are not
comparable: that work trained on 3,504-4,235 rows per property, while this
repository carries 186 rows that hold all three liquid-window targets (202 MP,
216 BP, 189 FP individually).  That is a factor of about 19-23x, so 直接对标 and
any superiority claim are forbidden; the reference is a scale marker and nothing
else.  What this lane reads is whether the channel carries learnable structure at
~186 rows, measured against an internal trivial baseline and against a placebo,
never against the literature number.

Design, entirely frozen in probes/w20_safety_model_prereg.json before the run:

* rows      the complete-window set: every row of
            data/processed/liquid_window_features.csv carrying a finite mp_C,
            bp_C and flash_point_C, joined to registry SMILES by InChIKey;
* targets   mp, bp, fp converted to K so the MAE unit matches the reference (an
            offset leaves MAE unchanged, so K and degC agree numerically -- the
            conversion is a unit statement, not a number);
* split     GroupKFold by InChIKey, 5 folds x 5 locked seeds.  Every usable row
            is a distinct compound, so the grouping is a no-op on today rows; it
            is kept because it is the discipline the lane is registered under,
            and it is what keeps the split honest if the target ever carries
            several observations per compound;
* model     one ExtraTrees regressor per (target, arm, seed, fold) with locked
            hyperparameters; no tuning, no post-hoc arm selection;
* baseline  the fold-local training mean, scored out-of-fold on the same folds;
* placebo   the identical protocol on structurally shuffled targets, so a
            "modelable" verdict that survives label shuffling is reported as a
            leak rather than a finding;
* rule      a target counts as modelable iff its cross-seed mean MAE is at least
            20% below its own baseline and the placebo does not clear that bar.

Discipline.  This is a reading-producing lane, so it takes shot 22 -- the first
reading-producing Week 20 gun, frozen in reports/_w20_section_gov.md (section
28.65).  It is still not a promotion: promoted = false, it writes no pool, it
uses no Reaxys value, and it does not touch the epsilon main scoreboard
(scoreboard_attempts_delta = 0).  The isolation rule is absolute: these MAE
readings may never be compared against the epsilon main scoreboard readings
(0.4091179943351143 / 0.4766400383507876) or against the eta readings
(0.08506361044387624 / 0.08908094784092072).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path

LIQUID_WINDOW_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_features.csv"
REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_model_summary.json"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_model_prereg.json"
REPEATS_CSV_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_safety_model_repeats.csv"

SCHEMA_VERSION = "w20_safety_model_plan_v0"
TASK = "week20_w20_2_step2_safety_channel_modelability"
SECTION = "28.58"

PRODUCES_READING = True
PROMOTED = False
MAIN_SCOREBOARD_UNTOUCHED = True
SCOREBOARD_ATTEMPTS_DELTA = 0
SHOT_NUMBER_TAKEN = 22
REAXYS_VALUES_USED = 0
WRITES_ANY_POOL = False

SHOT_NUMBER_BASIS = (
    "reports/_w20_section_gov.md section 28.65: the first reading-producing "
    "Week 20 gun takes 22"
)

GROUP_COLUMN = "inchikey"
TARGETS: tuple[str, ...] = ("mp", "bp", "fp")
TARGET_COLUMNS: dict[str, str] = {
    "mp": "mp_C",
    "bp": "bp_C",
    "fp": "flash_point_C",
}
CELSIUS_TO_KELVIN = 273.15

N_SPLITS = 5
SEEDS: tuple[int, ...] = (42, 1234, 2026, 31337, 7)

MORGAN_RADIUS = 2
MORGAN_BITS = 256
PHYSICAL_DESCRIPTORS: tuple[str, ...] = (
    "MolWt",
    "MolLogP",
    "TPSA",
    "NumHDonors",
    "NumHAcceptors",
    "NumRotatableBonds",
    "RingCount",
    "NumAromaticRings",
    "FractionCSP3",
    "HeavyAtomCount",
    "NumHeteroatoms",
    "LabuteASA",
    "BalabanJ",
    "BertzCT",
    "Chi0",
    "Chi1",
    "Kappa1",
    "Kappa2",
    "HallKierAlpha",
    "NumSaturatedRings",
    "NumAliphaticRings",
    "NumSpiroAtoms",
    "NumBridgeheadAtoms",
    "MaxPartialCharge",
    "MinPartialCharge",
)
FEATURE_COUNT = MORGAN_BITS + len(PHYSICAL_DESCRIPTORS)

#: Locked learner.  An XGBoost arm was measured first and rejected on cost, not
#: on quality: xgboost 3.4.1 spends ~35 ms per tree on this row count whatever
#: the feature count, so the 150 fits this protocol needs would take ~30 minutes.
#: ExtraTrees scores the same fits in well under a second each and is
#: deterministic under random_state, so it is the family this lane locks.  n_jobs
#: is pinned to 1: the result was measured identical at n_jobs = 8, and pinning 1
#: keeps the reading independent of the host core count.
MODEL_FAMILY = "sklearn.ensemble.ExtraTreesRegressor"
MODEL_PARAMS: dict[str, object] = {
    "n_estimators": 300,
    "n_jobs": 1,
}

MODELABILITY_RELATIVE_MARGIN = 0.20
SEED_SPREAD_TOLERANCE_K = 2.0
PLACEBO_SEED = 20260928
EXPECTED_USABLE_ROWS = 186

REFERENCE_TARGET: dict[str, object] = {
    "role": "scale marker only; the sample gap is always declared with it",
    "citation": "Angew 2024 (Gao et al.)",
    "mae_K": {"mp": 10.4, "bp": 4.6, "fp": 4.8},
    "train_rows_per_property": {"min": 3504, "max": 4235},
    "provenance": (
        "charter-locked (reports/week20_project_charter.md section 1 W20-2); "
        "not re-derived in this repository"
    ),
    "forbidden_use": "direct benchmarking or any superiority claim",
}

ISOLATION: dict[str, object] = {
    "epsilon_main_scoreboard_readings": [0.4091179943351143, 0.4766400383507876],
    "eta_readings": [0.08506361044387624, 0.08908094784092072],
    "rule": "this lane may never be compared against either set",
}

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def target_availability(liquid_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    """How many rows carry each target on its own, before the complete-case join."""

    return {
        name: sum(
            1 for row in liquid_rows if is_finite_number(row.get(TARGET_COLUMNS[name]))
        )
        for name in TARGETS
    }


def usable_rows(
    liquid_rows: Sequence[Mapping[str, str]],
    registry_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    """Rows carrying all three targets, joined to a registry SMILES by InChIKey."""

    smiles_by_key = {
        str(row["inchikey"]): str(row.get("smiles") or "")
        for row in registry_rows
        if row.get("inchikey")
    }
    rows: list[dict[str, object]] = []
    for row in liquid_rows:
        key = str(row.get("inchikey") or "").strip()
        if not key or not smiles_by_key.get(key):
            continue
        values: dict[str, float] = {}
        complete = True
        for name in TARGETS:
            raw = row.get(TARGET_COLUMNS[name])
            if not is_finite_number(raw):
                complete = False
                break
            values[name] = float(raw) + CELSIUS_TO_KELVIN
        if not complete:
            continue
        entry: dict[str, object] = {"inchikey": key, "smiles": smiles_by_key[key]}
        for name in TARGETS:
            entry[f"y_{name}"] = values[name]
        rows.append(entry)
    return rows


def featurize(rows: Sequence[Mapping[str, object]]) -> np.ndarray:
    """Morgan counts plus the locked physical block, one row per compound."""

    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdFingerprintGenerator

    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS, fpSize=MORGAN_BITS
    )
    matrix = np.zeros((len(rows), FEATURE_COUNT), dtype=np.float64)
    for index, row in enumerate(rows):
        molecule = Chem.MolFromSmiles(str(row["smiles"]))
        if molecule is None:
            raise SystemExit("cannot parse SMILES for " + str(row["inchikey"]))
        counts = generator.GetCountFingerprint(molecule).GetNonzeroElements()
        for position, count in counts.items():
            matrix[index, position] = count
        for offset, name in enumerate(PHYSICAL_DESCRIPTORS):
            matrix[index, MORGAN_BITS + offset] = float(getattr(Descriptors, name)(molecule))
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def repeat_folds(
    rows: Sequence[Mapping[str, object]],
    *,
    seed: int,
    n_splits: int = N_SPLITS,
) -> list[tuple[list[int], list[int]]]:
    """GroupKFold by InChIKey on a seed-shuffled group order.

    Shuffling the group order is what turns one deterministic GroupKFold split
    into five distinct repeats; every row is a distinct compound here, so the
    grouping itself is a no-op on today rows and is kept as discipline.
    """

    from sklearn.model_selection import GroupKFold

    groups = list(dict.fromkeys(str(row[GROUP_COLUMN]) for row in rows))
    random.Random(seed).shuffle(groups)
    order = {group: index for index, group in enumerate(groups)}
    ordered = sorted(range(len(rows)), key=lambda i: order[str(rows[i][GROUP_COLUMN])])
    labels = np.array([str(rows[i][GROUP_COLUMN]) for i in ordered])
    folds: list[tuple[list[int], list[int]]] = []
    splitter = GroupKFold(n_splits=n_splits)
    for train_positions, test_positions in splitter.split(np.zeros(len(ordered)), groups=labels):
        folds.append(
            ([ordered[i] for i in train_positions], [ordered[i] for i in test_positions])
        )
    return folds


def fold_predictions(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    """One locked ExtraTrees fit; no tuning, no early stopping, no seed selection."""

    from sklearn.ensemble import ExtraTreesRegressor

    model = ExtraTreesRegressor(random_state=seed, **MODEL_PARAMS)
    model.fit(x_train, y_train)
    return np.asarray(model.predict(x_test), dtype=np.float64)


@dataclass(frozen=True)
class RepeatReading:
    """One (property, arm, seed, fold) out-of-fold MAE and its trivial baseline."""

    property: str
    arm: str
    seed: int
    fold: int
    n_train: int
    n_test: int
    mae_K: float
    baseline_mae_K: float


REPEATS_CSV_FIELDS: tuple[str, ...] = (
    "property",
    "arm",
    "seed",
    "fold",
    "n_train",
    "n_test",
    "mae_K",
    "baseline_mae_K",
)


def repeats_csv_rows(readings: Sequence[RepeatReading]) -> list[dict[str, object]]:
    return [
        {
            "property": item.property,
            "arm": item.arm,
            "seed": item.seed,
            "fold": item.fold,
            "n_train": item.n_train,
            "n_test": item.n_test,
            "mae_K": repr(item.mae_K),
            "baseline_mae_K": repr(item.baseline_mae_K),
        }
        for item in readings
    ]


def write_repeats_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write the projected per-fold rows.  LF only, so the artifact stays diff-stable."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(REPEATS_CSV_FIELDS), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

def input_digests(paths: Sequence[Path]) -> dict[str, dict[str, object]]:
    digests: dict[str, dict[str, object]] = {}
    for path in paths:
        raw = Path(path).read_bytes()
        digests[portable_relative_path(path, root=REPOSITORY_ROOT)] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    return digests


def dependency_versions() -> dict[str, str]:
    """The two libraries the reading depends on, read from the modules themselves."""

    from importlib import import_module

    versions: dict[str, str] = {}
    for package in ("rdkit", "sklearn", "numpy"):
        try:
            versions[package] = str(import_module(package).__version__)
        except (ImportError, AttributeError):  # pragma: no cover - dependency absent
            versions[package] = "unknown"
    return versions


def prereg_reference(path: Path = PREREG_PATH) -> dict[str, object] | None:
    """Where the frozen registration is, and its digest, once it exists."""

    if not Path(path).is_file():
        return None
    raw = Path(path).read_bytes()
    return {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def input_blockers() -> list[str]:
    blockers: list[str] = []
    for label, path in (("liquid_window", LIQUID_WINDOW_PATH), ("registry", REGISTRY_PATH)):
        if not Path(path).is_file():
            blockers.append(
                f"{label} input is missing: "
                + portable_relative_path(path, root=REPOSITORY_ROOT)
            )
    return blockers


def blocking_conditions(*, prereg_path: Path = PREREG_PATH) -> list[str]:
    """Everything that must be in place before a reading may be produced."""

    blockers = input_blockers()
    if not Path(prereg_path).is_file():
        blockers.append("the preregistration is not on disk; run --write-prereg first")
    return blockers


def plan() -> dict[str, object]:
    """The pinned configuration, printable without producing a reading."""

    return {
        "schema_version": SCHEMA_VERSION,
        "task": TASK,
        "section": SECTION,
        "status": "pinned_awaiting_execution",
        "produces_reading": PRODUCES_READING,
        "promoted": PROMOTED,
        "main_scoreboard_untouched": MAIN_SCOREBOARD_UNTOUCHED,
        "scoreboard_attempts_delta": SCOREBOARD_ATTEMPTS_DELTA,
        "shot_number_taken": SHOT_NUMBER_TAKEN,
        "shot_number_basis": SHOT_NUMBER_BASIS,
        "reaxys_values_used": REAXYS_VALUES_USED,
        "writes_any_pool": WRITES_ANY_POOL,
        "models_fitted": 0,
        "isolation": ISOLATION,
        "reference_target": REFERENCE_TARGET,
        "targets": {
            "names": list(TARGETS),
            "columns": TARGET_COLUMNS,
            "unit": "K",
            "conversion": "degC + 273.15; MAE is offset-invariant, so the value is unchanged",
        },
        "split": {
            "group_column": GROUP_COLUMN,
            "n_splits": N_SPLITS,
            "seeds": list(SEEDS),
            "grouping_note": (
                "each usable row is a distinct compound, so the grouping is a no-op "
                "on this row set and is retained as the locked discipline"
            ),
        },
        "model": {
            "family": MODEL_FAMILY,
            "params": MODEL_PARAMS,
            "tuning": "none; one locked arm, no post-hoc selection",
        },
        "features": {
            "morgan_radius": MORGAN_RADIUS,
            "morgan_bits": MORGAN_BITS,
            "morgan_kind": "count fingerprint",
            "physical_descriptors": list(PHYSICAL_DESCRIPTORS),
            "feature_count": FEATURE_COUNT,
        },
        "decision_rule": {
            "modelability_relative_margin": MODELABILITY_RELATIVE_MARGIN,
            "seed_spread_tolerance_K": SEED_SPREAD_TOLERANCE_K,
            "placebo_seed": PLACEBO_SEED,
            "statement": (
                "a target is modelable iff its cross-seed mean MAE is at least "
                "MODELABILITY_RELATIVE_MARGIN below its own fold-local baseline, "
                "and the placebo arm does not clear the same bar"
            ),
        },
        "usable_rows_pin": EXPECTED_USABLE_ROWS,
        "inputs": {
            "liquid_window": portable_relative_path(
                LIQUID_WINDOW_PATH, root=REPOSITORY_ROOT
            ),
            "registry": portable_relative_path(REGISTRY_PATH, root=REPOSITORY_ROOT),
        },
        "blocking_conditions": input_blockers(),
    }


PREREG_PINNED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "task",
    "section",
    "produces_reading",
    "promoted",
    "main_scoreboard_untouched",
    "scoreboard_attempts_delta",
    "shot_number_taken",
    "reaxys_values_used",
    "writes_any_pool",
    "usable_rows_pin",
    "targets",
    "split",
    "model",
    "features",
    "decision_rule",
    "reference_target",
    "isolation",
)


def check_prereg_against_module(prereg_path: Path = PREREG_PATH) -> None:
    """Refuse to produce a reading if the frozen pins no longer match this module."""

    frozen = json.loads(Path(prereg_path).read_text(encoding="utf-8"))
    current = plan()
    for field in PREREG_PINNED_FIELDS:
        if frozen.get(field) != current[field]:
            raise SystemExit(
                f"the preregistration moved on {field!r}: "
                f"{frozen.get(field)!r} vs {current[field]!r}"
            )


def prereg_summary(*, locked_at_utc: str, prereg_path: Path = PREREG_PATH) -> dict[str, object]:
    inputs = [LIQUID_WINDOW_PATH, REGISTRY_PATH]
    return {
        **plan(),
        "status": "locked_before_run",
        "prereg_status": "locked_before_run",
        "locked_at_utc": locked_at_utc,
        "authority": [
            "reports/week20_project_charter.md::section 1 W20-2",
            "reports/_w20_section_gov.md::section 28.65",
        ],
        "inputs": input_digests(inputs),
        "blocking_conditions_at_lock": input_blockers(),
    }

def run(
    *,
    liquid_window_path: Path = LIQUID_WINDOW_PATH,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, object]:
    """Score the model and placebo arms.  Refuses until the prereg is frozen."""

    blockers = blocking_conditions()
    if blockers:
        raise SystemExit("W20-2 Step 2 is not armed: " + "; ".join(blockers))
    check_prereg_against_module()

    liquid_rows = read_csv_rows(liquid_window_path)
    registry_rows = read_csv_rows(registry_path)
    rows = usable_rows(liquid_rows, registry_rows)
    if len(rows) != EXPECTED_USABLE_ROWS:
        raise SystemExit(
            f"the usable row set moved: {len(rows)} vs the pinned {EXPECTED_USABLE_ROWS}"
        )
    features = featurize(rows)

    readings: list[RepeatReading] = []
    for target_index, name in enumerate(TARGETS):
        labels = np.array([float(row[f"y_{name}"]) for row in rows], dtype=np.float64)
        shuffled = labels.copy()
        random.Random(PLACEBO_SEED + target_index).shuffle(shuffled)
        for arm, values in (("model", labels), ("placebo", shuffled)):
            for seed in SEEDS:
                for fold_index, (train_index, test_index) in enumerate(
                    repeat_folds(rows, seed=seed)
                ):
                    x_train, x_test = features[train_index], features[test_index]
                    y_train, y_test = values[train_index], values[test_index]
                    prediction = fold_predictions(x_train, y_train, x_test, seed=seed)
                    baseline = np.full(len(test_index), float(np.mean(y_train)))
                    readings.append(
                        RepeatReading(
                            property=name,
                            arm=arm,
                            seed=seed,
                            fold=fold_index,
                            n_train=len(train_index),
                            n_test=len(test_index),
                            mae_K=float(np.mean(np.abs(prediction - y_test))),
                            baseline_mae_K=float(np.mean(np.abs(baseline - y_test))),
                        )
                    )

    per_property: dict[str, object] = {}
    for name in TARGETS:
        block: dict[str, object] = {}
        for arm in ("model", "placebo"):
            subset = [item for item in readings if item.property == name and item.arm == arm]
            seed_means = {
                str(seed): float(
                    np.mean([item.mae_K for item in subset if item.seed == seed])
                )
                for seed in SEEDS
            }
            seed_baselines = {
                str(seed): float(
                    np.mean([item.baseline_mae_K for item in subset if item.seed == seed])
                )
                for seed in SEEDS
            }
            model_mae = float(np.mean(list(seed_means.values())))
            baseline_mae = float(np.mean(list(seed_baselines.values())))
            block[arm] = {
                "cross_seed_mean_mae_K": model_mae,
                "cross_seed_mean_baseline_mae_K": baseline_mae,
                "relative_reduction_vs_baseline": 1.0 - model_mae / baseline_mae,
                "seed_mean_mae_K": seed_means,
                "seed_spread_K": float(max(seed_means.values()) - min(seed_means.values())),
            }
        model_block = block["model"]
        placebo_block = block["placebo"]
        assert isinstance(model_block, Mapping) and isinstance(placebo_block, Mapping)
        modelable = (
            model_block["relative_reduction_vs_baseline"] >= MODELABILITY_RELATIVE_MARGIN
        )
        placebo_modelable = (
            placebo_block["relative_reduction_vs_baseline"] >= MODELABILITY_RELATIVE_MARGIN
        )
        if modelable and placebo_modelable:
            verdict = "void_placebo_leak"
        elif modelable:
            verdict = "modelable"
        else:
            verdict = "not_modelable"
        block["verdict"] = verdict
        block["seed_spread_within_tolerance"] = (
            float(model_block["seed_spread_K"]) <= SEED_SPREAD_TOLERANCE_K
        )
        per_property[name] = block

    verdicts = [str(per_property[name]["verdict"]) for name in TARGETS]  # type: ignore[index]
    if "void_placebo_leak" in verdicts:
        overall = "void_placebo_leak"
    elif all(item == "modelable" for item in verdicts):
        overall = "modelable_all"
    elif any(item == "modelable" for item in verdicts):
        overall = "modelable_partial"
    else:
        overall = "not_modelable"

    availability = target_availability(liquid_rows)
    reference_rows = REFERENCE_TARGET["train_rows_per_property"]
    assert isinstance(reference_rows, Mapping)
    sample_gap = {
        "our_usable_rows": len(rows),
        "our_rows_per_target": availability,
        "reference_rows_per_property": dict(reference_rows),
        "ratio_min": float(reference_rows["min"]) / len(rows),
        "ratio_max": float(reference_rows["max"]) / len(rows),
        "statement": (
            "about 19-23x fewer rows than the Angew 2024 reference; the two MAE "
            "scales are therefore not comparable and no superiority claim is made"
        ),
    }

    return {
        **plan(),
        "status": "executed",
        "models_fitted": len(readings),
        "per_property": per_property,
        "verdict": overall,
        "sample_gap": sample_gap,
        "feature_matrix_shape": [len(rows), FEATURE_COUNT],
        "repeats": repeats_csv_rows(readings),
        "repeats_csv": portable_relative_path(REPEATS_CSV_PATH, root=REPOSITORY_ROOT),
        "dependency_versions": dependency_versions(),
        "inputs": input_digests([liquid_window_path, registry_path]),
        "prereg": prereg_reference(),
        "blocking_conditions": blocking_conditions(),
    }


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument(
        "--write-prereg",
        action="store_true",
        help="write the frozen preregistration JSON",
    )
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument(
        "--write-repeats-csv",
        action="store_true",
        help="write the per-fold repeats CSV",
    )
    parser.add_argument("--repeats-csv", type=Path, default=REPEATS_CSV_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write_prereg:
        prereg = prereg_summary(locked_at_utc=datetime.now(UTC).isoformat())
        args.prereg.write_text(
            json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    summary = run()
    if args.write_summary:
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.write_repeats_csv:
        write_repeats_csv(args.repeats_csv, summary["repeats"])  # type: ignore[arg-type]
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())