"""Independently verify the viscosity random-row and group-holdout baseline."""

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
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

MODEL_NAMES = ("DummyMean", "TOnlyRidge", "MorganTemperatureXGBoost")


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = target - prediction
    mean_target = float(np.mean(target))
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "r2": float(
            1.0
            - np.sum(residual**2)
            / np.sum((target - mean_target) ** 2)
        ),
    }


def check_group_key_leakage(
    rows: Sequence[Mapping[str, str]],
    split_assignment: Mapping[str, str],
) -> Check:
    key_sides: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("split_type") != "group_key":
            continue
        side = split_assignment.get(str(row.get("row_id", "")))
        if side:
            key_sides[str(row["inchikey"])].add(side)
    leaked = {
        key: sides for key, sides in key_sides.items() if {"train", "test"}.issubset(sides)
    }
    if leaked:
        return Check(
            "viscosity group leakage",
            False,
            f"train/test key overlap: {sorted(leaked)[:5]}",
        )
    return Check("viscosity group leakage", True, "no group key overlaps")


def check_prediction_binding(
    rows: Sequence[Mapping[str, str]],
    input_rows: Sequence[Mapping[str, str]],
    split_assignment: Mapping[str, str],
) -> Check:
    for row in rows:
        try:
            row_id = int(row["row_id"])
            input_row = input_rows[row_id]
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return Check("viscosity row binding", False, f"invalid row_id: {exc}")
        if row.get("inchikey") != input_row.get("inchikey"):
            return Check("viscosity row binding", False, f"inchikey mismatch for {row_id}")
        expected_split = split_assignment.get(
            f"{row.get('split_type')}:{row_id}",
            split_assignment.get(str(row_id)),
        )
        if row.get("split_type") != expected_split:
            return Check("viscosity row binding", False, f"split_type mismatch for {row_id}")
        for column in ("smiles", "name", "T_K"):
            if row.get(column) != input_row.get(column):
                return Check(
                    "viscosity row binding",
                    False,
                    f"{column} mismatch for {row_id}",
                )
        if row.get("used_for_metrics") != "true":
            return Check(
                "viscosity row binding",
                False,
                f"used_for_metrics mismatch for {row_id}",
            )
    return Check(
        "viscosity row binding",
        True,
        "all prediction rows bind to the source row, molecule, temperature, and split",
    )


def check_derived_columns(
    rows: Sequence[Mapping[str, str]],
    input_rows: Sequence[Mapping[str, str]],
) -> Check:
    for row in rows:
        try:
            input_row = input_rows[int(row["row_id"])]
            target_log = math.log10(float(input_row["viscosity_cP"]))
            target_cp = float(input_row["viscosity_cP"])
            target_pa_s = target_cp / 1000.0
            prediction_log = float(row["prediction_log10_cP"])
            prediction_cp = 10.0**prediction_log
            prediction_pa_s = prediction_cp / 1000.0
            checks = {
                "target_log10_cP": (float(row["target_log10_cP"]), target_log),
                "target_cP": (float(row["target_cP"]), target_cp),
                "target_Pa_s": (float(row["target_Pa_s"]), target_pa_s),
                "prediction_cP": (float(row["prediction_cP"]), prediction_cp),
                "prediction_Pa_s": (
                    float(row["prediction_Pa_s"]),
                    prediction_pa_s,
                ),
                "abs_error_log10_cP": (
                    float(row["abs_error_log10_cP"]),
                    abs(target_log - prediction_log),
                ),
                "abs_error_cP": (
                    float(row["abs_error_cP"]),
                    abs(target_cp - prediction_cp),
                ),
                "abs_error_Pa_s": (
                    float(row["abs_error_Pa_s"]),
                    abs(target_pa_s - prediction_pa_s),
                ),
            }
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return Check("viscosity derived columns", False, f"invalid row: {exc}")
        for column, (actual, expected) in checks.items():
            if not math.isclose(
                actual,
                expected,
                rel_tol=1e-10,
                abs_tol=1e-12,
            ):
                return Check(
                    "viscosity derived columns",
                    False,
                    f"{column} mismatch for {row['row_id']}",
                )
    return Check(
        "viscosity derived columns",
        True,
        "log10, cP, Pa*s, and absolute errors reproduced row by row",
    )


def check_gate_and_interpretation(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    passed: dict[str, bool] = {}
    for split_type in ("random_row", "group_key"):
        model_rows = [
            row
            for row in rows
            if row["split_type"] == split_type
            and row["model"] == "MorganTemperatureXGBoost"
        ]
        if not model_rows:
            return Check("viscosity gate", False, f"{split_type} predictions missing")
        mae = float(
            np.mean(
                [abs(float(row["target_log10_cP"]) - float(row["prediction_log10_cP"])) for row in model_rows]
            )
        )
        passed[split_type] = mae < 0.15
    gate = summary.get("primary_gate")
    if not isinstance(gate, Mapping):
        return Check("viscosity gate", False, "primary_gate missing")
    if (
        gate.get("random_row_passed") is not passed["random_row"]
        or gate.get("group_key_passed") is not passed["group_key"]
    ):
        return Check("viscosity gate", False, "primary gate mismatch")
    random_pass_group_fail = passed["random_row"] and not passed["group_key"]
    interpretation = summary.get("interpretation")
    if not isinstance(interpretation, Mapping):
        return Check("viscosity interpretation", False, "interpretation missing")
    if interpretation.get("random_pass_group_fail") is not random_pass_group_fail:
        return Check(
            "viscosity interpretation",
            False,
            "interpretation random_pass_group_fail mismatch",
        )
    if not interpretation.get(
        "random_row_tests_temperature_interpolation_and_row_memorization"
    ) or not interpretation.get("group_key_tests_new_molecule_generalization"):
        return Check(
            "viscosity interpretation",
            False,
            "interpretation split semantics missing",
        )
    return Check(
        "viscosity gate",
        True,
        f"random={passed['random_row']}; group={passed['group_key']}",
    )


def check_metrics_from_predictions(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    split_summaries = summary.get("splits")
    if not isinstance(split_summaries, Mapping):
        return Check("viscosity metrics", False, "split summary missing")
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["split_type"]), str(row["model"]))].append(row)
    for split_type in ("random_row", "group_key"):
        split_summary = split_summaries.get(split_type)
        if not isinstance(split_summary, Mapping):
            return Check("viscosity metrics", False, f"{split_type} missing")
        reported_models = split_summary.get("models")
        if not isinstance(reported_models, Mapping):
            return Check("viscosity metrics", False, f"{split_type} models missing")
        for model_name in MODEL_NAMES:
            model_rows = grouped[(split_type, model_name)]
            if not model_rows:
                return Check(
                    "viscosity metrics",
                    False,
                    f"{split_type}/{model_name} predictions missing",
                )
            target_log = np.asarray(
                [float(row["target_log10_cP"]) for row in model_rows]
            )
            prediction_log = np.asarray(
                [float(row["prediction_log10_cP"]) for row in model_rows]
            )
            actual = {
                "log10_cP": _metrics(target_log, prediction_log),
                "log10_Pa_s": _metrics(target_log - 3.0, prediction_log - 3.0),
                "cP": _metrics(
                    np.power(10.0, target_log),
                    np.power(10.0, prediction_log),
                ),
                "Pa_s": _metrics(
                    np.power(10.0, target_log) / 1000.0,
                    np.power(10.0, prediction_log) / 1000.0,
                ),
            }
            reported = reported_models.get(model_name)
            if not isinstance(reported, Mapping):
                return Check(
                    "viscosity metrics",
                    False,
                    f"{split_type}/{model_name} summary missing",
                )
            for unit, metrics in actual.items():
                expected = reported.get(unit)
                if not isinstance(expected, Mapping):
                    return Check(
                        "viscosity metrics",
                        False,
                        f"{split_type}/{model_name}/{unit} missing",
                    )
                for metric in ("mae", "rmse", "r2"):
                    tolerance = 1e-10 if unit == "log10_cP" else 1e-7
                    if abs(metrics[metric] - float(expected[metric])) > tolerance:
                        return Check(
                            "viscosity metrics",
                            False,
                            f"{split_type}/{model_name}/{unit}/{metric} mismatch",
                        )
    return Check(
        "viscosity metrics",
        True,
        "log10 and raw-unit metrics reproduced for both splits",
    )


def _split_hash(ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_split_reconstruction(
    predictions: Sequence[Mapping[str, str]],
    input_rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    ids = [row["inchikey"] for row in input_rows]
    random_indices = np.random.default_rng(42).permutation(len(input_rows))
    random_test_count = max(1, round(len(input_rows) * 0.2))
    random_train = random_indices[random_test_count:]
    random_test = random_indices[:random_test_count]
    group_splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.2,
        random_state=42,
    )
    group_train, group_test = next(
        group_splitter.split(np.zeros(len(ids)), groups=ids)
    )
    expected = {
        "random_row": (random_train, random_test),
        "group_key": (group_train, group_test),
    }
    split_summaries = summary.get("splits")
    if not isinstance(split_summaries, Mapping):
        return Check("viscosity split reconstruction", False, "split summary missing")
    for split_type, (train_indices, test_indices) in expected.items():
        split_summary = split_summaries.get(split_type)
        if not isinstance(split_summary, Mapping):
            return Check(
                "viscosity split reconstruction",
                False,
                f"{split_type} summary missing",
            )
        expected_test_rows = {str(int(index)) for index in test_indices}
        for model_name in MODEL_NAMES:
            actual_test = {
                row["row_id"]
                for row in predictions
                if row["split_type"] == split_type
                and row["model"] == model_name
                and row["row_id"] in expected_test_rows
            }
            if actual_test != expected_test_rows:
                return Check(
                    "viscosity split reconstruction",
                    False,
                    f"{split_type}/{model_name} row assignment mismatch",
                )
        if split_summary.get("train_id_hash") != _split_hash(ids, train_indices):
            return Check(
                "viscosity split reconstruction",
                False,
                f"{split_type} train hash mismatch",
            )
        if split_summary.get("test_id_hash") != _split_hash(ids, test_indices):
            return Check(
                "viscosity split reconstruction",
                False,
                f"{split_type} test hash mismatch",
            )
    train_keys = {ids[int(index)] for index in group_train}
    test_keys = {ids[int(index)] for index in group_test}
    if train_keys.intersection(test_keys):
        return Check(
            "viscosity split reconstruction",
            False,
            "group split key overlap",
        )
    split_summary = split_summaries["group_key"]
    if split_summary["group_overlap"] != 0:
        return Check(
            "viscosity split reconstruction",
            False,
            "summary group overlap is non-zero",
        )
    if split_summary["test_id_hash"] != _split_hash(ids, group_test):
        return Check(
            "viscosity split reconstruction",
            False,
            "group test hash mismatch",
        )
    return Check(
        "viscosity split reconstruction",
        True,
        "random and group splits reconstructed; no group overlap",
    )


def check_input_and_features(
    summary: Mapping[str, object],
    *,
    root: Path,
) -> Check:
    input_path = root / str(summary.get("input_path", ""))
    if not input_path.is_file():
        return Check("viscosity input/features", False, "input missing")
    if summary.get("input_hash_mode") != "canonical_text_lf_utf8":
        return Check("viscosity input/features", False, "hash mode mismatch")
    if canonical_text_sha256(input_path) != summary.get("input_sha256"):
        return Check("viscosity input/features", False, "input SHA256 mismatch")
    config = summary.get("feature_config")
    if not isinstance(config, Mapping):
        return Check("viscosity input/features", False, "feature config missing")
    if config.get("temperature_features") != ["T_K", "1000_over_T_K"]:
        return Check(
            "viscosity input/features",
            False,
            "temperature feature configuration mismatch",
        )
    rows = read_csv_rows(input_path)
    inverse_temperatures: list[float] = []
    for row in rows:
        temperature = float(row["T_K"])
        if not math.isfinite(temperature) or temperature <= 0:
            return Check(
                "viscosity input/features",
                False,
                f"invalid temperature for {row['inchikey']}",
            )
        inverse_temperatures.append(1000.0 / temperature)
    if not np.isfinite(np.asarray(inverse_temperatures, dtype=float)).all():
        return Check("viscosity input/features", False, "inverse T feature mismatch")
    models = summary.get("splits", {}).get("random_row", {}).get("models", {})
    if not models or any(not models.get(name, {}).get("config") for name in MODEL_NAMES):
        return Check("viscosity input/features", False, "model config missing")
    return Check(
        "viscosity input/features",
        True,
        "canonical hash, T features, and model configs present",
    )


def run_checks(root: Path = ROOT) -> list[Check]:
    predictions_path = (
        root / "data" / "processed" / "viscosity_baseline_predictions.csv"
    )
    summary_path = root / "probes" / "viscosity_baseline_summary.json"
    plot_path = root / "probes" / "artifacts" / "viscosity_baseline_parity.png"
    input_path = root / "data" / "viscosity_v01.csv"
    missing = [
        str(path)
        for path in (predictions_path, summary_path, plot_path, input_path)
        if not path.is_file()
    ]
    if missing:
        return [Check("viscosity baseline artifacts", False, f"missing: {missing}")]
    predictions = read_csv_rows(predictions_path)
    input_rows = read_csv_rows(input_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ids = [row["inchikey"] for row in input_rows]
    group_splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.2,
        random_state=42,
    )
    group_train, group_test = next(
        group_splitter.split(np.zeros(len(ids)), groups=ids)
    )
    group_assignment = {
        str(index): "test" for index in group_test
    } | {
        str(index): "train" for index in group_train
    }
    random_indices = np.random.default_rng(42).permutation(len(input_rows))
    random_test_count = max(1, round(len(input_rows) * 0.2))
    random_test = random_indices[:random_test_count]
    expected_prediction_splits = {
        **{
            f"random_row:{index}": "random_row"
            for index in random_test
        },
        **{
            f"group_key:{index}": "group_key"
            for index in group_test
        },
    }
    return [
        Check(
            "viscosity prediction count",
            len(predictions) == 4272,
            f"{len(predictions)} rows",
        ),
        check_group_key_leakage(
            predictions,
            group_assignment,
        ),
        check_prediction_binding(
            predictions,
            input_rows,
            expected_prediction_splits,
        ),
        check_derived_columns(predictions, input_rows),
        check_metrics_from_predictions(predictions, summary),
        check_gate_and_interpretation(predictions, summary),
        check_split_reconstruction(predictions, input_rows, summary),
        check_input_and_features(summary, root=root),
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
