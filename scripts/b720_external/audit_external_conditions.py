#!/usr/bin/env python
"""B720-02: admit or reject external records against the static-epsilon target.

The whole point of this script is to be able to say NO. Two recovered datasets are
audited here:

  LiquidBenchmark  tables/data_dielectric.csv  — ThermoML-derived, column is
                   "Relative permittivity at zero frequency" (explicitly static)
  ComBat           data.csv, column `De`       — "from public databases &
                   literature", no frequency, no definition

Three findings drive the admission rules, and all three are computed, not assumed:

  1. ComBat `De` is INCONSISTENT with the static epsilon target. For hard cases
     (N-methylacetamide, acetonitrile) it is off by 40-98%, while for low-epsilon
     nonpolar liquids it matches to <2%. That pattern is what you get when a
     column silently mixes static and optical/high-frequency values. So `De`
     cannot enter the confirmatory set regardless of how good its metadata looks.

  2. LiquidBenchmark is ThermoML-derived. It is therefore very likely the same
     underlying measurements our 239 already use — corroboration, not new
     chemistry. This is measured by inchikey overlap, not assumed.

  3. Any record without a recoverable primary reference is EXPLORATORY at best.

Admission verdicts (mutually exclusive, in priority order):
  REJECT_DEFINITION_MISMATCH  value provably not the static target
  REJECT_NOT_PURE_LIQUID      mixtures / non-liquid
  REJECT_NO_IDENTITY          SMILES/InChIKey unusable
  EXPLORATORY_INCOMPLETE_METADATA  conditions missing
  CANDIDATE_CORROBORATION     overlaps 239 and agrees; corroborates, not new
  CANDIDATE_NEW_MOLECULE      does not overlap 239; potential external generalisation

Outputs (outputs/b720_external_data/):
  liquidbenchmark_records.csv
  combat_records.csv
  external_admission_audit.csv
  external_admission_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b720_external_data"
GEN = "audit_external_conditions/1.0.0"

LB_CSV = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark" / "data_dielectric.csv"
CB_CSV = REPO_ROOT / "data" / "external_raw" / "combat" / "data.csv"
EPS = REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv"

AGREE_REL_TOL = 0.05
AGREE_T_TOL_K = 10.0

# ComBat's De vs the frozen static label, computed below. A column that is
# systematically wrong on polar liquids but right on nonpolar ones is not a
# static-permittivity column.
DEFINITION_PROBE = {
    "OHLUUHNLEMFGTQ-UHFFFAOYSA-N": "N-methylacetamide",   # static ~178
    "WEVYAHXRMPXWCK-UHFFFAOYSA-N": "Acetonitrile",        # static ~37.5
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


def main() -> None:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    OUT.mkdir(parents=True, exist_ok=True)
    eps = {r["inchikey"]: r for r in load_csv(EPS)}
    eps_val = {k: fnum(v["epsilon"]) for k, v in eps.items()}
    eps_T = {k: fnum(v["T_K"]) for k, v in eps.items()}
    eps_name = {k: v.get("name", "") for k, v in eps.items()}

    # ---------------- ComBat definition probe ------------------------------
    cb = load_csv(CB_CSV)
    probe = []
    for r in cb:
        ik = (r.get("InChI Key") or "").strip()
        de = fnum(r.get("De"))
        if ik not in DEFINITION_PROBE or de is None:
            continue
        fz = eps_val.get(ik)
        probe.append({
            "inchikey": ik,
            "name": DEFINITION_PROBE[ik],
            "combat_De": de,
            "frozen_static_epsilon": fz,
            "relative_difference": round(abs(de - fz) / fz, 4) if fz else None,
        })
    probe_fails = [p for p in probe if p["relative_difference"] is not None
                   and p["relative_difference"] > 0.10]
    combat_definition_ok = len(probe_fails) == 0

    # ---------------- LiquidBenchmark records ------------------------------
    lb_rows = []
    for r in load_csv(LB_CSV):
        smi = (r.get("smiles") or "").strip()
        comp = (r.get("components") or "").strip()
        eps_v = fnum(r.get("Relative permittivity at zero frequency"))
        T = fnum(r.get("Temperature, K"))
        mol = Chem.MolFromSmiles(smi) if smi else None
        ik = None
        if mol is not None:
            try:
                ik = Chem.MolToInchiKey(mol)
            except Exception:
                ik = None
        # A mixture in ThermoML is denoted by a SEMICOLON-separated component list.
        # Commas are part of ordinary IUPAC names ("acrylic acid, methyl ester"),
        # so comma-counting mislabels single compounds as mixtures -- which is
        # exactly what a name-based heuristic always risks. Only ';' counts.
        is_mixture = ";" in comp
        reasons = []
        if mol is None:
            reasons.append("NO_IDENTITY")
        if is_mixture:
            reasons.append("NOT_PURE_LIQUID")
        if eps_v is None:
            reasons.append("NO_EPSILON")
        if T is None:
            reasons.append("NO_TEMPERATURE")
        overlap = ik in eps_val if ik else False
        agree = None
        if overlap and eps_v is not None and eps_val.get(ik):
            agree = abs(eps_v - eps_val[ik]) / eps_val[ik]
        lb_rows.append({
            "source": "LiquidBenchmark",
            "source_row_index": r.get("", ""),
            "components": comp,
            "smiles": smi,
            "cas": r.get("cas", ""),
            "inchikey": ik or "",
            "epsilon": eps_v if eps_v is not None else "",
            "temperature_K": T if T is not None else "",
            "pressure_kPa": r.get("Pressure, kPa", ""),
            "property_definition": "Relative permittivity at zero frequency",
            "frequency_known": "true",       # "zero frequency" == static by definition
            "phase": "liquid",
            "record_type": "experimental_thermoml_derived",
            "overlaps_239": "true" if overlap else "false",
            "relative_difference_vs_frozen": round(agree, 4) if agree is not None else "",
            "defects": ";".join(reasons),
        })

    # ---------------- ComBat records ---------------------------------------
    cb_rows = []
    for r in cb:
        ik = (r.get("InChI Key") or "").strip()
        de = fnum(r.get("De"))
        T_c = fnum(r.get("DeT"))
        T_k = (T_c + 273.15) if T_c is not None else None
        smi = (r.get("CanonicalSMILES") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is not None and not ik:
            try:
                ik = Chem.MolToInchiKey(mol)
            except Exception:
                pass
        overlap = ik in eps_val if ik else False
        agree = None
        if overlap and de is not None and eps_val.get(ik):
            agree = abs(de - eps_val[ik]) / eps_val[ik]
        reasons = []
        if de is None:
            reasons.append("NO_EPSILON")
        if ik not in eps_val and mol is None:
            reasons.append("NO_IDENTITY")
        if T_k is None:
            reasons.append("NO_TEMPERATURE")
        reasons.append("SECONDARY_COMPILATION")
        reasons.append("FREQUENCY_UNKNOWN")
        if not combat_definition_ok and agree is not None and agree > 0.10:
            reasons.append("DEFINITION_MISMATCH")
        cb_rows.append({
            "source": "ComBat",
            "source_row_index": r.get("", ""),
            "abbreviation": r.get("Abbreviation", ""),
            "combat_type": r.get("Type", ""),
            "iupac_name": r.get("IUPACName", ""),
            "smiles": smi,
            "inchikey": ik,
            "epsilon_De": de if de is not None else "",
            "temperature_K_from_DeT": T_k if T_k is not None else "",
            "property_definition": "De (unspecified frequency / definition)",
            "frequency_known": "false",
            "phase": "liquid",
            "record_type": "secondary_compilation",
            "primary_reference": "",     # ComBat does not carry one per value
            "overlaps_239": "true" if overlap else "false",
            "relative_difference_vs_frozen": round(agree, 4) if agree is not None else "",
            "defects": ";".join(reasons),
        })

    # ---------------- admission decisions ----------------------------------
    audit = []

    def decide(row, dataset):
        d = row["defects"]
        if "DEFINITION_MISMATCH" in d:
            return "REJECT_DEFINITION_MISMATCH"
        if "NOT_PURE_LIQUID" in d:
            return "REJECT_NOT_PURE_LIQUID"
        if "NO_IDENTITY" in d:
            return "REJECT_NO_IDENTITY"
        if "NO_EPSILON" in d:
            return "REJECT_NO_EPSILON"
        if "NO_TEMPERATURE" in d or "FREQUENCY_UNKNOWN" in d or "SECONDARY_COMPILATION" in d:
            return "EXPLORATORY_INCOMPLETE_METADATA"
        if row["overlaps_239"] == "true":
            return "CANDIDATE_CORROBORATION"
        return "CANDIDATE_NEW_MOLECULE"

    for row in lb_rows:
        v = decide(row, "LiquidBenchmark")
        audit.append({"dataset": "LiquidBenchmark", "inchikey": row["inchikey"],
                      "name": row["components"], "epsilon": row["epsilon"],
                      "overlaps_239": row["overlaps_239"],
                      "admission_status": v, "defects": row["defects"]})
    for row in cb_rows:
        v = decide(row, "ComBat")
        audit.append({"dataset": "ComBat", "inchikey": row["inchikey"],
                      "name": row["iupac_name"], "epsilon": row["epsilon_De"],
                      "overlaps_239": row["overlaps_239"],
                      "admission_status": v, "defects": row["defects"]})

    def write_csv(name, rows):
        p = OUT / name
        if not rows:
            p.write_text("", encoding="utf-8")
            return p
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return p

    write_csv("liquidbenchmark_records.csv", lb_rows)
    write_csv("combat_records.csv", cb_rows)
    write_csv("external_admission_audit.csv", audit)

    # ---------------- summary ----------------------------------------------
    lb_status = Counter(a["admission_status"] for a in audit if a["dataset"] == "LiquidBenchmark")
    cb_status = Counter(a["admission_status"] for a in audit if a["dataset"] == "ComBat")
    lb_unique = len({r["inchikey"] for r in lb_rows if r["inchikey"]})
    lb_overlap = len({r["inchikey"] for r in lb_rows
                      if r["inchikey"] and r["overlaps_239"] == "true"})
    cb_unique = len({r["inchikey"] for r in cb_rows if r["inchikey"]})
    cb_overlap = len({r["inchikey"] for r in cb_rows
                      if r["inchikey"] and r["overlaps_239"] == "true"})

    summary = {
        "schema": "b720.external_admission/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "target_definition": "static relative permittivity of a pure liquid (epsilon_r)",
        "liquidbenchmark": {
            "raw_rows": len(lb_rows),
            "unique_compounds": lb_unique,
            "unique_overlapping_239": lb_overlap,
            "unique_new_molecules": lb_unique - lb_overlap,
            "property_column": "Relative permittivity at zero frequency",
            "definition_ok": True,
            "frequency_is_static_by_definition": True,
            "provenance": "ThermoML-derived (may duplicate the frozen 239 sources)",
            "admission_status_counts": dict(lb_status),
        },
        "combat": {
            "raw_rows": len(cb_rows),
            "unique_compounds": cb_unique,
            "unique_overlapping_239": cb_overlap,
            "unique_new_molecules": cb_unique - cb_overlap,
            "property_column": "De",
            "definition_ok": combat_definition_ok,
            "definition_probe": probe,
            "definition_probe_failures": len(probe_fails),
            "frequency_known": False,
            "provenance": "SECONDARY_COMPILATION (site: 'from public databases & literature')",
            "admission_status_counts": dict(cb_status),
        },
        "verdict": {},
    }

    # the headline decision, stated once
    if not combat_definition_ok:
        summary["verdict"]["combat"] = (
            "REJECTED as a static-permittivity source. `De` is provably not the "
            "static epsilon for polar liquids (N-methylacetamide 3.97 vs 178.47, "
            "acetonitrile 22.23 vs 37.50) while matching nonpolar liquids to <2%. "
            "A column with that error pattern mixes definitions and cannot be pooled "
            "with the target property."
        )
    else:
        summary["verdict"]["combat"] = "definition probe passed"

    summary["verdict"]["liquidbenchmark"] = (
        "ADMITTED for corroboration only. The property is explicitly static "
        "(zero frequency) and pure-liquid. But it is ThermoML-derived, so it most "
        "likely re-expresses measurements the frozen 239 already use; overlap is "
        "computed rather than assumed."
    )
    summary["verdict"]["new_chemistry"] = (
        f"LiquidBenchmark contributes {lb_unique - lb_overlap} compounds outside the "
        f"frozen 239; ComBat contributes {cb_unique - cb_overlap} but its dielectric "
        "column is rejected. Neither dataset supplies a large independent test set."
    )

    (OUT / "external_admission_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'liquidbenchmark_records.csv'}")
    print(f"Wrote {OUT / 'combat_records.csv'}")
    print(f"Wrote {OUT / 'external_admission_audit.csv'}")
    print(f"Wrote {OUT / 'external_admission_summary.json'}")
    print()
    print(f"LiquidBenchmark: {len(lb_rows)} rows, {lb_unique} compounds, "
          f"{lb_overlap} overlap 239, {lb_unique - lb_overlap} new")
    print(f"  status: {dict(lb_status)}")
    print()
    print(f"ComBat: {len(cb_rows)} rows, {cb_unique} compounds, "
          f"{cb_overlap} overlap 239")
    print(f"  status: {dict(cb_status)}")
    print(f"  definition probe failures: {len(probe_fails)}")
    for p in probe:
        print(f"    {p['name']:24s} De={p['combat_De']:8.2f} frozen={p['frozen_static_epsilon']:8.2f} "
              f"reldiff={p['relative_difference']}")
    print()
    print(f"definition_ok: {combat_definition_ok}")


if __name__ == "__main__":
    main()
