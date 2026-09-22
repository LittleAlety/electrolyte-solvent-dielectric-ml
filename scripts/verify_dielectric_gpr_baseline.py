"""Verify the Morgan+GPR dielectric baseline from raw artifacts, not summary claims."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from probes.dielectric_gpr_baseline import deterministic_split

PREDICTION_COLUMNS = {
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "target",
    "prediction",
    "std",
    "abs_error",
}
FINAL_KERNEL_PATTERN = re.compile(
    r"^(?P<constant>[0-9.eE+-]+)\*\*2 \* "
    r"RBF\(length_scale=(?P<length_scale>[0-9.eE+-]+)\) \+ "
    r"WhiteKernel\(noise_level=(?P<noise_level>[0-9.eE+-]+)\)$"
)


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


def _metrics(rows: Sequence[Mapping[str, str]]) -> dict[str, float]:
    target = [float(row["target"]) for row in rows]
    prediction = [float(row["prediction"]) for row in rows]
    residual = [observed - predicted for observed, predicted in zip(target, prediction)]
    mean_target = sum(target) / len(target)
    mae = sum(abs(value) for value in residual) / len(residual)
    rmse = math.sqrt(sum(value**2 for value in residual) / len(residual))
    denominator = sum((value - mean_target) ** 2 for value in target)
    r2 = 1.0 - sum(value**2 for value in residual) / denominator
    return {"mae": mae, "rmse": rmse, "r2": r2}


def check_input_hash(
    summary: Mapping[str, object],
    *,
    root: Path,
) -> Check:
    input_path = root / str(summary.get("input_path", ""))
    if not input_path.is_file():
        return Check("GPR input", False, f"missing input: {input_path}")
    actual = sha256_file(input_path)
    if actual != summary.get("input_sha256"):
        return Check("GPR input", False, "input SHA256 mismatch")
    return Check("GPR input", True, "input SHA256 matches dielectric v0.1")


def check_prediction_rows(rows: Sequence[Mapping[str, str]]) -> Check:
    missing = PREDICTION_COLUMNS - set(rows[0]) if rows else PREDICTION_COLUMNS
    if missing:
        return Check("GPR predictions", False, f"missing columns: {sorted(missing)}")
    if len(rows) != 100:
        return Check("GPR predictions", False, f"expected 100 rows, got {len(rows)}")
    if len({row["inchikey"] for row in rows}) != 100:
        return Check("GPR predictions", False, "expected 100 unique InChIKeys")
    test_rows = [row for row in rows if row.get("split") == "test"]
    train_rows = [row for row in rows if row.get("split") == "train"]
    if len(test_rows) != 20 or len(train_rows) != 80:
        return Check(
            "GPR predictions",
            False,
            f"expected 80 train/20 test, got {len(train_rows)}/{len(test_rows)}",
        )
    if any(row.get("used_for_metrics") != "true" for row in test_rows):
        return Check("GPR predictions", False, "test rows must be used for metrics")
    if any(row.get("used_for_metrics") != "false" for row in train_rows):
        return Check("GPR predictions", False, "train rows must not be used in metrics")
    return Check(
        "GPR predictions",
        True,
        "100 posterior rows: 80 train + 20 held-out test",
    )


def check_split_alignment(
    input_rows: Sequence[Mapping[str, str]],
    prediction_rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    if len(input_rows) != 100 or len(prediction_rows) != 100:
        return Check("GPR split alignment", False, "expected 100 input/prediction rows")
    expected_train_indices, expected_test_indices = deterministic_split(
        len(input_rows),
        seed=42,
    )
    train_indices = {int(index) for index in expected_train_indices}
    for row_index, (input_row, prediction_row) in enumerate(
        zip(input_rows, prediction_rows, strict=True)
    ):
        if prediction_row.get("inchikey") != input_row.get("inchikey"):
            return Check(
                "GPR split alignment",
                False,
                f"inchikey mismatch at row {row_index}",
            )
        expected_split = "train" if row_index in train_indices else "test"
        if prediction_row.get("split") != expected_split:
            return Check(
                "GPR split alignment",
                False,
                f"split mismatch for {input_row['inchikey']}",
            )
        expected_used = str(expected_split == "test").lower()
        if prediction_row.get("used_for_metrics") != expected_used:
            return Check(
                "GPR split alignment",
                False,
                f"used_for_metrics mismatch for {input_row['inchikey']}",
            )
        for prediction_column, input_column in (
            ("smiles", "smiles"),
        ):
            if prediction_row.get(prediction_column) != input_row.get(input_column):
                return Check(
                    "GPR split alignment",
                    False,
                    f"{prediction_column} mismatch for {input_row['inchikey']}",
                )
        for prediction_column, input_column in (
            ("target", "dielectric"),
            ("T_K", "T_K"),
        ):
            try:
                prediction_value = Decimal(prediction_row[prediction_column])
                input_value = Decimal(input_row[input_column])
            except (KeyError, InvalidOperation, TypeError):
                return Check(
                    "GPR split alignment",
                    False,
                    f"{prediction_column} mismatch for {input_row['inchikey']}",
                )
            if prediction_value != input_value:
                return Check(
                    "GPR split alignment",
                    False,
                    f"{prediction_column} mismatch for {input_row['inchikey']}",
                )

    expected_train_keys = [
        str(input_rows[int(index)]["inchikey"]) for index in expected_train_indices
    ]
    expected_test_keys = [
        str(input_rows[int(index)]["inchikey"]) for index in expected_test_indices
    ]
    split_summary = summary.get("split")
    if not isinstance(split_summary, Mapping):
        return Check("GPR split alignment", False, "summary split is missing")
    if split_summary.get("train_inchikeys") != expected_train_keys:
        return Check("GPR split alignment", False, "summary train IDs mismatch")
    if split_summary.get("test_inchikeys") != expected_test_keys:
        return Check("GPR split alignment", False, "summary test IDs mismatch")
    hash_payload = "|".join(
        str(input_rows[int(index)]["inchikey"])
        for index in sorted(int(value) for value in expected_test_indices)
    )
    expected_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()
    if split_summary.get("test_id_hash") != expected_hash:
        return Check("GPR split alignment", False, "test_id_hash mismatch")
    if (
        split_summary.get("seed") != 42
        or split_summary.get("train_count") != 80
        or split_summary.get("test_count") != 20
    ):
        return Check("GPR split alignment", False, "summary split counts mismatch")
    return Check(
        "GPR split alignment",
        True,
        "row order, keys, targets, smiles, temperatures, IDs, and hash match",
    )


def check_metrics_from_predictions(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    test_rows = [row for row in rows if row.get("split") == "test"]
    if not test_rows:
        return Check("GPR metrics", False, "no held-out test rows")
    recomputed = _metrics(test_rows)
    summary_metrics = summary.get("metrics")
    if not isinstance(summary_metrics, Mapping):
        return Check("GPR metrics", False, "summary metrics are missing")
    for key, label in (("mae", "MAE"), ("rmse", "RMSE"), ("r2", "R2")):
        if abs(recomputed[key] - float(summary_metrics[key])) > 1e-10:
            return Check(
                "GPR metrics",
                False,
                f"{label} mismatch: {recomputed[key]} != {summary_metrics[key]}",
            )
    return Check(
        "GPR metrics",
        True,
        (
            f"MAE={recomputed['mae']:.9g}; RMSE={recomputed['rmse']:.9g}; "
            f"R2={recomputed['r2']:.9g}"
        ),
    )


def check_uncertainty(rows: Sequence[Mapping[str, str]]) -> Check:
    for row in rows:
        std = float(row["std"])
        if not math.isfinite(std) or std < 0:
            return Check(
                "GPR uncertainty",
                False,
                f"negative or non-finite std for {row.get('inchikey', 'unknown')}: {std}",
            )
        abs_error = abs(float(row["target"]) - float(row["prediction"]))
        if not math.isclose(abs_error, float(row["abs_error"]), abs_tol=1e-12):
            return Check(
                "GPR uncertainty",
                False,
                f"abs_error mismatch for {row['inchikey']}",
            )
        expected_inside = abs_error <= 1.96 * std
        if str(expected_inside).lower() != row["inside_95"]:
            return Check(
                "GPR uncertainty",
                False,
                f"inside_95 mismatch for {row['inchikey']}",
            )
    return Check("GPR uncertainty", True, "all posterior std values are finite/nonnegative")


def check_std_summary(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    test_values = [
        float(row["std"])
        for row in rows
        if row.get("split") == "test"
    ]
    if not test_values:
        return Check("GPR std summary", False, "no held-out std values")
    recomputed = {
        "min": min(test_values),
        "max": max(test_values),
        "mean": sum(test_values) / len(test_values),
    }
    summary_std = summary.get("posterior_std")
    if not isinstance(summary_std, Mapping):
        return Check("GPR std summary", False, "posterior_std summary missing")
    for key, value in recomputed.items():
        try:
            reported = float(summary_std[key])
        except (KeyError, TypeError, ValueError):
            return Check("GPR std summary", False, f"{key} is missing")
        if abs(value - reported) > 1e-12:
            return Check(
                "GPR std summary",
                False,
                f"{key} mismatch: {value} != {reported}",
            )
    return Check(
        "GPR std summary",
        True,
        f"test std recomputed: min={recomputed['min']:.6g}, "
        f"max={recomputed['max']:.6g}, mean={recomputed['mean']:.6g}",
    )


def check_coverage(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    test_rows = [row for row in rows if row.get("split") == "test"]
    covered = sum(row["inside_95"] == "true" for row in test_rows)
    recomputed = covered / len(test_rows)
    coverage = summary.get("coverage_95")
    if not isinstance(coverage, Mapping):
        return Check("GPR coverage", False, "coverage summary missing")
    if int(coverage.get("covered", -1)) != covered:
        return Check("GPR coverage", False, "covered count mismatch")
    if abs(float(coverage.get("coverage", -1)) - recomputed) > 1e-12:
        return Check("GPR coverage", False, "coverage fraction mismatch")
    return Check(
        "GPR coverage",
        True,
        f"95% coverage={recomputed:.6f} ({covered}/{len(test_rows)})",
    )


def check_model_contract(summary: Mapping[str, object]) -> Check:
    split = summary.get("split")
    model = summary.get("model")
    feature = summary.get("feature")
    gate = summary.get("gate")
    if (
        not isinstance(split, Mapping)
        or not isinstance(model, Mapping)
        or not isinstance(feature, Mapping)
    ):
        return Check("GPR model contract", False, "split/model/feature missing")
    if (
        split.get("seed") != 42
        or split.get("train_count") != 80
        or split.get("test_count") != 20
    ):
        return Check("GPR model contract", False, "split contract mismatch")
    if model.get("hyperparameters_tuned_on_test") is not False:
        return Check("GPR model contract", False, "test tuning is not allowed")
    if (
        feature.get("radius") != 2
        or feature.get("fp_size") != 2048
        or feature.get("type") != "Morgan count fingerprint"
        or (
            feature.get("name") is not None
            and feature.get("name") != "Morgan count fingerprint"
        )
        or model.get("alpha") != 1e-6
        or model.get("normalize_y") is not True
        or model.get("n_restarts_optimizer") != 2
        or model.get("random_state") != 42
    ):
        return Check(
            "GPR model contract",
            False,
            "feature/model/random_state parameters mismatch",
        )
    expected_model_name = "StandardScaler + GaussianProcessRegressor"
    if model.get("name") != expected_model_name:
        return Check("GPR model contract", False, "model name mismatch")
    expected_initial_kernel = (
        "1**2 * RBF(length_scale=10) + WhiteKernel(noise_level=1)"
    )
    if model.get("initial_kernel") != expected_initial_kernel:
        return Check("GPR model contract", False, "initial kernel mismatch")
    final_kernel = str(model.get("final_kernel", ""))
    match = FINAL_KERNEL_PATTERN.fullmatch(final_kernel)
    if match is None:
        return Check("GPR model contract", False, "final kernel format mismatch")
    expected_kernel_parameters = {
        "constant": 2.16,
        "length_scale": 42.4,
        "noise_level": 0.278,
    }
    for name, expected_value in expected_kernel_parameters.items():
        if not math.isclose(
            float(match.group(name)),
            expected_value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            return Check(
                "GPR model contract",
                False,
                f"final kernel {name} mismatch",
            )
    if not isinstance(gate, Mapping) or gate.get("threshold") != 0.8:
        return Check("GPR model contract", False, "gate threshold is missing")
    metrics = summary.get("metrics")
    if not isinstance(metrics, Mapping):
        return Check("GPR model contract", False, "metrics are missing")
    expected_gate = float(metrics["r2"]) > float(gate["threshold"])
    if gate.get("passed") is not expected_gate:
        return Check("GPR model contract", False, "gate.passed mismatch")
    return Check(
        "GPR model contract",
        True,
        "names, seed, split, kernel parameters, and gate recomputation match",
    )


def run_checks(root: Path = ROOT) -> list[Check]:
    predictions_path = (
        root / "data" / "processed" / "dielectric_gpr_test_predictions.csv"
    )
    summary_path = root / "probes" / "dielectric_gpr_summary.json"
    plot_path = root / "probes" / "artifacts" / "dielectric_gpr_parity.png"
    missing = [
        str(path)
        for path in (predictions_path, summary_path, plot_path)
        if not path.is_file()
    ]
    if missing:
        return [Check("GPR artifacts", False, f"missing: {missing}")]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = read_csv_rows(predictions_path)
    input_rows = read_csv_rows(root / "data" / "dielectric_v01.csv")
    return [
        check_input_hash(summary, root=root),
        check_prediction_rows(rows),
        check_split_alignment(input_rows, rows, summary),
        check_metrics_from_predictions(rows, summary),
        check_uncertainty(rows),
        check_std_summary(rows, summary),
        check_coverage(rows, summary),
        check_model_contract(summary),
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> int:
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
