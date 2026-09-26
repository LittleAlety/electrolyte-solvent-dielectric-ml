"""Compose the W17-12 second-source orbital layer from the bounded PubChemQC
harvest.

Inputs (raw, git-ignored): data/raw/pubchemqc_w17/{manifest,records,records_head,unit_audit}.json[l]
Inputs (committed): the four-core registry, the epsilon and viscosity rosters.
Outputs (committed): data/processed/orbital_second_source_layer.csv and
probes/orbital_second_source_summary.json.

The layer is *additive*: the Batt-P30K values inside
data/processed/four_core_key_registry.csv are never rewritten (judgement F of
probes/orbital_second_source_prereg.json).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from probes.harvest_pubchemqc_orbital import load_targets as load_harvest_targets

RAW_DIR = ROOT / "data/raw/pubchemqc_w17"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = ROOT / "data/dielectric_v04.csv"
VISCOSITY_ROSTER = ROOT / "data/viscosity_v02.csv"
PREREG = ROOT / "probes/orbital_second_source_prereg.json"
LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
SUMMARY = ROOT / "probes/orbital_second_source_summary.json"

SOURCE_DATASET = "molssiai-hub/pubchemqc-b3lyp"
SOURCE_LEVEL = "B3LYP/6-31G*//PM6 (gas phase)"
SOURCE_LICENSE = "CC BY 4.0"
SOURCE_DOI = "10.1021/acs.jcim.3c00899"
CALIBRATION_ID = "linear_2fold_v1"
MIN_PAIRED_N = 60
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80

COLUMNS = [
    "inchikey",
    "pubchem_cid",
    "pubchem_version",
    "record_name",
    "formula",
    "molecular_mass",
    "charge",
    "multiplicity",
    "source_dataset",
    "source_level",
    "source_license",
    "source_doi",
    "homo_eV",
    "lumo_eV",
    "gap_eV",
    "homo_beta_eV",
    "lumo_beta_eV",
    "dipole_debye",
    "unit_check",
    "structure_check",
    "tags",
    "in_key_registry",
    "in_batt_orbit_pool",
    "in_epsilon_roster",
    "in_viscosity_roster",
    "in_viscosity_sample",
    "in_calibration_sample",
    "batt_homo_eV",
    "batt_lumo_eV",
    "batt_minus_pubchemqc_homo_eV",
    "batt_minus_pubchemqc_lumo_eV",
    "calib_homo_eV",
    "calib_lumo_eV",
    "calibration_id",
    "role",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def inchikey_from_inchi(inchi):
    if not inchi:
        return None
    try:
        from rdkit import Chem

        mol = Chem.MolFromInchi(inchi)
        if mol is None:
            return None
        return Chem.MolToInchiKey(mol)
    except Exception:  # noqa: BLE001 - an unparsable InChI is data, not a crash
        return None


def fmt(value, digits=6):
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return ("%." + str(digits) + "f") % number


def q6(value):
    """Quantise to the six decimals the layer CSV stores, so the summary is
    exactly reproducible from the committed CSV alone."""
    number = num_or_none(value)
    return None if number is None else round(number, 6)


def num_or_none(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def pearson(xs, ys):
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
    return sxy / math.sqrt(sxx * syy)


def fit_line(xs, ys):
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


def fold_map(keys, folds=2):
    """Deterministic 2-fold assignment by sorted-key rank."""
    ordered = sorted(keys)
    return {key: index % folds for index, key in enumerate(ordered)}


def calibration(pairs):
    """2-fold out-of-sample linear map y = slope * x + intercept."""
    result = {"n": len(pairs)}
    if len(pairs) < MIN_PAIRED_N:
        result["status"] = "insufficient_pairs"
        result["min_required"] = MIN_PAIRED_N
        return result
    folds = fold_map([p["inchikey"] for p in pairs])
    out_of_sample = []
    fold_fits = []
    for held in (0, 1):
        train = [p for p in pairs if folds[p["inchikey"]] != held]
        test = [p for p in pairs if folds[p["inchikey"]] == held]
        if len(train) < 2 or not test:
            continue
        xs = [p["pubchemqc"] for p in train]
        ys = [p["batt"] for p in train]
        fit = fit_line(xs, ys)
        if fit is None:
            continue
        slope, intercept = fit
        fold_fits.append({"held_out_fold": held, "n_train": len(train), "n_test": len(test),
                          "slope": slope, "intercept": intercept})
        for point in test:
            out_of_sample.append(
                {"inchikey": point["inchikey"], "y": point["batt"],
                 "yhat": slope * point["pubchemqc"] + intercept}
            )
    if not out_of_sample:
        result["status"] = "no_fold"
        return result
    errors = [abs(p["yhat"] - p["y"]) for p in out_of_sample]
    mae = sum(errors) / len(errors)
    full = fit_line([p["pubchemqc"] for p in pairs], [p["batt"] for p in pairs])
    r = pearson([p["pubchemqc"] for p in pairs], [p["batt"] for p in pairs])
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
    ok = (
        full is not None
        and mae <= MAE_LIMIT_EV
        and r is not None
        and r >= R_LIMIT
    )
    result["status"] = "usable_with_flag" if ok else "reference_only"
    result["mae_limit_eV"] = MAE_LIMIT_EV
    result["r_limit"] = R_LIMIT
    return result


def audited_cids(raw_dir):
    """CIDs whose unit was checked directly against the raw orbital arrays."""
    path = raw_dir / "unit_audit.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row.get("cid") for row in payload.get("checks", []) if row.get("cid") is not None}


def unit_audit_summary(raw_dir):
    path = raw_dir / "unit_audit.json"
    if not path.exists():
        return {"status": "missing", "pass_rate": None, "n": 0, "rows": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("checks", [])
    n = len(rows)
    passed = sum(1 for row in rows if row.get("passed"))
    return {
        "status": "ok" if n else "empty",
        "n": n,
        "passed": passed,
        "pass_rate": (passed / n) if n else None,
        "strata": payload.get("strata"),
        "cid_span_checked": payload.get("cid_span_checked"),
        "energy_field_equals_orbital_array": payload.get("energy_field_equals_orbital_array"),
        "gap_identity_holds": payload.get("gap_identity_holds"),
        "valence_window_discriminates_units": payload.get("valence_window_discriminates_units"),
        "card_declares_unit_for_scalar_fields": payload.get("card_declares_unit_for_scalar_fields"),
        "declared_unit_in_card": "hartree",
        "observed_unit": "eV",
        "note": "card annotation for orbital-energies is a documentation defect",
        "noble_gas_anchor": (
            "the viscosity roster legitimately contains helium; that record "
            "(HOMO -17.681958 eV, LUMO +30.471309 eV, gap 48.153267 eV) is an "
            "independent physical anchor for the eV reading"
        ),
        "rows": rows,
    }


def compose():
    manifest_path = RAW_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"raw harvest missing at {RAW_DIR}; run probes/harvest_pubchemqc_orbital.py first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = read_jsonl(RAW_DIR / "records.jsonl")
    head_records = read_jsonl(RAW_DIR / "records_head.jsonl")

    registry_rows = {row["inchikey"]: row for row in read_csv_rows(REGISTRY)}
    epsilon_keys = {row["inchikey"] for row in read_csv_rows(EPSILON_ROSTER) if row.get("inchikey")}
    viscosity_keys = {
        row["inchikey"] for row in read_csv_rows(VISCOSITY_ROSTER) if row.get("inchikey")
    }

    harvest_targets, _n_vis_pool, _n_reg_pool = load_harvest_targets()
    sample_keys = {
        "epsilon_roster": {k for k, v in harvest_targets.items() if "epsilon_roster" in v["tags"]},
        "viscosity_roster_sample": {
            k for k, v in harvest_targets.items() if "viscosity_roster_sample" in v["tags"]
        },
        "batt_calibration_sample": {
            k for k, v in harvest_targets.items() if "batt_calibration_sample" in v["tags"]
        },
    }
    sample_digests = {
        name: hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()
        for name, keys in sample_keys.items()
    }
    audit_cids = audited_cids(RAW_DIR)
    targeted_keys = {record.get("target_key") for record in records}
    candidates = list(head_records) + list(records)
    by_key = {}
    mismatch = []
    unresolvable = 0
    for record in candidates:
        key = inchikey_from_inchi(record.get("pubchem-inchi"))
        target = record.get("target_key")
        if key is None:
            unresolvable += 1
            continue
        if target and not target.startswith("name:") and key != target:
            mismatch.append({"target": target, "observed": key, "cid": record.get("cid")})
            continue
        tags = set()
        if target and target.startswith("name:"):
            tags.add("named_solvent")
        if target and target in targeted_keys:
            tags.add("targeted_harvest")
        if target and not target.startswith("name:"):
            structure_check = "inchikey_match_target"
        else:
            structure_check = "inchikey_from_pubchem_cid"
        entry = {
            "inchikey": key,
            "record": record,
            "tags": tags,
            "structure_check": structure_check,
        }
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = entry
        else:
            existing["tags"] |= tags
            if structure_check == "inchikey_match_target":
                existing["structure_check"] = structure_check
            if (record.get("cid") or 0) < (existing["record"].get("cid") or 0):
                existing["record"] = record

    pairs_homo = []
    pairs_lumo = []
    rows = []
    for key in sorted(by_key):
        record = by_key[key]["record"]
        tags = set(by_key[key]["tags"])
        if key in epsilon_keys:
            tags.add("epsilon_roster")
        if key in viscosity_keys:
            tags.add("viscosity_roster")
        reg = registry_rows.get(key)
        in_registry = reg is not None
        in_batt_pool = bool(reg and reg.get("has_orbitals") == "true" and reg.get("HOMO_eV"))
        in_viscosity_sample = key in sample_keys["viscosity_roster_sample"]
        in_calibration_sample = key in sample_keys["batt_calibration_sample"]
        if in_viscosity_sample:
            tags.add("viscosity_roster_sample")
        if in_calibration_sample:
            tags.add("batt_calibration_sample")
        if in_registry:
            tags.add("key_registry")
        if in_batt_pool:
            tags.add("batt_orbit_pool")
        batt_homo = q6(reg["HOMO_eV"]) if in_batt_pool else None
        batt_lumo = q6(reg["LUMO_eV"]) if in_batt_pool and reg.get("LUMO_eV") else None
        homo = q6(record.get("energy-alpha-homo"))
        lumo = q6(record.get("energy-alpha-lumo"))
        if batt_homo is not None and homo is not None:
            pairs_homo.append({"inchikey": key, "pubchemqc": homo, "batt": batt_homo})
        if batt_lumo is not None and lumo is not None:
            pairs_lumo.append({"inchikey": key, "pubchemqc": lumo, "batt": batt_lumo})
        rows.append(
            {
                "inchikey": key,
                "pubchem_cid": record.get("cid"),
                "pubchem_version": record.get("pubchem-version", ""),
                "record_name": record.get("name", ""),
                "formula": record.get("formula", ""),
                "molecular_mass": record.get("molecular-mass"),
                "charge": record.get("pubchem-charge", record.get("charge", "")),
                "multiplicity": record.get("multiplicity", ""),
                "source_dataset": SOURCE_DATASET,
                "source_level": SOURCE_LEVEL,
                "source_license": SOURCE_LICENSE,
                "source_doi": SOURCE_DOI,
                "homo_eV": homo,
                "lumo_eV": lumo,
                "gap_eV": record.get("energy-alpha-gap"),
                "homo_beta_eV": record.get("energy-beta-homo"),
                "lumo_beta_eV": record.get("energy-beta-lumo"),
                "dipole_debye": record.get("dipole-moment"),
                "unit_check": "verified_eV_audited"
                if record.get("cid") in audit_cids
                else "dataset_level_eV",
                "structure_check": by_key[key]["structure_check"],
                "tags": ";".join(sorted(tags)),
                "in_key_registry": in_registry,
                "in_batt_orbit_pool": in_batt_pool,
                "in_epsilon_roster": key in epsilon_keys,
                "in_viscosity_roster": key in viscosity_keys,
                "in_viscosity_sample": in_viscosity_sample,
                "in_calibration_sample": in_calibration_sample,
                "batt_homo_eV": batt_homo,
                "batt_lumo_eV": batt_lumo,
                "batt_minus_pubchemqc_homo_eV": (batt_homo - homo)
                if (batt_homo is not None and homo is not None)
                else None,
                "batt_minus_pubchemqc_lumo_eV": (batt_lumo - lumo)
                if (batt_lumo is not None and lumo is not None)
                else None,
                "calib_homo_eV": None,
                "calib_lumo_eV": None,
                "calibration_id": "",
                "role": "",
            }
        )

    calib_homo = calibration(pairs_homo)
    calib_lumo = calibration(pairs_lumo)
    calibrations = {"homo": calib_homo, "lumo": calib_lumo}
    usable = {
        "homo": calib_homo.get("status") == "usable_with_flag",
        "lumo": calib_lumo.get("status") == "usable_with_flag",
    }

    for row in rows:
        if row["batt_homo_eV"] is not None or row["batt_lumo_eV"] is not None:
            row["role"] = "paired_anchor"
        estimated = False
        if usable["homo"] and row["homo_eV"] is not None and row["batt_homo_eV"] is None:
            row["calib_homo_eV"] = (
                calib_homo["slope"] * row["homo_eV"] + calib_homo["intercept"]
            )
            estimated = True
        if usable["lumo"] and row["lumo_eV"] is not None and row["batt_lumo_eV"] is None:
            row["calib_lumo_eV"] = (
                calib_lumo["slope"] * row["lumo_eV"] + calib_lumo["intercept"]
            )
            estimated = True
        if row["role"] == "":
            row["role"] = "calibrated_estimate" if estimated else "uncalibrated_reference"
        if estimated:
            row["calibration_id"] = CALIBRATION_ID

    coverage = {
        "harvested_unique_keys": len(rows),
        "harvested_targeted_records": len(records),
        "harvested_head_records": len(head_records),
        "structure_mismatches": len(mismatch),
        "unresolvable_inchi": unresolvable,
        "epsilon_roster_keys": len(epsilon_keys),
        "epsilon_roster_hits": sum(1 for row in rows if row["in_epsilon_roster"]),
        "viscosity_roster_keys": len(viscosity_keys),
        "viscosity_roster_hits": sum(1 for row in rows if row["in_viscosity_roster"]),
        "key_registry_hits": sum(1 for row in rows if row["in_key_registry"]),
        "batt_orbit_pool_hits": sum(1 for row in rows if row["in_batt_orbit_pool"]),
        "paired_anchor_rows": sum(1 for row in rows if row["role"] == "paired_anchor"),
        "calibrated_estimate_rows": sum(1 for row in rows if row["role"] == "calibrated_estimate"),
        "uncalibrated_reference_rows": sum(
            1 for row in rows if row["role"] == "uncalibrated_reference"
        ),
    }
    by_key_rows = {row["inchikey"]: row for row in rows}
    for name, field in (
        ("epsilon_roster", "epsilon_roster"),
        ("viscosity_roster_sample", "viscosity_roster_sample"),
        ("batt_calibration_sample", "registry_orbit_sample"),
    ):
        keys = sample_keys[name]
        hits = sum(1 for key in keys if key in by_key_rows)
        coverage[field + "_size"] = len(keys)
        coverage[field + "_hits"] = hits
        coverage[field + "_hit_rate"] = (hits / len(keys)) if keys else None
        coverage[field + "_digest"] = sample_digests[name]
    coverage["unit_checked_rows"] = sum(
        1 for row in rows if row["unit_check"] == "verified_eV_audited"
    )
    coverage["dataset_level_unit_rows"] = sum(
        1 for row in rows if row["unit_check"] == "dataset_level_eV"
    )

    paired_rows = [row for row in rows if row["role"] == "paired_anchor"]
    paired_cids = sorted(row["pubchem_cid"] for row in paired_rows if row["pubchem_cid"] is not None)
    paired_composition = {
        "n": len(paired_rows),
        "from_pre_registered_sample": sum(
            1 for row in paired_rows if row["in_calibration_sample"]
        ),
        "from_targeted_harvest": sum(
            1 for row in paired_rows if "targeted_harvest" in row["tags"].split(";")
        ),
        "from_head_scan": sum(
            1 for row in paired_rows if "targeted_harvest" not in row["tags"].split(";")
        ),
        "max_pubchem_cid": paired_cids[-1] if paired_cids else None,
        "median_pubchem_cid": paired_cids[len(paired_cids) // 2] if paired_cids else None,
        "caveat": (
            "the paired set is NOT a random sample of the Batt orbit pool. Only %d of the %d pairs come "  # noqa: UP031
            "from the pre-registered 200-key random draw (the rest of that draw does not resolve to a "
            "PubChem CID at all, because those Batt molecules are largely bespoke); %d pairs are targeted "
            "electrolyte-roster molecules that happen to sit in the Batt pool, and %d come from the "
            "low-CID head scan. The map is therefore representative of electrolyte-like molecules, which "
            "is the intended use, but it must not be quoted as a general Batt-vs-PubChemQC level map"
        )
        % (
            sum(1 for row in paired_rows if row["in_calibration_sample"]),
            len(paired_rows),
            sum(1 for row in paired_rows if "targeted_harvest" in row["tags"].split(";")),
            sum(1 for row in paired_rows if "targeted_harvest" not in row["tags"].split(";")),
        ),
    }

    offsets = {
        "homo": summarize_offsets([p["batt"] - p["pubchemqc"] for p in pairs_homo]),
        "lumo": summarize_offsets([p["batt"] - p["pubchemqc"] for p in pairs_lumo]),
    }

    summary = {
        "arm": "W17-12",
        "title": "Second-source orbital layer (PubChemQC B3LYP/6-31G*//PM6, CC BY 4.0)",
        "prereg": "probes/orbital_second_source_prereg.json",
        "prereg_sha256": sha256_file(PREREG),
        "source_dataset": SOURCE_DATASET,
        "source_dataset_revision": manifest.get("dataset_revision"),
        "source_level": SOURCE_LEVEL,
        "source_license": SOURCE_LICENSE,
        "source_doi": SOURCE_DOI,
        "shard": manifest.get("shard"),
        "shard_cid_window": manifest.get("shard_cid_window"),
        "harvest_manifest_sha256": sha256_file(manifest_path),
        "input_digests": {
            "data/processed/four_core_key_registry.csv": sha256_file(REGISTRY),
            "data/dielectric_v04.csv": sha256_file(EPSILON_ROSTER),
            "data/viscosity_v02.csv": sha256_file(VISCOSITY_ROSTER),
            "data/raw/pubchemqc_w17/records.jsonl": sha256_file(RAW_DIR / "records.jsonl"),
            "data/raw/pubchemqc_w17/records_head.jsonl": sha256_file(RAW_DIR / "records_head.jsonl"),
            "data/raw/pubchemqc_w17/unit_audit.json": sha256_file(RAW_DIR / "unit_audit.json")
            if (RAW_DIR / "unit_audit.json").exists()
            else None,
        },
        "harvest_located_record_count": manifest.get("located_record_count"),
        "harvest_http_requests": manifest.get("http_requests"),
        "harvest_http_bytes_read": manifest.get("http_bytes_read"),
        "harvest_target_keys_resolved": manifest.get("target_keys_resolved"),
        "harvest_target_key_count": manifest.get("target_key_count"),
        "structure_probe": manifest.get("structure_probe"),
        "unit_audit": unit_audit_summary(RAW_DIR),
        "coverage": coverage,
        "paired_anchor_composition": paired_composition,
        "level_offsets_batt_minus_pubchemqc": offsets,
        "calibration": calibrations,
        "judgements": {
            "C_second_source_coverage": {
                "epsilon_pass": coverage["epsilon_roster_hits"] >= 40,
                "viscosity_pass": coverage["viscosity_roster_hits"] >= 100,
            },
            "F_primary_untouched": True,
            "G_reaxys_excluded": True,
            "H_structure_identity": {"mismatches": len(mismatch)},
        },
        "role_rules": {
            "paired_anchor": "both PubChemQC and Batt-P30K values exist; the pair drives the calibration",
            "calibrated_estimate": "PubChemQC-only value mapped onto the Batt level with calibration_id",
            "uncalibrated_reference": "PubChemQC-only value, no calibration applied (reference only)",
            "never": "no second-source number is written into four_core_key_registry.csv",
        },
        "structure_mismatch_examples": mismatch[:20],
        "notes": [
            "absolute orbital energies are level dependent; only the calibrated columns may be used next to Batt values",
            (
                "unit_check is graded: verified_eV_audited means the row's own CID was checked against the raw "
                "orbital arrays, dataset_level_eV means the unit was established by the stratified audit and the "
                "physical anchors for the dataset as a whole and was not re-checked for that row"
            ),
            (
                "pearson_r_in_sample is the in-sample coefficient; the honest generalisation number is mae_out_of_sample_eV "
                "(see also max_abs_error_out_of_sample_eV, which the MAE hides)"
            ),
            (
                "the paired anchors are dominated by low-CID head-scan molecules: see paired_anchor_composition.caveat "
                "before quoting the slope or the intercept as a general level map"
            ),
            f"shard 0 covers PubChem CIDs up to {(manifest.get('shard_cid_window') or ['1', '?'])[1]}",
        ],
    }
    return rows, summary


def summarize_offsets(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "mean_eV": sum(ordered) / n,
        "median_eV": ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2]),
        "min_eV": ordered[0],
        "max_eV": ordered[-1],
        "stdev_eV": math.sqrt(sum((v - sum(ordered) / n) ** 2 for v in ordered) / n) if n > 1 else 0.0,
    }


ROW_DIGITS = {
    "molecular_mass": 6,
    "homo_eV": 6,
    "lumo_eV": 6,
    "gap_eV": 6,
    "homo_beta_eV": 6,
    "lumo_beta_eV": 6,
    "dipole_debye": 6,
    "batt_homo_eV": 6,
    "batt_lumo_eV": 6,
    "batt_minus_pubchemqc_homo_eV": 6,
    "batt_minus_pubchemqc_lumo_eV": 6,
    "calib_homo_eV": 6,
    "calib_lumo_eV": 6,
}
BOOL_COLUMNS = ("in_key_registry", "in_batt_orbit_pool", "in_epsilon_roster",
                "in_viscosity_roster", "in_viscosity_sample", "in_calibration_sample")


def render(rows):
    lines = [",".join(COLUMNS)]
    for row in rows:
        cells = []
        for column in COLUMNS:
            value = row.get(column)
            if column in BOOL_COLUMNS:
                cells.append("true" if value else "false")
            elif column in ROW_DIGITS:
                cells.append(fmt(value, ROW_DIGITS[column]))
            elif value is None:
                cells.append("")
            else:
                text = str(value)
                if "," in text or '"' in text:
                    text = '"' + text.replace('"', '""') + '"'
                cells.append(text)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def write_outputs(rows, summary):
    LAYER.parent.mkdir(parents=True, exist_ok=True)
    text = render(rows)
    LAYER.write_text(text, encoding="utf-8", newline="\n")
    summary = dict(summary)
    summary["layer_path"] = str(LAYER.relative_to(ROOT)).replace("\\", "/")
    summary["layer_rows"] = len(rows)
    summary["layer_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    SUMMARY.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="re-derive and compare byte for byte")
    args = parser.parse_args(argv)
    rows, summary = compose()
    text = render(rows)
    if args.check:
        existing = LAYER.read_text(encoding="utf-8") if LAYER.exists() else ""
        if existing != text:
            print("CHECK FAILED: layer differs from re-derivation")
            return 1
        recorded = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
        if recorded.get("layer_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            print("CHECK FAILED: summary digest mismatch")
            return 1
        print(f"CHECK OK: {len(rows)} rows, digest {summary and recorded.get('layer_sha256')}")
        return 0
    written = write_outputs(rows, summary)
    print(json.dumps({"rows": written["layer_rows"], "sha256": written["layer_sha256"],
                      "coverage": written["coverage"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())