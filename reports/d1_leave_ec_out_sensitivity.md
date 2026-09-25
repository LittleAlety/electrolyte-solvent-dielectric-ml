# D1 leave-EC-out sensitivity (v0.3.14)

Status: complete, report-only, prepared for the D1 closure commit on 2026-09-25.
Machine-readable artefact: `probes/dielectric_leave_ec_out_summary.json`.
Independent verifier: `scripts/verify_d1_leave_ec_out.py` (8/8 checks).

## Pre-registration

The probe was frozen before it was run as a robustness/disclosure analysis. It
cannot trigger a post-hoc model switch, feature change or dataset revision. The
v1.0 configuration remains Morgan / Physical / equal-weight Hybrid exactly as
frozen in `probes/v032_ablation_summary.json`; any actual change would require a
separate pre-registered v1.1 revision.

## Protocol

| Item | Value |
|---|---|
| Frozen fold source | `data/processed/v032_ablation_predictions.csv` |
| Fold scheme | `RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)` |
| Seed scheme | `42 + global RepeatedKFold split index` |
| Baseline fitting set | 236 rows (the gate-fixed v0.3 benchmark) |
| Leave-EC-out fitting set | 235 rows per repeat |
| Removed row | ethylene carbonate, 313.15 K, 90.5, `extended_temperature` |
| EC training removal count | 40 (EC was held out once in each of 10 repeats, so it trained in the other 4 folds) |
| EC in training folds | 0 |

The 235 surviving compounds keep their frozen fold identifiers in every repeat.
The baseline arm reproduces the frozen benchmark exactly: 7080 baseline
prediction rows were compared and all matched.

## Paired sensitivity on the 235 surviving compounds

Deltas are leave-EC-out minus baseline. R2 and Spearman are maximised, whereas
MAE and RMSE are minimised; therefore positive R2/Spearman deltas and negative
MAE/RMSE deltas indicate better scores.

| Representation | Metric | Baseline (235) | Leave EC out | Delta | 95% CI | Paired p |
|---|---|---|---|---|---|---|
| Morgan | R2 | 0.2345 | 0.2273 | -0.0072 | [-0.0161, +0.0017] | 0.100 |
| Morgan | MAE | 7.3829 | 7.3372 | -0.0457 | [-0.1015, +0.0101] | 0.097 |
| Morgan | Spearman | 0.7199 | 0.7219 | +0.0020 | [-0.0028, +0.0068] | 0.379 |
| Physical | R2 | 0.3140 | 0.3096 | -0.0044 | [-0.0270, +0.0183] | 0.672 |
| Physical | MAE | 6.9734 | 6.9364 | -0.0371 | [-0.1528, +0.0787] | 0.487 |
| Physical | Spearman | 0.7999 | 0.8026 | +0.0028 | [-0.0012, +0.0068] | 0.149 |
| Morgan+Physical | R2 | 0.3494 | 0.3381 | -0.0112 | [-0.0243, +0.0018] | 0.083 |
| Morgan+Physical | MAE | 6.5065 | 6.4874 | -0.0191 | [-0.1000, +0.0618] | 0.606 |
| Morgan+Physical | Spearman | 0.8263 | 0.8295 | +0.0031 | [-0.0013, +0.0076] | 0.148 |

The RMSE direction is the opposite of MAE for every representation (for Hybrid,
+0.1305, CI [-0.0195, +0.2804], p = 0.081), which is expected when a single
extreme row is removed from an error distribution; no metric moves
significantly. The within-representation metric ranking is unchanged for
Morgan, Physical and Morgan+Physical.

## EC as an external leave-one-out target

EC is never trained on in the treatment arm; it is predicted from the 235-row
fits and compared with its stored target 90.5.

| Representation | Mean prediction | SD | Min | Max | Mean absolute error | Rank percentile among 235 |
|---|---|---|---|---|---|---|
| Morgan | 28.96 | 8.48 | 19.37 | 40.55 | 61.54 | 94.9 |
| Physical | 54.22 | 13.16 | 35.50 | 75.58 | 36.28 | 98.7 |
| Morgan+Physical | 41.59 | 9.32 | 28.09 | 51.15 | 48.91 | 98.7 |

## Reading

The model family ordering does not depend on EC: the explicit family ranking
across Morgan, Physical and Morgan+Physical is identical in both arms for all
four metrics (`family_ranking.changed = False`), and no paired metric moves
significantly. EC itself is recognised as an extreme high-permittivity
compound (98th percentile among the 235), but the predicted magnitude is
compressed by roughly a factor of 2.2 in the Hybrid arm. This is quantitative
evidence for the polar-aprotic high-permittivity hole discussed in the
Limitations section, not a reason to switch models.

## Reproduction

```bash
python probes/dielectric_leave_ec_out_sensitivity.py
python scripts/verify_d1_leave_ec_out.py
pytest -q tests/test_dielectric_leave_ec_out.py
```
