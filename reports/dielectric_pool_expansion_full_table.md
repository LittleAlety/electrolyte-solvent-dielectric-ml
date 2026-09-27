# Shot 13: the full released table as training material

**Generated:** 2026-09-27T07:24:39Z

**Pre-registration:** probes/dielectric_pool_expansion_prereg_v2.json (locked_before_run, 2026-09-27T07:05:00Z, sha256 5a45526be27732353a9b04a3aad63d2592512053cfc2a7123b48dc5b05e127db)

**Decision:** `co_primaries_missed` -- at least one co-primary arm misses 0.60; the achieved numbers and the shortfall are reported as they stand

## 1. The frozen side

| Quantity | Value |
|---|---|
| Scored rows | 457 |
| Scored compounds | 97 |
| Folds | 50 (10 repeats x 5) |
| Baseline reproduction | 0.4091179943351143 vs 0.4091179943351143 (abs 0.00e+00) |

## 2. The widened training pool

| Quantity | Value |
|---|---|
| Admitted rows in the merged table | 2029 |
| ... training-only | 1934 |
| ... training-only compounds | 455 |
| NBS block rows (optional arm) | 362 |
| NBS block compounds | 360 |
| Training rows per fold (mean) | 1739.2 |

## 3. Arms

| Arm | Morgan+Physical R2 | Delta vs baseline |
|---|---|---|
| `baseline_hybrid` | 0.4091179943351143 | +0.000000 |
| `full_table_hybrid` | 0.5300287425966430 | +0.120911 |
| `full_table_lever4` | 0.5433111678100043 | +0.134193 |
| `full_table_lever4_lever8` | 0.4914701852431905 | +0.082352 |
| `full_table_plus_nbs_hybrid` | 0.4544394689931626 | +0.045321 |
| `full_table_plus_nbs_lever4` | 0.5234221271950796 | +0.114304 |
| `full_table_label_placebo` | 0.0553962190214187 | -0.353722 |

## 4. Governance

| Dose | Compounds | Rows | R2 | Delta vs baseline |
|---|---|---|---|---|
| 0.25 | 114 | 362 | 0.3673756890730747 | -0.041742 |
| 0.50 | 228 | 846 | 0.3585096264143864 | -0.050608 |
| 0.75 | 341 | 1176 | 0.4664697229306144 | +0.057352 |
| 1.00 | 455 | 1934 | 0.4544394689931626 | +0.045321 |

- Arm A (compound-level label placebo on the training-only block): delta -0.353722, tolerance +0.02 -> PASS
- Arm B (monotone dose response): FAIL

## 5. Co-primary criterion

- `full_table_hybrid`: **0.5300287425966430** (shortfall +0.069971)
- `full_table_lever4_lever8`: **0.4914701852431905** (shortfall +0.108530)
- Bar: 0.60; met: **False**
- Frozen promoted headline for reference: 0.4766400383507876

## 6. Honest boundaries

- the scoring pool is 457 rows but only 276 distinct (compound, temperature) pairs
- the training-only rows come from the released table only, so this is a coverage and volume experiment inside one source, not new chemistry
- the dose curve is drawn from a single seeded permutation of training-only compounds, so each dose is one random subset rather than an average over subsets
- the frozen promoted headline stays 0.4766400383507876 until a promotion is written down deliberately

