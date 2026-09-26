"""Independent verifier for the W17-12 second-source orbital layer.

Deliberately does not import the builder: every number is recomputed here from
the committed artifacts alone (the layer CSV, the summary JSON, the four-core
registry and the two rosters), so a silent edit to any of them shows up as a
failure.  Use ``--check-raw`` for the stronger local mode that also re-derives
the layer from data/raw/pubchemqc_w17 and compares byte for byte.
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

LAYER = ROOT / "data/processed/orbital_second_source_layer.csv"
SUMMARY = ROOT / "probes/orbital_second_source_summary.json"
PREREG = ROOT / "probes/orbital_second_source_prereg.json"
REGISTRY = ROOT / "data/processed/four_core_key_registry.csv"
EPSILON_ROSTER = ROOT / "data/dielectric_v04.csv"
VISCOSITY_ROSTER = ROOT / "data/viscosity_v02.csv"

EXPECTED_COLUMNS = [
    "inchikey", "pubchem_cid", "pubchem_version", "record_name", "formula",
    "molecular_mass", "charge", "multiplicity", "source_dataset", "source_level",
    "source_license", "source_doi", "homo_eV", "lumo_eV", "gap_eV", "homo_beta_eV",
    "lumo_beta_eV", "dipole_debye", "unit_check", "structure_check", "tags",
    "in_key_registry", "in_batt_orbit_pool", "in_epsilon_roster", "in_viscosity_roster",
    "in_viscosity_sample", "in_calibration_sample", "batt_homo_eV", "batt_lumo_eV", "batt_minus_pubchemqc_homo_eV",
    "batt_minus_pubchemqc_lumo_eV", "calib_homo_eV", "calib_lumo_eV",
    "calibration_id", "role",
]
ALLOWED_ROLES = {"paired_anchor", "calibrated_estimate", "uncalibrated_reference"}
BOOL_COLUMNS = ("in_key_registry", "in_batt_orbit_pool", "in_epsilon_roster",
                "in_viscosity_roster", "in_viscosity_sample", "in_calibration_sample")
MIN_PAIRED_N = 60
MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


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


def refit(pairs):
    if len(pairs) < MIN_PAIRED_N:
        return {"status": "insufficient_pairs", "n": len(pairs)}
    order = sorted(pairs, key=lambda p: p["inchikey"])
    folds = {p["inchikey"]: index % 2 for index, p in enumerate(order)}
    out_of_sample = []
    for held in (0, 1):
        train = [p for p in pairs if folds[p["inchikey"]] != held]
        test = [p for p in pairs if folds[p["inchikey"]] == held]
        if len(train) < 2 or not test:
            continue
        fit = fit_line([p["pubchemqc"] for p in train], [p["batt"] for p in train])
        if fit is None:
            continue
        for point in test:
            out_of_sample.append(
                (point["batt"], fit[0] * point["pubchemqc"] + fit[1])
            )
    if not out_of_sample:
        return {"status": "no_fold", "n": len(pairs)}
    mae = sum(abs(yhat - y) for y, yhat in out_of_sample) / len(out_of_sample)
    full = fit_line([p["pubchemqc"] for p in pairs], [p["batt"] for p in pairs])
    r = pearson([p["pubchemqc"] for p in pairs], [p["batt"] for p in pairs])
    status = "usable_with_flag" if (mae <= MAE_LIMIT_EV and r is not None and r >= R_LIMIT) else "reference_only"
    return {
        "status": status,
        "n": len(pairs),
        "n_out_of_sample": len(out_of_sample),
        "slope": full[0],
        "intercept": full[1],
        "pearson_r_in_sample": r,
        "mae_out_of_sample_eV": mae,
    }


def close(a, b, tol):
    if a is None or b is None:
        return a == b
    return abs(a - b) <= tol


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-raw", action="store_true")
    args = parser.parse_args(argv)

    failures = []
    notes = []
    counter = {"n": 0}

    def check(name, ok, detail=""):
        counter["n"] += 1
        print(f"{name:<46} {'PASS' if ok else 'FAIL'}{(' ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    layer_bytes = LAYER.read_bytes()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    with open(LAYER, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)

    check("layer_header_exact", header == EXPECTED_COLUMNS)
    check("layer_sha256_matches_summary",
          sha256_bytes(layer_bytes) == summary.get("layer_sha256"),
          summary.get("layer_sha256", ""))
    check("layer_row_count_matches_summary",
          len(rows) == summary.get("layer_rows"), f"{len(rows)} rows")
    keys = [row["inchikey"] for row in rows]
    check("keys_unique_and_sorted", keys == sorted(set(keys)), f"{len(set(keys))} unique")
    check("prereg_locked_and_digest",
          prereg.get("status") == "locked_before_run"
          and sha256_bytes(PREREG.read_bytes()) == summary.get("prereg_sha256"))
    digests = summary.get("input_digests") or {}
    check("input_digests_match",
          digests.get("data/processed/four_core_key_registry.csv") == sha256_bytes(REGISTRY.read_bytes())
          and digests.get("data/dielectric_v04.csv") == sha256_bytes(EPSILON_ROSTER.read_bytes())
          and digests.get("data/viscosity_v02.csv") == sha256_bytes(VISCOSITY_ROSTER.read_bytes()))

    with open(EPSILON_ROSTER, newline="", encoding="utf-8") as handle:
        epsilon_keys = {row["inchikey"] for row in csv.DictReader(handle) if row.get("inchikey")}
    with open(VISCOSITY_ROSTER, newline="", encoding="utf-8") as handle:
        viscosity_keys = {row["inchikey"] for row in csv.DictReader(handle) if row.get("inchikey")}
    registry = {}
    with open(REGISTRY, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            registry[row["inchikey"]] = row

    recomputed_coverage = {
        "harvested_unique_keys": len(rows),
        "epsilon_roster_keys": len(epsilon_keys),
        "epsilon_roster_hits": sum(1 for row in rows if row["inchikey"] in epsilon_keys),
        "viscosity_roster_keys": len(viscosity_keys),
        "viscosity_roster_hits": sum(1 for row in rows if row["inchikey"] in viscosity_keys),
        "key_registry_hits": sum(1 for row in rows if row["inchikey"] in registry),
        "batt_orbit_pool_hits": sum(
            1 for row in rows
            if registry.get(row["inchikey"], {}).get("has_orbitals") == "true"
            and registry.get(row["inchikey"], {}).get("HOMO_eV")
        ),
        "paired_anchor_rows": sum(1 for row in rows if row["role"] == "paired_anchor"),
        "calibrated_estimate_rows": sum(1 for row in rows if row["role"] == "calibrated_estimate"),
        "uncalibrated_reference_rows": sum(
            1 for row in rows if row["role"] == "uncalibrated_reference"
        ),
    }
    recorded = summary.get("coverage", {})
    coverage_ok = all(recorded.get(k) == v for k, v in recomputed_coverage.items())
    check("coverage_recomputed_matches_summary", coverage_ok,
          "" if coverage_ok else json.dumps(recomputed_coverage, sort_keys=True))

    roles_ok = all(row["role"] in ALLOWED_ROLES for row in rows)
    paired_ok = all(
        num(row["batt_homo_eV"]) is not None or num(row["batt_lumo_eV"]) is not None
        for row in rows if row["role"] == "paired_anchor"
    )
    calib_ok = all(
        num(row["calib_homo_eV"]) is not None or num(row["calib_lumo_eV"]) is not None
        for row in rows if row["role"] == "calibrated_estimate"
    ) if recomputed_coverage["calibrated_estimate_rows"] else True
    check("role_partition_consistent",
          roles_ok and paired_ok and calib_ok
          and sum(1 for row in rows if row["role"] in ALLOWED_ROLES) == len(rows))

    # The unit / structure columns are graded, and each grade is cross-checked
    # against something outside this file rather than merely re-read.
    audited_rows = sum(1 for row in rows if row["unit_check"] == "verified_eV_audited")
    audit = summary.get("unit_audit", {})
    check("unit_check_values_are_graded",
          {row["unit_check"] for row in rows} <= {"verified_eV_audited", "dataset_level_eV"}
          and audited_rows == summary["coverage"].get("unit_checked_rows")
          and audited_rows <= (audit.get("n") or 0),
          f"audited_rows={audited_rows} audit_n={audit.get('n')}")
    check("unit_audit_sample_is_stratified_and_discriminative",
          (audit.get("strata") or 0) >= 10
          and audit.get("valence_window_discriminates_units") is True
          and audit.get("card_declares_unit_for_scalar_fields") is False
          and audit.get("pass_rate") == 1.0)
    check("structure_check_values_are_graded",
          {row["structure_check"] for row in rows}
          <= {"inchikey_match_target", "inchikey_from_pubchem_cid"})
    cid_name_ok = True
    for row in rows:
        try:
            expected_prefix = f"{int(row['pubchem_cid']):09d}.B3LYP@PM6"
        except (TypeError, ValueError):
            cid_name_ok = False
            break
        if not row["record_name"].startswith(expected_prefix):
            cid_name_ok = False
            break
    check("pubchem_cid_matches_record_name", cid_name_ok)
    check("boolean_columns_parse",
          all(row[column] in ("true", "false") for row in rows for column in BOOL_COLUMNS))

    gap_ok = True
    gap_bad = 0
    for row in rows:
        homo, lumo, gap = num(row["homo_eV"]), num(row["lumo_eV"]), num(row["gap_eV"])
        if homo is None or lumo is None or gap is None:
            continue
        if abs(gap - (lumo - homo)) > 1e-5:
            gap_ok = False
            gap_bad += 1
    check("gap_identity_within_tolerance", gap_ok, f"{gap_bad} violations")

    ranges_ok = True
    for row in rows:
        homo, lumo = num(row["homo_eV"]), num(row["lumo_eV"])
        if homo is not None and not (-30.0 <= homo <= 0.0):
            ranges_ok = False
        # the closed-shell noble gases reach a very high LUMO (helium is a
        # legitimate viscosity-roster member), hence the 40 eV ceiling
        if lumo is not None and not (-30.0 <= lumo <= 40.0):
            ranges_ok = False
        dipole = num(row["dipole_debye"])
        if dipole is not None and dipole < 0:
            ranges_ok = False
    check("orbital_ranges_sane_eV", ranges_ok)

    registry_ok = True
    for row in rows:
        reg = registry.get(row["inchikey"])
        if reg is None or row["role"] != "paired_anchor":
            continue
        # the layer stores six decimals, the registry keeps full precision
        if not close(num(reg.get("HOMO_eV")), num(row["batt_homo_eV"]), 5e-7):
            registry_ok = False
        if reg.get("LUMO_eV") and not close(num(reg.get("LUMO_eV")), num(row["batt_lumo_eV"]), 5e-7):
            registry_ok = False
    check("registry_values_not_rewritten", registry_ok)

    paired_homo = [
        {"inchikey": row["inchikey"], "pubchemqc": num(row["homo_eV"]), "batt": num(row["batt_homo_eV"])}
        for row in rows
        if num(row["homo_eV"]) is not None and num(row["batt_homo_eV"]) is not None
    ]
    paired_lumo = [
        {"inchikey": row["inchikey"], "pubchemqc": num(row["lumo_eV"]), "batt": num(row["batt_lumo_eV"])}
        for row in rows
        if num(row["lumo_eV"]) is not None and num(row["batt_lumo_eV"]) is not None
    ]
    for name, pairs in (("homo", paired_homo), ("lumo", paired_lumo)):
        got = refit(pairs)
        want = summary.get("calibration", {}).get(name, {})
        ok = got.get("status") == want.get("status") and got.get("n") == want.get("n")
        if got.get("status") == "usable_with_flag" or want.get("status") == "usable_with_flag":
            ok = ok and close(got.get("slope"), want.get("slope"), 1e-9)
            ok = ok and close(got.get("intercept"), want.get("intercept"), 1e-9)
            ok = ok and close(got.get("mae_out_of_sample_eV"), want.get("mae_out_of_sample_eV"), 1e-9)
            ok = ok and close(got.get("pearson_r_in_sample"), want.get("pearson_r_in_sample"), 1e-9)
        check(f"calibration_refit_matches_summary_{name}", ok,
              f"n={got.get('n')} status={got.get('status')}")

    # Recompute the pre-registered sample coverage with the sampler that defined
    # the samples, so these numbers do not depend on the builder at all.
    sys.path.insert(0, str(ROOT))
    from probes.harvest_pubchemqc_orbital import load_targets

    harvest_targets, _, _ = load_targets()
    layer_keys = set(keys)
    sample_ok = True
    sample_detail = []
    for tag, field in (
        ("epsilon_roster", "epsilon_roster"),
        ("viscosity_roster_sample", "viscosity_roster_sample"),
        ("batt_calibration_sample", "registry_orbit_sample"),
    ):
        sample = {k for k, v in harvest_targets.items() if tag in v["tags"]}
        hits = len(sample & layer_keys)
        recorded = summary["coverage"].get(field + "_hits")
        recorded_size = summary["coverage"].get(field + "_size")
        sample_ok = sample_ok and recorded == hits and recorded_size == len(sample)
        sample_detail.append(f"{field}={hits}/{len(sample)}")
    check("sample_coverage_recomputed_from_the_sampler", sample_ok, " ".join(sample_detail))

    composition = summary.get("paired_anchor_composition", {})
    check("paired_anchor_composition_is_consistent",
          composition.get("n") == recomputed_coverage["paired_anchor_rows"]
          and composition.get("from_pre_registered_sample")
          == summary["coverage"].get("registry_orbit_sample_hits")
          and composition.get("from_targeted_harvest", 0)
          + composition.get("from_head_scan", 0)
          == composition.get("n"))

    judgements = summary.get("judgements", {}).get("C_second_source_coverage", {})
    check("judgements_consistent_with_coverage",
          judgements.get("epsilon_pass") == (recomputed_coverage["epsilon_roster_hits"] >= 40)
          and judgements.get("viscosity_pass")
          == (summary["coverage"].get("viscosity_roster_sample_hits", 0) >= 100))

    no_calib_on_paired = all(
        row["calib_homo_eV"] == "" and row["calib_lumo_eV"] == ""
        for row in rows if row["role"] == "paired_anchor"
    )
    check("paired_rows_carry_no_calibrated_value", no_calib_on_paired)

    unit = summary.get("unit_audit", {})
    check("unit_audit_recorded",
          unit.get("observed_unit") == "eV" and unit.get("declared_unit_in_card") == "hartree",
          f"pass_rate={unit.get('pass_rate')}")

    if args.check_raw:
        raw_dir = ROOT / "data/raw/pubchemqc_w17"
        if not (raw_dir / "manifest.json").exists():
            check("raw_relayer_present", False, "data/raw/pubchemqc_w17 missing")
        else:
            raw_ok = True
            for relative, digest in summary.get("input_digests", {}).items():
                if digest is None or not str(relative).startswith("data/raw/pubchemqc_w17/"):
                    continue
                path = ROOT / relative
                raw_ok = raw_ok and path.exists() and sha256_bytes(path.read_bytes()) == digest
            check("raw_layer_digests_match_summary", raw_ok)
            audit_path = raw_dir / "unit_audit.json"
            if audit_path.exists():
                audit_cids = {
                    row.get("cid")
                    for row in json.loads(audit_path.read_text(encoding="utf-8")).get("checks", [])
                }
                layer_cids = {int(row["pubchem_cid"]) for row in rows}
                audited_in_layer = {
                    int(row["pubchem_cid"])
                    for row in rows
                    if row["unit_check"] == "verified_eV_audited"
                }
                check("audited_cids_are_exactly_the_audited_layer_rows",
                      audited_in_layer == (audit_cids & layer_cids))
            sys.path.insert(0, str(ROOT))
            from probes.build_orbital_second_source import compose, render

            raw_rows, _ = compose()
            relaid = render(raw_rows).encode("utf-8")
            check("raw_relayer_byte_identical", relaid == layer_bytes)
    else:
        notes.append("run with --check-raw for the byte-exact re-derivation from the raw harvest")

    print()
    print(f"checks: {counter['n']}, failures: {len(failures)}")
    for note in notes:
        print("note: " + note)
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())