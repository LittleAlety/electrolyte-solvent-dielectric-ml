# Dielectric v0.1: Morgan+GPR Baseline

## Scope

This baseline uses only `data/dielectric_v01.csv`: 100 independent P1
compound-level InChIKeys. Chodera contributes 45 historical/cross-check keys,
and all 45 overlap P1, so the effective union remains 100, not 145.

The recorded input SHA256 is the canonical UTF-8 text hash after normalizing
CRLF/CR line endings to LF, so Windows and Linux checkouts agree.

## Fixed Model

- Morgan count fingerprint, radius 2, 2048 bits.
- StandardScaler plus GaussianProcessRegressor.
- Deterministic 80/20 split, seed 42.
- Initial kernel: `1**2 * RBF(length_scale=10) + WhiteKernel(noise_level=1)`.
- Final kernel: `2.16**2 * RBF(length_scale=42.4) + WhiteKernel(noise_level=0.278)`.
- `alpha=1e-6`, `normalize_y=True`, `n_restarts_optimizer=2`,
  `random_state=42`.
- Hyperparameters were not selected using test metrics.

## Results

Held-out test contains 20 compounds. The model is poor on this small,
heterogeneous table:

| Metric | Value |
|---|---:|
| MAE | 11.5345014 |
| RMSE | 21.0820913 |
| R2 | 0.2312574 |
| 95% coverage | 0.95 (19/20) |

Diagnostic controls on the identical split are:

| Model | MAE | RMSE | R2 |
|---|---:|---:|---:|
| DummyMean | 17.0686 | 24.2616 | -0.01811 |
| MW + heavy atoms, Ridge | 16.3352 | 23.5925 | 0.03728 |
| MorganRBFGPR | 11.5345 | 21.0821 | 0.23126 |

Repeated 5-fold/10-repeat CV gives MorganRBFGPR R2 `0.02295 +/- 0.68149`,
confirming that the original held-out result is not stable across folds. A
single fixed descriptor-augmentation quick test reaches R2 `0.38059`; this is
recorded as evidence only and does not replace the original metrics.

Posterior standard deviations are finite and nonnegative, ranging from
`13.0834` to `31.1628`, with mean `18.3566`. The high standard deviation,
together with 95% empirical coverage, indicates a broad and highly uncertain
posterior rather than a useful predictive envelope for solvent screening.

No predictions were clipped. The held-out prediction set contains no negative
relative-permittivity values.

The R2 is below both the `0.8` gate and the P2 dipole baseline's `0.56365`, but
those targets are different and are not directly interchangeable. The result
is recorded as a negative baseline, not as model success.

## Interpretation

This is the active-learning starting point, not a final dielectric model. The
main limitations are only 100 compounds, broad chemical/ionic-liquid coverage,
high-dielectric outliers such as water and formamide, strong extrapolation
under the deterministic split, and Morgan topology features that do not encode
3D conformation or polarizability.

The output should be used to prioritize uncertainty-aware data acquisition and
later model comparison, not to claim deployable dielectric prediction.
