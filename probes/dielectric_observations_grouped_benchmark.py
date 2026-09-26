"""Benchmark the v1.x temperature-resolved observation table under grouped CV.

v1.0's headline R2 of 0.3636 comes from `RepeatedKFold` over 236 rows - one row
per compound, so no compound can straddle a fold and the leak is impossible by
construction. The observation table breaks that guarantee: a compound with 60
temperature points could sit in both train and test. This probe therefore scores
the enlarged table twice:

* **grouped** - GroupKFold by InChIKey, repeated with shuffled group order, so
  every temperature point of a compound lands in the same fold. This is the
  honest number for an observation-level table.
* **random_row** - the v1.0 row-level splitter, kept only as a reference so the
  size of the optimism introduced by the leak is visible.

Headline question: with 5-7x more rows and T_K varying within a compound, does
the hybrid representation still reach the v1.0 R2 of 0.3636 under the grouped
protocol?
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    PHYSICAL_COLUMNS,
    REPRESENTATIONS,
    SEED,
    evaluate_repeat,
    fit_predict_representation,
    morgan_count_features,
)
from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

OBSERVATIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv"
FEATURES_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
REFERENCE_SUMMARY = REPOSITORY_ROOT / "probes" / "dielectric_v03_representation_ablation_summary.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_observations_grouped_benchmark_summary.json"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"

METRIC_NAMES = ("r2", "mae", "rmse", "spearman", "mae_lt20", "mae_20_60", "mae_gt60")
FOLD_COLUMNS = (
    "protocol",
    "representation",
    "repeat",
    "fold",
    "train_rows",
    "test_rows",
    "train_compounds",
    "test_compounds",
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write LF-only CSV: `.gitattributes` pins `*.csv` to `eol=lf`."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def grouped_folds(
    groups: Sequence[str],
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """Yield (repeat, fold, train_index, test_index) with whole compounds held out.

    `GroupKFold` is deterministic and cannot be repeated, so each repeat draws a
    fresh permutation of the compound keys and deals them round-robin into folds.
    Every row of a compound inherits its compound's fold, which is what stops a
    temperature series from being split across the train/test boundary.
    """

    keys = np.asarray(sorted(set(groups)))
    group_array = np.asarray(groups)
    for repeat in range(n_repeats):
        rng = np.random.default_rng(seed + repeat)
        shuffled = rng.permutation(keys)
        fold_of = {str(key): index % n_splits for index, key in enumerate(shuffled)}
        fold_ids = np.asarray([fold_of[str(key)] for key in group_array])
        for fold in range(n_splits):
            test_index = np.flatnonzero(fold_ids == fold)
            train_index = np.flatnonzero(fold_ids != fold)
            yield repeat, fold, train_index, test_index


def random_row_folds(
    row_count: int,
    *,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    splitter = RepeatedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=seed)
    for split_index, (train_index, test_index) in enumerate(
        splitter.split(np.zeros(row_count))
    ):
        yield split_index // n_splits, split_index % n_splits, train_index, test_index


def load_table(
    observations_path: Path,
    features_path: Path,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, int]]:
    observations = read_csv_rows(observations_path)
    features = {
        row["inchikey"]: row
        for row in read_csv_rows(features_path)
        if row.get("status") != "error"
    }

    kept: list[dict[str, str]] = []
    dropped = defaultdict(int)
    for row in observations:
        feature = features.get(row["inchikey"])
        if feature is None:
            dropped["no_xtb_features"] += 1
            continue
        if not row["smiles"].strip():
            dropped["no_smiles"] += 1
            continue
        missing = [column for column in PHYSICAL_COLUMNS if not feature.get(column, "").strip()]
        if missing:
            dropped["incomplete_xtb_features"] += 1
            continue
        kept.append({**row, "_features": feature})
    return kept, features, {key: int(value) for key, value in dropped.items()}


def build_matrices(
    rows: Sequence[Mapping[str, object]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Return (morgan, physical, target, groups).

    The physical block is the frozen xTB vector with `T_K` swapped for the
    observation's own temperature, which is the entire data-side change v1.x
    makes: the pipeline and the feature list are untouched.
    """

    smiles = [str(row["smiles"]) for row in rows]
    morgan = morgan_count_features(smiles)
    physical = np.asarray(
        [
            [
                float(str(row["T_K"]))
                if column == "T_K"
                else float(str(row["_features"][column]))  # type: ignore[index]
                for column in PHYSICAL_COLUMNS
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    if not np.isfinite(physical).all():
        raise ValueError("physical feature matrix contains non-finite values")
    target = np.asarray([float(str(row["epsilon"])) for row in rows], dtype=float)
    temperatures = np.asarray([float(str(row["T_K"])) for row in rows], dtype=float)
    groups = [str(row["inchikey"]) for row in rows]
    return morgan, physical, target, temperatures, groups


def select_one_row_per_compound(
    rows: Sequence[Mapping[str, object]],
    *,
    target_temperature_k: float = 298.15,
) -> list[Mapping[str, object]]:
    """Keep the row closest to `target_temperature_k` for every compound.

    This is the apples-to-apples control for the temperature expansion: the same
    compound set, the same grouped protocol, but one observation per compound -
    which is exactly what v1.0 shipped. If the enlarged table does not beat it,
    the extra temperature points are buying nothing.
    """

    best: dict[str, Mapping[str, object]] = {}
    for row in rows:
        key = str(row["inchikey"])
        distance = abs(float(str(row["T_K"])) - target_temperature_k)
        current = best.get(key)
        if current is None or distance < abs(
            float(str(current["T_K"])) - target_temperature_k
        ):
            best[key] = row
    return [best[key] for key in sorted(best)]


def run_protocol(
    protocol: str,
    splits: Iterator[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, int],
]:
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    per_repeat: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    straddling_compounds: list[int] = []
    group_array = np.asarray(groups)
    for repeat, fold, train_index, test_index in splits:
        straddling = int(
            np.intersect1d(group_array[train_index], group_array[test_index]).size
        )
        if protocol == "grouped" and straddling:
            raise ValueError(f"{protocol}: a compound straddles the fold boundary")
        straddling_compounds.append(straddling)
        for representation in REPRESENTATIONS:
            prediction, _ = fit_predict_representation(
                representation,
                morgan=morgan,
                physical=physical,
                target=target,
                train_indices=train_index,
                test_indices=test_index,
                seed=SEED,
            )
            fold_metrics = evaluate_repeat(target[test_index], prediction)
            fold_rows.append(
                {
                    "protocol": protocol,
                    "representation": representation,
                    "repeat": repeat,
                    "fold": fold,
                    "train_rows": int(train_index.size),
                    "test_rows": int(test_index.size),
                    "train_compounds": int(np.unique(group_array[train_index]).size),
                    "test_compounds": int(np.unique(group_array[test_index]).size),
                    "mae": fold_metrics["mae"],
                    "rmse": fold_metrics["rmse"],
                    "r2": fold_metrics["r2"],
                    "spearman": fold_metrics["spearman"],
                }
            )
            bucket = per_repeat.setdefault(
                (representation, repeat), {"target": np.zeros(0), "prediction": np.zeros(0)}
            )
            bucket["target"] = np.concatenate([bucket["target"], target[test_index]])
            bucket["prediction"] = np.concatenate([bucket["prediction"], prediction])
            for row_index, value in zip(test_index, prediction, strict=True):
                prediction_rows.append(
                    {
                        "protocol": protocol,
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
                "protocol": protocol,
                "representation": representation,
                "repeat": repeat,
                **{name: metrics[name] for name in METRIC_NAMES},
            }
        )
    leak = {
        "folds": len(straddling_compounds),
        "folds_with_a_straddling_compound": sum(
            1 for count in straddling_compounds if count
        ),
        "max_straddling_compounds_in_a_fold": (
            max(straddling_compounds) if straddling_compounds else 0
        ),
    }
    return fold_rows, repeat_rows, prediction_rows, leak


def summarize_repeats(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, dict]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["protocol"]), str(row["representation"]))].append(row)
    summary: dict[str, dict[str, dict]] = {}
    for (protocol, representation), items in sorted(grouped.items()):
        summary.setdefault(protocol, {})[representation] = {
            metric: {
                "mean": float(np.nanmean([float(item[metric]) for item in items])),
                "std": float(np.nanstd([float(item[metric]) for item in items], ddof=1)),
                "n": len(items),
            }
            for metric in METRIC_NAMES
        }
    return summary


def read_reference() -> dict[str, object]:
    if not REFERENCE_SUMMARY.is_file():
        return {}
    payload = json.loads(REFERENCE_SUMMARY.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    if not summary:
        return {}
    return {
        "path": portable_relative_path(REFERENCE_SUMMARY, root=REPOSITORY_ROOT),
        "protocol": "v1.0 RepeatedKFold(5x10) over 236 compound rows",
        "hybrid": {
            metric: summary["Morgan+Physical"][metric]
            for metric in ("r2", "mae", "rmse", "spearman")
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows, _, dropped = load_table(args.observations, args.features)
    morgan, physical, target, temperatures, groups = build_matrices(rows)

    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    leak_report: dict[str, dict[str, int]] = {}
    single = select_one_row_per_compound(rows)
    single_morgan, single_physical, single_target, single_temperatures, single_groups = (
        build_matrices(single)
    )

    protocol_inputs = {
        "grouped": (
            grouped_folds(groups),
            morgan,
            physical,
            target,
            temperatures,
            groups,
        ),
        "grouped_single_row": (
            grouped_folds(single_groups),
            single_morgan,
            single_physical,
            single_target,
            single_temperatures,
            single_groups,
        ),
        "random_row": (
            random_row_folds(len(rows)),
            morgan,
            physical,
            target,
            temperatures,
            groups,
        ),
    }
    for protocol, (
        splits,
        protocol_morgan,
        protocol_physical,
        protocol_target,
        protocol_temperatures,
        protocol_groups,
    ) in protocol_inputs.items():
        folds, repeats, predictions, leak = run_protocol(
            protocol,
            splits,
            morgan=protocol_morgan,
            physical=protocol_physical,
            target=protocol_target,
            temperatures=protocol_temperatures,
            groups=protocol_groups,
        )
        fold_rows.extend(folds)
        repeat_rows.extend(repeats)
        prediction_rows.extend(predictions)
        leak_report[protocol] = leak

    summary = summarize_repeats(repeat_rows)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    write_csv_rows(args.artifacts / "dielectric_observations_benchmark_folds.csv", FOLD_COLUMNS, fold_rows)
    write_csv_rows(
        args.artifacts / "dielectric_observations_benchmark_repeats.csv",
        ("protocol", "representation", "repeat", *METRIC_NAMES),
        repeat_rows,
    )
    write_csv_rows(
        args.artifacts / "dielectric_observations_benchmark_predictions.csv",
        PREDICTION_COLUMNS,
        prediction_rows,
    )
    payload = {
        "inputs": {
            "observations": portable_relative_path(args.observations, root=REPOSITORY_ROOT),
            "observations_sha256": canonical_text_sha256(args.observations),
            "features": portable_relative_path(args.features, root=REPOSITORY_ROOT),
            "features_sha256": canonical_text_sha256(args.features),
        },
        "rows": len(rows),
        "compounds": len(set(groups)),
        "rows_per_compound": {
            "min": int(min(Counter(groups).values())),
            "max": int(max(Counter(groups).values())),
        },
        "dropped": dropped,
        "protocols": {
            "grouped": "group K-fold by InChIKey, shuffled group order, 10x5",
            "grouped_single_row": (
                "same grouped protocol, one row per compound (the row nearest 298.15 K)"
            ),
            "random_row": "RepeatedKFold(5, 10, random_state=42), v1.0 reference splitter",
        },
        "single_row_compounds": len(single),
        "summary": summary,
        "group_leak": leak_report,
        "reference": read_reference(),
        "outputs": {
            "folds": portable_relative_path(
                args.artifacts / "dielectric_observations_benchmark_folds.csv",
                root=REPOSITORY_ROOT,
            ),
            "repeats": portable_relative_path(
                args.artifacts / "dielectric_observations_benchmark_repeats.csv",
                root=REPOSITORY_ROOT,
            ),
            "predictions": portable_relative_path(
                args.artifacts / "dielectric_observations_benchmark_predictions.csv",
                root=REPOSITORY_ROOT,
            ),
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    hybrid = summary["grouped"]["Morgan+Physical"]["r2"]["mean"]
    reference = payload["reference"].get("hybrid", {}).get("r2", {}).get("mean")
    print(f"rows {len(rows)} across {len(set(groups))} compounds")
    for protocol in summary:
        line = ", ".join(
            f"{name} R2={summary[protocol][name]['r2']['mean']:.4f}"
            f" MAE={summary[protocol][name]['mae']['mean']:.4f}"
            for name in REPRESENTATIONS
        )
        print(f"  {protocol:11s}: {line}")
    if reference is not None:
        verdict = "holds" if hybrid >= reference else "drops"
        print(f"v1.0 hybrid R2={reference:.4f} -> grouped observation-level {hybrid:.4f} ({verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())