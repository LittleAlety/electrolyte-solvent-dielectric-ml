# Week 8 C2: rank:pairwise head versus the regression head

**Date:** 2026-09-24
**Probe:** probes/dielectric_ranking_head_probe.py
**Summary:** probes/dielectric_ranking_head_summary.json
**Status:** closed. Negative result. No rank:pairwise advantage is established.

## The question

The screening decision that motivates the project is a ranking decision, not a
regression decision: which solvent has the highest dielectric constant. If the
metric that matters is Spearman, it is worth checking whether optimising a
pairwise ranking objective directly beats optimising squared error and reading
the ranking off the predictions.

## Why the query definition decides the answer

XGBoost's rank:pairwise objective only produces a gradient from pairs of items
that share a query id. If qid is the InChIKey, every compound is its own query,
there are no pairs, and the objective collapses.

That is not a hypothetical. The negative control run uses qid = InChIKey and
produces:

| Negative control | Value |
| --- | ---: |
| qid count | 234 |
| symmetric query size | 234 singletons |
| total within-query pair capacity | 0 |
| splits where the ranker returned a constant score | 50 of 50 |

The ranker trains without error and returns a constant. Any comparison built on
that qid would be measuring nothing.

The primary scenario therefore uses the repository's existing structural
grouping rule: ring molecules group by Murcko scaffold, acyclic molecules group
by Butina clustering of ECFP4 Morgan radius 2 at a Tanimoto distance threshold
of 0.5. That rule reads SMILES only, never the target, the predictions or the
fold assignment. It yields 111 queries, 76 of them singletons, with 799 pairs of
comparable items in total.

## Protocol

The 5 x 10 x 42 repeated-CV structure is kept, but the splitter runs at the
**qid level**: a query's rows never straddle the train/test boundary. Both heads
receive exactly the same train and test row indices on every split. This is a
structural match to the frozen benchmark, not a row-for-row reuse of its fold
table; reusing that table would force qid = InChIKey and regress to the
degenerate control.

Because a rank score has no physical scale, absolute error cannot be compared
directly between the heads. The comparison uses scale-free metrics (macro
within-query pairwise accuracy and global Spearman) plus a calibrated MAE in
which both heads go through the same nested isotonic link.

## Result

Ten-repeat means:

| Metric | rank:pairwise | regression head |
| --- | ---: | ---: |
| Macro within-query pairwise accuracy | 0.7314 | **0.8011** |
| Global Spearman | 0.7062 | **0.7888** |
| Micro pairwise accuracy | 0.6356 | **0.7009** |
| AUC (epsilon over 15) | 0.8573 | **0.8865** |
| AUC (epsilon over 30) | 0.8650 | **0.9313** |
| Calibrated MAE | 8.6132 | **7.3706** |
| Calibrated RMSE | 16.403 | **15.656** |
| Calibrated R2 | 0.185 | **0.257** |

Paired differences (rank minus regression) with a qid-cluster bootstrap:

| Metric | Delta | 95% CI | Reading |
| --- | ---: | --- | --- |
| Macro pairwise accuracy | -0.0697 | [-0.1526, +0.0042] | no gain |
| Global Spearman | -0.0826 | [-0.1462, -0.0187] | regression is better |
| Calibrated MAE | +1.2425 | [+0.4512, +2.2081] | rank head is worse |

The pre-registered rule required both the macro-pairwise and the Spearman
intervals to sit strictly above zero for the rank head to be declared superior.
Neither does; the Spearman interval is strictly below zero and the calibrated
MAE interval is strictly above zero. The decision is
no_established_rank_pairwise_advantage.

The five main splits across the ten repeats are not treated as independent
samples. The reported intervals come from a qid-cluster bootstrap, and the
ten-repeat spread is reported as a stability diagnostic only.

## What this does and does not say

It does not say pairwise ranking objectives are useless in general. It says
that on this dataset, with a defensible query definition, the pairwise objective
does not buy ranking quality over a squared-error regressor. Two structural
facts explain part of that:

* 76 of the 111 queries are singletons and contribute no pairs at all.
* The minimum within-query pair capacity across the 50 splits is 173, and the
  split-to-split variation in that capacity is large. The pairwise signal is
  thin even in the scenario designed to give it the best chance.

Note the correction to the earlier audit figure. The read-only audit reported a
minimum pair capacity of roughly 277, which is the minimum for repeat 0 only.
The probe's full 50-split minimum is 173, and the summary records the corrected
value.

## Practical consequence

The screen should keep ranking with the regression head. Switching to
rank:pairwise would cost calibrated accuracy and rank correlation with no
compensating gain, and would additionally require maintaining a scaffold/Butina
query definition that the regression head does not need.

## Verification

tests/test_dielectric_ranking_head_probe.py passes 7 tests, covering the qid
count and singleton assertions, train/test qid disjointness, the requirement
that both heads see identical split indices, the pairwise-accuracy computation
on a synthetic example, and the degenerate single-item-query behaviour. Ruff is
clean.
