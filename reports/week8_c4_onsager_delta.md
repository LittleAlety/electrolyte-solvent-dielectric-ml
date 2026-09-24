# Week 8 C4: Onsager residual delta learning

**Date:** 2026-09-24
**Probe:** probes/dielectric_onsager_delta_probe.py
**Summary:** probes/dielectric_onsager_delta_summary.json
**Status:** closed. Decision is "go" for the residual layer only. Onsager is
**not** promoted to a standalone predictor.

## Outcome

The question was whether a physics-first, machine-learning-corrected model can
compete with an end-to-end regressor: compute the Onsager estimate g from the
xTB dipole, molar volume and polarizability, then learn delta = epsilon - g.

Across 234 compounds with a row-level RepeatedKFold(5, 10, seed=42), repeat
averaged:

| Arm | Overall MAE | Donor | Ionic | none | both | epsilon over 60 | Donor bias | Ionic bias |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O0_onsager | 10.49 | 16.66 | 41.22 | 4.43 | 34.03 | 87.02 | +13.84 | -34.25 |
| O1_structured_offset | 9.41 | 14.13 | 40.35 | 4.33 | 49.63 | 83.09 | +5.44 | -22.85 |
| R0_direct_regression | **6.36** | 11.15 | 7.04 | 4.11 | 8.45 | 71.34 | +4.12 | -0.04 |
| R1_direct_with_logg | 6.44 | 12.04 | 10.78 | 3.39 | 9.11 | 67.22 | +2.06 | -3.88 |
| D0_delta_core | 8.79 | 13.19 | 31.92 | 4.23 | 20.24 | 70.27 | +1.55 | -17.00 |
| D1_delta_core_morgan | 8.54 | 12.14 | 34.13 | 4.04 | 19.96 | 75.96 | +4.63 | -17.77 |
| D2_delta_log | 12.85 | 23.84 | 39.64 | 5.21 | 44.51 | 86.19 | -7.52 | -32.93 |
| D3_delta_leaky (diagnostic only) | 7.22 | 12.81 | 16.81 | 3.66 | 15.21 | 61.79 | +0.72 | -7.74 |

The O0 column reproduces the pre-registered audit exactly (overall 10.49, donor
16.66 with bias +13.84, ionic 41.22 with bias -34.25), so the physics baseline
is the one that was agreed in advance rather than a re-tuned variant.

## What the delta layer does and does not buy

The headline confirmatory arm D1 passes every pre-registered gate **on the point
estimate**: donor MAE 12.14 < O0's 16.66; ionic 34.13 does not worsen relative to
41.22; epsilon over 60 improves from 87.02 to 75.96; and overall 8.54 beats the
structured-offset baseline O1 at 9.41.

But the honest reading is narrower than that list suggests.

* D1 still loses badly to the plain Morgan+Physical regressor: 8.54 vs 6.36 MAE.
  R0 is better on every stratum that matters.
* The advantage over O1 has a bootstrap interval that **contains zero**
  (point estimate -0.872, 95% CI [-1.744, +0.011]). The gain is not established.
* The leaky diagnostic D3, which is allowed to see the Onsager inputs directly,
  beats every confirmatory arm at 7.22 MAE. Part of the apparent benefit comes
  from re-using the physical inputs rather than from learning an association
  correction, and D3 is not a legitimate model.

So the delta layer is real but modest: it turns a physically motivated but
badly biased predictor into a less biased one. It does not turn it into a
competitive regressor.

## The high-dielectric domain is still broken

The epsilon over 60 stratum contains exactly five compounds (ethanolammonium
nitrate 60.9, 2-hydroxyethylammonium lactate 85.6, N-methylacetamide 178.5,
water 78.9, formamide 106.1). Onsager predicts more than 60 for **zero of
them**. D0 lowers the stratum MAE from 87.02 to 70.27, but every prediction is
still a severe underestimate, with a stratum bias of +69.96.

That is the same failure the applicability module already documented with its
Onsager-threshold rule (0/150 high-dielectric coverage). The C4 result does not
rescue it, and the inherited record was read but not modified.

## Pairwise comparisons (compound-cluster bootstrap, 2000 resamples)

| Comparison | MAE delta | 95% CI | Contains zero |
| --- | ---: | --- | --- |
| O0 to D0 | -1.694 | [-2.919, -0.492] | no |
| O0 to D1 | -1.949 | [-2.987, -0.913] | no |
| O1 to D1 | -0.872 | [-1.744, +0.011] | **yes** |
| R0 to D0 | +2.437 | [+0.015, +5.699] | no (direct regression better) |
| D0 to D3_leaky | -1.575 | [-3.615, +0.023] | yes |

The ionic, "both" and epsilon over 60 strata hold fewer than 20 compounds each,
so their bootstrap intervals are suppressed by the pre-registered rule and the
suppression reason is recorded in the JSON.

## Decision wording

Learned delta layer confirmed for mechanism disclosure: **true**. Onsager
promoted to standalone predictor: **false**.

Any citation of this result must be accompanied by the R0/R1 direct-regression
comparison and the D3 leaky diagnostic, otherwise the value of the delta layer
is overstated.

## Verification

tests/test_dielectric_onsager_delta_probe.py passes 17 tests, covering the
four-parameter Onsager function against a closed-form reference and a pinned
gold value, the feature-closure assertion (set A disjoint from the delta
features, and D3_leaky intersecting both), the four structural domains including
water with hbd = 0 but an SMARTS donor, functional-group counts, raw and log
inverse transforms, the O1 domain-median fallback, the bootstrap suppression
rule, and the gate conjunction. Ruff is clean.
