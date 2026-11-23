"""Check whether the amine SMARTS actually compiles and matches inside the builder."""

import sys
from pathlib import Path

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

# exact string as written in the builder
SMARTS_AMINE = "[NX3;H2,H1,H0;!$(NC=O)]"
patt = Chem.MolFromSmarts(SMARTS_AMINE)
print("compile:", "OK" if patt else "FAILED")

tests = {
    "2-aminoethan-1-ol": "NCCO",
    "diethanolamine": "OCCNCCO",
    "triethanolamine": "OCCN(CCO)CCO",
    "pyridine": "c1ccncc1",
    "N,N-dimethylaniline": "CN(C)c1ccccc1",
    "acetamide": "CC(N)=O",
}
for name, smi in tests.items():
    mol = Chem.MolFromSmiles(smi)
    hit = mol.HasSubstructMatch(patt) if (mol and patt) else None
    print(f"  {name:22s} amine_hit={hit}")

# also test the simpler variant to see which one behaves
ALT = Chem.MolFromSmarts("[NX3;H2,H1,H0]")
if ALT:
    for name, smi in tests.items():
        mol = Chem.MolFromSmiles(smi)
        print(f"  ALT {name:18s} any_NX3={mol.HasSubstructMatch(ALT) if mol else None}")
