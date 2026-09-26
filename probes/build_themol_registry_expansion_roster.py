"""Build the frozen target roster for the THEMol registry-wide orbital expansion (W17-17).

W17-14 harvested 166 molecules (the eps roster plus the PubChemQC calibration
anchors).  Its verdict was negative, but its *coverage* claim was the useful
part: the join between `data/processed/four_core_key_registry.csv` and the
THEMol Hessian pool is 5,117 molecules, and only 166 of them had ever been
turned into GFN2-xTB orbital numbers.  This builder freezes the exact 5,117-row
target list, in priority tiers, *before* any measurement runs.

Tiers (lower runs first, and the tier is recorded per row):

1. `no_reference_orbital` -- covered by THEMol and carrying **no** orbital
   label in the registry: whatever GFN2 yields here is the only number that
   molecule will ever have (reference-only, but new information).
2. `flagship_dielectric` -- covered and in the 247-key eps roster.
3. `named_core_channel` -- covered and in the viscosity / redox /
   liquid-window rosters.
4. `calibration_bulk` -- covered and Batt-labelled: these are the cross-level
   calibration pairs; the arm's scientific payload is that this count goes from
   74 anchors to a few thousand.

The roster is a *plan*, not a measurement: `queries_executed = 0`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
INDEX_PATH = REPOSITORY_ROOT / "data" / "raw" / "themol" / "themol_registry_index.csv"
DIELECTRIC_PATH = REPOSITORY_ROOT / "data" / "dielectric_v04.csv"
ROSTER_OUT = REPOSITORY_ROOT / "probes" / "themol_registry_expansion_roster.csv"
SUMMARY_OUT = REPOSITORY_ROOT / "probes" / "themol_registry_expansion_roster_summary.json"

ROSTER_FIELDS = (
    "expansion_order",
    "expansion_tier",
    "inchikey",
    "name",
    "smiles",
    "has_orbitals",
    "homo_eV_reference",
    "lumo_eV_reference",
    "has_dielectric",
    "has_viscosity",
    "has_redox_label",
    "has_liquid_window",
    "has_density",
    "themol_uuid",
    "themol_h5_file",
)

TIER_ORDER = (
    "no_reference_orbital",
    "flagship_dielectric",
    "named_core_channel",
    "calibration_bulk",
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_smiles(value: str | None) -> str | None:
    if not value:
        return None
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(value)
    if molecule is None:
        return None
    return Chem.MolToSmiles(molecule)


def load_index(path: Path) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["canonical_smiles"]
            index.setdefault(key, (row["uuid"], row["h5_file"]))
    return index


def load_dielectric_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            canonical = canonical_smiles(row.get("smiles"))
            if canonical:
                keys.add(canonical)
    return keys


def classify(row: dict[str, str], dielectric_keys: set[str], canonical: str) -> str:
    if row.get("has_orbitals") != "true":
        return "no_reference_orbital"
    if canonical in dielectric_keys:
        return "flagship_dielectric"
    if any(
        row.get(field) == "true"
        for field in ("has_viscosity", "has_redox_label", "has_liquid_window")
    ):
        return "named_core_channel"
    return "calibration_bulk"


def build() -> tuple[list[dict[str, str]], dict[str, object]]:
    index = load_index(INDEX_PATH)
    dielectric_keys = load_dielectric_keys(DIELECTRIC_PATH)
    rows: list[dict[str, str]] = []
    counters = {
        "registry_rows": 0,
        "unparsable_smiles": 0,
        "not_in_themol": 0,
        "duplicate_canonical": 0,
        "matched": 0,
    }
    seen: set[str] = set()
    with REGISTRY_PATH.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            counters["registry_rows"] += 1
            canonical = canonical_smiles(raw.get("smiles"))
            if canonical is None:
                counters["unparsable_smiles"] += 1
                continue
            hit = index.get(canonical)
            if hit is None:
                counters["not_in_themol"] += 1
                continue
            if canonical in seen:
                counters["duplicate_canonical"] += 1
                continue
            seen.add(canonical)
            counters["matched"] += 1
            rows.append(
                {
                    "expansion_tier": classify(raw, dielectric_keys, canonical),
                    "inchikey": raw.get("inchikey", ""),
                    "name": raw.get("name", ""),
                    "smiles": raw.get("smiles", ""),
                    "has_orbitals": raw.get("has_orbitals", ""),
                    "homo_eV_reference": raw.get("HOMO_eV", ""),
                    "lumo_eV_reference": raw.get("LUMO_eV", ""),
                    "has_dielectric": raw.get("has_dielectric", ""),
                    "has_viscosity": raw.get("has_viscosity", ""),
                    "has_redox_label": raw.get("has_redox_label", ""),
                    "has_liquid_window": raw.get("has_liquid_window", ""),
                    "has_density": raw.get("has_density", ""),
                    "themol_uuid": hit[0],
                    "themol_h5_file": hit[1],
                }
            )
    rank = {tier: position for position, tier in enumerate(TIER_ORDER)}
    rows.sort(key=lambda row: (rank[row["expansion_tier"]], row["themol_h5_file"], row["inchikey"]))
    for position, row in enumerate(rows, start=1):
        row["expansion_order"] = str(position)
    by_tier = {tier: 0 for tier in TIER_ORDER}
    for row in rows:
        by_tier[row["expansion_tier"]] += 1
    by_channel = {
        field: sum(1 for row in rows if row[field] == "true")
        for field in (
            "has_dielectric",
            "has_viscosity",
            "has_orbitals",
            "has_redox_label",
            "has_liquid_window",
            "has_density",
        )
    }
    summary: dict[str, object] = {
        "arm": "W17-17",
        "is_a_plan_not_a_measurement": True,
        "queries_executed": 0,
        "counters": counters,
        "roster_rows": len(rows),
        "rows_by_tier": by_tier,
        "tier_order": list(TIER_ORDER),
        "rows_by_registry_channel": by_channel,
        "upsert_target_channel": "orbitals",
        "inputs": {
            "registry": {"path": "data/processed/four_core_key_registry.csv", "sha256": sha256_of(REGISTRY_PATH)},
            "themol_index": {"path": "data/raw/themol/themol_registry_index.csv", "sha256": sha256_of(INDEX_PATH)},
            "dielectric_roster": {"path": "data/dielectric_v04.csv", "sha256": sha256_of(DIELECTRIC_PATH)},
        },
        "method": "HTTP Range geometry read from THEMol Hessian shards + one GFN2-xTB single point",
        "level_of_theory": "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas phase, single point on the DFT geometry)",
        "license": "THEMol CC BY-NC 4.0; derived values are non-commercial and stay under data/raw/",
    }
    return rows, summary


def render_roster(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROSTER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_outputs(rows: list[dict[str, str]], summary: dict[str, object]) -> dict[str, str]:
    ROSTER_OUT.write_text(render_roster(rows), encoding="utf-8", newline="")
    summary = dict(summary)
    summary["roster_sha256"] = hashlib.sha256(ROSTER_OUT.read_bytes()).hexdigest()
    SUMMARY_OUT.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"roster": str(ROSTER_OUT), "summary": str(SUMMARY_OUT)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="rebuild in memory and compare bytes")
    args = parser.parse_args(argv)
    rows, summary = build()
    if args.check:
        if render_roster(rows) != ROSTER_OUT.read_text(encoding="utf-8"):
            print("ROSTER MISMATCH")
            return 1
        recorded = json.loads(SUMMARY_OUT.read_text(encoding="utf-8"))
        if recorded.get("roster_sha256") != hashlib.sha256(ROSTER_OUT.read_bytes()).hexdigest():
            print("SUMMARY DIGEST MISMATCH")
            return 1
        print(json.dumps({"status": "ok", "roster_rows": len(rows)}, sort_keys=True))
        return 0
    paths = write_outputs(rows, summary)
    print(
        json.dumps(
            {"counters": summary["counters"], "rows_by_tier": summary["rows_by_tier"], **paths},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
