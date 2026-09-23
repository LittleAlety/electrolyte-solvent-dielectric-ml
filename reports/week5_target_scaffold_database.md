# Week 5: target transform, scaffold holdout, and data-source audit

## Decision summary

Week 5 does not establish a single universally best model. It establishes a
representation-target pairing:

- Random repeated CV ranks raw `Morgan+Physical` best by R2 (`0.320 +/- 0.022`).
- `log(epsilon - 1)` improves pure Physical features on both MAE
  (`7.238 -> 6.066`) and R2 (`0.283 -> 0.303`), and raises Spearman from
  `0.821` to `0.899`.
- The transform is rejected for Morgan and for the raw-scale hybrid because
  R2 decreases under the pre-registered rule.
- Under the scaffold/cluster holdout, Physical with `log(epsilon - 1)` has
  the best mean R2 (`0.267 +/- 0.014`) and MAE (`6.718 +/- 0.316`).
- The raw hybrid remains competitive under scaffold holdout (R2
  `0.263 +/- 0.032`), while the log hybrid has the best AUC above 30
  (`0.911 +/- 0.007`).

The correct next modelling decision is therefore not "always log-transform".
It is to retain both raw and transformed heads during screening and select by
the decision objective.

## Target-transform decisions

| Representation | Decision | Raw R2 | Log R2 | Raw MAE | Log MAE |
| --- | --- | ---: | ---: | ---: | ---: |
| Morgan | rejected | 0.203 | 0.173 | 7.654 | 7.296 |
| Physical | accepted | 0.283 | 0.303 | 7.238 | 6.066 |
| Morgan+Physical | rejected | 0.320 | 0.285 | 6.726 | 6.130 |

The rule was frozen before comparison: accept only when both MAE decreases and
R2 increases under the same 10x5 random CV.

## Scaffold/cluster holdout

All 205 modelling compounds are partitioned into:

- ring molecules grouped by Murcko scaffold;
- acyclic molecules grouped by ECFP4 Butina clusters at distance threshold
  `0.5`.

The resulting 98 groups are evaluated with five balanced partitions
(`42-46`), each with five folds of 41 compounds. The independent verifier
reconstructs the groups from SMILES, confirms that no group spans a fold, and
reproduces all 90 metric rows and 18,450 predictions.

| Target | Representation | R2 | MAE | Spearman | AUC >30 |
| --- | --- | ---: | ---: | ---: | ---: |
| raw | Morgan | 0.123 +/- 0.018 | 9.116 +/- 0.302 | 0.551 +/- 0.042 | 0.765 +/- 0.023 |
| raw | Physical | 0.190 +/- 0.117 | 8.288 +/- 0.786 | 0.766 +/- 0.037 | 0.899 +/- 0.015 |
| raw | Morgan+Physical | 0.263 +/- 0.032 | 7.804 +/- 0.365 | 0.765 +/- 0.021 | 0.898 +/- 0.010 |
| log(epsilon-1) | Morgan | 0.124 +/- 0.012 | 8.390 +/- 0.343 | 0.635 +/- 0.049 | 0.797 +/- 0.009 |
| log(epsilon-1) | Physical | 0.267 +/- 0.014 | 6.718 +/- 0.316 | 0.861 +/- 0.021 | 0.902 +/- 0.010 |
| log(epsilon-1) | Morgan+Physical | 0.255 +/- 0.008 | 6.801 +/- 0.157 | 0.837 +/- 0.027 | 0.911 +/- 0.007 |

The holdout is a difficult chemical-generalization test. Mean MAE is `6.7-9.1`
and the `epsilon > 60` stratum remains poor, so the model is suitable for
ranking and triage rather than direct experimental prediction across new
chemical families.

## Data-source audit

The audit separates verified training rows from search hits and restricted
cross-check records.

| Source | Status | Evidence | Trainable additions |
| --- | --- | --- | ---: |
| v0.2 dataset | current training base | 210 compounds | 0 |
| NBS Circular 514 | public candidate pool | 215 resolved; 114 eligible; 110 selected | 0 promoted; 4 pending review |
| NIST ThermoML | local snapshot | 11,646 observations; 100 near-298 pure keys | 0 new |
| ChalkLab | local archive | 103 all-temperature pure keys; 0 new near-298 | 0 |
| SpringerMaterials | restricted cross-check | 60 matched compounds | 0 |
| Landolt-Bornstein 2015 | subscription | 217 chapter queue, values not transcribed | 0 automatic |
| ChemDataExtractor | text-mined records | 60,804 records, 11,054 compounds, no independent T | 0 |
| Crossref dataset search | metadata only | 1,198 dataset records by title/filter | 0 verified |
| DataCite search | metadata only | 0 exact query records | 0 |

Conclusion: there is no audited public-source path from 210 to 300-400
training compounds without manual source-specific transcription and rights
review. The four extra NBS candidates are small hydrocarbons pending manual
review and should not be counted as additions before promotion.

## Evidence

- Database audit:
  `probes/database_recheck.json` and `data/processed/database_recheck.csv`
- Target/scaffold summary:
  `probes/dielectric_target_scaffold_summary.json`
- Metrics:
  `data/processed/dielectric_target_scaffold_metrics.csv`
- Predictions:
  `data/processed/dielectric_target_scaffold_predictions.csv`
- Scaffold assignments:
  `data/processed/dielectric_scaffold_folds.csv`
- Figure:
  `probes/artifacts/dielectric_target_scaffold.png`

The independent verifier reports `11/11` checks and reconstructs scaffold
groups independently from the source SMILES.
