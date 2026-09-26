"""Compose the W17-17 THEMol/GFN2-xTB registry-wide orbital layer.

W17-14 harvested 166 molecules and answered the cross-level question on 74
paired anchors.  This arm runs the *whole* covered set -- every one of the
5,117 keys in ``data/processed/four_core_key_registry.csv`` that THEMol's
Hessian pool contains -- so the same question is asked again with roughly
sixty times the evidence, and so the 421 covered molecules that had no orbital
number at all get one (reference-only, because the level of theory does not
change).

Inputs (raw, git-ignored): ``data/raw/themol/expand/shard_*.csv`` plus the
two rosters.  Inputs (committed): the four-core registry, the epsilon roster
and the W17-12 second-source layer.

Outputs (committed): ``data/processed/themol_orbital_layer_expanded.csv`` and
``probes/themol_orbital_layer_expanded_summary.json``.  The W17-14 layer and
the registry are never touched: this file is purely additive.

Honesty rules, carried over verbatim from W17-14
-----------------------------------------------
* ``structure_check`` is recomputed per row from the row own SMILES.
* ``calib_*_eV`` stays empty unless that channel actually passes its gate.
* rows that are not in the frozen roster are excluded **and counted**, never
  silently dropped; a shard file still being written is reported as
  ``partial`` with malformed lines counted rather than parsed as data.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.build_themol_orbital_layer import (
    MAE_LIMIT_EV,
    MIN_PAIRED_N,
    R_LIMIT,
    calibration,
    fold_map,
    num_or_none,
    pearson,
    q6,
    read_csv_rows,
    sha256_file,
    structure_check,
    summarize_offsets,
)

RAW_DIR = REPOSITORY_ROOT / "data/raw/themol/expand"
SHARD_PREFIX = "shard_"
ROSTER = REPOSITORY_ROOT / "probes/themol_registry_expansion_roster.csv"
ROSTER_SUMMARY = REPOSITORY_ROOT / "probes/themol_registry_expansion_roster_summary.json"
REGISTRY = REPOSITORY_ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = REPOSITORY_ROOT / "data/dielectric_v04.csv"
SECOND_SOURCE_LAYER = REPOSITORY_ROOT / "data/processed/orbital_second_source_layer.csv"
LAYER = REPOSITORY_ROOT / "data/processed/themol_orbital_layer_expanded.csv"
UNIT_RECHECK = REPOSITORY_ROOT / "data/raw/themol/expand_unit_recheck.json"
SUMMARY = REPOSITORY_ROOT / "probes/themol_orbital_layer_expanded_summary.json"

ARM = "W17-17"
SOURCE_DATASET = "ByteDance-Seed/THEMol (Hessian subset) + GFN2-xTB 6.7.1"
SOURCE_LEVEL = "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"
SOURCE_LICENSE = "THEMol CC BY-NC 4.0; derived values non-commercial"
CALIBRATION_ID = "themol_gfn2_to_batt_2fold_v2_registry_wide"

COLUMNS = [
    "inchikey",
    "name",
    "smiles",
    "canonical_smiles",
    "expansion_tier",
    "structure_check",
    "in_epsilon_roster",
    "epsilon",
    "has_reference_orbital",
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

UNIT_CHECK_CLAIM = "pipeline_audited_eV_w17_14_unit_audit"


def load_expansion_shards() -> tuple[list[dict[str, str]], dict[str, object]]:
    """Read every finished or in-flight expansion shard.

    A shard that is still being written can end in a half-flushed line, so the
    reader keeps only lines with exactly the expected field count and reports
    the rest as ``malformed_lines``.  Nothing is inferred about a line that
    does not parse.
    """

    paths = sorted(path for path in RAW_DIR.glob(SHARD_PREFIX + "*.csv") if path.is_file())
    rows: list[dict[str, str]] = []
    per_shard: dict[str, int] = {}
    malformed: dict[str, int] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in text.split("\n") if line.strip()]
        if not lines:
            per_shard[path.name] = 0
            malformed[path.name] = 0
            continue
        header = next(csv.reader([lines[0]]))
        width = len(header)
        good = 0
        bad = 0
        buffer_lines = [lines[0]]
        for line in lines[1:]:
            if len(next(csv.reader([line]))) != width:
                bad += 1
                continue
            buffer_lines.append(line)
            good += 1
        per_shard[path.name] = good
        malformed[path.name] = bad
        rows.extend(csv.DictReader(buffer_lines))
    return rows, {"shard_files": [p.name for p in paths], "rows_by_shard": per_shard, "malformed_lines_by_shard": malformed}


def out_of_sample_r(channel_pairs: list[dict[str, object]], cal: dict[str, object]) -> float | None:
    """Pearson r over the fold-out predictions, i.e. over the same points as the MAE.

    ``calibration`` (W17-14) reports an *in-sample* Pearson r next to an
    out-of-sample MAE; audit W17-17/F1 flagged mixing the two.  This rebuilds
    the fold map that produced ``fold_fits`` and correlates observed against
    predicted on exactly the held-out points, so the gate below can be decided
    on out-of-sample statistics alone.
    """

    fits = cal.get("fold_fits") or []
    if not fits:
        return None
    folds = fold_map([str(pair["inchikey"]) for pair in channel_pairs])
    by_fold = {int(fit["held_out_fold"]): fit for fit in fits}
    observed: list[float] = []
    predicted: list[float] = []
    for pair in channel_pairs:
        fit = by_fold.get(folds[str(pair["inchikey"])])
        if fit is None:
            continue
        observed.append(float(pair["y"]))
        predicted.append(float(fit["slope"]) * float(pair["x"]) + float(fit["intercept"]))
    if len(observed) < 2:
        return None
    return pearson(predicted, observed)


def apply_out_of_sample_gate(
    cal: dict[str, object], channel_pairs: list[dict[str, object]]
) -> dict[str, object]:
    """Re-decide ``status`` on out-of-sample statistics only; the limits are unchanged."""

    if cal.get("slope") is None or cal.get("mae_out_of_sample_eV") is None:
        cal["status_basis"] = "insufficient_evidence"
        return cal
    r_out = out_of_sample_r(channel_pairs, cal)
    cal["pearson_r_out_of_sample"] = r_out
    cal["status_basis"] = "out_of_sample_mae_and_out_of_sample_r"
    passes = (
        float(cal["mae_out_of_sample_eV"]) <= MAE_LIMIT_EV
        and r_out is not None
        and r_out >= R_LIMIT
    )
    cal["status"] = "usable_with_flag" if passes else "reference_only"
    return cal


def unit_recheck_evidence() -> dict[str, object]:
    """Evidence behind the per-row eV claim for *this* layer.

    Audit W17-17/F6 found the claim rested on 8 molecules from another arm.
    ``probes/themol_expand_unit_recheck.py`` re-derives a seeded sample of this
    layer's own rows, so the JSON is cited together with the layer digest it
    was run against and the share of rows it actually covers.
    """

    if not UNIT_RECHECK.exists():
        return {"status": "absent", "path": str(UNIT_RECHECK.relative_to(REPOSITORY_ROOT))}
    payload = json.loads(UNIT_RECHECK.read_text(encoding="utf-8"))
    return {
        "status": "present",
        "path": str(UNIT_RECHECK.relative_to(REPOSITORY_ROOT)),
        "sha256": sha256_file(UNIT_RECHECK),
        "layer_sha256_at_recheck": payload.get("layer_sha256"),
        "n_rechecked": payload.get("n_sampled"),
        "sample_share": payload.get("sample_share"),
        "max_abs_delta_homo_eV": payload.get("max_abs_delta_homo_eV"),
        "max_abs_delta_lumo_eV": payload.get("max_abs_delta_lumo_eV"),
        "all_passed": payload.get("all_passed"),
        "independent_parser": payload.get("independent_parser"),
    }


def compose() -> tuple[list[dict[str, object]], dict[str, object]]:
    roster_rows = read_csv_rows(ROSTER)
    roster_summary = json.loads(ROSTER_SUMMARY.read_text(encoding="utf-8"))
    roster_by_key = {row["inchikey"]: row for row in roster_rows}
    registry = {row["inchikey"]: row for row in read_csv_rows(REGISTRY)}
    epsilon = {row["inchikey"]: row for row in read_csv_rows(EPSILON_ROSTER)}
    second = {row["inchikey"]: row for row in read_csv_rows(SECOND_SOURCE_LAYER)}

    harvest_rows, shard_meta = load_expansion_shards()

    rows: list[dict[str, object]] = []
    off_roster: list[dict[str, str]] = []
    duplicate_keys: list[str] = []
    failed_rows: list[dict[str, str]] = []
    # A resume pass writes a second file per shard, so the same key can appear
    # twice: once as a failure from the run that got throttled and once as a
    # real number.  Keep the row that carries a number, and count **every**
    # collision (plus how many of them upgraded a failure into a number) so that
    # nothing can be dropped without showing up in the summary.  Audit
    # W17-17/F2: the off-roster and duplicate branches used to sit *after* an
    # unfiltered ``continue`` and were therefore unreachable dead code.
    best: dict[str, dict[str, str]] = {}
    duplicate_upgrades = 0
    for harvest in harvest_rows:
        key = (harvest.get("inchikey") or "").strip()
        if key not in roster_by_key:
            off_roster.append(
                {"inchikey": key or harvest.get("name", ""), "status": harvest.get("status", "")}
            )
            continue
        current = best.get(key)
        if current is None:
            best[key] = harvest
            continue
        duplicate_keys.append(key)
        if current.get("status") != "ok" and harvest.get("status") == "ok":
            best[key] = harvest
            duplicate_upgrades += 1
    harvest_rows = list(best.values())
    for harvest in harvest_rows:
        inchikey = (harvest.get("inchikey") or "").strip()
        homo = num_or_none(harvest.get("homo_eV"))
        lumo = num_or_none(harvest.get("lumo_eV"))
        if homo is None or lumo is None or harvest.get("status") != "ok":
            failed_rows.append({"inchikey": inchikey, "name": harvest.get("name", ""), "status": harvest.get("status", "")})
            continue
        roster_row = roster_by_key[inchikey]
        registry_row = registry.get(inchikey, {})
        second_row = second.get(inchikey, {})
        epsilon_row = epsilon.get(inchikey, {})
        batt_homo = num_or_none(registry_row.get("HOMO_eV"))
        batt_lumo = num_or_none(registry_row.get("LUMO_eV"))
        batt_gap = num_or_none(registry_row.get("gap_eV"))
        pubchemqc_homo = num_or_none(second_row.get("homo_eV"))
        pubchemqc_lumo = num_or_none(second_row.get("lumo_eV"))
        smiles = harvest.get("smiles", "")
        gap = num_or_none(harvest.get("gap_eV"))
        if gap is None:
            gap = lumo - homo
        rows.append(
            {
                "inchikey": inchikey,
                "name": roster_row.get("name") or harvest.get("name", ""),
                "smiles": smiles,
                "canonical_smiles": harvest.get("canonical_smiles", ""),
                "expansion_tier": roster_row.get("expansion_tier", ""),
                "structure_check": structure_check(smiles, inchikey),
                "in_epsilon_roster": str(inchikey in epsilon).lower(),
                "epsilon": epsilon_row.get("dielectric", ""),
                "has_reference_orbital": roster_row.get("has_orbitals", ""),
                "themol_uuid": harvest.get("themol_uuid", ""),
                "themol_h5_file": harvest.get("themol_h5_file", ""),
                "natoms": num_or_none(harvest.get("natoms")),
                "geometry_sha256": harvest.get("geometry_sha256", ""),
                "source_dataset": SOURCE_DATASET,
                "source_level": SOURCE_LEVEL,
                "source_license": SOURCE_LICENSE,
                "xtb_version": harvest.get("xtb_version", ""),
                "unit_check": UNIT_CHECK_CLAIM,
                "homo_gfn2_eV": homo,
                "lumo_gfn2_eV": lumo,
                "gap_gfn2_eV": gap,
                "batt_homo_eV": batt_homo,
                "batt_lumo_eV": batt_lumo,
                "batt_gap_eV": batt_gap,
                "pubchemqc_homo_eV": pubchemqc_homo,
                "pubchemqc_lumo_eV": pubchemqc_lumo,
                "gfn2_minus_batt_homo_eV": q6(None if batt_homo is None else homo - batt_homo),
                "gfn2_minus_batt_lumo_eV": q6(None if batt_lumo is None else lumo - batt_lumo),
                "gfn2_minus_batt_gap_eV": q6(None if batt_gap is None else gap - batt_gap),
                "gfn2_minus_pubchemqc_homo_eV": q6(None if pubchemqc_homo is None else homo - pubchemqc_homo),
                "gfn2_minus_pubchemqc_lumo_eV": q6(None if pubchemqc_lumo is None else lumo - pubchemqc_lumo),
                "calib_homo_eV": None,
                "calib_lumo_eV": None,
                "calibration_id": "",
                "role": "",
            }
        )

    homo_pairs = [
        {"inchikey": row["inchikey"], "x": row["homo_gfn2_eV"], "y": row["batt_homo_eV"]}
        for row in rows
        if row["batt_homo_eV"] is not None
    ]
    lumo_pairs = [
        {"inchikey": row["inchikey"], "x": row["lumo_gfn2_eV"], "y": row["batt_lumo_eV"]}
        for row in rows
        if row["batt_lumo_eV"] is not None
    ]
    gap_pairs = [
        {"inchikey": row["inchikey"], "x": row["gap_gfn2_eV"], "y": row["batt_gap_eV"]}
        for row in rows
        if row["batt_gap_eV"] is not None
    ]
    homo_cal = calibration(homo_pairs)
    lumo_cal = calibration(lumo_pairs)
    gap_cal = calibration(gap_pairs)
    apply_out_of_sample_gate(homo_cal, homo_pairs)
    apply_out_of_sample_gate(lumo_cal, lumo_pairs)
    apply_out_of_sample_gate(gap_cal, gap_pairs)

    for row in rows:
        homo = row["homo_gfn2_eV"]
        lumo = row["lumo_gfn2_eV"]
        if homo_cal["status"] == "usable_with_flag":
            row["calib_homo_eV"] = q6(homo_cal["slope"] * homo + homo_cal["intercept"])
        if lumo_cal["status"] == "usable_with_flag":
            row["calib_lumo_eV"] = q6(lumo_cal["slope"] * lumo + lumo_cal["intercept"])
        row["calibration_id"] = CALIBRATION_ID if row["calib_homo_eV"] is not None else ""
        if row["batt_homo_eV"] is not None:
            row["role"] = "paired_anchor"
        elif row["calib_homo_eV"] is not None:
            row["role"] = "calibrated_estimate"
        else:
            row["role"] = "uncalibrated_reference"

    rows.sort(key=lambda item: item["inchikey"])
    by_tier: dict[str, int] = {}
    for row in rows:
        by_tier[row["expansion_tier"]] = by_tier.get(row["expansion_tier"], 0) + 1
    roles: dict[str, int] = {}
    for row in rows:
        roles[row["role"]] = roles.get(row["role"], 0) + 1
    delivered = len(rows)
    roster_total = len(roster_rows)
    summary: dict[str, object] = {
        "arm": ARM,
        "source_dataset": SOURCE_DATASET,
        "source_level": SOURCE_LEVEL,
        "source_license": SOURCE_LICENSE,
        "calibration_id": CALIBRATION_ID,
        "roster": {
            "path": "probes/themol_registry_expansion_roster.csv",
            "rows": roster_total,
            "sha256": roster_summary.get("roster_sha256"),
            "rows_by_tier": roster_summary.get("rows_by_tier"),
        },
        "run_status": "complete" if delivered == roster_total else "partial",
        "delivered_rows": delivered,
        "roster_rows": roster_total,
        "completion_share": (delivered / roster_total) if roster_total else None,
        "harvest": {
            **shard_meta,
            "rows_read": len(harvest_rows),
            "rows_off_roster": len(off_roster),
            "failed_rows": failed_rows,
            "duplicate_keys": duplicate_keys,
            "duplicate_collisions": len(duplicate_keys),
            "duplicate_upgrades": duplicate_upgrades,
            "fetched_bytes_total": sum(
                int(num_or_none(row.get("fetched_bytes")) or 0) for row in harvest_rows
            ),
            "elapsed_seconds_total": round(
                sum(num_or_none(row.get("elapsed_seconds")) or 0.0 for row in harvest_rows), 3
            ),
            "xtb_versions": sorted({row.get("xtb_version", "") for row in harvest_rows if row.get("xtb_version")}),
        },
        "coverage": {
            "epsilon_roster_keys": len(epsilon),
            "epsilon_roster_in_layer": sum(1 for row in rows if row["in_epsilon_roster"] == "true"),
            "no_reference_orbital_input": sum(
                1 for row in rows if row["has_reference_orbital"] != "true"
            ),
            "molecules_gaining_first_orbital_number": sum(
                1
                for row in rows
                if row["has_reference_orbital"] != "true" and row["pubchemqc_homo_eV"] is None
            ),
        },
        "rows_by_tier": by_tier,
        "structure_check": {
            "inchikey_match": sum(1 for row in rows if row["structure_check"] == "inchikey_match"),
            "inchikey_mismatch": sum(1 for row in rows if row["structure_check"] == "inchikey_mismatch"),
            "smiles_unparsable": sum(1 for row in rows if row["structure_check"] == "smiles_unparsable"),
        },
        "unit_check": {
            "status": "ok",
            "claimed_value": UNIT_CHECK_CLAIM,
            "scope": (
                "pipeline-level and per-row identical: the claim is that the harvest writes eV "
                "from an xTB single point, not that every row was independently re-derived "
                "(audit W17-17/F6)"
            ),
            "foreign_arm_evidence": (
                "data/raw/themol/unit_audit.json (W17-14, 8/8 molecules, residual <= 4.49e-05 eV) "
                "-- covers the W17-14 harvest, not this layer"
            ),
            "this_layer_evidence": unit_recheck_evidence(),
        },
        "calibration": {"homo": homo_cal, "lumo": lumo_cal, "gap": gap_cal},
        "level_offsets_gfn2_minus_batt": {
            "homo": summarize_offsets([row["gfn2_minus_batt_homo_eV"] for row in rows if row["gfn2_minus_batt_homo_eV"] is not None]),
            "lumo": summarize_offsets([row["gfn2_minus_batt_lumo_eV"] for row in rows if row["gfn2_minus_batt_lumo_eV"] is not None]),
            "gap": summarize_offsets([row["gfn2_minus_batt_gap_eV"] for row in rows if row["gfn2_minus_batt_gap_eV"] is not None]),
        },
        "level_offsets_gfn2_minus_pubchemqc": {
            "homo": summarize_offsets([row["gfn2_minus_pubchemqc_homo_eV"] for row in rows if row["gfn2_minus_pubchemqc_homo_eV"] is not None]),
            "lumo": summarize_offsets([row["gfn2_minus_pubchemqc_lumo_eV"] for row in rows if row["gfn2_minus_pubchemqc_lumo_eV"] is not None]),
        },
        "pair_counts": {
            "homo": len(homo_pairs),
            "lumo": len(lumo_pairs),
            "gap": len(gap_pairs),
            "gates": {"mae_limit_eV": MAE_LIMIT_EV, "r_limit": R_LIMIT, "min_pairs": MIN_PAIRED_N},
        },
        "roles": roles,
        "models_fitted": 0,
        "models_fitted_note": (
            "no predictive model of any target property is trained in this arm; the only "
            "quantities fitted are the cross-level linear maps in `calibration`, which put a "
            "GFN2-xTB level onto the repository level and are reported with their out-of-sample "
            "error rather than as model performance (audit W17-17/F7)"
        ),
    }
    return rows, summary


def render(rows: list[dict[str, object]]) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_outputs(rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    LAYER.write_text(render(rows), encoding="utf-8", newline="")
    SUMMARY.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="recompose and compare bytes, do not write")
    args = parser.parse_args(argv)
    rows, summary = compose()
    if args.check:
        ok = LAYER.exists() and render(rows) == LAYER.read_text(encoding="utf-8")
        recorded = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
        same_summary = recorded == summary
        print(json.dumps({"layer_matches": ok, "summary_matches": same_summary, "rows": len(rows), "run_status": summary["run_status"]}, sort_keys=True))
        return 0 if ok and same_summary else 1
    write_outputs(rows, summary)
    print(json.dumps({"rows": len(rows), "run_status": summary["run_status"], "delivered_rows": summary["delivered_rows"], "roster_rows": summary["roster_rows"], "rows_by_tier": summary["rows_by_tier"], "calibration_status": {k: v.get("status") for k, v in summary["calibration"].items()}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
