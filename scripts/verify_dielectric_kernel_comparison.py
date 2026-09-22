"""Independently verify the dielectric kernel comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Kernel, WhiteKernel
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.numerics import numerical_values_close

MODEL_NAMES = ("Tanimoto_GPR", "RBF_GPR", "XGBoost")
SEED = 42


class PrecomputedKernel(Kernel):
    def __init__(self) -> None:
        pass

    def __call__(self, X, Y=None, eval_gradient=False):
        kernel = np.asarray(X, dtype=float)
        if eval_gradient:
            return kernel, np.empty((kernel.shape[0], kernel.shape[1], 0))
        return kernel

    def diag(self, X):
        return np.diag(np.asarray(X, dtype=float))

    def is_stationary(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _morgan_values(
    smiles_values: Sequence[str],
    *,
    binary: bool,
) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        rows.append(
            generator.GetFingerprintAsNumPy(molecule)
            if binary
            else generator.GetCountFingerprintAsNumPy(molecule)
        )
    return np.vstack(rows).astype(np.float32, copy=False)


def _tanimoto(left: np.ndarray, right: np.ndarray | None = None) -> np.ndarray:
    left = np.asarray(left, dtype=float)
    right = left if right is None else np.asarray(right, dtype=float)
    intersection = left @ right.T
    union = (
        left.sum(axis=1)[:, None] + right.sum(axis=1)[None, :] - intersection
    )
    return np.divide(
        intersection,
        union,
        out=np.zeros_like(intersection, dtype=float),
        where=union != 0,
    )


def check_tanimoto_kernel(
    fingerprints: np.ndarray,
    observed_kernel: np.ndarray,
) -> Check:
    expected = _tanimoto(fingerprints)
    if expected.shape != observed_kernel.shape or not np.allclose(
        expected,
        observed_kernel,
        rtol=0,
        atol=1e-12,
    ):
        return Check("kernel Tanimoto", False, "Tanimoto kernel mismatch")
    return Check("kernel Tanimoto", True, "Tanimoto kernel reproduced")


def check_grid(rows: Sequence[Mapping[str, str]]) -> Check:
    expected = {
        (model_name, repeat, fold)
        for model_name in MODEL_NAMES
        for repeat in range(10)
        for fold in range(5)
    }
    actual = [
        (
            str(row.get("model", "")),
            int(row.get("repeat", -1)),
            int(row.get("fold", -1)),
        )
        for row in rows
    ]
    duplicates = {value for value in actual if actual.count(value) > 1}
    if duplicates:
        return Check("kernel CV grid", False, f"duplicate: {sorted(duplicates)[:3]}")
    actual_set = set(actual)
    if expected - actual_set:
        return Check(
            "kernel CV grid",
            False,
            f"missing: {sorted(expected - actual_set)[:3]}",
        )
    if actual_set - expected:
        return Check(
            "kernel CV grid",
            False,
            f"unexpected: {sorted(actual_set - expected)[:3]}",
        )
    return Check("kernel CV grid", True, "150 unique model/repeat/fold rows")


def check_metric_values(
    rows: Sequence[Mapping[str, str]],
    expected: Mapping[tuple[str, int, int], Mapping[str, float]],
) -> Check:
    for row in rows:
        key = (str(row["model"]), int(row["repeat"]), int(row["fold"]))
        if key not in expected:
            return Check("kernel metrics", False, f"unexpected metric row {key}")
        for metric in ("mae", "rmse", "r2"):
            family = {
                "Tanimoto_GPR": "gpr",
                "RBF_GPR": "gpr",
                "XGBoost": "xgboost",
            }[key[0]]
            if not numerical_values_close(
                row[metric],
                expected[key][metric],
                model_family=family,
            ):
                return Check(
                    "kernel metrics",
                    False,
                    f"{metric} mismatch for {key}",
                )
    return Check("kernel metrics", True, "all metrics match independent recomputation")


def check_derived_summary(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    r2_means = {
        model_name: float(
            np.mean(
                [
                    float(row["r2"])
                    for row in rows
                    if row.get("model") == model_name
                ]
            )
        )
        for model_name in MODEL_NAMES
    }
    difference = r2_means["Tanimoto_GPR"] - r2_means["RBF_GPR"]
    best_model = max(MODEL_NAMES, key=lambda name: r2_means[name])
    gate_passed = r2_means[best_model] > 0.8
    if abs(
        float(summary.get("tanimoto_vs_rbf_r2_mean_difference", math.nan))
        - difference
    ) > 1e-12:
        return Check(
            "kernel derived summary",
            False,
            "tanimoto_vs_rbf difference mismatch",
        )
    gate = summary.get("gate")
    if not isinstance(gate, Mapping) or gate.get("best_model") != best_model:
        return Check("kernel derived summary", False, "gate.best_model mismatch")
    if gate.get("passed") is not gate_passed:
        return Check("kernel derived summary", False, "gate.passed mismatch")
    conclusion = summary.get("conclusion")
    if not isinstance(conclusion, Mapping):
        return Check("kernel derived summary", False, "conclusion missing")
    if conclusion.get("tanimoto_improves_over_rbf") is not (difference > 0):
        return Check(
            "kernel derived summary",
            False,
            "conclusion improvement flag mismatch",
        )
    if (
        abs(float(conclusion.get("improvement_margin", math.nan)) - difference)
        > 1e-12
    ):
        return Check(
            "kernel derived summary",
            False,
            "conclusion improvement margin mismatch",
        )
    return Check(
        "kernel derived summary",
        True,
        f"difference={difference:.9g}; best={best_model}; gate={gate_passed}",
    )


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(target, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(target, prediction))),
        "r2": float(r2_score(target, prediction)),
    }


def _xgboost_model() -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=800,
        max_depth=10,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.6,
        reg_lambda=1.0,
        tree_method="hist",
        n_jobs=1,
        random_state=42,
    )


def _predict_independent(
    model_name: str,
    binary: np.ndarray,
    count: np.ndarray,
    target: np.ndarray,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
) -> np.ndarray:
    if model_name == "Tanimoto_GPR":
        model = GaussianProcessRegressor(
            kernel=PrecomputedKernel(),
            alpha=1e-6,
            normalize_y=True,
            optimizer=None,
            random_state=42,
        )
        model.fit(_tanimoto(binary[train_indices]), target[train_indices])
        return model.predict(
            _tanimoto(binary[test_indices], binary[train_indices])
        )
    if model_name == "RBF_GPR":
        kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
            noise_level=1.0
        )
        model = make_pipeline(
            StandardScaler(),
            GaussianProcessRegressor(
                kernel=kernel,
                alpha=1e-6,
                normalize_y=True,
                n_restarts_optimizer=2,
                random_state=42,
            ),
        )
        model.fit(count[train_indices], target[train_indices])
        return model.predict(count[test_indices])
    if model_name == "XGBoost":
        model = _xgboost_model()
        model.fit(count[train_indices], target[train_indices])
        return model.predict(count[test_indices])
    raise ValueError(f"unknown model: {model_name}")


def _index_hash(ids: Sequence[str], indices: Sequence[int]) -> str:
    payload = "|".join(ids[int(index)] for index in sorted(indices))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_checks(root: Path = ROOT) -> list[Check]:
    input_path = root / "data" / "dielectric_v01.csv"
    csv_path = root / "data" / "processed" / "dielectric_kernel_comparison.csv"
    summary_path = root / "probes" / "dielectric_kernel_comparison_summary.json"
    plot_path = root / "probes" / "artifacts" / "dielectric_kernel_comparison.png"
    missing = [
        str(path)
        for path in (input_path, csv_path, summary_path, plot_path)
        if not path.is_file()
    ]
    if missing:
        return [Check("kernel comparison artifacts", False, f"missing: {missing}")]
    input_rows = read_csv_rows(input_path)
    rows = read_csv_rows(csv_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checks = [check_grid(rows)]
    if not checks[0].passed:
        return checks
    target = np.asarray([float(row["dielectric"]) for row in input_rows], dtype=float)
    ids = [row["inchikey"] for row in input_rows]
    binary = _morgan_values([row["smiles"] for row in input_rows], binary=True)
    count = _morgan_values([row["smiles"] for row in input_rows], binary=False)
    splitter = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
    expected_metrics: dict[tuple[str, int, int], dict[str, float]] = {}
    for index, (train_indices, test_indices) in enumerate(
        splitter.split(np.zeros(len(target)))
    ):
        repeat = index // 5
        fold = index % 5
        for model_name in MODEL_NAMES:
            prediction = _predict_independent(
                model_name,
                binary,
                count,
                target,
                train_indices,
                test_indices,
            )
            expected_metrics[(model_name, repeat, fold)] = _metrics(
                target[test_indices],
                prediction,
            )
            row = next(
                row
                for row in rows
                if (
                    row["model"],
                    int(row["repeat"]),
                    int(row["fold"]),
                )
                == (model_name, repeat, fold)
            )
            if int(row["n_train"]) != len(train_indices) or int(row["n_test"]) != len(
                test_indices
            ):
                return [
                    *checks,
                    Check("kernel split sizes", False, f"size mismatch {model_name}"),
                ]
            if row["train_id_hash"] != _index_hash(ids, train_indices):
                return [
                    *checks,
                    Check("kernel split hashes", False, f"train hash {model_name}"),
                ]
            if row["test_id_hash"] != _index_hash(ids, test_indices):
                return [
                    *checks,
                    Check("kernel split hashes", False, f"test hash {model_name}"),
                ]
    checks.append(check_metric_values(rows, expected_metrics))
    summary_models = summary.get("models")
    if not isinstance(summary_models, Mapping):
        checks.append(Check("kernel summary", False, "model summaries missing"))
        return checks
    for model_name in MODEL_NAMES:
        model_rows = [row for row in rows if row["model"] == model_name]
        reported = summary_models.get(model_name)
        if not isinstance(reported, Mapping) or not reported.get("config"):
            checks.append(Check("kernel summary", False, f"{model_name} config missing"))
            continue
        for metric in ("mae", "rmse", "r2"):
            values = np.asarray([float(row[metric]) for row in model_rows])
            actual = {"mean": float(np.mean(values)), "std": float(np.std(values, ddof=1))}
            expected = reported.get("metrics", {}).get(metric)
            family = {
                "Tanimoto_GPR": "gpr",
                "RBF_GPR": "gpr",
                "XGBoost": "xgboost",
            }[model_name]
            if not isinstance(expected, Mapping) or any(
                not numerical_values_close(
                    actual[part],
                    expected[part],
                    model_family=family,
                )
                for part in ("mean", "std")
            ):
                checks.append(
                    Check("kernel summary", False, f"{model_name}/{metric} mismatch")
                )
                break
        else:
            continue
        break
    else:
        checks.append(Check("kernel summary", True, "CV summaries reproduced"))
    checks.append(check_derived_summary(rows, summary))
    input_summary = {
        "input_sha256": summary.get("input_sha256"),
        "input_hash_mode": summary.get("input_hash_mode"),
    }
    if (
        input_summary["input_hash_mode"] != "canonical_text_lf_utf8"
        or input_summary["input_sha256"] != canonical_text_sha256(input_path)
    ):
        checks.append(Check("kernel input", False, "input hash mismatch"))
    else:
        checks.append(Check("kernel input", True, "canonical input hash matches"))
    return checks


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
