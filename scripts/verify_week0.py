"""Verify that the Week 0 repository deliverables are present and coherent."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _check_file(relative_path: str, minimum_bytes: int = 1) -> Check:
    path = ROOT / relative_path
    if not path.is_file():
        return Check(relative_path, False, "missing")
    size = path.stat().st_size
    if size < minimum_bytes:
        return Check(relative_path, False, f"too small ({size} bytes)")
    return Check(relative_path, True, f"{size} bytes")


def _check_git_history() -> Check:
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "--verify", "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("git history", False, str(exc))
    if result.returncode != 0:
        return Check("git history", False, result.stderr.strip() or "no commit")
    return Check("git history", True, result.stdout.strip())


def _check_required_terms() -> list[Check]:
    expected = {
        "environment.yml": [
            "python=3.11",
            "rdkit",
            "scikit-learn",
            "xgboost",
            "pandas",
            "matplotlib",
        ],
        "pyproject.toml": ["electrolyte-ml", "pytest"],
    }
    checks: list[Check] = []
    for relative_path, terms in expected.items():
        path = ROOT / relative_path
        if not path.is_file():
            checks.append(Check(f"{relative_path} contents", False, "missing"))
            continue
        text = path.read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        checks.append(
            Check(
                f"{relative_path} contents",
                not missing,
                "ok" if not missing else f"missing: {', '.join(missing)}",
            )
        )
    return checks


def run_checks() -> list[Check]:
    required_files = [
        "environment.yml",
        "pyproject.toml",
        "docs/week0/setup.md",
        "docs/week0/thermoml/README.md",
        "docs/week0/thermoml/data_summary.md",
        "docs/week0/literature/pnas_2023_kim.md",
        "docs/week0/literature/reviews_battery_ai.md",
        "docs/week0/literature/reviews_electrolyte_ai.md",
        "docs/week0/literature/data_and_active_learning.md",
        "docs/week0/llm/README.md",
        "docs/week0/llm/prompts/data_cleaning_review.md",
        "docs/week0/llm/prompts/code_review.md",
        "scripts/check_environment.py",
        "scripts/fetch_thermoml.py",
        "scripts/normalize_thermoml.py",
        "src/electrolyte_ml/thermoml.py",
        "tests/test_check_environment.py",
        "tests/test_thermoml.py",
        "data/processed/thermoml_normalized.csv",
        "data/processed/thermoml_normalized.provenance.json",
    ]
    checks = [_check_file(path) for path in required_files]
    checks.extend(_check_required_terms())
    checks.append(_check_thermoml_batch())
    checks.append(_check_git_history())
    return checks


def _check_thermoml_batch() -> Check:
    path = ROOT / "data/processed/thermoml_normalized.csv"
    if not path.is_file():
        return Check("ThermoML batch", False, "missing normalized CSV")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 100:
        return Check("ThermoML batch", False, f"only {len(rows)} rows; need at least 100")
    required_columns = {
        "doi",
        "primary_compound_inchi_key",
        "property_name",
        "property_value",
        "temperature_value",
        "dielectric_kind",
        "source_sha256",
    }
    missing_columns = sorted(required_columns - set(rows[0]))
    if missing_columns:
        return Check(
            "ThermoML batch",
            False,
            f"missing columns: {', '.join(missing_columns)}",
        )
    invalid_rows = [
        index
        for index, row in enumerate(rows, start=2)
        if row["is_dielectric"] != "true" or not row["property_value"]
    ]
    if invalid_rows:
        preview = ", ".join(str(index) for index in invalid_rows[:5])
        return Check("ThermoML batch", False, f"invalid dielectric rows near {preview}")
    source_count = len({row["source_sha256"] for row in rows})
    return Check(
        "ThermoML batch",
        True,
        f"{len(rows)} dielectric rows from {source_count} source(s)",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    checks = run_checks()
    failures = [check for check in checks if not check.passed]
    if args.json:
        print(
            json.dumps(
                {
                    "passed": not failures,
                    "checks": [asdict(check) for check in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}")
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
