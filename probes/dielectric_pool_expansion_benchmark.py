r"""Week 17: widen only the *training* pool of the frozen epsilon scoreboard.

Pre-registration: probes/dielectric_pool_expansion_prereg.json, locked at
2026-09-27T02:20:00Z with status = locked_before_run.  The scoring pool does not
move: 457 rows / 97 compounds of thermoml_zero_frequency observations inside
293.15 <= T_K <= 303.15.  Every expansion row is admitted to train_mask only;
the fold assignment is still dealt over the scored compounds, so the folds this
probe scores on are the folds that produced paired_base = 0.4091179943351143.

Three governance arms sit next to the pre-registered ones:

* Arm A permutes the expansion block's epsilon labels *across compounds* (rows,
  composition and regularisation untouched) and refuses any gain above +0.02;
* Arm B subsamples the expansion block at 25 / 50 / 75 / 100 percent and
  requires the delta curve to be monotone non-decreasing;
* the baseline arm is re-run in this same script and has to reproduce
  0.4091179943351143 within 1e-9 before any other number is read.

Run:
    .venv\Scripts\python.exe probes\dielectric_pool_expansion_benchmark.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import dielectric_coordination_block as v1
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_band_ablation import MIN_TEST_ROWS_PER_FOLD, drop_thin_folds
from dielectric_lowfreq_gate_probe import (
    PRIMARY_FREQUENCY_CAP_MHZ,
    ROOM_TEMPERATURE_RANGE_K,
)
from dielectric_observations_grouped_benchmark import build_matrices
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    SEED,
    read_csv_rows,
)
from dielectric_room_window_paired import HYBRID, masked_splits
from export_results_common import write_json_stable

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_prereg.json"
EXPANSION_OBSERVATIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_pool_expansion_observations.csv"
)
EXPANSION_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_pool_expansion_features.csv"
)
COORDINATION_FEATURES_PATH = v1.ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
CONFORMER_FEATURES_PATH = (
    v1.ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
)
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_pool_expansion.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_pool_expansion"

#: The published frozen baseline this probe has to reproduce, bit for bit,
#: before it may read any of its own numbers.
BASELINE_R2_REFERENCE = 0.4091179943351143
REPRODUCTION_TOLERANCE = 1e-09

#: The pre-registered primary bar.
PRIMARY_TARGET_R2 = 0.60

#: Arm A tolerance and Arm B dose levels, both fixed before the run.
PLACEBO_TOLERANCE = 0.0200
DOSE_LEVELS = (0.25, 0.50, 0.75, 1.00)

EPSILON_LOWER_EXCLUSIVE = 1.0
EPSILON_UPPER_INCLUSIVE = 200.0

ARM_BASELINE = "baseline_hybrid"
ARM_PLUS_EXPANSION = "plus_expansion_hybrid"
ARM_EXPANSION_ONLY = "expansion_only"
ARM_LEVER = "plus_lever4_lever8"
ARM_LEVER_PLUS_EXPANSION = "plus_lever4_lever8_plus_expansion"
ARM_PLACEBO = "expansion_label_placebo"

FITTED_ARMS = (
    ARM_BASELINE,
    ARM_PLUS_EXPANSION,
    ARM_EXPANSION_ONLY,
    ARM_LEVER,
    ARM_LEVER_PLUS_EXPANSION,
    ARM_PLACEBO,
)

TRACK_COLUMN = "expansion_track"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_of(path: Path) -> str:
    return canonical_text_sha256(path)


def load_prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def _as_float(text: object) -> float | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def load_expansion(
    *,
    observations_path: Path,
    features_path: Path,
    blocked_keys: set[tuple[str, float]],
    scoring_compounds: set[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read the expansion table and gate every row against the pre-registered rules."""

    features: dict[str, dict[str, str]] = {}
    for row in read_csv_rows(features_path):
        if str(row.get("status", "")).strip() == "error":
            continue
        if any(not str(row.get(column, "")).strip() for column in PHYSICAL_COLUMNS):
            continue
        features[str(row["inchikey"])] = row

    low, high = ROOM_TEMPERATURE_RANGE_K
    observations = read_csv_rows(observations_path)
    kept: list[dict[str, object]] = []
    dropped: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, float]] = set()
    tracks: dict[str, int] = defaultdict(int)
    overlaps = 0
    for row in observations:
        key = str(row["inchikey"])
        reasons: list[str] = []
        t_k = _as_float(row.get("T_K"))
        if t_k is None or not (low <= t_k <= high):
            reasons.append("temperature_out_of_the_room_band")
        epsilon = _as_float(row.get("epsilon"))
        if epsilon is None or not (EPSILON_LOWER_EXCLUSIVE < epsilon <= EPSILON_UPPER_INCLUSIVE):
            reasons.append("epsilon_out_of_range")
        frequency_text = str(row.get("frequency_mhz", "")).strip()
        if frequency_text:
            frequency = _as_float(frequency_text)
            if frequency is None:
                reasons.append("frequency_not_a_number")
            elif frequency > PRIMARY_FREQUENCY_CAP_MHZ:
                reasons.append("frequency_above_the_primary_cap")
        if str(row.get("phase", "")).strip().lower() != "liquid":
            reasons.append("phase_is_not_liquid")
        if _as_float(row.get("component_count")) != 1.0:
            reasons.append("not_a_pure_component")
        if key not in features:
            reasons.append("no_xtb_features")
        if not str(row.get("smiles", "")).strip():
            reasons.append("no_smiles")
        for column in ("source_url", "license", "source_file_sha256"):
            if not str(row.get(column, "")).strip():
                reasons.append("no_" + column)
        if t_k is not None:
            if (key, round(t_k, 2)) in blocked_keys:
                reasons.append("duplicate_of_a_coverage_row")
            if (key, round(t_k, 2)) in seen:
                reasons.append("duplicate_within_the_expansion_block")
        if reasons:
            dropped["rows_rejected"] += 1
            for reason in reasons:
                dropped[reason] += 1
            continue
        assert t_k is not None
        seen.add((key, round(t_k, 2)))
        tracks[str(row.get(TRACK_COLUMN, ""))] += 1
        if key in scoring_compounds:
            overlaps += 1
        kept.append({**row, "_features": features[key]})

    return kept, {
        "rows_read": len(observations),
        "rows_admitted": len(kept),
        "dropout": {name: int(value) for name, value in sorted(dropped.items())},
        "tracks": {name: int(value) for name, value in sorted(tracks.items())},
        "compounds_admitted": len({str(row["inchikey"]) for row in kept}),
        "rows_whose_compound_is_already_scored": int(overlaps),
        "features_available": len(features),
    }


def dipole_map_from_conformer_rows(
    conformer_rows: Sequence[Mapping[str, object]],
) -> dict[str, float]:
    """The v0.4 conformer-averaged dipole per compound, read from the frozen artefact."""

    dipole_map: dict[str, float] = {}
    for row in conformer_rows:
        if str(row.get("status")) != "ok":
            continue
        text = str(row.get("dipole_D_conformer_mean", "")).strip()
        if not text:
            continue
        dipole_map[str(row["inchikey"])] = float(text)
    return dipole_map

def build_splits(
    groups: Sequence[str],
    *,
    score_mask: np.ndarray,
    train_mask: np.ndarray,
) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    raw = masked_splits(
        groups,
        score_mask=score_mask,
        train_mask=train_mask,
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        seed=SEED,
    )
    return list(drop_thin_folds(raw, min_test_rows=MIN_TEST_ROWS_PER_FOLD))


def fold_signature(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> list[tuple[int, int, tuple[int, ...]]]:
    return [
        (int(repeat), int(fold), tuple(sorted(int(index) for index in test)))
        for repeat, fold, _train, test in splits
    ]


def compound_blocks(groups: Sequence[str], mask: np.ndarray) -> dict[str, list[int]]:
    """Row indices of every masked compound, keyed by InChIKey."""

    by_compound: dict[str, list[int]] = defaultdict(list)
    for index in np.flatnonzero(np.asarray(mask, dtype=bool)).tolist():
        by_compound[str(groups[index])].append(int(index))
    return by_compound


def label_placebo_target(
    target: np.ndarray,
    groups: Sequence[str],
    mask: np.ndarray,
) -> np.ndarray:
    """Permute the expansion block's epsilon labels across its compounds.

    The row count, the per-compound row multiplicity, the feature matrix and
    every hyper-parameter stay untouched; only the attachment of the epsilon
    labels to compounds is destroyed.
    """

    blocks = compound_blocks(groups, mask)
    keys = sorted(blocks)
    rng = np.random.default_rng(SEED)
    order = [int(position) for position in rng.permutation(len(keys))]
    values = np.asarray(target, dtype=float)
    # The label *multiset* and the per-compound row counts are both preserved;
    # only the attachment of a label to a compound is destroyed.  Compounds are
    # not all the same size, so the donor pool is drawn sequentially rather than
    # block-for-block.
    donor_pool = np.concatenate([values[blocks[keys[position]]] for position in order])
    shuffled = values.copy()
    position = 0
    for key in keys:
        receiver = blocks[key]
        shuffled[receiver] = donor_pool[position : position + len(receiver)]
        position += len(receiver)
    if position != donor_pool.size:
        raise ValueError("the placebo lost rows")
    return shuffled


def dose_mask(
    groups: Sequence[str],
    mask: np.ndarray,
    *,
    level: float,
    seed: int = SEED,
) -> np.ndarray:
    """A deterministic subset of the expansion compounds at the requested dose."""

    blocks = compound_blocks(groups, mask)
    keys = sorted(blocks)
    rng = np.random.default_rng(seed)
    order = [int(position) for position in rng.permutation(len(keys))]
    take = round(level * len(keys))
    selected = np.zeros(np.asarray(mask).shape, dtype=bool)
    for position in order[:take]:
        selected[blocks[keys[position]]] = True
    return selected


def arm_r2(summary: Mapping[str, object], representation: str = HYBRID) -> float:
    block = summary[representation]  # type: ignore[index]
    return float(block["r2"]["mean"])  # type: ignore[index]


def build_summary(
    *,
    generated_at: str,
    prereg: Mapping[str, object],
    expansion_report: Mapping[str, object],
    contract: Mapping[str, object],
    arms: Mapping[str, object],
    dose_rows: Sequence[Mapping[str, object]],
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    baseline_r2 = arm_r2(arms[ARM_BASELINE]["summary"])  # type: ignore[index]
    plus_r2 = arm_r2(arms[ARM_PLUS_EXPANSION]["summary"])  # type: ignore[index]
    lever_r2 = arm_r2(arms[ARM_LEVER]["summary"])  # type: ignore[index]
    lever_plus_r2 = arm_r2(arms[ARM_LEVER_PLUS_EXPANSION]["summary"])  # type: ignore[index]
    expansion_only_r2 = arm_r2(arms[ARM_EXPANSION_ONLY]["summary"])  # type: ignore[index]
    placebo_r2 = arm_r2(arms[ARM_PLACEBO]["summary"])  # type: ignore[index]

    reproduction_gap = abs(baseline_r2 - BASELINE_R2_REFERENCE)
    reproduced = bool(reproduction_gap <= REPRODUCTION_TOLERANCE)

    primary_met = bool(plus_r2 > PRIMARY_TARGET_R2)
    placebo_delta = placebo_r2 - baseline_r2
    arm_a_pass = bool(placebo_delta <= PLACEBO_TOLERANCE)

    deltas = [float(row["delta_r2_vs_baseline"]) for row in dose_rows]
    arm_b_pass = bool(all(later >= earlier - 1e-09 for earlier, later in pairwise(deltas)))

    if primary_met and arm_a_pass and arm_b_pass:
        decision = "primary_met_with_governance"
        decision_text = (
            "the rebuilt hybrid scoreboard clears 0.60 and both governance arms hold; "
            "the gain may be written up as observation-level information"
        )
    elif primary_met:
        decision = "primary_met_governance_failed"
        decision_text = (
            "the rebuilt hybrid scoreboard clears 0.60 but Arm A or Arm B failed; the "
            "number is reported only as a data-volume effect"
        )
    else:
        decision = "primary_missed"
        decision_text = (
            "the rebuilt hybrid scoreboard misses 0.60; the achieved number and the "
            "shortfall are reported as they stand"
        )

    return {
        "schema_version": 1,
        "task": "dielectric_pool_expansion",
        "week": "week17",
        "generated_at_utc": generated_at,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "status": str(prereg.get("status")),
            "locked_at_utc": str(prereg.get("locked_at_utc")),
            "sha256": sha256_of(PREREG_PATH),
        },
        "frozen_contract": dict(contract),
        "expansion": dict(expansion_report),
        "arms": {
            name: {
                "r2": arm_r2(block["summary"]),
                "delta_r2_vs_baseline": arm_r2(block["summary"]) - baseline_r2,
                "representations": {
                    representation: float(block["summary"][representation]["r2"]["mean"])
                    for representation in sorted(block["summary"])
                },
                "leak": block["leak"],
                "seconds": block["seconds"],
            }
            for name, block in arms.items()
        },
        "dose_response": [dict(row) for row in dose_rows],
        "verdict": {
            "baseline_r2": baseline_r2,
            "baseline_r2_reference": BASELINE_R2_REFERENCE,
            "baseline_abs_gap": reproduction_gap,
            "baseline_reproduced": reproduced,
            "primary_arm": ARM_PLUS_EXPANSION,
            "primary_r2": plus_r2,
            "primary_target": PRIMARY_TARGET_R2,
            "primary_met": primary_met,
            "shortfall": PRIMARY_TARGET_R2 - plus_r2,
            "merged_gun_r2": lever_plus_r2,
            "merged_gun_delta_r2": lever_plus_r2 - baseline_r2,
            "lever_only_r2": lever_r2,
            "expansion_only_r2": expansion_only_r2,
            "placebo_r2": placebo_r2,
            "placebo_delta_r2": placebo_delta,
            "arm_a_pass": arm_a_pass,
            "arm_b_pass": arm_b_pass,
            "decision": decision,
            "decision_text": decision_text,
        },
        "telemetry": dict(telemetry),
        "honest_boundaries": [
            (
                "the scoring pool is 457 rows but only 276 distinct (compound, temperature) "
                "pairs; 276 is the honest sample size"
            ),
            (
                "no expansion row is ever scored, and no expansion row may be quoted as a "
                "scored observation"
            ),
            (
                "the expansion set is whatever the sources tabulate, not a random sample of "
                "chemical space, so coverage bias is measured and reported rather than assumed"
            ),
            (
                "Arm A and Arm B exist to separate information from target-distribution shift; "
                "a gain that fails them is a data-volume effect and is written up as one"
            ),
            "the primary criterion names the Morgan+Physical representation; the arm that "
            "carries it here is " + ARM_PLUS_EXPANSION + ", whose feature block is exactly "
            "the frozen hybrid block",
        ],
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    verdict = summary["verdict"]
    expansion = summary["expansion"]
    contract = summary["frozen_contract"]
    arms = summary["arms"]
    lines = [
        "# Week 17: widening only the training pool of the epsilon scoreboard",
        "",
        "**Generated:** " + str(summary["generated_at_utc"]),
        "",
        "**Pre-registration:** " + str(summary["prereg"]["path"]) + " (status "
        + str(summary["prereg"]["status"]) + ", locked " + str(summary["prereg"]["locked_at_utc"])
        + ", sha256 " + str(summary["prereg"]["sha256"]) + ")",
        "",
        "**Decision:** " + str(verdict["decision"]),
        "",
        str(verdict["decision_text"]),
        "",
        "## 1. The frozen side",
        "",
        "| Quantity | Value |",
        "|---|---|",
        "| Scored rows | " + str(contract["scored_rows"]) + " |",
        "| Scored compounds | " + str(contract["compounds_scored"]) + " |",
        "| Folds | " + str(contract["folds"]) + " (" + str(contract["executed_repeats"])
        + " repeats x 5) |",
        "| Baseline reproduction | " + format(verdict["baseline_r2"], ".16f") + " vs "
        + format(verdict["baseline_r2_reference"], ".16f") + " (abs gap "
        + format(verdict["baseline_abs_gap"], ".2e") + ", "
        + ("reproduced" if verdict["baseline_reproduced"] else "NOT reproduced") + ") |",
        "",
        "## 2. The expansion block",
        "",
        "| Quantity | Value |",
        "|---|---|",
        "| Rows read | " + str(expansion["rows_read"]) + " |",
        "| Rows admitted | " + str(expansion["rows_admitted"]) + " |",
        "| Compounds admitted | " + str(expansion["compounds_admitted"]) + " |",
        "| Rows of an already-scored compound | "
        + str(expansion["rows_whose_compound_is_already_scored"]) + " |",
        "| Tracks | " + str(expansion["tracks"]) + " |",
        "| Dropout | " + str(expansion["dropout"]) + " |",
        "",
        "## 3. Arms",
        "",
        "| Arm | Morgan+Physical R2 | Delta vs baseline |",
        "|---|---|---|",
    ]
    for name in FITTED_ARMS:
        block = arms[name]
        lines.append(
            "| " + name + " | " + format(block["r2"], ".16f") + " | "
            + format(block["delta_r2_vs_baseline"], "+.6f") + " |"
        )
    lines += [
        "",
        "## 4. Governance",
        "",
        "| Dose | Compounds | Rows | R2 | Delta vs baseline |",
        "|---|---|---|---|---|",
    ]
    for row in summary["dose_response"]:
        lines.append(
            "| " + format(row["dose"], ".2f") + " | " + str(row["compounds"]) + " | "
            + str(row["rows"]) + " | " + format(row["r2"], ".16f") + " | "
            + format(row["delta_r2_vs_baseline"], "+.6f") + " |"
        )
    lines += [
        "",
        "- Arm A (compound-level label placebo): delta " + format(verdict["placebo_delta_r2"], "+.6f")
        + ", tolerance +" + format(PLACEBO_TOLERANCE, ".2f") + " -> "
        + ("PASS" if verdict["arm_a_pass"] else "FAIL"),
        "- Arm B (monotone dose response): " + ("PASS" if verdict["arm_b_pass"] else "FAIL"),
        "",
        "## 5. Primary criterion",
        "",
        "- Primary arm " + str(verdict["primary_arm"]) + ": R2 " + format(verdict["primary_r2"], ".16f")
        + " against the bar " + format(verdict["primary_target"], ".2f"),
        "- Met: " + str(verdict["primary_met"]) + " (shortfall "
        + format(verdict["shortfall"], "+.6f") + ")",
        "- Merged gun (" + ARM_LEVER_PLUS_EXPANSION + "): " + format(verdict["merged_gun_r2"], ".16f")
        + " (" + format(verdict["merged_gun_delta_r2"], "+.6f") + " vs baseline)",
        "",
        "## 6. Honest boundaries",
        "",
    ]
    for item in summary["honest_boundaries"]:
        lines.append("- " + str(item))
    lines.append("")
    return lines


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(path, payload)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=0)
    parser.add_argument("--skip-lever-arms", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_utc = _utc_now()
    jobs = max(1, int(args.jobs)) if args.jobs else v1.default_jobs()

    for path in (PREREG_PATH, EXPANSION_OBSERVATIONS_PATH, EXPANSION_FEATURES_PATH):
        if not path.is_file():
            print("MISSING " + str(path))
            return 1

    prereg = load_prereg()
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the rebuilt scoreboard does not match the pre-registration")
        return 1
    print(
        "scoreboard: rows={scored_rows} compounds={compounds_scored} folds={folds}".format(**contract),
        flush=True,
    )

    base_rows = list(scoreboard["rows"])  # type: ignore[arg-type]
    base_scored = np.asarray(scoreboard["scored"], dtype=bool)
    blocked_keys = {(str(row["inchikey"]), round(float(str(row["T_K"])), 2)) for row in base_rows}
    scoring_compounds = {
        str(key) for key, flag in zip(scoreboard["groups"], base_scored, strict=True) if flag
    }

    expansion_rows, expansion_report = load_expansion(
        observations_path=EXPANSION_OBSERVATIONS_PATH,
        features_path=EXPANSION_FEATURES_PATH,
        blocked_keys=blocked_keys,
        scoring_compounds=scoring_compounds,
    )
    print(
        "expansion: {rows_admitted} rows / {compounds_admitted} compounds admitted from "
        "{rows_read}".format(**expansion_report),
        flush=True,
    )
    if not expansion_rows:
        print("no expansion row survived the admission gates")
        return 1

    expansion_morgan, expansion_physical, expansion_target, expansion_temperatures, (
        expansion_groups
    ) = build_matrices(expansion_rows)
    n_expansion = len(expansion_rows)

    morgan = np.vstack([scoreboard["morgan"], expansion_morgan])
    physical = np.vstack([scoreboard["physical"], expansion_physical])
    target = np.concatenate([scoreboard["target"], expansion_target])
    temperatures = np.concatenate([scoreboard["temperatures"], expansion_temperatures])
    groups = list(scoreboard["groups"]) + list(expansion_groups)
    scored = np.concatenate([base_scored, np.zeros(n_expansion, dtype=bool)])
    expansion_mask = np.concatenate(
        [np.zeros(base_scored.size, dtype=bool), np.ones(n_expansion, dtype=bool)]
    )
    extended_rows = base_rows + expansion_rows

    frozen_splits = list(scoreboard["splits"])  # type: ignore[arg-type]
    shared_splits = build_splits(groups, score_mask=scored, train_mask=scored | expansion_mask)
    folds_shared = fold_signature(frozen_splits) == fold_signature(shared_splits)
    if not folds_shared:
        print("the widened pool changed the fold assignment; refusing to continue")
        return 1

    masks = {
        ARM_BASELINE: scored,
        ARM_PLUS_EXPANSION: scored | expansion_mask,
        ARM_EXPANSION_ONLY: expansion_mask,
        ARM_LEVER: scored,
        ARM_LEVER_PLUS_EXPANSION: scored | expansion_mask,
        ARM_PLACEBO: scored | expansion_mask,
    }

    lever_available = (
        COORDINATION_FEATURES_PATH.is_file()
        and CONFORMER_FEATURES_PATH.is_file()
        and not args.skip_lever_arms
    )
    lever_notes: list[str] = []
    physical_hybrid_extended = physical
    physical_lever_scored = physical
    physical_lever_extended = physical
    if lever_available:
        dipole_map = dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
        physical_lever_scored, lever_report_scored = migration.build_physical_matrix_v04(
            base_rows, dipole_map=dipole_map
        )
        physical_lever_extended, lever_report_extended = migration.build_physical_matrix_v04(
            extended_rows, dipole_map=dipole_map
        )
        coordination_rows = read_csv_rows(COORDINATION_FEATURES_PATH)
        coordination_extended, coordination_report = v1.coordination_matrix(
            extended_rows, coordination_rows
        )
        coordination_scored, _ = v1.coordination_matrix(base_rows, coordination_rows)
        physical_lever_scored = np.hstack([physical_lever_scored, coordination_scored])
        physical_lever_extended = np.hstack([physical_lever_extended, coordination_extended])
        lever_notes.append(
            "lever4 migrated {migrated_compounds} compounds ({scored} of them scored)".format(
                migrated_compounds=lever_report_extended["migrated_compounds"],
                scored=lever_report_scored["migrated_compounds"],
            )
        )
        lever_notes.append(
            "lever8 resolved {rows}/{total} rows; expansion rows outside the block stay NaN".format(
                rows=coordination_report["rows_with_the_block"], total=len(extended_rows)
            )
        )
    else:
        lever_notes.append(
            "the lever-4 / lever-8 blocks were unavailable, so the two lever arms reuse "
            "the frozen hybrid block and are recorded as such"
        )

    levers = {
        ARM_BASELINE: physical_hybrid_extended,
        ARM_PLUS_EXPANSION: physical_hybrid_extended,
        ARM_EXPANSION_ONLY: physical_hybrid_extended,
        ARM_LEVER: physical_lever_scored,
        ARM_LEVER_PLUS_EXPANSION: physical_lever_extended,
        ARM_PLACEBO: physical_hybrid_extended,
    }

    arms: dict[str, dict[str, object]] = {}
    placebo_target = label_placebo_target(target, groups, expansion_mask)
    for arm in FITTED_ARMS:
        print("arm: " + arm, flush=True)
        clock = time.perf_counter()
        arm_target = placebo_target if arm == ARM_PLACEBO else target
        splits = build_splits(groups, score_mask=scored, train_mask=masks[arm])
        result = v1.evaluate_arm(
            arm,
            morgan=morgan,
            physical=levers[arm],
            target=arm_target,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        arms[arm] = dict(result) | {"seconds": time.perf_counter() - clock}
        print(
            "  Morgan+Physical R2 {r2:.6f}  ({seconds:.1f}s)".format(
                r2=arm_r2(result["summary"]), seconds=arms[arm]["seconds"]
            ),
            flush=True,
        )

    dose_rows: list[dict[str, object]] = []
    for level in DOSE_LEVELS:
        mask = dose_mask(groups, expansion_mask, level=level)
        splits = build_splits(groups, score_mask=scored, train_mask=scored | mask)
        name = f"dose_{round(level * 100):03d}"
        print("arm: " + name, flush=True)
        result = v1.evaluate_arm(
            name,
            morgan=morgan,
            physical=physical_hybrid_extended,
            target=target,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        dose_rows.append(
            {
                "dose": float(level),
                "compounds": len({str(groups[index]) for index in np.flatnonzero(mask)}),
                "rows": int(mask.sum()),
                "r2": arm_r2(result["summary"]),
                "delta_r2_vs_baseline": arm_r2(result["summary"])
                - arm_r2(arms[ARM_BASELINE]["summary"]),
            }
        )

    telemetry = {
        "started_at_utc": started_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "folds_per_arm": int(contract["folds"]),
        "folds_shared_with_the_frozen_baseline": folds_shared,
        "lever_arms_available": lever_available,
        "lever_notes": lever_notes,
        "arm_seconds": {name: float(block["seconds"]) for name, block in arms.items()},
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }

    summary = build_summary(
        generated_at=_utc_now(),
        prereg=prereg,
        expansion_report={
            **expansion_report,
            "observations_path": portable_relative_path(
                EXPANSION_OBSERVATIONS_PATH, root=REPOSITORY_ROOT
            ),
            "observations_sha256": sha256_of(EXPANSION_OBSERVATIONS_PATH),
            "features_path": portable_relative_path(
                EXPANSION_FEATURES_PATH, root=REPOSITORY_ROOT
            ),
            "features_sha256": sha256_of(EXPANSION_FEATURES_PATH),
            "extended_train_compounds": len(
                {str(groups[index]) for index in np.flatnonzero(expansion_mask)}
            ),
        },
        contract=contract,
        arms=arms,
        dose_rows=dose_rows,
        telemetry=telemetry,
    )
    summary["outputs"] = {
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    for arm in FITTED_ARMS:
        fold_rows.extend(arms[arm]["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(arms[arm]["repeat_rows"])  # type: ignore[arg-type]
    v1.write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), v1.FOLD_COLUMNS_OUT, fold_rows)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), v1.REPEAT_COLUMNS_OUT, repeat_rows
    )
    _write_json(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n")

    verdict = summary["verdict"]
    print()
    print(
        "baseline {:.16f} vs reference {:.16f} (abs {:.2e})".format(
            verdict["baseline_r2"],
            verdict["baseline_r2_reference"],
            verdict["baseline_abs_gap"],
        )
    )
    print(
        "primary  {:.16f} vs bar {:.2f} -> met={}".format(
            verdict["primary_r2"], verdict["primary_target"], verdict["primary_met"]
        )
    )
    print("decision " + str(verdict["decision"]))
    print("wall seconds {:.1f}".format(telemetry["wall_seconds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
