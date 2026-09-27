"""W19-D3: the Onsager residual delta layer under grouped (structure-family) CV.

Pre-registered before this file existed: probes/w19_onsager_grouped_prereg.json,
sha256 921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839.

Why the key the plan asks for is degenerate on this pool
--------------------------------------------------------
W19-5 / D3 asks for GroupKFold by InChIKey. The frozen row-level probe is built
on data/interim/v03_features_original.csv joined to data/dielectric_v03.csv,
which yields 234 modelling rows and 234 distinct InChIKeys; the frozen probe
refuses to run unless there is exactly one row per compound. Grouping by
InChIKey therefore makes every group a singleton, so it degenerates to a plain
row-out split and cannot add out-of-group pressure. The only key in this pool
that carries real family structure is the Murcko/Butina structure family the
frozen probe already uses for its compound-cluster bootstrap: 111 groups, 76 of
them singletons, the largest holding 31 compounds.

Three readings are reported side by side and never mixed:
* structure_family - the honest out-of-family test (primary).
* inchikey - the literal reading of the plan, the registered degenerate control.
* row_level_reproduction - the frozen row-level protocol re-run along the same
  code path, both as the side-by-side baseline and as a bit-for-bit check of
  probes/dielectric_onsager_delta_summary.json.

Everything else is reused verbatim from probes/dielectric_onsager_delta_probe.py:
the Onsager closure, the arms, the feature blocks, split_metrics and
evaluate_gates. No formula is rewritten here. This probe produces no deployable
model, never touches the main scoreboard, and cites no Reaxys number.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_onsager_delta_probe import (
    ARM_NAMES,
    B_CORE_FEATURE_NAMES,
    BOOTSTRAP_METRICS,
    DATASET_PATH,
    DOMAINS,
    HIGH_PERMITTIVITY_THRESHOLD,
    INPUT_PATH,
    ONSAGER_INPUT_COLUMNS,
    ONSAGER_VERSION,
    _fit_predict,
    assert_delta_features_exclude_onsager_inputs,
    average_metrics,
    chemical_descriptor_rows,
    closure_intersection,
    core_feature_matrix,
    domain_labels,
    evaluate_gates,
    invert_delta_log,
    invert_delta_raw,
    morgan_feature_names,
    onsager_estimates,
    onsager_input_matrix,
    paired_metric_comparison,
    residual_targets,
    split_metrics,
    spread_metrics,
    structured_offset,
    structured_offset_predictions,
    write_json_lf,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    SEED,
    fit_predict_representation,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)
from dielectric_target_and_scaffold import scaffold_group_keys
from sklearn.model_selection import RepeatedKFold

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w19_onsager_grouped_prereg.json"
PREREG_SHA256 = "921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w19_onsager_grouped_summary.json"
ROW_LEVEL_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_onsager_delta_summary.json"
DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DIAGNOSTIC_ARMS = (
    "O0_onsager",
    "O1_structured_offset",
    "D0_delta_core",
    "D1_delta_core_morgan",
    "D2_delta_log",
)
PRIMARY_PAIRS = (
    ("O0_onsager", "D0_delta_core", "primary"),
    ("O0_onsager", "D1_delta_core_morgan", "primary"),
    ("O1_structured_offset", "D0_delta_core", "primary"),
    ("O1_structured_offset", "D1_delta_core_morgan", "primary"),
)
READINGS = ("row_level_reproduction", "structure_family", "inchikey")



def grouped_partitions(
    groups: Sequence[str], *, n_splits: int, n_repeats: int, seed: int
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """Shuffled round-robin group assignment; no group ever crosses a fold."""
    unique = sorted({str(group) for group in groups})
    index_of = {group: position for position, group in enumerate(unique)}
    codes = np.asarray([index_of[str(group)] for group in groups], dtype=int)
    for repeat in range(n_repeats):
        order = np.random.default_rng(seed + repeat).permutation(len(unique))
        fold_of_group = np.empty(len(unique), dtype=int)
        for position, group_index in enumerate(order):
            fold_of_group[int(group_index)] = position % n_splits
        fold_of_row = fold_of_group[codes]
        for fold in range(n_splits):
            yield (
                repeat,
                fold,
                np.flatnonzero(fold_of_row != fold),
                np.flatnonzero(fold_of_row == fold),
            )


def row_level_partitions(
    n_rows: int, *, n_splits: int, n_repeats: int, seed: int
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """The frozen RepeatedKFold, replayed through the identical constructor call."""
    splitter = RepeatedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=seed)
    for split_index, (train_block, test_block) in enumerate(splitter.split(np.zeros(n_rows))):
        yield (
            split_index // n_splits,
            split_index % n_splits,
            np.asarray(train_block, dtype=int),
            np.asarray(test_block, dtype=int),
        )


def _sign_like_frozen(values: np.ndarray) -> np.ndarray:
    """Same sign convention as the frozen probe: zero counts as positive."""
    return np.where(np.asarray(values) >= 0.0, 1.0, -1.0)


def run_reading(
    *,
    reading: str,
    partitions: Iterable[tuple[int, int, np.ndarray, np.ndarray]],
    target: np.ndarray,
    core: np.ndarray,
    morgan: np.ndarray,
    physical: np.ndarray,
    onsager: np.ndarray,
    onsager_inputs: np.ndarray,
    delta_raw: np.ndarray,
    delta_log: np.ndarray,
    domains: np.ndarray,
    assoc: np.ndarray,
    ionic: np.ndarray,
    seed: int,
) -> dict[str, object]:
    n_rows = int(target.size)
    core_morgan = np.hstack([core, morgan])
    leaky = np.hstack([core, onsager_inputs])
    core_with_logg = np.hstack([core, np.log(onsager)[:, None]])
    oof = {arm: np.full((N_REPEATS, n_rows), np.nan) for arm in ARM_NAMES}
    fold_rows: list[dict[str, object]] = []
    train_counts: list[int] = []
    for repeat, fold, train_index, test_index in partitions:
        split_id = repeat * N_SPLITS + fold
        fold_seed = seed + split_id
        train_counts.append(int(train_index.size))
        predictions: dict[str, np.ndarray] = {}
        predictions["O0_onsager"] = np.maximum(onsager[test_index], 1.0)
        offsets, _fallback_domains = structured_offset(
            delta_raw[train_index], domains[train_index]
        )
        predictions["O1_structured_offset"] = structured_offset_predictions(
            onsager[test_index], domains[test_index], offsets
        )
        direct_prediction, _ = fit_predict_representation(
            "Morgan+Physical",
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train_index,
            test_indices=test_index,
            seed=fold_seed,
        )
        predictions["R0_direct_regression"] = np.asarray(direct_prediction, dtype=np.float64)
        predictions["R1_direct_with_logg"] = _fit_predict(
            core_with_logg, target, train_index, test_index, fold_seed
        )
        predictions["D0_delta_core"] = invert_delta_raw(
            onsager[test_index],
            _fit_predict(core, delta_raw, train_index, test_index, fold_seed),
        )
        predictions["D1_delta_core_morgan"] = invert_delta_raw(
            onsager[test_index],
            _fit_predict(core_morgan, delta_raw, train_index, test_index, fold_seed),
        )
        predictions["D2_delta_log"] = invert_delta_log(
            onsager[test_index],
            _fit_predict(core, delta_log, train_index, test_index, fold_seed),
        )
        predictions["D3_delta_leaky"] = invert_delta_raw(
            onsager[test_index],
            _fit_predict(leaky, delta_raw, train_index, test_index, fold_seed),
        )
        for arm in ARM_NAMES:
            prediction = np.asarray(predictions[arm], dtype=np.float64)
            if not np.isfinite(prediction).all():
                raise ValueError(f"non-finite prediction from {arm} at split {split_id}")
            oof[arm][repeat, test_index] = prediction
            metrics = split_metrics(
                target=target[test_index],
                prediction=prediction,
                onsager=onsager[test_index],
                assoc=assoc[test_index],
                ionic=ionic[test_index],
            )
            fold_rows.append(
                {
                    "reading": reading,
                    "arm": arm,
                    "split_id": split_id,
                    "repeat": repeat,
                    "fold": fold,
                    "fold_seed": fold_seed,
                    "train_count": int(train_index.size),
                    "n_test": int(test_index.size),
                    **metrics,
                }
            )
        if split_id % N_SPLITS == 0:
            print(
                json.dumps(
                    {"reading": reading, "split_id": split_id, "repeat": repeat},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    for arm in ARM_NAMES:
        if not np.isfinite(oof[arm]).all():
            raise ValueError(f"incomplete out-of-fold predictions for {arm}")
    repeat_metrics = {
        arm: [
            split_metrics(
                target=target,
                prediction=oof[arm][repeat],
                onsager=onsager,
                assoc=assoc,
                ionic=ionic,
            )
            for repeat in range(N_REPEATS)
        ]
        for arm in ARM_NAMES
    }
    return {
        "oof": oof,
        "fold_rows": fold_rows,
        "repeat_metrics": repeat_metrics,
        "train_count_min": int(min(train_counts)),
        "train_count_max": int(max(train_counts)),
        "n_folds": len(train_counts),
    }


def domain_diagnostics(
    *, oof: dict[str, np.ndarray], target: np.ndarray, onsager: np.ndarray, domains: np.ndarray
) -> dict[str, object]:
    """Per-domain bias and residual-sign accuracy, repeat by repeat."""
    report: dict[str, object] = {}
    for arm in DIAGNOSTIC_ARMS:
        per_domain: dict[str, object] = {}
        for domain in DOMAINS:
            mask = domains == domain
            count = int(mask.sum())
            if count == 0:
                per_domain[domain] = {"n": 0}
                continue
            biases: list[float] = []
            accuracies: list[float] = []
            for repeat in range(oof[arm].shape[0]):
                prediction = oof[arm][repeat][mask]
                truth = target[mask]
                biases.append(float(np.mean(truth - prediction)))
                agree = _sign_like_frozen(truth - onsager[mask]) == _sign_like_frozen(
                    prediction - onsager[mask]
                )
                accuracies.append(float(np.mean(agree.astype(np.float64))))
            mean_prediction = oof[arm].mean(axis=0)[mask]
            per_domain[domain] = {
                "n": count,
                "mae": float(np.mean(np.abs(target[mask] - mean_prediction))),
                "bias_mean_across_repeats": float(np.mean(biases)),
                "bias_std_across_repeats": float(np.std(biases, ddof=1)),
                "sign_accuracy_mean_across_repeats": float(np.mean(accuracies)),
                "sign_accuracy_std_across_repeats": float(np.std(accuracies, ddof=1)),
            }
        report[arm] = per_domain
    return report


def domain_sign_pattern(per_domain: object, arm: str) -> str | None:
    """Do the associated and the ionic domains carry opposite residual signs?"""
    arm_report = per_domain.get(arm) if isinstance(per_domain, dict) else None
    if not isinstance(arm_report, dict):
        return None
    assoc_bias = (arm_report.get("assoc_only") or {}).get("bias_mean_across_repeats")
    ionic_bias = (arm_report.get("ionic_only") or {}).get("bias_mean_across_repeats")
    if assoc_bias is None or ionic_bias is None:
        return None
    return "opposite" if (assoc_bias > 0) != (ionic_bias > 0) else "same"


def high_permittivity_diagnostics(
    *, overall: dict[str, object], target: np.ndarray, onsager: np.ndarray
) -> dict[str, object]:
    high = target > HIGH_PERMITTIVITY_THRESHOLD
    total = int(high.sum())
    hits = int((high & (onsager > HIGH_PERMITTIVITY_THRESHOLD)).sum())
    return {
        "threshold": HIGH_PERMITTIVITY_THRESHOLD,
        "row_count": total,
        "onsager_above_threshold": hits,
        "onsager_coverage_fraction": float(hits / total) if total else None,
        "onsager_coverage_is_split_invariant": True,
        "onsager_coverage_note": (
            "Onsager is label-free and computed once outside every fold, so its "
            "coverage of the eps > 60 zone cannot depend on the splitter."
        ),
        "per_arm": {
            arm: {
                "mae_gt60": overall[arm]["mae_gt60"],
                "bias_gt60": overall[arm]["bias_gt60"],
                "spearman_gt60": overall[arm]["spearman_gt60"],
                "mae": overall[arm]["mae"],
            }
            for arm in ARM_NAMES
        },
    }


def structure_group_report(
    *, rows: Sequence[dict[str, object]], groups: Sequence[str], target: np.ndarray
) -> dict[str, object]:
    sizes = Counter(str(group) for group in groups)
    high = np.flatnonzero(target > HIGH_PERMITTIVITY_THRESHOLD)
    return {
        "n_groups": len(sizes),
        "singleton_groups": int(sum(1 for size in sizes.values() if size == 1)),
        "max_group_size": int(max(sizes.values())),
        "group_size_histogram": {
            str(size): int(count)
            for size, count in sorted(Counter(sizes.values()).items())
        },
        "gt60_members": [
            {
                "name": str(rows[index]["name"]),
                "inchikey": str(rows[index]["inchikey"]),
                "epsilon_observed": float(target[index]),
                "structure_group": str(groups[index]),
                "structure_group_size": int(sizes[str(groups[index])]),
            }
            for index in high
        ],
    }


def run_experiment(
    *,
    input_path: Path,
    dataset_path: Path,
    summary_path: Path,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = SEED,
) -> dict[str, object]:
    rows, _failed_rows, _withheld_rows = read_modelling_rows(
        input_path, dataset_path=dataset_path
    )
    keys = [row["inchikey"] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(
            "the degeneracy claim needs exactly one row per compound in this pool"
        )
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=np.float64)
    descriptors = chemical_descriptor_rows(rows)
    core = core_feature_matrix(rows, descriptors=descriptors)
    morgan = np.asarray(
        morgan_count_features([row["smiles"] for row in rows]), dtype=np.float64
    )
    physical = physical_feature_matrix(rows)
    onsager_inputs = onsager_input_matrix(rows)
    onsager = onsager_estimates(rows)
    delta_raw, delta_log = residual_targets(target, onsager)
    domains = domain_labels(descriptors)
    assoc = np.asarray([domain in ("assoc_only", "both") for domain in domains], dtype=bool)
    ionic = np.asarray([domain in ("ionic_only", "both") for domain in domains], dtype=bool)
    structure_groups = np.asarray(scaffold_group_keys([row["smiles"] for row in rows]), dtype=object)
    core_names = list(B_CORE_FEATURE_NAMES)
    morgan_names = morgan_feature_names(int(morgan.shape[1]))
    assert_delta_features_exclude_onsager_inputs(core_names)
    assert_delta_features_exclude_onsager_inputs([*core_names, *morgan_names])
    if closure_intersection([*core_names, *ONSAGER_INPUT_COLUMNS]) != sorted(ONSAGER_INPUT_COLUMNS):
        raise ValueError("the leaky diagnostic did not reproduce the whole closure")
    n_rows = len(rows)
    inchikey_groups = np.asarray(keys, dtype=object)
    readings: dict[str, object] = {}
    partitions_by_reading = {
        "row_level_reproduction": row_level_partitions(
            n_rows, n_splits=N_SPLITS, n_repeats=N_REPEATS, seed=seed
        ),
        "structure_family": grouped_partitions(
            structure_groups, n_splits=N_SPLITS, n_repeats=N_REPEATS, seed=seed
        ),
        "inchikey": grouped_partitions(
            inchikey_groups, n_splits=N_SPLITS, n_repeats=N_REPEATS, seed=seed
        ),
    }
    for reading in READINGS:
        readings[reading] = run_reading(
            reading=reading,
            partitions=partitions_by_reading[reading],
            target=target,
            core=core,
            morgan=morgan,
            physical=physical,
            onsager=onsager,
            onsager_inputs=onsager_inputs,
            delta_raw=delta_raw,
            delta_log=delta_log,
            domains=domains,
            assoc=assoc,
            ionic=ionic,
            seed=seed,
        )
    frozen_text = ROW_LEVEL_SUMMARY_PATH.read_text(encoding="utf-8")
    frozen = json.loads(frozen_text)
    reproduction_keys = ("mae", "mae_assoc", "mae_ionic", "mae_gt60", "r2", "spearman")
    reproduction_gap = 0.0
    for arm in ARM_NAMES:
        for index in range(N_REPEATS):
            for key in reproduction_keys:
                mine = float(readings["row_level_reproduction"]["repeat_metrics"][arm][index][key])
                theirs = float(frozen["per_repeat_metrics"][arm][index][key])
                reproduction_gap = max(reproduction_gap, abs(mine - theirs))
    if not np.isfinite(reproduction_gap) or reproduction_gap > 1e-9:
        raise ValueError("the row-level replay did not reproduce the frozen summary")
    summary_block: dict[str, dict[str, object]] = {}
    for reading in READINGS:
        payload = readings[reading]
        repeat_metrics = payload["repeat_metrics"]
        overall = {arm: average_metrics(repeat_metrics[arm]) for arm in ARM_NAMES}
        spread = {arm: spread_metrics(repeat_metrics[arm]) for arm in ARM_NAMES}
        gates = evaluate_gates(overall_metrics=overall)
        comparisons = [
            paired_metric_comparison(
                baseline_arm=baseline_arm,
                challenger_arm=challenger_arm,
                metric=metric,
                role=role,
                repeat_metrics=repeat_metrics,
                oof=payload["oof"],
                target=target,
                clusters=structure_groups,
                assoc=assoc,
                ionic=ionic,
                n_resamples=n_resamples,
                seed=seed,
            )
            for baseline_arm, challenger_arm, role in PRIMARY_PAIRS
            for metric in BOOTSTRAP_METRICS
        ]
        summary_block[reading] = {
            "overall_metrics": overall,
            "overall_metrics_std_across_repeats": spread,
            "gates": gates,
            "per_repeat_metrics": repeat_metrics,
            "per_fold_mae": {
                arm: [
                    float(row["mae"])
                    for row in payload["fold_rows"]
                    if row["arm"] == arm
                ]
                for arm in ARM_NAMES
            },
            "per_fold_n_test": [
                int(row["n_test"])
                for row in payload["fold_rows"]
                if row["arm"] == ARM_NAMES[0]
            ],
            "train_count_min": payload["train_count_min"],
            "train_count_max": payload["train_count_max"],
            "n_folds": payload["n_folds"],
            "domain_diagnostics": domain_diagnostics(
                oof=payload["oof"], target=target, onsager=onsager, domains=domains
            ),
            "high_permittivity": high_permittivity_diagnostics(
                overall=overall, target=target, onsager=onsager
            ),
            "paired_results": comparisons,
        }
        print(
            json.dumps(
                {"reading_done": reading, "headline_gate_passed": gates["passed"]},
                ensure_ascii=False,
            ),
            flush=True,
        )
    structure = summary_block["structure_family"]
    row_block = summary_block["row_level_reproduction"]
    control = summary_block["inchikey"]
    structure_gates = structure["gates"]
    row_gates = row_block["gates"]
    control_gates = control["gates"]
    groups_report = structure_group_report(rows=rows, groups=structure_groups, target=target)
    key_size_histogram = Counter(Counter(keys).values())
    confirmatory_arms = sorted(structure_gates["per_arm"])
    headline_arm = structure_gates["headline_arm"]
    row_pattern = {
        arm: domain_sign_pattern(row_block["domain_diagnostics"], arm)
        for arm in DIAGNOSTIC_ARMS
    }
    grouped_pattern = {
        arm: domain_sign_pattern(structure["domain_diagnostics"], arm)
        for arm in DIAGNOSTIC_ARMS
    }
    q2_preserved = all(
        row_pattern[arm] == "opposite" and grouped_pattern[arm] == "opposite"
        for arm in DIAGNOSTIC_ARMS
    )
    zone = structure["high_permittivity"]
    grouped_best_gt60 = min(float(zone["per_arm"][arm]["mae_gt60"]) for arm in confirmatory_arms)
    row_best_gt60 = min(
        float(row_block["high_permittivity"]["per_arm"][arm]["mae_gt60"])
        for arm in confirmatory_arms
    )
    coverage_zero = float(zone["onsager_coverage_fraction"] or 0.0) == 0.0
    three_questions = {
        "q1_grouped_delta_gates": {
            "reading": "structure_family",
            "grouping_key": "murcko_butina_structure_family",
            "n_groups": groups_report["n_groups"],
            "headline_arm": headline_arm,
            "headline_passed_all_five_gates": bool(structure_gates["passed"]),
            "per_arm_passed": {
                arm: bool(structure_gates["per_arm"][arm]["passed"])
                for arm in confirmatory_arms
            },
            "per_arm_failed_gates": {
                arm: list(structure_gates["per_arm"][arm]["failed_gates"])
                for arm in confirmatory_arms
            },
            "row_level_headline_arm": row_gates["headline_arm"],
            "row_level_headline_passed_all_five_gates": bool(row_gates["passed"]),
            "inchikey_control_headline_passed_all_five_gates": bool(control_gates["passed"]),
            "inchikey_control_degenerate": True,
            "verdict": (
                "delta_layer_survives_out_of_family"
                if structure_gates["passed"]
                else "delta_layer_does_not_survive_out_of_family"
            ),
        },
        "q2_domain_sign_split": {
            "row_level_pattern": row_pattern,
            "grouped_pattern": grouped_pattern,
            "row_level_domain_diagnostics": row_block["domain_diagnostics"],
            "grouped_domain_diagnostics": structure["domain_diagnostics"],
            "verdict": (
                "sign_split_preserved_out_of_family"
                if q2_preserved
                else "sign_split_not_preserved_out_of_family"
            ),
        },
        "q3_high_permittivity_zone": {
            "row_count": zone["row_count"],
            "onsager_coverage_fraction": zone["onsager_coverage_fraction"],
            "onsager_coverage_is_split_invariant": True,
            "row_level_best_confirmatory_mae_gt60": row_best_gt60,
            "grouped_best_confirmatory_mae_gt60": grouped_best_gt60,
            "grouped_bias_gt60": {
                arm: zone["per_arm"][arm]["bias_gt60"] for arm in confirmatory_arms
            },
            "gt60_members": groups_report["gt60_members"],
            "verdict": (
                "zone_still_unsolvable_out_of_family"
                if coverage_zero
                else "zone_coverage_changed"
            ),
        },
    }
    three_questions["q3_high_permittivity_zone"]["grouped_best_not_better_than_row_level"] = bool(
        grouped_best_gt60 >= row_best_gt60
    )
    frozen_sha256 = hashlib.sha256(ROW_LEVEL_SUMMARY_PATH.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "probe": "w19_onsager_grouped",
        "generated_at": datetime.now(UTC).isoformat(),
        "prereg": {
            "path": "probes/w19_onsager_grouped_prereg.json",
            "sha256": PREREG_SHA256,
            "status": "locked_before_run",
            "pre_run_amendment": (
                "row_level_reproduction was added to the pre-registration before any "
                "result existed, as the side-by-side baseline and as the bit-for-bit "
                "replay check of the frozen row-level summary"
            ),
        },
        "produces_deployable_model": False,
        "onsager_is_label_free_and_deterministic": True,
        "promotes_no_reading": True,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "reaxys_numeric_red_line": (
            "Reaxys numeric values never enter any pool, feature or deliverable; "
            "this probe cites none."
        ),
        "role": (
            "appendix evidence for the capped W18 registration plus the mechanism "
            "disclosure layer; not a promotion arm"
        ),
        "onsager_version": ONSAGER_VERSION,
        "onsager_formula": frozen["onsager_formula"],
        "registry": {
            "version": "data/dielectric_v03.csv roster (the E4 nine-member eps >= 60 list)",
            "conflict_note": (
                "the draft six self-associated protic liquids is a different roster; "
                "the two lists must never be cited across each other"
            ),
            "dataset_path": "data/dielectric_v03.csv",
            "dataset_sha256": frozen["dataset_sha256"],
            "input_path": "data/interim/v03_features_original.csv",
            "input_sha256": frozen["input_sha256"],
            "in_pool_gt60_count": len(groups_report["gt60_members"]),
            "in_pool_gt60_members": [
                f"{member['name']} {member['epsilon_observed']:.2f} ({member['inchikey']})"
                for member in groups_report["gt60_members"]
            ],
        },
        "pool": {
            "rows": n_rows,
            "distinct_inchikey": len(set(keys)),
            "failed_rows": len(_failed_rows),
            "withheld_rows": len(_withheld_rows),
            "domains": frozen["domain_counts"],
            "strata": frozen["sample_strata"],
            "inchikey_group_size_histogram": {
                str(size): int(count) for size, count in sorted(key_size_histogram.items())
            },
        },
        "structure_groups": groups_report,
        "splitter": {
            "row_level_reproduction": {
                "class": "sklearn.model_selection.RepeatedKFold",
                "n_splits": N_SPLITS,
                "n_repeats": N_REPEATS,
                "random_state": seed,
                "fold_seed_rule": "SEED + split_index",
            },
            "structure_family": {
                "key": "murcko_butina_structure_family",
                "n_groups": groups_report["n_groups"],
                "n_splits": N_SPLITS,
                "n_repeats": N_REPEATS,
                "group_assignment": (
                    "np.random.default_rng(SEED + repeat).permutation over the sorted "
                    "group order, then round-robin assignment to folds"
                ),
                "fold_seed_rule": "SEED + split_index",
            },
            "inchikey": {
                "key": "inchikey",
                "n_groups": len(set(keys)),
                "degenerate": True,
                "degenerate_reason": (
                    "234 rows carry 234 distinct InChIKeys, so every group is a "
                    "singleton and this splitter is a plain row-out split"
                ),
            },
        },
        "readings": summary_block,
        "reproduction_check": {
            "row_level_reference_path": "probes/dielectric_onsager_delta_summary.json",
            "row_level_reference_sha256": frozen_sha256,
            "keys_compared": list(reproduction_keys),
            "max_abs_difference": reproduction_gap,
            "reproduced_bit_for_bit": bool(reproduction_gap <= 1e-9),
        },
        "three_questions": three_questions,
        "limitations": [
            (
                "the pool holds 234 one-row-per-compound entries, so the plan's "
                "GroupKFold-by-InChIKey request cannot constrain anything on this pool"
            ),
            (
                "the structure family is the only non-vacuous grouping key here and it "
                "is coarser than a compound split, so its reading is a lower bound"
            ),
            (
                "76 of 111 structure groups are singletons, so most rows see the same "
                "training pool they would see under a compound-level split"
            ),
            (
                "the eps > 60 zone holds 5 rows, so its MAE is a point estimate with no "
                "meaningful interval"
            ),
            (
                "Onsager is label-free and deterministic, so its zone coverage cannot "
                "change with the splitter; only the fitted arms move"
            ),
        ],
        "honest_boundary": {
            "not_a_promotion_arm": True,
            "main_scoreboard_untouched": True,
            "frozen_baseline": 0.4091179943351143,
            "frozen_headline": 0.4766400383507876,
            "epsilon_lane_is_frozen": True,
        },
    }
    write_json_lf(summary_path, payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--summary-output", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_experiment(
        input_path=args.input,
        dataset_path=args.dataset,
        summary_path=args.summary_output,
        n_resamples=args.bootstrap,
        seed=args.seed,
    )
    gate_by_reading = {
        reading: payload["readings"][reading]["gates"]["passed"] for reading in READINGS
    }
    report = {
        "probe": payload["probe"],
        "summary_json": "probes/w19_onsager_grouped_summary.json",
        "reproduction_gap": payload["reproduction_check"]["max_abs_difference"],
        "headline_gate_passed_by_reading": gate_by_reading,
        "three_questions": {
            key: value.get("verdict") for key, value in payload["three_questions"].items()
        },
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
