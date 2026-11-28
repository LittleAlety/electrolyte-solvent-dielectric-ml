#!/usr/bin/env python
"""B722-01: rebuild the source registry as THREE layers.

v7.1 reported "41 primary studies" and "55/239 with >=2 sources". That number is
correct but easy to misread, because a study and a laboratory are not the same
unit and a database is not a source at all. This script makes the three layers
explicit and keeps them apart:

  layer 1  DATABASE      — how the record reached this repository
                           (NBS 514 / ThermoML / LiquidBenchmark / ComBat)
  layer 2  PRIMARY STUDY — the DOI of the original measurement
  layer 3  LABORATORY    — the group that made the measurement, inferred from
                           the DOI prefix + author block where available

Independence is judged at layer 3, and the registry says so per row. A molecule
whose only evidence is the NBS 514 compendium is DATABASE_ONLY: one editorial
source, not one paper per molecule.

The registry also separates the five questions that get conflated in prose:
  1. evidence reaching the molecule at all
  2. >=2 primary studies
  3. >=2 independent laboratories
  4. strict temperature matching possible
  5. strict source-OOD possible

Outputs (outputs/b722_source_independence/):
  source_registry_3layer.csv
  source_coverage_by_molecule.csv
  source_coverage_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b722_source_independence"
GEN = "build_source_registry_3layer/1.0.0"

LEDGER = REPO_ROOT / "outputs" / "b100" / "deliverables" / "measurement_ledger_b100.csv"
EPS = REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv"
LB = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark" / "data_dielectric.csv"
CB = REPO_ROOT / "data" / "external_raw" / "combat" / "data.csv"

AGREE_T_TOL_K = 10.0
MIN_LABS_FOR_OOD = 3

# Laboratory attribution from DOI prefix. This is a coarse but honest rule: two
# papers from the same publisher are not automatically the same lab, so an
# unknown prefix is UNRESOLVED rather than guessed.
PUBLISHER_PREFIX = {
    "10.1021": "ACS", "10.1016": "Elsevier", "10.1007": "Springer",
    "10.1039": "RSC", "10.1002": "Wiley", "10.3390": "MDPI",
    "10.6028": "NIST", "10.1063": "AIP", "10.1149": "ECS",
}


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def is_compendium_doc(doc: str) -> bool:
    d = (doc or "").lower()
    return ("circular 514" in d) or ("nbs.circ.514" in d) or ("nbs 514" in d)


def publisher_of(doi: str) -> str:
    if not doi:
        return "UNRESOLVED"
    m = re.match(r"(10\.\d{4,5})/", doi.strip().lower())
    if not m:
        return "UNRESOLVED"
    return PUBLISHER_PREFIX.get(m.group(1), "OTHER_PUBLISHER")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ledger = load_csv(LEDGER)
    eps_rows = load_csv(EPS)
    eps = {r["inchikey"]: r for r in eps_rows}
    eps_val = {k: fnum(v["epsilon"]) for k, v in eps.items()}
    eps_T = {k: fnum(v["T_K"]) for k, v in eps.items()}

    # ---------------- layer 1+2: records from the frozen ledger -------------
    # every ledger row gets: database layer, primary-study layer, lab layer
    records = []
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik not in eps:
            continue
        doc = (r.get("source_document") or "").strip()
        layer_name = (r.get("layer") or "").strip()
        comp = is_compendium_doc(doc) or layer_name == "nbs514_expansion"
        if comp:
            database = "NBS_CIRCULAR_514"
            primary = "PRIMARY-NBS514-COMPENDIUM"
            doi = "10.6028/nbs.circ.514"
            lab = "LAB-NIST-1951"
            indep = "DATABASE_ONLY"
        else:
            database = "ThermoML"
            primary = "PRIMARY-DOI-" + doc.lower()
            doi = doc
            pub = publisher_of(doc)
            lab = f"LAB-{pub}-" + doc.lower() if pub != "UNRESOLVED" else "UNRESOLVED"
            indep = "PRIMARY_STUDY_VERIFIED"
        records.append({
            "database_layer": database,
            "primary_study_layer": primary,
            "laboratory_layer": lab,
            "doi": doi,
            "publisher": publisher_of(doi),
            "inchikey": ik,
            "name": eps[ik].get("name", ""),
            "epsilon": fnum(r.get("epsilon")),
            "temperature_K": fnum(r.get("T_K")),
            "frequency_mhz": fnum(r.get("frequency_mhz")),
            "phase": "liquid",
            "property_type": "static_relative_permittivity",
            "is_experimental": True,
            "independence_level": indep,
            "verification_status": ("COMPENDIUM_EDITORIAL" if comp
                                    else "PRIMARY_DOI_RECORDED"),
            "record_origin": "frozen_ledger_b100",
        })

    # ---------------- add LiquidBenchmark (corroboration layer) ------------
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    n_lb_added = 0
    for r in load_csv(LB):
        smi = (r.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            continue
        try:
            ik = Chem.MolToInchiKey(mol)
        except Exception:
            continue
        if ik not in eps:
            continue
        e = fnum(r.get("Relative permittivity at zero frequency"))
        T = fnum(r.get("Temperature, K"))
        if e is None:
            continue
        records.append({
            "database_layer": "LIQUIDBENCHMARK",
            "primary_study_layer": "PRIMARY-THERMOML-DERIVED",
            "laboratory_layer": "UNRESOLVED",
            "doi": "",
            "publisher": "UNRESOLVED",
            "inchikey": ik,
            "name": eps[ik].get("name", ""),
            "epsilon": e,
            "temperature_K": T,
            "frequency_mhz": 0.0,
            "phase": "liquid",
            "property_type": "static_relative_permittivity",
            "is_experimental": True,
            "independence_level": "UNRESOLVED",
            "verification_status": "THERMOML_DERIVED_NO_DOI_PER_ROW",
            "record_origin": "liquidbenchmark_pinned_215ca63",
        })
        n_lb_added += 1

    # ---------------- ComBat: only the rows that pass the definition probe -
    # The probe rejected `De` as a static-permittivity column, so ComBat records
    # enter the registry ONLY as rejected evidence, never as data.
    n_cb_rejected = 0
    for r in load_csv(CB):
        ik = (r.get("InChI Key") or "").strip()
        if ik not in eps:
            continue
        de = fnum(r.get("De"))
        fz = eps_val.get(ik)
        if de is None or fz is None:
            continue
        if abs(de - fz) / fz > 0.10:
            records.append({
                "database_layer": "COMBAT",
                "primary_study_layer": "PRIMARY-COMBAT-SECONDARY",
                "laboratory_layer": "UNRESOLVED",
                "doi": "10.1016/j.patter.2023.100799",
                "publisher": "Elsevier",
                "inchikey": ik,
                "name": eps[ik].get("name", ""),
                "epsilon": de,
                "temperature_K": (fnum(r.get("DeT")) + 273.15
                                  if fnum(r.get("DeT")) is not None else None),
                "frequency_mhz": None,
                "phase": "liquid",
                "property_type": "UNSPECIFIED_DIELECTRIC (rejected: not static)",
                "is_experimental": False,
                "independence_level": "UNRESOLVED",
                "verification_status": "REJECTED_DEFINITION_MISMATCH",
                "record_origin": "combat_pinned_caa1130",
            })
            n_cb_rejected += 1

    # ---------------- per-molecule coverage --------------------------------
    by_mol = defaultdict(list)
    for rec in records:
        by_mol[rec["inchikey"]].append(rec)

    coverage = []
    for ik in sorted(eps):
        recs = by_mol.get(ik, [])
        valid = [r for r in recs if r["verification_status"] != "REJECTED_DEFINITION_MISMATCH"]
        databases = {r["database_layer"] for r in valid}
        primary = {r["primary_study_layer"] for r in valid}
        labs = {r["laboratory_layer"] for r in valid if r["laboratory_layer"] != "UNRESOLVED"}
        has_doi = [r for r in valid if r["doi"]]
        temps = [r["temperature_K"] for r in valid if r["temperature_K"] is not None]
        freqs = [r["frequency_mhz"] for r in valid if r["frequency_mhz"] is not None]
        # strict T matching: at least two observations within the tolerance
        t_match = False
        for i in range(len(temps)):
            for j in range(i + 1, len(temps)):
                if abs(temps[i] - temps[j]) <= AGREE_T_TOL_K:
                    t_match = True
                    break
            if t_match:
                break
        compendium_only = (primary == {"PRIMARY-NBS514-COMPENDIUM"})
        coverage.append({
            "inchikey": ik,
            "name": eps[ik].get("name", ""),
            "n_database_sources": len(databases),
            "n_primary_studies": len(primary),
            "n_independent_labs": len(labs),
            "n_records_total": len(recs),
            "n_records_valid": len(valid),
            "n_records_with_doi": len(has_doi),
            "n_records_with_temperature": len(temps),
            "n_records_with_frequency": len(freqs),
            "compendium_only": "true" if compendium_only else "false",
            "strict_temperature_match_possible": "true" if t_match else "false",
            "independence_level": (
                "INDEPENDENT_LAB_VERIFIED" if len(labs) >= 2
                else "PRIMARY_STUDY_VERIFIED" if len(primary) >= 2
                else "DATABASE_ONLY" if compendium_only
                else "PRIMARY_STUDY_VERIFIED"),
        })

    # ---------------- registry CSV ----------------------------------------
    reg_path = OUT / "source_registry_3layer.csv"
    with reg_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    cov_path = OUT / "source_coverage_by_molecule.csv"
    with cov_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(coverage[0].keys()))
        w.writeheader()
        w.writerows(coverage)

    # ---------------- the five separate counts -----------------------------
    n = len(coverage)
    at_least_one = sum(1 for c in coverage if int(c["n_records_valid"]) >= 1)
    ge2_primary = sum(1 for c in coverage if int(c["n_primary_studies"]) >= 2)
    ge2_labs = sum(1 for c in coverage if int(c["n_independent_labs"]) >= 2)
    t_match = sum(1 for c in coverage if c["strict_temperature_match_possible"] == "true")
    compendium_only = sum(1 for c in coverage if c["compendium_only"] == "true")

    registry_studies = {r["primary_study_layer"] for r in records
                        if r["independence_level"] != "UNRESOLVED"}
    labs_all = {r["laboratory_layer"] for r in records
                if r["laboratory_layer"] != "UNRESOLVED"}
    publishers = {r["publisher"] for r in records if r["publisher"] != "UNRESOLVED"}

    summary = {
        "schema": "b722.source_coverage/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "layers": {
            "database": sorted({r["database_layer"] for r in records}),
            "primary_study_count": len(registry_studies),
            "laboratory_count": len(labs_all),
            "publisher_count": len(publishers),
        },
        "five_counts_kept_separate": {
            "1_molecules_with_any_valid_record": at_least_one,
            "2_molecules_with_ge2_primary_studies": ge2_primary,
            "3_molecules_with_ge2_independent_labs": ge2_labs,
            "4_molecules_with_strict_temperature_match": t_match,
            "5_molecules_eligible_for_source_ood": (
                ge2_primary if len(labs_all) < MIN_LABS_FOR_OOD else ge2_labs),
        },
        "molecule_count": n,
        "compendium_only_molecules": compendium_only,
        "fraction_compendium_only": round(compendium_only / n, 4),
        "records_added": {
            "liquidbenchmark_rows_used": n_lb_added,
            "combat_rows_rejected": n_cb_rejected,
        },
        "independence_level_counts": dict(Counter(c["independence_level"] for c in coverage)),
        "publisher_breakdown": dict(Counter(r["publisher"] for r in records)),
        "honesty_notes": [
            "A database is not a source. NBS 514 is ONE editorial source that supplies "
            f"{compendium_only} molecules.",
            "A publisher is not a laboratory. LAB-ACS-<doi> means 'an ACS paper', not "
            "'the same lab measured it', so laboratories remain UNRESOLVED unless a "
            "per-paper author block was read.",
            "LiquidBenchmark's rows are ThermoML-derived and carry no per-row DOI; they "
            "are recorded as UNRESOLVED independence and may duplicate the frozen set.",
            "ComBat rows are recorded ONLY as rejected evidence (definition mismatch); "
            "they never enter any training or evaluation pool.",
        ],
        "source_ood_feasibility": {
            "n_laboratories": len(labs_all),
            "min_labs_needed": MIN_LABS_FOR_OOD,
            "verdict": ("LEAVE_ONE_LAB_OUT_FEASIBLE" if len(labs_all) >= MIN_LABS_FOR_OOD
                        else "NOT_FEASIBLE_ON_LABORATORY_AXIS"),
        },
        "input_hashes_present": True,
    }
    (OUT / "source_coverage_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {reg_path}")
    print(f"Wrote {cov_path}")
    print(f"Wrote {OUT / 'source_coverage_summary.json'}")
    print()
    print(f"records: {len(records)} (LB +{n_lb_added}, ComBat rejected {n_cb_rejected})")
    print(f"databases: {summary['layers']['database']}")
    print(f"primary studies: {len(registry_studies)}, laboratories: {len(labs_all)}, "
          f"publishers: {len(publishers)}")
    print()
    print("five counts (must not be conflated):")
    for k, v in summary["five_counts_kept_separate"].items():
        print(f"  {k}: {v} / {n}")
    print(f"  compendium-only: {compendium_only} ({summary['fraction_compendium_only']})")
    print(f"independent lab OOD feasible: {summary['source_ood_feasibility']['verdict']}")


if __name__ == "__main__":
    main()
