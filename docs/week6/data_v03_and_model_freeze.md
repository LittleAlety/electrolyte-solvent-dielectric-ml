# Week 6 v0.3 Increment and Model Freeze

## v0.3 candidate table

`data/dielectric_v03.csv` is built from:

- the 210 rows in `data/dielectric_v02.csv`; and
- 10 independently public additions in
  `data/processed/modern_solvent_public_observations.csv`.

The additions are:

- six n-nitriles at 298.15 K from the public Pramana article
  `10.1007/BF02848094`;
- four NBS Circular 514 records that were eligible in v0.2 but had remained
  below the selection cutoff.

The build rejects any addition whose `redistribution_status` is not `allowed`
or `public_domain`. SpringerMaterials values remain restricted cross-check
evidence and are not promoted.

Build and verify:

```powershell
.\.venv\Scripts\python.exe scripts\build_dielectric_v03.py `
  --minimum-additions 10
.\.venv\Scripts\python.exe scripts\verify_dielectric_v03.py
```

This is an incremental v0.3 candidate, not the final 30-50 compound modern
solvent target. The remaining gap is represented by
`data/processed/modern_battery_solvent_candidate_queue.csv`.

## Experimental-density feature test

Of 205 successful physical-feature compounds, 66 have a ThermoML density
observation within 10 K of the dielectric target temperature. The remaining
139 use the xTB-estimated molar volume.

The fixed 10x5 CV comparison is in
`probes/dielectric_density_feature_summary.json`. Experimental density did not
improve the model:

- raw Physical R2 delta: `-0.0014`;
- log-target Physical R2 delta: `-0.0024`;
- raw Hybrid R2 delta: `-0.0039`;
- log-target Hybrid R2 delta: `-0.0052`.

Decision: retain the original xTB-estimated `mu_sq_over_Vm` for the frozen
v1.0 feature set. Keep the experimental-density variant as a documented
negative result and robustness check.

## Applicability domain

`src/electrolyte_ml/applicability.py` marks a prediction as
`outside_associated_liquid` when `HBD >= 1` and predicted dielectric `> 60`.
This is a disclosure boundary, not a post-hoc model improvement.

## Neural-network probes

The first small-data MLP probe uses the same 10x5 folds and log(epsilon - 1)
target. Its best R2 representation is negative, so the Go/Kill decision is
`no_go`; the Physical MLP does retain a higher mean Spearman correlation
(`0.884`) than the XGBoost hybrid (`0.830`), which reinforces the ranking-only
interpretation of the representation ceiling.

Chemprop 2.1.0 is installed only in `.venv-chemprop` because it requires
NumPy 1.x while the project environment pins NumPy 2.x. The D-MPNN baseline
uses the same 10x5 outer folds and is recorded separately.
