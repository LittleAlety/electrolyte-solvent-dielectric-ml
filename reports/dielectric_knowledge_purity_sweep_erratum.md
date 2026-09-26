# Lever 9 erratum round: offset-aware permutation importance

The week 15 adversarial review (finding C-1) showed that version 1 of the knowledge
purity sweep measured the wrong columns: the ten pool names labelled the first ten
columns of the frozen physical block. This round re-runs the whole k grid with the
column targeting corrected. Version 1's numbers are quoted verbatim and are never
rewritten.

## What was wrong

- `permutation_importance` enumerates the labels it is handed from position zero, so
  `columns=KNOWLEDGE_POOL` addressed the first ten columns of
  `hstack([frozen_physical, knowledge])` -- the frozen block -- while carrying pool names.
- The top-k selection followed that broken order, and the arm's column order followed the
  selection, so with `colsample_bytree=0.8` the fit as well as the selection moved with it.

## Defect reproduced numerically, not narrated

- folds checked: 50
- folds where version 1's labels sat on the frozen block: 50
- worst absolute score difference: 0.000e+00 (tolerance 1e-12)

## Corrected label-to-column binding

- folds checked: 3, verified: 3
- worst absolute difference against the explicit-index computation: 0.000e+00 (tolerance 1e-15)

## Pre-registration

- `probes/dielectric_knowledge_purity_sweep_erratum_prereg.json` sha256 `88c45e4a58f333eb638b69ea8f6639da028fa5f2d96b5c003fba3f06a2273daf`
- locked at 2026-09-26T07:24:48Z, status `locked_before_run`
- thresholds: {"kill_delta_r2": 0.005, "min_positive_repeats": 8, "note": "the same four constants version 1 used (probes/dielectric_knowledge_purity_sweep.py:161-164), inherited verbatim and not relaxed. The corrected measurement is judged against the same bar as the invalid one.", "pass_delta_r2": 0.02, "placebo_collapse_tolerance": 0.02}
- pass criterion: the best k reaches a grouped R2 delta of at least +0.0200 against the baseline arm re-run in the same script, AND the delta is positive in at least 8 of the 10 repeats, AND the placebo arm collapses
- kill line: every k stays below +0.0050 -> dead, reported as dead. A pass carried by a single repeat is not a pass.
- shots registered up front: 4

## Scoreboard

- 457 rows over 97 compounds, 50 folds, 10 repeats, splitter GroupKFold by InChIKey (masked_splits), seed 42
- fold signature reproduced by a second deal: True
- the fold signature also matches version 1: True
- baseline reproduces 0.4091179943351143 against the published 0.4091179943351143: True

## Delta-R2 by k, the two column-targeting rules side by side

| k | version 1 (pool names over the frozen block) | corrected (offset-aware) |
|---|---|---|
| 2 | +0.002941058 | -0.005136434 |
| 4 | +0.007773678 | +0.005201058 |
| 6 | +0.008825444 | +0.004912652 |
| 10 | +0.014709978 | +0.015746812 |

- k=10 moved by +0.001036834

## Corrected curve

- best k: 10, best delta-R2: +0.015747
- shape: `edge_peak_high_k` (no_interior_peak_edge_peak)
- contradicts the paper's mechanism: True
- positive repeats by k: {"10": 7, "2": 5, "4": 4, "6": 6}
- placebo curve: `interior_peak` against `placebo_frozen_block_reference` (-0.045865), collapsed: True

## Verdict

- **sub_threshold**
- k=10 moved grouped R2 by +0.0157: above the kill line +0.005 but below the pass line +0.02
- the delta-R2 curve is `edge_peak_high_k` with no interior peak (`no_interior_peak_edge_peak`): the paper's law that more embedded knowledge lowers accuracy is not reproduced inside the frozen grid, and the contradiction is reported as such rather than filed as a non-result

## Is the curve order-free?  Three orders, measured

| order of the appended pool columns | k=2 | k=4 | k=6 | k=10 | best |
|---|---|---|---|---|---|
| version_1_broken_order | +0.002941 | +0.007774 | +0.008825 | +0.014710 | k=10 (+0.014710) |
| preregistered_pool_order | +0.005995 | -0.009829 | -0.000005 | +0.008666 | k=10 (+0.008666) |
| corrected_importance_order | -0.005136 | +0.005201 | +0.004913 | +0.015747 | k=10 (+0.015747) |

- k=10 spread across the three orders: 0.007080803
- every order stays below the pre-registered pass line: True
- the curve is not order-free.  At k=10 the three measured orders give three different deltas, which is the substantive content of finding C-1: the k=10 cell was never an invariant.  What the order does not change is the verdict -- every order stays below the pre-registered +0.0200 pass line, so the correction moves a number, not a decision

- the figure the week 15 ledger quoted as the corrected k=10 is the reading with the pool appended in the PRE-REGISTERED order, not the reading with the pool appended in the corrected importance order.  Both are legitimate orders and they are different measurements; the ledger' s label for that number was wrong, and the erratum reports all three side by side

## What changed and what did not

- version 1 decision: `sub_threshold`; corrected decision: `sub_threshold`; changed: False
- the corrected grid does NOT equal the re-review's quoted canonical-order grid; that quote is the pre-registered pool order, and the erratum measures both rather than picking one
- the adjusted declared check: adjusted_and_flagged -- the frozen callee addresses a column by the label's position in the list it is handed, so permuting the label list does not enumerate the same measurement twice -- it produces a mislabelled matrix, which is the defect under correction. Binding and determinism are the well-formed readings of the same intent and are reported instead; the adjustment is flagged for the next review round rather than counted as met

## Boundaries

- the k grid caps at k=10, which is the whole pool, so a peak beyond the grid cannot be
  excluded by this sweep;
- version 1's artefacts are pinned by digest and are not edited; both readings stand
  side by side and the corrected one is the measurement, not a second chance;
- AB-6's per-feature narrative and its top-three list stay uncitable unless the
  corrected ranking agrees with them;
- the pooled-OOF or random-row rescue of any reading here is still forbidden.

