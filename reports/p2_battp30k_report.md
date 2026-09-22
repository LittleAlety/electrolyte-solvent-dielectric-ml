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

## Important limitation

The official README identifies `dipole` as a three-component vector, but neither
the repository documentation nor the HDF5 metadata declares its physical unit.
The target is therefore the norm in source units, not a confirmed Debye or
atomic-unit target.

## Decision

Morgan count fingerprints plus XGBoost are not sufficient for this target. The
next step should add chemically meaningful descriptors, use a 3D/GNN
representation, or train a D-MPNN. Additional depth or tuning of the same
Morgan+XGBoost baseline is not the preferred path.

Formal machine-readable results remain in `probes/p2_summary.json`; the executed
notebook is `probes/p2_battp30k_baseline.ipynb`.
