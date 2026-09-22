# AL Round-1 Candidate Selection

## Scope

This round converts the pinned Batt-SLM solvent pool into a transparent
shortlist for human review. It does not establish experimental availability,
room-temperature liquid state, synthetic accessibility, safety, or compatibility
with a battery formulation.

## Inputs and provenance

- Source commit:
  `a5101e30c6975552d97e34f1e93461126715c862`.
- `data/external/Batt-SLM.smi`: 1,879,361 bytes, SHA256
  `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d`.
- `data/external/SolvFunc-87.csv`: SHA256
  `1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493`.
- Dielectric input: `data/dielectric_v01.csv`, canonical text SHA256
  `6f31c5b22a6a85a14954d3103a9ce5498eb4cdb265e55cfc8679adb78e4e5396`.
- The unavailable 308-solvent ECW list was not used as a candidate pool.

## Filtering funnel

| Stage | Rows |
| --- | ---: |
| Parsed Batt-SLM records | 115,756 |
| Invalid SMILES | 0 |
| Unique canonical structures | 115,756 |
| Removed because the InChIKey is in dielectric v0.1 | 27 |
| Removed by hazard substructure rules | 29,808 |
| Safe candidates scored | 85,921 |

The 27 removals are the number of v0.1 keys actually present in Batt-SLM, not an
assumption that all 100 v0.1 keys occur in that pool. Hazard filtering uses the
recorded `al_round1_hazard_v4` SMARTS rules. The v4 additions are default hard
exclusions for halogen-oxygen bonds and an expanded thiocarbonyl family. The
alpha-halo ether, ordinary thiocarbonyl, and S-S exclusions from v2 remain.
These motifs introduce substantial alkylation, hydrolysis, or redox reactivity
risk in an electrolyte screening pool. No candidate matching these rules was
retained, and no exception path was added.

`halogen_oxygen` uses `[F,Cl,Br,I]-[OX2]` and matches 1,299 source records.
The previous rank-2 candidate `ClOCOCC(Cl)(Cl)Cl` now matches this rule and is
absent from both the longlist and Top 30. `thiocarbonyl` now combines
`[CX3]=[SX1]` with the complete carbon-sulfur motif `[#6]=[#16]`; the combined
flag matches 3,274 records. The real cumulated SMILES
`C1=S=C=C2OCCOC=12` matches this rule. It was selection order 13 before this
change (`alr1:028678`, `VYGLPZUKLQBYQO-UHFFFAOYSA-N`) and is now absent from
both the longlist and Top 30. Rule-level hit counts are retained in
`probes/al_round1_summary.json`; counts overlap because a molecule can match
more than one rule.

Ordinary polyhalogenated alkyl structures that do not match a hard rule are not
automatically excluded. They receive `manual_review_warnings=polyhalogenated_alkyl`
instead. There are 10,602 such safe candidates and 9 in the final Top 30.

## Scoring and tiers

The frozen predictor is Morgan count fingerprint radius 2, 2048 bits, followed
by StandardScaler and the existing Gaussian process configuration. Candidates
were scored in batches of 4096 to avoid materializing a 115k x 2048 matrix.

Candidate novelty is:

```text
novelty = 1 - max(binary Morgan Tanimoto similarity to dielectric v0.1)
```

The acquisition score is:

```text
acquisition_score = std_percentile * novelty
```

The final ranking is not based on posterior standard deviation alone.
SolvFunc-87 supplies nearest-neighbor context and tiers:

- Tier A: maximum SolvFunc binary Morgan Tanimoto >= 0.4.
- Tier B: maximum SolvFunc binary Morgan Tanimoto >= 0.3.
- Tier C: maximum similarity below 0.3.

All 85,921 safe candidates have a tier: A, 13,361; B, 17,570; C, 54,990. The
300-row longlist contains 68 Tier A and 232 Tier B rows. No Tier C row was needed
to fill the longlist.

## Top 30 summary

The first ten rows in deterministic selection order are:

| Order | Family | Tier | Predicted dielectric | Posterior std | Novelty | Acquisition | Selection step score |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Cyclic Carbonates | B | 36.685193 | 28.596536 | 0.920000 | 0.888520 | 0.888520 |
| 2 | Formates | B | 24.181145 | 33.973802 | 0.863636 | 0.855816 | 1.000000 |
| 3 | Ethers | B | 22.883156 | 30.653701 | 0.846154 | 0.830338 | 0.967742 |
| 4 | Ethers | B | 28.209330 | 34.415671 | 0.833333 | 0.827078 | 0.961538 |
| 5 | Ethers | B | 19.197940 | 30.269963 | 0.814815 | 0.798086 | 0.941176 |
| 6 | Ethers | B | 51.100108 | 28.013070 | 0.869565 | 0.834072 | 0.933333 |
| 7 | Ethers | A | 36.500439 | 27.588219 | 0.818182 | 0.779520 | 0.931034 |
| 8 | Cyclic Carbonates | B | 25.413783 | 35.712781 | 0.785714 | 0.782605 | 0.903226 |
| 9 | Cyclic Carbonates | A | 14.619675 | 38.476826 | 0.888889 | 0.887513 | 0.894737 |
| 10 | Ethers | B | 90.868888 | 28.802517 | 0.843750 | 0.816656 | 0.891892 |

The Top 30 family distribution is Cyclic Carbonates 6, Ethers 6, Formates 6,
Sulfones/Sulfoxides 5, Ketones 3, Nitriles 2, Other Esters 1, and Linear
Carbonates 1. The A/B hard-quota pass produced 20 rows. Because the A/B
longlist could not satisfy the 30-row target without exceeding the quota, the
selection continued with Tier C rows and added 10 more. Final Top 30 tiers are
A 6, B 14, and C 10.

The selection uses deterministic greedy MaxMin diversity with a hard family
quota of 6 and seed 42. There is no all-remaining fallback: if the family quota
cannot be satisfied, fewer than 30 rows are returned. Tier C is used only by
continuing the selection after the A/B pass, with the top six
acquisition-ranked Tier C rows per family available and the same hard quota
still enforced. Every row records its selection order, step score, source
commit, and `model_input_sha256`. This field identifies the dielectric input
used to fit the model; it is not presented as a serialized model artifact hash.

## Limitations and status

- Predictions are model outputs, not measurements.
- The dielectric model remains weak: the frozen GPR baseline has held-out R2
  `0.23126`, so predicted dielectric values must not be treated as accurate
  target-property estimates.
- Similarity tiers indicate chemical context relative to SolvFunc-87. They do
  not establish electrochemical stability, solubility, toxicity, or battery
  compatibility.
- Melting point, boiling point, and literature DOI are intentionally empty for
  all selected candidates.
- Availability remains `unknown`, and all 30 final rows have
  `decision_status=awaiting_manual_review`.
- No candidate is claimed to be experimentally available or confirmed as a
  room-temperature liquid.

Artifacts:

- `data/processed/al_round1_longlist.csv`
- `data/round1_candidates.csv`
- `probes/al_round1_summary.json`
- `probes/artifacts/al_round1_selection.png`
