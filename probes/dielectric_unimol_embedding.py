"""W18-P5 -- a pre-trained Uni-Mol representation as a frozen feature block.

The end-to-end 3D trunk could not be kept alive on this roster, but a pre-trained
embedding used as a frozen column block is a different object: the network is
frozen, the block is dense, and the frozen XGB head is untouched.  This is the
only representation family that has never been measured on this scoreboard.

Two stages under one pre-registration:

* stage 2 -- --build-embeddings calls the Uni-Mol runtime once, embeds every
  compound on the conformer roster and writes
  probes/artifacts/dielectric_unimol_embedding.csv with columns inchikey, smiles
  and dim_000 ... dim_{D-1}.  probes/build_unimol_embeddings.py is the standalone
  entry point for that stage when the runtime lives in a separate interpreter;
  --build-embeddings delegates to it.
* stage 1 -- the default invocation scores three arms over the pre-locked
  five-seed set: the frozen dense physical block (anchor arm), that block with
  the embedding block appended, and the embedding block alone.

If the runtime or the checkpoint is absent the lane does not guess.  It writes a
blocked summary that carries the measured blocker evidence, claims no reading,
promotes nothing and puts no number into any pool.  A blocked lane is not a
negative result and must never be quoted as one.

Run:
    .venv/Scripts/python.exe probes/dielectric_unimol_embedding.py --build-embeddings
    .venv/Scripts/python.exe probes/dielectric_unimol_embedding.py --jobs 2
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
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
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_pool_expansion_benchmark import fold_signature
from dielectric_representation_ablation import SEED, XGB_PARAMS, evaluate_repeat, read_csv_rows
from dielectric_representation_seed_robustness import build_context, splits_for
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable

from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_unimol_embedding_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_unimol_embedding_summary.json"
PLACEBO_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_unimol_embedding_placebo_summary.json"
)
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_unimol_embedding.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
EMBEDDINGS_PATH = ARTIFACTS_DIR / "dielectric_unimol_embedding.csv"
CONFORMER_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"

SCHEMA = "dielectric_unimol_embedding/summary@1"
REPRESENTATION = "Physical(lever4)+UniMol"
DEFAULT_SEEDS = "42,1234,2026,31337,7"
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
PLACEBO_RNG_SEED = 2026
CONFIRM_BAR = 0.02
PARTIAL_BAR = 0.005
PARTIAL_TARGET_R2 = 0.60

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_CROSS_SEED_ENDPOINT = 0.5861142332208197
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143

RUNTIME_MODULES = ("torch", "unimol_tools")
CHECKPOINT_ENVIRONMENT_VARIABLE = "UNIMOL_WEIGHTS_PATH"
CHECKPOINT_FILENAME = "mol_pre_all_h_220816.pt"
CHECKPOINT_REPOSITORY = "dptech/Uni-Mol-Models"
CHECKPOINT_MIRROR = (
    "https://hf-mirror.com/dptech/Uni-Mol-Models/resolve/main/" + CHECKPOINT_FILENAME
)

ARM_REFERENCE = "reference_lever4"
ARM_PLUS = "plus_unimol"
ARM_ONLY = "unimol_only"
ARMS = (ARM_REFERENCE, ARM_PLUS, ARM_ONLY)
ARM_DESCRIPTIONS = {
    ARM_REFERENCE: "frozen dense physical block, 13 columns, conformer-average dipole (anchor arm)",
    ARM_PLUS: "reference_lever4 with the frozen Uni-Mol embedding block appended",
    ARM_ONLY: "the frozen Uni-Mol embedding block alone (control arm)",
}

EMBEDDING_ID_COLUMNS = ("inchikey", "smiles")
REPEAT_COLUMNS_OUT = (
    "seed",
    "arm",
    "representation",
    "repeat",
    *METRIC_NAMES,
    "auc_gt15",
    "auc_gt30",
)

_FOLD_STATE: dict[str, object] = {}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=str, default=DEFAULT_SEEDS)
    parser.add_argument("--build-embeddings", action="store_true")
    parser.add_argument("--placebo", action="store_true")
    return parser.parse_args(argv)


def checkpoint_search_paths() -> tuple[Path, ...]:
    candidates: list[Path] = []
    override = os.environ.get(CHECKPOINT_ENVIRONMENT_VARIABLE, "").strip()
    if override:
        candidates.append(Path(override))
    home = Path.home()
    candidates.append(home / ".unimol" / CHECKPOINT_FILENAME)
    candidates.append(home / ".cache" / "unimol" / CHECKPOINT_FILENAME)
    candidates.append(ARTIFACTS_DIR / CHECKPOINT_FILENAME)
    return tuple(candidates)


def checkpoint_path() -> Path | None:
    for candidate in checkpoint_search_paths():
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    return None


def runtime_blockers(*, require_checkpoint: bool) -> list[dict[str, object]]:
    """Every reason the Uni-Mol runtime cannot be driven from this interpreter."""

    blockers: list[dict[str, object]] = []
    for module in RUNTIME_MODULES:
        spec = None
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError) as error:
            blockers.append(
                {"kind": "module_not_importable", "module": module, "evidence": repr(error)}
            )
            continue
        if spec is None:
            blockers.append(
                {
                    "kind": "missing_module",
                    "module": module,
                    "evidence": "importlib.util.find_spec returned None on " + sys.executable,
                }
            )
    if require_checkpoint and checkpoint_path() is None:
        blockers.append(
            {
                "kind": "missing_checkpoint",
                "checkpoint": CHECKPOINT_FILENAME,
                "repository": CHECKPOINT_REPOSITORY,
                "mirror": CHECKPOINT_MIRROR,
                "environment_variable": CHECKPOINT_ENVIRONMENT_VARIABLE,
                "searched": [str(path) for path in checkpoint_search_paths()],
            }
        )
    return blockers


def smiles_by_inchikey() -> dict[str, str]:
    table: dict[str, str] = {}
    for row in read_csv_rows(CONFORMER_FEATURES_PATH):
        key = str(row.get("inchikey", "")).strip()
        value = str(row.get("smiles", "")).strip()
        if key and value and key not in table:
            table[key] = value
    return table


def stage_two() -> int:
    """Build the embedding table through the standalone builder.

    The builder imports only the standard library and numpy at module level, so an
    isolated interpreter that carries the pre-trained stack can run it without the
    scoring dependencies.  --build-embeddings is the same code path, reached from
    inside this module.
    """

    blockers = runtime_blockers(require_checkpoint=False)
    if blockers:
        for blocker in blockers:
            print("BLOCKED " + json.dumps(blocker, ensure_ascii=False, sort_keys=True))
        return 2

    from build_unimol_embeddings import main as build_main

    override = checkpoint_path()
    extra = ["--checkpoint", str(override)] if override is not None else []
    return int(build_main(extra))


def embedding_table() -> tuple[dict[str, np.ndarray], int]:
    table: dict[str, np.ndarray] = {}
    dimension = 0
    for row in read_csv_rows(EMBEDDINGS_PATH):
        key = str(row.get("inchikey", "")).strip()
        if not key:
            continue
        vector: list[float] = []
        index = 0
        while True:
            column = "dim_" + format(index, "03d")
            if column not in row:
                break
            vector.append(float(row[column]))
            index += 1
        if not vector:
            continue
        table[key] = np.asarray(vector, dtype=float)
        dimension = max(dimension, len(vector))
    return table, dimension


def embedding_matrix(
    groups: Sequence[str], table: Mapping[str, np.ndarray], dimension: int
) -> tuple[np.ndarray, dict[str, object]]:
    matrix = np.zeros((len(groups), dimension), dtype=float)
    hits = 0
    missing: set[str] = set()
    for index, group in enumerate(groups):
        vector = table.get(str(group))
        if vector is None:
            missing.add(str(group))
            continue
        matrix[index, : vector.size] = vector
        hits += 1
    return matrix, {
        "rows": len(groups),
        "rows_with_an_embedding": hits,
        "unique_compounds_without_an_embedding": len(missing),
        "zero_filled_rows": len(groups) - hits,
    }


def _init_fold_worker(
    matrices: Mapping[str, np.ndarray],
    target: np.ndarray,
    arms: Sequence[str],
) -> None:
    _FOLD_STATE["matrices"] = dict(matrices)
    _FOLD_STATE["target"] = target
    _FOLD_STATE["arms"] = tuple(arms)


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    repeat, fold, train_index, test_index = task
    matrices = _FOLD_STATE["matrices"]
    target = _FOLD_STATE["target"]
    arms = _FOLD_STATE["arms"]
    assert isinstance(matrices, dict)
    assert isinstance(target, np.ndarray)
    assert isinstance(arms, tuple)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    train_target = target[train]
    predictions: dict[str, list[float]] = {}
    for arm in arms:
        features = matrices[str(arm)]
        model = XGBRegressor(**XGB_PARAMS, random_state=SEED)
        model.fit(features[train], train_target)
        predictions[str(arm)] = [
            float(value) for value in np.maximum(model.predict(features[test]), 1.0)
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
    matrices: Mapping[str, np.ndarray],
    groups: Sequence[str],
    jobs: int,
    placebo: bool,
) -> tuple[list[dict[str, object]], dict[str, int], bool]:
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    target = np.asarray(context["target"], dtype=float)
    group_array = np.asarray([str(item) for item in groups])
    splits = splits_for(seed, groups, scored, full_base)
    signature_ok = True
    if seed == ANCHOR_SEED and not placebo:
        frozen = fold_signature(list(context["frozen_splits"]))  # type: ignore[arg-type]
        if fold_signature(splits) != frozen:
            signature_ok = False
    fit_target = target
    if placebo:
        generator = np.random.default_rng(PLACEBO_RNG_SEED)
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
        initializer=_init_fold_worker,
        initargs=(matrices, fit_target, tuple(ARMS)),
    )
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    for repeat, fold, train_index, test_index, predictions in results:  # type: ignore[misc]
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(group_array[train], group_array[test]).size))
        for arm in ARMS:
            prediction = np.asarray(predictions[arm], dtype=float)
            bucket = buckets.setdefault(
                (str(arm), int(repeat)), {"target": [], "prediction": []}
            )
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
                **{name: metrics[name] for name in (*METRIC_NAMES, "auc_gt15", "auc_gt30")},
            }
        )
    leak = {
        "folds": len(straddling),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
    }
    return repeat_rows, leak, signature_ok


def arm_summary(
    repeat_rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    by_arm: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in repeat_rows:
        by_arm[str(row["arm"])].append(row)
    summary: dict[str, dict[str, object]] = {}
    for arm, rows in by_arm.items():
        r2 = np.asarray([float(str(row["r2"])) for row in rows], dtype=float)
        summary[arm] = {
            "repeats": len(rows),
            "r2_mean": float(r2.mean()),
            "r2_sd": float(r2.std(ddof=1)) if r2.size > 1 else 0.0,
            "r2_min": float(r2.min()),
            "r2_max": float(r2.max()),
            "repeats_above_060": int((r2 > PARTIAL_TARGET_R2).sum()),
            "mae_mean": float(np.mean([float(str(row["mae"])) for row in rows])),
            "spearman_mean": float(np.nanmean([float(str(row["spearman"])) for row in rows])),
            "auc_gt30_mean": float(np.nanmean([float(str(row["auc_gt30"])) for row in rows])),
        }
    return summary


def write_csv_rows(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator=chr(10))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def blocked_summary(
    prereg: Mapping[str, object],
    prereg_sha: str,
    blockers: Sequence[Mapping[str, object]],
    context: Mapping[str, object] | None,
    groups: Sequence[str],
    scored: np.ndarray | None,
) -> dict[str, object]:
    pool: dict[str, object] = {"scored_rows": 457, "scored_compounds": 97, "rows": 457}
    if context is not None and scored is not None:
        roster = sorted({str(groups[i]) for i in range(len(groups)) if bool(scored[i])})
        pool = {
            "base_rows": int(np.asarray(context["full_base"], dtype=bool).sum()),
            "scored_rows": int(scored.sum()),
            "scored_compounds": len(roster),
            "rows": len(groups),
        }
    return {
        "schema": SCHEMA,
        "stage": "blocked",
        "generated_at_utc": _utc_now(),
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": prereg_sha,
            "status": "locked_before_run",
        },
        "pool": pool,
        "blockers": [dict(blocker) for blocker in blockers],
        "blocked_rule": prereg.get("blocked_rule"),
        "contract": {
            "representation": REPRESENTATION,
            "arms": list(ARMS),
            "arm_descriptions": ARM_DESCRIPTIONS,
            "anchor_seed": ANCHOR_SEED,
            "anchor_value": FROZEN_SINGLE_REPRESENTATION,
            "seeds": list(prereg.get("seeds", [])),  # type: ignore[arg-type]
            "n_repeats": 10,
            "n_splits": 5,
            "frozen_head_params": dict(XGB_PARAMS),
        },
        "embedding": {
            "path": portable_relative_path(EMBEDDINGS_PATH, root=REPOSITORY_ROOT),
            "present": EMBEDDINGS_PATH.is_file(),
            "dimension": None,
        },
        "decision": {
            "verdict": "blocked",
            "promotable": False,
            "confirm_bar": CONFIRM_BAR,
            "partial_bar": PARTIAL_BAR,
            "reason": (
                "the pre-trained Uni-Mol runtime was not available to this interpreter, so the "
                "lane claims no reading; a blocked lane is not a negative result"
            ),
        },
        "readings_claimed": [],
        "artifacts": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "embeddings": portable_relative_path(EMBEDDINGS_PATH, root=REPOSITORY_ROOT),
        },
        "frozen_control": {
            "baseline_r2": FROZEN_BASELINE,
            "headline_r2": FROZEN_HEADLINE,
            "single_representation_r2": FROZEN_SINGLE_REPRESENTATION,
            "single_representation_cross_seed_mean": FROZEN_CROSS_SEED_ENDPOINT,
        },
    }


def format_report(summary: Mapping[str, object]) -> str:
    lines: list[str] = []
    lines.append("# W18-P5 -- Uni-Mol pre-trained embeddings as a feature block")
    lines.append("")
    lines.append("lane: W18-P5 (independent pre-registration, promotes nothing)")
    lines.append("")
    lines.append("- representation: " + REPRESENTATION)
    lines.append("- pool: " + json.dumps(summary.get("pool", {}), ensure_ascii=False))
    lines.append(
        "- frozen control: baseline " + repr(FROZEN_BASELINE) + ", headline " + repr(FROZEN_HEADLINE)
    )
    lines.append(
        "- frozen single representation "
        + repr(FROZEN_SINGLE_REPRESENTATION)
        + ", cross-seed endpoint "
        + repr(FROZEN_CROSS_SEED_ENDPOINT)
    )
    lines.append("")
    stage = str(summary.get("stage", ""))
    if stage == "blocked":
        lines.append("## Verdict: blocked (no reading claimed)")
        lines.append("")
        lines.append(str(summary.get("blocked_rule")))
        lines.append("")
        lines.append("Measured blockers:")
        lines.append("")
        for blocker in summary.get("blockers", []):  # type: ignore[union-attr]
            lines.append("- " + json.dumps(blocker, ensure_ascii=False, sort_keys=True))
        lines.append("")
        lines.append(
            "Stage 2 (the --build-embeddings stage) has not run in this environment, so there is "
            "no embedding table, no arm reading and no number this lane may be quoted for."
        )
        lines.append("")
    else:
        decision = summary.get("decision", {})
        assert isinstance(decision, dict)
        lines.append("## Verdict: " + str(decision.get("verdict")))
        lines.append("")
        lines.append(
            "Cross-seed endpoint: " + json.dumps(summary.get("cross_seed", {}), ensure_ascii=False)
        )
        lines.append("")
        lines.append("Delta vs the anchor arm: " + repr(summary.get("delta_plus_minus_reference")))
        lines.append("")
        lines.append(
            "Seeds with a positive delta: " + repr(summary.get("seeds_with_a_positive_delta"))
        )
        lines.append("")
    lines.append("## Boundaries")
    lines.append("")
    lines.append("- the lane adds no shot to the frozen main scoreboard")
    lines.append("- a blocked lane is not a negative result and must never be quoted as one")
    lines.append("- a synthetic or imputed embedding may never stand in for the pre-trained block")
    lines.append("")
    return chr(10).join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.time()
    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg_sha = canonical_text_sha256(PREREG_PATH)
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))

    if args.build_embeddings:
        return stage_two()

    context = build_context()
    groups = [str(item) for item in context["groups"]]
    scored = np.asarray(context["scored"], dtype=bool)
    placebo = bool(args.placebo)

    blockers: list[dict[str, object]] = []
    if not EMBEDDINGS_PATH.is_file():
        blockers.append(
            {
                "kind": "missing_embedding_table",
                "path": portable_relative_path(EMBEDDINGS_PATH, root=REPOSITORY_ROOT),
                "evidence": (
                    "stage 2 (--build-embeddings) has not written the pre-trained embedding table"
                ),
            }
        )
        blockers.extend(runtime_blockers(require_checkpoint=True))
    if blockers:
        summary = blocked_summary(prereg, prereg_sha, blockers, context, groups, scored)
        write_json(SUMMARY_PATH, summary)
        if not EMBEDDINGS_PATH.is_file():
            write_csv_rows(EMBEDDINGS_PATH, EMBEDDING_ID_COLUMNS, [])
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
        for blocker in blockers:
            print("BLOCKED " + json.dumps(blocker, ensure_ascii=False, sort_keys=True))
        print("wrote " + str(SUMMARY_PATH))
        print("wrote " + str(REPORT_PATH))
        return 0

    table, dimension = embedding_table()
    matrix, coverage = embedding_matrix(groups, table, dimension)
    reference = np.asarray(context["physical_lever4"], dtype=float)
    matrices = {
        ARM_REFERENCE: reference,
        ARM_PLUS: np.hstack([reference, matrix]),
        ARM_ONLY: matrix,
    }
    seeds = [int(item) for item in str(args.seeds).split(",") if item.strip()]
    seed_rows: list[dict[str, object]] = []
    repeat_rows_all: list[dict[str, object]] = []
    leak_rows: list[dict[str, object]] = []
    signature_ok = True
    for seed in seeds:
        repeat_rows, leak, ok = evaluate_seed(
            seed, context, matrices, groups, int(args.jobs), placebo
        )
        signature_ok = signature_ok and bool(ok)
        summary_by_arm = arm_summary(repeat_rows)
        for arm, block in sorted(summary_by_arm.items()):
            seed_rows.append({"seed": int(seed), "arm": arm, **block})
        leak_rows.append({"seed": int(seed), **leak})
        for row in repeat_rows:
            repeat_rows_all.append({"seed": int(seed), **row})
        per_seed = {
            str(block["arm"]): float(str(block["r2_mean"]))
            for block in seed_rows
            if int(str(block["seed"])) == int(seed)
        }
        line = f"  seed {seed} | " + " | ".join(
            f"{arm} {per_seed[arm]:.6f}" for arm in ARMS
        )
        print(line + f"  ({time.time() - started:.1f}s)")

    repeats_name = (
        "dielectric_unimol_embedding_placebo_repeats.csv"
        if placebo
        else "dielectric_unimol_embedding_repeats.csv"
    )
    write_csv_rows(
        ARTIFACTS_DIR / repeats_name,
        REPEAT_COLUMNS_OUT,
        [
            {column: row[column] for column in REPEAT_COLUMNS_OUT}
            for row in repeat_rows_all
        ],
    )

    cross_seed = {
        arm: float(
            np.mean([float(str(row["r2_mean"])) for row in seed_rows if str(row["arm"]) == arm])
        )
        for arm in ARMS
    }

    def reading(seed: int, arm: str) -> float:
        return next(
            float(str(row["r2_mean"]))
            for row in seed_rows
            if int(str(row["seed"])) == int(seed) and str(row["arm"]) == arm
        )

    deltas = {int(seed): reading(int(seed), ARM_PLUS) - reading(int(seed), ARM_REFERENCE) for seed in seeds}
    delta_plus = cross_seed[ARM_PLUS] - cross_seed[ARM_REFERENCE]
    positive = sum(1 for value in deltas.values() if value > 0)
    anchor_reading = reading(ANCHOR_SEED, ARM_REFERENCE)
    anchor_ok = abs(anchor_reading - FROZEN_SINGLE_REPRESENTATION) <= ANCHOR_TOLERANCE

    if not placebo and not anchor_ok:
        print("ANCHOR MISMATCH " + repr(anchor_reading) + " vs " + repr(FROZEN_SINGLE_REPRESENTATION))
        return 1
    if not placebo and not signature_ok:
        print("FOLD SIGNATURE MISMATCH at seed " + str(ANCHOR_SEED))
        return 1

    if placebo:
        verdict = "placebo"
        promotable = False
    elif delta_plus >= CONFIRM_BAR and positive >= 4:
        verdict = "confirmed"
        promotable = True
    elif delta_plus >= PARTIAL_BAR:
        verdict = "partial"
        promotable = False
    else:
        verdict = "refuted"
        promotable = False

    summary = {
        "schema": SCHEMA,
        "stage": "placebo" if placebo else "reading",
        "generated_at_utc": _utc_now(),
        "wall_seconds": time.time() - started,
        "jobs": int(args.jobs),
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": prereg_sha,
            "status": "locked_before_run",
        },
        "pool": {
            "base_rows": int(np.asarray(context["full_base"], dtype=bool).sum()),
            "scored_rows": int(scored.sum()),
            "scored_compounds": len(
                {groups[index] for index in range(len(groups)) if bool(scored[index])}
            ),
            "rows": len(groups),
        },
        "embedding": {
            "path": portable_relative_path(EMBEDDINGS_PATH, root=REPOSITORY_ROOT),
            "present": True,
            "dimension": int(dimension),
            "table_rows": len(table),
            "coverage": coverage,
        },
        "contract": {
            "representation": REPRESENTATION,
            "arms": list(ARMS),
            "arm_descriptions": ARM_DESCRIPTIONS,
            "anchor_seed": ANCHOR_SEED,
            "anchor_value": FROZEN_SINGLE_REPRESENTATION,
            "seeds": seeds,
            "n_repeats": 10,
            "n_splits": 5,
            "frozen_head_params": dict(XGB_PARAMS),
        },
        "anchors": {
            "seed": ANCHOR_SEED,
            "arm": ARM_REFERENCE,
            "value": anchor_reading,
            "expected": FROZEN_SINGLE_REPRESENTATION,
            "tolerance": ANCHOR_TOLERANCE,
            "reproduced": bool(anchor_ok),
            "fold_signature_matched": bool(signature_ok),
        },
        "seed_rows": seed_rows,
        "cross_seed": cross_seed,
        "per_seed_delta_plus_minus_reference": {str(seed): value for seed, value in sorted(deltas.items())},
        "delta_plus_minus_reference": delta_plus,
        "seeds_with_a_positive_delta": int(positive),
        "decision": {
            "verdict": verdict,
            "promotable": bool(promotable),
            "confirm_bar": CONFIRM_BAR,
            "partial_bar": PARTIAL_BAR,
            "compared_against": FROZEN_CROSS_SEED_ENDPOINT,
        },
        "leakage": leak_rows,
        "frozen_control": {
            "baseline_r2": FROZEN_BASELINE,
            "headline_r2": FROZEN_HEADLINE,
            "single_representation_r2": FROZEN_SINGLE_REPRESENTATION,
            "single_representation_cross_seed_mean": FROZEN_CROSS_SEED_ENDPOINT,
        },
        "artifacts": {
            "summary": portable_relative_path(
                PLACEBO_SUMMARY_PATH if placebo else SUMMARY_PATH, root=REPOSITORY_ROOT
            ),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "embeddings": portable_relative_path(EMBEDDINGS_PATH, root=REPOSITORY_ROOT),
        },
    }
    write_json(PLACEBO_SUMMARY_PATH if placebo else SUMMARY_PATH, summary)
    if not placebo:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("verdict=" + verdict + " delta=" + repr(delta_plus) + " positive_seeds=" + str(positive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
