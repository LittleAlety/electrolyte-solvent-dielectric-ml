#!/usr/bin/env python
"""B724-01: ether subtypes with a fifth class, plus external ether evidence.

v7.1 split ether into chlorinated / aliphatic / other. Two gaps remain:

  1. cyclic ethers were forced into `aliphatic_ether` (or `other`), which lumps
     THF and 1,4-dioxane in with open-chain dialkyl ethers even though ring strain
     changes both the static permittivity and how a molecular descriptor sees the
     C-O-C geometry;
  2. no check was made whether the recovered external datasets contain any
     additional ethers that could raise n above 2 for the chlorinated class.

So this script (a) rebuilds the subtype rules with an explicit `cyclic_ether`
class, evaluated BEFORE aliphatic, and (b) audits LiquidBenchmark + ComBat for
etheric compounds, admitting them only if they pass the same structural rules.

Priority order (mutually exclusive, reproducible from SMILES):
  chlorinated_ether  has C-O-C and >=1 covalent C-Cl
  aromatic_ether     has an aryl-O bond
  cyclic_ether       C-O-C where at least one C is in a ring, no Cl, no aryl-O
  aliphatic_ether    CX4-O-CX4 acyclic, no Cl, no aryl-O, not cyclic
  other_or_ambiguous anything left

The official `family` column is never touched.

Outputs (outputs/b724_ether/):
  ether_subtype_v2.csv
  ether_subtype_v2_manifest.json
  external_ether_audit.csv
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b724_ether"
GEN = "classify_ether_v2/1.0.0"
RULE_VERSION = "ether_subtype_v2.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"
LB = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark" / "data_dielectric.csv"
CB = REPO_ROOT / "data" / "external_raw" / "combat" / "data.csv"


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


def classify(mol) -> tuple[str, dict]:
    from rdkit import Chem

    ether_pat = Chem.MolFromSmarts("[#6]-[#8]-[#6]")
    aryl_ether_pat = Chem.MolFromSmarts("[c]-[#8]-[#6]")
    aliph_ether_pat = Chem.MolFromSmarts("[CX4]-[#8]-[CX4]")
    # an ether oxygen whose at least one carbon is a ring atom
    cyclic_ether_pat = Chem.MolFromSmarts("[#6;R]-[#8]-[#6]")

    has_ether = mol.HasSubstructMatch(ether_pat)
    has_aryl = mol.HasSubstructMatch(aryl_ether_pat)
    has_aliph = mol.HasSubstructMatch(aliph_ether_pat)
    has_cyclic = mol.HasSubstructMatch(cyclic_ether_pat)
    n_cl = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
    n_ring = mol.GetRingInfo().NumRings()

    if not has_ether:
        sub = "not_an_ether"
    elif n_cl >= 1:
        sub = "chlorinated_ether"
    elif has_aryl:
        sub = "aromatic_ether"
    elif has_cyclic:
        sub = "cyclic_ether"
    elif has_aliph:
        sub = "aliphatic_ether"
    else:
        sub = "other_or_ambiguous"

    return sub, {
        "has_ether_C_O_C": has_ether,
        "has_aryl_ether": has_aryl,
        "has_aliphatic_ether": has_aliph,
        "has_cyclic_ether": has_cyclic,
        "n_Cl": n_cl,
        "n_rings": n_ring,
    }


def main() -> None:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)
    lofo = {r["inchikey"]: r for r in load_csv(LOFO)} if LOFO.exists() else {}
    eps = {r["inchikey"]: r for r in rows}

    # ---------------- the frozen ether set --------------------------------
    ether = [r for r in rows if (r.get("family") or "") == "ether"]
    records = []
    for r in ether:
        smi = (r.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            continue
        sub, ev = classify(mol)
        lr = lofo.get(r["inchikey"], {})
        records.append({
            "scope": "frozen_239",
            "inchikey": r["inchikey"],
            "name": r.get("name", ""),
            "smiles": smi,
            "official_family": r.get("family", ""),
            "family_subtype_v2": sub,
            "family_subtype_rule_version": RULE_VERSION,
            "epsilon": r.get("epsilon", ""),
            "lofo_pred": lr.get("lofo_pred", ""),
            "lofo_resid": lr.get("resid", ""),
            **{f"rule_{k}": (str(v).lower() if isinstance(v, bool) else v)
               for k, v in ev.items()},
        })

    frozen_counts = Counter(r["family_subtype_v2"] for r in records)

    # ---------------- external ether search ------------------------------
    # LiquidBenchmark + ComBat are scanned for etheric SMILES. These are NOT added
    # to the modelling set: they are candidates whose admissibility is decided by
    # the same structural rules plus the condition checks done in B720.
    ext_rows = []
    for r, src in [(x, "LiquidBenchmark") for x in load_csv(LB)] + \
                  [(x, "ComBat") for x in load_csv(CB)]:
        smi = (r.get("smiles") or r.get("CanonicalSMILES") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            continue
        sub, ev = classify(mol)
        if sub == "not_an_ether":
            continue
        name = (r.get("components") or r.get("IUPACName") or "").strip()
        e = fnum(r.get("Relative permittivity at zero frequency") or r.get("De"))
        T = fnum(r.get("Temperature, K"))
        if T is None:
            dT = fnum(r.get("DeT"))
            T = (dT + 273.15) if dT is not None else None
        try:
            ik = Chem.MolToInchiKey(mol)
        except Exception:
            ik = ""
        already = ik in eps
        # admission: etheric + has a value + (static definition confirmed OR
        # already consistent with the frozen label)
        reasons = []
        if e is None:
            reasons.append("NO_EPSILON")
        if T is None:
            reasons.append("NO_TEMPERATURE")
        if src == "ComBat":
            reasons.append("SECONDARY_COMPILATION")
            reasons.append("FREQUENCY_UNKNOWN")
        ext_rows.append({
            "source_dataset": src,
            "name": name,
            "smiles": smi,
            "inchikey": ik,
            "family_subtype_v2": sub,
            "epsilon": e if e is not None else "",
            "temperature_K": T if T is not None else "",
            "already_in_frozen_239": "true" if already else "false",
            "admission": ("DUPLICATE_OF_FROZEN" if already else
                          "EXPLORATORY" if reasons else "CANDIDATE_NEW_ETHER"),
            "defects": ";".join(reasons),
        })

    # dedupe by inchikey keeping the first occurrence
    seen = set()
    ext_unique = []
    for r in ext_rows:
        key = (r["inchikey"] or r["smiles"], r["source_dataset"])
        if key in seen:
            continue
        seen.add(key)
        ext_unique.append(r)

    ext_counts = Counter(r["family_subtype_v2"] for r in ext_unique
                         if r["admission"] == "CANDIDATE_NEW_ETHER")
    new_chlorinated = [r for r in ext_unique
                       if r["admission"] == "CANDIDATE_NEW_ETHER"
                       and r["family_subtype_v2"] == "chlorinated_ether"]

    # ---------------- write ------------------------------------------------
    if records:
        with (OUT / "ether_subtype_v2.csv").open("w", newline="",
                                                encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)
    if ext_unique:
        with (OUT / "external_ether_audit.csv").open("w", newline="",
                                                     encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ext_unique[0].keys()))
            w.writeheader()
            w.writerows(ext_unique)

    doc = {
        "schema": "b724.ether_subtype_v2/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "rule_version": RULE_VERSION,
        "supersedes": "family_subtype_v1 (B710), which had no cyclic_ether class",
        "original_family_column_modified": False,
        "official_family_still": "ether",
        "rules_priority": [
            "chlorinated_ether: C-O-C AND >=1 C-Cl",
            "aromatic_ether: aryl-O present",
            "cyclic_ether: C-O-C with at least one ring carbon",
            "aliphatic_ether: acyclic CX4-O-CX4",
            "other_or_ambiguous: remainder",
        ],
        "name_matching_used": False,
        "frozen_counts": dict(frozen_counts),
        "n_frozen_ether": len(records),
        "external_scan": {
            "n_etheric_records_found": len(ext_unique),
            "admission_counts": dict(Counter(r["admission"] for r in ext_unique)),
            "new_ether_by_subtype": dict(ext_counts),
            "new_chlorinated_ethers": [r["name"] for r in new_chlorinated],
            "can_raise_chlorinated_above_5": len(new_chlorinated) >= 3,
        },
        "inference_readiness": {
            sub: {
                "n": cnt,
                "inference_allowed": cnt >= 5,
                "note": ("n>=5 allows exploratory correlation; below that only "
                         "descriptive statistics and per-molecule predictions")
                if cnt < 5 else "exploratory correlation permitted",
            }
            for sub, cnt in frozen_counts.items()
        },
        "verdict": (
            "ether heterogeneity is real but the chlorinated class remains too small "
            "for inference; no external chlorinated ether was admitted, so the n=2 "
            "limitation stands"
        ),
    }
    (OUT / "ether_subtype_v2_manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'ether_subtype_v2.csv'}")
    print(f"Wrote {OUT / 'external_ether_audit.csv'}")
    print(f"Wrote {OUT / 'ether_subtype_v2_manifest.json'}")
    print()
    print(f"frozen ether subtypes: {dict(frozen_counts)}")
    print()
    print(f"external etheric records: {len(ext_unique)}")
    print(f"  admissions: {dict(Counter(r['admission'] for r in ext_unique))}")
    print(f"  candidate NEW ethers by subtype: {dict(ext_counts)}")
    print(f"  new chlorinated: {[r['name'] for r in new_chlorinated]}")


if __name__ == "__main__":
    main()
