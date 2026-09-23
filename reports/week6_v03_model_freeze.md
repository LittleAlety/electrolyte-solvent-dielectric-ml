# Week 6 Report: v0.3 Increment and Model Freeze

## Outcome

Week 6 completed the first public v0.3 increment and closed the planned model
upgrades without weakening the evidence standard.

- `dielectric_v03.csv` contains 220 compounds.
- The public additions are ten observations: six nitriles from a public
  Pramana article and four remaining eligible NBS Circular 514 records.
- The independent v0.3 verifier passes 6/6.
- Experimental density does not improve the fixed-fold model.
- Applicability domain flags are materialized for all existing OOF
  predictions.
- MLP and Chemprop baselines are complete; neither replaces XGBoost.
- A Scientific Data paper skeleton is committed.

## Remaining coverage gap

The target was 30-50 modern battery solvents. The current public increment is
10 because most remaining candidates lead only to restricted compilations.
Their metadata and unresolved statuses remain in the candidate queue. A value
is not promoted until an independent public or primary-source trail is
available.

## Model decision

The frozen model remains the equal-weight Morgan+Physical XGBoost ensemble with
raw dielectric output for R2 and `log(epsilon - 1)` Physical output for
ranking/MAE decisions. No universal target transform is selected.

The three explicit boundaries remain:

- representation ceiling: random-CV R2 approximately 0.32;
- extrapolation ceiling: scaffold/cluster R2 approximately 0.26;
- associated-liquid boundary: `HBD >= 1` and predicted dielectric `> 60`.

## Evidence files

- `data/dielectric_v03.csv`
- `docs/week6/data_v03_and_model_freeze.md`
- `probes/dielectric_density_feature_summary.json`
- `probes/dielectric_mlp_probe_summary.json`
- `probes/dielectric_chemprop_summary.json`
- `reports/model_comparison.md`
- `paper/outline.md`
