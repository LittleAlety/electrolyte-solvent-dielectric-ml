# W18-P5 -- Uni-Mol pre-trained embeddings as a feature block

lane: W18-P5 (independent pre-registration, promotes nothing)

- representation: Physical(lever4)+UniMol
- pool: {"base_rows": 2029, "scored_rows": 457, "scored_compounds": 97, "rows": 2391}
- frozen control: baseline 0.4091179943351143, headline 0.4766400383507876
- frozen single representation 0.6080587938801277, cross-seed endpoint 0.5861142332208197

## Verdict: refuted

Cross-seed endpoint: {"reference_lever4": 0.5861142332208197, "plus_unimol": 0.1102020209457352, "unimol_only": 0.0305790659288033}

Delta vs the anchor arm: -0.4759122122750845

Seeds with a positive delta: 0

## Boundaries

- the lane adds no shot to the frozen main scoreboard
- a blocked lane is not a negative result and must never be quoted as one
- a synthetic or imputed embedding may never stand in for the pre-trained block
