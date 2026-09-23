"""Independently verify target-transform and scaffold-split artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.ML.Cluster import Butina
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
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
SCAFFOLD_SEEDS = tuple(range(42, 47))


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = target - prediction
    target_rank = rankdata(target, method="average")
    prediction_rank = rankdata(prediction, method="average")
    result = {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "r2": float(1.0 - np.sum(error**2) / np.sum((target - np.mean(target)) ** 2)),
        "spearman": float(np.corrcoef(target_rank, prediction_rank)[0, 1]),
        "auc_gt15": float(roc_auc_score(target > 15.0, prediction)),
        "auc_gt30": float(roc_auc_score(target > 30.0, prediction)),
    }
    for name, mask in (
        ("mae_lt20", target < 20.0),
        ("mae_20_60", (target >= 20.0) & (target <= 60.0)),
        ("mae_gt60", target > 60.0),
    ):
        result[name] = float(np.mean(np.abs(error[mask]))) if np.any(mask) else math.nan
    return result


def _mean_std(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 1:
        return float(array[0]), 0.0
    return float(np.mean(array)), float(np.std(array, ddof=1))


def _independent_group_keys(smiles_values: list[str]) -> list[str]:
    scaffolds = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        scaffolds.append(
            MurckoScaffold.MurckoScaffoldSmiles(
                mol=molecule,
                includeChirality=False,
            )
        )
    acyclic_indices = [index for index, scaffold in enumerate(scaffolds) if not scaffold]
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprints = [
        generator.GetFingerprint(Chem.MolFromSmiles(smiles_values[index]))
        for index in acyclic_indices
    ]
    distances = []
    for right in range(1, len(fingerprints)):
        for left in range(right):
            distances.append(
                1.0
                - DataStructs.TanimotoSimilarity(
                    fingerprints[right],
                    fingerprints[left],
                )
            )
    clusters = Butina.ClusterData(
        tuple(distances),
        len(fingerprints),
        0.5,
        isDistData=True,
        reordering=True,
    )
    ordered_clusters = sorted(clusters, key=lambda cluster: (-len(cluster), cluster))
    acyclic_group = {
        acyclic_indices[local_index]: f"acyclic_cluster:{rank}"
        for rank, cluster in enumerate(ordered_clusters)
        for local_index in cluster
    }
    return [
        f"ring:{scaffold}" if scaffold else acyclic_group[index]
        for index, scaffold in enumerate(scaffolds)
    ]


def _independent_folds(
    group_keys: list[str],
    *,
    seed: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(group_keys):
        groups[key].append(index)
    ordered_groups = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    size_groups: dict[int, list[tuple[str, list[int]]]] = defaultdict(list)
    for item in ordered_groups:
        size_groups[len(item[1])].append(item)
    ordered: list[tuple[str, list[int]]] = []
    for size in sorted(size_groups, reverse=True):
        bucket = size_groups[size]
        random.Random(seed + size).shuffle(bucket)
        ordered.extend(bucket)
    folds: list[list[int]] = [[] for _ in range(5)]
    for _, indices in ordered:
        destination = min(range(5), key=lambda index: (len(folds[index]), index))
        folds[destination].extend(indices)
    all_indices = set(range(len(group_keys)))
    return [
        (
            np.asarray(sorted(all_indices - set(fold)), dtype=int),
            np.asarray(sorted(fold), dtype=int),
        )
        for fold in folds
    ]


def verify(root: Path) -> dict[str, object]:
    metrics_path = root / "data" / "processed" / "dielectric_target_scaffold_metrics.csv"
    predictions_path = (
        root / "data" / "processed" / "dielectric_target_scaffold_predictions.csv"
    )
    assignments_path = (
        root / "data" / "processed" / "dielectric_scaffold_folds.csv"
    )
    summary_path = root / "probes" / "dielectric_target_scaffold_summary.json"
    feature_path = root / "data" / "processed" / "dielectric_physical_features.csv"
    metric_rows = read_csv_rows(metrics_path)
    prediction_rows = read_csv_rows(predictions_path)
    assignments = read_csv_rows(assignments_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    feature_rows = [row for row in read_csv_rows(feature_path) if row["status"] != "error"]
    checks: list[Check] = []

    metric_lookup = {
        (
            row["strategy"],
            row["target_mode"],
            row["representation"],
            row["fold"],
        ): row
        for row in metric_rows
    }
    grouped_predictions: dict[
        tuple[str, str, str, str],
        list[Mapping[str, str]],
    ] = defaultdict(list)
    for row in prediction_rows:
        grouped_predictions[
            (
                row["strategy"],
                row["target_mode"],
                row["representation"],
                row["fold_or_repeat"],
            )
        ].append(row)

    checks.append(
        Check(
            "metric row count",
            len(metric_rows) == 90,
            f"expected 90, got {len(metric_rows)}",
        )
    )
    checks.append(
        Check(
            "prediction row count",
            len(prediction_rows) == 90 * 205,
            f"expected {90 * 205}, got {len(prediction_rows)}",
        )
    )

    coverage_ok = True
    coverage_detail = "each metric group covers row indices 0-204 once"
    recomputed: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for key, values in grouped_predictions.items():
        indices = sorted(int(row["row_index"]) for row in values)
        if indices != list(range(205)):
            coverage_ok = False
            coverage_detail = f"invalid coverage for {key}"
            break
        target = np.asarray([float(row["target"]) for row in values], dtype=float)
        prediction = np.asarray([float(row["prediction"]) for row in values], dtype=float)
        recomputed[key] = _metrics(target, prediction)
    checks.append(Check("prediction coverage", coverage_ok, coverage_detail))

    metric_mismatches: list[str] = []
    for key, actual in recomputed.items():
        expected = metric_lookup.get(key)
        if expected is None:
            metric_mismatches.append(f"missing metric row {key}")
            break
        for metric in METRICS:
            if not _close(actual[metric], float(expected[metric])):
                metric_mismatches.append(f"{key}/{metric}")
                break
    checks.append(
        Check(
            "metric recomputation",
            not metric_mismatches,
            metric_mismatches[0] if metric_mismatches else "all 90 metrics reproduced",
        )
    )

    summary_mismatches: list[str] = []
    for strategy, modes in summary["summary"].items():
        for target_mode, representations in modes.items():
            for representation, metrics in representations.items():
                keys = [
                    key
                    for key in recomputed
                    if key[:3] == (strategy, target_mode, representation)
                ]
                for metric in METRICS:
                    values = [recomputed[key][metric] for key in keys]
                    mean, std = _mean_std(values)
                    expected = metrics[metric]
                    if not _close(mean, float(expected["mean"])) or not _close(
                        std,
                        float(expected["std"]),
                    ):
                        summary_mismatches.append(
                            f"{strategy}/{target_mode}/{representation}/{metric}"
                        )
    checks.append(
        Check(
            "summary recomputation",
            not summary_mismatches,
            (
                summary_mismatches[0]
                if summary_mismatches
                else "all summary means and standard deviations reproduced"
            ),
        )
    )

    assignment_counts = defaultdict(int)
    scaffold_folds: dict[tuple[int, str], set[int]] = defaultdict(set)
    for row in assignments:
        partition_seed = int(row["partition_seed"])
        assignment_counts[(partition_seed, row["inchikey"])] += 1
        scaffold_folds[(partition_seed, row["scaffold"])].add(int(row["fold"]))
    fold_sizes = {seed: [0] * 5 for seed in SCAFFOLD_SEEDS}
    for row in assignments:
        fold_sizes[int(row["partition_seed"])][int(row["fold"])] += 1
    no_leakage = all(len(folds) == 1 for folds in scaffold_folds.values())
    checks.append(
        Check(
            "scaffold accounting",
            len(assignments) == 205 * len(SCAFFOLD_SEEDS)
            and all(count == 1 for count in assignment_counts.values()),
            (
                f"{len(assignments)} assignments, "
                f"{len(assignment_counts)} unique seed/compound pairs"
            ),
        )
    )
    checks.append(
        Check(
            "scaffold leakage",
            no_leakage,
            (
                f"{len(scaffold_folds)} seed/group pairs; "
                "no group spans folds"
            )
            if no_leakage
            else "at least one scaffold spans multiple folds",
        )
    )
    group_keys = _independent_group_keys([row["smiles"] for row in feature_rows])
    expected_folds = {
        seed: _independent_folds(group_keys, seed=seed) for seed in SCAFFOLD_SEEDS
    }
    expected_assignment = {
        (seed, feature_rows[index]["inchikey"]): (group_keys[index], fold)
        for seed, folds in expected_folds.items()
        for fold, (_, test_indices) in enumerate(folds)
        for index in test_indices
    }
    actual_assignment = {
        (int(row["partition_seed"]), row["inchikey"]): (
            row["scaffold"],
            int(row["fold"]),
        )
        for row in assignments
    }
    checks.append(
        Check(
            "independent scaffold reconstruction",
            actual_assignment == expected_assignment,
            "all scaffold labels and fold assignments reproduced from SMILES",
        )
    )
    checks.append(
        Check(
            "scaffold summary counts",
            summary["scaffold_cv"]["unique_scaffolds"] == len(set(group_keys))
            and summary["scaffold_cv"]["largest_scaffold_size"]
            == max(
                sum(key == group for key in group_keys)
                for group in set(group_keys)
            )
            and summary["scaffold_cv"]["fold_sizes"]
            == {str(seed): [len(test) for _, test in folds] for seed, folds in expected_folds.items()},
            "unique/max group counts and fold sizes match independent reconstruction",
        )
    )
    checks.append(
        Check(
            "input hash",
            summary["input_sha256"]
            == __import__("hashlib").sha256(feature_path.read_bytes()).hexdigest(),
            "summary input hash matches physical-feature artifact",
        )
    )
    checks.append(
        Check(
            "scaffold balance",
            {str(seed): sizes for seed, sizes in fold_sizes.items()}
            == summary["scaffold_cv"]["fold_sizes"],
            "all five partitions are balanced and match the summary",
        )
    )

    result = {
        "passed": all(check.passed for check in checks),
        "check_count": len(checks),
        "passed_count": sum(check.passed for check in checks),
        "checks": [asdict(check) for check in checks],
    }
    return result


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
