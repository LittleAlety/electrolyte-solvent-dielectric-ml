r"""Week 18 lane B / Appendix X lever 3 rescue: log space + isotonic calibration.

Appendix X lever 3 moved the epsilon fit into log space and the R^2 there is a healthy
0.551, but exponentiating the prediction back to the original scale is where it died:
the original-scale R^2 went negative (-0.105).  The reason is not the ranking -- the
log model still orders compounds sensibly -- it is that exp() of a regression that is
calibrated in log space is biased low on the original scale, and the bias is
scale-dependent.

This probe asks the next, separate question: if the log-space prediction is mapped
back through an isotonic regression fitted ONLY inside the training fold, does the
original-scale R^2 turn positive, and does it beat the frozen dense head?

Nothing on the frozen side moves.  The pool (2029 base training rows / 457 scored rows
over 97 compounds), the score mask, the GroupKFold-by-InChIKey splitter, the protocol
(5 folds x 10 repeats) and the frozen dense head (n_estimators=200 / max_depth=2 /
learning_rate=0.05) are the ones that produced 0.6080587938801277.  Arm
``reference_lever4`` has to reproduce that reading bit for bit on seed 42, otherwise
the probe refuses to report anything else.

Two guards are carried over from the shot-17 tradition: the seed-42 fold assignment is
compared against the frozen one before anything is trusted, and a scored compound that
straddles a fold aborts the run.  ``--placebo`` permutes the scored targets with the
frozen rng 2026 and is run as its own invocation.

Registered honesty: MAE / Spearman / AUC>30 are reported for every arm, and a gain on
those secondary scales may support at most a ``partial`` verdict -- it never licenses a
claim that the original-scale R^2 is good enough.

This probe is diagnostic.  No reading it produces may be promoted: the frozen headline
stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv\Scripts\python.exe probes\dielectric_log_scale_calibration.py --placebo --jobs 4
    .venv\Scripts\python.exe probes\dielectric_log_scale_calibration.py --jobs 4
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
from dielectric_representation_ablation import SEED, XGB_PARAMS, evaluate_repeat
from dielectric_representation_seed_robustness import build_context, splits_for
from export_results_common import write_json_stable
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import r2_score
from xgboost import XGBRegressor

from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_log_scale_calibration_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_log_scale_calibration_summary.json"
PLACEBO_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_log_scale_calibration_placebo_summary.json"
)
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_log_scale_calibration.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_log_scale_calibration"

REPRESENTATION = "Physical(lever4)"
DEFAULT_SEEDS = "42,1234,2026,31337,7"
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
PLACEBO_RNG_SEED = 2026

ARM_REFERENCE = "reference_lever4"
ARM_LOG_RAW = "log_space_raw"
ARM_LOG_ISOTONIC = "log_space_isotonic"
ARMS = (ARM_REFERENCE, ARM_LOG_RAW, ARM_LOG_ISOTONIC)

FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
PARTIAL_TARGET_R2 = 0.60

MAE_PARTIAL_MARGIN = 0.01
SPEARMAN_PARTIAL_MARGIN = 0.01
AUC_PARTIAL_MARGIN = 0.005

REPEAT_COLUMNS_OUT = (
    "seed",
    "arm",
    "representation",
    "repeat",
    *METRIC_NAMES,
    "auc_gt15",
    "auc_gt30",
    "log_r2",
)

ARM_DESCRIPTIONS = {
    ARM_REFERENCE: "冻结稠密块 physical_lever4，直接在 epsilon 原尺度拟合（锚点臂）",
    ARM_LOG_RAW: "同一特征与头，在 log(epsilon) 上拟合，exp 回原尺度",
    ARM_LOG_ISOTONIC: "log 空间模型 + 训练折内拟合的保序校准（IsotonicRegression）",
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


def safe_log_r2(target: np.ndarray, prediction: np.ndarray) -> float:
    """R^2 of the prediction read in log space: the scale lever 3 was measured on."""

    target = np.asarray(target, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if np.any(target <= 0.0) or np.any(prediction <= 0.0):
        return float("nan")
    if np.unique(target).size < 2:
        return float("nan")
    return float(r2_score(np.log(target), np.log(prediction)))



_FOLD_STATE: dict[str, object] = {}





def _init_fold_worker(
    features: np.ndarray,
    groups: np.ndarray,
    target: np.ndarray,
) -> None:
    _FOLD_STATE["features"] = features
    _FOLD_STATE["groups"] = groups
    _FOLD_STATE["target"] = target


def _fold_task(
    task: tuple[int, int, Sequence[int], Sequence[int]],
) -> tuple[int, int, list[int], list[int], dict[str, list[float]]]:
    """One fold: the frozen head in the original scale and in log space."""

    repeat, fold, train_index, test_index = task
    features = _FOLD_STATE["features"]
    target = _FOLD_STATE["target"]
    assert isinstance(features, np.ndarray)
    assert isinstance(target, np.ndarray)
    train = np.asarray(train_index)
    test = np.asarray(test_index)
    train_target = target[train]
    train_features = features[train]
    test_features = features[test]

    reference = XGBRegressor(**XGB_PARAMS, random_state=SEED)
    reference.fit(train_features, train_target)
    reference_prediction = np.maximum(np.asarray(reference.predict(test_features)), 1.0)

    log_model = XGBRegressor(**XGB_PARAMS, random_state=SEED)
    log_model.fit(train_features, np.log(train_target))
    log_train_prediction = np.asarray(log_model.predict(train_features), dtype=float)
    log_test_prediction = np.asarray(log_model.predict(test_features), dtype=float)
    raw_prediction = np.maximum(np.exp(log_test_prediction), 1.0)

    isotonic = IsotonicRegression(out_of_bounds="clip")
    isotonic.fit(log_train_prediction, train_target)
    isotonic_prediction = np.maximum(
        np.asarray(isotonic.predict(log_test_prediction), dtype=float), 1.0
    )

    predictions = {
        ARM_REFERENCE: [float(value) for value in reference_prediction],
        ARM_LOG_RAW: [float(value) for value in raw_prediction],
        ARM_LOG_ISOTONIC: [float(value) for value in isotonic_prediction],
    }
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
    features: np.ndarray,
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
        initargs=(features, group_array, fit_target),
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
        pooled_target = np.concatenate(bucket["target"])
        pooled_prediction = np.concatenate(bucket["prediction"])
        metrics = evaluate_repeat(pooled_target, pooled_prediction)
        repeat_rows.append(
            {
                "arm": arm,
                "representation": REPRESENTATION,
                "repeat": repeat,
                **{name: metrics[name] for name in (*METRIC_NAMES, "auc_gt15", "auc_gt30")},
                "log_r2": safe_log_r2(pooled_target, pooled_prediction),
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
            "r2_above_zero": int((r2 > 0.0).sum()),
            "repeats_above_060": int((r2 > PARTIAL_TARGET_R2).sum()),
            "mae_mean": float(np.mean([float(str(row["mae"])) for row in rows])),
            "spearman_mean": float(np.nanmean([float(str(row["spearman"])) for row in rows])),
            "auc_gt30_mean": float(np.nanmean([float(str(row["auc_gt30"])) for row in rows])),
            "log_r2_mean": float(np.nanmean([float(str(row["log_r2"])) for row in rows])),
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

    context = build_context()
    groups = [str(item) for item in context["groups"]]
    features = np.asarray(context["physical_lever4"], dtype=float)
    scored_total = int(np.asarray(context["scored"]).sum())
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
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
            seed, context, features, groups, jobs, placebo
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

    def mean_metric(arm: str, key: str) -> float:
        return float(np.mean([float(summaries[seed][arm][key]) for seed in seeds]))

    cross_seed = {
        arm: float(np.mean([float(summaries[seed][arm]["r2_mean"]) for seed in seeds]))
        for arm in ARMS
    }
    mae_gain = mean_metric(ARM_REFERENCE, "mae_mean") - mean_metric(ARM_LOG_ISOTONIC, "mae_mean")
    spearman_gain = mean_metric(ARM_LOG_ISOTONIC, "spearman_mean") - mean_metric(
        ARM_REFERENCE, "spearman_mean"
    )
    auc_gain = mean_metric(ARM_LOG_ISOTONIC, "auc_gt30_mean") - mean_metric(
        ARM_REFERENCE, "auc_gt30_mean"
    )
    secondary_gains = {
        "mae_improvement": float(mae_gain),
        "spearman_improvement": float(spearman_gain),
        "auc_gt30_improvement": float(auc_gain),
    }
    secondary_partial = (
        mae_gain >= MAE_PARTIAL_MARGIN
        or spearman_gain >= SPEARMAN_PARTIAL_MARGIN
        or auc_gain >= AUC_PARTIAL_MARGIN
    )
    if placebo:
        verdict = "placebo"
    elif cross_seed[ARM_LOG_ISOTONIC] > cross_seed[ARM_REFERENCE]:
        verdict = "improved"
    elif secondary_partial:
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
        "schema": "dielectric_log_scale_calibration/summary@1",
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
        "contract": {
            "representation": REPRESENTATION,
            "n_splits": 5,
            "n_repeats": 10,
            "seeds": [int(seed) for seed in seeds],
            "anchor_seed": ANCHOR_SEED,
            "arms": list(ARMS),
            "frozen_head_params": dict(XGB_PARAMS),
            "random_state": int(SEED),
            "calibration": "IsotonicRegression(out_of_bounds=clip), fitted in-sample on the training fold only",
            "optional_arm_not_run": "log_space_isotonic_spearman (isotonic is order-only, so a rank variant is identical)",
        },
        "anchors": {
            "reproduced": bool(anchors_reproduced) if not placebo else None,
            "tolerance": ANCHOR_TOLERANCE,
            "rows": anchor_rows,
        },
        "arm_descriptions": dict(ARM_DESCRIPTIONS),
        "seed_rows": seed_rows,
        "cross_seed": cross_seed,
        "secondary_gains": secondary_gains,
        "decision": {
            "verdict": verdict,
            "secondary_partial_rule_satisfied": bool(secondary_partial),
            "mae_partial_margin": MAE_PARTIAL_MARGIN,
            "spearman_partial_margin": SPEARMAN_PARTIAL_MARGIN,
            "auc_partial_margin": AUC_PARTIAL_MARGIN,
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
        + " log_space_raw=" + format(cross_seed[ARM_LOG_RAW], ".6f")
        + " log_space_isotonic=" + format(cross_seed[ARM_LOG_ISOTONIC], ".6f"),
        flush=True,
    )
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    cross = summary["cross_seed"]
    decision = summary["decision"]
    gains = summary["secondary_gains"]
    seed_rows = list(summary["seed_rows"])
    anchors = summary["anchors"]
    placebo = summary["placebo"]
    verdict = str(decision["verdict"])
    verdict_zh = {
        "improved": "improved（原尺度跨种子均值 R² 超过锚点臂）",
        "partial": "partial（原尺度 R² 未超锚点，但 MAE / Spearman / AUC 至少一项改善过门）",
        "refuted": "refuted（原尺度 R² 与三档次要口径都没有过门）",
        "placebo": "placebo（安慰剂枪，不作判据）",
    }[verdict]

    lines: list[str] = []
    lines.append("# Week 18 lane B（P6）：log 空间训练 + 保序校准回原尺度")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(
        "**verdict = " + verdict_zh + "。** 原尺度跨种子均值：``reference_lever4`` **"
        + format(float(cross[ARM_REFERENCE]), ".6f") + "**，``log_space_raw`` **"
        + format(float(cross[ARM_LOG_RAW]), ".6f") + "**，``log_space_isotonic`` **"
        + format(float(cross[ARM_LOG_ISOTONIC]), ".6f") + "**。"
    )
    lines.append("")
    lines.append(
        "- 次要口径（均值差，正数=保序臂更好）：MAE 改善 **"
        + format(float(gains["mae_improvement"]), "+.4f") + "**（门 +"
        + format(MAE_PARTIAL_MARGIN, ".2f") + "）、Spearman 改善 **"
        + format(float(gains["spearman_improvement"]), "+.4f") + "**（门 +"
        + format(SPEARMAN_PARTIAL_MARGIN, ".2f") + "）、AUC>30 改善 **"
        + format(float(gains["auc_gt30_improvement"]), "+.4f") + "**（门 +"
        + format(AUC_PARTIAL_MARGIN, ".3f") + "）。"
    )
    lines.append(
        "- **本枪是诊断枪，任何读数都不 promote**；也**不得**据此宣称原尺度 R² 达标。"
        "冻结头条仍是 **" + format(FROZEN_HEADLINE, ".16g") + "**，冻结基线仍是 **"
        + format(FROZEN_BASELINE, ".16g") + "**。"
    )
    lines.append("")
    lines.append("## 冻结对照与锚点")
    lines.append("")
    lines.append("- 锚点读数口径：``full_table_lever4`` / ``Physical``（单表示），冻结读数 = **"
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
    lines.append(
        "| 臂 | 原尺度 R² | R² sd | 原尺度 R²>0 的种子数 | MAE 均值 | Spearman 均值 | AUC>30 均值 | log 空间 R² 均值 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        block = next(row for row in seed_rows if str(row["arm"]) == arm and row["seed"] == seed_rows[0]["seed"])
        values = [float(row["r2_mean"]) for row in seed_rows if str(row["arm"]) == arm]
        positive = int(sum(1 for value in values if value > 0.0))
        lines.append(
            "| ``" + arm + "`` | " + format(float(cross[arm]), ".6f") + " | "
            + format(float(np.std(values, ddof=1)), ".6f") + " | " + str(positive) + "/"
            + str(len(values)) + " | " + format(float(block["mae_mean"]), ".4f") + " | "
            + format(float(block["spearman_mean"]), ".4f") + " | "
            + format(float(block["auc_gt30_mean"]), ".4f") + " | "
            + format(float(block["log_r2_mean"]), ".4f") + " |"
        )
    lines.append("")
    lines.append("## 逐种子")
    lines.append("")
    lines.append("| 种子 | reference_lever4 | log_space_raw | log_space_isotonic |")
    lines.append("|---|---|---|---|")
    for seed in sorted({int(row["seed"]) for row in seed_rows}):
        lookup = {str(row["arm"]): float(row["r2_mean"]) for row in seed_rows if int(row["seed"]) == seed}
        lines.append(
            "| " + str(seed) + " | " + format(lookup[ARM_REFERENCE], ".6f") + " | "
            + format(lookup[ARM_LOG_RAW], ".6f") + " | "
            + format(lookup[ARM_LOG_ISOTONIC], ".6f") + " |"
        )
    lines.append("")
    lines.append("## 校准口径（必须先看清再用数）")
    lines.append("")
    lines.append(
        "- 保序映射 ``IsotonicRegression(out_of_bounds='clip')`` 只用**训练折**：输入是该折 in-sample 的 log 空间预测，"
        "目标是该折的真实 epsilon。测试折的任何信息都不进入校准。"
    )
    lines.append(
        "- 已知乐观性来源：校准输入是 **in-sample** 预测（深度 2 的 XGB 在训练折上比折外更准），"
        "所以映射的坡度会比交叉拟合时更陡。本枪**没有**跑交叉拟合版本；这是下一枪的候选。"
    )
    lines.append(
        "- 可选臂 ``log_space_isotonic_spearman`` **未跑**：保序回归只依赖次序，按秩做保序与 "
        "``log_space_isotonic`` 数值恒等，注册一个恒等重复臂属于凑数。"
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
    lines.append("- 本枪只动目标尺度与回程映射，池 / 划分器 / 评分器 / 协议 / 头全部冻结；结论**只限本池与本配置**。")
    lines.append("- 次要口径（MAE / Spearman / AUC>30）的改善最多支持 ``partial``，**不得**当作原尺度 R² 达标。")
    lines.append("- 端点定义为 5 种子均值；单一 seed 42 的读数不得单独引用为成绩。")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
