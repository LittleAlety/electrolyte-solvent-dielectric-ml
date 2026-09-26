"""S-5 placebo arms: is the Week 11 coverage gain observation-level information?

Week 11 produced exactly one number for the v1.x line and could not attribute it.
With the scored rows, the folds and the denominators held fixed, widening the
training pool from the 457 room rows of the 97 v11 compounds to also carry the 127
room rows of the 50 frequency-gate compounds moved the grouped Hybrid R2 from
0.4091179943351143 to 0.5332044440328436 - a paired
dR2 = +0.1240864496977293. Two causes survive that measurement:

* the added rows carry *observation-level information* - a new compound's own
  temperature series and its physical/xTB vector - and the trees transfer it to the
  scored compounds;
* the added rows are only *more data*: 127 extra fitting rows and the regularisation
  that comes with them, which any 127 rows would have supplied.

The S-5 pre-registration of the local manual separates the two with a three-arm
placebo. Every arm keeps the Week 11 contract bit for bit - the same scored 457 rows
of the same 97 compounds, the same folds, the same denominators, the same row
counts, the same representation and the same regularisation - and moves exactly one
thing:

    arm A  label placebo   the epsilons of the 50 added compounds are permuted
                           *between compounds*. Row count, composition and
                           regularisation are untouched, so only the
                           label-to-compound association is destroyed.
                           Criterion: the paired dR2 collapses to <= +0.02.
    arm B  dose curve      the added compounds enter at 25 / 50 / 75 / 100 %, and
                           the subsample is drawn at the *compound* level so a
                           compound is wholly in or wholly out.
                           Criterion: the paired dR2 rises monotonically.
    arm C  mean-row only   each added compound keeps only its mean row - one row
                           carrying the compound's own xTB vector at its mean T_K
                           and its mean epsilon. The compound count survives (50)
                           and the temperature resolution does not.
                           Criterion: the gain falls below the full arm, which is
                           what makes the resolution rather than the count the
                           carrier.

The gain may be called information-driven only when arm A collapses *and* arm B
rises monotonically. If either fails, the number is a data-volume artefact and this
report says so, in the pre-registered words.

The probe reuses the Week 11 pipeline instead of re-deriving it:
`merge_feature_blocks` and `load_coverage_table` load and gate the table,
`run_coverage_protocol` and `run_protocol_family` deal and run the folds, and
`scored_fold_signature`, `paired_delta`, `splitter_contract`,
`training_expansion` and `write_artifacts` do the accounting. No split is invented
here: every arm scores the same 457 rows, and `masked_splits` deals folds over the
scored mask alone, so every arm inherits `paired_base`'s fold assignment. The probe
proves that instead of assuming it, by comparing the scored-side fold signature of
every protocol it runs.

The four fixed-pool Week 11 protocols are re-run inside this process first, so the
published +0.1241 has to reappear (with its +0.1363 / +0.0211 split) before any arm
is read.

Read-only with respect to every released artefact: `data/dielectric_v03.csv` keeps
its pinned digest and `paper/` is not touched. The outputs are
`probes/dielectric_coverage_placebo_arms_summary.json`,
`reports/dielectric_coverage_placebo_arms.md` and the three
`probes/artifacts/dielectric_coverage_placebo_arms_*.csv` tables. Without
`--overwrite` an existing output is left alone. No network I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coverage_paired_benchmark as week_eleven
import numpy as np
from dielectric_band_ablation import ROOM_BAND
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    SEED,
    XGB_PARAMS,
)
from dielectric_room_window_paired import (
    HYBRID,
    paired_delta,
    scored_fold_signature,
)

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coverage_placebo_arms_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_coverage_placebo_arms.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_coverage_placebo_arms"

WEEK_ELEVEN_SUMMARY_PATH = week_eleven.SUMMARY_PATH
FROZEN_TABLE_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
#: The frozen v0.3 digest. This probe only reads the table, and it re-reads the
#: digest so a stray write anywhere in the run is visible rather than assumed away.
FROZEN_TABLE_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"

#: The Week 11 numbers this probe has to reproduce before any arm may be read.
PAIRED_BASE_R2 = 0.4091179943351143
PAIRED_PLUS_COVERAGE_R2 = 0.5332044440328436
PAIRED_DELTA_R2 = 0.1240864496977293
PAIRED_SCORED_ROWS = 457
PAIRED_SCORED_COMPOUNDS = 97
ADDED_COMPOUNDS = 50
ADDED_ROOM_ROWS = 127
ADDED_EXTRA_ROWS_PER_FOLD = 127.0

#: S-5 arm A: the placebo passes when the paired dR2 collapses to at most this.
ARM_A_TOLERANCE = 0.02

BASE_PROTOCOL = "paired_base"
FULL_ARM_PROTOCOL = "paired_plus_coverage"
ARM_A_PROTOCOL = "arm_a_label_placebo"
ARM_A_REFERENCE_PROTOCOL = "arm_a_reference_base"
ARM_C_PROTOCOL = "arm_c_mean_row_only"
ARM_C_REAL_ROW_PROTOCOL = "arm_c_nearest_real_row"

#: The four fixed-pool protocols of Week 11, re-run here as the reproduction gate.
#: Their presence is also what lets `splitter_contract` and `training_expansion`
#: be reused verbatim, because those two read a hard-coded name list.
WEEK_ELEVEN_PROTOCOLS = (
    "paired_base",
    "paired_plus_coverage",
    "paired_plus_new_xtb",
    "paired_plus_v03_block",
)

#: Arm B records. The 100 % record *is* the full arm: its training mask is identical
#: by construction, which the probe proves with an array equality check instead of
#: re-running the same fits under a second name.
DOSE_RUN_PERCENTS = (25, 50, 75)
DOSE_CURVE_PERCENTS = (25, 50, 75, 100)

#: Fixed seeds. The fold seed is Week 11's, because the arms have to share its
#: folds; the placebo and dose seeds are pinned and recorded so both arms reproduce.
FOLD_SEED = SEED
PLACEBO_SEED = 20260926
DOSE_SEED = 20260927


def dose_protocol(percent: int) -> str:
    """The protocol name of one arm B dose."""

    return f"arm_b_dose_{percent:02d}"


DOSE_PROTOCOL_NAMES = tuple(dose_protocol(percent) for percent in DOSE_RUN_PERCENTS)

FAMILY_ONE_PROTOCOLS = (
    *WEEK_ELEVEN_PROTOCOLS,
    *DOSE_PROTOCOL_NAMES,
    ARM_C_PROTOCOL,
    ARM_C_REAL_ROW_PROTOCOL,
)
FAMILY_TWO_PROTOCOLS = (ARM_A_REFERENCE_PROTOCOL, ARM_A_PROTOCOL)

ARM_DESCRIPTIONS = {
    ARM_A_REFERENCE_PROTOCOL: (
        "the Week 11 base re-run on the permuted target, to prove the placebo moved only "
        "rows that paired_base can neither score nor fit"
    ),
    ARM_A_PROTOCOL: (
        "S-5 arm A: train on the same 127 added room rows with their epsilons permuted between "
        "the added compounds; scored rows, folds, row counts and regularisation unchanged"
    ),
    ARM_C_PROTOCOL: (
        "S-5 arm C: each added compound contributes one mean row - its own xTB vector at its "
        "mean T_K and its mean epsilon - so the compound count survives and the T resolution "
        "does not"
    ),
    ARM_C_REAL_ROW_PROTOCOL: (
        "S-5 arm C, second reading: each added compound keeps only the existing room row closest "
        "to its own mean epsilon, one real row per compound instead of a synthesised mean row"
    ),
    **{
        dose_protocol(percent): (
            f"S-5 arm B at {percent}% of the 50 added compounds, drawn at the compound level so "
            "a compound is wholly in or wholly out"
        )
        for percent in DOSE_RUN_PERCENTS
    },
}


def protocol_description(protocol: str) -> str:
    """The description of any protocol this probe runs."""

    if protocol in ARM_DESCRIPTIONS:
        return ARM_DESCRIPTIONS[protocol]
    return week_eleven.PROTOCOL_DESCRIPTIONS[protocol]


def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the verdict."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


@contextmanager
def arm_descriptions() -> Iterator[None]:
    """Register this probe's protocol names with the Week 11 runner, reversibly.

    `run_coverage_protocol` looks its description up in the Week 11 module's
    `PROTOCOL_DESCRIPTIONS`, so an arm needs a name that dict knows. The names are
    added for the duration of the run and removed afterwards, so importing both
    modules into one process cannot leak this probe's names into Week 11's table.
    """

    added = {
        name: text
        for name, text in ARM_DESCRIPTIONS.items()
        if name not in week_eleven.PROTOCOL_DESCRIPTIONS
    }
    week_eleven.PROTOCOL_DESCRIPTIONS.update(added)
    try:
        yield
    finally:
        for name in added:
            del week_eleven.PROTOCOL_DESCRIPTIONS[name]


def frozen_table_digest(
    path: Path = FROZEN_TABLE_PATH,
    expected: str = FROZEN_TABLE_SHA256,
) -> dict[str, object]:
    """Re-read the frozen v0.3 digest, which this probe must not have moved."""

    if not path.is_file():
        return {
            "path": portable_relative_path(path, root=REPOSITORY_ROOT),
            "status": "not read",
            "reason": "the frozen v0.3 table is absent from this checkout",
            "expected": expected,
            "matches_literal": None,
        }
    payload = path.read_bytes()
    raw = hashlib.sha256(payload).hexdigest()
    return {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "status": "read",
        "sha256": raw,
        "sha256_lf_canonical": canonical_text_sha256(path),
        "crlf_present": b"\r\n" in payload,
        "expected": expected,
        "matches_literal": raw == expected,
    }


def week_eleven_reference(path: Path = WEEK_ELEVEN_SUMMARY_PATH) -> dict[str, object]:
    """The numbers Week 11 published, read back rather than remembered."""

    entry: dict[str, object] = {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "status": "read",
        "paired_base_hybrid_r2": None,
        "paired_plus_coverage_hybrid_r2": None,
        "paired_delta_r2": None,
        "chain": {},
    }
    if not path.is_file():
        entry["status"] = "not read"
        entry["reason"] = "the Week 11 summary is absent from this checkout"
        return entry
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        family = payload["fixed_pool_family"]
        summary = family["summary"]
        entry["paired_base_hybrid_r2"] = float(summary[BASE_PROTOCOL][HYBRID]["r2"]["mean"])
        entry["paired_plus_coverage_hybrid_r2"] = float(
            summary[FULL_ARM_PROTOCOL][HYBRID]["r2"]["mean"]
        )
        entry["chain"] = {
            str(step["widened"]): float(step["delta_r2"]) for step in family["chain"]
        }
        entry["extra_rows_fitted_per_fold_mean"] = float(
            family["training_expansion"][FULL_ARM_PROTOCOL]["extra_rows_fitted_per_fold_mean"]
        )
    except (KeyError, TypeError, ValueError) as error:
        entry["status"] = "not read"
        entry["reason"] = f"the Week 11 summary has no readable fixed-pool block ({error})"
        return entry
    entry["paired_delta_r2"] = float(entry["paired_plus_coverage_hybrid_r2"]) - float(
        entry["paired_base_hybrid_r2"]
    )
    return entry


def pinned_reproduction(
    *,
    paired_base_r2: float,
    paired_plus_coverage_r2: float,
    repeats: int,
    expected_repeats: int = N_REPEATS,
) -> dict[str, object]:
    """Diff the re-run Week 11 numbers against the pinned literals.

    The Week 11 means are means over ten repeats, so a run with fewer repeats cannot
    reproduce them. That case is recorded as not applicable *with its reason* rather
    than as a pass or a failure, and the caller has to declare the reduced repeat
    count as a degradation in the report.
    """

    delta = float(paired_plus_coverage_r2) - float(paired_base_r2)
    entry: dict[str, object] = {
        "paired_base_hybrid_r2": float(paired_base_r2),
        "paired_plus_coverage_hybrid_r2": float(paired_plus_coverage_r2),
        "delta_r2": delta,
        "expected_paired_base_hybrid_r2": PAIRED_BASE_R2,
        "expected_paired_plus_coverage_hybrid_r2": PAIRED_PLUS_COVERAGE_R2,
        "expected_delta_r2": PAIRED_DELTA_R2,
        "repeats": int(repeats),
        "expected_repeats": int(expected_repeats),
        "applicable": int(repeats) == int(expected_repeats),
    }
    entry["paired_base_abs_delta"] = abs(float(paired_base_r2) - PAIRED_BASE_R2)
    entry["paired_plus_coverage_abs_delta"] = abs(
        float(paired_plus_coverage_r2) - PAIRED_PLUS_COVERAGE_R2
    )
    entry["delta_abs_delta"] = abs(delta - PAIRED_DELTA_R2)
    if not entry["applicable"]:
        entry["bit_exact"] = None
        entry["reason"] = (
            f"not read: the Week 11 means are {expected_repeats}-repeat means while this run "
            f"executed {repeats} repeat(s)"
        )
        return entry
    entry["bit_exact"] = bool(
        float(paired_base_r2) == PAIRED_BASE_R2
        and float(paired_plus_coverage_r2) == PAIRED_PLUS_COVERAGE_R2
        and delta == PAIRED_DELTA_R2
    )
    return entry


# --------------------------------------------------------------------------- #
# arm A: the label placebo
# --------------------------------------------------------------------------- #


def permute_added_compound_labels(
    keys: Sequence[str],
    target: np.ndarray,
    *,
    added_mask: Sequence[bool],
    seed: int,
) -> tuple[np.ndarray, dict[str, object]]:
    """Move the epsilons of the added compounds onto other added compounds.

    The added rows are grouped by compound and laid out in sorted-key order. A random
    permutation of the compound keys then re-reads those blocks as one donor stream
    and pours it back into the destination blocks in their canonical order. What
    comes out is a permutation *of the added rows*: the row count, every feature
    vector, every T_K and the multiset of epsilons are exactly what they were, and
    nothing outside the added block moves. Only the association between a compound
    and its own epsilons is destroyed.

    Unequal block lengths are why the labels move as a stream rather than as a
    block-for-block swap: a destination compound smaller than its donor stops
    mid-block, and the rest of that donor spills onto the next destination. That is
    what makes the movement genuinely between compounds instead of a relabelling of
    identical shapes.
    """

    added = np.flatnonzero(np.asarray(added_mask, dtype=bool))
    values = np.asarray(target, dtype=float)
    permuted = np.array(values, dtype=float, copy=True)
    report: dict[str, object] = {
        "seed": int(seed),
        "added_rows": int(added.size),
        "added_compounds": 0,
        "compounds_with_a_changed_label_multiset": 0,
        "compounds_receiving_a_foreign_label": 0,
        "labels_changed": 0,
        "label_change_fraction": 0.0,
        "rows_receiving_a_foreign_label": 0,
        "label_multiset_preserved": None,
        "labels_untouched_outside_the_added_block": None,
        "donor_compounds_per_destination": {},
    }
    if added.size == 0:
        report["note"] = "no added rows: the placebo is the identity"
        return permuted, report

    key_array = np.asarray([str(key) for key in keys])
    blocks: dict[str, list[int]] = defaultdict(list)
    for index in added:
        blocks[key_array[index]].append(int(index))
    names = sorted(blocks)
    report["added_compounds"] = len(names)
    if len(names) < 2:
        report["note"] = "one added compound cannot be permuted between compounds"
        return permuted, report

    order = np.random.default_rng(int(seed)).permutation(len(names))
    donor_stream = [
        (int(donor), float(values[index]))
        for donor in order
        for index in blocks[names[int(donor)]]
    ]
    donors_per_destination: dict[str, list[str]] = {}
    changed_multiset = 0
    foreign_compounds = 0
    foreign_rows = 0
    cursor = 0
    for position, name in enumerate(names):
        rows = blocks[name]
        stream = donor_stream[cursor : cursor + len(rows)]
        cursor += len(rows)
        permuted[rows] = [value for _donor, value in stream]
        donors = sorted({donor for donor, _value in stream})
        donors_per_destination[name] = [names[donor] for donor in donors]
        if sorted(float(value) for value in values[rows]) != sorted(
            float(value) for value in permuted[rows]
        ):
            changed_multiset += 1
        if donors != [position]:
            foreign_compounds += 1
            foreign_rows += sum(1 for donor, _value in stream if donor != position)

    outside = ~np.asarray(added_mask, dtype=bool)
    report["donor_compounds_per_destination"] = donors_per_destination
    report["compounds_with_a_changed_label_multiset"] = changed_multiset
    report["compounds_receiving_a_foreign_label"] = foreign_compounds
    report["rows_receiving_a_foreign_label"] = int(foreign_rows)
    report["labels_changed"] = int(np.count_nonzero(permuted[added] != values[added]))
    report["label_change_fraction"] = float(report["labels_changed"] / int(added.size))
    report["label_multiset_preserved"] = bool(
        sorted(permuted[added].tolist()) == sorted(values[added].tolist())
    )
    report["labels_untouched_outside_the_added_block"] = bool(
        np.array_equal(permuted[outside], values[outside])
    )
    return permuted, report


# --------------------------------------------------------------------------- #
# arm B: the dose curve
# --------------------------------------------------------------------------- #


def dose_compound_order(compound_keys: Sequence[str], *, seed: int) -> list[str]:
    """One random compound order, so every dose is a prefix and the doses nest.

    The order is drawn once and every dose takes a prefix of it. The levels therefore
    nest - 25 % is a subset of 50 % - which is what lets a step in the curve be read
    as a step in *added information* rather than as a reshuffle of which compounds
    happen to be present.
    """

    unique = np.asarray(sorted({str(key) for key in compound_keys}))
    if unique.size == 0:
        raise ValueError("no compounds to dose")
    return [str(key) for key in np.random.default_rng(int(seed)).permutation(unique)]


def dose_compounds(order: Sequence[str], percent: int) -> list[str]:
    """The first ceil(percent/100 * n) compounds of the shared order, key-sorted."""

    if not 0 < int(percent) <= 100:
        raise ValueError(f"dose percent out of range: {percent}")
    count = max(1, -(-int(percent) * len(order) // 100))
    return sorted(str(key) for key in list(order)[:count])


def dose_curve_report(
    points: Sequence[Mapping[str, object]],
    *,
    tolerance: float = 1e-12,
) -> dict[str, object]:
    """Judge the S-5 dose curve from one paired delta per dose.

    `points` is ordered by dose and every entry needs `percent` and `delta_r2`.
    "Monotone" is the pre-registration's 单调递增 read strictly - every step has to be
    positive - and `non_decreasing` is reported beside it with a float tolerance, so
    that a numeric tie can be told apart from a real reversal.
    """

    percents = [int(point["percent"]) for point in points]
    deltas = [float(point["delta_r2"]) for point in points]
    if len(deltas) < 2:
        return {
            "percents": percents,
            "delta_r2": deltas,
            "steps": [],
            "monotone": False,
            "non_decreasing": False,
            "span": None,
            "tolerance": float(tolerance),
            "reason": "a dose curve needs at least two doses",
        }
    steps = [deltas[index + 1] - deltas[index] for index in range(len(deltas) - 1)]
    return {
        "percents": percents,
        "delta_r2": deltas,
        "steps": steps,
        "step_between": [
            [percents[index], percents[index + 1]] for index in range(len(steps))
        ],
        "monotone": all(step > tolerance for step in steps),
        "non_decreasing": all(step >= -tolerance for step in steps),
        "span": deltas[-1] - deltas[0],
        "tolerance": float(tolerance),
        "note": (
            "monotone reads 单调递增 strictly (every step positive); non_decreasing is "
            "the same curve with a float tolerance and is reported beside it"
        ),
    }


# --------------------------------------------------------------------------- #
# arm C: the mean row
# --------------------------------------------------------------------------- #


def mean_row_selection(
    keys: Sequence[str],
    target: np.ndarray,
    temperatures: Sequence[float],
    *,
    candidate_mask: Sequence[bool],
) -> tuple[np.ndarray, dict[str, object]]:
    """Keep, per compound, the one existing row whose epsilon is nearest its mean.

    This is the second reading of S-5 arm C: instead of synthesising a mean row it
    selects a real one, so the arm cannot be accused of inventing a row. An exact tie
    goes to the smallest row index.
    """

    mask = np.asarray(candidate_mask, dtype=bool)
    values = np.asarray(target, dtype=float)
    key_array = np.asarray([str(key) for key in keys])
    blocks: dict[str, list[int]] = defaultdict(list)
    for index in np.flatnonzero(mask):
        blocks[key_array[index]].append(int(index))
    keep = np.zeros(values.size, dtype=bool)
    per_compound: dict[str, dict[str, object]] = {}
    for name in sorted(blocks):
        rows = blocks[name]
        compound_values = np.asarray([values[index] for index in rows], dtype=float)
        reference = float(compound_values.mean())
        distances = np.abs(compound_values - reference)
        chosen = rows[int(np.argmin(distances))]
        keep[chosen] = True
        per_compound[name] = {
            "candidate_rows": len(rows),
            "mean_epsilon": reference,
            "kept_row": int(chosen),
            "kept_epsilon": float(values[chosen]),
            "kept_T_K": float(temperatures[chosen]),
            "max_abs_distance_to_the_mean": float(distances.max()),
        }
    return keep, {
        "selection_rule": "the real room row whose epsilon is closest to the compound's mean",
        "tie_break": "smallest row index wins an exact tie (argmin over an index-ordered block)",
        "compounds": len(blocks),
        "candidate_rows": int(mask.sum()),
        "kept_rows": int(keep.sum()),
        "rows_dropped": int(mask.sum()) - int(keep.sum()),
        "per_compound": per_compound,
    }


def mean_row_augmentation(
    keys: Sequence[str],
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    *,
    added_mask: Sequence[bool],
    room_mask: Sequence[bool],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str], dict[str, object]]:
    """Append one mean row per added compound to the feature and target blocks.

    A compound's mean row carries the compound's own Morgan fingerprint and xTB
    vector, its mean T_K in the T_K column, and its mean epsilon as the target. It is
    appended *after* the observation rows, so not one existing row index moves: every
    mask, fold and prediction of every other arm keeps its meaning.

    The row is only a mean row because the physical block is constant within a
    compound apart from T_K. That is checked here instead of assumed - if a compound's
    rows disagreed on a feature, its mean row would be an invention.
    """

    added = np.asarray(added_mask, dtype=bool) & np.asarray(room_mask, dtype=bool)
    values = np.asarray(target, dtype=float)
    temperature_values = np.asarray([float(value) for value in temperatures], dtype=float)
    columns = list(PHYSICAL_COLUMNS)
    if "T_K" not in columns:
        raise ValueError("the physical block has no T_K column to average")
    t_index = columns.index("T_K")
    other_columns = [column for column in range(physical.shape[1]) if column != t_index]
    key_array = np.asarray([str(key) for key in keys])
    blocks: dict[str, list[int]] = defaultdict(list)
    for index in np.flatnonzero(added):
        blocks[key_array[index]].append(int(index))

    morgan_rows: list[np.ndarray] = []
    physical_rows: list[np.ndarray] = []
    target_rows: list[float] = []
    temperature_rows: list[float] = []
    synthetic_keys: list[str] = []
    per_compound: dict[str, dict[str, object]] = {}
    for name in sorted(blocks):
        rows = blocks[name]
        block = physical[np.ix_(rows, other_columns)]
        vector = physical[rows[0]].astype(float, copy=True)
        mean_temperature = float(temperature_values[rows].mean())
        mean_epsilon = float(values[rows].mean())
        vector[t_index] = mean_temperature
        morgan_rows.append(morgan[rows[0]].astype(morgan.dtype, copy=True))
        physical_rows.append(vector)
        target_rows.append(mean_epsilon)
        temperature_rows.append(mean_temperature)
        synthetic_keys.append(name)
        per_compound[name] = {
            "rows": len(rows),
            "source_row": int(rows[0]),
            "mean_T_K": mean_temperature,
            "mean_epsilon": mean_epsilon,
            "physical_block_constant_within_the_compound": bool(np.all(block == block[0])),
        }

    report: dict[str, object] = {
        "compounds": len(synthetic_keys),
        "synthetic_rows": len(synthetic_keys),
        "row_index_start": int(values.size),
        "row_index_stop": int(values.size) + len(synthetic_keys),
        "physical_block_constant_within_every_compound": all(
            bool(item["physical_block_constant_within_the_compound"])
            for item in per_compound.values()
        ),
        "device": "the mean row is appended after the observation rows, so no index moves",
        "per_compound": per_compound,
    }
    if not synthetic_keys:
        return morgan, physical, values, temperature_values, [str(key) for key in keys], report
    return (
        np.vstack([morgan, np.vstack(morgan_rows)]),
        np.vstack([physical, np.vstack(physical_rows)]),
        np.concatenate([values, np.asarray(target_rows, dtype=float)]),
        np.concatenate([temperature_values, np.asarray(temperature_rows, dtype=float)]),
        [str(key) for key in keys] + synthetic_keys,
        report,
    )


# --------------------------------------------------------------------------- #
# the shared contract, the expansion and the judgement
# --------------------------------------------------------------------------- #


def arm_training_expansion(
    protocols: Sequence[str],
    masks: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
    *,
    splits_by_protocol: Mapping[str, Sequence[tuple[int, int, np.ndarray, np.ndarray]]],
    base: str = BASE_PROTOCOL,
) -> dict[str, object]:
    """How much training material each arm really adds, fold by fold.

    `rows_added_over_base` is the pool-level widening. `extra_rows_fitted_per_fold_mean`
    is counted from the folds that were actually run, so it cannot disagree with the
    benchmark: the two differ exactly when the added rows belong to compounds outside
    the scored pool, because those carry no fold and every fold may fit all of them.
    """

    base_train = np.asarray(masks[base][1], dtype=bool)
    base_splits = splits_by_protocol[base]
    if not base_splits:
        raise ValueError(f"{base} produced no folds to measure the arms against")
    table: dict[str, object] = {}
    for protocol in protocols:
        train_mask = np.asarray(masks[protocol][1], dtype=bool)
        splits = splits_by_protocol[protocol]
        extras: list[int] = []
        for base_split, split in zip(base_splits, splits, strict=False):
            if (int(split[0]), int(split[1])) != (int(base_split[0]), int(base_split[1])):
                raise ValueError(f"{protocol}: fold order does not match {base}")
            extras.append(int(split[2].size - base_split[2].size))
        table[protocol] = {
            "train_pool_rows": int(train_mask.sum()),
            "rows_added_over_base": int(train_mask.sum() - base_train.sum()),
            "folds_compared": len(extras),
            "extra_rows_fitted_per_fold_mean": float(np.mean(extras)) if extras else 0.0,
            "extra_rows_fitted_per_fold_min": int(min(extras)) if extras else 0,
            "extra_rows_fitted_per_fold_max": int(max(extras)) if extras else 0,
            "extra_rows_fitted_total": int(sum(extras)),
        }
    return table


def fold_contract(
    protocols: Mapping[str, Mapping[str, object]],
    splits_by_protocol: Mapping[str, Sequence[tuple[int, int, np.ndarray, np.ndarray]]],
) -> dict[str, object]:
    """Re-derive the shared-scored-row contract for the arms this probe adds.

    `week_eleven.splitter_contract` reads a hard-coded list of the four fixed-pool
    names, so it is called here on the block those four names still describe, and the
    same invariants are then re-checked over every arm. The scored-side fold signature
    - the scored rows of every fold, repeat by repeat - is compared across all of
    them, and that is the property the whole probe rests on.
    """

    signatures = {
        name: scored_fold_signature(splits)
        for name, splits in splits_by_protocol.items()
        if splits
    }
    shared = len(signatures) == len(splits_by_protocol) and len(set(signatures.values())) == 1
    contract = week_eleven.splitter_contract(
        {"protocols": protocols, "folds_are_shared": shared}
    )
    contract["scored_fold_signatures_identical"] = bool(shared)
    contract["protocols_with_a_signature"] = len(signatures)
    contract["arms_scored_rows"] = sorted(
        {int(protocols[name]["scored_rows"]) for name in protocols}
    )
    contract["arms_compounds_scored"] = sorted(
        {int(protocols[name]["compounds_scored"]) for name in protocols}
    )
    contract["arms_fold_counts"] = sorted({int(protocols[name]["folds"]) for name in protocols})
    contract["arms_scored_rows_identical"] = len(contract["arms_scored_rows"]) == 1
    contract["arms_compounds_scored_identical"] = len(contract["arms_compounds_scored"]) == 1
    contract["arms_fold_counts_identical"] = len(contract["arms_fold_counts"]) == 1
    contract["basis"] = "the scored rows of every fold, repeat by repeat"
    return contract


def build_criteria(
    *,
    integrity_ok: bool,
    arm_a_delta_r2: float | None,
    dose_curve: Mapping[str, object],
    arm_c_delta_r2: float | None,
    full_arm_delta_r2: float | None,
) -> dict[str, object]:
    """The S-5 pass/fail booleans, as literal readings of the pre-registration."""

    arm_a = None if arm_a_delta_r2 is None else bool(float(arm_a_delta_r2) <= ARM_A_TOLERANCE)
    arm_c = None
    if arm_c_delta_r2 is not None and full_arm_delta_r2 is not None:
        arm_c = bool(float(arm_c_delta_r2) < float(full_arm_delta_r2))
    return {
        "arm_a_placebo_collapse": arm_a,
        "arm_a_threshold": ARM_A_TOLERANCE,
        "arm_b_dose_monotone": bool(dose_curve.get("monotone")),
        "arm_b_non_decreasing": bool(dose_curve.get("non_decreasing")),
        "arm_c_below_the_full_arm": arm_c,
        "integrity_ok": bool(integrity_ok),
        "statement": (
            "arm A passes when its paired dR2 is at most +0.02; arm B passes when the "
            "25/50/75/100 % curve rises monotonically (every step positive); arm C is a "
            "mechanism cross-check and does not enter the pre-registered headline"
        ),
    }


def verification_passed(criteria: Mapping[str, object]) -> bool:
    """Every criterion, including the integrity gate, has to hold."""

    return all(
        bool(criteria.get(key))
        for key in (
            "arm_a_placebo_collapse",
            "arm_b_dose_monotone",
            "arm_c_below_the_full_arm",
            "integrity_ok",
        )
    )


def build_verdict(
    criteria: Mapping[str, object],
    *,
    arm_a_delta_r2: float | None,
    full_arm_delta_r2: float | None,
) -> dict[str, object]:
    """The S-5 reading, in the pre-registered words.

    The headline is the pre-registration's own rule - arm A collapses *and* arm B is
    monotone - so it is reported even when arm C or a secondary check disagrees, and
    the disagreement stays visible through `verification_passed`.
    """

    arm_a_text = "not read" if arm_a_delta_r2 is None else f"{float(arm_a_delta_r2):+.4f}"
    full_text = "not read" if full_arm_delta_r2 is None else f"{float(full_arm_delta_r2):+.4f}"
    if not criteria.get("integrity_ok"):
        return {
            "decision": "unverified",
            "headline": "未通过完整性自检，三臂数字不得用于判读",
            "observation_level_information_driven": None,
            "statement": (
                "完整性自检未通过（见 integrity），因此即使某个臂的 ΔR² 落在阈值一侧也不作判读；"
                f"W11 的 +{PAIRED_DELTA_R2:.4f} 保持未归因状态。"
            ),
        }
    if criteria.get("arm_a_placebo_collapse") and criteria.get("arm_b_dose_monotone"):
        return {
            "decision": "observation_level_information_driven",
            "headline": "观测级信息驱动",
            "observation_level_information_driven": True,
            "statement": (
                f"Arm A 标签安慰剂把 ΔR² 从 {full_text} 压到 {arm_a_text}（判据 ≤ +{ARM_A_TOLERANCE:.2f}），"
                "Arm B 剂量曲线 25→50→75→100% 单调递增；两条同时成立，故 "
                f"+{PAIRED_DELTA_R2:.4f} 是观测级信息（新化合物自己的温度序列与物理向量）带来的增益，"
                "不能用样本量/正则化效应解释。"
            ),
        }
    reasons: list[str] = []
    if not criteria.get("arm_a_placebo_collapse"):
        reasons.append(f"Arm A 未塌缩（ΔR²={arm_a_text}，判据要求 ≤ +{ARM_A_TOLERANCE:.2f}）")
    if not criteria.get("arm_b_dose_monotone"):
        reasons.append("Arm B 剂量曲线不是单调递增")
    return {
        "decision": "data_volume_effect",
        "headline": f"数据量效应，+{PAIRED_DELTA_R2:.4f} 不得对外引用",
        "observation_level_information_driven": False,
        "statement": (
            "；".join(reasons)
            + f"。因此 W11 的 +{PAIRED_DELTA_R2:.4f} 只能读作数据量/正则化效应，"
            "该数字不得对外引用（Arm C 的均值退化只作机制旁证，不参与这条判据）。"
        ),
    }


#: (label, protocol) rows of the three-arm table, in reading order.
ARM_TABLE_ROWS = (
    ("base", BASE_PROTOCOL),
    ("full (+50 compounds)", FULL_ARM_PROTOCOL),
    ("A label placebo", ARM_A_PROTOCOL),
    ("A reference base", ARM_A_REFERENCE_PROTOCOL),
    ("B dose 25%", dose_protocol(25)),
    ("B dose 50%", dose_protocol(50)),
    ("B dose 75%", dose_protocol(75)),
    ("C mean row", ARM_C_PROTOCOL),
    ("C nearest real row", ARM_C_REAL_ROW_PROTOCOL),
)


def format_report(summary: Mapping[str, object]) -> list[str]:
    """Render the console report, in the order the question was asked."""

    arms = summary["arms"]
    criteria = summary["criteria"]
    verdict = summary["verdict"]
    seeds = summary["seeds"]
    pinned = summary["pinned_check"]
    contract = summary["fold_contract"]
    dose = summary["arm_b_dose"]
    lines: list[str] = []
    lines.append("S-5 placebo arms for the Week 11 coverage gain")
    lines.append(
        "scored pool   : {} rows / {} compounds, {} protocols, folds shared: {}".format(
            contract["arms_scored_rows"][0],
            contract["arms_compounds_scored"][0],
            contract["protocols_with_a_signature"],
            contract["scored_fold_signatures_identical"],
        )
    )
    lines.append(
        "seeds         : folds seed {} x {} repeats, placebo seed {}, dose seed {}".format(
            seeds["fold_seed"], seeds["repeats"], seeds["placebo_seed"], seeds["dose_seed"]
        )
    )
    lines.append(
        "Week 11 re-run: paired_base R2 = {:.16f} (bit exact {})".format(
            float(pinned["paired_base_hybrid_r2"]), pinned["bit_exact"]
        )
    )
    lines.append(
        "                paired_plus_coverage R2 = {:.16f}, dR2 = {:+.16f}".format(
            float(pinned["paired_plus_coverage_hybrid_r2"]), float(pinned["delta_r2"])
        )
    )
    lines.append("")
    lines.append("arm                    dR2       dMAE      dSpearman  R2        W11 band")
    for label, protocol in ARM_TABLE_ROWS:
        block = arms[protocol]
        delta = block["delta_vs_paired_base"]
        lines.append(
            "{:<22s} {:>+9.4f} {:>+9.4f} {:>+9.4f}  {:.4f}  {}".format(
                label,
                float(delta["delta_r2"]),
                float(delta["metrics"]["mae"]["delta"]),
                float(delta["metrics"]["spearman"]["delta"]),
                float(block["hybrid_r2"]),
                delta["verdict"],
            )
        )
    lines.append("")
    lines.append(
        "arm A dR2 = {:+.4f}  (S-5 threshold <= +{:.2f}): {}".format(
            float(arms[ARM_A_PROTOCOL]["delta_vs_paired_base"]["delta_r2"]),
            ARM_A_TOLERANCE,
            criteria["arm_a_placebo_collapse"],
        )
    )
    curve_points = dose["curve"]
    lines.append(
        "arm B dose curve deltas: "
        + ", ".join(
            f"{percent:.0f}%={value:+.4f}"
            for percent, value in zip(curve_points["percents"], curve_points["delta_r2"])
        )
    )
    lines.append(
        "arm B monotone: {} (non-decreasing: {})".format(
            criteria["arm_b_dose_monotone"], criteria["arm_b_non_decreasing"]
        )
    )
    lines.append(
        "arm C dR2 = {:+.4f} vs full arm {:+.4f} -> below: {}".format(
            float(arms[ARM_C_PROTOCOL]["delta_vs_paired_base"]["delta_r2"]),
            float(arms[FULL_ARM_PROTOCOL]["delta_vs_paired_base"]["delta_r2"]),
            criteria["arm_c_below_the_full_arm"],
        )
    )
    lines.append("")
    lines.append("integrity     : {}".format("PASS" if criteria["integrity_ok"] else "FAILED"))
    lines.append("verification  : {}".format(summary["verification_passed"]))
    lines.append("verdict       : {}".format(verdict["decision"]))
    lines.append(str(verdict["headline"]))
    lines.append(str(verdict["statement"]))
    return lines


def render_markdown(summary: Mapping[str, object]) -> str:
    """Render the report from the summary, so no number in it is hand-typed."""

    arms = summary["arms"]
    criteria = summary["criteria"]
    verdict = summary["verdict"]
    seeds = summary["seeds"]
    pinned = summary["pinned_check"]
    inputs = summary["inputs"]
    contract = summary["fold_contract"]
    expansion = summary["training_expansion"]
    crosscheck = summary["training_expansion_week_eleven_crosscheck"]
    dose = summary["arm_b_dose"]
    curve = dose["curve"]
    permutation = summary["arm_a_permutation"]
    target_stats = summary["arm_a_target_stats"]
    scope = summary["placebo_scope_check"]
    mean_row = summary["arm_c_mean_row"]
    augmentation = summary["mean_row_augmentation"]
    frozen = summary["frozen_table"]
    reference = summary["week_eleven_reference"]

    def r2(protocol: str) -> float:
        return float(arms[protocol]["hybrid_r2"])

    def delta(protocol: str, metric: str = "r2") -> float:
        block = arms[protocol]["delta_vs_paired_base"]
        return float(block["metrics"][metric]["delta"])

    def flag(value: object) -> str:
        if value is None:
            return "not read"
        return "PASS" if value else "FAIL"

    def table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
        out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        for row in rows:
            out.append("| " + " | ".join(str(cell) for cell in row) + " |")
        return out

    lines: list[str] = []
    lines.append("# Week 12 · S-5 三臂安慰剂：+0.1241 是观测级信息还是数据量效应？")
    lines.append("")
    lines.append("**探针：** `probes/dielectric_coverage_placebo_arms.py`")
    lines.append("**测试：** `tests/test_dielectric_coverage_placebo_arms.py`")
    lines.append(
        "**复现命令：** `.\\.venv\\Scripts\\python.exe probes\\dielectric_coverage_placebo_arms.py "
        "--overwrite`"
    )
    lines.append("**降级状态：** 本次运行执行 {} 次重复（默认 {}），{}".format(
        seeds["repeats"],
        seeds["repeats_default"],
        "**未降级**" if not seeds["reduced_repeats"] else "**已降级**：W11 钉死值不再逐位可比",
    ))
    lines.append(
        "**本文件由探针渲染：** 下面每一个数字都取自同一次运行写出的 "
        "`probes/dielectric_coverage_placebo_arms_summary.json`，没有手写数字。"
    )
    lines.append("")
    lines.append("## 一、判读结论（S-5 原文判据）")
    lines.append("")
    lines.append("**{}**（`decision = {}`）".format(verdict["headline"], verdict["decision"]))
    lines.append("")
    lines.append(str(verdict["statement"]))
    lines.append("")
    arm_c_gap = (
        f"ΔR²_C = {delta(ARM_C_PROTOCOL):+.4f} "
        f"vs ΔR²_full = {delta(FULL_ARM_PROTOCOL):+.4f}"
    )
    lines.extend(
        table(
            ["S-5 判据", "阈值 / 含义", "实测", "结果"],
            [
                [
                    "Arm A 标签安慰剂塌缩",
                    f"ΔR² ≤ +{ARM_A_TOLERANCE:.2f}",
                    f"ΔR² = {delta(ARM_A_PROTOCOL):+.4f}",
                    flag(criteria["arm_a_placebo_collapse"]),
                ],
                [
                    "Arm B 剂量曲线单调递增",
                    "25→50→75→100%，每一步为正",
                    "步长 " + "、".join(f"{step:+.4f}" for step in curve["steps"]),
                    flag(criteria["arm_b_dose_monotone"]),
                ],
                [
                    "Arm C 均值退化低于全量臂",
                    "ΔR²_C < ΔR²_full（机制旁证，不入判据）",
                    arm_c_gap,
                    flag(criteria["arm_c_below_the_full_arm"]),
                ],
                ["完整性自检", "折共享 + W11 钉死值逐位复现", "见第六节", flag(criteria["integrity_ok"])],
            ],
        )
    )
    lines.append("")
    lines.append(
        "`verification_passed` = **{}**（三项判据 + 完整性自检全过才为 True；"
        "headline 按 S-5 的 A 与 B 判据书写）".format(summary["verification_passed"])
    )
    lines.append("")
    lines.append("## 二、三臂实测")
    lines.append("")
    lines.append(
        "打分池钉死为 v11 室温带 **{} 行 / {} 化合物**。折由 `masked_splits` 只在打分侧化合物上发放，"
        "本探针跑的 {} 个协议**打分侧折签名逐位相同 = {}**，所以每个臂的分母与被评行都一致。".format(
            contract["arms_scored_rows"][0],
            contract["arms_compounds_scored"][0],
            contract["protocols_with_a_signature"],
            contract["scored_fold_signatures_identical"],
        )
    )
    lines.append("")
    rows = []
    for label, protocol in ARM_TABLE_ROWS:
        step = expansion[protocol]
        rows.append(
            [
                label,
                f"`{protocol}`",
                step["train_pool_rows"],
                arms[protocol]["train_pool_compounds"],
                "{:.1f}".format(step["extra_rows_fitted_per_fold_mean"]),
                f"{r2(protocol):.4f}",
                f"{delta(protocol):+.4f}",
                "{:+.4f}".format(delta(protocol, "mae")),
                "{:+.4f}".format(delta(protocol, "spearman")),
                arms[protocol]["delta_vs_paired_base"]["verdict"],
            ]
        )
    lines.extend(
        table(
            [
                "臂",
                "协议",
                "训练池行",
                "训练池化合物",
                "每折真实多训练行",
                "R²",
                "ΔR²",
                "ΔMAE",
                "ΔSpearman",
                "W11 ±0.005 判词",
            ],
            rows,
        )
    )
    lines.append("")
    lines.append(
        "- **W11 钉死值逐位复现：** `paired_base` R² = **{:.16f}**（期望 {:.16f}）；"
        "`paired_plus_coverage` R² = **{:.16f}**（期望 {:.16f}）；ΔR² = **{:.16f}**"
        "（期望 {:.16f}）；`bit_exact` = **{}**{}".format(
            float(pinned["paired_base_hybrid_r2"]),
            PAIRED_BASE_R2,
            float(pinned["paired_plus_coverage_hybrid_r2"]),
            PAIRED_PLUS_COVERAGE_R2,
            float(pinned["delta_r2"]),
            PAIRED_DELTA_R2,
            pinned["bit_exact"],
            "" if pinned["applicable"] else "（" + str(pinned["reason"]) + "）",
        )
    )
    lines.append(
        "- **有效训练扩张：** 全量臂 **{:.1f} 行/折**（合计 {}，min=max={}），训练池 {} 行 / {} 化合物；"
        "W11 同项交叉核对 = **{}**。".format(
            expansion[FULL_ARM_PROTOCOL]["extra_rows_fitted_per_fold_mean"],
            expansion[FULL_ARM_PROTOCOL]["extra_rows_fitted_total"],
            expansion[FULL_ARM_PROTOCOL]["extra_rows_fitted_per_fold_min"],
            expansion[FULL_ARM_PROTOCOL]["train_pool_rows"],
            arms[FULL_ARM_PROTOCOL]["train_pool_compounds"],
            crosscheck[FULL_ARM_PROTOCOL]["identical"],
        )
    )
    lines.append(
        "- **上游对账：** 读到的 `probes/dielectric_coverage_paired_benchmark_summary.json` "
        "state = {}；其固定池链 {}，其 `extra_rows_fitted_per_fold_mean` = {}。".format(
            reference["status"],
            ", ".join(
                f"{name}={value:+.4f}" for name, value in reference.get("chain", {}).items()
            ),
            reference.get("extra_rows_fitted_per_fold_mean"),
        )
    )
    lines.append("")
    lines.append("## 三、Arm A 标签安慰剂：到底置换了什么")
    lines.append("")
    lines.append(
        "置换只在**新增化合物的 ε 标签之间**做：把某个化合物的标签整块挪到别的化合物上，"
        "行数（{} 行）、组成、特征向量、T_K 与正则化一字不动，打分侧（v11 零频 {} 行）一个标签都没碰。".format(
            permutation["added_rows"], inputs["scored_rows"]
        )
    )
    lines.append("")
    lines.extend(
        table(
            ["量", "值"],
            [
                ["被打乱的化合物数（自身标签多重集改变）", permutation["compounds_with_a_changed_label_multiset"]],
                ["收到外来标签的化合物数", permutation["compounds_receiving_a_foreign_label"]],
                ["标签发生变化行数", permutation["labels_changed"]],
                ["标签变化比例", "{:.4f}".format(permutation["label_change_fraction"])],
                ["收到外来化合物标签的行数", permutation["rows_receiving_a_foreign_label"]],
                ["置乱后新增块 ε 多重集不变", permutation["label_multiset_preserved"]],
                ["新增块之外一个标签都没动", permutation["labels_untouched_outside_the_added_block"]],
                ["固定种子", permutation["seed"]],
            ],
        )
    )
    lines.append("")
    lines.append("新增块的 ε 分布（多重集不变，所以均值/方差必然逐位相同）：")
    lines.append("")
    before_stats = target_stats["before"]
    after_stats = target_stats["after"]
    lines.extend(
        table(
            ["统计量", "置换前", "置换后"],
            [
                ["行数", before_stats["rows"], after_stats["rows"]],
                ["均值", f"{before_stats['mean']:.6f}", f"{after_stats['mean']:.6f}"],
                ["方差", f"{before_stats['var']:.6f}", f"{after_stats['var']:.6f}"],
                [
                    "最小 / 最大",
                    "{} / {}".format(before_stats["min"], before_stats["max"]),
                    "{} / {}".format(after_stats["min"], after_stats["max"]),
                ],
                ["> 60 的行数", before_stats["rows_above_60"], after_stats["rows_above_60"]],
            ],
        )
    )
    lines.append("")
    lines.append(
        "**安慰剂作用域自检：** 置换只动新增化合物的 ε，而 `paired_base` 既不打分也不拟合这些行，"
        "所以「置换目标下的 base」必须与真实标签下的 base 逐位相同。实测 {} 个格（3 表示 × {} 指标）"
        "的 `max_abs_delta` = **{}**，`bit_exact` = **{}**。".format(
            scope["cells"],
            len(week_eleven.METRIC_NAMES),
            scope["max_abs_delta"],
            scope["bit_exact"],
        )
    )
    lines.append(
        "Arm A 的 ΔR² = **{:+.4f}**：判据要求 ≤ +{:.2f}，实测 {}。".format(
            delta(ARM_A_PROTOCOL), ARM_A_TOLERANCE, flag(criteria["arm_a_placebo_collapse"])
        )
    )
    lines.append("")
    lines.append("## 四、Arm B 剂量曲线")
    lines.append("")
    lines.append(
        "子采样在**化合物层**做：先按固定种子 {} 抽一个化合物顺序，四个档位各取该顺序的前缀，"
        "所以各档**互相嵌套**（25% ⊂ 50% ⊂ 75% ⊂ 100%），一个化合物整块进或整块不进。100% 档的"
        "训练掩码与全量臂逐位相同 = **{}**，故直接复用全量臂的拟合而不重跑。".format(
            dose["seed"], dose["hundred_percent_mask_equals_the_full_arm_mask"]
        )
    )
    lines.append("")
    dose_rows = []
    for level in dose["levels"]:
        percent = int(level["percent"])
        protocol = str(level["protocol"])
        value = float(arms[protocol]["delta_vs_paired_base"]["delta_r2"])
        index = curve["percents"].index(percent)
        step_text = "-" if index == 0 else "{:+.4f}".format(curve["steps"][index - 1])
        dose_rows.append(
            [
                f"{percent}%",
                level["compounds"],
                expansion[protocol]["train_pool_rows"],
                "{:.1f}".format(expansion[protocol]["extra_rows_fitted_per_fold_mean"]),
                f"{r2(protocol):.4f}",
                f"{value:+.4f}",
                step_text,
            ]
        )
    lines.extend(
        table(["档位", "纳入化合物", "训练池行", "每折多训练行", "R²", "ΔR²", "本步增量"], dose_rows)
    )
    lines.append("")
    lines.append(
        "- 单调（严格，每步 > 0）= **{}**；非递减（浮点容差 {}）= **{}**；曲线跨度 = {:+.4f}。".format(
            curve["monotone"], curve["tolerance"], curve["non_decreasing"], curve["span"]
        )
    )
    lines.append(
        "- 判据「剂量曲线单调递增」：**{}**。{}".format(
            flag(criteria["arm_b_dose_monotone"]), curve["note"]
        )
    )
    lines.append("")
    lines.append("## 五、Arm C 均值退化：温度分辨率才是载体？")
    lines.append("")
    lines.append(
        "两种读法都跑了，两者都保留 50 个化合物、都只剩 1 行/化合物："
        "(1) **均值行**（合成）= 该化合物自己的 xTB 向量 + 自己的平均 T_K + 自己的平均 ε；"
        "(2) **最近真实行**（选择）= 该化合物室温行里 ε 最接近其均值的真实一行。".format()
    )
    lines.append("")
    full_expansion = expansion[FULL_ARM_PROTOCOL]
    mean_row_expansion = expansion[ARM_C_PROTOCOL]
    real_row_expansion = expansion[ARM_C_REAL_ROW_PROTOCOL]
    lines.extend(
        table(
            ["方案", "协议", "行/化合物", "新增行", "每折多训练行", "R²", "ΔR²", "相对全量臂亏损"],
            [
                [
                    "全量臂（参照）",
                    f"`{FULL_ARM_PROTOCOL}`",
                    f"{full_expansion['rows_added_over_base'] / ADDED_COMPOUNDS:.2f}",
                    full_expansion["rows_added_over_base"],
                    f"{full_expansion['extra_rows_fitted_per_fold_mean']:.1f}",
                    f"{r2(FULL_ARM_PROTOCOL):.4f}",
                    f"{delta(FULL_ARM_PROTOCOL):+.4f}",
                    "-",
                ],
                [
                    "C-1 均值行（合成）",
                    f"`{ARM_C_PROTOCOL}`",
                    f"{mean_row_expansion['rows_added_over_base'] / ADDED_COMPOUNDS:.2f}",
                    mean_row_expansion["rows_added_over_base"],
                    f"{mean_row_expansion['extra_rows_fitted_per_fold_mean']:.1f}",
                    f"{r2(ARM_C_PROTOCOL):.4f}",
                    f"{delta(ARM_C_PROTOCOL):+.4f}",
                    f"{delta(ARM_C_PROTOCOL) - delta(FULL_ARM_PROTOCOL):+.4f}",
                ],
                [
                    "C-2 最近真实行",
                    f"`{ARM_C_REAL_ROW_PROTOCOL}`",
                    f"{real_row_expansion['rows_added_over_base'] / ADDED_COMPOUNDS:.2f}",
                    real_row_expansion["rows_added_over_base"],
                    f"{real_row_expansion['extra_rows_fitted_per_fold_mean']:.1f}",
                    f"{r2(ARM_C_REAL_ROW_PROTOCOL):.4f}",
                    f"{delta(ARM_C_REAL_ROW_PROTOCOL):+.4f}",
                    f"{delta(ARM_C_REAL_ROW_PROTOCOL) - delta(FULL_ARM_PROTOCOL):+.4f}",
                ],
            ],
        )
    )
    lines.append("")
    lines.append(
        "- C-1：保留化合物 **{}** 个、只保留 **{}** 行（丢掉 {} 行），"
        "均值行的物理块在化合物内恒定 = **{}**。".format(
            augmentation["compounds"],
            augmentation["synthetic_rows"],
            expansion[FULL_ARM_PROTOCOL]["rows_added_over_base"] - augmentation["synthetic_rows"],
            augmentation["physical_block_constant_within_every_compound"],
        )
    )
    lines.append(
        "- C-2：候选 {} 行 → 保留 {} 行（丢掉 {} 行），每化合物恰一行 = **{}**。".format(
            mean_row["candidate_rows"],
            mean_row["kept_rows"],
            mean_row["rows_dropped"],
            mean_row["kept_rows"] == ADDED_COMPOUNDS,
        )
    )
    arm_c_below = flag(delta(ARM_C_PROTOCOL) < delta(FULL_ARM_PROTOCOL))
    real_row_below = flag(delta(ARM_C_REAL_ROW_PROTOCOL) < delta(FULL_ARM_PROTOCOL))
    lines.append(
        f"- 判据「ΔR² 显著低于全量臂」：C-1 {arm_c_below}、C-2 {real_row_below}"
        "（两个读法同向才算稳）。"
    )
    lines.append("")
    lines.append("## 六、完整性自检")
    lines.append("")
    lines.extend(
        table(
            ["检查", "结果"],
            [[key, flag(value)] for key, value in summary["integrity"].items()],
        )
    )
    lines.append("")
    lines.append(
        "- 冻结文件 `{}`：{}\uff0c实测 sha256 = `{}`（期望 `{}`），CRLF = {}。".format(
            frozen["path"],
            frozen["status"],
            frozen.get("sha256", "not read"),
            frozen["expected"],
            frozen.get("crlf_present", "not read"),
        )
    )
    lines.append(
        "- 输入指纹：cov = `{}`，v11 = `{}`。".format(
            inputs["coverage_sha256"], inputs["v11_sha256"]
        )
    )
    lines.append("")
    lines.append("## 七、可复现性")
    lines.append("")
    lines.append(
        "- 固定随机量：折种子 **{}**（= W11 的 SEED）x {} 折 x {} 次重复；"
        "置换种子 **{}**；剂量种子 **{}**。".format(
            seeds["fold_seed"],
            N_SPLITS,
            seeds["repeats"],
            seeds["placebo_seed"],
            seeds["dose_seed"],
        )
    )
    lines.append(
        "- 本报告与 summary 不含时间戳，任何随机过程都由上面的种子决定；"
        "带 `--overwrite` 重跑两次的产物应当逐字节一致。"
    )
    lines.append(
        "- {} 显式声明：{}".format(
            "降级" if seeds["reduced_repeats"] else "无降级",
            str(pinned.get("reason", "本次运行与 W11 的重复次数一致，钉死值逐位可比")),
        )
    )
    lines.append("")
    lines.append("## 八、红线")
    lines.append("")
    lines.append("- `paper/` 零改动：本探针只写 summary、本报告与三个 CSV。")
    lines.append(
        "- `data/dielectric_v03.csv` 未改：digest 保持 `{}`（实测 = {}）。".format(
            FROZEN_TABLE_SHA256, frozen.get("sha256", "not read")
        )
    )
    lines.append(
        "- 未引入新的数据划分：所有臂都跑在 W11 的 `masked_splits` 上，折签名逐位相同。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# the summary and the entry point
# --------------------------------------------------------------------------- #


def assemble_summary(
    *,
    repeats: int,
    fold_seed: int,
    family_one: Mapping[str, object],
    family_two: Mapping[str, object],
    masks: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
    mask_report: Mapping[str, object],
    permutation_report: Mapping[str, object],
    target_stats: Mapping[str, object],
    dose_selection: Mapping[str, object],
    mean_row_report: Mapping[str, object],
    augmentation_report: Mapping[str, object],
    frozen_digest: Mapping[str, object],
    reference: Mapping[str, object],
    agreement: Mapping[str, object],
    inventory: Mapping[str, object],
    feature_report: Mapping[str, object],
    coverage_dropped: Mapping[str, int],
    coverage_sha256: str,
    v11_sha256: str,
) -> dict[str, object]:
    """Assemble every number of the run into the summary the report is rendered from."""

    protocols: dict[str, object] = {**family_one["protocols"], **family_two["protocols"]}
    audits: dict[str, object] = {**family_one["audits"], **family_two["audits"]}
    metrics: dict[str, object] = {**family_one["summary"], **family_two["summary"]}
    splits_by_protocol: dict[str, object] = {
        **family_one["splits_by_protocol"],
        **family_two["splits_by_protocol"],
    }
    names = [*FAMILY_ONE_PROTOCOLS, *FAMILY_TWO_PROTOCOLS]

    arms: dict[str, object] = {}
    for name in names:
        meta = protocols[name]
        arms[name] = {
            "protocol": name,
            "description": protocol_description(name),
            "splitter": str(meta["splitter"]),
            "scored_rows": int(meta["scored_rows"]),
            "compounds_scored": int(meta["compounds_scored"]),
            "train_pool_rows": int(meta["train_pool_rows"]),
            "train_pool_compounds": int(meta["train_pool_compounds"]),
            "folds": int(meta["folds"]),
            "executed_repeats": int(meta["executed_repeats"]),
            "repeats_note": str(meta["note"]),
            "compounds_available_for_training": int(
                audits[name]["compounds_available_for_training"]
            ),
            "training_only_compounds": len(audits[name]["training_only_compounds"]),
            "hybrid_r2": float(metrics[name][HYBRID]["r2"]["mean"]),
            "metrics": metrics[name],
            "delta_vs_paired_base": paired_delta(metrics, base=BASE_PROTOCOL, widened=name),
        }

    expansion = arm_training_expansion(names, masks, splits_by_protocol=splits_by_protocol)
    week_eleven_expansion = week_eleven.training_expansion(
        masks, splits_by_protocol=splits_by_protocol
    )
    crosscheck = {
        name: {
            "mine": expansion[name],
            "week_eleven": week_eleven_expansion[name],
            "identical": expansion[name] == week_eleven_expansion[name],
        }
        for name in WEEK_ELEVEN_PROTOCOLS
    }
    contract = fold_contract(protocols, splits_by_protocol)
    dose_curve = dose_curve_report(
        [
            {
                "percent": int(level["percent"]),
                "delta_r2": float(arms[str(level["protocol"])]["delta_vs_paired_base"]["delta_r2"]),
            }
            for level in dose_selection["levels"]
        ]
    )
    dose_report = {**dose_selection, "curve": dose_curve}

    scope_cells: dict[str, object] = {}
    for representation in week_eleven.REPRESENTATIONS:
        for metric in week_eleven.METRIC_NAMES:
            left = float(metrics[ARM_A_REFERENCE_PROTOCOL][representation][metric]["mean"])
            right = float(metrics[BASE_PROTOCOL][representation][metric]["mean"])
            scope_cells[f"{representation}|{metric}"] = {
                "permuted_target": left,
                "paired_base": right,
                "delta": left - right,
            }
    scope = {
        "protocol": ARM_A_REFERENCE_PROTOCOL,
        "compared_against": BASE_PROTOCOL,
        "cells": len(scope_cells),
        "representations": list(week_eleven.REPRESENTATIONS),
        "metrics": list(week_eleven.METRIC_NAMES),
        "max_abs_delta": max(
            (abs(float(cell["delta"])) for cell in scope_cells.values()), default=0.0
        ),
        "bit_exact": all(float(cell["delta"]) == 0.0 for cell in scope_cells.values()),
        "deltas": scope_cells,
        "statement": (
            "the placebo moves only the epsilons of added compounds, which paired_base can "
            "neither score nor fit, so its re-run under the permuted target has to come back "
            "bit-identical to the run under the true labels"
        ),
    }

    pinned = pinned_reproduction(
        paired_base_r2=float(arms[BASE_PROTOCOL]["hybrid_r2"]),
        paired_plus_coverage_r2=float(arms[FULL_ARM_PROTOCOL]["hybrid_r2"]),
        repeats=repeats,
    )
    arm_a_delta = float(arms[ARM_A_PROTOCOL]["delta_vs_paired_base"]["delta_r2"])
    arm_c_delta = float(arms[ARM_C_PROTOCOL]["delta_vs_paired_base"]["delta_r2"])
    full_delta = float(arms[FULL_ARM_PROTOCOL]["delta_vs_paired_base"]["delta_r2"])

    integrity: dict[str, object] = {
        "frozen_v03_digest_unchanged": bool(frozen_digest.get("matches_literal")),
        "merged_v11_block_order_identical": bool(agreement["order_identical"]),
        "every_protocol_uses_the_grouped_splitter": all(
            str(protocols[name]["splitter"]) == "grouped" for name in names
        ),
        "folds_shared_by_every_arm": bool(contract["scored_fold_signatures_identical"]),
        "scored_pool_is_the_pinned_457_over_97": bool(
            int(protocols[BASE_PROTOCOL]["scored_rows"]) == PAIRED_SCORED_ROWS
            and int(protocols[BASE_PROTOCOL]["compounds_scored"]) == PAIRED_SCORED_COMPOUNDS
        ),
        "added_compounds_are_the_pinned_50": bool(int(inventory["compounds"]) == ADDED_COMPOUNDS),
        "added_room_rows_are_the_pinned_127": bool(
            int(inventory["room_rows_total"]) == ADDED_ROOM_ROWS
        ),
        "extra_rows_fitted_per_fold_is_the_pinned_127": bool(
            float(expansion[FULL_ARM_PROTOCOL]["extra_rows_fitted_per_fold_mean"])
            == ADDED_EXTRA_ROWS_PER_FOLD
        ),
        "training_expansion_matches_week_11_on_the_shared_names": all(
            bool(item["identical"]) for item in crosscheck.values()
        ),
        "week_eleven_numbers_reproduced": pinned["bit_exact"],
        "placebo_moved_only_rows_the_base_cannot_reach": scope["bit_exact"],
        "permutation_preserved_the_label_multiset": permutation_report["label_multiset_preserved"],
        "mean_row_arm_kept_one_row_per_added_compound": bool(
            int(augmentation_report["synthetic_rows"]) == ADDED_COMPOUNDS
        ),
        "mean_rows_are_constant_within_a_compound": augmentation_report[
            "physical_block_constant_within_every_compound"
        ],
    }
    # A None entry means "not read" - the pinned Week 11 means under a reduced repeat
    # count, for instance - and is recorded as such rather than counted as a failure.
    integrity["ok"] = all(value is not False for value in integrity.values())

    criteria = build_criteria(
        integrity_ok=bool(integrity["ok"]),
        arm_a_delta_r2=arm_a_delta,
        dose_curve=dose_curve,
        arm_c_delta_r2=arm_c_delta,
        full_arm_delta_r2=full_delta,
    )
    verdict = build_verdict(
        criteria, arm_a_delta_r2=arm_a_delta, full_arm_delta_r2=full_delta
    )

    return {
        "schema_version": 1,
        "probe": "probes/dielectric_coverage_placebo_arms.py",
        "reproduce": (
            ".\\.venv\\Scripts\\python.exe probes\\dielectric_coverage_placebo_arms.py --overwrite"
        ),
        "pinned_targets": {
            "scored_rows": PAIRED_SCORED_ROWS,
            "scored_compounds": PAIRED_SCORED_COMPOUNDS,
            "added_compounds": ADDED_COMPOUNDS,
            "added_room_rows": ADDED_ROOM_ROWS,
            "extra_rows_fitted_per_fold": ADDED_EXTRA_ROWS_PER_FOLD,
            "paired_base_hybrid_r2": PAIRED_BASE_R2,
            "paired_plus_coverage_hybrid_r2": PAIRED_PLUS_COVERAGE_R2,
            "paired_delta_r2": PAIRED_DELTA_R2,
            "arm_a_threshold": ARM_A_TOLERANCE,
            "frozen_v03_sha256": FROZEN_TABLE_SHA256,
        },
        "seeds": {
            "fold_seed": int(fold_seed),
            "n_splits": N_SPLITS,
            "repeats": int(repeats),
            "repeats_default": N_REPEATS,
            "reduced_repeats": int(repeats) < N_REPEATS,
            "placebo_seed": PLACEBO_SEED,
            "dose_seed": DOSE_SEED,
        },
        "protocol": {
            "validation": (
                "group K-fold by InChIKey over the scored pool: a fresh permutation of the "
                "sorted scored compound keys per repeat, dealt round-robin, whole compounds "
                "held out - Week 11's own splitter, reused through masked_splits"
            ),
            "n_splits": N_SPLITS,
            "repeats": int(repeats),
            "random_state": int(fold_seed),
            "model": "XGBRegressor with the frozen v1.0 hyper-parameters",
            "xgb_params": dict(XGB_PARAMS),
            "representations": list(week_eleven.REPRESENTATIONS),
            "physical_block": "frozen xTB vector with T_K replaced by the observation's T_K",
            "min_test_rows_per_fold": week_eleven.MIN_TEST_ROWS_PER_FOLD,
            "scored_mask": "the v11 zero-frequency room-band rows",
            "paired_rule": (
                "folds are dealt over the compounds of the scored mask only, so every arm that "
                "scores the same rows shares one fold assignment even when its training pool "
                "differs - and every arm here scores the same rows"
            ),
            "arm_a": (
                "epsilons of the added compounds permuted between compounds, seed "
                f"{PLACEBO_SEED}"
            ),
            "arm_b": (
                "compound-level subsample at 25/50/75/100% of the added compounds, one shared "
                f"random compound order so the doses nest, seed {DOSE_SEED}"
            ),
            "arm_c": (
                "one mean row per added compound, appended after the observation rows so no "
                "index moves"
            ),
        },
        "inputs": {
            "observations_path": portable_relative_path(
                week_eleven.COVERAGE_PATH, root=REPOSITORY_ROOT
            ),
            "observations_sha256": coverage_sha256,
            "v11_observations_path": portable_relative_path(
                week_eleven.OBSERVATIONS_PATH, root=REPOSITORY_ROOT
            ),
            "v11_observations_sha256": v11_sha256,
            "coverage_sha256": coverage_sha256,
            "v11_sha256": v11_sha256,
            "scored_rows": PAIRED_SCORED_ROWS,
            "scored_compounds": PAIRED_SCORED_COMPOUNDS,
            "coverage_rows": int(agreement["coverage_zero_frequency_rows"]),
            "dropped_rows": dict(sorted(coverage_dropped.items())),
            "coverage_compounds": len(inventory["per_compound"]),
        },
        "frozen_table": frozen_digest,
        "week_eleven_reference": reference,
        "feature_blocks": feature_report,
        "pinned_check": pinned,
        "placebo_scope_check": scope,
        "inventory": {
            key: value for key, value in inventory.items() if key != "per_compound"
        },
        "masks": mask_report,
        "arms": arms,
        "arm_a_permutation": permutation_report,
        "arm_a_target_stats": target_stats,
        "arm_b_dose": dose_report,
        "arm_c_mean_row": mean_row_report,
        "mean_row_augmentation": augmentation_report,
        "fold_contract": contract,
        "training_expansion": expansion,
        "training_expansion_week_eleven_crosscheck": crosscheck,
        "integrity": integrity,
        "criteria": criteria,
        "verification_passed": verification_passed(criteria),
        "verdict": verdict,
    }


def planned_outputs(
    summary_path: Path,
    report_path: Path,
    artifacts_dir: Path,
) -> dict[str, Path]:
    """Every path this probe writes, so --overwrite can be checked before the run."""

    return {
        "summary": summary_path,
        "report": report_path,
        "folds": artifacts_dir / (ARTIFACT_STEM + "_folds.csv"),
        "repeats": artifacts_dir / (ARTIFACT_STEM + "_repeats.csv"),
        "predictions": artifacts_dir / (ARTIFACT_STEM + "_predictions.csv"),
    }


def refuse_existing(paths: Mapping[str, Path], *, overwrite: bool) -> list[Path]:
    """The outputs that already exist while --overwrite was not given."""

    if overwrite:
        return []
    return sorted((path for path in paths.values() if path.exists()), key=str)


def jsonable(value: object) -> object:
    """Convert whatever the run produced into JSON-native objects.

    The accounting is arithmetic on numpy scalars, so a stray np.float64 would break
    the encoder; this walks the result once instead of sprinkling casts through it.
    """

    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [jsonable(item) for item in value.tolist()]
    return value


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=FOLD_SEED, help="fold-dealing seed")
    parser.add_argument("--placebo-seed", type=int, default=PLACEBO_SEED, help="arm A permutation")
    parser.add_argument("--dose-seed", type=int, default=DOSE_SEED, help="arm B compound order")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing summary, report or artifact table",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    repeats = int(args.repeats)
    fold_seed = int(args.seed)
    outputs = planned_outputs(Path(args.summary), Path(args.report), Path(args.artifacts_dir))
    existing = refuse_existing(outputs, overwrite=bool(args.overwrite))
    if existing:
        print("refusing to touch an existing output without --overwrite:")
        for path in existing:
            print("  " + portable_relative_path(path, root=REPOSITORY_ROOT))
        return 2

    v11_rows, _frozen_features, _v11_dropped = week_eleven.load_table(
        week_eleven.OBSERVATIONS_PATH, week_eleven.FEATURES_PATH
    )
    merged, feature_report = week_eleven.merge_feature_blocks()
    coverage_rows, coverage_dropped = week_eleven.load_coverage_table(
        week_eleven.COVERAGE_PATH, merged
    )
    agreement = week_eleven.frozen_table_agreement(v11_rows, coverage_rows)
    inventory = week_eleven.new_compound_inventory(
        coverage_rows, {str(row["inchikey"]) for row in v11_rows}
    )

    morgan, physical, target, temperatures, groups = week_eleven.build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    keys = [str(value) for value in groups]
    zero = origin == week_eleven.ZERO_FREQUENCY_ORIGIN
    room = band == ROOM_BAND
    added_keys = set(inventory["per_compound"])
    is_new = np.asarray([key in added_keys for key in keys])
    new_xtb_keys = {
        str(key)
        for key, item in inventory["per_compound"].items()
        if item.get("feature_source") == week_eleven.NEW_XTB_SOURCE
    }
    is_new_xtb = np.asarray([key in new_xtb_keys for key in keys])
    scored = zero & room
    added_room = is_new & room

    arm_a_target, permutation_report = permute_added_compound_labels(
        keys, target, added_mask=is_new, seed=int(args.placebo_seed)
    )
    target_values = np.asarray(target, dtype=float)
    arm_a_values = np.asarray(arm_a_target, dtype=float)
    target_stats = {
        "before": week_eleven.value_stats(target_values[is_new]),
        "after": week_eleven.value_stats(arm_a_values[is_new]),
        "scored_side_labels_untouched": bool(
            np.array_equal(arm_a_values[scored], target_values[scored])
        ),
        "block_statistics_identical": bool(
            week_eleven.value_stats(target_values[is_new])
            == week_eleven.value_stats(arm_a_values[is_new])
        ),
    }

    morgan_ext, physical_ext, target_ext, temperatures_ext, keys_ext, augmentation = (
        mean_row_augmentation(
            keys, morgan, physical, target, temperatures, added_mask=is_new, room_mask=room
        )
    )
    synthetic = np.zeros(target_ext.size, dtype=bool)
    synthetic[int(augmentation["row_index_start"]) : int(augmentation["row_index_stop"])] = True
    arm_a_target_ext = np.concatenate([arm_a_target, target_ext[synthetic]])
    real_row_keep, mean_row_report = mean_row_selection(
        keys, target, temperatures, candidate_mask=added_room
    )

    order = dose_compound_order(inventory["per_compound"], seed=int(args.dose_seed))
    dose_members = {
        percent: set(dose_compounds(order, percent)) for percent in DOSE_RUN_PERCENTS
    }

    def padded(mask: Sequence[bool], *, extra: bool = False) -> np.ndarray:
        return np.concatenate(
            [np.asarray(mask, dtype=bool), np.full(int(synthetic.sum()), bool(extra))]
        )

    family_one_masks: dict[str, tuple[np.ndarray, np.ndarray]] = {
        BASE_PROTOCOL: (padded(scored), padded(scored)),
        FULL_ARM_PROTOCOL: (padded(scored), padded(room & (zero | is_new))),
        "paired_plus_new_xtb": (padded(scored), padded(room & (zero | is_new_xtb))),
        "paired_plus_v03_block": (
            padded(scored),
            padded(room & (zero | (is_new & ~is_new_xtb))),
        ),
        ARM_C_PROTOCOL: (padded(scored), padded(scored, extra=True)),
        ARM_C_REAL_ROW_PROTOCOL: (padded(scored), padded(scored | (added_room & real_row_keep))),
    }
    for percent in DOSE_RUN_PERCENTS:
        chosen = np.asarray([key in dose_members[percent] for key in keys])
        family_one_masks[dose_protocol(percent)] = (
            padded(scored),
            padded(room & (zero | (is_new & chosen))),
        )
    family_two_masks: dict[str, tuple[np.ndarray, np.ndarray]] = {
        ARM_A_REFERENCE_PROTOCOL: (padded(scored), padded(scored)),
        ARM_A_PROTOCOL: (padded(scored), padded(room & (zero | is_new))),
    }

    is_new_ext = padded(is_new, extra=True)
    keys_ext_array = np.asarray(keys_ext)

    def compounds_in(mask: Sequence[bool]) -> set[str]:
        return {str(key) for key in keys_ext_array[np.asarray(mask, dtype=bool) & is_new_ext]}

    every_added = np.ones_like(is_new)
    mask_report = {
        "observation_rows": int(scored.size),
        "synthetic_rows": int(synthetic.sum()),
        "scored_rows": int(scored.sum()),
        "added_rows": int(is_new.sum()),
        "added_room_rows": int(added_room.sum()),
        "added_compounds": len(added_keys),
        "week_eleven_expression_equivalences": {
            "full_arm_two_ways": bool(np.array_equal(room & (zero | is_new), scored | added_room)),
            "new_xtb_two_ways": bool(
                np.array_equal(
                    room & (zero | is_new_xtb), scored | (added_room & is_new_xtb)
                )
            ),
            "v03_block_two_ways": bool(
                np.array_equal(
                    room & (zero | (is_new & ~is_new_xtb)),
                    scored | (added_room & (is_new & ~is_new_xtb)),
                )
            ),
        },
        "dose_mask_compounds_are_exactly_the_selected_ones": {
            str(percent): sorted(compounds_in(family_one_masks[dose_protocol(percent)][1]))
            == sorted(dose_members[percent])
            for percent in DOSE_RUN_PERCENTS
        },
        "mean_row_arm_compounds_are_all_added_compounds": sorted(
            compounds_in(family_one_masks[ARM_C_PROTOCOL][1])
        )
        == sorted(added_keys),
        "mean_row_arm_added_rows": int(
            np.asarray(family_one_masks[ARM_C_PROTOCOL][1], dtype=bool).sum()
            - np.asarray(family_one_masks[BASE_PROTOCOL][1], dtype=bool).sum()
        ),
        "hundred_percent_mask_equals_the_full_arm_mask": bool(
            np.array_equal(
                padded(room & (zero | (is_new & every_added))),
                np.asarray(family_one_masks[FULL_ARM_PROTOCOL][1], dtype=bool),
            )
        ),
    }
    dose_selection = {
        "seed": int(args.dose_seed),
        "order": order,
        "nesting": "every dose is a prefix of one shared compound order, so the levels nest",
        "levels": [
            {
                "percent": int(percent),
                "protocol": protocol,
                "compounds": len(dose_members[percent])
                if percent in dose_members
                else len(added_keys),
                "selected_compounds": sorted(dose_members[percent])
                if percent in dose_members
                else sorted(added_keys),
            }
            for percent, protocol in zip(
                DOSE_CURVE_PERCENTS, (*DOSE_PROTOCOL_NAMES, FULL_ARM_PROTOCOL), strict=True
            )
        ],
        "hundred_percent_mask_equals_the_full_arm_mask": mask_report[
            "hundred_percent_mask_equals_the_full_arm_mask"
        ],
    }

    with arm_descriptions():
        family_one = week_eleven.run_protocol_family(
            FAMILY_ONE_PROTOCOLS,
            splitters={name: "grouped" for name in FAMILY_ONE_PROTOCOLS},
            morgan=morgan_ext,
            physical=physical_ext,
            target=target_ext,
            temperatures=temperatures_ext,
            groups=keys_ext,
            masks=family_one_masks,
            n_splits=N_SPLITS,
            n_repeats=repeats,
            seed=fold_seed,
        )
        family_two = week_eleven.run_protocol_family(
            FAMILY_TWO_PROTOCOLS,
            splitters={name: "grouped" for name in FAMILY_TWO_PROTOCOLS},
            morgan=morgan_ext,
            physical=physical_ext,
            target=arm_a_target_ext,
            temperatures=temperatures_ext,
            groups=keys_ext,
            masks=family_two_masks,
            n_splits=N_SPLITS,
            n_repeats=repeats,
            seed=fold_seed,
        )

    summary = assemble_summary(
        repeats=repeats,
        fold_seed=fold_seed,
        family_one=family_one,
        family_two=family_two,
        masks={**family_one_masks, **family_two_masks},
        mask_report=mask_report,
        permutation_report=permutation_report,
        target_stats=target_stats,
        dose_selection=dose_selection,
        mean_row_report=mean_row_report,
        augmentation_report=augmentation,
        frozen_digest=frozen_table_digest(),
        reference=week_eleven_reference(),
        agreement=agreement,
        inventory=inventory,
        feature_report=feature_report,
        coverage_dropped=coverage_dropped,
        coverage_sha256=canonical_text_sha256(week_eleven.COVERAGE_PATH),
        v11_sha256=canonical_text_sha256(week_eleven.OBSERVATIONS_PATH),
    )
    artifacts = week_eleven.write_artifacts(
        Path(args.artifacts_dir),
        ARTIFACT_STEM,
        fold_rows=[*family_one["fold_rows"], *family_two["fold_rows"]],
        repeat_rows=[*family_one["repeat_rows"], *family_two["repeat_rows"]],
        prediction_rows=[*family_one["prediction_rows"], *family_two["prediction_rows"]],
    )
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
        **artifacts,
    }

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(jsonable(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(summary), encoding="utf-8", newline="\n")

    for line in format_report(summary):
        print(line)
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    for name, path in artifacts.items():
        print(f"{name:9s}: {path}")
    return 0 if summary["criteria"]["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
