"""Independently verify the W17-17 THEMol/GFN2-xTB registry-wide orbital layer.

Nothing here imports the builder.  Every derived column is re-derived from its
two source columns, the 2-fold calibration is re-fit from scratch, and the
roster digest is checked against the prereg that was frozen before the run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data/processed/themol_orbital_layer_expanded.csv"
SUMMARY = ROOT / "probes/themol_orbital_layer_expanded_summary.json"
PREREG = ROOT / "probes/themol_registry_expansion_prereg.json"
ROSTER = ROOT / "probes/themol_registry_expansion_roster.csv"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"

EXPECTED_COLUMNS = [
    "inchikey", "name", "smiles", "canonical_smiles", "expansion_tier",
    "structure_check", "in_epsilon_roster", "epsilon", "has_reference_orbital",
    "themol_uuid", "themol_h5_file", "natoms", "geometry_sha256",
    "source_dataset", "source_level", "source_license", "xtb_version",
    "unit_check", "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV",
    "batt_homo_eV", "batt_lumo_eV", "batt_gap_eV",
    "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV", "gfn2_minus_batt_gap_eV",
    "gfn2_minus_pubchemqc_homo_eV", "gfn2_minus_pubchemqc_lumo_eV",
    "calib_homo_eV", "calib_lumo_eV", "calibration_id", "role",
]

ALLOWED_ROLES = {"paired_anchor", "calibrated_estimate", "uncalibrated_reference"}
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80
MIN_PAIRED_N = 40
CALIBRATION_ID = "themol_gfn2_to_batt_2fold_v2_registry_wide"
SOURCE_DATASET = "ByteDance-Seed/THEMol (Hessian subset) + GFN2-xTB 6.7.1"
SOURCE_LEVEL = "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"
SOURCE_LICENSE = "THEMol CC BY-NC 4.0; derived values non-commercial"
UNIT_CLAIM = "pipeline_audited_eV_w17_14_unit_audit"
TOL = 1e-9
STAT_TOL = 1e-6


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def num(value: object) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def fit_line(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def fold_map(keys: list[str], folds: int = 2) -> dict[str, int]:
    return {key: index % folds for index, key in enumerate(sorted(keys))}


def refit(pairs: list[dict[str, object]]) -> dict[str, object]:
    if len(pairs) < MIN_PAIRED_N:
        return {"status": "insufficient_pairs", "n": len(pairs)}
    folds = fold_map([str(pair["inchikey"]) for pair in pairs])
    errors: list[float] = []
    observed: list[float] = []
    predicted: list[float] = []
    for held in (0, 1):
        train = [p for p in pairs if folds[str(p["inchikey"])] != held]
        test = [p for p in pairs if folds[str(p["inchikey"])] == held]
        if len(train) < 2 or not test:
            continue
        fit = fit_line([float(p["x"]) for p in train], [float(p["y"]) for p in train])
        if fit is None:
            continue
        slope, intercept = fit
        for point in test:
            yhat = slope * float(point["x"]) + intercept
            errors.append(abs(yhat - float(point["y"])))
            observed.append(float(point["y"]))
            predicted.append(yhat)
    if not errors:
        return {"status": "no_fold", "n": len(pairs)}
    mae = sum(errors) / len(errors)
    full = fit_line([float(p["x"]) for p in pairs], [float(p["y"]) for p in pairs])
    r = pearson([float(p["x"]) for p in pairs], [float(p["y"]) for p in pairs])
    # The gate is decided on out-of-sample statistics only (audit W17-17/F1):
    # the in-sample r is still reported, but it no longer decides the status.
    r_out = pearson(predicted, observed) if len(observed) >= 2 else None
    ok = full is not None and mae <= MAE_LIMIT_EV and r_out is not None and r_out >= R_LIMIT
    return {
        "status": "usable_with_flag" if ok else "reference_only",
        "status_basis": "out_of_sample_mae_and_out_of_sample_r",
        "n": len(pairs),
        "n_out_of_sample": len(errors),
        "slope": full[0] if full else None,
        "intercept": full[1] if full else None,
        "pearson_r_in_sample": r,
        "pearson_r_out_of_sample": r_out,
        "mae_out_of_sample_eV": mae,
        "max_abs_error_out_of_sample_eV": max(errors),
    }


def close(a: object, b: object, tol: float = TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def inchikey_skeleton(smiles: str) -> str:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles) if smiles else None
    if molecule is None:
        return "smiles_unparsable"
    return Chem.MolToInchiKey(molecule).split("-")[0]


def check() -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        failures.append("prereg status is not locked_before_run")
    if prereg.get("is_a_plan_not_a_measurement") is not True:
        failures.append("prereg does not declare itself a plan")
    if prereg.get("queries_executed") != 0:
        failures.append("prereg queries_executed must be 0")
    if sha256_file(ROSTER) != prereg["inputs"]["target_roster"]["sha256"]:
        failures.append("roster digest differs from the prereg")
    if sha256_file(REGISTRY) != prereg["inputs"]["registry"]["sha256"]:
        failures.append("registry (prior arm) changed since the prereg")

    roster_rows = read_rows(ROSTER)
    roster_by_key = {row["inchikey"]: row for row in roster_rows}
    layer_rows = read_rows(LAYER)
    with LAYER.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    if header != EXPECTED_COLUMNS:
        failures.append("layer header does not match the frozen column list")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    if summary.get("roster_rows") != len(roster_rows):
        failures.append("summary roster_rows does not match the roster file")
    if summary.get("delivered_rows") != len(layer_rows):
        failures.append("summary delivered_rows does not match the layer")
    expected_status = "complete" if len(layer_rows) == len(roster_rows) else "partial"
    if summary.get("run_status") != expected_status:
        failures.append("run_status does not match the delivered row count")

    seen: set[str] = set()
    homo_pairs: list[dict[str, object]] = []
    lumo_pairs: list[dict[str, object]] = []
    gap_pairs: list[dict[str, object]] = []
    roles: dict[str, int] = {}
    tiers: dict[str, int] = {}
    structure: dict[str, int] = {
        "inchikey_match": 0,
        "inchikey_mismatch": 0,
        "smiles_unparsable": 0,
    }
    for index, row in enumerate(layer_rows, start=2):
        key = row["inchikey"]
        where = f"row {index} ({key})"
        if key not in roster_by_key:
            failures.append(f"{where} is not in the frozen roster")
            continue
        if key in seen:
            failures.append(f"{where} is a duplicate key")
        seen.add(key)
        roster_row = roster_by_key[key]
        if row["expansion_tier"] != roster_row["expansion_tier"]:
            failures.append(f"{where} tier disagrees with the roster")
        if row["themol_uuid"] != roster_row["themol_uuid"]:
            failures.append(f"{where} uuid disagrees with the roster")
        if row["in_epsilon_roster"] not in ("true", "false"):
            failures.append(f"{where} in_epsilon_roster is not a bool literal")
        if row["has_reference_orbital"] != roster_row["has_orbitals"]:
            failures.append(f"{where} has_reference_orbital disagrees with the roster")
        for field, constant in (
            ("source_dataset", SOURCE_DATASET),
            ("source_level", SOURCE_LEVEL),
            ("source_license", SOURCE_LICENSE),
            ("unit_check", UNIT_CLAIM),
        ):
            if row[field] != constant:
                failures.append(f"{where} {field} is not the frozen constant")
        if not row["geometry_sha256"]:
            failures.append(f"{where} has no geometry digest")
        derived = inchikey_skeleton(row["smiles"])
        expected_check = "smiles_unparsable" if derived == "smiles_unparsable" else ("inchikey_match" if derived == key.split("-")[0] else "inchikey_mismatch")
        stored = row["structure_check"]
        if stored != expected_check:
            failures.append(f"{where} structure_check {stored} != {expected_check}")
        structure[stored] = structure.get(stored, 0) + 1
        homo = num(row["homo_gfn2_eV"])
        lumo = num(row["lumo_gfn2_eV"])
        gap = num(row["gap_gfn2_eV"])
        if homo is None or lumo is None or gap is None:
            failures.append(f"{where} has a missing GFN2 level")
            continue
        if not close(gap, lumo - homo):
            failures.append(f"{where} gap != lumo - homo")
        batt_homo = num(row["batt_homo_eV"])
        batt_lumo = num(row["batt_lumo_eV"])
        batt_gap = num(row["batt_gap_eV"])
        pc_homo = num(row["pubchemqc_homo_eV"])
        pc_lumo = num(row["pubchemqc_lumo_eV"])
        pairs_to_check = (
            ("gfn2_minus_batt_homo_eV", batt_homo, homo - batt_homo if batt_homo is not None else None),
            ("gfn2_minus_batt_lumo_eV", batt_lumo, lumo - batt_lumo if batt_lumo is not None else None),
            ("gfn2_minus_batt_gap_eV", batt_gap, gap - batt_gap if batt_gap is not None else None),
            ("gfn2_minus_pubchemqc_homo_eV", pc_homo, homo - pc_homo if pc_homo is not None else None),
            ("gfn2_minus_pubchemqc_lumo_eV", pc_lumo, lumo - pc_lumo if pc_lumo is not None else None),
        )
        for field, source, want in pairs_to_check:
            if source is None and num(row[field]) is not None:
                failures.append(f"{where} {field} is set although its source is missing")
            if source is not None and not close(num(row[field]), want):
                failures.append(f"{where} {field} is not the difference")
        if row["role"] not in ALLOWED_ROLES:
            failures.append(f"{where} role is not allowed")
        roles[row["role"]] = roles.get(row["role"], 0) + 1
        tiers[row["expansion_tier"]] = tiers.get(row["expansion_tier"], 0) + 1
        if batt_homo is not None:
            homo_pairs.append({"inchikey": key, "x": homo, "y": batt_homo})
        if batt_lumo is not None:
            lumo_pairs.append({"inchikey": key, "x": lumo, "y": batt_lumo})
        if batt_gap is not None:
            gap_pairs.append({"inchikey": key, "x": gap, "y": batt_gap})

    recomputed_cal = {
        "homo": refit(homo_pairs),
        "lumo": refit(lumo_pairs),
        "gap": refit(gap_pairs),
    }
    for channel, expected in recomputed_cal.items():
        recorded = summary["calibration"].get(channel, {})
        if recorded.get("status") != expected.get("status"):
            failures.append(f"{channel} calibration status disagrees with the refit")
            continue
        for field in ("n", "n_out_of_sample"):
            if expected.get(field) is not None and recorded.get(field) != expected.get(field):
                failures.append(f"{channel} calibration {field} disagrees")
        for field in (
            "slope",
            "intercept",
            "pearson_r_in_sample",
            "pearson_r_out_of_sample",
            "mae_out_of_sample_eV",
            "max_abs_error_out_of_sample_eV",
        ):
            if not close(recorded.get(field), expected.get(field), STAT_TOL):
                failures.append(f"{channel} calibration {field} disagrees")
        if recorded.get("status_basis") != expected.get("status_basis"):
            failures.append(f"{channel} calibration status_basis disagrees")

    homo_gate = recomputed_cal["homo"]["status"] == "usable_with_flag"
    lumo_gate = recomputed_cal["lumo"]["status"] == "usable_with_flag"
    slope = recomputed_cal["homo"]["slope"]
    intercept = recomputed_cal["homo"]["intercept"]
    for index, row in enumerate(layer_rows, start=2):
        if (num(row["calib_homo_eV"]) is not None) != homo_gate:
            failures.append(f"row {index} calib_homo_eV presence disagrees with the gate")
            break
        if (num(row["calib_lumo_eV"]) is not None) != lumo_gate:
            failures.append(f"row {index} calib_lumo_eV presence disagrees with the gate")
            break
        if homo_gate and not close(
            num(row["calib_homo_eV"]),
            slope * float(row["homo_gfn2_eV"]) + intercept,
            STAT_TOL,
        ):
            failures.append(f"row {index} calib_homo_eV is not the fitted map")
            break
        if homo_gate and row["calibration_id"] != CALIBRATION_ID:
            failures.append(f"row {index} calibration_id is not the frozen id")
            break
        if not homo_gate and row["calibration_id"]:
            failures.append(f"row {index} carries a calibration_id with no calibrated value")
            break

    if summary.get("roles") != roles:
        failures.append("summary roles disagrees with the layer")
    if summary.get("rows_by_tier") != tiers:
        failures.append("summary rows_by_tier disagrees with the layer")
    if summary.get("structure_check") != structure:
        failures.append("summary structure_check disagrees with the layer")
    stats = {
        "layer_rows": len(layer_rows),
        "roster_rows": len(roster_rows),
        "run_status": summary.get("run_status"),
        "homo_pairs": len(homo_pairs),
        "calibration_status": {key: value["status"] for key, value in recomputed_cal.items()},
        "failures": len(failures),
    }
    return failures, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="run the independent recomputation")
    parser.parse_args(argv)
    failures, stats = check()
    print(json.dumps(stats, indent=2, sort_keys=True))
    if failures:
        for failure in failures[:40]:
            print("FAIL", failure)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
