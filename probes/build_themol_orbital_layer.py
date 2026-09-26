"""Compose the W17-14 THEMol/GFN2-xTB orbital layer from the sharded harvest.

Inputs (raw, git-ignored): data/raw/themol/shard_*.csv plus the two rosters.
Inputs (committed): the four-core registry, the epsilon roster and the W17-12
second-source layer.
Outputs (committed): data/processed/themol_orbital_layer.csv and
probes/themol_orbital_layer_summary.json.

What this layer is
------------------
A **third** orbital source at a level of theory nothing else in the repository
uses: GFN2-xTB single points on THEMol's B3LYP-D3(BJ)/DZVP geometries.  It is
additive -- the Batt-P30K columns in four_core_key_registry.csv and the
PubChemQC columns in orbital_second_source_layer.csv are never rewritten.

The layer exists to answer one question with evidence: does a semi-empirical
Hamiltonian on someone else's DFT geometry reproduce the authoritative
wB97X-V/def2-TZVPPD/SMD(eps=18.5) level closely enough to be used, or is it
only a qualitative ordering?  The answer is produced by the same 2-fold
out-of-sample linear map the W17-12 layer uses, on the 72 molecules where a
Batt-P30K value, a THEMol geometry and a GFN2-xTB number all exist.

Honesty rules
-------------
* ``unit_check`` is a **pipeline-level** claim backed by
  ``data/raw/themol/unit_audit.json`` (see ``probes/themol_orbital_unit_audit.py``),
  not a per-row assertion that has no evidence behind it.
* ``structure_check`` is recomputed per row: the InChIKey is re-derived from the
  row's own SMILES and compared with the roster key.  It is not a constant.
* ``calib_lumo_eV`` stays empty unless the LUMO map actually passes its gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from probes.build_orbital_second_source import fit_line, fold_map, pearson, sha256_file

RAW_DIR = ROOT / "data/raw/themol"
SHARD_GLOB = "shard_*.csv"
ANCHOR_ROSTER = RAW_DIR / "themol_anchor_roster.csv"
UNIT_AUDIT = RAW_DIR / "unit_audit.json"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = ROOT / "data/dielectric_v04.csv"
SECOND_SOURCE_LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
LAYER = ROOT / "data/processed/themol_orbital_layer.csv"
SUMMARY = ROOT / "probes/themol_orbital_layer_summary.json"

SOURCE_DATASET = "ByteDance-Seed/THEMol (Hessian subset) + GFN2-xTB 6.7.1"
SOURCE_LEVEL = "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"
SOURCE_LICENSE = "THEMol CC BY-NC 4.0; derived values non-commercial"
CALIBRATION_ID = "themol_gfn2_to_batt_2fold_v1"
MIN_PAIRED_N = 40
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80

COLUMNS = [
    "inchikey",
    "name",
    "smiles",
    "canonical_smiles",
    "structure_check",
    "in_epsilon_roster",
    "epsilon",
    "in_anchor_roster",
    "themol_uuid",
    "themol_h5_file",
    "natoms",
    "geometry_sha256",
    "source_dataset",
    "source_level",
    "source_license",
    "xtb_version",
    "unit_check",
    "homo_gfn2_eV",
    "lumo_gfn2_eV",
    "gap_gfn2_eV",
    "batt_homo_eV",
    "batt_lumo_eV",
    "batt_gap_eV",
    "pubchemqc_homo_eV",
    "pubchemqc_lumo_eV",
    "gfn2_minus_batt_homo_eV",
    "gfn2_minus_batt_lumo_eV",
    "gfn2_minus_batt_gap_eV",
    "gfn2_minus_pubchemqc_homo_eV",
    "gfn2_minus_pubchemqc_lumo_eV",
    "calib_homo_eV",
    "calib_lumo_eV",
    "calibration_id",
    "role",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def q6(value: float | None) -> float | None:
    """Store a derived number at full precision.

    Rounding to six decimals was tried first and rejected: a rounded
    difference is not the difference of the rounded operands, so the verifier
    could no longer re-derive each column from its two source columns.  The
    name is kept so every call site still reads as "this is a derived value".
    """

    return None if value is None else float(value)


def num_or_none(value: object) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def inchikey_of(smiles: str | None) -> str | None:
    if not smiles:
        return None
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return Chem.MolToInchiKey(molecule)


def structure_check(smiles: str, inchikey: str) -> str:
    """Re-derive the key from the row's own SMILES instead of trusting the join."""

    derived = inchikey_of(smiles)
    if derived is None:
        return "smiles_unparsable"
    skeleton = derived.split("-")[0]
    return "inchikey_match" if skeleton == inchikey.split("-")[0] else "inchikey_mismatch"


def unit_audit_summary() -> dict[str, object]:
    if not UNIT_AUDIT.exists():
        return {"status": "missing", "n": 0, "passed": 0, "pass_rate": None, "rows": []}
    payload = json.loads(UNIT_AUDIT.read_text(encoding="utf-8"))
    rows = payload.get("checks", [])
    passed = sum(1 for row in rows if row.get("passed"))
    return {
        "status": "ok" if rows else "empty",
        "n": len(rows),
        "passed": passed,
        "pass_rate": (passed / len(rows)) if rows else None,
        "max_abs_residual_eV": max(
            (abs(row.get("residual_eV", 0.0)) for row in rows), default=None
        ),
        "rows": rows,
    }


def calibration(pairs: list[dict[str, float]]) -> dict[str, object]:
    """2-fold out-of-sample linear map y = slope * x + intercept (x=gfn2, y=batt)."""

    result: dict[str, object] = {"n": len(pairs)}
    if len(pairs) < MIN_PAIRED_N:
        result["status"] = "insufficient_pairs"
        result["min_required"] = MIN_PAIRED_N
        return result
    folds = fold_map([pair["inchikey"] for pair in pairs])
    out_of_sample: list[dict[str, object]] = []
    fold_fits: list[dict[str, object]] = []
    for held in (0, 1):
        train = [pair for pair in pairs if folds[pair["inchikey"]] != held]
        test = [pair for pair in pairs if folds[pair["inchikey"]] == held]
        if len(train) < 2 or not test:
            continue
        fit = fit_line([p["x"] for p in train], [p["y"] for p in train])
        if fit is None:
            continue
        slope, intercept = fit
        fold_fits.append(
            {
                "held_out_fold": held,
                "n_train": len(train),
                "n_test": len(test),
                "slope": slope,
                "intercept": intercept,
            }
        )
        for point in test:
            out_of_sample.append(
                {
                    "inchikey": point["inchikey"],
                    "y": point["y"],
                    "yhat": slope * point["x"] + intercept,
                }
            )
    if not out_of_sample:
        result["status"] = "no_fold"
        return result
    errors = [abs(point["yhat"] - point["y"]) for point in out_of_sample]
    mae = sum(errors) / len(errors)
    full = fit_line([p["x"] for p in pairs], [p["y"] for p in pairs])
    r = pearson([p["x"] for p in pairs], [p["y"] for p in pairs])
    result.update(
        {
            "n_out_of_sample": len(out_of_sample),
            "slope": full[0] if full else None,
            "intercept": full[1] if full else None,
            "pearson_r_in_sample": r,
            "mae_out_of_sample_eV": mae,
            "max_abs_error_out_of_sample_eV": max(errors),
            "fold_fits": fold_fits,
        }
    )
    ok = full is not None and mae <= MAE_LIMIT_EV and r is not None and r >= R_LIMIT
    result["status"] = "usable_with_flag" if ok else "reference_only"
    result["mae_limit_eV"] = MAE_LIMIT_EV
    result["r_limit"] = R_LIMIT
    return result


def summarize_offsets(values: list[float]) -> dict[str, object]:
    if not values:
        return {"n": 0, "mean_eV": None, "sigma_eV": None, "min_eV": None, "max_eV": None}
    n = len(values)
    mean = sum(values) / n
    variance = sum((value - mean) ** 2 for value in values) / n
    return {
        "n": n,
        "mean_eV": mean,
        "sigma_eV": variance**0.5,
        "min_eV": min(values),
        "max_eV": max(values),
    }


def load_shards() -> tuple[list[dict[str, str]], list[str]]:
    paths = sorted(RAW_DIR.glob(SHARD_GLOB))
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.extend(read_csv_rows(path))
    return rows, [path.name for path in paths]


def compose() -> tuple[list[dict[str, object]], dict[str, object]]:
    registry = {row["inchikey"]: row for row in read_csv_rows(REGISTRY)}
    epsilon = {row["inchikey"]: row for row in read_csv_rows(EPSILON_ROSTER)}
    second = {row["inchikey"]: row for row in read_csv_rows(SECOND_SOURCE_LAYER)}
    anchors = (
        {row["inchikey"] for row in read_csv_rows(ANCHOR_ROSTER)}
        if ANCHOR_ROSTER.exists()
        else set()
    )
    harvest_rows, shard_names = load_shards()
    audit = unit_audit_summary()

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped: list[dict[str, str]] = []
    for harvest in harvest_rows:
        inchikey = harvest.get("inchikey", "")
        homo = num_or_none(harvest.get("homo_eV"))
        lumo = num_or_none(harvest.get("lumo_eV"))
        if not inchikey or homo is None or lumo is None or inchikey in seen:
            skipped.append(
                {
                    "inchikey": inchikey,
                    "name": harvest.get("name", ""),
                    "status": harvest.get("status", ""),
                }
            )
            continue
        seen.add(inchikey)
        registry_row = registry.get(inchikey, {})
        second_row = second.get(inchikey, {})
        epsilon_row = epsilon.get(inchikey, {})
        batt_homo = num_or_none(registry_row.get("HOMO_eV"))
        batt_lumo = num_or_none(registry_row.get("LUMO_eV"))
        pubchemqc_homo = num_or_none(second_row.get("homo_eV"))
        pubchemqc_lumo = num_or_none(second_row.get("lumo_eV"))
        smiles = harvest.get("smiles", "")
        rows.append(
            {
                "inchikey": inchikey,
                "name": registry_row.get("name") or harvest.get("name", ""),
                "smiles": smiles,
                "canonical_smiles": harvest.get("canonical_smiles", ""),
                "structure_check": structure_check(smiles, inchikey),
                "in_epsilon_roster": str(inchikey in epsilon).lower(),
                "epsilon": epsilon_row.get("dielectric", ""),
                "in_anchor_roster": str(inchikey in anchors).lower(),
                "themol_uuid": harvest.get("themol_uuid", ""),
                "themol_h5_file": harvest.get("themol_h5_file", ""),
                "natoms": harvest.get("natoms", ""),
                "geometry_sha256": harvest.get("geometry_sha256", ""),
                "source_dataset": SOURCE_DATASET,
                "source_level": SOURCE_LEVEL,
                "source_license": SOURCE_LICENSE,
                "xtb_version": harvest.get("xtb_version", ""),
                "unit_check": "pipeline_audited_eV" if audit["status"] == "ok" else "unverified",
                "homo_gfn2_eV": q6(homo),
                "lumo_gfn2_eV": q6(lumo),
                "gap_gfn2_eV": q6(lumo - homo),
                "batt_homo_eV": q6(batt_homo),
                "batt_lumo_eV": q6(batt_lumo),
                "batt_gap_eV": (
                    q6(batt_lumo - batt_homo)
                    if batt_homo is not None and batt_lumo is not None
                    else None
                ),
                "pubchemqc_homo_eV": q6(pubchemqc_homo),
                "pubchemqc_lumo_eV": q6(pubchemqc_lumo),
                "gfn2_minus_batt_homo_eV": q6(homo - batt_homo) if batt_homo is not None else None,
                "gfn2_minus_batt_lumo_eV": q6(lumo - batt_lumo) if batt_lumo is not None else None,
                "gfn2_minus_batt_gap_eV": (
                    q6((lumo - homo) - (batt_lumo - batt_homo))
                    if batt_homo is not None and batt_lumo is not None
                    else None
                ),
                "gfn2_minus_pubchemqc_homo_eV": (
                    q6(homo - pubchemqc_homo) if pubchemqc_homo is not None else None
                ),
                "gfn2_minus_pubchemqc_lumo_eV": (
                    q6(lumo - pubchemqc_lumo) if pubchemqc_lumo is not None else None
                ),
            }
        )

    homo_pairs = [
        {"inchikey": r["inchikey"], "x": r["homo_gfn2_eV"], "y": r["batt_homo_eV"]}
        for r in rows
        if r["batt_homo_eV"] is not None
    ]
    lumo_pairs = [
        {"inchikey": r["inchikey"], "x": r["lumo_gfn2_eV"], "y": r["batt_lumo_eV"]}
        for r in rows
        if r["batt_lumo_eV"] is not None
    ]
    homo_cal = calibration(homo_pairs)
    lumo_cal = calibration(lumo_pairs)
    # The gap is the level-shift-invariant channel: a rigid shift of both
    # manifolds cancels out, so a gap map that fails cannot be rescued by
    # re-referencing the absolute energies.
    gap_pairs = [
        {"inchikey": r["inchikey"], "x": r["gap_gfn2_eV"], "y": r["batt_gap_eV"]}
        for r in rows
        if r["batt_gap_eV"] is not None
    ]
    gap_cal = calibration(gap_pairs)

    for row in rows:
        homo = row["homo_gfn2_eV"]
        lumo = row["lumo_gfn2_eV"]
        if homo_cal["status"] == "usable_with_flag":
            row["calib_homo_eV"] = q6(
                homo_cal["slope"] * homo + homo_cal["intercept"]  # type: ignore[operator]
            )
        else:
            row["calib_homo_eV"] = None
        if lumo_cal["status"] == "usable_with_flag":
            row["calib_lumo_eV"] = q6(
                lumo_cal["slope"] * lumo + lumo_cal["intercept"]  # type: ignore[operator]
            )
        else:
            row["calib_lumo_eV"] = None
        row["calibration_id"] = CALIBRATION_ID if row["calib_homo_eV"] is not None else ""
        if row["batt_homo_eV"] is not None:
            row["role"] = "paired_anchor"
        elif row["calib_homo_eV"] is not None:
            row["role"] = "calibrated_estimate"
        else:
            row["role"] = "uncalibrated_reference"

    rows.sort(key=lambda item: item["inchikey"])
    roles: dict[str, int] = {}
    for row in rows:
        roles[row["role"]] = roles.get(row["role"], 0) + 1
    source_counts: dict[str, int] = {}
    for path in shard_names:
        source_counts[path] = sum(1 for r in read_csv_rows(RAW_DIR / path))
    summary: dict[str, object] = {
        "arm": "W17-14",
        "source_dataset": SOURCE_DATASET,
        "source_level": SOURCE_LEVEL,
        "source_license": SOURCE_LICENSE,
        "calibration_id": CALIBRATION_ID,
        "harvest": {
            "shards": shard_names,
            "rows_by_shard": source_counts,
            "rows_total": len(harvest_rows),
            "molecules_in_layer": len(rows),
            "skipped": skipped,
            "fetched_bytes_total": sum(
                int(num_or_none(r.get("fetched_bytes")) or 0) for r in harvest_rows
            ),
            "elapsed_seconds_total": round(
                sum(num_or_none(r.get("elapsed_seconds")) or 0.0 for r in harvest_rows), 3
            ),
            "xtb_versions": sorted({r.get("xtb_version", "") for r in harvest_rows}),
        },
        "coverage": {
            "epsilon_roster_keys": len(epsilon),
            "epsilon_roster_in_layer": sum(1 for r in rows if r["in_epsilon_roster"] == "true"),
            "anchor_roster_keys": len(anchors),
            "anchor_roster_in_layer": sum(1 for r in rows if r["in_anchor_roster"] == "true"),
        },
        "structure_check": {
            "inchikey_match": sum(1 for r in rows if r["structure_check"] == "inchikey_match"),
            "inchikey_mismatch": sum(
                1 for r in rows if r["structure_check"] == "inchikey_mismatch"
            ),
            "smiles_unparsable": sum(
                1 for r in rows if r["structure_check"] == "smiles_unparsable"
            ),
        },
        "unit_check": {**audit, "claimed_value": "pipeline_audited_eV"},
        "calibration": {"homo": homo_cal, "lumo": lumo_cal, "gap": gap_cal},
        "level_offsets_gfn2_minus_batt": {
            "homo": summarize_offsets(
                [r["gfn2_minus_batt_homo_eV"] for r in rows if r["gfn2_minus_batt_homo_eV"] is not None]
            ),
            "lumo": summarize_offsets(
                [r["gfn2_minus_batt_lumo_eV"] for r in rows if r["gfn2_minus_batt_lumo_eV"] is not None]
            ),
            "gap": summarize_offsets(
                [r["gfn2_minus_batt_gap_eV"] for r in rows if r["gfn2_minus_batt_gap_eV"] is not None]
            ),
        },
        "level_offsets_gfn2_minus_pubchemqc": {
            "homo": summarize_offsets(
                [
                    r["gfn2_minus_pubchemqc_homo_eV"]
                    for r in rows
                    if r["gfn2_minus_pubchemqc_homo_eV"] is not None
                ]
            ),
            "lumo": summarize_offsets(
                [
                    r["gfn2_minus_pubchemqc_lumo_eV"]
                    for r in rows
                    if r["gfn2_minus_pubchemqc_lumo_eV"] is not None
                ]
            ),
        },
        "three_way": {
            "has_batt_and_pubchemqc": sum(
                1
                for r in rows
                if r["batt_homo_eV"] is not None and r["pubchemqc_homo_eV"] is not None
            ),
            "has_batt_only": sum(
                1
                for r in rows
                if r["batt_homo_eV"] is not None and r["pubchemqc_homo_eV"] is None
            ),
            "has_pubchemqc_only": sum(
                1
                for r in rows
                if r["batt_homo_eV"] is None and r["pubchemqc_homo_eV"] is not None
            ),
            "gfn2_only": sum(
                1
                for r in rows
                if r["batt_homo_eV"] is None and r["pubchemqc_homo_eV"] is None
            ),
        },
        "roles": roles,
    }
    return rows, summary


def render(rows: list[dict[str, object]]) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in COLUMNS})
    return buffer.getvalue()


def write_outputs(rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    LAYER.parent.mkdir(parents=True, exist_ok=True)
    LAYER.write_text(render(rows), encoding="utf-8", newline="")
    summary["layer_sha256"] = sha256_file(LAYER)
    summary["layer_rows"] = len(rows)
    summary["layer_columns"] = len(COLUMNS)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline=""
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="recompose and compare with disk")
    args = parser.parse_args(argv)

    rows, summary = compose()
    if args.check:
        expected = render(rows)
        actual = LAYER.read_text(encoding="utf-8") if LAYER.exists() else ""
        if expected != actual:
            print("MISMATCH: layer on disk differs from a fresh compose()")
            return 1
        print(f"PASS: layer byte-identical ({len(rows)} rows, sha256 {sha256_file(LAYER)[:12]})")
        return 0

    write_outputs(rows, summary)
    print(json.dumps(json.loads(json.dumps(summary)), indent=2)[:4000])
    print(f"wrote {LAYER} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())