# Week 4 physical-feature ablation

## Scope

The Week 4 experiment tests whether explicit molecular physics recovers
information that a 2D Morgan fingerprint cannot express for relative
permittivity.

The modelling table starts from 210 v0.2 compounds:

- 205 compounds have complete GFN2-xTB physical features.
- 4 compounds failed the xTB calculation and are recorded as `error`.
- 1 conflicting source value, `Ethyl isothiocyanate`, is retained in
  `data/processed/dielectric_v02_exclusions.csv`.

No missing physical feature is imputed, and the excluded conflict is not used
for training or evaluation.

## Physical features

The physical representation contains:

`T_K`, `formal_charge`, `heavy_atom_count`, `hbd`, `hba`, `tpsa_A2`,
`molecular_volume_A3`, `dipole_D`, `polarizability_A3`, `mu_sq_over_Vm`,
`alpha_over_Vm`, `total_energy_hartree`, and `homo_lumo_gap_ev`.

The xTB command is fixed to GFN2 optimization with charge and multiplicity
from the standardized molecule. The cache key binds canonical SMILES, formal
charge, conformer seed, input geometry, xTB version, and executable metadata.

## Model comparison

All three representations use the same 10x5 `RepeatedKFold` split, seed, and
single-threaded XGBoost parameters. `Morgan+Physical` is the exact 1:1 average
of two separately trained component models. It is not a raw high-dimensional
concatenation.

Metrics are computed on a complete out-of-fold vector for each repeat, then
summarized across the 10 repeats. Per-fold metrics are diagnostic only.
Predictions are clipped to the physical lower bound `dielectric >= 1`.

| Representation | R2 | MAE | RMSE | Spearman | AUC >15 | AUC >30 |
| --- | --- | --- | --- | --- | --- | --- |
| Morgan | 0.203 +/- 0.015 | 7.654 +/- 0.131 | 17.016 +/- 0.161 | 0.697 +/- 0.026 | 0.886 +/- 0.009 | 0.812 +/- 0.014 |
| Physical | 0.283 +/- 0.041 | 7.238 +/- 0.320 | 16.131 +/- 0.455 | 0.821 +/- 0.016 | 0.902 +/- 0.011 | 0.928 +/- 0.007 |
| Morgan+Physical | 0.320 +/- 0.022 | 6.726 +/- 0.176 | 15.711 +/- 0.252 | 0.830 +/- 0.012 | 0.921 +/- 0.006 | 0.915 +/- 0.008 |

## Interpretation

Physical information is a real signal. `Morgan+Physical` improves R2 by
`0.118` and reduces MAE by `0.927` relative to Morgan alone. Spearman rank
correlation rises from `0.697` to `0.830`, and AUC for `epsilon > 15` rises
from `0.886` to `0.921`.

The hybrid is not uniformly best. The pure physical representation remains
best for `epsilon > 30` discrimination (`0.928` versus `0.915`). The result
supports a physics-informed screening model, but not a claim of a resolved
full-range regression.

The high-permittivity stratum remains difficult. Mean MAE for `epsilon > 60`
is `81.3` for Morgan, `63.8` for Physical, and `72.3` for the hybrid. This
large residual, rather than the aggregate R2 alone, is the main remaining
scientific caveat. A single pre-registered transformed-target experiment
(`log(epsilon - 1)` or a Clausius-Mossotti/Onsager linearization) remains the
next controlled test.

## Evidence

- Builder: `probes/dielectric_representation_ablation.py`
- Independent verifier: `scripts/verify_dielectric_representation_ablation.py`
- Summary: `probes/dielectric_representation_ablation_summary.json`
- Per-fold metrics: `data/processed/dielectric_representation_ablation_cv.csv`
- Per-repeat metrics: `data/processed/dielectric_representation_ablation_repeats.csv`
- OOF predictions: `data/processed/dielectric_representation_ablation_predictions.csv`
- Figure: `probes/artifacts/dielectric_representation_ablation.png`
- Cold xTB benchmark: `probes/p5b_xtb_timing.csv`

The independent verifier passes 12/12 checks. It reproduces all 150 fold
metrics, all 30 repeat metrics, and the summary statistics from prediction
artifacts without calling the builder's aggregation code.
