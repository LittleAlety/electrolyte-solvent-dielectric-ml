#!/usr/bin/env python
"""B721-01: recover ComBat's solvent table (data.csv) from a pinned commit.

ComBat is a SECONDARY compilation: the site itself says the dielectric column
`De` comes "from public databases & literature", with `DeT` the temperature in
degrees C. That is exactly the provenance shape that makes it dangerous to treat
as an independent experimental source, so what gets recovered and recorded here is:

  * the raw file, byte-identical, with a SHA256
  * the field dictionary from the site (so `De` is not silently read as a
    static-permittivity measurement)
  * a provenance record stating the data are second-hand

Only `data.csv` is pulled: the per-solvent MD artefacts (RDFs, clustering,
solvation structures) are simulation output for different quantities and are not
evidence about experimental dielectric constants.

Licence: MIT (permissive), so the file can be stored with the licence text.

Outputs:
  data/external_raw/combat/data.csv
  data/external_raw/combat/LICENSE
  data/external_raw/combat/PROVENANCE.json
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEST = REPO_ROOT / "data" / "external_raw" / "combat"
GEN = "recover_combat/1.0.0"

OWNER_REPO = "rashatwi/combat"
COMMIT = "caa1130df2b4feeb9eaafe1565af8e1a4283986a"
FILES = ["data.csv", "LICENSE", "README.md"]

FIELD_DICTIONARY = {
    "Abbreviation": "short solvent code used in the ComBat figures",
    "Type": "chemical class assigned by ComBat",
    "InChI Key": "InChIKey of the solvent",
    "InChI": "InChI string",
    "CanonicalSMILES": "canonical SMILES",
    "IUPACName": "IUPAC name",
    "CAS": "CAS registry number",
    "CID": "PubChem CID",
    "MolecularFormula": "molecular formula",
    "MolecularWeight": "molecular weight",
    "Density": "density, FROM PUBLIC DATABASES",
    "DN": "donor number, FROM PUBLIC DATABASES & LITERATURE",
    "De": "dielectric constant, FROM PUBLIC DATABASES & LITERATURE (secondary)",
    "DeT": "temperature (degC) at which De was measured, FROM PUBLIC DATABASES & LITERATURE",
    "Viscosity": "viscosity, secondary",
    "Refraction": "refractive index, from ChemSpider",
    "FlashPoint": "flash point degC, secondary",
    "MeltingPoint": "melting point degC, secondary",
    "BoilingPoint": "boiling point degC, secondary",
}


def fetch_via_api(path: str) -> bytes:
    url = (f"https://api.github.com/repos/{OWNER_REPO}/contents/{path}"
           f"?ref={COMMIT}")
    r = subprocess.run(["curl", "-sS", "-m", "120", url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {path}: {r.stderr[:200]!r}")
    payload = json.loads(r.stdout.decode("utf-8"))
    if "content" not in payload:
        raise RuntimeError(f"no content for {path}: {str(payload)[:300]}")
    if payload.get("encoding") != "base64":
        raise RuntimeError(f"unexpected encoding {payload.get('encoding')}")
    return base64.b64decode(payload["content"])


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    records = {}
    for name in FILES:
        data = fetch_via_api(name)
        out = DEST / name
        out.write_bytes(data)
        records[name] = {
            "saved_as": str(out.relative_to(REPO_ROOT)).replace("\\", "/"),
            "bytes": len(data),
            "sha256": sha256_bytes(data),
        }
        print(f"  {name:24s} {len(data):>8d} bytes  {records[name]['sha256'][:16]}")

    prov = {
        "schema": "b720.combat_provenance/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "repository": f"https://github.com/{OWNER_REPO}",
        "website": "https://rashatwi.github.io/combat/",
        "pinned_commit": COMMIT,
        "commit_date": "2023-04-15T00:35:34Z",
        "licence": "MIT",
        "associated_paper": "Atwi & Rajput, Patterns 2023, doi:10.1016/j.patter.2023.100799",
        "provenance_class": "SECONDARY_COMPILATION",
        "provenance_note": (
            "ComBat aggregates solvent properties 'from public databases & literature'. "
            "The `De` column is therefore NOT a primary measurement. It may not be "
            "counted as an independent experimental source, and if its underlying "
            "reference turns out to be NBS 514 or ThermoML it must be merged into that "
            "primary-study cluster rather than treated as new evidence."
        ),
        "property_caveat": (
            "`De` has no frequency field. Treating it as a static relative permittivity "
            "is an ASSUMPTION, not something the file establishes; records without a "
            "recoverable primary reference stay EXPLORATORY."
        ),
        "field_dictionary": FIELD_DICTIONARY,
        "files": records,
        "not_recovered": (
            "per-solvent MD artefacts (radial_distribution_functions/, "
            "polysulfide_clustering/, solvation_structures/, diffusion/, "
            "coordination_numbers/) are simulation output for other quantities and are "
            "not evidence about experimental dielectric constants"
        ),
    }
    (DEST / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {DEST / 'PROVENANCE.json'}")
    print(f"commit {COMMIT[:12]}, licence MIT, provenance=SECONDARY_COMPILATION")


if __name__ == "__main__":
    main()
