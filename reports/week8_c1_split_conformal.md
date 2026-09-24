# Week 8 C1: split-conformal intervals from the archived OOF predictions

**Date:** 2026-09-24
**Probe:** probes/dielectric_split_conformal_probe.py
**Summary:** probes/dielectric_split_conformal_summary.json
**Status:** closed. Marginal coverage holds; conditional coverage above
epsilon 60 collapses and is reported as a negative result.

## Outcome

Split conformal prediction gives the frozen dielectric benchmark a
zero-retraining, finite-sample marginal interval. At a nominal 90% level every
one of the six representation/arm series lands slightly above nominal:

| Series | Coverage | Repeat dispersion (descriptive) | Mean width | Median q |
| --- | --- | --- | --- | --- |
| Morgan / baseline | 0.9153 | [0.9142, 0.9164] | 42.23 | 17.49 |
| Morgan / augmented | 0.9154 | [0.9144, 0.9165] | 40.93 | 16.81 |
| Physical / baseline | 0.9156 | [0.9145, 0.9168] | 43.66 | 16.24 |
| Physical / augmented | 0.9138 | [0.9127, 0.9148] | 45.44 | 18.07 |
| Morgan+Physical / baseline | 0.9156 | [0.9148, 0.9164] | 38.93 | 17.23 |
| Morgan+Physical / augmented | 0.9151 | [0.9141, 0.9161] | 38.43 | 17.17 |

The third column is a **repeat dispersion interval, not a confidence interval**:
mean +/- t_{0.975,9} * s / sqrt(10) over the ten repeat-level means. Each
repeat re-fits the same 234 compounds, so the repeats are not independent
samples and this spread is descriptive only. A sampling interval would need a
compound-level bootstrap, which this probe does not claim.

The infinite-interval rate is exactly 0.0 for every series: with a 50%
calibration fraction inside each fold the per-cell calibration set is roughly 23
compounds, comfortably above the nine needed for a finite 90% order statistic.

Coverage being above nominal is the expected behaviour of the finite-sample
order statistic, not a sign of a miscalibrated model. The interval is
deliberately conservative.

## The negative result that matters

Marginal coverage is not conditional coverage. Conditioning on the target
stratum shows the model has no usable coverage where it counts:

| Series | epsilon under 20 | 20 to 60 | epsilon over 60 |
| --- | --- | --- | --- |
| Morgan / baseline | 0.978 | 0.777 | 0.015 |
| Morgan / augmented | 0.976 | 0.784 | 0.015 |
| Physical / baseline | 0.954 | 0.841 | 0.257 |
| Physical / augmented | 0.956 | 0.842 | 0.101 |
| Morgan+Physical / baseline | 0.972 | 0.796 | 0.038 |
| Morgan+Physical / augmented | 0.968 | 0.811 | 0.015 |

The high stratum holds only five compounds out of 234, so this number is noisy,
but the point estimate is unambiguous: an interval advertised as 90% covers the
high-dielectric tail at 1.5% to 26%. A normalised score
(s = abs(y - y_hat) / (1 + abs(y_hat))) lifts that to 0.18 to 0.51 and shrinks
the mean width, but it still does not come close to nominal.

This is the behaviour the applicability-domain work already flagged: the
benchmark interpolates the low-dielectric bulk well and extrapolates the
high-dielectric tail badly. The conformal probe turns that qualitative warning
into a number, and the number is bad.

## Method: what the first draft got wrong

The first implementation pooled residuals from every fold into a single global
quantile. That is not split conformal. Each (repeat, fold) cell comes from a
different training set and a different XGBoost seed, so residuals from different
cells are not exchangeable and a pooled quantile has no finite-sample guarantee.

The corrected protocol is:

1. For every random split r draw one global calibration/test partition of all
   234 compounds. The role of a compound is fixed by (seed + split_id) alone, so
   it is identical across every representation, arm and repeat, and all paired
   comparisons see the same rows.
2. Inside each frozen RepeatedKFold(5, 10, random_state=42) fold, estimate the
   conformal quantile from that fold's calibration compounds only and evaluate
   it on that fold's test compounds only. The quantile is never pooled across
   cells.
3. Quantile rule: k = ceil((m + 1) * (1 - alpha)); q = s_(k) if k is at most m,
   else +inf.
4. Summarise over the 200 random splits inside each repeat, then average the ten
   repeats with equal weight. The ten repeats are model refits, not ten
   independent datasets, so no test treats them as independent samples.

The probe records exchangeability.repeat_treated_as_independent = false,
exchangeability.conditional_target_coverage_claimed = false, and
repeat_dispersion_interval_note, which states that the ten-repeat spread is
descriptive rather than inferential.

## Honest boundary

The guarantee is marginal in compounds under exchangeability. The OOF
predictions are reused after the fact, so the interval describes the frozen
benchmark procedure rather than a freshly fitted single model. It provides no
conditional coverage guarantee, no chemical extrapolation guarantee and no
distribution-shift guarantee. The ten repeats do not create new independent
samples.

## Verification

tests/test_dielectric_split_conformal_probe.py passes 13 tests, including a
regression test that locks in both invariants: marginal coverage at or above
nominal, and the high-epsilon conditional collapse. Ruff is clean.
