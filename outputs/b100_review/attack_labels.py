"""Label provenance + final numbers used in the review."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"E:\Claude Code\电解质ML\电解质ML")
OUT = ROOT / "outputs" / "b100_review"

lab = pd.read_csv(ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv")
led = pd.read_csv(ROOT / "outputs" / "b100" / "deliverables" / "measurement_ledger_b100.csv")
mm = pd.read_csv(ROOT / "outputs" / "b100" / "model_matrix_b100.csv")
rk = pd.read_csv(ROOT / "outputs" / "b100" / "e6_ranking_b100.csv")

res = {}
# exact provenance: does each label equal some ledger value for that molecule, at the label T?
exact, same_T, interp, no_ledger = 0, 0, [], []
led_by = {k: g for k, g in led.groupby("inchikey")}
for _, r in lab.iterrows():
    g = led_by.get(r.inchikey)
    if g is None:
        no_ledger.append(r.inchikey)
        continue
    hit = g[(np.abs(g.epsilon - r.epsilon) < 1e-6)]
    if len(hit):
        exact += 1
        if (np.abs(hit.T_K - r.T_K) < 1e-6).any():
            same_T += 1
    else:
        interp.append((r.inchikey, r.name, r.epsilon, r.T_K,
                       list(zip(g.T_K.tolist(), g.epsilon.tolist()))))
res["label_provenance"] = {
    "n_labels": int(len(lab)),
    "n_exact_match_in_ledger": exact,
    "n_exact_match_and_T_match": same_T,
    "n_not_matching_any_ledger_value": len(interp),
    "n_no_ledger_rows": len(no_ledger),
    "examples_not_matching": interp[:8],
}
print(json.dumps(res["label_provenance"], indent=1, default=str)[:2500])

# duplicate structures? same name twice?
res["duplicates"] = {
    "n_unique_inchikey": int(mm.inchikey.nunique()),
    "n_rows": int(len(mm)),
    "n_duplicate_names": int(mm.name.duplicated().sum()),
    "dup_names": mm.loc[mm.name.duplicated(keep=False), "name"].tolist()[:10],
}
print("duplicates:", res["duplicates"])

# e6 ranks of the two best molecules
for nm in ["Hydrocyanic acid", "glycerol", "Tetranitromethane"]:
    r = rk[rk.name == nm]
    if len(r):
        print(nm, r[["rank_by_prediction", "y_true", "y_pred"]].to_dict("records"))

# n nitro/nitrate in the model top-10
top10 = rk.sort_values("rank_by_prediction").head(10)
res["top10_picks"] = top10[["rank_by_prediction", "name", "family", "y_true", "y_pred"]].to_dict("records")
print(top10[["name", "family", "y_true", "y_pred"]].to_string())

(OUT / "attack_labels.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
print("wrote attack_labels.json")
