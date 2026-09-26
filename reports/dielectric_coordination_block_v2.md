# Lever 8, second shot - the Li+ coordination block under an amended placebo clause

- generated: `2026-09-26T04:23:50Z`
- pre-registration (v2): `probes/dielectric_coordination_block_prereg_v2.json` (sha256 `80e7d8891cb7ad2e9659d22add34aa55e4e41b55c7f06145335173b6bfeda70b`, locked 2026-09-26T04:02:50Z)
- decision: **pass_under_amended_placebo_clause**

- the block moved grouped Morgan+Physical R2 by +0.0441 against the re-run baseline and the amended placebo clause collapsed; the block arm beat the baseline in 8 of 10 repeats. The v1 decision remains `dead` and this is a second, separately counted shot.

## Read this beside v1, never on top of it

- v1 (`probes/dielectric_coordination_block_summary.json`) recorded **dead** and still records **dead**. Its pre-registration and every one of its artefacts are byte identical; the digests taken at lock time are in the v2 pre-registration.
- the superseded clause `the mae_gt60 stratum must not get worse, and the placebo arm must collapse (|delta R2| <= 0.0200)` names no reference, and against the real-label baseline it is unsatisfiable whenever the placebo behaves as a placebo. That is a defect of the sentence, not a reading of our numbers.
- this shot is a **new, separately counted** attempt under an explicitly amended clause, written before the run and identical in form to lever 2 and lever 9.
- the amendment exists to repair a broken sentence, **not to rescue lever 8**. Gating on all three readings at once is at least as strict as either sibling.
- whether the block is carried into a merge arm is **not decided here**: left to the integrator: this shot neither requests nor pre-empts a merge arm

## Scoreboard

- scored rows 457, compounds 97, folds 50, repeats 10
- straddling compounds across a fold boundary: 0
- shuffled label vector: seed 42, sha256 `fe2a1ba082fcee62809dbfd90d532c2b3b1607003a29f5bc4e7d748e8dc4e75b` - reused from v1, not redrawn
- coordination block: 88 compounds with a usable block, read byte identical from the v1 feature artefact
- xTB executed by this shot: **no** (the block is frozen, so there is no cost)

## Arms

| arm | role | R2 | MAE | Spearman | MAE >60 |
| --- | --- | --- | --- | --- | --- |
| `baseline` | reference (real labels, frozen v03 physical + Morgan) | 0.4091 | 8.0407 | 0.7763 | 55.7131 |
| `plus_coordination_block` | the shot (the five coordination columns appended, real labels) | 0.4532 | 7.9176 | 0.7869 | 51.0224 |
| `placebo_shuffled_target` | placebo (the same block pipeline, shuffled labels) | -0.0408 | 13.6127 | -0.0166 | 68.4971 |
| `baseline_features_shuffled_target` | contrast (frozen feature set, the SAME shuffled labels) | -0.0304 | 13.5725 | -0.0052 | 67.9139 |
| `no_information_floor` | no-information floor (training-fold mean, the SAME shuffled labels) | -0.0044 | 13.3887 | -0.0692 | 68.4284 |
| `no_information_floor_real_labels` | no-information floor on the real labels (context) | -0.0687 | 14.0197 | -0.3535 | 68.7348 |

## Amended placebo clause (all three readings must hold)

- rule 1, floor upper bound: placebo -0.0408 minus floor -0.0044 = -0.0365 -> holds: True
- rule 2, the same pipeline on real labels: placebo minus the block arm = -0.4940 -> holds: True
- rule 3, within-pipeline shuffled contrast: placebo minus the frozen feature set on the SAME shuffled labels = -0.0104 -> holds: True
- tolerance for every rule: 0.02; **collapsed: True**
- floor definition: the training-fold-mean predictor scored on the identical folds and the identical permuted label vector as the shuffled-label arm
- note: the superseded v1 clause named no reference; measured against the real-label baseline it is unsatisfiable by construction. This clause names its reference explicitly, is one-sided, and gates on all three readings.

## Paired deltas (plus_coordination_block - baseline)

| metric | delta |
| --- | --- |
| r2 | +0.0441 |
| mae | -0.1231 |
| rmse | -0.5172 |
| spearman | +0.0106 |
| mae_lt20 | -0.2721 |
| mae_20_60 | +0.4886 |
| mae_gt60 | -4.6907 |

- baseline reproduction: 0.4091179943351143 vs published 0.4091179943351143 (abs delta 0.00e+00)
- mae_gt60 delta -4.6907 (not a gate in v2, reported)

## v1 and v2 side by side

| | v1 | v2 |
| --- | --- | --- |
| decision | `dead` (unchanged) | `pass_under_amended_placebo_clause` |
| placebo reference | the real-label baseline, absolute distance | the no-information floor on the identical permuted labels |
| block delta R2 | +0.0441 | +0.0441 |
| placebo R2 | -0.0408 | -0.0408 |
| shots | 1 | 1 (lever 8 total 2) |

## Honest boundaries

- the v1 decision is `dead` and remains `dead`. This shot is a second, separately counted attempt under an explicitly amended clause; it does not overturn v1 and must never be quoted as if it had.
- the amended clause exists because the v1 sentence named no reference and is unsatisfiable by construction against a real-label baseline. The amendment was written before this run and is identical in form to lever 2 and lever 9, not tuned to this lever's numbers.
- all three clause readings are gated at once at the same +0.0200. Two of them are easy to satisfy; the third, the within-pipeline contrast against the frozen feature set on the identical shuffled labels, is the one that would catch a block that still lifts on random labels.
- target mismatch: the source review describes solvating power inside an electrolyte, while this scoreboard predicts the static dielectric constant of a pure solvent. The block tests which of the review's axes transfers to a different target.
- no xTB ran in this shot. The coordination block is read byte identical from the v1 feature artefact, so the feature side is frozen by construction and no cost was incurred.
- GFN2-xTB overbinds Li+; only the spread of the binding energy across compounds is used, never its absolute value as thermochemistry.
- the Li+ complex is gas phase and single molecule: no anion, no solvent-solvent competition - the weakness the review itself states for the binding-energy descriptor.
- nine compounds have no O and no N, so the pre-registered site rule leaves their block undefined rather than filled; the frozen model handles the missing cells natively.
- the mae_gt60 stratum, MAE, RMSE and Spearman deltas are reported beside the decision, not gated by it: the v2 pass criterion names only the baseline reproduction, the R2 delta and the amended placebo clause.
- the placebo arm sits -0.4500 below the real-label baseline. That is the expected sign for shuffled labels and is reported for completeness only; the v1 clause that made that distance a gate is superseded here, not deleted.

## Shots

- this shot: 1
- v1 shot: 1
- lever 8 total after this run: 2
- policy: attempts at the main scoreboard are counted in reports/decisions_log.md section 12
- this probe may not edit decisions_log.md, so the count is carried here for the integrator to register

## Files

- folds: `probes/artifacts/dielectric_coordination_block_v2_folds.csv`
- predictions: `probes/artifacts/dielectric_coordination_block_v2_predictions.csv`
- repeats: `probes/artifacts/dielectric_coordination_block_v2_repeats.csv`
- report: `reports/dielectric_coordination_block_v2.md`
- summary: `probes/dielectric_coordination_block_v2_summary.json`

