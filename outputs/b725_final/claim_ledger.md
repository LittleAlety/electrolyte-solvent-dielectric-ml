# B725 claim ledger

generated 2026-11-25T13:34:30.617139+00:00

claims: 27  CONFIRMED=20  SUPPORTED=3  EXPLORATORY=1  UNRESOLVED=1  NOT_TESTABLE=2

## CONFIRMED (20)

| id | RQ | claim | limitation |
|---|---|---|---|
| E1 | data | LiquidBenchmark recovered from a pinned commit: 246 rows, 45 compounds, property column is explicitly 'Relative permittivity at zero frequency' (static). |  |
| E2 | data | LiquidBenchmark overlaps the frozen 239 on 25 compounds and contributes 20 compounds outside it, but those rows are ThermoML-derived and carry no per-row DOI. | overlap means corroboration, not new chemistry |
| E3 | data | ComBat `De` is rejected as a static-permittivity source: it is wrong by 40-98% on polar liquids (acetonitrile 22.23 vs 37.50; N-methylacetamide 3.97 vs 178.47) while matching nonpolar liquids to <2%. | the column mixes definitions; consequence recorded, data never used |
| E4 | data | ComBat contributes 56 compounds, 8 overlapping the frozen set; none enters any training or evaluation pool. |  |
| S1 | RQ1 | Of 239 molecules, 239 have at least one valid record; 47 have >=2 primary studies; 35 have >=2 independent laboratories. | these three counts are different quantities and must not be merged |
| S2 | RQ1 | 186 of 239 molecules (77.8%) rest on the NBS 514 compendium alone — one editorial source, not one paper per molecule. | v7.1 reported 167; v7.2 is stricter at 186 because URL-level external records without a per-row DOI no longer count as sources |
| S3 | RQ1 | Cross-source agreement: 1363 comparable pairs over 47 molecules, median relative difference 2.78%, 74.1% within 5%. | restricted to /dT/ <= 10 K |
| S4 | RQ1 | A CLEAN leave-one-source-out test is not feasible: 0 studies hold >=3 molecules that no other source also covers. Every apparent source-OOD number is a programme-shift stress test, not an unseen-source test. | this is the binding limitation of the whole study |
| S6 | RQ1 | The study supports, at most: internal-data performance and repeat-measurement agreement. It does NOT support independent-laboratory validation or new-chemical-space external generalisation. |  |
| P1 | RQ3 | The E6 metric is confirmed against the code: top-k = k largest predictions, regret = oracle-top-k mean minus model-top-k mean over the same pool, ties broken stably by index. |  |
| P2 | RQ3 | Regret instability is dominated by the CANDIDATE POOL, not by training composition: at an 80% pool the regret sd is 6.4187 vs 0.749 for training resampling (ratio 8.57). |  |
| P3 | RQ3 | Shrinking the pool changes the regret LEVEL, not just its spread: median regret 18.735 on the full pool vs 2.776 at 80% (shift -15.959). | a smaller pool makes the top-10 an easier target |
| P4 | RQ3 | The FEATURE-BLOCK ORDERING is stable under pool resampling: mu2/Vm has the lowest median regret at 100%, 80% and 60% pool fractions, followed by r2SCAN-3c electronic, xTB electronic, then structure only. |  |
| P5 | RQ3 | Only 11 of 239 molecules appear in the mu2/Vm top-10 on >=90% of pool draws; 19 appear at least once. The recommendation set is therefore NOT a stable shortlist. |  |
| P6 | RQ3 | Only 4 molecules are stable (>=90%) under BOTH the mu2/Vm and the r2SCAN-3c-electronic arms, so the two feature blocks do not agree on a shortlist. |  |
| T1 | RQ1 | Ether splits into 5 reproducible structural classes: {'chlorinated_ether': 2, 'aromatic_ether': 5, 'aliphatic_ether': 6, 'other_or_ambiguous': 1, 'cyclic_ether': 2}. | official family column unchanged; subtypes are auxiliary |
| T2 | RQ1 | Subtype LEVELS differ by 18.255 in median epsilon (chlorinated ~22 vs aliphatic ~3.7), which is a real and large effect. |  |
| T5 | RQ1 | External search found no admissible new chlorinated ether, so the n=2 limitation cannot be lifted from the recovered datasets. |  |
| C1 | RQ2 | MAE ranking is stable across 20 seeds: mu2/Vm 4.3385 < r2SCAN-3c-electronic 5.1172 < structure 7.0313, with sd <= 0.0784. |  |
| C2 | RQ3 | MAE stability does NOT carry over to regret: MAE relative dispersion is 0.018 while regret relative dispersion is 0.536. |  |

## SUPPORTED (3)

| id | RQ | claim | limitation |
|---|---|---|---|
| S5 | RQ1 | Programme-shift stress test: 8 of 14 held-out studies beat their constant baseline (mean OOD MAE 6.4869), but 0 are clean. | contaminated by compendium overlap; do not quote as generalisation |
| C3 | RQ1 | Halocarbon failure is a calibratable family-level offset, verified without leakage: honest nested calibration MAE 1.7834 vs constant baseline 1.9517. | 7 of 11 families remain diagnostic-only |
| C4 | RQ2 | On the completed 2x2 matrix the method effect (0.2718 D) exceeds the geometry effect (0.0735 D), so geometric relaxation is not the main descriptor lever. | 12-molecule preflight only; absolute sizes are small |

## EXPLORATORY (1)

| id | RQ | claim | limitation |
|---|---|---|---|
| T4 | RQ1 | The 'pooling cancelled a real within-subtype signal' explanation is consistent with the data but not significant (pooled rho p=0.618). |  |

## UNRESOLVED (1)

| id | RQ | claim | limitation |
|---|---|---|---|
| T3 | RQ1 | Within-subtype ranking is NOT demonstrated: no stratum reaches p<0.05, and the chlorinated class has n=2 so no correlation exists at all. | requires >=5 measured chlorinated ethers to settle |

## NOT_TESTABLE (2)

| id | RQ | claim | limitation |
|---|---|---|---|
| N1 | RQ1 | Independent-laboratory generalisation: the registry's laboratory layer is only publisher-level, so leave-one-LAB-out cannot be run as such. |  |
| N2 | RQ3 | Whether a larger pool with new chemistry would preserve the mu2/Vm advantage: no external dataset supplies admissible new molecules with a verified static epsilon. |  |
