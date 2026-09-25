"""Verify the pre-registered leave-EC-out sensitivity artefact (D1).

This verifier never refits.  It reads the summary and the tracked prediction
table and recomputes every published number from the latter, including the
paired confidence intervals, p-values, per-repeat deltas, representation
rankings and EC's rank percentile.  It also checks the invariants that make the
probe meaningful:

* the baseline arm reproduces the frozen benchmark prediction table exactly;
* every one of the 236 compounds keeps its frozen fold identifier in both arms;
* EC is held out exactly once per repeat and never trains;
* the 235-row paired deltas in the summary equal the deltas recomputed from
  the prediction table;
* no input file moved after the probe was written;
* the summary contains no missing or non-finite published value.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    _safe_spearman,
    read_csv_rows,
    regression_metrics,
)
from v032_controlled_comparison import _paired_stats

from electrolyte_ml.exporting import canonical_text_sha256

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EXPECTED_COMPOUND_COUNT = 236
EXPECTED_REMAINING_COUNT = 235
PAIRED_METRICS = ("r2", "mae", "rmse", "spearman")
TOLERANCE = 1e-6

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_leave_ec_out_summary.json"
PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_leave_ec_out_predictions.csv"
)
FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
EXCLUSIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_v03_exclusions.csv"
FROZEN_PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "v032_ablation_predictions.csv"
)


def _metrics_from(pairs: list[tuple[float, float]]) -> dict[str, float]:
    target = np.asarray([pair[0] for pair in pairs], dtype=float)
    prediction = np.asarray([pair[1] for pair in pairs], dtype=float)
    values = regression_metrics(target, prediction)
    values["spearman"] = _safe_spearman(target, prediction)
    return values


def _rank_percentile(values: np.ndarray, value: float) -> float:
    return float(100.0 * np.mean(np.asarray(values, dtype=float) <= float(value)))


def _is_finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _finite_csv_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _close(recorded: object, expected: object, label: str, errors: list[str]) -> None:
    if not _is_finite(recorded):
        errors.append(f"{label}: missing or non-finite ({recorded!r})")
        return
    if not _is_finite(expected):
        errors.append(f"{label}: recomputed value is non-finite ({expected!r})")
        return
    if abs(float(recorded) - float(expected)) > TOLERANCE:
        errors.append(f"{label}: {recorded!r} != {expected!r}")


def _non_finite_paths(node: object, path: str = "$") -> list[str]:
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            found.extend(_non_finite_paths(value, f"{path}.{key}"))
        return found
    if isinstance(node, list):
        found = []
        for index, value in enumerate(node):
            found.extend(_non_finite_paths(value, f"{path}[{index}]"))
        return found
    if isinstance(node, float) and not math.isfinite(node):
        return [path]
    return []


def verify(
    *,
    summary_path: Path = SUMMARY_PATH,
    predictions_path: Path = PREDICTIONS_PATH,
    frozen_predictions_path: Path = FROZEN_PREDICTIONS_PATH,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def record(name: str, errors: list[str], detail: str = "") -> None:
        checks.append({"name": name, "passed": not errors, "errors": errors, "detail": detail})

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = read_csv_rows(predictions_path)

    schema_errors = []
    if summary.get("schema_version") != 1 or summary.get("probe") != "dielectric_leave_ec_out_sensitivity":
        schema_errors.append(
            f"unexpected summary header: {summary.get('schema_version')}/{summary.get('probe')}"
        )
    for path in _non_finite_paths(summary):
        schema_errors.append(f"non-finite summary value at {path}")
    record("summary schema", schema_errors)

    selection_errors = []
    if summary.get("selection_effect") != "none":
        selection_errors.append(f"selection_effect={summary.get('selection_effect')!r}")
    if summary.get("model_selection_impact") != "none":
        selection_errors.append(
            f"model_selection_impact={summary.get('model_selection_impact')!r}"
        )
    if summary.get("removed_inchikey") != EC_INCHIKEY:
        selection_errors.append("removed_inchikey is not EC")
    record("report-only pre-registration", selection_errors)

    count_errors = []
    expected = {
        "baseline_fit_count": EXPECTED_COMPOUND_COUNT,
        "leave_ec_out_fit_count": EXPECTED_REMAINING_COUNT,
        "ec_in_training_folds": 0,
        "ec_holdout_repeats": N_REPEATS,
        "ec_training_removals": N_REPEATS * (N_SPLITS - 1),
        "baseline_matches_frozen_predictions": True,
        "same_fold_ids_for_235": True,
        "failed_physical_feature_count": 4,
        "withheld_not_model_ready_count": 1,
        "removed_name": "ethylene carbonate",
        "removed_temperature_K": 313.15,
        "removed_temperature_band": "extended_temperature",
        "frozen_prediction_rows_checked": EXPECTED_COMPOUND_COUNT
        * N_REPEATS
        * len(REPRESENTATIONS),
        "excluded_count": 5,
        "fold_scheme": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
        "seed_scheme": "42 + global RepeatedKFold split index",
        "fold_source": "data/processed/v032_ablation_predictions.csv",
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            count_errors.append(f"{key}={summary.get(key)!r} != {value!r}")
    preregistration = summary.get("preregistration")
    if not isinstance(preregistration, str) or not (
        "Report-only robustness probe" in preregistration
        and "cannot trigger a post-hoc model switch" in preregistration
    ):
        count_errors.append("preregistration text is missing or weakened")
    expected_outputs = {
        "summary_json": "probes/dielectric_leave_ec_out_summary.json",
        "predictions_csv": "probes/artifacts/dielectric_leave_ec_out_predictions.csv",
        "plot": "probes/artifacts/dielectric_leave_ec_out.png",
    }
    if summary.get("outputs") != expected_outputs:
        count_errors.append(f"outputs={summary.get('outputs')!r} != {expected_outputs!r}")
    record("recorded invariants", count_errors)

    input_errors = []
    inputs = summary.get("inputs", {})
    for key, path in (
        ("dataset_sha256", REPOSITORY_ROOT / "data" / "dielectric_v03.csv"),
        ("features_sha256", FEATURES_PATH),
        ("exclusions_sha256", EXCLUSIONS_PATH),
        ("frozen_predictions_sha256", frozen_predictions_path),
    ):
        live = canonical_text_sha256(path)
        if inputs.get(key) != live:
            input_errors.append(f"{key} is stale: {inputs.get(key)} != {live}")
    record("input digests are current", input_errors)

    shape_errors = []
    expected_rows = EXPECTED_COMPOUND_COUNT * N_REPEATS * len(REPRESENTATIONS) * 2
    if len(rows) != expected_rows:
        shape_errors.append(f"{len(rows)} prediction rows, expected {expected_rows}")
    arms = {row["arm"] for row in rows}
    if arms != {"baseline", "leave_ec_out"}:
        shape_errors.append(f"unexpected arms: {sorted(arms)}")
    representations = {row["representation"] for row in rows}
    if representations != set(REPRESENTATIONS):
        shape_errors.append(f"unexpected representations: {sorted(representations)}")
    repeats = {int(row["repeat"]) for row in rows}
    if repeats != set(range(N_REPEATS)):
        shape_errors.append(f"unexpected repeats: {sorted(repeats)}")
    for row in rows:
        if not _finite_csv_number(row.get("prediction")) or not _finite_csv_number(row.get("target")):
            shape_errors.append(
                f"{row.get('representation')}/{row.get('repeat')}/{row.get('arm')}/"
                f"{row.get('inchikey')}: non-finite target or prediction"
            )
            continue
        try:
            fold = int(row["fold"])
        except (KeyError, TypeError, ValueError):
            shape_errors.append(f"{row.get('inchikey')}: missing or invalid fold")
            continue
        if fold < 0 or fold >= N_SPLITS:
            shape_errors.append(f"{row.get('inchikey')}: fold {fold} outside 0..{N_SPLITS - 1}")
    record("prediction table shape", shape_errors)

    frozen_rows = read_csv_rows(frozen_predictions_path)
    frozen: dict[tuple[str, int, str], tuple[str, str]] = {
        (row["representation"], int(row["repeat"]), row["inchikey"]): (
            row["prediction"],
            row["fold"],
        )
        for row in frozen_rows
    }
    baseline_mismatch = []
    fold_mismatch = []
    for row in rows:
        key = (row["representation"], int(row["repeat"]), row["inchikey"])
        expected_row = frozen.get(key)
        if expected_row is None:
            baseline_mismatch.append(row)
            continue
        if row["arm"] == "baseline" and row["prediction"] != expected_row[0]:
            baseline_mismatch.append(row)
        if str(row["fold"]) != str(expected_row[1]):
            fold_mismatch.append(row)
    record(
        "baseline arm reproduces the frozen benchmark",
        []
        if not baseline_mismatch
        and len(frozen) == EXPECTED_COMPOUND_COUNT * N_REPEATS * len(REPRESENTATIONS)
        else [
            f"{len(baseline_mismatch)} baseline rows differ from the frozen table",
            f"{len(frozen)} frozen rows indexed",
        ],
        f"{len(frozen)} frozen rows compared",
    )

    grouped: dict[tuple[str, int, str], dict[str, tuple[float, float]]] = defaultdict(dict)
    for row in rows:
        key = (row["representation"], int(row["repeat"]), row["arm"])
        grouped[key][row["inchikey"]] = (float(row["target"]), float(row["prediction"]))

    fold_errors = []
    non_ec_fold_mismatch = [
        row for row in fold_mismatch if row["inchikey"] != EC_INCHIKEY
    ]
    if fold_mismatch:
        fold_errors.append(f"{len(fold_mismatch)} fold values differ from the frozen assignment")
    if non_ec_fold_mismatch:
        fold_errors.append(
            f"{len(non_ec_fold_mismatch)} non-EC fold values differ from the frozen assignment"
        )
    for representation in REPRESENTATIONS:
        for repeat in range(N_REPEATS):
            base = grouped.get((representation, repeat, "baseline"), {})
            treat = grouped.get((representation, repeat, "leave_ec_out"), {})
            if len(base) != EXPECTED_COMPOUND_COUNT or len(treat) != EXPECTED_COMPOUND_COUNT:
                fold_errors.append(
                    f"{representation}/{repeat}: baseline={len(base)} treatment={len(treat)}"
                )
            if EC_INCHIKEY not in base or EC_INCHIKEY not in treat:
                fold_errors.append(f"{representation}/{repeat}: EC missing")
    record("every repeat scores all 236 compounds", fold_errors)

    metric_errors = []
    metrics = summary.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    recomputed_by_representation: dict[str, dict[str, dict]] = {}
    for representation in REPRESENTATIONS:
        block = metrics.get(representation)
        if not isinstance(block, dict):
            metric_errors.append(f"{representation}: missing metrics block")
            continue
        base_235: list[dict[str, float]] = []
        treat_235: list[dict[str, float]] = []
        base_236: list[dict[str, float]] = []
        complete = True
        for repeat in range(N_REPEATS):
            base = grouped.get((representation, repeat, "baseline"))
            treat = grouped.get((representation, repeat, "leave_ec_out"))
            if not base or not treat or len(base) != EXPECTED_COMPOUND_COUNT or len(treat) != EXPECTED_COMPOUND_COUNT:
                metric_errors.append(f"{representation}/{repeat}: incomplete grouped rows")
                complete = False
                break
            survivors = [key for key in base if key != EC_INCHIKEY]
            base_235.append(_metrics_from([base[key] for key in survivors]))
            treat_235.append(_metrics_from([treat[key] for key in survivors]))
            base_236.append(_metrics_from(list(base.values())))
        if not complete:
            continue
        recomputed_paired: dict[str, dict] = {}
        for metric in PAIRED_METRICS:
            label = f"{representation}/{metric}"
            _close(
                block.get("baseline_full_236", {}).get(metric, {}).get("mean"),
                float(np.mean([row[metric] for row in base_236])),
                f"{label}/baseline_full_236.mean",
                metric_errors,
            )
            _close(
                block.get("baseline_full_236", {}).get(metric, {}).get("std"),
                float(np.std([row[metric] for row in base_236], ddof=1)),
                f"{label}/baseline_full_236.std",
                metric_errors,
            )
            for arm_key, repeat_rows in (
                ("baseline_surviving_235", base_235),
                ("leave_ec_out_235", treat_235),
            ):
                _close(
                    block.get(arm_key, {}).get(metric, {}).get("mean"),
                    float(np.mean([row[metric] for row in repeat_rows])),
                    f"{label}/{arm_key}.mean",
                    metric_errors,
                )
                _close(
                    block.get(arm_key, {}).get(metric, {}).get("std"),
                    float(np.std([row[metric] for row in repeat_rows], ddof=1)),
                    f"{label}/{arm_key}.std",
                    metric_errors,
                )
            recorded = block.get("paired_leave_ec_out_minus_baseline_235", {}).get(metric, {})
            recomputed = _paired_stats(
                [row[metric] for row in base_235], [row[metric] for row in treat_235]
            )
            recomputed_paired[metric] = recomputed
            for field in (
                "n_pairs",
                "baseline_mean",
                "augmented_mean",
                "delta_mean",
                "delta_std",
                "paired_t_pvalue",
                "wilcoxon_pvalue",
            ):
                _close(recorded.get(field), recomputed[field], f"{label}/paired.{field}", metric_errors)
            recorded_ci = recorded.get("delta_ci95", [])
            recomputed_ci = recomputed["delta_ci95"]
            if not isinstance(recorded_ci, list) or len(recorded_ci) != 2:
                metric_errors.append(f"{label}/paired.delta_ci95: missing or wrong length")
            else:
                for index, (got, want) in enumerate(zip(recorded_ci, recomputed_ci, strict=True)):
                    _close(got, want, f"{label}/paired.delta_ci95[{index}]", metric_errors)
            recorded_deltas = recorded.get("per_repeat_delta", [])
            if not isinstance(recorded_deltas, list) or len(recorded_deltas) != N_REPEATS:
                metric_errors.append(f"{label}/paired.per_repeat_delta: missing or wrong length")
            else:
                for index, (got, want) in enumerate(
                    zip(recorded_deltas, recomputed["per_repeat_delta"], strict=True)
                ):
                    _close(got, want, f"{label}/paired.per_repeat_delta[{index}]", metric_errors)
        baseline_ranking = sorted(
            PAIRED_METRICS,
            key=lambda metric: (
                recomputed_paired[metric]["baseline_mean"]
                if metric in ("mae", "rmse")
                else -recomputed_paired[metric]["baseline_mean"]
            ),
        )
        treatment_ranking = sorted(
            PAIRED_METRICS,
            key=lambda metric: (
                recomputed_paired[metric]["augmented_mean"]
                if metric in ("mae", "rmse")
                else -recomputed_paired[metric]["augmented_mean"]
            ),
        )
        if block.get("metric_ranking_baseline") != baseline_ranking:
            metric_errors.append(f"{representation}: baseline metric ranking mismatch")
        if block.get("metric_ranking_leave_ec_out") != treatment_ranking:
            metric_errors.append(f"{representation}: leave-EC-out metric ranking mismatch")
        if block.get("ranking_changed") != (baseline_ranking != treatment_ranking):
            metric_errors.append(f"{representation}: ranking_changed mismatch")
        recomputed_by_representation[representation] = recomputed_paired

        ec_block = summary.get("ec_leave_one_out", {}).get(representation, {})
        ec_rows = [
            grouped.get((representation, repeat, "leave_ec_out"), {}).get(EC_INCHIKEY)
            for repeat in range(N_REPEATS)
        ]
        if any(row is None for row in ec_rows):
            metric_errors.append(f"{representation}: EC row missing from the leave-EC-out arm")
            continue
        ec_predictions = np.asarray([row[1] for row in ec_rows], dtype=float)
        ec_target = ec_rows[0][0]
        treatment_rows = grouped.get((representation, 0, "leave_ec_out"), {})
        survivor_means = np.asarray(
            [
                float(
                    np.mean(
                        [
                            grouped[(representation, repeat, "leave_ec_out")][key][1]
                            for repeat in range(N_REPEATS)
                        ]
                    )
                )
                for key in treatment_rows
                if key != EC_INCHIKEY
            ],
            dtype=float,
        )
        _close(ec_block.get("target"), ec_target, f"{representation}/EC.target", metric_errors)
        _close(
            ec_block.get("prediction_mean"),
            float(np.mean(ec_predictions)),
            f"{representation}/EC.prediction_mean",
            metric_errors,
        )
        _close(
            ec_block.get("prediction_std"),
            float(np.std(ec_predictions, ddof=1)),
            f"{representation}/EC.prediction_std",
            metric_errors,
        )
        _close(
            ec_block.get("prediction_min"),
            float(np.min(ec_predictions)),
            f"{representation}/EC.prediction_min",
            metric_errors,
        )
        _close(
            ec_block.get("prediction_max"),
            float(np.max(ec_predictions)),
            f"{representation}/EC.prediction_max",
            metric_errors,
        )
        _close(
            ec_block.get("abs_error_mean"),
            float(np.mean(np.abs(ec_predictions - ec_target))),
            f"{representation}/EC.abs_error_mean",
            metric_errors,
        )
        _close(
            ec_block.get("signed_error_mean"),
            float(np.mean(ec_predictions - ec_target)),
            f"{representation}/EC.signed_error_mean",
            metric_errors,
        )
        _close(
            ec_block.get("rank_percentile_among_235"),
            _rank_percentile(survivor_means, float(np.mean(ec_predictions))),
            f"{representation}/EC.rank_percentile_among_235",
            metric_errors,
        )

    expected_family_ranking: dict[str, object] = {}
    if set(recomputed_by_representation) == set(REPRESENTATIONS):
        for arm, mean_key in (("baseline", "baseline_mean"), ("leave_ec_out", "augmented_mean")):
            expected_family_ranking[arm] = {
                metric: sorted(
                    REPRESENTATIONS,
                    key=lambda representation: recomputed_by_representation[representation][
                        metric
                    ][mean_key],
                    reverse=metric in ("r2", "spearman"),
                )
                for metric in PAIRED_METRICS
            }
        expected_family_ranking["changed"] = (
            expected_family_ranking["baseline"] != expected_family_ranking["leave_ec_out"]
        )
        if summary.get("family_ranking") != expected_family_ranking:
            metric_errors.append("family_ranking block mismatch")
    else:
        metric_errors.append("family_ranking cannot be recomputed: metrics blocks missing")
    record("summary numbers recomputed from the prediction table", metric_errors)

    errors = [error for check in checks for error in check["errors"]]
    return {
        "passed": not errors,
        "check_count": len(checks),
        "passed_count": sum(1 for check in checks if check["passed"]),
        "checks": checks,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument(
        "--frozen-predictions", type=Path, default=FROZEN_PREDICTIONS_PATH
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = verify(
        summary_path=args.summary,
        predictions_path=args.predictions,
        frozen_predictions_path=args.frozen_predictions,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
