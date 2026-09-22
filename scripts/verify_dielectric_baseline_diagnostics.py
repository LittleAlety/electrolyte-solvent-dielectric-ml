"""Verify dielectric baseline diagnostics from CSV evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sklearn.model_selection import RepeatedKFold

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.numerics import numerical_values_close
from probes.dielectric_baseline_diagnostics import (
    _fit_predict,
    build_size_matrix,
    descriptor_features,
    gasteiger_nonfinite_count,
    morgan_count_features,
    run_descriptor_enhancement,
)
from probes.dielectric_gpr_baseline import (
    deterministic_split,
    regression_metrics,
)
from probes.dielectric_gpr_baseline import (
    read_csv_rows as read_baseline_rows,
)

MODEL_NAMES = ("DummyMean", "SizeOnlyRidge", "MorganRBFGPR")
TRAIN_SIZES = (20, 40, 60, 80)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def metric_within_tolerance(
    model_name: str,
    actual: float,
    expected: float,
) -> bool:
    """Compare metrics with an explicit model-aware platform tolerance."""

    if model_name == "DescriptorGPR":
        return numerical_values_close(
            actual,
            expected,
            model_family="descriptor_gpr",
        )
    if model_name == "MorganRBFGPR":
        return numerical_values_close(
            actual,
            expected,
            model_family="morgan_gpr",
        )
    return numerical_values_close(actual, expected, model_family="strict")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check_row_count(
    scope: str,
    rows: Sequence[object],
    *,
    expected: int,
) -> Check:
    if len(rows) != expected:
        return Check(
            f"diagnostics {scope}",
            False,
            f"expected {expected} rows, got {len(rows)}",
        )
    return Check(f"diagnostics {scope}", True, f"{expected} rows")


def check_model_names(
    rows: Sequence[Mapping[str, str]],
    *,
    expected: set[str],
) -> Check:
    names = {str(row.get("model", "")) for row in rows}
    if "" in names or names != expected:
        return Check(
            "diagnostics model names",
            False,
            f"expected model names {sorted(expected)}, got {sorted(names)}",
        )
    return Check("diagnostics model names", True, ", ".join(sorted(names)))


def _index_hash(molecule_ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(molecule_ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_model_inputs(root: Path):
    rows = read_baseline_rows(root / "data" / "dielectric_v01.csv")
    target = np.asarray([float(row["dielectric"]) for row in rows], dtype=float)
    molecule_ids = [row["inchikey"] for row in rows]
    morgan = morgan_count_features([row["smiles"] for row in rows])
    size = build_size_matrix([row["smiles"] for row in rows])
    return rows, target, molecule_ids, morgan, size


def _expected_cv_splits():
    splitter = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
    return list(splitter.split(np.zeros(100)))


def check_cv_grid(rows: Sequence[Mapping[str, str]]) -> Check:
    expected = {
        (model_name, repeat, fold)
        for model_name in MODEL_NAMES
        for repeat in range(10)
        for fold in range(5)
    }
    actual = [
        (str(row.get("model", "")), int(row.get("repeat", -1)), int(row.get("fold", -1)))
        for row in rows
    ]
    duplicates = {combination for combination in actual if actual.count(combination) > 1}
    if duplicates:
        return Check(
            "diagnostics CV grid",
            False,
            f"duplicate fold combinations: {sorted(duplicates)[:3]}",
        )
    actual_set = set(actual)
    missing = expected - actual_set
    unexpected = actual_set - expected
    if missing:
        return Check(
            "diagnostics CV grid",
            False,
            f"missing fold combinations: {sorted(missing)[:3]}",
        )
    if unexpected:
        return Check(
            "diagnostics CV grid",
            False,
            f"unexpected fold combinations: {sorted(unexpected)[:3]}",
        )
    return Check(
        "diagnostics CV grid",
        True,
        "3 models x 10 repeats x 5 folds = 150 unique combinations",
    )


def _mean_std(values: Sequence[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    variance = (
        sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        if len(values) > 1
        else 0.0
    )
    return {"mean": mean, "std": math.sqrt(variance)}


def check_cv_summary(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    cv = summary.get("cv")
    if not isinstance(cv, Mapping) or not isinstance(cv.get("models"), Mapping):
        return Check("diagnostics CV summary", False, "CV summary missing")
    if (
        cv.get("n_splits") != 5
        or cv.get("n_repeats") != 10
        or cv.get("fold_rows") != 150
    ):
        return Check("diagnostics CV summary", False, "CV run configuration mismatch")
    reported = cv["models"]
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["model"])].append(row)
    for model_name in MODEL_NAMES:
        if model_name not in grouped:
            return Check("diagnostics CV summary", False, f"{model_name} missing")
        expected = reported.get(model_name)
        if not isinstance(expected, Mapping):
            return Check("diagnostics CV summary", False, f"{model_name} summary missing")
        for metric in ("mae", "rmse", "r2"):
            actual = _mean_std([float(row[metric]) for row in grouped[model_name]])
            metric_summary = expected.get(metric)
            if not isinstance(metric_summary, Mapping):
                return Check(
                    "diagnostics CV summary",
                    False,
                    f"{model_name}/{metric} missing",
                )
            for statistic in ("mean", "std"):
                if not metric_within_tolerance(
                    model_name,
                    actual[statistic],
                    float(metric_summary[statistic]),
                ):
                    return Check(
                        "diagnostics CV summary",
                        False,
                        f"{model_name}/{metric}/{statistic} mismatch",
                    )
    return Check("diagnostics CV summary", True, "CV mean/std recomputed")


def check_cv_fold_metrics(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    grid = check_cv_grid(rows)
    if not grid.passed:
        return Check("diagnostics CV fold metrics", False, grid.detail)
    _, target, molecule_ids, morgan, size = _load_model_inputs(root)
    split_pairs = _expected_cv_splits()
    by_combo = {
        (str(row["model"]), int(row["repeat"]), int(row["fold"])): row
        for row in rows
    }
    for repeat in range(10):
        test_union: set[int] = set()
        for fold in range(5):
            split_index = repeat * 5 + fold
            train_indices, test_indices = split_pairs[split_index]
            if test_union.intersection(test_indices):
                return Check(
                    "diagnostics CV fold metrics",
                    False,
                    f"test overlap in repeat {repeat}",
                )
            test_union.update(int(index) for index in test_indices)
        if test_union != set(range(100)):
            return Check(
                "diagnostics CV fold metrics",
                False,
                f"repeat {repeat} test folds do not cover 100 compounds",
            )
    for repeat in range(10):
        for fold in range(5):
            train_indices, test_indices = split_pairs[repeat * 5 + fold]
            for model_name in MODEL_NAMES:
                row = by_combo[(model_name, repeat, fold)]
                if int(row["n_train"]) != len(train_indices):
                    return Check(
                        "diagnostics CV fold metrics",
                        False,
                        f"n_train mismatch for {model_name}/{repeat}/{fold}",
                    )
                if int(row["n_test"]) != len(test_indices):
                    return Check(
                        "diagnostics CV fold metrics",
                        False,
                        f"n_test mismatch for {model_name}/{repeat}/{fold}",
                    )
                if row["train_id_hash"] != _index_hash(molecule_ids, train_indices):
                    return Check(
                        "diagnostics CV fold metrics",
                        False,
                        f"train_id_hash mismatch for {model_name}/{repeat}/{fold}",
                    )
                if row["test_id_hash"] != _index_hash(molecule_ids, test_indices):
                    return Check(
                        "diagnostics CV fold metrics",
                        False,
                        f"test_id_hash mismatch for {model_name}/{repeat}/{fold}",
                    )
                features = {
                    "DummyMean": np.zeros((len(target), 1), dtype=float),
                    "SizeOnlyRidge": size,
                    "MorganRBFGPR": morgan,
                }[model_name]
                prediction = _fit_predict(
                    model_name,
                    features[train_indices],
                    target[train_indices],
                    features[test_indices],
                )
                recomputed = regression_metrics(target[test_indices], prediction)
                for metric in ("mae", "rmse", "r2"):
                    if not metric_within_tolerance(
                        model_name,
                        recomputed[metric],
                        float(row[metric]),
                    ):
                        return Check(
                            "diagnostics CV fold metrics",
                            False,
                            f"{model_name}/{repeat}/{fold}/{metric} mismatch",
                        )
    return Check(
        "diagnostics CV fold metrics",
        True,
        "all 150 fold metrics reproduced; folds cover 100 compounds per repeat",
    )


def check_learning_summary(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    learning = summary.get("learning_curve")
    if not isinstance(learning, Mapping) or not isinstance(
        learning.get("summary"),
        Mapping,
    ):
        return Check("diagnostics learning summary", False, "learning summary missing")
    if (
        learning.get("train_sizes") != list(TRAIN_SIZES)
        or learning.get("repeats") != 5
        or learning.get("fixed_test_count") != 20
        or learning.get("rows") != 60
    ):
        return Check(
            "diagnostics learning summary",
            False,
            "learning-curve configuration mismatch",
        )
    reported = learning["summary"]
    grouped: dict[tuple[str, int], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["model"]), int(row["train_size"]))].append(row)
    for model_name in MODEL_NAMES:
        for train_size in TRAIN_SIZES:
            model_rows = grouped[(model_name, train_size)]
            if len(model_rows) != 5:
                return Check(
                    "diagnostics learning summary",
                    False,
                    f"{model_name}/{train_size} run count mismatch",
                )
            model_summary = reported.get(model_name)
            if not isinstance(model_summary, Mapping):
                return Check(
                    "diagnostics learning summary",
                    False,
                    f"{model_name} summary missing",
                )
            size_summary = model_summary.get(str(train_size))
            if not isinstance(size_summary, Mapping):
                return Check(
                    "diagnostics learning summary",
                    False,
                    f"{model_name}/{train_size} summary missing",
                )
            for metric in ("mae", "rmse", "r2"):
                actual = _mean_std([float(row[metric]) for row in model_rows])
                expected = size_summary.get(metric)
                if not isinstance(expected, Mapping):
                    return Check(
                        "diagnostics learning summary",
                        False,
                        f"{model_name}/{train_size}/{metric} missing",
                    )
                for statistic in ("mean", "std"):
                    if not metric_within_tolerance(
                        model_name,
                        actual[statistic],
                        float(expected[statistic]),
                    ):
                        return Check(
                            "diagnostics learning summary",
                            False,
                            f"{model_name}/{train_size}/{metric}/{statistic} mismatch",
                        )
    return Check(
        "diagnostics learning summary",
        True,
        "learning-curve mean/std recomputed",
    )


def check_learning_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    expected = {
        (model_name, train_size, run)
        for model_name in MODEL_NAMES
        for train_size in TRAIN_SIZES
        for run in range(5)
    }
    actual = [
        (str(row.get("model", "")), int(row.get("train_size", -1)), int(row.get("run", -1)))
        for row in rows
    ]
    if set(actual) != expected or len(actual) != len(expected):
        return Check(
            "diagnostics learning rows",
            False,
            "unexpected learning-curve run grid",
        )
    _, target, molecule_ids, morgan, size = _load_model_inputs(root)
    original_train, original_test = deterministic_split(len(target), seed=42)
    expected_test_hash = _index_hash(molecule_ids, original_test)
    selected_by_run: dict[tuple[int, int], np.ndarray] = {}
    for train_size in TRAIN_SIZES:
        for run in range(5):
            rng = np.random.default_rng(42 + 1000 * train_size + run)
            selected = rng.choice(original_train, size=train_size, replace=False)
            if set(selected).intersection(original_test):
                return Check(
                    "diagnostics learning rows",
                    False,
                    f"test overlap for train_size={train_size}, run={run}",
                )
            selected_by_run[(train_size, run)] = selected
    by_combo = {
        (str(row["model"]), int(row["train_size"]), int(row["run"])): row
        for row in rows
    }
    for train_size in TRAIN_SIZES:
        for run in range(5):
            selected = selected_by_run[(train_size, run)]
            expected_train_hash = _index_hash(molecule_ids, selected)
            for model_name in MODEL_NAMES:
                row = by_combo[(model_name, train_size, run)]
                if (
                    int(row["n_train"]) != train_size
                    or int(row["n_test"]) != len(original_test)
                ):
                    return Check(
                        "diagnostics learning rows",
                        False,
                        f"n_train/n_test mismatch for {model_name}/{train_size}/{run}",
                    )
                if row["train_id_hash"] != expected_train_hash:
                    return Check(
                        "diagnostics learning rows",
                        False,
                        f"train_id_hash mismatch for {model_name}/{train_size}/{run}",
                    )
                if row["test_id_hash"] != expected_test_hash:
                    return Check(
                        "diagnostics learning rows",
                        False,
                        f"test_id_hash mismatch for {model_name}/{train_size}/{run}",
                    )
                features = {
                    "DummyMean": np.zeros((len(target), 1), dtype=float),
                    "SizeOnlyRidge": size,
                    "MorganRBFGPR": morgan,
                }[model_name]
                prediction = _fit_predict(
                    model_name,
                    features[selected],
                    target[selected],
                    features[original_test],
                )
                recomputed = regression_metrics(target[original_test], prediction)
                for metric in ("mae", "rmse", "r2"):
                    if not metric_within_tolerance(
                        model_name,
                        recomputed[metric],
                        float(row[metric]),
                    ):
                        return Check(
                            "diagnostics learning rows",
                            False,
                            f"{model_name}/{train_size}/{run}/{metric} mismatch",
                        )
    return Check(
        "diagnostics learning rows",
        True,
        "all 60 learning-curve rows replay and metrics reproduce",
    )


def check_descriptor_enhancement(
    summary: Mapping[str, object],
    *,
    root: Path,
) -> Check:
    descriptor = summary.get("descriptor_enhancement")
    if not isinstance(descriptor, Mapping):
        return Check("diagnostics descriptor enhancement", False, "summary missing")
    input_rows = read_baseline_rows(root / "data" / "dielectric_v01.csv")
    target = np.asarray([float(row["dielectric"]) for row in input_rows], dtype=float)
    descriptor_x, names = descriptor_features([row["smiles"] for row in input_rows])
    if descriptor.get("feature_names") != list(names):
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "feature name set mismatch",
        )
    recomputed_metrics = run_descriptor_enhancement(target, descriptor_x)
    reported_metrics = descriptor.get("metrics")
    if not isinstance(reported_metrics, Mapping):
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "metric summary missing",
        )
    for metric in ("mae", "rmse", "r2"):
        if not metric_within_tolerance(
            "DescriptorGPR",
            recomputed_metrics[metric],
            float(reported_metrics[metric]),
        ):
            return Check(
                "diagnostics descriptor enhancement",
                False,
                f"metric mismatch: {metric}",
            )
    single = summary.get("single_split")
    if not isinstance(single, Mapping) or not isinstance(
        single.get("MorganRBFGPR"), Mapping
    ):
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "Morgan reference metric missing",
        )
    recomputed_gain = (
        recomputed_metrics["r2"] - float(single["MorganRBFGPR"]["r2"])
    )
    if not metric_within_tolerance(
        "DescriptorGPR",
        recomputed_gain,
        float(descriptor["r2_gain_over_morgan"]),
    ):
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "r2_gain_over_morgan mismatch",
        )
    recomputed_flag = recomputed_metrics["r2"] >= 0.35
    if descriptor.get("reached_r2_0_35") is not recomputed_flag:
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "reached_r2_0_35 flag mismatch",
        )
    expected_nonfinite = gasteiger_nonfinite_count(
        [row["smiles"] for row in input_rows]
    )
    if descriptor.get("gasteiger_nonfinite_atom_count") != expected_nonfinite:
        return Check(
            "diagnostics descriptor enhancement",
            False,
            "Gasteiger non-finite count mismatch",
        )
    return Check(
        "diagnostics descriptor enhancement",
        True,
        f"descriptor GPR independently reproduced R2={recomputed_metrics['r2']:.9g}",
    )


def check_single_split(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
    gpr_summary: Mapping[str, object],
) -> Check:
    expected = summary.get("single_split")
    if not isinstance(expected, Mapping):
        return Check("diagnostics single split", False, "single_split missing")
    by_model = {str(row["model"]): row for row in rows}
    for model_name in MODEL_NAMES:
        if model_name not in by_model or not isinstance(expected.get(model_name), Mapping):
            return Check(
                "diagnostics single split",
                False,
                f"{model_name} metrics missing",
            )
        for metric in ("mae", "rmse", "r2"):
            if abs(
                float(by_model[model_name][metric])
                - float(expected[model_name][metric])
            ) > 1e-12:
                return Check(
                    "diagnostics single split",
                    False,
                    f"{model_name}/{metric} mismatch",
                )
    original = gpr_summary.get("metrics")
    if not isinstance(original, Mapping):
        return Check("diagnostics single split", False, "GPR metrics missing")
    for metric in ("mae", "rmse", "r2"):
        if abs(
            float(by_model["MorganRBFGPR"][metric]) - float(original[metric])
        ) > 1e-12:
            return Check(
                "diagnostics single split",
                False,
                f"original GPR {metric} was overwritten",
            )
    return Check(
        "diagnostics single split",
        True,
        "three models consistent; original GPR metrics preserved",
    )


def check_input_and_split(summary: Mapping[str, object], *, root: Path) -> Check:
    input_path = root / str(summary.get("input_path", ""))
    if not input_path.is_file():
        return Check("diagnostics input/split", False, "input missing")
    if summary.get("input_hash_mode") != "canonical_text_lf_utf8":
        return Check("diagnostics input/split", False, "hash mode mismatch")
    if canonical_text_sha256(input_path) != summary.get("input_sha256"):
        return Check("diagnostics input/split", False, "input hash mismatch")
    split = summary.get("split")
    if not isinstance(split, Mapping):
        return Check("diagnostics input/split", False, "split summary missing")
    if (
        split.get("seed") != 42
        or split.get("train_count") != 80
        or split.get("test_count") != 20
    ):
        return Check("diagnostics input/split", False, "split contract mismatch")
    rows = read_csv_rows(input_path)
    _, test_indices = deterministic_split(len(rows), seed=42)
    payload = "|".join(rows[int(index)]["inchikey"] for index in sorted(test_indices))
    expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if split.get("split_id_hash") != expected_hash:
        return Check("diagnostics input/split", False, "split ID hash mismatch")
    return Check(
        "diagnostics input/split",
        True,
        "canonical input hash and seed-42 split hash match",
    )


def check_configuration(summary: Mapping[str, object]) -> Check:
    config = summary.get("model_config")
    descriptor = summary.get("descriptor_enhancement")
    if not isinstance(config, Mapping) or not isinstance(descriptor, Mapping):
        return Check("diagnostics configuration", False, "configuration missing")
    for model_name in (*MODEL_NAMES, "descriptor_enhancement"):
        if not config.get(model_name):
            return Check(
                "diagnostics configuration",
                False,
                f"empty model config: {model_name}",
            )
    metrics = descriptor.get("metrics")
    if not isinstance(metrics, Mapping):
        return Check("diagnostics configuration", False, "descriptor metrics missing")
    for metric in ("mae", "rmse", "r2"):
        if not isinstance(metrics.get(metric), (int, float)) or not math.isfinite(
            float(metrics[metric])
        ):
            return Check(
                "diagnostics configuration",
                False,
                f"invalid descriptor metric: {metric}",
            )
    return Check(
        "diagnostics configuration",
        True,
        "model configs and descriptor metrics present",
    )


def run_checks(root: Path = ROOT) -> list[Check]:
    comparison_path = root / "data" / "processed" / "dielectric_baseline_comparison.csv"
    cv_path = root / "data" / "processed" / "dielectric_gpr_repeated_cv.csv"
    learning_path = root / "data" / "processed" / "dielectric_learning_curve.csv"
    summary_path = root / "probes" / "dielectric_baseline_diagnostics_summary.json"
    comparison_plot = root / "probes" / "artifacts" / "dielectric_baseline_comparison.png"
    learning_plot = root / "probes" / "artifacts" / "dielectric_learning_curve.png"
    gpr_summary_path = root / "probes" / "dielectric_gpr_summary.json"
    required = (
        comparison_path,
        cv_path,
        learning_path,
        summary_path,
        comparison_plot,
        learning_plot,
        gpr_summary_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return [Check("diagnostics artifacts", False, f"missing: {missing}")]
    comparison_rows = read_csv_rows(comparison_path)
    cv_rows = read_csv_rows(cv_path)
    learning_rows = read_csv_rows(learning_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    gpr_summary = json.loads(gpr_summary_path.read_text(encoding="utf-8"))
    return [
        check_row_count("comparison", comparison_rows, expected=3),
        check_row_count("CV", cv_rows, expected=150),
        check_row_count("learning curve", learning_rows, expected=60),
        check_model_names(comparison_rows, expected=set(MODEL_NAMES)),
        check_model_names(cv_rows, expected=set(MODEL_NAMES)),
        check_model_names(learning_rows, expected=set(MODEL_NAMES)),
        check_cv_grid(cv_rows),
        check_cv_fold_metrics(cv_rows, root=root),
        check_cv_summary(cv_rows, summary),
        check_learning_summary(learning_rows, summary),
        check_learning_rows(learning_rows, root=root),
        check_single_split(comparison_rows, summary, gpr_summary),
        check_input_and_split(summary, root=root),
        check_configuration(summary),
        check_descriptor_enhancement(summary, root=root),
    ]


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    output = stdout if stdout is not None else sys.stdout
    if args.json:
        print(
            json.dumps(
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
                ensure_ascii=False,
                indent=2,
            ),
            file=output,
        )
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=output)
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed", file=output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
