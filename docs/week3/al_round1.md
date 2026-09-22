# AL Round-1 Runbook

## Purpose

`probes/al_round1.py` builds a reviewable first-round active-learning shortlist
from the pinned Batt-SLM pool. It uses the existing dielectric v0.1 model only
as a ranking signal. It does not perform an AL training round or claim that any
candidate is experimentally usable.

## Rebuild inputs

- `data/external/Batt-SLM.smi`, pinned at commit
  `a5101e30c6975552d97e34f1e93461126715c862`.
- `data/external/SolvFunc-87.csv` from the same commit.
- `data/dielectric_v01.csv` as the 100-key reference set and GPR training set.

The source files and dielectric input are checked against recorded canonical
hashes before scoring.

## Selection procedure

1. Parse and canonicalize Batt-SLM SMILES with RDKit and derive InChIKeys.
2. Deduplicate the 115,756 parsed records.
3. Remove keys present in dielectric v0.1 and apply the versioned
   `al_round1_hazard_v4` SMARTS exclusions. The v4 rules add halogen-oxygen
   hard exclusions and extend the thiocarbonyl flag with the complete
   `[#6]=[#16]` carbon-sulfur motif while retaining the ordinary `C=S` rule.
4. Predict dielectric and posterior standard deviation with the frozen
   Morgan count/StandardScaler/GPR model in 4096-row batches.
5. Compute binary Morgan Tanimoto novelty relative to the 100 v0.1 compounds.
6. Find the nearest SolvFunc-87 neighbor and assign Tier A, B, or C.
7. Rank by `std_percentile * novelty`, retain a 300-row Tier A/B longlist, and
   apply deterministic MaxMin diversity with a hard family quota of 6 and seed
   42. If the A/B pass falls short, continue from the top six
   acquisition-ranked Tier C rows per family. The family quota remains hard in
   both phases; there is no all-remaining fallback.

Non-hard polyhalogenated alkyl structures receive
`manual_review_warnings=polyhalogenated_alkyl`. Warnings do not remove a
candidate; only a matching hard hazard rule can exclude a molecule.

The longlist and Top 30 retain the selection fields needed for independent
recomputation. The full hazard rule map, source hashes, model configuration, and
aggregate counts are in `probes/al_round1_summary.json`.

## Reproduction

```powershell
.\.venv\Scripts\python.exe probes\al_round1.py
.\.venv\Scripts\python.exe scripts\verify_al_round1.py
```

The builder is deterministic for the pinned inputs. The verifier independently
checks source hashes, the 16-flag hazard contract, filtering counts, model input
hash, predictions, similarities, family quota, and selection fields.
For the Top 30 it compares every exported field, including hazard flags,
availability and decision status, selection order and step score, source
commit, `model_input_sha256`, acquisition score, and predicted value.

## Interpretation boundary

This is an exploration table, not a training table or an experimental
recommendation. The model has a weak held-out dielectric R2 of `0.2312574`.
Candidates remain `availability_status=unknown` and
`decision_status=awaiting_manual_review`. Melting point, boiling point, and DOI
fields are empty until a human review adds traceable evidence.

The unavailable 308-solvent ECW target is not represented as a candidate pool
or treated as observed data.

## Outputs

- `data/processed/al_round1_longlist.csv`
- `data/round1_candidates.csv`
- `probes/al_round1_summary.json`
- `probes/artifacts/al_round1_selection.png`
- `reports/al_round1.md`
