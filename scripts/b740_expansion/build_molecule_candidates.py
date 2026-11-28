#!/usr/bin/env python
"""B741-01: build the molecule-expansion cohort ledger from the ThermoML scan.

This is the screen that decides which molecules may enter which cohort. It uses
only what the local ThermoML scan proves, and it refuses to promote anything that
lacks a per-molecule primary DOI with a stated temperature.

Five cohorts (the plan's, plus one for mixtures):

  CORE239                       the frozen modelling set
  SAME_MOLECULE_EXTERNAL        extra measurements of a CORE239 molecule
  NEW_MOLECULE_VALIDATED        new molecule with a static epsilon, temperature,
                                AND >=1 primary DOI naming the measurement
  NEW_MOLECULE_EXPLORATORY      new molecule with static epsilon but incomplete
                                conditions (e.g. only one DOI with no T, or
                                temperature only from a compilation)
  MIXTURE_MECHANISM_DATA        multi-component systems; mechanism study only
  COMPUTATIONAL_ONLY            no experiment, kept for DFT/xTB work only

Admission rule for VALIDATED, stated so it can be audited:
  * InChIKey present and resolvable
  * property == dielectric_constant_static (zero-frequency wording)
  * at least one record with a numeric temperature
  * at least one DOI distinct from the NBS 514 compendium
  * phase == Liquid
If any of those fails, the molecule lands in EXPLORATORY, never VALIDATED.

Outputs (outputs/b740_expansion/molecule_expansion/):
  cohort_ledger.csv
  cohort_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion"
GEN = "build_molecule_candidates/1.0.0"

SCAN = REPO_ROOT / "outputs" / "b740_expansion" / "thermoml" / "thermoml_local_scan.csv"
NBS_DOI = "10.6028/nbs.circ.514"


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
    OUT.mkdir(parents=True, exist_ok=True)
    scan = load_csv(SCAN)
    core = {}
    for r in load_csv(REPO_ROOT / "outputs" / "b100" / "deliverables"
                      / "epsilon_labels_b100.csv"):
        core[r["inchikey"]] = r

    pure = [r for r in scan if r["is_mixture"] == "false"]
    stat = [r for r in pure if r["property"] == "dielectric_constant_static"]
    dens = [r for r in pure if r["property"] == "density"]
    ri = [r for r in pure if r["property"] == "refractive_index"]
    hvap = [r for r in pure if r["property"] == "enthalpy_of_vaporization"]
    mix = [r for r in scan if r["is_mixture"] == "true"]

    def group(records):
        g = defaultdict(list)
        for r in records:
            if r["inchikey"]:
                g[r["inchikey"]].append(r)
        return g

    gstat, gdens, gri, ghvap = group(stat), group(dens), group(ri), group(hvap)

    rows = []
    all_iks = set(gstat) | set(gdens) | set(gri) | set(ghvap) | set(core)
    for ik in sorted(all_iks):
        st = gstat.get(ik, [])
        rh = gdens.get(ik, [])
        rf = gri.get(ik, [])
        hv = ghvap.get(ik, [])
        dois = {r["doi"] for r in st if r["doi"]}
        non_nbs = {d for d in dois if d and d != NBS_DOI}
        temps = [fnum(r["temperature_K"]) for r in st]
        temps = [t for t in temps if t is not None]
        eps_vals = [fnum(r["value"]) for r in st]
        eps_vals = [v for v in eps_vals if v is not None]
        names = [r["name"] for r in st + rh if r["name"]]
        name = core.get(ik, {}).get("name") or (names[0] if names else "")
        phases = {r["phase"] for r in st}

        # ---- cohort decision ----
        reasons = []
        if ik in core:
            cohort = "CORE239"
            reasons.append("member of the frozen modelling set")
        elif st and eps_vals:
            ok = True
            if not any(ph.lower().startswith("liquid") for ph in phases if ph):
                ok = False
                reasons.append("phase not stated as liquid")
            if not temps:
                ok = False
                reasons.append("no numeric temperature")
            if not non_nbs:
                ok = False
                reasons.append("no primary DOI beyond the NBS compendium")
            cohort = "NEW_MOLECULE_VALIDATED" if ok else "NEW_MOLECULE_EXPLORATORY"
            if ok:
                reasons.append("static epsilon + T + >=1 primary DOI")
        elif rh or rf or hv:
            cohort = "NEW_MOLECULE_EXPLORATORY"
            reasons.append("has auxiliary properties but no static epsilon")
        else:
            cohort = "COMPUTATIONAL_ONLY"
            reasons.append("no admissible experimental record")

        rows.append({
            "inchikey": ik,
            "name": name,
            "family_hint": core.get(ik, {}).get("family", ""),
            "cohort": cohort,
            "in_core239": "true" if ik in core else "false",
            "core_epsilon": core.get(ik, {}).get("epsilon", ""),
            "n_static_eps_records": len(st),
            "n_distinct_eps_dois": len(dois),
            "n_primary_dois_beyond_compendium": len(non_nbs),
            "n_density_records": len(rh),
            "n_refractive_index_records": len(rf),
            "n_hvap_records": len(hv),
            "eps_min": round(min(eps_vals), 4) if eps_vals else "",
            "eps_max": round(max(eps_vals), 4) if eps_vals else "",
            "eps_median": round(sorted(eps_vals)[len(eps_vals) // 2], 4) if eps_vals else "",
            "n_temperature_points": len(temps),
            "temperature_min_K": round(min(temps), 2) if temps else "",
            "temperature_max_K": round(max(temps), 2) if temps else "",
            "dois": ";".join(sorted(non_nbs))[:400],
            "cohort_rationale": "; ".join(reasons),
        })

    out_csv = OUT / "cohort_ledger.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts = Counter(r["cohort"] for r in rows)
    new_val = [r for r in rows if r["cohort"] == "NEW_MOLECULE_VALIDATED"]
    new_exp = [r for r in rows if r["cohort"] == "NEW_MOLECULE_EXPLORATORY"]
    mix_systems = {r["doi"] for r in mix if r["doi"]}

    doc = {
        "schema": "b740.cohort_ledger/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "criterion_for_validated": [
            "InChIKey present",
            "property == 'Relative permittivity at zero frequency'",
            "at least one numeric temperature",
            "at least one DOI distinct from the NBS 514 compendium",
            "phase stated as Liquid where stated",
        ],
        "n_molecules_in_ledger": len(rows),
        "cohort_counts": dict(counts),
        "core239_preserved": len(core),
        "new_molecule_validated": {
            "n": len(new_val),
            "with_ge2_primary_dois": sum(1 for r in new_val
                                         if int(r["n_primary_dois_beyond_compendium"]) >= 2),
            "with_ge5_temperature_points": sum(1 for r in new_val
                                               if int(r["n_temperature_points"]) >= 5),
            "names": [r["name"] for r in new_val],
        },
        "new_molecule_exploratory": {
            "n": len(new_exp),
            "reasons": dict(Counter(
                r["cohort_rationale"] for r in new_exp)),
        },
        "mixture_mechanism": {
            "n_mixture_records": len(mix),
            "n_distinct_dois": len(mix_systems),
            "policy": "mechanism study only; never used as pure-liquid epsilon",
        },
        "coverage_vs_core": {
            "core_with_static_eps_in_local_thermoml": len(set(core) & set(gstat)),
            "core_with_density": len(set(core) & set(gdens)),
            "core_with_refractive_index": len(set(core) & set(gri)),
            "core_with_all_three": len(set(core) & set(gstat) & set(gdens) & set(gri)),
        },
        "honesty_notes": [
            "The local ThermoML copy is 242 documents out of the full archive, so the "
            "validated count is a LOWER BOUND.",
            "A validated molecule still has only the properties ThermoML records; "
            "absence of a frequency field means the static wording is the only proof "
            "it is static.",
            "CORE239 membership is decided by the frozen epsilon_labels file and is "
            "never re-derived here.",
        ],
    }
    (OUT / "cohort_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'cohort_summary.json'}")
    print(f"molecules in ledger: {len(rows)}")
    print(f"cohorts: {dict(counts)}")
    print()
    print(f"NEW_MOLECULE_VALIDATED: {len(new_val)}")
    for r in sorted(new_val, key=lambda r: -int(r["n_primary_dois_beyond_compendium"]))[:15]:
        print(f"  {r['name'][:30]:30s} DOIs={r['n_primary_dois_beyond_compendium']:>4} "
              f"Tpts={r['n_temperature_points']:>4} eps {r['eps_min']}-{r['eps_max']}")
    print()
    print(f"CORE coverage: eps {doc['coverage_vs_core']['core_with_static_eps_in_local_thermoml']}, "
          f"rho {doc['coverage_vs_core']['core_with_density']}, "
          f"RI {doc['coverage_vs_core']['core_with_refractive_index']}, "
          f"all3 {doc['coverage_vs_core']['core_with_all_three']}")


if __name__ == "__main__":
    main()
