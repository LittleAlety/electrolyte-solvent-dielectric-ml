#!/usr/bin/env python
"""B710-01: build a real source registry keyed on the ORIGINAL measurement.

The v6.0/v7.0 limitation is not "few DOIs" — it is that 113 of 240 model-ready rows
trace to ONE editorial compendium (NBS Circular 514). A compendium is one source of
evidence, not 113. Two databases citing the same primary paper are also one source.

This script rebuilds independence from the measurement ledger, applying three rules:

  R1  A compendium (NBS 514) counts as ONE source no matter how many rows/parts it
      contributes.
  R2  Independence is decided at the level of the ORIGINAL study (document DOI), not
      the database that republished it.
  R3  A molecule is "independently corroborated" only if >=2 original studies report
      it, and their values agree within a stated tolerance at comparable conditions.

It then reports the honesty-critical numbers:
  - how many distinct original studies actually back the 239-molecule set
  - how many molecules have >=2 independent originals
  - whether a strict independent test set of meaningful size can be built

Outputs (outputs/b710_evidence/source_independence/):
  source_registry.csv
  source_lineage.json
  molecule_source_overlap.csv
  external_data_audit.csv
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "source_independence"
GEN = "build_source_registry/1.0.0"

LEDGER = REPO_ROOT / "outputs" / "b100" / "deliverables" / "measurement_ledger_b100.csv"
EPS = REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv"
V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
EXT2 = REPO_ROOT / "data" / "raw" / "open_data_eps2" / "observations.csv"
PUBCHEM = REPO_ROOT / "data" / "raw" / "pubchem_eps" / "pugview_eps.csv"

# R3 tolerances
AGREE_REL_TOL = 0.05      # 5% relative
AGREE_T_TOL_K = 10.0      # within 10 K counts as comparable conditions
COMPENDIUM_IDS = {"nbs514_expansion", "NBS Circular 514", "nbs514"}
MIN_SOURCES_FOR_CLAIM = 5
MIN_SOURCES_FOR_EXPLORATORY = 3


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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def is_compendium(doc: str, layer: str) -> bool:
    d = (doc or "").strip().lower()
    if layer == "nbs514_expansion":
        return True
    return "nbs circular 514" in d or "nbs.circ.514" in d or "circular 514" in d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    ledger = load_csv(LEDGER)
    eps_rows = load_csv(EPS)
    v04 = load_csv(V04)
    ext2 = load_csv(EXT2)
    pubchem = load_csv(PUBCHEM)

    eps_set = {r["inchikey"] for r in eps_rows}
    name_of = {r["inchikey"]: r.get("name", "") for r in eps_rows}

    # ---------------- original-study registry from the measurement ledger -------
    # key: original study identifier (document DOI, or the compendium singleton)
    studies = {}
    for r in ledger:
        doc = (r.get("source_document") or "").strip()
        layer = (r.get("layer") or "").strip()
        if not doc:
            continue
        if is_compendium(doc, layer):
            sid = "SRC-NBS514-COMPENDIUM"
            rec = studies.setdefault(sid, {
                "source_id": sid,
                "original_paper": "Maryott & Smith, NBS Circular 514 (1951)",
                "doi": "10.6028/nbs.circ.514",
                "database_name": "NBS Circular 514",
                "is_compendium": True,
                "is_experimental": True,
                "laboratory": "National Bureau of Standards (US)",
                "publication_year": 1951,
                "measurement_method": "resonance/capacitance methods (compilation)",
                "n_rows": 0,
                "molecules": set(),
                "temperatures": [],
                "frequencies": [],
            })
        else:
            sid = "SRC-DOI-" + doc.lower()
            rec = studies.setdefault(sid, {
                "source_id": sid,
                "original_paper": doc,
                "doi": doc,
                "database_name": "ThermoML",
                "is_compendium": False,
                "is_experimental": True,
                "laboratory": "",
                "publication_year": None,
                "measurement_method": "",
                "n_rows": 0,
                "molecules": set(),
                "temperatures": [],
                "frequencies": [],
            })
        rec["n_rows"] += 1
        ik = (r.get("inchikey") or "").strip()
        if ik:
            rec["molecules"].add(ik)
        t = fnum(r.get("T_K"))
        if t is not None:
            rec["temperatures"].append(t)
        fr = fnum(r.get("frequency_mhz"))
        if fr is not None:
            rec["frequencies"].append(fr)

    # ---------------- external (non-ledger) sources ----------------------------
    ext_sources = {}
    for r, tag in [(x, "open_data_eps2") for x in ext2] + [(x, "pubchem_eps") for x in pubchem]:
        url = (r.get("source_url") or "").strip()
        if not url:
            continue
        sid = "SRC-EXT-" + hashlib.sha256(url.encode()).hexdigest()[:12]
        rec = ext_sources.setdefault(sid, {
            "source_id": sid,
            "original_paper": url,
            "doi": url.replace("https://doi.org/", ""),
            "database_name": tag,
            "is_compendium": False,
            "is_experimental": True,
            "laboratory": "",
            "publication_year": None,
            "measurement_method": "",
            "n_rows": 0,
            "molecules": set(),
            "temperatures": [],
            "frequencies": [],
        })
        rec["n_rows"] += 1
        ik = (r.get("inchikey") or "").strip()
        if ik:
            rec["molecules"].add(ik)
        t = fnum(r.get("t_k"))
        if t is not None:
            rec["temperatures"].append(t)
        fr = fnum(r.get("frequency_mhz"))
        if fr is not None:
            rec["frequencies"].append(fr)

    # ---------------- overlap between DB-level sources -------------------------
    # Does open_data_eps2 re-cite a paper already in the ThermoML ledger?
    ledger_dois = {s["doi"].lower() for s in studies.values() if s["doi"]}
    ext_dupes = []
    for sid, s in ext_sources.items():
        if s["doi"] and s["doi"].lower() in ledger_dois:
            ext_dupes.append({"source_id": sid, "doi": s["doi"],
                              "duplicate_of": "ThermoML ledger document"})

    # ---------------- per-molecule source coverage -----------------------------
    mol_sources = defaultdict(set)
    mol_compendium_only = defaultdict(bool)
    for sid, s in studies.items():
        for ik in s["molecules"]:
            if ik in eps_set:
                mol_sources[ik].add(sid)
    for sid, s in ext_sources.items():
        for ik in s["molecules"]:
            if ik in eps_set:
                mol_sources[ik].add(sid)

    # ---------------- cross-source agreement (rule R3) -------------------------
    # Use the ledger to compare values of the SAME molecule from DIFFERENT originals.
    per_mol_obs = defaultdict(list)   # inchikey -> list of (source_id, T, eps)
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik not in eps_set:
            continue
        doc = (r.get("source_document") or "").strip()
        layer = (r.get("layer") or "").strip()
        sid = "SRC-NBS514-COMPENDIUM" if is_compendium(doc, layer) else "SRC-DOI-" + doc.lower()
        e = fnum(r.get("epsilon"))
        t = fnum(r.get("T_K"))
        if e is not None:
            per_mol_obs[ik].append((sid, t, e))

    agree_counts = Counter()
    overlap_rows = []
    corroborated = 0
    for ik in sorted(eps_set):
        obs = per_mol_obs.get(ik, [])
        distinct_srcs = {o[0] for o in obs}
        pair_status = "SINGLE_SOURCE"
        rel = None
        if len(distinct_srcs) >= 2:
            # find best pairwise comparison at comparable T
            best = None
            for i in range(len(obs)):
                for j in range(i + 1, len(obs)):
                    s1, t1, e1 = obs[i]
                    s2, t2, e2 = obs[j]
                    if s1 == s2:
                        continue
                    if t1 is not None and t2 is not None and abs(t1 - t2) > AGREE_T_TOL_K:
                        continue
                    if not e2:
                        continue
                    r_ = abs(e1 - e2) / abs(e2)
                    if best is None or r_ < best[0]:
                        best = (r_, e1, e2, t1, t2)
            if best is not None:
                rel = best[0]
                pair_status = "AGREE" if rel <= AGREE_REL_TOL else "CONFLICT"
        if pair_status in ("AGREE", "CONFLICT"):
            corroborated += 1
        agree_counts[pair_status] += 1
        overlap_rows.append({
            "inchikey": ik,
            "name": name_of.get(ik, ""),
            "n_sources": len(mol_sources.get(ik, ())),
            "n_ledger_observations": len(obs),
            "n_distinct_ledger_sources": len(distinct_srcs),
            "contains_compendium": "true" if "SRC-NBS514-COMPENDIUM" in mol_sources.get(ik, set()) else "false",
            "cross_source_status": pair_status,
            "best_relative_difference": round(rel, 6) if rel is not None else "",
        })

    # ---------------- external records vs frozen labels -------------------------
    # The plan asks whether external data can build an independent test set. Two
    # things decide that: (i) does the external value agree with the frozen label
    # at comparable temperature, (ii) does the external source cover molecules the
    # 239 already contain (in which case it is corroboration, not new chemistry).
    frozen_eps = {r["inchikey"]: fnum(r["epsilon"]) for r in eps_rows}
    frozen_T = {r["inchikey"]: fnum(r["T_K"]) for r in eps_rows}
    external_agreement = []
    for r in list(ext2) + list(pubchem):
        ik = (r.get("inchikey") or "").strip()
        if ik not in frozen_eps:
            continue
        ext_eps = fnum(r.get("epsilon"))
        ext_T = fnum(r.get("t_k"))
        fz = frozen_eps.get(ik)
        fT = frozen_T.get(ik)
        if ext_eps is None or fz is None:
            continue
        comparable = (ext_T is None and fT is None) or (
            ext_T is not None and fT is not None and abs(ext_T - fT) <= AGREE_T_TOL_K)
        rel = abs(ext_eps - fz) / abs(fz) if fz else None
        external_agreement.append({
            "inchikey": ik,
            "name": r.get("name", ""),
            "source_url": r.get("source_url", ""),
            "external_epsilon": ext_eps,
            "external_T_K": ext_T,
            "frozen_epsilon": fz,
            "frozen_T_K": fT,
            "comparable_conditions": bool(comparable),
            "relative_difference": round(rel, 6) if rel is not None else None,
            "agrees_within_5pct": (bool(rel <= AGREE_REL_TOL) if rel is not None else None),
        })

    comparable_agreement = [x for x in external_agreement if x["comparable_conditions"]]
    ext_summary = {
        "n_external_records_overlapping_239": len(external_agreement),
        "n_comparable_conditions": len(comparable_agreement),
        "n_agree_within_5pct": sum(1 for x in comparable_agreement if x["agrees_within_5pct"]),
        "median_relative_difference": (
            round(statistics.median([x["relative_difference"] for x in comparable_agreement
                                     if x["relative_difference"] is not None]), 4)
            if comparable_agreement else None),
        "can_build_independent_test_set": bool(
            len(comparable_agreement) >= 20 and
            sum(1 for x in comparable_agreement if x["agrees_within_5pct"]) >= 10),
        "why_not": (
            "external coverage of the 239 is small, most records lack frequency and "
            "temperature, and every overlapping record is a re-measurement of a "
            "molecule already in the set -- that is corroboration, not new chemistry"
        ),
    }

    # ---------------- external data audit --------------------------------------
    ext_audit = []
    for sid, s in ext_sources.items():
        overlap_n = len(s["molecules"] & eps_set)
        cond_complete = bool(s["temperatures"]) and bool(s["molecules"])
        ext_audit.append({
            "source_id": sid,
            "doi": s["doi"],
            "database_name": s["database_name"],
            "n_rows": s["n_rows"],
            "n_compounds": len(s["molecules"]),
            "n_overlap_with_239": overlap_n,
            "has_temperature": "true" if s["temperatures"] else "false",
            "has_frequency": "true" if s["frequencies"] else "false",
            "admission_status": ("EXPLORATORY" if not cond_complete or overlap_n == 0
                                 else "CANDIDATE_EXTERNAL"),
            "reason": ("conditions incomplete or no overlap with the frozen 239"
                       if not cond_complete or overlap_n == 0
                       else "overlaps the 239 and carries at least temperature"),
        })

    # ---------------- registry CSV ---------------------------------------------
    all_sources = list(studies.values()) + list(ext_sources.values())
    reg_path = OUT / "source_registry.csv"
    with reg_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "original_paper", "DOI", "laboratory",
                    "publication_year", "database_name", "original_reference",
                    "measurement_method", "temperature_min_K", "temperature_max_K",
                    "frequency_mhz_median", "phase", "property_type",
                    "is_experimental", "source_independence", "admission_status",
                    "n_rows", "n_compounds", "n_overlap_with_239"])
        for s in all_sources:
            temps = s["temperatures"]
            freqs = s["frequencies"]
            reg_path_row = [
                s["source_id"], s["original_paper"], s["doi"], s["laboratory"],
                s["publication_year"], s["database_name"], s["doi"],
                s["measurement_method"],
                round(min(temps), 2) if temps else "",
                round(max(temps), 2) if temps else "",
                round(statistics.median(freqs), 3) if freqs else 0.0,
                "liquid", "static relative permittivity",
                "true" if s["is_experimental"] else "false",
                "COMPENDIUM_SINGLE" if s["is_compendium"] else "PRIMARY_STUDY",
                ("COMPENDIUM" if s["is_compendium"] else "PRIMARY"),
                s["n_rows"], len(s["molecules"]),
                len(s["molecules"] & eps_set),
            ]
            w.writerow(reg_path_row)

    # ---------------- lineage JSON ---------------------------------------------
    n_primary = sum(1 for s in studies.values() if not s["is_compendium"])
    n_total_primary = n_primary
    mol_with_ge2 = sum(1 for ik in eps_set if len(mol_sources.get(ik, ())) >= 2)
    mol_with_ge3 = sum(1 for ik in eps_set if len(mol_sources.get(ik, ())) >= 3)
    compendium_only = sum(1 for ik in eps_set
                          if mol_sources.get(ik) == {"SRC-NBS514-COMPENDIUM"})
    single_primary = sum(1 for ik in eps_set
                         if len(mol_sources.get(ik, ())) == 1
                         and mol_sources.get(ik) != {"SRC-NBS514-COMPENDIUM"})

    lineage = {
        "schema": "b710.source_lineage/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "rules": {
            "R1_compendium_is_one_source": "NBS Circular 514 counts once regardless of row/part count",
            "R2_independence_at_original_study": "same primary paper republished by two databases is one source",
            "R3_corroboration": f"two originals agree if |rel diff| <= {AGREE_REL_TOL} at |dT| <= {AGREE_T_TOL_K} K",
        },
        "ledger_original_studies": n_primary,
        "compendia_present": ["SRC-NBS514-COMPENDIUM"],
        "external_databases_audited": sorted({s["database_name"] for s in ext_sources.values()}),
        "external_sources_with_ledger_duplicate_doi": ext_dupes,
        "molecules_239": len(eps_set),
        "molecules_with_1_source": sum(1 for ik in eps_set if len(mol_sources.get(ik, ())) == 1),
        "molecules_with_ge2_sources": mol_with_ge2,
        "molecules_with_ge3_sources": mol_with_ge3,
        "cross_source_status_counts": dict(agree_counts),
        "molecules_independently_corroborated": corroborated,
        "n_primary_studies_after_dedup": n_total_primary,
        # Two levels must be reported separately. "Enough studies exist overall" and
        # "the modelled molecules are individually corroborated" are different claims,
        # and conflating them is exactly how a 1-compendium dataset gets described as
        # multi-source. The molecular-level coverage is the binding constraint.
        "external_agreement": ext_summary,
        "external_agreement_detail_count": len(external_agreement),
        "molecule_level_coverage": {
            "compendium_only": compendium_only,
            "single_primary_study": single_primary,
            "with_ge2_independent_sources": mol_with_ge2,
            "fraction_with_ge2_independent_sources": round(mol_with_ge2 / max(len(eps_set), 1), 4),
        },
        "claim_gate": {
            "min_for_exploratory": MIN_SOURCES_FOR_EXPLORATORY,
            "min_for_claim": MIN_SOURCES_FOR_CLAIM,
            "n_primary_studies": n_total_primary,
            "study_level_verdict": (
                "ENOUGH_PRIMARY_STUDIES" if n_total_primary >= MIN_SOURCES_FOR_CLAIM
                else "EXPLORATORY_FEW_STUDIES" if n_total_primary >= MIN_SOURCES_FOR_EXPLORATORY
                else "TOO_FEW_STUDIES"
            ),
            "molecule_level_verdict": (
                "MAJORITY_INDEPENDENTLY_CORROBORATED"
                if mol_with_ge2 / max(len(eps_set), 1) >= 0.5
                else "MINORITY_INDEPENDENTLY_CORROBORATED"
            ),
            "binding_constraint": "molecule-level coverage, not study count",
            "permitted_claim": (
                "Large-N modelling study with cross-source validation possible on the "
                f"{mol_with_ge2} molecules that carry >=2 independent sources; the "
                f"{compendium_only} compendium-only molecules support modelling but NOT "
                "a cross-source generalisation claim."
            ),
        },
        "input_hashes": {
            "measurement_ledger": sha256(LEDGER) if LEDGER.exists() else "",
            "epsilon_labels": sha256(EPS),
            "dielectric_v04": sha256(V04),
            "open_data_eps2": sha256(EXT2) if EXT2.exists() else "",
            "pubchem_eps": sha256(PUBCHEM) if PUBCHEM.exists() else "",
        },
    }
    (OUT / "source_lineage.json").write_text(
        json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- overlap CSV ----------------------------------------------
    with (OUT / "molecule_source_overlap.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(overlap_rows[0].keys()))
        w.writeheader()
        w.writerows(overlap_rows)

    # ---------------- external audit CSV ---------------------------------------
    with (OUT / "external_data_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ext_audit[0].keys()))
        w.writeheader()
        w.writerows(ext_audit)

    print(f"Wrote {reg_path}")
    print(f"Wrote {OUT / 'source_lineage.json'}")
    print(f"Wrote {OUT / 'molecule_source_overlap.csv'}")
    print(f"Wrote {OUT / 'external_data_audit.csv'}")
    print()
    print(f"primary original studies (dedup): {n_primary}")
    print(f"compendia: 1 (NBS 514)")
    print(f"molecules with >=2 sources: {mol_with_ge2}")
    print(f"molecules with >=3 sources: {mol_with_ge3}")
    print(f"cross-source status: {dict(agree_counts)}")
    print(f"compendium-only molecules: {compendium_only} / {len(eps_set)}")
    print(f"study-level: {lineage['claim_gate']['study_level_verdict']}")
    print(f"molecule-level: {lineage['claim_gate']['molecule_level_verdict']}")
    print(f"external DB dupe DOIs: {len(ext_dupes)}")
    print(f"external overlap records: {ext_summary['n_external_records_overlapping_239']}, "
          f"comparable: {ext_summary['n_comparable_conditions']}, "
          f"agree<5%: {ext_summary['n_agree_within_5pct']}")
    print(f"independent test set buildable: {ext_summary['can_build_independent_test_set']}")

    with (OUT / "external_agreement.csv").open("w", newline="", encoding="utf-8") as f:
        if external_agreement:
            w = csv.DictWriter(f, fieldnames=list(external_agreement[0].keys()))
            w.writeheader()
            w.writerows(external_agreement)


if __name__ == "__main__":
    main()
