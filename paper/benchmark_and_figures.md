# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2 benchmark, 236 fitted rows)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Constant (train-fold mean) | raw | -0.012 | 11.75 | — | — | 7.84 |
| Morgan (ECFP4) | raw | 0.240 | 7.61 | 0.722 | 0.837 | 4.38 |
| Physical (13-dim) | raw | 0.342 | 7.10 | 0.802 | 0.937 | 4.33 |
| Morgan+Physical | raw | **0.364** | **6.69** | **0.828** | 0.933 | 3.95 |
| Morgan | log(eps-1) | 0.187 | 7.32 | 0.766 | 0.845 | 3.20 |
| Physical | log(eps-1) | 0.290 | 6.37 | 0.880 | 0.926 | 2.70 |
| Morgan+Physical | log(eps-1) | 0.293 | 6.27 | 0.878 | 0.927 | 2.55 |

The reference row is a constant predictor set to the training-fold mean on the
same 10x5 folds, recomputed from `data/processed/v032_ablation_predictions.csv`.
The 236 fitted rows are the 241 featurized v0.3.2 rows minus four xTB failures
and minus vinylene carbonate, which the dataset flags `model_ready=false`;
`read_modelling_rows` withholds it and reports it separately.
It replaces an earlier `Dummy (mean)` row whose 21.66 MAE could not be
reproduced from any committed artifact. A constant predictor has no ranking
signal, so its Spearman and AUC are undefined rather than 0.5.

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2
candidate model. It is selected for its consistent rank across all metrics, not
for a single best score. The log(eps-1) target improves the Physical
representation but does not transfer to the hybrid.

## Neural baselines (205-row v0.2 feature table, same 10x5 folds)

These rows were computed on `data/processed/dielectric_physical_features.csv`
(205 compounds, v0.2). They were **not** recomputed on the v0.3.2 236-row folds,
so they may only be compared against like-for-like 205-row XGBoost references.
They also predate the `model_ready` gate, which the 205-row v0.2 table never
triggers (no v0.2 compound is flagged).

| Model | R2 | MAE | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| MLP-Morgan | -0.447 | 12.81 | 0.170 | 0.563 |
| MLP-Physical | -0.172 | 7.43 | **0.884** | 0.940 |
| MLP-Hybrid | -0.458 | 12.89 | 0.228 | 0.646 |
| MLP-Physical (calibrated) | -0.309 | 7.81 | 0.865 | 0.937 |
| Chemprop D-MPNN | 0.237 | 7.89 | 0.665 | 0.857 |

MLP-Physical achieves the highest Spearman correlation across all models (0.884)
but with negative R2. A pre-registered linear calibration probe did not recover
positive R2, confirming this as a ranking-only representation ceiling.
Chemprop D-MPNN R2 (0.237) exceeds the like-for-like 205-row v0.2 Morgan
XGBoost baseline (0.203) but its Spearman (0.665) is lower than both Morgan
(0.697) and Physical (0.821) on that same 205-row table, reinforcing that graph
representations carry fingerprint-level information while physical features
drive ranking quality. The neural rows are retained as representation-ceiling
evidence on the v0.2 feature table; they were not recomputed on the v0.3.2
236-row fold set.

## Extrapolation: scaffold/cluster holdout (v0.3.2, 236 rows)

Source: `probes/v032_target_scaffold_summary.json` (ring Murcko scaffolds plus
acyclic ECFP4 clusters, five balanced partitions). These values supersede the
older 205-row scaffold table.

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.138 +/- 0.014 | 9.097 +/- 0.239 | 0.597 +/- 0.014 |
| Physical | raw | 0.268 +/- 0.051 | 8.082 +/- 0.317 | 0.747 +/- 0.016 |
| Morgan+Physical | raw | 0.295 +/- 0.027 | 7.806 +/- 0.105 | 0.756 +/- 0.017 |
| Morgan | log(eps-1) | 0.130 +/- 0.020 | 8.442 +/- 0.188 | 0.639 +/- 0.024 |
| **Physical** | **log(eps-1)** | **0.276 +/- 0.044** | **6.669 +/- 0.218** | **0.862 +/- 0.016** |
| Morgan+Physical | log(eps-1) | 0.261 +/- 0.029 | 6.885 +/- 0.129 | 0.838 +/- 0.015 |

Physical with log(eps-1) is the best representation for scaffold extrapolation,
confirming that physical descriptors generalize better to novel chemical
structures than fingerprint-based representations.

## Domain-gap external test: frozen v0.2 model on 29 new battery solvents

| Representation | R2 | Spearman |
|---|---|---|
| Morgan | 0.122 | 0.692 |
| RDKit Physical | 0.154 | 0.367 |
| Morgan+Physical (hybrid) | 0.286 | 0.590 |
| v0.2 CRV reference (hybrid) | 0.320 | 0.830 |

The external R2 of 0.286 (vs. 0.320 cross-validation) confirms that the v0.2
model partially generalizes to battery-relevant solvents. The systematic
underprediction of high-permittivity targets (GVL, NMP) directly visualizes
the domain gap that v0.3's expanded coverage aims to close.

# Figures

The v1.0 manuscript carries six figures. Each one names the artifact that holds
the rendered file and a committed command that re-renders it, so a reader can
reproduce every panel without the authors. Two of the six (Figures 1 and 4) are
produced by a purpose-built figure probe that fails when the numbers it draws
stop matching the committed summaries; the other four are re-rendered from the
committed benchmark summaries by the probes that computed them. Panels that earlier drafts listed as
separate figures (chemical-space projection, applicability-domain error split,
cross-source scatter) are reported as tables or prose instead: they either
duplicated a panel above or rested on fewer than ten compounds, and a six-figure
budget is easier to audit than an eight-figure one that repeats itself.

**Figure 1. Dataset growth and source composition.**
Panel A: compounds in each released roster (v0.1 100, v0.2 210, v0.3 243,
v0.3.2 245, v0.3.3 246) with the 236-row modelling subset marked. That subset is
frozen on the v0.3.2 table and is re-derived in the figure as 245 rows - 4 rows
named in the five-row curated exclusion list that are present in that source -
4 rows failing the xTB physical features - 1 row
withheld by `model_ready` = 236.
Panel B: provenance mix of the current 246-row roster by `evidence_level` (208
v0.2 core values, 20 open-access review-table values, 17 open-access primary
measurements, 1 secondary compilation with no traceable primary source),
annotated with the gate counts (240 `model_ready=true`, 6 withheld), the single
extended-temperature row (EC at 313.15 K) and the 45 ThermoML rows that also
appear in the independent Chodera et al. (2015) extraction from the same archive.
Artifact: `probes/artifacts/paper_fig1_dataset_growth.png`.
Script: `python probes/paper_figure_dataset_growth.py` (the probe re-reads every
roster digest and fails if the row counts or the exclusion arithmetic drift).

**Figure 2. Main benchmark across representations and targets.**
R2, MAE, RMSE and Spearman rho for the Morgan, RDKit-physical and hybrid
representations under the frozen 10x5 repeated cross-validation on 236 rows,
with error bars of +/- 1 SD across the ten repeats. The hybrid representation is
the best of the three on R2 (0.364), Spearman (0.828) and MAE (6.69), and the
physical block is what carries the improvement over Morgan.
Artifact: `probes/artifacts/v032_ablation.png` (`probes/v032_ablation_summary.json`).
Script: `python probes/dielectric_representation_ablation.py --plot-only --summary-output probes/v032_ablation_summary.json --plot probes/artifacts/v032_ablation.png` (re-rendering this artifact from the committed summary reproduces the
tracked file byte for byte).

**Figure 3. Domain-gap parity plot.**
Frozen v0.2 model predictions against experimental permittivity for the 29
battery-relevant solvents added in v0.3, one panel per representation; points
whose absolute error exceeds 10 are labelled. On this external set the frozen
model reaches R2 = 0.122 (Morgan), 0.154 (RDKit physical) and 0.286 (hybrid).
The two worst calls are the polar solvents at the right edge: gamma-valerolactone
(36.1) and N-methylpyrrolidone (32.2) are both predicted near 13-16, the same
range as the non-polar diluents.
Artifact: `probes/artifacts/domain_gap_parity.png` (`probes/g2_domain_gap_summary.json`).
Script: `python probes/g2_domain_gap_test.py`.

**Figure 4. Split-conformal coverage is marginal and collapses above eps 60.**
Panel A: empirical coverage of the nominal 90% split-conformal interval inside
eps < 20 (n = 182), 20-60 (n = 47) and eps > 60 (n = 5), for the three
representations. Marginal coverage sits at the nominal level for all three
(0.9153-0.9156), but the same intervals cover 0.0145 (Morgan), 0.2568 (physical)
and 0.0382 (hybrid) of the eps > 60 compounds.
Panel B: re-scaling the residual by 1+|prediction| raises eps > 60 coverage to
0.1995, 0.4778 and 0.2881 respectively, and still does not restore nominal
coverage, because a marginal interval does not become conditional by rescaling
its width. The eps > 60 stratum holds five compounds, so these conditional
values are an exploratory diagnostic and are not claimed as a coverage
guarantee. The analogous failure of the point predictions is in the benchmark
tables: hybrid MAE is 3.9 below eps 20 and 63.8 above eps 60.
Artifact: `probes/artifacts/paper_fig4_conformal_strata.png`.
Script: `python probes/paper_figure_conformal_strata.py` (the probe fails if the
marginal guarantee stops holding or the high-permittivity collapse disappears).

**Figure 5. Target transform and scaffold/cluster holdout.**
R2, MAE, Spearman rho and AUC > 30 for random cross-validation against
scaffold/cluster holdout, crossed with the raw and log(eps-1) targets. Under
cluster holdout the physical and hybrid representations retain R2 = 0.27-0.29
where Morgan falls to 0.14, which is the quantitative form of the extrapolation
claim: what survives leaving the scaffold neighbourhood is the physical block,
not the fingerprint.
Artifact: `probes/artifacts/v032_target_scaffold.png` (`probes/v032_target_scaffold_summary.json`).
Script: `python probes/dielectric_target_and_scaffold.py --plot-only --summary-output probes/v032_target_scaffold_summary.json --plot probes/artifacts/v032_target_scaffold.png` (likewise byte-identical to the tracked artifact).

**Figure 6. NBS Circular 514 temperature harmonization to 298.15 K.**
Panel A: the shift eps(298.15 K) - eps(tabulated) implied by the coefficients
printed in the circular, over the 74 transcribed records that carry one; the
median shift is 0.0 and the mean is -0.15.
Panel B: the same shift as a percentage of the tabulated value (mean absolute
1.4%). The panel exists to bound a systematic error, not to move data: 0.762 of
the coefficient rows state a validity range that covers 25 C, 18 records state a
range that excludes it, and only those 18 would need the harmonization to be
treated as an extrapolation. No value in the frozen dataset is modified by this
probe.
Artifact: `probes/artifacts/nbs514_alpha_harmonization.png` (`probes/nbs514_alpha_harmonization_summary.json`).
Script: `python probes/nbs514_alpha_harmonization_probe.py`.

## Applicability domain (reported as prose, not a figure)

The adopted boundary is structural rather than a predicted-dielectric
threshold: the SMARTS pattern `[O,S,N;!H0]` counts textbook
hydrogen-bond donors, so the trigger is independent of any model output. The
structural donor rule triggers on 2,070 of the 6,150 out-of-fold rows (33.66%)
and covers all 150 rows whose experimental permittivity exceeds 60. Mean
absolute error is 5.02 permittivity units inside the domain and 11.51 outside
it. The superseded variant, which combined the donor count with a predicted
dielectric above 60, reached only 5 of those 150 rows and was retired for
reading the model output the boundary exists to qualify. An earlier draft
carried this material as Figure 7; it is two numbers and a flag table
(`data/processed/dielectric_applicability_flags.csv`), so it is reported here instead.
