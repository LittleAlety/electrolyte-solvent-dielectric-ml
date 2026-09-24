# Week 6 v0.3 Increment and Model Freeze

## v0.3 candidate table

`data/dielectric_v03.csv` is built from:

- the 210 rows in `data/dielectric_v02.csv`; and
- 33 public additions across:
  - `data/processed/modern_solvent_public_observations.csv`; and
  - `data/processed/modern_solvent_public_review_observations.csv`.

The primary additions are:

- six n-nitriles at 298.15 K from the public Pramana article
  `10.1007/BF02848094`;
- four NBS Circular 514 records that were eligible in v0.2 but had remained
  below the selection cutoff.

The review-table additions include modern carbonates, cyclic ethers, glymes,
phosphates, nitriles, fluorinated ethers, and chlorinated diluents. Every row
retains its review DOI, table, temperature-source status, license, license URL,
and explicit redistribution condition. The source metadata distinguishes
CC BY, CC BY-NC, and CC BY-NC-ND reuse from unrestricted redistribution. Of
the 33 additions, 30 are model-ready and three are retained only as explicit
conflicts (`FEC`, `TEP`, `TMP`). `Ethyl isothiocyanate` remains excluded from
model fitting because its NBS and restricted cross-check values differ by 10.2.

The build rejects any addition whose `redistribution_status` is not `allowed`
or `public_domain`, and rejects review additions with missing, unknown,
restricted, or unrestricted `redistribution_conditions`. SpringerMaterials
values remain restricted cross-check evidence and are not promoted.

Build and verify:

```powershell
.\.venv\Scripts\python.exe scripts\build_dielectric_v03.py `
  --minimum-additions 10
.\.venv\Scripts\python.exe scripts\verify_dielectric_v03.py
```

The v0.3 table now contains 243 compounds and satisfies the count target. It
remains a candidate release because many review-table values do not state an
independent temperature and still require primary-source confirmation before
v1.0.

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

## v0.3 model sensitivity

The frozen Morgan, Physical, and equal-weight hybrid models were rerun on the
v0.3 rows with physical features available. The original week-6 rerun covered
235 rows and reported Morgan `0.190`, Physical `0.273` and hybrid `0.310`;
those values predate the `model_ready` gate and fitted vinylene carbonate, which
the dataset flags `model_ready=false`. **Superseded 2026-09-24 (v0.3.4)** by the
gate-fixed rerun on 236 rows:

- Morgan: R2 `0.240`, MAE `7.612`, Spearman `0.722`;
- Physical: R2 `0.342`, MAE `7.098`, Spearman `0.802`;
- Morgan+Physical: R2 `0.364`, MAE `6.686`, Spearman `0.828`.

The hybrid R2 is essentially unchanged from the v0.2 result (`0.320`), and the
controlled train-only PC/EC comparison shows no measurable gain (`+0.0059`,
95% CI -0.002 to +0.013, p = 0.11). The expansion therefore improves domain
coverage but not predictive accuracy. This must be described as a coverage
result, not a performance improvement.

## Applicability domain

`src/electrolyte_ml/applicability.py` marks a prediction as
`outside_associated_liquid` when the compound carries at least one
hydrogen-bond donor site (`[O,S,N;!H0]`, counted from the structure, so the
boundary never reads the model output) and as `outside_nonphysical` when the
prediction falls below 1.0. The rule triggers on 2,070 of the 6,150 out-of-fold
rows (33.66%). This is a disclosure boundary, not a post-hoc model
improvement.

## Neural-network probes

The first small-data MLP probe uses the same 10x5 folds and log(epsilon - 1)
target. Its best R2 representation is negative, so the Go/Kill decision is
`no_go`; the Physical MLP does retain a higher mean Spearman correlation
(`0.884`) than the XGBoost hybrid (`0.830`), which reinforces the ranking-only
interpretation of the representation ceiling.

Chemprop 2.1.0 is installed only in `.venv-chemprop` because it requires
NumPy 1.x while the project environment pins NumPy 2.x. The D-MPNN baseline
uses the same 10x5 outer folds and is recorded separately.
