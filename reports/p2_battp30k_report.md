# P2 Batt-P30K Baseline Report

## Outcome

The end-to-end pipeline succeeded: HDF5 molecule groups were parsed, SMILES were
canonicalized with RDKit, Morgan count fingerprints were generated, and XGBoost
regression predicted the Euclidean norm of each three-component dipole vector.
The source file contains 29,519 molecule groups and zero invalid SMILES.

The model gate failed. On the deterministic 80/20 split, seed 42:

| Metric | Value |
|---|---:|
| MAE | 0.360058308 |
| RMSE | 0.489559393 |
| R2 | 0.563648641 |
| R2 > 0.8 | false |

The learning curve improved from R2 0.294 at 1,000 training molecules to 0.515
at 10,000 and approximately 0.570 on the full training set, but it did not
approach the required threshold.

## Unit resolution

The HDF5 and Batt-SLM README do not declare a unit. However, Batt-SLM is built
on PiNN, whose official dipole documentation and `pinn/models/dipole.py` define
the property in atomic units. Batt-SLM `Batt-P30K/params.yml` also sets
`d_scale: 2.5412` and `d_unit: 2.5412` for the atomic-unit/Debye conversion.
The standard physical conversion used for reporting is
`1 a.u. = 2.5418 Debye`; `2.5412` is the rounded upstream training constant.

This is a high-confidence source-code inference, not HDF5 metadata:

- https://github.com/Teoroo-CMC/PiNN/blob/b166b8635a3ace9497ff34a80928a3a8d2b8eb01/docs/usage/dipole.md
- https://github.com/Teoroo-CMC/PiNN/blob/b166b8635a3ace9497ff34a80928a3a8d2b8eb01/pinn/models/dipole.py
- https://github.com/Teoroo-CMC/Batt-SLM/blob/a5101e30c6975552d97e34f1e93461126715c862/Batt-P30K/params.yml

## Target distribution

The full 29,519-molecule target has median `3.4617 D` and p95 `6.8984 D`.
Only `1.52%` is below `0.5 D` and `4.24%` is below `1 D`; `36.30%` is
`1-3 D` and `59.46%` is above `3 D`. Near-zero target compression is therefore
not the primary explanation for the failed R2 gate.

The held-out error by true-label stratum is:

| Stratum | n | MAE (D) | RMSE (D) | R2 | Status |
|---|---:|---:|---:|---:|---|
| `<0.5 D` | 85 | 2.0614 | 2.2003 | -172.70 | insufficient |
| `0.5-1 D` | 170 | 1.7161 | 1.8676 | -147.53 | reported |
| `1-3 D` | 2,134 | 0.8218 | 1.1090 | -3.223 | reported |
| `>3 D` | 3,515 | 0.9055 | 1.2524 | 0.305 | reported |

The negative stratum R2 values are dominated by low within-stratum variance and
should not be interpreted as stable subgroup generalization estimates. They do
show that the model is not simply compressing near-zero labels.

## Model comparison

All models use the same 80/20 split, seed 42.

| Model | MAE (a.u.) | RMSE (a.u.) | R2 | MAE (D) | RMSE (D) |
|---|---:|---:|---:|---:|---:|
| Dummy mean | 0.5812 | 0.7411 | -0.0000026 | 1.4773 | 1.8838 |
| MW + heavy atoms, Ridge | 0.5797 | 0.7386 | 0.00679 | 1.4734 | 1.8774 |
| Morgan + XGBoost | 0.3601 | 0.4896 | 0.56365 | 0.9152 | 1.2444 |

The dummy and size-only controls are near zero R2, while Morgan+XGBoost retains
a real but insufficient signal. This argues against a pipeline code bug and
against a simple molecular-size explanation.

The diagnostic pipeline does not read the formal Morgan metrics as inputs. It
independently retrains the same Morgan count + XGBoost model on the cache with
the same split and compares the result with `p2_summary.json`. The absolute
differences are MAE `4.7309e-8`, RMSE `7.4684e-9`, and R2 `3.9245e-9`, below
the fixed numerical audit tolerance `1e-7`. The audit requires `passed=true`.

## Decision

The pipeline is GREEN, but the R2 gate remains FAILED. Morgan count fingerprints
capture useful 2D information yet do not represent 3D geometry or
conformational dipole orientation well enough for this target. The next step is
Chemprop/D-MPNN or a 3D/GNN representation, not deeper tuning of the same
Morgan+XGBoost baseline.

Formal machine-readable results remain in `probes/p2_summary.json`; the executed
diagnostic outputs are in `probes/p2_diagnostics_summary.json`,
`data/processed/p2_diagnostics.csv`, and `probes/p2_diagnostics.ipynb`.
