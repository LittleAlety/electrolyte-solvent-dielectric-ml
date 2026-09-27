# W19-D5: the eta channel under a second model family (Chemprop D-MPNN)

Task `week19_w19d5_chemprop_viscosity_crosscheck`, generated 2026-09-27T17:28:22Z

## 0. A correction registered before the run

The W19 plan said the kinematic residue was 214 rows still frozen and that this shot would use only thawed rows. Both halves of that sentence are wrong: 214 is a family-level exclusion count, the row-level residue is 86 rows, and `reports/decisions_log.md` 28.38 already unfroze those rows and judged the arm refuted. This probe reuses the unfrozen pools as they stand and re-thaws nothing.

## 1. What was compared

| item | incumbent | this shot |
| --- | --- | --- |
| model | Morgan count 2048 plus a temperature block, XGBoost | Chemprop D-MPNN, learned graph representation |
| extra inputs | T_K, 1000/T_K | T_K, 1000/T_K, the same two, standardized |
| split | GroupShuffleSplit by InChIKey, seed 42 | identical, hashes asserted |
| target | log10(cP) | log10(cP) |
| gate | 0.15 | 0.15, reported rather than used as the criterion |

## 2. Readings, grouped split only

| pool | rows | keys | test rows | incumbent MAE | Chemprop MAE | delta | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| row_level | 4151 | 976 | 838 | 0.15686276760094522 | 0.08506361044387624 | -0.07179915715706899 | chemprop_better |
| family_level | 3582 | 957 | 708 | 0.17477197208762 | 0.08908094784092072 | -0.08569102424669928 | chemprop_better |

Every pool reports `split_verified_against_incumbent = true`, so both models see the same train rows and the same test rows.

## 3. Verdict

Primary pool `row_level`: delta = -0.07179915715706899 log10(cP) against the registered tolerance of +/-0.02 -> **chemprop_better**.

The learned graph representation wins by more than the tolerance, so under this registered protocol the representation layer was the ceiling on this channel. That is the trigger for a follow-up lane, not a promotion.

Gate context on the primary pool: the Chemprop ensemble reads 0.08506361044387624 and the incumbent reads 0.15686276760094522 against the registered gate of 0.15.

## 4. Boundaries

- The eta channel is a separate channel from epsilon: its row and compound counts are never mixed with 457 / 97 / 276 / 2029.
- The grouped split here is GroupShuffleSplit(test_size=0.2, seed=42), not the 50-fold GroupKFold used by the epsilon scoreboard; it is the incumbent viscosity split, reproduced bit-for-bit and asserted before any member is fitted.
- The Chemprop members use a fixed epoch budget and no validation fold, so no test-fold information can select a hyperparameter or a checkpoint.
- The timing probe is not a reading; only the registered epoch budget is a reading.
- The incumbent is a frozen single-configuration, single-seed XGBoost while the Chemprop arm is a three-seed ensemble, so part of the gap can be ensembling or re-tuning rather than representation. The W18 hyperparameter arm moved the incumbent model family by only 0.01370607964226378 on the epsilon channel, so pure tuning is an unlikely explanation for a delta of this size, but the confound is not removable from this design.
- The grouped protocol here is a single 20 percent hold-out draw, so there is no fold-level variance. The three Chemprop seeds probe initialization variance only, not split variance.
- The Chemprop configuration was registered before the run and was never searched: this is an untuned neural arm against a frozen fingerprint arm, not the best that either family can do.
- A verdict of chemprop_better opens a follow-up lane. It does not by itself promote the eta channel, and it moves no epsilon number.

Nothing here is promoted and no main-scoreboard attempt is spent.
