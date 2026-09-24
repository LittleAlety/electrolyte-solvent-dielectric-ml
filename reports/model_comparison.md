# Model Benchmark Update

All neural rows use the fixed 10x5 outer-fold grid. Metrics are means over the
ten repeat-level out-of-fold metric values.

| model | target | R2 | MAE | Spearman | AUC >30 |
|---|---:|---:|---:|---:|---:|
| XGBoost Morgan | raw | 0.203 | 7.654 | 0.697 | 0.915 |
| XGBoost Physical | raw | 0.283 | 7.238 | 0.821 | 0.928 |
| XGBoost Morgan+Physical | raw | 0.320 | 6.727 | 0.830 | 0.915 |
| MLP Morgan | log(epsilon - 1) | -0.447 | 12.813 | 0.170 | 0.563 |
| MLP Physical | log(epsilon - 1) | -0.172 | 7.432 | 0.884 | 0.940 |
| MLP Morgan+Physical | log(epsilon - 1) | -0.458 | 12.885 | 0.228 | 0.646 |
| Chemprop D-MPNN | raw | 0.237 | 7.887 | 0.665 | 0.857 |

## v0.3 coverage sensitivity (gate-fixed)

The same XGBoost representations on the expanded v0.3 feature set. The week-6
row-wise rerun (235 rows, hybrid R2 `0.310`) predates the v0.3.4
`model_ready` gate and still fitted vinylene carbonate; the gate-fixed rerun
covers 236 rows:

| model | R2 | MAE | Spearman | AUC >30 |
|---|---:|---:|---:|---:|
| Morgan | 0.240 | 7.612 | 0.722 | 0.837 |
| Physical | 0.342 | 7.098 | 0.802 | 0.937 |
| Morgan+Physical | 0.364 | 6.686 | 0.828 | 0.933 |

The hybrid R2 is essentially unchanged from the 205-row v0.2 result
(`0.320`), and the controlled train-only PC/EC test finds no measurable gain
(`+0.0059`, 95% CI -0.002 to +0.013, p = 0.11). The expansion therefore
addresses chemical-domain coverage, not predictive accuracy.

Interpretation:

- Chemprop is worse than the frozen XGBoost hybrid on every headline metric,
  consistent with the small-data regime.
- The Physical MLP has the highest Spearman correlation but unstable
  absolute predictions and a negative R2. It reinforces the ranking-only use
  case rather than replacing the frozen regressor.
- No neural variant is promoted. Chemprop remains a required benchmark row,
  not a deployment candidate.
