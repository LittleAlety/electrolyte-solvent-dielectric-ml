"""Strictly verify Week 1 closure and Week 2 artifact contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.standardize import GATE_FLAGS

ALLOWED_GATE_FLAGS = frozenset(GATE_FLAGS)
GENERATED_FLAG_FILES = (
    "data/processed/p1_spot_check.csv",
    "data/processed/coverage_gap.csv",
    "data/processed/viscosity_raw.csv",
    "data/processed/viscosity_predictions.csv",
    "data/processed/dielectric_viscosity_intersection.csv",
)
REPO_P2_ARTIFACTS = {
    "parity_plot": "probes/artifacts/p2_dipole_parity.png",
    "learning_curve_plot": "probes/artifacts/p2_dipole_learning_curve.png",
    "learning_curve_csv": "data/processed/p2_learning_curve.csv",
    "test_predictions_csv": "data/processed/p2_test_predictions.csv",
}
OPTIONAL_REPO_P2_ARTIFACTS = {
    "model_json": "probes/artifacts/p2_dipole_model.json",
}


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


def check_gate_flags(
    source: str,
    rows: Iterable[Mapping[str, str]],
) -> Check:
    unknown: set[str] = set()
    empty_rows: list[int] = []
    for row_index, row in enumerate(rows, start=2):
        value = str(row.get("gate_flags", "")).strip()
        if not value:
            empty_rows.append(row_index)
            continue
        unknown.update(
            flag for flag in value.split("|") if flag not in ALLOWED_GATE_FLAGS
        )
    if unknown:
        return Check(
            f"gate_flags:{source}",
            False,
            f"unknown flags: {', '.join(sorted(unknown))}",
        )
    if empty_rows:
        return Check(
            f"gate_flags:{source}",
            False,
            f"empty gate_flags rows: {empty_rows[:5]}",
        )
    return Check(f"gate_flags:{source}", True, "all flags are registered")


def check_spot_rows(rows: Sequence[Mapping[str, str]]) -> Check:
    if len(rows) != 7:
        return Check("spot check", False, f"expected 7 rows, got {len(rows)}")
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
    if status_counts.get("pass") != 5:
        return Check(
            "spot check",
            False,
            f"expected 5 pass rows, got {status_counts.get('pass', 0)}",
        )
    by_id = {str(row.get("anchor_id", "")): row for row in rows}
    pc = by_id.get("propylene_carbonate_298K")
    if pc is None or pc.get("status") != "not_found":
        return Check("spot check", False, "PC must be not_found")
    if pc.get("expected_value") != "64.9" or pc.get("reference_value") != "64.9":
        return Check("spot check", False, "PC manual reference must be 64.9")
    ec = by_id.get("ethylene_carbonate_temperature_guard")
    if ec is None or ec.get("status") != "blocked_temperature_gate":
        return Check("spot check", False, "EC temperature guard is missing")
    if ec.get("expected_value", "") != "" or ec.get("reference_value", "") != "":
        return Check("spot check", False, "EC guard must not fabricate a reference")
    return Check("spot check", True, "5 pass; PC not_found; EC blocked")


def check_manifest_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> Check:
    if len(rows) != 205:
        return Check("ThermoML manifest", False, f"expected 205 rows, got {len(rows)}")
    dielectric_sources = sum(
        int(str(row.get("dielectric_row_count", "0"))) > 0 for row in rows
    )
    if dielectric_sources != 91:
        return Check(
            "ThermoML manifest",
            False,
            f"expected 91 dielectric sources, got {dielectric_sources}",
        )
    row_sum = sum(int(str(row.get("dielectric_row_count", "0"))) for row in rows)
    if row_sum != 11646:
        return Check(
            "ThermoML manifest",
            False,
            f"expected dielectric row sum 11646, got {row_sum}",
        )

    raw_dir = root / "data" / "raw" / "thermoml"
    if not raw_dir.is_dir():
        return Check(
            "ThermoML manifest",
            True,
            "205 rows, 91 sources, 11646 rows; raw hash check skipped (raw XML absent)",
        )
    for row in rows:
        path = root / str(row.get("source_file", ""))
        if not path.is_file():
            return Check("ThermoML manifest", False, f"missing raw XML: {path}")
        expected_hash = str(row.get("sha256", ""))
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            return Check(
                "ThermoML manifest",
                False,
                f"SHA256 mismatch for {path.name}",
            )
        if path.stat().st_size != int(str(row.get("size_bytes", "0"))):
            return Check("ThermoML manifest", False, f"size mismatch for {path.name}")
    return Check(
        "ThermoML manifest",
        True,
        "205 rows, 91 sources, 11646 rows; 205 raw hashes verified",
    )


def check_coverage_gap(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    if len(rows) != 246:
        return Check("coverage gap", False, f"expected 246 rows, got {len(rows)}")
    if summary.get("target_308_available") is not False:
        return Check(
            "coverage gap",
            False,
            "target_308_available must be false",
        )
    return Check("coverage gap", True, "246 fallback rows; target_308 unavailable")


def check_viscosity_rows(
    experimental: Sequence[Mapping[str, str]],
    predictions: Sequence[Mapping[str, str]],
) -> Check:
    if len(experimental) != 3582:
        return Check(
            "viscosity sources",
            False,
            f"expected 3582 experimental rows, got {len(experimental)}",
        )
    if any(row.get("data_status") != "experimental" for row in experimental):
        return Check("viscosity sources", False, "experimental table has mixed statuses")
    if len(predictions) != 650:
        return Check(
            "viscosity sources",
            False,
            f"expected 650 prediction rows, got {len(predictions)}",
        )
    if any(row.get("data_status") != "predicted" for row in predictions):
        return Check("viscosity sources", False, "prediction table has mixed statuses")
    return Check(
        "viscosity sources",
        True,
        "3582 experimental; 650 predicted; statuses isolated",
    )


def check_intersection_rows(rows: Sequence[Mapping[str, str]]) -> Check:
    if len(rows) != 456:
        return Check(
            "dielectric-viscosity intersection",
            False,
            f"expected 456 paired rows, got {len(rows)}",
        )
    unique_keys = {str(row.get("inchikey", "")) for row in rows}
    if len(unique_keys) != 46:
        return Check(
            "dielectric-viscosity intersection",
            False,
            f"expected 46 paired keys, got {len(unique_keys)}",
        )
    max_delta = max(abs(float(row["temperature_delta_K"])) for row in rows)
    if max_delta > 5:
        return Check(
            "dielectric-viscosity intersection",
            False,
            f"max temperature delta {max_delta} exceeds 5 K",
        )
    if any(row.get("pair_type") != "loose_join" for row in rows):
        return Check(
            "dielectric-viscosity intersection",
            False,
            "all rows must be pair_type=loose_join",
        )
    if any(str(row.get("model_ready", "")).lower() != "false" for row in rows):
        return Check(
            "dielectric-viscosity intersection",
            False,
            "all rows must be model_ready=false",
        )
    if any(
        "not_training_ready" not in str(row.get("gate_flags", "")).split("|")
        for row in rows
    ):
        return Check(
            "dielectric-viscosity intersection",
            False,
            "all rows must carry not_training_ready",
        )
    return Check(
        "dielectric-viscosity intersection",
        True,
        "46 keys; 456 loose-join rows; max delta <=5 K; model_ready=false",
    )


def check_p2_summary(summary: Mapping[str, object]) -> Check:
    if summary.get("pass_r2_gt_0_8") is not False:
        return Check("P2 summary", False, "pass_r2_gt_0_8 must be false")
    metrics = summary.get("final_metrics")
    if not isinstance(metrics, Mapping):
        return Check("P2 summary", False, "final_metrics must be an object")
    invalid = [
        name
        for name in ("mae", "rmse", "r2")
        if not isinstance(metrics.get(name), (int, float))
        or not math.isfinite(float(metrics[name]))
    ]
    if invalid:
        return Check("P2 summary", False, f"non-finite metrics: {invalid}")
    return Check("P2 summary", True, "R2 gate false; metrics are finite")


def check_p2_artifacts(root: Path) -> Check:
    missing = [
        relative
        for relative in REPO_P2_ARTIFACTS.values()
        if not (root / relative).is_file()
    ]
    if missing:
        return Check("P2 artifact paths", False, f"missing: {missing}")
    optional_missing = [
        relative
        for relative in OPTIONAL_REPO_P2_ARTIFACTS.values()
        if not (root / relative).is_file()
    ]
    detail = "all required repository artifacts exist"
    if optional_missing:
        detail += "; model_json is export-only and absent from this checkout"
    return Check("P2 artifact paths", True, detail)


def check_notebook(path: Path) -> Check:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("P2 notebook", False, f"cannot read notebook: {exc}")
    code_cells = [
        cell
        for cell in notebook.get("cells", [])
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    ]
    if not code_cells:
        return Check("P2 notebook", False, "notebook has no code cells")
    unexecuted = [
        index
        for index, cell in enumerate(code_cells, start=1)
        if cell.get("execution_count") is None
    ]
    errors = [
        index
        for index, cell in enumerate(code_cells, start=1)
        if any(
            output.get("output_type") == "error"
            for output in cell.get("outputs", [])
            if isinstance(output, dict)
        )
    ]
    if unexecuted or errors:
        return Check(
            "P2 notebook",
            False,
            f"unexecuted cells: {unexecuted}; error cells: {errors}",
        )
    return Check("P2 notebook", True, f"{len(code_cells)} code cells executed without errors")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON document is not an object: {path}")
    return payload


def run_checks(root: Path = ROOT) -> list[Check]:
    processed = root / "data" / "processed"
    checks: list[Check] = []
    for relative in GENERATED_FLAG_FILES:
        path = root / relative
        if not path.is_file():
            checks.append(Check(f"gate_flags:{relative}", False, "missing CSV"))
            continue
        checks.append(check_gate_flags(relative, read_csv_rows(path)))

    spot_rows = read_csv_rows(processed / "p1_spot_check.csv")
    manifest_rows = read_csv_rows(processed / "thermoml_source_manifest.csv")
    coverage_rows = read_csv_rows(processed / "coverage_gap.csv")
    coverage_summary = _read_json(processed / "coverage_gap_summary.json")
    viscosity_rows = read_csv_rows(processed / "viscosity_raw.csv")
    prediction_rows = read_csv_rows(processed / "viscosity_predictions.csv")
    intersection_rows = read_csv_rows(
        processed / "dielectric_viscosity_intersection.csv"
    )
    p2_summary = _read_json(root / "probes" / "p2_summary.json")

    checks.extend(
        [
            check_spot_rows(spot_rows),
            check_manifest_rows(manifest_rows, root=root),
            check_coverage_gap(coverage_rows, coverage_summary),
            check_viscosity_rows(viscosity_rows, prediction_rows),
            check_intersection_rows(intersection_rows),
            check_p2_summary(p2_summary),
            check_p2_artifacts(root),
            check_notebook(root / "probes" / "p2_battp30k_baseline.ipynb"),
        ]
    )
    return checks


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
                {
                    "passed": not failures,
                    "checks": [asdict(check) for check in checks],
                },
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
