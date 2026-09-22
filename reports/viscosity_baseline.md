# Viscosity Strong Baseline

## Setup

The model uses only `data/viscosity_v01.csv`: 3,582 experimental rows and 957
unique InChIKeys. The target is `log10(viscosity_cP)`.

Features are Morgan count fingerprint radius 2/2048 bits plus `T_K` and
`1000/T_K`. All models use seed 42:

- Dummy mean.
- Ridge on `T_K + 1000/T_K`.
- Fixed XGBoost on Morgan + temperature features.

Two evaluations are reported:

1. random row 80/20, which allows other temperatures of the same molecule in
   train and test;
2. InChIKey group holdout 80/20, which prevents the same molecule from appearing
   in both sides.

## Random Row

| Model | log10(cP) MAE | RMSE | R2 | Gate MAE<0.15 |
|---|---:|---:|---:|---|
| DummyMean | 0.38487 | 0.47253 | -0.00040 | false |
| TOnlyRidge | 0.37964 | 0.46593 | 0.02736 | false |
| MorganTemperatureXGBoost | 0.06357 | 0.11868 | 0.93689 | true |

## Group Holdout By InChIKey

| Model | log10(cP) MAE | RMSE | R2 | Gate MAE<0.15 |
|---|---:|---:|---:|---|
| DummyMean | 0.39890 | 0.48662 | -0.00121 | false |
| TOnlyRidge | 0.39176 | 0.47856 | 0.03168 | false |
| MorganTemperatureXGBoost | 0.17477 | 0.24407 | 0.74813 | false |

## Unit Relations

`log10(Pa*s) = log10(cP) - 3`. Therefore the log10 MAE, RMSE, and R2 are
numerically equivalent in both log-unit columns, while raw Pa*s values are
the corresponding raw cP values divided by 1000.

For Morgan+Temperature XGBoost, raw cP metrics are:

- random row: MAE `0.45274`, RMSE `1.35555`, R2 `0.84841`;
- group holdout: MAE `0.92721`, RMSE `2.10599`, R2 `0.63811`.

## Conclusion

The random-row baseline passes the `log10(cP) MAE < 0.15` gate, while the
group-key holdout fails at `0.17477`. This distinction is important:
random-row performance largely measures temperature interpolation within known
molecules, whereas group holdout measures generalization to unseen molecules.
The latter is the relevant warning signal for screening new solvents. No
test-driven hyperparameter tuning was performed.
