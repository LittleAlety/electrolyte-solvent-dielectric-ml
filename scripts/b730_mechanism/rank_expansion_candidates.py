#!/usr/bin/env python
"""B735-01: targeted expansion candidate pool, ranked by what it can TEST.

The plan allows adding molecules but does not require it. So the pool is built to
close specific gaps found in B731-B734, not to raise n:

  G1 chlorinated ethers   n=2 in CORE239; within-subtype ranking untestable
  G2 association-heavy    ASSOCIATION_HEAVY is the most common mechanism tag (106)
  G3 conformer-sensitive  C_mu > 0.5 for 22 of 39; needs structural contrast
  G4 low-polarity/high-eps only 1 molecule carries that tag
  G5 family gaps          ester / halocarbon / nitrile under-represented

Candidate sources, in order of provenance quality:
  A. LiquidBenchmark compounds NOT in CORE239 -> static epsilon, temperature given,
     but ThermoML-derived with no per-row DOI  => NEW_MOLECULE_EXPLORATORY
  B. CRAFT-epsilon reference liquids NOT in CORE239 -> epsilon is the author's
     stored value, not a per-molecule primary reference => EXPLORATORY
  C. CORE239 molecules that already lack a conformer analysis -> no new chemistry,
     just more conformer work (reported separately, not "new molecules")

Nothing is admitted to NEW_MOLECULE_VALIDATED by this script: that status requires
a per-molecule primary reference with temperature AND frequency, which neither
recovered dataset supplies. The script's job is to say which candidates WOULD help
and what evidence each still lacks.

Outputs (outputs/b730_mechanism/expansion_candidates/):
  expansion_candidates.csv
  expansion_rationale.json
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "expansion_candidates"
GEN = "rank_expansion_candidates/1.0.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LB = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark" / "data_dielectric.csv"
CRAFT_REF = REPO_ROOT / "data" / "external_raw" / "craft_epsilon" / "tests_data_reference.json"
MECH = REPO_ROOT / "outputs" / "b730_mechanism" / "error_mechanism" / "molecule_error_mechanism_map.csv"

# Same rules as B724 v2, so a candidate's subtype is comparable with CORE239.
_PAT = {}


def _pat(smarts):
    """Compile each SMARTS once. [CX4]-[#8]-[#CX4] is not a valid RDKit SMARTS
    (#CX4 is not a valid primitive), which returned None and crashed the match;
    [#6X4]-[#8]-[#6X4] is the correct acyclic-sp3 ether form."""
    if smarts not in _PAT:
        from rdkit import Chem
        _PAT[smarts] = Chem.MolFromSmarts(smarts)
    return _PAT[smarts]


def classify(mol):
    ether = mol.HasSubstructMatch(_pat("[#6]-[#8]-[#6]"))
    aryl = mol.HasSubstructMatch(_pat("[c]-[#8]-[#6]"))
    aliph = mol.HasSubstructMatch(_pat("[#6X4]-[#8]-[#6X4]"))
    cyc = mol.HasSubstructMatch(_pat("[#6;R]-[#8]-[#6]"))
    ncl = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
    if not ether:
        return None
    if ncl >= 1:
        return "chlorinated_ether"
    if aryl:
        return "aromatic_ether"
    if cyc:
        return "cyclic_ether"
    if aliph:
        return "aliphatic_ether"
    return "other_or_ambiguous"


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
    from rdkit.Chem import rdMolDescriptors
    RDLogger.DisableLog("rdApp.*")

    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    mech = {r["inchikey"]: r for r in load_csv(MECH)}
    core_iks = set(desc)

    # gap sizing from CORE239 itself
    fam_counts = {}
    for r in desc.values():
        fam_counts[r.get("family", "")] = fam_counts.get(r.get("family", ""), 0) + 1
    tag_counts = {}
    for r in mech.values():
        t = r.get("mechanism_tags", "")
        if t and t != "NONE":
            for tag in t.split(";"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    cands = []

    # ---- A. LiquidBenchmark compounds outside CORE239 -------------------
    seen = set()
    for r in load_csv(LB):
        smi = (r.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            continue
        try:
            ik = Chem.MolToInchiKey(mol)
        except Exception:
            continue
        if ik in core_iks or ik in seen:
            continue
        seen.add(ik)
        eps = fnum(r.get("Relative permittivity at zero frequency"))
        T = fnum(r.get("Temperature, K"))
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        sub = classify(mol)
        cands.append({
            "inchikey": ik,
            "smiles": smi,
            "name": r.get("components", ""),
            "source_dataset": "LiquidBenchmark",
            "epsilon": eps if eps is not None else "",
            "temperature_K": T if T is not None else "",
            "property_definition": "Relative permittivity at zero frequency",
            "has_per_row_primary_reference": "false",
            "ether_subtype": sub or "",
            "hbd": hbd, "hba": hba,
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "cohort_if_admitted": "NEW_MOLECULE_EXPLORATORY",
        })

    # ---- B. CRAFT reference liquids outside CORE239 ---------------------
    ref = json.loads(CRAFT_REF.read_text(encoding="utf-8"))
    for smi, meta in ref.items():
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        try:
            ik = Chem.MolToInchiKey(mol)
        except Exception:
            continue
        if ik in core_iks or ik in seen:
            continue
        seen.add(ik)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        cands.append({
            "inchikey": ik,
            "smiles": smi,
            "name": meta["name"],
            "source_dataset": "CRAFT_epsilon_reference",
            "epsilon": round(meta["epsilon_paper"], 4),
            "temperature_K": 298.15,
            "property_definition": "author's stored epsilon (static, 298.15 K)",
            "has_per_row_primary_reference": "false",
            "ether_subtype": classify(mol) or "",
            "hbd": hbd, "hba": hba,
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "cohort_if_admitted": "NEW_MOLECULE_EXPLORATORY",
        })

    # ---- score each candidate against the declared gaps ------------------
    for c in cands:
        reasons, gap_hits = [], []
        # G1 chlorinated ether
        if c["ether_subtype"] == "chlorinated_ether":
            reasons.append("fills chlorinated_ether gap (CORE239 n=2)")
            gap_hits.append("G1_chlorinated_ether")
        # G2 association
        if c["hbd"] + c["hba"] >= 2:
            reasons.append("association-heavy (hbd+hba>=2)")
            gap_hits.append("G2_association")
        # G4 low polarity high eps
        eps = fnum(c["epsilon"])
        if eps is not None and eps >= 20 and c["hbd"] == 0 and c["hba"] == 0:
            reasons.append("high epsilon with no H-bond capacity")
            gap_hits.append("G3_low_polarity_high_eps")
        # G5 nitrile-like (C≡N present, no HBD)
        if c["smiles"] and "#N" in c["smiles"] and c["hbd"] == 0:
            reasons.append("nitrile family (CORE239 n=7)")
            gap_hits.append("G5_nitrile")
        # simple molecules give a clean structural contrast
        if c["heavy_atoms"] <= 6:
            reasons.append("small molecule: clean structural contrast")
            gap_hits.append("G6_small_contrast")
        c["gap_hits"] = ";".join(gap_hits) if gap_hits else "NONE"
        c["n_gaps_addressed"] = len(gap_hits)
        c["rationale"] = "; ".join(reasons) if reasons else "no declared gap addressed"
        # admissibility: what is MISSING decides the cohort
        c["missing_for_validated"] = ";".join([
            "per-molecule primary reference (DOI)",
            "measurement frequency",
        ])

    # Domain filter: CRAFT itself excludes molecules with fewer than two carbons,
    # and this project's descriptor set is built for organic solvents. Water and
    # similar tiny inorganics are therefore flagged rather than ranked as priority
    # targets, otherwise the list is dominated by solvents the model never covers.
    for c in cands:
        mol = Chem.MolFromSmiles(c["smiles"])
        nc = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "C") if mol else 0
        c["n_carbons"] = nc
        c["in_model_domain"] = "true" if nc >= 2 else "false"
        if nc < 2:
            c["cohort_if_admitted"] = "OUT_OF_DOMAIN"

    cands.sort(key=lambda c: (c["in_model_domain"] != "true",
                              -c["n_gaps_addressed"], c["heavy_atoms"]))

    with (OUT / "expansion_candidates.csv").open("w", newline="",
                                                 encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cands[0].keys()))
        w.writeheader()
        w.writerows(cands)

    by_source = {}
    for c in cands:
        by_source.setdefault(c["source_dataset"], []).append(c)
    useful = [c for c in cands if c["n_gaps_addressed"] > 0]

    doc = {
        "schema": "b730.expansion_candidates/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "policy": (
            "the plan permits but does not require expansion; candidates are ranked "
            "by the research gap they would close, not by how much they would raise n"
        ),
        "core239_state": {
            "n_molecules": len(core_iks),
            "family_counts": dict(sorted(fam_counts.items())),
            "mechanism_tag_counts": dict(sorted(tag_counts.items())),
        },
        "candidates": {
            "n_total": len(cands),
            "n_addressing_a_declared_gap": len(useful),
            "by_source": {k: len(v) for k, v in by_source.items()},
            "by_ether_subtype": {
                k: sum(1 for c in cands if c["ether_subtype"] == k)
                for k in ("chlorinated_ether", "aliphatic_ether", "cyclic_ether",
                          "aromatic_ether", "other_or_ambiguous")
            },
            "chlorinated_ethers_found": [c["name"] for c in cands
                                         if c["ether_subtype"] == "chlorinated_ether"],
        },
        "admission_decision": {
            "n_admitted_to_validated": 0,
            "why_zero": (
                "NEW_MOLECULE_VALIDATED requires a per-molecule primary reference with "
                "temperature AND frequency. LiquidBenchmark rows are ThermoML-derived "
                "without per-row DOIs, and the CRAFT reference values are the author's "
                "fitted-table entries, not per-molecule measurements. Admitting either "
                "as validated would repeat the exact error this project criticises."
            ),
            "n_exploratory": len(cands),
            "consequence": (
                "no new molecule enters a confirmatory test set this round. The pool is "
                "available for exploratory analysis and for targeted literature search "
                "in a later round."
            ),
        },
        "recommended_next_batch": [
            {"name": c["name"], "smiles": c["smiles"], "gaps": c["gap_hits"],
             "what_it_would_test": c["rationale"]}
            for c in useful[:12]],
        "what_would_unlock_validated_admission": [
            "resolve the original paper DOI for each LiquidBenchmark row",
            "or hand-collect 5-10 liquids with a stated static epsilon, T and frequency "
            "from a single-lab paper",
        ],
    }
    (OUT / "expansion_rationale.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'expansion_candidates.csv'}")
    print(f"Wrote {OUT / 'expansion_rationale.json'}")
    print()
    print(f"candidates from external: {len(cands)} "
          f"({doc['candidates']['n_addressing_a_declared_gap']} address a gap)")
    print(f"by source: {doc['candidates']['by_source']}")
    print(f"by ether subtype: {doc['candidates']['by_ether_subtype']}")
    print(f"chlorinated ethers found: {doc['candidates']['chlorinated_ethers_found']}")
    print()
    print("admitted to VALIDATED:", doc["admission_decision"]["n_admitted_to_validated"])
    print()
    print("top candidates:")
    for c in cands[:10]:
        print(f"  {c['name'][:34]:34s} {c['source_dataset'][:22]:22s} "
              f"gaps={c['n_gaps_addressed']}  {c['gap_hits']}")


if __name__ == "__main__":
    main()
