"""Family-taxonomy audit: are the 17 'amine' molecules actually amines?"""
import json
import sys
from pathlib import Path

import pandas as pd
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")
ROOT = Path(r"E:\Claude Code\电解质ML\电解质ML")
m = pd.read_csv(ROOT / "outputs" / "b100" / "model_matrix_b100.csv")

NITRO = Chem.MolFromSmarts("[N+](=O)[O-]")
NITRATE = Chem.MolFromSmarts("[OX2][N+](=O)[O-]")
AMINE = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O);!$(N=O);!$(N+)]")


def has(smi, patt):
    mo = Chem.MolFromSmiles(smi)
    return bool(mo is not None and patt is not None and mo.HasSubstructMatch(patt))


am = m[m.family == "amine"].copy()
am["is_nitro"] = [has(s, NITRO) for s in am.smiles]
am["is_nitrate"] = [has(s, NITRATE) for s in am.smiles]
am["is_true_amine"] = [has(s, AMINE) for s in am.smiles]
print(am[["name", "epsilon", "is_nitro", "is_nitrate", "is_true_amine"]].to_string())
out = {
    "n_amine_family": int(len(am)),
    "n_nitro": int(am.is_nitro.sum()),
    "n_nitrate": int(am.is_nitrate.sum()),
    "n_true_amine": int(am.is_true_amine.sum()),
    "n_neither_nitro_nor_amine": int((~am.is_nitro & ~am.is_true_amine).sum()),
    "eps_mean_family": round(float(am.epsilon.mean()), 2),
    "eps_mean_nitro_containing": round(float(am.loc[am.is_nitro].epsilon.mean()), 2),
    "eps_mean_true_amines": round(float(am.loc[am.is_true_amine].epsilon.mean()), 2) if am.is_true_amine.any() else None,
}
print(json.dumps(out, indent=1))

# what are the "other neutral liquids"?
on = m[m.family == "other_neutral_liquid"]
print("\nother_neutral_liquid (n=%d) mean eps %.2f" % (len(on), on.epsilon.mean()))
print(on.sort_values("epsilon")[["name", "epsilon", "n_halogen"]].head(40).to_string())
(ROOT / "outputs" / "b100_review" / "family_taxonomy.json").write_text(
    json.dumps({"amine_family": out,
                "amine_members": am[["name", "epsilon", "is_nitro", "is_nitrate", "is_true_amine"]]
                .to_dict("records")}, indent=2), encoding="utf-8")
print("\nwrote family_taxonomy.json")
