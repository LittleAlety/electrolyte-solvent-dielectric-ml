r"""Week 18 lane A / Appendix X lever 4 delta: does conformer SPREAD add anything?

Appendix X lever 4 migrated the frozen v0.3 physical block to the v0.4 conformer
protocol, but it carries only the conformer MEAN dipole
(``dipole_D_conformer_mean``).  Two compounds with the same mean dipole and very
different internal flexibility -- a rigid nitrile versus a gauche-happy diol -- are
indistinguishable to that block.  The v0.4 accounting already stores the spread per
compound (``dipole_D_conformer_std``, ``dipole_D_conformer_range``) and the number of
converged conformers, so this probe asks the next, separate question: with the pool,
the splitter, the scorer, the protocol and the head all frozen, does APPENDING those
columns to the winning dense configuration move the single-representation read?

Nothing on the frozen side moves.  The pool (2029 base training rows / 457 scored
rows over 97 compounds), the score mask, the GroupKFold-by-InChIKey splitter, the
protocol (5 folds x 10 repeats) and the frozen dense head (n_estimators=200 /
max_depth=2 / learning_rate=0.05) are the ones that produced 0.6080587938801277 on
``full_table_lever4`` / ``Physical``.  Arm ``reference_lever4`` has to reproduce that
reading bit for bit on seed 42, otherwise the probe refuses to report anything else.

Two guards are carried over from the shot-17 tradition: the seed-42 fold assignment
is compared against the frozen one before anything is trusted, and a scored compound
that straddles a fold aborts the run.  ``--placebo`` permutes the scored targets with
the frozen rng 2026 and is run as its own invocation.

This probe is diagnostic.  No reading it produces may be promoted: the frozen
headline stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv\Scripts\python.exe probes\dielectric_conformer_flexibility.py --placebo --jobs 4
    .venv\Scripts\python.exe probes\dielectric_conformer_flexibility.py --jobs 4
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_conformer_flexibility_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_conformer_flexibility_summary.json"
PLACEBO_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_conformer_flexibility_placebo_summary.json"
)
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_conformer_flexibility.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_conformer_flexibility"
CONFORMER_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"

REPRESENTATION = "Physical(lever4+flex)"
DEFAULT_SEEDS = "42,1234,2026,31337,7"
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
PLACEBO_RNG_SEED = 2026

ARM_REFERENCE = "reference_lever4"
ARM_PLUS = "plus_flexibility"
ARM_ONLY = "flexibility_only"
ARMS = (ARM_REFERENCE, ARM_PLUS, ARM_ONLY)

FLEXIBILITY_COLUMNS = (
    "dipole_D_conformer_std",
    "dipole_D_conformer_range",
    "n_conformers",
)

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
PARTIAL_TARGET_R2 = 0.60

CONFIRM_BAR_R2 = 0.02
PARTIAL_BAR_R2 = 0.005

REPEAT_COLUMNS_OUT = (
    "seed",
    "arm",
    "representation",
    "repeat",
    *METRIC_NAMES,
    "auc_gt15",
    "auc_gt30",
)

ARM_DESCRIPTIONS = {
    ARM_REFERENCE: "冻结稠密块 physical_lever4（13 列，构象均值偶极），锚点臂",
    ARM_PLUS: "physical_lever4 追加柔性列（构象偶极 std / range / 构象数）",
    ARM_ONLY: "只放柔性列（对照臂）",
}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--placebo", action="store_true")
    return parser.parse_args(argv)


def flexibility_map_from_conformer_rows(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, float]]:
    """One entry per compound that has a usable v0.4 conformer accounting row."""

    result: dict[str, dict[str, float]] = {}
    for row in rows:
        if str(row.get("status", "")).strip() != "ok":
            continue
        if not str(row.get("n_conformers", "")).strip():
            continue
        result[str(row["inchikey"])] = {
            column: float(str(row[column])) for column in FLEXIBILITY_COLUMNS
        }
    return result


def flexibility_coverage(rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    """Descriptive coverage of the source table, before anything is modelled."""

    usable = [
        row
        for row in rows
        if str(row.get("status", "")).strip() == "ok"
        and str(row.get("n_conformers", "")).strip()
    ]
    counts = sorted({int(str(row["n_conformers"])) for row in usable})
    std = [float(str(row["dipole_D_conformer_std"])) for row in usable]
    spread = [float(str(row["dipole_D_conformer_range"])) for row in usable]
    return {
        "source_rows": len(rows),
        "usable_rows": len(usable),
        "unusable_rows": len(rows) - len(usable),
        "n_conformers_values": counts,
        "n_conformers_is_constant": len(counts) == 1,
        "rows_with_nonzero_std": int(sum(1 for value in std if value > 0.0)),
        "rows_with_nonzero_range": int(sum(1 for value in spread if value > 0.0)),
        "max_std": float(max(std)) if std else 0.0,
        "max_range": float(max(spread)) if spread else 0.0,
    }


def flexibility_matrix(
    groups: Sequence[str],
    flex_map: Mapping[str, Mapping[str, float]],
) -> tuple[np.ndarray, dict[str, int]]:
    """The flexibility block, aligned with the pool's row order."""

    matrix = np.zeros((len(groups), len(FLEXIBILITY_COLUMNS)), dtype=np.float64)
    compounds: set[str] = set()
    hits = 0
    for index, key in enumerate(groups):
        entry = flex_map.get(str(key))
        if entry is None:
            continue
        matrix[index] = [float(entry[column]) for column in FLEXIBILITY_COLUMNS]
        compounds.add(str(key))
        hits += 1
    return matrix, {
        "rows": len(groups),
        "rows_with_a_conformer_row": hits,
        "rows_filled_with_zero": len(groups) - hits,
        "compounds_with_a_conformer_row": len(compounds),
    }


_FOLD_STATE: dict[str, object] = {}


def _init_fold_worker(
    matrices: Mapping[str, np.ndarray],
    groups: np.ndarray,
    target: np.ndarray,
    arms: Sequence[str],
) -> None:
    _FOLD_STATE["matrices"] = dict(matrices)
    _FOLD_STATE["groups"] = groups
    _FOLD_STATE["target"] = target
    _FOLD_STATE["arms"] = tuple(arms)


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    """One fold: the frozen head on every requested feature block."""

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
    if seed == ANCHOR_SEED:
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
        initargs=(matrices, group_array, fit_target, tuple(ARMS)),
    )
    buckets: dict[tuple[str, int], dict[str, list[np.ndarray]]] = {}
    straddling: list[int] = []
    for repeat, fold, train_index, test_index, predictions in results:  # type: ignore[misc]
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        straddling.append(int(np.intersect1d(group_array[train], group_array[test]).size))
        for arm in ARMS:
            prediction = np.asarray(predictions[arm], dtype=float)
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
                **{name: metrics[name] for name in (*METRIC_NAMES, "auc_gt15", "auc_gt30")},
            }
        )
    leak = {
        "folds": len(straddling),
        "folds_with_a_straddling_compound": int(sum(1 for count in straddling if count)),
        "max_straddling_compounds_in_a_fold": int(max(straddling)) if straddling else 0,
    }
    return repeat_rows, leak, signature_ok


def arm_summary(repeat_rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
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
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def load_placebo_block() -> dict[str, object]:
    if not PLACEBO_SUMMARY_PATH.is_file():
        return {"status": "not_run"}
    try:
        payload = json.loads(PLACEBO_SUMMARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "unreadable"}
    cross = dict(payload.get("cross_seed", {}))
    reference = cross.get(ARM_REFERENCE)
    collapsed = reference is not None and float(reference) < 0.5 * FROZEN_SINGLE_REPRESENTATION
    return {
        "status": "ran",
        "path": portable_relative_path(PLACEBO_SUMMARY_PATH, root=REPOSITORY_ROOT),
        "cross_seed": cross,
        "reference_below_half_of_the_frozen_anchor": bool(collapsed),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()
    jobs = max(1, int(args.jobs))
    seeds = tuple(int(token) for token in str(args.seeds).split(",") if token.strip())
    placebo = bool(args.placebo)
    if not seeds:
        print("no seeds requested")
        return 1
    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1
    if not CONFORMER_FEATURES_PATH.is_file():
        print("MISSING " + str(CONFORMER_FEATURES_PATH))
        return 1

    conformer_rows = read_csv_rows(CONFORMER_FEATURES_PATH)
    flex_map = flexibility_map_from_conformer_rows(conformer_rows)
    coverage = flexibility_coverage(conformer_rows)

    context = build_context()
    groups = [str(item) for item in context["groups"]]
    flex_matrix, flex_alignment = flexibility_matrix(groups, flex_map)
    physical_lever4 = np.asarray(context["physical_lever4"], dtype=float)
    matrices = {
        ARM_REFERENCE: physical_lever4,
        ARM_PLUS: np.hstack([physical_lever4, flex_matrix]),
        ARM_ONLY: flex_matrix,
    }
    scored_total = int(np.asarray(context["scored"]).sum())
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
        flush=True,
    )
    print(
        "flexibility: " + str(flex_alignment["rows_with_a_conformer_row"]) + " rows covered / "
        + str(flex_alignment["rows_filled_with_zero"]) + " rows filled with 0.0",
        flush=True,
    )
    print("arms: " + ", ".join(ARMS), flush=True)
    if placebo:
        print("PLACEBO run", flush=True)

    per_seed: dict[int, list[dict[str, object]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for seed in seeds:
        clock = time.perf_counter()
        repeat_rows, leak, signature_ok = evaluate_seed(
            seed, context, matrices, groups, jobs, placebo
        )
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        per_seed[seed] = repeat_rows
        spreadsheet.extend({"seed": int(seed), **row} for row in repeat_rows)
        leakage[str(seed)] = leak
        block = arm_summary(repeat_rows)
        for arm in ARMS:
            print(
                "  seed " + str(seed) + " | " + arm + " | "
                + format(float(block[arm]["r2_mean"]), ".6f")
                + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
                flush=True,
            )

    summaries = {seed: arm_summary(rows) for seed, rows in per_seed.items()}
    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    if ANCHOR_SEED in summaries and not placebo:
        measured = float(summaries[ANCHOR_SEED][ARM_REFERENCE]["r2_mean"])
        gap = abs(measured - FROZEN_SINGLE_REPRESENTATION)
        anchors_reproduced = gap <= ANCHOR_TOLERANCE
        anchor_rows.append(
            {
                "arm": ARM_REFERENCE,
                "seed": ANCHOR_SEED,
                "expected": FROZEN_SINGLE_REPRESENTATION,
                "measured": measured,
                "abs_gap": gap,
                "ok": anchors_reproduced,
            }
        )
        if not anchors_reproduced:
            print("the seed-42 anchor did not reproduce; refusing to report anything else")
            return 1

    leak_clean = all(
        block["folds_with_a_straddling_compound"] == 0
        and block["max_straddling_compounds_in_a_fold"] == 0
        for block in leakage.values()
    )
    if not leak_clean:
        print("a scored compound straddled a fold; refusing to continue")
        return 1

    cross_seed = {
        arm: float(np.mean([float(summaries[seed][arm]["r2_mean"]) for seed in seeds]))
        for arm in ARMS
    }
    per_seed_delta = {
        str(seed): float(summaries[seed][ARM_PLUS]["r2_mean"])
        - float(summaries[seed][ARM_REFERENCE]["r2_mean"])
        for seed in seeds
    }
    delta = cross_seed[ARM_PLUS] - cross_seed[ARM_REFERENCE]
    positive_seeds = int(sum(1 for value in per_seed_delta.values() if value > 0.0))

    if placebo:
        verdict = "placebo"
    elif delta >= CONFIRM_BAR_R2:
        verdict = "confirmed"
    elif delta >= PARTIAL_BAR_R2:
        verdict = "partial"
    else:
        verdict = "refuted"

    seed_rows: list[dict[str, object]] = []
    for seed in seeds:
        for arm in ARMS:
            seed_rows.append({"seed": int(seed), "arm": arm, **summaries[seed][arm]})

    finished_at_utc = _utc_now()
    summary_path = PLACEBO_SUMMARY_PATH if placebo else SUMMARY_PATH
    csv_path = ARTIFACTS_DIR / (
        ARTIFACT_STEM + "_placebo_repeats.csv" if placebo else ARTIFACT_STEM + "_repeats.csv"
    )
    write_csv_rows(csv_path, REPEAT_COLUMNS_OUT, spreadsheet)

    summary: dict[str, object] = {
        "schema": "dielectric_conformer_flexibility/summary@1",
        "generated_at_utc": finished_at_utc,
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "wall_seconds": float(time.perf_counter() - started),
        "jobs": int(jobs),
        "placebo_run": placebo,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": _sha256_of(PREREG_PATH),
            "status": str(prereg.get("status")),
        },
        "pool": {
            "base_rows": int(context["n_base"]),
            "scored_rows": scored_total,
            "expansion_rows": int(context["n_expansion"]),
            "rows": len(groups),
            "compounds": len(set(groups)),
            "expansion_report": context["expansion_report"],
            "lever4_report": context["lever4_report"],
        },
        "flexibility": {
            "source": portable_relative_path(CONFORMER_FEATURES_PATH, root=REPOSITORY_ROOT),
            "source_sha256": _sha256_of(CONFORMER_FEATURES_PATH),
            "columns": list(FLEXIBILITY_COLUMNS),
            "coverage": coverage,
            "alignment": flex_alignment,
            "missing_fill": "0.0",
        },
        "contract": {
            "representation": REPRESENTATION,
            "n_splits": 5,
            "n_repeats": 10,
            "seeds": [int(seed) for seed in seeds],
            "anchor_seed": ANCHOR_SEED,
            "arms": list(ARMS),
            "frozen_head_params": dict(XGB_PARAMS),
            "random_state": int(SEED),
            "flexibility_columns": list(FLEXIBILITY_COLUMNS),
        },
        "anchors": {
            "reproduced": bool(anchors_reproduced) if not placebo else None,
            "tolerance": ANCHOR_TOLERANCE,
            "rows": anchor_rows,
        },
        "arm_descriptions": dict(ARM_DESCRIPTIONS),
        "seed_rows": seed_rows,
        "cross_seed": cross_seed,
        "per_seed_delta_plus_minus_reference": per_seed_delta,
        "delta_plus_minus_reference": float(delta),
        "seeds_with_a_positive_delta": positive_seeds,
        "decision": {
            "confirm_bar": CONFIRM_BAR_R2,
            "partial_bar": PARTIAL_BAR_R2,
            "verdict": verdict,
            "promotable": False,
        },
        "placebo": (
            {
                "status": "this_run",
                "cross_seed": cross_seed,
                "reference_below_half_of_the_frozen_anchor": bool(
                    cross_seed[ARM_REFERENCE] < 0.5 * FROZEN_SINGLE_REPRESENTATION
                ),
            }
            if placebo
            else load_placebo_block()
        ),
        "leakage": {"by_seed": leakage, "clean": bool(leak_clean)},
        "frozen_control": {
            "headline": FROZEN_HEADLINE,
            "baseline": FROZEN_BASELINE,
            "single_representation_anchor": FROZEN_SINGLE_REPRESENTATION,
        },
        "artifacts": {
            "summary": portable_relative_path(summary_path, root=REPOSITORY_ROOT),
            "repeats_csv": portable_relative_path(csv_path, root=REPOSITORY_ROOT),
        },
    }
    write_json_stable(summary_path, summary)
    if not placebo:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(format_report(summary), encoding="utf-8")
    print("verdict: " + verdict, flush=True)
    print(
        "cross-seed: reference_lever4=" + format(cross_seed[ARM_REFERENCE], ".6f")
        + " plus_flexibility=" + format(cross_seed[ARM_PLUS], ".6f")
        + " flexibility_only=" + format(cross_seed[ARM_ONLY], ".6f")
        + " delta=" + format(delta, ".6f"),
        flush=True,
    )
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    cross = summary["cross_seed"]
    decision = summary["decision"]
    seed_rows = list(summary["seed_rows"])
    flexibility = summary["flexibility"]
    coverage = flexibility["coverage"]
    alignment = flexibility["alignment"]
    anchors = summary["anchors"]
    placebo = summary["placebo"]
    delta = float(summary["delta_plus_minus_reference"])
    verdict = str(decision["verdict"])
    reference_mean = float(cross[ARM_REFERENCE])
    plus_mean = float(cross[ARM_PLUS])
    only_mean = float(cross[ARM_ONLY])
    verdict_zh = {
        "confirmed": "confirmed（跨种子均值提升 ≥ +0.02）",
        "partial": "partial（跨种子均值提升 ≥ +0.005，但不到 +0.02）",
        "refuted": "refuted（跨种子均值提升 < +0.005）",
        "placebo": "placebo（安慰剂枪，不作判据）",
    }[verdict]

    lines: list[str] = []
    lines.append("# Week 18 lane A（P3）：构象方差 / 柔性特征")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(
        "**verdict = " + verdict_zh + "。** 柔性列追加臂 ``plus_flexibility`` 的 5 种子均值 = **"
        + format(plus_mean, ".6f") + "**，锚点臂 ``reference_lever4`` 的 5 种子均值 = **"
        + format(reference_mean, ".6f") + "**，差值 **" + format(delta, "+.6f") + "**。"
    )
    lines.append("")
    lines.append(
        "- 对照臂 ``flexibility_only``（只放柔性列）的 5 种子均值 = **"
        + format(only_mean, ".6f") + "**，"
        + str(int(summary["seeds_with_a_positive_delta"])) + "/"
        + str(len(seed_rows) // len(ARMS)) + " 个种子上 ``plus_flexibility`` 相对锚点为正。"
    )
    lines.append(
        "- 本枪是诊断枪：**任何读数都不 promote**。冻结头条仍是 **"
        + format(FROZEN_HEADLINE, ".16g") + "**，冻结基线仍是 **"
        + format(FROZEN_BASELINE, ".16g") + "**。"
    )
    lines.append("")
    lines.append("## 冻结对照与锚点")
    lines.append("")
    lines.append("- 判据臂读数口径：``full_table_lever4`` / ``Physical``（单表示），冻结读数 = **"
                 + format(FROZEN_SINGLE_REPRESENTATION, ".16g") + "**。")
    if anchors["rows"]:
        row = anchors["rows"][0]
        lines.append(
            "- 锚点复现（seed " + str(row["seed"]) + "）：期望 "
            + format(float(row["expected"]), ".16g") + "，实测 **"
            + format(float(row["measured"]), ".16g") + "**，绝对差 "
            + format(float(row["abs_gap"]), ".3g") + "，容差 "
            + format(float(anchors["tolerance"]), ".0e") + " ⇒ "
            + ("**逐位一致**" if row["ok"] else "**不一致（探针拒绝出数）**") + "。"
        )
    lines.append("")
    lines.append("## 主表：跨种子均值（端点 = 5 种子均值）")
    lines.append("")
    lines.append("| 臂 | R² 均值 | R² sd | R² 最小 | R² 最大 | 10 重复中 >0.60 | MAE 均值 | Spearman 均值 | AUC>30 均值 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        block = next(row for row in seed_rows if str(row["arm"]) == arm and row["seed"] == seed_rows[0]["seed"])
        values = [float(row["r2_mean"]) for row in seed_rows if str(row["arm"]) == arm]
        lines.append(
            "| ``" + arm + "`` | " + format(cross[arm], ".6f") + " | "
            + format(float(np.std(values, ddof=1)), ".6f") + " | "
            + format(min(values), ".6f") + " | " + format(max(values), ".6f") + " | "
            + str(block["repeats_above_060"]) + " | " + format(float(block["mae_mean"]), ".4f")
            + " | " + format(float(block["spearman_mean"]), ".4f") + " | "
            + format(float(block["auc_gt30_mean"]), ".4f") + " |"
        )
    lines.append("")
    lines.append("## 逐种子")
    lines.append("")
    lines.append("| 种子 | reference_lever4 | plus_flexibility | flexibility_only | Δ(plus − reference) |")
    lines.append("|---|---|---|---|---|")
    per_seed_delta = summary["per_seed_delta_plus_minus_reference"]
    for seed in sorted({int(row["seed"]) for row in seed_rows}):
        lookup = {str(row["arm"]): float(row["r2_mean"]) for row in seed_rows if int(row["seed"]) == seed}
        lines.append(
            "| " + str(seed) + " | " + format(lookup[ARM_REFERENCE], ".6f") + " | "
            + format(lookup[ARM_PLUS], ".6f") + " | " + format(lookup[ARM_ONLY], ".6f") + " | "
            + format(float(per_seed_delta[str(seed)]), "+.6f") + " |"
        )
    lines.append("")
    lines.append("## 柔性列的覆盖率（先看分布，再看模型）")
    lines.append("")
    lines.append("- 源表 **" + str(coverage["usable_rows"]) + " / " + str(coverage["source_rows"])
                 + "** 行可用（``status=ok`` 且 ``n_conformers`` 非空）。")
    lines.append(
        "- 池内对齐：**" + str(alignment["rows_with_a_conformer_row"]) + " / " + str(alignment["rows"])
        + "** 行有构象行（**" + str(alignment["compounds_with_a_conformer_row"]) + "** 个化合物），"
        + "其余 **" + str(alignment["rows_filled_with_zero"]) + "** 行按 0.0 填充。"
    )
    lines.append(
        "- 非零覆盖：``dipole_D_conformer_std`` **" + str(coverage["rows_with_nonzero_std"]) + "/"
        + str(coverage["usable_rows"]) + "**，``dipole_D_conformer_range`` **"
        + str(coverage["rows_with_nonzero_range"]) + "/" + str(coverage["usable_rows"]) + "**"
        + "（两者同号，std=0 时 range 必为 0）；最大 std = "
        + format(float(coverage["max_std"]), ".4f") + " D，最大 range = "
        + format(float(coverage["max_range"]), ".4f") + " D。"
    )
    lines.append(
        "- **坑（必须照实说）**：``n_conformers`` 在可用行上取值集合 = "
        + str(coverage["n_conformers_values"]) + " ⇒ **零方差列**；但缺失化合物被填 0，"
        + "所以它实际退化成「该化合物在不在构象表里」的指示变量，**不是柔性信息**。"
    )
    lines.append("")
    lines.append("## 泄漏审计")
    lines.append("")
    leakage = summary["leakage"]
    lines.append("- ``clean = " + str(bool(leakage["clean"])) + "``（全部 "
                 + str(sum(block["folds"] for block in leakage["by_seed"].values()))
                 + " 折里跨折化合物计数为 0）。")
    lines.append("")
    lines.append("## 安慰剂")
    lines.append("")

    lines.append(
        "- 口径限制（无论读数如何都成立）：本安慰剂只置换 457 个 scored 行的标签，"
        "训练池 2029 行里其余 1572 行仍带真标签；对以 ``full_base`` 训练的臂，它**不是**"
        "「把信息全部打断」的强安慰剂，读数偏高属结构性预期，不得据此宣布通过。"
    )
    if placebo.get("status") == "ran":
        reference_placebo = float(placebo["cross_seed"][ARM_REFERENCE])
        lines.append(
            "- 安慰剂（rng 2026 只置换 scored 行标签）下锚点臂跨种子均值 = **"
            + format(reference_placebo, ".6f") + "** ⇒ collapsed = **"
            + str(bool(placebo["reference_below_half_of_the_frozen_anchor"])) + "**（门 = 0.5 × 锚点 = "
            + format(0.5 * FROZEN_SINGLE_REPRESENTATION, ".6f") + "）。"
        )
    else:
        lines.append("- 安慰剂**未跑**（未找到 ``" + str(PLACEBO_SUMMARY_PATH.name) + "``）。")
    lines.append("")
    lines.append("## 边界声明")
    lines.append("")
    lines.append("- 本枪只动特征块，池 / 划分器 / 评分器 / 协议 / 头全部冻结；结论**只限本池与本配置**，不得外推。")
    lines.append("- 柔性列的 0.0 填充把「缺失」与「刚性（多构象但偶极一致）」混在同一取值上，是本枪已知的结构性弱点。")
    lines.append("- 端点定义为 5 种子均值；单一 seed 42 的读数不得单独引用为成绩。")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
