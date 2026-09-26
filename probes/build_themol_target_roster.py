"""Write the THEMol harvest target rosters from committed tables (W17-14).

The harvest in ``probes/themol_hessian_orbitals.py`` needs a roster CSV with
``name`` / ``inchikey`` / ``smiles`` columns.  Two of them are assembled here
rather than hand-written, so the target list is auditable:

``themol_anchor_roster.csv``
    The 111 W17-12 ``paired_anchor`` molecules -- those that carry both a
    PubChemQC value and a Batt-P30K value.  THEMol covers 72 of them, and those
    72 are the only molecules where a GFN2-xTB number can be calibrated
    against the authoritative wB97X-V level.

``themol_target_roster.csv``
    The flagship epsilon roster (``data/dielectric_v04.csv``) unioned with the
    anchor roster, de-duplicated on canonical SMILES.  This is the list the
    sharded harvest workers consume.

Both files land under ``data/raw/themol/``: they are regenerable, and the
harvest itself is licence-encumbered evidence, not delivery data.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

LAYER_PATH = REPOSITORY_ROOT / "data" / "processed" / "orbital_second_source_layer.csv"
REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
EPSILON_ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v04.csv"
OUTPUT_DIR = REPOSITORY_ROOT / "data" / "raw" / "themol"

ANCHOR_FIELDS = ("name", "inchikey", "smiles", "batt_homo_eV", "batt_lumo_eV", "role")
TARGET_FIELDS = ("name", "inchikey", "smiles", "roster_value", "roster_source")


def canonical(value: str | None) -> str | None:
    if not value:
        return None
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(value)
    return Chem.MolToSmiles(molecule) if molecule is not None else None


def build_anchor_roster() -> list[dict[str, Any]]:
    registry: dict[str, dict[str, str]] = {}
    with REGISTRY_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            registry.setdefault(row["inchikey"], row)

    rows: list[dict[str, Any]] = []
    with LAYER_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("role") != "paired_anchor":
                continue
            source = registry.get(row["inchikey"])
            if source is None:
                continue
            rows.append(
                {
                    "name": row.get("record_name") or source.get("name") or "",
                    "inchikey": row["inchikey"],
                    "smiles": source["smiles"],
                    "batt_homo_eV": row.get("batt_homo_eV") or "",
                    "batt_lumo_eV": row.get("batt_lumo_eV") or "",
                    "role": "paired_anchor",
                }
            )
    rows.sort(key=lambda item: item["inchikey"])
    return rows


def build_target_roster(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    with EPSILON_ROSTER_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = canonical(row.get("smiles"))
            if key is None or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "name": row.get("name") or "",
                    "inchikey": row.get("inchikey") or "",
                    "smiles": row.get("smiles") or "",
                    "roster_value": row.get("dielectric") or "",
                    "roster_source": EPSILON_ROSTER_PATH.name,
                }
            )
    for anchor in anchors:
        key = canonical(anchor["smiles"])
        if key is None or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "name": anchor["name"],
                "inchikey": anchor["inchikey"],
                "smiles": anchor["smiles"],
                "roster_value": anchor["batt_homo_eV"],
                "roster_source": "themol_anchor_roster.csv",
            }
        )
    return rows


def write_rows(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    anchors = build_anchor_roster()
    targets = build_target_roster(anchors)
    write_rows(args.output_dir / "themol_anchor_roster.csv", ANCHOR_FIELDS, anchors)
    write_rows(args.output_dir / "themol_target_roster.csv", TARGET_FIELDS, targets)
    print(f"anchor roster rows = {len(anchors)}")
    print(f"target roster rows = {len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())