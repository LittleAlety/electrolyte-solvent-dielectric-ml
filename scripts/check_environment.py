"""Check the electrolyte-ml runtime without network access."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import TextIO

PYTHON_MINIMUM = (3, 12)


@dataclass(frozen=True)
class PackageSpec:
    distribution: str
    import_name: str
    minimum: tuple[int, ...]

    @property
    def required(self) -> str:
        return ">=" + ".".join(str(part) for part in self.minimum)


PACKAGE_SPECS = (
    PackageSpec("numpy", "numpy", (2, 5, 3)),
    PackageSpec("pandas", "pandas", (2, 1)),
    PackageSpec("scikit-learn", "sklearn", (1, 9, 1)),
    PackageSpec("xgboost", "xgboost", (3, 4, 1)),
    PackageSpec("matplotlib", "matplotlib", (3, 8)),
    PackageSpec("rdkit", "rdkit", (2023, 9)),
    PackageSpec("PyYAML", "yaml", (6, 0)),
    PackageSpec("requests", "requests", (2, 31)),
    PackageSpec("pytest", "pytest", (7, 4)),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    actual: str | None = None
    required: str | None = None


@dataclass(frozen=True)
class EnvironmentReport:
    python: CheckResult
    packages: tuple[CheckResult, ...]
    rdkit_smiles: CheckResult

    @property
    def passed(self) -> bool:
        return (
            self.python.passed
            and all(result.passed for result in self.packages)
            and self.rdkit_smiles.passed
        )

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        results = (self.python, *self.packages, self.rdkit_smiles)
        return tuple(result for result in results if not result.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "python": asdict(self.python),
            "packages": [asdict(result) for result in self.packages],
            "rdkit_smiles": asdict(self.rdkit_smiles),
            "failures": [result.name for result in self.failures],
        }


def _version_numbers(version: str) -> tuple[int, ...]:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", version)
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _meets_minimum(version: str, minimum: tuple[int, ...]) -> bool:
    actual = _version_numbers(version)
    if not actual:
        return False
    width = max(len(actual), len(minimum))
    padded_actual = actual + (0,) * (width - len(actual))
    padded_minimum = minimum + (0,) * (width - len(minimum))
    return padded_actual >= padded_minimum


def check_python(
    python_version: Iterable[int | str] = sys.version_info,
    minimum: tuple[int, ...] = PYTHON_MINIMUM,
) -> CheckResult:
    version_parts = list(python_version)
    actual_parts = tuple(int(part) for part in version_parts[:3])
    actual = ".".join(str(part) for part in actual_parts)
    required = ">=" + ".".join(str(part) for part in minimum)
    passed = _meets_minimum(actual, minimum)
    detail = f"Python {actual} satisfies {required}" if passed else f"Python {actual} is below {required}"
    return CheckResult("python", passed, detail, actual=actual, required=required)


def check_package(
    spec: PackageSpec,
    *,
    importer: Callable[[str], object] = importlib.import_module,
    version_getter: Callable[[str], str] = importlib.metadata.version,
) -> CheckResult:
    try:
        importer(spec.import_name)
    except Exception as exc:  # noqa: BLE001 - import failures must be reported
        detail = f"could not import {spec.import_name}: {type(exc).__name__}: {exc}"
        return CheckResult(spec.distribution, False, detail, required=spec.required)

    try:
        actual = str(version_getter(spec.distribution))
    except Exception as exc:  # noqa: BLE001 - metadata failures are check results
        detail = (
            f"importable, but distribution metadata for {spec.distribution} is unavailable: "
            f"{type(exc).__name__}: {exc}"
        )
        return CheckResult(spec.distribution, False, detail, required=spec.required)

    if not _meets_minimum(actual, spec.minimum):
        detail = f"{actual} is below required {spec.required}"
        return CheckResult(
            spec.distribution,
            False,
            detail,
            actual=actual,
            required=spec.required,
        )

    detail = f"{actual} satisfies {spec.required}"
    return CheckResult(
        spec.distribution,
        True,
        detail,
        actual=actual,
        required=spec.required,
    )


def check_rdkit_smiles(
    importer: Callable[[str], object] = importlib.import_module,
) -> CheckResult:
    try:
        chem = importer("rdkit.Chem")
        descriptors = importer("rdkit.Chem.Descriptors")
        molecule = chem.MolFromSmiles("CCO")
        if molecule is None:
            raise ValueError("MolFromSmiles('CCO') returned None")
        molecular_weight = float(descriptors.MolWt(molecule))
        if molecular_weight <= 0:
            raise ValueError(f"MolWt returned a non-positive value: {molecular_weight}")
    except Exception as exc:  # noqa: BLE001 - RDKit failures must not crash the checker
        detail = f"minimal RDKit SMILES check failed: {type(exc).__name__}: {exc}"
        return CheckResult("rdkit_smiles", False, detail)

    detail = f"CCO parsed successfully; MolWt={molecular_weight:.2f}"
    return CheckResult("rdkit_smiles", True, detail)


def run_checks(
    *,
    python_version: Iterable[int] | None = None,
    importer: Callable[[str], object] = importlib.import_module,
    version_getter: Callable[[str], str] = importlib.metadata.version,
) -> EnvironmentReport:
    if python_version is None:
        python_version = sys.version_info

    package_results = tuple(
        check_package(spec, importer=importer, version_getter=version_getter)
        for spec in PACKAGE_SPECS
    )
    return EnvironmentReport(
        python=check_python(python_version),
        packages=package_results,
        rdkit_smiles=check_rdkit_smiles(importer),
    )


def _print_text_report(report: EnvironmentReport, stream: TextIO) -> None:
    results = (report.python, *report.packages, report.rdkit_smiles)
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}", file=stream)

    if report.passed:
        print("\nEnvironment check passed.", file=stream)
    else:
        print(f"\nEnvironment check failed ({len(report.failures)} failed checks).", file=stream)


def main(
    argv: Sequence[str] | None = None,
    *,
    python_version: Iterable[int] | None = None,
    importer: Callable[[str], object] = importlib.import_module,
    version_getter: Callable[[str], str] = importlib.metadata.version,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one machine-readable JSON document.",
    )
    args = parser.parse_args(argv)

    report = run_checks(
        python_version=python_version,
        importer=importer,
        version_getter=version_getter,
    )
    output = stdout if stdout is not None else sys.stdout
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), file=output)
    else:
        _print_text_report(report, output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
