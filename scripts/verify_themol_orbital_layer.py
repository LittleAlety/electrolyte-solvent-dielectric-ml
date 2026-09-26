"""Independent verifier for the W17-14 THEMol/GFN2-xTB orbital layer.

Deliberately does not import the builder.  Every number is recomputed here from
the committed artifacts alone -- the layer CSV, the summary JSON, the four-core
registry, the epsilon roster and the W17-12 second-source layer -- so a silent
edit to any of them shows up as a failure.

``--check`` is the mode CI runs and needs no raw data: the 111 anchor molecules
are re-derived as the ``paired_anchor`` rows of the W17-12 layer, which is what
``probes/build_themol_target_roster.py`` used to build the anchor roster in the
first place.

``--check-raw`` is the stronger local mode.  It needs data/raw/themol/ (a
git-ignored directory), re-composes the layer from the harvest shards, and
compares byte for byte.
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

LAYER = ROOT / "data/processed/themol_orbital_layer.csv"
SUMMARY = ROOT / "probes/themol_orbital_layer_summary.json"
PREREG = ROOT / "probes/themol_orbital_layer_prereg.json"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = ROOT / "data/dielectric_v04.csv"
SECOND_SOURCE_LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
UNIT_AUDIT = ROOT / "data/raw/themol/unit_audit.json"
ANCHOR_ROSTER = ROOT / "data/raw/themol/themol_anchor_roster.csv"

EXPECTED_COLUMNS = [
    "inchikey", "name", "smiles", "canonical_smiles", "structure_check",
    "in_epsilon_roster", "epsilon", "in_anchor_roster", "themol_uuid",
    "themol_h5_file", "natoms", "geometry_sha256", "source_dataset",
    "source_level", "source_license", "xtb_version", "unit_check",
    "homo_gfn2_eV", "lumo_gfn2_eV", "gap_gfn2_eV", "batt_homo_eV",
    "batt_lumo_eV", "batt_gap_eV", "pubchemqc_homo_eV", "pubchemqc_lumo_eV",
    "gfn2_minus_batt_homo_eV", "gfn2_minus_batt_lumo_eV", "gfn2_minus_batt_gap_eV",
    "gfn2_minus_pubchemqc_homo_eV", "gfn2_minus_pubchemqc_lumo_eV",
    "calib_homo_eV", "calib_lumo_eV", "calibration_id", "role",
]
ALLOWED_ROLES = {"paired_anchor", "calibrated_estimate", "uncalibrated_reference"}
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80
MIN_PAIRED_N = 40
EXPECTED_ROWS = 166
EXPECTED_EPSILON_HITS = 142
EXPECTED_ANCHOR_HITS = 72
TOLERANCE = 1e-9


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def num(value):
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def pearson(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def fit_line(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def fold_map(keys, folds=2):
    ordered = sorted(keys)
    return {key: index % folds for index, key in enumerate(ordered)}


def calibration(pairs, failures):
    if len(pairs) < MIN_PAIRED_N:
        failures.append(f"only {len(pairs)} paired rows, need {MIN_PAIRED_N}")
        return None
    folds = fold_map([pair[0] for pair in pairs])
    out_of_sample = []
    for held in (0, 1):
        train = [pair for pair in pairs if folds[pair[0]] != held]
        test = [pair for pair in pairs if folds[pair[0]] == held]
        fit = fit_line([p[1] for p in train], [p[2] for p in train])
        if fit is None:
            continue
        for point in test:
            out_of_sample.append(abs(fit[0] * point[1] + fit[1] - point[2]))
    full = fit_line([p[1] for p in pairs], [p[2] for p in pairs])
    r = pearson([p[1] for p in pairs], [p[2] for p in pairs])
    mae = sum(out_of_sample) / len(out_of_sample)
    status = "usable_with_flag" if (mae <= MAE_LIMIT_EV and r is not None and r >= R_LIMIT) else "reference_only"
    return {
        "n": len(pairs), "slope": full[0], "intercept": full[1],
        "pearson_r_in_sample": r, "mae_out_of_sample_eV": mae,
        "max_abs_error_out_of_sample_eV": max(out_of_sample), "status": status,
    }


def close(a, b):
    if a is None or b is None:
        return a == b
    return abs(a - b) <= TOLERANCE


def inchikey_skeleton(smiles):
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles or "")
    if molecule is None:
        return None
    return Chem.MolToInchiKey(molecule).split("-")[0]


def check():
    failures = []
    rows = read_rows(LAYER)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))

    if sha256_file(LAYER) != summary.get("layer_sha256"):
        failures.append("layer sha256 does not match the summary")
    if list(rows[0].keys()) != EXPECTED_COLUMNS:
        failures.append("layer columns differ from the verifier's EXPECTED_COLUMNS")
    if len(rows) != EXPECTED_ROWS or summary.get("layer_rows") != EXPECTED_ROWS:
        failures.append(f"expected {EXPECTED_ROWS} rows, layer={len(rows)} summary={summary.get('layer_rows')}")
    if summary.get("layer_columns") != len(EXPECTED_COLUMNS):
        failures.append("summary layer_columns disagrees with the verifier")
    keys = [row["inchikey"] for row in rows]
    if len(set(keys)) != len(keys):
        failures.append("duplicate inchikey in the layer")

    if prereg["thresholds"]["mae_limit_eV"] != MAE_LIMIT_EV:
        failures.append("prereg MAE gate disagrees with the verifier")
    if prereg["thresholds"]["r_limit"] != R_LIMIT:
        failures.append("prereg r gate disagrees with the verifier")
    if prereg["thresholds"]["min_paired_n"] != MIN_PAIRED_N:
        failures.append("prereg min_paired_n disagrees with the verifier")

    # Independent joins.
    registry = {row["inchikey"]: row for row in read_rows(REGISTRY)}
    epsilon = {row["inchikey"] for row in read_rows(EPSILON_ROSTER)}
    second = read_rows(SECOND_SOURCE_LAYER)
    anchors = {row["inchikey"] for row in second if row.get("role") == "paired_anchor"}
    pubchem = {row["inchikey"]: row for row in second}
    if len(anchors) != 111:
        failures.append(f"expected 111 paired_anchor rows in the W17-12 layer, got {len(anchors)}")

    structure_counts = {"inchikey_match": 0, "inchikey_mismatch": 0, "smiles_unparsable": 0}
    unit_counts = {}
    role_counts = {}
    epsilon_hits = anchor_hits = 0
    calib_homo_nonempty = calib_lumo_nonempty = 0
    offset_values = {
        "gfn2_minus_batt_homo_eV": [],
        "gfn2_minus_batt_lumo_eV": [],
        "gfn2_minus_batt_gap_eV": [],
        "gfn2_minus_pubchemqc_homo_eV": [],
        "gfn2_minus_pubchemqc_lumo_eV": [],
    }
    pairs = {"homo": [], "lumo": [], "gap": []}
    for row in rows:
        key = row["inchikey"]
        skeleton = inchikey_skeleton(row["smiles"])
        expected_structure = (
            "smiles_unparsable" if skeleton is None
            else ("inchikey_match" if skeleton == key.split("-")[0] else "inchikey_mismatch")
        )
        structure_counts[row["structure_check"]] = structure_counts.get(row["structure_check"], 0) + 1
        if row["structure_check"] != expected_structure:
            failures.append(f"{key}: structure_check {row['structure_check']} != recomputed {expected_structure}")
        unit_counts[row["unit_check"]] = unit_counts.get(row["unit_check"], 0) + 1
        role_counts[row["role"]] = role_counts.get(row["role"], 0) + 1
        if row["role"] not in ALLOWED_ROLES:
            failures.append(f"{key}: unknown role {row['role']}")

        in_eps = key in epsilon
        if row["in_epsilon_roster"] != str(in_eps).lower():
            failures.append(f"{key}: in_epsilon_roster disagrees with the epsilon roster")
        epsilon_hits += 1 if in_eps else 0
        in_anchor = key in anchors
        if row["in_anchor_roster"] != str(in_anchor).lower():
            failures.append(f"{key}: in_anchor_roster disagrees with the W17-12 paired anchors")
        anchor_hits += 1 if in_anchor else 0

        registry_row = registry.get(key, {})
        batt_homo = num(registry_row.get("HOMO_eV"))
        batt_lumo = num(registry_row.get("LUMO_eV"))
        if not close(num(row["batt_homo_eV"]), batt_homo):
            failures.append(f"{key}: batt_homo_eV disagrees with the four-core registry")
        if not close(num(row["batt_lumo_eV"]), batt_lumo):
            failures.append(f"{key}: batt_lumo_eV disagrees with the four-core registry")
        if batt_homo is not None and batt_lumo is not None and not close(
            num(row["batt_gap_eV"]), batt_lumo - batt_homo
        ):
            failures.append(f"{key}: batt_gap_eV is not LUMO - HOMO")

        second_row = pubchem.get(key, {})
        for column, source in (
            ("pubchemqc_homo_eV", "homo_eV"),
            ("pubchemqc_lumo_eV", "lumo_eV"),
        ):
            if not close(num(row[column]), num(second_row.get(source))):
                failures.append(f"{key}: {column} disagrees with the W17-12 layer")

        homo = num(row["homo_gfn2_eV"])
        lumo = num(row["lumo_gfn2_eV"])
        if not close(num(row["gap_gfn2_eV"]), (lumo - homo) if homo is not None and lumo is not None else None):
            failures.append(f"{key}: gap_gfn2_eV is not LUMO - HOMO")

        expected_offsets = {
            "gfn2_minus_batt_homo_eV": (homo - batt_homo) if batt_homo is not None else None,
            "gfn2_minus_batt_lumo_eV": (lumo - batt_lumo) if batt_lumo is not None else None,
            "gfn2_minus_batt_gap_eV": (
                (lumo - homo) - (batt_lumo - batt_homo)
                if None not in (homo, lumo, batt_homo, batt_lumo)
                else None
            ),
            "gfn2_minus_pubchemqc_homo_eV": (
                (homo - num(second_row.get("homo_eV")))
                if num(second_row.get("homo_eV")) is not None
                else None
            ),
            "gfn2_minus_pubchemqc_lumo_eV": (
                (lumo - num(second_row.get("lumo_eV")))
                if num(second_row.get("lumo_eV")) is not None
                else None
            ),
        }
        for column, expected in expected_offsets.items():
            if not close(num(row[column]), expected):
                failures.append(f"{key}: {column} is not the difference of its two source columns")
            if num(row[column]) is not None:
                offset_values[column].append(num(row[column]))

        if num(row["calib_homo_eV"]) is not None:
            calib_homo_nonempty += 1
        if num(row["calib_lumo_eV"]) is not None:
            calib_lumo_nonempty += 1
        if batt_homo is not None and batt_lumo is not None:
            pairs["homo"].append((key, homo, batt_homo))
            pairs["lumo"].append((key, lumo, batt_lumo))
            pairs["gap"].append((key, lumo - homo, batt_lumo - batt_homo))
        expected_role = (
            "paired_anchor" if batt_homo is not None
            else ("calibrated_estimate" if num(row["calib_homo_eV"]) is not None else "uncalibrated_reference")
        )
        if row["role"] != expected_role:
            failures.append(f"{key}: role {row['role']} != recomputed {expected_role}")

    if epsilon_hits != EXPECTED_EPSILON_HITS:
        failures.append(f"epsilon roster hits: expected {EXPECTED_EPSILON_HITS}, got {epsilon_hits}")
    if anchor_hits != EXPECTED_ANCHOR_HITS:
        failures.append(f"anchor roster hits: expected {EXPECTED_ANCHOR_HITS}, got {anchor_hits}")
    if summary["coverage"]["epsilon_roster_in_layer"] != epsilon_hits:
        failures.append("summary epsilon coverage disagrees")
    if summary["coverage"]["anchor_roster_in_layer"] != anchor_hits:
        failures.append("summary anchor coverage disagrees")
    for name, counted in structure_counts.items():
        if summary["structure_check"].get(name, 0) != counted:
            failures.append(f"summary structure_check[{name}] disagrees")
    if unit_counts != {"pipeline_audited_eV": len(rows)}:
        failures.append(f"unit_check column is not uniformly pipeline_audited_eV: {unit_counts}")
    if sorted(role_counts.items()) != sorted(summary["roles"].items()):
        failures.append("summary roles disagree with the layer")
    if sum(role_counts.values()) != len(rows):
        failures.append("role counts do not sum to the row count")

    # Unit audit: the claim behind unit_check must actually be recorded and passing.
    audit = summary["unit_check"]
    if audit.get("status") != "ok" or audit.get("pass_rate") != 1.0:
        failures.append("summary unit_check is not a clean pass")
    if not audit.get("rows") or not all(row.get("passed") for row in audit["rows"]):
        failures.append("summary unit_check rows are not all passed")
    if audit.get("n") != len(audit.get("rows", [])):
        failures.append("summary unit_check n disagrees with its own rows")
    if UNIT_AUDIT.exists():
        on_disk = json.loads(UNIT_AUDIT.read_text(encoding="utf-8"))
        if on_disk.get("passed") != on_disk.get("n"):
            failures.append("data/raw/themol/unit_audit.json is not a clean pass")
        if len(on_disk.get("checks", [])) != audit.get("n"):
            failures.append("summary unit_check disagrees with data/raw/themol/unit_audit.json")

    # Recompute every calibration and every offset summary from the layer alone.
    for name, channel_rows in pairs.items():
        recomputed = calibration(channel_rows, failures)
        if recomputed is None:
            continue
        recorded = summary["calibration"][name]
        for field in ("n", "slope", "intercept", "pearson_r_in_sample",
                      "mae_out_of_sample_eV", "max_abs_error_out_of_sample_eV"):
            if not close(recomputed[field], recorded.get(field)):
                failures.append(
                    f"calibration[{name}].{field}: verifier {recomputed[field]} != summary {recorded.get(field)}"
                )
        if recomputed["status"] != recorded.get("status"):
            failures.append(f"calibration[{name}].status disagrees")
        if recomputed["status"] != "usable_with_flag" and name == "lumo" and calib_lumo_nonempty:
            failures.append("calib_lumo_eV is populated although the LUMO map is not usable")
        if recomputed["status"] != "usable_with_flag" and name == "homo" and calib_homo_nonempty:
            failures.append("calib_homo_eV is populated although the HOMO map is not usable")

    for name, values in offset_values.items():
        recorded = {
            "gfn2_minus_batt_homo_eV": summary["level_offsets_gfn2_minus_batt"]["homo"],
            "gfn2_minus_batt_lumo_eV": summary["level_offsets_gfn2_minus_batt"]["lumo"],
            "gfn2_minus_batt_gap_eV": summary["level_offsets_gfn2_minus_batt"]["gap"],
            "gfn2_minus_pubchemqc_homo_eV": summary["level_offsets_gfn2_minus_pubchemqc"]["homo"],
            "gfn2_minus_pubchemqc_lumo_eV": summary["level_offsets_gfn2_minus_pubchemqc"]["lumo"],
        }[name]
        if recorded["n"] != len(values):
            failures.append(f"offset summary {name}: n {recorded['n']} != {len(values)}")
            continue
        mean = sum(values) / len(values)
        sigma = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        if not close(round(mean, 12), round(recorded["mean_eV"], 12)):
            failures.append(f"offset summary {name}: mean disagrees")
        if not close(round(sigma, 12), round(recorded["sigma_eV"], 12)):
            failures.append(f"offset summary {name}: sigma disagrees")

    harvest = summary["harvest"]
    if harvest["rows_total"] != EXPECTED_ROWS:
        failures.append(f"summary harvest rows_total {harvest['rows_total']} != {EXPECTED_ROWS}")
    if sum(harvest["rows_by_shard"].values()) != harvest["rows_total"]:
        failures.append("summary rows_by_shard does not sum to rows_total")
    if harvest["skipped"]:
        failures.append(f"summary records skipped molecules: {harvest['skipped']}")

    return failures, {
        "layer_sha256": sha256_file(LAYER),
        "rows": len(rows),
        "columns": len(EXPECTED_COLUMNS),
        "epsilon_hits": epsilon_hits,
        "anchor_hits": anchor_hits,
        "roles": role_counts,
        "structure_check": structure_counts,
        "unit_check": unit_counts,
        "calibration_status": {
            name: summary["calibration"][name].get("status") for name in ("homo", "lumo", "gap")
        },
    }


def check_raw():
    sys.path.insert(0, str(ROOT))
    from probes.build_themol_orbital_layer import compose, render

    failures = []
    rows, _ = compose()
    expected = render(rows)
    if expected != LAYER.read_text(encoding="utf-8"):
        failures.append("layer on disk is not byte-identical to a fresh compose()")
    if not ANCHOR_ROSTER.exists():
        failures.append("data/raw/themol/themol_anchor_roster.csv is missing")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-raw", action="store_true")
    args = parser.parse_args(argv)

    failures, report = check()
    if args.check_raw:
        failures.extend(check_raw())
    if failures:
        print(f"FAIL ({len(failures)} checks)")
        for failure in failures:
            print("  -", failure)
        return 1
    print(f"PASS {json.dumps(report, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())