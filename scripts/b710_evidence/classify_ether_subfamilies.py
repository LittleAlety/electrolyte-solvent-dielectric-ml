#!/usr/bin/env python
"""B710-03: build an AUXILIARY ether subtype classification with RDKit.

Hard constraint: the official `family` column is NOT modified. The subtype lives in
new columns (`family_subtype_v1`, `family_subtype_rule_version`,
`family_subtype_review_status`) and is only used for exploratory comparison.

Rules are structural, recomputable from SMILES, and do not look at names:

  chlorinated_ether  has an ether C-O-C AND >=1 covalent C-Cl
  aliphatic_ether    has an aliphatic (non-aromatic) C-O-C, no C-Cl, no aryl ether
  other_or_ambiguous everything else (aryl ether, mixed, unclassifiable)

Priority is chlorinated first, per the plan: a molecule that is both chlorinated
and etheric must not be split across subtypes to balance the groups.
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
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "ether_subfamilies"
GEN = "classify_ether_subfamilies/1.0.0"
RULE_VERSION = "ether_subtype_v1.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"


def load_csv(path: Path) -> list[dict]:
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
    """Return (subtype, evidence). Pure structural rules, no name matching."""
    from rdkit import Chem

    ether_pat = Chem.MolFromSmarts("[#6]-[#8]-[#6]")
    aryl_ether_pat = Chem.MolFromSmarts("[c]-[#8]-[#6]")
    aliph_ether_pat = Chem.MolFromSmarts("[CX4]-[#8]-[CX4]")

    has_ether = mol.HasSubstructMatch(ether_pat)
    has_aryl_ether = mol.HasSubstructMatch(aryl_ether_pat)
    has_aliph_ether = mol.HasSubstructMatch(aliph_ether_pat)

    n_cl = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
    n_br = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Br")
    n_i = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "I")
    n_f = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "F")
    n_ring = mol.GetRingInfo().NumRings()
    n_arom = sum(1 for a in mol.GetAtoms() if a.GetIsAromatic())

    # chlorinated takes priority
    if has_ether and n_cl >= 1:
        sub = "chlorinated_ether"
    elif has_ether and has_aliph_ether and not has_aryl_ether and n_cl == 0:
        sub = "aliphatic_ether"
    else:
        sub = "other_or_ambiguous"

    return sub, {
        "has_ether_C_O_C": has_ether,
        "has_aryl_ether": has_aryl_ether,
        "has_aliphatic_ether": has_aliph_ether,
        "n_Cl": n_cl, "n_Br": n_br, "n_I": n_i, "n_F": n_f,
        "n_rings": n_ring, "n_aromatic_atoms": n_arom,
    }


def main() -> None:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)
    lofo = {r["inchikey"]: r for r in load_csv(LOFO)} if LOFO.exists() else {}

    ether = [r for r in rows if (r.get("family") or "") == "ether"]
    records = []
    unparsed = []
    for r in ether:
        smi = (r.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            unparsed.append({"inchikey": r["inchikey"], "name": r.get("name", ""),
                             "smiles": smi, "reason": "RDKit parse failed"})
            continue
        sub, ev = classify(mol)
        lr = lofo.get(r["inchikey"], {})
        records.append({
            "inchikey": r["inchikey"],
            "name": r.get("name", ""),
            "smiles": smi,
            "family": "ether",                       # unchanged
            "family_subtype_v1": sub,
            "family_subtype_rule_version": RULE_VERSION,
            "family_subtype_review_status": "AUTO_CLASSIFIED_PENDING_MANUAL_SPOT_CHECK",
            "epsilon": r.get("epsilon", ""),
            "lofo_pred": lr.get("lofo_pred", ""),
            "lofo_resid": lr.get("resid", ""),
            **{f"rule_{k}": (str(v).lower() if isinstance(v, bool) else v)
               for k, v in ev.items()},
        })

    # CSV
    csv_path = OUT / "ether_subtype_table.csv"
    if records:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)

    counts = Counter(r["family_subtype_v1"] for r in records)

    # Descriptive stats per subtype (no inferential claim when n is small)
    desc = {}
    for sub in ("chlorinated_ether", "aliphatic_ether", "other_or_ambiguous"):
        sub_rows = [r for r in records if r["family_subtype_v1"] == sub]
        eps = [fnum(r["epsilon"]) for r in sub_rows]
        eps = [v for v in eps if v is not None]
        resid = [fnum(r["lofo_resid"]) for r in sub_rows]
        resid = [v for v in resid if v is not None]
        desc[sub] = {
            "n": len(sub_rows),
            "molecules": [r["name"] for r in sub_rows],
            "epsilon_min": round(min(eps), 3) if eps else None,
            "epsilon_max": round(max(eps), 3) if eps else None,
            "epsilon_median": round(sorted(eps)[len(eps) // 2], 3) if eps else None,
            "mean_abs_lofo_resid": round(sum(abs(v) for v in resid) / len(resid), 4) if resid else None,
            "n_for_inference_sufficient": len(sub_rows) >= 5,
        }

    doc = {
        "schema": "b710.ether_subtype/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "rule_version": RULE_VERSION,
        "original_family_column_modified": False,
        "official_family_still": "ether",
        "classification_rules": {
            "chlorinated_ether": "has C-O-C AND >=1 covalent C-Cl (checked FIRST, priority)",
            "aliphatic_ether": "has CX4-O-CX4, no aryl ether, no Cl",
            "other_or_ambiguous": "aryl ether, mixed, or unclassifiable",
            "name_matching_used": False,
        },
        "n_ether_total": len(ether),
        "n_classified": len(records),
        "n_unparsed": len(unparsed),
        "unparsed": unparsed,
        "counts": dict(counts),
        "per_subtype": desc,
        "sample_size_warning": (
            "Subtypes with n<5 support descriptive statistics only. A high Spearman rho "
            "on such a group must not be read as evidence the heterogeneity problem is solved."
        ),
    }
    (OUT / "ether_subtype_manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {OUT / 'ether_subtype_manifest.json'}")
    print(f"ether members: {len(ether)}, classified: {len(records)}, unparsed: {len(unparsed)}")
    print(f"counts: {dict(counts)}")
    print()
    for sub, d in desc.items():
        print(f"{sub:20s} n={d['n']:2d} eps {d['epsilon_min']}-{d['epsilon_max']} "
              f"(median {d['epsilon_median']}) mean|resid|={d['mean_abs_lofo_resid']}")
        if d["n"] < 5:
            print(f"{'':20s}   (n<5: descriptive only)")


if __name__ == "__main__":
    main()
