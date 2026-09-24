"""C1: split-conformal prediction intervals from archived OOF predictions.

The dielectric benchmark already stores out-of-fold predictions for every
representation, training arm and repeated CV run. No model is retrained here.

Protocol (corrected after an adversarial audit of the first draft):

* For every random split r we draw one global calibration/test partition of all
  234 compounds. The role of a compound is therefore identical across every
  representation, arm and repeat, so all paired comparisons see the same
  compounds in the calibration and test halves.
* Inside a split the partition is applied per frozen RepeatedKFold fold. The
  conformal quantile is estimated only from the calibration compounds that fall
  in that fold and evaluated only on the test compounds of the same fold. The
  quantile is never pooled across folds, repeats, arms or representations,
  because each (repeat, fold) cell comes from a different training set and a
  different XGBoost seed.
* Per-repeat summaries are the equal-weight mean over the 200 random splits.
  The ten repeats are then averaged with equal weight. The ten repeats are model
  refits, not ten independent datasets, so no t-test treats them as independent.

This yields a marginal, finite-sample compound-level guarantee under
exchangeability of the OOF scores. It is explicitly not a conditional coverage
guarantee for a target range, nor a chemical extrapolation guarantee.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dielectric_representation_ablation import (
    N_REPEATS,
    REPRESENTATIONS,
    SEED,
    read_modelling_rows,
    write_csv_rows,
)
from scipy.stats import t as student_t
from v032_controlled_comparison import _fold_assignment

from electrolyte_ml.exporting import canonical_text_sha256

ALPHA = 0.10
CALIBRATION_FRACTION = 0.50
N_RANDOM_SPLITS = 200
MIN_CALIBRATION_N = 9
ARMS = ("baseline_v0.3", "augmented_pc_ec_train_only")
DEFAULT_OOF = REPOSITORY_ROOT / "probes" / "v032_controlled_comparison_repeats_oof.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "dielectric_split_conformal_summary.json"
DEFAULT_SPLITS = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_split_conformal_splits.csv"
)
DEFAULT_PLOT = REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_split_conformal.png"
STRATA = (("lt20", None, 20.0), ("20_60", 20.0, 60.0), ("gt60", 60.0, None))
N_FOLDS = 5
SPLIT_COLUMNS = (
    "representation",
    "arm",
    "repeat",
    "split",
    "calibration_count",
    "test_count",
    "infinite_interval_count",
    "infinite_interval_rate",
    "quantile_abs_error_median",
    "normalized_quantile_median",
    "interval_width",
    "coverage",
    "coverage_lt20",
    "coverage_20_60",
    "coverage_gt60",
    "normalized_interval_width",
    "normalized_coverage",
    "normalized_coverage_lt20",
    "normalized_coverage_20_60",
    "normalized_coverage_gt60",
) + tuple(
    f"fold{fold}_{suffix}"
    for fold in range(N_FOLDS)
    for suffix in (
        "calibration_count",
        "test_count",
        "quantile",
        "coverage",
        "normalized_quantile",
        "normalized_coverage",
    )
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Return the finite-sample split-conformal quantile, or +inf."""

    values = np.asarray(scores, dtype=float)
    if values.size == 0:
        raise ValueError("at least one calibration score is required")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    rank = int(np.ceil((values.size + 1) * (1.0 - alpha)))
    if rank > values.size:
        return float("inf")
    return float(np.sort(values)[rank - 1])


def global_calibration_mask(
    compound_count: int,
    *,
    rng: np.random.Generator,
    calibration_fraction: float = CALIBRATION_FRACTION,
) -> np.ndarray:
    """Assign a stable calibration/test role to every compound for one split."""

    if compound_count <= 0:
        raise ValueError("compound_count must be positive")
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction must be in (0, 1)")
    permuted = rng.permutation(compound_count)
    take = int(np.ceil(compound_count * calibration_fraction))
    mask = np.zeros(compound_count, dtype=bool)
    mask[permuted[:take]] = True
    return mask


def _conditional_coverage(
    target: np.ndarray,
    errors: np.ndarray,
    threshold: np.ndarray,
    *,
    low: float | None = None,
    high: float | None = None,
) -> float | None:
    mask = np.ones(target.shape, dtype=bool)
    if low is not None:
        mask &= target >= low
    if high is not None:
        mask &= target <= high
    if not np.any(mask):
        return None
    return float(np.mean(errors[mask] <= threshold[mask]))


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


def write_json_lf(path: Path, payload: object) -> None:
    """Write JSON with explicit LF endings and no non-finite literals.

    Path.write_text translates the newline to os.linesep on Windows, which would
    make the artifact bytes depend on the host platform. Non-finite floats are
    converted to null first because bare NaN and Infinity are not valid JSON.
    """

    text = (
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _aggregate(values: Sequence[float]) -> dict[str, float | int | None]:
    """Summarise the ten repeat-level means.

    The half-width is a descriptive Student-t spread of the ten repeat means,
    not a sampling confidence interval: the repeats re-fit the same 234
    compounds and are not independent samples. The field is therefore named
    repeat_dispersion_interval rather than ci95.
    """

    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {
            "mean": None,
            "std": None,
            "repeat_dispersion_interval": [None, None],
            "n": 0,
        }
    mean = float(np.mean(array))
    std = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
    half_width = (
        float(student_t.ppf(0.975, array.size - 1) * std / np.sqrt(array.size))
        if array.size > 1
        else 0.0
    )
    return {
        "mean": mean,
        "std": std,
        "repeat_dispersion_interval": [mean - half_width, mean + half_width],
        "n": int(array.size),
    }


def _mean_optional(values: Sequence[float | None]) -> float | None:
    finite = np.asarray(
        [value for value in values if value is not None and np.isfinite(value)],
        dtype=float,
    )
    return float(np.mean(finite)) if finite.size else None


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    if not np.isfinite(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.12g}"


def evaluate_series(
    rows: Sequence[Mapping[str, str]],
    *,
    representation: str,
    arm: str,
    key_order: Sequence[str],
    fold_by_key: Mapping[tuple[str, int], int],
    n_random_splits: int = N_RANDOM_SPLITS,
    seed: int = SEED,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    by_key = {row["inchikey"]: row for row in rows}
    if set(by_key) != set(key_order):
        raise ValueError(
            f"OOF keys do not match ordered keys for {representation}/{arm}"
        )
    ordered_target = np.asarray(
        [float(by_key[key]["target"]) for key in key_order], dtype=float
    )
    ordered_prediction = np.asarray(
        [float(by_key[key]["prediction"]) for key in key_order], dtype=float
    )

    # Roles are drawn once per random split from (seed + split_id) only, so the
    # calibration/test membership never depends on the repeat, arm or
    # representation. Every paired comparison therefore sees the same rows.
    split_masks = [
        global_calibration_mask(len(key_order), rng=np.random.default_rng(seed + s))
        for s in range(n_random_splits)
    ]

    series_splits: list[dict[str, object]] = []
    repeat_summaries: list[dict[str, object]] = []
    for repeat in range(N_REPEATS):
        fold_ids = np.asarray(
            [fold_by_key[(key, repeat)] for key in key_order], dtype=int
        )
        n_folds = int(fold_ids.max()) + 1
        coverage_values: list[float] = []
        width_values: list[float] = []
        normalized_coverage_values: list[float] = []
        normalized_width_values: list[float] = []
        infinite_rate_values: list[float] = []
        calibration_counts: list[int] = []
        quantile_medians: list[float] = []
        conditional_values: dict[str, list[float | None]] = {
            name: [] for name, _, _ in STRATA
        }
        normalized_conditional_values: dict[str, list[float | None]] = {
            name: [] for name, _, _ in STRATA
        }
        per_fold_coverage: dict[int, list[float]] = {fold: [] for fold in range(n_folds)}
        per_fold_normalized: dict[int, list[float]] = {
            fold: [] for fold in range(n_folds)
        }
        for split_id, calibration_mask in enumerate(split_masks):
            target_chunks: list[np.ndarray] = []
            error_chunks: list[np.ndarray] = []
            threshold_chunks: list[np.ndarray] = []
            normalized_threshold_chunks: list[np.ndarray] = []
            cell_qs: list[float] = []
            cell_normalized_qs: list[float] = []
            cell_cal_counts: list[int] = []
            cell_test_counts: list[int] = []
            cell_coverages: list[float] = []
            cell_normalized_coverages: list[float] = []
            for fold in range(n_folds):
                cell = fold_ids == fold
                cal_index = np.flatnonzero(cell & calibration_mask)
                test_index = np.flatnonzero(cell & ~calibration_mask)
                calibration_errors = np.abs(
                    ordered_target[cal_index] - ordered_prediction[cal_index]
                )
                test_errors = np.abs(
                    ordered_target[test_index] - ordered_prediction[test_index]
                )
                if cal_index.size < MIN_CALIBRATION_N:
                    quantile = float("inf")
                    normalized_quantile = float("inf")
                else:
                    quantile = conformal_quantile(calibration_errors, ALPHA)
                    normalized_scores = calibration_errors / (
                        1.0 + np.abs(ordered_prediction[cal_index])
                    )
                    normalized_quantile = conformal_quantile(normalized_scores, ALPHA)
                threshold = np.full(test_index.size, quantile, dtype=float)
                normalized_threshold = normalized_quantile * (
                    1.0 + np.abs(ordered_prediction[test_index])
                )
                target_chunks.append(ordered_target[test_index])
                error_chunks.append(test_errors)
                threshold_chunks.append(threshold)
                normalized_threshold_chunks.append(normalized_threshold)
                cell_qs.append(quantile)
                cell_normalized_qs.append(normalized_quantile)
                cell_cal_counts.append(int(cal_index.size))
                cell_test_counts.append(int(test_index.size))
                cell_coverages.append(
                    float(np.mean(test_errors <= threshold))
                    if test_index.size
                    else float("nan")
                )
                cell_normalized_coverages.append(
                    float(np.mean(test_errors <= normalized_threshold))
                    if test_index.size
                    else float("nan")
                )
                per_fold_coverage[fold].append(cell_coverages[-1])
                per_fold_normalized[fold].append(cell_normalized_coverages[-1])

            targets = np.concatenate(target_chunks)
            errors = np.concatenate(error_chunks)
            thresholds = np.concatenate(threshold_chunks)
            normalized_thresholds = np.concatenate(normalized_threshold_chunks)
            coverage = float(np.mean(errors <= thresholds))
            normalized_coverage = float(np.mean(errors <= normalized_thresholds))
            width = float(np.mean(2.0 * thresholds))
            normalized_width = float(np.mean(2.0 * normalized_thresholds))
            infinite_count = int(np.sum(~np.isfinite(thresholds)))
            coverage_values.append(coverage)
            normalized_coverage_values.append(normalized_coverage)
            width_values.append(width)
            normalized_width_values.append(normalized_width)
            infinite_rate_values.append(infinite_count / max(targets.size, 1))
            calibration_counts.append(int(calibration_mask.sum()))
            quantile_medians.append(float(np.median(cell_qs)))

            row: dict[str, object] = {
                "representation": representation,
                "arm": arm,
                "repeat": repeat,
                "split": split_id,
                "calibration_count": int(calibration_mask.sum()),
                "test_count": int(targets.size),
                "infinite_interval_count": infinite_count,
                "infinite_interval_rate": _fmt(infinite_count / max(targets.size, 1)),
                "quantile_abs_error_median": _fmt(float(np.median(cell_qs))),
                "normalized_quantile_median": _fmt(
                    float(np.median(cell_normalized_qs))
                ),
                "interval_width": _fmt(width),
                "coverage": _fmt(coverage),
                "normalized_interval_width": _fmt(normalized_width),
                "normalized_coverage": _fmt(normalized_coverage),
            }
            for name, low, high in STRATA:
                value = _conditional_coverage(
                    targets, errors, thresholds, low=low, high=high
                )
                normalized_value = _conditional_coverage(
                    targets, errors, normalized_thresholds, low=low, high=high
                )
                row[f"coverage_{name}"] = _fmt(value)
                row[f"normalized_coverage_{name}"] = _fmt(normalized_value)
                conditional_values[name].append(value)
                normalized_conditional_values[name].append(normalized_value)
            for fold in range(n_folds):
                row[f"fold{fold}_calibration_count"] = cell_cal_counts[fold]
                row[f"fold{fold}_test_count"] = cell_test_counts[fold]
                row[f"fold{fold}_quantile"] = _fmt(cell_qs[fold])
                row[f"fold{fold}_coverage"] = _fmt(cell_coverages[fold])
                row[f"fold{fold}_normalized_quantile"] = _fmt(
                    cell_normalized_qs[fold]
                )
                row[f"fold{fold}_normalized_coverage"] = _fmt(
                    cell_normalized_coverages[fold]
                )
            series_splits.append(row)
        repeat_summaries.append(
            {
                "repeat": repeat,
                "coverage_mean": float(np.mean(coverage_values)),
                "coverage_std": float(np.std(coverage_values, ddof=1)),
                "coverage_min": float(np.min(coverage_values)),
                "coverage_max": float(np.max(coverage_values)),
                "interval_width_mean": float(np.mean(width_values)),
                "interval_width_median": float(np.median(width_values)),
                "infinite_interval_rate_mean": float(np.mean(infinite_rate_values)),
                "infinite_interval_rate_max": float(np.max(infinite_rate_values)),
                "calibration_count_median": float(np.median(calibration_counts)),
                "quantile_median": float(np.median(quantile_medians)),
                "coverage_lt20": _mean_optional(conditional_values["lt20"]),
                "coverage_20_60": _mean_optional(conditional_values["20_60"]),
                "coverage_gt60": _mean_optional(conditional_values["gt60"]),
                "normalized_coverage_mean": float(np.mean(normalized_coverage_values)),
                "normalized_coverage_std": float(
                    np.std(normalized_coverage_values, ddof=1)
                ),
                "normalized_interval_width_mean": float(
                    np.mean(normalized_width_values)
                ),
                "normalized_coverage_lt20": _mean_optional(
                    normalized_conditional_values["lt20"]
                ),
                "normalized_coverage_20_60": _mean_optional(
                    normalized_conditional_values["20_60"]
                ),
                "normalized_coverage_gt60": _mean_optional(
                    normalized_conditional_values["gt60"]
                ),
                "per_fold_coverage": [
                    _mean_optional(per_fold_coverage[fold])
                    for fold in range(n_folds)
                ],
                "per_fold_normalized_coverage": [
                    _mean_optional(per_fold_normalized[fold])
                    for fold in range(n_folds)
                ],
            }
        )

    def repeat_values(field: str) -> list[float]:
        return [
            float(value)
            for row in repeat_summaries
            if (value := row.get(field)) is not None
        ]

    summary = {
        "representation": representation,
        "arm": arm,
        "coverage": _aggregate(repeat_values("coverage_mean")),
        "coverage_min_across_splits": min(
            float(row["coverage_min"]) for row in repeat_summaries
        ),
        "coverage_max_across_splits": max(
            float(row["coverage_max"]) for row in repeat_summaries
        ),
        "interval_width": _aggregate(repeat_values("interval_width_mean")),
        "infinite_interval_rate": _aggregate(
            repeat_values("infinite_interval_rate_mean")
        ),
        "calibration_count_median": _aggregate(
            repeat_values("calibration_count_median")
        ),
        "quantile_median": _aggregate(repeat_values("quantile_median")),
        "coverage_lt20": _aggregate(repeat_values("coverage_lt20")),
        "coverage_20_60": _aggregate(repeat_values("coverage_20_60")),
        "coverage_gt60": _aggregate(repeat_values("coverage_gt60")),
        "normalized_coverage": _aggregate(repeat_values("normalized_coverage_mean")),
        "normalized_interval_width": _aggregate(
            repeat_values("normalized_interval_width_mean")
        ),
        "normalized_coverage_lt20": _aggregate(
            repeat_values("normalized_coverage_lt20")
        ),
        "normalized_coverage_20_60": _aggregate(
            repeat_values("normalized_coverage_20_60")
        ),
        "normalized_coverage_gt60": _aggregate(
            repeat_values("normalized_coverage_gt60")
        ),
        "per_repeat": repeat_summaries,
    }
    return series_splits, summary


def _series_key(representation: str, arm: str) -> str:
    return f"{representation}|{arm}"


def build_summary(
    *,
    oof_path: Path = DEFAULT_OOF,
    summary_path: Path = DEFAULT_SUMMARY,
    splits_path: Path = DEFAULT_SPLITS,
    plot_path: Path = DEFAULT_PLOT,
) -> dict[str, object]:
    base_rows, _, _ = read_modelling_rows(
        REPOSITORY_ROOT / "data" / "interim" / "v03_features_original.csv"
    )
    key_order = [row["inchikey"] for row in base_rows]
    fold_by_key = _fold_assignment(key_order)
    records: dict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv_rows(oof_path):
        records[
            (
                row["representation"],
                row["arm"],
                int(row["repeat"]),
            )
        ].append(row)
    expected_series = {
        (representation, arm, repeat)
        for representation in REPRESENTATIONS
        for arm in ARMS
        for repeat in range(N_REPEATS)
    }
    if set(records) != expected_series:
        missing = sorted(expected_series - set(records))
        extra = sorted(set(records) - expected_series)
        raise ValueError(f"OOF series mismatch; missing={missing}, extra={extra}")

    all_splits: list[dict[str, object]] = []
    series_summaries: dict[str, dict[str, object]] = {}
    for representation in REPRESENTATIONS:
        for arm in ARMS:
            series_rows = [
                row
                for repeat in range(N_REPEATS)
                for row in records[(representation, arm, repeat)]
            ]
            series_splits, series_summary = evaluate_series(
                series_rows,
                representation=representation,
                arm=arm,
                key_order=key_order,
                fold_by_key=fold_by_key,
            )
            all_splits.extend(series_splits)
            series_summaries[_series_key(representation, arm)] = series_summary

    targets = np.asarray([float(row["dielectric"]) for row in base_rows], dtype=float)
    payload = {
        "schema_version": "dielectric_split_conformal/v2",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": {
            "question": (
                "Can archived OOF predictions support a finite-sample,"
                " zero-retraining prediction interval for dielectric constant?"
            ),
            "method": "per-fold split conformal on absolute residuals",
            "nominal_coverage": 1.0 - ALPHA,
            "alpha": ALPHA,
            "calibration_fraction": CALIBRATION_FRACTION,
            "random_splits_per_repeat": N_RANDOM_SPLITS,
            "min_calibration_n": MIN_CALIBRATION_N,
            "split_stratification": (
                "one global calibration/test partition per random split, applied "
                "independently inside each frozen RepeatedKFold(5, 10, "
                "random_state=42) fold; the conformal quantile is estimated and "
                "evaluated within a single (repeat, fold) cell and is never "
                "pooled across cells"
            ),
            "calibration_role_stability": (
                "the calibration/test role of a compound is drawn once per random "
                "split from (seed + split_id) and is shared by every "
                "representation, arm and repeat"
            ),
            "model_retraining": False,
        },
        "inputs": {
            "oof_path": str(oof_path.relative_to(REPOSITORY_ROOT)),
            "oof_sha256": canonical_text_sha256(oof_path),
            "fold_source": "RepeatedKFold(5, 10, random_state=42) over v0.3 row order",
        },
        "counts": {
            "compounds": len(key_order),
            "repeats": N_REPEATS,
            "series": len(expected_series),
            "split_rows": len(all_splits),
        },
        "exchangeability": {
            "unit": "compound",
            "repeat_treated_as_independent": False,
            "conditional_target_coverage_claimed": False,
            "interval_guarantee": "marginal in compounds under exchangeability",
            "target_strata_sizes": {
                "lt20": int(np.sum(targets < 20.0)),
                "20_60": int(np.sum((targets >= 20.0) & (targets <= 60.0))),
                "gt60": int(np.sum(targets > 60.0)),
            },
        },
        "repeat_dispersion_interval_note": (
            "repeat_dispersion_interval is mean +/- t_{0.975,n-1} * s / sqrt(n) "
            "over the ten repeat-level means. It is a descriptive spread of the "
            "ten refits, not a sampling confidence interval: the repeats re-use "
            "the same 234 compounds and are not independent samples. Interval "
            "uncertainty in compounds would need a compound-level bootstrap, "
            "which this probe does not claim."
        ),
        "series": series_summaries,
        "honest_boundary": [
            (
                "The guarantee is marginal in compounds under exchangeability; "
                "it is not a conditional coverage guarantee for every target range."
            ),
            (
                "Conditional (target-stratum) coverage is reported as an "
                "exploratory diagnostic only. The >60 stratum contains only five "
                "compounds, so its conditional coverage is extremely noisy."
            ),
            (
                "The archived OOF predictions are reused, so the interval "
                "describes the frozen benchmark procedure rather than a freshly "
                "fitted single model."
            ),
            (
                "The ten repeats are model refits, not ten independent datasets. "
                "Repeat-level summaries are averaged with equal weight and no "
                "test treats the repeats as independent samples."
            ),
            (
                "Calibration scores are never pooled across folds, repeats, arms "
                "or representations: each (repeat, fold) cell comes from a "
                "different training set and a different XGBoost seed, so pooling "
                "would break the exchangeability assumption the quantile relies on."
            ),
            (
                "No guarantee is claimed for chemical extrapolation or for "
                "distribution shift outside the frozen 234-compound benchmark."
            ),
        ],
        "warnings": [
            (
                "The first draft of this probe pooled residuals across folds into "
                "one global quantile. That was methodologically wrong: residuals "
                "from different folds are not exchangeable. The v2 protocol fixes "
                "this by estimating one quantile per (repeat, fold) cell."
            ),
            (
                "The normalized variant divides residuals by (1 + |prediction|). "
                "It is still a marginal interval; it only rescales the width and "
                "does not buy conditional coverage."
            ),
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_lf(summary_path, payload)
    write_csv_rows(splits_path, SPLIT_COLUMNS, all_splits)
    _write_plot(series_summaries, plot_path)
    return payload


def _write_plot(series: Mapping[str, Mapping[str, object]], path: Path) -> None:
    labels = [f"{name}|baseline_v0.3" for name in REPRESENTATIONS]
    coverage = [float(series[label]["coverage"]["mean"]) for label in labels]
    c_low = [
        float(series[label]["coverage"]["repeat_dispersion_interval"][0])
        for label in labels
    ]
    c_high = [
        float(series[label]["coverage"]["repeat_dispersion_interval"][1])
        for label in labels
    ]
    normalized_coverage = [
        float(series[label]["normalized_coverage"]["mean"]) for label in labels
    ]
    width = [float(series[label]["interval_width"]["mean"]) for label in labels]
    normalized_width = [
        float(series[label]["normalized_interval_width"]["mean"]) for label in labels
    ]
    x = np.arange(len(labels))
    bar_width = 0.36
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 5.0))
    errors = np.vstack(
        [
            np.asarray(coverage) - np.asarray(c_low),
            np.asarray(c_high) - np.asarray(coverage),
        ]
    )
    axes[0].bar(
        x - bar_width / 2,
        coverage,
        bar_width,
        yerr=errors,
        capsize=3,
        label="absolute residual",
        color="#2563eb",
    )
    axes[0].bar(
        x + bar_width / 2,
        normalized_coverage,
        bar_width,
        label="normalized by 1+|prediction|",
        color="#f59e0b",
    )
    axes[0].axhline(1.0 - ALPHA, color="#111827", linestyle="--", linewidth=1.0)
    axes[0].set_ylim(0.0, 1.03)
    axes[0].set_ylabel("test coverage")
    axes[0].set_xticks(x, labels=[name.split("|")[0] for name in labels])
    axes[0].legend(loc="lower right")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(
        x - bar_width / 2,
        width,
        bar_width,
        label="absolute residual",
        color="#2563eb",
    )
    axes[1].bar(
        x + bar_width / 2,
        normalized_width,
        bar_width,
        label="normalized by 1+|prediction|",
        color="#f59e0b",
    )
    axes[1].set_ylabel("mean interval width (epsilon units)")
    axes[1].set_xticks(x, labels=[name.split("|")[0] for name in labels])
    axes[1].legend(loc="upper right")
    axes[1].grid(axis="y", alpha=0.25)
    figure.suptitle("C1 split-conformal intervals from archived OOF predictions")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oof", type=Path, default=DEFAULT_OOF)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--plot", type=Path, default=DEFAULT_PLOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = build_summary(
        oof_path=args.oof,
        summary_path=args.summary,
        splits_path=args.splits,
        plot_path=args.plot,
    )
    series = payload["series"]
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "counts": payload["counts"],
                "series": {
                    key: {
                        "coverage": value["coverage"]["mean"],
                        "interval_width": value["interval_width"]["mean"],
                        "infinite_interval_rate": value["infinite_interval_rate"][
                            "mean"
                        ],
                    }
                    for key, value in series.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
