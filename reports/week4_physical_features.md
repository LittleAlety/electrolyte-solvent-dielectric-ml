# Week 4 physical-feature report

## Result

The representation hypothesis is supported in the main screening metrics.
Adding GFN2-xTB and RDKit physical descriptors to the 2D fingerprint raises
10-repeat mean R2 from `0.203` to `0.320`, lowers MAE from `7.654` to `6.726`,
and raises Spearman correlation from `0.697` to `0.830`.

Pure physical descriptors already beat pure Morgan on every main metric tested
except the narrow `epsilon > 30` classification, where Morgan has AUC `0.812`
and Physical has `0.928`. The hybrid reaches AUC `0.915`; therefore the pure
physical representation remains the best high-permittivity discriminator.

## Controls

- The comparison uses one fixed 10x5 RepeatedKFold split and one fixed
  single-threaded XGBoost configuration.
- The hybrid is an exact 0.5/0.5 prediction ensemble of separately trained
  Morgan and Physical models.
- Predictions are constrained to `dielectric >= 1`.
- All metrics are recomputed from 6,150 out-of-fold predictions by an
  independent verifier.
- The source accounting is 210 v0.2 rows = 205 successful features + 4 xTB
  failures + 1 excluded source conflict.
- The four failures are reported and excluded, not imputed.

## Caveat

The result is a representation gain, not a deployable full-range model. The
`epsilon > 60` stratum still has mean MAE between `63.8` and `81.3`. The
remaining error appears dominated by the small high-permittivity group and
single-conformer xTB features. A transformed-target test remains the next
controlled experiment.

## Verification

`scripts/verify_dielectric_representation_ablation.py` passes 12/12 checks.
The cold xTB benchmark records `0.134-0.235 s` per representative molecule,
well below the 10-minute P5 gate.
