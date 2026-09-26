"""Compound-count learning curve for the frozen dielectric v1.0 benchmark.

Hypothesis under test: on the frozen ``RepeatedKFold(5, 10, seed=42)`` protocol
the frozen v1.0 table (236 modelling compounds, one near-room-temperature
epsilon per compound) reaches R^2 = 0.3636 for the hybrid ``Morgan+Physical``
representation, while a temperature-resolved observation table that covers only
98-101 compounds reaches R^2 = 0.186 under the same grouped protocol. If
compound coverage -- not temperature coverage -- is the lever, then the R^2 of
the frozen representation should climb monotonically as we feed it more
distinct compounds, and the observed 236-compound score should sit on that
curve rather than above it.

This probe therefore holds the pipeline bit-for-bit frozen (it imports
``fit_predict_representation`` et al. from ``dielectric_representation_ablation``
rather than reimplementing anything) and varies exactly one thing: how many
compounds enter the fit. For every rung of a compound ladder it samples a
*nested* subset (``np.random.default_rng(SEED).permutation`` then ``[:n]``), runs
the frozen 10x5 ``RepeatedKFold`` on those rows, and reports mean +/- SD of R^2,
MAE, RMSE and Spearman per representation, plus the marginal R^2 bought by each
added compound between rungs.

The probe is read-only with respect to the released artefacts: it never writes
``data/dielectric_v03.csv``, any digest, or any v1.0 output. Everything lands in
``probes/dielectric_compound_coverage_curve_summary.json``,
``probes/artifacts/dielectric_compound_coverage_curve.csv`` and
``probes/artifacts/dielectric_compound_coverage_curve.png``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
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
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
    fit_predict_representation,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
DEFAULT_DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "dielectric_compound_coverage_curve_summary.json"
DEFAULT_CSV = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_compound_coverage_curve.csv"
)
DEFAULT_PLOT = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_compound_coverage_curve.png"
)

# The first six rungs are the ladder requested for the v1.x decision; the final
# rung is always the full modelling table so the curve is anchored on the frozen
# v1.0 score.
FIXED_LADDER = (30, 60, 90, 120, 160, 200)
METRIC_NAMES = ("r2", "mae", "rmse", "spearman")
COLORS = {"Morgan": "#2563eb", "Physical": "#dc2626", "Morgan+Physical": "#059669"}

CURVE_COLUMNS = (
    "representation",
    "n_compounds",
    "n_repeats",
    "n_splits",
    "r2_mean",
    "r2_std",
    "mae_mean",
    "mae_std",
    "rmse_mean",
    "rmse_std",
    "spearman_mean",
    "spearman_std",
    "delta_r2_from_previous",
    "marginal_r2_per_compound",
)


def write_curve_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write the curve table with LF endings, matching repository text style."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CURVE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _build_ladder(n_rows: int, requested: Sequence[int] | None) -> list[int]:
    """Return the compound ladder, always ending on the full table."""

    if requested:
        ladder = sorted({int(size) for size in requested})
        invalid = [size for size in ladder if size < 2 * N_SPLITS or size > n_rows]
        if invalid:
            raise ValueError(
                f"ladder sizes must be within [{2 * N_SPLITS}, {n_rows}]: {invalid}"
            )
    else:
        ladder = [size for size in FIXED_LADDER if size <= n_rows]
    if not ladder or ladder[-1] != n_rows:
        ladder.append(n_rows)
    return ladder


def _nested_subsets(n_rows: int, ladder: Sequence[int]) -> dict[int, np.ndarray]:
    """Sample nested compound subsets from one fixed-seed permutation.

    Nested subsets keep every rung a superset of the previous one, so the
    marginal R^2 per added compound is not polluted by a wholesale reshuffle of
    which compounds are present.
    """

    permutation = np.random.default_rng(SEED).permutation(n_rows)
    subsets: dict[int, np.ndarray] = {}
    for size in ladder:
        selected = np.sort(permutation[:size])
        if size == n_rows and not np.array_equal(selected, np.arange(n_rows)):
            raise ValueError("full-coverage rung must contain every compound")
        subsets[size] = selected
    return subsets


def run_curve(
    rows: Sequence[Mapping[str, str]],
    *,
    ladder: Sequence[int] | None = None,
) -> tuple[list[dict[str, object]], dict[int, np.ndarray]]:
    """Run the frozen protocol on each compound rung.

    Returns the per-repeat metric rows and the sampled compound subsets.
    """

    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    physical = physical_feature_matrix(rows)

    sizes = _build_ladder(len(rows), ladder)
    subsets = _nested_subsets(len(rows), sizes)

    curve_rows: list[dict[str, object]] = []
    for size in sizes:
        selected = subsets[size]
        subset_target = target[selected]
        subset_morgan = morgan[selected]
        subset_physical = physical[selected]
        splitter = RepeatedKFold(
            n_splits=N_SPLITS,
            n_repeats=N_REPEATS,
            random_state=SEED,
        )
        for representation in REPRESENTATIONS:
            oof_by_repeat = [np.full(size, np.nan) for _ in range(N_REPEATS)]
            for repeat, (train_indices, test_indices) in enumerate(
                splitter.split(np.zeros(size))
            ):
                repeat_number = repeat // N_SPLITS
                prediction, _ = fit_predict_representation(
                    representation,
                    morgan=subset_morgan,
                    physical=subset_physical,
                    target=subset_target,
                    train_indices=train_indices,
                    test_indices=test_indices,
                    seed=SEED + repeat,
                )
                oof_by_repeat[repeat_number][test_indices] = prediction
            for repeat_number, prediction in enumerate(oof_by_repeat):
                if not np.isfinite(prediction).all():
                    raise ValueError(
                        f"incomplete OOF predictions for {representation}/{size}/{repeat_number}"
                    )
                metrics = evaluate_repeat(subset_target, prediction)
                curve_rows.append(
                    {
                        "representation": representation,
                        "n_compounds": size,
                        "repeat": repeat_number,
                        **metrics,
                    }
                )
            r2_values = [
                float(row["r2"])
                for row in curve_rows
                if row["representation"] == representation and row["n_compounds"] == size
            ]
            print(
                json.dumps(
                    {
                        "n_compounds": size,
                        "representation": representation,
                        "r2": f"{np.mean(r2_values):.6f}",
                    }
                ),
                flush=True,
            )
    return curve_rows, subsets


def summarize_curve(
    curve_rows: Sequence[Mapping[str, object]],
    ladder: Sequence[int],
) -> dict[str, dict[str, dict[str, object]]]:
    """Aggregate per-repeat metrics into mean +/- SD per representation and rung."""

    summary: dict[str, dict[str, dict[str, object]]] = {}
    for representation in REPRESENTATIONS:
        summary[representation] = {}
        previous_r2: float | None = None
        previous_size: int | None = None
        for size in ladder:
            rows = [
                row
                for row in curve_rows
                if row["representation"] == representation and int(row["n_compounds"]) == size
            ]
            if len(rows) != N_REPEATS:
                raise ValueError(f"expected {N_REPEATS} repeats for {representation}/{size}")
            entry: dict[str, object] = {}
            for metric in METRIC_NAMES:
                values = np.asarray([float(row[metric]) for row in rows], dtype=float)
                entry[metric] = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values, ddof=1)),
                }
            r2_mean = float(entry["r2"]["mean"])  # type: ignore[index]
            if previous_r2 is None or previous_size is None:
                entry["delta_r2_from_previous"] = None
                entry["marginal_r2_per_compound"] = None
            else:
                delta = r2_mean - previous_r2
                entry["delta_r2_from_previous"] = float(delta)
                entry["marginal_r2_per_compound"] = float(delta / (size - previous_size))
            previous_r2 = r2_mean
            previous_size = size
            summary[representation][str(size)] = entry
    return summary


def _curve_table(
    summary: Mapping[str, Mapping[str, Mapping[str, object]]],
    ladder: Sequence[int],
) -> list[dict[str, object]]:
    table: list[dict[str, object]] = []
    for representation in REPRESENTATIONS:
        for size in ladder:
            entry = summary[representation][str(size)]
            table.append(
                {
                    "representation": representation,
                    "n_compounds": size,
                    "n_repeats": N_REPEATS,
                    "n_splits": N_SPLITS,
                    **{
                        f"{metric}_{stat}": _format_optional(entry[metric][stat])
                        for metric in METRIC_NAMES
                        for stat in ("mean", "std")
                    },
                    "delta_r2_from_previous": _format_optional(entry["delta_r2_from_previous"]),
                    "marginal_r2_per_compound": _format_optional(
                        entry["marginal_r2_per_compound"]
                    ),
                }
            )
    return table


def _format_optional(value: object) -> str:
    return "" if value is None else f"{float(value):.12g}"


def _write_plot(
    summary: Mapping[str, Mapping[str, Mapping[str, object]]],
    ladder: Sequence[int],
    path: Path,
) -> None:
    figure, (r2_axis, marginal_axis) = plt.subplots(1, 2, figsize=(12.5, 4.6))
    for representation in REPRESENTATIONS:
        means = [float(summary[representation][str(size)]["r2"]["mean"]) for size in ladder]
        stds = [float(summary[representation][str(size)]["r2"]["std"]) for size in ladder]
        r2_axis.errorbar(
            ladder,
            means,
            yerr=stds,
            marker="o",
            capsize=3,
            color=COLORS[representation],
            label=representation,
        )
    r2_axis.axhline(0.3636, color="#6b7280", linestyle="--", linewidth=1.0)
    r2_axis.text(
        ladder[0],
        0.3636,
        " frozen v1.0 Morgan+Physical (0.3636)",
        va="bottom",
        ha="left",
        fontsize=8,
        color="#374151",
    )
    r2_axis.set_xlabel("Compounds in the fit")
    r2_axis.set_ylabel("R2 (mean over 10 repeats)")
    r2_axis.set_title("Compound-coverage learning curve")
    r2_axis.grid(alpha=0.25)
    r2_axis.legend()

    steps = [
        (ladder[index], ladder[index] - ladder[index - 1]) for index in range(1, len(ladder))
    ]
    width = 0.26
    positions = np.arange(len(steps))
    for offset, representation in enumerate(REPRESENTATIONS):
        values = []
        for size, _ in steps:
            entry = summary[representation][str(size)]["marginal_r2_per_compound"]
            values.append(float(entry) * 100.0 if entry is not None else 0.0)
        marginal_axis.bar(
            positions + (offset - 1) * width,
            values,
            width=width,
            color=COLORS[representation],
            label=representation,
        )
    marginal_axis.axhline(0.0, color="#111827", linewidth=0.8)
    marginal_axis.set_xticks(positions)
    marginal_axis.set_xticklabels([f"+{step}" for _, step in steps], rotation=0)
    marginal_axis.set_xlabel("Compounds added between rungs")
    marginal_axis.set_ylabel("Marginal R2 per added compound (x100)")
    marginal_axis.set_title("Marginal value of the next compound")
    marginal_axis.grid(axis="y", alpha=0.25)
    marginal_axis.legend(fontsize=8)

    figure.suptitle("Dielectric compound-coverage curve (frozen 10x5 RepeatedKFold)")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=None,
        help="explicit compound ladder; the full table is appended if absent",
    )
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--plot", type=Path, default=DEFAULT_PLOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows, failed_rows, withheld_rows = read_modelling_rows(
        args.input,
        dataset_path=args.dataset,
    )
    sizes = _build_ladder(len(rows), args.sizes)
    curve_rows, subsets = run_curve(rows, ladder=sizes)
    summary = summarize_curve(curve_rows, sizes)

    payload = {
        "schema_version": 1,
        "seed": SEED,
        "protocol": {
            "validation": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
            "sampling": "np.random.default_rng(SEED).permutation(n)[:size] (nested subsets)",
        },
        "representations": list(REPRESENTATIONS),
        "ladder": list(sizes),
        "model_params": XGB_PARAMS,
        "n_modelling_rows": len(rows),
        "n_failed_rows": len(failed_rows),
        "n_withheld_rows": len(withheld_rows),
        "input_path": portable_relative_path(args.input, root=REPOSITORY_ROOT),
        "input_sha256": canonical_text_sha256(args.input),
        "dataset_path": portable_relative_path(args.dataset, root=REPOSITORY_ROOT),
        "dataset_sha256": canonical_text_sha256(args.dataset),
        "subset_inchikeys": {
            str(size): [rows[int(index)]["inchikey"] for index in subsets[size]] for size in sizes
        },
        "summary": summary,
        "rows": curve_rows,
        "outputs": {
            "csv": portable_relative_path(args.csv, root=REPOSITORY_ROOT),
            "summary": portable_relative_path(args.summary, root=REPOSITORY_ROOT),
            "plot": portable_relative_path(args.plot, root=REPOSITORY_ROOT),
        },
    }

    write_curve_csv(args.csv, _curve_table(summary, sizes))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(summary, sizes, args.plot)
    print(
        json.dumps(
            {
                "ladder": list(sizes),
                "r2": {
                    representation: {
                        str(size): round(float(summary[representation][str(size)]["r2"]["mean"]), 4)
                        for size in sizes
                    }
                    for representation in REPRESENTATIONS
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())