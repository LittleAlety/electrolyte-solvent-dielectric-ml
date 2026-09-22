# Dielectric Kernel Comparison

## Setup

All three models use the same 100-compound `dielectric_v01.csv` input and the
same `RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)` assignment:
150 model/fold rows total.

Tanimoto-GPR uses binary Morgan fingerprints with radius 2 and 2048 bits.
Train/train and train/test Tanimoto kernels are precomputed, the diagonal is
one, and `alpha=1e-6` provides jitter. No kernel hyperparameter optimization
is used.

RBF-GPR uses count Morgan fingerprints, StandardScaler, and the existing
`C(1)*RBF(length_scale=10)+WhiteKernel(noise_level=1)` configuration.
XGBoost uses the existing 800-tree configuration with `n_jobs=1`, fixing the
histogram reduction to a single thread for cross-platform reproducibility.

## Results

| Model | MAE mean +/- std | RMSE mean +/- std | R2 mean +/- std |
|---|---:|---:|---:|
| Tanimoto-GPR | 10.9603 +/- 3.6161 | 19.7630 +/- 10.3702 | 0.04246 +/- 0.81976 |
| RBF-GPR | 11.6865 +/- 3.8583 | 20.2361 +/- 10.1300 | 0.02295 +/- 0.68149 |
| XGBoost | 11.0124 +/- 3.7248 | 20.3296 +/- 10.7854 | 0.04135 +/- 0.52577 |

Tanimoto-GPR improves the RBF-GPR mean R2 by `0.01950`. Its mean MAE
`10.9603` remains slightly better than XGBoost `11.0124`. The revision changes
XGBoost's mean R2 from the earlier multithreaded value `0.03185` to `0.04135`,
but does not change the conclusion: this is a modest improvement, not a
meaningful gate pass. All models remain far below `R2 > 0.8`, and fold-level
variance remains very large.

## Conclusion

The current evidence does not justify further kernel hyperparameter tuning.
The next diagnostic step should focus on fold-level failures and representation
or data limitations rather than adjusting Tanimoto/RBF parameters.
