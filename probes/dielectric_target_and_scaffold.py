"""Test target transforms and Murcko-scaffold generalization for dielectric v0.2."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.ML.Cluster import Butina
from sklearn.model_selection import RepeatedKFold
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from probes.dielectric_representation_ablation import (
    XGB_PARAMS,
    evaluate_repeat,
    morgan_count_features,
    physical_feature_matrix,
    read_modelling_rows,
)

SEED = 42
N_SPLITS = 5
N_REPEATS = 10
N_SCAFFOLD_PARTITIONS = 5
SCAFFOLD_SEEDS = tuple(range(SEED, SEED + N_SCAFFOLD_PARTITIONS))
TARGET_MODES = ("raw", "log_epsilon_minus_one")
REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
SUMMARY_FIELDS = (
    "strategy",
    "target_mode",
    "representation",
    "fold",
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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def transform_target(target: np.ndarray, mode: str) -> np.ndarray:
    target = np.asarray(target, dtype=float)
    if mode == "raw":
        return target
    if mode == "log_epsilon_minus_one":
        if np.any(target <= 1.0):
            raise ValueError("log(epsilon - 1) requires epsilon > 1")
        return np.log(target - 1.0)
    raise ValueError(f"unknown target mode: {mode}")


def inverse_target(prediction: np.ndarray, mode: str) -> np.ndarray:
    prediction = np.asarray(prediction, dtype=float)
    if mode == "raw":
        return prediction
    if mode == "log_epsilon_minus_one":
        return np.exp(prediction) + 1.0
    raise ValueError(f"unknown target mode: {mode}")


def murcko_scaffolds(
    smiles_values: Sequence[str],
) -> list[str]:
    scaffolds: list[str] = []
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
    return scaffolds


def scaffold_group_keys(
    smiles_values: Sequence[str],
    *,
    acyclic_distance_threshold: float = 0.5,
) -> list[str]:
    scaffolds = murcko_scaffolds(smiles_values)
    acyclic_indices = [index for index, scaffold in enumerate(scaffolds) if not scaffold]
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprints = []
    for index in acyclic_indices:
        molecule = Chem.MolFromSmiles(smiles_values[index])
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles_values[index]!r}")
        fingerprints.append(generator.GetFingerprint(molecule))
    distances: list[float] = []
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
        acyclic_distance_threshold,
        isDistData=True,
        reordering=True,
    )
    ordered_clusters = sorted(clusters, key=lambda cluster: (-len(cluster), cluster))
    acyclic_group: dict[int, str] = {}
    for rank, cluster in enumerate(ordered_clusters):
        for local_index in cluster:
            acyclic_group[acyclic_indices[local_index]] = f"acyclic_cluster:{rank}"
    return [
        f"ring:{scaffold}" if scaffold else acyclic_group[index]
        for index, scaffold in enumerate(scaffolds)
    ]


def scaffold_folds(
    scaffold_values: Sequence[str],
    *,
    n_splits: int = N_SPLITS,
    seed: int = SEED,
) -> list[tuple[np.ndarray, np.ndarray]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, scaffold in enumerate(scaffold_values):
        groups[scaffold].append(index)
    folds: list[list[int]] = [[] for _ in range(n_splits)]
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    size_groups: dict[int, list[tuple[str, list[int]]]] = defaultdict(list)
    for item in ordered:
        size_groups[len(item[1])].append(item)
    ordered = []
    for size in sorted(size_groups, reverse=True):
        bucket = size_groups[size]
        random.Random(seed + size).shuffle(bucket)
        ordered.extend(bucket)
    for _, indices in ordered:
        destination = min(range(n_splits), key=lambda index: (len(folds[index]), index))
        folds[destination].extend(indices)
    all_indices = set(range(len(scaffold_values)))
    result = []
    for fold in folds:
        test = np.asarray(sorted(fold), dtype=int)
        train = np.asarray(sorted(all_indices - set(fold)), dtype=int)
        result.append((train, test))
    return result


def build_scaffold_assignments(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    scaffold_values = scaffold_group_keys(
        [row["smiles"] for row in rows],
    )
    folds_by_seed = [
        scaffold_folds(scaffold_values, seed=seed) for seed in SCAFFOLD_SEEDS
    ]
    return [
        {
            "partition_seed": seed,
            "inchikey": rows[index]["inchikey"],
            "smiles": rows[index]["smiles"],
            "scaffold": scaffold_values[index],
            "fold": fold,
        }
        for seed, folds in zip(SCAFFOLD_SEEDS, folds_by_seed, strict=True)
        for fold, (_, test_indices) in enumerate(folds)
        for index in test_indices
    ]


def _fit_component(
    features: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    seed: int,
) -> np.ndarray:
    model = XGBRegressor(**XGB_PARAMS, random_state=seed)
    model.fit(features[train_indices], target[train_indices])
    return model.predict(features[test_indices])


def fit_predict(
    representation: str,
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    target_mode: str,
    seed: int,
) -> np.ndarray:
    transformed = transform_target(target, target_mode)
    morgan_prediction = inverse_target(
        _fit_component(morgan, transformed, train_indices, test_indices, seed),
        target_mode,
    )
    if representation == "Morgan":
        prediction = morgan_prediction
    elif representation == "Physical":
        prediction = inverse_target(
            _fit_component(
                physical,
                transformed,
                train_indices,
                test_indices,
                seed,
            ),
            target_mode,
        )
    elif representation == "Morgan+Physical":
        physical_prediction = inverse_target(
            _fit_component(
                physical,
                transformed,
                train_indices,
                test_indices,
                seed,
            ),
            target_mode,
        )
        prediction = 0.5 * (morgan_prediction + physical_prediction)
    else:
        raise ValueError(f"unknown representation: {representation}")
    return np.maximum(prediction, 1.0)


def _metric_row(
    *,
    strategy: str,
    target_mode: str,
    representation: str,
    fold: int | str,
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, object]:
    metrics = evaluate_repeat(target, prediction)
    return {
        "strategy": strategy,
        "target_mode": target_mode,
        "representation": representation,
        "fold": fold,
        **{name: f"{value:.12g}" for name, value in metrics.items()},
    }


def _run_random_cv(
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    splitter = RepeatedKFold(
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        random_state=SEED,
    )
    rows: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    for target_mode in TARGET_MODES:
        for representation in REPRESENTATIONS:
            oof = np.full((N_REPEATS, len(target)), np.nan)
            for split_index, (train_indices, test_indices) in enumerate(
                splitter.split(np.zeros(len(target)))
            ):
                repeat = split_index // N_SPLITS
                prediction = fit_predict(
                    representation,
                    morgan=morgan,
                    physical=physical,
                    target=target,
                    train_indices=train_indices,
                    test_indices=test_indices,
                    target_mode=target_mode,
                    seed=SEED + split_index,
                )
                oof[repeat, test_indices] = prediction
            for repeat in range(N_REPEATS):
                rows.append(
                    _metric_row(
                        strategy="random_repeated_kfold",
                        target_mode=target_mode,
                        representation=representation,
                        fold=repeat,
                        target=target,
                        prediction=oof[repeat],
                    )
                )
                for row_index, prediction in enumerate(oof[repeat]):
                    predictions.append(
                        {
                            "strategy": "random_repeated_kfold",
                            "target_mode": target_mode,
                            "representation": representation,
                            "fold_or_repeat": repeat,
                            "row_index": row_index,
                            "target": f"{target[row_index]:.12g}",
                            "prediction": f"{prediction:.12g}",
                        }
                    )
            print(
                json.dumps(
                    {
                        "strategy": "random_repeated_kfold",
                        "target_mode": target_mode,
                        "representation": representation,
                    }
                ),
                flush=True,
            )
    return rows, predictions


def _run_scaffold(
    *,
    rows: Sequence[Mapping[str, str]],
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, int],
    list[dict[str, object]],
]:
    scaffold_values = scaffold_group_keys(
        [row["smiles"] for row in rows],
    )
    results: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    assignments = build_scaffold_assignments(rows)
    fold_sizes: dict[str, list[int]] = {}
    for seed in SCAFFOLD_SEEDS:
        folds = scaffold_folds(scaffold_values, seed=seed)
        fold_sizes[str(seed)] = [len(test) for _, test in folds]
        for target_mode in TARGET_MODES:
            for representation in REPRESENTATIONS:
                oof = np.full(len(rows), np.nan)
                for fold, (train_indices, test_indices) in enumerate(folds):
                    prediction = fit_predict(
                        representation,
                        morgan=morgan,
                        physical=physical,
                        target=target,
                        train_indices=train_indices,
                        test_indices=test_indices,
                        target_mode=target_mode,
                        seed=seed + fold,
                    )
                    oof[test_indices] = prediction
                results.append(
                    _metric_row(
                        strategy="scaffold_cluster_5fold",
                        target_mode=target_mode,
                        representation=representation,
                        fold=seed,
                        target=target,
                        prediction=oof,
                    )
                )
                for row_index, prediction in enumerate(oof):
                    predictions.append(
                        {
                            "strategy": "scaffold_cluster_5fold",
                            "target_mode": target_mode,
                            "representation": representation,
                            "fold_or_repeat": seed,
                            "row_index": row_index,
                            "target": f"{target[row_index]:.12g}",
                            "prediction": f"{prediction:.12g}",
                        }
                    )
                print(
                    json.dumps(
                        {
                            "strategy": "scaffold_cluster_5fold",
                            "partition_seed": seed,
                            "target_mode": target_mode,
                            "representation": representation,
                        }
                    ),
                    flush=True,
                )
    scaffold_counts = {
        "unique_scaffolds": len(set(scaffold_values)),
        "largest_scaffold_size": max(
            len(indices)
            for indices in (
                [
                    index
                    for index, value in enumerate(scaffold_values)
                    if value == scaffold
                ]
                for scaffold in set(scaffold_values)
            )
        ),
        "fold_sizes": fold_sizes,
        "acyclic_distance_threshold": 0.5,
    }
    return results, predictions, scaffold_counts, assignments


def _parse_float(row: Mapping[str, object], field: str) -> float:
    return float(row[field])


def _summarize(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (str(row["strategy"]), str(row["target_mode"]), str(row["representation"]))
        ].append(row)
    result: dict[str, dict[str, dict[str, dict[str, float]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    metric_names = (
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
    for (strategy, target_mode, representation), values in grouped.items():
        result[strategy][target_mode][representation] = {
            metric: {
                "mean": float(np.mean([_parse_float(row, metric) for row in values])),
                "std": (
                    float(np.std([_parse_float(row, metric) for row in values], ddof=1))
                    if len(values) > 1
                    else 0.0
                ),
                "n": len(values),
            }
            for metric in metric_names
        }
    return dict(result)


def _target_transform_decisions(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, object]]]],
) -> dict[str, dict[str, object]]:
    raw = summary["random_repeated_kfold"]["raw"]
    transformed = summary["random_repeated_kfold"]["log_epsilon_minus_one"]
    decisions: dict[str, dict[str, object]] = {}
    for representation in REPRESENTATIONS:
        raw_mae = float(raw[representation]["mae"]["mean"])
        transformed_mae = float(transformed[representation]["mae"]["mean"])
        raw_r2 = float(raw[representation]["r2"]["mean"])
        transformed_r2 = float(transformed[representation]["r2"]["mean"])
        accepted = transformed_mae < raw_mae and transformed_r2 > raw_r2
        decisions[representation] = {
            "decision": "accepted" if accepted else "rejected",
            "raw_mae": raw_mae,
            "log_mae": transformed_mae,
            "raw_r2": raw_r2,
            "log_r2": transformed_r2,
            "rule": "accept only when both MAE decreases and R2 increases",
        }
    return decisions


def _write_plot(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, object]]]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.5))
    x = np.arange(len(REPRESENTATIONS))
    width = 0.2
    colors = ("#2563eb", "#dc2626", "#7c3aed", "#ea580c")
    for axis, (metric, title) in zip(
        axes.flat,
        (
            ("r2", "R2"),
            ("mae", "MAE"),
            ("spearman", "Spearman rho"),
            ("auc_gt30", "AUC >30"),
        ),
        strict=True,
    ):
        series = (
            ("random_repeated_kfold", "raw", "random / raw"),
            ("random_repeated_kfold", "log_epsilon_minus_one", "random / log"),
            ("scaffold_cluster_5fold", "raw", "cluster / raw"),
            ("scaffold_cluster_5fold", "log_epsilon_minus_one", "cluster / log"),
        )
        for offset, (strategy, target_mode, label) in enumerate(series):
            values = [
                float(summary[strategy][target_mode][name][metric]["mean"])
                for name in REPRESENTATIONS
            ]
            axis.bar(
                x + (offset - 1.5) * width,
                values,
                width,
                label=label,
                color=colors[offset],
            )
        axis.set_xticks(x, REPRESENTATIONS, rotation=15)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    figure.suptitle("Target transform and scaffold/cluster holdout")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run(
    *,
    input_path: Path,
    summary_path: Path,
    rows_path: Path,
    predictions_path: Path,
    scaffold_assignment_path: Path,
    plot_path: Path,
    reuse_random: bool = False,
) -> dict[str, object]:
    rows, failed = read_modelling_rows(input_path)
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    morgan = morgan_count_features([row["smiles"] for row in rows])
    physical = physical_feature_matrix(rows)

    if reuse_random:
        random_rows = [
            row
            for row in _read_csv_rows(rows_path)
            if row["strategy"] == "random_repeated_kfold"
        ]
        random_predictions = [
            row
            for row in _read_csv_rows(predictions_path)
            if row["strategy"] == "random_repeated_kfold"
        ]
    else:
        random_rows, random_predictions = _run_random_cv(
            morgan=morgan,
            physical=physical,
            target=target,
        )
    scaffold_rows, scaffold_predictions, scaffold_counts, assignments = _run_scaffold(
        rows=rows,
        morgan=morgan,
        physical=physical,
        target=target,
    )
    all_rows = [*random_rows, *scaffold_rows]
    summary = _summarize(all_rows)
    transform_decisions = _target_transform_decisions(summary)
    payload: dict[str, object] = {
        "schema_version": 1,
        "input_path": input_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "input_sha256": canonical_text_sha256(input_path),
        "compound_count": len(rows),
        "failed_physical_feature_count": len(failed),
        "target_modes": list(TARGET_MODES),
        "representations": list(REPRESENTATIONS),
        "random_cv": {
            "strategy": "RepeatedKFold",
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "random_state": SEED,
        },
        "scaffold_cv": {
            "strategy": (
                "Ring Murcko scaffolds plus acyclic ECFP4 clusters assigned "
                "to balanced folds; repeated across five partition seeds"
            ),
            **scaffold_counts,
        },
        "summary": summary,
        "target_transform_decisions": transform_decisions,
        "interpretation_rule": (
            "Target transform is accepted only if it improves MAE and R2 under "
            "the same random CV; scaffold results combine ring-scaffold and "
            "acyclic-ECFP cluster holdouts across five partition seeds."
        ),
        "outputs": {
            "rows_csv": rows_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "predictions_csv": predictions_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "scaffold_assignment_csv": scaffold_assignment_path.relative_to(
                REPOSITORY_ROOT
            ).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    _write_csv_rows(rows_path, SUMMARY_FIELDS, all_rows)
    _write_csv_rows(
        predictions_path,
        (
            "strategy",
            "target_mode",
            "representation",
            "fold_or_repeat",
            "row_index",
            "target",
            "prediction",
        ),
        [*random_predictions, *scaffold_predictions],
    )
    _write_csv_rows(
        scaffold_assignment_path,
        ("partition_seed", "inchikey", "smiles", "scaffold", "fold"),
        assignments,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(summary, plot_path)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-summary",
        action="store_true",
    )
    parser.add_argument(
        "--reuse-random",
        action="store_true",
    )
    parser.add_argument(
        "--assignments-only",
        action="store_true",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
    )
    parser.add_argument(
        "--scaffold-assignment-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_scaffold_folds.csv",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features.csv",
    )
    parser.add_argument(
        "--rows-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_target_scaffold_metrics.csv",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_target_scaffold_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_target_scaffold_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_target_scaffold.png",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.refresh_summary:
        rows = _read_csv_rows(args.rows_output)
        summary = _summarize(rows)
        payload = json.loads(args.summary_output.read_text(encoding="utf-8"))
        payload["summary"] = summary
        payload["target_transform_decisions"] = _target_transform_decisions(summary)
        args.summary_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "summary": args.summary_output.relative_to(
                        REPOSITORY_ROOT
                    ).as_posix(),
                    "target_transform_decisions": payload[
                        "target_transform_decisions"
                    ],
                },
                indent=2,
            )
        )
        return 0
    if args.assignments_only:
        rows, failed = read_modelling_rows(args.input)
        assignments = build_scaffold_assignments(rows)
        _write_csv_rows(
            args.scaffold_assignment_output,
            ("partition_seed", "inchikey", "smiles", "scaffold", "fold"),
            assignments,
        )
        print(
            json.dumps(
                {
                    "compound_count": len(rows),
                    "failed_physical_feature_count": len(failed),
                    "assignment_count": len(assignments),
                    "output": args.scaffold_assignment_output.relative_to(
                        REPOSITORY_ROOT
                    ).as_posix(),
                },
                indent=2,
            )
        )
        return 0
    if args.plot_only:
        payload = json.loads(args.summary_output.read_text(encoding="utf-8"))
        _write_plot(payload["summary"], args.plot)
        print(json.dumps({"plot": args.plot.relative_to(REPOSITORY_ROOT).as_posix()}))
        return 0
    result = run(
        input_path=args.input,
        summary_path=args.summary_output,
        rows_path=args.rows_output,
        predictions_path=args.predictions_output,
        scaffold_assignment_path=args.scaffold_assignment_output,
        plot_path=args.plot,
        reuse_random=args.reuse_random,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
