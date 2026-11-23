"""Diagnose the B100 family assignment: does the ordered rule list lose molecules?"""

import csv
import json
from collections import Counter
from pathlib import Path

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

REPO = Path(r"E:\Claude Code\电解质ML\电解质ML")
REG = REPO / "outputs" / "b100" / "molecule_registry_b100.csv"

AMINE = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O)]")
AMIDE = Chem.MolFromSmarts("[NX3][CX3](=[OX1])")
NITRO = Chem.MolFromSmarts("[NX3](=O)=O")

rows = list(csv.DictReader(REG.open(encoding="utf-8-sig")))

hits = {"amine": [], "amide": [], "nitro": []}
for r in rows:
    smi = r["smiles"]
    mol = Chem.MolFromSmiles(smi) if smi else None
    if mol is None:
        continue
    if mol.HasSubstructMatch(AMIDE):
        hits["amide"].append((r["name"], r["family"]))
    if mol.HasSubstructMatch(AMINE):
        hits["amine"].append((r["name"], r["family"]))
    if mol.HasSubstructMatch(NITRO):
        hits["nitro"].append((r["name"], r["family"]))

print("Structural presence vs assigned family")
print("=" * 62)
for k, v in hits.items():
    assigned = sum(1 for _n, f in v if f == k)
    print(f"{k:8s}: contains group {len(v):3d}, assigned '{k}' {assigned:3d}")
    for name, fam in v[:6]:
        flag = "" if fam == k else "  <-- assigned elsewhere"
        print(f"          {name[:34]:34s} -> {fam}{flag}")
    print()

# Which families absorb the amine/nitro molecules? Ordering decides this.
print("Family distribution:")
for fam, n in Counter(r["family"] for r in rows).most_common():
    print(f"  {fam:24s} {n}")

# Verify no molecule is unclassified while having a valid structure
no_fam = [r for r in rows if r["family"] in
          ("UNCLASSIFIED_NO_SMILES", "UNCLASSIFIED_BAD_SMILES",
           "UNCLASSIFIED_NO_RDKIT")]
print(f"\nStructurally unclassifiable: {len(no_fam)}")
for r in no_fam[:5]:
    print(f"  {r['name'][:40]:40s} smiles={r['smiles'][:30]}")

# Every molecule should have >=1 matched rule because 'other_neutral_liquid' is
# the fallback only when matched_rules is empty.
no_rule = [r for r in rows if not r["matched_rules"]]
print(f"\nWith zero matched rules (fallback): {len(no_rule)}")
