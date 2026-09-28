# W20-1: the eta fairness review (budget-aligned arms, grouped five by five)

Task `week20_w20_1_eta_fairness`, generated 2026-09-28T12:49:06Z.

## 0. What this lane removes

W19-D5 flagged two boundaries it could not remove: the incumbent was a frozen single-configuration single-seed XGBoost against a three-seed Chemprop ensemble, and the grouped protocol was one 20 percent hold-out draw with no fold-level variance. This lane grants the incumbent the tuning and multi-seed budget, and upgrades the split to GroupKFold by InChIKey, five folds by five repeats.

## 1. What was compared

| item | incumbent_aligned | chemprop_aligned |
| --- | --- | --- |
| model | Morgan count 2048 plus a temperature block, XGBoost | Chemprop D-MPNN, learned graph representation |
| budget | three-config grid, inner GroupKFold(3) selection, three-seed ensemble | W19-D5 registered configuration, three-seed ensemble, no search |
| split | GroupKFold by InChIKey, 5 folds x 5 repeats | identical, cells shared |
| target | log10(cP) | log10(cP) |
| gate | 0.15 | 0.15, reported rather than used as the criterion |

## 2. Readings, grouped out-of-fold grid only

| pool | rows | keys | cells | incumbent mean | incumbent min | chemprop mean | chemprop min | delta | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| row_level | 4151 | 976 | 25 | 0.15963939692814613 | 0.1585952380556532 | 0.1054414994165841 | 0.10480157137745644 | -0.05419789751156204 | eta_crosses_gate_out_of_fold |
| family_level | 3582 | 957 | 25 | 0.1471395849716971 | 0.14563072278438924 | 0.1014586835798006 | 0.10048136581675947 | -0.0456809013918965 | incumbent_budget_closes_gate |

## 3. Incumbent in-place reproduction (prior)

| pool | split | observed MAE | frozen MAE | abs_gap |
| --- | --- | --- | --- | --- |
| row_level | GroupShuffleSplit(test_size=0.2, random_state=42) by inchikey | 0.15686276760094522 | 0.15686276760094522 | 0.0 |
| family_level | GroupShuffleSplit(test_size=0.2, random_state=42) by inchikey | 0.17477197208762 | 0.17477197208762 | 0.0 |

## 4. Placebo

| arm | seed | cells | grid MAE | constant predictor MAE | collapsed |
| --- | --- | --- | --- | --- | --- |
| placebo_shuffled_target | 20260928 | 25 | 0.3952143564868206 | 0.39910182316678505 | False |

## 5. Verdict

Primary pool `row_level`: delta = -0.05419789751156204 log10(cP) against the registered tolerance of +/-0.02 -> **eta_crosses_gate_out_of_fold**.

Under a five-fold by five-repeat grouped protocol, with the incumbent granted the tuning and multi-seed budget it was denied, the Chemprop arm still leads by more than the tolerance and the two gate states are unchanged. The eta channel crosses its gate out of fold.

Gate context on the primary pool: the Chemprop arm reads 0.1054414994165841 (min 0.10480157137745644)
 and the incumbent reads 0.15963939692814613 (min 0.1585952380556532) against the registered gate of 0.15.

**W20-3 decision**: Only a verdict of eta_crosses_gate_out_of_fold authorises W20-3 to fold eta into the ranking key v1. Every other verdict means W20-3 must NOT fold eta in.
Authorised to fold eta in: **True**.

## 6. Boundaries

- The eta channel is a separate channel from epsilon: its row and compound counts are never mixed with 457 / 97 / 276 / 2029.
- The split is GroupKFold by InChIKey, five folds by five repeats, so there is fold-level variance here that the W19-D5 single hold-out could not give. The folds are group-disjoint by construction and that is asserted before any arm is fitted.
- The incumbent arm is granted strictly MORE budget than the Chemprop arm: a three-config grid with inner grouped selection plus a three-seed ensemble, against the Chemprop arm registered configuration plus a three-seed ensemble with no search. The design is conservative against the Chemprop arm.
- The Chemprop epoch budget was reduced 60 -> 30 before the run under the declared amendment rule, because the registered 60-epoch grid extrapolated to several hours. The split, the pools and the arms were not reduced.
- The Chemprop configuration was registered in W19-D5 and was never searched: this is still an untuned neural arm against a budget-aligned fingerprint arm, not the best that either family can do.
- A verdict of eta_crosses_gate_out_of_fold authorises W20-3 to fold eta into the ranking key v1. It promotes nothing, and it moves no epsilon number.

## 7. Registered as not verifiable

- Whether a hyperparameter search on the Chemprop arm would move the verdict is not verifiable from this design: the search budget was spent on the incumbent.
- The upstream provenance of the pooled rows (extraction, density pairing, unit conversion) is reused and not re-verified here.
- GroupKFold removes group leakage by InChIKey but does not remove scaffold or chemistry-family similarity, so new-chemistry generalisation is not verified.
- The placebo probes permuted labels only; permuted features and permuted groups are not probed, so the placebo is a one-sided collapse check.
- The incumbent in-place reproduction is exact on the W19-D5 GroupShuffleSplit split only; it is not a reproduction of the 5x5 grid, which has no prior.
- Per-seed readings pair a Chemprop seed with the incumbent seed of the same index; that pairing is a reporting convenience and carries no physical meaning.

Nothing here is promoted and no main-scoreboard attempt is spent. The frozen baseline 0.4091179943351143 and the frozen headline 0.4766400383507876 are not touched. No Reaxys value appears anywhere in this lane.

