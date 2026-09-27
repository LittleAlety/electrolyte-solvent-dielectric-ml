# Week 17: widening only the training pool of the epsilon scoreboard

**Generated:** 2026-09-27T06:28:26Z

**Pre-registration:** probes/dielectric_pool_expansion_prereg.json (status locked_before_run, locked 2026-09-27T02:20:00Z, sha256 aa9a40eb534d1d6923f70fcaf3eb252d6f2a398a199eb7203c5c5e88093cd3e9)

**Decision:** primary_missed

the rebuilt hybrid scoreboard misses 0.60; the achieved number and the shortfall are reported as they stand

## 1. The frozen side

| Quantity | Value |
|---|---|
| Scored rows | 457 |
| Scored compounds | 97 |
| Folds | 50 (10 repeats x 5) |
| Baseline reproduction | 0.4091179943351143 vs 0.4091179943351143 (abs gap 0.00e+00, reproduced) |

## 2. The expansion block

| Quantity | Value |
|---|---|
| Rows read | 392 |
| Rows admitted | 362 |
| Compounds admitted | 360 |
| Rows of an already-scored compound | 13 |
| Tracks | {'nbs514': 362} |
| Dropout | {'duplicate_of_a_coverage_row': 29, 'no_xtb_features': 1, 'rows_rejected': 30} |

## 3. Arms

| Arm | Morgan+Physical R2 | Delta vs baseline |
|---|---|---|
| baseline_hybrid | 0.4091179943351143 | +0.000000 |
| plus_expansion_hybrid | 0.3809089252433510 | -0.028209 |
| expansion_only | 0.1250465112927389 | -0.284071 |
| plus_lever4_lever8 | 0.4766400383507876 | +0.067522 |
| plus_lever4_lever8_plus_expansion | 0.4353185412382897 | +0.026201 |
| expansion_label_placebo | 0.2196470593710983 | -0.189471 |

## 4. Governance

| Dose | Compounds | Rows | R2 | Delta vs baseline |
|---|---|---|---|---|
| 0.25 | 90 | 90 | 0.4959439161308793 | +0.086826 |
| 0.50 | 180 | 180 | 0.4021071725198608 | -0.007011 |
| 0.75 | 270 | 270 | 0.4058565921533362 | -0.003261 |
| 1.00 | 360 | 362 | 0.3809089252433510 | -0.028209 |

- Arm A (compound-level label placebo): delta -0.189471, tolerance +0.02 -> PASS
- Arm B (monotone dose response): FAIL

## 5. Primary criterion

- Primary arm plus_expansion_hybrid: R2 0.3809089252433510 against the bar 0.60
- Met: False (shortfall +0.219091)
- Merged gun (plus_lever4_lever8_plus_expansion): 0.4353185412382897 (+0.026201 vs baseline)

## 6. Honest boundaries

- the scoring pool is 457 rows but only 276 distinct (compound, temperature) pairs; 276 is the honest sample size
- no expansion row is ever scored, and no expansion row may be quoted as a scored observation
- the expansion set is whatever the sources tabulate, not a random sample of chemical space, so coverage bias is measured and reported rather than assumed
- Arm A and Arm B exist to separate information from target-distribution shift; a gain that fails them is a data-volume effect and is written up as one
- the primary criterion names the Morgan+Physical representation; the arm that carries it here is plus_expansion_hybrid, whose feature block is exactly the frozen hybrid block

