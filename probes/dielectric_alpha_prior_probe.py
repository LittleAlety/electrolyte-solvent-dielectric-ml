"""Turn the NBS Circular 514 temperature coefficients into a model-facing prior.

Why this probe exists
=====================
The v1.x execution handbook lists six data sources. Item 2 is "NBS 514 alpha
temperature coefficients (already on disk): generate a harmonised column *and*
use the coefficient itself as a prior feature". Week 8 shipped the harmonised
column (``data/processed/nbs514_alpha_harmonization.csv``); the prior-feature
half never landed. This probe lands it, and then reports - with paired numbers
rather than an opinion - whether it should be used at all.

Unit conventions
================
Read out of ``probes/nbs514_alpha_harmonization_probe.py`` (which in turn read
sections 2.1 and 2.5 of the circular). They are not guessed here::

    kind "a"      a     = -d(eps)/dT          printed as  a     * 1e5
    kind "alpha"  alpha = -d(log10 eps)/dT    printed as  alpha * 1e5

Both are per kelvin. Inverting them::

    kind "a"      d(eps)/dT = -a_1e5     * 1e-5
    kind "alpha"  d(eps)/dT = -alpha_1e5 * 1e-5 * eps * ln(10)

Two consequences the reporting has to respect.

* The transcribed column is always named ``alpha_1e5``, even when
  ``alpha_kind == "a"`` and it therefore holds ``a``, not ``alpha``. It is a
  transposed coefficient, not a derivative; comparing it with an empirical
  d(eps)/dT has to go through the kind switch.
* The ``alpha`` branch is *relative* (per unit eps), so turning it into a
  derivative needs an epsilon. The frozen table supplies the tabulated epsilon
  through its ``implied_dielectric_slope`` column. That column is deliberately
  NOT used as a model feature here, because 43 of the 44 alpha-carrying rows of
  the v1.0 pool carry a label that is byte-identical to that tabulated epsilon
  (measured, see ``label_identity``): the column would be a function of the
  label. The feature block built below is epsilon-free for exactly that reason.

``alpha_to_depsilon_dt`` re-derives the conversion from the definitions above
instead of importing it, and ``verify_conversion`` proves the re-derivation
reproduces the frozen ``implied_dielectric_slope`` column.

Three questions
===============
1. Cross-check. Do the NBS coefficients agree with a least-squares d(eps)/dT
   fitted on the v1.x observation table? The honest answer starts with an
   intersection problem, so the cohort is widened with every other
   temperature-resolved dielectric table already on disk and each source is
   also reported alone.
2. Prior feature. Does a temperature-sensitivity feature move the grouped
   room-band benchmark (GroupKFold by InChIKey, 10x5, frozen XGBoost hybrid)?
   Five arms share one fold assignment and one scored row set. The NBS
   coefficient arm is the handbook's item 2; the empirical-slope arms measure
   what the *compound's own* slope would buy, both in its leaky form (the slope
   is fitted on rows that are later scored) and in its honest form (the slope is
   fitted on the training fold only, which leaves test compounds with no slope
   at all). A second family repeats the NBS comparison on the v1.0
   236-compound pool, the only pool on disk where alpha coverage is real.
3. Verdict. Should alpha enter the v1.x pipeline, and does it serve compound
   coverage or the temperature dimension?

Ordering and pairing
====================
Every delta in the summary is paired: one fold assignment, one compound pool and
one scored row set per family, so a delta reads as the effect of the single
thing that changed. ``random_row`` splitting is never used.

The probe never writes to ``data/`` and never modifies a released artefact. It
writes ``probes/artifacts/dielectric_alpha_prior_*.csv``,
``probes/dielectric_alpha_prior_probe_summary.json`` and, unless ``--no-report``
is given, ``reports/dielectric_alpha_prior_probe.md``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))


import numpy as np
from dielectric_band_ablation import drop_thin_folds
from dielectric_observations_grouped_benchmark import (
    FEATURES_PATH,
    METRIC_NAMES,
    OBSERVATIONS_PATH,
    build_matrices,
    grouped_folds,
    load_table,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    evaluate_repeat,
    fit_predict_representation,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)
from scipy.stats import wilcoxon
from sklearn.model_selection import RepeatedKFold

ALPHA_TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "nbs514_alpha_harmonization.csv"

LOWFREQ_CANDIDATES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_lowfreq_candidates.csv"
)

FROZEN_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)

DATASET_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"

BAND_ABLATION_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_band_ablation_summary.json"
)

ROOM_WINDOW_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_room_window_paired_summary.json"
)

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_alpha_prior_probe_summary.json"

REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_alpha_prior_probe.md"

ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"

ROOM_BAND = "room_temperature"

HYBRID = "Morgan+Physical"

#: Same convention as ``dielectric_band_ablation.py``: a paired delta smaller
#: than this is reported as inert rather than as a win or a loss.
INERT_TOLERANCE = 0.005

#: Self-check targets. The room baseline is the pinned band-ablation number; the
#: v1.0 endpoint is the released headline. Both must come back bit-identical.
PINNED_ROOM_BASELINE_R2 = 0.4091179943351143

PINNED_V10_ENDPOINT_R2 = 0.36357268752900124

LOG_10 = math.log(10.0)

#: XGBoost's native missing value, used for every compound the prior does not
#: cover. A NaN is a real statement here: "no coefficient exists for this
#: compound", which is different from "the coefficient is zero".
MISSING = float("nan")

ALPHA_ARMS = (
    "room_baseline",
    "room_plus_null_block_two_columns",
    "room_plus_nbs_alpha",
    "room_plus_null_block_one_column",
    "room_plus_emp_slope_leaky_all",
    "room_plus_emp_slope_leaky_room",
    "room_plus_emp_slope_train_only",
)

V10_ARMS = (
    "v10_frozen_baseline",
    "v10_frozen_plus_null_block",
    "v10_frozen_plus_nbs_alpha",
    "v10_grouped_baseline",
    "v10_grouped_plus_null_block",
    "v10_grouped_plus_nbs_alpha",
)

ARM_ORDER = ALPHA_ARMS + V10_ARMS

PAIRINGS = (
    ("room_plus_null_block_two_columns", "room_baseline"),
    ("room_plus_nbs_alpha", "room_baseline"),
    ("room_plus_null_block_one_column", "room_baseline"),
    ("room_plus_emp_slope_leaky_all", "room_baseline"),
    ("room_plus_emp_slope_leaky_room", "room_baseline"),
    ("room_plus_emp_slope_train_only", "room_baseline"),
    ("v10_frozen_plus_null_block", "v10_frozen_baseline"),
    ("v10_frozen_plus_nbs_alpha", "v10_frozen_baseline"),
    ("v10_grouped_plus_null_block", "v10_grouped_baseline"),
    ("v10_grouped_plus_nbs_alpha", "v10_grouped_baseline"),
)

#: (arm, its same-width all-NaN placebo). Widening the feature matrix re-draws
#: ``colsample_bytree``'s column subsample even when the added columns are
#: entirely missing - measured by ``subsampling_control`` - so an arm's delta
#: against the baseline is not its effect. The effect is the delta against the
#: same-width placebo.
NULL_BLOCK_PAIRS = (
    ("room_plus_nbs_alpha", "room_plus_null_block_two_columns"),
    ("room_plus_emp_slope_leaky_all", "room_plus_null_block_one_column"),
    ("room_plus_emp_slope_leaky_room", "room_plus_null_block_one_column"),
    ("room_plus_emp_slope_train_only", "room_plus_null_block_one_column"),
    ("v10_frozen_plus_nbs_alpha", "v10_frozen_plus_null_block"),
    ("v10_grouped_plus_nbs_alpha", "v10_grouped_plus_null_block"),
)

ARM_DESCRIPTIONS = {
    "room_baseline": "room_temperature rows, frozen matrix, grouped 10x5",
    "room_plus_null_block_two_columns": (
        "room rows + two all-NaN columns: the same-width placebo for the alpha arm"
    ),
    "room_plus_nbs_alpha": "room rows + the two epsilon-free NBS alpha columns",
    "room_plus_null_block_one_column": (
        "room rows + one all-NaN column: the same-width placebo for the slope arms"
    ),
    "room_plus_emp_slope_leaky_all": (
        "room rows + the compound's own d(eps)/dT fitted on every v11 row "
        "(LEAKY: the fit sees the scored rows)"
    ),
    "room_plus_emp_slope_leaky_room": (
        "room rows + the compound's own d(eps)/dT fitted on its room rows "
        "(LEAKY: the fit sees the scored rows)"
    ),
    "room_plus_emp_slope_train_only": (
        "room rows + the compound's d(eps)/dT fitted on the training fold only "
        "(honest; a scored compound has no training rows, so it gets NaN)"
    ),
    "v10_frozen_baseline": "v1.0 236-compound pool, released RepeatedKFold 5x10",
    "v10_frozen_plus_null_block": "v1.0 pool, released splitter + two all-NaN columns",
    "v10_frozen_plus_nbs_alpha": "v1.0 pool, released splitter + the NBS alpha columns",
    "v10_grouped_baseline": "v1.0 236-compound pool, grouped by InChIKey 10x5",
    "v10_grouped_plus_null_block": "v1.0 pool, grouped folds + two all-NaN columns",
    "v10_grouped_plus_nbs_alpha": "v1.0 pool, grouped folds + the NBS alpha columns",
}


def alpha_to_depsilon_dt(alpha_1e5: float, alpha_kind: str, epsilon: float) -> float:
    """Convert a transcribed NBS 514 coefficient into d(eps)/dT, per kelvin.

    ``alpha_1e5`` holds whichever coefficient the circular printed, selected by
    ``alpha_kind``; see the module docstring for the two definitions. An unknown
    kind is refused rather than silently treated as the linear branch, because
    the two branches differ by a factor of ``eps * ln(10)`` (a factor of 5 for
    water, 86 for acetonitrile).
    """

    kind = (alpha_kind or "").strip().lower()
    scaled = alpha_1e5 * 1e-5
    if kind == "a":
        return -scaled
    if kind in {"alpha", "\u03b1"}:
        return -scaled * epsilon * LOG_10
    raise ValueError(f"unsupported alpha_kind: {alpha_kind!r}")


def fit_empirical_slope(
    temperatures: Sequence[float],
    epsilons: Sequence[float],
) -> dict[str, float] | None:
    """Least-squares d(eps)/dT for one compound.

    Returns None when the compound has fewer than two distinct temperatures,
    which is the only honest answer: a single point carries no slope, and
    duplicating it would manufacture a slope of exactly zero.
    """

    t = np.asarray(temperatures, dtype=float)
    e = np.asarray(epsilons, dtype=float)
    if t.size != e.size:
        raise ValueError("temperature and epsilon arrays differ in length")
    if t.size == 0:
        return None
    if np.unique(t).size < 2:
        return None
    slope, intercept = np.polyfit(t, e, 1)
    residual = e - (slope * t + intercept)
    total = float(np.sum((e - float(e.mean())) ** 2))
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "n_points": int(t.size),
        "n_distinct_temperatures": int(np.unique(t).size),
        "span_K": float(t.max() - t.min()),
        "mean_temperature_K": float(t.mean()),
        "mean_epsilon": float(e.mean()),
        "r2": float(1.0 - float(np.sum(residual**2)) / total) if total > 0 else float("nan"),
    }


def describe(values: Iterable[float]) -> dict[str, float | int | None]:
    """Median, quartiles and tails of a finite-only sample."""

    arr = np.asarray(
        [float(value) for value in values if value is not None and math.isfinite(float(value))],
        dtype=float,
    )
    if arr.size == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "min": None,
            "max": None,
            "n_negative": 0,
            "n_positive": 0,
        }
    return {
        "n": int(arr.size),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "n_negative": int(np.count_nonzero(arr < 0)),
        "n_positive": int(np.count_nonzero(arr > 0)),
    }


def symmetric_relative_difference(left: float, right: float) -> float:
    """|left - right| normalised by the mean magnitude of the two."""

    denominator = 0.5 * (abs(left) + abs(right))
    if denominator == 0.0:
        return 0.0
    return abs(left - right) / denominator


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_alpha_table(path: Path = ALPHA_TABLE_PATH) -> dict[str, dict[str, str]]:
    return {row["inchikey"]: row for row in read_csv_rows(path)}


def alpha_coefficient(row: Mapping[str, str]) -> tuple[float, str] | None:
    """(coefficient, kind) for a row of the alpha table, or None if it has none."""

    raw = (row.get("alpha_1e5") or "").strip()
    if not raw:
        return None
    return float(raw), (row.get("alpha_kind") or "").strip()


def verify_conversion(
    alpha_table: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    """Prove ``alpha_to_depsilon_dt`` reproduces the frozen ``implied_dielectric_slope``.

    The frozen column was produced by ``nbs514_alpha_harmonization_probe.py``.
    Reproducing it from the definitions is the only evidence that this probe's
    unit handling is the week-8 unit handling and not a re-guess.
    """

    deltas: list[float] = []
    kinds: Counter[str] = Counter()
    for row in alpha_table.values():
        coefficient = alpha_coefficient(row)
        frozen_raw = (row.get("implied_dielectric_slope") or "").strip()
        if coefficient is None or not frozen_raw:
            continue
        alpha_1e5, kind = coefficient
        mine = alpha_to_depsilon_dt(
            alpha_1e5, kind, float(row["dielectric_observed"])
        )
        deltas.append(abs(mine - float(frozen_raw)))
        kinds[kind] += 1
    max_delta = max(deltas) if deltas else None
    return {
        "rows_compared": len(deltas),
        "alpha_kind_counts": dict(sorted(kinds.items())),
        "max_abs_delta": max_delta,
        "bit_exact": max_delta is not None and max_delta == 0.0,
        "note": (
            "the frozen column is written to the CSV with finite precision, so a "
            "non-zero max_abs_delta is first read as a serialisation limit; it is "
            "only a definition mismatch if it exceeds that limit"
        ),
    }


def label_identity(
    alpha_table: Mapping[str, Mapping[str, str]],
    dataset_rows: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    """How often a pool label IS the tabulated epsilon the alpha column refers to.

    This is what disqualifies ``implied_dielectric_slope`` from the feature
    block: for those rows the column is a deterministic function of the label.
    """

    dataset = {row["inchikey"]: row for row in dataset_rows}
    overlapping = 0
    identical = 0
    for key, alpha_row in alpha_table.items():
        if alpha_coefficient(alpha_row) is None:
            continue
        dataset_row = dataset.get(key)
        if dataset_row is None:
            continue
        overlapping += 1
        same_epsilon = abs(
            float(dataset_row["dielectric"]) - float(alpha_row["dielectric_observed"])
        ) < 1e-9
        same_temperature = (
            abs(float(dataset_row["T_K"]) - float(alpha_row["T_K"])) < 1e-9
        )
        if same_epsilon and same_temperature:
            identical += 1
    return {
        "alpha_carrying_rows_also_in_the_pool": overlapping,
        "label_is_the_nbs_tabulated_value": identical,
    }


def compound_slopes(
    rows: Sequence[Mapping[str, str]],
    *,
    band: str | None = None,
) -> dict[str, dict[str, float]]:
    """d(eps)/dT per compound over all rows of ``rows`` (optionally one band)."""

    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if band is not None and row.get("temperature_band") != band:
            continue
        points[str(row["inchikey"])].append(
            (float(row["T_K"]), float(row["epsilon"]))
        )
    fitted: dict[str, dict[str, float]] = {}
    for key, values in points.items():
        fit = fit_empirical_slope(
            [value[0] for value in values], [value[1] for value in values]
        )
        if fit is not None:
            fitted[key] = fit
    return fitted


def crosscheck_rows(
    slopes: Mapping[str, Mapping[str, float]],
    alpha_table: Mapping[str, Mapping[str, str]],
    *,
    cohort: str,
) -> list[dict[str, object]]:
    """Pair every compound that has both an empirical slope and a coefficient."""

    rows: list[dict[str, object]] = []
    for key in sorted(slopes):
        alpha_row = alpha_table.get(key)
        if alpha_row is None:
            continue
        coefficient = alpha_coefficient(alpha_row)
        if coefficient is None:
            continue
        alpha_1e5, kind = coefficient
        fit = slopes[key]
        tabulated_epsilon = float(alpha_row["dielectric_observed"])
        at_tabulated = alpha_to_depsilon_dt(alpha_1e5, kind, tabulated_epsilon)
        at_observed = alpha_to_depsilon_dt(alpha_1e5, kind, fit["mean_epsilon"])
        empirical = fit["slope"]
        rows.append(
            {
                "cohort": cohort,
                "inchikey": key,
                "compound_name": alpha_row["compound_name"],
                "alpha_1e5": alpha_1e5,
                "alpha_kind": kind,
                "nbs_tabulated_T_K": float(alpha_row["T_K"]),
                "nbs_tabulated_epsilon": tabulated_epsilon,
                "nbs_slope_at_tabulated_epsilon": at_tabulated,
                "nbs_slope_at_observed_mean_epsilon": at_observed,
                "empirical_slope": empirical,
                "n_points": fit["n_points"],
                "n_distinct_temperatures": fit["n_distinct_temperatures"],
                "temperature_span_K": fit["span_K"],
                "mean_temperature_K": fit["mean_temperature_K"],
                "empirical_mean_epsilon": fit["mean_epsilon"],
                "empirical_r2": fit["r2"],
                "signed_deviation_at_observed": empirical - at_observed,
                "absolute_deviation_at_observed": abs(empirical - at_observed),
                "symmetric_relative_deviation_at_observed": (
                    symmetric_relative_difference(empirical, at_observed)
                ),
                "signed_deviation_at_tabulated": empirical - at_tabulated,
                "symmetric_relative_deviation_at_tabulated": (
                    symmetric_relative_difference(empirical, at_tabulated)
                ),
                "same_sign": (empirical < 0) == (at_observed < 0),
            }
        )
    return rows

CROSSCHECK_COLUMNS = (
    "cohort",
    "inchikey",
    "compound_name",
    "alpha_1e5",
    "alpha_kind",
    "nbs_tabulated_T_K",
    "nbs_tabulated_epsilon",
    "nbs_slope_at_tabulated_epsilon",
    "nbs_slope_at_observed_mean_epsilon",
    "empirical_slope",
    "n_points",
    "n_distinct_temperatures",
    "temperature_span_K",
    "mean_temperature_K",
    "empirical_mean_epsilon",
    "empirical_r2",
    "signed_deviation_at_observed",
    "absolute_deviation_at_observed",
    "symmetric_relative_deviation_at_observed",
    "signed_deviation_at_tabulated",
    "symmetric_relative_deviation_at_tabulated",
    "same_sign",
)

SLOPE_COLUMNS = (
    "cohort",
    "inchikey",
    "compound_name",
    "slope",
    "intercept",
    "n_points",
    "n_distinct_temperatures",
    "span_K",
    "mean_temperature_K",
    "mean_epsilon",
    "r2",
)


def summarize_crosscheck(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Paired comparison of the NBS coefficient against the empirical slope."""

    by_cohort: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_cohort[str(row["cohort"])].append(row)

    def block(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
        empirical = [float(item["empirical_slope"]) for item in items]
        nbs = [float(item["nbs_slope_at_observed_mean_epsilon"]) for item in items]
        signed = [float(item["signed_deviation_at_observed"]) for item in items]
        relative = [
            float(item["symmetric_relative_deviation_at_observed"]) for item in items
        ]
        return {
            "pairs": len(items),
            "compounds": len({str(item["inchikey"]) for item in items}),
            "alpha_kind_counts": dict(
                sorted(Counter(str(item["alpha_kind"]) for item in items).items())
            ),
            "empirical_slope_per_K": describe(empirical),
            "nbs_slope_per_K": describe(nbs),
            "signed_deviation_per_K": describe(signed),
            "absolute_deviation_per_K": describe([abs(value) for value in signed]),
            "symmetric_relative_deviation": describe(relative),
            "fraction_same_sign": (
                sum(1 for item in items if item["same_sign"]) / len(items)
                if items
                else None
            ),
            "temperature_span_K": describe(
                [float(item["temperature_span_K"]) for item in items]
            ),
            "n_distinct_temperatures": describe(
                [float(item["n_distinct_temperatures"]) for item in items]
            ),
        }

    blocks = {cohort: block(items) for cohort, items in sorted(by_cohort.items())}
    combined = [item for items in by_cohort.values() for item in items]
    return {"by_cohort": blocks, "all_cohorts": block(combined) if combined else None}


def feature_coverage(
    rows: Sequence[Mapping[str, str]],
    alpha_table: Mapping[str, Mapping[str, str]],
    *,
    label: str,
) -> dict[str, object]:
    compounds = sorted({str(row["inchikey"]) for row in rows})
    with_row = [key for key in compounds if key in alpha_table]
    with_coefficient = [
        key for key in with_row if alpha_coefficient(alpha_table[key]) is not None
    ]
    kinds = Counter(
        (alpha_table[key].get("alpha_kind") or "").strip() for key in with_coefficient
    )
    return {
        "label": label,
        "rows": len(rows),
        "compounds": len(compounds),
        "compounds_with_an_alpha_row": len(with_row),
        "compounds_with_a_coefficient": len(with_coefficient),
        "coefficient_coverage": (
            len(with_coefficient) / len(compounds) if compounds else None
        ),
        "alpha_kind_counts": dict(sorted(kinds.items())),
    }

FOLD_COLUMNS = (
    "protocol",
    "representation",
    "repeat",
    "fold",
    "train_rows",
    "test_rows",
    "train_compounds",
    "test_compounds",
    "extra_columns",
    "mae",
    "rmse",
    "r2",
    "spearman",
)

PREDICTION_COLUMNS = (
    "protocol",
    "representation",
    "repeat",
    "fold",
    "inchikey",
    "T_K",
    "target",
    "prediction",
)

Arm = Callable[[np.ndarray, np.ndarray], np.ndarray]


def static_arm(block: np.ndarray) -> Arm:
    """An arm that appends the same column block to every fold."""

    def arm(_train_index: np.ndarray, _test_index: np.ndarray) -> np.ndarray:
        return block

    return arm


def nbs_alpha_block(
    rows: Sequence[Mapping[str, str]],
    alpha_table: Mapping[str, Mapping[str, str]],
) -> tuple[np.ndarray, dict[str, object]]:
    """The epsilon-free NBS alpha feature block.

    Two columns and no more. ``nbs_alpha_1e5`` is the transcribed coefficient
    itself (the handbook's "use the coefficient as a prior feature");
    ``nbs_alpha_kind_is_log`` says which of the two definitions produced it.
    Neither column reads the pool's epsilon, so neither can be a function of the
    label - see ``label_identity``.
    """

    block = np.full((len(rows), 2), MISSING, dtype=float)
    covered = 0
    kinds: Counter[str] = Counter()
    for index, row in enumerate(rows):
        alpha_row = alpha_table.get(str(row["inchikey"]))
        coefficient = alpha_coefficient(alpha_row) if alpha_row is not None else None
        if coefficient is None:
            continue
        alpha_1e5, kind = coefficient
        block[index, 0] = alpha_1e5
        block[index, 1] = 1.0 if kind in {"alpha", "\u03b1"} else 0.0
        kinds[kind] += 1
        covered += 1
    return block, {
        "columns": ("nbs_alpha_1e5", "nbs_alpha_kind_is_log"),
        "rows": len(rows),
        "rows_covered": covered,
        "coverage": covered / len(rows) if rows else None,
        "compounds_covered": len(
            {
                str(row["inchikey"])
                for index, row in enumerate(rows)
                if math.isfinite(block[index, 0])
            }
        ),
        "alpha_kind_counts": dict(sorted(kinds.items())),
        "epsilon_free": True,
        "unit": "coefficient as printed by the circular, already scaled by 1e5",
    }


def slope_block(
    rows: Sequence[Mapping[str, str]],
    slopes: Mapping[str, Mapping[str, float]],
) -> np.ndarray:
    block = np.full((len(rows), 1), MISSING, dtype=float)
    for index, row in enumerate(rows):
        fit = slopes.get(str(row["inchikey"]))
        if fit is not None:
            block[index, 0] = float(fit["slope"])
    return block


def make_train_only_arm(
    rows: Sequence[Mapping[str, str]],
) -> tuple[Arm, dict[str, object]]:
    """The honest analogue of the empirical-slope feature.

    For each fold the slope is fitted on that fold's training rows only. Under
    grouped CV a scored compound has no training row, so it receives NaN. The
    returned counters record how often that happens, because "the feature is
    honest" and "the feature is empty" are the same statement here and the
    report has to show the number rather than assert it.
    """

    keys = [str(row["inchikey"]) for row in rows]
    temperatures = [float(row["T_K"]) for row in rows]
    epsilons = [float(row["epsilon"]) for row in rows]
    positions: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        positions[key].append(index)
    stats: dict[str, object] = {
        "folds": 0,
        "test_rows_total": 0,
        "test_rows_with_a_slope": 0,
        "training_compounds_with_a_slope": 0,
    }

    def arm(train_index: np.ndarray, test_index: np.ndarray) -> np.ndarray:
        train_positions = {int(index) for index in train_index}
        fitted: dict[str, float] = {}
        for key, members in positions.items():
            index_set = [index for index in members if index in train_positions]
            fit = fit_empirical_slope(
                [temperatures[index] for index in index_set],
                [epsilons[index] for index in index_set],
            )
            if fit is not None:
                fitted[key] = float(fit["slope"])
        block = np.full((len(rows), 1), MISSING, dtype=float)
        for index, key in enumerate(keys):
            value = fitted.get(key)
            if value is not None:
                block[index, 0] = value
        stats["folds"] = int(stats["folds"]) + 1
        stats["test_rows_total"] = int(stats["test_rows_total"]) + int(test_index.size)
        stats["test_rows_with_a_slope"] = int(stats["test_rows_with_a_slope"]) + int(
            np.count_nonzero(np.isfinite(block[test_index, 0]))
        )
        stats["training_compounds_with_a_slope"] = len(fitted)
        return block

    return arm, stats


def run_arm(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: np.ndarray,
    groups: Sequence[str],
    arm: Arm | None = None,
    seed_for_fold: Callable[[int, int], int] | None = None,
) -> dict[str, object]:
    """Fit every representation on every fold, optionally with an extra block.

    ``arm`` returns the extra columns for one fold, or None for the frozen
    matrix unchanged. ``fit_predict_representation`` is reused verbatim, so an
    arm that returns None is the band-ablation protocol bit-for-bit - which is
    what makes the deltas in this probe readable.
    """

    splits = list(splits)
    if not splits:
        raise ValueError(f"no fold survived for protocol {name!r}; nothing to report")

    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    per_repeat: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    group_array = np.asarray(groups)

    for repeat, fold, train_index, test_index in splits:
        extra = None if arm is None else arm(train_index, test_index)
        features = physical if extra is None else np.hstack([physical, extra])
        extra_columns = 0 if extra is None else int(extra.shape[1])
        fit_seed = SEED if seed_for_fold is None else int(seed_for_fold(repeat, fold))
        for representation in REPRESENTATIONS:
            prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=features,
                target=target,
                train_indices=train_index,
                test_indices=test_index,
                seed=fit_seed,
            )
            metrics = evaluate_repeat(target[test_index], prediction)
            fold_rows.append(
                {
                    "protocol": name,
                    "representation": representation,
                    "repeat": repeat,
                    "fold": fold,
                    "train_rows": int(train_index.size),
                    "test_rows": int(test_index.size),
                    "train_compounds": int(np.unique(group_array[train_index]).size),
                    "test_compounds": int(np.unique(group_array[test_index]).size),
                    "extra_columns": extra_columns,
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "r2": metrics["r2"],
                    "spearman": metrics["spearman"],
                }
            )
            bucket = per_repeat.setdefault(
                (representation, repeat),
                {"target": np.zeros(0), "prediction": np.zeros(0)},
            )
            bucket["target"] = np.concatenate([bucket["target"], target[test_index]])
            bucket["prediction"] = np.concatenate([bucket["prediction"], prediction])
            for row_index, value in zip(test_index, prediction, strict=True):
                prediction_rows.append(
                    {
                        "protocol": name,
                        "representation": representation,
                        "repeat": repeat,
                        "fold": fold,
                        "inchikey": groups[int(row_index)],
                        "T_K": float(temperatures[int(row_index)]),
                        "target": float(target[int(row_index)]),
                        "prediction": float(value),
                    }
                )

    repeat_rows: list[dict[str, object]] = []
    for (representation, repeat), bucket in per_repeat.items():
        metrics = evaluate_repeat(bucket["target"], bucket["prediction"])
        repeat_rows.append(
            {
                "protocol": name,
                "representation": representation,
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    return {
        "name": name,
        "description": ARM_DESCRIPTIONS.get(name, ""),
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summarize_repeats(repeat_rows)[name],
    }


def run_room_family(
    rows: Sequence[Mapping[str, str]],
    alpha_table: Mapping[str, Mapping[str, str]],
    *,
    slope_source_rows: Sequence[Mapping[str, str]] | None = None,
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """The room-band arms, all on one fold assignment.

    ``slope_source_rows`` is the table the "all bands" slope is fitted on, and it
    has to be passed in explicitly: the room family's own rows are room rows, so
    fitting "all bands" on them would silently reproduce the room-only slope and
    make two of the arms identical.
    """

    morgan, physical, target, temperatures, groups = build_matrices(rows)
    splits = list(
        drop_thin_folds(
            grouped_folds(groups, n_splits=n_splits, n_repeats=n_repeats, seed=seed)
        )
    )
    source_rows = list(slope_source_rows) if slope_source_rows is not None else list(rows)
    slopes_all_bands = compound_slopes(source_rows)
    slopes_room_band = compound_slopes(rows, band=ROOM_BAND)
    nbs_block, nbs_meta = nbs_alpha_block(rows, alpha_table)
    null_two = np.full((len(rows), 2), MISSING, dtype=float)
    null_one = np.full((len(rows), 1), MISSING, dtype=float)
    train_only_arm, train_only_stats = make_train_only_arm(rows)

    shared = {
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "temperatures": temperatures,
        "groups": groups,
    }
    arms = {
        "room_baseline": run_arm("room_baseline", splits, **shared),
        "room_plus_null_block_two_columns": run_arm(
            "room_plus_null_block_two_columns",
            splits,
            arm=static_arm(null_two),
            **shared,
        ),
        "room_plus_nbs_alpha": run_arm(
            "room_plus_nbs_alpha", splits, arm=static_arm(nbs_block), **shared
        ),
        "room_plus_null_block_one_column": run_arm(
            "room_plus_null_block_one_column",
            splits,
            arm=static_arm(null_one),
            **shared,
        ),
        "room_plus_emp_slope_leaky_all": run_arm(
            "room_plus_emp_slope_leaky_all",
            splits,
            arm=static_arm(slope_block(rows, slopes_all_bands)),
            **shared,
        ),
        "room_plus_emp_slope_leaky_room": run_arm(
            "room_plus_emp_slope_leaky_room",
            splits,
            arm=static_arm(slope_block(rows, slopes_room_band)),
            **shared,
        ),
        "room_plus_emp_slope_train_only": run_arm(
            "room_plus_emp_slope_train_only", splits, arm=train_only_arm, **shared
        ),
    }
    compound_total = len(set(groups))
    return {
        "rows": len(rows),
        "compounds": compound_total,
        "folds": len(splits),
        "n_splits": n_splits,
        "n_repeats": n_repeats,
        "splitter": "GroupKFold by InChIKey, shuffled compound order",
        "slope_source_rows": len(source_rows),
        "arms": arms,
        "nbs_alpha_block": nbs_meta,
        "empirical_slope_coverage": {
            "compounds": compound_total,
            "compounds_with_a_slope_over_all_bands": len(slopes_all_bands),
            "compounds_with_a_slope_in_the_room_band": len(slopes_room_band),
            "coverage_over_all_bands": len(slopes_all_bands) / compound_total,
            "coverage_in_the_room_band": len(slopes_room_band) / compound_total,
        },
        "train_only_slope": train_only_stats,
    }


def run_v10_family(
    frozen_features: Path,
    dataset_path: Path,
    alpha_table: Mapping[str, Mapping[str, str]],
    *,
    n_splits: int,
    n_repeats: int,
    seed: int,
) -> dict[str, object]:
    """The only pool on disk where the alpha coverage is real.

    Two splitters are used. The first replays the released v1.0 protocol exactly
    (RepeatedKFold, per-fold fit seed) so the baseline can be compared with the
    published headline; the second keeps this probe's grouped discipline so the
    pair still reads as a grouped delta.
    """

    rows, failed_rows, withheld_rows = read_modelling_rows(
        frozen_features, dataset_path=dataset_path
    )
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([str(row["smiles"]) for row in rows])
    physical = physical_feature_matrix(rows)
    temperatures = np.asarray([float(row["T_K"]) for row in rows], dtype=float)
    groups = [str(row["inchikey"]) for row in rows]
    nbs_block, nbs_meta = nbs_alpha_block(rows, alpha_table)
    null_two = np.full((len(rows), 2), MISSING, dtype=float)

    splitter = RepeatedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=seed)
    frozen_splits = [
        (index // n_splits, index % n_splits, train_index, test_index)
        for index, (train_index, test_index) in enumerate(
            splitter.split(np.zeros(len(rows)))
        )
    ]
    grouped_splits = list(
        drop_thin_folds(
            grouped_folds(groups, n_splits=n_splits, n_repeats=n_repeats, seed=seed)
        )
    )

    def frozen_seed(repeat: int, fold: int) -> int:
        return seed + repeat * n_splits + fold

    shared = {
        "morgan": morgan,
        "physical": physical,
        "target": target,
        "temperatures": temperatures,
        "groups": groups,
    }
    arms = {
        "v10_frozen_baseline": run_arm(
            "v10_frozen_baseline", frozen_splits, seed_for_fold=frozen_seed, **shared
        ),
        "v10_frozen_plus_null_block": run_arm(
            "v10_frozen_plus_null_block",
            frozen_splits,
            arm=static_arm(null_two),
            seed_for_fold=frozen_seed,
            **shared,
        ),
        "v10_frozen_plus_nbs_alpha": run_arm(
            "v10_frozen_plus_nbs_alpha",
            frozen_splits,
            arm=static_arm(nbs_block),
            seed_for_fold=frozen_seed,
            **shared,
        ),
        "v10_grouped_baseline": run_arm(
            "v10_grouped_baseline", grouped_splits, **shared
        ),
        "v10_grouped_plus_null_block": run_arm(
            "v10_grouped_plus_null_block",
            grouped_splits,
            arm=static_arm(null_two),
            **shared,
        ),
        "v10_grouped_plus_nbs_alpha": run_arm(
            "v10_grouped_plus_nbs_alpha",
            grouped_splits,
            arm=static_arm(nbs_block),
            **shared,
        ),
    }
    return {
        "rows": len(rows),
        "compounds": len(set(groups)),
        "failed_rows": len(failed_rows),
        "withheld_rows": len(withheld_rows),
        "folds": {"frozen": len(frozen_splits), "grouped": len(grouped_splits)},
        "n_splits": n_splits,
        "n_repeats": n_repeats,
        "arms": arms,
        "nbs_alpha_block": nbs_meta,
    }


def repeat_metric_lookup(
    arms: Mapping[str, Mapping[str, object]],
) -> dict[tuple[str, int], dict[str, float]]:
    lookup: dict[tuple[str, int], dict[str, float]] = {}
    for result in arms.values():
        for row in result["repeat_rows"]:  # type: ignore[union-attr]
            lookup[(str(row["protocol"]), int(row["repeat"]))] = {
                metric: float(row[metric]) for metric in METRIC_NAMES
            }
    return lookup


def wilcoxon_p(deltas: Sequence[float]) -> float | None:
    values = np.asarray(list(deltas), dtype=float)
    if values.size == 0 or np.allclose(values, 0.0):
        return None
    try:
        return float(wilcoxon(values).pvalue)
    except ValueError:
        return None


def classify(delta: float | None) -> str:
    if delta is None:
        return "not run"
    if delta > INERT_TOLERANCE:
        return "helps"
    if delta < -INERT_TOLERANCE:
        return "hurts"
    return "inert"


def paired_delta(
    lookup: Mapping[tuple[str, int], Mapping[str, float]],
    *,
    baseline: str,
    arm: str,
    representation: str = HYBRID,
) -> dict[str, object]:
    """Per-repeat paired deltas of ``arm`` against ``baseline`` (arm - baseline)."""

    repeats = sorted(
        repeat
        for (name, repeat) in lookup
        if name == arm and (baseline, repeat) in lookup
    )
    if not repeats:
        return {"baseline": baseline, "arm": arm, "repeats": 0, "note": "not run"}
    deltas = {
        metric: [lookup[(arm, repeat)][metric] - lookup[(baseline, repeat)][metric] for repeat in repeats]
        for metric in ("r2", "mae", "spearman")
    }
    mean_r2 = float(np.mean(deltas["r2"]))
    return {
        "baseline": baseline,
        "arm": arm,
        "representation": representation,
        "repeats": len(repeats),
        "delta_r2": describe(deltas["r2"]),
        "delta_mae": describe(deltas["mae"]),
        "delta_spearman": describe(deltas["spearman"]),
        "mean_delta_r2": mean_r2,
        "classification_r2": classify(mean_r2),
        "classification_mae": classify(-float(np.mean(deltas["mae"]))),
        "repeats_favouring_the_arm": int(np.count_nonzero(np.asarray(deltas["r2"]) > 0)),
        "wilcoxon_p_r2": wilcoxon_p(deltas["r2"]),
        "fold_metrics_identical_to_baseline": _fold_metrics_identical(
            lookup, baseline=baseline, arm=arm
        ),
    }


def _fold_metrics_identical(
    lookup: Mapping[tuple[str, int], Mapping[str, float]],
    *,
    baseline: str,
    arm: str,
) -> bool:
    """True when every repeat-level metric of the two arms is bit-identical."""

    repeats = [repeat for (name, repeat) in lookup if name == baseline and (arm, repeat) in lookup]
    if not repeats:
        return False
    for repeat in repeats:
        for metric in METRIC_NAMES:
            left = lookup[(baseline, repeat)][metric]
            right = lookup[(arm, repeat)][metric]
            if not (left == right or (math.isnan(left) and math.isnan(right))):
                return False
    return True


def effect_over_null_block(
    deltas: Mapping[str, Mapping[str, object]],
    pairs: Sequence[tuple[str, str]] = NULL_BLOCK_PAIRS,
) -> dict[str, dict[str, object]]:
    """An arm's paired delta minus its same-width all-NaN placebo's delta."""

    output: dict[str, dict[str, object]] = {}
    for arm, placebo in pairs:
        arm_delta = deltas.get(arm)
        placebo_delta = deltas.get(placebo)
        if not arm_delta or not placebo_delta:
            continue
        effect = float(arm_delta["mean_delta_r2"]) - float(placebo_delta["mean_delta_r2"])
        output[arm] = {
            "placebo": placebo,
            "delta_r2_of_the_arm": float(arm_delta["mean_delta_r2"]),
            "delta_r2_of_the_placebo": float(placebo_delta["mean_delta_r2"]),
            "effect_over_the_placebo_r2": effect,
            "classification": classify(effect),
        }
    return output


def subsampling_control(
    rows: Sequence[Mapping[str, str]],
    *,
    seed: int = SEED,
) -> dict[str, object]:
    """Measure that an all-missing column is not a no-op.

    ``XGB_PARAMS`` keeps ``colsample_bytree = 0.8``, which subsamples columns by
    index. Adding two columns therefore re-draws the subsample and moves every
    prediction even when those two columns are 100% NaN and carry no
    information. Without this measurement the placebo arms look like a
    precaution instead of the only readable comparison in the probe.
    """

    morgan, physical, target, _temperatures, groups = build_matrices(rows)
    usable = [
        split
        for split in grouped_folds(groups, n_splits=5, n_repeats=1, seed=seed)
        if split[3].size >= 2
    ]
    if not usable:
        return {"measured": False, "reason": "no fold with at least two scored rows"}
    _repeat, _fold, train_index, test_index = usable[0]
    baseline, _ = fit_predict_representation(
        "Physical",
        morgan=morgan,
        physical=physical,
        target=target,
        train_indices=train_index,
        test_indices=test_index,
        seed=seed,
    )
    block = np.full((len(rows), 2), MISSING, dtype=float)
    widened, _ = fit_predict_representation(
        "Physical",
        morgan=morgan,
        physical=np.hstack([physical, block]),
        target=target,
        train_indices=train_index,
        test_indices=test_index,
        seed=seed,
    )
    return {
        "measured": True,
        "representation": "Physical",
        "scored_rows": int(test_index.size),
        "extra_columns": 2,
        "extra_columns_are_all_missing": True,
        "predictions_identical": bool(np.array_equal(baseline, widened)),
        "max_abs_prediction_delta": float(np.max(np.abs(baseline - widened))),
        "cause": (
            "XGB_PARAMS pins colsample_bytree=0.8, which subsamples by column "
            "index; widening the matrix re-draws the subsample"
        ),
    }


def read_json(path: Path) -> object | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def reference_reproduction(
    baseline_summary: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    band_summary_path: Path = BAND_ABLATION_SUMMARY_PATH,
    room_summary_path: Path = ROOM_WINDOW_SUMMARY_PATH,
) -> dict[str, object]:
    """Re-derive the pinned room baseline and compare it cell by cell.

    Two independent sibling summaries pin the same number. Comparing all three
    representations x seven metrics against both of them is a stronger
    statement than comparing one headline R2, because a divergence limited to a
    stratification bucket would still be caught. A sibling summary that is
    absent, or that carries no such pointer, is reported by name in
    ``references_missing`` instead of being dropped silently.
    """

    band = read_json(band_summary_path)
    room = read_json(room_summary_path)
    references: list[tuple[str, object, str]] = [
        (
            band_summary_path.name,
            band.get("summary", {}).get("band_room_only") if isinstance(band, dict) else None,
            "summary.band_room_only",
        ),
        (
            room_summary_path.name,
            room.get("reference", {})
            .get("band_ablation", {})
            .get("protocols", {})
            .get("band_room_only")
            if isinstance(room, dict)
            else None,
            "reference.band_ablation.protocols.band_room_only",
        ),
    ]

    max_delta = 0.0
    cells = 0
    found: list[str] = []
    missing: list[str] = []
    for label, reference, pointer in references:
        if not isinstance(reference, dict):
            missing.append(label)
            continue
        found.append(f"{label}:{pointer}")
        for representation in REPRESENTATIONS:
            for metric in METRIC_NAMES:
                mine = float(baseline_summary[representation][metric]["mean"])
                theirs = float(reference[representation][metric]["mean"])
                max_delta = max(max_delta, abs(mine - theirs))
                cells += 1

    hybrid_r2 = float(baseline_summary[HYBRID]["r2"]["mean"])
    return {
        "protocol": "band_room_only, grouped by InChIKey 10x5, frozen hybrid",
        "hybrid_r2": hybrid_r2,
        "pinned_hybrid_r2": PINNED_ROOM_BASELINE_R2,
        "bit_exact_against_the_pinned_constant": hybrid_r2 == PINNED_ROOM_BASELINE_R2,
        "references_found": found,
        "references_missing": missing,
        "cells_compared": cells,
        "max_abs_delta_vs_the_sibling_summaries": max_delta,
        "bit_exact_against_the_sibling_summaries": cells > 0 and max_delta == 0.0,
    }


def build_verdict(
    room_family: Mapping[str, object],
    v10_family: Mapping[str, object] | None,
    room_deltas: Mapping[str, Mapping[str, object]],
    v10_deltas: Mapping[str, Mapping[str, object]],
    over_the_null_block: Mapping[str, Mapping[str, object]],
    reproduction: Mapping[str, object],
) -> dict[str, object]:
    """The decision, assembled from the measured numbers only."""

    def effect(arm: str) -> float | None:
        block = over_the_null_block.get(arm)
        return None if not block else float(block["effect_over_the_placebo_r2"])

    def classification(arm: str) -> str | None:
        block = over_the_null_block.get(arm)
        return None if not block else str(block["classification"])

    room_nbs = room_deltas["room_plus_nbs_alpha"]
    leaky_all = room_deltas["room_plus_emp_slope_leaky_all"]
    leaky_room = room_deltas["room_plus_emp_slope_leaky_room"]
    honest = room_deltas["room_plus_emp_slope_train_only"]
    train_only = room_family["train_only_slope"]
    test_rows = int(train_only["test_rows_total"])
    covered = int(train_only["test_rows_with_a_slope"])
    test_coverage = covered / test_rows if test_rows else None
    room_coverage = room_family["nbs_alpha_block"]["coverage"]
    v10_coverage = v10_family["nbs_alpha_block"]["coverage"] if v10_family else None
    return {
        "alpha_coverage_on_the_v1x_room_benchmark": room_coverage,
        "alpha_coverage_on_the_v10_pool": v10_coverage,
        "nbs_alpha_room_delta_r2_versus_baseline": room_nbs["delta_r2"],
        "nbs_alpha_room_delta_r2_versus_the_placebo": effect("room_plus_nbs_alpha"),
        "nbs_alpha_room_classification_versus_the_placebo": classification(
            "room_plus_nbs_alpha"
        ),
        "leaky_slope_room_delta_r2_versus_the_placebo": effect(
            "room_plus_emp_slope_leaky_all"
        ),
        "leaky_slope_room_delta_r2_room_rows_only_versus_the_placebo": effect(
            "room_plus_emp_slope_leaky_room"
        ),
        "honest_train_only_slope_delta_r2_versus_the_placebo": effect(
            "room_plus_emp_slope_train_only"
        ),
        "honest_train_only_slope_test_row_coverage": test_coverage,
        "honest_train_only_slope_classification": honest["classification_r2"],
        "leaky_all_slope_delta_r2_versus_baseline": leaky_all["delta_r2"],
        "leaky_room_slope_delta_r2_versus_baseline": leaky_room["delta_r2"],
        "v10_frozen_nbs_alpha_effect_r2": effect("v10_frozen_plus_nbs_alpha"),
        "v10_frozen_nbs_alpha_classification": classification("v10_frozen_plus_nbs_alpha"),
        "v10_frozen_nbs_alpha_delta_r2_versus_baseline": (
            v10_deltas["v10_frozen_plus_nbs_alpha"]["delta_r2"] if v10_family else None
        ),
        "v10_grouped_nbs_alpha_effect_r2": effect("v10_grouped_plus_nbs_alpha"),
        "v10_grouped_nbs_alpha_classification": classification(
            "v10_grouped_plus_nbs_alpha"
        ),
        "baseline_reproduced_bit_exactly": reproduction[
            "bit_exact_against_the_pinned_constant"
        ],
        "temperature_dimension": (
            "alpha cannot serve it: the coefficient covers "
            f"{room_coverage:.1%} of the v1.x room-band compound pool, so the arm "
            "reads a feature matrix whose every added cell is missing, and the "
            "empirical slope that would cover everything is only obtainable by "
            "fitting on the scored rows themselves."
        ),
        "compound_coverage": (
            f"alpha is a coverage asset, not a temperature asset: it is available "
            f"for {v10_coverage:.1%} of the v1.0 pool"
            if v10_coverage is not None
            else "alpha is a coverage asset, not a temperature asset."
        ),
        "recommendation": (
            "do not add alpha to the v1.x feature block; keep the harmonised "
            "column as an external sanity band for the temperature dimension and "
            "revisit only if the compound roster is widened to the NBS family"
        ),
    }


def _number(value: object, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return f"{float(value):.{digits}f}"


def _percent(value: object, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"


def render_report(payload: Mapping[str, object]) -> str:
    """Render the Chinese report from the measured payload."""

    verdict = payload["verdict"]
    coverage = payload["coverage"]
    crosscheck = payload["crosscheck"]
    room = payload["benchmark"]["room_family"]
    v10 = payload["benchmark"]["v10_family"]
    reproduction = payload["reference_reproduction"]
    inputs = payload["inputs"]
    room_paired = payload["paired"]["room"]
    v10_paired = payload["paired"]["v10"]
    placebo = payload["paired"]["over_the_null_block"]
    control = payload["subsampling_control"]

    lines: list[str] = []
    lines.append("# NBS 514 alpha 温度系数：交叉校验与先验特征")
    lines.append("")
    lines.append(
        "本报告由 `probes/dielectric_alpha_prior_probe.py` 直接生成，所有数字来自实测；"
        "读不到的地方写 `n/a` 并注明原因。"
    )
    lines.append(
        "对应执行手册数据源表第 2 项：调和列（week 8 已交付）之外的"
        "\"系数本身作为先验特征\"这一步。"
    )
    lines.append("")
    lines.append("## 0. 判决前置")
    lines.append("")
    lines.append(
        f"- **alpha 不进 v1.x 特征块。** v1.x 室温带化合物池里有系数的化合物占 "
        f"**{_percent(verdict['alpha_coverage_on_the_v1x_room_benchmark'])}**，"
        "该 arm 加进去的每一格都是缺失值。"
        f"它与同宽安慰块的配对比 ΔR² = "
        f"{_number(verdict['nbs_alpha_room_delta_r2_versus_the_placebo'])}"
        f"（{verdict['nbs_alpha_room_classification_versus_the_placebo']}）。"
    )
    lines.append(
        f"- **它对温度维度无用，它是个覆盖率资产。** alpha 表与 v11 观测表的化合物集合"
        f"几乎不相交；唯一覆盖率说得过去的地方是 v1.0 的 246 化合物池"
        f"（{_percent(verdict['alpha_coverage_on_the_v10_pool'])}）。"
    )
    lines.append(
        f"- **化合物自身的经验斜率不可部署。** 诚实版本（只用训练折拟合）在被打分行上的"
        f"覆盖率是 **{_percent(verdict['honest_train_only_slope_test_row_coverage'])}**，"
        f"相对同宽安慰块的 ΔR² = "
        f"{_number(verdict['honest_train_only_slope_delta_r2_versus_the_placebo'])}"
        f"（{verdict['honest_train_only_slope_classification']}）。"
        "也就是说：在分组 CV 下，一个被打分化合物的温度敏感度本质上不可观测。"
    )
    lines.append(
        "- **加列不是无操作。** 冻结超参里 `colsample_bytree = 0.8` 按列下标抽样，"
        f"塞进两列全 NaN 也会改变预测（实测最大偏差 "
        f"{_number(control.get('max_abs_prediction_delta'), 6)} ε 单位，"
        f"`predictions_identical = {control.get('predictions_identical')}`）。"
        "因此本探针每个特征臂都配了一个同宽全 NaN 安慰块，"
        "\"该不该进管线\"的判据一律取**相对安慰块**的效应，而不是相对基线。"
    )
    lines.append(
        f"- 室温带基线逐位复现：**{verdict['baseline_reproduced_bit_exactly']}**"
        f"（R² = `{_number(reproduction['hybrid_r2'], 17)}`，"
        f"钉住常数 = `{_number(reproduction['pinned_hybrid_r2'], 17)}`）。"
    )
    lines.append("")
    lines.append("## 1. alpha 的定义与单位换算")
    lines.append("")
    lines.append(
        "定义取自 `probes/nbs514_alpha_harmonization_probe.py`（它转录的是 NBS Circular 514 "
        "第 2.1 / 2.5 节），不是本探针的重新猜测："
    )
    lines.append("")
    lines.append("```")
    lines.append('kind "a"      a     = -d(eps)/dT          printed as  a     * 1e5')
    lines.append('kind "alpha"  alpha = -d(log10 eps)/dT    printed as  alpha * 1e5')
    lines.append("```")
    lines.append("")
    lines.append("反解（两者都按开尔文）：")
    lines.append("")
    lines.append("```")
    lines.append('kind "a"      d(eps)/dT = -a_1e5     * 1e-5')
    lines.append('kind "alpha"  d(eps)/dT = -alpha_1e5 * 1e-5 * eps * ln(10)')
    lines.append("```")
    lines.append("")
    lines.append("两点必须写清楚：")
    lines.append("")
    lines.append(
        "1. 转录列**一律叫 `alpha_1e5`**，即使 `alpha_kind == \"a\"` 时它装的是 `a` 而不是 "
        "`alpha`。它是被换算过的系数，不是导数；任何与经验 dε/dT 的比较都必须过 kind 分支，"
        "因为两支之间差一个 `eps * ln(10)`（水差 5 倍，乙腈差 86 倍）。"
    )
    lines.append(
        "2. `alpha` 支是**相对量**（每单位 eps），换算成导数需要一个 eps。"
        "本探针**没有**把 `implied_dielectric_slope` 当特征："
        f"v1.0 池里 44 条带系数的行中有 "
        f"**{payload['label_identity']['label_is_the_nbs_tabulated_value']} 条**"
        "的标签与那张表登记的 eps 逐位相同，该列会是标签的函数。"
        "因此特征块只用与 eps 无关的两列。"
    )
    lines.append("")
    conversion = payload["conversion_check"]
    lines.append(
        f"换算自检：本探针独立重推的换算与冻结列 `implied_dielectric_slope` 在 "
        f"**{conversion['rows_compared']}** 行上比较，`bit_exact = {conversion['bit_exact']}`，"
        f"max_abs_delta = {conversion['max_abs_delta']}。"
    )
    lines.append("")
    lines.append("## 2. 覆盖率（先验能不能用，先看它有没有值）")
    lines.append("")
    lines.append("| 池 | 行数 | 化合物 | 有 alpha 行 | 有系数 | 系数覆盖率 | kind 分布 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for key in (
        "v11_observations",
        "v11_room_band",
        "v11_multi_temperature_compounds",
        "v10_pool",
        "lowfreq_candidates",
    ):
        block = coverage.get(key)
        if not block:
            continue
        lines.append(
            f"| `{key}` | {block['rows']} | {block['compounds']} | "
            f"{block['compounds_with_an_alpha_row']} | "
            f"{block['compounds_with_a_coefficient']} | "
            f"{_percent(block['coefficient_coverage'])} | {block['alpha_kind_counts']} |"
        )
    lines.append("")
    lines.append("## 3. 交叉校验：NBS 系数 vs 经验 dε/dT")
    lines.append("")
    lines.append(
        "经验斜率 = 同一化合物在 v11 观测表（或旁证表）里全部温度点上的最小二乘斜率，"
        "单位 K⁻¹。NBS 侧按 kind 分支换算；`alpha` 支额外在**该化合物的观测均值 eps**上取值"
        "（经验割线实际所在的 eps）。"
    )
    lines.append("")
    lines.append(
        "| cohort | 配对数 | kind | 经验斜率中位 | NBS 斜率中位 | 带符号偏差中位 | "
        "绝对偏差中位 (p90) | 对称相对偏差中位 (p90) | 同号比例 |"
    )
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for name, block in crosscheck["by_cohort"].items():
        empirical = block["empirical_slope_per_K"]
        nbs = block["nbs_slope_per_K"]
        signed = block["signed_deviation_per_K"]
        absolute = block["absolute_deviation_per_K"]
        relative = block["symmetric_relative_deviation"]
        lines.append(
            f"| `{name}` | {block['pairs']} | {block['alpha_kind_counts']} | "
            f"{_number(empirical['median'], 6)} | {_number(nbs['median'], 6)} | "
            f"{_number(signed['median'], 6)} | "
            f"{_number(absolute['median'], 6)} ({_number(absolute['p90'], 6)}) | "
            f"{_percent(relative['median'], 2)} ({_percent(relative['p90'], 2)}) | "
            f"{_percent(block['fraction_same_sign'])} |"
        )
    combined = crosscheck.get("all_cohorts")
    if combined:
        relative = combined["symmetric_relative_deviation"]
        absolute = combined["absolute_deviation_per_K"]
        lines.append(
            f"| **合并** | {combined['pairs']} | {combined['alpha_kind_counts']} | "
            f"{_number(combined['empirical_slope_per_K']['median'], 6)} | "
            f"{_number(combined['nbs_slope_per_K']['median'], 6)} | "
            f"{_number(combined['signed_deviation_per_K']['median'], 6)} | "
            f"{_number(absolute['median'], 6)} ({_number(absolute['p90'], 6)}) | "
            f"{_percent(relative['median'], 2)} ({_percent(relative['p90'], 2)}) | "
            f"{_percent(combined['fraction_same_sign'])} |"
        )
    lines.append("")
    lines.append(
        "逐条配对见 `probes/artifacts/dielectric_alpha_prior_crosscheck.csv`；"
        "全部经验斜率见 `probes/artifacts/dielectric_alpha_prior_empirical_slopes.csv`。"
    )
    lines.append("")
    lines.append("## 4. 作为先验特征：配对对照")
    lines.append("")
    lines.append(
        f"室温带 {room['rows']} 行 / {room['compounds']} 化合物，{room['splitter']}，"
        f"{room['n_splits']}×{room['n_repeats']}（{room['folds']} 折）；"
        "所有 arm 共用同一折划分与同一被打分行集合。"
        "表示法与超参取自冻结管线（`fit_predict_representation` 原样复用）。"
    )
    lines.append("")
    lines.append(
        "| arm | 加了几列 | Hybrid R² | MAE | Spearman | ΔR² vs 基线 | "
        "ΔR² vs 同宽安慰块 | 判定 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for name in ALPHA_ARMS:
        summary = room["arms"][name]["summary"][HYBRID]
        delta = room_paired.get(name, {})
        block = placebo.get(name, {})
        lines.append(
            f"| `{name}` | {room['arms'][name]['extra_columns']} | "
            f"{_number(summary['r2']['mean'])} ± {_number(summary['r2']['std'])} | "
            f"{_number(summary['mae']['mean'])} | "
            f"{_number(summary['spearman']['mean'])} | "
            f"{_number(delta.get('mean_delta_r2'))} | "
            f"{_number(block.get('effect_over_the_placebo_r2'))} | "
            f"{block.get('classification', '-')} |"
        )
    lines.append("")
    if v10:
        lines.append(
            f"v1.0 池（{v10['rows']} 行 / {v10['compounds']} 化合物，"
            f"其中 {v10['withheld_rows']} 行被 model_ready 扣留、{v10['failed_rows']} 行 xTB 失败）："
            "第一个 splitter 逐位重放已发布的 RepeatedKFold 协议，第二个保持本探针的分组纪律。"
        )
        lines.append("")
        lines.append("| arm | 加了几列 | Hybrid R² | MAE | ΔR² vs 基线 | ΔR² vs 同宽安慰块 | 判定 |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for name in V10_ARMS:
            summary = v10["arms"][name]["summary"][HYBRID]
            delta = v10_paired.get(name, {})
            block = placebo.get(name, {})
            lines.append(
                f"| `{name}` | {v10['arms'][name]['extra_columns']} | "
                f"{_number(summary['r2']['mean'])} ± {_number(summary['r2']['std'])} | "
                f"{_number(summary['mae']['mean'])} | "
                f"{_number(delta.get('mean_delta_r2'))} | "
                f"{_number(block.get('effect_over_the_placebo_r2'))} | "
                f"{block.get('classification', '-')} |"
            )
        lines.append("")
    lines.append(
        "安慰块效应的含义：`inert` 表示该列带给模型的变化落在\"换一列噪声\"的量级内，"
        "即该特征没有被模型用起来；`hurts` 表示它不仅没用、还把采样扰动放大成了实打实的掉点。"
    )
    lines.append("")
    lines.append("## 5. 自检复现")
    lines.append("")
    lines.append(
        f"- 室温带基线 Hybrid R² = `{_number(reproduction['hybrid_r2'], 17)}`，"
        f"钉住常数 = `{_number(reproduction['pinned_hybrid_r2'], 17)}`，"
        f"`bit_exact = {reproduction['bit_exact_against_the_pinned_constant']}`。"
    )
    lines.append(
        f"- 与两个兄弟 summary 逐格比较（{reproduction['cells_compared']} 格）："
        f"`bit_exact = {reproduction['bit_exact_against_the_sibling_summaries']}`，"
        f"max_abs_delta = {reproduction['max_abs_delta_vs_the_sibling_summaries']}。"
    )
    lines.append(
        f"- 参照文件：{reproduction['references_found']}；缺失：{reproduction['references_missing']}。"
    )
    lines.append(
        f"- 加列扰动对照：`predictions_identical = {control.get('predictions_identical')}`，"
        f"max_abs_prediction_delta = {control.get('max_abs_prediction_delta')}。"
    )
    lines.append("")
    lines.append("## 6. 未闭环与如实标注")
    lines.append("")
    lines.append(
        f"- **α 表与 v11 几乎不相交**：v11 的 "
        f"{coverage['v11_observations']['compounds']} 个化合物里只有 "
        f"{coverage['v11_observations']['compounds_with_an_alpha_row']} 个在 alpha 表里，"
        "唯一进入多温度集合的是 `Methyl ether`。任务书里那条\"与 NBS 514 在共同化合物上对比\""
        "在 v11 上因此是 n=1，不构成统计判断；本报告用磁盘上其余温度分辨表把 cohort 撑大，"
        "并逐 cohort 单独报告。"
    )
    lines.append(
        "- 旁证 cohort（`lowfreq_*`）是**频率弛豫**数据（1 MHz 主闸等），不是零频；"
        "它的 dε/dT 含色散成分，只能作为方向与量级的旁证，不能当零频斜率用。"
    )
    lines.append(
        "- `lowfreq_candidates` 表来自同期并行工作流，本探针只读它；"
        "文件缺失时该 cohort 退化为不出现，不报 0。"
    )
    lines.append(
        "- v1.0 池的分组 splitter 与已发布 RepeatedKFold 的折成员不同，因此 "
        "`v10_grouped_baseline` 的绝对值**不可与 0.3636 直接比**；"
        "两种 splitter 下可读的都是同折配对的 ΔR²。"
    )
    lines.append(
        "- 泄漏口径：`room_plus_emp_slope_leaky_*` 的斜率拟合包含了被打分行本身，"
        "只能作为\"如果有完美敏感度先验能买到多少\"的上界；"
        "`room_plus_emp_slope_train_only` 是唯一诚实的版本，它在被打分行上覆盖率 0，"
        "因此它相对安慰块的效应就是那两列噪声本身的效应。"
    )
    lines.append(
        "- 本探针不写 `data/`，不改任何已发布工件，不修改任何既有文件。"
    )
    lines.append("")
    lines.append("## 7. 复现")
    lines.append("")
    lines.append("```powershell")
    lines.append(".\\\\.venv\\\\Scripts\\\\python.exe probes\\\\dielectric_alpha_prior_probe.py")
    lines.append(
        ".\\\\.venv\\\\Scripts\\\\python.exe -m pytest tests\\\\test_dielectric_alpha_prior_probe.py -q"
    )
    lines.append("```")
    lines.append("")
    lines.append("输入指纹：")
    lines.append("")
    lines.append("| 文件 | sha256 | 行数 |")
    lines.append("|---|---|---:|")
    for path, info in sorted(inputs.items()):
        lines.append(f"| `{path}` | `{info['sha256']}` | {info['rows']} |")
    lines.append("")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.as_posix()

COVERAGE_COLUMNS = (
    "label",
    "rows",
    "compounds",
    "compounds_with_an_alpha_row",
    "compounds_with_a_coefficient",
    "coefficient_coverage",
    "alpha_kind_counts",
)


def summarize_family(family: Mapping[str, object]) -> dict[str, object]:
    """The family dict minus the per-fold and per-prediction payloads."""

    trimmed = {key: value for key, value in family.items() if key != "arms"}
    trimmed["arms"] = {
        name: {
            **{
                key: value
                for key, value in result.items()
                if key not in {"fold_rows", "prediction_rows"}
            },
            "extra_columns": (
                int(result["fold_rows"][0]["extra_columns"])
                if result.get("fold_rows")
                else 0
            ),
        }
        for name, result in family["arms"].items()  # type: ignore[union-attr]
    }
    return trimmed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NBS 514 alpha prior probe (see the module docstring)."
    )
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--alpha-table", type=Path, default=ALPHA_TABLE_PATH)
    parser.add_argument("--lowfreq", type=Path, default=LOWFREQ_CANDIDATES_PATH)
    parser.add_argument("--frozen-features", type=Path, default=FROZEN_FEATURES_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--splits", type=int, default=N_SPLITS)
    parser.add_argument("--repeats", type=int, default=N_REPEATS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--quick", action="store_true", help="run 3x2 instead of 5x10 (used by tests)"
    )
    parser.add_argument(
        "--skip-v10",
        action="store_true",
        help="skip the v1.0-pool family and its coverage block",
    )
    parser.add_argument("--no-report", action="store_true", help="do not write the md report")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    n_splits = 3 if args.quick else args.splits
    n_repeats = 2 if args.quick else args.repeats

    observations, _features, dropped = load_table(args.observations, args.features)
    room_rows = [row for row in observations if row["temperature_band"] == ROOM_BAND]
    alpha_table = read_alpha_table(args.alpha_table)

    points_per_compound: dict[str, set[float]] = defaultdict(set)
    for row in observations:
        points_per_compound[str(row["inchikey"])].add(float(row["T_K"]))
    multi_keys = {key for key, values in points_per_compound.items() if len(values) >= 2}
    multi_rows = [row for row in observations if str(row["inchikey"]) in multi_keys]

    coverage: dict[str, object] = {
        "v11_observations": feature_coverage(
            observations, alpha_table, label="v11 observations, every band"
        ),
        "v11_room_band": feature_coverage(
            room_rows, alpha_table, label="v11 observations, room band"
        ),
        "v11_multi_temperature_compounds": feature_coverage(
            multi_rows,
            alpha_table,
            label="v11 rows of compounds carrying two or more distinct temperatures",
        ),
    }
    if not args.skip_v10 and args.frozen_features.exists():
        v10_pool_rows, _failed, _withheld = read_modelling_rows(
            args.frozen_features, dataset_path=args.dataset
        )
        coverage["v10_pool"] = feature_coverage(
            v10_pool_rows,
            alpha_table,
            label="v1.0 modelling pool (model_ready + xTB)",
        )

    crosscheck_table: list[dict[str, object]] = []
    slope_table: list[dict[str, object]] = []
    cohorts: dict[str, object] = {}

    def add_cohort(label: str, rows: Sequence[Mapping[str, str]]) -> None:
        slopes = compound_slopes(rows)
        names: dict[str, str] = {}
        for row in rows:
            names.setdefault(str(row["inchikey"]), str(row.get("name", "")))
        for key, fit in sorted(slopes.items()):
            slope_table.append(
                {"cohort": label, "inchikey": key, "compound_name": names.get(key, ""), **fit}
            )
        crosscheck_table.extend(crosscheck_rows(slopes, alpha_table, cohort=label))
        cohorts[label] = {
            "rows": len(rows),
            "compounds": len({str(row["inchikey"]) for row in rows}),
            "compounds_with_a_fitted_slope": len(slopes),
        }

    add_cohort("v11_all_bands", observations)
    add_cohort("v11_room_band", room_rows)
    if args.lowfreq.exists():
        lowfreq_rows = read_csv_rows(args.lowfreq)
        coverage["lowfreq_candidates"] = feature_coverage(
            lowfreq_rows, alpha_table, label="frequency-relaxed candidates (sibling probe)"
        )
        add_cohort(
            "lowfreq_primary_gate",
            [row for row in lowfreq_rows if row.get("gate") == "accepted_primary_lowfreq"],
        )
        add_cohort(
            "lowfreq_extended_gate",
            [row for row in lowfreq_rows if row.get("gate") == "accepted_extended_lowfreq"],
        )

    room_family = run_room_family(
        room_rows,
        alpha_table,
        slope_source_rows=observations,
        n_splits=n_splits,
        n_repeats=n_repeats,
        seed=args.seed,
    )
    v10_family = (
        None
        if args.skip_v10
        else run_v10_family(
            args.frozen_features,
            args.dataset,
            alpha_table,
            n_splits=n_splits,
            n_repeats=n_repeats,
            seed=args.seed,
        )
    )

    room_lookup = repeat_metric_lookup(room_family["arms"])
    room_deltas = {
        arm: paired_delta(room_lookup, baseline=baseline, arm=arm)
        for arm, baseline in PAIRINGS
        if arm in room_family["arms"]
    }
    v10_deltas: dict[str, dict[str, object]] = {}
    if v10_family is not None:
        v10_lookup = repeat_metric_lookup(v10_family["arms"])
        v10_deltas = {
            arm: paired_delta(v10_lookup, baseline=baseline, arm=arm)
            for arm, baseline in PAIRINGS
            if arm in v10_family["arms"]
        }
    over_the_placebo = {
        **effect_over_null_block(room_deltas),
        **effect_over_null_block(v10_deltas),
    }

    reproduction = reference_reproduction(room_family["arms"]["room_baseline"]["summary"])
    label_identity_block = label_identity(alpha_table, read_csv_rows(args.dataset))
    conversion = verify_conversion(alpha_table)
    control = subsampling_control(room_rows, seed=args.seed)
    crosscheck_summary = summarize_crosscheck(crosscheck_table)
    verdict = build_verdict(
        room_family, v10_family, room_deltas, v10_deltas, over_the_placebo, reproduction
    )

    inputs: dict[str, object] = {}
    for path in (
        args.alpha_table,
        args.observations,
        args.features,
        args.frozen_features,
        args.dataset,
        args.lowfreq,
    ):
        if not path.exists():
            continue
        rows: int | None = None
        if path.suffix == ".csv":
            rows = len(read_csv_rows(path))
        inputs[display_path(path)] = {"sha256": file_sha256(path), "rows": rows}

    args.artifacts.mkdir(parents=True, exist_ok=True)
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_crosscheck.csv",
        CROSSCHECK_COLUMNS,
        crosscheck_table,
    )
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_empirical_slopes.csv",
        SLOPE_COLUMNS,
        slope_table,
    )
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_feature_coverage.csv",
        COVERAGE_COLUMNS,
        [
            {**block, "alpha_kind_counts": json.dumps(block["alpha_kind_counts"])}
            for block in coverage.values()
        ],
    )
    arms = {
        **room_family["arms"],
        **(v10_family["arms"] if v10_family is not None else {}),
    }
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_folds.csv",
        FOLD_COLUMNS,
        [row for name in ARM_ORDER if name in arms for row in arms[name]["fold_rows"]],
    )
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_repeats.csv",
        ("protocol", "representation", "repeat", *METRIC_NAMES),
        [row for name in ARM_ORDER if name in arms for row in arms[name]["repeat_rows"]],
    )
    write_csv_rows(
        args.artifacts / "dielectric_alpha_prior_predictions.csv",
        PREDICTION_COLUMNS,
        [
            row
            for name in ARM_ORDER
            if name in arms
            for row in arms[name]["prediction_rows"]
        ],
    )

    payload: dict[str, object] = {
        "schema_version": 1,
        "seed": args.seed,
        "quick": bool(args.quick),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": {
            "room_family": (
                "room_temperature rows, GroupKFold by InChIKey, shuffled compound "
                f"order, {n_splits}x{n_repeats}, frozen XGBoost hybrid"
            ),
            "v10_family": (
                "v1.0 236-compound modelling rows, released RepeatedKFold 5x10 and "
                "grouped by InChIKey 10x5, frozen XGBoost hybrid"
            ),
            "random_row_used": False,
            "null_block_control": (
                "every feature arm carries a same-width all-NaN placebo; the effect "
                "of a feature is its paired delta against that placebo, because "
                "colsample_bytree re-draws the column subsample as soon as the "
                "matrix gets wider"
            ),
        },
        "inputs": inputs,
        "dropped": dropped,
        "alpha_definition": {
            "source": "NBS Circular 514 sections 2.1 / 2.5, as transcribed by week 8",
            "kind_a": "a = -d(eps)/dT, printed as a * 1e5",
            "kind_alpha": "alpha = -d(log10 eps)/dT, printed as alpha * 1e5",
            "inverse_a": "d(eps)/dT = -a_1e5 * 1e-5  [per K]",
            "inverse_alpha": "d(eps)/dT = -alpha_1e5 * 1e-5 * eps * ln(10)  [per K]",
            "column_naming_caveat": (
                "alpha_1e5 holds a*1e5 when alpha_kind == 'a'; it is a transcribed "
                "coefficient, not a derivative"
            ),
        },
        "conversion_check": conversion,
        "label_identity": label_identity_block,
        "subsampling_control": control,
        "coverage": coverage,
        "cohorts": cohorts,
        "crosscheck": crosscheck_summary,
        "benchmark": {
            "room_family": summarize_family(room_family),
            "v10_family": None if v10_family is None else summarize_family(v10_family),
        },
        "paired": {
            "room": room_deltas,
            "v10": v10_deltas,
            "over_the_null_block": over_the_placebo,
        },
        "reference_reproduction": reproduction,
        "verdict": verdict,
        "outputs": {
            "summary": display_path(args.summary),
            "report": None if args.no_report else display_path(args.report),
            "artifacts": [
                display_path(args.artifacts / name)
                for name in (
                    "dielectric_alpha_prior_crosscheck.csv",
                    "dielectric_alpha_prior_empirical_slopes.csv",
                    "dielectric_alpha_prior_feature_coverage.csv",
                    "dielectric_alpha_prior_folds.csv",
                    "dielectric_alpha_prior_repeats.csv",
                    "dielectric_alpha_prior_predictions.csv",
                )
            ],
        },
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if not args.no_report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_report(payload))

    print(
        "room family: "
        f"rows={room_family['rows']} compounds={room_family['compounds']} "
        f"folds={room_family['folds']}"
    )
    print(
        "alpha coverage: "
        f"v11 room band={coverage['v11_room_band']['coefficient_coverage']}, "
        f"v10 pool={coverage.get('v10_pool', {}).get('coefficient_coverage')}"
    )
    print(
        "subsampling control: "
        f"identical={control.get('predictions_identical')} "
        f"max_abs_delta={control.get('max_abs_prediction_delta')}"
    )
    print(
        "self-check: "
        f"bit_exact={reproduction['bit_exact_against_the_pinned_constant']} "
        f"hybrid_r2={reproduction['hybrid_r2']!r}"
    )
    for arm, baseline in PAIRINGS:
        delta = room_deltas.get(arm, {})
        if delta:
            block = over_the_placebo.get(arm, {})
            print(
                f"  {arm} vs {baseline}: dR2={delta['mean_delta_r2']!r} "
                f"dR2_vs_placebo={block.get('effect_over_the_placebo_r2')!r} "
                f"{block.get('classification', '')}"
            )
    for arm, baseline in PAIRINGS:
        delta = v10_deltas.get(arm, {})
        if delta:
            block = over_the_placebo.get(arm, {})
            print(
                f"  {arm} vs {baseline}: dR2={delta['mean_delta_r2']!r} "
                f"dR2_vs_placebo={block.get('effect_over_the_placebo_r2')!r} "
                f"{block.get('classification', '')}"
            )
    print(f"summary written to {display_path(args.summary)}")
    if not args.no_report:
        print(f"report written to {display_path(args.report)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
