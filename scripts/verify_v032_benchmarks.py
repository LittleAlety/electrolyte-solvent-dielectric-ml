"""Independently verify the v0.3.2/v0.3.3 benchmark artifacts and the model_ready gate.

The v0.3.4 correction introduced the model_ready gate: rows the dataset flags
`model_ready=false` must be absent from every fit. Two things follow from that
statement and both are checked here, straight from the committed artifacts:

1. the gate is **complete** - every compound key that appears in a benchmark
   prediction file is `model_ready=true` in `data/dielectric_v03.csv`, and the
   one withheld compound (vinylene carbonate) appears nowhere;
2. the headline numbers are **reproducible** - the per-repeat predictions
   regenerate the summary means and standard deviations for the Morgan,
   Physical and hybrid representations, on both the v0.3.2 and v0.3.3 lineages,
   and the paired controlled comparison regenerates its delta, CI and p-value.

The dataset hash each summary records is re-bound to the working tree, so a
provenance patch cannot silently move the numbers out from under the table.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
METRICS = (
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
WITHHELD_INCHIKEY = "VAYTZRYEBVHVLE-UHFFFAOYSA-N"
WITHHELD_NAME = "vinylene carbonate"

LINEAGES = {
    "v0.3.2": {
        "summary": "probes/v032_ablation_summary.json",
        "predictions": "data/processed/v032_ablation_predictions.csv",
    },
    "v0.3.3": {
        "summary": "probes/dielectric_v03_representation_ablation_summary.json",
        "predictions": (
            "data/processed/"
            "dielectric_v03_representation_ablation_predictions.csv"
        ),
    },
}
CONTROLLED_SUMMARY = "probes/v032_controlled_comparison_summary.json"
CONTROLLED_OOF = "probes/v032_controlled_comparison_repeats_oof.csv"
SCAFFOLD_SUMMARY = "probes/v032_target_scaffold_summary.json"
SCAFFOLD_PREDICTIONS = "data/processed/v032_target_scaffold_predictions.csv"
SCAFFOLD_METRICS = "data/processed/v032_target_scaffold_metrics.csv"
SCAFFOLD_FOLDS = "data/processed/v032_scaffold_folds.csv"
DATASET = "data/dielectric_v03.csv"

BASELINE_ARM = "baseline_v0.3"
AUGMENTED_ARM = "augmented_pc_ec_train_only"
# Every paired statistic the paper quotes, not just the headline R2.
CONTROLLED_METRICS = ("r2", "mae", "rmse", "spearman")
TARGET_MODES = ("raw", "log_epsilon_minus_one")
# strategy -> number of held-out groups (repeats / scaffold partitions)
SCAFFOLD_STRATEGIES = {"random_repeated_kfold": 10, "scaffold_cluster_5fold": 5}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = target - prediction
    metrics = {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "r2": float(1.0 - np.sum(error**2) / np.sum((target - np.mean(target)) ** 2)),
        "spearman": float(
            np.corrcoef(
                rankdata(target, method="average"),
                rankdata(prediction, method="average"),
            )[0, 1]
        ),
        "auc_gt15": float(roc_auc_score(target > 15.0, prediction)),
        "auc_gt30": float(roc_auc_score(target > 30.0, prediction)),
    }
    for name, mask in (
        ("mae_lt20", target < 20.0),
        ("mae_20_60", (target >= 20.0) & (target <= 60.0)),
        ("mae_gt60", target > 60.0),
    ):
        metrics[name] = float(np.mean(np.abs(error[mask]))) if np.any(mask) else math.nan
    return metrics


def _hash_binding_errors(
    root: Path,
    label: str,
    summary: Mapping[str, object],
    *,
    require_pairs: bool = True,
) -> tuple[list[str], int]:
    """Bind every recorded `<x>_path`/`<x>_sha256` pair back to the working tree.

    The summaries state which feature/exclusion/dataset file each number was
    computed from. Recomputing those digests stops a stale or substituted input
    from sitting behind an otherwise internally consistent report.
    """

    errors: list[str] = []
    bound = 0
    for key, value in summary.items():
        if isinstance(value, Mapping):
            nested_errors, nested_bound = _hash_binding_errors(
                root, f"{label}.{key}", value, require_pairs=False
            )
            errors.extend(nested_errors)
            bound += nested_bound
            continue
        if not key.endswith("_path") or not isinstance(value, str):
            continue
        digest = summary.get(key[: -len("_path")] + "_sha256")
        if not isinstance(digest, str):
            continue
        bound += 1
        target = root / value
        if not target.is_file():
            errors.append(f"{label}: {value} is missing")
            continue
        # Probes record either the raw file digest or the canonical-text digest
        # (they coincide for LF-terminated files). Accept whichever the summary
        # used, but nothing else.
        actual = sha256_file(target)
        if actual != digest and canonical_text_sha256(target) != digest:
            errors.append(f"{label}: {value} does not match its recorded sha256")
    if require_pairs and not bound:
        errors.append(f"{label}: records no path/sha256 pair to bind")
    return errors, bound


def _arm_metric(
    rows: list[dict[str, str]],
    representation: str,
    arm: str,
    repeat: int,
    metric: str,
) -> float:
    subset = [
        row
        for row in rows
        if row["representation"] == representation
        and row["arm"] == arm
        and int(row["repeat"]) == repeat
    ]
    target = np.asarray([float(row["target"]) for row in subset], dtype=float)
    prediction = np.asarray([float(row["prediction"]) for row in subset], dtype=float)
    return _metrics(target, prediction)[metric]


def verify(root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    checks: list[Check] = []
    dataset_path = root / DATASET
    dataset_rows = read_csv_rows(dataset_path)
    model_ready = {row["inchikey"]: row.get("model_ready", "") for row in dataset_rows}
    dataset_sha256 = sha256_file(dataset_path)

    # 1. Every prediction file is confined to the model_ready set.
    prediction_files = [entry["predictions"] for entry in LINEAGES.values()] + [
        CONTROLLED_OOF,
        SCAFFOLD_FOLDS,
    ]
    leaked: list[str] = []
    for relative in prediction_files:
        for row in read_csv_rows(root / relative):
            key = row["inchikey"]
            if model_ready.get(key) != "true":
                leaked.append(f"{relative}:{key}:{model_ready.get(key, 'absent')}")
    checks.append(
        Check(
            "model_ready gate completeness",
            not leaked,
            (
                f"{len(prediction_files)} prediction files confined to the "
                f"{sum(value == 'true' for value in model_ready.values())} "
                "model_ready rows"
            )
            if not leaked
            else f"non-model_ready keys in prediction files: {leaked[:5]}",
        )
    )
    checks.append(
        Check(
            "withheld compound absent",
            all(
                WITHHELD_INCHIKEY not in {row["inchikey"] for row in read_csv_rows(root / relative)}
                for relative in prediction_files
            ),
            f"{WITHHELD_NAME} ({WITHHELD_INCHIKEY}) appears in no prediction file",
        )
    )

    for lineage, entry in LINEAGES.items():
        summary = json.loads((root / entry["summary"]).read_text(encoding="utf-8"))
        prediction_rows = read_csv_rows(root / entry["predictions"])
        keys = {row["inchikey"] for row in prediction_rows}

        checks.append(
            Check(
                f"{lineage} dataset hash",
                summary.get("dataset_sha256") == dataset_sha256,
                f"{entry['summary']} records dataset_sha256={summary.get('dataset_sha256')}",
            )
        )
        checks.append(
            Check(
                f"{lineage} withheld disclosure",
                summary.get("withheld_not_model_ready_count") == 1
                and summary.get("withheld_not_model_ready_names") == [WITHHELD_NAME],
                "summary discloses exactly one withheld row",
            )
        )
        checks.append(
            Check(
                f"{lineage} fitted count",
                len(keys) == summary.get("compound_count"),
                f"{len(keys)} predicted compounds == compound_count {summary.get('compound_count')}",
            )
        )

        by_repeat: dict[tuple[str, int], dict[str, float]] = {}
        for representation in REPRESENTATIONS:
            for repeat in range(10):
                subset = [
                    row
                    for row in prediction_rows
                    if row["representation"] == representation
                    and int(row["repeat"]) == repeat
                ]
                target = np.asarray([float(row["target"]) for row in subset], dtype=float)
                prediction = np.asarray(
                    [float(row["prediction"]) for row in subset], dtype=float
                )
                by_repeat[(representation, repeat)] = _metrics(target, prediction)

        mismatches: list[str] = []
        for representation in REPRESENTATIONS:
            for metric in METRICS:
                values = [by_repeat[(representation, repeat)][metric] for repeat in range(10)]
                mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
                expected = summary["summary"][representation][metric]
                if not _close(mean, float(expected["mean"])):
                    mismatches.append(
                        f"{representation}/{metric} mean {mean:.12g} != {expected['mean']:.12g}"
                    )
                if not _close(std, float(expected["std"])):
                    mismatches.append(
                        f"{representation}/{metric} std {std:.12g} != {expected['std']:.12g}"
                    )
        checks.append(
            Check(
                f"{lineage} main benchmark reproduction",
                not mismatches,
                (
                    f"all {len(REPRESENTATIONS) * len(METRICS)} summary means and "
                    "standard deviations reproduced from the per-repeat predictions"
                )
                if not mismatches
                else mismatches[0],
            )
        )

    # 2. The controlled train-only PC/EC comparison reproduces its own statistics.
    controlled = json.loads((root / CONTROLLED_SUMMARY).read_text(encoding="utf-8"))
    oof_rows = read_csv_rows(root / CONTROLLED_OOF)
    for representation in REPRESENTATIONS:
        for metric in CONTROLLED_METRICS:
            recorded = controlled["paired_deltas"][representation][metric]
            deltas = np.asarray(
                [
                    _arm_metric(oof_rows, representation, AUGMENTED_ARM, repeat, metric)
                    - _arm_metric(oof_rows, representation, BASELINE_ARM, repeat, metric)
                    for repeat in range(10)
                ],
                dtype=float,
            )
            mean = float(np.mean(deltas))
            std = float(np.std(deltas, ddof=1))
            half_width = float(stats.t.ppf(0.975, len(deltas) - 1) * stats.sem(deltas))
            p_value = float(stats.ttest_rel(deltas, np.zeros_like(deltas)).pvalue)
            agrees = (
                _close(mean, float(recorded["delta_mean"]))
                and _close(std, float(recorded["delta_std"]))
                and _close(mean - half_width, float(recorded["delta_ci95"][0]))
                and _close(mean + half_width, float(recorded["delta_ci95"][1]))
                and _close(p_value, float(recorded["paired_t_pvalue"]))
            )
            checks.append(
                Check(
                    f"controlled comparison {representation} {metric}",
                    agrees,
                    (
                        f"delta {mean:+.6f} (recorded {float(recorded['delta_mean']):+.6f}), "
                        f"p {p_value:.6f} (recorded {float(recorded['paired_t_pvalue']):.6f})"
                    ),
                )
            )

    # 3. The scaffold/cluster holdout - the extrapolation table the paper quotes -
    #    is recomputed from its own per-prediction file, not taken on trust.
    scaffold_summary = json.loads((root / SCAFFOLD_SUMMARY).read_text(encoding="utf-8"))[
        "summary"
    ]
    scaffold_metrics = read_csv_rows(root / SCAFFOLD_METRICS)

    # The aggregation below walks the JSON that is actually present, so a
    # deleted metric or an emptied summary would simply shorten the walk and
    # still report success. Pin the exact schema - and the group count derived
    # from the held-out design - before trusting any of it.
    schema_errors: list[str] = []
    if set(scaffold_summary) != set(SCAFFOLD_STRATEGIES):
        schema_errors.append(
            f"strategy keys {sorted(scaffold_summary)} != {sorted(SCAFFOLD_STRATEGIES)}"
        )
    for strategy, modes in scaffold_summary.items():
        if set(modes) != set(TARGET_MODES):
            schema_errors.append(
                f"{strategy}: target modes {sorted(modes)} != {sorted(TARGET_MODES)}"
            )
        for target_mode, representations in modes.items():
            if set(representations) != set(REPRESENTATIONS):
                schema_errors.append(
                    f"{strategy}/{target_mode}: representations "
                    f"{sorted(representations)} != {sorted(REPRESENTATIONS)}"
                )
            for representation, metrics in representations.items():
                if set(metrics) != set(METRICS):
                    schema_errors.append(
                        f"{strategy}/{target_mode}/{representation}: metrics "
                        f"{sorted(metrics)} != {sorted(METRICS)}"
                    )
    expected_group_count = sum(
        len(REPRESENTATIONS) * len(TARGET_MODES) * groups
        for groups in SCAFFOLD_STRATEGIES.values()
    )
    observed_group_count = len(
        {(row["strategy"], row["target_mode"], row["representation"], row["fold"]) for row in scaffold_metrics}
    )
    if observed_group_count != expected_group_count:
        schema_errors.append(
            f"{observed_group_count} held-out groups != the {expected_group_count} "
            "the design implies"
        )
    checks.append(
        Check(
            "scaffold benchmark schema",
            not schema_errors,
            (
                f"{expected_group_count} held-out groups over "
                f"{len(SCAFFOLD_STRATEGIES)} strategies, every representation "
                f"carrying all {len(METRICS)} metrics"
            )
            if not schema_errors
            else schema_errors[0],
        )
    )
    scaffold_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in read_csv_rows(root / SCAFFOLD_PREDICTIONS):
        key = (
            row["strategy"],
            row["target_mode"],
            row["representation"],
            row["fold_or_repeat"],
        )
        scaffold_groups.setdefault(key, []).append(row)

    metric_keys = {
        (row["strategy"], row["target_mode"], row["representation"], row["fold"])
        for row in scaffold_metrics
    }
    group_mismatches: list[str] = []
    if set(scaffold_groups) != metric_keys:
        group_mismatches.append(
            "the prediction groups and the metric rows do not describe the same groups"
        )
    else:
        for key, subset in scaffold_groups.items():
            target = np.asarray([float(row["target"]) for row in subset], dtype=float)
            prediction = np.asarray(
                [float(row["prediction"]) for row in subset], dtype=float
            )
            recomputed = _metrics(target, prediction)
            recorded = next(
                row
                for row in scaffold_metrics
                if (row["strategy"], row["target_mode"], row["representation"], row["fold"])
                == key
            )
            for metric in METRICS:
                if not _close(recomputed[metric], float(recorded[metric])):
                    group_mismatches.append(
                        f"{key}/{metric} artifact={float(recorded[metric]):.12g} "
                        f"recomputed={recomputed[metric]:.12g}"
                    )
    checks.append(
        Check(
            "scaffold group metrics recomputation",
            not group_mismatches,
            (
                f"all {len(metric_keys) * len(METRICS)} held-out group metrics "
                "reproduced from the per-prediction file"
            )
            if not group_mismatches
            else group_mismatches[0],
        )
    )

    scaffold_mismatches: list[str] = []
    for strategy, modes in scaffold_summary.items():
        for target_mode, representations in modes.items():
            for representation, metrics in representations.items():
                for metric in metrics:
                    values = [
                        float(row[metric])
                        for row in scaffold_metrics
                        if row["strategy"] == strategy
                        and row["target_mode"] == target_mode
                        and row["representation"] == representation
                    ]
                    mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
                    expected = metrics[metric]
                    if not _close(mean, float(expected["mean"])) or not _close(
                        std, float(expected["std"])
                    ):
                        scaffold_mismatches.append(f"{strategy}/{target_mode}/{representation}/{metric}")
    checks.append(
        Check(
            "scaffold summary reproduction",
            not scaffold_mismatches,
            (
                "all scaffold summary means and standard deviations reproduced "
                "from the per-group metrics"
            )
            if not scaffold_mismatches
            else scaffold_mismatches[0],
        )
    )

    group_folds: dict[tuple[str, str], set[str]] = {}
    for row in read_csv_rows(root / SCAFFOLD_FOLDS):
        group_folds.setdefault((row["partition_seed"], row["scaffold"]), set()).add(
            row["fold"]
        )
    spanning = sorted(key for key, folds in group_folds.items() if len(folds) != 1)
    checks.append(
        Check(
            "scaffold group leakage",
            not spanning,
            (
                f"{len(group_folds)} seed/scaffold pairs each confined to one fold"
                if not spanning
                else f"{len(spanning)} scaffold groups span folds: {spanning[:3]}"
            ),
        )
    )

    recorded_hash_errors: list[str] = []
    for label, relative in (
        ("v0.3.2 ablation", LINEAGES["v0.3.2"]["summary"]),
        ("v0.3.3 ablation", LINEAGES["v0.3.3"]["summary"]),
        ("scaffold", SCAFFOLD_SUMMARY),
        ("controlled", CONTROLLED_SUMMARY),
    ):
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
        pair_errors, _bound = _hash_binding_errors(root, label, payload)
        recorded_hash_errors.extend(pair_errors)
    checks.append(
        Check(
            "recorded input hashes",
            not recorded_hash_errors,
            (
                "every input, exclusion and dataset digest in the summaries "
                "matches the working tree"
            )
            if not recorded_hash_errors
            else recorded_hash_errors[0],
        )
    )

    return {
        "passed": all(check.passed for check in checks),
        "check_count": len(checks),
        "passed_count": sum(check.passed for check in checks),
        "dataset_sha256": dataset_sha256,
        "checks": [asdict(check) for check in checks],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
