"""Independently verify P4 redox parsing, merging, models, and artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import h5py
import nbformat
import numpy as np
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.standardize import standardize_molecule

RX_SHA256 = "d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87"
RX_SIZE = 248404
RX_ROWS = 392
P30K_ROWS = 29519
SOURCE_COMMIT = "a5101e30c6975552d97e34f1e93461126715c862"
MODEL_NAMES = ("linear", "scalar_gpr", "fingerprint_gpr")
TARGETS = ("oxidation_free_energy", "reduction_free_energy")
SPLIT_SEED = 42
TEST_FRACTION = 0.2
GATE_MAE_THRESHOLD = 0.15


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_source_file(
    path: Path,
    *,
    expected_sha256: str = RX_SHA256,
    expected_size: int = RX_SIZE,
) -> Check:
    if not path.is_file():
        return Check("P4 RX source", False, f"missing {path}")
    if path.stat().st_size != expected_size:
        return Check(
            "P4 RX source",
            False,
            f"size {path.stat().st_size} != {expected_size}",
        )
    actual = _sha256_file(path)
    if actual != expected_sha256:
        return Check("P4 RX source", False, f"SHA256 {actual} != {expected_sha256}")
    return Check("P4 RX source", True, "size and SHA256 match pinned source")


def _select_dielectric_18(value: str) -> float:
    matches = []
    for item in value.split("&"):
        if ":" not in item:
            continue
        key, raw = item.rsplit(":", 1)
        if "DIELECTRIC=18" in key:
            matches.append(float(raw))
    if len(matches) != 1:
        raise ValueError(f"expected one DIELECTRIC=18 value, got {len(matches)}")
    return matches[0]


def _parse_rx(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("$")
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        values = dict(zip(header, line.split("$")))
        ip = _select_dielectric_18(values["dictIEs"])
        raw_ea = _select_dielectric_18(values["dictEAs"])
        oxidation_potential = _select_dielectric_18(values["dictOxPots"])
        reduction_potential = _select_dielectric_18(values["dictRedPots"])
        molecule = Chem.MolFromInchi(values["Inchi"])
        if molecule is None:
            raise ValueError(f"cannot parse InChI at line {line_number}")
        smiles = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        standardized = standardize_molecule(smiles)
        rows.append(
            {
                "row_id": f"rx392:{values['MolId']}",
                "IP": ip,
                "EA": -raw_ea,
                "oxidation_free_energy": oxidation_potential + 4.44,
                "reduction_free_energy": -(reduction_potential + 4.44),
                "raw_EA": raw_ea,
                "oxidation_potential": oxidation_potential,
                "reduction_potential": reduction_potential,
                "smiles": standardized.smiles,
                "inchikey": standardized.inchikey,
            }
        )
    return rows


def check_formula_recomputation(
    raw_rows: Sequence[Mapping[str, object]],
    merged_rows: Sequence[Mapping[str, object]],
) -> Check:
    if len(raw_rows) != len(merged_rows):
        return Check(
            "P4 RX formulas",
            False,
            f"row count mismatch: {len(raw_rows)} != {len(merged_rows)}",
        )
    for index, (raw, merged) in enumerate(zip(raw_rows, merged_rows, strict=True)):
        for identity_field in ("row_id", "smiles", "inchikey"):
            if raw.get(identity_field) != merged.get(identity_field):
                return Check(
                    "P4 RX formulas",
                    False,
                    f"{identity_field} mismatch at row {index}",
                )
        expected = {
            "EA": -float(raw["raw_EA"]),
            "oxidation_free_energy": float(raw["oxidation_potential"]) + 4.44,
            "reduction_free_energy": -(float(raw["reduction_potential"]) + 4.44),
        }
        for field, value in expected.items():
            try:
                actual = float(merged[field])
            except (KeyError, TypeError, ValueError):
                return Check(
                    "P4 RX formulas",
                    False,
                    f"{field} missing/non-numeric at row {index}",
                )
            if not math.isclose(actual, value, rel_tol=1e-12, abs_tol=1e-12):
                return Check(
                    "P4 RX formulas",
                    False,
                    f"{field} mismatch at row {index}: {actual} != {value}",
                )
    return Check("P4 RX formulas", True, "392 EA/oxidation/reduction formulas recomputed")


def check_merged_hash(summary: Mapping[str, object], path: Path) -> Check:
    merged = summary.get("merged")
    if not isinstance(merged, Mapping):
        return Check("P4 merged hash", False, "summary merged section is missing")
    actual = _sha256_file(path)
    if merged.get("sha256") != actual:
        return Check(
            "P4 merged hash",
            False,
            f"SHA256 mismatch: {actual}",
        )
    return Check("P4 merged hash", True, "merged CSV SHA256 matches summary")


def check_model_configs(summary: Mapping[str, object]) -> Check:
    configs = summary.get("model_configs")
    if not isinstance(configs, Mapping):
        return Check("P4 model configs", False, "model_configs is missing")
    expected_keys = {
        f"{target}:{model}" for target in TARGETS for model in MODEL_NAMES
    }
    if set(configs) != expected_keys:
        return Check("P4 model configs", False, "model config key set mismatch")
    for key, value in configs.items():
        text = str(value)
        if not key.endswith(":linear"):
            if "random_state=42" not in text:
                return Check("P4 model configs", False, f"{key} lacks seed 42")
            if "initial_kernel=" not in text or "final_kernel=" not in text:
                return Check("P4 model configs", False, f"{key} lacks kernel evidence")
    return Check("P4 model configs", True, "all six fixed model configs recorded")


def check_merged_counts(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_rx: int,
    expected_p30k: int,
) -> Check:
    counts = Counter(str(row.get("source", "")) for row in rows)
    if counts.get("RX-392") != expected_rx:
        return Check(
            "P4 merged counts",
            False,
            f"RX-392 count {counts.get('RX-392')} != {expected_rx}",
        )
    if counts.get("Batt-P30K") != expected_p30k:
        return Check(
            "P4 merged counts",
            False,
            f"Batt-P30K count {counts.get('Batt-P30K')} != {expected_p30k}",
        )
    if len(rows) != expected_rx + expected_p30k:
        return Check(
            "P4 merged counts",
            False,
            f"total {len(rows)} != {expected_rx + expected_p30k}",
        )
    return Check(
        "P4 merged counts",
        True,
        f"RX-392={expected_rx}, Batt-P30K={expected_p30k}, total={len(rows)}",
    )


def check_h5_rows(path: Path) -> Check:
    if not path.is_file():
        return Check(
            "P4 H5 rows",
            True,
            f"skipped: {path} is not present in this checkout",
        )
    required = {"smiles", "ip", "ea", "homo", "lumo", "dipole"}
    with h5py.File(path, "r") as handle:
        keys = sorted(handle.keys())
        if len(keys) != P30K_ROWS:
            return Check(
                "P4 H5 rows",
                False,
                f"{len(keys)} groups != {P30K_ROWS}",
            )
        for key in (keys[0], keys[len(keys) // 2], keys[-1]):
            missing = required - set(handle[key].keys())
            if missing:
                return Check(
                    "P4 H5 rows",
                    False,
                    f"{key} missing {sorted(missing)}",
                )
    return Check("P4 H5 rows", True, f"{P30K_ROWS} groups with required fields")


def _metrics(rows: Sequence[Mapping[str, str]]) -> dict[str, float]:
    target = np.asarray([float(row["target"]) for row in rows], dtype=float)
    prediction = np.asarray([float(row["prediction"]) for row in rows], dtype=float)
    residual = target - prediction
    mean = float(np.mean(target))
    denominator = float(np.sum((target - mean) ** 2))
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "r2": (
            float(1.0 - np.sum(residual**2) / denominator)
            if denominator
            else float("nan")
        ),
    }


def check_metrics_from_predictions(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    summary_metrics = summary.get("metrics")
    if not isinstance(summary_metrics, Mapping):
        return Check("P4 metrics", False, "summary metrics are missing")
    for target in TARGETS:
        for model in MODEL_NAMES:
            selected = [
                row
                for row in rows
                if row.get("target_name") == target
                and row.get("model") == model
                and row.get("split") == "test"
                and row.get("used_for_metrics") == "true"
            ]
            if not selected:
                return Check(
                    "P4 metrics",
                    False,
                    f"no held-out rows for {target}/{model}",
                )
            recomputed = _metrics(selected)
            expected = summary_metrics[target][model]
            for metric, value in recomputed.items():
                if not math.isclose(
                    value,
                    float(expected[metric]),
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    return Check(
                        "P4 metrics",
                        False,
                        f"{target}/{model} {metric} mismatch",
                    )
    return Check("P4 metrics", True, "all 6 model/target metrics recomputed")


def check_split(
    merged_rx_rows: Sequence[Mapping[str, str]],
    prediction_rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, object],
) -> Check:
    indices = np.random.default_rng(SPLIT_SEED).permutation(len(merged_rx_rows))
    test_count = max(1, round(len(merged_rx_rows) * TEST_FRACTION))
    train_indices = {int(value) for value in indices[test_count:]}
    test_indices = {int(value) for value in indices[:test_count]}
    expected_hash = hashlib.sha256(
        "|".join(
            merged_rx_rows[index]["row_id"] for index in sorted(test_indices)
        ).encode("utf-8")
    ).hexdigest()
    split_summary = summary.get("split")
    if not isinstance(split_summary, Mapping):
        return Check("P4 split", False, "summary split is missing")
    if (
        split_summary.get("seed") != SPLIT_SEED
        or split_summary.get("train_count") != len(train_indices)
        or split_summary.get("test_count") != len(test_indices)
        or split_summary.get("test_id_hash") != expected_hash
    ):
        return Check("P4 split", False, "summary split contract mismatch")
    for target in TARGETS:
        for model in MODEL_NAMES:
            selected = [
                row
                for row in prediction_rows
                if row["target_name"] == target and row["model"] == model
            ]
            if len(selected) != len(merged_rx_rows):
                return Check(
                    "P4 split",
                    False,
                    f"{target}/{model} row count mismatch",
                )
            by_id = {
                row["row_id"]: row for row in selected
            }
            for index, merged in enumerate(merged_rx_rows):
                row = by_id.get(merged["row_id"])
                if row is None:
                    return Check("P4 split", False, "prediction row missing")
                expected_split = "train" if index in train_indices else "test"
                expected_used = "false" if index in train_indices else "true"
                if row["split"] != expected_split or row["used_for_metrics"] != expected_used:
                    return Check(
                        "P4 split",
                        False,
                        f"split mismatch for {merged['row_id']}",
                    )
    return Check("P4 split", True, "fixed 80/20 split and test hash match")


def check_gate(summary: Mapping[str, object]) -> Check:
    metrics = summary.get("metrics")
    gate = summary.get("gate")
    if not isinstance(metrics, Mapping) or not isinstance(gate, Mapping):
        return Check("P4 gate", False, "metrics or gate missing")
    best = {
        target: min(
            float(metrics[target][model]["mae"]) for model in MODEL_NAMES
        )
        for target in TARGETS
    }
    expected_passed = all(value < GATE_MAE_THRESHOLD for value in best.values())
    if gate.get("passed") != expected_passed:
        return Check("P4 gate", False, "gate pass flag mismatch")
    for target, value in best.items():
        if not math.isclose(
            value,
            float(gate["best_model_mae"][target]),
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            return Check("P4 gate", False, f"{target} best MAE mismatch")
    return Check("P4 gate", True, f"best MAE={best}")


def check_308_status(record: Mapping[str, object]) -> Check:
    if record.get("status") != "unavailable" or record.get("rows") != 0:
        return Check("P4 308 status", False, "308 must be unavailable with 0 rows")
    return Check("P4 308 status", True, "308 unavailable and no rows fabricated")


def check_notebook(path: Path) -> Check:
    if not path.is_file():
        return Check("P4 notebook", False, f"missing {path}")
    notebook = nbformat.read(path, as_version=4)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells:
        return Check("P4 notebook", False, "notebook has no code cells")
    for index, cell in enumerate(code_cells, start=1):
        if cell.get("execution_count") is None:
            return Check("P4 notebook", False, f"code cell {index} not executed")
        if cell.get("outputs") and any(
            output.get("output_type") == "error" for output in cell["outputs"]
        ):
            return Check("P4 notebook", False, f"code cell {index} has an error")
    return Check("P4 notebook", True, f"{len(code_cells)} code cells executed")


def run_checks(root: Path = ROOT) -> list[Check]:
    rx_path = root / "data" / "external" / "Batt-SLM-RX-392.csv"
    batt_path = root / "data" / "raw" / "batt" / "Batt-P30K.h5"
    merged_path = root / "data" / "processed" / "redox_merged.csv"
    predictions_path = root / "data" / "processed" / "p4_redox_predictions.csv"
    summary_path = root / "probes" / "p4_redox_summary.json"
    linear_plot = root / "probes" / "artifacts" / "p4_redox_linear.png"
    parity_plot = root / "probes" / "artifacts" / "p4_redox_parity.png"
    notebook_path = root / "probes" / "p4_redox_baseline.ipynb"
    required = (
        rx_path,
        merged_path,
        predictions_path,
        summary_path,
        linear_plot,
        parity_plot,
        notebook_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return [Check("P4 artifacts", False, f"missing: {missing}")]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    merged_rows = read_csv_rows(merged_path)
    prediction_rows = read_csv_rows(predictions_path)
    rx_rows = _parse_rx(rx_path)
    merged_rx_rows = [row for row in merged_rows if row["source"] == "RX-392"]
    return [
        check_source_file(rx_path),
        Check(
            "P4 RX rows",
            len(rx_rows) == RX_ROWS,
            f"{len(rx_rows)} rows",
        ),
        check_formula_recomputation(rx_rows, merged_rx_rows),
        check_merged_counts(
            merged_rows,
            expected_rx=RX_ROWS,
            expected_p30k=P30K_ROWS,
        ),
        check_h5_rows(batt_path),
        check_merged_hash(summary, merged_path),
        check_model_configs(summary),
        check_metrics_from_predictions(prediction_rows, summary),
        check_split(merged_rx_rows, prediction_rows, summary),
        check_gate(summary),
        check_308_status(summary["sources"]["ecw_308"]),
        check_notebook(notebook_path),
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
            print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
        print(f"{len(checks) - len(failures)}/{len(checks)} checks passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
