"""Verify that the Week 0 repository deliverables are present and coherent."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.thermoml import CSV_COLUMNS, PROVENANCE_SCHEMA_VERSION


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
            "python=3.12",
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
        "tests/test_normalize_thermoml.py",
        "tests/test_thermoml.py",
        "tests/test_verify_week0.py",
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
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)
    if len(rows) < 100:
        return Check("ThermoML batch", False, f"only {len(rows)} rows; need at least 100")
    expected_columns = list(CSV_COLUMNS)
    if columns != expected_columns:
        return Check(
            "ThermoML batch",
            False,
            "CSV header does not exactly match CSV_COLUMNS",
        )
    required_columns = {
        "doi",
        "primary_compound_inchi_key",
        "property_name",
        "property_value",
        "temperature_value",
        "temperature_unit",
        "dielectric_kind",
        "is_dielectric",
        "source_sha256",
    }
    missing_columns = sorted(required_columns - set(columns))
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

    provenance_path = ROOT / "data/processed/thermoml_normalized.provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("ThermoML batch", False, f"cannot read provenance: {exc}")
    if not isinstance(provenance, dict):
        return Check("ThermoML batch", False, "provenance is not a JSON object")
    if provenance.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        return Check(
            "ThermoML batch",
            False,
            (
                "schema_version mismatch: "
                f"{provenance.get('schema_version')!r} != "
                f"{PROVENANCE_SCHEMA_VERSION}"
            ),
        )
    if provenance.get("row_count") != len(rows):
        return Check(
            "ThermoML batch",
            False,
            (
                "provenance row_count mismatch: "
                f"{provenance.get('row_count')!r} != {len(rows)}"
            ),
        )
    if provenance.get("columns") != expected_columns:
        return Check(
            "ThermoML batch",
            False,
            "provenance columns do not match CSV_COLUMNS",
        )
    if provenance.get("filter") != "dielectric_only":
        return Check(
            "ThermoML batch",
            False,
            f"provenance filter is {provenance.get('filter')!r}, not 'dielectric_only'",
        )
    if provenance.get("errors") != []:
        return Check(
            "ThermoML batch",
            False,
            f"provenance errors must be empty, got {provenance.get('errors')!r}",
        )
    if provenance.get("deduplication") != "none":
        return Check(
            "ThermoML batch",
            False,
            (
                "provenance deduplication must be 'none', got "
                f"{provenance.get('deduplication')!r}"
            ),
        )
    if provenance.get("unit_conversion") != "none":
        return Check(
            "ThermoML batch",
            False,
            (
                "provenance unit_conversion must be 'none', got "
                f"{provenance.get('unit_conversion')!r}"
            ),
        )

    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources:
        return Check("ThermoML batch", False, "sources must be a non-empty list")
    if provenance.get("raw_file_count") != len(sources):
        return Check(
            "ThermoML batch",
            False,
            (
                "raw_file_count mismatch: "
                f"{provenance.get('raw_file_count')!r} != {len(sources)}"
            ),
        )

    source_rows: dict[tuple[str, str, str], int] = {}
    source_urls: dict[str, tuple[str, str, str]] = {}
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            return Check("ThermoML batch", False, f"source {index} is not an object")
        file_name = str(source.get("file", ""))
        source_url = str(source.get("url", ""))
        source_sha256 = str(source.get("sha256", ""))
        if not file_name or not source_url or not source_sha256:
            return Check(
                "ThermoML batch",
                False,
                f"source {index} is missing file, url, or sha256",
            )
        previous_key = source_urls.get(source_url)
        source_key = (file_name, source_url, source_sha256)
        if previous_key is not None and previous_key != source_key:
            return Check(
                "ThermoML batch",
                False,
                f"duplicate source URL alias: {source_url}",
            )
        if source_key in source_rows:
            return Check(
                "ThermoML batch",
                False,
                f"duplicate source entry: {file_name}",
            )
        try:
            row_count = int(source.get("row_count", -1))
        except (TypeError, ValueError):
            row_count = -1
        if row_count < 0:
            return Check(
                "ThermoML batch",
                False,
                f"source {file_name} has invalid row_count",
            )
        source_rows[source_key] = row_count
        source_urls[source_url] = source_key

    csv_source_counts = Counter(
        (row["source_file"], row["source_url"], row["source_sha256"]) for row in rows
    )
    for source_key, csv_count in csv_source_counts.items():
        expected_count = source_rows.get(source_key)
        if expected_count is None:
            return Check(
                "ThermoML batch",
                False,
                f"CSV source is not declared in provenance: {source_key[0]}",
            )
        if csv_count != expected_count:
            return Check(
                "ThermoML batch",
                False,
                (
                    f"source row_count mismatch for {source_key[0]}: "
                    f"{csv_count} != {expected_count}"
                ),
            )
    if sum(source_rows.values()) != len(rows):
        return Check(
            "ThermoML batch",
            False,
            (
                "source row counts do not sum to CSV rows: "
                f"{sum(source_rows.values())} != {len(rows)}"
            ),
        )

    missing_temperature_rows = [
        row for row in rows if not row["temperature_value"].strip()
    ]
    missing_temperature_unit_rows = [
        row for row in rows if not row["temperature_unit"].strip()
    ]
    if len(missing_temperature_rows) != len(missing_temperature_unit_rows):
        return Check(
            "ThermoML batch",
            False,
            (
                "temperature value/unit missingness differs: "
                f"{len(missing_temperature_rows)} values and "
                f"{len(missing_temperature_unit_rows)} units"
            ),
        )
    constraint_temperature_rows = 0
    for row in rows:
        if not row["temperature_value"].strip():
            continue
        try:
            constraints = json.loads(row["constraints_json"])
        except json.JSONDecodeError:
            constraints = []
        if isinstance(constraints, list) and any(
            isinstance(constraint, dict) and constraint.get("kind") == "temperature"
            for constraint in constraints
        ):
            constraint_temperature_rows += 1

    summary_path = ROOT / "docs/week0/thermoml/data_summary.md"
    try:
        summary = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        return Check("ThermoML batch", False, f"cannot read data summary: {exc}")
    summary_missing_temperature = _summary_metric(
        summary,
        "Rows missing temperature",
    )
    if summary_missing_temperature is None:
        return Check(
            "ThermoML batch",
            False,
            "data summary is missing the 'Rows missing temperature' metric",
        )
    if len(missing_temperature_rows) != summary_missing_temperature:
        return Check(
            "ThermoML batch",
            False,
            (
                "temperature missing count differs from summary: "
                f"{len(missing_temperature_rows)} != {summary_missing_temperature}"
            ),
        )
    summary_constraint_temperature = _summary_metric(
        summary,
        "Rows with temperature from Constraint",
    )
    if summary_constraint_temperature is None:
        return Check(
            "ThermoML batch",
            False,
            (
                "data summary is missing the 'Rows with temperature from "
                "Constraint' metric"
            ),
        )
    if constraint_temperature_rows != summary_constraint_temperature:
        return Check(
            "ThermoML batch",
            False,
            (
                "Constraint temperature count differs from summary: "
                f"{constraint_temperature_rows} != {summary_constraint_temperature}"
            ),
        )

    source_count = len({row["source_sha256"] for row in rows})
    return Check(
        "ThermoML batch",
        True,
        (
            f"{len(rows)} dielectric rows from {source_count} source(s); "
            f"{len(missing_temperature_rows)} missing temperature; "
            f"{constraint_temperature_rows} with temperature from Constraint"
        ),
    )


def _summary_metric(summary: str, label: str) -> int | None:
    match = re.search(
        rf"^\|\s*{re.escape(label)}\s*\|\s*(\d+)\s*\|",
        summary,
        flags=re.MULTILINE,
    )
    return int(match.group(1)) if match else None


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
