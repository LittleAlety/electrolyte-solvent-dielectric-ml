"""Exploratory probe: does the target scale (epsilon vs log epsilon) move the held-out R2?

.. warning::

   This file is explicitly **exploratory_not_promotable**.  It measures numbers
   that may not be quoted as a promoted headline; it exists to decide whether the
   pre-registered shot that follows is worth locking, exactly like
   ``dielectric_pool_expansion_diagnostic.py`` did for shot 13.  The fold count is
   deliberately reduced so the probe stays cheap, which is a second reason its
   numbers are not comparable with the 50-fold protocol.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

PROBES_DIR = Path(__file__).resolve().parent
if str(PROBES_DIR) not in sys.path:
    sys.path.insert(0, str(PROBES_DIR))
import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import dielectric_xtb_full_table_migration as migration
from dielectric_representation_ablation import read_csv_rows
from export_results_common import write_json_stable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFORMER_FEATURES_PATH = (
    v1.ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
)
COORDINATION_FEATURES_PATH = v1.ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_target_scale_explore.json"
REPRESENTATION = "Morgan+Physical"


def eps_space_fold_r2(prediction_rows: Sequence[Mapping[str, object]]) -> tuple[float, int]:
    """Mean per-fold R2 back in epsilon space for a model that fitted log(eps)."""

    buckets: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for row in prediction_rows:
        key = (int(row["repeat"]), int(row["fold"]))
        buckets.setdefault(key, []).append((float(row["target"]), float(row["prediction"])))
    scores: list[float] = []
    for _key, pairs in sorted(buckets.items()):
        truth = np.exp(np.asarray([item[0] for item in pairs], dtype=float))
        guess = np.exp(np.asarray([item[1] for item in pairs], dtype=float))
        residual = float(np.sum((truth - guess) ** 2))
        total = float(np.sum((truth - truth.mean()) ** 2))
        if total <= 0.0:
            continue
        scores.append(1.0 - residual / total)
    return float(np.mean(scores)) if scores else float("nan"), len(scores)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args(argv)

    # The reduced fold count is what makes this an exploratory probe.
    bn.N_REPEATS = max(1, int(args.repeats))
    started = time.perf_counter()

    scoreboard = v1.build_scoreboard()
    rows = list(scoreboard["rows"])
    scored = np.asarray(scoreboard["scored"], dtype=bool)
    groups = list(scoreboard["groups"])
    temperatures = np.asarray(scoreboard["temperatures"], dtype=float)
    epsilon = np.asarray(scoreboard["target"], dtype=float)
    log_epsilon = np.log(epsilon)
    everything = np.ones(len(rows), dtype=bool)
    splits = bn.build_splits(groups, score_mask=scored, train_mask=everything)
    print("folds", len(splits), "rows", len(rows))

    dipole_map = bn.dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
    lever4, _ = migration.build_physical_matrix_v04(rows, dipole_map=dipole_map)
    coordination, coordination_report = v1.coordination_matrix(
        rows, read_csv_rows(COORDINATION_FEATURES_PATH)
    )
    lever4_lever8 = np.hstack([lever4, coordination])
    print("lever8 rows covered", coordination_report["rows_with_the_block"], "/", len(rows))

    physical = np.asarray(scoreboard["physical"], dtype=float)
    morgan = np.asarray(scoreboard["morgan"], dtype=float)
    arms = (
        ("eps_hybrid", physical, epsilon, False),
        ("log_hybrid", physical, log_epsilon, True),
        ("eps_lever4", lever4, epsilon, False),
        ("log_lever4", lever4, log_epsilon, True),
        ("eps_lever4_lever8", lever4_lever8, epsilon, False),
        ("log_lever4_lever8", lever4_lever8, log_epsilon, True),
    )

    readings: dict[str, object] = {}
    for name, block, target, is_log in arms:
        clock = time.perf_counter()
        result = v1.evaluate_arm(
            name,
            morgan=morgan,
            physical=block,
            target=target,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=max(1, int(args.jobs)),
        )
        if is_log:
            r2, folds = eps_space_fold_r2(result["prediction_rows"])
        else:
            fold_rows = [row for row in result["fold_rows"] if row["representation"] == REPRESENTATION]
            r2 = float(np.mean([float(row["r2"]) for row in fold_rows]))
            folds = len(fold_rows)
        seconds = time.perf_counter() - clock
        readings[name] = {
            "r2_epsilon_space": r2,
            "folds": folds,
            "target_scale": "log" if is_log else "linear",
            "seconds": seconds,
        }
        print(name, round(r2, 6), "folds", folds, "(", round(seconds, 1), "s )", flush=True)

    payload = {
        "schema_version": 1,
        "task": "dielectric_target_scale_explore",
        "status": "exploratory_not_promotable",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fold_protocol": {"n_splits": bn.N_SPLITS, "n_repeats": bn.N_REPEATS},
        "rows": len(rows),
        "scored_rows": int(scored.sum()),
        "lever8_rows_covered": int(coordination_report["rows_with_the_block"]),
        "readings": readings,
        "wall_seconds": time.perf_counter() - started,
    }
    write_json_stable(SUMMARY_PATH, payload)
    print("wrote", SUMMARY_PATH.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
