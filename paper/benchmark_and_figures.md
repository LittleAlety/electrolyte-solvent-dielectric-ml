# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2 benchmark, 237 fitted rows)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Constant (train-fold mean) | raw | -0.010 | 12.33 | — | — | 8.20 |
| Morgan (ECFP4) | raw | 0.223 | 8.22 | 0.689 | 0.826 | 4.74 |
| Physical (13-dim) | raw | 0.354 | 7.50 | 0.801 | 0.936 | 4.53 |
| Morgan+Physical | raw | **0.366** | **7.13** | **0.814** | 0.929 | 4.22 |
| Morgan | log(eps-1) | 0.192 | 7.66 | 0.767 | 0.851 | 3.24 |
| Physical | log(eps-1) | 0.338 | 6.53 | **0.883** | 0.931 | 2.68 |
| Morgan+Physical | log(eps-1) | 0.315 | 6.54 | 0.881 | 0.931 | 2.58 |

The reference row is a constant predictor set to the training-fold mean on the
same 10x5 folds, recomputed from `data/processed/v032_ablation_predictions.csv`.
It replaces an earlier `Dummy (mean)` row whose 21.66 MAE could not be
reproduced from any committed artifact. A constant predictor has no ranking
signal, so its Spearman and AUC are undefined rather than 0.5.

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2
candidate model. It is selected for its consistent rank across all metrics, not
for a single best score. The log(eps-1) target improves the Physical
representation but does not transfer to the hybrid.

## Neural baselines (205-row v0.2 feature table, same 10x5 folds)

These rows were computed on `data/processed/dielectric_physical_features.csv`
(205 compounds, v0.2). They were **not** recomputed on the v0.3.2 237-row folds,
so they may only be compared against like-for-like 205-row XGBoost references.

| Model | R2 | MAE | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| MLP-Morgan | -0.447 | 12.81 | 0.170 | 0.563 |
| MLP-Physical | -0.172 | 7.43 | **0.884** | 0.940 |
| MLP-Hybrid | -0.458 | 12.89 | 0.228 | 0.646 |
| MLP-Physical (calibrated) | -0.309 | 7.81 | 0.865 | 0.937 |
| Chemprop D-MPNN | 0.237 | 7.89 | 0.665 | — |

MLP-Physical achieves the highest Spearman correlation across all models (0.884)
but with negative R2. A pre-registered linear calibration probe did not recover
positive R2, confirming this as a ranking-only representation ceiling.
Chemprop D-MPNN R2 (0.237) exceeds the like-for-like 205-row v0.2 Morgan
XGBoost baseline (0.203) but its Spearman (0.665) is lower than both Morgan
(0.697) and Physical (0.821) on that same 205-row table, reinforcing that graph
representations carry fingerprint-level information while physical features
drive ranking quality. The neural rows are retained as representation-ceiling
evidence on the v0.2 feature table; they were not recomputed on the v0.3.2
237-row fold set.

## Extrapolation: scaffold/cluster holdout (v0.3.2, 237 rows)

Source: `probes/v032_target_scaffold_summary.json` (ring Murcko scaffolds plus
acyclic ECFP4 clusters, five balanced partitions). These values supersede the
older 205-row scaffold table.

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.129 +/- 0.017 | 9.861 +/- 0.280 | 0.558 +/- 0.042 |
| Physical | raw | 0.213 +/- 0.047 | 8.950 +/- 0.549 | 0.735 +/- 0.033 |
| Morgan+Physical | raw | 0.289 +/- 0.033 | 8.406 +/- 0.420 | 0.739 +/- 0.027 |
| Morgan | log(eps-1) | 0.138 +/- 0.022 | 8.964 +/- 0.228 | 0.619 +/- 0.034 |
| **Physical** | **log(eps-1)** | **0.299 +/- 0.018** | **7.103 +/- 0.168** | **0.855 +/- 0.017** |
| Morgan+Physical | log(eps-1) | 0.279 +/- 0.016 | 7.274 +/- 0.205 | 0.832 +/- 0.016 |

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

**Figure 1. Dataset growth and source composition.**
Panel A: Cumulative compound count from v0.1 (100) through v0.2 (210) and
v0.3 (243) to v0.3.3 (246), annotated by source type (ThermoML, NBS Circular
514, open-access review tables, primary literature).
Panel B: Source-type proportions in the final v0.3.3 table.

**Figure 2. Chemical space visualization.**
UMAP or t-SNE projection of Morgan fingerprints (radius 2, 2048 bits) with
compounds colored by dielectric constant magnitude and battery-solvent families
(carbonates, ethers, nitriles, phosphates, fluorinated compounds) highlighted.

**Figure 3. Model benchmark comparison.**
Grouped bar chart of R2, MAE, and Spearman across all representations (Morgan,
Physical, Hybrid) and targets (raw, log), with error bars showing +/- 1 std
across 10 repeats.

**Figure 4. Prediction error by dielectric stratum.**
Stratified MAE for low (eps < 20), medium (20-60), and high (eps > 60)
permittivity ranges, comparing Morgan, Physical, and Hybrid representations.

**Figure 5. Domain-gap parity plot.**
Frozen v0.2 model predictions vs. experimental values for 29 new battery
solvents. High-permittivity outliers (GVL, NMP) are labeled. This figure
directly visualizes the coverage improvement in v0.3.

**Figure 6. Scaffold/cluster holdout comparison.**
R2 under random CV vs. scaffold/cluster holdout for each representation,
demonstrating the extrapolation advantage of physical features.

**Figure 7. Applicability domain boundary.**
Prediction reliability (absolute error) as a function of HBD count and
predicted permittivity, with the outside_associated_liquid region marked.

**Figure 8. Cross-source agreement.**
Scatter plot of NBS Circular 514 values vs. ThermoML values for overlapping
compounds, with median absolute deviation annotated. The four withheld
compounds (FEC, TEP, TMP, ethyl isothiocyanate) are highlighted as excluded
points, and the flagged-but-fitted row (vinylene carbonate) is annotated
separately.
