#!/usr/bin/env python
"""B741-02: resolve 3D-capable structures for molecules outside CORE239.

Why this exists
---------------
v7.4 recovered static permittivity for 67 molecules outside CORE239 plus 145
non-CORE molecules that appear as components of binary dielectric mixtures.
None of them has a SMILES, and without a structure we can neither

  * compute the r2SCAN-3c descriptor layer (B742) for them, nor
  * decide chemically which mixture components are H-bond donors.

The local corpus gives an InChIKey only. So we resolve InChIKey -> SMILES from
PubChem and then PROVE the identity: RDKit is asked to re-derive the InChIKey
from the fetched SMILES, and the molecule is admitted only if the round trip
returns exactly the requested key. A candidate that does not round-trip is a
wrong structure and is rejected, not "fixed".

Outputs (outputs/b740_expansion/molecule_expansion/):
  new_molecule_structures.csv     verified structures + RDKit descriptors
  structure_resolution_summary.json

Raw responses are cached under data/external_raw/pubchem_b740/ with SHA-256 in
PROVENANCE.json so the resolution is reproducible without hitting the network.

BUG-FIX / DESIGN NOTES
  * PubChem returns MULTIPLE CIDs for one InChIKey (e.g. water -> neutral and
    an H+/OH- pair). Taking the first CID blindly would admit an ion for a
    neutral liquid. Every candidate is round-trip tested instead.
  * some records are salts / ionic liquids whose ThermoML InChIKey belongs to a
    multi-component entry; the round trip then fails for the neutral fragment
    and the molecule is honestly reported as UNRESOLVED.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "molecule_expansion"
CACHE = REPO_ROOT / "data" / "external_raw" / "pubchem_b740"
SCAN = REPO_ROOT / "outputs" / "b740_expansion" / "thermoml" / "thermoml_local_scan.csv"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
GEN = "resolve_new_structures/1.0.0"

PUBCHEM_URL = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/{ik}"
               "/property/SMILES,IsomericSMILES,MolecularFormula/JSON")
SLEEP_S = 0.25
UA = "electrolyte-ml/0.0 (research; contact: local)"


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(ik: str) -> tuple[dict | None, str, bytes | None]:
    url = PUBCHEM_URL.format(ik=ik)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            raw = fh.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}", None
    except Exception as exc:                                  # noqa: BLE001
        return None, f"ERROR {type(exc).__name__}", None
    try:
        return json.loads(raw.decode("utf-8")), "OK", raw
    except Exception:                                          # noqa: BLE001
        return None, "JSON_DECODE_FAIL", raw


def main() -> None:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, rdMolDescriptors

    RDLogger.DisableLog("rdApp.*")

    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    core = {r["inchikey"] for r in load_csv(DESC)}
    scan = load_csv(SCAN)
    ledger = {r["inchikey"]: r for r in load_csv(OUT / "cohort_ledger.csv")}

    relevant = {
        r["inchikey"] for r in scan
        if r["inchikey"] and r["property"] in
        ("dielectric_constant_static", "density", "refractive_index")
    }
    targets = sorted(relevant - core)
    print(f"CORE239: {len(core)}  candidates to resolve: {len(targets)}", flush=True)

    prov = {}
    out_rows = []
    unresolved = []
    for i, ik in enumerate(targets, 1):
        cache_path = CACHE / f"{ik}.json"
        status = "CACHED"
        raw = None
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                payload, status, raw = *fetch(ik), None
                if payload is not None and raw is not None:
                    cache_path.write_bytes(raw)
                    prov[f"{ik}.json"] = {"sha256": sha256_bytes(raw),
                                          "url": PUBCHEM_URL.format(ik=ik)}
        else:
            payload, status, raw = fetch(ik)
            if payload is not None and raw is not None:
                cache_path.write_bytes(raw)
                prov[f"{ik}.json"] = {"sha256": sha256_bytes(raw),
                                      "url": PUBCHEM_URL.format(ik=ik)}
            time.sleep(SLEEP_S)

        cands = ((payload or {}).get("PropertyTable", {}) or {}).get("Properties", []) or []

        chosen = None
        n_tried = 0
        for cand in cands:
            for key in ("IsomericSMILES", "SMILES"):
                smi = (cand.get(key) or "").strip()
                if not smi:
                    continue
                n_tried += 1
                mol = Chem.MolFromSmiles(smi)
                if mol is None:
                    continue
                derived = Chem.MolToInchiKey(mol)
                if derived == ik:
                    chosen = (cand, smi, mol)
                    break
            if chosen:
                break

        if chosen is None:
            unresolved.append({
                "inchikey": ik,
                "name": ledger.get(ik, {}).get("name", ""),
                "reason": ("no candidate SMILES round-trips to the requested "
                           "InChIKey" if cands else status),
                "n_candidates": len(cands),
                "n_smiles_tried": n_tried,
            })
            continue

        cand, smi, mol = chosen
        row = {
            "inchikey": ik,
            "name": ledger.get(ik, {}).get("name", ""),
            "cohort": ledger.get(ik, {}).get("cohort", "MIXTURE_COMPONENT_ONLY"),
            "in_core239": "false",
            "pubchem_cid": cand.get("CID", ""),
            "smiles": smi,
            "smiles_canonical": Chem.MolToSmiles(mol),
            "formula_pubchem": cand.get("MolecularFormula", ""),
            "formula_rdkit": rdMolDescriptors.CalcMolFormula(mol),
            "inchikey_roundtrip": Chem.MolToInchiKey(mol),
            "identity_verified": "true",
            "n_candidates": len(cands),
            "mw": round(Descriptors.MolWt(mol), 3),
            "heavy_atom_count": mol.GetNumHeavyAtoms(),
            "hbd": rdMolDescriptors.CalcNumHBD(mol),
            "hba": rdMolDescriptors.CalcNumHBA(mol),
            "tpsa_A2": round(rdMolDescriptors.CalcTPSA(mol), 3),
            "n_rings": rdMolDescriptors.CalcNumRings(mol),
            "n_rotatable": rdMolDescriptors.CalcNumRotatableBonds(mol),
            "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 4),
            "n_aromatic_atoms": sum(1 for a in mol.GetAtoms() if a.GetIsAromatic()),
            "n_hetero": sum(1 for a in mol.GetAtoms() if a.GetSymbol() not in ("C", "H")),
            "n_halogen": sum(1 for a in mol.GetAtoms()
                             if a.GetSymbol() in ("F", "Cl", "Br", "I")),
            "formal_charge": Chem.GetFormalCharge(mol),
        }
        out_rows.append(row)
        if i % 20 == 0:
            print(f"  {i}/{len(targets)} resolved (kept {len(out_rows)})", flush=True)

    fieldnames = list(out_rows[0].keys()) if out_rows else ["inchikey"]
    out_csv = OUT / "new_molecule_structures.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    (CACHE / "PROVENANCE.json").write_text(json.dumps({
        "schema": "b740.pubchem_resolution/v1",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "PubChem PUG REST",
        "endpoint": "compound/inchikey/<KEY>/property/SMILES,IsomericSMILES,MolecularFormula",
        "terms": "PubChem data are publicly available; no redistribution restrictions imposed here",
        "n_files": len(prov),
        "files": prov,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    n_verified = len(out_rows)
    doc = {
        "schema": "b740.structure_resolution/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "source": "PubChem PUG REST, InChIKey lookup",
        "n_requested": len(targets),
        "n_verified": n_verified,
        "n_unresolved": len(unresolved),
        "identity_rule": ("a structure is admitted only if RDKit re-derives the exact "
                          "requested InChIKey from the fetched SMILES"),
        "why_inchikey_roundtrip": ("PubChem returns several CIDs per InChIKey; the first "
                                   "CID is not necessarily the neutral liquid, so every "
                                   "candidate SMILES is tested instead of trusted"),
        "cohort_breakdown": {
            c: sum(1 for r in out_rows if r["cohort"] == c)
            for c in sorted({r["cohort"] for r in out_rows})
        },
        "unresolved": unresolved,
        "note": ("unresolved molecules are NOT silently dropped from the property tables; "
                 "they simply have no structure and therefore no computed descriptor"),
    }
    (OUT / "structure_resolution_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nverified {n_verified}/{len(targets)}  unresolved {len(unresolved)}")
    for u in unresolved[:10]:
        print("  UNRESOLVED", u["name"], u["reason"])


if __name__ == "__main__":
    main()
