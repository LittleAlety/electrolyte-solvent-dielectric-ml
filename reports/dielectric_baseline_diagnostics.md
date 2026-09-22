# Dielectric Baseline Diagnostics

## Scope

All diagnostics use `data/dielectric_v01.csv` with 100 unique P1 keys. The
canonical UTF-8/LF input SHA256 is
`6f31c5b22a6a85a14954d3103a9ce5498eb4cdb265e55cfc8679adb78e4e5396`.
The original seed-42 held-out split is reused unchanged:

- train 80
- held-out test 20
- test ID hash `a9ba1277297a5c1d8666e8271a6aec46e6ebad0497153b83dc2be5fe7e56b7ee`

## Single Split Comparison

| Model | MAE | RMSE | R2 |
|---|---:|---:|---:|
| DummyMean | 17.0686 | 24.2616 | -0.01811 |
| MW + heavy atoms, Ridge | 16.3352 | 23.5925 | 0.03728 |
| Morgan count + RBF-GPR | 11.5345 | 21.0821 | 0.23126 |

The original GPR held-out metrics are preserved exactly in
`probes/dielectric_gpr_summary.json`; CV and descriptor diagnostics are
additional evidence and do not replace them.

## Repeated Cross-Validation

`RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)` gives 150 fold rows,
50 per model:

| Model | MAE mean +/- std | RMSE mean +/- std | R2 mean +/- std |
|---|---:|---:|---:|
| DummyMean | 14.9043 +/- 3.5468 | 22.1645 +/- 9.3687 | -0.1638 +/- 0.4662 |
| SizeOnlyRidge | 14.5913 +/- 3.4700 | 21.9452 +/- 8.9662 | -0.1861 +/- 0.6698 |
| MorganRBFGPR | 11.6865 +/- 3.8583 | 20.2361 +/- 10.1300 | 0.02295 +/- 0.6815 |

The low positive single-split GPR R2 is not stable under repeated folds. The
large fold-to-fold variance is consistent with the small dataset and
high-dielectric outliers.

## Learning Curve

The original 20 held-out compounds remain fixed. Train subsets of 20, 40, 60,
and 80 were sampled five times each from the original training partition.

MorganRBFGPR results:

| Train size | MAE mean +/- std | R2 mean +/- std |
|---:|---:|---:|
| 20 | 15.4088 +/- 1.8787 | -0.02261 +/- 0.19056 |
| 40 | 13.8689 +/- 1.3346 | 0.12456 +/- 0.13449 |
| 60 | 14.0919 +/- 1.7754 | 0.03447 +/- 0.18112 |
| 80 | 11.5345 +/- 0.0000 | 0.23126 +/- 0.0000 |

The curve is noisy rather than monotonically improving, but the full 80-row
training partition is the best observed subset.

## Descriptor Enhancement

A single fixed quick test appended 14 RDKit/Gasteiger descriptors to the Morgan
count fingerprint and used the same StandardScaler + GPR configuration and
split. No hyperparameter tuning was performed.

| Metric | Morgan only | Morgan + descriptors | Change |
|---|---:|---:|---:|
| MAE | 11.5345 | 10.1514 | -1.3831 |
| RMSE | 21.0821 | 18.9240 | -2.1581 |
| R2 | 0.23126 | 0.38059 | +0.14933 |

The quick test reached R2 `0.38059`, above the diagnostic reference `0.35`.
This is encouraging but not sufficient for the `0.8` gate and not a final
model. Fourteen Gasteiger atom values were non-finite for two
hexafluorophosphate structures; statistics use finite charges only, with
all-zero charge statistics if none are finite.

## Limitations

- Only 100 compounds are available.
- Repeated CV and learning-curve variance are high.
- High-dielectric substances such as water and formamide strongly affect RMSE.
- The descriptor test is one fixed experiment, not a tuned benchmark.
