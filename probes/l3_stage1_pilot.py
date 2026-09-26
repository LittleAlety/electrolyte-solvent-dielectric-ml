"""L3 back-validation stage-1 pilot: dielectric channel, in-roster pool, EC/PC.

This probe implements the *stage-1 pilot* that
``probes/l3_backvalidation_prereg.json`` -> ``stage_1_pilot`` allows: only the
dielectric channel, only inside a pool frozen to disk before any scoring, and
only the EC / PC solvent-list champions reported.

It is **not** the L3 verdict and must never be quoted as one.  Every artifact it
writes carries the label ``stage_1_pilot_not_a_verdict``.  The pre-registration's
real decision is written over four channels and four champions; the full run is
a separate, larger job.  In particular ``criteria.C3_negative_control`` is NOT
executed here, and the redox channel that owns ``criteria.C2_additive`` is NOT
executed here.

Frozen recipe -- nothing below is new:

* target transform, inverse transform, and the equal-weight ensemble
  (``0.5 * (morgan_raw + physical_raw)``, averaged *after* each component has
  been inverse-transformed back to raw epsilon):
  ``probes/dielectric_target_and_scaffold.py`` (``transform_target``,
  ``inverse_target``, ``fit_predict``).
* XGBoost parameters, the Morgan **count** fingerprint (radius 2, 2048) and the
  13 physical columns: ``probes/dielectric_representation_ablation.py``.
* fold geometry and seed scheme:
  ``probes/dielectric_leave_ec_out_sensitivity.py`` -- the precedent that
  ``fold_and_seed.fold_policy`` names.  ``RepeatedKFold(n_splits=5,
  n_repeats=10, random_state=42)``; ``seed = 42 + global split index``; a
  champion leaves every *training* side but is still scored out-of-fold at its
  original fold.
* applicability gate: ``src/electrolyte_ml/applicability.py``.

Every artifact this probe writes is LF-only, so the recorded ``pool_sha256`` is
simultaneously the raw-byte digest and the canonical (line-ending normalised)
digest, and the freeze is auditable from the file alone.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    REPRESENTATIONS,
    SEED,
    evaluate_repeat,
    morgan_count_features,
    physical_feature_matrix,
    read_csv_rows,
    read_modelling_rows,
)
from dielectric_target_and_scaffold import fit_predict
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.applicability import applicability_domain, count_hbond_donors
from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
FROZEN_TABLE_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
FROZEN_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
ANCHOR_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "v032_target_scaffold_summary.json"
ANCHOR_ABLATION_PATH = REPOSITORY_ROOT / "probes" / "v032_ablation_summary.json"
ANCHOR_PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "v032_target_scaffold_predictions.csv"
)
ANCHOR_ABLATION_PREDICTIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "v032_ablation_predictions.csv"
)

POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
DETAIL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_detail.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json"

PILOT_LABEL = "stage_1_pilot_not_a_verdict"
POOL_LIST_NAME = "solvent"
READOUT_MODE = "log_epsilon_minus_one"
READOUT_REPRESENTATION = "Morgan+Physical"
TARGET_MODES = ("raw", "log_epsilon_minus_one")
METRIC_NAMES = (
    "mae",
    "rmse",
    "r2",
    "spearman",
    "auc_gt15",
    "auc_gt30",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
)
ANCHOR_TOLERANCE = 1e-9
ANCHOR_CROSSCHECK_TOLERANCE = 1e-6
FOLD_AGGREGATION = "mean_over_the_10_out_of_fold_repeat_predictions"

CHAMPION_LITERALS = {
    "EC": ("ethylene carbonate", "KMTRUDSVKNLOMY-UHFFFAOYSA-N"),
    "PC": ("propylene carbonate", "RUOJZAUFBMNUDX-UHFFFAOYSA-N"),
    "FEC": ("fluoroethylene carbonate", "SBLRHMKNNHXPHG-UHFFFAOYSA-N"),
    "VC": ("vinylene carbonate", "VAYTZRYEBVHVLE-UHFFFAOYSA-N"),
}
POOL_COLUMNS = (
    "list",
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "target_dielectric",
    "model_ready",
    "is_champion",
    "champion_short",
    "pilot_label",
)
DETAIL_COLUMNS = (
    "list",
    "inchikey",
    "name",
    "smiles",
    "target_dielectric",
    "predicted_dielectric",
    "domain_flag",
    "donor_count",
    "is_champion",
    "champion_short",
    "rank",
    "in_top20",
    "n_repeats",
    "fold_aggregation",
    "delta_log10_vs_truth",
    "abs_delta_log10_vs_truth",
    "pilot_label",
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_csv_lf(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write a CSV with LF line endings (the repository's ``eol=lf`` rule)."""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _write_text(path, buffer.getvalue())


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_prereg() -> dict:
    payload = _read_json(PREREG_PATH)
    if payload.get("status") != "LOCKED":
        raise ValueError("the L3 back-validation pre-registration is not LOCKED")
    if payload["stage_1_pilot"]["allowed"] is not True:
        raise ValueError("the pre-registration does not allow a stage-1 pilot")
    return payload


def locked_constants(prereg: Mapping[str, object]) -> dict[str, object]:
    """The seven locked numbers plus the locked pass expression, read verbatim."""

    criteria = prereg["criteria"]
    return {
        "C1_K": criteria["C1_recall_at_K"]["K"],
        "C1_champions_required_in_top_k_total": criteria["C1_recall_at_K"][
            "champions_required_in_top_k_total"
        ],
        "C2_solvent_max_abs_delta_log10_epsilon": criteria["C2_magnitude_solvent"][
            "max_abs_delta_log10_epsilon"
        ],
        "C2_additive_max_abs_delta_ev": criteria["C2_additive"]["max_abs_delta_ev"],
        "C3_permutation_seed": criteria["C3_negative_control"]["permutation_seed"],
        "C3_max_champion_hits": criteria["C3_negative_control"]["max_champion_hits"],
        "min_scored_per_list": prereg["pool_rule"]["min_scored_per_list"],
        "pass_expression": criteria["pass_expression"],
    }


def champion_specs(prereg: Mapping[str, object]) -> dict[str, dict[str, object]]:
    specs: dict[str, dict[str, object]] = {}
    champion_set = prereg["champion_set"]
    for item in [*champion_set["solvent_list"], *champion_set["additive_list"]]:
        short = str(item["short"])
        name, inchikey = CHAMPION_LITERALS[short]
        if item["name"] != name or item["inchikey"] != inchikey:
            raise ValueError(f"pre-registered champion drifted for {short}")
        specs[short] = {
            "short": short,
            "name": item["name"],
            "inchikey": item["inchikey"],
            "truth_dielectric": float(item["truth_dielectric"]),
            "truth_T_K": float(item["truth_T_K"]),
            "model_ready": bool(item["model_ready"]),
            "already_withheld_from_dielectric_fit": bool(
                item["already_withheld_from_dielectric_fit"]
            ),
            "list": POOL_LIST_NAME if short in ("EC", "PC") else "additive",
        }
    return specs

def build_pool(
    prereg: Mapping[str, object],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, dict[str, object]],
]:
    """Return (pool rows, modelling rows, failed, withheld, champion specs).

    The pool is the *in-roster* one the pre-registration's blocking item 3
    allows as the fallback ("pool limited to the roster, declared as such").
    It is exactly the rows the frozen recipe can actually score: ``model_ready``
    is true and the xTB physical-feature step succeeded.  Order is the frozen
    236-row order, so a pool row index is also the anchor's ``row_index``.
    """

    modelling_rows, failed_rows, withheld_rows = read_modelling_rows(FROZEN_FEATURES_PATH)
    specs = champion_specs(prereg)
    by_inchikey = {str(spec["inchikey"]): spec for spec in specs.values()}
    frozen_table = {row["inchikey"]: row for row in read_csv_rows(FROZEN_TABLE_PATH)}
    pool_rows: list[dict[str, str]] = []
    for row in modelling_rows:
        inchikey = row["inchikey"]
        if inchikey not in frozen_table:
            raise ValueError(f"modelling row {inchikey} is absent from the frozen table")
        if float(frozen_table[inchikey]["dielectric"]) != float(row["dielectric"]):
            raise ValueError(f"frozen-table dielectric drifted for {inchikey}")
        spec = by_inchikey.get(inchikey)
        pool_rows.append(
            {
                "list": POOL_LIST_NAME,
                "inchikey": inchikey,
                "name": row["name"],
                "smiles": row["smiles"],
                "T_K": row["T_K"],
                "target_dielectric": row["dielectric"],
                "model_ready": "true",
                "is_champion": "true" if spec is not None else "false",
                "champion_short": str(spec["short"]) if spec is not None else "",
                "pilot_label": PILOT_LABEL,
            }
        )
    return pool_rows, modelling_rows, failed_rows, withheld_rows, specs


def freeze_pool(
    pool_rows: Sequence[Mapping[str, object]],
    *,
    require_existing: bool,
) -> dict[str, object]:
    """Freeze the pool to disk *before* any scoring, and hash what is on disk.

    ``sha256`` is simultaneously the raw-byte digest and the canonical
    (line-ending normalised) digest; the two agreeing is the proof that the file
    is LF-only, so the freeze cannot be argued about after the fact.
    """

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=POOL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(pool_rows)
    text = buffer.getvalue()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existed = POOL_PATH.is_file()
    if existed:
        on_disk = hashlib.sha256(POOL_PATH.read_bytes()).hexdigest()
        if on_disk != digest:
            raise ValueError(
                "the frozen pool on disk differs from the pool rebuilt from the frozen "
                "roster; refusing to score against a drifted pool"
            )
    elif require_existing:
        raise ValueError(
            "no frozen pool on disk: run --freeze-pool-only first, then score"
        )
    else:
        _write_text(POOL_PATH, text)
    raw_digest = sha256_file(POOL_PATH)
    canonical_digest = canonical_text_sha256(POOL_PATH)
    if not raw_digest == canonical_digest == digest:
        raise ValueError(
            "the pool file is not LF-only, so its digest is line-ending dependent"
        )
    stat = POOL_PATH.stat()
    return {
        "path": portable_relative_path(POOL_PATH, root=REPOSITORY_ROOT),
        "sha256": digest,
        "sha256_raw_bytes": raw_digest,
        "sha256_canonical_text": canonical_digest,
        "rows": len(pool_rows),
        "size_by_list": {POOL_LIST_NAME: len(pool_rows)},
        "line_ending": "LF",
        "frozen_before_scoring": True,
        "frozen_in_this_invocation": not existed,
        "pre_existing_on_disk": existed,
        "mtime_utc": datetime.datetime.fromtimestamp(
            stat.st_mtime, datetime.UTC
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": list(POOL_COLUMNS),
        "rule": (
            "rule 5 of pool_rule.requirements: the pool is frozen to a file and its "
            "sha256 recorded before the first scoring call"
        ),
    }


def fold_geometry(row_count: int) -> list[dict[str, object]]:
    """The frozen fold geometry: ``RepeatedKFold`` seeds keyed by split index."""

    splitter = RepeatedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    geometry: list[dict[str, object]] = []
    for split_index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(row_count))
    ):
        geometry.append(
            {
                "split_index": split_index,
                "fold": split_index % N_SPLITS,
                "repeat": split_index // N_SPLITS,
                "seed": SEED + split_index,
                "train_indices": train_indices,
                "test_indices": test_indices,
            }
        )
    if len(geometry) != N_SPLITS * N_REPEATS:
        raise ValueError("unexpected RepeatedKFold geometry length")
    return geometry


def out_of_fold_predictions(
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    target_mode: str,
    representation: str,
    geometry: Sequence[Mapping[str, object]],
    excluded_indices: Sequence[int] = (),
) -> tuple[np.ndarray, dict[int, int]]:
    """Out-of-fold predictions through the frozen ``fit_predict`` code path.

    ``excluded_indices`` are dropped from the *training* side of every fold only;
    each of them is still scored out-of-fold at its original fold.  That is the
    ``fold_and_seed.fold_policy`` the leave-EC-out precedent establishes.
    """

    row_count = len(target)
    excluded = np.asarray(sorted({int(index) for index in excluded_indices}), dtype=int)
    oof = np.full((N_REPEATS, row_count), np.nan)
    removals = {int(index): 0 for index in excluded}
    for split in geometry:
        train_indices = np.asarray(split["train_indices"], dtype=int)
        test_indices = np.asarray(split["test_indices"], dtype=int)
        if excluded.size:
            drop = np.isin(train_indices, excluded)
            for index in train_indices[drop]:
                removals[int(index)] += 1
            train_indices = train_indices[~drop]
        prediction = fit_predict(
            representation,
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train_indices,
            test_indices=test_indices,
            target_mode=target_mode,
            seed=int(split["seed"]),
        )
        oof[int(split["repeat"]), test_indices] = prediction
    if not np.isfinite(oof).all():
        raise ValueError(
            f"incomplete out-of-fold predictions for {target_mode}/{representation}"
        )
    return oof, removals

def regression_anchor(
    *,
    keys: Sequence[str],
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    geometry: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Reproduce the frozen benchmark on the full roster with no exclusion.

    This is the correctness proof for everything that follows: same frozen
    ``fit_predict`` call, same folds, same seeds.

    Primary reference: ``probes/v032_target_scaffold_summary.json`` together with
    ``data/processed/v032_target_scaffold_predictions.csv`` -- the pipeline this
    probe actually calls.  Cross-reference:
    ``probes/v032_ablation_summary.json``.  The two frozen artifacts disagree
    with *each other* by up to ~5.3e-8 on raw Morgan+Physical, because the older
    ablation runner ensembles its two components a float32 rounding step
    differently; a single 1e-9 tolerance therefore cannot cover both.  Exact
    alignment is required against the primary, and the cross-reference is
    reported with its own measured spread instead of being quietly absorbed.
    """

    anchor_summary = _read_json(ANCHOR_SUMMARY_PATH)
    anchor_ablation = _read_json(ANCHOR_ABLATION_PATH)
    frozen_random = anchor_summary["summary"]["random_repeated_kfold"]
    frozen_ablation = anchor_ablation["summary"]
    frozen_predictions = {
        (
            row["target_mode"],
            row["representation"],
            int(row["fold_or_repeat"]),
            int(row["row_index"]),
        ): row["prediction"]
        for row in read_csv_rows(ANCHOR_PREDICTIONS_PATH)
        if row["strategy"] == "random_repeated_kfold"
    }
    if not frozen_predictions:
        raise ValueError("the frozen anchor holds no random_repeated_kfold rows")
    ablation_predictions = {
        (row["representation"], int(row["repeat"]), row["inchikey"]): float(
            row["prediction"]
        )
        for row in read_csv_rows(ANCHOR_ABLATION_PREDICTIONS_PATH)
    }
    mutual_spread = max(
        abs(
            float(frozen_random["raw"][representation][metric]["mean"])
            - float(frozen_ablation[representation][metric]["mean"])
        )
        for representation in REPRESENTATIONS
        for metric in METRIC_NAMES
    )

    arms: dict[str, object] = {}
    row_values_compared = 0
    row_mismatches: list[str] = []
    max_abs_metric_diff = 0.0
    max_abs_crosscheck_diff = 0.0
    ablation_row_max_abs_diff = 0.0
    for target_mode in TARGET_MODES:
        for representation in REPRESENTATIONS:
            oof, _ = out_of_fold_predictions(
                morgan=morgan,
                physical=physical,
                target=target,
                target_mode=target_mode,
                representation=representation,
                geometry=geometry,
            )
            repeat_metrics = [
                evaluate_repeat(target, oof[repeat]) for repeat in range(N_REPEATS)
            ]
            # The frozen summariser averages per-repeat metrics that it first wrote
            # out as f"{value:.12g}", so exact alignment needs the same rounding.
            mine = {
                metric: float(
                    np.mean([float(f"{row[metric]:.12g}") for row in repeat_metrics])
                )
                for metric in METRIC_NAMES
            }
            reference = {
                metric: float(frozen_random[target_mode][representation][metric]["mean"])
                for metric in METRIC_NAMES
            }
            diff_vs_target_scaffold = {
                metric: abs(mine[metric] - reference[metric]) for metric in METRIC_NAMES
            }
            primary_max = max(diff_vs_target_scaffold.values())
            max_abs_metric_diff = max(max_abs_metric_diff, primary_max)

            crosscheck = None
            if target_mode == "raw":
                diff_vs_ablation = {
                    metric: abs(
                        mine[metric] - float(frozen_ablation[representation][metric]["mean"])
                    )
                    for metric in METRIC_NAMES
                }
                crosscheck_max = max(diff_vs_ablation.values())
                max_abs_crosscheck_diff = max(max_abs_crosscheck_diff, crosscheck_max)
                crosscheck = {
                    "reference": "probes/v032_ablation_summary.json",
                    "abs_diff": diff_vs_ablation,
                    "max_abs_diff": crosscheck_max,
                    "within_tolerance": crosscheck_max <= ANCHOR_CROSSCHECK_TOLERANCE,
                }
                for repeat in range(N_REPEATS):
                    for row_index, inchikey in enumerate(keys):
                        ablation_value = ablation_predictions.get(
                            (representation, repeat, inchikey)
                        )
                        if ablation_value is None:
                            raise ValueError(
                                f"the ablation anchor misses {representation}/{repeat}/{inchikey}"
                            )
                        ablation_row_max_abs_diff = max(
                            ablation_row_max_abs_diff,
                            abs(float(oof[repeat, row_index]) - ablation_value),
                        )

            for repeat in range(N_REPEATS):
                for row_index in range(len(target)):
                    row_values_compared += 1
                    expected = frozen_predictions.get(
                        (target_mode, representation, repeat, row_index)
                    )
                    actual = f"{oof[repeat, row_index]:.12g}"
                    if expected != actual and len(row_mismatches) < 8:
                        row_mismatches.append(
                            f"{target_mode}/{representation}/repeat{repeat}/row{row_index}: "
                            f"frozen={expected!r} mine={actual!r}"
                        )
            arms[f"{target_mode}::{representation}"] = {
                "target_mode": target_mode,
                "representation": representation,
                "primary_reference": "probes/v032_target_scaffold_summary.json",
                "mine": mine,
                "frozen": reference,
                "abs_diff_vs_target_scaffold": diff_vs_target_scaffold,
                "max_abs_diff": primary_max,
                "aligned": primary_max <= ANCHOR_TOLERANCE,
                "ablation_crosscheck": crosscheck,
            }

    aligned = (
        max_abs_metric_diff <= ANCHOR_TOLERANCE
        and max_abs_crosscheck_diff <= ANCHOR_CROSSCHECK_TOLERANCE
        and not row_mismatches
    )
    return {
        "status": "aligned" if aligned else "mismatch",
        "tolerance_abs": ANCHOR_TOLERANCE,
        "crosscheck_tolerance_abs": ANCHOR_CROSSCHECK_TOLERANCE,
        "max_abs_metric_diff": max_abs_metric_diff,
        "max_abs_crosscheck_diff_vs_ablation": max_abs_crosscheck_diff,
        "ablation_row_level_max_abs_diff": ablation_row_max_abs_diff,
        "frozen_anchor_mutual_spread": mutual_spread,
        "row_values_compared": row_values_compared,
        "row_value_mismatches": row_mismatches,
        "no_champion_excluded_here": True,
        "metric_aggregation": (
            "per-repeat metrics are rounded to 12 significant digits before averaging, "
            "which is the frozen summariser's own convention (_run_random_cv writes "
            'f\"{value:.12g}\" rows and _summarize averages those)'
        ),
        "row_level_alignment": (
            "every stored OOF prediction string in "
            "data/processed/v032_target_scaffold_predictions.csv (6 arms x 236 rows x 10 "
            "repeats) is reproduced character for character"
        ),
        "anchor_disagreement_note": (
            "probes/v032_target_scaffold_summary.json and probes/v032_ablation_summary.json "
            "disagree with each other on raw Morgan+Physical by up to the mutual spread "
            "recorded here; this probe reproduces the former exactly and the latter only to "
            "that spread, so the two are never merged into one tolerance"
        ),
        "references": {
            "probes/v032_target_scaffold_summary.json": canonical_text_sha256(
                ANCHOR_SUMMARY_PATH
            ),
            "probes/v032_ablation_summary.json": canonical_text_sha256(ANCHOR_ABLATION_PATH),
            "data/processed/v032_target_scaffold_predictions.csv": canonical_text_sha256(
                ANCHOR_PREDICTIONS_PATH
            ),
            "data/processed/v032_ablation_predictions.csv": canonical_text_sha256(
                ANCHOR_ABLATION_PREDICTIONS_PATH
            ),
        },
        "arms": arms,
    }


def rank_order(predictions: np.ndarray, keys: Sequence[str]) -> list[int]:
    """Descending predicted epsilon, ties broken by InChIKey ascending."""

    return sorted(
        range(len(predictions)),
        key=lambda index: (-float(predictions[index]), keys[index]),
    )


def exclusion_audit(
    *,
    geometry: Sequence[Mapping[str, object]],
    champion_indices: Mapping[str, int],
    row_count: int,
) -> dict[str, object]:
    """Prove that every champion left every training side and kept its fold."""

    excluded = set(champion_indices.values())
    per_champion = {
        short: {"train_side_removals": 0, "held_out_folds": 0}
        for short in champion_indices
    }
    min_train = row_count
    max_train = 0
    for split in geometry:
        train = {int(index) for index in split["train_indices"]}
        test = {int(index) for index in split["test_indices"]}
        train_after = train - excluded
        for short, index in champion_indices.items():
            if index in train_after:
                raise ValueError(f"{short} survived into a training side")
            if index in train:
                per_champion[short]["train_side_removals"] += 1
            if index in test:
                per_champion[short]["held_out_folds"] += 1
        min_train = min(min_train, len(train_after))
        max_train = max(max_train, len(train_after))
    for repeat in range(N_REPEATS):
        for short, index in champion_indices.items():
            held = sum(
                1
                for split in geometry
                if int(split["repeat"]) == repeat
                and index in {int(value) for value in split["test_indices"]}
            )
            if held != 1:
                raise ValueError(f"{short} is not scored exactly once in repeat {repeat}")
    return {
        "per_champion": per_champion,
        "min_train_rows_after_exclusion": min_train,
        "max_train_rows_after_exclusion": max_train,
        "split_count": len(geometry),
    }

def run_readings(
    *,
    pool_rows: Sequence[Mapping[str, str]],
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    geometry: Sequence[Mapping[str, object]],
    specs: Mapping[str, Mapping[str, object]],
    prereg: Mapping[str, object],
) -> dict[str, object]:
    keys = [row["inchikey"] for row in pool_rows]
    solvent_specs = {
        short: spec for short, spec in specs.items() if spec["list"] == POOL_LIST_NAME
    }
    if len(solvent_specs) != 2:
        raise ValueError("the dielectric solvent list must carry exactly two champions")
    champion_indices = {
        short: keys.index(str(spec["inchikey"])) for short, spec in solvent_specs.items()
    }
    if len(set(champion_indices.values())) != len(champion_indices):
        raise ValueError("the solvent-list champions do not occupy distinct pool rows")

    criteria = prereg["criteria"]
    top_k = int(criteria["C1_recall_at_K"]["K"])
    c2_threshold = float(criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"])
    excluded = sorted(champion_indices.values())

    audit = exclusion_audit(
        geometry=geometry,
        champion_indices=champion_indices,
        row_count=len(pool_rows),
    )
    donor_counts = [count_hbond_donors(row["smiles"]) for row in pool_rows]

    readouts: dict[str, object] = {}
    detail_rows: list[dict[str, object]] = []
    for target_mode, role in (
        (READOUT_MODE, "locked_readout"),
        ("raw", "diagnostic_only_not_the_locked_readout"),
    ):
        oof, removals = out_of_fold_predictions(
            morgan=morgan,
            physical=physical,
            target=target,
            target_mode=target_mode,
            representation=READOUT_REPRESENTATION,
            geometry=geometry,
            excluded_indices=excluded,
        )
        aggregated = oof.mean(axis=0)
        order = rank_order(aggregated, keys)
        rank = {index: position + 1 for position, index in enumerate(order)}
        champion_rows: dict[str, dict[str, object]] = {}
        for short, index in champion_indices.items():
            spec = solvent_specs[short]
            predicted = float(aggregated[index])
            truth = float(spec["truth_dielectric"])
            delta = math.log10(predicted / truth)
            champion_rows[short] = {
                "short": short,
                "inchikey": spec["inchikey"],
                "pool_row_index": index,
                "rank": rank[index],
                "in_top_k": rank[index] <= top_k,
                "predicted_dielectric": predicted,
                "truth_dielectric": truth,
                "delta_log10": delta,
                "abs_delta_log10": abs(delta),
                "within_c2_tolerance": abs(delta) <= c2_threshold,
                "domain_flag": applicability_domain(
                    predicted, donor_count=donor_counts[index]
                ),
                "donor_count": donor_counts[index],
            }
        hits = sum(1 for row in champion_rows.values() if row["in_top_k"])
        readouts[target_mode] = {
            "target_mode": target_mode,
            "representation": READOUT_REPRESENTATION,
            "role": role,
            "fold_aggregation": FOLD_AGGREGATION,
            "pool_size": len(pool_rows),
            "top_k": top_k,
            "champions": champion_rows,
            "champion_hits_in_top_k": hits,
            "champions_required_here": len(champion_rows),
            "top_k_inchikeys": [keys[index] for index in order[:top_k]],
            "top_k_names": [pool_rows[index]["name"] for index in order[:top_k]],
            "training_side_removals": {str(key): value for key, value in removals.items()},
            "c1_pass_in_this_channel": hits == len(champion_rows),
            "c2_solvent_pass_in_this_channel": all(
                row["within_c2_tolerance"] for row in champion_rows.values()
            ),
        }
        if target_mode != READOUT_MODE:
            continue
        for index, key in enumerate(keys):
            predicted = float(aggregated[index])
            truth = float(pool_rows[index]["target_dielectric"])
            delta = math.log10(predicted / truth)
            detail_rows.append(
                {
                    "list": pool_rows[index]["list"],
                    "inchikey": key,
                    "name": pool_rows[index]["name"],
                    "smiles": pool_rows[index]["smiles"],
                    "target_dielectric": f"{truth:.12g}",
                    "predicted_dielectric": f"{predicted:.12g}",
                    "domain_flag": applicability_domain(
                        predicted, donor_count=donor_counts[index]
                    ),
                    "donor_count": donor_counts[index],
                    "is_champion": pool_rows[index]["is_champion"],
                    "champion_short": pool_rows[index]["champion_short"],
                    "rank": rank[index],
                    "in_top20": "true" if rank[index] <= top_k else "false",
                    "n_repeats": N_REPEATS,
                    "fold_aggregation": FOLD_AGGREGATION,
                    "delta_log10_vs_truth": f"{delta:.12g}",
                    "abs_delta_log10_vs_truth": f"{abs(delta):.12g}",
                    "pilot_label": PILOT_LABEL,
                }
            )

    locked = readouts[READOUT_MODE]
    locked_champions = locked["champions"]
    temperature_check: dict[str, dict[str, object]] = {}
    for short, index in champion_indices.items():
        spec = solvent_specs[short]
        table_temperature = float(pool_rows[index]["T_K"])
        truth_temperature = float(spec["truth_T_K"])
        temperature_check[short] = {
            "frozen_table_T_K": table_temperature,
            "prereg_truth_T_K": truth_temperature,
            "consistent": table_temperature == truth_temperature,
        }
    return {
        "readouts": readouts,
        "locked_readouts": locked,
        "exclusion_audit": audit,
        "detail_rows": detail_rows,
        "temperature_check": temperature_check,
        "champion_indices": champion_indices,
        "C1_recall_at_K": {
            "K": top_k,
            "champions_required_here_dielectric_solvent_list": len(solvent_specs),
            "champions_required_total_prereg_four_channels": int(
                criteria["C1_recall_at_K"]["champions_required_in_top_k_total"]
            ),
            "champion_ranks_in_dielectric_solvent_list": {
                short: row["rank"] for short, row in locked_champions.items()
            },
            "hits_in_dielectric_solvent_list": locked["champion_hits_in_top_k"],
            "passed_in_this_channel": locked["c1_pass_in_this_channel"],
            "top_k_inchikeys": locked["top_k_inchikeys"],
            "top_k_names": locked["top_k_names"],
            "not_a_verdict": True,
        },
        "C2_magnitude_solvent": {
            "max_abs_delta_log10_epsilon": c2_threshold,
            "champions": {
                short: {
                    "predicted_dielectric": row["predicted_dielectric"],
                    "truth_dielectric": row["truth_dielectric"],
                    "delta_log10": row["delta_log10"],
                    "abs_delta_log10": row["abs_delta_log10"],
                    "within_tolerance": row["within_c2_tolerance"],
                    "domain_flag": row["domain_flag"],
                }
                for short, row in locked_champions.items()
            },
            "passed_in_this_channel": locked["c2_solvent_pass_in_this_channel"],
            "not_a_verdict": True,
        },
        "C2_additive": {
            "status": "not_run_stage_1_pilot_redox_channel_not_executed",
            "reason": (
                "FEC / VC are additive-list champions on the redox channel; this pilot "
                "executes the dielectric channel only"
            ),
            "max_abs_delta_ev": float(criteria["C2_additive"]["max_abs_delta_ev"]),
        },
        "C3_negative_control": {
            "status": "c3_not_run_stage_1_pilot",
            "reason": "the label-permutation control belongs to the full four-channel run",
            "permutation_seed_locked": int(criteria["C3_negative_control"]["permutation_seed"]),
            "max_champion_hits_locked": int(
                criteria["C3_negative_control"]["max_champion_hits"]
            ),
        },
    }

def run_pilot(*, require_pool_on_disk: bool) -> dict[str, object]:
    prereg = read_prereg()
    locked = locked_constants(prereg)
    pool_rows, modelling_rows, failed_rows, withheld_rows, specs = build_pool(prereg)
    pool_info = freeze_pool(pool_rows, require_existing=require_pool_on_disk)
    if [row["inchikey"] for row in pool_rows] != [
        row["inchikey"] for row in modelling_rows
    ]:
        raise ValueError("pool rows and modelling rows are not index aligned")
    target = np.asarray([float(row["dielectric"]) for row in modelling_rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in modelling_rows])
    physical = physical_feature_matrix(modelling_rows)
    geometry = fold_geometry(len(pool_rows))

    anchor = regression_anchor(
        keys=[row["inchikey"] for row in pool_rows],
        morgan=morgan,
        physical=physical,
        target=target,
        geometry=geometry,
    )
    readings = run_readings(
        pool_rows=pool_rows,
        morgan=morgan,
        physical=physical,
        target=target,
        geometry=geometry,
        specs=specs,
        prereg=prereg,
    )
    detail_rows = readings.pop("detail_rows")
    write_csv_lf(DETAIL_PATH, DETAIL_COLUMNS, detail_rows)
    pool_rel = str(pool_info["path"])
    detail_rel = portable_relative_path(DETAIL_PATH, root=REPOSITORY_ROOT)
    summary_rel = portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT)

    pool_keys = {row["inchikey"] for row in pool_rows}
    additive_declaration = {
        short: {
            "inchikey": spec["inchikey"],
            "model_ready": spec["model_ready"],
            "already_withheld_from_dielectric_fit": spec[
                "already_withheld_from_dielectric_fit"
            ],
            "present_in_pool": str(spec["inchikey"]) in pool_keys,
            "extra_exclusion_needed": False,
            "note": (
                "already outside the frozen dielectric fit via model_ready=false, so no "
                "leave-one-out was performed for it"
            ),
        }
        for short, spec in specs.items()
        if spec["list"] == "additive"
    }

    summary: dict[str, object] = {
        "schema_version": 1,
        "task": "l3_stage1_pilot",
        "title": (
            "L3 back-validation stage-1 pilot (dielectric channel, in-roster pool, EC/PC)"
        ),
        "label": PILOT_LABEL,
        "not_a_verdict": True,
        "verdict_eligible": False,
        "generated_at_utc": datetime.datetime.now(datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "status": prereg["status"],
            "locked_at_utc": prereg["locked_at_utc"],
            "sha256": canonical_text_sha256(PREREG_PATH),
            "locked_constants_read_verbatim": locked,
        },
        "pilot_scope": {
            "channels_run": ["dielectric"],
            "channels_not_run": ["redox", "homo_lumo", "viscosity"],
            "lists_run": [POOL_LIST_NAME],
            "champions_reported": ["EC", "PC"],
            "pool_limited_to_roster": True,
            "roster_limitation_declaration": (
                "the repository has no SMILES->epsilon entry point, so per the "
                "pre-registration's blocking item 3 the pool is limited to the frozen "
                "roster and the limitation is declared rather than hidden; no xTB or new "
                "prediction entry point was built"
            ),
        },
        "pool": pool_info,
        "pool_rule_runtime_fill": {
            "pool_path": pool_info["path"],
            "pool_sha256": pool_info["sha256"],
            "pool_size_by_list": pool_info["size_by_list"],
            "pool_frozen_before_scoring": True,
            "additive_list_scored": 0,
            "additive_list_note": (
                "the additive list belongs to the redox channel, which this pilot does "
                "not execute; it is deliberately absent from pool_size_by_list so the "
                "frozen >= min_scored_per_list floor is never asserted over an unscored list"
            ),
            "amendment": {
                "kind": "runtime_field_fill_only",
                "locked_values_unchanged": True,
                "locked_values_touched": [],
            },
        },
        "fold_and_seed": {
            "fold_source": "data/processed/v032_ablation_predictions.csv",
            "fold_scheme": "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)",
            "seed_scheme": "42 + global RepeatedKFold split index",
            "fold_policy_precedent": "probes/dielectric_leave_ec_out_sensitivity.py",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
            "split_count": len(geometry),
        },
        "readout_recipe": {
            "ranking_readout": (
                f"representation={READOUT_REPRESENTATION}, target_mode={READOUT_MODE}"
            ),
            "ensemble": (
                "0.5 * (morgan_raw + physical_raw); each component is inverse-transformed "
                "back to raw epsilon first"
            ),
            "prediction_clip": "clipped to dielectric >= 1",
            "direction": "higher predicted epsilon ranks first",
            "tie_break": "InChIKey ascending",
            "fold_aggregation": FOLD_AGGREGATION,
            "features": (
                "Morgan count fingerprint (radius 2, 2048) plus the 13 frozen physical columns"
            ),
            "model": "XGBRegressor with the frozen XGB_PARAMS",
            "applicability_gate": (
                "src/electrolyte_ml/applicability.py: pred < 1 -> outside_nonphysical; "
                "donor_count >= 1 -> outside_associated_liquid; else inside_domain"
            ),
        },
        "regression_anchor": anchor,
        "exclusion": {
            "levels": [
                {
                    "level": "L1",
                    "prereg": prereg["exclusion_levels"][0],
                    "implementation": (
                        "EC and PC are removed from the training side of every one of the "
                        "50 folds; they are still scored out-of-fold at their original fold"
                    ),
                },
                {
                    "level": "L2",
                    "prereg": prereg["exclusion_levels"][1],
                    "implementation": (
                        "features are the Morgan count fingerprint and the frozen physical "
                        "descriptors only; no target encoding and no champion-derived feature"
                    ),
                },
                {
                    "level": "L3",
                    "prereg": prereg["exclusion_levels"][2],
                    "implementation": (
                        "XGB_PARAMS, feature set, seeds and the no-early-stopping 200-round "
                        "schedule are all frozen before the champions are ever scored"
                    ),
                },
                {
                    "level": "L4",
                    "prereg": prereg["exclusion_levels"][3],
                    "implementation": (
                        "champions go through the same fit_predict call and the same fold "
                        "aggregation as every other pool member; the is_champion column never "
                        "reaches the scoring path"
                    ),
                },
            ],
            "audit": readings["exclusion_audit"],
            "additive_champions": additive_declaration,
            "withheld_from_frozen_fit_inchikeys": sorted(
                row["inchikey"] for row in withheld_rows
            ),
            "failed_feature_inchikeys": sorted(row["inchikey"] for row in failed_rows),
            "asymmetry_statement": (
                "only EC and PC needed an extra exclusion. FEC and VC are already outside "
                "the frozen dielectric fit (model_ready=false), so no leave-one-out was run "
                "for them. This is NOT four leave-one-outs."
            ),
        },
        "readings": {
            "C1_recall_at_K": readings["C1_recall_at_K"],
            "C2_magnitude_solvent": readings["C2_magnitude_solvent"],
            "C2_additive": readings["C2_additive"],
            "C3_negative_control": readings["C3_negative_control"],
        },
        "readouts": readings["readouts"],
        "temperature_check": readings["temperature_check"],
        "reporting_rules_compliance": [
            {
                "rule": "report per channel and per list; never merge the two lists",
                "how": "only the dielectric solvent list is reported; the additive list is declared not run",
            },
            {
                "rule": "give champion rank, K, pool size, applicability flag, prediction, truth, error, control hits",
                "how": (
                    "readings.C1_recall_at_K / C2_magnitude_solvent plus readouts[<mode>] and the detail CSV"
                ),
            },
            {
                "rule": "a hit is a hit and a miss is a miss",
                "how": (
                    "ranks are reported as integers and C1 is computed from rank <= K, with no "
                    "near-miss language"
                ),
            },
            {
                "rule": "pool size < 100 means the conclusion is only 'underpowered'",
                "how": "pool size 236 >= 100, so that clause does not trigger",
            },
        ],
        "outputs": {
            "script": "probes/l3_stage1_pilot.py",
            "pool_csv": pool_rel,
            "detail_csv": detail_rel,
            "summary_json": summary_rel,
            "report": "reports/l3_stage1_pilot.md",
            "decisions_log_section": "reports/decisions_log.md section 17",
        },
        "summary_written_after_pool": True,
    }

    label_locations = [
        path
        for path in (pool_rel, detail_rel)
        if PILOT_LABEL in (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    ]
    summary["label_locations"] = [*label_locations, summary_rel]
    conflicts = [
        {
            "id": "pool_runtime_fields_are_pinned_null_by_an_existing_guard",
            "frozen_point": (
                "tests/test_l3_backvalidation_prereg.py::"
                "test_pool_rule_carries_the_machine_readable_freeze_fields asserted the "
                "four runtime fields were still null / false"
            ),
            "pilot_requires": (
                "pool_rule.pool_path / pool_sha256 / pool_size_by_list filled and "
                "pool_frozen_before_scoring = true, so the freeze is machine-readable and "
                "the pre-registration's own requirement 5 is satisfied"
            ),
            "resolution": (
                "the four runtime fields were filled and that one guard was upgraded, never "
                "weakened: it now asserts the frozen pool is internally consistent (path "
                "exists, digest equals the file's digest, every list >= min_scored_per_list) "
                "while all seven locked constants stay re-asserted untouched"
            ),
            "more_conservative_side_taken": (
                "no locked threshold moved and the guard became stricter; the pool freeze is "
                "recorded in both the pre-registration and this summary"
            ),
        },
        {
            "id": "readout_target_vs_fold_geometry_precedent",
            "frozen_point": (
                "the leave-EC-out fold-geometry precedent only ever fitted the raw target"
            ),
            "pilot_requires": (
                "the dielectric channel's locked ranking readout is the log(epsilon-1) target, "
                "per pool_rule.solvent_list_readout and the C2_solvent rationale"
            ),
            "resolution": (
                "fold geometry (which rows land in which fold, and 42 + split index) is "
                "target-independent, so the precedent is reused verbatim and only the frozen "
                "target transform differs; the log(epsilon-1) out-of-fold metrics for the same "
                "236-row order already exist in probes/v032_target_scaffold_summary.json, and "
                "the regression anchor reproduces them"
            ),
            "more_conservative_side_taken": (
                "C1/C2 are read off the pre-registered log(epsilon-1) readout; the raw-target "
                "ranking is reported only as a clearly labelled diagnostic and never as C1"
            ),
        },
    ]
    conflicts.append(
        {
            "id": "the_two_named_frozen_anchors_disagree_with_each_other",
            "frozen_point": (
                "the task names probes/v032_target_scaffold_summary.json and "
                "probes/v032_ablation_summary.json as anchors; the two disagree with each "
                "other on raw Morgan+Physical by up to 5.28e-8 (their own per-row raw "
                "Morgan+Physical predictions differ by up to 1.9e-6, a float32 ensemble "
                "rounding step in the older ablation runner), while their Morgan and "
                "Physical arms agree to ~1e-11"
            ),
            "pilot_requires": (
                "an alignment that is tight enough to be meaningful -- a tolerance widened "
                "to cover 5e-8 would no longer detect a real regression"
            ),
            "resolution": (
                "alignment is required exactly (<= 1e-9) against v032_target_scaffold_summary"
                ".json, the artifact the frozen recipe actually calls and the one the C2 "
                "rationale cites; v032_ablation_summary.json is carried as a cross-reference "
                "with its own recorded spread and a 1e-6 bound, plus the measured per-row "
                "distance between my predictions and that pipeline"
            ),
            "more_conservative_side_taken": (
                "neither frozen number was touched and the tolerance was not silently "
                "widened; the disagreement is printed in the summary rather than absorbed"
            ),
        }
    )
    summary["conflicts_with_frozen_points"] = conflicts
    _write_json(SUMMARY_PATH, summary)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freeze-pool-only",
        action="store_true",
        help="write the pool file and stop before any scoring happens",
    )
    parser.add_argument(
        "--require-pool-on-disk",
        action="store_true",
        help="refuse to score unless the pool was already frozen in an earlier invocation",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = _parse_args()
    if args.freeze_pool_only:
        prereg = read_prereg()
        pool_rows, _, failed_rows, withheld_rows, _ = build_pool(prereg)
        pool_info = freeze_pool(pool_rows, require_existing=False)
        print(
            json.dumps(
                {
                    "label": PILOT_LABEL,
                    "pool": pool_info,
                    "failed_rows": len(failed_rows),
                    "withheld_rows": len(withheld_rows),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    summary = run_pilot(require_pool_on_disk=args.require_pool_on_disk)
    readings = summary["readings"]
    print(
        json.dumps(
            {
                "label": PILOT_LABEL,
                "not_a_verdict": True,
                "pool": {
                    "path": summary["pool"]["path"],
                    "sha256": summary["pool"]["sha256"],
                    "size_by_list": summary["pool"]["size_by_list"],
                },
                "regression_anchor": {
                    "status": summary["regression_anchor"]["status"],
                    "max_abs_metric_diff": summary["regression_anchor"][
                        "max_abs_metric_diff"
                    ],
                    "max_abs_crosscheck_diff_vs_ablation": summary["regression_anchor"][
                        "max_abs_crosscheck_diff_vs_ablation"
                    ],
                    "frozen_anchor_mutual_spread": summary["regression_anchor"][
                        "frozen_anchor_mutual_spread"
                    ],
                    "row_values_compared": summary["regression_anchor"][
                        "row_values_compared"
                    ],
                    "row_value_mismatches": summary["regression_anchor"][
                        "row_value_mismatches"
                    ],
                },
                "C1_recall_at_K": {
                    "K": readings["C1_recall_at_K"]["K"],
                    "champion_ranks": readings["C1_recall_at_K"][
                        "champion_ranks_in_dielectric_solvent_list"
                    ],
                    "hits": readings["C1_recall_at_K"][
                        "hits_in_dielectric_solvent_list"
                    ],
                    "required_here": readings["C1_recall_at_K"][
                        "champions_required_here_dielectric_solvent_list"
                    ],
                    "passed_in_this_channel": readings["C1_recall_at_K"][
                        "passed_in_this_channel"
                    ],
                },
                "C2_magnitude_solvent": {
                    "max_abs_delta_log10_epsilon": readings["C2_magnitude_solvent"][
                        "max_abs_delta_log10_epsilon"
                    ],
                    "champions": readings["C2_magnitude_solvent"]["champions"],
                    "passed_in_this_channel": readings["C2_magnitude_solvent"][
                        "passed_in_this_channel"
                    ],
                },
                "C2_additive": readings["C2_additive"]["status"],
                "C3_negative_control": readings["C3_negative_control"]["status"],
                "temperature_check": summary["temperature_check"],
                "diagnostic_raw_mode_ranks": {
                    short: row["rank"]
                    for short, row in summary["readouts"]["raw"]["champions"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())