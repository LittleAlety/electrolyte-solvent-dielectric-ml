# Week 6 Report: v0.3 Increment and Model Freeze

## Outcome

Week 6 completed the first public v0.3 increment and closed the planned model
upgrades without weakening the evidence standard.

- `dielectric_v03.csv` contains 243 compounds.
- The public additions are 33 observations: ten primary/archive additions and
  23 open-access article/table additions.
- Thirty additions are model-ready; three review-source additions remain
  explicit conflicts and four rows in total are excluded from fitting.
- Every review-source addition retains its DOI, citation, table, license, and
  explicit redistribution condition; no row is labelled unrestricted.
- The independent v0.3 verifier passes 6/6.
- Experimental density does not improve the fixed-fold model.
- Applicability domain flags are materialized for all existing OOF
  predictions.
- MLP and Chemprop baselines are complete; neither replaces XGBoost.
- A Scientific Data paper skeleton is committed.

## Coverage and sensitivity result

The count target is met, but the expanded model does not improve:
Morgan+Physical mean R2 is `0.310` on 235 fitted rows versus `0.320` on the
205-row frozen v0.2 set. The result is evidence for broader chemical coverage,
not better prediction. Review-table values that lack a clearly stated
temperature remain candidate evidence pending primary-source confirmation.

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
- `data/processed/modern_solvent_public_review_observations.csv`
- `data/processed/dielectric_v03_exclusions.csv`
- `data/processed/dielectric_physical_features_v03.csv`
- `docs/week6/data_v03_and_model_freeze.md`
- `probes/dielectric_density_feature_summary.json`
- `probes/dielectric_mlp_probe_summary.json`
- `probes/dielectric_chemprop_summary.json`
- `probes/dielectric_v03_representation_ablation_summary.json`
- `reports/model_comparison.md`
- `paper/outline.md`
